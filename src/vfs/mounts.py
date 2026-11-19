"""A :term:`mount` is one storage backend attached at one path. This module holds the mount and where a path lives.

The file system keeps one :class:`Mount` for each path that a storage is attached at, the root included.
``mounts()`` hands the same objects back. The checks a mount change passes before the kernel's table
changes are here too.

```python
for mount in fs.mounts():
    print(mount.path, sorted(mount.caps))
    json.dumps(mount.to_payload())
```
"""

from __future__ import annotations

import asyncio
import heapq
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple, Protocol, TypedDict

from vfs.chain import judge_in_hand
from vfs.deadline import WALL_TIME_BUDGET, Deadline
from vfs.exceptions import raise_lone_or_group
from vfs.models import Observation
from vfs.offload import wall_truncation
from vfs.ops import GRANT_OPS, READ_OPS
from vfs.paths import METADATA_ROOT, ROOT, Path
from vfs.pattern_matching import ScopeChannel, compile_gates
from vfs.results import ErrorKind, Result, ResultError, classified
from vfs.results.kinds import TRASHED_KEY, Severity, kind_family
from vfs.storage import HOLDS, StorageBackend, SupportsHolds, TransportError

if TYPE_CHECKING:
    from collections.abc import Coroutine, Iterable, Mapping, Sequence

    from vfs.authority import Authority
    from vfs.ops import Op
    from vfs.permissions import PermissionMap, PermissionsPayload

# ---------------------------------------------------------------------------
# The mount and its payload
# ---------------------------------------------------------------------------


class MountPayload(TypedDict):
    """The JSON form of a :class:`Mount`, which is what :meth:`Mount.to_payload` returns.

    Every value is a string, a boolean, ``None``, or a list or dict of these, so the payload comes back
    unchanged from ``json.dumps`` and ``json.loads``. The storage is named and never carried.
    ``storage_name``, ``storage_type`` and ``description`` stand in for the live object. ``caps`` and
    ``deny_ops`` are sorted lists. ``permissions`` is the payload of the mount's own permission map, or
    ``None`` when the mount has no rules of its own.
    """

    path: str
    storage_name: str
    storage_type: str
    description: str
    caps: list[str]
    deny_ops: list[str]
    permissions: PermissionsPayload | None
    no_overlay: bool
    owned: bool


@dataclass(frozen=True, slots=True)
class Mount:
    """One :term:`mount`, a storage backend attached at a path with the policy its mounter set.

    Every path belongs to exactly one mount, the deepest one at or above it. The file system's own
    storage at ``/`` is an ordinary mount, and it answers when no deeper mount matches.

    Policy lives on the mount and state lives on the storage.

    - ``permissions`` holds rules written relative to the mount. ``None`` means it has no rules of its own.
    - ``deny_ops`` is the set of operations the mounter masked.
    - ``no_overlay`` refuses new mounts beneath this one. The mounts already there keep working, so a
      sealed subtree can lose mounts and never gain one.
    - ``owned`` says that ``close()`` disposes the storage.
    - ``declared_caps`` is what ``storage.capabilities()`` returned when the mount was added, before the
      mask.
    - ``caps`` is what the gate reads. It is computed once, when the mount is built, as
      ``declared_caps - deny_ops``.

    A mount is frozen and is always replaced whole, so ``caps`` cannot drift from the two it is computed
    from.

    A mount holds the live storage object, so it is not JSON-native. :meth:`to_payload` gives the form that is.
    """

    path: Path
    storage: StorageBackend
    permissions: PermissionMap | None = None
    deny_ops: frozenset[str] = frozenset()
    no_overlay: bool = False
    owned: bool = True
    declared_caps: frozenset[str] = frozenset()
    caps: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "caps", self.declared_caps - self.deny_ops)

    def to_payload(self) -> MountPayload:
        """Return this mount as a :class:`MountPayload`, with the storage named in place of the object.

        The storage's ``name`` and ``description`` are read, and both are attributes and not calls.
        No storage I/O runs.
        """
        return MountPayload(
            path=str(self.path),
            storage_name=self.storage.name,
            storage_type=type(self.storage).__name__,
            description=self.storage.description,
            caps=sorted(self.caps),
            deny_ops=sorted(self.deny_ops),
            permissions=None if self.permissions is None else self.permissions.to_payload(),
            no_overlay=self.no_overlay,
            owned=self.owned,
        )


