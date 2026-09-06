# The glean statistics leak under row grants (2026-09-05)

Study S2 of the principals-and-permissions programme
(`context/research/2026-09-05-principals-and-permissions-research-plan.md`
§4). Memo: `context/research/2026-09-05-glean-statistics-leak.md`.

The question: when row grants hide some rows from a caller, do `glean`'s
scores, its exported `lexical_stats`, or its ranks reveal the terms of
the hidden rows? BM25 scores every visible row with corpus-wide `N`,
`avg_dl` and per-term `df`, so a visible row's score depends on rows
the caller cannot read.

## Scripts (repo venv: `uv run --no-sync python`, from this directory)

The scoring is vfs's own: `vfs.models.lexical.tokenize` (the Rust
engine), `idf` and `term_weight`, with the answer shaped the way
`glean` emits it (min-max scaled over the answer, nine decimals). One
SciFact abstract is one document and one chunk. numpy is used only for
the adversary's least-squares solves and the topical k-means split.

- `common.py`: the SciFact loader (through `tests/ranking/corpora.beir`,
  the harness cache at `~/.cache/vfs/ranking/beir/scifact`), the index,
  statistics over any row subset, the served answer, nDCG@10, and the
  partitions (random and topical hidden fractions 10/50/90 %).
- `leak_channels.py`: the three channels. The adversary reads the visible
  rows, plants 4 + 64 anchor documents and a 128-document ladder, and
  asks one query per vocabulary term (400 terms stratified by visible
  df). Channel a solves `N` and `avg_dl` from two anchor queries and
  each term's df from one two-term query on the min-max-scaled scores;
  channel b reads the export; channel c reads a term's idf off the
  ladder's interleaving from the ranks alone (given `N`, `avg_dl`).
- `mitigations.py`: nDCG@10 on the visible qrels per statistics policy
  (global, visible-set, power-of-two df buckets, stale global snapshot),
  the multiplayer intersection, the cross-mount merge's export vs the
  union fallback, the residual leak of each policy against the channel-a
  adversary, and the cost model for visible-set df.

## Rerun

    cd context/research/studies/2026-09-05-glean-statistics-leak
    uv run --no-sync python leak_channels.py > results.md   # ~40 s
    uv run --no-sync python mitigations.py >> results.md    # ~60 s

`results.md` holds the raw tables as produced. Seeds are fixed
(`SEED = 20260905`); the topical split hashes terms with Python's
`hash`, so set `PYTHONHASHSEED=0` for a bit-identical split.
