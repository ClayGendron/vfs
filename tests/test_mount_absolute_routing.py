"""Tests for absolute-path routing of glob/grep through mounts.

Covers the bug where ``glob("/mnt/**/*.py")`` and ``grep`` with paths under
a mount returned empty results because :meth:`_route_fanout` dispatches the
full pattern to every mount without stripping the mount prefix — but the
mount's terminal filesystem stores paths mount-relative.

The baseline path for single-candidate ops (``read``, ``write``, ``edit``)
goes through :meth:`_route_single` which calls ``_resolve_terminal`` to
strip the mount prefix. ``glob``/``grep`` take the fanout branch and skip
that strip. Contrast: a pattern like ``**/*.py`` has no mount prefix, so
fanout happens to work — see ``test_glob_through_public_api`` in
``test_database.py``.

Mount paths are single-segment by construction
(see ``VirtualFileSystem._normalize_mount_path``); real nesting is
router-to-router (an outer router's mount points at a non-storage
VirtualFileSystem that itself mounts a leaf). The ``nested_mounts``
fixture exercises that two-hop case.

The fixtures here use **isolated** engines per mount (one engine per
filesystem) so that a file written through the mount cannot accidentally
leak into the root's storage — the only way glob can return a match is if
the mount-prefix rewrite is correct.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from vfs.backends.database import DatabaseFileSystem
from vfs.base import VirtualFileSystem
from vfs.client import VFSClientAsync
from vfs.results import Candidate, VFSResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _sqlite_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


@pytest.fixture
async def two_mounts() -> AsyncIterator[tuple[VirtualFileSystem, DatabaseFileSystem, DatabaseFileSystem]]:
    """Router with two isolated DB mounts at ``/data`` and ``/other``.

    Each mount has its own engine — no shared storage. Seeds a small,
    predictable tree on each so glob/grep can exercise mount-prefix
    rewriting across varied path depths.
    """
    data_engine = await _sqlite_engine()
    other_engine = await _sqlite_engine()
    data = DatabaseFileSystem(engine=data_engine)
    other = DatabaseFileSystem(engine=other_engine)

    # Seed /data — written through the mount, so the router rebases
    # paths to mount-relative before they hit ``_write_impl``.
    router = VFSClientAsync()
    await router.add_mount("/data", data)
    await router.add_mount("/other", other)

    await router.write("/data/readme.md", "data readme")
    await router.write("/data/src/app.py", "print('data')")
    await router.write("/data/src/util.py", "def util(): ...")
    await router.write("/data/docs/guide.md", "guide")
    await router.write("/data/docs/deep/nested.md", "nested")

    await router.write("/other/notes.md", "other notes")
    await router.write("/other/src/main.py", "print('other')")

    try:
        yield router, data, other
    finally:
        await data_engine.dispose()
        await other_engine.dispose()


@pytest.fixture
async def storageful_root_with_mount() -> AsyncIterator[tuple[DatabaseFileSystem, DatabaseFileSystem]]:
    """A real storage root (``DatabaseFileSystem``) with one mount underneath.

    Important: ``VirtualFileSystem`` has ``storage=False`` (see ``client.py``),
    so the existing ``two_mounts`` fixture exercises the no-storage
    branch of ``_route_fanout``. The router-side post-filter and
    self-vs-mount merging path needs a storageful root to be exercised.
    """
    root_engine = await _sqlite_engine()
    mount_engine = await _sqlite_engine()
    root = DatabaseFileSystem(engine=root_engine)
    mount = DatabaseFileSystem(engine=mount_engine)
    await root.add_mount("/data", mount)

    # Files at root, outside any mount
    await root.write("/top.md", "top level")
    await root.write("/lib/util.py", "util at root")
    await root.write("/lib/sub/deep.py", "deep at root")

    # Files inside the mount
    await root.write("/data/readme.md", "data readme")
    await root.write("/data/src/app.py", "print('mount')")
    await root.write("/data/src/sub/inner.py", "inner")

    try:
        yield root, mount
    finally:
        await root_engine.dispose()
        await mount_engine.dispose()


@pytest.fixture
async def wildcard_mount_router() -> AsyncIterator[tuple[VirtualFileSystem, DatabaseFileSystem]]:
    """Router with one mount whose name lets us test glob mount selectors.

    The mount name ``data`` matches ``*``, ``d?ta``, ``d[ae]ta``, and ``da*``.
    """
    engine = await _sqlite_engine()
    mount = DatabaseFileSystem(engine=engine)
    router = VFSClientAsync()
    await router.add_mount("/data", mount)

    await router.write("/data/src/app.py", "print('x')")
    await router.write("/data/src/util.py", "u")
    await router.write("/data/src/sub/deep.py", "d")
    await router.write("/data/readme.md", "r")

    try:
        yield router, mount
    finally:
        await engine.dispose()


@pytest.fixture
async def nested_mounts() -> AsyncIterator[tuple[VirtualFileSystem, DatabaseFileSystem]]:
    """Router → mid-router → leaf DB, mounted at ``/l1/l2``.

    Exercises a two-level mount chain: the leaf should only ever see
    paths rooted under ``/``, even when the caller uses the full
    ``/l1/l2/...`` path.
    """
    leaf_engine = await _sqlite_engine()
    leaf = DatabaseFileSystem(engine=leaf_engine)
    mid = VirtualFileSystem(storage=False)
    await mid.add_mount("/l2", leaf)
    router = VFSClientAsync()
    await router.add_mount("/l1", mid)

    await router.write("/l1/l2/plan.md", "the plan")
    await router.write("/l1/l2/src/a.py", "a = 1")
    await router.write("/l1/l2/src/sub/b.py", "b = 2")

    try:
        yield router, leaf
    finally:
        await leaf_engine.dispose()


@pytest.fixture
async def deep_chain_mounts() -> AsyncIterator[tuple[VirtualFileSystem, DatabaseFileSystem]]:
    """Three-hop chain: VirtualFileSystem → router1 → router2 → leaf DB.

    Mounted at ``/a`` → ``/b`` → ``/c``, so the external path
    ``/a/b/c/foo.py`` resolves through three mount-prefix strips before
    hitting the leaf, where it's stored as ``/foo.py``. This is the
    "mount a fs to another, mount that to another, mount that to
    VirtualFileSystem" case — each hop must consume its own single-segment
    mount prefix and recursively dispatch.
    """
    leaf_engine = await _sqlite_engine()
    leaf = DatabaseFileSystem(engine=leaf_engine)
    router2 = VirtualFileSystem(storage=False)
    await router2.add_mount("/c", leaf)
    router1 = VirtualFileSystem(storage=False)
    await router1.add_mount("/b", router2)
    outer = VFSClientAsync()
    await outer.add_mount("/a", router1)

    await outer.write("/a/b/c/top.md", "top")
    await outer.write("/a/b/c/src/app.py", "app")
    await outer.write("/a/b/c/src/util.py", "util")
    await outer.write("/a/b/c/src/sub/deep.py", "deep")

    try:
        yield outer, leaf
    finally:
        await leaf_engine.dispose()


# =========================================================================
# Baseline — mount-relative patterns already work today
# =========================================================================


class TestBaselineRelativePatterns:
    """Patterns without an absolute prefix should match across every mount.

    These tests pin the behavior that currently works so a mount-prefix
    rewrite fix doesn't regress it.
    """

    async def test_glob_double_star_matches_all_mounts(self, two_mounts):
        router, _data, _other = two_mounts
        r = await router.glob("**/*.py")
        assert set(r.paths) == {
            "/data/src/app.py",
            "/data/src/util.py",
            "/other/src/main.py",
        }

    async def test_glob_double_star_matches_md_across_mounts(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.glob("**/*.md")
        assert set(r.paths) == {
            "/data/readme.md",
            "/data/docs/guide.md",
            "/data/docs/deep/nested.md",
            "/other/notes.md",
        }

    async def test_grep_no_path_filter_scans_all_mounts(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.grep("print")
        assert set(r.paths) == {"/data/src/app.py", "/other/src/main.py"}


# =========================================================================
# Bug — absolute pattern with mount prefix
# =========================================================================


class TestGlobAbsolutePatternUnderMount:
    """``glob('/data/**/*.py')`` must find files that live inside the ``/data`` mount.

    These are the tests that demonstrate the routing bug. They should
    fail on ``main`` until the mount-prefix rewrite lands in
    ``_route_fanout``.
    """

    async def test_absolute_mount_prefix_double_star(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.glob("/data/**/*.py")
        assert set(r.paths) == {"/data/src/app.py", "/data/src/util.py"}

    async def test_absolute_mount_prefix_with_subdir(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.glob("/data/src/*.py")
        assert set(r.paths) == {"/data/src/app.py", "/data/src/util.py"}

    async def test_absolute_mount_prefix_all_files(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.glob("/data/**")
        assert "/data/readme.md" in set(r.paths)
        assert "/data/src/app.py" in set(r.paths)
        assert "/data/docs/deep/nested.md" in set(r.paths)
        # Must not leak /other into a /data-scoped query.
        assert not any(p.startswith("/other") for p in r.paths)

    async def test_absolute_mount_prefix_single_file(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.glob("/data/readme.md")
        assert set(r.paths) == {"/data/readme.md"}

    async def test_absolute_mount_prefix_deep_nested(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.glob("/data/docs/**/*.md")
        assert set(r.paths) == {
            "/data/docs/guide.md",
            "/data/docs/deep/nested.md",
        }

    async def test_mount_scoped_pattern_ignores_other_mount(self, two_mounts):
        """A ``/data/...`` pattern must not return files from ``/other``."""
        router, _, _ = two_mounts
        r = await router.glob("/data/**/*.md")
        assert "/other/notes.md" not in set(r.paths)
        assert set(r.paths) == {
            "/data/readme.md",
            "/data/docs/guide.md",
            "/data/docs/deep/nested.md",
        }

    async def test_pattern_targeting_unmounted_prefix_returns_empty(self, two_mounts):
        """A pattern rooted at a non-existent prefix must not accidentally
        match files stored inside a mount."""
        router, _, _ = two_mounts
        r = await router.glob("/nowhere/**/*.py")
        assert r.success
        assert r.paths == ()


class TestGrepAbsolutePathsUnderMount:
    """``grep`` with ``paths`` positional under a mount must find matches.

    Same root cause: ``paths`` flows into ``_apply_structural_filters``
    as literal LIKE prefixes, so without mount-prefix stripping the
    prefix ``/data/src`` never matches the mount's internal ``/src/...``
    storage.
    """

    async def test_grep_with_absolute_path_under_mount(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.grep("print", paths=("/data/src",))
        assert set(r.paths) == {"/data/src/app.py"}

    async def test_grep_with_absolute_mount_root_path(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.grep("print", paths=("/data",))
        assert set(r.paths) == {"/data/src/app.py"}

    async def test_grep_path_scoping_isolates_mounts(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.grep("print", paths=("/other",))
        assert set(r.paths) == {"/other/src/main.py"}

    async def test_grep_multi_path_across_mounts(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.grep("print", paths=("/data/src", "/other/src"))
        assert set(r.paths) == {"/data/src/app.py", "/other/src/main.py"}

    async def test_grep_with_glob_option_scoped_to_mount(self, two_mounts):
        """``--glob`` patterns are also mount-prefix-sensitive; they go
        through ``glob_to_sql_like`` in ``_apply_structural_filters``."""
        router, _, _ = two_mounts
        r = await router.grep("print", globs=("/data/**/*.py",))
        assert set(r.paths) == {"/data/src/app.py"}


class TestCandidateBasedSearchUnderMount:
    """Candidate-based search must also honor absolute mount-scoped filters.

    ``_dispatch_candidates`` rebases candidate paths to the terminal
    filesystem before dispatch. Absolute path/glob filters therefore
    need router-side handling as well; forwarding them unchanged to the
    terminal backend would mismatch against mount-relative candidate
    paths.
    """

    async def test_glob_candidates_with_absolute_mount_pattern(self, two_mounts):
        router, _, _ = two_mounts
        seeds = VFSResult(
            candidates=[
                Candidate(path="/data/src/app.py"),
                Candidate(path="/other/src/main.py"),
            ]
        )
        r = await router.glob("/data/**/*.py", candidates=seeds)
        assert set(r.paths) == {"/data/src/app.py"}

    async def test_grep_candidates_with_absolute_mount_glob_filter(self, two_mounts):
        router, _, _ = two_mounts
        seeds = VFSResult(
            candidates=[
                Candidate(path="/data/src/app.py"),
                Candidate(path="/other/src/main.py"),
            ]
        )
        r = await router.grep("print", candidates=seeds, globs=("/data/**/*.py",))
        assert set(r.paths) == {"/data/src/app.py"}


# =========================================================================
# Nested mount chains
# =========================================================================


class TestNestedMountAbsolutePaths:
    async def test_glob_absolute_path_through_two_levels(self, nested_mounts):
        router, _leaf = nested_mounts
        r = await router.glob("/l1/l2/**/*.py")
        assert set(r.paths) == {"/l1/l2/src/a.py", "/l1/l2/src/sub/b.py"}

    async def test_glob_absolute_prefix_all(self, nested_mounts):
        router, _leaf = nested_mounts
        r = await router.glob("/l1/l2/**")
        assert "/l1/l2/plan.md" in set(r.paths)
        assert "/l1/l2/src/a.py" in set(r.paths)

    async def test_grep_absolute_path_through_two_levels(self, nested_mounts):
        router, _leaf = nested_mounts
        r = await router.grep("=", paths=("/l1/l2/src",))
        assert set(r.paths) == {"/l1/l2/src/a.py", "/l1/l2/src/sub/b.py"}

    async def test_leaf_stores_mount_relative_paths(self, nested_mounts):
        """Sanity check — the leaf filesystem must store paths without the
        ``/l1/l2`` prefix. If this ever changes, the whole bug story
        changes with it."""
        _router, leaf = nested_mounts
        async with leaf._use_session() as s:
            r = await leaf._glob_impl(pattern="/**/*.py", session=s)
        assert set(r.paths) == {"/src/a.py", "/src/sub/b.py"}


# =========================================================================
# Root + mount coexistence
# =========================================================================


class TestRootAndMountAbsolutePaths:
    """Mix of root-level storage and a mount — absolute patterns must
    route correctly to both."""

    async def test_root_pattern_does_not_reach_mount(self, two_mounts):
        """An absolute prefix that does not match any mount should be
        answered by the root (or return empty if the root has no
        storage). It must never fall through to a mount whose prefix
        does not match."""
        router, _, _ = two_mounts
        r = await router.glob("/data2/**/*.py")
        assert r.paths == ()

    async def test_pattern_matches_only_intended_mount(self, two_mounts):
        """``/other/**`` must only reach the ``/other`` mount, not ``/data``."""
        router, _, _ = two_mounts
        r = await router.glob("/other/**/*.py")
        assert set(r.paths) == {"/other/src/main.py"}


