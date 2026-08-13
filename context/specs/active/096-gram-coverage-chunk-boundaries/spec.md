# 096 — Gram coverage: chunk boundaries stop eating matches

- **Status: draft 2026-08-13** — born from the review campaign memo
  (`research/2026-08-13-glob-grep-indexing-review-campaign.md`,
  finding 3 critical + adjacent leads). One owner fork marked
  `[NEEDS CLARIFICATION]` and pointered in `open-questions.md`.
- **Date:** 2026-08-13
- **Owner:** Clay Gendron
- **Kind:** correctness repair of gram extraction at chunk boundaries
  + coverage-class test battery + one postings-codec boundary pin.
- **Depends on:** ADR 033 (chunk-grain corpus, posting doc-id grain,
  the no-false-negatives rule), spec 095 §6 (`INDEX_FORMAT_VERSION` —
  this spec's change is its first mandatory bump).
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

### 1. The grain fix `[NEEDS CLARIFICATION — fork, pointered]`

Two mechanics close the class; both make every body trigram
nominable:

- **(a) Overlap emission (recommended by the memo):** chunk emission
  carries `GRAM_SIZE − 1` characters of overlap — either by actually
  overlapping stored chunks or (smaller) by extracting grams over each
  boundary window and attributing them to the preceding chunk id. The
  posting doc-id grain, the intersection, and the verify path are
  untouched; index size grows by a boundary term only.
- **(b) Per-entry extraction grain:** extract grams over the whole
  entry and post at entry grain. Cleaner statement of the invariant,
  but it re-opens ADR 033 §4's doc-id grain decision (posting ids,
  dedupe, budget arithmetic all shift) — a materially bigger change.

Whichever lands: `INDEX_FORMAT_VERSION` bumps (spec 095 §6), and the
extraction docstring states the invariant: *every trigram of the
entry's folded body appears in at least one chunk's gram set.*

### 2. Whitespace-only spans (verified adjacent lead)

`split_code` drops whitespace-only spans entirely — a second
extraction-coverage gap of the same class (a pattern spanning a
dropped span can lose its bridging trigrams). Confirm the reach with
the §3 battery shapes and close it with the same invariant; if it
turns out unreachable (fold collapses the class first), record that in
the extraction docstring instead of adding machinery.

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
- Index-size delta of the chosen grain fix measured and recorded in
  the landing message (boundary term only for fork (a)).

## Touch points

`src/vfs/models/chunk.py` / `src/vfs/models/code_grams.py` (grain
fix), `src/vfs/storage/backends/database/indexing.py` (extraction
call sites, knob bump), `tests/models/test_postings.py` (§4),
`tests/storage/database/test_indexing.py` + conformance battery (§3),
`context/research/studies/2026-08-05-grep-differential-battery/`
(boundary edition rider).

## Slices

- **A** — §1 fork resolved and landed with the knob bump + minimal
  straddle row.
- **B** — §3 battery + §2 whitespace-span closure.
- **C** — §4 codec pin (independent; can land first).

## Open questions

- The grain fork (§1): overlap emission vs per-entry grain — (a) is
  the memo's recommendation; (b) re-opens ADR 033 §4.
  `[NEEDS CLARIFICATION]`
