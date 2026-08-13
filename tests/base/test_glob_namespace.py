"""Namespace-coordinate glob over real storages — the placement-invariance law.

The dispatch tests prove which mounts receive which patterns with
doubles; these rows prove the *results* over real entries: the same
logical tree returns the same rows for the same call whether a subtree
is plain directories or a mount. Row sets are compared sorted — row
*order* is the fan-out merge order (entries in table order), a
pre-existing contract placement does change.
"""

from __future__ import annotations

import pytest

from tests.support.base_doubles import RecorderStorage
from vfs.base import VirtualFileSystem
from vfs.models import Observation
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage.backends.memory import InMemoryStorage

# The demo tree: /notes.txt at the root, a.txt and deep/b.txt under /data.
TREE = (("/notes.txt", "root"), ("/data/a.txt", "a"), ("/data/deep/b.txt", "b"))

INVARIANCE_BATTERY = (
    "*.txt",  # name arm
    "b.txt",  # name arm, mount-interior row
    "/data/*.txt",  # anchored, direct children
    "/data/**/*.txt",  # ** spanning the seam
    "**/*.txt",  # explicit any-depth
    "*/a.txt",  # depth pin across the seam
    "**/**/*.txt",  # adjacent ** canonicalizes; the derivative stays exact
    "/docs/*.md",  # dead prefix: nothing anywhere
    "/d*",  # the bind-point / plain-directory row itself
    "*.{txt,md}",  # brace alternation, name arms
    "/data/{deep,api}/*.txt",  # brace alternation across the seam
    "{/data/deep/*.txt,notes.*}",  # mixed-subject arms: one anchored, one floating
)


async def _plain_world() -> VirtualFileSystem:
    fs = VirtualFileSystem()
    for path, content in TREE:
        await fs.write(path=path, content=content, parents=True)
    return fs


async def _mounted_world() -> VirtualFileSystem:
    fs = VirtualFileSystem()
    await fs.write(path="/notes.txt", content="root")
    await fs.add_mount(InMemoryStorage(), "/data")
    await fs.write(path="/data/a.txt", content="a")
    await fs.write(path="/data/deep/b.txt", content="b", parents=True)
    return fs


async def test_the_headline_repro_flips() -> None:
    # The motivating bug: these two calls returned empty success while
    # the rows sat in the /data mount.
    fs = await _mounted_world()
    both = await fs.glob("/data/**/*.txt")
    assert sorted(both.paths) == ["/data/a.txt", "/data/deep/b.txt"]
    direct = await fs.glob("/data/*.txt")
    assert direct.paths == ("/data/a.txt",)


@pytest.mark.parametrize("pattern", INVARIANCE_BATTERY)
async def test_mount_placement_is_invisible_to_patterns(pattern: str) -> None:
    plain = await (await _plain_world()).glob(pattern)
    mounted = await (await _mounted_world()).glob(pattern)
    assert plain.success is True and mounted.success is True
    assert sorted(plain.paths) == sorted(mounted.paths)


async def test_scoped_patterns_read_root_relative() -> None:
    # Three spellings of the same question — including the deliberate
    # contract change: a leading slash anchors at the scope root.
    fs = await _mounted_world()
    absolute = await fs.glob("/data/deep/*.txt")
    scoped = await fs.glob("deep/*.txt", paths=("/data",))
    anchored = await fs.glob("/deep/*.txt", paths=("/data",))
    assert absolute.paths == scoped.paths == anchored.paths == ("/data/deep/b.txt",)


async def test_double_star_spans_a_nested_mount_boundary() -> None:
    fs = await _mounted_world()
    await fs.add_mount(InMemoryStorage(), "/data/api")
    await fs.write(path="/data/api/y.txt", content="y")
    spanning = await fs.glob("/data/**/*.txt")
    assert sorted(spanning.paths) == ["/data/a.txt", "/data/api/y.txt", "/data/deep/b.txt"]


