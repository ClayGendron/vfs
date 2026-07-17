# 046 — Decide the Storage Seam: Inherited `_*_impl` Flag vs. Composed Backend Protocol

- **Status:** decided 2026-07-04 — **composed `StorageBackend` protocol**,
  chosen on spike evidence (`spike_inherited.py` / `spike_composed.py`
  in this folder, both executed) and the design walkthrough recorded
  below. Deliverables landed 2026-07-05: ADR 001
  (`context/decisions/001-storage-backend-composition.md`) and the
  follow-up refactor story 049
  (`context/stories/049-storage-backend-protocol/`), which also
  executed the refactor. The spike files remain as the decision's
  evidence; `spike_inherited.py` demonstrates the *retired* shape and
  no longer runs against the refactored router — by design.
- **Date:** 2026-07-03 (opened) / 2026-07-04 (decided)
- **Owner:** Clay Gendron
- **Kind:** analysis + architecture decision (blocking-adjacent: decide
  before the database backend story starts)
- **Depends on:** 036 (the router surface either shape sits under), 037
  (single result channel — either shape returns `Result` through the same
  seam)
- **Enables:** the database backend port (which fossilizes whichever
  shape it is built against), honest `capabilities()` for storage
  backends

## Intent

`VirtualFileSystem` is currently two roles fused by a constructor flag:
a **router node** (mount table, verb surface, gates) and an **abstract
storage backend** (the `_{op}_impl` seam). The fusion points, at
`06cf551`:

- `storage: bool = False` (`base2.py:89`) — an identity claim the class
  makes about itself with a boolean.
- `_call_local_impl` reaching the impl by string:
  `getattr(self, f"_{op}_impl")` (`base2.py:447`) — the one seam `ty`
  cannot check. A backend that forgets one impl fails at *dispatch time*
  with `AttributeError` on the raw-exception channel — precisely the
  channel 037 reserved for bugs, which this makes true by definition,
  but late.
- Seven routability checks keyed on the flag (`fs is self and not
  self._storage` — `base2.py:493`, `:558`, `:622`, `:699`, `:788`,
  `:1186`, and the fan-out self-target at `:728`).
- `capabilities()` (`base2.py:405`) hand-declared, with nothing tying
  the declared set to the impls that actually exist.

The alternative is composition: storage is an *object the node holds*,
not a *thing the node is*.

```python
class StorageBackend(Protocol):
    async def read(self, *, path: Path, ...) -> Result: ...
    # one method per op family; transactions live inside the backend

VirtualFileSystem(storage=SqlStorage(engine))   # storage: StorageBackend | None
```

This was the last cheap moment to choose. The database backend is the
next fundamental; every `_read_impl`/`_write_impl` it lands is a vote
for the current shape, and re-deciding afterward means rewriting the
largest module in the new stack.

## The case for composing — why it won

Four arguments, in the order they carried weight:

1. **It is the last unchecked contract in a stack built on checked
   ones.** The refactor's through-line is replacing "both sides happen
   to agree" with enforcement: 035 pinned the op vocabulary with drift
   tests, 037 made `Result` the single classified channel, 040
   collapsed five gate sites into one, 045 pins the request schema.
   `getattr(self, f"_{op}_impl")` is a contract enforced by nothing but
   memory — and its failure mode (a raw `AttributeError` at dispatch)
   lands on the channel 037 promised would carry only *our* bugs. A
   forgotten method is not a router bug; surfacing it as one is a small
   lie in our own error taxonomy.
2. **VFS's futures are all partial backends, and `capabilities()`
   honesty is load-bearing.** The no-probe rule means agents *trust the
   declared set instead of poking* — but today the set is a hand-written
   frozenset with no connection to which impls exist. The roadmap is
   partial capability as the *normal* case: an in-memory backend without
   `glean`, MSSQL and Postgres differing on search, an MCP tool catalog
   doing only `ls`/`read`/`run`. With op-family protocols the honest
   answer is *computed* from what the storage object implements
   (`isinstance` against `runtime_checkable` families) — the default
   cannot drift from reality because it is derived from reality. A
   hand-declared override stays available for policy.
