# What ranked search leaks under row grants: BM25 statistics as a side channel

- **Status:** research memo (commits us to nothing); study S2 of the
  principals-and-permissions programme
  (`2026-09-05-principals-and-permissions-research-plan.md` §4)
- **Date:** 2026-09-05
- **Owner:** Clay Gendron
- **Question:** when row grants hide some rows from a caller, does
  `glean` still reveal what is in the hidden rows? vfs scores every
  visible row with corpus-wide statistics (`N`, `avg_dl`, per-term
  `df`), and the cross-mount merge exports those statistics outright.
  Measure the leak on each observable channel, then cost the
  mitigations.
- **Method:** an executed experiment on BEIR SciFact (5,183 abstracts,
  300 claims, the harness's copy) scored with vfs's own tokenizer and
  formula (`vfs.models.lexical.tokenize`, `idf`, `term_weight`), the
  answer shaped as `glean` emits it (min-max scaled, nine decimals).
  A concrete adversary with read on the visible rows and write on a
  folder of their own, six partitions (random and topical hidden
  fractions of 10, 50, 90 %), 400 probe terms per partition. Scripts
  and raw tables:
  `context/research/studies/2026-09-05-glean-statistics-leak/`.
- **Sources:** Büttcher and Clarke, *A Security Model for Full-Text
  File System Search in Multi-User Environments*, USENIX FAST 2005,
  <https://www.usenix.org/legacy/events/fast05/tech/full_papers/buettcher/buettcher.pdf>
  (read 2026-09-05); PostgreSQL 18 docs, `CREATE FUNCTION`
  (`LEAKPROOF`) <https://www.postgresql.org/docs/current/sql-createfunction.html>
  and *Row Security Policies*
  <https://www.postgresql.org/docs/current/ddl-rowsecurity.html> (read
  2026-09-05). A web search for membership-inference work against IR
  statistics found nothing beyond Büttcher and Clarke; the searchable-
  encryption literature studies access-pattern leakage, a different
  channel.

## Bottom line

1. **The leak is total, on every channel.** At a 50 % hidden set the
   adversary learns, for every probe term, whether it occurs in hidden
   rows (precision 1.000, recall 1.000) and its exact hidden document
   frequency (99 to 100 % exact) from scores, from the `lexical_stats`
   export, and from ranks alone. The hidden set's *size* is recovered
   to within two documents from two queries.
2. **Min-max scaling hides nothing.** A single-term query's scaled
   scores carry no idf, but a two-term query carries the idf *ratio*,
   and one planted anchor document turns a ratio into an absolute df.
3. **The `lexical_stats` export is the worst channel.** It names `N`
   and each queried term's global `df` directly, for any term in the
   index, including terms no visible row contains. At h = 50 %, 41 %
   of the hidden vocabulary appears in no visible row; the export
   confirms each such term with one query naming it.
4. **Ranks alone still leak.** A 128-document ladder of planted
   anchors reads a term's idf off the interleaving: df exact for
   98.8 % of terms at h = 50 %.
5. **Visible-set statistics close the leak at no measured quality
   cost.** nDCG@10 on the visible qrels moves by −0.008 to +0.015
   across the six partitions, inside the harness's noise. The
   multiplayer intersection and the per-mount visible export behave
   the same way.
6. **Coarsening does not work.** Power-of-two df buckets still give
   recall 0.91 at precision 1.0; a stale global snapshot still gives
   recall 0.42.
7. **The cost is one aggregated pass over the visible postings of the
   query's terms**: about 12 terms and 14,000 posting rows per SciFact
   query (2.7 × N), most of them under 52 stop-like terms.

This is Büttcher and Clarke's FAST 2005 result, re-run on vfs's own
formula and on its actual output shape, with the same conclusion they
reached: statistics must be computed over the caller's readable files,
inside the query processor, never post-filtered.

## 1. What the caller sees today

`glean` on one mount computes `idf(df, N)` from the epoch's `lex_df`
and `lex_stats` rows, which cover every indexed chunk. There is no
per-caller filter anywhere on that path today
(`src/vfs/storage/backends/database/glean.py`, `lexical_stats` in
`lexical.py`). Three things leave the mount:

- the ranked visible rows with scores, min-max scaled over the answer
  and rounded to nine decimals (`_order`), plus the per-entry lexical
  leg in `legs` (`_fuse`);
