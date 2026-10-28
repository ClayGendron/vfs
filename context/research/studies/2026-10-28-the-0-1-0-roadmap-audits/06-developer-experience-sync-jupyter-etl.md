# Audit — developer experience: sync calls, notebooks, ETL, install, docs, examples, host integration

Audited 2026-10-28 against the live tree at `/home/user/vfs` (read-only). Labels: READ = read the file, EXECUTED = ran it here, INFERRED = reasoned from evidence. Throwaway scripts are under `/tmp/claude-0/-home-user-vfs/b12de1a3-b6d8-5d68-8b2c-bafd27ab036c/scratchpad/dx/` (`exp123.py`, `exp4.py`, `exp5.py`, `exp6.py`, `exp7.py`).

One line: the async kernel and the 10k batch contract are solid; there is no sync facade at all, the docs tree is one-third stubs, five of seven example notebooks import dead names, and the install story still points at a pure-Python 0.0.22 on PyPI.

---

## 1. Built today

### 1.1 The public API is async-only

- Every verb on `VirtualFileSystem` is `async def`: `read` `src/vfs/base.py:902`, `stat` :915, `ls` :928, `tree` :941, `write` :958, `edit` :1010, `delete` :1053, `restore` :1088, `sweep` :1111, `mkdir` :1135, `mkedge` :1155, `rmedge` :1200, `move` :1227, `copy` :1240, `glob` :1257, `grep` :1349, `glean` :1463, `graph` :1524, `run` :1571, `grant` :1593, `revoke` :1617, `grants` :1628, `posture` :1640, `add_member` :1655, `remove_member` :1674; mount admin `bind` :408, `unbind` :486, `add_mount` :509, `remove_mount` :556, `remount` :581, `close` :650, `locate` :734. READ.
- The only synchronous public members: `__init__` :360, `mounts()` :693, `session()` :787, `capabilities()` :797. READ.
- `Session` (`src/vfs/session.py:36-415`) mirrors every verb, all `async def`; `__aenter__`/`__aexit__` only, no sync context manager. READ.
- **There is no sync facade.** `grep -rn "run_coroutine_threadsafe|greenlet_spawn|anyio|nest_asyncio|class Sync|run_until_complete|asyncio.run(" src/vfs` returns nothing. EXECUTED.
- `src/vfs/__init__.py` exports `VirtualFileSystem`, `Session`, `Authority`, `Principal`, `Path`, `Result`, `ResultError`, `PermissionMap`, `PermissionsPayload`, `MountInfo`, the exception classes and `permissions`. **Not exported at top level:** `Entry` (lives at `vfs.models`), `DatabaseStorage` / `InMemoryStorage` (`vfs.storage.backends`). An ETL dev needs three import lines before the first write. READ.

### 1.2 Engine construction and loop binding

- `EngineHost.__init__` (`src/vfs/storage/backends/database/engine.py:129-199`): `url=` XOR `session_factory=` (built vs borrowed) enforced at :140-145. The built path creates `create_async_engine` + `async_sessionmaker` at :175-184; a `StaticPool` engine (the `:memory:` default behind `InMemoryStorage`) is wrapped in `_SerializedSessions` :181. READ.
- The module docstring :1-13 states the intended notebook posture: "The borrowed path is single-loop by intent; in notebooks and sync-client pipelines, use the built path, which binds nothing to a loop until first touch." The `asyncio.Lock` is created lazily on first `ensure_ready` :196, :255-256, so construction is loop-free. READ.
- Pinned by `tests/storage/database/test_engine.py:300-317` (`test_construct_on_one_loop_first_touch_on_another`): construct on loop A, first-touch on loop B. **Not pinned:** first-touch on loop A then *use again* on loop B — the real "one `asyncio.run` per cell" notebook shape. READ.
- `DatabaseStorage.__init__` (`src/vfs/storage/backends/database/backend.py:186-243`) takes `url`, `session_factory`, `schema`, `embedder`, `native_embedding`, `posture`, wall budgets, renderers. READ.
- CPU offload: `src/vfs/storage/backends/database/offload.py` — one `ThreadPoolExecutor` per host (`OFFLOAD_WORKERS = os.cpu_count()` :65), used for grep verify and reindex chunk/posting passes; `base.py:137` `MEASURE_OFFLOAD_BYTES = 100_000` hops large-body sha256 to the loop's default executor. These are the tree's only threads today; none of them is a sync entry point. READ.
- `install_extensions()` is on `EngineHost` :271-296 (reached as `storage.install_extensions()` per `docs/how-to/provision-postgres-search.md:30`); it is a developer-plane verb on the **storage**, not on the router. READ.

### 1.3 Provisioning and the (absent) migration story

