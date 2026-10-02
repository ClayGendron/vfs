# Permission-filtered search at scale: how search engines keep document-level security fast as a user's access list grows

- **Status:** research memo (commits us to nothing). Answers topic A of
  the partial-glean latency follow-up: the bench
  (`studies/2026-09-29-partial-glean-latency/`) showed `glean` for a
  partial caller climbing from about 45 ms (whole mount) to 440 ms at
  100 grants and 2 s at 500 grants on SQLite with 50,000 files.
- **Date:** 2026-09-30
- **Owner:** Clay Gendron
- **Question:** Where do real search systems compute the permission
  filter, how does its cost scale with the number of grants, roles or
  groups, what do enterprise products do (early binding vs late
  binding), how do they treat ranking statistics under document-level
  security, and what should vfs adopt?
- **Method:** three parallel read-only studies (OpenSearch Security's
  DLS source; Lucene's and tantivy's filter, cache, index-sort and kNN
  code; vendor documentation for Elasticsearch, OpenSearch, SharePoint /
  Microsoft Search, Azure AI Search, Google Cloud Search, Glean, Coveo
  and Solr), and four executed experiments on vfs's own table shapes, on
  SQLite 3.50.4 and on Postgres 17.11 + pgvector 0.8.6 (the docker test
  container):
  `studies/2026-09-30-search-document-level-security/` (`results.md`,
  `filter_shapes.py`, `join_variants.py`, `filter_shapes_pg.py`,
  `pg_variants.py`, `scale_ordinal.py`). Nothing under `src/` or
  `tests/` was touched.
- **Sources (clones):** `apache/lucene` refreshed to `origin/main` @
  `4eb488d` (2026-09-30, Apache-2.0); `quickwit-oss/tantivy` refreshed to
  `origin/main` @ `d5e2842` (2026-09-29, MIT);
  `opensearch-project/security` cloned 2026-09-29 @ `75f5c204`
  (`origin/main`, Apache-2.0). Licences re-checked after the refresh.
  None was dirty. Study only; nothing copied.
