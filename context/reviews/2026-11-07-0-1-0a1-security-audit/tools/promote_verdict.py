#!/usr/bin/python3 -I
"""promote_verdict.py <run> <vid>: promote the scratch files a verdict cites as agents/<vid>/artifacts/<rel>."""
import json, subprocess, sys
run, vid = sys.argv[1], sys.argv[2]
r = json.load(open(f"{run}/tools/verdicts/{vid}.json"))
pre = f"agents/{vid}/artifacts/"
rels = sorted({e["file"][len(pre):] for e in r.get("record", {}).get("evidence", []) if e.get("file", "").startswith(pre)})
if not rels:
    print(vid, "no artifacts cited"); sys.exit(0)
sys.exit(subprocess.call(["/usr/bin/python3", "-I", f"{run}/tools/promote.py", f"{run}/agents/{vid}", str(1 << 20), str(4 << 20), *rels]))
