# 111 — Assembly and batch shapes: hydration law everywhere, batched maintenance, honest profiles

- **Status: all slices landed 2026-08-18.**
  §1: `reads._observe` re-brands stored paths (`Path._brand`) and
  glob's candidate gate runs `passes_row_filters` over ridden
  `name`/`ext` columns (queried beside `fetched`, never leaked into
  a narrow `columns=` observation) — measured on the finding's own
  20k-row shapes, interleaved arms: glob 311 → 146 ms (−53%), ls
  277 → 204 ms (−26%), counts identical. The ls-precondition lead
  settled by declaration: the storage protocol docstring now states
  paths cross the seam as branded `Path` objects and a bare `str`
  is out of contract (string-holding callers go through the router,
  which resolves). §2: delete accumulates its root posting deltas
  and flushes one `move_postings` batch per call after adjudication
  — nothing in the loop reads segments, refused targets never
  accumulate, and the expired-bucket 1:1 delta lawfully rides the
  rename fast path. Measured at the 10k-target contract,
  interleaved: sqlite 21.8 → 16.0 s (−26%), live Postgres (the
  finding's venue) 48.5 → 36.0 s (−26%). The move/restore executor
  was inspected and left per-pair with the reason recorded: its
  descendant work already batches, the root move is one triple per
  pair (no 10k-per-call contract shape), and the occupant-trash
  interleave would need its own deferral-hazard audit — revisit
  when a measurement names it. §3: `pathterms` carries the
  acknowledged-suboptimality paragraph (corpus-width union, the
  measured numbers, SQL-side join as the named future direction, no
  cap implied). §4: all four engine legs green (Postgres 209, MySQL
  210, MSSQL 211, Oracle 208 — segment-mirror and cascade batteries
  included), both grep ladders identical counts with the zero-hit
  floor at 41.9 ms, full 3.13 leg green (100% coverage).
  **Mined 2026-08-19:** decision set recorded as ADR 047 (branded-Path seam precondition, hydration law for every reader, delete maintenance flushed once per call, move/restore left per-pair with reason, the acknowledged-not-capped profile doctrine). The `_brand` sweep and SQL-side allow-list join stay in the spec as follow-ups. Folder stays as the historical record.
- **Drafted 2026-08-18.**
  Born from the review campaign memo
  (`../../../research/2026-08-18-glob-grep-review-campaign.md`),
  findings 7 (ownership lens), 10, and 11 (scale lens) — three
  measured decay findings, none wrong-results: the read path's
  hydration law adopted by only one of its three readers, a bulk
  verb paying 40% of its time in single-element maintenance calls,
  and a corpus-scaled allocation with no acknowledgment and no
  deadline.
- **Date:** 2026-08-18
- **Owner:** Clay Gendron
- **Kind:** performance and hygiene inside the database backend —
  identical results contractually required everywhere; the bench
  gates exist to prove both the wins and the no-regressions. No
  schema change, no verb or Result movement.
- **Depends on:** ADR 041 (the re-brand-not-re-gate hydration law
  and `Path._brand`), spec 104 / ADR 040 (`move_postings`' batch
  API and the segment-maintenance laws), spec 099
  (`passes_row_filters` and the pattern-gate ownership this
  extends).
- **Relates to:** spec 108 (owns `allow_list_ids`' statement count
  and deadline-between-arms; this spec owns its memory
  acknowledgment — land in either order, the seams are disjoint),
  the never-design-toward-caps rule (§3 is its docstring form).

## Intent

1. **The hydration law has one obeyer.** ADR 041 declared backend
   row hydration a branded site — stored paths are canonical by
   invariant, so re-validating them per row is pure waste — and
   grep's assembly implements it. But `reads._observe`, serving
   read/stat/ls/tree/glob, still runs the full gate per row, and
   glob's candidate loop mints a *second* gated `Path` per
   candidate even though `passes_row_filters` exists for exactly
   that gate. Measured: `Path(str)` 8.77 µs vs `Path._brand`
   0.15 µs per row — 38.9% of a 20k-row glob and 29.4% of a
   20k-child ls, results identical on every arm.
2. **Bulk delete does per-target maintenance a batch API exists
   for.** Each trashed target calls `move_postings` with a
   one-element list (a trash reparent is never the rename fast
   path): 5.01 segment statements per target, and on live Postgres
   at the contractual 10,000-target scale, 29 s of a 72 s delete —
   40% of the verb. Batching the same deltas measured 30–55×
   faster on the maintenance step, and the review's verifier
   cleared the deferral hazards (no read-your-writes on segments
   inside the loop, no id collisions, order-independent keying).
   ADR 040 §2 describes the batched shape; the loop predates it.
3. **The allow-list union is corpus-scaled and says nothing.**
   `allow_list_ids` materializes the scope's whole id union as
   Python sets before `CANDIDATE_BUDGET` can truncate: measured
   103 MB traced peak (+360 MB RSS) and 5.5 s at a 1M-entry scope,
   with the wall clock never consulted. At benchmark scale it is
   ~10 MB and sub-second — fine today, unacknowledged. The
   no-designed-caps rule requires the honest docstring: name the
   profile, name the future direction, never convert it into a
   limit.

Laws that bind the slices:

1. **Identical results, proven.** Every change here is
   behavior-preserving by contract: parity is asserted row-for-row
   against the pre-change implementation on generated corpora
   (paths with every component class the gate distinguishes), plus
   the full suite and conformance legs.
2. **Wins are measured where the finding measured.** Each landed
   change re-runs the finding's own measurement (the 20k-row
   glob/ls profile, the 10k-target delete) and records
   before/after; a change that fails to reproduce its predicted
   win is re-examined, not shipped on faith.
