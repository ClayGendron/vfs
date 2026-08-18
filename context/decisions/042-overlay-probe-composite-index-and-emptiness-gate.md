# 042. The Overlay Probe: Composite Index and the Same-Snapshot Emptiness Gate

- **Status:** accepted 2026-08-17 — spec 105's decision set,
  written at its mining pass. Schema format 5. **Amended
  2026-08-18** (spec 107): the emptiness gate's verdict is no longer
  same-snapshot-at-the-preamble — see the amendment note under
  *Consequences*.
- **Date:** 2026-08-17
- **Deciders:** Clay Gendron (research-first directive; "make sure
  the index doesn't slow writes"); mechanisms chosen by the memo's
  measurements.
- **Context source:** the overlay-probe research memo
  (`../research/2026-08-17-overlay-probe-cost.md`; decomposition
  and engine-survey studies under
  `../research/studies/2026-08-17-overlay-probe-index/`).
  Implemented by spec 105.

## Context

Every grep call probes the scan tier for `NOT encoded` rows so
index staleness can never lose a match — measured at ~1.7 ms per
call. The research located the cost as index pollution, not a
missing index: the single-column `encoded` index's `encoded = 0`
seek set is mostly directories (6,160 at linux scale), each paying
a table rowid lookup only to be rejected by the `kind` filter. The
entering hypothesis — a partial index `WHERE NOT encoded` — was
refuted by measurement (the sqlite planner never chooses it) and by
the portability survey (nothing on Oracle/MySQL; MSSQL's filtered
indexes die under forced parameterization).

## Decision

1. **The entry table's `encoded` index is the composite
   `(encoded, kind)`** — plain B-tree, identical on every engine,
   no dialect forks. Probe DB time 1,070 → 5.5 µs on an empty
   overlay; the real write path measured unchanged (10k-file
   batches −0.96%, noise).
2. **The epoch-pointer read carries an overlay-emptiness verdict**
   in the same statement (a CASE-wrapped EXISTS, ORM-built so the
   negation renders as an inline literal on every dialect — the
   fact that keeps the seek reachable). An empty verdict skips the
   scan-tier statement outright; skipping returns exactly what
   scanning an empty overlay would. The gate keys off scan-shaped
   *plans*, not the flag: `invert_match` calls and gramless
   patterns run the scan tier without consulting the gate, while an
   `allow_scan` call whose pattern is indexable rides the ladder
   and is gated like any other. (As accepted, this bullet read
   "`allow_scan` and `invert_match` callers never consult the
   gate" — the code was always plan-keyed; the prose was wrong.)
3. **Rejected on measurement:** partial/filtered indexes, a
   separate EXISTS round trip (overhead ≈ the fixed probe), and a
   maintained meta-row counter (an ETL write hot-spot for zero read
   benefit over EXISTS).

## Consequences

- ~1.3 ms off every grep call at any scale; the zero-hit floor's
  day arc ran 110 → 41 ms with this and ADR 041/043's landings.
- The overlay is legitimately non-empty on real corpora
  (index-ineligible files; trashed files until swept) — the gate
  tolerates both, and the probe they trigger is now µs-scale.
  Trash stamping (`delete` setting `encoded = True`) would make the
  gate exact; deliberately left as its own future decision because
  it touches trash/restore semantics.
- Any future query against `encoded` must spell the predicate
  ORM-built (`~entry.c.encoded`), never raw text — the raw
  bareword spelling measured as a full-table scan.
- **Amendment (2026-08-18, spec 107):** the accepted design read
  the verdict once, in the preamble, and treated it as
  same-snapshot with the statements it vouched for. That holds
  only under a repeatable-read pin; on SQL Server, Oracle, and the
  GENERIC floor a rival demotion committing between the verdict
  and the candidate fetch lost the demoted row silently (executed
  by the 2026-08-18 review campaign,
  `../research/2026-08-18-glob-grep-review-campaign.md`). The
  repair keeps this ADR's statement shape and cost profile but
  moves authority: the preamble verdict is advisory, and skipping
  the scan is authorized only by re-issuing the combined read
  after the candidate fetch, where it doubles as the epoch recheck
  — statement counts on the skip and scan paths unchanged, no
  locks, no writer involvement.
