# Folder grants as ranges: prior art and a measured fix for the many-grant predicate

- **Status:** research memo. Commits us to nothing. Input to spec 058's
  read path (the visibility predicate) and to the partial-caller cost of
  `glean`.
- **Date:** 2026-09-30
- **Owner:** Clay Gendron
- **Question:** A caller with 100 folder grants pays about 440 ms for a
  `glean` on 50,000 files; with 500 grants, about 2 s
  (`studies/2026-09-29-partial-glean-latency/runs/sqlite-50000.md`).
  Two statements do most of that work: the visible-corpus count and the
  vector leg's distance query. Each tests every chunk row against every
  OR'd `LIKE` arm. How do path-shaped permission systems avoid this?
  Can "everything under this folder" become a cheap range? What does
  each range encoding cost when a subtree moves? And what should vfs
  change?
- **Method:**
  1. Executed experiment at 51k and 102k entry rows on SQLite 3.50.4 and
     Postgres 17.11, comparing ten predicate forms for the same rights.
     Every form's answer is asserted equal to a pure-Python truth.
     Study: `studies/2026-09-30-path-acl-ranges/` (`bench.py`,
     `runs/*.md`, `runs/*-plans.md`).
  2. Line-level reading of Apache Jackrabbit Oak's permission evaluation
     and query engine.
  3. Line-level reading of index sorting in Lucene and tantivy.
  4. The tree-encoding literature (nested sets, pre/post numbering,
     Dewey and ORDPATH labels), from the published papers named in §5.
     No paper was re-read for this memo; the claims there are the
     well-known headline results.
- **Sources** (every clone refreshed to its upstream default branch on
  2026-09-30; licence re-checked after the refresh; none was dirty):
  - `jackrabbit-oak` — branch `trunk`, commit `69a8641` (2026-09-30),
    Apache-2.0.
  - `lucene` — branch `main`, commit `4eb488d` (2026-09-30), Apache-2.0.
  - `tantivy` — branch `main`, commit `d5e2842` (2026-09-29), MIT.
    The clone is shallow (88 commits).
  - S1: `2026-09-05-permissions-predicate-at-scale.md` and its study.
  - vfs: `storage/backends/database/rights.py` (`cover_clause`,
    `visibility_clauses`, `_units`, `_owned_beneath`),
    `storage/backends/database/glean.py` (`_visible_corpus`,
    `_visible_chunks`, `_vector_leg`), `storage/grants.py` (`resolve`,
    `Arm`), `models/rows.py`.
  - No code was copied from any reference repo. Citations are
    `file:line` at the commits above.

## Terms used here

- **Arm.** One granted folder, compiled to SQL. Today an arm is
  `path = p OR path LIKE 'p/%'`. A caller's rights are the arms OR'd
  together.
- **Range arm.** The same folder as a byte range:
  `path = p OR (path >= 'p/' AND path < 'p0')`. It works because `0` is
  the byte right after `/`. vfs stores `path` in a bytewise collation,
  so the range is exact.
- **Driving table.** In a join, the table the database reads first. It
  then looks up matching rows in the other table. Which side drives
  decides how many rows the arms are tested on.
- **Semi-join.** A filter of the form
  `d.entry_id IN (SELECT e.id FROM entries e WHERE <arms>)`. It asks the
  database to find the visible entries first, then keep the chunk rows
  that belong to them.
- **Preorder number.** Number every row in tree order: a folder, then
  everything inside it, then the next folder. A folder and its whole
  subtree then hold one unbroken run of numbers, `[pre, pend]`. This is
  the "nested set" idea from the SQL literature.
- **Doc number.** The same idea for the lexical index: number the
  chunk rows of an epoch in preorder, so a folder's chunks are one
  unbroken run of doc numbers.
- **Epoch.** One build of the lexical index. vfs rebuilds it whole on
  `reindex`, so its numbering is fixed until the next build.

## Bottom line

1. **The slowness is a driving-side problem, not a `LIKE` problem.** On
   SQLite, with vfs's `case_sensitive_like = ON`, `LIKE` arms use the
   path index just as well as range arms. Counting 102k entries under
   500 arms costs 13.7 ms with `LIKE` and 10.8 ms with ranges. But once
   the statement joins the chunk table, SQLite drives from the chunks
   and tests every chunk row against every arm. The same 500 arms then
   cost 1,874 ms (`LIKE`) and 1,880 ms (ranges). Changing the arm form
   does nothing there. Changing the statement shape does everything.
