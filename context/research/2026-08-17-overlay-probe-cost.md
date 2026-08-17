# The overlay probe's fixed cost: where it lives and what removes it

- **Status**: research memo — design input for a pending decision on
  cutting the scan-tier overlay probe (~1.6–2.5 ms paid on every grep
  call) now that the scoped ladder's remaining rg gaps are single-digit
  milliseconds. The working hypothesis entering this research — a
  partial index on `NOT encoded` — is **refuted by measurement**; the
  evidence points to a different, portable schema change plus a small
  code change.
- **Date**: 2026-08-17
- **Owner**: Clay Gendron
- **Question**: The profiler for the scoped-grep work measured the
  `NOT encoded` overlay probe at ~1.6–2.5 ms on every grep call even
  though the overlay is nominally empty post-reindex and an index on
  `encoded` already exists. Where do those milliseconds actually live
  (DB execution vs SQLAlchemy statement work vs async-driver hops),
  and which mechanism — partial index, composite index, EXISTS
  fast-path, epoch-read piggyback, or maintained counter — removes
  them across the production engines?
- **Evidence gathered**: executed decomposition experiments on APFS
  clones of the 2026-08-16 linux-tree store (93,760 files, all
  encoded; scripts and raw JSON in
  `studies/2026-08-17-overlay-probe-index/`), EXPLAIN plans for every
  variant, index-maintenance timings at ETL batch scale; plus a
  cited engine survey (SQLite/Postgres/MSSQL/Oracle/MySQL partial and
  filtered index semantics, SQLAlchemy modeling and compiled-cache
  behavior — `studies/2026-08-17-overlay-probe-index/SURVEY.md`) with
  read-only source study of the postgres and sqlalchemy checkouts.

---

## 1. Reproduction and a discovery: the overlay is not empty

Timing the real code path (`_entries_for_scan`, `everything=False`,
arguments exactly as `grep_rows` passes them, real `AsyncSession`)
reproduces the profiler: **1,704 µs gateless / 1,607 µs gated** on the
benchmark store; the same SQL through sync `sqlite3` costs ~1,340 µs,
so the cost is real DB work, not measurement artifact.

The store's overlay also turns out to be non-empty by design: **96
files sit at `chunked=1, indexable=0`** (`/MAINTAINERS`, giant
generated headers) — `chunk_dirty` marks them index-ineligible, so
`encoded` stays 0 forever and they legitimately ride the scan tier on
every call. A truly-emptied clone still costs **979 µs** per probe.
Any "skip when empty" gate therefore helps only corpora with zero
ineligible files; the probe itself has to get cheap.

## 2. Decomposition: it is the database, not Python

Measured split of the ~1.7 ms (empty-overlay clone, gateless):

| component | cost | notes |
| --- | --- | --- |
| build the `select()` object | ~50 µs | per call |
| compiled-cache key + lookup | ~0.1 µs | cache **hits every call**; zero recompiles over repeated fresh builds |
| async driver hop (aiosqlite) | ~95–140 µs | fixed per statement (`SELECT 1` baseline) |
| SQLite execution | **~650–1,350 µs** | the only part that grows with the store |

Verdict: **H1 (DB execution) dominant at 75–85%; H2 (SQLAlchemy
statement work) minor at ~150–200 µs — the compiled cache works as
documented; H3 (driver hop) real but small.** The pre-research theory
that statement construction dominates is wrong.

## 3. Why the DB side costs a millisecond: index pollution

EXPLAIN shows the existing `ix_vfs_entries_encoded` **is used**
(`SEARCH vfs USING INDEX ix_vfs_encoded (encoded=?)`). The cost is
what else lives under `encoded = 0`:

- **Directories** — written `encoded=False` and never encoded: 6,160
  rows in the seek set, each paying a rowid lookup into the 3.4 GB
  table only to be rejected by the `kind IN` filter (~0.19 µs/row
  ≈ 1.17 ms). This is the millisecond.
- **Trash** (0 rows in this store, but grows unbounded by code
  reading): delete demotes `encoded=0` and `chunk_dirty` only
  re-covers `deleted_at IS NULL`, so trashed *files* sit in the seek
  set until swept — they match `encoded=0 ∧ kind='file'`, so no index
  shape filters them; only the meta/liveness arms reject them, after
  the row fetch.

## 4. Mechanisms, measured on clones