- **Sources (web, read 2026-09-30):** Elasticsearch document- and field-level security,
  <https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/controlling-access-at-document-field-level>,
  its limitations snippet,
  <https://raw.githubusercontent.com/elastic/docs-content/main/deploy-manage/_snippets/field-doc-sec-limitations.md>,
  security settings (`xpack.security.dls.bitset.cache.*`),
  <https://www.elastic.co/guide/en/elasticsearch/reference/current/security-settings.html>,
  the `terms` query, <https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-terms-query>,
  PRs <https://github.com/elastic/elasticsearch/pull/43669> and
  <https://github.com/elastic/elasticsearch/pull/50535>;
  Elastic connectors DLS, <https://www.elastic.co/docs/reference/search-connectors/es-dls-overview>,
  <https://www.elastic.co/docs/reference/search-connectors/es-dls-e2e-guide>,
  and the SharePoint Online connector's `expand_site_group_members`,
  <https://raw.githubusercontent.com/elastic/elasticsearch/main/docs/reference/search-connectors/es-connectors-sharepoint-online.md>;
  OpenSearch DLS,
  <https://raw.githubusercontent.com/opensearch-project/documentation-website/main/_security/access-control/document-level-security.md>;
  SharePoint custom security trimming,
  <https://github.com/SharePoint/sp-dev-docs/blob/main/docs/general-development/custom-security-trimming-for-search-in-sharepoint-server.md>,
  crawl best practices, <https://learn.microsoft.com/en-us/sharepoint/search/best-practices-for-crawling>,
  SharePoint Online limits,
  <https://learn.microsoft.com/en-us/office365/servicedescriptions/sharepoint-online-service-description/sharepoint-online-limits>;
  Microsoft Graph connectors items, external groups and limits,
  <https://learn.microsoft.com/en-us/graph/connecting-external-content-manage-items>,
  <https://learn.microsoft.com/en-us/graph/connecting-external-content-external-groups>,
  <https://learn.microsoft.com/en-us/graph/connecting-external-content-api-limits>;
  Azure AI Search security trimming, `search.in`, document-level access,
  query-time enforcement, push-API ACLs and the SharePoint indexer,
  <https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search>,
  <https://learn.microsoft.com/en-us/azure/search/search-query-odata-search-in-function>,
  <https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview>,
  <https://learn.microsoft.com/en-us/azure/search/search-query-access-control-rbac-enforcement>,
  <https://learn.microsoft.com/en-us/azure/search/search-index-access-control-lists-and-rbac-push-api>,
  <https://learn.microsoft.com/en-us/azure/search/search-indexer-sharepoint-access-control-lists>;
  Google Cloud Search ACLs and the items API,
  <https://developers.google.com/workspace/cloud-search/docs/guides/acls>,
  <https://developers.google.com/workspace/cloud-search/docs/reference/rest/v1/indexing.datasources.items>;
  Google Search Appliance feeds guide,
  <https://www.google.com/support/enterprise/static/gsa/docs/admin/current/gsa_doc_set/feedsguide/feedsguide.html>,
  and file-system connector 3.x release notes,
  <https://raw.githubusercontent.com/googlegsa/filesystem.v3/3.2.4/projects/file-system-connector/RELEASE_NOTES>;
  Vertex AI Search access control,
  <https://docs.cloud.google.com/generative-ai-app-builder/docs/data-source-access-control>;
  Glean security principles, indexing-API permissions, crawl refresh
  rates and identity blog,
  <https://docs.glean.com/security/security-principles>,
  <https://developers.glean.com/api-info/indexing/documents/permissions>,
  <https://docs.glean.com/connectors/crawling-refresh-rates>,
  <https://www.glean.com/blog/using-our-identity-schema-to-deliver-personalized-permissions-aware-results>;
  Coveo early binding, permission model and security identity cache,
  <https://docs.coveo.com/en/1719/>, <https://docs.coveo.com/en/25/>,
  <https://docs.coveo.com/en/2007/>, <https://docs.coveo.com/en/1527/>;
  New Idea Engineering on early vs late binding (2005, archived),
  <https://web.archive.org/web/2015/http://www.ideaeng.com/security-eprise-search-p2-0305>;
  Sinequa, <https://www.sinequa.com/resources/blog/data-access-security-management-the-enterprise-search-challenge/>;
  Solr filter caching and custom security post-filters (Lucidworks,
  archived), <https://web.archive.org/web/2020/https://lucidworks.com/post/advanced-filter-caching-in-solr/>,
  <https://web.archive.org/web/2019/https://lucidworks.com/post/custom-security-filtering-in-solr/>;
  Solr terms and join parsers,
  <https://solr.apache.org/guide/solr/latest/query-guide/other-parsers.html>,
  <https://solr.apache.org/guide/solr/latest/query-guide/join-query-parser.html>;
  Lucidworks Fusion AD ACLs, <https://doc.lucidworks.com/docs/fusion-connectors/concepts/ad-acl>
  (the trimming stage's cache settings seen only in a search snippet,
  partially verified). Glean engineering internals (caching,
  "real-time permissions", ranking statistics): no public write-up
  found, unverified.

## Bottom line

1. **vfs already does the cheap half of what enterprise search does.**
   Every product studied stores permissions *with the documents* and
   adds the caller's identities to the query ("early binding"). The
   products that make a folder change cheap store a **reference** to
   the folder's permissions, not a copy on every child. vfs's
   prefix grant is exactly such a reference: the path is the
   permission key, and a grant on a folder with 100,000 files is one
   row. Products that copy permissions onto each child pay a re-crawl
   of every item beneath the folder. vfs must not move toward that.
2. **Our slowness is the shape of the SQL, not the number of grants.**
   OR'd `LIKE` arms make the engine test every arm against every row.
   On SQLite that is `rows × grants`: 230 ms at 100 grants, 937 ms at
   500 and 10.8 s at 5,000 single-file grants (50,000 chunks). The same
   rights sent as a list of byte ranges and *joined* to the path index
   cost 4, 26 and 16 ms. Postgres evaluates arms faster but grows the
   same way (15 → 148 → 290 ms); one array-bind range join stays at
   21–36 ms. This is the fix with the most leverage, and it needs no
   schema change.
