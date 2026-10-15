"""Drift tests pinning the op vocabulary to its consumers.

The vocabulary in ``vfs.ops`` is the single source of truth for verb names
and dispatch classes; these tests hold the router surface, the permission
gate, and the projection table to it so the sets can never drift apart the
way the three hand-copies once did.
"""

from __future__ import annotations

import inspect
from typing import get_args

from tests.support.base_doubles import BindableStorage, RecorderFS, RecorderStorage
from vfs import ops, permissions
from vfs.base import VirtualFileSystem
from vfs.ops import (
    ALL_OPS,
    DEVELOPER_OPS,
    EXEC_OPS,
    GRANT_OPS,
    GRANT_WRITE_OPS,
    MUTATING_OPS,
    READ_OPS,
    RUNGS,
    TWO_PATH_OPS,
    VERB_RUNGS,
    WRITE_GATED_OPS,
    Rung,
)
from vfs.results import projection
from vfs.storage.grants import LEVEL_RANK

# Public router methods that manage the mount tree rather than route an op.
# A new public coroutine on VirtualFileSystem must be a registered op or a
# deliberate addition here.
MANAGEMENT_METHODS = frozenset(
    {"add_mount", "remove_mount", "bind", "unbind", "remount", "close", "locate", "locate_edge"}
)


# ---------------------------------------------------------------------------
# Set invariants
# ---------------------------------------------------------------------------


def test_all_ops_is_the_union_of_dispatch_classes() -> None:
    assert ALL_OPS == MUTATING_OPS | READ_OPS | EXEC_OPS | GRANT_OPS


def test_dispatch_classes_are_pairwise_disjoint() -> None:
    classes = (MUTATING_OPS, READ_OPS, EXEC_OPS, GRANT_OPS)
    for i, left in enumerate(classes):
        for right in classes[i + 1 :]:
            assert not left & right


def test_the_write_gate_covers_the_mutations_and_the_grant_writes() -> None:
    # Listing grants is the one grant op a read-only mount still answers.
    assert GRANT_OPS - {"grants"} == GRANT_WRITE_OPS
    assert WRITE_GATED_OPS == MUTATING_OPS | GRANT_WRITE_OPS


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
                "rmedge",
                "move",
                "copy",
                "ls",
                "tree",
                "glob",
                "grep",
                "glean",
                "graph",
                "run",
                "grant",
                "revoke",
                "grants",
                "posture",
                "add_member",
                "remove_member",
            },
        )
        == ALL_OPS
    )


# ---------------------------------------------------------------------------
# The verb-to-rung table
# ---------------------------------------------------------------------------


def test_the_ladder_is_the_declared_order_and_the_ranks_are_dense() -> None:
    assert RUNGS == ("none", "list", "read", "add", "contribute", "read_write")
    assert get_args(Rung) == RUNGS
    assert [LEVEL_RANK[rung] for rung in RUNGS] == list(range(len(RUNGS)))


def test_every_op_has_exactly_one_rung_entry() -> None:
    assert frozenset(VERB_RUNGS) == ALL_OPS
    for needs in VERB_RUNGS.values():
        assert needs.primary in RUNGS and needs.primary != "none"
        assert needs.create is None or needs.create in RUNGS
        assert needs.traverse is None or needs.traverse in RUNGS


def test_a_mutation_never_sits_below_add() -> None:
    for op in MUTATING_OPS | GRANT_WRITE_OPS:
        needs = VERB_RUNGS[op]
        assert LEVEL_RANK[needs.primary] >= LEVEL_RANK["add"], op
        assert needs.create is None or LEVEL_RANK[needs.create] >= LEVEL_RANK["add"], op


def test_a_read_never_mints() -> None:
    for op in READ_OPS | EXEC_OPS:
        assert VERB_RUNGS[op].create is None, op
    assert VERB_RUNGS["grants"].create is None


def test_creating_is_never_harder_than_modifying() -> None:
    for op, needs in VERB_RUNGS.items():
        if needs.create is not None:
            assert LEVEL_RANK[needs.create] <= LEVEL_RANK[needs.primary], op
        if needs.traverse is not None:
            assert LEVEL_RANK[needs.traverse] <= LEVEL_RANK[needs.primary], op


def test_the_listing_verbs_name_at_list_and_the_search_verbs_read() -> None:
    assert {op for op in READ_OPS if VERB_RUNGS[op].primary == "list"} == {"stat", "ls", "tree", "glob"}
    assert {op for op in READ_OPS if VERB_RUNGS[op].primary == "read"} == {"read", "grep", "glean", "graph"}
    assert VERB_RUNGS["graph"].traverse == "list"
    assert VERB_RUNGS["mkedge"].traverse == VERB_RUNGS["rmedge"].traverse == "list"
    assert VERB_RUNGS["copy"].traverse == "read"


# ---------------------------------------------------------------------------
# Consumers share the one vocabulary
# ---------------------------------------------------------------------------


def test_permission_gate_uses_the_shared_write_gated_set() -> None:
    assert permissions.WRITE_GATED_OPS is ops.WRITE_GATED_OPS


def test_projection_derives_action_functions_from_the_shared_set() -> None:
    assert projection.ACTION_FUNCTIONS is ops.MUTATING_OPS


def test_projection_derives_grant_functions_from_the_shared_set() -> None:
    assert projection.GRANT_FUNCTIONS is ops.GRANT_OPS
    assert all(projection.default_projection(op) == ("path",) for op in GRANT_OPS)


def test_glean_and_run_have_default_projections() -> None:
    assert projection.default_projection("glean") == ("path", "score", "matches")
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
# Developer plane — sweep and the mount-policy verbs never reach an agent surface
# ---------------------------------------------------------------------------


def test_sweep_and_mount_policy_are_developer_plane_ops() -> None:
    assert {"sweep", "posture", "add_member", "remove_member"} == DEVELOPER_OPS
    assert DEVELOPER_OPS <= WRITE_GATED_OPS
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
        "graph": lambda: fs.graph("outbound", "/a.py"),
        "write": lambda: fs.write(path="/f.txt", content="x"),
        "edit": lambda: fs.edit("/f.txt", old="a", new="b"),
        "delete": lambda: fs.delete("/f.txt"),
        "restore": lambda: fs.restore("/f.txt"),
        "mkdir": lambda: fs.mkdir("/d"),
        "mkedge": lambda: fs.mkedge(source="/a.py", target="/b.py", edge_type="imports"),
        "rmedge": lambda: fs.rmedge(source="/a.py", target="/b.py", edge_type="imports"),
        "move": lambda: fs.move(src="/a.txt", dest="/b.txt"),
        "copy": lambda: fs.copy(src="/a.txt", dest="/b.txt"),
        "run": lambda: fs.run("/tool"),
        "grant": lambda: fs.grant("/d", "bob", "read"),
        "revoke": lambda: fs.revoke("/d", "bob"),
        "grants": lambda: fs.grants("/d"),
    }
    assert frozenset(calls) == ALL_OPS - DEVELOPER_OPS
    for call in calls.values():
        result = await call()
        assert result.success is True
    await fs.add_mount(RecorderStorage(name="m"), "/m")
    await fs.remove_mount("/m")
    assert all(op not in DEVELOPER_OPS for op, _ in fs.calls)
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
