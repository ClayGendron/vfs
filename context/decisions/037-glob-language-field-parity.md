# 037. Glob Language Field Parity: Brace Alternation, Exclusion Channels, Kind Filter

- **Status:** accepted 2026-08-07 — the five shaping forks resolved by
  Clay at the spec 094 shaping review; recorded retroactively at the
  2026-08-13 mining pass, the same convention as ADRs 032/033 (the
  retroactive records of 073's and 093's decision sets). Extends
  ADR 032's pattern language and pushdown doctrine; the two
  annotations this arc obliged — ADR 030 (the root-union premise
  retired by alternation) and ADR 034 (the fetch-to-populate
  refinement) — were written in-place at the landing.
- **Date:** 2026-08-07 (decided); recorded 2026-08-13
- **Deciders:** Clay Gendron
- **Context source:** the glob-docs research pass — the field survey
  against ripgrep/globset, gitignore, bash, and `glob.translate`
  recorded in `docs/explanation/glob-language.md` and
  `docs/reference/glob-patterns.md`, with an empirical battery
  against the live compiler — and the open-questions entry "Glob
  language gaps vs the field." Implemented by spec 094 (landed
  2026-08-07 in three slices; mined to `../specs/archive/`
  2026-08-13). Adversarially reviewed at shaping (three drafting
  errors corrected against the live tree before any code).

## The deciding argument

The survey found the language sound but short in four places, two of
them false friends: `{a,b}` silently matched a literal brace-named
file when every neighboring tool would expand it — exactly the
typo'd-recursion shape `glob_defect` exists to refuse — and glob had
no exclusion channel while its sibling verb did. The fixes all follow
one law: **no new matching machinery — only new spellings into the
compiled-authority machinery ADRs 031–034 already landed.** Braces
expand into the pattern fan every surface already speaks; exclusions
ride the channel shape grep already carries; "directories only" is a
column fact selected by a parameter, never pattern syntax.

## Decisions

### 1. Brace alternation is expansion-first at the chokepoint

`{a,b}` expands **textually, before anything else sees the pattern**
— before anchoring, defect scanning, canonicalization, composition,
and compilation — so every downstream surface (composition,
residuation, SQL prefilters, the compiled authority) keeps receiving
plain patterns. Grammar: one or more comma-separated alternatives of
arbitrary pattern text (`/` included, so `{src,docs}/**/*.md`
works); empty alternatives legal (`x{a,}` → `xa`, `x`); groups
cross-product left to right; `{a}` → `a`; duplicates collapse.

### 2. A bare brace alternates or refuses — never silently literal

Any `{`/`}` outside a character class participates in alternation
syntax or is a refusable defect (unclosed `{`, bare `}`, empty
`{}`). Defects are **gated twice**: raw brace structure first, then
every expanded arm re-passes `glob_defect` — expansion can
manufacture defects (`x/{a,}` yields the empty-component arm `x/`),
and the refusal names both the arm and the caller's source pattern.
Literal braces are spelled with class notation (`[{]`, `[}]`) —
since spec 098, `escape_glob` produces that spelling for callers.

### 3. Nesting is refused; the arm cap is a declared 64

Nested braces refuse (globset's posture — expandable later without
breaking anything). `MAX_PATTERN_ARMS = 64` bounds the expansion; an
over-cap pattern refuses `invalid` naming the cap and the fix, and
collection stops one arm past the cap so the oversized expansion is
detected without being materialized.

### 4. Exclusions are authority-side, never SQL prefilters

The LIKE-superset doctrine (ADR 032) structurally cannot serve
exclusion: an over-approximating `NOT LIKE` would wrongly *exclude*
— the forbidden false negative. `globs_not`/`ext_not` therefore gate
candidates in Python beside the compiled authority, on both verbs.
An exact-literal-only exclusion pushdown is a recorded, demand-gated
future optimization. Exclusions compose per scope root exactly as
admissions do, so a composed exclusion can never reach another
root's subtree; exclusion can only narrow — it never reveals
`/.vfs`.

### 5. Directory-only matching is a parameter, not pattern syntax

`kind=` (`file` | `directory`) is the house answer to gitignore's
trailing-`foo/` convention: the pattern stays pure path algebra, and
the kind fact — an exact filter, not a prefilter — rides **inside
every self-contained pattern arm** per the arm doctrine (a conjunct
beside the fan demotes every engine's multi-index OR to a scan).

### 6. Chained `kind=` is fetch-to-populate

ADR 034's law, generalized rather than excepted: *a chained verb
matches in memory the facts it holds and fetches only the facts the
call's parameters make load-bearing and the rows lack.* Rows
carrying `kind` filter as held; lacking rows get one batched `stat`
for exactly them; an unstattable row classifies loudly beside the
healthy rows. Without `kind=`, chained glob touches no storage. The
lacking case is rare by construction: `kind` is an identity field
(`ALWAYS_ON_FIELDS`) riding every storage-served projection — only
hand-built rows lack it.

### 7. The meta bypass is judged per composed arm

`/.{vfs,src}/**` expands to an arm whose literal `/.vfs` head lifts
the meta exclusion for that subtree — consistent with
expansion-first (the arm is what the caller now means). ADR 031 §5's
bypass law otherwise unchanged.

## Declined and deferred (recorded with rationale)

- **Case-insensitive path matching (`--iglob`)** — *deferred to
  research*: the one gap that cuts semantics, not spelling
  (collation-aware SQL prefilter variants per dialect; a case
  posture for residuation's component matching at mount seams).
- **Plural `patterns=` on the public verb** — *declined*: one
  pattern is the verb's subject; braces express the common unions;
  the seam's `patterns` tuple is dispatch plumbing, not contract.
- **Backslash escapes** — *declined*: ambiguous against names that
  really contain backslashes; class notation escapes every
  metacharacter.
- **POSIX classes (`[[:alpha:]]`)** — *declined*: no engine support
  in `glob.translate`, no observed demand, ranges cover the cases.
- **gitignore trailing-slash (`foo/`)** — *declined* in favor of
  decision 5; the defect gate keeps refusing the spelling loudly.
- **`{1..3}` numeric ranges** — *deferred*: bash-only in the field;
  `[1-3]` covers the single-digit cases.

## Consequences

- `expand_pattern` + `MAX_PATTERN_ARMS` land public at the
  chokepoint; glob's router dispatch is per-member with any-arm root
  service and reachability; `SupportsPatternSearch.glob` gains
  `globs_not`/`ext_not`/`kind` — the story's one protocol change —
  and the per-arm bind ceiling (`ARM_FIXED_BINDS`) grows to 7.
- Recorded behavior change: `{a,b}.txt` stopped matching a
  literally-brace-named file (greenfield, docs flipped in the same
  landing).
- ADR 032's LIKE-superset study trigger discharged by argument: the
  chokepoint's *ingress* changed (expansion, new defects), not the
  translation — post-expansion no brace reaches the translator.
- Proofs at landing: the brace edition of the differential battery
  (121 case-checks vs `rg -g` across four worlds), the cap-×-1k-roots
  scale row (64,000 members, one glob call + one probe), conformance
  rows for all three channels on all four Docker engine legs.
