# One object cannot serve both `fs.read()` and `await fs.read()` without brittleness: every mechanism that returns a bare value or a bare coroutine breaks in a notebook cell or under the type checker, and the only shapes that pass all four settings name the mode in the caller's spelling (twins, or a handle with an explicit `.result()`)

This study executed thirteen prototypes of the dual-mode mechanisms that exist in the Python ecosystem (plain loop detection, Prefect's `sync_compatible` and `async_dispatch`, fsspec's `asynchronous` flag and `sync()`, SQLAlchemy's greenlet bridge, `greenback`, `asgiref`, two lazy awaitable results, an awaitable handle with `.result()`, and today's class twins as the control) over one stand-in coroutine, in four settings: a plain script, a running loop on the caller's thread (both `asyncio.run(main())` and a real ipykernel driven through `jupyter_client`), a `ThreadPoolExecutor` worker while the main thread runs a loop, and `ty` plus `mypy`. It also ran one confirming pass over the real `vfs.VirtualFileSystem` on `InMemoryStorage`. The time box was 45 minutes; when it ran out every prototype had run in every setting, the real-kernel pass and both type checkers were done, and the one thing not run was a loop-bound real database driver (asyncpg against Postgres), which section 6 names as the experiment that settles it.

## Sources

Clones, read by `path:line`: `prefect` at commit d61f4fa, Apache-2.0 (`src/prefect/utilities/asyncutils/__init__.py`, `src/prefect/_internal/compatibility/async_dispatch.py`, `docs/v3/release-notes/oss/version-3-1.mdx`, `docs/v3/release-notes/oss/version-3-6.mdx`); `filesystem_spec` at commit 12c823b, BSD-3-Clause (`fsspec/asyn.py`). Installed packages, licences read from their metadata on 2026-11-06: SQLAlchemy 2.0.52 in `/home/user/vfs/.venv` (`sqlalchemy/util/_concurrency_py3k.py`), MIT; in the scratch venv `experiments/04-dual-mode/.venv` (gitignored, recreate with `uv venv .venv -p 3.13 && uv pip install -p .venv/bin/python greenback asgiref mypy prefect fsspec sqlalchemy ipykernel jupyter_client`): prefect 3.9.1 (Apache-2.0), fsspec 2026.9.0 (BSD-3-Clause), SQLAlchemy 2.1.8 (MIT), greenback 1.3.0 (MIT or Apache-2.0), greenlet 3.5.6 (MIT and PSF-2.0), asgiref 3.13.0 (BSD-3-Clause), mypy 2.4.1 (MIT); ty 0.0.60 from the project venv. vfs at commit 09163c0: `src/vfs/base.py`, `src/vfs/sync.py`, `src/vfs/storage/backends/memory.py`. Experiments, all under `experiments/04-dual-mode/`: `mechanisms.py` (the prototypes), `run_one.py` and `run_all.py` (settings 1 to 3, output `results.jsonl`), `kernel_cells.py` (real ipykernel, output `kernel_cells.out`), `extra.py` (cost, reentrancy, laziness, loop affinity, outputs `extra.out` and `cost.out`), `sqla_20.py` (`sqla_20.out`), `vfs_confirm.py` (`vfs_confirm.out`), `typecheck_cases.py` and `typecheck_prefect_fn.py` (outputs `mypy.out`, `ty.out`, `mypy_prefect_fn.out`, `ty_prefect_fn.out`). No web pages were used.

Labels: EXECUTED means I ran it here and report its output; READ means I read the cited file; INFERRED means my reasoning from the other two.

## The answer

