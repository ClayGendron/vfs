# 091 — Namespace patterns: residual routing at the mount seam

- **Status: landed 2026-08-01**, same session as 073. All three
  slices green, tests first throughout: the residuation primitives
  in `glob_patterns.py` (unit table then port; spike re-pointed and
  identical — 5,590 cases, zero failures, 261 multi-residual, max
  set 2), the router wiring in `base.py` (12 dispatch rows with
  doubles, then the glob-only residual step + the router-side
  `glob_defect` gate), and the real-storage battery in
  `tests/base/test_glob_namespace.py` (headline flip, placement
  invariance, root-relative scoping, `**`-spanning, bind-point row).
  Full suite 1972 passed, `ruff`/`ty` zero, four Docker legs green.
  One phrasing true-up against acceptance: placement invariance
  holds on the row *set* (compared sorted); row *order* remains the
  pre-existing fan-out merge order (entries in table order), which
  this story deliberately did not change.
  **Mined 2026-08-05:** every decision was already downstream — ADR
  030 (semantics; decision 3's dispatch shape since amended by ADR
  031), the 2026-07-31 seam-routing memo, and the residuation study
  (`../../../research/studies/2026-07-31-glob-residuation/`), which
  stays the permanent acceptance harness. This folder is the
  historical record; nothing here governs current work.
- Previously: shaped and planned 2026-07-31, same session as ADR 030
  (accepted) — all forks resolved there; see `plan.md`.
- **Date:** 2026-07-31
- **Owner:** Clay Gendron
- **Kind:** router contract change (pattern routing at the mount
  seam — no schema change, no storage-protocol change, no backend
  edits)
- **Depends on:** ADR 030 (namespace patterns, residual routing,
  roots + root-anchored filters), spec 073 (the compile chokepoint
  and gitignore-exact anchoring — must land first), ADR 023 (scope
  anchors are find operands), 071 (ingress gates)
- **Relates to:** 072 Pass C grep (its `globs`/`globs_not` filters
  inherit this seam contract — obligation recorded here, discharged
  there), the storage conformance suite

## Intent

The router rebases scope anchors at the mount seam but passes glob
patterns verbatim, so each mount matches the pattern against its own
entry-relative rows. Executed repro (2026-07-31): with a mount at
`/data` holding `a.txt`, unscoped `glob("/data/*.txt")` returns
empty success. ADR 030 decides the fix: patterns are
namespace-coordinate (Article 1.4 — mount placement must not be
observable through pattern behavior), the verb shape is roots +
root-anchored filters (the find/rg shape ADR 023 started), and the
router crosses the seam by **residuation** — the segment-wise
derivative of the pattern by each bind path.

One sentence: **anchor the pattern under each scope root, derive
each mount's residual, skip mounts whose residual is dead, dispatch
live residuals as ordinary entry-local patterns, and merge as
today — making `glob` mean the same thing whatever the mount table
looks like.**

## Shape (pinned — by ADR 030; no open forks)

1. **Namespace-coordinate patterns; placement invariance.** A glob
   pattern matches against the one unified namespace. The binding
   law: the same tree of rows returns the same matches for the same
   call whether a subtree is plain directories or a mount — pinned
   by a conformance row that builds both worlds and compares.
2. **Roots + root-anchored filters** (ADR 030 §6). A path-arm
   pattern resolves under **each scope root**:
   `glob("src/*.py", paths=("/data",))` means `/data/src/*.py`;
   a leading `/` anchors at the scope root; the default root is `/`,
   so unscoped calls are namespace-absolute and
   `glob("/data/**/*.py")` is the one-argument idiom. Name-arm
   patterns are coordinate-free — never joined to a root, broadcast
   verbatim, candidates narrowed by the scope as today.
3. **Residuation lives in `glob_patterns.py`** beside 073's chokepoint:
   pure functions computing the effective pattern per root and the
   residual set per `(effective pattern, bind path)` — literal and
   wildcard components consume matching mount segments, `**` both
   survives consumption and may match zero, character classes
   consume like wildcards. Component-aligned by construction; the
   normative reference is
   `context/research/studies/2026-07-31-glob-residuation/verify_residuation.py`.
4. **Residuals drive dispatch.** Dead (empty set): the mount cannot
   hold a match — **no dispatch and no skip record** (routing, like
   a scope that reaches nothing; not a capability gap). Empty-tuple
   residual: the pattern matches the bind point itself — that row is
   the parent storage's stored mount-point directory; it creates no
   child dispatch. Live residuals: dispatched to the mount as
   ordinary entry-local anchored patterns, in sorted rendered order
   (determinism), one dispatch per residual, merged by the existing
   fan-out machinery — value-identity dedup absorbs overlap.
   Multi-residual sets are bounded tiny (spike: max 2 across 5,590
   cases); `SupportsPatternSearch` is unchanged.
