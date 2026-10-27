"""S8 experiment: a one-tool MCP server returning typed content blocks, driven by
the official Python SDK client over a real stdio pipe, with every JSON-RPC line
logged by a relay process and the tool result validated against the MCP JSON
Schema of each protocol revision.

Three roles in one file:
  (no flag)          the client: spawns the relay, calls the tool, reads a resource,
                     prints the logged wire and validates it
  --relay LOG SCHEMA spawns the server and copies stdin/stdout both ways, appending
                     every line to LOG tagged by direction
  --serve            the MCP server over stdio

Run from the vfs repo root:

    uv run --with mcp --with jsonschema python -I \
        context/research/studies/2026-10-15-agent-shell/experiments/s8/mcp_blocks_experiment.py \
        ~/Git/Repos/modelcontextprotocol/schema
"""

from __future__ import annotations

import base64
import importlib.metadata
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()

# A 1x1 opaque red PNG, 67 bytes.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)
PLACEHOLDER = "[image/png 67 B /photos/pixel.png v3]"


# ---------------------------------------------------------------------------
# Server role
# ---------------------------------------------------------------------------


def serve() -> None:
    import anyio
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp_types import (
        Annotations,
        BlobResourceContents,
        CallToolResult,
        ImageContent,
        ListToolsResult,
        ReadResourceResult,
        ResourceLink,
        TextContent,
        Tool,
    )

    async def list_tools(ctx: Any, params: Any) -> ListToolsResult:
        return ListToolsResult(
            tools=[
                Tool(
                    name="read",
                    description="vfs read: rows of a Result projected onto MCP blocks",
                    input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                    output_schema={"type": "object", "properties": {"success": {"type": "boolean"}}, "required": ["success"]},
                )
            ]
        )

    async def call_tool(ctx: Any, params: Any) -> CallToolResult:
        payload = {
            "success": True,
            "ops": ["read"],
            "observations": [
                {"path": "/photos/pixel.png", "kind": "file", "mime_type": "image/png", "size_bytes": 67, "version": 3},
                {"path": "/clips/intro.mp4", "kind": "file", "mime_type": "video/mp4", "size_bytes": 10485760, "version": 1},
            ],
            "errors": [],
        }
        return CallToolResult(
            content=[
                TextContent(text="| path | mime_type | size_bytes |\n| /photos/pixel.png | image/png | 67 |\n" + PLACEHOLDER),
                ImageContent(
                    data=base64.b64encode(PNG_1X1).decode("ascii"),
                    mime_type="image/png",
                    annotations=Annotations(audience=["user", "assistant"], priority=0.5),
                    _meta={"dev.vfs/path": "/photos/pixel.png", "dev.vfs/version": 3},
                ),
                ResourceLink(
                    uri="vfs:///clips/intro.mp4",
                    name="intro.mp4",
                    description="video/mp4, 10 MiB, version 1",
                    mime_type="video/mp4",
                    size=10485760,
                ),
            ],
            structured_content=payload,
            is_error=False,
        )

    async def read_resource(ctx: Any, params: Any) -> ReadResourceResult:
        return ReadResourceResult(
            contents=[BlobResourceContents(uri=params.uri, mime_type="image/png", blob=base64.b64encode(PNG_1X1).decode("ascii"))]
        )

    server = Server(  # pyright: ignore[reportDeprecated]
        name="vfs-s8", version="0.0.0", on_list_tools=list_tools, on_call_tool=call_tool, on_read_resource=read_resource
    )

    async def main() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(main)


# ---------------------------------------------------------------------------
# Relay role: copies both directions, logs each line with its direction
# ---------------------------------------------------------------------------


def relay(log_path: str) -> None:
    child = subprocess.Popen(
        [sys.executable, "-I", str(HERE), "--serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr
    )
    assert child.stdin is not None and child.stdout is not None
    lock = threading.Lock()

    def pump(src: Any, dst: Any, tag: str) -> None:
        for line in iter(src.readline, b""):
            with lock, open(log_path, "ab") as log:
                log.write(tag.encode() + line)
            dst.write(line)
            dst.flush()
        try:
            dst.close()
        except Exception:  # noqa: BLE001
            pass

    t_in = threading.Thread(target=pump, args=(sys.stdin.buffer, child.stdin, "C>S "), daemon=True)
    t_out = threading.Thread(target=pump, args=(child.stdout, sys.stdout.buffer, "S>C "))
    t_in.start()
    t_out.start()
    t_out.join()
    child.wait()


# ---------------------------------------------------------------------------
# Client role
# ---------------------------------------------------------------------------


def validate(schema_root: Path, instance: Any, definition: str, revision: str) -> str:
    import jsonschema

    schema = json.loads((schema_root / revision / "schema.json").read_text())
    # 2025-06-18 and earlier are draft-07 and keep their definitions under "definitions".
    key = "$defs" if "$defs" in schema else "definitions"
    defs = schema[key]
    if definition not in defs:
        return f"SKIP: {revision} has no {key}/{definition}"
    wrapped = {"$ref": f"#/{key}/{definition}", key: defs}
    errors = sorted(jsonschema.Draft202012Validator(wrapped).iter_errors(instance), key=lambda e: list(e.path))
    if not errors:
        return f"VALID   {revision} $defs/{definition}"
    return f"INVALID {revision} $defs/{definition}: " + "; ".join(
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message[:110]}" for e in errors[:3]
    )


