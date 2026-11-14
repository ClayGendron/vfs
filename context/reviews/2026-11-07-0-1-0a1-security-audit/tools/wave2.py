#!/usr/bin/python3 -I
import json, sys, unicodedata
out = sys.argv[1]
L = json.load(open(f"{out}/coverage-ledger.json")); by = {u["coverage_id"]: u for u in L}
crit = json.load(open(f"{out}/tools/results/c01-critic.json"))
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
            "wave": 2, "status": "in_progress", "agent_id": hunter, "reviewed_paths": [], "local_checks": [], "result_fingerprints": [], "unresolved": [],
            "x_planned_hunter": hunter, "x_reason": m["reason"]}
M = crit["missing_units"]
h05u = json.load(open(f"{out}/tools/results/h05-sql.json"))["uncovered"][0]
h05u = dict(h05u, selected_companion_blocks=["DATA-ISOLATION-AND-LIFECYCLE.md#Core discipline", "DATA-ISOLATION-AND-LIFECYCLE.md#Tenant and object-isolation attack classes", "DATA-ISOLATION-AND-LIFECYCLE.md#Universal moves", "DATA-ISOLATION-AND-LIFECYCLE.md#Validation rules"],
            excluded_blocks=[{"block": "ATTACK-CLASSES.md#Injection", "reason": "injection on these predicates was closed by the SQL unit; this unit is about collation-dependent comparison"}])
plan = [(M[5], "w2a-visibility"), (M[4], "w2b-derived"), (M[2], "w2c-compute"), (M[3], "w2c-compute"), (M[0], "w2d-reindex-edit"), (M[1], "w2d-reindex-edit"), (h05u, "w2e-collation")]
for m, h in plan:
    u = new_unit(m, h); assert u["coverage_id"] not in by, "collision " + u["coverage_id"]; L.append(u); by[u["coverage_id"]] = u
reassign = {crit["reassign_ids"][0]: "w2a-visibility", crit["reassign_ids"][1]: "w2b-derived", crit["reassign_ids"][2]: "w2c-compute"}
reasons = {crit["reassign_ids"][0]: "c01-critic: the first attempt was blocked; road helpers _owned_beneath/_open_beneath and descent.classify_miss were not read, so hidden-equals-absent on every miss path is not established.",
           crit["reassign_ids"][1]: "c01-critic: the first attempt left graph node/edge filtering, the cross-mount rerank and the vector-leg top-k ordering unreviewed.",
           crit["reassign_ids"][2]: "c01-critic: the first attempt left the sre_parse recursion classification and graph meet minimal=True pruning cost unsettled."}
for cid, h in reassign.items():
    u = by[cid]
    u["attempts"].append({k: u[k] for k in ("wave", "status", "agent_id", "reviewed_paths", "local_checks", "result_fingerprints", "unresolved")} | {"reassignment_reason": reasons[cid]})
    u.update(wave=2, status="in_progress", agent_id=h, reviewed_paths=[], local_checks=[], result_fingerprints=[], unresolved=[], x_planned_hunter=h)
L.sort(key=lambda u: u["coverage_id"])
json.dump(L, open(f"{out}/coverage-ledger.json", "w"), indent=1, ensure_ascii=False)
from collections import defaultdict; A = defaultdict(list)
for u in L:
    if u["status"] == "in_progress": A[u["agent_id"]].append(u["coverage_id"])
json.dump(A, open(f"{out}/tools/assignments-w2.json", "w"), indent=1); print({k: len(v) for k, v in A.items()}, len(L), "units")
