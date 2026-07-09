# 057 — Tasks

## Pass A — the envelope

1. [x] `results2.py` vocabulary: `Severity`; retry-class enum; the
   per-kind contract table (retry class, hint, `path_means`);
   `kind_family()`; `_KIND_ALIASES` tombstone for
   `vfs.backend_unavailable`.
2. [x] `results2.py` kinds: re-parent `backend_unavailable` →
   `"vfs.unavailable.backend"`; add `unaddressable`; docstring gains
   namespace partition, prefix-dispatch rule, producer-exclusivity
   rules, per-kind `path_means`.
3. [x] `ResultError`: `severity` + `source` fields; `extra='allow'`;
   always-copy `with_mount` with source stamping + append-once
   namespaced overflow record; `without_mount` strips both; derived
   `is_fatal` / `retry_class`; value-identity contract in docstring.
4. [x] `Result`: drop stored `success` (derived property, serialized
   outbound, stripped inbound); `ops` tuple + `.op` property + legacy
   `function` shim (spec decision 8 amendment); `extra='allow'`;
   value-equality `_combined_errors`; `merge` / `merge_branches`
   (zero-progress rule); `to_payload(max_errors=…)` rollup; lenient
   per-item `from_payload` with reconciliation + `strict=True`.
5. [x] `tests/test_result_laws.py`: L1–L5 algebra laws; retry-table
   totality; prefix degradation; alias resolution; unknown severity;
   quarantine both arms; reconciliation; source stamping across hops;
   overflow reconstruction; rollup invariance.
6. [x] End of session: law suite green; ruff/ty on `results2.py`.

## Pass B — threading and consumers

7. [x] `base2.py` `_error`: op required, `severity` param, no
   `success=`.
8. [x] `base2.py` `_backend_unsupported`: `path=ROOT` entry anchoring;
   state the funnel rebase-seam invariant once (covers the
   TransportError arm; delete the pun comment).
9. [x] `base2.py` merges: `Result.merge` at grouped/two-path/
   entry-batch sites; `Result.merge_branches` at `_route_fanout` +
   `_tree_entry` only; bind-path decoration rule stated in the
   docstring (replaces the false disjointness claim).
10. [x] `base2.py` fan-out: info-severity `vfs.unsupported` entry per
    capability skip; re-apply `max_count`/`limit` post-merge.
11. [x] `base2.py` consumers: `_probe_bind_site` dispatches on
    `kind_family` (not_found → mkdir advice, unavailable.* → transport
    failure); `add_mount`/`remove_mount` raise `MountError` carrying
    the `ResultError` list.
12. [x] `backends/memory.py`: delete every `success=` construction;
    fast-follow if cheap — per-entry mutation failure enumeration,
    `status="deleted"` on delete rows.
13. [x] `render.py`/`projection.py`: dispatch on `.op` (None → generic;
    'hybrid' branch dies; graph-method function names retire — 067
    seed); delete the transitional `.function` alias; one-line error
    rendering (severity, locus, message, hint, retry directive),
    grouped errors → warnings → info; rollup counts.
14. [x] `exceptions.py`: `exception_for_kind` consults `kind_family`
    for partial degradation of unknown child kinds; `raise_if_failed`
    raises for fatal entries only (warnings/info never become
    exceptions — pressure-test finding).
15. [x] Tests rework: `success=` constructions, 'hybrid'/'' and old
    kind-string assertions; new acceptance-criteria tests (demotion
    both arms, scoped no-demotion, probe kinds, max_count post-merge,
    MountError, field pass-through across a hop).
16. [x] Ripples: 056 spec notes (decision 12 kind value re-parented;
    decision 7 docstring superseded); retire `repro.py` once its ten
    assertions are covered by the suites.
17. [x] End of session: `uv run pytest tests/`, `uv run ruff check`,
    `uv run ty check` on touched files.

Pass B structural notes (2026-07-08):

- The inbound `function="x"` shim (task 4) was dropped later the same
  day (owner decision, spec decision 8 re-amendment): pre-deployment,
  no producer of the legacy key exists. The before-validator now only
  strips inbound `success` — decision 1's rule, not a shim.

- The kind vocabulary and contract tables moved to a new `vfs/kinds.py`
  (re-exported by `results2`): the renderer needs
  `KIND_CONTRACTS`/`kind_family` at runtime and `results2` imports
  `render`, so leaving them in `results2` would have forced a deferred
  import.
- `_route_fanout` splits the merge: entries the caller named merge
  plain (`Result.merge`); only unscoped branches pass through
  `merge_branches` — "scoped dispatch never demotes" holds even in
  mixed scoped+region calls, with branch progress judged within the
  unscoped set. A named entry subsumed by a sibling region dispatches
  once but its result is pinned out of the demotion pool (pressure-test
  finding, 2026-07-08).

Pressure-test run (2026-07-08, 56 agents, 13 confirmed findings, all
resolved same day): named-scope subsumption demotion; observation-shaped
dispatch bypassing the row cap; `max_count<=0` silently uncapping (now
`invalid`; memory glob also checked cap-before-append); `top()`
re-sorting scored glob rows (cap is now order-preserving for everything
but `glean`); peer newlines forging renderer error lines (one-line-ness
now enforced); directory-only write batches rendering "nothing to do"
(directories join the write summary); `bind()` racing `close()`
escaping a raw `KeyError` (closed-table re-check under the lock);
quarantine-clip test desync (bound now derives from the constant).
Every fix is pinned by a new test. Verified-solid under attack:
raise_if_failed/exception_for_kind/MountError, provenance rebase
through nested routers, wire round-trips of skips/demotions/rollups,
memory batch stage-and-commit atomicity, probe kind dispatch.
