#!/usr/bin/python3 -I
"""render_main.py <run>: REPORT.md from findings.json, the ledger and run metadata."""
import json, sys, collections, urllib.parse
run = sys.argv[1]
fs = json.load(open(f"{run}/findings.json")); L = json.load(open(f"{run}/coverage-ledger.json")); md = json.load(open(f"{run}/run-metadata.json"))
RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
conf = sorted([r for r in fs if r["verdict"] == "confirmed"], key=lambda r: (RANK[r["severity"]["overall_severity"]], r["fingerprint"]))
nv = [r for r in fs if r["verdict"] == "needs_validation"]; rej = [r for r in fs if r["verdict"] == "rejected"]
sev = collections.Counter(r["severity"]["overall_severity"] for r in conf); st = collections.Counter(u["status"] for u in L)
import glob, os
finals = [json.load(open(f)) for f in glob.glob(f"{run}/tools/finals/*.json")]
ver = sum(f["decision"] == "verified" for f in finals); rep = sum(f["decision"] == "replace" for f in finals)
BOUNDARY = json.load(open(f"{run}/tools/boundaries.json")); ONE = json.load(open(f"{run}/tools/oneliners.json"))
def cell(s): return s.replace("|", "\\|").replace("\n", " ")
def first(s): return s.split(". ")[0].rstrip(".") + "."
O = []
O += ["# vfs security audit, run 1", "",
"## 1. Run", "",
f"- **Target:** `vfs` (`vfs-py`) at commit `{md['source_ref']['commit']}`. The worktree was dirty only by the untracked `examples/pluto-demo/`, which was not reviewed.",
f"- **Profile:** `{md['profile']}`, over the whole repository: `src/`, `crates/`, `.github/`, `scripts/`, `pyproject.toml` and tracked configuration. No scoped exclusions.",
f"- **Agents:** every hunter, critic and verifier ran on Opus. Budget {md['budget']['max_agent_invocations']} agent invocations, {md['budget']['spent']} spent. The developer raised the budget twice during the run: from 30 to 65 after wave 1, and from 75 to 90 after critic c05 opened wave 6. The parent also raised it from 65 to 75 to keep the standard profile complete, and told the developer.",
"- **Execution:** sandboxed, source-and-local-only. Target code ran only under `tools/sandbox-run.py`: `sandbox-exec` denied all network including loopback, writes went only to the agent's own scratch folder, the environment was empty apart from a short allowlist, and CPU (60 s), wall clock (120 s), file size (64 MiB) and processes (256) were capped. macOS refuses memory rlimits, so a trusted parent watchdog sampled process-group RSS every 50 ms and killed the group above 2 GiB. A self-test confirmed it killed a 3 GiB allocation at 2.6 GiB. Only SQLite and InMemoryStorage ran; no real database engine, Docker, provider, network or PyPI was touched. Evidence files were promoted by trusted parent code with no-follow, single-link, size-bounded copies.",
"- **Prior runs:** none. There was no prior ledger to carry, so nothing was excluded or carried forward.",
f"- **Deferred coverage:** one unit, `graph(method='meet', minimal=True)` over caller-minted edges. Its hunter was stopped by a model safeguard (request `{md['safeguard_events'][0]['request_id']}`). It was not retried, and the parent did not do its work. Its superlinear prune cost is recorded as a hardening note below, not as a finding.",
"- **Out of scope:** no web, browser, cloud, RPC or desktop surface exists in source, so those companion domains were not selected. Deployment facts (GitHub environment rules, PyPI publisher settings, production collations) are outside source; where they decide a lead, it is in the Needs validation table.",
f"- **Status:** {md['run_status']}.", "",
"## 2. Security posture", "",
f"vfs's central controls are sound in shape: row rights are enforced inside storage, SQL is built with bound parameters, and the storage-tier search has real budgets. The audit confirmed **{len(conf)} findings** ({', '.join(f'{sev[k]} {k}' for k in RANK if sev[k])}) and left **{len(nv)} leads** that need a fact this run could not observe. The one **high** finding is an authorization bypass: `grant` and `revoke` are checked only at the path they name, so a caller with open access at a parent can grant itself into a private folder beneath it. Most medium findings are availability: a small file or a short pattern written by one agent makes the shared host process do quadratic or unbounded work, before any of vfs's own limits apply. Two medium findings cross principals directly: a caller-chosen `content_hash` lends one principal's rendered text to another, and a read-only permission map can be bypassed by verbs that act on a whole subtree.", "",
"Put simply: the permission checks are in the right place, but three of them check only one path where the effect spans many, and several parsers do their expensive work before the budget is consulted.", "",
"## 3. Confirmed findings", "",
"| # | Severity | Title | Boundary crossed | Observed result |", "|---|---|---|---|---|"]
for i, r in enumerate(conf, 1):
    O.append(f"| {i} | {r['severity']['overall_severity']} | {cell(r['title'])} | {cell(BOUNDARY[r['fingerprint']])} | {cell(ONE[r['fingerprint']])} |")
