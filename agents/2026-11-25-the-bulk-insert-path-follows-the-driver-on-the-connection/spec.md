# A bulk insert takes asyncpg's binary `COPY` only when the connection's driver is asyncpg; a psycopg 3 session factory runs the conformance contract and lands a 10,000-file write through Core in at least two counted pages.

A fix. Flags: it is not structural; it adds no public name and changes no verb, argument or error kind (the one packaging change is that the `postgres` extra also installs psycopg 3, decision 10); it does not change the schema format; it needs the engine legs (Postgres on asyncpg, Postgres on psycopg 3, and MariaDB, SQL Server and Oracle because `bulk_insert` is on every engine's write path); it touches no rights; it does not touch the Rust engine; it is parallel-safe with every unit that does not edit `bulk_insert`, `tests/conftest.py`'s leg table or the dialect workflow's matrix. It serves roadmap storage story D3 at gate b, criterion 3 only, whose acceptance line is the contract: "The bulk path is chosen by driver (spec 157's proposed `bulk_insert_mode`; today's helper is `dialects.bulk_insert`): `"copy"` only when the driver is asyncpg; a `postgresql+psycopg://` leg runs the conformance contract and a 10,000-file write lands in `"core"` with ≥ 2 insert pages counted." ([the roadmap](../../context/standards/roadmap.md), line 477). It is converted, by amendment, from sections 4 and 5 and acceptance bullet 3 of [spec 157](../../context/specifications/archive/157-postgres-provisioning-for-host-apps/spec.md), read with [the study of that spec](../2026-11-25-the-backlog-converted/studies/051-162/157-postgres-provisioning-for-host-apps.md) and placed by [the map of units](../2026-11-25-the-backlog-converted/units.md) as unit 157-2. It stands on item 20 of [the 2026-10-08 integration memo](../../context/research/2026-10-08-smartowl-workspace-integration-issues.md), on [the 2026-08-26 bulk-insert study](../../context/research/studies/2026-08-26-bulk-inserts/bulk-inserts.md) and on [the 2026-07-14 posting-storage memo](../../context/research/2026-07-14-database-storage-posting-storage.md). It depends on no other spec and on no roadmap decision: story D3 names story D2 as its dependency, and nothing here reads what D2 changes (the direction of a format mismatch), so that dependency is the story's ordering and not this unit's build. It can be built at any point after commit `9daedd2b`, before or after its two siblings from the same source.

## The problem

Every fact below is at commit `9daedd2b`. The server facts were taken by scratch scripts, not kept in the tree, against a private `pgvector/pgvector:pg17` container (pgvector 0.8.7) with SQLAlchemy 2.0.52, asyncpg 0.31.0 and `psycopg[binary]` 3.3.9 on Python 3.13.

- The bulk mode is read from the dialect's profile alone. READ, `src/vfs/storage/backends/database/dialects.py:913-914`: `dialect = session.get_bind().dialect` and then `mode = profile_for(dialect.name).bulk_insert`. The Postgres profile declares `bulk_insert="copy"` (READ, `dialects.py:539`).
- The copy branch reaches for a method only asyncpg has, and checks nothing first. READ, `dialects.py:923-936`: it fetches the raw driver connection, narrows it with `assert driver is not None` (`:928`) and awaits `driver.copy_records_to_table(...)` (`:931`).
- No function chooses a mode by driver. EXECUTED: a search for `bulk_insert_mode` over `src/` and `tests/` finds nothing.
- A mount on psycopg 3 passes first touch and then fails every mutation, with a refusal that invites a retry that cannot succeed. EXECUTED: `DatabaseStorage(session_factory=<a session factory over create_async_engine("postgresql+psycopg://...")>, schema=...)` returned success from `first_touch()`; `mkdir` then returned `vfs.unavailable` with `retryable=True` and the message "Unavailable: mkdir failed: 'AsyncConnection' object has no attribute 'copy_records_to_table'"; the `write` after it refused `vfs.not_found` on the parent that was never made. The source and the memo describe a raised `AttributeError`; the memo marks its item "Checked: read. Not run." What a caller sees is worse than a traceback: a retryable refusal.
- The borrowed construction is a documented one. READ, `README.md:51`: `DatabaseStorage(session_factory=sessions)`. READ, `src/vfs/storage/backends/database/engine.py:185-189`: the constructor takes exactly one of `url=` and `session_factory=`.
- SQLAlchemy names the driver on the live dialect. EXECUTED: `create_async_engine("postgresql+asyncpg://...").dialect.driver` is `"asyncpg"`; `PGDialectAsync_psycopg().driver` is `"psycopg"` and the class instantiates without the psycopg package installed; both report `insertmanyvalues_max_parameters == 32700` and `use_insertmanyvalues_wo_returning is False`.
- Under Core, an `INSERT` without `RETURNING` on either Postgres driver is not rewritten into multi-row pages. READ, SQLAlchemy 2.0.52 `sql/crud.py:1659-1673`: insertmanyvalues applies without `RETURNING` only where the dialect sets `use_insertmanyvalues_wo_returning`. So `session.execute(insert(table), rows)` (`dialects.py:916`) hands the driver's own `executemany` one single-row statement and one parameter set per row.
- With the mode held to `"core"` on psycopg 3 (the profile lookup inside `dialects.py` replaced for the run), the tree works. EXECUTED: a 10,000-file `write(parents=True)` succeeded with 10,000 `created`; the cursor saw 11 `INSERT` executions against `vfs_entries` (the upsert's multi-row pages, which never pass through `bulk_insert` on Postgres, READ `src/vfs/storage/backends/database/writes.py:475-476`), and one `executemany` each against `vfs_content` (10,000 parameter sets), `vfs_segments` (20,020) and `vfs_edges` (10,021); a 10,000-file overwrite, `stat`, `read`, `ls`, `glob`, `grep`, `edit`, `mkdir`, `mkedge`, `delete`, `restore`, `grant`, `grants`, `rebuild` and `search` all returned success.
- The two transaction facts the asyncpg leg pins hold on psycopg 3 under Core. EXECUTED: a first-statement bulk insert rolled back left 0 rows; a duplicate under a savepoint raised `IntegrityError` (SQLSTATE 23505) and the outer transaction then landed 3 rows.
- On asyncpg the same 10,000-file write copies. EXECUTED: 11 `INSERT` executions against `vfs_entries`, none against `vfs_content`, `vfs_segments` or `vfs_edges`, and `copy_records_to_table` called once for `vfs_content`, twice for `vfs_segments` and twice for `vfs_edges`.
- Nothing in the test configuration can reach a second Postgres driver. READ: one URL variable per engine in `tests/conftest.py:64-69`; one Postgres row in `.github/workflows/test-dialects.yml:38-40`; one Postgres command in `.claude/skills/db_test/SKILL.md:79` and `:119` and in `docker/README.md:29` and `:55`; the `postgres` extra is `asyncpg>=0.29`, `pgvector>=0.3` (`pyproject.toml:55`). EXECUTED: psycopg is not importable in the project environment.
- The unit tests of the copy branch run on SQLite with the profile pinned to `"copy"` and a stub raw connection (READ, `tests/storage/database/test_dialects.py:754-756`, `:870-903`, `:940-976`); they do not set a driver, so they describe a state the fix makes unreachable.

What is wrong: the profile's mode is a fact about one driver, applied to every driver of the dialect. A host application whose Postgres driver is psycopg 3 cannot mount vfs on its own sessions, and no engine leg would notice a regression there.

## Architecture

```mermaid
flowchart TD
    subgraph dialects["src/vfs/storage/backends/database/dialects.py"]
        preferred["DialectProfile.bulk_insert<br/>the preferred mode"]
        copydriver["_COPY_DRIVER"]:::planned
        taken["bulk_insert_mode(profile, dialect)<br/>the taken mode"]:::planned
        bulk["bulk_insert(session, table, rows)"]
        core["Core branch<br/>session.execute(insert(table), rows)"]
        driverbranch["driver branch<br/>exec_driver_sql, paged"]
        copy["copy branch<br/>copy_records_to_table, paged"]
    end
    live["SQLAlchemy Dialect.driver<br/>on the session's bind"]
    subgraph engine["src/vfs/storage/backends/database/engine.py"]
        host["EngineHost"]
        hostmode["EngineHost.bulk_insert_mode"]:::planned
    end
    subgraph config["test configuration"]
        urls["tests/conftest.py ENGINE_URLS"]
        psyurl["postgres_psycopg marker and<br/>VFS_TEST_POSTGRES_PSYCOPG_URL"]:::planned
        extra["pyproject.toml postgres extra"]
        psyextra["psycopg[binary]>=3.1"]:::planned
        matrix[".github/workflows/test-dialects.yml matrix"]
        psyrow["postgres-psycopg row"]:::planned
        legtests["tests/test_engine_legs.py"]:::planned
        skill["db_test skill and docker/README.md"]
    end
    subgraph legs["tests/storage/test_conformance.py"]
        pgleg["TestPostgresConformance<br/>TestPostgresBulkInsertTransaction"]
        psyleg["TestPostgresPsycopgConformance<br/>TestPostgresPsycopgBulkInsertTransaction"]:::planned
        tenk["two 10,000-file write tests"]:::planned
        borrowed["tests/support/server_schemas.py<br/>borrowed_server_storage"]:::planned
    end
    unit["tests/storage/database/test_dialects.py<br/>TestBulkInsertMode"]:::planned

    bulk -.-> taken
    preferred -.-> taken
    live -.-> taken
    copydriver -.-> taken
    taken -.->|core| core
    taken -.->|driver| driverbranch
    taken -.->|copy| copy
    host --- hostmode
    hostmode -.-> taken
    urls --- psyurl
    extra --- psyextra
    matrix --- psyrow
    legtests -.-> urls
    legtests -.-> matrix
    psyrow -.-> psyurl
    skill -.-> psyurl
    psyleg -.-> psyurl
    tenk -.-> borrowed
    tenk -.-> hostmode
    pgleg --- psyleg
    unit -.-> taken

    classDef planned stroke-dasharray: 6 4
    classDef retiring stroke-dasharray: 2 3
```

- **Preferred mode.** The value a `DialectProfile` declares in `bulk_insert`: the mode measured fastest on the driver the profile was tuned with.
- **Taken mode.** What `bulk_insert_mode(profile, dialect)` returns for one live dialect: the preferred mode, except that `"copy"` falls to `"core"` on a driver that is not asyncpg.
- **Counted insert page.** One cursor execution of an `INSERT` statement against one named table, as SQLAlchemy's `before_cursor_execute` event reports it. A raw `COPY` never fires the event, so the count against a table that copies is zero.
- **Driver leg.** A conformance leg that re-runs an engine's contract on a second driver of the same server. It has its own marker and URL variable and is not an entry of `ENGINE_LEGS`.

Nothing is removed, so no node carries the `retiring` class.

## Decisions

### 1. One function, `bulk_insert_mode(profile, dialect)`, returns the mode a bulk insert takes, and `bulk_insert` calls it where it read the profile.

It lives in `dialects.py` under the `Bulk inserts` banner, above `bulk_insert`, and returns a `BulkInsertMode`. `bulk_insert` replaces `mode = profile_for(dialect.name).bulk_insert` (`dialects.py:914`) with `mode = bulk_insert_mode(profile_for(dialect.name), dialect)`. The signature follows `supports_values_update(profile, dialect)` (`dialects.py:852-860`), the tree's existing function that joins a profile declaration to a live dialect fact. The source places the function "beside `membership_budget`"; the file's layout groups public functions by concern, so it sits with the bulk inserts. One producer of the mode means one place where a driver is named.

Basis: the source spec, section 4; still true at `9daedd2b` (no `bulk_insert_mode` exists, by search; `bulk_insert` reads only the profile, `dialects.py:914`).

### 2. `"copy"` is taken only when the live dialect's `driver` is `"asyncpg"`; any other driver under a profile that prefers `"copy"` takes `"core"`.

The copy branch is written against asyncpg's `copy_records_to_table`, so it is correct on that driver and no other. Core is the mode every DBAPI serves, and it is what the generic floor already takes for a driver nothing is known about (`dialects.py:219-229`). On psycopg 3 it worked for every verb tried (the problem, EXECUTED).

Basis: verified lean, the source's section 4 lean of `"core"` for every Postgres driver that is not asyncpg, which the study verifies as holding (its open choice 6); precedent: `context/research/2026-07-14-database-storage-posting-storage.md:54` names psycopg 3's native `executemany` as the fastest pure-Core bulk path on Postgres, and the Core branch at `dialects.py:915-917`.

### 3. A profile that prefers `"driver"` or `"core"` keeps that mode on every driver.

The driver branch calls `exec_driver_sql` with a parameter list (`dialects.py:943`), which every DBAPI's `executemany` serves; only the copy branch calls a method outside the DBAPI. Gating `"driver"` by driver name would need a measured driver per profile that no bench has produced, which is speculative.

Basis: decided in drafting, because the defect is a call to a method one driver has, and the driver branch makes no such call.

### 4. The copying driver is named once, by the module constant `_COPY_DRIVER: Final = "asyncpg"`, beside `_COPY_PROLOGUE`.

SQLAlchemy already exposes the driver's name on the live dialect, so no `DialectProfile` field is added: a profile field is justified only for a decision SQLAlchemy takes no position on, and the fact here belongs to the copy branch's code, not to the Postgres dialect. The constant sits directly above the function that reads it, with a comment of at most two lines.

Basis: decided in drafting, because AGENTS.md, "Lean on SQLAlchemy; keep profiles lightweight", asks that a live `Dialect` fact be read and not redeclared.

### 5. psycopg 3 takes neither `"driver"` mode nor its own `COPY` in this spec; either is a fork taken only after the bulk-insert bench shows it winning.

The bench is `context/research/studies/2026-08-26-bulk-inserts/prototype/bulk_insert_bench.py`. A mode is chosen from a measurement on the engine leg, and a clock belongs in a bench, never in a test. `_bulk_statement`'s cache key already carries `dialect.driver` and `dialect.paramstyle` (`dialects.py:1132`), so the fork needs no change to the cache. The source cites a retired decision record for this rule; the rule is restated here with its reason and the record is not cited.

Basis: verified lean, the source's section 4 fork, which the study verifies as holding (its open choice 6); precedent: `context/research/studies/2026-08-26-bulk-inserts/bulk-inserts.md:34-36`, where every profile's mode was read from the bench table and the engine legs, and AGENTS.md, "Count operations, never wall-clock time".

### 6. The Core branch is left as it is: one `session.execute(insert(table), rows)` per call, paged by SQLAlchemy where the dialect pages and handed to the driver's `executemany` where it does not.

On psycopg 3 that is one `executemany` per call with one single-row statement and one parameter set per row (the problem, READ and EXECUTED). The statement never grows with the batch: its binds are the table's columns. `bulk_insert`'s docstring states this profile and names the fork of decision 5 as the direction, as AGENTS.md asks of a path that is not the fastest at scale. This departs from a literal reading of the roadmap's "≥ 2 insert pages counted", which assumes Core pages a 10,000-row insert on psycopg 3; it does not.

Basis: provisional, no ruling on record; the options were (a) leave the Core branch unchanged and count pages where the write already pages, (b) page the Core branch inside `bulk_insert` by `rows_per_statement` through `chunked` on every engine that takes it, (c) add a fourth mode that issues multi-row `VALUES` pages on psycopg 3; chosen (a) because it changes no statement on SQL Server, Oracle or the generic floor and so no counted pin there, because the 2026-08-26 study measured the multi-row `VALUES` shape eight times slower than Core's executemany on Postgres (`bulk-inserts.md:15`, `:35`), and because paging can be added later without changing what any caller sees.

### 7. The 10,000-file criterion counts insert pages against two tables: at least two against the entries table and at least one against the content table.

The entries count is the one the tree's own batch pin takes (`tests/storage/database/test_dialects.py:515-525`, `:668`), and on Postgres it is where a 10,000-file write pages its inserts through Core: 11 pages on either driver (EXECUTED). The content count is what tells Core from `COPY`: 1 on psycopg 3 and 0 on asyncpg (EXECUTED). The floor of two is the roadmap's and the title's; the criterion does not pin 11, which would pin the entry row's width.

Basis: decided in drafting, because under decision 6 the entries upsert is the only place the write pages inserts through Core, and a count that could not tell Core from `COPY` would pin nothing this spec changes.

### 8. The copy branch carries no driver check of its own, and its narrowing `assert` stays.

`bulk_insert_mode` is the only producer of `"copy"`, so a second check in the branch would be a duplicate that can drift. `assert driver is not None` (`dialects.py:928`) narrows a type after the gate and validates nothing, which is the only use AGENTS.md allows an `assert` in `src/`.

Basis: the source spec, section 4; still true at `9daedd2b` (the assert is at `dialects.py:928`, where the source cites line 813).

### 9. The host exposes the taken mode as a read-only property, `EngineHost.bulk_insert_mode`, computed from the same function.

It returns `bulk_insert_mode(self.profile, self._policy().dialect)` and sits after `membership_budget` (`engine.py:276-279`), the existing property that calls the `dialects.py` function of its own name. It is not stored at first touch: `bulk_insert` receives a session, not the host, so a stored copy would be a second source that the insert path never reads. There is no logging convention in `src/vfs`, so an attribute a test can read is how the choice is made visible.

Basis: verified lean, the source's section 4 lean of holding the mode on `EngineHost`, verified by the study as holding with the amendment that the attribute is a read of the one function (its open choice 7); precedent: `EngineHost.membership_budget` and `EngineHost.parameter_budget` (`engine.py:271-279`), with `EngineHost.vector_version` (`engine.py:208-210`) as the first-touch fact the source compared it to.

### 10. `psycopg[binary]>=3.1` joins the `postgres` extra, and `uv.lock` is regenerated.

The engine leg and CI install by extra (`uv sync --extra postgres`, `.github/workflows/test-dialects.yml:77`), and a `postgresql+psycopg://` URL handed to `url=` needs the driver the URL names. The floor is 3.1 because that release made `executemany` use pipeline mode, which is what keeps the Core branch from one round trip per row; SQLAlchemy 2.0 itself accepts 3.0.2. The `all` extra includes `postgres` and so gains it too (`pyproject.toml:67`).

Basis: the source spec, section 5; still true at `9daedd2b` (`pyproject.toml:55` lists asyncpg and pgvector only; psycopg is not importable in the project environment, EXECUTED).

### 11. The second leg is selected by its own marker, `postgres_psycopg`, and its own variable, `VFS_TEST_POSTGRES_PSYCOPG_URL`.

`ENGINE_URLS` gains `"postgres_psycopg": ("VFS_TEST_POSTGRES_PSYCOPG_URL",)` and `pyproject.toml`'s `markers` gains the matching line. The variable's name is the source's. A separate marker is what lets the collection hook deselect the leg when its URL is unset (`tests/conftest.py:95-97` keys on markers); a second URL under the `postgres` marker would select both drivers' tests whenever either URL was set and leave the other to skip at fixture time.

Basis: decided in drafting, because AGENTS.md, "never skip a test by hand where a marker and this hook can deselect it", and the hook selects by marker.

### 12. The psycopg leg is new classes beside the asyncpg ones; no existing class is parametrized and no existing node id changes.

`TestPostgresPsycopgConformance(StorageContract, GrantsContract)` and `TestPostgresPsycopgBulkInsertTransaction` are added to `tests/storage/test_conformance.py`. The two transaction test bodies move into module-level helpers that take the URL variable, the file's own convention (`_purge_sweeps_a_mid_purge_rival(env_var)`, `tests/storage/test_conformance.py:391`, `:453`), and both classes call them. This departs from the source, which parametrizes the two existing classes: parametrizing renames every existing Postgres node id, and [the battery split](../2026-11-25-the-conformance-battery-is-split-by-kernel-operation-with-no-test-lost/spec.md) compares collected node ids line for line.

Basis: decided in drafting, because the file already holds one class per leg (`tests/storage/test_conformance.py:181-188`, `:242-258`) and a sibling unit pins the collected ids.

### 13. The psycopg conformance class runs on an engine vfs builds from the `postgresql+psycopg://` URL; the 10,000-file write and its asyncpg twin run through a borrowed session factory.

The contract's helpers read the built engine (`host.engine.sync_engine`, `tests/support/grants_contract.py:1359`), and a borrowed host refuses that read (`engine.py:259-264`), so the grants contract's statement-counting tests cannot run on a borrowed host on any engine today. The borrowed construction is the one the memo's host uses, so the scale test takes it. `tests/support/server_schemas.py` gains `borrowed_server_storage(env_var, **options)`, an async context manager that makes the per-test schema, builds an engine and an `async_sessionmaker(engine, expire_on_commit=False)`, yields the storage and the engine, and on exit closes the storage, disposes the engine and drops the schema.

Basis: decided in drafting, because the roadmap's line names a `postgresql+psycopg://` leg for the contract, the title names a session factory for the write, and the contract's own helpers settle which construction can carry which.

### 14. The psycopg conformance class skips the engine-proof batteries and builds no plan store.

It sets `engine_proven_by = "TestPostgresConformance"` and leaves `plan_backend` at `None`, as the in-memory leg does for SQLite (`tests/storage/test_conformance.py:61-78`). The three scope-channel batteries and the plan pins judge the server's answers and plans for statements spelled with literal values (`tests/support/plan_store.py:14-20`), which a driver does not change, and the plan store is a 50,000-file build. The `plan_store` fixture's skip message (`tests/support/storage_contract.py:1414-1416`) names the in-memory backend; it is reworded to name `engine_proven_by`, so it is true on both legs that use it.

Basis: decided in drafting, because the tree already has a leg that re-runs a proven engine and skips exactly these (`tests/support/storage_contract.py:281-285`, `:1405-1418`).

### 15. The psycopg leg is a driver leg: it is not added to `ENGINE_LEGS`, and the other Postgres-only tests stay on asyncpg.

`ENGINE_LEGS` is "one leg per server engine" (`tests/support/server_schemas.py:59-65`) and parametrizes engine facts. The psycopg leg runs the contract, the two transaction facts and the 10,000-file write; the rival, cascade, ranking and audit classes (`tests/storage/test_conformance.py:374` onward) prove the server and run once.

Basis: decided in drafting, because the source's section 5 names only the contract and the bulk-insert transaction class for the second driver.

### 16. The dialect workflow gains a fifth matrix row, `postgres-psycopg`, with three keys that default to `dialect`.

The row is `dialect: postgres-psycopg`, `service: postgres`, `extra: postgres`, `marker: postgres_psycopg`, `env_var: VFS_TEST_POSTGRES_PSYCOPG_URL`, `url: "postgresql+psycopg://vfs:vfs@localhost:54320/vfs"`. The start step uses `${{ matrix.service || matrix.dialect }}`, the install step `${{ matrix.extra || matrix.dialect }}` and the pytest step `-m ${{ matrix.marker || matrix.dialect }}`, so the four existing rows are untouched. A job of its own keeps the per-leg pass count the roadmap's story D6 asks for, and it runs beside the asyncpg job on the same image.

Basis: decided in drafting, because one job per leg is the workflow's existing shape (`.github/workflows/test-dialects.yml:33-48`) and exporting two URLs into the Postgres job would double its serial run and merge two counts.

### 17. A contract test that is red on psycopg 3 and green on asyncpg is fixed where its statement is built, by typing the bind in SQL; no code outside `bulk_insert_mode` reads the driver's name.

asyncpg's dialect casts every bind and psycopg 3 leaves an untyped bind to the server's inference, so a statement can be correct on one and refused on the other. The sweep in the problem found no such case over fifteen verbs; the full contract has not run on psycopg 3 (INFERRED that it may find one). A fix of this kind adds an explicit type and changes no result on asyncpg. A failure whose fix would change what a statement does on asyncpg is reported in the Landing notes and held for a ruling, and the pull request does not open until every criterion below is met.

Basis: decided in drafting, because decision 1 makes one function the only place a driver is named, and the tree already casts in SQL where a driver's own typing lost data (`tests/storage/test_conformance.py:340-342`).

### 18. The engine-leg skill and `docker/README.md` carry the second URL beside the first.

`.claude/skills/db_test/SKILL.md` gains the `VFS_TEST_POSTGRES_PSYCOPG_URL` command with `-m postgres_psycopg` in its test section and a fifth line in its concurrent block; `docker/README.md` gains the same command and a row in its engine table. Both state that the two Postgres legs share one container and that `--extra postgres` installs both drivers.

Basis: the source spec, section 5 and its scope list; still true at `9daedd2b` (one Postgres command at `.claude/skills/db_test/SKILL.md:79` and `:119`, `docker/README.md:29` and `:55`).

## Intent

After this spec, a host application on Postgres can hand vfs the session factory it already has, whatever async driver its engine uses: on asyncpg a bulk insert still streams a binary `COPY`, and on psycopg 3 the same mount serves every verb, with a 10,000-file `write` landing in one call through SQLAlchemy Core instead of refusing `vfs.unavailable` on its first `mkdir`. `pip install "vfs-py[postgres]"` installs both drivers, `storage._host.bulk_insert_mode` says which path a mount takes, and the conformance contract runs on both drivers in CI, so a change that breaks either one is seen on the pull request that makes it.

## Design

The order of work is the order of the numbered steps. Each test is written and seen failing before the code that passes it.

1. **The leg table's tests.** New file `tests/test_engine_legs.py`, three tests: `test_every_engine_marker_is_registered` (each key of `tests.conftest.ENGINE_URLS` is a marker name in `pyproject.toml`'s `markers`, read with `tomllib`); `test_the_dialect_workflow_runs_one_job_per_engine_marker` (the matrix of `.github/workflows/test-dialects.yml`, read with PyYAML, a declared dependency at `pyproject.toml:39`, yields pairs of `marker or dialect` and `env_var` equal to each `ENGINE_URLS` key with its first variable); `test_a_leg_is_deselected_when_only_another_legs_url_is_set` (with only `VFS_TEST_POSTGRES_URL` in the environment, `_engine_leg_without_url` is true for an item marked `postgres_psycopg` and false for one marked `postgres`, and the reverse with only the psycopg variable). Seen failing: the second leg is in none of the three places.
2. **The leg table.** `pyproject.toml`: the `postgres` extra becomes `["asyncpg>=0.29", "psycopg[binary]>=3.1", "pgvector>=0.3"]` and `markers` gains `"postgres_psycopg: conformance leg against a real PostgreSQL server on psycopg 3 (VFS_TEST_POSTGRES_PSYCOPG_URL)"`; `uv.lock` is regenerated by `uv sync --all-extras --group dev`. `tests/conftest.py`: the `ENGINE_URLS` entry of decision 11. `.github/workflows/test-dialects.yml`: the row and the three expressions of decision 16. Step 1 passes.
3. **The leg's tests.** `tests/support/server_schemas.py`: `borrowed_server_storage` (decision 13). `tests/support/storage_contract.py`: the reworded skip message (decision 14). `tests/storage/test_conformance.py`: the two helper functions and the two new classes (decision 12, marked `postgres_psycopg`), and two module-level tests marked `slow`, `test_a_ten_thousand_file_write_through_a_borrowed_psycopg_factory_lands_through_core` (marked `postgres_psycopg`) and `test_a_ten_thousand_file_write_on_asyncpg_copies_one_call_per_page` (marked `postgres`). Both write `Entry(path=Path(f"/lake/d{i // 500:02}/r{i:05}.json"), ...)` for `i` under 10,000 with `parents=True`, the shape of the tree's SQLite batch pin (`tests/storage/database/test_dialects.py:659-661`), and both count insert pages with a `before_cursor_execute` listener on the borrowed engine, matching the schema-qualified table name. The asyncpg test records `COPY` calls without importing a driver: it wraps `AsyncConnection.get_raw_connection` so that the object it returns carries a `driver_connection` whose `copy_records_to_table` appends the table, the column list and the record count and then awaits the real method. No test module imports `asyncpg` or `psycopg`: a leg's job installs one engine's extra, and a top-level driver import would break collection on the other legs. Seen failing on the psycopg leg at the present code: the first mutation refuses `vfs.unavailable` (the problem, EXECUTED); the asyncpg test fails on the missing host property.
4. **The unit tests.** `tests/storage/database/test_dialects.py`: new class `TestBulkInsertMode` with `test_copy_is_taken_only_on_the_asyncpg_driver` (the Postgres profile with SQLAlchemy's asyncpg dialect gives `"copy"`; with `PGDialectAsync_psycopg()` and with a dialect whose `driver` is any other name gives `"core"`) and `test_a_profile_that_prefers_another_mode_keeps_it_on_any_driver` (each of `SQLITE`, `MARIADB`, `MSSQL`, `ORACLE` and `GENERIC` returns its own `bulk_insert` for two driver names); in `TestBulkInsert`, `test_a_copy_profile_on_another_driver_inserts_through_core` (SQLite with the profile pinned to `"copy"` and the driver left as aiosqlite: the rows land, `AsyncConnection.get_raw_connection` is awaited zero times and `exec_driver_sql` sees no `SELECT 1`). `tests/storage/database/test_engine.py`: new class `TestBulkInsertMode` with `test_the_host_reports_the_mode_its_driver_takes` (a SQLite host reports `"driver"`; with the profile pinned to `"copy"` it reports `"core"`). Seen failing: the import of `bulk_insert_mode`, an `AttributeError` from the aiosqlite connection, and the missing property.
5. **The code.** `src/vfs/storage/backends/database/dialects.py`: `_COPY_DRIVER` (decision 4), `bulk_insert_mode` (decisions 1 to 3; a docstring and a body of one conditional), the one-line change in `bulk_insert` (decision 1), and two docstrings: the `bulk_insert` paragraph of `DialectProfile` (`:219-229`) says the field is the preferred mode and that `"copy"` is taken only on asyncpg; `bulk_insert`'s own says what the Core branch does on a driver SQLAlchemy does not page for and names the measured fork (decision 6). `src/vfs/storage/backends/database/engine.py`: the property of decision 9 and the import of the function. No comment or docstring names this spec, the source's number or a decision.
6. **The copy stubs.** `TestBulkInsert`'s two copy tests (`test_dialects.py:870-903`, `:940-976`) set the storage dialect's `driver` to `"asyncpg"` with `monkeypatch.setattr` after pinning the mode, through one helper beside `_pin_mode`; their assertions do not change. `test_profiles_pin_the_measured_mode` (`:1074-1085`) does not change: the Postgres profile still prefers `"copy"`.
7. **The words.** `.claude/skills/db_test/SKILL.md` and `docker/README.md` (decision 18).
8. **The gates.** `scripts/ci.sh` (the branch touches `src/`, `tests/` and `pyproject.toml`); `scripts/docs.sh check` (two docstrings under `src/vfs/` change); the five legs, each from fresh containers as the skill directs: `-m postgres`, `-m postgres_psycopg`, `-m mariadb`, `-m mssql`, `-m oracle`. Every command carries a timeout of about twice its estimate.

What the change adds at the reference deployment, by multiplier:

- **The function.** `bulk_insert_mode` is one attribute read and one string comparison per `bulk_insert` call, with no statement, no lock and no structure. A fresh write makes three such calls whatever its size (content, segments, edges; EXECUTED on the 10,000-file write, INFERRED the same for one file), so per file write it is about 3 × 1,050,000 comparisons a day; per index visit it is one per page the build already inserts.
- **asyncpg, SQLite, MariaDB, SQL Server, Oracle, the floor.** No statement changes. The taken mode equals the preferred mode on every one of them (decision 3 and the asyncpg arm of decision 2), so every existing counted pin holds as written.
- **A Postgres driver that is not asyncpg.** Statements that were never issued, because the path refused, are now issued by the existing Core branch. Per `bulk_insert` call there is one single-row `INSERT` whose binds are the table's columns (2 for segments, 3 for content, 14 for versions, EXECUTED from the table definitions), executed once per row by the driver's `executemany`. The statement is constant in the batch size, so no bind budget is approached: the widest is far under SQLAlchemy's declared 32,700 and under the 2,100 floor of the least generous engine, which this path never reaches because only the Postgres profile prefers `"copy"`. The copy branch's page is unchanged: `rows_per_statement(dialect.insertmanyvalues_max_parameters, ...)` through `chunked` (`dialects.py:921`, `:929`).
- **In memory.** SQLAlchemy builds one parameter list as long as the call's rows, beside the caller's own list: the same residency the Core branch has on SQL Server and Oracle today, bounded by what the caller passes. Callers are unchanged.
- **Per batch.** A 10,000-file write on psycopg 3 is 11 entries pages and three `executemany` calls carrying about 40,000 single-row executions (EXECUTED: 10,000, 20,020 and 10,021). With pipeline mode, which psycopg 3.1 and libpq 14 provide and `psycopg[binary]` bundles, those are three pipelined sends and not 40,000 waits; 100 batches a night is about 4,000,000 row executions where asyncpg issues about 500 `COPY` calls. A psycopg built against an older libpq falls to one round trip per row; that is the host's driver build, it is stated in the docstring, and it is what the fork of decision 5 would measure. The cost per row on psycopg 3 is unmeasured; on asyncpg the study read Core's executemany at 8.9 µs a row against `COPY`'s 4.25 (`bulk-inserts.md:15`).
- **Per lock.** No lock is added and none is held longer by design. The Core inserts run in the write's own transaction, as the `COPY` does, and insert new rows that no reader waits on. The transaction is longer by the per-row cost above; it takes no lock another caller needs that the same write does not take on asyncpg.

## Scope

In: decisions 1 to 18. Files: `src/vfs/storage/backends/database/dialects.py`, `src/vfs/storage/backends/database/engine.py`, `pyproject.toml`, `uv.lock`, `tests/conftest.py`, `tests/test_engine_legs.py` (new), `tests/support/server_schemas.py`, `tests/support/storage_contract.py` (one skip message), `tests/storage/test_conformance.py`, `tests/storage/database/test_dialects.py`, `tests/storage/database/test_engine.py`, `.github/workflows/test-dialects.yml`, `.claude/skills/db_test/SKILL.md`, `docker/README.md`.

Out:

- Creating the mount's schema at first touch, and classifying a privilege refusal: [157-1](../2026-11-25-first-touch-creates-the-mounts-schema-and-names-a-privilege-refusal/spec.md). That unit changes no file under `docker/`, the workflow or `pyproject.toml`, so the two share only `tests/storage/test_conformance.py`.
- The `mssql+aioodbc` check for `use_setinputsizes=False` and `install_extensions(path)` on the facade: [157-3](../2026-11-25-a-borrowed-sql-server-factory-is-checked-and-the-facade-installs-extensions/spec.md).
- psycopg 3 in `"driver"` mode, psycopg 3's own `COPY`, and running the bench: a later spec, opened when a bench run on the leg shows a winner (decision 5).
- Paging the Core branch inside `bulk_insert`, and a 10,000-row count pin per verb per engine leg: roadmap story D4, which has no spec ("For each of `mkdir`, `move`, `copy`, `sweep`, `grep` (scoped), `search` (scoped), `grant`, `revoke`, a `slow` test writes 10,000 entries and asserts the verb's statement count equals a named formula beside the test").
- Naming psycopg 3 in the published engine matrix: roadmap story D1, which has no spec ("`README.md` carries one row per `PROFILES` entry plus "any other SQLAlchemy dialect": driver extra, minimum server version, ...").
- Splitting the contract into a package: [the battery split](../2026-11-25-the-conformance-battery-is-split-by-kernel-operation-with-no-test-lost/spec.md). Whichever lands second rebases: this unit adds one leg class and one skip message to files that unit moves.
- A second driver for MariaDB, SQL Server or Oracle, and any driver gate on `"driver"` mode (decision 3).
- A first-touch check or advisory for a psycopg built without pipeline support.
- Running the legs from the published wheel: roadmap story D6.
- A new compose service: both Postgres legs use the one `postgres` service on port 54320.

## Acceptance criteria

1. `bulk_insert_mode` returns `"copy"` for the Postgres profile with SQLAlchemy's asyncpg dialect and `"core"` for the same profile with the psycopg 3 dialect and with a dialect of any other driver name: `tests/storage/database/test_dialects.py::TestBulkInsertMode::test_copy_is_taken_only_on_the_asyncpg_driver`.
2. `bulk_insert_mode` returns each of the SQLite, MariaDB, SQL Server, Oracle and generic profiles' own `bulk_insert` for two different driver names: `tests/storage/database/test_dialects.py::TestBulkInsertMode::test_a_profile_that_prefers_another_mode_keeps_it_on_any_driver`.
3. With the profile pinned to `"copy"` on a driver that is not asyncpg, `bulk_insert` lands its rows, awaits `get_raw_connection` zero times and issues no `SELECT 1` prologue: `tests/storage/database/test_dialects.py::TestBulkInsert::test_a_copy_profile_on_another_driver_inserts_through_core`.
4. With the driver named asyncpg, the copy branch issues one `SELECT 1` and pages three records as calls of two and one under a parameter budget of 14: `tests/storage/database/test_dialects.py::TestBulkInsert::test_copy_mode_streams_records_on_the_raw_connection`.
5. A SQLite host's `bulk_insert_mode` is `"driver"`, and with its profile pinned to `"copy"` it is `"core"`: `tests/storage/database/test_engine.py::TestBulkInsertMode::test_the_host_reports_the_mode_its_driver_takes`.
6. Every key of `ENGINE_URLS` is a registered pytest marker: `tests/test_engine_legs.py::test_every_engine_marker_is_registered`.
7. The dialect workflow's matrix holds exactly one row per `ENGINE_URLS` key, with that key as its marker and the key's first variable as its `env_var`, five rows in all: `tests/test_engine_legs.py::test_the_dialect_workflow_runs_one_job_per_engine_marker`.
8. With only one Postgres leg's URL set, the other leg's items are deselected and that leg's are not, in both directions: `tests/test_engine_legs.py::test_a_leg_is_deselected_when_only_another_legs_url_is_set`.
9. On the psycopg leg the storage and grants contracts report zero failures, and their passed count equals `TestPostgresConformance`'s on the asyncpg leg less the tests that `engine_proven_by` and the absent plan store skip: conformance row `tests/storage/test_conformance.py::TestPostgresPsycopgConformance`.
10. On psycopg 3 a bulk insert issued as a transaction's first statement and rolled back leaves zero rows: `tests/storage/test_conformance.py::TestPostgresPsycopgBulkInsertTransaction::test_a_first_statement_bulk_insert_rolls_back`.
11. On psycopg 3 a duplicate bulk insert under a savepoint raises `IntegrityError` and the outer transaction commits three rows: `tests/storage/test_conformance.py::TestPostgresPsycopgBulkInsertTransaction::test_a_duplicate_under_a_savepoint_leaves_the_transaction_usable`.
12. A 10,000-file `write` through a borrowed psycopg 3 session factory succeeds with 10,000 `created` observations, the host's `bulk_insert_mode` is `"core"`, at least two insert pages are counted against the entries table and at least one against the content table: `tests/storage/test_conformance.py::test_a_ten_thousand_file_write_through_a_borrowed_psycopg_factory_lands_through_core`.
13. The same write through a borrowed asyncpg session factory reports `"copy"`, counts zero insert pages against the content table, and every recorded `copy_records_to_table` call carries at most `rows_per_statement(budget, columns)` records, with at least two calls for the segments table: `tests/storage/test_conformance.py::test_a_ten_thousand_file_write_on_asyncpg_copies_one_call_per_page`.
14. The asyncpg leg's two transaction tests keep their node ids and pass: `tests/storage/test_conformance.py::TestPostgresBulkInsertTransaction`.
15. The MariaDB, SQL Server and Oracle legs report the pass counts they reported before the change, read from the runs recorded in the Landing notes: conformance rows `TestMariaDBConformance`, `TestMSSQLConformance` and `TestOracleConformance` in `tests/storage/test_conformance.py`.

## Landing notes

Filled in when the pull request is opened.

## One line

The bulk insert asks the live dialect which driver it is on, copies only on asyncpg and inserts through Core on any other Postgres driver, and a psycopg 3 leg with its own marker, URL, workflow job and counted 10,000-file write keeps it that way.
