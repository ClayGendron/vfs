<!--
DIÁTAXIS TYPE: Reference (information-oriented)
THE RULE: Austere, neutral, complete. Describe the machinery; do not instruct
or explain. Structure MIRRORS the code. Accuracy is the whole job.
-->

# Synchronous use

Module `vfs.sync`. Two classes: `SyncVirtualFileSystem`, the synchronous twin of [`VirtualFileSystem`](api.md), and `SyncSession`, the twin of [`Session`](session.md). Each twin method has the original's parameter names, kinds, defaults and order, and returns what the original returns.

```python
from vfs.storage.backends.memory import InMemoryStorage
from vfs.sync import SyncVirtualFileSystem

sync_fs = SyncVirtualFileSystem(storage=InMemoryStorage())
written = sync_fs.write(path="/notes/a.txt", content="hello", parents=True)
assert written.success is True
assert sync_fs.read("/notes/a.txt").one().content == "hello"
sync_fs.close()
```

## Construction

`SyncVirtualFileSystem(*, name=None, title=None, description=None, storage=None, permissions="read_write", deny_ops=(), no_overlay=False, hop_budget=16, close_timeout=10.0, rerankers=(BM25Rerank(),), default_authority=None)`. The parameters are `VirtualFileSystem`'s. The router is built, then one asyncio loop is created and started on one daemon thread named `vfs-sync-loop`. A refused argument raises the router's own `TypeError`, before any thread starts.

`SyncVirtualFileSystem.wrap(fs: VirtualFileSystem) -> SyncVirtualFileSystem`. The facade over a router the caller built. Pinned on SQLite, whose driver tolerates a change of loop; unproven on asyncpg, which binds an engine to the loop that first touches it.

## Lifecycle

| Call | Behavior |
|---|---|
| `with SyncVirtualFileSystem(...) as fs` | enters; `close()` runs on exit |
| `fs.close()` | closes the router on the loop, stops the loop, joins the thread; idempotent; final |
| `fs.closed` | `bool`: whether `close()` has run |

After `close()`, no thread named `vfs-sync-loop` remains. A call another thread had in flight when `close()` ran raises `concurrent.futures.CancelledError` in that thread.

Each call runs on the loop thread in a copy of the calling thread's context, taken when the call is submitted. The hop budget is per call, as for a top-level `await` on the router.

```python
import threading

with SyncVirtualFileSystem(storage=InMemoryStorage()) as scoped:
    assert scoped.ls("/").success is True
    assert any(t.name == "vfs-sync-loop" for t in threading.enumerate())
assert scoped.closed is True
assert not any(t.name == "vfs-sync-loop" for t in threading.enumerate())
```

## Verbs

Every verb of `VirtualFileSystem`, with the same parameters: `read`, `stat`, `ls`, `tree`, `write`, `edit`, `delete`, `restore`, `sweep`, `mkdir`, `mkedge`, `rmedge`, `move`, `copy`, `glob`, `grep`, `glean`, `graph`, `run`, `grant`, `revoke`, `grants`, `posture`, `add_member`, `remove_member`. Each returns a `Result`.

Every management method, with the same parameters: `bind`, `unbind`, `add_mount`, `remove_mount`, `remount`, `locate`, `locate_edge`. Each returns what the router's returns and raises what the router's raises. `mounts()` and `capabilities()` answer without a hop. `session(authority)` returns a `SyncSession`.

## Refusals

A verb on a closed facade dispatches nothing and returns a `Result` with `ops=(<verb>,)` and one error:

| Field | Value |
|---|---|
| `kind` | `vfs.unavailable.backend` |
| `message` | `Backend unavailable: the filesystem is closed` |

A management method on a closed facade raises `RuntimeError("the filesystem is closed; the loop thread has stopped")`.

A verb called from the facade's own loop thread, for example inside a reranker or an embedder the router runs, dispatches nothing and returns a `Result` with `ops=(<verb>,)` and one error:

| Field | Value |
|---|---|
| `kind` | `vfs.invalid` |
| `message` | `Invalid: called from the facade's own loop thread; a callback running on the loop uses the async filesystem` |

A management method called from the loop thread raises `RuntimeError` with the same words.

```python
from vfs.results import ErrorKind

closed_fs = SyncVirtualFileSystem(storage=InMemoryStorage())
closed_fs.close()
refused = closed_fs.read("/notes/a.txt")
assert refused.success is False
assert refused.errors[0].kind is ErrorKind.backend_unavailable
```

## SyncSession

`SyncVirtualFileSystem.session(authority: Authority) -> SyncSession`. The twin wraps a `Session` over the facade's router; `authority` and `closed` are the wrapped session's.

| Call | Behavior |
|---|---|
| `with fs.session(a) as s` | enters; `close()` runs on exit |
| `s.close()` | marks the session closed; idempotent; no hop |
| `with s` after close | raises `ValueError("the session is closed and cannot reopen; open a new one")` |

Every session verb, with `Session`'s parameters. A verb on a closed session returns the refusal [Session](session.md#refusal-on-a-closed-session) documents, before any hop.

```python
from vfs import Authority, Principal

with SyncVirtualFileSystem(storage=InMemoryStorage()) as owner_fs:
    with owner_fs.session(Authority.of(Principal("alice"))) as s:
        assert s.write(path="/a.txt", content="x").success is True
        assert s.read("/a.txt").one().content == "x"
    assert s.closed is True
    assert s.read("/a.txt").errors[0].kind is ErrorKind.invalid
```

## Engines

The facade's loop is the only loop its storage is touched on, so a `DatabaseStorage` over an asyncpg URL constructed for the facade is safe inside a process whose main thread runs its own loop. `wrap` over a router already touched by another loop is pinned on SQLite only.
