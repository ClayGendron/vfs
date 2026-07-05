"""The terminal gate and error taxonomy: routability, capability (derived and
overridden), permission, and kind-based exception dispatch."""

from __future__ import annotations

from typing import Any

import pytest

from base_doubles import (
    EchoFS,
    LimitedEchoFS,
    ReadFamilyStorage,
    RecorderFS,
    RecorderStorage,
    RunnerFS,
    _mutate,
    _mutate_at_root,
)
from vfs.base2 import VirtualFileSystem
from vfs.exceptions import (
    NotFoundError,
    ValidationError,
    VFSError,
    WriteConflictError,
    exception_for_kind,
    raise_if_failed,
)
from vfs.models2 import Entry, Observation
from vfs.ops import ALL_OPS, MUTATING_OPS
from vfs.paths import Path
from vfs.results2 import Result, ResultError, VFSErrorKind

# ----------------------------------------------------------------------
# _error and kind-based exception dispatch
# ----------------------------------------------------------------------


def test_exception_for_kind_maps_known_kinds() -> None:
    assert exception_for_kind(VFSErrorKind.not_found) is NotFoundError
    assert exception_for_kind(VFSErrorKind.read_only) is WriteConflictError
    assert exception_for_kind(VFSErrorKind.invalid) is ValidationError


def test_exception_for_kind_unmapped_and_unknown_fall_back_to_base() -> None:
    # internal is a real kind with no explicit mapping; the str is a newer peer's kind.
    assert exception_for_kind(VFSErrorKind.internal) is VFSError
    assert exception_for_kind("vfs.quota_exceeded") is VFSError


def test_error_returns_failed_result_by_default() -> None:
    fs = VirtualFileSystem()
    r = fs._error("gone", kind=VFSErrorKind.not_found, path=Path("/x"))
    assert r.success is False
    assert r.errors[0].kind is VFSErrorKind.not_found
    assert r.errors[0].path == "/x"


def test_error_attaches_structured_data() -> None:
    fs = VirtualFileSystem()
    r = fs._error("stale", kind=VFSErrorKind.conflict, data={"expected": 1})
    assert r.errors[0].data == {"expected": 1}


def test_error_never_raises_and_carries_function() -> None:
    # The node layer has one failure channel: a returned Result. The op
    # travels as function so a wire consumer can tell which verb failed.
    fs = VirtualFileSystem()
    r = fs._error("gone", kind=VFSErrorKind.not_found, function="read")
    assert r.success is False
    assert r.function == "read"


def test_raise_if_failed_passes_success_through() -> None:
    ok = Result(function="read", observations=[])
    assert raise_if_failed(ok) is ok


def test_raise_if_failed_maps_single_error_to_kind_exception() -> None:
    failed = VirtualFileSystem()._error("gone", kind=VFSErrorKind.not_found, function="read")
    with pytest.raises(NotFoundError) as exc:
        raise_if_failed(failed)
    # the raised exception still carries the full failed result
    assert exc.value.result is failed
    assert exc.value.result.success is False


def test_raise_if_failed_groups_multiple_errors() -> None:
    # A fan-out failure reports every downed terminal, not just the first.
    failed = Result(
        success=False,
        errors=[
            ResultError(kind=VFSErrorKind.not_found, message="gone"),
            ResultError(kind=VFSErrorKind.read_only, message="frozen"),
        ],
    )
    with pytest.raises(ExceptionGroup) as exc:
        raise_if_failed(failed)
    matched = {type(e) for e in exc.value.exceptions}
    assert matched == {NotFoundError, WriteConflictError}


def test_raise_if_failed_handles_errorless_failure() -> None:
    with pytest.raises(VFSError):
        raise_if_failed(Result(success=False))


# ----------------------------------------------------------------------
# capabilities gate + run verb
# ----------------------------------------------------------------------


async def test_run_on_pure_router_is_not_found() -> None:
    root = VirtualFileSystem()
    r = await root.run("/nope/tool")
    assert r.success is False
    assert r.errors[0].kind is VFSErrorKind.not_found


async def test_run_routes_to_child_and_rebases() -> None:
    root = VirtualFileSystem()
    catalog = RunnerFS()
    await root.add_mount(catalog, "/nonvfs")
    r = await root.run("/nonvfs/clone-repo", arguments={"repo": "org/proj"})
    assert catalog.calls == [("run", "/clone-repo", {"repo": "org/proj"})]
    assert r.success is True
    assert r.paths == ("/nonvfs/clone-repo",)


async def test_capabilities_gate_blocks_unsupported_op() -> None:
    root = VirtualFileSystem()
    catalog = RunnerFS(caps=frozenset({"read"}))
    await root.add_mount(catalog, "/nonvfs")
    blocked = await root.run("/nonvfs/clone-repo")
    assert blocked.success is False
    assert blocked.errors[0].kind is VFSErrorKind.unsupported
    assert catalog.calls == []  # never dispatched


