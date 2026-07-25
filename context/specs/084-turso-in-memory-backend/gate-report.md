# Gate report — Turso as the in-memory engine (spec 084, decision 1)

- **Date:** 2026-07-25
- **Probe environment:** `pyturso==0.7.1` (`[sqlalchemy]` extra),
  SQLAlchemy 2.0.46, Python 3.13.11, macOS arm64. Probe scripts ran
  against `sqlite+aioturso:///:memory:`; total probe wall-clock for
  items (a)–(e) was 0.03 s once the engine constructed.
- **Decision: FALLBACK ARM.** The in-memory backend lands on
  `sqlite+aiosqlite:///:memory:` (StaticPool). `pyturso` was added for
  the probe (`uv add "pyturso[sqlalchemy]"`, resolved and installed
  cleanly) and removed again after the gate (`uv remove pyturso`) —
  no new dependency ships. Turso is re-attempted when the blockers
  below are fixed upstream, per ADR 028 pin 3.

## Blockers (three, all upstream in pyturso's SQLAlchemy adapter)

All three were found in `turso/sqlalchemy/dialect.py` as shipped in
pyturso 0.7.1; the third also reproduces the same way conceptually in
the 0.8.0rc1 wheel (blockers 1–2 were checked there directly and are
unfixed). None can be fixed from vfs without monkeypatching pyturso or
SQLAlchemy internals, which is below the adoption bar for the default
dev/test storage.

1. **Engine construction fails outright** (gate item a, first half).
   `AioTursoDialect` subclasses SQLAlchemy's `SQLiteDialect_aiosqlite`,
   whose `__init__` in SQLAlchemy 2.0.46 reads `self.dbapi.has_stop`;
   pyturso's `AsyncAdapt_turso_dbapi` never sets it.

   ```text
   create_async_engine("sqlite+aioturso:///:memory:")
   AttributeError: 'AsyncAdapt_turso_dbapi' object has no attribute 'has_stop'
   ```

   Probe workaround (evidence only): class-level `has_stop = False`,
   which merely disables `has_terminate` — semantically safe, but a
   monkeypatch of a third-party adapter.

2. **The writer-listener recipe cannot install** (gate item a, second
   half). vfs's sqlite transaction control sets
   `dbapi_connection.isolation_level = None` at pool checkout (the
   documented SQLAlchemy recipe for taking over BEGIN emission).
   pyturso uses SQLAlchemy's *generic* `AsyncAdapt_dbapi_connection`,
   which neither proxies `isolation_level` (aiosqlite's dedicated
   adapter does) nor allows setting it (`__slots__`, no `__dict__`):

   ```text
   AttributeError: 'AsyncAdapt_dbapi_connection' object has no attribute
   'isolation_level' and no __dict__ for setting new attributes
   ```

   The underlying `turso.aio.Connection` *does* expose
   `isolation_level`; the probe reached it through the private
   `dbapi_connection._connection` — workable as evidence, not as a
   shipped code path.

3. **`memoryview` bind parameters are rejected** (found by gate item
   f, the decisive check). vfs's `entry_id` (`ULIDKey` →
   `BINARY(16)`) binds through `dbapi.Binary`, which is `memoryview`
   on the sqlite family — pyturso even re-exports
   `sqlite3.Binary`. Turso's driver refuses it, so **first touch
   fails and every verb after it**:

   ```text
   sqlalchemy.exc.DatabaseError: (turso.lib.DatabaseError) unexpected
   parameter value, only None, numbers, strings and bytes are supported
   [SQL: INSERT INTO vfs (entry_id, parent_id, path, name, kind, version,
   lines, size_bytes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)]
   [parameters: (<memory at 0x...>, None, '/', '/', 'directory', 1, 0, 0, ...)]
   ```

## The six items

1. **`BEGIN IMMEDIATE`** — **parses and runs.** Raw
   `BEGIN IMMEDIATE … COMMIT` executed cleanly, and the existing
   begin listener worked once blockers 1–2 were shimmed. Not a
   blocker in itself; the listener *installation* is (blocker 2).
2. **Pooled `:memory:` semantics** — **shared, via StaticPool.** The
   aioturso dialect resolves `:memory:` URLs to `StaticPool` under
   the async engine (its sync-path `get_pool_class` names
   `SingletonThreadPool`, but the async engine got `StaticPool`);
   two sequential checkouts and two concurrent tasks all saw the same
   database. One shared connection ⇒ access serializes — the same
   posture as the fallback arm.
