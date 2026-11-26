# A mount's durability trait comes from one probe of the engine's own setting at first touch, and an in-memory store declares none

A draft, written on 2026-11-25 and checked against `dev` at `27f3d24d`. It is not reviewed, and nothing is built. It serves story K7, gate f, of [the roadmap](../../context/standards/roadmap.md), by its heading only: "spec 179 (slices)" (`roadmap.md:194`); none of K7's five criteria names durability. It is unit 179-4 of [the unit map](../2026-11-25-the-backlog-converted/units.md), converted from section 2.5, task 5 and criterion 6 of [spec 179](../../context/specifications/archive/179-the-storage-seam-as-the-kernel/spec.md), read through [its study](../2026-11-25-the-backlog-converted/studies/165-181/179-the-storage-seam-as-the-kernel.md) and [the reassessment against dev](../2026-11-25-the-backlog-converted/reassessment/seam.md). The source's MariaDB, SQL Server and Oracle probes are dropped, because dev serves SQLite and Postgres only. It rests on no unbuilt unit.

## The outcome wanted

A caller holding a database storage reads `storage.traits().get("durability")` once the storage has made its first touch and learns what a commit that returned survives on the engine actually serving it. A SQLite file whose connection runs `synchronous = FULL` or `EXTRA` says `full`; one an application has turned down to `NORMAL` or `OFF` says `relaxed`. A Postgres mount says `full` unless the session it runs in has `synchronous_commit = off`, and then says `relaxed`. An in-memory store, a mount on the generic floor and a storage that has not made its first touch say nothing: the key is absent. The answer costs one statement per storage, at first touch, and nothing on any verb call. It is seen in tests that set each engine's setting, call `first_touch()`, and read the trait and the count of probe statements, on SQLite and on the Postgres leg.

## Builds on

