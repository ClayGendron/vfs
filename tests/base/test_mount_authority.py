"""Who may change a mount: the caller needs ``read_write`` at the mount point, and the storage that holds it says so."""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any

import pytest

from tests.support.base_doubles import BindableStorage, ReadFamilyStorage, RecorderStorage
from vfs import AsyncVirtualFileSystem, InMemoryStorage, VirtualFileSystem
from vfs.authority import Authority, Principal
from vfs.exceptions import MountError
from vfs.ops import GRANT_OPS
from vfs.results import ErrorKind, Result
from vfs.storage import TransportError

if TYPE_CHECKING:
    from vfs.ops import Op

SYSTEM = Authority.system()
ADA = Authority.of(Principal("ada"))
GRACE = Authority.of(Principal("grace"))

MOUNT_METHODS = ("add_mount", "remove_mount", "update_mount")


async def closed() -> AsyncVirtualFileSystem:
    """A file system whose posture gives nobody anything, so only a grant or the system actor passes."""
    fs = AsyncVirtualFileSystem()
    assert (await fs.set_posture("/", "none", authority=SYSTEM)).success is True
    return fs


def paths(fs: AsyncVirtualFileSystem) -> list[str]:
    return [str(mount.path) for mount in fs.mounts()]


@pytest.mark.parametrize("face", [AsyncVirtualFileSystem, VirtualFileSystem])
@pytest.mark.parametrize("method", MOUNT_METHODS)
def test_every_mount_method_takes_an_authority(face: type, method: str) -> None:
    authority = inspect.signature(getattr(face, method)).parameters["authority"]
    assert (authority.kind, authority.default) == (inspect.Parameter.KEYWORD_ONLY, None)


async def test_on_an_open_file_system_a_mount_change_needs_no_name() -> None:
    # A fresh file system gives everyone read_write, so a call that names nobody still passes.
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(InMemoryStorage(), "/data")
    await fs.update_mount("/data", no_overlay=True)
    assert (await fs.remove_mount("/data")).no_overlay is True
    assert paths(fs) == ["/"]


async def test_a_closed_posture_refuses_a_mount_change_that_names_nobody() -> None:
    fs = await closed()
    with pytest.raises(MountError, match="Cannot mount at /data") as exc:
        await fs.add_mount(InMemoryStorage(), "/data")
    assert exc.value.errors[0].kind is ErrorKind.unauthenticated
    assert paths(fs) == ["/"]
    # Refused before anything changed: no directory was made for the mount.
    assert (await fs.stat("/data", authority=SYSTEM)).errors[0].kind is ErrorKind.not_found

    with pytest.raises(MountError, match="Cannot update the mount at /") as exc:
        await fs.update_mount("/", permissions="read")
    assert exc.value.errors[0].kind is ErrorKind.unauthenticated
    assert (await fs.write(path="/a.txt", content="x", authority=SYSTEM)).success is True  # the root is not read-only


async def test_a_caller_needs_read_write_at_the_mount_point() -> None:
    fs = await closed()
    # The directory is there already, so what is tested is the level and not who may make it.
    assert (await fs.mkdir("/data", authority=SYSTEM)).success is True
    assert (await fs.grant("/data", "ada", "contribute", authority=SYSTEM)).success is True
    with pytest.raises(MountError, match="Cannot mount at /data") as exc:
        await fs.add_mount(InMemoryStorage(), "/data", authority=ADA)
    assert exc.value.errors[0].kind is ErrorKind.permission_denied
    assert str(exc.value.errors[0].path) == "/data"
    assert paths(fs) == ["/"]

    assert (await fs.grant("/data", "ada", "read_write", authority=SYSTEM)).success is True
    child = InMemoryStorage()
    await fs.add_mount(child, "/data", authority=ADA)
    assert fs.mounts()[1].storage is child

    # grace holds nothing at /data, so she is told no more than that the path is not there.
    with pytest.raises(MountError, match="Cannot update the mount at /data") as exc:
        await fs.update_mount("/data", no_overlay=True, authority=GRACE)
    assert exc.value.errors[0].kind is ErrorKind.not_found
    with pytest.raises(MountError, match="Cannot unmount /data") as exc:
        await fs.remove_mount("/data", authority=GRACE)
    assert exc.value.errors[0].kind is ErrorKind.not_found
    assert paths(fs) == ["/", "/data"]
    assert fs.mounts()[1].no_overlay is False

    await fs.update_mount("/data", no_overlay=True, authority=ADA)
    assert fs.mounts()[1].no_overlay is True
    assert (await fs.remove_mount("/data", authority=ADA)).storage is child


