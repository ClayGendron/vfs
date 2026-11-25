"""Identity through the router: absence is anonymous by name, the default
is a named privilege, storage always receives an authority, the control
plane runs as the system actor, and the session is sugar over the funnel."""

from __future__ import annotations

import inspect
import logging
import pathlib
import re
from typing import Any

import pytest

import vfs.authority
from tests.support.base_doubles import RecorderFS, RecorderStorage
from vfs.authority import Authority, Principal
from vfs.base import AsyncVirtualFileSystem
from vfs.models import Entry
from vfs.ops import ALL_OPS, Op
from vfs.paths import Path
from vfs.results import ErrorKind, Result
from vfs.session import AsyncSession
from vfs.storage.backends.memory import InMemoryStorage
from vfs.sync import Session, VirtualFileSystem

ALICE = Authority.of(Principal("alice"))
SYSTEM = Authority.system()
ANON = Authority.anonymous()

# The smallest well-formed call per verb — enough to pass the param gate.
CALLS: dict[Op, dict[str, Any]] = {
    "read": {"path": "/f.txt"},
    "stat": {"path": "/f.txt"},
    "ls": {"path": "/"},
    "tree": {"path": "/"},
    "write": {"path": "/f.txt", "content": "x"},
    "edit": {"path": "/f.txt", "old": "a", "new": "b"},
    "delete": {"path": "/f.txt"},
    "restore": {"path": "/f.txt"},
    "sweep": {},
    "mkdir": {"path": "/d"},
    "mkedge": {"source": "/a.py", "target": "/b.py", "edge_type": "ref"},
    "rmedge": {"source": "/a.py", "target": "/b.py", "edge_type": "ref"},
    "move": {"src": "/a", "dest": "/b"},
    "copy": {"src": "/a", "dest": "/b"},
    "glob": {"pattern": "*"},
    "grep": {"pattern": "x"},
    "search": {"query": "x"},
    "traverse": {"method": "outbound", "path": "/f.txt"},
    "run": {"path": "/t"},
    "grant": {"path": "/d", "principal": "bob", "level": "read"},
    "revoke": {"path": "/d", "principal": "bob"},
    "grants": {"path": "/d"},
    "set_posture": {"path": "/d", "posture": "read"},
    "add_member": {"group": "group:eng", "member": "bob"},
    "remove_member": {"group": "group:eng", "member": "bob"},
}


def seen(storage: RecorderStorage) -> list[tuple[str, Authority | None]]:
    """Each recorded call paired with the authority it arrived under."""
    return [(op, authority) for (op, _), authority in zip(storage.calls, storage.authorities, strict=True)]