- the `lexical_stats` extra on the `Result`: `n_docs`, `avg_dl`, and
  `{term: {df, idf}}` for every query term the index knows
  (`present`), whether or not any visible row contains it;
- the order of the rows.

The router's merge (`src/vfs/rerank.py`) sums the exports across
mounts and re-scores the union. A remote mount ships the export over
the wire.

## 2. The adversary

The adversary is a principal with read on some rows and write on a
folder of their own. That is every agent. They read all their visible
rows, so they know each visible row's term frequencies and length,
and the visible df of every term. They want `df_h(t)`: how many hidden
rows contain a term `t`.

They plant documents. Anchor A is a made-up token in 4 planted
documents, anchor B in 64, lengths spread from 20 to 2,000 tokens. For
the rank channel, 128 more documents each carry one unique token with
`tf` and length chosen so their raw scores climb geometrically. Then
one query per probe term. The probe set is 400 visible terms
stratified by visible df (100 each at df 1, 2 to 5, 6 to 30, 31+).

### 2.1 Channel a: scores

A single-term query is useless: every row's score is `idf × w(tf, dl)`
and min-max removes the common `idf`. So the adversary works in two
steps.

Step one, the corpus. Query anchor B alone: the scaled scores over 64
known lengths depend only on `avg_dl`. One least-squares fit recovers
it. Query A and B together: the shape now depends on
`idf(4, N) / idf(64, N)`, which pins `N`. Both fits take under a
second.

Step two, the term. Query `(t, A)`. The rows are the visible rows with
`t` plus the 4 anchor rows. The scaled scores fix
`ρ = idf(t) / idf(A)`; `idf(A) = idf(4, N)` is known; invert
`idf(df, N)` for `df`. Subtract the visible df.

| h | split | hidden size: estimate vs true | present-in-hidden precision / recall | hidden df exact |
|---|---|---|---|---|
| 10 % | random | 517 vs 518 | 1.000 / 1.000 | 1.000 |
| 50 % | random | 2,590 vs 2,592 | 1.000 / 1.000 | 0.993 |
| 90 % | random | 4,665 vs 4,665 | 1.000 / 1.000 | 1.000 |
| 10 % | topical | 519 vs 518 | 1.000 / 1.000 | 1.000 |
| 50 % | topical | 2,591 vs 2,592 | 1.000 / 1.000 | 1.000 |
| 90 % | topical | 4,666 vs 4,665 | 1.000 / 1.000 | 1.000 |

With the true `N` and `avg_dl` handed over instead of solved, every
partition is exact. The base rate ("some hidden row has the term") is
0.35 to 0.93 across partitions, so precision 1.0 is the adversary
never guessing, not a lucky prior.

A term with no visible occurrence leaks nothing on this channel: its
idf multiplies a term frequency of zero. Channel b does not have that
limit.

### 2.2 Channel b: the `lexical_stats` export

Nothing to solve. `n_docs` is `N`; `df` is the global df; the hidden
df is the difference. One query with `k` terms returns `k` dfs of
about 12.4 bits each (`log2 N`). Terms in no visible row are confirmed
the same way. At h = 50 % that is 10,782 terms (random split) or 11,927
(topical), 41 % and 47 % of the hidden vocabulary; at h = 90 % it is
72 % and 78 %.

### 2.3 Channel c: ranks only

The adversary is given `N` and `avg_dl` here (an upper bound on what
ranks leak; solving them from ranks alone is possible but coarse). The
query is `t` plus all 128 ladder tokens. Each visible row with `t`
lands between two rungs, which brackets `idf(t)`; the brackets
intersect over the rows; the midpoint is the estimate.

| h | split | precision / recall | hidden df exact | mean bracket width (docs) |
|---|---|---|---|---|
| 10 % | random | 1.000 / 1.000 | 0.995 | 12 |
| 50 % | random | 1.000 / 1.000 | 0.988 | 46 |
| 90 % | random | 1.000 / 1.000 | 0.777 | 374 |
| 10 % | topical | 1.000 / 0.986 | 0.993 | 33 |
| 50 % | topical | 1.000 / 1.000 | 0.988 | 23 |
| 90 % | topical | 1.000 / 1.000 | 0.860 | 171 |

Presence is always recovered. The count blurs only for common terms
(df above 30) at large hidden fractions, where the bracket widens.
Büttcher and Clarke reported the same split in 2005: exact statistics
with scores, approximate without.

