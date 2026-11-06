# LangChain serves both worlds with name twins on one object, sync as the required floor and async as an optional override that defaults to a thread hop, so vfs fits it best as one class with `read` and `aread` whose async half awaits the loop that owns the engine

This study asks how LangChain and LangGraph serve sync and async callers, what an AI engineer expects of a library they wrap as a tool or a retriever, and how vfs's async router and its new sync facade fit that shape. The time box was 45 minutes. When it ran out, the LangChain core paths (Runnable, tools, retrievers, vector stores, callbacks) and the LangGraph tool node and node wrapper were read, and three experiments had run against the real `SyncVirtualFileSystem` and `VirtualFileSystem` with `langchain_core` 1.2.13 from the vfs venv. LangGraph was read but not executed, because it is not installed in the venv; its tool-node fan-out was reproduced with `langchain_core`'s own executor helper. No web pages were read.

## Sources

Clones, read-only. `langchain` (the monorepo), commit bb6a25a, MIT, cloned 2026-11-06 per `refresh.log`. `langgraph`, cloned `--depth 1` by this researcher on 2026-11-06 at `origin/main` commit e5e37b5, licence MIT (`LICENSE`: "MIT License, Copyright (c) 2024 LangChain, Inc."), recorded in `licenses.log` and `refresh.log`. The installed `langchain_core` that the experiments ran against is version 1.2.13, not the clone's master; the paths exercised (`run_in_executor`, `StructuredTool`, `@tool`, `get_executor_for_config`) were checked to have the same behaviour in the clone (READ). vfs at the working tree of 2026-11-06: `src/vfs/sync.py` and `src/vfs/base.py`. Experiments: `experiments/02-langchain-tool-shapes/run.py` with `output.txt`, `owner_loop.py` with `owner_loop_output.txt`, and `detect_and_handle.py` with `detect_and_handle_output.txt`, all in this study folder.

Labels: EXECUTED means I ran it here and report its output; READ means I read the cited file at the commit above; INFERRED means my own reasoning from those.

## The answer

LangChain's whole surface is name twins on one object: `invoke`/`ainvoke`, `batch`/`abatch`, `stream`/`astream`, `_run`/`_arun`, `_get_relevant_documents`/`_aget_relevant_documents`, `similarity_search`/`asimilarity_search`, `add_documents`/`aadd_documents`, and `StructuredTool.from_function(func=..., coroutine=...)` (READ). The sync method is the abstract floor; the async twin defaults to running the sync one on a thread through `run_in_executor` with the caller's context copied, and there is no general reverse bridge: an object that has only the async half raises `TypeError` or `NotImplementedError` when called sync (READ, EXECUTED). So the AI engineer expects two things of a library: a sync call that works anywhere, including on a worker thread with no loop, and an `a`-prefixed call they can `await` from an async agent. vfs's facade already satisfies the first and passes LangChain's `RunnableConfig` and the caller's context variables through both hops, the executor thread and the facade's loop thread (EXECUTED). What fights the shape is having two objects: an AI engineer who writes a tool with both a sync and an async body must hold a router and a facade, and if both touch one engine, that engine sees two loops, the hazard `SyncVirtualFileSystem.wrap` already names. The shape that fits is one class with `read` and `aread`, where `aread` awaits the facade's own loop via `asyncio.wrap_future` so one engine only ever sees one loop; that bridge was executed and keeps the caller's loop free (EXECUTED). Context detection and dual-use handles both produce silent wrong answers inside sync tools, which LangChain stringifies straight into the model's context (EXECUTED).

## 1. How LangChain's Runnable serves both

1.1 READ. `Runnable.invoke` is the abstract method (`libs/core/langchain_core/runnables/base.py:948-950`). `Runnable.ainvoke`'s default body is one line, `await run_in_executor(config, self.invoke, input, config, **kwargs)` (`base.py:993`). Sync is the floor every Runnable must provide; async is an optional override.

1.2 READ. `run_in_executor` (`runnables/config.py:678-712`) runs the sync function on the loop's default executor wrapped in `copy_context().run`, so context variables cross into the worker thread, and turns a `StopIteration` into `RuntimeError` because a future cannot carry one.

