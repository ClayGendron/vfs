#!/usr/bin/python3 -I
"""collect.py <run-dir> <name> <transcript.jsonl>: save the agent's final SubagentHandback JSON to tools/results/<name>.json"""
import json, sys
out, name, path = sys.argv[1:4]
last = None
for line in open(path):
    try: o = json.loads(line)
    except ValueError: continue
    for c in ((o.get("message") or {}).get("content") or []):
        if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "SubagentHandback":
            last = c["input"]["message"]
if last is None: sys.exit("no handback")
s = last.strip()
if s.startswith("```"): s = s.split("\n", 1)[1].rsplit("```", 1)[0]
r = json.loads(s)
json.dump(r, open(f"{out}/tools/results/{name}.json", "w"), indent=1, ensure_ascii=False)
if "units" in r:
    for u in r["units"]: print(name, u["disposition"], u["coverage_id"][:70], u.get("candidate_fingerprints"), u.get("unresolved"))
    for c in r.get("candidates", []): print("  CAND", c.get("proposed_verdict"), c.get("severity", {}).get("overall") if isinstance(c.get("severity"), dict) else c.get("severity"), c["fingerprint"], "|", c["title"][:110])
    print("  hardening:", len(r.get("hardening", [])), "uncovered:", [(x["surface"], x["attack_class"]) for x in r.get("uncovered", [])])
else:
    print(name, json.dumps(r)[:600])
