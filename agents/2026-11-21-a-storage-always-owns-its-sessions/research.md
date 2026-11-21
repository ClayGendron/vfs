# A storage already owns every session it runs, the handed session factory can go, and a URL alone is not enough to build the engine it owns

This memo answers one question, asked on 2026-11-21: is it sound to remove `session_factory=` from `DatabaseStorage` and have a storage always own its session factory, its engine and its pool, on the reasoning that VFS sessions are never shared with the application and that VFS owns a whole schema and scopes its connections to it. It was written in one sitting on 2026-11-21. The VFS source was read, ten experiments were run on SQLite and on SQLAlchemy with no server, source and documentation were read in 38 fresh shallow clones, and issue threads were read on the web. The question was asked to be tested, not endorsed, so each section looks for what breaks. A memo decides nothing; a spec decides.

Every claim carries a label. EXECUTED means a command ran here and the claim reports its output. READ means the claim was seen in a file or page that is cited. INFERRED means reasoning from the two.

## The answer in one paragraph

The proposal is two claims, and they do not stand or fall together. The first claim is that a storage owns its sessions and its transactions. That is already true: a handed storage opens a session of its own for every attempt, and a write it made stayed after the application rolled its own transaction back. No peer takes a session factory, and the one project that offers the hook calls it highly discouraged. The handed form also changes the application's engine on SQLite, leaves nine caveats documented, and is the reason for 61 collected tests. So removing `session_factory=` is sound. The second claim is that a storage therefore owns its engine and pool, built from a URL. That does not follow, and as literally stated it breaks four things: a pool cannot be sized or turned off, asyncpg cannot run behind PgBouncer in transaction mode, a token that expires cannot be supplied, and a thousand storages on one database become a thousand pools. Every peer that owns its connections to a server accepts engine or pool arguments beside the URL, and three of them carry a separate way to supply a token. The proposal holds under three conditions: the constructor takes engine keyword arguments, the engine is reachable for listeners, and several storages on one database can share one engine that VFS made. "Scoped to its schema" is sound as schema-qualified names, which VFS already renders on the four server engines, and a role limited to the schema. It is not sound as a `search_path` set on the session: the poolers drop it or leak it, and pgvector's operator is found through it.

## Sources

VFS at `3d02c89` on branch `a-cancelled-call-leaves-its-storage-intact`, read on 2026-11-21. Every `src/vfs` and `tests` citation below is at that commit.

Each clone was made on 2026-11-21 as a shallow clone of the upstream default branch, beside the checkout, so each is at its upstream head on that day. None was modified, and no code was copied from any of them. A clone marked sparse holds only the paths read.

| Clone | Commit | Date | Licence | Extent of the clone, and what was read |
|---|---|---|---|---|
| `alembic` | `1bcba93` | 2026-10-27 | MIT | Whole clone. The files cited below. |
| `apscheduler` | `a37e6c9` | 2026-11-18 | MIT | Whole clone. The files cited below. |
| `celery` | `a2d470f` | 2026-11-19 | BSD-3-Clause | Whole clone. The files cited below. |
| `optuna` | `0abf066` | 2026-11-18 | MIT | Whole clone. The files cited below. |
| `mlflow` | `7da49e7` | 2026-11-21 | Apache-2.0 | Sparse: `mlflow/store`, `mlflow/tracking`. |
| `prefect` | `5513abc` | 2026-11-20 | Apache-2.0 | Sparse: `src/prefect/server/database`, `src/prefect/settings`. |
| `dagster` | `939bd1e` | 2026-11-20 | Apache-2.0 | Sparse: `dagster-postgres`, `_core/storage`. |
| `airflow` | `a58f636` | 2026-11-21 | Apache-2.0 | Sparse: `config_templates`. |
| `sqlalchemy-continuum` | `3d3c86b` | 2026-10-15 | BSD | README only. |
| `sqlalchemy` | `4917592` | 2026-11-19 | MIT | Documentation and dialect docstrings. The installed 2.0.52 is what ran. |
| `langgraph` | `c6335a4` | 2026-11-20 | MIT | `libs/checkpoint-postgres`, `libs/checkpoint-sqlite`. |
| `langchain-postgres` | `9afb650` | 2026-10-29 | MIT | Whole clone. The files cited below. |
| `llama_index` | `99d7433` | 2026-11-13 | MIT | Sparse: the Postgres vector store. |
| `openai-agents-python` | `6c4e4a2` | 2026-11-20 | MIT | `extensions/memory/sqlalchemy_session.py`. |
| `adk-python` | `f578fcd` | 2026-11-20 | Apache-2.0 | `sessions/database_session_service.py`. |
| `mem0` | `fff8a64` | 2026-11-18 | Apache-2.0 | The pgvector configuration. |
| `chroma` | `1a3ac2c` | 2026-11-06 | Apache-2.0 | Sparse: `chromadb/db`. |
| `letta` | `8816d3a` | 2026-10-18 | Apache-2.0 | Not read: the server is no longer on the default branch. |
| `oban` | `a1b7d9a` | 2026-11-17 | Apache-2.0 | `lib/oban.ex`, the guides. |
| `river` | `1f19003` | 2026-11-14 | MPL-2.0, studied only | `client.go`, `docs/README.md`, `CHANGELOG.md`. |
| `pg-boss` | `f2bfc23` | 2026-11-20 | MIT | `docs/api`. |
| `graphile-worker` | `b4f1b41` | 2026-11-05 | MIT | `website/docs`. |
| `good_job` | `c51be9f` | 2026-11-14 | MIT | README. |
| `solid_queue` | `b9c646a` | 2026-11-03 | MIT | README. |
| `que` | `57cfa4a` | 2026-09-08 | MIT | README, `docs/README.md`. |
| `procrastinate` | `98be035` | 2026-11-21 | MIT | The connector and the production how-to pages. |
| `hangfire` | `8bedc72` | 2026-10-30 | Multi-licensed, LGPL-3.0 among the choices; studied only | Sparse: `src/Hangfire.SqlServer`. |
| `quartz` | `741ccc3` | 2026-09-28 | Apache-2.0 | The two JDBC job store classes. |
| `juicefs` | `23d2a45` | 2026-11-20 | Apache-2.0 | `pkg/meta/sql.go`, the metadata engine page. |
| `seaweedfs` | `afdb32d` | 2026-11-21 | Apache-2.0 | Sparse: `weed/filer`. |
| `lakefs` | `bb048e4` | 2026-11-19 | Business Source Licence 1.1, studied only | `pkg/config`. |
| `supabase-storage` | `c0d596a` | 2026-11-20 | Apache-2.0 | `src/internal/database`. |
| `supabase-auth` | `10ef107` | 2026-11-17 | MIT | The configuration. |
| `keycloak` | `d0284ff` | 2026-11-20 | Apache-2.0 | Sparse: `docs/guides/server/db.adoc`. |
| `pgbouncer` | `b554e3d` | 2026-11-20 | ISC | `doc/config.md`, `NEWS.md`. |
| `pgbouncer.github.io` | `8524727` | 2026-11-03 | ISC | `features.md`. |
| `postgres` | `207b529` | 2026-11-20 | PostgreSQL licence | Sparse: `doc/src/sgml/ddl.sgml`. |
| `cloud-sql-python-connector` | `06437ef` | 2026-11-19 | Apache-2.0 | README. |