## 3. Mitigations and their cost

Four statistics policies. "global" is today. "visible" is exact
`N`, `avg_dl` and `df` over the caller's visible rows. "bucket2" keeps
`N` and `avg_dl` and rounds every df to the nearest power of two.
"snapshot" takes every statistic from a fixed random half of the
corpus, the same for every caller. nDCG@10 is on the visible qrels
(a hidden relevant document cannot count), so the query count shrinks
with the visible set.

| split | h | queries | global | visible | bucket2 | snapshot |
|---|---|---|---|---|---|---|
| random | 10 % | 268 | 0.6647 | 0.6628 | 0.6630 | 0.6683 |
| random | 50 % | 150 | 0.6850 | 0.6775 | 0.6802 | 0.6802 |
| random | 90 % | 37 | 0.8338 | 0.8402 | 0.8430 | 0.8362 |
| topical | 10 % | 246 | 0.6521 | 0.6509 | 0.6506 | 0.6550 |
| topical | 50 % | 155 | 0.6936 | 0.7007 | 0.6922 | 0.6943 |
| topical | 90 % | 29 | 0.6984 | 0.7136 | 0.7008 | 0.7111 |

All rows visible, global statistics: 0.6627 (the harness records 0.658
for the same corpus through the database driver). Visible-set
statistics move nDCG@10 by −0.0075 (random 50 %) to +0.0152 (topical
90 %). The sign flips between splits and the sizes sit inside the
harness's 0.005 gate plus sampling noise at these query counts. There
is no quality argument for global statistics.

### 3.1 Residual leak per policy

The channel-a adversary again, handed each policy's `N` and `avg_dl`,
at h = 50 %. The decision rule is the one that is certain under the
policy: a recovered df above the visible df (global, snapshot), or a
different bucket (bucket2).

| split | policy | recovers the policy's df | precision | recall |
|---|---|---|---|---|
| random | global | 1.000 | 1.000 | 1.000 |
| random | visible | 1.000 | n/a | 0.000 |
| random | bucket2 | 1.000 | 1.000 | 0.910 |
| random | snapshot | 1.000 | 1.000 | 0.424 |
| topical | global | 1.000 | 1.000 | 1.000 |
| topical | visible | 1.000 | n/a | 0.000 |
| topical | bucket2 | 1.000 | 1.000 | 0.731 |
| topical | snapshot | 1.000 | 1.000 | 0.441 |

Bucketing is not a mitigation: the adversary recovers the bucket
exactly, and a hidden occurrence crosses a bucket edge most of the
time. The snapshot halves the recall and still leaks `N` and half the
vocabulary, and it goes stale. Only visible-set statistics give
recall zero, and they do so by construction: nothing the caller
receives is a function of a hidden row.

### 3.2 Multiplayer: the subject set's intersection

Each principal sees 70 % of the corpus; the session sees the
intersection. Statistics over the intersection are the multiplayer
form of "visible".

| principals | mix | intersection | queries | global | intersection | each principal's own (mean) |
|---|---|---|---|---|---|---|
| 1 | random | 70 % | 216 | 0.7047 | 0.7017 | 0.7017 |
| 2 | random | 49 % | 152 | 0.7124 | 0.7114 | 0.7100 |
| 3 | random | 34 % | 123 | 0.7287 | 0.7333 | 0.7315 |
| 5 | random | 17 % | 62 | 0.8083 | 0.7909 | 0.8075 |
| 2 | topical + random | 49 % | 144 | 0.6831 | 0.6839 | 0.6848 |
| 3 | topical + random | 34 % | 113 | 0.6876 | 0.6883 | 0.6910 |

The intersection's statistics track global within 0.017 down to a 17 %
visible corpus of 860 documents, and the largest gap sits on the
smallest query set (62). Quality does not degrade as the set shrinks
the corpus. Using any one principal's own statistics would leak that
principal's rows to the others; the intersection is the only safe
choice and it costs nothing measurable.

### 3.3 The merge

Two mounts, random halves; the caller sees 50 % of each. Each mount
ranks its visible rows to depth 30 (`fanout_depth(10)`), the router
re-scores the union with the summed exports or the union's own texts,
then applies the order law.

