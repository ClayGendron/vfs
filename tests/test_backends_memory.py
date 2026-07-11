"""Backend contract for ``InMemoryStorage`` — called directly, no router.

Exercises the dict-backed reference backend against the ``StorageBackend``
contract: identity, the POSIX parent/site rules, read/ls/tree shapes,
move/copy subtree semantics, edit/delete atomicity, glob/grep modes, the
``allow_files=False`` directories-only mode, ``mkedge``, and the per-row
classification of batched reads.
"""

from __future__ import annotations

from vfs.models import Entry, Observation
from vfs.ops import MUTATING_OPS
from vfs.paths import Path, edge_out_path
from vfs.results import VFSErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.replace import EditOperation

# ----------------------------------------------------------------------
# Identity and capabilities
# ----------------------------------------------------------------------


def test_default_identity() -> None:
    storage = InMemoryStorage()
    assert storage.name == "memory"
    assert storage.description == "In-memory storage"


def test_constructor_kwargs_override_identity() -> None:
    storage = InMemoryStorage(name="scratch", description="Scratch namespace")
    assert storage.name == "scratch"
    assert storage.description == "Scratch namespace"


def test_capabilities_are_read_pattern_search_and_mutation_only() -> None:
    storage = InMemoryStorage()
    caps = storage.capabilities()
    assert caps == frozenset({"read", "stat", "ls", "tree", "glob", "grep"}) | MUTATING_OPS
    assert "glean" not in caps
    assert "graph" not in caps
    assert "run" not in caps


def test_capabilities_are_identical_regardless_of_allow_files() -> None:
    # Capability speaks ops, not per-kind guarantees.
    assert InMemoryStorage(allow_files=True).capabilities() == InMemoryStorage(allow_files=False).capabilities()


# ----------------------------------------------------------------------
# POSIX parent/site rules — write and mkdir
# ----------------------------------------------------------------------


async def test_write_without_parents_missing_ancestor_is_not_found() -> None:
    storage = InMemoryStorage()
    result = await storage.write(path=Path("/a/b/c.txt"), content="hi")
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.not_found
    assert result.errors[0].path == "/a"


async def test_write_with_parents_mints_the_missing_chain() -> None:
    storage = InMemoryStorage()
    result = await storage.write(path=Path("/a/b/c.txt"), content="hi", parents=True)
    assert result.success is True
    assert result.observations[0].status == "created"
    # The minted ancestors are not echoed on this result, but they now exist.
    ancestor = await storage.stat(path=Path("/a/b"))
    assert ancestor.success is True
    assert ancestor.observations[0].kind == "directory"


async def test_mkdir_with_parents_reports_every_created_ancestor() -> None:
    storage = InMemoryStorage()
    result = await storage.mkdir(path=Path("/a/b/c"), parents=True)
    assert result.success is True
    assert [o.path for o in result.observations] == ["/a", "/a/b", "/a/b/c"]
    assert all(o.status == "created" for o in result.observations)


async def test_mkdir_without_parents_missing_ancestor_is_not_found() -> None:
    storage = InMemoryStorage()
    result = await storage.mkdir(path=Path("/a/b"))
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.not_found
    assert result.errors[0].path == "/a"


async def test_ancestor_stored_as_a_file_is_wrong_kind_without_parents() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/f"), content="x")
    result = await storage.write(path=Path("/f/sub.txt"), content="x")
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.wrong_kind
    assert result.errors[0].path == "/f"


async def test_ancestor_stored_as_a_file_is_wrong_kind_even_with_parents() -> None:
    # Unconditional: parents=True mints missing ancestors, it never coerces one.
    storage = InMemoryStorage()
    await storage.write(path=Path("/f"), content="x")
    result = await storage.mkdir(path=Path("/f/sub"), parents=True)
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.wrong_kind
    assert result.errors[0].path == "/f"


async def test_mkdir_on_occupied_site_is_exists() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a"))
    result = await storage.mkdir(path=Path("/a"))
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.exists


async def test_mkdir_exist_ok_on_a_directory_occupant_is_unchanged() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a"))
    result = await storage.mkdir(path=Path("/a"), exist_ok=True)
    assert result.success is True
    assert result.observations[0].status == "unchanged"


async def test_mkdir_exist_ok_on_a_file_occupant_still_exists() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a"), content="x")
    result = await storage.mkdir(path=Path("/a"), exist_ok=True)
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.exists


