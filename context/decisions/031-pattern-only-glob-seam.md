# 031. The Pattern Is the Whole Query: Pattern-Only Glob Seam, Batched

- **Status:** accepted 2026-08-04 — ratified by Clay in session
  after the confirm pass (ext arity committed, probe separate and
  concurrent, interim assertion fix landed, probe stated as the
  general fan-out law scoped to glob) and the executable routing
  walkthrough. Drafted 2026-08-01 from Clay's framing (the rg
  formulation, below). Amends ADR 030 decision 3 (dispatch shape:
  "no protocol change" is withdrawn) and completes its §6; every
  ADR 030 *semantics* decision (namespace coordinates, residuation,
  roots as assertions, gitignore-exact anchoring) stands unchanged.
  **Spec 092 owns implementation.**
- **Date:** 2026-08-01
- **Deciders:** Clay Gendron
- **Context source:** the five-lens verified review of commit
  `e628fb1` (the 073+091 landing). Its surviving major: a scoped
  path-arm glob dispatches one storage transaction per scope root —
  measured 4–17× slower than the batched name arm at 10k roots on
  live engines, and through a 5 ms link it exhausts the session pool
  and returns a failed, partial result. Related verified findings:
  a merged result can be internally torn across per-root snapshots
  (a concurrent committed move surfaced one file at both paths in a
  single result), and subsumed roots re-scan rows purely to discharge
  their existence assertion. Interim harm reduction is landed (root
  dedup, a session bound of 8, linear merge fold); this ADR decides
  the real shape. A live routing walkthrough (2026-08-04,
  `../research/studies/2026-08-04-adr-031-routing-walkthrough/`)
  added a fourth verified finding: **name-arm subsumption silently
  dropped a covered root's find-operand assertion** — a bogus root
  under a covering sibling region returned success. Fixed in the
  interim the same day (the name arm now dispatches both arms like
  the path arm); decision 4's probe is the structural fix.

## The deciding argument

