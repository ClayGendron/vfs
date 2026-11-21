"""The mount listing on its own: finding the mount that holds a path, counted in the work it does.

The rules for what a listing shows at a mount point are pinned through the kernel, in
``tests/base/test_mount_listing.py``.
"""

from __future__ import annotations

import pytest

from tests.support.base_doubles import BindableStorage
from vfs import listing as listing_module
from vfs import paths as paths_module
from vfs.mounts import Mount
from vfs.paths import Path


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
