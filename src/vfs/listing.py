"""What the listing verbs show at each mount point, and how the :term:`kernel` asks several storages at once.

A mount point names two entries. One is the directory stored in the storage above, and the other is
the root of the storage mounted there. :class:`MountListing` holds the rules by which ``ls``,
``stat``, ``tree``, ``glob`` and ``locate`` show the second and never the first. It is built from one
copy of the kernel's table, so every step of one call reads the same table. :func:`gather_settled`
runs the calls on several storages at the same time, and it raises a fault only once every call has
finished. :class:`PathFilters` carries the path filters of a ``glob`` or a ``grep`` that reaches
several mounts.

This module is not public. The kernel builds a :class:`MountListing` each time its table changes. The
:term:`mount` itself, and the call on its storage, come from ``vfs.mounts``.
"""

from __future__ import annotations

import asyncio
import bisect
import heapq
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple

from vfs.chain import judge_in_hand
from vfs.deadline import WALL_TIME_BUDGET, Deadline
from vfs.exceptions import raise_lone_or_group
from vfs.models import Observation
from vfs.offload import wall_truncation
from vfs.paths import ROOT, Path
from vfs.pattern_matching import ScopeChannel, compile_gates
from vfs.results import ErrorKind, Result, ResultError, classified
from vfs.results.kinds import Severity, kind_family

if TYPE_CHECKING:
    from collections.abc import Container, Coroutine, Iterable, Mapping, Sequence

    from vfs.authority import Authority
    from vfs.mounts import AskStorage, Location, Mount
    from vfs.ops import Op

# The fields of a bare row, which says only that a directory is there.
BARE_FIELDS: Final[frozenset[str]] = frozenset({"path", "kind"})

# The refusals that say what a caller may see. Any other failure says the storage could not answer.
_DENIALS: Final = frozenset({ErrorKind.not_found, ErrorKind.permission_denied, ErrorKind.unauthenticated})

# What shrinks a ``glob`` that could not judge every mount point in time.
_POINTS_REFINE_GUIDANCE: Final = "narrow the pattern or its exclusions"

# ---------------------------------------------------------------------------
# What a listing shows at a mount point
# ---------------------------------------------------------------------------


class PathFilters(NamedTuple):
    """The caller's path filters, in the four channels of :class:`~vfs.pattern_matching.GlobGates`.

    Apart from the keywords that are passed straight on, this is the one argument that ``glob`` and
    ``grep`` hand the :term:`kernel` for a call that reaches several mounts. ``admissions`` is glob's
    pattern, as its :term:`arms <arm>`, or grep's ``globs``. ``exclusions`` is ``globs_not`` on both
    verbs. These two are rewritten for each mount before they reach its storage. They are sent as
    written beside the roots that lie beneath the mount. For the few roots that lie above it, they are
    joined to the root and cut down to the part inside the mount. The two ``ext`` channels reach the
    storage unchanged. The kernel reads them only to judge a root's own row and the mount points.
    """

    admissions: tuple[str, ...]
    exclusions: tuple[str, ...]
    ext: tuple[str, ...]
    ext_not: tuple[str, ...]


def bare_directory(path: Path) -> Observation:
    """Return a row that says a directory is at ``path`` and nothing more."""
    return Observation.model_validate({"path": path, "kind": "directory", "populated": BARE_FIELDS})


async def gather_settled(coros: Iterable[Coroutine[Any, Any, Result]]) -> list[Result]:
    """Run the calls on several storages at the same time, and return their results once all are done.

    A verb reports failure only through a :class:`Result`, so an exception here is a fault in the
    code, or a cancellation. A fault is raised only after every call has finished. A batch can then
    never go on changing things behind a caller who has already seen a failure, and anything that
    retries sees a world that has stopped moving. Several faults are raised together as a group.

    A cancellation comes before a fault. If the finished batch holds both, the cancellation is raised
    and the fault is dropped. Hiding a cancellation to show a fault would break the way a task is torn
    down, and everything has finished either way.
    """
    settled = await asyncio.gather(*coros, return_exceptions=True)
    bugs: list[Exception] = []
    for item in settled:
        if isinstance(item, BaseException) and not isinstance(item, Exception):
            raise item
        if isinstance(item, Exception):
            bugs.append(item)
    raise_lone_or_group(bugs, "impl errors during dispatch")
    return [item for item in settled if isinstance(item, Result)]


