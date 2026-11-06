# FastAPI developers pick sync or async per function, and every library they pair with FastAPI answers with two classes of the same method names; the one placement that hurts them is a blocking call inside `async def`, and the one that fools them is a forgotten `await` that still returns 200

The question: how FastAPI and Starlette serve `def` and `async def`, what the FastAPI population expects of a library called from an endpoint and from a background task, and which shape the libraries that population pairs with FastAPI chose. The time box was 45 minutes. When it ran out, the code reading of FastAPI, Starlette and six paired libraries was done, two executed experiments over the real vfs router and the real `SyncVirtualFileSystem` inside a real FastAPI app were done, and the web design discussions were read only through search-result summaries, because the session's network refused `mongodb.com` and `psycopg.org` (both named under "What this study does not settle").

## Sources

Clones, all shallow and read-only under `/home/user`, licence checked first: `fastapi` 1ca09c1 (2026-11-05, MIT); `starlette` 271c277 (2026-11-06, BSD-3-Clause, Encode); `httpx` b5addb6 (2026-02-23, BSD-3-Clause, Encode); `httpcore` 10a6582 (2025-10-13, BSD-3-Clause, Encode); `sqlalchemy` 9a77da0 (2026-11-03, MIT); `sqlmodel` 6a939fb (2026-11-02, MIT); `redis-py` 21c5ae8 (2026-11-06, MIT); `mongo-python-driver` (pymongo) 039144e (2026-11-05, Apache-2.0); `psycopg` 7dee51c (2026-11-04, LGPL-3.0, studied only, nothing copied). Motor was not cloned: it is deprecated in favour of pymongo's own async API, and pymongo is the live code.

vfs files read at the working tree of 2026-11-06: `src/vfs/base.py` (the async router, `VirtualFileSystem`, every verb `async def`, `asyncio.Lock` at line 391) and `src/vfs/sync.py` (the facade, `SyncVirtualFileSystem`, one loop on one daemon thread, `run_coroutine_threadsafe` at line 678).

Installed versions in the experiments: fastapi 0.162.0, starlette 1.10.0, httpx 0.28.1, CPython 3.13, added only to an ephemeral `uv run --with` overlay; the project environment was not changed.

Experiments: [experiments/01-fastapi-placement/placement.py](experiments/01-fastapi-placement/placement.py) with its output [placement.out](experiments/01-fastapi-placement/placement.out), and [probe_errors.py](experiments/01-fastapi-placement/probe_errors.py) with [probe_errors.out](experiments/01-fastapi-placement/probe_errors.out).

Web, read 2026-11-06 as search-result summaries only (the pages themselves could not be fetched from this session): MongoDB's PyMongo migration guide from Motor, https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/ and Motor's page https://www.mongodb.com/docs/drivers/motor ; Daniele Varrazzo, "Automatic async to sync code conversion", https://psycopg.org/articles/2024/09/23/async-to-sync (2024-09-23).

Labels: EXECUTED means I ran it in this session and report its output; READ means I read the cited file or page; INFERRED means my own reasoning from the evidence.

## The answer in one paragraph

FastAPI never asks a library to be both. It asks the developer to choose, per function, between `def` (FastAPI runs it on an anyio worker thread, at most 40 at once) and `async def` (FastAPI awaits it on the server loop), and its own documentation tells the developer to choose by the library: "if a library tells you to call it with `await`, use `async def`; if it doesn't, use `def`; if you just don't know, use `def`". Every library this population pairs with FastAPI answers that rule the same way: two classes, same method names, the async one prefixed `Async` (httpx `Client`/`AsyncClient`, psycopg `Connection`/`AsyncConnection`, pymongo `MongoClient`/`AsyncMongoClient`, SQLAlchemy `Session`/`AsyncSession`), or, in redis-py, the same class name in a second module (`redis.Redis`/`redis.asyncio.Redis`). Three of them generate the sync class from the async source so the two cannot drift. Executed inside a real FastAPI app over the real vfs router, both of today's vfs classes work in the placement they are meant for, at the expected concurrency, including in background tasks. Two placements go wrong, and both are the developer's choice of class, not a defect of a class: the sync facade inside `async def` serialised 100 requests into 5.7 seconds with the server loop frozen the whole time, and an async verb called without `await` inside `async def` returned HTTP 200 whose body was the text of a coroutine object. So, for this population, the expected shape is class twins with identical verb names; the dream shape (one class, awaited or not) works in the placements I ran, but it turns the forgotten `await` from a type error into a silent success, and that is the failure FastAPI developers already meet most.

