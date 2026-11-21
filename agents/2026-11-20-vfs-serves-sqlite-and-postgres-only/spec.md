# VFS serves SQLite and Postgres only

This spec was written on 2026-11-20 against commit `c42dccd4`, the tip of `write-takes-preconditions-and-an-append`, on the branch `vfs-serves-sqlite-and-postgres-only` cut from it. It was amended on 2026-11-21 after one review, which is answered under "What the review found, and the answer". Nothing is built. Two files in this directory carry what it rests on. `inventory.md` lists every line the drop touches. `research.md` holds the study of the seam between the engines, and it ranks the Postgres-native work this spec leaves to later specs.

## The outcome wanted

VFS is built, tested and documented for two SQL engines, SQLite and Postgres, and for no other. Both are core product. SQLite serves demos and local applications that need a database, and Postgres serves production. MariaDB and the MySQL family, SQL Server and Oracle are no longer supported, so their code, tests, containers, drivers and prose leave the tree. Git history keeps them, and they can come back after 0.1.0 if they are wanted.

The narrowing is temporary and done for one reason: to reach 0.1.0 sooner. Every design that follows is checked against two engines instead of five.

On SQLite and Postgres, no verb changes its behaviour. They issue the same statements as before. Any other SQLAlchemy dialect is still served by the generic floor, as today, and is now told, by a warning, that it is not supported and is fit for testing only.

## Builds on

- The working agreement, `AGENTS.md`: "Production posture", "The reference deployment" and "Tooling".
- The dialect profile design in `src/vfs/storage/backends/database/dialects.py`: facts SQLAlchemy models are read off the live `Dialect`, and only the decisions SQLAlchemy leaves open are declared.
- `InMemoryStorage` in `src/vfs/storage/backends/memory.py`, a subclass of `DatabaseStorage` that only constructs, which is the pattern for landing 3.
- Three branches that are not on `dev` (at `93f3d297`), checked on 2026-11-21. This branch lands after all three and is rebased on `dev` once they have merged.
  - `write-takes-preconditions-and-an-append`, from which this branch is cut.
  - `a-reserved-owner-is-refused-and-vfs-has-a-logger`. It adds vfs's first logger in `src/vfs/authority.py`, under the roadmap's X7 ("one logger, `vfs`, with child names per package"), and its ruling D17: a configuration warning is one `WARNING` record, which the standard `logging` configuration silences. It also writes `documentation/get-started.md`, whose extras already name only Postgres since `d5454ccb`, and a lint test in `tests/lint/test_code_shape.py` that holds those extras.
  - `a-cancelled-call-leaves-its-storage-intact`, which rewrites 92 lines of `engine.py`, where landings 2 and 3 put their code.

## Terms

- **Engine.** A SQL database server or library that vfs stores into: SQLite or Postgres here.
- **Dialect.** SQLAlchemy's name for an engine's SQL and driver behaviour, read as `dialect.name`: `sqlite`, `postgresql`, `mssql`, `oracle`, `mysql`, `mariadb`.
- **Profile.** A `DialectProfile`: the decisions vfs declares for one dialect.
- **Tuned profile.** A profile written for one engine and measured on it. After this spec there are two, `SQLITE` and `POSTGRESQL`.
- **Generic floor.** The profile `GENERIC`, stamped with the dialect's own name, that `profile_for` returns for any dialect without a tuned profile. It serves the core verbs and withholds `search`.
- **Dropped engine.** MariaDB and the MySQL family, SQL Server and Oracle.
- **Arm.** One branch of code that a profile field selects.
- **Engine leg.** The storage contract and the engine-only tests run against one real server in Docker, selected by `VFS_TEST_<ENGINE>_URL`.

## What the code does today

Read and run on 2026-11-20 at `c42dccd4`. "Run" means a command was executed in this checkout.

