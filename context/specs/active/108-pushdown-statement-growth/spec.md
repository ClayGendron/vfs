# 108 — Statement growth in the grep pushdown: true bind accounting and a chunked channel

- **Status: drafted 2026-08-18.**
  Born from the review campaign memo
  (`../../../research/2026-08-18-glob-grep-review-campaign.md`),
  findings 2 and 3 (scale lens, both CONFIRMED on live engines) plus
  the allow-list statement-count lead absorbed from finding 3. The
  two defects share one root: the candidate-fetch pushdown grows
  with caller input where every neighboring statement chunks by a
  declared budget.
- **Date:** 2026-08-18
- **Owner:** Clay Gendron
- **Kind:** statement-construction changes inside grep's candidate
  fetch and the pathterms seam, plus an error-classification fix.
  No contract, verb, or Result shape moves; no schema change; the
  pushdown stays a narrowing-only convenience with `_passes_gates`
  the authority.
- **Depends on:** spec 104 (the pushdown and allow-list seam this
  repairs), the dialect budget machinery
  (`membership_budget`/`arm_budget`/`chunked`, spec 093/097 line),
  ADR 041 (the assembly shapes around the fetch).
- **Relates to:** spec 111 (the same `allow_list_ids` gets its
  memory-profile docstring there; the statement-count repair lives
  here), the MSSQL error-classification lead (§4 fixes the two
  observed rows; a fuller audit of the classification table is its
  own follow-up).

## Intent

CLAUDE.md's scale law is that **no statement may grow unboundedly
with batch size or caller input** — the tightest engine caps are the
floor. The review executed two breaches in the grep read path, both
in code the 104/perf arc added beside statements that already chunk
correctly:

1. **The ext-membership ride is charged 2 binds instead of its
   width.** `_predicate_binds` counts bind slots off the compiled
   registry, where an expanding `IN` counts as 2 regardless of
   element count; `_entries_for_docs` sizes its id chunk as
   `membership_budget - _predicate_binds(pushdown)`, so the executed
   statement crosses SQL Server's ~2,100-parameter cap. Measured
   boundary exactly where the arithmetic predicts: 31 ext values
   succeed, 32 fail (error 42000), 35+ surface as retry-shaped
   `vfs.unavailable`. `ExtMembership` was built precisely to pair
   the predicate with its true bind count — `_pushdown_terms` drops
   `ride.binds` and grep re-counts via compile.
2. **The admissions channel renders as one unchunked
   `or_(*arms)`.** No cap, no `expression_depth_budget` consult —
   the profile field whose docstring names exactly this hazard, and
   which the scan tier's fan already respects via `arm_budget` +
   `chunked`. sqlite (the dev default) dies at 499 plain globs
   ("Expression tree is too large"); SQL Server by 1,088 arms; and
   before either cap, arm binds crowd out the id budget — measured
   on live Oracle, 400 arms collapse `per_chunk` to 1, turning one
   candidate fetch into one statement per candidate (0.10 s →
   1.52 s at 300 candidates; 25,000 at full budget).
   `MAX_PATTERN_ARMS` caps per *pattern* by design; the `globs`
   channel is caller-sized and the router multiplies it by scope
   roots (a realistic 8 roots × 63 globs = 504 arms fails today).

Laws that bind the slices:

1. **Every pushdown statement is budget-bounded regardless of
   caller input.** Ext width, arm count, and id chunking share one
   arithmetic that charges true costs; the tightest of the
   parameter, `IN`-list, and expression-depth budgets governs, via
   the existing helpers — no new budget mechanism.
2. **The pushdown may weaken, never wrong.** Narrowing is a
   convenience: when a channel's fan exceeds what one statement may
   carry, the lawful moves are chunk-and-union or drop-to-`None` for
   that statement — both supersets, both re-checked by
   `_passes_gates`. Recall is never spent to stay under a cap.
3. **Over-limit is never retry-shaped.** A statement the engine
   refuses for size is a construction bug (ours) or an impossible
   request (the caller's), not a transient: the observed
   `vfs.unavailable` classifications become `internal`/`invalid`
   truthfully. With laws 1–2 held, the grep path itself should
   never produce one.

## Shape

- **§1 True bind accounting.** `_pushdown_terms` carries each
  predicate with its declared bind count — threading
  `ExtMembership.binds` (and a computed count for the channel
  disjunction) instead of letting grep re-derive via
  `_predicate_binds`' compile-time registry. `_entries_for_docs`
  charges the sum against `membership_budget` when sizing id
  chunks; the `per_chunk` floor of 1 disappears because a pushdown
  too wide to leave id room is handled by §2 before it reaches the
  fetch. `_predicate_binds` goes away or shrinks to the seam that
  owns the count — one bind-counting mechanism, not two.
- **§2 The chunked channel.** The channel disjunction respects the
  same fan budget as the scan tier: arms chunk by
  `arm_budget(profile, parameter_budget)`; a channel that fits one
  chunk rides the fetch as today; a wider channel either unions
  per-chunk row sets (§2a, the scan-tier precedent) or voids the
  ride for that statement (§2b — the fetch runs unfiltered and
  `_passes_gates` rejects, exactly the pre-104 shape). The slice
  picks §2a or §2b **by measurement** on the arm-count ladder (§4):
  §2b is simpler and lawful; §2a wins only if the union's extra
  statements beat the wider unfiltered fetch at real widths. The
  scan tier's existing fan is untouched either way.
- **§3 The allow-list's statement count.** `allow_list_ids` issues
  one self-join per deduped arm in a Python loop — bounded per
  statement but not in statement count (504 sequential round trips
  for the 504-arm shape above). Arms whose term sets fit one
  statement batch through a shared query where the dialect allows;
  at minimum the loop honors the call deadline between arms
  (today it is deadline-blind) and the count is bounded by the same
  fan budget as §2. Memory profile and docstring belong to
  spec 111; only statement shape and count move here.
- **§4 The gates.** Regression tests at the measured boundaries:
  the 499-arm sqlite shape and the 32-ext SQL Server shape succeed
  post-change (db_test leg for the latter; a bind-arithmetic unit
  pin for engines without servers); an arm-count ladder (1, 64,
  504, 2,000) on sqlite pins statement-count and result parity
  against the unfiltered fetch; the 25-row unscoped and 12-row
  scoped ladders re-run with identical counts and no wall-time
  regression (the pushdown restructure touches the hot fetch).
  Classification rows: the former over-cap failures now classify
  per law 3.

## Slices

- **A. Bind accounting.** §1 with its unit pins (charged binds ==
  executed parameters, asserted against compiled statements per
  dialect) and the SQL Server 31/32 db_test leg.
- **B. The chunked channel and the allow-list loop.** §2 measured
  and landed, §3's loop bounded; the arm-count ladder recorded.
- **C. Classification and the record.** §3 of law 3 (the two
  observed rows reclassified, with tests), both benchmark ladders
  re-run, numbers into the status line; spec status updated for the
  mining pass.

## Open questions

- **Where does the ext channel's width stop being useful?** 32+
  ext values is already an odd call shape; if usage mining ever
  shows real callers near the cap, a compiled ext *predicate*
  (LIKE-chain or temp-table join) may beat membership — no evidence
  yet, recorded so the option isn't lost.
- **The full MSSQL classification audit** (which other permanent
  statement defects read as `unavailable`?) is deliberately not
  this spec; two observed rows are fixed here, the sweep is its own
  task.
