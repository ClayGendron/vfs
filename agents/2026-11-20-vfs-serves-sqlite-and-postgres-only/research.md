# With only SQLite and Postgres left, the first Postgres gains are a bound subtree range, a pgvector floor, one array bind and dropped epoch tables

This memo answers two questions asked on 2026-11-20.

1. What does dropping MariaDB, SQL Server and Oracle touch, and where should the line between the two remaining engines run?
2. Which Postgres-native features should vfs use now, and where did a design take a worse shape to fit the dropped engines?

It was written in one sitting on 2026-11-20 at commit `c42dccd4`. Five studies ran in parallel and read the vfs source, five reference clones, the installed drivers and the Postgres, pgvector and managed-service documentation. Four experiments were then run on Postgres 17 and 18 and on SQLite. The spec that stands on this memo is `spec.md` in this directory, and `inventory.md` lists every line the drop touches. A memo decides nothing; a spec decides.

Every claim carries a label. EXECUTED means a command ran and the claim reports its output. READ means the claim was seen in a file or page that is cited. INFERRED means reasoning from the two.

## The answer in one paragraph

Dropping the three engines changes no statement on SQLite or Postgres. Both already chunk at 32,668 keys, set by SQLAlchemy's parameter budget, and never met Oracle's or SQL Server's caps. What the drop removes is about 2,500 lines of code, tests and tooling, and a habit of designing to the least generous engine.

The line between the engines should stay where it is: one storage class, a profile of facts and selectors, and the builder functions that read it. `SQLiteStorage` and `PostgresStorage` are worth adding as names, not as places for behaviour.

On Postgres, four changes stand out after the experiments:

- A subtree predicate spelled as a bound `LIKE` becomes a full table scan once Postgres switches a prepared statement to its generic plan. It happened on vfs's own `tree` statement. The range form keeps the index on every plan.
- On pgvector below 0.8, vector search returns at most 40 chunks of the 100 or more it asks for, scoped or not.
- An expanding `IN` prepares a new server statement for every list length, where one `= ANY($1)` bind keeps a single statement and still seeks its index.
- Reclaiming an index epoch by `DELETE` writes about 2,500 times the WAL of dropping a table.

The owned BM25 stays. Only one of its reasons was the dropped engines.

## Sources

VFS at `c42dccd4` on the branch `vfs-serves-sqlite-and-postgres-only`, read on 2026-11-20.

| Clone | Commit | Date | Licence | State |
|---|---|---|---|---|
| `postgres` | `207b5293` | 2026-11-20 | PostgreSQL Licence | Refreshed to `origin/master`. Tags `REL_18_0` and `REL_19_0` fetched. |
| `pgvector` | `2eb55afb` (0.8.7) | 2026-11-19 | PostgreSQL Licence | Refreshed to `origin/master`. |
| `paradedb` | `05e9bb3c` | 2026-11-20 | AGPL-3.0, studied only | Refreshed to `origin/main`. |
| `sqlite` | `3d17c3f9` | 2026-08-04 | Public domain | Refreshed to `origin/master`. |
| `sqlite-vec` | `04d28bd2` (0.1.10-alpha.4) | 2026-05-17 | MIT and Apache-2.0 | Refreshed to `origin/main`. |
| `django` | `c67d8727` | 2026-11-19 | BSD-3 | Refreshed to `origin/main`. |
| `sqlalchemy` | `4917592d` | 2026-11-19 | MIT | Refreshed to `origin/main`. The installed 2.0.52 is what runs. |

Every clone was clean before its refresh. Installed packages: SQLAlchemy 2.0.52, asyncpg 0.31.0, aiosqlite 0.22.1 and SQLite 3.50.4, on Python 3.13.11. The experiment servers were PostgreSQL 17.11 with pgvector 0.8.6, PostgreSQL 18.7 with 0.8.7, and PostgreSQL 17.0 with 0.7.4, each from the `pgvector/pgvector` images, on tmpfs and at default settings. Web pages, read on 2026-11-20:

- <https://www.postgresql.org/support/versioning/>
- the 17 and 18 release notes
- the AWS RDS release calendar
- the Cloud SQL versions page
- the Azure Database for PostgreSQL announcement of 18

No code was copied from any clone or package. The experiment scripts were kept in the session's scratch directory, outside the repository, and are not durable. Section 4 describes each experiment closely enough to be written again.

## 1. What the drop touches

`inventory.md` has every item with file, lines and action. Its findings that bear on design:

- **No chunk size changes.** EXECUTED. On SQLite and Postgres, `membership_budget` is `min(in_list_budget, parameter_budget - 32)`. The parameter budget is SQLAlchemy's `insertmanyvalues_max_parameters`, 32,700 on both, so the chunk is 32,668 on both. Neither engine's own `in_list_budget` binds, at 32,766 and 65,535. asyncpg refuses more than 32,767 arguments (READ, `asyncpg/protocol/prepared_stmt.pyx:130-132`), so Postgres's declared 65,535 could never have been reached.
- **The generic floor's two numbers come from dropped engines.** READ, `dialects.py:659-667`. Its 1,700 key bytes are SQL Server's and Oracle's, and its 1,000 `IN` elements are Oracle's ORA-01795.
- **Four shared values were set across five engines and reach both kept engines.** READ. They are `RELABEL_ROWS` at 50,000, `BLOB_PAGE_BYTES` at 8 MiB, `_STATEMENT_BIND_RESERVE` at 8 and `_PATTERN_ARM_CEILING` at 200. Changing any of them changes statements, so the spec keeps them and rewrites only their reasons.
- **Ten profile fields serve only a dropped engine, and two are read by nothing.** READ, and a grep of readers was EXECUTED. The two are `vector_dimension_cap` and `ann_dimension_cap`.
- **A dropped engine's URL falls to the floor.** INFERRED, from compiling the plain types on each dialect. Without its type variants it probably fails at provisioning: Oracle has no `BINARY`, and the MySQL family caps `TEXT` and `BLOB` at 64 KB and keys at 3,072 bytes. A MySQL community URL, already served by the floor, gets the MySQL-family variants today and loses them.
- **The floor has no end-to-end test.** READ. Its arms are proven field by field over SQLite: 34 `replace(profile, field=...)` overrides and 19 monkeypatches, which bypass `EngineHost._policy()`.
- **Scale of the removal.** EXECUTED, counts:
  - about 750 to 900 lines of `src/`
  - about 1,000 to 1,300 of `tests/`, of which 339 sit under the three engines' markers
  - about 420 of packaging and tooling, including six locked packages
  - about 120 of the `db_test` skill
  - about 25 sentences of prose

## 2. Where the line between the two engines runs

The question: once two engines and a floor remain, should the engines be classes, strategy objects, or one class with a profile?

**What the code is.** EXECUTED, greps; READ.
- The profile is passed as a value into 188 parameters across 31 modules, and `membership(...)` alone is called 107 times. `DatabaseStorage` reads the profile itself in 6 places. Every other read is inside a free builder function that never sees the storage.
- There are 38 profile fields besides `name`: 23 are facts, such as a budget or a setting, and 15 select an arm. After the drop, 24 remain: 14 facts and 10 selectors.
- Of the 10 selectors, only 6 differ between SQLite and Postgres: `share_lock`'s door, `values_join`, `content_bytes`, `bulk_insert`, `vector_distance` and `range_source`. The other 4 (`arbitration`, `guard_miss`, `tuple_in`, `scope_facts_beside_fan`) exist to give the floor its arm.
- There are 9 branches on an engine's name in the storage layer, and 8 survive. About 30 more sit in `models/` and use SQLAlchemy's own per-dialect type and DDL seams, which is the right home for them.
- About 450 of `engine.py`'s 1,140 lines serve SQLite only: planner statistics, transaction control, sqlite-vec loading and the serialized in-memory pool.

**Prior art.** READ.
- Django splits a backend into `DatabaseFeatures`, about 160 facts; `DatabaseOperations`, 83 hook methods; and a wrapper subclass per engine. Its Postgres bulk insert is an `UNNEST` override in `postgresql/compiler.py:18-61` that falls back to the generic form.
- SQLAlchemy has a `Dialect` subclass per engine, with about 78 capability flags and a compiler subclass. An unknown URL raises `NoSuchModuleError`, so there is no generic floor at run time.
- Both use a class per engine because third parties add engines. vfs's set is closed.

**The options.**

| Option | What it costs | Verdict |
|---|---|---|
| One class plus a profile, pruned | The deletions only. No home for engine-only construction arguments. | The core of the recommendation. |
| Public subclasses that hold behaviour | An override reaches only the storage's 6 reads. The builders still need the profile. Each floor arm, today proven by changing one field, could then be proven only by changing the class. | No. |
| A strategy object for behaviour, a profile for facts | About 25 methods from the start, 188 parameters and 437 test references rewritten, and the per-field floor proofs lost. | No, unless one verb's whole pipeline comes to differ by engine. |
| One class and a profile, with `SQLiteStorage` and `PostgresStorage` as subclasses that only construct, as `InMemoryStorage` is | Two classes of about 50 lines, and a mismatch check at first touch. | **Recommended.** |

