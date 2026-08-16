# 100 — Gram-planner upgrades: shrink the refusal set

- **Status: draft 2026-08-14** — the recorded successor story of
  ADR 033 (planner upgrades deferred at 093's shaping fork 3,
  resolved by Clay 2026-08-05: "all three deferred to a follow-up
  story once the refusal gate has live users"). No code yet; §6's
  cap fork is the one owner decision, pointered in
  `../../open-questions.md`.
- **Date:** 2026-08-14
- **Owner:** Clay Gendron
- **Kind:** planner capability extension — three upgrades to
  `build_code_gram_query` that widen the indexable pattern set. The
  refusal gate's law, the ladder, the budgets, and the verifier are
  untouched.
- **Depends on:** ADR 033 (the refusal gate and the folded-planning
  law this spec widens; its consequences section names this story),
  ADR 036 (entry-grain extraction — the doc-id grain the planner's
  output intersects over), spec 093 (the landed planner).
- **Relates to:** the resolved open-questions entry "Gram-planner
  upgrades: in 093 or a follow-up story?";
  `../../research/2026-07-13-database-storage-grep-index.md`
  (codesearch `RegexpQuery` / zoekt prior art already studied for
  093).

## Intent

The refusal gate refuses any pattern whose plan is `GramAny` unless
`allow_scan=True`. Today the planner gives up on three pattern shapes
that field tools index routinely, so common ripgrep idioms refuse
while equivalent spellings index — an asymmetry users hit immediately:

1. **Character classes flush the run.** `[fF]oo` refuses while
   `(?i)foo` indexes — perverse under folded planning, where `[fF]`
   collapses to the single folded byte `f` and the expansion often
   costs nothing.
2. **Only top-level alternation branches.** `^(import|from)` and
   `foo_(bar|baz)` plan `GramAny` because a non-top-level `BRANCH`
   conservatively flushes; pg_trgm and zoekt answer these from the
   index in milliseconds.
3. **Anchors split literal runs.** `AT` nodes (`^`, `$`, `\b`, `\A`,
   `\Z`) are zero-width — they consume no bytes, so the literals on
   either side are byte-adjacent in any actual match — yet the
   collector flushes on them, discarding cross-anchor grams and, via
   `_pure_literal_text`, demoting groups that contain one.

Every upgrade only ever *widens* the indexable set and *narrows*
candidate sets; the soundness law is unchanged and absolute — the
plan is a necessary fact, never an authority; weaker predicates are
always acceptable, unsoundness never. Planning stays folded-only.
Every pattern the planner still refuses remains answerable under
`allow_scan=True`, exactly as today.

## Shape

- **§1 Bounded char-class expansion.** An `IN` node whose members
  enumerate — literal members and small ranges, after folding — below
  a declared member cap splices into the surrounding run as a
  cross-product of run variants; the variant set compiles to an OR of
  per-variant gram conjunctions (the existing `GramOr` algebra).
  Negated classes, category escapes (`\w`, `\d`), and over-cap
  classes keep today's flush — degrade, never refuse. Folding runs
  per variant through the one shared fold, so `[fF]` and `[İi]`
  collapse before grams are cut.
- **§2 Alternation cross-products.** A `BRANCH` at any depth compiles
  each branch to its own sub-query and combines with the surrounding
  literal context under a declared arm cap, generalizing the existing
  top-level split. The existing collapse law extends unchanged: any
  unconstrained branch collapses its OR to `GramAny`, and an over-cap
  product degrades to the flush the collector does today.
- **§3 Anchor-tolerant extraction.** `AT` nodes become
  adjacency-transparent in both `_collect_runs` and
  `_pure_literal_text`: a zero-width assertion contributes no bytes
  and severs no adjacency. Soundness argument to record in the
  docstring: if a match exists, the literals flanking a zero-width
  node are byte-adjacent in it; a pattern the assertion makes
  unsatisfiable (`foo\bbar`) has no matches to lose, so requiring the
  joined grams is vacuously sound.
- **§4 Interactions.** The upgrades compose (a class inside a nested
  branch inside an anchored group); the caps must bound the *product*
  of expansions, not each in isolation — one shared arm-count
  ceiling on the final query width, in the spirit of
  `MAX_PATTERN_ARMS`. Wide-alternation fetch cost stays governed by
  the runtime budgets (ADR 033 — per-branch rarest-gram exemption,
  wall-clock between branches); this spec adds no new runtime knob.

## Research task (bounded, before slice B)

One dated memo extending the 2026-07-13 study with the specific
numbers this spec needs: codesearch's `RegexpQuery` expansion limits
and zoekt's `regexpToQuery` caps (where they clamp class/alternation
products and what they degrade to), plus a measured refusal-set delta
— run the planner over a corpus of field patterns (ripgrep issue
corpus, the differential battery's pattern set, the query-ladder
patterns) before and after, so the upgrade's value and the cap's bite
are numbers, not vibes.

## Verification obligations

- The grep differential battery re-runs green (ADR 033 names it the
  permanent harness whenever the planner changes) and gains a planner
  edition: rows for each newly indexable class — folded class
  collapse, nested alternation, anchored groups — checked against
  `grep -E`/`rg -uu` across the four worlds.
- The query-ladder benchmark re-runs; newly indexable patterns joins
  its ladder so the index-vs-scan delta is recorded.
- A soundness property row per upgrade: on a seeded world, index-side
  results equal the same call under `allow_scan=True` ground truth
  (candidates may only widen, results must not change).
- Mutation checks on the caps: raising the member cap past the
  declared constant and dropping the over-cap collapse must each fail
  a pinned row.
- Refusal-gate contract rows stay green: a still-unindexable pattern
  refuses with the same `unindexable_pattern` message naming
  `allow_scan=True`.

## Touch points

- `src/vfs/models/code_grams.py` — the planner (`_collect_runs`,
  `_pure_literal_text`, `_query_from_ast`, new expansion helpers, the
  declared caps).
- `tests/models/test_code_grams.py` — planner rows, cap mutants, the
  folded-collapse pins.
- `context/research/studies/2026-08-05-grep-differential-battery/`,
  `.../2026-08-05-grep-query-ladder-benchmark/` — the planner
  edition and the re-run records.
- Nothing in `grep.py`, the gate, the ladder, or the budgets moves.

## Slices

- **A** — research memo (prior-art caps + refusal-delta measurement);
  resolves §6 with Clay.
- **B** — char-class expansion (§1), the declared caps, planner rows.
- **C** — alternation cross-products (§2) and composition (§4).
- **D** — anchor transparency (§3); battery planner edition +
  query-ladder re-run; true-up of ADR 033's deferred list.

## Open questions

- **§6 [NEEDS CLARIFICATION] The caps** (pointered in
  `../../open-questions.md`): one shared final-width ceiling vs
  per-upgrade caps (class member cap × branch arm cap), and the
  numbers — slice A's memo brings the prior-art values and the
  measured deltas; Clay picks.
