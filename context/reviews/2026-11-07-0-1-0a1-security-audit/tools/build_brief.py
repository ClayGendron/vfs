#!/usr/bin/python3 -I
"""build_brief.py <out-dir> <kind:hunter> <agent-id> <coverage-id>...  -> writes agents/<id>/BRIEF.md

Copies every block verbatim from the skill files, the ledger and architecture.md, so no hunter
prompt carries a paraphrase. The per-agent brief lives outside scratch/ and is parent-owned.
"""
import json, re, sys, os
SKILL = "./.claude/skills/security-audit"
out, kind, agent, ids = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
def read(name): return open(os.path.join(SKILL, name)).read()
def fenced_after(text, marker):
    i = text.index(marker); j = text.index("```text\n", i) + 8; return text[j:text.index("\n```", j)]
def ordinary(name):
    t = read("ATTACK-CLASSES.md"); m = re.search(r"^\*\*" + re.escape(name) + r"\*\* \(subagent_type.*?(?=^\*\*[A-Z][^*]+\*\* \(subagent_type|\Z)", t, re.S | re.M)
    if not m: raise SystemExit(f"no ordinary block {name}")
    return m.group(0).rstrip()
def companion(ref):
    f, h = ref.split("#", 1); t = read(f)
    m = re.search(r"^## " + re.escape(h) + r"[^\n]*\n.*?(?=^## |\Z)", t, re.S | re.M)
    if not m: raise SystemExit(f"no companion block {ref}")
    return m.group(0).rstrip()
hunting = read("HUNTING.md")
schema = json.load(open(os.path.join(SKILL, "report-schema.json")))["items"]["oneOf"]
ledger = {u["coverage_id"]: u for u in json.load(open(os.path.join(out, "coverage-ledger.json")))}
units = [ledger[i] for i in ids]
peers = sorted(u["coverage_id"] for u in ledger.values() if u["coverage_id"] not in ids and u["status"] in ("planned", "in_progress"))
blocks, excluded = [], {}
for u in units:
    if u["ordinary_attack_class_block"]:
        b = ("ord", u["ordinary_attack_class_block"].split("#", 1)[1])
        if b not in blocks: blocks.append(b)
    for c in u["selected_companion_blocks"]:
        if ("comp", c) not in blocks: blocks.append(("comp", c))
    for e in u["excluded_blocks"]: excluded[e["block"]] = e["reason"]
adir = os.path.join(out, "agents", agent)
parts = [
 "# Hunter brief for agent `" + agent + "`\n",
 "## 1. Role\n\nYour goal is to find source-grounded security invariant failures in your assigned coverage units of the vfs repository at .. You must return exactly one JSON object matching the structured-result contract at the end of this brief, with no surrounding prose.\n",
 "## 2. architecture.md (verbatim)\n\n" + open(os.path.join(out, "architecture.md")).read(),
 "## 3. Assigned units (verbatim from coverage-ledger.json)\n\n```json\n" + json.dumps([{k: u[k] for k in ("coverage_id","canonical_refs","surface","boundary","subsystem","attack_class","starting_paths","ordinary_attack_class_block","selected_companion_blocks","excluded_blocks")} for u in units], indent=1, ensure_ascii=False) + "\n```\n",
 "## 4. Selected blocks (verbatim)\n\n" + "\n\n---\n\n".join(("### ATTACK-CLASSES.md#" + n + "\n\n" + ordinary(n)) if k == "ord" else ("### " + n + "\n\n" + companion(n)) for k, n in blocks) + "\n",
 "## 5. Excluded blocks\n\n" + ("\n".join(f"- {b}: {r}" for b, r in sorted(excluded.items())) or "- none") + "\n",
 "## 6. Core hunting method (verbatim)\n\n```text\n" + fenced_after(hunting, "#### Core hunting method") + "\n```\n\n### Promotion procedure (verbatim)\n\n```text\n" + fenced_after(hunting, "#### Promotion procedure") + "\n```\n",
 "## 7. Core validation rules (verbatim)\n\n```text\n" + fenced_after(hunting, "#### Core validation rules") + "\n```\n",
 "## 8. Exclusions\n\nNo prior run exists, so there are no carried same-source confirmed exclusions. Peer-owned coverage IDs you must not duplicate (return a variant there under `uncovered` only if no unit covers it):\n\n" + "\n".join("- " + p for p in peers) + "\n",
 "## 9. Your paths, sandbox, and result contract\n\n"
 f"- Agent ID: `{agent}`. Scratch (the only place you or target code may write): `{adir}/scratch/`. Never write `{adir}/artifacts/`; the parent promotes.\n"
 f"- Promotion allowlist: any regular files you name under `scratch/evidence/` in your result's local-check `artifact` fields (as `agents/{agent}/artifacts/evidence/<name>`), at most 256 KiB each and 1 MiB total. List them; the parent promotes them after you return.\n"
 f"- Sandbox: run target code ONLY as `{out}/tools/sandbox-run.py {adir}/scratch <cmd...>`. It denies all network (loopback too), starts an empty env (HOME/TMPDIR in scratch), makes everything but scratch read-only, and caps CPU 60 s, wall 120 s, RSS 2 GiB (watchdog), files 64 MiB, 256 procs. Use `./.venv/bin/python -I <scratch-script>` as the interpreter (vfs and all extras are installed; do not use uv, pip, or network). Write harness scripts into scratch first. SQLite files and InMemoryStorage only; no real database engines. Never run target code outside this launcher.\n"
 "- Do not edit anything in the repository. Do not run git commands that change state.\n\n"
 "### Structured hunter result (verbatim)\n\n" + hunting[hunting.index("Return exactly one JSON object, with no surrounding prose:"):hunting.index("## Parent consolidation")].rstrip() + "\n\n"
 "### report-schema.json `confirmed` branch (verbatim)\n\n```json\n" + json.dumps(schema[0], indent=1) + "\n```\n\n"
 "### report-schema.json `needs_validation` branch (verbatim)\n\n```json\n" + json.dumps(schema[1], indent=1) + "\n```\n",
]
os.makedirs(os.path.join(adir, "scratch"), exist_ok=True)
open(os.path.join(adir, "BRIEF.md"), "w").write("\n".join(parts))
print(os.path.join(adir, "BRIEF.md"), len("\n".join(parts)))
