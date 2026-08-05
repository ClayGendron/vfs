# 032. Glob Pattern Language: Segment Semantics, Gitignore-Exact Anchoring, Pushdown Soundness

- **Status:** accepted 2026-07-14 (owner decision in the 072 slice-7
  design-precedent review; the anchoring rule revised to
  gitignore-exact 2026-07-31). Recorded as an ADR 2026-08-05 at spec
  073's mining pass — the decisions predate the record and were
  carried by the spec until it landed (2026-08-01) and was mined;
  the spec rests in `../specs/archive/073-glob-segment-semantics/`.
  ADRs 030/031 build on this decision set and cite it as "073's
  anchoring rule" / "the compile chokepoint."
- **Date:** 2026-07-14
- **Deciders:** Clay Gendron
- **Context source:** every glob in the pre-073 tree used stdlib
  `fnmatch` semantics — `*` crossed `/`, `?` matched `/`, `**` was
  not special. No one chose this; the memory backend reached for
  `fnmatch` and the conformance suite pinned what it did. The
  2026-07-14 precedent review found zero reference support and four
  references against: fsspec compiles globs through CPython's
  `glob_translate` (`filesystem_spec/fsspec/utils.py:713-742`);
  pyfilesystem2 is segment-aware in both engines
  (`fs/wildcard.py:155`, `fs/glob.py:80` refuses mid-component
  `**`); CPython's `glob`/`pathlib` are the semantics every coding
  agent carries; and this project's own quarry
  (`src2/vfs/patterns.py:79-91`) was segment-aware — the fnmatch
  contract was a regression the rewrite introduced. Caller-visible
  damage (demonstrated): `/docs/*.txt` returned files three levels
  deep, and `/docs/**/*.txt` silently missed `/docs/a.txt` because
  `**/` had to consume a character — over- and under-matching both.

## The deciding argument

Glob must mean what it means in every tool an agent already knows —
`*` within a segment, `**` across segments — compiled at one
chokepoint every consumer shares. An agent-facing namespace whose
pattern language diverges from the shell/gitignore/ripgrep family is
a standing false friend, and the `**/` consume-a-character trap is
silent data loss, the worst failure class a read surface has.

## Decisions

### 1. Segment-aware semantics via CPython `glob.translate`

`*` matches within one segment (`[^/]*`); `?` matches one
non-separator character; `**` as a whole component matches zero or
more components; `[seq]`/`[!seq]` classes; case-sensitive. Hidden
files match (`include_hidden=True`) — this is an agent namespace,
not an interactive shell; the reserved `/.vfs` subtree stays
invisible via liveness scope (namespace policy, not pattern policy).
Consequence: `requires-python` moved to `>=3.13`, where
`glob.translate` lives — the chokepoint wraps stdlib rather than
vendoring a translator.

### 2. One compile chokepoint

`src/vfs/glob_patterns.py` owns the pattern language. Every
consumer — both backends' glob, grep's `globs`/`globs_not` when
Pass C lands, the router's routing primitives (ADR 030) — compiles
there and nowhere else. Compilation happens before any row is
touched; a refused pattern classifies `invalid` naming the defect
(never raises).

### 3. Anchoring is gitignore-exact: any `/` anchors, no `/` floats

A slash-free pattern floats by name (the name arm — `find -name`).
Any `/` in a pattern anchors it: the chokepoint prepends a bare `/`
to a path-arm pattern lacking one, so `src/*.py` means root-level
`/src/*.py`, `*/x.py` means depth one, and any-depth is the explicit
`**/` prefix (`**/x.py` ≡ `/**/x.py`, root level included).

Without the normalization, an unanchored path-arm pattern is legal
but can never match an absolute subject (executed: bare-translate
`*/x.py` matches nothing; `**/*.txt` misses every root-level row) —
the same silent-false-friend class this decision exists to kill.

Decision trail, kept because the first call was wrong: first
resolved as *float* (prepend `/**/`) on the claim that floating was
the gitignore posture; the ripgrep prior-art study showed that claim
wrong for slash-containing patterns — gitignore floats only
slash-free patterns and leaves anything containing `/` root-anchored
(`ripgrep/crates/ignore/src/gitignore.rs:490-525`) — and Clay
revised to gitignore-exact the same day (2026-07-31). Refusing
unanchored patterns (loudest, zero normalization) was rejected: it
punishes the most reflexive agent idiom (`src/**/*.py`).

### 4. Mid-component `**` refuses; name-arm `**` degrades to `*`

