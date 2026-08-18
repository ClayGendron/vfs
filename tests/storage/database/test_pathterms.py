"""The term compiler and the allow-list seam — the superset battery.

The one law under test: nomination built from compiled terms
over-approximates the glob authority — every path the compiled
``GlobFilter`` matches is nominated by the term evaluation, for every
(path, glob) pair in the generated cross — and exclusions never enter
the seam at all. The DB half proves the same law through the posting
table: the allow-list ids always cover the authority's matches, void
channels return ``None``, dead terms return honestly empty sets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select

from tests.support.database_helpers import _url
from vfs.models import Entry
from vfs.paths import Path
from vfs.pattern_matching import compile_filter, glob_defect
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.pathterms import (
    ArmTerms,
    NameFact,
    _term_counts,
    allow_list_ids,
    compile_channel,
    compile_terms,
)
from vfs.storage.backends.database.segments import path_segments

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# A corpus of stored-path shapes: root-level, nested, recurring names,
# dotfiles, case variants, dotted directory names, deep chains, plus
# term-overlap decoys (a segment shared without the whole conjunction)
# and a five-literal chain that makes the intersection cap slice.
PATHS = tuple(
    Path(text)
    for text in (
        "/Makefile",
        "/notes.txt",
        "/src/main.py",
        "/src/app/main.py",
        "/src/app/util/helpers.py",
        "/src/test_alpha.py",
        "/src/alpha_test.c",
        "/src/.py",
        "/src/app.tests/x.py",
        "/docs/readme.md",
        "/docs/img1/photo.png",
        "/a/x/a/f.txt",
        "/a/a/a.txt",
        "/Docs/Readme.MD",
        "/.hidden/config",
        "/deep/er/est/leaf",
        "/app/solo.txt",
        "/p1/p2/p3/p4/p5/leaf.txt",
        "/p2/p3/p4/p5/decoy.txt",
    )
)

# Glob shapes across the language: anchored and floating, extension
# tails, stem prefixes and suffixes, classes, braces, ** at every
# position, full-literal paths, and the unbounded catch-alls.
GLOBS = (
    "src/**/*.py",
    "src/*.py",
    "**/*.py",
    "*.py",
    "*.PY",
    "Makefile",
    "**/Makefile",
    "src/**",
    "/src/**",
    "docs/*",
    "*/main.py",
    "src/app/*.py",
    "{src,docs}/**/*.p?",
    "src/**/test_*.py",
    "test_*.py",
    "*_test.c",
    "docs/img[0-9]/*.png",
    "a/**/f.txt",
    "/a/a/a.txt",
    "?",
    "**",
    "src/app.tests/*.py",
    ".hidden/**",
    "/deep/er/**",
    "src/{app,app.tests}/**",
)


def _nominated(arm: ArmTerms, path: Path) -> bool:
    """The pure mirror of the arm's nomination terms, exactly as SQL would apply them."""
    if not (arm.segments <= path_segments(str(path))):
        return False
    if arm.ext is not None and path.ext != arm.ext.ext and path.name != arm.ext.dot_suffix:
        return False
    if arm.name is not None:
        if arm.name.prefix:
            return path.name.startswith(arm.name.text)
        return path.name == arm.name.text
    return True


@pytest.fixture
async def storage(tmp_path) -> AsyncIterator[DatabaseStorage]:
    mount = DatabaseStorage(url=_url(tmp_path))
    entries = [Entry(path=path, content=f"body of {path}") for path in PATHS]
    assert (await mount.write(entries=entries, parents=True)).success is True
    yield mount
    await mount.close()


# ---------------------------------------------------------------------------
# The compiler — term shapes per pattern
# ---------------------------------------------------------------------------


