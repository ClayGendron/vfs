# 026 — VFSResult by Mount + Structured Errors

- **Status:** draft
- **Date:** 2026-05-03
- **Owner:** Clay Gendron
- **Kind:** refactor + contract + constitutional amendment
- **Depends on:** 015 (router calls public API), 016 (`MountError`
  / `MountErrorKind`), 025 (`_WriteAbort` orchestrator)
- **Enables:** FSP error envelope, MCP wire mapping, CLI /
  `parse_query` error surface, long-op cancellation surface,
  data-pipeline ergonomics on `VFSClient`

## TL;DR

Two changes in one story, because they are one design decision:

1. **`VFSResult` partitions by mount.** `VFSResult.mounts:
   list[MountResult]` replaces the old single envelope.
   `MountResult` carries `(mount, success, message, candidates)`
   per terminal filesystem the op visited.
2. **Errors are typed Python exceptions, prose-only on the wire.**
   A 13-kind internal `VFSErrorKind` enum drives a typed
   exception hierarchy (`NotFoundError`, `ExistsError`, …).
   `MountResult.message` is prose. `_classify_error` (the
   prose-classifying function) is deleted. The kind is supplied
   at the construction site, never inferred.

The raise rule (v1 — strict, single policy):

```python
# When raise_on_error is set, raise on ANY mount failure.
if self._raise_on_error and result.mounts and not result.success:
    raise <typed subclass>(result.message, result=result)
```

Where `result.success = all(m.success for m in result.mounts)`.

This is the most honest v1 policy: any error is a problem. A
write that landed on two mounts and failed on a third is a
half-finished batch, not a success — the sync pipeline raises,
the async caller sees `success=False`. Per-operation policies
(read-style "any-mount-succeeded counts as success") are deferred
to a follow-up; v1 treats every operation the same way.

`VFSClient` (sync) defaults `raise_on_error=True` — sync devs
write data pipelines and want to know when something breaks.
`VFSClientAsync` defaults `raise_on_error=False` — async devs
write apps and don't want surprise exceptions; they handle
results explicitly.

This deviates from the current constitution (7 error kinds, no
mount partition on results). The amendment to Article 2 is in
scope.

---

## 1. Problem

Two defects, both observable on `main`, both addressed in one
change because they are entangled:

### 1.1 Prose-classified errors

```python
def _classify_error(message, errors, result) -> VFSError:
    first = errors[0] if errors else message
    if "Not found:" in first or "Not a directory:" in first:
        return NotFoundError(message, result)
    if "No mount found" in first:
        return MountError(message, result)
    if "Already exists" in first or "Cannot write" in first or "Cannot delete" in first:
        return WriteConflictError(message, result)
    if "failed:" in first:
        return GraphError(message, result)
    if any(kw in first for kw in ("requires", "Invalid", "Duplicate", "Source not found")):
        return ValidationError(message, result)
    return VFSError(message, result)
```

Any of 67 `_error(...)` call sites can be reworded and silently
change exception type. The exception class is recovered from
prose by string match.

### 1.2 No mount provenance on results

Today's `VFSResult` has one flat `errors: list[str]` and one flat
`candidates: list[Candidate]`. A merged result from a fan-out
across `/postgres` + `/mssql` reduces every failure to a free-form
string; the agent cannot tell which mount produced which error,
which mounts succeeded, or which work landed.

CLI failures (`parse_query` raises bare `ValueError` for unknown
commands) bypass the structured envelope entirely. Long-op
deadline / cancellation surfaces have nowhere to land.

### 1.3 Why one story

The shape change (1.2) and the typed-exception change (1.1) touch
the same files, the same 67 call sites, and the same renderers.
Splitting them means touching every call site twice. The raise
rule depends on per-mount `success` existing. The renderer rewrite
needs both. One story.

---

## 2. The taxonomy

The 13 kinds live as an **internal Python enum** — they drive the
exception class `raise_on_error=True` raises, but they do not
appear on `MountResult` or in JSON output. The wire shape is
prose.

The derivation rule: every kind appears in at least three of the
four canonical traditions (POSIX, Plan 9, gRPC, MCP/JSON-RPC).

### 2.1 The four traditions

- **POSIX `<errno.h>` (IEEE 1003.1-2024)** — 107 codes;
  `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/sys/errno.h`.
- **Plan 9 `/sys/src/9/port/error.h`** — ~50 named `extern char
  E*[]` strings carried on 9P's `Rerror` message.
- **gRPC** — 17 status codes; modern compressed peer.
- **MCP / JSON-RPC 2.0** — 5 base codes plus MCP's
  `URL_ELICITATION_REQUIRED = -32042` and the `TaskStatus`
  vocabulary.

### 2.2 The 13 kinds

```python
from enum import StrEnum

class VFSErrorKind(StrEnum):
    # — namespace / object existence —
    NotFound          = "vfs.not_found"          # ENOENT,    Enonexist
    Exists            = "vfs.exists"             # EEXIST,    Eexist
    WrongKind         = "vfs.wrong_kind"         # ENOTDIR/EISDIR, Enotdir/Eisdir
    NotEmpty          = "vfs.not_empty"          # ENOTEMPTY

    # — authorization —
    PermissionDenied  = "vfs.permission_denied"  # EACCES/EPERM/EROFS, Eperm/Enocreate

    # — capability / method discovery —
    Unsupported       = "vfs.unsupported"        # ENOSYS/ENOTSUP, Enotconf/Enodev
    Unrecognized      = "vfs.unrecognized"       # METHOD_NOT_FOUND (-32601)

    # — request validity —
    Invalid           = "vfs.invalid"            # EINVAL/ENAMETOOLONG, Ebadarg, INVALID_PARAMS

    # — concurrency / preconditions —
    Conflict          = "vfs.conflict"           # ESTALE/EBUSY, Einuse/Eismtpt, FAILED_PRECONDITION
    CrossMount        = "vfs.cross_mount"        # EXDEV, Emount/Eunion

    # — runtime liveness —
    Unavailable       = "vfs.unavailable"        # EIO/ECONNREFUSED/ENOSPC/EAGAIN, Eio, INTERNAL_ERROR
    Timeout           = "vfs.timeout"            # ETIMEDOUT, Etimedout, DEADLINE_EXCEEDED
    Cancelled         = "vfs.cancelled"          # ECANCELED/EINTR, Eintr, CANCELLED
```

### 2.3 What changed from the constitution's 7