3. **Real engines make filter cost independent of grant count in three
   ways**, and vfs can use all three:
   - they **compile the filter once into a set of documents** and cache
     it per index segment (Lucene's query cache, Elasticsearch's DLS
     bitset cache);
   - they **sort the index** so a filter on the sort key is a
     contiguous id range found by binary search (Lucene's index-sorted
     range query: two binary searches, cost independent of hits);
   - for vector search they **decide pre-filter vs post-filter from the
     filter's size** (Lucene's kNN query: exact search when the filter
     admits ≤ k docs, graph search with a visit limit otherwise).
4. **Nobody filters ranking statistics except the research papers.**
   Elasticsearch documents that DLS "doesn't affect global index
   statistics". OpenSearch's DLS reader passes `numDocs`, `terms()` and
   `docFreq` straight through. vfs's visible-set statistics (ADR 065
   rule 5) remain stricter than the field. The price of that rule is
   the visible count, which path-ordered ordinals turn into two index
   seeks per range (0.06 ms flat at 50,000 and 500,000 chunks).

## 1. Terms used in this memo

- **Document-level security (DLS):** hiding whole documents from a
  caller inside a search engine. vfs's row grants are DLS.
- **ACL (access control list):** the list of who may read a document.
- **Early binding:** the ACL is stored in the index next to each
  document, and the query itself carries the caller's identities as a
  filter. The engine never returns a hidden document.
- **Late binding (post-filtering):** the engine returns candidates and
  a second step checks each one against the source system. vfs's
  final `Rights.admits` check is late binding, used as a safety net on
  top of an early-bound SQL predicate.
- **Security trimming:** Microsoft's name for DLS. **Pre-trimming** is
  early binding; **post-trimming** is late binding.
- **Bitset:** one bit per document, 1 if the filter admits it. A
  bitset for 1 M documents is 125 KB.
- **Segment:** Lucene's and tantivy's unit of an immutable index
  slice. vfs's closest analogue is a lexical **epoch** (ADR 055).
- **Arm:** one OR'd piece of vfs's compiled predicate, `path = :p OR
  path LIKE :p/%`.
- **Byte range:** the half-open interval `[p/, p0)`. Because `0` is the
  byte after `/`, every path under `p` sorts inside it. vfs already
  uses this trick in `_owned_beneath`
  (`src/vfs/storage/backends/database/rights.py:729-731`).
- **Ordinal:** a chunk's position in path order within an epoch.

## 2. Where real systems compute the filter (question 1)

| system | where the filter is built | cached? keyed by | invalidated by |
|---|---|---|---|
| Lucene core | per query, per segment, from the filter `Query` | optional `LRUQueryCache` (off by default, `IndexSearcher.java:82-84`), one doc-id set per (query, segment core key) (`LRUQueryCache.java:423-427, 827, 834`) | segment close; deletes do **not** invalidate, live docs are applied separately as `acceptDocs` (`IndexSearcher.java:851-852`) |
| Lucene join `QueryBitSetProducer` | per segment | weak map by segment core key (`QueryBitSetProducer.java:38, 63-67`) | GC of the segment |
| Elasticsearch DLS | role queries OR'd, run per segment | **DLS bitset cache**, per (rendered role query, segment); LRU, 10 % of heap, 2 h idle TTL | segment close, role-cache clear, TTL |
| OpenSearch Security | role queries OR'd as `SHOULD` clauses (`DlsRestriction.java:65-95`), recomputed on every request; config compiled to precomputed index→role→rule maps (`AbstractRuleBasedPrivileges.java:648-726, 816-889`) | no per-user cache in the plugin; searches are a query rewrite (`DlsFlsValveImpl.java:545-575`), so reuse falls to core's query cache (inferred) | config swap (`PrivilegesConfiguration.java:151-209`) |
| Solr | `fq` per query | `filterCache` per filter string; Lucidworks advises `cache=false` or a post-filter for per-user ACL filters | commit |
| SharePoint Server | pre-trimming: the query is rewritten with the user's SIDs/claims | internal, undocumented | crawl |
| Azure AI Search | security filter `search.in(group_ids, …)`, or (preview) the caller's token resolved through Microsoft Graph at query time | internal; "initial ACL-based queries might experience higher latency… due to caching" | not stated |
| Google Cloud Search | item ACLs with inheritance chains, "evaluated from leaf to root" at query time | not stated | item update |
| Glean | mirrored ACLs and groups; "at query time, Glean evaluates the signed-in user's identity against those mirrored permissions" | not stated | periodic crawls (e.g. Confluence identity crawl every 8 h) |
| Coveo | early binding; a **security identity cache** expands a user into every parent identity | identity graph, refreshed daily by default | identity refresh (groups), crawl (item permissions) |
| **vfs today** | per call, rights resolved in app code and compiled to OR'd arms | resolved rights cached by `(subjects, grant_revision)` (`RightsCache`, `rights.py:113-129`); the compiled SQL is not | a grant write bumps the revision |

