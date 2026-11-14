#!/usr/bin/python3 -I
import json, sys, unicodedata
out = sys.argv[1]
L = json.load(open(f"{out}/coverage-ledger.json")); by = {u["coverage_id"]: u for u in L}
crit = json.load(open(f"{out}/tools/results/c03-critic.json"))
def enc(s):
    assert unicodedata.normalize("NFC", s) == s and s == s.strip()
    return "".join(chr(b) if (chr(b).isascii() and (chr(b).isalnum() or chr(b) in "-._~")) else "%%%02X" % b for b in s.encode())
NOT_SEL = {"WEB-PROTOCOL-AND-AUTH.md": "no HTTP, token, session or identity protocol exists in source", "CLIENT-SIDE.md": "no browser code in source",
           "CLOUD-AND-DEPLOYMENT.md": "no IaC or runtime deployment config in source", "PROTOCOLS-RPC-AND-MESSAGING.md": "no RPC or broker in source",
           "DESKTOP-MOBILE-AND-LOCAL-IPC.md": "no native app or IPC in source"}
def new_unit(m, hunter):
    ac = m["attack_class"]; ordinary = ac if ac.startswith("ATTACK-CLASSES.md#") else None
    refs = {"surface": m["surface"], "boundary": m["boundary"], "subsystem": m["subsystem"], "attack_class": ac}
    excl = list(m["excluded_blocks"]) + [{"block": f"{f}#Core discipline", "reason": r} for f, r in NOT_SEL.items()]
    return {"coverage_id": "::".join(enc(refs[k]) for k in ("surface", "boundary", "subsystem", "attack_class")), "canonical_refs": refs,
            "surface": m["surface"], "boundary": m["boundary"], "subsystem": m["subsystem"], "attack_class": ac.split("#", 1)[1],
            "starting_paths": [p.rstrip("/") for p in m["starting_paths"]], "ordinary_attack_class_block": ordinary,
            "selected_companion_blocks": m["selected_companion_blocks"], "excluded_blocks": excl, "prior_status": "none", "attempts": [],
            "wave": 4, "status": "in_progress", "agent_id": hunter, "reviewed_paths": [], "local_checks": [], "result_fingerprints": [], "unresolved": [],
            "x_planned_hunter": hunter, "x_reason": m["reason"]}
M = crit["missing_units"]
for m in M:
    m["excluded_blocks"] = [e for e in m["excluded_blocks"] if not e["block"].endswith("#Core discipline") or e["block"].split("#")[0] not in NOT_SEL]
    u = new_unit(m, "w4a-cost"); assert u["coverage_id"] not in by; L.append(u); by[u["coverage_id"]] = u
for lead in crit["resolved_prior_leads"]:
    cid, _, why = lead.partition(" :: ")
    if cid in by and by[cid]["status"] == "blocked":
        u = by[cid]
        u["attempts"].append({k: u[k] for k in ("wave", "status", "agent_id", "reviewed_paths", "local_checks", "result_fingerprints", "unresolved")} | {"reassignment_reason": "c03-critic resolved this unit from the attempt's own source facts: " + why})
        u.update(status="covered", unresolved=[], x_resolved_by="c03-critic", x_resolution=why, wave=4, agent_id="c03-critic",
                 local_checks=[{"agent_id": "c03-critic", "reviewed_paths": ["src/vfs/embedding/hashing.py", "src/vfs/embedding/provider.py", "src/vfs/storage/backends/database/lexical.py", "src/vfs/storage/backends/database/backend.py"], "invariant": "Glean query text cannot amplify work beyond the caller's own request size", "method": "source", "result": why, "artifact": None}],
                 reviewed_paths=["src/vfs/embedding/hashing.py", "src/vfs/embedding/provider.py", "src/vfs/storage/backends/database/backend.py", "src/vfs/storage/backends/database/lexical.py"], result_fingerprints=[])
L.sort(key=lambda u: u["coverage_id"])
json.dump(L, open(f"{out}/coverage-ledger.json", "w"), indent=1, ensure_ascii=False)
from collections import defaultdict; A = defaultdict(list)
for u in L:
    if u["status"] == "in_progress": A[u["agent_id"]].append(u["coverage_id"])
json.dump(A, open(f"{out}/tools/assignments-w4.json", "w"), indent=1); print({k: len(v) for k, v in A.items()}, len(L), "units")
