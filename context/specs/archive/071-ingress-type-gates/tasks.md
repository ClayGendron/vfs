# 071 — Tasks

Ordered; every task leaves the suite green.

- [x] 1. `ops.py`: add `GRAPH_METHODS`; retire `TRAVERSAL_FUNCTIONS`
      everywhere — one name for the vocabulary.
- [x] 2. `src/vfs/params.py`: `ParamSpec`, `ShapeRule`, `PARAMS`,
      `RULES`, `param_violation`.
- [x] 3. `base.py`: `_gate_params` in the gates section; wire all 16
      public verbs.
- [x] 4. `base.py` removals: tree `max_depth`, fan-out not-both +
      `row_cap`, single-shape exclusivity, mkedge `edge_type`, graph
      method check + `TRAVERSAL_FUNCTIONS` import, `_route_pairs`
      matrix, write matrix, edit matrix (asserts where ty needs
      narrowing).
- [x] 5. `tests/test_params.py`: drift test, garbage matrix with zero
      dispatch, precedence pins (beats closed, beats busy), positive
      controls.
- [x] 6. Session end: `uv run pytest tests/ -q`, `ruff`, `ty`; update
      spec status; note re-pins actually needed in plan.
