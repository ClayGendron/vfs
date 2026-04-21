# Native BM25 in Postgres — `pg_search` vs `pg_textsearch`

> Review date: 2026-04-20
> Scope: official PostgreSQL docs, official `pg_textsearch` repo/docs, official ParadeDB / `pg_search` docs and release metadata
> Method: primary sources only

## Executive Summary

As of 2026-04-20, PostgreSQL core still does **not** provide native BM25 ranking. Core full-text search gives you `tsvector`, `tsquery`, `ts_rank`, and `ts_rank_cd`, but the PostgreSQL docs explicitly note that the built-in ranking functions do **not** use global information. That means they are not BM25, because BM25 depends on corpus-level document frequency / IDF.

If the goal is "real BM25 inside Postgres" rather than "better-than-LIKE ranking," an extension is the practical route.

For **Grover as it exists today**, my recommendation is:

- Prefer **`pg_textsearch`** if you want to replace the current Postgres `ts_rank_cd` path with a focused BM25 implementation.
- Prefer **`pg_search`** only if you intentionally want Grover's lexical layer to become an Elastic-like search subsystem with custom tokenizers, phrase queries, faceting / aggregations, join-aware search pushdown, and eventually tighter hybrid-search behavior inside SQL itself.

The main reason is not just "simplicity." It is that Grover's `vfs_objects` table is a **single heterogeneous table** (`file`, `directory`, `chunk`, `version`, `edge`, API nodes, deleted rows, user-scoped path prefixes). `pg_textsearch` fits that shape better because it lets us create **normal Postgres-style partial and expression BM25 indexes** over exactly the rows we want. ParadeDB's `pg_search` is much more ambitious, but its own docs say only **one BM25 index can exist per table**, and that covering-index model couples Grover's wide table much more tightly to the search engine.

## What PostgreSQL Core Gives You

PostgreSQL core full-text search is still useful, but it is not BM25.

Relevant facts from the official PostgreSQL docs:

- `ts_rank` and `ts_rank_cd` are the built-in ranking functions.
- Their normalization options can account for document length and proximity.
- The docs explicitly say these ranking functions **do not use global information**.
- The docs also note that ranking can be expensive because PostgreSQL must consult the `tsvector` of each matching document.

That maps directly to Grover's current `PostgresFileSystem` implementation:

- Today, [`src/vfs/backends/postgres.py`](/Users/claygendron/Git/Repos/grover/src/vfs/backends/postgres.py) uses `to_tsvector(...) @@ to_tsquery(...)` plus `ts_rank_cd(...)`.
- That path is natively inside Postgres, but it is still **FTS ranking**, not BM25.

So the decision is not "native Postgres vs extension." It is:

- core Postgres FTS with non-BM25 ranking, or
- a BM25 extension that runs inside Postgres.

## Grover-Specific Constraints

The choice should be made against Grover's actual schema and query shape, not against generic benchmark charts.

Important repo facts:

- [`src/vfs/models.py`](/Users/claygendron/Git/Repos/grover/src/vfs/models.py) stores all namespace entities in one `vfs_objects` table.
- The primary key is `id: str` (UUID text), not an integer surrogate key.
- Searchable text lives primarily in `content`.
- Lexical search filters out deleted rows and version rows.
- User scoping is path-prefix based in the backend (`path LIKE '/{user_id}/%'`), not row-level BM25 tenant partitioning.
- Candidate-scoped lexical search already falls back to the portable Python BM25 path; the native Postgres override is only the full-corpus top-k case.

Those constraints favor a BM25 implementation that:

- works cleanly on a single `content` expression,
- supports partial indexes on only live searchable rows,
- does not force the whole wide table into one search index definition,
- does not assume integer document ids for best performance,
- leaves filtering / graph / regex / vector logic under Grover's control.

## Recommendation

### Recommended default for Grover: `pg_textsearch`

`pg_textsearch` is the better fit if the target is:

- "real BM25 for `lexical_search`"
- over one main text expression (`content`)
- in a normal Postgres query shape
- with Grover still owning the rest of the retrieval pipeline

Why this fits Grover well:

- It is a **BM25 index access method**, not a replacement query language.
- Its query surface is close to Grover's current SQL style: `ORDER BY content <@> ... LIMIT k`.
- It supports **partial indexes**, which is important for `vfs_objects`.
- It supports **expression indexes**, which keeps the schema change localized.
- It is **PostgreSQL-licensed**, which removes the AGPL question entirely.
- Grover already has application-side logic for candidates, hydration, scoping, and result shaping, so we do not need the extension to own those concerns.

### Choose `pg_search` if the lexical layer is becoming a search engine

`pg_search` is the better fit if the actual target is larger than BM25:

- phrase queries,
- custom tokenizers beyond Postgres text configs,
- field-aware query builders,
- facets / aggregations,
- join pushdown,
- hybrid search inside the extension's query path,
- search behavior that looks more like Lucene / Elasticsearch than like ordinary Postgres ranking.

That is a real direction, but it is a broader architectural commitment than "make Grover's Postgres lexical search use BM25."

## `pg_textsearch` — What It Is

As of 2026-04-20, the official `timescale/pg_textsearch` README describes it as:

- "Modern ranked text search for Postgres"
- BM25 with configurable `k1` and `b`
- based on Postgres text search configurations
- supporting expression indexes, partial indexes, and partitioned tables
- optimized for top-k queries via Block-Max WAND
- "v1.0.0 - Production ready"

Current published constraints from the official repo:

- Supported PostgreSQL versions: **17 and 18**
- Requires `shared_preload_libraries = 'pg_textsearch'`
- Requires `CREATE EXTENSION pg_textsearch`
- Uses an index syntax like:

```sql
CREATE INDEX docs_idx
ON documents
USING bm25 (content)
WITH (text_config = 'english');
```

- Query syntax is:

```sql
SELECT *
FROM documents
ORDER BY content <@> 'search terms'
LIMIT 10;
```

- The `<@>` operator returns a **negative** BM25 score because Postgres operator scans sort ascending. Lower values are better; application code should negate the value if it wants a positive relevance score.

### Why `pg_textsearch` fits Grover

The extension is narrow in exactly the right way for Grover's current `lexical_search`:

- It gives us BM25.
- It does not try to take over the whole query planner surface.
- It lets us keep normal SQL `WHERE` clauses for `deleted_at`, `kind`, and user-scope filters.
- It lets us keep Grover's own result hydration and `Entry` shaping.

Most importantly, it supports the kind of partial index that a unified `vfs_objects` table wants:

```sql
CREATE INDEX ix_vfs_objects_bm25_live_content
ON vfs_objects
USING bm25 (content)
WITH (text_config = 'simple')
WHERE content IS NOT NULL
  AND deleted_at IS NULL
  AND kind != 'version';
```

That matches the current lexical-search semantics much better than a table-wide covering search index.

If Grover later wants separate search behavior for files vs chunks, `pg_textsearch` also leaves room for multiple partial BM25 indexes on the same table, for example:

- one index for live files,
- one index for live chunks,
- one index per language,
- one index over a transformed expression.

That flexibility is unusually valuable on a heterogeneous table.

### Important `pg_textsearch` limitations

The official README also calls out several tradeoffs:

- **No phrase queries**. The index stores term frequencies but not term positions.
- **No built-in faceted search**. You use standard Postgres filtering / grouping around ranked results.
- **Partial indexes require explicit index selection**. The README's partial-index examples use `to_bm25query(query, index_name)` because the implicit `text <@> 'query'` form skips partial indexes.
- **Insert / update performance is not yet fully optimized** for sustained write-heavy workloads.
- **No background compaction** yet; compaction is synchronous during spill operations.
- **Partition-local statistics** mean BM25 scores across partitions are not necessarily comparable.
- The implicit operator form depends on planner hooks, so in PL/pgSQL you should use explicit `to_bm25query(...)`.
- **No `LIMIT` means more scoring work**. Without `ORDER BY ... LIMIT`, the extension scores up to `pg_textsearch.default_limit`.
- It uses `shared_preload_libraries`, so it is not a drop-in fit for every managed Postgres service.