| mount-local statistics | export the router sums | nDCG@10 | leaks hidden df |
|---|---|---|---|
| global | global | 0.6885 | yes |
| global | visible | 0.6929 | yes (the local ranking) |
| global | union | 0.6917 | yes (the local ranking) |
| visible | visible | 0.6960 | no |
| visible | union | 0.6950 | no |

One index over the caller's visible rows with visible statistics
scores 0.6962. The safe export (per-mount statistics over the caller's
visible rows) matches it; the union fallback (`"statistics": "union"`
in `rerank.py`) is 0.001 behind and needs no export at all.

### 3.4 What visible-set statistics cost to compute

Global statistics are `k` summary-row reads per query (`lex_df`) plus
one `lex_stats` row. Visible-set `df` needs, per query term, the count
of its postings whose chunk the caller may see: one aggregated pass
over the visible posting rows of the query's terms, joined to the
grant predicate. On SciFact:

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| distinct indexed terms `k` | 12.0 | 11 | 21 | 26 |
| posting rows under those terms (sum of global df) | 14,028 | 13,619 | 27,575 | 33,453 |
| as a share of `N` | 2.7 | 2.6 | 5.3 | 6.5 |

52 terms occur in more than 20 % of documents (`of`, `the`, `and`,
`in`, `to`, `that`, `for`, `with`) and carry most of those rows and
almost none of the score. `N` and `avg_dl` over the visible rows are
one aggregate over the entry table under the same predicate.

Two facts make this cheaper than it looks. The lexical index is
rebuilt whole per epoch, so visible statistics are stable within an
epoch and can be memoised per `(epoch, principal)` or, because grants
are prefix-shaped (spec 058), maintained per `(epoch, grant prefix,
term)` and summed over the caller's covering prefixes. And the
postings vfs stores are already the rows the scorer fetches; the
count is a by-product of the fetch when the grant predicate is
pushed into it. Büttcher and Clarke measured their query-integrated
version at 12 to 17 % slower with everything visible and 22 to 30 %
slower with half the files visible, on a 2005 disk-bound engine. That
is the shape of the cost: a constant factor, not a new order.

## 4. What this decides

- **Spec 058's `invisible` rung means invisible to statistics.** A row
  the caller may not read must contribute nothing to any number the
  caller receives: not `N`, not `avg_dl`, not any term's `df`, not a
  score computed from them, not a rank. Post-filtering the ranked list
  is fail-open; the predicate belongs inside the scorer's statistics
  (ADR 006/021 already say "compiled into the query"; this extends it
  to the aggregates). This is the `LEAKPROOF` question in vfs's terms:
  Postgres refuses to run a non-leakproof function before the policy
  because its side effects could reveal a hidden row; BM25 with global
  statistics is a non-leakproof function of the hidden rows.
- **The `lexical_stats` export in `src/vfs/rerank.py` must be computed
  over the caller's visible rows**, on the mount, as a function of the
  principal (or the subject set). Exporting global statistics is the
  most efficient leak of the three. The export must also be limited to
  terms some visible row contains, or the vocabulary of hidden rows is
  enumerable. The union fallback is a safe and adequate default when a
  mount cannot export per-caller statistics.
- **The multiplayer rule holds for search as for reads**: a session
  acting for a set of principals scores with statistics over the
  intersection of their visible sets. The measured cost is nil; using
  any member's own statistics leaks their rows to the rest.
- **Coarsened idf and stale snapshots are not on the table.** They
  keep most of the leak and add a maintenance story.
- **Scores can stay in the answer.** Once statistics are visible-set,
  the score is a function of visible rows only; there is nothing left
  to hide, and the rank channel leaks the same information anyway.

## 5. Limits

- SciFact is 5,183 short abstracts, one chunk each. vfs chunks
  entries; the leak is per chunk and the arithmetic is identical.
- The adversary plants documents. Every agent with write on one folder
  can. A read-only adversary keeps the idf-ratio channel and loses the
  anchor; the integrality of `df` over many probes likely recovers `N`
  anyway, but that was not run.
- The 128-document ladder uses long documents (up to 15 × `avg_dl`)
  and raised the corpus mean length about fivefold. A shorter ladder
  covers terms with df under about 250 only; presence inference is
  unaffected.
- Channel c was handed `N` and `avg_dl`; it is an upper bound on what
  ranks alone leak.
- nDCG@10 at h = 90 % rests on 29 to 37 queries; those cells are
  direction, not measurement.
- The cost model counts rows, not milliseconds; S1 owns the engine
  numbers.
