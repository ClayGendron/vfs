"""Mount administration: the ``Mount`` class, ``mounts()``, ``update_mount``
policy changes in place, and the ``deny_ops`` mount-flag family."""

from __future__ import annotations

import asyncio
import json
from dataclasses import FrozenInstanceError, replace
from typing import TYPE_CHECKING, Any, cast

import pytest

import vfs
import vfs.base
import vfs.mounts
from tests.support.base_doubles import (
    BindableStorage,
    CapCountingStorage,
    RecorderFS,
    RecorderStorage,
    RunnerStorage,
    SuspendingProbeStorage,
)
from vfs import InMemoryStorage, Mount, VirtualFileSystem
from vfs.authority import Authority
from vfs.base import AsyncVirtualFileSystem, Location
from vfs.exceptions import MountError
from vfs.paths import Path
from vfs.permissions import read_only, read_write
from vfs.results import ErrorKind, Result, ResultError

if TYPE_CHECKING:
    from vfs.ops import Op


def replay_ops(deny_ops: frozenset[str]) -> frozenset[Op]:
    """Typed replay of a mount's ``deny_ops`` into an intake.

    The mount's ``frozenset[str]`` is not statically assignable to the
    intakes' ``Iterable[Op]``; the cast widens it back.  Stored masks
    replay fine at runtime regardless (unknown op names are deliberately
    maskable), so this is purely a ty-boundary conversion.
    """
    return cast("frozenset[Op]", deny_ops)


# ----------------------------------------------------------------------
# Mount — one public class
# ----------------------------------------------------------------------


def test_a_mounts_caps_are_its_declared_caps_less_its_mask() -> None:
    mount = Mount(
        path=Path("/m"),
        storage=InMemoryStorage(),
        declared_caps=frozenset({"read", "write", "run"}),
        deny_ops=frozenset({"run", "edit"}),
    )
    assert mount.caps == frozenset({"read", "write"})
    assert mount.declared_caps == frozenset({"read", "write", "run"})
    assert Mount(path=Path("/m"), storage=InMemoryStorage()).caps == frozenset()
    # A changed mask is a new mount, and its caps are computed again.
    assert replace(mount, deny_ops=frozenset()).caps == frozenset({"read", "write", "run"})


def test_a_mount_is_frozen_and_its_caps_cannot_be_passed() -> None:
    storage = InMemoryStorage()
    mount = Mount(path=Path("/m"), storage=storage)
    with pytest.raises(FrozenInstanceError):
        mount.no_overlay = True  # ty: ignore[invalid-assignment]
    with pytest.raises(TypeError):
        Mount(path=Path("/m"), storage=storage, caps=frozenset({"read"}))  # ty: ignore[unknown-argument]


def test_mount_is_the_one_class_for_a_mount() -> None:
    assert vfs.Mount is vfs.mounts.Mount
    assert vfs.MountPayload is vfs.mounts.MountPayload
    assert {"Mount", "MountPayload"} <= set(vfs.__all__)
    for gone in ("Binding", "MountMeta", "MountInfo"):
        assert not hasattr(vfs, gone), gone
        assert not hasattr(vfs.base, gone), gone


@pytest.mark.parametrize("face", [AsyncVirtualFileSystem, VirtualFileSystem])
def test_the_mount_methods_are_a_verb_then_the_noun(face: type) -> None:
    for name in ("add_mount", "remove_mount", "update_mount", "mounts"):
        assert callable(getattr(face, name)), name
    for gone in ("bind", "unbind", "remount"):
        assert not hasattr(face, gone), gone


# ----------------------------------------------------------------------
# mounts() — the table is readable
# ----------------------------------------------------------------------


def test_fresh_router_has_one_root_mount() -> None:
    fs = AsyncVirtualFileSystem()
    mounts = fs.mounts()
    assert len(mounts) == 1
    mount = mounts[0]
    assert isinstance(mount, Mount)
    assert mount.path == "/"
    assert mount.caps == fs.capabilities()
    assert mount.permissions is not None
    assert mount.permissions.to_payload() == {"default": "read_write", "overrides": []}
    assert mount.deny_ops == frozenset()
    assert mount.no_overlay is False
    assert mount.owned is True
    assert isinstance(mount.storage, InMemoryStorage)


