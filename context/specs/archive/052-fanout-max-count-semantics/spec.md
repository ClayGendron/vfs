# 052 — `max_count` and `limit` Are Per-Terminal, Not Global: Decide and Document

- **Status:** decided and landed — 057 Pass B (2026-07-08) shipped the
  "Both" option: `glob`'s `max_count` and `glean`'s `limit` dispatch per
  terminal **and** re-apply at the merge on every input shape (paths,
  regions, observations). `glob` truncates order-preserving in merge
  order — named scopes first, then mount-table order — untouched by
  stray scores; `glean` trims by score, with the cross-terminal
  comparability caveat documented. `grep`'s `max_count` is per-file
  (ripgrep `-m`) and needs no merge trim. A non-positive bound is
  `invalid`, never a silent no-cap. Recorded in the verb docstrings
  (`vfs/base2.py`); the trim drops silently — a `data` note can come
  later if agents prove to need it. (Shape hardened by the 2026-07-08
  pressure-test run: observation-shaped bypass, score-jump ordering,
  and the `max_count<=0` no-cap hole all found and closed.)
- **Date:** 2026-07-07 (decided 2026-07-08)
- **Owner:** Clay Gendron
- **Kind:** design decision + doc/contract fix (possibly small code)
- **Depends on:** 036 (router verb surface), 045 (verb wire contract —
  wherever caps/limits are promised on the wire)
- **Enables:** callers sizing agent context windows against search
  results they can actually predict

## Intent

Pin down what a result cap means across a fan-out, and make the
router honor the pinned meaning. Today `glob`/`grep` pass `max_count`
and `glean` passes `limit` through to *each* terminal, and
`_merge_results` concatenates without re-trimming: `grep(...,
max_count=10)` over five mounts can return fifty rows; `glean(...,
limit=10)` can return `10 × mounts`. Nothing in the public docstrings
says so — a caller reading `max_count=10` reasonably expects ten rows.

## Why

- The primary consumer is an agent budgeting its context window. A cap
  that silently scales with mount count defeats its purpose exactly
  when the namespace grows.
- For `glean` the divergence is worse than count: each terminal ranks
  by its own scorer, so a global top-k needs a fusion step at the
  merge, not just a trim. Whatever this story decides must not promise
  cross-terminal score comparability the backends don't have.
- Whichever semantics wins, it must be *written* — in the verb
  docstrings and the wire contract — because both readings are
  defensible and silent ambiguity is the actual bug.

## Options

- **Per-terminal (status quo, documented).** Cheap, preserves each
  backend's own ranking, caller does its own `.top(k)`. Cost: the cap
  no longer bounds the response size, and remote hops ship rows the
  caller will drop.
- **Global (router trims at the merge).** `max_count` bounds the
  result. For `glob`/`grep` a plain truncation after merge is
  defensible (matches have no cross-terminal order anyway — document
  mount-table order). For `glean`, trim by score with the explicit
  caveat that cross-terminal scores are only loosely comparable.
- **Both:** dispatch `max_count` per terminal *and* trim the merge to
  the same cap — bounds wire cost and response size in one move. The
  likely winner. `[NEEDS CLARIFICATION]` confirm, and decide whether
  the trim reports that it dropped rows (a `data` note on the result)
  or drops silently.

## Acceptance criteria

- A decided semantics, recorded here and in the `glob`/`grep`/`glean`
  docstrings (and the wire contract if 045 promises limits).
- If global/both: `grep` over N mounts with `max_count=k` returns at
  most `k` rows; a test with two echo mounts pins it. Same for
  `glean(limit=k)`, trimmed by score after merge.
- If per-terminal stands: docstrings state "per terminal; a fan-out
  may return up to `k × terminals` rows" in so many words.
- Scoped and observation-shaped dispatch obey the same rule as the
  unscoped fan-out.
