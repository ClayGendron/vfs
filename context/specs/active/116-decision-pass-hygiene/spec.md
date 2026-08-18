# 116 — Decision-pass hygiene: five verified-but-inert trues

- **Drafted 2026-08-18.** Born from the remediation-landing review's
  decision pass
  (`../../../research/2026-08-18-remediation-landing-review.md`,
  "Decision pass" section) — the five design questions Clay routed to
  a single hygiene landing: run-1 questions 1, 3, 5, 8, and the
  record half of 6. Every item was verified accurate-but-inert by the
  review; nothing here changes behavior on any engine.
- **Date:** 2026-08-18
- **Owner:** Clay Gendron
- **Kind:** hygiene — naming, one docstring law, one docstring
  disclosure, and one test decoupled from a private attribute. The
  bench ladders and full suite are the no-regression referee.
- **Depends on:** specs 107–111 (the arc whose review surfaced these);
  spec 115 (the sibling hygiene landing — disjoint seams, same files).
- **Relates to:** the decision pass's other dispositions (Q2's
  status-quo ratification is *recorded* here as the `ContentMatcher`
  law; the cadence unification stays parked with its byte-cap
  trigger; the counting-convention reconciliation stays with the
  mining pass).

## Intent

Five small drifts, each confirmed real and each confirmed harmless
today; the point of landing them together is to stop paying attention
to them:

1. **The channel fan budget is derived independently at two sites**
   (`storage/backends/database/grep.py` — the `allow_list_ids`
   `statement_budget=` argument and the `_pushdown_terms` `within_fan`
   check, both computing
   `arm_budget(profile, parameter_budget, _CHANNEL_ARM_BINDS)`).
   Result-neutral, but `arm_budget`'s third argument is a per-arm
   *bind* cost while the pruning consumer caps a *statement count* —
   the two share a number, not a unit — and `pathterms.py`, which
   spends the figure, cannot trace where it came from.
2. **The row-gate ride vocabulary is a repeated literal.** Grep spells
   `ride_along = {"size_bytes", "ext", "name"}` at two fetcher sites;
   glob spells `frozenset({"name", "ext"})` at one. The `name`/`ext`
   pair is the row-fact gate's input vocabulary — it belongs beside
   `passes_row_filters`, named once. A forgotten ride fails loud (a
   `KeyError`), not wrong; this is traceability, not a defect.
   Related: `reads.glob_rows` splats a positional three-tuple into
   `passes_row_filters`, where a parameter reorder would silently
   mis-gate; grep's `_passes_gates` destructures to named locals.
3. **`ContentMatcher` is silent on partial per-body results.** Each
   engine declares its own law at its implementation (the pure engine
   may leave a wall-expired body's partial count in place; the Rust
   engine is exact-or-absent), and the decision pass ratified the
   status quo — partiality is a result-level signal only. One
   Protocol sentence fixes that vocabulary so a third engine inherits
   it as contract.
4. **The rarest-first ordering pin reads SQLAlchemy's private
   `_where_criteria`** (`tests/storage/database/test_pathterms.py`).
   Stable through 2.1.0b3, but public `Select.whereclause` carries the
   same fact without coupling a test to a private attribute.
5. **The budgeted split path's linear pre-work is undisclosed.** The
   pure engine pays decode plus an eager line split (~2.4× transient
   residency, ~7% overrun at 512 MiB against the 10 s default) before
   its first deadline consult. The decision pass chose disclosure over
   engineering — a lazy line iterator alone would not close it
   (`_as_text` is a second linear pre-pass on both paths) — so the
   docstring names the pre-work window honestly.

Laws that bind the work:

1. **Behavior identical everywhere.** No query shape, budget figure,
   mask, or result may change on any engine; the full suite and the
   grep ladders referee.
2. **One name per fact.** The fan budget is computed once and passed;
   the ride vocabulary is declared once and shared. No new counting
   convention, no fifth spelling.
3. **Docstrings state law, not intention.** The `ContentMatcher`
   sentence must describe what both engines verifiably do today —
   exact rows except where the incomplete flag says otherwise — and
   the pre-work note must carry the measured magnitude, not a vague
   "some setup cost".

## Shape

- **§1 The fan budget.** Derive the channel fan figure at one site in
  `storage/backends/database/grep.py` and pass it to both consumers,
  under a name that states its unit at each seam (arms of fan, which
  the pruning loop spends one statement per). `pathterms.py`'s
  parameter docstring says where the figure comes from.
- **§2 The ride vocabulary.** One shared constant for the row-fact
  gate's input pair (`name`, `ext`), declared beside
  `passes_row_filters` in `pattern_matching/glob.py` (the function
  owns its input vocabulary); grep's two fetcher sites compose it
  with their own `size_bytes` pricing ride, glob's queried-mask site
  uses it directly. `glob_rows` passes the three row facts to
  `passes_row_filters` as named locals, matching grep's
  `_passes_gates`.
- **§3 The Protocol law.** One sentence on `ContentMatcher`: per-body
  results are exact, except that an engine may skip a body it did not
  reach or leave a partial count on the body the budget interrupted —
  the incomplete flag is the only partiality signal; no per-row
  marker exists.
- **§4 The public pin.** The `test_pathterms.py` ordering assertion
  reads `Select.whereclause` instead of `_where_criteria`, asserting
  the same anchor-first fact.
- **§5 The disclosure.** The pure-engine docstring that owns the
  budget story names the pre-deadline linear pre-work (decode + eager
  split, the measured ~2.4× residency and ~7% figure at the 512 MiB
  scale) beside the residual paragraph that already discloses the
  backtracking floor.
- **§6 The gate.** Full suite and coverage green; `ruff`/`ty`/format
  clean; both grep ladders byte-identical counts (the referee that §1
  changed no figure).

## Slices

- **A.** All of §1–§6 in one landing — the items are independent and
  individually tiny; splitting them would manufacture ceremony.

## Open questions

- None held here. The neighboring dispositions this spec does *not*
  own: cadence unification (parked, byte-cap trigger), the
  counting-convention narrative (mining pass), and the offload fork
  (research memo commissioned, `../../../open-questions.md`).