Installed packages, in the project's environment: sqlalchemy 2.0.52, aiosqlite, asyncpg, Python 3.13. The experiments ran in a four-core Linux container, and no time below is a measure of anything but order. One experiment added opentelemetry-instrumentation-sqlalchemy 0.66b2 and opentelemetry-sdk 1.45.2 in a throwaway overlay that changed nothing in the project.

Web pages read on 2026-11-21, each cited where it is used: <https://github.com/langchain-ai/langgraph/issues/7345>, <https://github.com/langchain-ai/langgraphjs/pull/838>, <https://github.com/google/adk-python/issues/1397>, <https://github.com/google/adk-python/pull/3565>, <https://github.com/run-llama/llama_index/pull/18507>, <https://github.com/riverqueue/river/issues/345>, <https://github.com/celery/celery/pull/10135>. Each was read through a fetch that summarises, not line by line. Issue titles and dates were also read from GitHub's search listing.

The experiment scripts are kept in the session scratch directory, outside the repository, and are not durable. Each experiment is described closely enough to be written again.

## 1. What a handed storage shares with the application today

### 1.1 The code

- READ. `EngineHost` takes exactly one of `url=` and `session_factory=`. `src/vfs/storage/backends/database/engine.py:187-191`. With a URL it calls `create_async_engine(url, **engine_arguments(url))` and makes its own `async_sessionmaker`. With a factory it holds no engine. `engine.py:216-228`.
- READ. Every verb takes a new session from the factory for each attempt, inside `with_retry`. A read does so at `backend.py:1377-1383`, a mutation at `backend.py:1483-1493`. First touch, the vector probe and the statistics pass do the same, `engine.py:627`, `636`, `669`, `687`, `934`. No verb accepts a session, a connection or a transaction from its caller.
- INFERRED. So what a handed factory shares is whatever the factory is bound to. Bound to an engine, it shares the engine and its pool. Bound to one `Connection`, it shares that connection and the transaction on it. The session and the transaction are never the application's own objects.
- READ. `DatabaseStorage` has seventeen constructor parameters, and `url` is the only one that reaches the engine. EXECUTED: no public attribute of a storage names its engine.
- READ. The README's first database example hands a session factory, `README.md:46-51`, and states the rule at `README.md:125`. The one tutorial that builds a database storage uses the URL form, `documentation/tutorials/keep-your-files-in-a-database.md:21`, and the pages under `docs/` use `InMemoryStorage`. A search of `documentation/` and `docs/` for `session_factory` finds only `documentation/maintainers/cancellation.md`.

### 1.2 Experiment 1: a call does not run in the application's transaction

A file database and one `async_sessionmaker` over one engine. The application made a table of its own, then handed the factory to a `DatabaseStorage`.

- EXECUTED. Inside an open application session that had run a `SELECT`, `storage.write` succeeded and checked one more connection out of the pool. The application then inserted a row and rolled back. Afterwards the application's table held 0 rows and the VFS entry held 1.
- EXECUTED. With the application's session holding SQLite's write lock, an insert not yet committed, `storage.write` called from the same task returned failure after 20.4 s: `Conflict: write kept losing to concurrent changes: a retryable engine conflict outlived 4 attempts`. The task was waiting on a lock that only it could release.
- INFERRED. A handed storage is a second writer beside the application, on the application's pool. It is never a participant in the application's transaction.

### 1.3 Experiment 2: what first touch does to a handed SQLite engine

The same engine, inspected before and after `first_touch()`.

| On the application's engine | Before | After |
|---|---|---|
| Listeners | none of VFS's | one more on `checkout`, one on `begin`, and the attribute `_vfs_sqlite_control` |
| `SELECT 'ABC' LIKE 'abc'` in an application session | 1 | 0 |
| `PRAGMA journal_mode` of the file | `delete` | `wal` |
| `PRAGMA synchronous`, `cache_size` | defaults | 2 (`FULL`), 256 MiB |
| The driver's `isolation_level` | `''`, the implicit `BEGIN` | `None`, with an explicit `BEGIN` from VFS's listener |
| `vec_version()` | no such function | `v0.1.9`: sqlite-vec is loaded into the application's connections |

- EXECUTED. Every row of the table.
- READ. The code says so: the settings are stamped at every checkout, on every connection of the pool, `engine.py:1020-1030`, and the docstring names the explicit `BEGIN` that "other users of that engine see", `engine.py:31-37`. It does not name the change to `LIKE`.
- INFERRED. `PRAGMA case_sensitive_like = ON`, `dialects.py:488`, changes the answer of the application's own queries. The handed form is not read-only toward the application.
- READ. On a server engine VFS installs nothing on the engine: the two listeners are for SQLite only, `engine.py:590-601`. It sets the isolation level of each of its own connections through execution options, `dialects.py:691-719`.