# ----------------------------------------------------------------------
# ls / read / tree semantics
# ----------------------------------------------------------------------


async def test_ls_directory_lists_children() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a"))
    await storage.write(path=Path("/a/f.txt"), content="x")
    result = await storage.ls(path=Path("/a"))
    assert result.success is True
    assert [o.path for o in result.observations] == ["/a/f.txt"]


async def test_ls_file_lists_itself() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="x")
    result = await storage.ls(path=Path("/a.txt"))
    assert result.success is True
    assert result.observations[0].path == "/a.txt"


async def test_ls_missing_is_not_found() -> None:
    storage = InMemoryStorage()
    result = await storage.ls(path=Path("/nope"))
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.not_found


async def test_read_on_a_directory_is_wrong_kind() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a"))
    result = await storage.read(path=Path("/a"))
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.wrong_kind


async def test_tree_max_depth_budgets_the_subtree() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a/b/c"), parents=True)
    await storage.write(path=Path("/a/b/c/d.txt"), content="x")

    shallow = await storage.tree(path=Path("/a"), max_depth=1)
    assert [o.path for o in shallow.observations] == ["/a/b"]

    deeper = await storage.tree(path=Path("/a"), max_depth=2)
    assert [o.path for o in deeper.observations] == ["/a/b", "/a/b/c"]

    full = await storage.tree(path=Path("/a"))
    assert [o.path for o in full.observations] == ["/a/b", "/a/b/c", "/a/b/c/d.txt"]


async def test_tree_on_a_file_returns_just_that_row() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="x")
    result = await storage.tree(path=Path("/a.txt"))
    assert [o.path for o in result.observations] == ["/a.txt"]


async def test_tree_rejects_a_sub_one_max_depth() -> None:
    storage = InMemoryStorage()
    result = await storage.tree(path=Path("/"), max_depth=0)
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.invalid


async def test_tree_missing_is_not_found() -> None:
    storage = InMemoryStorage()
    result = await storage.tree(path=Path("/nope"))
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.not_found


async def test_stat_row_shapes() -> None:
    storage = InMemoryStorage()
    await storage.write(entries=[Entry(path=Path("/a.txt"), content="hello")])
    file_row = (await storage.stat(path=Path("/a.txt"))).observations[0]
    assert file_row.kind == "file"
    assert file_row.content is None  # stat never carries content
    assert file_row.size_bytes == len(b"hello")

    await storage.mkdir(path=Path("/d"))
    dir_row = (await storage.stat(path=Path("/d"))).observations[0]
    assert dir_row.kind == "directory"
    assert dir_row.size_bytes is None


# ----------------------------------------------------------------------
# move / copy subtree semantics
# ----------------------------------------------------------------------


async def test_move_rewrites_the_subtree_prefix() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a"))
    await storage.write(path=Path("/a/x.txt"), content="x")
    result = await storage.move(operations=[ResolvedPair(src=Path("/a"), dest=Path("/b"))])
    assert result.success is True
    assert (await storage.stat(path=Path("/a"))).success is False
    assert (await storage.stat(path=Path("/b"))).success is True
    assert (await storage.stat(path=Path("/b/x.txt"))).success is True


async def test_copy_rewrites_the_subtree_prefix_and_keeps_the_source() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a"))
    await storage.write(path=Path("/a/x.txt"), content="x")
    result = await storage.copy(operations=[ResolvedPair(src=Path("/a"), dest=Path("/b"))])
    assert result.success is True
    assert (await storage.stat(path=Path("/a/x.txt"))).success is True
    assert (await storage.stat(path=Path("/b/x.txt"))).success is True


async def test_move_into_itself_is_invalid() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a"))
    result = await storage.move(operations=[ResolvedPair(src=Path("/a"), dest=Path("/a/sub"))])
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.invalid


async def test_move_a_directory_onto_an_occupied_site_is_wrong_kind() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a"))
    await storage.write(path=Path("/c.txt"), content="x")
    result = await storage.move(operations=[ResolvedPair(src=Path("/a"), dest=Path("/c.txt"))])
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.wrong_kind


async def test_move_a_file_onto_a_directory_is_wrong_kind() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/f.txt"), content="x")
    await storage.mkdir(path=Path("/d"))
    result = await storage.move(operations=[ResolvedPair(src=Path("/f.txt"), dest=Path("/d"))])
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.wrong_kind


