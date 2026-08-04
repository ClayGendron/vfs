# 092 — Pattern-only glob seam: batched patterns and the root probe

- **Status: draft 2026-08-04** — shaped in the ADR 031 ratification
  session, immediately after the confirm pass and the executable
  routing walkthrough
  (`../../../research/studies/2026-08-04-adr-031-routing-walkthrough/`).
  Not started. **Research pass complete and folded** (same day):
  the five-agent field study —
  `../../../research/2026-08-04-batched-glob-seam-field-study.md` —
  confirmed both precedent claims, measured the sqlite fan
  (batched wins ~1.4-2× at every scale, sweet spot ~200
  arms/statement, expression-depth ceiling at 1000), and revised
  the executor rendering rule (ext facts render inside arms; a
  call-level AND beside the fan costs ~350× by killing the OR
  optimization). Awaiting shaping review.
- **Date:** 2026-08-04
- **Owner:** Clay Gendron
- **Kind:** storage-protocol signature change + backend batch
  executor + router dispatch rewrite + conformance rewrite. The
  interim dispatch shape (per-root transactions, session bound,
  both-arms subsumption carve-out) is deleted at landing.
- **Depends on:** ADR 031 (accepted 2026-08-04 — every fork resolved
  there or in its confirm pass), ADR 030 (semantics unchanged), ADR
  023 (the find-operand law this spec re-carries), specs 073 + 091
  (landed — the chokepoint and residuation this spec re-plumbs),
  and the 2026-08-04 field study
  (`../../../research/2026-08-04-batched-glob-seam-field-study.md`
  — the normative source for budgets, rendering rules, and probe
  outcome shape below).
- **Relates to:** 072 Pass C grep (inherits the seam and the probe
  law — obligation recorded here, discharged there), the storage
  conformance suite, the `db_test` Docker legs.

## Intent

The 091 landing gave glob correct namespace semantics with an
interim dispatch shape: one storage transaction per scope root on
the path arm (measured 4–17× slower than the batched name arm at
10k roots, pool-exhausting over a 5 ms link, tearable across
per-root snapshots), and a dual scoping channel whose subsumption
rule silently dropped a covered root's existence assertion until the
2026-08-04 interim fix. ADR 031 decides the real shape: **scoping
crosses the storage seam only as pattern text**, batched one call
per entry in one transaction, and **root assertions move to a
router-side probe** that no dispatch optimization can drop.

One sentence: **compose each root into its pattern, send every live
pattern for an entry in one storage call under one snapshot, assert
every root with one cheap concurrent probe, and delete the interim
scaffolding — same rows, same errors, a fraction of the
transactions, and no channel for an assertion to fall through.**

## Shape (pinned — by ADR 031 and its confirm pass; no open forks)