async def test_capabilities_gate_allows_supported_op() -> None:
    root = VirtualFileSystem()
    catalog = RunnerFS(caps=frozenset({"read"}))
    await root.add_mount(catalog, "/nonvfs")
    ok = await root.read("/nonvfs/clone-repo")
    assert ok.success is True
    assert ok.paths == ("/nonvfs/clone-repo",)
    assert catalog.calls == [("read", "/clone-repo", None)]


async def test_capabilities_none_imposes_no_gate() -> None:
    # A plain child (capabilities() is None) answers run with no restriction.
    root = VirtualFileSystem()
    catalog = RunnerFS()
    await root.add_mount(catalog, "/nonvfs")
    r = await root.run("/nonvfs/x")
    assert r.success is True


# ----------------------------------------------------------------------
# mutation gates across the full verb surface
# ----------------------------------------------------------------------


@pytest.mark.parametrize("op", sorted(MUTATING_OPS))
async def test_read_only_mount_rejects_every_mutation(op: str) -> None:
    root = VirtualFileSystem()
    child = RecorderFS(permissions="read")
    await root.add_mount(child, "/m")
    result = await _mutate(root, op, "/m")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.read_only
    assert child.calls == []  # gated before any dispatch


@pytest.mark.parametrize("op", sorted(MUTATING_OPS))
async def test_writable_mount_dispatches_every_mutation_once(op: str) -> None:
    root = VirtualFileSystem()
    child = RecorderFS()
    await root.add_mount(child, "/m")
    result = await _mutate(root, op, "/m")
    assert result.success is True
    assert len(child.calls) == 1
    assert child.calls[0][0] == op


@pytest.mark.parametrize("op", sorted(MUTATING_OPS))
@pytest.mark.parametrize("target", ["/", "/.vfs"])
async def test_root_and_reserved_targets_rejected(op: str, target: str) -> None:
    fs = RecorderFS()
    result = await _mutate_at_root(fs, op, target)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_inverse_edge_projection_is_not_a_write_target() -> None:
    fs = RecorderFS()
    result = await fs.write(path="/.vfs/a.py/__meta__/edges/in/imports/b.py", content="x")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


# ----------------------------------------------------------------------
# one terminal gate — structured error paths and pinned order
# ----------------------------------------------------------------------


async def _gated_namespace() -> VirtualFileSystem:
    """Router with a read-only mount and a capability-limited mount."""
    root = VirtualFileSystem()
    await root.add_mount(RecorderFS(permissions="read"), "/ro")
    await root.add_mount(LimitedEchoFS(caps=frozenset({"read"})), "/dim")
    return root


GATE_FAILURES = [
    (
        "single/no-mount",
        lambda r: r.write(path="/nowhere/x.txt", content="c"),
        VFSErrorKind.not_found,
        "/nowhere/x.txt",
    ),
    (
        "grouped/no-mount",
        lambda r: r.delete(observations=[Observation(path=Path("/nowhere/f.txt"))]),
        VFSErrorKind.not_found,
        "/nowhere/f.txt",
    ),
    (
        "pair/no-mount",
        lambda r: r.move(src="/nowhere/a.txt", dest="/nowhere/b.txt"),
        VFSErrorKind.not_found,
        "/nowhere/a.txt",
    ),
    (
        "entries/no-mount",
        lambda r: r.write(entries=[Entry(path=Path("/nowhere/f.txt"), content="c")]),
        VFSErrorKind.not_found,
        "/nowhere/f.txt",
    ),
    ("scoped/no-mount", lambda r: r.grep("x", paths=("/nowhere/sub",)), VFSErrorKind.not_found, "/nowhere/sub"),
    (
        "mkedge/no-mount",
        lambda r: r.mkedge("/nowhere/a.py", "/nowhere/b.py", "imports"),
        VFSErrorKind.not_found,
        "/nowhere/a.py",
    ),
    ("single/read-only", lambda r: r.write(path="/ro/x.txt", content="c"), VFSErrorKind.read_only, "/ro/x.txt"),
    (
        "grouped/read-only",
        lambda r: r.delete(observations=[Observation(path=Path("/ro/f.txt"))]),
        VFSErrorKind.read_only,
        "/ro/f.txt",
    ),
    ("pair-src/read-only", lambda r: r.move(src="/ro/a.txt", dest="/ro/b.txt"), VFSErrorKind.read_only, "/ro/a.txt"),
    ("pair-dest/read-only", lambda r: r.copy(src="/ro/a.txt", dest="/ro/b.txt"), VFSErrorKind.read_only, "/ro/b.txt"),
    (
        "entries/read-only",
        lambda r: r.write(entries=[Entry(path=Path("/ro/y.txt"), content="c")]),
        VFSErrorKind.read_only,
        "/ro/y.txt",
    ),
    ("single/incapable", lambda r: r.write(path="/dim/x.txt", content="c"), VFSErrorKind.unsupported, "/dim/x.txt"),
    (
        "grouped/incapable",
        lambda r: r.stat(observations=[Observation(path=Path("/dim/f.txt"))]),
        VFSErrorKind.unsupported,
        "/dim/f.txt",
    ),
    ("pair/incapable", lambda r: r.move(src="/dim/a.txt", dest="/dim/b.txt"), VFSErrorKind.unsupported, "/dim/a.txt"),
    (
        "entries/incapable",
        lambda r: r.write(entries=[Entry(path=Path("/dim/f.txt"), content="c")]),
        VFSErrorKind.unsupported,
        "/dim/f.txt",
    ),
    ("scoped/incapable", lambda r: r.grep("x", paths=("/dim/sub",)), VFSErrorKind.unsupported, "/dim/sub"),
    (
        "mkedge/incapable",
        lambda r: r.mkedge("/dim/a.py", "/dim/b.py", "imports"),
        VFSErrorKind.unsupported,
        "/dim/a.py",
    ),
]