async def test_transfer_classifies_a_row_that_overflows_at_the_destination() -> None:
    # Both pair paths are individually valid; only a deep row's minted
    # destination exceeds the limit — refuse the pair, never raise.
    storage = InMemoryStorage()
    tail = "x" * 200 + ".txt"
    await storage.mkdir(path=Path("/d"))
    await storage.write(path=Path("/d/" + tail), content="deep")
    parent = "/" + "/".join(["p" * 200 for _ in range(4)])
    await storage.mkdir(path=Path(parent), parents=True)
    dest = Path(parent + "/" + "q" * 100)
    for op in (storage.move, storage.copy):
        result = await op(operations=[ResolvedPair(src=Path("/d"), dest=dest)])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unaddressable
    assert (await storage.read(path=Path("/d/" + tail))).success is True


async def test_move_batch_is_staged_atomic() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="x")
    operations = [
        ResolvedPair(src=Path("/a.txt"), dest=Path("/moved.txt")),
        ResolvedPair(src=Path("/missing.txt"), dest=Path("/also-moved.txt")),
    ]
    result = await storage.move(operations=operations)
    assert result.success is False
    # Nothing committed: the first pair's effect never lands.
    assert (await storage.stat(path=Path("/a.txt"))).success is True
    assert (await storage.stat(path=Path("/moved.txt"))).success is False


# ----------------------------------------------------------------------
# edit — sequential, atomic
# ----------------------------------------------------------------------


async def test_edit_applies_operations_sequentially() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="hello world")
    edits = [EditOperation(old="hello", new="hi"), EditOperation(old="hi world", new="hi there")]
    result = await storage.edit(edits=edits, path=Path("/a.txt"))
    assert result.success is True
    assert (await storage.read(path=Path("/a.txt"))).observations[0].content == "hi there"


async def test_edit_batch_is_atomic_on_a_failed_match() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="hello world")
    edits = [EditOperation(old="hello", new="hi"), EditOperation(old="nonexistent", new="x")]
    result = await storage.edit(edits=edits, path=Path("/a.txt"))
    assert result.success is False
    # The first edit's effect never lands either.
    assert (await storage.read(path=Path("/a.txt"))).observations[0].content == "hello world"


# ----------------------------------------------------------------------
# delete
# ----------------------------------------------------------------------


async def test_delete_root_is_invalid() -> None:
    storage = InMemoryStorage()
    result = await storage.delete(path=Path("/"))
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.invalid


async def test_delete_non_empty_directory_without_cascade_is_not_empty() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a"))
    await storage.write(path=Path("/a/f.txt"), content="x")
    result = await storage.delete(path=Path("/a"), cascade=False)
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.not_empty
    assert (await storage.stat(path=Path("/a/f.txt"))).success is True


async def test_delete_cascades_by_default() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a"))
    await storage.write(path=Path("/a/f.txt"), content="x")
    result = await storage.delete(path=Path("/a"))
    assert result.success is True
    assert (await storage.stat(path=Path("/a"))).success is False
    assert (await storage.stat(path=Path("/a/f.txt"))).success is False


async def test_delete_accepts_the_permanent_flag() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="x")
    result = await storage.delete(path=Path("/a.txt"), permanent=True)
    assert result.success is True
    assert (await storage.stat(path=Path("/a.txt"))).success is False


# ----------------------------------------------------------------------
# glob / grep
# ----------------------------------------------------------------------


async def test_glob_matches_by_name_without_a_slash_in_the_pattern() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a/b"), parents=True)
    await storage.write(path=Path("/a/b/x.py"), content="x")
    result = await storage.glob(pattern="x.py")
    assert [o.path for o in result.observations] == ["/a/b/x.py"]


async def test_glob_matches_full_path_when_pattern_has_a_slash() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a/b"), parents=True)
    await storage.write(path=Path("/a/b/x.py"), content="x")
    result = await storage.glob(pattern="*/x.py")
    assert [o.path for o in result.observations] == ["/a/b/x.py"]


async def test_glob_filters_by_extension() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.py"), content="x")
    await storage.write(path=Path("/a.txt"), content="x")
    result = await storage.glob(pattern="a.*", ext=("py",))
    assert [o.path for o in result.observations] == ["/a.py"]


async def test_glob_respects_max_count() -> None:
    storage = InMemoryStorage()
    for name in ("a.py", "b.py", "c.py"):
        await storage.write(path=Path(f"/{name}"), content="x")
    result = await storage.glob(pattern="*.py", max_count=2)
    assert len(result.observations) == 2


