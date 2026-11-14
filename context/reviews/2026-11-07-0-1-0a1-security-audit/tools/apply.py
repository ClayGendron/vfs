#!/usr/bin/python3 -I
"""apply.py <run-dir> <name>: promote a hunter's declared artifacts, then write its unit results into the ledger."""
import json, os, subprocess, sys
out, name = sys.argv[1:3]
r = json.load(open(f"{out}/tools/results/{name}.json"))
L = json.load(open(f"{out}/coverage-ledger.json")); by = {u["coverage_id"]: u for u in L}
for u in r["units"]:
    for c in u["checks"]:
        a = c.get("artifact")
        if c["method"] == "local" and a:
            pre = f"agents/{c['agent_id']}/artifacts/"
            rel = a[len(pre):] if a.startswith(pre) else None
            ok = rel and not os.path.exists(f"{out}/{a}") and subprocess.run([f"{out}/tools/promote.py", f"{out}/agents/{c['agent_id']}", str(256*1024), str(1024*1024), rel]).returncode == 0
            if not ok and not os.path.isfile(f"{out}/{a}"):
                print("PROMOTION FAILED", a, "-> check downgraded to source evidence"); c["method"], c["artifact"] = "source", None
                c["result"] += " [Parent note: the declared local artifact could not be promoted, so this check is retained as source evidence only.]"
    lu = by[u["coverage_id"]]
    assert lu["agent_id"] == name and lu["status"] == "in_progress", (lu["agent_id"], lu["status"])
    lu.update(status=u["disposition"], reviewed_paths=sorted({p for c in u["checks"] for p in c["reviewed_paths"]}),
              local_checks=u["checks"], result_fingerprints=u["candidate_fingerprints"], unresolved=u["unresolved"])
    lu["x_hardening"] = r.get("hardening", [])
    lu["x_uncovered"] = r.get("uncovered", [])
json.dump(L, open(f"{out}/coverage-ledger.json", "w"), indent=1, ensure_ascii=False)
cands = json.load(open(f"{out}/tools/candidates.json")) if os.path.exists(f"{out}/tools/candidates.json") else {}
for c in r.get("candidates", []): cands.setdefault(c["fingerprint"], []).append({"from": name, "candidate": c})
json.dump(cands, open(f"{out}/tools/candidates.json", "w"), indent=1, ensure_ascii=False)
print("applied", name)
