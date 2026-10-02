# Filtered vector search: keeping the vector leg cheap under a permission filter

- **Status:** research memo (commits us to nothing). Input to spec 058's
  vector leg under a partial view, and to ADR 071's clause fan-out.
  Follows the partial-glean latency study
  (`studies/2026-09-29-partial-glean-latency/`), which measured the cost
  this memo explains.
- **Date:** 2026-09-30
- **Owner:** Clay Gendron
- **Question:** How do vector engines combine a filter with
  nearest-neighbour search? Which of their answers fit vfs, whose filter
  is a permission set (a union of path prefixes, per caller)? And why
  does vfs's vector leg on SQLite take 212 ms at 100 grants and about
  2 s at 500?
- **Method:** three parallel read-only studies of refreshed clones
  (qdrant; pgvector with the Weaviate, Milvus and Pinecone docs; sqlite-vec
  and lancedb). Then four executed experiments in
  `studies/2026-09-30-filtered-vector-search/`:
  - `sqlite_bench.py`: 12 strategies on SQLite 3.50.4 + sqlite-vec 0.1.9, at dimensions 64 and 384.
  - `pg_bench.py`: 9 strategies on Postgres 17.11 + pgvector 0.8.6 with an HNSW index, at dimension 384.
  - `vfs_plan.py`: captures vfs's own vector-leg statement and prints its query plan. It also times an admitted-first rewrite against vfs's real tables.
  - `prefix_join.py`: tests grants held as rows in a table instead of as bind parameters.

  Every table the Postgres runs created was dropped. A final check found no `fvs_%` tables left.
- **Sources (clones; none was dirty):**
  - `qdrant/qdrant` @ `6ab21cac1`, v1.19.1, Apache-2.0. Cloned 2026-09-30 and recorded as is; its commit date is 2026-09-03.
  - `pgvector/pgvector` @ `70fb225`, PostgreSQL License. Refreshed 2026-09-30 from `e48241b` to `origin/master`.
  - `asg017/sqlite-vec` @ `04d28bd`, dual MIT / Apache-2.0. Commit date 2026-05-17; already at `origin/main` on 2026-09-30.
  - `lancedb/lancedb` @ `82d3948`, Apache-2.0. Refreshed 2026-09-30 from `2fbf6d6` to `origin/main`; commit date 2026-09-29.

  Each licence was re-checked after the refresh. Nothing was copied; this memo describes and cites.
- **Sources (web, read 2026-09-30):**
  - Weaviate: vector-index config reference, filtering concepts, and the blog post "speed up filtered vector search".
  - Milvus: `use-partition-key`, `multi_tenancy`, `filtered-search`, and the product FAQ.
  - Pinecone: `implement-multitenancy` and `learn/vector-search-filtering`.
  - Papers: ACORN (Patel et al., SIGMOD 2024, arXiv 2403.04871) and Filtered-DiskANN (Gollapudi et al., WWW 2023). The Filtered-DiskANN figures come from abstracts and snippets; the ACM page refused a direct fetch.

## Terms used in this memo

- **kNN (k nearest neighbours):** the k rows whose vectors are closest to
  the query vector. vfs uses k = 10 here.
- **Brute force (exact search):** compute the distance to every candidate
  row, sort, and keep the top k. The answer is always correct. The cost
  grows with the number of rows.
- **ANN (approximate nearest neighbour):** an index that finds *most* of
  the true top k without looking at every row. It is fast, but it can
  miss some neighbours.
- **HNSW (Hierarchical Navigable Small World):** the most common ANN
  index. It is a graph. Each vector links to about `m` (default 16) near
  neighbours. A search walks the graph towards the query and keeps a
  candidate list of size `ef_search`. pgvector's default `ef_search`
  is 40.
- **Recall@10:** the share of the true top 10 that a search returned.
  1.00 means it found all ten. 0.70 means three of the ten true
  neighbours were missed and replaced by worse ones.