1.3 READ. `batch` defaults to `invoke` mapped over a `ContextThreadPoolExecutor` sized by `max_concurrency`, skipping the pool for one input (`base.py:995-1047`, `config.py:607-657`, `config.py:660-676`). `abatch` defaults to `ainvoke` under `gather_with_concurrency` (`base.py:1130-1177`). `stream` defaults to yielding one `invoke`, and `astream` to yielding one `ainvoke` (`base.py:1258-1298`). Batching in LangChain means many independent calls in parallel, not one call carrying many rows; a subclass "must override" `batch` to use a native batch API (`base.py:1007-1008`).

1.4 READ. `RunnableConfig` is a `TypedDict` that also flows implicitly through a `ContextVar`, `var_child_runnable_config` (`config.py:55-75`, `config.py:174-176`). Tags, callbacks and tracing reach a child by context, which is why every thread hop copies the context.

1.5 READ. No reverse bridge exists for Runnables. `RunnableLambda` built from only an async function raises `TypeError("Cannot invoke a coroutine function synchronously.Use `ainvoke` instead.")` on `invoke` (`base.py:5325-5333`).

1.6 READ. LangChain does keep one internal reverse bridge, for async callback handlers fired from sync code: with no running loop it runs the coroutines in a fresh `asyncio.Runner`; inside a running loop it submits that runner to a shared thread pool and blocks on `.result()`, with the comment that submitting to the running loop would deadlock (`callbacks/manager.py:360-411`). The retry hook in `language_models/llms.py:99-113` instead probes `asyncio.get_event_loop()` and either schedules a task or calls `asyncio.run`. INFERRED: LangChain's own sync-over-async is the same idea as vfs's facade (a loop on another thread, block on a future), except it builds a fresh loop per call, which is cheap for callbacks and wrong for a library that owns a pooled database engine.

## 2. Tools, the `@tool` decorator, retrievers and vector stores

2.1 READ. `BaseTool._run` is abstract; `BaseTool._arun` defaults to `run_in_executor(None, self._run, ...)` after converting an async run manager to a sync one (`tools/base.py:908-932`). The sync body runs under `context.run` with the child config set (`tools/base.py:1098`); the async body runs through `coro_with_context` (`tools/base.py:1216-1228`).

2.2 READ. `@tool` sends a coroutine function to `StructuredTool(coroutine=...)` and a plain function to `func=` (`tools/convert.py:307`, `tools/convert.py:344`). `StructuredTool.ainvoke` falls back to `run_in_executor(config, self.invoke, ...)` when there is no coroutine (`tools/structured.py:115-125`); `StructuredTool._run` with no `func` raises `NotImplementedError("StructuredTool does not support sync invocation.")` (`tools/structured.py:129-154`). `from_function` accepts both at once (`tools/structured.py:191-255`).

2.3 READ. `BaseRetriever._aget_relevant_documents` defaults to running `_get_relevant_documents` in an executor (`retrievers.py:311-328`). `VectorStore` declares `add_texts`, `add_documents` and `similarity_search` sync, and every `a`-twin defaults to `run_in_executor(None, ...)` (`vectorstores/base.py:185-232`, `vectorstores/base.py:265-291`, `vectorstores/base.py:606-622`). `as_retriever` is the bridge from store to retriever (`vectorstores/base.py:905`).

2.4 READ. The partner integration that most AI engineers touch, `ChatOpenAI`, holds two SDK objects, `client` and `async_client` (`partners/openai/langchain_openai/chat_models/base.py:799-803`), and takes `http_client` and `http_async_client` separately (`base.py:1029-1033`). INFERRED: when the wrapped SDK offers class twins (`OpenAI`/`AsyncOpenAI`), the LangChain integration hides them behind one object with name twins; the population sees the name twins, the integration author pays for the class twins.

## 3. LangGraph and the agent's tool-calling loop

3.1 READ. LangGraph's `ToolNode` has a sync body that maps `_run_one` (which calls `tool.invoke`) over `get_executor_for_config(config)` (`libs/prebuilt/langgraph/prebuilt/tool_node.py:801-834`, call at `tool_node.py:966`) and an async body that gathers `_arun_one` (which awaits `tool.ainvoke`) with `asyncio.gather` (`tool_node.py:836-867`, call at `tool_node.py:1126`). Parallel tool calls from one model turn therefore become threads on the sync path and tasks on the async path.

