# 037 — Boundary Raise and a Single Result Channel

- **Status:** implemented (commit 06cf551, 2026-07-03)
- **Date:** 2026-07-03
- **Owner:** Clay Gendron
- **Kind:** refactor (router failure semantics) + two contract fixes
- **Depends on:** 036 (router verb surface), 035 (op vocabulary)
- **Enables:** the `DatabaseFileSystem` port (backends implement against a
  one-channel failure contract), MCP tool exposure (a tool call can never
  observe a half-applied batch it wasn't told about)

## Intent

Make `Result` the **only** failure channel inside the mount tree. Raising
becomes a property of the outermost call boundary (the client facade), not
of any filesystem node.

Two personas drive the design, and they need opposite failure behavior:

- **An app serving an LLM agent must never raise.** Errors reach the
  agent as text — the failed `Result` renders to prose via `to_str()` /
  crosses MCP as a payload with `is_error` — and the conversation
  continues. This must be structural, not a flag someone remembers to
  set: a mis-set flag in an app is an unhandled exception in front of an
  agent.
- **A developer running an ETL to populate the filesystem must get loud
  failures.** A silent failed `Result` in a fire-and-forget script reads
  as "okay, it worked" — the exact outcome to prevent. The developer
  opts into raising **once, at the boundary** (the raising client), and
  every failure becomes a kind-mapped exception.

The node layer serves the first persona unconditionally; the boundary
adapter serves the second explicitly. Concretely:

1. Delete `raise_on_error` from `VirtualFileSystem` — no node-level flag,
   no mount-time propagation, no dual-channel `_probe`.
2. Harden every `asyncio.gather` dispatch site so **all sibling groups
   settle before the router reports anything** — no fire-and-forget
   mutations.
3. Two result-channel contract fixes that fall out of the same audit:
   failed results carry `function`, and `Result.__bool__` means *success*,
   not *success and non-empty*.

## Why — verified failures in the current design

Both defects below were reproduced against `base2.py` at `54462cf`
(scripts: scratchpad `pressure_base2.py`; port into `tests/test_base.py`
as part of this story).

### Fire-and-forget mutations under `raise_on_error=True`

`asyncio.gather` with the default `return_exceptions=False` propagates the
first child exception to the awaiter but does **not** cancel or await the
sibling tasks. A grouped mutation touching a failing terminal and a slow
healthy terminal:

```python
root = VirtualFileSystem(raise_on_error=True)
await root.add_mount(SlowOkFS(), "/ok")     # write takes ~50ms
await root.add_mount(FailFS(), "/bad")      # write errors immediately

entries = [Entry(path="/ok/a.txt", content="A"),
           Entry(path="/bad/b.txt", content="B")]
await root.write(entries=entries)           # raises VFSError("boom")
```

Observed:

```text
write raised: VFSError: boom
ok.write_log immediately after raise: []
ok.write_log 100ms later:             ['/a.txt']   <- landed AFTER the caller saw the exception
```

The caller cannot know `/ok/a.txt` was written; a retry double-applies it.
The successful group's `Result` (row statuses, versions) is discarded
unseen. Every gather site has this shape: `_dispatch_grouped_observations`,
`_route_two_path`, `_route_entry_batch`, and both gathers in
`_route_fanout`.

### The node-level flag is the root cause

`raise_on_error` lives on every node and is copied onto whole subtrees at
mount time (`base2.py:177-183`). Consequences:

- Exceptions can surface *inside* internal composition points, which is
  exactly what makes the gather defect possible.
- `_probe` exists almost entirely to reconcile the two failure channels of
  a read verb (failed `Result` vs kind-mapped `VFSError`).
- The flag is mutable shared state duplicated across nodes; nothing keeps
  it coherent after mount time except convention.

One channel inside the tree deletes the whole class.

### Considered and rejected: raise only at the root mount

The obvious refinement — keep raising node-side but confine it to the
tree's root, since every node can reach it via `_root()` — does not
survive composition. "Root" is a **role, not a type**, and the role
changes at runtime: a filesystem's public verbs are simultaneously the
API a direct caller uses *and* the seam a parent router dispatches
through once the filesystem is mounted. A node that raises
because-it-is-currently-root starts throwing into its new parent's
gather the moment `add_mount` gives it a parent — recreating the
dual-channel problem this story deletes. Self-dispatch has the same
issue in miniature: `_is_path_mountable` calls the public `stat` on
*self*, so a raising root needs `_probe`-style exception arms even with
no mounts involved.

A node can never know whether it is the outermost frame of the call;
**only the caller knows**. So the raise lives in a wrapper the caller
chooses (D2), which is outermost by construction, and the node layer is
uniform: every `VirtualFileSystem` returns `Result`, whether it is a
root, a leaf, or about to become either.

## Design

### D1 — `Result` is the only internal channel

`VirtualFileSystem.__init__` loses `raise_on_error`. `_error` always
returns a failed `Result`:

```python
def _error(
    self,
    message: str,
    *,
    kind: VFSErrorKind,
    function: str = "",
    path: Path | None = None,
    data: dict[str, Any] | None = None,
) -> Result:
    """Compose a failed ``Result``. The router never raises — values in,
    Result out. Raising is the boundary's job (see ``raise_if_failed``)."""
    return Result(
        function=function,
        success=False,
        errors=[ResultError(kind=kind, message=message, path=path, data=data)],
    )
```

Deleted along with the flag:

- The subtree-propagation loop in `add_mount` (`base2.py:177-183`) and its
  comment.
- The `VFSError` / `NotFoundError` arms of `_probe` — with one channel it
  collapses to:

```python
@staticmethod
async def _probe(call: Coroutine[Any, Any, Result]) -> list[Observation] | None:
    """Await a read verb for the mountability check, mapping absence to []."""
    result = await call
    if result.success:
        return list(result.observations)
    if all(e.kind == VFSErrorKind.not_found for e in result.errors):
        return list(result.observations)
    return None
```

A raw non-`VFSError` exception from an impl remains an impl bug and
propagates with its real traceback — unchanged policy.

### D2 — raising moves to the call boundary

One function, plus a thin opt-in on the facade. `exception_for_kind` is
already the kind→exception map; it stays.

```python
# vfs/results2.py (or vfs/exceptions.py — reviewer's pick)

def raise_if_failed(result: Result) -> Result:
    """Boundary adapter: turn a failed Result into its kind-mapped exception.

    The router never raises; callers who want exceptions wrap their calls
    (or construct VFSClient(raise_on_error=True), which applies this to
    every verb). Multiple errors raise an ExceptionGroup so a fan-out
    failure reports every downed terminal, not just the first.
    """
    if result.success:
        return result
    excs = [exception_for_kind(e.kind)(e.message, result) for e in result.errors]
    if len(excs) == 1:
        raise excs[0]
    raise ExceptionGroup("multiple VFS errors", excs)
```

Caller-facing shapes, one per persona:

```python
# App serving an LLM agent — nodes return Result, always; errors are text.
fs = VirtualFileSystem()
r = await fs.grep("auth")
if not r.success:
    reply = r.to_str()          # errors render as prose for the agent
# (over MCP this is automatic: to_payload() carries is_error=not success)

# Developer ETL — opt into raising once, at the boundary; failures are loud.
client = VFSClient(fs, raise_on_error=True)
await client.write(entries=batch)     # raises WriteConflictError / NotFoundError / ...
# or ad hoc, without the facade:
raise_if_failed(await fs.write(entries=batch))
```

The opt-in is deliberately *only* at the boundary: an ETL script that
calls the raw `fs` directly still gets silent `Result`s — the raising
client **is** the ETL contract, and scripts that populate the filesystem
should construct one. In exchange, the app path cannot be misconfigured
into raising: there is no flag on any node to set wrong.

An unknown/str kind (a newer peer's novel kind crossing MCP) raises as
base `VFSError` — deliberately the *broadest* class, not `unrecognized`'s
`ValidationError`: a novel kind could be a quota, a rate limit, anything,
and a narrow class would misstate a failure this client cannot classify.
(Resolved this way by the post-implementation adversarial review; the
`ResultError` docstring states the same contract.)

### D3 — every gather settles before the router reports

All five dispatch gathers switch to `return_exceptions=True` and merge
after everything has settled. With D1 in place the only exceptions left
are impl bugs (and cancellation), so the policy is: **let all siblings
finish, then re-raise the bug** — sibling results are complete and any
retry logic upstream sees a settled world.

```python
async def _gather_settled(self, coros: Iterable[Coroutine[Any, Any, Result]]) -> list[Result]:
    """Run dispatch coroutines to completion — every sibling settles.

    A raised exception here is an impl bug (the Result channel never
    raises); it propagates after all siblings finish, so a partial batch
    can never keep mutating behind a caller who already saw a failure.
    """
    settled = await asyncio.gather(*coros, return_exceptions=True)
    bugs = [s for s in settled if isinstance(s, BaseException)]
    for bug in bugs:
        if isinstance(bug, asyncio.CancelledError):
            raise bug
    if bugs:
        if len(bugs) == 1:
            raise bugs[0]
        raise ExceptionGroup("impl errors during dispatch", [b for b in bugs if isinstance(b, Exception)])
    return list(settled)
```

Call sites (mechanical): `_dispatch_grouped_observations`,
`_route_two_path`, `_route_entry_batch`, and both gathers in
`_route_fanout` replace

```python
results = await asyncio.gather(*(_run_group(...) for ...))
return self._merge_results(list(results))
```

with

```python
results = await self._gather_settled(_run_group(...) for ...)
return self._merge_results(results)
```

### D4 — failed results carry `function`

Today `_error` never sets `function`, so on the wire an agent cannot tell
which verb failed. Every `_error` call site inside a routed verb passes
the op:

```python
return self._error(
    f"No mount found for path: {path}",
    kind=VFSErrorKind.not_found,
    function=op,
)
```

Chokepoints that already know `op` (`_route_single`, `_route_two_path`,
`_route_fanout`, `_route_entry_batch`, `_dispatch_grouped_observations`,
`mkedge`, `graph`, the `_route_pairs` front) thread it through.
`check_writable` in `vfs/permissions.py` gains an `op`-forwarding line the
same way (it already receives `op`).

### D5 — `Result.__bool__` means success

Current behavior conflates success with non-emptiness — a successful glob
with zero matches is falsy:

```python
r = Result(function="glob", observations=[], success=True)
bool(r)   # False today — the trap
```

New contract:

```python
def __bool__(self) -> bool:
    """Truthiness is success. Emptiness is a separate fact — use len()."""
    return self.success
```

`if not result:` now reads as "did it fail," which is what every call
site means. Emptiness checks are `len(result) == 0` / `result.first() is
None`. Audit existing `tests/` truthiness assertions during the port —
any test that relied on empty-success being falsy was encoding the trap.

## Out of scope

- `VFSClient` port off old `base.py` (this story only defines the
  boundary adapter it will use).
- Cross-terminal atomicity / rollback — validation-then-settle remains
  the contract; true transactional batches are a backend story.
- The rebase overflow raise (`ValueError` escaping `glob`) — that is
  story 038's gate-policy fix, not a channel problem.

## Test plan

Port the scratchpad reproductions into `tests/test_base.py`:

1. **Settle-before-report:** slow-ok + fast-fail terminals, grouped write
   → returned `Result` has `success=False`, *and* the ok terminal's rows
   are present in `observations` with their statuses; the ok write is in
   the log **before** the call returns (no post-return landing).
2. **Impl bug propagation:** one terminal raises `RuntimeError` → the
   `RuntimeError` propagates, and the sibling's write has completed
   before it does.
3. **Boundary raise:** `raise_if_failed` on a single-error result raises
   the kind-mapped exception carrying the full result; multi-error
   fan-out failure raises `ExceptionGroup` with one member per error.
4. **`_probe` single-channel:** mountability checks behave identically
   with the exception arms gone (existing 00116ae tests keep passing).
5. **`function` on failures:** every routed verb's error result reports
   its op in `function` (parametrize over `ALL_OPS` where a forced
   routing error is constructible).
6. **`__bool__`:** empty-success is truthy; failed non-empty is falsy.
7. **Removal:** constructing `VirtualFileSystem(raise_on_error=True)`
   is a `TypeError`; `add_mount` no longer touches child flags.

## Migration notes

- `permissions.py` module docstring: drop the `raise_on_error=True`
  paragraphs (the `read_only`-kind → `WriteConflictError` mapping now
  happens only at the boundary adapter).
- `exceptions.exception_for_kind` is unchanged and becomes
  boundary-only.
- Old `base.py` / `client.py` keep their behavior until their own port
  story; this story touches `base2.py`, `results2.py`, `permissions.py`,
  `tests/` only.