For Grover, those limitations are mostly acceptable:

- phrase queries are not part of the current `lexical_search` contract,
- facets are not part of the current lexical API,
- candidate-scoped search already uses Python BM25,
- Grover issues top-k searches with an explicit `k`, which is exactly the fast path the extension wants.

The one limitation that could be decisive is PostgreSQL version support:

- if Grover must support **Postgres 15 or 16**, `pg_textsearch` is currently disqualified.

## `pg_search` — What It Is

As of 2026-04-20, official ParadeDB docs and PGXN metadata describe `pg_search` as:

- a Postgres extension for BM25,
- built on **Tantivy** via **pgrx**,
- exposing custom operators / query functions,
- supporting search, filtering, aggregations, joins, and hybrid-search-adjacent features,
- published on PGXN as **stable**,
- latest PGXN release at the time of review: **0.23.0** on **2026-04-16**,
- community license: **AGPL-3.0**.

The official docs describe the BM25 index as:

- a custom index type,
- laid out as an **LSM tree**,
- with both inverted-index and columnar structures,
- updated transactionally with table writes,
- using custom operators and custom scans to push more of query execution into the extension.

Representative index definition:

```sql
CREATE INDEX search_idx
ON mock_items
USING bm25 (id, description, category, rating)
WITH (key_field = 'id');
```

Representative query shape:

```sql
SELECT id, pdb.score(id)
FROM mock_items
WHERE description ||| 'running shoes'
ORDER BY pdb.score(id) DESC
LIMIT 5;
```

### What `pg_search` does better than `pg_textsearch`

This is where ParadeDB is genuinely stronger.

It gives you a richer search platform inside Postgres:

- **custom tokenizers** and token filters,
- **phrase queries**,
- **fuzzy matching / typo tolerance**,
- **highlighting / snippets**,
- **multi-field indexing**,
- **non-text fields inside the same BM25 index**,
- **facets / aggregates**,
- **join support** and some join pushdown,
- **custom scans** that can push more work into the extension,
- an explicit path toward **hybrid search** with `pgvector`,
- support docs for **Postgres 15+** in current install guidance,
- compatibility guidance for **distributed setups via Citus**.

If Grover wanted to evolve toward "search engine embedded inside the DB," these are meaningful advantages.

The tokenizer story is especially important:

- `pg_textsearch` uses Postgres text search configurations.
- ParadeDB exposes a larger tokenizer surface, including `unicode`, `literal`, `ngram`, and other search-engine-style choices.

For code-heavy corpora, that can matter. Grover today stores source files, chunks, and docs in the same system. If identifier-aware or partial-match tokenization becomes central, `pg_search` has the stronger built-in story.

### Why I still would not choose `pg_search` first for Grover

The problem is not capability. The problem is **fit**.

ParadeDB's own docs say:

- only **one BM25 index can exist per table**,
- it is a **covering index**,
- all relevant columns should be included up front,
- adding or removing columns requires a **REINDEX**,
- the most recently created BM25 index is the one used for queries.

On Grover's `vfs_objects` table, that creates several mismatches:

- The table is wide and heterogeneous.
- Searchable rows are only a subset of rows.
- Grover already has separate implementations for grep, graph traversal, vector search, path scoping, and candidate-scoped lexical ranking.
- We do not currently need a search engine that owns sorting / aggregates / join pushdown over this table.

In other words, `pg_search` is strongest when the table itself wants to be a first-class search document store. Grover's table is not just a search document store; it is the entire virtual filesystem namespace.

Two concrete repo-specific downsides:

- **Single-index-per-table coupling** is awkward on `vfs_objects`. We lose the freedom to keep small, targeted partial BM25 indexes over only the rows / expressions that matter.
- Grover's primary key is a **UUID string**. ParadeDB docs say unique text keys are allowed, but also say integer key fields are most performant. So Grover is compatible, but not in the extension's ideal shape.

### Important `pg_search` tradeoffs

From official docs:

- requires `shared_preload_libraries = 'pg_search'`,
- requires superuser / self-managed installation flow,
- community edition is **AGPL-3.0**,
- the covering-index design means schema evolution is more invasive,
- frequent writes create segments and can degrade some query performance until maintenance catches up,
- some performance guidance depends on Postgres worker settings, shared buffers, and autovacuum behavior.

