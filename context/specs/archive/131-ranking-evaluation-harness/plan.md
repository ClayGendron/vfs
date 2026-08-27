# 131 — plan

## Approach

Everything lands under `tests/` and `scripts/`; `src/` is untouched.
The harness is dev tooling that *measures* the product; the product's
lexical query path is spec 132's to build, and the harness's own BM25
driver is the independent referee 132 is measured against ("any gap is
a bug"). A driver in `src/` today would be rewritten by 132 within
days and carry a 100 % coverage obligation for throwaway shape — so
the "tiny scoring driver" the spec allows lives in
`tests/ranking/driver.py`.

### Layout

```
tests/ranking/
  __init__.py
  corpora.py      # Corpus; the vfs-native loader; the BEIR loader (skip when absent)
  driver.py       # load_corpus (write + reindex); bm25_run — the two-round search
  metrics.py      # ranx: evaluate / compare; METRICS = ndcg@10 mrr@10 recall@10 recall@50
  embedders.py    # the hashing embedder (local copy until spec 134); model2vec loader
  merge.py        # naive_score_sort, round_robin — the cross-mount floors (spec 137)
  controls.py     # uninformative_prior — the standing control arm (spec 136)
  pins.py         # assert_top10_pin(storage) — the determinism row every leg calls
  baselines.json  # the recorded numbers the 0.005 gate compares against
  test_*.py
tests/fixtures/ranking/vfs_native/
  README.md       # what the snapshot is, how queries were written and labelled
  corpus/         # 200 markdown files frozen from docs/ + context/
  queries.tsv     # qid \t query text
  qrels.txt       # TREC: qid 0 docid grade   (grades 0–3)
  top10.json      # qid -> ordered top-10 paths (the cross-engine pin)
scripts/fetch_beir.py   # downloads SciFact + NFCorpus into the cache outside the repo
```

### Corpora

- **vfs-native**: `docs/**/*.md` (56), `context/decisions/*.md` (58),
  `context/standards/**/*.md` (13), `context/product/*.md` (1), and
  the 72 most recent `context/research/*.md` memos under 40 KB — 200
  files, ≈2.3 MB, frozen by copy so labels never drift with the live
  docs. Doc id = the repo-relative path.
- **BEIR pair**: SciFact and NFCorpus, the `test` split, fetched as the
  canonical BEIR zips (`corpus.jsonl`, `queries.jsonl`,
  `qrels/test.tsv`) by `scripts/fetch_beir.py` into
  `$VFS_RANKING_CACHE` (default `~/.cache/vfs/ranking/beir/`). Tests
  skip when the directory is absent. **Deviation from the spec's
  `ir_datasets`**: the zips are what `ir_datasets` itself downloads;
  reading three files with the stdlib saves a dependency group with a
  dozen transitive packages. Documents are written as
  `/{doc_id}.txt` with `title\n\ntext`.

### Labelling protocol (vfs-native)

Forty queries in four kinds an agent actually issues: prose questions
about the design, identifier queries (code tokens), path-flavoured
queries, and rare+common multi-term queries. For each query a
candidate pool is the union of BM25 top-30 over the snapshot and every
file that `grep -il` matches on any query term (pooling, TREC-style;
the grep leg keeps the pool from being BM25's own reflection).
Subagents grade every pooled file on a 0–3 scale against a written
rubric per query (3: answers the query directly; 2: substantially
about it; 1: mentions it in passing; 0: not relevant). Unpooled files
are 0. The protocol is recorded in the fixture README.

### The driver

`bm25_run(storage, corpus, k)` is ADR 055 pin 4 in test form: tokenize
the query; `lexical_stats`; the head fetch (`block_no < HEAD_BLOCKS`,
8); `score_blocks` at the fusion K (1,000); `competing_blocks` per
overflowing term; the round-two key fetch with the epoch equality
inside every arm; score again; then MaxP to entries through the
chunk→path map read once at load. Scores are rounded to
`SCORE_DECIMALS` (9) and ordered `(score DESC, path ASC)` — path, not
`entry_id`, because entry ids are ULIDs minted per write and a pin
must survive a rebuild. Spec 132 adopts the rounding and the tie-break.

### Metrics, gate, pins

- ranx enters the `dev` group (installs on 3.11–3.14; numba's JIT
  costs ≈5 s on first `evaluate` per process — once a run).
- `baselines.json` records nDCG@10 / MRR@10 / recall@10 / recall@50
  per corpus for the `bm25` arm and the merge floors; the gate test
  asserts nDCG@10 ≥ recorded − 0.005 on every corpus present.
- `top10.json` is generated on sqlite and asserted by
  `assert_top10_pin` on the memory, sqlite and four server legs.
- Embedder pins: sha256 of the float32 packing of one fixed sentence,
  for the hashing embedder (always) and potion-base-8M (skipped unless
  model2vec is importable and the model is in the HF cache).

## Trade-offs

- A 2.3 MB fixture in git versus a generated one: labels are only
  valid against frozen text; the size is the spec's own estimate.
- Pooled labels favour lexical retrieval; the grep leg and the note in
  the README bound the bias. The BEIR pair carries the unbiased
  numbers.
- The driver duplicates the fidelity referee's `_two_round` in SQL
  form; the referee stays the block-level proof, the driver the
  end-to-end one.