async def test_mounts_track_the_table_lifecycle() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    child = RecorderStorage(name="child")
    await fs.add_mount(child, "/data", no_overlay=True, owned=False)
    rows = {str(r.path): r for r in fs.mounts()}
    assert set(rows) == {"/", "/data"}
    assert rows["/data"].storage is child
    assert rows["/data"].no_overlay is True
    assert rows["/data"].owned is False
    assert rows["/data"].caps == child.capabilities()

    removed = await fs.remove_mount("/data")
    assert removed == rows["/data"]
    assert removed.storage is child
    assert {r.path for r in fs.mounts()} == {"/"}
    await fs.close()
    assert fs.mounts() == ()


async def test_rows_are_ordered_by_mount_path() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    for path in ("/zeta", "/alpha", "/alpha/inner", "/mid"):
        await fs.add_mount(BindableStorage(name=path.strip("/")), path)
    assert [r.path for r in fs.mounts()] == ["/", "/alpha", "/alpha/inner", "/mid", "/zeta"]


async def test_every_payload_is_a_json_fixed_point() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage(), permissions=read_write(read=["/frozen"]))
    masked = RecorderStorage(name="masked")
    await fs.add_mount(masked, "/m", permissions=read_only(write=["/inbox"]), deny_ops={"edit"})
    await fs.add_mount(RecorderStorage(name="bare"), "/n")
    for mount in fs.mounts():
        payload = mount.to_payload()
        assert json.loads(json.dumps(payload)) == payload
        assert payload["path"] == mount.path
        assert payload["storage_name"] == mount.storage.name
        assert payload["storage_type"] == type(mount.storage).__name__
        assert payload["description"] == mount.storage.description
        assert payload["caps"] == sorted(mount.caps)
        assert payload["deny_ops"] == sorted(mount.deny_ops)
        assert payload["permissions"] == (None if mount.permissions is None else mount.permissions.to_payload())
        assert payload["no_overlay"] == mount.no_overlay
        assert payload["owned"] == mount.owned
    assert set(fs.mounts()[0].to_payload()) == {
        "path",
        "storage_name",
        "storage_type",
        "description",
        "caps",
        "deny_ops",
        "permissions",
        "no_overlay",
        "owned",
    }


async def replay(mounts: tuple[Mount, ...]) -> AsyncVirtualFileSystem:
    """The documented recipe: every mount added bare, then each one's policy applied, deepest first.

    A mount that is read-only, masks ``mkdir`` or is sealed with
    ``no_overlay`` refuses the new mounts beneath it, so no order of
    ``add_mount`` calls that carry their policy rebuilds every table.
    A read-only mount also refuses a change to the mounts beneath it,
    so the policy of the deepest mount goes on first and the root's last.
    """
    root = mounts[0]
    rebuilt = AsyncVirtualFileSystem(storage=root.storage)
    for mount in mounts[1:]:
        await rebuilt.add_mount(mount.storage, mount.path, owned=mount.owned)
    for mount in reversed(mounts):
        await rebuilt.update_mount(
            mount.path, permissions=mount.permissions, deny_ops=replay_ops(mount.deny_ops), no_overlay=mount.no_overlay
        )
    return rebuilt


async def test_replay_round_trip_rebuilds_an_equal_table() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage(name="rootstore"))
    await fs.add_mount(BindableStorage(name="masked"), "/m")
    await fs.add_mount(BindableStorage(name="plain"), "/p")
    await fs.add_mount(BindableStorage(name="nested"), "/m/deep", owned=False, no_overlay=True)
    await fs.update_mount("/m", permissions=read_only(write=["/inbox"]), deny_ops={"edit", "run", "mkdir"})
    await fs.update_mount("/", permissions=read_write(read=["/frozen", "/frozen/deep"]), deny_ops={"mkedge"})
    mounts = fs.mounts()

    assert mounts[0].path == "/"
    assert (await replay(mounts)).mounts() == mounts