INFERRED: a Postgres fast path then needs one more selector value and one arm in the function that owns the statement, with the generic arm kept as the fallback. Binary COPY (`bulk_insert="copy"`) and the pgvector ANN tier are already built this way. A later tidying would turn the 8 checks of an engine's name into declared facts, and move SQLite's 450 lines into a module of their own. It changes no behaviour.

**Names.** READ, `documentation/maintainers/how-we-name.md`, the README, `AGENTS.md`, the extra `vfs-py[postgres]` and the test markers. The project's noun is "Postgres". PEP 8 capitalises an acronym in a class name, as in `ULIDKey`. So the names are `PostgresStorage` and `SQLiteStorage`.

## 3. What vfs already does natively on Postgres

READ. Each candidate below was checked against this list before being called new.

- `INSERT … ON CONFLICT … RETURNING` for create arbitration. `writes.py:595-660`.
- `UPDATE … FROM (VALUES …) RETURNING` for guarded updates, bumps, claims and edge touches. `writes.py:913-981`, `edges.py:492-550`.
- Binary COPY through asyncpg's `copy_records_to_table` for every bulk insert that needs nothing back. `dialects.py:892-943`, 22 call sites.
- `unnest` of bound arrays for the rights ranges and the relabel. `ranges.py:328-352`, `labels.py:633-636`.
- `pg_advisory_xact_lock` for first-touch provisioning. `engine.py:736-741`.
- `REPEATABLE READ` for operations and `READ COMMITTED` for topology. `dialects.py:691-719`.
- `COLLATE "C"` on every path key, a partial unique index on `vfs_edges`, and `STORAGE EXTERNAL` on blobs. `rows.py:191-236`, `636-646`, `915-924`.
- An HNSW index on `vfs_chunks.embedding`, and `SET LOCAL hnsw.iterative_scan = relaxed_order` on pgvector 0.8 and later. `rows.py:932-950`, `backend.py:649-653`.
- `SET LOCAL jit = off` before a partial caller's read. `rights.py:579-582`.

## 4. Four experiments

### X1. Does HNSW serve vfs's real vector statement, and what recall does a scoped caller get?

**Method.** EXECUTED.
- vfs's own `search` ran on Postgres through its public API, and a `before_cursor_execute` listener recorded what it sent: `SET LOCAL hnsw.iterative_scan = relaxed_order`, then `SELECT … ORDER BY vfs_chunks.embedding <=> $1, vfs_chunks.id LIMIT $4`, with `$4 = 100`.
- The depth is `max(10 · limit, 100)` (`search.py:377`). A scope that resolves to at most 5,000 entries becomes `vfs_entries.id IN (...)` in the statement. A wider scope runs unfiltered and is gated in Python.
- Data: vfs's own schema, with 20,000 files of 5 chunks each, 100,000 chunks at 128 dimensions in 100 clusters, and the HNSW index at m 16 and ef_construction 64.
- Queries: 50 of them, unscoped and at scopes of 1% and 10%, at `hnsw.ef_search` 40, 100 and 400 crossed with the iterative scan off, `relaxed_order` and `strict_order`.
- Exact answer: the same statement with index scans off. Recall@10 and recall@100 were measured against it.

**Results.** EXECUTED.
- **The `chunks.id` tie-break does not keep the index out.** On 17.11 with 0.8.6, on 18.7 with 0.8.7 and on 17.0 with 0.7.4, generic plans included, the plan is an Incremental Sort over the HNSW Index Scan. Recall was identical with and without the tie-break, to four decimals. A claim from reading, that the tie-break defeats the index, is refuted.
- **pgvector filters above the index scan, not inside it.** The rows are filtered at the join to `vfs_entries`. The iterative scan fills the window by pulling more tuples. At a 10% scope it read 1,114 index tuples for 100 rows. The profile's docstring, "pgvector filters inside the index scan", is loose.
- **Without the iterative scan, search starves.**

| Case (PG 17.11, pgvector 0.8.6) | Rows of 100 | recall@10 | recall@100 |
|---|---|---|---|
| Unscoped, ef 40, iterative off | 40 | 0.954 | 0.400 |
| Unscoped, vfs's prelude (`relaxed_order`) | 100 | 0.976 | 0.964 |
| 10% scope, ef 40, iterative off | 3.9 (min 0) | 0.394 | 0.039 |
| 10% scope, ef 400, iterative off | 39.6 | 0.976 | 0.396 |
| 10% scope, vfs's prelude | 100 | 0.976 | 0.950 |
| 1% scope, any setting (the planner chose the exact btree path) | 100 | 1.000 | 1.000 |