| Constitution | This spec | Why |
|---|---|---|
| `NotFound` | `NotFound` | Same. ENOENT direct. |
| (folded) | **`Exists`** (new) | EEXIST is its own POSIX/Plan 9 code; the agent retry differs (`overwrite=True` vs. re-read). |
| (folded) | **`WrongKind`** (new) | ENOTDIR/EISDIR. "Path exists but as the wrong kind" is too actionable to bury. |
| (folded) | **`NotEmpty`** (new) | ENOTEMPTY. Specific recovery (`cascade=True`). |
| `PermissionDenied` | `PermissionDenied` | Same. |
| `UnsupportedCapability` | **`Unsupported`** (renamed) | gRPC `UNIMPLEMENTED` register. |
| (absent) | **`Unrecognized`** (new) | JSON-RPC `METHOD_NOT_FOUND`. CLI / MCP needs it. |
| `Invalid` | `Invalid` | Same. EINVAL direct. |
| `Conflict` | `Conflict` | Reduced scope — overwrite/not-empty/wrong-kind moved out. |
| `CrossMount` | `CrossMount` | Same. EXDEV direct. |
| `BackendUnavailable` | **`Unavailable`** (renamed) | Drops "Backend"; gRPC `UNAVAILABLE`. |
| (absent) | **`Timeout`** (new) | ETIMEDOUT direct. Constitution §5 already requires deadlines. |
| (absent) | **`Cancelled`** (new) | ECANCELED direct. Distinct from `Timeout` in every tradition. |

### 2.4 Deliberately rejected

- **`RateLimited`** — folds into `Unavailable` with
  `detail.reason="rate_limited"` (detail lives only on the
  exception, not the wire) until a real boundary appears.
- **`OutOfRange`** — gRPC streaming concept; not applicable.
- **`DataLoss`** — no detection layer.
- **`Internal` / `Unknown`** — invites lazy classification.
- **WebDAV `Locked`** — we use optimistic concurrency
  (`if_revision`), not pessimistic locks. Folds into `Conflict`.
- **POSIX socket / process errnos** — not filesystem.

### 2.5 Two design choices

- **String identifiers, not integers.** Plan 9 / gRPC names.
  POSIX/FUSE use small ints because the kernel ABI needs them;
  we don't.
- **One enum value per *agent decision*, not per *kernel
  condition*.** ENOTEMPTY is a kind because the retry differs.
  EALREADY is not because the agent does the same thing it
  would for `Conflict`.

---

## 3. Two audiences, two surfaces

| Audience | Reads | Gets |
|---|---|---|
| **The LLM agent** (via JSON / MCP / CLI render) | `MountResult.message`, `MountResult.success`, `mount` | Prose. No taxonomy. |
| **The Python developer** (via `try / except`) | The raised exception class | Typed. `except NotFoundError:`. |

The kind enum exists *only* to drive the exception class. It
never reaches JSON, never appears in `MountResult`, never shows
up in renderer output.

This is the FastAPI / MCP idiom: typed exception inside, prose
outside. FastAPI's `HTTPException` carries `status_code` and
`detail`; Pydantic's `ValidationError` is the same pattern. MCP
SEP-1303 made this exact decision for tool-execution errors —
prose to the model, types inside.

---

## 4. The data model

### 4.1 `MountResult` — per-mount outcome

```python
from pydantic import BaseModel, PrivateAttr

class MountResult(BaseModel):
    mount: str                        # "/" inside the terminal; rewritten by router
    success: bool
    message: str = ""                 # "" on success; prose on failure
    candidates: list[Candidate] = []

    # Internal-only: the typed error kind, used by _return_or_raise to
    # pick the exception class. PrivateAttr — not serialized to JSON,
    # not in the public schema, not visible to agents via to_str.
    _kind: VFSErrorKind | None = PrivateAttr(default=None)

    def add_prefix(self, prefix: str) -> MountResult:
        """Stamp the router-side mount prefix on the way back up."""
        if not prefix:
            return self
        new_mount = "/" if self.mount == "/" else self.mount
        new_mount = prefix if new_mount == "/" else f"{prefix}{new_mount}"
        new_candidates = [
            c.model_copy(update={"path": prefix + c.path if c.path != "/" else prefix})
            for c in self.candidates
        ]
        out = self.model_copy(update={"mount": new_mount, "candidates": new_candidates})
        out._kind = self._kind        # carry the kind through prefix rewrites
        return out
```

`MountResult` is **mutable** — not `frozen=True`. Routers
rewrite `mount` (via `add_prefix`) and may attach
implementation state as the result rises through the mount
chain, so freezing the model would force `model_copy` everywhere
the existing per-mount surface evolves. `Candidate` stays frozen
(its identity is the path); `MountResult` does not.

Terminal filesystems produce `mount="/"` because they don't
know what they're mounted as. `add_prefix` rewrites `mount` and
every candidate's `path` together, preserving `_kind` so the
raise rule still has the typed kind on the way up.

`_kind` is a Pydantic `PrivateAttr`. It does not appear in
`model_dump()` or `to_json()`, does not contribute to the model
schema, and is invisible to agents reading `to_str`. The only
consumers are `_error()` (writes) and `_return_or_raise` (reads).

### 4.2 `VFSResult` — partition by mount

```python
class VFSResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    function: str = ""
    mounts: list[MountResult] = []

    # — derived/convenience accessors —

    @property
    def success(self) -> bool:
        """True only if every dispatched mount succeeded.

        v1 is strict: any mount failure flips the whole result to
        ``success=False``. The sync client (raise_on_error=True)
        raises on this; the async client returns it for the caller
        to inspect ``mounts``. Empty ``mounts`` (nothing dispatched)
        is True — there's nothing to fail.
        """
        return all(m.success for m in self.mounts) if self.mounts else True

    @property
    def candidates(self) -> list[Candidate]:
        """Flattened across mounts, in dispatch order."""
        return [c for m in self.mounts for c in m.candidates]

    @property
    def message(self) -> str:
        """Failure prose, one line per failed mount.

        Empty string on full success (no mount failed).
        Single-mount failure → the mount's prose, unannotated.
        Multi-mount with failures → ``"(mount=<m>) <prose>"`` per
        failed mount, joined by ``"\\n"``. Successful mounts do not
        appear in ``message`` — successful work is in
        ``candidates``, not in the prose.

        This is what ``to_str`` prints in the error block (§11)
        and what the typed exception carries as its primary
        message when ``raise_on_error`` is set.
        """
        failed = [m for m in self.mounts if not m.success]
        if not failed:
            return ""
        if len(self.mounts) == 1:
            return failed[0].message
        return "\n".join(f"(mount={m.mount}) {m.message}" for m in failed)

    @property
    def mount(self) -> MountResult:
        """The single mount, when there is exactly one. Else raises."""
        if len(self.mounts) != 1:
            raise ValueError(f"VFSResult has {len(self.mounts)} mounts, not 1")
        return self.mounts[0]

    @property
    def file(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None

    @property
    def content(self) -> str | None:
        return self.candidates[0].content if self.candidates else None

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(c.path for c in self.candidates)

    def __bool__(self) -> bool:
        return self.success and bool(self.candidates)

    def __len__(self) -> int:
        return len(self.candidates)

    def __contains__(self, path: str) -> bool:
        return path in self.paths
```

