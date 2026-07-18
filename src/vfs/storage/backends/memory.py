"""In-memory storage backend — the reference ``StorageBackend``.

``InMemoryStorage`` implements the read, pattern-search, and mutation
families over a plain dict, honoring the POSIX parent rules natively:
mutations never mint missing ancestors unless the caller passes
``parents=True``, and an ancestor stored as a non-directory is
``wrong_kind`` unconditionally.

    fs = VirtualFileSystem(storage=InMemoryStorage())     # tmpfs-like node

With ``allow_files=False`` the store carries namespace shape only —
directories and mount points — and refuses file content as
``unsupported``.  A bare ``VirtualFileSystem()`` defaults to that mode,
so a router's namespace is stored without becoming an accidental RAM
file store.

Batch ops (entry writes, move/copy pairs, multi-target edits and
deletes) stage against a copy and commit only on full success — the
in-memory analogue of the transaction a database backend opens inside
each op.  Failures enumerate per entry: a failed batch reports every
failing target, not just the first, stamps the requested target into
``error.data`` so value-identical failures stay distinct, and commits
nothing.  Overlapping targets are order-independent: a cascade delete
subsumes requested descendants and repeats (judged against committed
state), while a move refuses duplicate sources and sources inside
another moved source as a batch-shape conflict.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from dataclasses import replace as clone_row
from typing import TYPE_CHECKING, Literal

from pydantic import ValidationError

from vfs.models import Entry, Match, Observation
from vfs.paths import Path, edge_out_path, extract_extension
from vfs.results import Result, ResultError, VFSErrorKind
from vfs.storage import storage_ops
from vfs.storage.replace import replace

if TYPE_CHECKING:
    from collections.abc import Mapping

    from vfs.ops import CaseMode, GrepOutputMode, Op
    from vfs.paths import ObjectKind
    from vfs.storage import ResolvedPair
    from vfs.storage.replace import EditOperation

_Status = Literal["created", "updated", "unchanged", "deleted"]

ROOT = Path("/")

# Stored kinds that carry editable text content; everything else is
# shape or metadata and refuses read/edit of content.
_CONTENT_KINDS = frozenset({"file", "chunk", "version"})


@dataclass
class _Row:
    """One stored object: the kind plus whatever content/metadata it carries.

    ``revision`` is per-entry monotone: fresh rows mint 1, every material
    mutation or bump adds 1. Two rows' revisions are never comparable.
    """

    kind: ObjectKind
    content: str | None = None
    edge_type: str | None = None
    revision: int = 1


class InMemoryStorage:
    """Dict-backed storage: read + pattern search + mutation families.

    ``allow_files=False`` switches the store to directories-only mode:
    every op that would store non-directory content classifies
    ``unsupported``, while directory mutations, reads, and name search
    keep working.  ``capabilities()`` declares the full implemented set
    either way — capability speaks ops, not per-kind guarantees.
    """

    def __init__(
        self,
        *,
        allow_files: bool = True,
        name: str = "memory",
        description: str = "In-memory storage",
    ) -> None:
        self.name = name
        self.description = description
        self._allow_files = allow_files
        self._rows: dict[Path, _Row] = {ROOT: _Row(kind="directory")}

    def capabilities(self) -> frozenset[Op]:
        return storage_ops(self)

    def traits(self) -> Mapping[str, str]:
        # Live-state scan: no index tier, so results are never stale.
        return {"grep_tier": "scan", "grep_staleness": "none", "revision_encoding": "per_entry64"}

    # -------------------------------------------------------------------
    # Read family
    # -------------------------------------------------------------------

    async def read(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        rows: list[Observation] = []
        errors: list[ResultError] = []
        # Per-row: a bad row classifies and the loop continues, so a batch
        # returns every good row plus one error per failure.
        for target in self._targets(path, observations):
            row = self._rows.get(target)
            if row is None:
                errors.append(self._classify_miss(self._rows, target))
                continue
            if row.kind not in _CONTENT_KINDS:
                # The prose names the row's actual kind — a directly
                # addressed edge row is not a directory.
                article = "an" if row.kind[0] in "aeiou" else "a"
                errors.append(_classified(VFSErrorKind.wrong_kind, f"Is {article} {row.kind}: {target}", target))
                continue
            rows.append(self._observe(target, row, content=True))
        return Result(ops=("read",), observations=rows, errors=errors)

    async def stat(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        rows: list[Observation] = []
        errors: list[ResultError] = []
        for target in self._targets(path, observations):
            row = self._rows.get(target)
            if row is None:
                errors.append(self._classify_miss(self._rows, target))
                continue
            rows.append(self._observe(target, row))
        return Result(ops=("stat",), observations=rows, errors=errors)

    async def ls(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        rows: list[Observation] = []
        errors: list[ResultError] = []
        for target in self._targets(path, observations, default=ROOT):
            row = self._rows.get(target)
            if row is None:
                errors.append(self._classify_miss(self._rows, target))
                continue
            if row.kind != "directory":
                rows.append(self._observe(target, row))
                continue
            children = [p for p in self._rows if p != ROOT and p.parent_dir == target]
            rows.extend(self._observe(p, self._rows[p]) for p in sorted(children))
        return Result(ops=("ls",), observations=rows, errors=errors)

    async def tree(
        self,
        *,
        path: Path,
        max_depth: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        if max_depth is not None and max_depth < 1:
            return _fail("tree", VFSErrorKind.invalid, f"max_depth must be >= 1, got {max_depth}")
        row = self._rows.get(path)
        if row is None:
            return Result(ops=("tree",), errors=[self._classify_miss(self._rows, path)])
        if row.kind != "directory":
            return Result(ops=("tree",), observations=[self._observe(path, row)])
        rows = [
            self._observe(p, self._rows[p])
            for p in sorted(self._rows)
            if (depth := _depth_below(p, path)) is not None and (max_depth is None or depth <= max_depth)
        ]
        return Result(ops=("tree",), observations=rows)

    # -------------------------------------------------------------------
    # Pattern search
    # -------------------------------------------------------------------

    async def glob(
        self,
        *,
        pattern: str,
        paths: tuple[Path, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        scope = paths or tuple(o.path for o in observations or [])
        wanted_ext = frozenset(e.lstrip(".").lower() for e in ext)
        rows: list[Observation] = []
        for p in sorted(self._rows):
            if max_count is not None and len(rows) >= max_count:
                break
            if p == ROOT or not _in_scope(p, scope):
                continue
            subject = str(p) if "/" in pattern else p.name
            if not fnmatch.fnmatchcase(subject, pattern):
                continue
            if wanted_ext and (extract_extension(p) or "") not in wanted_ext:
                continue
            rows.append(self._observe(p, self._rows[p]))
        return Result(ops=("glob",), observations=rows)

    async def grep(
        self,
        *,
        pattern: str,
        paths: tuple[Path, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        case_mode: CaseMode = "sensitive",
        fixed_strings: bool = False,
        word_regexp: bool = False,
        invert_match: bool = False,
        before_context: int = 0,
        after_context: int = 0,
        output_mode: GrepOutputMode = "lines",
        max_count: int | None = None,
        allow_scan: bool = False,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        # allow_scan is a no-op: this backend is already the scan tier.
        regex = _compile_grep(pattern, case_mode=case_mode, fixed_strings=fixed_strings, word_regexp=word_regexp)
        if regex is None:
            return _fail("grep", VFSErrorKind.invalid, f"Invalid pattern: {pattern!r}")
        scope = paths or tuple(o.path for o in observations or [])
        want = frozenset(e.lstrip(".").lower() for e in ext)
        avoid = frozenset(e.lstrip(".").lower() for e in ext_not)
        rows: list[Observation] = []
        for p in sorted(self._rows):
            row = self._rows[p]
            if row.content is None or row.kind not in _CONTENT_KINDS or not _in_scope(p, scope):
                continue
            file_ext = extract_extension(p) or ""
            if (want and file_ext not in want) or file_ext in avoid:
                continue
            if globs and not any(fnmatch.fnmatchcase(str(p), g) for g in globs):
                continue
            if globs_not and any(fnmatch.fnmatchcase(str(p), g) for g in globs_not):
                continue
            hit = _grep_file(
                p,
                row.content,
                regex,
                revision=row.revision,
                invert_match=invert_match,
                before_context=before_context,
                after_context=after_context,
                output_mode=output_mode,
                max_count=max_count,
            )
            if hit is not None:
                rows.append(hit)
        return Result(ops=("grep",), observations=rows)

    # -------------------------------------------------------------------
    # Mutation family
    # -------------------------------------------------------------------

    async def write(
        self,
        *,
        entries: list[Entry],
        overwrite: bool = True,
        parents: bool = False,
        user_id: str | None = None,
    ) -> Result:
        return self._write_entries(entries, overwrite=overwrite, parents=parents)

    async def edit(
        self,
        *,
        edits: list[EditOperation],
        path: Path | None = None,
        observations: list[Observation] | None = None,
        user_id: str | None = None,
    ) -> Result:
        if not self._allow_files:
            return self._directories_only("edit")
        staged = dict(self._rows)
        edited: list[Path] = []
        errors: list[ResultError] = []
        for target in self._targets(path, observations):
            row = staged.get(target)
            if row is None:
                errors.append(self._classify_miss(staged, target))
                continue
            if row.kind not in _CONTENT_KINDS or row.content is None:
                errors.append(_classified(VFSErrorKind.wrong_kind, f"No editable content: {target}", target))
                continue
            content = row.content
            failed: ResultError | None = None
            for op in edits:
                outcome = replace(content, op.old, op.new, replace_all=op.replace_all)
                if not outcome.success or outcome.content is None:
                    failed = _classified(VFSErrorKind.invalid, outcome.error or "edit failed", target)
                    break
                content = outcome.content
            if failed is not None:
                errors.append(failed)
                continue
            try:
                # Edits synthesize content, so the result re-enters the same
                # gate writes pass: Entry owns every content invariant.
                Entry(path=target, kind=row.kind, content=content)
            except ValidationError as exc:
                errors.append(_classified(VFSErrorKind.invalid, exc.errors()[0]["msg"], target))
                continue
            staged[target] = clone_row(row, content=content, revision=row.revision + 1)
            edited.append(target)
        if errors:
            return Result(ops=("edit",), errors=errors)
        # Observe only after the whole batch is staged: a repeated target
        # re-stamps the row an earlier iteration would have observed.
        rows = [self._observe(target, staged[target], status="updated") for target in edited]
        self._rows = staged
        return Result(ops=("edit",), observations=rows)

    async def delete(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        permanent: bool = False,
        cascade: bool = True,
        user_id: str | None = None,
    ) -> Result:
        staged = dict(self._rows)
        rows: list[Observation] = []
        errors: list[ResultError] = []
        requested = self._targets(path, observations)
        unique = set(requested)
        seen: set[Path] = set()
        for target in requested:
            if target == ROOT:
                errors.append(_classified(VFSErrorKind.invalid, "Cannot delete the root directory", target))
                continue
            # A target inside another target's cascade — or a repeat — is
            # subsumed: judged against committed state, order-independent.
            covered = cascade and any(o != target and target.startswith(o + "/") for o in unique)
            if covered or target in seen:
                row = self._rows.get(target)
                if row is None:
                    errors.append(self._classify_miss(self._rows, target))
                else:
                    rows.append(self._observe(target, row, status="deleted"))
                continue
            seen.add(target)
            row = staged.get(target)
            if row is None:
                errors.append(self._classify_miss(staged, target))
                continue
            descendants = [p for p in staged if p.startswith(target + "/")]
            if descendants and not cascade:
                errors.append(_classified(VFSErrorKind.not_empty, f"Directory not empty: {target}", target))
                continue
            for p in (*descendants, target):
                staged.pop(p, None)
            self._bump_parent(staged, target)
            rows.append(self._observe(target, row, status="deleted"))
        if errors:
            return Result(ops=("delete",), errors=errors)
        self._rows = staged
        return Result(ops=("delete",), observations=rows)

    async def mkdir(
        self,
        *,
        path: Path,
        parents: bool = False,
        exist_ok: bool = False,
        user_id: str | None = None,
    ) -> Result:
        staged = dict(self._rows)
        occupant = staged.get(path)
        if occupant is not None:
            if exist_ok and occupant.kind == "directory":
                return Result(ops=("mkdir",), observations=[self._observe(path, occupant, status="unchanged")])
            return _fail("mkdir", VFSErrorKind.exists, f"Already exists: {path}", path)
        gate = self._parent_gate(staged, "mkdir", path, parents=parents)
        if gate is not None:
            return gate
        minted = self._mint_chain(staged, path)
        staged[path] = _Row(kind="directory")
        self._bump_parent(staged, path)
        # Observe after every stamp and bump so each row reports its
        # committed revision, not a mid-batch one.
        rows = [self._observe(p, staged[p], status="created") for p in (*minted, path)]
        self._rows = staged
        return Result(ops=("mkdir",), observations=rows)

    async def move(
        self,
        *,
        operations: list[ResolvedPair],
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        return self._transfer("move", operations, overwrite=overwrite)

    async def copy(
        self,
        *,
        operations: list[ResolvedPair],
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        return self._transfer("copy", operations, overwrite=overwrite)

    async def mkedge(
        self,
        *,
        source: Path,
        target: Path,
        edge_type: str,
        user_id: str | None = None,
    ) -> Result:
        if not self._allow_files:
            return self._directories_only("mkedge")
        for endpoint in (source, target):
            if endpoint not in self._rows:
                return _fail("mkedge", VFSErrorKind.not_found, f"Not found: {endpoint}", endpoint)
        try:
            edge_path = edge_out_path(source, target, edge_type)
        except ValueError as exc:
            return _fail("mkedge", VFSErrorKind.invalid, str(exc))
        staged = dict(self._rows)
        # Edge projections are internal machinery — their meta ancestors are
        # minted implicitly, exempt from the strict parent rule.
        self._mint_chain(staged, edge_path)
        prior = staged.get(edge_path)
        status = "updated" if prior is not None else "created"
        revision = prior.revision + 1 if prior is not None else 1
        staged[edge_path] = _Row(kind="edge", edge_type=edge_type, revision=revision)
        if status == "created":
            self._bump_parent(staged, edge_path)
        self._rows = staged
        return Result(ops=("mkedge",), observations=[self._observe(edge_path, staged[edge_path], status=status)])

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _targets(
        self,
        path: Path | None,
        observations: list[Observation] | None,
        *,
        default: Path | None = None,
    ) -> list[Path]:
        """The paths an op addresses: the single path, the rows', or *default*."""
        if path is not None:
            return [path]
        if observations is not None:
            return [o.path for o in observations]
        return [default] if default is not None else []

    def _observe(self, path: Path, row: _Row, *, content: bool = False, status: _Status | None = None) -> Observation:
        # The populated mask derives from the non-None fields here — this
        # backend fetches whole rows, so value-presence and fetched coincide.
        size = len(row.content.encode()) if row.content is not None else None
        return Observation(
            path=path,
            kind=row.kind,
            content=row.content if content else None,
            edge_type=row.edge_type,
            size_bytes=size,
            revision=row.revision,
            status=status,
        )

    def _bump_parent(self, rows: dict[Path, _Row], path: Path) -> None:
        """Unconditional parent-revision bump for a namespace mutation at *path*.

        Clones the parent row — *rows* may be a staged copy sharing row
        objects with the committed dict, and a failed batch must not leave
        a bump behind.
        """
        parent = rows.get(path.parent_dir)
        if parent is not None:
            rows[path.parent_dir] = clone_row(parent, revision=parent.revision + 1)

    def _directories_only(self, op: str) -> Result:
        return _fail(op, VFSErrorKind.unsupported, "This storage holds directories only; file content is not supported")

    def _classify_miss(self, rows: dict[Path, _Row], target: Path) -> ResultError:
        """Descent classification for a missed *target* — first failing boundary wins.

        The shared error-ordering ladder: a missing ancestor classifies
        ``not_found`` at that component; an ancestor stored as a
        non-directory classifies ``wrong_kind`` there — before any fact
        about the leaf. Only when the whole parent chain is sound is the
        miss the leaf's own ``not_found``. Every error stamps the requested
        *target* into ``data`` so sibling misses under one dead ancestor
        stay distinct through merge dedup.
        """
        for ancestor in _ancestor_chain(target):
            row = rows.get(ancestor)
            if row is None:
                return _classified(VFSErrorKind.not_found, f"Not found: {ancestor}", ancestor, target=target)
            if row.kind != "directory":
                return _classified(VFSErrorKind.wrong_kind, f"Not a directory: {ancestor}", ancestor, target=target)
        return _classified(VFSErrorKind.not_found, f"Not found: {target}", target, target=target)

    def _parent_gate(self, rows: dict[Path, _Row], op: str, path: Path, *, parents: bool) -> Result | None:
        """The POSIX parent rule: wrong_kind is unconditional; absence needs the flag."""
        for ancestor in _ancestor_chain(path):
            row = rows.get(ancestor)
            if row is None:
                if parents:
                    return None
                return _fail(op, VFSErrorKind.not_found, f"Not found: {ancestor}", ancestor, target=path)
            if row.kind != "directory":
                return _fail(op, VFSErrorKind.wrong_kind, f"Not a directory: {ancestor}", ancestor, target=path)
        return None

    def _mint_chain(self, rows: dict[Path, _Row], path: Path) -> list[Path]:
        """Create the missing ancestor directories of *path*; return them in order.

        Each mint is a namespace mutation of its own parent: the minted row
        is stamped and the parent bumped, shallowest first.
        """
        minted: list[Path] = []
        for ancestor in _ancestor_chain(path):
            if ancestor not in rows:
                rows[ancestor] = _Row(kind="directory")
                self._bump_parent(rows, ancestor)
                minted.append(ancestor)
        return minted

    def _put_file(
        self,
        staged: dict[Path, _Row],
        op: str,
        path: Path,
        content: str | None,
        *,
        kind: ObjectKind,
        overwrite: bool,
        parents: bool,
    ) -> Result | _Status:
        """Gate and stage one content-bearing row; a ``Result`` is the failure.

        Returns the staged row's status — callers observe after the whole
        batch is staged, so no observation carries a mid-batch revision.
        """
        if not self._allow_files and kind != "directory":
            return self._directories_only(op)
        gate = self._parent_gate(staged, op, path, parents=parents)
        if gate is not None:
            return gate
        occupant = staged.get(path)
        if occupant is not None:
            if occupant.kind == "directory":
                return _fail(op, VFSErrorKind.wrong_kind, f"Is a directory: {path}", path)
            if not overwrite:
                return _fail(op, VFSErrorKind.exists, f"Already exists: {path}", path)
        self._mint_chain(staged, path)
        revision = occupant.revision + 1 if occupant is not None else 1
        staged[path] = _Row(kind=kind, content=content, revision=revision)
        if occupant is None:
            self._bump_parent(staged, path)
        return "updated" if occupant is not None else "created"

    def _write_entries(self, entries: list[Entry], *, overwrite: bool, parents: bool) -> Result:
        staged = dict(self._rows)
        pending: list[tuple[Path, _Status]] = []
        errors: list[ResultError] = []
        for entry in entries:
            if entry.kind == "directory":
                occupant = staged.get(entry.path)
                if occupant is not None:
                    if occupant.kind != "directory":
                        errors.append(
                            _classified(VFSErrorKind.wrong_kind, f"Not a directory: {entry.path}", entry.path)
                        )
                        continue
                    pending.append((entry.path, "unchanged"))
                    continue
                gate = self._parent_gate(staged, "write", entry.path, parents=parents)
                if gate is not None:
                    errors.extend(gate.errors)
                    continue
                self._mint_chain(staged, entry.path)
                staged[entry.path] = _Row(kind="directory")
                self._bump_parent(staged, entry.path)
                pending.append((entry.path, "created"))
                continue
            outcome = self._put_file(
                staged,
                "write",
                entry.path,
                entry.content,
                kind=entry.kind,
                overwrite=overwrite,
                parents=parents,
            )
            if isinstance(outcome, Result):
                errors.extend(outcome.errors)
                continue
            pending.append((entry.path, outcome))
        if errors:
            return Result(ops=("write",), errors=errors)
        # Observe only after the whole batch is staged: a later entry may
        # bump a row observed earlier (sibling parent bumps, repeat paths).
        rows = [self._observe(p, staged[p], status=status) for p, status in pending]
        self._rows = staged
        return Result(ops=("write",), observations=rows)

    def _transfer(self, op: str, operations: list[ResolvedPair], *, overwrite: bool) -> Result:
        staged = dict(self._rows)
        pending: list[tuple[Path, _Status, _Row]] = []
        errors: list[ResultError] = []
        move_srcs = [pair.src for pair in operations] if op == "move" else []
        # Enumeration is best-effort past a failed pair: later pairs judge
        # against the staged state that excludes the failed pair's effect.
        for pair in operations:
            src, dest = pair.src, pair.dest
            if src != ROOT and (move_srcs.count(src) > 1 or _covering_src(src, move_srcs) is not None):
                # Overlapping move sources are a batch-shape conflict judged
                # against committed state, so the outcome is order-independent.
                if self._rows.get(src) is None:
                    errors.append(self._classify_miss(self._rows, src))
                elif move_srcs.count(src) > 1:
                    errors.append(
                        _classified(VFSErrorKind.invalid, f"Duplicate move source in batch: {src}", src, target=src)
                    )
                else:
                    ancestor = _covering_src(src, move_srcs)
                    errors.append(
                        _classified(
                            VFSErrorKind.invalid,
                            f"Cannot move {src}: inside {ancestor}, which this batch also moves",
                            src,
                            target=src,
                        )
                    )
                continue
            src_row = staged.get(src)
            if src_row is None:
                errors.append(self._classify_miss(staged, src))
                continue
            if src == ROOT or dest == ROOT:
                errors.append(_classified(VFSErrorKind.invalid, f"Cannot {op} the root directory"))
                continue
            if dest == src:
                # POSIX rename-to-self: a successful no-op, never a refusal.
                pending.append((dest, "unchanged", src_row))
                continue
            gate = self._parent_gate(staged, op, dest, parents=False)
            if gate is not None:
                errors.extend(gate.errors)
                continue
            # The rename ladder: no-replace exists first, cycle next (one
            # kind, both directions), then kind, then emptiness — last.
            occupant = staged.get(dest)
            if occupant is not None and not overwrite:
                errors.append(_classified(VFSErrorKind.exists, f"Already exists: {dest}", dest))
                continue
            if dest.startswith(src + "/"):
                errors.append(_classified(VFSErrorKind.invalid, f"Cannot {op} {src} into itself: {dest}"))
                continue
            if src.startswith(dest + "/"):
                errors.append(_classified(VFSErrorKind.invalid, f"Cannot {op} {src} onto its own ancestor: {dest}"))
                continue
            if occupant is not None:
                if (src_row.kind == "directory") != (occupant.kind == "directory"):
                    errors.append(_classified(VFSErrorKind.wrong_kind, f"Cannot {op} onto: {dest}", dest))
                    continue
                if occupant.kind == "directory" and any(p.startswith(dest + "/") for p in staged):
                    errors.append(_classified(VFSErrorKind.not_empty, f"Directory not empty: {dest}", dest))
                    continue
            moved = [(p, staged[p]) for p in list(staged) if p == src or p.startswith(src + "/")]
            # Mint every destination before mutating: one unaddressable row
            # refuses the pair whole rather than raising or tearing the tree.
            try:
                dests = [Path(dest + p[len(src) :]) if p != src else dest for p, _ in moved]
            except ValueError as exc:
                errors.append(_classified(VFSErrorKind.unaddressable, f"Cannot {op} {src}: {exc}", dest))
                continue
            # Copy mints new nodes at revision 1 (an overwritten occupant is
            # a material update instead); move keeps descendants' revisions
            # (a reparent is a material write of the moved node plus both
            # parent bumps, nothing more).
            for (p, row), new_path in zip(moved, dests, strict=True):
                if op == "copy":
                    prior = staged.get(new_path)
                    staged[new_path] = clone_row(row, revision=prior.revision + 1 if prior is not None else 1)
                else:
                    staged[new_path] = clone_row(row, revision=row.revision)
                    del staged[p]
            if op == "move":
                staged[dest] = clone_row(staged[dest], revision=staged[dest].revision + 1)
                self._bump_parent(staged, src)
                self._bump_parent(staged, dest)
            elif occupant is None:
                self._bump_parent(staged, dest)
            pending.append((dest, "updated" if occupant is not None else "created", staged[dest]))
        if errors:
            return Result(ops=(op,), errors=errors)
        # Observe only after the whole batch is staged: a later pair may
        # bump a row staged earlier. The pair's own staged row is the
        # fallback for a dest a later pair in the batch moved away.
        rows = [self._observe(p, staged.get(p, snapshot), status=status) for p, status, snapshot in pending]
        self._rows = staged
        return Result(ops=(op,), observations=rows)


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _covering_src(src: Path, srcs: list[Path]) -> Path | None:
    """The batch source whose subtree contains *src*, if any."""
    return next((other for other in srcs if other != src and src.startswith(other + "/")), None)