async def test_multi_residual_rows_arrive_exactly_once() -> None:
    # ** either spans the nested bind segment or stops before it: two
    # dispatches to /data/api whose overlap must merge to one row.
    fs = await _mounted_world()
    await fs.add_mount(InMemoryStorage(), "/data/api")
    await fs.write(path="/data/api/y.txt", content="y")
    result = await fs.glob("/data/**/api/*.txt")
    assert result.paths == ("/data/api/y.txt",)


async def test_bind_point_row_is_served_by_the_parent() -> None:
    # /d* exhausts at the bind point: the match is the parent's stored
    # mount-point directory, and the mount itself is never dispatched.
    fs = VirtualFileSystem()
    recorder = RecorderStorage()
    await fs.add_mount(recorder, "/data")
    result = await fs.glob("/d*")
    assert result.paths == ("/data",)
    assert recorder.calls == []


async def test_multiple_roots_into_one_entry_all_serve() -> None:
    # Every scope root must reach the batch: a regression that drops
    # roots after the first per entry loses rows, not duplicates them.
    plain = await (await _plain_world()).glob("**/*.txt", paths=("/data", "/data/deep"))
    mounted = await (await _mounted_world()).glob("**/*.txt", paths=("/data", "/data/deep"))
    assert sorted(plain.paths) == sorted(mounted.paths) == ["/data/a.txt", "/data/deep/b.txt"]
    assert len(mounted.paths) == len(set(mounted.paths))


async def test_max_count_returns_a_merge_order_prefix_of_the_set() -> None:
    # The invariance law binds the match *set*; a cap keeps merge order,
    # which mount layout can reorder — pinned as prefix-of-set semantics.
    for world in (await _plain_world(), await _mounted_world()):
        full = await world.glob("**/*.txt")
        capped = await world.glob("**/*.txt", max_count=2)
        assert len(capped.paths) == 2
        assert set(capped.paths) <= set(full.paths)


async def test_name_arm_root_covered_by_a_region_keeps_its_assertion() -> None:
    # A bogus root fails loud even when a sibling region covers its entry:
    # subsumption must not drop the find-operand assertion with the dispatch.
    fs = await _mounted_world()
    await fs.add_mount(InMemoryStorage(), "/data/api")
    await fs.write(path="/data/api/sub/z.txt", content="z", parents=True)
    missing = await fs.glob("*.txt", paths=("/data", "/data/api/nope"))
    assert missing.success is False
    assert missing.errors[0].kind is VFSErrorKind.not_found
    both = await fs.glob("*.txt", paths=("/data", "/data/api/sub"))
    assert both.success is True
    assert sorted(both.paths) == ["/data/a.txt", "/data/api/sub/z.txt", "/data/deep/b.txt"]
    assert len(both.paths) == len(set(both.paths))  # probe and batch overlap; the merge dedups


async def test_scoped_name_arm_still_hits_direct_children() -> None:
    # The float made spatial must lose nothing: root + /**/ + pattern
    # matches direct children because ** spans zero segments.
    for world in (await _plain_world(), await _mounted_world()):
        result = await world.glob("*.txt", paths=("/data",))
        assert sorted(result.paths) == ["/data/a.txt", "/data/deep/b.txt"]


async def test_root_order_does_not_change_the_answer() -> None:
    # The ripgrep multi-root regression class: the same call with roots
    # in both orders returns the same set and the same per-root errors.
    fs = await _mounted_world()
    forward = await fs.glob("*.txt", paths=("/data", "/data/deep", "/missing"))
    reverse = await fs.glob("*.txt", paths=("/missing", "/data/deep", "/data"))
    assert sorted(forward.paths) == sorted(reverse.paths)
    assert forward.success is False and reverse.success is False
    assert [(e.kind, e.path) for e in forward.failures] == [(e.kind, e.path) for e in reverse.failures]