### 1.4 Experiment 3: what every call pays for the handed form

A trace callback on each SQLite connection of a built storage counted the statements of one call.

- EXECUTED. A `stat` sent 11 statements on a file and 10 in memory. Seven of them are the checkout's: six `PRAGMA` settings and one probe for sqlite-vec. A `write` sent 23, the same seven among them.
- READ. They are stamped at checkout and not at connect because "a borrowed pool's pre-existing connections never fire connect", and to re-stamp "state another borrower may have changed". `engine.py:1009-1014`, `1024-1025`.
- INFERRED. On an engine that only VFS uses, the seven statements belong to the `connect` event and are paid once for each connection. This is SQLite only: no server profile declares session settings.

### 1.5 Experiment 4: a factory bound to one connection

The fixture an application's test suite uses: one connection, an outer transaction, a session factory bound to the connection, a rollback at the end. It was run with each of `join_transaction_mode` `create_savepoint`, `rollback_only` and `conditional_savepoint`.

- EXECUTED. On an engine where another storage had already installed VFS's listeners, a `write` and a `stat` succeeded through the bound factory, and the outer rollback removed the row. This is the one way a VFS call runs inside an application's transaction today.
- EXECUTED. On a fresh engine the same fixture is refused at first touch: `sqlite-vec did not load: this interpreter's sqlite3 cannot load extensions`. The message is wrong about the cause. `_policy` installs the SQLite control only when the bind is an `Engine`, `engine.py:590`, so nothing loaded the extension, no setting was stamped, and no `BEGIN IMMEDIATE` was sent.
- EXECUTED. In SQLAlchemy alone, asking a session that is bound to a connection already in a transaction for an isolation level raises `InvalidRequestError: ... isolation_level may not be altered unless rollback() or commit() is called first`.
- READ. VFS pins an isolation level on every op connection on Postgres and MariaDB, `dialects.py:534-535`, `605-608`.
- INFERRED. So the fixture works on SQLite by accident and would raise on Postgres and MariaDB. Not run on a server.
- INFERRED. Inside an outer transaction a VFS commit is a savepoint release. A retry of `with_retry` cannot take a fresh snapshot, and VFS's serialization point is held until the application ends its transaction.

### 1.6 Experiment 5: a handed in-memory engine

`create_async_engine("sqlite+aiosqlite:///:memory:")`, which SQLAlchemy serves through a `StaticPool`, handed as a session factory.

- EXECUTED. One `write` succeeded. Five concurrent `stat` calls all failed: `cannot start a transaction within a transaction`. Of five concurrent `write` calls one succeeded. The same five writes on a built in-memory storage all succeeded.
- READ. The host serializes sessions on one connection only when it built the engine. `engine.py:595`. The defect is recorded at `context/specifications/archive/153-docs-tell-the-truth-about-v2/spec.md:66` and on the cancellation page.

### 1.7 Experiment 6: `schema=` on SQLite

- EXECUTED. A built storage with `schema="tenant"` on a SQLite file is refused at first touch: `unknown database "tenant"`.
- EXECUTED. A handed storage with the same `schema=` works when the application's own `connect` listener runs `ATTACH DATABASE ... AS tenant`.
- INFERRED. On SQLite the handed form is the only way `schema=` means anything today. Under the proposal the file is the schema and the parameter is refused there.

### 1.8 What VFS cannot do or promise on a handed engine

Nine caveats are written down. Each exists only because of the handed form.

| # | Caveat | Where it is written |
|---|---|---|
| 1 | A handed in-memory factory has no turns, so calls collide on the one connection. | `documentation/maintainers/cancellation.md`, "Not covered"; spec 153, line 66; experiment 5. |
| 2 | A handed engine on Python 3.11 keeps the open cursor of a failed statement, and with it the file's side files and a five-second stall. | The cancellation page; `agents/tasks.md:33`. |
| 3 | A session bound to a `Connection` is not refused at each statement after a cancellation. | The cancellation page. |
| 4 | A handed factory over SQLite "is not fully covered" for a cancelled write. | `agents/tasks.md:32`. |
| 5 | The handed path is single-loop: notebooks and sync pipelines must use the built path. | `engine.py:11-13`. |
| 6 | Every other session on the engine is given VFS's explicit `BEGIN`. | `engine.py:31-37`; experiment 2 adds the settings. |
| 7 | Handed connections are never replaced when planner statistics move; they reload at their next write, and a connection that only reads keeps stale statistics. | `engine.py:46-50`, `597-598`. |
| 8 | Driver arguments are the builder's job: `use_setinputsizes=False` on SQL Server, without which non-Latin-1 text is stored as `?`, and the closing connection class on SQLite. | `drivers.py:49-71`. |
| 9 | On Postgres a handed psycopg factory fails at its first bulk insert, because the profile's `COPY` path calls asyncpg's `copy_records_to_table` whatever the driver. | `dialects.py:913-933`; `context/research/2026-10-08-smartowl-workspace-integration-issues.md`, item 20. |

- READ. Every row.
- INFERRED. Caveats 8 and 9 are silent or late failures on server engines: wrong text on SQL Server, a crash at the first batch on Postgres. A built engine has neither, because `engine_arguments` chooses the arguments and the URL names the driver.

### 1.9 The count

