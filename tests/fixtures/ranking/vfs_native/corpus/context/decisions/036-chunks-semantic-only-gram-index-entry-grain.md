# 036. Chunks Are Semantic-Only; the Gram Index Reads Whole Entries

- **Status:** accepted 2026-08-13 — decided by Clay at the spec 096
  kickoff, resolving its §1 grain fork with executed evidence in hand.
  Supersedes the first clause of ADR 033 §4 ("documents are chunks")
  and amends ADR 033 §7's eligibility derivation; every other ADR 033
  decision stands.
- **Date:** 2026-08-13
- **Deciders:** Clay Gendron
- **Context source:** the glob/grep/indexing review campaign
  (`../research/2026-08-13-glob-grep-indexing-review-campaign.md`,
  finding 3, critical): a match straddling a 2048-char chunk cut whose
  straddling trigrams appear in no single chunk is silently never
  served — reproduced on sqlite and live Postgres. Spec 096 drafted
  two fixes; resolving the fork produced the executed refutation
  below, which changed the option space before Clay decided.

## The deciding argument

The memo's recommended fix — emit `GRAM_SIZE − 1` characters of
boundary overlap and leave the posting grain, the intersection, and
the verify path untouched — is unsound, and an executed sweep proves
it. Grep's candidate AND intersects posting lists **per chunk id**
(`grep.py`), so a candidate must contain *every* chosen gram in the
*same* chunk. A needle straddling a cut with `GRAM_SIZE` or more
characters on each side has interior trigrams on both sides of the
cut — they live in two different chunks, and no fixed-width overlap
can put all of them in one. Sweeping a six-char needle across the
2048 cut (offset = characters left of the cut):

| split | today | overlap emission | required anywhere in entry |
|-------|-------|------------------|----------------------------|
| 0/6   | found | found            | found                      |
| 1/5   | LOST  | LOST             | found                      |
| 2/4   | LOST  | LOST             | found                      |
| 3/3   | LOST  | LOST             | found                      |
| 4/2   | LOST  | found            | found                      |
| 5/1   | LOST  | found            | found                      |
| 6/0   | found | found            | found                      |

Every sound fix therefore makes nomination entry-grain. Once that is
accepted, the coupling itself is the defect: grep's authoritative
verify already fetches the full entry body, `re` matches raw file
content, and the split serves no purpose on the grep path except to
manufacture this failure class. Chunks do have a real purpose — they
are the unit of the future vector/semantic and BM25-style lexical
search — and that purpose has nothing to do with trigram nomination.
The decision separates the two cleanly: **grep is based on the actual
file; chunks belong to semantic search.**

## Decisions

### 1. The gram index's documents are entries

Gram extraction runs once over each entry's **full folded body** —
the same newline-normalized, Turkic-i-folded, casefolded stream as
before, now uninterrupted by cuts — and the posting `doc_id` is the
entry row's surrogate integer key (`entries.id`). The delta-varint
codec, the rarest-first budgeted intersection, and the Python verify
are unchanged in shape; candidate mapping gets simpler (posting ids
resolve to entry rows directly, no chunks-table hop). The extraction
invariant, stated in the indexer's docstring: *every trigram of the
entry's folded body is in the entry's posted gram set.* This also
closes the adjacent whitespace-span gap by construction — spans a
splitter would drop are still bytes of the body.

Two structural consequences are wins, not costs: posting lists
deduplicate per entry (a gram recurring across a file posts one id,
not one per chunk), so the index shrinks; and `doc_count` now counts
entries — exactly the unit the candidate budget and the verify loop
are priced in.

### 2. Chunks are semantic-only

The `chunks` table and `Chunk.split` machinery exist for one purpose:
vector/semantic embedding and BM25-style lexical ranking, where a
retrieval unit smaller than a file is the point and recall is
probabilistic by nature. No grep-path code may read chunk rows.
Reindex keeps refreshing chunks (the split is still content-derived
state and reindex is still the batch maintenance verb), but that is a
service to the future semantic pipeline, which owns its own gates,
grain, and cadence and may move the refresh when it lands.

### 3. Gram eligibility is materialized on the entry row

ADR 033 §7 derived "ineligible" from `chunked` with zero chunk rows —
a derivation that dies with the coupling. Eligibility becomes an
explicit `indexable` boolean on the entry row, stamped by the
chunking phase's version-guarded flip from the body it just read:
within byte and distinct-gram bounds **and** at least `GRAM_SIZE`
bytes after normalization (a shorter body posts nothing, and any
pattern short enough to match it plans no grams and scans
everything). The pending-work probe reads `chunked AND NOT encoded
AND indexable` on live rows — the correlated-EXISTS probe against
chunk rows retires. The gates still bound bloat, never coverage: an
un-`indexable` entry stays scan-side forever.

### 4. The format knob bumps

`INDEX_FORMAT_VERSION` goes to 2 — the extraction grain changed, so
every published epoch's fingerprint mismatches and the next reindex
drops and rebuilds. This is the first consumer of the knob ADR 033 §6
declared.

## Rejected alternatives

- **Overlap emission with per-chunk intersection untouched** (the
  memo's recommendation, spec 096's drafted option (a)) — refuted by
  execution: the sweep above loses splits 1/5 through 3/3. The
  invariant it establishes ("every body trigram is in *some* chunk")
  is necessary but not sufficient under a same-chunk AND.
- **Overlap emission plus entry-grain intersection** — sound: keep
  chunk-grain postings, map each decoded posting list chunk→entry
  before intersecting. Rejected because it pays a per-gram mapping
  query on the hot read path, keeps a chunk-grain `doc_count` that no
  longer prices anything real, still needs separate machinery for the
  whitespace-span gap, and preserves the grep↔chunks coupling the
  deciding argument identifies as the defect.
- **Per-entry extraction posted under a representative chunk id** —
  sound and minimal (no schema change), but it launders entry-grain
  facts through chunk-id clothing: doc ids that name one arbitrary
  chunk, eligibility still derived from chunk-row presence, and the
  coupling intact. Clay rejected it for the honest grain.
- **Deriving eligibility instead of materializing it** — `size_bytes`
  covers the byte gate but nothing on the entry row can see the
  distinct-gram count; recomputing it at every build turns the
  idempotent-cheap no-op into a full-corpus content scan.

## Consequences

- The straddle class and the whitespace-span class close for every
  offset and needle length; the boundary battery (spec 096 §3) pins
  both on the indexed tier.
- The index shrinks and selectivity ranking improves (per-entry
  dedupe; entry-priced `doc_count`); spec 096 records the measured
  size delta at landing.
- Grep's read path loses one table hop; the pending-work probe loses
  its correlated EXISTS (the T-SQL legality lesson from spec 095
  stays recorded there).
- The entries schema grows one boolean, handled exactly like its
  siblings: a content write resets all three derived flags
  (`chunked`/`encoded`/`indexable`), and the chunking phase re-stamps
  eligibility before any consumer reads it (it is only read behind a
  true `chunked`).
- Chunk-grain assumptions in tests (posting fan-out counts, seeded
  epochs keyed by chunk ids) are re-homed to entry grain in the same
  landing.
