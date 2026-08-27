# The vfs-native golden set

A frozen retrieval test collection over this repository's own
documentation: 200 markdown files, 40 queries, graded relevance
judgments. It is the only golden corpus that exercises vfs's path
namespace, code tokens in prose, and multi-chunk entries; the BEIR pair
(`scripts/fetch_beir.py`) carries the unbiased academic numbers.

## Corpus (`corpus/`)

Snapshot taken 2026-08-27 from the live tree: `docs/**/*.md` (56),
`context/decisions/*.md` (58), `context/standards/**/*.md` (13),
`context/product/*.md` (1), and the 72 most recent
`context/research/*.md` memos under 40 KB. A document's id is its
repo-relative path; it is written to vfs as `/<id>`. **Never refresh
the snapshot in place** — the labels are valid only against this text.
A new snapshot is a new collection with new labels.

## Queries (`queries.tsv`)

Forty queries in the four kinds an agent issues against a codebase's
docs: prose questions about the design (q01–q14), identifier queries
(q15–q24), path-flavoured and navigational queries (q25–q30), and
rare-plus-common multi-term queries (q31–q40). The `need` column is the
information need each grader judged against; the harness reads only
`qid` and `query`.

## Judgments (`qrels.txt`)

TREC format, `qid 0 doc grade`, grades 0–3:

- **3** — directly answers the need: the decision record that decides
  it, the how-to or reference page for it, the memo dedicated to it.
- **2** — a substantial treatment (a major section) that is not the
  primary document.
- **1** — a passing mention: a sentence, a cross-reference, a bullet.
- **0** — not relevant, or vocabulary overlap only.

Unjudged pairs are 0. Pooling: for each query, the union of a BM25
top-30 over the snapshot (vfs's own tokenizer, k1 = 1.2, b = 0.75) and
every file containing any query term with document frequency ≤ 25 —
1,256 pooled pairs. Graders (eight, each holding 25 files and all 40
needs) read every file in full, graded every pooled pair, and were
asked to add any unpooled pair they judged ≥ 1; those additions are
what keeps the labels from being BM25's own reflection. Pooled labels
still favour lexical retrieval — read a gain on this set beside the
BEIR pair before believing it.

## The pin (`top10.json`)

The ordered top-10 paths of every query under the BM25 baseline
driver, recorded on sqlite (`VFS_RANKING_REPIN=1`) and asserted on the
memory, sqlite and every server leg — the cross-engine determinism row.