async def test_replay_of_a_sealed_table_applies_the_seal_last() -> None:
    # An update_mount(no_overlay=True) over existing children produces mounts
    # no order of add_mount calls that carry the flag can rebuild.
    fs = AsyncVirtualFileSystem(storage=BindableStorage(name="rootstore"))
    await fs.add_mount(BindableStorage(name="parent"), "/a")
    await fs.add_mount(BindableStorage(name="child"), "/a/b")
    await fs.update_mount("/a", no_overlay=True)
    await fs.update_mount("/", no_overlay=True)
    mounts = fs.mounts()

    assert (await replay(mounts)).mounts() == mounts


async def test_child_mount_without_permissions_reports_none_and_root_never_does() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(RecorderStorage(name="child"), "/m")
    rows = {str(r.path): r for r in fs.mounts()}
    assert rows["/m"].permissions is None
    assert rows["/"].permissions is not None


async def test_mounts_does_no_storage_io() -> None:
    root = CapCountingStorage(name="root")
    child = CapCountingStorage(name="child")
    fs = AsyncVirtualFileSystem(storage=root)
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
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(child, "/m")
    child.calls.clear()
    child.description = "after"
    rows = {str(r.path): r for r in fs.mounts()}
    assert rows["/m"].to_payload()["description"] == "after"
    assert child.calls == []


# ----------------------------------------------------------------------
# update_mount — entry policy changes in place
# ----------------------------------------------------------------------


async def test_update_mount_read_makes_writes_classify_as_permission_denials() -> None:
    fs = RecorderFS()
    before = await fs.write(path="/f.md", content="x")
    assert before.success
    await fs.update_mount("/", permissions="read")
    after = await fs.write(path="/f.md", content="x")
    assert not after.success
    assert after.errors[0].kind is ErrorKind.read_only


async def test_remove_then_add_has_a_gap_and_update_mount_does_not() -> None:
    # The parent's probe reads suspend, so mounting again yields mid-flight;
    # a gathered read then lands while /m has no mount and resolves to the parent.
    parent = SuspendingProbeStorage(name="parent")
    child = RecorderStorage(name="child")
    fs = AsyncVirtualFileSystem(storage=parent)
    await fs.add_mount(child, "/m")
    parent.calls.clear()
    child.calls.clear()

    async def mount_again() -> None:
        await fs.remove_mount("/m")
        await fs.add_mount(child, "/m")

    await asyncio.gather(mount_again(), fs.read(path="/m/f.md"))
    assert any(op == "read" and str(kw.get("path")) == "/m/f.md" for op, kw in parent.calls)
    assert all(op != "read" for op, _ in child.calls)

    # update_mount never awaits while the mount is absent: the same gathered
    # read resolves at the mount point under old or new policy, never parent.
    parent2 = SuspendingProbeStorage(name="parent2")
    child2 = RecorderStorage(name="child2")
    fs2 = AsyncVirtualFileSystem(storage=parent2)
    await fs2.add_mount(child2, "/m")
    parent2.calls.clear()
    child2.calls.clear()
    await asyncio.gather(fs2.update_mount("/m", permissions="read"), fs2.read(path="/m/f.md"))
    assert all(op != "read" for op, _ in parent2.calls)
    assert [op for op, _ in child2.calls] == ["read"]


async def test_refresh_caps_picks_up_a_widened_declaration() -> None:
    narrow: frozenset[Op] = frozenset({"read", "stat", "ls"})
    child = RecorderStorage(name="child", caps=narrow)
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(child, "/m")
    wider: frozenset[Op] = frozenset({"read", "stat", "ls", "write"})
    child._caps = wider

    await fs.update_mount("/m")  # no refresh — snapshot stays
    assert "write" not in {str(r.path): r for r in fs.mounts()}["/m"].caps
    await fs.update_mount("/m", refresh_caps=True)
    assert "write" in {str(r.path): r for r in fs.mounts()}["/m"].caps