- EXECUTED. In `src/vfs` the handed form is named on 32 lines of five files: 22 in `engine.py`, 6 in `backend.py`, 2 in `attempts.py`, and 1 each in `drivers.py` and `dialects.py`. A search for the words finds no other file.
- READ. It is fifteen sites of code: the parameter, the XOR and the `None` engine (`engine.py:179-228`); the `engine` property's refusal (`258-263`); dialect policy deferred to a session's bind, because a handed host cannot know its dialect earlier (`229-232`, `578-603`); the `Engine` check, the `StaticPool` check and the two `self._engine is not None` branches (`590`, `595`, `599`, `567`); the marker that keeps two hosts from installing twice on one bind, checkout in place of connect, and the probe before each load (`1016-1030`, `1068-1075`); the reload for a connection that predates the statistics (`822-837`); the one view per engine and the `Engine` check in `attempts.py`; the pass-through and the two docstrings in `backend.py`; one docstring each in `drivers.py` and `dialects.py`.
- EXECUTED. Thirteen call sites in `tests/` pass `session_factory=`, in five files: `test_engine.py` (8), `test_statistics.py` (2), `test_sqlite_vec.py` (1), `tests/test_offload.py` (1), `tests/support/cancelled_callers.py` (1).
- EXECUTED. Of the collected tests, 59 name the handed or borrowed form: 52 parametrized cases of `tests/storage/test_cancelled_call.py` that run on a handed host, and seven named tests in `test_engine.py`, `test_statistics.py` and `test_sqlite_vec.py`. Two more exist only for it, the XOR refusal and the install-once guard, which makes 61. Four others use the form as a convenience and would be rewritten: two in `TestWhereAnAttemptRuns`, the pool-exhaustion test and one in `test_offload.py`.
- READ. The pool-exhaustion test builds an engine with `pool_size=1, max_overflow=0, pool_timeout=0.2` and hands its factory. `tests/storage/database/test_engine.py:502-507`. INFERRED: it has to, because a built storage's pool cannot be sized.
- READ. Nine documented caveats, in section 1.8.

## 2. What `schema=` is today

- READ. `build_vfs_tables(schema=...)` puts the schema on every table of the family. `src/vfs/models/rows.py:386-404`. EXECUTED: the family is 24 tables and 21 indexes, every one named `vfs_*`, and a statement compiles to `FROM tenant.vfs_meta` on Postgres, SQL Server, Oracle, MySQL and SQLite alike.
- READ. The raw statements are qualified too: `LOCK TABLE` goes through the dialect's `format_table`, `labels.py:540-543`, and `COPY` passes `schema_name=table.schema`, `dialects.py:931-933`.
- READ. A storage assumes one mount for each schema: "The names are fixed ... so one schema holds one mount". `rows.py:397-398`. It verifies its own meta row and never lists or drops what it did not name.
- READ. VFS never creates the schema. A search of `src/vfs` for `CREATE SCHEMA` finds nothing, and the draft at `context/specifications/active/157-postgres-provisioning-for-host-apps/spec.md` proposes it.
- INFERRED. Application tables in the same schema break nothing in VFS unless a name begins `vfs_`. What is shared is the file's settings on SQLite (experiment 2), the database's advisory-lock key space on Postgres, `engine.py:755-760`, and the role's rights.
- INFERRED. With `schema=None` the names are unqualified, and the tables land wherever the connection's default schema points. That is the one case where the connection's scope decides where VFS's data is.

## 3. What the peers do

### 3.1 Python libraries on SQLAlchemy or a driver

| Peer | What it accepts | Schema | The fact that bears on the decision |
|---|---|---|---|
| Alembic | The application's `env.py` builds the engine, or takes a `Connection` placed in `Config.attributes`. | `version_table_schema` | The recipe exists so that "all operations ... proceed along a single transaction". `alembic/docs/build/cookbook.rst:191-231`. |
| APScheduler 4 | `engine_or_url`: a URL or an engine. | `schema=`, created if missing. | It "will not manage the life cycle of any engine instance passed to it". `src/apscheduler/datastores/sqlalchemy.py:154-193`, `406-419`. |
| Celery result backend | A URL, `database_engine_options`, and since 5.7 `database_engine_callback`. | `database_table_schemas`, table names. | The callback was added for "per-connection authentication, such as injecting JWT tokens or using IAM-based auth via a `do_connect` listener". `docs/userguide/configuration.rst:1433-1467`; `celery/backends/database/__init__.py:83-118`. |
| Optuna `RDBStorage` | A URL and `engine_kwargs`. | None. | `skip_table_creation` for a role with no DDL rights. `optuna/storages/_rdb/storage.py:206-262`. |
| MLflow tracking store | A URI. Pool size, overflow, recycle and pool class come from environment variables. | None. | `mlflow/store/db/utils.py:382-423`. |
| Prefect server | A URL, with settings for pool size, overflow and connect arguments. | `search_path`, sent as an asyncpg `server_settings` entry. | `statement_cache_size` 0 "is required behind PgBouncer in transaction mode". `src/prefect/server/database/configurations.py:135-176`, `256-292`. |
| Dagster Postgres storage | A URL, built with `NullPool`. | None. | A token provider registers a `do_connect` hook. `dagster_postgres/utils.py:169-186`. `should_autocreate_tables`. |
| Airflow | A URL, `sql_alchemy_engine_args`, `sql_alchemy_connect_args`, pool settings. | `sql_alchemy_schema` | The hook that takes a session factory is headed "Use of sql_alchemy_session_maker Highly Discouraged" and warns of "data corruption". `config_templates/config.yml:635-766`. |

- READ. Every row.

### 3.2 Storage for LLM applications, the nearest neighbours