## 1. How FastAPI and Starlette serve `def` and `async def`

READ: Starlette decides once per callable with `is_async_callable`, which unwraps `functools.partial` and checks `iscoroutinefunction` on the object or its `__call__` (`/home/user/starlette/starlette/_utils.py:61-65`). A plain function is wrapped in `run_in_threadpool` (`/home/user/starlette/starlette/routing.py:55`), and `run_in_threadpool` is one line over `anyio.to_thread.run_sync` (`/home/user/starlette/starlette/concurrency.py:32-34`).

READ: FastAPI copies that decision into its own request handler (`/home/user/fastapi/fastapi/routing.py:134-138`), classifies the endpoint once with `_is_coroutine_callable` (`/home/user/fastapi/fastapi/routing.py:416`, defined at `/home/user/fastapi/fastapi/dependencies/models.py:223`), and then either awaits the endpoint or sends it to the threadpool (`/home/user/fastapi/fastapi/routing.py:363-376`). It even moves response validation to the threadpool when the endpoint was sync (`/home/user/fastapi/fastapi/routing.py:335-340`).

READ: Dependencies follow the same rule. An `async def` dependency is awaited; a plain one goes to `run_in_threadpool` (`/home/user/fastapi/fastapi/dependencies/utils.py:730-733`). A generator dependency with `yield` is wrapped as an async context manager if it is an async generator, else as a sync one whose `__enter__` and `__exit__` run on worker threads (`/home/user/fastapi/fastapi/dependencies/utils.py:623-631`). The `__exit__` runs under its own one-token limiter so a full threadpool cannot deadlock a database pool's release (`/home/user/fastapi/fastapi/concurrency.py:17-41`, the reason is in the comment at lines 21-26).

READ: Background tasks follow the same rule. `BackgroundTask` records `is_async_callable(func)` at construction and either awaits the function or runs it in the threadpool after the response is sent (`/home/user/starlette/starlette/background.py:12-23`); FastAPI's `BackgroundTasks` is a subclass (`/home/user/fastapi/fastapi/background.py`). The FastAPI tutorial says the task "can be an `async def` or normal `def` function" (`/home/user/fastapi/docs/en/docs/tutorial/background-tasks.md:28`).

READ: Middleware, lifespan and WebSocket endpoints are async only. `BaseHTTPMiddleware.dispatch` is `async def` (`/home/user/starlette/starlette/middleware/base.py:210`), the documented `@app.middleware("http")` example is `async def` (`/home/user/fastapi/docs_src/middleware/tutorial001_py310.py:9`), and the lifespan is turned into an `asynccontextmanager` (`/home/user/fastapi/fastapi/routing.py:2597`).

READ: The documented rule for the developer is in `/home/user/fastapi/docs/en/docs/async.md:9-50`: use `async def` when the library tells you to `await` it; use `def` when the library has no `await` support, "this is currently the case for most database libraries"; "If you just don't know, use normal `def`"; and mix the two freely. Lines 418-430 say a `def` endpoint or dependency runs "in an external threadpool that is then awaited". Lines 434-438 add that a utility function the developer calls directly is never moved to a thread: FastAPI only manages the functions it calls itself.

READ: The SQL tutorial, the page this population copies to wire a database, is fully synchronous: SQLModel's sync `create_engine` and `Session`, a `yield` dependency, and every endpoint a plain `def` (`/home/user/fastapi/docs_src/sql_databases/tutorial001_an_py310.py:4-67`). SQLModel's own FastAPI tutorial explains `check_same_thread=False` by saying that "in FastAPI each request could be handled by multiple interacting threads" (`/home/user/sqlmodel/docs/tutorial/fastapi/simple-hero-api.md:40`).

READ: Starlette itself already ships a sync front over an async core with the mechanism `vfs.sync` uses. `TestClient` is a synchronous client that drives the async app through an anyio blocking portal, a loop on another thread that each sync call hands work to and waits on (`/home/user/starlette/starlette/testclient.py:406-415`). FastAPI developers use it in every test suite the docs teach (`/home/user/fastapi/docs/en/docs/tutorial/testing.md`).

EXECUTED: the anyio default thread limiter has 40 tokens (first line of `placement.out`). INFERRED: that is the ceiling on concurrent `def` endpoints and `def` dependencies per process, whatever library they call.

## 2. What happens to each vfs placement inside a real FastAPI app

