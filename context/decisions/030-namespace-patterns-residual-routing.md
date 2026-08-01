# 030. Namespace-Coordinate Patterns: Residual Routing at the Mount Seam

- **Status:** accepted 2026-07-31 — decided by Clay in session:
  option (b) with the Article 1.4 framing, and decision 6 resolved by
  deriving the API net-new from the prior-art corpus (roots +
  root-anchored filters — the find/rg shape ADR 023 already chose,
  finished) rather than patching the landed signature.
- **Date:** 2026-07-31
- **Deciders:** Clay Gendron
- **Context source:** a teaching session on glob routing surfaced
  that path-arm patterns cross the mount seam verbatim while scope
  anchors rebase — executed repro: with a mount at `/data`, unscoped
  `glob("/data/*.txt")` returns empty success. No ADR, spec, or
  router test pinned the seam; the verb docstring ("match against
  the namespace") contradicted the emergent behavior. Research:
  `../research/2026-07-31-glob-pattern-seam-routing.md` (five
  prior-art studies); spike:
  `../research/studies/2026-07-31-glob-residuation/verify_residuation.py`
  (5,590 cases, exact equality, mutation-audited).

## The deciding argument

The field does not decide this — the constitution does. No studied
system pushes a pattern across a mount/server/repository boundary,
because every one of them dropped at least one of vfs's two bets:
a transparent unified namespace (Article 1.4: a mount composes the
namespace and MUST NOT change path semantics) and server-side pattern
evaluation (the 072/073 SQL pushdown, mandatory at the 10k-batch
production posture). Under entry-local patterns,
`glob("/data/**/*.py")` returns different results depending on
whether `/data` is a mount or a plain directory — mount placement
becomes observable through the pattern language, which is precisely
the semantics change Article 1.4 forbids. Namespace-coordinate
patterns are therefore not a convenience feature; they are the
transparency invariant applied to the one verb family where callers
supply patterns rather than paths. The honest counter-position is
recorded under *Rejected alternatives*.

## Decisions

### 1. Patterns are namespace-coordinate

A glob pattern (and, when Pass C lands, grep's `globs`/`globs_not`
filters) matches against the one unified namespace. Results are
invariant to mount placement: binding a subtree to different storage
never changes what a pattern matches. This makes the glob docstring's
"match *pattern* against the namespace" true rather than aspirational.

### 2. The router routes patterns by residuation

For each mount, the router computes the pattern's **residual** — the
segment-wise derivative of the anchored pattern's components by the
bind path's segments: a literal or wildcard component consumes a
matching mount segment; `**` both survives consumption and may match
zero components; character classes consume like wildcards. The
residual set drives dispatch:

- **Dead (empty set):** the mount cannot hold a match — no dispatch.
  This is routing, like a scope that names no entry, not a capability
  gap: no skip record is minted.
- **Live residuals:** dispatched to the mount as ordinary entry-local
  patterns.
- **Empty-tuple residual** (pattern exhausted exactly at the bind
  point): the match is the stored mount-point row, owned by the
  parent storage; it contributes no child dispatch.

Residuation is component-aligned by construction — never a byte-level
prefix slice (the ignore crate's lenient strip is the recorded
anti-pattern). Verified exact — soundness and tightness — by the
spike: unified-namespace matches equal the union of entry-local
residual matches on every one of 5,590 structured cases.

### 3. Dispatch shape: N entry-local calls, existing machinery, no protocol change

A mount whose residual set has more than one member receives one
dispatch per residual; results merge through the existing fan-out
merge (value-identity dedup already handles overlap). The spike
bounds the cost: residual sets never exceeded 2 (269/261 multi-
residual dispatches across ~5,600 patterns × 5 tables), and the bound
is structural (adjacent-`**` ambiguity). `SupportsPatternSearch` is
unchanged; backends stay mount-agnostic and receive residuals as
ordinary patterns in their own coordinates.

### 4. The residual is a necessary fact, never an authority

Residuation routes and rebases; it decides no match. The backend's
authoritative verify (Python `re` over the compiled pattern) runs
unchanged on every candidate — the globset posture, where necessary
facts prune and sufficient facts are someone else's job. A residuation
bug can therefore cost coverage, never correctness of returned rows;
the conformance suite owns coverage (tightness rows), the spike owns
the algebra.

### 5. Name-arm patterns are coordinate-free

A slash-free pattern matches leaf names at any depth and crosses the
seam verbatim — unchanged, and consistent with the gitignore
convention where slash-free patterns float (073's anchoring rule owns
the path-arm/name-arm split).

### 6. The verb shape: roots + root-anchored filters (the find/rg shape, finished)

Derived net-new from the prior-art corpus rather than inherited. The
studied glob APIs collapse into two archetypes: **"the pattern is the
path"** (shells, fsspec, absolute `glob.glob` — one argument whose
literal prefix is the root) and **"roots + filters"** (`find ROOTS
-name/-path`, `rg -g GLOB ROOT`, `pathlib`'s `root.glob(pattern)`,
CPython's `root_dir=`, LSP's `RelativePattern{baseUri, pattern}`,
Bazel). No tool has the landed hybrid — an absolute-but-entry-local
pattern plus an orthogonal scope with undefined interaction — and
every ecosystem ships **both** archetypes side by side (`ls
/data/*.txt` beside `find /data -name '*.txt'`) under one underlying
rule. vfs had already committed to the find shape — ADR 023 pinned
`paths` to POSIX find-operand semantics, and the name-arm/path-arm
dispatch is `find -name` vs `find -path` — leaving only pattern
coordinates undecided. Prior art answers that unanimously: **filters
resolve relative to each root.**