- First touch: `_verify_or_provision` :479-517 runs `metadata.create_all(checkfirst=True)` when the meta table is absent :492, then `_provision` :519-546 inserts the meta row (`schema_format_version=SCHEMA_FORMAT_VERSION`), the lock row, the posture grant row and the root entry. READ.
- `_adopt` :559-597: a stored `schema_format_version` that differs from the build's refuses `schema_mismatch` with "re-provision the mount". There is **no migration path, no alembic, no ALTER**: `grep -rli alembic src/vfs context/specs/active context/decisions` is empty. EXECUTED.
- `SCHEMA_FORMAT_VERSION: Final = 23` at `src/vfs/models/rows.py:139`. ADR 020 (`context/decisions/020-schema-format-version-policy.md`) says the constant "stays 1 until the first release". The constant has moved 22 times; the ADR is stale (see Risks). READ.
- Schema creation: vfs never runs `CREATE SCHEMA`; `schema=` requires the host to create it (spec 157 §Intent; memo item 19). READ.

### 1.4 The ETL batch contract

- `write(entries=...)` takes a list of `Entry` (`base.py:958-1008`). The storage plans the whole batch in memory and executes chunked inserts (`context/architecture/04-one-call-end-to-end.md`, write picture). READ.
- EXECUTED (`exp5.py`, statement counter via `before_cursor_execute` on `storage._host.engine.sync_engine`, the same pattern the suite uses at `tests/storage/database/test_writes.py:99-109`):

  | storage | rows | statements | INSERT | SELECT | success |
  |---|---|---|---|---|---|
  | `InMemoryStorage` | 2,000 | 26 | 7 | 9 | True, 2,000 rows back |
  | `DatabaseStorage` sqlite file | 2,000 | 26 | 7 | 9 | True |
  | `DatabaseStorage` sqlite file | 10,000 | 49 | 16 | 9 | True, 10,000 rows back |

  SELECT count is flat in N; INSERT/SAVEPOINT count grows by chunk, not by row. Read-back and `glob` on the written tree succeeded. Wall times (1.3 s / 7.3 s) are informational only, per the project's no-clock rule.
- Pins in the suite: `tests/storage/database/test_dialects.py:367` `BATCH_SIZES = [2_500, 10_000 (slow)]` under `TestMembershipChunking`; `test_writes.py:107-109` asserts `len(statements) <= 10` for 100 entries ("O(tables), never O(entries)"); `tests/storage/database/test_reads.py:529` 2,000 / 10k (slow); `test_trash.py:1020` 1k / 2k (slow). READ.
- `docs/how-to/bulk-load-as-the-system-actor.md:30` states "Batches of ten thousand entries in one call are supported; the backend chunks the statements." READ.

### 1.5 Install and release

- `pyproject.toml`: `requires-python = ">=3.11"`; maturin build; extras `openai`, `langchain`, `embed-local`, `postgres` (asyncpg+pgvector), `mssql` (aioodbc+pyodbc), `mariadb`, `oracle`, `pdf/docx/pptx/xlsx/documents`, `all`; dev group includes `ipykernel>=7.2.0`, `sybil`, `pytest-xdist`. READ.
- `.github/workflows/publish.yml`: triggers only `on: release: types: [published]`; builds abi3 wheels for linux x86_64/aarch64 (manylinux_2_28), musllinux x86_64/aarch64, macOS arm64/x86_64, windows x64, then `uv publish --trusted-publishing`. READ.
- PyPI today: latest `vfs-py` is `0.0.22`, files `vfs_py-0.0.22-py3-none-any.whl` + sdist — the **previous-generation pure-Python package**. `pip install vfs-py` (README:16) installs the old API, not this tree. EXECUTED (curl to pypi.org JSON).
- `pyproject.toml:14` and `src/vfs/__init__.py:1` both say `0.0.22`, the same number as that old release (memo item 6). READ.
- `vfs/native.py:26-41`: the compiled extension is required; no fallback. A host image without a wheel needs cargo (memo item 18). READ.
- `CONTRIBUTING.md:16-21` says `uv venv; uv pip install -e ".[all]"; uv pip install --group dev`; `docs/contributing.md:10-12` the same plus `--group docs`. `CLAUDE.md` says `uv sync --all-extras --group dev`. Two setup recipes. READ.

### 1.6 Docs (mkdocs Diátaxis tree)

29 Markdown files under `docs/`, 1,583 lines total. `uv run pytest docs README.md -q -o addopts=""` → **38 fences pass** (EXECUTED). The root `conftest.py` runs every `python` fence in README and the four Diátaxis dirs with a fresh SQLite `storage`/`fs` and top-level `await` allowed.