async def test_add_mount_makes_its_directories_as_the_caller_would() -> None:
    fs = await closed()
    assert (await fs.grant("/a/b/c", "ada", "read_write", authority=SYSTEM)).success is True
    # ada holds nothing above /a/b/c, so her own mkdir may not make /a, and her add_mount may not either.
    own = await fs.mkdir("/a/b/c", parents=True, authority=ADA)
    assert own.success is False
    with pytest.raises(MountError, match="Cannot mount at /a/b/c") as exc:
        await fs.add_mount(InMemoryStorage(), "/a/b/c", parents=True, authority=ADA)
    assert (exc.value.errors[0].kind, str(exc.value.errors[0].path)) == (own.errors[0].kind, str(own.errors[0].path))
    assert paths(fs) == ["/"]
    assert (await fs.stat("/a", authority=SYSTEM)).errors[0].kind is ErrorKind.not_found

    # Once the directories above exist and she may list them, her mkdir passes and so does her add_mount.
    assert (await fs.mkdir("/a/b", parents=True, authority=SYSTEM)).success is True
    assert (await fs.grant("/", "ada", "list", authority=SYSTEM)).success is True
    await fs.add_mount(InMemoryStorage(), "/a/b/c", authority=ADA)
    assert paths(fs) == ["/", "/a/b/c"]


async def test_update_mount_is_refused_where_removing_and_adding_the_mount_would_be() -> None:
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(InMemoryStorage(), "/data", deny_ops={"sweep"})
    await fs.update_mount("/", permissions="read")
    # The root is read-only at /data, so the mount there can be neither removed nor added, nor changed in place.
    with pytest.raises(MountError, match="Cannot update the mount at /data") as exc:
        await fs.update_mount("/data", deny_ops=())
    assert exc.value.errors[0].kind is ErrorKind.read_only
    assert fs.mounts()[1].deny_ops == frozenset({"sweep"})
    # The root mount has no mount above it, so its own policy can always be changed back.
    await fs.update_mount("/", permissions="read_write")
    await fs.update_mount("/data", deny_ops=())
    assert fs.mounts()[1].deny_ops == frozenset()


@pytest.mark.parametrize("masked", ["delete", "mkdir"])
async def test_update_mount_needs_a_storage_above_that_can_make_and_delete_a_directory(masked: Op) -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage(name="root"))
    await fs.add_mount(RecorderStorage(name="child"), "/m")
    await fs.update_mount("/", deny_ops={masked})
    with pytest.raises(MountError, match="Cannot update the mount at /m") as exc:
        await fs.update_mount("/m", no_overlay=True)
    assert exc.value.errors[0].kind is ErrorKind.unsupported
    assert fs.mounts()[1].no_overlay is False


async def test_the_root_can_clear_its_own_mask_of_mkdir_and_delete() -> None:
    # The root has no mount above it, so its own mask never refuses a change to the root mount.
    fs = AsyncVirtualFileSystem(storage=BindableStorage(name="root"))
    await fs.update_mount("/", deny_ops={"mkdir", "delete"})
    await fs.update_mount("/", deny_ops=())
    assert fs.mounts()[0].deny_ops == frozenset()