@pytest.mark.parametrize(("call", "kind", "path"), [c[1:] for c in GATE_FAILURES], ids=[c[0] for c in GATE_FAILURES])
async def test_gate_failures_carry_the_router_side_path(call: Any, kind: VFSErrorKind, path: str) -> None:
    # Every chokepoint x every gate failure reachable there: the error's
    # structured path is the path the caller addressed — never None.
    root = await _gated_namespace()
    result = await call(root)
    assert result.success is False
    assert result.errors[0].kind is kind
    assert result.errors[0].path == path


async def test_mkedge_permission_denial_reports_the_derived_edge_path() -> None:
    # mkedge's write target is the derived canonical out-edge path — the one
    # gate error implicating a path the caller never typed — and even that
    # path is reported router-side, rebased under the mount prefix.
    root = await _gated_namespace()
    result = await root.mkedge("/ro/a.py", "/ro/b.py", "imports")
    assert result.errors[0].kind is VFSErrorKind.read_only
    assert result.errors[0].path == "/ro/.vfs/a.py/__meta__/edges/out/imports/b.py"


async def test_gate_order_capability_outranks_permission() -> None:
    # A terminal that is simultaneously incapable and read-only fails
    # unsupported: what the terminal cannot do outranks what policy denies.
    root = VirtualFileSystem()
    await root.add_mount(LimitedEchoFS(caps=frozenset({"read"}), permissions="read"), "/m")
    result = await root.write(path="/m/f.txt", content="c")
    assert result.errors[0].kind is VFSErrorKind.unsupported


async def test_gate_order_routability_outranks_capability() -> None:
    # A pure router with no mount at the path is not_found even when the op
    # is also outside its own capability set.
    class IncapableRouter(VirtualFileSystem):
        def capabilities(self) -> frozenset[str] | None:
            return frozenset()

    result = await IncapableRouter().write(path="/nowhere/f.txt", content="c")
    assert result.errors[0].kind is VFSErrorKind.not_found


# ----------------------------------------------------------------------
# derived capabilities + own-backend disposal
# ----------------------------------------------------------------------


async def test_default_capabilities_derive_from_the_backend() -> None:
    # The default set is computed from what the backend implements — it
    # cannot drift from reality.
    read_only = VirtualFileSystem(storage=ReadFamilyStorage())
    assert read_only.capabilities() == frozenset({"read", "stat", "ls", "tree"})
    full = VirtualFileSystem(storage=RecorderStorage())
    assert full.capabilities() == ALL_OPS


async def test_pure_router_capabilities_are_spine_plus_subtree() -> None:
    root = VirtualFileSystem()
    assert root.capabilities() == frozenset({"ls", "stat", "tree"})  # every node answers "/"
    await root.add_mount(LimitedEchoFS(caps=frozenset({"read"})), "/m")
    assert root.capabilities() == frozenset({"ls", "stat", "tree", "read"})


async def test_capabilities_none_child_keeps_no_limit_contagious() -> None:
    # A child declaring "no limit" makes the subtree unbounded too.
    root = VirtualFileSystem()
    await root.add_mount(RunnerFS(), "/tools")
    assert root.capabilities() is None


async def test_derived_capabilities_route_through_nested_routers() -> None:
    # Fan-out trusts subtree honesty: a pure router between root and a
    # capable leaf must not hide the leaf.
    root = VirtualFileSystem()
    middle = VirtualFileSystem()
    leaf = EchoFS()
    await middle.add_mount(leaf, "/leaf")
    await root.add_mount(middle, "/mid")
    result = await root.glob("*.md")
    assert result.success is True
    assert result.paths == ("/mid/leaf/hit.md",)


async def test_partial_backend_gates_unimplemented_family_as_unsupported() -> None:
    # A read-family-only terminal answers a mutation with unsupported at the
    # gate — before dispatch, on the classified channel.
    fs = VirtualFileSystem(storage=ReadFamilyStorage())
    result = await fs.write(path="/f.txt", content="x")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.unsupported
