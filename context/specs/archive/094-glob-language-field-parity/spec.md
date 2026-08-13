# 094 — Glob language field parity: brace alternation, exclusion channel, kind filter

- **Status: shaped 2026-08-07** — drafted from the glob-docs research
  pass (the ripgrep/globset, gitignore, bash, and `glob.translate`
  survey behind `docs/reference/glob-patterns.md` and
  `docs/explanation/glob-language.md`, with the empirical battery
  against `vfs.pattern_matching.glob`) and the open-questions entry
  "Glob language gaps vs the field." The five owner forks were
  resolved by Clay at the same-day shaping review — resolutions
  inline and in *Open questions*; fork 4 resolved with an option
  better than any drafted (fetch-to-populate, grep parity).
  **Adversarially reviewed
  2026-08-07** (subagent verification pass against the live tree):
  three drafting errors corrected (glob's dispatch builder is
  single-pattern today and must rewrite to per-member shape; defect
  gating must run twice — raw text and per expanded arm; `kind`
  rides inside each self-contained pattern arm, never beside the
  fan) and the root-probe gate, `params.py`, the meta-admission
  arm, the ADR 030 annotation, and the LIKE-superset trigger
  argument added.
  **Slice A landed 2026-08-07**: `expand_pattern` + `MAX_PATTERN_ARMS`
  (64) + the brace defect clauses (twice-gated, class-aware scanner,
  lazy cross-product stopping one arm past the cap) at the chokepoint;
  glob's dispatch builder rewritten to the per-member
  `_composed_members` shape with any-arm keep/reaches; ingress
  expansion on glob's pattern and grep's glob channels; chained glob
  any-arm. Suite 2159, coverage 100%, `ruff`/`ty` zero.
  **Slice B landed 2026-08-07**: `globs_not`/`ext_not`/`kind` across
  verb → params gate (`OBJECT_KINDS`) → composition (exclusions
  compose per root via `_composed_members`) → the one protocol
  signature change → backend → `reads.py` (kind inside every arm,
  `ARM_FIXED_BINDS` 6→7; exclusions gate Python-side beside the
  authority, never SQL); the probe's `keep` honors every channel;
  chained glob gains the exclusion gates and the fork-4
  fetch-to-populate (`stat` with the empty projection — identity
  fields ride free). Conformance rows for all three channels plus
  defective-exclusion refusal; namespace rows incl. root-row
  rejection per channel and the chained kind battery (held-fact
  no-storage, fetch-only-lacking, vanished-loud, no-kind-no-fetch).
  Suite 2178, coverage 100%; **four Docker engine legs green**
  (Postgres 191 / MySQL 191 / MSSQL 192 / Oracle 190) with the new
  rows live on every engine.
  **Slice C landed 2026-08-07 — story complete**: the cap-×-1k-roots
  scale row (one glob call + one probe, 64,000 members); the
  differential battery's brace edition (three `rg -g` brace cases —
  admission by name, anchored path, exclusion — 121 case-checks green
  across the four worlds); docs flip (reference: alternation section,
  refusal table, escape table, ripgrep table; explanation: field
  table, "where the language deliberately stops"); open-questions
  true-up; the ADR 030/034 annotations written in-place. The optional
  notebook cell is the one §4 item left undone, by choice.
  **Mined and archived 2026-08-13**: decision set → ADR 037 (the
  retroactive record — the five fork resolutions, the
  exclusions-are-authority-side doctrine, kind-as-parameter,
  fetch-to-populate, and the declined/deferred list); everything
  else was already downstream at landing (the two docs pages, the
  ADR 030/034 in-place annotations, the differential battery's
  brace edition, the open-questions resolution). STATUS.md trued up
  in the same pass per the campaign's decision 7.
- **Date:** 2026-08-07
- **Owner:** Clay Gendron
- **Kind:** pattern-language extension (brace alternation at the
  chokepoint) + glob verb parameter additions (`globs_not`,
  `ext_not`, `kind`) + one storage-protocol signature change
  (`SupportsPatternSearch.glob` gains the new channels) +
  conformance rows + docs true-up.
- **Depends on:** ADR 032 (the compile chokepoint and the
  LIKE-superset doctrine), ADR 031 (the pattern-only seam;
  composition and residuation; the probe), ADR 034 (chaining filters
  rows in hand through the same shared authorities), ADR 030
  (anchoring and composition), ADR 023 (path-derived ext), the
  2026-08-07 field survey recorded in
  `docs/explanation/glob-language.md`.
