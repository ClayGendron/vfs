# 126 — close disposes every close: the latch falls

- **Status: landed 2026-08-25.**
  One slice: the one-shot ``_closed`` gate is deleted — every close
  releases whatever the host holds now (offload pool, ready latch,
  engine pool), idempotent by cheapness, never by flag, matching the
  pools underneath; a close cancelled mid-dispose records nothing as
  torn down, so the router's documented retry recovery is now true
  (pinned by the cancelled-close retry row); close → verb → close
  releases the re-minted connections (pinned at the pool), and
  queued offload work at close is served whole, never cancelled —
  spec 122's law gains its referee. Ledger rows P16 (gate
  reintroduced, 2 kills) and P17 (cancel-futures reversion, 1 kill)
  proven under safe-restore. Gates: 3.13 CI leg green; all four
  engine legs live (Postgres 211, MySQL 213, MSSQL 213, Oracle 210).
  Landed at ``0ede8f1``.
- **Born from** the remediation-round landing review
  (`../../../research/2026-08-25-remediation-round-landing-review.md`),
  finding F1 (the one-shot `_closed` gate stranding re-minted
  connections — four lenses converged, live-Postgres proven) with
  its `_ready` lead, and F2 (the unpinned cancel-futures direction
  of spec 122's close law). Fix shape ruled in the 2026-08-25
  decision pass **conditional on prior-art verification**, delivered
  as `2026-08-25-close-lifecycle-and-shutdown-race-prior-art.md`:
  drop the latch.
- **Date:** 2026-08-25
- **Owner:** Clay Gendron
- **Kind:** lifecycle fix in the database backend's engine host. No
  change to any verb's results; the change is what the second and
  later closes release.
- **Depends on:** spec 122 (whose every-close pool law this extends
  to the whole teardown), the conformance lifecycle row
  (`test_pattern_search_serves_after_close`), SQLAlchemy's
  documented dispose-then-connect contract (the prior-art memo §1).
- **Relates to:** the should-close-refuse open question
  (deliberately not ruled here — this spec makes the *release* half
  of close correct under the current serve-after-close posture,
  whichever way that question is one day decided).

## Intent

1. **`close()` is one-shot where it must be every-shot.**
   `EngineHost.close()` (engine.py) gates `self._ready = False` and
   `await self._engine.dispose()` behind `if self._closed: return`,
   and `_closed` — written only at init and in close itself, with no
   other reader — latches forever on the first close. The backend's
   own contract makes close → verb → close first-class: verbs revive
   after close, re-minting pools and connections. The second close
   shuts the offload pool (spec 122 hoisted that above the gate) and
   strands everything else: executed on live Postgres, the pinned
   post-close grep's connection (pid cross-checked in
   `pg_stat_activity`) survives two further closes, every reference
   drop, and `gc.collect()` — reclaimed only by a manual
   `engine.dispose()`. Bounded at pool_size per host; a multi-tenant
   process cycling hosts through lazy unmount accumulates stranded
   sessions against `max_connections`.
2. **The latch also lies under cancellation.** `_closed = True` is
   set *before* the dispose await, so a close cancelled mid-dispose
   — exactly what the router's `wait_for(storage.close(), ...)`
   timeout produces — latches closed with the engine live, and the
   documented recovery ("a second `close()` after cancellation
   finishes the job") reclaims nothing. Executed: 4 of 5 pooled
   connections stranded on the ordinary shutdown path.
3. **Prior art is unambiguous.** SQLAlchemy — the layer this host
   sits on — has no dispose latch: `Engine.dispose()` is a
   repeatable pool-flush with documented connect-after-dispose, and
   every pool `dispose()` is idempotent by cheapness, never by flag.
   No surveyed system pairs a one-shot close latch with
   revival-on-use; every latch's real job is refusal, which this
   backend deliberately does not have. And SQLite's zombie close
   carries the second law: state never claims teardown that has not
   completed.
4. **The close law's fourth leg is unpinned (F2).** Restoring
   `shutdown(wait=False, cancel_futures=True)` — the exact spelling
   spec 122 removed, whose removal the docstring declares as law
   ("queued work is never cancelled … a served call beats a poisoned
   one") — survives the entire suite while a queued grep's batch
   dies as raw `CancelledError` across the seam. Queued-at-close is
   ordinary load since spec 120 put reindex hops on the same
   single pool.

Laws that bind the slices:

1. **Every close releases everything currently held** — offload
   pool, engine pool, ready latch — with no gate. Idempotence is by
   cheapness: a second close finds nothing held and does nothing,
   exactly like the pools underneath.
2. **No state before completion:** nothing may record teardown as
   done ahead of the awaited dispose returning. (With the flag
   dropped this is vacuous today; it binds any future latch.)
3. **Borrowed connectivity stays untouched** — the existing
   "dispose iff built" arm is the `self._engine is not None` check,
   which already carries it; the borrowed host holds no engine.
4. **The cancelled-close retry finishes the job** — the router's
   documented recovery becomes true, not aspirational.
5. **Queued work is never cancelled** — spec 122's law, now with a
   referee.

## Shape

- **§1 The latch falls.** Delete `_closed` (both writes and the
  gate; it has no other reader). `close()` becomes: shut and clear
  the offload pool (unchanged), drop `_ready`, and
  `await self._engine.dispose()` whenever an engine is held. Docstring
  re-derived: idempotent by cheapness, every close releases, the
  retry contract. The memory leg's `_rearm_on_fresh_connection`
  listener already handles StaticPool re-provisioning — verify, do
  not assume.
- **§2 The release pins.** (a) close → verb → close releases the
  re-minted engine's connections — asserted at the pool
  (checked-in/checked-out accounting or a dispose spy), on the
  sqlite legs, with the conformance serve-after-close row unchanged
  as the revival referee. (b) The cancelled-close retry pin: cancel
  a close mid-dispose, close again, assert the engine is disposed.
  (c) `test_built_close_is_idempotent` stays green as-is.
- **§3 The queued-work pin (F2).** With the pool held at one worker
  and a verify batch queued when close lands, the queued grep is
  served whole — the review's executed repro lifted into
  `TestExecutorOwnership` (its `_GatedMatcher`/`_until` helpers and
  an `OFFLOAD_WORKERS` monkeypatch are the ready shape).
- **§4 The ledger rows.** Executed under safe-restore, each landing
  with its proven kill: the cancel-futures reversion (killed by §3);
  the gate reintroduced whole (killed by §2a); the flag-before-await
  shape is subsumed by the flag's deletion — §2b guards the class.

## Slices

- **A** — §1 + §2: the latch falls, the release and retry pins, the
  gate-reintroduction ledger row.
- **B** — §3 + the cancel-futures ledger row.

Gates per the house cadence: `scripts/ci.sh 3.13` at 100 % coverage;
all four engine legs (the release pin is engine-visible — the
Postgres leg re-checks it live).
