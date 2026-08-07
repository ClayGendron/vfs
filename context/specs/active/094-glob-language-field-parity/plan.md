# 094 — Plan: three slices on existing machinery

Implements `spec.md`'s shape. Drafted 2026-08-07 alongside the draft
spec; updated same day to the resolved forks (defect on malformed
braces, no nesting, cap 64, **fetch-to-populate** on chained
unpopulated kind, iglob deferred). Working discipline: tests first;
every slice
lands green (`uv run pytest`, `ruff`, `ty`, coverage 100%); the four
Docker engine legs run at slice B (the protocol-changing slice) via
the `db_test` skill.

## Module layout (decisions)

1. **`src/vfs/pattern_matching/glob.py`** — everything brace-shaped
   lives at the chokepoint, nowhere else:
   - `MAX_PATTERN_ARMS: Final = 64` beside the module constants.
   - `expand_pattern(pattern: str) -> tuple[str, ...]` (new public,
     "Validation and compilation" group): scans left to right,
     tracking character-class state so `[{]` never opens a group;
     collects top-level groups; refuses (via the defect path, below)
     unclosed `{`, bare `}`, `{}`, and a `{` inside an open group;
     cross-products the alternatives; dedupes while preserving first
     appearance; result length > cap raises nothing — it returns the
     arms and the *router* classifies the cap refusal, keeping the
     function pure and the cap policy at the ingress where the other
     refusals live. A brace-free pattern returns `(pattern,)`.
   - `glob_defect` gains the brace clauses so the defect gate stays
     the single refusal vocabulary; `expand_pattern` asserts its
     input is defect-free (same contract as `compile_glob`).
2. **`src/vfs/base.py`** — ingress and chaining:
   - One helper expands-and-gates a pattern channel, **defects gated
     twice**: raw-text check (brace structure + the existing
     defects) → `expand_pattern` → per-arm `glob_defect` (expansion
     can manufacture defects — `x/{a,}` yields the empty-component
     arm `x/`; the refusal names both the arm and the caller's
     source pattern) → cap check (classified `invalid` naming the
     cap and the distinct-arm count). Applied to glob's `pattern`,
     grep's `globs`/`globs_not`, and glob's new `globs_not`.
   - **Glob's dispatch builder rewrites to per-member shape.** Today
     `_glob_dispatches` branches once on the call-level pattern and
     the probe `keep` / `_glob_reaches` predicates take one pattern.
     They move to the `_composed_members` form grep already uses
     (per-pattern `"/" in pattern` inside the loop), with any-arm
     semantics: any arm admits for root service and reachability.
     `keep` also gains the new gates — any exclusion glob, `ext_not`
     entry, or non-matching `kind` rejects the root row.
   - `_glob_dispatches` grows the exclusion composition by mirroring
     `_grep_dispatches`' existing shape (compose each exclusion under
     each root; entry-local render after residuation) — extract the
     shared compose-exclusions-per-root helper rather than copying
     it; both verbs call it.
   - Chained glob: admission = any expanded arm's `compile_filter`
     matches; then exclusion gates and the ext/kind facts. The
     existing `filter_paths` stays the simple public single-pattern
     form; the router's chained branch uses the compiled-gates shape
     directly (it already does for grep via `filter_candidates`).
   - Chained `kind=` fetch: mirror `_grep_rows_in_hand`'s
     absent-content shape — collect rows with `kind is None`, one
     `await self.stat(observations=lacking, columns=frozenset())`
     (identity fields always ride, so the empty projection serves
     exactly `path`/`kind`/`version` — the cheapest possible fetch),
     filter on the fetched kind, pass stat's error rows through
     loudly. Zero storage calls when every row carries `kind`;
     without `kind=` the branch is untouched.
3. **`src/vfs/storage/protocol.py` + `backend.py` + `reads.py` +
   `params.py`** — `glob` gains `globs_not: tuple[str, ...] = ()`,
   `ext_not: tuple[str, ...] = ()`, `kind: ObjectKind | None =
   None`; `params.py`'s glob `PARAM_SPECS` row declares all three
   (kind with its choices vocabulary), mirroring grep's row, or the
   ingress gate never sees them. `reads.py`: `kind` rides **inside
   every pattern arm** (the fan is a pure OR of self-contained arms
   — a conjunct beside it demotes the multi-index OR to a scan;
   caller `ext` and liveness already duplicate per-arm), bumping
   `ARM_FIXED_BINDS` by one; `ext_not` is an exact Python-side fact
   beside the authority gate; `globs_not` compiles once per call and
   gates candidates in the same Python authority pass that already
   runs `GlobFilter.matches` — no SQL rendering for exclusions.

## Mechanics pinned here (the spec delegated these)

1. **Expansion is pre-anchoring.** `expand_pattern` runs on the raw
   caller text; each arm then anchors/canonicalizes independently.
   `{src/a,b}` therefore yields one path-arm and one name-arm, and
   the per-pattern name-vs-path dispatch does the rest — no
   mixed-arm special case anywhere downstream.
2. **Dedupe after expansion, not before dispatch.** `{a,a}` → one
   arm at the chokepoint; the dispatch layer keeps its existing
   behavior for identical composed members.
3. **Cap is counted post-dedupe** — the refusal names the *distinct*
   arm count, so `{a,a}` never trips it.
4. **Exclusion evaluation order in `reads.py`:** admission
   candidates first (SQL prefilter + authority), then `globs_not`
   compiled gates, then `ext_not`, then the `kind` predicate is
   already in SQL. Order chosen so the cheap exact facts run last on
   the smallest set; no correctness dependence on order.
5. **Chained-grep parity check:** grep's chained branch gains brace
   expansion on its `globs`/`globs_not` through the same ingress
   helper — no drift between the storage path and the chained path.
6. **Conformance placement:** brace and exclusion rows go in the
   storage contract battery (they cross the seam); chained-filter
   rows go in `tests/base/` beside the ADR 034 rows; `expand_pattern`
   unit rows in `tests/pattern_matching/test_glob.py`.

## Slice order and landing checks

- **A — braces.** Chokepoint function + defects + cap + ingress
  wiring + chaining + docs-adjacent notebook cell (optional).
  Red-first: the expansion battery and two namespace rows
  (`*.{ts,tsx}` scoped and chained). No protocol change; sqlite
  suite only.
- **B — channels.** The one protocol signature change with verb,
  composition, backend, and chaining wiring; conformance rows for
  `globs_not`/`ext_not`/`kind`; **four Docker legs green before the
  slice closes.**
- **C — proof and true-up.** Differential rows vs `rg -g` brace
  behavior; the 10k-root cap-expansion scale row; docs flip
  (`reference/glob-patterns.md` brace + channel sections,
  `explanation/glob-language.md` gaps shrink); open-questions entry
  → resolved-by-094 for gaps 1/2/4/5.
