# 036 — Router Verb Surface (all sixteen ops on `VirtualFileSystem`)

- **Status:** draft
- **Date:** 2026-07-03
- **Owner:** Clay Gendron
- **Kind:** feature (router layer only)
- **Depends on:** 035 (op vocabulary in `vfs.ops`), the base2 router core
  (mount routing, capabilities gate, `_route_single`,
  `_dispatch_grouped_observations`)
- **Enables:** the `DatabaseFileSystem` port (backends implement
  `_{op}_impl` against a settled dispatch contract), the `cli` meta-verb
  story (parses into these verbs), MCP tool exposure

## Intent

Build the twelve missing public verb routers on `vfs.base2.VirtualFileSystem`
so every op in `ops.ALL_OPS` routes: **write, edit, delete, mkdir, mkedge,
move, copy, tree, glob, grep, glean, graph** join the existing read, stat,
ls, run. Routers only — the pure router still has no storage, and no
`_{op}_impl` is implemented here. Every verb resolves terminals, applies
the capability and permission gates, dispatches (to `self` through
`_call_local_impl`, to a child mount through its public method), and
rebases results. Backend semantics stay behind the seam.

On completion, the 035 drift test tightens from subset to **equality**:
the router's public verb surface *is* `ALL_OPS`.

## Why

The op vocabulary (035) names sixteen verbs; the router answers four. The
`DatabaseFileSystem` port cannot start until each `_{op}_impl` has a
router above it that owns routing, gating, and rebasing — otherwise those
concerns leak into the backend and get reimplemented per storage class,
which is the exact disease the old `base.py` had (routing, permission
checks, and impl logic interleaved across 1,865 lines).

## Router shapes

Five dispatch shapes cover all sixteen verbs. The old `base.py` proved
each shape out; this story ports the shapes onto the base2 chokepoints.

| shape | verbs | routing rule |
|---|---|---|
| **single** (exists) | read, stat, ls, tree, run, write, edit, delete, mkdir | one path (or an observation batch) → longest-prefix terminal via `_route_single` |
| **two-path** (new) | move, copy | src and dest each resolve; same terminal → one dispatch; different terminals → `cross_mount` error |
| **endpoint-pair** (new) | mkedge | source and target each resolve; same terminal → write the canonical `edges/out` path there; different terminals → `cross_mount` error (cross-server edges are story 021) |
| **fan-out** (new) | glob, grep, glean | no path scope → dispatch to self-storage **and every mount** in parallel, rebase and `_merge_results`; an explicit path scope routes to that terminal only |
| **grouped** (new) | graph | path → longest-prefix terminal; observations → group by terminal (the existing `_dispatch_grouped_observations` machinery), **each mount runs the algorithm on its own subgraph** over its own group; results rebase and merge |

There is no cross-mount traversal: a walk never follows an edge out of
its mount's graph, by construction (each terminal only sees its own
subgraph). Cross-server edges remain story 021.

## Decided semantics

- **Kwargs pass through verbatim.** Routers validate *routing* inputs
  (paths, observations, the src/dest pair) and pass op kwargs
  (`overwrite`, `permanent`, `cascade`, `max_depth`, patterns, ...)
  unmodified to `_call_local_impl` / the child's public method. Impl
  semantics are the backend story's contract; the router neither
  interprets nor defaults them beyond the signature.
- **Signatures follow the old `base.py` quarry** (`base.py:1148`–`1545`)
  with three deliberate changes:
  1. `candidates: Result` inputs become `observations: list[Observation]`
     (the base2 convention already used by read/stat/ls).
  2. The four search methods (`semantic_search`, `vector_search`,
     `lexical_search`, + bm25) collapse into **`glean(query, *,
     limit=10, ...)` — a Google-style search: text in, one fused ranked
     list out.** There is no method selector; the caller (an LLM) never
     picks a retrieval strategy. Backends index chunks by vector,
     lexical/BM25, and graph-centrality signals and fuse the rankings
     (reciprocal rank fusion in the reference implementation) — all of
     it backend-tunable and invisible in the public signature. The
     router passes `query` and `limit` through opaquely.
  3. The traversal methods collapse into
     `graph(method, path=None, observations=None, ...)` — one public
     verb, one capability. **Centrality is dropped entirely** (recent
     scope change): `graph`'s method vocabulary is exactly
     `projection.TRAVERSAL_FUNCTIONS` (predecessors, successors,
     ancestors, descendants, neighborhood, meeting_subgraph,
     min_meeting_subgraph) — the one set serves dispatch validation and
     rendering, per the 035 rule that `ops.py` grows no method table. An
     unknown method rejects with `kind=invalid` before any dispatch.