3.2 READ. `coerce_to_runnable` wraps a plain sync node function as `RunnableCallable(func, partial(run_in_executor, None, func))`, and an async one as `RunnableCallable(None, afunc)` (`libs/langgraph/langgraph/_internal/_runnable.py:590-605`). `RunnableCallable.invoke` with no sync function raises `TypeError('No synchronous function provided ...')` (`_runnable.py:406-412`), and `RunnableCallable.ainvoke` with no async function calls `self.invoke` directly on the loop thread (`_runnable.py:484-487`). INFERRED: the second is the path where a blocking sync call lands on a running loop inside LangGraph; the public `add_node` path avoids it through `coerce_to_runnable`, but a `RunnableCallable` built by hand or by an integration does not.

3.3 READ. The v1 agent factory composes middleware hooks as sync and async twins, `wrap_tool_call` and `awrap_tool_call`, and raises when only the other half exists (`libs/langchain_v1/langchain/agents/factory.py:1091-1127`, `agents/middleware/types.py:639`). The twin-name convention runs all the way up to the newest agent API.

## 4. Experiments: vfs as a LangChain tool

4.1 EXECUTED (`run.py`, section 1, 1b, 1c). A sync `@tool` over `SyncVirtualFileSystem` returns the file through `.invoke` on the main thread and through `.ainvoke` on executor thread `asyncio_0`. Inside the verb's own task on the facade loop thread `vfs-sync-loop`, both the caller's own `ContextVar` and LangChain's `var_child_runnable_config` tags arrive intact, for `.invoke` (`'caller-probe', 't-probe'`) and for `.ainvoke` after two hops (`'caller-probe-async', 't-probe-async'`). The context copy at submit time that `sync.py` documents composes with LangChain's executor context copy. The probe used the facade's private `_submit` only to observe that context.

4.2 EXECUTED (section 2). An async `@tool` over the router works through `.ainvoke` and, called with `.invoke`, raises `NotImplementedError: StructuredTool does not support sync invocation.`. An async-only vfs gives a LangChain user exactly this error in any sync agent, notebook cell or `batch` call.

4.3 EXECUTED (section 3). `StructuredTool.from_function(func=<facade read>, coroutine=<router read>)` runs the coroutine on `MainThread` from `.ainvoke` and the function on a worker thread from `.invoke`: each path native, no executor round trip on the async side. It needed two vfs objects, one router for `coroutine` and one facade for `func`.

4.4 EXECUTED (section 4). The bridge an AI engineer writes by hand, `asyncio.run(router.read(...))` inside a sync tool, works from `.invoke` with no loop and from `.ainvoke` (it lands on an executor thread with no loop), and fails with `RuntimeError: asyncio.run() cannot be called from a running event loop` when the same sync body is called on the loop thread, leaving a never-awaited coroutine warning behind. It also builds a fresh loop and a fresh router per call.

4.5 EXECUTED (section 5). Two hundred blocking facade reads made on the event-loop thread let a heartbeat task tick 0 times; the same reads through `asyncio.to_thread` let it tick about 680,000 times. The facade never deadlocks there, because its loop is another thread, but it freezes the agent's loop for the whole call.

4.6 EXECUTED (section 6). Eight parallel tool calls from an async agent: a sync-only tool ran on 8 distinct worker threads of the default executor; a tool with a coroutine ran all 8 on `MainThread`. Eight calls from a sync agent through `get_executor_for_config(max_concurrency=4)` ran on 4 threads. Every one of those threads funnels into the facade's single loop thread.

4.7 EXECUTED (section 7, wall-clock in a research script, one run, InMemoryStorage, 2,000 reads each, microseconds per call). `await router.read` 4,198; `to_thread(facade.read)` 4,713; async tool `.ainvoke` 4,875; sync tool `.ainvoke` 5,154; `facade.read` with no loop 4,399; sync tool `.invoke` 5,026. INFERRED: at this storage the thread hops cost a few hundred microseconds against a read of about four milliseconds; the executor round trip is not where an agent's time goes.

4.8 EXECUTED (section 8). `facade.write(entries)` with 10,000 `Entry` rows returned `success: True` with 10,000 rows, and `RunnableLambda.abatch` over 50 facade reads all succeeded. One `vfs-sync-loop` thread was alive at the end.