EXECUTED: `placement.py` mounts the real vfs router and the real `SyncVirtualFileSystem` (over a subclass whose `read` awaits a 50 ms sleep, standing in for network storage) into a FastAPI app, fires 100 concurrent requests per route through `httpx.ASGITransport`, counts the peak number of reads in flight, and runs a 5 ms heartbeat task on the server loop to see whether the loop is ever frozen. The results, from `placement.out`:

| Placement | Statuses | Peak reads in flight | Wall | Longest loop freeze |
|---|---|---|---|---|
| a. `async def`, `await router.read()` | 100 × 200 | 100 | 0.58 s | 18 ms |
| b. `def`, `facade.read()` | 100 × 200 | 40 | 0.63 s | 28 ms |
| c. `async def`, `facade.read()` (no await) | 100 × 200 | 1 | 5.68 s | 5,683 ms |
| d. `def`, `asyncio.run(router.read())` | 96 × 500, 4 × 200 | 40 | 0.21 s | 15 ms |
| e. `async def`, `router.read()` with the `await` forgotten | 2 × 200 | 0 | 0.01 s | 6 ms |
| f. `async def`, `asyncio.run(router.read())` | 2 × 500 | 0 | 0.01 s | 6 ms |
| g. `async def`, `await dual_read()` (a context-detecting stand-in) | 100 × 200 | 100 | 0.50 s | 21 ms |
| h. `def`, `dual_read()` | 100 × 200 | 40 | 0.63 s | 16 ms |
| i. `async def` endpoint with the router from an `async def` dependency | 100 × 200 | 100 | 0.56 s | 15 ms |

EXECUTED: (a) and (i) are the async router where FastAPI expects it: full concurrency. (b) is the sync facade where FastAPI expects it: correct, capped at the 40 worker threads, and the endpoint ran on "AnyIO worker thread". One facade served all 40 worker threads through its single loop thread, and only one `vfs-sync-loop` thread was alive at the end.

EXECUTED: (c) is the textbook FastAPI mistake, a blocking call inside `async def`. Every answer was correct, so no test or log flags it, but the 100 requests ran one at a time and the heartbeat ticked once in 5.7 seconds: the whole server, every other route included, was frozen.

EXECUTED: (e) is the other textbook mistake. The endpoint returned HTTP 200 with the body `{"text":"<coroutine object Slow.read at 0x...>"}` (`probe_errors.out`). The only signal was the `RuntimeWarning: coroutine 'Slow.read' was never awaited` on stderr. (f) failed loudly with `asyncio.run() cannot be called from a running event loop`.

EXECUTED: (d) is what a developer writes when given "async only with a documented bridge" and a `def` endpoint: `asyncio.run` per call over one shared router. One thread at a time, 40 of 40 calls succeeded; eight threads at a time, 40 calls gave 1 success, 38 `RuntimeError: <asyncio.locks.Lock ...> is bound to a different event loop`, and 1 call that hung past its 5 s cap (`probe_errors.out`). INFERRED: the lock is created once per router and binds to the first loop that contends it; `src/vfs/base.py:391` is one such lock, and a database engine's pool binds the same way, which is why `sync.py` owns one loop for its storage.

EXECUTED: background tasks. A `def` task calling the facade, an `async def` task awaiting the router, and the bound methods `router.write` and `facade.write` passed straight to `add_task` all ran and wrote their files. Starlette classified the bound async method as async (`is_async_callable(router.read)` is True) and ran it on the main thread; it classified the facade's method as sync and ran it on a worker thread.

EXECUTED: the dual-mode stand-in, a plain `def` that returns a coroutine when a loop is running in its thread and a value when not, worked in (g) and (h), and as a background task it was classified as sync and ran on a worker thread, where it found no loop and returned a `Result`. INFERRED: FastAPI never sees the dual nature; it treats the dual function as sync everywhere it inspects one (dependencies, background tasks, endpoints passed directly), so a dual `fs.read` given to `Depends` or `add_task` takes the threadpool path even under an async app. That costs a worker thread and the 40-token cap, though it stays correct.

## 3. Which shape the paired libraries chose, and why

