# 038. Gram-Planner Expansion Upgrades: Bounded Variants Under Two Declared Caps

- **Status:** accepted 2026-08-16 — the spec 100 §6 cap fork resolved
  by Clay in session on the slice A memo's numbers (taught through
  the measurement before deciding); recorded at the same-day mining
  pass, the same convention as ADRs 032/033/037 (the retroactive
  records of 073's, 093's, and 094's decision sets). Discharges
  ADR 033's deferred planner-upgrades item (093's shaping fork 3);
  everything else ADR 033 governs — the refusal gate, the posting
  ladder, the budgets, the epoch lifecycle, the verifier — is
  untouched.
- **Date:** 2026-08-16 (decided, landed, and recorded)
- **Deciders:** Clay Gendron
- **Context source:** the slice A research memo
  `../research/2026-08-16-gram-planner-expansion-caps.md` (prior-art
  studies of the read-only codesearch and zoekt checkouts, a
  231-pattern field corpus, and an executed prototype of all three
  upgrades whose off-configuration reproduced the live planner on
  every pattern), with the rerunnable study under
  `../research/studies/2026-08-16-gram-planner-expansion-caps/`.
  Implemented by spec 100 (landed 2026-08-16, all slices in one arc;
  mined to `../specs/archive/` the same day).

## The deciding argument

Once the refusal gate had live shape, the field corpus put numbers on
what it refused: 61 of 216 parseable field patterns (28%), and the
boundary between refused and served was partly invisible — CPython's
`sre_parse` factors shared branch prefixes, so `min|max` parses as
`m(in|ax)` and refused while `alpha|beta` indexed. The three deferred
upgrades turned out to be one mechanism, not three: every conservative
give-up in the planner is the same adjacency break, and each upgrade
replaces one break with a finite fork of guaranteed-literal variants —
so the caps must bound the *composed product* of forks, not each
upgrade in isolation.

The cap fork was decided by measurement, not taste. A single shared
width ceiling alone is order-sensitive and **non-monotonic** — W=128
rescued fewer patterns than W=64, because gramless digit-class forks
expand first and starve the gram-bearing branch behind them. Per-node
caps alone leave the product unbounded (a width-1,000 expansion
in-corpus; adversarially unlimited). Both caps together are monotone
with 4× headroom over measured saturation (W=16) and the widest real
demand (12) — which is also codesearch's shape: a class-cardinality
cap plus small set caps re-applied after every combine. zoekt is the
floor being moved off (it never expands, and answers these patterns
by factoring instead).

## Decisions

### 1. The planner compiles bounded guaranteed-literal variants

`build_code_gram_query` compiles the `sre_parse` AST into a set of
*variants* — each a sequence of literal segments with known adjacency
— then to the existing algebra: one `GramAnd` per variant, `GramOr`
across variants, identical gram sets deduped. The three upgrades
share this one core; the soundness law (false positives allowed,
false negatives never; the plan is a necessary fact, not an
authority) and folded-only planning are unchanged.

### 2. Small character classes fork per post-fold member

An `IN` node whose members enumerate (literals and small ranges)
forks one variant per member, **counted after the shared fold** — so
`[fF]` costs width 1 and `[fF]oo` plans exactly as `(?i)foo`, the
perversity the arc set out to fix. Negated classes, category escapes
(`\w`, `\d`), and over-cap classes keep the adjacency break.

### 3. Alternations fork at any depth; group transparency is a prerequisite

A `BRANCH` at any depth forks one variant per arm, composed with the
surrounding literal context — erasing the prefix-factoring asymmetry
(`min|max` and `alpha|beta` now plan alike). `SUBPATTERN` becomes
fully adjacency-transparent: `foo_(bar|baz)` only composes if the
group passes adjacency through, so transparency ships with the
alternation upgrade, not as an optimization.

### 4. Zero-width anchors sever no adjacency

`AT` nodes (`^`, `$`, `\b`, ...) contribute no bytes and no longer
break runs. Soundness: if a match exists, the literals flanking a
zero-width assertion are byte-adjacent in it; a pattern the assertion
makes unsatisfiable has no matches to lose, so requiring the joined
grams is vacuously sound (codesearch compiles the same six assertions
to the empty string).

### 5. Two declared caps, small values, enforced continuously

`MAX_CLASS_MEMBERS = 8` (post-fold; between codesearch's
`maxExact = 7` and its case-orbit floor of 8 — keeps every folding
pair and small enumerable class, flushes the digit/hex ranges the
measurement showed are pure budget-burners) and
`MAX_VARIANT_WIDTH = 64` (the shared ceiling on the variant product,
enforced at **every** cross step so intermediate state stays bounded,
never only on the final query). The width value deliberately equals
glob's `MAX_PATTERN_ARMS`, so both pattern surfaces degrade at the
same declared width — pinned by a test asserting the equality.

### 6. Over-cap expansion degrades; refusal stays the collapse law's job

An over-cap class or product degrades **that node** to the plain
adjacency break — a weaker predicate, never a refusal, and the
already-accumulated variants survive. Refusal remains exclusively the
collapse law: any variant with no required grams collapses the whole
query to `GramAny` (`^(#|Using)` still refuses — the `#` arm can
guarantee no trigram).

### 7. The planner never manufactures grams

Invariant preserved by every upgrade: the planner only claims grams
appearing in the pattern's guaranteed literal text — it never
manufactures wildcard-position grams to dodge a refusal. Sub-3-byte
patterns (`ab`, `md`) stay refused at every cap value; serving them
would be an index-shape change (a different gram size), not a planner
change.

### 8. No new runtime knob

Wide-alternation fetch cost stays governed by ADR 033's runtime
bounds (per-branch rarest-gram budget exemption, the wall-clock
deadline consulted between branches). `grep.py`, the gate message,
the ladder, and the budgets did not change in this arc.

## Declined and deferred (recorded with rationale)

- **Expanding negated classes, categories, and lookarounds** —
  *declined*: zero rescues attributable in the corpus; they keep
  today's break, expandable later without breaking anything.
- **Wider class caps** — *declined by measurement*: the member-cap
  sweep was flat from M=2 to M=128 (rescues never moved); larger
  values only re-admit the starvation pathology the small cap kills.
- **Sub-trigram pattern support** — *out of scope*: a different
  index grain, not an expansion; `allow_scan=True` remains the
  answer, and the refusal names it.

## Consequences

- `MAX_CLASS_MEMBERS` and `MAX_VARIANT_WIDTH` are public module
  constants beside `GRAM_SIZE` in `models/code_grams.py`; the
  run-collector internals (`_collect_runs`, `_pure_literal_text`)
  were replaced by the variant compiler validated in slice A.
- Measured refusal delta on the field corpus: 28% → 22% of parseable
  patterns; every rescue comes from the alternation upgrade — classes
  and anchors earn their keep by narrowing candidate sets on
  already-indexable patterns (15/155 plans strengthened).
- Proofs at landing: pinned planner rows (`min|max` indexable,
  `^(#|Using)` still refused, the digit-class starvation pattern
  indexable at the declared caps as the monotonicity guard, `[fF]oo`
  single-variant), **executed** cap mutants (member cap to 16, width
  ceiling to 128, over-cap collapse dropped — each fails a pinned
  row), a match-preserving mutation fuzz, the battery planner edition
  (181 case-checks vs `grep -E`/`rg -uu` across four worlds), and
  the ladder planner rows (rescued classes serve at 21–28 ms vs
  272–318 ms scans at the 10K-doc tier).
- The slice A study measured the pre-upgrade planner; its docstring
  pins the baseline commit (`354a6f7`) so its recorded numbers stay
  reproducible.