4.9 EXECUTED (`owner_loop.py`). A tool whose `coroutine` awaits `asyncio.wrap_future(asyncio.run_coroutine_threadsafe(router.read(...), facade_loop))` ran the verb on `vfs-sync-loop`, cost 4,891 microseconds a call sequentially and 4,807 amortised over 500 gathered calls, and the caller's loop stayed free (150,513 heartbeat ticks during 50 gathered calls). Its `func` half on a worker thread used the facade's blocking call. INFERRED: this is the one-object shape: both halves reach one router on one loop, so an asyncpg engine is only ever touched by the loop that created it. Gathered calls were no faster than sequential ones at this storage; INFERRED, the in-memory backend's work is CPU-bound under the GIL, so the number says nothing about a network database.

4.10 EXECUTED (`detect_and_handle.py`, stand-ins, no vfs code). A Prefect-style function that returns a coroutine when a loop runs on the current thread gave the right text from a sync tool's `.invoke` and `.ainvoke`, and gave the model the string `<coroutine object _read at 0x...>` when the same sync body ran on the loop thread. A dual-use handle (awaitable, with a blocking `.result()`) stringified in a sync tool without `.result()` gave the model `<__main__.Handle object at 0x...>`. Neither raised. LangChain turns a tool's return value into the tool message, so both mistakes reach the model as content and nothing reaches the developer.

## 5. What this population expects, as opinion apart from the evidence above

5.1 INFERRED. An AI engineer wraps a library in a two-line `@tool` and reaches for whichever half their agent runs: sync in a notebook, a script or a `create_agent(...).invoke`, async under LangGraph's server, FastAPI or `astream_events`. They expect both halves on the object they already hold, named by the `a`-prefix convention every LangChain class teaches them (sections 1 to 3).

5.2 INFERRED. They expect the return value to stringify into something a model can read. vfs's `Result.__str__` already renders the rows or the classified error (EXECUTED in 4.1 and 4.4: the not-found error rendered as `ERROR /notes: Not found ... (retry: never)` before the experiment added `parents=True`). That is a good fit and a reason never to return an unresolved object from a sync call.

5.3 INFERRED. They expect retrieval as `retriever.invoke(query)` returning `list[Document]` and ingest as `add_documents(docs)` in one call. A vfs `as_retriever()` adapter over `glean` with `_get_relevant_documents` on the facade and `_aget_relevant_documents` on the owner loop would meet that without LangChain's default executor fallback.

## 6. Deliverable (a): what this population types without reading docs

A read inside a tool, sync and async, written against one object:

```python
@tool
def read_file(path: str) -> str:
    """Read a file from the workspace."""
    return str(fs.read(path))

@tool
async def aread_file(path: str) -> str:
    """Read a file from the workspace."""
    return str(await fs.aread(path))
```

A write of 10,000 entries, the shape of `vectorstore.add_documents(docs)`:

```python
entries = [Entry(path=f"/docs/{d.metadata['id']}.md", content=d.page_content) for d in docs]
result = fs.write(entries)          # or: result = await fs.awrite(entries)
```

A search, as a retriever the agent can call either way:

```python
retriever = fs.as_retriever(limit=5)
hits = retriever.invoke("quarterly revenue")        # or: await retriever.ainvoke(...)
```

## 7. Deliverable (b): ranked API shapes from the AI engineer's point of view