| Page | State |
|---|---|
| `tutorials/getting-started.md` (12 lines) | **stub** — header comment plus a one-line goal; no steps |
| `how-to/add-a-backend.md`, `how-to/expose-over-mcp.md` | **stubs** (6 lines, title only) |
| `how-to/provision-postgres-search.md` | real (pgvector install, `install_extensions`) |
| `how-to/run-calls-as-a-principal.md`, `share-a-folder-with-grants.md`, `walk-the-edges-around-a-file.md`, `bulk-load-as-the-system-actor.md` | real, fence-tested |
| `reference/api.md` | partial: only "Identity" and `graph`; no `read/write/edit/glob/grep/glean/...` entries |
| `reference/session.md`, `authority.md`, `glob-patterns.md`, `glossary.md` | real |
| `reference/query-engine.md`, `reference/metadata-paths.md` | **stubs** |
| `reference/` **no `Result` page, no `Entry` page, no `DatabaseStorage` page** | missing |
| `explanation/architecture.md`, `filesystem-internals.md`, `why-database-backed.md` | **stubs** |
| `explanation/` other seven pages | real essays |
| `docs/index.md` | a positioning essay; sections "2." and "4." are empty headings; ends in ~20 blank lines |

Not in `mkdocs.yml` nav (EXECUTED diff): `explanation/the-namespace-is-the-interface.md`, `explanation/why-mounts-expand-agent-capability.md`, `explanation/write-pipeline.md`, `how-to/share-a-folder-with-grants.md`, `how-to/walk-the-edges-around-a-file.md`.

No page covers: installing (extras table, wheel platforms), running in a notebook, running in a plain script/ETL, SQLite-file/MSSQL/Oracle setup, `Result` fields and error kinds as a table, the `Entry` model, or `DatabaseStorage` constructor options.

### 1.7 Examples

`examples/` has 9 files; it is in no CI step (`grep examples .github/workflows scripts/ci.sh` finds only the docs-fence step name). EXECUTED import extraction:

| File | Imports | Verdict |
|---|---|---|
| `glean_walkthrough.ipynb` | `vfs.VirtualFileSystem`, `vfs.models.Entry`, `vfs.paths.Path`, `vfs.results.preview.select_preview`, `vfs.storage.backends.DatabaseStorage` | **live names** (all exist: `preview.py:79`, `backends/__init__.py:9`) |
| `glob_residuation.ipynb` | `vfs.pattern_matching.glob._canonical`, `._component_matches` | live but **private** names (`glob.py:491`, `:508`) |
| `postgres_backend_playground.ipynb` | `vfs.backends.PostgresFileSystem`, `vfs.vector.Vector`, `vfs.models.postgres_native_vfs_object_model` | **dead** |
| `postgres_repo_glob_grep.ipynb` | `vfs.VFSClient`, `vfs.backends.postgres.PostgresFileSystem` | **dead** |
| `repo_postgres_cli_smoke.ipynb` | `vfs.backends.database.DatabaseFileSystem`, `vfs.client.VFSClient`, `vfs.models.VFSObject`, `sqlmodel` | **dead** |
| `story_001_demo.ipynb` | `DatabaseFileSystem`, `vfs.query.parser/executor/render/ast`, `vfs.results.VFSResult/Entry/LineMatch`, `sqlmodel` | **dead** |
| `cli_query_demo.py` | `grover.backends.database.DatabaseFileSystem`, `sqlmodel` | **dead** (pre-rename package name) |
| `demo_dbfs.py` | Flask, `src.models.user` | unrelated Flask demo, not vfs |
| `main.py` | `os` | trivial |

### 1.8 What a notebook user hits today — EXECUTED in a real ipykernel (`exp6.py`, cells sent through `jupyter_client`)

| Cell | Outcome |
|---|---|
| `fs = VirtualFileSystem(storage=InMemoryStorage())` | ok |
| `r = await fs.write(path='/n.txt', content='notebook')` | works (IPython autoawait) |
| `asyncio.run(fs.read('/n.txt'))` | `RuntimeError: asyncio.run() cannot be called from a running event loop` |
| `asyncio.get_event_loop().run_until_complete(fs.read(...))` | `RuntimeError: This event loop is already running` |
| `r = fs.read('/n.txt')` (forgot `await`) | silently a `<coroutine object>`; no error until GC warns |

Plain script (`exp123.py`): `asyncio.run(main())` with `InMemoryStorage` write+read → `(True, True, ['hello'])`. Nested `asyncio.run` inside a running loop reproduces the same two `RuntimeError`s.