- **Relates to:** the open-questions entry "Glob language gaps vs
  the field: braces, exclusion channel, iglob, kind filter" (this
  spec closes gaps 1, 2, 4, and 5 of that entry and records the
  posture on 3 and 6); spec 093 (grep's `globs`/`globs_not`
  machinery, inherited here by glob); the MCP pass (result
  transport, where any future pagination/case questions land).

## Intent

The glob docs research measured vfs against the field (ripgrep,
globset, gitignore, bash) and found the language sound but short in
four places. Two are false friends today: `{a,b}` silently matches a
literal brace-named file when every neighboring tool would expand it
— exactly the typo'd-recursion shape `glob_defect` exists to refuse —
and a glob call cannot exclude (`grep` has `globs_not=`; `glob` has
nothing, so "everything under `/src` except `tests/**`" is
inexpressible in one call). Two are absent conveniences with clean
homes: directory-only matching (gitignore's trailing `foo/`, refused
by our defect gate, wants a `kind=` parameter instead of pattern
syntax) and extension exclusion (`ext_not=`, which grep already has).

One sentence: **teach the chokepoint to expand braces into the
pattern fan every surface already speaks, give `glob` the exclusion
and kind channels its sibling verb already has, and keep every new
fact flowing through the one compiled authority — no new matching
machinery, only new spellings into the machinery that landed with
ADRs 031–034.**

Explicitly *not* in this story (recorded with rationale in shape §5):
case-insensitive path matching, plural `patterns=`, backslash
escapes, POSIX classes, gitignore trailing-slash syntax, and
`{1..3}` numeric ranges.

## Shape

### 1. Brace alternation at the chokepoint

`{a,b}` becomes alternation, expanded **textually, before anything
else sees the pattern** — before anchoring, defect scanning,
canonicalization, composition, and compilation — so every downstream
surface keeps receiving plain patterns it already understands.

- **Grammar.** `{alt,alt,...}` with one or more comma-separated
  alternatives; each alternative is arbitrary pattern text (wildcards,
  classes, and `/` allowed — `{src,docs}/**/*.md` and `*.{ts,tsx}`
  both work). Alternatives may be empty (`x{a,}` expands to `xa` and
  `x`); an expansion that manufactures an empty component is caught
  by the existing defect gate downstream. Multiple groups take the
  cross-product (`{a,b}/{c,d}` → four patterns). Nested braces are
  refused (fork 2). A single-alternative group `{a}` expands to `a`.
