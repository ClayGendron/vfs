"""The ranking evaluation harness: golden corpora, the BM25 baseline driver,
ranx metrics, the determinism pins and the regression gate.

Dev-only tooling — nothing here is imported by ``src/``. The corpora are
the frozen vfs-native golden set under ``tests/fixtures/ranking`` and
the BEIR pair (SciFact, NFCorpus) read from a cache outside the repo
(``scripts/fetch_beir.py``), skipped when absent.
"""
