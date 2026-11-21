"""The mount listing on its own: finding the mounts at, above and beneath a path, counted in the work it does.

The rules for what a listing shows at a mount point are pinned through the kernel, in
``tests/base/test_mount_listing.py``.
"""

from __future__ import annotations

import random

import pytest

from tests.support.base_doubles import BindableStorage
from vfs import listing as listing_module
from vfs import paths as paths_module
from vfs.mounts import Mount
from vfs.paths import Path

# Names that sort next to "/" on either side, so a search by prefix that is off by one shows.
NEIGHBOURS = ("a", "a-b", "a.b", "a0", "a/b", "a/b/c", "a/b-c", "a/b0", "b", "b/a", "ab", "a/ba")


def _oracle_beneath(table: dict[Path, Mount], path: Path) -> list[Mount]:
    return [mount for key, mount in table.items() if key != path and (path == "/" or key.startswith(path + "/"))]


def _oracle_governing(table: dict[Path, Mount], path: Path) -> list[Mount]:
    found = [mount for key, mount in table.items() if key == "/" or path == key or path.startswith(key + "/")]
    return sorted(found, key=lambda mount: mount.path.depth)


@pytest.mark.parametrize("seed", range(40))
def test_beneath_and_governing_agree_with_a_scan_of_the_whole_table(seed: int) -> None:
    rng = random.Random(seed)
    chosen = rng.sample(NEIGHBOURS, rng.randint(0, len(NEIGHBOURS)))
    table = {Path(path): Mount(Path(path), BindableStorage()) for path in ("/", *(f"/{name}" for name in chosen))}
    listing = listing_module.MountListing(table)
    for probe in ("/", *(f"/{name}" for name in NEIGHBOURS), "/a/b/c/d", "/zz"):
        path = Path(probe)
        assert listing.beneath(path) == _oracle_beneath(table, path), probe
        assert list(listing.governing(path)) == _oracle_governing(table, path), probe


def test_an_empty_table_is_governed_by_no_mount() -> None:
    assert listing_module.MountListing({}).governing(Path("/a")) == ()


@pytest.mark.parametrize(("mounted", "steps"), [(("/y",), 1), (("/x/x",), 2), (("/y/y/y",), 3)])
def test_the_walk_up_a_deep_path_starts_at_the_depth_of_the_deepest_mount(
    mounted: tuple[str, ...], steps: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = {Path(path): Mount(Path(path), BindableStorage()) for path in ("/", *mounted)}
    listing = listing_module.MountListing(table)
    walked: list[str] = []
    original = listing_module._parent

    def counted(path: str) -> str:
        walked.append(path)
        return original(path)

    monkeypatch.setattr(listing_module, "_parent", counted)
    governing = listing.governing(deep_path())
    assert [mount.path for mount in governing] == [path for path in table if deep_path().startswith(path)]
    assert len(walked) == steps


def deep_path() -> Path:
    """A legal path of 1,024 bytes, the longest a path may be."""
    return Path("/x" * 512)


@pytest.mark.parametrize("mounted", [(), ("/y",), ("/x/x", "/x/x/x/x", "/y")], ids=["root", "beside", "above"])
def test_finding_the_mount_that_holds_a_path_checks_no_path_again(
    mounted: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    deep = deep_path()
    table = {Path(path): Mount(Path(path), BindableStorage()) for path in ("/", *mounted)}
    listing = listing_module.MountListing(table)
    checked: list[str] = []
    original = paths_module.validate_path

    def counted(path: str) -> tuple[bool, str]:
        checked.append(path)
        return original(path)

    monkeypatch.setattr(paths_module, "validate_path", counted)
    holder = listing.holder(deep)
    assert holder is not None
    assert holder.path == max((path for path in table if path == "/" or deep.startswith(path + "/")), key=len)
    assert checked == []


@pytest.mark.parametrize(("mounted", "steps"), [((), 0), (("/y",), 512)], ids=["root alone", "beside"])
def test_a_table_that_holds_only_the_root_answers_without_walking_the_path(
    mounted: tuple[str, ...], steps: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = {Path(path): Mount(Path(path), BindableStorage()) for path in ("/", *mounted)}
    listing = listing_module.MountListing(table)
    walked: list[str] = []
    original = listing_module._parent

    def counted(path: str) -> str:
        walked.append(path)
        return original(path)

    monkeypatch.setattr(listing_module, "_parent", counted)
    holder = listing.holder(deep_path())
    assert holder is not None
    assert holder.path == "/"
    assert len(walked) == steps