That does not make `pg_search` a bad choice. It makes it a bigger choice.

## Head-to-Head Comparison

| Dimension | `pg_textsearch` | `pg_search` |
|---|---|---|
| BM25 | Yes | Yes |
| License | PostgreSQL license | AGPL-3.0 community |
| Current version signal | v1.0.0, "Production ready" | stable PGXN release, 0.23.0 as of 2026-04-16 |
| PostgreSQL versions | 17 and 18 | install docs say Postgres 15+ |
| Install model | extension + `shared_preload_libraries` | extension + `shared_preload_libraries` |
| Query shape | ordinary SQL ranking operator in `ORDER BY` | custom operators + `pdb.score(...)` |
| Best fit | focused BM25 ranking on text expressions | embedded search platform inside Postgres |
| Partial indexes | Yes | yes in legacy docs, but only one BM25 index per table is the operative constraint |
| Multiple BM25 indexes on one table | Yes; the official README shows multiple named partial BM25 indexes on one table for multilingual search | docs say only one BM25 index per table |
| Expression indexes | Yes | Yes |
| Phrase queries | No | Yes |
| Facets / aggregates / richer search DSL | No built-in search-specific layer | Yes |
| Tokenizer flexibility | Postgres text search configs | much broader custom tokenizer system |
| Partitioning | supported, but scores are partition-local | supported, with broader distributed-search story |
| Write-path maturity | still calls out write-heavy optimization gaps | richer tuning / LSM model, but heavier operational system |
| Fit to Grover's current lexical API | Strong | Medium |
| Fit to "Grover becomes a built-in search engine" | Medium | Strong |

## Implementation Shape in Grover

### If Grover adopts `pg_textsearch`

This is the cleanest path.

Suggested index:

```sql
CREATE EXTENSION IF NOT EXISTS pg_textsearch;

CREATE INDEX ix_vfs_objects_bm25_live_content
ON vfs_objects
USING bm25 (content)
WITH (text_config = 'simple')
WHERE content IS NOT NULL
  AND deleted_at IS NULL
  AND kind != 'version';
```

Suggested query shape:

```sql
WITH ranked AS (
  SELECT
    path,
    kind,
    content,
    content <@> to_bm25query(:query, 'ix_vfs_objects_bm25_live_content') AS raw_score
  FROM vfs_objects
  WHERE content IS NOT NULL
    AND deleted_at IS NULL
    AND kind != 'version'
    AND (:user_scope IS NULL OR path LIKE :user_scope ESCAPE '\')
)
SELECT path, kind, content, -raw_score AS score
FROM ranked
ORDER BY raw_score ASC, path
LIMIT :k;
```

Grover-specific notes:

- Use `to_bm25query(query, index_name)` explicitly, even outside PL/pgSQL, because Grover will likely want partial indexes and deterministic index selection.
- Negate the operator result before storing it in `Entry.score`.
- Keep the current Python BM25 path for `candidates != None`.
- Add a dedicated prefix-friendly path index if user-scope filtering becomes a bottleneck. A normal unique index on `path` is not always enough for fast `LIKE '/prefix/%'` filtering depending on collation / planner behavior.

Suggested backend changes:

- add `verify_native_bm25_schema()` alongside the current full-text verification,
- gate it behind an explicit backend mode or feature flag so Grover can still run with core Postgres FTS,
- keep current `tsvector` support as the zero-extra-extension fallback.

### If Grover adopts `pg_search`

The minimal path would be something like:

```sql
CREATE EXTENSION IF NOT EXISTS pg_search;

CREATE INDEX ix_vfs_objects_search
ON vfs_objects
USING bm25 (
  id,
  content,
  kind,
  path
)
WITH (key_field = 'id');
```

Then query with ParadeDB operators and `pdb.score(id)`.

But to get the real benefit, Grover would need to lean into ParadeDB's model more aggressively:

