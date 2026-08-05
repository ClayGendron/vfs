# 093 — Grep: indexed content search on the database backend (072 Pass C)

- **Status: shaped 2026-08-05** — drafted from 072 §6 and tasks
  19–22, a two-agent survey of the live tree and the design corpus,
  and the ADR obligations recorded since 072 was written; the three
  owner forks (staleness trait vocabulary, Article 2 §3 cursor
  posture, planner-upgrade scope) were resolved by Clay at the
  same-day shaping review — resolutions inline below and in
  `../../open-questions.md`. Planned same day; see `plan.md`.
  **Slice A landed 2026-08-05**: `models/postings.py` (count-prefixed
  delta+varint, numpy-vectorized decode, loud
  `PostingCorruptionError` on every malformed-blob class including
  the int64-wrap sign check) with its 13-row property/corruption
  battery; numpy is a core dependency. Suite 2023 passed, coverage
  100%, `ruff`/`ty` zero.
- **Date:** 2026-08-05
- **Owner:** Clay Gendron
- **Kind:** verb implementation (the last read-family stub) + index
  write/read machinery + one backend admin verb + a storage-protocol
  signature change (grep adopts the pattern-only seam) + the
  conformance flip that makes 14 already-written grep rows run.
- **Depends on:** 072 §6 (the governing design — as corrected below),
  ADR 013 (flag-partitioned overlay; supersedes §6's watermark),
  ADR 030 §7 (globs residuate; content pattern never), ADR 031 D4/D6
  (probe + seam inheritance), ADR 032 §5/§6 (name-vs-path dispatch,
  LIKE-superset doctrine), ADR 023 (find-operand law, meta hiding,
  path-derived ext), ADR 007 (grep is the exact-match verb), the
  2026-07-13 grep-index memo, the 2026-07-14 posting-storage memo,
  the 2026-05-25 tokenizer memo, and 072's `spike-results.md` (every
  budget constant).
- **Relates to:** the multimodal ADR chain (a future derived-text
  corpus must be joinable, not precluded), 056 Pass B/C (MCP surfaces
  reindex progress), story 007 (archived — the strongest
  counter-position to the refusal gate, rebutted below).

## Intent

Grep is fully specified end to end and implemented nowhere: the
router verb, the 17-parameter ingress table, the protocol contract,
the `Match` model, the ripgrep-style renderer, and 14 conformance
rows all landed in earlier passes, and both backends simply omit
`grep` from `capabilities()`, so every row skips. This spec makes the
declared contract true — with the byte-trigram gram index as a core
deliverable (072's hard requirement: grep stays fast at millions of
documents; a LIKE-prefilter scan is never the default public
behavior), and the glob arc's seam and probe obligations discharged
so grep is born on the pattern-only dispatch shape rather than
retrofitted later.

One sentence: **compile, plan folded, refuse the unindexable loudly
(`allow_scan` runs the scan tier), intersect the k-rarest posting
lists, verify every candidate with Python `re`, union the
flag-partitioned dirty side, and cross the storage seam the way glob
now does — patterns and a probe, one call per entry, one snapshot.**

## Corrections to 072 §6 (inputs superseded since it was written)

1. **Dirty overlay predicate**: `revision > watermark` is dead. ADR
   013 D3: index side `WHERE encoded`, scan side `WHERE NOT encoded`
   — mutually exclusive by construction; reindex flips flags only
   with a version-guarded update (`SET encoded = true WHERE id = :id
   AND revision = :seen`).
2. **Epoch fingerprint**: two-part (index format version + options
   hash). The max-revision watermark part is superseded; the
   idempotent-cheap no-op check becomes "no rows awaiting chunking or
   encoding," not a watermark comparison.
3. **`grep_staleness` trait value `"watermark"`** names a dead
   mechanism. Replaced with `"overlay"` — staleness is bounded by
   the flag-partitioned scan side, not a timestamp. (Resolved by
   Clay, 2026-08-05, at the shaping review.)
4. **No scan-tier backend exists.** `InMemoryStorage` is a
   construction-only `DatabaseStorage` subclass (ADR 028), so grep
   lands everywhere at once and `grep_tier` is `"indexed"` for every
   shipped backend; the `"scan"` value stays in the vocabulary for
   future backends. The conformance `allow_scan` row holds: the
   parameter is accepted and meaningful (it is the refusal opt-out).
5. **MySQL is in-tier** and its plain `BLOB` silently truncates at
   64 KB: posting blobs (and any other LargeBinary this pass adds)
   declare `mysql.LONGBLOB` via `with_variant`.