class RestoreRecorder(InMemoryStorage):
    """An in-memory storage that records the authority of every ``restore`` it is asked to run."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.restored_as: list[Authority | None] = []

    async def restore(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self.restored_as.append(authority)
        return await super().restore(authority=authority, **kwargs)


async def test_a_mount_added_again_restores_its_directory_as_the_caller() -> None:
    root = RestoreRecorder()
    fs = AsyncVirtualFileSystem(storage=root)
    await fs.add_mount(InMemoryStorage(), "/data", authority=ADA)
    await fs.remove_mount("/data", authority=ADA)
    await fs.add_mount(InMemoryStorage(), "/data", authority=ADA)
    assert root.restored_as == [ADA]
    assert paths(fs) == ["/", "/data"]


async def test_the_system_actor_and_a_default_authority_may_change_a_mount() -> None:
    fs = await closed()
    await fs.add_mount(InMemoryStorage(), "/a", authority=SYSTEM)
    await fs.update_mount("/a", no_overlay=True, authority=SYSTEM)
    await fs.remove_mount("/a", authority=SYSTEM)
    assert paths(fs) == ["/"]

    trusted = AsyncVirtualFileSystem(default_authority=SYSTEM)
    assert (await trusted.set_posture("/", "none")).success is True
    await trusted.add_mount(InMemoryStorage(), "/a")
    assert paths(trusted) == ["/", "/a"]


async def test_the_storage_that_holds_the_mount_point_judges() -> None:
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(InMemoryStorage(), "/outer")
    # The storage at /outer is closed and the root stays open.
    assert (await fs.set_posture("/outer", "none", authority=SYSTEM)).success is True
    with pytest.raises(MountError, match="Cannot mount at /outer/inner") as exc:
        await fs.add_mount(InMemoryStorage(), "/outer/inner")
    assert exc.value.errors[0].kind is ErrorKind.unauthenticated
    assert str(exc.value.errors[0].path) == "/outer/inner"
    # The mount point of /outer itself is a directory in the root, which is open.
    await fs.update_mount("/outer", no_overlay=True)
    assert fs.mounts()[1].no_overlay is True


async def test_a_mount_change_asks_one_question_and_the_system_actor_asks_none() -> None:
    root = BindableStorage(name="root")
    fs = AsyncVirtualFileSystem(storage=root)
    await fs.add_mount(RecorderStorage(name="child"), "/m", authority=ADA)
    asked = [(op, kwargs) for op, kwargs in root.calls if op == "holds"]
    assert [(str(kwargs["path"]), kwargs["level"]) for _, kwargs in asked] == [("/m", "read_write")]
    assert root.calls[0][0] == "holds"  # asked before the directory was made
    assert root.authorities[0] == ADA

    root.calls.clear()
    await fs.update_mount("/m", no_overlay=True, authority=SYSTEM)
    await fs.remove_mount("/m", authority=SYSTEM)
    assert all(op != "holds" for op, _ in root.calls)


class UnreachableRights(BindableStorage):
    """A storage whose peer is gone when it is asked what a caller holds."""

    async def holds(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        raise TransportError("the peer hung up")


async def test_a_storage_that_cannot_be_reached_refuses_the_mount_change() -> None:
    fs = AsyncVirtualFileSystem(storage=UnreachableRights(name="root"))
    with pytest.raises(MountError, match=r"Cannot mount at /m: .*the peer hung up") as exc:
        await fs.add_mount(RecorderStorage(), "/m", authority=ADA)
    assert exc.value.errors[0].kind is ErrorKind.backend_unavailable
    assert paths(fs) == ["/"]


class SlowRights(BindableStorage):
    """A storage that says what a caller holds only when the test lets it."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.asked = asyncio.Event()
        self.release = asyncio.Event()

    async def holds(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self.asked.set()
        await self.release.wait()
        return Result(ops=("holds",))


async def test_a_mount_added_above_while_rights_were_judged_refuses_the_change() -> None:
    # The root judged ada for /x/y. By the time she commits, /x is a mount and its storage never judged her.
    root = SlowRights(name="root")
    fs = AsyncVirtualFileSystem(storage=root)
    pending = asyncio.create_task(fs.add_mount(RecorderStorage(name="child"), "/x/y", authority=ADA))
    await root.asked.wait()
    await fs.add_mount(BindableStorage(name="above"), "/x", authority=SYSTEM)
    root.release.set()
    with pytest.raises(ValueError, match="retry"):
        await pending
    assert paths(fs) == ["/", "/x"]


async def test_a_storage_mounted_again_elsewhere_while_rights_were_judged_refuses_the_add() -> None:
    # The storage at /x/y judged ada for /z inside it. It is now at /x, where /x/y/z is /y/z, a path it never judged.
    root = BindableStorage(name="root")
    judge = SlowRights(name="judge")
    fs = AsyncVirtualFileSystem(storage=root)
    await fs.add_mount(judge, "/x/y", authority=SYSTEM)
    child = RecorderStorage(name="child")
    pending = asyncio.create_task(fs.add_mount(child, "/x/y/z", authority=ADA))
    await judge.asked.wait()
    await fs.remove_mount("/x/y", authority=SYSTEM)
    await fs.add_mount(judge, "/x", authority=SYSTEM)
    judge.release.set()
    with pytest.raises(ValueError, match="retry"):
        await pending
    assert paths(fs) == ["/", "/x"]
    assert all(mount.storage is not child for mount in fs.mounts())


async def replace_the_mount_at_x_y(fs: AsyncVirtualFileSystem, *, above: bool) -> RecorderStorage:
    """Put another storage at /x/y as the system actor, under a new mount at /x when ``above`` is true."""
    await fs.remove_mount("/x/y", authority=SYSTEM)
    if above:
        await fs.add_mount(BindableStorage(name="above"), "/x", authority=SYSTEM)
    replacement = RecorderStorage(name="replacement")
    await fs.add_mount(replacement, "/x/y", authority=SYSTEM)
    return replacement


@pytest.mark.parametrize("above", [False, True], ids=["replaced", "mount-added-above"])
async def test_a_mount_replaced_while_rights_were_judged_refuses_the_update(above: bool) -> None:
    # The root judged ada for the mount it saw at /x/y. The mount there now is another one.
    root = SlowRights(name="root")
    fs = AsyncVirtualFileSystem(storage=root)
    await fs.add_mount(RecorderStorage(name="first"), "/x/y", authority=SYSTEM)
    pending = asyncio.create_task(fs.update_mount("/x/y", no_overlay=True, deny_ops={"sweep"}, authority=ADA))
    await root.asked.wait()
    replacement = await replace_the_mount_at_x_y(fs, above=above)
    root.release.set()
    with pytest.raises(ValueError, match="retry"):
        await pending
    mount = fs.mounts()[-1]
    assert (str(mount.path), mount.storage) == ("/x/y", replacement)
    assert (mount.no_overlay, mount.deny_ops) == (False, frozenset())


@pytest.mark.parametrize("above", [False, True], ids=["replaced", "mount-added-above"])
async def test_a_mount_replaced_while_rights_were_judged_refuses_the_remove(above: bool) -> None:
    root = SlowRights(name="root")
    fs = AsyncVirtualFileSystem(storage=root)
    await fs.add_mount(RecorderStorage(name="first"), "/x/y", authority=SYSTEM)
    pending = asyncio.create_task(fs.remove_mount("/x/y", authority=ADA))
    await root.asked.wait()
    replacement = await replace_the_mount_at_x_y(fs, above=above)
    root.release.set()
    with pytest.raises(ValueError, match="retry"):
        await pending
    assert fs.mounts()[-1].storage is replacement
    assert paths(fs) == (["/", "/x", "/x/y"] if above else ["/", "/x/y"])


class GrantsWithoutTheQuestion(ReadFamilyStorage):
    """A storage that declares the grant verbs and cannot say what a caller holds."""

    def capabilities(self) -> frozenset[Op]:
        writes: frozenset[Op] = frozenset({"mkdir", "delete"})
        return super().capabilities() | GRANT_OPS | writes

    async def mkdir(self, **kwargs: Any) -> Result:
        return Result(ops=("mkdir",))


async def test_a_storage_that_keeps_grants_and_cannot_answer_refuses_a_named_caller() -> None:
    fs = AsyncVirtualFileSystem(storage=GrantsWithoutTheQuestion())
    with pytest.raises(MountError, match="Cannot mount at /m") as exc:
        await fs.add_mount(RecorderStorage(), "/m", authority=ADA)
    assert exc.value.errors[0].kind is ErrorKind.unsupported
    assert paths(fs) == ["/"]


async def test_a_storage_that_keeps_no_grants_has_nothing_to_judge() -> None:
    # No grant verb is declared, so there are no rights here to go around. The gate still decides.
    fs = AsyncVirtualFileSystem(storage=ReadFamilyStorage())
    with pytest.raises(MountError, match="Cannot mount at /m") as exc:
        await fs.add_mount(RecorderStorage(), "/m", authority=ADA)
    assert exc.value.errors[0].kind is ErrorKind.unsupported
    assert "mkdir" in str(exc.value)
