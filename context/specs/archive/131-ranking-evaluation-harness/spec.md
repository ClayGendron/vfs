# 131 — the ranking evaluation harness: golden sets, BEIR pairs, ranx metrics, determinism pins

- **Status:** **landed 2026-08-27** — drafted 2026-08-26 from ADR 052
  pin 8 ("the harness lands with or before the first backend"). Second
  of the glean arc; landed before the verb so every later slice is
  measured, not guessed. Landing note at the end.
- **Born from:** ADR 052 §8; memo
  `../../../research/2026-08-26-glean-fusion-and-cross-mount-merge.md`
  §6; ADR 053's accuracy study (memo §9).
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Kind:** dev-only test tooling and fixtures; no `src/` behaviour
  change beyond a tiny scoring driver over spec 130's tables.
- **Depends on:** spec 130 as rewritten under ADR 055 (the BM25
  baseline it measures first is the block-posting index read through
  the scorer, not an in-engine `SUM`).
- **Relates to:** every later glean spec (each adds arms and pins here);
  the accuracy research leg (SWE-bench Verified, a Wikipedia slice) runs
  on this harness but is research, not this spec.

## Intent

Every ranking knob the ADRs name — α, β, k, γ, fetch depth, K chunks —
is set by taste until a relevance set exists. The harness makes ranking
changes measurable and pins cross-engine determinism, so the fused
statement's "identical rankings on six dialects" is a test row rather
than a study result.

## Decided semantics

1. **Golden corpora**, all offline and deterministic:
   - a **vfs-native set**: ≈ 200 files from `docs/` + `context/` frozen
     as a fixture snapshot, ≈ 40 queries with graded qrels in TREC
     format, hand-labelled and checked in (it alone exercises path
     globs, code tokens and entry/chunk aggregation);
   - a **BEIR pair** (SciFact for precision@1; NFCorpus for recall
     under truncation) fetched by a `uv run` script into a cache
     *outside* the repo (`ir_datasets` in a dev group), and skipped —
     not failed — when absent or offline.
2. **Metrics via ranx** (dev-only dependency; never imported by
   `src/`): `nDCG@10`, `MRR@10`, `recall@10`, `recall@50`;
   `optimize_fusion` for sweeps; `compare` for significance when a
   change claims a gain.
3. **Embedders**: the hashing embedder (spec 134 ships it in core; until
   then the harness carries a local copy of the same function) as the
   zero-dependency floor; model2vec potion-base-8M as the semantic
   default *when installed and cached*, skipped otherwise; both pinned
   by the content hash of their vectors for one fixed sentence.
4. **Determinism pins**: for every golden query the conformance suite
   pins the *ordered* top-10 path list per backend, identical across
   SQLite, Postgres, MariaDB, MySQL, SQL Server and Oracle; the pin
   requires an explicit total order (`score DESC, entry_id ASC,
   chunk_index ASC`) and the fused score rounded to a fixed number of
   decimals before the order-by. Spec 130's BM25 baseline is the first
   pinned ranker.
5. **Regression gate**: nDCG@10 on each golden corpus may not drop by
   more than 0.005 without an ADR note; naive score sort and round-robin
   are kept as named baselines so the gate has a floor.
6. **Controls**: the uninformative-prior injection from the fusion study
   is a standing arm that no prior may worsen (used from spec 136 on).

## Scope

In: fixtures, the fetch script and cache contract, the metrics driver,
the pins for the BM25 baseline, the gate. Out: the arms that need later
specs (they add themselves), the research runs themselves (SWE-bench,
Wikipedia — a research leg on this harness).

## Slices

- **A — fixtures and qrels**: the vfs-native snapshot and hand labels;
  the BEIR fetcher with cache-outside-repo and skip-when-absent.
- **B — driver and metrics**: a `tests/ranking/` (or `benchmarks/`)
  driver that loads a corpus into the in-memory backend, runs a ranker
  callable, and reports ranx metrics; the BM25-baseline pin via spec
  130's tables.
- **C — determinism and gate**: the ordered-top-10 pin as a conformance
  row (engine legs), rounding and tie-break laws, the 0.005 gate.

## Landing criteria

- `scripts/ci.sh 3.13` green with the BEIR pair absent (skips) and
  green locally with it present.
- The BM25-baseline pin holds on all engine legs.
- The landing note records the baseline numbers (nDCG@10 / MRR@10 /
  recall@10 on all three corpora) that every later spec is measured
  against.

## Landing note (2026-08-27)

