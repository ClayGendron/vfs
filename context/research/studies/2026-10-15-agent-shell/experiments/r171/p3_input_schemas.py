"""Probe 3 for the spec 171 review: how the verb parameters map onto a JSON input
schema. Part A counts the params table's kinds over the agent-facing verbs;
Part B lets the official SDK derive a schema from each verb's Python signature
(the path a builder would reach for first) and reports what leaks or breaks.

Run from the repo root:
    uv run --with mcp python context/research/studies/2026-10-15-agent-shell/experiments/r171/p3_input_schemas.py
"""

from __future__ import annotations

import json
from collections import Counter

from mcp.server.mcpserver.utilities.func_metadata import func_metadata

from vfs.base import VirtualFileSystem
from vfs.ops import ALL_OPS, DEVELOPER_OPS
from vfs.params import PARAMS, RULES, VALUE_RULES

AGENT_OPS = sorted(ALL_OPS - DEVELOPER_OPS - {"run"})
AWKWARD = {"observations", "entries", "edits", "pairs", "edges", "bytes", "dict", "authority", "str_set"}

print(f"=== A. params table over {len(AGENT_OPS)} agent-facing verbs (ALL_OPS - DEVELOPER_OPS - run) ===")
print("verbs:", AGENT_OPS)
kinds = Counter()
for op in AGENT_OPS:
    awkward = []
    for spec in PARAMS[op]:
        kinds[spec.kind] += 1
        if spec.kind in AWKWARD:
            awkward.append(f"{spec.name}:{spec.kind}")
    rules = len(RULES.get(op, ())) + len(VALUE_RULES.get(op, ()))
    print(f"  {op:<8} params={len(PARAMS[op]):>2} shape/value rules={rules} awkward={awkward}")
print("kind counts:", dict(sorted(kinds.items())))
print("mkedge provenance default:", [s.default for s in PARAMS["mkedge"] if s.name == "provenance"])

print("\n=== B. SDK func_metadata over the router's signatures ===")
total = 0
for op in AGENT_OPS:
    fn = getattr(VirtualFileSystem, op)
    try:
        meta = func_metadata(fn, skip_names=["self"], structured_output=False)
        schema = meta.arg_model.model_json_schema()
    except Exception as exc:  # noqa: BLE001
        print(f"  {op:<8} FAILED {type(exc).__name__}: {str(exc).splitlines()[0][:140]}")
        continue
    text = json.dumps(schema)
    total += len(text)
    props = schema.get("properties", {})
    flags = []
    if "authority" in props:
        flags.append("authority exposed")
    for name in ("observations", "entries", "edges", "edits", "moves", "copies"):
        if name in props:
            flags.append(f"{name}->{'$defs ' + ','.join(sorted(schema.get('$defs', {}))) if '$defs' in schema else 'inline'}")
    if "columns" in props:
        flags.append("columns=" + json.dumps(props["columns"])[:90])
    if "data" in props:
        flags.append("data=" + json.dumps(props["data"])[:90])
    print(f"  {op:<8} {len(text):>6} chars; {'; '.join(flags) if flags else 'clean'}")
print(f"total input-schema chars across verbs: {total:,}")
