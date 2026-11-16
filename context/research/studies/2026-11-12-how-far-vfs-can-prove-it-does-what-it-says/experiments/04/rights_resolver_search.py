"""Experiment 04-d: the rights resolver against the pointwise oracle, under a wider generated search.

Run from the checkout root, with Hypothesis's store outside it:
HYPOTHESIS_STORAGE_DIRECTORY=<scratch>/hyp uv run --with hypothesis pytest <this file> -p no:cacheprovider --no-cov -n 0 -q
The suite runs 400 worlds from one fixed seed (tests/storage/test_grants.py). Here
Hypothesis drives the same world builder through its own random source, so every run
draws new worlds and a failure shrinks to the seed Hypothesis reports.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.support.grant_worlds import LAYOUTS, SUBJECT_SETS, random_world
from tests.support.oracles.grants import everyone_rank, set_rank
from vfs.storage.grants import GRANTABLE_LEVELS, LEVEL_RANK, resolve


@settings(max_examples=20_000, deadline=None, database=None)
@given(st.randoms(use_true_random=False), st.sampled_from(LAYOUTS), st.sampled_from(GRANTABLE_LEVELS))
def test_the_resolver_agrees_with_the_oracle(rng, layout, level) -> None:
    world = random_world(rng, layout)
    need = LEVEL_RANK[level]
    for subjects in SUBJECT_SETS:
        rights = resolve(world.closures(subjects), world.grants, level)
        for path in (*layout.paths, *layout.traps):
            for owner in (world.owners.get(path), None, *subjects):
                world.owners[path] = owner
                expected = set_rank(world, subjects, path) >= need
                assert rights.admits(path, owner, everyone_rank(world, path)) is expected
                world.owners.pop(path, None)