pgvector 0.7.4 has no iterative scan. It behaved as "iterative off" at every `ef_search`. vfs serves `native_ann` there with no prelude (`backend.py:651`), so on 0.7 every vector search returns at most 40 chunks.

INFERRED, not measured: `hnsw.max_scan_tuples`, 20,000 by default, caps the iterative scan. A scope narrow enough to need more, if the planner still chose HNSW, would come back short again.

### X2. Does a bound `LIKE` lose its index under a generic plan?

**Method.** EXECUTED, on 17.11 and 18.7.
- 1,000,000 paths in a `varchar(1024) COLLATE "C"` column with a unique btree.
- Four statements were prepared: `path LIKE $1 ESCAPE '\'`; the range `path > $1 AND path < $2`; the keyset page of `rights.py:_refused_beneath`, as `LIKE $1 AND path > $2 ORDER BY path LIMIT 100`; and its range twin.
- Each ran under `force_custom_plan` and `force_generic_plan`.

| Statement | Plan | Rows removed by the filter | Buffers |
|---|---|---|---|
| `LIKE $1`, a 100-row subtree, custom | Index Scan over the prefix range | 0 | 103 |
| `LIKE $1`, the same, generic | Parallel Seq Scan | 999,900 | 7,353 |
| Range, the same, generic | Bitmap Index Scan | 0 | 103 |
| Keyset `LIKE`, last page, generic | Index walk from `last` to the end of the table | 906,200 | 910,459 |
| Keyset range, generic | Index Scan, bounded | 0 | 56 |

**Does vfs reach a generic plan?** READ and EXECUTED.
- SQLAlchemy's asyncpg dialect keeps a 100-entry LRU of prepared statements per connection (`sqlalchemy/dialects/postgresql/asyncpg.py:720-790`), and asyncpg makes each one a named server statement. vfs sets no cache size.
- On one connection, vfs's own `tree` statement, `WHERE vfs_entries.path LIKE $1::VARCHAR ESCAPE '\' …`, was one server statement reused 12 times.
- In `auto` mode Postgres keeps custom plans while they are cheap. After five executions on a large subtree, the sixth call, on a 200-row subtree, ran the generic Seq Scan, and every later call on that connection stayed generic.
- An operator who sets `plan_cache_mode = force_generic_plan`, as some poolers advise, makes it happen at once.

**The cost at the reference deployment.** INFERRED. A generic-plan full scan of `vfs_entries` is 10,000,000 row visits. A keyset page that walks to the end of the table costs about 17,000 times the buffers of its custom plan.

The `LIKE` is used by:
- the move's descendant collection, `topology.py:356-381`
- the delete's tombstoning, `trash.py:472-499`
- `_deeper_postures`, `labels.py:599-610`
- the meta exclusion of every enumeration, `descent.py:220-231`
- `tree`

A connection flips once, and then it stays flipped. So the cost lands per verb call, on reads that the working agreement says must cost in proportion to what they return.

### X3. What does reclaiming an index epoch cost?

**Method.** EXECUTED, on 17.11.
- A table shaped like `vfs_lex_docs`, `(epoch, chunk_id, entry_id, dl)`, with its two indexes, holding 1,000,000 rows in each of two epochs.
- A checkpoint before each step, so that full-page images are counted.
- WAL measured from `pg_current_wal_lsn()`, locks from `pg_locks`.
- A second connection with `lock_timeout = 1s` probed whether a reader was blocked.

| Form | WAL | Dead tuples | Size after | Readers blocked |
|---|---|---|---|---|
| `DELETE … WHERE epoch < 2`, as `indexing.py:611-626` does | 124.7 MB, then 60.9 MB for the `VACUUM` | 1,000,000 | 305.6 MB, unchanged | none |
| `DROP TABLE` of a table per epoch | 49 KB | 0 | 131 MB freed | only readers of the dropped table |
| `DETACH PARTITION … CONCURRENTLY`, then `DROP` | 135 KB | 0 | 152.8 MB freed | none. It waits for old snapshots and holds no lock on the parent while it waits |
| A plain `DETACH`, or a `DROP` of an attached partition | small | 0 | — | every reader of the parent: `ACCESS EXCLUSIVE` on it |