Cross-loop reuse (`exp4.py`): one `InMemoryStorage` and one sqlite-file `DatabaseStorage`, written under `asyncio.run` (loop A), read under a second `asyncio.run` (loop B), closed under a third — all succeed. aiosqlite tolerates a loop change. INFERRED: asyncpg does not (ADR 002 :22-30 records "attached to a different loop"); no Postgres URL is set here (`env | grep VFS_TEST` → 0) so this leg is unverified today.

Dependencies present in the venv (EXECUTED): `greenlet 3.3.1` (via `sqlalchemy[asyncio]`), `anyio 4.12.1` (transitive only, via httpx/openai/jupyter_client/oracledb — not a vfs dependency), `nest_asyncio` (transitive, dev).

### 1.9 Option (a) prototype — EXECUTED (`exp7.py`)

A 25-line `SyncVirtualFileSystem` owning a private loop on a daemon thread, forwarding each coroutine verb through `asyncio.run_coroutine_threadsafe(...).result()`:

- plain script, no loop: 2,000-row `write(entries=)`, `read`, `glob` (2,000 rows), `mounts()`, `close()` — all succeed;
- inside a running loop, with the sqlite storage **already first-touched on the outer loop**: facade `read`/`write` on the thread loop succeed, and a subsequent `await` on the outer loop still works;
- `InMemoryStorage` (StaticPool + `_SerializedSessions`) under the same shape: succeeds.

---

## 2. In flight — specs and ADRs touching this domain

- **Spec 157** `context/specs/active/157-postgres-provisioning-for-host-apps/spec.md` (draft, 2026-10-08): first touch creates the schema via a `DialectProfile.schema_ddl`; `42501` → classified `unavailable` with `data={"schema","privilege"}`; bulk-insert mode chosen per driver (`copy` only on asyncpg, `core` elsewhere) so psycopg 3 session factories work; `VFS_TEST_POSTGRES_PSYCOPG_URL` leg; `vfs_nocreate` docker role. Out of scope by its own words: `ALTER` migrations. Unlanded. READ.
- **Spec 156** `.../156-mount-admission/spec.md` (draft): a router is not a storage; `add_mount(VirtualFileSystem)` must refuse at admission. Rule 1 (seal default root) dropped — the in-memory default root is "the owner's choice", README says so (spec 153). READ.
- **Memo** `context/research/2026-10-08-smartowl-workspace-integration-issues.md` — a real host integration. DX-relevant items: 3 (README example used non-existent classes), 6 (v2 still calls itself 0.0.22), 18 (no Linux wheel; host container has no cargo), 19 (schema by hand), 20 (asyncpg-only bulk path), 21 (rendering waits for whole-storage `reindex()` under a lease; hosts must retry `conflict`), 22 (cross-mount copy refused → spec 160), 23 (unverified default posture). READ.
- **ADR 002** `context/decisions/002-database-engine-ownership.md`: the built/borrowed XOR exists *because of* notebook loop poisoning with asyncpg; names "a standalone backend (notebooks, pipelines, the sync client)" as a first-class shape — the sync client it names no longer exists in `src/`. READ.
- **ADR 020** schema-format-version policy — stale against `SCHEMA_FORMAT_VERSION = 23`. READ.
- **ADR 087 / architecture 01 & 04**: the Python API is "the one front that is built"; MCP `serve()` (spec 171), shell (167), WASI (169b/172) are planned and each calls the same router methods — a sync facade is a fourth front by this model and must store no fact. READ.
- **Spec 153** (README says what the default root is) — referenced by 156; not read in full.

---

## 3. Gaps vs the 0.1.0 goal (theme 5: Jupyter sync calls + ETL; theme 2: engines; theme 6: MCP)

1. **No sync entry point.** A notebook user must `await`; a plain script must write `asyncio.run(main())` boilerplate around every pipeline; forgetting `await` is silent.
2. **The asyncpg + notebook hazard is undocumented and unpinned** in the live tree (only ADR 002 history). Whichever loop first-touches the engine owns it on asyncpg.
3. **Three imports to write a file**: `Entry`, `DatabaseStorage`/`InMemoryStorage` are not top-level exports.
4. **Docs**: no tutorial (stub), no install page, no notebook/ETL how-to, no SQLite-file/MSSQL/Oracle how-to, no `Result`/`Entry`/verb reference, five pages off the nav, `index.md` has empty sections, eight stub pages shipped under real titles.
5. **Examples**: five of seven notebooks plus one script import dead names (`vfs.backends.*`, `VFSClient`, `DatabaseFileSystem`, `vfs.query.*`, `sqlmodel`, `grover`); nothing runs them in CI.
6. **Install**: `pip install vfs-py` gives the old generation; the version number is shared; no Linux wheel for v2 on PyPI until a GitHub release is published; two contradictory setup recipes.
7. **Host provisioning**: spec 157 unlanded — `schema=` needs a hand-made schema; psycopg hosts cannot borrow sessions.
8. **Migration**: by design refuse-and-re-provision; fine pre-1.0 but undocumented for a host (how to detect, what "re-provision" means for existing data), and ADR 020 contradicts the code.
9. **`install_extensions` lives on the storage** — a host holding only `fs` cannot reach it without the storage handle; `mounts()` returns `MountInfo`, check whether it exposes the storage (not verified).
10. **`reindex()` is whole-storage under a lease** (memo 21) — an ETL pipeline that writes PDFs must call it and retry `conflict`; no path-scoped reindex.