- **Pre-filter:** find the allowed rows first, then search only those.
- **Post-filter:** search without the filter, then drop what the caller
  may not see.
- **Over-fetch:** a post-filter asks for more than k rows (a window `W`)
  so that enough survive the filter. If the caller sees 10% of rows, it
  needs about `W = 10 × k / 0.10 = 100` rows on average to keep 10.
- **Selectivity / cardinality:** how many rows the filter admits.
  Selectivity is that count as a fraction, and cardinality is the count
  itself. A "selective" filter admits few rows.
- **Arm:** one granted prefix in vfs's compiled predicate. An arm reads
  `path = :p OR path LIKE :p || '/%'`, and the arms are joined by OR.
- **Admitted-first:** the shape this memo proposes. It first finds the
  admitted entry ids through the path index, then computes distance
  only over their chunks.

## Findings

### 1. The cost is not the distance. It is testing every row against every arm.

vfs's own vector-leg statement was captured on the partial-glean
bench's 50,000-file mount (`runs/vfs-vector-leg-plan.md`). It was then
re-run alone, and its plan was printed.

- **Without planner statistics:** SQLite drives the statement from the
  `kind` index, and `kind IN ('chunk','file','version')` matches every
  row.
- **After `ANALYZE`:** it switches to a full `SCAN` of the entries table
  (`runs/vfs-vector-leg-plan-analyzed.md`).
- **In both cases,** the path index is never used. Every row is tested
  against every arm, as a leftover filter.

For scale, the distance itself is cheap. Brute force over all 50,000
chunks costs 15 ms at dimension 64, and 51 to 75 ms at dimension 384.

The same arms in an **admitted-first** statement tell the difference.
That statement puts the arms in a materialised CTE (a subquery the
engine runs once and stores). The path index drives it through SQLite's
multi-index OR. Then the distance runs over the admitted chunks only.

| grants (visible) | vfs today: vector statement | admitted-first, path arms | admitted-first + owner arm as a `UNION` branch |
|---|---|---|---|
| 1 (0.1%) | 11 ms | 0 ms | 0 ms |
| 10 (1%) | 32 ms | 1 ms | 1 ms |
| 100 (10%) | 214 ms | 9 ms | 10 ms |
| 500 (50%) | 393 ms for the first of 3 clause statements | 42 ms, one statement | 44 ms |

The results are exact by construction. It is the same predicate,
evaluated in a different order. In the synthetic bench, the
admitted-first top 10 matched the one-statement top 10 on every query
(recall 1.00 in every row).

Two details matter:

- **The owner arm.** vfs's clause ORs `owner_id = :me` into the path
  arms. A single OR that mixes columns does not get the multi-index OR
  plan here. As its own `UNION` branch, the owner arm costs 0 to 2 ms
  more (up to 7 ms after `ANALYZE`). `owner_id` is already indexed (`models/rows.py:409`).
- **Join order on SQLite.** SQLite needed `CROSS JOIN` to keep the
  admitted set as the outer loop. With a plain `JOIN`, the 1-grant case
  cost 32 ms instead of 0. Postgres kept the right order unaided.

How the arm is spelled matters much less than what drives the plan.
Once the path index drives, `LIKE` arms (with vfs's
`case_sensitive_like = ON`) and byte-range arms cost the same: 32 against
33 ms at 500 arms (`runs/sqlite-dim64.md`). This agrees with the
2026-09-05 predicate memo, which found the two forms within noise when
another index drove the plan.

**In short:** the leg is slow because the permission filter never gets
to choose the rows. Let it choose first.

### 2. Post-filtering is cheap to run, but it silently loses results.

In post-filtering, the engine searches the whole mount for a window of
`W` rows, and app code drops the rows the caller may not see. The
corpus clusters vectors by folder, so a query's true neighbours sit in
a few folders, as real text does. This is the hard case for
post-filtering: the nearest rows may all be in folders the caller
cannot see.

SQLite, dimension 384, cells show recall@10 and then the mean number of
hits returned (`runs/sqlite-dim384.md`):

