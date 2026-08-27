# 132 — tasks

## Slice 0 — selection per query

- [x] `select_blocks` in the crate and the binding (protocol 7), the
      oracle, parity and hand-case tests; the referee and the harness
      driver on it; 0.144 ms measured.

## Slice A — the leg and scope

- [x] A1 Promote `pointer_with_overlay` → `indexing.py`,
      `content_for_entries` → `reads.py`; grep imports them.
- [x] A2 `glean.py`: constants, `glean_rows`, the two rounds, scope
      rungs, MaxP/top-K, normalisation, the mask, `lexical_stats`.
- [x] A3 `backend.glean`, `glean_wall_seconds`, traits + vocabulary.
- [x] A4 `test_glean.py`: rungs (referee both ways), entries-not-chunks,
      ordering laws, empty query, columns projection.

## Slice B — overlay and records

- [x] B1 Overlay scan + bodies + query-time blocks + scorer; ADR 044
      two-read protocol under the `glean:after-pointer-read` seam.
- [x] B2 Records: overlay budget, scope probe, window; `invalid`.
- [x] B3 Tests: dirty entry found before reindex, budget truncation,
      stale pointer redrive, records' `data`.

## Slice C — surface and measurement

- [x] C1 Conformance rows in `storage_contract.py`; `SupportsGlean` on
      `ConformanceBackend`; engine pin rows pointed at `glean`.
- [x] C2 Harness arm `glean` = BM25 baseline on three corpora.
- [x] C3 EXPLAIN of the round-two statement on every engine leg,
      recorded in the landing note.
- [x] C4 `scripts/ci.sh` full matrix; four legs; landing note;
      STATUS; archive.
