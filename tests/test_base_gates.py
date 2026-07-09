"""The terminal gate and error taxonomy: capability (declared, not inferred),
permission composition, pinned gate order, and kind-based exception dispatch."""

from __future__ import annotations

from typing import Any

import pytest

from base_doubles import (
    BindableStorage,
    ReadFamilyStorage,
    RecorderFS,
    RecorderStorage,
    RunnerStorage,
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
from vfs.results2 import Result, ResultError, Severity, VFSErrorKind

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


@pytest.mark.parametrize("kind", [VFSErrorKind.busy, VFSErrorKind.backend_unavailable, VFSErrorKind.budget_exhausted])
def test_exception_for_kind_new_kinds_fall_back_to_base(kind: VFSErrorKind) -> None:
    # The three kinds this story adds have no dedicated exception class yet —
    # they still raise loud, just as the generic VFSError.
    assert exception_for_kind(kind) is VFSError


def test_error_returns_failed_result_by_default() -> None:
    fs = VirtualFileSystem()
    r = fs._error("gone", kind=VFSErrorKind.not_found, op="read", path=Path("/x"))
    assert r.success is False
    assert r.errors[0].kind is VFSErrorKind.not_found
    assert r.errors[0].path == "/x"


def test_error_attaches_structured_data() -> None:
    fs = VirtualFileSystem()
    r = fs._error("stale", kind=VFSErrorKind.conflict, op="edit", data={"expected": 1})
    assert r.errors[0].data == {"expected": 1}


def test_error_never_raises_and_carries_the_op() -> None:
    # The router has one failure channel: a returned Result. The op rides
    # the envelope so a wire consumer can tell which verb failed.
    fs = VirtualFileSystem()
    r = fs._error("gone", kind=VFSErrorKind.not_found, op="read")
    assert r.success is False
    assert r.op == "read"


def test_error_severity_defaults_to_error_and_accepts_tiers() -> None:
    fs = VirtualFileSystem()
    fatal = fs._error("gone", kind=VFSErrorKind.not_found, op="read")
    advisory = fs._error("skip", kind=VFSErrorKind.unsupported, op="grep", severity=Severity.info)
    assert fatal.errors[0].severity is Severity.error
    assert advisory.success is True
    assert advisory.errors[0].severity is Severity.info


def test_raise_if_failed_passes_success_through() -> None:
    ok = Result(ops=("read",), observations=[])
    assert raise_if_failed(ok) is ok


def test_raise_if_failed_maps_single_error_to_kind_exception() -> None:
    failed = VirtualFileSystem()._error("gone", kind=VFSErrorKind.not_found, op="read")
    with pytest.raises(NotFoundError) as exc:
        raise_if_failed(failed)
    # the raised exception still carries the full failed result
    assert exc.value.result is failed
    assert exc.value.result.success is False


def test_raise_if_failed_groups_multiple_errors() -> None:
    # A fan-out failure reports every downed terminal, not just the first.
    failed = Result(
        errors=[
            ResultError(kind=VFSErrorKind.not_found, message="gone"),
            ResultError(kind=VFSErrorKind.read_only, message="frozen"),
        ],
    )
    with pytest.raises(ExceptionGroup) as exc:
        raise_if_failed(failed)
    matched = {type(e) for e in exc.value.exceptions}
    assert matched == {NotFoundError, WriteConflictError}


def test_raise_if_failed_passes_warnings_and_info_through() -> None:
    # Warnings and info are loss on record, not failure — the boundary
    # adapter never turns them into exceptions.
    result = Result(
        ops=("glob",),
        errors=[
            ResultError(kind=VFSErrorKind.unaddressable, message="deep row", severity=Severity.warning),
            ResultError(kind=VFSErrorKind.unsupported, message="skipped", severity=Severity.info),
        ],
    )
    assert raise_if_failed(result) is result


# ----------------------------------------------------------------------
# capabilities — declared per entry, never inferred
# ----------------------------------------------------------------------


async def test_default_capabilities_derive_from_the_backend() -> None:
    # The default set is computed from what the backend implements — it
    # cannot drift from reality.
    read_only = VirtualFileSystem(storage=ReadFamilyStorage())
    assert read_only.capabilities() == frozenset({"read", "stat", "ls", "tree"})
    full = VirtualFileSystem(storage=RecorderStorage())
    assert full.capabilities() == ALL_OPS


async def test_capabilities_union_across_bindings() -> None:
    # The router's capabilities() is the union of every entry's declared
    # snapshot, self included.
    root = VirtualFileSystem(storage=BindableStorage(caps=frozenset({"read", "stat", "ls", "tree"})))
    assert root.capabilities() == frozenset({"read", "stat", "ls", "tree"})
    await root.bind(BindableStorage(caps=frozenset({"glean"})), "/m")
    assert root.capabilities() == frozenset({"read", "stat", "ls", "tree", "glean"})


async def test_capability_snapshot_is_pinned_at_bind_not_live() -> None:
    # Decision 2: the gate consults the bind-time snapshot. An in-process
    # backend that later "declares" more never widens what the table sees.
    backend = BindableStorage(caps=frozenset({"read"}))
    root = VirtualFileSystem(storage=backend)
    assert root.capabilities() == frozenset({"read"})
    backend._caps = frozenset({"read", "write"})  # the live backend's own set changes
    assert root.capabilities() == frozenset({"read"})  # the router's snapshot does not


# ----------------------------------------------------------------------
# capabilities gate + run verb
# ----------------------------------------------------------------------


async def test_run_on_default_root_is_unsupported() -> None:
    # The default backend (InMemoryStorage) never declares run — every path
    # answers unsupported at the gate, not not_found: the root entry always
    # resolves, it just cannot execute anything.
    root = VirtualFileSystem()
    r = await root.run("/nope/tool")
    assert r.success is False
    assert r.errors[0].kind is VFSErrorKind.unsupported


async def test_run_routes_to_child_and_rebases() -> None:
    root = VirtualFileSystem()
    catalog = RunnerStorage()
    await root.add_mount(catalog, "/nonvfs")
    r = await root.run("/nonvfs/clone-repo", arguments={"repo": "org/proj"})
    assert catalog.calls == [("run", {"path": "/clone-repo", "arguments": {"repo": "org/proj"}})]
    assert r.success is True
    assert r.paths == ("/nonvfs/clone-repo",)


async def test_capabilities_gate_blocks_unsupported_op() -> None:
    root = VirtualFileSystem()
    catalog = RunnerStorage(caps=frozenset({"read"}))
    await root.add_mount(catalog, "/nonvfs")
    blocked = await root.run("/nonvfs/clone-repo")
    assert blocked.success is False
    assert blocked.errors[0].kind is VFSErrorKind.unsupported
    assert catalog.calls == []  # never dispatched


async def test_capabilities_gate_allows_supported_op() -> None:
    root = VirtualFileSystem()
    catalog = RunnerStorage(caps=frozenset({"read"}))
    await root.add_mount(catalog, "/nonvfs")
    ok = await root.read("/nonvfs/clone-repo")
    assert ok.success is True
    assert ok.paths == ("/nonvfs/clone-repo",)
    assert catalog.calls == [("read", {"path": "/clone-repo", "columns": None})]


# ----------------------------------------------------------------------
# mutation gates across the full verb surface
# ----------------------------------------------------------------------


@pytest.mark.parametrize("op", sorted(MUTATING_OPS))
async def test_read_only_mount_rejects_every_mutation(op: str) -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/m", permissions="read")
    result = await _mutate(root, op, "/m")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.read_only
    assert child.calls == []  # gated before any dispatch


@pytest.mark.parametrize("op", sorted(MUTATING_OPS))
async def test_writable_mount_dispatches_every_mutation_once(op: str) -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
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
    await root.add_mount(RecorderStorage(), "/ro", permissions="read")
    await root.add_mount(RecorderStorage(caps=frozenset({"read"})), "/dim")
    return root


GATE_FAILURES = [
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
    ("single/incapable", lambda r: r.write(path="/dim/x.txt", content="c"), VFSErrorKind.unsupported, "/dim"),
    (
        "grouped/incapable",
        lambda r: r.stat(observations=[Observation(path=Path("/dim/f.txt"))]),
        VFSErrorKind.unsupported,
        "/dim",
    ),
    ("pair/incapable", lambda r: r.move(src="/dim/a.txt", dest="/dim/b.txt"), VFSErrorKind.unsupported, "/dim"),
    (
        "entries/incapable",
        lambda r: r.write(entries=[Entry(path=Path("/dim/f.txt"), content="c")]),
        VFSErrorKind.unsupported,
        "/dim",
    ),
    ("scoped/incapable", lambda r: r.grep("x", paths=("/dim/sub",)), VFSErrorKind.unsupported, "/dim"),
    (
        "mkedge/incapable",
        lambda r: r.mkedge("/dim/a.py", "/dim/b.py", "imports"),
        VFSErrorKind.unsupported,
        "/dim",
    ),
]


@pytest.mark.parametrize(("call", "kind", "path"), [c[1:] for c in GATE_FAILURES], ids=[c[0] for c in GATE_FAILURES])
async def test_gate_failures_carry_the_router_side_path(call: Any, kind: VFSErrorKind, path: str) -> None:
    # Every chokepoint x every gate failure: a permission denial reports the
    # addressed path; a capability miss reports the entry's bind path.
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
    child = RecorderStorage(caps=frozenset({"read"}))
    await root.add_mount(child, "/m", permissions="read")
    result = await root.write(path="/m/f.txt", content="c")
    assert result.errors[0].kind is VFSErrorKind.unsupported


async def test_gate_order_busy_outranks_capability_and_permission() -> None:
    # The busy guard runs before the entry is even resolved for gating — a
    # live bind site refuses busy no matter what the terminal would say.
    root = VirtualFileSystem()
    child = RecorderStorage(caps=frozenset({"read"}))
    await root.add_mount(child, "/m", permissions="read")
    result = await root.delete("/m")
    assert result.errors[0].kind is VFSErrorKind.busy


async def test_read_only_root_makes_writable_child_read_only_end_to_end() -> None:
    # Decision 3's recorded behavior change: ancestor restriction composes —
    # the most restrictive layer from / to the terminal wins. Add via bind()
    # (the control-plane primitive), since add_mount's own mkdir would itself
    # be gated read_only against a read-only root.
    root = VirtualFileSystem(storage=BindableStorage(), permissions="read")
    child = RecorderStorage()
    await root.bind(child, "/scratch", permissions="read_write")
    result = await root.write(path="/scratch/f.txt", content="c")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.read_only
    assert child.calls == []


# ----------------------------------------------------------------------
# partial backends
# ----------------------------------------------------------------------


async def test_partial_backend_gates_unimplemented_family_as_unsupported() -> None:
    # A read-family-only terminal answers a mutation with unsupported at the
    # gate — before dispatch, on the classified channel.
    fs = VirtualFileSystem(storage=ReadFamilyStorage())
    result = await fs.write(path="/f.txt", content="x")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.unsupported
