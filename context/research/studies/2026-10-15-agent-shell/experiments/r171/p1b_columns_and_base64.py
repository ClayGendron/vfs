"""Probe 1b for the spec 171 review: what resources/read's planned
`read(path, columns={"data"})` returns for a text row and a bytes row, and
which base64 alphabet the Observation serializer uses.

Run from the repo root:
    uv run python context/research/studies/2026-10-15-agent-shell/experiments/r171/p1b_columns_and_base64.py
"""

from __future__ import annotations

import asyncio
import base64
import json

import pydantic

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.models.entry import Observation


async def main() -> None:
    print("pydantic", pydantic.VERSION)
    fs = VirtualFileSystem()
    sysa = Authority.system()
    blob = bytes(range(250, 256)) * 3  # bytes whose base64 needs '+' or '/'
    await fs.write(path="/t/a.md", content="# hello\n", parents=True, authority=sysa)
    await fs.write(path="/t/b.bin", data=blob, parents=True, authority=sysa)
    for path in ("/t/a.md", "/t/b.bin"):
        for cols in ({"data"}, {"data", "mime_type"}, {"data", "content", "mime_type", "kind", "version"}):
            r = await fs.read(path, columns=frozenset(cols), authority=sysa)
            o = r.first()
            print(f"read {path} columns={sorted(cols)}: success={r.success} errors={[str(e.kind) for e in r.errors]}"
                  f" populated={sorted(o.populated) if o else None}"
                  f" content={o.content!r} data_len={len(o.data) if o and o.data else None}"
                  f" mime={o.mime_type if o else None}")
    row = Observation(path="/t/b.bin", data=blob)
    wire = json.loads(row.model_dump_json())["data"]
    print("\nObservation JSON data:", wire)
    print("standard base64       :", base64.b64encode(blob).decode())
    print("urlsafe base64        :", base64.urlsafe_b64encode(blob).decode())
    try:
        ok = base64.b64decode(wire, validate=True) == blob
    except Exception as exc:  # noqa: BLE001
        ok = f"{type(exc).__name__}: {exc}"
    print("strict standard decode of the serializer's output:", ok)


asyncio.run(main())
