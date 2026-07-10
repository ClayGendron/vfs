# 069 — Tasks

Ordered; every task leaves the suite green.

- [x] 1. `ResolvedTerminal.full` property; use it in `_tree_entry`.
- [x] 2. Add `_HopGrant` to the module type block; rework
      `_enter_hop` → `_HopGrant`, `_exit_hop(token: Token | None)`;
      rewire `_tree_entry` and `_route_fanout`.
- [x] 3. Add `_invalid_path(resolved, raw, op) -> Result` to the
      errors section (`ResolvedPath` under `TYPE_CHECKING`); convert
      the eight resolve-and-classify sites.
- [x] 4. Add `_FanoutPlan` to the type block; extract
      `_classify_fanout_scopes` (verbatim lift: early-return order,
      skip dedup).
- [x] 5. Add pure `_merge_fanout` staticmethod.
- [x] 6. Rework `_route_fanout` to validate → classify → dispatch →
      merge (≤ 45 body lines).
- [x] 7. Fold grouping into `_dispatch_grouped_observations`
      (terminal from resolved path); delete
      `_group_observations_by_terminal`.
- [x] 8. Layout: move `_coerce_two_path` + `_route_pairs` into the
      dispatch-shapes section.
- [x] 9. New tests in `tests/test_base_dispatch.py`: `_merge_fanout`
      (pinning, demotion, all-dead), `_classify_fanout_scopes`
      (sweep, region expansion, skip dedup, invalid refusal,
      scoped-incapable refusal, empty-on-refusal), hop grant
      (exhaustion, restore, `_exit_hop(None)`), two-path multi-fault
      precedence (`invalid` beats `busy`).
- [x] 10. Session end: `uv run pytest tests/ -q` (all green, none
      modified), `uv run ruff check src tests`,
      `uv run ty check src tests`, union-rule grep over base.py,
      fan-out line count.
