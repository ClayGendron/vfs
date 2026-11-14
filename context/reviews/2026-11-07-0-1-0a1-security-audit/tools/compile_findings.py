#!/usr/bin/python3 -I
"""compile_findings.py <run>: build findings.json from tools/verdicts, dropping keys the schema branch does not declare."""
import json, sys
run = sys.argv[1]
schema = json.load(open("./.claude/skills/security-audit/report-schema.json"))
branches = {b["properties"]["verdict"]["const"]: b for b in schema["items"]["oneOf"]}
dropped = []
def prune(node, sch, where):
    if isinstance(node, dict) and sch.get("type") == "object" and "properties" in sch:
        out = {}
        for k, v in node.items():
            if k not in sch["properties"]:
                dropped.append(f"{where}.{k}"); continue
            out[k] = prune(v, sch["properties"][k], f"{where}.{k}")
        return out
    if isinstance(node, list) and "items" in sch:
        return [prune(x, sch["items"], f"{where}[{i}]") for i, x in enumerate(node)]
    return node
# Phase 5 replacements the parent reviewed as non-material (line, wording or remediation-sketch corrections only).
NONMATERIAL = {"vfs.rendering:ooxml-part-decompression-unbounded": "f10-p5", "vfs.rendering.xlsx:region-table-quadratic-materialization": "f18-p5", "vfs/storage/replace.py:fuzzy-replacers-quadratic-inline-in-writer-transaction": "f15-p5", "vfs.rendering.docx:table-gridspan-expansion": "f08-p5", "vfs:storage/backends/database/backend.py:_embed_step:refused-batch-head-of-line-no-split-or-quarantine": "f20-p5"}
# Non-material trace-kind relabels so a multi-step trace has exactly one terminal sink.
FIXUPS = {"v04-p3": [(4, "propagation")], "v20-p3": [(4, "propagation"), (5, "sink")], "v10-p3": [(6, "propagation")]}
vmap = json.load(open(f"{run}/tools/verifier-map-p3.json"))
records = []
import os
for vid, fp in sorted(vmap.items()):
    p = f"{run}/tools/verdicts/{vid}.json"
    if not os.path.exists(p):
        print("MISSING", vid, fp); continue
    rec = json.load(open(p))["record"]
    fid = NONMATERIAL.get(fp)
    if fid:
        rep = json.load(open(f"{run}/tools/finals/{fid}.json"))
        assert rep["decision"] == "replace" and rep["record"]["fingerprint"] == fp
        rec = rep["record"]; dropped.append(f"{vid}: applied non-material Phase 5 replacement from {fid}")
    assert rec["fingerprint"] == fp, (vid, rec["fingerprint"], fp)
    for i, kind in FIXUPS.get(vid, []):
        dropped.append(f"{vid}.trace[{i}].kind {rec['trace'][i]['kind']} -> {kind} (label-only)"); rec["trace"][i]["kind"] = kind
    records.append(prune(rec, branches[rec["verdict"]], vid))
records.sort(key=lambda r: r["fingerprint"])
json.dump(records, open(f"{run}/findings.json", "w"), indent=1, ensure_ascii=False)
print(len(records), "records;", {v: sum(r["verdict"] == v for r in records) for v in branches})
for d in dropped: print("dropped", d)
