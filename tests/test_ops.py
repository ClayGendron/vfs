"""Drift tests pinning the op vocabulary to its consumers.

The vocabulary in ``vfs.ops`` is the single source of truth for verb names
and dispatch classes; these tests hold the router surface, the permission
gate, and the projection table to it so the sets can never drift apart the
way the three hand-copies once did.
"""

from __future__ import annotations

import inspect

from tests.support.base_doubles import BindableStorage, RecorderFS, RecorderStorage
from vfs import ops, permissions
from vfs.base import VirtualFileSystem
from vfs.ops import ALL_OPS, DEVELOPER_OPS, EXEC_OPS, MUTATING_OPS, READ_OPS, TWO_PATH_OPS
from vfs.results import projection

# Public router methods that manage the mount tree rather than route an op.
# A new public coroutine on VirtualFileSystem must be a registered op or a
# deliberate addition here.
MANAGEMENT_METHODS = frozenset({"add_mount", "remove_mount", "bind", "unbind", "remount", "close"})


# ---------------------------------------------------------------------------
# Set invariants
# ---------------------------------------------------------------------------


def test_all_ops_is_the_union_of_dispatch_classes() -> None:
    assert ALL_OPS == MUTATING_OPS | READ_OPS | EXEC_OPS


def test_dispatch_classes_are_pairwise_disjoint() -> None:
    assert not MUTATING_OPS & READ_OPS
    assert not MUTATING_OPS & EXEC_OPS
    assert not READ_OPS & EXEC_OPS


def test_two_path_ops_are_mutations() -> None:
    assert TWO_PATH_OPS <= MUTATING_OPS


def test_cli_and_rm_are_not_ops() -> None:
    # cli is a meta-verb (parses into real ops); rm lost to delete.
    for banned in ("cli", "rm"):
        assert banned not in ALL_OPS
        assert banned not in TWO_PATH_OPS


def test_expected_vocabulary() -> None:
    assert (
        frozenset(
            {
                "read",
                "write",
                "edit",
                "delete",
                "restore",
                "sweep",
                "stat",
                "mkdir",
                "mkedge",
                "move",
                "copy",
                "ls",
                "tree",
                "glob",
                "grep",
                "glean",
                "graph",
                "run",
            },
        )
        == ALL_OPS
    )


# ---------------------------------------------------------------------------
# Consumers share the one vocabulary
# ---------------------------------------------------------------------------


def test_permission_gate_uses_the_shared_mutation_set() -> None:
    assert permissions.MUTATING_OPS is ops.MUTATING_OPS


def test_projection_derives_action_functions_from_the_shared_set() -> None:
    assert projection.ACTION_FUNCTIONS is ops.MUTATING_OPS


def test_glean_and_run_have_default_projections() -> None:
    assert projection.default_projection("glean") == ("path", "score")
    assert projection.default_projection("run") == ("path",)
    assert "glean" in projection.KNOWN_FUNCTIONS
    assert "run" in projection.KNOWN_FUNCTIONS


def test_pruned_vocabularies_are_gone() -> None:
    # Centrality left the product scope; per-method search names died with
    # the glean redesign (fusion is opaque — no producing method to name).
    assert not hasattr(projection, "CENTRALITY_FUNCTIONS")
    assert not hasattr(projection, "RANKED_SEARCH_FUNCTIONS")
    for stale in ("pagerank", "hits", "vector_search", "semantic_search", "lexical_search", "bm25"):
        assert stale not in projection.KNOWN_FUNCTIONS


# ---------------------------------------------------------------------------
# Developer plane — sweep never reaches an agent surface
# ---------------------------------------------------------------------------


def test_sweep_is_a_developer_plane_op() -> None:
    assert "sweep" in DEVELOPER_OPS
    assert DEVELOPER_OPS <= MUTATING_OPS
    assert not DEVELOPER_OPS & READ_OPS


async def test_no_agent_surface_op_ever_dispatches_sweep() -> None:
    # Route every non-developer op — and the unmount path — through a
    # recording backend: none may dispatch the sweep verb on storage.
    fs = RecorderFS(storage=BindableStorage())
    calls = {
        "read": lambda: fs.read("/f.txt"),
        "stat": lambda: fs.stat("/f.txt"),
        "ls": lambda: fs.ls("/d"),
        "tree": lambda: fs.tree("/"),
        "glob": lambda: fs.glob("*.py"),
        "grep": lambda: fs.grep("needle"),
        "glean": lambda: fs.glean("how does auth work"),
        "graph": lambda: fs.graph("ancestors", "/a.py"),
        "write": lambda: fs.write(path="/f.txt", content="x"),
        "edit": lambda: fs.edit("/f.txt", old="a", new="b"),
        "delete": lambda: fs.delete("/f.txt"),
        "restore": lambda: fs.restore("/f.txt"),
        "mkdir": lambda: fs.mkdir("/d"),
        "mkedge": lambda: fs.mkedge("/a.py", "/b.py", "imports"),
        "move": lambda: fs.move(src="/a.txt", dest="/b.txt"),
        "copy": lambda: fs.copy(src="/a.txt", dest="/b.txt"),
        "run": lambda: fs.run("/tool"),
    }
    assert frozenset(calls) == ALL_OPS - DEVELOPER_OPS
    for call in calls.values():
        result = await call()
        assert result.success is True
    await fs.add_mount(RecorderStorage(name="m"), "/m")
    await fs.remove_mount("/m")
    assert all(op != "sweep" for op, _ in fs.calls)
    # The unmount path removed its directory with the trash delete.
    assert any(op == "delete" for op, _ in fs.calls)


# ---------------------------------------------------------------------------
# Router surface ⊆ vocabulary
# ---------------------------------------------------------------------------


def test_router_public_verbs_are_exactly_the_registered_ops() -> None:
    """The full-equality drift test: the router surface *is* the vocabulary.

    A new public coroutine on the router must be a registered op or a
    deliberate addition to the management allowlist; a registered op with
    no router method is an unbuilt verb.
    """
    verbs = {
        name
        for name, _member in inspect.getmembers(VirtualFileSystem, inspect.iscoroutinefunction)
        if not name.startswith("_")
    }
    assert verbs - MANAGEMENT_METHODS == ALL_OPS