6. **ADR 023 §2's anchor-channel language** is read as revised by
   ADRs 030/031: the find-operand law survives, carried by the probe
   and the root-row rule, not by a per-anchor dispatch channel.

## Shape

### 1. The seam: grep crosses storage as patterns + a probe

The storage contract loses `paths` and keeps three pattern channels:
`pattern` (content regex — never residuated, never a path pattern,
per ADR 030 §7) and `globs`/`globs_not` (path patterns — already
tuples, now carrying the composed, residuated, entry-local scope).
One call per entry, one transaction, one snapshot. `observations=`
grouped dispatch is untouched. The protocol family docstring's
"grep still carries scope `paths` until it adopts the same seam"
sentence retires, and the dead `scope_of` helper is deleted.

Router-side, per scope root (mirroring `_glob_dispatches`):

- Caller `globs` compose under each root via `composed_pattern`
  (name-arm float made spatial, path-arm via `effective_pattern`,
  canonicalization downstream). No caller globs → the root composes
  to `root/**`. Admission is **any** composed glob.
- `globs_not` compose under each root identically. A composed
  exclusion carries its root prefix, so it can never reach another
  root's subtree; exclusion is **any** composed not-pattern.
  Unscoped calls broadcast name-arm filters verbatim and anchor
  path-arm filters at `/`, exactly as glob does (ADR 030 §5/§6).
- Residuation, the owner gate, dead-entry skips, and the
  one-call-per-entry batch are exactly the landed glob machinery.
- **The probe** (ADR 031 D4, adopted verbatim): one batched
  point-read per owning entry, concurrent with dispatch; three-way
  outcomes; a stat-incapable entry's roots are honestly
  undeterminable (the 2026-08-05 posture); ROOT exempt.
- **Root-row rule** (find's operand law: `grep pat /a/file.txt`
  greps the file): the router matches each root's path against the
  caller's `globs` (name-arm by name, path-arm by namespace path; no
  globs = automatic hit) and, on a hit, adds the root's literal path
  as one more composed member so the storage scan covers the root's
  own content — the content test can only happen at storage, so for
  grep the root row rides the pattern batch, not the probe. Roots
  whose names contain glob metacharacters inherit whatever literal
  posture the landed glob composition has; no new mechanism.
- **Meta bypass** is already the right rule for free: a composed
  pattern whose literal prefix is meta-addressed lifts `/.vfs` for
  that subtree (ADR 031 D5). Scoping into `/.vfs/...` composes a
  meta-prefixed glob; a call with neither meta root nor meta glob
  keeps the subtree hidden. Pinned by the existing conformance row.
- Grep leaves `_route_fanout`'s generic else-branch; the dispatch
  tests that used grep as the generic-branch specimen re-anchor on
  `glean`.

### 2. Structural pushdowns inside the entry-local call

- `globs` render through the proven LIKE-superset translation with
  the escaped-prefix fan; **verify unconditional** (ADR 032 §6) —
  the authoritative compiled filters gate candidates in Python with
  the name-vs-path dispatch (ADR 032 §5, discharged here).
- `ext`/`ext_not` read the path-derived extension (ADR 023 §5,
  extended to grep as it always should have been); the indexed
  stored column may serve as a prefilter only under the structural
  write-agreement, exactly like glob's pushdown, with the dotfile
  arm and the unconditional Python check.
- Liveness, trash, and meta exclusion ride the same entries-join
  predicates as glob; `kind`-gating to content rows.

### 3. The index (core deliverable — 072 §6 as corrected)

- **Corpus grain**: index documents are **chunks** (the chunk
  autoincrement id is the posting `doc_id`, as the schema already
  pins); result rows are **entries** (one row per matching file, as
  conformance pins). Candidate chunks dedupe to entries before
  content fetch, so chunk overlap can never multiply rows — closing
  the 2026-04-24 memo's measured loss cause.
- **Refusal gate, four steps**: compile (`re.error` → `invalid`);
  plan folded unconditionally for every case mode; `GramAny` → a
  classified **`unindexable_pattern`** refusal naming
  `allow_scan=True`; `allow_scan` runs the scan/verify tier. No
  weak-selectivity refusal tier — selectivity is a runtime budget.
  (ADR 007 tension, on the record: `allow_scan` selects an execution
  tier, which brushes against "parameters select what, never how."
  It is justified as the escape hatch from a refusal — without it a
  refused pattern is unanswerable; with it, no pattern is
  unanswerable, only un-silently-slow. Story 007's "never reject a
  valid pattern" position is thereby honored in sum: refusal names
  its own override.)