| visible | post, W = 100 | post, W = 1,000 | vec0 KNN, W = 4,096 | post, deepen ×4 until 10 | admitted-first |
|---|---|---|---|---|---|
| 0.1% | 0.00 · 0.0 | 0.10 · 0.9 | 0.27 · 2.6 | 1.00 · 10, **320 ms** | 1.00 · 10, **0.1 ms** |
| 1% | 0.05 · 0.5 | 0.57 · 5.8 | 0.97 · 9.7 | 1.00 · 10, 160 ms | 1.00 · 10, 0.5 ms |
| 10% | 0.15–0.34 | 1.00 · 10 | 1.00 · 10 | 1.00 · 10, 101–104 ms | 1.00 · 10, 6–8 ms |
| 50% | 0.85–0.95 | 1.00 · 10 | 1.00 · 10 | 1.00 · 10, 51 ms | 1.00 · 10, 33–38 ms |

What the table shows:

- **A fixed window fails selective callers.** At 1% visible, `W = 1,000`
  finds only 5.8 of the 10 rows. At 0.1%, it finds 0.9.
- **Deepening fixes recall but costs time.** Growing the window until
  10 rows survive always ends exact. But each deepening pass is another
  full scan: 320 ms at 0.1%.
- **On an exact-only engine, post-filtering never wins.** On SQLite,
  every post-filter pays at least the full brute-force scan (51 to
  75 ms at dimension 384). Admitted-first pays for the admitted rows
  only.
- **sqlite-vec's `vec0` table is no faster here.** Its KNN was slower
  than the scalar `vec_distance_cosine` scan vfs uses today: 72 to
  80 ms against 51 to 75 ms. It also caps k at 4,096
  (`sqlite-vec.c:7901-7908`).

### 3. On Postgres, HNSW under today's filter is fast but misses 15–30% of the true neighbours.

With an HNSW index, vfs today runs the arms inside an HNSW-ordered
query, with `hnsw.iterative_scan = relaxed_order`. The Postgres planner
itself chose HNSW for most filtered queries, even at 1% visible (the
`plan` column in `runs/postgres-dim384-run1.md`). pgvector's cost model
has no term for the filter's selectivity. Its startup-cost ratio
depends only on `m`, `ef_search` and the graph layer
(`src/hnsw.c:199-216`).

Postgres, dimension 384, 50,000 chunks. Each cell shows median ms and
then recall@10. The first clean run is shown; the `ef100 top40` column
comes from the second run (`runs/postgres-dim384-run2.md`), which was
noisier in its last two rows.

| visible (grants) | exact, admitted-first | HNSW + arms (today, indexed) | HNSW + arms, ef 100, top 40 re-sorted | HNSW post-filter, W = 1,000 | HNSW post-filter, W = 4,000 | gate: count, then choose |
|---|---|---|---|---|---|---|
| 0.1% (1) | 0.8 · 1.00 | 2.7 · 1.00 | 2.7 · 1.00 | 14.8 · 0.11 | 34.5 · 0.26 | 1.4 · 1.00 |
| 1% (10) | 1.4 · 1.00 | 17.5 · **0.76** | 3.8 · 1.00 | 14.9 · 0.50 | 35.3 · 0.97 | 2.5 · 1.00 |
| 1% (500 files) | 26.6 · 1.00 | 38.0 · **0.85** | 31.0 · 1.00 | 12.0 · 0.83 | 32.4 · 1.00 | 49.8 · 1.00 |
| 10% (1) | 6.3 · 1.00 | 5.7 · **0.70** | 6.2 · 0.77 | 12.5 · 0.93 | 36.1 · 1.00 | 7.6 · 1.00 |
| 10% (100) | 9.9 · 1.00 | 7.4 · **0.73** | 8.1 · 0.78 | 12.8 · 0.90 | 35.8 · 1.00 | 13.3 · 1.00 |
| 50% (5) | 29.5 · 1.00 | 3.3 · 0.97 | 17.3 · 0.97 | 15.0 · 0.99 | 44.1 · 1.00 | 6.2 · 0.97 |
| 50% (500) | 86.8 · 1.00 | 16.0 · 0.93 | 120.8 · 1.00 | 14.3 · 0.99 | 35.0 · 1.00 | 27.4 · 0.96 |