No mechanism lets one method name return a plain value to `fs.read()` and a coroutine to `await fs.read()` safely, because a function cannot see whether its caller is about to `await` it; every mechanism instead guesses from "is a loop running on this thread", and that guess is wrong in exactly the place one of the three populations lives: a Jupyter cell has a running loop, so `fs.read()` there hands the data engineer a coroutine, an `AttributeError`, and a "never awaited" warning that the kernel prints under the next cell (EXECUTED, sections 1 and 2). The mechanisms that dodge the guess either refuse the call (asgiref, SQLAlchemy's `await_only`, greenback without a portal, fsspec in async mode), or block the caller's event loop and run the work on a different loop (fsspec's sync flag, Prefect's private loop thread, the lazy result), and under `ty` and `mypy` every guessing mechanism is typed as `Result | Coroutine[...]`, which both checkers reject in both spellings, so the dream shape cannot be typed for either caller (EXECUTED, section 4). The only shapes that work in all four settings put the mode in what the caller types: twin names or twin classes, or a returned handle that is awaited for async and asked `.result()` for sync; one object can still serve both, provided the two spellings differ by a name and not by the presence of `await` (EXECUTED, sections 1 and 5).

## 1. The four settings, per mechanism

All rows are EXECUTED (`results.jsonl`, `kernel_cells.out`). "Sync" is `fs.read("a")` used as a value; "await" is `await fs.read("a")` (for twins and fsspec, the async name). "Loop blocked" is a heartbeat task on the caller's loop that ticked zero times during the call. "Foreign loop" means the coroutine ran on a loop other than the caller's.

| Mechanism | 1 plain script, sync | 2 loop thread, sync (also real ipykernel) | 2 loop thread, await | 3 executor worker, sync |
|---|---|---|---|---|
| plain detection (`get_running_loop`) | value, new loop per call | coroutine returned: `AttributeError`, "never awaited" | value, caller's loop | value, new loop in the worker |
| Prefect `sync_compatible` | value, on `RunSyncEventLoopThread` | coroutine returned: `AttributeError`, "never awaited" | value, caller's loop | value, foreign loop thread |
| Prefect `async_dispatch` (sync body on a private loop) | value, private loop | coroutine returned: `AttributeError`, "never awaited" | value, caller's loop | value, private loop |
| fsspec `asynchronous=False` (`cat_file` / `_cat_file`) | value, `fsspecIO` thread | value, but caller's loop blocked, foreign loop | value via `_cat_file`, caller's loop | value, `fsspecIO` |
| fsspec `asynchronous=True` | `RuntimeError: Loop is not running` | same `RuntimeError` | value via `_cat_file` | same `RuntimeError` |
| SQLAlchemy `await_only` | value (only by wrapping in `asyncio.run(greenlet_spawn(...))`) | `MissingGreenlet`; value only if the caller runs it under `greenlet_spawn` | not awaitable (sync-only spelling) | value, new loop in the worker |
| greenback `await_` | value via `asyncio.run` fallback | `RuntimeError: You must create a greenback portal`; value, caller's loop not blocked, once `await greenback.ensure_portal()` ran in the same task | not awaitable (returns a value) | value, new loop in the worker |
| asgiref `async_to_sync` | value, on a fresh executor thread | `RuntimeError: You cannot use AsyncToSync in the same thread as an async event loop` | refused (same) | value |
| lazy result, forced on a private loop | handle; value on attribute access | handle; value on access, caller's loop blocked | value, caller's loop | handle escapes the worker and is forced later on the loop thread, blocking it |
| lazy result, forced by greenback | handle; value | needs a portal; with one, value on caller's loop | value | handle escapes and raises the portal error on the loop thread |
| awaitable handle with `.result()` | value | value, caller's loop blocked, foreign loop | value, caller's loop | value, private loop |
| control: class twins (`read` / `aread`) | value, private loop | value, caller's loop blocked, foreign loop | value via `aread`, caller's loop | value, private loop |

1.1 EXECUTED: every mechanism that chooses by "is a loop running here" (plain detection, both Prefect decorators, `asgiref` with detection) returned a coroutine for the sync spelling inside `asyncio.run(main())` and inside a real ipykernel cell; the cell printed `detect sync spelling -> coroutine NO .thread`, and the kernel attached `RuntimeWarning: coroutine '_aread' was never awaited` to the source line of the following cell, so the warning points at the wrong code (`kernel_cells.out`).

1.2 EXECUTED: a real ipykernel cell sees a running loop (`cell sees a running loop`), so the notebook case and the `asyncio.run(main())` simulation agree row for row (`kernel_cells.out`).

1.3 EXECUTED: greenback's portal is per task, and ipykernel runs each cell as its own task: `await greenback.ensure_portal()` in one cell did not help the next cell (`greenback next cell -> RAISED RuntimeError You must create a greenback portal`), while the same two statements in one cell worked (`kernel_cells.out`). A notebook user would have to start every cell with an `await`, which defeats the purpose.

1.4 READ: Prefect's `sync_compatible` checks for a Prefect run context first and only then calls `asyncio.get_running_loop()` (`src/prefect/utilities/asyncutils/__init__.py:310-330`), and in a running loop returns the coroutine (`:352`); without a loop it submits to a process-wide loop thread through `run_coro_as_sync` (`:144-215`). `async_dispatch` does the same detection in `is_in_async_context` (`src/prefect/_internal/compatibility/async_dispatch.py:17-41`) and picks the sync body or the async body; the escape hatch is a private `_sync=` keyword (`:89-93`).

1.5 READ: fsspec does not detect: the mode is fixed by the constructor flag `asynchronous` (`fsspec/asyn.py:490-498`), the coroutine lives under an underscored name and the sync name is generated by `mirror_sync_methods` (`:1150-1185`), and `sync()` refuses to block on its own loop (`:78-80`, `NotImplementedError: Calling sync() from within a running loop`) but will block any other loop, which is why the notebook row shows a value with the caller's loop stalled.

## 2. Where each one breaks

2.1 EXECUTED, the wrong-type break: plain detection and both Prefect decorators hand a coroutine to a caller who wrote sync code on a loop thread (a notebook, a FastAPI `async def` endpoint that calls a helper written as plain `def`, a LangChain async callback). The failure surfaces one line later as `AttributeError: 'coroutine' object has no attribute ...`, never at the call (`results.jsonl`, rows `s2_sync`).

2.2 EXECUTED, the deadlock break: a private-loop mechanism called synchronously from code already running on that private loop hangs forever. Twins and the `.result()` handle both produced `HANG (no result in 5 s)`; fsspec raised `NotImplementedError` because it guards for exactly this; Prefect returned a coroutine because its detection saw the loop (`extra.out`). In vfs this would be a hook, a storage callback or a mount that calls the sync facade from inside the kernel's loop (INFERRED).

2.3 EXECUTED, the loop-affinity break: an `asyncio.Event` first used on loop A and then used by a call bridged to a private loop raised `RuntimeError: ... is bound to a different event loop` (`extra.out`). Every mechanism that runs the sync spelling on a loop other than the caller's (fsspec, Prefect, twins, the lazy and handle shapes) is exposed to this when a resource was created by the other spelling first (INFERRED).

2.4 EXECUTED, but the vfs kernel on `InMemoryStorage` survived it: writing on loop A and reading on loop B in another thread both succeeded, as did a fresh `asyncio.run` per call; aiosqlite runs its own connection threads, and two of them were left alive with `ResourceWarning: Connection ... was deleted before being closed` (`vfs_confirm.out`). INFERRED: asyncpg connections are bound to the loop that opened them, so the Postgres leg is where per-call loops and mixed spellings would fail; section 6 names that experiment.

2.5 EXECUTED, the laziness break: a lazy result returned from a worker thread is not forced in the worker; it escapes through `run_in_executor` and is forced on the loop thread at first attribute access, which blocked the loop (`lazy_portal`, zero ticks) or raised the greenback portal error (`lazy_greenback`) (`results.jsonl`, `s3_worker`). Forced inside the worker, both worked (`extra.out`). The work happens wherever the first attribute is read, which no reader of the code can see.

2.6 EXECUTED, the refusal break: asgiref refuses on a loop thread in both spellings; SQLAlchemy 2.0.52 `await_only` raises `MissingGreenlet` everywhere outside `greenlet_spawn`, and the deprecated `await_fallback` works only without a running loop (`sqla_20.out`). READ: `await_fallback` is marked deprecated since 2.0.24 and removed in 2.1 (`sqlalchemy/util/_concurrency_py3k.py:135-147`); SQLAlchemy's own sync-over-async design requires the host to enter the greenlet first (`AsyncSession.run_sync` style), it is not a way for a library to sniff its caller.

2.7 READ: Prefect is moving away from the guessing decorator. The 3.6 release notes list eleven "Migrate ... from `@sync_compatible` to `@async_dispatch`" entries (`docs/v3/release-notes/oss/version-3-6.mdx:725-777`), and 3.1 records removing `sync_compatible` from modules outright (`version-3-1.mdx:188`, `:461`). `async_dispatch` keeps a real sync body and exposes the async body under its own name (`wrapper.aio`, `async_dispatch.py:96-98`), so Prefect's direction is towards two implementations with two names, chosen by detection only as a default. INFERRED: the detection default still produced the wrong-type break in 2.1, so the direction helps maintainers more than notebook users.

## 3. What each one costs

3.1 EXECUTED, 200 sync calls from a plain script (`cost.out`): plain detection, SQLAlchemy's fallback and greenback's fallback each created 200 event loops (one `asyncio.run` per call); asgiref created 200 loops and ran the work on 200 different threads; Prefect `sync_compatible` created one loop on one long-lived `RunSyncEventLoopThread`; fsspec, twins, the lazy result and the handle created no loop per call, reusing one private loop thread made once per object or per process.

3.2 EXECUTED: greenback with a portal and SQLAlchemy under `greenlet_spawn` are the only mechanisms that ran the sync spelling on the caller's own loop without blocking it (heartbeat ticked 10 times; `results.jsonl`, `s2_sync_portal`, `s2_sync_spawned`). The cost is a greenlet switch per await and a setup step the caller must perform in each task (INFERRED from 1.3 and the `greenlet_spawn` source, `_concurrency_py3k.py:167-212`).

3.3 INFERRED: the private-loop shapes (fsspec, Prefect, twins, handle) pay one extra thread per process or per object plus a cross-thread hand-off per call, and on a loop thread they stall every other task for the duration of the call; that stall is the honest price of a sync call on a loop thread, and it is visible (a slow cell, a slow endpoint) rather than silent.

## 4. What the type checkers say

4.1 EXECUTED: a detection-based dual method honestly annotated `-> Result | Coroutine[Any, Any, Result]` is rejected by both checkers in both spellings: the sync use `fs.read("a").success` is `union-attr` in mypy ("Maybe you forgot to use await?") and `unresolved-attribute` in ty, and `await fs.read("a")` is `Incompatible types in "await"` in mypy and `invalid-await ... is not awaitable` in ty (`mypy.out`, `ty.out`, lines 89 and 94).

4.2 EXECUTED: Prefect's real decorator types are worse. On a free `async def read(...) -> int` decorated with `sync_compatible`, mypy reveals `Coroutine[Any, Any, R?]` with the type variable unsolved, reports the sync call as an unused coroutine, rejects `x: int = read("a")`, and reveals `await read("a")` as `R?`; ty reveals `int | Coroutine[Any, Any, int]`, rejects the assignment and rejects the await (`mypy_prefect_fn.out`, `ty_prefect_fn.out`). READ: Prefect's own docstring tells users to `# type: ignore` and cast (`asyncutils/__init__.py:297-302`).

4.3 EXECUTED: the lazy result typed with `__getattr__` makes every attribute `Any`, so neither checker sees anything, including a forgotten await in async code that silently blocks the loop (`mypy.out`, `ty.out`, lines 84 and 105). fsspec ships no annotations: mypy reports `import-untyped` and the sync call is `Any`; ty calls it `Unknown` (line 87).

4.4 EXECUTED: the forgotten await is caught only when the forgotten value is a plain coroutine: both checkers flag a bare `Twins().aread("a")` statement (mypy `unused-coroutine`, ty `unused-awaitable`) and `.success` on the un-awaited coroutine (line 106 to 108). Neither flags a dropped awaitable handle (line 109) or a dropped union (line 110). The handle's two spellings type cleanly: `await h` and `h.result()` both reveal `Result` in both checkers (lines 85 and 98).

## 5. Ranking the mechanisms as a basis for vfs

5.1 INFERRED, from sections 1 to 4: correct in all four settings, typed in both checkers, and costing one private loop thread: class or name twins (today's `vfs.sync` shape) and the awaitable handle with `.result()`. Correct except for a deadlock fsspec guards against and the others do not: all private-loop shapes, so a reentrancy guard (fsspec's check of the running loop against the private loop, `asyn.py:78-80`) belongs in any of them. Correct only with caller cooperation: greenback and SQLAlchemy's greenlet bridge. Wrong in a notebook and untypeable: plain detection and both Prefect decorators. Refusing on a loop thread: asgiref and fsspec's async mode, which are honest but give the notebook user nothing.

5.2 INFERRED: the dream spelling (`fs.read()` and `await fs.read()` on one object, same name) is achievable only as the lazy result, and the lazy result is the shape with the worst failure: it is correct in every setting when forced in the right place, but it moves the I/O to the first attribute access, blocks the loop silently when an `await` is forgotten, and erases types to `Any`. It trades a loud failure for a silent one.

## Deliverable (a): what a developer reaching for a dual-mode library types

```python
# read: the dream, typed the same in a script, a cell and an endpoint
result = fs.read("/docs/a.md")            # in a script or a cell
result = await fs.read("/docs/a.md")      # in an async def
```

```python
# write 10,000 entries: one call, no loop management
entries = [Entry(path=f"/rows/{i}.json", content=row) for i, row in enumerate(rows)]
written = fs.write(entries)               # or: written = await fs.write(entries)
```

```python
# search
hits = fs.glean("lease renewal terms", path="/contracts")
for obs in hits.observations:
    print(obs.path, obs.score)
```

## Deliverable (b): ranked shortlist from the mechanism's point of view

1. Class twins with the same method names (`VirtualFileSystem` / `SyncVirtualFileSystem`, or `Client` / `AsyncClient`): correct in all four settings, cleanly typed, one private loop thread, and the forgotten await on the async class is caught by both checkers (EXECUTED, 1 and 4.4).
2. Name twins on one class (`read` / `aread`): the same mechanism as 1 on one object, equally correct and typed; it doubles the surface of one class, which is a population question rather than a mechanism one (EXECUTED for `twins`, which carries both names).
3. Dual-use handle, awaitable with an explicit blocking `.result()`: correct and typed in all settings and close to the dream spelling, but a dropped handle is caught by neither checker (EXECUTED, 4.4).
4. One class with a mode flag and underscored async names (fsspec): works, but the flag decides at construction which spelling raises, async mode refuses every sync call, and the sync path stalls a caller's loop without saying so (EXECUTED, 1).
5. Async only with a documented bridge (greenback portal, `greenlet_spawn`, `asyncio.run`): correct when the caller follows the bridge, but the bridge is per task, so a notebook needs it in every cell (EXECUTED, 1.3).
6. Sync only: correct everywhere, but it blocks every async caller's loop and has nothing to offer the FastAPI and LangChain populations' await path (INFERRED).
7. One API that detects the caller's context (Prefect's `sync_compatible`, plain detection, `async_dispatch`): wrong type in every notebook cell and untypeable in both checkers, and its own authors are migrating off the decorator (EXECUTED, 1.1 and 4.2; READ, 2.7).

