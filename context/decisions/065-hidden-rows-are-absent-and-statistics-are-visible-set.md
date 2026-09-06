# 065. Visibility: Hidden Rows Are Absent Everywhere, Refusals Never Confirm Existence, and Search Statistics Are Computed Over the Visible Set

- **Status:** accepted 2026-09-06 (Clay, each option put as a question and
  ratified as written; binds spec 058's `invisible` rung, `glean`, the merge and `grep`). Drafted 2026-09-05 as Phase 3 of the
  principals and permissions research programme
  (`../research/2026-09-05-principals-and-permissions-research-plan.md`);
  companions 062 to 067 were ratified together.
- **Date:** 2026-09-05
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, 2026-09-06). Originally drafted by Claude from study S2
  (`../research/2026-09-05-glean-statistics-leak.md`), lens L4 (the six
  leak classes; Postgres `LEAKPROOF` and `pg_statistic`; SQL Server's
  full-text join "to avoid leaking the primary keys of rows that should
  be filtered"), L2 (`exportfs -P` projection vs `permFile` refusal),
  L1 (`EACCES` on a denied component, never `ENOENT` for a known
  name), L5 (Microsoft's "could not be shared" message vs Claude Tag's
  disabled search) and the Mirage memo's leak rules.

## Context

Spec 058 proposed a three-rung ladder, `invisible < read < read_write`,
and ADR 021 fixed reads as a compiled predicate. What neither said is
what "invisible" must mean for the verbs that compute over the corpus
rather than fetch a row. Study S2 answered it: with global BM25
statistics, a caller who sees half the corpus recovers, for every probe
term, whether it occurs in hidden rows (precision 1.000, recall 1.000)
and its exact hidden document frequency (99 to 100 % exact), from scores,
from ranks alone, and most directly from the merge's exported
`lexical_stats`. The hidden set's size is recovered to within two
documents from two queries. Min-max scaling hides nothing; bucketed or
stale statistics still leak (recall 0.91 and 0.42). Visible-set
statistics close the leak completely at no measured ranking cost
(nDCG@10 within noise on every partition, including the multiplayer
intersection and the per-mount export). This is Büttcher and Clarke's
FAST 2005 result on vfs's own formula and output shape.

The databases name the same class: Postgres refuses to pass
`pg_statistic` values to non-leakproof functions under row security,
and orders security quals before leaky ones; SQL Server adds a join to
full-text ranking for the same reason.

## Decision

1. **A hidden row is absent.** For a caller (or a subject set) that
   holds no rung on a row, the row does not exist: not in listings,
   globs, greps, glean results, edge traversals, `locate`, or
   statistics. A request naming it answers *not found*, the same answer
   an unknown path gets, with the same timing class as far as the
   engine allows.
2. **A refusal never confirms existence.** Denied is a classified
   refusal only for a row the caller can *see* but may not act on
   (Unix `EACCES` on a visible component). Error payloads carry no key
   values, no engine detail, and echo only what the caller supplied
   (L4's error-message rule; Supabase's mapping of hidden to not-found).
   In a group session the refusal is the room's, so it must not
   reveal to any member what another cannot see (Microsoft's "a
   response could not be shared" is the counter-example).
3. **Hide is a projection applied before any lookup; deny is a
   refusal after it.** Two code paths (Plan 9's `exportfs -P` returning
   nil before stat vs `permFile`'s "permission denied").
4. **The visibility predicate runs before any content function.** No
   regex, embedding distance, tokenizer or score touches a row the
   predicate has not admitted (Postgres's leakproof ordering). Where an
   engine cannot order it, the verb must fetch under the predicate and
   compute after.
5. **Search statistics are computed over the visible set, inside the
   query.** `N`, `avg_dl` and every term's `df` for `glean` come from
   the rows the predicate admits for this authority. The cross-mount
   merge exports `lexical_stats` only over the caller's visible rows
   and only for terms a visible row contains; the union fallback is
   the same. Coarsening, bucketing and stale snapshots are not
   mitigations and are not offered. The cost is one aggregated pass
   over the visible postings of the query's terms (about 2.7 × N
   posting rows per SciFact query), memoisable per grant revision.
6. **Reads filter, writes check, and a write that returns the row
   raises.** A read silently omits what is hidden; a write to a hidden
   or denied path is refused with the classified kind; a verb that
   would return the row it wrote never silently drops it (Postgres
   `WITH CHECK` vs `USING`; SQL Server `BLOCK` vs `FILTER`).
7. **For a subject set, hidden from any member is hidden from the
   session** (ADR 066), for rows and for statistics alike.

## Options considered

- **Post-filter results and leave statistics global.** Rejected on
  S2's numbers: the leak is total on every channel.
- **Coarsened or snapshotted statistics without per-caller cost.**
  Rejected: measured residual recall 0.91 and 0.42.
- **Deny with a message ("you cannot see this").** Rejected: it is the
  existence leak, and the field's one instance of it (Copilot's
  preview gate) shows the shape.

## Consequences

- `glean`'s statistics query joins the grant predicate; `rerank.py`'s
  `Statistics` and `lexical_stats` become authority-scoped. Study S2's
  scripts pin the residual leak at zero for the visible-set design and
  should become a regression test.
- `grep`'s regex and the embedding leg run under the predicate, never
  beside it.
- The error taxonomy separates hidden (not found), denied (visible,
  refused by grant) and refused by profile (ADR 063).
- What becomes harder: a `df` cache keyed by principal or subject set;
  ADR 067 sizes it.
