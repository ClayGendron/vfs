"""Mount administration: ``mounts()`` introspection, ``remount`` policy
changes in place, and the ``deny_ops`` mount-flag family."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, cast

import pytest

from tests.support.base_doubles import (
    BindableStorage,
    CapCountingStorage,
    RecorderFS,
    RecorderStorage,
    RunnerStorage,
    SuspendingProbeStorage,
)
from vfs.base import MountMeta, VirtualFileSystem
from vfs.exceptions import MountError
from vfs.permissions import PermissionMap, read_only, read_write, validate_permission
from vfs.results import VFSErrorKind

if TYPE_CHECKING:
    from vfs.ops import Op
    from vfs.permissions import PermissionsPayload


def payload_to_map(payload: PermissionsPayload) -> PermissionMap:
    """Typed replay of a row's ``permissions`` payload into a map.

    The payload's ``list[list[str]]`` is runtime-valid for the constructor
    but not statically assignable to its declared overrides tuple type.
    """
    return PermissionMap(
        default=payload["default"],
        overrides=tuple((prefix, validate_permission(perm)) for prefix, perm in payload["overrides"]),
    )


def replay_ops(row_deny_ops: tuple[str, ...]) -> tuple[Op, ...]:
    """Typed replay of a row's ``deny_ops`` — the intake mirror of
    ``payload_to_map``.

    The row's ``tuple[str, ...]`` is not statically assignable to the
    intakes' ``Iterable[Op]``; the cast widens it back.  Stored masks
    replay fine at runtime regardless (unknown op names are deliberately
    maskable), so this is purely a ty-boundary conversion.
    """
    return cast("tuple[Op, ...]", row_deny_ops)


# ----------------------------------------------------------------------
# MountMeta invariant
# ----------------------------------------------------------------------


def test_meta_caps_is_always_the_masked_intersection() -> None:
    meta = MountMeta(declared_caps=frozenset({"read", "write", "run"}), deny_ops=frozenset({"run", "edit"}))
    assert meta.caps == frozenset({"read", "write"})
    assert meta.declared_caps == frozenset({"read", "write", "run"})
    assert MountMeta().caps == frozenset()


# ----------------------------------------------------------------------
# mounts() — the table is readable
# ----------------------------------------------------------------------


def test_fresh_router_has_one_root_row() -> None:
    fs = VirtualFileSystem()
    rows = fs.mounts()
    assert len(rows) == 1
    row = rows[0]
    assert row.path == "/"
    assert row.caps == tuple(sorted(fs.capabilities()))
    assert row.permissions == {"default": "read_write", "overrides": []}
    assert row.deny_ops == ()
    assert row.no_overlay is False
    assert row.owned is True
    assert row.storage_type == "InMemoryStorage"


async def test_rows_track_the_table_lifecycle() -> None:
    fs = VirtualFileSystem(storage=BindableStorage())
    child = RecorderStorage(name="child")
    await fs.add_mount(child, "/data", no_overlay=True, owned=False)
    rows = {r.path: r for r in fs.mounts()}
    assert set(rows) == {"/", "/data"}
    assert rows["/data"].storage_name == "child"
    assert rows["/data"].no_overlay is True
    assert rows["/data"].owned is False
    assert rows["/data"].caps == tuple(sorted(child.capabilities()))

    await fs.remove_mount("/data")
    assert {r.path for r in fs.mounts()} == {"/"}
    await fs.close()
    assert fs.mounts() == ()


async def test_rows_are_ordered_by_bind_path() -> None:
    fs = VirtualFileSystem(storage=BindableStorage())
    for path in ("/zeta", "/alpha", "/alpha/inner", "/mid"):
        await fs.bind(BindableStorage(name=path.strip("/")), path)
    assert [r.path for r in fs.mounts()] == ["/", "/alpha", "/alpha/inner", "/mid", "/zeta"]


async def test_every_row_is_a_json_fixed_point() -> None:
    fs = VirtualFileSystem(storage=BindableStorage(), permissions=read_write(read=["/frozen"]))
    await fs.bind(RecorderStorage(name="masked"), "/m", permissions=read_only(write=["/inbox"]), deny_ops={"edit"})
    await fs.bind(RecorderStorage(name="bare"), "/n")
    for row in fs.mounts():
        dumped = json.dumps(row._asdict())
        loaded = json.loads(dumped)
        assert loaded["path"] == row.path
        assert loaded["caps"] == list(row.caps)
        assert loaded["deny_ops"] == list(row.deny_ops)
        assert loaded["permissions"] == row.permissions
        assert loaded["no_overlay"] == row.no_overlay
        assert loaded["owned"] == row.owned


async def test_replay_round_trip_rebuilds_an_equal_table() -> None:
    fs = VirtualFileSystem(
        storage=BindableStorage(name="rootstore"),
        permissions=read_write(read=["/frozen", "/frozen/deep"]),
        deny_ops={"mkedge"},
    )
    await fs.bind(
        BindableStorage(name="masked"), "/m", permissions=read_only(write=["/inbox"]), deny_ops={"edit", "run"}
    )
    await fs.bind(BindableStorage(name="plain"), "/p")
    await fs.bind(BindableStorage(name="nested"), "/m/deep", owned=False, no_overlay=True)
    rows = fs.mounts()

    storages = {b.storage.name: b.storage for b in fs._bindings.values()}
    root_row = rows[0]
    assert root_row.path == "/"
    assert root_row.permissions is not None
    rebuilt = VirtualFileSystem(
        storage=storages[root_row.storage_name],
        permissions=payload_to_map(root_row.permissions),
        deny_ops=replay_ops(root_row.deny_ops),
        no_overlay=root_row.no_overlay,
    )
    for row in rows[1:]:
        await rebuilt.bind(
            storages[row.storage_name],
            row.path,
            permissions=None if row.permissions is None else payload_to_map(row.permissions),
            deny_ops=replay_ops(row.deny_ops),
            no_overlay=row.no_overlay,
            owned=row.owned,
        )
    assert rebuilt.mounts() == rows


async def test_replay_of_a_grandfathered_seal_goes_seal_last() -> None:
    # A remount(no_overlay=True) over existing children produces rows no
    # verbatim bind order can rebuild — the documented recipe seals last.
    fs = VirtualFileSystem(storage=BindableStorage(name="rootstore"))
    parent = BindableStorage(name="parent")
    child = BindableStorage(name="child")
    await fs.bind(parent, "/a")
    await fs.bind(child, "/a/b")
    await fs.remount("/a", no_overlay=True)
    await fs.remount("/", no_overlay=True)
    rows = fs.mounts()

    storages = {b.storage.name: b.storage for b in fs._bindings.values()}
    root_row = rows[0]
    assert root_row.permissions is not None
    rebuilt = VirtualFileSystem(
        storage=storages[root_row.storage_name],
        permissions=payload_to_map(root_row.permissions),
        deny_ops=replay_ops(root_row.deny_ops),
    )
    for row in rows[1:]:
        await rebuilt.bind(
            storages[row.storage_name],
            row.path,
            permissions=None if row.permissions is None else payload_to_map(row.permissions),
            deny_ops=replay_ops(row.deny_ops),
            owned=row.owned,
        )
    for row in rows:
        if row.no_overlay:
            await rebuilt.remount(row.path, no_overlay=True)
    assert rebuilt.mounts() == rows


async def test_child_bind_without_permissions_reports_none_and_root_never_does() -> None:
    fs = VirtualFileSystem(storage=BindableStorage())
    await fs.bind(RecorderStorage(name="child"), "/m")
    rows = {r.path: r for r in fs.mounts()}
    assert rows["/m"].permissions is None
    assert rows["/"].permissions is not None


async def test_mounts_does_no_storage_io() -> None:
    root = CapCountingStorage(name="root")
    child = CapCountingStorage(name="child")
    fs = VirtualFileSystem(storage=root)
    await fs.add_mount(child, "/data")
    root.calls.clear()
    child.calls.clear()
    root_snapshot, child_snapshot = root.capabilities_calls, child.capabilities_calls

    fs.mounts()
    fs.mounts()
    assert root.calls == []
    assert child.calls == []
    assert root.capabilities_calls == root_snapshot
    assert child.capabilities_calls == child_snapshot


async def test_description_is_a_live_attribute_read() -> None:
    child = RecorderStorage(name="child", description="before")
    fs = VirtualFileSystem(storage=BindableStorage())
    await fs.bind(child, "/m")
    child.calls.clear()
    child.description = "after"
    rows = {r.path: r for r in fs.mounts()}
    assert rows["/m"].description == "after"
    assert child.calls == []


# ----------------------------------------------------------------------
# remount — entry policy changes in place
# ----------------------------------------------------------------------


async def test_remount_read_makes_writes_classify_as_permission_denials() -> None:
    fs = RecorderFS()
    before = await fs.write(path="/f.md", content="x")
    assert before.success
    await fs.remount("/", permissions="read")
    after = await fs.write(path="/f.md", content="x")
    assert not after.success
    assert after.errors[0].kind is VFSErrorKind.read_only


async def test_unbind_bind_has_a_gap_and_remount_does_not() -> None:
    # The parent's probe reads suspend, so the rebind sequence yields
    # mid-flight; a gathered read then lands while /m is unbound and
    # resolves to the parent entry — the non-atomic seam.
    parent = SuspendingProbeStorage(name="parent")
    child = RecorderStorage(name="child")
    fs = VirtualFileSystem(storage=parent)
    await fs.bind(child, "/m")
    parent.calls.clear()
    child.calls.clear()

    async def rebind() -> None:
        await fs.unbind("/m")
        await fs.bind(child, "/m")

    await asyncio.gather(rebind(), fs.read(path="/m/f.md"))
    assert any(op == "read" and str(kw.get("path")) == "/m/f.md" for op, kw in parent.calls)
    assert all(op != "read" for op, _ in child.calls)

    # remount never awaits while the entry is absent: the same gathered
    # read resolves at the bound path under old or new meta, never parent.
    parent2 = SuspendingProbeStorage(name="parent2")
    child2 = RecorderStorage(name="child2")
    fs2 = VirtualFileSystem(storage=parent2)
    await fs2.bind(child2, "/m")
    parent2.calls.clear()
    child2.calls.clear()
    await asyncio.gather(fs2.remount("/m", permissions="read"), fs2.read(path="/m/f.md"))
    assert all(op != "read" for op, _ in parent2.calls)
    assert [op for op, _ in child2.calls] == ["read"]


async def test_refresh_caps_picks_up_a_widened_declaration() -> None:
    narrow: frozenset[Op] = frozenset({"read", "stat", "ls"})
    child = RecorderStorage(name="child", caps=narrow)
    fs = VirtualFileSystem(storage=BindableStorage())
    await fs.bind(child, "/m")
    wider: frozenset[Op] = frozenset({"read", "stat", "ls", "write"})
    child._caps = wider

    await fs.remount("/m")  # no refresh — snapshot stays
    assert "write" not in {r.path: r for r in fs.mounts()}["/m"].caps
    await fs.remount("/m", refresh_caps=True)
    assert "write" in {r.path: r for r in fs.mounts()}["/m"].caps


async def test_remount_preserves_every_unchanged_field() -> None:
    fs = VirtualFileSystem(storage=BindableStorage())
    await fs.bind(
        RecorderStorage(name="child"), "/m", permissions=read_only(write=["/inbox"]), deny_ops={"edit"}, owned=False
    )
    before = {r.path: r for r in fs.mounts()}["/m"]
    await fs.remount("/m", no_overlay=True)
    after = {r.path: r for r in fs.mounts()}["/m"]
    assert after.no_overlay is True
    assert after._replace(no_overlay=False) == before

    await fs.remount("/m")  # the all-None no-op
    assert {r.path: r for r in fs.mounts()}["/m"] == after


async def test_remount_unknown_path_and_closed_table_raise() -> None:
    fs = VirtualFileSystem(storage=BindableStorage())
    with pytest.raises(ValueError, match="No mount at"):
        await fs.remount("/nope", permissions="read")
    with pytest.raises(ValueError, match="No mount at"):
        await fs.remount("/nope", refresh_caps=True)
    await fs.close()
    with pytest.raises(ValueError, match="No mount at"):
        await fs.remount("/", permissions="read")


async def test_remount_refuses_when_the_probed_mount_is_rebound_mid_flight(monkeypatch) -> None:
    # refresh_caps probes capabilities() outside the lock; a rival
    # rebinding the entry before the lock lands must refuse, not adopt.
    fs = VirtualFileSystem(storage=BindableStorage())
    child = RecorderStorage(name="child")
    await fs.bind(child, "/m")
    key = next(k for k in fs._bindings if str(k) == "/m")
    rival = RecorderStorage(name="rival")
    real = child.capabilities

    def swap_binding() -> frozenset[Op]:
        fs._bindings[key] = fs._bindings[key]._replace(storage=rival)
        return real()

    monkeypatch.setattr(child, "capabilities", swap_binding)
    with pytest.raises(ValueError, match="changed while remounting"):
        await fs.remount("/m", refresh_caps=True)


async def test_no_overlay_remount_grandfathers_children_and_ratchets() -> None:
    fs = VirtualFileSystem(storage=BindableStorage())
    parent = BindableStorage(name="parent")
    child = RecorderStorage(name="child")
    await fs.bind(parent, "/a")
    await fs.bind(child, "/a/b")

    await fs.remount("/a", no_overlay=True)
    answered = await fs.read(path="/a/b/f.md")
    assert answered.success  # the grandfathered child still dispatches
    with pytest.raises(ValueError, match="does not allow binds beneath it"):
        await fs.bind(RecorderStorage(name="late"), "/a/c")

    # The ratchet: the sealed subtree can shrink but never grow back.
    await fs.unbind("/a/b")
    with pytest.raises(ValueError, match="does not allow binds beneath it"):
        await fs.bind(child, "/a/b")


async def test_no_overlay_remount_on_root_seals_the_namespace() -> None:
    fs = VirtualFileSystem(storage=BindableStorage())
    await fs.bind(RecorderStorage(name="child"), "/m")
    await fs.remount("/", no_overlay=True)
    with pytest.raises(ValueError, match="does not allow child mounts"):
        await fs.bind(RecorderStorage(name="late"), "/n")
    rows = {r.path: r for r in fs.mounts()}
    assert rows["/"].no_overlay is True
    assert "/m" in rows  # the sealed root still shows its child row


# ----------------------------------------------------------------------
# deny_ops — the noexec family
# ----------------------------------------------------------------------


async def test_deny_run_is_noexec_for_a_tool_mount() -> None:
    runner = RunnerStorage()
    # A run-less root, so the namespace-level capabilities assertion below
    # tests "no other entry declares it" honestly.
    runless: frozenset[Op] = frozenset({"read", "stat", "ls", "tree"})
    fs = VirtualFileSystem(storage=BindableStorage(caps=runless))
    await fs.bind(runner, "/tools", deny_ops={"run"})

    ran = await fs.run("/tools/x")
    assert not ran.success
    assert ran.errors[0].kind is VFSErrorKind.unsupported
    assert str(ran.errors[0].path) == "/tools"
    read = await fs.read(path="/tools/x")
    assert read.success
    assert "run" not in fs.capabilities()


async def test_masks_never_alter_fanout() -> None:
    masked_fs = VirtualFileSystem(storage=BindableStorage())
    await masked_fs.bind(BindableStorage(name="entry"), "/e", deny_ops={"run"})
    plain_fs = VirtualFileSystem(storage=BindableStorage())
    await plain_fs.bind(BindableStorage(name="entry"), "/e")

    masked = await masked_fs.glob("*.py")
    plain = await plain_fs.glob("*.py")
    assert masked.success == plain.success
    assert [(e.kind, str(e.path or "")) for e in masked.errors] == [(e.kind, str(e.path or "")) for e in plain.errors]
    assert len(masked.observations) == len(plain.observations)


async def test_read_family_masks_are_rejected_at_every_intake() -> None:
    with pytest.raises(ValueError, match="read-family"):
        VirtualFileSystem(deny_ops={"read"})

    root = BindableStorage(name="root")
    fs = VirtualFileSystem(storage=root)
    with pytest.raises(ValueError, match="read-family"):
        await fs.bind(RecorderStorage(name="c1"), "/m", deny_ops={"ls"})
    assert {r.path for r in fs.mounts()} == {"/"}

    root.calls.clear()
    with pytest.raises(ValueError, match="read-family"):
        await fs.add_mount(RecorderStorage(name="c2"), "/m", deny_ops={"stat"})
    assert {r.path for r in fs.mounts()} == {"/"}
    assert all(op != "mkdir" for op, _ in root.calls)  # rejected before the site mkdir

    await fs.bind(RecorderStorage(name="c3"), "/m", deny_ops={"edit"})
    with pytest.raises(ValueError, match="read-family"):
        await fs.remount("/m", deny_ops={"grep"})
    assert {r.path: r for r in fs.mounts()}["/m"].deny_ops == ("edit",)


async def test_bare_string_deny_ops_is_rejected_not_char_splattered() -> None:
    # frozenset("run") would silently store {'r','u','n'} — an inert mask
    # that fails open and can even clear a working one via remount.
    with pytest.raises(TypeError, match="bare string"):
        VirtualFileSystem(deny_ops="read")  # ty: ignore[invalid-argument-type]

    fs = VirtualFileSystem(storage=BindableStorage())
    with pytest.raises(TypeError, match="bare string"):
        await fs.bind(RecorderStorage(name="c1"), "/m", deny_ops="run")  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError, match="bare string"):
        await fs.add_mount(RecorderStorage(name="c2"), "/m", deny_ops="run")  # ty: ignore[invalid-argument-type]

    await fs.bind(RecorderStorage(name="c3"), "/m", deny_ops={"run"})
    with pytest.raises(TypeError, match="bare string"):
        await fs.remount("/m", deny_ops="edit")  # ty: ignore[invalid-argument-type]
    assert {r.path: r for r in fs.mounts()}["/m"].deny_ops == ("run",)  # the working mask survived


async def test_read_family_mask_with_refresh_never_resnapshots() -> None:
    child = CapCountingStorage(name="child")
    fs = VirtualFileSystem(storage=BindableStorage())
    await fs.bind(child, "/m")
    before_caps = {r.path: r for r in fs.mounts()}["/m"].caps
    count = child.capabilities_calls
    with pytest.raises(ValueError, match="read-family"):
        await fs.remount("/m", deny_ops={"read"}, refresh_caps=True)
    assert child.capabilities_calls == count
    assert {r.path: r for r in fs.mounts()}["/m"].caps == before_caps


async def test_parent_mkdir_mask_refuses_add_mount_but_not_bind() -> None:
    fs = VirtualFileSystem(storage=BindableStorage(), deny_ops={"mkdir"})
    with pytest.raises(MountError):
        await fs.add_mount(RecorderStorage(name="c1"), "/m")
    # The probe is ungated (stat/ls only), so a direct bind still lands.
    await fs.bind(RecorderStorage(name="c2"), "/n")
    assert "/n" in {r.path for r in fs.mounts()}


async def test_inert_mask_is_stored_and_bites_after_refresh() -> None:
    narrow: frozenset[Op] = frozenset({"read", "stat", "ls"})
    child = BindableStorage(name="child", caps=narrow)
    fs = VirtualFileSystem(storage=BindableStorage())
    await fs.bind(child, "/m", deny_ops={"run"})

    row = {r.path: r for r in fs.mounts()}["/m"]
    assert row.caps == tuple(sorted(narrow))  # inert: caps unchanged
    assert row.deny_ops == ("run",)  # but the mask is still echoed

    wider: frozenset[Op] = frozenset({"read", "stat", "ls", "run"})
    child._caps = wider
    await fs.remount("/m", refresh_caps=True)
    row = {r.path: r for r in fs.mounts()}["/m"]
    assert "run" not in row.caps  # the stored mask started biting


async def test_constructor_deny_ops_masks_the_root_entry() -> None:
    fs = VirtualFileSystem(storage=RecorderStorage(), deny_ops={"write"})
    denied = await fs.write(path="/f.md", content="x")
    assert not denied.success
    assert denied.errors[0].kind is VFSErrorKind.unsupported
    row = fs.mounts()[0]
    assert row.deny_ops == ("write",)
    assert "write" not in row.caps


async def test_mask_replace_and_clear_recompute_without_storage_io() -> None:
    child = CapCountingStorage(name="child")
    fs = VirtualFileSystem(storage=BindableStorage())
    await fs.bind(child, "/m", deny_ops={"edit"})
    declared = tuple(sorted(child.capabilities()))
    count = child.capabilities_calls

    await fs.remount("/m", deny_ops={"run"})
    row = {r.path: r for r in fs.mounts()}["/m"]
    assert "edit" in row.caps  # restored from the stored snapshot
    assert "run" not in row.caps
    await fs.remount("/m", deny_ops=())
    assert {r.path: r for r in fs.mounts()}["/m"].caps == declared
    assert child.capabilities_calls == count  # neither call re-snapshotted
