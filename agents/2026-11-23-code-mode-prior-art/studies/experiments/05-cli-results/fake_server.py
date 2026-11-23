"""A minimal MCP stdio server for probing MCP-to-CLI clients.

Written for study 05. Speaks newline-delimited JSON-RPC with no SDK. Three tools:

- ``echo``: returns the arguments it received as JSON text, so a client's flag-to-JSON coercion is visible.
- ``fail``: returns ``isError: true`` with the text ``boom``.
- ``big``: returns one text block of ``lines`` numbered lines (default 5,000, about 200,000 characters).

Every call is appended to the file named by ``FAKE_SERVER_LOG`` so a driver can count wire calls.
"""

from __future__ import annotations

import json
import os
import sys

TOOLS = [
    {
        "name": "echo",
        "description": "Echo the arguments back as JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "free text"},
                "limit": {"type": "integer"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "mode": {"type": "string", "enum": ["fast", "slow"]},
                "verbose": {"type": "boolean"},
                "filter": {
                    "type": "object",
                    "properties": {"field": {"type": "string"}, "op": {"type": "string"}},
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "fail",
        "description": "Always returns isError.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "big",
        "description": "Returns many lines of text.",
        "inputSchema": {"type": "object", "properties": {"lines": {"type": "integer"}}},
        "annotations": {"readOnlyHint": True},
    },
]


def main() -> None:
    log_path = os.environ.get("FAKE_SERVER_LOG")
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        msg = json.loads(line)
        if log_path:
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(json.dumps({"method": msg.get("method"), "params": msg.get("params")}) + "\n")
        if "id" not in msg:
            continue
        reply = {"jsonrpc": "2.0", "id": msg["id"], "result": answer(msg.get("method"), msg.get("params") or {})}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


def answer(method: str | None, params: dict) -> dict:
    if method == "initialize":
        version = params.get("protocolVersion", "2025-06-18")
        return {"protocolVersion": version, "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "0"}}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        return call(params.get("name"), params.get("arguments") or {})
    return {}


def call(name: str | None, args: dict) -> dict:
    if name == "echo":
        return {"content": [{"type": "text", "text": json.dumps(args, sort_keys=True)}]}
    if name == "fail":
        return {"content": [{"type": "text", "text": "boom"}], "isError": True}
    if name == "big":
        count = int(args.get("lines", 5000))
        text = "\n".join(f"line {i:05d} " + "x" * 28 for i in range(count))
        return {"content": [{"type": "text", "text": text}]}
    return {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}


if __name__ == "__main__":
    main()