## Deliverable (c): brittleness of the top two shapes

Class twins. What breaks: a sync facade called from inside the kernel's own loop (a hook, a storage callback) hangs forever, as `twins` did in `extra.out`; a resource created through the async class on the caller's loop and then used through the sync facade fails with "bound to a different event loop" on loop-bound drivers; on a loop thread the sync facade stalls the loop for the call. Who: library maintainers writing hooks (the hang), FastAPI users who mix the two classes over one storage (the loop error), notebook users (a slow cell, not a wrong answer). How a maintainer finds out: the hang shows only as a stuck test or process, so the facade needs fsspec's guard that refuses to block on its own loop and turns the hang into a traceback; the loop error is a traceback naming the loop; type checkers catch the forgotten await on the async class (EXECUTED, 4.4).

Name twins on one class. What breaks: the same three as class twins, since the mechanism is the same, plus one of its own: in async code a caller can type `fs.read()` and get a correct value while stalling the loop, and no checker flags it because the sync twin is a legitimate call (INFERRED from 1 and 4). Who: FastAPI and LangChain users inside `async def`. How a maintainer finds out: not from the type checker; only from latency under load, or from a runtime check in the sync twin that warns when it is called on a thread with a running loop that is not its own (INFERRED; fsspec's guard at `asyn.py:78-80` shows the check is cheap).

## 6. What this study does not settle

6.1 Loop-bound real drivers. Run `vfs_confirm.py` against the Postgres leg (`VFS_TEST_POSTGRES_URL`, asyncpg) with the four strategies: per-call `asyncio.run`, the private loop thread, an async write followed by a sync read on one storage object, and the reverse; record which raise "attached to a different loop".

6.2 Whether a reentrancy guard in `vfs.sync` costs anything measurable. Add the private-loop check to a copy of the facade in the experiments folder, call it 10,000 times, and count the extra calls with cProfile against the unguarded copy.

6.3 Whether a warning from the sync twin when called on a foreign running loop is noise in Jupyter, where every cell has one. Run `kernel_cells.py` with such a warning enabled and count warnings per cell for a typical ten-cell notebook.

6.4 Whether a typed lazy result that subclasses the result type (so attributes keep their types) changes section 4.3. Add that class to `typecheck_cases.py` and rerun both checkers on the forgotten-await lines.

## One line

A method cannot see whether its caller will `await` it, so every same-name dual mechanism guesses from the running loop, guesses wrong in every notebook cell, and cannot be typed; the shapes that pass all four settings put the mode in the name the caller types, twins or a handle with `.result()`.