# ---------------------------------------------------------------------------
# The checks a mount change passes
# ---------------------------------------------------------------------------


def require_storage(storage: object) -> None:
    """Raise ``TypeError`` unless ``storage`` can be mounted, which needs the read verbs and a name."""
    if not isinstance(storage, StorageBackend):
        msg = f"storage must implement the read family (see vfs.storage), got {type(storage).__name__}"
        raise TypeError(msg)


def normalize_mount_path(path: str, *, allow_root: bool = False) -> Path:
    """Return ``path`` as a checked :class:`Path` that may hold a :term:`mount`.

    :class:`Path` does the general work. It makes the path absolute, drops ``.`` and ``..``, strips the
    white space around each segment, and refuses control characters and segments that are too long.
    Spaces inside a segment are kept, as in ``"/My Documents"``. A mount path has two more rules. It is
    never the root unless ``allow_root`` is true, which ``update_mount`` passes because the root is an
    ordinary mount. It never uses the reserved segment ``.vfs``. The call raises ``ValueError`` for a
    path that breaks a rule.
    """
    mount_path = Path(path)
    if mount_path == ROOT and not allow_root:
        msg = "Mount path must not be empty or root"
        raise ValueError(msg)
    meta_segment = METADATA_ROOT.strip("/")
    if meta_segment in mount_path.split("/")[1:]:
        msg = f"Mount path may not use the reserved metadata segment {meta_segment!r}: {path!r}"
        raise ValueError(msg)
    return mount_path


def validate_deny_ops(deny_ops: Iterable[Op]) -> frozenset[Op]:
    """Return ``deny_ops`` as a frozen set, after checking that it masks no read operation.

    A mask applies to every caller alike. Refusing a read is the job of the storage's rights, which
    know who the caller is. Only the known read operations are refused here, so a name the kernel does
    not know can still be masked. The call raises ``ValueError`` that names the read operations. It
    raises ``TypeError`` for a bare string, which would be read as a set of letters.
    """
    if isinstance(deny_ops, (str, bytes)):
        msg = f"deny_ops must be an iterable of op names, not a bare string: {deny_ops!r}"
        raise TypeError(msg)
    mask = frozenset(deny_ops)
    blocked = mask & READ_OPS
    if blocked:
        msg = f"deny_ops may not mask read-family ops: {', '.join(sorted(blocked))}"
        raise ValueError(msg)
    return mask


def mount_point_owner(mounts: Mapping[Path, Mount], mount_path: Path) -> Mount:
    """Return the :term:`mount` in ``mounts`` that stores the directory at ``mount_path``.

    That is the deepest mount above the path. The root mount stores its own. No storage is asked.
    """
    return mounts[max((p for p in mounts if p == ROOT or mount_path.startswith(p + "/")), key=len)]


class MountJudgement(NamedTuple):
    """What a check of a caller's rights judged, which must still be so when the :term:`mount` change commits.

    ``owner_path`` and ``owner`` are the path and the storage of the mount that holds the mount point,
    and that storage is the one that judged. A storage detached and attached again at another path
    judges another path there, so the path is kept as well as the storage. ``target`` is the storage
    of the mount at the mount point, or ``None`` when there was none.
    """

    owner_path: Path
    owner: StorageBackend
    target: StorageBackend | None

    @classmethod
    def of(cls, mounts: Mapping[Path, Mount], mount_path: Path) -> MountJudgement:
        """Return what ``mounts`` holds at the mount point ``mount_path`` and above it now. No storage is asked."""
        owner = mount_point_owner(mounts, mount_path)
        target = mounts.get(mount_path)
        return cls(owner.path, owner.storage, None if target is None else target.storage)


