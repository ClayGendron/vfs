# Audit — storage backends and SQL dialects (v0.1.0 roadmap input)

Audited 2026-10-28 against HEAD `90f5883` (2026-10-27). Read-only. Every claim is labelled READ (I read the file), EXECUTED (I ran it), or INFERRED (my conclusion from what I read).

---

## 1. Built today

### 1.1 One backend, five tuned profiles, one floor

- One storage implementation: `DatabaseStorage` (`src/vfs/storage/backends/database/backend.py`). `InMemoryStorage` is a construction-only subclass over `sqlite+aiosqlite:///:memory:` with a `StaticPool` and a host lock that serializes sessions (`src/vfs/storage/backends/memory.py:34-58`; `engine.py:684-741` `_SerializedSessions`, `_rearm_on_fresh_connection`). READ.
- Dialect policy is one frozen dataclass `DialectProfile` (`dialects.py:139-376`) with five tuned instances and one floor: `SQLITE` (`:379-423`), `POSTGRESQL` (`:425-456`), `MSSQL` (`:458-485`), `MARIADB` (`:491-524`), `ORACLE` (`:531-552`), `GENERIC` (`:556-561`). `profile_for()` returns the floor renamed to the live dialect's name for anything else (`:572-582`). READ.
- Facts SQLAlchemy models are read off the live dialect, not redeclared: parameter budget = `dialect.insertmanyvalues_max_parameters` (`engine.py:224-227`), disconnect = `dialect.is_disconnect()` (`engine.py:330-343`). READ.

Per-profile declarations (READ, `dialects.py` lines cited above):

| Field | SQLite | Postgres | SQL Server | MariaDB | Oracle | GENERIC |
|---|---|---|---|---|---|---|
| `arbitration` | upsert | upsert | catch_retry | catch_retry | catch_retry | catch_retry |
| `guard_miss` | reprobe | reprobe | reprobe | **redrive** | reprobe | redrive (default) |
| `key_byte_budget` | 4,096 | 2,704 | 1,700 | 3,072 | 1,700 | 1,700 |
| `in_list_budget` | 32,766 | 65,535 | **2,000** (lock budget: 2 key locks/row under the 5,000 escalation trigger) | 65,535 | **1,000** (ORA-01795) | 1,000 |
| `op_isolation` / `topology_isolation` | — / — | REPEATABLE READ / READ COMMITTED | — / — | REPEATABLE READ / READ COMMITTED | — / — | — / — |
| `membership` form | in_list | in_list | **values** (VALUES derived table, ADR 061) | in_list | in_list | in_list |
| `row_lock_hint` | — (writer txn is the lock) | FOR UPDATE | `UPDLOCK, FORCESEEK` | FOR UPDATE | FOR UPDATE | FOR UPDATE |
| `values_join` (set-based guarded UPDATE…RETURNING) | no | yes | yes | no | no | no |
| `tuple_in` | yes | yes | no | yes | yes | no |
| `like_bracket_class` | — | — | yes | — | — | — |
| `content_bytes` (grep fetches bytes) | yes | — | — | — | — | — |
| `bulk_insert` | driver (sqlite3.executemany) | **copy** (asyncpg binary COPY) | core | driver (aiomysql multirow) | core (array DML; bare driver loses setinputsizes → 179 leg failures) | core |
| `vector_distance` | exact (sqlite-vec) | ann (pgvector) | exact (2025 `VECTOR_DISTANCE`, DiskANN makes table read-only) | ann (`VEC_DISTANCE_COSINE`, MHNSW) | ann (`VECTOR_DISTANCE`) | **none** |
| `vector_dimension_cap` / `ann_dimension_cap` | — | 16,000 / 2,000 | 1,998 | 16,383 | 65,535 | — |
| `ann_honours_scope` | — | yes | — | no | no | — |
| `range_source` (rights as sorted path ranges, ADR 072) | json_each + CROSS JOIN + MATERIALIZED fence | unnest + `SET LOCAL jit = off` | OPENJSON + INNER LOOP JOIN | JSON_TABLE + STRAIGHT_JOIN + FORCE INDEX | JSON_TABLE over CLOB + 4 optimizer hints | **None → literal OR fan** |
| retry classification | sqlite code 5 (BUSY); 517 deliberately not | SQLSTATE 40001/40P01 | 40001/40P01 | errno 1213, 1205, 1020 | ORA-00060, ORA-08177 | 40001/40P01 |
| `value_cap_query` | — | — | — | `@@max_allowed_packet` (read at first touch; refused pre-send) | — | — |
| `vector_function` (probe / install) | `SELECT vec_version()` / none | pgvector catalog row / `CREATE EXTENSION IF NOT EXISTS vector` | none (built in) | none | none | none |
| `relabel_rows` | 50,000 on every profile (measured safe everywhere) ||||||

