"""Identity through the router: absence is anonymous by name, the default
is a named privilege, storage always receives an authority, the control
plane runs as the system actor, and the session is sugar over the funnel."""

from __future__ import annotations

import inspect
import pathlib
import re
from typing import Any

import pytest

import vfs.authority
from tests.support.base_doubles import RecorderFS, RecorderStorage
from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem
from vfs.ops import ALL_OPS, Op
from vfs.results import Result, VFSErrorKind
from vfs.session import Session
from vfs.storage.backends.memory import InMemoryStorage

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
    "glean": {"query": "x"},
    "graph": {"method": "successors", "path": "/f.txt"},
    "run": {"path": "/t"},
    "grant": {"path": "/d", "principal": "bob", "level": "read"},
    "revoke": {"path": "/d", "principal": "bob"},
    "grants": {"path": "/d"},
    "posture": {"path": "/d", "posture": "shared"},
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
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_a_non_authority_value_is_invalid_not_unauthenticated() -> None:
    result = await RecorderFS().read("/f.txt", authority="alice")  # ty: ignore[invalid-argument-type]
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert "must be an Authority" in result.errors[0].message


async def test_unauthenticated_is_its_own_kind_beside_permission_denied() -> None:
    assert VFSErrorKind.unauthenticated.value == "vfs.unauthenticated"
    assert VFSErrorKind.unauthenticated is not VFSErrorKind.permission_denied


# ---------------------------------------------------------------------------
# Storage always receives an authority
# ---------------------------------------------------------------------------


async def test_the_default_authority_reaches_storage() -> None:
    storage = RecorderStorage()
    fs = VirtualFileSystem(storage=storage, default_authority=SYSTEM)
    assert (await fs.read("/f.txt")).success is True
    assert seen(storage) == [("read", SYSTEM)]


async def test_an_explicit_authority_beats_the_default() -> None:
    storage = RecorderStorage()
    fs = VirtualFileSystem(storage=storage, default_authority=SYSTEM)
    await fs.read("/f.txt", authority=ALICE)
    assert seen(storage) == [("read", ALICE)]


async def test_the_authority_is_threaded_not_cached() -> None:
    # Two calls, two authorities: each dispatch carries its own value.
    storage = RecorderStorage()
    fs = VirtualFileSystem(storage=storage)
    bob = Authority.of(Principal("bob"))
    await fs.read("/f.txt", authority=ALICE)
    await fs.read("/f.txt", authority=bob)
    assert seen(storage) == [("read", ALICE), ("read", bob)]


async def test_the_control_plane_runs_as_the_system_actor() -> None:
    # Mount administration is the router's own work: the bind-site
    # probes and the mount-point mkdir and rmdir run as the system
    # actor, whatever default or caller is configured.
    storage = RecordingMemory()
    fs = VirtualFileSystem(storage=storage, default_authority=ALICE)
    await fs.add_mount(RecorderStorage(name="child"), "/m", parents=True)
    await fs.remove_mount("/m")
    assert storage.seen and all(authority == SYSTEM for _op, authority in storage.seen)
    assert {op for op, _ in storage.seen} == {"mkdir", "stat", "ls", "delete"}
    await fs.close()


async def test_locate_probes_existence_as_the_caller_not_the_system() -> None:
    # A caller must not learn through locate that a row it cannot see
    # exists: the probe runs as the caller, else the default, else anonymous.
    storage = RecordingMemory()
    fs = VirtualFileSystem(storage=storage, default_authority=ALICE)
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
    direct = VirtualFileSystem(storage=direct_storage)
    routed = VirtualFileSystem(storage=session_storage)
    expected = await getattr(direct, op)(**CALLS[op], authority=ALICE)
    async with routed.session(ALICE) as s:
        assert s.authority == ALICE and s.closed is False
        result = await getattr(s, op)(**CALLS[op])
    assert result == expected
    assert seen(session_storage) == seen(direct_storage)
    assert all(authority == ALICE for _op, authority in seen(session_storage))


@pytest.mark.parametrize("op", sorted(ALL_OPS))
def test_session_verbs_take_no_identity_argument(op: Op) -> None:
    # The session signature is the verb's, minus the authority, so the two
    # surfaces cannot drift apart silently.
    fs_params = dict(inspect.signature(getattr(VirtualFileSystem, op)).parameters)
    session_params = dict(inspect.signature(getattr(Session, op)).parameters)
    assert "authority" not in session_params
    del fs_params["authority"]
    assert [(n, p.kind, p.default) for n, p in fs_params.items()] == [
        (n, p.kind, p.default) for n, p in session_params.items()
    ]


@pytest.mark.parametrize("op", sorted(ALL_OPS))
async def test_a_closed_session_refuses_and_dispatches_nothing(op: Op) -> None:
    storage = RecorderStorage()
    fs = VirtualFileSystem(storage=storage)
    async with fs.session(ALICE) as s:
        pass
    assert s.closed is True
    result = await getattr(s, op)(**CALLS[op])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert "closed" in result.errors[0].message
    assert storage.calls == []


async def test_closed_is_final() -> None:
    fs = VirtualFileSystem(storage=RecorderStorage())
    s = fs.session(ALICE)
    await s.close()
    await s.close()  # idempotent
    with pytest.raises(ValueError, match="cannot reopen"):
        async with s:
            pass


async def test_a_session_needs_no_default_on_the_filesystem() -> None:
    storage = RecorderStorage()
    fs = VirtualFileSystem(storage=storage)
    async with fs.session(ALICE) as s:
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
