# 086 — Write-vs-topology coherence: two-sided guards on the parent row

- **Status:** landed 2026-07-26 (`67aa7bd`, one landing with specs
  087/088; all four engine legs green, throughput within noise) —
  awaiting the backward-flow mining pass, then deletion. Decision 8's
  classify-at-the-seam arm is partially superseded by spec 087
  decision 3 (verification campaign,
  `../../../research/2026-07-26-writes-topology-review-verification.md`).
- **Evidence:**
  `context/research/2026-07-25-write-vs-topology-adversarial-campaign.md`
  (executed repros; §7 is the decision list this spec answers);
  `context/research/2026-07-25-write-vs-topology-prior-art.md`
  (precedent per decision; §4 leans);
  `context/open-questions.md` — the torn-path-cache entry (amended
  2026-07-25 with the campaign's corrections);
  spec 079 (statement attribution — the discipline this spec extends
  from the write family's own rows to the parent row and to topology);
  `context/decisions/025-conflict-redrive-and-single-batch-writer-doctrine.md`
  (the constraints that stand: writes are never serialized with
  topology; retryable outcomes redrive the whole method).
- **Depends on:** spec 085 (landed) — delete always trashes, sweep is
  the only destroyer; the guard work below assumes that verb surface.

## Problem

Writes are deliberately not serialized with topology verbs, and the
campaign proved the current optimism is unguarded in both directions.
Confirmed with executed repros on live engines: a write creating under
a concurrently relocated directory commits a torn path cache
(MySQL/MSSQL/Oracle, deterministic); the reverse ordering — a rival
write committing between a topology verb's descendant collection and
its reparent — tears **Postgres too**, falsifying the ledger's
Postgres-safe claim; a rival uncommitted during the purge's final
re-collection lands a permanent orphan; copy stamps metadata and body
from two reads and tears them; edit reports success at addresses that
no longer exist because subtree rewrites bump no versions; torn ghosts
name-squat their addresses and absorb later lawful writes (silent data
loss without a race by the caller); purge orphans content rows the
schema's zero foreign keys never catch; and topology address races
leak raw driver text as `unavailable/retryable=True`.

The survey's structural finding frames the fix: every surveyed system
that survives this race locks the parent, refuses to materialize
paths, or forces a shared arbitration row into both commits. vfs does
none of the three — and the ratified constraints (materialized path
cache, single-batch-writer throughput doctrine, READ COMMITTED
topology pin, no background work, 10k batches) rule out locks,
schema inversion, and isolation pins. What remains is the third
option, and vfs already owns the machinery: **the parent row, whose
version every child write already bumps, becomes the shared
arbitration cell both sides guard on.** Conditional-update-verified-
by-rowcount is the field's standard part (juicefs ships it on our
engines; Oak's commit root is the same shape), and retry means
re-deriving the whole operation from fresh state — never patching a
stale intermediate.

## Decisions this spec owns

1. **The write side guards its parent bumps.** `_bump_parents` (and
   every write-family parent touch) becomes a guarded UPDATE on
   `(entry_id, path-at-snapshot)`, rowcount-verified per `chunked()`
   chunk against the chunk's id count. A guard miss aborts the whole
   batch — the torn creates are uncommitted inserts in the same
   transaction and roll back with it — and classifies a retryable
   `conflict`, redriving the method from a fresh snapshot under the
   landed retry discipline. The guard predicate is the path, not
   `parent_id` (a grandparent's relocation must miss too). This
   closes the forward torn-path ordering on every carrier — delete,
   move, restore, and the purge-destroyed-parent case, which
   precedent treats as one failure mode with relocation (`S_DEAD` is
   set by rmdir and rename-over-target alike) — **and the residual
   purge window**: a rival's parent bump blocks on the purge's
   uncommitted entry delete, resolves against the post-commit state,
   misses, and takes its insert down with it. Write-side
   revalidation is the only side that can close that window; no
   purge-side re-read ever sees an uncommitted rival.
2. **The topology side guards its claim on the same cell.** Each
   topology verb's reparent/claim UPDATE on the target row gains a
   `version`-at-snapshot guard. Every child create/update bumps the
   parent's version, so a rival write committing between the
   verb's descendant collection and its reparent flips the guard;
   the verb redrives from a fresh snapshot, and re-collection is
   correctness by construction (the FreeBSD shape: anything resolved
   before your serialization is presumed stale and re-derived). This
   closes the reverse ordering on every engine, Postgres included.
   Descendant path rewrites still bump no descendant versions — the
   detection lives in the guards, not in version flooding.
3. **Zero-row guard outcomes are interpreted per engine.** On the
   mysql family, a 0-row guarded UPDATE at REPEATABLE READ is
   ambiguous (snapshot staleness vs a removed row) and maps to
   retry-the-whole-method; elsewhere a re-probe classifies the miss
   honestly (`not_found` vs `conflict`). SQLAlchemy takes no position,
   so this is declared `DialectProfile` knowledge, beside the landed
   retry taxonomy.
4. **The write family's own-row guard gains the path predicate.**
   Spec 079's guarded material update adds `path`-at-snapshot beside
   `version` (both the VALUES-join and executemany arms), closing the
   edit/overwrite false success: a target whose ancestor was
   relocated mid-window now misses the guard and classifies
   `conflict` instead of reporting success at an address that no
   longer exists. The observation-honesty contract — the observation
   equals a post-commit stat of its path — is restored and pinned on
   the exposed engines explicitly (Postgres redrives either way and
   would mask a regression).
5. **Arbitration refuses to adopt an incoherent row.** Write
   arbitration by `(parent_id, name)` additionally compares the
   matched row's stored path to the requested path; a mismatch
   classifies retryable `conflict` and never updates the row. This
   blocks the ghost name-squat data loss for any legacy torn row and
   is deliberate defense-in-depth beneath decisions 1–2.
6. **Copy reads metadata and body as one observation.** The subtree
   fetch joins content (`content_joined()`), chunked under the
   existing bind and memory budgets, so stamped `content_hash`/
   `size_bytes`/`lines`/`mime_type` and the copied body come from the
   same read; the occupant-overwrite arm gets the same treatment. If
   a budget ever forces a second read, it pins to the first read's
   observation and a mismatch surfaces as typed `conflict` — never a
   silent tear.
7. **Purge deletes entries first; side tables follow the verified id
   set; sweep reclaims fenced orphans.** The purge's per-chunk order
   inverts: entry rows go first, and side-table deletes derive from
   the ids actually deleted (rowcount-verified), so a rival's
   `_replace_content` can no longer slip a fresh content row past an
   already-issued side-table delete. The sweep verb's retention arm
   additionally reclaims content rows that reference no entry and are
   older than a declared age fence (the field's standard mechanism —
   juicefs 1h, Oak 24h — sized conservatively at 24h), reporting each
   reclaim as a warning-severity observation. Within one invocation,
   no background work; this also drains rows leaked before this spec
   lands.
8. **Topology address claims classify at the seam.** The destination
   claims in restore/move/copy catch `IntegrityError`,
   retry-and-reprobe (the no-SAVEPOINT shape: re-run the probe, let
   application logic return the honest answer), and classify
   `exists`/`conflict` with the caller's own path attribution — the
   verb is classification input, raw driver text is demoted to
   detail, and trash-internal addresses never surface. The Postgres
   unique-path-index escape classifies through the same seam.
9. **The windows get seams, and the race family gets tests.** New
   declared seams: `delete:post-collect` (between descendant
   collection and reparent — the reverse-ordering window),
   `purge:pre-entry-delete`, and `restore:post-resolve`. The test
   family has two legs: seam-staged one-shot repros for every closed
   window (all four carriers, both orderings, the residual window,
   the copy tear, the edit false success, the address race), and
   two-instance natural-timing storms (N in the low thousands,
   seeded, with the campaign's integrity audit) on the four engine
   legs — the campaign's ~500 ms windows are invisible to seam-only
   tests, and pjdfstest confirms there is no corpus to borrow.

## Acceptance criteria

- Every campaign repro family, re-run against the landed tree on all
  four engine legs, now ends in an honest classification or a clean
  redrive: no torn path (any carrier, either ordering, Postgres
  included), no residual-window orphan, no copy metadata/body tear,
  no false-success edit/write, no adoption of an incoherent row —
  integrity audit clean over 30-round storms per engine.
- Guard misses classify per decision 3's per-dialect table; a
  seam-staged miss on each engine pins the declared outcome.
- Seeded orphan content rows older than the fence are reclaimed by
  sweep with warning observations; younger rows survive; entry-first
  purge ordering pinned by a seam-staged rival at
  `purge:pre-entry-delete`.
- No raw driver text on any public `Result` from the address races;
  classification rows pinned per engine and per verb.
- Throughput holds: a 10k-entry batch write's wall-clock stays within
  noise of the pre-change baseline on the Postgres and MySQL legs —
  the guards add predicates to existing statements, not statements.
- The natural-timing storm family lands in `tests/` behind the engine
  markers and passes on all four legs; the exposed engines are
  asserted explicitly.
- Full suite, `ruff`, `ty` at zero; coverage held; four engine legs
  green.

## Non-goals

- **A standalone fsck/repair verb** (two-way path-vs-parent-chain
  reconciliation, constructive path repair behind a flag, destructive
  reclaim doubly gated). The survey's strongest consensus says vfs
  wants one — no-FK peers all ship it — but it is its own story;
  decision 7's fenced reclaim inside sweep is the compliant subset
  this spec lands.
- **Foreign keys.** Declined for now: unanimous no-FK precedent among
  bulk-load peers, and decisions 1 and 7 close both orphan classes at
  the application layer. Reopening is a new entry paired with the
  fsck story.
- **Id-closure subtree collection.** Path-LIKE collection stays; the
  two-sided guard makes a stale list unable to commit. The id-closure
  rewrite remains the recorded alternative if a legacy-torn-row
  healer is ever demanded beyond decision 5's refusal.
- **Isolation changes** — the READ COMMITTED topology pin is
  load-bearing for refusal correctness and stands.
- **MSSQL cold-start first-touch behaviors** under an in-flight
  topology transaction (campaign §5.5 leads) — filed in
  `open-questions.md`, not owned here.
- **The mysql-family per-row UPDATE round trips** (spec 080) — the
  guarded bump inherits that cost profile; the set-based fix stays
  080's.
- **Trashing move/copy overwrite occupants** — the open
  overwrite-occupant question is untouched by this spec.
