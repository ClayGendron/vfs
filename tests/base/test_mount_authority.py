"""Who may change a mount: the caller needs ``read_write`` at the mount point, and the storage that holds it says so."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

import pytest

from tests.support.base_doubles import BindableStorage, ReadFamilyStorage, RecorderStorage
from vfs import AsyncVirtualFileSystem, InMemoryStorage, VirtualFileSystem
from vfs.authority import Authority, Principal
from vfs.exceptions import MountError
from vfs.ops import GRANT_OPS
from vfs.results import ErrorKind, Result

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
