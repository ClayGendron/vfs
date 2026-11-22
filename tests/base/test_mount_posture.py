"""A mount can be added closed: ``add_mount(..., posture=...)`` sets what everyone holds before the mount is live."""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
from collections import UserString
from functools import partial
from typing import TYPE_CHECKING, Any

import pytest

from tests.support.base_doubles import (
    BindableStorage,
    ReadFamilyStorage,
    RecorderStorage,
    TransportFailStorage,
)
from vfs import AsyncVirtualFileSystem, DatabaseStorage, InMemoryStorage, VirtualFileSystem
from vfs.authority import Authority, Principal
from vfs.exceptions import MountError
from vfs.mounts import Mount, MountPayload, everyone_holds, mount_table_refusal, validate_posture
from vfs.ops import GRANT_OPS, RUNGS
from vfs.paths import Path
from vfs.results import ErrorKind, Result, ResultError

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

    from vfs.ops import Op
    from vfs.storage import StorageBackend
    from vfs.storage.grants import Posture

SYSTEM = Authority.system()
ADA = Authority.of(Principal("ada"))

# The two faces of the kernel, with calls to await and with plain calls.
Face = type[AsyncVirtualFileSystem] | type[VirtualFileSystem]


async def closed() -> AsyncVirtualFileSystem:
    """A file system whose posture gives nobody anything, so only a grant or the system actor passes."""
    fs = AsyncVirtualFileSystem()
    assert (await fs.set_posture("/", "none", authority=SYSTEM)).success is True
    return fs


def paths(fs: AsyncVirtualFileSystem) -> list[str]:
    return [str(mount.path) for mount in fs.mounts()]


def everyone_rows(answer: Result) -> list[dict[str, Any]]:
    return [row for row in (answer.model_extra or {}).get("grants") or [] if row["principal_id"] == "*"]


async def posture_at(fs: AsyncVirtualFileSystem, path: str) -> str | None:
    """The level of the everyone row stored exactly at ``path``, as the system actor reads it."""
    rows = everyone_rows(await fs.grants(path, authority=SYSTEM))
    return next((row["level"] for row in rows if row["path_prefix"] == path), None)


def granted(*rows: dict[str, Any]) -> Result:
    return Result(ops=("grants",)).model_copy(update={"grants": list(rows)})


def refused(kind: ErrorKind, message: str) -> Result:
    return Result(ops=("set_posture",), errors=[ResultError(kind=kind, message=message, path=Path("/"))])


