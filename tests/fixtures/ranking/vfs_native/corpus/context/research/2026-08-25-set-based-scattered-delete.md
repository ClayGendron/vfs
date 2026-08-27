# Set-based scattered delete — spec 102's research questions, answered on five engines

- **Date:** 2026-08-25
- **Method:** executed experiments on Postgres 17, MySQL 8.4, MariaDB
  11.4, SQL Server 2022, and Oracle 23ai Free in Docker, on the real
  vfs schema in fresh namespaces. The live arm was profiled per
  statement shape with a rival topology verb measuring the lock hold;
  a set-based prototype ran the same batch in a sibling namespace with
  a parity referee diffing both end states. Scripts and every run's
  JSON under `studies/2026-08-25-set-based-topology-statements/`
  (`prototype_set_based_delete.py`, `profile_scattered_delete.py`,
  `mssql_snapshot_fetch.py`, `results/`).
- **Corpus:** N files spread ten per directory plus N/100 directory
  targets holding five children each — every file and every such
  directory is a target (10,100 targets and 500 descendants at
  N = 10,000), written in one batch. The rival is a sibling handle
  issuing one `move` 0.5 s after the delete begins; its elapsed is the
  hold measurement (spec 102 Q4's acceptance number).
- **Feeds:** spec 102 (design waits on this memo); spec 080's shape on
  the mysql family (companion memo
  `2026-08-25-mysql-family-batch-update-shapes.md`).

## Q1 — where the 4-statements-per-target go

The live arm at 10k issues **~31,800 statements** in one serialized
transaction on every engine. By share of transaction time:

| engine | bumps (2 per target) | reparent (1 per target) | other |
|---|---|---|---|
| Postgres | **64.8 %** — 20,203 stmts, 22.1 s | 30.0 % — 10,100, 10.2 s | segment deletes 3.3 %, LIKE selects 0.7 % |
| MySQL | **83.4 %** — 54.9 s | 13.4 % — 8.8 s | ≤ 2 % |
| Oracle | **50.6 %** — 17.1 s | 42.5 % — 14.4 s | ≤ 3 % |
| MSSQL | **36.7 %** — 21.5 s | 30.2 % — 17.7 s | **snapshot IN-list fetch 25.2 % — 14.8 s over 6 statements** |

So the cost is not the descendant collection or the postings — it is
the two per-target `_bump` statements (bucket and parent, each a
single-row UPDATE) and the per-target guarded reparent. On MSSQL a
third cost appears that the reshape does not touch by itself: the
10k-path snapshot fetch through `rows_by_path`'s chunked IN list.

Baseline elapsed and hold (the standalone profiler; the prototype
script's live half agrees within run noise):

| engine | 1k delete / rival blocked | 10k delete / rival blocked |
|---|---|---|
| Postgres | 5.9 s / 5.4 s | **78.2 s / 77.7 s** |
| MSSQL | 15.4 s / 14.9 s | **159.2 s / 158.7 s** |

The b16c38b figure (52.9 s / 51.9 s on Postgres) was a different corpus;
the shape of the result is the same — the rival waits for the whole
transaction.

## Q2 — set-based reparent on every declared engine

The prototype replaces the per-target quartet with, per chunk: one
guarded set-based reparent, one fused descendant select, one fused
descendant rewrite, one set-based parent bump, then the posting delta.
It takes the same serialization point (`_serialize`), mints the same
trash chain (`_TrashChain`), computes the same trash names, and stamps
the same columns (`deleted_at`, `encoded=False`, `original_*`,
`version + 1`) — the parity referee compares both namespaces' entry and
segment tables (ids resolved to paths, ULID prefixes normalized) and
reported **equal on every engine at 1k and 10k**.

Per-engine spelling, guarded on `(entry_id, version)` and proven by the
statement's own evidence:

| engine | spelling | proof | chunk at 10k (7 binds/row) |
|---|---|---|---|
| Postgres, MSSQL | VALUES join UPDATE (`values(...)` + `update().where(...)`) | RETURNING / OUTPUT set == N | 4,671 rows → 3 stmts; MSSQL 299 rows → 34 stmts |
| MySQL, MariaDB | UNION ALL derived table in a multi-table UPDATE (spec 080's shape) | FOUND_ROWS rowcount == N | 4,671 rows → 3 stmts |
| Oracle | the existing per-row guarded UPDATE as **array DML** (`session.execute(stmt, params)`) | aggregate rowcount == N | 1,000 rows → 11 stmts |

Oracle's note: a MERGE cannot update columns named in its ON clause
(ORA-38104), and both the version guard and the path rewrite update
their own join columns, so MERGE is out; but python-oracledb's
executemany is true array DML — one round trip per chunk — so the
set-based spelling on Oracle is simply the statement the arm already
has, driven as a batch. No derived table needed.

## Q3 — the fused descendant rewrite: it fuses, and the range form is the sargable one

One statement per chunk of directory targets rewrites every descendant
under every old prefix:

```sql
UPDATE entries SET path = v.new || substring(entries.path, v.len + 1, 4096)
FROM (VALUES (old, new, len), …) AS v
WHERE entries.path > v.old || '/' AND entries.path < v.old || '0'
```

(`+`/`CONCAT` per dialect; the mysql family in its multi-table form;
Oracle applies the fused select's rows by array DML instead, MERGE
being barred as above.) A matching fused SELECT returns
`(entry_id, old, new)` for the posting delta. Both bounded by the same
bind budget as the reparent.

**Sargability, measured on Postgres at the 10k corpus:** the planner
chose a sequential scan for both predicates at this table size (a
cost decision, ~11.6k rows). With `enable_seqscan = off`:

- the **half-open byte range** `path > old || '/' AND path < old || '0'`
  runs as a nested loop over the VALUES rows with an **Index Scan on
  the path index, Index Cond on both bounds** — 5 rows per prefix, 100
  loops, 312 buffers;
- the **LIKE** `path LIKE old || '/%'` cannot become an index condition
  with a non-constant pattern: Seq Scan plus Join Filter, 1,159,800
  rows removed, 256 ms.

The range form needs no LIKE escaping and relies on bytewise ordering
of `path`, which ADR 024 pins on Postgres (`COLLATE "C"`), MSSQL
(`_BIN2`), and the mysql family (`VARBINARY`) — Oracle's ordering is
the declared degradation, and Oracle applies rewrites by id anyway.
Guard discipline is unchanged: the rewrite bumps no versions and takes
no guard, exactly as `_apply_rewrites` does today, because nothing
observable on a descendant changed.

## Q4 — the lock-hold curve after

| engine | 1k live hold → prototype hold | 10k live hold → prototype hold | reduction at 10k |
|---|---|---|---|
| Postgres | 4.47 s → 0.07 s | 73.9 s → **2.00 s** | **37×** |
| MySQL | 5.27 s → 0.07 s | 125.3 s → **3.14 s** | **40×** |
| MariaDB | 4.61 s → 0.12 s | 67.5 s → **2.85 s** | **24×** |
| Oracle | 6.86 s → 0.18 s | 75.1 s → **2.85 s** | **26×** |
| MSSQL | 14.3 s → 1.58 s | 143.5 s → **18.8 s** | **7.6×** |

Statement counts fell from ~31,800 to 1,130–1,200 per 10k batch.
Postgres' prototype profile is now led by the posting delta
(`move_postings`' 1,100 per-segment deletes, 0.35 s of 2.6 s) — the
next cost if anyone wants one, not a blocker.

**MSSQL's residual is the snapshot fetch, and it is fixable:** 10.4 s
of the 19.3 s prototype run is the 10k-path `IN`-list fetch (5
statements at the ~2,100-bind budget), which the live arm pays too.
Measured head-to-head at 10,100 paths (`mssql_snapshot_fetch.py`, two
rounds each):

| engine | IN list (today) | VALUES join |
|---|---|---|
| MSSQL | 10.85 s, 8.87 s | **0.40 s, 0.22 s** |
| Postgres | **0.10 s, 0.09 s** | 0.26 s, 0.26 s |

A dialect-shaped fetch — VALUES join where the profile declares
`values_join`, IN list elsewhere — would take MSSQL's set-based hold to
roughly 9 s (~16×) and shave ~10 s off every scattered 10k verb on
MSSQL today. Postgres keeps its IN list.

## Q5 — cross-transaction chunking is not needed

Set-based execution holds the whole contract (batch atomicity, guard
discipline, restorability, attribution — parity-equal end states on
every engine) with the hold at 2–3 s on four engines and ~19 s (→ ~9 s
with the fetch fix) on MSSQL. Chunking would weaken atomicity for no
remaining need; it stays out.

## Recommendation for spec 102's design (slice B)

1. Reshape `delete_rows`' trash-everything arm to the prototype's
   per-chunk sequence: snapshot → guarded set-based reparent (proof by
   RETURNING set or aggregate rowcount, per the existing `_claim`
   evidence ladder) → fused descendant select + rewrite by the byte
   range → set-based parent bumps (`version + n` per parent, `+ N` on
   the bucket) → one posting delta. Per-target observations and error
   attribution are computed from the snapshot as today; a reparent
   miss raises `StaleSnapshot` for the whole batch exactly as the
   per-target guard does.
2. Spellings by capability: VALUES join (`values_join`), UNION ALL
   join (mysql family), array DML (Oracle) — sharing spec 080's
   derived-table helper so there is one owner for "a set of rows as a
   join source" per dialect.
3. Add the dialect-shaped snapshot fetch (VALUES join on MSSQL) to
   `rows_by_path` — a separate, smaller change that also pays off on
   every scattered verb today; measured here, not yet specced.
4. Pins: the existing trash conformance rows plus a scattered-scale
   row on the four engine legs; the parity referee's end-state diff
   is the model for that row.
5. The acceptance criterion as written ("an order of magnitude on
   Postgres and MSSQL") is met on Postgres (37×) and reachable on
   MSSQL only with item 3 (7.6× → ~16×); record that dependency in the
   spec rather than softening the criterion.