For comparison, HNSW with no filter took 1.0 to 1.3 ms, with recall
0.99 (second run). The exact whole-mount scan took 23 to 27 ms.

What the table shows:

- **Today's indexed shape loses recall silently.** For callers who see
  1% to 10%, it returns 10 rows every time, but only 7 or 8 of them
  are true top-10 rows. Nothing in the envelope says so. Raising
  `ef_search` and re-sorting the top 40 fixes the 1% case but not the
  10% case (0.77–0.78).
- **Exact admitted-first is both exact and fast for small visible
  sets.** Up to 5,000 admitted rows it costs 0.8 to 27 ms. HNSW only
  earns its place for broad callers: at 50% visible, exact costs 30 to
  87 ms against HNSW's 3 to 16 ms.
- **A cardinality gate gets the best of both.** The last column counts
  the admitted entries first. Up to 5,000 rows, it runs exact
  admitted-first. Above that, it runs an HNSW post-filter with window
  `3k / selectivity`, deepening if short. Its recall is 1.00 wherever
  the caller sees 10% or less, and 0.96 to 0.97 at 50%. That is as
  good as HNSW with the filter inside (0.93 to 0.97) at that visibility.
- **The gate's own cost is the count.** At 500 file grants it costs
  about 23 ms (500 index probes). That count can be cached or made
  cheaper; see recommendation 3.

### 4. How the engines combine filter and search, and when each wins

Three families:

| family | how it works | wins when | loses when | who does it |
|---|---|---|---|---|
| pre-filter + brute force | list the rows the filter admits (via a payload or scalar index), score them all exactly | the filter admits few rows | the filter admits most rows (it becomes a full scan) | qdrant "plain" search; Weaviate flat search; pgvector with a B-tree on the filter column; lancedb prefilter (the default) |
| post-filter + over-fetch | ANN for `W` rows, then drop the disallowed ones | the filter admits most rows | the filter is selective, or anti-correlated with the query: recall collapses (finding 2) | pgvector without iterative scan; lancedb `postfilter()` |
| filter-aware traversal | check the filter while walking the graph, skipping failing nodes; extra links keep the graph connected under the filter | the middle ground; large corpora | very selective filters (the graph disconnects); needs an engine-owned index | qdrant filterable HNSW and ACORN; Weaviate ACORN; Milvus (bitset into the index); Pinecone single-stage; Filtered-DiskANN |

pgvector's iterative scan is a fourth, weaker form. It is a post-filter
that resumes the graph walk from discarded candidates when too few rows
pass (`src/hnswscan.c:62-87, 249-286`). It stops at
`hnsw.max_scan_tuples`, which defaults to 20,000 (`src/hnsw.c:101-104`).

**How systems choose: they estimate the filter's cardinality, and brute
force below a threshold.**

- **qdrant** is the clearest model (`lib/segment/src/index/hnsw_index/hnsw/read_view/dispatch.rs:113-174`).
  - It estimates the filter's cardinality as a `min / expected / max`
    triple. It combines the triple through AND, OR and NOT
    (`lib/segment/src/index/query_estimator.rs:119-220, 328-354`).
  - If `max` is below `full_scan_threshold`, it brute-forces the
    admitted points. If `min` is above it, it uses HNSW.
  - In between, it samples up to 1,000 points and stops once a ~95%
    confidence interval clears the threshold
    (`lib/segment/src/index/sample_estimation.rs:5-52`).
  - The threshold is set in kilobytes of vectors: 10,000 KB by
    default (`lib/segment/src/types.rs:2356`). That is about 10,000
    vectors of dimension 256.
  - For an OR, the estimate's `max` is the sum of the branch maxes
    (`query_estimator.rs:152`). So a many-armed OR drifts towards the
    HNSW path.
