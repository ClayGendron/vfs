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
// __SCOPE_CONSTANTS__
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
