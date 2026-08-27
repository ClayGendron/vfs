# 045. The Bounded Pushdown: True Bind Accounting, a Fan-Budgeted Channel, and Over-Limit as a Permanent Defect

- **Status:** accepted 2026-08-18 — the decision set of spec 108 with
  the true-ups of specs 115 and 116, written at the 107–116 mining
  pass (2026-08-19). Applies CLAUDE.md's scale law to grep's
  candidate fetch and the pathterms allow-list; ADR 040/041's
  nomination shapes stand.
- **Date:** 2026-08-18
- **Deciders:** Clay Gendron (the "one spec per defect class" landing
  rule and the decision pass); the §2 shape chosen by measurement.
- **Context source:** the 2026-08-18 review campaign
  (`../research/2026-08-18-glob-grep-review-campaign.md`, findings 2
  and 3 — both executed live: MSSQL 07002 at 32 ext values, sqlite's
  expression tree dying at 499 globs, Oracle `per_chunk` collapsing to
  1 at 400 arms) and the remediation-landing review's findings 4 and
  Q1. Implemented by specs 108, 115, 116.

## Context

The 104/perf arc added a candidate-fetch pushdown (ext membership +
channel facts) and a per-arm allow-list loop beside statements that
already chunk by declared budgets — but the pushdown charged an
expanding `IN` at 2 binds regardless of width, rendered the admissions
channel as one unchunked `OR`, and the allow-list issued one statement
per arm with no count bound and no deadline. Each grew with caller
input; the tightest engines broke first.

## Options considered

- **§2a union-per-chunk** (the scan tier's precedent) vs **§2b void
  the ride** when the channel exceeds one fan chunk — measured on the
  linux store's arm ladder (1/64/504/2,000 arms): no material winner
  inside ~10 % noise, so §2b landed by the simplicity default.
- **Derive the base charge through `_static_binds`** vs a directly
  pinned constant — declined: the base facts include an expanding
  membership, which `_static_binds` refuses by contract.
- **Thread the live dialect into `_static_binds`** vs pin the
  default-compiler invariant — pinned (count-identical on five bundled
  dialects × six profiles; divergence would need a dialect overriding
  bind *cardinality*, which none does).

## Decision

1. **Every pushdown statement is budget-bounded regardless of caller
   input, under one arithmetic that charges true costs.** The pushdown
   carries its bind spend as built (`ExtMembership.binds` at element
   width, channel facts counted as built, static predicates at
   executed-parameter count via `render_postcompile`); the whole ride
   is capped at half the membership budget so the id chunk always
   keeps room. The law is *charged == executed*, pinned per dialect.
2. **The counting convention is one arithmetic with term-typed
   counters, not one function.** Four sites each own a different kind
   of term — `base_binds` (the kind membership, element width),
   `_channel_facts`' as-built increments, `_CHANNEL_ARM_BINDS` (the
   per-arm ceiling), `_static_binds` (executed count of
   dialect-count-invariant predicates) — and each is pinned against
   its executed width. Spec 108's "one mechanism, not two" is read as
   this: one law, no compile-registry re-derivation; a fifth counter
   would trigger consolidation.
3. **The channel fan is one figure, derived once.** `fan_arms =
   arm_budget(profile, parameter_budget, _CHANNEL_ARM_BINDS)` is
   computed in `grep_rows` and passed to both consumers under a name
   that states its unit; a channel wider than the fan voids the ride
   (fetch unfiltered, `_passes_gates` rejects) and voids allow-list
   pruning whole — never a partial union, which would under-nominate.
4. **The pushdown may weaken, never wrong.** Narrowing is a
   convenience; recall is never spent to stay under a cap.
5. **Over-limit is never retry-shaped.** SQLSTATE class 07 joins class
   42 as a permanent defect (`internal`/`invalid`, never
   `unavailable`); sqlite's generic code stays an operating condition
   as the honest residual.

## Consequences

- sqlite serves 499- and 2,000-glob channels; MSSQL's saturated 40-ext
  fetch lands 33 binds under cap at the maximum chunk; the former
  `per_chunk` collapse is unreachable.
- Any new predicate riding the fetch must arrive with its bind count
  and a charged-equals-executed pin; any new fan consumer takes
  `fan_arms`, not a fresh `arm_budget` call.
- The allow-list union stays corpus-width in Python memory (the
  acknowledged suboptimality recorded in `pathterms`' docstring, spec
  111); the SQL-side join is the named future direction, no cap
  implied.
- The full MSSQL error-classification audit and a compiled ext
  predicate for 32+-value channels remain their own tasks.