Three patterns stand out.

- **The permission model is resolved in app code and cached by a
  version number.** OpenSearch precompiles roles into lookup maps and
  swaps the whole structure on config change. vfs's `RightsCache`
  keyed by `(subjects, grant_revision)` is the same design. Nothing to
  change here.
- **The document set is cached per immutable index slice.** Lucene and
  Elasticsearch key on the segment, so a new segment gets fresh
  entries and old ones age out. Deletes never invalidate: they are a
  separate "live docs" bitset applied last. vfs's epoch is the
  analogue of a segment.
- **Per-user caches flood.** Elastic had to change the DLS bitset
  cache from "small size, long lifetime" to "large size, short
  lifetime" (PR 50535) because templated per-user role queries made
  one entry per user. OpenSearch renders `${user.name}` per request
  and caches nothing (`DocumentPrivileges.java:157-192`). Lesson: key a
  cache by the *resolved permission set*, not by the user. Two users
  with the same groups should share one entry.

## 3. How cost scales with grants, roles and groups (question 2)

### 3.1 What the engines do

- **A big OR of ACL terms** (`TermInSetQuery` in Lucene) sorts the terms
  once and walks the term dictionary in order
  (`TermInSetQuery.java:123-160, 258-296`). Up to 16 terms it becomes a
  boolean OR; above that it pours small postings into one bitset
  (`AbstractMultiTermQueryConstantScoreWrapper.java:42-43`;
  `MultiTermQueryConstantScoreBlendedWrapper.java:40, 60-120`). Cost is
  one dictionary seek per term plus the postings of matching terms.
  It grows with the number of terms, but gently: seeks, not scans.
- **Microsoft publishes the only hard numbers.** Azure's `search.in`
  gives "sub-second response time" for "hundreds or thousands of
  values", but "latency will grow as the number of values grows".
  Writing the same filter as OR'd equalities "slows down query
  response time by many seconds". Graph connectors: fewer than 2,049
  external groups per user, and more than 10,000 fails with a 400.