2. **A semi-join or a `VALUES` join fixes it without any schema
   change.** On SQLite at 102k rows the visible-corpus count drops from
   458 ms to 6.5 ms at 100 grants (70x) and from 1,874 ms to 36 ms at
   500 grants (52x). The vector leg's shape (a per-row score, ordered,
   limit 10) drops the same way: 441 ms to 6.9 ms, and 1,918 ms to
   38 ms. At 51k rows, the glean bench's size, today's form costs
   221 ms at 100 grants. That matches the 215 ms the glean profile
   measured. The semi-join costs 5.6 ms.
3. **On Postgres, range arms beat `LIKE` arms by 2 to 6 times.**
   Postgres already drives from the entries side. But it re-checks every
   `LIKE` arm as a filter on every row it fetches. Range arms need no
   re-check. Entries count at 500 grants: 196 ms with `LIKE`, 34 ms with
   ranges, 15 ms as a `VALUES` join. This refines S1, which saw the two
   forms tie at about 8 arms.
4. **Numbering chunks in preorder makes a grant set almost free.** If
   an epoch's chunks carry preorder doc numbers, 500 folder grants
   become at most 500 doc-number ranges. The visible-corpus count is
   then 1.2 ms on SQLite and 11 to 14 ms on Postgres, with no join to
   entries. From an in-memory prefix-sum array it is 0.05 ms. Checking
   50,100 candidate chunks for visibility drops from 78 to 177 ms (a
   chunked `IN` join plus an app-side check, today) to 7 to 15 ms (a
   pure-Python bisect over the ranges). A Rust kernel would be faster
   still.
5. **Do not keep a preorder number on the live entries table.** It
   must be renumbered on writes. Inserting one row at the front
   renumbers every row after it: 213 ms on SQLite and 1,053 ms on
   Postgres at 102k rows. Moving a folder to the far end costs the
   same. And it buys nothing on entries: the bytewise `path` is already
   an order key that vfs maintains on every move, and byte-range arms
   on it are as fast as integer ranges. The doc number is worth having
   only inside an epoch, where nothing renumbers it.
6. **The prior art agrees on the parts that matter.**
   - Oak evaluates permissions per node by walking up the ancestors. It
     post-filters query results row by row. Its counts are either exact
     after reading every row or an index estimate that ignores ACLs.
     vfs's SQL pushdown is already better than that.
   - Lucene makes a sort-key range one contiguous run of doc ids per
     segment. It then finds the run by binary search and counts it
     without reading it. That is the doc-number idea, and Lucene's
     answer to updates (new segments plus later merges) is the model for
     keeping it fresh.

## 1. Why today's statement is slow

The visible-corpus count in `_visible_corpus` (`glean.py:743`) is one
aggregate:

    SELECT count(*), sum(dl)
    FROM lex_docs d JOIN entries e ON e.entry_id = d.entry_id
    WHERE d.epoch = :epoch AND (<arm 1> OR <arm 2> OR ...)

The vector leg in `_vector_leg` (`glean.py:582`) has the same `FROM`
and `WHERE`, then orders by distance and takes the top rows.

The query plans show what happens (`runs/sqlite-102210-plans.md`):

- **SQLite, 100 arms:** `SEARCH d USING INDEX ix_docs_entry (epoch=?)`
  and then `SEARCH e USING INTEGER PRIMARY KEY`. SQLite reads every
  chunk row of the epoch. For each one it fetches the entry and tests
  the OR of arms. That is chunks times arms tests. At 10 arms SQLite
  chose the other side and was fast (0.9 ms); somewhere between 10 and
  100 arms its cost model flips.
- **SQLite, semi-join or `VALUES` join:** `SCAN g` (the prefix list),
  then `SEARCH e USING COVERING INDEX ix_path (path>? AND path<?)`, then
  `SEARCH d USING INDEX ix_docs_entry (epoch=? AND entry_id=?)`. One
  index range per grant, then one lookup per visible entry. The work
  grows with grants plus visible rows, not grants times all rows.
- **Postgres, 100 `LIKE` arms:** a `BitmapOr` of index scans on entries
  (good), then a `Bitmap Heap Scan` whose `Filter` repeats the whole OR
  of `LIKE` arms on every fetched row (bad), then a hash join to the
  chunks. With range arms the filter disappears.

## 2. Measured numbers

