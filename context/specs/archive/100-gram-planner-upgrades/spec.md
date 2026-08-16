# 100 — Gram-planner upgrades: shrink the refusal set

- **Status: complete — all slices landed 2026-08-16** — the recorded
  successor story of ADR 033 (planner upgrades deferred at 093's
  shaping fork 3, resolved by Clay 2026-08-05: "all three deferred to
  a follow-up story once the refusal gate has live users"). Slice A's
  research memo landed 2026-08-16
  (`../../research/2026-08-16-gram-planner-expansion-caps.md`, with
  the rerunnable study under `research/studies/`); Clay resolved the
  §6 cap fork the same day (see §6); slices B–D landed together the
  same day as one planner rewrite (the three upgrades share the
  slice A prototype's fragment core), with the harness re-runs
  recorded in the two study docstrings. **Mined and archived
  2026-08-16** — decision set recorded as ADR 038
  (`../../decisions/038-gram-planner-expansion-upgrades.md`); the
  research memo, the two study run records, and the ADR 033 true-up
  were already downstream at landing. Nothing here governs current
  work.
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
   index in milliseconds. The reach is wider than grouped
   alternations: `sre_parse` factors common prefixes out of branches
   (`min|max` parses as `[LITERAL 'm', BRANCH('in'|'ax')]`), so even
   a *bare* alternation refuses today whenever its arms share a
   first character, while `alpha|beta` indexes — an asymmetry users
   cannot see (slice A memo §3).
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
  top-level split. **Group adjacency-transparency is a prerequisite,
  not a side effect**: `foo_(bar|baz)` only composes if the group
  passes adjacency through to its body, so §2 replaces the
  pure-literal-only splice with full transparency for `SUBPATTERN`
  (a group is its body's sequence; the slice A prototype ties the
  two together and validates the composed behavior). The existing
  collapse law extends unchanged: any unconstrained branch collapses
  its OR to `GramAny`, and an over-cap product degrades to the flush
  the collector does today.
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
  of expansions, not each in isolation. **Resolved by §6: two caps,
  both declared constants** — a post-fold class-member cap (8) that
  filters gramless category-range expansions before they bid for
  width, and one shared width ceiling (64, `MAX_PATTERN_ARMS`'s
  spirit and value) on the accumulated variant product, enforced at
  every cross step so intermediate state stays bounded (codesearch's
  clamp-after-every-combine discipline). Over-cap expansion degrades
  that node to today's flush — degrade, never refuse. Wide-alternation
  fetch cost stays governed by the runtime budgets (ADR 033 —
  per-branch rarest-gram exemption, wall-clock between branches);
  this spec adds no new runtime knob. One invariant the upgrades must
  preserve: the planner only claims grams that appear in the
  pattern's guaranteed literal text — it never manufactures
  wildcard-position grams to dodge a refusal (sub-3-byte patterns
  stay refused at every cap value).

## Research task (bounded, before slice B) — **done 2026-08-16**

Landed as `../../research/2026-08-16-gram-planner-expansion-caps.md`
with the rerunnable study (miner, prototype planner, measurement) in
`../../research/studies/2026-08-16-gram-planner-expansion-caps/`.
Headline numbers: codesearch clamps at `maxExact = 7` / `maxSet = 20`
/ class-cardinality 100, re-applied after every combine, with anchors
fully transparent; zoekt has no expansion caps because it never
expands (the do-nothing floor). Over a 231-pattern field corpus
(ripgrep tests/docs, linux/git/postgres/freebsd/sqlite/zoekt build
scripts, the ladder and battery sets): 61/216 parseable patterns
refuse today; all 13 rescues come from §2; §1/§3 narrow 15/155
already-indexable plans instead of rescuing; a single shared ceiling
is non-monotonic (W=128 rescues fewer than W=64 — gramless
digit-class forks starve the gram-bearing branch); a post-fold member
cap of 8 makes the sweep monotone, saturating at W=16 with widest
real demand 12.

## Verification obligations — **all discharged 2026-08-16**

Discharged by `tests/models/test_code_grams.py` (per-upgrade shape
rows, the pinned rows below, cap-mutant rows, a match-preserving
mutation fuzz), the battery planner edition (181 case-checks green),
and the ladder planner edition (rescued classes serve at 21–28 ms vs
272–318 ms scans). The cap mutants were executed: raising the member
cap to 16, raising the width ceiling to 128, and dropping the
over-cap collapse each fail a pinned row.

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
- Pinned rows from the slice A measurement (each guards a finding a
  future cap change could silently lose):
  - `min|max` plans indexable (the sre common-prefix factoring case —
    §2 must see the nested BRANCH);
  - `^(#|Using)` still refuses (a gramless arm collapses the OR — the
    collapse law survives the upgrades);
  - `' +[0-9]+\.[0-9]+% .* (Interpreter|jdk\.internal).*'` plans
    indexable at the declared caps (the junk-starvation pathology —
    this row is the monotonicity guard);
  - `[fF]oo` plans as a single-variant `GramAnd` containing the
    `foo` gram (post-fold member dedupe).

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

- **A** — **done 2026-08-16**: research memo (prior-art caps +
  refusal-delta measurement) landed; §6 resolved with Clay.
- **B** — **done 2026-08-16**: char-class expansion (§1), the declared
  caps (`MAX_CLASS_MEMBERS = 8`, `MAX_VARIANT_WIDTH = 64`, module
  constants beside `GRAM_SIZE`), planner rows.
- **C** — **done 2026-08-16**: alternation cross-products (§2), group
  transparency, and composition (§4).
- **D** — **done 2026-08-16**: anchor transparency (§3); battery
  planner edition + query-ladder re-run (records in the study
  docstrings); ADR 033's deferred list trued up.

## Open questions

- **§6 The caps — resolved 2026-08-16 (Clay, in session, on the
  slice A memo's numbers): both caps, small values.** A post-fold
  class-member cap of **8** and a shared width ceiling of **64**
  enforced at every cross step; over-cap expansion degrades that node
  to today's flush. Rationale (memo §§3–4): a single ceiling alone is
  order-sensitive and measured non-monotonic (junk forks starve
  valuable ones); per-upgrade caps alone leave the composed product
  unbounded (width-1000 in-corpus, adversarially unbounded); together
  they are monotone with 4× headroom over measured saturation (W=16)
  and demand (12). The width constant deliberately matches glob's
  `MAX_PATTERN_ARMS = 64` so both pattern surfaces degrade at the
  same declared width. Slice B named them `MAX_CLASS_MEMBERS` and
  `MAX_VARIANT_WIDTH`, module constants beside `GRAM_SIZE`; the
  resolved open-questions entry moved to
  `../../open-questions-archive.md`.
