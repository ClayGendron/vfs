# Gram-planner expansion caps: prior-art values and the measured refusal delta

- **Status**: research memo — slice A of the planner-upgrades story;
  brings the numbers for the caps fork (one shared final-width ceiling
  vs per-upgrade caps), pointered in `../open-questions.md`
- **Date**: 2026-08-16
- **Owner**: Clay Gendron
- **Question**: The three planner upgrades (bounded char-class
  expansion, alternation cross-products, anchor-tolerant extraction)
  compose, so their caps must bound the *product* of expansions. What
  do the field tools clamp, what would each upgrade actually rescue
  over field patterns, and where should our caps sit?
- **Evidence gathered**: two line-level prior-art studies of the
  read-only reference checkouts (`~/Git/Repos/codesearch`, BSD;
  `~/Git/Repos/zoekt`, Apache-2.0); a 231-pattern field corpus mined
  from the ripgrep test suite and docs plus `grep -E`/`egrep`/`rg`
  invocations in the linux, git, postgres, freebsd-src, sqlite, and
  zoekt trees; and an executed prototype of all three upgrades whose
  off-configuration reproduces the live planner exactly (0/231
  mismatches). Scripts and the mined corpus are rerunnable under
  `studies/2026-08-16-gram-planner-expansion-caps/`.

---

## 1. Prior art: two opposite disciplines

**codesearch expands and clamps** (`index/regexp.go`). Its planner
builds exact/prefix/suffix string sets per AST node and re-clamps them
after *every* combine step:

- `maxExact = 7` — exact-set width (regexp.go:368); sized so three
  case-insensitive letters (2³ = 8 variants) trigger a flush.
- `maxSet = 20` — prefix/suffix-set width (regexp.go:377); sized so a
  case-insensitive 3-letter literal (8 variants) survives.
- Inline `100` — character-class cardinality cap (regexp.go:525):
  classes up to 100 runes expand to single-char exact strings; larger
  classes degrade to any-char.
- The cross product lives in concatenation (`cross`, regexp.go:838)
  and is unbounded *within* one combine, but every `analyze` case ends
  in `simplify`, so sets re-enter the next combine at ≤7/≤20. Degrade
  is a ratchet, never a refusal: overflowing exact sets bank their
  trigrams into the match query first, then truncate to 2-byte
  prefixes/suffixes; overflowing prefix/suffix sets shorten strings
  until they fit; any string under 3 bytes makes `andTrigrams` a
  no-op (`q AND ALL = q`).
- Zero-width assertions (`^ $ \A \z \b \B`) all compile to the empty
  string (regexp.go:428-432) — fully adjacency-transparent, exactly
  spec 100 §3's shape, with the same soundness argument.

**zoekt never expands** (`index/eval.go`,
`regexpToMatchTreeRecursive`). No character-class enumeration (an
explicit TODO at eval.go:617-619), no alternation distribution
(alternation compiles branch-by-branch to an OR; a concat containing
an alternation stays factored as AND(OR(...), ...)), no gram-joining
across concat siblings — so it has *no expansion caps at all*, only
the ≥3-byte literal floor (`ngramSize = 3`) and a degrade-to-brute-
force default. Assertions sever adjacency as a side effect of only
extracting grams within single literal nodes. One relevant execution-
time clamp: per substring atom it intersects only the *two*
lowest-frequency trigrams' postings and verifies the rest by string
comparison — a frequency-driven clamp rather than a width cap.

zoekt is the floor we are moving off (it is why `^(import|from)`-class
patterns still answer from its index: it factors, where our collector
flushes and loses everything). codesearch is the existence proof for
the expand-and-clamp direction, with the clamp applied after every
combine so intermediate state stays bounded.

## 2. Method

