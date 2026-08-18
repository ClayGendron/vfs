"""Backend-agnostic storage conformance suite — the behavior contract.

``StorageContract`` holds every test a ``StorageBackend`` must pass
identically regardless of engine: the POSIX parent/site rules, the shared
error-ordering descent ladder and per-verb leaf tables, read/ls/tree
shapes, move/copy subtree semantics, edit/delete atomicity, glob/grep
modes, per-row batch classification, version stamping, and the
populated-field mask. **Zero per-engine conditional assertions** — a
backend that needs a special case here is out of contract.

Usage: subclass in a ``test_*`` file and provide the ``storage`` fixture
yielding a fresh backend per test (dispose in the fixture when the backend
owns resources)::

    class TestMemoryConformance(StorageContract):
        @pytest.fixture
        async def storage(self) -> AsyncIterator[InMemoryStorage]:
            storage = InMemoryStorage()
            yield storage
            await storage.close()

Per-family opt-in is declared, not sniffed: tests marked
``@needs("write", ...)`` skip when the backend's ``capabilities()`` lacks
any required op — partial backends are first-class.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import pytest

from vfs.models import Entry, Observation
from vfs.paths import Path
from vfs.pattern_matching import escape_glob
from vfs.results import Severity, VFSErrorKind
from vfs.results.projection import OBSERVATION_FIELDS
from vfs.storage import (
    TRAIT_KEYS,
    TRAIT_VALUES,
    ResolvedPair,
    StorageBackend,
    SupportsMutation,
    SupportsPatternSearch,
    SupportsReindex,
    SupportsTraits,
)
from vfs.storage.replace import EditOperation

needs = pytest.mark.needs
"""Ops a test requires; the gate fixture skips when capabilities lack any."""


class ConformanceBackend(StorageBackend, SupportsPatternSearch, SupportsMutation, Protocol):
    """The full verb surface the suite may call; capability gating trims per test."""


def _indexed_grep_tier(storage: ConformanceBackend) -> bool:
    """Whether the backend declares the indexed grep tier (refusal gate).

    Absence fails loudly: dropping the trait would silently flip every
    tier row to a skip, which is exactly the blind spot this guards.
    Only an explicit ``"scan"`` opts a backend out of the tier rows.
    """
    tier = storage.traits().get("grep_tier") if isinstance(storage, SupportsTraits) else None
    if tier not in ("indexed", "scan"):
        pytest.fail(f"backend declares grep_tier={tier!r}; every backend must declare 'indexed' or 'scan'")
    return tier == "indexed"


def _reindexer_of(storage: ConformanceBackend) -> SupportsReindex:
    """The backend's reindex surface; backends without one skip these rows."""
    if not isinstance(storage, SupportsReindex):
        pytest.skip("backend does not expose reindex")
    return storage


async def _revision_of(storage: ConformanceBackend, path: str) -> int:
    result = await storage.stat(path=Path(path))
    version = result.observations[0].version
    assert version is not None
    return version


# Directory names holding a LIKE metacharacter, beside the near-miss
# decoys an unescaped prefix pattern would erroneously match.
METACHAR_DIRS = ("a%b", "a_b", "a\\b", "a[1]b")
DECOY_DIRS = ("aXb", "ab", "a1b")


async def _mint_metachar_tree(storage: ConformanceBackend) -> None:
    for name in (*METACHAR_DIRS, *DECOY_DIRS):
        result = await storage.write(entries=[Entry(path=Path(f"/{name}/inner.txt"), content=name)], parents=True)
        assert result.success is True