3. **Pragmas on `:memory:`** — **all accepted.** The sqlite profile's
   `file_settings` (`page_size = 16384`, `journal_mode = WAL`) and
   `session_settings` (`busy_timeout`, `synchronous`,
   `case_sensitive_like`) all ran without error; `journal_mode = WAL`
   answered `wal` (stock SQLite answers `memory` on a `:memory:` db —
   a divergence in the answer, not a failure). No profile variant
   needed on either arm.
4. **`insertmanyvalues`** — **sane, inherited.**
   `insertmanyvalues_max_parameters = 32700`,
   `use_insertmanyvalues = True`, `supports_multivalues_insert =
   True`, insert/update/delete RETURNING all declared `True` — the
   sqlite base dialect's values, as hoped.
5. **Suite speed** — measured on the fallback arm (the landed one):
   - Before (bespoke dict backend): **1807 passed, 594 skipped in
     11.28 s** (wall 12.2 s).
   - After (in-memory `DatabaseStorage`, aiosqlite + StaticPool):
     **1785 passed, 599 skipped in 17.24 s** (wall 18.1 s) — every
     memory-leg conformance row now provisions a real schema and
     runs SQL. ~1.5× wall-clock — inside the spec's ~2× line, so
     recorded, not raised as a finding. Count deltas: the deleted
     `test_backends_memory.py` carried 22 tests; on the memory leg
     the 13 restore/sweep skips now run while 18 grep/mkedge rows
     skip (the old backend implemented both; `DatabaseStorage`
     stubs them until their passes land — the in-memory default
     loses grep/mkedge for now, honestly declared).
6. **Full conformance on aioturso** — **fails wholesale on blocker
   3.** With blockers 1–2 shimmed, the `StorageContract` run on
   `sqlite+aioturso:///:memory:` gave **114 failed, 6 passed, 18
   skipped in 4.87 s**; every failure traced to first touch dying on
   the `memoryview` bind (the 6 passes are tests that never reach a
   verb, e.g. trait-vocabulary checks). No deeper triage is
   meaningful until the driver accepts binary parameters.

## Re-running the gate

The probe is kept beside this report, runnable on demand once the
dependency is present:

```sh
uv add "pyturso[sqlalchemy]"                 # temporary, for the probe
uv run python context/specs/084-turso-in-memory-backend/gate_probe.py
# decisive check (f): the conformance contract on aioturso :memory: —
# point a StorageContract subclass at sqlite+aioturso:///:memory: and
# run it with gate_shims.py loaded as a pytest plugin (-p), e.g.
#   PYTHONPATH=context/specs/084-turso-in-memory-backend \
#   uv run pytest <the-temp-leg-file> -p gate_shims
uv remove pyturso                            # the gate leaves no dependency
```

The Turso arm passes the gate when `gate_probe.py` runs clean with its
two shims deleted and the conformance leg is green.

## Upstream issues to file (left for the reviewer)

Against `tursodatabase/turso` (Python bindings):

1. `AsyncAdapt_turso_dbapi` lacks `has_stop` — dialect unusable on
   SQLAlchemy ≥ 2.0.46 (`create_async_engine` raises at import of the
   dialect). Also unfixed in 0.8.0rc1.
2. The async adapter should proxy `isolation_level` (as SQLAlchemy's
   own aiosqlite adapter does) so pool-checkout listeners can manage
   transaction control.
3. `turso.connect().execute()` rejects `memoryview` parameters even
   though the module exports `Binary = sqlite3.Binary = memoryview` —
   binary column round-trips fail under SQLAlchemy's sqlite dialects.

## Fallback-arm verification

`DatabaseStorage(url="sqlite+aiosqlite:///:memory:")` works with
**zero engine changes**: SQLAlchemy's aiosqlite dialect already
returns `StaticPool` for non-file databases (verified on the live
engine — no explicit `poolclass` needed), the pragmas above are all
safe on `:memory:`, and first touch, write, delete, restore, and
sweep all pass. Access serializes on the single shared connection —
the declared single-process posture (ADR 028 pin 4); the seam-based
concurrency tests stay on the engine legs.

Per the coordinator's design amendment: because Turso failed its
gate, **no `TursoStorage` class ships** — `InMemoryStorage` is a thin
subclass of `DatabaseStorage` directly, pinning the aiosqlite
in-memory URL. `TursoStorage` arrives when Turso clears the gate.
