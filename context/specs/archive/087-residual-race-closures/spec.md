# 087 — Residual race closures: redrive over probe, guard every destroy

- **Status:** landed 2026-07-26 (`67aa7bd`, one landing with specs
  086/088; all four engine legs green, throughput at baseline) —
  awaiting the backward-flow mining pass, then deletion.
- **Evidence:**
  `context/research/2026-07-26-writes-topology-review-verification.md`
  (§1 is the confirmed-defect list this spec answers; every defect
  below was reproduced on live engines);
  `context/decisions/025-conflict-redrive-and-single-batch-writer-doctrine.md`
  (redrive doctrine — this spec extends it to the arms that still
  probe-and-classify);
  spec 086 (landed 2026-07-26) — the two-sided guard machinery this
  spec completes; its decision 8 (classify address races at the seam)
  is **partially superseded** by decision 3 below on the campaign's
  evidence.
- **Depends on:** spec 086 (landed).

## Problem

Spec 086 closed the first-order write-vs-topology races, and the
verification campaign proved the machinery it landed — guarded bumps,
guarded claims, the stale-snapshot redrive — flawless everywhere it
fires. But the campaign also reproduced five residual defects, all of
the same two shapes: places that **classify off a probe** the engine's
isolation level can make lie (or that a redrive would answer more
honestly), and places that **destroy or update rows without a guard**
while rivals are not serialized against them. Concretely, on live
engines: a delete applies a stale descendant-rewrite list and strands
a depth-2 row with a live path under a trashed chain; an
overwrite-move purges a rival's committed file with no error and no
trash copy; the absorb arm lands a write's content on a row a rival
delete just trashed while reporting success at the vacated address;
concurrent `parents=True` writes hard-fail the loser's whole batch on
a shared minted ancestor (deterministically on MySQL) where sequential
execution succeeds; and copy/move destination claim races blame the
wrong path with the wrong kind. Beneath these, topology's single-row
claim guards trust `rowcount` unconditionally — a simulated insane
dialect committed torn state — and `retryable` on the same race
depends on which engine you ran.

The unifying fix is already in the tree: when provable current state
cannot be observed, redrive the method from fresh state — never
classify off a snapshot-blinded probe, and never destroy what a rival
may have changed since the last proof.

## Decisions this spec owns

1. **Occupant-vanished arbitration arms redrive.** In write
   arbitration, when the post-`IntegrityError` occupant probe finds
   no row at the conflicted `(parent_id, name)`, the arm raises the
   stale-snapshot signal instead of classifying a non-retryable
   `conflict`: the probe is blinded at REPEATABLE READ (MySQL always,
   Postgres via the path-index escape), and even where it is honest,
   a vanished rival is precisely the case a fresh snapshot resolves.
   This converges all engines with the Postgres 40001 path and
   removes the arms that contradict the mysql family's declared
   `guard_miss` doctrine.
2. **A directory absorbs a directory (mkdir-p parity).** A staged
   directory create that loses arbitration to a directory occupant
   whose stored path matches the request adopts the occupant's
   identity with the "unchanged" outcome — the same forgiveness
   staging already grants sequentially. Ghost refusal (path
   mismatch) and kind mismatches keep their landed classifications.
   Together with decision 1 this makes concurrent ancestor minting
   converge to success on every engine.
