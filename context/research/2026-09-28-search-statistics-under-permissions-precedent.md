# Search statistics under permissions: how serious the leak is, and what everyone else did

- **Status:** research memo (commits us to nothing). Answers Clay's
  question Q3 on ADR 065 rule 5. Follows study S2
  (`2026-09-05-glean-statistics-leak.md`), which measured the leak; this
  memo rates it, surveys precedent, and costs the options.
- **Date:** 2026-09-28
- **Owner:** Clay Gendron
- **Method:** three parallel read-only studies (engine source in six
  refreshed clones plus the Postgres checkout; the academic record; the
  industry docs, advisories and CVE databases), a direct check of what
  vfs's public `glean` returns today (a scratch script against a sqlite
  mount; nothing under `src/` touched), and one executed study on vfs's
  own Rust engine:
  `studies/2026-09-28-search-statistics-precedent/` (`README.md`,
  `results.md`, `visible_df_cost.py`).
- **Sources (clones, each refreshed to `origin/HEAD` on 2026-09-28,
  licence re-checked after the refresh; none was dirty):**
  `apache/lucene` @ `b304eea` (2026-09-28, Apache-2.0);
  `quickwit-oss/tantivy` @ `047464c` (2026-09-28, MIT);
  `paradedb/paradedb` @ `0282cc5` (2026-09-28, AGPL-3.0);
  `timescale/pg_textsearch` @ `710976a` (2026-09-27, PostgreSQL licence);
  `tensorchord/VectorChord-bm25` @ `14fc2a3` (2026-04-28, dual
  AGPL-3.0 / Elastic License 2.0);
  `opensearch-project/neural-search` @ `187ba63` (2026-09-25,
  Apache-2.0). Postgres read only, not refreshed by this study
  (`cc053b6e`, 2026-09-28, PostgreSQL licence). Study only; nothing
  copied.
