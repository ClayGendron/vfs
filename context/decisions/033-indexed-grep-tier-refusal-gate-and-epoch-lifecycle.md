# 033. Indexed Grep Tier: Refusal Gate, Runtime Budgets, Batch Epoch Lifecycle

- **Status:** accepted 2026-08-05 (the shaping-review fork resolutions
  and the slice-pinned design calls of spec 093, all made or confirmed
  by Clay that day). Recorded as an ADR 2026-08-05 at the spec's
  mining pass — the decisions were carried by the spec until it landed
  (same day) and was mined; the spec rests in
  `../specs/archive/093-grep-content-search/`. Builds on ADR 013
  (flag-partitioned overlay), ADR 031 (pattern-only seam, probe), and
  ADR 032 (compile chokepoint, LIKE-superset doctrine, name-vs-path
  dispatch); the underlying index research is the 2026-07-13
  grep-index memo, the 2026-07-14 posting-storage memo, and 072's
  `spike-results.md`.
- **Date:** 2026-08-05
- **Deciders:** Clay Gendron
- **Decided by:** human (the three shaping forks) and AI-with-approval
  (the implementation-pinned calls, confirmed at the landing reviews)

## Context

Grep's contract was fully specified and implemented nowhere: the verb,
ingress table, `Match` model, and conformance rows all existed while
both backends omitted `grep` from `capabilities()`. 072 §6 fixed the
hard requirement — grep stays fast at millions of documents, so a
LIKE-prefilter scan is never the default public behavior — and the
byte-trigram index research (memo + spike) fixed the machinery. What
remained were the contract decisions: what refuses, what budgets, how
the index publishes, and how grep crosses the storage seam. Spec 093
made them; this ADR is their durable record.

## Decisions

### 1. The refusal gate is pattern-shaped, and refusal names its override

Four steps, in order: compile (`re.error` → `invalid`); plan grams
from the **folded** pattern unconditionally for every case mode; a
plan with no required gram (`GramAny`) refuses with the classified
kind **`vfs.invalid.unindexable_pattern`** whose message names
`allow_scan=True`; `allow_scan` runs the same scan/verify tier that
serves the overlay. There is no weak-selectivity refusal —
selectivity is a runtime budget (decision 3), never a plan-time
prediction. Silent false negatives are forbidden everywhere: the
index may only ever narrow candidates that the unconditional Python
`re` verification then confirms.

The ADR 007 tension is on the record: `allow_scan` selects an
execution tier, which brushes against "parameters select what, never
how." It is justified as the escape hatch from a refusal — without it
a refused pattern is unanswerable; with it, no pattern is
unanswerable, only un-silently-slow. Archived story 007's "never
reject a valid pattern" position is honored in sum: refusal names its
own override.

### 2. Folded planning, sensitive verification, and the fold definition

Candidate lookup always plans against the folded gram stream;
verification always compiles the caller's original pattern with the
conformance-pinned modifier wrapping (`fixed_strings` escape →
`word_regexp` wrap → case flags, smart case judged on the raw
pattern). The fold is raw folded codepoints — newline-normalize,
Turkic-i pre-fold, `casefold`, **no Unicode normalization** — and the
index format version covers its definition. Consequence, pinned by
conformance: folding can shorten a pattern below gram size (`ẞ` →
`ss`), flipping indexable → refused; the opt-out still answers
case-sensitively.

### 3. Selectivity is a runtime budget; truncation is loud and names refine moves

Declared module constants (spike-derived): ~10,000 candidates
fetched+verified, a posting-byte budget enforced **before** blob
fetch via the stored `byte_size`, and a wall-time deadline checked
between ladder stages. A tripped budget appends a warning-severity
**`vfs.budget_exhausted.truncated`** record naming the refine moves
(narrow the pattern, add globs or ext filters, or scope with paths) —
never silent partial results. The constitution's refine-or-cursor
mechanism is satisfied by refine-guidance for now; the **cursor is
deliberately deferred to the MCP pass** as a read-family-wide
question (glob/ls/tree share the gap; keyset resumption over
path-sorted results is the recorded sketch).

### 4. Corpus grain: documents are chunks, results are entries

Posting `doc_id` is the chunk autoincrement id; result rows are
entries. Candidate chunk ids dedupe to entries **before** any content
fetch, so chunk overlap can never multiply rows. The execution ladder
is rarest-first by `doc_count`, default k=4 with early exit and the
empty-posting short-circuit; structural gates (globs LIKE-superset
fan, ext prefilter, liveness, meta exclusion) join before content
fetch on both sides, and the authoritative compiled filters gate
every candidate in Python.

### 5. The overlay is flag-partitioned and the scan engine is one body of code

