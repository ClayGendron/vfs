"""Mount table lifecycle: bind/unbind primitives, add/remove sugar, close,
the busy guard, shadow filtering, decoration, and terminal resolution."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from tests.support.base_doubles import (
    BadCloseStorage,
    BindableStorage,
    CannedStorage,
    DictStorage,
    GatedCloseStorage,
    ReadFamilyStorage,
    RecorderStorage,
    ScopeSpyStorage,
    SpyCloseStorage,
    TransportFailStorage,
)
from vfs.base import Binding, MountMeta, VirtualFileSystem
from vfs.exceptions import MountError
from vfs.models import Entry, Observation
from vfs.paths import Path
from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.storage.backends.memory import InMemoryStorage

# ----------------------------------------------------------------------
# file-local doubles
# ----------------------------------------------------------------------


class GhostStorage(BindableStorage):
    """Answers the bind-site probe honestly (empty directory at *mount_path*)
    but a general ``ls``/``tree`` also leaks a phantom row beneath the site —
    isolates shadow filtering as the guard, not the probe."""

    def __init__(self, *, mount_path: str, ghost_path: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._mount = Path(mount_path)
        self._ghost = Observation(path=Path(ghost_path), kind="file")

    async def ls(self, *, path: Path | None = None, user_id: str | None = None, **kwargs: Any) -> Result:
        self.calls.append(("ls", {"path": path, **kwargs}))
        if path == self._mount:
            return Result(ops=("ls",), observations=[])
        rows = [Observation(path=self._mount, kind="directory"), self._ghost]
        return Result(ops=("ls",), observations=rows)

    async def tree(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        self.calls.append(("tree", kwargs))
        rows = [Observation(path=self._mount, kind="directory"), self._ghost]
        return Result(ops=("tree",), observations=rows)


# ----------------------------------------------------------------------
# __init__
# ----------------------------------------------------------------------


def test_init_defaults_to_inmemory_storage_and_root_binding() -> None:
    fs = VirtualFileSystem()
    assert isinstance(fs._bindings[Path("/")].storage, InMemoryStorage)
    assert fs._sorted_mount_paths == [Path("/")]
    assert fs.name is None
    assert fs.title is None
    assert fs.description is None


def test_init_holds_the_given_backend() -> None:
    backend = RecorderStorage()
    fs = VirtualFileSystem(name="root", storage=backend)
    assert fs.name == "root"
    assert fs._bindings[Path("/")].storage is backend


def test_init_rejects_backend_missing_the_read_family() -> None:
    class StatOnly:
        async def stat(self, **kwargs: Any) -> Result:
            return Result(ops=("stat",), observations=[])

    with pytest.raises(TypeError, match="read family"):
        VirtualFileSystem(storage=StatOnly())  # ty: ignore[invalid-argument-type]


def test_init_root_permissions_and_no_overlay_wire_into_root_meta() -> None:
    fs = VirtualFileSystem(permissions="read", no_overlay=True)
    meta = fs._bindings[Path("/")].meta
    assert meta.permission_map is not None
    assert meta.permission_map.default == "read"
    assert meta.no_overlay is True
    assert meta.owned is True


def test_init_root_capability_snapshot_matches_backend() -> None:
    fs = VirtualFileSystem(storage=ReadFamilyStorage())
    assert fs._bindings[Path("/")].meta.caps == frozenset({"read", "stat", "ls", "tree"})


# ----------------------------------------------------------------------
# _normalize_mount_path
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("data", "/data"), ("/data", "/data"), ("/data/", "/data"), ("data/archive", "/data/archive")],
)
def test_normalize_mount_path_valid(raw: str, expected: str) -> None:
    assert VirtualFileSystem._normalize_mount_path(raw) == expected


@pytest.mark.parametrize("raw", ["", "/", "//"])
def test_normalize_mount_path_rejects_empty_or_root(raw: str) -> None:
    with pytest.raises(ValueError):
        VirtualFileSystem._normalize_mount_path(raw)


@pytest.mark.parametrize("raw", [".vfs", "/.vfs", "/.vfs/"])
def test_normalize_mount_path_rejects_reserved_metadata_root(raw: str) -> None:
    with pytest.raises(ValueError, match="reserved"):
        VirtualFileSystem._normalize_mount_path(raw)


@pytest.mark.parametrize("raw", [" /data", "/data/ ", "/x /y"])
def test_normalize_mount_path_canonicalizes_stray_whitespace(raw: str) -> None:
    # Leading/trailing per-segment whitespace is canonicalized, not rejected.
    VirtualFileSystem._normalize_mount_path(raw)


# ----------------------------------------------------------------------
# bind — the primitive
# ----------------------------------------------------------------------


async def test_bind_succeeds_onto_an_existing_empty_directory() -> None:
    root = VirtualFileSystem(storage=BindableStorage())
    child = RecorderStorage()
    await root.bind(child, "/data")
    assert root._bindings[Path("/data")].storage is child


async def test_add_mount_mkdir_failure_raises_mount_error_with_evidence() -> None:
    # The prose stays a ValueError match for string-matching callers; the
    # structured ResultError list rides on the typed exception.
    root = VirtualFileSystem(storage=InMemoryStorage())
    await root.write(entries=[Entry(path="/site", content="x")])
    with pytest.raises(MountError, match="Cannot mount at /site") as exc:
        await root.add_mount(InMemoryStorage(), "/site")
    assert isinstance(exc.value, ValueError)
    assert exc.value.errors[0].kind is VFSErrorKind.exists


async def test_remove_mount_rmdir_failure_raises_mount_error_with_evidence() -> None:
    backend = InMemoryStorage()
    root = VirtualFileSystem(storage=backend)
    await root.add_mount(InMemoryStorage(name="child"), "/m")
    await backend.write(entries=[Entry(path=Path("/m/foreign.txt"), content="secret")])  # bypasses the router
    with pytest.raises(MountError, match="removing its directory failed") as exc:
        await root.remove_mount("/m")
    assert exc.value.errors[0].kind is VFSErrorKind.not_empty


async def test_bind_beneath_a_dead_backend_reports_the_transport_failure() -> None:
    # The probe dispatches on the error kind: a dead backend surfaces its
    # transport failure — never the mkdir advice, which cannot help.
    root = VirtualFileSystem()
    await root.add_mount(TransportFailStorage(), "/dead")
    with pytest.raises(ValueError, match="unavailable") as exc:
        await root.bind(InMemoryStorage(), "/dead/sub")
    assert "mkdir" not in str(exc.value)


async def test_bind_racing_close_refuses_cleanly() -> None:
    # close() may empty the table while the site probe's storage I/O is
    # suspended; bind must refuse as "closed", never escape a KeyError.
    class GateStatStorage(BindableStorage):
        def __init__(self) -> None:
            super().__init__()
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def stat(self, **kwargs: Any) -> Result:
            self.entered.set()
            await self.release.wait()
            return await super().stat(**kwargs)

    backend = GateStatStorage()
    root = VirtualFileSystem(storage=backend)
    bind_task = asyncio.create_task(root.bind(InMemoryStorage(), "/site"))
    await backend.entered.wait()
    await root.close()
    backend.release.set()
    with pytest.raises(ValueError, match="closed"):
        await bind_task


async def test_bind_rejects_non_storage_backend() -> None:
    root = VirtualFileSystem()
    with pytest.raises(TypeError, match="read family"):
        await root.bind(object(), "/x")  # ty: ignore[invalid-argument-type]


async def test_bind_rejects_missing_site() -> None:
    root = VirtualFileSystem()
    with pytest.raises(ValueError, match="no directory stored"):
        await root.bind(RecorderStorage(), "/nope")


async def test_bind_rejects_a_file_at_the_site() -> None:
    root = VirtualFileSystem(storage=DictStorage({"/f": "file"}))
    with pytest.raises(ValueError, match="stored as 'file'"):
        await root.bind(RecorderStorage(), "/f")


async def test_bind_rejects_a_non_empty_directory() -> None:
    root = VirtualFileSystem(storage=DictStorage({"/data": "directory", "/data/kept.txt": "file"}))
    with pytest.raises(ValueError, match="not empty"):
        await root.bind(RecorderStorage(), "/data")


async def test_bind_rejects_duplicate_path() -> None:
    root = VirtualFileSystem(storage=BindableStorage())
    await root.bind(BindableStorage(), "/data")
    with pytest.raises(ValueError, match="already exists"):
        await root.bind(RecorderStorage(), "/data")


async def test_bind_rejects_shallower_when_deeper_already_bound() -> None:
    root = VirtualFileSystem(storage=BindableStorage())
    await root.bind(BindableStorage(), "/a/b")
    with pytest.raises(ValueError, match="deeper mount already sits"):
        await root.bind(RecorderStorage(), "/a")


async def test_bind_rejects_the_same_storage_object_twice() -> None:
    root = VirtualFileSystem(storage=BindableStorage())
    shared = BindableStorage()
    await root.bind(shared, "/a")
    with pytest.raises(ValueError, match="already bound"):
        await root.bind(shared, "/b")
    assert set(root._bindings) == {Path("/"), Path("/a")}


async def test_root_no_overlay_refuses_every_bind() -> None:
    root = VirtualFileSystem(storage=BindableStorage(), no_overlay=True)
    with pytest.raises(ValueError, match="does not allow child mounts"):
        await root.bind(RecorderStorage(), "/m")


async def test_per_entry_no_overlay_refuses_binds_beneath_it() -> None:
    root = VirtualFileSystem(storage=BindableStorage())
    await root.bind(BindableStorage(), "/locked", no_overlay=True)
    with pytest.raises(ValueError, match="does not allow binds beneath"):
        await root.bind(RecorderStorage(), "/locked/inner")


# ----------------------------------------------------------------------
# unbind
# ----------------------------------------------------------------------


async def test_unbind_is_pure_table_surgery() -> None:
    root = VirtualFileSystem(storage=BindableStorage())
    child = RecorderStorage()
    await root.bind(child, "/data")
    removed = await root.unbind("/data")
    assert removed.storage is child
    assert Path("/data") not in root._bindings
    assert child.calls == []  # no storage I/O on unbind


async def test_unbind_rejects_missing() -> None:
    root = VirtualFileSystem()
    with pytest.raises(ValueError, match="No mount at"):
        await root.unbind("/nope")


async def test_unbind_refuses_while_deeper_bindings_exist() -> None:
    root = VirtualFileSystem(storage=BindableStorage())
    await root.bind(BindableStorage(), "/a")
    await root.bind(RecorderStorage(), "/a/b")
    with pytest.raises(ValueError, match="deeper mounts exist"):
        await root.unbind("/a")
    assert Path("/a") in root._bindings


# ----------------------------------------------------------------------
# add_mount — mkdir-if-absent + bind, fused
# ----------------------------------------------------------------------


async def test_add_mount_path_defaults_to_storage_name() -> None:
    root = VirtualFileSystem()
    await root.add_mount(InMemoryStorage(name="data"))
    assert Path("/data") in root._bindings


async def test_add_mount_requires_path_or_named_storage() -> None:
    root = VirtualFileSystem()
    with pytest.raises(ValueError, match="path or a named storage"):
        await root.add_mount(RecorderStorage(name=""))


async def test_add_mount_creates_missing_parents_when_asked() -> None:
    root = VirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/a/b/c", parents=True)
    assert Path("/a/b/c") in root._bindings


async def test_add_mount_without_parents_raises_on_missing_ancestor() -> None:
    root = VirtualFileSystem()
    with pytest.raises(ValueError):
        await root.add_mount(RecorderStorage(), "/a/b/c")
    assert Path("/a/b/c") not in root._bindings


async def test_add_mount_onto_preexisting_empty_dir_succeeds() -> None:
    root = VirtualFileSystem()
    await root.mkdir("/data")
    await root.add_mount(RecorderStorage(), "/data")
    assert Path("/data") in root._bindings


async def test_add_mount_after_restart_rebinds_onto_existing_empty_dir() -> None:
    # A fresh router over the same persistent backend can re-mount at the
    # same site: mkdir(exist_ok=True) + an empty-directory bind, not a
    # fused create that would fail every process restart.
    backend = InMemoryStorage()
    first = VirtualFileSystem(storage=backend)
    await first.add_mount(InMemoryStorage(name="child"), "/data")
    second = VirtualFileSystem(storage=backend)
    await second.add_mount(InMemoryStorage(name="child2"), "/data")
    assert Path("/data") in second._bindings


async def test_add_mount_failed_bind_leaves_the_directory() -> None:
    # No rollback: a plain empty directory is a valid future mount site.
    root = VirtualFileSystem()
    shared = RecorderStorage()
    await root.add_mount(shared, "/first")
    with pytest.raises(ValueError, match="already bound"):
        await root.add_mount(shared, "/second")  # aliasing fails the bind half
    stat = await root.stat("/second")
    assert stat.success is True
    assert stat.one().kind == "directory"


async def test_add_remove_readd_mount_cycle_is_clean() -> None:
    root = VirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/data")
    await root.remove_mount("/data")
    assert Path("/data") not in root._bindings
    await root.add_mount(RecorderStorage(), "/data")
    assert Path("/data") in root._bindings


# ----------------------------------------------------------------------
# remove_mount — unbind + strict rmdir, fused
# ----------------------------------------------------------------------


async def test_remove_mount_unbinds_and_rmdirs() -> None:
    root = VirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/data")
    await root.remove_mount("/data")
    assert Path("/data") not in root._bindings
    stat = await root.stat("/data")
    assert stat.success is False
    assert stat.errors[0].kind is VFSErrorKind.not_found


async def test_remove_mount_parks_the_directory_in_trash_restorable() -> None:
    # Unmount never destroys: the empty mount directory is an ordinary
    # trash row, and restore brings it back as a plain directory.
    root = VirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/data")
    await root.remove_mount("/data")
    assert (await root.stat("/data")).success is False
    restored = await root.restore("/data")
    assert restored.success is True
    assert (await root.stat("/data")).one().kind == "directory"


async def test_a_sweep_reclaims_the_trashed_mount_directory() -> None:
    root = VirtualFileSystem(storage=InMemoryStorage(trash_days=0))
    await root.add_mount(RecorderStorage(), "/data")
    await root.remove_mount("/data")
    buckets = (await root.ls("/.vfs/trash")).observations
    assert len(buckets) == 1
    bucket = str(buckets[0].path)
    rows = (await root.ls(bucket)).observations
    assert any(str(o.path).endswith("-data") for o in rows)
    # Even at trash_days=0 the current hour has not fully aged, so the
    # retention sweep keeps the bucket; the bucket-address arm reclaims it.
    retained = await root.sweep()
    if bucket != f"/.vfs/trash/{datetime.now(UTC).strftime('%Y-%m-%d-%H')}":
        pytest.skip("hour boundary crossed between unmount and sweep")
    assert retained.success is True
    assert retained.observations == []
    reclaimed = await root.sweep(bucket)
    assert reclaimed.success is True
    assert (await root.stat(bucket)).success is False


async def test_remove_mount_rejects_missing() -> None:
    root = VirtualFileSystem()
    with pytest.raises(ValueError, match="No mount at"):
        await root.remove_mount("/nope")


async def test_remove_mount_refuses_while_deeper_mounts_exist() -> None:
    root = VirtualFileSystem()
    await root.add_mount(BindableStorage(), "/a", parents=True)
    await root.add_mount(RecorderStorage(), "/a/b", parents=True)
    with pytest.raises(ValueError, match="deeper mounts exist"):
        await root.remove_mount("/a")
    assert Path("/a") in root._bindings


async def test_remove_mount_of_a_non_empty_directory_fails_loud_and_leaves_it() -> None:
    backend = InMemoryStorage()
    root = VirtualFileSystem(storage=backend)
    await root.add_mount(InMemoryStorage(name="child"), "/m")
    await backend.write(entries=[Entry(path=Path("/m/foreign.txt"), content="secret")])  # bypasses the router entirely
    with pytest.raises(ValueError, match="removing its directory failed"):
        await root.remove_mount("/m")
    assert Path("/m") not in root._bindings  # the unbind half stands
    stat = await backend.stat(path=Path("/m"))
    assert stat.success is True
    assert stat.one().kind == "directory"
    foreign = await backend.stat(path=Path("/m/foreign.txt"))
    assert foreign.success is True  # the foreign row survives untouched


# ----------------------------------------------------------------------
# close — snapshot-and-clear under the lock, dispose outside it
# ----------------------------------------------------------------------


async def test_close_disposes_owned_backends_and_clears_the_table() -> None:
    root = VirtualFileSystem()
    a, b = SpyCloseStorage(), SpyCloseStorage()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    await root.close()
    assert a.close_count == 1
    assert b.close_count == 1
    assert root._bindings == {}
    assert root._sorted_mount_paths == []


async def test_close_disposes_the_root_backend_too() -> None:
    backend = SpyCloseStorage()
    root = VirtualFileSystem(storage=backend)
    await root.close()
    assert backend.close_count == 1


async def test_close_never_disposes_an_unowned_backend() -> None:
    owned, shared = SpyCloseStorage(), SpyCloseStorage()
    root = VirtualFileSystem()
    await root.add_mount(owned, "/owned", owned=True)
    await root.add_mount(shared, "/shared", owned=False)
    await root.close()
    assert owned.close_count == 1
    assert shared.close_count == 0


async def test_close_dedupes_the_same_storage_bound_twice_via_direct_table_edit() -> None:
    # bind() forbids aliasing; reach the malformed shape directly to prove
    # close()'s identity-dedup holds even then.
    shared = SpyCloseStorage()
    root = VirtualFileSystem(storage=shared)
    root._bindings[Path("/x")] = Binding(
        path=Path("/x"), storage=shared, meta=MountMeta(declared_caps=shared.capabilities())
    )
    root._sorted_mount_paths = sorted(root._bindings, reverse=True)
    await root.close()
    assert shared.close_count == 1


async def test_close_collects_a_single_failure_and_raises_it_directly() -> None:
    root = VirtualFileSystem()
    good = SpyCloseStorage()
    await root.add_mount(BadCloseStorage(), "/bad")
    await root.add_mount(good, "/good")
    with pytest.raises(RuntimeError, match="boom"):
        await root.close()
    assert good.close_count == 1  # the sibling was not stranded
    assert root._bindings == {}


async def test_close_groups_multiple_failures() -> None:
    root = VirtualFileSystem()
    await root.add_mount(BadCloseStorage(), "/a")
    await root.add_mount(BadCloseStorage(), "/b")
    with pytest.raises(ExceptionGroup):
        await root.close()
    assert root._bindings == {}


async def test_close_disposes_concurrently_not_sequentially() -> None:
    # Two never-releasing backends under a short timeout: sequential
    # disposal would take ~2x the timeout; concurrent gather takes ~1x.
    gate = asyncio.Event()  # never set within the test
    root = VirtualFileSystem(close_timeout=0.05)
    await root.add_mount(GatedCloseStorage(gate), "/a")
    await root.add_mount(GatedCloseStorage(gate), "/b")
    loop = asyncio.get_event_loop()
    start = loop.time()
    with pytest.raises(ExceptionGroup):
        await root.close()
    assert loop.time() - start < 0.15


async def test_close_cancellation_parks_disposal_for_a_retry() -> None:
    gate = asyncio.Event()
    storage = GatedCloseStorage(gate)
    root = VirtualFileSystem()
    await root.add_mount(storage, "/a")
    task = asyncio.ensure_future(root.close())
    await asyncio.sleep(0)  # let close() snapshot-clear and reach the gate
    assert root._bindings == {}
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert root._bindings == {}
    assert storage.close_count == 0  # disposal parked, not lost
    gate.set()
    await root.close()  # the retry drains the parked snapshot
    assert storage.close_count == 1


@pytest.mark.parametrize(
    "call",
    [
        lambda fs: fs.read("/f.txt"),
        lambda fs: fs.ls("/"),
        lambda fs: fs.write(entries=[Entry(path="/f.txt", content="x")]),
        lambda fs: fs.glob("*.py"),
        lambda fs: fs.mkedge("/a.py", "/b.py", "imports"),
        lambda fs: fs.move(src="/a", dest="/b"),
    ],
)
async def test_closed_router_answers_backend_unavailable_for_every_verb(call: Any) -> None:
    root = VirtualFileSystem()
    await root.close()
    result = await call(root)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.backend_unavailable
    assert result.errors[0].message == "Filesystem is closed"


# ----------------------------------------------------------------------
# the busy guard — EBUSY on a live bind site
# ----------------------------------------------------------------------


async def test_busy_guard_blocks_delete_at_a_bind_path() -> None:
    root = VirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/m", parents=True)
    result = await root.delete("/m")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.busy


async def test_busy_guard_blocks_delete_of_a_region_containing_a_bind() -> None:
    root = VirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/a/m", parents=True)
    result = await root.delete("/a", cascade=True)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.busy


async def test_busy_guard_blocks_move_dest_onto_a_bind_path() -> None:
    root = VirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/m", parents=True)
    result = await root.move(src="/x.txt", dest="/m")
    assert result.errors[0].kind is VFSErrorKind.busy


async def test_busy_guard_blocks_move_src_subtree_containing_a_bind() -> None:
    root = VirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/a/m", parents=True)
    result = await root.move(src="/a", dest="/b")
    assert result.errors[0].kind is VFSErrorKind.busy


async def test_busy_guard_blocks_copy_onto_a_bind_path() -> None:
    root = VirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/m", parents=True)
    result = await root.copy(src="/x.txt", dest="/m")
    assert result.errors[0].kind is VFSErrorKind.busy


async def test_copy_from_a_subtree_containing_a_bind_is_not_busy() -> None:
    # copy only busy-gates the destination region — the source side is fine.
    root = VirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/a/m", parents=True)
    result = await root.copy(src="/a", dest="/b")
    assert result.success is True


# ----------------------------------------------------------------------
# shadow filtering — a deeper bind fully shadows the shallower storage
# ----------------------------------------------------------------------


async def test_shadow_filter_drops_ls_rows_beneath_a_deeper_bind() -> None:
    ghost = GhostStorage(mount_path="/a", ghost_path="/a/ghost.txt")
    root = VirtualFileSystem(storage=ghost)
    await root.bind(RecorderStorage(), "/a")
    result = await root.ls("/")
    assert "/a/ghost.txt" not in result.paths
    assert "/a" in result.paths  # the bind row itself survives, decorated


async def test_shadow_filter_drops_tree_rows_beneath_a_deeper_bind() -> None:
    ghost = GhostStorage(mount_path="/a", ghost_path="/a/deep/ghost.txt")
    root = VirtualFileSystem(storage=ghost)
    await root.bind(RecorderStorage(), "/a")
    result = await root.tree("/")
    assert "/a/deep/ghost.txt" not in result.paths
    assert "/a" in result.paths


# ----------------------------------------------------------------------
# capabilities — union of entry snapshots, taken at bind
# ----------------------------------------------------------------------


def test_capabilities_reflects_backend_declared_set() -> None:
    root = VirtualFileSystem(storage=ReadFamilyStorage())
    assert root.capabilities() == frozenset({"read", "stat", "ls", "tree"})


async def test_capabilities_is_the_union_across_bound_entries() -> None:
    root = VirtualFileSystem()
    narrow = RecorderStorage(caps=frozenset({"read", "stat", "ls", "tree", "run"}))
    await root.add_mount(narrow, "/tools", parents=True)
    assert "run" in root.capabilities()


async def test_capability_snapshot_is_taken_at_bind_not_live() -> None:
    storage = RecorderStorage(caps=frozenset({"read", "stat", "ls", "tree"}))
    root = VirtualFileSystem()
    await root.add_mount(storage, "/m", parents=True)
    storage._caps = frozenset({"read", "stat", "ls", "tree", "run"})  # backend grows live
    assert "run" not in root.capabilities()  # router still sees the bind-time snapshot


# ----------------------------------------------------------------------
# permission composition — most restrictive layer from / down wins
# ----------------------------------------------------------------------


async def test_readonly_root_makes_a_writable_mount_readonly() -> None:
    backend = InMemoryStorage()
    await backend.mkdir(path=Path("/scratch"))
    root = VirtualFileSystem(storage=backend, permissions="read")
    child = RecorderStorage()
    await root.bind(child, "/scratch", permissions="read_write")
    result = await root.write(entries=[Entry(path="/scratch/f.txt", content="x")])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.read_only
    assert child.calls == []


# ----------------------------------------------------------------------
# resolution — _match_mount / _resolve_terminal, one table, longest prefix
# ----------------------------------------------------------------------


async def test_match_mount_longest_prefix() -> None:
    root = VirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/a", parents=True)
    await root.add_mount(RecorderStorage(), "/ab", parents=True)
    long_match = root._match_mount(Path("/ab/x"))
    short_match = root._match_mount(Path("/a/x"))
    assert long_match is not None and long_match.path == "/ab"
    assert short_match is not None and short_match.path == "/a"


async def test_resolve_terminal_root_fallback() -> None:
    root = VirtualFileSystem()
    terminal = root._resolve_terminal(Path("/nope/file.txt"))
    assert terminal.binding.path == "/"
    assert terminal.rel == "/nope/file.txt"


async def test_resolve_terminal_at_bind_root() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/data", parents=True)
    terminal = root._resolve_terminal(Path("/data"))
    assert terminal.binding.storage is child
    assert terminal.rel == "/"


# ----------------------------------------------------------------------
# tree — depth budget across bound regions
# ----------------------------------------------------------------------


async def test_tree_budgets_depth_across_bound_regions() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/data/a", parents=True)

    depth1 = await root.tree("/", max_depth=1)
    assert set(depth1.paths) == {"/data"}
    assert child.calls == []

    depth2 = await root.tree("/", max_depth=2)
    assert set(depth2.paths) == {"/data", "/data/a"}
    assert child.calls == []

    await root.tree("/", max_depth=3)
    assert child.calls == [("tree", {"path": "/", "max_depth": 1, "columns": None})]

    child.calls.clear()
    await root.tree("/")
    assert child.calls == [("tree", {"path": "/", "max_depth": None, "columns": None})]


async def test_tree_skips_incapable_binding_with_info_record() -> None:
    root = VirtualFileSystem()
    capable = RecorderStorage()
    dim = RecorderStorage(caps=frozenset({"read", "stat", "ls"}))  # no "tree"
    await root.add_mount(capable, "/data/a", parents=True)
    await root.add_mount(dim, "/data/b", parents=True)
    result = await root.tree("/")
    assert result.success is True
    assert {"/data", "/data/a", "/data/b"} <= set(result.paths)
    assert dim.calls == []
    [skip] = result.errors
    assert skip.kind is VFSErrorKind.unsupported
    assert skip.severity is Severity.info
    assert skip.path == "/data/b"


async def test_tree_budgets_depth_from_a_non_root_target() -> None:
    root = VirtualFileSystem()
    child = RecorderStorage()
    await root.add_mount(child, "/data/a/b", parents=True)

    # The bind sits two segments beneath the target: depth 2 exhausts the
    # budget at the mount point, whose stored directory row still shows.
    depth2 = await root.tree("/data", max_depth=2)
    assert set(depth2.paths) == {"/data/a", "/data/a/b"}
    assert child.calls == []

    await root.tree("/data", max_depth=3)
    assert child.calls == [("tree", {"path": "/", "max_depth": 1, "columns": None})]


async def test_tree_dead_descent_demotes_beside_live_rows() -> None:
    root = VirtualFileSystem()
    await root.add_mount(TransportFailStorage(), "/data/dead", parents=True)
    result = await root.tree("/")
    assert result.success is True
    assert {"/data", "/data/dead"} <= set(result.paths)
    [warning] = result.errors
    assert warning.severity is Severity.warning
    assert warning.kind is VFSErrorKind.backend_unavailable


# ----------------------------------------------------------------------
# fan-out — a scope with binds beneath it expands into a region
# ----------------------------------------------------------------------


async def test_scoped_fanout_expands_into_bindings_beneath_the_scope() -> None:
    root = VirtualFileSystem(storage=DictStorage({"/data": "directory"}))
    inside = ScopeSpyStorage(echo_path="/inside.txt")
    await root.add_mount(inside, "/data/a")
    result = await root.grep("g", paths=("/data",))
    assert result.success is True
    assert result.paths == ("/data/a/inside.txt",)
    assert inside.scopes == [()]  # the covered binding runs unscoped


async def test_scope_at_exact_bind_path_dispatches_scoped_not_expanded() -> None:
    root = VirtualFileSystem()
    spy = ScopeSpyStorage()
    await root.add_mount(spy, "/data/a", parents=True)
    result = await root.grep("g", paths=("/data/a",))
    assert result.paths == ("/data/a/hit.md",)
    assert spy.scopes == [("/",)]  # scoped dispatch, not a region expansion


# ----------------------------------------------------------------------
# grouped-vs-single classification equivalence against stored directories
# ----------------------------------------------------------------------


async def test_grouped_and_single_delete_agree_on_a_stored_directory() -> None:
    # No synthesized spine rows anymore: a plain stored directory classifies
    # identically whichever input shape addresses it — storage truth, not a
    # router-side special case.
    root = VirtualFileSystem()
    await root.mkdir("/data/sub", parents=True)
    single = await root.delete("/data", cascade=False)
    grouped = await root.delete(observations=[Observation(path=Path("/data"))], cascade=False)
    assert single.success is False
    assert grouped.success is False
    assert single.errors[0].kind is grouped.errors[0].kind is VFSErrorKind.not_empty


# ----------------------------------------------------------------------
# probe and lifecycle edges — closed tables, odd stat answers, dead ls
# ----------------------------------------------------------------------


class _CancelledCloseStorage(RecorderStorage):
    """Owned storage whose disposal is cancelled mid-flight."""

    async def close(self) -> None:
        raise asyncio.CancelledError


async def test_bind_on_a_closed_filesystem_is_refused() -> None:
    fs = VirtualFileSystem()
    await fs.close()
    with pytest.raises(ValueError, match="filesystem is closed"):
        await fs.bind(RecorderStorage(), "/m")


async def test_match_mount_is_none_only_when_closed() -> None:
    fs = VirtualFileSystem()
    await fs.close()
    assert fs._match_mount(Path("/anything")) is None


async def test_bind_advises_mkdir_when_stat_answers_without_the_row() -> None:
    # A stat that succeeds but omits the site row reads as "nothing stored".
    root = VirtualFileSystem(storage=CannedStorage({"stat": Result(ops=("stat",), observations=[])}))
    with pytest.raises(ValueError, match="no directory stored"):
        await root.bind(RecorderStorage(), "/m")


async def test_bind_surfaces_a_failed_mount_point_listing() -> None:
    answers = {
        "stat": Result(ops=("stat",), observations=[Observation(path=Path("/m"), kind="directory")]),
        "ls": Result(ops=("ls",), errors=[ResultError(kind=VFSErrorKind.internal, message="listing broke")]),
    }
    root = VirtualFileSystem(storage=CannedStorage(answers))
    with pytest.raises(ValueError, match="listing broke"):
        await root.bind(RecorderStorage(), "/m")


async def test_close_reraises_cancellation_from_a_storage_close() -> None:
    fs = VirtualFileSystem()
    await fs.add_mount(_CancelledCloseStorage(), "/m")
    with pytest.raises(asyncio.CancelledError):
        await fs.close()
    assert fs._match_mount(Path("/m")) is None