READ: httpx is class twins with identical method names. `Client` and `AsyncClient` share a `BaseClient` that holds every piece that does no I/O (`/home/user/httpx/httpx/_client.py:188`, `594`, `1307`), and each twin writes its own I/O path (`_send_single_request` at lines 1001 and 1717). Its docs say "HTTPX offers a standard synchronous API by default" and that inside an async framework "you'll also want to use an async client" (`/home/user/httpx/docs/async.md:3-11`). The `Response` model, which both clients return, carries name twins on one object (`read`/`aread`, `iter_bytes`/`aiter_bytes`, `close`/`aclose`) and raises `RuntimeError("Attempted to call a sync iterator on an async stream.")` on the wrong one (`/home/user/httpx/httpx/_models.py:876-1048`).

READ: httpcore, httpx's engine, writes only the async source and generates the sync package with a token substitution script, `async def` to `def`, `await ` to nothing, `Async` prefixes stripped (`/home/user/httpcore/scripts/unasync.py:6-27`), and its `check` script fails when the generated copy differs (`/home/user/httpcore/scripts/check:14`).

READ: psycopg 3 is class twins in one package: `Connection` and `AsyncConnection` (`/home/user/psycopg/psycopg/psycopg/connection.py:58`, `/home/user/psycopg/psycopg/psycopg/connection_async.py:62`). The protocol is written once as I/O-free generators that yield "wait for the socket" states (`/home/user/psycopg/psycopg/psycopg/generators.py:1-16`), driven by a sync `wait` or an async `wait_async` (`/home/user/psycopg/psycopg/psycopg/waiting.py:158`). The user-facing sync files are generated from the async ones by an AST rewriter (`/home/user/psycopg/tools/async_to_sync.py:1-30`) and carry "auto-generated ... DO NOT CHANGE" (`/home/user/psycopg/psycopg/psycopg/connection.py:1-3`). READ (search summary of the 2024 post): until 3.1 the two variants were kept in step by hand with "cumbersome and noisy diffs", which is why the async code became the single source.