class StorageContract:
    """The shared behavior contract. Subclass per backend; see module docstring."""

    @pytest.fixture
    def storage(self) -> ConformanceBackend:
        raise NotImplementedError("conformance subclasses must provide the storage fixture")

    @pytest.fixture(autouse=True)
    def _capability_gate(self, request: pytest.FixtureRequest, storage: ConformanceBackend) -> None:
        marker = request.node.get_closest_marker("needs")
        if marker is None:
            return
        missing = frozenset(marker.args) - storage.capabilities()
        if missing:
            pytest.skip(f"backend does not declare: {', '.join(sorted(missing))}")

    # ------------------------------------------------------------------
    # POSIX parent/site rules — write and mkdir
    # ------------------------------------------------------------------

    @needs("write", "stat")
    async def test_write_without_parents_missing_ancestor_is_not_found(self, storage: ConformanceBackend) -> None:
        result = await storage.write(entries=[Entry(path=Path("/a/b/c.txt"), content="hi")])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found
        assert result.errors[0].path == "/a"

    @needs("write", "stat")
    async def test_write_with_parents_mints_the_missing_chain(self, storage: ConformanceBackend) -> None:
        result = await storage.write(entries=[Entry(path=Path("/a/b/c.txt"), content="hi")], parents=True)
        assert result.success is True
        assert result.observations[0].status == "created"
        # The minted ancestors are not echoed on this result, but they now exist.
        ancestor = await storage.stat(path=Path("/a/b"))
        assert ancestor.success is True
        assert ancestor.observations[0].kind == "directory"

    @needs("mkdir")
    async def test_mkdir_with_parents_reports_every_created_ancestor(self, storage: ConformanceBackend) -> None:
        result = await storage.mkdir(path=Path("/a/b/c"), parents=True)
        assert result.success is True
        assert [o.path for o in result.observations] == ["/a", "/a/b", "/a/b/c"]
        assert all(o.status == "created" for o in result.observations)

    @needs("mkdir")
    async def test_mkdir_without_parents_missing_ancestor_is_not_found(self, storage: ConformanceBackend) -> None:
        result = await storage.mkdir(path=Path("/a/b"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found
        assert result.errors[0].path == "/a"

    @needs("write")
    async def test_ancestor_stored_as_a_file_is_wrong_kind_without_parents(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/f"), content="x")])
        result = await storage.write(entries=[Entry(path=Path("/f/sub.txt"), content="x")])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        assert result.errors[0].path == "/f"

    @needs("write", "mkdir")
    async def test_ancestor_stored_as_a_file_is_wrong_kind_even_with_parents(self, storage: ConformanceBackend) -> None:
        # Unconditional: parents=True mints missing ancestors, it never coerces one.
        await storage.write(entries=[Entry(path=Path("/f"), content="x")])
        result = await storage.mkdir(path=Path("/f/sub"), parents=True)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        assert result.errors[0].path == "/f"

    @needs("write", "mkdir")
    async def test_write_onto_a_directory_is_wrong_kind(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/d"))
        result = await storage.write(entries=[Entry(path=Path("/d"), content="x")])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind

    @needs("write")
    async def test_write_onto_an_existing_file_without_overwrite_is_exists(self, storage: ConformanceBackend) -> None:
        # The create leaf table: existence outranks everything else at the leaf.
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="first")])
        result = await storage.write(entries=[Entry(path=Path("/a.txt"), content="second")], overwrite=False)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.exists

    @needs("write", "mkdir")
    async def test_write_entries_creates_and_forgives_directories(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/existing"))
        result = await storage.write(
            entries=[Entry(path=Path("/existing"), kind="directory"), Entry(path=Path("/new"), kind="directory")]
        )
        assert result.success is True
        assert {o.path: o.status for o in result.observations} == {"/existing": "unchanged", "/new": "created"}

    @needs("write")
    async def test_write_entries_classifies_directory_failures_per_entry(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/f"), content="x")])
        result = await storage.write(
            entries=[
                Entry(path=Path("/f"), kind="directory"),
                Entry(path=Path("/ghost/sub"), kind="directory"),
            ]
        )
        assert result.success is False
        kinds = {str(e.path): e.kind for e in result.errors}
        assert kinds["/f"] == VFSErrorKind.wrong_kind
        assert kinds["/ghost"] == VFSErrorKind.not_found

    @needs("mkdir")
    async def test_mkdir_on_occupied_site_is_exists(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        result = await storage.mkdir(path=Path("/a"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.exists

    @needs("mkdir")
    async def test_mkdir_exist_ok_on_a_directory_occupant_is_unchanged(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        result = await storage.mkdir(path=Path("/a"), exist_ok=True)
        assert result.success is True
        assert result.observations[0].status == "unchanged"

    @needs("write", "mkdir")
    async def test_mkdir_exist_ok_on_a_file_occupant_still_exists(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a"), content="x")])
        result = await storage.mkdir(path=Path("/a"), exist_ok=True)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.exists

    # ------------------------------------------------------------------
    # ls / read / tree / stat shapes
    # ------------------------------------------------------------------

    @needs("write", "mkdir", "ls")
    async def test_ls_directory_lists_children(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        await storage.write(entries=[Entry(path=Path("/a/f.txt"), content="x")])
        result = await storage.ls(path=Path("/a"))
        assert result.success is True
        assert [o.path for o in result.observations] == ["/a/f.txt"]

    @needs("write", "ls")
    async def test_ls_file_lists_itself(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        result = await storage.ls(path=Path("/a.txt"))
        assert result.success is True
        assert result.observations[0].path == "/a.txt"

    @needs("write", "ls")
    async def test_ls_without_a_target_defaults_to_the_root(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        result = await storage.ls()
        assert result.success is True
        assert [o.path for o in result.observations] == ["/a.txt"]

    @needs("ls")
    async def test_ls_missing_is_not_found(self, storage: ConformanceBackend) -> None:
        result = await storage.ls(path=Path("/nope"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found

    @needs("mkdir", "ls")
    async def test_ls_of_an_empty_directory_is_an_empty_success(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/empty"))
        result = await storage.ls(path=Path("/empty"))
        assert result.success is True
        assert result.observations == []

    @needs("mkdir", "tree")
    async def test_tree_of_an_empty_directory_is_an_empty_success(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/empty"))
        result = await storage.tree(path=Path("/empty"))
        assert result.success is True
        assert result.observations == []

    @needs("write", "read", "stat")
    async def test_repeated_batch_targets_observe_per_occurrence(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        twice = [Observation(path=Path("/a.txt")), Observation(path=Path("/a.txt"))]
        read = await storage.read(observations=twice)
        assert [str(o.path) for o in read.observations] == ["/a.txt", "/a.txt"]
        stat = await storage.stat(observations=twice)
        assert [str(o.path) for o in stat.observations] == ["/a.txt", "/a.txt"]

    @needs("mkdir", "read")
    async def test_read_on_a_directory_is_wrong_kind(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        result = await storage.read(path=Path("/a"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind

    @needs("write", "mkdir", "tree")
    async def test_tree_max_depth_budgets_the_subtree(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a/b/c"), parents=True)
        await storage.write(entries=[Entry(path=Path("/a/b/c/d.txt"), content="x")])

        shallow = await storage.tree(path=Path("/a"), max_depth=1)
        assert [o.path for o in shallow.observations] == ["/a/b"]

        deeper = await storage.tree(path=Path("/a"), max_depth=2)
        assert [o.path for o in deeper.observations] == ["/a/b", "/a/b/c"]

        full = await storage.tree(path=Path("/a"))
        assert [o.path for o in full.observations] == ["/a/b", "/a/b/c", "/a/b/c/d.txt"]

    @needs("write", "tree")
    async def test_tree_on_a_file_returns_just_that_row(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        result = await storage.tree(path=Path("/a.txt"))
        assert [o.path for o in result.observations] == ["/a.txt"]

    @needs("tree")
    async def test_tree_rejects_a_sub_one_max_depth(self, storage: ConformanceBackend) -> None:
        result = await storage.tree(path=Path("/"), max_depth=0)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid

    @needs("tree")
    async def test_tree_missing_is_not_found(self, storage: ConformanceBackend) -> None:
        result = await storage.tree(path=Path("/nope"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found

    @needs("write", "mkdir", "stat")
    async def test_stat_row_shapes(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="hello")])
        file_row = (await storage.stat(path=Path("/a.txt"))).observations[0]
        assert file_row.kind == "file"
        assert file_row.content is None  # stat never carries content
        assert file_row.size_bytes == len(b"hello")

        await storage.mkdir(path=Path("/d"))
        dir_row = (await storage.stat(path=Path("/d"))).observations[0]
        assert dir_row.kind == "directory"
        assert dir_row.size_bytes is None

    # ------------------------------------------------------------------
    # The shared descent ladder — first failing boundary wins
    # ------------------------------------------------------------------

    @needs("write", "read", "stat", "ls", "tree")
    async def test_missing_ancestor_classifies_not_found_at_that_component(self, storage: ConformanceBackend) -> None:
        # Positional precedence: the walk stops at the leftmost failing
        # boundary; deeper conditions (the missing leaf) never surface.
        await storage.write(entries=[Entry(path=Path("/top.txt"), content="x")])
        for verb in (storage.read, storage.stat, storage.ls, storage.tree):
            result = await verb(path=Path("/ghost/deep/x.txt"))
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.not_found
            assert result.errors[0].path == "/ghost"

    @needs("write", "read", "stat", "ls", "tree")
    async def test_file_ancestor_classifies_wrong_kind_at_that_component(self, storage: ConformanceBackend) -> None:
        # Wrong-kind on a node beats everything deeper — the V7
        # access-clobbers-ENOTDIR bug is the counterexample on record.
        await storage.write(entries=[Entry(path=Path("/f"), content="x")])
        for verb in (storage.read, storage.stat, storage.ls, storage.tree):
            result = await verb(path=Path("/f/deep/x.txt"))
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.wrong_kind
            assert result.errors[0].path == "/f"

    @needs("write", "edit", "delete")
    async def test_mutation_misses_classify_the_first_failing_boundary(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/f"), content="x")])
        edited = await storage.edit(edits=[EditOperation(old="a", new="b")], path=Path("/ghost/a.txt"))
        assert edited.errors[0].kind == VFSErrorKind.not_found
        assert edited.errors[0].path == "/ghost"
        deleted = await storage.delete(path=Path("/f/deep/a.txt"))
        assert deleted.errors[0].kind == VFSErrorKind.wrong_kind
        assert deleted.errors[0].path == "/f"

    # ------------------------------------------------------------------
    # move / copy subtree semantics and the move leaf table
    # ------------------------------------------------------------------

    @needs("write", "mkdir", "move", "stat")
    async def test_move_rewrites_the_subtree_prefix(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        await storage.write(entries=[Entry(path=Path("/a/x.txt"), content="x")])
        result = await storage.move(operations=[ResolvedPair(src=Path("/a"), dest=Path("/b"))])
        assert result.success is True
        assert (await storage.stat(path=Path("/a"))).success is False
        assert (await storage.stat(path=Path("/b"))).success is True
        assert (await storage.stat(path=Path("/b/x.txt"))).success is True

    @needs("write", "mkdir", "copy", "stat")
    async def test_copy_rewrites_the_subtree_prefix_and_keeps_the_source(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        await storage.write(entries=[Entry(path=Path("/a/x.txt"), content="x")])
        result = await storage.copy(operations=[ResolvedPair(src=Path("/a"), dest=Path("/b"))])
        assert result.success is True
        assert (await storage.stat(path=Path("/a/x.txt"))).success is True
        assert (await storage.stat(path=Path("/b/x.txt"))).success is True

    @needs("mkdir", "move")
    async def test_move_into_own_descendant_is_one_cycle_kind_at_any_depth(self, storage: ConformanceBackend) -> None:
        # Both a depth-1 and a depth-2 destination refuse with the same
        # kind — cycle refusal is one classification, not two.
        await storage.mkdir(path=Path("/a/b"), parents=True)
        shallow = await storage.move(operations=[ResolvedPair(src=Path("/a"), dest=Path("/a/sub"))])
        deep = await storage.move(operations=[ResolvedPair(src=Path("/a"), dest=Path("/a/b/c"))])
        assert shallow.success is False and deep.success is False
        assert shallow.errors[0].kind == VFSErrorKind.invalid
        assert deep.errors[0].kind == VFSErrorKind.invalid

    @needs("write", "move", "read")
    async def test_move_to_the_same_path_is_a_no_op(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="keep")])
        result = await storage.move(operations=[ResolvedPair(src=Path("/a.txt"), dest=Path("/a.txt"))])
        assert result.success is True
        assert result.observations[0].status == "unchanged"
        assert (await storage.read(path=Path("/a.txt"))).observations[0].content == "keep"

    @needs("write", "move")
    async def test_move_source_missing_wins_over_occupied_destination(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/dest.txt"), content="x")])
        result = await storage.move(operations=[ResolvedPair(src=Path("/ghost.txt"), dest=Path("/dest.txt"))])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found

    @needs("write", "mkdir", "move")
    async def test_move_cycle_classifies_before_the_occupied_destination(self, storage: ConformanceBackend) -> None:
        # Destination is both occupied AND inside the source: the cycle
        # refusal wins over occupied-target kind translation (the Linux
        # rename ladder — trap checks precede vfs_rename's kind checks).
        await storage.mkdir(path=Path("/a"))
        await storage.write(entries=[Entry(path=Path("/a/f.txt"), content="x")])
        result = await storage.move(operations=[ResolvedPair(src=Path("/a"), dest=Path("/a/f.txt"))])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid

    @needs("write", "mkdir", "move")
    async def test_move_onto_own_ancestor_is_the_same_cycle_kind(self, storage: ConformanceBackend) -> None:
        # Both cycle directions collapse to one refusal kind: the target-
        # ancestor-of-source direction must not surface as the occupied-
        # target kind (Linux's EINVAL/ENOTEMPTY split deliberately not copied).
        await storage.mkdir(path=Path("/a/b"), parents=True)
        result = await storage.move(operations=[ResolvedPair(src=Path("/a/b"), dest=Path("/a"))])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid

    @needs("write", "mkdir", "move")
    async def test_move_no_replace_occupied_destination_is_exists_before_kind(
        self, storage: ConformanceBackend
    ) -> None:
        # Under no-replace, existence outranks kind translation — the
        # RENAME_NOREPLACE EEXIST fires before any type check.
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="x")])
        onto_dir = await storage.move(operations=[ResolvedPair(src=Path("/f.txt"), dest=Path("/d"))], overwrite=False)
        onto_file = await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path("/f.txt"))], overwrite=False)
        assert onto_dir.errors[0].kind == VFSErrorKind.exists
        assert onto_file.errors[0].kind == VFSErrorKind.exists

    @needs("write", "mkdir", "move", "stat")
    async def test_move_dir_over_empty_dir_replaces_it(self, storage: ConformanceBackend) -> None:
        # POSIX rename: an empty target directory is replaced.
        await storage.mkdir(path=Path("/src"))
        await storage.write(entries=[Entry(path=Path("/src/f.txt"), content="x")])
        await storage.mkdir(path=Path("/empty"))
        result = await storage.move(operations=[ResolvedPair(src=Path("/src"), dest=Path("/empty"))])
        assert result.success is True
        assert (await storage.stat(path=Path("/empty/f.txt"))).success is True
        assert (await storage.stat(path=Path("/src"))).success is False

    @needs("write", "mkdir", "copy", "stat")
    async def test_copy_dir_over_empty_dir_replaces_it(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/src"))
        await storage.write(entries=[Entry(path=Path("/src/f.txt"), content="x")])
        await storage.mkdir(path=Path("/empty"))
        result = await storage.copy(operations=[ResolvedPair(src=Path("/src"), dest=Path("/empty"))])
        assert result.success is True
        assert (await storage.stat(path=Path("/empty/f.txt"))).success is True
        assert (await storage.stat(path=Path("/src/f.txt"))).success is True

    @needs("write", "mkdir", "move", "stat")
    async def test_move_dir_over_non_empty_dir_is_not_empty(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/src"))
        await storage.mkdir(path=Path("/dst"))
        await storage.write(entries=[Entry(path=Path("/dst/keep.txt"), content="x")])
        result = await storage.move(operations=[ResolvedPair(src=Path("/src"), dest=Path("/dst"))])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_empty
        assert (await storage.stat(path=Path("/dst/keep.txt"))).success is True

    @needs("write", "move")
    async def test_move_file_over_file_without_overwrite_is_exists(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="a")])
        await storage.write(entries=[Entry(path=Path("/b.txt"), content="b")])
        result = await storage.move(operations=[ResolvedPair(src=Path("/a.txt"), dest=Path("/b.txt"))], overwrite=False)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.exists

    @needs("write", "mkdir", "move")
    async def test_move_a_directory_onto_an_occupied_site_is_wrong_kind(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        await storage.write(entries=[Entry(path=Path("/c.txt"), content="x")])
        result = await storage.move(operations=[ResolvedPair(src=Path("/a"), dest=Path("/c.txt"))])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind

    @needs("write", "mkdir", "move")
    async def test_move_a_file_onto_a_directory_is_wrong_kind(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="x")])
        await storage.mkdir(path=Path("/d"))
        result = await storage.move(operations=[ResolvedPair(src=Path("/f.txt"), dest=Path("/d"))])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind

    @needs("write", "mkdir", "move", "copy", "read")
    async def test_transfer_classifies_a_row_that_overflows_at_the_destination(
        self, storage: ConformanceBackend
    ) -> None:
        # Both pair paths are individually valid; only a deep row's minted
        # destination exceeds the limit — refuse the pair, never raise.
        tail = "x" * 200 + ".txt"
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/" + tail), content="deep")])
        parent = "/" + "/".join(["p" * 200 for _ in range(4)])
        await storage.mkdir(path=Path(parent), parents=True)
        dest = Path(parent + "/" + "q" * 100)
        for op in (storage.move, storage.copy):
            result = await op(operations=[ResolvedPair(src=Path("/d"), dest=dest)])
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.unaddressable
        assert (await storage.read(path=Path("/d/" + tail))).success is True

    @needs("mkdir", "move")
    async def test_transfers_involving_the_root_are_invalid(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        as_source = await storage.move(operations=[ResolvedPair(src=Path("/"), dest=Path("/a/root"))])
        as_target = await storage.move(operations=[ResolvedPair(src=Path("/a"), dest=Path("/"))])
        assert as_source.errors[0].kind == VFSErrorKind.invalid
        assert as_target.errors[0].kind == VFSErrorKind.invalid

    @needs("write", "move")
    async def test_move_destination_under_a_missing_parent_is_not_found(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        result = await storage.move(operations=[ResolvedPair(src=Path("/a.txt"), dest=Path("/ghost/a.txt"))])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found
        assert result.errors[0].path == "/ghost"

    @needs("write", "move", "stat")
    async def test_move_batch_is_staged_atomic(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        operations = [
            ResolvedPair(src=Path("/a.txt"), dest=Path("/moved.txt")),
            ResolvedPair(src=Path("/missing.txt"), dest=Path("/also-moved.txt")),
        ]
        result = await storage.move(operations=operations)
        assert result.success is False
        # Nothing committed: the first pair's effect never lands.
        assert (await storage.stat(path=Path("/a.txt"))).success is True
        assert (await storage.stat(path=Path("/moved.txt"))).success is False

    # ------------------------------------------------------------------
    # edit — sequential, atomic
    # ------------------------------------------------------------------

    @needs("write", "edit", "read")
    async def test_edit_applies_operations_sequentially(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="hello world")])
        edits = [EditOperation(old="hello", new="hi"), EditOperation(old="hi world", new="hi there")]
        result = await storage.edit(edits=edits, path=Path("/a.txt"))
        assert result.success is True
        assert (await storage.read(path=Path("/a.txt"))).observations[0].content == "hi there"

    @needs("write", "edit", "read")
    async def test_edit_batch_is_atomic_on_a_failed_match(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="hello world")])
        edits = [EditOperation(old="hello", new="hi"), EditOperation(old="nonexistent", new="x")]
        result = await storage.edit(edits=edits, path=Path("/a.txt"))
        assert result.success is False
        # The first edit's effect never lands either.
        assert (await storage.read(path=Path("/a.txt"))).observations[0].content == "hello world"

    @needs("write", "edit", "read")
    async def test_edit_result_reenters_entry_validation(self, storage: ConformanceBackend) -> None:
        # Writes only accept validated entries; edits synthesize content, so
        # the result re-enters the same gate (null bytes are unstorable).
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="clean text")])
        result = await storage.edit(edits=[EditOperation(old="clean", new="cl\x00ean")], path=Path("/a.txt"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid
        assert (await storage.read(path=Path("/a.txt"))).observations[0].content == "clean text"

    @needs("mkdir", "edit")
    async def test_edit_on_a_directory_is_wrong_kind(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/d"))
        result = await storage.edit(edits=[EditOperation(old="a", new="b")], path=Path("/d"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind

    # ------------------------------------------------------------------
    # delete — the leaf table
    # ------------------------------------------------------------------

    @needs("delete")
    async def test_delete_root_is_invalid(self, storage: ConformanceBackend) -> None:
        result = await storage.delete(path=Path("/"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid

    @needs("delete")
    async def test_delete_missing_victim_is_not_found_first(self, storage: ConformanceBackend) -> None:
        result = await storage.delete(path=Path("/ghost.txt"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found

    @needs("write", "mkdir", "delete", "stat")
    async def test_delete_non_empty_directory_without_cascade_is_not_empty(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        await storage.write(entries=[Entry(path=Path("/a/f.txt"), content="x")])
        result = await storage.delete(path=Path("/a"), cascade=False)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_empty
        assert (await storage.stat(path=Path("/a/f.txt"))).success is True

    @needs("write", "mkdir", "delete", "stat")
    async def test_delete_cascades_by_default(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        await storage.write(entries=[Entry(path=Path("/a/f.txt"), content="x")])
        result = await storage.delete(path=Path("/a"))
        assert result.success is True
        assert (await storage.stat(path=Path("/a"))).success is False
        assert (await storage.stat(path=Path("/a/f.txt"))).success is False

    @needs("write", "delete", "read", "stat")
    async def test_a_single_target_delete_carries_a_restorable_trash_path(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="body")])
        result = await storage.delete(path=Path("/a.txt"))
        assert result.success is True
        obs = result.observations[0]
        assert obs.trash_path is not None
        assert "trash_path" in obs.populated
        assert (await storage.stat(path=Path("/a.txt"))).success is False
        assert (await storage.restore(path=obs.trash_path)).success is True
        assert (await storage.read(path=Path("/a.txt"))).observations[0].content == "body"

    @needs("write", "mkdir", "delete", "read", "stat")
    async def test_a_covered_targets_trash_path_resolves_but_only_its_root_restores(
        self, storage: ConformanceBackend
    ) -> None:
        # Every observation names where its row now lives; only the
        # covering root's address is a restore handle — covered rows
        # ride back with it.
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="deep")])
        targets = [Observation(path=Path("/d/f.txt")), Observation(path=Path("/d"))]
        result = await storage.delete(observations=targets)
        assert result.success is True
        assert all(o.trash_path is not None for o in result.observations)
        by_path = {str(o.path): o for o in result.observations}
        root_trash = by_path["/d"].trash_path
        covered_trash = by_path["/d/f.txt"].trash_path
        assert root_trash is not None and covered_trash is not None
        assert (await storage.stat(path=covered_trash)).success is True
        assert (await storage.read(path=covered_trash)).observations[0].content == "deep"
        refused = await storage.restore(path=covered_trash)
        assert refused.success is False
        assert refused.errors[0].kind == VFSErrorKind.invalid
        assert (await storage.restore(path=root_trash)).success is True
        assert (await storage.read(path=Path("/d/f.txt"))).observations[0].content == "deep"

    @needs("write", "delete", "stat")
    async def test_delete_of_the_trash_chain_refuses_naming_sweep(self, storage: ConformanceBackend) -> None:
        # /.vfs and /.vfs/trash hold the active bucket chain: trashing
        # them would reparent the chain into its own cascade.
        await storage.write(entries=[Entry(path=Path("/keep.txt"), content="x")])
        deleted = await storage.delete(path=Path("/keep.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        for target in (Path("/.vfs"), Path("/.vfs/trash")):
            result = await storage.delete(path=target)
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.invalid
            assert "sweep" in (result.errors[0].message or "")
        # Nothing purged: the trashed row is still addressable.
        assert (await storage.stat(path=trash_path)).success is True

    @needs("write", "delete", "stat")
    async def test_delete_of_the_current_bucket_refuses_naming_sweep(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/keep.txt"), content="x")])
        deleted = await storage.delete(path=Path("/keep.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        bucket = trash_path.parent_dir
        result = await storage.delete(path=bucket)
        if str(bucket) != f"/.vfs/trash/{datetime.now(UTC).strftime('%Y-%m-%d-%H')}":
            pytest.skip("hour boundary crossed between deletes")
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid
        assert "sweep" in (result.errors[0].message or "")
        assert (await storage.stat(path=trash_path)).success is True

    @needs("write", "delete", "read", "stat")
    async def test_delete_of_an_older_bucket_trashes_nested_and_restores(self, storage: ConformanceBackend) -> None:
        # Only the active chain is protected: an aged bucket is an
        # ordinary directory that trashes (nested) and restores whole.
        old_bucket = Path("/.vfs/trash/2020-01-01-00")
        await storage.write(entries=[Entry(path=Path(f"{old_bucket}/f.txt"), content="x")], parents=True)
        result = await storage.delete(path=old_bucket)
        assert result.success is True
        trash_path = result.observations[0].trash_path
        assert trash_path is not None
        assert (await storage.stat(path=old_bucket)).success is False
        assert (await storage.restore(path=trash_path)).success is True
        assert (await storage.read(path=Path(f"{old_bucket}/f.txt"))).observations[0].content == "x"

    # ------------------------------------------------------------------
    # restore — the trash contract
    # ------------------------------------------------------------------

    @needs("write", "delete", "read", "stat")
    async def test_restore_by_trash_path_round_trips(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="body")])
        deleted = await storage.delete(path=Path("/a.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        result = await storage.restore(path=trash_path)
        assert result.success is True
        assert result.observations[0].path == "/a.txt"
        assert result.observations[0].status == "created"
        assert (await storage.read(path=Path("/a.txt"))).observations[0].content == "body"
        assert (await storage.stat(path=trash_path)).success is False

    @needs("write", "delete", "read")
    async def test_restore_by_original_path_takes_the_newest_candidate(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="one")])
        await storage.delete(path=Path("/a.txt"))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="two")])
        await storage.delete(path=Path("/a.txt"))
        assert (await storage.restore(path=Path("/a.txt"))).success is True
        assert (await storage.read(path=Path("/a.txt"))).observations[0].content == "two"
        # The older candidate stayed in trash: purge the newer, restore again.
        await storage.sweep(path=Path("/a.txt"))
        assert (await storage.restore(path=Path("/a.txt"))).success is True
        assert (await storage.read(path=Path("/a.txt"))).observations[0].content == "one"

    @needs("write", "delete", "restore")
    async def test_batch_refusals_onto_one_destination_stay_distinct(self, storage: ConformanceBackend) -> None:
        # Two trash rows refusing onto one occupied destination each carry
        # their own trash-side attribution — two errors, never one.
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="one")])
        first = (await storage.delete(path=Path("/f.txt"))).observations[0].trash_path
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="two")])
        second = (await storage.delete(path=Path("/f.txt"))).observations[0].trash_path
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="occupant")])
        assert first is not None and second is not None
        result = await storage.restore(observations=[Observation(path=first), Observation(path=second)])
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.exists] * 2
        assert {e.data["target"] for e in result.errors if e.data} == {str(first), str(second)}

    @needs("write", "mkdir", "move")
    async def test_move_refusals_onto_one_destination_carry_their_sources(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/s1"))
        await storage.mkdir(path=Path("/s2"))
        await storage.write(entries=[Entry(path=Path("/d/kid.txt"), content="x")], parents=True)
        pairs = [ResolvedPair(src=Path("/s1"), dest=Path("/d")), ResolvedPair(src=Path("/s2"), dest=Path("/d"))]
        result = await storage.move(operations=pairs, overwrite=True)
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.not_empty] * 2
        assert {e.data["target"] for e in result.errors if e.data} == {"/s1", "/s2"}

    @needs("move")
    async def test_moving_the_root_carries_its_source_target(self, storage: ConformanceBackend) -> None:
        result = await storage.move(operations=[ResolvedPair(src=Path("/"), dest=Path("/copy"))])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid
        assert result.errors[0].data == {"target": "/"}

    @needs("write", "move")
    async def test_unaddressable_move_carries_its_source_target(self, storage: ConformanceBackend) -> None:
        # A subtree whose deepest path fits only under its short root:
        # rebasing under a longer destination overflows the path cap.
        deep = Path("/s/" + "/".join(["a" * 200] * 5))
        await storage.write(entries=[Entry(path=deep, content="x")], parents=True)
        result = await storage.move(operations=[ResolvedPair(src=Path("/s"), dest=Path("/" + "d" * 30))])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unaddressable
        assert result.errors[0].data == {"target": "/s"}

    @needs("write", "delete", "read")
    async def test_restore_occupied_site_is_exists_until_overwrite(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="old")])
        await storage.delete(path=Path("/a.txt"))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="squatter")])
        refused = await storage.restore(path=Path("/a.txt"))
        assert refused.success is False
        assert refused.errors[0].kind == VFSErrorKind.exists
        replaced = await storage.restore(path=Path("/a.txt"), overwrite=True)
        assert replaced.success is True
        assert replaced.observations[0].status == "updated"
        assert (await storage.read(path=Path("/a.txt"))).observations[0].content == "old"

    async def test_restore_with_no_candidate_is_not_found(self, storage: ConformanceBackend) -> None:
        result = await storage.restore(path=Path("/ghost.txt"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found

    async def test_restore_of_a_missing_trash_path_is_not_found(self, storage: ConformanceBackend) -> None:
        result = await storage.restore(path=Path("/.vfs/trash/1999-01-01-00/ghost"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found

    @needs("write", "mkdir", "delete", "stat")
    async def test_restore_of_a_directory_brings_the_subtree(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="deep")])
        await storage.delete(path=Path("/d"))
        assert (await storage.restore(path=Path("/d"))).success is True
        assert (await storage.stat(path=Path("/d/f.txt"))).success is True

    @needs("write")
    async def test_restore_of_a_user_authored_trash_row_is_invalid(self, storage: ConformanceBackend) -> None:
        squatter = Path("/.vfs/trash/2026-07-18-10/x.txt")
        await storage.write(entries=[Entry(path=squatter, content="mine")], parents=True)
        result = await storage.restore(path=squatter)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid

    @needs("write", "mkdir", "delete", "read")
    async def test_failed_restore_keeps_the_row_in_trash(self, storage: ConformanceBackend) -> None:
        # Fail-and-keep: a dead original parent refuses, metadata intact.
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        deleted = await storage.delete(path=Path("/d/f.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        await storage.sweep(path=Path("/d"))
        by_site = await storage.restore(path=Path("/d/f.txt"))
        assert by_site.success is False
        assert by_site.errors[0].kind == VFSErrorKind.not_found
        by_row = await storage.restore(path=trash_path)
        assert by_row.success is False
        assert by_row.errors[0].kind == VFSErrorKind.not_found
        assert (await storage.read(path=trash_path)).observations[0].content == "x"

    # ------------------------------------------------------------------
    # sweep — reclamation
    # ------------------------------------------------------------------

    @needs("write", "mkdir", "stat")
    async def test_sweep_drops_an_expired_bucket_wholesale(self, storage: ConformanceBackend) -> None:
        # Trash is an ordinary subtree, so an aged bucket is creatable
        # through public verbs — foreign rows inside drop with it.
        bucket = Path("/.vfs/trash/2020-01-01-00")
        await storage.mkdir(path=bucket, parents=True)
        await storage.write(entries=[Entry(path=Path(f"{bucket}/foreign.txt"), content="x")])
        result = await storage.sweep(path=Path("/.vfs/trash"))
        assert result.success is True
        assert [str(o.path) for o in result.observations] == [str(bucket)]
        assert result.observations[0].status == "deleted"
        assert (await storage.stat(path=bucket)).success is False
        assert (await storage.stat(path=Path(f"{bucket}/foreign.txt"))).success is False

    @needs("write", "delete", "stat")
    async def test_sweep_retains_young_buckets(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deleted = await storage.delete(path=Path("/a.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        result = await storage.sweep(path=Path("/.vfs/trash"))
        assert result.success is True
        assert result.observations == []
        assert (await storage.stat(path=trash_path)).success is True

    @needs("write", "mkdir", "stat")
    async def test_sweep_skips_and_surfaces_non_bucket_rows(self, storage: ConformanceBackend) -> None:
        # A file, a directory whose name is no date at all, and a near-miss
        # name strptime would admit but the strict round-trip refuses —
        # all foreign state, skipped and surfaced.
        await storage.write(entries=[Entry(path=Path("/.vfs/trash/notes.txt"), content="keep")], parents=True)
        await storage.mkdir(path=Path("/.vfs/trash/junk"))
        await storage.mkdir(path=Path("/.vfs/trash/2020-1-1-0"))
        result = await storage.sweep(path=Path("/.vfs/trash"))
        assert result.success is True
        skipped = sorted(str(e.path) for e in result.errors)
        assert skipped == ["/.vfs/trash/2020-1-1-0", "/.vfs/trash/junk", "/.vfs/trash/notes.txt"]
        assert all(e.severity == Severity.warning for e in result.errors)
        for survivor in skipped:
            assert (await storage.stat(path=Path(survivor))).success is True

    async def test_sweep_of_a_never_used_trash_is_an_idempotent_no_op(self, storage: ConformanceBackend) -> None:
        for _ in range(2):
            result = await storage.sweep(path=Path("/.vfs/trash"))
            assert result.success is True
            assert result.observations == []
            assert result.errors == []

    @needs("write", "mkdir", "stat")
    async def test_sweep_purges_an_arbitrary_directory_wholesale(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/proj"))
        await storage.write(entries=[Entry(path=Path("/proj/f.txt"), content="x")])
        result = await storage.sweep(path=Path("/proj"))
        assert result.success is True
        obs = result.observations[0]
        assert str(obs.path) == "/proj"
        assert obs.status == "deleted"
        assert obs.trash_path is None
        assert (await storage.stat(path=Path("/proj"))).success is False
        assert (await storage.stat(path=Path("/proj/f.txt"))).success is False
        # Nothing landed in trash: the purge never mints the bucket chain.
        assert (await storage.stat(path=Path("/.vfs/trash"))).success is False

    @needs("write", "stat")
    async def test_sweep_purges_a_single_file(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        result = await storage.sweep(path=Path("/a.txt"))
        assert result.success is True
        assert result.observations[0].status == "deleted"
        assert result.observations[0].trash_path is None
        assert (await storage.stat(path=Path("/a.txt"))).success is False

    async def test_sweep_of_the_root_is_invalid(self, storage: ConformanceBackend) -> None:
        result = await storage.sweep(path=Path("/"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid

    async def test_sweep_of_a_missing_address_is_not_found(self, storage: ConformanceBackend) -> None:
        result = await storage.sweep(path=Path("/ghost"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found

    @needs("write", "delete", "stat")
    async def test_sweep_of_a_bucket_address_reclaims_it_regardless_of_age(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deleted = await storage.delete(path=Path("/a.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        bucket = trash_path.parent_dir
        result = await storage.sweep(path=bucket)
        assert result.success is True
        assert (await storage.stat(path=bucket)).success is False
        # The trash root itself survives per-bucket reclamation.
        assert (await storage.stat(path=Path("/.vfs/trash"))).success is True

    # ------------------------------------------------------------------
    # glob / grep
    # ------------------------------------------------------------------

    @needs("write", "mkdir", "glob")
    async def test_glob_matches_by_name_without_a_slash_in_the_pattern(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a/b"), parents=True)
        await storage.write(entries=[Entry(path=Path("/a/b/x.py"), content="x")])
        result = await storage.glob(patterns=("x.py",))
        assert [o.path for o in result.observations] == ["/a/b/x.py"]

    @needs("write", "mkdir", "glob")
    async def test_glob_matches_full_path_when_pattern_has_a_slash(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a/b"), parents=True)
        await storage.write(entries=[Entry(path=Path("/a/b/x.py"), content="x")])
        result = await storage.glob(patterns=("**/x.py",))
        assert [o.path for o in result.observations] == ["/a/b/x.py"]

    @needs("write", "mkdir", "glob")
    async def test_glob_segment_semantics_acceptance_table(self, storage: ConformanceBackend) -> None:
        # The spec's demo tree: * within a segment, ** across segments,
        # any / anchors at the root, no / floats by name.
        await storage.mkdir(path=Path("/docs/deep/nested"), parents=True)
        for path in ("/notes.txt", "/docs/a.txt", "/docs/deep/nested/b.txt"):
            await storage.write(entries=[Entry(path=Path(path), content="x")])

        async def paths(pattern: str) -> list[str]:
            return [str(o.path) for o in (await storage.glob(patterns=(pattern,))).observations]

        assert await paths("/docs/*.txt") == ["/docs/a.txt"]
        assert await paths("*/b.txt") == []  # depth one, not any depth
        assert await paths("*/a.txt") == ["/docs/a.txt"]
        assert await paths("docs/*.txt") == ["/docs/a.txt"]  # implicit anchor
        assert await paths("docs/[ab].txt") == ["/docs/a.txt"]  # class fallback stays anchored
        assert await paths("/docs/**/*.txt") == ["/docs/a.txt", "/docs/deep/nested/b.txt"]
        assert await paths("*.txt") == ["/docs/a.txt", "/docs/deep/nested/b.txt", "/notes.txt"]
        assert await paths("**/*.txt") == ["/docs/a.txt", "/docs/deep/nested/b.txt", "/notes.txt"]
        assert await paths("/*.txt") == ["/notes.txt"]

    @needs("write", "mkdir", "glob")
    async def test_glob_double_star_zero_depth_match_is_not_lost(self, storage: ConformanceBackend) -> None:
        # The only match sits at zero depth under ** — the row a broken
        # prefilter silently loses before the verifier can see it.
        await storage.mkdir(path=Path("/docs"))
        await storage.write(entries=[Entry(path=Path("/docs/a.txt"), content="x")])
        result = await storage.glob(patterns=("/docs/**/*.txt",))
        assert [str(o.path) for o in result.observations] == ["/docs/a.txt"]

    @needs("write", "glob")
    async def test_glob_mid_component_double_star_classifies_invalid(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/axxb.txt"), content="x")])
        for pattern in ("a**b.txt", "/x/a**b.txt", "***"):
            result = await storage.glob(patterns=(pattern,))
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.invalid
            assert result.observations == []

    @needs("write", "glob")
    async def test_glob_empty_component_classifies_invalid(self, storage: ConformanceBackend) -> None:
        # No stored path has an empty segment; silent empty success (or a
        # normalized match the authority rejects) would be a false friend.
        await storage.write(entries=[Entry(path=Path("/data.txt"), content="x")])
        for pattern in ("/data/", "data/", "//x", "/*/", "/"):
            result = await storage.glob(patterns=(pattern,))
            assert result.success is False, pattern
            assert result.errors[0].kind == VFSErrorKind.invalid
            assert result.observations == []

    @needs("write", "glob")
    async def test_glob_bare_double_star_name_pattern_behaves_as_star(self, storage: ConformanceBackend) -> None:
        for name in ("a.py", "b.txt"):
            await storage.write(entries=[Entry(path=Path(f"/{name}"), content="x")])
        starred = await storage.glob(patterns=("*",))
        doubled = await storage.glob(patterns=("**",))
        assert [o.path for o in doubled.observations] == [o.path for o in starred.observations]

    @needs("write", "glob")
    async def test_glob_dotfiles_match_wildcards(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/.env"), content="x")])
        await storage.write(entries=[Entry(path=Path("/real.txt"), content="x")])
        result = await storage.glob(patterns=("*",))
        assert [str(o.path) for o in result.observations] == ["/.env", "/real.txt"]

    @needs("write", "glob")
    async def test_glob_pure_dotfile_matches_the_pattern_but_not_the_ext_filter(
        self, storage: ConformanceBackend
    ) -> None:
        # A file literally named ".txt": the pattern matches it, while the
        # ext filter drops it — its lexical extension is None, not "txt".
        await storage.write(entries=[Entry(path=Path("/.txt"), content="x")])
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        matched = await storage.glob(patterns=("*.txt",))
        assert [str(o.path) for o in matched.observations] == ["/.txt", "/a.txt"]
        filtered = await storage.glob(patterns=("*.txt",), ext=("txt",))
        assert [str(o.path) for o in filtered.observations] == ["/a.txt"]

    @needs("write", "glob")
    async def test_glob_ext_filter_agrees_with_a_divergent_explicit_ext(self, storage: ConformanceBackend) -> None:
        # The model normalizes ext to the lexical value, so the stored
        # column and the path-derived gate agree on every row.
        result = await storage.write(entries=[Entry(path=Path("/b.txt"), content="x", ext="png")])
        assert result.success is True
        kept = await storage.glob(patterns=("*",), ext=("txt",))
        assert [str(o.path) for o in kept.observations] == ["/b.txt"]
        dropped = await storage.glob(patterns=("*",), ext=("png",))
        assert dropped.observations == []

    @needs("write", "move", "glob")
    async def test_move_rederives_the_stored_ext_at_the_new_name(self, storage: ConformanceBackend) -> None:
        # A rename changes the lexical extension; the stored column must
        # follow it or the ext filter silently loses the row.
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        moved = await storage.move(operations=[ResolvedPair(src=Path("/a.txt"), dest=Path("/b.png"))])
        assert moved.success is True
        kept = await storage.glob(patterns=("*",), ext=("png",))
        assert [str(o.path) for o in kept.observations] == ["/b.png"]
        assert (await storage.glob(patterns=("*",), ext=("txt",))).observations == []

    @needs("write", "copy", "glob")
    async def test_copy_rederives_the_stored_ext_at_the_new_name(self, storage: ConformanceBackend) -> None:
        # Both copy arms rename the root: the fresh-row arm and the
        # overwrite arm that clobbers an occupant's material in place.
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        copied = await storage.copy(operations=[ResolvedPair(src=Path("/a.txt"), dest=Path("/b.png"))])
        assert copied.success is True
        fresh = await storage.glob(patterns=("*",), ext=("png",))
        assert [str(o.path) for o in fresh.observations] == ["/b.png"]
        await storage.write(entries=[Entry(path=Path("/c.md"), content="y")])
        clobber = await storage.copy(operations=[ResolvedPair(src=Path("/a.txt"), dest=Path("/c.md"))], overwrite=True)
        assert clobber.success is True
        clobbered = await storage.glob(patterns=("*",), ext=("md",))
        assert [str(o.path) for o in clobbered.observations] == ["/c.md"]

    @needs("write", "mkdir", "copy", "glob")
    async def test_copy_keeps_interior_row_ext_under_a_renamed_root(self, storage: ConformanceBackend) -> None:
        # Only the renamed root re-derives; interior rows keep their own
        # names, and their stored ext must keep feeding the pushdown.
        await storage.mkdir(path=Path("/src"))
        await storage.write(entries=[Entry(path=Path("/src/x.py"), content="x")])
        assert (await storage.copy(operations=[ResolvedPair(src=Path("/src"), dest=Path("/d.png"))])).success is True
        kept = await storage.glob(patterns=("**",), ext=("py",))
        assert [str(o.path) for o in kept.observations] == ["/d.png/x.py", "/src/x.py"]

    @needs("write", "mkdir", "move", "glob")
    async def test_move_keeps_interior_row_ext_under_a_renamed_root(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/src"))
        await storage.write(entries=[Entry(path=Path("/src/x.py"), content="x")])
        assert (await storage.move(operations=[ResolvedPair(src=Path("/src"), dest=Path("/d.png"))])).success is True
        kept = await storage.glob(patterns=("**",), ext=("py",))
        assert [str(o.path) for o in kept.observations] == ["/d.png/x.py"]

    @needs("write", "glob")
    async def test_glob_filters_by_extension(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.py"), content="x")])
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        result = await storage.glob(patterns=("a.*",), ext=("py",))
        assert [o.path for o in result.observations] == ["/a.py"]

    @needs("write", "glob")
    async def test_glob_respects_max_count(self, storage: ConformanceBackend) -> None:
        for name in ("a.py", "b.py", "c.py"):
            await storage.write(entries=[Entry(path=Path(f"/{name}"), content="x")])
        result = await storage.glob(patterns=("*.py",), max_count=2)
        assert len(result.observations) == 2

    @needs("write", "glob")
    async def test_glob_max_count_takes_the_first_n_in_path_order(self, storage: ConformanceBackend) -> None:
        for name in ("a.py", "b.py", "c.py", "d.py"):
            await storage.write(entries=[Entry(path=Path(f"/{name}"), content="x")])
        result = await storage.glob(patterns=("*.py",), max_count=2)
        assert [o.path for o in result.observations] == ["/a.py", "/b.py"]

    @needs("write", "glob")
    async def test_glob_question_mark_matches_exactly_one_character(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.py"), content="x")])
        await storage.write(entries=[Entry(path=Path("/ab.py"), content="x")])
        result = await storage.glob(patterns=("?.py",))
        assert [o.path for o in result.observations] == ["/a.py"]

    @needs("write", "glob")
    async def test_glob_ext_filter_normalizes_dot_and_case(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/notes.md"), content="x")])
        await storage.write(entries=[Entry(path=Path("/a.py"), content="x")])
        result = await storage.glob(patterns=("*",), ext=(".MD",))
        assert [o.path for o in result.observations] == ["/notes.md"]

    @needs("write", "mkdir", "glob")
    async def test_glob_ext_matches_the_path_derived_extension(self, storage: ConformanceBackend) -> None:
        # One lexical law for every kind: a dot-named directory stores
        # ext "py" and the filter (gate and pushdown alike) honors it.
        await storage.mkdir(path=Path("/v1.py"))
        await storage.write(entries=[Entry(path=Path("/v1.py/a.py"), content="x")])
        result = await storage.glob(patterns=("*",), ext=("py",))
        assert [o.path for o in result.observations] == ["/v1.py", "/v1.py/a.py"]

    @needs("write", "mkdir", "glob")
    async def test_glob_batches_patterns_as_one_any_match_call(self, storage: ConformanceBackend) -> None:
        # The batched contract: one call, rows matching any pattern,
        # overlapping patterns yielding each row exactly once.
        await storage.write(entries=[Entry(path=Path("/docs/a.txt"), content="x")], parents=True)
        await storage.write(entries=[Entry(path=Path("/docs/b.md"), content="x")])
        await storage.write(entries=[Entry(path=Path("/other.py"), content="x")])
        result = await storage.glob(patterns=("/docs/**/*.txt", "/docs/*.md", "*.txt"))
        assert [str(o.path) for o in result.observations] == ["/docs/a.txt", "/docs/b.md"]

    @needs("write", "glob")
    async def test_glob_one_defective_pattern_refuses_the_batch_whole(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        result = await storage.glob(patterns=("*.txt", "a**b"))
        assert result.success is False
        assert result.observations == []
        assert [e.kind for e in result.errors] == [VFSErrorKind.invalid]

    @needs("write", "mkdir", "glob")
    async def test_glob_exclusions_gate_beside_the_authority(self, storage: ConformanceBackend) -> None:
        # Exclusions never prefilter in SQL — an over-approximating NOT
        # LIKE would wrongly exclude — so the compiled gates decide.
        await storage.mkdir(path=Path("/src/tests"), parents=True)
        await storage.write(entries=[Entry(path=Path("/src/a.py"), content="x")])
        await storage.write(entries=[Entry(path=Path("/src/tests/b.py"), content="x")])
        result = await storage.glob(patterns=("/src/**/*.py",), globs_not=("/src/tests/**",))
        assert [str(o.path) for o in result.observations] == ["/src/a.py"]
        by_name = await storage.glob(patterns=("*.py",), globs_not=("b.*",))
        assert [str(o.path) for o in by_name.observations] == ["/src/a.py"]

    @needs("write", "glob")
    async def test_glob_ext_not_drops_the_derived_extension(self, storage: ConformanceBackend) -> None:
        for name in ("a.py", "b.txt"):
            await storage.write(entries=[Entry(path=Path(f"/{name}"), content="x")])
        result = await storage.glob(patterns=("*",), ext_not=(".PY",))
        assert [str(o.path) for o in result.observations] == ["/b.txt"]

    @needs("write", "mkdir", "glob")
    async def test_glob_kind_filters_rows_exactly(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/dir"))
        await storage.write(entries=[Entry(path=Path("/file.txt"), content="x")])
        directories = await storage.glob(patterns=("*",), kind="directory")
        assert [str(o.path) for o in directories.observations] == ["/dir"]
        files = await storage.glob(patterns=("*",), kind="file")
        assert [str(o.path) for o in files.observations] == ["/file.txt"]

    @needs("write", "glob")
    async def test_glob_defective_exclusion_refuses_the_call_whole(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        result = await storage.glob(patterns=("*.txt",), globs_not=("a**b",))
        assert result.success is False
        assert result.observations == []
        assert [e.kind for e in result.errors] == [VFSErrorKind.invalid]

    # ------------------------------------------------------------------
    # LIKE metacharacters in stored paths — near-miss decoys never leak
    # ------------------------------------------------------------------

    @needs("write", "read")
    async def test_metachar_paths_write_and_read_exactly(self, storage: ConformanceBackend) -> None:
        await _mint_metachar_tree(storage)
        for name in METACHAR_DIRS:
            result = await storage.read(path=Path(f"/{name}/inner.txt"))
            assert result.observations[0].content == name

    @needs("write", "tree")
    async def test_tree_under_a_metachar_name_excludes_like_near_misses(self, storage: ConformanceBackend) -> None:
        # An unescaped "/a%b/%" or "/a_b/%" prefix would sweep in the
        # decoys' children; "/a\b/%" would collapse onto "/ab/%".
        await _mint_metachar_tree(storage)
        for name in METACHAR_DIRS:
            result = await storage.tree(path=Path(f"/{name}"))
            assert [str(o.path) for o in result.observations] == [f"/{name}/inner.txt"]

    @needs("write", "glob")
    async def test_glob_pattern_prefix_with_metachars_stays_inside_its_subtree(
        self, storage: ConformanceBackend
    ) -> None:
        # The pattern's literal prefix must escape LIKE metachars, or
        # the decoy siblings' children leak into the fan. Glob metachars
        # in the stored name cross as escaped pattern text — the form
        # every composed scope root arrives in.
        await _mint_metachar_tree(storage)
        for name in METACHAR_DIRS:
            result = await storage.glob(patterns=(escape_glob(f"/{name}") + "/**/*",))
            assert [str(o.path) for o in result.observations] == [f"/{name}/inner.txt"]

    @needs("write", "glob")
    async def test_glob_pattern_with_literal_metachars_matches_literally(self, storage: ConformanceBackend) -> None:
        for name in ("100%.txt", "100p.txt", "x_y.txt", "xzy.txt"):
            result = await storage.write(entries=[Entry(path=Path(f"/m/{name}"), content="x")], parents=True)
            assert result.success is True
        percent = await storage.glob(patterns=("100%*",))
        assert [str(o.path) for o in percent.observations] == ["/m/100%.txt"]
        underscore = await storage.glob(patterns=("x_y*",))
        assert [str(o.path) for o in underscore.observations] == ["/m/x_y.txt"]

    @needs("write", "delete", "tree", "stat")
    async def test_cascade_delete_of_a_metachar_directory_takes_only_its_subtree(
        self, storage: ConformanceBackend
    ) -> None:
        # The cascade collects and rewrites by prefix, and the trash row's
        # name keeps the metachars — the trash-side tree re-runs the scan.
        await _mint_metachar_tree(storage)
        result = await storage.delete(path=Path("/a%b"))
        assert result.success is True
        trash_path = result.observations[0].trash_path
        assert trash_path is not None
        for name in (*(n for n in METACHAR_DIRS if n != "a%b"), *DECOY_DIRS):
            assert (await storage.stat(path=Path(f"/{name}/inner.txt"))).success is True
        trashed = await storage.tree(path=trash_path)
        assert [str(o.path) for o in trashed.observations] == [f"{trash_path}/inner.txt"]

    @needs("write", "delete", "tree", "stat")
    async def test_cascade_delete_of_a_bracket_directory_leaves_no_orphans(self, storage: ConformanceBackend) -> None:
        # T-SQL LIKE reads [...] as a class: an unescaped bracket prefix
        # trashes the root but strands its live descendants — the orphan
        # shape. The subtree must travel to trash whole.
        await _mint_metachar_tree(storage)
        result = await storage.delete(path=Path("/a[1]b"))
        assert result.success is True
        assert (await storage.stat(path=Path("/a[1]b/inner.txt"))).success is False
        trash_path = result.observations[0].trash_path
        assert trash_path is not None
        trashed = await storage.tree(path=trash_path)
        assert [str(o.path) for o in trashed.observations] == [f"{trash_path}/inner.txt"]
        for name in (*(n for n in METACHAR_DIRS if n != "a[1]b"), *DECOY_DIRS):
            assert (await storage.stat(path=Path(f"/{name}/inner.txt"))).success is True

    @needs("write", "move", "tree", "stat")
    async def test_move_of_a_bracket_directory_carries_its_whole_subtree(self, storage: ConformanceBackend) -> None:
        # Move composes the same descendant filter; the class miss would
        # leave the child behind under a path that no longer exists.
        await _mint_metachar_tree(storage)
        result = await storage.move(operations=[ResolvedPair(src=Path("/a[1]b"), dest=Path("/moved"))])
        assert result.success is True
        assert (await storage.stat(path=Path("/a[1]b/inner.txt"))).success is False
        assert (await storage.stat(path=Path("/moved/inner.txt"))).success is True
        for name in DECOY_DIRS:
            assert (await storage.stat(path=Path(f"/{name}/inner.txt"))).success is True

    # ------------------------------------------------------------------
    # Enumeration liveness — the /.vfs meta scope
    # ------------------------------------------------------------------

    @needs("write", "ls", "tree", "glob")
    async def test_default_enumeration_hides_the_meta_subtree(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/real.txt"), content="x")])
        await storage.write(entries=[Entry(path=Path("/.vfs/state/s.txt"), content="m")], parents=True)
        assert [o.path for o in (await storage.ls(path=Path("/"))).observations] == ["/real.txt"]
        assert [o.path for o in (await storage.tree(path=Path("/"))).observations] == ["/real.txt"]
        assert [o.path for o in (await storage.glob(patterns=("*",))).observations] == ["/real.txt"]

    @needs("write", "ls", "glob")
    async def test_meta_addressing_serves_its_own_subtree(self, storage: ConformanceBackend) -> None:
        # The glob bypass is a property of what the caller wrote: a
        # meta literal prefix lifts the exclusion; a wildcard head
        # never does.
        await storage.write(entries=[Entry(path=Path("/.vfs/state/s.txt"), content="m")], parents=True)
        listing = await storage.ls(path=Path("/.vfs/state"))
        assert [o.path for o in listing.observations] == ["/.vfs/state/s.txt"]
        literal = await storage.glob(patterns=("/.vfs/state/**/*",))
        assert [o.path for o in literal.observations] == ["/.vfs/state/s.txt"]
        wildcard = await storage.glob(patterns=("/.v*/state/**/*",))
        assert wildcard.success is True
        assert wildcard.observations == []

    @needs("write", "grep")
    async def test_default_grep_hides_the_meta_subtree(self, storage: ConformanceBackend) -> None:
        # The lift is a property of what the caller wrote: a meta-literal
        # glob opens the subtree; a wildcard-headed glob never does.
        await storage.write(entries=[Entry(path=Path("/real.txt"), content="needle in the open")])
        await storage.write(entries=[Entry(path=Path("/.vfs/state/s.txt"), content="needle hidden")], parents=True)
        default = await storage.grep(pattern="needle")
        assert [o.path for o in default.observations] == ["/real.txt"]
        literal = await storage.grep(pattern="needle", globs=("/.vfs/state/**",))
        assert [o.path for o in literal.observations] == ["/.vfs/state/s.txt"]
        wildcard = await storage.grep(pattern="needle", globs=("/.v*/state/**",))
        assert wildcard.success is True
        assert wildcard.observations == []

    @needs("write", "grep")
    async def test_grep_default_case_mode_is_sensitive(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="hello world")])
        result = await storage.grep(pattern="Hello")
        assert result.observations == []

    @needs("write", "grep")
    async def test_grep_insensitive_case_mode_ignores_case(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="hello world")])
        result = await storage.grep(pattern="HELLO", case_mode="insensitive")
        assert [o.path for o in result.observations] == ["/a.txt"]

    @needs("write", "grep")
    async def test_grep_smart_case_mode_is_insensitive_for_a_lowercase_pattern(
        self, storage: ConformanceBackend
    ) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="Hello World")])
        result = await storage.grep(pattern="hello", case_mode="smart")
        assert [o.path for o in result.observations] == ["/a.txt"]

    @needs("write", "grep")
    async def test_grep_fixed_strings_treats_the_pattern_literally(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/dot.txt"), content="a.b")])
        await storage.write(entries=[Entry(path=Path("/any.txt"), content="axb")])
        result = await storage.grep(pattern="a.b", fixed_strings=True)
        assert [o.path for o in result.observations] == ["/dot.txt"]

    @needs("write", "grep")
    async def test_grep_word_regexp_matches_whole_words_only(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/whole.txt"), content="cat scratched")])
        await storage.write(entries=[Entry(path=Path("/sub.txt"), content="concatenate")])
        result = await storage.grep(pattern="cat", word_regexp=True)
        assert [o.path for o in result.observations] == ["/whole.txt"]

    @needs("write", "grep")
    async def test_grep_invert_match_returns_non_matching_lines(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="keep\nmatch")])
        result = await storage.grep(pattern="match", invert_match=True)
        matches = result.observations[0].matches
        assert matches is not None
        assert len(matches) == 1
        assert matches[0].content == "keep"

    @needs("write", "grep")
    async def test_grep_output_mode_files_omits_content(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle")])
        result = await storage.grep(pattern="needle", output_mode="files")
        row = result.observations[0]
        assert row.content is None
        assert row.matches is None

    @needs("write", "grep")
    async def test_grep_output_mode_count_reports_match_count(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle\nneedle\nneedle")])
        result = await storage.grep(pattern="needle", output_mode="count")
        row = result.observations[0]
        assert row.score == 3.0
        assert row.content is None

    @needs("write", "grep")
    async def test_grep_max_count_limits_matches_per_row(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle\nneedle\nneedle")])
        result = await storage.grep(pattern="needle", output_mode="count", max_count=1)
        assert result.observations[0].score == 1.0

    @needs("grep")
    async def test_grep_rejects_an_uncompilable_pattern_as_invalid(self, storage: ConformanceBackend) -> None:
        result = await storage.grep(pattern="(")
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid

    @needs("write", "grep")
    async def test_grep_accepts_allow_scan(self, storage: ConformanceBackend) -> None:
        # The opt-out into an index-refusing backend's scan tier; a
        # scan-tier backend accepts it as a no-op. An indexable pattern
        # succeeds under it everywhere.
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle here")])
        result = await storage.grep(pattern="needle", allow_scan=True)
        assert result.success is True
        assert [o.path for o in result.observations] == ["/a.txt"]

    # ------------------------------------------------------------------
    # Grep pattern-class taxonomy — fully / partially / unindexable
    # ------------------------------------------------------------------

    @needs("write", "grep")
    async def test_grep_fully_indexable_patterns_serve_under_the_default_gate(
        self, storage: ConformanceBackend
    ) -> None:
        # Long literals and alternations of long literals carry required
        # grams — no opt-out needed on any tier.
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha line")])
        await storage.write(entries=[Entry(path=Path("/b.txt"), content="beta line")])
        literal = await storage.grep(pattern="alpha")
        assert [o.path for o in literal.observations] == ["/a.txt"]
        alternation = await storage.grep(pattern="alpha|beta")
        assert sorted(o.path for o in alternation.observations) == ["/a.txt", "/b.txt"]

    @needs("write", "grep")
    async def test_grep_partially_indexable_pattern_serves_under_the_default_gate(
        self, storage: ConformanceBackend
    ) -> None:
        # Literals embedded among match-anything runs still plan grams;
        # the wildcard gap is verified, not planned.
        await storage.write(entries=[Entry(path=Path("/hit.txt"), content="alpha bridge omega")])
        await storage.write(entries=[Entry(path=Path("/half.txt"), content="alpha only")])
        result = await storage.grep(pattern="alpha.*omega")
        assert [o.path for o in result.observations] == ["/hit.txt"]

    @needs("write", "grep")
    async def test_grep_unindexable_patterns_refuse_loudly_on_the_indexed_tier(
        self, storage: ConformanceBackend
    ) -> None:
        # Sub-gram literals, match-all shapes, and an alternation with an
        # unindexable branch: a classified refusal, never a silent [].
        if not _indexed_grep_tier(storage):
            pytest.skip("scan-tier backends serve every compilable pattern")
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="ab alpha")])
        for pattern in ("ab", ".*", "alpha|ab"):
            result = await storage.grep(pattern=pattern)
            assert result.success is False, pattern
            assert result.errors[0].kind == VFSErrorKind.unindexable_pattern
            assert "allow_scan=True" in result.errors[0].message
            assert result.observations == []

    @needs("write", "grep")
    async def test_grep_fold_shortening_flips_indexable_to_refused(self, storage: ConformanceBackend) -> None:
        # 'ẞ' is three raw bytes but folds to two ('ss') — the folded
        # index cannot serve it; the opt-out still answers sensitively.
        if not _indexed_grep_tier(storage):
            pytest.skip("scan-tier backends serve every compilable pattern")
        await storage.write(entries=[Entry(path=Path("/sharp.txt"), content="GROẞE")])
        await storage.write(entries=[Entry(path=Path("/fold.txt"), content="grosse")])
        refused = await storage.grep(pattern="ẞ")
        assert refused.success is False
        assert refused.errors[0].kind == VFSErrorKind.unindexable_pattern
        scanned = await storage.grep(pattern="ẞ", allow_scan=True)
        assert [o.path for o in scanned.observations] == ["/sharp.txt"]

    # ------------------------------------------------------------------
    # Reindex — the index tier actually builds and serves, per engine
    # ------------------------------------------------------------------

    @needs("write", "grep")
    async def test_reindex_builds_and_the_indexed_tier_serves(self, storage: ConformanceBackend) -> None:
        # After a successful build the row is index-partitioned — the
        # scan side excludes it, so only a live index can serve it.
        reindexer = _reindexer_of(storage)
        await storage.write(entries=[Entry(path=Path("/idx.txt"), content="magnet needle here")])
        assert (await reindexer.reindex()).success is True
        found = await storage.grep(pattern="magnet")
        assert [o.path for o in found.observations] == ["/idx.txt"]

    @needs("write", "grep")
    async def test_grep_mixed_channel_serves_the_fact_free_arm_in_both_worlds(
        self, storage: ConformanceBackend
    ) -> None:
        # globs mixing a fact-carrying arm (*.py pins ext) with a
        # fact-free arm (docs/** pins no column fact): both rows serve.
        reindexer = _reindexer_of(storage)
        files = (("/src/a.py", "needle py"), ("/docs/readme.md", "needle md"), ("/notes.txt", "needle txt"))
        for text, content in files:
            written = await storage.write(entries=[Entry(path=Path(text), content=content)], parents=True)
            assert written.success is True
        expected = ["/docs/readme.md", "/src/a.py"]
        scanned = await storage.grep(pattern="needle", globs=("*.py", "docs/**"))
        assert [o.path for o in scanned.observations] == expected
        assert (await reindexer.reindex()).success is True
        indexed = await storage.grep(pattern="needle", globs=("*.py", "docs/**"))
        assert [o.path for o in indexed.observations] == expected

    @needs("write", "grep")
    async def test_grep_a_wide_ext_channel_survives_a_saturated_fetch(self, storage: ConformanceBackend) -> None:
        # The engine-cap shape: enough candidates to fill an id chunk
        # plus a 40-member ext ride — the arithmetic must charge the
        # ride's true width so no statement crosses a parameter cap.
        reindexer = _reindexer_of(storage)
        entries = [Entry(path=Path(f"/w/f{i}.x{i % 40:02d}"), content="needle body") for i in range(2_200)]
        assert (await storage.write(entries=entries, parents=True)).success is True
        assert (await reindexer.reindex()).success is True
        wanted = tuple(f"x{i:02d}" for i in range(40))
        found = await storage.grep(pattern="needle", ext=wanted, output_mode="files")
        assert found.success is True, found.errors
        assert len(found.observations) == 2_200

    @needs("write", "grep")
    async def test_reindex_twice_then_a_rewrite_advances_the_epoch(self, storage: ConformanceBackend) -> None:
        # The second build runs the pending probe against a live epoch —
        # a statement surface the first build never reaches.
        reindexer = _reindexer_of(storage)
        await storage.write(entries=[Entry(path=Path("/idx.txt"), content="first magnet")])
        assert (await reindexer.reindex()).success is True
        assert (await reindexer.reindex()).success is True
        rewrite = Entry(path=Path("/idx.txt"), content="second lodestone")
        assert (await storage.write(entries=[rewrite], overwrite=True)).success is True
        assert (await reindexer.reindex()).success is True
        stale = await storage.grep(pattern="magnet")
        assert stale.success is True and stale.observations == []
        fresh = await storage.grep(pattern="lodestone")
        assert [o.path for o in fresh.observations] == ["/idx.txt"]

    @needs("write", "grep", "delete", "restore")
    async def test_restored_content_stays_greppable_after_a_rebuild(self, storage: ConformanceBackend) -> None:
        # The forbidden state: delete → rebuild → restore leaving a live
        # row invisible to both tiers. Coverage exit must demote.
        reindexer = _reindexer_of(storage)
        await storage.write(entries=[Entry(path=Path("/gone.txt"), content="buried needle")])
        assert (await reindexer.reindex()).success is True
        deleted = await storage.delete(path=Path("/gone.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        await storage.write(entries=[Entry(path=Path("/other.txt"), content="steady text")])
        assert (await reindexer.reindex()).success is True  # a rebuild without the trashed row
        assert (await storage.restore(path=trash_path)).success is True
        found = await storage.grep(pattern="buried")
        assert [o.path for o in found.observations] == ["/gone.txt"]
        assert (await reindexer.reindex()).success is True  # and the next build re-covers it
        found = await storage.grep(pattern="buried")
        assert [o.path for o in found.observations] == ["/gone.txt"]

    @needs("write", "grep", "delete")
    async def test_trash_scoped_grep_serves_a_trashed_root_after_a_rebuild(self, storage: ConformanceBackend) -> None:
        reindexer = _reindexer_of(storage)
        await storage.write(entries=[Entry(path=Path("/gone.txt"), content="buried needle")])
        assert (await reindexer.reindex()).success is True
        deleted = await storage.delete(path=Path("/gone.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        assert (await reindexer.reindex()).success is True
        assert (await storage.grep(pattern="buried")).observations == []  # default scope hides trash
        found = await storage.grep(pattern="buried", globs=(str(trash_path),))
        assert [o.path for o in found.observations] == [trash_path]

    @needs("write", "grep")
    async def test_a_needle_straddling_the_split_cut_is_served_after_reindex(self, storage: ConformanceBackend) -> None:
        # The minimal boundary shape: the needle's bytes sit on both
        # sides of a 2048 split cut; nomination must be immune to it.
        reindexer = _reindexer_of(storage)
        body = "a" * 2045 + "straddle_needle" + "b" * 3000
        await storage.write(entries=[Entry(path=Path("/cut.txt"), content=body)])
        assert (await reindexer.reindex()).success is True
        found = await storage.grep(pattern="straddle_needle")
        assert [o.path for o in found.observations] == ["/cut.txt"]

    @needs("write", "grep")
    async def test_long_single_line_bodies_stay_greppable_after_reindex(self, storage: ConformanceBackend) -> None:
        # The ETL corpus shape: lines longer than any split budget
        # (minified JSON, long log lines) keep every match after a build.
        reindexer = _reindexer_of(storage)
        minified = "{" + ",".join(f'"key_{i}":"{"x" * 40}"' for i in range(60)) + "}"
        log_line = "ts=17 level=info " + "f" * 4096 + " marker_after_4k trailer"
        entries = [Entry(path=Path("/data.json"), content=minified), Entry(path=Path("/app.log"), content=log_line)]
        await storage.write(entries=entries)
        assert (await reindexer.reindex()).success is True
        assert [o.path for o in (await storage.grep(pattern="key_59")).observations] == ["/data.json"]
        assert [o.path for o in (await storage.grep(pattern="marker_after_4k")).observations] == ["/app.log"]

    @needs("write", "grep")
    async def test_a_needle_with_interior_whitespace_survives_a_rebuild(self, storage: ConformanceBackend) -> None:
        # Splitters may drop whitespace-only spans; extraction must see
        # every byte of the body, interior space runs included.
        reindexer = _reindexer_of(storage)
        body = "pad = '" + "p" * 2030 + "'\nleft_anchor      right_anchor\n"
        await storage.write(entries=[Entry(path=Path("/mod.py"), content=body)])
        assert (await reindexer.reindex()).success is True
        found = await storage.grep(pattern="left_anchor      right_anchor")
        assert [o.path for o in found.observations] == ["/mod.py"]

    # ------------------------------------------------------------------
    # mkedge
    # ------------------------------------------------------------------

    @needs("write", "mkedge")
    async def test_mkedge_requires_both_endpoints_to_exist(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/src.py"), content="x")])
        result = await storage.mkedge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found
        assert result.errors[0].path == "/dst.py"

    @needs("write", "mkedge")
    async def test_mkedge_observes_the_source_entry_with_the_edge_type(self, storage: ConformanceBackend) -> None:
        # An edge is entry-scoped metadata, not a namespace row: the
        # observation names the owning source entry, never a derived path.
        await storage.write(entries=[Entry(path=Path("/src.py"), content="x")])
        await storage.write(entries=[Entry(path=Path("/dst.py"), content="x")])
        result = await storage.mkedge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
        assert result.success is True
        row = result.observations[0]
        assert row.path == "/src.py"
        assert row.edge_type == "imports"
        assert row.status == "created"

    @needs("write", "mkedge")
    async def test_mkedge_rejects_an_unlawful_edge_type_as_invalid(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/src.py"), content="x")])
        await storage.write(entries=[Entry(path=Path("/dst.py"), content="x")])
        result = await storage.mkedge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="im/ports")
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid

    @needs("write", "mkedge")
    async def test_mkedge_second_call_reports_updated(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/src.py"), content="x")])
        await storage.write(entries=[Entry(path=Path("/dst.py"), content="x")])
        await storage.mkedge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
        result = await storage.mkedge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
        assert result.observations[0].status == "updated"

    # ------------------------------------------------------------------
    # Per-row classification for batched reads
    # ------------------------------------------------------------------

    @needs("write", "read")
    async def test_read_batch_classifies_each_row_and_keeps_the_good_ones(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="a")])
        await storage.write(entries=[Entry(path=Path("/b.txt"), content="b")])
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

    @needs("write", "mkdir", "read")
    async def test_read_batch_classifies_a_wrong_kind_row_alongside_good_ones(
        self, storage: ConformanceBackend
    ) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="a")])
        await storage.mkdir(path=Path("/d"))
        result = await storage.read(observations=[Observation(path=Path("/a.txt")), Observation(path=Path("/d"))])
        assert result.success is False
        assert len(result.observations) == 1
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        assert result.errors[0].path == "/d"

    @needs("read")
    async def test_read_single_path_keeps_the_fail_whole_shape(self, storage: ConformanceBackend) -> None:
        result = await storage.read(path=Path("/missing.txt"))
        assert result.success is False
        assert result.observations == []
        assert len(result.errors) == 1

    @needs("write", "stat")
    async def test_stat_batch_classifies_each_row(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="a")])
        observations = [Observation(path=Path("/a.txt")), Observation(path=Path("/missing.txt"))]
        result = await storage.stat(observations=observations)
        assert result.success is False
        assert [o.path for o in result.observations] == ["/a.txt"]
        assert len(result.errors) == 1
        assert result.errors[0].path == "/missing.txt"

    @needs("stat")
    async def test_stat_single_path_keeps_the_fail_whole_shape(self, storage: ConformanceBackend) -> None:
        result = await storage.stat(path=Path("/missing.txt"))
        assert result.success is False
        assert result.observations == []

    @needs("write", "ls")
    async def test_ls_batch_groups_children_under_their_own_parents(self, storage: ConformanceBackend) -> None:
        await storage.write(
            entries=[
                Entry(path=Path("/a/n.txt"), content="1"),
                Entry(path=Path("/a/m.txt"), content="2"),
                Entry(path=Path("/b/z.txt"), content="3"),
                Entry(path=Path("/b/y.txt"), content="4"),
            ],
            parents=True,
        )
        result = await storage.ls(observations=[Observation(path=Path("/b")), Observation(path=Path("/a"))])
        assert result.success is True
        # Each child under its own anchor, anchors in target order,
        # children name-ordered within each parent.
        assert [str(o.path) for o in result.observations] == ["/b/y.txt", "/b/z.txt", "/a/m.txt", "/a/n.txt"]

    @needs("write", "mkdir", "ls")
    async def test_ls_batch_classifies_each_row(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        await storage.write(entries=[Entry(path=Path("/a/f.txt"), content="x")])
        observations = [Observation(path=Path("/a")), Observation(path=Path("/missing"))]
        result = await storage.ls(observations=observations)
        assert result.success is False
        assert [o.path for o in result.observations] == ["/a/f.txt"]
        assert len(result.errors) == 1
        assert result.errors[0].path == "/missing"

    @needs("ls")
    async def test_ls_single_path_keeps_the_fail_whole_shape(self, storage: ConformanceBackend) -> None:
        result = await storage.ls(path=Path("/missing"))
        assert result.success is False
        assert result.observations == []

    # ------------------------------------------------------------------
    # Version stamping and the populated mask
    # ------------------------------------------------------------------

    @needs("write", "mkdir", "stat", "read", "ls", "tree", "glob", "grep")
    async def test_every_observation_carries_revision_and_the_identity_mask(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        await storage.write(entries=[Entry(path=Path("/a/f.txt"), content="x")])
        for result in (
            await storage.stat(path=Path("/a/f.txt")),
            await storage.read(path=Path("/a/f.txt")),
            await storage.ls(path=Path("/a")),
            await storage.tree(path=Path("/a")),
            await storage.glob(patterns=("*.txt",)),
            await storage.grep(pattern="x"),
        ):
            for o in result.observations:
                assert o.version is not None
                assert {"path", "kind", "version"} <= o.populated

    @needs("write", "stat", "read", "ls", "glob")
    async def test_the_mask_never_omits_a_populated_field(self, storage: ConformanceBackend) -> None:
        # The mask may exceed the non-null fields (fetched-but-null is
        # legal) but must never omit a field that carries a value.
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        for result in (
            await storage.stat(path=Path("/a.txt")),
            await storage.read(path=Path("/a.txt")),
            await storage.ls(path=Path("/")),
            await storage.glob(patterns=("*.txt",)),
        ):
            for o in result.observations:
                valued = {f for f in OBSERVATION_FIELDS if getattr(o, f) is not None}
                assert valued <= o.populated, f"mask omits populated fields: {valued - o.populated}"

    @needs("write", "stat")
    async def test_material_writes_stamp_strictly_increasing_revisions(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="1")])
        first = await _revision_of(storage, "/a.txt")
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="2")])
        second = await _revision_of(storage, "/a.txt")
        assert second > first

    @needs("write", "mkdir", "stat")
    async def test_namespace_create_bumps_the_parent_but_overwrite_does_not(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/docs"))
        before = await _revision_of(storage, "/docs")
        await storage.write(entries=[Entry(path=Path("/docs/a.md"), content="1")])
        after_create = await _revision_of(storage, "/docs")
        assert after_create > before
        await storage.write(entries=[Entry(path=Path("/docs/a.md"), content="2")])
        assert await _revision_of(storage, "/docs") == after_create

    @needs("write", "mkdir", "edit", "stat")
    async def test_edit_bumps_the_target_not_the_parent(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/docs"))
        await storage.write(entries=[Entry(path=Path("/docs/a.md"), content="old text")])
        parent = await _revision_of(storage, "/docs")
        target = await _revision_of(storage, "/docs/a.md")
        await storage.edit(path=Path("/docs/a.md"), edits=[EditOperation(old="old", new="new")])
        assert await _revision_of(storage, "/docs/a.md") > target
        assert await _revision_of(storage, "/docs") == parent

    @needs("write", "mkdir", "delete", "stat")
    async def test_delete_bumps_the_parent(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/docs"))
        await storage.write(entries=[Entry(path=Path("/docs/a.md"), content="x")])
        before = await _revision_of(storage, "/docs")
        await storage.delete(path=Path("/docs/a.md"))
        assert await _revision_of(storage, "/docs") > before

    @needs("write", "mkdir", "move", "stat")
    async def test_move_stamps_the_root_keeps_descendants_and_bumps_both_parents(
        self, storage: ConformanceBackend
    ) -> None:
        await storage.mkdir(path=Path("/src"))
        await storage.mkdir(path=Path("/dst"))
        await storage.mkdir(path=Path("/src/sub"))
        await storage.write(entries=[Entry(path=Path("/src/sub/f.txt"), content="x")])
        moved_before = await _revision_of(storage, "/src/sub")
        child_before = await _revision_of(storage, "/src/sub/f.txt")
        src_parent_before = await _revision_of(storage, "/src")
        dst_parent_before = await _revision_of(storage, "/dst")
        await storage.move(operations=[ResolvedPair(src=Path("/src/sub"), dest=Path("/dst/sub"))])
        assert await _revision_of(storage, "/dst/sub") > moved_before
        assert await _revision_of(storage, "/dst/sub/f.txt") == child_before
        assert await _revision_of(storage, "/src") > src_parent_before
        assert await _revision_of(storage, "/dst") > dst_parent_before

    @needs("write", "mkdir", "copy", "stat")
    async def test_copy_mints_fresh_revisions_on_every_copied_row(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/src"))
        await storage.write(entries=[Entry(path=Path("/src/f.txt"), content="x")])
        source = await _revision_of(storage, "/src/f.txt")
        await storage.copy(operations=[ResolvedPair(src=Path("/src"), dest=Path("/dst"))])
        # Copied rows are fresh nodes: per-entry versions start at 1, and
        # the source keeps its own value untouched.
        assert await _revision_of(storage, "/dst") == 1
        assert await _revision_of(storage, "/dst/f.txt") == 1
        assert await _revision_of(storage, "/src/f.txt") == source

    @needs("write", "mkdir", "delete", "stat")
    async def test_failed_batch_leaves_revisions_untouched(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/docs"))
        await storage.write(entries=[Entry(path=Path("/docs/a.md"), content="x")])
        parent = await _revision_of(storage, "/docs")
        target = await _revision_of(storage, "/docs/a.md")
        targets = [Observation(path=Path("/docs/a.md")), Observation(path=Path("/missing"))]
        result = await storage.delete(observations=targets)
        assert result.success is False
        assert await _revision_of(storage, "/docs") == parent
        assert await _revision_of(storage, "/docs/a.md") == target

    # ------------------------------------------------------------------
    # Batch observations reflect committed state, never a mid-batch one
    # ------------------------------------------------------------------
    # A version value is never observable before the state it stamps: a
    # later entry/pair in the same batch may re-stamp a row staged earlier
    # (sibling parent bumps, repeated targets), so every observation a
    # successful batch returns must equal a post-commit stat of its path.

    @needs("write", "stat")
    async def test_batch_write_observations_match_the_committed_state(self, storage: ConformanceBackend) -> None:
        result = await storage.write(
            entries=[
                Entry(path=Path("/a"), kind="directory"),
                Entry(path=Path("/a/x.txt"), content="x"),
                Entry(path=Path("/a/y.txt"), content="y"),
            ]
        )
        assert result.success is True
        for o in result.observations:
            committed = (await storage.stat(path=o.path)).observations[0]
            assert o.version == committed.version

    @needs("write", "stat", "read")
    async def test_batch_write_repeated_path_reports_the_committed_row(self, storage: ConformanceBackend) -> None:
        result = await storage.write(
            entries=[Entry(path=Path("/f.txt"), content="first"), Entry(path=Path("/f.txt"), content="second")]
        )
        assert result.success is True
        committed = (await storage.stat(path=Path("/f.txt"))).observations[0]
        assert all(o.version == committed.version for o in result.observations)
        assert (await storage.read(path=Path("/f.txt"))).observations[0].content == "second"

    @needs("write", "mkdir", "move", "stat")
    async def test_batch_move_observations_match_the_committed_state(self, storage: ConformanceBackend) -> None:
        # Pair 2 creates under pair 1's destination, bumping the directory
        # row pair 1 already staged.
        await storage.mkdir(path=Path("/a"))
        await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])
        await storage.mkdir(path=Path("/dst"))
        result = await storage.move(
            operations=[
                ResolvedPair(src=Path("/a"), dest=Path("/dst/a")),
                ResolvedPair(src=Path("/x.txt"), dest=Path("/dst/a/x.txt")),
            ]
        )
        assert result.success is True
        for o in result.observations:
            committed = (await storage.stat(path=o.path)).observations[0]
            assert o.version == committed.version

    @needs("write", "mkdir", "copy", "stat")
    async def test_batch_copy_observations_match_the_committed_state(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/a"))
        await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])
        await storage.mkdir(path=Path("/dst"))
        result = await storage.copy(
            operations=[
                ResolvedPair(src=Path("/a"), dest=Path("/dst/a")),
                ResolvedPair(src=Path("/x.txt"), dest=Path("/dst/a/x.txt")),
            ]
        )
        assert result.success is True
        for o in result.observations:
            committed = (await storage.stat(path=o.path)).observations[0]
            assert o.version == committed.version

    @needs("write", "mkdir", "stat")
    async def test_batch_unchanged_directory_reports_the_bumped_revision(self, storage: ConformanceBackend) -> None:
        # A pre-existing directory forgiven as "unchanged" is still bumped
        # when a later entry creates a child under it — its observation
        # must carry the bump, not its pre-batch version.
        await storage.mkdir(path=Path("/d"))
        result = await storage.write(
            entries=[Entry(path=Path("/d"), kind="directory"), Entry(path=Path("/d/child.txt"), content="x")]
        )
        assert result.success is True
        unchanged = next(o for o in result.observations if str(o.path) == "/d")
        assert unchanged.status == "unchanged"
        committed = (await storage.stat(path=Path("/d"))).observations[0]
        assert unchanged.version == committed.version

    @needs("write", "edit", "stat")
    async def test_batch_edit_repeated_target_reports_the_committed_revision(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="aa")])
        targets = [Observation(path=Path("/f.txt")), Observation(path=Path("/f.txt"))]
        result = await storage.edit(edits=[EditOperation(old="a", new="aa", replace_all=True)], observations=targets)
        assert result.success is True
        committed = (await storage.stat(path=Path("/f.txt"))).observations[0]
        assert all(o.version == committed.version for o in result.observations)

    # ------------------------------------------------------------------
    # Overlapping batch targets are order-independent
    # ------------------------------------------------------------------
    # A cascade delete subsumes requested descendants and repeats, judged
    # against committed state (the S3/fsspec norm); a move refuses
    # duplicate sources and a source inside another moved source as a
    # batch-shape conflict. Per-target errors stamp the requested target
    # into ``data`` so value-identical failures survive merge dedup.

    @needs("write", "mkdir", "delete", "stat")
    async def test_delete_subsumes_a_descendant_of_another_target_in_either_order(
        self, storage: ConformanceBackend
    ) -> None:
        for order in (("/a", "/a/b/c.txt"), ("/a/b/c.txt", "/a")):
            await storage.mkdir(path=Path("/a"))
            await storage.mkdir(path=Path("/a/b"))
            await storage.write(entries=[Entry(path=Path("/a/b/c.txt"), content="x")])
            result = await storage.delete(observations=[Observation(path=Path(p)) for p in order])
            assert result.success is True
            assert {str(o.path) for o in result.observations} == {"/a", "/a/b/c.txt"}
            assert (await storage.stat(path=Path("/a"))).success is False

    @needs("mkdir", "delete", "stat")
    async def test_delete_covered_miss_classifies_the_requested_target(self, storage: ConformanceBackend) -> None:
        # /a/ghost sits inside /a's cascade but never existed: the error
        # names the requested target, never the cascade root.
        await storage.mkdir(path=Path("/a"))
        result = await storage.delete(observations=[Observation(path=Path("/a")), Observation(path=Path("/a/ghost"))])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found
        assert result.errors[0].path == "/a/ghost"
        assert (await storage.stat(path=Path("/a"))).success is True

    @needs("write", "delete", "stat")
    async def test_delete_repeated_target_reports_each_occurrence(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="x")])
        targets = [Observation(path=Path("/f.txt")), Observation(path=Path("/f.txt"))]
        result = await storage.delete(observations=targets)
        assert result.success is True
        assert [str(o.path) for o in result.observations] == ["/f.txt", "/f.txt"]
        assert (await storage.stat(path=Path("/f.txt"))).success is False

    @needs("delete")
    async def test_delete_sibling_misses_under_one_dead_ancestor_stay_distinct(
        self, storage: ConformanceBackend
    ) -> None:
        result = await storage.delete(
            observations=[Observation(path=Path("/dead/x")), Observation(path=Path("/dead/y"))]
        )
        assert result.success is False
        assert len(result.errors) == 2
        assert {(e.data or {}).get("target") for e in result.errors} == {"/dead/x", "/dead/y"}

    @needs("mkdir", "move", "stat")
    async def test_move_refuses_a_source_inside_another_moved_source_in_either_order(
        self, storage: ConformanceBackend
    ) -> None:
        await storage.mkdir(path=Path("/a"))
        await storage.mkdir(path=Path("/a/b"))
        await storage.mkdir(path=Path("/dst"))
        pairs = [
            ResolvedPair(src=Path("/a"), dest=Path("/dst/a")),
            ResolvedPair(src=Path("/a/b"), dest=Path("/dst/b")),
        ]
        for operations in (pairs, list(reversed(pairs))):
            result = await storage.move(operations=operations)
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.invalid
            assert result.errors[0].path == "/a/b"
            assert (await storage.stat(path=Path("/a/b"))).success is True

    @needs("write", "mkdir", "move")
    async def test_move_refuses_duplicate_sources(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="x")])
        await storage.mkdir(path=Path("/d1"))
        await storage.mkdir(path=Path("/d2"))
        result = await storage.move(
            operations=[
                ResolvedPair(src=Path("/f.txt"), dest=Path("/d1/f.txt")),
                ResolvedPair(src=Path("/f.txt"), dest=Path("/d2/f.txt")),
            ]
        )
        assert result.success is False
        assert all(e.kind == VFSErrorKind.invalid for e in result.errors)

    @needs("move")
    async def test_move_duplicate_missing_source_classifies_the_miss(self, storage: ConformanceBackend) -> None:
        # The miss outranks the batch-shape conflict: a duplicated source
        # that never existed classifies not_found at each occurrence.
        result = await storage.move(
            operations=[
                ResolvedPair(src=Path("/ghost"), dest=Path("/a")),
                ResolvedPair(src=Path("/ghost"), dest=Path("/b")),
            ]
        )
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.not_found, VFSErrorKind.not_found]
        assert {str(e.path) for e in result.errors} == {"/ghost"}

    @needs("write", "copy", "read")
    async def test_copy_allows_the_same_source_to_fan_out(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="x")])
        result = await storage.copy(
            operations=[
                ResolvedPair(src=Path("/f.txt"), dest=Path("/c1.txt")),
                ResolvedPair(src=Path("/f.txt"), dest=Path("/c2.txt")),
            ]
        )
        assert result.success is True
        assert (await storage.read(path=Path("/c1.txt"))).observations[0].content == "x"
        assert (await storage.read(path=Path("/c2.txt"))).observations[0].content == "x"

    # ------------------------------------------------------------------
    # Occupant identity, delete observations, unicode round trips
    # ------------------------------------------------------------------

    @needs("write", "delete", "stat")
    async def test_delete_observes_the_pre_delete_row(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/obs.txt"), content="12345")])
        before = (await storage.stat(path=Path("/obs.txt"))).observations[0]
        result = await storage.delete(path=Path("/obs.txt"))
        assert result.success is True
        observed = result.observations[0]
        assert str(observed.path) == "/obs.txt"
        assert observed.status == "deleted"
        assert observed.kind == "file"
        assert observed.version == before.version
        assert observed.size_bytes == before.size_bytes

    @needs("mkdir", "delete", "stat")
    async def test_deleting_an_empty_directory_without_cascade_succeeds(self, storage: ConformanceBackend) -> None:
        await storage.mkdir(path=Path("/empty"))
        assert (await storage.delete(path=Path("/empty"), cascade=False)).success is True
        assert (await storage.stat(path=Path("/empty"))).success is False

    @needs("write", "mkdir", "delete", "stat")
    async def test_delete_batch_may_empty_a_directory_then_delete_it_without_cascade(
        self, storage: ConformanceBackend
    ) -> None:
        # Occupancy reads live state: a target emptied earlier in the
        # batch deletes cleanly even under cascade=False.
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        targets = [Observation(path=Path("/d/f.txt")), Observation(path=Path("/d"))]
        result = await storage.delete(observations=targets, cascade=False)
        assert result.success is True, result.errors
        assert (await storage.stat(path=Path("/d"))).success is False

    @needs("write", "move")
    async def test_move_destination_through_a_file_is_wrong_kind(self, storage: ConformanceBackend) -> None:
        await storage.write(
            entries=[Entry(path=Path("/f.txt"), content="x"), Entry(path=Path("/blocker.txt"), content="x")]
        )
        result = await storage.move(operations=[ResolvedPair(src=Path("/f.txt"), dest=Path("/blocker.txt/f.txt"))])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        assert result.errors[0].path == "/blocker.txt"

    @needs("write", "move", "read", "stat")
    async def test_move_file_over_an_occupied_file_reports_updated(self, storage: ConformanceBackend) -> None:
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha")])
        await storage.write(entries=[Entry(path=Path("/b.txt"), content="beta")])
        result = await storage.move(operations=[ResolvedPair(src=Path("/a.txt"), dest=Path("/b.txt"))], overwrite=True)
        assert result.success is True
        assert result.observations[0].status == "updated"
        assert (await storage.read(path=Path("/b.txt"))).observations[0].content == "alpha"
        assert (await storage.stat(path=Path("/a.txt"))).success is False

    @needs("write", "copy", "read", "stat")
    async def test_copy_file_over_an_occupied_file_updates_it_in_place(self, storage: ConformanceBackend) -> None:
        # The occupant keeps its identity: a material update continuing
        # its version line, never a fresh row at version 1.
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha")])
        await storage.write(entries=[Entry(path=Path("/b.txt"), content="beta")])
        before = await _revision_of(storage, "/b.txt")
        result = await storage.copy(operations=[ResolvedPair(src=Path("/a.txt"), dest=Path("/b.txt"))], overwrite=True)
        assert result.success is True
        assert result.observations[0].status == "updated"
        after = (await storage.stat(path=Path("/b.txt"))).observations[0]
        assert after.version == before + 1
        assert (await storage.read(path=Path("/b.txt"))).observations[0].content == "alpha"
        assert (await storage.read(path=Path("/a.txt"))).observations[0].content == "alpha"

    @needs("write", "read", "stat", "move", "copy", "delete")
    async def test_non_latin1_names_round_trip_through_every_verb(self, storage: ConformanceBackend) -> None:
        # Multibyte names must survive byte-for-byte on every engine — a
        # backend that stores a lossy transcription is out of contract.
        source = Path("/名前/🚀 données.txt")
        moved = Path("/名前/移動-🌕.md")
        copied = Path("/名前/प्रतिलिपि.txt")
        written = await storage.write(entries=[Entry(path=source, content="unicode ✓ содержимое")], parents=True)
        assert written.success is True, written.errors
        assert (await storage.stat(path=source)).success is True
        assert (await storage.read(path=source)).observations[0].content == "unicode ✓ содержимое"
        assert (await storage.move(operations=[ResolvedPair(src=source, dest=moved)])).success is True
        assert (await storage.read(path=moved)).observations[0].content == "unicode ✓ содержимое"
        assert (await storage.copy(operations=[ResolvedPair(src=moved, dest=copied)])).success is True
        listing = await storage.ls(path=Path("/名前"))
        assert sorted(str(o.path) for o in listing.observations) == sorted([str(moved), str(copied)])
        assert (await storage.delete(path=copied)).success is True
        assert (await storage.stat(path=copied)).success is False

    # ------------------------------------------------------------------
    # Declared traits
    # ------------------------------------------------------------------

    async def test_declared_traits_stay_within_the_vocabulary(self, storage: ConformanceBackend) -> None:
        if not isinstance(storage, SupportsTraits):
            pytest.skip("backend declares no traits")
        for key, value in storage.traits().items():
            assert key in TRAIT_KEYS, f"undeclared trait key {key!r}"
            assert value in TRAIT_VALUES[key], f"trait {key!r} value {value!r} outside the vocabulary"

    @needs("grep")
    async def test_grep_tier_traits_are_declared(self, storage: ConformanceBackend) -> None:
        # The battery gates its tier rows on these traits: popping them
        # must fail here, never silently flip those rows to skips.
        if not isinstance(storage, SupportsTraits):
            pytest.fail("a grep-capable backend must declare its tier traits")
        traits = storage.traits()
        assert traits.get("grep_tier") in ("indexed", "scan")
        assert traits.get("grep_staleness") in ("overlay", "none")
