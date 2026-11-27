"""A vid mint for tests that build rows without a storage of their own."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from ulid import ULID

from vfs.vid import VidMint

if TYPE_CHECKING:
    from vfs.paths import Path
    from vfs.results import Result

TEST_MINT: Final = VidMint(str(ULID()))
"""A mint over an identity of its own, for plans and builders a test calls with no storage behind them."""


def vid_in(result: Result) -> str:
    """The vid of the one row *result* holds; a row with a version always has one."""
    vid = result.one().vid
    assert vid is not None
    return vid


def vids_in(result: Result) -> dict[Path, str]:
    """The vid of each row *result* holds, by its path; every row must carry one."""
    vids = {row.path: row.vid for row in result.observations}
    assert None not in vids.values()
    return {path: vid for path, vid in vids.items() if vid is not None}
