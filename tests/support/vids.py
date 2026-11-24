"""A vid mint for tests that build rows without a storage of their own."""

from __future__ import annotations

from typing import Final

from ulid import ULID

from vfs.vid import VidMint

TEST_MINT: Final = VidMint(str(ULID()))
"""A mint over an identity of its own, for plans and builders a test calls with no storage behind them."""