- **Sources (web, read 2026-09-28):**
  Büttcher and Clarke, FAST 2005,
  <https://www.usenix.org/legacy/events/fast05/tech/full_papers/buettcher/buettcher.pdf>;
  Büttcher, PhD thesis, Waterloo 2007,
  <http://stefan.buettcher.org/papers/buettcher_phd_thesis.pdf>;
  Wang, Grubbs, Lu, Bindschaedler, Cash, Ristenpart, *Side-Channel
  Attacks on Shared Search Indexes* (STRESS), IEEE S&P 2017,
  <https://stressattack.github.io/paper/sp17stress.pdf>;
  Espiritu and Cash, *Plaintext Recovery Against Post-Filtering Access
  Control*, arXiv 2608.11730 (2026-08-12), <https://arxiv.org/abs/2608.11730>;
  Singh, Srivatsa, Liu, ICWS 2007,
  <https://faculty.cc.gatech.edu/~lingliu/papers/2007/fssearch-icws07.pdf>;
  Zerr et al., Zerber (EDBT 2008) and Zerber+R (EDBT 2009),
  <https://openproceedings.org/2008/conf/edbt/ZerrDONWM08.pdf>,
  <https://openproceedings.org/2009/conf/edbt/ZerrONS09.pdf>;
  Bawa, Bayardo, Agrawal, VLDB 2003,
  <https://www.vldb.org/conf/2003/papers/S27P03.pdf>;
  Bailey, Hawking, Matson, CIKM 2006,
  <https://david-hawking.net/pubs/cikm127_bailey.pdf>;
  Elastic security limitations,
  <https://www.elastic.co/docs/deploy-manage/security/limitations>, and
  document/field-level access,
  <https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/controlling-access-at-document-field-level>;
  Elastic consistent scoring,
  <https://www.elastic.co/docs/solutions/search/full-text/search-relevance/consistent-scoring>;
  Solr common query parameters,
  <https://solr.apache.org/guide/solr/latest/query-guide/common-query-parameters.html>;
  SharePoint custom security trimming,
  <https://learn.microsoft.com/en-us/sharepoint/dev/general-development/custom-security-trimming-for-search-in-sharepoint-server>;
  Azure AI Search security trimming, scoring, and document-level access,
  <https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search>,
  <https://learn.microsoft.com/en-us/azure/search/index-similarity-and-scoring>,
  <https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview>;
  Vespa streaming search and significance,
  <https://docs.vespa.ai/en/performance/streaming-search.html>,
  <https://docs.vespa.ai/en/ranking/significance.html>;
  Weaviate multi-tenancy,
  <https://weaviate.io/blog/weaviate-multi-tenancy-architecture-explained>;
  Algolia tie-breaking,
  <https://www.algolia.com/doc/faq/index-configuration/how-does-algolia-s-tie-breaking-ranking-algorithm-work/>;
  Postgres text-search ranking, planner statistics security, rules and
  privileges, `CREATE FUNCTION`,
  <https://www.postgresql.org/docs/current/textsearch-controls.html>,
  <https://www.postgresql.org/docs/current/planner-stats-security.html>,
  <https://www.postgresql.org/docs/current/rules-privileges.html>,
  <https://www.postgresql.org/docs/current/sql-createfunction.html>;
  NVD / CVE records for CVE-2024-11129 (GitLab, fetched from the NVD API),
  CVE-2021-22135 (Elastic,
  <https://discuss.elastic.co/t/elastic-stack-7-12-0-and-6-8-15-security-update/268125>),
  CVE-2017-7484, CVE-2019-10130, CVE-2024-4317, CVE-2025-8713
  (PostgreSQL); MITRE CWE-202, CWE-1230, CWE-612, CWE-203, CWE-204,
  <https://cwe.mitre.org/data/definitions/202.html> and siblings.
  Glean, Google Cloud Search / Vertex AI Search: public pages only, no
  statement on ranking statistics found (unverified either way).

## Bottom line

1. **It is a real vulnerability, rated Medium in the field.** Global
   statistics do not hand over hidden text. They answer two questions
   about any word the attacker can name: "does some hidden document
   contain it?" and "how many do?". Answers are exact. The field's
   nearest match, a GitLab search that leaked "the count of issues
   containing the searched term", got a CVE at CVSS 6.3 (vendor) and 7.5
   (NVD).
2. **Nobody shipping fixes it with per-user statistics.** Every search
   engine studied computes BM25 statistics over the whole index and
   filters results afterwards. Elastic and pg_textsearch document the
   leak. OpenSearch, Solr, Azure AI Search, ParadeDB and VectorChord say
   nothing. The systems that are safe avoid the problem structurally
   (one index per tenant) or use no corpus statistics at all.
3. **The research record is unanimous the other way.** Büttcher and
   Clarke (2005), Büttcher's thesis (2007), Singh et al. (2007) and the
   STRESS paper (2017) all say: statistics must come only from what the
   caller can see, or from data with no private content. Post-filtering
   is insecure even when scores are hidden. Noise is not a defence.
4. **Postgres is the one production system that applies the rule.** Its
   planner refuses to show a function the table's statistics when row
   security is active, and it has issued four CVEs for gaps in that
   rule.
5. **ADR 065 rule 5 stands.** Precedent supports it. What precedent adds
   is how to make it cheap: a fast path when the caller sees the whole
   mount (option c), and, for everyone else, counting over contiguous
   id ranges. Measured on vfs's engine: if chunk ids follow path order,
   a caller's visible `df` costs about 22 boundary blocks and 3 KB per
   query at 207 k chunks, flat in corpus size. The naive count decodes
   every block (567 KB per query, growing with the corpus).
6. **The stored block maxima are unsafe under visible statistics.** 5 to
   14 % of blocks have a stored bound below their true visible maximum.
   A one-line rescale, `max_weight × idf_v / idf_g × max(1, avg_dl_v /
   avg_dl_g)`, is provably safe (0 violations measured) and costs no
   format change.

## 1. The question

Clay asked:

> "How much of a security issue is this? If we use the grouped
> statistics, are we actually exposing the data to users? Is there
> precedent for this with things like BM25 or search where we have to
> adjust search algorithms based on permissions?"

Some terms first.

- **BM25** is the scoring formula `glean` uses for its keyword leg. It
  gives each matching chunk a number. Higher means more relevant.
- BM25 needs three **corpus statistics**. `N` is the number of chunks.
  `avg_dl` is their average length in tokens. `df(t)` ("document
  frequency") is how many chunks contain term `t`.
- `idf(t)` ("inverse document frequency") is computed from `df(t)` and
  `N`. A rare word gets a high `idf`, a common one a low `idf`.
- **Grouped statistics**, in Clay's words, are statistics computed once
  over every row, and shared by every caller. That is what vfs stores
  today (`lex_stats`, `lex_df` per epoch).
- **Visible-set statistics** are computed only over the rows this
  caller may see. ADR 065 rule 5 requires them.
- A **hidden row** is one the caller holds no grant on (spec 058's
  "invisible" rung).

## 2. What the leak is, in plain words

A visible chunk's score depends on `idf`. `idf` depends on `df`. With
grouped statistics, `df` counts hidden chunks too. So a visible chunk's
score changes when a hidden chunk contains the query word.

The attacker cannot see the hidden chunk. But they can see the score
move. From that they learn the hidden `df`.

Said another way: grouped statistics turn `glean` into a **counting
oracle**. An oracle, in security language, is a system that answers
yes/no or counting questions about a secret. Here the question is "how
many hidden chunks contain this word?". The answer is exact.

What it does **not** give:

- It does not return hidden text.
- It does not return hidden paths or file names.
- It does not tell which hidden chunk holds the word.
- vfs has no phrase queries, so it does not reveal word order.
  Büttcher and Clarke rebuilt whole files only because their engine had
  phrase queries (§5.3 of their paper).

What it **does** give:

- For any word the attacker names: is it in some hidden chunk, and in
  how many.
- The size of the hidden set (`N` minus the visible count), within two
  chunks, from two queries (S2).

That is less than "reading the file". It is still a lot. Many secrets
are single words: a person's name, a codename, a diagnosis, "layoff".

## 3. Severity

### 3.1 What vfs returns today

I checked this by running `glean` through `VirtualFileSystem` on a
sqlite mount (a scratch script, no source edits).

| channel | reaches a router caller today? | notes |
|---|---|---|
| **scores** (channel a in S2) | yes | min-max scaled to [0, 1], nine decimals, on every row and every `Match` |
| **ranks** (channel c) | yes | the order of rows |
| **`lexical_stats` export** (channel b) | **no, not through the router** | the storage's `Result` carries it (`glean.py:376-383`), but `Result.merge` keeps no extras and the router re-adds only `legs`. A direct `DatabaseStorage.glean` caller gets it, and any future remote mount would ship it over the wire, as `rerank.py` is designed to read it |

Two more facts set the timing.

- **Row grants have not landed.** Spec 058 is active, not built. Today
  every caller of a mount sees every row of it. So the leak is
  **latent**: it goes live on the day the invisible rung ships, unless
  slice D (statistics) ships with it.
- **Cross-mount is not affected.** Statistics are per mount. A mount
  the caller cannot reach is never dispatched to.

### 3.2 Concrete attacks

The setting: an agent with read on `/team`, and `/hr` and `/legal`
hidden from it. Most agents can also write somewhere (their own
scratch folder).

**A1. The name probe.** The attacker wants to know whether HR has a
file about a colleague. They search for the colleague's surname next to
a word with known statistics. With write access, they first plant a
few "anchor" files containing made-up words, so they know those words'
`df` exactly. One query per probe word then gives the hidden `df`
exactly (S2: precision 1.000, recall 1.000, count exact 99–100 %).
Answer: "yes, 3 hidden chunks mention `okafor`".

**A2. The layoff watch.** The attacker probes `layoff`, `severance`,
`redundancy`, `rif`. Yesterday all were 0 in hidden rows. Today
`severance` is 14. They did not read a file. They learned the news.

**A3. The codename.** Legal has a deal codenamed `falcon`. The
attacker has a list of 500 candidate acquisition targets. They probe
each name. The one with hidden `df > 0` that co-rises with `falcon` is
the target. This is insider-trading grade information from 500
queries.

**A4. The new-file differential.** A new file lands in `/hr`. After
the next reindex, the attacker re-probes a dictionary. Every word whose
hidden `df` went up by exactly one is in the new file. That is the new
file's **bag of words** (its set of words, without order), limited to
the words tried. Not run; it follows from S2's exactness. Büttcher and
Clarke name the same harm.

**A5. Probing words no visible file contains.** S2 noted the score
channel cannot see a word absent from every visible chunk. But a writer
can make it visible: plant one file containing the word, then probe.
So for an attacker with write access, the whole vocabulary is open.

**A6. The read-only attacker.** Without write, there are no anchors.
Two-word queries still give the ratio of two words' `idf`s from any
visible chunk that contains both. Presence of a word in hidden rows is
still detectable when a visible chunk contains it. Not measured; weaker,
not zero.

What the attacker needs:

| need | required? |
|---|---|
| read on some rows of the same mount | yes |
| write somewhere in the mount | no, but it makes the counts exact and opens every word |
| scores in the result | no; ranks alone leak (S2 channel c; Büttcher §5.2; STRESS on GitHub) |
| the `lexical_stats` export | no; it only makes the attack free (one query, k words, no anchors) |
| many queries | about one per probed word; a 10,000-word dictionary is an afternoon for an agent |
| a reindex after planting | only if anchors must be in the epoch; the overlay scores live files with the epoch's statistics |

### 3.3 Vocabulary and rating

In standard terms:

- It is a **side channel**: information leaves through a path not
  meant to carry it (the score), not through the data path (the rows).
- It is an **inference attack**: the secret is deduced from allowed
  answers.
- The specific shape is an **existence (membership) oracle** plus a
  **count oracle**.

CWE labels (MITRE's weakness catalogue):

| CWE | name | fit |
|---|---|---|
| **CWE-202** | Exposure of Sensitive Information Through Data Queries | best: "an attacker can often infer some of the information by using statistics" |
| CWE-1230 | Exposure of Sensitive Information Through Metadata | parent; its text names "search indices, statistical reports" |
| CWE-612 | Improper Authorization of Index Containing Sensitive Information | sibling; the index is not limited to authorised readers |
| CWE-203 / CWE-204 | Observable (Response) Discrepancy | the mechanism |
| CWE-200 / CWE-209 | generic exposure | what vendors actually file under (Elastic 200, GitLab 209) |

How the field has rated the same class:

| case | what leaked | rating |
|---|---|---|
| CVE-2024-11129, GitLab EE | "the count of issues containing the searched term" | 6.3 Medium (GitLab), 7.5 High (NVD) |
| CVE-2021-22135, Elasticsearch | existence of documents under DLS, via suggesters and the profile API | fixed as a CVE, CWE-200 |
| CVE-2017-7484, CVE-2019-10130, CVE-2024-4317, CVE-2025-8713, PostgreSQL | planner statistics readable past privileges or row security | 3.1 to 4.3 (Postgres), up to 7.5 (NVD, 2017) |
| Elastic DLS scoring statistics | "count how many inaccessible documents contain a given term" | documented limitation, not a CVE |

**What an enterprise security reviewer would say.** Medium, rising to
High where the hidden rows are HR, legal or health data. The deciding
fact is the promise. vfs promises, in ADR 065 rule 1, that a hidden row
is "absent everywhere". Shipping grouped statistics would break that
promise, and a reviewer would file a broken promise as a vulnerability,
not a limitation. Elastic got away with "limitation" only because it
wrote the limitation down. Even so, the 2026 Espiritu and Cash paper
calls out Elastic for documenting the leak while still claiming DLS
"prevents users from viewing restricted documents".

**Where the severity is zero.** A single-user mount. A mount in the
default `open` posture with no private folders. Any caller whose rights
cover the whole mount. For those callers the grouped statistics are
the visible statistics (option c, §5).

## 4. Precedent

Five ways a system can respond:

- **(i) ignores** the leak;
- **(ii) documents** it;
- **(iii) fixes** it with statistics over the caller's visible set (or
  a union of per-partition statistics);
- **(iv) avoids** it structurally: a separate index per tenant, so
  there is nothing hidden inside an index;
- **(v) removes** private statistics: no corpus statistics at all, or
  statistics from a public corpus.

| system | statistics come from | response | evidence |
|---|---|---|---|
| Büttcher and Clarke, Wumpus (FAST 2005; thesis 2007) | the caller's searchable files, per query | **(iii)** | "query integration": each posting list restricted to the user's files before `N`, `avg_dl`, `df` are computed. Cost 12–17 % at 100 % visible, 20–39 % *faster* at 10 % visible; thesis: 6–8 % |
| Singh, Srivatsa, Liu (ICWS 2007) | one index per "access control barrel" (files with the same readers), merged at query time | **(iii)**, per partition | query time comparable (113–150 vs 131 ms) |
| STRESS (IEEE S&P 2017) | proposes public-corpus or "blind" df | **(v)** | attack worked on hosted Elasticsearch, CloudSearch, Solr services and GitHub, rank-only included; public df cost MAP 0.17 → 0.17 |
| Espiritu and Cash (arXiv 2026) | attack paper | n/a | whole-text recovery from Elasticsearch/OpenSearch DLS via scoring and prefix-expansion channels |
| Zerber / Zerber+R (EDBT 2008/09) | drops `idf` entirely | **(v)** | different threat (untrusted index server); "collection-wide statistics such as IDF is a topic for future work" |
| Lucene | whole reader, deleted docs included (`IndexSearcher.java:1130-1158`, `Terms.java:106-121`) | engine: **(i)**, with a hook | `termStats`/`fieldStats` are overridable "to return a term's statistics across a distributed collection" (`:1122`, `:1139`); FILTER clauses never touch statistics (`BooleanWeight.java:59`) |
| Elasticsearch DLS | whole shard; DLS marks hidden docs deleted, and deleted docs still count | **(ii)** | "Document level security doesn't affect global index statistics that relevancy scoring uses"; a user can "count how many inaccessible documents contain a given term". Suggester and profile leaks were fixed as CVE-2021-22135 |
| OpenSearch DLS/FLS | whole shard (`DlsFlsFilterLeafReader` passes `terms()` through) | **(i)** | no mention in docs or issues |
| Solr (`fq`-based security plugins) | whole core | **(i)** | `fq` restricts "the superset of documents that can be returned, without influencing score" |
| SharePoint / Microsoft 365 | not stated for ranking | **(ii)**, partly | pre-trimming "prevents information leakage for refiner data and hit count"; nothing on ranking statistics |
| Azure AI Search | per shard, or `scoringStatistics=global` across shards | **(i)** | security filters are plain OData filters; new document-level access preview trims results only |
| Google Vertex AI Search, Glean | not stated | unknown | no public statement found |
| Vespa, indexed mode | per content node, all docs | **(i)** | no warning |
| Vespa, streaming mode | none collected; significance set to 1 | **(iv)/(v)** | recommended for "personal indexes"; motivated by cost, not this leak |
| Weaviate multi-tenancy | per tenant shard | **(iv)** | filtered BM25 without multi-tenancy is deliberately global: **(i)** |
| Algolia | no TF-IDF | **(v)** | tie-breaking ranking only |
| Postgres `ts_rank` | the document alone | **(v)** | "the ranking functions do not use any global information" |
| tantivy | all segments, deleted docs included (`query/bm25.rs:27-50`) | engine: **(i)**, with a hook | `Bm25StatisticsProvider` lets a caller supply statistics (`core/searcher.rs:189-199`) |
| ParadeDB `pg_search` | tantivy defaults over the MVCC segment view; RLS is an executor filter | **(i)** | RLS tests check `pdb.score` works, never leakage; docs say dead rows affect scores until VACUUM |
| pg_textsearch | index metapage + memtable, dead docs included | **(ii)** + a refuse switch | README: statistics "include all indexed rows, including rows hidden by RLS"; `pg_textsearch.allow_rls = off` refuses BM25 indexes on RLS tables (`src/access/rls.c:195-215`) |
| VectorChord-bm25 | stored at build and maintain; deletes only flagged | **(i)** | no mention |
| OpenSearch neural-search (hybrid) | Lucene per shard | **(i)** | refuses `dfs_query_then_fetch` for ordering reasons, not security |
| PostgreSQL planner | `pg_statistic` withheld under row security unless the operator is `LEAKPROOF` (`selfuncs.c:6674-6698`); `pg_stats` shows no rows under active RLS (`system_views.sql:274-276`) | **(iii)** by withholding | four CVEs for gaps; the docs decline to defend timing and plan-choice channels |
| SQL Server | `DBCC SHOW_STATISTICS` restricted because it "can leak information otherwise protected by a security policy" (lens L4) | **(iii)** by withholding | |
| GitLab EE search | issue counts per searched term | fixed, **CVE-2024-11129** | 6.3 / 7.5 |

What the table says, in three sentences.

- **Products** mostly ignore or document the leak. None computes
  statistics per caller. The safe ones got safe by structure (one index
  per tenant) or by having no corpus statistics.
- **Research** always says per caller (or public) statistics, and says
  post-filtering is insecure even without scores.
- **Databases** treat statistics that cross a row-security boundary as
  a CVE class, and fix it by withholding.

Two more patterns worth naming.

- **Every engine counts deleted rows** in its statistics until a merge
  or VACUUM (Lucene, tantivy, ParadeDB, pg_textsearch, VectorChord,
  Azure). This is the same leak in time instead of in permissions: a
  deleted row keeps shaping scores. vfs has the same property within an
  epoch.
- **"One index per tenant" is everyone's fallback, and everyone rejects
  it on cost, not on security.** Elastic told the STRESS authors so.
  Büttcher and Clarke rejected it because shared files get indexed many
  times and a `chmod` forces re-indexing.

## 5. What precedent means for vfs's options

### (a) Grouped statistics always

This is the Elastic and pg_textsearch position. It is defensible only
when written down and when the product does not promise invisibility.
vfs does promise it (ADR 065 rule 1). The GitLab and Elastic suggester
CVEs show that reviewers file existence and count oracles as
vulnerabilities. **Precedent does not support (a) as a default.**
pg_textsearch's switch is the one useful idea here: a mount could
decline to build a lexical index at all under a non-open posture. vfs
does not need that switch if (c) and exact counting are affordable.

### (b) Visible-set statistics always

This is Büttcher and Clarke's answer. It is exact, and it is what ADR
065 ratified. The issue is cost on vfs's storage, which is not
Büttcher's in-memory index.

Measured on vfs's engine (40 × SciFact, 207 k chunks, 300 queries,
`studies/.../results.md`):

| per query, mean | today's ranking (head blocks) | naive visible `df` (decode every block) |
|---|---|---|
| id-blob bytes fetched | 11.9 KB | 566.6 KB |
| blocks decoded | ≤ 8 per term | 4,390 |

The naive count reads every block of every query term. That is 48 ×
today's fetch, and it grows with the corpus: extrapolated to 10 M
chunks it is about 27 MB of blobs per query. Block-max skipping exists
precisely so a common term's blocks are not read; the naive count
undoes it. **(b) is right; the naive way to compute it does not scale.**

### (c) Fast path when the caller sees the whole mount

When the caller's rights cover every row of the mount, the visible set
*is* the corpus. The stored statistics *are* the visible-set
statistics. Using them is not a relaxation of ADR 065; it is ADR 065,
computed in advance.

This is the common case. The default posture is `open` (ADR 068). A
single-user mount is always whole. The owner or a `/` grant holder is
always whole.

The branch is decided by the caller's own rights, never by the data.
The caller already knows their own rights, so choosing the fast path
reveals nothing.

One edge to settle in the spec, not here: rows deleted or re-granted
after the epoch was built still count in the stored statistics until
the next reindex (the engine-wide "deleted docs count" pattern above).
A caller whose whole-mount rights predate the epoch saw every such row
when it was live, so nothing leaks to them. A caller who gained
whole-mount rights after the build could, in principle, learn the
`df` of a row deleted before they joined. Keying the fast path on the
epoch's `grant_revision` closes it.

**Precedent supports (c).** It is Büttcher's rule with his measured
"100 % visible" cost driven to zero.

### (d) Per-partition precomputed statistics

Store `df`, `N` and `Σ dl` per (term, partition), where a partition is
a grant prefix. A caller's statistics are the sum over the partitions
they can see.

**This is not what ADR 065 rejected.** ADR 065 rejected *coarsened*
statistics (bucketed `df`) and *stale* statistics (a snapshot). Both
are wrong for the caller: they are functions of hidden rows. A sum of
exact per-partition counts over exactly the caller's partitions is the
caller's visible `df`. It is a function of visible rows only. Singh et
al.'s "access control barrels" (2007) are the precedent.

The limits are practical:

- It is exact only when the visible set is a union of partitions. vfs's
  grants are prefixes, which fits. But the owner floor (a caller owns
  a file outside their granted prefixes) and the `*` narrowing rows
  (a private folder inside an open one) add rows that are not whole
  partitions.
- Grants change between epochs. A grant created after the build has no
  partition row. So (d) needs a fallback anyway.
- Storage grows with partitions. On SciFact the summary table grows
  2 × at 4 partitions, 3.9 × at 16, 6.8 × at 64 and 10.5 × at 256
  (summary rows only; postings unchanged).

**Precedent supports (d) as exact, not as a coarsening.** But it is
brittle as the only path.

### (e) New from this study: path-ordered ids and range counting

The epoch is rebuilt whole (ADR 055), so the build chooses the order of
the ids it writes. If the lexical index numbers chunks **in path
order**, every folder becomes one contiguous id range. Then a caller's
hidden set is a few ranges (their `*`-narrowed folders, the prefixes
they lack), not scattered ids.

With ranges, most blocks are counted without reading them. The summary
row already stores each block's first id, and every block holds 128
postings except a term's last. A block wholly inside a hidden range
counts 128 hidden postings from the summary alone. Only blocks that
straddle a range edge (about two per term per range) must be fetched
and decoded.

Measured (40 × SciFact, mean per query; all methods agree exactly on
every query):

| hidden share | ids | naive (all blocks) | complement (blocks touching hidden ids) | ranges (edge blocks only) |
|---|---|---|---|---|
| 5 % | clustered, 1 range | 566.6 KB | 30.2 KB | **3.1 KB** (21.5 blocks) |
| 50 % | clustered, 1 range | 566.6 KB | 284.7 KB | **3.3 KB** (22.7 blocks) |
| 90 % | clustered, 1 range | 566.6 KB | 511.4 KB | **3.3 KB** (23.2 blocks) |
| 5 % | scattered (today's write order) | 566.6 KB | 566.3 KB | 566.3 KB |
| 50 % | scattered | 566.6 KB | 566.6 KB | 566.6 KB |

In words:

- With path-ordered ids, exact visible `df` costs about a quarter of
  today's head fetch, and the cost does not grow with the corpus or the
  hidden share. It grows with the number of ranges.
- With ids in write order (today), a folder's files are scattered, and
  no trick helps. Every block must be read.
- `N_v` and `avg_dl_v` come from the same ranges: `N_v` is a count and
  `Σ dl` over a range is two reads of a running-sum column on
  `lex_docs`.

The price is a build change: the lexical doc id becomes an
epoch-local ordinal in path order, with `lex_docs` mapping ordinal to
chunk id, and the build scans in path order instead of chunk-id order.
The owner floor's stray files and deep `*` carve-outs are just more
ranges. This is a design direction to put to an ADR, not a decision.

### (f) Statistics from rows everyone can see

STRESS's "blind df" has a vfs analogue: compute statistics only over
rows every principal can read (the `*` posture's shared set). It is
safe for every caller and one cache serves them all. But it is not the
caller's visible set: a caller working mostly in their own private
folder would be scored against someone else's corpus. ADR 065 rule 5
asks for the visible set, and (c) plus (e) make that affordable, so (f)
is noted, not recommended.

## 6. The block-max (WAND) bounds

**Block-max pruning** (WAND is the classic name) skips blocks that
cannot change the top-k. It needs an **upper bound** per block: a
number no posting in the block can beat. vfs stores that bound as
`max_weight`, computed at build time with the global `idf` and
`avg_dl` (ADR 055 decision 2).

Under visible-set statistics, `idf` and `avg_dl` change. So the stored
bound can be too low. If a bound is too low, the pruner can skip a
block that holds a true top-k chunk. The answer would silently lose a
row.

Measured on SciFact (every block with at least one visible posting):

| hidden | ids | blocks | stored bound too low | rescaled bound too low | median true / rescaled |
|---|---|---|---|---|---|
| 5 % | clustered | 38,348 | 5,407 (14.1 %) | **0** | 0.999 |
| 5 % | scattered | 38,243 | 5,564 (14.5 %) | **0** | 1.000 |
| 50 % | clustered | 27,876 | 3,608 (12.9 %) | **0** | 0.994 |
| 50 % | scattered | 28,803 | 3,119 (10.8 %) | **0** | 0.994 |
| 90 % | clustered | 12,368 | 679 (5.5 %) | **0** | 0.910 |
| 90 % | scattered | 13,755 | 637 (4.6 %) | **0** | 0.891 |

**The rescale.** Use

    bound_v = max_weight × (idf_v / idf_g) × max(1, avg_dl_v / avg_dl_g)

Why it is safe, in two steps:

1. BM25's weight is `idf × tf-part`. The `idf` factor comes out
   exactly: multiply by `idf_v / idf_g`.
2. The `tf-part` is `tf(k1+1) / (tf + k1(1 − b + b·dl/avg_dl))`. If
   `avg_dl` shrinks, every `tf-part` shrinks, so the old bound still
   holds. If `avg_dl` grows by a factor `r`, the denominator shrinks by
   at most `r`, so every `tf-part` grows by at most `r`.

So the rescaled bound is never too low. It is also tight: the median
block is within 1 % of its true maximum at 5 and 50 % hidden, 9–11 %
at 90 %. It needs no format change: `idf_g`, `avg_dl_g` and
`max_weight` are already stored.

Two notes.

- The stored maximum was taken over *all* postings, hidden ones too.
  That only makes the bound looser, never unsafe. It does mean hidden
  postings influence *which* blocks are fetched, which is a timing
  signal (Postgres's "class 5", which its docs decline to defend). The
  answer itself stays exact. Record it; do not design around it now.
- Precedent splits the same way. Lucene stores Pareto pairs of (term
  frequency, length) per block and scores them at query time, so its
  bounds follow whatever statistics the query uses. pg_textsearch
  stores max `tf` and min length separately, also safe. tantivy and
  VectorChord store one pair chosen under the build's `avg_dl`, which
  is not strictly safe under other statistics. vfs's rescale gets
  Lucene's safety without Lucene's storage.
- The scorer's `ScoreBlock.bound` orders accumulation (terms by
  descending bound). It must receive the rescaled bound too, or the
  sums are reproducible but ordered by the wrong key.

## 7. Recommendation

1. **Keep ADR 065 rule 5 as ratified.** The research record is
   unanimous, the field rates the oracle Medium to High, and vfs
   promises invisibility. Grouped statistics for a partially-scoped
   caller would be a vulnerability.
2. **Build it as (c) plus exact counting.** Callers whose rights cover
   the mount use the stored statistics (zero cost, most callers).
   Everyone else gets exact visible-set statistics, memoised per
   `(epoch, rights shape, term)` as spec 058 §7 already says.
3. **Put path-ordered lexical ids (option e) to an ADR.** It is what
   makes exact counting flat in corpus size. Without it, a partially
   scoped caller's first query on a term reads every block of that
   term; the memo softens repeats but not first touches. Option (d) is
   the fallback shape if (e) is rejected.
4. **Rescale block bounds under visible statistics** with the formula
   in §6, in the same slice as the statistics. Without it, pruning
   silently drops rows for 5–14 % of blocks.
5. **Keep `lexical_stats` off the router's answer** (it is off today by
   accident of `Result.merge`; make it a decision), and scope the
   mount's export to the visible set before any remote mount ships it.
6. **Same class, not studied here:** stored ranking signals such as
   centrality (`signals.py`) are also computed over every row. A
   visible file's centrality can reveal hidden in-links. It needs the
   same visible-set treatment or a documented exemption.

## 8. Limits

- The cost study counts blob bytes and engine time. It runs no SQL and
  no round trips, and does not measure resolving a caller's rights to
  id ranges.
- The 40 × corpus is SciFact replicated: same vocabulary, `df` times 40.
  A real 200 k-chunk corpus has a longer vocabulary tail.
- "Clustered" models path-ordered ids with one hidden range. A caller
  with many narrow grants has many ranges; cost grows with that count.
- Attacks A4 and A6 are reasoned, not run.
- Glean (the company) and Google's enterprise search published nothing
  on ranking under permissions that this study could find.
- Espiritu and Cash (2026) is a preprint, read from its abstract page.

## One-line version

Grouped statistics let any caller count hidden documents containing any
word they can name, which the field files as a Medium-to-High CVE; no
product fixes it per user, the research always says to, so keep ADR
065, use the stored statistics when the caller sees the whole mount,
count exactly (over path-ordered id ranges) otherwise, and rescale the
block bounds.
