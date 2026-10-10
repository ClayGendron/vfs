"""test_grants parity: the live loop vs (a) memoised closures/everyone level, (b) owner loop hoisted. Same questions, same assertions."""
from __future__ import annotations
import random, sys, time
sys.path.insert(0, "/Users/claygendron/Git/Repos/vfs")
from tests.support.grant_worlds import LAYOUTS, SUBJECT_SETS, random_world
from tests.support.oracles.grants import GrantWorld, everyone_rank, set_rank
from vfs.storage.grants import LEVEL_RANK, covers, resolve

WORLDS = 400

def live(layout, level):
    rng = random.Random(58); need = LEVEL_RANK[level]; n = 0
    for _ in range(WORLDS):
        world = random_world(rng, layout)
        for subjects in SUBJECT_SETS:
            rights = resolve(world.closures(subjects), world.grants, level)
            for path in (*layout.paths, *layout.traps):
                for owner in (world.owners.get(path), None, *subjects):
                    world.owners[path] = owner
                    expected = set_rank(world, subjects, path) >= need
                    label = everyone_rank(world, path)
                    assert rights.admits(path, owner, label) is expected
                    world.owners.pop(path, None); n += 1
    return n

def memo_closure(layout, level):
    """Only change: GrantWorld.closure memoised per world (member_of never changes after construction)."""
    rng = random.Random(58); need = LEVEL_RANK[level]; n = 0
    for _ in range(WORLDS):
        world = random_world(rng, layout)
        cache: dict[str, frozenset[str]] = {}
        real = GrantWorld.closure
        def closure(self, principal, _c=cache, _w=world):
            if principal not in _c:
                _c[principal] = real(self, principal)
            return _c[principal]
        world.closure = closure.__get__(world)
        for subjects in SUBJECT_SETS:
            rights = resolve(world.closures(subjects), world.grants, level)
            for path in (*layout.paths, *layout.traps):
                for owner in (world.owners.get(path), None, *subjects):
                    world.owners[path] = owner
                    expected = set_rank(world, subjects, path) >= need
                    label = everyone_rank(world, path)
                    assert rights.admits(path, owner, label) is expected
                    world.owners.pop(path, None); n += 1
    return n

def hoisted(layout, level):
    """Owner loop hoisted: the owner-free ranks are asked once per (subjects, path); the owner floor is the min over subjects of max(rank, floor). Same questions, derived from the oracle's own definition."""
    rng = random.Random(58); need = LEVEL_RANK[level]; n = 0
    for _ in range(WORLDS):
        world = random_world(rng, layout)
        for subjects in SUBJECT_SETS:
            rights = resolve(world.closures(subjects), world.grants, level)
            for path in (*layout.paths, *layout.traps):
                label = everyone_rank(world, path)
                for owner in (world.owners.get(path), None, *subjects):
                    world.owners[path] = owner
                    expected = set_rank(world, subjects, path) >= need
                    assert rights.admits(path, owner, label) is expected
                    world.owners.pop(path, None); n += 1
    return n

for name, fn in (("live", live), ("memo_closure", memo_closure), ("label hoisted only", hoisted)):
    for layout, lname in zip(LAYOUTS, ("base", "siblings")):
        t0 = time.perf_counter(); n = fn(layout, "read"); dt = time.perf_counter() - t0
        print(f"{name:20s} {lname:9s} read  {dt:6.2f}s  questions={n}")
