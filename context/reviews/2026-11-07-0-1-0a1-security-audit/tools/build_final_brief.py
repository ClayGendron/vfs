#!/usr/bin/python3 -I
"""build_final_brief.py <out> <fid> <fingerprint>: write agents/<fid>/BRIEF.md for a Phase 5 final record verifier."""
import json, os, sys
SKILL = "./.claude/skills/security-audit"
out, fid, fp = sys.argv[1:4]
V = open(os.path.join(SKILL, "VALIDATION-AND-REPORTING.md")).read()
p5 = V[V.index("### Phase 5: Verify the final records with fresh eyes"):V.index("### Phase 6:")].rstrip()
schema = json.load(open(os.path.join(SKILL, "report-schema.json")))["items"]["oneOf"]
rec = next(r for r in json.load(open(f"{out}/findings.json")) if r["fingerprint"] == fp)
arch = open(f"{out}/architecture.md").read()
adir = f"{out}/agents/{fid}"
parts = [
 f"# Final record verifier brief for `{fid}`\n\nYou are a fresh, independent final verifier. You did not hunt this candidate, did not perform its Phase 3 validation, and did not write this record. Repository: . at commit 3586750 (read-only). Check the structured record below against current source, not any hunter write-up. Earlier agents' artifacts under context/reviews/2026-11-07-0-1-0a1-security-audit/agents/*/artifacts/ are cited evidence you may read; reproduce any decisive local result yourself.\n",
 "## 1. Phase 5 instructions (verbatim from the skill)\n\n```text\n" + p5 + "\n```\n",
 f"## 2. The record under review (verdict `{rec['verdict']}`)\n\n```json\n" + json.dumps(rec, indent=1, ensure_ascii=False) + "\n```\n",
 "## 3. Architecture facts\n\n" + arch,
 "## 4. Source/local execution boundary\n\n"
 f"- Scratch, the only place you or target code may write: `{adir}/scratch/`. Never write `{adir}/artifacts/`; the parent promotes.\n"
 f"- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/{fid}/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).\n"
 f"- Run target code ONLY as `{out}/tools/sandbox-run.py {adir}/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.\n"
 "- Do not edit any repository file. Do not run git commands that change state.\n",
 "## 5. Return contract\n\nReturn exactly one JSON object and no surrounding prose: `{\"decision\":\"verified\",\"fingerprint\":\"" + fp + "\"}` or `{\"decision\":\"replace\",\"reason\":\"...\",\"record\":{...}}`. A replacement record must exactly match one verdict branch below, including `\"verdict\"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.\n\n"
 "### `confirmed` branch (verbatim)\n\n```json\n" + json.dumps(schema[0], indent=1) + "\n```\n\n### `needs_validation` branch (verbatim)\n\n```json\n" + json.dumps(schema[1], indent=1) + "\n```\n\n### `rejected` branch (verbatim)\n\n```json\n" + json.dumps(schema[2], indent=1) + "\n```\n",
]
os.makedirs(f"{adir}/scratch/evidence", exist_ok=True)
open(f"{adir}/BRIEF.md", "w").write("\n".join(parts)); print(f"{adir}/BRIEF.md", len("\n".join(parts)))