- The MSSQL engine gets `use_setinputsizes=False` so non-Latin1 text survives (`engine.py:583-603`); its string columns use `Latin1_General_100_BIN2_UTF8` (SQL Server 2019+ floor; `rows.py:176-190`). READ.
- SQLite: `BEGIN IMMEDIATE` for writers via a `begin` listener, session PRAGMAs stamped at every pool checkout, sqlite-vec loaded into every connection (`engine.py:606-642`, `:667-681`). File settings `page_size=16384` then WAL run once at first touch (`dialects.py:405-409`). READ; pinned EXECUTED by `test_engine.py` (146 tests passed across `test_dialects.py`, `test_engine.py`, `test_sqlite_vec.py`, `test_membership.py`, 26 s, `-n 0`).

### 1.2 Capabilities and traits per engine

- `capabilities()` = all protocol ops minus `glean` when `vector_distance == "none"` (`backend.py:276-286`). `graph` is served on every dialect (ADR 079 frontier walk; `graph.py`). `traits()` declares `arbitration` from the profile and `durability = "full"` only for names in `PROFILES` (`backend.py:288-301`). READ.
- So today: SQLite, Postgres, SQL Server, MariaDB, Oracle → every op in `Op` (`ops.py:36-62`). Unknown dialect (incl. `mysql://`) → every op except `glean`, no `durability` trait. Pinned EXECUTED: `test_sqlite_vec.py:234 test_an_unknown_dialect_serves_the_core_verbs_and_withholds_glean`; `test_dialects.py:149 test_mariadb_is_tuned_and_mysql_community_is_an_unknown_dialect`.
- Vector tiers: `native_ann` only when profile is `ann` AND an ANN index is provisioned, and `_ann_indexed()` is Postgres-only (`backend.py:654-667`); the pgvector HNSW index is dialect-conditional DDL (`rows.py:899-915`). MariaDB and Oracle therefore run `native_exact` although their profiles say `ann`. READ.
- Cosine spelling per dialect in `distance.py:30-45`; the generic floor raises `ValueError` there (the capability gate stops it earlier). READ.

### 1.3 First touch, verify, provision, install

