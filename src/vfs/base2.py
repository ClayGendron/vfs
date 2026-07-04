"""VirtualFileSystem — async router whose mount boundary is the public API.

The base class owns mount routing and path rebasing.  The filesystem object
itself owns ``/`` — mounting at ``"/"`` is illegal.  It also owns the
**spine**: ``/`` plus every proper ancestor of a mount path.  Spine paths are
real directories — ``ls``/``stat``/``tree`` answer on them locally from the
mount table, a scoped fan-out landing on one expands across the mounts
beneath it, and every other verb classifies them ``wrong_kind``, exactly as
it would a stored directory.

Public methods are routers.  They resolve the terminal filesystem via
longest-prefix mount matching, then dispatch across the mount boundary:

- When the terminal is ``self``, the router drops to local storage through
  ``_call_local_impl`` — the one seam down to an ``_*_impl`` method.
- When the terminal is a child mount, the router calls the child's **public**
  method only — never the child's session, engine, or ``_*_impl``.  Values go
  in, ``Result`` comes out.

Five dispatch shapes cover the whole verb surface: single-path (most verbs),
grouped observations (chained rows, and ``graph`` over row sets), two-path
pairs (``move``/``copy``), the endpoint pair (``mkedge``), and fan-out
(``glob``/``grep``/``glean`` with no scope reach every mount in parallel).

Paths cross the public boundary as plain ``str``; the resolve gate mints
:class:`~vfs.paths.Path` once, and everything below it — routing, gating,
impl dispatch — carries the branded type.  Any path an ``_*_impl`` receives
is already proven.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple

from vfs.models2 import Entry, Observation
from vfs.ops import MUTATING_OPS
from vfs.paths import METADATA_ROOT, Path, edge_out_path, resolve_path
from vfs.permissions import (
    Permission,
    PermissionMap,
    check_writable,
    coerce_permissions,
)
from vfs.projection import TRAVERSAL_FUNCTIONS
from vfs.replace import EditOperation
from vfs.results2 import Result, ResultError, VFSErrorKind

if TYPE_CHECKING:
    from collections.abc import Coroutine, Sequence

    from vfs.ops import Op

# Grep option vocabularies — shared with the CLI grammar when it lands.
CaseMode = Literal["sensitive", "insensitive", "smart"]
GrepOutputMode = Literal["lines", "files", "count"]

# The read verbs the router answers itself on spine paths; every other verb
# classifies a spine path as a directory at the routability step.
_SPINE_READ_OPS: Final[frozenset[Op]] = frozenset({"ls", "stat", "tree"})


class TwoPathOperation(NamedTuple):
    """A source/destination pair for move or copy — the caller-facing input shape."""

    src: str
    dest: str


class ResolvedPair(NamedTuple):
    """A gated, terminal-relative src/dest pair — what move/copy impls receive.

    Distinct from :class:`TwoPathOperation` so the annotation says which side
    of the resolve gate a pair is on: raw caller strings in, minted paths out.
    """

    src: Path
    dest: Path


class VirtualFileSystem:
    """Async router base class for all VFS filesystems."""

    def __init__(
        self,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        storage: bool = False,
        allow_child_mounts: bool = True,
        permissions: Permission | PermissionMap = "read_write",
    ) -> None:
        self.name = name
        self.title = title
        self.description = description
        self._storage = storage
        self._allow_child_mounts = allow_child_mounts
        self._permission_map: PermissionMap = coerce_permissions(permissions)
        self._parent: VirtualFileSystem | None = None
        self._mounts: dict[Path, VirtualFileSystem] = {}
        self._sorted_mount_paths: list[Path] = []
        self._class_name = self.__class__.__name__

    # -------------------------------------------------------------------
    # mounts and routing
    # -------------------------------------------------------------------

    async def add_mount(self, filesystem: VirtualFileSystem, path: str | None = None) -> None:
        """Mount a child *filesystem* at *path*, which may be nested.

        *path* is optional: when omitted, the filesystem's ``name`` is used as
        the mount point, so a named filesystem can mount itself
        (``root.add_mount(VirtualFileSystem(name="data"))`` lands at ``/data``).
        An explicit *path* takes precedence; if neither *path* nor the
        filesystem's name is available, the call raises.

        *path* is interpreted relative to this filesystem: the namespace
        root is the global origin, and calling on a sub-node treats *path*
        as local to that node (so ``data.add_mount(fs, "/tmp")`` lands at the
        data-local ``/tmp``).

        Routing:

        - If *path* falls under an existing mount, the request is delegated
          to that mount — with ``/data`` mounted, ``add_mount(fs, "/data/tmp")``
          becomes ``data_fs.add_mount(fs, "/tmp")``.  This recurses to any depth.
        - Otherwise *self* owns the mount.  It is rejected when a deeper
          mount already sits beneath *path* (the reverse order: ``/data/tmp``
          first, then ``/data``), when it duplicates an instance or would
          form a cycle, or — if *self* has storage — when stored contents
          conflict with the mount point or cannot be verified (see
          ``_is_path_mountable``).

        A filesystem created with ``allow_child_mounts=False`` (e.g. a mount
        that proxies a remote/external namespace) rejects any mount whose
        owner it would be — including a delegated one — so a parent cannot
        mutate the remote's local mount table without an explicit opt-in.
        """
        mount_name = path or filesystem.name
        if not mount_name:
            msg = "add_mount needs a path or a named filesystem"
            raise ValueError(msg)
        mount_path = self._normalize_mount_path(mount_name)

        if not self._allow_child_mounts:
            msg = f"{self._class_name} does not allow child mounts"
            raise ValueError(msg)

        # A filesystem lives in one place only: reject self-mounts, re-mounts, or cycles (checked at the true root).
        if filesystem is self:
            msg = "Cannot mount a filesystem into itself"
            raise ValueError(msg)
        if filesystem._parent is not None:
            msg = f"Cannot mount at {mount_path}: that filesystem is already mounted elsewhere"
            raise ValueError(msg)
        if id(self._root()) in filesystem._reachable_ids():
            msg = (
                f"Mounting at {mount_path} would create a cycle: that filesystem already contains this namespace's root"
            )
            raise ValueError(msg)

        matched = self._match_mount(mount_path)
        if matched is not None:
            mount_at, mount_fs = matched
            if mount_at == mount_path:
                msg = f"Mount already exists at: {mount_path}"
                raise ValueError(msg)
            await mount_fs.add_mount(filesystem, mount_path.without_mount(mount_at))
            return

        # self owns mount_path
        for existing_path in self._mounts:
            if existing_path.startswith(mount_path + "/"):
                msg = f"Cannot mount at {mount_path}: it is owned by a deeper mount at {existing_path}"
                raise ValueError(msg)
        mountable, reason = await self._is_path_mountable(mount_path)
        if not mountable:
            msg = f"Cannot mount at {mount_path}: {reason}"
            raise ValueError(msg)

        filesystem._parent = self
        self._mounts[mount_path] = filesystem
        self._rebuild_sorted_mounts()

    async def remove_mount(self, path: str) -> None:
        """Unmount the filesystem at *path*, which may be nested.

        *path* is interpreted relative to this filesystem, as in
        ``add_mount``.  A nested path under an existing mount is delegated to
        that mount.  Only the mount table is updated; lifecycle
        (engine disposal) is the caller's concern — disposal happens in
        ``close()`` or via an explicit ``await fs.close()`` on a reference
        the caller retained.
        """
        mount_path = self._normalize_mount_path(path)
        matched = self._match_mount(mount_path)
        if matched is not None and matched[0] != mount_path:
            mount_at, mount_fs = matched
            await mount_fs.remove_mount(mount_path.without_mount(mount_at))
            return
        if mount_path not in self._mounts:
            msg = f"No mount at: {mount_path!r}"
            raise ValueError(msg)
        detached = self._mounts.pop(mount_path)
        detached._parent = None
        self._rebuild_sorted_mounts()

    async def close(self) -> None:
        """Close every mounted filesystem, then clear the mount table.

        Closing is polymorphic: each mount closes itself (a
        ``DatabaseFileSystem`` disposes its own engine).  The router never
        touches a child's engine directly.

        Every mount is closed even if one fails; failures are collected and
        re-raised after the table is cleared, so a single bad disposal can
        neither strand a sibling's engine nor leave the table populated.
        """
        errors: list[Exception] = []
        for fs in list(self._mounts.values()):
            try:
                await fs.close()
            except Exception as exc:
                errors.append(exc)
            fs._parent = None
        self._mounts.clear()
        self._sorted_mount_paths.clear()
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup("errors while closing mounts", errors)

    @staticmethod
    def _normalize_mount_path(path: str) -> Path:
        """Canonicalize and validate a mount path through the :class:`Path` gate.

        The gate does the normalization and structural validation (make
        absolute, drop ``.``/``..``, strip per-segment whitespace, reject
        control characters and over-long segments).  A mount path adds only
        two policy rules the generic gate cannot know: it is never the root,
        and it never uses the reserved metadata segment (``".vfs"``).  Stray
        whitespace is canonicalized like any other path, not rejected;
        interior spaces (``"/My Documents"``) are preserved.
        """
        mount_path = Path(path)
        if mount_path == "/":
            msg = "Mount path must not be empty or root"
            raise ValueError(msg)
        meta_segment = METADATA_ROOT.strip("/")
        if meta_segment in mount_path.split("/")[1:]:
            msg = f"Mount path may not use the reserved metadata segment {meta_segment!r}: {path!r}"
            raise ValueError(msg)
        return mount_path

    def _rebuild_sorted_mounts(self) -> None:
        """Rebuild the pre-sorted mount path list, longest prefix first.

        Reverse-lexicographic is enough: only mounts matching the same path
        need relative order, and those are always prefix-chains, where the
        proper prefix sorts strictly lower.
        """
        self._sorted_mount_paths = sorted(self._mounts.keys(), reverse=True)

    def _match_mount(self, path: Path) -> tuple[Path, VirtualFileSystem] | None:
        """Longest-prefix mount match for *path*."""
        for mount_path in self._sorted_mount_paths:
            if path == mount_path or path.startswith(mount_path + "/"):
                return mount_path, self._mounts[mount_path]
        return None

    def _resolve_terminal(self, path: Path) -> tuple[VirtualFileSystem, Path, Path]:
        """Walk the mount chain to find the terminal filesystem.

        Takes a gated :class:`Path` — callers resolve first.  Returns
        ``(terminal_fs, relative_path, prefix)`` where:
        - *terminal_fs* is the filesystem that owns the path
        - *relative_path* is the path within that filesystem
        - *prefix* is the accumulated mount path for rebasing results;
          ``/`` when *self* owns the path (the rebase identity)
        """
        fs = self
        prefix = Path("/")
        rel = path
        while True:
            matched = fs._match_mount(rel)
            if matched is None:
                break
            mount_path, mount_fs = matched

            fs = mount_fs
            prefix = mount_path.with_mount(prefix)
            rel = rel.without_mount(mount_path)
        return fs, rel, prefix

    def _spine_children(self, rel: Path) -> dict[str, VirtualFileSystem | None]:
        """Immediate child segments of *rel* implied by the mount table.

        Maps segment → mounted filesystem when the child IS a mount point,
        or → ``None`` when it is an intermediate spine directory (a mount
        lies deeper).  Empty when *rel* is not on the spine.  Derived from
        the mount table on every call — no new state to keep in sync.
        """
        base = "" if rel == "/" else str(rel)
        children: dict[str, VirtualFileSystem | None] = {}
        for mount_path, fs in self._mounts.items():
            if not mount_path.startswith(base + "/"):
                continue
            segment, _, deeper = mount_path[len(base) + 1 :].partition("/")
            children[segment] = None if deeper else fs
        return children

    def _is_spine_path(self, rel: Path) -> bool:
        """Whether *rel* is on the spine: ``/`` or a proper mount ancestor.

        Mount points themselves are not spine paths — they route into their
        mount, whose own root answers (the recursion the tree stands on).
        """
        return rel == "/" or bool(self._spine_children(rel))

    def _root(self) -> VirtualFileSystem:
        """Walk parent links to the top of this mount tree.

        Visited-guarded so a malformed parent chain cannot hang the walk,
        matching ``_reachable_ids``; the single-parent invariant keeps the
        chain acyclic in practice.
        """
        node = self
        seen: set[int] = set()
        while node._parent is not None and id(node) not in seen:
            seen.add(id(node))
            node = node._parent
        return node

    def _reachable_ids(self) -> set[int]:
        """Return ``id()`` of this filesystem and every transitive mount.

        Used to keep the mount graph a tree: a new mount's reachable set
        must be disjoint from the destination tree's, which rejects cycles,
        duplicate instances, and shared sub-mounts in one check — including
        the case where the incoming filesystem already carries its own
        mounts.  The walk is visited-guarded so it terminates even on a
        malformed graph.
        """
        ids: set[int] = set()
        stack: list[VirtualFileSystem] = [self]
        while stack:
            fs = stack.pop()
            if id(fs) in ids:
                continue
            ids.add(id(fs))
            stack.extend(fs._mounts.values())
        return ids

    async def _is_path_mountable(self, path: Path) -> tuple[bool, str]:
        """Return ``(ok, reason)`` for attaching a mount at *path* here.

        A mount point must not collide with stored contents: *path* itself
        must not exist and every ancestor that exists must be a directory.
        One batched ``stat`` over the lineage answers both — and rules out
        shadowed descendants too, because storage keeps the namespace
        *connected*: writes materialize every ancestor directory, so a
        descendant cannot exist without *path* showing up here.  A sparse
        backend that cannot honor that invariant must override this.

        Composed from the public verb via self-dispatch, so any storage
        backend answers correctly without overriding; an override is a
        one-query optimization, not an obligation.  Absence must surface as
        ``not_found``; any other failure is conservatively unmountable, with
        *reason* saying the contents could not be verified — a downed
        backend is not a contents conflict.
        """
        if not self._storage:
            return True, ""

        lineage = [Observation(path=path)]
        node = path.parent_dir
        while node != "/":
            lineage.append(Observation(path=node))
            node = node.parent_dir
        found, reason = await self._probe(self.stat(observations=lineage))
        if found is None:
            return False, reason
        if any(o.path == path or o.kind != "directory" for o in found):
            return False, "storage contents conflict with that mount point"
        return True, ""

    @staticmethod
    async def _probe(call: Coroutine[Any, Any, Result]) -> tuple[list[Observation] | None, str]:
        """Await a read verb for the mountability check, mapping absence to ``[]``.

        Returns ``(rows, "")`` with the rows found — ``[]`` when everything
        was ``not_found`` (pure absence, the mountable case) — or
        ``(None, reason)`` on a *classified* read failure, which the caller
        must treat as "cannot verify" and reject.  ``Result`` is the only
        failure channel a verb has, so no exception handling is needed: a raw
        exception from an impl is an impl bug and propagates with its real
        traceback rather than being masked as a mount conflict.
        """
        result = await call
        if result.success or all(e.kind == VFSErrorKind.not_found for e in result.errors):
            return list(result.observations), ""
        failure = next(e for e in result.errors if e.kind != VFSErrorKind.not_found)
        return None, f"cannot verify storage contents there ({failure.kind}: {failure.message})"

    # -------------------------------------------------------------------
    # observation grouping
    # -------------------------------------------------------------------

    def _group_observations_by_terminal(
        self,
        observations: list[Observation],
    ) -> list[tuple[VirtualFileSystem, Path, list[Observation]]]:
        """Group observations by terminal filesystem, rebasing paths.

        Returns ``[(filesystem, prefix, rebased_observations)]`` where each
        observation's path is relative to its terminal filesystem (the mount
        prefix stripped via :meth:`Observation.without_mount`).
        """
        groups: dict[tuple[int, Path], tuple[VirtualFileSystem, list[Observation]]] = {}
        for obs in observations:
            fs, _rel, prefix = self._resolve_terminal(obs.path)
            key = (id(fs), prefix)
            _fs, obs_list = groups.setdefault(key, (fs, []))
            obs_list.append(obs.without_mount(prefix))
        return [(fs, pfx, obs_list) for ((_id, pfx), (fs, obs_list)) in groups.items()]

    # -------------------------------------------------------------------
    # spine answers — the directories the mount table implies
    # -------------------------------------------------------------------

    def _storage_answers(self, op: Op) -> bool:
        """Whether self-storage joins a router-composed answer for *op*.

        The unscoped-fan-out capability rule: storage participates silently
        when capable, and its absence never fails the composed answer.
        """
        if not self._storage:
            return False
        caps = self.capabilities()
        return caps is None or op in caps

    @staticmethod
    def _absorb_not_found(result: Result) -> Result:
        """Strip a pure-absence failure — a spine directory exists regardless.

        Storage holding nothing at a spine path answers ``not_found``, but
        the mount table makes the directory real; only genuine failures
        (anything beyond absence) propagate into the composed result.
        """
        # An errorless failure is malformed; pass it through rather than promote it.
        if result.success or not result.errors or not all(e.kind == VFSErrorKind.not_found for e in result.errors):
            return result
        return Result(function=result.function, observations=list(result.observations))

    def _spine_row(self, rel: Path) -> Observation:
        """The synthesized directory row for a spine path.

        The root row carries this node's own description, so a parent reading
        a mount point composes to the child's constructor metadata — no
        parent-side special case, and never a wire call.
        """
        description = self.description if rel == "/" else None
        return Observation(path=rel, kind="directory", description=description)

    async def _spine_read(self, op: Op, rel: Path, *, user_id: str | None = None, **kwargs: Any) -> Result:
        """Answer ``ls``/``stat``/``tree`` for a spine path this router owns."""
        if op == "ls":
            return await self._spine_ls(rel, user_id=user_id, **kwargs)
        if op == "tree":
            return await self._spine_tree(rel, user_id=user_id, **kwargs)
        return Result(function="stat", observations=[self._spine_row(rel)])

    async def _spine_ls(
        self,
        rel: Path,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        """List a spine directory: storage rows plus rows synthesized from mounts.

        A mount-point child carries the mount's description; an intermediate
        child is a bare directory row.  Storage rows win on overlap, with
        synthesized fields filling only what storage left null — collisions
        are safe by construction (a mount point cannot exist in storage).
        """
        synthesized = [
            Observation(path=rel / segment, kind="directory", description=fs.description if fs else None)
            for segment, fs in self._spine_children(rel).items()
        ]
        synth = Result(function="ls", observations=synthesized)
        if not self._storage_answers("ls"):
            return synth
        stored = await self._call_local_impl("ls", path=rel, columns=columns, user_id=user_id)
        return self._absorb_not_found(stored) | synth

    async def _spine_tree(
        self,
        rel: Path,
        *,
        max_depth: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        """Tree from a spine path: storage subtree, spine skeleton, mount descent.

        Each mount at segment distance ``s`` below *rel* runs
        ``tree("/", max_depth - s)`` — skipped when the remaining budget is
        ``<= 0`` (its skeleton row stays), unlimited when *max_depth* is
        ``None``.  Incapable mounts are skipped silently, as in an unscoped
        fan-out: a tree over a region must not fail on one incapable catalog.
        """
        if max_depth is not None and max_depth < 1:
            return self._error(f"max_depth must be >= 1, got {max_depth}", kind=VFSErrorKind.invalid, function="tree")

        skeleton: dict[Path, Observation] = {}
        descents: list[tuple[VirtualFileSystem, Path, int | None]] = []
        for mount_path, fs in self._mounts.items():
            if rel != "/" and not mount_path.startswith(rel + "/"):
                continue
            tail = mount_path if rel == "/" else mount_path[len(rel) :]
            segments = tail.strip("/").split("/")
            node = rel
            for depth, segment in enumerate(segments, start=1):
                if max_depth is not None and depth > max_depth:
                    break
                node = node / segment
                description = fs.description if depth == len(segments) else None
                skeleton.setdefault(node, Observation(path=node, kind="directory", description=description))
            budget = None if max_depth is None else max_depth - len(segments)
            if budget is not None and budget <= 0:
                continue
            caps = fs.capabilities()
            if caps is not None and "tree" not in caps:
                continue
            descents.append((fs, mount_path, budget))

        async def _descend(fs: VirtualFileSystem, prefix: Path, budget: int | None) -> Result:
            r = await fs.tree("/", budget, columns=columns, user_id=user_id)
            return r.with_mount(prefix)

        results: list[Result] = []
        if self._storage_answers("tree"):
            stored = await self._call_local_impl(
                "tree",
                path=rel,
                max_depth=max_depth,
                columns=columns,
                user_id=user_id,
            )
            results.append(self._absorb_not_found(stored))
        results.append(Result(function="tree", observations=[skeleton[p] for p in sorted(skeleton)]))
        results.extend(await self._gather_settled(_descend(fs, pfx, budget) for fs, pfx, budget in descents))
        return self._merge_results(results)

    # -------------------------------------------------------------------
    # dispatch across the mount boundary
    # -------------------------------------------------------------------

    @staticmethod
    def _as_list(items: object) -> list[Any] | None:
        """Materialize a batch input (observations/entries/pairs) to a list, or
        ``None`` if it is not a batch — a non-iterable, or a bare ``str``/``bytes``.

        Materializing once rejects a non-iterable without leaking ``TypeError``,
        and lets the batch be walked more than once: a generator would otherwise
        be exhausted by the validation pass and vanish before dispatch.
        """
        if isinstance(items, (str, bytes)) or not isinstance(items, Iterable):
            return None
        return list(items)

    def capabilities(self) -> frozenset[str] | None:
        """Operations this filesystem answers as a terminal, or ``None`` for no limit.

        The router consults the terminal's set before dispatch and returns
        ``unsupported`` without a wire call when an op is absent (the no-probe
        rule). The base router imposes no limit; capability-limited leaves (an
        MCP tool catalog) override with an explicit set.
        """
        return None

    def _gate_terminal(
        self,
        fs: VirtualFileSystem,
        op: Op,
        prefix: Path,
        *,
        report: Path,
        write_rels: Sequence[Path] = (),
        spine_check: bool = True,
    ) -> Result | None:
        """Routability → capability → permission, in the pinned order.

        Every dispatch chokepoint runs this gate on its resolved terminal
        before touching it.  The order is a contract: an incapable terminal
        reads as ``unsupported``, never as a policy denial, and an unroutable
        path reads as ``not_found`` before anything else.  A spine path is
        routable but is a directory, so at the routability step it classifies
        ``wrong_kind`` — never ``not_found`` — for every verb except the
        spine reads, which are answered upstream and never gate a spine path.

        *report* is the terminal-relative path implicated in terminal-level
        failures (routability, capability); it is reported router-side —
        rebased under *prefix* — so the caller always sees the path they
        typed.  *write_rels* are the terminal-relative paths the permission
        gate checks (empty when the write target is derived later, as in
        mkedge's pre-delegation gate).  *spine_check* is switched off by the
        two chokepoints whose spine handling is deliberately elsewhere:
        grouped observations (reads peel, mutations keep today's failures)
        and mkedge (endpoints answer to the edge grammar).  Returns the
        first classified failure, else ``None``.
        """
        reported = report.with_mount(prefix)
        if fs is self and spine_check:
            for rel in (report, *write_rels):
                if self._is_spine_path(rel):
                    spine_path = rel.with_mount(prefix)
                    return self._error(
                        f"Is a directory: {spine_path}",
                        kind=VFSErrorKind.wrong_kind,
                        function=op,
                        path=spine_path,
                    )
        if fs is self and not self._storage:
            return self._error(
                f"No mount found for path: {reported}",
                kind=VFSErrorKind.not_found,
                function=op,
                path=reported,
            )
        caps = fs.capabilities()
        if caps is not None and op not in caps:
            return self._error(
                f"Operation {op!r} is not supported here",
                kind=VFSErrorKind.unsupported,
                function=op,
                path=reported,
            )
        for rel in write_rels:
            err = check_writable(fs, op, rel, mount_prefix=prefix)
            if err is not None:
                return err
        return None

    async def _call_local_impl(
        self,
        op: Op,
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> Result:
        """The one seam from the router down to *self*'s own storage.

        This is the *only* place a filesystem reaches its own ``_*_impl``.
        It is valid for ``self`` alone — a child mount is always reached
        through its public method, never through this helper.

        The pure router has no storage, so the base implementation errors.
        Storage backends override it to open their own transaction and pass
        the resulting handle (e.g. a SQL session) to ``_{op}_impl`` — the
        session contract is a backend internal the router never sees.
        """
        if not self._storage:
            return self._error(f"No storage backend for operation: {op}", kind=VFSErrorKind.unsupported, function=op)
        impl = getattr(self, f"_{op}_impl")
        return await impl(user_id=user_id, **kwargs)

    async def _dispatch_grouped_observations(
        self,
        op: Op,
        observations: list[Observation],
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> Result:
        """Route pre-grouped observation operations to terminal filesystems.

        Each group runs against its terminal filesystem: ``self`` through the
        local seam, a child mount through its public method.  Results are
        rebased and merged.

        For the spine reads (``ls``/``stat``/``tree``), observations on this
        router's own spine peel off into a synthesized local answer, so a
        chained read over spine rows round-trips.  Everything else — other
        reads, and every mutation — groups and dispatches unchanged.
        """
        rows = self._as_list(observations)
        if rows is None:
            return self._error(
                f"observations must be an iterable of Observation, got {type(observations).__name__}",
                kind=VFSErrorKind.invalid,
                function=op,
            )
        for obs in rows:
            if not isinstance(obs, Observation):
                return self._error(
                    f"observations must be Observation instances, got {type(obs).__name__}",
                    kind=VFSErrorKind.invalid,
                    function=op,
                )
            resolved = resolve_path(obs.path, mutation=op in MUTATING_OPS)
            if resolved.path is None:
                return self._error(
                    resolved.error or f"Invalid path: {obs.path!r}",
                    kind=VFSErrorKind.invalid,
                    function=op,
                )

        spine_rels: dict[Path, None] = {}
        routed = rows
        if op in _SPINE_READ_OPS:
            routed = []
            for obs in rows:
                fs, rel, _prefix = self._resolve_terminal(obs.path)
                if fs is self and self._is_spine_path(rel):
                    spine_rels.setdefault(rel)
                else:
                    routed.append(obs)

        groups = self._group_observations_by_terminal(routed)
        if not groups and not spine_rels:
            return Result(function=op, observations=[])

        # All gates run before any dispatch, so a batch touching a bad
        # terminal is rejected whole, nothing dispatched.
        for fs, prefix, group in groups:
            err = self._gate_terminal(
                fs,
                op,
                prefix,
                report=group[0].path,
                write_rels=[o.path for o in group],
                spine_check=False,
            )
            if err is not None:
                return err

        async def _run_group(
            fs: VirtualFileSystem,
            prefix: Path,
            group: list[Observation],
        ) -> Result:
            if fs is self:
                r = await self._call_local_impl(op, observations=group, user_id=user_id, **kwargs)
            else:
                r = await getattr(fs, op)(observations=group, user_id=user_id, **kwargs)
            return r.with_mount(prefix)

        coros: list[Coroutine[Any, Any, Result]] = [
            self._spine_read(op, rel, user_id=user_id, **kwargs) for rel in spine_rels
        ]
        coros.extend(_run_group(fs, pfx, group) for fs, pfx, group in groups)
        results = await self._gather_settled(coros)
        return self._merge_results(results)

    async def _route_single(
        self,
        op: Op,
        path: str | None,
        observations: list[Observation] | None,
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> Result:
        """Route a single-path or observation-based operation.

        With observations: group by filesystem, dispatch in parallel.
        With path: resolve one terminal and dispatch once — to ``self``
        through the local seam, or to a child mount through its public method.

        Exactly one of *path* / *observations* is required; neither or both
        is a caller error returned as ``invalid`` (the router never raises
        on bad input — values in, ``Result`` out).
        """
        if (path is None) == (observations is None):
            return self._error(
                "Exactly one of path or observations must be provided",
                kind=VFSErrorKind.invalid,
                function=op,
            )

        if observations is not None:
            return await self._dispatch_grouped_observations(op, observations, user_id=user_id, **kwargs)

        assert path is not None
        resolved = resolve_path(path, mutation=op in MUTATING_OPS)
        if resolved.path is None:
            return self._error(resolved.error or f"Invalid path: {path!r}", kind=VFSErrorKind.invalid, function=op)
        path = resolved.path

        fs, rel, prefix = self._resolve_terminal(path)
        # A spine path this router owns is answered from the mount table;
        # routability is satisfied by the spine, not by storage.
        if fs is self and op in _SPINE_READ_OPS and self._is_spine_path(rel):
            return await self._spine_read(op, rel, user_id=user_id, **kwargs)
        err = self._gate_terminal(fs, op, prefix, report=rel, write_rels=(rel,))
        if err is not None:
            return err

        if fs is self:
            result = await self._call_local_impl(op, path=rel, user_id=user_id, **kwargs)
        else:
            result = await getattr(fs, op)(path=rel, user_id=user_id, **kwargs)

        return result.with_mount(prefix)

    async def _route_two_path(
        self,
        op: Op,
        operations: list[TwoPathOperation],
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> Result:
        """Route src/dest pair mutations, gating every pair before any dispatch.

        Pairs arrive as caller-facing :class:`TwoPathOperation` and dispatch
        as gated, terminal-relative :class:`ResolvedPair` groups.  Both
        endpoints of a pair must resolve to the same terminal — a pair
        spanning mounts is ``cross_mount``, never a partial execution.
        ``move`` mutates both endpoints, so both are write-gated; ``copy``
        only writes ``dest``, so its source needs no mutation resolution or
        write permission.

        All pairs are *validated* up front: a single bad pair rejects the
        whole batch with nothing dispatched. Atomicity stops at validation —
        once per-terminal dispatch begins, terminals run concurrently and a
        runtime failure in one does not roll back another. True
        cross-terminal atomicity is a backend/transaction concern, not the
        router's (see also ``_route_fanout`` and ``_route_entry_batch``).
        """
        if not operations:
            return Result(function=op, observations=[])

        groups: dict[int, tuple[VirtualFileSystem, Path, list[ResolvedPair]]] = {}
        for pair in operations:
            src = resolve_path(pair.src, mutation=op == "move")
            if src.path is None:
                return self._error(src.error or f"Invalid path: {pair.src!r}", kind=VFSErrorKind.invalid, function=op)
            dest = resolve_path(pair.dest, mutation=True)
            if dest.path is None:
                return self._error(dest.error or f"Invalid path: {pair.dest!r}", kind=VFSErrorKind.invalid, function=op)

            src_fs, src_rel, src_prefix = self._resolve_terminal(src.path)
            dest_fs, dest_rel, dest_prefix = self._resolve_terminal(dest.path)
            if src_fs is not dest_fs:
                return self._error(
                    f"Cross-mount {op} is not supported: {src.path} and {dest.path} resolve to different filesystems",
                    kind=VFSErrorKind.cross_mount,
                    function=op,
                )
            # Same terminal ⇒ same prefix, so one gate covers both endpoints;
            # relaxing the cross-mount rule means gating each terminal itself.
            assert src_prefix == dest_prefix
            write_rels = (src_rel, dest_rel) if op == "move" else (dest_rel,)
            err = self._gate_terminal(src_fs, op, src_prefix, report=src_rel, write_rels=write_rels)
            if err is not None:
                return err

            key = id(src_fs)
            _fs, _pfx, pairs = groups.setdefault(key, (src_fs, src_prefix, []))
            pairs.append(ResolvedPair(src=src_rel, dest=dest_rel))

        batch_kwarg = "moves" if op == "move" else "copies"

        async def _run_group(
            fs: VirtualFileSystem,
            prefix: Path,
            group: list[ResolvedPair],
        ) -> Result:
            if fs is self:
                r = await self._call_local_impl(op, operations=group, user_id=user_id, **kwargs)
            else:
                r = await getattr(fs, op)(**{batch_kwarg: group}, user_id=user_id, **kwargs)
            return r.with_mount(prefix)

        results = await self._gather_settled(_run_group(fs, pfx, group) for fs, pfx, group in groups.values())
        return self._merge_results(results)

    async def _route_fanout(
        self,
        op: Op,
        *,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        user_id: str | None = None,
        **kwargs: object,
    ) -> Result:
        """Route a namespace-wide query: everywhere, a scope subset, or rows.

        With observations: reuse grouped dispatch.  With scope paths: group
        the scopes by terminal and dispatch each group — a scoped terminal
        that cannot answer errors ``unsupported``, like the single shape.
        With neither: fan out to self-storage and every mount in parallel
        (mount-table order), silently skipping terminals whose
        ``capabilities()`` lack *op* — the no-probe rule's purpose: one
        incapable catalog must not fail a namespace-wide query.

        A scope on this router's own spine names a *region*, not a terminal:
        it expands to self-storage scoped to it plus every mount strictly
        beneath it dispatched unscoped, under the unscoped capability rule
        (silent skip).  A scope that resolves inside a mount named the
        terminal, and keeps the explicit ``unsupported``.

        *paths* and *observations* are mutually exclusive — supplying both
        is a caller error returned as ``invalid`` rather than silently
        preferring one.
        """
        if paths and observations is not None:
            return self._error(
                f"{op} takes paths or observations, not both",
                kind=VFSErrorKind.invalid,
                function=op,
            )
        if observations is not None:
            return await self._dispatch_grouped_observations(op, observations, user_id=user_id, **kwargs)

        if paths:
            groups: dict[int, tuple[VirtualFileSystem, Path, list[Path]]] = {}
            spine_rels: dict[Path, None] = {}
            expanded: dict[int, tuple[VirtualFileSystem, Path]] = {}
            for raw in paths:
                resolved = resolve_path(raw)
                if resolved.path is None:
                    return self._error(
                        resolved.error or f"Invalid path: {raw!r}",
                        kind=VFSErrorKind.invalid,
                        function=op,
                    )
                fs, rel, prefix = self._resolve_terminal(resolved.path)
                if fs is self and self._is_spine_path(rel):
                    spine_rels.setdefault(rel)
                    for mount_path, mount in self._mounts.items():
                        if rel != "/" and not mount_path.startswith(rel + "/"):
                            continue
                        caps = mount.capabilities()
                        if caps is not None and op not in caps:
                            continue
                        expanded.setdefault(id(mount), (mount, mount_path))
                    continue
                err = self._gate_terminal(fs, op, prefix, report=rel, write_rels=(rel,))
                if err is not None:
                    return err
                key = id(fs)
                _fs, _pfx, rels = groups.setdefault(key, (fs, prefix, []))
                rels.append(rel)

            async def _run_scoped(
                fs: VirtualFileSystem,
                prefix: Path,
                rels: tuple[Path, ...],
            ) -> Result:
                if fs is self:
                    r = await self._call_local_impl(op, paths=rels, user_id=user_id, **kwargs)
                else:
                    r = await getattr(fs, op)(paths=rels, user_id=user_id, **kwargs)
                return r.with_mount(prefix)

            # An expansion already covers its whole mount, so a narrower scope
            # into the same mount is subsumed — one dispatch per terminal.
            coros = [
                _run_scoped(fs, pfx, tuple(rels)) for key, (fs, pfx, rels) in groups.items() if key not in expanded
            ]
            if spine_rels and self._storage_answers(op):
                # A root scope covers all of storage, so it dispatches unscoped.
                self_rels = () if "/" in spine_rels else tuple(spine_rels)
                coros.append(_run_scoped(self, Path("/"), self_rels))
            coros.extend(_run_scoped(mount, mount_path, ()) for mount, mount_path in expanded.values())
            if not coros:
                return Result(function=op, observations=[])
            results = await self._gather_settled(coros)
            return self._merge_results(results)

        targets: list[tuple[VirtualFileSystem, Path]] = []
        own_caps = self.capabilities()
        if self._storage and (own_caps is None or op in own_caps):
            targets.append((self, Path("/")))
        for mount_path, fs in self._mounts.items():
            child_caps = fs.capabilities()
            if child_caps is not None and op not in child_caps:
                continue
            targets.append((fs, mount_path))
        if not targets:
            return Result(function=op, observations=[])

        async def _run_target(fs: VirtualFileSystem, prefix: Path) -> Result:
            if fs is self:
                r = await self._call_local_impl(op, paths=(), user_id=user_id, **kwargs)
            else:
                r = await getattr(fs, op)(user_id=user_id, **kwargs)
            return r.with_mount(prefix)

        results = await self._gather_settled(_run_target(fs, pfx) for fs, pfx in targets)
        return self._merge_results(results)

    async def _route_entry_batch(
        self,
        entries: Sequence[Entry],
        *,
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        """Route a batch write, grouping entries by terminal via each entry's path.

        The entry-path analogue of grouped-observation dispatch: every
        entry's path is mutation-resolved and write-gated before anything
        dispatches, then each terminal receives its entries rebased into
        local coordinates via :meth:`Entry.without_mount`.
        """
        rows = self._as_list(entries)
        if rows is None:
            return self._error(
                f"write entries must be an iterable of Entry, got {type(entries).__name__}",
                kind=VFSErrorKind.invalid,
                function="write",
            )
        if not rows:
            return Result(function="write", observations=[])

        groups: dict[int, tuple[VirtualFileSystem, Path, list[Entry]]] = {}
        for entry in rows:
            if not isinstance(entry, Entry):
                return self._error(
                    f"write entries must be Entry instances, got {type(entry).__name__}",
                    kind=VFSErrorKind.invalid,
                    function="write",
                )
            resolved = resolve_path(entry.path, mutation=True)
            if resolved.path is None:
                return self._error(
                    resolved.error or f"Invalid path: {entry.path!r}",
                    kind=VFSErrorKind.invalid,
                    function="write",
                )
            fs, rel, prefix = self._resolve_terminal(resolved.path)
            err = self._gate_terminal(fs, "write", prefix, report=rel, write_rels=(rel,))
            if err is not None:
                return err
            key = id(fs)
            _fs, _pfx, entry_group = groups.setdefault(key, (fs, prefix, []))
            entry_group.append(entry.without_mount(prefix))

        async def _run_group(
            fs: VirtualFileSystem,
            prefix: Path,
            group: list[Entry],
        ) -> Result:
            if fs is self:
                r = await self._call_local_impl("write", entries=group, overwrite=overwrite, user_id=user_id)
            else:
                r = await fs.write(entries=group, overwrite=overwrite, user_id=user_id)
            return r.with_mount(prefix)

        results = await self._gather_settled(_run_group(fs, pfx, group) for fs, pfx, group in groups.values())
        return self._merge_results(results)

    @staticmethod
    async def _gather_settled(coros: Iterable[Coroutine[Any, Any, Result]]) -> list[Result]:
        """Run dispatch coroutines to completion — every sibling settles.

        ``Result`` is the only failure channel a verb has, so an exception
        here is an impl bug (or cancellation, which re-raises untouched).  A
        bug propagates only *after* all siblings finish: a partial batch can
        never keep mutating behind a caller who already saw a failure, and
        any retry logic upstream sees a settled world.

        Precedence is deliberate: cancellation outranks impl bugs.  When a
        settled batch holds both, the ``CancelledError`` re-raises and the
        bug is dropped — suppressing cancellation to surface a bug would
        break task-teardown semantics, and everything has settled either way.
        """
        settled = await asyncio.gather(*coros, return_exceptions=True)
        bugs: list[Exception] = []
        for item in settled:
            if isinstance(item, BaseException) and not isinstance(item, Exception):
                raise item
            if isinstance(item, Exception):
                bugs.append(item)
        if len(bugs) == 1:
            raise bugs[0]
        if bugs:
            raise ExceptionGroup("impl errors during dispatch", bugs)
        return [item for item in settled if isinstance(item, Result)]

    @staticmethod
    def _merge_results(results: list[Result]) -> Result:
        """Merge multiple results — any failure makes the whole a failure.

        ``|`` propagates ``success=False`` and concatenates ``errors`` while
        preserving all successful observations.  Its path-union collapses
        duplicate global paths (left wins); this is lossless here because
        terminals have disjoint mount prefixes, so their rows never collide.
        """
        if not results:
            return Result(observations=[])
        merged = results[0]
        for r in results[1:]:
            merged = merged | r
        return merged

    # -------------------------------------------------------------------
    # errors
    # -------------------------------------------------------------------

    def _error(
        self,
        message: str,
        *,
        kind: VFSErrorKind,
        function: str = "",
        path: Path | None = None,
        data: dict[str, Any] | None = None,
    ) -> Result:
        """Compose a failed ``Result``.  The router never raises — values in,
        ``Result`` out; raising is the call boundary's job (``raise_if_failed``).

        Pass the prose *message* and the structured *kind* (required), the op
        as *function* so a failure reports which verb produced it, plus an
        optional *path* and machine-readable *data*.  Callers that already
        hold a shaped ``Result`` should return it directly.
        """
        return Result(
            function=function,
            success=False,
            errors=[ResultError(kind=kind, message=message, path=path, data=data)],
        )

    # -------------------------------------------------------------------
    # public methods — reads
    # -------------------------------------------------------------------

    async def read(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._route_single("read", path, observations, columns=columns, user_id=user_id)

    async def stat(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._route_single("stat", path, observations, columns=columns, user_id=user_id)

    async def ls(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._route_single("ls", path, observations, columns=columns, user_id=user_id)

    async def tree(
        self,
        path: str,
        max_depth: int | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._route_single("tree", path, None, max_depth=max_depth, columns=columns, user_id=user_id)

    # -------------------------------------------------------------------
    # public methods — search
    # -------------------------------------------------------------------

    async def glob(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        """Match *pattern* against the namespace — unscoped calls reach every mount."""
        return await self._route_fanout(
            "glob",
            paths=paths,
            observations=observations,
            pattern=pattern,
            ext=ext,
            max_count=max_count,
            columns=columns,
            user_id=user_id,
        )

    async def grep(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
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
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        """Search content for *pattern* — unscoped calls reach every mount."""
        return await self._route_fanout(
            "grep",
            paths=paths,
            observations=observations,
            pattern=pattern,
            ext=ext,
            ext_not=ext_not,
            globs=globs,
            globs_not=globs_not,
            case_mode=case_mode,
            fixed_strings=fixed_strings,
            word_regexp=word_regexp,
            invert_match=invert_match,
            before_context=before_context,
            after_context=after_context,
            output_mode=output_mode,
            max_count=max_count,
            columns=columns,
            user_id=user_id,
        )

    async def glean(
        self,
        query: str,
        *,
        limit: int = 10,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        """Ranked search: text in, one fused ranked list out.

        The caller never picks a retrieval strategy — backends index by
        vector, lexical, and graph signals and fuse the rankings however
        they see fit.  The router passes *query* and *limit* through
        opaquely; results report ``function="glean"``.
        """
        return await self._route_fanout(
            "glean",
            paths=paths,
            observations=observations,
            query=query,
            limit=limit,
            columns=columns,
            user_id=user_id,
        )

    async def graph(
        self,
        method: str,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        depth: int | None = None,
        user_id: str | None = None,
    ) -> Result:
        """Run the graph traversal *method* — each terminal answers over its own subgraph.

        A path routes to one terminal; observations group by terminal and
        each mount runs the algorithm on its own graph, so a walk can never
        follow an edge out of its mount.  *method* is validated against the
        traversal vocabulary before any dispatch; results report the
        specific method name in ``function``.
        """
        if method not in TRAVERSAL_FUNCTIONS:
            return self._error(
                f"Unknown graph method {method!r}; expected one of {sorted(TRAVERSAL_FUNCTIONS)}",
                kind=VFSErrorKind.invalid,
                function="graph",
            )
        return await self._route_single("graph", path, observations, method=method, depth=depth, user_id=user_id)

    # -------------------------------------------------------------------
    # public methods — mutations
    # -------------------------------------------------------------------

    async def write(
        self,
        entries: Sequence[Entry] | None = None,
        *,
        path: str | None = None,
        content: str | None = None,
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        """Write one file (*path* + *content*) or a batch of *entries*.

        Batch entries route by their own paths — grouped per terminal,
        rebased, and gated per entry before anything dispatches. *entries*
        and *path*/*content* are mutually exclusive.
        """
        if entries is not None:
            if path is not None or content is not None:
                return self._error(
                    "write takes entries or path/content, not both",
                    kind=VFSErrorKind.invalid,
                    function="write",
                )
            return await self._route_entry_batch(entries, overwrite=overwrite, user_id=user_id)
        return await self._route_single("write", path, None, content=content, overwrite=overwrite, user_id=user_id)

    async def edit(
        self,
        path: str | None = None,
        old: str | None = None,
        new: str | None = None,
        edits: list[EditOperation] | None = None,
        observations: list[Observation] | None = None,
        replace_all: bool = False,
        *,
        user_id: str | None = None,
    ) -> Result:
        """Apply find-and-replace edits — a multi-edit verb by contract.

        *edits* is the native input: applied sequentially (each edit sees
        the content left by the previous one) and atomically (one failed
        match applies nothing) — guarantees the backend impl must honor.
        The *old*/*new* pair is sugar wrapping a one-item list; supplying
        both forms is a caller error.
        """
        if edits is not None:
            if old is not None or new is not None:
                return self._error(
                    "edit takes old/new or an edits list, not both",
                    kind=VFSErrorKind.invalid,
                    function="edit",
                )
            ops = self._as_list(edits)
            if ops is None or not all(isinstance(e, EditOperation) for e in ops):
                return self._error(
                    "edit edits must be an iterable of EditOperation",
                    kind=VFSErrorKind.invalid,
                    function="edit",
                )
            edits = ops
        else:
            if old is None or new is None:
                return self._error(
                    "edit requires old and new strings, or an edits list",
                    kind=VFSErrorKind.invalid,
                    function="edit",
                )
            edits = [EditOperation(old=old, new=new, replace_all=replace_all)]
        return await self._route_single("edit", path, observations, edits=edits, user_id=user_id)

    async def delete(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        permanent: bool = False,
        cascade: bool = True,
        user_id: str | None = None,
    ) -> Result:
        return await self._route_single(
            "delete",
            path,
            observations,
            permanent=permanent,
            cascade=cascade,
            user_id=user_id,
        )

    async def mkdir(self, path: str, *, user_id: str | None = None) -> Result:
        return await self._route_single("mkdir", path, None, user_id=user_id)

    async def mkedge(
        self,
        source: str,
        target: str,
        edge_type: str,
        *,
        user_id: str | None = None,
    ) -> Result:
        """Create a typed edge from *source* to *target*.

        Both endpoints must resolve to the same terminal (``cross_mount``
        otherwise — cross-server edges are a later story).  The terminal
        writes the canonical ``edges/out`` projection; the inverse ``in``
        path is derived, never a write target.
        """
        if not isinstance(edge_type, str):
            return self._error(
                f"edge_type must be a string, got {type(edge_type).__name__}",
                kind=VFSErrorKind.invalid,
                function="mkedge",
            )
        src = resolve_path(source)
        if src.path is None:
            return self._error(src.error or f"Invalid path: {source!r}", kind=VFSErrorKind.invalid, function="mkedge")
        tgt = resolve_path(target)
        if tgt.path is None:
            return self._error(tgt.error or f"Invalid path: {target!r}", kind=VFSErrorKind.invalid, function="mkedge")

        src_fs, src_rel, src_prefix = self._resolve_terminal(src.path)
        tgt_fs, tgt_rel, _ = self._resolve_terminal(tgt.path)
        if src_fs is not tgt_fs:
            return self._error(
                f"Cross-mount edges are not supported: {src.path} and {tgt.path} resolve to different filesystems",
                kind=VFSErrorKind.cross_mount,
                function="mkedge",
            )
        # Spine classification stays off: edge endpoints answer to the edge
        # grammar (root/reserved endpoints reject as invalid, not wrong_kind).
        err = self._gate_terminal(src_fs, "mkedge", src_prefix, report=src_rel, spine_check=False)
        if err is not None:
            return err

        if src_fs is not self:
            # The child re-derives the edge path and gates it against its own
            # permission map — rules live in filesystem-relative coordinates.
            result = await src_fs.mkedge(src_rel, tgt_rel, edge_type, user_id=user_id)
            return result.with_mount(src_prefix)

        try:
            edge_path = edge_out_path(src_rel, tgt_rel, edge_type)
        except ValueError as exc:
            return self._error(str(exc), kind=VFSErrorKind.invalid, function="mkedge")
        err = check_writable(self, "mkedge", edge_path, mount_prefix=src_prefix)
        if err is not None:
            return err
        result = await self._call_local_impl(
            "mkedge",
            source=src_rel,
            target=tgt_rel,
            edge_type=edge_type,
            user_id=user_id,
        )
        return result.with_mount(src_prefix)

    @staticmethod
    def _coerce_two_path(item: object) -> TwoPathOperation | None:
        """Coerce a batch item to a ``TwoPathOperation``, or ``None`` if malformed.

        Accepts a ``TwoPathOperation`` as-is or a 2-tuple/list of two strings.
        Anything else — wrong arity, non-string members, a stray ``str`` that
        a ``Sequence`` iteration would splatter into characters — is rejected
        so the caller sees ``invalid`` instead of a raw ``TypeError``.
        """
        if isinstance(item, TwoPathOperation):
            return item
        if isinstance(item, (tuple, list)) and len(item) == 2:
            src, dest = item
            if isinstance(src, str) and isinstance(dest, str):
                return TwoPathOperation(src=src, dest=dest)
        return None

    async def move(
        self,
        src: str | None = None,
        dest: str | None = None,
        moves: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
        *,
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        return await self._route_pairs("move", src, dest, moves, overwrite=overwrite, user_id=user_id)

    async def copy(
        self,
        src: str | None = None,
        dest: str | None = None,
        copies: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
        *,
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        return await self._route_pairs("copy", src, dest, copies, overwrite=overwrite, user_id=user_id)

    async def _route_pairs(
        self,
        op: Op,
        src: str | None,
        dest: str | None,
        batch: Sequence[TwoPathOperation | tuple[str, str]] | None,
        *,
        overwrite: bool,
        user_id: str | None,
    ) -> Result:
        """Shared move/copy front: normalize the src/dest-or-batch input, then route.

        *src*/*dest* and *batch* are mutually exclusive; each batch item is
        coerced through :meth:`_coerce_two_path`, so a malformed pair is an
        ``invalid`` result rather than an uncaught ``TypeError``.
        """
        if batch is not None:
            if src is not None or dest is not None:
                return self._error(
                    f"{op} takes src/dest or a batch list, not both",
                    kind=VFSErrorKind.invalid,
                    function=op,
                )
            pairs = self._as_list(batch)
            if pairs is None:
                return self._error(
                    f"{op} batch must be an iterable of (src, dest) pairs, got {type(batch).__name__}",
                    kind=VFSErrorKind.invalid,
                    function=op,
                )
        else:
            if not src or not dest:
                return self._error(
                    f"{op} requires src and dest, or a batch list",
                    kind=VFSErrorKind.invalid,
                    function=op,
                )
            pairs = [TwoPathOperation(src=src, dest=dest)]
        operations: list[TwoPathOperation] = []
        for item in pairs:
            pair = self._coerce_two_path(item)
            if pair is None:
                return self._error(
                    f"{op} pair must be (src, dest) of two strings: {item!r}",
                    kind=VFSErrorKind.invalid,
                    function=op,
                )
            operations.append(pair)
        return await self._route_two_path(op, operations, overwrite=overwrite, user_id=user_id)

    # -------------------------------------------------------------------
    # public methods — execution
    # -------------------------------------------------------------------

    async def run(
        self,
        path: str,
        *,
        arguments: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> Result:
        """Execute the tool at *path* with *arguments* — the execution verb.

        ``read``/``stat``/``ls`` discover a tool's definition; ``run`` is the only
        verb that executes it. Not a namespace mutation, so it takes no
        write-authorization gate.
        """
        return await self._route_single("run", path, None, arguments=arguments, user_id=user_id)
