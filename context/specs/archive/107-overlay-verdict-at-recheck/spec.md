# 107 — The overlay verdict moves to the recheck: lock-free false-empty repair

- **Status: all slices landed 2026-08-18.**
  Slice A: the two-read protocol in
  `grep_rows` with its race pins: the seam-staged rival demotion, the
  rescued false-empty verdict (mid-call scan), the redrive at the
  authoritative read, statement-cadence pins on both common paths
  (skip: two combined reads, zero pointer reads; scan: one of each),
  the `allow_scan`-with-indexable-pattern row, and the re-pinned
  epoch-ladder battery. Full 3.13 leg green (2,522 tests, 100%
  coverage). **Slice B landed 2026-08-18** — the seam-staged
  rival-demotion race leg green on all four engines (Postgres 207,
  MySQL 208, MSSQL 209, Oracle 206 passed), with the mutant proof
  executed live: reverting the protocol to trust the preamble loses
  exactly the demoted row on SQL Server (`['/a.txt', '/c.txt']`),
  and the repaired protocol serves all three; ADR 042 amended.
  **Slice C landed 2026-08-18** — the §4 gate executed on a
  fresh-built linux-tree store (93,760 files; write 47 s, reindex
  175 s, db 5.0 GB — the spec 105 record reproduced). Write path:
  interleaved 10,000-file batches through `storage.write`, three
  rounds per arm — before median 2.717 s, after 2.701 s (−0.6%,
  noise). Grep path: the 25-row unscoped ladder and 12-row scoped
  study both re-ran with identical counts and recall on every row
  in both arms; the zero-hit floor held (41.6 ms before, 42.0 ms
  after); quiet-store scoped rows within noise. The raced path
  measured once: quiet skip 42.0 ms, steady scan path 45.0 ms,
  raced (advisory false empty rescued mid-call) 43.2 ms — the
  correctness price is ~1 ms, one scan over the demoted overlay.
  Budget constants unmoved. Bench scripts were session-scratch
  repros per the campaign convention; numbers live here.
  **Mined 2026-08-19:** decision set recorded as ADR 044 (the lock-free advisory/authoritative protocol and the rejected mitigations); ADR 042 already carries the amendment note. The trash-stamping fork stays open in ADR 042/044. Folder stays as the historical record.
- **Drafted 2026-08-18.**
  Born from the 2026-08-18 five-lens review campaign over
  `0359c8d..da3cee3` (run `wf_2784b845-963`), whose adversarial lens
  found and executed the one critical defect in the range: on engines
  without the REPEATABLE READ op-isolation pin (SQL Server, Oracle,
  and the GENERIC floor), spec 105's overlay-emptiness gate can skip
  the scan tier on a verdict that a rival write has already
  invalidated, and grep returns `success=True` with the freshly
  written row silently missing. Evidence, all executed on live
  engines: a seam-staged race loses 1 of 3 rows on SQL Server and
  Oracle while sqlite/Postgres/MySQL hold all 3; forcing
  `overlay_empty=False` restores all 3 on both engines (the gate is
  the sole cause); a hook-free natural race (200 files, 12 rounds of
  concurrent grep + rival write) lost a row in 7 of 12 rounds on
  SQL Server. The pointer-only recheck cannot catch it: a content
  write demotes `encoded` but moves no epoch pointer.
- **Date:** 2026-08-18
- **Owner:** Clay Gendron
- **Kind:** a reordering of reads inside `grep_rows`' per-call
  protocol plus its race pins and bench gate. No schema change, no
  write-path change, no contract/verb/Result movement, no new
  `DialectProfile` field, no isolation change anywhere.
- **Depends on:** spec 105 / ADR 042 (the gate this repairs; ADR 042
  is amended by §5), spec 097 (the `StaleSnapshot` redrive machinery
  this reuses), spec 104 (the nomination pipeline the protocol
  wraps).
