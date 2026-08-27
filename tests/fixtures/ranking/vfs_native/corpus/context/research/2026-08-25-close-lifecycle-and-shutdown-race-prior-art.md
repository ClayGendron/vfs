# Prior art — close/dispose lifecycle and the shutdown race

- **Date:** 2026-08-25
- **Method:** two research agents over the read-only reference
  checkouts under `~/Git/Repos/` (sqlalchemy, sqlite, postgres,
  pyfilesystem2, filesystem_spec, opendal, minio, seaweedfs) plus
  stdlib/Go/trio design knowledge, each answering one question posed
  by the 2026-08-25 remediation-round landing review's decision pass
  (`2026-08-25-remediation-round-landing-review.md`). New
  investigation, gathered to inform two pending rulings; citations
  are repo-relative to the sibling checkouts.
- **Question 1:** for a resource-holding handle that revives on use
  after `close()`, should teardown be gated by a one-shot closed
  latch, or run on every close? (Feeds spec 126.)
- **Question 2:** when shutdown races in-flight work, does prior art
  let the work finish on the resource it captured, migrate it per
  step to fresh resources, or bound/chunk a degraded path? (Feeds
  spec 129's posture on the close-window prose.)

## 1. Close/dispose lifecycle — the latch question

### SQLAlchemy: no latch exists; dispose is a repeatable pool-flush

The binding prior art, since vfs's revival contract sits directly on
it. `Engine.dispose()` (`sqlalchemy/lib/sqlalchemy/engine/base.py:3137`)
is not a state transition: it drains the current pool and immediately
installs a fresh one (`self.pool.dispose(); self.pool =
self.pool.recreate()`). **No disposed flag exists anywhere on
`Engine`**; the docstring's own words are "a new connection pool is
created immediately after the old one has been disposed," so
connect-after-dispose works by construction and repeated dispose is
trivially safe. `AsyncEngine.dispose()`
(`ext/asyncio/engine.py:1145`) is a pure passthrough. The docs
(`doc/build/core/connections.rst`, engine-disposal section) list
"many ad-hoc, short-lived Engine objects created and disposed" as
first-class usage. Every pool `dispose()` is **idempotent by
cheapness, never by flag**: `QueuePool.dispose()` pulls until
`Empty`, `NullPool.dispose()` is `pass`, `StaticPool.dispose()` is
an existence check (`pool/impl.py:218/317/471`).

### The stdlib pattern: latch and refusal always travel together

`io` file objects, `sqlite3.Connection`, and
`concurrent.futures.Executor` all make close idempotent — and in
every one of them, the closed flag exists **to refuse subsequent
use** (`ValueError`, `ProgrammingError`, `RuntimeError` on
post-shutdown submit), with teardown-skipping only a byproduct. None
revives. (vfs already treats its offload executor accordingly:
the stdlib object is terminal, so close clears the slot and the next
call re-mints a *new* one — revival by replacement.)

### pyfilesystem2: the coherent counter-model vfs rejected

`FS.close()` (`pyfilesystem2/fs/base.py:375`) sets `_closed = True`
and **every operation refuses** afterward via `check()` →
`FilesystemClosed` (`base.py:1664`). Latch + refuse is internally
consistent: nothing can acquire resources after the latch falls, so
a skipped second teardown has nothing to strand. This is exactly the
design vfs's conformance suite pins *against*
(`test_pattern_search_serves_after_close`).

### fsspec and opendal: where revival is expected, terminal close is eliminated

`AbstractFileSystem` has no `close()` and no closed flag at all —
teardown is cache-eviction plus `weakref.finalize` (best-effort, no
latch; `fsspec/spec.py:1599`, `implementations/http.py:122`), and
"revival" is reconstruction from cache. opendal's `Operator`
(`core/src/types/operator/operator.rs:167`) has no
close/shutdown/dispose whatsoever; teardown is drop of the last
clone. Close exists only on single-use per-stream handles.

### SQLite: never claim teardown that has not completed

`sqlite3_close_v2` (`sqlite/src/main.c:1353`) marks the connection a
zombie and **frees only when the last statement/backup finishes**
(`sqlite3LeaveMutexAndCloseZombie`, main.c:1365) — the release
*request* and the *completion* of teardown are decoupled, and state
never asserts completion early. (Its zombie is still terminal —
lawful there because use-after-close is refused as MISUSE.) minio
confirms the pairing a third time: its revivable state (`offline`)
has no latch, its latched state (`closed`) refuses
(`minio/internal/rest/client.go:390`).

### Verdict 1

Prior art supports **dropping the one-shot latch and tearing down on
every close, idempotent by cheapness** — SQLAlchemy is that exact
design, one layer down. **No surveyed system pairs a one-shot close
latch with revival-on-use**, and the survey shows why: every latch's
real job is refusal; keep the latch without the refusal and the
skipped teardown strands whatever revival re-acquired — the
mechanism of the observed Postgres leak. Second law, from SQLite:
never set closed-state *before* the awaited teardown completes; a
cancellation between flag and dispose latches a lie.

## 2. The shutdown race — who finishes in-flight work, and where

### The drain idiom dominates everything surveyed

Go's `http.Server.Shutdown` gates new work and lets admitted
requests **run to completion on their original goroutines**,
unbounded unless the *caller's* context imposes a deadline — and
deadline expiry abandons, it does not interrupt. minio wraps every
handler: new requests get 503 after the shutdown flag, admitted ones
run untouched (`minio/internal/http/server.go` `Server.Init`/
`Shutdown`); its background-work drain races a 60 s timer owned by
the stopper (`cmd/signals.go:32`). seaweedfs's vendored `httpdown`
states the ladder crisply — drain (`StopTimeout`) → force-close →
abandon (`KillTimeout`), each stage a wall-clock bound imposed by
the stopper (`weed/util/httpdown/http_down.go:22-55`). Postgres
makes drain-vs-cancel-vs-abort a **named operator policy**
(smart/fast/immediate, `src/backend/postmaster/postmaster.c` signal
handling), and no mode migrates or degrades a running query.
`concurrent.futures`: work already submitted keeps running on the
same pool threads after `shutdown(wait=False)` returns; nothing is
ever migrated to another executor. SQLite's zombie close is the
same shape at the connection level: in-flight statements finish on
the **original, fully functional resource** because teardown is
deferred, not because the work degrades.

### Per-step re-checks exist — and always mean stop, never switch

trio/anyio deliver cancellation at every checkpoint, and seaweedfs
consults `IsStopping()` inside long subscription loops
(`weed/util/log_buffer/log_read.go`) — but in every instance the
observed flag **cancels** the work. No surveyed system re-acquires
per step and continues on fresh resources. The nearest cousin is
SQLAlchemy's `dispose()`+`recreate()`, which deliberately stops
short: checked-out connections finish on the old pool; only *new*
checkouts ride the fresh one (`engine/base.py:3137` docstring).

### Verdict 2

- **(A) finish on the captured resource** is the universal shape;
  where a bound exists it is a wall-clock deadline owned by the
  **closer**, escalating to cancel/abort — never chunked or slower
  completion.
- **(B) per-hop migration to a re-minted pool has no precedent**
  anywhere in the survey.
- **(C) bounding degraded work by work-units has no precedent**
  either.

vfs's shape is unusual in one respect worth recording: everywhere
else the racing operation finishes on the *original* resource
because close defers teardown; vfs tears down eagerly and the
racing verb degrades to the event loop. The prior-art-faithful
upgrade, if the close-window loop stall is ever deemed
unacceptable, is therefore a **zombie pool** (defer executor
teardown until in-flight verbs drain — the SQLite/SQLAlchemy
shape), or a closer-owned drain deadline — not per-hop pool
re-reads and not chunked inline fallback. Recorded as an open
question; the ruling for now is prose-plus-pin (spec 129).