class TestCompileTerms:
    def test_directory_literals_become_segment_terms(self) -> None:
        (arm,) = compile_terms("src/**/*.py")
        assert arm.pattern == "/src/**/*.py"
        assert arm.segments == {"src"}
        assert arm.ext is not None and arm.ext.ext == "py"
        assert arm.name is None

    def test_a_full_literal_path_pins_everything(self) -> None:
        (arm,) = compile_terms("/a/b/f.txt")
        assert arm.segments == {"a", "b"}
        assert arm.name == NameFact(text="f.txt", prefix=False)
        assert arm.ext is not None and arm.ext.ext == "txt"

    def test_basename_literal_and_stem_prefix_tails(self) -> None:
        (makefile,) = compile_terms("src/**/Makefile")
        assert makefile.name == NameFact(text="Makefile", prefix=False)
        assert makefile.ext is None
        (stem,) = compile_terms("test_*.py")
        assert stem.segments == frozenset()
        assert stem.name == NameFact(text="test_", prefix=True)
        assert stem.ext is not None and stem.ext.ext == "py"

    def test_wildcard_and_class_components_contribute_nothing(self) -> None:
        (arm,) = compile_terms("docs/img[0-9]/*.png")
        assert arm.segments == {"docs"}
        (starred,) = compile_terms("*/x.py")
        assert starred.segments == frozenset()
        assert starred.name == NameFact(text="x.py", prefix=False)

    def test_suffix_stems_pin_only_the_extension(self) -> None:
        (arm,) = compile_terms("*_test.c")
        assert arm.segments == frozenset()
        assert arm.name is None
        assert arm.ext is not None and arm.ext.ext == "c"

    def test_the_catch_alls_are_unbounded(self) -> None:
        for pattern in ("**", "*", "?", "**/*"):
            (arm,) = compile_terms(pattern)
            assert arm.segments == frozenset()
            assert arm.segment_bounded is False

    def test_brace_arms_compile_separately(self) -> None:
        arms = compile_terms("{src,docs}/**/*.md")
        assert [arm.segments for arm in arms] == [{"src"}, {"docs"}]

    def test_a_leaf_double_star_pins_no_name(self) -> None:
        (arm,) = compile_terms("src/**")
        assert arm.segments == {"src"}
        assert arm.name is None
        assert arm.ext is None

    def test_root_level_literals_have_no_segment_terms(self) -> None:
        (arm,) = compile_terms("/Makefile")
        assert arm.segments == frozenset()
        assert arm.name == NameFact(text="Makefile", prefix=False)


class TestCompileChannel:
    def test_channel_dedupes_patterns_and_arms(self) -> None:
        channel = compile_channel(("src/**", "src/**", "{src,src}/**"))
        assert len(channel.arms) == 1

    def test_prunable_requires_every_arm_segment_bounded(self) -> None:
        assert compile_channel(("src/**", "docs/**")).prunable is True
        assert compile_channel(("src/**", "*.py")).prunable is False
        assert compile_channel(()).prunable is False


# ---------------------------------------------------------------------------
# The superset battery — generated paths x generated globs
# ---------------------------------------------------------------------------


class TestSupersetLaw:
    @pytest.mark.parametrize("pattern", GLOBS)
    def test_term_nomination_covers_the_authority(self, pattern: str) -> None:
        assert glob_defect(pattern) is None
        authority = compile_filter(pattern, ())
        arms = compile_terms(pattern)
        for path in PATHS:
            if authority.matches(path):
                assert any(_nominated(arm, path) for arm in arms), f"{pattern!r} matches {path} but no arm nominates it"

    def test_directory_positions_nominate_ancestors_not_order(self) -> None:
        # Order and position stay the authority's job: the terms
        # over-approximate by design, never the other way around.
        (arm,) = compile_terms("a/x/**")
        assert _nominated(arm, Path("/x/a/f.txt")) is True
        assert compile_filter("a/x/**", ()).matches(Path("/x/a/f.txt")) is False


# ---------------------------------------------------------------------------
# The allow-list seam — id sets from the posting table
# ---------------------------------------------------------------------------


async def _paths_by_id(storage: DatabaseStorage) -> dict[int, str]:
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as session:
        rows = (await session.execute(select(entry.c.id, entry.c.path))).all()
    return {row.id: row.path for row in rows}


async def _allow_list(storage: DatabaseStorage, patterns: tuple[str, ...]) -> list[int] | None:
    channel = compile_channel(patterns)
    async with storage._host.session_factory() as session:
        return await allow_list_ids(session, storage._host.tables, storage._host.membership_budget, channel)