INFERRED: at about 186 bytes of WAL a row, a daily `DELETE` reclaim of 100,000,000 `lex_docs` rows writes 10 to 20 GB of WAL before the postings are counted. The long transaction also holds back vacuum on every table. The constant-cost forms do neither. Only the per-epoch table and `DETACH … CONCURRENTLY` meet the lock rules.

### X4. Do array binds stop statement churn, and does SQLite's counterpart keep its index?

**Method.** EXECUTED.
- Postgres, through SQLAlchemy and asyncpg on one pooled connection: a lookup in a 100,000-row table at key-list lengths of 1 to 50 and 5,000, each run twice. It ran once as an expanding `IN` and once as `k = ANY(:ks)`.
- Counted: asyncpg prepare calls, server prepared statements, SQLAlchemy's prepared LRU and its compiled cache.

| Form | Prepares | Server statements | Compiled-cache entries added |
|---|---|---|---|
| Expanding `IN` | 52 | 52 | 1 |
| `= ANY($1::VARCHAR[])` | 2 | 1, plus driver introspection | 1 |

- **Past the LRU.** At 400 distinct lengths run twice, the expanding `IN` took 804 prepares for 800 executions, so there was no reuse. About 146 statements stayed open, with about 20 MB in the backend's plan-cache memory.
- **The compiled cache.** The claim that the expanding `IN` churns SQLAlchemy's compiled cache is refuted. It compiles once and renders per execution.
- **The generic plan of `= ANY`.** Under `force_generic_plan` it is still an Index Scan with `k = ANY($1)`, at 3 keys (10 buffers) and at 5,000 (2,843). So it does not have X2's problem.
- **SQLite.** On 3.50.4, `path IN (SELECT value FROM json_each(?))` with 5,000 keys plans as `SEARCH … USING COVERING INDEX` with a Bloom filter, in about 55,000 VM steps. A 5,000-bind literal list took about 50,000, and a full scan about 402,000. Integer and rowid keys behave the same.

## 5. Postgres-native candidates, ranked

"Take now" means a spec is worth writing next. "Later" means the gain is real and waits on a measurement or a lower priority. Each keeps verb results identical on SQLite unless it says otherwise.

### 1. Subtree predicates as a bytewise range, not a bound `LIKE`: take now, small

- **Today.** `descendant_filter` spells `path LIKE :root || '/%' ESCAPE '\'` (READ, `descent.py:193-207`). `ranges.py:384-389` already uses the range form `path > root || '/' AND path < root || '0'` for scopes (READ).
- **Postgres.** Postgres derives an index condition from `LIKE` only when the pattern is a constant (READ, `../postgres/src/backend/utils/adt/like_support.c:265-275`). X2 shows the full scan on vfs's own statement. The range is exact under `COLLATE "C"`, because `'/'` (0x2F) sorts just before `'0'` (0x30).
- **SQLite.** `BINARY` collation is bytewise, so the same range is exact and seeks the index. It also removes vfs's reliance on `PRAGMA case_sensitive_like` (READ, `dialects.py:488`), which SQLite documents as deprecated. Parity holds: the same rows match.
- **The floor** keeps `LIKE`, since an unknown engine's key order is not known to be bytewise. That takes one profile fact, such as "bytewise key order", true on both tuned engines.
- **Cost.** Per verb call: from up to 10,000,000 row visits on a flipped connection down to the subtree's own size.

### 2. Require pgvector 0.8 for the ANN tier, and pin the plan and recall: take now, small

- **Today.** `native_ann` is served on any pgvector version, and the iterative-scan prelude is set only on 0.8 and later (READ, `backend.py:647-653`). The `LIMIT` is at least 100 and `ef_search` is never set.
- **The defect.** On 0.7, search returns at most 40 chunks: recall@100 is 0.40 unscoped and 0.039 at a 10% scope (X1).
- **The change.** Below 0.8, either serve the exact tier, or set `hnsw.ef_search` to at least the depth for the transaction. The simpler rule is a floor of pgvector 0.8 for `native_ann`.
  - On the Postgres leg, a test checks the plan: the leg's statement shows an Index Scan on `ix_vfs_chunks_embedding` whenever the tier says `native_ann`.
  - A second test checks recall at fixed seeds, scoped and unscoped, against the Rust `cosine_topk` referee.
