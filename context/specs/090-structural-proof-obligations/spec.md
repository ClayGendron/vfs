# 090 — Structural proof obligations: one chokepoint per coherence proof

- **Status:** round 1 landed 2026-07-26 as `0c200b4`; round 2 —
  remediation of that landing's review (2 major, 8 minor, all
  adversarially confirmed), owned by §Round 2 below — landed
  2026-07-26 (uncommitted on `main`; all four engine legs green,
  every named mutation killed, the first-touch real-lock repro
  classifies and recovers, coverage at parity). Next: the
  backward-flow mining pass, then deletion.
  One scope note: `_execute_copy`'s insert chunking stays on
  `rows_per_statement` under decision 3's executemany carve-out (it
  executes per-row dicts with no hidden binds; SQLAlchemy's
  insertmanyvalues re-chunks it against the dialect cap internally).
- **Evidence:**
  `context/decisions/029-proof-obligations-are-structural-not-disciplinary.md`
  (the ratified doctrine this spec implements);
  `context/research/2026-07-26-prior-art-namespace-concurrency-audit.md`
  (kernel/DB-filesystem/OCC prior art behind each decision). Review
  findings cited inline below were adversarially verified with live
  repros: the adopt torn-path corruption (natural timing, Oracle,
  public API, torn on round 2/120 across three runs; parent-version
  facet deterministic 25/25 on MSSQL and Oracle), the MSSQL parent-bump
  overflow (1048-ok/1049-fail, driver error 8003), and the Postgres
  exhaustion misclassification (16-writer storm: 84/128 outcomes
  `unavailable` with raw driver text vs MySQL's clean `conflict`).
- **Depends on:** specs 087, 088, 089 (landed 2026-07-26).

## Problem

The landed race machinery is empirically sound wherever it is applied
— the review traced every guard, claim, and redrive to its contract —
but its coherence proofs are discharged by per-callsite discipline,
and each new code path re-runs the same gamble. The adopt arm (087
decision 2) forgot the one obligation nothing forced it to remember —
re-registering the adopted parent's bump — and shipped the exact
torn-namespace corruption the campaign existed to close. The bump
chunker predicted its statement's bind count by hand and drifted from
the compiled reality by one fixed bind — failing whole batches at
exactly 1,049 parents on MSSQL, inside the supported 10k contract.
The retry loop judges Postgres 40001 retryable on the way in, then
lets a different classifier report its exhaustion as `unavailable`
with raw driver text. ADR 029's finding: every one of these is the
same defect — a proof held at a different site from the evidence that
discharges it — and every surviving prior-art system holds each proof
at exactly one site.

## Decisions this spec owns

1. **Child-attaching mutations affirm their parent structurally**
   *(closes the adopt torn-path critical and the spurious-grandparent
   minor).* The write execution path derives, at execution time, the
   set of committed parent directories that any staged row attaches a
   child to — including parents acquired by arbitration (`adopt`,
   `absorb`) — and emits one verified write against each such parent
   row inside the same transaction (the existing guarded bump; a
   verified no-op touch where no observable version change is owed).
   The adopted parent's `(entry_id, path)` is learned at adoption time
   and carried, so the bump resolver never depends on the committed
   snapshot containing the row. Registration of bumps as a
   staging-time side effect is deleted, not patched: staging declares
   *facts* (which rows attach where); execution derives *obligations*
   from the final staged states. An adopted create that changed no
   membership registers no bump for its own site's parent chain beyond
   the children it actually attaches — restoring the sequential parity
   087 promised (the `unchanged` mkdir bumps nothing).
2. **One retry-exhaustion channel** *(closes the Postgres
   classification major).* `with_retry` owns exhaustion: when its
   predicate judges an outcome retryable (native driver error or
   `StaleSnapshot`) and attempts are spent, it raises the one semantic
   signal — `StaleSnapshot` carrying the original as `__cause__` plus
   attempt count — and the backend's existing `except StaleSnapshot`
   arm becomes the single exhaustion classifier for both channels:
   retryable `conflict`, clean text, never raw driver text.
   `classify_failure` serves only non-retryable failures. Reads keep
   their current path (a retryable read failure redrives the same way;
   an exhausted one classifies through the same arm).
3. **Bind budgets are measured at one chokepoint** *(closes the MSSQL
   overflow critical and its two slack-surviving siblings).* A shared
   `statement_budget` helper in `dialects.py` computes rows-per-chunk
   from the compiled statement's actual bind registry: compile a
   probe statement on the live dialect, take
   `fixed = len(compiled.bind_names) − probe_rows × per_row_width`,
   and chunk at `(parameter_budget − fixed) // per_row_width` —
   SQLAlchemy's insertmanyvalues formula generalized. All three
   hand-arithmetic sites adopt it (`_bump_by_values`,
   `_values_update`, `_execute_copy`'s insert chunking). *(Amended in
   round 2, matching ADR 029's amendment: the originally promised
   execution-seam budget assert was superseded by the measurement
   itself — a future fixed bind is measured and subtracted, not
   predicted; the structural check that lands is the helper's own
   width-drift `AssertionError` over a genuinely duplicated probe
   row.)* `rows_per_statement` remains for executemany paths
   (per-row dicts carry no hidden binds); `_FILTER_BIND_RESERVE`
   stays for `IN`-list predicates, documented as serving that class
   only.
4. **Review remediation riders** *(the surviving minors land with the
   spec so the tree exits review-clean).*
   - `already_exists`/`wrong_kind` convention completed: transfer's
     `not_empty` rung (and its `unaddressable` and root-refusal
     neighbors) stamp `target=` like every sibling rung.
   - `_incoherent_row` mints its error through `classified()`.
   - Docstring truth: `sweep_rows` and the module docstring cover the
     unconditional orphan-reclaim pass; `_execute_copy` records why a
     mid-window rival child merges where move refuses (equivalent
     serial history; copy destroys nothing); the races-suite
     docstring drops its spec-number citation.
   - The four missing pins, shaped per the verifiers' corrections:
     a relocated-absorb unit pin (occupant UPDATEd to a new path →
     `StaleSnapshot`); a conformance pin asserting the
     `data["target"]` *values* when two trash rows refuse onto one
     occupied dest; `retryable is True` assertions at the three
     existing conflict-pin sites; a monkeypatched-dialect end-to-end
     test proving a write whose parent bump cannot be verified
     refuses `unsupported` and commits nothing.

## Acceptance criteria

- The adopt corruption repros, re-staged at tip, end honestly on all
  four engines: the natural-timing Oracle storm (120 rounds × 3 runs)
  produces no torn row and the integrity audit passes; the
  deterministic version-facet repro shows the adopted parent's version
  moving exactly as the sequential baseline does, on MSSQL and Oracle;
  the races suite gains pins asserting parent versions and depth-2
  integrity under the adopt arm.
- A single write batch touching ≥1,049 distinct pre-existing parent
  directories succeeds on MSSQL; the boundary is pinned (unit-level
  compiled-bind arithmetic plus an engine-legged batch test); the
  execution-seam budget assert is exercised by a deliberate-overflow
  unit test.
- A 16-writer Postgres storm through the public API reports lost races
  as retryable `conflict` with clean text — zero `unavailable`, zero
  raw driver text — matching the other three engines for the identical
  workload.
- Every decision-4 rider lands; the previously surviving mutations
  (drop the read-back path comparison, discard `target=`, drop the
  retryable stamp, discard `_bump_parents`' refusal) now each fail at
  least one test.
- Full suite, `ruff`, `ty` at zero; coverage held; all four engine
  legs green; 10k-batch write throughput within noise of the 089
  baseline (pg 2.33–2.37s / mysql 1.94–1.95s) — decision 1 adds no
  statement to the no-arbitration hot path.

## Round 2 — remediation of the landing review (commit 0c200b4)

The review of round 1 confirmed the central mechanisms but caught the
meta-defect once more at the one call site round 1 did not touch, plus
pin and prose gaps. Round 2 owns:

1. **The exhaustion channel reaches its third caller** *(closes the
   major regression).* `ensure_ready` — the one `with_retry` caller
   round 1 left untouched — gains the same `except StaleSnapshot` arm
   the backend seams carry, returning the same classification
   (retryable `conflict`, clean text, `exc.context` in the message).
   First-touch exhaustion is pinned end-to-end: a fresh host whose
   provisioning exhausts retries returns a classified `Result` from a
   public verb, never a raw exception, and its kind matches the other
   two channels.
2. **Probe duplication moves into the helper** *(closes the major pin
   gap at its root and makes the helper's derivation true).*
   `statement_budget` takes the statement builder plus the batch's
   first row and compiles one- and two-copy probes itself — the
   duplication that makes the arithmetic exact is owned structurally,
   not re-remembered per call site — so fixed overhead can no longer
   measure negative and the probe no longer copies the whole batch.
   Two new
   unit pins make the arithmetic's load-bearing terms observable: a
   NULL-undershoot probe (compiled delta < declared width) pinning
   the charge-at-declared-`row_width` divisor, and an even-budget
   case (2,100) that distinguishes the `- fixed` subtraction the
   2,099 pin arithmetically absorbs.
3. **Orphan reclaim is unconditional in fact** *(minor).* The
   retention arm's trash-root-squatter skip no longer returns early:
   the squatter is surfaced as the same warning while the aged-orphan
   reclaim still runs, making the round-1 docstrings true as written.
   Pinned by a combined squatter-plus-orphan test.
4. **The HY000 catch-all defers to the driver errno** *(closes the
   review's MySQL retryable-codes lead, verified live).* pymysql
   exposes the server's SQLSTATE on every error, and MySQL ships
   lock-wait timeout 1205 under the vendor catch-all ``HY000`` — so
   the SQLSTATE rung swallowed the classification and the profile's
   declared ``retryable_driver_codes`` were dead on the whole MySQL
   family (deadlock 1213 survived only because the server sends it as
   40001). ``is_retryable`` now treats ``HY000`` — by ISO definition
   "look elsewhere" — as non-informative and falls through to the
   errno rung. Verified end-to-end on live MySQL: a lock-wait timeout
   through the public write retries and exhausts as a retryable
   ``conflict`` with clean text (previously: zero retries,
   ``unavailable``). The pymysql test double gains the ``sqlstate``
   attribute the real driver carries — the phantom that hid this.
5. **Prose and pin riders.**
   - `StagedEntry.adopt`'s docstring scopes its promise to material
     columns (the bump pass may affirm an adopted parent and refresh
     its version); the `version` field comment adds adopt to absorb
     as post-execution learners.
   - The remaining unpinned `target=` stamps get distinguishing
     assertions: transfer's root-refusal and unaddressable rungs, and
     `_incoherent_row`'s `data["target"]` — completing the round-1
     acceptance criterion that every `target=` mutation dies.
   - The hot-row storm asserts a non-vacuous floor (at least one
     observed conflict) and matches error messages against the three
     vfs-owned templates ("kept losing to concurrent changes",
     "Concurrent modification", "missed their snapshot") instead of a
     two-driver denylist.

### Round-2 acceptance

- The first-touch repro (rival holding the lock through every retry)
  returns a classified retryable `conflict` from a public verb on a
  fresh host; at round 1 it raised.
- Each named mutation now fails at least one test: divisor
  `// row_width` → `// per_row`; delete `- fixed`; drop `target=` at
  the root rung, the unaddressable rung, and `_incoherent_row`;
  revert the `HY000` fall-through.
- A live MySQL 1205 classifies retryable at the unit seam and rides
  the retry-then-exhaust channel through the public write.
- Full suite, `ruff`, `ty` at zero; coverage held; engine legs green.

## Non-goals

- **Row-locking parents or serializing writes with topology** —
  rejected in ADR 029; revisit trigger recorded there.
- **A hard subtree-move ceiling** — ADR 029 decision 5 keeps it a
  documentation obligation until production evidence demands more.
- **POSIX parent-ladder consolidation** (three homes) and the sweep
  anti-join cost profile — filed for the backward-flow mining pass.
- **Storm-harness jitter diversification** (the reviewers' observation
  that 34/34 rounds sampled one interleaving) — a test-infrastructure
  question, filed, not a landing gate here.