1. Name twins on one class (`read`/`aread`): it is LangChain's own convention from `invoke`/`ainvoke` to `_run`/`_arun` to `wrap_tool_call`/`awrap_tool_call`, and it gives `StructuredTool.from_function(func=fs.read, coroutine=fs.aread)` from one object with one loop under the engine (4.3, 4.9).
2. Class twins with the same method names (`Client`/`AsyncClient`): familiar from the OpenAI SDK that `ChatOpenAI` wraps, but the tool author must hold two objects, and two objects over one engine is the two-loop hazard (2.4, 4.3).
3. Async only with a documented bridge: native under LangGraph's async path, but every sync agent, notebook and `batch` meets `NotImplementedError`, and the hand bridge `asyncio.run` breaks on the loop thread (4.2, 4.4).
4. Module twins with identical class names (`playwright.sync_api`/`async_api`): workable, but a LangChain tool module that needs both halves imports two classes with one name and aliases one.
5. Sync only: fits every LangChain default, since sync is the floor and async falls back to the executor, at the price of a thread per parallel tool call and a frozen loop wherever a sync call lands on it (1.1, 4.5, 4.6).
6. One class with a mode flag and underscored async names (fsspec): the flag must match where the agent runs, which in LangChain changes per call (`.invoke` versus `.ainvoke` on the same tool), and the `_` names read as private to this population.
7. Dual-use handles, awaitable with a blocking `.result()`: a forgotten `.result()` in a sync tool feeds the model an object repr with no error (4.10).
8. One API that detects the caller's context (`sync_compatible`): LangChain moves sync tool bodies between loop-less worker threads and, on some paths, the loop thread itself, so the same tool returns text on one path and a coroutine repr on the other, silently (3.2, 4.10).

## 8. Deliverable (c): brittleness of the top two shapes

8.1 Name twins on one class. What breaks: an AI engineer calls `fs.read` (blocking) inside an `async def` tool or node instead of `fs.aread`. It does not deadlock, because the blocking half waits on the owner loop's thread, but it freezes the agent's loop for the call (EXECUTED 4.5). Who meets it: async agent authors, mostly under LangGraph's server. How a maintainer finds out: no type checker flags it, since both are typed `Result`; `asyncio` debug mode's slow-callback warning and a tracer's latency spikes do; vfs could refuse or warn when the blocking half is called on a thread with a running loop, as the facade already refuses its own loop thread (INFERRED). The second break is a forgotten `await` on `fs.aread`, which a type checker reports as a coroutine passed where `str` is expected, and which at runtime stringifies a coroutine into the tool message with a "never awaited" warning in the log (INFERRED from 4.10's identical repr). The cost is a doubled public surface, about thirty verbs twice, which is the maintenance load LangChain itself carries (INFERRED). The owner-loop bridge also means every call, async included, crosses to one thread; at network-database latency that is one hop against a round trip, at in-memory latency it was a few percent (EXECUTED 4.7, 4.9).

8.2 Class twins with the same method names. What breaks: the tool author builds `VirtualFileSystem` for `coroutine=` and `SyncVirtualFileSystem` for `func=` over one storage; the async half touches the engine on the agent's loop and the sync half on the facade's loop. On SQLite that passes; on asyncpg, whose engine binds to the first loop that used it, it fails with a cross-loop error at the first call from the other side (READ `src/vfs/sync.py:117-127`, which records the hazard as unproven on asyncpg; INFERRED for the failure mode). Who meets it: an AI engineer who wants both halves, exactly the person who follows LangChain's twin convention. How a maintainer finds out: a traceback from the driver in production, never from the in-memory tests, and never from a type checker, since both classes type-check. Building the async class over the sync one's loop removes the hazard and is shape 1 under two names.

## What this study does not settle

The asyncpg cross-loop failure in 8.2 is inferred, not run; the experiment is to build a router on one loop over Postgres, wrap it with `SyncVirtualFileSystem.wrap`, and call both halves from a `from_function(func=..., coroutine=...)` tool against the Postgres leg. The cost of the owner-loop bridge under real concurrency is measured only on InMemoryStorage; the experiment is `owner_loop.py` rerun against the Postgres and SQL Server legs with 8 and 64 gathered tool calls, compared with `await router.read` on the caller's loop. LangGraph's behaviour was read, not executed; the experiment is to install `langgraph` in a scratch venv and run a two-node graph with a sync and an async vfs tool through `invoke`, `ainvoke` and `astream_events`, recording the thread each verb ran on. A blocking-call guard for the sync half on a loop thread is proposed in 8.1, not prototyped; the experiment is a stand-in facade that checks `asyncio.get_running_loop()` on its calling thread and warns, run under the section 5 heartbeat and under LangChain's `.ainvoke`, to confirm it fires only where the loop is truly blocked.

## One line

LangChain teaches its users name twins on one object with sync as the floor and async defaulting to a thread hop, so vfs serves them best as one class with `read` and `aread`, where `aread` awaits the one loop that owns the engine, and worst with any shape that can hand a sync tool an unresolved object, because LangChain feeds it straight to the model.