def require_judgement_stands(
    judged: MountJudgement | None, change: str, mount_path: Path, mounts: Mapping[Path, Mount]
) -> None:
    """Raise ``ValueError`` that asks for a retry when ``mounts`` no longer holds what was ``judged``.

    The :term:`mount` that holds the mount point must be the same storage at the same path. If a mount
    was at the mount point when the rights were judged, the same storage must be mounted there still.
    ``None`` stands for the system actor, who is not judged. ``change`` is the words the error uses. No
    storage is asked, so the caller holds the mount lock and commits with no await in between.
    """
    if judged is None:
        return
    now = MountJudgement.of(mounts, mount_path)
    moved = now.owner_path != judged.owner_path or now.owner is not judged.owner
    replaced = judged.target is not None and now.target is not judged.target
    if moved or replaced:
        msg = f"Cannot {change} {mount_path}: a mount at or above it changed while rights were checked, so retry"
        raise ValueError(msg)


async def rights_refusal(owner: Mount, mount_path: Path, who: Authority) -> Result | None:
    """Return why ``who`` may not change the :term:`mount` at ``mount_path``, or ``None`` when they may.

    ``owner`` is the mount that stores the mount-point directory. Its storage says, through ``holds``,
    whether ``who`` holds ``read_write`` there. A storage that declares no grant verb keeps no rights
    to go around, so it refuses nobody. A storage that keeps grants and cannot answer refuses with
    ``unsupported``. A storage that cannot be reached refuses with ``backend_unavailable``.
    """
    storage = owner.storage
    if isinstance(storage, SupportsHolds):
        rel = mount_path.without_mount(owner.path)
        try:
            answer = await storage.holds(path=rel, level="read_write", authority=who)
        except TransportError as exc:
            fact = classified(ErrorKind.backend_unavailable, ROOT, detail=f"the transport failed: {exc}")
            answer = Result(ops=(HOLDS,), errors=[fact])
        return None if answer.success else answer.with_mount(owner.path)
    if owner.declared_caps & GRANT_OPS:
        detail = "the storage that holds the mount point keeps grants and cannot say what the caller holds"
        return Result(ops=(HOLDS,), errors=[classified(ErrorKind.unsupported, owner.path, detail=detail)])
    return None


def is_tombstoned_site(result: Result, path: Path) -> bool:
    """Return whether ``result`` was refused because ``path`` itself holds a deleted row.

    That is the one refusal that a ``restore`` can put right.
    """
    error = result.errors[0]
    return error.kind is ErrorKind.not_found and error.path == path and bool((error.data or {}).get(TRASHED_KEY))


# ---------------------------------------------------------------------------
# What a listing shows at a mount point
# ---------------------------------------------------------------------------

# The fields of a bare row, which says only that a directory is there.
BARE_FIELDS: Final[frozenset[str]] = frozenset({"path", "kind"})

# The refusals that say what a caller may see. Any other failure says the storage could not answer.
_DENIALS: Final = frozenset({ErrorKind.not_found, ErrorKind.permission_denied, ErrorKind.unauthenticated})

# What shrinks a ``glob`` that could not judge every mount point in time.
_POINTS_REFINE_GUIDANCE: Final = "narrow the pattern or its exclusions"


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