| Peer | What it accepts | Schema | The fact that bears on the decision |
|---|---|---|---|
| LangGraph Postgres saver | A psycopg connection or a psycopg pool; `from_conn_string` opens one connection. | None in Python. | A connection made by hand must carry `autocommit=True` and `row_factory=dict_row`, or setup is not persisted and reads raise. `libs/checkpoint-postgres/README.md:37-49`; `aio.py:50-87`. |
| LangGraph SQLite saver | An aiosqlite connection; `from_conn_string`. | The file. | `libs/checkpoint-sqlite/.../aio.py:130-157`. |
| `langchain-postgres` | `PGEngine.from_connection_string(url, **kwargs)` or `PGEngine.from_engine(AsyncEngine)`. One `PGEngine` serves many stores. | `schema_name` on each table, quoted into every statement. | `v2/engine.py:44-113`. |
| LlamaIndex `PGVectorStore` | Connection strings, `create_engine_kwargs`, and since April 2025 `engine=` and `async_engine=`. | `schema_name`, created if missing. | `base.py:295-311`, `501-536`. |
| `openai-agents-python` `SQLAlchemySession` | An `AsyncEngine`; `from_url(url, engine_kwargs)`. | None. | It adds a `connect` listener that sets `busy_timeout` and WAL on a SQLite engine it was given, and it exposes `engine`. `sqlalchemy_session.py:109-137`, `161-166`, `258-283`, `668`. |
| ADK `DatabaseSessionService` | Exactly one of `db_url` and `db_engine`; other keywords go to `create_async_engine`. | None. | SQLite listeners are installed only on an engine it built, and `close()` disposes only an engine it built. `database_session_service.py:386-459`, `1105-1108`. |
| mem0 pgvector | Parameters, a connection string, or a psycopg pool. | None. | `mem0/configs/vector_stores/pgvector.py:16-39`. |
| Chroma, embedded | A directory. It owns the file and a pool of its own. | The file. | In memory it is one connection behind a lock. `chromadb/db/impl/sqlite.py:78-93`. |

- READ. Every row.
- READ. LlamaIndex added the engine form "To allow better control or engine instances and lifetimes". <https://github.com/run-llama/llama_index/pull/18507>, merged 2025-04-23.
- READ. ADK began with a URL alone. A request of 2025-06-14 asked for an engine because the project "requires deep customization of the SQLAlchemy engine": pooling, execution options, event listeners. <https://github.com/google/adk-python/issues/1397>. The change that added `db_engine` was opened on 2025-11-15 and merged on 2026-06-18. It lists "Multiple connection pools competing for resources", and a comment on it reads "not creating multiple connection pools to a database is mandatory in my opinion". <https://github.com/google/adk-python/pull/3565>.
- READ. The Python LangGraph saver has no schema option. The request for one says that `search_path` is "fragile with pools, PgBouncer transaction mode, and mixed-tenant reuse of physical connections", and it was closed as not planned on 2026-10-31. <https://github.com/langchain-ai/langgraph/issues/7345>. The JavaScript saver gained a `schema` option on 2025-02-21 so as to avoid "modifying the connection string's search path (which can be unreliable at best)". <https://github.com/langchain-ai/langgraphjs/pull/838>.
- INFERRED. None of these peers takes a session factory. The ones that share take an engine or a pool, and each of them owns the sessions it opens on it.

### 3.3 Job queues in the application's database

| Peer | What it accepts | Schema | The fact that bears on the decision |
|---|---|---|---|
| Oban | The application's Ecto repo. | `prefix`, written into every query. | "Transactional Control" is a headline feature. At scale the guide suggests "another pool that’s exclusively for Oban’s internal use", and a dedicated repo that goes around PgBouncer. `README.md:75`; `guides/advanced/scaling.md:165-171`; `troubleshooting.md:63-79`. |
| River | The application's pgx pool, through a driver. | `Config.Schema`, a prefix on every table reference; empty means `search_path`. | `InsertTx` enqueues on the application's transaction. `Config.Schema` was added as "particularly useful for proxies like PgBouncer that may not respect a schema configured in `search_path`". `client.go:404-409`, `1929-1946`; `CHANGELOG.md:560`. |
| pg-boss | A connection string with `max`, or a `db` object with `executeSql`. | `schema`, with `createSchema: false` and `migrate: false`. | A `db` passed to one call runs that call on the application's transaction. `docs/api/constructor.md:47-122`; `docs/api/jobs.md:388`. |
| graphile-worker | A connection string with `maxPoolSize`, or a `pg.Pool`. | `schema`, default `graphile_worker`. | `website/docs/library/run.md:55-64`. |
| GoodJob | Active Record's connections; the parent class can point at another database. | None. | It counts its connections: one for each thread and two more. PgBouncer transaction mode works only with advisory locks and `LISTEN` turned off. `README.md:382-388`, `1353-1362`, `1649-1692`. |
| Solid Queue | A separate database by default. | The database. | The README calls the shared transaction "a powerful yet sharp tool" that "can also backfire", and so "by default Solid Queue is configured in a different database as the main app". `README.md:850`. |
| Que | Active Record's or Sequel's connections, or any pool. | None. | A separate connection URL serves the locker when the application's connections "can't use advisory locks", as behind PgBouncer. `docs/README.md:101`. |
| Procrastinate | Its own psycopg pool from keywords, a `pool_factory`, or an existing pool. | `options=-c search_path=...` on the connection. | A job can be deferred on an external connection, "inside your transaction", for the transactional outbox. `psycopg_connector.py:57-101`; `docs/howto/production/schema.md`; `external_connection.md`. |
| Hangfire | A connection string, an existing `DbConnection`, or a `Func<DbConnection>` factory. | `SchemaName`, with `PrepareSchemaIfNecessary`. | `SqlServerStorage.cs:71-147`; `SqlServerStorageOptions.cs:44`, `125`, `147`. |
| Quartz | A data source it manages, or the container's. | A table prefix, `QRTZ_`. | Two stores: `JobStoreTX` commits for itself, and `JobStoreCMT` is for "container-managed-transactions" where "No commit / rollback will be handled by this class". |

- READ. Every row.
- INFERRED. This is the one family where sharing the application's transaction is the point. The unit shared is one `INSERT` of one row. Every member of the family that shares also keeps or recommends a second path that does not: a dedicated pool, a separate database, a second store class.

### 3.4 Services and file systems that keep their own tables

