#!/usr/bin/python3 -I
"""build_verifier_brief.py <out> <verifier-id> <fingerprint>: write agents/<id>/BRIEF.md for a Phase 3 candidate verifier."""
import json, os, re, sys
SKILL = "./.claude/skills/security-audit"
out, vid, fp = sys.argv[1:4]
read = lambda n: open(os.path.join(SKILL, n)).read()
def fenced_after(t, marker):
    i = t.index(marker); j = t.index("```text\n", i) + 8; return t[j:t.index("\n```", j)]
def companion(ref):
    f, h = ref.split("#", 1); m = re.search(r"^## " + re.escape(h) + r"[^\n]*\n.*?(?=^## |\Z)", read(f), re.S | re.M); return m.group(0).rstrip()
V = read("VALIDATION-AND-REPORTING.md"); H = read("HUNTING.md")
schema = json.load(open(os.path.join(SKILL, "report-schema.json")))["items"]["oneOf"]
cands = json.load(open(f"{out}/tools/candidates.json"))[fp]
L = json.load(open(f"{out}/coverage-ledger.json"))
units = [u for u in L if fp in u["result_fingerprints"] or any(fp in a["result_fingerprints"] for a in u["attempts"])]
hunters = sorted({c["from"] for c in cands})
checks = []
for u in units:
    for src in [u] + u["attempts"]:
        if fp in src["result_fingerprints"]:
            checks += [{"coverage_id": u["coverage_id"], **c} for c in src["local_checks"]]
val_blocks = sorted({b.split("#")[0] for u in units for b in u["selected_companion_blocks"]})
vb = "\n\n".join(f"### {f}#Validation rules\n\n" + companion(f"{f}#Validation rules") for f in val_blocks) or "(no companion selected for this unit)"
arch = open(f"{out}/architecture.md").read()
adir = f"{out}/agents/{vid}"
parts = [
 f"# Candidate verifier brief for `{vid}`\n\nYou are a fresh verifier. You did not hunt this candidate; it came from hunter(s) {', '.join(hunters)}. Repository: . at commit 3586750 (read-only).\n",
 "## 1. Verifier instructions (verbatim)\n\n```text\n" + fenced_after(V, "#### Candidate-verifier prompt") + "\n```\n",
 "## 2. Promotion procedure (verbatim)\n\n```text\n" + fenced_after(V, "Copy this promotion procedure verbatim into every candidate-verifier prompt:") + "\n```\n",
 "## 3. The candidate (as the hunter proposed it)\n\n```json\n" + json.dumps([c["candidate"] for c in cands], indent=1, ensure_ascii=False) + "\n```\n",
 "## 4. Linked coverage-unit checks and artifacts\n\nArtifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.\n\n```json\n" + json.dumps(checks, indent=1, ensure_ascii=False) + "\n```\n",
 "## 5. Architecture facts\n\n" + arch,
 "## 6. Relevant validation blocks (verbatim)\n\n" + vb + "\n\n### Core candidate gate (verbatim)\n\n```text\n" + fenced_after(H, "#### Core validation rules") + "\n```\n",
 "## 7. Source/local execution boundary\n\n"
 f"- Scratch, the only place you or target code may write: `{adir}/scratch/`. Never write `{adir}/artifacts/`; the parent promotes.\n"
 f"- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/{vid}/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).\n"
 f"- Run target code ONLY as `{out}/tools/sandbox-run.py {adir}/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.\n"
 "- Do not edit any repository file. Do not run git commands that change state.\n- Prior records with the same fingerprint: none (no prior run).\n",
 "## 8. Return contract\n\nReturn exactly one JSON object and no surrounding prose: `{\"decision\": \"confirmed|needs_validation|rejected\", \"record\": { ... }}`. The record must exactly match the decision's verdict branch below, including `\"verdict\"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `" + fp + "` unless you identify a genuinely different root cause.\n\n"
 "### `confirmed` branch (verbatim)\n\n```json\n" + json.dumps(schema[0], indent=1) + "\n```\n\n### `needs_validation` branch (verbatim)\n\n```json\n" + json.dumps(schema[1], indent=1) + "\n```\n\n### `rejected` branch (verbatim)\n\n```json\n" + json.dumps(schema[2], indent=1) + "\n```\n",
]
os.makedirs(f"{adir}/scratch", exist_ok=True)
open(f"{adir}/BRIEF.md", "w").write("\n".join(parts)); print(f"{adir}/BRIEF.md", len("\n".join(parts)), "checks:", len(checks))