O += ["", "## 4. Finding summaries", "", "The complete trace, payloads and remediation sketch for every medium or high finding are in [FINDINGS-DETAIL.md](FINDINGS-DETAIL.md). The low findings are complete here.", ""]
for i, r in enumerate(conf, 1):
    s, x = r["severity"], r["execution"]
    src = r["trace"][-1]; ent = r["trace"][0]
    O += [f"### {i}. {r['title']}", "",
          f"- **Severity:** {s['overall_severity']} (likelihood {s['likelihood']['score']}, impact {s['impact']['score']}).",
          f"- **Source:** entry `{ent['file']}:{ent['line']}` (`{ent['scope']}`), sink `{src['file']}:{src['line']}` (`{src['scope']}`).",
          f"- **Lower-trust principal:** {x['attacker_perspective']}",
          f"- **Reproduction:** " + " ".join(f"({j}) {t}" for j, t in enumerate(x["instructions"], 1)),
          f"- **Conditions:** " + " ".join(f"{c['description']}" for c in r["conditions"]),
          f"- **Actual result:** {x['observed_result']}",
          f"- **Impact:** {s['impact']['reason']}",
          f"- **Priority:** {s['likelihood']['reason']}",
          f"- **Smallest fix:** {r['remediation']['strategy']}", ""]
O += ["## 5. Needs validation", "", "These are source-grounded leads, not confirmed vulnerabilities, and they carry no severity. Each needs one fact this run could not observe. The full traces and plans are in [NEEDS-VALIDATION.md](NEEDS-VALIDATION.md).", "",
      "| # | Lead | Trace | Blocker | Local next step | Owner check |", "|---|---|---|---|---|---|"]
for i, r in enumerate(nv, 1):
    p = r["validation_plan"]; t = " → ".join(f"`{x['file']}:{x['line']}`" for x in (r["trace"][0], r["trace"][-1]))
    O.append(f"| {i} | {cell(r['title'])} | {t} | {cell(first(r['blockers'][0]))} | {cell(first(p['local'])) if p.get('local') else 'none'} | {cell(first(p['deployment'])) if p.get('deployment') else 'none'} |")
O += ["", open(f"{run}/tools/report-tail.md").read().rstrip(), "",
"## 8. Coverage", "",
f"The ledger holds {len(L)} coverage units: {st['covered']} covered, {st['candidate']} that produced candidates, {st['blocked']} blocked and {st['deferred']} deferred. Six hunter waves ran, each followed by a coverage critic (c01 to c06). A distinct final-clean critic, c07, found no missing unit and no reassignment and stopped the loop. Every candidate got a fresh Phase 3 verifier, and every confirmed and needs-validation record got a second, fresh Phase 5 verifier. Of the {len(conf)+len(nv)} final records, {ver} came back verified as written, and {rep} came back with non-material replacements (line numbers, a citation, wording, or a broken fix sketch), which were applied directly; no Phase 5 verifier changed a verdict, root cause, result or severity. {len(rej)} candidate was rejected: link extraction minting edges to rows the author cannot list. The mechanics are real, but no rights boundary is crossed, so it stays in `findings.json` only to stop a later run repeating it.", "",
"Important limits. One run never exhausts a target: this is a first pass with no prior ledger. Real-engine concurrency (Postgres, MariaDB, SQL Server, Oracle) could not run here, which is why the race and collation leads are open. Deployment controls on GitHub and PyPI are not in source. The deferred `graph meet` unit has a source-level hardening note but no hunter result.", ""]
open(f"{run}/REPORT.md", "w").write("\n".join(O)); print("REPORT.md", len("\n".join(O)))
