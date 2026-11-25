export const meta = {
  name: 'backlog-write-on-dev',
  description: 'Write the backlog specs still needed on dev, one Opus writer per spec, then check each against the specs it builds on',
  phases: [
    { title: 'Write', detail: 'one Opus writer per spec', model: 'opus' },
    { title: 'Cross-check', detail: 'quotations of drafted dependencies read again', model: 'opus' },
  ],
}

const TASKS = null
const WORK = 'agents/2026-11-25-the-backlog-converted'
const CHECK = `uv run python ${WORK}/check_shape.py`

const RULES = `
Ground rules.
- Today is 2026-11-25. This checkout contains origin/dev in full (git rev-list --left-right --count HEAD...origin/dev prints "N 0"); the tree at HEAD is dev's tree. Cite code at the commit git rev-parse --short=8 origin/dev prints. dev serves SQLite and Postgres, and an unknown dialect on the generic floor; MariaDB, SQL Server and Oracle are not served. The environment is synced to this tree: uv run python imports the current package.
- Open branches of origin that dev does not contain are listed in ${WORK}/dev-index.md; read one with git show <branch>:<path>, never check it out. Ignore the claude/* and worktree-agent-* branches.
- Run no git command that changes state (no commit, add, checkout, switch, merge, restore, stash, worktree). Edit no file but the one named for this task. Many writers work in this checkout at once.
- Every shell command gets a timeout. Never run the test suite and never run uv sync. Read-only probes are encouraged: grep, file reads, scratch scripts in the session scratchpad run with uv run python.
- The file is under agents/, so AGENTS.md's voice rule binds it: objective and impersonal, no person's name, no "I", "we" or "you", nothing about who wrote or decided anything; "Decided <date>: ..." for a ruling. The callers of vfs (agents, developers, ETL pipelines) may be named. One line per paragraph.
- Before returning, run: ${CHECK} <the file written> (timeout 60 seconds) and fix every fault it prints, except a "dead link" to another spec of this conversion that is not written yet.
`

const SCHEMA = {
  type: 'object',
  properties: {
    spec_file: { type: 'string' },
    decisions: { type: 'integer' },
    choices_to_confirm: { type: 'array', items: { type: 'string' }, description: 'each choice left to confirm, with the side taken' },
    waits: { type: 'array', items: { type: 'string' }, description: 'any choice with no reversible side, which the build waits for' },
    builds_on_unbuilt: { type: 'array', items: { type: 'string' } },
  },
  required: ['spec_file', 'decisions', 'choices_to_confirm', 'waits'],
}
const CHECK_SCHEMA = {
  type: 'object',
  properties: { consistent: { type: 'boolean' }, corrections: { type: 'array', items: { type: 'string' } } },
  required: ['consistent', 'corrections'],
}

const draftLine = t => ({
  amend: `A draft exists at ${t.dir}/spec.md, written against main at 0ed462f in an older nine-section shape. Its design is sound but its facts and names moved on dev, as the reassessment says. Rewrite it in the template's shape, keeping what still holds and correcting what moved; the file is overwritten.`,
  rewrite: `A draft exists at ${t.dir}/spec.md, written against main at 0ed462f. The reassessment says the ground under it changed; read it as material only and write the spec anew in the template's shape; the file is overwritten.`,
  discard: `A draft exists at ${t.dir}/spec.md, written against main at 0ed462f, which the reassessment says not to reuse: dev built most of it. Write only what remains, anew; the file is overwritten.`,
  none: `No draft exists; write the spec anew at ${t.dir}/spec.md (create the directory).`,
}[t.draft] || '')