| Peer | What it accepts | Schema | The fact that bears on the decision |
|---|---|---|---|
| JuiceFS SQL metadata | A URL whose query carries `max_open_conns`, `max_idle_conns`, `max_life_time`, `table_prefix`. | `search_path` in the URL, one schema only; a `jfs_` table prefix. | `pkg/meta/sql.go:440-547`; `docs/en/reference/how_to_set_up_metadata_engine.md:670-672`. |
| SeaweedFS filer store | Configuration keys, with `connection_max_open`, `connection_max_idle`, a lifetime. | `schema`, sent as `search_path`, and not sent at all when `pgbouncer_compatible` is set. | `weed/filer/postgres/postgres_store.go:44-61`, `119-121`. |
| lakeFS | A connection string, `max_open_connections` 25. | None. | `pkg/config/config.go:81-84`; `defaults.go:138-140`. |
| Supabase Storage | A database URL, or a pool URL for an external pooler. | `storage`. | On a direct connection it sends `-c search_path=...` at startup. On an external pool it sends none and runs `set_config('search_path', $1, true)` inside each transaction. `src/internal/database/pg-connection.ts:211`, `239-240`, `833-840`. |
| Supabase Auth | A database URL. | `DB_NAMESPACE`, default `auth`. | `internal/conf/configuration.go:127-128`. |
| Keycloak | A JDBC URL, `db-pool-*` settings. | `db-schema`. | An AWS wrapper is inserted into the URL for IAM logins. `docs/guides/server/db.adoc:165`, `178`, `385`, `752`. |

- READ. Every row.
- INFERRED. Everything in this family owns its connections, and none joins a caller's transaction. All of them are separate processes, which have no application engine to be handed. Chroma in its embedded form is the one in-process member.
- INFERRED. Not one peer that connects to a database server owns its connections from a URL alone. Each one read takes pool settings or engine arguments beside the URL, or takes the application's pool. Supabase Auth, for one, has `MaxPoolSize` and three more pool settings, `internal/conf/configuration.go:134-138`.

## 4. Poolers, drivers and tokens

### 4.1 PgBouncer and `search_path`

- READ. In transaction pooling `SET` and `RESET` are "Never" safe, and neither are `LISTEN` and session-level advisory locks. `pgbouncer.github.io/features.md:55-67`.
- READ. A startup parameter that PgBouncer does not track raises an error unless it is listed in `ignore_startup_parameters`. `pgbouncer/doc/config.md:288-310`.
- READ. Since 1.26.0, released 2026-09-23, `search_path` is tracked by default, fully on PostgreSQL 18 and later. On an older server PgBouncer knows only the value from the startup packet, applies it when the client becomes active, and "Changes made with `SET` after connecting are not tracked ... so they leak to other clients sharing the server connection". `doc/config.md:235-286`. The next release notes say that "various bugs were reported around tracking of `search_path`". `NEWS.md:14-23`.
- READ. The River project's reply in its tracker is that PgBouncer, lacking `search_path` support, "doesn't support exactly 50% of the mechanisms for using a schema". <https://github.com/riverqueue/river/issues/345>, opened 2024-05-08 and still open.
- INFERRED. A schema chosen by `SET` on the session is unsafe behind a transaction pooler on every version. A schema chosen at startup is honoured only by a pooler from September 2026 or later, and refused by an older one. Three peers moved away from it for that reason: River, the JavaScript LangGraph saver, and SeaweedFS in its PgBouncer mode.

### 4.2 asyncpg behind a pooler

- READ. SQLAlchemy's asyncpg page gives the form for PgBouncer: `poolclass=NullPool` and `connect_args={"prepared_statement_name_func": ...}`, a callable. `sqlalchemy/lib/sqlalchemy/dialects/postgresql/asyncpg.py:122-156`.
- EXECUTED. Experiment 7. A URL query does not reach the pool: `?pool_size=1`, `?poolclass=NullPool` and `?pool_pre_ping=true` each left the engine with a queue pool of 5 and were passed to the driver's `connect` as strings.
- EXECUTED. Experiment 7. `asyncpg.connect` has no `options` parameter, and its `server_settings` is a dictionary. So `?options=-csearch_path=vfs` reaches the driver as a keyword it does not have.
- READ. Prefect has the same finding in a comment: the dialect "forwards URL query parameters as plain keyword arguments", so a startup setting must be moved into `server_settings`. `configurations.py:270-275`.
- INFERRED. A storage built from a URL alone cannot run on asyncpg behind PgBouncer in transaction mode, and cannot set a startup parameter. asyncpg is the driver VFS's Postgres profile needs.

### 4.3 Tokens that expire

- READ. SQLAlchemy's documentation gives `do_connect` as the way "to dynamically insert an authentication token that might change over the lifespan of an Engine", and a separate recipe for Azure access tokens on SQL Server. `sqlalchemy/doc/build/core/engines.rst:420-441`.
- READ. `creator`, and `async_creator` on an async engine, make the connection themselves, and "the parameters specified in the URL are not applied". `engine/create.py:180-189`; `ext/asyncio/engine.py:86-96`.
- READ. The Cloud SQL connector is used through exactly that: `create_async_engine("postgresql+asyncpg://", async_creator=...)`. `cloud-sql-python-connector/README.md:643-646`.
- READ. Three peers that own their engine carry a way to supply a token beside the URL. Celery added `database_engine_callback` in 2026 because there was "no hook" for a `do_connect` listener, <https://github.com/celery/celery/pull/10135>, merged 2026-04-02. Dagster has a token provider. Keycloak wraps its JDBC URL. MLflow has none, and a search result shows a third-party plugin that adds RDS IAM logins by registering `do_connect`; its page was not opened.
- EXECUTED. Experiment 9: a `do_connect` listener placed on a built storage's engine fired on its first connection. The engine was reached through the private `storage._host.engine`.
- INFERRED. An owning constructor needs two things for tokens: engine keyword arguments, which carry `async_creator` and `connect_args`, and a way to reach the engine before first touch for `do_connect`.

### 4.4 Scoping a connection to a schema, engine by engine