class AskStorage(Protocol):
    """The kernel's call on the storage of one :term:`mount`, whose result carries the storage's own paths."""

    def __call__(
        self, mount: Mount, op: Op, *, authority: Authority | None = None, **kwargs: Any
    ) -> Coroutine[Any, Any, Result]:
        """Call ``op`` on the storage of ``mount`` and return its result as the storage gave it."""
        ...


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
    always shows, at least as a bare row, so a caller can walk down to the mount.

    A listing is built from one copy of the kernel's table, and every step of one call reads that
    copy. A mount added or removed while a call waits on a storage changes the calls after it and
    never the call in flight. ``mounts`` is that copy. The rest is worked out once from it, when the
    table changes. ``above`` is every directory that lies above a mount point, the root among them.
    ``held`` gives, for each mount, the directories above a mount point that it stores, by their
    path inside the mount. ``inside`` gives the mount points in each directory, and ``roads`` the
    bare rows of the directories in it that lead to a mount point. ``points`` is the bare row of
    every mount point and of every directory above one, apart from the root. A ``glob`` judges them.
    Each of these lists is in path order, so no answer depends on the order of a set or on the
    order the mounts were added in.
    """

    mounts: Mapping[Path, Mount]
    above: frozenset[Path] = field(init=False)
    held: Mapping[Path, Mapping[Path, Path]] = field(init=False)
    inside: Mapping[Path, tuple[Mount, ...]] = field(init=False)
    roads: Mapping[Path, tuple[Observation, ...]] = field(init=False)
    points: tuple[Observation, ...] = field(init=False)

    def __post_init__(self) -> None:
        table = dict(self.mounts)
        above: set[Path] = set()
        for path in table:
            node = path
            while node != ROOT and (node := node.parent_dir) not in above:
                above.add(node)
        object.__setattr__(self, "mounts", table)
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
        object.__setattr__(self, "above", frozenset(above))
        object.__setattr__(self, "held", held)
        object.__setattr__(self, "inside", {path: tuple(found) for path, found in inside.items()})
        object.__setattr__(self, "roads", {path: tuple(found) for path, found in roads.items()})
        object.__setattr__(self, "points", points)

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
        mount point that the storage gives no row for, and refuses with nothing but ``not_found``,
        then gets a bare row. ``ls`` answers each such directory on its own, once however often the
        batch names it. Its rows come after the rows of the other targets, once for each time the
        batch names it, and its errors are kept once. One path is answered with the storage's own
        envelope.
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
            roads = [held[rel] for rel in special]
            return _with_roads(answer, roads, alone=path is not None) if roads else answer
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
        other answers are dropped. A mount that fails while others answer becomes a warning, and the
        failure of its ``stat`` is then not reported as well. A failure that names no path is set at
        the mount's path. A directory between a mount and the
        target is listed among the rows of the mount that stores it.
        """
        full = rel.with_mount(mount.path)
        reached: list[tuple[Mount, int | None]] = []
        for deeper in self.mounts.values():
            if deeper.path != full and _lies_in(deeper.path, full):
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
            kept = _recovered(own, full) if full in self.above else None
            if kept is None:
                return own
            own = kept
        answers = {mount.path: own}
        answers |= {
            deeper.path: _at_mount(answer, deeper) for (deeper, _left), answer in zip(asked, trees, strict=True)
        }
        failed = {path for path, answer in answers.items() if not answer.success}
        head = {row.path: [row] for row in heads.observations}
        roads: dict[Path, list[Observation]] = {}
        between = {above for deeper, _left in reached for above in _between(deeper.path, full)} - self.mounts.keys()
        for node in sorted(between):
            roads.setdefault(self._owner(node), []).append(bare_directory(node))
        records = [
            record for record in heads.errors if record.source is None or self._owner(record.source) not in failed
        ]
        branches = [Result(errors=records)]
        for owner in (mount, *(deeper for deeper, _left in reached)):
            answer = self._uncovered(answers.get(owner.path, Result(ops=("tree",))), owner)
            rows = [*head.get(owner.path, ()), *_in_path_order(answer.observations, roads.get(owner.path, ()))]
            branches.append(answer.model_copy(update={"observations": rows}))
        merged = Result.merge_branches(branches, op="tree")
        skips = [skip_record("tree", deeper) for deeper, _left in entered if "tree" not in deeper.caps]
        return merged.model_copy(update={"errors": [*merged.errors, *skips]}) if skips else merged

    async def matched(
        self,
        ask: AskStorage,
        roots: tuple[Path, ...],
        filters: PathFilters,
        kind: str | None,
        columns: frozenset[str] | None,
        max_count: int | None,
        *,
        authority: Authority | None,
    ) -> Result:
        """Return the mount points, and the directories above them, that a ``glob`` matches.

        The storage above a mount point holds a directory that is never shown, and the mounted
        storage does not list its own root. A directory above a mount point is returned by its
        storage only to a caller who may see it. So each such path is judged here, by the rule a
        storage applies to a row of its own. A path is kept when it lies beneath a root and an arm
        matches it, and it is dropped when an exclusion, an extension filter or ``kind`` rules it out.
        A mount point that is kept shows the root of its storage. A directory above one shows bare,
        and the merge fills it in when its own storage returned the row too.

        The rows come in path order. No path is judged when none lies beneath a root. With
        ``max_count``, only the first ``max_count`` paths are kept, and only their mounted roots are
        asked. :meth:`shown` then leaves out the paths whose own directory a storage refused to list.
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
        kept = kept[:max_count]
        heads = await self._heads(
            ask, [self.mounts[row.path] for row in kept if row.path in self.mounts], columns, authority
        )
        head = {row.path: row for row in heads.observations}
        rows = [head.get(row.path, row) for row in kept]
        records = [] if completed else [wall_truncation(_POINTS_REFINE_GUIDANCE)]
        return Result(observations=rows, errors=[*heads.errors, *records])

    def shown(self, roots: tuple[Path, ...], named: list[Result], branches: list[tuple[Path, Result]]) -> list[Result]:
        """Return ``named`` without the paths of :meth:`matched` whose own directory a storage refused to list.

        ``named`` holds the answers of the root probes of one ``glob``, and last the answer of
        :meth:`matched`. ``branches`` holds the answer of each mount that the ``glob`` asked, by its
        path. A name shows only in a listing of its parent that succeeds. So a path is left out, with
        the records of its ``stat``, when the mount that stores its directory failed this ``glob``.
        That mount is the deepest one strictly above the path. A path is left out too when it lies
        beneath one of ``roots`` whose probe failed. A mount that was not asked refused nothing, and
        the paths it stores are kept. A mount whose own ``glob`` failed is reported once, by that
        failure, and the records of its ``stat`` are left out.
        """
        *probes, found = named
        refused = {path for path, answer in branches if not answer.success}
        failures = [failure for probe in probes for failure in probe.failures]
        barred = {root for root in roots for failure in failures if _names(failure, root)}
        hidden = {
            row.path
            for row in found.observations
            if self._owner(row.path.parent_dir) in refused or self._beneath(row.path, barred)
        }
        gone = hidden | refused
        rows = [row for row in found.observations if row.path not in hidden]
        records = [record for record in found.errors if record.source is None or self._owner(record.source) not in gone]
        if len(rows) == len(found.observations) and len(records) == len(found.errors):
            return named
        return [*probes, found.model_copy(update={"observations": rows, "errors": records})]

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
        root is not a directory. A refusal adds no record. Any other failure adds a record of
        severity ``warning``, at the mount's path when the failure names none. The storage's own
        records on a ``stat`` that succeeds are kept. The ``source`` of each record names the mount.
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
            rows.append(row if row is not None and row.kind == "directory" else bare_directory(mount.path))
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

        The directory is there because a mount lies beneath it. So a ``not_found`` at its path, or
        at a directory above it, only says the caller holds nothing on it. The listing then shows
        what the mount table knows, beside the storage's other rows and records. Any other refusal
        stands, and so does a ``not_found`` at any other path. The listing adds the row of each mount
        point in the directory, and a bare row for each directory in it that leads to a mount, in
        path order among the storage's own rows. The answer keeps the storage's own envelope.
        """
        own, heads = await gather_settled(
            [
                self.called(ask, mount, "ls", path=rel, columns=columns, authority=authority),
                self._heads(ask, self.inside.get(full, ()), columns, authority),
            ]
        )
        kept = _recovered(own, full)
        if kept is None:
            return own
        kept = self._uncovered(kept, mount)
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
            if row.path == mount.path or self._owner(row.path.parent_dir, mount.path) == mount.path
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

    def _owner(self, path: Path, stop: Path = ROOT) -> Path:
        """Return the deepest mount at or above ``path``, looking no higher than ``stop``."""
        node = path
        while node not in (stop, ROOT) and node not in self.mounts:
            node = node.parent_dir
        return node

    @staticmethod
    def _beneath(path: Path, roots: set[Path]) -> bool:
        """Return whether ``path`` lies strictly beneath one of ``roots``."""
        node = path
        while node != ROOT:
            node = node.parent_dir
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