---

## 4. Risks — wrong, stale, or contradictory

- **ADR 020 vs `rows.py:139`**: "stays 1 until first release" vs `23`. One of them must change before 0.1.0 declares a public format number. READ.
- **README:16 `pip install vfs-py`** installs `0.0.22 py3-none-any` — the old API. The alpha banner at :19 admits it, but the install line still sits above the banner. EXECUTED/READ.
- **README PyPI badge** advertises 0.0.22 as the version of this README's API. READ.
- **`CHANGELOG.md` Unreleased** describes SQLModel/`VFSEntry`/`DatabaseFileSystem` — the old generation. Stale. READ.
- **`engine.py:10-13` docstring** says notebooks should use the built path. True for aiosqlite (EXECUTED), unproven for asyncpg in the live suite; the sentence reads as a guarantee. READ/INFERRED.
- **`CONTRIBUTING.md:19-21`** (`uv pip install -e`) vs `CLAUDE.md` (`uv sync --all-extras --group dev --reinstall-package vfs-py` after Rust edits). A contributor following CONTRIBUTING will have a venv `uv sync` later strips of extras (CLAUDE.md records this happened 2026-09-04). READ.
- **`examples/cli_query_demo.py:12`** imports `grover.*` — a package name that predates `vfs`. READ.
- **`docs/how-to/index.md`** lists seven guides as plain text, two of which are stubs; the nav lists five. READ.
- **Forgotten `await` is silent** (EXECUTED C6). An ETL dev who writes `fs.write(...)` in a loop gets 10,000 un-awaited coroutines and no rows. A sync facade removes this class of error for its users; for the async API a `__del__` warning already exists only via CPython's "never awaited" RuntimeWarning.
- **`nest_asyncio` is importable in the dev venv** (transitive). A notebook user might patch the kernel loop with it; that path is unsupported and untested. EXECUTED.
- **Spec 157 line references** (`ensure_ready L260–277`, etc.) have drifted (`ensure_ready` is now :252). Cosmetic. READ.

---

## 5. Sync-facade design options and recommendation

Definitions: a *facade* is a thin front over the async kernel (ADR 087 sense: stores no fact). *Loop* = asyncio event loop. *Jupyter's loop* = the kernel already runs one on the main thread, so `asyncio.run` is refused (EXECUTED).

| Option | Mechanism | Works in Jupyter? | Works in plain script? | Touches kernel code? | New dependency? | Cost / risk |
|---|---|---|---|---|---|---|
| **(a) thread-loop wrapper** | facade owns a private loop on a daemon thread; each verb → `run_coroutine_threadsafe(...).result()` | yes (EXECUTED `exp7`) | yes (EXECUTED) | no | no | one thread hop per call (~tens of µs, fine for agents and ETL); engine must be first-touched on the facade's loop for asyncpg; `close()` must stop the loop; `contextvars` (hop budget) not inherited across the hop — fine, it is per-call state |
| (b) greenlet, SQLAlchemy-style | kernel written sync-style, `await_only()` at each I/O, async front wraps with `greenlet_spawn` | needs a loop at the top anyway | only with a sync driver stack | **rewrite of every `async def` in the kernel** | no (greenlet already present) | SQLAlchemy's bridge is "sync inside, async outside"; vfs is the inverse, so adopting it is a kernel rewrite; a loop-free sync caller still needs sync DB drivers (psycopg2, pyodbc, sqlite3) — a second backend |
| (c) `anyio.from_thread.start_blocking_portal` | same as (a) with anyio's maintained portal | yes | yes | no | **yes** (anyio becomes a core dep; today transitive only) | nicer API, cancellation handling, +1 dependency for ~30 lines of code |
| (d) unasync codegen (httpx/redis-py) | generate sync twins of every module at build time | yes | yes | needs a **sync storage path**: sync engine + sync drivers, sync offload, a second 10k write builder | build tooling | doubles the backend surface; MCP stays async; every statement-count pin runs twice; not a 0.1.0 shape |

**Recommendation: (a), as `vfs.sync` with `SyncVirtualFileSystem` and `SyncSession`.** It is the smallest correct design: ~100 lines, no new dependency, no kernel change, a fourth "front" exactly as ADR 087 describes fronts (owns only its machinery — a loop and a thread — stores no fact). Rules the story must pin:

1. **The facade owns the loop and the lifecycle.** `SyncVirtualFileSystem(storage=..., **vfs_kwargs)` constructs the `VirtualFileSystem` *itself* so that construction, first touch and close all happen on the facade's loop; `with SyncVirtualFileSystem(...) as fs:` and `fs.close()` stop the thread. Wrapping an already-touched async `fs` is allowed but documented as "SQLite only" until the asyncpg leg pins it.
2. **Explicit methods, not `__getattr__`**: each verb is written out with the async signature minus nothing, so `ty` and IDEs see the signatures; a parity test asserts the sync surface's parameter names, kinds and defaults equal the async surface's (the same test shape `docs/reference/session.md` describes for `Session`).
3. **Calling a sync verb from inside the facade's own loop thread is refused loudly** (deadlock guard: compare `threading.get_ident()`).
4. **MCP `serve()` stays async-native**; the facade is for notebooks, scripts and ETL only. Agents in-process keep the async API.
5. Thread-safety: `run_coroutine_threadsafe` serializes all facade calls onto one loop, so a multi-threaded ETL (one facade shared by a `ThreadPoolExecutor`) is safe by construction; concurrency inside the loop is still the kernel's.

(c) is the fallback if cancellation/KeyboardInterrupt handling in notebooks turns out to need more than `.result()` gives — anyio's portal handles Ctrl-C into a blocked `.result()` cleanly; (a) needs a small `try/except KeyboardInterrupt → future.cancel()` wrapper, which the prototype did not test.

---

## 6. Proposed roadmap stories

### DX-1 — `vfs.sync`: a synchronous facade for notebooks and scripts

**Why.** Theme 5 says vfs runs in a Jupyter notebook with sync calls and works in ETL pipelines. Today every verb is `async def` (base.py:902-1690), a notebook cell cannot `asyncio.run` (EXECUTED), and a plain script needs an `asyncio.run(main())` harness. The smallest correct design is a facade owning a private loop on a background thread (EXECUTED prototype, §1.9/§5), which adds a fourth front in ADR 087's sense and touches no kernel code.

**Depends on.** Nothing in the tree; a Postgres leg run for the asyncpg criterion (db_test skill).

**Acceptance criteria.**
- `from vfs.sync import SyncVirtualFileSystem`; `with SyncVirtualFileSystem(storage=InMemoryStorage()) as fs: fs.write(path="/a.txt", content="x"); fs.read("/a.txt")` returns `Result`s with `success is True` in a plain `python -c` with no running loop.
- The same cells, executed through a real ipykernel (`jupyter_client`, the pattern in `exp6.py`), succeed while the kernel loop is running; no `RuntimeError` and no `nest_asyncio`.
- A parity test asserts, for every verb named in `docs/reference/session.md`, that `inspect.signature(SyncVirtualFileSystem.<verb>)` equals `inspect.signature(VirtualFileSystem.<verb>)` (names, kinds, defaults, order) and that `SyncSession` matches `Session` likewise.
- A sync call issued from the facade's own loop thread (e.g. inside a reranker or callback) returns a classified `invalid` result naming the deadlock, never hangs; pinned with a `Reranker` stub.
- `fs.close()` and `__exit__` stop the loop thread; `threading.enumerate()` shows no `vfs-sync-loop` thread afterwards; a verb after close returns the router's `closed` error, not a raised exception.
- On the Postgres leg: `SyncVirtualFileSystem(storage=DatabaseStorage(url="postgresql+asyncpg://…"))` serves `write` then `read` from a script whose main thread runs its own `asyncio.run` in between (the asyncpg loop-affinity case); and wrapping an async `fs` already first-touched on the main loop is refused or documented as unsupported, pinned either way.
- A 10,000-entry `fs.write(entries=...)` through the facade lands with the same statement count the async path pins in `test_dialects.py::TestMembershipChunking` (counted with `before_cursor_execute`, never timed).
- `scripts/ci.sh` green; the new module at 100% coverage.

### DX-2 — ETL ergonomics: top-level exports and one-import pipelines

**Why.** Writing one file today takes `from vfs import VirtualFileSystem`, `from vfs.models import Entry`, `from vfs.storage.backends import DatabaseStorage`. The ETL audience (10k batches in one call) should get `Entry`, `DatabaseStorage`, `InMemoryStorage` and the sync facade from `vfs` directly, and `write(entries=)` should accept any iterable of `Entry`, not only a list (verify current `_as_list` at base.py:1697).

**Depends on.** DX-1 for the sync export.