Corpus: 10 top folders, each holding 200 folders of 50 files (51k run:
100 folders). One chunk per file. Every tenth folder has a sibling file
whose name extends the folder's (`/t00/f000.md` beside `/t00/f000/`);
it sorts inside the byte range `[p, p0)` and tests that no form admits
it by mistake. Entry ids and chunk ids are shuffled, so neither is in
path order by accident. Grants are folder prefixes: 10, 100 or 500
spread evenly, or 100 adjacent folders. Medians of 5 warm runs, in ms.

Forms:

| form | what it is |
|---|---|
| `a_like` | OR of `path = p OR path LIKE 'p/%'` — today |
| `b_range` | OR of `path = p OR (path >= 'p/' AND path < 'p0')` |
| `*_semi` | the arms inside `d.entry_id IN (SELECT e.id ... )`, 200 arms per `UNION` branch |
| `c_values` | the prefixes as a `VALUES` list, joined by byte range `[p, p0)` plus a one-byte check that drops `p.md`-style siblings |
| `c_temp` | the same, with the prefixes in a temp table (fill time included) |
| `c_unnest` | Postgres only: the prefixes as two array binds, `unnest`-ed |
| `d_or` / `d_values` | a preorder number on entries: OR of `pre BETWEEN lo AND hi`, or a `VALUES` join |
| `e_or` / `e_values` / `e_unnest` | chunks numbered in preorder: doc-number ranges, **no join to entries** |
| `g_sums` | the count from an in-memory prefix-sum array over doc numbers; no SQL |

### 2.1 The visible-corpus count (`_visible_corpus`'s shape)

SQLite, 102,210 entries, 100,200 chunk rows:

| form | 10 spread | 100 spread | 500 spread | 100 adjacent |
|---|---|---|---|---|
| no predicate (whole mount) | 41 | 42 | 40 | 41 |
| `a_like` (today) | 0.9 | **458** | **1,874** | 449 |
| `b_range` | 0.8 | 432 | 1,880 | 514 |
| `a_like_semi` | 0.9 | 7.1 | 40 | 7.2 |
| `b_range_semi` | 0.8 | 6.5 | 36 | 6.4 |
| `c_values` | 0.7 | 7.2 | 34 | 7.1 |
| `c_temp` | 0.7 | 6.3 | 32 | 6.9 |
| `d_or` | 0.7 | 110 | 371 | 116 |
| `d_values` | 0.6 | 5.7 | 29 | 6.2 |
| `e_or` | 0.1 | 0.8 | 4.0 | 0.7 |
| `e_values` | 0.0 | 0.2 | 1.2 | 0.2 |
| `g_sums` | 0.001 | 0.009 | 0.045 | 0.001 |

