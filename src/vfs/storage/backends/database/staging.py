"""In-memory staging for the write family — the plan half of plan-then-execute.

A ``WritePlan`` overlays the committed snapshot ``writes.py`` fetched with the
rows a batch means to write, runs the POSIX parent/site gates against that
committed-plus-staged world, and accumulates classified per-entry errors. It
holds no session and runs no SQL: every method here is pure Python against
dictionaries, so a batch is fully adjudicated before any mutation statement is
built. Any error fails the batch whole — ``writes.py`` refuses to execute an
errored plan.

``StagedEntry`` is one path's planned final state — a create or a material
update — carrying the persistence bookkeeping a domain ``Entry`` never holds:
the durable ``entry_id`` (minted here for creates, copied from the committed
row for updates), the ``base_version`` guard, and ``persistence`` — which
execution pass writes the row's material columns. That is why it lives here
beside the plan and not among the session-free models.

A deleted row stays at its path with a tombstone, and the plan reads
around it: a tombstoned row is absent to every gate — a tombstoned
ancestor refuses ``not_found`` with the trashed hint, with or without
``parents`` — except at a file write's own target, where a tombstoned
file is the revive: the write stages an update that keeps the row's
identity, clears its tombstone and replaces its body, and the parent
learns a member returned. A file where a directory was deleted refuses
``wrong_kind``; a directory anywhere a tombstone sits refuses
``not_found`` — a tombstoned directory comes back only through
``restore``. Nothing is written into the trash view itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from ulid import ULID

from vfs.paths import TRASH_ROOT, byte_length, is_trash_path
from vfs.results import ErrorKind, ResultError, already_exists, classified, wrong_kind
from vfs.storage.backends.database.descent import ancestor_chain, tombstone_miss, trashed_hint

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping

    from vfs.authority import Authority
    from vfs.models.media import Source
    from vfs.paths import ObjectKind, Path

Status = Literal["created", "updated", "unchanged"]
# Which execution pass writes a staged row's material columns. Distinct
# vocabulary from Status, which reports what a finished op did.
PersistenceState = Literal["insert", "update", "absorb", "adopt"]


@dataclass
class StagedEntry:
    """One path's planned final state: a create or a material update.

    ``ext`` is derived from the path here, never accepted — the stored
    column must agree with the path-derived read gates on every row.
    """

    path: Path
    parent: Path
    kind: ObjectKind
    persistence: PersistenceState  # which pass writes this row; arbitration may rewrite it
    entry_id: str  # durable identity: minted for creates; an arbitration clobber adopts the rival's
    content: str | None = None
    data: bytes | None = None  # the bytes body of a bytes-sourced row; its text is a rendering
    source: Source = "text"
    content_hash: str | None = None
    size_bytes: int = 0
    lines: int = 0
    ext: str | None = field(init=False, default=None)
    mime_type: str | None = None
    owner_id: str | None = None  # the payload's declared owner; only the system actor honours it
    base_version: int | None = None  # the version the guarded arm compares against
    base_size_bytes: int | None = None  # the replaced body's size at snapshot; the mint pages its reads by it
    base_content: str | None = None  # the replaced text body, when the snapshot joined it; the mint keeps it unread
    base_data: bytes | None = None  # the replaced bytes body, when the snapshot joined it; its text rides base_content
    version: int = 1  # "insert" mints 1; "update" stages base + 1; "absorb"/bumped "adopt" learn post-execution
    revive: bool = False  # the update lands on a tombstoned row: its guard expects the tombstone, and its parent bumps
    expected_version: int | None = None  # the version the caller said it replaces; settle refuses any other

    def __post_init__(self) -> None:
        self.ext = self.path.ext

    def refresh_material(
        self,
        *,
        kind: ObjectKind,
        content: str | None,
        content_hash: str | None,
        size_bytes: int,
        lines: int,
        mime_type: str | None,
        owner_id: str | None = None,
        data: bytes | None = None,
        source: Source = "text",
    ) -> None:
        """Replace material state, preserving identity and persistence bookkeeping."""
        self.kind = kind
        self.content = content
        self.data = data
        self.source = source
        self.content_hash = content_hash
        self.size_bytes = size_bytes
        self.lines = lines
        self.mime_type = mime_type
        self.owner_id = owner_id

    def absorb(self, entry_id: str) -> None:
        """Lose insert arbitration to the rival row *entry_id* and clobber it.

        The row becomes an unguarded update onto the rival's identity; its
        final version is learned from the post-execution read-back, never
        staged — there is no base to predict a successor from.
        """
        self.persistence = "absorb"
        self.entry_id = entry_id

    def adopt(self, entry_id: str, version: int) -> None:
        """Lose insert arbitration to an equivalent occupant and stand down.

        No material remains to write: the occupant already is what this
        row meant to create, so identity and version become the occupant's
        — the mkdir-p forgiveness the sequential gates grant, applied at
        arbitration. No pass writes its material columns; the bump pass
        may still affirm the row as a parent of surviving inserts,
        refreshing ``version`` from its read-back.
        """
        self.persistence = "adopt"
        self.entry_id = entry_id
        self.version = version


# ---------------------------------------------------------------------------
# Write plan
# ---------------------------------------------------------------------------


class WritePlan:
    """Staged batch state: the committed snapshot, staged rows, errors.

    ``staged`` overlays ``committed`` for every gate, so entries in one
    batch see the parents earlier entries minted. Staging declares facts
    (which rows attach where); execution derives obligations from them —
    :meth:`derive_bumps` after arbitration has settled every row's final
    state, with ``bump_versions`` holding read-back values when an
    observation needs one. Any error fails the batch whole — an errored
    plan is never executed.
    """

    def __init__(
        self,
        committed: dict[str, RowMapping],
        *,
        authority: Authority | None,
        budget: int,
    ) -> None:
        self.committed = committed
        self.authority = authority
        self.budget = budget
        self.staged: dict[Path, StagedEntry] = {}
        self.bump_versions: dict[str, int] = {}
        self.errors: list[ResultError] = []
        self.pending: list[tuple[Path, Status]] = []

    def kind_of(self, path: Path) -> str | None:
        """The kind of the live row at *path* through the staged overlay; a tombstone is absent."""
        staged = self.staged.get(path)
        if staged is not None:
            return staged.kind
        row = self.committed.get(str(path))
        return row["kind"] if row is not None and row["deleted_at"] is None else None

    def tombstone_of(self, path: Path) -> RowMapping | None:
        """The tombstoned committed row at *path*; asked only where :meth:`kind_of` found no live row."""
        row = self.committed.get(str(path))
        return row if row is not None and row["deleted_at"] is not None else None

    def material_of(self, path: Path) -> tuple[str, str | None]:
        """Current kind and content through the staged overlay.

        Lawful only for a present path whose snapshot was fetched with
        content — a repeat target reads its own staged output.
        """
        staged = self.staged.get(path)
        if staged is not None:
            return staged.kind, staged.content
        row = self.committed[str(path)]
        return row["kind"], row["content"]

    def parent_id_of(self, staged: StagedEntry) -> str:
        """The parent row's ``entry_id`` through the staged overlay.

        Staged-first because a parent minted in this batch has no
        committed row; a parent that loses arbitration fails the batch
        before its children's rows are ever built.
        """
        parent = self.staged.get(staged.parent)
        if parent is not None:
            return parent.entry_id
        return self.committed[str(staged.parent)]["entry_id"]

    def within_budget(self, path: Path) -> bool:
        """A lawful path can still exceed an engine's index-key byte cap."""
        if byte_length(str(path)) <= self.budget:
            return True
        self.errors.append(
            classified(
                ErrorKind.unaddressable,
                path,
                detail=f"the path exceeds this engine's {self.budget}-byte key budget",
            )
        )
        return False

    def within_namespace(self, path: Path) -> bool:
        """The trash view is an address for reading tombstoned rows, never a place a write lands."""
        if not is_trash_path(str(path)):
            return True
        detail = f"{TRASH_ROOT} is a view over deleted rows; nothing is written there"
        self.errors.append(classified(ErrorKind.invalid, path, detail=detail))
        return False

    def parent_gate(self, path: Path, *, parents: bool, target: Path) -> bool:
        """The POSIX parent rule: wrong_kind is unconditional; absence needs the flag.

        A tombstoned ancestor is absent whatever the flag says — the
        flag mints missing directories, never revives deleted ones — and
        its refusal carries the trashed hint.
        """
        for ancestor in ancestor_chain(path):
            kind = self.kind_of(ancestor)
            if kind is None:
                tombstone = self.tombstone_of(ancestor)
                if tombstone is not None:
                    self.errors.append(tombstone_miss(ancestor, tombstone["deleted_at"], target=target))
                    return False
                if parents:
                    return True
                self.errors.append(classified(ErrorKind.not_found, ancestor, target=target))
                return False
            if kind != "directory":
                self.errors.append(wrong_kind(kind, ancestor, target=target))
                return False
        return True

    def put_file(
        self,
        target: Path,
        *,
        kind: ObjectKind,
        content: str | None,
        content_hash: str | None,
        size_bytes: int,
        lines: int,
        mime_type: str | None,
        overwrite: bool,
        parents: bool,
        owner_id: str | None = None,
        data: bytes | None = None,
        source: Source = "text",
        expected: int | None = None,
    ) -> Status | None:
        """Gate and stage one content-bearing row; ``None`` means an error was appended.

        A tombstoned file at the site is the revive: an update that keeps
        the row's identity, whatever ``overwrite`` says, since no live row
        occupies the path. A tombstoned directory refuses ``wrong_kind``
        with the trashed hint, as a live one refuses without it.

        *expected* is the version the caller says it replaces. A row
        that is expected exists, so nothing is made for it: no parent,
        no file, and no revive of a deleted one. Whether the version is
        the row's is judged later, by :meth:`settle`.
        """
        if not self.within_namespace(target) or not self.within_budget(target):
            return None
        if not self.parent_gate(target, parents=parents and expected is None, target=target):
            return None
        occupant = self.kind_of(target)
        tombstone = self.tombstone_of(target) if occupant is None else None
        # Occupied is answered before the occupant's kind, as O_EXCL answers EEXIST over a directory.
        if occupant is not None and not overwrite:
            self.errors.append(self.occupied(target))
            return None
        if occupant == "directory":
            self.errors.append(wrong_kind("directory", target))
            return None
        if tombstone is not None and tombstone["kind"] == "directory":
            hint = {"kind": "directory", **trashed_hint(tombstone["deleted_at"])}
            self.errors.append(classified(ErrorKind.wrong_kind, target, detail="directory", data=hint))
            return None
        if expected is not None and occupant is None:
            self.errors.append(tombstone_miss(target, None if tombstone is None else tombstone["deleted_at"]))
            return None
        self.mint_chain(target)
        stage = self.stage_create if occupant is None and tombstone is None else self.stage_update
        stage(
            target,
            kind=kind,
            content=content,
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            mime_type=mime_type,
            owner_id=owner_id,
            data=data,
            source=source,
        )
        if tombstone is not None:
            self.staged[target].revive = True
        self.staged[target].expected_version = expected
        return "created" if occupant is None and tombstone is None else "updated"

    def occupied(self, path: Path) -> ResultError:
        """The ``exists`` of a create-only write at the live row at *path*, naming what the stored row holds.

        A row this batch itself staged is named bare: it is not stored,
        and the refusal means it never will be.
        """
        if path in self.staged:
            return already_exists(path)
        row = self.committed[str(path)]
        return occupant_exists(path, row["version"], row["content_hash"])

    def put_dir(self, target: Path, *, parents: bool, exclusive: bool = False) -> Status | None:
        """Gate and stage one directory; a tombstone at the site is absent, and only ``restore`` brings it back.

        *exclusive* refuses any live occupant with ``exists``, a
        directory too, as ``mkdir`` does without ``exist_ok``.
        """
        if not self.within_namespace(target):
            return None
        occupant = self.kind_of(target)
        if occupant is not None:
            if exclusive:
                self.errors.append(self.occupied(target))
                return None
            if occupant != "directory":
                self.errors.append(wrong_kind(occupant, target))
                return None
            return "unchanged"
        tombstone = self.tombstone_of(target)
        if tombstone is not None:
            self.errors.append(tombstone_miss(target, tombstone["deleted_at"]))
            return None
        if not self.within_budget(target) or not self.parent_gate(target, parents=parents, target=target):
            return None
        self.mint_chain(target)
        self.stage_create(target, kind="directory")
        return "created"

    def mint_chain(self, path: Path) -> list[Path]:
        """Stage the missing ancestor directories of *path*, shallowest first."""
        minted: list[Path] = []
        for ancestor in ancestor_chain(path):
            if self.kind_of(ancestor) is None:
                self.stage_create(ancestor, kind="directory")
                minted.append(ancestor)
        return minted

    def stage_create(
        self,
        path: Path,
        *,
        kind: ObjectKind,
        content: str | None = None,
        content_hash: str | None = None,
        size_bytes: int = 0,
        lines: int = 0,
        mime_type: str | None = None,
        owner_id: str | None = None,
        data: bytes | None = None,
        source: Source = "text",
    ) -> None:
        prior = self.staged.get(path)
        if prior is not None:  # a repeat target folds into the one staged row
            prior.refresh_material(
                kind=kind,
                content=content,
                content_hash=content_hash,
                size_bytes=size_bytes,
                lines=lines,
                mime_type=mime_type,
                owner_id=owner_id,
                data=data,
                source=source,
            )
            return
        self.staged[path] = StagedEntry(
            path=path,
            parent=path.parent_dir,
            kind=kind,
            persistence="insert",
            entry_id=str(ULID()),
            content=content,
            data=data,
            source=source,
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            mime_type=mime_type,
            owner_id=owner_id,
        )

    def stage_update(
        self,
        path: Path,
        *,
        kind: ObjectKind,
        content: str | None,
        content_hash: str | None,
        size_bytes: int,
        lines: int,
        mime_type: str | None,
        owner_id: str | None = None,
        data: bytes | None = None,
        source: Source = "text",
    ) -> None:
        prior = self.staged.get(path)
        if prior is not None:
            prior.refresh_material(
                kind=kind,
                content=content,
                content_hash=content_hash,
                size_bytes=size_bytes,
                lines=lines,
                mime_type=mime_type,
                owner_id=owner_id,
                data=data,
                source=source,
            )
            return
        row = self.committed[str(path)]
        self.staged[path] = StagedEntry(
            path=path,
            parent=path.parent_dir,
            kind=kind,
            persistence="update",
            entry_id=row["entry_id"],
            content=content,
            data=data,
            source=source,
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            mime_type=mime_type,
            owner_id=owner_id,
            base_version=row["version"],
            base_size_bytes=row["size_bytes"],
            # A text row's body is its text. A bytes row's is its bytes, with the rendering beside them.
            base_content=row["content"] if "content" in row and (row["source"] == "text" or "data" in row) else None,
            base_data=row.get("data"),
            version=row["version"] + 1,
        )

    def settle(self) -> None:
        """Drop each staged update that would leave its row as it is, then refuse each stale expected version.

        It runs once, after every entry is staged, so a path written twice
        is judged on its last body. A revive is a change whatever its
        body, since it clears a tombstone, and a create has no row to
        equal. A dropped row reports ``unchanged`` and writes nothing: its
        version, its stamps and its index marks stay as they were.

        The drop comes first, so a call sent twice meets its own body and
        hears ``unchanged``, whatever version it expected. Every row left
        whose expected version is not the committed one is a ``conflict``.
        """
        same = frozenset(
            path
            for path, staged in self.staged.items()
            if staged.persistence == "update"
            and not staged.revive
            and _same_material(staged, self.committed[str(path)])
        )
        for path in same:
            del self.staged[path]
        if same:
            self.pending = [(path, "unchanged" if path in same else status) for path, status in self.pending]
        for path, staged in self.staged.items():
            if staged.expected_version is None:
                continue
            current = self.committed[str(path)]["version"]
            if staged.expected_version != current:
                self.errors.append(stale_version(path, current))

    def derive_bumps(self) -> dict[str, str]:
        """The directories whose membership this batch changes: path → entry_id.

        Derived from final staged states, after arbitration, so it cannot
        go stale: every surviving insert attaches a child to its parent. A
        parent standing as this batch's own insert already reflects that
        membership in its fresh row; a committed parent — including one
        acquired at arbitration (adopt), whose identity the staged entry
        carries — owes a guarded bump proving it still lives at its
        address. Absorb and adopt rows attach nothing themselves: the
        occupant they resolved to already held the address. A revive
        attaches too: its row was hidden, and the parent's listing changes.
        """
        bumps: dict[str, str] = {}
        for staged in self.staged.values():
            # A revive returns a member to its parent's listing as a create adds one.
            if staged.persistence != "insert" and not staged.revive:
                continue
            parent = self.staged.get(staged.parent)
            if parent is None:
                bumps[str(staged.parent)] = self.committed[str(staged.parent)]["entry_id"]
            elif parent.persistence != "insert":
                bumps[str(parent.path)] = parent.entry_id
        return bumps


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def stale_version(path: Path, current: int) -> ResultError:
    """The ``conflict`` of a write whose expected version is not the row's, naming the version there now.

    It is not retryable: the same call would carry the same stale
    version, so the caller reads the file again first.
    """
    detail = "the version expected is not the version stored"
    return classified(ErrorKind.conflict, path, detail=detail, data={"version": current})


def occupant_exists(path: Path, version: int, content_hash: str | None) -> ResultError:
    """The ``exists`` of a create that found a live row at *path*, naming the row's version and its body's hash.

    A caller that lost the reply to its own create can tell from the
    two that the row there is the one it made. A directory has no
    body, and names its version alone.
    """
    data: dict[str, object] = {"version": version}
    if content_hash is not None:
        data["content_hash"] = content_hash
    return classified(ErrorKind.exists, path, data=data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _same_material(staged: StagedEntry, row: RowMapping) -> bool:
    """Whether *staged* would store what *row* already holds: the same kind, source, body hash and type.

    Every other column a write sets is worked out from these four, or is
    a stamp that stays true while the body does. Text and bytes of the
    same body hash alike, which is why the source is compared. A body
    with no hash equals nothing.
    """
    return (
        staged.content_hash is not None
        and staged.content_hash == row["content_hash"]
        and staged.kind == row["kind"]
        and staged.source == row["source"]
        and staged.mime_type == row["mime_type"]
    )