async def test_a_matching_directory_root_row_is_served_from_the_probe() -> None:
    # find parity the anchor channel missed: a directory operand whose
    # own row matches the pattern appears, served by the probe.
    fs = await _mounted_world()
    result = await fs.glob("d*", paths=("/data/deep",))
    assert result.paths == ("/data/deep",)


async def test_roots_stay_assertions() -> None:
    # A pattern matching nothing is clean empty success; a missing root
    # is a loud per-root error; a file root is matched itself.
    fs = await _mounted_world()
    empty = await fs.glob("/data/nothing/*.rs")
    assert empty.success is True and empty.paths == ()
    missing = await fs.glob("**/*.txt", paths=("/missing",))
    assert missing.success is False
    assert missing.errors[0].kind is VFSErrorKind.not_found
    hit = await fs.glob("*.txt", paths=("/notes.txt",))
    assert hit.paths == ("/notes.txt",)
    miss = await fs.glob("*.py", paths=("/notes.txt",))
    assert miss.success is True and miss.paths == ()


# ----------------------------------------------------------------------
# Metachar roots — a scope root is a path, never glob syntax
# ----------------------------------------------------------------------

METACHAR_ROOT_NAMES = ("[x]", "{a}", "a*b", "c?d", "data [prod]")


async def test_metachar_roots_serve_exactly_their_own_subtree() -> None:
    # The regression class: an unquoted root spliced into pattern text
    # captured siblings ([x] served /x) or refused whole calls ({a}).
    for fs in (await _plain_world(), await _mounted_world()):
        for name in METACHAR_ROOT_NAMES:
            await fs.write(path=f"/data/{name}/hit.txt", content="hit", parents=True)
        await fs.write(path="/data/x/decoy.txt", content="decoy", parents=True)
        await fs.write(path="/data/ab/decoy.txt", content="decoy", parents=True)
        for name in METACHAR_ROOT_NAMES:
            result = await fs.glob("*.txt", paths=(f"/data/{name}",))
            assert result.success is True, (name, result.errors)
            assert result.paths == (f"/data/{name}/hit.txt",), name


async def test_every_root_sees_exactly_its_prefix_subtree() -> None:
    # Property shape: for any legal path p, glob("**", paths=(p,)) is
    # exactly p's subtree — p's own row included, nothing beside it.
    fs = await _plain_world()
    for name in METACHAR_ROOT_NAMES:
        await fs.write(path=f"/m/{name}/deep/d.txt", content="x", parents=True)
    everything = sorted((await fs.glob("**")).paths)
    for root in everything:
        scoped = await fs.glob("**", paths=(root,))
        assert scoped.success is True, root
        expected = [p for p in everything if p == root or p.startswith(root + "/")]
        assert sorted(scoped.paths) == expected, root


# ----------------------------------------------------------------------
# Brace alternation — arms expand at the chokepoint, results union
# ----------------------------------------------------------------------


async def test_brace_arms_union_across_the_namespace() -> None:
    fs = await _mounted_world()
    result = await fs.glob("/data/{a,deep/b}.txt")
    assert sorted(result.paths) == ["/data/a.txt", "/data/deep/b.txt"]


async def test_brace_expansion_past_the_cap_refuses_loudly() -> None:
    fs = await _mounted_world()
    result = await fs.glob("{a,b}{c,d}{e,f}{g,h}{i,j}{k,l}{m,n}")  # 128 arms
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.invalid
    assert "arm cap" in result.errors[0].message


async def test_brace_defect_refuses_naming_the_manufactured_arm() -> None:
    fs = await _mounted_world()
    result = await fs.glob("/data/{deep,}/b.txt")
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.invalid
    assert "'/data//b.txt'" in result.errors[0].message