def _classified(
    kind: VFSErrorKind,
    message: str,
    path: Path | None = None,
    *,
    target: Path | None = None,
) -> ResultError:
    # ``target`` names the requested row so value-identical errors from
    # distinct batch targets survive merge dedup (envelope's discriminator).
    data = {"target": str(target)} if target is not None else None
    return ResultError(kind=kind, message=message, path=path, data=data)


def _fail(
    op: str,
    kind: VFSErrorKind,
    message: str,
    path: Path | None = None,
    *,
    target: Path | None = None,
) -> Result:
    return Result(ops=(op,), errors=[_classified(kind, message, path, target=target)])


def _ancestor_chain(path: Path) -> list[Path]:
    """Proper ancestors of *path*, shallowest first, root excluded."""
    chain: list[Path] = []
    node = path.parent_dir
    while node != ROOT:
        chain.append(node)
        node = node.parent_dir
    return list(reversed(chain))


def _depth_below(path: Path, anchor: Path) -> int | None:
    """Segment distance of *path* strictly below *anchor*, else ``None``."""
    base = "" if anchor == ROOT else str(anchor)
    if not path.startswith(base + "/") or path == ROOT:
        return None
    return path[len(base) + 1 :].count("/") + 1


def _in_scope(path: Path, scope: tuple[Path, ...]) -> bool:
    return not scope or any(s == ROOT or path == s or path.startswith(s + "/") for s in scope)