SQLite at 51,110 entries (the glean bench's size): `a_like` 221 ms at
100 grants and 854 ms at 500; `a_like_semi` 6.3 and 37 ms; `c_values`
4.3 and 22 ms; `e_values` 0.2 and 1.2 ms (`runs/sqlite-51110.md`).

Postgres 17, same corpus:

| form | 10 spread | 100 spread | 500 spread | 100 adjacent |
|---|---|---|---|---|
| no predicate | 19 | 19 | 19 | 30 |
| `a_like` (today) | 1.5 | 16 | **185** | 29 |
| `b_range` | 1.3 | 8.0 | 32 | 15 |
| `a_like_semi` | 1.5 | 17 | 94 | 23 |
| `b_range_semi` | 1.2 | 7.7 | 36 | 21 |
| `c_values` | 1.2 | 7.2 | 29 | 15 |
| `c_temp` | 4.0 | 11 | 34 | 27 |
| `c_unnest` | 1.4 | 7.8 | 42 | 18 |
| `d_or` | 6.4 | 8.3 | 21 | 15 |
| `d_values` | 9.3 | 10 | 26 | 19 |
| `e_or` | 0.7 | 4.7 | 86 | 2.7 |
| `e_values` | 0.6 | 1.3 | 14 | 3.0 |
| `e_unnest` | 0.7 | 1.3 | 11 | 2.6 |
| `g_sums` | 0.001 | 0.009 | 0.068 | 0.004 |

What to read from these:

- On SQLite, only the statement shape matters. `a_like` and `b_range`
  are equally slow; every semi-join or join form is 50 to 70 times
  faster.
- On Postgres, the arm form matters. Range arms halve to sixth the
  cost. The semi-join adds nothing, because Postgres already filtered
  entries first.
- `e_or` on Postgres at 500 ranges is slow (86 ms): a `BitmapOr` of 500
  index scans. The same ranges as a `VALUES` join or `unnest` cost 11
  to 14 ms. A long OR list is a poor shape on Postgres even when every
  arm is cheap.
- Temp tables cost a fixed 3 to 10 ms on Postgres (create, `COPY`,
  `ANALYZE`). They win nothing here.

### 2.2 The vector leg's shape (per-row score, order, limit 10)

A computed per-row score stands in for the cosine distance, so the
measurement isolates the predicate.

| form | sqlite 100 | sqlite 500 | postgres 100 | postgres 500 |
|---|---|---|---|---|
| no predicate | 45 | 46 | 33 | 35 |
| `a_like` (today) | **473** | **1,927** | 26 | **203** |
| `b_range` | 441 | 1,918 | 17 | 45 |
| `a_like_semi` | 7.6 | 50 | 24 | 110 |
| `b_range_semi` | 6.9 | 38 | 17 | 45 |
| `c_values` | 6.8 | 45 | 16 | 37 |
| `e_values` | 0.4 | 2.1 | 3.9 | 16 |

The same story: SQLite needs the semi-join; Postgres needs range arms;
`b_range_semi` is the one form that is good on both.

### 2.3 Entries alone (list, glob and the owner scans)

With no chunk join, every form is cheap on SQLite (13.7 ms worst, at
500 `LIKE` arms). On Postgres `a_like` costs 16 ms at 100 arms and
196 ms at 500; `b_range` 6.2 and 34 ms; `c_values` 4.3 and 15 ms.
Full tables in `runs/`.

### 2.4 Which candidate chunks are visible (`_visible_chunks`' job)

50,100 candidate chunk ids (half the corpus), the shape a common term
produces.

| method | sqlite (10 / 100 / 500 grants) | postgres (10 / 100 / 500) |
|---|---|---|
| chunked `IN` join to entries, then `admits` in Python (today) | 78 / 80 / 83 | 177 / 119 / 127 |
| bisect over doc-number ranges, pure Python, no SQL | 8.3 / 12 / 15 | 7.3 / 9.0 / 11 |

Today's method pays the same whatever the grant count, because it
ships every candidate id to the database. Ranges need no round trip.

### 2.5 What a move or insert costs each encoding

One `UPDATE`, rolled back after each run. Entries table of 102,210 rows.

| operation | rows touched | sqlite ms | postgres ms |
|---|---|---|---|
| rename a folder: rewrite `path` of its subtree (vfs today) | 51 | 0.8 | 1.1 |
| rename a top folder: rewrite `path` of its subtree | 10,221 | 39 | 89 |
| move a folder to the far end: dense preorder renumber | 102,209 | 234 | 913 |
| move a folder next door: dense preorder renumber | 102 | 1.0 | 3.5 |
| insert one row at the front: dense preorder renumber | 102,209 | 213 | 1,053 |

A path rewrite touches only the moved subtree. A dense preorder
renumber touches every row between the old and new position. An
insert near the front touches almost the whole table.

## 3. Apache Jackrabbit Oak

Oak is a hierarchical content repository with path-scoped access
control entries (ACEs) and a query engine. It is the closest analogue
to vfs. Paths below are relative to the repo root; **P/** is
`oak-core/src/main/java/org/apache/jackrabbit/oak/security/authorization/permission/`
and **Q/** is `oak-core/src/main/java/org/apache/jackrabbit/oak/query/`.

### 3.1 The permission store

- Oak keeps a hidden copy of every ACE, rearranged for lookup. The
  layout is `rep:permissionStore/<workspace>/<principal>/<hash of the
  access-controlled path>`. Each hash node holds that path's ACEs.
  Hash collisions go into `c0`, `c1`... children.
  `oak-doc/src/site/markdown/security/permission/default.md:80-114`;
  `P/PermissionUtil.java:60-63`.
- A lookup for one path finds the hash child and checks the stored
  path. It does not walk ancestors itself. `P/PermissionStoreImpl.java:80-102`.
- A commit hook rewrites the store. `PermissionHook` diffs the commit
  for changed ACL nodes. `PermissionStoreEditor` rewrites the affected
  principal's hash node and keeps an exact per-principal count,
  `rep:numPermissions`. `P/PermissionHook.java:89-122`;
  `P/PermissionStoreEditor.java:169-250`.

### 3.2 Compiled permissions and the entry cache

- Principals split into users and groups. User entries are consulted
  before group entries. `P/CompiledPermissionImpl.java:102-121,435-445`.
- **The eager cache has two thresholds.** `eagerCacheSize` defaults to
  250 and `eagerCacheMaxPaths` defaults to 10.
  `P/CacheStrategyImpl.java:23-27`. A principal with 10 or fewer
  access-controlled paths is loaded whole. If every principal loads
  whole, or the total is under 250 paths, Oak builds one merged
  path → entries map. `P/CacheStrategyImpl.java:35-73`;
  `P/PermissionCacheBuilder.java:48-121`.
- **Past the thresholds, loading turns lazy.** For each path checked,
  Oak asks the store once per principal that has entries, and remembers
  up to 1,000 misses in an LRU set. `P/PermissionEntryCache.java:54-82`;
  `P/PrincipalPermissionEntries.java:37,59-64`.
- **Evaluation walks up.** The entry iterator goes from the target path
  to `/`, parent by parent, and yields the entries at each level. The
  first entry to decide a privilege bit wins. `P/PermissionEntryProviderImpl.java:95-134`;
  `P/CompiledPermissionImpl.java:313-381`.

So Oak's per-check cost grows with path depth and principal count. It
does not grow with the number of grants. That is the same shape as
vfs's `Rights.admits` (`grants.py:182`), which does a dictionary lookup
per ancestor. vfs's app side is already Oak-shaped. vfs's SQL side is
what grows with grants.

### 3.3 TreePermission: evaluating while walking down

- A `TreePermission` for a child is built from its parent's. Its
  iterator reuses the entries each ancestor already loaded, instead of
  new store lookups. `P/CompiledPermissionImpl.java:486-517,632-673`.
- A node loads its own entries only if it has a `rep:policy` child.
  `P/PermissionCacheBuilder.java:151-156`.
- `canReadAll()` is always false in the default model, because proving
  "the whole subtree is readable" needs subtree knowledge Oak does not
  keep. So every child and child count is filtered.
  `P/ReadStatus.java:79-82`;
  `oak-core/src/main/java/org/apache/jackrabbit/oak/core/SecureNodeState.java:98-150`.
  vfs's `Rights.covers_subtree` answers that question from the arms.

### 3.4 Restrictions

Restrictions narrow one ACE. They are built once, when the entry
loads, and evaluated per entry at check time.
`oak-core/.../authorization/restriction/RestrictionProviderImpl.java:90-128`.

| restriction | matches | as SQL |
|---|---|---|
| `rep:glob` | the ACE path plus a glob; no wildcard means the node and its descendants (`GlobPattern.java:88-111,183-225`) | a prefix range; general globs need a pattern |
| `rep:subtrees` | paths under the ACE path that contain `<subtree>/` or end with it (`SubtreePattern.java:41-83`) | several prefix ranges |
| `rep:itemNames` | the last path segment (`ItemNamePattern.java:45-56`) | `name IN (...)` |
| `rep:ntNames` | the primary node type (`NodeTypePattern.java:49-56`) | a `kind` column |
| `rep:current` | the ACE node itself and named properties (`CurrentPattern.java:139-157`) | `path = p` |

Oak's principal-based module allows only "allow" entries.
`oak-doc/src/site/markdown/security/authorization/principalbased.md:104-106`.
It loads every entry eagerly into a map keyed by effective path, and
unions the bits of each ancestor. No deny logic.
`oak-authorization-principalbased/.../impl/EntryCache.java:55-79`;
`.../PrincipalBasedPermissionProvider.java:257-286`. This is the shape
vfs's additive grants have. vfs's posture holes are the one place it
carves, and a hole is just a range subtracted from a range.

### 3.5 The query engine: post-filtering

- **Oak filters every result row after the index returns it.** For each
  row, it asks the session's secure tree whether the path exists.
  `Q/ast/SelectorImpl.java:528-573` (the check itself at `:563`).
- **No index pushes ACLs down.** Lucene and Elastic indexes consult
  access only for suggestions, spellcheck and facets, also after the
  fact. `Q/index/FilterImpl.java:639-642`;
  `oak-lucene/.../LuceneIndex.java:432,455`.
- **Counts are exact only by reading every row.** Without
  `fastQuerySize`, `getSize()` prefetches up to 100 rows. It returns an
  exact count only if the result ends there; otherwise it returns −1.
  `oak-jcr/src/main/java/org/apache/jackrabbit/oak/jcr/query/PrefetchIterator.java:103-146`.
  With `fastQuerySize` on, the index answers, and the docs say plainly
  that "ACLs are not applied to the results". `oak-doc/src/site/markdown/query/query-engine.md:280-285`.
- **Read limits count rows before the ACL check.** `queryLimitReads`
  (default 100,000) counts index rows traversed, so a caller who sees
  little can still hit it. `Q/QueryEngineSettings.java:53-60`.
- Facets have a secure mode (default), a statistical mode that samples
  1,000 docs and scales, and an insecure mode.
  `oak-search/.../FulltextIndexConstants.java:386-395`.

### 3.6 Caching and invalidation

- Every commit, refresh or rebase calls `PermissionProvider.refresh()`,
  which throws away the compiled state. All caches are per session.
  `oak-core/.../core/MutableRoot.java:234-266`;
  `P/CompiledPermissionImpl.java:144-156`.
- After a refresh the eager threshold drops to 250 paths, because
  reloading large sets on every refresh hurt (OAK-9203, cited in a code
  comment). `P/CacheStrategyImpl.java:38-42`.
- Closed user groups (CUGs) keep a cheap "does this subtree hold any
  CUG" counter at the root, and give up above 10.
  `oak-authorization-cug/.../impl/TopLevelPaths.java:35,55-95`.

**What Oak teaches vfs.** Oak expects few ACEs per principal and pays
per row at query time. It has no range trick. Its counts are either
slow or leak hidden rows. vfs already does the harder, better thing:
it pushes rights into SQL so counts are exact. The lesson is to keep
that, and make the pushed predicate cheap.

## 4. Lucene and tantivy: index sorting

Paths below: Lucene `core/` means `lucene/core/src/java/org/apache/lucene/`.

### 4.1 Lucene makes a sort-key range contiguous

- **Index sorting.** `IndexWriterConfig.setIndexSort` fixes a sort
  order for the index. It accepts string and numeric sort fields.
  `core/index/IndexWriterConfig.java:505-515`;
  `core/search/SortField.java:569-600`.
- **At flush,** Lucene computes a permutation (`Sorter.DocMap`) and
  writes every structure through it.
  `core/index/IndexingChain.java:249-297`; `core/index/Sorter.java:50-59`.
- **At merge,** already-sorted segments are merge-sorted with a
  priority queue. The sort can never change after creation.
  `core/index/MultiSorter.java:41,117-138`;
  `core/index/IndexWriter.java:1213-1229`.
- **Doc ids are per segment.** So a key range is one contiguous run per
  segment, not one run for the whole index.
  `core/search/TopFieldCollector.java:54-59`.

### 4.2 What the contiguous run buys

- **Find the run by binary search.**
  `IndexSortSortedNumericDocValuesRangeQuery` finds the first and last
  matching doc by two binary searches over doc ids, then returns
  `DocIdSetIterator.range(min, max)`.
  `core/search/IndexSortSortedNumericDocValuesRangeQuery.java:535-607,649-707`.
- **Count without reading.** Its `count()` returns `max − min`, but only
  when the segment has no deletions. Deleted docs would sit inside the
  run. Same file `:178-219`.
- **String keys too.** `SortedSetDocValuesRangeQuery` does the same for
  a string primary sort through a doc-values skipper.
  `core/document/SortedSetDocValuesRangeQuery.java:121-130`;
  `core/document/SortedSkipperScorerSupplier.java:83-131`.
- **A range is the cheapest doc-id set.** `advance()` is O(1) and the
  whole run is reported at once. `core/search/DocIdSetIterator.java:47,75-104`.
  Intersecting it with a posting list is a leapfrog of `advance()` calls.
  `core/search/ConjunctionDISI.java:166-200`.

### 4.3 Other Lucene answers to "under this folder"

- **Ancestor terms.** `PathHierarchyTokenizer` indexes `/a/b/c` as the
  terms `/a`, `/a/b`, `/a/b/c`. "Under folder X" becomes one term
  query, and its count is the term's document frequency.
  `lucene/analysis/common/src/java/org/apache/lucene/analysis/path/PathHierarchyTokenizer.java:28-45`;
  `core/search/TermQuery.java:255-265`. The cost is one extra posting per
  ancestor per doc, and a move must rewrite them.
- **Filter caching.** `LRUQueryCache` caches a repeated filter as a
  per-segment bitset, dropped when the segment goes away. It is off by
  default since Lucene 11. `core/search/LRUQueryCache.java:580-591,1133-1135`;
  `core/search/IndexSearcher.java:81-84`.

### 4.4 tantivy

- tantivy has `IndexSettings.sort_by_field` on a fast field of type
  i64, u64, f64, date, string or bytes. `src/index/index_meta.rs:231-240`;
  `src/index/index.rs:305-345`. The writer sorts each segment when it
  finalizes; the merger k-way merges sorted segments.
  `src/indexer/segment_writer.rs:105-135`; `src/indexer/merger.rs:386-469`.
- Its CHANGELOG records index sorting as removed in 0.24
  (`CHANGELOG.md:113`), yet `main` has it again. The shallow clone does
  not show when it returned.
- **tantivy's queries do not use the sort.** Its fast-field range query
  scans value blocks linearly; nothing reads `sort_by_field`.
  `src/query/range_query/fast_field_range_doc_set.rs:43-146`. So tantivy
  has the ordering but not the binary-search payoff.

**What Lucene teaches vfs.** Order the docs so a folder is one run,
find the run by binary search, count it by subtraction, and intersect
it with postings by skipping. Keep the order fixed inside an immutable
unit (a segment; for vfs, an epoch). Handle changes by adding a new
unit and re-sorting at merge, never by renumbering in place.

## 5. Encodings that make "under this folder" a range

| encoding | the subtree test | insert | move / rename a subtree of k rows | notes |
|---|---|---|---|---|
| **Bytewise path** (vfs today) | `path = p OR path in [p/, p0)`: two index probes | O(1) | rewrite k paths (measured: 0.8 ms for 51 rows, 39 to 89 ms for 10k) | Already maintained. Almost preorder: `p.md` sorts between `p` and `p/`, so a subtree is the point `p` plus one range, not one range. |
| **Tree sort key** (path with the separator mapped to the lowest byte) | one range `[p, p‹next›)` | O(1) | rewrite k keys | Makes a subtree exactly one range. A second key column for a one-bind saving; not worth it on its own. |
| **Dense preorder / nested set** (Celko's `lft`/`rgt`; Grust's pre/post plane, SIGMOD 2002) | `pre BETWEEN lo AND hi` | renumber every later row (measured: 213 ms SQLite, 1,053 ms Postgres at 102k) | renumber every row between old and new position (measured: 234 to 913 ms end to end) | Fast reads, O(n) writes. Built for read-mostly XML stores. |
| **Gapped or variable-length labels** (ORDPATH, O'Neil et al., SIGMOD 2004; Dewey order, Tatarinov et al., SIGMOD 2002) | a range on the label | O(1) amortized: insert into a gap or extend the label | relabel the k moved rows | Solves inserts, not moves. vfs's path is already a Dewey-like label. |
| **Closure table** (ancestor, descendant) | `ancestor = p` | depth rows | delete and re-add k × depth rows | Exact and indexable. Rows grow with depth. S1 ruled out a per-principal materialisation; a per-entry closure is smaller, but still multiplies writes. |
| **Epoch-local doc numbers** (Lucene's model) | `doc_no BETWEEN lo AND hi`, or a bisect in memory | nothing until the next build | nothing until the next build; the moved rows' numbers go stale | No write cost. Needs a rule for rows that changed since the build. |

The pattern across the table: **every encoding that makes a subtree
one range pays O(k) or more on a move.** vfs already pays O(k) to
rewrite `path`. So the path is the right live order key. An extra
integer only earns its keep where there is no path at all — the chunk
rows of the lexical index — and only where nothing renumbers it: inside
an epoch.

## 6. What the arms look like as ranges

A caller's rights are arms with holes (`grants.py:111`). As ranges:

- An arm on `p` is the point `p` plus the byte range `[p/, p0)`.
- A hole `h` under `p` removes the point `h` and `[h/, h0)`. Rows like
  `h.md` stay, because they sit beside `h`, not under it. So one arm
  with one hole becomes a few disjoint ranges.
- The union of all arms, minus holes, is a **sorted list of disjoint
  ranges.** Overlap disappears.

That last point matters today. `_visible_corpus` says per-clause counts
cannot be summed, because clauses overlap, so a multi-clause caller
reads every visible row back (`glean.py:743-771`). Disjoint ranges add.
With them, a caller whose rights fan into several clauses still gets
one aggregate per clause, summed. Owner arms (`OwnerArm`) are not path
ranges; they stay a separate residual predicate.

## Recommendations

1. **Change the statement shape now (no schema change).** Where a
   chunk-side table joins entries under a partial view — the
   visible-corpus count and the vector leg — put the arms in a
   semi-join: `d.entry_id IN (SELECT e.entry_id FROM entries e WHERE
   <arms>)`. On SQLite this is the 50 to 70 times win. It is plain
   portable SQL, and every engine vfs supports has semi-join plans for
   `IN (subquery)`; the `db_test` legs should confirm the plans.
2. **Compile arms as byte ranges, not `LIKE`.** `path = p OR (path >=
   'p/' AND path < 'p0')`. This is the form `_owned_beneath` already
   uses (`rights.py:719-748`). On Postgres it is 2 to 6 times faster at
   100 to 500 arms. It needs no `LIKE` escaping. It costs 3 binds per
   arm instead of 2; the clause fan already budgets binds per unit.
3. **Normalize rights to sorted, disjoint ranges before compiling.**
   Then clause results add, and the multi-clause row read-back in
   `_visible_corpus` goes away. The same normal form feeds
   recommendation 5.
4. **Keep a `VALUES` join as a dialect option, not the default.** It is
   the fastest SQL form on both engines (SQLite 34 ms, Postgres 29 ms
   at 500 grants). But S1 found a `VALUES` join slower than `IN` on SQL
   Server for read-only join-backs, and this study did not run MariaDB,
   SQL Server or Oracle. The semi-join with range arms is within about
   25% of it everywhere measured, and sometimes faster. Do not use temp
   tables (a fixed 3 to 10 ms on Postgres).
5. **Prototype epoch-local preorder doc numbers.** At lexical build,
   stream chunks in tree order and number them. Store, per epoch, each
   directory's doc range: a nested set frozen for the epoch's life.
   Then:
   - rights become doc ranges by one lookup per arm prefix;
   - the visible-corpus count is a prefix-sum subtraction in memory
     (under 0.1 ms) or a `doc_no BETWEEN` join (1 to 14 ms);
   - the visible-chunk check and the posting-block filter become range
     intersections in the Rust kernel, with no round trip (today
     80 to 180 ms for 50k candidates, whatever the grant count);
   - a posting block whose doc span misses every range can be skipped
     unread, which is Lucene's `advance()` over a range.

   The open design question is staleness. A move after the build
   leaves the moved chunks with numbers that belong to their old
   folder. Lucene's answer is delete-plus-add: treat changed rows as
   outside the ordered unit. vfs has the pieces: the `NOT encoded`
   overlay already scores rows the epoch does not reflect. A move could
   mark its subtree the same way for the ranged view, checked by exact
   path, until the next reindex. That must be designed and measured
   before anything is decided.
6. **Do not add a live preorder number, nested set or closure table to
   entries.** Every one of them pays O(n) or O(k × depth) per write or
   move, and on entries none beats byte ranges on `path`.

### What to prototype in the glean bench

- **P1 (shape only):** `cover_clause` as range arms, `_visible_corpus`
  and `_vector_leg` as semi-joins. Rerun
  `studies/2026-09-29-partial-glean-latency/bench.py` at 50k on SQLite
  and Postgres. Expect the two statements that cost about 427 ms at
  100 grants to cost about 10 ms together. Then see what is left: the
  grant-independent `_visible_chunks` round trip is the likely next
  cost.
- **P2 (disjoint ranges):** normalize rights to disjoint ranges, sum
  per-clause aggregates, and rerun the 500-grant caller (3 clauses
  today).
- **P3 (doc numbers):** number one epoch's chunks in preorder, keep the
  directory → doc-range map, and replace `_visible_corpus` and
  `_visible_chunks` with range arithmetic. Measure with the Rust
  intersection kernel, and measure a move-then-glean to size the
  staleness rule.

## Caveats

- One chunk per file, uniform folder sizes, and grants spread evenly.
  Real grant sets cluster, which helps ranges: 100 adjacent folders
  coalesced into 10 doc ranges here, broken only by the sibling files.
- SQLite and Postgres only. MariaDB, SQL Server and Oracle plan
  semi-joins well in general, but this study did not run them. The
  `db_test` legs should confirm recommendation 1 before it ships.
- The vector leg was measured with a computed score, not a real cosine
  distance. The predicate cost is what the measurement isolates; the
  distance computation adds the same amount to every form.
- The SQLite plan flip happened between 10 and 100 arms here. It
  depends on the planner's statistics, so the exact threshold will
  move; the semi-join removes the dependence.

## One-line version

The many-grant slowdown is the database testing every chunk against
every folder arm; run the arms on entries first (a semi-join with byte
ranges — 458 → 6.5 ms at 100 grants, 1,874 → 36 ms at 500 on SQLite),
normalize rights to disjoint ranges, and prototype Lucene-style
preorder doc numbers inside each lexical epoch, where a folder becomes
one range and visibility becomes arithmetic.