Clay's formulation: **the pattern is the whole query.** When
`rg -g '*.py' /a /b /c` descends into `/a`, the predicate applied
inside that tree is just the glob — no directory operand survives
into the matcher, because *being inside `/a` already is the routing*.
The scope root's confinement job dissolves into the pattern's literal
prefix; what remains of the root is an assertion ("this place
exists"), which is not a query concern at all.

The landed implementation kept both channels alive at the storage
seam — the pattern (now root-relative per ADR 030 §6) *and* the
per-root anchor — and paid for the duplication in transactions: the
storage contract's single `pattern: str` slot forces one dispatch per
root the moment each root carries its own effective pattern. The
per-root *pattern* is semantics; the per-root *transaction* was only
ever an artifact of a one-pattern signature.

Field precedent is uniform on the matcher side: find and ripgrep
evaluate root-relative predicates inside one traversal; zoekt shards
receive pure predicate trees with routing upstream; gitignore
matchers hold patterns, never scopes. No studied system turns N roots
into N wire calls. The batch-of-patterns wire shape has in-house
precedent too: grep's `globs`/`globs_not` are already
`tuple[str, ...]` in the storage protocol.

## Decisions

### 1. The glob storage seam is pattern-only

The router never sends scope roots to storage for glob. Scoping
crosses the seam only as pattern text — the composed, residuated,
entry-local patterns whose literal prefixes confine candidates
exactly as the anchor fan did. The storage glob contract loses
`paths` and gains the batch form (decision 2); `observations=`
grouped dispatch is untouched.

### 2. Storage glob takes a tuple of patterns — one call per entry

```python
async def glob(*, patterns: tuple[str, ...], ext=..., max_count=...,
               columns=..., user_id=...) -> Result: ...
```

One protocol call per entry carries every live pattern for that
entry — all scope roots' residuals and every member of a
multi-residual set alike. The backend runs it in **one transaction,
one snapshot** (closing the result-tearing finding), chunking
statements internally by the declared budgets exactly like every
other batch surface: each pattern contributes one OR-arm (its
sargable escaped-prefix LIKE, plus its exact LIKE translation where
expressible), arms chunked by the tighter of bind count and OR
depth. Extension facts split by arity: the **`ext` parameter is
caller intent, one call-level conjunct** — it must hold whichever
pattern matched, and its semantics (case-insensitive, the empty
extension, the kind-free lexical ext law) are inexpressible as
pattern text — while a **derived extension is a per-arm conjunct**
inside its own pattern's OR-arm. Per-arm is always sound where a
call-level union is not (one derivation-free pattern kills a global
pushdown), enables dead-arm elimination (an arm whose derived ext
contradicts the caller's `ext` is provably empty and never reaches
SQL), and may hoist to call level as an executor optimization when
every arm derives the same fact. Both charge the bind accounting
the review fixed.
The authoritative verify compiles one regex per pattern and keeps a
candidate matching **any** — the necessary-fact posture of ADR 030
§4 unchanged. `glob_defect` gates every pattern before any row is
touched; one defective pattern refuses the call whole, matching the
batch-refusal posture of the write family.

### 3. The composition rule — scoped name-arm patterns become spatial

Per scope root, the effective pattern is:

- **path-arm** (`/` present): `root` + anchored pattern —
  `effective_pattern` as landed (ADR 030 §6).
- **name-arm** (slash-free): `root` + `/**/` + pattern — the
  gitignore float made spatial, since a pattern-only seam must
  *spell* "any depth" rather than lean on an anchor channel.
  `glob("*.csv", paths=("/a/data",))` composes to
  `/a/data/**/*.csv`; direct-children intent keeps its precedent
  spelling, a leading slash: `glob("/*.csv", paths=(...))`.

**Unscoped** name-arm patterns stay coordinate-free and broadcast
verbatim (ADR 030 §5 unchanged) — the float rule at the storage
layer serves them; composition applies only where a root exists to
compose with. Residuation then derives each mount's members from the
composed patterns exactly as today.

### 4. Root assertions move to a router-side probe

The find-operand law (ADR 023) survives with a cheaper carrier: the
router asserts all scope roots in **one batched point-read per
entry** (the `stat` shape, chunked by the membership budget),
**concurrent with** the pattern dispatch. It is a separate call by
design: probe/glob snapshot skew (a root vanishing between the two)
is accepted — the same race every find-family tool runs against a
live filesystem — and folding assertions into the glob call was
rejected as reintroducing a path channel at the seam. The probe is
stated as the **general carrier of the find-operand law for scoped
fan-outs**: this ADR's spec builds it for glob only, and grep adopts
it at Pass C along with the seam (decision 6). Because assertions no
longer ride query dispatch, they are structurally immune to the
subsumption laundering the walkthrough exposed — every named root is
asserted identically whatever the mount-table shape or arm. From the
probe:

- a missing root is the per-root loud error, exactly as today;
- **the root row itself is matched against the caller's pattern by
  the router** — name-arm against its name, path-arm against its
  namespace path — and included on a hit. This one rule unifies two
  behaviors the anchor channel carried separately (find matches its
  operands: a *file* root matched itself; a *directory* root's own
  row appeared when the pattern hit it) and composition alone would
  lose (`/a/data/**/*.csv` matches strictly below `/a/data`);
- merge pinning derives from the router's own knowledge of which
  entries the named roots' composed patterns reach — a named root's
  entry still fails loud; nothing about pin classes rides the seam.

### 5. The meta bypass restates over literal prefixes

With no meta-addressed anchor to lift the `/.vfs` exclusion, the
rule becomes: **a pattern whose literal prefix is meta-addressed
lifts the exclusion for that subtree** (`_literal_prefix` already
extracts it). `glob("/.vfs/trash/**")` — scoped or not — serves
trash rows; patterns without a meta literal prefix keep the subtree
hidden. This makes the bypass a property of what the caller wrote
rather than of which argument carried it.

### 6. Grep inherits the seam at Pass C

`globs`/`globs_not` are already pattern tuples; they compose and
residuate per mount into the same shape with zero contract motion.
Grep's content pattern remains outside the pattern seam entirely.

### 7. Scale posture

Root count is unbounded at the router (composition and residuation
are cheap string work); **dispatch count is one call per entry
regardless of root count**; statement count grows only with
pattern-tuple size over the chunk budgets; the probe is
membership-chunked point reads. This restores the pre-091 transaction
shape while keeping 091's semantics — and the review's MSSQL
observation (the batched OR fan measured slower than per-root queries
there) becomes a per-dialect chunk-width tuning question inside one
transaction, not a dispatch-shape question. The implementing spec
carries a **benchmark gate**: the batched fan is measured against
per-root dispatch on MSSQL before its chunk width becomes that
dialect's default — "tuning question" must not become an unexamined
regression on one engine.

### 8. Verification: executable precedent

The implementing spec's acceptance harness includes a **differential
battery**: build a scratch tree on the real filesystem, run
`find <roots> -name/-path` (and `rg -uu -g`) over a pattern set, run
vfs glob over the same tree in plain and mounted worlds, and diff.
Unix semantics stop being cited and start being executed. The
deliberate divergences are pinned as the battery's allowlist:
dotfiles match (no default-hidden filtering — `rg -uu` parity, not
`rg` default), no ignore-file consultation, and refusal (not
silent-empty) for defective patterns. Two named cases join the
battery from the review follow-ups: a composed name-arm must hit
**direct children** of its root (`/a/data/**/*.csv` matches
`/a/data/x.csv` — the `**`-matches-zero-segments arm the
canonicalization work proved delicate), and composition can
**manufacture adjacent `**`** (`glob("**/x", paths=...)` composes to
`root/**/**/x`), so canonicalization sits downstream of composition
at the chokepoint. This battery also pins ADR 030
§4's honest limit, which the review exposed: the backend verifies
rendered residuals, so "a residuation bug costs coverage, never
correctness" holds only up to render fidelity — the differential and
placement-invariance batteries are what pin that fidelity.

## Rejected alternatives

- **(anchor, pattern) pairs** (LSP's `RelativePattern` registration
  shape) — two channels where one suffices: the anchor's only
  non-redundant job at the seam was the assertion, and an assertion
  does not belong inside a query call. Every pair is losslessly a
  pattern plus a probe entry.
- **Root-relative semantics on the existing signature** (one
  `pattern` + `paths`, storage anchors the pattern under each root) —
  restores one-call dispatch but keeps the dual channel and gives one
  signature two meanings across layers; cannot carry heterogeneous
  pattern sets (multi-residual members are different patterns for the
  same entry), so the per-residual dispatch survives alongside it.
- **Bounded per-root dispatch** (the landed interim: dedup, session
  bound, linear merge) — fixes the failure mode, not the shape; N
  round-trips at contract scale contradicts the batch posture that
  binds every other surface. It remains the live behavior until the
  implementing spec lands, and its remediations (bind accounting,
  canonicalization, defect gates, the name-arm both-arms assertion
  fix) carry forward unchanged.

## Consequences

- A new spec owns implementation: the protocol signature change, the
  backend batch executor, the router probe, the composition rule,
  the meta-bypass restatement, and the conformance rewrite — scoped
  glob rows move from anchor-channel semantics to composed-pattern
  semantics, with the root-row rule (decision 4) replacing the
  anchor-row-itself and file-anchor rows one-for-one.
- Storage-side "anchor" vocabulary retires with the channel:
  "scope root" is the noun for elements of `paths=` (a router-level
  concept), "anchoring" stays the pattern-position verb; the
  subtree-OR machinery (`_anchor_fan`) is repurposed as the pattern
  prefix fan.
- The router's `paths=` surface is untouched — callers keep roots,
  assertions, and merge pinning exactly as ADR 030 §6 promises; this
  ADR changes only what crosses the storage seam.
- `max_count` keeps merge-order-prefix semantics (the review's
  carve-out); one-transaction-per-entry restores per-entry snapshot
  consistency and removes the subsumed-root re-scan question.
- The landed interim ships until the spec lands. Interim
  remediations (the review's, and the walkthrough's name-arm
  assertion fix) are harm reduction against live contract
  violations, not the shape — nothing else in this ADR is hotfixed
  into the live tree.