**Acceptance criteria.**
- `from vfs import Entry, DatabaseStorage, InMemoryStorage, SyncVirtualFileSystem` imports; `__all__` lists them; `tests/test_dependencies.py`'s walk still loads no numpy.
- `fs.write(entries=(Entry(...) for _ in range(10_000)), parents=True)` (a generator) succeeds with the same statement count as a list; pinned at 2,500 by default and 10,000 under `slow`.
- A router-level pin (not only storage-level) counts statements for a 10k `write` through `VirtualFileSystem`, including the parents walk, and asserts the count is independent of N beyond chunk arithmetic.
- The README quick-start uses only top-level imports and is fence-tested by Sybil.

### DX-3 — Getting-started tutorial, notebook how-to, ETL how-to (fence-tested)

**Why.** `docs/tutorials/getting-started.md` is a 12-line stub; no page says how to run vfs in a notebook or a script. The Sybil harness already turns fences into tests (38 pass today), so each page is executable documentation.

**Depends on.** DX-1, DX-2.

**Acceptance criteria.**
- `docs/tutorials/getting-started.md`: install → construct → write → `glob`/`grep`/`glean` → one `Result` rendered, every step a fence Sybil runs; the page needs no Postgres.
- `docs/how-to/use-vfs-in-a-notebook.md`: the `SyncVirtualFileSystem` path and the `await` path side by side, with the two `RuntimeError`s from §1.8 named as "what you will see if you try `asyncio.run`".
- `docs/how-to/bulk-load-from-a-pipeline.md`: a 10k-row batch from a CSV/parquet-shaped iterable, the whole-batch-atomic rule ("one bad row writes nothing"), `reindex()` after binary writes and its `conflict` retry.
- Every new page is in `mkdocs.yml` nav; a test asserts every `docs/**/*.md` is referenced by the nav (closes the five-page drift today).
- `uv run pytest docs README.md -o addopts=""` green.

### DX-4 — Reference pages for `Result`, `Entry`, every verb, and `DatabaseStorage`

**Why.** `docs/reference/api.md` documents only identity and `graph`; there is no `Result` page although every verb returns one and the README sells "one result type, classified errors". Reference is the Diátaxis quadrant an ETL dev and an MCP integrator both read.

**Depends on.** None (can run in parallel with DX-1).

**Acceptance criteria.**
- `docs/reference/result.md`: `Result` fields, `Observation` columns, `ResultError` fields, the `ErrorKind` table generated from `vfs.results.kinds` (a test asserts every kind in the enum appears on the page), `|` merging, `to_payload`/`from_payload`, `__str__`.
- `docs/reference/verbs.md` (or one page per family): every public verb on `VirtualFileSystem` with its signature; a test asserts the set of verbs on the page equals the set of `async def` public methods on the class.
- `docs/reference/storage.md`: `DatabaseStorage.__init__` parameters with defaults; built vs borrowed; `install_extensions`; the schema-mismatch refusal and what "re-provision" means.
- The three reference stubs (`query-engine.md`, `metadata-paths.md`, and the empty parts of `api.md`) are either filled or deleted and removed from the nav; no page under `docs/` is a header comment with no body.

### DX-5 — Per-engine how-tos and an install page (theme 2)

**Why.** Only Postgres has a how-to. 0.1.0 names SQLite, Postgres, MSSQL and Oracle. Each has one or two facts a dev needs (driver extra, URL shape, sqlite-vec loaded automatically, pgvector superuser step, ODBC driver for MSSQL, Oracle 23ai for vector). An install page is where extras and wheel platforms are listed.

**Depends on.** Spec 157 for the Postgres schema/psycopg paragraphs.

**Acceptance criteria.**
- `docs/how-to/install.md`: extras table generated from `pyproject.toml` (a test asserts every extra name appears), the wheel-platform list from `publish.yml`, the "no Rust toolchain needed on a listed platform" statement, Python 3.11–3.14.
- One how-to each for SQLite (file URL, `:memory:` default root, concurrency note), Postgres (existing page extended), SQL Server, Oracle: URL, extra, provisioning privilege, the first-touch refusal text when the vector function is absent.
- Each engine page's fences run under Sybil where SQLite suffices, and the engine-specific fences are `<!-- skip: next -->` with the exact text pinned by the corresponding engine-leg conformance test.
- `CONTRIBUTING.md` and `docs/contributing.md` use the `uv sync --all-extras --group dev` recipe from `CLAUDE.md`; one recipe, three places agreeing (a grep test or the docs fence).

### DX-6 — Examples: delete the dead, run the live

**Why.** Five of seven notebooks and one script import names that do not exist; the directory is a trap for a new user and is in no CI step.

