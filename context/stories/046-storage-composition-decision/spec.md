# 046 — Decide the Storage Seam: Inherited `_*_impl` Flag vs. Composed Backend Protocol

- **Status:** draft — this is a decision story; the deliverable is a
  signed decision record, not necessarily a refactor. Deliberately left
  open 2026-07-03: the owner wants further research before choosing, so
  the branch spike below is the next action, and the record waits on its
  evidence. The fork is this story's deliverable, not an open question
  to strip.
- **Date:** 2026-07-03
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
    # one method per op family; a transaction/session hook owned here

VirtualFileSystem(storage=SqlStorage(engine))   # storage: StorageBackend | None
```

This is the last cheap moment to choose. The database backend is the
next fundamental; every `_read_impl`/`_write_impl` it lands is a vote
for the current shape, and re-deciding afterward means rewriting the
largest module in the new stack. The deliverable here is a one-page
decision record in `context/decisions/` — either direction — so the
database story starts on settled ground.

## The case for composing

- **Missing impls become type errors.** A `StorageBackend`
  implementation missing a method fails `ty` at the definition site,
  today at dispatch time in production. This is the verifiable claim:
  the whole class of "backend forgot an op" bugs moves from runtime to
  the type checker.
- **`capabilities()` becomes derivable.** With op families as narrow
  protocols (`SupportsSearch`, `SupportsGraph`, …), a node's capability
  set can be *computed* from what its storage object implements —
  killing the declared-set-vs-real-impls drift that the no-probe rule
  currently trusts blindly. A hand-declared override stays possible for
  policy; the default stops lying.
- **The stringly seam disappears.** `getattr(self, f"_{op}_impl")`
  becomes a method call on a typed object; the router's last
  reflection-based dispatch goes away.
- **The two roles get separate lifecycles.** `close()` currently walks
  mounts but has no notion of *own* storage to dispose — a composed
  backend owns its engine and its disposal, and the router's close walks
  both uniformly. The `storage: bool` identity claim becomes simply
  "is the object there."
- **Testing gets lighter.** Today's suite builds `VirtualFileSystem`
  subclasses with spy `_call_local_impl` overrides; a spy that
  implements a two-method protocol is smaller and cannot accidentally
  override router behavior.

## The case for the current shape

- **It exists, is documented, and is at 100% coverage.** The
  one-seam design (`_call_local_impl` as "the only place a filesystem
  reaches its own impl") is a real discipline, clearly stated, tested.
- **The session contract has an obvious home.** "Open a transaction,
  pass the handle to each `_{op}_impl`" lives naturally in an overridden
  `_call_local_impl`. Composition must house it deliberately — likely a
  `run_in_op(op, **kwargs)` entry point on the protocol so the
  transaction wrapper stays backend-internal — designable, but it is
  the one place the composed shape is *less* obvious, and cross-op
  atomicity hooks (038's batch semantics, future two-phase work) live
  behind that same door.
- **Subclass ergonomics.** `class MemoryFS(VirtualFileSystem)` with
  three `_*_impl` methods is a genuinely low floor for contributors; a
  protocol + constructor wiring is a slightly higher one.
- **Inheritance keeps `self` unified** where an impl legitimately needs
  node context (the permission map for user-scoped rewriting, the node
  name for errors). Composition has to pass that context explicitly —
  arguably a feature (the dependency becomes visible), but it is churn.

## What "decided" means

1. **A decision record** in `context/decisions/` stating the chosen
   shape and the rejected one's strongest argument (both sides above,
   compressed), signed by the owner.
2. **If composed:** a follow-up refactor story scoped *before* the
   database story in sequence — protocol definition (granularity
   settled: **op families**, not 16 flat methods — search ops share
   filters, mutations share the transaction; the spike validates the
   family boundaries), the `storage=` constructor migration, capability
   derivation, and the spy-fixture rewrite in `tests/test_base.py`.
3. **If inherited:** the current shape is re-stated as chosen-not-
   inherited, plus the two cheap hardenings that survive either
   decision: a construction-time assertion that every op in
   `capabilities()` (or `ALL_OPS` for unlimited nodes with storage) has
   a resolvable `_{op}_impl` — moving the missing-impl failure from
   dispatch time to mount/construction time — and a drift test pinning
   impl-method names to `ALL_OPS` so a verb rename cannot strand an
   impl silently.

## Out of scope

- Implementing the database backend — this story exists so that one
  starts on settled ground.
- The remote/MCP mount class — 034's children are reached through
  public methods, not the storage seam; this decision is invisible to
  them (which is itself worth a line in the decision record: the seam
  is *local-only* either way).
- Re-litigating the router's dispatch shapes or gates (036/040) — only
  the seam below `_call_local_impl` is in question.

## Test plan

Decision stories don't ship tests; the follow-up does. But the record
must cite executable evidence either way — minimum: a branch spike
showing `ty` catching a deliberately-omitted op under the composed
shape, and the equivalent failure mode under the current shape (the
dispatch-time `AttributeError`), so the central claim is demonstrated
rather than asserted.

## Open questions

None beyond the fork itself, which is the story's deliverable (see
Status). The two details are settled either way: protocol granularity is
op families (folded into "What decided means" item 2), and `user_scoped`
path rewriting stays backend-internal under either shape — it reads that
way today ("inside the impl, after the permission check"), and keeping
it there avoids re-opening the user-scoping design.