Index side `WHERE encoded`, scan side `WHERE NOT encoded` — mutually
exclusive by one column (ADR 013 D3, discharged). One scan executor
serves three callers: the permanent dirty overlay, the `allow_scan`
opt-out, and `invert_match` — which is **scan-shaped by
construction** (no occurrence index narrows non-matches) and runs
under the runtime budgets *without* requiring `allow_scan`; the
refusal gate is pattern-shaped, and the pinned conformance row
(default invert succeeds) is the contract. Recorded so nobody later
"fixes" invert into a refusal without a decision.

### 6. Index lifecycle: batch only, one admin verb, one publish transaction

No per-write index maintenance — writes stamp `chunked`/`encoded`
false and nothing else. **`reindex()`** is a backend admin method
beside `close()`, outside the routed surface and invisible to
`capabilities()`. Phases: chunk the dirty (version-guarded flips; a
raced entry stays dirty), build the full posting set under a fresh
epoch in `(epoch, gram_key)`-sorted byte-capped batches (invisible
until publish), then **one publish transaction** flips the covered
entries' `encoded` flags and the epoch pointer together — the
pointer flip is a CAS on the epoch the build started from
(rows-affected checked; a rival publishing first classifies
`conflict`), because a flag flip published before the pointer would
let a reader treat an entry as index-side while its grams are
invisible. Old-epoch reclamation is a separate step; the
idempotent-cheap no-op is the two-part fingerprint (format version +
options hash) plus no-dirty-rows. Readers therefore see old or new,
never a mix — pinned through the `reindex:before-publish` seam.

### 7. Eligibility gates bound bloat, never coverage

A chunk the indexer skips (NUL-bearing binary, > 2 MiB body,
< 3 bytes, > 20,000 distinct grams — zoekt's constants, declared)
simply never sets `encoded` and is scanned forever: ineligible =
`chunked` with zero chunk rows, scan-side residency derivable, no
tri-state column. The codec is delta+varint over sorted doc-ids with
numpy-vectorized decode; every malformed-blob class raises a loud
`PostingCorruptionError` that classifies `internal` — never
silently-wrong results. Posting blobs declare `mysql.LONGBLOB`
(plain BLOB truncates silently at 64 KB).

### 8. Grep crosses the seam as patterns + a probe; the root row rides the pattern batch

The storage contract has no `paths`: scoping crosses only as composed
glob text on `globs`/`globs_not` (ADR 031's seam, inherited whole —
composition, residuation, owner gate, dead-residual routing, the
concurrent stat probe with three-way outcomes). The one grep-specific
refinement of the find-operand law: the probe serves **no** rows for
grep (a root's content test can only happen at storage), so when a
root's path passes the caller's globs its literal path joins the
composed pattern batch as one more member — the root row rides the
pattern batch, not the probe.

### 9. Capabilities derive from the surface; traits name the tier

`DatabaseStorage.capabilities()` returns `storage_ops(self)` minus
`mkedge` (the last classified stub satisfies the mutation family
structurally but is not live — the subtraction is the honesty).
`traits()` declares `grep_tier="indexed"` and
`grep_staleness="overlay"` — `"watermark"` left the vocabulary with
the mechanism it named (shaping fork 1). `"scan"` stays in the
`grep_tier` vocabulary for future backends; the taxonomy conformance
rows gate their refusal assertions on the declared tier.

## Rejected alternatives

- **Serve every pattern from the index, however weak the grams**
  (story 007's posture) — an un-narrowed pattern degenerates to a
  full-corpus fetch+verify; the budget flag would fire on every hot
  pattern and the p99 story collapses. Refusal-with-override keeps
  the default path fast and every pattern answerable.
- **Per-write incremental index maintenance** — couples every write
  to gram encoding, and the research (zoekt, codesearch) is
  unanimous that batch rebuild + a small live overlay is the simpler
  sound design at this scale. The per-chunk `encoded` column stays
  reserved for an incremental future.
- **A query-wide row cap or cursor now** — no wire surface exists to
  carry a cursor; a bare row cap without resumption is a silent-loss
  trap. Deferred whole to the MCP pass (shaping fork 2).
- **Planner upgrades in-band** (bounded char-class expansion,
  alternation cross-products, anchor-tolerant literals) — deferred
  to a follow-up story once the refusal gate has live users (shaping
  fork 3); every refused pattern still runs correctly under
  `allow_scan=True`.

## Consequences

- Implemented by spec 093, landed 2026-08-05 (all four slices;
  commit line in `../specs/STATUS.md`); the spec was mined into this
  record the same day.
- The differential battery
  (`../research/studies/2026-08-05-grep-differential-battery/`) and
  the query-ladder benchmark
  (`../research/studies/2026-08-05-grep-query-ladder-benchmark/`)
  are the permanent acceptance harnesses: re-run them when the
  planner, verifier, ladder, or budgets change.
- The planner-upgrade follow-up story and the MCP-pass cursor are
  the two recorded successors; reindex progress/cancellation also
  waits on the MCP pass, where admin work becomes wire-visible.
- `mkedge` is now the only classified stub between the live tree and
  a fully-derived capability surface (ADR 018's wiring spec owns it).