- **Expansion point.** A new public `expand_pattern(pattern) ->
  tuple[str, ...]` in `vfs.pattern_matching.glob`, applied at router
  ingress to `glob`'s `pattern` and to every element of `grep`'s
  `globs`/`globs_not` (and glob's new channels, §2). Chained calls
  expand identically before filtering rows in hand. Storage is
  untouched by this section: the pattern-search seam already carries
  `patterns: tuple[str, ...]`, and each expanded arm composes,
  residuates, and prefilters as an ordinary pattern. Mixed-subject
  expansions (`{src/a,b}` → one anchored arm, one floating arm) are
  legal — but only the storage seam and grep's `_composed_members`
  are per-pattern today; **glob's router dispatch builder branches
  once on the call-level pattern** (member building, the probe's
  `keep` predicate, and `_glob_reaches` all assume one pattern), so
  slice A rewrites glob's dispatch to the per-member shape grep
  already uses, with any-arm semantics for root service and
  reachability.
- **Defects, not false friends — gated twice.** The raw caller text
  is checked first (brace-structure defects: unclosed `{`, bare `}`,
  empty group `{}`, nested braces — messages in the existing
  register), then `expand_pattern` runs, then **every expanded arm
  passes through `glob_defect` again** — expansion can manufacture
  defects (`x/{a,}` yields the empty-component arm `x/`), and the
  per-arm refusal names both the offending arm and the caller's
  source pattern so the message points at what was written, not at
  text the router invented. Per fork 1 (recommended), *any* bare
  brace outside a character class participates in alternation syntax
  or is refused — never silently literal.
- **Expansion cap.** A declared module constant bounds the arm count
  (fork 3 — recommended 64). Exceeding it classifies as an `invalid`
  refusal naming the cap, mirroring the refusal-gate posture: loud,
  with the fix in the message. The cap bounds the multiplication the
  fan machinery must absorb (arms × LIKE variants per arm), on top of
  the chunked statement budgets that already keep any batch bounded.
- **Literal braces** are matched with class notation — `[{]` and
  `[}]`, verified against the live compiler (`/[{]a,b[}].txt`
  matches `/{a,b}.txt`). Behavior change, recorded: a pattern like
  `{a,b}.txt` stops matching a literally-brace-named file and starts
  expanding. Greenfield, no users to migrate; the docs flip in the
  same landing.

### 2. Exclusion channels on glob: `globs_not` and `ext_not`

`glob` gains the two exclusion channels `grep` already carries, with
identical semantics — a row is admitted by `pattern` (any expanded
arm) and rejected by any exclusion:

- **Verb ingress:** `globs_not: tuple[str, ...] = ()` and
  `ext_not: tuple[str, ...] = ()` on the public `glob`. Defective
  exclusion globs refuse before dispatch, exactly as grep's do.
  `ext_not` normalizes by the same law as `ext` (dot stripped,
  case folded).
- **Composition and the seam:** exclusions compose under each scope
  root through `composed_pattern` and residuate per mount — the
  machinery spec 093 landed for grep's channels, reused verbatim. A
  composed exclusion carries its root prefix, so it can never reach
  another root's subtree. `SupportsPatternSearch.glob` gains
  `globs_not` and `ext_not` (entry-local, composed) — the one
  protocol signature change in this story.
- **Authority, not prefilter:** the LIKE-superset doctrine cannot
  serve exclusions — an over-approximating `NOT LIKE` would wrongly
  *exclude*, the forbidden false negative. Exclusions are therefore
  applied by the compiled authorities in Python against candidates
  the admission side produced; SQL pushdown of exclusions is out of
  scope (an exact-literal-only pushdown is a recorded future
  optimization, demand-gated).
- **Chaining:** chained `glob(observations=..., globs_not=...,
  ext_not=...)` applies the exclusions in memory over rows in hand —
  same pure-filter posture as ADR 034, no storage, order and
  duplicates preserved, no meta rule (paths in hand are never
  hidden).
- **The root probe honors every channel.** The find-operand law
  serves a scope root's own row when the pattern matches it; today
  the probe's `keep` predicate checks pattern + ext only. It gains
  the full gate set — any expanded arm admits, any exclusion glob or
  `ext_not` rejects, and the §3 `kind` fact must match — so a root
  row can never be served past a filter the caller stated.
- **Meta interplay:** exclusion can only *narrow*; it can never
  reveal `/.vfs`. No change to the meta bypass rule. One admission
  change rides §1, recorded here: the meta literal-prefix bypass is
  judged per composed arm, so `/.{vfs,src}/**` — a literal brace
  name today, no bypass — expands to an arm whose `/.vfs` prefix
  lifts the meta exclusion for that subtree. Consistent with
  expansion-first (the arm is what the caller now means), and pinned
  by a conformance row.

### 3. Kind filter on glob

- `glob` gains `kind: ObjectKind | None = None`
  (`Literal["file", "directory"]`); `None` means no filter. This is
  the house answer to gitignore's trailing-slash convention: the
  pattern stays pure path algebra, and "directories only" is a
  column fact selected by a parameter — *what*, not *how*.
- **Storage:** an exact `kind = :kind` predicate — a true filter,
  not a prefilter, so no Python re-check is needed beyond the
  existing authority gate. It rides **inside every pattern arm**,
  not beside the fan: the arm doctrine is a pure OR of
  self-contained arms (a conjunct beside the fan demotes every
  engine's multi-index OR to a scan), so `kind` duplicates into each
  arm exactly as caller `ext` and liveness do, and the per-arm bind
  accounting (`ARM_FIXED_BINDS`) grows by one.
  `SupportsPatternSearch.glob` carries the parameter (folded into
  §2's signature change).
- **Chaining — fetch-to-populate (fork 4, resolved by Clay
  2026-08-07):** chained glob with `kind=` acts exactly like chained
  grep acts for content. Rows that carry `kind` filter in memory, as
  held. Rows whose `kind` is unpopulated get it fetched through the
  router's own `stat` over the grouped-dispatch machinery — one
  batched call for just the lacking rows — and a row that cannot be
  statted classifies loudly through stat's ladder beside the healthy
  rows' results, never a silent drop. This is ADR 034's own law
  generalized, not an exception to it: *a chained verb matches in
  memory the facts it holds and fetches only the facts the call's
  parameters make load-bearing and the rows lack* — `kind=` makes
  kind load-bearing the way grep's pattern makes content
  load-bearing. Without `kind=`, chained glob stays purely
  in-memory, storage never touched; ADR 034 decision 1 gets an
  annotation recording the subject-expansion reading (§4).
- **The lacking case is rare by construction (verified premise):**
  `kind` is an identity field — `ALWAYS_ON_FIELDS` in the backend's
  projection means every storage-served row carries `path`, `kind`,
  and `version` under *any* `columns=` projection, already pinned by
  the projection conformance rows. Only hand-built
  `Observation(path=...)` rows lack `kind`, so the fetch triggers
  exactly for them.
- **Grep is untouched** — its subject already confines it to content
  rows.

### 4. Docs, records, and notebook true-up

The two docs pages this spec grew out of flip in the same landing —
not just the named sections but every statement the change falsifies:
the reference page's brace paragraph ("literal text" → the
alternation grammar with the cap and the `[{]` escape), its
ripgrep-comparison table rows (braces, exclusion), and the
"Exclusion is a separate channel (grep's `globs_not=`)" line; the
explanation page's "no pattern spelling for directories-only today"
sentence, its field-comparison table (`{a,b}` row), and the "Gaps
worth closing" section, which shrinks to the recorded deferrals.
The open-questions entry updates to resolved-by-094 for the closed
gaps. **ADR 030 gets an annotation**: its "why `paths` survives"
rationale includes "the pattern grammar has no alternation, so a
pattern cannot express a root union" — after braces that premise is
dead (`{/data,/logs}/**` expresses the union, minus assertions); the
decision stands on its other rationales, and the annotation says so
rather than leaving the record citing a dead premise. **ADR 034
decision 1 gets an annotation too**: "chained glob never touches
storage" gains the `kind=` fetch-to-populate refinement (§3) — the
law generalizes from "glob's subject is always in hand" to "fetch
only the load-bearing facts the rows lack," which is what decision 2
already said for grep. Optional: a brace-expansion cell in
`examples/glob_residuation.ipynb`.

### 5. Declined and deferred (recorded)

- **Case-insensitive path matching (`--iglob`)** — *deferred to its
  own research memo* (fork 5). It is the one gap that cuts semantics,
  not spelling: the compile chokepoint gains a flag easily, but the
  SQL prefilters need case-folded variants per dialect (collation
  interplay), and residuation's `_component_matches` would need a
  case posture at mount seams. Research-stage per the pipeline, not
  spec-stage.
- **Plural `patterns=` on the public verb** — *declined.* One
  pattern is the verb's subject; braces express the common unions,
  and multiple calls (or chaining) compose the rest. The seam's
  `patterns` tuple is dispatch plumbing, not a public contract.
- **Backslash escapes** — *declined.* Ambiguous against names that
  really contain backslashes; class notation already escapes every
  metacharacter, now including `[{]`.
- **POSIX classes (`[[:alpha:]]`)** — *declined.* No engine support
  in `glob.translate`, no observed demand, ranges cover the cases.
- **gitignore trailing-slash (`foo/`)** — *declined* in favor of §3;
  the defect gate keeps refusing the spelling loudly.
- **`{1..3}` numeric ranges** — *deferred*; bash-only in the field
  (globset lacks them), and `[1-3]` covers the single-digit cases.

## Verification obligations

- **Chokepoint battery:** `expand_pattern` rows — cross-products,
  empty alternatives, slash-bearing and mixed-subject arms, `{a}`,
  cap refusal at the boundary, and every new defect message
  including the **post-expansion per-arm defect** (`x/{a,}` refuses
  naming both arm and source); the existing `glob_defect` battery
  extends rather than forks.
- **Conformance rows:** brace patterns through the full stack (
  scoped, mounted, chained — placement-invariance style) including
  a mixed-subject expansion and the **meta-admission arm** (§2);
  `globs_not` and `ext_not` on glob incl. the never-reveals-meta
  row, the composed-exclusion-stays-under-its-root row, and the
  **root-row rows** (a scope root rejected by each of `globs_not` /
  `ext_not` / `kind` is not served); `kind=` rows for both values
  plus the fork-4 chaining rows: a hand-built row's kind is fetched
  and filtered correctly, a vanished row classifies loudly through
  stat's ladder, and a fully-populated batch dispatches **zero**
  storage calls (the fetch triggers only for lacking rows). The
  identity-projection premise needs no new rows — the existing
  projection pins cover it.
- **LIKE-superset study trigger, discharged by argument:** ADR 032
  obliges a re-run of the LIKE-superset harness when the chokepoint
  changes. This story changes the chokepoint's *ingress* (expansion,
  new defects) but not the translation: every arm reaching
  `_glob_like` is a plain pattern of the already-studied grammar,
  and post-expansion no brace can reach the translator at all
  (today they reach it as literals). Recorded here as the reason the
  trigger does not fire; if review disagrees, the harness re-runs
  re-pointed instead.
- **Differential battery extension:** brace arms vs `rg -g` over the
  existing scratch worlds (the one field tool with the same expansion
  semantics), with divergences allowlisted as before.
- **Scale row:** an expansion at the cap across 10k-root scope stays
  within the declared statement budgets (recorded-statement
  assertions on sqlite; the chunked fan already owns the bound).
- Suite green, coverage 100%, `ruff`/`ty` zero, no new suppressions;
  the four Docker engine legs green (the protocol signature change
  touches every engine's glob path).

## Touch points

- `src/vfs/pattern_matching/glob.py` — `expand_pattern` (new public),
  brace defects, the arm-cap constant.
- `src/vfs/pattern_matching/__init__.py` — re-export.
- `src/vfs/base.py` — ingress expansion for glob/grep pattern
  channels with the twice-gated defect flow; glob's dispatch builder
  rewritten to per-member shape (the `_composed_members` form) with
  any-arm root service and reachability; the probe's `keep`
  predicate gains the exclusion/`ext_not`/`kind` gates; chained glob
  gains exclusion/kind filtering.
- `src/vfs/params.py` — glob's `PARAM_SPECS` row gains `globs_not`,
  `ext_not`, and `kind` (with its choices vocabulary), mirroring
  grep's row.
- `src/vfs/storage/protocol.py` — `SupportsPatternSearch.glob` gains
  `globs_not`, `ext_not`, `kind`.
- `src/vfs/storage/backends/database/backend.py`, `reads.py` —
  parameter plumb-through; `kind` inside every pattern arm with the
  `ARM_FIXED_BINDS` bump; Python-side exclusion gate beside the
  existing authority check.
- `tests/pattern_matching/test_glob.py`, `tests/base/`,
  `tests/support/storage_contract.py`, `tests/storage/database/` —
  per the verification obligations.
- `docs/reference/glob-patterns.md`,
  `docs/explanation/glob-language.md`, `context/open-questions.md` —
  the §4 true-up.

## Slices (each landing leaves the tree green)

- **A — braces at the chokepoint.** `expand_pattern`, defects, cap,
  ingress wiring for glob + grep channels, chaining, chokepoint and
  conformance rows. No protocol change; lands end to end on the
  existing patterns fan.
- **B — the new glob channels.** `globs_not`/`ext_not`/`kind` across
  verb → composition → seam → backend → chaining, in one signature
  change; conformance rows live on all legs.
- **C — proof and true-up.** Differential battery extension, scale
  row, docs flip, open-questions resolution, four Docker legs.

## Open questions

None — the five shaping forks were resolved by Clay at the
2026-08-07 shaping review:

1. **Malformed braces → defect.** Any bare `{`/`}` outside a class
   either alternates or refuses; never silently literal.
2. **Nesting → refused now** (globset's posture; expandable later
   without breaking anything).
3. **Arm cap → 64**, the declared constant.
4. **Chained kind on unpopulated rows → fetch-to-populate** (Clay's
   own resolution, superseding all three drafted options): mirror
   chained grep — batch-`stat` exactly the lacking rows, filter on
   the fetched fact, classify unstattable rows loudly. Shape §3
   records the mechanism and the ADR 034 generalization; the
   identity-field projection guarantee (`kind` always rides, any
   projection) was verified live and is already pinned.
5. **iglob → deferred** to a research memo (collation-aware SQL
   prefilters and residuation case posture are research-stage).
