# 038 — Branded Rebase Under a Hard 1024 Path Ceiling

- **Status:** implemented (commit 6e6f090, 2026-07-04)
- **Date:** 2026-07-03
- **Owner:** Clay Gendron
- **Kind:** fix (no-raise contract violation) + perf (rebase hot path)
- **Depends on:** 032 (unified path resolution chokepoint), 037 (single
  result channel — overflow rows ride the error list), 87ffdb9
  (idempotent resolve gate on branded input) — this story is its
  companion for the *derivation* fast paths
- **Enables:** large fan-out results (grep/glob/glean across mounts) at
  routing cost proportional to string concat, not gate revalidation

## Intent

`Path.with_mount` / `Path.without_mount` are the router's rebase
primitives — they run **per row, per boundary crossing** on every merged
result. Today both re-enter the full gate. Two consequences, both
verified (`repro.py` in this folder):

1. **Contract violation:** a rebase that pushes a valid child-local path
   past the 1024-char limit raises a raw `ValueError` out of a public
   verb, breaking "values in, Result out".
2. **Hot-path cost:** ~7–9 µs/row against 0.15 µs for a branded concat
   (~50×) — tens of milliseconds of pure routing overhead on a 10k-row
   grep merge.

**Decided policy: 1024 is a hard, namespace-wide invariant.** No `Path`
may exceed it — not at the ingress gate, not as the output of
`with_mount`/`without_mount`, not anywhere. The reason is
re-addressability: every path a `Result` returns must be valid input to
the next request. A rebased 1037-char path would be observable but
forever unreadable — the caller could list a row it can never `read`.
That asymmetry is worse than refusing the row outright, so the row is
refused *in a classified way*: an overflow at the rebase seam becomes a
`ResultError`, never a raised exception and never an over-long `Path`.

(The alternative — raising the ceiling to 4096 so deep-mount rows stay
addressable — was considered and **rejected**: it only moves the cliff,
and it weakens the one-number invariant every layer can rely on. 1024
stays the single truth, enforced everywhere.)

## Why — verified failures

Reproduced against `base2.py` at `54462cf` (`repro.py`; both cases
become tests in this story).

### Rebase overflow escapes the public API

A child mount legally holds a 955-char path (valid against the child's
own 1024 budget). Mounted under an 82-char prefix, the rebased global
path is 1037 chars. The child's rows come back, the router rebases, the
gate rejects:

```text
local row: 955 chars (valid); rebased: 1037 chars (> 1024)
RAISED through public glob: ValueError: Path too long (max 1024 characters)
```

The exception escapes `glob()` even with the no-raise contract in force.
The same failure is reachable through every fan-out and grouped verb.

### Rebase pays the full gate per row

```text
Path.with_mount (full gate): 7.03 us/row -> 70.3 ms per 10k-row merge
branded concat:              0.15 us/row (47x)
```

Commit 87ffdb9 made *re-gating a branded path* free, but `with_mount`
builds a **raw str** (`posixpath.join`) and re-enters the full gate every
time, so the router's per-row rebase never benefits.

## Design

### D1 — 1024 everywhere: the invariant, named and documented

```python
# vfs/paths.py — module constants
MAX_PATH_LENGTH = 1024     # hard namespace-wide invariant — see Path docstring
MAX_SEGMENT_LENGTH = 255
```

`validate_path` / `validate_relative_path` use the named constants
(behavior unchanged). The `Path` class docstring gains the invariant's
statement — this is the documentation the policy demands:

```python
class Path(str):
    """A path that has passed the gate: canonical, validated, safe to route.

    ...

    **Length is a hard invariant, not an ingress rule.** No ``Path`` ever
    exceeds ``MAX_PATH_LENGTH`` (1024) — including the outputs of
    ``with_mount`` / ``without_mount`` / ``joinpath``. This guarantees
    every path a ``Result`` returns is valid input to the next request
    (re-addressability). A rebase that would exceed the limit raises
    ``ValueError`` at the ``Path`` layer; the router's rebase seam
    (``Result.with_mount``) converts that per row into a classified
    ``ResultError`` — an over-long global path can therefore never be
    observed, raised, or stored anywhere in the system.

    Consequence for deep mounts: a child-local path is only reachable
    through a parent if ``len(mount_prefix) + len(local_path) <= 1024``.
    Content written *through* the parent always satisfies this (the
    ingress gate bounds the global path); content written directly to a
    child that is also mounted deeper elsewhere may not — such rows
    surface as ``invalid`` errors on the parent's results rather than as
    rows.
    """
```

### D2 — `with_mount` brands by proof, guards length explicitly

Two canonical absolute paths concatenate to a canonical absolute path:
the mount is not `/` (so it has no trailing slash) and the local path
starts with `/` — no empty, `.`, `..`, or whitespace-padded segment can
appear that wasn't already rejected in the parts, and character/segment
invariants are closed under concatenation. **Length is the one invariant
concatenation does not preserve**, so it is the one explicit check:

```python
def with_mount(self, mount: str) -> Path:
    """Re-root this mount-local path under *mount* (local → global).

    The outbound half of routing; inverse of :meth:`without_mount`.
    Both sides are canonical and canonical-absolute concatenation is
    canonical, so the result is branded directly — except length, the
    one invariant concatenation can break, which is checked explicitly.
    Raises ``ValueError`` on overflow; the router's rebase seam converts
    that into a classified per-row error (see ``Result.with_mount``).
    """
    mount = Path(mount)
    if mount == "/":
        return self
    if self == "/":
        return mount
    if len(mount) + len(self) > MAX_PATH_LENGTH:
        msg = (
            f"Rebased path too long (max {MAX_PATH_LENGTH}): "
            f"mount {mount!r} + local path of {len(self)} chars"
        )
        raise ValueError(msg)
    return Path._brand(mount + self)
```