| Engine | What a schema is | Ways to scope | What is read or run |
|---|---|---|---|
| Postgres | A namespace in a database. | Qualified names; `search_path` at startup, by `SET`, by `SET LOCAL`, or as a default of the role; `schema_translate_map`. | READ. SQLAlchemy's advice is to "keep the `search_path` variable set to its default of `public`" and "name these explicitly within Table definitions". `dialects/postgresql/base.py:340-390`. Its recipe for a non-default path is a `connect` listener that runs `SET SESSION search_path`. |
| SQL Server | A namespace in a database. | Qualified names; the default schema of the database user. | READ. SQLAlchemy reads the default with `SELECT schema_name()`, `dialects/mssql/base.py:3394-3396`, and offers no statement that sets it for a session. Microsoft's documentation was not read. |
| Oracle | A user. | Qualified names; `ALTER SESSION SET CURRENT_SCHEMA` at connect; logging in as the owner. | READ. `sqlalchemy/doc/build/core/metadata.rst:502-543` gives the listener. |
| MariaDB | A database. | The database in the URL; qualified `database.table` names. | READ. `dialects/mysql/base.py:3045-3046` reads `SELECT DATABASE()`. |
| SQLite | A file, or an attached file. | The file in the URL; `ATTACH`. | EXECUTED. Experiment 6. |

- READ. Operators are looked up through `search_path`: "In practice one usually relies on the search path for operators". `postgres/doc/src/sgml/ddl.sgml:3684-3695`.
- READ. VFS spells cosine distance as the bare operator `<=>`. `src/vfs/storage/backends/database/distance.py:35`.
- INFERRED. A connection whose `search_path` holds only VFS's schema cannot find pgvector's operator or its type unless the extension lives in that schema. Scoping by `search_path` alone would break ranked search on Postgres. Not run.
- READ. A secure pattern on Postgres removes from the path every schema that other roles can write to. `ddl.sgml:3794-3800`.
- INFERRED. The scope that works on all five engines is the one VFS already renders: every object named with its schema. What can be added without a session setting is a role whose rights end at the schema.

## 5. The expectations a removal could break

### 5.1 One transaction for application data and VFS data

- EXECUTED. VFS does not offer it. Experiment 1.
- EXECUTED. It happens only through a factory bound to one connection, on SQLite, on an engine VFS has already set up. Experiment 4.
- READ. The peers that offer it are the job queues, for one inserted row. Solid Queue ships with it off and warns against relying on it. No file system, metadata store or checkpointer in the survey offers it.
- READ. The reference deployment forbids what it would take: "A lock other callers need is held for the length of a commit." `AGENTS.md`, "Per lock".
- INFERRED. A VFS write inside an application's transaction would hold VFS's serialization point until the application committed: the write lock on SQLite, the advisory lock on Postgres. Held with a condition: nothing is lost that was offered, and the documentation should say that a VFS call commits on its own.

### 5.2 Connection budget

- EXECUTED. Experiment 8. A built storage's pool is `AsyncAdaptedQueuePool`, 5 connections, 10 overflow, a 30 s wait, no pre-ping, no recycle. Nothing in the constructor changes it.
- EXECUTED. Experiment 8, continued: 40 built storages, one call each, opened 40 connections and held 40 idle. After eight concurrent calls, five of them held 25 idle. A pool keeps what it opened until `close()`.
- INFERRED. At the reference deployment about 20 verb calls a second arrive at peak and each lasts tens of milliseconds, so about one connection is busy at a time in the whole deployment. One pool of five is ample. The cost is the number of pools: one for each storage, in each process.
- READ. `build_vfs_tables` expects "a host that places thousands of tenants in their own schemas". `rows.py:401-404`.
- INFERRED. A thousand storages that each own an engine hold at least a thousand connections once each is touched. Postgres's `max_connections` default "is typically 100 connections", READ at `postgres/doc/src/sgml/config.sgml:724`. Today those storages can share the one engine behind a handed factory.
- INFERRED. Broken as literally stated. Held when the constructor takes pool arguments, `NullPool` among them, and when several storages on one database can share one engine.

### 5.3 Authentication that is not a static URL

- READ. Section 4.3.
- INFERRED. Broken as literally stated. Held when the constructor takes engine keyword arguments and the engine can be reached before first touch.

### 5.4 Testing habits

- EXECUTED. The rolled-back-transaction fixture works today on SQLite only, and only on an engine VFS has already set up. Experiment 4.
- EXECUTED. An in-memory engine shared between the application and a handed storage fails on concurrent calls today. Experiment 5.
- READ. VFS's own suite uses the form the proposal keeps: a URL and a fresh schema for each test on a server, `tests/support/server_schemas.py:70-86`, and `InMemoryStorage` or a temporary file elsewhere.
- INFERRED. Held with a condition. Both habits are lost, and both are already unsound. The replacement is to be documented: `InMemoryStorage` for unit tests, and a schema or a file for each test.

### 5.5 Operations

- EXECUTED. Experiment 10, with OpenTelemetry's SQLAlchemy instrumentation and one `stat` on a file. Instrumented globally before VFS was imported, a built storage exported 117 spans. Instrumented globally after the import, it exported 5. A handed storage whose engine the application instrumented by name exported 117.
- INFERRED. With an engine VFS built and does not expose, tracing depends on import order. An engine accessor or a callback removes the dependence.
- READ. Ownership of `close()` becomes one rule. Today it is "Dispose iff built". `engine.py:529-568`.
- READ. A built storage binds nothing to an event loop until first touch, and the handed path is "single-loop by intent". `engine.py:11-13`.
- INFERRED. Held with a condition: the engine is reachable for listeners. Fork safety and loop safety improve, because VFS can dispose and rebuild an engine that is its own.

### 5.6 Several storages on one database

- READ. One schema holds one mount, section 2.
- INFERRED. Three shapes. An engine for each storage is as many pools as mounts. One engine shared by storages that each name a schema is one pool, and it is what a handed factory gives today. `langchain-postgres` has the same shape with ownership kept: one `PGEngine`, made from a URL, serves many stores.
- INFERRED. Broken as literally stated for many mounts on one database. Held when VFS has a shareable connectivity object that it builds itself.

### 5.7 Migration and DDL rights

