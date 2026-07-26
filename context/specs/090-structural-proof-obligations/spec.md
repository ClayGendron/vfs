# 090 — Structural proof obligations: one chokepoint per coherence proof

- **Status:** landed 2026-07-26 (uncommitted on `main`; all four engine
  legs green, every acceptance repro re-run clean at campaign scale,
  all four previously-surviving mutations now killed, throughput at
  baseline) — awaiting the backward-flow mining pass, then deletion.
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
   `_values_update`, `_execute_copy`'s insert chunking), and the
   execution seam asserts every compiled multi-row statement fits the
   dialect's budget, so any future fixed bind fails loudly in
   development. `rows_per_statement` remains for executemany paths
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