Everything under `tests/` and `scripts/`; `src/` untouched. The BM25
baseline driver lives in `tests/ranking/driver.py` as the independent
referee spec 132's `glean` is measured against (see `plan.md` for why
not `src/`).

**Landed**

- `tests/fixtures/ranking/vfs_native/`: 200 frozen markdown files
  (2.3 MB), 40 queries in four kinds with a written information need
  each, 1,577 graded judgments in TREC format (grades 0–3; 675 / 675 /
  164 / 63 by grade; 321 of them unpooled additions by the graders),
  the labelling protocol in its README, and `top10.json` — the ordered
  top-10 pin.
- `scripts/fetch_beir.py` + `tests/ranking/corpora.py`: the BEIR pair
  from the canonical zips into `$VFS_RANKING_CACHE` (default
  `~/.cache/vfs/ranking`); absent → skip. **Deviation:** the stdlib
  reads the three files `ir_datasets` would download; no
  `ir_datasets` group.
- `tests/ranking/driver.py`: the two-round search over the block tables
  (`HEAD_BLOCKS = 8`, fusion K = 1,000, round-two arms with the epoch
  equality inside each, MaxP to entries), scores rounded to
  `SCORE_DECIMALS = 9`, ordered `score DESC, path ASC` — path, not
  `entry_id`, because entry ids are ULIDs minted per write and a pin
  must survive a rebuild. Spec 132 adopts both laws.
- `tests/ranking/metrics.py`: ranx `evaluate` / `compare` (ranx in the
  `dev` group; installs 3.11–3.14; ≈5–14 s of numba JIT on the first
  `evaluate` per process).
- `tests/ranking/embedders.py`: the hashing embedder (blake2b over the
  index's tokens and bigrams, 256-d, L2) pinned at
  `c985e95f…819bf4`; potion-base-8M pinned at `8d2c32da…f90ee2`,
  skipped unless model2vec and the cached model are present.
- `merge.py` (naive score sort, round-robin), `controls.py` (the
  uninformative prior, β = 0.5, hash-seeded), `pins.py`
  (`assert_top10_pin`), the four engine rows in
  `tests/storage/test_conformance.py`.
- The gate: `tests/fixtures/ranking/baselines.json`; nDCG@10 may not
  drop more than 0.005 below it. `VFS_RANKING_REBASELINE=1` /
  `VFS_RANKING_REPIN=1` rewrite the files — a deliberate act, recorded
  in the landing note of the spec that moved the number.

**Baseline numbers** (BM25 through the block tables and the Rust
scorer, k1 = 1.2, b = 0.75, no stop list, no stemming)

| corpus | docs / queries | nDCG@10 | MRR@10 | recall@10 | recall@50 |
|---|---|---|---|---|---|
| vfs-native | 200 / 40 | **0.7589** | 0.9833 | 0.4134 | 0.7852 |
| SciFact (test) | 5,183 / 300 | **0.6580** | 0.6235 | 0.7890 | 0.8737 |
| NFCorpus (test) | 3,633 / 323 | **0.3052** | 0.5152 | 0.1459 | 0.2045 |

SciFact sits at the fusion study's bm25s figure (0.663, with a stop
list) without one; NFCorpus is in BM25's published band (0.32 with
stemming). Arms recorded on vfs-native: the uninformative-prior
control **0.7355** (−0.023, inside ADR 052's ≤ 0.05 bound); the merge
floors over a `docs/` + `context/` two-mount split — naive score sort
**0.7353**, round-robin **0.5600** (single-mount BM25 0.7589 is the
ceiling spec 137's rerank is measured against).

**Gates.** `scripts/ci.sh 3.13`: 2,812 passed, 882 skipped, 100 %
coverage (BEIR present locally; absent → two skips). Full matrix
3.11–3.14 green. Engine legs with the pin row: Postgres 215, MySQL 215,
SQL Server 215, Oracle 212 — the ordered top-10 identical on every
engine. Cost: golden corpus 0.6 s to load, 0.2 s for 40 queries;
SciFact 2.7 s + 1.6 s; NFCorpus 1.9 s + 0.8 s.

**Residue.** Pooled labels favour lexical retrieval (README says so;
the BEIR pair is the unbiased check). Several `docs/how-to` and
`docs/reference` pages in the snapshot are title-only stubs, so three
navigational queries have no grade-3 document. model2vec is not in
any dependency group; the potion pin was recorded from a scratch venv.
`Corpus` holds whole corpora in memory — fine at BEIR's size, the
accuracy research leg (SWE-bench, Wikipedia) will want a streaming
loader.
