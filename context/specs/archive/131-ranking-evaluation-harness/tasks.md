# 131 — tasks

## Slice A — fixtures and qrels

- [x] A1 Freeze the vfs-native snapshot into
      `tests/fixtures/ranking/vfs_native/corpus/` (200 files).
- [x] A2 Draft `queries.tsv` (40 queries, four kinds); build pools
      (BM25 top-30 ∪ grep); subagents grade → `qrels.txt`; README.
- [x] A3 `scripts/fetch_beir.py`; the cache contract
      (`VFS_RANKING_CACHE`); fetch locally.

## Slice B — driver and metrics

- [x] B1 `pyproject.toml`: ranx in `dev`; `uv lock`; `norecursedirs`
      gains `tests/fixtures`.
- [x] B2 `tests/ranking/corpora.py`, `driver.py`, `metrics.py`.
- [x] B3 `embedders.py` with both pins; `merge.py`; `controls.py`.
- [x] B4 Run the three corpora; record `baselines.json`.

## Slice C — determinism and gate

- [x] C1 `pins.py` + `top10.json`; memory and sqlite rows; the four
      engine rows in `tests/storage/test_conformance.py`.
- [x] C2 The gate test; the merge-floor and control tests.
- [x] C3 `scripts/ci.sh` full matrix (BEIR absent → skips, present →
      green); `db_test` four legs for the pin.
- [x] C4 Landing note with the baseline table; `STATUS.md`; archive.