# =========================================================================
# Glob with positional ``paths`` arg
# =========================================================================


class TestGlobPathsPositional:
    """``glob('**/*.py', '/data/src')`` — positional ``paths`` are literal
    prefixes that must be mount-prefix-stripped (or routed) just like the
    main pattern."""

    async def test_glob_paths_under_mount(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.glob("**/*.py", paths=("/data/src",))
        assert set(r.paths) == {"/data/src/app.py", "/data/src/util.py"}

    async def test_glob_paths_at_mount_root(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.glob("**/*.md", paths=("/data",))
        assert set(r.paths) == {
            "/data/readme.md",
            "/data/docs/guide.md",
            "/data/docs/deep/nested.md",
        }

    async def test_glob_paths_isolates_mounts(self, two_mounts):
        """A path under ``/data`` must not return ``/other`` files."""
        router, _, _ = two_mounts
        r = await router.glob("**/*.py", paths=("/data",))
        assert "/other/src/main.py" not in set(r.paths)
        assert set(r.paths) == {"/data/src/app.py", "/data/src/util.py"}

    async def test_glob_multi_paths_across_mounts(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.glob("**/*.py", paths=("/data/src", "/other/src"))
        assert set(r.paths) == {
            "/data/src/app.py",
            "/data/src/util.py",
            "/other/src/main.py",
        }

    async def test_glob_paths_pointing_at_unmounted_prefix(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.glob("**/*.py", paths=("/nowhere",))
        assert r.paths == ()


# =========================================================================
# Grep --glob and --glob-not (negated) routing
# =========================================================================


class TestGrepGlobsNot:
    """``globs_not`` must NEVER be silently dropped during fanout. If a
    negated glob can't be exactly rewritten for a mount's pushdown, the
    router must enforce it after the mount returns."""

    async def test_globs_not_excludes_files_under_mount(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.grep("print", globs_not=("/data/src/util.py",))
        # /data/src/util.py doesn't match "print" anyway, so this just
        # asserts the rewrite path doesn't break things.
        assert set(r.paths) == {"/data/src/app.py", "/other/src/main.py"}

    async def test_globs_not_excludes_a_real_match(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.grep("print", globs_not=("/data/src/app.py",))
        assert set(r.paths) == {"/other/src/main.py"}

    async def test_globs_not_with_wildcard_mount_selector(self, two_mounts):
        """``/*/src/main.py`` is a non-literal-prefix glob that should
        still exclude ``/other/src/main.py`` after rebase."""
        router, _, _ = two_mounts
        r = await router.grep("print", globs_not=("/*/src/main.py",))
        assert "/other/src/main.py" not in set(r.paths)
        assert set(r.paths) == {"/data/src/app.py"}

    async def test_globs_positive_routes_to_mount(self, two_mounts):
        router, _, _ = two_mounts
        r = await router.grep("print", globs=("/data/**/*.py",))
        assert set(r.paths) == {"/data/src/app.py"}

    async def test_globs_positive_with_wildcard_selector(self, two_mounts):
        """``/*/src/*.py`` should match files in both ``/data/src`` and
        ``/other/src`` because ``*`` covers each mount name."""
        router, _, _ = two_mounts
        r = await router.grep("print", globs=("/*/src/*.py",))
        assert set(r.paths) == {"/data/src/app.py", "/other/src/main.py"}

    async def test_globs_positive_mixed_exact_and_ambiguous(self, two_mounts):
        """If one positive glob needs router-side filtering, the router
        must still preserve matches from the other exact-rewrite positive
        globs on the same mount."""
        router, _, _ = two_mounts
        r = await router.grep("print", globs=("/data/src/*.py", "/**/main.py"))
        assert set(r.paths) == {"/data/src/app.py", "/other/src/main.py"}


# =========================================================================
# Wildcarded mount-selector segments
# =========================================================================


class TestWildcardMountSelectors:
    """The first absolute segment of a glob can use ``*``, ``?``, or
    character classes to select the mount. The router must consume the
    matching mount(s), not skip them."""

    async def test_star_selects_mount(self, wildcard_mount_router):
        router, _ = wildcard_mount_router
        r = await router.glob("/*/src/*.py")
        assert set(r.paths) == {"/data/src/app.py", "/data/src/util.py"}

    async def test_question_mark_selects_mount(self, wildcard_mount_router):
        router, _ = wildcard_mount_router
        r = await router.glob("/da?a/src/*.py")
        assert set(r.paths) == {"/data/src/app.py", "/data/src/util.py"}

    async def test_char_class_selects_mount(self, wildcard_mount_router):
        router, _ = wildcard_mount_router
        r = await router.glob("/d[ae]ta/**/*.py")
        assert set(r.paths) == {
            "/data/src/app.py",
            "/data/src/util.py",
            "/data/src/sub/deep.py",
        }

    async def test_negated_char_class_skips_mount(self, wildcard_mount_router):
        """``/d[!a]ta`` excludes ``data`` — should not match."""
        router, _ = wildcard_mount_router
        r = await router.glob("/d[!a]ta/**/*.py")
        assert r.paths == ()

    async def test_star_at_root_with_two_mounts(self, two_mounts):
        """``/*/src/*.py`` should reach both ``/data`` and ``/other``."""
        router, _, _ = two_mounts
        r = await router.glob("/*/src/*.py")
        assert set(r.paths) == {
            "/data/src/app.py",
            "/data/src/util.py",
            "/other/src/main.py",
        }

    async def test_double_star_at_root_reaches_mounts(self, two_mounts):
        """``/**/*.md`` (absolute, ``**``-leading) must use the safe
        superset + router-side post-filter path and still find files
        inside mounts."""
        router, _, _ = two_mounts
        r = await router.glob("/**/*.md")
        assert {
            "/data/readme.md",
            "/data/docs/guide.md",
            "/data/docs/deep/nested.md",
            "/other/notes.md",
        } <= set(r.paths)

    async def test_invalid_double_star_pattern_still_errors(self, wildcard_mount_router):
        """The safe-superset fallback must not turn a malformed absolute
        glob into a successful broad match."""
        router, _ = wildcard_mount_router
        r = await router.glob("/**/[z-a].py")
        assert not r.success
        assert "Invalid glob pattern" in r.error_message


# =========================================================================
# Storageful root + mount
# =========================================================================


class TestStoragefulRootWithMount:
    """``DatabaseFileSystem`` as the root with a mount underneath.

    Exercises the ``_route_fanout`` branch where ``self._storage`` is
    True — root self-query + mount fanout merge — which the
    ``VirtualFileSystem`` fixtures don't cover.
    """

    async def test_root_only_pattern_does_not_leak_mount(self, storageful_root_with_mount):
        root, _ = storageful_root_with_mount
        r = await root.glob("/lib/**/*.py")
        assert set(r.paths) == {"/lib/util.py", "/lib/sub/deep.py"}

    async def test_mount_only_pattern_does_not_leak_root(self, storageful_root_with_mount):
        root, _ = storageful_root_with_mount
        r = await root.glob("/data/**/*.py")
        assert set(r.paths) == {"/data/src/app.py", "/data/src/sub/inner.py"}

    async def test_recursive_pattern_spans_root_and_mount(self, storageful_root_with_mount):
        """``**/*.py`` should return matches from both root storage and
        the mount, with no duplicates from ``_exclude_mounted_paths``."""
        root, _ = storageful_root_with_mount
        r = await root.glob("**/*.py")
        assert set(r.paths) == {
            "/lib/util.py",
            "/lib/sub/deep.py",
            "/data/src/app.py",
            "/data/src/sub/inner.py",
        }

    async def test_grep_paths_against_root_only(self, storageful_root_with_mount):
        root, _ = storageful_root_with_mount
        r = await root.grep("util", paths=("/lib",))
        assert set(r.paths) == {"/lib/util.py"}

    async def test_grep_paths_split_root_and_mount(self, storageful_root_with_mount):
        root, _ = storageful_root_with_mount
        r = await root.grep("i", paths=("/lib", "/data/src"))
        # Both branches should be reachable; spot-check that paths from
        # both root and mount appear.
        assert any(p.startswith("/lib") for p in r.paths)
        assert any(p.startswith("/data/src") for p in r.paths)


# =========================================================================
# Deep nested chain — VirtualFileSystem → router → router → leaf
# =========================================================================


class TestDeepChainMounts:
    """Three-hop chain. Each level strips its own single-segment mount
    prefix; recursion handles the rest. Both glob and grep must work
    through the full chain."""

    async def test_glob_through_deep_chain_absolute(self, deep_chain_mounts):
        outer, _ = deep_chain_mounts
        r = await outer.glob("/a/b/c/**/*.py")
        assert set(r.paths) == {
            "/a/b/c/src/app.py",
            "/a/b/c/src/util.py",
            "/a/b/c/src/sub/deep.py",
        }

    async def test_glob_through_deep_chain_subtree(self, deep_chain_mounts):
        outer, _ = deep_chain_mounts
        r = await outer.glob("/a/b/c/src/*.py")
        assert set(r.paths) == {
            "/a/b/c/src/app.py",
            "/a/b/c/src/util.py",
        }

    async def test_glob_through_deep_chain_relative_pattern(self, deep_chain_mounts):
        """``**/*.py`` (no leading slash) should still reach the leaf."""
        outer, _ = deep_chain_mounts
        r = await outer.glob("**/*.py")
        assert set(r.paths) == {
            "/a/b/c/src/app.py",
            "/a/b/c/src/util.py",
            "/a/b/c/src/sub/deep.py",
        }

    async def test_glob_through_deep_chain_partial_prefix_skips(self, deep_chain_mounts):
        """``/a/b/wrong/**`` should not return anything."""
        outer, _ = deep_chain_mounts
        r = await outer.glob("/a/b/wrong/**/*.py")
        assert r.paths == ()

    async def test_glob_through_deep_chain_wildcard_selectors(self, deep_chain_mounts):
        """Use wildcards at each level of the chain — the segment-aware
        consumer should match each hop's mount name."""
        outer, _ = deep_chain_mounts
        r = await outer.glob("/?/?/?/**/*.py")
        assert set(r.paths) == {
            "/a/b/c/src/app.py",
            "/a/b/c/src/util.py",
            "/a/b/c/src/sub/deep.py",
        }

    async def test_grep_through_deep_chain_absolute(self, deep_chain_mounts):
        outer, _ = deep_chain_mounts
        r = await outer.grep("app", paths=("/a/b/c/src",))
        assert set(r.paths) == {"/a/b/c/src/app.py"}

    async def test_grep_through_deep_chain_globs(self, deep_chain_mounts):
        outer, _ = deep_chain_mounts
        r = await outer.grep("e", globs=("/a/b/c/**/*.py",))
        assert set(r.paths) == {"/a/b/c/src/sub/deep.py"}

    async def test_grep_through_deep_chain_globs_not(self, deep_chain_mounts):
        outer, _ = deep_chain_mounts
        # Exclude util.py via a wildcard-selector glob_not — must enforce
        # after rebase.
        r = await outer.grep("u", globs_not=("/*/*/*/src/util.py",))
        assert "/a/b/c/src/util.py" not in set(r.paths)

    async def test_leaf_stores_fully_relative_paths(self, deep_chain_mounts):
        """Sanity: the leaf at the bottom of the chain stores paths as
        ``/src/...``, not ``/a/b/c/src/...``."""
        _outer, leaf = deep_chain_mounts
        async with leaf._use_session() as s:
            r = await leaf._glob_impl(pattern="/**/*.py", session=s)
        assert set(r.paths) == {
            "/src/app.py",
            "/src/util.py",
            "/src/sub/deep.py",
        }


# =========================================================================
# Cross-mount candidate dispatch
# =========================================================================


class TestCrossMountCandidates:
    """``glob`` / ``grep`` invoked with ``candidates=`` whose paths cross
    mount boundaries.

    Regression for the second-pass fix in ``_dispatch_candidates``: the
    router must filter absolute candidate paths against the original
    pattern / structural filters BEFORE grouping by terminal, then call
    each terminal's ``_*_impl`` with mount-relative candidates and a
    no-op ``pattern="**"`` (glob) or empty structural filters (grep).
    Without this, the absolute pattern reaches the terminal and never
    matches the mount-relative candidate paths.
    """

    async def test_glob_candidates_cross_mount_filtered_at_router(self, two_mounts):
        router, _, _ = two_mounts
        seeds = await router.glob("**/*")
        assert any(p.startswith("/data") for p in seeds.paths)
        assert any(p.startswith("/other") for p in seeds.paths)

        r = await router.glob("/data/**/*.py", candidates=seeds)
        assert set(r.paths) == {"/data/src/app.py", "/data/src/util.py"}

    async def test_glob_candidates_with_paths_filter_under_mount(self, two_mounts):
        router, _, _ = two_mounts
        seeds = await router.glob("**/*")
        r = await router.glob("**/*.py", paths=("/data/src",), candidates=seeds)
        assert set(r.paths) == {"/data/src/app.py", "/data/src/util.py"}

    async def test_glob_candidates_wildcard_mount_selector(self, two_mounts):
        router, _, _ = two_mounts
        seeds = await router.glob("**/*")
        r = await router.glob("/*/src/*.py", candidates=seeds)
        assert set(r.paths) == {
            "/data/src/app.py",
            "/data/src/util.py",
            "/other/src/main.py",
        }

    async def test_grep_candidates_cross_mount_with_globs(self, two_mounts):
        router, _, _ = two_mounts
        seeds = await router.glob("**/*.py")
        r = await router.grep("print", globs=("/data/**/*.py",), candidates=seeds)
        assert set(r.paths) == {"/data/src/app.py"}

    async def test_grep_candidates_cross_mount_with_globs_not(self, two_mounts):
        router, _, _ = two_mounts
        seeds = await router.glob("**/*.py")
        r = await router.grep("print", globs_not=("/data/**/*.py",), candidates=seeds)
        assert set(r.paths) == {"/other/src/main.py"}

    async def test_grep_candidates_cross_mount_paths_positional(self, two_mounts):
        router, _, _ = two_mounts
        seeds = await router.glob("**/*.py")
        r = await router.grep("print", paths=("/other",), candidates=seeds)
        assert set(r.paths) == {"/other/src/main.py"}

    async def test_glob_candidates_invalid_pattern_errors(self, two_mounts):
        router, _, _ = two_mounts
        seeds = await router.glob("**/*")
        r = await router.glob("/**/[z-a].py", candidates=seeds)
        assert not r.success
        assert "Invalid glob pattern" in r.error_message

    async def test_glob_candidates_through_deep_chain(self, deep_chain_mounts):
        outer, _ = deep_chain_mounts
        seeds = await outer.glob("**/*")
        r = await outer.glob("/a/b/c/src/*.py", candidates=seeds)
        assert set(r.paths) == {
            "/a/b/c/src/app.py",
            "/a/b/c/src/util.py",
        }
