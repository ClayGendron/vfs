---
name: code_review
description: Run the full multi-agent code review of the current uncommitted changes or branch — five parallel review agents (ownership_review, contract_review, scale_review, test_review, adversarial_review), an adversarial verifier per finding (verify_findings), and a final synthesis agent. Use when the user asks for a "code review", a "full review", or to "review this change" with the whole suite.
---

# Code review — the full suite as one workflow

Orchestrate the five review lenses over one change, verify every finding
adversarially, and deliver a single synthesized report. Invoking this
skill is the user's opt-in to multi-agent orchestration: launch it with
the Workflow tool.

The design follows the suite's contract: each lens owns a defect class,
so the five reviewers run in parallel without overlap; the verifier
exists because unverified findings cost the reader attention — only
findings that survive refutation reach the report.

## Shape

1. **Review** — five agents in parallel, one per skill. Each agent is
   instructed to read its skill file and follow it exactly:
   - `.claude/skills/ownership_review/SKILL.md` — structure: who owns each block of logic
   - `.claude/skills/contract_review/SKILL.md` — implementation vs declared contracts
   - `.claude/skills/scale_review/SKILL.md` — bounded at production scale, tightest engine
   - `.claude/skills/test_review/SKILL.md` — do the tests pin the contract
   - `.claude/skills/adversarial_review/SKILL.md` — executed attacks on the change
2. **Verify** — one agent per finding, following
   `.claude/skills/verify_findings/SKILL.md`. Findings verify as soon as
   their reviewer finishes (pipeline, no barrier between lenses).
3. **Synthesize** — after all verification completes, one agent merges
   the surviving findings: dedups across lenses, ranks by severity,
   and writes the report.

## Per-agent rules (must appear in every prompt)

- **uv project**: everything runs as `uv run python ...`,
  `uv run pytest ...`, `uv run ty check ...` from the repo root.
- **Repo is read-only**: never modify, stash, checkout, or commit
  anything. Scratch scripts go ONLY under the session scratchpad.
- **Follow the skill file**: the agent's first action is reading its
  assigned SKILL.md; the skill's procedure and evidence standard are
  binding.
- **Structured findings**: reviewers return findings via the schema —
  never prose-only.
- **Severity is normalized at the seam.** Each lens keeps its own
  vocabulary internally (breach/growth/decay/gap, blocker/major/minor,
  high/medium/low); the reviewer carries that label in `category` and
  maps it onto the schema's shared scale: `critical` (corruption, data
  loss, wrong results), `major` (violated contract, failure at
  supported scale, unpinned high-risk behavior), `minor` (bounded
  waste, decay, smells), `question` (design notes, ambiguous intent).

## Workflow template

Adapt paths/diff scope to the request, then launch:

```js
export const meta = {
  name: 'code-review',
  description: 'Five review lenses, adversarial verification, one report',
  phases: [{ title: 'Review' }, { title: 'Verify' }, { title: 'Synthesize' }],
}
const FINDINGS = {
  type: 'object', required: ['findings'],
  properties: { findings: { type: 'array', items: {
    type: 'object',
    required: ['title', 'file', 'severity', 'claim', 'evidence'],
    properties: {
      title: { type: 'string' }, file: { type: 'string' },
      line: { type: 'integer' },
      severity: { enum: ['critical', 'major', 'minor', 'question'] },
      category: { type: 'string' },  // the lens's own class label (e.g. breach, blocker, parity gap)
      claim: { type: 'string' },     // falsifiable statement of the defect
      evidence: { type: 'string' },  // quoted code/contract/output per the lens's standard
    },
  } } },
}
const VERDICT = {
  type: 'object', required: ['verdict', 'evidence'],
  properties: {
    verdict: { enum: ['CONFIRMED', 'REFUTED', 'DOWNGRADED'] },
    evidence: { type: 'string' },
    corrected_severity: { enum: ['critical', 'major', 'minor', 'question'] },
  },
}
const LENSES = ['ownership_review', 'contract_review', 'scale_review', 'test_review', 'adversarial_review']
const RULES = `Repo: <repo root>. Scope: <diff/branch under review>.
uv for everything; repo read-only; scratch only under <scratchpad>.
First read .claude/skills/<LENS>/SKILL.md and follow it exactly.`
const verified = await pipeline(
  LENSES,
  lens => agent(RULES.replace('<LENS>', lens) + `\nYou are the ${lens} reviewer.`,
    { label: lens, phase: 'Review', schema: FINDINGS }),
  (review, lens) => parallel((review?.findings ?? []).map(f => () =>
    agent(`Verify one finding per .claude/skills/verify_findings/SKILL.md.\n` +
      RULES + `\nFinding from ${lens}: ${JSON.stringify(f)}`,
      { label: `verify:${f.title}`, phase: 'Verify', schema: VERDICT })
      .then(v => ({ ...f, lens, ...v })))),
)
const surviving = verified.flat().filter(Boolean).filter(f => f.verdict !== 'REFUTED')
const report = await agent(
  `Write the final code-review report from these verified findings.\n` +
  `Dedup findings that describe the same defect through different lenses ` +
  `(keep the strongest evidence, note the converging lenses). Rank by severity ` +
  `(use corrected_severity when present). For each: what is wrong, why it matters, ` +
  `the evidence, and a suggested fix direction. End with what was reviewed and ` +
  `which lenses came back clean.\n${JSON.stringify(surviving)}`,
  { label: 'report', phase: 'Synthesize' })
return { report, confirmed: surviving.length, raw: verified.flat().filter(Boolean).length }
```

## Reporting

Relay the synthesized report to the user, then note the funnel — raw
findings vs survivors — so refuted noise is visible as work done, not
hidden. If a lens produced zero raw findings, say so explicitly: a
clean lens is a result, not an omission. Do not paste raw per-agent
output; the report is the deliverable.