def _lies_in(path: Path, directory: Path) -> bool:
    """Return whether ``path`` is ``directory`` or lies beneath it."""
    return directory in (path, ROOT) or path.startswith(directory + "/")


def _between(path: Path, directory: Path) -> list[Path]:
    """Return the directories that lie strictly between ``directory`` and ``path``, which lies beneath it."""
    found: list[Path] = []
    node = path.parent_dir
    while node != directory:
        found.append(node)
        node = node.parent_dir
    return found


def _recovered(answer: Result, full: Path) -> Result | None:
    """Return ``answer`` without the misses of ``full``, or ``None`` when another refusal stands.

    ``full`` lies above a mount point, so it is there whatever its storage says. A miss is a
    ``not_found`` at ``full``, at a directory above it, or at no path, and it only says the caller
    holds nothing on ``full``. The answer keeps its rows and its other records.
    """
    failures = answer.failures
    if any(kind_family(f.kind) is not ErrorKind.not_found or not _names(f, full) for f in failures):
        return None
    return answer.model_copy(update={"errors": [error for error in answer.errors if not error.is_fatal]})


def _with_roads(answer: Result, roads: Sequence[Path], *, alone: bool) -> Result:
    """Return the ``stat`` answer ``answer`` with a bare row for each of ``roads`` that it gives no row for.

    Each of ``roads`` lies above a mount point, so it is there. A ``not_found`` at its path, at a
    directory above it, or at no path only says the caller holds nothing on it. A ``not_found``
    names the first part of a path that is missing, so several targets can share one. One such
    error is dropped for each bare row, the one at the road's own path first. Any other refusal at
    those paths stands, and the road then gets no row. If ``alone`` is true, the answer is for one
    road only, and a refusal at any other path stands as well.
    """
    if alone and any(not _names(failure, roads[0]) for failure in answer.failures):
        return answer
    have = {row.path for row in answer.observations}
    rows, errors = list(answer.observations), list(answer.errors)
    for road in roads:
        if road in have:
            continue
        misses = [error for error in errors if error.is_fatal and _names(error, road)]
        if any(kind_family(miss.kind) is not ErrorKind.not_found for miss in misses):
            continue
        if misses:
            errors.remove(min(misses, key=lambda miss: miss.path != road))
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