- **Result `function`:** `graph` results report the specific traversal
  name (`"descendants"`, ...) — the envelope's `function` identifies how
  rows were produced, and the traversal vocabulary is registered in
  `vfs.projection`. `glean` results report `"glean"`: fusion means there
  is no single producing method to name, and the sub-signal mix is
  deliberately opaque to the caller.
- **Permission gating for two-path ops:** `move` requires *both* src and
  dest writable (a move deletes its source); `copy` requires dest only.
  `mkedge` checks writability of the canonical edge path. All checks run
  before any dispatch — a two-path op never half-executes on a gate
  rejection.
- **Mutation path resolution:** every `MUTATING_OPS` verb resolves its
  target(s) with `resolve_path(mutation=True)` — root, `/.vfs` grammar
  violations, and inverse-edge targets reject with `kind=invalid` before
  routing (this is existing `_route_single` behavior extended to the new
  verbs; `copy`'s *source* resolves with `mutation=False`).
- **Fan-out skips incapable terminals silently.** A terminal whose
  `capabilities()` lacks the op contributes no rows and no error — this
  is the no-probe rule's purpose (an MCP tool catalog that cannot grep
  should not fail every namespace-wide grep). A fan-out with an explicit
  path scope routed to a single incapable terminal still errors
  `unsupported`, matching single-shape behavior.
- **Storageless root behavior matches read today:** a verb whose path
  resolves to a storageless `self` with no matching mount returns
  `not_found`; fan-out over zero capable terminals returns an empty
  success.
- **Batch write routes by entry path.** `write(entries=[...])` groups
  `models2.Entry` values by terminal (the entry-path analogue of
  `_dispatch_grouped_observations`), rebases each group with
  `Entry.without_mount`, gates each entry's path, dispatches groups in
  parallel, and merges. Single write stays `write(path, content=..., ...)`.
- **Supporting value types get new homes:** `EditOperation` (frozen
  old/new/replace_all triple) lives in `vfs.replace` beside the engine
  that consumes it; `TwoPathOperation` (frozen src/dest pair) lives in
  `vfs.base2` — it is a router-owned shape. Neither imports from the old
  stack.
- **`edit` is a multi-edit verb by contract.** `edits=[EditOperation, ...]`
  is the native input — applied *sequentially* (each edit sees the content
  left by the previous one) and *atomically* (if any edit fails to match,
  none apply; the file is never left half-edited). The
  `edit(path, old=..., new=...)` form is sugar wrapping a one-item list.
  Sequencing/atomicity are impl-layer guarantees the backend story must
  honor; the router only shapes the input.
- **Cross-mount glean merges as-is in v1.** Fan-out unions each
  terminal's fused rows; per-backend scores are only roughly comparable
  across mounts, and re-fusing ranks at the router is a recorded
  road-not-taken for now (`.top(k)` on the merged result is the caller's
  cut). Revisit alongside story 022 (hybrid search across mounts).

## Scope

### In

