# 157 — Postgres provisioning for host apps: create the schema on first touch, bulk-insert by driver

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo;
  revised 2026-10-08 after a review against `0760fe9` (privilege
  errors are `internal` today; `CREATE SCHEMA IF NOT EXISTS` is not
  portable; the extension marker resolves; psycopg's mode is a fork
  to measure; no logging convention exists; the leg harness has one
  URL per engine)
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** feature (database backend: `engine.py` provisioning and
  failure classification, `dialects.py` bulk-insert selection and one
  profile field; the Postgres engine leg)
- **Depends on:** first-touch provisioning as built (`engine.py`:
  `ensure_ready` L260–277, `_first_touch` L386–399,
  `_verify_or_provision` L439–478, `_provision` L480–506), the
  `CREATE EXTENSION IF NOT EXISTS vector` DDL as a `before_create`
  event on the metadata (`models/rows.py` L876–877, only when
  `native_embedding` is set), `classify_failure` and
  `is_permanent_defect` (`engine.py` L305–334, `dialects.py`
  L895–922), the `DialectProfile.bulk_insert` modes (`"core"`,
  `"driver"`, `"copy"`) and ADR 056.
- **Research it stands on:**
  `../../../research/2026-10-08-smartowl-workspace-integration-issues.md`
  items 19 and 20.

## Intent

A host app on Postgres already has a schema convention and a driver.
Today vfs breaks on both. `DatabaseStorage(schema="vfs")` qualifies
every table with the schema and never creates it, so the first touch
fails unless the host ran `CREATE SCHEMA` by hand. And the Postgres
profile pins bulk inserts to asyncpg's binary `COPY`, so a host that
hands vfs a psycopg 3 session factory gets an `AttributeError` on the
first bulk insert because a psycopg connection has no
`copy_records_to_table`. The borrowed-session construction that
`session_factory=` supports does not work on the most common Postgres
driver.

One line: provisioning creates what it needs, and the bulk path is
chosen by the driver actually on the connection.

## Decided semantics

1. **First touch creates the schema.** When `schema=` is set,
   provisioning issues the dialect's schema DDL on the same connection
   in `_verify_or_provision`, before `create_all`. SQLAlchemy takes no
   position: `dialect.supports_schemas` is `True` on every dialect
   including SQLite, and `CreateSchema(..., if_not_exists=True)`
   compiles to the same `CREATE SCHEMA IF NOT EXISTS` text everywhere,
   which SQL Server rejects. So a `DialectProfile.schema_ddl: str |
   None` field carries it: Postgres `CREATE SCHEMA IF NOT EXISTS
   {schema}`; SQL Server `IF NOT EXISTS (SELECT 1 FROM sys.schemas
   WHERE name = N'{schema}') EXEC('CREATE SCHEMA {schema}')`; `None`
   elsewhere (Oracle schemas are users; SQLite and MariaDB have no
   schema to create). The name goes through
   `dialect.identifier_preparer.quote_schema`, never an f-string.
   `tests/support/server_schemas.py` L38–48 already holds the same
   per-dialect table and adopts the profile field.
2. **A privilege refusal is classified, not a traceback.** Today
   SQLSTATE class 42 is a "permanent statement defect" and lands as
   `internal`. `42501 insufficient_privilege` is lifted out of that
   rung and classified `unavailable` with `data={"schema": …,
   "privilege": "CREATE"}`; `3F000 invalid_schema_name` keeps
   `unavailable` and names the schema. Precedent for a named-fix
   `unavailable`: `_probe_sqlite_vec` (`engine.py` L417–437).
3. **The extension step needs no tolerance logic.** Postgres checks
   `IF NOT EXISTS` before any privilege check
   (`CreateExtension`, `src/backend/commands/extension.c` L2170–2174
   in the reference clone), so an installed extension is always
   "skipping", never refused. An absent extension under a
   non-superuser (pgvector's control file is not `trusted`) refuses
   `unavailable` naming `vector` and `superuser` through the same
   carve-out as rule 2. The 2026-10-08 marker on this point is
   resolved.
4. **Bulk insert is chosen per driver, not per dialect.** The profile
   keeps `bulk_insert` as the dialect's *preferred* mode; the backend
   reads `dialect.driver` off the live engine: `"copy"` only when the
   driver is `asyncpg`; every other Postgres driver takes `"core"`.
   `"driver"` for psycopg 3 (its pipelined `executemany` through the
   compiled statement `_bulk_statement` already keys on driver and
   paramstyle, L964) is a fork taken only after
   `bulk_insert_bench.py` on the leg shows it winning, per ADR 056 §6.
   The selection is one function, `bulk_insert_mode(profile,
   dialect)`, beside `membership_budget`; it is the only producer of
   `"copy"`, so the copy branch carries no check of its own (the
   `assert driver is not None` at `dialects.py` L813 is a narrowing
   assert and stays). There is no logging convention in `src/vfs`;
   the chosen mode is stored on `EngineHost` as `bulk_insert_mode`
   (like `pgvector_version`) and pinned by a test.
5. **The engine legs prove it.** A second env var
   `VFS_TEST_POSTGRES_PSYCOPG_URL` (`postgresql+psycopg://…`)
   parametrizes `TestPostgresConformance` and
   `TestPostgresBulkInsertTransaction`; `psycopg[binary]>=3.1` joins
   the `postgres` extra; `docker/initdb/postgres/` adds a role
   `vfs_nocreate` with `CONNECT` only, for the privilege criterion.
   The fallback is pinned by a real engine, not a mock.

## Scope

- `schema_ddl` on `DialectProfile`; the issue site in
  `_verify_or_provision`; the SQLSTATE carve-out in
  `is_permanent_defect` and `classify_failure`.
- `bulk_insert_mode(profile, dialect)` in `dialects.py`;
  `EngineHost.bulk_insert_mode`.
- `psycopg[binary]` in the `postgres` extra; the second URL in the
  db_test skill's Postgres leg and `test-dialects.yml`; the
  `vfs_nocreate` role in the compose init.
- Out of scope: `ALTER` migrations, a schema-per-mount convention,
  Oracle user creation, measuring psycopg's `"driver"` mode.

## Acceptance criteria

- `DatabaseStorage(url="postgresql+asyncpg://…", schema="vfs_demo")`
  on a database with no such schema serves its first `write`; the same
  on the SQL Server leg.
- The same through the `vfs_nocreate` role refuses `unavailable` with
  `data["schema"] == "vfs_demo"` and `data["privilege"] == "CREATE"`.
- A 10,000-file `write` through a psycopg 3 session factory lands in
  `"core"` mode; through asyncpg it still takes `COPY`, and a
  monkeypatched `copy_records_to_table` on the asyncpg leg counts one
  call per page.
- `scripts/ci.sh 3.13` green; the Postgres engine leg green on both
  drivers.