| Fact | How it is known |
|---|---|
| `PROFILES` holds five tuned profiles: SQLite, Postgres, SQL Server, MariaDB and Oracle. Any other name resolves to `GENERIC`. | Read, `dialects.py:669-688`. |
| On SQLite and Postgres a membership chunk is 32,668 keys. That is SQLAlchemy's 32,700 parameter budget less a reserve of 32. Their own `in_list_budget` (32,766 and 65,535) never binds. Oracle's 1,000 and SQL Server's 2,099 reach neither engine. | Run: the budgets computed for each dialect. Read, `dialects.py:760-767`. |
| `GENERIC` declares 1,700 index-key bytes and 1,000 `IN` elements. Both numbers come from dropped engines: 1,700 is SQL Server's and Oracle's key cap, and 1,000 is Oracle's ORA-01795. | Read, `dialects.py:659-667`, and the field docstring at 175. |
| Four shared values were measured across all five engines and reach SQLite and Postgres: `RELABEL_ROWS` at 50,000 (SQL Server was the slowest engine), `BLOB_PAGE_BYTES` at 8 MiB (half justified by the MySQL packet), `_STATEMENT_BIND_RESERVE` at 8 (for ODBC's wrapper) and `_PATTERN_ARM_CEILING` at 200. | Read, `dialects.py:97-103`, `770-772`, `809-811`. |
| Several statement shapes were written for SQL Server and run unchanged on SQLite and Postgres. They include the embed refusal probe's cast keys, the `CASE` wrappers in trash and indexing, the row-presence probe in place of `SELECT EXISTS`, and keyset pages in place of a cursor. | Read, `embed.py:271-273`, `trash.py:502-508`, `indexing.py:521-528`, `944-957`, `pages.py:6-8`. |
| Ten profile fields are set to a value of their own only by a dropped engine: `row_lock_hint`, `membership`, `like_bracket_class`, `retryable_driver_codes`, `range_entry_hint`, `range_hints`, `value_cap_query` and `value_cap_setting`, and the `hint` and `"table"` forms of `share_lock`. Two more fields are read by nothing at all: `vector_dimension_cap` and `ann_dimension_cap`. | Read, and a grep of every reader was run. |
| The profile is passed as a value into 188 parameters across 31 modules. `DatabaseStorage` reads it itself in only 6 places. | Run, a grep. |
| The profile is resolved once per storage, lazily, in `EngineHost._policy()`. A URL-built storage and a borrowed `session_factory` both reach it before any dialect decision. | Read, `engine.py:563-583`. |
| `src/` has no logger at `c42dccd4`. Its one warning is the once-per-facade `RuntimeWarning` in `sync.py`. The pending logger branch adds `logging.getLogger(__name__)` in `vfs.authority` and logs one `WARNING` for a system default authority. | Read, `sync.py:69-72`, `691-700`; `git show a-reserved-owner-is-refused-and-vfs-has-a-logger:src/vfs/authority.py`. |
| The profile is first resolved when the kernel is built, through `storage.capabilities()` inside `VirtualFileSystem(...)` and `add_mount`, or at a storage's first call when it is used alone. `_policy()` is synchronous and is reached from about 50 sites through the `profile` and `parameter_budget` properties. | Read, `base.py:349`, `432`, `736`; `engine.py:264-275`. |
| A SQLite engine whose dialect instance is renamed resolves to the floor and then fails first touch, `unavailable`, because it loses its SQLite type variants. | Run, in the review. |
| No test runs the storage contract on the generic floor. Its arms are proven by swapping one profile field to the floor's value over SQLite and asserting the same answer, 34 times, and by 19 monkeypatches of the profile, which bypass `_policy()`. | Run, a grep. Read, `tests/storage/database/test_rights.py:275-291`. |
| A MySQL community URL is already served by the generic floor, and it still gets the `LONGTEXT`, `LONGBLOB` and `VARBINARY` type variants, because `_MYSQL_FAMILY` includes `"mysql"`. | Read, `models/rows.py:170-172`. |
| No minimum Postgres version is stated anywhere. The engine leg runs `pgvector/pgvector:pg17`. Nothing checks the pgvector extension's version except the gate for the iterative-scan prelude, at 0.8. | Run, a grep. Read, `docker/compose.test.yml:31`, `backend.py:651`. |
| The dropped engines' share of the tree: about 750 to 900 lines of `src/`, about 1,000 to 1,300 of `tests/`, about 420 of packaging and tooling (six locked packages, three compose services, the ODBC step in CI), about 120 lines of the `db_test` skill, and about 25 sentences of prose, 6 of them in `AGENTS.md`. `crates/` holds nothing engine-specific. | Run: counts by file, an AST count of the marker-scoped tests (339 lines in 37 items), and a `tomllib` read of `uv.lock`. `inventory.md` in this directory lists each item with its lines. |

## The problem

Every change to the database backend is costed, written and tested five times. A spec names the floor of the least generous engine. A review checks every statement against Oracle's `IN` list and SQL Server's bind count. A pull request waits on three server engines, and one of them, SQL Server, does not run on an Apple Silicon laptop without emulation and an ODBC driver.

The cost buys reach that 0.1.0 does not need. It has also bent shared code. Constants, statement shapes and two of the floor's numbers are justified by engines that will not ship. On Postgres, some designs took a worse shape than the engine needs: `research.md` gives the cases.

## Decisions

### 1. Two engines are supported: SQLite and Postgres

`PROFILES` holds `SQLITE` and `POSTGRESQL`. The profiles `MSSQL`, `MARIADB` and `ORACLE` are deleted, with every arm, type variant, driver argument, test, engine leg, compose service, dependency and sentence that serves only them.

Reason: the goal is 0.1.0, and these are the engines it ships on. Git history keeps the rest. The tree to restore from is the parent of landing 1's squash commit on `dev`, because a work-branch commit is lost when the branch is squashed and deleted. `inventory.md` lists what was there.

### 2. Every other dialect is served by the generic floor, and logs one warning per storage

`profile_for` is unchanged. A dialect without a tuned profile gets `GENERIC` under its own name, with the same values, arms and capabilities as today. The one narrowing is decision 3's, for the dropped engines' own drivers. Keeping the floor was decided on 2026-11-20, when the goal was set.

New: when a storage resolves a dialect to the floor, it logs one `WARNING` record on the module logger of `engine.py`, `logging.getLogger(__name__)`, which is `vfs.storage.backends.database.engine`.

```python
_UNSUPPORTED_DIALECT: Final = (
    "vfs does not support the %r SQL dialect: it is served the generic floor, without search,"
    " and is fit for testing only. vfs supports SQLite and Postgres."
)
```

- **Where.** In `EngineHost._policy()`, in the branch that resolves the profile, when `profile.name not in PROFILES`, after the profile and dialect are cached. This is the one place that both a URL-built storage and a borrowed `session_factory` reach.
- **How often.** `_policy()` resolves once per host and never again, so the record is logged once per storage with no latch of its own. Two storages on the same dialect log two records.
- **When.** When the profile is first resolved. For a mounted storage that is inside `VirtualFileSystem(...)` or `add_mount`, through `storage.capabilities()`. For a storage used alone it is at its first call.
- **Not in `profile_for`.** `bulk_insert` calls `profile_for` again on every batch (`dialects.py:914`), so a record there would repeat.
- **No new public name.** The logger's name is public surface under X7, as `vfs.authority`'s is.

Reason for the floor: it costs little to keep and lets a person try vfs on an engine it does not support. The warning stops that from being mistaken for support.

Reason for `logging` rather than `warnings`: D17, decided on 2026-11-20 on the logger branch, rules that a configuration warning is one `WARNING` record that the standard `logging` configuration silences, and X7 gives vfs one logger tree. One channel for every configuration warning is simpler for a host than two. vfs adds no handler, so a host that configures no logging still sees the record through Python's last-resort handler. `warnings.warn` with a public category was the first draft's choice. It was dropped because it would be a second channel and a new public type for one message.

### 3. The dropped engines get no refusal and no promise

A `mariadb://`, `mysql://`, `mssql://` or `oracle://` URL is an unknown dialect like any other. It resolves to the floor and draws the warning. Their type variants and driver error-number classification are deleted with their profiles.

- Expected result: provisioning probably fails on Oracle, which has no `BINARY` type. It probably fails on the MySQL family, whose 64 KB `TEXT` and `BLOB` and 3,072-byte key cap are below what vfs builds. On SQL Server, text other than Latin is probably mangled. This was inferred from compiling the plain types on each dialect, not run.
- A MySQL community URL loses the `LONGTEXT`, `LONGBLOB` and `VARBINARY` variants it gets today. That is a change for an unsupported dialect, and it is accepted.
- Classification by SQLSTATE stays as it is, including the arm of `_sqlstate_of` that reads a five-character SQLSTATE from `args[0]`. pyodbc reports its SQLSTATE that way, and the arm belongs to no one engine. So any driver that reports a SQLSTATE, by attribute or by pyodbc's convention, is classified as today: `40001` and `40P01` retry, and `23505` is a unique violation.
- The integer error numbers of the MySQL family and python-oracledb go: `_driver_code_of`, `_DRIVER_UNIQUE_CODES` (1062 and ORA-00001), `_MSSQL_UNIQUE_NUMBERS` (2627 and 2601), the errno rungs of `is_unique_violation` and `is_value_too_large`, and `_MYSQL_PACKET_TOO_LARGE` (1153). This narrows the floor for those drivers, as the type variants do. A MySQL-family or Oracle unique violation, and a MySQL packet too large, are no longer recognised by number on the floor. Retry is unchanged: the floor's `retryable_driver_codes` is already empty, so it never retried by number.
- What this touches is small. The writes catch `IntegrityError` by class (`writes.py:644`, `733`, `763`), so the floor's `catch_retry` arbitration does not read these numbers. `is_unique_violation` has one caller, `indexing.py:346`.

Reason: keeping half of a dropped engine is the code this spec removes. A refusal by name would be a second list of engines to maintain, and the warning already says what is true.

### 4. Values that a dropped engine set and that reach SQLite and Postgres keep their values. Only the stated reasons change

| Value | Stays at | New stated reason |
|---|---|---|
| `RELABEL_ROWS` | 50,000 | The bound measured safe on every engine vfs has run, kept until it is measured on Postgres alone. `research.md` lists the experiment. |
| `BLOB_PAGE_BYTES` | 8 MiB | Every engine holds the page in client memory. |
| `_STATEMENT_BIND_RESERVE` | 8 | Room under the bind cap for a driver's own parameters. |
| `_PATTERN_ARM_CEILING` | 200 | The gain from more arms in a statement stops at about 200, and 200 clears SQLite's expression depth of 1,000. |
| `GENERIC.key_byte_budget` | 1,700 | The tightest key cap vfs has met. |
| `GENERIC.in_list_budget` | 1,000 | The tightest `IN` list vfs has met. |

Reason: a changed value changes chunk sizes, and so the statements issued on SQLite and Postgres. That breaks the outcome this spec promises. A value that is wrong for Postgres is changed by its own spec, after a measurement.

### 5. Statement shapes written for SQL Server stay in this spec

The shapes listed under "What the code does today" keep their SQL and lose only the comments that name SQL Server. The schema keeps the column name `version_number`, the explicit `Identity()`, the root's `name="/"` and the surrogate key of `vfs_grants`, so `SCHEMA_FORMAT_VERSION` stays at 27.

Reason: changing any of them changes statement text or the schema, which this spec does not do. `research.md` lists them for later.

### 6. The profile loses what only a dropped engine reached. What the generic floor or a later Postgres arm needs stays

**Deleted.**
- The fields `row_lock_hint`, `membership`, `like_bracket_class`, `retryable_driver_codes`, `range_entry_hint`, `range_hints`, `value_cap_query` and `value_cap_setting`.
- The dead fields `vector_dimension_cap` and `ann_dimension_cap`.
- The types and constants `MembershipForm`, `RangeHints`, `NO_RANGE_HINTS`, `ValueCap`, `wire_bytes` and `_ESCAPED_BYTES`.
- The value-cap chain through `engine.py`, `staging.py`, `writes.py` and `backend.py`.
- `vector_native.py`.
- `MSSQL_UTF8_COLLATION`, `_MYSQL_FAMILY`, the `_string` helper, and the dropped variants of `BytewiseString`, `_body_text`, `_body_bytes`, `_timestamp` and `ULIDKey`.
- The dropped arms of `distance.py`, `drivers.py`, `descent.escape_like`, `labels._relabel_opens`, `labels._stamp_under_share`, `ranges.py` and `models/vector.py`.

**Collapsed.**
- `RangeSource` becomes `Literal["json_each", "unnest"]`.
- `ShareLock` keeps the `"row"` and `"exclusive"` forms and `door`.
- `lock_rows` becomes `with_for_update()`.
- `NATIVE_VECTOR_DIALECTS` becomes `{"postgresql"}`.
- `uq_vfs_edges_fs_parent` is emitted on `("sqlite", "postgresql")`.
- `membership()` and `locked_lookup()` keep only the `IN` arm.

**Kept on purpose.**
- `membership(target, keys, profile)` keeps its `profile` parameter. It is the slot for the Postgres array-bind arm that `research.md` ranks first. Removing it would touch about 100 call sites, and the next spec would add them back.
- `arbitration`, `guard_miss`, `tuple_in` and `scope_facts_beside_fan` stay. They exist only to give the floor its arm, and the floor stays.
- `retryable_sqlstates`, `expression_depth_budget` and `relabel_rows` stay as fields, though every profile now holds the same value. Tests override them one at a time, and folding them into constants buys no behaviour.
- `ann_honours_scope` stays. `research.md` finds it does not describe what pgvector does, and the fix is a design of its own, not a deletion.

Reason: the profile then names only decisions that someone still makes, and no field is removed that the next spec needs.

### 7. The Postgres version vfs is tested on is stated, not enforced

The docs and `docker/README.md` state that vfs is tested on Postgres 17 and 18 with pgvector 0.8. The engine leg in CI runs on `pgvector/pgvector:pg17` and `pgvector/pgvector:pg18`. First touch does not check the server version.

How the leg runs on both:
- `docker/compose.test.yml` keeps one `postgres` service, whose image is `${VFS_PG_IMAGE:-pgvector/pgvector:pg17}`. A laptop runs 17 by default, and `VFS_PG_IMAGE=pgvector/pgvector:pg18` runs 18 from the same file.
- The service's tmpfs moves from `/var/lib/postgresql/data` to `/var/lib/postgresql`. From version 18 the official image keeps its data under `/var/lib/postgresql/18/docker`, and the parent directory covers both layouts. This is inferred from the image's documented change and not yet run.
- In `test-dialects.yml` the matrix row carries `image`, besides `dialect`, `env_var` and `url`. Two rows run, `postgres` with pg17 and `postgres` with pg18, under the same marker and extra.
- The pg18 leg is run once, on a laptop or in CI, before landing 1 is called green. That run also runs `SHOW data_directory` and `df` inside the container on both images, to show that the data directory is on the tmpfs. The pg17 image declares `VOLUME /var/lib/postgresql/data`, which may sit over a tmpfs mounted at its parent. If it does, the tmpfs path comes from a second variable, `VFS_PG_DATA`, which keeps `/var/lib/postgresql/data` for 17.

Reason: today nothing states a version, and only 17 is run. Refusing an older server changes behaviour, and `research.md` recommends enforcing a floor of 17 in its own landing, together with the pgvector 0.8 requirement for ANN.

### 8. The working agreement, the skills and the docs say two engines

Each sentence lands with the code it describes. Landing 1 writes everything below except what names the warning or a new class. Item 2's warning sentence and the docs' warning sentence land in landing 2. The class names in the docs land in landing 3.

`AGENTS.md`, in four places:

1. "Never assume SQLite" becomes: "**Design for both engines.** SQLite and Postgres are both core product. SQLite serves demos and local applications, and Postgres serves production at the reference deployment. A design that works only within SQLite's single writer, or only with a Postgres extension, needs a counterpart on the other engine with the same verb results. The caps to design against are the real ones: SQLite's 32,766 variables and expression depth of 1,000, asyncpg's 32,767 bind parameters, and SQLAlchemy's 32,700 parameter budget."
2. "Unknown dialects are served the core verbs, never ranked search" keeps its rule against ranked search. It names the supported engines as SQLite, with sqlite-vec, and Postgres, with pgvector. "Exactly as a tuned engine does" becomes "They are served the core verbs on the generic floor, which no engine leg tests, and are fit for testing only." The sentences about MariaDB, SQL Server 2025, Oracle 23ai and MySQL community go. In landing 2 it adds: "Each storage on the floor logs one `WARNING` saying so."
3. The Engines row of the reference deployment table becomes: "| Engines | Postgres 17 or 18 with pgvector 0.8, tested; SQLite for local and demo use | the caps above are live constraints; an engine outside these two is unsupported |".
4. "Per batch" says: "10,000 rows through chunked builders is one membership statement per table touched at the engines' 32,668-key chunk, and about nine for a 28-column multi-row insert; a round trip per row adds 10,000." The example in "The engine's own reader locks count" loses its SQL Server instance and keeps its rule.

The anecdote in Tooling about the SQL Server leg that hung stays, because it is the reason for that rule.

Skills:
- `db_test` becomes a Postgres-only procedure. It loses Rosetta, ODBC and the SQL Server phantom-container workaround.
- `scale_review` and `spec_review` name the caps from item 1 as the floor.
- `code_review` (its `SKILL.md`, `workflow_template.js` and `check_workflow.py`) and `test_suite` drop the dropped engines' URLs, ports and extras.
- `verify_findings` loses its "a live Oracle" example.

Docs and other prose:
- `README.md:145`, `CONTRIBUTING.md:85`, `documentation/overview.md:121`, `documentation/tutorials/keep-your-files-in-a-database.md:105`, `documentation/explanation/why-vfs-stores-files-in-a-database.md:39` and the two strings in `documentation/images/architecture.svg` say SQLite and Postgres.
- `documentation/get-started.md`, written by the logger branch, already names only the Postgres extra. The lint test that holds its extras is checked against the extras that remain.
- The docstrings that name a dropped engine in about 15 modules are reworded.
- `agents/tasks.md` loses "Run the SQL Server leg", and the task at line 107, on `edit` and the row lock, loses its MariaDB, SQL Server and Oracle cases.

`context/` takes no new work and is not edited.

### 9. The engine leg, packaging and CI carry Postgres alone

- `tests/conftest.py` `ENGINE_URLS` and `tests/support/server_schemas.py` `ENGINE_LEGS` keep `postgres`. The `mariadb`, `mssql` and `oracle` markers leave `pyproject.toml`.
- The extras `mssql`, `mariadb` and `oracle` leave `pyproject.toml`, and `all` stops naming them. `uv lock` drops aioodbc, pyodbc, aiomysql, pymysql, oracledb and cryptography. A read of `uv.lock` on 2026-11-20 found oracledb to be the only package that needs cryptography.
- `docker/compose.test.yml` loses three services and its profile and Rosetta comments. `docker/initdb/mariadb` and `docker/initdb/oracle` are deleted. `docker/README.md` keeps only the Postgres setup.
- `.github/workflows/test-dialects.yml` runs a matrix of Postgres 17 and 18 and loses the ODBC step.
- `tests/support/plan_store.py` keeps the SQLite and Postgres plan readers.

### 10. `SQLiteStorage` and `PostgresStorage` are named constructors over the one storage class

A class for each engine was left open when the goal was set, to be taken if it made sense. The study of the seam, in section 2 of `research.md`, recommends this form, and this spec takes it as landing 3.

```python
from vfs import DatabaseStorage, InMemoryStorage, PostgresStorage, SQLiteStorage

SQLiteStorage(path="knowledge.db")                                     # demos and local apps
InMemoryStorage()                                                      # an SQLiteStorage over :memory:
PostgresStorage(url="postgresql+asyncpg://app@db/vfs", schema="vfs")   # production, an engine vfs builds
PostgresStorage(session_factory=app_sessionmaker)                      # production, a borrowed engine
DatabaseStorage(url="duckdb:///x.db")                                  # the generic floor; logs one warning
```

- Each is a subclass of `DatabaseStorage` that only constructs, as `InMemoryStorage` is today. It carries no verb, no override and no behaviour. Every difference between the engines stays where it is chosen: in the profile, read by the builder functions.
- `SQLiteStorage(path=...)` builds its URL as `sqlalchemy.engine.URL.create("sqlite+aiosqlite", database=os.fspath(path))`, and `EngineHost` accepts a `URL` without turning it into a string. A formatted string would misread a path that holds `?`: `make_url("sqlite+aiosqlite:///notes?v2.db").database` is `'notes'`. `SQLiteStorage(session_factory=...)` borrows. `PostgresStorage` takes `url=` or `session_factory=` and `schema=`. The common arguments of `DatabaseStorage` pass through.
- Each records the dialect name it expects on its host. `_policy()` compares the resolved dialect with that name in its resolving branch. On a mismatch it records the refusal and installs no listener on the engine, so a borrowed SQLite engine is not changed by a `PostgresStorage` that refuses it. `_policy()` is synchronous and is reached from about 50 sites, the first inside `VirtualFileSystem.__init__`, so it cannot return a refusal, and it does not raise.
- One host method returns the recorded refusal. `EngineHost._first_touch` calls it first, before any file setting or extension probe, and so does `install_extensions`, which runs without first touch. The refusal is `unavailable` with `retryable=False`, because the bind will not change. Its message names both dialects, and no further statement is sent. Until first touch, `capabilities()` reports the bound engine's profile, which is what a mismatched storage would serve if it were allowed to.
- `InMemoryStorage` becomes a subclass of `SQLiteStorage`. Its arguments are unchanged.
- `DatabaseStorage` stays public. It is the shared type that signatures name, and the way into the floor. `DatabaseStorage(url="sqlite...")` and `DatabaseStorage(url="postgresql...")` keep working with no warning, so the 505 constructions in `tests/` need not change.
- The docs teach the named classes. The tutorial gains a Postgres construction, which no page teaches today.

Names: the project's noun for the engine is "Postgres" (README, `AGENTS.md`, the extra `vfs-py[postgres]`, the test markers), and PEP 8 capitalises an acronym in a class name, as in `ULIDKey`. So the names are `PostgresStorage` and `SQLiteStorage`. `documentation/maintainers/how-we-name.md` gives one noun per concept.

Reasons for this form:
- **Not behaviour in subclasses.** Almost every difference between SQLite and Postgres is a different statement inside about 30 free builder functions, which receive the profile as a value and never see the storage. A subclass override reaches only the 6 places where the storage reads the profile itself.
- **Not a strategy object.** One would put the 10 remaining selectors behind about 25 methods, a god class from the start. It would also rewrite 188 parameters and 437 test references, and lose the tests that prove each floor arm by changing one field.
- **Django and SQLAlchemy** do use a class for each engine. Their sets of engines are open to third parties, and vfs's set is closed.
- **The subclasses still earn a place.** They give engine-only arguments a home, they let a mismatched bind be refused, and they give the docs a name to teach.

## Where the code goes

| Concern | Owner |
|---|---|
| The two tuned profiles, the floor, `profile_for` | `storage/backends/database/dialects.py` |
| The warning's text and its record | `storage/backends/database/engine.py`, the module logger, in the resolving branch of `EngineHost._policy()` |
| The expected dialect and the mismatch refusal | `storage/backends/database/engine.py`: recorded on the host at construction, checked first in `EngineHost._first_touch` |
| A `URL` accepted as well as a string | `EngineHost.__init__` and `drivers.engine_arguments` |
| `SQLiteStorage`, `PostgresStorage` | a new `storage/backends/sqlite.py` and `storage/backends/postgres.py`, beside `memory.py`, exported from `vfs` and `vfs.storage.backends` |

## Landings

1. **The three engines leave.** This covers decisions 1 and 3 to 9, less the sentences decision 8 assigns to later landings. Statements on SQLite and Postgres are unchanged, and the statement diff under Tests proves it. The floor changes only by decision 3's narrowing for the dropped engines' own drivers.
2. **The floor warns.** Decision 2, and the sentences that describe it.
3. **The named constructors.** Decision 10, the docs that teach them, and the conformance fixtures switched to them.

Each landing is its own pull request to `dev`, squashed to one commit. Landing 1 is then reviewed as a deletion, landing 2 adds one behaviour, and landing 3 adds public API. Each leaves the tree green and is of use alone.

The three branches under "Builds on" land first. This branch is then rebased on `dev` once, before landing 1's pull request. Landing 2 follows D17's channel whether or not the logger branch has merged, since it needs only the standard library. That branch's lint test, which holds X7's logger rule, then covers it.

## Cost

Costed against the reference deployment.

- **Per verb call, per file write, per index visit, per batch, per lock.** Unchanged on SQLite and Postgres, because the statements do not change. The SQL Server collation casts, the Oracle hints and the MariaDB packet meter never ran on those engines.
- **The warning.** One log record per storage on the floor, when its profile is first resolved. On a tuned engine it costs one membership test of a dict, once per storage.
- **The mismatch check in landing 3.** One comparison of two names, once per storage.
- **CI.** The `test-dialects` matrix goes from four legs to two: MariaDB, SQL Server and Oracle leave, and Postgres 18 joins Postgres 17. The SQL Server leg needed an ODBC driver installed on the runner, and Oracle's needed a wait for its first login. Six fewer packages also shorten `uv sync --all-extras` in every job.
- **A developer's laptop.** The engine legs need one container, and no Rosetta, no ODBC driver and no `openssl@3` link.

## Left as it is

Each item is ranked in `research.md` and waits for a spec of its own.

- **Every Postgres-native change.** This includes array binds for membership, the bytewise range in place of the subtree `LIKE`, the pgvector ANN tier, dropping old index epochs as tables, and savepoints taken per row.
- **The SQL Server-shaped statements and schema** of decision 5.
- **Enforcing a Postgres floor** at first touch.
- **`ann_honours_scope`.**
- **Turning the eight checks of an engine name into declared facts**, and moving the roughly 450 SQLite-only lines out of `engine.py` into a module of their own. The study of the seam recommends both. They change no behaviour and are tidying for a later landing.
- **A test of the storage contract on the generic floor end to end.** No engine exists for it to run on. The floor stays proven arm by arm over SQLite.
- **Engine-only construction options** on `PostgresStorage`, such as the pgvector index method, which today sits on `NativeEmbeddingConfig`.

## Tests

Each new test is written and seen failing before the code that passes it. The counts are of calls and statements, never of time.

**Landing 1: proof that nothing changed.**
- **A statement diff.** It is run before the change and after it. It is a verification, run in the autonomous pass, with its result recorded in this spec. It is not a test kept in the tree.
  - The legs: the storage contract and `tests/storage/database/` on the SQLite file leg and on the Postgres leg, with `-n 0`, so that one process records in test order.
  - The recorder: a `before_cursor_execute` listener that keeps, for each test node id, the set of distinct statement texts. In each text, every bind name, savepoint name and literal is replaced by one placeholder, and an expanded `IN (…)` list by one marker. Provisioning DDL is part of the record.
  - Equal: the two runs give equal sets for every node id outside `test_races.py`, and equal sets over the whole run with it.
  - Allowed differences: the node ids that exist in only one run, which are the tests landing 1 deletes, and the node ids of the re-pointed tests, which keep their ids. Both are listed with their differences, and no other difference is allowed.
- The existing suite passes, less the deleted legs and tests.
- `scripts/ci.sh`, `scripts/docs.sh check` and the Postgres engine leg pass, on 17 and once on 18.

**Landing 1: tests that are re-pointed.** None of these loses its case. Where a test used a dropped profile for a field the floor shares, it takes `GENERIC` or `replace(SQLITE, field=...)`. The 100% coverage gate in `scripts/ci.sh` shows that no floor arm lost its only test.
- `test_reads.py:1176` and the docstring at `test_grep.py:1707` use SQL Server's 2,099-parameter budget to force tight chunks. They switch to a made-up budget, as `test_dialects.py:541` already does.
- `test_search.py:571-584` uses `MSSQL` both for its budget and for `tuple_in=False`. It switches to a made-up budget and `replace(SQLITE, tuple_in=False)`.
- `test_grep.py:1441` parametrises `[SQLITE, MSSQL]` to prove the bracket-class escape. Its `MSSQL` row leaves with `like_bracket_class`.
- `test_coherence.py:442-476` uses `MARIADB` as the profile that redrives. It switches to `replace(SQLITE, guard_miss="redrive")`.
- Each test whose parameter list includes a dropped profile keeps its `SQLITE`, `POSTGRESQL` and `GENERIC` rows.

**Landing 1: new tests.**
- `profile_for("mysql")`, `profile_for("mariadb")`, `profile_for("mssql")` and `profile_for("oracle")` each return the floor, stamped with that name.
- `PROFILES` holds exactly `sqlite` and `postgresql`.
- A driver error whose `args[0]` is `40001` is retryable on `GENERIC`, and a bare `23000` reads as no unique violation. Together they pin the arm decision 3 keeps.

**Landing 2: the warning.** Each test records with `caplog` on the engine module's logger.
- A storage over a bind whose dialect name is unknown logs one `WARNING` when `storage.capabilities()` is first read, and none on the second to tenth read. The test makes a SQLite engine and gives its dialect instance an unknown `name`, so that `_policy()` runs and is not patched around. That storage then fails first touch, because it loses SQLite's type variants, so the test counts records and calls no verb.
- Two such storages log two records.
- The record's message names the dialect.
- A SQLite storage and a Postgres storage log no record from this logger. The Postgres check is a row of the engine leg.

**Landing 3: the named constructors.**
- `SQLiteStorage(path=tmp)` round-trips a write and a read, and so does a path that holds `?`. `InMemoryStorage()` is an instance of `SQLiteStorage`.
- `PostgresStorage(url=...)` passes the storage contract. The conformance fixtures construct the named classes.
- `SQLiteStorage(session_factory=<postgres factory>)` and `PostgresStorage(session_factory=<sqlite factory>)` are refused as `unavailable`, not retryable, at their first verb call and at `install_extensions()`. The refusal names both dialects. The statement recorder sees no statement after the refusal, and the borrowed SQLite engine carries no listener vfs added. The Postgres half runs on the engine leg.
- Neither class logs the warning.

## Scope

In scope: `src/`, `tests/`, `pyproject.toml`, `uv.lock`, `docker/`, `.github/workflows/`, `.claude/skills/`, `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `documentation/`, `agents/tasks.md`.

Out of scope: `context/`, which takes no new work, and `crates/`, which holds nothing engine-specific. Also out of scope is every change ranked in `research.md`.

## What the docs must say

- **Overview and tutorial, landing 1.** VFS runs on SQLite and Postgres. SQLite is the database for a demo or a local application, and Postgres the database for a shared deployment.
- **Postgres requirements, landing 1.** Version 17 or 18, tested, with pgvector 0.8 installed by a role that may create extensions. vfs proves the extension and never creates it.
- **`DatabaseStorage`, landing 2.** It serves any SQLAlchemy URL. A dialect other than the two is served the generic floor, is withheld `search`, and logs one warning on the `vfs.storage.backends.database.engine` logger.
- **Reference and tutorial, landing 3.** `SQLiteStorage` and `PostgresStorage` each get an entry, and the tutorial shows both constructions.

## Earlier decisions this reverses

- The posture that production runs on "Postgres, SQL Server, Oracle, and other SQLAlchemy-compatible engines", and that the tightest engine's caps are the design floor (`AGENTS.md`, "Production posture").
- MariaDB as a supported dialect with native vectors, which `AGENTS.md` records.
- The SQL Server and Oracle rows of the reference deployment's Engines row.
- The 0.1.0 promise in `context/standards/roadmap.md` section 1.1, "SQLite, Postgres, SQL Server and Oracle, with MariaDB served as a second tier", and its items D1, D3, D5, D6 and D18, which are 0.1.0 gates for those engines. They are void for the dropped engines. The roadmap is not edited, because `context/` takes no new work, and its migration to `documentation/` carries the change.
- The decision copies under `tests/fixtures/ranking/vfs_native/corpus/context/decisions/` that assume five engines are fixture text, not live decisions, and are not edited. They are a ranking corpus.

## What the review found, and the answer

One fresh reader read the first draft on 2026-11-20, and its record is `review.md` in this directory. It found that landing 1's promise holds: every deleted arm is selected only by a dropped profile's value or name, and chunks stay at 32,668 on both engines. The verdict was "Not yet", for two High and five Medium findings. Each is answered here.

- **H1, the mismatch refusal sat in `_policy()`, which cannot refuse.** Taken: the check runs first in `_first_touch` and returns `unavailable`, and `_policy()` only records the expected name (decision 10).
- **H2, two rulings of the roadmap were reversed unnamed.** Taken: the 0.1.0 promise and its gates are named above. The warning now follows D17 and X7 as one `WARNING` log record, and `UnsupportedDialectWarning` is withdrawn (decision 2).
- **M1, deleting the pyodbc SQLSTATE arm changed the floor.** Taken in part. The arm stays, because it belongs to no engine. The errno rungs of the MySQL family and Oracle go, and decision 3 says what that narrows. The false sentence about `catch_retry` is corrected.
- **M2, the statement diff was not specified enough to give one answer.** Taken: the recorder, its normalisation, `-n 0`, the treatment of `test_races.py` and the allowed differences are stated.
- **M3, landing 1 described landing 2's warning.** Taken: each sentence of decision 8 and each docs item is assigned to a landing.
- **M4, two pending branches were unnamed.** Taken: "Builds on" names all three with the order of landing. `documentation/get-started.md` and its lint test are in decision 8.
- **M5, the Postgres 18 leg had no mechanism.** Taken: an image variable, the tmpfs moved to `/var/lib/postgresql`, and an `image` key in the matrix (decision 7).
- **L1 to L11.** All taken, in this order:
  - L1, L2 and L4 by the move to `logging`, with no latch and a test through `capabilities()`.
  - L3 in decision 2's "When".
  - L5 in the re-pointed tests.
  - L6 in decision 1.
  - L7 and L9 in decision 8.
  - L8 in decision 10.
  - L10 in decision 8.
  - L11 in Landings.

A second reading on 2026-11-21 found every finding closed, except M5 in part, and gave "Fit to build". It raised five Lows, N1 to N5, and each was taken with its fix text:
- N1 and N2 in decision 10: one refusal method, called by `_first_touch` and `install_extensions`, no listener on a mismatched engine, and `retryable=False`.
- N3 in decision 3 and its pinning test.
- N4 in the statement diff.
- N5, the rest of M5, in decision 7.

## Not checked

- That provisioning fails on the dropped engines once their variants leave. It is inferred from compiled types and was not run.
- The statement diff. It is a step of landing 1, not yet run.
- Postgres 18 on the engine leg, and the tmpfs at `/var/lib/postgresql`. Neither has run.
- Whether `scripts/docs.sh check` passes after the docstring edits.

## The statement diff of landing 1

Run on 2026-11-21, before the change at `5dfdcc79` and after it at `704e7e8a`, with `-n 0` and a recorder that keeps each test's distinct statement texts with every bind, literal, savepoint, schema name and expanded `IN` list replaced by one marker. The statistics pass runs in the background and lands on whichever test is running, so its statements are kept as one set for the whole run; two runs of the unchanged code gave equal records only with that rule.

- **Postgres 17 leg** (`-m postgres`, 506 tests): 507 records before and 507 after, none in only one run, none differing. `test_races.py` equal over the whole run.
- **SQLite file leg** (`TestSqliteConformance` and `tests/storage/database/`, about 2,020 tests): no record that exists in both runs differs, and `test_races.py` is equal over the whole run. Five records exist only before: the three value-cap tests landing 1 deletes, and the old names of two re-pointed tests. Two exist only after: those two new names. `test_a_wide_ext_filter_beside_the_widest_group_stays_inside_a_tight_budget` sends the same set as its old name. `test_a_partial_read_issues_the_profiles_range_settings` sends the same set less one comment, `/* visible vfs_lex_docs ix_vfs_lex_docs_entry */`, a derived hint the old test put on the profile and that no profile declares.
- Two tests of `TestWhereAnAttemptRuns` fail under the recorder in both runs and pass without it: they count an engine's listeners, and the recorder adds one.

The Postgres server was a container started again, not created fresh, for both runs; the comparison is between two runs on that one server.

## Choices to confirm

Confirmed on 2026-11-21: choices 1, 2 and 4 stand as written. Choice 3 is not yet confirmed.

Since this spec was written, `DatabaseStorage(session_factory=...)` was removed by the branch `a-cancelled-call-leaves-its-storage-intact`, and a storage always builds its own engine from `url=` and `engine_arguments=`. Decision 10's borrowed-engine example and landing 3's mismatch tests name `session_factory=`. Before landing 3 is built they are recut: the mismatch is a URL of the other engine, such as `SQLiteStorage(url="postgresql+asyncpg://...")`, refused with both dialects named. Landings 1 and 2 are unaffected.

1. **The warning is a `logging` record, not a Python warning.** D17 and X7 give the reason. The other choice is `warnings.warn` with a public `UnsupportedDialectWarning`, which a caller filters by category, at the price of a second channel and a new public type.
2. **The dropped engines resolve to the floor with the warning**, and are not refused by name. Decision 3 gives the reason.
3. **The tested Postgres versions are stated but not enforced** in this spec. Decision 7 gives the reason.
4. **Landing 3 is in this spec.** The other choice is to land the drop alone and give the named constructors a spec of their own.

## One line

VFS keeps SQLite and Postgres, deletes the three other engines without changing a statement on the two it keeps, logs one warning for any other dialect saying it is fit for testing only, and names the two engines with `SQLiteStorage` and `PostgresStorage`.