3. **Storage-as-object makes the node's mental model uniform with
   mounts.** A node already *holds* things it routes to — the mount
   table is a dict of composed objects reached through their public
   surface. Storage is the one terminal a node reaches by *being* it,
   via a boolean identity claim. After composition the picture is one
   sentence: a node is a router over things it holds — child mounts
   across edges, and optionally a storage object underneath.
   `storage: bool` becomes `self._storage is not None`; `close()` walks
   mounts and disposes its own backend symmetrically (today it has no
   notion of own storage to dispose).
4. **The 4,086-line database port is where the bill arrives either
   way.** Whichever shape is picked gets fossilized by that port.
   Composition's cost is a refactor of a 1,591-line router that is
   fresh and at 100% coverage — the safest possible moment to move a
   seam. Inheritance's cost is rewriting the largest module in the
   stack later.

## The case for the current shape — and its disposition

- **It exists, is documented, and is at 100% coverage.** True, and the
  strongest practical point — answered by timing: the coverage is
  exactly what makes the refactor safe *now*.
- **The session contract has an obvious home** ("open a transaction,
  pass the handle to each `_{op}_impl`" in an overridden
  `_call_local_impl`). Real, and the one place composition needs
  deliberate design — resolved by D5 below: the wrapper relocates
  inside the backend object, one method deep, with the same
  information hiding. The old `backends/database.py` already treats
  the session as backend-internal plumbing; this is relocation, not
  invention.
- **Subclass ergonomics** (`class MemoryFS(VirtualFileSystem)` with
  three `_*_impl` methods is a low floor). A class implementing a
  small protocol is barely a higher floor — and it removes a live
  footgun: a subclass sees every private method of a ~1,600-line
  router and can shadow one silently. `tests/test_base.py` has 18 such
  subclasses today, several overriding `_call_local_impl` itself under
  `# type: ignore[override]`.
- **Inheritance keeps `self` unified** where an impl needs node
  context. `user_id` already travels per-call, so user-scoping is
  unaffected; what remains is error-message branding (node name),
  which is small and is assigned to the follow-up story (see accepted
  costs).

## Spike evidence (executed 2026-07-04)

Both files are checked into this folder; the test plan's demand that
the central claim be demonstrated rather than asserted is met:

- `spike_inherited.py` — a `storage=True` subclass defining **no**
  impls passes `uv run ty check` clean; running it fails only at
  dispatch, as `AttributeError: 'ForgetfulFS' object has no attribute
  '_read_impl'` raised from `base2.py:696`.
- `spike_composed.py` — the same omission expressed against a
  `StorageBackend` protocol fails `ty` at the hand-off site:
  `invalid-argument-type … protocol member 'read' is not defined on
  type 'ForgetfulStorage'`. The same file shows
  `PostgresStorage(DatabaseStorage)` — a provider overriding one
  method — type-checking against the protocol unchanged, confirming
  D4 below.

## Decision — the composed shape, with these settled details

### D1 — protocol granularity: op families

`runtime_checkable` protocols per family, not 16 flat methods:
`SupportsRead` (`read`, `stat`, `ls`, `tree`), `SupportsSearch`
(`glob`, `grep`, `glean`), `SupportsMutation` (`write`, `edit`,
`delete`, `mkdir`, `move`, `copy`), `SupportsGraph` (`graph`,
`mkedge`), `SupportsRun` (`run`). `StorageBackend` — the constructor's
accepted type — is the read family as the minimum viable backend (the
mountability probe needs `stat`). A backend implements the families it
genuinely supports; `ty` checks each family it claims. The follow-up
story validates the family boundaries against the real database port.

### D2 — the router seam: an exhaustive match, not a relocated getattr

The router's chokepoints are generic (`_route_single` serves many ops
with `op` as a variable), so composition cannot be "call
`storage.read()` directly" — something must map the op variable to a
typed method. `_call_local_impl` becomes a `match op:` over the `Op`
literal ending in `assert_never(op)`: sixteen boring arms, each calling
a real protocol method, with family membership narrowed via
`isinstance` where the capability gate upstream already guarantees it.
The stringly seam does not move into the backend; it dies here, once,
in checked form. Two properties are bought: adding a verb to `ops.py`
fails `ty` until the funnel routes it (the drift test from the fallback
plan, as the type system, unskippable), and every arm's target must
exist on the protocol.