`errors: list[str]` is gone. There is no `VFSErrorRecord`. There
is no `VFSPartial`. The result is a list of `MountResult`, period.

### 4.3 What `_error(...)` returns

A construction site that fails inside a terminal filesystem
returns a `VFSResult` with one `MountResult` whose `mount="/"`,
`success=False`, `message=<prose>`, and `_kind` stamped with the
typed enum value:

```python
def _error(self, kind: VFSErrorKind, message: str) -> VFSResult:
    """Compose a single-mount failed result.

    The kind is stored on the MountResult's PrivateAttr so the
    @boundary decorator's _return_or_raise hook can pick the right
    exception class without ever exposing the kind on the public
    result shape.
    """
    mr = MountResult(mount="/", success=False, message=message)
    mr._kind = kind
    return VFSResult(
        function=self._current_function,    # set by the dispatcher
        mounts=[mr],
    )
```

The kind lives on `MountResult._kind` (PrivateAttr — see §4.1).
It does not appear in `model_dump()`, `to_json()`, or `to_str`.
The only consumers are `_error` (writes the kind) and
`_return_or_raise` (reads it to pick the exception class).

### 4.4 The exception hierarchy

One subclass per kind, all `VFSError` subclasses:

```python
class VFSError(Exception):
    def __init__(self, message: str, *, result: VFSResult | None = None) -> None:
        super().__init__(message)
        self.result = result

class NotFoundError(VFSError):           pass
class ExistsError(VFSError):             pass
class WrongKindError(VFSError):          pass
class NotEmptyError(VFSError):           pass
class PermissionDeniedError(VFSError):   pass
class UnsupportedError(VFSError):        pass
class UnrecognizedError(VFSError):       pass
class InvalidError(VFSError):            pass
class ConflictError(VFSError):           pass
class CrossMountError(VFSError):         pass
class UnavailableError(VFSError):        pass
class VFSTimeout(VFSError):              pass     # avoids TimeoutError builtin
class VFSCancelled(VFSError):            pass     # avoids asyncio.CancelledError

_EXCEPTION_FOR_KIND: dict[VFSErrorKind, type[VFSError]] = {
    VFSErrorKind.NotFound:         NotFoundError,
    VFSErrorKind.Exists:           ExistsError,
    VFSErrorKind.WrongKind:        WrongKindError,
    VFSErrorKind.NotEmpty:         NotEmptyError,
    VFSErrorKind.PermissionDenied: PermissionDeniedError,
    VFSErrorKind.Unsupported:      UnsupportedError,
    VFSErrorKind.Unrecognized:     UnrecognizedError,
    VFSErrorKind.Invalid:          InvalidError,
    VFSErrorKind.Conflict:         ConflictError,
    VFSErrorKind.CrossMount:       CrossMountError,
    VFSErrorKind.Unavailable:      UnavailableError,
    VFSErrorKind.Timeout:          VFSTimeout,
    VFSErrorKind.Cancelled:        VFSCancelled,
}
```

`_classify_error` is deleted. The kind comes from the
construction site; the lookup is a dict access.

---

## 5. Set algebra

`VFSResult` algebra (`&`, `|`, `-`) defers to per-mount algebra,
matching mounts by `mount` field. When two results are combined:

- **Same mount on both sides** → algebra runs on that mount's
  candidates (left wins on overlap).
- **Mount only on left** → carried through as-is.
- **Mount only on right** → carried through as-is.
- **`function` mismatch** → result `function = "hybrid"`. Same
  rule as today.

```python
def __or__(self, other: VFSResult) -> VFSResult:
    by_mount: dict[str, MountResult] = {m.mount: m for m in self.mounts}
    for rm in other.mounts:
        if rm.mount in by_mount:
            by_mount[rm.mount] = _merge_mount_or(by_mount[rm.mount], rm)
        else:
            by_mount[rm.mount] = rm
    return VFSResult(
        function=self._merged_function(other),
        mounts=list(by_mount.values()),
    )
```

`_merge_mount_or` does the existing left-wins candidate merge
within one mount. `&` and `-` follow the same per-mount pattern.

Cross-mount merging never happens. A user who wants flattened
candidates uses `result.candidates` (the property).

---

## 6. Routing changes

Three router methods produce multi-mount results today:
`_route_fanout`, `_route_glob_fanout`, `_route_grep_fanout`.
Each gets two changes:

1. **Build a `MountResult` per mount it dispatched to**, instead
   of merging into a flat `VFSResult`. The `mount=` field is set
   to the accumulated prefix as the result rises through the
   mount chain.
2. **Apply `add_prefix` on the way back up**, mirroring the
   existing candidate-path rewrite.

Single-mount routers (`_route_single`, `_route_two_path`,
`_route_write_batch` when one terminal) return a one-element
`mounts` list.

`_merge_results` becomes a `MountResult`-aware merge: collect by
`mount` field, run per-mount algebra on collisions, preserve
order.

The terminal `_*_impl` methods do not change. They still return
`VFSResult` with `mount="/"` on their `MountResult`. The router
stamps the prefix on the way back.

---

## 7. The raise rule

The instance flag stays — but its default differs by client:

```python
class VFSClient:                    # sync
    def __init__(self, ..., raise_on_error: bool = True): ...

class VFSClientAsync:               # async
    def __init__(self, ..., raise_on_error: bool = False): ...
```

**Why split the default.** `VFSClient` (sync) is used in data
pipelines — short scripts, ETL jobs, notebooks. The pipeline dev
wants to know when something breaks; surprise data loss in a
silent `success=False` is the worst outcome. Default `True`.

`VFSClientAsync` is used in apps, agents, and long-running
services. The app dev handles results explicitly and does not
want surprise exceptions interleaving with their async control
flow. Default `False`.