class TestAllowListSeam:
    async def test_the_allow_list_covers_the_authority(self, storage: DatabaseStorage) -> None:
        ids = await _allow_list(storage, ("src/**/*.py",))
        assert ids is not None
        by_id = await _paths_by_id(storage)
        admitted = {by_id[doc_id] for doc_id in ids}
        authority = compile_filter("src/**/*.py", ())
        matched = {str(path) for path in by_id.values() if authority.matches(Path(path))}
        assert matched <= admitted

    async def test_multi_term_arms_intersect(self, storage: DatabaseStorage) -> None:
        ids = await _allow_list(storage, ("src/app/**",))
        assert ids is not None
        by_id = await _paths_by_id(storage)
        admitted = {by_id[doc_id] for doc_id in ids}
        # Every admitted row carries both segments among its ancestors.
        assert admitted
        for path in admitted:
            assert {"src", "app"} <= path_segments(path)

    async def test_the_union_spans_the_channel(self, storage: DatabaseStorage) -> None:
        src = await _allow_list(storage, ("src/**",))
        docs = await _allow_list(storage, ("docs/**",))
        both = await _allow_list(storage, ("src/**", "docs/**"))
        assert src is not None and docs is not None and both is not None
        assert set(both) == set(src) | set(docs)

    async def test_brace_arms_union_like_separate_globs(self, storage: DatabaseStorage) -> None:
        braced = await _allow_list(storage, ("{src,docs}/**",))
        separate = await _allow_list(storage, ("src/**", "docs/**"))
        assert braced is not None and separate is not None
        assert braced == separate

    async def test_an_unbounded_arm_voids_pruning(self, storage: DatabaseStorage) -> None:
        assert await _allow_list(storage, ("*.py",)) is None
        assert await _allow_list(storage, ("src/**", "**")) is None
        assert await _allow_list(storage, ()) is None

    async def test_a_dead_term_is_an_honest_empty_set(self, storage: DatabaseStorage) -> None:
        ids = await _allow_list(storage, ("nosuchdir/**",))
        assert ids is not None
        assert ids == []
        union = await _allow_list(storage, ("nosuchdir/**", "docs/**"))
        docs = await _allow_list(storage, ("docs/**",))
        assert union is not None and docs is not None
        assert union == docs

    async def test_a_dead_term_short_circuits_its_arm(self, storage: DatabaseStorage) -> None:
        # Both terms compile, but the dead one intersects first (it is
        # the smallest posting) and empties the arm without a second look.
        ids = await _allow_list(storage, ("ghost/src/**",))
        assert ids == []

    async def test_the_intersection_excludes_a_term_overlap_decoy(self, storage: DatabaseStorage) -> None:
        # /app/solo.txt carries the rarer term without the conjunction —
        # a join shortened to the rarest term alone would admit it.
        ids = await _allow_list(storage, ("src/app/**",))
        assert ids is not None
        by_id = await _paths_by_id(storage)
        admitted = {by_id[doc_id] for doc_id in ids}
        assert "/src/app/main.py" in admitted
        assert not any(path.startswith("/app/") for path in admitted)

    async def test_a_wide_arm_slices_to_the_rarest_terms_and_stays_sound(self, storage: DatabaseStorage) -> None:
        # Five literal directories exceed the intersection cap: the join
        # keeps the four rarest, and p1 (rarest) always survives.
        ids = await _allow_list(storage, ("p1/p2/p3/p4/p5/*.txt",))
        assert ids is not None
        by_id = await _paths_by_id(storage)
        admitted = {by_id[doc_id] for doc_id in ids}
        assert "/p1/p2/p3/p4/p5/leaf.txt" in admitted
        assert "/p2/p3/p4/p5/decoy.txt" not in admitted

    async def test_the_join_drives_from_the_rarest_term(
        self, storage: DatabaseStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Written order seeds engines that join in written order: the
        # anchor condition must name the rarest term, not the first.
        channel = compile_channel(("docs/img1/**",))
        captured: list[Any] = []
        async with storage._host.session_factory() as session:
            real = session.execute

            async def spying(stmt, *args, **kwargs):
                captured.append(stmt)
                return await real(stmt, *args, **kwargs)

            monkeypatch.setattr(session, "execute", spying)
            budget = storage._host.membership_budget
            counts = await _term_counts(session, storage._host.tables, budget, {"docs", "img1"})
            assert counts["img1"] < counts["docs"]  # the pin is non-vacuous
            ids = await allow_list_ids(session, storage._host.tables, storage._host.membership_budget, channel)
        assert ids
        anchor_condition = captured[-1]._where_criteria[0]
        assert anchor_condition.right.value == "img1"

    async def test_ids_are_sorted_and_deduped(self, storage: DatabaseStorage) -> None:
        ids = await _allow_list(storage, ("src/**", "src/app/**"))
        assert ids is not None
        assert ids == sorted(set(ids))

    async def test_exclusions_never_shrink_the_allow_list(self, storage: DatabaseStorage) -> None:
        # The seam takes no exclusion channel at all: rows an exclusion
        # would remove are still nominated — the authority removes them.
        ids = await _allow_list(storage, ("src/**",))
        assert ids is not None
        by_id = await _paths_by_id(storage)
        admitted = {by_id[doc_id] for doc_id in ids}
        excluded_by_caller = compile_filter("src/**/*.py", ())
        assert any(excluded_by_caller.matches(Path(path)) for path in admitted)