### D3 — capabilities are derived, with a policy override

The default `capabilities()` is computed from which families the
storage object satisfies (`isinstance` per D1's `runtime_checkable`
protocols); a node with no storage answers the spine-only set. A
hand-declared override remains legitimate for policy — advertising
less than the backend can do — but the default stops being able to
lie.

### D4 — provider inheritance lives inside the backend family

The valued `DatabaseFileSystem → PostgresFileSystem → MSSQLFileSystem`
structure is preserved as `DatabaseStorage → PostgresStorage →
MSSQLStorage`: per-provider overrides of individual methods (search,
graph) exactly as the old `backends/` tree does — `mssql.py` today
describes itself as overriding three search methods and inheriting the
rest. Only the class the hierarchy hangs off changes. The user-facing
names survive as thin wiring, which never touches the seam:

```python
class PostgresFileSystem(VirtualFileSystem):
    def __init__(self, engine: AsyncEngine, **kw: Any) -> None:
        super().__init__(storage=PostgresStorage(engine), **kw)
```

`VirtualFileSystem` keeps the entire public API and all
mounting/routing logic.

### D5 — transactions are backend-internal

Each backend opens/commits its own transaction inside its op methods
(`async with self._session_factory() as session, session.begin():` at
the top of `write`, etc. — or via a shared internal helper). The
router never sees a session; cross-op batch atomicity (038) lives
naturally in methods that receive the whole batch
(`write(entries=[...])`). The backend owns its engine and its
disposal; the router's `close()` walks mounts and its own storage
uniformly.

### Accepted costs (eyes open)

- **The 16-arm match is real verbosity** — a screen of boring code
  replacing one clever line. Boring-and-exhaustive beats
  clever-and-invisible, but it is not free.
- **Migration churn:** the seven flag checks, the constructor,
  `close()`, the 18 test subclasses, and the class docstring's seam
  doctrine all move in the follow-up story.
- **Backends lose ambient `self` context.** Error-message branding
  (node name) needs a standalone home — a small helper or a value
  passed at construction; the follow-up story's plan.md decides which.
  `user_id` already travels per-call; user-scoped rewriting stays
  backend-internal as before.
- **Cross-verb atomicity needs a deliberate door.** If a future story
  wants two-phase semantics *across* verbs, the protocol must grow one
  designed entry point — under inheritance that door was "override
  `_call_local_impl` harder", which is exactly the unchecked
  flexibility being retired.

## What "decided" means

1. **A decision record** in `context/decisions/` (ADR 001) stating the
   chosen shape, the rejected one's strongest argument (the session
   contract's obvious home), and citing the spike evidence above.
2. **A follow-up refactor story scoped *before* the database story:**
   protocol definition per D1, the `_call_local_impl` match funnel per
   D2, the `storage=` constructor migration, capability derivation per
   D3, the error-branding home, and the spy-fixture rewrite in
   `tests/test_base.py`.

## Out of scope

- Implementing the database backend — this story exists so that one
  starts on settled ground.
- The remote/MCP mount class — 034's children are reached through
  public methods, not the storage seam; this decision is invisible to
  them (worth a line in the decision record: the seam is *local-only*
  either way).
- Re-litigating the router's dispatch shapes or gates (036/040) — only
  the seam below `_call_local_impl` was in question.

## Test plan

Decision stories don't ship tests; the follow-up does. The record's
demand for executable evidence is satisfied by the two spike files in
this folder (see *Spike evidence*): `ty` catching the
deliberately-omitted op under the composed shape, and the equivalent
failure under the current shape arriving only at dispatch time.

## Open questions

None — the fork is resolved (see Status). Protocol granularity is op
families (D1), `user_scoped` path rewriting stays backend-internal
under the chosen shape, and the two details that surfaced during the
decision walkthrough — error-message branding and the cross-verb
atomicity door — are assigned to the follow-up story rather than left
open here.