- **What makes cost independent of the count** is either a cache (the
  filter's document set is built once and reused) or a sorted index
  (the filter is a range, found by binary search). Lucene's
  `IndexSortSortedNumericDocValuesRangeQuery` does two binary searches
  and returns a dense doc-id range; `count()` is `max − min`
  (`IndexSortSortedNumericDocValuesRangeQuery.java:69, 178-218,
  555-590, 603, 659-660`). tantivy can sort an index by a field
  (`index_meta.rs:232-235`) but has no range shortcut and no filter
  cache (`fast_field_range_doc_set.rs:95-143`;
  `automaton_weight.rs:87-111` rebuilds a bitset every query).

### 3.2 What vfs does, measured

The executed study (`studies/2026-09-30-search-document-level-security/results.md`)
builds vfs's table shapes (entries, `lex_docs`, chunks) with 50,000
files, written in shuffled order as a live mount would be. It times the
two statements the latency bench named as the cost: the visible-corpus
count and the vector leg. All methods return identical answers.

**SQLite 3.50.4, visible-corpus count, ms:**

| caller | visible | OR'd LIKE arms (today) | range join | ordinal seeks |
|---|---|---|---|---|
| 1 grant | 5,000 | 4.7 | 4.1 | 0.07 |
| 100 grants | 5,000 | 230.2 | 4.2 | 0.58 |
| 500 grants | 25,000 | 937.1 | 26.1 | 3.02 |
| 5,000 file grants | 5,000 | 10,787.0 | 16.5 | 29.99 |

The 230 ms at 100 grants reproduces the latency bench's 215 ms. So the
standalone study captures the real cost.

Why: at 100 grants SQLite's plan drives from `lex_docs`, looks up each
row's entry, and tests every arm on every row. Spelling the arms as
byte ranges does not help (212.6 ms), because the plan is the same.
Forcing SQLite to start from `entry` gets its multi-index OR and helps
at 100 grants (18.6 ms) but not at 500 (242 ms). Only the **join**
shape, where the ranges are rows and the path index is searched once
per range, is flat.

**Postgres 17 + pgvector, ms:**

| caller | OR'd LIKE arms | range join, 2 array binds (`unnest`) | ordinal seeks via `unnest` |
|---|---|---|---|
| 1 grant | 6.3 | 13.4 | 4.9 |
| 100 grants | 14.6 | 20.7 | 9.2 |
| 500 grants | 147.6 | 36.0 | 20.2 |
| 5,000 file grants | 289.6 | 34.8 | 99.9 |

Postgres hash-joins and tests each arm once per entry row, quickly. But
it still grows with grants × rows. The array-bind join is one
statement with two binds at any grant count, and stays flat. A warning
from the same run: the portable alternative, an inline `VALUES` list
split every 500 ranges to respect SQL Server's bind cap, planned badly
at 20 slices (each slice hash-joined the whole chunk table; the vector
leg took 1.8 s). The row source must be one statement where the engine
allows it.

**The join still grows with visible rows; the ordinal does not**
(SQLite, `scale_ordinal.py`):

| chunks | caller | visible | range join | ordinal seeks |
|---|---|---|---|---|
| 50,000 | 1 grant | 5,000 | 3.9 | 0.06 |
| 500,000 | 1 grant | 50,000 | 82.8 | 0.06 |

**The vector leg** (SQLite, ms; whole mount unfiltered: 32.6):

| caller | OR'd LIKE arms | range join |
|---|---|---|
| 100 grants | 21.7 | 6.9 |
| 500 grants | 264.4 | 35.6 |
| 5,000 file grants | 145.9 | 17.2 |

On Postgres a third option was tried: run the whole-mount vector
statement unfiltered and check the caller's ranges in Python on the
rows it returns, deepening the window 4× until 10 visible rows arrive
(post-filtering). It cost 41–63 ms when the caller sees 10–50 % of the
mount, but 187 ms at 0.5 % visible, where it needed a 10,240-row
window. Pre-filtering (the join) is the opposite: cheap when the caller
sees little. This is exactly the trade Lucene's kNN query settles by
the filter's size (`AbstractKnnVectorQuery.java:244-302`: the filter is
evaluated first; if it admits no more than k documents the search is
exact over them; otherwise graph search runs with a visit limit and
falls back to exact).

## 4. Early binding vs late binding (question 3)

### 4.1 What the products do

**Every product studied uses early binding.** The differences are in
how the ACL is stored.