- **Weaviate** brute-forces the allow-list below `flatSearchCutoff`,
  which defaults to 40,000 objects. Above it, it uses ACORN. ACORN makes
  two-hop expansions only through nodes that fail the filter, and adds
  filter-matching entry points. Weaviate reports up to 10× gains when
  the filter and the query are poorly correlated.
- **pgvector** leaves the choice to Postgres's generic planner, which
  underestimates what the filter will throw away. Its README says to:
  - index the filter column, because exact search wins when the filter
    matches a low percentage of rows (`README.md:432-446`);
  - use iterative scans (`README.md:480-547`);
  - use partial indexes or partitioning for a few distinct filter
    values (`README.md:456-476`).
- **lancedb** prefilters by default. It warns that a postfilter "can
  return fewer than `limit` results (or even no results)"
  (`rust/lancedb/src/query.rs:509-527, 881`). Scalar indexes (BTREE,
  BITMAP, LABEL_LIST) make that prefilter cheap
  (`rust/lancedb/src/index/scalar.rs:4-52`).

Filterable HNSW and ACORN need an index the engine owns. qdrant builds
extra sub-graphs per indexed payload value
(`lib/segment/src/index/hnsw_index/hnsw/build.rs:449-533, 641-730`)
and checks the filter at every expanded node
(`lib/segment/src/index/hnsw_index/point_scorer.rs:79-131`). None of
the SQL engines vfs targets exposes that. pgvector, MariaDB, Oracle and
SQL Server all check the filter outside the graph.

### 5. What changes when the filter is a permission set

A permission filter has a helpful shape, and some unhelpful ones.

- **Helpful: each arm is one contiguous range of the path index.** A
  prefix `/a/b` covers exactly the byte range `(/a/b/, /a/b0)`, plus
  `/a/b` itself. So vfs already has what qdrant calls a payload index
  and lancedb calls a scalar index: the unique `path` index. Each arm
  is one index range scan. The cardinality of an arm is the size of a
  subtree.
- **Unhelpful: it is a per-caller union of many arms, with holes and an
  owner arm.** qdrant's estimator would treat such an OR as the sum of
  its parts, capped at the total. vfs can do better. It can count
  exactly, cheaply, through the same index (1 to 23 ms here).
- **Reuse: the same caller asks again and again.** The compiled
  clauses are already cached (`RightsCache`). The admitted count could
  be cached too, keyed by the rights and the mount's write generation.
  A materialised visible-id table (`temp-allow` in the SQLite bench,
  2 to 30 ms) was no faster than admitted-first. That agrees with the
  2026-09-05 predicate memo, which found a materialised visibility
  table never beat the literal predicate.
- **Many grants: SQL engines have their own caps.** SQLite refused a
  5,000-arm OR with "Expression tree is too large (maximum depth
  1000)". That is `SQLITE_MAX_EXPR_DEPTH`, an external cap the clause
  fan-out must respect. Holding the grants as **rows** removes both the
  cap and the fan-out:
  - put the resolved prefixes into a scratch table `(lo, hi)` in
    chunked inserts;
  - range-join that table to the path index;
  - the join matched the inlined-arm results exactly and ran at the
    same speed (3.2 vs 3.4 ms at 100 grants, 17.0 vs 17.4 ms at 500);
  - it answered 5,000 file grants in **9 ms in one statement**
    (`runs/prefix-join.md`).
- **Partitions and namespaces do not map onto grants.**
  - Milvus: at most 1,024 partitions. Partition-key isolation needs
    exactly one key value per query.
  - Pinecone: one query searches one namespace. Its `$in` filter takes
    at most 10,000 values.
  - sqlite-vec: at most 4 partition-key columns, and no `IN` on them
    (`sqlite-vec.c:3471, 6171-6221`; project `TODO:7`).
  - pgvector: partial indexes or list partitions, one per value
    (`README.md:456-476`).

  All of these assume a small, stable set of tenant values, and a
  caller who searches **one** of them. A vfs caller's rights are
  dynamic, nested prefixes. A caller who spans many folders would fan
  out into one search per partition and merge the lists. That is the
  cost vfs already pays per clause. The one real tenant boundary vfs
  has, the mount, is already physical: one table set per mount. That is
  qdrant's `is_tenant` idea, and it is already done.

