"""Part A: a census of real tool catalogs against spec 170's flag table (§2).

Run: cd /home/user/vfs && uv run python -I agents/2026-11-23-code-mode-prior-art/studies/experiments/08-tool-catalogs/census.py
Writes census.json beside this file and prints Markdown tables.

Each top-level property is normalised as spec 170 §2 says (a local $ref resolved one level; anyOf/oneOf
with exactly one non-null arm, or type [T, "null"], becomes T) and put in one row of the flag table.
"Shell-native" rows take a plain word (string, integer, number, boolean, enum/const, array of scalars by
repeating the flag); "JSON-valued" rows take '<json>' as the flag's value (array of objects, object,
several-arm union, no type). A tool is reachable only through `--json` when its top level is not an
object with properties, or a property is named help or json, or a property name is not a flag word.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalogs import compact, load_all, model_view, nbytes  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FLAG_WORD = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
SCALARS = {"string", "integer", "number", "boolean"}
NATIVE = ["string", "string-base64", "integer", "number", "boolean", "enum", "array-scalar"]
JSONV = ["union-scalar", "array-object", "array-other", "object-flat", "object-nested", "object-free", "union", "untyped"]
WORDISH = {"union-scalar"}  # the JSON row, but a plain word works: JSON-parse, else the string arm
ROWS = NATIVE + JSONV
FULL_ORIGINS = {"toolsnap", "export", "docker-inputSchema"}


def resolve(prop, root):
    ref = prop.get("$ref")
    if isinstance(ref, str):
        for prefix, key in (("#/$defs/", "$defs"), ("#/definitions/", "definitions")):
            if ref.startswith(prefix):
                target = (root.get(key) or {}).get(ref[len(prefix) :])
                if isinstance(target, dict):
                    merged = {k: v for k, v in prop.items() if k != "$ref"}
                    merged.update(target)
                    return merged
    return prop


def normalize(prop, root):
    prop = resolve(prop, root)
    for key in ("anyOf", "oneOf"):
        arms = prop.get(key)
        if isinstance(arms, list):
            live = [resolve(a, root) for a in arms if not (isinstance(a, dict) and a.get("type") == "null")]
            if len(live) == 1 and isinstance(live[0], dict):
                merged = {k: v for k, v in prop.items() if k != key}
                merged.update(live[0])
                return merged
    t = prop.get("type")
    if isinstance(t, list):
        live = [x for x in t if x != "null"]
        if len(live) == 1:
            prop = dict(prop, type=live[0])
    return prop


def scalar_kind(prop, root):
    """'enum', a scalar type name, or None when the item is not a scalar."""
    prop = normalize(prop, root)
    if "enum" in prop or "const" in prop:
        return "enum"
    t = prop.get("type")
    return t if t in SCALARS else None


def classify(prop, root):
    prop = normalize(prop, root)
    if "enum" in prop or "const" in prop:
        return "enum"
    for key in ("anyOf", "oneOf"):
        if isinstance(prop.get(key), list):
            arms = [a for a in prop[key] if isinstance(a, dict) and a.get("type") != "null"]
            return "union-scalar" if arms and all(scalar_kind(a, root) for a in arms) else "union"
    t = prop.get("type")
    if isinstance(t, list):
        return "union-scalar" if all(x in SCALARS or x == "null" for x in t) else "union"
    if t == "string":
        return "string-base64" if prop.get("contentEncoding") == "base64" else "string"
    if t in ("integer", "number", "boolean"):
        return t
    if t == "array":
        items = prop.get("items")
        if isinstance(items, dict):
            if scalar_kind(items, root):
                return "array-scalar"
            if normalize(items, root).get("type") == "object":
                return "array-object"
        return "array-other"
    if t == "object":
        sub = prop.get("properties")
        if not isinstance(sub, dict) or not sub:
            return "object-free"
        if all(scalar_kind(p, root) or classify(p, root) == "array-scalar" for p in sub.values() if isinstance(p, dict)):
            return "object-flat"
        return "object-nested"
    return "untyped"


def kebab(name):
    return name.replace("_", "-")


def census_tool(tool):
    schema = tool["input_schema"]
    out = {"server": tool["server"], "name": tool["name"], "origin": tool["origin"], "rows": Counter(),
           "rows_required": Counter(), "json_reasons": [], "camel": 0, "n_props": 0, "n_required": 0,
           "positionals": 0, "has_description_props": 0}
    if schema is None:
        out["json_reasons"].append("no schema data")
        return out
    top_union = any(k in schema for k in ("oneOf", "anyOf", "allOf"))
    props = schema.get("properties")
    if top_union or (schema.get("type") not in (None, "object")):
        out["json_reasons"].append("top level is not an object with properties")
    if not isinstance(props, dict):
        props = {}
    required = [r for r in (schema.get("required") or []) if r in props]
    out["n_props"], out["n_required"] = len(props), len(required)
    kebabs = Counter(kebab(n) for n in props)
    for name, prop in props.items():
        if not isinstance(prop, dict):
            continue
        row = classify(prop, schema)
        out["rows"][row] += 1
        if name in required:
            out["rows_required"][row] += 1
            if row in NATIVE:
                out["positionals"] += 1
        if name in ("help", "json"):
            out["json_reasons"].append(f"property named {name}")
        if not FLAG_WORD.match(name):
            out["json_reasons"].append(f"property {name!r} is not a flag word")
        if re.search(r"[a-z][A-Z]", name):
            out["camel"] += 1
        if kebabs[kebab(name)] > 1:
            out["json_reasons"].append(f"kebab alias of {name!r} collides")
        if normalize(prop, schema).get("description"):
            out["has_description_props"] += 1
    return out


def pct(n, d):
    return f"{100 * n / d:.1f}%" if d else "n/a"


def main():
    tools = load_all()
    rows = [census_tool(t) for t in tools]
    by_server = defaultdict(list)
    for t, r in zip(tools, rows):
        by_server[t["server"]].append((t, r))

    # Per-server sizes, as a model would receive tools/list.
    servers = []
    for server, items in sorted(by_server.items(), key=lambda kv: -len(kv[1])):
        catalog = compact([model_view(t) for t, _ in items])
        full = compact([{k: v for k, v in {"name": t["name"], "description": t["description"],
                                            "inputSchema": t["input_schema"], "annotations": t["annotations"] or None,
                                            "outputSchema": t["output_schema"]}.items() if v is not None}
                        for t, _ in items])
        origins = Counter(t["origin"] for t, _ in items)
        servers.append({"server": server, "tools": len(items), "bytes": nbytes(catalog),
                        "est_tokens": -(-len(catalog) // 4), "bytes_with_annotations_output": nbytes(full),
                        "origins": dict(origins)})

    full_rows = [r for t, r in zip(tools, rows) if t["origin"] in FULL_ORIGINS]
    arg_rows = [r for t, r in zip(tools, rows) if t["origin"] == "docker-arguments"]

    def table(rs):
        total, req = Counter(), Counter()
        for r in rs:
            total.update(r["rows"])
            req.update(r["rows_required"])
        props = sum(total.values())
        tools_n = len(rs)
        native_only = sum(1 for r in rs if not r["json_reasons"] and all(k in NATIVE for k in r["rows"]))
        any_jsonv = sum(1 for r in rs if any(k in JSONV for k in r["rows"]))
        req_jsonv = sum(1 for r in rs if any(k in JSONV for k in r["rows_required"]))
        needs_json = sum(1 for r in rs if r["json_reasons"])
        zero = sum(1 for r in rs if r["n_props"] == 0)
        word_only = sum(1 for r in rs if not r["json_reasons"] and all(k in NATIVE or k in WORDISH for k in r["rows"]))
        flat_only_jsonv = sum(1 for r in rs if any(k in JSONV for k in r["rows"])
                              and all(k in NATIVE or k == "object-flat" for k in r["rows"]))
        return {"tools": tools_n, "properties": props,
                "rows": {k: [total[k], req[k], total[k] - req[k]] for k in ROWS},
                "native_properties": sum(total[k] for k in NATIVE),
                "jsonvalued_properties": sum(total[k] for k in JSONV),
                "tools_zero_props": zero, "tools_native_only": native_only, "tools_any_jsonvalued": any_jsonv,
                "tools_required_jsonvalued": req_jsonv, "tools_needing_json_fallback": needs_json,
                "tools_rescued_by_dotted_flags": flat_only_jsonv, "tools_plain_words_only": word_only,
                "wordish_properties": sum(total[k] for k in WORDISH),
                "props_per_tool_median": statistics.median([r["n_props"] for r in rs]) if rs else 0,
                "props_per_tool_max": max([r["n_props"] for r in rs], default=0),
                "required_per_tool_median": statistics.median([r["n_required"] for r in rs]) if rs else 0,
                "positionals_median": statistics.median([r["positionals"] for r in rs]) if rs else 0,
                "camel_case_props": sum(r["camel"] for r in rs),
                "props_with_description": sum(r["has_description_props"] for r in rs)}

    per_server_tables = {}
    for server, items in by_server.items():
        rs = [r for t, r in items if t["origin"] in FULL_ORIGINS]
        if rs:
            per_server_tables[server] = table(rs)

    annotations = {}
    for server in ("github", "alibaba-devops"):
        c = Counter()
        for t, _ in by_server[server]:
            a = t["annotations"]
            c["tools"] += 1
            for hint in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
                if hint in a:
                    c[f"{hint}={a[hint]}"] += 1
            if a.get("readOnlyHint") is not True and "destructiveHint" not in a:
                c["write_without_destructiveHint"] += 1
            if "title" in a:
                c["title"] += 1
        annotations[server] = dict(c)
    docker_ann = Counter()
    for t in tools:
        if t["server"] not in ("github", "alibaba-devops") and t["annotations"]:
            docker_ann["tools_with_annotations"] += 1
            for hint in ("readOnlyHint", "destructiveHint"):
                if hint in t["annotations"]:
                    docker_ann[f"{hint}={t['annotations'][hint]}"] += 1
    annotations["docker-registry"] = dict(docker_ann)

    desc_bytes = [nbytes(t["description"]) for t in tools]
    json_list = [{"server": r["server"], "name": r["name"], "reasons": sorted(set(r["json_reasons"]))}
                 for r in full_rows if r["json_reasons"]]
    result = {"servers": servers, "full_schema": table(full_rows), "docker_arguments": table(arg_rows),
              "per_server": per_server_tables, "annotations": annotations,
              "description_bytes": {"median": statistics.median(desc_bytes), "p90": sorted(desc_bytes)[int(0.9 * len(desc_bytes))],
                                    "max": max(desc_bytes), "empty": sum(1 for b in desc_bytes if b == 0)},
              "tools_needing_json": json_list,
              "origin_counts": dict(Counter(t["origin"] for t in tools)),
              "total_tools": len(tools), "total_servers": len(by_server)}
    with open(os.path.join(HERE, "census.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)

    print(f"tools={len(tools)} servers={len(by_server)} origins={result['origin_counts']}")
    print("\n| server | tools | catalog bytes | est. tokens | bytes incl. annotations+outputSchema |")
    for s in servers[:12]:
        print(f"| {s['server']} | {s['tools']} | {s['bytes']:,} | {s['est_tokens']:,} | {s['bytes_with_annotations_output']:,} |")
    for label, tab in (("full-schema", result["full_schema"]), ("docker-arguments (lossy)", result["docker_arguments"])):
        print(f"\n{label}: tools={tab['tools']} properties={tab['properties']}")
        print("| row | properties | required | optional | share |")
        for k in ROWS:
            tot, req, opt = tab["rows"][k]
            print(f"| {k} | {tot} | {req} | {opt} | {pct(tot, tab['properties'])} |")
        for key in ("native_properties", "jsonvalued_properties", "tools_zero_props", "tools_native_only",
                    "tools_any_jsonvalued", "tools_required_jsonvalued", "tools_needing_json_fallback",
                    "tools_plain_words_only", "wordish_properties",
                    "tools_rescued_by_dotted_flags", "props_per_tool_median", "props_per_tool_max",
                    "required_per_tool_median", "positionals_median", "camel_case_props", "props_with_description"):
            print(f"  {key}: {tab[key]}")
    print("\nper server (full schema):")
    print("| server | tools | props | native | JSON-valued | tools native-only | tools plain words only | tools any JSON-valued | tools needing --json |")
    for server, tab in sorted(per_server_tables.items(), key=lambda kv: -kv[1]["tools"]):
        print(f"| {server} | {tab['tools']} | {tab['properties']} | {tab['native_properties']} | {tab['jsonvalued_properties']} | "
              f"{tab['tools_native_only']} | {tab['tools_plain_words_only']} | {tab['tools_any_jsonvalued']} | {tab['tools_needing_json_fallback']} |")
    print("\nannotations:", json.dumps(annotations, indent=1))
    print("description bytes:", result["description_bytes"])
    print("tools needing --json:", len(json_list))
    for j in json_list[:40]:
        print("  ", j)


if __name__ == "__main__":
    main()