Both surfaces let the caller flip the flag at construction:

```python
sync = VFSClient(..., raise_on_error=False)    # opt out of raises in pipelines
app  = VFSClientAsync(..., raise_on_error=True)  # opt in to raises in apps
```

### 7.1 The `@boundary` decorator

The rule fires at the public boundary only — implemented as a
decorator applied explicitly to every public method that returns
a `VFSResult`. The decorator is the **single source of truth**
for "what does the public surface do with a failed result?"

```python
# vfs/boundary.py

import asyncio
import functools
from typing import Callable

def boundary(fn: Callable) -> Callable:
    """Apply the result-contract rule at the public surface.

    Every public method that returns a ``VFSResult`` is decorated
    with ``@boundary``. The decorator routes the returned value
    through ``self._return_or_raise(...)``, which decides whether
    to surface the result or raise a typed exception based on the
    instance's ``raise_on_error`` flag and the per-mount success
    pattern.
    """
    if asyncio.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(self, *args, **kwargs):
            result = await fn(self, *args, **kwargs)
            return self._return_or_raise(result)
        return async_wrapper

    @functools.wraps(fn)
    def sync_wrapper(self, *args, **kwargs):
        result = fn(self, *args, **kwargs)
        return self._return_or_raise(result)
    return sync_wrapper
```

One decorator that detects coroutine vs. function at class
definition time, so `@boundary` can be applied uniformly across
sync and async surfaces without the caller picking a variant.
The runtime check is paid once per method definition, never at
call time.

### 7.2 The `_return_or_raise(...)` hook

The decorator delegates to a method on the instance. The rule
lives on `self`, not in the decorator. Subclasses that need a
different policy (e.g., a future `raise_on_any_mount_failure`
mode) override the method, not the decorator.

```python
class VirtualFileSystem:
    def _return_or_raise(self, result: VFSResult) -> VFSResult:
        """Decide whether to return *result* or raise its typed exception.

        v1 policy: **raise on any mount failure** when
        ``self._raise_on_error`` is set. There is no partial-success
        loophole. A write that landed on two mounts and failed on
        a third raises; a search that returned data from two mounts
        and a connection-refused on a third also raises. Both are
        "something went wrong"; the typed exception names what,
        and ``result.message`` enumerates which mount did what.

        Per-operation policies (read-style fan-out tolerating
        partial failure) are deferred to a follow-up. v1 treats
        every operation the same way — the most honest baseline.
        """
        if not self._raise_on_error:
            return result
        if not result.mounts:                  # nothing dispatched
            return result
        if result.success:                     # all mounts succeeded
            return result
        # At least one mount failed. Pick the kind from the first failed mount.
        failed = next(m for m in result.mounts if not m.success)
        kind = failed._kind                    # stashed by _error()
        raise _EXCEPTION_FOR_KIND[kind](result.message, result=result)
```

The "any mount failed" condition is strict by design. There is
no `raise_on_partial` flag because there is no partial-success
loophole to flip; v1 is strict. The async client surfaces the
same shape as a return: `result.success = False`, `result.message`
enumerating per-mount outcomes, `result.mounts` available for
inspection. The exception's `.result` carries the same breakdown
so a `try / except` on the sync side has full provenance.

### 7.3 Selective application

`@boundary` is applied **explicitly, only to public methods that
return `VFSResult`**. Methods that return other shapes
(`add_mount`, `remove_mount`, `close`, `parse_query`, the
`__init__` constructor) are not decorated — the decorator does
not type-sniff its return value. Forgetting to decorate a new
public method is caught by the boundary tests in §13.

```python
class VirtualFileSystem:

    @boundary
    async def read(self, path, ...) -> VFSResult:
        return await self._route_single("read", path, ...)

    @boundary
    async def glob(self, pattern, ...) -> VFSResult:
        return await self._route_glob_fanout(...)

    # NOT decorated — not a result-returning method:
    async def add_mount(self, path, filesystem) -> None: ...
    async def close(self) -> None: ...
```

Reading a public method's signature now tells the contributor
two things at a glance: the return type (`VFSResult`) and the
boundary policy (the `@boundary` decorator). The two travel
together; missing one is a bug.

### 7.4 Why a decorator (not a method called at the end)

The previous draft of this story called a `_maybe_raise(result)`
helper at the end of every public method:

```python
async def read(self, path, ...) -> VFSResult:
    result = await self._route_single("read", path, ...)
    return self._maybe_raise(result)        # ← every method must remember this
```

That shape has two real defects. First, every new public method
has to remember to call the helper; forgetting it silently
breaks the contract. Second, the call-it-yourself pattern
distributes the boundary rule across every method head, instead
of locating it in one place. The decorator deletes both
problems: the rule is one block of code, applied uniformly, and
the absence of `@boundary` on a result-returning method is
visible in code review.

The decorator approach has a small cost — `functools.wraps`
preserves signatures but type checkers can occasionally lose
overload information through async wrappers. We accept this; the
codebase already runs `ty` against typed wrappers elsewhere (see
`_use_session`) and the patterns are known.

---

## 8. Per-kind usage guide

Each entry: when to use, when NOT to use, the exception class,
and an example showing both the result an agent sees and the
exception a sync caller catches.

### `NotFound` — `NotFoundError`

- **Use when** a path the operation needs does not exist. POSIX
  `ENOENT`. Includes "no mount resolves this path."
- **Do NOT use when** the path *exists but is the wrong kind*
  (`WrongKind`), the path is *malformed* (`Invalid`), or no rule
  grants you write access (`PermissionDenied`).
- **Example:**
  ```python
  >>> r = await async_vfs.read("/missing.md")
  >>> r.success, r.mounts[0].message
  (False, "not found: /missing.md")

  >>> sync_vfs.read("/missing.md")    # raise_on_error=True by default
  Traceback (most recent call last):
    ...
  vfs.exceptions.NotFoundError: not found: /missing.md
  ```

### `Exists` — `ExistsError`

- **Use when** a write would create at a path that already
  exists and the caller passed `overwrite=False`. POSIX `EEXIST`.
- **Do NOT use when** the conflict is about state version
  (`Conflict`) or kind (`WrongKind`).
- **Example:**
  ```python
  >>> sync_vfs.write(path="/notes.md", content="…", overwrite=False)
  Traceback (most recent call last):
    ...
  vfs.exceptions.ExistsError: path already exists: /notes.md
  ```

### `WrongKind` — `WrongKindError`

