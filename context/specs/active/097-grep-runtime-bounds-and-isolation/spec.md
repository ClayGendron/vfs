# 097 — Grep runtime: epoch consistency, resource bounds, contract pins

- **Status: implemented 2026-08-13, uncommitted** — born from the
  review campaign memo
  (`research/2026-08-13-glob-grep-indexing-review-campaign.md`,
  findings 7–9, 11, 15, 18, 20 + verified-adjacent leads). The §1 fork
  was resolved by Clay at kickoff (2026-08-13, recorded in
  `open-questions.md`): the **epoch-reread retry ladder**, plus a
  rider — reindex gains a crash-safe **single-runner lease** (§1b),
  with the timer-task heartbeat shape and the permissive budget
  postures (§5 no branch cap; §2 configurable wall clock) also Clay's
  in-session calls. Landing ledger, all same day: suite 2,243 passed
  at 100.00% coverage, ruff/ty zero; **four Docker legs green with
  the two §1 race rows live** (Postgres 201 / MySQL 202 / MSSQL 203 /
  Oracle 200 passed, 4 capability skips each) — the grep-vs-
  publish+reclaim row and the concurrent-reindex refusal row pass on
  every engine, and both were validated end-to-end on sqlite first.
  **§3 EXPLAIN evidence (Postgres, 20k rows, ≈1% dirty):** no index =
  Seq Scan, 228 buffers, 0.93 ms; btree `(encoded)` = Index Scan, 202
  buffers, 0.21 ms; btree `(encoded, kind)` = Bitmap, 191 buffers,
  0.35 ms — **`(encoded)` alone chosen** (fastest, narrowest write-
  side maintenance; `kind` filtered only 11 rows). §6 mutants killed
  by hand: dropping `invert_match` from `scan_all` fails the new
  post-reindex invert row; popping the tier traits fails three rows
  (the hardened `_indexed_grep_tier` fails on absence instead of
  skipping). `SCHEMA_FORMAT_VERSION` → 3 (096's `indexable` column
  rode without a bump; this landing's lease columns + index take it
  with them). One observed-once anomaly, not reproduced: the first
  combined MSSQL leg on a fresh container hung client-side (two
  sessions idle in open write-path transactions, zero server-side
  blocking); races and conformance passed in isolation and the exact
  combined selection re-ran green (203/87 s) — filed as Rosetta
  first-run flakiness, worth an eye on future legs.
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

### 1. Epoch consistency on every engine — resolved: epoch-reread ladder

Memo finding 7 (major): Postgres/MySQL profiles pin REPEATABLE READ;
MSSQL/Oracle/GENERIC run the ladder at statement-level READ COMMITTED,
so a rival publish+reclaim between the pointer read and the
posting/entry reads empties both tiers for that call (reproduced live
on MSSQL and Oracle: `rows=0, success=True`). Contradicts ADR 033 §6
and backend.py's one-snapshot claim.

Resolved (Clay, kickoff): the **epoch-reread ladder**. After grep's
last epoch-dependent read (index candidates *and* the `NOT encoded`
overlay both count — `encoded` flips at publish), re-read the pointer;
movement raises `StaleSnapshot`, which the existing `with_retry`
restarts on a fresh session, exhaustion classifying as a retryable
`conflict`. Soundness (verified in-session): `reclaim_epochs` commits
strictly after the publish CAS, so every observable mix moves the
pointer first; the pointer is monotonic, so the re-read cannot false-
negative. On pinned engines the re-read is a same-snapshot no-op; no
call pattern pays more than one cheap SELECT. Isolation pins rejected:
Oracle would pay SERIALIZABLE/ORA-08177, MSSQL SNAPSHOT demands a
database-level prerequisite, and GENERIC cannot be pinned — the
declared floor would keep the bug. Lands with an engine-marked race
row on the spec 095 §9 battery (grep concurrent with reindex, all
four legs).

### 1b. Reindex single-runner lease (Clay's kickoff rider)

Two concurrent reindexes are already *correct* (epoch mint unique-key
collision → `StaleSnapshot`; publish CAS picks one winner; the loser
reclaims its build) but both pay the full build. Clay's rider: make
"a reindex is running" first-class —

- **Lease on the meta row**: `reindex_holder` (opaque token) +
  `reindex_heartbeat` (epoch-milliseconds). Claim is one guarded
  UPDATE: `WHERE holder IS NULL OR heartbeat < now − TTL`. A zero-row
  claim means a live run exists → the verb refuses loudly (kind
  `conflict`, retryable, message naming the running lease's age) —
  that refusal *is* the "currently running" signal.
- **Heartbeat** (Clay, in-session): a background `asyncio` beat task
  under an async context manager — claim, then pulse the guarded
  refresh every `REINDEX_HEARTBEAT_SECONDS` (60s against the 5-min
  TTL: four missed beats of slack) on its own short transactions, so
  arbitrarily long phases stay covered on server engines; on the
  single-connection sqlite host a mid-phase beat just queues to the
  phase boundary (where rival reindexers cannot exist anyway). A
  zero-row refresh means the lease was taken: the task flags it and
  the run stops at the next phase boundary with a retryable
  `conflict` rather than racing the usurper; a transient beat failure
  is absorbed by the TTL, never treated as loss. Exit cancels and
  awaits the beat task *before* the best-effort release. The lease
  stays an arbiter, not a guard correctness depends on — a claim-
  through still lands on today's CAS arbitration (duplicated work,
  never corruption).
- **Crash posture**: release is best-effort (clear on completion); a
  crashed run simply stops heartbeating and the lease expires after
  the TTL, so no state wedges. The crashed build's partial rows were
  already inert by design — built-but-unpublished epochs are skipped
  by the next build and reclaimed after its publish; `chunked` work
  committed by the dead run is kept work, not dirt.
- **Clocks**: heartbeat comparisons mix writers' clocks only across
  app instances; the TTL is minutes-scale against seconds-scale
  batch gaps, and the tolerance is documented at the constant.

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
- The wall-clock budget is constructor-configurable (Clay,
  2026-08-13, in-session): `DatabaseStorage(grep_wall_seconds=…)`,
  default the declared 10.0, non-positive refused at construction —
  the `trash_days` shape.
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
  alternations fetch one exempt blob per branch. **Resolved (Clay,
  2026-08-13, in-session): declare the exposure, never cap the
  width** — bulk unions (IOC lists, generated symbol sweeps) are a
  supported shape, and the hostile case (65+ distinct-prefix branches
  of corpus-common trigrams) is contrived, not easy to hit; caps are
  imposed only where trouble is easy to reach. The bound is time, not
  shape: the wall-clock deadline is consulted between OR branches,
  truncating loudly. (Also verified: CPython's parser factors shared
  literal prefixes, so similar-string unions never even branch, and
  parenthesized unions already plan gramless.)
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
`src/vfs/storage/backends/database/indexing.py` (§1b lease),
`src/vfs/models/rows.py` (§3 index, §1b lease columns),
`src/vfs/storage/backends/database/backend.py` (§6 traits hardening),
`tests/storage/database/test_grep.py`, conformance battery rows
(§1/§6), ADR 033 annotations (§5 exemption, §6 consistency mechanics).

## Slices

- **A** — §3 + §4 (index and bounded merge: pure wins, no forks).
- **B** — §2 (content budget + deadline).
- **C** — §1 + §1b (ladder, lease; race row on the 095 battery).
- **D** — §5 + §6 (declarations and pins).

## Open questions

None — the §1 fork was resolved by Clay at the 2026-08-13 kickoff
(epoch-reread ladder + the §1b lease rider; recorded in
`open-questions.md`).
