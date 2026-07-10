# 069 — Plan: routing decomposition

Behavior-preserving refactor of `src/vfs/base.py` executing the spec's
decisions 1 and 3–8 (decision 2 resolved to no code change beyond its
mandatory precedence test). The proof of preservation is the existing
suite passing unmodified; every pinning test is black-box through the
public verbs, verified during the research review.

## Approach

Work bottom-up — types and helpers first, then rewire consumers, then
delete what was absorbed — so the file never holds two copies of a
rule. Each step leaves the suite green; steps are ordered so no step
depends on a later one.

1. **Types first.** `ResolvedTerminal.full` (property, decision 6),
   `_FanoutPlan` and `_HopGrant` (module-level private NamedTuples).
   The class body cannot interleave module types, so both live with
   the existing router types (`MountMeta`, `Binding`,
   `ResolvedTerminal`) at the top of the module — "beside its user"
   resolves to the type block, since the users are methods.
2. **`_invalid_path` (decision 1).** One total error-minter in the
   errors section, signature
   `(resolved: ResolvedPath, raw: str, op: Op) -> Result`
   (`ResolvedPath` imported under `TYPE_CHECKING`). Convert the eight
   resolve-and-classify sites; the two-line
   `resolve_path` / `is None` shape at each site is untouched, so
   `ty` narrowing is preserved.
3. **Hop budget (decision 5).** `_enter_hop` returns `_HopGrant`;
   `_exit_hop` accepts `Token | None` and no-ops on `None`. Rewire
   the two call sites (`_tree_entry`, `_route_fanout`), keeping their
   `try/finally` shape. This removes the file's one standing
   union-return violation.
4. **Fan-out decomposition (decisions 3–4).**
   `_classify_fanout_scopes` lifts the classification block verbatim
   — first-bad-path early return and `setdefault` skip dedup
   preserved — returning a `_FanoutPlan` whose `refusal` carries the
   early exits (empty collections on refusal; output-only per
   amendment A1). `_merge_fanout` is a pure staticmethod taking bind
   *paths*, not bindings, so it is testable with hand-built
   `Result`s. `_route_fanout` becomes the four-phase orchestration:
   validate → classify → dispatch → merge, target ≤ 45 body lines.
   The validation preamble keeps its exact order (row-cap check
   before the observations delegation — pinned by
   `test_non_positive_result_bound_is_invalid`).
5. **Resolve-once (decision 7).** `_dispatch_grouped_observations`
   folds grouping into its validation loop — terminal matched on the
   *resolved* path, the original observation rebased, gate-all-
   before-dispatch order unchanged — and
   `_group_observations_by_terminal` (single caller) is deleted.
6. **Layout (decision 8).** `_route_pairs` and `_coerce_two_path`
   move out of the public-mutations banner into the dispatch-shapes
   section (`_coerce_two_path` directly before `_route_pairs`, its
   only user — the class has no trailing internal-helpers banner, so
   beside-its-user governs).
7. **Tests.** New direct tests in `tests/test_base_dispatch.py`:
   `_merge_fanout` (pinning survives subsumption; demotion only for
   unpinned; all-dead stays loud), `_classify_fanout_scopes` (no-path
   sweep, region expansion, skip dedup, invalid-path refusal,
   scoped-incapable refusal — all with empty-collection invariant on
   refusal), `_HopGrant` (exhaustion refusal, token restore,
   `_exit_hop(None)` no-op), and the mandatory two-path multi-fault
   precedence test (bind-site src + invalid dest reports `invalid`).

## Trade-offs taken

- `_FanoutPlan`/`_HopGrant` at module level rather than nested: the
  layout rule's "beside its user" yields to Python's flat-class
  reality; the type block is the established home (`ResolvedTerminal`
  precedent).
- `_merge_fanout` takes `list[tuple[Path, Result]]` rather than
  zipping bindings internally: the pure signature is the point
  (amendment-free unit tests), and the call site already holds the
  zip.
- Decision 7 matches terminals on the resolved path where the old
  grouping helper matched on the raw observation path. For branded
  observation paths the two are identical; the resolved path is the
  more correct input and the change is unobservable in the suite.

## Risks and their checks

- **Error-precedence drift** in the reworked loops → the suite pins
  kinds per shape; the new precedence test pins the two-path order
  explicitly.
- **Skip records feeding demotion** → structurally prevented: skips
  live only on `_FanoutPlan.skips` and rejoin after `_merge_fanout`
  via `_with_skips`.
- **Union-rule regressions** → acceptance check greps base.py return
  annotations; the only sanctioned unions are `X | None`.

## Verification

`uv run pytest tests/ -q` unmodified-green, plus the new tests;
`uv run ruff check src tests`; `uv run ty check src tests`;
`_route_fanout` body line count ≤ 45.