class WaitingPostureStorage(RecorderStorage):
    """A child whose ``set_posture`` records the mount table, says it has started, and waits to be released."""

    def __init__(self, fs: AsyncVirtualFileSystem | None = None) -> None:
        super().__init__()
        self.fs = fs
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.seen: list[list[str]] = []

    async def set_posture(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        if self.fs is not None:
            self.seen.append(paths(self.fs))
        self.entered.set()
        await self.release.wait()
        return self._answer("set_posture", kwargs, authority)


class WaitingGrantsStorage(RecorderStorage):
    """A child whose ``grants`` read says it has started and waits to be released."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def grants(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self.entered.set()
        await self.release.wait()
        return self._answer("grants", kwargs, authority)


class HoldsListStorage(RecorderStorage):
    """A child whose ``grants`` read says that everyone already holds ``list`` at its root."""

    async def grants(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self._answer("grants", kwargs, authority)
        return granted({"principal_id": "*", "path_prefix": "/", "level": "list"})


class WaitingLsStorage(InMemoryStorage):
    """An in-memory root whose ``ls`` of ``/work`` says it has answered and waits to be released."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def ls(self, **kwargs: Any) -> Result:
        answer = await super().ls(**kwargs)
        if kwargs.get("path") == "/work":
            self.entered.set()
            await self.release.wait()
        return answer


class SlowProbeStorage(BindableStorage):
    """A root whose ``ls`` says it has started and waits to be released."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def ls(self, **kwargs: Any) -> Result:
        self.entered.set()
        await self.release.wait()
        return await super().ls(**kwargs)


class RootCopyingStorage(RecorderStorage):
    """A child whose ``set_posture`` copies the ops the root storage has recorded so far."""

    def __init__(self, root: RecorderStorage) -> None:
        super().__init__()
        self.root = root
        self.root_ops: list[str] = []

    async def set_posture(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self.root_ops = [op for op, _ in self.root.calls]
        return self._answer("set_posture", kwargs, authority)


class RefusingPostureStorage(RecorderStorage):
    """A child whose ``set_posture`` is refused with ``permission_denied``, carrying ``message``."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    async def set_posture(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self._answer("set_posture", kwargs, authority)
        return refused(ErrorKind.permission_denied, self.message)


class FailsOncePostureStorage(RecorderStorage):
    """A child whose first ``set_posture`` fails and whose later ones succeed."""

    async def set_posture(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        answer = self._answer("set_posture", kwargs, authority)
        first = [op for op, _ in self.calls].count("set_posture") == 1
        return refused(ErrorKind.internal, "the first write broke") if first else answer


class RaisingPostureStorage(RecorderStorage):
    """A child whose ``set_posture`` has a fault and raises."""

    async def set_posture(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        msg = "the posture write broke"
        raise RuntimeError(msg)


class ClaimsGrantsStorage(ReadFamilyStorage):
    """A read-only double that declares the grant verbs and has none of their methods."""

    def capabilities(self) -> frozenset[Op]:
        return super().capabilities() | GRANT_OPS


class CountingMemoryStorage(InMemoryStorage):
    """An in-memory storage that counts its ``set_posture`` calls."""

    def __init__(self) -> None:
        super().__init__()
        self.posture_writes = 0

    async def set_posture(self, **kwargs: Any) -> Result:
        self.posture_writes += 1
        return await super().set_posture(**kwargs)


class WaitingGrantsMemoryStorage(CountingMemoryStorage):
    """A new in-memory storage whose ``grants`` read says it has started and waits to be released."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def grants(self, **kwargs: Any) -> Result:
        self.entered.set()
        await self.release.wait()
        return await super().grants(**kwargs)


class CountingDatabaseStorage(DatabaseStorage):
    """A database storage that counts its ``set_posture`` calls."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.posture_writes = 0

    async def set_posture(self, **kwargs: Any) -> Result:
        self.posture_writes += 1
        return await super().set_posture(**kwargs)


async def stored_closed(storage: DatabaseStorage) -> AsyncVirtualFileSystem:
    """Close ``storage`` at its root, and return a closed file system where ada holds ``read_write`` at ``/data``."""
    assert (await storage.set_posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
    fs = await closed()
    assert (await fs.mkdir("/data", authority=SYSTEM)).success is True
    assert (await fs.grant("/data", "ada", "read_write", authority=SYSTEM)).success is True
    return fs


# ---------------------------------------------------------------------------
# The argument
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("face", [AsyncVirtualFileSystem, VirtualFileSystem])
def test_add_mount_takes_a_posture_that_defaults_to_none(face: Face) -> None:
    posture = inspect.signature(face.add_mount).parameters["posture"]
    assert (posture.kind, posture.default) == (inspect.Parameter.KEYWORD_ONLY, None)


@pytest.mark.parametrize("face", [AsyncVirtualFileSystem, VirtualFileSystem])
def test_update_mount_and_the_mount_take_no_posture(face: Face) -> None:
    assert "posture" not in inspect.signature(face.update_mount).parameters
    assert "posture" not in {field.name for field in dataclasses.fields(Mount)}
    assert "posture" not in MountPayload.__annotations__


async def test_a_mount_added_closed_is_closed_from_its_first_call() -> None:
    fs = await closed()
    await fs.add_mount(InMemoryStorage(), "/data", posture="none", authority=SYSTEM)
    assert (await fs.write(path="/data/report.md", content="q3", authority=SYSTEM)).success is True
    assert (await fs.read("/data/report.md")).errors[0].kind is ErrorKind.unauthenticated
    assert (await fs.read("/data/report.md", authority=ADA)).errors[0].kind is ErrorKind.not_found
    assert await posture_at(fs, "/data") == "none"


async def test_a_mount_added_with_no_posture_keeps_what_its_storage_holds() -> None:
    fs = await closed()
    await fs.add_mount(InMemoryStorage(), "/data", authority=SYSTEM)
    assert await posture_at(fs, "/data") == "read_write"
    assert (await fs.write(path="/data/a.md", content="open")).success is True
    kept = DatabaseStorage(url="sqlite+aiosqlite:///:memory:", posture="list")
    await fs.add_mount(kept, "/kept", authority=SYSTEM)
    assert await posture_at(fs, "/kept") == "list"
    await fs.close()


@pytest.mark.parametrize("level", RUNGS)
async def test_each_level_can_be_the_posture_of_a_new_mount(level: Posture) -> None:
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(InMemoryStorage(), "/data", posture=level)
    assert await posture_at(fs, "/data") == level


# ---------------------------------------------------------------------------
# What the child is asked, and when
# ---------------------------------------------------------------------------


async def test_no_posture_asks_the_new_storage_nothing() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    child = RecorderStorage()
    await fs.add_mount(child, "/m", authority=SYSTEM)
    assert child.calls == []


async def test_a_posture_is_set_at_the_root_as_the_caller() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    child = RecorderStorage()
    await fs.add_mount(child, "/m", posture="list", authority=ADA)
    assert child.calls == [("grants", {"path": Path("/")}), ("set_posture", {"path": Path("/"), "posture": "list"})]
    assert child.authorities == [ADA, ADA]


async def test_a_call_with_no_authority_sets_the_posture_as_the_kernel_s_default() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage(), default_authority=ADA)
    child = RecorderStorage()
    await fs.add_mount(child, "/m", posture="list")
    assert child.authorities == [ADA, ADA]


async def test_a_posture_checks_the_mount_point_again_whether_or_not_it_is_written() -> None:
    root = BindableStorage()
    fs = AsyncVirtualFileSystem(storage=root)
    await fs.add_mount(RecorderStorage(), "/m", posture="list", authority=SYSTEM)
    assert [op for op, _ in root.calls] == ["mkdir", "stat", "ls", "stat", "ls"]
    root.calls.clear()
    held = HoldsListStorage()
    await fs.add_mount(held, "/n", posture="list", authority=SYSTEM)
    assert [op for op, _ in held.calls] == ["grants"]
    assert [op for op, _ in root.calls] == ["mkdir", "stat", "ls", "stat", "ls"]


async def test_a_storage_that_does_not_declare_grants_is_written_without_a_read() -> None:
    child = RecorderStorage(caps=RecorderStorage().capabilities() - {"grants"})
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(child, "/m", posture="list")
    assert [op for op, _ in child.calls] == ["set_posture"]


async def test_the_posture_is_set_before_the_mount_is_in_the_table() -> None:
    fs = AsyncVirtualFileSystem()
    child = WaitingPostureStorage(fs)
    task = asyncio.create_task(fs.add_mount(child, "/data", posture="none"))
    await child.entered.wait()
    assert paths(fs) == ["/"]
    child.release.set()
    await task
    assert paths(fs) == ["/", "/data"]
    assert child.seen == [["/"]]


async def test_the_posture_is_set_after_the_mount_point_is_made_and_checked() -> None:
    root = BindableStorage()
    fs = AsyncVirtualFileSystem(storage=root)
    child = RootCopyingStorage(root)
    await fs.add_mount(child, "/m", posture="none", authority=SYSTEM)
    assert child.root_ops == ["mkdir", "stat", "ls"]


# ---------------------------------------------------------------------------
# A refused call leaves the child's posture alone
# ---------------------------------------------------------------------------


async def test_a_caller_who_may_not_mount_changes_no_posture() -> None:
    fs = await closed()
    assert (await fs.mkdir("/data", authority=SYSTEM)).success is True
    assert (await fs.grant("/data", "ada", "contribute", authority=SYSTEM)).success is True
    child = RecorderStorage()
    with pytest.raises(MountError) as exc:
        await fs.add_mount(child, "/data", posture="none", authority=ADA)
    assert exc.value.errors[0].kind is ErrorKind.permission_denied
    assert child.calls == []


async def test_a_mount_point_that_cannot_hold_a_mount_changes_no_posture() -> None:
    fs = AsyncVirtualFileSystem()
    assert (await fs.mkdir("/data", authority=SYSTEM)).success is True
    assert (await fs.write(path="/data/x.md", content="x", authority=SYSTEM)).success is True
    child = RecorderStorage()
    with pytest.raises(ValueError, match="not empty"):
        await fs.add_mount(child, "/data", posture="none")
    assert child.calls == []


async def test_a_storage_that_is_already_mounted_keeps_its_posture() -> None:
    fs = AsyncVirtualFileSystem()
    storage = InMemoryStorage()
    await fs.add_mount(storage, "/a")
    with pytest.raises(ValueError, match="already mounted"):
        await fs.add_mount(storage, "/b", posture="none")
    assert await posture_at(fs, "/a") == "read_write"


@pytest.mark.parametrize(
    "make",
    [ReadFamilyStorage, partial(RecorderStorage, caps=frozenset({"read", "stat", "ls", "tree"}))],
    ids=["read-family", "declares-no-grants"],
)
async def test_a_storage_that_keeps_no_posture_refuses_one_before_anything_is_made(
    make: Callable[[], StorageBackend],
) -> None:
    fs = AsyncVirtualFileSystem()
    child = make()
    with pytest.raises(MountError, match="keeps no posture") as exc:
        await fs.add_mount(child, "/m", posture="none")
    assert exc.value.errors[0].kind is ErrorKind.unsupported
    assert str(exc.value.errors[0].path) == "/m"
    assert paths(fs) == ["/"]
    assert (await fs.stat("/m", authority=SYSTEM)).errors[0].kind is ErrorKind.not_found
    await fs.add_mount(child, "/m")
    assert paths(fs) == ["/", "/m"]


async def test_a_storage_that_declares_the_grant_verbs_and_lacks_them_refuses_a_posture() -> None:
    fs = AsyncVirtualFileSystem()
    with pytest.raises(MountError) as exc:
        await fs.add_mount(ClaimsGrantsStorage(), "/m", posture="none")
    assert exc.value.errors[0].kind is ErrorKind.unsupported
    assert paths(fs) == ["/"]
    assert (await fs.stat("/m", authority=SYSTEM)).errors[0].kind is ErrorKind.not_found


async def test_a_storage_that_keeps_no_posture_is_refused_before_the_rights_are_checked() -> None:
    fs = await closed()
    with pytest.raises(MountError, match="keeps no posture") as exc:
        await fs.add_mount(ReadFamilyStorage(), "/m", posture="none", authority=ADA)
    assert exc.value.errors[0].kind is ErrorKind.unsupported


async def test_a_gate_tightened_while_the_mount_point_is_checked_changes_no_posture() -> None:
    root = SlowProbeStorage()
    fs = AsyncVirtualFileSystem(storage=root)
    child = RecorderStorage()
    task = asyncio.create_task(fs.add_mount(child, "/m", posture="none", authority=SYSTEM))
    await root.entered.wait()
    await fs.update_mount("/", permissions="read", authority=SYSTEM)
    root.release.set()
    with pytest.raises(MountError) as exc:
        await task
    assert exc.value.errors[0].kind is ErrorKind.read_only
    assert child.calls == []


async def test_an_unknown_posture_is_refused_before_anything_is_made() -> None:
    fs = await closed()
    with pytest.raises(ValueError, match="posture must be one of") as exc:
        await fs.add_mount(InMemoryStorage(), "/m", posture="open", authority=ADA)  # ty: ignore[invalid-argument-type]
    # Exactly ValueError, so the check came before the rights check, which raises MountError.
    assert type(exc.value) is ValueError
    assert paths(fs) == ["/"]
    assert (await fs.stat("/m", authority=SYSTEM)).errors[0].kind is ErrorKind.not_found


async def test_a_storage_that_refuses_the_posture_is_not_mounted() -> None:
    fs = AsyncVirtualFileSystem()
    with pytest.raises(MountError, match="Cannot mount at /m") as exc:
        await fs.add_mount(RefusingPostureStorage("no posture for you"), "/m", posture="none")
    assert exc.value.errors[0].kind is ErrorKind.permission_denied
    assert str(exc.value.errors[0].path) == "/m"
    assert paths(fs) == ["/"]
    assert (await fs.stat("/m", authority=SYSTEM)).success is True
    with pytest.raises(MountError, match="the storage refused the posture"):
        await fs.add_mount(RefusingPostureStorage(""), "/m", posture="none")


async def test_a_storage_that_cannot_be_reached_is_not_mounted() -> None:
    fs = AsyncVirtualFileSystem()
    with pytest.raises(MountError) as exc:
        await fs.add_mount(TransportFailStorage(), "/m", posture="none")
    assert exc.value.errors[0].kind is ErrorKind.backend_unavailable
    assert str(exc.value.errors[0].path) == "/m"
    assert paths(fs) == ["/"]


# ---------------------------------------------------------------------------
# What is written
# ---------------------------------------------------------------------------


async def test_a_storage_that_already_holds_the_posture_is_not_written() -> None:
    child = CountingMemoryStorage()
    assert (await child.set_posture(path=Path("/"), posture="list", authority=SYSTEM)).success is True
    assert child.posture_writes == 1
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(child, "/data", posture="list", authority=SYSTEM)
    assert child.posture_writes == 1
    assert await posture_at(fs, "/data") == "list"
    await fs.remove_mount("/data", authority=SYSTEM)
    await fs.add_mount(child, "/data", posture="read", authority=SYSTEM)
    assert child.posture_writes == 2
    assert await posture_at(fs, "/data") == "read"


async def test_a_named_caller_s_grant_at_the_root_does_not_stand_for_everyone() -> None:
    child = InMemoryStorage()
    assert (await child.grant(path=Path("/"), principal="ada", level="read", authority=SYSTEM)).success is True
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(child, "/data", posture="read", authority=SYSTEM)
    assert await posture_at(fs, "/data") == "read"
    assert (await fs.write(path="/data/x.md", content="anon")).success is False


async def test_a_posture_replaces_a_stored_one_and_keeps_the_deeper_ones(tmp_path: pathlib.Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path}/stored.sqlite"
    first = AsyncVirtualFileSystem()
    await first.add_mount(DatabaseStorage(url=url), "/data", authority=SYSTEM)
    assert (await first.set_posture("/data", "none", authority=SYSTEM)).success is True
    assert (await first.set_posture("/data/pub", "read", authority=SYSTEM)).success is True
    assert (await first.grant("/data", "ada", "read", authority=SYSTEM)).success is True
    await first.close()

    fs = AsyncVirtualFileSystem()
    storage = DatabaseStorage(url=url)
    await fs.add_mount(storage, "/data", authority=SYSTEM)
    assert await posture_at(fs, "/data") == "none"
    await fs.remove_mount("/data", authority=SYSTEM)
    await fs.add_mount(storage, "/data", posture="list", authority=SYSTEM)
    assert await posture_at(fs, "/data") == "list"
    assert await posture_at(fs, "/data/pub") == "read"
    rows = (await fs.grants("/data", authority=SYSTEM)).model_extra or {}
    ada = [row for row in rows["grants"] if row["principal_id"] == "ada"]
    assert [(row["path_prefix"], row["level"]) for row in ada] == [("/data", "read")]
    await fs.close()


async def test_the_mask_does_not_stop_the_posture_of_a_new_mount() -> None:
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(InMemoryStorage(), "/frozen", posture="read", deny_ops={"set_posture"})
    assert await posture_at(fs, "/frozen") == "read"
    answer = await fs.set_posture("/frozen", "none", authority=SYSTEM)
    assert answer.errors[0].kind is ErrorKind.unsupported


async def test_the_mount_s_own_permissions_do_not_stop_its_posture() -> None:
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(InMemoryStorage(), "/ro", permissions="read", posture="none")
    assert await posture_at(fs, "/ro") == "none"
    answer = await fs.set_posture("/ro", "read", authority=SYSTEM)
    assert answer.errors[0].kind is ErrorKind.read_only


# ---------------------------------------------------------------------------
# The reservation of the storage object
# ---------------------------------------------------------------------------


async def test_no_second_call_mounts_a_storage_while_its_posture_is_being_set() -> None:
    fs = AsyncVirtualFileSystem()
    child = WaitingPostureStorage()
    first = asyncio.create_task(fs.add_mount(child, "/a", posture="none"))
    await child.entered.wait()
    with pytest.raises(ValueError, match="another call is mounting"):
        await fs.add_mount(child, "/b")
    with pytest.raises(ValueError, match="another call is mounting"):
        await fs.add_mount(child, "/b", posture="read")
    child.release.set()
    await first
    assert paths(fs) == ["/", "/a"]
    assert [op for op, _ in child.calls].count("set_posture") == 1


async def test_a_failed_posture_write_frees_the_storage_for_the_next_call() -> None:
    fs = AsyncVirtualFileSystem()
    child = FailsOncePostureStorage()
    with pytest.raises(MountError):
        await fs.add_mount(child, "/m", posture="none")
    await fs.add_mount(child, "/m", posture="none")
    assert paths(fs) == ["/", "/m"]


async def test_the_posture_stays_when_the_table_refuses_the_mount_after_it_was_set() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    child = WaitingPostureStorage()
    first = asyncio.create_task(fs.add_mount(child, "/data", posture="none"))
    await child.entered.wait()
    # A mount lock held across the posture write would keep this call from returning.
    await fs.add_mount(RecorderStorage(), "/data")
    child.release.set()
    with pytest.raises(ValueError, match="Mount already exists"):
        await first
    ops = [op for op, _ in child.calls]
    assert ops.count("set_posture") == 1
    assert ops[-1] == "set_posture"


async def test_a_cancelled_posture_write_frees_the_storage() -> None:
    fs = AsyncVirtualFileSystem()
    child = WaitingPostureStorage()
    task = asyncio.create_task(fs.add_mount(child, "/a", posture="none"))
    await child.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await fs.add_mount(child, "/a")
    assert paths(fs) == ["/", "/a"]


async def test_a_storage_that_raises_in_set_posture_is_freed() -> None:
    fs = AsyncVirtualFileSystem()
    child = RaisingPostureStorage()
    with pytest.raises(RuntimeError, match="the posture write broke"):
        await fs.add_mount(child, "/m", posture="none")
    await fs.add_mount(child, "/m")
    assert paths(fs) == ["/", "/m"]


# ---------------------------------------------------------------------------
# What changes while the posture is read or written
# ---------------------------------------------------------------------------


async def test_a_mount_point_that_gains_a_row_during_the_posture_write_is_not_covered() -> None:
    fs = AsyncVirtualFileSystem()
    child = WaitingPostureStorage()
    task = asyncio.create_task(fs.add_mount(child, "/inbox", posture="read", authority=SYSTEM))
    await child.entered.wait()
    assert (await fs.write(path="/inbox/note.txt", content="hello", authority=SYSTEM)).success is True
    child.release.set()
    with pytest.raises(ValueError, match="not empty"):
        await task
    assert paths(fs) == ["/"]
    assert (await fs.read("/inbox/note.txt", authority=SYSTEM)).success is True
    assert [op for op, _ in child.calls] == ["grants", "set_posture"]


async def test_a_mount_point_that_gains_a_row_while_a_held_posture_is_read_is_not_covered() -> None:
    fs = AsyncVirtualFileSystem()
    child = WaitingGrantsMemoryStorage()
    task = asyncio.create_task(fs.add_mount(child, "/inbox", posture="read_write", authority=SYSTEM))
    await child.entered.wait()
    assert (await fs.write(path="/inbox/note.txt", content="hello", authority=SYSTEM)).success is True
    child.release.set()
    with pytest.raises(ValueError, match="not empty"):
        await task
    assert paths(fs) == ["/"]
    assert (await fs.read("/inbox/note.txt", authority=SYSTEM)).success is True
    assert child.posture_writes == 0


async def test_a_mount_point_removed_during_the_posture_write_is_not_mounted() -> None:
    fs = AsyncVirtualFileSystem()
    child = WaitingPostureStorage()
    task = asyncio.create_task(fs.add_mount(child, "/gone", posture="read", authority=SYSTEM))
    await child.entered.wait()
    assert (await fs.delete("/gone", authority=SYSTEM)).success is True
    child.release.set()
    with pytest.raises(ValueError, match="no directory stored at the mount point"):
        await task
    assert paths(fs) == ["/"]


async def test_a_mount_point_whose_holder_changed_during_the_posture_write_is_not_mounted() -> None:
    root = WaitingLsStorage()
    fs = AsyncVirtualFileSystem(storage=root)
    parent = asyncio.create_task(fs.add_mount(InMemoryStorage(), "/work", authority=SYSTEM))
    await root.entered.wait()
    child = WaitingPostureStorage()
    task = asyncio.create_task(fs.add_mount(child, "/work/sub", posture="read", authority=SYSTEM))
    await child.entered.wait()
    root.release.set()
    await parent
    child.release.set()
    with pytest.raises(ValueError, match="no directory stored at the mount point"):
        await task
    assert paths(fs) == ["/", "/work"]


async def test_a_mount_point_whose_holder_was_removed_while_the_posture_is_read_is_not_mounted() -> None:
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(InMemoryStorage(), "/work", authority=SYSTEM)
    child = WaitingGrantsStorage()
    task = asyncio.create_task(fs.add_mount(child, "/work/sub", posture="none", authority=SYSTEM))
    await child.entered.wait()
    await fs.remove_mount("/work", authority=SYSTEM)
    child.release.set()
    with pytest.raises(ValueError, match="no directory stored at the mount point"):
        await task
    assert paths(fs) == ["/"]


async def test_a_kernel_closed_during_the_posture_write_adds_no_mount() -> None:
    fs = AsyncVirtualFileSystem()
    child = WaitingPostureStorage()
    task = asyncio.create_task(fs.add_mount(child, "/data", posture="none", authority=SYSTEM))
    await child.entered.wait()
    await fs.close()
    child.release.set()
    with pytest.raises(ValueError, match="filesystem is closed"):
        await task
    assert paths(fs) == []


async def test_a_kernel_closed_while_the_posture_is_read_writes_no_posture() -> None:
    fs = AsyncVirtualFileSystem()
    child = WaitingGrantsStorage()
    task = asyncio.create_task(fs.add_mount(child, "/data", posture="read", authority=SYSTEM))
    await child.entered.wait()
    await fs.close()
    child.release.set()
    with pytest.raises(ValueError, match="filesystem is closed"):
        await task
    assert [op for op, _ in child.calls] == ["grants"]


async def test_a_gate_tightened_while_the_posture_is_read_writes_no_posture() -> None:
    fs = AsyncVirtualFileSystem()
    child = WaitingGrantsStorage()
    task = asyncio.create_task(fs.add_mount(child, "/data", posture="read", authority=SYSTEM))
    await child.entered.wait()
    await fs.update_mount("/", permissions="read", authority=SYSTEM)
    child.release.set()
    with pytest.raises(MountError) as exc:
        await task
    assert exc.value.errors[0].kind is ErrorKind.read_only
    assert [op for op, _ in child.calls] == ["grants"]


async def test_a_mount_point_taken_while_the_posture_is_read_writes_no_posture() -> None:
    fs = AsyncVirtualFileSystem()
    child = WaitingGrantsStorage()
    task = asyncio.create_task(fs.add_mount(child, "/data", posture="read", authority=SYSTEM))
    await child.entered.wait()
    await fs.add_mount(RecorderStorage(), "/data", authority=SYSTEM)
    child.release.set()
    with pytest.raises(ValueError, match="Mount already exists"):
        await task
    assert [op for op, _ in child.calls] == ["grants"]


# ---------------------------------------------------------------------------
# As whom the posture is set
# ---------------------------------------------------------------------------


async def test_a_named_caller_who_adds_a_closed_mount_holds_nothing_in_it() -> None:
    fs = await closed()
    assert (await fs.mkdir("/data", authority=SYSTEM)).success is True
    assert (await fs.grant("/data", "ada", "read_write", authority=SYSTEM)).success is True
    await fs.add_mount(InMemoryStorage(), "/data", posture="none", authority=ADA)
    assert (await fs.write(path="/data/a.md", content="x", authority=ADA)).errors[0].kind is ErrorKind.permission_denied
    rows = (await fs.grants("/data", authority=SYSTEM)).model_extra or {}
    assert [(row["principal_id"], row["granted_by"]) for row in rows["grants"]] == [("*", "ada")]


async def test_a_named_caller_cannot_widen_a_stored_posture(tmp_path: pathlib.Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path}/shared.sqlite"
    storage = DatabaseStorage(url=url)
    fs = await stored_closed(storage)
    with pytest.raises(MountError) as exc:
        await fs.add_mount(storage, "/data", posture="read_write", authority=ADA)
    assert exc.value.errors[0].kind is ErrorKind.not_found
    assert paths(fs) == ["/"]
    other = DatabaseStorage(url=url)
    rows = everyone_rows(await other.grants(path=Path("/"), authority=SYSTEM))
    assert [(row["path_prefix"], row["level"]) for row in rows] == [("/", "none")]
    await other.close()
    await storage.close()


async def test_a_named_caller_cannot_add_a_stored_closed_storage_with_the_posture_it_holds(
    tmp_path: pathlib.Path,
) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path}/shared.sqlite"
    storage = DatabaseStorage(url=url)
    fs = await stored_closed(storage)
    with pytest.raises(MountError) as exc:
        await fs.add_mount(storage, "/data", posture="none", authority=ADA)
    assert exc.value.errors[0].kind is ErrorKind.not_found
    await fs.add_mount(storage, "/data", authority=ADA)
    assert await posture_at(fs, "/data") == "none"
    await fs.close()


async def test_a_caller_who_can_read_the_stored_posture_and_asks_for_it_is_not_refused(
    tmp_path: pathlib.Path,
) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path}/shared.sqlite"
    storage = CountingDatabaseStorage(url=url)
    fs = await stored_closed(storage)
    assert (await storage.grant(path=Path("/"), principal="ada", level="read", authority=SYSTEM)).success is True
    storage.posture_writes = 0
    await fs.add_mount(storage, "/data", posture="none", authority=ADA)
    assert storage.posture_writes == 0
    await fs.close()


# ---------------------------------------------------------------------------
# The attach step, the plain face and the helpers
# ---------------------------------------------------------------------------


async def test_the_attach_step_sets_the_posture_itself() -> None:
    fs = AsyncVirtualFileSystem()
    assert (await fs.mkdir("/data", authority=SYSTEM)).success is True
    with pytest.raises(MountError) as exc:
        await fs._attach_mount(ReadFamilyStorage(), "/data", posture="none")
    assert exc.value.errors[0].kind is ErrorKind.unsupported
    undeclared = RecorderStorage(caps=RecorderStorage().capabilities() - {"set_posture"})
    with pytest.raises(MountError) as exc:
        await fs._attach_mount(undeclared, "/data", posture="none")
    assert exc.value.errors[0].kind is ErrorKind.unsupported
    assert undeclared.calls == []
    with pytest.raises(ValueError, match="posture must be one of") as wrong:
        await fs._attach_mount(InMemoryStorage(), "/data", posture="open")  # ty: ignore[invalid-argument-type]
    assert type(wrong.value) is ValueError
    child = RecorderStorage()
    await fs._attach_mount(child, "/data", posture="none")
    assert "set_posture" in [op for op, _ in child.calls]


def test_the_plain_face_passes_the_posture_on() -> None:
    with VirtualFileSystem() as fs:
        fs.add_mount(InMemoryStorage(), "/data", posture="none")
        assert fs.read("/data/a.md").errors[0].kind is ErrorKind.unauthenticated


def test_validate_posture_and_everyone_holds() -> None:
    assert validate_posture(None) is None
    for level in RUNGS:
        assert validate_posture(level) == level
    with pytest.raises(ValueError, match="posture must be one of"):
        validate_posture("open")
    for wrong, kind in ((3, "int"), (UserString("read"), "UserString")):
        with pytest.raises(ValueError, match=f"^posture must be a string, got {kind}$"):
            validate_posture(wrong)
    row = {"principal_id": "*", "path_prefix": "/", "level": "list"}
    assert everyone_holds(refused(ErrorKind.not_found, "gone"), "list") is False
    assert everyone_holds(Result(ops=("grants",)), "list") is False
    assert everyone_holds(granted({**row, "principal_id": "ada"}), "list") is False
    assert everyone_holds(granted({**row, "path_prefix": "/pub"}), "list") is False
    assert everyone_holds(granted({**row, "level": "read"}), "list") is False
    assert everyone_holds(granted(row), "list") is True


def test_the_table_checks_follow_the_order_the_kernel_keeps() -> None:
    mounts = {Path(p): Mount(path=Path(p), storage=RecorderStorage()) for p in ("/", "/m/a", "/m/b")}
    mount = Mount(path=Path("/m"), storage=RecorderStorage())
    for first, second in (("/m/a", "/m/b"), ("/m/b", "/m/a")):
        order = [Path(first), Path(second), Path("/")]
        refusal = mount_table_refusal(mounts, order, mount, set(), "Kernel")
        assert refusal == f"Cannot mount at /m: a deeper mount already sits at {first}"