async def test_grep_glob_channels_expand_braces() -> None:
    # The subject is channel expansion; allow_scan sidesteps the index
    # tier's refusal gate for the short unindexable pattern.
    fs = await _mounted_world()
    result = await fs.grep("a|b|root", globs=("*.{txt,md}",), allow_scan=True)
    assert sorted(result.paths) == ["/data/a.txt", "/data/deep/b.txt", "/notes.txt"]
    excluded = await fs.grep("a|b|root", globs_not=("{notes,b}.*",), allow_scan=True)
    assert excluded.paths == ("/data/a.txt",)


# ----------------------------------------------------------------------
# Exclusion channels and the kind filter — rejection honors every gate
# ----------------------------------------------------------------------


async def test_globs_not_excludes_in_both_worlds() -> None:
    for world in (await _plain_world(), await _mounted_world()):
        by_path = await world.glob("**/*.txt", globs_not=("/data/deep/**",))
        assert sorted(by_path.paths) == ["/data/a.txt", "/notes.txt"]
        by_name = await world.glob("*.txt", globs_not=("{a,b}.txt",))
        assert by_name.paths == ("/notes.txt",)


async def test_scoped_exclusion_composes_under_its_root() -> None:
    # "deep/**" is root-relative: it excludes /data/deep/** under the
    # /data root, exactly as the admission pattern would anchor.
    fs = await _mounted_world()
    result = await fs.glob("**/*.txt", paths=("/data",), globs_not=("deep/**",))
    assert result.paths == ("/data/a.txt",)


async def test_ext_not_drops_extensions_normalized() -> None:
    # ext_not drops only the named extensions — an extensionless row
    # (the directory) is never its business.
    fs = await _mounted_world()
    await fs.write(path="/data/readme.md", content="m")
    result = await fs.glob("/data/*", ext_not=(".TXT",))
    assert sorted(result.paths) == ["/data/deep", "/data/readme.md"]


async def test_kind_filters_files_and_directories() -> None:
    fs = await _mounted_world()
    directories = await fs.glob("**", kind="directory")
    assert sorted(directories.paths) == ["/data", "/data/deep"]
    files = await fs.glob("/data/**", kind="file")
    assert sorted(files.paths) == ["/data/a.txt", "/data/deep/b.txt"]


async def test_exclusion_never_reveals_meta() -> None:
    fs = await _mounted_world()
    result = await fs.glob("**", globs_not=("**/*.txt",))
    assert not any(str(path).startswith("/.vfs") for path in result.paths)


async def test_root_row_service_honors_every_channel() -> None:
    # The find-operand law serves a matching root's own row — unless an
    # exclusion glob, ext fact, or kind fact the caller stated rejects it.
    fs = await _mounted_world()
    served = await fs.glob("*.txt", paths=("/data/a.txt",))
    assert "/data/a.txt" in served.paths
    excluded = await fs.glob("*.txt", paths=("/data/a.txt",), globs_not=("a.*",))
    assert "/data/a.txt" not in excluded.paths
    wrong_ext = await fs.glob("*", paths=("/data/a.txt",), ext_not=("txt",))
    assert "/data/a.txt" not in wrong_ext.paths
    wrong_kind = await fs.glob("*", paths=("/data/a.txt",), kind="directory")
    assert "/data/a.txt" not in wrong_kind.paths


# ----------------------------------------------------------------------
# Chaining — observations are rows in hand, filtered without dispatch
# ----------------------------------------------------------------------


async def test_chained_glob_applies_exclusions_and_ext_not_in_memory() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/src/a.py")),
        Observation(path=Path("/src/tests/t.py")),
        Observation(path=Path("/src/b.pyc")),
    ]
    excluded = await fs.glob("**/*", observations=rows, globs_not=("/src/tests/**",))
    assert [str(o.path) for o in excluded.observations] == ["/src/a.py", "/src/b.pyc"]
    by_ext = await fs.glob("**/*", observations=rows, ext_not=("pyc",))
    assert [str(o.path) for o in by_ext.observations] == ["/src/a.py", "/src/tests/t.py"]


