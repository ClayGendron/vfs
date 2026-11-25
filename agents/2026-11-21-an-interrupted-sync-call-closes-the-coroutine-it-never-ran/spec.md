# An interrupted sync call closes the coroutine it never ran

Written on 2026-11-21 from a warning in one gate run of the bounded-waits work; not built.

## The outcome wanted

A `VirtualFileSystem` call interrupted before its loop has started it leaves no coroutine unawaited. No `RuntimeWarning: coroutine ... was never awaited` follows a Ctrl-C, whenever it lands.

## The problem

Seen once, in a `scripts/ci.sh` run of 6,043 tests. Not yet reproduced on purpose.

- **The warning.** The run's warnings summary named `tests/test_sync.py::test_an_interrupt_in_the_waiting_thread_cancels_the_call` with "RuntimeWarning: coroutine 'AsyncVirtualFileSystem.read' was never awaited", raised from `asyncio/base_events.py`. The earlier gate run on the same tree did not show it.
- **The path, read and not run.** `VirtualFileSystem._submit` in `src/vfs/sync.py` passes `self._tracked(coroutine)` to `asyncio.run_coroutine_threadsafe`. When the wait raises, it calls `future.cancel()`.
  - If the cancel lands before the loop has run the task's first step, the task is cancelled before `_tracked` awaits the verb's coroutine.
  - That coroutine is then collected unstarted, and Python warns.
- **It stays a warning.** The suite makes `ResourceWarning` and the unraisable and thread warnings errors, not `RuntimeWarning`. So the warning does not fail the test, and the call is still cancelled as the test asserts.

## Choices left open

1. **Where the coroutine is closed.** Either `_tracked` closes its coroutine in a `finally` when it never awaited it, or `_submit` passes the verb's coroutine only once the loop runs it, for example through a factory.
2. **Whether the test pins it.** The test could hold the loop so the cancel lands before the task's first step, and assert that no warning is recorded.

## Tests

- First, a deterministic reproduction: block the loop thread on an event, interrupt the wait, release the loop, and collect. It must record the warning on the current tree before any fix.

## Scope

- In: `VirtualFileSystem._submit` and `_tracked` in `src/vfs/sync.py`.
- Out: the close and drain paths, which have their own tests.

## Not checked

- Whether the session twin's submit path has the same shape.

## One line

A call cancelled before it started closes what it never ran.