def _names(error: ResultError, path: Path) -> bool:
    """Return whether ``error`` names ``path``, a directory above it, or no path at all."""
    return error.path is None or _lies_in(path, error.path)


def _in_path_order(rows: Sequence[Observation], extras: Iterable[Observation]) -> list[Observation]:
    """Return ``rows`` with each of ``extras`` whose path is not among them put in at its place in path order.

    The rows keep the order their storage gave them, whatever that order is.
    """
    have = {row.path for row in rows}
    fresh = sorted((extra for extra in extras if extra.path not in have), key=lambda row: row.path)
    return list(heapq.merge(rows, fresh, key=lambda row: row.path)) if fresh else list(rows)


# ---------------------------------------------------------------------------
# Where a path lives
# ---------------------------------------------------------------------------


class Location(NamedTuple):
    """Where a path lives, as ``locate`` reports it. Every field is JSON-native.

    ``mount`` is the path of the :term:`mount` that holds ``path``, the deepest one at or above it.
    ``storage_path`` is the same path as that storage sees it. The last three fields are filled only when
    the storage was asked. ``exists`` and ``kind`` are ``None`` when it was not asked or could not
    answer, and ``note`` then carries its message. Nothing here says whether a verb would accept the path.
    """

    path: str
    mount: str
    storage_name: str
    storage_type: str
    storage_path: str
    exists: bool | None = None
    kind: str | None = None
    note: str | None = None


class EdgeLocation(NamedTuple):
    """Where the two ends of an edge live, as ``locate_edge`` reports it.

    ``same_storage`` is the test ``mkedge`` applies before it dispatches. An edge never crosses from one
    :term:`mount` to another. ``reason`` is a sentence for a person that names the first thing in the
    edge's way, and it is never a classified error. ``None`` means nothing was found in the way.
    """

    source: Location
    target: Location
    same_storage: bool
    reason: str | None