def _compile_grep(
    pattern: str,
    *,
    case_mode: CaseMode,
    fixed_strings: bool,
    word_regexp: bool,
) -> re.Pattern[str] | None:
    source = re.escape(pattern) if fixed_strings else pattern
    if word_regexp:
        source = rf"\b(?:{source})\b"
    insensitive = case_mode == "insensitive" or (case_mode == "smart" and pattern == pattern.lower())
    try:
        return re.compile(source, re.IGNORECASE if insensitive else 0)
    except re.error:
        return None


def _grep_file(
    path: Path,
    content: str,
    regex: re.Pattern[str],
    *,
    revision: int,
    invert_match: bool,
    before_context: int,
    after_context: int,
    output_mode: GrepOutputMode,
    max_count: int | None,
) -> Observation | None:
    """One row per matching file: matched line regions (1-indexed) in ``matches``."""
    lines = content.splitlines()
    regions: list[Match] = []
    for index, line in enumerate(lines):
        if (regex.search(line) is not None) == invert_match:
            continue
        start = max(1, index + 1 - before_context)
        end = min(len(lines), index + 1 + after_context)
        regions.append(Match(start=start, end=end, match=index + 1, content="\n".join(lines[start - 1 : end])))
        if max_count is not None and len(regions) >= max_count:
            break
    if not regions:
        return None
    if output_mode == "files":
        return Observation(path=path, kind="file", revision=revision)
    if output_mode == "count":
        return Observation(path=path, kind="file", revision=revision, score=float(len(regions)))
    return Observation(path=path, kind="file", revision=revision, content=content, matches=regions)


__all__ = ["InMemoryStorage"]
