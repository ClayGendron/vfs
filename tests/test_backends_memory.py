"""Memory-specific behavior of ``InMemoryStorage`` — called directly, no router.

The shared backend contract (POSIX parent/site rules, error ordering,
move/copy/edit/delete semantics, glob/grep modes, batch classification,
revision stamping, the mask) lives in ``storage_conformance.py`` and runs
via ``test_storage_conformance.py``. This file keeps only what is true of
the memory backend specifically: its identity defaults, its exact
capability and trait declarations, the ``allow_files=False``
directories-only mode, and its meta-path minting.
"""

from __future__ import annotations

from vfs.models import Entry
from vfs.ops import MUTATING_OPS
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage import TRAIT_KEYS, TRAIT_VALUES, ResolvedPair
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.replace import EditOperation

# ----------------------------------------------------------------------
# Identity, capabilities, traits
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


def test_traits_declares_the_scan_tier_within_the_vocabulary() -> None:
    traits = InMemoryStorage().traits()
    assert traits["grep_tier"] == "scan"
    assert traits["grep_staleness"] == "none"
    assert traits["revision_encoding"] == "per_entry64"
    for key, value in traits.items():
        assert key in TRAIT_KEYS
        assert value in TRAIT_VALUES[key]


async def test_grep_allow_scan_is_a_strict_no_op() -> None:
    # This backend is already the scan tier: the opt-out changes nothing.
    storage = InMemoryStorage()
    await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle here")])
    default = await storage.grep(pattern="needle")
    opted = await storage.grep(pattern="needle", allow_scan=True)
    assert default.observations == opted.observations
    assert default.success and opted.success


# ----------------------------------------------------------------------
# allow_files=False — directories only
# ----------------------------------------------------------------------


async def test_write_content_is_unsupported_without_allow_files() -> None:
    storage = InMemoryStorage(allow_files=False)
    result = await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
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
# Meta-path minting
# ----------------------------------------------------------------------


async def test_read_of_an_edge_row_names_the_actual_kind() -> None:
    # The refusal kind is wrong_kind either way; the prose an agent reads
    # must not call a directly-addressed edge projection a directory.
    storage = InMemoryStorage()
    await storage.write(entries=[Entry(path=Path("/src.py"), content="x")])
    await storage.write(entries=[Entry(path=Path("/dst.py"), content="x")])
    edge = await storage.mkedge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
    result = await storage.read(path=edge.observations[0].path)
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.wrong_kind
    assert "edge" in result.errors[0].message
    assert "directory" not in result.errors[0].message


async def test_mkedge_mints_meta_ancestors_exempt_from_the_strict_parent_rule() -> None:
    # No prior mkdir under /.vfs was ever done — mkedge mints its own frame.
    storage = InMemoryStorage()
    await storage.write(entries=[Entry(path=Path("/src.py"), content="x")])
    await storage.write(entries=[Entry(path=Path("/dst.py"), content="x")])
    result = await storage.mkedge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
    assert result.success is True
    edge_path = result.observations[0].path
    ancestor = await storage.stat(path=edge_path.parent_dir)
    assert ancestor.success is True
    assert ancestor.observations[0].kind == "directory"