READ: pymongo is the same choice, made late. `pymongo.asynchronous` is the source, `pymongo.synchronous` is generated by `tools/synchro.py` with `unasync` and a rename table (`AsyncMongoClient` to `MongoClient`, `AsyncCollection` to `Collection`; `/home/user/mongo-python-driver/tools/synchro.py:1-30`), and a module flag `_IS_SYNC` covers the few behaviours that differ (`/home/user/mongo-python-driver/pymongo/asynchronous/mongo_client.py:155`, `966`). The changelog says 4.9 refactored internals "to support the new asynchronous API" and broke Motor below 3.6 (`/home/user/mongo-python-driver/doc/changelog.rst:715-719`). READ (search summary of MongoDB's migration guide): Motor, the earlier async driver, "relies on a thread pool to perform network operations", which "can lead to performance degradation"; it is deprecated as of 2025-05-14 in favour of the native async API. INFERRED: the one library in this set that once shipped async as a thread-hop facade over sync code retired it for performance; vfs's facade is the mirror image (sync as a thread hop over async), whose cost lands on the sync caller, who already sits on a worker thread in FastAPI.

READ: SQLAlchemy 2 is class twins by wrapping: `AsyncSession` is a proxy over a sync `Session` (`/home/user/sqlalchemy/lib/sqlalchemy/ext/asyncio/session.py:215`), every async method runs the sync method in a greenlet with `greenlet_spawn` (for example lines 652, 974, 1031), and `run_sync` hands a sync function the sync session (line 539). Any I/O reached outside that greenlet, typically a lazy-loaded attribute, raises `MissingGreenlet: ... Was IO attempted in an unexpected place?` (`/home/user/sqlalchemy/lib/sqlalchemy/util/concurrency.py:150-159`), and the docs devote a section to "Preventing Implicit IO when Using AsyncSession" with `AsyncAttrs.awaitable_attrs` as the escape (`/home/user/sqlalchemy/doc/build/orm/extensions/asyncio.rst:354-409`). The docs also warn that one `AsyncSession` "is not safe for use in multiple, concurrent tasks" (lines 159-163). SQLModel adds only an `AsyncSession` subclass with an async `exec` (`/home/user/sqlmodel/sqlmodel/ext/asyncio/session.py:30-70`), and its docs never teach it: the only `async` in its docs outside the release notes is a link to FastAPI's page.

READ: redis-py is module twins with identical class names: `redis.client.Redis` and `redis.asyncio.client.Redis` (`/home/user/redis-py/redis/client.py:213`, `/home/user/redis-py/redis/asyncio/client.py:166`). Both inherit one set of command mixins whose method body is shared and returns whatever `execute_command` returns, a value or an awaitable (`ResponseT = Union[Awaitable[Any], Any]`, `/home/user/redis-py/redis/typing.py:56`). To give each client its real return type, every command now carries two `@overload`s keyed on `self: SyncClientProtocol` or `self: AsyncClientProtocol` (`/home/user/redis-py/redis/commands/core.py:122-145`), protocols told apart by a `Literal` marker attribute `_is_async_client` (`/home/user/redis-py/redis/typing.py:22-37`, set at `redis/client.py:229` and `redis/asyncio/client.py:182`). EXECUTED: `grep -c "@overload" redis/commands/core.py` printed 704.

INFERRED: the six libraries agree on three things. The sync and async faces are separate types, so a type checker knows which one the developer holds. The method names are the same on both, so the developer's knowledge carries over and only the `await` changes. And the two faces are produced from one source (generation in httpcore, psycopg and pymongo; a shared base plus wrapping in httpx and SQLAlchemy; shared mixins plus 704 overloads in redis-py), because hand-kept twins drift. None of the six offers one object whose method is sometimes awaitable; the closest is redis-py's shared mixin, whose cost is exactly the overload wall needed to hide it from the type checker.

## 4. What the FastAPI population expects of a library

INFERRED from section 1 and 3: a FastAPI developer decides `def` or `async def` by asking "does this library tell me to `await`?" and expects the library to answer with an import. They expect to build the client once (at module level for sync libraries, in the lifespan for async ones, because async engines bind to the server's loop), hand it to endpoints through a dependency, often a `yield` dependency that closes it, and call it from background tasks in whichever style the task was written in. They expect a context manager on both faces (`with`, `async with`). They expect the async face never to block the loop, and the sync face to be safe across worker threads, because FastAPI will call it from up to 40 at once.

EXECUTED and READ together: today's vfs pair already meets those expectations in placement. The router is safe in `async def` endpoints, dependencies and tasks (a, i, background); the facade is safe in `def` endpoints and tasks from many worker threads at once (b, background), with one loop for its storage. INFERRED: what departs from the population's habit is the naming: `vfs.VirtualFileSystem` (async) beside `vfs.sync.SyncVirtualFileSystem` reverses the httpx, psycopg and pymongo convention, where the unprefixed name is sync and the async twin carries `Async`.

## 5. Evidence apart from opinion

The evidence is sections 1 to 3: FastAPI's dispatch rule as code and as documentation, the eight-plus-one placements as measured, and the six libraries' shapes and generation tooling as read. What follows is opinion. A FastAPI developer will not notice which mechanism sits behind the sync face; they will notice the import, the class name, whether their type checker flags a missing `await`, and whether their server freezes. The naming convention is the cheapest of these to match. The freeze in placement (c) cannot be prevented by any shape, because a library cannot tell a blocking call in `async def` from a blocking call in a worker thread without inspecting the caller's thread; it can only be made less likely by keeping the async face the obvious one in async code. The silent 200 in placement (e) can be prevented, by a type checker, only if the async and sync faces are different types.

## Deliverable (a): what this population types without reading docs

A read, in an endpoint, written both ways because a FastAPI developer writes both:

```python
@app.get("/files/{path:path}")
async def read_file(path: str, fs: Annotated[AsyncVirtualFileSystem, Depends(get_fs)]):
    result = await fs.read(f"/{path}")
    return result

@app.get("/sync/files/{path:path}")
def read_file_sync(path: str, fs: Annotated[VirtualFileSystem, Depends(get_sync_fs)]):
    return fs.read(f"/{path}")
```

A write of 10,000 entries, from a background task after an upload:

```python
def ingest(rows: list[dict]) -> None:
    with VirtualFileSystem(storage=storage) as fs:
        fs.write([Entry(path=r["path"], content=r["body"]) for r in rows])

@app.post("/ingest")
async def start_ingest(rows: list[dict], tasks: BackgroundTasks):
    tasks.add_task(ingest, rows)
    return {"queued": len(rows)}
```

A search, async, with the client built in the lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncVirtualFileSystem(storage=storage) as fs:
        app.state.fs = fs
        yield

@app.get("/search")
async def search(q: str, request: Request):
    return await request.app.state.fs.grep(q, paths=("/docs",))
```

## Deliverable (b): ranked shapes from this population's point of view

1. Class twins with the same method names (`VirtualFileSystem` / `AsyncVirtualFileSystem`): it is what httpx, psycopg, pymongo and SQLAlchemy chose, it answers FastAPI's "does it tell me to await?" with an import, and the type checker catches the forgotten `await` that placement (e) shows is otherwise a silent 200.
2. Module twins with identical class names (`vfs.VirtualFileSystem` / `vfs.aio.VirtualFileSystem`, as redis-py): equally familiar and equally typed, but a wrong import is invisible in review and in tracebacks, since both classes print the same name.
3. Name twins on one class (`read` / `aread`): typed and discoverable, and FastAPI developers know it from httpx's `Response` and LangChain, but it doubles every verb on one class and puts the blocking `read` one keystroke from the async code where placement (c) freezes the server.
4. Async only with a documented bridge: right for `async def` code, but FastAPI's docs send the unsure developer to `def`, and the bridge they will write, `asyncio.run` per call, failed 39 of 40 calls under concurrency in placement (d).
5. One API that detects the caller's context (`sync_compatible`, the dream shape): it worked in placements (g) and (h), but FastAPI files it as sync in every dependency and background task, and it makes the forgotten `await` of placement (e) indistinguishable from a correct sync call for the type checker.
6. Dual-use handles, awaitable with a blocking `.result()`: unfamiliar in this population, and `.result()` inside `async def` is placement (c) again with a deadlock risk if the handle's loop is the server's own.
7. One class with a mode flag and underscored async names (fsspec): no library this population pairs with FastAPI does this, and the flag is chosen at construction, far from the `def` or `async def` that should decide it.
8. Sync only: works from every `def` endpoint and task at the 40-thread cap, but every call from `async def` freezes the server as placement (c) measured, and the async-native storage underneath would be wasted.

## Deliverable (c): brittleness of the top two shapes

Class twins. What breaks: a developer uses the sync class inside `async def` (placement c) or the async class without `await` (placement e). For whom: the FastAPI developer, in production, under load. How a maintainer finds out: (c) produces no traceback, no warning and no wrong answer, only latency, and is found by a loop-lag metric, a profiler, or asyncio debug mode's slow-callback log; (e) is caught before it runs by `mypy` (`unused-coroutine`) and pyright (`reportUnusedCoroutine`) only because the async class's method is typed as returning a coroutine, and at run time by the `RuntimeWarning` and a coroutine repr in the response body. What breaks for the maintainer: the twins drift if kept by hand; the population's libraries prevent that by generating one face from the other and failing CI on a diff (httpcore `scripts/check`, psycopg's "DO NOT CHANGE" header). vfs's `sync.py` is a 1,045-line hand-written forwarder; INFERRED: its drift is a missing or mistyped parameter on a new verb, found today only by its own tests, and a generated or signature-checked facade would find it at lint time. Thread pools: the sync twin under FastAPI is called from up to 40 worker threads at once; executed placement (b) shows the facade's one loop thread serves them all correctly.

Module twins. Everything above, plus two specific failures. A wrong import (`from vfs import VirtualFileSystem` where the async one was meant) looks identical in review and in a traceback, because both classes have the same `__name__`; the developer finds out through the type checker or a coroutine repr, as in (e). And any shared code between the two modules that returns "value or awaitable", the redis-py route, needs a pair of overloads on every verb (704 in redis-py's core commands) to stay typed; a maintainer finds a missing overload only when a user's type checker reports `Awaitable[Result] | Result` where a `Result` was expected.

## What this study does not settle

The MongoDB and psycopg design pages were read only as search summaries; fetching both pages once `mongodb.com` and `psycopg.org` are allowed in the session's network settings would let their quotations replace the summaries. The facade's extra hop (worker thread to loop thread) was measured only at 50 ms per read; running `placement.py` with `DELAY = 0` and a profiled call count per request would show what the hop costs a `def` endpoint against a native sync twin. The loop binding behind placement (d) was shown on the in-memory storage; repeating `probe_errors.py` over the database storage on asyncpg would show whether a Postgres engine fails the same way or worse. Whether the dual stand-in's behaviour holds for a real `sync_compatible`-style decorator applied to the router's verbs belongs to study 04, and the check here would be to pass such a decorated verb to `Depends` and `add_task` in `placement.py` and record how Starlette's `is_async_callable` files it. Whether `ty` flags the forgotten `await` of placement (e) as `mypy` and pyright do is an experiment of one file: an `async def` that calls `router.read()` without `await`, checked under `uv run ty check`.

## One line

FastAPI developers choose `def` or `async def` by the import a library gives them, every library they pair with FastAPI gives two classes with the same method names, and a single dual-mode class would make their most common mistake, the forgotten `await`, return 200 instead of a type error.