| product | ACL stored as | a grant on a folder with 100 k items beneath it costs |
|---|---|---|
| SharePoint Server | expanded per item; SharePoint-group changes force a "security-only crawl, which updates all affected items" | a re-crawl of every affected item; Microsoft advises AD groups because they "don't require the crawler to update the affected items" |
| Azure AI Search, SharePoint indexer | "computes the effective ACL for each file"; each chunk carries its own copy | parent-scope change is "Detected automatically: No"; call `/resync` with `permissions`; until then "the index serves stale ACL data" |
| Elastic connectors DLS | `_allow_access_control` identity list on each document, plus one access document per user | a content sync of every document beneath; the SharePoint connector added compact `site_group:` tokens because expanding members "for large site groups" was too costly |
| Google Cloud Search | `readers` / `deniedReaders` plus `inheritAclFrom` a parent item, with `CHILD_OVERRIDE`, `PARENT_OVERRIDE`, `BOTH_PERMIT` | rewrite the folder item only (inferred; Google's GSA connector notes say inheritance reduces "the number of files/directories that must be re-indexed as a result of an ACL change to a folder") |
| Coveo | permission **levels** of allowed/denied sets on each item; groups expanded by a security identity cache | a group change is an identity refresh, not a re-crawl; item permission changes are crawled |
| Glean | `allowedUsers` / `allowedGroups` on documents; groups and memberships indexed separately | group changes are cheap; propagation follows each connector's crawl cadence ("might be a small delay") |
| Graph (Copilot) connectors | ACL entries on items, grant/deny, deny wins; "external groups" as an indirection layer | group changes are cheap; item ACLs re-pushed |
| Vertex AI Search | flat `readers` per document, up to 3,000 | every document beneath (no inheritance documented) |

The vendors' own case for early binding is performance and
correctness of counts. SharePoint: "We recommend the use of
pre-trimming for performance and general correctness; pre-trimming
prevents information leakage for refiner data and hit count." Sinequa:
late binding hurts "query time" and "the consistency of pagination,
metadata counts". The classic worked example (New Idea Engineering,
2005): a user who sees 10 % of the content forces about 100 checks to
fill a 10-result page.

### 4.2 The cost of a permission change

Early binding has one well-known cost. If each document stores a
*copy* of its folder's ACL, changing the folder's ACL means rewriting
every document beneath it. For a folder with 100,000 documents that is
100,000 index updates, and until they finish the index serves stale
permissions (Azure says so plainly).

Every mitigation in the field is the same idea: **store a reference,
not a copy.**

- Cloud Search and the Google Search Appliance: the child points at
  its parent's ACL (`inheritAclFrom`), resolved at query time.
- SharePoint, Elastic, Glean, Graph, Coveo: store group tokens and
  resolve membership at query time, so a membership change touches no
  document.

### 4.3 Where vfs sits

vfs's grants are **early binding by reference, for free**:

- The document's "ACL term" is its path. The path column is already
  indexed, unique and bytewise-ordered (`BytewiseString`,
  `src/vfs/models/rows.py:184-222`).
- A grant `(principal, prefix, level)` is Cloud Search's
  `inheritAclFrom` taken to its limit: every row inherits from every
  ancestor, and the grant lives on the ancestor alone.
- Groups are resolved at query time, per member (ADR 071 rule 3), like
  Coveo's identity cache and Glean's group index.
- So a grant on a folder with 100,000 files is one row and one
  revision bump. No document is rewritten and nothing is stale.

The rejected alternative, for the record: copying each row's effective
readers onto the row (an `acl` column or table, filtered with
`acl IN (:me, :my_groups…)`). It would make a folder grant cost one
write per row beneath it, bring back the stale window every vendor
documents, and break the "10,000+ files per call" ETL contract for
anyone who re-shares a big folder. It also does not remove the scaling
axis: the query still carries one term per group. **Do not adopt.**

What vfs lacks is not the binding model. It is the **query shape**:
the vendors' filters are "is one of these terms on this document",
which an inverted index answers by seeking. Our arms ask the SQL engine
"does this path start with any of these prefixes", which it answers by
testing each prefix on each row. The range join (§3.2) turns our
question back into seeks.

## 5. Ranking statistics under DLS (question 4)

The 2026-09-28 memo surveyed this in depth. This study adds source
evidence for OpenSearch and confirms the vendor picture.

- **Elasticsearch:** "Document level security doesn't affect global
  index statistics that relevancy scoring uses", and a restricted user
  "could still… count how many inaccessible documents contain a given
  term" (documented limitation).
- **OpenSearch Security:** the DLS reader wrapper reports the
  unfiltered `numDocs` (`DlsFlsFilterLeafReader.java:173, 789-791`),
  passes `terms()` through except for field-level masking (`:692-698`)
  and delegates `docFreq` (`:865-866`). Normal searches do not use the
  wrapper at all; they rewrite the query (`DlsFlsValveImpl.java:545-575`),
  and a query filter never touches statistics. So IDF counts hidden
  documents. Nothing in the repo discusses it.