- choose tokenizer strategy intentionally,
- include filtering / sorting fields in the covering index,
- decide how `path`, `kind`, `deleted_at`, and maybe ownership metadata should live in the search index,
- accept the one-BM25-index-per-table constraint,
- think about future hybrid search and aggregates in ParadeDB terms rather than Grover-only terms.

That is a valid architecture, but it is not a small substitution for the current `ts_rank_cd(...)` query.

## Operational Notes

### Shared preload requirement

Both extensions require `shared_preload_libraries`, which has an immediate practical consequence:

- if the target deployment is a managed Postgres service that does not let you preload arbitrary extensions, neither option may be available.

In that case, Grover should keep the current built-in Postgres FTS path.

### Vacuum / maintenance

Both systems have maintenance realities.

For `pg_textsearch`:

- memtables live in shared memory,
- `pg_textsearch.memory_limit` is the main safety valve; when pressure stays above the hard cap, inserts fail with an error instead of risking an OOM kill,
- heavy write workloads need memory / spill tuning,
- compaction is currently synchronous.

Two operationally useful details from the official README:

- After bulk loads or sustained incremental inserts, `bm25_force_merge(index_name)` can consolidate segments to improve query speed.
- Grover's existing `lexical_search(query, k)` API is a good fit because `ORDER BY ... LIMIT` is the path that enables Block-Max WAND; without a limit, `pg_textsearch` falls back to scoring more documents.

For `pg_search`:

- writes create segments in an LSM-style structure,
- docs call out that autovacuum / vacuum behavior can affect search performance,
- worker / buffer tuning matters more because the extension is doing more work inside custom scans.

If Grover's workload is mostly read-heavy repository / document search with periodic writes, both are workable. If it becomes a very high-ingest system, operational maturity matters more and should be tested under Grover's real write profile before committing.

## Bottom Line

If I were making the call for Grover today, I would do this:

1. Keep the current built-in Postgres FTS path as the default fallback.
2. Add a new **optional BM25-native path using `pg_textsearch`** for Postgres 17/18 deployments that can install preload extensions.
3. Revisit `pg_search` only if Grover's lexical search requirements expand into:
   - phrase search,
   - fuzzy matching / typo tolerance,
   - snippets / highlighting,
   - custom tokenization for code / partial match,
   - facets / aggregates,
   - join-aware search pushdown,
   - or a broader "search engine inside Postgres" strategy.

The implementation strategy should be **selectable, not destructive**:

- keep native Postgres FTS as the zero-extra-extension fallback,
- add a backend/feature switch for BM25-native lexical search,
- and keep the current Python BM25 candidate-scoped path unchanged.

That avoids forcing a hard migration on deployments that cannot preload extensions, and it keeps Grover honest about which ranking path it is actually using.

In short:

- **`pg_textsearch` is the better BM25 replacement for Grover's current lexical_search.**
- **`pg_search` is the better foundation for a future ParadeDB-shaped search subsystem.**

## Sources

- PostgreSQL 17 docs: [Controlling Text Search](https://www.postgresql.org/docs/17/textsearch-controls.html)
- `pg_textsearch` official repo / README: [timescale/pg_textsearch](https://github.com/timescale/pg_textsearch)
- PostgreSQL news post for `pg_textsearch` v1.0: [pg_textsearch v1.0](https://www.postgresql.org/about/news/pg_textsearch-v10-3264/)
- ParadeDB docs: [Create an Index](https://docs.paradedb.com/documentation/indexing/create-index)
- ParadeDB docs: [BM25 Scoring](https://docs.paradedb.com/documentation/sorting/score)
- ParadeDB docs: [Architecture](https://docs.paradedb.com/welcome/architecture)
- ParadeDB docs: [Limitations & Tradeoffs](https://docs.paradedb.com/welcome/limitations)
- ParadeDB self-hosted extension install: [Extension](https://docs.paradedb.com/deploy/self-hosted/extension)
- PGXN metadata for `pg_search`: [pg_search on PGXN](https://pgxn.org/dist/pg_search/)
- `pg_search` development README inside ParadeDB: [paradedb/paradedb `pg_search` README](https://github.com/paradedb/paradedb/blob/main/pg_search/README.md)