- **Also.** `index_method="ivfflat"` creates its index on an empty table at the `after_create` event and never raises `ivfflat.probes` (READ, `models/vector.py:97`, `models/rows.py:945-950`; pgvector `README.md:378-395`, `945-951`). INFERRED: its recall is near useless. Remove the option, or build the index only after data exists.
- **SQLite.** Unchanged: exact through sqlite-vec.
- **Cost.** Per verb call, at the reference deployment: 100,000,000 chunks at 1,536 dimensions hold 614 GB of float32 vectors, so an exact scan per search is not affordable. INFERRED: ANN is a requirement at that scale, and its index must be shown to work.
- **Later.** A cardinality gate that runs an exact search over the admitted rows for narrow scopes. It covers the `max_scan_tuples` ceiling and the planner's lack of a selectivity term in `hnswcostestimate` (READ, pgvector `src/hnsw.c:144-235`). It needs a measured threshold, and the 2026-09-30 filtered-vector memo in `context/research/` holds the prior work.

### 3. Membership as one array bind: take now, medium

- **Today.** Every key list is an expanding `IN`, built in one owner, `membership()` (READ, `membership.py:63-68`). Some lists are corpus-sized: `_visible_chunks` over every chunk a query term names (READ, `lexical.py:628-647`), at about 300 statements for 10,000,000 ids.
- **Postgres.** `col = ANY($1::type[])` keeps one statement text for every length, and its generic plan seeks the index (X4). vfs already binds arrays this way for rights ranges.
- **SQLite.** `IN (SELECT value FROM json_each(?))`, which keeps its index (X4). vfs already uses `json_each` for ranges.
- **Cost.**
  - Per verb call: one prepared statement per call site instead of one per list length. That avoids the churn X4 measured, 804 prepares in 800 executions once lengths vary.
  - Per batch: a 10,000-key snapshot is one statement either way, at the 32,668 chunk.
  - A corpus-sized list becomes one statement instead of hundreds. The work inside the statement does not shrink.
- **Still to do.** Keep a declared element budget as a bound on memory and on how long locks are held, so that no statement grows without limit. Check each converted call site's plan. A generic plan estimates an array at 10 elements (X4).
- **Next.** The multi-row `VALUES` writes (the entry upsert at 28 binds a row, the material update at 24) can take `INSERT … SELECT FROM unnest(...)` and `UPDATE … FROM unnest(...)` on Postgres. A 10,000-entry layer goes from about 9 statements of about 32,600 binds to 1 (INFERRED, arithmetic). That half needs its own count of statements and prepares before it is chosen.

### 4. Drop an old index epoch as a table, not by deleting its rows: take now, spec first, large