- **The fold**: raw folded codepoints — newline-normalize, Turkic-i
  pre-fold, `casefold`, **no Unicode normalization**; candidate fold
  ⊇ verifier case orbit, pinned by the orbit-scan test; the
  index-format-version covers the fold definition.
- **Execution ladder**: rarest-first by `doc_count`, default k=4
  with early exit; empty-posting short-circuit; posting-byte budget
  enforced **before fetch** via `byte_size`; numpy varint decode;
  intersect; map chunk ids → entries; the §2 structural/liveness
  join **before** any content fetch; fetch survivors' content;
  **unconditional Python `re` verification**; union the scan side.
- **Scan side / dirty overlay**: `WHERE NOT encoded` (chunks not yet
  indexed, plus entries not yet chunked) is scan-grepped and
  unioned; the two sides are mutually exclusive by flags. The
  scan/verify machinery is permanent keepable code — verification
  layer, `allow_scan` engine, and overlay in one.
- **Index-ineligible content stays scan-side forever** — false
  negatives are never acceptable, so the ingestion gates bound index
  bloat, never coverage: a chunk the indexer skips (NUL-bearing
  binary, > 2 MiB body, < 3 bytes, > 20,000 distinct grams) simply
  never sets `encoded` and is always scanned. Recommended constants
  are zoekt's, as declared module constants.
- **Budgets** (from the spike): ~10,000 candidates fetched+verified,
  a few MB of posting bytes, a wall-time deadline — capped queries
  surface a truncation flag (a warning-severity record on the
  result), never silent partial results — the flag's message names
  the refine moves (narrow the pattern, add globs/ext, scope with
  paths). Constitution Article 2 §3's refine-or-cursor mechanism is
  satisfied by refine-guidance for now; the cursor is **deliberately
  deferred** (resolved by Clay, 2026-08-05): pagination is a
  read-family-wide question (glob/ls/tree share the same gap) and
  belongs with the MCP pass, where result transport is designed —
  keyset resumption over path-sorted results is the recorded sketch.

### 4. Index lifecycle: batch only, one admin verb

- No per-write index maintenance; writes keep stamping
  `chunked`/`encoded` false (already landed).
- **`reindex()`** is a backend admin method beside `close()` —
  outside the sixteen-verb routed surface, invisible to
  `capabilities()` (072's ruling; constitution Article 5's
  progress/cancellation ask is recorded for the MCP pass, where
  long-running admin work becomes wire-visible).
- Reindex chunks the unchunked (structure-aware splitter, landed),
  builds posting rows under a new epoch, publishes with a
  **compare-and-set pointer flip** (rows-affected checked), flips
  flags with the version-guarded update, reclaims old epochs as a
  separate step, and is idempotent-cheap when nothing is dirty.
- Posting bulk-insert: sorted by `(epoch, gram_key)`,
  size-partitioned, byte-capped batches (SQLAlchemy pages by
  parameter count only; MSSQL's cap yields 349 rows/statement at six
  columns; a page of big blobs must shrink by bytes).
- **Codec** (`models/postings.py`, new): delta+varint over sorted
  doc-ids, numpy-vectorized decode; the 013 hardening list carries
  over — encode bounds ids to signed-BIGINT, decode rejects
  negative counts, over-wide values, out-of-range ids, trailing
  data — loud `PostingCorruptionError`, never silently-wrong
  results. numpy becomes a core dependency.

### 5. Output modes, matches, and budgets

- `Match` regions are 1-indexed line spans with the hit line and
  region text, per the landed model; context lines come free from
  the content already fetched for verification.