- **Relates to:** the trash-stamping fork (ADR 042, still open —
  untouched here), the review campaign's unverified lead that the
  GENERIC floor shares the exposure (resolved by construction in §2:
  the repaired protocol is sound without any isolation assumption).

## Intent

Spec 105's law 2 demanded that a false empty verdict "be impossible
within the snapshot the call already trusts" — but the gate reads its
verdict in the *preamble*, and the index-tier statements it vouches
for run *after* it. On engines where each statement sees its own
world (SQL Server's default READ COMMITTED, Oracle's per-statement
consistency, and whatever an unknown GENERIC engine does), a rival
transaction can commit a demotion between the verdict and the
candidate fetch: the demoted row is excluded from the index side
(`encoded = False`) and the scan tier that owns it never runs. The
row vanishes with no error and no truncation record — the forbidden
silent false negative, on the read path whose contract is recall.

The repair chosen (Clay, 2026-08-18) is the one that holds no locks
and never makes a writer wait, even for milliseconds: **read the
authoritative verdict after the reads it authorizes skipping for.**
The mitigation space was assessed and the alternatives rejected
by that constraint: per-engine isolation pins (SQL Server's
lock-free SNAPSHOT requires a database-level option vfs cannot
impose; its REPEATABLE READ fallback takes shared locks that block
writers), a writer-maintained overlay generation (turns the meta row
into a hotspot every write transaction serializes on), and fusing
the EXISTS into the candidate fetch (a single statement is not
point-in-time consistent under SQL Server's locking READ COMMITTED).
Disabling the gate on unpinned engines was sound but strictly worse:
it forfeits the skip and forks the dialects, where the late verdict
keeps both and adds no statement.

Laws that bind the slices:

1. **The verdict that authorizes skipping the scan tier is read
   after every index-tier statement it vouches for.** Any demotion
   committed before the candidate fetch is committed before the
   verdict read, so the verdict sees it and the scan runs; a
   demotion committed after the fetch means the fetch served the
   row's still-encoded version. Either way the row is served —
   false empty is structurally impossible, with no isolation
   assumption, so the guarantee covers the GENERIC floor too.
2. **No locks, no writer involvement.** grep acquires nothing beyond
   the plain reads it issues today; no write-path statement is
   added, changed, or reordered; the meta row is written by publish
   alone, exactly as today. This is the constraint that selected
   the design and the bench gate (§4) exists to prove it held.
3. **Cost neutrality on the common paths.** The quiet-store skip
   path and the busy-store scan path each issue exactly as many
   statements as today. The only new work is a scan-tier run when a
   rival demotion actually landed mid-call — the case where the
   pre-105 pipeline paid the scan on every call.
4. **Recall semantics and everything downstream are unchanged.** The
   scan tier stays a lawful superset re-checked by the verify
   authority; `allow_scan` and `invert_match` callers are untouched;
   truncation reporting (including the budget-exhausted
   "overlay not consulted" record) does not move.

## Shape

- **§1 The two-read protocol.** The preamble keeps the combined
  pointer + overlay-EXISTS read (`_pointer_with_overlay`), but its
  overlay arm becomes *advisory*: a non-empty preamble verdict
  routes the call onto today's scan path unchanged (scan, then the
  post-scan pointer recheck, exactly as now). An *empty* preamble
  verdict defers the decision: after the ladder and candidate fetch,
  the call re-issues the same combined statement — the
  *authoritative* read. Empty again → skip the scan; this read also
  serves as the epoch recheck, so the skip path's statement count is
  unchanged (two combined reads replace one combined read plus one
  pointer recheck; the EXISTS arm measured ≈ 0 in the spec 105
  research). Non-empty now → a rival demotion landed mid-call: run
  the scan tier before assembly, then the post-scan pointer recheck.
  Pointer moved at either read → `StaleSnapshot`, today's redrive.