`a**b` classifies `invalid` (the fsspec/pyfilesystem2 posture — loud
beats hiding a typo'd recursion). Stdlib will not refuse it
(`glob.translate` silently collapses it to `a[^/]*b`), so the
chokepoint pre-checks components. This also keeps the LIKE fusion
rule (decision 6) trivially safe: only whole-component `**` reaches
it. A `**` in a slash-free pattern is behaviorally `*` for free
(names contain no separator) — no special-casing, pinned by a test.

### 5. Name-vs-path dispatch is load-bearing, and extends to grep

No `/` → match the leaf name; `/` present → match the full path.
Under segment semantics this dispatch stops being cosmetic: a
path-matched `*.py` filter matches nothing (the leading `/` alone
kills it), so grep's `globs`/`globs_not` filters must adopt the same
dispatch as the verb — pinned here, discharged at Pass C.

### 6. The database prefilter is a proven LIKE superset, verify unconditional

The prefilter-then-authoritative-verify structure (zoekt/codesearch
doctrine) is what makes semantics changes safe: the LIKE must be a
*superset* of the authoritative regex — under-matching silently
loses rows before the verifier sees them. The translation: `*` → `%`
and `?` → `_` (deliberately loose — they cross `/` where the glob
does not), a whole `**` component fuses with its trailing separator
into a single `%` (`/docs/**/*.txt` → `/docs/%%.txt` — the fix for
the consume-a-character trap one layer down), LIKE metacharacters
escaped; `[` classes and mid-component `**` fall back to the escaped
literal-prefix LIKE. The verify stays unconditional even where the
translation looks exact — sqlite's LIKE is ASCII-case-insensitive by
default, so an "exact" translation is already a superset on case
alone. Soundness is machine-verified, not argued:
`../research/studies/2026-07-14-glob-like-superset/verify_like_superset.py`
(zero drops over 523k authoritative matches against the landed code;
the spike itself survived a three-agent adversarial audit — ~11.5M
fuzz trials, a 12-mutant mutation audit, and differential testing
against real PostgreSQL 18.0). The spike proves soundness, never
tightness — selectivity is a performance property.

### 7. Extension narrowing pushes down to the indexed `ext` column

Two pure AND-ed narrowings under the same superset doctrine:

- **The `ext` parameter** becomes `ext IN (...)` in SQL (the Python
  check stays).
- **A pattern-derived extension** (`**/*.txt`, `?.py`) narrows as
  `ext = '<derived>' OR name = '<literal dot-suffix>'`. The OR arm
  is not optional: `*.txt` matches the pure dotfile `.txt`, whose
  lexical extension is `None` — a bare equality silently drops it.
  This is what rescues anchor-free patterns: `LIKE '%.txt'` is
  unsargable, but `ext = 'txt'` is an indexed equality.

**The column law is lexical**: `ext` stores `extract_extension` of
the name for *every* kind (a directory named `docs.txt` has ext
`txt`); `paths.normalize_extension` is the one tail law, and the
write path populates the column through the same chokepoint the read
side compares against — the agreement is structural, asserted by
conformance, because the derived-ext pushdown is unsound without it.

### 8. Portability facts worth pinning (from the adversarial audit)

- Postgres errors on a dangling-escape LIKE *data-dependently* —
  some rows error, others silently drop — so "no emitted LIKE ever
  ends in a dangling escape" is a structurally checked invariant of
  the translator, not a style preference.
- SQLAlchemy renders the LIKE ESCAPE character inline (the pattern
  is a bound parameter; the escape char is not), so
  `standard_conforming_strings=off` — deprecated since Postgres
  9.1 — is an unsupported configuration.
- sqlite's ASCII case folding was the only engine divergence found
  anywhere, always superset-ward.

## Rejected alternatives

- **Keep fnmatch semantics** — zero reference support; both over-
  and under-matches segment semantics, so neither is a superset of
  the other and "compatibility" preserves silent data loss.
- **Vendor a translator instead of the 3.13 floor** — the floor
  costs nothing (runtime and `ty` already targeted 3.13); a vendored
  translator is a standing divergence risk against the semantics
  every agent carries.
- **Refuse or float unanchored path-arm patterns** — see the
  decision-3 trail.

## Deferred (recorded, not committed)

Anchor-free patterns without a derivable extension (`**/*rc`,
`**/Makefile*`) defeat both the path B-tree and the ext pushdown and
scan the path column — bounded and correct, just unindexed. The
scale lever is engine-native (`pg_trgm` GIN on the path column,
story 007's schema, Postgres-only, a pure accelerator with zero
contract risk because correctness lives in the verifier). Revive
with the Postgres dialect when a workload demands it; no custom
trigram machinery for paths.

## Consequences

- Implemented by spec 073, landed 2026-08-01 (commit line recorded
  in `../specs/STATUS.md`); the spec was mined into this record
  2026-08-05.
- ADR 030 (namespace-coordinate patterns) and ADR 031 (pattern-only
  seam) both build directly on the chokepoint and the anchoring
  rule; the composition rule (ADR 031 decision 3) is this anchoring
  made spatial.
- The LIKE-superset study is the permanent acceptance harness for
  the translator: re-point and re-run it whenever `_glob_like`,
  `derive_ext`, or the chokepoint change.
