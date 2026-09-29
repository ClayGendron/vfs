# Visible-set statistics on vfs block postings (2026-09-28)

Study for the memo
`context/research/2026-09-28-search-statistics-under-permissions-precedent.md`.
It follows study S2 (`../2026-09-05-glean-statistics-leak/`), which
measured the leak. This one measures two costs of closing it.

## The two questions

1. **Cost.** ADR 065 says `glean` must use statistics over the rows the
   caller can see. The visible `df` of a term is "how many of the
   caller's visible chunks contain it". How many bytes and how much
   engine time does it take to count that on vfs's block postings?
2. **Bounds.** Each stored block carries a maximum weight. That maximum
   was computed with the global `idf` and `avg_dl`. Is it still an upper
   bound when the query uses visible-set statistics? If not, what bound
   is safe?

## How it runs

    cd context/research/studies/2026-09-28-search-statistics-precedent
    uv run --no-sync python visible_df_cost.py > results.md   # ~6 min

- The index is built by vfs's own Rust engine
  (`vfs.models.lexical.lexical_builder`), in memory. No database.
- Every visible count uses the engine's own decode-and-intersect kernel
  (`candidate_ids`, the one grep's prefilter uses).
- Corpus: BEIR SciFact from the harness cache
  (`~/.cache/vfs/ranking/beir/scifact`). Once at its own size (5,183
  chunks). Once replicated 40 times (207,320 chunks, 24.8 M postings).
  Replication keeps the vocabulary and scales every `df` by 40.
- Hidden sets: 5 %, 50 % and 90 % of the chunks. Two shapes:
  - **clustered**: one contiguous id range. This is what a folder looks
    like if the index numbers chunks in path order.
  - **scattered**: random ids. This is what a folder looks like when its
    files were written at different times and ids follow write order,
    as they do today.
- Queries: the 300 SciFact test claims, tokenized by vfs.
- Seed `20260928`.

## The four ways to count visible `df`

- **full**: fetch and decode every block of every query term, intersect
  with the visible id set, count.
- **complement**: decode only the blocks whose id span holds a hidden
  id; subtract the hidden hits from the stored `df`.
- **ranges**: like complement, but a block that lies wholly inside a
  hidden range is counted from the summary alone (every block holds 128
  postings except a term's last). Only blocks that straddle a range edge
  are fetched.
- **partition** (storage only): a stored `df` per (term, partition).

The script checks that full, complement and ranges return the same
counts on every query. They do (0 disagreements in every cell).

## Caveats

- "Engine ms" includes handing the visible or hidden id list to the
  engine once per term. For `full` with a small hidden set that list is
  ~200 k ids and dominates the time; a production kernel would pass it
  once per query. Read the byte and block columns as the main result.
- "KB fetched" counts id blobs only. A scorer also needs the `tfs` and
  `dls` blobs; counting `df` does not.
- No round trips, no SQL. The cost of resolving the caller's visible id
  set from the grant predicate is not measured here (it is memoisable
  per epoch and rights shape).
- The bound check decodes varints in Python; it runs on SciFact at its
  own size only.

`results.md` holds the raw tables as produced.
