# 122 — grep serves across close: the verify pool follows the sibling law

- **Status: landed 2026-08-25.**
  The sibling law landed three ways: close shuts *and clears* the
  verify pool (every close, so a re-minted pool is owned by the next
  close) and stops cancelling queued batches — their greps are still
  awaiting, and a served call beats a poisoned one; `_run` serves the
  batch inline when a submit races the shutdown (one on-loop batch in
  the close window, never a raw escape); and the ready latch falls
  with close, so the first op after close re-runs the idempotent
  first touch instead of serving a catalog miss off a disposed pool
  (found by the new battery row on the memory leg — the `:memory:`
  backend's first post-close op previously failed retryable).
  Pinned by the re-shaped shutdown pin (re-mint asserts), the
  mint-after-close ownership pin, the seam-staged close-race row, and
  a backend-agnostic conformance row (`test_pattern_search_serves_
  after_close`) on the memory leg and all four engine legs. The
  review's 24-in-flight-greps + close repro re-run: 24/24 served,
  zero raw escapes. Mutants proven under safe-restore, ledger rows
  P8/P9/P10. The close-refusal question recorded in
  `open-questions.md` as ruled. Gates: 3.13 CI leg green at 100 %
  coverage; engine legs green at +1 — Postgres 211, MySQL 213,
  MSSQL 213, Oracle 210.
- **Amendment (2026-08-25, spec 129):** "one on-loop batch in the
  close window" understates the bound. A grep that captured the pool
  before close serves *all* its remaining verify batches inline
  (executed: a raced grep over a >32 MiB corpus ran both batches on
  `MainThread`), and reindex — riding the same hop since spec 120 —
  serves its captured phase's remaining hops inline (the whole split,
  1.56 s on-loop at 20,000 files). Behavior is correct throughout;
  the bound is verb-sized, now stated that way in `offload.py` and
  ADR 048, and pinned from reindex's side by spec 129's
  `test_a_reindex_racing_close_is_served_whole`. The zombie-pool
  alternative is recorded in `open-questions.md`, not ruled.
- **Born from** the chunking-arc landing review
  (`../../../research/2026-08-25-chunking-arc-landing-review.md`),
  finding F3 (the raw RuntimeError — introduced by spec 118 slice A;
  no such failure mode existed before the offload) and the adjacent
  executor-leak lead. Posture ruled in the 2026-08-25 decision pass:
  **serve like the siblings**; the global should-close-refuse
  question stays open.
- **Date:** 2026-08-25
- **Owner:** Clay Gendron
- **Kind:** lifecycle fix in the database backend's engine host and
  error classification. No change to grep results on the live path.
- **Depends on:** ADR 049 / spec 118 (the verify executor whose
  lifecycle this repairs), the backend's classification law in
  `backend.py` (`_execute`).
- **Relates to:** spec 120 (whatever executor the reindex offload
  rides is governed by the same rules landed here), the
  close-does-not-stop-the-storage lead (recorded below as an open
  question, deliberately not ruled).

## Intent

1. **grep is the one verb that dies across `close()`.**
   `EngineHost.close()` shuts the lazily-minted verify executor down
   (`shutdown(wait=False, cancel_futures=True)`) but never clears
   `_verify_executor`, so the `verify_executor` property keeps
   returning the dead pool. Any grep after — including greps already
   **in flight** when close lands — escapes as a raw
   `RuntimeError: cannot schedule new futures after shutdown`.
   `_execute` classifies only `StaleSnapshot` / `SQLAlchemyError` /
   `OSError`, so the exception crosses the storage seam raw, against
   the backend's stated law that failures come back classified.
   Executed: 100 % reproduction, 4/4 runs, sqlite and live Postgres,
   from the top public API — 24 in-flight `fs.grep` tasks +
   `fs.close()` → 24 raw RuntimeErrors, while the identical glob
   shape returns 24 clean Results.
2. **The failure depends on hidden pool state.** Every sibling verb
   (glob/write/read) keeps serving after close via transparent
   re-pooling, and grep itself serves after close *if no grep ever
   ran before it* — a fresh pool is minted on first use. The same
   call is fatal or fine depending only on whether a grep happened
   earlier in the process. Lazy-unmount (`unbind` + dispose) is a
   documented live-system operation, so the window is not confined
   to process teardown.
3. **The leak twin:** a grep issued after a close that never minted
   the pool mints a fresh executor that nothing will ever shut down —
   the mint-after-close path has no owner (unverified lead, made
   verified in passing here or refuted by the landed shape).

Laws that bind the slices:

1. **The sibling law:** after and across `close()`, grep behaves
   exactly like glob — it serves, transparently re-establishing
   whatever resources it needs. Close remains idempotent per
   `SupportsClose`.
2. **Nothing crosses the seam raw.** Whatever shape lands, an
   in-flight grep overlapping close comes back as a classified
   Result — served if the work can complete, classified-failed if it
   cannot — never a raw exception.
3. **Every minted executor has exactly one owner responsible for its
   shutdown.** Mint-after-close is either impossible by construction
   or the minted pool is tracked and shut by the next close.

## Shape

- **§1 The re-mint (or inline fallback).** The direction of least
  contract change: `close()` clears `_verify_executor` after
  shutdown so the property re-mints on next use (the glob-pool
  pattern), or `VerifyOffload` falls back to inline verify when the
  pool is dead. Pick during planning by which shape keeps law 2
  simplest for the in-flight window — the race between
  `submit` and `shutdown` must land classified either way.
- **§2 Classification.** The close-window failure joins the
  classified family: either the RuntimeError becomes impossible (the
  re-mint swallows the window) or `_execute`'s classification learns
  the executor-shutdown shape as an operating condition. No new
  SQLSTATE-like taxonomy — the smallest honest classification.
- **§3 The pins.** A verb-level after-close conformance row: grep
  after close serves, equal to a fresh handle's answer — beside the
  existing glob behavior, on the memory leg and every engine leg.
  The in-flight race pinned: N grep tasks + close, all N return
  classified Results (served or failed, never raised). The
  mint-after-close leak pinned by whichever §1 shape lands (no
  orphan executor observable, or the orphan is impossible). The
  existing offload-law pins (P3–P5) stay green.

## Slices

One slice — the fix, the classification, and the conformance rows
land together; the surface is small and the laws interlock.

## Open questions

- **Should a closed backend refuse?** Deliberately not ruled here.
  Post-close writes currently serve and *mutate* (executed, in the
  review's leads) — whether `close()` should mean refusal for every
  verb is a contract decision touching all backends and
  `SupportsClose` itself. Record in `open-questions.md` on landing,
  pointing at this spec and the review memo.
