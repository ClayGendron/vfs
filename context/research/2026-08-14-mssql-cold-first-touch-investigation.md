# MSSQL cold first touch under an in-flight topology window: measured, explained, and half-retired

- **Status**: research memo (executed investigation; closes the
  open-questions entry "MSSQL cold first touch under an in-flight
  topology transaction")
- **Date**: 2026-08-14
- **Owner**: Clay Gendron (investigation ordered in session; executed
  same day)
- **Question**: The 2026-07-25 adversarial campaign filed two
  unverified MSSQL-only leads whose repro scripts were not preserved:
  (1) a cold `DatabaseStorage` whose first op landed inside a rival's
  in-flight topology window failed 2/2 with a raw "Attempt to use a
  closed connection"; (2) a cold first touch blocked 237 s behind an
  in-flight topology transaction. Are either real on the current tree
  (post-086 coherence campaign, post-095–099)?
- **Evidence gathered**: executed repros against a fresh MSSQL 2022
  container (Rosetta, `docker/compose.test.yml`), staged with the
  `delete:post-collect` seam; scripts preserved in
  `studies/2026-08-14-mssql-cold-first-touch/` — this time the
  artifacts outlive the session.

## 1. The block is real, first-touch-specific, and by design

A cold instance's first op blocked for **exactly the rival's hold** —
10.1 s under a 10 s hold, 45.1 s under 45 s, 60.1 s under 60 s —
and completed cleanly the moment the rival committed, classifying
honestly (`not_found` for the deleted target; `success` elsewhere; no
raw driver text).

The mechanism is declared in the code, not an accident:
`topology.py:_serialize` serializes topology on the non-postgres,
non-sqlite engines with a self-assignment UPDATE that X-locks the
single meta row — "serializing rival topology verbs **and first touch
alike**" (its own docstring). Cold first touch
(`engine.py:_verify_or_provision`) reads that meta row inside its own
serialized transaction, so it queues behind any in-flight topology
verb for as long as the verb runs.

The controls pin the flavor: a cold instance touching an **unrelated
path** still blocks (C1 — it is first touch, not row contention),
while a warm instance is untouched during the same window (C2
instant, even reading the subtree mid-delete, C3). The campaign's
"237 s" was therefore the rival's hold time, not a property of first
touch — the same minutes-long topology holds the scattered-10k-delete
entry measures. **Spec 102 (set-based scattered delete) is the real
fix**: shrink the hold and the first-touch wait shrinks with it.
Bounding the wait independently (lock timeout + honest `unavailable`)
remains the recorded mitigation if a deployment needs a startup-latency
ceiling before 102 lands; warm-up (touch the mount at deploy time)
remains the operational workaround.

## 2. The closed-connection failure does not reproduce

Zero raw failures in ten cold first-touches across every shape tried:
short and long holds (10/45/60 s — past driver login timeouts), and
an eight-way concurrent cold-instance storm inside one 60 s window
(all eight blocked through the hold, all eight classified clean at
release). The campaign saw 2/2 against the pre-086 tree; on today's
tree (086–090 coherence arc, 095–099 campaign, the 097 lease and
epoch ladder) the failure shape is gone at these interleavings.
Verdict: **presumed fixed or environmental (Rosetta first-run
stall)** — not reproducible, retired as a defect lead. The 097 watch
item (observed-once combined-leg hang) is the standing tripwire if it
resurfaces.

## 3. Fresh-container combined leg: green

The full MSSQL conformance leg ran on the same fresh, cold container
immediately after the storm: **205 passed / 4 skipped in 70 s** — no
recurrence of 097's observed-once first-run hang. One clean data
point for that watch item, not proof; the item stays open.
