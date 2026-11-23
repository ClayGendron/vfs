"""Part B: the cost of each disclosure level for the combined catalog.

Run: cd /home/user/vfs && uv run python -I agents/2026-11-23-code-mode-prior-art/studies/experiments/08-tool-catalogs/disclosure.py
Writes disclosure.json beside this file and prints a Markdown table. Tokens are chars/4, an estimate.

Levels:
  1  every full schema preloaded: the compact JSON list of {name, description, inputSchema}
  1+ the same with annotations and outputSchema, as tools/list carries them
  2  names only, one per line
  3  name and the first sentence of the description, one per line
  4a `ls /.vfs/mcp`: one server name per line
  4b `ls /.vfs/mcp/<server>/tools`: one tool name per line, for one server (median and max over servers)
  4c every path /.vfs/mcp/<server>/tools/<tool>, one per line (a recursive listing)
  5  one tool's full manifest: its JSON (name, description, inputSchema), median, p90 and max
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalogs import compact, load_all, model_view, nbytes  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SENTENCE = re.compile(r"^(.+?[.!?。])(?:\s|$)", re.S)


def first_sentence(text):
    text = " ".join(text.split())
    m = SENTENCE.match(text)
    return m.group(1) if m else text


def size(text):
    return {"bytes": nbytes(text), "est_tokens": -(-len(text) // 4)}


def main():
    tools = load_all()
    by_server = defaultdict(list)
    for t in tools:
        by_server[t["server"]].append(t)
    levels = {}
    levels["1 full schemas"] = size(compact([model_view(t) for t in tools]))
    levels["1+ with annotations, outputSchema"] = size(compact([
        {k: v for k, v in {**model_view(t), "annotations": t["annotations"] or None, "outputSchema": t["output_schema"]}.items()
         if v is not None} for t in tools]))
    levels["2 names only"] = size("\n".join(t["name"] for t in tools) + "\n")
    levels["3 name + first sentence"] = size("\n".join(f"{t['name']}: {first_sentence(t['description'])}" for t in tools) + "\n")
    levels["4a ls /.vfs/mcp"] = size("\n".join(sorted(by_server)) + "\n")
    per_server = sorted(nbytes("\n".join(t["name"] for t in ts) + "\n") for ts in by_server.values())
    levels["4b ls one server (median)"] = {"bytes": statistics.median(per_server), "est_tokens": -(-int(statistics.median(per_server)) // 4)}
    levels["4b ls one server (max)"] = {"bytes": per_server[-1], "est_tokens": -(-per_server[-1] // 4)}
    levels["4c every path"] = size("\n".join(f"/.vfs/mcp/{t['server']}/tools/{t['name']}" for t in tools) + "\n")
    one = sorted(nbytes(compact(model_view(t))) for t in tools)
    full = [t for t in tools if t["origin"] in ("toolsnap", "export", "docker-inputSchema")]
    one_full = sorted(nbytes(compact(model_view(t))) for t in full)
    levels["5 one manifest, all tools (median)"] = {"bytes": statistics.median(one), "est_tokens": -(-int(statistics.median(one)) // 4)}
    levels["5 one manifest, full-schema tools (median)"] = {"bytes": statistics.median(one_full), "est_tokens": -(-int(statistics.median(one_full)) // 4)}
    levels["5 one manifest (p90)"] = {"bytes": one_full[int(0.9 * len(one_full))], "est_tokens": -(-one_full[int(0.9 * len(one_full))] // 4)}
    levels["5 one manifest (max)"] = {"bytes": one_full[-1], "est_tokens": -(-one_full[-1] // 4)}
    biggest = max(full, key=lambda t: nbytes(compact(model_view(t))))
    base = levels["1 full schemas"]["bytes"]
    for v in levels.values():
        v["ratio_to_full"] = round(v["bytes"] / base, 5)
        v["x_smaller"] = round(base / v["bytes"], 1)

    # Where the bytes of level 1 go, for the two largest full-schema servers.
    split = {}
    for server in ("github", "alibaba-devops"):
        ts = by_server[server]
        names = sum(nbytes(t["name"]) for t in ts)
        descs = sum(nbytes(t["description"]) for t in ts)
        schemas = sum(nbytes(compact(t["input_schema"])) for t in ts)
        prop_desc = sum(nbytes(str(p.get("description", ""))) for t in ts
                        for p in (t["input_schema"].get("properties") or {}).values() if isinstance(p, dict))
        outs = sum(nbytes(compact(t["output_schema"])) for t in ts if t["output_schema"])
        split[server] = {"tools": len(ts), "name_bytes": names, "description_bytes": descs, "input_schema_bytes": schemas,
                         "of_which_property_descriptions": prop_desc, "output_schema_bytes": outs}
    multiplexed = [t["name"] for t in tools if t["input_schema"] and
                   isinstance((t["input_schema"].get("properties") or {}).get("method"), dict) and
                   "enum" in t["input_schema"]["properties"]["method"]]
    out = {"tools": len(tools), "servers": len(by_server), "levels": levels, "split": split,
           "largest_manifest": f"{biggest['server']}/{biggest['name']}",
           "multiplexed_method_tools": multiplexed}
    with open(os.path.join(HERE, "disclosure.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(f"tools={len(tools)} servers={len(by_server)} largest manifest={out['largest_manifest']}")
    print("| level | bytes | est. tokens | share of level 1 | times smaller |")
    for k, v in levels.items():
        print(f"| {k} | {v['bytes']:,} | {v['est_tokens']:,} | {100 * v['ratio_to_full']:.2f}% | {v['x_smaller']} |")
    print(json.dumps(split, indent=1))
    print("multiplexed (a `method` enum):", len(multiplexed), multiplexed)


if __name__ == "__main__":
    main()
