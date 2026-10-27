"""S8 probe: what the live vfs tree does today with a bytes-bearing Observation
at the two projections — the text renderer (`to_str`) and the MCP structured
payload (`to_payload`). Run from the repo root with `uv run python -I <this file>`.
"""

from __future__ import annotations

import base64
import json

from vfs.models.entry import Observation
from vfs.results.envelope import Result

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)

text_row = Observation(path="/notes/a.md", kind="file", content="# hello\n", mime_type="text/markdown", size_bytes=8, version=1)
bytes_row = Observation(path="/photos/pixel.png", kind="file", data=PNG_1X1, mime_type="image/png", size_bytes=len(PNG_1X1), version=3)
result = Result(ops=("read",), observations=[text_row, bytes_row])

print("populated on bytes row:", sorted(bytes_row.populated))
print("\n--- to_str() default projection ---")
print(repr(result.to_str()))
print("\n--- to_str(projection=('path','mime_type','size_bytes')) ---")
print(result.to_str(projection=("path", "mime_type", "size_bytes")))
payload = result.to_payload()
print("\n--- to_payload() bytes row ---")
print(json.dumps(payload["observations"][1], indent=1))
print("\nround trip equal:", Result.from_payload(payload).observations[1].data == PNG_1X1)
print("payload bytes for a 1 MiB image would be about", len(base64.b64encode(b"x" * (1 << 20))), "chars of base64")