**Depends on.** DX-3 (so the deleted notebooks' intent survives as docs).

**Acceptance criteria.**
- `examples/postgres_backend_playground.ipynb`, `postgres_repo_glob_grep.ipynb`, `repo_postgres_cli_smoke.ipynb`, `story_001_demo.ipynb`, `cli_query_demo.py`, `demo_dbfs.py`, `main.py` are removed (or `src2`-style archived outside `examples/`).
- `glean_walkthrough.ipynb` is executed in CI (nbclient/papermill via `ipykernel`, already in the dev group) against the live tree; `glob_residuation.ipynb` either uses public names or is removed.
- A test asserts no file under `examples/` imports `vfs.backends`, `vfs.client`, `vfs.query`, `sqlmodel`, or `grover`.

### DX-7 — Release hygiene for 0.1.0: version, wheels, changelog, schema-version policy

**Why.** `pip install vfs-py` installs the old generation; the tree calls itself the same `0.0.22`; `CHANGELOG.md` describes SQLModel-era changes; ADR 020 says the schema number is 1 while the code says 23; a host without cargo cannot install until a GitHub release publishes wheels (memo 18).

**Depends on.** Clay's decisions in §7 (version line, schema-number policy).

**Acceptance criteria.**
- `pyproject.toml` and `vfs.__version__` move off `0.0.22` (`0.1.0a1` or whatever Clay picks); a test asserts they agree.
- `CHANGELOG.md` `[Unreleased]` describes this tree; the old-generation entries move under their own released heading.
- ADR 020 is superseded or amended so the policy matches `SCHEMA_FORMAT_VERSION = 23` and says what 0.1.0 stamps; `docs/reference/storage.md` states the refuse-and-re-provision contract (no migrations in 0.1.0).
- A pre-release tag publishes wheels via `publish.yml`; `pip install vfs-py==<pre>` on a `manylinux_2_28` x86_64 container with no cargo imports `vfs.native` successfully (a workflow job, not a local test).
- README's install block names the pre-release pin and the alpha banner moves above it.

### DX-8 — Land spec 157 (host provisioning) and name `install_extensions` from the router

**Why.** The one real host integration (SmartOwl) hit `schema=` requiring a hand-made schema and an asyncpg-only bulk path. Spec 157 decides both. Separately, `install_extensions` lives on the storage only; a host holding `fs` should be able to run it per mount.

**Depends on.** Spec 157 (storage domain); the Postgres leg with a psycopg URL.

**Acceptance criteria.** Spec 157's own four criteria, plus:
- `fs.mounts()` exposes enough to reach each mount's `install_extensions` (or the router gains a thin `await fs.install_extensions(path)` admin verb that fans to the mount); pinned on SQLite as a no-op success and on Postgres as the real install.
- `docs/how-to/provision-postgres-search.md` gains the `schema=` paragraph and the psycopg borrowed-session paragraph.

---

## 7. Open questions for Clay

1. **Facade shape**: (a) hand-written thread-loop facade with no new dependency, or (c) `anyio` portal (one new core dependency, better Ctrl-C handling)? Recommendation is (a).
2. **Facade ownership rule**: must `SyncVirtualFileSystem` always construct the `VirtualFileSystem` itself (safe on asyncpg), or may it wrap an existing async `fs` (convenient in notebooks that already awaited once; safe on SQLite today, EXECUTED; unsafe on asyncpg per ADR 002)? Both can ship if the wrap path is documented as SQLite-only until pinned.
3. **Top-level exports**: is `from vfs import Entry, DatabaseStorage, InMemoryStorage` wanted, or is the three-module import deliberate layering?
4. **Version line for the rebuild**: `0.1.0a1` now (so a Linux wheel can exist on PyPI before 0.1.0), or stay at `0.0.22` until the release?
5. **Schema number policy**: amend ADR 020 to "the number moves on every incompatible change, 0.1.0 ships at N" (what the code already does), or reset to 1 at 0.1.0 as ADR 020 planned? Either way: refuse-and-re-provision stays the contract for 0.1.0 (no alembic) — confirm.
6. **Examples**: delete the stale notebooks outright (git history keeps them) or move them beside `src2/` as archived quarry?
7. **Docs scope for 0.1.0**: the minimum here is one tutorial, three how-tos (notebook, pipeline, install), four engine how-tos, and three reference pages (`Result`, verbs, storage). Is that the bar, or is a smaller set acceptable for 0.1.0?
8. **Path-scoped `reindex()`** (memo item 21): a pipeline that writes binary bodies must run a whole-storage reindex under a lease and retry `conflict`. Is a per-path/per-batch render in scope for 0.1.0, or documented as the contract?
9. **CONTRIBUTING recipe**: converge on `uv sync --all-extras --group dev` (CLAUDE.md) and drop `uv pip install -e`?
