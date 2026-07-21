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

## 0. Scout the scope first — inline, before launching

Reviewers cannot review what they were not pointed at, and a scope
placeholder that reaches an agent verbatim is a silent no-op. Establish
the scope yourself in a couple of tool calls, then pass it into the
workflow as `args` — never as hand-substituted text in the script:

- `git status --porcelain` and `git diff --stat` for the working tree.
- **Untracked files are in scope.** `git diff` cannot see them; list
  them explicitly (`git status --porcelain | grep '^??'`) and name them
  in the scope string, or a whole new test file reviews as absent.
- For a branch review, `git diff --stat <base>...HEAD` plus the commit
  list. Say which base you used.
- If the change is large or spans unrelated subsystems, say so in the
  scope string — reviewers should read enough surrounding code to judge
  the change, but only report on what changed.

Pass `{ repo, scope, scratch }` as `args`. The script reads them; no
`<placeholder>` string ever survives into a prompt.

## Shape

1. **Review** — five agents in parallel, one per skill, each running on
   Fable (`model: 'fable'`). Each agent is instructed to read its skill
   file and follow it exactly:
   - `.claude/skills/ownership_review/SKILL.md` — structure: who owns each block of logic
   - `.claude/skills/contract_review/SKILL.md` — implementation vs declared contracts
   - `.claude/skills/scale_review/SKILL.md` — bounded at production scale, tightest engine
   - `.claude/skills/test_review/SKILL.md` — do the tests pin the contract
   - `.claude/skills/adversarial_review/SKILL.md` — executed attacks on the change
2. **Verify** — verifiers follow
   `.claude/skills/verify_findings/SKILL.md`, on Opus (`model: 'opus'`),
   at high effort. Findings verify as soon as their reviewer finishes
   (pipeline, no barrier between lenses). Verification depth scales
   with the stakes: **three independent skeptics for `critical` and
   `major`, one for `minor` and `question`.** A finding survives only
   if fewer than half its verifiers refute it — ties refute, because a
   split panel is not evidence a defect is real.
3. **Synthesize** — after all verification completes, one agent on
   Fable (`model: 'fable'`) merges the surviving findings: dedups
   across lenses, ranks by severity, and writes the report. **Skipped
   entirely when nothing survived** — an empty review is reported
   directly, not narrated by an agent with no material.

## Per-agent rules (must appear in every prompt)

- **uv project**: everything runs as `uv run python ...`,
  `uv run pytest ...`, `uv run ty check ...` from the repo root.
- **Repo is read-only**: never modify, stash, checkout, or commit
  anything. Scratch scripts go ONLY under the session scratchpad.
  Reviewers do not need `isolation: 'worktree'` — nothing writes.
- **Follow the skill file**: the agent's first action is reading its
  assigned SKILL.md; the skill's procedure and evidence standard are
  binding.
- **Structured findings**: reviewers return findings via the schema —
  never prose-only.
- **The close-out ledger is not optional.** Four of the five lenses end
  by requiring a statement of what was checked and found clean, because
  a review reporting only findings hides how much of the surface was
  actually verified. That ledger goes in the schema's `coverage` field —
  including anything the lens deliberately did not reach (a spent time
  box, an engine it could not exercise). A lens that returns findings
  but no coverage has not finished.
- **Severity is normalized at the seam.** Each lens keeps its own
  vocabulary internally (breach/growth/decay/gap;
  misplacement/duplication/envy/leak/divergence; blocker/major/minor;
  high/medium/low); the reviewer carries that label in `category` and
  maps it onto the schema's shared scale: `critical` (corruption, data
  loss, wrong results), `major` (violated contract, failure at
  supported scale, unpinned high-risk behavior), `minor` (bounded
  waste, decay, smells), `question` (design notes, ambiguous intent).

## Workflow template

Launch with `args: { repo, scope, scratch }` from step 0:

```js
export const meta = {
  name: 'code-review',
  description: 'Five review lenses, adversarial verification, one report',
  phases: [{ title: 'Review' }, { title: 'Verify' }, { title: 'Synthesize' }],
}
const FINDINGS = {
  type: 'object', required: ['findings', 'coverage'],
  properties: {
    // The lens's own close-out ledger: surface checked and found clean,
    // plus anything it deliberately did not reach. Never omit.
    coverage: { type: 'string' },
    findings: { type: 'array', items: {
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
  } },
  },
}
const VERDICT = {
  type: 'object', required: ['verdict', 'evidence'],
  properties: {
    verdict: { enum: ['CONFIRMED', 'REFUTED', 'DOWNGRADED'] },
    evidence: { type: 'string' },
    corrected_severity: { enum: ['critical', 'major', 'minor', 'question'] },
    repro: { type: 'string' },   // minimal `uv run python` repro, CONFIRMED only
    leads: { type: 'string' },   // unverified observations noticed in passing
  },
}
const LENSES = ['ownership_review', 'contract_review', 'scale_review', 'test_review', 'adversarial_review']
const { repo, scope, scratch } = args
const RULES = `Repo: ${repo}. Scope under review: ${scope}
uv for everything; the repo is READ-ONLY (no edits, stash, checkout, commit);
scratch scripts go only under ${scratch}.`

const RANK = { critical: 0, major: 1, minor: 2, question: 3 }
const votesFor = f => (f.severity === 'critical' || f.severity === 'major') ? 3 : 1

// A finding is dropped only by a majority of independent skeptics; a
// panel that all died is surfaced as UNVERIFIED, never as clean.
async function adjudicate(f, lens) {
  const n = votesFor(f)
  const votes = (await parallel(Array.from({ length: n }, (_, i) => () =>
    agent(`${RULES}