class RecordingMemory(InMemoryStorage):
    """A real in-memory backend that notes the authority behind the admin verbs."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[tuple[str, Authority | None]] = []

    async def stat(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self.seen.append(("stat", authority))
        return await super().stat(authority=authority, **kwargs)

    async def ls(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self.seen.append(("ls", authority))
        return await super().ls(authority=authority, **kwargs)

    async def mkdir(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self.seen.append(("mkdir", authority))
        return await super().mkdir(authority=authority, **kwargs)

    async def delete(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self.seen.append(("delete", authority))
        return await super().delete(authority=authority, **kwargs)


def test_the_call_table_covers_every_op() -> None:
    assert set(CALLS) == ALL_OPS


# ---------------------------------------------------------------------------
# Absence is a name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("op", sorted(ALL_OPS))
async def test_a_verb_with_no_authority_and_no_default_runs_as_anonymous(op: Op) -> None:
    # Nobody in particular still has a name: storage sees the anonymous
    # authority, never a blank, and the call is not refused here — a
    # mount whose posture wants a name is the one that refuses.
    fs = RecorderFS()
    result = await getattr(fs, op)(**CALLS[op])
    assert result.success is True
    assert seen(fs.backend) and all(authority == ANON for _op, authority in seen(fs.backend))


async def test_garbage_is_still_refused_first() -> None:
    result = await RecorderFS().read("/f.txt", columns=123)  # ty: ignore[invalid-argument-type]
    assert result.errors[0].kind is ErrorKind.invalid


async def test_a_non_authority_value_is_invalid_not_unauthenticated() -> None:
    result = await RecorderFS().read("/f.txt", authority="alice")  # ty: ignore[invalid-argument-type]
    assert result.errors[0].kind is ErrorKind.invalid
    assert "must be an Authority" in result.errors[0].message


async def test_unauthenticated_is_its_own_kind_beside_permission_denied() -> None:
    assert ErrorKind.unauthenticated.value == "vfs.unauthenticated"
    assert ErrorKind.unauthenticated is not ErrorKind.permission_denied


# ---------------------------------------------------------------------------
# Storage always receives an authority
# ---------------------------------------------------------------------------


async def test_the_default_authority_reaches_storage() -> None:
    storage = RecorderStorage()
    fs = AsyncVirtualFileSystem(storage=storage, default_authority=SYSTEM)
    assert (await fs.read("/f.txt")).success is True
    assert seen(storage) == [("read", SYSTEM)]


async def test_an_explicit_authority_beats_the_default() -> None:
    storage = RecorderStorage()
    fs = AsyncVirtualFileSystem(storage=storage, default_authority=SYSTEM)
    await fs.read("/f.txt", authority=ALICE)
    assert seen(storage) == [("read", ALICE)]


def test_a_system_default_is_warned_of_once_when_the_file_system_is_made(caplog: pytest.LogCaptureFixture) -> None:
    # The sync face builds one kernel, so it warns once too, never twice.
    with caplog.at_level(logging.DEBUG, logger="vfs"):
        AsyncVirtualFileSystem(storage=RecorderStorage(), default_authority=SYSTEM)
        with VirtualFileSystem(storage=InMemoryStorage(), default_authority=SYSTEM):
            pass
    warnings = [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert [record.name for record in warnings] == ["vfs.authority", "vfs.authority"]


def test_a_kernel_that_cannot_be_made_warns_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="vfs"), pytest.raises(ValueError):
        AsyncVirtualFileSystem(storage=RecorderStorage(), default_authority=SYSTEM, deny_ops={"read"})
    assert caplog.records == []


async def test_locate_that_asks_no_storage_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    fs = RecorderFS(default_authority=SYSTEM)
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="vfs"):
        await fs.locate("/f.txt")
    assert caplog.records == []


@pytest.mark.parametrize("default", [None, ALICE, ANON], ids=["none", "alice", "anon"])
def test_no_other_default_warns(default: Authority | None, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="vfs"):
        AsyncVirtualFileSystem(storage=RecorderStorage(), default_authority=default)
    assert caplog.records == []


async def test_each_call_that_falls_back_to_the_default_logs_at_debug_and_no_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage(), default_authority=SYSTEM)
    secret = "the body of a file, which no log record carries"
    caplog.clear()  # the warning as the kernel is made is the test above's
    with caplog.at_level(logging.DEBUG, logger="vfs"):
        assert (await fs.write(path="/f.txt", content=secret)).success is True
        assert (await fs.read("/f.txt", authority=ALICE)).success is True
    [record] = caplog.records
    assert record.levelno == logging.DEBUG and "write" in record.getMessage()
    assert secret not in record.getMessage()


async def test_the_authority_is_threaded_not_cached() -> None:
    # Two calls, two authorities: each dispatch carries its own value.
    storage = RecorderStorage()
    fs = AsyncVirtualFileSystem(storage=storage)
    bob = Authority.of(Principal("bob"))
    await fs.read("/f.txt", authority=ALICE)
    await fs.read("/f.txt", authority=bob)
    assert seen(storage) == [("read", ALICE), ("read", bob)]


# ---------------------------------------------------------------------------
# A declared owner
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("owner", ["*", "anon", "system", "group:eng", "", "   "])
@pytest.mark.parametrize("authority", [SYSTEM, ALICE, None], ids=["system", "alice", "none"])
async def test_a_reserved_owner_refuses_the_whole_write_before_any_storage(
    owner: str, authority: Authority | None
) -> None:
    fs = RecorderFS()
    entries = [
        Entry(path=Path("/ok.txt"), content="a"),
        Entry(path=Path("/f.txt"), content="a", owner_id=owner),
    ]
    result = await fs.write(entries=entries, authority=authority)
    assert result.success is False
    [error] = result.errors
    assert (error.kind, error.path) == (ErrorKind.invalid, "/f.txt")
    assert repr(owner) in error.message
    assert fs.calls == []


async def test_any_other_declared_owner_reaches_the_storage() -> None:
    fs = RecorderFS()
    entry = Entry(path=Path("/f.txt"), content="a", owner_id="carol")
    assert (await fs.write(entries=[entry], authority=SYSTEM)).success is True
    [(op, kwargs)] = fs.calls
    assert op == "write" and [e.owner_id for e in kwargs["entries"]] == ["carol"]


async def test_a_mount_change_makes_its_directory_as_the_caller_and_does_its_own_work_as_the_system_actor() -> None:
    # The caller makes the mount-point directory, as their own mkdir would. The check of the mount
    # point and the delete of its directory are the kernel's own work, whoever the caller is.
    storage = RecordingMemory()
    fs = AsyncVirtualFileSystem(storage=storage, default_authority=ALICE)
    await fs.add_mount(RecorderStorage(name="child"), "/m", parents=True)
    await fs.remove_mount("/m")
    assert set(storage.seen) == {("mkdir", ALICE), ("stat", SYSTEM), ("ls", SYSTEM), ("delete", SYSTEM)}
    await fs.close()


async def test_locate_probes_existence_as_the_caller_not_the_system() -> None:
    # A caller must not learn through locate that a row it cannot see
    # exists: the probe runs as the caller, else the default, else anonymous.
    storage = RecordingMemory()
    fs = AsyncVirtualFileSystem(storage=storage, default_authority=ALICE)
    bob = Authority.of(Principal("bob"))
    await fs.locate("/x", exists=True, authority=bob)
    await fs.locate_edge("/x", "/y", exists=True)
    await fs.locate("/x")
    assert storage.seen == [("stat", bob), ("stat", ALICE), ("stat", ALICE)]
    await fs.close()


# ---------------------------------------------------------------------------
# The session facade
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("op", sorted(ALL_OPS))
async def test_a_session_verb_is_the_direct_call_with_the_authority_filled_in(op: Op) -> None:
    direct_storage, session_storage = RecorderStorage(), RecorderStorage()
    direct = AsyncVirtualFileSystem(storage=direct_storage)
    routed = AsyncVirtualFileSystem(storage=session_storage)
    expected = await getattr(direct, op)(**CALLS[op], authority=ALICE)
    async with routed.open_session(ALICE) as s:
        assert s.authority == ALICE and s.closed is False
        result = await getattr(s, op)(**CALLS[op])
    assert result == expected
    assert seen(session_storage) == seen(direct_storage)
    assert all(authority == ALICE for _op, authority in seen(session_storage))


@pytest.mark.parametrize("op", sorted(ALL_OPS))
def test_session_verbs_take_no_identity_argument(op: Op) -> None:
    # The session signature is the verb's, minus the authority, so the two
    # surfaces cannot drift apart silently.
    fs_params = dict(inspect.signature(getattr(AsyncVirtualFileSystem, op)).parameters)
    session_params = dict(inspect.signature(getattr(AsyncSession, op)).parameters)
    assert "authority" not in session_params
    del fs_params["authority"]
    assert [(n, p.kind, p.default) for n, p in fs_params.items()] == [
        (n, p.kind, p.default) for n, p in session_params.items()
    ]


@pytest.mark.parametrize("op", sorted(ALL_OPS))
async def test_a_closed_session_refuses_and_dispatches_nothing(op: Op) -> None:
    storage = RecorderStorage()
    fs = AsyncVirtualFileSystem(storage=storage)
    async with fs.open_session(ALICE) as s:
        pass
    assert s.closed is True
    result = await getattr(s, op)(**CALLS[op])
    assert result.success is False
    assert result.errors[0].kind is ErrorKind.invalid
    assert "closed" in result.errors[0].message
    assert storage.calls == []


async def test_closed_is_final() -> None:
    fs = AsyncVirtualFileSystem(storage=RecorderStorage())
    s = fs.open_session(ALICE)
    await s.close()
    await s.close()  # idempotent
    with pytest.raises(ValueError, match="cannot reopen"):
        async with s:
            pass


@pytest.mark.parametrize("face", [AsyncSession, Session])
def test_a_session_cannot_reach_a_mount(face: type) -> None:
    # A mount carries its storage, and reaching the storage would go around
    # permissions: a session is the verbs, cli and its own lifecycle, nothing else.
    public = {name for name in dir(face) if not name.startswith("_")}
    assert public == ALL_OPS | {"authority", "closed", "close", "cli"}
    for name in sorted(public):
        member = inspect.getattr_static(face, name)
        returns = inspect.signature(member.fget if isinstance(member, property) else member).return_annotation
        assert returns in {"Result", "LineResult", "Authority", "bool", "None"}, name


async def test_a_session_needs_no_default_on_the_filesystem() -> None:
    storage = RecorderStorage()
    fs = AsyncVirtualFileSystem(storage=storage)
    async with fs.open_session(ALICE) as s:
        assert (await s.ls("/")).success is True
    assert seen(storage) == [("ls", ALICE)]


# ---------------------------------------------------------------------------
# One construction site
# ---------------------------------------------------------------------------


def test_only_the_authority_module_constructs_the_types_bare() -> None:
    # The three classmethods and the edge factory are the construction
    # doors; a bare ``Authority(`` or a system-kind ``Principal(`` anywhere
    # else in src/ is a new door nobody agreed to.
    package = pathlib.Path(vfs.authority.__file__).parent
    bare = re.compile(r"(?<![\w.])Authority\(|Principal\([^)]*kind=\"(system|anonymous)\"")
    offenders = [
        f"{path.relative_to(package)}:{n}"
        for path in sorted(package.rglob("*.py"))
        if path.name != "authority.py"
        for n, line in enumerate(path.read_text().splitlines(), start=1)
        if bare.search(line)
    ]
    assert offenders == []
