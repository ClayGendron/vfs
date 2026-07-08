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

7. [ ] `base2.py` `_error`: op required, `severity` param, no
   `success=`.
8. [ ] `base2.py` `_backend_unsupported`: `path=ROOT` entry anchoring;
   state the funnel rebase-seam invariant once (covers the
   TransportError arm; delete the pun comment).
9. [ ] `base2.py` merges: `Result.merge` at grouped/two-path/
   entry-batch sites; `Result.merge_branches` at `_route_fanout` +
   `_tree_entry` only; bind-path decoration rule stated in the
   docstring (replaces the false disjointness claim).
10. [ ] `base2.py` fan-out: info-severity `vfs.unsupported` entry per
    capability skip; re-apply `max_count`/`limit` post-merge.
11. [ ] `base2.py` consumers: `_probe_bind_site` dispatches on
    `kind_family` (not_found → mkdir advice, unavailable.* → transport
    failure); `add_mount`/`remove_mount` raise `MountError` carrying
    the `ResultError` list.
12. [ ] `backends/memory.py`: delete every `success=` construction;
    fast-follow if cheap — per-entry mutation failure enumeration,
    `status="deleted"` on delete rows.
13. [ ] `render.py`/`projection.py`: dispatch on `.op` (None → generic;
    'hybrid' branch dies; graph-method function names retire — 067
    seed); delete the transitional `.function` alias; one-line error
    rendering (severity, locus, message, hint, retry directive),
    grouped errors → warnings → info; rollup counts.
14. [ ] `exceptions.py`: `exception_for_kind` consults `kind_family`
    for partial degradation of unknown child kinds; `raise_if_failed`
    raises for fatal entries only (warnings/info never become
    exceptions — pressure-test finding).
15. [ ] Tests rework: `success=` constructions, 'hybrid'/'' and old
    kind-string assertions; new acceptance-criteria tests (demotion
    both arms, scoped no-demotion, probe kinds, max_count post-merge,
    MountError, field pass-through across a hop).
16. [ ] Ripples: 056 spec notes (decision 12 kind value re-parented;
    decision 7 docstring superseded); retire `repro.py` once its ten
    assertions are covered by the suites.
17. [ ] End of session: `uv run pytest tests/`, `uv run ruff check`,
    `uv run ty check` on touched files.
