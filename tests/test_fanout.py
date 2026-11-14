"""The fan-out planner pinned with no router: plain data in, a plan out.

Every node builds its mount-table facts from literal paths and asserts
states and counts: members, scope channels, residuations, clock reads.
"""

from __future__ import annotations

from typing import Any

import pytest

from vfs import deadline as deadline_module
from vfs import fanout as fanout_module
from vfs.deadline import Deadline
from vfs.fanout import ScopePlan, plan_scope, walks
from vfs.paths import ROOT, Path
from vfs.pattern_matching import ScopeChannel

ENTRY = Path("/m")


class _LateClock:
    """A fake monotonic clock: 0.0 on its first read, far past any wall on every later one."""

    def __init__(self) -> None:
        self.reads = 0

    def __call__(self) -> float:
        self.reads += 1
        return 0.0 if self.reads == 1 else 1e12


def _counted(monkeypatch: pytest.MonkeyPatch, name: str) -> list[tuple[Any, ...]]:
    """Each call the planner makes to its own binding of *name*; the real function answers."""
    calls: list[tuple[Any, ...]] = []
    real = getattr(fanout_module, name)

    def counted(*args: Any) -> Any:
        calls.append(args)
        return real(*args)

    monkeypatch.setattr(fanout_module, name, counted)
    return calls


def _beneath(entry: Path, count: int) -> tuple[Path, ...]:
    """*count* roots strictly beneath *entry*."""
    return tuple(Path(f"{'' if entry == ROOT else entry}/r{index:03}") for index in range(count))


def _planned(roots: tuple[Path, ...], entry: Path = ENTRY) -> ScopePlan:
    """The plan of the one arm ``*.txt`` under *roots*, all owned by *entry*, with no wall."""
    owners = dict.fromkeys(roots, entry)
    return plan_scope(owners, (entry,), (), roots, ("*.txt",), (), (), frozenset(), Deadline.never())


def test_plan_scope_is_a_pure_function(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: the walk reading a router, a mount table or its own last answer, so
    equal inputs plan differently or compose a different number of times."""
    composed = _counted(monkeypatch, "composed_pattern")
    roots = (*_beneath(ENTRY, 200), ENTRY)
    first = _planned(roots)
    assert len(composed) == 1
    second = _planned(roots)
    assert len(composed) == 2
    assert first == second
    assert (first.completed, first.roots) == (True, roots)
    rels = tuple(Path(f"/r{index:03}") for index in range(200))
    assert first.scopes[ENTRY].roots == rels
    assert second.scopes[ENTRY].roots == rels


def test_the_walk_stops_at_its_wall_and_keeps_undecided_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: a stopped walk dropping the skips it never decided, or reporting
    roots it never planned; and the deadline read at any cadence but every 64th."""
    residuated = _counted(monkeypatch, "residuals")
    clock = _LateClock()
    monkeypatch.setattr(deadline_module, "monotonic", clock)
    roots = _beneath(ROOT, 100)
    skips = (Path("/s0"), Path("/s1"))
    plan = plan_scope(
        dict.fromkeys(roots, ROOT), (ROOT,), skips, roots, ("*.txt",), (), ("*.txt",), frozenset(), Deadline(at=10.0)
    )
    assert (plan.completed, plan.roots) == (False, roots[:64])
    assert plan.skips == frozenset(skips)
    assert (len(residuated), clock.reads) == (0, 2)

    monkeypatch.setattr(deadline_module, "monotonic", _LateClock())
    undecided = tuple(Path(f"/b{index:03}") for index in range(100))
    stopped = plan_scope({}, (ROOT,), undecided, (), ("*.txt",), (), ("/a/*.txt",), frozenset(), Deadline(at=10.0))
    assert (stopped.completed, stopped.roots) == (False, ())
    assert stopped.skips == frozenset(undecided[64:])


@pytest.mark.parametrize(
    ("count", "arms", "extra", "rides", "compositions"),
    [
        pytest.param(2, 1, None, False, 0, id="2-1"),
        pytest.param(10, 20, None, False, 0, id="10-20"),
        pytest.param(200, 1, None, False, 0, id="200-1"),
        pytest.param(201, 1, None, False, 0, id="201-1"),
        pytest.param(10, 64, ENTRY, False, 64, id="10-64-whole-side"),
        pytest.param(201, 1, Path("/m/.vfs"), False, 1, id="201-1-view-ancestor"),
        pytest.param(2, 1, Path("/m/.vfs/trash/.vfs"), True, 0, id="2-1-tombstoned-meta-root"),
    ],
)
def test_every_root_beneath_an_entry_rides_its_scope(
    monkeypatch: pytest.MonkeyPatch, count: int, arms: int, extra: Path | None, rides: bool, compositions: int
) -> None:
    """Guards: a root strictly beneath its entry composing at any size, a whole-side
    root or a live ancestor of the trash head riding the scope, the tombstoned
    root stored at ``/.vfs`` (beneath the head, so no ancestor of it) composing,
    or the staging test made false so every root composes."""
    composed = _counted(monkeypatch, "composed_pattern")
    beneath = _beneath(ENTRY, count)
    roots = beneath if extra is None else (*beneath, extra)
    patterns = tuple(f"*.e{index}" for index in range(arms))
    plan = plan_scope(dict.fromkeys(roots, ENTRY), (ENTRY,), (), roots, patterns, (), (), frozenset(), Deadline.never())
    rels = tuple(Path(f"/r{index:03}") for index in range(count))
    if extra is not None and rides:
        rels = (*rels, extra.without_mount(ENTRY))
    assert plan.scopes == {ENTRY: ScopeChannel(roots=rels, arms=patterns, arms_not=())}
    assert len(composed) == compositions
    members = plan.members[ENTRY]
    assert members is not None
    assert len(members) == compositions
    assert (plan.completed, plan.roots) == (True, roots)


@pytest.mark.parametrize("others", [0, 201])
def test_a_view_ancestor_root_composes_at_every_size(others: int) -> None:
    """Guards: a live root above the trash head riding the scope past some size,
    where its joined text can no longer enter the trash view."""
    roots = (Path("/m/.vfs"), *_beneath(ENTRY, others))
    owners = dict.fromkeys(roots, ENTRY)
    plan = plan_scope(owners, (ENTRY,), (), roots, ("trash/x/**",), (), (), frozenset(), Deadline.never())
    assert plan.members[ENTRY] == {"/.vfs/trash/x/**"}
    rels = tuple(Path(f"/r{index:03}") for index in range(others))
    expected = {ENTRY: ScopeChannel(roots=rels, arms=("trash/x/**",), arms_not=())} if others else {}
    assert plan.scopes == expected


def test_walks_is_true_exactly_when_planning_residuates() -> None:
    """Guards: ``walks`` forgetting one of the four things that make a plan residuate."""
    assert walks((), ("*.txt", "a?"), ("*.md",), ()) is False
    assert walks((Path("/a"),), ("*.txt",), (), ()) is True
    assert walks((), ("src/*.txt",), (), ()) is True
    assert walks((), ("*.txt",), ("src/*.md",), ()) is True
    assert walks((), ("*.txt",), (), (Path("/m"),)) is True