async def test_update_mount_preserves_every_unchanged_field() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(
        RecorderStorage(name="child"), "/m", permissions=read_only(write=["/inbox"]), deny_ops={"edit"}, owned=False
    )
    before = {str(r.path): r for r in fs.mounts()}["/m"]
    await fs.update_mount("/m", no_overlay=True)
    after = {str(r.path): r for r in fs.mounts()}["/m"]
    assert after.no_overlay is True
    assert replace(after, no_overlay=False) == before

    await fs.update_mount("/m")  # the all-None no-op
    assert {str(r.path): r for r in fs.mounts()}["/m"] == after


async def test_update_mount_unknown_path_and_closed_table_raise() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    with pytest.raises(ValueError, match="No mount at"):
        await fs.update_mount("/nope", permissions="read")
    with pytest.raises(ValueError, match="No mount at"):
        await fs.update_mount("/nope", refresh_caps=True)
    await fs.close()
    with pytest.raises(ValueError, match="No mount at"):
        await fs.update_mount("/", permissions="read")


async def test_update_mount_refuses_when_the_probed_mount_is_replaced_mid_flight(monkeypatch) -> None:
    # refresh_caps probes capabilities() outside the lock; a rival
    # replacing the mount before the lock lands must refuse, not adopt.
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    child = RecorderStorage(name="child")
    await fs.add_mount(child, "/m")
    key = next(k for k in fs._mounts if str(k) == "/m")
    rival = RecorderStorage(name="rival")
    real = child.capabilities

    def swap_mount() -> frozenset[Op]:
        fs._mounts[key] = replace(fs._mounts[key], storage=rival)
        return real()

    monkeypatch.setattr(child, "capabilities", swap_mount)
    with pytest.raises(ValueError, match="changed while it was being updated"):
        await fs.update_mount("/m", refresh_caps=True)


async def test_no_overlay_update_grandfathers_children_and_ratchets() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    parent = BindableStorage(name="parent")
    child = RecorderStorage(name="child")
    await fs.add_mount(parent, "/a")
    await fs.add_mount(child, "/a/b")

    await fs.update_mount("/a", no_overlay=True)
    answered = await fs.read(path="/a/b/f.md")
    assert answered.success  # the grandfathered child still dispatches
    with pytest.raises(ValueError, match="does not allow mounts beneath it"):
        await fs.add_mount(RecorderStorage(name="late"), "/a/c")

    # The ratchet: the sealed subtree can shrink but never grow back.
    await fs.remove_mount("/a/b")
    with pytest.raises(ValueError, match="does not allow mounts beneath it"):
        await fs.add_mount(child, "/a/b")


async def test_no_overlay_update_on_root_seals_the_namespace() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(RecorderStorage(name="child"), "/m")
    await fs.update_mount("/", no_overlay=True)
    with pytest.raises(ValueError, match="does not allow child mounts"):
        await fs.add_mount(RecorderStorage(name="late"), "/n")
    rows = {str(r.path): r for r in fs.mounts()}
    assert rows["/"].no_overlay is True
    assert "/m" in rows  # the sealed root still shows its child row


# ----------------------------------------------------------------------
# deny_ops — the noexec family
# ----------------------------------------------------------------------


async def test_deny_run_is_noexec_for_a_tool_mount() -> None:
    runner = RunnerStorage()
    # A run-less root, so the namespace-level capabilities assertion below
    # tests "no other entry declares it" honestly. It declares mkdir, which a mount needs.
    runless: frozenset[Op] = frozenset({"read", "stat", "ls", "tree", "mkdir"})
    fs = AsyncVirtualFileSystem(storage=BindableStorage(caps=runless))
    await fs.add_mount(runner, "/tools", deny_ops={"run"})

    ran = await fs.run("/tools/x")
    assert not ran.success
    assert ran.errors[0].kind is ErrorKind.unsupported
    assert str(ran.errors[0].path) == "/tools"
    read = await fs.read(path="/tools/x")
    assert read.success
    assert "run" not in fs.capabilities()


async def test_masks_never_alter_fanout() -> None:
    masked_fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await masked_fs.add_mount(BindableStorage(name="entry"), "/e", deny_ops={"run"})
    plain_fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await plain_fs.add_mount(BindableStorage(name="entry"), "/e")

    masked = await masked_fs.glob("*.py")
    plain = await plain_fs.glob("*.py")
    assert masked.success == plain.success
    assert [(e.kind, str(e.path or "")) for e in masked.errors] == [(e.kind, str(e.path or "")) for e in plain.errors]
    assert len(masked.observations) == len(plain.observations)


