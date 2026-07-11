# 071 — Plan: ingress type gates

Implements the spec's nine decisions: one declarative table
(`src/vfs/params.py`), one checking helper on the router, gates invoked
at every public verb, inline ad-hoc checks removed.

## Approach

1. **Vocabulary first.** `ops.py` gains `GRAPH_METHODS` (the traversal
   vocabulary moves up from `results/projection.py`, which re-imports
   it — ops.py is the charter home beside `CaseMode`/`GrepOutputMode`;
   `params.py` must stay a leaf and cannot import projection, which
   imports models).
2. **`src/vfs/params.py`.** `ParamSpec` (name, kind, required, minimum,
   choices, default, doc) and `ShapeRule` (two groups; exactly-one or
   not-both; both/missing messages). `PARAMS`/`RULES` tables per op.
   `param_violation(op, params) -> str | None` — pure, stdlib+ops only;
   type checks run first, shape rules second (so garbage containers get
   the type message, and presence tests run on typed values). Model
   kinds (`observations`, `entries`, `edits`, `pairs`) are declared for
   drift/schema but validated downstream where their classes live.
   Presence for shape rules: `is not None`, except `str_seq` where an
   empty tuple/list is absent (matches fan-out's truthiness contract).
3. **Router wiring.** `_gate_params(op, **params) -> Result | None` in
   the gates section, minting via `_error` (`vfs.invalid`). Every
   public verb calls it before delegating — params-invalid now beats
   closed (Decision 5).
4. **Removals** (each replaced by a table entry): `_tree_region`'s
   `max_depth` gate; `_route_fanout`'s not-both and `row_cap` checks;
   `_route_single`'s path/observations exclusivity (the `assert path is
   not None` stays — gate-guaranteed); mkedge's `edge_type` isinstance;
   graph's inline `TRAVERSAL_FUNCTIONS` check (and base's import of
   it); `_route_pairs`' exclusivity/missing checks (its `_as_list` and
   per-item coercion stay — item validation lives downstream by
   design); write's entries-vs-path/content check; edit's both-forms
   and old/new-missing checks (the `EditOperation` item check stays in
   the verb).
5. **Tests** in `tests/test_params.py`: signature↔table drift test per
   op; a garbage matrix per verb family (wrong type, bounds, bogus
   enum, truthy-non-bool, str-where-container, bool-where-int) with
   recorder-verified zero dispatch; precedence pins (param beats
   closed, param beats busy); positive `run(arguments=dict)`
   passthrough.

## Deliberate behavior changes (re-pins)

- Bad param on a closed router: `invalid` (was closed-first).
- `case_mode`/`output_mode` garbage: `invalid` (was silent default).
- `max_depth=True` / `max_count=True` / `limit=True`: `invalid` (bool
  retrofit).
- `write(path=…)` without `content` (and vice versa): router `invalid`
  (was backend truth).
- `move(src="")`: presence is now `is not None` — an empty string
  resolves like every other path input instead of reporting
  missing-argument (consistency with `read("")`).
- Messages gain the op prefix (`"mkedge edge_type must be…"`); tests
  pin kinds, not prose, so no re-pins expected.

Outcome: none of these changes was pinned by an existing test — the
full pre-change suite (1225) passed unmodified; the 51 new tests pin
the new behavior.

Post-implementation verification (adversarial fuzz, 2070 calls across
all 16 verbs) found one hole: `None` bypassed every type check for
non-required params. Fixed with `ParamSpec.nullable` (default True,
False on the 19 params whose signatures are not None-able) plus six
matrix cases. The fuzz also confirmed: no reachable asserts from the
removed inline checks, the gate never copies or mutates values, and
`move(src="")` re-pins as path-semantics (`invalid`, root-mutation
message) per the presence-semantics note above.

## Risks and checks

- ty narrowing where inline checks guarded construction (`edit`'s
  old/new, `_route_pairs`' src/dest): replaced by asserts, the
  established gate-guaranteed pattern.
- Silent drift between verb signatures and the table: the drift test
  is the guard, both directions.
- Suite: `uv run pytest tests/ -q` green; `ruff`/`ty` clean.