Verify exactly one finding per .claude/skills/verify_findings/SKILL.md — read it first and follow it exactly.
You are verifier ${i + 1} of ${n}. Work independently and from the code itself; the reviewer's
reasoning chain is a claim to refute, not a premise to build on.
Finding from ${lens}: ${JSON.stringify(f)}`,
      { label: `verify:${f.title} #${i + 1}`, phase: 'Verify', schema: VERDICT, model: 'opus', effort: 'high' })
  ))).filter(Boolean)
  if (!votes.length) return { ...f, lens, verdict: 'UNVERIFIED', evidence: 'every verifier agent failed' }
  if (votes.filter(v => v.verdict === 'REFUTED').length * 2 >= votes.length) return null
  // Keep the most conservative surviving verdict.
  const kept = votes.find(v => v.verdict === 'DOWNGRADED') ?? votes.find(v => v.verdict === 'CONFIRMED') ?? votes[0]
  return { ...f, lens, ...kept, votes: votes.map(v => v.verdict) }
}

// A lens whose agent died is a hole in coverage, never a clean lens.
const ledger = []
const verified = await pipeline(
  LENSES,
  lens => agent(`${RULES}
You are the ${lens} reviewer. First read .claude/skills/${lens}/SKILL.md and follow it exactly.
Return findings through the schema only — never prose-only. Fill in \`coverage\` with your
skill's close-out ledger: what you checked and found clean, and what you did not reach.`,
    { label: lens, phase: 'Review', schema: FINDINGS, model: 'fable' }),
  (review, lens) => {
    const found = review?.findings ?? []
    ledger.push({ lens, raw: found.length, coverage: review?.coverage ?? 'LENS FAILED — no coverage; this surface is unreviewed' })
    log(`${lens}: ${found.length} raw finding(s)${review ? '' : ' — AGENT FAILED, surface unreviewed'}`)
    return parallel(found.map(f => () => adjudicate(f, lens)))
  },
)

const all = verified.flat().filter(Boolean)
const surviving = all.sort((a, b) => (RANK[a.corrected_severity ?? a.severity] ?? 9) - (RANK[b.corrected_severity ?? b.severity] ?? 9))
const leads = all.map(f => f.leads).filter(Boolean)
log(`${surviving.length} finding(s) survived verification`)
if (!surviving.length) return { report: null, confirmed: 0, ledger, leads }

const report = await agent(
  `Write the final code-review report from these verified findings.
Scope reviewed: ${scope}
Dedup findings that describe the same defect through different lenses (keep the strongest
evidence, note the converging lenses). They arrive ranked by severity — preserve that order.
For each: what is wrong, why it matters, the evidence, the minimal repro if one was produced,
and a suggested fix direction. Flag any UNVERIFIED finding as unverified in the report.
End with a coverage section built from each lens's own ledger below — what was checked and
found clean, and what no lens reached. Report a failed lens as unreviewed surface, never as clean.
Findings: ${JSON.stringify(surviving)}
Coverage ledger: ${JSON.stringify(ledger)}`,
  { label: 'report', phase: 'Synthesize', model: 'fable' })
return { report, confirmed: surviving.length, findings: surviving, ledger, leads }
```

## Iterating on a run

Every launch persists its script and returns a `scriptPath` and
`runId`. To adjust a lens prompt or the adjudication rule, edit that
file and relaunch with `{ scriptPath, resumeFromRunId }` — the
unchanged prefix of `agent()` calls returns cached instantly, so only
the edited stage re-runs. Before diagnosing an empty or surprising
result, read `journal.jsonl` in the transcript directory: it records
what each agent actually returned. Do not assume a lens was clean when
its agent may simply have failed.

## Reporting

1. **Relay the synthesized report** — that is the deliverable. Do not
   paste raw per-agent output.
2. **Call `ReportFindings` once** with the surviving findings, most
   severe first, so the host UI renders them: map `claim` →
   `summary`, the verifier's repro or failure path →
   `failure_scenario`, `title` → `short_summary` (≤60 chars), the
   lens's own label → `category`, and the adjudicated verdict →
   `verdict`. Report findings through the tool *or* as text, not both.
3. **Show the funnel** — raw findings vs survivors, per lens, from the
   returned `ledger`. A lens with zero raw findings *and* a coverage
   ledger is a result: say what it checked. A lens whose agent failed
   is *not* a clean lens — it left that surface unreviewed, and saying
   "no findings" for it is the one reporting error that makes the whole
   review misleading rather than merely incomplete.
4. **Surface the leads** — unverified observations verifiers noticed in
   passing, clearly labelled as unverified, at the end.
5. **Never apply fixes as part of the review.** If the user asks for
   fixes afterward, re-report with `outcome` set per finding.