def test_the_grant_listing_is_a_read_and_cannot_be_masked() -> None:
    # grants only lists the grant rows, so refusing it is the storage's rights' job, as for read.
    with pytest.raises(ValueError, match="grants"):
        AsyncVirtualFileSystem(deny_ops={"grants"})
    assert AsyncVirtualFileSystem(deny_ops={"grant", "revoke"}).mounts()[0].deny_ops == frozenset({"grant", "revoke"})


async def test_an_empty_mount_path_is_refused_and_never_falls_back_to_the_storage_name() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage(name="root"))
    with pytest.raises(ValueError, match="empty"):
        await fs.add_mount(RecorderStorage(name="named"), path="")
    assert {r.path for r in fs.mounts()} == {"/"}
    await fs.add_mount(RecorderStorage(name="named"))
    assert {r.path for r in fs.mounts()} == {"/", "/named"}


def test_a_storage_whose_read_verbs_are_not_callable_cannot_be_mounted() -> None:
    class Broken(RecorderStorage):
        read = 5

    with pytest.raises(TypeError, match="read"):
        AsyncVirtualFileSystem(storage=Broken())  # ty: ignore[invalid-argument-type]


async def test_read_family_masks_are_rejected_at_every_intake() -> None:
    with pytest.raises(ValueError, match="read-family"):
        AsyncVirtualFileSystem(deny_ops={"read"})

    root = BindableStorage(name="root")
    fs = AsyncVirtualFileSystem(storage=root)
    # The private attach step is an intake of its own, beneath add_mount's.
    with pytest.raises(ValueError, match="read-family"):
        await fs._attach_mount(RecorderStorage(name="c1"), "/m", deny_ops={"ls"})
    assert {r.path for r in fs.mounts()} == {"/"}

    root.calls.clear()
    with pytest.raises(ValueError, match="read-family"):
        await fs.add_mount(RecorderStorage(name="c2"), "/m", deny_ops={"stat"})
    assert {r.path for r in fs.mounts()} == {"/"}
    assert all(op != "mkdir" for op, _ in root.calls)  # rejected before the site mkdir

    await fs.add_mount(RecorderStorage(name="c3"), "/m", deny_ops={"edit"})
    with pytest.raises(ValueError, match="read-family"):
        await fs.update_mount("/m", deny_ops={"grep"})
    assert {str(r.path): r for r in fs.mounts()}["/m"].deny_ops == frozenset({"edit"})


async def test_bare_string_deny_ops_is_rejected_not_char_splattered() -> None:
    # frozenset("run") would silently store {'r','u','n'} — an inert mask
    # that fails open and can even clear a working one via update_mount.
    with pytest.raises(TypeError, match="bare string"):
        AsyncVirtualFileSystem(deny_ops="read")  # ty: ignore[invalid-argument-type]

    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    # The private attach step is an intake of its own, beneath add_mount's.
    with pytest.raises(TypeError, match="bare string"):
        await fs._attach_mount(RecorderStorage(name="c1"), "/m", deny_ops="run")  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError, match="bare string"):
        await fs.add_mount(RecorderStorage(name="c2"), "/m", deny_ops="run")  # ty: ignore[invalid-argument-type]

    await fs.add_mount(RecorderStorage(name="c3"), "/m", deny_ops={"run"})
    with pytest.raises(TypeError, match="bare string"):
        await fs.update_mount("/m", deny_ops="edit")  # ty: ignore[invalid-argument-type]
    assert {str(r.path): r for r in fs.mounts()}["/m"].deny_ops == frozenset({"run"})  # the working mask survived


async def test_read_family_mask_with_refresh_never_resnapshots() -> None:
    child = CapCountingStorage(name="child")
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(child, "/m")
    before_caps = {str(r.path): r for r in fs.mounts()}["/m"].caps
    count = child.capabilities_calls
    with pytest.raises(ValueError, match="read-family"):
        await fs.update_mount("/m", deny_ops={"read"}, refresh_caps=True)
    assert child.capabilities_calls == count
    assert {str(r.path): r for r in fs.mounts()}["/m"].caps == before_caps