1. The twelve router methods on `VirtualFileSystem`, per the shape table.
2. The two new dispatch chokepoints: `_route_two_path` (move/copy, used
   by mkedge's endpoint variant) and `_route_fanout` (glob/grep/glean),
   plus the batch-entry write router.
3. `TwoPathOperation` in base2; `EditOperation` in `vfs.replace`.
4. Tightening `tests/test_ops.py::test_router_public_verbs_are_registered_ops`
   to equality: public coroutines minus the management allowlist
   (`add_mount`, `remove_mount`, `close`) **==** `ALL_OPS`. (The `cli`
   story will add `cli` to the allowlist when it lands.)
5. Router-level tests in `tests/test_base.py` using `SpyFS`-style fakes —
   including the gate coverage deferred from 035 (`mkdir` now write-gated;
   `rm` not a method at all).
6. Pruning dead vocabulary from `vfs.projection` — it reads as a
   promise. `CENTRALITY_FUNCTIONS` goes (centrality is out of the
   product scope), and `RANKED_SEARCH_FUNCTIONS` goes with it: no verb
   produces `vector_search`/`semantic_search`/`lexical_search`/`bm25`
   envelopes anymore, so `glean` becomes a plain `_DEFAULT_PROJECTION`
   entry (`("path", "score")`). `KNOWN_FUNCTIONS` shrinks by those
   eleven names; the `in_degree`/`out_degree` Observation fields stay
   (traversal results may still report degrees). Swap the stale
   `pagerank` example in `ops.py`'s docstring for a traversal name.
   Ripple: `tests/test_projection.py`, `tests/test_render.py`, and
   `tests/test_results.py` use `vector_search`/`bm25` as fixture
   function names — retarget those fixtures to `glean` (they exercise
   ranked-arrangement rendering and score-sort chains, which `glean`
   now represents).
7. The `permissions.py` module docstring update deferred from 035 — its
   chokepoint list becomes true again in this story; rewrite it to name
   the base2 chokepoints.

### Out

- **No `_{op}_impl` implementations** — the pure router errors through
  `_call_local_impl` exactly as it does for read today. Backend behavior
  (overwrite semantics, cascade, chunking, version bumps, search
  execution) is the `DatabaseFileSystem` story.
- **No cross-mount move/copy emulation.** `cross_mount` is the answer;
  read-then-write emulation in the router is a recorded road-not-taken
  (it would make the router hold content and invent partial-failure
  semantics).
- **No `cli`** — separate story porting `vfs/query/` onto the new verbs.
- **No cross-server graph scope** (021), **no union mounts** (019), **no
  changes to `vfs/query/`, `render.py`, or the old stack**.
- **No MCP wiring** — capability sets stay as `capabilities()` returns.

## Acceptance criteria

1. Every name in `ops.ALL_OPS` is a public async method on
   `VirtualFileSystem`; the tightened equality drift test passes; no
   public coroutine exists outside `ALL_OPS` ∪ {add_mount, remove_mount,
   close}.
2. Parametrized over all seven `MUTATING_OPS`: dispatch against a
   read-only mount returns `kind=read_only` with no impl call recorded
   by the spy; against a writable mount the spy records exactly one
   rebased dispatch.
3. Parametrized over all seven `MUTATING_OPS`: root and reserved-`/.vfs`
   targets return `kind=invalid` before any dispatch; a direct
   inverse-edge (`edges/in`) write target is rejected.
4. `move`/`copy`: same-terminal pair dispatches once with both rel paths;
   split-terminal pair returns `kind=cross_mount` with no dispatch;
   `move` with read-only src (writable dest) and read-only dest (writable
   src) both reject; `copy` with read-only src and writable dest
   succeeds in routing.
5. `mkedge`: writes the canonical `edges/out` path on the shared
   terminal; split endpoints return `kind=cross_mount`; the inverse `in`
   projection is never a write target.
6. Fan-out: `glob`/`grep`/`glean` with no scope reach self-storage plus
   every mounted spy in parallel with correctly rebased results merged
   left-to-right in mount-table order; an incapable terminal is skipped
   with no error row; an explicit scope reaches only its terminal; a
   scoped call to an incapable terminal returns `kind=unsupported`.
7. `graph`: a path input routes to exactly one terminal; an observations
   input spanning two mounts dispatches one grouped call per terminal
   (each spy sees only its own rebased group) with results merged; a
   centrality or unknown method name returns `kind=invalid` with no
   dispatch; the returned envelope's `function` is the specific
   traversal name; `glean` results report `function="glean"`.
8. `projection.KNOWN_FUNCTIONS` contains no centrality or per-method
   search names; `CENTRALITY_FUNCTIONS` and `RANKED_SEARCH_FUNCTIONS`
   no longer exist; `default_projection("glean") == ("path", "score")`
   still holds; traversal names keep their `("path", "kind")` default
   projection.
9. `write(entries=...)` spanning two mounts groups, gates, rebases, and
   merges per criterion 2's rules, entry paths localized per terminal.
10. Full live suite passes with zero xfail/skip markers; `ruff` and `ty`
    pass on all touched files (`ty` at parity or better — the two
    pre-existing diagnostics in base2/exceptions are not made worse).
11. `permissions.py`'s docstring names the real base2 chokepoints.

## Post-implementation hardening

A five-agent adversarial audit of the landed router (authorization,
routing, async/merge, vocabulary, input-fuzzing) confirmed the gate
coverage and the rename, and surfaced five defects — all fixed in the
same story with regression tests. Recorded here because each is a
standing contract the `DatabaseFileSystem` port must not regress.

1. **Gate ordering — capability check must precede dispatch
   (`_dispatch_grouped_observations`).** The `check_writable` loop ran
   before dispatch, but `_capability_error` sat *inside* the
   `asyncio.gather`-fanned `_run_group`. An observation-batch mutation
   (`delete`/`edit`) spanning a capable and a capability-limited terminal
   dispatched to the capable one while reporting overall failure —
   partial mutation, and inconsistent with every other chokepoint. Fix:
   hoist the capability check into the same pre-dispatch loop
   (capability then permission), so a batch touching any incapable or
   read-only terminal is rejected whole with nothing dispatched.
   **Contract:** every chokepoint resolves paths, checks capability, and
   checks permission for *all* targets before dispatching *any*.

2. **Error fan-in must not collapse distinct-mount failures
   (`Result._combined_errors`).** The `|` fold dropped right-side errors
   equal to a left-side error — correct for diamond chains
   (`(a | b) & b`, the *same* object down both arms) but wrong on the
   merge path, where two mounts failing identically (e.g. `unavailable`
   with `path=None`) are two real failures. Fix: dedup by object
   identity (`id()`), not equality — diamonds still collapse, distinct
   mounts are both reported. **Contract:** a caller counting errors sees
   one per downed terminal.

3. **Cross-terminal atomicity stops at validation — say so.**
   `asyncio.gather` does not cancel siblings when one dispatch *raises*,
   so a `move`/`copy`/entry-batch spanning terminals can apply one side
   and still surface the raise. The router cannot make this atomic; true
   all-or-nothing across terminals is a backend/transaction concern.
   Fix: the `_route_two_path` (and sibling) docstrings now state that
   the all-or-nothing guarantee covers the *validation* phase only.
   **Contract:** the backend story owns cross-terminal transactionality;
   the router guarantees only that gates are all-or-nothing.

4. **The router never raises on bad input — values in, `Result` out.**
   Several public verbs leaked raw exceptions instead of an `invalid`
   result: `_route_single`'s exactly-one-of-path/observations guard
   (`raise ValueError` → reachable by `write()`/`delete()`/`graph(m)`
   with no target); `TwoPathOperation(*item)` splatting malformed
   `moves`/`copies` items (bad arity, a stray `str`) into `TypeError`;
   and `.path` dereferences on non-`Entry`/`Observation` batch elements
   and a non-`str` `mkedge` `edge_type` into `AttributeError`. Fix: the
   guard returns `invalid`; `_coerce_two_path` validates each pair;
   batch loops `isinstance`-check their elements; `mkedge` type-checks
   `edge_type`. **Contract:** every public verb returns a `Result` for
   any argument shape; only genuine programming misuse (never reachable
   from typed calls) may raise.

5. **Mutually-exclusive inputs are rejected, not silently preferred.**
   `write(entries=, path=/content=)`, `edit(old/new=, edits=)`,
   `move`/`copy(src/dest=, batch=)`, and fan-out
   `glob`/`grep`/`glean(paths=, observations=)` previously let one input
   silently win and dropped the other. Fix: supplying both forms returns
   `invalid`. **Contract:** the router never silently discards caller
   intent.

Acceptance for the hardening: regression tests in `tests/test_base.py`
cover each of 1–5 (capable-terminal-not-dispatched, two-equal-errors
preserved while the diamond still dedups, malformed-pair/non-Entry/
non-Observation/non-str-edge_type → `invalid`, and every
both-inputs-given → `invalid`); `base2.py` and `results2.py` reach 100%
line coverage; suite green with zero xfail/skip.