- `output_mode="files"` short-circuits a file at its first verified
  match and returns rows with neither `content` nor `matches`;
  `"count"` reports the match count on `score` (both pinned by
  conformance). Candidate-side, these modes still fetch content —
  verification requires it; the two-stage id-first shape from the
  2026-04-24 memo is the internal ordering (§3's ladder), not a
  different contract.
- `max_count` stays ripgrep's per-file `-m`; the router passes no
  `row_cap` for grep.
- `invert_match`, `word_regexp`, `fixed_strings`, `case_mode` wrap
  the compiled pattern exactly as the conformance rows pin;
  `fixed_strings` plans grams from the literal directly
  (`grams_for_fixed_string`). `invert_match` is scan-shaped by
  construction (no occurrence index narrows non-matches) and runs
  the scan side under the runtime budgets without `allow_scan` —
  the refusal gate is pattern-shaped, and the pinned conformance
  row (default invert succeeds) is the contract.

### 6. Capabilities, traits, conformance flip

- `capabilities()` gains `grep` on `DatabaseStorage` (and thereby
  `InMemoryStorage`); the memory-backend drift pin moves in the same
  commit; task 22's `storage_ops(self)` derivation becomes possible
  once grep completes `SupportsPatternSearch` — adopt it here.
- `traits()` declares `grep_tier="indexed"` and the resolved
  staleness value (correction 3).
- All 14 conformance grep rows go live on every engine leg; the
  pattern-class taxonomy (fully / partially / unindexable, from the
  grep-index memo) joins the conformance harness, plus the
  fold-shortening edge case.

### 7. Out of scope (recorded)

- **Planner upgrades** — bounded char-class expansion (`[fF]oo`
  refuses while `(?i)foo` indexes — the highest-value refusal-set
  shrink), alternation cross-products, anchor-tolerant literal
  extraction. All three deferred to a follow-up story once the
  refusal gate has live users (resolved by Clay, 2026-08-05): the
  planner is audited landed code whose failure mode is the forbidden
  silent false negative, and every refused pattern still runs
  correctly under `allow_scan=True`.
- The Postgres `pg_trgm` provider override (narrow win, always
  behind the refusal gate) — demand-gated.
- Derived-text corpora for media (multimodal chain) — the corpus
  join must not preclude it; nothing built here.
- `globs_not` on glob; the `**`-residual discharge optimization
  (ADR 030 §8) — unchanged.

## Verification obligations

- **Existing harnesses green unchanged**: the placement-invariance
  battery, `verify_residuation.py`, the glob conformance rows — the
  seam flip touches shared machinery.
- **Differential battery, grep edition**: extend the
  2026-08-05 study's precedent — one scratch tree, `grep -rn` /
  `rg -uu` legs vs vfs grep over plain and mounted worlds, with the
  allowlist (dotfiles, no ignore files, refusal-not-silent for
  unindexable patterns under the default gate, rg operand exemption
  divergence).
- **Scale rows**: 10k roots into one entry → one grep call + one
  probe; posting-build statement counts chunk within declared
  budgets (recorded-statement assertions on sqlite).
- **Epoch atomicity**: readers see old or new, never a mix
  (constitution Article 5 makes this constitutional, not nice).
- **Overlay exclusivity**: a modified entry never double-hits
  (flag-partition row).
- **Rerunnable benchmark harness**: the spike's query-ladder and
  budget numbers move from one-off to a rerunnable script under
  `research/studies/` (the quality-rubric condition for scoring
  performance above 2).
- Four Docker engine legs green; suite, coverage 100%, `ruff`/`ty`
  zero, no new suppressions.

## Touch points

- `src/vfs/models/postings.py` (new) — codec. `pyproject.toml` —
  numpy core dep.
- `src/vfs/models/code_grams.py`, `chunking.py`, `chunk.py` — landed;
  consumed, not rewritten.
- `src/vfs/storage/protocol.py` — grep signature (seam flip), family
  docstring true-up, `scope_of` deletion, staleness trait value.
- `src/vfs/storage/backends/database/` — `grep.py` (new: planner
  gate, ladder, overlay, scan tier; connection passed in, never
  begins/commits), `backend.py` (stub → live, caps/traits, reindex
  admin verb), `reads.py` (shared fan machinery reuse), `rows.py`
  (LONGBLOB variant).
- `src/vfs/base.py` — `_grep_dispatches` + probe adoption; generic
  else-branch narrows.
- `src/vfs/results/kinds.py` — `unindexable_pattern` classified kind.
- `tests/` — conformance flip, dispatch rewrites, taxonomy rows,
  codec property tests, overlay/epoch rows.
- `context/specs/active/072-database-storage-backend/` — Pass C
  tasks marked owned by this spec; 072 status true-up at landing.

## Slices (each landing leaves the tree green; grep stays undeclared
until the final slice)

- **A — codec.** `models/postings.py` + property tests + numpy.
- **B — reindex.** Chunking + posting build + epoch publish + flag
  flips + the admin verb, exercised by direct backend tests.
- **C — the read pipeline and the seam.** Protocol flip, router
  dispatch + probe, planner gate, ladder, scan tier, output modes —
  test-first against the already-written conformance rows run
  locally.
- **D — the flip and proof.** Capabilities/traits declare grep;
  conformance rows live on all legs; differential battery; scale and
  atomicity rows; benchmark harness; 072 true-up.

## Open questions

None — the three shaping forks were resolved by Clay at the
2026-08-05 shaping review: staleness trait value `"overlay"`
(correction 3), truncation-flag-with-refine-guidance now and the
cursor deferred to the MCP pass as a read-family question (shape
§3), and all planner upgrades deferred to a follow-up story (shape
§7). The `../../open-questions.md` entries record the resolutions.
