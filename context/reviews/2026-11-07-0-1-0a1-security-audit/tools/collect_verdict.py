#!/usr/bin/python3 -I
"""collect_verdict.py <run-dir> <agent-id>: save a Phase 3 verifier's decision JSON and print a one-line summary."""
import json, sys, os
out, aid = sys.argv[1:3]
name = json.load(open(f"{out}/tools/agent-map-p3.json"))[aid]
path = f"<session-tmp>/tasks/{aid}.output"
last = None
for line in open(path):
    try: o = json.loads(line)
    except ValueError: continue
    for c in ((o.get("message") or {}).get("content") or []):
        if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "SubagentHandback": last = c["input"]["message"]
if last is None: sys.exit(f"{name}: no handback")
s = last.strip()
if s.startswith("```"): s = s.split("\n", 1)[1].rsplit("```", 1)[0]
r = json.loads(s)
os.makedirs(f"{out}/tools/verdicts", exist_ok=True)
json.dump(r, open(f"{out}/tools/verdicts/{name}.json", "w"), indent=1, ensure_ascii=False)
expected = json.load(open(f"{out}/tools/verifier-map-p3.json"))[name]
rec = r["record"]; sev = (rec.get("severity") or {}).get("overall_severity")
print(name, r["decision"], sev, "fp-same" if rec.get("fingerprint") == expected else f"FP-CHANGED {rec.get('fingerprint')}", "|", rec.get("title", "")[:100])
