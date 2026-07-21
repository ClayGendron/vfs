---
name: scale_review
description: Review a diff or branch for correctness and boundedness at production scale — 10,000+-entry batches, the least generous SQL engine, real concurrency. Use when the user asks to "scale review", "check this at scale", "will this survive a 10k batch", "review for Oracle/SQL Server limits", "audit statement growth", or before landing any change that touches the database backend, a write/read builder, or a loop over batch input.
---

# Scale review — bounded on the least generous engine

One question, asked of every touched statement, loop, and collection:
**does this stay correct and bounded when the batch is 10,000+ entries,
the engine is the tightest one we serve, and other sessions are writing
at the same time?** Batches of 10,000+ files in a single call are a
supported contract here, not an edge case — and SQLite's generous limits
prove nothing, because production runs on Postgres, SQL Server, Oracle,
and any other SQLAlchemy engine. A design that only works within
SQLite's caps is a bug, not a style issue.

The declared budgets live in
`src/vfs/storage/backends/database/dialects.py`: per-dialect
`DialectProfile`s carry `in_list_budget` and `key_byte_budget`; the bind
budget is read live off `dialect.insertmanyvalues_max_parameters`; the
chunk size for membership predicates is `membership_budget(profile,
parameter_budget)` and slicing goes through `chunked()`. Unknown
dialects resolve to the `GENERIC` floor. Review against those, not
against intuition.

## Process

### 1. Inventory what grows

List every SQL statement the diff touches or adds (builders, raw
`text()`, ORM constructs), every loop over batch input, and every
collection populated from query results. For each, name **the variable
that scales with batch size**: the entries list feeding an `IN (...)`,
the rows in a bulk `VALUES`, the bind parameters per row times rows, the
accumulator holding results. Anything with no batch-scaled variable is
out of scope; everything else gets audited. This inventory is the
skeleton of the report.

### 2. Statement-growth audit

For each statement with a batch-scaled variable, ask what the statement
looks like at 10,000 entries:

- **`IN`-lists** must chunk by `membership_budget(...)` and merge
  results. An unchunked `path IN :paths` is a finding even if every
  current caller passes ten paths — the contract is 10,000.
- **Bulk inserts/updates** must respect the bind-parameter budget.
  Parameters multiply: 10 columns times 1,000 rows is 10,000 binds.
  SQLAlchemy's insertmanyvalues batching covers plain `insert()`
  executemany; hand-rolled multi-row `VALUES`, `UPDATE ... FROM`
  constructs, and compound `OR` fans do not get that protection and
  must chunk explicitly.
- **Composite predicates** count too: `(path, version) IN (...)` and
  `OR`-of-tuples shapes consume elements and binds faster than flat
  lists.
- Verify the merge: chunked reads must recombine partial results
  correctly (ordering, dedup, exists-maps keyed per chunk), and
  chunked writes must keep their all-or-nothing story inside one
  transaction or say why not.

### 3. Engine floor check

Judge every limit against the tightest cap actually served, never the
dev engine: Oracle's 1,000-element `IN`-list cap is the `GENERIC`
floor's `in_list_budget`; SQL Server's ~2,100 bind parameters bounds
both membership chunks and bulk rows; `key_byte_budget` floors at
1,700 bytes for index keys. A literal constant like `CHUNK = 5000` is
a finding: budgets come from the profile and the live dialect, not
from numbers that happen to fit one engine. Also flag any use of
engine-specific SQL or behavior (dialect-only functions, SQLite
pragma assumptions, upsert syntax outside the declared `arbitration`
mechanism) that the `GENERIC` path cannot serve.

### 4. Query-shape review

- **N+1 / query-in-loop**: any per-entry `SELECT`, `INSERT`, or
  `UPDATE` inside a loop over batch input is 10,000 round-trips.
  Point-wise statements must become bulk set operations with chunked
  membership.
- **Chatty sequences**: multiple dependent statements per entry
  (read-check-write per row) multiply both round-trips and race
  windows; prefer one set-based statement or one read plus one write
  per chunk.
- **Predicate/index fit**: a new `WHERE` predicate or `ORDER BY` on a
  large table implies an index. Check the touched models/DDL for one
  that serves it (leading columns, liveness filters); a full scan per
  chunk at 10k entries is a finding.
- **Overfetch**: selecting whole rows (or LOB/content columns) where
  only ids or paths are consumed.

### 5. Memory-growth audit

Trace each batch-scaled collection to its high-water mark: lists that
accumulate all rows before processing, dicts keyed by every entry,
results concatenated across chunks and then copied again. Chunking the
SQL but materializing the union of all chunks is fine when the caller
is owed the full result; building *intermediate* whole-batch structures
that could stream chunk-by-chunk is a finding. Watch for quadratic
shapes: repeated list concatenation, membership tests against a list
instead of a set, per-chunk rescans of the whole batch.

### 6. Concurrency and isolation

Assume READ COMMITTED unless the code pins otherwise (the profiles pin
Postgres op-sessions to REPEATABLE READ; others run engine defaults).
For every read-then-write the diff touches, ask what a concurrent
committed write does between the read and the write:

- **Lost updates**: unguarded `UPDATE` based on previously read state
  overwrites concurrent commits. Look for a guard — a version/liveness
  predicate in the `WHERE`, an atomic set-based update, or the declared
  arbitration path (`upsert` vs `catch_retry`).
- **Check-then-act races**: existence checks followed by inserts must
  go through arbitration, not a bare `SELECT`-then-`INSERT`.
- **Cross-chunk visibility**: a chunked read at READ COMMITTED can see
  different snapshots per chunk; flag logic whose correctness assumes
  one consistent snapshot across chunks.
- **Retry discipline**: new error paths must classify via
  `is_retryable(...)` (SQLSTATE/code, never message text), and retried
  work must be idempotent at the restart boundary.

### 7. Evidence standard

Every finding names three things: **the statement or loop** (file,
function, the construct itself), **the variable that grows with batch
size**, and **the specific cap or resource it can exceed** (the 1,000
`IN`-list floor, the ~2,100 bind budget, the key-byte budget,
round-trip count, resident memory, a lost-update window). "This looks
slow" is not a finding. If chunking exists, verify the budget it uses
is the declared one and the merge is correct — a finding may equally
be "chunked, but by a hardcoded size" or "chunked, but the exists-map
drops keys across chunks".

### 8. Deliverable

Report findings ordered by severity, each with the violated bound:

- **Blocker** — fails outright at contract scale on a supported engine
  (statement over an engine cap, unbounded growth, lost-update window
  on user data).
- **Major** — survives but degrades badly or is one caller away from a
  blocker (N+1 at 10k, whole-batch intermediates, missing index on a
  hot predicate, hardcoded chunk size).
- **Minor** — bounded but wasteful (overfetch, avoidable round-trips).

Close with what was checked and found clean, so a clean audit is
distinguishable from an unfinished one.