| mechanism | probe cost (empty / steady-state) | verdict |
| --- | --- | --- |
| **Partial index `WHERE NOT encoded`** (the entering hypothesis) | unchanged (~1,248 µs) | **dead end — the SQLite planner never chooses it**, in either the bare or kind-scoped form; non-portable besides (survey §6) |
| **Composite `(encoded, kind)` replacing `ix_encoded`** | DB 1,070→**5.5 µs** / 1,340→**180 µs**; call 979→**393 µs** / 1,704→**839 µs** | **works, portable** — plan becomes `(encoded=? AND kind=?)`; maintenance +2.2% on a 10k `encoded=0` insert, +5.5% on the 103k-row reindex flip, +640 KiB |
| Stamp directories `encoded=1` | DB **3.7 µs** / **172 µs** with the existing index | same effect, zero schema change, but semantic surgery: mkdir stamps, delete's demotion must skip directories |
| Separate `EXISTS` fast-path statement | **8–10 ms** without an index fix (planner picks `ix_kind`, scans ~93k rows); µs after one, but ~150–200 µs round trip ≈ the fixed probe | never as a separate statement; spelling is load-bearing (`encoded = 0` seeks, bareword `NOT encoded` scans) |
| **Overlay-`EXISTS` piggybacked on the epoch-pointer read** | pointer read alone 186–223 µs; pointer + EXISTS scalar subquery **165–187 µs** — marginal cost ≈ 0 | **works** — "overlay empty → skip `_entries_for_scan`" for free; saves the residual ~300–400 µs where the overlay is truly empty |
| Maintained counter in the meta row | read side identical to piggybacked EXISTS | **rejected** — write side hot-spots a single row under concurrent 10k-batch ETL writers for no read benefit |

A note for the record: `rows.py`'s comment beside `ix_encoded`
("measured faster than an (encoded, kind) composite") is contradicted
by these measurements — with directory pollution in the seek set the
composite wins in both states. The original measurement predates the
directory population at this scale.

## 5. The engine survey: portability of each shape

Full survey with citations in `studies/…/SURVEY.md`. The facts that
bind the design:

- **Partial indexes**: SQLite (textual predicate match, no binds),
  Postgres (`predtest.c` prover; parameterized clauses never match),
  MSSQL (filtered indexes; **forced parameterization silently
  disqualifies them** — the one operational landmine, worth a
  `db_test` leg if ever adopted), Oracle (none through 23ai; only the
  function-based-index NULL trick), MySQL/MariaDB (none; a plain
  index on the boolean *is* used for the rare value via index dives).
  One SQLAlchemy `Index` can carry `sqlite_where` /
  `postgresql_where` / `mssql_where` simultaneously while Oracle,
  MySQL, and GENERIC render it plain. All of this is moot for the
  recommended design — the composite is an ordinary index everywhere.
- **The composite `(encoded, kind)`** is plain-B-tree portable: worst
  case on any engine is one index descent (~4–5 pages at 10⁸ rows).
- **SQLAlchemy renders `~encoded` as an inline literal on all five
  dialects** (`NOT encoded` on PG, `encoded = 0` elsewhere) — an
  ORM-built probe predicate is bind-free everywhere, which is what
  makes the seek shapes above reachable at all. Keep the probe
  ORM-built; never raw-text `NOT encoded`.
- **Compiled cache**: hits on every probe execution today (measured
  §2); `.in_()` uses expanding parameters and does not disable
  caching. No pre-compilation machinery is warranted.

## 6. Recommended direction (for the decide stage)

1. **Schema**: replace `ix_{table}_entries_encoded` with a composite
   `(encoded, kind)` index, and fix the stale comment beside it.
   Probe DB time drops ~250× empty / ~7× steady-state; costs +2%/+5.5%
   on write/reindex maintenance and +640 KiB at linux scale.
2. **Code**: ride an overlay-`EXISTS` scalar on the epoch-pointer
   read `grep_rows` already performs, and skip `_entries_for_scan`
   when the overlay is empty — measured marginal cost ≈ 0, removes
   the last ~300–400 µs (statement build + driver hop) in truly-empty
   corpora.
3. **Design follow-up, separate decision**: trash pollution — trashed
   files match `encoded=0 ∧ kind='file'` forever, rejected only after
   row fetch. Delete stamping `encoded=True` (restore demoting) would
   make `encoded=0 ∧ kind∈CONTENT_KINDS` exactly the overlay and the
   EXISTS gate exact. Touches trash/restore semantics; needs its own
   look at the reindex and `chunk_dirty` interplay.
4. **Rejected on measurement**: partial/filtered indexes (planner
   never chooses the shape; non-portable), a separate EXISTS round
   trip (overhead ≈ the fixed probe), a maintained meta-row counter
   (ETL write hot-spot for zero read benefit).

Projected effect on the two remaining rg-favored bench rows: ~1.3 ms
off `spin_lock @ kernel/**/*.c` (23.4 ms → ~22 ms) and
`GFP_KERNEL @ mm/**` (15.6 ms → ~14 ms, ahead of rg's 15.1) — plus
~1.3 ms off every grep call at any scale, scoped or not.