Pinned:

- The pattern is anchored under **each scope root** by 073's
  gitignore-exact rule: `glob("src/*.py", paths=("/data",))` means
  `/data/src/*.py`; slash-free patterns float by name (`find
  -name`); leading `**/` is the explicit any-depth form.
- The default root is `/`, so unscoped calls are namespace-absolute
  exactly as decision 1 requires — and archetype 1 falls out for
  free: `glob("/data/**/*.py")` with no `paths` is the shell/fsspec
  idiom, its literal prefix routing via residuation. Both idioms,
  one rule.
- Mechanically: anchor under each root, then residuate (decision 2).
  Below the router nothing changes — backends receive entry-local
  patterns; mount transparency holds because the effective pattern is
  namespace-resolved before the seam.

**Why `paths` survives at all**, given a pattern can now carry its
own scope — recorded so the next reader need not re-derive it. Roots
are *assertions*; patterns are *predicates*:

1. A missing root is a per-anchor **error** (ADR 023's find-operand
   semantics); a pattern matching nothing is clean empty success and
   cannot distinguish a typo'd directory from an empty one. Named
   roots also pin the merge loud (a named entry that cannot answer
   fails loudly; unscoped branches demote) — intent the router can
   only see when the caller names the region.
2. Multiple disjoint roots compose in one batch call
   (`paths=("/data", "/logs")`); the pattern grammar has no
   alternation, so a pattern cannot express a root union. The ETL
   batch contract makes this first-class.
3. Roots are literal and immune to glob metacharacters in names
   (glob has no escape syntax — the reason CPython ships
   `glob.escape`); a directory named `data [prod]` is addressable
   only literally.
4. `observations=` — `paths`' mutually-exclusive sibling — is the
   chaining surface (glob over a prior result's rows); patterns
   cannot consume prior results.
5. It is the universal ecosystem shape: where-to-look (literal,
   existence-checked) separated from what-to-keep (predicate).

Scoping purely by pattern is fully supported; the caller merely
trades away the existence assertion.

**What this changes vs. the landed behavior:** a scoped path-arm
pattern is read root-relative, not mount-root-relative —
`glob("/x/*.py", paths=("/data",))` becomes `/data/x/*.py`. This also
repairs a latent incoherence: today a scope *deeper* than the mount
root composes absolute entry-local patterns and scope filtering into
a silently vacuous intersection.

### 7. Grep symmetry, content patterns excluded

`globs`/`globs_not` residuate identically per mount when Pass C
lands — they are path patterns and face the same seam. Grep's
*content* pattern is not a path pattern and is never residuated.

### 8. Discharge optimization: recorded, demand-gated

A residual of bare `**` proves every row in the mount satisfies the
path constraint; the dispatch could drop the pattern filter entirely
(zoekt's `Const{true}` discharge). Not built until a workload shows
the filter cost matters.

## Rejected alternatives

- **Entry-local patterns + helpful refusal (option (a))** — viable
  and industry-shipped: LSP's `GlobPattern = Pattern |
  RelativePattern` is this design as a negotiated wire contract, and
  ripgrep's search-root model is its CLI shape. Rejected because it
  surrenders Article 1.4: mount placement becomes observable through
  pattern behavior. If that invariant is ever relaxed for the pattern
  language, this is the fallback, and PostgreSQL is the precedent for
  the posture — it built the LIKE-prefix derivation
  (`like_support.c`) and deliberately declined to consume it for
  partition pruning, requiring clauses in the container algebra
  instead.
- **Rebase the path, not the pattern** (the ignore crate: N matchers,
  N independent path rebases, zero pattern rewriting) — fails vfs's
  pushdown requirement: the prefilter runs inside backend SQL against
  entry-local rows, and storage is deliberately mount-agnostic; rows
  would have to travel to the router before the pattern could see
  them.
- **Caller-side enumeration** (shells, glibc, FUSE, pyfilesystem2's
  MountFS walk) — correct by construction and structurally incapable
  of pushdown; forecloses the production posture.
- **Boundary-opaque patterns** (Bazel: glob never crosses a package;
  crossing is a separate primitive returning container handles) —
  encodes ownership semantics vfs mounts do not have; mounts are
  composition (Article 1.4), not claims.

## Consequences

- The router grows one pure function (`pattern_residual`, reference
  implementation in the spike, ~40 lines) and a residuation step in
  the fan-out classifier; `_classify_fanout_scopes`' region machinery
  is reused unchanged for scope routing.
- Spec 091 owns the implementation, test-first: the 14-case seam
  table as unit rows on the pure function, dispatch tests asserting
  which mounts receive which residuals (including never-dispatched
  dead mounts), conformance rows over the unified tree, and the spike
  re-run against the landed function as the acceptance gate.
- Sequencing: 073 lands first (091 consumes its `patterns.py`
  chokepoint and anchoring rule); the unscoped-absolute-pattern
  silent-empty behavior documented in `open-questions.md` remains
  until 091 lands and is fixed by it, not papered over in 073.
- `base.py`'s glob/grep docstrings state the seam contract in one
  line each when 091 lands; the conformance suite pins mount-
  placement invariance (same tree, same pattern, mount vs plain
  directory — identical results).
- Observation from the survey, demand-gated: every mature glob
  surface pairs include with exclude patterns (`rg -g '!…'`,
  VS Code `findFiles(include, exclude)`, Bazel, grep's own
  `globs_not`) while vfs glob has only `ext`. A `globs_not` on glob
  is a natural follow-up once a consumer asks; it inherits this
  ADR's coordinates and 073's anchoring unchanged.