- **§2 Why this is sound everywhere.** The argument in law 1 needs
  only that a statement never sees *less* than what was committed
  when it began — true on every engine class vfs serves: the
  RR-pinned engines (one snapshot for the whole call, where the gate
  was already sound and the second read is a no-op change), the
  statement-consistent engines (each read sees at least everything
  committed before it), and sqlite's serialized writer. No dialect
  fork, no profile field, no GENERIC carve-out.
- **§3 What the authoritative verdict decides and tolerates.**
  Empty → skip, with results identical to scanning (the spec 105
  contract, now actually held). Non-empty → the scan runs against
  the same overlay arms as today. The budget-exhausted branch
  (`remaining <= 0`) keeps its honest truncation record and never
  forces a scan it has no budget for. Steady-state non-empty
  overlays (index-ineligible rows, unswept trash) behave exactly as
  under spec 105 §3: the preamble's advisory read routes them to the
  scan path and the late verdict costs them nothing.
- **§4 The bench gate — writes and greps, before and after.** Two
  A/B measurements on the linux-tree store, both arms rebuilt from
  the same corpus at the same schema format, interleaved runs,
  medians reported (Clay, 2026-08-18: the spec must prove the repair
  did not regress either audience):
  - **Write path:** the real-write-path batch benchmark (10,000-file
    batches through `storage.write`, the spec 105 slice-A
    methodology) before and after the change. Expected within noise
    — the change touches no write statement — and the gate exists to
    catch the unexpected.
  - **Grep path:** both ladders re-run — the 25-row unscoped ladder
    and the 12-row scoped study — with identical counts required on
    every row and wall-time within noise on the rows the gate
    serves: the zero-hit floor (the skip path — must hold its
    ~41 ms) and the quiet-store scoped rows. The raced path (staged
    demotion mid-call) is measured once and recorded: its cost is
    one scan-tier run, the price of correctness on a path that was
    previously wrong.
- **§5 The record trued.** ADR 042's consequence prose overstates
  the flag's role ("allow_scan callers never consult the gate" — the
  gate actually keys off scan-shaped plans, and an `allow_scan` call
  with an indexable pattern is gated; the code is right, the prose
  is wrong — review finding 9). Amend ADR 042 to name scan-shaped
  calls precisely and to record this spec's protocol as the repair
  of its emptiness-gate consequence; spec 105's archived text stays
  as the historical record, untouched.

## Slices

- **A. The protocol.** §1–§3 in `grep_rows` (+ whatever seam the
  staged tests need beside the existing `grep:after-pointer-read`):
  the advisory/authoritative split, the mid-call scan, the redrive
  arms. Tests: the seam-staged race on sqlite (rival demotion landed
  between preamble and fetch → the row is served, deterministic);
  the `TestOverlayGate` spy battery re-pinned to the late-verdict
  cadence (empty overlay still skips with unchanged statement
  count; unencoded rows still scan; the raced call scans); the
  `allow_scan`-with-indexable-pattern row (§5's prose defect, pinned
  so a refactor that really keys off the flag is caught); the
  missing-meta-row degradation row kept.
- **B. The engine legs.** Per-engine `db_test` race legs, seam-staged
  (deterministic, not sampled): on SQL Server and Oracle the staged
  race that loses a row at `da3cee3` must serve it under the new
  protocol; Postgres/MySQL run the same leg as a no-regression pin.
  ADR 042 amended per §5.
- **C. The bench gate and the record.** §4 executed on the rebuilt
  store — write A/B, both ladders, the raced-path measurement —
  numbers into the status line; budget constants re-derived only if
  the numbers move them (they should not); spec status updated for
  the mining pass.

## Open questions

- **The steady-state overlay set.** Spec 105's open fork (trash
  stamping `encoded = True` on delete) would shrink the overlay the
  advisory read routes to the scan path; it stays its own decision,
  unblocked and unresolved by this spec.
- **Event-loop occupancy of the verify stage.** The review's
  unverified lead that a full `grep_wall_seconds` of synchronous
  matching blocks the event loop even on the Rust engine is out of
  scope here (it is spec 110 material); noted so the raced path's
  extra scan is not mistaken for the fix's venue.
