#!/usr/bin/python3 -I
"""collect_final.py <run-dir> <agent-id>: save a Phase 5 final verifier's decision JSON and print a one-line summary."""
import json, sys, os
out, aid = sys.argv[1:3]
name = json.load(open(f"{out}/tools/agent-map-p5.json"))[aid]
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
json.dump(r, open(f"{out}/tools/finals/{name}.json", "w"), indent=1, ensure_ascii=False)
expected = json.load(open(f"{out}/tools/final-map-p5.json"))[name]
if r["decision"] == "verified":
    print(name, "verified", "fp-same" if r.get("fingerprint") == expected else f"FP-CHANGED {r.get('fingerprint')}")
else:
    rec = r["record"]
    print(name, "REPLACE", rec.get("verdict"), (rec.get("severity") or {}).get("overall_severity"), "fp-same" if rec.get("fingerprint") == expected else f"FP-CHANGED {rec.get('fingerprint')}", "|", r.get("reason", "")[:300])