async def test_grep_default_case_mode_is_sensitive() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="hello world")
    result = await storage.grep(pattern="Hello")
    assert result.observations == []


async def test_grep_insensitive_case_mode_ignores_case() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="hello world")
    result = await storage.grep(pattern="HELLO", case_mode="insensitive")
    assert [o.path for o in result.observations] == ["/a.txt"]


async def test_grep_smart_case_mode_is_insensitive_for_a_lowercase_pattern() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="Hello World")
    result = await storage.grep(pattern="hello", case_mode="smart")
    assert [o.path for o in result.observations] == ["/a.txt"]


async def test_grep_fixed_strings_treats_the_pattern_literally() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/dot.txt"), content="a.b")
    await storage.write(path=Path("/any.txt"), content="axb")
    result = await storage.grep(pattern="a.b", fixed_strings=True)
    assert [o.path for o in result.observations] == ["/dot.txt"]


async def test_grep_word_regexp_matches_whole_words_only() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/whole.txt"), content="cat scratched")
    await storage.write(path=Path("/sub.txt"), content="concatenate")
    result = await storage.grep(pattern="cat", word_regexp=True)
    assert [o.path for o in result.observations] == ["/whole.txt"]


async def test_grep_invert_match_returns_non_matching_lines() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="keep\nmatch")
    result = await storage.grep(pattern="match", invert_match=True)
    matches = result.observations[0].matches
    assert matches is not None
    assert len(matches) == 1
    assert matches[0].content == "keep"


async def test_grep_output_mode_files_omits_content() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="needle")
    result = await storage.grep(pattern="needle", output_mode="files")
    row = result.observations[0]
    assert row.content is None
    assert row.matches is None


async def test_grep_output_mode_count_reports_match_count() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="needle\nneedle\nneedle")
    result = await storage.grep(pattern="needle", output_mode="count")
    row = result.observations[0]
    assert row.score == 3.0
    assert row.content is None


async def test_grep_max_count_limits_matches_per_row() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="needle\nneedle\nneedle")
    result = await storage.grep(pattern="needle", output_mode="count", max_count=1)
    assert result.observations[0].score == 1.0


# ----------------------------------------------------------------------
# allow_files=False — directories only
# ----------------------------------------------------------------------


async def test_write_content_is_unsupported_without_allow_files() -> None:
    storage = InMemoryStorage(allow_files=False)
    result = await storage.write(path=Path("/a.txt"), content="x")
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.unsupported
    assert "directories only" in result.errors[0].message


async def test_write_entries_file_kind_is_unsupported_without_allow_files() -> None:
    storage = InMemoryStorage(allow_files=False)
    result = await storage.write(entries=[Entry(path=Path("/a.txt"), kind="file", content="x")])
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.unsupported


async def test_edit_is_unsupported_without_allow_files() -> None:
    storage = InMemoryStorage(allow_files=False)
    result = await storage.edit(edits=[EditOperation(old="a", new="b")], path=Path("/a.txt"))
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.unsupported


async def test_mkedge_is_unsupported_without_allow_files() -> None:
    storage = InMemoryStorage(allow_files=False)
    result = await storage.mkedge(source=Path("/a"), target=Path("/b"), edge_type="imports")
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.unsupported


async def test_mkdir_still_works_without_allow_files() -> None:
    storage = InMemoryStorage(allow_files=False)
    result = await storage.mkdir(path=Path("/a"))
    assert result.success is True


async def test_directory_delete_and_move_still_work_without_allow_files() -> None:
    storage = InMemoryStorage(allow_files=False)
    await storage.mkdir(path=Path("/a"))
    moved = await storage.move(operations=[ResolvedPair(src=Path("/a"), dest=Path("/b"))])
    assert moved.success is True
    deleted = await storage.delete(path=Path("/b"))
    assert deleted.success is True


async def test_reads_and_name_glob_still_work_without_allow_files() -> None:
    storage = InMemoryStorage(allow_files=False)
    await storage.mkdir(path=Path("/a"))
    assert (await storage.stat(path=Path("/a"))).success is True
    assert (await storage.ls(path=Path("/"))).success is True
    glob_result = await storage.glob(pattern="a")
    assert [o.path for o in glob_result.observations] == ["/a"]


async def test_grep_finds_nothing_honestly_without_allow_files() -> None:
    storage = InMemoryStorage(allow_files=False)
    await storage.mkdir(path=Path("/a"))
    result = await storage.grep(pattern="anything")
    assert result.success is True
    assert result.observations == []