1. **The protocol.** `SupportsPatternSearch.glob` loses `paths` and
   gains `patterns: tuple[str, ...]`; `observations=` grouped
   dispatch is untouched. Semantics: return rows matching **any**
   pattern (regex authority per pattern, necessary-fact posture of
   ADR 030 §4 unchanged), executed in **one transaction, one
   snapshot** per call. `glob_defect` gates every pattern before any
   row is touched; one defective pattern refuses the call whole
   (the write family's batch-refusal posture). `max_count` bounds
   the call's rows; the router's `row_cap` re-applies after merge as
   today.
2. **Composition, then canonicalization.** Per scope root: path-arm
   composes via the landed `effective_pattern`; name-arm composes as
   `root + /**/ + pattern` (the gitignore float made spatial).
   Unscoped name-arm patterns stay coordinate-free and broadcast
   verbatim (ADR 030 §5). Composition can manufacture adjacent `**`
   (`glob("**/x", paths=…)` → `root/**/**/x`), so canonicalization
   runs **downstream of composition** at the chokepoint. Residuation
   then derives each entry's members exactly as landed; a root
   strictly inside an entry contributes its composed pattern to its
   **owning** entry only (the walkthrough's owner gate — never an
   ancestor's shadowed region).
3. **One call per entry.** All live patterns for an entry — every
   root's residuals and every multi-residual member — form one
   sorted, deduped tuple and one dispatch. Router merge machinery
   (pinning, `row_cap`, skips, zero-progress demotion) is unchanged;
   within an entry, overlap can no longer produce duplicate rows,
   because there is only one scan.
4. **The probe.** One batched point-read per entry (membership-
   chunked), grouped by owning entry, run **concurrently** with the
   pattern dispatches — a separate call by design; probe/dispatch
   snapshot skew is accepted (the find-family race; ripgrep's
   parallel walker and BSD find both stat operands up front, and
   find's readdir-race forgiveness applies only below the roots).
   Per-root outcomes are **three-way** — present / absent /
   undeterminable — with the path carried beside every error (the
   opendal batch-result shape); a backend's inability to answer is
   never coerced into "absent." A root that vanishes concurrently
   (`not_found` racing the dispatch) is tolerated as
   skip-and-continue on the row side while the assertion still
   reports. From the probe: a missing root is the per-root
   `not_found`, and the root's own row is matched by the **router**
   against the caller's pattern — name-arm against its name,
   path-arm against its namespace path — included on a hit. This
   replaces the anchor-channel behaviors one-for-one (file anchor
   matched itself; directory root row on a pattern hit — both
   already pattern-gated in the pinned tests; this is find's
   semantics, deliberately not ripgrep's operand exemption). Merge
   pinning derives from router knowledge of which entries named
   roots reach. The probe is uniform across both arms and immune to
   subsumption by construction.
5. **The backend batch executor.** Each pattern contributes one
   OR-arm: its escaped literal-prefix subtree fan (the `_anchor_fan`
   machinery repurposed as the pattern prefix fan) AND its superset
   LIKE translation. The field study pins the rendering rules:
   - **The WHERE renders as a pure OR of uniform prefix-form arms.**
     Both sqlite's multi-index OR and postgres's BitmapOr are
     all-or-nothing — one non-indexable arm or one stray top-level
     conjunct demotes the whole fan to a scan (measured ~350× on
     sqlite when `AND ext IN (…)` sat beside the fan).
   - **All ext facts render inside arms.** The ADR's semantic split
     stands — the caller's `ext` is one call-level *fact*, a derived
     extension is a per-arm fact — but both are *rendered* per arm
     by distribution ((A∨B)∧e ≡ (A∧e)∨(B∧e)). Dead arms (derived
     ext contradicting the caller's `ext`) drop before SQL. Never
     hoist a conjunct beside the fan.
   - **Chunking budgets**: arms chunk by the tightest of the
     bind-parameter budget (MSSQL 2,099; postgres 65,535; sqlite
     32,766), the `IN`-list cap (Oracle 1,000), and the
     **expression-depth budget** — new to the `DialectProfile`:
     sqlite parses a flat OR left-deep, so height ≈ arms + per-arm
     depth against `SQLITE_MAX_EXPR_DEPTH` 1000 (measured wall: 997
     arms); postgres flattens and has no depth cap. Default chunk
     width **~200 arms** — the benchmark shows the win saturates by
     C=50-200 at every scale, and 200 clears every engine cap.
     Balanced parenthesization (height log₂ N) is the recorded
     escape hatch, not the default.
   - **The plan, not just the SQL, is a conformance concern.** The
     LIKE-prefix rewrite has collation/opclass preconditions
     (sqlite: case-sensitive LIKE or a matching-collation index —
     default LIKE never seeks a BINARY path index, a measured
     100-1000× cliff; postgres: `text_pattern_ops` unless
     C-locale). The profile gains a declared
     like-prefix-index-requirement fact per dialect, and the reads
     tests pin the sqlite plan (multi-index OR preserved).
   - `DialectProfile` additions justified by the study: expression
     depth + whether OR chains accumulate it, a general (non-INSERT)
     bind budget, the compound-SELECT cap (if a UNION rendering is
     ever adopted per-dialect), the LIKE-prefix index requirement.
     SQLAlchemy models none of these.
6. **Meta bypass by literal prefix.** A pattern whose literal prefix
   is meta-addressed lifts the `/.vfs` exclusion for that subtree;
   composition preserves the old anchor-carried bypass
   (`glob("*", paths=("/.vfs/trash",))` composes to a meta-prefixed
   pattern). A wildcard-headed prefix never lifts it.
7. **Interim scaffolding deleted.** The per-residual branch
   dispatches and per-anchor scoped glob dispatches in
   `_glob_residual_dispatches`, the `_GLOB_SESSION_BOUND` semaphore
   and `_gated`, the `op == "glob"` subsumption carve-out in the
   generic fan-out, and the storage-side "anchor" vocabulary
   ("scope root" is the router noun; "anchoring" stays the
   pattern-position verb). Their tests are rewritten against the
   new seam, not deleted — every behavior they pinned survives.
8. **Grep obligation recorded.** `globs`/`globs_not` are already
   pattern tuples; Pass C composes and residuates them into this
   seam and adopts the probe law (ADR 031 D4 as confirmed: the law
   is general, this spec builds it for glob only).
9. **Not built** (demand-gated): probe generalization to other
   fan-out ops; `globs_not` on glob; the `**`-residual discharge
   optimization.

## Verification obligations (from ADR 031 D7–D8)

- **Differential battery** (new spike under this spec's dir): build
  a scratch tree on the real filesystem, run `find <roots>
  -name/-path` and `rg -uu -g` over a pattern set, run vfs glob over
  the same tree in plain and mounted worlds, and diff. Allowlist of
  deliberate divergences: dotfiles match (`rg -uu` parity), no
  ignore-file consultation, refusal (not silent-empty) for defective
  patterns, **and the rg leg's root-row cases** — find tests the
  root itself against the expression (vfs's rule); rg exempts
  explicitly-named operands from `-g` entirely, so the two legs
  disagree on root rows by design. Two named cases: a composed
  name-arm hits **direct children** of its root (`**` matches zero
  segments), and composition-manufactured adjacent `**`
  canonicalizes.
- **Existing harnesses stay green unchanged:** the placement-
  invariance battery, `verify_residuation.py` (identical
  statistics), the conformance suite's glob rows as rewritten.
- **MSSQL benchmark gate:** the batched OR fan measured against
  per-root dispatch on MSSQL before its chunk width becomes that
  dialect's default; result recorded in this spec before archive.
- **Scale row:** 10k roots into one entry → one storage call, one
  probe call, statements chunked within budget (recorded-statement
  assertion on sqlite with a pinned budget, per the 073 idiom).

## Touch points

- `src/vfs/storage/protocol.py` — the glob signature.
- `src/vfs/storage/backends/database/backend.py` + `reads.py` — the
  batch executor; `_anchor_fan` repurposed; ext arity split.
- `src/vfs/storage/backends/memory.py` — the conformance twin.
- `src/vfs/glob_patterns.py` — the composition function (D3 rule);
  canonicalization ordering; `residuals`/`render_residual`
  unchanged.
- `src/vfs/base.py` — the probe, per-entry batch dispatch, interim
  deletion; the fan-out docstrings true up.
- `tests/support/storage_contract.py`, `tests/base/test_dispatch.py`,
  `tests/base/test_glob_namespace.py`,
  `tests/storage/database/test_reads.py` — rewrites per slice B/C.
- `spike/` (this dir) — the differential battery script.
- `specs/STATUS.md`, `../open-questions.md` — true-ups at landing.

## Slices (each landing leaves the tree green)

- **A — pure functions.** The composition rule and
  canonicalization-after-composition ordering in
  `glob_patterns.py`, unit-tabled (including the two named battery
  cases at the unit level).
- **B — the flip.** Protocol signature, backend executors, router
  batch dispatch, and the probe land together (the signature change
  binds them into one landing), test-first: conformance and dispatch
  tests rewritten in the same slice. The walkthrough's gap test and
  `test_roots_stay_assertions` must pass **unchanged** — they pin
  behavior, not machinery.
- **C — deletion and vocabulary.** Interim scaffolding removed;
  storage-side anchor vocabulary retired; docstring true-ups.
- **D — proof.** Differential battery, scale row, four Docker legs,
  MSSQL benchmark recorded.

## Acceptance criteria

- **Call-log:** N roots resolving into one entry produce exactly one
  storage glob call carrying the deduped pattern tuple, plus probe
  point-reads — zero per-root glob calls (doubles, per the
  test_dispatch idiom).
- **Assertions uniform:** the walkthrough's covered-root case stays
  loud on both arms under the new machinery; a missing root is
  `not_found` naming the path; healthy roots still deliver rows;
  the envelope reads failed (find's exit-1 shape).
- **Root-row rule one-for-one:** `test_roots_stay_assertions` passes
  verbatim — file anchor hit/miss, clean-empty pattern, loud missing
  root.
- **No intra-entry duplicates by construction:** the multi-residual
  and covered-root overlap cases return each row once with no
  router-side dedup needed within an entry.
- **Snapshot consistency:** a multi-pattern call executes in one
  transaction (recorded-statement/session assertion); the tearing
  shape — one file at both its old and new path within a single
  entry's rows — is structurally impossible per entry.
- **Placement invariance and `max_count`** keep their landed
  semantics (match-set invariance; merge-order prefix).
- **Meta bypass:** scoped composition into `/.vfs/trash` lifts the
  exclusion; a wildcard-headed prefix does not.
- **Ext rendering observable in SQL:** every ext fact rides inside
  its arm — recorded statements show the WHERE as a pure OR fan
  with no top-level conjunct beside it; a contradicting arm is
  absent entirely; on sqlite the reads tests pin the multi-index OR
  plan surviving the ext facts (the ~350× cliff stays closed).
- **Root-order independence:** the same multi-root call with
  `paths` in both orders returns the same match set and the same
  per-root errors (the ripgrep multi-root regression class).
- Differential battery green with its allowlist;
  `verify_residuation.py` green with identical statistics; full
  suite, `ruff`/`ty`, coverage 100%; four Docker legs green; MSSQL
  benchmark recorded in this spec.

## Open questions

- [NEEDS CLARIFICATION: the probe verb for a glob-capable but
  stat-incapable entry — capability-skip, or a bounded-list
  fallback?] The field study narrowed this to two precedented
  postures: (a) record the `unsupported` skip — opendal's shape,
  where capability-missing propagates as its own outcome (present /
  absent / undeterminable) and is never coerced to "absent"; (b)
  degrade to a bounded list used as a weaker signal (opendal
  `Operator::check`'s limit-1 lister, fsspec HTTP's ls-based
  existence) — precedented, but it cannot distinguish
  empty-from-missing on prefix-semantics backends and should be
  opt-in and observable if built. Shaping-time lean remains (a),
  with (b) demand-gated. Decision is Clay's; resolve in slice B.
  Pointer in `../open-questions.md`.