3. **Topology destination-claim races redrive** *(supersedes 086
   decision 8's classify-at-the-seam for these arms)*. The
   `IntegrityError` handlers in the move/restore claim and the copy
   subtree insert raise the stale-snapshot signal; the redrive re-runs
   the pair ladder against fresh state, which produces the honest
   per-pair refusal (`not_empty`, `exists`, `wrong_kind`) with the
   caller's own attribution — the campaign showed the seam-time
   classification blames the pair root for child collisions and
   contradicts already-granted `overwrite`. Raw driver text remains
   demoted to detail on whatever the ladder ultimately returns; the
   retry budget is the landed `with_retry` discipline.
4. **Delete applies rewrites from a post-claim re-collection.** The
   pre-claim collection remains for the refusal ladder, but after the
   guarded reparent of each target, descendants are re-collected and
   the rewrite applies to the fresh set — move's `_rewrite_descendants`
   shape, which the campaign verified closes the depth-2 window. A
   late arrival whose rewritten path exceeds the byte budget raises
   the stale-snapshot signal (the redrive's ladder then refuses
   honestly) rather than storing an over-budget path; the transfer
   verbs get the same late-arrival budget check.
5. **Overwrite occupant destruction is guarded.** The occupant-root
   destroy inside the shared move/restore executor becomes a guarded
   statement on `(entry_id, version-at-emptiness-probe)`; a miss
   raises the stale-snapshot signal, and the redrive's fresh ladder
   refuses `not_empty` honestly. A rival committing after the guarded
   destroy blocks on the row lock and takes its own guard miss. This
   closes the silent-destruction window without deciding the open
   trash-the-occupant question (non-goal below).
6. **The absorb arm proves its address.** The absorb update adds a
   `path`-at-probe predicate (both arms), and the executemany arm
   verifies application (per-row rowcount where sane; otherwise the
   read-back compares the stored path) — a miss raises the
   stale-snapshot signal. No version guard: last-writer-wins between
   concurrent writes is by design; only topology relocations (which
   always rewrite the path) must miss.
7. **Topology's single-row claim guards gate on capability.** The
   guarded reparent, the move/restore claim, and decision 5's guarded
   destroy verify by `rowcount` only where the dialect declares it
   sane, fall back to RETURNING where the dialect models it, and
   otherwise refuse with the same classified `unsupported` writes
   uses — never a bare `rowcount == 0` that an insane dialect answers
   with −1. The purge chunk check keeps its lenient form (it sits
   behind the serialization point; the claim guards do not).
8. **Surviving race classifications stamp `retryable=True`.** The
   reprobe-mode guard-miss `conflict` (and any classify arm that
   survives decisions 1–3 and reports a pure timing race) carries
   `retryable=True` — the campaign proved an identical retry succeeds.
   Which engine you run on no longer changes the retry advice for the
   same outcome.
9. **The campaign's repros become pins.** Seam-staged one-shots:
   depth-2 delete re-collection (both orderings of the existing
   depth-1 pin), overwrite-purge rival survival (move and restore
   arms — the rival's row must survive, trash included, or the verb
   must refuse), absorb-address honesty on the catch-retry engines,
   copy child-collision redrive honesty, and a unit-level insane
   rowcount refusal for decision 7. Natural-timing: a concurrent
   ancestor-mint storm (genuine task concurrency, both writers
   `parents=True` under a fresh shared parent, every trial must end
   in two successes) on all four engine legs.

## Acceptance criteria

- Every §1 repro from the campaign memo, re-staged against the landed
  tree, ends in an honest outcome on all four engine legs: no stranded
  descendant at any depth, no destroyed rival row (survives or the
  verb refuses `not_empty`), no success observation naming an address
  a post-commit stat contradicts, concurrent ancestor minting ends in
  two successes, and claim races surface the fresh ladder's refusal
  with the caller's own attribution.
- A guard or claim on a dialect without sane rowcount (and without
  RETURNING) refuses classified `unsupported`; the simulated insane
  dialect commits nothing torn.
- No public `Result` from any of these paths reports
  `retryable=False` for an outcome an identical immediate retry
  resolves.
- Throughput holds: the 10k-entry batch write stays within noise of
  the pre-change baseline on the Postgres and MySQL legs (the changes
  add predicates and a re-collection to topology verbs, not
  statements to the write hot path).
- Full suite, `ruff`, `ty` at zero; coverage held; four engine legs
  green including the new pins.

## Non-goals

- **Trashing move/copy overwrite occupants** — decision 5 guards the
  existing destroy; whether occupants should be trashed instead
  remains the filed open question.
- **A general guarded-statement abstraction.** The campaign's
  extraction review examined and rejected unifying writes' batch
  ladder with topology's single-row guards; decision 7 is a narrow
  single-statement helper, not a merge.
- **Error-envelope attribution polish** (helper `target=` parameters,
  the `already_exists` monopoly, `wrong_kind` adoption) — spec 088.
- **Shared-idiom extractions** (`rows_by_path`, subtree predicates) —
  spec 089, deliberately after this spec so the refactor moves
  already-correct code.
- **Foreign keys, fsck, id-closure collection, isolation changes** —
  unchanged from 086's non-goals.
