# 097 — Grep runtime: epoch consistency, resource bounds, contract pins

- **Status: draft 2026-08-13** — born from the review campaign memo
  (`research/2026-08-13-glob-grep-indexing-review-campaign.md`,
  findings 7–9, 11, 15, 18, 20 + verified-adjacent leads). One owner
  fork marked `[NEEDS CLARIFICATION]` and pointered in
  `open-questions.md`.
- **Date:** 2026-08-13
- **Owner:** Clay Gendron
- **Kind:** grep-verb hardening — epoch-consistent reads on every
  engine, bounded memory on both tiers, one serving index, and the
  test pins that make the tier contract survive mutation.
- **Depends on:** ADR 033 (§6 "old or new, never a mix"; §5 the
  invert-stays-scan-shaped contract; budgets and truncation), spec 095
  (the writer half of the epoch race surface; its conformance battery
  carries rows this spec adds to).
- **Relates to:** the open-questions entry "Grep's query-wide result
  bound"; CLAUDE.md's production posture (10k+ batches, tightest
  engine as the floor, latency-sensitive agent path).

## Intent

The grep pipeline is correct on the engines and corpora the batteries
exercised, and unbounded or unpinned just outside them: the ladder is
epoch-consistent only on engines with an isolation pin (MSSQL, Oracle,
and GENERIC silently lose matches during a concurrent reindex); the
scan tier materializes up to 10,000 full bodies with no byte budget
and no deadline check around the fetch; the permanent overlay is a
whole-table pass with no serving index; and two load-bearing routing
facts (invert's scan membership, the declared tier traits) survive
mutation because no test pins them.

One sentence: **make every grep read epoch-consistent on every
declared engine, put a byte budget and the deadline around everything
the verb materializes, give the overlay its serving index, declare the
one undeclared budget policy, and pin the routing contract so the
suite defends it.**

## Shape

### 1. Epoch consistency on every engine
`[NEEDS CLARIFICATION — fork, pointered]`

Memo finding 7 (major): Postgres/MySQL profiles pin REPEATABLE READ;
MSSQL/Oracle/GENERIC run the ladder at statement-level READ COMMITTED,
so a rival publish+reclaim between the pointer read and the
posting/entry reads empties both tiers for that call (reproduced live
on MSSQL and Oracle: `rows=0, success=True`). Contradicts ADR 033 §6
and backend.py's one-snapshot claim. Two mechanics:

- **(a) Pin op isolation** on the unpinned profiles (MSSQL
  SNAPSHOT/REPEATABLE READ; note Oracle offers READ COMMITTED or
  SERIALIZABLE only — the pin there is SERIALIZABLE with its
  ORA-08177 retry posture, a real cost).
- **(b) Epoch-consistent ladder:** re-read the epoch pointer after
  the ladder's last read; if it moved, retry the call (bounded
  retries, then loud `unavailable`). Engine-independent, no isolation
  cost, one extra cheap statement per call — and it protects the
  GENERIC floor, which profile pins cannot promise.

The memo leans (b) for the floor argument; either must land with an
engine-marked race row on the spec 095 §9 battery (grep concurrent
with reindex, all four legs).

### 2. Content materialization gets a byte budget and the deadline

Memo finding 8 (major): `_content_for_entries` fetches the entire
gated candidate set's bodies into one dict — measured 251.7 MB for a
1-row result, 307 MB at the 10k candidate cap, identical on Postgres;
files over `MAX_INDEXABLE_BYTES` never encode, so large-file corpora
pay this on *every* grep; the wall-clock deadline is checked before
and after — never around — the fetch; `files`/`count` modes retain
every body they discard.

- A declared `CONTENT_BYTE_BUDGET` bounds bytes in flight: chunked
  fetch → verify → release, never the whole set resident.
- The deadline is consulted per fetch chunk; an expired call stops
  fetching and reports its truncation loudly (the existing
  warning-severity record).
- `files`/`count` modes drop bodies at verification, retaining only
  the verdict.
- Scale pin: peak-RSS-shaped test at the candidate cap (the memo's
  measured shapes), plus a deadline-expiry row asserting no
  post-expiry fetch.

### 3. The overlay gets its serving index