- **Use when** the operation needs a directory and finds a
  file (or vice versa, or a chunk-parent that's not a file).
  POSIX `ENOTDIR` / `EISDIR`. Plan 9 `Enotdir` / `Eisdir`.
- **Do NOT use when** the path doesn't exist (`NotFound`) or
  the kind is right but the state is wrong (`Conflict`).

### `NotEmpty` — `NotEmptyError`

- **Use when** delete refuses because the target directory has
  children and `cascade=False`. POSIX `ENOTEMPTY`.
- **Do NOT use when** delete refuses for any other reason.

### `PermissionDenied` — `PermissionDeniedError`

- **Use when** a mutation hits a read-only mount, read-only
  override, or future ReBAC rule. POSIX `EACCES` / `EROFS`.
- **Do NOT use when** the op is unsupported by the backend
  (`Unsupported`), the call shape is wrong (`Invalid`).

### `Unsupported` — `UnsupportedError`

- **Use when** the op is recognized and well-formed but the
  resolved terminal filesystem cannot execute it
  (`semantic_search` with no embedding provider configured).
  POSIX `ENOSYS` / `ENOTSUP`. gRPC `UNIMPLEMENTED`.
- **Do NOT use when** the op name is unknown to the parser
  (`Unrecognized`), the args are wrong (`Invalid`), or the
  capability is declared but transient failure stopped it
  (`Unavailable`).

### `Unrecognized` — `UnrecognizedError`

- **Use when** the CLI / `parse_query` / MCP tool router
  receives a verb, flag, or expression it has no handler for.
  JSON-RPC `METHOD_NOT_FOUND` (-32601).
- **Do NOT use when** the verb is recognized and the args are
  wrong (`Invalid`) or this backend doesn't support it
  (`Unsupported`).
- **Example:** The CLI today raises bare `ValueError`; after this
  story it returns `MountResult(success=False, message="unknown
  command: grup — did you mean 'grep'?")` and on the sync client
  raises `UnrecognizedError`.

### `Invalid` — `InvalidError`

- **Use when** the call shape is wrong: missing required args,
  contradictory args, malformed pattern, `max_depth < 1`,
  post-tokenize empty query, write to root path, write to a
  `chunk`/`version`/`edge` kind from the user surface, duplicate
  path inside one batch, embedding provider returns wrong shape.
  POSIX `EINVAL`.
- **Heuristic:** "would this call be valid against an empty
  filesystem?" If no → `Invalid`.

### `Conflict` — `ConflictError`

- **Use when** an `if_revision=` mismatch fires (Constitution
  §1.5), a precondition does not hold. POSIX `ESTALE` / `EBUSY`.
  gRPC `FAILED_PRECONDITION`.
- **Do NOT use when** the conflict is "already exists" (use
  `Exists`), "not empty" (use `NotEmpty`), "wrong kind" (use
  `WrongKind`).

### `CrossMount` — `CrossMountError`

- **Use when** an op the contract declares same-mount is asked
  to span two: `mkedge` between paths in different mounts,
  atomic `move`/`copy` whose endpoints split. POSIX `EXDEV`.
  Plan 9 `Emount`.
- **Do NOT use when** a fan-out search merely visits multiple
  mounts — that is the normal multi-mount case, not an error.

### `Unavailable` — `UnavailableError`

- **Use when** the backend is reachable-but-broken or
  unreachable: SQLAlchemy driver exception during persist,
  embedding-provider HTTP error, auto-chunk / index-maintenance
  runtime failure, connection refused. POSIX `EIO` /
  `ECONNREFUSED` / `EAGAIN`. gRPC `UNAVAILABLE` / `INTERNAL`.
- **Do NOT use when** the failure is the caller's fault
  (`Invalid`), the backend doesn't declare the capability
  (`Unsupported`), the op timed out (`Timeout`), or a public-state
  contradiction would result (`Conflict` / `Exists`).

### `Timeout` — `VFSTimeout`

- **Use when** an op could not complete within a deadline set
  by the caller, harness, or backend (SQL `statement_timeout`,
  HTTP read timeout, MCP long-op TTL). POSIX `ETIMEDOUT`. gRPC
  `DEADLINE_EXCEEDED`.
- **Do NOT use when** the work was *cancelled* by an explicit
  caller decision (`Cancelled`), or the backend hard-failed
  (`Unavailable`).

### `Cancelled` — `VFSCancelled`

- **Use when** an in-flight op observes an explicit cancel:
  `asyncio.CancelledError` propagated to the result boundary,
  MCP `notifications/cancelled` received. POSIX `ECANCELED` /
  `EINTR`. gRPC `CANCELLED`.
- **Do NOT use when** a deadline elapsed (`Timeout`), or the
  cancel arrived before the op started (return success with empty
  candidates — there is nothing to undo).

---

## 9. Worked end-to-end examples

### 9.1 Single-mount happy path (the common case)

```python
>>> r = await async_vfs.read("/notes.md")
>>> r.success
True
>>> r.content
"# Notes\n..."
>>> len(r.mounts)
1
>>> r.mount.mount    # convenience accessor for the single-mount case
"/"
```

The `mounts` list has exactly one entry. The convenience
accessors (`r.content`, `r.file`, `r.paths`) work identically
to today.

### 9.2 Single-mount failure

```python
>>> r = await async_vfs.read("/missing.md")
>>> r
VFSResult(
    function="read",
    mounts=[MountResult(
        mount="/",
        success=False,
        message="not found: /missing.md",
        candidates=[],
    )],
)
>>> r.success
False
>>> r.message
"not found: /missing.md"

# Sync facade — defaults raise_on_error=True
>>> sync_vfs.read("/missing.md")
Traceback (most recent call last):
  ...
vfs.exceptions.NotFoundError: not found: /missing.md
>>> # The exception's .result is the VFSResult above.
```

### 9.3 Multi-mount fan-out, partial failure (async returns, sync raises)

v1 is strict: any mount failure flips `success=False` on the
async surface and raises on the sync surface. The async caller
still gets the candidates from the healthy mounts attached to
the result; the sync caller catches the exception and reads
`exc.result.mounts` for the same breakdown.

```python
>>> async_vfs = VFSClientAsync()       # raise_on_error=False
>>> await async_vfs.add_mount("/postgres", PostgresFileSystem(...))
>>> await async_vfs.add_mount("/mssql",    MSSQLFileSystem(...))
>>> await async_vfs.add_mount("/broken",   PostgresFileSystem(bad_url))

>>> r = await async_vfs.glob("**/*.md")

>>> r.success
False                                  # any mount failed → success=False
>>> [m.mount for m in r.mounts]
["/postgres", "/mssql", "/broken"]

>>> r.mounts[0]
MountResult(mount="/postgres", success=True,  message="",
            candidates=[<42 rows>])
>>> r.mounts[2]
MountResult(mount="/broken",   success=False,
            message="connection refused", candidates=[])

>>> len(r.candidates)                  # flattened — healthy mounts still landed
59

>>> r.message                          # one line per failed mount
"(mount=/broken) connection refused"

>>> print(r)                           # to_str — agent surface
ERROR (mount=/broken): connection refused

/mssql/architecture.md
/postgres/notes/a.md
/postgres/notes/b.md
... (59 paths total — flattened, no mount partition visible)
```

Same op against the sync client raises:

```python
>>> sync_vfs = VFSClient(...)          # raise_on_error=True
>>> sync_vfs.add_mount("/postgres", PostgresFileSystem(...))
>>> sync_vfs.add_mount("/mssql",    MSSQLFileSystem(...))
>>> sync_vfs.add_mount("/broken",   PostgresFileSystem(bad_url))

>>> sync_vfs.glob("**/*.md")
Traceback (most recent call last):
  ...
vfs.exceptions.UnavailableError: (mount=/broken) connection refused

>>> # exc.result preserves the full per-mount breakdown for the developer:
>>> try:
...     sync_vfs.glob("**/*.md")
... except UnavailableError as e:
...     for m in e.result.mounts:
...         print(m.mount, m.success, len(m.candidates), m.message)
/postgres True 42 ""
/mssql    True 17 ""
/broken   False 0 connection refused
```

### 9.4 Multi-mount fan-out, total failure

```python
>>> sync_vfs = VFSClient()             # raise_on_error=True
>>> sync_vfs.add_mount("/broken1", PostgresFileSystem(bad_url_1))
>>> sync_vfs.add_mount("/broken2", PostgresFileSystem(bad_url_2))

>>> sync_vfs.glob("**/*.md")           # both mounts fail
Traceback (most recent call last):
  ...
vfs.exceptions.UnavailableError: (mount=/broken1) connection refused
(mount=/broken2) connection refused

>>> # to_str on the async client renders the same error block, no body:
>>> r = await async_vfs.glob("**/*.md")
>>> print(r)
ERROR (mount=/broken1): connection refused
ERROR (mount=/broken2): connection refused
```

### 9.5 Construction at a call site

```python
# Today:
return self._error(f"Not found: {path}")

# After this story:
return self._error(VFSErrorKind.NotFound, f"not found: {path}")

# More context, same call shape:
return self._error(
    VFSErrorKind.WrongKind,
    f"not a directory: {path}",
)
```

The kind is supplied; the message is prose. Both flow through
the same single helper. No `_classify_error` step.

### 9.6 The CLI / `Unrecognized` path

```python
>>> await async_vfs.cli("grup notes")
"ERROR (unrecognized): grup — did you mean 'grep'?"

>>> r = await async_vfs.run_query("grup notes")
>>> r.mounts[0]
MountResult(mount="/", success=False,
            message="unknown command: grup — did you mean 'grep'?",
            candidates=[])

>>> sync_vfs.run_query("grup notes")
Traceback (most recent call last):
  ...
vfs.exceptions.UnrecognizedError: unknown command: grup — did you mean 'grep'?
```

Today this raises bare `ValueError` out of `parse_query`. After
this story it goes through the structured envelope.

---

## 10. Migration map

Every `_error(...)` and `_WriteAbort(...)` site converts
mechanically. The kind comes from this table; the message stays
prose.

| Today's prose | New kind |
|---|---|
| `Not found: {p}` | `NotFound` |
| `No mount found for path: {p}` | `NotFound` |
| `Source not found: {p}` | `NotFound` |
| `Chunk parent file not found: {owner} (for {p})` | `NotFound` |
| `Already exists (overwrite=False): {p}` | `Exists` |
| `Destination path occupied: {p}` | `Exists` |
| `Not a directory: {p}` | `WrongKind` |
| `Ancestor path exists as {kind}, not directory: {p}` | `WrongKind` |
| `Cannot write to {kind} path: {p}` | `WrongKind` |
| `Not empty (use cascade=True): {p}` | `NotEmpty` |
| `Cannot write to read-only path '{p}' …` | `PermissionDenied` |
| `Cannot write to root path` / `Cannot delete root path` | `Invalid` |
| `<op> requires a path or candidates` / `…, not both` | `Invalid` |
| `<op> requires X or Y` (call-shape) | `Invalid` |
| `<op> requires at least one …` | `Invalid` |
| `Duplicate path in write batch: {p}` | `Invalid` |
| `Invalid glob pattern: {pat}` | `Invalid` |
| `Invalid regex pattern: {pat}` | `Invalid` |
| `max_depth must be >= 1, got {n}` | `Invalid` |
| `lexical_search: no searchable terms in query` | `Invalid` |
| Vector size mismatch | `Invalid` |
| `<op> sources must resolve to the same mount` | `CrossMount` |
| `<op> destinations must resolve to the same mount` | `CrossMount` |
| `Cross-mount edges not supported: {a} and {b}` | `CrossMount` |
| `if_revision` mismatch (planned) | `Conflict` |
| `No content to edit: {p}` | `Conflict` |
| `semantic_search requires an embedding provider` | `Unsupported` |
| `semantic_search requires a vector store` | `Unsupported` |
| `vector_search requires a vector store` | `Unsupported` |
| `Embedding provider failed: {exc}` | `Unavailable` |
| `Auto-chunk failed for {p}: {exc}` | `Unavailable` |
| `Index maintenance failed: {exc}` | `Unavailable` |
| `Write failed for {p}: {exc}` | `Unavailable` |
| `Delete failed for {p}: {exc}` | `Unavailable` |
| (CLI parse failure, currently bare `ValueError`) | `Unrecognized` |
| (long-op deadline, planned) | `Timeout` |
| (caller-initiated cancel, planned) | `Cancelled` |

---

## 11. Renderer changes — `to_str` is the agent surface

`to_str` renders for the **agent**, not the developer. The agent
sees one filesystem; the mount partition is a developer/debugger
concern that lives in `to_json` and on `exc.result.mounts`. The
renderer therefore never shows a `mounts:` block on success and
preserves the namespace illusion on the success path.

### 11.1 The rule

**Default = Unix-shaped per function. Tables = only when the
caller projects metadata fields.** This is the existing
`_render_body` contract (`results.py:521`); the only thing this
story changes is what the *error block* looks like on multi-mount
failure. The success body inherits the existing dispatcher
unchanged.

| Function | Default render | Unix analog | Becomes a table when… |
|---|---|---|---|
| `read` (1 file) | raw content | `cat` | non-`content` projection (rare) |
| `read` (N files) | `==> /path <==` headers | `head -v` | non-`content` projection |
| `glob` / `ls` | one path per line | `find` / `ls -1` | projection includes a non-path field |
| `tree` | `├── / └──` ASCII tree | `tree(1)` | never |
| `grep` | `path:N:text` (match), `path-N-text` (context) | `grep -n` | projection includes a non-line-level field |
| `stat` | block: header + indented `  field: value` | `stat(1)` | never |
| `write`/`delete`/`edit`/`mkdir`/`mkedge`/`move`/`copy` | one-liner: `Wrote /path` / `Wrote N paths` | (Unix-style) | never |
| ranked search / centrality | Markdown table (score is always projected) | (no Unix analog) | always |

Future renderers added under §11 must follow the same rule:
**Unix-shaped by default, tabular only on request**. Reviewers
can reject any new renderer that defaults to Markdown tables for
a function with a Unix peer.

### 11.2 Three cases

The full rule has three cases. The only difference between
total failure and partial success is whether the success body
renders below the error block.

#### Full success (every mount succeeded)

Render the candidates flattened, exactly as today's single-mount
renderer would — no mount header, no partition visible. The
namespace illusion is total. The agent cannot tell whether one
mount or five mounts answered.

```
# Notes
...
```

(For a single-file `read`, the file contents.) For `glob`/`ls`,
the path listing. For `grep`, the `grep -n`-style line output.

#### Failure error block

One `ERROR:` line per failed mount, in the Unix `<tool>:
<source>: <message>` shape that `ls`, `grep`, `gcc` use on
stderr. Single-mount failures omit the source segment since
there is nothing to disambiguate.

**Single-mount failure:**

```
ERROR: not found: /missing.md
```

**Multi-mount, one failed:**

```
ERROR: /broken: connection refused
```

**Multi-mount, several failed:**

```
ERROR: /broken1: connection refused
ERROR: /broken2: connection timed out
```

The mount appears as the first colon-delimited segment after
`ERROR:`, exactly the slot where Unix tools put the source
(`ls: /nonexistent: No such file or directory`,
`grep: /nonexistent: No such file or directory`).

#### Total failure vs. partial success

The error block above is identical in both cases. **The only
difference is whether successful candidates render below it.**

**Total failure** — error block, nothing else:

```
ERROR: /broken1: connection refused
ERROR: /broken2: connection timed out
```

**Partial success** — error block, then the successful
candidates flattened as if everything succeeded (the same
function-specific Unix-shaped render from §11.1):

```
ERROR: /broken: connection refused

<normal candidate render of result.candidates from healthy mounts>
```

The mount label appears *only* on error lines — never in the
success body. A partial-success `glob` looks like:

```
ERROR: /broken: connection refused

/mssql/architecture.md
/postgres/notes/a.md
/postgres/notes/b.md
...
```

A partial-success `grep` looks like:

```
ERROR: /broken: connection refused

/mssql/architecture.md:17:authentication is handled by ...
/postgres/notes/a.md:42:def parse(query): ...
```

A partial-success multi-file `read` looks like:

```
ERROR: /broken: connection refused

==> /mssql/architecture.md <==
...content...

==> /postgres/notes/a.md <==
...content...
```

Each defers to its function-specific renderer for the body.

### 11.3 `to_json` is unchanged in spirit

`to_json` emits the full `VFSResult` structure including the
`mounts: [...]` partition. JSON consumers (FSP wire, MCP
debugger, structured tooling) get the breakdown; the prose
renderer doesn't. Two surfaces, two audiences.

---

## 12. Scope

### 12.1 In

1. Constitutional amendment to Article 2: replace the
   five-class taxonomy and the single-envelope `VFSResult` with
   the per-mount partition plus the 13-kind internal enum.
2. `MountResult` model.
3. `VFSResult.mounts: list[MountResult]`. Drop `errors:
   list[str]`. Add convenience accessors (`success`, `candidates`,
   `message`, `mount`, `file`, `content`, `paths`).
4. `MountResult.add_prefix(prefix)` mirroring the existing
   pattern.
5. `VFSResult` set algebra defers per-mount; `function` flips to
   `"hybrid"` on mismatch.
6. `VFSErrorKind` enum (13 values, internal only).
7. Per-kind exception subclasses (`NotFoundError`, …,
   `VFSTimeout`, `VFSCancelled`).
8. `_error(kind, message)` signature; kind stashed for the raise
   rule.
9. Routers (`_route_fanout`, `_route_glob_fanout`,
   `_route_grep_fanout`, `_merge_results`) build per-mount
   results.
10. `VFSClient.__init__(..., raise_on_error: bool = True)` and
    `VFSClientAsync.__init__(..., raise_on_error: bool = False)`.
11. `@boundary` decorator and `_return_or_raise(result)` hook
    method. The decorator is applied explicitly to every public
    method that returns `VFSResult`. The hook raises whenever
    `raise_on_error` is set AND any mount in the result failed
    (strict v1 policy — no partial-success loophole).
12. CLI / `parse_query` wrapper that turns parser exceptions
    into `MountResult(success=False, message="unknown command:
    …")` records.
13. Conversion of all 67 `_error(...)` and `_WriteAbort(...)`
    sites per §10.
14. Renderer rewrite per §11.
15. Deletion of `_classify_error`.

### 12.2 Out

- FSP / JSON-RPC wire framing (FSP wave 2's job).
- Capability advertisement (`capabilities()` hook). The
  `Unsupported` kind exists today for the configurable case;
  pure "not implemented" lands in a separate story.
- Trace IDs / observability fields on errors.
- `RateLimited` kind. Folds into `Unavailable`.
- Per-operation raise policy (read-style ops tolerating
  partial failure). v1 is strict for every op.
- Bind-cycle detection (story 016).

---

## 13. Acceptance criteria

1. `VFSResult.mounts: list[MountResult]` is the canonical
   structure. `errors: list[str]` is gone.
2. `MountResult(mount, success, message, candidates)` is the
   per-mount primitive. No `kind`, no `detail`, no `errors`.
3. `MountResult.add_prefix(prefix)` rewrites both the `mount`
   field and every candidate's `path`.
4. Convenience accessors on `VFSResult` (`success`, `candidates`,
   `message`, `mount`, `file`, `content`, `paths`, `__bool__`,
   `__len__`, `__contains__`) work identically to today's
   single-envelope behavior in the single-mount case.
5. `VFSErrorKind` has the 13 values listed in §2.2.
6. One exception subclass per kind. `_EXCEPTION_FOR_KIND` maps
   one to one.
7. Zero `self._error("…")` (string-literal, no kind) in
   `src/vfs/`.
8. `_classify_error` is deleted. No prose-classification path
   remains.
9. `VFSClient` defaults `raise_on_error=True`. `VFSClientAsync`
   defaults `raise_on_error=False`. Both accept the constructor
   override.
10. The raise rule fires whenever `raise_on_error` is set AND
    `result.mounts` is non-empty AND any mount returned
    `success=False`. v1 is strict; partial failure raises.
11. A multi-mount glob across one healthy and one broken mount:
    on the async client returns a `VFSResult` with two
    `MountResult` entries, the healthy mount's candidates
    present in `result.candidates`, `result.success=False`, and
    `result.message` listing only the failed mount
    (`"(mount=/broken) connection refused"`). On the sync
    client, the same call raises the typed exception with the
    same message; `exc.result` preserves both `MountResult`
    entries.
12. A multi-mount glob across two broken mounts raises
    `UnavailableError` from the sync client; the exception's
    `.result.mounts` lists both broken entries.
13. `vfs.cli("grup foo")` returns a `VFSResult` with
    `MountResult(success=False, message="unknown command: grup
    …")` and does not raise on the async client; raises
    `UnrecognizedError` on the sync client.
14. Set algebra (`&`, `|`, `-`) on `VFSResult` defers
    per-mount; `function` flips to `"hybrid"` on mismatch.
15. **`to_str` never reveals the mount partition on success.**
    A multi-mount full-success `glob` renders byte-identically
    to a single-mount `glob` over the same flattened candidates.
    A multi-mount partial-success `glob` renders one
    `ERROR (mount=...)` line per failed mount, then the
    flattened successful candidates as if everything succeeded.
    A multi-mount total-failure renders only the error block,
    no body.
16. **`to_json` always includes the full `mounts: [...]`
    partition.** Two surfaces, two audiences: prose for the
    agent, structured shape for the JSON consumer.
17. Per-kind boundary tests cover the four most-confusable
    pairs: `NotFound` vs `WrongKind`, `Exists` vs `Conflict`,
    `Unsupported` vs `Unrecognized`, `Unavailable` vs `Timeout`.
18. Existing tests in `tests/test_vfs_client.py` are updated to
    assert classification via the typed exception subclass, not
    via string matching.

---

## 14. Risks

- **`VFSResult` shape change is a public-contract change.**
  `errors: list[str]` is gone; `mounts` is new. Mitigation:
  `result.message` and `result.success` keep working via
  properties; the single-mount case is structurally identical
  through the convenience accessors; pre-1.0 project; small
  ecosystem.
- **Sync vs. async raise default asymmetry.** A developer
  importing `VFSClient` (sync) gets surprise raises; importing
  `VFSClientAsync` doesn't. This is by design — the two have
  different audiences — but it is a real footgun for someone
  who switches between them. Mitigation: document at the top
  of both classes' docstrings; mention in the README's "which
  client should I use?" section; the constructor flag lets
  either side flip.
- **Conversion of 67 sites is mechanical but bulky.** Mitigation:
  the migration table in §10 has a row per site; convert by
  module batch with the test suite green between batches.
- **Constitutional amendment is the largest in this project's
  history.** Mitigation: every kind is named in at least three
  of POSIX, Plan 9, gRPC, MCP/JSON-RPC; the partition by mount
  has WebDAV 207 and Elasticsearch `_shards` precedent.
- **`_classify_error` deletion in one change.** Mitigation:
  pre-1.0; no external dependents; the shim's public surface
  was always private.
- **Per-mount result for single-mount ops adds one wrapping
  level.** Mitigation: convenience accessors (`r.content`,
  `r.file`, `r.mount`) keep ergonomics identical; only callers
  who explicitly want the partition pay any new cost.

---

## 15. References

### Codebase

- `src/vfs/exceptions.py:46` — `_classify_error` (deleted by
  this story)
- `src/vfs/results.py:268` — `VFSResult.errors: list[str]`
  (replaced by `mounts`)
- `src/vfs/results.py:403` — existing `add_prefix` pattern
  (extended to `MountResult`)
- `src/vfs/base.py:1093` — `_error()` constructor (signature
  changes)
- `src/vfs/base.py` (router methods) — multi-mount fan-out
  builds `MountResult` per terminal
- `src/vfs/permissions.py:298–301` — `Cannot write …` sites →
  `PermissionDenied`
- `src/vfs/backends/database.py:1424` — `_write_impl`'s
  `_WriteAbort` catch
- Story 016 — `MountError` / `MountErrorKind` (consumed here)
- Story 025 — `_WriteAbort` orchestrator (extended here)

### Project context

- Constitution Article 2 (this story amends both the closed
  taxonomy and the result shape)
- `context/learnings/2026-04-18-posix-and-related-standards.md`
  (prior POSIX-vs-VFS analysis; this story consciously updates
  its "five-class hierarchy is enough" claim)
- `context/learnings/2026-04-18-swe-agent-aci-principles.md`
  (guardrail principle on error self-description)
- `project_fsp_vfs_synthesis.md` (`error.data.class` commitment)

### External precedent

- POSIX `<errno.h>` (IEEE 1003.1-2024) —
  `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/sys/errno.h`
- Plan 9 kernel error strings —
  `/Users/claygendron/Git/Repos/plan9/sys/src/9/port/error.h`
- gRPC status codes — `https://grpc.io/docs/guides/status-codes/`
  (17 codes; closest peer to `VFSErrorKind`)
- JSON-RPC 2.0 specification —
  `https://www.jsonrpc.org/specification#error_object`
- MCP draft schema —
  `/Users/claygendron/Git/Repos/modelcontextprotocol/schema/draft/schema.ts`
  (lines 224–345; SEP-1303 for input-validation as
  tool-execution-error)
- WebDAV (RFC 4918) `207 Multi-Status` — direct precedent for
  partition-by-source on a single response envelope
- Elasticsearch `_shards: {total, successful, failed,
  failures}` — same posture, modern reference