- **Lucene, tantivy:** filters never change statistics, but both offer
  a hook to supply them (`IndexSearcher` `termStatistics` /
  `collectionStatistics`; tantivy's `Bm25StatisticsProvider`,
  `src/query/bm25.rs:15-25`, `Searcher::search_with_statistics_provider`,
  `src/core/searcher.rs:189-206`).
- **SharePoint, Azure, Google, Glean, Coveo:** nothing documented about
  ranking statistics. SharePoint's stated reason for pre-trimming is
  that hit counts and refiners leak.

So the field leaks, and vfs's ADR 065 rule 5 stays stricter than every
product. The useful news for cost: the same ordinals that make the
visible corpus count flat (§3.2) are the prerequisite for the flat
visible `df` measured in the 2026-09-28 memo (§5e: about 22 boundary
blocks per term, 3 KB per query). One structure serves both.

## 6. Candidate designs for vfs (question 5)

Each candidate below keeps two invariants: `Rights.admits` in app code
is the final check on every row (ADR 071 rule 2), and reads never write
(ADR 071 rule 1).

### A. Compile rights to disjoint byte ranges, and join them

What:
- Turn a `Rights` into a sorted list of disjoint half-open byte ranges
  over `path`. Each arm prefix `p` gives `[p, p+U+0001)` (the row
  itself; vfs paths never hold a control character) and `[p/, p0)`
  (everything beneath). Holes are subtracted as intervals. Overlaps
  merge.
- Owner arms become ranges tagged with an owner, joined with
  `AND e.owner_id = r.owner`.
- Memoize the range list on the cached `Resolution`, so it is computed
  once per `(subjects, grant_revision)`.
- Send it as a row source joined to `entry` on
  `path >= lo AND path < hi`:
  - Postgres: two array binds, `unnest($1, $2)`, one statement at any
    grant count.
  - Others: an inline `VALUES` list. SQLite handled 10,000 ranges in
    one statement. SQL Server's ~2,100-bind cap forces slices; there,
    try `OPENJSON` of one JSON bind first. Oracle 23ai has a `VALUES`
    constructor; older Oracle needs collections or `UNION ALL`.

Why it is safe to slice: the ranges are **disjoint**, so per-slice
counts and sums add up exactly. Today's `_visible_corpus` has to fetch
every row and deduplicate when there is more than one clause, because
the arms overlap (`glean.py:743-770`). Disjoint ranges remove that.

Cost: proportional to visible rows plus one index seek per range. No
schema change. It also speeds up every other read that uses
`visibility_clauses` (the topology verbs, glob, grep).

Risk: the planner. Postgres mis-planned 20 `VALUES` slices. Each
dialect must be measured with the `db_test` legs before the shape is
chosen.

### B. Path-ordered ordinals per epoch (the open question, now with a second payoff)

What: the epoch build numbers chunks in path order and stores, per
chunk, its ordinal and a running length sum (or keeps `lex_docs`
keyed by ordinal). A caller's ranges map to ordinal ranges with two
index seeks each. Then:
- `N_v` = Σ (hi − lo), `Σ dl` = Σ (cum[hi] − cum[lo]): flat in
  corpus size (0.06 ms at 50,000 and 500,000 chunks).