Memo finding 9 (major): the permanent overlay filters
`kind IN (...) AND NOT encoded` with no index on `encoded` — a
whole-table pass per grep at steady state (measured: 2,286 buffers at
20k rows, linear; the btree remedy measured 6 buffers). Add the index
in `rows.py` — `encoded` alone or `(encoded, kind)`, decided by a
quick EXPLAIN comparison on Postgres at the 20k-row shape; record the
choice in the model docstring beside the flag pair.

### 4. Scan-merge bounds and the loop deadline

Memo finding 18 (minor) + verified lead: the scan-side merge holds
arm-chunks × (limit+1) rows before truncating (~1M RowMappings at the
router's 10k-root contract), and the arm-chunk loop checks no
deadline — one measured run burned 9.43 s of a 10 s budget inside the
executor and returned zero observations. Per-chunk top-(limit+1) is
the correct merge input (proven), so: prune incrementally to the
lowest limit+1 while chunks arrive, and consult the deadline between
arm chunks with the loud truncation record on expiry.

### 5. Budget policy true-ups (declare what the code does)

- Memo finding 15 (minor, resolved posture — declare): the rarest
  gram is always fetched regardless of `POSTING_BYTE_BUDGET`, once
  per OR branch. This is the right call (strict enforcement would
  silently lose index-side matches — verified), so *declare* it: the
  module docstring and the ADR 033 §5 annotation state the
  first-gram exemption; a test pins the over-budget sole-gram fetch.
- Verified lead alongside: nothing caps OR-branch count, so wide
  alternations fetch one exempt blob per branch. Bound it with the
  existing budget vocabulary (branches beyond the cap route to the
  scan tier loudly) or declare the exposure; either lands in the same
  docstring.
- Verified lead from the review's overlay analysis: when the index
  side saturates `CANDIDATE_BUDGET`, the overlay union is skipped
  entirely — freshly-written (scan-side) files silently drop out of a
  busy pattern's results behind a generic truncation record. Make the
  truncation record name the skipped overlay, or reserve overlay
  headroom inside the budget; pin whichever posture is chosen.

### 6. The routing contract gets its pins

- Memo finding 11 (major): `scan_all = invert_match or plan.is_any()`
  — dropping `invert_match` survives the suite because the
  conformance pin never reindexes. The 4-line missing test (write two
  files, reindex, invert-grep, assert the non-containing file) lands
  beside `TestOverlayPartition`; the fixed_strings/word_regexp rows
  get the same post-reindex variant (verified same blind spot).
- Memo finding 20 (minor): no test asserts the declared
  `grep_tier`/`grep_staleness` traits, and the conformance battery
  gates on them — popping the traits flips 4 rows to skip with zero
  failures. Land a direct traits pin beside the capabilities pin, and
  harden `_indexed_grep_tier`: absence of the trait fails; only an
  explicit `"scan"` skips.

## Verification obligations

- Suite green, coverage 100%, `ruff`/`ty` zero.
- §1's race row green on all four legs (the MSSQL/Oracle repro
  re-expressed); §2's RSS and deadline pins; §3's EXPLAIN evidence
  recorded in the landing message; §6's mutants killed (verified by
  running the two mutations by hand before landing).
- Four Docker engine legs green; Postgres EXPLAIN comparison for §3
  attached to the landing message.

## Touch points

`src/vfs/storage/backends/database/grep.py` (§1 ladder, §2, §4, §5),
`src/vfs/storage/backends/database/dialects.py` (only if fork (a):
isolation pins), `src/vfs/models/rows.py` (§3 index),
`src/vfs/storage/backends/database/backend.py` (§6 traits hardening),
`tests/storage/database/test_grep.py`, conformance battery rows
(§1/§6), ADR 033 annotations (§5 exemption, §6 consistency mechanics).

## Slices

- **A** — §3 + §4 (index and bounded merge: pure wins, no forks).
- **B** — §2 (content budget + deadline).
- **C** — §1 (fork resolved; race row on the 095 battery).
- **D** — §5 + §6 (declarations and pins).

## Open questions

- Fork (§1): isolation pins per profile vs the epoch-reread retry
  ladder — the GENERIC floor and Oracle's SERIALIZABLE-only pin cost
  are the deciding facts. `[NEEDS CLARIFICATION]`