async def test_chained_kind_filters_on_the_held_fact_without_storage() -> None:
    # Rows that carry kind are judged as held — storage sees no call.
    fs = VirtualFileSystem()
    recorder = RecorderStorage()
    await fs.add_mount(recorder, "/data")
    rows = [
        Observation(path=Path("/data/f.txt"), kind="file", populated=frozenset({"path", "kind"})),
        Observation(path=Path("/data/d"), kind="directory", populated=frozenset({"path", "kind"})),
    ]
    result = await fs.glob("**", observations=rows, kind="file")
    assert [str(o.path) for o in result.observations] == ["/data/f.txt"]
    assert recorder.calls == []


async def test_chained_kind_fetches_only_the_lacking_rows() -> None:
    # A hand-built row carries no kind: the load-bearing fact is
    # statted in one batch and the filter judges the fetched value.
    fs = await _mounted_world()
    rows = [Observation(path=Path("/data/a.txt")), Observation(path=Path("/data/deep"))]
    files = await fs.glob("**", observations=rows, kind="file")
    assert files.success is True
    assert [str(o.path) for o in files.observations] == ["/data/a.txt"]
    directories = await fs.glob("**", observations=rows, kind="directory")
    assert [str(o.path) for o in directories.observations] == ["/data/deep"]


async def test_chained_kind_on_a_vanished_row_classifies_loudly() -> None:
    fs = await _mounted_world()
    rows = [Observation(path=Path("/data/a.txt")), Observation(path=Path("/data/gone.txt"))]
    result = await fs.glob("**", observations=rows, kind="file")
    assert [str(o.path) for o in result.observations] == ["/data/a.txt"]
    assert result.success is False
    assert any(e.kind == VFSErrorKind.not_found for e in result.errors)


async def test_chained_without_kind_never_touches_storage() -> None:
    # The fetch exists only for the kind fact; plain chaining stays pure.
    fs = VirtualFileSystem()
    recorder = RecorderStorage()
    await fs.add_mount(recorder, "/data")
    rows = [Observation(path=Path("/data/a.txt"))]
    result = await fs.glob("**", observations=rows, globs_not=("*.md",), ext_not=("py",))
    assert [str(o.path) for o in result.observations] == ["/data/a.txt"]
    assert recorder.calls == []


async def test_chained_glob_matches_any_brace_arm() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/src/a.ts")),
        Observation(path=Path("/src/b.tsx")),
        Observation(path=Path("/src/c.css")),
    ]
    result = await fs.glob("*.{ts,tsx}", observations=rows)
    assert [str(o.path) for o in result.observations] == ["/src/a.ts", "/src/b.tsx"]


async def test_chained_glob_filters_rows_in_hand_without_storage() -> None:
    # Pure filter: rows pass or drop on their held paths alone — the
    # rows here exist nowhere in storage, and duplicates survive.
    fs = VirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/keep/a.txt")),
        Observation(path=Path("/drop/b.md")),
        Observation(path=Path("/keep/a.txt")),
    ]
    result = await fs.glob("*.txt", observations=rows)
    assert result.success is True
    assert [str(o.path) for o in result.observations] == ["/keep/a.txt", "/keep/a.txt"]


async def test_chained_glob_path_arm_anchors_and_ext_applies() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/src/a.py")),
        Observation(path=Path("/lib/b.py")),
        Observation(path=Path("/src/c.txt")),
    ]
    anchored = await fs.glob("/src/*", observations=rows)
    assert [str(o.path) for o in anchored.observations] == ["/src/a.py", "/src/c.txt"]
    by_ext = await fs.glob("*", observations=rows, ext=("py",))
    assert [str(o.path) for o in by_ext.observations] == ["/src/a.py", "/lib/b.py"]


async def test_chained_glob_never_hides_meta_rows_in_hand() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    rows = [Observation(path=Path("/.vfs/trash/x"))]
    result = await fs.glob("*", observations=rows)
    assert [str(o.path) for o in result.observations] == ["/.vfs/trash/x"]
