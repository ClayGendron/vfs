# 049 — The Composed Storage Seam: `StorageBackend` Protocol Under the Router

- **Status:** implemented 2026-07-05 — landing commit `218e88c`
- **Date:** 2026-07-05
- **Owner:** Clay Gendron
- **Kind:** refactor (executes ADR 001 / story 046's decision)
- **Depends on:** 046 (the decision this executes), 037 (`Result` as the
  single classified channel), 040 (the one terminal gate)
- **Enables:** the database backend port, honest `capabilities()` for
  partial backends

## Intent

Replace the inherited `_{op}_impl` seam in `vfs.base2` with the
composed `StorageBackend` protocol decided in story 046 (ADR 001),
before the database backend story fossilizes the old shape. After this
story, a node is one sentence: **a router over things it holds — child
mounts across edges, and optionally a storage object underneath.**

## Scope

### 1. `vfs/storage.py` — the protocol module (new)

- `runtime_checkable` protocols per op family (046 §D1, with two
  boundaries refined): `SupportsRead` (`read`, `stat`, `ls`, `tree`),
  `SupportsPatternSearch` (`glob`, `grep`), `SupportsGlean` (`glean`),
  `SupportsMutation` (exactly `MUTATING_OPS`: `write`, `edit`,
  `delete`, `mkdir`, `mkedge`, `move`, `copy`), `SupportsGraph`
  (`graph`), `SupportsRun` (`run`). Two refinements over 046's sketch,
  both the boundary validation 046 assigned here: the search split
  (a lexical scan needs no retrieval index — 046's own motivating
  case, an in-memory backend without `glean`, could not claim a fused
  search family honestly), and `mkedge` moving from the graph family
  into mutation (it writes the edge projection; the family boundary
  follows the write gate, making `SupportsMutation` equal
  `MUTATING_OPS` and `SupportsGraph` pure read-side traversal — so a
  SQL base backend can own a portable `mkedge` while dialects own
  traversal).
- `StorageBackend` — the constructor's accepted type — is the read
  family as the minimum viable backend (the mountability probe needs
  `stat`).
- `SupportsClose` — optional disposal: a backend that owns an engine
  exposes `async close()`; the router disposes it in its own `close()`.
- Method signatures mirror what the router's chokepoints already pass
  through `_call_local_impl` (keyword-only, gated `Path`s in, `Result`
  out). `ResolvedPair` moves here from `base2` — it is the impl-side
  pair shape and the protocol needs it without an import cycle.
- `storage_ops(obj) -> frozenset[Op]` — the derivation helper: which
  ops an object honestly answers, computed per family via `isinstance`.
- `CaseMode` / `GrepOutputMode` move from `base2` to `ops.py` (shared
  vocabulary; both `base2` and the protocols need them acyclically).

### 2. `vfs/base2.py` — the seam migration

- Constructor: `storage: StorageBackend | None = None` replaces
  `storage: bool = False`; a non-`None` backend missing the read family
  raises `TypeError` at construction (fail loud, even for untyped
  callers). Derived ops are computed once at construction.
- `_call_local_impl` becomes the exhaustive `match op:` funnel (046
  §D2): sixteen arms, each calling a real protocol method, family
  membership narrowed via `isinstance`, ending in `assert_never(op)`.
  A narrowing miss (possible only when a policy override advertises
  more than the backend implements) classifies `unsupported` — never a
  raw `AttributeError`.
- `capabilities()` default is **derived** (046 §D3): the spine reads
  (`ls`/`stat`/`tree` — every node answers them on `/`), plus the
  storage object's families, plus the union of every mount's set (so a
  parent consulting a subtree still routes into nested mounts; a child
  answering `None` keeps "no limit" contagious). A hand-declared
  override remains legitimate for policy.
- `_storage_answers(op)` checks the derived storage set directly —
  never the node's subtree set — intersected with any policy override.
- `_gate_terminal`'s capability step splits: for `fs is self` it asks
  `_storage_answers` (the terminal is the storage object); for a child
  it consults the child's `capabilities()` as today. Pinned order
  (routability → capability → permission) is unchanged.
- The remaining flag checks (`_is_path_mountable`, fan-out self-target)
  become `self._storage is None` / `_storage_answers`.
- `close()` walks mounts and then disposes its own backend when it
  satisfies `SupportsClose`, collecting failures into the same
  ExceptionGroup discipline. Repeated disposal is the backend's concern.
- Module and method docstrings that teach the seam doctrine are
  rewritten for composition.

### 3. `tests/test_base.py` — spy rewrite

Storage test doubles become backend objects (`RecorderStorage`,
`EchoStorage`, `CannedStorage`, `DictStorage`, gated/slow/failing write
variants), composed into thin node wrappers that keep the existing
class names and assertions. Overrides of `_call_local_impl` disappear —
that funnel is now router-internal. Node-level overrides that are
genuinely node policy (`_is_path_mountable`, `capabilities()`,
public-method spies) stay as subclasses. A new `tests/test_storage.py`
covers the derivation helper, including the drift guard: the family
map's union must equal the `Op` vocabulary.

## Settled details

- **Error branding:** backend errors brand with the backend's own
  identity (its class, its engine); a wiring class that wants node
  naming passes `name` into its backend at construction. No router
  threading — the router's own gate errors already carry router-side
  paths.
- **Transactions** stay backend-internal (046 §D5): sessions open and
  commit inside backend op methods; the router never sees one.
- **Cross-verb atomicity** stays out: if a future story wants it, the
  protocol grows one designed entry point. Not this story.

## Out of scope

- The database backend port (`DatabaseStorage` and providers) — next
  story, on this seam.
- Remote/MCP mount classes — reached through public methods; this seam
  is invisible to them.
- Router dispatch shapes and gates (036/040) beyond the capability-step
  split described above.

## Acceptance criteria

- A backend object missing a claimed family method is a `ty` error at
  the constructor hand-off (spike-equivalent, now enforced in the real
  seam).
- Adding an op to `ops.py` without routing it in the funnel fails
  `ty` (`assert_never`) — the drift test as the type system.
- Default `capabilities()` of a storage node equals what its backend
  implements (plus spine/mounts); it cannot drift from reality.
- `uv run pytest tests/` green; `ruff` and `ty` clean on
  `base2.py`, `storage.py`, `ops.py`, and the touched tests.