const writePrompt = t => `Write one specification of the vfs backlog, against the current dev branch, so that a reader who did not write it could find it fit to build.

The unit: key ${t.key}, "${t.title}", gate ${t.gate}, roadmap stories ${(t.stories || []).join(', ') || 'none named'}. Its source is the numbered spec context/specifications/archive/${t.source}/ (spec.md, and plan.md and tasks.md where present).
What dev already holds of it (verdict "${t.verdict}"): ${t.covered_by || 'nothing'}.
What remains, which is what this spec specifies: ${t.remaining || 'the whole unit'}
${draftLine(t)}
Other specs of this conversion it builds on, which may or may not be written yet: ${(t.deps_dirs || []).map(d => d + '/spec.md').join(', ') || 'none'}.
Dependencies and changes the reassessment names: ${(t.new_deps || []).join('; ') || 'none'}.
Roadmap decisions involved: ${(t.decisions || []).join(', ') || 'none'}.

Read, in this order.
1. agents/templates/spec.md, which is the shape, followed exactly: the first paragraph, the sections in their order, Choices to confirm for what is not settled. Then one worked example on dev: agents/2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md.
2. ${WORK}/reassessment/${t.group}.md at the section for ${t.key}: the state of this unit against dev, and the main input.
3. ${WORK}/units.md (the map of every unit and its directory; sibling specs are cited as ../<directory>/spec.md) and ${WORK}/dev-index.md.
4. Each dev work directory, built spec or open branch the reassessment names for this unit, read where it covers or touches this unit. A shape this spec relies on from one of them is quoted by its decision number.
5. The study of the source, ${WORK}/studies/${t.study_group}/${t.source}.md, and the decision verifications under ${WORK}/decisions/ for the roadmap decisions named: background written against 0ed462f, to be re-checked against dev before anything from it is used.
6. context/standards/roadmap.md at the stories named (as it stands on dev), context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md for names and arguments, context/standards/constitution.md, and documentation/maintainers/how-we-name.md.
7. The source spec, then the tree. Every verb, argument, error kind, module, path, table, column and count is checked against dev before it is written down.

What the spec must hold.
- Only what remains on dev: what dev has built or specified is cited under Builds on, never specified again.
- Every choice the build would otherwise make is decided with its reason and precedent; what the rulings, the tree and precedent do not settle goes under Choices to confirm, with the side taken (the additive or cheaper-to-reverse one) and why.
- Cost against AGENTS.md's reference deployment and the least generous engine served (Postgres or SQLite), with declared budgets, never hardcoded sizes.
- Tests named by file and node at the layer the behaviour lives, following the layout that exists under tests/ on dev; counts and states, never clocks; the Postgres leg where storage changes; a leak test where rights change.
- What it was not able to check, under Not checked.
- No more length than deciding everything takes. Do not carry the source's history or status lines.
${RULES}
Return the summary.`

const checkPrompt = t => `Check one specification against the specifications of this conversion it builds on, now that they are written, and correct what no longer agrees.

The spec is ${t.dir}/spec.md. It builds on: ${(t.deps_dirs || []).map(d => d + '/spec.md').join(', ')}. For each place it quotes or relies on one of them (a decision number, a name, an argument, an error kind, a table, a test), open that spec as it stands and compare. Where they disagree, the depended-on spec wins on what it owns: correct this spec's quotation, its design text and any test that used the stale shape. If one of them does not exist yet, leave the quotation and say so under Not checked. Also confirm that every relative link in the spec resolves, and fix those that do not. Edit only ${t.dir}/spec.md.
${RULES}
Return whether it was consistent and each correction made.`

const keys = args.keys
const items = keys.map(k => TASKS[k])
let results
if (args.mode === 'check') {
  results = await parallel(items.map(t => () => agent(checkPrompt(t), { label: `check:${t.key}`, phase: 'Cross-check', schema: CHECK_SCHEMA, model: 'opus' }).then(r => ({ key: t.key, check: r }))))
} else {
  results = await parallel(items.map(t => () => agent(writePrompt(t), { label: `write:${t.key}`, phase: 'Write', schema: SCHEMA, model: 'opus' }).then(r => ({ key: t.key, dir: t.dir, write: r }))))
}
const missing = keys.filter((_, i) => !results[i] || !(results[i].write || results[i].check))
if (missing.length) log(`No result from: ${missing.join(', ')}`)
return { results: results.filter(Boolean), missing }
