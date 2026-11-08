"""The namespaces the both-shapes rows run against: composed scope against the scope channel.

The router composes every arm under every owned root up to its
composition limit and sends the roots beside the arms past it, so one
call can be asked twice, once per shape, by patching the limit to ``0``
and to ``10**9``. The worlds here hold what makes the two shapes differ
if either is wrong: a mount at ``/m`` with a second mount beneath
``/m/p000``, nested and metacharacter roots, tombstoned directories
under the root entry's trash view, and two posture worlds whose mount
root is private to everyone.

The worlds cost thousands of rows and 603 posture changes, so they are
built once per test session into SQLite files (:func:`build_world_files`,
under :func:`~tests.support.shared_builds.build_once`), and each module
opens its own copies of the files (:func:`open_worlds`), mounted as the
build mounted them, so no two processes ever write one file.

    shared = shared_directory(tmp_path_factory)
    source = Path(build_once(shared, "scope-worlds", build_world_files))
    worlds = await open_worlds(source, tmp_path_factory.mktemp("worlds"))
"""

from __future__ import annotations

import asyncio
import shutil
from typing import TYPE_CHECKING, NamedTuple

from vfs.authority import Authority
from vfs.base import AsyncVirtualFileSystem
from vfs.models import Entry, Observation
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

if TYPE_CHECKING:
    import pathlib

    from vfs.results import Result

# The plain directories of the mount at /m, each holding DIRECTORY_FILES.
DIRECTORIES: tuple[str, ...] = tuple(f"/m/d{i:03}" for i in range(250))
DIRECTORY_FILES = ("a.py", "b.txt", "src/c.py", "src/d.md", "test_e.py", "a/f.txt", "b/g.txt")

# The directory holding the nested mount, and the nested mount's own files.
NESTED_HOST = "/m/p000"
NESTED_MOUNT = "/m/p000/sub"
NESTED_FILES = ("s.py", "src/t.py", "test_u.py")

# Directories whose names hold the pattern language's metacharacters.
METACHAR_DIRECTORIES: tuple[str, ...] = tuple(
    f"/m/k{char}{i:03}" for char, count in (("[", 84), ("*", 83), ("{", 83)) for i in range(count)
)
METACHAR_FILES = ("a1.txt", "b2.py", "c3.md")

# Directories of the root entry, deleted whole, so they answer under its trash view.
TRASHED: tuple[str, ...] = tuple(f"/t{i:03}" for i in range(250))
TRASHED_FILES = ("x.txt", "y.py")
TRASH_ROOTS: tuple[str, ...] = tuple(f"/.vfs/trash{path}" for path in TRASHED)

# The posture worlds' directories: each holds a.py and src/c.py.
POSTURE_DIRECTORIES: tuple[str, ...] = tuple(f"/m/d{i:03}" for i in range(201))

# Each world's mounts, in mounting order, each a SQLite file named by its position.
WORLD_MOUNTS: dict[str, tuple[str, ...]] = {
    "main": ("/", "/m", NESTED_MOUNT),
    "private_roots": ("/", "/m"),
    "private_src": ("/", "/m"),
}

_SYSTEM = Authority.system()


class ShapeWorlds(NamedTuple):
    """The main world and the two posture worlds: roots private with ``src`` public, and the reverse."""

    main: AsyncVirtualFileSystem
    private_roots: AsyncVirtualFileSystem
    private_src: AsyncVirtualFileSystem


class ShapeCall(NamedTuple):
    """One scoped call asked of both shapes: its verb, subject, scope roots, world and keywords."""

    name: str
    verb: str
    subject: str
    paths: tuple[str, ...]
    world: str = "main"
    options: tuple[tuple[str, object], ...] = ()

    async def run(self, worlds: ShapeWorlds) -> Result:
        """The call against its world, as the anonymous caller every world's posture judges."""
        fs = getattr(worlds, self.world)
        verb = getattr(fs, self.verb)
        return await verb(self.subject, paths=self.paths, **dict(self.options))