async def run_session(schema_root: Path, mode: str) -> None:
    from mcp.client.client import Client
    from mcp.client.stdio import StdioServerParameters

    log = HERE.parent / f"wire_{mode}.jsonl"
    log.unlink(missing_ok=True)
    params = StdioServerParameters(command=sys.executable, args=["-I", str(HERE), "--relay", str(log)])
    async with Client(params, mode=mode) as client:  # type: ignore[arg-type]
        negotiated = getattr(client, "protocol_version", None)
        result = await client.call_tool("read", {"path": "/photos/pixel.png"})
        read = await client.read_resource("vfs:///photos/pixel.png")
    print(f"\n=== session mode={mode!r} negotiated={negotiated!r} wire log={log.name} ===")
    print("SDK-side CallToolResult.is_error:", result.is_error, "| blocks:", [b.type for b in result.content])
    print("SDK-side ReadResourceResult contents:", [type(c).__name__ for c in read.contents])
    lines = log.read_text().splitlines()
    print(f"{len(lines)} wire lines; methods: ", [json.loads(l[4:]).get("method") for l in lines if l.startswith("C>S")])
    revisions = ["2026-07-28", "2025-11-25", "2025-06-18"]
    for line in lines:
        msg = json.loads(line[4:])
        if line.startswith("C>S") and msg.get("method") == "tools/call":
            print("\nWIRE C>S tools/call request:\n" + json.dumps(msg, indent=1))
        if line.startswith("S>C") and "result" in msg and "content" in msg["result"]:
            print("\nWIRE S>C tools/call response:\n" + json.dumps(msg, indent=1))
            for rev in revisions:
                print(validate(schema_root, msg["result"], "CallToolResult", rev))
            print(validate(schema_root, msg, "JSONRPCResponse", negotiated or "2026-07-28"))
            print(validate(schema_root, msg, "JSONRPCResultResponse", negotiated or "2026-07-28"))
        if line.startswith("S>C") and "result" in msg and "contents" in msg["result"]:
            res = dict(msg["result"])
            res["contents"] = [{**c, "blob": c["blob"][:16] + "..."} for c in res["contents"]]
            print("\nWIRE S>C resources/read response (blob elided):\n" + json.dumps(res, indent=1))
            for rev in revisions:
                print(validate(schema_root, msg["result"], "ReadResourceResult", rev))


def negative_checks(schema_root: Path) -> None:
    print("\n=== hand-built instances against the schema ===")
    cases = {
        "video block (2026-07-28)": ({"resultType": "complete", "content": [{"type": "video", "data": "AAAA", "mimeType": "video/mp4"}]}, "2026-07-28"),
        "missing resultType (2026-07-28)": ({"content": [{"type": "text", "text": "hi"}]}, "2026-07-28"),
        "missing resultType (2025-11-25)": ({"content": [{"type": "text", "text": "hi"}]}, "2025-11-25"),
        "reserved _meta prefix, schema cannot police it (2026-07-28)": ({"resultType": "complete", "content": [{"type": "text", "text": "hi", "_meta": {"io.modelcontextprotocol/x": 1}}]}, "2026-07-28"),
        "resource_link without name (2026-07-28)": ({"resultType": "complete", "content": [{"type": "resource_link", "uri": "vfs:///a"}]}, "2026-07-28"),
        "image without mimeType (2026-07-28)": ({"resultType": "complete", "content": [{"type": "image", "data": "AAAA"}]}, "2026-07-28"),
        "embedded blob resource, no mimeType (2026-07-28)": ({"resultType": "complete", "content": [{"type": "resource", "resource": {"uri": "vfs:///a.bin", "blob": "AAAA"}}]}, "2026-07-28"),
        "scalar structuredContent (2026-07-28)": ({"resultType": "complete", "content": [], "structuredContent": 42}, "2026-07-28"),
        "scalar structuredContent (2025-06-18)": ({"content": [], "structuredContent": 42}, "2025-06-18"),
        "array structuredContent (2025-06-18)": ({"content": [], "structuredContent": [1]}, "2025-06-18"),
        "annotations.priority 1.5 (2026-07-28)": ({"resultType": "complete", "content": [{"type": "text", "text": "x", "annotations": {"priority": 1.5}}]}, "2026-07-28"),
        "annotations.audience ['system'] (2026-07-28)": ({"resultType": "complete", "content": [{"type": "text", "text": "x", "annotations": {"audience": ["system"]}}]}, "2026-07-28"),
        "isError true with image block (2026-07-28)": ({"resultType": "complete", "isError": True, "content": [{"type": "image", "data": "AAAA", "mimeType": "image/png"}]}, "2026-07-28"),
    }
    for label, (instance, rev) in cases.items():
        print(f"{label}: {validate(schema_root, instance, 'CallToolResult', rev)}")


def client_main(schema_root: Path) -> None:
    import anyio

    print("mcp", importlib.metadata.version("mcp"), "| mcp-types", importlib.metadata.version("mcp-types"),
          "| jsonschema", importlib.metadata.version("jsonschema"), "| python", sys.version.split()[0])
    for mode in ("2026-07-28", "auto", "legacy"):
        try:
            anyio.run(run_session, schema_root, mode)
        except Exception as exc:  # noqa: BLE001
            print(f"session mode={mode!r} failed: {type(exc).__name__}: {str(exc)[:300]}")
    negative_checks(schema_root)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    elif "--relay" in sys.argv:
        relay(sys.argv[sys.argv.index("--relay") + 1])
    else:
        client_main(Path(sys.argv[1]).expanduser())