### D3 — `without_mount` brands by proof (no length guard needed)

Stripping a prefix only shortens the path, so the inbound half cannot
overflow; the existing boundary check is the only guard:

```python
def without_mount(self, mount: str) -> Path:
    mount = Path(mount)
    if mount == "/":
        return self
    if self == mount:
        return Path._brand("/")
    if not self.startswith(mount + "/"):
        msg = f"Path {self!r} is not within mount {mount!r}"
        raise ValueError(msg)   # routing bug — raising here stays correct
    return Path._brand(self[len(mount):])
```

This runs in `_resolve_terminal` on **every** routed call and in every
grouped/entry rebase, so it is at least as hot as the outbound half.

(`Path._brand`'s docstring currently claims `resolve_path` is its only
caller — update it to name the rebase pair as the other proven sites.)

### D4 — the router's rebase seam classifies overflow instead of raising

`Result.with_mount` is the single seam every dispatch return crosses
(`r.with_mount(prefix)` at each chokepoint), so overflow handling lives
there once. A row whose rebased path would exceed the limit is **removed
from `observations` and reported in `errors`** — kind `invalid`, the
local path and mount prefix carried in `data` so a caller (or operator)
can still identify the row:

```python
# vfs/results2.py
def with_mount(self, mount: str) -> Result:
    """New result with every row and error path re-rooted under *mount*.

    The router's outbound rebase. A row whose global path would exceed
    ``MAX_PATH_LENGTH`` cannot exist as a ``Path`` (hard invariant), so
    it is converted to an ``invalid`` error carrying the local path and
    mount in ``data`` — the result reports the row exists but is not
    addressable through this mount. Pure — the original is untouched.
    """
    if not mount or mount == "/":
        return self
    observations: list[Observation] = []
    errors = [e.with_mount(mount) for e in self.errors]
    overflowed = False
    for o in self.observations:
        if len(mount) + len(o.path) > MAX_PATH_LENGTH:
            overflowed = True
            errors.append(ResultError(
                kind=VFSErrorKind.invalid,
                message=(
                    f"Path exceeds {MAX_PATH_LENGTH} chars when rebased under "
                    f"'{mount}' and cannot be addressed through this mount"
                ),
                data={"mount": str(mount), "local_path": str(o.path)},
            ))
            continue
        observations.append(o.with_mount(mount))
    return Result(
        function=self.function,
        observations=observations,
        success=self.success and not overflowed,
        errors=errors,
    )
```

Semantics follow the existing merge philosophy: the surviving rows are
kept, the failure is structured, and `success=False` because the result
is knowingly incomplete — identical to how a downed terminal reads after
`_merge_results`. An error whose own `path` would overflow rebases with
`path=None` (the message and `data` still locate it); `ResultError.with_mount`
gets the same guard.

`Observation.with_mount` / `Entry.with_mount` stay thin `Path` delegates
and may still raise — they are model-layer primitives; the *router seam*
is `Result.with_mount`, and it is the one place that must never raise.
Inbound (`Result.without_mount`) needs no change: stripping cannot
overflow.

### D5 — `joinpath` stays fully gated

`joinpath` / `__truediv__` accept arbitrary caller segments — no proof is
available, so they keep the full gate (which enforces the same 1024
ceiling). The fast path is *only* for the two rebase primitives whose
inputs are already branded. Same shape as 87ffdb9: prove once, brand at
the proven site, gate everywhere else.

## Non-goals

- No change to the ingress gate's semantics or limits — 1024/255 stay
  exactly as they are; they gain names (`MAX_PATH_LENGTH`,
  `MAX_SEGMENT_LENGTH`) only.
- No mount-time depth budgeting (rejecting a mount because a child *might*
  hold deep content) — content depth is dynamic; the per-row
  classification at the seam is the honest enforcement point.
- No relaxation for `RelativePath`.

## Test plan

1. **Overflow classification (replaces the repro's raise):** child with a
   >960-char local row mounted under a long prefix; `root.glob(...)`
   returns `success=False`, the overflow row is absent from
   `observations`, and an `invalid` error carries the mount and local
   path in `data`. Nothing raises. Sibling rows in the same result
   survive.
2. **Re-addressability invariant:** property-style sweep — every
   observation path in any returned `Result` satisfies
   `len(path) <= MAX_PATH_LENGTH` and round-trips through
   `resolve_path` as valid request input.
3. **Path-layer guard:** `Path.with_mount` raises `ValueError` naming
   both lengths when the concat would exceed 1024; `without_mount`
   never length-checks (prefix-strip cannot overflow).
4. **Brand-equivalence property test:** for a corpus of canonical paths
   × mount prefixes (including `/`, single-segment, nested, meta paths,
   and pairs summing to exactly 1024), `with_mount` under D2 equals the
   old gate-based result wherever the old one succeeded; likewise
   `without_mount`. Exactly-1024 passes; 1025 classifies.
5. **Inverse law:** `p.with_mount(m).without_mount(m) == p` and
   `q.without_mount(m).with_mount(m) == q` for `q` under `m` (within the
   length budget).
6. **Error-path rebase:** a `ResultError` whose `path` would overflow
   rebases to `path=None` with message/`data` intact.
7. **Microbenchmark note (not a CI gate):** record the before/after
   µs/row in the story's `results.md`.

## Open question

Whether `MAX_PATH_LENGTH` should be advertised through `capabilities()`
so an MCP peer can learn the ceiling instead of discovering it via
`invalid` errors. Deferred — belongs to the capabilities/handshake story.