## Recommendations

1. **Adopt admitted-first for the vector leg under a partial view, on
   every dialect.**
   - Find the admitted entry ids through the path index first: a
     materialised CTE, a derived table, or `entry_id IN (subquery)`,
     whichever each engine plans well.
   - Then compute the distance over those entries' chunks only.
   - Put the owner arm in its own `UNION` branch.
   - This is exact, with no recall trade. Measured on vfs's own tables:
     214 ms → 9 ms at 100 grants. At 500 grants, the first of today's
     three clause statements alone costs 393 ms; the single
     admitted-first statement costs 42 ms.
   - On the `exact` dialects (SQLite, SQL Server), this is the whole
     answer, because there is no ANN index to choose.
2. **On `ann` dialects, gate ANN on the admitted count, qdrant-style.**
   - Count the admitted entries first.
   - At or below a declared threshold, run exact admitted-first.
     5,000 was used here; qdrant's default is about 10,000 vectors and
     Weaviate's 40,000.
   - Above it, use the ANN index. Either over-fetch `W = 3k /
     selectivity` and deepen if short, or keep the filter inside the
     scan but fetch k × 4 and re-sort exactly.
   - Today's indexed shape returns wrong neighbours 15 to 30% of the
     time for callers who see 1 to 10%. The gate measured recall 1.00
     there.
   - The threshold is a performance knob, not a scale cap. It chooses
     a path; it never limits what a caller can search.
3. **Make the count cheap.** Options:
   - Cache it per (rights fingerprint, mount write generation).
   - Or keep subtree row counts, since an arm's cardinality is a
     subtree size.
   - Or derive it from the admitted-first CTE itself, which already
     materialises the set.

   The uncached count costs up to 23 ms at 500 grants.
4. **Prototype grants as rows to retire the clause fan-out.** Put the
   resolved ranges in a scratch table (or pass them as one array on
   Postgres, `unnest($1::text[])`), then range-join them to the path
   index.
   - The statement stays bounded at any grant count.
   - 5,000 grants answered in 9 ms, where the inlined OR hits SQLite's
     depth cap.
   - Holes become an anti-join.
   - Each engine's spelling (temp table, table-valued parameter,
     collection) needs its own leg test.
5. **Do not adopt:**
   - partitions or namespaces per permission group (they do not fit
     dynamic prefix unions);
   - sqlite-vec `vec0` (slower here, k ≤ 4,096, no prefix filter);
   - post-filtering as the default on exact engines (never faster than
     admitted-first, and lossy unless it deepens);
   - filterable HNSW or ACORN (none of vfs's engines exposes them;
     revisit only if one ships it).
6. **Report the tier honestly.** When the ANN path serves a scoped
   query, the envelope should say the vector leg is approximate. It
   should not look identical to an exact answer.

**What to prototype in the glean bench**
(`studies/2026-09-29-partial-glean-latency/bench.py`):

- **(a)** An admitted-first `_vector_leg` behind a flag. Rerun the
  existing caller table, with a new recall column that checks against
  an exact oracle.
- **(b)** The cardinality gate, on Postgres with an HNSW index, reusing
  `pg_bench.py`'s callers.
- **(c)** Grants as rows, at 500 and 5,000 grants, on SQLite and
  Postgres first, then the MSSQL and Oracle legs.

## One-line version

The vector leg is slow because every row is tested against every grant
before the path index gets a say; find the admitted rows through the
path index first, then brute-force them (exact, 214 ms → 9 ms), and
use HNSW only when the admitted set is large. Today's HNSW-under-filter
silently drops 15–30% of the true neighbours for narrow callers.