5. **The assertion channel is untouched** (ADR 023). Scope anchors
   keep flowing to owning entries exactly as today — missing-root
   per-anchor errors, file-anchor-matched-itself, loud pinning of
   named entries in the merge. Residuation transforms only the
   pattern; it never replaces the anchor flow. A caller who scopes
   purely by pattern trades away the existence assertion — supported
   and documented, not refused.
6. **The residual is a necessary fact, never an authority.**
   Backends are untouched: they receive entry-local patterns and run
   their authoritative verify unchanged. A residuation bug can cost
   coverage, never row correctness; coverage is pinned by
   conformance and the spike.
7. **Grep obligation recorded, discharged in Pass C.** The
   `globs`/`globs_not` filters residuate identically per mount when
   grep lands; grep's *content* pattern is never residuated. No grep
   code changes in this story.
8. **Not built** (recorded in ADR 030): the `**`-residual discharge
   optimization; `globs_not` on glob. Both demand-gated.

## Verification evidence (2026-07-31)

`verify_residuation.py` checks the exact-equality law — unified-
namespace matches equal the union of entry-local residual matches per
mount — over 5 mount tables (nested three deep, bind-point rows
modeled in parents, shadowed placements excluded) × ~5,600 patterns
covering the full 14-case seam table. Results under the 073 anchoring
rule: **5,590 cases, zero failures; 5,766 dead-mount skips; 261
multi-residual dispatches, max set size 2.** Mutation audit: killing
the `**`-survives arm or the `**`-matches-zero arm fails 230 and 135
cases respectively. The spike is this story's acceptance harness:
re-pointed at the landed functions, claims must stay green.

## Touch points

- `src/vfs/glob_patterns.py` — the residuation functions beside 073's
  chokepoint (see `plan.md` for the pinned API).
- `src/vfs/base.py` — glob's fan-out route: effective-pattern
  computation per scope root, per-binding residuals, dead-mount
  elision, multi-residual dispatch; `_route_fanout`'s generic
  machinery (merge pinning, `row_cap`, skips, hop budget) unchanged.
  The glob docstring's "match *pattern* against the namespace"
  becomes true and gains one line stating the seam contract.
- `tests/base/test_dispatch.py` — dispatch tests with doubles
  asserting which mounts receive which patterns, that dead mounts
  are never called, and multi-residual double-dispatch merging.
- `tests/support/storage_contract.py` + router-level conformance —
  the invariance row and the headline rows (below). Backends receive
  no changes, so backend-leg conformance is unchanged; the new rows
  exercise the router over `DatabaseStorage` mounts.
- `context/open-questions.md`, `specs/STATUS.md` — true-ups at
  landing.

## Acceptance criteria

- **The headline repro flips:** over root rows `{/notes.txt}` and a
  `/data` mount holding `{a.txt, deep/b.txt}`, unscoped
  `glob("/data/**/*.txt")` returns both mount rows and
  `glob("/data/*.txt")` returns exactly `/data/a.txt`.
- **Placement invariance:** the same logical tree built as plain
  directories and as a mount returns the identical match *set* for a
  fixed pattern battery (name-arm, anchored, `**`-spanning,
  dead-prefix); row order is merge order, and a `max_count` prefix of
  it is therefore layout-dependent — pinned as prefix-of-set
  semantics. (Originally written "byte-identical"; trued up at the
  2026-08-01 review remediation.)
- **Root-relative scoping:** `glob("src/*.py", paths=("/data",))` ≡
  unscoped `glob("/data/src/*.py")`; `glob("/x/*.py",
  paths=("/data",))` reads as `/data/x/*.py` (the deliberate
  contract change from mount-root coordinates, per ADR 030 §6).
- **Dead mounts are never dispatched:** call-log assertion — a mount
  at `/other` records zero calls for `glob("/data/**/*.py")`; no
  skip record appears.
- **Multi-residual correctness:** a nested-mount case with residual
  set size 2 (`/data/**/api/*.txt` against mounts `/data` and
  `/data/api`) returns the correct rows exactly once.
- **Assertions survive:** `glob("**/*.py", paths=("/missing",))`
  still yields the per-anchor error; a file anchor is still matched
  itself; named-entry failures still merge loud.
- **`**`-spanning:** `/data/**/*.txt` matches rows inside a nested
  `/data/api` mount (the `**` crosses the boundary).
- **Bind-point row:** `glob("/d*")` matches the stored `/data`
  mount-point directory (served by the parent), with no dispatch to
  the `/data` mount.
- `verify_residuation.py`, importing the landed functions, passes
  all cases; `ruff`/`ty` at zero; full suite green; the four Docker
  legs green (router change exercised over real engines).

## Open questions

None — ADR 030 resolved the fork set. The one deliberate contract
break (scoped path-arm patterns read root-relative, not
mount-root-relative) is pinned in acceptance rather than questioned.