async def test_parent_mkdir_mask_refuses_add_mount() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage(), deny_ops={"mkdir"})
    with pytest.raises(MountError):
        await fs.add_mount(RecorderStorage(name="c1"), "/m")
    assert {r.path for r in fs.mounts()} == {"/"}


async def test_inert_mask_is_stored_and_bites_after_refresh() -> None:
    narrow: frozenset[Op] = frozenset({"read", "stat", "ls"})
    child = BindableStorage(name="child", caps=narrow)
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(child, "/m", deny_ops={"run"})

    row = {str(r.path): r for r in fs.mounts()}["/m"]
    assert row.caps == narrow  # inert: caps unchanged
    assert row.deny_ops == frozenset({"run"})  # but the mask is still echoed

    wider: frozenset[Op] = frozenset({"read", "stat", "ls", "run"})
    child._caps = wider
    await fs.update_mount("/m", refresh_caps=True)
    row = {str(r.path): r for r in fs.mounts()}["/m"]
    assert "run" not in row.caps  # the stored mask started biting


async def test_constructor_deny_ops_masks_the_root_entry() -> None:
    fs = AsyncVirtualFileSystem(storage=RecorderStorage(), deny_ops={"write"})
    denied = await fs.write(path="/f.md", content="x")
    assert not denied.success
    assert denied.errors[0].kind is ErrorKind.unsupported
    row = fs.mounts()[0]
    assert row.deny_ops == frozenset({"write"})
    assert "write" not in row.caps


async def test_mask_replace_and_clear_recompute_without_storage_io() -> None:
    child = CapCountingStorage(name="child")
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(child, "/m", deny_ops={"edit"})
    declared = child.capabilities()
    count = child.capabilities_calls

    await fs.update_mount("/m", deny_ops={"run"})
    row = {str(r.path): r for r in fs.mounts()}["/m"]
    assert "edit" in row.caps  # restored from the stored snapshot
    assert "run" not in row.caps
    await fs.update_mount("/m", deny_ops=())
    assert {str(r.path): r for r in fs.mounts()}["/m"].caps == declared
    assert child.capabilities_calls == count  # neither call re-snapshotted


# ----------------------------------------------------------------------
# locate() / locate_edge() — the table answers where a path lives
# ----------------------------------------------------------------------


async def test_locate_reports_the_root_mount_for_an_unmounted_path() -> None:
    fs = AsyncVirtualFileSystem()
    row = await fs.locate("/docs/guide.md")
    assert row == Location(
        path="/docs/guide.md",
        mount="/",
        storage_name=fs.mounts()[0].storage.name,
        storage_type="InMemoryStorage",
        storage_path="/docs/guide.md",
    )
    assert (row.exists, row.kind, row.note) == (None, None, None)
    assert json.loads(json.dumps(row._asdict()))["mount"] == "/"


async def test_locate_reports_the_deepest_mount_and_the_storage_local_path() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    outer, inner = BindableStorage(name="outer"), RecorderStorage(name="inner")
    await fs.add_mount(outer, "/vendor")
    await fs.add_mount(inner, "/vendor/lib")
    recorded = list(outer.calls)
    assert (await fs.locate("/vendor/lib/x.md"))[:5] == (
        "/vendor/lib/x.md",
        "/vendor/lib",
        "inner",
        "RecorderStorage",
        "/x.md",
    )
    assert (await fs.locate("/vendor/x.md"))[:5] == ("/vendor/x.md", "/vendor", "outer", "BindableStorage", "/x.md")
    assert (await fs.locate("/vendor/lib"))[:5] == ("/vendor/lib", "/vendor/lib", "inner", "RecorderStorage", "/")
    assert (await fs.locate("/vendor/../other/./y.md")).path == "/other/y.md"
    assert outer.calls == recorded and inner.calls == []  # the table answered; no storage was asked
    await fs.close()


