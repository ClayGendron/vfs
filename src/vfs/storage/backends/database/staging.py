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
the row ``entry_id``, the ``base_revision`` guard, and the create/update
discriminator. That is why it lives here beside the plan and not among the
session-free models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from vfs.results import ResultError, VFSErrorKind
from vfs.storage.backends.database.descent import ancestor_chain, classified, in_trash

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping

    from vfs.paths import ObjectKind, Path

Status = Literal["created", "updated", "unchanged"]


@dataclass
class StagedEntry:
    """One path's planned final state: a create or a material update."""

    path: Path
    parent: Path
    kind: ObjectKind
    created: bool
    content: str | None = None
    content_hash: str | None = None
    size_bytes: int = 0
    lines: int = 0
    ext: str | None = None
    mime_type: str | None = None
    entry_id: int | None = None  # committed id for updates; creates learn theirs at insert
    base_revision: int | None = None  # the update guard; None = unguarded (arbitration clobber)
    revision: int = 1  # creates mint 1; updates stage base + 1; clobbers learn theirs post-execution


# ---------------------------------------------------------------------------
# Write plan
# ---------------------------------------------------------------------------


class WritePlan:
    """Staged batch state: the committed snapshot, staged rows, bumps, errors.

    ``staged`` overlays ``committed`` for every gate, so entries in one
    batch see the parents earlier entries minted; ``bumps`` collects the
    committed directories whose membership changed, and ``bump_revisions``
    holds their read-back values when an observation needs one. Any error
    fails the batch whole — an errored plan is never executed.
    """

    def __init__(self, committed: dict[str, RowMapping], *, user_id: str | None, budget: int) -> None:
        self.committed = committed
        self.user_id = user_id
        self.budget = budget
        self.staged: dict[Path, StagedEntry] = {}
        self.bumps: set[str] = set()
        self.bump_revisions: dict[str, int] = {}
        self.errors: list[ResultError] = []
        self.pending: list[tuple[Path, Status]] = []

    def kind_of(self, path: Path) -> str | None:
        staged = self.staged.get(path)
        if staged is not None:
            return staged.kind
        row = self.committed.get(str(path))
        return row["kind"] if row is not None else None

    def outside_trash(self, path: Path) -> bool:
        """Refuse the reserved trash subtree as a write target.

        Rows minted there would be invisible to every read verb — a
        write-only hole, since the liveness filter hides the trash scope.
        """
        if not in_trash(path):
            return True
        self.errors.append(
            classified(
                VFSErrorKind.invalid,
                f"Cannot write into the reserved trash namespace: {path}",
                path,
                target=path,
            )
        )
        return False

    def within_budget(self, path: Path) -> bool:
        """A lawful path can still exceed an engine's index-key byte cap."""
        if len(str(path).encode()) <= self.budget:
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
        if not self.outside_trash(target) or not self.within_budget(target):
            return None
        if not self.parent_gate(target, parents=parents, target=target):
            return None
        occupant = self.kind_of(target)
        if occupant is not None:
            if occupant == "directory":
                self.errors.append(classified(VFSErrorKind.wrong_kind, f"Is a directory: {target}", target))
                return None
            if not overwrite:
                self.errors.append(classified(VFSErrorKind.exists, f"Already exists: {target}", target))
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
        if not self.outside_trash(target):
            return None
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
            self._refresh(prior, kind, content, content_hash, size_bytes, lines, ext, mime_type)
            return
        self.staged[path] = StagedEntry(
            path=path,
            parent=path.parent_dir,
            kind=kind,
            created=True,
            content=content,
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            ext=ext,
            mime_type=mime_type,
        )
        self.bump_parent(path)

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
            self._refresh(prior, kind, content, content_hash, size_bytes, lines, ext, mime_type)
            return
        row = self.committed[str(path)]
        self.staged[path] = StagedEntry(
            path=path,
            parent=path.parent_dir,
            kind=kind,
            created=False,
            content=content,
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            ext=ext,
            mime_type=mime_type,
            entry_id=row["id"],
            base_revision=row["revision"],
            revision=row["revision"] + 1,
        )

    def bump_parent(self, path: Path) -> None:
        """Mark a namespace mutation at *path*: its committed parent gets a bump.

        A batch-minted parent is skipped — its single fresh revision already
        reflects the membership it was created with.
        """
        parent = path.parent_dir
        if parent not in self.staged and str(parent) in self.committed:
            self.bumps.add(str(parent))

    def _refresh(
        self,
        prior: StagedEntry,
        kind: ObjectKind,
        content: str | None,
        content_hash: str | None,
        size_bytes: int,
        lines: int,
        ext: str | None,
        mime_type: str | None,
    ) -> None:
        prior.kind = kind
        prior.content = content
        prior.content_hash = content_hash
        prior.size_bytes = size_bytes
        prior.lines = lines
        prior.ext = ext
        prior.mime_type = mime_type