- The trait vocabulary on dev: `TraitKey`, `TRAIT_KEYS` and `TRAIT_VALUES` (`src/vfs/storage/protocol.py:78-100`), with `durability` taking `full` and `relaxed` (`:96`), and the rule that "an absent key means the trait is not declared, never a default" (`:75-77`). Built.
- `DatabaseStorage.traits()` (`src/vfs/storage/backends/database/backend.py:240-253`). Built.
- First touch on `EngineHost`: `ensure_ready` runs `_first_touch` under `with_retry` and classifies what escapes (`src/vfs/storage/backends/database/engine.py:285-302`); `_first_touch` applies the file settings, reads `in_memory` on SQLite, proves the vector function and verifies or provisions the schema (`:557-573`). Built.
- The vector-function probe as the precedent for a profile-declared probe: `VectorFunction` (`src/vfs/storage/backends/database/dialects.py:84-100`) and `_probe_vector_function` (`engine.py:595-623`), which raises what the retry policy would restart or what cost the connection, and reads every other driver error as a verdict. Built.
- `agents/2026-11-20-vfs-serves-sqlite-and-postgres-only/spec.md`: two tuned profiles, `SQLITE` and `POSTGRESQL`, and the `GENERIC` floor (`dialects.py:360-461`). Built.
- Unit 179-3, [the atomic-unit spec](../2026-11-25-the-seam-states-its-atomic-unit-and-its-two-atomicity-models/spec.md), written and not built. Its decision 13 turns `backend.py:250-252` into `declared |= {"durability": "full", "atomic_unit": "call"}` under the tuned-profile `if` on dev, and follows decision 12 below in both landing orders: where this unit has landed first it adds the entry and the `PROFILES` import, two lines, and sets the entry of `backend.py` in `MODULE_LINE_BASELINE` to the count reached, 1,509 from 1,507 on dev's base, so the tree is the same in either order. Neither unit waits for the other.
- The vid and kernel-records stack, open, tip `origin/the-kernel-writes-records-behind-and-sweeps-them`. It adds `"vid": "entry_version"` to the literal of `traits()` and leaves the three durability lines as they are (READ, the tip's `backend.py:261-275`). It splits the engine core out, so the tip's `engine.py` holds 849 lines and has no size baseline, while `_first_touch` (the tip's `engine.py:445`) and `_read_in_memory` (`:582`) keep their shape (READ). This unit lands on either side of it; decisions 11 and 12 hold in both.

## Terms

- **Durability**: what a commit that has returned survives. `full`: it survives a crash of the engine's host, process, operating system or power. `relaxed`: such a crash may lose it.
- **Probe**: the one statement a profile declares that reads the engine's own commit setting from a live connection.
- **First touch**: the idempotent, lazy setup a storage runs before its first verb or at `first_touch()`.

## What the code does today

1. `traits()` declares `durability: "full"` for every tuned profile by name, and reads no engine setting: "Tuned engines are the measured ones, and only they claim full durability" (READ, `backend.py:250-252`).
2. It says so before first touch. A fresh `DatabaseStorage` on a SQLite file answers `full` before any connection exists (EXECUTED, a scratch script on dev).
3. `InMemoryStorage` subclasses `SQLiteStorage` and declares the same `full` (READ, `src/vfs/storage/backends/memory.py:40-44`). Its database is gone at `close()`.
4. vfs pins `PRAGMA synchronous = FULL` at every checkout of a SQLite connection (READ, `dialects.py:370`, run by `_on_checkout`, `engine.py:966-974`). An application may put listeners on the engine (READ, `engine.py:5-7`). A checkout listener added after construction runs after vfs's and wins: with one setting `synchronous = NORMAL`, the connection answered `1` after first touch while `traits()` said `full` (EXECUTED).
5. SQLite's `synchronous` is a setting of each attached database. An unqualified `PRAGMA synchronous = OFF` left an attached database at `2` (EXECUTED, Python's `sqlite3`, SQLite 3.53.1). A mount with `schema=` on SQLite is an attached database (READ, `tests/storage/database/test_engine.py:82-98`).
6. An in-memory SQLite database answers `PRAGMA synchronous` with `2` (EXECUTED), so the setting alone would claim `full` for a store that keeps nothing. First touch already reads whether the database is in memory, from `PRAGMA database_list` (READ, `engine.py:562`, `:709-720`), and that read covers a shared-cache `file::memory:` URL (READ, `tests/storage/database/test_statistics.py:515-521`).
7. Nothing reads Postgres's `synchronous_commit` (EXECUTED, no hit for `synchronous_commit` under `src/vfs`).
8. Nothing under `src/vfs` reads the `durability` trait; the one reader of `traits()` is the cursor's `listing_cursor` test (READ, `src/vfs/cursor.py:131`). The pins are `tests/storage/database/test_engine.py:151-161` and the vocabulary row of the contract (`tests/support/storage_contract.py:3263-3268`).
9. `engine.py` is held at exactly 1,008 lines and `backend.py` at 1,509 (READ, `tests/lint/allowlist.py:26-33`); the lint fails a listed module that grows or shrinks without its entry (READ, `tests/lint/test_code_shape.py:228-252`). `dialects.py` holds 931 lines under the ceiling of 1,000 (EXECUTED, `wc -l`).

## The problem

The trait is a contract a caller reads instead of probing (READ, `protocol.py:520-523`), and today it is a guess made from the profile's name. It is wrong in three cases that a caller cannot see. An in-memory store says `full` and keeps nothing past its process. A Postgres server, database or role tuned with `synchronous_commit = off`, a common setting for bulk ingest, says `full` while PostgreSQL may lose the last commits that returned in a crash. A SQLite engine whose application lowered `synchronous` says `full` as well.

At the reference deployment the cost of the wrong answer falls on the ETL pipelines. Postgres is the common case, and the nightly batch is 100 commits of 10,000 files. A pipeline that drops its own copy of a batch once the commit returns is trusting the trait. With `synchronous_commit = off` a crash can lose the last of those commits, which PostgreSQL bounds at three times `wal_writer_delay`, 600 ms at the default ([PostgreSQL, WAL configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html#GUC-SYNCHRONOUS-COMMIT)). The fix costs one statement per storage, not per call.

## Decisions

1. **The `durability` key keeps its two values, and their meaning is written down.** `full`: a commit that returned survives a crash of the engine's host. `relaxed`: such a crash may lose it. An absent key promises nothing. `TRAIT_VALUES` does not change. The meaning goes in the `SupportsTraits` docstring, because a backend author and a caller read it there.
2. **Each tuned profile declares its probe as a field, `DialectProfile.durability_probe: DurabilityProbe | None = None`.** `DurabilityProbe` is a `NamedTuple` beside `VectorFunction` in `dialects.py`, with three fields: `statement`, the probe, with `{schema}` where the setting is per database; `full`, the answers that mean `full`; and `relaxed`, the answers that mean `relaxed`. An answer is compared as `str(answer)`. SQLAlchemy takes no position on commit durability, so AGENTS.md's rule for a profile field is met. Precedent: `VectorFunction`, a probe declared on the profile and run at first touch.
3. **SQLite probes `PRAGMA {schema}.synchronous`, formatted with the mount's quoted schema; `full` is `{"2", "3"}` and `relaxed` is `{"0", "1"}`.** The values are FULL and EXTRA, OFF and NORMAL. NORMAL is `relaxed` because "a transaction committed in WAL mode with synchronous=NORMAL might roll back following a power loss or system crash" ([SQLite, PRAGMA synchronous](https://www.sqlite.org/pragma.html#pragma_synchronous)). The statement is schema-qualified because the setting is per attached database (fact 5); `statistics_listing` is formatted the same way, through `_statistics_schema()` (`engine.py:722-730`). SQLite is probed although vfs pins FULL, because an application listener can lower it (fact 4).
4. **Postgres probes `SHOW synchronous_commit`; `full` is `{"on", "remote_apply", "remote_write", "local"}` and `relaxed` is `{"off"}`.** PostgreSQL documents `off` as the one value that returns before the commit's WAL reaches disk; the other four differ only in what they wait for from a standby. The session's value already folds in the server, database and role settings and any setting made at connect, so one `SHOW` reads what the mount's commits run under.
5. **`GENERIC` declares no probe, so the floor never declares durability.** That keeps today's behaviour on an unknown dialect, pinned at `test_engine.py:160-161`.
6. **An in-memory database sends no probe and declares no durability.** First touch reads `in_memory` before the probe, and `True` skips it. The probe alone would answer `full` for an in-memory database (fact 6). The key is absent rather than a new value; choice 1 says why.
7. **The probe runs once in each first touch, after `_verify_or_provision` returns no refusal and before `_ready` is set.** It runs on a session of its own, outside a transaction on SQLite (`vfs_no_begin`, as `_read_in_memory` and the vector probe do), and in the session's own transaction on Postgres, which closes with a rollback. It runs inside `with_retry`, like every other first-touch step. A refused mount declares nothing. When a fresh connection re-arms first touch (`engine.py:553-555`), the next first touch reads it again. Reading it last means the mount declares only once it serves, and the probe holds no lock: the serialization point is released at `_verify_or_provision`'s commit.
8. **A probe failure is read the way the vector probe reads one.** A `DBAPIError` that cost the connection, or that `is_retryable` would restart, propagates to the retry and the classifier. Any other driver error leaves the key absent and the mount serving. An answer in neither set, or no row, leaves the key absent. Precedent: `_probe_vector_function` (`engine.py:612-619`), and spec 179's Oracle row, "not declared when the role may not read `v$parameter`". Refusing the mount over a setting it could not read would take service away to report a missing promise.
9. **Before first touch the key is absent.** The vocabulary's own rule says an absent key is "not declared, never a default" (`protocol.py:75-77`), and nothing has been read before first touch. This changes what `traits()` answers before the first call (fact 2); nothing under `src/vfs` reads it then (fact 8).
10. **`EngineHost.durability: Durability | None`, `None` until a probe answers.** `Durability = Literal["full", "relaxed"]` lives in the new module. A test pins `frozenset(get_args(Durability)) == TRAIT_VALUES["durability"]` and every probe's two sets to it.
11. **A new module, `src/vfs/storage/backends/database/durability.py`, holds `Durability`, `probe_durability(sessions, profile, schema)` and `read_in_memory`, moved from `EngineHost._read_in_memory` with its docstring.** `probe_durability` takes the session factory, the profile and the quoted schema, and returns `Durability | None`. `read_in_memory` moves because the in-memory answer is the first half of the durability decision, and because `engine.py` is held at its exact count (fact 9): the move frees more lines than the attribute, the import and the call add. `engine.py` never grows. Its baseline entry is lowered to the count the build leaves, or removed if it falls to 1,000 or fewer. Where the engine-core split has landed and `engine.py` has no entry, the move is still made, for ownership. `durability.py` imports `dialects.py` for `is_retryable`; `dialects.py` imports nothing from it, so there is no cycle. The module is under `vfs.storage.backends`, which `LAYERS` places already (`tests/lint/test_code_shape.py:54-62`).
12. **`traits()` puts `"durability": self._host.durability` in its literal and returns the entries whose value is not `None`.** On dev the three lines of `backend.py:250-252` and the `PROFILES` import (`backend.py:44`) go, one entry and a one-line comment come in, and the baseline drops from 1,509 to 1,507. If unit 179-3 has landed first, its tuned-profile `if` folds into the same literal, as `"atomic_unit": "call" if self._host.profile.name in PROFILES else None`, under one comment line that gives both reasons, at no net line. If 179-3 lands second, it adds that entry and the import and pays for them itself. It pays by setting the entry of `backend.py` to the count reached, which is the count the other order leaves (its decision 13 and its choice 5). `ty` narrows the filtered comprehension to `Mapping[str, str]` (EXECUTED, `ty check` on a scratch module of that shape).
13. **The SQLite tests set the setting with a checkout listener added after construction, and the Postgres tests with a connect listener that sends `SET synchronous_commit`.** Both are what an application may do (fact 4), and both work on either Postgres driver. No test reaches into the profile to fake an answer the engine did not give, except where the failure path needs a statement the engine refuses.
14. **`test_durability_full_is_declared_per_tuned_profile` (`test_engine.py:151-161`) is deleted and replaced by the tests below.** It patches the profile and reads `traits()` with no first touch, which is the rule this unit removes. Unit 179-3's own test `TestConstruction::test_the_call_is_the_atomic_unit_on_every_tuned_profile_and_undeclared_on_the_floor` stands alone and is not deleted with it.

## Cost

- **The probe.** One statement per first touch, on one connection checked out of the pool. A storage makes one first touch in its life, plus one after each re-armed fresh connection on a single-connection pool, where the in-memory skip sends nothing. The multiplier is the number of storages a deployment builds, about one per process per mount, never a verb call, a file write, an index visit or a batch. At 1,000 callers each starting one process a day, that is 1,000 statements a day against 150,000 verb calls, each of which issues several. On Postgres the session costs its begin and its rollback beside the `SHOW`.
- **Locks.** `SHOW` and the SQLite `PRAGMA` read connection state and take no lock. The probe runs after the topology serialization point is released, so no reader or writer waits on it.
- **Growth.** No statement here grows with batch size, so no budget applies: there is no `IN` list, no bind and no row loop.
- **`traits()`.** Builds one dictionary of at most ten entries in memory, with no IO, as today.

## Left as it is

- **vfs does not pin `synchronous` on an attached SQLite schema.** `PRAGMA synchronous = FULL` in `session_settings` sets the main database only (fact 5). A mount in an attached schema runs at that database's own setting, which is FULL on the build checked and may differ on a build with another compiled default. The probe now reports it honestly. Pinning it changes write behaviour, so it is a spec of its own.
- **A setting changed after first touch is not seen.** The probe is one read. A server reconfigured while a storage lives, or an application that changes the setting on some connections only, is seen by the next storage. The `SupportsTraits` docstring says the value is read once, at first touch.
- **The journal mode.** vfs sets WAL in `file_settings` in the same first touch (`dialects.py:377-381`); the probe does not read it again.
- **The kernel-records place.** The open stack's `RecordPlace.durable` (READ, `agents/2026-11-22-the-kernel-keeps-records-of-its-own/spec.md:127`) is a property of where records go, and it is not derived from this trait here.

## Tests

Written first, and seen failing. Counts and states, never clocks. No right changes, so no leak test applies.

- `tests/storage/database/test_dialects.py::TestDialectPolicy::test_each_tuned_profile_reads_its_engines_commit_setting_and_the_floor_reads_none`: `SQLITE.durability_probe` is `DurabilityProbe("PRAGMA {schema}.synchronous", frozenset({"2", "3"}), frozenset({"0", "1"}))`; `POSTGRESQL.durability_probe` is `DurabilityProbe("SHOW synchronous_commit", frozenset({"on", "remote_apply", "remote_write", "local"}), frozenset({"off"}))`; `GENERIC.durability_probe is None`; each probe's two sets are disjoint.
- `tests/storage/database/test_durability.py::test_the_durability_values_are_the_trait_vocabulary`: `frozenset(get_args(Durability)) == TRAIT_VALUES["durability"]`.
- `tests/storage/database/test_durability.py::test_a_probe_the_retry_would_restart_propagates`: over a stub session factory whose statement raises a `DBAPIError` wrapping a SQLite busy error (code 5), `probe_durability` raises it.
- `tests/storage/database/test_durability.py::test_a_probe_that_cost_the_connection_propagates`: the stub raises a `DBAPIError` with `connection_invalidated=True`, and it propagates.
- `tests/storage/database/test_durability.py::test_a_permanent_probe_failure_declares_nothing`: the stub raises a `DBAPIError` wrapping SQLite's generic error (code 1); the result is `None`.
- `tests/storage/database/test_durability.py::test_an_answer_outside_both_sets_declares_nothing`: answers `"7"` and no row each give `None`.
- `tests/storage/database/test_durability.py::test_no_probe_opens_no_session`: a profile with `durability_probe=None` gives `None`, and the stub factory counts 0 sessions.
- `tests/storage/database/test_engine.py::TestDurability::test_durability_is_declared_only_once_first_touch_has_read_it`: a SQLite file storage has no `durability` key before `first_touch()` and `full` after it.
- `tests/storage/database/test_engine.py::TestDurability::test_a_sqlite_file_declares_what_its_synchronous_setting_says`, parametrized `OFF`, `NORMAL`, `FULL`, `EXTRA`: a checkout listener sets the value; after first touch the trait is `relaxed`, `relaxed`, `full`, `full`.
- `tests/storage/database/test_engine.py::TestDurability::test_a_mount_in_an_attached_schema_reads_its_own_databases_setting`: with `schema="tenant"` attached by a connect listener, as at `test_engine.py:82-98`. With the main database set `OFF` and `tenant` left alone the trait is `full`. With `tenant.synchronous = NORMAL` it is `relaxed`. An unqualified probe fails the first case.
- `tests/storage/database/test_engine.py::TestDurability::test_the_probe_is_one_statement_at_first_touch_and_none_after`, parametrized `[sqlite, *ENGINE_LEGS]` from `tests/support/server_schemas.py:52-54`: a `before_cursor_execute` recorder counts statements equal to the formatted probe across `first_touch()`, a `write`, a `read`, an `ls` and a second `first_touch()`, and the count is 1. This is the Postgres leg of the storage change.
- `tests/storage/database/test_engine.py::TestDurability::test_a_postgres_mount_declares_what_synchronous_commit_says`, marked `postgres`, parametrized `on`, `remote_apply`, `remote_write`, `local`, `off`: a connect listener sends `SET synchronous_commit = <value>` on a `server_storage("VFS_TEST_POSTGRES_URL")` mount; after first touch the trait is `full` four times and `relaxed` once.
- `tests/storage/database/test_engine.py::TestDurability::test_a_refused_mount_declares_no_durability`: with `engine_module.profile_for` patched to `replace(SQLITE, vector_function=VectorFunction(probe="SELECT NULL", missing="absent"))`, as `test_engine.py:170-175` patches a profile, first touch refuses `unavailable`, and the key is absent.
- `tests/storage/database/test_engine.py::TestDurability::test_a_probe_the_engine_refuses_leaves_the_mount_serving`: with the probe's statement patched to `SELECT no_such_function()`, first touch succeeds, the key is absent, and a `write` then a `read` succeed.
- `tests/storage/database/test_engine.py::TestDurability::test_a_profile_with_no_probe_declares_nothing`: with `replace(SQLITE, durability_probe=None)` the key is absent after first touch, which pins decision 5 on a live engine.
- `tests/storage/test_memory.py::test_an_in_memory_storage_declares_no_durability_and_sends_no_probe`, parametrized `InMemoryStorage()` and `DatabaseStorage(url="sqlite+aiosqlite:///file::memory:?cache=shared&uri=true")`: after first touch the key is absent and the recorder counts 0 probe statements.
- Unchanged and still passing: the vocabulary rows at `test_engine.py:146-149` and `tests/support/storage_contract.py:3263-3268` on every leg, and `tests/storage/database/test_statistics.py:515-521`, which pins the moved `read_in_memory`.
- The gates: `uv run ruff check src/ tests/`, `uv run ruff format --check src/ tests/`, `uv run ty check src/ tests/`, `tests/lint/` with the lowered baselines, `scripts/ci.sh`, and `scripts/docs.sh check`, because docstrings under `src/vfs/` change.

## Scope

In: `src/vfs/storage/backends/database/durability.py` (new); `DurabilityProbe` and the `durability_probe` field and its two values in `src/vfs/storage/backends/database/dialects.py`; `EngineHost.durability`, the probe call in `_first_touch` and the move of `_read_in_memory` in `src/vfs/storage/backends/database/engine.py`; `traits()` and the import in `src/vfs/storage/backends/database/backend.py`; the docstrings of `src/vfs/storage/protocol.py` and `src/vfs/storage/backends/memory.py`; the entries of `tests/lint/allowlist.py`; the tests above, and the deletion decision 14 names.

Out:

- A third value such as `none`: choice 1.
- Postgres `fsync`: choice 2.
- Pinning `synchronous` on an attached SQLite schema: a spec of its own, under Left as it is.
- MariaDB, SQL Server and Oracle probes: those engines are not served.
- A router or `MountInfo` surface for traits: none exists today (fact 8), and no story asks for one.
- The atomic-unit trait: unit 179-3.

## What the docs must say

- `SupportsTraits` (`protocol.py:514-524`): what `full` and `relaxed` mean, and that a database storage reads the value from its live connection once, at first touch, so the key is absent before it.
- `InMemoryStorage` (`memory.py:40`), rendered on `documentation/reference/python-api/storage.md`: one sentence saying it declares no durability, because nothing it holds outlives the storage. Its "every verb, capability, and trait comes from `DatabaseStorage`" stays true.
- `DialectProfile` (`dialects.py:119-348`): one paragraph on `durability_probe`, the statement, its `{schema}` and the two answer sets, and that the floor declares none.
- The `engine.py` module docstring: the durability probe joins the list of what first touch does, once the mount serves.
- The `durability.py` module docstring: what the module decides and from what, with the two engines' settings named.
- No page under `documentation/` changes in prose. The glossary has no durability entry, and this unit adds none.

## Earlier decisions this reverses

- The rule in the comment at `backend.py:250`, "Tuned engines are the measured ones, and only they claim full durability", which made the claim from the profile's name. It becomes a claim read from the engine.
- Nothing of [unit 179-3](../2026-11-25-the-seam-states-its-atomic-unit-and-its-two-atomicity-models/spec.md): its decision 13, as amended on 2026-11-25, takes both landing orders from decision 12 above.

## Not checked

- The Postgres leg was not run. No server was reachable (`VFS_TEST_POSTGRES_URL` is unset). The four `full` answers and the one `relaxed` answer of `SHOW synchronous_commit`, and that `SHOW` returns the canonical name and not an alias, are taken from PostgreSQL's documentation and were not run.
- That a connect listener's `SET synchronous_commit` reaches every pooled connection on both asyncpg and psycopg was not run.
- SQLite was run on 3.53.1 only. A build with another `SQLITE_DEFAULT_SYNCHRONOUS` or `SQLITE_DEFAULT_WAL_SYNCHRONOUS` was not run.
- The line counts the build leaves in `engine.py`, `backend.py` and `dialects.py` were estimated, not measured. Only the `ty` narrowing of decision 12 was run.
- The test suite, `scripts/ci.sh` and `scripts/docs.sh check` were not run.

## Choices to confirm

1. **An in-memory store leaves the key absent, or declares a new value `none`.** Spec 179 added `none` to `TRAIT_VALUES` ("nothing survives the process"); the unit map and the reassessment read it as no key. Taken: no key. It adds nothing to the vocabulary, and a caller already reads an absent key as "no promise". Adding `none` later is additive; removing it once callers match on it is not.
2. **Postgres `fsync = off` is read too, or not.** One statement could read both settings, and a server with `fsync = off` makes no `full` promise. Taken: `synchronous_commit` alone, as the unit and its source name it. `fsync = off` risks a corrupt cluster after a crash, which is more than `relaxed` means, so declaring it honestly would want a third value. Folding it in later changes one profile constant and its test.

## One line

A database storage declares `durability` from one first-touch read of its engine's own commit setting, `PRAGMA <schema>.synchronous` on SQLite and `SHOW synchronous_commit` on Postgres, `relaxed` when it is turned down, and declares nothing in memory, on the floor or before first touch.
