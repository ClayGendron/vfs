# 096 — Gram coverage: chunk boundaries stop eating matches

- **Status: implemented 2026-08-13, uncommitted** — born from the
  review campaign memo
  (`research/2026-08-13-glob-grep-indexing-review-campaign.md`,
  finding 3 critical + adjacent leads). The §1 owner fork was resolved
  by Clay at kickoff (2026-08-13) after an executed sweep refuted the
  drafted option (a): the decision is **ADR 036** — the gram index
  extracts over each entry's full folded body; chunks are
  semantic-only. Landing ledger, all same day: suite 2,218 passed at
  100% coverage, ruff/ty zero; **all four Docker legs green with the
  three §3 boundary rows live** (Postgres 198, MySQL 199, MSSQL 200,
  Oracle 197 passed — +3 over the 095 numbers on every leg); the
  differential battery's boundary edition ran green (133 case-checks,
  up from 121); the §4 codec pin's blob was verified by hand to decode
  silently as ``[5]`` under the cap-10 mutant. **Measured index-size
  delta (repo's own 45 src files):** entry-grain postings are ~2.8×
  smaller — 111,760 blob bytes / 97,931 doc ids vs 311,567 / 288,779
  at chunk grain — with 11 *more* distinct grams indexed (boundary and
  whitespace-span grams the old grain lost). **Adjacent find, fixed
  and pinned in this landing:** copy-onto-occupant replaced the
  occupant's body without demoting its flags — a coverage exit
  violating the 095 invariant (fresh body permanently invisible to
  both tiers; executed repro at kickoff); the occupant's material
  update now resets ``chunked``/``encoded``/``indexable`` like any
  content write, pinned by a facade regression row.
- **Date:** 2026-08-13
- **Owner:** Clay Gendron
- **Kind:** correctness repair of gram extraction at chunk boundaries
  + coverage-class test battery + one postings-codec boundary pin.
- **Depends on:** ADR 036 (entry-grain gram index, semantic-only
  chunks — this spec is its landing vehicle), ADR 033 (refusal gate,
  budgets, epoch lifecycle — §4/§7 as amended by 036), spec 095 §6
  (`INDEX_FORMAT_VERSION` — this spec's change is its first mandatory
  bump).
- **Relates to:** spec 093 (the landed chunking/extraction machinery),
  `code_grams`'s own "must never introduce false negatives" contract.

## Intent

Chunks split with no overlap, and grams are extracted per chunk and
intersected per chunk id. A match straddling a 2048-char cut whose
straddling trigrams appear in **no single chunk of the file** is never
nominated; the entry is `encoded`, so the overlay skips it too;
`allow_scan=True` does not help (it bypasses the refusal gate, not
`scan_all`). Silent — `success=True`, `errors=[]`. Verification
fetches the full body, so the loss is narrower than "every straddle" —
an entry recovers when every required trigram recurs elsewhere in some
chunk — but the failing class is routine for intra-line cuts: lines
longer than the chunk budget (minified JS/CSS, single-line JSON, long
log lines, CSV rows, base64) — precisely the ETL corpus the project
declares first-class. Reproduced on sqlite and live Postgres with a
4 KB log line and minified JSON.

One sentence: **no chunk cut may remove a trigram from the entry's
nomination set — close the gap at the extraction grain, bump the
format knob, and pin the boundary class in the batteries that missed
it.**

## Shape

### 1. The grain fix — resolved: entry-grain extraction (ADR 036)

The drafted option (a) — overlap emission with the per-chunk
intersection untouched — was **refuted by execution at kickoff**:
grep's AND requires every chosen gram in the *same* chunk, so a
needle straddling a cut with ≥ `GRAM_SIZE` chars on each side keeps
its interior trigrams in two different chunks under any fixed-width
overlap (sweep: splits 1/5, 2/4, 3/3 all stay lost). Every sound fix
makes nomination entry-grain; Clay decided the coupling itself is the
defect (full argument and rejected middle options in ADR 036).

What lands:

- **Extraction** runs once over each entry's full folded body;
  postings carry the entry surrogate id (`entries.id`) as `doc_id`.
  Codec, rarest-first budgeted intersection, and verify unchanged in
  shape; candidate mapping drops the chunks-table hop.
- **Eligibility** materializes as an `indexable` boolean on the entry
  row, stamped by the chunking phase's version-guarded flip: within
  the byte and distinct-gram bounds and ≥ `GRAM_SIZE` normalized
  bytes. The pending-work probe reads `chunked AND NOT encoded AND
  indexable` — the correlated-EXISTS-on-chunks probe retires.
- **Chunks stay semantic-only**: reindex keeps refreshing them for
  the future vector/BM25 pipeline; no grep-path code reads them.
- `INDEX_FORMAT_VERSION` → 2 (spec 095 §6's first consumer), and the
  extraction docstring states the invariant: *every trigram of the
  entry's folded body is in the entry's posted gram set.*

### 2. Whitespace-only spans (verified adjacent lead)

`split_code` drops whitespace-only spans entirely — under chunk-grain
extraction, a second coverage gap of the same class. **Closed by
construction under §1**: the full body is the extraction stream, so
dropped spans are still bytes of it. The §3 battery keeps a
whitespace-span shape as the pin.

### 3. The boundary battery

The batteries that validated 093 never placed a needle across a cut —
the differential corpora are short-line ASCII. Add:

- Conformance rows: needle straddling the chunk cut (minimal
  `"a"*2045 + needle` shape), long-line realistic shapes (minified
  JSON, 4 KB log line), each asserted **after** reindex on the indexed
  tier.
- A boundary edition in the grep differential battery: corpus rows
  engineered so matches land on, before, and across every cut.
- The §2 whitespace-span shape.

### 4. Postings-codec boundary pin (memo finding 19)

The over-wide-varint test feeds an 11-byte varint; the minimal illegal
width is 10, and the mutant `_MAX_VARINT_BYTES = 10` survives the
suite while decoding a crafted 10-byte blob silently wrong (`[5]` via
int64 wrap) — the class the codec docstring forbids. One test: the
10-byte minimal illegal blob refuses loudly. (Homed here because the
codec battery is this spec's test surface; no production code change.)

## Verification obligations

- Suite green, coverage 100%, `ruff`/`ty` zero.
- The memo's straddle repros (`v1_straddle.py`, `v1_realistic.py`
  shapes) re-expressed as tests and passing on sqlite + live Postgres.
- Four Docker engine legs green with the boundary rows live (rides
  spec 095 §9's engine-marked reindex battery).
- Index-size delta of entry-grain postings measured and recorded in
  the landing message (per-entry dedupe should shrink it).

## Touch points

`src/vfs/models/rows.py` (`indexable` column),
`src/vfs/storage/backends/database/indexing.py` (entry-grain build,
eligibility stamp, probe, knob bump),
`src/vfs/storage/backends/database/grep.py` (entry-id candidates, no
chunks hop), `tests/models/test_postings.py` (§4),
`tests/storage/database/test_indexing.py` + conformance battery (§3),
`context/research/studies/2026-08-05-grep-differential-battery/`
(boundary edition rider). ADR 033 status annotation + ADR 036 are
written.

## Slices

- **A** — §1 landed per ADR 036 with the knob bump + minimal straddle
  row.
- **B** — §3 battery + the §2 whitespace-span pin.
- **C** — §4 codec pin (independent; can land first).

## Open questions

None — the §1 fork was resolved by Clay at the 2026-08-13 kickoff
(ADR 036; recorded in `open-questions.md`).