async def test_locate_edge_agrees_with_mkedge_on_the_boundary() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    a, b = RecorderStorage(name="a"), RecorderStorage(name="b")
    await fs.add_mount(a, "/a")
    await fs.add_mount(b, "/b")
    split = await fs.locate_edge("/a/x.md", "/b/y.md")
    assert split.same_storage is False
    assert (split.source.mount, split.target.mount) == ("/a", "/b")
    assert split.reason == "an edge cannot cross a mount boundary; the source lives on /a and the target on /b"
    refused = await fs.mkedge(source="/a/x.md", target="/b/y.md", edge_type="links")
    assert refused.errors[0].kind is ErrorKind.cross_mount
    together = await fs.locate_edge("/a/x.md", "/a/deep/y.md")
    assert together.same_storage is True and together.reason is None
    assert together.target.storage_path == "/deep/y.md"
    assert (await fs.mkedge(source="/a/x.md", target="/a/deep/y.md", edge_type="links")).success is True
    assert json.loads(json.dumps(split._asdict()))["source"] == list(split.source)
    # A storage that answers a stat with no row is "not there", like a not_found.
    assert (await fs.locate("/a/x.md", exists=True)).exists is False
    await fs.close()


async def test_locate_with_exists_asks_the_owning_storage_directly() -> None:
    fs = AsyncVirtualFileSystem()
    assert (await fs.write(path="/docs/guide.md", content="hi", parents=True)).success is True
    present = await fs.locate("/docs/guide.md", exists=True)
    assert (present.exists, present.kind, present.note) == (True, "file", None)
    parent = await fs.locate("/docs", exists=True)
    assert (parent.exists, parent.kind) == (True, "directory")
    absent = await fs.locate("/docs/missing.md", exists=True)
    assert (absent.exists, absent.kind, absent.note) == (False, None, None)
    edge = await fs.locate_edge("/docs/guide.md", "/docs/missing.md", exists=True)
    assert edge.same_storage is True and edge.reason == "the target does not exist: /docs/missing.md"
    edge = await fs.locate_edge("/docs/missing.md", "/docs/guide.md", exists=True)
    assert edge.reason == "the source does not exist: /docs/missing.md"
    await fs.close()


class _DeadStorage(RecorderStorage):
    """A storage whose every answer is a transport failure."""

    def _answer(self, op: str, kwargs: dict[str, Any], authority: Authority | None = None) -> Result:
        self.calls.append((op, kwargs))
        self.authorities.append(authority)
        return Result(ops=(op,), errors=[ResultError(kind=ErrorKind.backend_unavailable, message="connection refused")])


async def test_locate_with_exists_reports_a_storage_that_cannot_answer() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(_DeadStorage(name="dead"), "/remote")
    row = await fs.locate("/remote/x.md", exists=True)
    assert (row.exists, row.kind, row.note) == (None, None, "connection refused")
    edge = await fs.locate_edge("/remote/x.md", "/remote/y.md", exists=True)
    assert edge.same_storage is True and edge.reason is None
    await fs.close()


async def test_locate_raises_where_no_row_can_answer() -> None:
    fs = AsyncVirtualFileSystem()
    with pytest.raises(ValueError, match="null"):
        await fs.locate("/bad\x00name.md")
    with pytest.raises(ValueError, match="null"):
        await fs.locate_edge("/ok.md", "/bad\x00name.md")
    await fs.close()
    with pytest.raises(ValueError, match="closed"):
        await fs.locate("/anything.md")


async def test_unmount_and_remount_pass_under_a_rule_beneath_the_site() -> None:
    store = InMemoryStorage()
    fs = AsyncVirtualFileSystem(storage=store, permissions=read_write(read=["/data/archive", "/d2/x"]))
    await fs.add_mount(InMemoryStorage(), "/data")
    await fs.remove_mount("/data")
    await fs.add_mount(InMemoryStorage(), "/data")
    plain = AsyncVirtualFileSystem(storage=store)
    assert (await plain.mkdir("/d2")).success is True
    assert (await plain.delete("/d2", cascade=False)).success is True
    restored = await fs.restore("/d2")
    assert restored.success is True
