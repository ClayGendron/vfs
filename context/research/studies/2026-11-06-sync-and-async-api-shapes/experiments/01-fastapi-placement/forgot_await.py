"""Placement e for a type checker: an async verb called without await inside async def."""

from __future__ import annotations

from vfs import VirtualFileSystem


async def endpoint(fs: VirtualFileSystem) -> dict[str, str]:
    fs.read("/a.txt")
    result = fs.read("/a.txt")
    return {"text": str(result)}