# ----------------------------------------------------------------------
# mkedge
# ----------------------------------------------------------------------


async def test_mkedge_requires_both_endpoints_to_exist() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/src.py"), content="x")
    result = await storage.mkedge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.not_found
    assert result.errors[0].path == "/dst.py"


async def test_mkedge_creates_the_edge_row_at_the_derived_path() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/src.py"), content="x")
    await storage.write(path=Path("/dst.py"), content="x")
    expected_path = edge_out_path(Path("/src.py"), Path("/dst.py"), "imports")
    result = await storage.mkedge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
    assert result.success is True
    row = result.observations[0]
    assert row.path == expected_path
    assert row.kind == "edge"
    assert row.edge_type == "imports"
    assert row.status == "created"


async def test_mkedge_mints_meta_ancestors_exempt_from_the_strict_parent_rule() -> None:
    # No prior mkdir under /.vfs was ever done — mkedge mints its own frame.
    storage = InMemoryStorage()
    await storage.write(path=Path("/src.py"), content="x")
    await storage.write(path=Path("/dst.py"), content="x")
    result = await storage.mkedge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
    assert result.success is True
    edge_path = result.observations[0].path
    ancestor = await storage.stat(path=edge_path.parent_dir)
    assert ancestor.success is True
    assert ancestor.observations[0].kind == "directory"


async def test_mkedge_second_call_reports_updated() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/src.py"), content="x")
    await storage.write(path=Path("/dst.py"), content="x")
    await storage.mkedge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
    result = await storage.mkedge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
    assert result.observations[0].status == "updated"


# ----------------------------------------------------------------------
# Per-row classification for batched reads (source change)
# ----------------------------------------------------------------------


async def test_read_batch_classifies_each_row_and_keeps_the_good_ones() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="a")
    await storage.write(path=Path("/b.txt"), content="b")
    observations = [
        Observation(path=Path("/a.txt")),
        Observation(path=Path("/missing.txt")),
        Observation(path=Path("/b.txt")),
    ]
    result = await storage.read(observations=observations)
    assert result.success is False
    assert {o.path: o.content for o in result.observations} == {"/a.txt": "a", "/b.txt": "b"}
    assert len(result.errors) == 1
    assert result.errors[0].kind == VFSErrorKind.not_found
    assert result.errors[0].path == "/missing.txt"


async def test_read_batch_classifies_a_wrong_kind_row_alongside_good_ones() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="a")
    await storage.mkdir(path=Path("/d"))
    result = await storage.read(observations=[Observation(path=Path("/a.txt")), Observation(path=Path("/d"))])
    assert result.success is False
    assert len(result.observations) == 1
    assert result.errors[0].kind == VFSErrorKind.wrong_kind
    assert result.errors[0].path == "/d"


async def test_read_single_path_keeps_the_fail_whole_shape() -> None:
    storage = InMemoryStorage()
    result = await storage.read(path=Path("/missing.txt"))
    assert result.success is False
    assert result.observations == []
    assert len(result.errors) == 1


async def test_stat_batch_classifies_each_row() -> None:
    storage = InMemoryStorage()
    await storage.write(path=Path("/a.txt"), content="a")
    observations = [Observation(path=Path("/a.txt")), Observation(path=Path("/missing.txt"))]
    result = await storage.stat(observations=observations)
    assert result.success is False
    assert [o.path for o in result.observations] == ["/a.txt"]
    assert len(result.errors) == 1
    assert result.errors[0].path == "/missing.txt"


async def test_stat_single_path_keeps_the_fail_whole_shape() -> None:
    storage = InMemoryStorage()
    result = await storage.stat(path=Path("/missing.txt"))
    assert result.success is False
    assert result.observations == []


async def test_ls_batch_classifies_each_row() -> None:
    storage = InMemoryStorage()
    await storage.mkdir(path=Path("/a"))
    await storage.write(path=Path("/a/f.txt"), content="x")
    observations = [Observation(path=Path("/a")), Observation(path=Path("/missing"))]
    result = await storage.ls(observations=observations)
    assert result.success is False
    assert [o.path for o in result.observations] == ["/a/f.txt"]
    assert len(result.errors) == 1
    assert result.errors[0].path == "/missing"


async def test_ls_single_path_keeps_the_fail_whole_shape() -> None:
    storage = InMemoryStorage()
    result = await storage.ls(path=Path("/missing"))
    assert result.success is False
    assert result.observations == []
