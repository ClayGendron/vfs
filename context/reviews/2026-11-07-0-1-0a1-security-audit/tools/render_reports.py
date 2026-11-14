#!/usr/bin/python3 -I
"""render_reports.py <run>: FINDINGS-DETAIL.md and NEEDS-VALIDATION.md copied mechanically from findings.json."""
import json, sys
run = sys.argv[1]
fs = json.load(open(f"{run}/findings.json"))
RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
conf = sorted([r for r in fs if r["verdict"] == "confirmed"], key=lambda r: (RANK[r["severity"]["overall_severity"]], r["fingerprint"]))
nv = [r for r in fs if r["verdict"] == "needs_validation"]
def loc(x): return f"`{x['file']}:{x['line']}`"
def trace(r): return "\n".join(f"{i}. **{t['kind']}** {loc(t)} `{t['scope']}`: {t['description']}" for i, t in enumerate(r["trace"], 1))
def evidence(r): return "\n".join(f"- {loc(e)}: {e['description']}" for e in r["evidence"])
D = ["# Findings detail", "", "Each confirmed medium, high or critical record from `findings.json`, copied in full. Run `vfs-run-1-2026-11-07` at commit `35867501a71f0246d9a9f6b755e1fcf323d58bb4`. Artifact paths are relative to the run folder.", ""]
for n, r in enumerate([r for r in conf if RANK[r["severity"]["overall_severity"]] <= 2], 1):
    s, x, m = r["severity"], r["execution"], r["remediation"]
    D += [f"## {n}. {r['title']}", "", f"**Severity:** {s['overall_severity']} (likelihood {s['likelihood']['score']}, impact {s['impact']['score']}). **Confidence:** {r['confidence']['score']}. **Fingerprint:** `{r['fingerprint']}`", "",
          r["description"], "", "### Root cause", "", r["root_cause"], "", "### Intended behaviour", "", r["intended_behavior"], "",
          "### Trace", "", trace(r), "", "### Evidence", "", evidence(r), "",
          "### Conditions", "", "\n".join(f"- *{c['kind']}*: {c['description']}" for c in r["conditions"]), "",
          "### Reproduction", "", f"**Attacker perspective:** {x['attacker_perspective']}", "", "Payloads:", "", "\n".join(f"- `{p}`" for p in x["payloads"]), "",
          "Instructions:", "", "\n".join(f"{i}. {t}" for i, t in enumerate(x["instructions"], 1)), "", f"**Observed result:** {x['observed_result']}", "",
          "### Priority", "", f"Likelihood {s['likelihood']['score']}: {s['likelihood']['reason']}", "", f"Impact {s['impact']['score']}: {s['impact']['reason']}", "", f"Confidence: {r['confidence']['reason']}", "",
          "### Remediation", "", m["strategy"], ""]
    for c in m.get("code_changes", []):
        D += [f"Sketch for `{c['file_name']}`:", "", "```" + ("rust" if c["file_name"].endswith(".rs") else "python"), c["fixed_code"], "```", ""]
open(f"{run}/FINDINGS-DETAIL.md", "w").write("\n".join(D))
N = ["# Needs validation", "", "Source-grounded leads whose deciding fact lies outside what this run could observe. These have no severity and are not confirmed vulnerabilities. Each names the exact blocker and a bounded way to settle it.", ""]
for n, r in enumerate(nv, 1):
    p = r["validation_plan"]
    N += [f"## {n}. {r['title']}", "", f"**Fingerprint:** `{r['fingerprint']}`", "", r["description"], "", "### Claimed root cause", "", r["claimed_root_cause"], "",
          "### Trace", "", trace(r), "", "### Evidence", "", evidence(r), "", "### Blockers", "", "\n".join(f"- {b}" for b in r["blockers"]), ""]
    if p.get("local"): N += ["### Local resolution plan", "", p["local"], ""]
    if p.get("deployment"): N += ["### Owner-observed deployment check", "", p["deployment"], ""]
open(f"{run}/NEEDS-VALIDATION.md", "w").write("\n".join(N))
print(len(conf), "confirmed;", len(nv), "needs_validation")
for r in conf: print(r["severity"]["overall_severity"], "|", r["title"][:110])