def build_world_files(directory: pathlib.Path) -> str:
    """Build the three worlds into SQLite files under *directory*, on a loop of their own; answers the directory."""
    asyncio.run(_build_worlds(directory))
    return str(directory)


async def open_worlds(source: pathlib.Path, target: pathlib.Path) -> ShapeWorlds:
    """The worlds built under *source*, opened from copies under *target*, each mounted as the build mounted it."""
    opened: dict[str, AsyncVirtualFileSystem] = {}
    for world, mounts in WORLD_MOUNTS.items():
        (target / world).mkdir()
        for index in range(len(mounts)):
            for built in (source / world).glob(f"{index}.sqlite*"):
                shutil.copy(built, target / world / built.name)
        opened[world] = await _mounted(target / world, mounts)
    return ShapeWorlds(**opened)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _build_worlds(directory: pathlib.Path) -> None:
    """Every world built and closed, its files left whole under *directory*."""
    for world, mounts in WORLD_MOUNTS.items():
        (directory / world).mkdir()
        fs = await _mounted(directory / world, mounts)
        try:
            if world == "main":
                await _fill_main_world(fs)
            else:
                await _fill_posture_world(fs, private_roots=world == "private_roots")
        finally:
            await fs.close()


async def _mounted(directory: pathlib.Path, mounts: tuple[str, ...]) -> AsyncVirtualFileSystem:
    """A namespace over the world's files under *directory*: the first at ``/``, the rest mounted in order."""
    [root, *rest] = mounts
    fs = AsyncVirtualFileSystem(storage=_storage(directory, 0))
    assert root == "/"
    for index, mount in enumerate(rest, start=1):
        await fs.add_mount(_storage(directory, index), mount, parents=True)
    return fs


def _storage(directory: pathlib.Path, index: int) -> DatabaseStorage:
    return DatabaseStorage(url=f"sqlite+aiosqlite:///{directory}/{index}.sqlite")


async def _fill_main_world(fs: AsyncVirtualFileSystem) -> None:
    """The main world's rows: the plain, nested-host, metacharacter and trashed directories, the nested mount's own."""
    rows = [*_files(DIRECTORIES, DIRECTORY_FILES), *_files(METACHAR_DIRECTORIES, METACHAR_FILES)]
    rows += [*_files((NESTED_HOST,), ("a.py", "src/c.py")), *_files(("/m",), ("top.py",))]
    rows += [*_files(TRASHED, TRASHED_FILES), *_files(("/",), ("live.txt",))]
    rows += _files((NESTED_MOUNT,), NESTED_FILES)
    assert (await fs.write(entries=rows, parents=True, authority=_SYSTEM)).success is True
    gone = [Observation(path=Path(path)) for path in TRASHED]
    assert (await fs.delete(observations=gone, authority=_SYSTEM)).success is True


async def _fill_posture_world(fs: AsyncVirtualFileSystem, *, private_roots: bool) -> None:
    """A world whose ``/m`` mount root is private to everyone, its roots and their ``src`` postured apart.

    With *private_roots* each root is private and its ``src`` public;
    without, each root is public and its ``src`` private.
    """
    rows = list(_files(POSTURE_DIRECTORIES, ("a.py", "src/c.py")))
    assert (await fs.write(entries=rows, parents=True, authority=_SYSTEM)).success is True
    assert (await fs.posture("/m", "none", authority=_SYSTEM)).success is True
    root_level, src_level = ("none", "read") if private_roots else ("read", "none")
    for root in POSTURE_DIRECTORIES:
        if root_level != "none":
            assert (await fs.posture(root, root_level, authority=_SYSTEM)).success is True
        assert (await fs.posture(f"{root}/src", src_level, authority=_SYSTEM)).success is True


def _files(directories: tuple[str, ...], names: tuple[str, ...]) -> list[Entry]:
    """One entry per directory and name, its body the grep needle and its own path."""
    base = (directory.rstrip("/") for directory in directories)
    return [Entry(path=Path(f"{root}/{name}"), content=f"needle {root}/{name}") for root in base for name in names]
