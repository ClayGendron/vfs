"""The listing cursor at the kernel: ``after=`` and ``limit=`` on ``ls``, ``tree`` and ``glob``, across mounts.

A drained listing is checked against the same listing asked whole: the same rows, in path order, none
repeated and none lost. Counts are calls on a storage, never clocks.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

import pytest

from vfs import AsyncVirtualFileSystem, InMemoryStorage
from vfs.authority import Authority, Principal
from vfs.models import Entry, Observation
from vfs.paths import Path
from vfs.results import ErrorKind, Result
from vfs.session import AsyncSession
from vfs.storage import TransportError
from vfs.sync import Session, VirtualFileSystem

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

SYSTEM = Authority.system()
ADA = Authority.of(Principal("ada"))
ANONYMOUS = Authority.anonymous()
LISTING_OPS = ("ls", "tree", "glob")


def ok(result: Result) -> Result:
    assert result.success is True, result.error_message
    return result


class Spied(InMemoryStorage):
    """An in-memory storage that records the keywords of every listing call it receives."""

    def __init__(self) -> None:
        super().__init__()
        self.listings: list[tuple[str, dict[str, Any]]] = []

    async def ls(self, **kwargs: Any) -> Result:
        self.listings.append(("ls", kwargs))
        return await super().ls(**kwargs)

    async def tree(self, **kwargs: Any) -> Result:
        self.listings.append(("tree", kwargs))
        return await super().tree(**kwargs)

    async def glob(self, **kwargs: Any) -> Result:
        self.listings.append(("glob", kwargs))
        return await super().glob(**kwargs)


class Plain(Spied):
    """A storage that cannot page by itself: it declares no ``listing_cursor``, so the kernel derives its pages."""

    def traits(self) -> Mapping[str, str]:
        return {key: value for key, value in super().traits().items() if key != "listing_cursor"}


class FailingGlob(InMemoryStorage):
    """A storage whose ``glob`` finds its far side dead."""

    async def glob(self, **kwargs: Any) -> Result:
        raise TransportError("gone")


async def drain(call: Callable[..., Awaitable[Result]], limit: int, **kwargs: Any) -> tuple[list[str], list[Result]]:
    """Every row of a listing read ``limit`` at a time, and every page."""
    pages: list[Result] = []
    after: Path | None = None
    while True:
        page = ok(await call(after=after, limit=limit, **kwargs))
        pages.append(page)
        assert len(page) <= limit
        if page.next_after is None:
            return [str(path) for path in (p for page in pages for p in page.paths)], pages
        assert after is None or page.next_after > after
        after = page.next_after
        assert len(pages) < 1_000


def files(root: str, count: int, ext: str = "txt") -> list[Entry]:
    return [Entry(path=Path(f"{root}/f{index:05d}.{ext}"), content="x") for index in range(count)]


async def layout() -> tuple[AsyncVirtualFileSystem, Spied]:
    """A root storage and a storage mounted at ``/d/m``, beside files and a deeper directory in ``/d``."""
    fs = AsyncVirtualFileSystem(storage=Spied())
    ok(await fs.write(files("/d", 23), parents=True, authority=SYSTEM))
    ok(await fs.write(files("/d/sub", 7), parents=True, authority=SYSTEM))
    ok(await fs.write(files("/d/n", 4), parents=True, authority=SYSTEM))
    ok(await fs.mkdir("/d/m", authority=SYSTEM))
    mounted = Spied()
    await fs.add_mount(mounted, "/d/m", authority=SYSTEM)
    ok(await fs.write(files("/d/m", 11), authority=SYSTEM))
    ok(await fs.write(files("/d/m/inner", 5), parents=True, authority=SYSTEM))
    return fs, mounted


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


REFUSED = [
    ("a batch ls", lambda fs: fs.ls(observations=[Observation(path=Path("/d"))], limit=10)),
    ("a glob with max_count", lambda fs: fs.glob("*", max_count=5, limit=5)),
    ("a glob over rows in hand", lambda fs: fs.glob("*", observations=[Observation(path=Path("/d"))], limit=5)),
    ("a zero limit", lambda fs: fs.ls("/d", limit=0)),
    ("a limit that is not an int", lambda fs: fs.tree("/d", limit="5")),
    ("a key that is no path", lambda fs: fs.ls("/d", after="/d/a\x00b")),
    ("an ls key outside the directory", lambda fs: fs.ls("/d", after="/e/x")),
    ("an ls key below a child", lambda fs: fs.ls("/d", after="/d/sub/f00000.txt")),
    ("an ls key at the directory", lambda fs: fs.ls("/d", after="/d")),
    ("a tree key outside the subtree", lambda fs: fs.tree("/d", after="/e/x")),
    ("a tree key at its root", lambda fs: fs.tree("/d", after="/d")),
]


@pytest.mark.parametrize(("label", "call"), REFUSED, ids=[label for label, _call in REFUSED])
async def test_a_bad_cursor_is_invalid_before_any_storage_call(label: str, call: Any) -> None:
    fs, mounted = await layout()
    root = fs._mounts[Path("/")].storage
    assert isinstance(root, Spied)
    root.listings.clear()
    result = await call(fs)
    assert not result.success, label
    assert result.errors[0].kind == ErrorKind.invalid
    assert root.listings == mounted.listings == []


async def test_a_key_in_a_mount_beneath_an_ls_target_is_a_child_there() -> None:
    fs, _mounted = await layout()
    assert ok(await fs.ls("/d/m", after="/d/m/f00003.txt", limit=2)).paths == ("/d/m/f00004.txt", "/d/m/f00005.txt")


# ---------------------------------------------------------------------------
# Drained listings equal whole ones
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [1, 3, 10, 100])
async def test_ls_pages_one_directory_with_its_mount_point(limit: int) -> None:
    fs, _mounted = await layout()
    whole = sorted(ok(await fs.ls("/d")).paths)
    assert "/d/m" in whole
    rows, pages = await drain(fs.ls, limit, path="/d")
    assert rows == whole
    assert len(pages) == max(1, -(-len(whole) // limit))


@pytest.mark.parametrize("limit", [1, 4, 25, 1000])
async def test_tree_pages_across_the_mount_beneath_it(limit: int) -> None:
    fs, _mounted = await layout()
    whole = sorted(ok(await fs.tree("/")).paths)
    assert "/d/m/inner/f00004.txt" in whole
    rows, _pages = await drain(fs.tree, limit, path="/")
    assert rows == whole


async def test_tree_under_max_depth_pages_too() -> None:
    fs, _mounted = await layout()
    whole = sorted(ok(await fs.tree("/d", max_depth=2)).paths)
    rows, _pages = await drain(fs.tree, 6, path="/d", max_depth=2)
    assert rows == whole


@pytest.mark.parametrize("pattern", ["**/*.txt", "/d/*", "f0000*", "/d/**"])
async def test_glob_pages_across_mounts(pattern: str) -> None:
    fs, _mounted = await layout()
    whole = sorted(ok(await fs.glob(pattern)).paths)
    assert whole
    rows, _pages = await drain(fs.glob, 4, pattern=pattern)
    assert rows == whole


async def test_glob_under_scope_roots_pages_too() -> None:
    fs, _mounted = await layout()
    whole = sorted(ok(await fs.glob("*.txt", paths=("/d/sub", "/d/m"))).paths)
    rows, _pages = await drain(fs.glob, 3, pattern="*.txt", paths=("/d/sub", "/d/m"))
    assert rows == whole


async def test_the_trash_head_pages_on_any_key() -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(files("/t", 9), parents=True, authority=SYSTEM))
    for index in range(0, 9, 2):
        ok(await fs.delete(f"/t/f{index:05d}.txt", authority=SYSTEM))
    whole = sorted(ok(await fs.ls("/.vfs/trash")).paths)
    assert len(whole) == 5
    rows, _pages = await drain(fs.ls, 2, path="/.vfs/trash")
    assert rows == whole


async def test_limit_alone_lists_in_path_order_and_after_alone_lists_the_rest() -> None:
    fs, _mounted = await layout()
    whole = sorted(ok(await fs.ls("/d")).paths)
    assert ok(await fs.ls("/d", limit=len(whole))).next_after is None
    rest = ok(await fs.ls("/d", after=Path(whole[4])))
    assert list(rest.paths) == whole[5:]
    assert rest.next_after is None


async def test_the_page_text_says_how_to_go_on() -> None:
    fs, _mounted = await layout()
    page = ok(await fs.ls("/d", limit=2))
    assert page.to_str().splitlines()[-1] == f"more: after={page.next_after}"


# ---------------------------------------------------------------------------
# Two mounts, each holding 1,500 files
# ---------------------------------------------------------------------------


async def two_mounts() -> tuple[AsyncVirtualFileSystem, Spied, Spied]:
    root, mounted = Spied(), Spied()
    fs = AsyncVirtualFileSystem(storage=root)
    ok(await fs.mkdir("/m", authority=SYSTEM))
    await fs.add_mount(mounted, "/m", authority=SYSTEM)
    ok(await fs.write(files("/m/a", 1_500), parents=True, authority=SYSTEM))
    ok(await fs.write(files("/z", 1_500), parents=True, authority=SYSTEM))
    return fs, root, mounted


@pytest.mark.slow
async def test_a_glob_over_two_mounts_drains_in_three_pages() -> None:
    fs, root, mounted = await two_mounts()
    root.listings.clear()
    mounted.listings.clear()
    rows, pages = await drain(fs.glob, 1_000, pattern="**/*.txt")
    assert len(pages) == 3
    assert rows == sorted(rows) and len(rows) == len(set(rows)) == 3_000
    assert [op for op, _kwargs in mounted.listings] == ["glob", "glob"]
    assert [op for op, _kwargs in root.listings] == ["glob", "glob", "glob"]


@pytest.mark.slow
async def test_a_tree_over_two_mounts_drains_whole() -> None:
    fs, _root, mounted = await two_mounts()
    whole = sorted(ok(await fs.tree("/")).paths)
    mounted.listings.clear()
    rows, pages = await drain(fs.tree, 1_000, path="/")
    assert rows == whole
    assert len(pages) == 4
    assert len(mounted.listings) == 2


async def test_a_mount_that_fails_mid_listing_is_a_warning_and_the_listing_ends() -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(files("/a", 7), parents=True, authority=SYSTEM))
    ok(await fs.mkdir("/b", authority=SYSTEM))
    await fs.add_mount(FailingGlob(), "/b", authority=SYSTEM)
    rows, pages = await drain(fs.glob, 3, pattern="**/*.txt")
    assert rows == [f"/a/f{index:05d}.txt" for index in range(7)]
    assert all(any(error.kind == ErrorKind.backend_unavailable for error in page.warnings) for page in pages)


# ---------------------------------------------------------------------------
# A storage that cannot page
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("op", "kwargs"),
    [("ls", {"path": "/p/d"}), ("tree", {"path": "/p"}), ("glob", {"pattern": "**/*.txt"})],
)
async def test_a_storage_without_the_trait_gets_no_cursor_and_the_kernel_pages_it(
    op: str, kwargs: dict[str, Any]
) -> None:
    native, plain = Spied(), Plain()
    fs = AsyncVirtualFileSystem()
    for name, storage in (("q", native), ("p", plain)):
        ok(await fs.mkdir(f"/{name}", authority=SYSTEM))
        await fs.add_mount(storage, f"/{name}", authority=SYSTEM)
        ok(await fs.write(files(f"/{name}/d", 17), parents=True, authority=SYSTEM))
    whole = sorted(ok(await getattr(fs, op)(**kwargs)).paths)
    plain_rows, _pages = await drain(getattr(fs, op), 5, **kwargs)
    assert plain_rows == whole
    assert any(row.startswith("/p/") for row in plain_rows)
    if op != "glob":
        native = {key: value.replace("/p", "/q", 1) if key == "path" else value for key, value in kwargs.items()}
        native_rows, _pages = await drain(getattr(fs, op), 5, **native)
        assert [row.replace("/q", "/p", 1) for row in native_rows] == plain_rows
    assert all("after" not in seen and "limit" not in seen for _op, seen in plain.listings)


# ---------------------------------------------------------------------------
# Who pages
# ---------------------------------------------------------------------------


async def test_an_anonymous_caller_pages_under_a_list_posture_and_is_refused_under_none() -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(files("/d", 9), parents=True, authority=SYSTEM))
    ok(await fs.set_posture("/", "list", authority=SYSTEM))
    rows, pages = await drain(fs.ls, 4, path="/d", authority=ANONYMOUS)
    assert rows == [f"/d/f{index:05d}.txt" for index in range(9)]
    assert len(pages) == 3
    ok(await fs.set_posture("/", "none", authority=SYSTEM))
    refused = await fs.ls("/d", limit=4, authority=ANONYMOUS)
    assert [error.kind for error in refused.errors] == [ErrorKind.unauthenticated]


async def test_a_named_caller_with_a_grant_on_some_files_pages_only_what_it_may_see() -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(files("/d", 40), parents=True, authority=SYSTEM))
    ok(await fs.set_posture("/", "none", authority=SYSTEM))
    for index in range(0, 40, 7):
        ok(await fs.grant(f"/d/f{index:05d}.txt", "ada", "read", authority=SYSTEM))
    whole = sorted(ok(await fs.ls("/d", authority=ADA)).paths)
    assert len(whole) == 6
    rows, pages = await drain(fs.ls, 2, path="/d", authority=ADA)
    assert rows == whole
    assert all(page.next_after is None or page.next_after in page.paths for page in pages)


# ---------------------------------------------------------------------------
# Every face takes the two arguments
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("face", [AsyncVirtualFileSystem, AsyncSession, VirtualFileSystem, Session])
@pytest.mark.parametrize("op", LISTING_OPS)
def test_every_face_takes_after_and_limit(face: type, op: str) -> None:
    parameters = inspect.signature(getattr(face, op)).parameters
    assert parameters["after"].default is None
    assert parameters["limit"].default is None
    assert parameters["after"].kind is inspect.Parameter.KEYWORD_ONLY


async def test_a_session_and_the_synchronous_face_page_alike() -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(files("/d", 5), parents=True, authority=SYSTEM))
    session = fs.open_session(SYSTEM)
    page = ok(await session.ls("/d", limit=2))
    assert page.paths == ("/d/f00000.txt", "/d/f00001.txt")
    rest = ok(await session.tree("/d", after=page.next_after))
    assert rest.paths == ("/d/f00002.txt", "/d/f00003.txt", "/d/f00004.txt")
    found = ok(await session.glob("*.txt", after=page.next_after, limit=1))
    assert found.paths == ("/d/f00002.txt",)