- READ. First touch runs `create_all` when the meta table is absent, and only verifies when it is present. `engine.py:692-696`.
- INFERRED. A database administrator can create the schema and the tables in advance, and a serving role with no DDL rights then passes first touch. Not run on a server.
- READ. Peers give an explicit switch: `createSchema: false` and `migrate: false` in pg-boss, `PrepareSchemaIfNecessary` in Hangfire, `skip_table_creation` in Optuna, `should_autocreate_tables` in Dagster, `create_tables=False` by default in `openai-agents-python`, an explicit `setup()` in LangGraph.
- INFERRED. Owning a schema raises the stakes of two gaps that exist today and are independent of the handed form: VFS does not create the schema, and a privilege refusal is not yet classified. The draft spec 157 covers both.

### 5.8 Middle designs

| Design | Peers that chose it | Keeps | Loses |
|---|---|---|---|
| A. A URL alone. The proposal as worded. | None. | The simplest constructor. One rule for `close()`. | Pool sizing, PgBouncer on asyncpg, tokens, tracing, many mounts on one database. |
| B. A URL and engine keyword arguments, with the engine reachable. | Optuna, Celery, MLflow, Prefect, Airflow, Dagster, JuiceFS, lakeFS, Keycloak. | Everything A keeps. Pools, poolers, tokens, tracing. VFS may set what it needs at connect, on every engine. | One pool shared with the application. A second engine to configure. Many mounts are still many pools. |
| C. B, and one engine that VFS built shared by several storages. | `langchain-postgres` `PGEngine`. | Everything B keeps, and one pool for many mounts. | One more public object. |
| D. An `AsyncEngine` accepted beside the URL. Never a session factory. | APScheduler, ADK, `openai-agents-python`, LlamaIndex, mem0, graphile-worker. | One pool with the application. The application's engine setup is reused. | Caveats 2, 5, 6, 7, 8 and 9 of section 1.8 stay, and "dispose iff built" stays. On SQLite VFS still changes the application's connections. |
| E. `session_factory=` kept and narrowed to an engine-bound factory. | Airflow, which discourages it. | What D keeps. | What D loses, and the session class and its settings stay outside VFS's control. |
| F. As today. | None. | The rollback fixture on SQLite. | Section 1.8 whole. |

- INFERRED. Every row, from sections 1 to 5.

## 6. The findings that bind the design

1. **A storage already owns its sessions and transactions, so removing `session_factory=` removes no capability that was promised.** Experiment 1 shows the transaction is never shared. What the handed form shares is a pool, and on SQLite the price is the application's own connections changed under it, experiment 2. The form costs fifteen sites of code, 61 tests and nine written caveats, two of them silent failures on server engines.

2. **Owning the sessions does not require owning the engine from a URL alone, and no peer does that.** Every owner in the survey takes engine or pool arguments. On asyncpg the arguments a pooler needs are a pool class and a callable, which no URL carries, section 4.2. A token needs `async_creator` or a `do_connect` listener, section 4.3.

3. **The request peers receive after shipping a URL alone is for the application's engine, and the reason given is pools.** ADK and LlamaIndex both added the engine form on request. Celery shows the other half: engine options were not enough for tokens, and a callback was added in 2026.

4. **One engine for each storage does not scale to many mounts on one database.** Experiment 8 and section 5.2. Ownership has to sit on something that several storages can share.

5. **A schema is scoped by naming it, not by setting it on the session.** VFS already qualifies every table and every raw statement. `search_path` on the session is dropped or leaked by poolers, three peers left it for that reason, and pgvector's operator needs the path, section 4.4. A role limited to the schema adds what naming cannot.

6. **On SQLite, ownership pays for itself on every call.** Seven of the eleven statements of a `stat` are settings stamped at checkout because the pool might be someone else's, experiment 3.

7. **An engine form can be added after a release, and a handed form cannot be removed after one.** Accepting an engine later is an addition. Removing a handed form later is a break. The project is before its first release, `AGENTS.md`, "Project stage".

## 7. Not checked

- **Any server engine.** Nothing was executed on Postgres, MariaDB, SQL Server or Oracle. That a factory bound to a connection raises at the isolation pin, that a serving role with no DDL rights passes first touch on tables made in advance, and that a `search_path` without the extension's schema breaks `<=>` are INFERRED. Each is one test on the Postgres engine leg.
- **PgBouncer itself.** Its behaviour is read from its documentation and release notes. A VFS storage has not been run through it. The experiment is the Postgres leg behind PgBouncer 1.26 in transaction mode, with `NullPool` and named prepared statements.
- **RDS Proxy, Supavisor and Neon's pooler.** Not read. Each is a documentation reading and the same leg.
- **Microsoft's and Oracle's own documentation.** Two documentation hosts were outside the session's network, `www.pgbouncer.org` and `docs.sqlalchemy.org`, and both were read from their source repositories instead. SQL Server's rule for a user's default schema and Oracle's `CURRENT_SCHEMA` are known here only through SQLAlchemy's source and documentation.
- **Issue threads.** Seven were read through a fetch that summarises. The quoted words were not checked against the pages line by line.
- **Peers not read.** Letta's server, Zep, Datasette and sqlite-utils, fsspec's SQL file systems, Hasura's catalog, Flyway, Liquibase, and the PostGIS and Timescale extension schemas. SQLAlchemy-Continuum was read in its README only.
- **MLflow's token plugin.** Seen in a search result and not opened.
- **A count of lines.** Section 1.9 counts sites, call sites and collected tests. The lines a removal would delete were not counted, because the count depends on the design that replaces them.
- **Whether `use_setinputsizes` and the driver can be verified on a handed engine at first touch.** Design D depends on it. The experiment is a first touch on the SQL Server and Postgres legs with an engine built without VFS's arguments.

## One line

A storage already runs every call in a session and a transaction of its own, so the handed session factory can go; but it must be built from a URL and engine arguments with the engine reachable, several storages on one database must be able to share one engine that VFS made, and its schema is scoped by qualified names and a limited role, not by a `search_path` on the session.
