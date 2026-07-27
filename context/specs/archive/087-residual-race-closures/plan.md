# 087 — plan

Approach: every change routes through machinery 086 landed — the
stale-snapshot signal, `with_retry`, guarded statements — so the diff
is arms rewired, not mechanisms invented. Order of work puts the
redrive rewiring first (it deletes classification code the later
fixes would otherwise have to touch), then the two guard additions,
then the capability gate, then tests.

## 1. Redrive rewiring (decisions 1–3, 8)

- `writes.py` `_classify_arbitration_loss` and `_resolve_rows`:
  - occupant `None` → `raise StaleSnapshot(...)` (was: classified
    `conflict`). The absorb-arm vanished-row `_conflict` follows.
  - staged directory + occupant directory + matching stored path →
    absorb-as-unchanged: adopt identity the same way the absorb arm
    does, but mark the staged row "unchanged" so no material update or
    content replace runs and the observation reports the occupant's
    version. Reuse the existing absorb plumbing; the new bit is
    skipping the material update, which staging's unchanged handling
    already models for no-op writes.
  - `_conflict` (reprobe guard-miss) gains `retryable=True` — needs a
    direct `ResultError` construction or an envelope-helper flag;
    prefer the small helper extension since 088 touches the same
    helpers anyway (coordinate: land the flag argument here, 088 adds
    `target=`).
- `topology.py` `_execute_move` claim and `_execute_copy` chunk
  handlers: `except IntegrityError` → roll back the savepoint, then
  `raise StaleSnapshot(...)` with the pair attribution in the context
  string. Delete `_classify_claim_race` (both its arms are now
  redrives; the ladder produces the honest refusal on redrive). The
  ghost-blocks-restore conformance pin moves from expecting the
  seam-time `conflict` to expecting the redriven ladder outcome.
- Risk: redrive loops. A *persistent* collision (occupant that never
  goes away) must not redrive forever — but the redrive re-runs the
  refusal ladder first, which classifies the occupant terminally
  before any claim retries. Verify with the always-racing-handler
  exhaustion test shape from 086.

## 2. Delete re-collection (decision 4)

`topology.py` `delete_rows`: after the guarded `_reparent_to_trash`
succeeds for a target, call the existing `_descendant_rewrites`
against live state (mirror `_rewrite_descendants`' placement in
`_execute_move`) and apply that fresh list. Keep the pre-claim
collection only for the refusal ladder and byte-budget check; add the
late-arrival budget re-check on the fresh list (over-budget →
`StaleSnapshot`). Watch `local_bumps`: the re-collection happens
inside the same transaction, so counts for later targets are
unaffected.

## 3. Guarded occupant destroy (decision 5)

`_execute_move`: the `overwrite` arm currently purges the occupant
subtree unguarded. Insert a guarded root destroy first — an UPDATE or
DELETE on `(entry_id == occupant, version == version-at-probe)`
verified per decision 7 — then let `_purge_subtree` clean descendants
(it is loop-until-empty and now safe: any rival child create must
bump the already-destroyed root and takes its own guard miss).
Thread `occupant["version"]` from the ladder's probe into the
executor (extend the pending-transfer tuple).

## 4. Claim capability gate (decision 7)

New private helper in `topology.py` (not a shared abstraction —
non-goal): execute a single-row guarded statement; if
`dialect.supports_sane_rowcount`, verify `rowcount == 1`; elif the
dialect models UPDATE…RETURNING, re-issue with `.returning(entry_id)`
and count; else return the classified `unsupported` refusal in
writes' wording. Call sites: `_reparent_to_trash`, the move/restore
claim, the new occupant destroy. Unit-test with a doubles session
reporting −1.

## 5. Absorb-arm address proof (decision 6)

`writes.py`: absorb updates add `path == path-at-probe`:
- VALUES-join arm: reuse the guarded machinery with a path-only
  predicate variant (no version tuple) — extend `_values_update`'s
  guard flag into a three-state (version+path / path-only / none) or
  pass predicate columns explicitly; keep the statement width math
  in sync.
- executemany arm: add the path bind to the WHERE; verify per-row
  rowcount where `supports_sane_multi_rowcount`/per-row sane, else
  compare the read-back's stored path to the expected path (the
  read-back already fetches the row; add `path` to its columns).
- Miss → `StaleSnapshot`.
- `_replace_content` for absorbed rows rides the same proof: content
  replace happens after the verified material update in the same
  transaction, and the entry-row lock now held blocks the rival
  reparent until commit — no second predicate needed there.

## 6. Tests (decision 9)

- `tests/test_backends_database_races.py`: depth-2 delete
  re-collection; overwrite-purge rival survival (move + restore; the
  assertion is "rival row survives somewhere or the verb refused
  not_empty", per engine both outcomes are legal depending on
  interleaving); copy child-collision honesty (final error is
  `not_empty` at `/dest` after redrive, no `exists`, no driver
  tokens); ancestor-mint storm (gather N pairs, all trials end in two
  successes; N modest — the campaign saw MySQL fail 300/300, so even
  N=20 pins it).
- `tests/test_backends_database.py` (sqlite, same-session seam
  handlers + doubles): occupant-vanished arm raises `StaleSnapshot`;
  dir-absorbs-dir unchanged outcome; absorb path-predicate miss;
  insane-rowcount refusal for the claim helper; `_classify_claim_race`
  tests retire with the function.
- Conformance: the mkdir-p concurrency contract (two `parents=True`
  writers both succeed) is engine-legged, not sqlite (single-writer
  serializes it trivially).
- Absorb-on-trash pin is Oracle/MSSQL-shaped; stage it with the
  in-suite seam if one exists in the window, else pin the guard miss
  at unit level and lean on the storm's audit for the engine legs
  (the campaign's staging patched a module global — fine for a
  scratch verifier, not for the suite).

## Trade-offs taken

- Redrive-over-classify costs a re-collection round trip on genuine
  collision, in exchange for honest attribution and engine
  convergence — ADR 025's exact trade, extended.
- Decision 5 keeps destroy-the-occupant semantics (guarded) rather
  than deciding trash-the-occupant; smaller diff, open question
  untouched.
- Decision 2 is implemented in arbitration, not staging, so the
  sequential path is byte-identical.

## Verification

sqlite suite + ruff + ty continuously; the four engine legs (already
up in-session) after each phase lands; 10k-batch bench on Postgres +
MySQL at the end against the 086 baseline (pg 2.40–2.47s,
mysql 1.98–2.03s).