- **Today.** `reclaim_epochs` deletes every old-epoch row of every epoch-scoped table in one transaction (READ, `indexing.py:611-626`). The tables are the gram postings, `lex_docs`, `lex_postings`, `lex_df`, `lex_stats` and the fingerprints.
- **Postgres.** A table per epoch, dropped once the live pointer has moved past it, or a list partition per epoch reclaimed by `DETACH … CONCURRENTLY` and `DROP` (X3). A build into a table created in the same transaction can also use `COPY … FREEZE`, which writes pages already frozen, so no later vacuum pass revisits them (INFERRED; whether asyncpg's `copy_records_to_table` can pass `FREEZE` is not verified).
- **SQLite.** A table per epoch, and `DROP TABLE`. The 2026-10-31 memo measured repeated rebuilds on SQLite slowing the lexical build from 3.6 s to 30.2 s over seven epochs (READ), so SQLite gains too.
- **Cost.** Per corpus, once a day: about 200,000,000 deleted rows a day, with their WAL and vacuum, become a few hundred kilobytes. Per lock: no reader of the live epoch waits.
- **Risk.** DDL moves into the rebuild's lifecycle, and each read resolves its table names from the live epoch. Medium to large. It needs its own spec and a test that a reader of the live epoch never waits on a reclaim.

### 5. No savepoint per row on a conflicted chunk: take later, small, after a count

- **Today.** A conflicted chunk is re-run one row at a time, each row in its own savepoint (READ, `writes.py:709-780`, `edges.py:463-489`). That can be up to 1,167 savepoints, a chunk of the 28-column upsert.
- **Postgres.** Each backend caches 64 subtransaction ids (READ, `../postgres/src/include/storage/proc.h:44`). Past that, while the transaction stays open, other sessions' visibility checks read `pg_subtrans` (INFERRED from the source).
- **The change.** Edges can arbitrate with `ON CONFLICT (source_id, target_id, edge_type) DO NOTHING RETURNING`, and directories with an untargeted `DO NOTHING`. Both engines have both forms (READ, the Postgres and SQLite upsert pages).
- **Not run.** The count of savepoints and the `pg_stat_slru` subtransaction reads were not measured. That is the experiment to run first.

### 6. A Postgres floor of 17, enforced at first touch: take with candidate 2, a declaration

- **Today.** vfs states no minimum and runs only 17 (READ, `docker/compose.test.yml:31`). The newest feature it needs is in Postgres 12 or earlier (INFERRED).
- **Community support** (READ, the versioning page): 17 ends 2029-11-08, 18 ends 2030-11-14, and 14 ended 2026-11-12.
- **Managed services** (READ): RDS offers 14 to 18, Cloud SQL defaults to 18.6, and Azure has had 18 generally available since November 2025. 19 was released on 2026-11-19 and is not yet on RDS or Cloud SQL.
- **Why 17.**
  - It is the version tested.
  - 17 made btree lookups of a set of values cheaper (READ, the 17 release notes), which `= ANY` relies on.
  - 17 made the subtransaction cache sizes configurable.
- **Later floors.** 18 adds `RETURNING old.*`, and 19 adds `ON CONFLICT DO SELECT`. Each would simplify a step, and each is a reason to revisit the floor, not to move it now.

### Later

| Candidate | Gain | What it waits on |
|---|---|---|
| `fillfactor` 90 on `vfs_entries`, so that a parent's version bump is a HOT update | A bump writes no entries to the 15 indexes. Up to about 15,700,000 index inserts a day, per file write (INFERRED) | A count of the HOT ratio, the index growth and the WAL at fillfactor 100, 90 and 80 |
| Server-side `INSERT … SELECT` for the version mint and for `copy` | 3 to 7 GB of bodies stop crossing the wire per 10,000-file overwrite at the mean size (INFERRED) | A proof that the entry's stamped metrics equal the body's. The mint now measures the body on purpose (READ, `versions.py:15-27`) |
| `jit = off` once per connection through asyncpg's `server_settings` | One round trip per partial caller's read | Nothing. A borrowed engine keeps the `SET LOCAL` |
| `pg_trgm` GIN on `name` and `path` for infix globs | An infix glob stops scanning `vfs_entries`. Results cannot change, since the glob stays the authority | A count of plans and of the write cost on a move. The extension is trusted, so it needs no superuser |
| `halfvec` or binary-quantised HNSW, re-ranked in float32 | Indexes past 2,000 dimensions. Index memory falls from 614 GB to about 19 GB plus the graph, at the reference corpus | A recall measurement |
| A partial index on rows waiting for the index, on both engines | Replaces SQLite's `unlikely()` hint, and about 11,000,000 always-indexed rows leave the index | A plan pin |
| `lz4` compression of text bodies | Faster decompression on about 11,000,000 body reads a day, per index visit | A count of stored bytes |
| A covering index for the visible corpus count | The count becomes index-only | The engine-neutral fix below |
| Re-measure `RELABEL_ROWS` on Postgres alone | It was set with SQL Server as the slowest engine | A count of rows, WAL and waiting mints per chunk |

### Not taken

| Candidate | Reason |
|---|---|
| `tsvector` and GIN, in place of the owned BM25 | `ts_rank` uses no corpus statistics (READ, `textsearch.sgml:1205`). The tokenizer is not vfs's code-aware one, and SQLite's ranking would differ. Of the owned BM25's reasons (ADR 051, 055), only parity across five engines left with them. |
| ParadeDB `pg_search` | AGPL-3.0. Its IDF is computed over the whole index, so a caller who sees part of the corpus cannot be scored on what they can see (READ, `docs/reference/full-text/score.mdx:462`). Not on the common managed services (INFERRED). |
| `pg_trgm` for grep over content | It drops non-alphanumeric characters (READ, `pgtrgm.sgml:37-40`), so code patterns like `->` and `::` give no trigram. A 4 KB body adds about 2,000 GIN entries per write. |
| `MERGE` | It does not arbitrate concurrent inserts (READ, `mvcc.sgml:416-420`). `ON CONFLICT` does. |
| `SERIALIZABLE` | It adds predicate locks to every read, and reads that can abort, and removes none of the floor's machinery. |
| Row-level security | A second source of truth for rights, on Postgres only. |
| `LISTEN`/`NOTIFY` | Delivered after commit, so it cannot replace the stamp read in the verb's own snapshot. It also fails under transaction pooling. |
| `ltree`, range types, exclusion constraints | `ltree` labels cannot hold arbitrary names, and nested prefixes overlap lawfully. |
| Partitioning `vfs_entries` | The global unique keys on `path` and on `(parent_id, name)` would need the partition key. |
| `UNLOGGED` index tables | A crash truncates them under rows marked encoded, and a standby cannot read them. |
| IVFFlat | Worse recall for its speed than HNSW, and created on an empty table today. |
| Materialized views for directory aggregates | A refresh recomputes 10,000,000 rows. The reference deployment's shape is a table maintained with the write. |
| Statement-level triggers for aggregates | SQLite has only row triggers. The deltas can ride the existing bump statement. |
| Server-side cursors in place of keyset pages | Keyset pages are bounded already, and a cursor fetched in batches turns off parallel query. |

## 6. Shapes that bent for the dropped engines

READ. These run today on SQLite and Postgres. Each was written so that one statement served five engines. The spec keeps each of them in landing 1, so that no statement changes. Each is a small later change.

- The subtree `LIKE`, chosen because it does not depend on collation. It is candidate 1.
- The multi-row `VALUES` membership form and its collation casts, for SQL Server. Deleted in the spec.
- The OR form of the lexical leg's second round, for SQL Server's lack of row-value `IN`. Both kept engines set `tuple_in`, so it now serves only the floor, which withholds `search`.
- Three membership lists and a client-side filter stand in for a tuple `IN` on edge triples (`edges.py:425-460`). Both engines can probe exact triples.
- Two single-list deletes avoided in `trash.py:607-610`, because they "would carry the chunk's binds twice, doubling past the tightest engine cap". With an array bind it is one statement.
- `CASE` in place of a boolean in a value position (`trash.py:502-508`, `indexing.py:524-529`), and a row probe in place of `SELECT EXISTS` (`indexing.py:944-957`).
- Keyset pages in place of a cursor, partly for SQL Server over ODBC (`pages.py:6-8`). The other reason, writes between pages, stands.
- A planner hint (`rarity_hint`) where a partial index would do. Both kept engines have partial indexes.
- The per-principal `UPDATE`, then `INSERT` when no row exists, in `revision.py`, `labels.py` and `rights.py`. Both engines have `ON CONFLICT DO UPDATE`. The volume is a few admin writes a day, so this is tidying.
- The root's `name="/"`, because Oracle folds `''` to `NULL`, and the column name `version_number`, because `NUMBER` is reserved in Oracle. Both are schema, so they stay.

## 7. Found on the way

These do not depend on the dropped engines, and none is acted on here.

- **The topology lock is held for a batch's body.** READ. `serialize()` takes the lock row `FOR UPDATE` as a serialized verb's first statement and holds it to commit (`serialized.py:112-123`). A 10,000-target delete therefore stalls every other delete, restore, sweep, move and copy on the mount for the length of the batch. Writes, reads and rights compiles do not wait. The working agreement's second lock rule says a lock other callers need is never held for a batch's body. The same holds on SQLite.
- **A relabel rewrites rows whose level is already right.** READ, `labels.py:476-488`. It has no `everyone_level <> :rank` term, and on Postgres an unchanged `UPDATE` still writes a new row version. The term is portable and changes no behaviour.
- **Under a partial view, search counts every visible chunk on every call.** READ, `lexical.py:563-603`. At the reference deployment, a caller who sees half the corpus visits about 50,000,000 rows a search (INFERRED). That is the read side's largest per-call cost. The fix, chunk ids numbered in path order and counted by id range, is engine-neutral.
- **`bulk_insert` resolves the profile a second time.** READ, `dialects.py:914`. It does not take the host's.
- **The profile's docstring on ANN is loose.** EXECUTED, X1. pgvector filters above the index scan, not inside it.

## 8. Not checked

- Provisioning on a dropped engine once its variants leave, and a MySQL community server on the floor. Inferred only.
- Candidate 3's multi-row half, the statement and prepare counts for `unnest` writes.
- Candidate 5's savepoint count and its subtransaction reads.
- The HOT ratio of parent bumps, `lz4` and the quantised indexes.
- The recall of the iterative scan at scopes narrow enough to meet `max_scan_tuples`. At 1% the planner left HNSW, and no narrower scope was run.
- Whether `COPY … FREEZE` passes through asyncpg's `copy_records_to_table`.
- Recall on real embeddings. X1 used synthetic clusters at 128 dimensions.

## One line

Dropping the three engines changes no statement on SQLite or Postgres. The right line between the engines is one class with a profile, with two named constructors. The first Postgres work is four changes: a bound subtree range in place of a bound `LIKE`, which full-scans under a generic plan; pgvector 0.8 for the ANN tier, without which search returns 40 chunks; one array bind per key list; and old index epochs dropped as tables.
