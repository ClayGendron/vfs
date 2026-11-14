#!/usr/bin/python3 -I
"""ledger_dispositions.py <run>: stamp each candidate unit's final record dispositions as x_final bookkeeping."""
import json, sys
run = sys.argv[1]
fs = {r["fingerprint"]: r for r in json.load(open(f"{run}/findings.json"))}
L = json.load(open(f"{run}/coverage-ledger.json"))
for u in L:
    fps = list(u["result_fingerprints"]) + [fp for a in u["attempts"] for fp in a["result_fingerprints"] if fp not in u["result_fingerprints"]]
    if fps:
        u["x_final"] = [{"fingerprint": fp, "verdict": fs[fp]["verdict"], "severity": (fs[fp].get("severity") or {}).get("overall_severity")} for fp in fps]
json.dump(L, open(f"{run}/coverage-ledger.json", "w"), indent=1, ensure_ascii=False)
print(sum(len(u.get("x_final", [])) for u in L), "dispositions stamped")