3. **The write path's other users are untouched.** Batching
   delete's maintenance must not change move/copy/restore behavior
   or their cascade semantics; the segment-mirror battery is the
   referee after every verb sequence.

## Shape

- **§1 Hydration law adopted by reads.** `_observe` re-brands
  stored paths (`Path._brand`); glob's candidate gate adopts
  `passes_row_filters` over the ridden `name`/`ext` columns instead
  of minting a second `Path` — honoring the constraint that a
  narrow `columns=` selection can exclude those columns from
  `effective_columns` (ride them for the gate, strip them from the
  observation, mirroring grep's mask discipline). The review's
  adjacent lead — `DatabaseStorage.ls(path="/flat")` with a plain
  `str` dies as a raw `AttributeError` — is settled while in the
  file: the storage seam either declares the branded-`Path`
  precondition loudly or refuses typed; pick one and pin it.
- **§2 Batched delete maintenance.** The delete loop accumulates
  its per-target segment deltas and flushes them through
  `move_postings`' batch path once per call (chunked by the
  declared budgets like every neighbor). The shared move/restore
  executor's same-shaped per-pair call (the review's unverified
  lead) is inspected while here: batched if the same argument
  holds, left with a recorded reason if not.
- **§3 The honest profile.** `pathterms`' module docstring gains
  the acknowledged-suboptimality paragraph: the union is
  corpus-width in memory (numbers from the finding), the future
  direction is pushing the allow-list join into the candidate
  fetch as a SQL predicate, and no size cap is implied. The
  deadline plumbing itself lands with spec 108's loop work; this
  spec only guarantees the acknowledgment cannot land without the
  measured profile beside it.
- **§4 The gates.** Law 2's per-finding measurements, plus the
  ladders: the 25-row unscoped and 12-row scoped grep ladders and
  a glob/ls timing row (20k-row shapes) before and after, identical
  counts everywhere; the 10k-target delete A/B on sqlite and one
  real engine (Postgres, the finding's own venue); the
  segment-mirror battery green across every verb sequence.

## Slices

- **A. Hydration.** §1 with its parity corpus, the ls-precondition
  decision, and the glob/ls measurements.
- **B. Delete maintenance.** §2 with the mirror battery, the
  delete A/B on both venues, and the move/restore-executor
  inspection recorded.
- **C. The profile and the record.** §3's docstring, §4 complete,
  numbers into the status line; spec status updated for the mining
  pass.

## Open questions

- **How far should `_brand` reach?** The hydration law plausibly
  covers other row→model sites beyond reads (tree assembly,
  conformance helpers). §1 lands the measured offenders; a sweep
  for stragglers is cheap follow-up once the pattern has three
  exemplars.
- **The SQL-side allow-list join** (§3's named future direction) is
  a real design with engine-specific shapes (temp tables, VALUES
  joins, arrays); it activates when a workload shows corpus-width
  scopes with tight budgets, and belongs to its own research pass.
