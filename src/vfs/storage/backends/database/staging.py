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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ulid import ULID

from vfs.paths import byte_length
from vfs.results import ResultError, VFSErrorKind, already_exists, classified, wrong_kind
from vfs.storage.backends.database.descent import ancestor_chain

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping

    from vfs.paths import ObjectKind, Path

Status = Literal["created", "updated", "unchanged"]
# Which execution pass writes a staged row's material columns. Distinct
# vocabulary from Status, which reports what a finished op did.
PersistenceState = Literal["insert", "update", "absorb", "adopt"]


@dataclass
class StagedEntry:
    """One path's planned final state: a create or a material update."""

    path: Path
    parent: Path
    kind: ObjectKind
    persistence: PersistenceState  # which pass writes this row; arbitration may rewrite it
    entry_id: str  # durable identity: minted for creates; an arbitration clobber adopts the rival's
    content: str | None = None
    content_hash: str | None = None
    size_bytes: int = 0
    lines: int = 0
    ext: str | None = None
    mime_type: str | None = None
    base_version: int | None = None  # the version the guarded arm compares against
    version: int = 1  # "insert" mints 1; "update" stages base + 1; "absorb"/bumped "adopt" learn post-execution

    def refresh_material(
        self,
        *,
        kind: ObjectKind,
        content: str | None,
        content_hash: str | None,
        size_bytes: int,
        lines: int,
        ext: str | None,
        mime_type: str | None,
    ) -> None:
        """Replace material state, preserving identity and persistence bookkeeping."""
        self.kind = kind
        self.content = content
        self.content_hash = content_hash
        self.size_bytes = size_bytes
        self.lines = lines
        self.ext = ext
        self.mime_type = mime_type

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

    def __init__(self, committed: dict[str, RowMapping], *, user_id: str | None, budget: int) -> None:
        self.committed = committed
        self.user_id = user_id
        self.budget = budget
        self.staged: dict[Path, StagedEntry] = {}
        self.bump_versions: dict[str, int] = {}
        self.errors: list[ResultError] = []
        self.pending: list[tuple[Path, Status]] = []

    def kind_of(self, path: Path) -> str | None:
        staged = self.staged.get(path)
        if staged is not None:
            return staged.kind
        row = self.committed.get(str(path))
        return row["kind"] if row is not None else None

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
                VFSErrorKind.unaddressable,
                f"Path exceeds this engine's {self.budget}-byte key budget: {path}",
                path,
                target=path,
            )
        )
        return False

    def parent_gate(self, path: Path, *, parents: bool, target: Path) -> bool:
        """The POSIX parent rule: wrong_kind is unconditional; absence needs the flag."""
        for ancestor in ancestor_chain(path):
            kind = self.kind_of(ancestor)
            if kind is None:
                if parents:
                    return True
                self.errors.append(
                    classified(VFSErrorKind.not_found, f"Not found: {ancestor}", ancestor, target=target)
                )
                return False
            if kind != "directory":
                self.errors.append(
                    classified(VFSErrorKind.wrong_kind, f"Not a directory: {ancestor}", ancestor, target=target)
                )
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
        ext: str | None,
        mime_type: str | None,
        overwrite: bool,
        parents: bool,
    ) -> Status | None:
        """Gate and stage one content-bearing row; ``None`` means an error was appended."""
        if not self.within_budget(target):
            return None
        if not self.parent_gate(target, parents=parents, target=target):
            return None
        occupant = self.kind_of(target)
        if occupant is not None:
            if occupant == "directory":
                self.errors.append(wrong_kind("directory", target))
                return None
            if not overwrite:
                self.errors.append(already_exists(target))
                return None
        self.mint_chain(target)
        stage = self.stage_create if occupant is None else self.stage_update
        stage(
            target,
            kind=kind,
            content=content,
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            ext=ext,
            mime_type=mime_type,
        )
        return "created" if occupant is None else "updated"

    def put_dir(self, target: Path, *, parents: bool) -> Status | None:
        occupant = self.kind_of(target)
        if occupant is not None:
            if occupant != "directory":
                self.errors.append(classified(VFSErrorKind.wrong_kind, f"Not a directory: {target}", target))
                return None
            return "unchanged"
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
        ext: str | None = None,
        mime_type: str | None = None,
    ) -> None:
        prior = self.staged.get(path)
        if prior is not None:  # a repeat target folds into the one staged row
            prior.refresh_material(
                kind=kind,
                content=content,
                content_hash=content_hash,
                size_bytes=size_bytes,
                lines=lines,
                ext=ext,
                mime_type=mime_type,
            )
            return
        self.staged[path] = StagedEntry(
            path=path,
            parent=path.parent_dir,
            kind=kind,
            persistence="insert",
            entry_id=str(ULID()),
            content=content,
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            ext=ext,
            mime_type=mime_type,
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
        ext: str | None,
        mime_type: str | None,
    ) -> None:
        prior = self.staged.get(path)
        if prior is not None:
            prior.refresh_material(
                kind=kind,
                content=content,
                content_hash=content_hash,
                size_bytes=size_bytes,
                lines=lines,
                ext=ext,
                mime_type=mime_type,
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
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            ext=ext,
            mime_type=mime_type,
            base_version=row["version"],
            version=row["version"] + 1,
        )

    def derive_bumps(self) -> dict[str, str]:
        """The directories whose membership this batch changes: path → entry_id.

        Derived from final staged states, after arbitration, so it cannot
        go stale: every surviving insert attaches a child to its parent. A
        parent standing as this batch's own insert already reflects that
        membership in its fresh row; a committed parent — including one
        acquired at arbitration (adopt), whose identity the staged entry
        carries — owes a guarded bump proving it still lives at its
        address. Absorb and adopt rows attach nothing themselves: the
        occupant they resolved to already held the address.
        """
        bumps: dict[str, str] = {}
        for staged in self.staged.values():
            if staged.persistence != "insert":
                continue
            parent = self.staged.get(staged.parent)
            if parent is None:
                bumps[str(staged.parent)] = self.committed[str(staged.parent)]["entry_id"]
            elif parent.persistence != "insert":
                bumps[str(parent.path)] = parent.entry_id
        return bumps