**Corpus** (231 unique patterns after dedupe): the ripgrep test suite
(53 — `.arg("...")` strings minus flags, flag values, and created
file names; regression.rs keys tests to real issue numbers, making
this the practical "ripgrep issue corpus"), ripgrep docs examples
(31), `grep -E`/`egrep`/`rg` invocations mined from shell scripts and
makefiles of linux, git, postgres, freebsd-src, sqlite, and zoekt
(122 — mostly linux perf/tooling scripts), plus the vfs query-ladder
(10) and differential-battery (15) pattern sets. POSIX classes were
normalized to Python spellings (`[[:space:]]` → `[\s]`, `\>` → `\b`)
since vfs users write Python re; 15 patterns that Python `re` rejects
(Rust-only syntax like `[\w--\p{ascii}]`, `(?-u)`, bare `*`) are
excluded — the live planner degrades them to `GramAny` and the
authoritative compile reports the error, so they are not planner
work.

**Prototype**: all three upgrades implemented over a fragment algebra
(a fragment is one alternative's guaranteed-literal segments with
open/closed adjacency at each end; every conservative give-up is the
BREAK fragment, which is exactly today's flush). Each upgrade sits
behind a toggle; caps are `member_cap` (post-fold class members) and
`width_cap` (fragment-set width, enforced at every cross step, the
codesearch discipline). Over-cap expansion degrades the node to
BREAK — degrade, never refuse. **Validation**: with all toggles off
the prototype's query equals the live `build_code_gram_query` on all
231 patterns (same `GramAny`/`GramAnd`/`GramOr` shape, same gram
sets). **Soundness spot checks**: for ten upgraded plans with a
hand-known matching line, the folded line's grams satisfy at least
one variant — zero false negatives observed.

## 3. The numbers

Baseline over the 216 parseable patterns: **155 indexable today, 61
refused (28%)**. Of the refused, 45 carry class/alternation/anchor/
group structure (the upgrades' target population); the rest are
sub-3-byte literals and bare wildcards no expansion can constrain.

**Rescue attribution** (generous caps, so attribution is not
cap-limited):

| upgrade configuration | rescued of 61 |
|---|---|
| §1 classes alone | 0 |
| §2 branches alone | **13** |
| §3 anchors alone | 0 |
| all three | 13 |

Every rescue is §2. One mechanism deserves naming because it makes
§2's reach wider than the spec's examples suggest: `min|max` refuses
*today* even though the planner splits top-level alternation, because
`sre_parse` factors the common prefix out of the branches — the AST
is `[LITERAL 'm', BRANCH('in'|'ax')]`, no longer a single top-level
BRANCH, so the split never fires and the lone `m` run has no trigram.
`alpha|beta` (no shared prefix) stays a bare BRANCH and indexes fine.
Whether an alternation indexes today thus depends on whether its arms
happen to share a first character — an asymmetry users cannot see;
§2's any-depth handling erases it. The rescued patterns are exactly
the field idioms the spec names — `^(startup|exit|split|unlikely|hot|unknown)(\.|$)`,
`MAP_(UNINITIALIZED|TYPE|SHARED_VALIDATE)`-style linux perf checks,
`^(fatal|error):.*(requires|incompatible with|needs)` from git,
`min|max`, `^(commit|tag)`, `(MSK|VERBOSE|MGC_VAL)\b`. That is 13/45
of the structured refusals (29%); the refusal rate over all parseable
patterns drops 28% → 22%. The still-refused structured patterns are
correctly refused: digit-only classes (`[0-9]+\.[0-9]+%`), sub-3-byte
branches (`^(#|Using)` — the `#` arm can guarantee no trigram), bare
anchors (`^`), `\b`-wrapped short literals (`\bR_`) — the collapse
law working as designed, not cap bites.

**§1 and §3 earn their keep by narrowing, not rescuing.** Over the
155 already-indexable patterns, 14-16 plans strengthen (strictly more
required grams / tighter OR arms) as the member cap rises from 0 to
100 at W=64 — e.g. `ext[234]` goes from requiring only `ext` to an OR
of `ext2/ext3/ext4` variants, and anchor transparency joins runs
across `^`/`$`/`\b` into longer gram chains. Candidate sets narrow;
results are unchanged by the soundness law. `[fF]oo`-style folding
classes collapse to a single variant post-fold (the spec's perversity
case) but did not appear as a refusal in this corpus — field users
apparently already write `(?i)`.

**Width demand is small and junk-dominated at the tail.** Uncapped,
11/13 rescues need final width ≤16; the two outliers (widths 101 and
200) get there by exploding *digit classes* whose variants contribute
zero grams — e.g. `' +[0-9]+\.[0-9]+% .* (Interpreter|jdk\.internal).*'`
spends 100 variants on `[0-9]+` digits and 2 on the branch that
carries all the grams.

**The single-ceiling shape is non-monotonic** — the measured surprise
that decides the fork. With one shared ceiling W (member cap tied to
W): W=64 rescues 13, **W=128 rescues 12**, W=256 rescues 13. At
W=128 the digit classes in the outlier pattern are under their cap,
so they expand first and exhaust the width budget before the
`(Interpreter|jdk\.internal)` fork — the branch degrades and every
variant ends gramless. At W=64 the second digit class is over budget
and flushes instead, preserving the branch. A left-to-right budget
lets worthless expansions starve valuable ones, and "raise the cap"
can *lose* patterns.

**A small member cap fixes it, and costs nothing.** With M=8
(post-fold), digit classes (10 members) and hex classes (16+) flush
immediately — they cannot constrain a gram query anyway — while
folding pairs (`[fF]` → 1), `[234]` (3), and `[ATCG]` (4) survive.
The W sweep at fixed M=8 is monotone and saturates at W=16 (13/13
from W=16 up). The member-cap sweep at W=64 is flat (13 rescues for
every M from 2 to 128) — M only moves the narrowing margin (15/155
strengthened at M=8 vs 16/155 at M=32).

**Per-upgrade caps alone don't bound the product.** With M=16 and no
shared ceiling, the corpus already produces a width-1000 expansion
(`[0-9]+.[0-9]+.[0-9]+` → 10×10×10 gramless variants), and the shape
is adversarially unbounded (nested branches multiply under any
per-node cap). With M=8 and no ceiling the corpus maxes at 12 — but
only because M=8 happens to kill the junk; composition
(`(a|b)(c|d)(e|f)...`) still needs the ceiling.

## 4. Reading and recommendation

The fork's two named options each fail alone, measurably: one shared
final-width ceiling is order-sensitive and non-monotonic (W=128 <
W=64); per-upgrade caps leave the composed product unbounded. The
answer is **both, with small numbers** — which is also exactly
codesearch's shape (class-cardinality cap + tiny set caps re-applied
after every combine):

- **Class member cap M = 8**, counted *post-fold*. Keeps every
  folding pair and small enumerable class; flushes digit/hex/alpha
  ranges, which the measurement shows are pure budget-burners (no
  rescue at any M; they only starve branches). Sits between
  codesearch's `maxExact = 7` and its case-orbit floor of 8.
- **Shared final-width ceiling W = 64**, enforced at every cross step
  (bounds intermediate state and memory, not just the final query).
  4× headroom over both the measured saturation point (W=16) and the
  widest real demand (12); numerically identical to glob's
  `MAX_PATTERN_ARMS = 64`, so the two pattern surfaces degrade at the
  same declared width.
- Over-cap behavior stays as specced: degrade that node to today's
  flush, never refuse; refusal remains the collapse law's job.

Implementation notes for slices B–D that fall out of the numbers:
group adjacency-transparency is a *prerequisite* of §2 (the
`foo_(bar|baz)` composition requires the group to pass adjacency
through; the prototype ties it to the branches toggle); and the two
caps make the W=128 pathology unreachable, but a planner row pinning
the `' +[0-9]+…(Interpreter|jdk\.internal)'` pattern as indexable
would keep it that way under future cap changes.

## 5. Limitations

The corpus skews toward linux/git build-and-perf scripts (122 of
231); agent-issued patterns may lean harder on `(?i)` and classes.
Rescue counts are corpus-relative — the qualitative findings (all
rescues are §2; digit classes never help; single ceiling is
non-monotonic) are structural and should transfer. The prototype
dedupes identical variants at query build; the live implementation
may dedupe earlier. Lookarounds, `\w`-category classes, and negated
classes were left at today's flush per the spec, and nothing in the
corpus argues for more.
