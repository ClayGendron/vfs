"""The grant verbs through the router — routing, rebasing, gating, rendering.

A grant addresses a prefix, not a row: the router resolves the mount
holding the path, hands the backend its storage-local path, and rebases
the ``grants=`` rows it answers with back to router coordinates. The
writing grant verbs pass the mount's permission layers like any
mutation; listing grants does not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.support.base_doubles import BindableStorage, ReadFamilyStorage, RecorderFS, RecorderStorage
from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem
from vfs.models import Entry
from vfs.paths import Path
from vfs.results import Result, VFSErrorKind
from vfs.results.render import render_result
from vfs.storage.backends.memory import InMemoryStorage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

SYSTEM = Authority.system()
ANN = Authority.of(Principal("ann"))


@pytest.fixture
async def fs() -> AsyncIterator[VirtualFileSystem]:
    """A root mount with a grant-capable child at ``/m`` holding ``/m/eng/spec.md``."""
    fs = VirtualFileSystem(storage=InMemoryStorage(), default_authority=SYSTEM)
    child = InMemoryStorage()
    await fs.add_mount(child, "/m")
    assert (await fs.write(path="/m/eng/spec.md", content="x", parents=True)).success is True
    yield fs
    await fs.close()


# ---------------------------------------------------------------------------
# Routing and rebasing
# ---------------------------------------------------------------------------


async def test_a_grant_reaches_its_mount_with_the_storage_local_path() -> None:
    fs = RecorderFS(storage=BindableStorage())
    await fs.add_mount(RecorderStorage(name="child"), "/m")
    child = fs._bindings[Path("/m")].storage
    assert isinstance(child, RecorderStorage)
    await fs.grant("/m/eng", "bob", "read")
    assert child.calls[-1] == ("grant", {"path": "/eng", "principal": "bob", "level": "read"})


async def test_membership_verbs_carry_no_path_to_storage() -> None:
    fs = RecorderFS()
    await fs.add_member("group:eng", "bob")
    assert fs.calls[-1] == ("add_member", {"group": "group:eng", "member": "bob"})


async def test_listed_grant_rows_come_back_in_router_coordinates(fs: VirtualFileSystem) -> None:
    granted = await fs.grant("/m/eng", "ann", "read")
    assert granted.success is True
    assert [row["path_prefix"] for row in _granted(granted)] == ["/m/eng"]
    listed = await fs.grants("/m/eng/spec.md")
    assert {row["path_prefix"] for row in _granted(listed)} == {"/m", "/m/eng"}


async def test_a_grant_on_the_root_mount_needs_no_rebase(fs: VirtualFileSystem) -> None:
    result = await fs.posture("/", "shared")
    assert result.success is True
    assert _granted(result)[0]["path_prefix"] == "/"


async def test_the_grant_takes_effect_for_the_next_routed_read(fs: VirtualFileSystem) -> None:
    assert (await fs.posture("/m", "private")).success is True
    assert (await fs.read("/m/eng/spec.md", authority=ANN)).errors[0].kind == VFSErrorKind.not_found
    assert (await fs.grant("/m/eng", "ann", "read")).success is True
    assert (await fs.read("/m/eng/spec.md", authority=ANN)).success is True


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


async def test_a_read_only_mount_refuses_grant_writes_but_lists(fs: VirtualFileSystem) -> None:
    await fs.remount("/m", permissions="read")
    for refused in (
        await fs.grant("/m/eng", "ann", "read"),
        await fs.revoke("/m/eng", "ann"),
        await fs.posture("/m", "private"),
        await fs.add_member("group:eng", "ann", path="/m"),
        await fs.remove_member("group:eng", "ann", path="/m"),
    ):
        assert refused.errors[0].kind == VFSErrorKind.read_only
    assert (await fs.grants("/m/eng")).success is True


async def test_a_backend_without_grants_is_unsupported() -> None:
    fs = VirtualFileSystem(storage=ReadFamilyStorage())
    result = await fs.grant("/x", "bob", "read")
    assert result.errors[0].kind == VFSErrorKind.unsupported


async def test_a_closed_filesystem_refuses_grants() -> None:
    fs = VirtualFileSystem()
    await fs.close()
    result = await fs.grants("/x")
    assert result.success is False


async def test_an_invalid_grant_path_is_refused_before_dispatch() -> None:
    fs = RecorderFS()
    result = await fs.grant("/bad\x00name", "bob", "read")
    assert result.success is False
    assert fs.calls == []


@pytest.mark.parametrize(
    "call",
    [
        lambda fs: fs.grant("/d", "bob", "none"),
        lambda fs: fs.grant("/d", "bob", "admin"),
        lambda fs: fs.grant("/d", 7, "read"),
        lambda fs: fs.grant(None, "bob", "read"),
        lambda fs: fs.posture("/d", "public"),
        lambda fs: fs.add_member("group:eng", None),
        lambda fs: fs.remove_member(3, "bob"),
        lambda fs: fs.revoke("/d", 7),
        lambda fs: fs.grants(None),
    ],
)
async def test_garbage_grant_parameters_are_invalid_with_zero_dispatch(call) -> None:
    fs = RecorderFS()
    result = await call(fs)
    assert result.errors[0].kind == VFSErrorKind.invalid
    assert fs.calls == []


# ---------------------------------------------------------------------------
# Rendering and names
# ---------------------------------------------------------------------------


async def test_grant_rows_render_as_a_table(fs: VirtualFileSystem) -> None:
    await fs.grant("/m/eng", "ann", "read")
    text = render_result(await fs.grants("/m/eng"))
    assert "principal_id" in text and "/m/eng" in text and "ann" in text
    revoked = render_result(await fs.revoke("/m/eng", "ann"))
    assert "none" in revoked


def test_a_grant_answer_with_no_rows_says_so() -> None:
    assert render_result(Result(ops=("grants",), grants=[])) == "No grants"
    assert render_result(Result(ops=("add_member",), members=[{"group_id": "group:e", "principal_id": "a"}]))
    assert render_result(Result(ops=("grant",))) == "No changes"


@pytest.mark.parametrize("sub", ["*", "group:eng"])
def test_a_principal_may_not_take_a_grant_row_name(sub: str) -> None:
    with pytest.raises(ValueError, match="name grant rows"):
        Principal(sub)


async def test_writes_through_the_router_stamp_the_caller_as_owner(fs: VirtualFileSystem) -> None:
    # Under a private mount, ann's own file stays hers to read.
    assert (await fs.posture("/m", "private")).success is True
    assert (await fs.grant("/m/eng", "ann", "read_write")).success is True
    await fs.write([Entry(path=Path("/m/eng/mine.md"), content="x")], authority=ANN)
    assert (await fs.revoke("/m/eng", "ann")).success is True
    assert (await fs.read("/m/eng/mine.md", authority=ANN)).success is True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _granted(result: Result) -> list[dict[str, object]]:
    """The ``grants=`` rows a grant verb answered with."""
    rows = (result.model_extra or {}).get("grants")
    assert isinstance(rows, list), result
    return rows