@dataclass(frozen=True, slots=True)
class MountListing:
    """What the listing verbs show at the mount points of one :term:`kernel`.

    A mount point names two entries. One is the directory stored in the storage above, and the other
    is the root of the storage mounted there. A listing shows the second and never the first, as a
    directory read does on Plan 9 and as ``ls -l`` does on Linux. The mounted storage decides how much
    of the row a caller sees, and it never hides the name. A directory that lies above a mount point
    shows in every listing that succeeds, at least as a bare row, so a caller can walk to the mount.

    A listing is built from one copy of the kernel's table, and every step of one call reads that
    copy. A mount added or removed while a call waits on a storage changes the calls after it and
    never the call in flight. :meth:`holder` and :meth:`beneath` say where a path lives, for every
    verb of the kernel. ``mounts`` is that copy. The rest is worked out once from it, when the
    table changes. ``above`` is every directory that lies above a mount point, the root among them.
    ``held`` gives, for each mount, the directories above a mount point that it stores, by their
    path inside the mount. ``inside`` gives the mount points in each directory, and ``roads`` the
    bare rows of the directories in it that lead to a mount point. ``points`` is the bare row of
    every mount point and of every directory above one, apart from the root. A ``glob`` judges them.
    Each of these lists is in path order, so no answer depends on the order of a set or on the
    order the mounts were added in. ``ordered`` is every mount path in path order, which
    :meth:`beneath` searches, and ``rank`` gives each mount path its place in the table. ``deepest``
    is the number of segments in the deepest mount path, so a walk up a path can start there.
    """

    mounts: Mapping[Path, Mount]
    above: frozenset[Path] = field(init=False)
    held: Mapping[Path, Mapping[Path, Path]] = field(init=False)
    inside: Mapping[Path, tuple[Mount, ...]] = field(init=False)
    roads: Mapping[Path, tuple[Observation, ...]] = field(init=False)
    points: tuple[Observation, ...] = field(init=False)
    ordered: tuple[Path, ...] = field(init=False)
    rank: Mapping[Path, int] = field(init=False)
    deepest: int = field(init=False)

    def __post_init__(self) -> None:
        table = dict(self.mounts)
        object.__setattr__(self, "ordered", tuple(sorted(table)))
        object.__setattr__(self, "rank", {path: index for index, path in enumerate(table)})
        object.__setattr__(self, "deepest", max((path.count("/") for path in table if path != ROOT), default=0))
        above: set[Path] = set()
        for path in table:
            node = path
            while node != ROOT and (node := node.parent_dir) not in above:
                above.add(node)
        object.__setattr__(self, "mounts", table)
        object.__setattr__(self, "above", frozenset(above))
        held: dict[Path, dict[Path, Path]] = {}
        inside: dict[Path, list[Mount]] = {}
        roads: dict[Path, list[Observation]] = {}
        for full in sorted(above):
            owner = self._owner(full)
            held.setdefault(owner, {})[full.without_mount(owner)] = full
            if full not in table:
                roads.setdefault(full.parent_dir, []).append(bare_directory(full))
        for path in sorted(table):
            if path != ROOT:
                inside.setdefault(path.parent_dir, []).append(table[path])
        points = tuple(bare_directory(path) for path in sorted({*table, *above} - {ROOT}))
        object.__setattr__(self, "held", held)
        object.__setattr__(self, "inside", {path: tuple(found) for path, found in inside.items()})
        object.__setattr__(self, "roads", {path: tuple(found) for path, found in roads.items()})
        object.__setattr__(self, "points", points)

    def holder(self, path: Path) -> Mount | None:
        """Return the :term:`mount` that holds ``path``, the deepest one at or above it, or ``None`` for an empty table.

        The call cuts the path at each ``/`` and looks each prefix up in the table as plain text. A
        prefix of a checked path is never checked again, so the call costs the depth of the path and
        never the number of mounts. A table that holds only the root answers at once.
        """
        return self.mounts.get(self._owner(path))

    def governing(self, path: Path) -> tuple[Mount, ...]:
        """Return the mounts at or above ``path``, the root's first, or none for an empty table.

        The call costs at most the depth of the deepest mount path in table lookups, and never the
        number of mounts. A table that holds only the root answers at once.
        """
        root = self.mounts.get(ROOT)
        if not self.above:
            return () if root is None else (root,)
        found: list[Mount] = []
        # A prefix deeper than every mount path names no mount, so the walk starts at that depth.
        parts = path.split("/", self.deepest + 1)
        node: str = "/".join(parts[: self.deepest + 1]) if len(parts) > self.deepest + 1 else path
        while node != ROOT:
            if (mount := self.mounts.get(node)) is not None:
                found.append(mount)
            node = _parent(node)
        if root is not None:
            found.append(root)
        return tuple(reversed(found))

    def beneath(self, path: Path) -> list[Mount]:
        """Return the mounts that lie strictly beneath ``path``, in table order.

        The call costs the log of the number of mounts and the mounts it returns, and never a visit
        to each mount. This says where calls are sent, and not what a caller may see.
        """
        if path == ROOT:
            return [mount for key, mount in self.mounts.items() if key != ROOT]
        # "0" is the character after "/", so the run of paths beneath ends before the first that starts with it.
        start = bisect.bisect_left(self.ordered, path + "/")
        keys = self.ordered[start : bisect.bisect_left(self.ordered, path + "0", start)]
        return [self.mounts[key] for key in sorted(keys, key=self.rank.__getitem__)]

    async def called(
        self, ask: AskStorage, mount: Mount, op: Op, *, authority: Authority | None = None, **kwargs: Any
    ) -> Result:
        """Call ``op`` on the storage of ``mount``, and return its result with the kernel's own paths.

        The rows that lie beneath a deeper mount are dropped. They belong to that mount's storage
        whatever the storage above holds there, and they can be left by a crash or written by another
        client of a shared storage. For ``glob``, the row at a deeper mount's own path is dropped too,
        because it is the stored directory beneath the mount. A deleted row at that path is kept, as
        a trash view lists it.
        """
        result = self._without_hidden(
            (await ask(mount, op, authority=authority, **kwargs)).with_mount(mount.path), mount
        )
        return self._uncovered(result, mount) if op == "glob" else result

    async def listed(
        self,
        ask: AskStorage,
        mount: Mount,
        op: Literal["ls", "stat", "tree"],
        *,
        path: Path | None = None,
        observations: Sequence[Observation] | None = None,
        max_depth: int | None = None,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """Answer ``ls``, ``stat`` or ``tree`` for one path or one batch that ``mount`` holds.

        :meth:`tree` answers ``tree``. For the other two, a target that is not a directory above a
        mount point is answered by the storage alone. A call with no such target is one storage call,
        as it is with no mounts. ``stat`` is one storage call for the whole batch. A directory above a
        mount point is there, so a bare row stands in for a ``not_found`` of it and for nothing else.
        Each target is judged on its own errors, as :func:`_with_roads` says. ``ls`` answers each such
        directory on its own, once however often the batch names it. Its rows come after the rows of
        the other targets, once for each time the batch names it, and its errors are kept once. One
        path is answered with the storage's own envelope.
        """
        if op == "tree":
            assert path is not None
            return await self.tree(ask, mount, path, max_depth=max_depth, columns=columns, authority=authority)
        held = self.held.get(mount.path, {})
        targets = [path] if path is not None else [row.path for row in observations or ()]
        special = dict.fromkeys(target for target in targets if target in held)
        target: dict[str, Any] = {"path": path} if path is not None else {"observations": observations}
        if op == "stat" or not special:
            answer = await self.called(ask, mount, op, columns=columns, authority=authority, **target)
            roads = [held[rel] for rel in targets if rel in special]
            return _with_roads(answer, roads, mount.path, len(set(targets)) == 1) if roads else answer
        if path is not None:
            return await self._directory(ask, mount, path, held[path], columns, authority)
        plain = [row for row in observations or () if row.path not in special]
        calls: list[Coroutine[Any, Any, Result]] = [
            self._directory(ask, mount, rel, held[rel], columns, authority) for rel in special
        ]
        if plain:
            calls.append(self.called(ask, mount, op, observations=plain, columns=columns, authority=authority))
        answers = await gather_settled(calls)
        answered = dict(zip(special, answers, strict=False))
        rest = answers[len(special) :]
        rows = [row for answer in rest for row in answer.observations]
        rows += [row for target in targets if target in answered for row in answered[target].observations]
        errors = [error for answer in (*rest, *answered.values()) for error in answer.errors]
        return Result(ops=(op,), observations=rows, errors=errors)

    async def tree(
        self,
        ask: AskStorage,
        mount: Mount,
        rel: Path,
        *,
        max_depth: int | None,
        columns: frozenset[str] | None,
        authority: Authority | None,
    ) -> Result:
        """List the subtree at ``rel`` of ``mount``, and of every mount beneath it that the depth reaches.

        Each mount that lies within ``max_depth`` shows its row, and so does every directory between
        it and the target. A mount with depth left beneath it is asked for its own subtree, and one
        that cannot answer ``tree`` is skipped with a record of severity ``info``. All of them are
        asked at the same time as the target. If the target is refused, the refusal is returned and the
        other answers are dropped. Its rows are kept, apart from the directory beneath a mount, which
        no answer ever shows. A mount that fails while others answer becomes a warning, and the
        failure of its ``stat`` is then not reported as well. A failure that names no path is set at
        the mount's path. A directory between a mount and the target is listed among the rows of the
        mount that stores it. Each answer is judged as the target's is before any directory it holds
        is added, so a mount that failed adds no directory and no mount point beneath it.
        """
        full = rel.with_mount(mount.path)
        reached: list[tuple[Mount, int | None]] = []
        for deeper in self.beneath(full):
            left = None if max_depth is None else max_depth - deeper.path.without_mount(full).depth
            if left is None or left >= 0:
                reached.append((deeper, left))
        entered = [(deeper, left) for deeper, left in reached if left is None or left > 0]
        asked = [(deeper, left) for deeper, left in entered if "tree" in deeper.caps]
        own, heads, *trees = await gather_settled(
            [
                self.called(ask, mount, "tree", path=rel, max_depth=max_depth, columns=columns, authority=authority),
                self._heads(ask, [deeper for deeper, _left in reached], columns, authority),
                *(
                    self.called(ask, deeper, "tree", path=ROOT, max_depth=left, columns=columns, authority=authority)
                    for deeper, left in asked
                ),
            ]
        )
        if not own.success:
            kept = _recovered(own) if full in self.above else None
            if kept is None:
                return self._uncovered(own, mount)
            own = kept
        answers = {mount.path: own}
        for (deeper, _left), answer in zip(asked, trees, strict=True):
            kept = _recovered(answer) if deeper.path in self.above and not answer.success else None
            answers[deeper.path] = _at_mount(answer, deeper) if kept is None else kept
        failed = {path for path, answer in answers.items() if not answer.success}
        hidden = {deeper.path for deeper, _left in reached if self._owner(_parent(deeper.path)) in failed}
        head = {row.path: [row] for row in heads.observations if row.path not in hidden}
        roads: dict[Path, list[Observation]] = {}
        between = {above for deeper, _left in reached for above in _between(deeper.path, full)} - self.mounts.keys()
        for node in sorted(between):
            if (owner := self._owner(node)) not in failed:
                roads.setdefault(owner, []).append(bare_directory(node))
        records = [
            record
            for record in heads.errors
            if record.source is None or self._owner(record.source) not in failed | hidden
        ]
        branches = [Result(errors=records)]
        for owner in (mount, *(deeper for deeper, _left in reached)):
            answer = self._uncovered(answers.get(owner.path, Result(ops=("tree",))), owner)
            rows = [*head.get(owner.path, ()), *_in_path_order(answer.observations, roads.get(owner.path, ()))]
            branches.append(answer.model_copy(update={"observations": rows}))
        merged = Result.merge_branches(branches, op="tree")
        skips = [skip_record("tree", deeper) for deeper, _left in entered if "tree" not in deeper.caps]
        return merged.model_copy(update={"errors": [*merged.errors, *skips]}) if skips else merged

    async def matched(self, roots: tuple[Path, ...], filters: PathFilters, kind: str | None) -> Result:
        """Return the mount points, and the directories above them, that a ``glob`` matches.

        The storage above a mount point holds a directory that is never shown, and the mounted
        storage does not list its own root. A directory above a mount point is returned by its
        storage only to a caller who may see it. So each such path is judged here, by the rule a
        storage applies to a row of its own. A path is kept when it lies beneath a root and an arm
        matches it, and it is dropped when an exclusion, an extension filter or ``kind`` rules it out.

        The rows come bare and in path order, and no storage is asked. No path is judged when none
        lies beneath a root. :meth:`shown` gives a mount point that is kept the row of its mounted
        root. A directory above one stays bare, and the merge fills it in when its own storage
        returned the row too.
        """
        if not self.points or kind not in (None, "directory"):
            return Result()
        arms, exclusions, ext, ext_not = filters
        whole, named = not roots or ROOT in roots, set(roots)
        points = list(self.points) if whole else [row for row in self.points if self._beneath(row.path, named)]
        if not points:
            return Result()
        beneath = tuple(root for root in roots if root != ROOT)
        scope = ScopeChannel(roots=beneath, arms=arms, arms_not=exclusions) if beneath else None
        gates = compile_gates(arms if whole else (), exclusions if whole else (), ext=ext, ext_not=ext_not, scope=scope)
        kept, completed = await judge_in_hand(gates, points, Deadline.after(WALL_TIME_BUDGET))
        return Result(observations=kept, errors=[] if completed else [wall_truncation(_POINTS_REFINE_GUIDANCE)])

    async def shown(
        self,
        ask: AskStorage,
        roots: tuple[Path, ...],
        columns: frozenset[str] | None,
        max_count: int | None,
        authority: Authority | None,
        named: list[Result],
        branches: list[tuple[Path, Result]],
    ) -> list[Result]:
        """Return ``named`` without the paths of :meth:`matched` whose own directory a storage refused to list.

        ``named`` holds the answers of the root probes of one ``glob``, in the order of
        :meth:`probed`, and last the answer of :meth:`matched`. ``branches`` holds the answer of
        each mount that the ``glob`` asked, by its path. A name shows only in a listing of its parent
        that succeeds. A failure says that one region of one mount could not be listed, and only the
        paths that mount holds in that region are left out. The paths that are kept, or the first
        ``max_count`` of them, are then given the rows of their mounted roots, so no mounted root is
        asked for a path the caller does not get.

        A path is held by the deepest mount strictly above it. A failure of a mount's ``glob`` is the
        region at the path it was raised for, which is ``data["vfs.target"]`` or its own path, and
        that path is in it. A failure of a probe is the region strictly beneath the root it was
        raised for, and the root's own row is kept. A failure that cannot be tied to a path, or a
        probe failure that names none of the roots it probed, is the whole mount. A warning removes
        nothing. A mount that was not asked refused nothing, and the paths it holds are kept. A
        mount whose own ``glob`` failed is reported once, by that failure, and the records of its
        ``stat`` are left out.
        """
        *probes, found = named
        regions: dict[Path, set[Path | None]] = {}
        tops: dict[Path, set[Path | None]] = {}
        for (key, (_mount, rels)), probe in zip(self.probed(roots)[0].items(), probes, strict=True):
            asked = {rel.with_mount(key) for rel in rels}
            for failure in probe.failures:
                target = _target(failure)
                regions.setdefault(key, set()).add(target if target in asked else None)
        for key, answer in branches:
            failed = {_target(failure) for failure in answer.failures}
            regions.setdefault(key, set()).update(failed)
            tops.setdefault(key, set()).update(failed)
        kept = [row for row in found.observations if not self._barred(row.path, regions, tops)]
        capped = found.model_copy(update={"observations": kept if max_count is None else kept[:max_count]})
        found = await self._headed(ask, capped, columns, authority)
        gone = {key for key, answer in branches if not answer.success}
        records = [record for record in found.errors if record.source is None or self._owner(record.source) not in gone]
        return [*probes, found.model_copy(update={"errors": records})]

    async def located(self, ask: AskStorage, mount: Mount, rel: Path, row: Location, authority: Authority) -> Location:
        """Return ``row``, which ``locate`` built for ``rel`` in ``mount``, with what the storage says of it.

        The storage is asked to ``stat`` the path directly, past the gate, as ``authority``, and its
        answer is read with the kernel's own paths. A directory that lies above a mount point is
        there, so it exists and is a directory. A refusal of any other kind than ``not_found`` is
        reported in ``note``, for that directory as for any path, by the test ``stat`` applies.
        """
        full = rel.with_mount(mount.path)
        stat = await self.called(ask, mount, "stat", path=rel, authority=authority)
        if full in self.above:
            stat = _with_roads(stat, [full], mount.path, True)
        refusal = _refusal(stat)
        if refusal is not None:
            return row._replace(note=refusal.message or f"could not stat {row.path}")
        found = next((o for o in stat.observations if o.path == full), None)
        return row._replace(exists=False) if found is None else row._replace(exists=True, kind=found.kind)

    async def _headed(
        self, ask: AskStorage, found: Result, columns: frozenset[str] | None, authority: Authority | None
    ) -> Result:
        """Return ``found`` with the row at each mount point in it taken from the mounted root, by :meth:`_heads`."""
        mounted = [self.mounts[row.path] for row in found.observations if row.path in self.mounts]
        heads = await self._heads(ask, mounted, columns, authority)
        head = {row.path: row for row in heads.observations}
        rows = [head.get(row.path, row) for row in found.observations]
        return found.model_copy(update={"observations": rows, "errors": [*heads.errors, *found.errors]})

    def probed(self, roots: tuple[Path, ...]) -> tuple[dict[Path, tuple[Mount, list[Path]]], list[ResultError]]:
        """Group the roots a caller named by the :term:`mount` that holds each, for the probe of a search.

        The call returns, for each mount in the order its first root came, the mount and its roots
        as its storage sees them. It returns a warning for each root that cannot be checked. The root
        of the file tree is left out, because it is the tree itself and never a row. A mount that
        cannot answer ``stat`` cannot say whether its roots are there, so each such root gets a
        warning. It is never treated as absent, and it never passes in silence.
        """
        grouped: dict[Path, tuple[Mount, list[Path]]] = {}
        unverifiable: list[ResultError] = []
        detail = "the root is unverifiable: the storage mounted here does not support stat"
        for root in roots:
            if root == ROOT:
                continue
            mount = self.mounts[self._owner(root)]
            if "stat" not in mount.caps:
                warning = classified(
                    ErrorKind.unsupported, root, severity=Severity.warning, source=mount.path, detail=detail
                )
                unverifiable.append(warning)
                continue
            grouped.setdefault(mount.path, (mount, []))[1].append(root.without_mount(mount.path))
        return grouped, unverifiable

    async def _heads(
        self,
        ask: AskStorage,
        mounts: Sequence[Mount],
        columns: frozenset[str] | None,
        authority: Authority | None,
    ) -> Result:
        """Return the row a listing shows at the mount point of each of ``mounts``, with the records of its ``stat``.

        The row is what ``stat`` of the mounted root returns to the caller. A mount that cannot
        answer ``stat`` is not asked. Each of the others costs one storage call, and all are asked
        at the same time. A mount shows bare when it gives no row that is a directory. That is a
        mount that refuses the caller, one that cannot answer ``stat``, one that fails, and one whose
        root is not a directory. A row that comes with a failure is not trusted, so a mount that
        fails shows bare even when it gave a row. A refusal adds no record. Any other failure adds a
        record of severity ``warning``, at the mount's path when the failure names none. The
        storage's own records on a ``stat`` that succeeds are kept. The ``source`` of each record
        names the mount.
        """
        asked = [mount for mount in mounts if "stat" in mount.caps]
        stats = await gather_settled(
            self.called(ask, mount, "stat", path=ROOT, columns=columns, authority=authority) for mount in asked
        )
        answers = {mount.path: answer for mount, answer in zip(asked, stats, strict=True)}
        rows: list[Observation] = []
        records: list[ResultError] = []
        for mount in mounts:
            answer = answers.get(mount.path, Result())
            row = next((found for found in answer.observations if found.path == mount.path), None)
            trusted = row is not None and row.kind == "directory" and answer.success
            rows.append(row if row is not None and trusted else bare_directory(mount.path))
            records += answer.errors if answer.success else []
            records += [
                failure.model_copy(update={"severity": Severity.warning, "path": failure.path or mount.path})
                for failure in answer.failures
                if kind_family(failure.kind) not in _DENIALS
            ]
        return Result(observations=rows, errors=records)

    async def _directory(
        self,
        ask: AskStorage,
        mount: Mount,
        rel: Path,
        full: Path,
        columns: frozenset[str] | None,
        authority: Authority | None,
    ) -> Result:
        """Answer ``ls`` of one directory that lies above a mount point.

        The directory is there because a mount lies beneath it. So a ``not_found`` only says the
        caller holds nothing on it, and the listing shows what the mount table knows, beside the
        storage's other rows and records. Any other refusal stands. The answer is then returned with
        its rows and records, less the directory beneath each mount. Otherwise the listing adds the
        row of each mount point in the directory, and a bare row for each directory in it that leads
        to a mount, in path order among the storage's own rows. The answer keeps the storage's own
        envelope.
        """
        own, heads = await gather_settled(
            [
                self.called(ask, mount, "ls", path=rel, columns=columns, authority=authority),
                self._heads(ask, self.inside.get(full, ()), columns, authority),
            ]
        )
        own = self._uncovered(own, mount)
        kept = _recovered(own)
        if kept is None:
            return own
        rows = _in_path_order(kept.observations, [*heads.observations, *self.roads.get(full, ())])
        return kept.model_copy(update={"observations": rows, "errors": [*kept.errors, *heads.errors]})

    def _without_hidden(self, result: Result, mount: Mount) -> Result:
        """Return ``result``, which ``mount`` gave, without the rows that lie beneath a deeper mount.

        Each row costs a walk up its own path, so the cost grows with the depth of the path and not
        with the number of mounts.
        """
        if mount.path not in self.above or not result.observations:
            return result
        kept = [
            row
            for row in result.observations
            if row.path == mount.path or self._owner(_parent(row.path), mount.path) == mount.path
        ]
        return result if len(kept) == len(result.observations) else result.model_copy(update={"observations": kept})

    def _uncovered(self, result: Result, mount: Mount) -> Result:
        """Return ``result``, which ``mount`` gave, without the stored directory at a deeper mount's path.

        That directory is covered by the mount. A deleted row at the same path is kept.
        """
        if mount.path not in self.above or not result.observations:
            return result
        kept = [
            row
            for row in result.observations
            if row.path == mount.path or row.path not in self.mounts or row.deleted_at is not None
        ]
        return result if len(kept) == len(result.observations) else result.model_copy(update={"observations": kept})

    def _owner(self, path: str, stop: Path = ROOT) -> Path:
        """Return the deepest mount at or above ``path``, looking no higher than ``stop``.

        Each prefix is looked up as plain text and never checked again, and a table with no mount
        but the root answers at once.
        """
        if not self.above:
            return ROOT
        node = path
        while node not in (stop, ROOT) and node not in self.mounts:
            node = _parent(node)
        mount = self.mounts.get(node)
        return stop if mount is None else mount.path

    def _barred(
        self, path: Path, regions: Mapping[Path, set[Path | None]], tops: Mapping[Path, set[Path | None]]
    ) -> bool:
        """Return whether ``path`` lies in a region that the mount holding it failed to list.

        A region holds what lies strictly beneath its path, and a region in ``tops`` holds its path
        too. ``None`` stands for the whole mount. The test walks up the path, so it costs the depth
        of the path and never the number of failures.
        """
        key = self._owner(_parent(path))
        region = regions.get(key)
        if not region:
            return False
        return None in region or path in tops.get(key, ()) or self._beneath(path, region)

    @staticmethod
    def _beneath(path: str, roots: Container[str | None]) -> bool:
        """Return whether ``path`` lies strictly beneath one of ``roots``. No prefix is checked again."""
        node = path
        while node != ROOT:
            node = _parent(node)
            if node in roots:
                return True
        return False


def skip_record(op: Op, mount: Mount) -> ResultError:
    """Return the record that says ``mount`` was skipped because it cannot answer ``op``.

    A search of a region, or a ``tree``, skips such a :term:`mount`. The record has the severity
    ``info`` and is never a failure. The mount's path is both its ``path`` and its ``source``.
    """
    detail = f"skipped: operation {op!r} is not declared by the storage mounted here"
    return classified(ErrorKind.unsupported, mount.path, severity=Severity.info, source=mount.path, detail=detail)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _between(path: Path, directory: Path) -> list[Path]:
    """Return the directories that lie strictly between ``directory`` and ``path``, which lies beneath it."""
    found: list[Path] = []
    node = path.parent_dir
    while node != directory:
        found.append(node)
        node = node.parent_dir
    return found


def _refuses(error: ResultError) -> bool:
    """Return whether ``error`` is a failure that is not a ``not_found``.

    Such a failure says the storage refused the caller or could not answer, so it stands. A
    ``not_found`` says only that a path is missing. For a directory that lies above a mount point,
    which is there by construction, it says only that the caller holds nothing on it.
    """
    return error.is_fatal and kind_family(error.kind) is not ErrorKind.not_found


def _refusal(answer: Result) -> ResultError | None:
    """Return the first error of ``answer`` that :func:`_refuses` finds, or ``None`` when there is none."""
    return next((error for error in answer.errors if _refuses(error)), None)


def _recovered(answer: Result) -> Result | None:
    """Return the answer for one directory above a mount point without its misses, or ``None`` when it was refused.

    It is refused when :func:`_refusal` finds a failure. Otherwise every failure is a ``not_found``,
    and each is dropped. The answer keeps its rows and its other records.
    """
    if _refusal(answer) is not None:
        return None
    return answer.model_copy(update={"errors": [error for error in answer.errors if not error.is_fatal]})


def _with_roads(answer: Result, roads: Sequence[Path], root: Path, alone: bool) -> Result:
    """Return a ``stat`` answer with a bare row in place of each miss of one of ``roads``.

    Each of ``roads`` lies above a mount point, so it is there, and each target is judged on its own
    errors. A failure is raised for ``data["vfs.target"]`` when the storage set it, and for its own
    path when not. When the call has one target, ``alone`` is true and every failure is raised for
    it, so one path and a batch of that path give the same answer. A failure at no path, or at the
    storage's own ``root`` with no target, as a transport failure is, is raised for the whole answer.
    A failure that is not a ``not_found`` withholds the bare row of the target it was raised for,
    or of every target when it was raised for the whole answer. A ``not_found`` raised for a road
    that is not withheld is dropped, and the road gets one bare row for each time the call names it
    beyond the rows the storage gave for it. Every other failure stands. A batch costs its length.
    """
    raised = {
        index: roads[0] if alone else _raised_for(error, root)
        for index, error in enumerate(answer.errors)
        if error.is_fatal
    }
    withheld = {target for index, target in raised.items() if _refuses(answer.errors[index])}
    if None in withheld:
        return answer
    named = set(roads) - withheld
    errors = [error for index, error in enumerate(answer.errors) if index not in raised or raised[index] not in named]
    short = Counter(road for road in roads if road in named)
    short.subtract(row.path for row in answer.observations)
    rows = list(answer.observations)
    for road in roads:
        if short[road] > 0:
            short[road] -= 1
            rows.append(bare_directory(road))
    return answer.model_copy(update={"observations": rows, "errors": errors})


def _at_mount(answer: Result, mount: Mount) -> Result:
    """Return ``answer``, which ``mount`` gave, with each failure that names no path set at the mount's path."""
    if all(failure.path is not None for failure in answer.failures):
        return answer
    errors = [
        error.model_copy(update={"path": mount.path}) if error.is_fatal and error.path is None else error
        for error in answer.errors
    ]
    return answer.model_copy(update={"errors": errors})


def _parent(path: str) -> str:
    """Return the directory that holds ``path``, as plain text. The root is its own parent."""
    return path[: path.rfind("/")] or ROOT


def _raised_for(error: ResultError, root: Path) -> Path | None:
    """Return the target of a batch that ``error`` was raised for, or ``None`` when it can name none.

    That is :func:`_target`, unless the storage set no target and the error names no path or its
    own ``root``. Such an error is a failure of the whole answer.
    """
    target = _target(error)
    return None if target == root and "vfs.target" not in (error.data or {}) else target


def _target(error: ResultError) -> Path | None:
    """Return the path ``error`` was raised for, which is ``data["vfs.target"]`` when set and its own path when not."""
    target = (error.data or {}).get("vfs.target")
    return error.path if target is None else Path(target)


def _in_path_order(rows: Sequence[Observation], extras: Iterable[Observation]) -> list[Observation]:
    """Return ``rows`` with each of ``extras`` whose path is not among them put in at its place in path order.

    The rows keep the order their storage gave them, whatever that order is.
    """
    have = {row.path for row in rows}
    fresh = sorted((extra for extra in extras if extra.path not in have), key=lambda row: row.path)
    return list(heapq.merge(rows, fresh, key=lambda row: row.path)) if fresh else list(rows)
