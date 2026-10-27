"""Probe 2 for the spec 171 review: what the official SDK's per-revision result
sieve does to spec 171's blocks on every revision a legacy client can
negotiate, not only the three the study validated.

Run from the repo root:
    uv run --with mcp python context/research/studies/2026-10-15-agent-shell/experiments/r171/p2_sdk_version_sieve.py
"""

from __future__ import annotations

import importlib.metadata
import json

from mcp_types import methods
from mcp_types.version import KNOWN_PROTOCOL_VERSIONS, MODERN_PROTOCOL_VERSIONS

CALL = {
    "content": [
        {"type": "text", "text": "[binary /p.png image/png 70B v3]"},
        {"type": "image", "data": "iVBORw0KGgo=", "mimeType": "image/png", "_meta": {"dev.vfs/path": "/p.png", "dev.vfs/version": 3}},
        {"type": "audio", "data": "AAAA", "mimeType": "audio/wav"},
        {"type": "resource_link", "uri": "vfs:///clips/intro.mp4", "name": "intro.mp4", "mimeType": "video/mp4", "size": 10485760,
         "description": "[binary /clips/intro.mp4 video/mp4 10485760B v1]", "_meta": {"dev.vfs/path": "/clips/intro.mp4"}},
    ],
    "structuredContent": {"success": True, "ops": ["read"], "observations": [{"path": "/p.png"}], "errors": []},
    "isError": False,
}
TOOLS = {
    "tools": [{"name": "read", "inputSchema": {"type": "object"}, "outputSchema": {"type": "object"}}],
}
READ = {"contents": [{"uri": "vfs:///p.png", "mimeType": "image/png", "blob": "iVBORw0KGgo="}], "ttlMs": 0, "cacheScope": "private"}


def show(method: str, version: str, data: dict) -> None:
    if version in MODERN_PROTOCOL_VERSIONS:
        data = {"resultType": "complete", **data}
    try:
        out = methods.serialize_server_result(method, version, data)
    except KeyError as exc:
        print(f"  {method:<16} {version}: no surface ({exc})")
        return
    except Exception as exc:  # noqa: BLE001
        print(f"  {method:<16} {version}: REJECTED {type(exc).__name__}: {str(exc).splitlines()[0][:150]}")
        return
    if method == "tools/call":
        kinds = [b.get("type") for b in out.get("content", [])]
        print(f"  {method:<16} {version}: kept blocks={kinds} structuredContent={'structuredContent' in out}"
              f" _meta on image={'_meta' in out['content'][1] if len(out.get('content', [])) > 1 else None}")
    elif method == "tools/list":
        print(f"  {method:<16} {version}: outputSchema kept={'outputSchema' in out['tools'][0]} keys={sorted(out)}")
    else:
        print(f"  {method:<16} {version}: keys={sorted(out)}")


print("mcp", importlib.metadata.version("mcp"), "| mcp-types", importlib.metadata.version("mcp-types"))
print("surface keys for tools/call:", sorted(v for (m, v) in methods.SERVER_RESULTS if m == "tools/call"))
for version in KNOWN_PROTOCOL_VERSIONS:
    print(f"--- {version}")
    show("tools/call", version, json.loads(json.dumps(CALL)))
    show("tools/list", version, json.loads(json.dumps(TOOLS)))
    show("resources/read", version, json.loads(json.dumps(READ)))


# Part 2: what the SDK lets through, validated against each revision's own schema.
import pathlib  # noqa: E402

import jsonschema  # noqa: E402

ROOT = pathlib.Path("~/Git/Repos/modelcontextprotocol/schema").expanduser()
print("\n--- the sieved tools/call result against each revision's published schema")
for version in KNOWN_PROTOCOL_VERSIONS:
    data = json.loads(json.dumps(CALL))
    if version in MODERN_PROTOCOL_VERSIONS:
        data = {"resultType": "complete", **data}
    out = methods.serialize_server_result("tools/call", version, data)
    schema = json.loads((ROOT / version / "schema.json").read_text())
    key = "$defs" if "$defs" in schema else "definitions"
    wrapped = {"$ref": f"#/{key}/CallToolResult", key: schema[key]}
    validator = jsonschema.validators.validator_for(schema)(wrapped)
    errs = list(validator.iter_errors(out))
    print(f"  {version}: {'VALID' if not errs else 'INVALID'}"
          + ("" if not errs else " - " + "; ".join(f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message[:80]}" for e in errs[:3])))
    for i, block in enumerate(out["content"]):
        sub = {**wrapped, "$ref": f"#/{key}/CallToolResult"}
        single = dict(out, content=[block])
        if list(jsonschema.validators.validator_for(schema)(sub).iter_errors(single)):
            print(f"      block {i} ({block['type']}) is not in {version}'s vocabulary")