- `EngineHost.ensure_ready()` → `_first_touch()`: file settings → value cap → vector probe → `_verify_or_provision()` (`engine.py:260-300`, `:400-420`). READ.
- `_verify_or_provision`: serialization point (`pg_advisory_xact_lock` on Postgres; SQLite's `BEGIN IMMEDIATE`; nothing elsewhere, unique-violation arbitration is the backstop — `engine.py:539-545`), `create_all(checkfirst=True)` only when the meta table is absent, then provision under a savepoint or adopt (`engine.py:480-516`). READ.
- `_adopt`: `schema_format_version != SCHEMA_FORMAT_VERSION` → `ErrorKind.schema_mismatch` (`vfs.unavailable.schema`) with `data={"found","expected"}` and "re-provision the mount" (`engine.py:567-577`; `results/kinds.py:88`). Native column width ≠ stored embedding width → `invalid`. Stored *model* mismatch is not refused (vector leg declines per call; `reindex` migrates). READ; pinned EXECUTED `test_engine.py:186-200`, `:206-217`.
- `SCHEMA_FORMAT_VERSION = 23` (`rows.py:139`). 22 tables in `VFSTables` (`rows.py:337-362`). READ.
- `install_extensions()`: runs the profile's install statement under a savepoint then re-probes; 42501 → `permission_denied` naming the fix (`engine.py:302-326`; `backend.py:1099`). ADR 077. READ; pinned by `test_sqlite_vec.py:118-232`.
- **There is no migration story.** No `ALTER`, no Alembic, no "upgrade" verb; a mismatch is a refusal to re-provision. ADR 020 says the number stays 1 until first release and bumps thereafter with a directional message and a corruption class — none of the pin-3 refinements exist (`context/decisions/020-…md:32-47`). READ.
- `schema=` qualifies every table but **nothing creates the schema** (spec 157 unbuilt; `grep schema_ddl src/` empty). The test harness creates it per test (`tests/support/server_schemas.py:38-48`: schema on Postgres/MSSQL, database on MariaDB, user on Oracle). READ.

### 1.4 Statement boundedness (the 10k contract)

- `membership_budget = min(in_list_budget, parameter_budget − 32)` (`dialects.py:623-630`); `arm_budget` caps glob OR-fans at 200 arms and under the expression-depth budget (`:638-651`); `statement_budget` measures per-row binds off the compiled bind registry and fails loudly on drift (`:763-795`); `bulk_insert` pages by `rows_per_statement` (`:838-880`). READ.
- Every `IN (...)` goes through `membership()`/`locked_lookup()` (`membership.py`) — 90+ call sites. The nine raw `.in_()` sites outside it are all bounded: `glean.py:495/509/810` and `lexical.py:123` iterate `chunked(..., membership_budget)` and round-two arms are packed under `parameter_budget` (`glean.py:507-525`); `reads.py:428` admits the ext set only when `len ≤ membership_budget`; `reads.py:446` and `render.py:209-210` are fixed small sets; `indexing.py:696` is a chunk. READ. INFERRED: no statement grows with batch size on any verb today.
- MSSQL/SQL-Server-specific: `_pending_probe`'s "never a bare SELECT EXISTS" (live error 42000, `open-questions.md:225`). READ.

10k / scale pins that exist in `tests/` (READ):

| Verb | Pin | Size | Marked slow |
|---|---|---|---|
| write + stat | `test_dialects.py:511 test_a_large_entry_batch_round_trips` (asserts ≥2 insert pages) | 2,500 default, 10,000 | 10k yes |
| mkedge / touch / rmedge | `test_dialects.py:529 test_a_large_edge_batch_round_trips` | 2,500 / 10,000 | 10k yes |
| glob (pattern fan) | `test_reads.py:527-531` | 2,000×10 / 10,000×50 | 10k yes |
| delete + restore | `test_trash.py:1020-1025` flat statement count | 1,000 / 2,000 | 2k yes |
| read of tombstoned paths | `test_trash.py:1113-1116` | 10,000 | yes |
| graph seeds | `test_graph.py:246-248` declared statement count | 10,000 | yes |
| every verb under budget 48 | `test_dialects.py:413 test_tiny_budget_batch_survives_every_verb` | 60 entries, membership 16 | no |
| write/edit statement counts | `test_writes.py:94,112,142` | small | no |
| **move / copy / mkdir / sweep / grep / glean / grant verbs** | **no ≥1k count pin found** (`grep range(1_000…)` empty in `test_topology.py`, `test_writes.py`) | — | — |

### 1.5 Concurrency, pooling, isolation

- Pooling: `create_async_engine(url)` defaults only; no `pool_size`, `max_overflow`, `pool_pre_ping`, `pool_recycle` anywhere in `src/` (grep empty). READ.
- Retry: whole-method redrive on retryable DBAPI errors or `StaleSnapshot`, 4 attempts, jittered doubling backoff (`engine.py:328-360`; jitter landed `ae27108` 2026-10-24). Exhaustion → `conflict`, retryable. READ.
- Serialized verbs (delete, restore, sweep, move, copy) take a locking read of the one-row `vfs_lock` table as their first statement (`serialized.py:112-123`, ADR 078); writes are not serialized with them and are guarded on version. READ.
- Lock-order fix `25f6da4` (2026-10-24): every write pass walks rows sorted by path; deadlocks were possible on all four server engines before. READ (commit body).
- Isolation pins: Postgres and MariaDB pin op REPEATABLE READ / topology READ COMMITTED; SQL Server, Oracle, SQLite run their defaults (`dialects.py` table above). READ.

### 1.6 CI and the real-engine legs

- `.github/workflows/test.yml`: SQLite only, Python 3.11–3.14, `ty` + 100% coverage on 3.13. READ.
- `.github/workflows/test-dialects.yml`: four jobs (postgres, mariadb, mssql, oracle) from `docker/compose.test.yml` — `pgvector/pgvector:pg17`, `mariadb:11.8`, `mcr.microsoft.com/mssql/server:2025-latest` (amd64 only), `gvenzl/oracle-free:23-slim` — on push to main and PRs touching storage/models/tests; no schedule (dropped `242ca9f`). Each leg runs `pytest -m <dialect> -n 0` — i.e. **only the ~330 tests carrying that marker**, not the whole suite. READ.
- Markers in `tests/`: postgres 14, mariadb 14, mssql 15, oracle 11 class-level marks plus `ENGINE_LEGS` parametrizations in `test_signals.py`, `test_links.py`, `test_races.py`, `ranking/test_harness.py`. The conformance instantiation is `tests/storage/test_conformance.py` (one `StorageContract + GrantsContract` subclass per engine, ~215 `@needs(...)` gates, plus per-engine regressions: MSSQL bind budget, membership form, torn-row, chunk guard; topology rivals on all four; segment cascades; encoded-kind index; lexical fidelity; ranking pin; lexical build beyond a page; content-bytes audit; blob column). READ.
- Last recorded local four-leg run with counts: `0e0f7d8` 2026-10-13 — Postgres 337, MariaDB 328, Oracle 333, SQL Server 338. READ (commit body). `ac5c515` (spec 164 graph, 2026-10-14) says "Engine legs not run here". READ.
- GitHub "Dialect tests" runs (EXECUTED via `gh run list/view`): success on `0e0f7d8`, `e8b8d9a`, `ac5c515` (2026-10-15, all four green). **The latest run, 2026-10-28 on HEAD `90f5883`: postgres, mariadb, oracle green; mssql FAILED at the "Install ODBC driver" step** (apt from packages.microsoft.com; tests never ran). The six storage fixes of 2026-10-24 (`25f6da4`…`ba77449`) therefore have no SQL Server evidence, local or CI.
- Local tooling: `.claude/skills/db_test/SKILL.md` (full cycle), `docker/README.md`. `scripts/mssql_up.sh`, `mssql_test.sh`, `mssql_down.sh` are **dead**: they reference `docker/mssql/docker-compose.yml` (absent), `grover-mssql-2025`, `GROVER_MSSQL_URL`, `tests/test_mssql_backend.py` (absent). READ.

---

## 2. In flight (specs/ADRs touching this domain)

| Item | Status line (READ) | What it would change here |
|---|---|---|
| ADR 059 | accepted 2026-08-27; pin 4 amended by ADR 079 | Supported = has a cosine function; MySQL community dropped; unknown dialects get core verbs, withheld `glean` only |
| ADR 077 | accepted 2026-10-12, reconciled 2026-10-13 with `install_extensions` (`c1900be`) | Built |
| ADR 078 | accepted 2026-10-13 | Built (`vfs_lock`, `serialized.py`) |
| ADR 079 | accepted 2026-10-14, spec 164 landed | Built; graph on every dialect |
| ADR 056 / 061 / 067 / 071 / 072 | accepted | Built (bulk modes; VALUES membership; rights compile; fan; range join) |
| ADR 087 | proposed 2026-10-24; six leans pending Clay | Pin 8: engine error code as `data["vfs.engine_error"]`; fault model written once at the seam (spec 179) |
| Spec 051 fan-out deadline | draft 2026-07-07, two `[NEEDS CLARIFICATION]` | Router-level; `timeout` kind. Not a storage change. |
| Spec 080 MySQL-family batch UPDATE | researched 2026-08-25, design waits on Clay | MariaDB guarded updates are O(N) driver round trips (10k overwrite ≈ 10k UPDATEs, 4.7 s → 1.2 s measured with the UNION ALL derived-table join) |
| Spec 102 set-based scattered delete | researched 2026-08-25, design waits on Clay | **Largely overtaken by spec 162**: delete is now a tombstone stamp, set-based, "one bounded fetch … once per chunk" (`trash.py:1-35`; flat-count pin `test_trash.py:1025`). The reparent/path-rewrite the research measured no longer exists. INFERRED: 102 should be re-scoped to *move/copy at 10k* or closed. |
| Spec 156 mount admission | draft 2026-10-08 | Router; not storage |
| Spec 157 Postgres provisioning for host apps | draft 2026-10-08; markers resolved | `schema_ddl` profile field + `CREATE SCHEMA` at first touch (Postgres, MSSQL); `bulk_insert_mode(profile, dialect)` so psycopg 3 takes `core`, only asyncpg takes `copy`; 42501 classified on provisioning; second Postgres leg URL. **Unbuilt** (`install_extensions` covered the privilege half for the extension only). |
| Spec 160 cross-mount copy | draft 2026-10-08 | Router; not storage |
| Spec 161 version rows | seed; write-replace mint built by 162 slice B (`versions.py`) | Read-side verb and retention still owed (now spec 180's `versions`) |
| Spec 162 trash tombstone | built and committed 2026-10-12/13; all four legs green at `0e0f7d8` | Done |
| Spec 165 permission ladder | landed 2026-10-14 | Done |
| Spec 166 release lane | draft 2026-10-15 | Final-0.1.0 bar: "the four real-engine legs (Postgres, MariaDB, SQL Server, Oracle) pass from the published wheel"; `[NEEDS CLARIFICATION]` whether a feature gate applies |
| Spec 179 storage seam as kernel | draft 2026-10-24, not started | `Supports*` regrouped by kernel group; `features()`; atomic-unit trait; fault model in `protocol.py`; engine code as a structured field; retry/rights-cache counters; conformance split by kernel op + crash-point + access-path families |
| Specs 174 / 176 / 177 / 178 / 180 / 181 | drafts 2026-10-24, not started | Write preconditions + append; listing cursor; request key / replay; `read(range=)` via engine substring; `pack`/bounded `sweep`/`versions`; `entry_id` on `stat`. Each adds statements the legs must prove on four engines. |
| Archived 072, 084, 108, 110, 111, 115 | landed | Prior landings; 108/115 are why bind accounting is "true" today |

---

## 3. Gaps vs the 0.1.0 goal (theme 2: "storage for SQLite, Postgres, MSSQL, Oracle")

1. **No README/engine support matrix.** README line 132 says "green on SQLite, Postgres, MariaDB, SQL Server and Oracle" and nothing more; `docs/how-to` has only the pgvector page. No page states versions, extras, limits, or what "supported" means. READ.
2. **Schema lifecycle is "re-provision".** No migration, no directional message, no corruption class (ADR 020 pin 3 unbuilt), no `schema` creation (spec 157). A host on a real database that upgrades vfs across a format bump loses its mount unless it dumps/reloads by hand. READ.
3. **SQL Server CI leg is fragile at the apt step** and is the one engine with no arm64 image; the 2026-10-24 storage fixes are unproven on it. EXECUTED.
4. **Legs run only marked tests (~330 of 5,780).** Verb-level unit families (`test_writes.py`, `test_reads.py`, `test_graph.py`, …) run on SQLite only; the engines see them only through the conformance contract. INFERRED risk: a Postgres-only or MSSQL-only branch in a builder with no conformance row is untested on that engine.
5. **No 10k count pins for move, copy, mkdir, sweep, grep, glean, grant verbs** (§1.4 table). The contract says every builder is bounded at 10k; only write/edge/glob/delete/restore/graph are pinned at ≥1k.
6. **MariaDB guarded updates are O(N) round trips** (spec 080, open-questions.md:44-52). Correct and bounded, but a 10k overwrite is ~10k statements inside REPEATABLE READ.
7. **Pool and connection posture is unconfigured and undocumented** (no `pool_pre_ping`, no sizing, no guidance for borrowed factories; MSSQL `use_setinputsizes=False` is only applied on the built path — a borrowed pyodbc factory silently mangles non-Latin1, `engine.py:583-603`).
8. **Driver choice is pinned per dialect, not per driver**: a `postgresql+psycopg://` URL would hit `copy_records_to_table` on a psycopg connection (spec 157 item 4; `dialects.py:852-867`). INFERRED from code: `bulk_insert` reads `profile.bulk_insert` only.
9. **Engine error code is not a structured field** (ADR 087 pin 8 / spec 179): refusals carry `str(origin)` in `detail` (`engine.py:344-356`).
10. **Oracle naming drift**: the `23` image family now reports "Oracle AI Database 26ai Free 23.26.2.0.0" (engine-matrix study, 2026-08-26); the repo says "23ai" everywhere. Cosmetic but a README matrix must say which.

---

## 4. Risks — stale, wrong, or contradictory

1. **CLAUDE.md:60 and `context/architecture/01-vfs-at-a-glance.md:101` say the generic floor withholds `glean` *and* `graph`.** Code withholds `glean` only (`backend.py:283-286`); ADR 059's status line records the ADR 079 amendment. Two docs stale. READ.
2. **ADR 020 says `SCHEMA_FORMAT_VERSION` "stays 1 until the first release"; it is 23** (`rows.py:139`) and `architecture/06:216` says "bumped on every schema change". The ADR's pin 1 was abandoned without amendment; its pin 3 (directional message, corruption class) is unbuilt. READ.
3. **`docker/README.md:4-5` and `.claude/skills/db_test/SKILL.md:16` cite `tests/test_storage_conformance.py`** — the file is `tests/storage/test_conformance.py`. The skill also says "mkedge is the last classified stub"; `mkedge` is built (`backend.py:924`). READ.
4. **`scripts/mssql_up.sh` / `mssql_test.sh` / `mssql_down.sh` are dead** (grover-era paths; §1.6). READ.
5. **MariaDB and Oracle profiles declare `vector_distance="ann"` but the mount never provisions an ANN index on them** (`rows.py:899-915` Postgres-only; `_ann_indexed` Postgres-only). The declaration is about the engine, the tier is always `native_exact`. Honest but confusing; the support matrix must say "exact scan" for both. READ.
6. **Spec 102 describes a delete arm that no longer exists** (reparent into trash buckets); open-questions.md:159-180 still carries it as open. READ.
7. **Spec 166's final bar names MariaDB** as one of "the four real-engine legs" while Clay's 0.1.0 theme list names SQLite, Postgres, MSSQL, Oracle. Contradiction to resolve (§6).
8. **Latest Dialect-tests run is red on mssql at an infra step** (§1.6). Anyone reading the badge sees red; the code itself is unproven, not failing.
9. **pyproject `version = "0.0.22"`** while spec 166 wants `0.1.0a1`; the publish matrix "has never run" (`standards/release.md:19-24`). READ.
10. **Borrowed-session hosts skip `_engine_kwargs`** (MSSQL setinputsizes) and the SQLite transaction-control install is marker-guarded on the *engine* — two hosts borrowing one bind share PRAGMAs silently (`engine.py:606-618`). READ; INFERRED hazard for host apps (theme 5/6).
11. **`docs/how-to/add-a-backend.md`, `expose-over-mcp.md` are headings only**; `docs/index.md` is the old essay. READ.

---

## 5. Proposed roadmap stories

### S-1 — The engine support matrix is a published, tested page

**Why.** "Supported" today means: a tuned `DialectProfile`, a Docker leg in CI, and a cosine distance function (ADR 059). Nowhere does the README say this, name versions (Postgres 17 + pgvector ≥0.8, MariaDB ≥11.8, SQL Server 2025 with the UTF-8 BIN2 collation floor of 2019+, Oracle 23ai/26ai Free, SQLite ≥3.50 with extension loading), or say what an unknown dialect gets. A 0.1.0 host picks an engine off this table. The table must be generated from or pinned to `PROFILES` so it cannot drift. **Depends on.** Nothing. Precedes 0.1.0b1. **Acceptance.**
1. `README.md` carries a matrix with one row per `PROFILES` entry plus "any other SQLAlchemy dialect", columns: driver extra, minimum server version, verbs served, vector tier (`ann`/`exact`), ANN index provisioned (Postgres only), arbitration, isolation pins, known caps (Oracle `IN` 1,000; SQL Server 2,100 binds / 2,000 lock budget; MariaDB `max_allowed_packet` and 65,535-byte row; pgvector HNSW 2,000 dims).
2. A docs-fence test (the existing `pytest docs README.md` job) asserts the matrix's dialect names equal `set(PROFILES) | {"generic"}` and each row's `arbitration`/`vector_distance` cell equals the profile field.
3. CLAUDE.md:60 and `architecture/01:101` say `glean` alone is withheld; a grep test over `context/architecture/*.md` for "withholds `glean` and `graph`" finds nothing.
4. `docker/README.md`, `db_test/SKILL.md` cite `tests/storage/test_conformance.py`; `scripts/mssql_*.sh` are deleted.
5. The matrix names the Oracle image's reported release string verbatim.

### S-2 — Schema lifecycle: directional mismatch, corruption class, and a `migrate`/re-provision path a host can run

**Why.** Every format bump today strands any real database (`schema_mismatch` → "re-provision"). 0.1.0 is the commitment point ADR 020 named: from then on bumps must carry a path. The minimum honest story for 0.1.0: the refusal says which side is older; an absent/garbage version row classifies as corruption not mismatch; and a developer-plane verb (`migrate()` or `reprovision(confirm=…)`) exists with at least the identity-preserving dump/reload the test suite already does (`test_identity_portability.py` proves rows survive re-minting). Full `ALTER` migrations can wait for 0.2. **Depends on.** ADR 020 amendment (Clay). Interacts with spec 157 (schema creation) and spec 179 (fault model). **Acceptance.**
1. A meta row at `SCHEMA_FORMAT_VERSION + 1` refuses `schema_mismatch` with `data["direction"] == "store_newer"` and a message naming "upgrade vfs"; at `− 1`, `"store_older"` naming the migrate verb. Pinned on SQLite and on every engine leg.
2. A meta table present with no row, or a non-integer/negative version, classifies `ErrorKind.corruption` (new kind or existing `internal`? — Clay), never `schema_mismatch`.
3. `migrate()` on a store one version behind returns `success=True` and the next `first_touch` adopts; the number of DDL statements issued is pinned per bump (count, not time).
4. ADR 020 is amended to record that pre-release bumps happened (1 → 23) and that the commitment point is `0.1.0b1`.
5. A `SCHEMA_FORMAT_VERSION` bump without a matching migration entry fails a unit test (a registry of `(from, to, statements)`).

### S-3 — Provisioning for host apps: create the schema, pick the bulk path by driver, classify privilege refusals (spec 157, built)

**Why.** A host handing vfs `schema="vfs"` on Postgres or SQL Server must `CREATE SCHEMA` by hand; a psycopg 3 session factory crashes on the first bulk insert with `AttributeError`; a role without `CREATE` privilege gets `internal`. These are the first three things a production host hits (the SmartOwl memo). Theme 6 (serve as MCP) and theme 5 (sync/ETL) both start with a host app's existing Postgres. **Depends on.** Spec 157 as written (markers resolved). S-2 for the corruption/direction vocabulary. **Acceptance.**
1. `DatabaseStorage(url=postgres, schema="vfs_demo")` on a database with no such schema serves its first `write`; same on the SQL Server leg; `profile.schema_ddl is None` on SQLite, MariaDB, Oracle and first touch issues no schema statement there (statement count pinned).
2. Through a `vfs_nocreate` role (new initdb script), first touch refuses `unavailable` (or `permission_denied` — Clay) with `data["schema"] == "vfs_demo"` and `data["privilege"] == "CREATE"`, never a traceback.
3. `bulk_insert_mode(profile, dialect)` returns `"copy"` only when `dialect.driver == "asyncpg"`; a `postgresql+psycopg://` leg (`VFS_TEST_POSTGRES_PSYCOPG_URL`) runs the conformance contract and a 10,000-file write lands in `"core"` with ≥2 insert pages counted.
4. A borrowed session factory on `mssql+aioodbc` without `use_setinputsizes=False` is refused at first touch with a classified `invalid` naming the engine kwarg, or the host applies it itself — one of the two, pinned on the mssql leg with a non-Latin1 path round-trip.

### S-4 — Every verb has a 10k count pin, and the legs run them

**Why.** The ETL contract is "10,000+ files in one call on every dialect". Pins exist for write, edges, glob, delete/restore, tombstoned reads and graph; none for move, copy, mkdir, sweep, grep, glean, grant verbs. A `count operations, never wall-clock` pin per verb is cheap on SQLite and is the only thing that catches a builder regressing to per-row statements. The slow tier runs them on the engine legs too. **Depends on.** Nothing; informs S-5 and S-7. **Acceptance.**
1. For each of `mkdir`, `move`, `copy`, `sweep`, `grep` (scoped to 10k paths), `glean` (scoped), `grant`/`revoke` (10k subjects or paths): a test writes 10,000 entries and asserts the statement count issued by the verb equals a declared formula in `O(chunks)` with the chunk count derived from `membership_budget`, marked `slow`.
2. Each pin is parametrized over `ENGINE_LEGS` so the four legs run it with their real budgets (Oracle 1,000; MSSQL 2,000).
3. Under a monkeypatched `parameter_budget = 48`, every verb above still returns the correct result (extends `test_tiny_budget_batch_survives_every_verb`).
4. The MariaDB leg records the per-row UPDATE count of a 10k overwrite as a *known* number in the pin (so spec 080 landing is a visible delta, not a surprise).

### S-5 — MariaDB set-based guarded updates (spec 080) — only if MariaDB stays in 0.1.0

**Why.** Correct and bounded today, but 10k overwrites are ~10k round trips inside REPEATABLE READ, widening the deadlock/lock-wait window. The research is done (UNION ALL derived-table join, 4× faster, savepoint-and-redrive attribution proven on both family members). **Depends on.** Clay's decision on MariaDB (§6 Q1). S-4's pin. Spec 080 slice B design. **Acceptance.**
1. A clean 10,000-row overwrite on the MariaDB leg issues `ceil(N / rows_per_statement)` UPDATE statements, counted by a `before_cursor_execute` spy; the per-row width is measured by `statement_budget`.
2. `CLIENT_FOUND_ROWS` is asserted on the connection at first touch (the semantic the aggregate `rowcount == N` relies on); a connection without it refuses `unsupported`.
3. A conflicted row inside a set-based chunk is attributed by the savepoint re-drive exactly as the executemany arm attributes it today (conformance contract unchanged, byte-identical observations).
4. SQLite, Postgres, SQL Server, Oracle statement counts are unchanged (their pins from S-4 hold).

### S-6 — The SQL Server leg is reliable and the four legs are a release gate

**Why.** The latest CI run is red at `apt-get install msodbcsql18`, and the 2026-10-24 storage fixes have no SQL Server evidence. Spec 166's final bar requires the legs to pass *from the published wheel*. The leg must not depend on a third-party apt repo being up at push time, and the legs must be runnable against a wheel, not a checkout. **Depends on.** Spec 166. **Acceptance.**
1. The mssql job installs the ODBC driver with a retry loop or from a cached artifact; a `workflow_dispatch` input lets any leg run against `pip install vfs-py==<version>` instead of the checkout.
2. `test-dialects.yml` is green on HEAD for all four engines, and the commit that fixes it records per-leg pass counts in its body (the `0e0f7d8` convention).
3. A `scripts/legs.sh` (or the `db_test` skill) runs the four legs concurrently and prints one line per leg with its pass count; the skill's stale paths are corrected.
4. `publish.yml` gains a step that runs the four legs against the built wheel before `uv publish` (or the release standard says why not).

### S-7 — Pool, connection and borrowed-host posture, documented and pinned

**Why.** Themes 5 and 6 put vfs inside notebooks, ETL processes and an MCP server, all long-lived. Today the engine is `create_async_engine(url)` with defaults: no `pool_pre_ping`, no recycle, no sizing, and a borrowed factory skips the MSSQL kwarg. A dropped connection classifies `backend_unavailable, retryable=True` and the whole-method redrive handles it, which is right — but the pool facts should be declared and the borrowed path's obligations stated at the seam. **Depends on.** Spec 179 (counters) is adjacent; not required. **Acceptance.**
1. `DatabaseStorage(url=…, pool=PoolConfig(size, overflow, pre_ping, recycle))` (or kwargs) is plumbed into `create_async_engine`; the SQLite `:memory:` path keeps `StaticPool` and serialization.
2. A test kills the connection between two ops on each engine leg (`pg_terminate_backend`, `KILL CONNECTION`, `KILL <spid>`, `ALTER SYSTEM KILL SESSION`) and asserts the next op succeeds after exactly one `backend_unavailable` retry counted by the retry spy.
3. A borrowed `session_factory` on MSSQL built without `use_setinputsizes=False` round-trips `/测试.md` losslessly or refuses `invalid` at first touch — pinned on the mssql leg.
4. `docs/how-to/` gains "run vfs on your own Postgres/SQL Server/Oracle" pages (one each) whose code blocks are executed by the docs fence against the in-memory engine where possible.

### S-8 — Engine error as a structured field at the seam (ADR 087 pin 8 slice of spec 179)

**Why.** Every classified refusal from the engine today carries `str(origin)` in `detail`. An MCP client or a CLI cannot branch on `ORA-00060` vs `40P01` without parsing text, which the repo's own rule forbids. One field, read from the driver attributes the classifiers already read. **Depends on.** ADR 087 accepted (pin 8 is not among the leans). Spec 179 slice. **Acceptance.**
1. `classify_failure` sets `data["vfs.engine_error"] = {"sqlstate": …, "code": …, "driver": dialect.driver}` using `_sqlstate_of`/`_driver_code_of`, never regex on the message.
2. On each engine leg, a forced deadlock/serialization failure that outlives retries carries the engine's own code (`40001`/`40P01`, `1213`, `60`, `1205`) in that field.
3. The `KindContract` table in `results/kinds.py` documents the field for `unavailable`, `backend_unavailable`, `conflict`, `internal`.

---

## 6. Open questions Clay must decide

1. **Is MariaDB a 0.1.0 target?** Clay's theme list says SQLite, Postgres, MSSQL, Oracle; spec 166 item 5 and `docker/README.md` say four legs *including* MariaDB; ADR 059 made MariaDB "the MySQL family's supported member". **Keeping it costs**: spec 080 (set-based updates, ~1 slice), the per-row UPDATE cost documented in the matrix, one CI leg (cheapest of the four: arm64 native, ~3 min), and every new builder (174–181) proven on five engines not four. **Dropping it costs**: deleting `MARIADB`, the `mariadb` extra, the leg, the initdb script, `range_source="json_table"`, `value_cap`, `guard_miss="redrive"` and the `redrive` path's only real-engine exercise (the generic floor also declares `redrive` — it would then be pinned synthetically only); and the MySQL family becomes "unknown dialect: core verbs, no glean". My read: the code is already there and green; the cost of keeping is spec 080, the cost of dropping is losing the one engine that exercises `redrive` and the byte-key index-cap regression pin (ADR 024). Recommend: keep as *supported, second tier* (served, in CI, no ANN) and say so in the matrix — but this is Clay's call.
2. **What does `schema_mismatch` do from 0.1.0b1 on** — refuse-and-re-provision (today), or a `migrate` verb with a statement registry (S-2)? And is a corrupt version row `internal` or a new `corruption` kind (ADR 020 pin 3)?
3. **Is spec 157 (schema creation, driver-chosen bulk path) a 0.1.0 story?** It is the first thing a Postgres host app hits; I recommend yes (S-3).
4. **Spec 102**: close as overtaken by 162, or re-scope to move/copy at 10k? The research numbers no longer describe the code.
5. **Should the engine legs run the whole suite** (`-m <dialect>` runs ~330 tests of 5,780) or stay as the marked contract? A middle path: parametrize the verb-level count pins (S-4) over `ENGINE_LEGS`.
6. **Is the four-leg-from-published-wheel bar (spec 166 item 5) the only 0.1.0 final gate**, or does a feature (MCP surface, `versions` read side) gate it?
7. **Pool configuration surface** (S-7): constructor kwargs, a `PoolConfig` model, or URL query parameters only?
8. **Oracle naming**: say "Oracle 23ai" (vendor's marketing name for the 23 line) or the image's reported "26ai Free 23.26"? Which Oracle version is the floor — the vector type and `VECTOR_DISTANCE` arrived in 23.4; the matrix should name 23.4+.
