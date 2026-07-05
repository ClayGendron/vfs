"""Spike: the current inherited ``_*_impl`` seam fails at dispatch time.

``ForgetfulFS`` claims storage and full capability but never defines
``_read_impl``.  ``ty`` accepts this file without complaint — the string
seam ``getattr(self, f"_{op}_impl")`` is invisible to the type checker —
and the omission surfaces only when a ``read`` actually dispatches, as a
raw ``AttributeError`` on the impl-bug channel.

Run: ``uv run ty check <this file>`` (passes), then
``uv run python <this file>`` (crashes at dispatch).
"""

from __future__ import annotations

import asyncio

from vfs.base2 import VirtualFileSystem


class ForgetfulFS(VirtualFileSystem):
    """Storage backend that forgot every impl. The type checker cannot tell."""

    def __init__(self) -> None:
        super().__init__(name="forgetful", storage=True)


async def main() -> None:
    fs = ForgetfulFS()
    await fs.read("/anything.txt")  # AttributeError: no _read_impl — at runtime


if __name__ == "__main__":
    asyncio.run(main())