- visible `df` = postings inside the ordinal ranges, counted in the
  Rust engine from block first-ids, decoding only boundary blocks (the
  2026-09-28 memo's option e).
- the vector leg can filter on an integer range column instead of a
  path join.

This is Lucene's index sorting applied to vfs's epoch.

The hard part, which the open question already names ("renumbering on
move"): a row moved or deleted after the epoch was built keeps its old
ordinal. Lucene's answer is the **live-docs pattern**: the segment is
immutable and a small per-query correction is applied last. For vfs:
count over the epoch's ranges, then correct with the rows whose path
changed since the epoch (a delta read of moved or deleted rows, bounded
by write activity since the last reindex). Without that correction the
statistics could count a row the caller can no longer see, which is
the leak ADR 065 closes. This needs an ADR.

Cost of building: one extra sort at reindex, which is already a whole
rebuild (ADR 055).

### C. Pick pre-filter or post-filter for the vector leg by the visible fraction

What: glean already computes `N_v` before it runs the vector leg. Use
`N_v / N` as the selectivity:
- small visible share: pre-filter (candidate A's join; distances only
  over visible chunks);
- large visible share: run the whole-mount vector statement and
  post-filter with the in-memory range list, deepening the window.

The threshold is to be measured. Lucene's rule is the model; unlike a
graph index, vfs's vector leg is brute force today, so the crossover is
simply "is computing distances over the visible chunks cheaper than
over all of them plus a deeper window".

### D. A per-authority visible-set cache (only if A–C are not enough)

What: cache the caller's visible chunk ordinals (a bitset, or a range
list) keyed by `(resolved rights, grant_revision, epoch)`. This is the
Elasticsearch DLS bitset cache. Size: 125 KB per million chunks as a
bitset, far less as ranges.

Lessons from the field if we go there:
- key by the **resolved rights**, not the user, so people with the same
  groups share one entry (Elastic's per-user templated queries flooded
  its cache);
- bound it by bytes and idle time, like Elastic (10 % heap, 2 h TTL);
- treat moves since the epoch as a live-docs delta, as in B.

With B in place, the range list is already small and cheap to recompute,
so D may never be needed.

### E. Not recommended

- **Copy effective readers onto each row** (early binding by copy): §4.3.
- **Cache the compiled SQL per user**: the SQL is not the cost; the
  plan is.
- **Global statistics for partial callers**: violates ADR 065 rule 5,
  and the cost argument for it disappears with B.

## 7. What to prototype in the glean bench

In `studies/2026-09-29-partial-glean-latency/bench.py`, as study code
(nothing under `src/`):

1. **Range join for `_visible_corpus` and `_vector_leg`** (candidate
   A). Replace the clauses with a ranges row source; keep `admits` on
   every fetched row. Expected on SQLite at 100 / 500 grants: the two
   dominant statements drop from about 215 + 212 ms to single-digit
   and tens of ms. Run the same on the Postgres, SQL Server, MariaDB
   and Oracle legs.
2. **A 5,000-grant caller** (single-file grants) and a caller with
   holes, so the bench covers the shape that hurt most here (10.8 s on
   SQLite today) and interval subtraction.
3. **Pre/post-filter switch for the vector leg** (candidate C): record
   the crossover visible share per engine.
4. **Ordinal counting** (candidate B) as a side table built by the
   bench after reindex: `N_v`, `Σ dl` by seeks, and visible `df` by
   boundary blocks in Rust. Measure against the common-word row of
   the bench (194–249 ms today), which is dominated by reading every
   block.
5. Record per-statement timings, as the bench's profile did, so each
   change is attributed.

## Recommendations

1. **Keep vfs's binding model.** Prefix grants are early binding by
   reference: a folder grant is one row, whatever lies beneath it. Do
   not copy permissions onto rows.
2. **Change the predicate shape first (candidate A).** Compile rights
   to disjoint byte ranges, memoized with the cached resolution, and
   join them to the path index. It is the largest measured win (50× at
   100 grants, 650× at 5,000 on SQLite), it needs no schema change, and
   it helps every verb that reads through `visibility_clauses`. Choose
   the row-source spelling per dialect by measurement.
3. **Then take path-ordered ordinals to an ADR (candidate B).** It
   makes both the visible corpus count and the visible `df` flat in
   corpus size, which is what ADR 065 rule 5 needs to be cheap. The
   ADR must settle moves since the epoch as a live-docs style delta.
4. **Switch the vector leg between pre- and post-filtering by the
   visible share (candidate C)**, following Lucene's kNN rule.
5. **Hold the per-authority cache (candidate D) in reserve.** If it is
   built, key it by resolved rights, not by user.

## One-line version

Search engines stay fast under document-level security by storing
permissions as references and turning the filter into seeks over a
sorted index; vfs already stores references (path prefixes), so the fix
is to send its grants as byte ranges joined to the path index now, and
number each epoch's chunks in path order next.
