"""Dispatch across the mount boundary: the five shapes, the storage funnel,
the busy guard, the hop budget, backend_unavailable classification, input
hardening, and settled sibling semantics."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from base_doubles import (
    BuggyWriteStorage,
    CannedStorage,
    DeepRowStorage,
    EchoStorage,
    FailingWriteStorage,
    ReadFamilyStorage,
    RecorderFS,
    RecorderStorage,
    SlowWriteStorage,
    TransportFailStorage,
    _fan,
)
from vfs.base2 import VirtualFileSystem
from vfs.exceptions import WriteConflictError, raise_if_failed
from vfs.models2 import Entry, Observation
from vfs.ops import ALL_OPS, TwoPathOperation
from vfs.paths import MAX_PATH_LENGTH, Path
from vfs.permissions import read_write
from vfs.replace import EditOperation
from vfs.results2 import Result, ResultError, VFSErrorKind
from vfs.storage import ResolvedPair

# ----------------------------------------------------------------------
# single-shape verbs localize their dispatch
# ----------------------------------------------------------------------


async def test_write_localizes_path_and_passes_kwargs() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m")
    await root.write(path="/m/f.txt", content="x", overwrite=False)
    assert child.calls == [("write", {"path": "/f.txt", "content": "x", "overwrite": False, "parents": False})]


async def test_edit_wraps_old_new_into_edits_list() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m")
    await root.edit(path="/m/f.txt", old="a", new="b")
    assert child.calls == [("edit", {"path": "/f.txt", "edits": [EditOperation(old="a", new="b")]})]


async def test_edit_requires_old_new_or_edits() -> None:
    fs = RecorderFS()
    result = await fs.edit(path="/f.txt")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_tree_routes_with_depth_passthrough() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m")
    await root.tree("/m/src", max_depth=2)
    assert child.calls == [("tree", {"path": "/src", "max_depth": 2, "columns": None})]


# ----------------------------------------------------------------------
# two-path shape: move / copy
# ----------------------------------------------------------------------


async def test_move_same_terminal_dispatches_localized_pair() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m")
    result = await root.move(src="/m/a.txt", dest="/m/b.txt")
    assert result.success is True
    assert child.calls == [
        ("move", {"operations": [ResolvedPair(src=Path("/a.txt"), dest=Path("/b.txt"))], "overwrite": True}),
    ]


@pytest.mark.parametrize("op", ["move", "copy"])
async def test_two_path_cross_mount_rejected(op: str) -> None:
    root = VirtualFileSystem()
    a, b = RecorderStorage(), RecorderStorage()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    method = getattr(root, op)
    result = await method(src="/a/x.txt", dest="/b/y.txt")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.cross_mount
    assert a.calls == [] and b.calls == []


async def test_two_path_batch_one_bad_pair_rejects_all() -> None:
    root = VirtualFileSystem()
    a, b = RecorderStorage(), RecorderStorage()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    result = await root.move(moves=[TwoPathOperation(src="/a/x.txt", dest="/a/y.txt"), ("/a/z.txt", "/b/w.txt")])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.cross_mount
    assert a.calls == [] and b.calls == []  # nothing half-executes


async def test_move_gates_both_endpoints() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m", permissions=read_write(read=["/frozen"]))
    src_frozen = await root.move(src="/m/frozen/a.txt", dest="/m/b.txt")
    dest_frozen = await root.move(src="/m/a.txt", dest="/m/frozen/b.txt")
    assert src_frozen.errors[0].kind is VFSErrorKind.read_only
    assert src_frozen.errors[0].path == "/m/frozen/a.txt"
    assert dest_frozen.errors[0].kind is VFSErrorKind.read_only
    assert dest_frozen.errors[0].path == "/m/frozen/b.txt"
    assert child.calls == []


async def test_copy_gates_dest_only() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m", permissions=read_write(read=["/frozen"]))
    result = await root.copy(src="/m/frozen/a.txt", dest="/m/b.txt")
    assert result.success is True  # read-only source is fine for copy
    assert child.calls == [
        ("copy", {"operations": [ResolvedPair(src=Path("/frozen/a.txt"), dest=Path("/b.txt"))], "overwrite": True}),
    ]


async def test_two_path_unrouted_target_is_not_found_from_backend() -> None:
    # No mount catches "/nope" — it routes to the root's own storage, which
    # reports the missing source as not_found (there is no "no mount" state
    # anymore: every path resolves, at worst to the identity entry).
    root = VirtualFileSystem()
    result = await root.move(src="/nope/a.txt", dest="/nope/b.txt")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.not_found


async def test_two_path_capability_gate_blocks() -> None:
    root = VirtualFileSystem()
    child = EchoStorage(caps=frozenset({"read"}))
    await root.add_mount(child, "/m")
    result = await root.move(src="/m/a.txt", dest="/m/b.txt")
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert child.calls == []


# ----------------------------------------------------------------------
# the busy guard — bind sites are EBUSY to the data plane
# ----------------------------------------------------------------------


async def test_delete_bind_site_is_busy() -> None:
    root = VirtualFileSystem()
    a = RecorderStorage()
    await root.add_mount(a, "/a")
    result = await root.delete("/a")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.busy
    assert a.calls == []


async def test_delete_region_containing_bind_site_is_busy() -> None:
    root = VirtualFileSystem()
    a = RecorderStorage()
    await root.add_mount(a, "/data/a")
    result = await root.delete("/data")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.busy


async def test_cascade_delete_refused_busy_when_region_holds_a_bind() -> None:
    root = VirtualFileSystem()
    a = RecorderStorage()
    await root.add_mount(a, "/data/m")
    result = await root.delete("/data", cascade=True)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.busy
    assert a.calls == []


async def test_grouped_delete_bind_site_is_busy() -> None:
    root = VirtualFileSystem()
    a = RecorderStorage()
    await root.add_mount(a, "/a")
    result = await root.delete(observations=[Observation(path=Path("/a"))])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.busy
    assert a.calls == []


async def test_move_onto_bind_site_is_busy() -> None:
    root = VirtualFileSystem()
    a, b = RecorderStorage(), RecorderStorage()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    result = await root.move(src="/a/x.txt", dest="/b")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.busy
    assert a.calls == [] and b.calls == []


async def test_move_source_bind_site_is_busy() -> None:
    root = VirtualFileSystem()
    a = RecorderStorage()
    await root.add_mount(a, "/a")
    result = await root.move(src="/a", dest="/z")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.busy
    assert a.calls == []


async def test_move_region_containing_bind_site_is_busy() -> None:
    root = VirtualFileSystem()
    a = RecorderStorage()
    await root.add_mount(a, "/data/a")
    result = await root.move(src="/data", dest="/moved")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.busy
    assert a.calls == []


async def test_copy_from_bind_site_is_not_busy() -> None:
    # Copy never disturbs its source, so copying *from* a bind path is fine;
    # only the destination is guarded — move guards both endpoints.
    root = VirtualFileSystem()
    a = RecorderStorage()
    await root.add_mount(a, "/a")
    result = await root.copy(src="/a", dest="/a/backup")
    assert result.success is True
    assert a.calls == [
        ("copy", {"operations": [ResolvedPair(src=Path("/"), dest=Path("/backup"))], "overwrite": True}),
    ]


# ----------------------------------------------------------------------
# endpoint-pair shape: mkedge
# ----------------------------------------------------------------------


async def test_mkedge_localizes_endpoints_on_shared_terminal() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m")
    result = await root.mkedge("/m/a.py", "/m/b.py", "imports")
    assert result.success is True
    assert child.calls == [("mkedge", {"source": "/a.py", "target": "/b.py", "edge_type": "imports"})]


async def test_mkedge_cross_mount_rejected() -> None:
    root = VirtualFileSystem()
    a, b = RecorderStorage(), RecorderStorage()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    result = await root.mkedge("/a/x.py", "/b/y.py", "imports")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.cross_mount
    assert a.calls == [] and b.calls == []


async def test_mkedge_rejects_bad_edge_type() -> None:
    fs = RecorderFS()
    result = await fs.mkedge("/a.py", "/b.py", "im/ports")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_mkedge_missing_endpoints_is_not_found() -> None:
    root = VirtualFileSystem()
    result = await root.mkedge("/nope/a.py", "/nope/b.py", "imports")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.not_found


async def test_mkedge_capability_gate_blocks() -> None:
    root = VirtualFileSystem()
    child = EchoStorage(caps=frozenset({"read"}))
    await root.add_mount(child, "/m")
    result = await root.mkedge("/m/a.py", "/m/b.py", "imports")
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert child.calls == []


async def test_mkedge_invalid_endpoints_rejected() -> None:
    fs = RecorderFS()
    bad_source = await fs.mkedge("/a\x00.py", "/b.py", "imports")
    bad_target = await fs.mkedge("/a.py", "/b\x00.py", "imports")
    assert bad_source.errors[0].kind is VFSErrorKind.invalid
    assert bad_target.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_mkedge_rejects_non_string_edge_type() -> None:
    result = await RecorderFS().mkedge("/a.py", "/b.py", 123)  # ty: ignore[invalid-argument-type]
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


# ----------------------------------------------------------------------
# fan-out shape: glob / grep / glean
# ----------------------------------------------------------------------


@pytest.mark.parametrize("op", ["glob", "grep", "glean"])
async def test_fanout_reaches_every_mount_in_table_order(op: str) -> None:
    root = VirtualFileSystem()
    a, b = EchoStorage(), EchoStorage()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    result = await _fan(root, op)
    assert result.success is True
    assert result.paths == ("/a/hit.md", "/b/hit.md")  # rebased, mount-table order
    assert a.calls[0][0] == op and b.calls[0][0] == op
    assert a.calls[0][1]["paths"] == ()  # child impl sees an unscoped call


@pytest.mark.parametrize("op", ["glob", "grep", "glean"])
async def test_fanout_skips_incapable_terminal_silently(op: str) -> None:
    root = VirtualFileSystem()
    a = EchoStorage()
    b = EchoStorage(caps=frozenset({"read"}))
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    result = await _fan(root, op)
    assert result.success is True
    assert result.errors == []
    assert result.paths == ("/a/hit.md",)
    assert b.calls == []


@pytest.mark.parametrize("op", ["glob", "grep", "glean"])
async def test_fanout_scoped_routes_only_the_target_terminal(op: str) -> None:
    root = VirtualFileSystem()
    a, b = EchoStorage(), EchoStorage()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    result = await _fan(root, op, paths=("/a/src",))
    assert result.success is True
    assert a.calls[0][1]["paths"] == ("/src",)
    assert b.calls == []


async def test_fanout_scoped_incapable_terminal_is_unsupported() -> None:
    root = VirtualFileSystem()
    b = EchoStorage(caps=frozenset({"read"}))
    await root.add_mount(b, "/b")
    result = await root.glob("*.py", paths=("/b/src",))
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert b.calls == []


async def test_fanout_includes_self_storage_before_mounts() -> None:
    # The identity entry at "/" is an ordinary binding: it participates in
    # an unscoped fan-out alongside every mounted entry, self first.
    root = VirtualFileSystem()
    await root.write(path="/notes.md", content="alpha")
    child = EchoStorage()
    await root.add_mount(child, "/m")
    result = await root.glob("*.md")
    assert result.paths == ("/notes.md", "/m/hit.md")


async def test_fanout_with_no_capable_terminals_is_empty_success() -> None:
    # The default backend never declares glean, and there are no mounts.
    result = await VirtualFileSystem().glean("anything")
    assert result.success is True
    assert len(result) == 0
    assert result.function == "glean"


async def test_fanout_rebase_overflow_classifies_instead_of_raising() -> None:
    # A child row valid in local coordinates but over 1024 once rebased is
    # refused as an `invalid` error; the sibling row in the same result survives.
    root = VirtualFileSystem()
    mount = "/" + "m" * 30
    await root.add_mount(DeepRowStorage(), mount)
    result = await root.glob("**/*", paths=(mount,))
    assert result.success is False
    assert result.paths == (f"{mount}/ok.py",)
    [err] = result.errors
    assert err.kind is VFSErrorKind.invalid
    assert err.data == {"mount": mount, "local_path": DeepRowStorage.DEEP}
    # re-addressability: every surviving path is valid input to the next request
    assert all(len(p) <= MAX_PATH_LENGTH and Path(p) is p for p in result.paths)


async def test_grep_observations_use_grouped_dispatch() -> None:
    root = VirtualFileSystem()
    a, b = RecorderStorage(), RecorderStorage()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    rows = [Observation(path=Path("/a/f.py")), Observation(path=Path("/b/g.py"))]
    await root.grep("needle", observations=rows)
    assert len(a.calls) == 1 and len(b.calls) == 1
    (a_obs,) = a.calls[0][1]["observations"]
    assert a_obs.path == "/f.py"  # rebased into the terminal's coordinates


# ----------------------------------------------------------------------
# grouped reads classify per-row; mutations reject the whole batch
# ----------------------------------------------------------------------


async def test_grouped_read_partial_rows_and_error_both_surface() -> None:
    # Reads classify per-row: a backend may answer some observations AND an
    # error for the same call, and the router merges both through as-is.
    partial = Result(
        function="stat",
        success=False,
        observations=[Observation(path=Path("/ok.txt"), kind="file")],
        errors=[ResultError(kind=VFSErrorKind.not_found, message="gone", path=Path("/missing.txt"))],
    )
    root = VirtualFileSystem()
    child = CannedStorage({"stat": partial})
    await root.add_mount(child, "/m")
    rows = [Observation(path=Path("/m/ok.txt")), Observation(path=Path("/m/missing.txt"))]
    result = await root.stat(observations=rows)
    assert result.success is False
    assert result.paths == ("/m/ok.txt",)
    assert result.errors[0].kind is VFSErrorKind.not_found


async def test_observation_batch_mutation_gates_capability_before_dispatch() -> None:
    # A delete batch spanning a capable and a capability-limited terminal
    # must dispatch to NEITHER — the capability check runs before any group
    # executes, like every other chokepoint.
    root = VirtualFileSystem()
    capable = RecorderStorage()
    limited = EchoStorage(caps=frozenset({"read"}))
    await root.add_mount(capable, "/cap")
    await root.add_mount(limited, "/lim")
    rows = [Observation(path=Path("/cap/a.txt")), Observation(path=Path("/lim/b.txt"))]
    result = await root.delete(observations=rows)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert capable.calls == []  # not dispatched despite being capable


# ----------------------------------------------------------------------
# grouped shape: graph
# ----------------------------------------------------------------------


async def test_graph_rejects_unknown_and_centrality_methods() -> None:
    fs = RecorderFS()
    for method in ("pagerank", "not_a_method"):
        result = await fs.graph(method, path="/a.py")
        assert result.success is False
        assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_graph_path_routes_to_one_terminal() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m")
    await root.graph("descendants", path="/m/a.py")
    assert child.calls == [("graph", {"path": "/a.py", "method": "descendants", "depth": None})]


async def test_graph_observations_group_per_mount() -> None:
    root = VirtualFileSystem()
    a, b = RecorderStorage(), RecorderStorage()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    rows = [Observation(path=Path("/a/x.py")), Observation(path=Path("/b/y.py"))]
    await root.graph("neighborhood", observations=rows, depth=2)
    assert len(a.calls) == 1 and len(b.calls) == 1
    (a_obs,) = a.calls[0][1]["observations"]
    assert a_obs.path == "/x.py"  # each mount walks only its own subgraph
    assert a.calls[0][1]["method"] == "neighborhood"
    assert a.calls[0][1]["depth"] == 2


# ----------------------------------------------------------------------
# batch-entry writes
# ----------------------------------------------------------------------


async def test_write_entries_batch_groups_and_localizes() -> None:
    root = VirtualFileSystem()
    a, b = RecorderStorage(), RecorderStorage()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    entries = [Entry(path=Path("/a/f.txt"), content="x"), Entry(path=Path("/b/g.txt"), content="y")]
    result = await root.write(entries)
    assert result.success is True
    assert len(a.calls) == 1 and len(b.calls) == 1
    (a_entry,) = a.calls[0][1]["entries"]
    assert a_entry.path == "/f.txt"
    assert a.calls[0][1]["overwrite"] is True


async def test_write_entries_one_read_only_target_rejects_all() -> None:
    root = VirtualFileSystem()
    a = RecorderStorage()
    b = RecorderStorage()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b", permissions="read")
    entries = [Entry(path=Path("/a/f.txt"), content="x"), Entry(path=Path("/b/g.txt"), content="y")]
    result = await root.write(entries)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.read_only
    assert a.calls == [] and b.calls == []  # gated before any dispatch


async def test_write_entries_missing_parent_is_not_found() -> None:
    root = VirtualFileSystem()
    result = await root.write(entries=[Entry(path=Path("/missing/f.txt"), content="x")])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.not_found


async def test_write_entries_capability_gate_blocks() -> None:
    root = VirtualFileSystem()
    child = EchoStorage(caps=frozenset({"read"}))
    await root.add_mount(child, "/m")
    result = await root.write(entries=[Entry(path=Path("/m/f.txt"), content="x")])
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert child.calls == []


async def test_write_entries_inverse_edge_target_rejected() -> None:
    fs = RecorderFS()
    entry = Entry(path=Path("/.vfs/a.py/__meta__/edges/in/imports/b.py"))
    result = await fs.write(entries=[entry])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


# ----------------------------------------------------------------------
# hop budget — fan-out and tree answer finitely, never hang
# ----------------------------------------------------------------------


@pytest.mark.parametrize("op", ["glob", "grep", "glean"])
async def test_fanout_with_zero_hop_budget_is_budget_exhausted(op: str) -> None:
    root = VirtualFileSystem(hop_budget=0)
    await root.add_mount(EchoStorage(), "/m")
    result = await _fan(root, op)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.budget_exhausted


async def test_tree_with_zero_hop_budget_is_budget_exhausted() -> None:
    root = VirtualFileSystem(hop_budget=0)
    result = await root.tree("/")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.budget_exhausted


async def test_hop_budget_charged_once_per_call_not_per_binding() -> None:
    # A single fan-out request costs one hop regardless of how many entries
    # it fans out to.
    root = VirtualFileSystem(hop_budget=1)
    await root.add_mount(EchoStorage(), "/a")
    await root.add_mount(EchoStorage(), "/b")
    result = await root.glob("*.md")
    assert result.success is True
    assert set(result.paths) == {"/a/hit.md", "/b/hit.md"}


async def test_hop_budget_resets_between_calls() -> None:
    # The budget is per-request (a context var reset on the way out);
    # consuming it on one call must not starve the next.
    root = VirtualFileSystem(hop_budget=1)
    await root.add_mount(EchoStorage(), "/m")
    first = await root.glob("*.md")
    second = await root.glob("*.md")
    assert first.success is True
    assert second.success is True


# ----------------------------------------------------------------------
# backend_unavailable — a dead wire peer classifies, never raises
# ----------------------------------------------------------------------


async def test_transport_error_classifies_backend_unavailable() -> None:
    root = VirtualFileSystem()
    await root.add_mount(TransportFailStorage(), "/dead")
    result = await root.read("/dead/f.txt")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.backend_unavailable
    assert result.function == "read"


async def test_transport_error_message_names_the_failure() -> None:
    root = VirtualFileSystem()
    await root.add_mount(TransportFailStorage(), "/dead")
    result = await root.stat("/dead/f.txt")
    assert "peer is gone" in result.errors[0].message


async def test_transport_error_at_root_storage_reports_root_path() -> None:
    fs = VirtualFileSystem(storage=TransportFailStorage())
    result = await fs.read("/f.txt")
    assert result.errors[0].kind is VFSErrorKind.backend_unavailable
    assert result.errors[0].path == "/"


async def test_backend_unavailable_keeps_the_binding_bound() -> None:
    # Keep-and-error: a dead backend never auto-unbinds; a second call still
    # reaches it and classifies the same way.
    root = VirtualFileSystem()
    dead = TransportFailStorage()
    await root.add_mount(dead, "/dead")
    first = await root.read("/dead/f.txt")
    second = await root.read("/dead/f.txt")
    assert first.errors[0].kind is VFSErrorKind.backend_unavailable
    assert second.errors[0].kind is VFSErrorKind.backend_unavailable
    assert len(dead.calls) == 2  # both calls actually reached the backend


# ----------------------------------------------------------------------
# router edge and error branches
# ----------------------------------------------------------------------


async def test_dispatch_reaches_the_backend_method() -> None:
    class PathEchoStorage(RecorderStorage):
        async def read(self, *, path: Path | None = None, user_id: str | None = None, **kwargs: Any) -> Result:
            return Result(function="read", observations=[Observation(path=Path(str(path)))])

    result = await VirtualFileSystem(storage=PathEchoStorage()).read("/f.txt")
    assert result.paths == ("/f.txt",)


async def test_funnel_backstop_answers_unsupported_when_capability_overclaims() -> None:
    # A capability snapshot may overclaim what the backend implements (a
    # policy bug); the funnel's own family check backstops it — unsupported,
    # never a raw AttributeError.
    class OverclaimingStorage(ReadFamilyStorage):
        def capabilities(self) -> frozenset[str]:
            return ALL_OPS

    fs = VirtualFileSystem(storage=OverclaimingStorage())
    gated = await fs.write(path="/f.txt", content="x")  # passes the gate (caps lie)
    assert gated.success is False
    assert gated.errors[0].kind is VFSErrorKind.unsupported
    assert gated.function == "write"


@pytest.mark.parametrize("op", sorted(ALL_OPS - {"read", "stat", "ls", "tree"}))
async def test_every_guarded_funnel_arm_backstops_a_missing_family(op: str) -> None:
    # Each non-read arm's family guard answers unsupported for a backend that
    # only implements the read family — the backstop behind the gate,
    # exercised arm by arm by calling the funnel directly.
    class OverclaimingStorage(ReadFamilyStorage):
        def capabilities(self) -> frozenset[str]:
            return ALL_OPS

    fs = VirtualFileSystem(storage=OverclaimingStorage())
    binding = fs._bindings[Path("/")]
    result = await fs._call_storage(binding, op)  # ty: ignore[invalid-argument-type]
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert result.function == op


async def test_run_dispatches_through_the_funnel_to_the_backend() -> None:
    fs = RecorderFS()
    result = await fs.run("/tool", arguments={"x": 1})
    assert result.success is True
    assert fs.calls == [("run", {"path": "/tool", "arguments": {"x": 1}})]


async def test_funnel_fails_loud_on_an_unknown_op() -> None:
    # A string outside the Op vocabulary is a router bug: assert_never
    # raises rather than guessing a dispatch.
    fs = VirtualFileSystem()
    binding = fs._bindings[Path("/")]
    with pytest.raises(AssertionError):
        await fs._call_storage(binding, "bogus")  # ty: ignore[invalid-argument-type]


async def test_route_single_requires_exactly_one_input() -> None:
    fs = RecorderFS()
    neither = await fs.read()
    both = await fs.read("/f.txt", observations=[Observation(path=Path("/f.txt"))])
    assert neither.success is False and neither.errors[0].kind is VFSErrorKind.invalid
    assert both.success is False and both.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_stat_and_ls_route_and_localize() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m")
    await root.stat("/m/f.txt")
    await root.ls("/m/dir")
    assert child.calls == [
        ("stat", {"path": "/f.txt", "columns": None}),
        ("ls", {"path": "/dir", "columns": None}),
    ]


async def test_grouped_observations_empty_list_is_empty_success() -> None:
    result = await RecorderFS().read(observations=[])
    assert result.success is True
    assert len(result) == 0


async def test_grouped_observations_mutation_gate_rejects_invalid_target() -> None:
    fs = RecorderFS()
    result = await fs.delete(observations=[Observation(path=Path("/"))])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_grouped_observations_respect_read_only_mount() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m", permissions="read")
    result = await root.delete(observations=[Observation(path=Path("/m/f.txt"))])
    assert result.errors[0].kind is VFSErrorKind.read_only
    assert child.calls == []


async def test_grouped_observations_capability_error_is_rebased() -> None:
    root = VirtualFileSystem()
    child = EchoStorage(caps=frozenset({"glob"}))
    await root.add_mount(child, "/m")
    result = await root.read(observations=[Observation(path=Path("/m/f.txt"))])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert child.calls == []


async def test_merge_results_of_nothing_is_empty() -> None:
    merged = VirtualFileSystem._merge_results([])
    assert merged.success is True
    assert len(merged) == 0


async def test_two_path_empty_batch_is_empty_success() -> None:
    result = await RecorderFS().move(moves=[])
    assert result.success is True
    assert len(result) == 0


async def test_two_path_invalid_src_rejected() -> None:
    result = await RecorderFS().move(src="/a\x00b.txt", dest="/b.txt")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


@pytest.mark.parametrize("op", ["move", "copy"])
async def test_two_path_requires_pair_or_batch(op: str) -> None:
    result = await getattr(RecorderFS(), op)()
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_write_entries_empty_batch_is_empty_success() -> None:
    result = await RecorderFS().write(entries=[])
    assert result.success is True
    assert len(result) == 0


async def test_observation_dispatch_unroutable_path_is_not_found() -> None:
    fs = VirtualFileSystem()
    single = await fs.read("/nope")
    batch = await fs.read(observations=[Observation(path=Path("/nope"))])
    assert single.errors[0].kind is VFSErrorKind.not_found
    assert batch.errors[0].kind is VFSErrorKind.not_found


async def test_gated_denial_is_a_result_until_the_boundary() -> None:
    # A read-only mount denies as a classified Result; only the
    # caller-applied boundary adapter turns it into an exception.
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/c", permissions="read")
    denied = await root.write(path="/c/f.txt", content="x")
    assert denied.success is False
    assert denied.errors[0].kind is VFSErrorKind.read_only
    assert denied.function == "write"
    with pytest.raises(WriteConflictError):
        raise_if_failed(denied)


# ----------------------------------------------------------------------
# audit hardening — gate ordering, error fan-in, input validation
# ----------------------------------------------------------------------


async def test_grouped_observations_reject_non_observation_element() -> None:
    result = await RecorderFS().delete(observations=["notanobs"])  # ty: ignore[invalid-argument-type]
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_merge_preserves_distinct_but_equal_errors_from_different_mounts() -> None:
    # Two mounts failing identically are two real failures.
    left = Result(function="grep", errors=[ResultError(kind=VFSErrorKind.unavailable, message="down")])
    right = Result(function="grep", errors=[ResultError(kind=VFSErrorKind.unavailable, message="down")])
    merged = left | right
    assert len(merged.errors) == 2


async def test_merge_still_dedups_the_same_error_object_in_a_diamond() -> None:
    err = ResultError(kind=VFSErrorKind.unavailable, message="down")
    a = Result(function="grep", observations=[Observation(path=Path("/a"))], errors=[err])
    b = Result(function="grep", errors=[err])
    diamond = (a | b) & b  # same err instance flows down both arms
    assert len(diamond.errors) == 1


@pytest.mark.parametrize("bad", [("/a",), ("/a", "/b", "/c"), ("/a", 123), "ab"])
async def test_two_path_batch_rejects_malformed_pairs(bad: object) -> None:
    result = await RecorderFS().move(moves=[bad])  # ty: ignore[invalid-argument-type]
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_write_entries_rejects_non_entry_element() -> None:
    result = await RecorderFS().write(entries=["notanentry"])  # ty: ignore[invalid-argument-type]
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_write_rejects_entries_and_path_together() -> None:
    result = await RecorderFS().write(entries=[Entry(path=Path("/a.txt"))], path="/b.txt", content="x")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_edit_rejects_old_new_and_edits_together() -> None:
    result = await RecorderFS().edit(path="/f.txt", old="a", new="b", edits=[EditOperation(old="c", new="d")])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


@pytest.mark.parametrize("op", ["move", "copy"])
async def test_two_path_rejects_pair_and_batch_together(op: str) -> None:
    method = getattr(RecorderFS(), op)
    result = await method(src="/a.txt", dest="/b.txt", **{"moves" if op == "move" else "copies": [("/c", "/d")]})
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


@pytest.mark.parametrize("op", ["glob", "grep", "glean"])
async def test_fanout_rejects_paths_and_observations_together(op: str) -> None:
    root = VirtualFileSystem()
    await root.add_mount(EchoStorage(), "/m")
    result = await _fan(root, op, paths=("/m/x",), observations=[Observation(path=Path("/m/y"))])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


# ----------------------------------------------------------------------
# audit round 2 — batch containers, generators, edit hardening
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("verb", "kwargs"),
    [
        ("delete", {"observations": 5}),
        ("read", {"observations": 5}),
        ("write", {"entries": 5}),
        ("move", {"moves": 5}),
        ("copy", {"copies": 5}),
        ("edit", {"path": "/f.txt", "edits": 5}),
    ],
)
async def test_non_iterable_batch_arg_is_invalid_not_crash(verb: str, kwargs: dict[str, Any]) -> None:
    result = await getattr(RecorderFS(), verb)(**kwargs)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_generator_observations_are_not_silently_dropped() -> None:
    # A single-use generator must survive the validate + group passes.
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m")
    gen = (Observation(path=Path(p)) for p in ("/m/a.txt", "/m/b.txt"))
    result = await root.delete(observations=gen)  # ty: ignore[invalid-argument-type]
    assert result.success is True
    assert len(child.calls) == 1
    assert len(child.calls[0][1]["observations"]) == 2  # both rows dispatched


async def test_generator_entries_survive() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m")
    gen = (Entry(path=Path(p), content="x") for p in ("/m/a.txt", "/m/b.txt"))
    result = await root.write(gen)  # ty: ignore[invalid-argument-type]
    assert result.success is True
    assert len(child.calls[0][1]["entries"]) == 2


@pytest.mark.parametrize("bad", ["foo", [None], ["notanedit"], [EditOperation(old="a", new="b"), None]])
async def test_edit_rejects_malformed_edits(bad: object) -> None:
    result = await RecorderFS().edit(path="/f.txt", edits=bad)  # ty: ignore[invalid-argument-type]
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


# ----------------------------------------------------------------------
# settled dispatch — every sibling finishes before the router reports
# ----------------------------------------------------------------------


async def test_sibling_writes_settle_before_failure_is_reported() -> None:
    # One terminal fails fast, the other writes slowly: the returned Result
    # must already contain the slow sibling's outcome — never a write that
    # lands behind a caller who has already seen the failure.
    root = VirtualFileSystem()
    ok, bad = SlowWriteStorage(), FailingWriteStorage()
    await root.add_mount(ok, "/ok")
    await root.add_mount(bad, "/bad")
    result = await root.write(
        entries=[Entry(path=Path("/ok/a.txt"), content="A"), Entry(path=Path("/bad/b.txt"), content="B")],
    )
    assert result.success is False
    assert ok.write_log == ["/a.txt"]  # completed before the router returned
    assert "/ok/a.txt" in result.paths  # and its outcome is reported, not dropped
    assert any(e.kind is VFSErrorKind.unavailable for e in result.errors)


async def test_impl_bug_propagates_only_after_siblings_settle() -> None:
    # A raw exception is an impl bug: it propagates with its traceback, but
    # only after every sibling group has finished mutating.
    root = VirtualFileSystem()
    ok, buggy = SlowWriteStorage(), BuggyWriteStorage()
    await root.add_mount(ok, "/ok")
    await root.add_mount(buggy, "/bug")
    with pytest.raises(RuntimeError, match="impl bug"):
        await root.write(
            entries=[Entry(path=Path("/ok/a.txt"), content="A"), Entry(path=Path("/bug/b.txt"), content="B")],
        )
    assert ok.write_log == ["/a.txt"]  # the world had settled before the raise


async def test_cancellation_reraises_untouched() -> None:
    # Cancellation is not an impl bug: it re-raises as-is, never collected
    # into an ExceptionGroup, so task teardown semantics stay intact.
    class CancelledWriteStorage(RecorderStorage):
        async def write(self, **_: Any) -> Result:
            raise asyncio.CancelledError

    root = VirtualFileSystem()
    await root.add_mount(CancelledWriteStorage(), "/c")
    with pytest.raises(asyncio.CancelledError):
        await root.write(entries=[Entry(path=Path("/c/a.txt"), content="A")])


async def test_multiple_impl_bugs_raise_an_exception_group() -> None:
    root = VirtualFileSystem()
    await root.add_mount(BuggyWriteStorage(), "/bug1")
    await root.add_mount(BuggyWriteStorage(), "/bug2")
    with pytest.raises(ExceptionGroup) as exc:
        await root.write(
            entries=[Entry(path=Path("/bug1/a.txt"), content="A"), Entry(path=Path("/bug2/b.txt"), content="B")],
        )
    assert len(exc.value.exceptions) == 2


# ----------------------------------------------------------------------
# the closed filesystem — every verb classifies backend_unavailable
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("verb", "call"),
    [
        ("read", lambda fs: fs.read("/nope")),
        ("stat", lambda fs: fs.stat("/nope")),
        ("ls", lambda fs: fs.ls("/nope")),
        ("tree", lambda fs: fs.tree("/nope")),
        ("write", lambda fs: fs.write(path="/nope", content="x")),
        ("edit", lambda fs: fs.edit(path="/nope", old="a", new="b")),
        ("delete", lambda fs: fs.delete("/nope")),
        ("mkdir", lambda fs: fs.mkdir("/nope/d")),
        ("mkedge", lambda fs: fs.mkedge("/a.txt", "/b.txt", "ref")),
        ("move", lambda fs: fs.move("/a", "/b")),
        ("copy", lambda fs: fs.copy("/a", "/b")),
        ("graph", lambda fs: fs.graph("descendants", "/nope")),
        ("run", lambda fs: fs.run("/nope")),
        ("glob", lambda fs: fs.glob("*", paths=("/nope",))),
        ("grep", lambda fs: fs.grep("x", paths=("/nope",))),
        ("glean", lambda fs: fs.glean("q", paths=("/nope",))),
    ],
)
async def test_closed_filesystem_fails_every_verb_as_backend_unavailable(verb: str, call: Any) -> None:
    # After close(), the table is empty: every verb classifies
    # backend_unavailable and still reports which verb failed.
    fs = VirtualFileSystem()
    await fs.close()
    result = await call(fs)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.backend_unavailable
    assert result.function == verb
