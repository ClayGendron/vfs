# 157 — Postgres provisioning for host apps: create the schema on first touch, bulk-insert by driver

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** feature (database backend: `engine.py` provisioning,
  `dialects.py` bulk-insert selection)
- **Depends on:** first-touch provisioning as built (`engine.py`
  L133–154, the `CREATE EXTENSION IF NOT EXISTS vector` DDL in
  `models/rows.py`), the `DialectProfile.bulk_insert` modes
  (`"core"`, `"driver"`, `"copy"`) and ADR 056.
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
`copy_records_to_table`. The borrowed-session construction the README
advertises does not work on the most common Postgres driver.

One line: provisioning creates what it needs, and the bulk path is
chosen by the driver actually on the connection.

## Decided semantics

1. **First touch creates the schema.** When `schema=` is set,
   provisioning issues `CREATE SCHEMA IF NOT EXISTS <schema>` before
   the tables, on engines that have schemas (Postgres, SQL Server;
   Oracle schemas are users and are out of scope; SQLite has none). A
   role that may not create schemas gets a classified `unavailable`
   naming the schema and the privilege, not a driver traceback.
   `[NEEDS CLARIFICATION: also make the extension step tolerant — if
   `CREATE EXTENSION vector` is refused for lack of privilege but the
   extension already exists, continue; if it does not exist, refuse
   with the same classified shape. Leaning yes.]`
2. **Bulk insert is chosen per driver, not per dialect.** The profile
   keeps `bulk_insert` as the dialect's *preferred* mode; the backend
   reads `dialect.driver` off the live engine and falls back:
   `"copy"` only when the driver is asyncpg; psycopg (3) takes
   `"driver"` (its `executemany` pipelines); psycopg2 and anything
   unknown take `"core"`. The selection is one function beside
   `membership_budget`, and the chosen mode is logged once at
   provisioning.
3. **The engine legs prove it.** The Postgres leg runs its bulk-insert
   conformance test twice, once per driver (`asyncpg`, `psycopg`), so
   the fallback is pinned by a real engine, not a mock.

## Scope

- `CREATE SCHEMA IF NOT EXISTS` in provisioning, behind the dialect's
  schema support; the classified privilege refusal.
- `bulk_insert_mode(profile, dialect)` in `dialects.py`; the copy
  branch asserts asyncpg or raises a programming error.
- `psycopg` joins the `postgres` extra; the db_test skill's Postgres
  leg gains the second driver.
- Out of scope: `ALTER` migrations, a schema-per-mount convention,
  Oracle user creation.

## Acceptance criteria

- `DatabaseStorage(url="postgresql+asyncpg://…", schema="vfs_demo")`
  on a database with no such schema serves its first `write`.
- The same with a role lacking `CREATE` on the database refuses
  `unavailable` with the schema and privilege named in `data`.
- A 10,000-file `write` through a psycopg 3 session factory lands;
  through asyncpg it still takes `COPY` (the engine leg's statement
  spy sees one `COPY` per page).
- `scripts/ci.sh 3.13` green; the Postgres engine leg green on both
  drivers.
