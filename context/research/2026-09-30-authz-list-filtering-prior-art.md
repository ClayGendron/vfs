# Listing what a caller may see: keeping the per-query cost flat as grants grow

- **Status:** research memo. Commits us to nothing. Feeds a follow-up
  to spec 058 (§4 compilation, §11 budgets) and ADR 071 (the chunked
  fan), and the glean partial-caller work measured in
  `studies/2026-09-29-partial-glean-latency/`.
- **Date:** 2026-09-30
- **Owner:** Clay Gendron
- **Question:** vfs compiles a caller's rights to OR'd path-prefix
  arms. On SQLite at 50,000 files, `glean` with limit 10 costs about
  40–70 ms at 1–5 grants, about 440 ms at 100 grants and about 2 s at
  500 grants. The cost is rows × arms: every row is tested against
  every arm. How do mature authorization systems answer "which objects
  can this user see?" without that growth? How many grants does a user
  really hold? What should vfs adopt, and what should the glean bench
  prototype?
- **Method:** (1) four read-only source studies, one per family:
  SpiceDB, OpenFGA, Postgres row-level security, and partial
  evaluation (Oso, OPA, Cedar), each claim cited `file:line` or by URL;
  (2) one web study of the Zanzibar paper (Leopard, caching) and of
  published group and grant limits; (3) an executed probe,
  `studies/2026-09-30-authz-list-filtering/` (`README.md` there):
  six predicate shapes on one lean 50,000-entry corpus (the glean
  bench's layout), on SQLite 3.50 and Postgres 17.11, plus the engine
  plans and two one-bind variants (`unnest.py`, `jsonbind.py`), every
  shape asserted to return the same rows. Medians of 3 to 5 warm runs
  on one laptop; read the ratios. The 2026-09-05 lens memo
  (`2026-09-05-permissions-lens-authz-engines-and-databases.md`)
  already covers how these engines decide a single check; this memo
  covers only listing and its cost curve. Cites and describes only;
  no code copied.
- **Sources:** refreshed to `origin/HEAD` on 2026-09-30, none dirty,
  licences re-checked after the refresh: `authzed/spicedb` @ `e4b276d`
  (2026-09-29, Apache-2.0); `openfga/openfga` @ `97943bf` (2026-09-28,
  Apache-2.0); `postgres/postgres` @ `c712b0d4` (2026-09-30,
  PostgreSQL licence, `COPYRIGHT`); `osohq/oso` @ `7292df0`
  (2025-02-26, Apache-2.0; the README marks the library deprecated);
  `open-policy-agent/opa` @ `753cf54` (2026-09-30, Apache-2.0);
  `cedar-policy/cedar` @ `8a0730b` (2026-09-28, Apache-2.0). Web
  pages read 2026-09-30, cited inline: the Zanzibar paper (Pang et
  al., USENIX ATC 2019, https://www.usenix.org/system/files/atc19-pang.pdf),
  the AuthZed docs repo (`authzed/docs`, `main`), openfga.dev,
  Supabase, Oso Cloud, Microsoft, Google, Okta and Dropbox limit pages.

## Terms used below

- **Grant.** One row `(principal, path_prefix, level)`. It admits the
  prefix and everything under it.
- **Arm.** One compiled test for one covering prefix:
  `path = :p OR path LIKE :p || '/%'`. The caller's arms are OR'd.
- **Covering prefix set.** The caller's minimal, disjoint list of
  prefixes after groups, the meet and the posture are resolved. vfs
  already computes it (`Rights.arms`).
- **Byte range.** A covering prefix `p` is two half-open ranges in
  bytewise order: the row `p` itself, and `[p/, p0)`, every path under
  `p`. The ranges of a minimal prefix set never overlap. That is the
  one fact this memo leans on.
- **Scan-side test.** The engine reads candidate rows and tests each
  one against the predicate. Cost is rows × (cost of one test).
- **Grant-side drive.** The engine starts from the caller's ranges and
  reads, for each range, only the rows inside it through the `path`
  index. Cost is ranges × one index seek, plus the visible rows.
- **Table function.** A function the engine reads as rows: Postgres
  `unnest(array)`, SQLite `json_each(text)`, SQL Server `OPENJSON`,
  Oracle and MariaDB `JSON_TABLE`. It lets one bound value carry a
  whole list.
- **Pre-filter / post-filter.** Pre-filter: narrow the query to what
  the caller may see before ranking or limiting. Post-filter: run the
  query without authorization, then check each result.
- **Leopard.** Zanzibar's index that flattens nested group membership
  ahead of time (paper §3.2.4).
- **Revision.** vfs's `grant_revision`, bumped on every grant or
  membership write. Zanzibar calls its version a *zookie*; SpiceDB
  calls it a *ZedToken*.
- **JIT.** Postgres's just-in-time compiler. It compiles an expensive
  query's expressions to machine code with LLVM before running it,
  which costs time up front.

## Bottom line

1. **Nobody tests every row against every grant.** SpiceDB walks
   outward from the principal with batched index probes, 100 ids per
   `IN`. Postgres RLS best practice keeps the policy text fixed and
   puts the user's grants in data computed once. Oso Cloud ships the
   user's grant facts as a `VALUES` table and joins it. Only OPA's
   Compile API inlines grants as an OR list, which is vfs's current
   shape, and nobody publishes how big that gets (§2–§6).
2. **The fix for vfs is a change of direction, not a cache.** vfs's
   covering prefixes are disjoint byte ranges. Join them to the `path`
   index so the engine starts from the ranges: one index range search
   per range, then only the rows inside. Cost then follows the rows the
   caller can see, not the number of grants. In the probe on SQLite,
   500 folder grants drop from 895 ms to 6 ms; 5,000 file grants drop
   from 10 s to 5 ms. On Postgres, 149 ms to 21 ms and 322 ms to
   28–72 ms (§8).
3. **Ship the ranges as one bind, not as a table and not as a long
   `VALUES` list.** A table of ranges is fast but makes a read write,
   which ADR 071 rejected. A `VALUES` list executes just as fast, but
   building a 2,000-bind statement costs more than running it (§8.2).
   One bind holding the whole list, unpacked by the engine
   (`unnest` of two arrays on Postgres, `json_each` of one JSON text on
   SQLite), runs as fast as the table: 10,000 ranges in 28 ms on
   Postgres and 11 ms on SQLite, in one statement with no chunking
   (§8.3). SQL Server (`OPENJSON`), Oracle and MariaDB (`JSON_TABLE`)
   have the same tool and are not yet measured.
4. **The statement text stops depending on the caller.** That is the
   Postgres RLS lesson (§5) and Oso Cloud's shape (§6): per-user
   variation lives in data, the predicate stays fixed, and the engine
   can cache one plan.
5. **Leopard solves a problem vfs does not have yet.** Leopard flattens
   group-to-group reachability so a *check* is one set intersection.
   vfs already resolves groups once per `(subjects, revision)` and
   caches the result; the walk is off the hot path. The part worth
   borrowing is Leopard's representation: sorted sets and fast
   intersection. For glean, that means numbering chunks in path order
   so a visible folder is one id range (§4, §9).
6. **Users hold tens to thousands of groups.** Every platform caps it:
   Okta puts 100 groups in a claim, Entra ID 200, Active Directory
   allows 1,015, Google Workspace about 9,000 direct plus indirect. No
   study measures how many grants a user effectively holds. Plan for
   hundreds to thousands of covering prefixes, not ten (§7).
7. **What to prototype:** the one-bind range join in glean's two
   partial-caller scans (the visible-corpus count and the vector leg),
   behind a small threshold, on all five engines (§10).

## 1. The problem, restated

The glean bench (`studies/2026-09-29-partial-glean-latency/`) grants a
caller N folders and times `glean`. A caller whose rights cover the
whole mount skips the filter. Every other caller pays for exact
visible-set statistics (`_visible_corpus` in
`src/vfs/storage/backends/database/glean.py`) and for a vector leg that
runs once per visibility clause.

Both are scans over the chunk table joined to the entry table. The
compiled predicate is an OR of N arms. For a row the caller cannot
see, the engine evaluates all N arms before it rejects the row. So a
full scan costs about rows × N arm tests. At 500 arms, `visibility_clauses`
also splits into 3 clauses (the 200-arm ceiling, `_PATTERN_ARM_CEILING`
in `dialects.py`), and each clause scans again.

The arms are already minimal and disjoint. The engine is simply never
told that. An OR list is opaque to the planner: it cannot
binary-search it. SQLite stops using the `path` index for it somewhere
between 10 and 100 arms and scans. Postgres keeps the index through a
BitmapOr of one scan per arm, but rechecks every fetched row against
the whole list (§8).

## 2. SpiceDB: walk out from the principal, batch the ids

**LookupResources never scans the resource table.** It starts at the
subject and walks the schema's *reachability graph* outward
(`pkg/schema/reachabilitygraph.go:148-160`; cached per definition,
`:24-29`). Each step is an *entrypoint*: a relation the subject type can
enter through (`internal/graph/lookupresources3.go:492-557`).

**The key trick is batching.** A relation entrypoint runs one reverse
index query with many subject ids at once
(`lookupresources3.go:602-634, 796-808`). The resource ids it finds are
chunked, at most 100 (`dispatch-chunk-size`, `pkg/cmd/serve.go:156`), and
each chunk becomes the next hop's subject list in one request
(`lookupresources3.go:953-968`). The datastore's `IN` cap is set to the
same number (`pkg/cmd/server/server.go:250-252`;
`internal/datastore/common/sql.go:127-132`). The index it probes is
`ix_relation_tuple_by_subject` (`internal/datastore/postgres/schema/indexes.go:23-25`).

**Cost follows edges reached, not rows × grants.** A user in 50 groups
costs one query to find the groups, then one `subject_id IN (≤100)`
probe per entrypoint per level, plus one row per edge returned.
Intersections and exclusions add a bulk check per chunk
(`lookupresources3.go:914-935, 993-1050`). A pure union skips it.

**Streaming and limits.** Results stream in batches of 500
(`lookupresources3.go:36, 318-330`). A cursor records the position in
each entrypoint (`:217-226`). The page limit is capped at 1,000
(`serve.go:119`). Depth is capped at 50 (`serve.go:157`).

**Caching is revision-keyed and never invalidated.** The dispatch cache
key hashes the request and appends the revision
(`internal/dispatch/keys/hasher.go:148-157`). Entries age out. The
default revision *quantization* is 5 s
(`pkg/cmd/datastore/dsconfig/config.go:83, 220`): every read in the same
5 s window uses the same rounded revision, so they share cache
entries. The TTL is about twice that window
(`pkg/cmd/server/cacheconfig.go:21-56`). `minimize_latency` reads the
quantized revision; `at_least_as_fresh` takes the newer of it and the
caller's ZedToken (`pkg/middleware/consistency/consistency.go:143-215, 286-320`).

**The documented recommendation has three tiers**
(https://authzed.com/docs/spicedb/modeling/protecting-a-list-endpoint):

| Accessible set | Pattern | How |
|---|---|---|
| small, under about 10k | pre-filter | LookupResources, then `WHERE id IN (...)` |
| most of the table | post-filter | fetch a page, CheckBulk it, loop until full |
| large, at scale | Materialize | a join in your own database |

CheckBulk takes up to 10,000 items and groups them by permission and
subject (`internal/services/v1/bulkcheck.go:46-57`;
`grouping.go:29-54`).

**Materialize is AuthZed's hosted Leopard.** It emits two kinds of
edges: member→set (`user:evan ∈ document:123#view`) and set→set
(a group nested in a permission). The relational guide stores them as
`member_to_set` and `set_to_set` tables, so "documents X can view" is
two joins (AuthZed docs, `materialize/guides/relational-database`). It
tolerates lag and is fed by a change stream. No write-amplification
number is published. The open-source tree has no flattening; a grep
finds only a TODO about Materialize cost estimates
(`internal/fdw/stats/stats.go:54`).

## 3. OpenFGA: a capped walk, and "filter by a coarser parent"

**Two algorithms, chosen per request** (`pkg/server/commands/list_objects.go:574-576`).
The default is a streaming pipeline of workers, one per node of the
model graph (`internal/listobjects/pipeline/doc.go:1-41`). The fallback
is *reverse expansion* then Check: walk back from the user, and check
every candidate that went through an `and` or `but not`
(`list_objects.go:445-479`; `internal/graph/reverseexpand/reverse_expand.go:214-215`).

**Hard caps, not scaling.** ListObjects returns at most 1,000 results
and stops at 3 s (`pkg/server/config/config.go:27-28`). A deadline hit
returns what it found, with nothing to say it was cut short
(`list_objects.go:486-489`). Results are unsorted and not paginated.

**Caching.** Sub-check results are keyed by store, model, contextual
tuples and the sub-problem (`pkg/storage/cache.go:312-363`), 10 s TTL
by default (`config.go:38, 43-44`). A cache controller reads the
newest changes from the changelog and writes invalidation markers
(`internal/cachecontroller/cache_controller.go:150-194, 241-356`).
`HIGHER_CONSISTENCY` bypasses all of it.

**No Leopard.** OpenFGA's roadmap says it is "optimized to offer low
latency for models with up to 2 nested levels" and that deeper ones
need "Leopard indexes" (https://github.com/openfga/roadmap/issues/10,
open since 2022). Nested groups are flattened per request.

**The search guidance is the most useful part**
(https://openfga.dev/docs/interacting/search-with-permissions). It
names three options: search then check; build a local index from the
changes feed; ListObjects then search. For the Google Drive case (many
rows, many accessible objects, a small share of the type) it gives a
fourth move: *list a coarser parent first* (the accessible folders) and
filter documents by folder in SQL. That is exactly vfs's prefix model.
vfs already filters by folder; the question is only how the SQL is
shaped.

## 4. Zanzibar's Leopard, and its vfs equivalent

**What Leopard indexes** (paper §3.2.4). Two set types, stored as
sorted integer lists:

- `GROUP2GROUP(s)`: every group nested under group `s`, directly or
  not. This is the flattened part.
- `MEMBER2GROUP(s)`: the groups user `s` is a *direct* member of.

User U is in group G when `MEMBER2GROUP(U) ∩ GROUP2GROUP(G)` is not
empty. Intersections cost O(min(|A|, |B|)) skip-list seeks. Leopard is
opt-in per namespace, for the ones with deep or wide nesting.

**How it stays current.** An offline builder rebuilds shards from a
snapshot. An online layer applies changes from Zanzibar's Watch stream
on top, merged at query time by timestamp.

**What it costs on writes.** "a single Zanzibar tuple addition or
deletion may yield potentially tens of thousands of discrete Leopard
tuple events." Every serving instance receives the full stream. The
paper measures 1.56M QPS median, under 150 µs median and 1 ms p99, and
about 500 index updates per second median (§4.4). It publishes no index
size.

**The vfs equivalent of GROUP2GROUP** is a closure table
`group_closure(group, ancestor)`, written under the revision lock when
a membership changes. Adding member M to group G adds one row for
every pair (M or a group under M, G or a group above G). Removing one
is harder: with several paths between two groups, the row must stay
until the last path goes, so it needs a path count or a local
recompute. With the 8-level cap the fan-out is small.

**But vfs does not need it today.** The group walk runs only on a
`RightsCache` miss, keyed by `(subjects, grant_revision)`
(`src/vfs/storage/backends/database/rights.py`, `resolve_authority`).
It costs at most 8 statements, once per revision. The measured cost is
not the walk. It is the arms × rows scan that follows. A closure table
would speed up a step that is already amortized.

**The vfs equivalent of "flatten ahead of time" for the *rights*** is
a per-principal cover table: `principal → disjoint byte ranges`,
rewritten when a grant or membership touching the principal changes.
Two things make it expensive for vfs. A change to the `*` posture
rewrites every principal's rows (S1's everyone-grant problem, at range
granularity instead of row granularity). And a subject set (Ann and
John together) takes the meet of two covers, which a table cannot
store for every possible set. Reads would still write for subject
sets. §8 shows the table is not needed for speed either.

**The part of Leopard vfs should borrow** is the representation:
sorted integer sets and fast intersection. vfs already has a Rust
kernel that intersects posting blocks (`candidate_ids`, used in
`_visible_lexicon`). If chunk ids were assigned in path order at
reindex, a visible folder would be one contiguous id range. The
visible set for glean's lexical leg would then be a short list of id
ranges, intersected with postings in Rust, with no SQL predicate at
all. The glean docstring already names this as "the known way to make
it flat".

## 5. Postgres row-level security

**How policies enter the query.** The rewriter ORs the permissive
policies into one expression and ANDs the restrictive ones
(`src/backend/rewrite/rowsecurity.c:715-792`). The result becomes the
table's `securityQuals` (`rewriteHandler.c:2267-2294`). The planner
turns each into a qual with a *security level*
(`src/backend/optimizer/plan/initsplan.c:1945-1984`).

**Leakproof and qual order.** A user qual may run before a security
qual only if it is *leakproof* (cannot reveal its argument through an
error) (`src/backend/optimizer/util/restrictinfo.c:134-135, 422-433`).
A non-promotable qual cannot become an index qual (`indxpath.c:2605`).
`text_lt`, `text_ge` and `starts_with` are leakproof; `textlike`, the
`LIKE` operator, is not (`src/include/catalog/pg_proc.dat:1585, 1594,
169, 1871`). vfs is not RLS, so this ordering does not bind it. It is
one more small reason to prefer range pairs over `LIKE`.

**Plan caching is keyed by database role, not by user.** A cached plan
records the role it was built for and is thrown away when the role or
`row_security` changes (`src/backend/utils/cache/plancache.c:736-743,
979-981, 1142-1156`). Supabase runs every user as one role and reads
the user id from a setting. So the policy text is the same for every
user, and so is the plan. Per-user variation lives in *data*, never in
*predicate shape*. vfs is the opposite: SQL text grows with N.

**The Supabase measurements**
(https://supabase.com/docs/guides/troubleshooting/rls-performance-and-best-practices-Z5Jjwv;
https://github.com/GaryAustin1/RLS-Performance):

| change | before | after |
|---|---|---|
| wrap `auth.uid()` as `(select auth.uid())` | 179 ms | 9 ms |
| wrap a role-lookup function | 178,000 ms | 12 ms |
| `team_id = any(array(select user_teams()))` | 173,000 ms | 16 ms |
| `auth.uid() in (select user_id from team_user where team_id = t.team_id)` rewritten as `team_id in (select team_id from team_user where user_id = auth.uid())` | 9,000 ms | 20 ms |

**Why the fast forms are fast.** An uncorrelated subquery becomes an
*initPlan*: it runs once per statement (`src/backend/optimizer/plan/subselect.c:411, 426`).
An uncorrelated `x IN (select ...)` becomes a *hashed SubPlan*: one
hash probe per row (`subselect.c:524-536`). The slow forms are
*correlated*: they re-run the subquery for every row. Supabase's own
caveat: "If the in list gets to be over 10K items, then extra analysis
is likely needed."

**What maps to vfs.** The team rewrite turns "for each row, look up
the user" into "compute the user's set once, then match rows to it".
With equality keys (`team_id`), that is a hash probe. With vfs's
prefixes the key is a range, so a hash does not apply. What does
apply: a join clause `e.path >= c.lo AND e.path < c.hi` can drive a
parameterized index range scan, one per outer range
(`indxpath.c:436, 605, 2480`). Postgres 18 folds an OR of equalities
into `= ANY` (`indxpath.c:3295`), but an OR of ranges becomes a
BitmapOr of N index scans (`indxpath.c:113, 321`): it works, but plan
time and text grow with N. `path LIKE ANY(array)` gets no index at all
(`indxpath.c:3133-3185`). One risk: with non-constant bounds, range
selectivity falls back to a default (`DEFAULT_RANGE_INEQ_SEL = 0.005`,
`src/include/utils/selfuncs.h:40`), so row estimates are generic.

## 6. Partial evaluation to SQL: Oso, OPA, Cedar

**OPA inlines.** The Compile API partially evaluates a policy with the
table's columns unknown. Each residual query becomes one arm of a
top-level OR (`internal/compile/ucast.go:20-69`). `startswith(col, p)`
becomes `col LIKE 'p%'` (`internal/ucast/ucast.go:121-129`), and values
are interpolated into the SQL text, not bound (`ucast.go:61-73`). Known
`data` (the grants) is substituted during evaluation
(`docs/docs/filtering/fragment.md:49-89`). So N prefix grants give N
OR'd `LIKE` arms. That is vfs's shape exactly. Nothing merges arms,
and no page publishes a residual size.

**Legacy Oso inlines too.** Its filter is an OR of AND-sets, one arm per
partial result (`polar-core/src/filter.rs:23-39, 146-154`). The
SQLAlchemy adapter ORs them and adds `DISTINCT`
(`languages/python/oso/polar/data/adapter/sqlalchemy_adapter.py:18-40`).
A role held on the actor becomes one arm with a literal id.

**Oso Cloud joins.** Its local authorization maps facts to queries on
your own tables. Grant facts held centrally arrive in the SQL as a
`VALUES` relation, equi-joined to a CTE over your table
(https://www.osohq.com/docs/authorization-data/local-authorization;
a real `listLocal` output is shown in
https://microservices.io/post/architecture/2026/02/13/microservices-authn-authz-part-6-oso-local-authorization.html).
Oso's stated reason: the query is "proportional to the number of
parent resources the user has access to, rather than the much larger
number of child resources". Its published range: id-list filtering up
to "~10,000 authorized resources per user"; local SQL filtering
"millions" (https://www.osohq.com/docs/app-integration/integrate-authorization/filter-lists).

**Cedar has no SQL path.** Typed partial evaluation gives one residual
per policy (`cedar-policy-core/src/tpe.rs:41-71`), so residual count
follows policies, not data. `query_resource` re-authorizes every
candidate in memory (`cedar-policy/src/api/tpe.rs:777-860`). Entity
loaders "must compute and include all ancestors"
(`api/tpe.rs:670-674`), a precomputed closure. The third-party
`luxas/cedar-sql` joins a hierarchy table with `EXISTS`.

**The lesson.** Inlining grants as literals grows with N. Shipping the
same literals as *rows* (`VALUES`) and joining lets the engine use an
index. Oso Cloud made that move; it is the move §8 measures.

## 7. How many grants and groups real users hold

No source measures the effective grant count per user. The published
numbers are caps. Caps exist because the tails are real.

**Groups per user (all declared limits):**

| system | limit | source |
|---|---|---|
| Okta | 100 groups in a groups claim | https://support.okta.com/help/s/article/how-to-exceed-the-100-groups-limitation-on-a-claim |
| Entra ID | 200 groups in a JWT, 150 in SAML, then an "overage" pointer | https://learn.microsoft.com/en-us/entra/identity/hybrid/connect/how-to-connect-fed-group-claims |
| Active Directory | 1,015 groups, nesting included (token size) | https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/plan/active-directory-domain-services-maximum-limits |
| Kerberos default token | breaks past about 120 universal groups | https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-authentication-problems-if-user-belongs-to-groups |
| Google Workspace | about 3,600 direct, about 9,000 direct plus indirect | https://knowledge.workspace.google.com/admin/groups/understand-groups-policies-and-limits |

**Grants and ACL entries (declared limits):**

| system | limit | source |
|---|---|---|
| SharePoint | 50,000 unique permission scopes per list, 5,000 recommended | https://learn.microsoft.com/en-us/office365/servicedescriptions/sharepoint-online-service-description/sharepoint-online-limits |
| Google Drive | 600 people per file; 100 groups per file | https://support.google.com/drive/answer/2494822 |
| Dropbox | 30,000 shared folders per account; sync no more than 1,000 | https://help.dropbox.com/plans/large-deployments |

**Measured system scale.** Zanzibar: over 2 trillion tuples, over
1,500 namespaces, a median namespace near 15,000 tuples, over 10M QPS,
Check p95 under 10 ms (paper §4). Google Drive search issues "tens to
hundreds of authorization checks" per result page (§4.5). SpiceDB's
benchmark: 1M QPS over 100B relationships, Check p95 5.76 ms, a 95.9%
cache hit rate (https://authzed.com/blog/google-scale-authorization).
Okta FGA: 1.05M RPS over 100B tuples
(https://auth0.com/blog/getting-unlimited-scalability-with-okta-fine-grained-authorization/).

**What this means for vfs.** A person in 50 groups, each group holding
10 folder grants, has up to 500 covering prefixes before minimisation.
Dropbox's "1,000 shared folders" and Drive's per-file sharing both put
a heavy user's shared-with-me list in the hundreds to thousands. vfs
should expect callers with hundreds to low thousands of covering
prefixes and make that case flat. It is not a pathological tail.

## 8. The probe: six shapes, same rows

`studies/2026-09-30-authz-list-filtering/probe.py` builds a lean copy
of the tables glean scans: an entry table (`path` with vfs's
`BytewiseString` and its unique index) and a chunk table (`dl`, a
score), 50,000 entries in the glean bench's layout (10 × 100 × 50).
Each caller is a minimal prefix set. Two statements per shape, both
shaped like glean's partial-caller scans: `count` (visible chunk count
and total length, the BM25 statistics) and `top10` (the ten lowest
scores over every visible chunk, the vector leg's shape). Every shape
is asserted to return the same count and the same ten ids. SQLite runs
with vfs's `PRAGMA case_sensitive_like = ON`.

The six shapes:

| shape | what it is | writes? | binds |
|---|---|---|---|
| `like` | today's arms, OR'd, split at 400 arms (vfs splits at 200) | no | 2 per arm |
| `range` | the same with `path >= p/ AND path < p0` | no | 3 per arm |
| `tree` | the sorted ranges as a balanced `CASE path < split THEN … ELSE … END`: about log2(2N) comparisons per row | no | about 6 per arm |
| `stab` | ranges in a small table; each row looks up the greatest range start at or below its path (`ORDER BY lo DESC LIMIT 1`) | yes | 1 |
| `drive` | the same table, joined: `path >= lo AND path < hi` | yes | 1 |
| `values` | `drive` with the ranges as a literal `VALUES` list, 1,000 ranges per statement | no | 2 per range, 4 per arm |

### 8.1 SQLite, 50,000 entries (median of 3 warm runs, ms)

`count` / `top10`, in ms. "rows" is how many entries the caller sees.

| caller | arms | rows | like | range | tree | stab | drive | values |
|---|---|---|---|---|---|---|---|---|
| 1 folder | 1 | 50 | 1.0 / 0.9 | 0.8 / 0.8 | 11 / 10 | 16 / 15 | 1.2 / 1.0 | 1.7 / 1.6 |
| 10 folders | 10 | 500 | 2.0 / 1.9 | 2.0 / 2.2 | 16 / 21 | 22 / 23 | 1.4 / 1.3 | 3.2 / 3.2 |
| 100 folders | 100 | 5,000 | 201 / 207 | 204 / 199 | 16 / 18 | 17 / 18 | 1.5 / 1.5 | 4.8 / 5.0 |
| 500 folders | 500 | 25,000 | 895 / 871 | 906 / 929 | 34 / 80 | 20 / 21 | 5.9 / 6.2 | 23 / 25 |
| one top folder | 1 | 5,000 | 1.7 / 1.7 | 1.6 / 1.7 | 5.7 / 6.1 | 16 / 17 | 1.2 / 1.3 | 1.5 / 1.5 |
| 5,000 files | 5,000 | 5,000 | 9,964 / 9,949 | 9,733 / 9,968 | 442 / 734 | 21 / 21 | 4.9 / 5.1 | 170 / 184 |

The plans (`runs/plans-sqlite.md`) show why. `like` and `tree` scan the
whole chunk table and test each row. `drive` and `values` read the
ranges first, then run one `path` index range search per range
(`SEARCH … USING COVERING INDEX … (path>? AND path<?)`), then fetch
the chunks by `entry_id`.

### 8.2 Postgres 17, 50,000 entries (median of 3 warm runs, ms)

Same layout. Postgres runs with its default `jit = on`.

| caller | arms | rows | like | range | tree | stab | drive | values |
|---|---|---|---|---|---|---|---|---|
| 1 folder | 1 | 50 | 1.1 / 0.9 | 1.4 / 0.8 | 7.5 / 7.1 | 54 / 52 | 9.1 / 4.3 | 8.2 / 6.3 |
| 10 folders | 10 | 500 | 5.4 / 4.3 | 2.8 / 2.2 | 13 / 12 | 49 / 49 | 13 / 7.1 | 6.9 / 6.6 |
| 100 folders | 100 | 5,000 | 15 / 15 | 8.2 / 7.9 | 18 / 17 | 122 / 118 | 8.5 / 7.6 | 15 / 14 |
| 500 folders | 500 | 25,000 | 149 / 143 | 31 / 32 | 1,804 / 2,173 | 150 / 142 | 21 / 20 | 54 / 55 |
| one top folder | 1 | 5,000 | 6.2 / 5.4 | 5.7 / 5.3 | 10 / 9.4 | 54 / 53 | 7.1 / 5.6 | 7.7 / 6.0 |
| 5,000 files | 5,000 | 5,000 | 322 / 455 | 268 / 279 | 20,380 / 18,185 | 118 / 116 | 72 / 67 | 463 / 463 |

Postgres does better than SQLite on the OR list. It turns the arms into
a BitmapOr of one index scan per arm (`runs/plans-postgres.md`), so
`like` at 500 arms is 149 ms, not 895. But it still rechecks every
fetched row against the whole OR list, and plan time grows with N.

Two surprises, both explained by the plans:

- **`tree` collapses on Postgres because of JIT.** A 1,000-range `CASE`
  pushes the plan cost past `jit_above_cost`, and Postgres compiles the
  expression with LLVM on every run. At 500 folders `EXPLAIN ANALYZE`
  takes 1,366 ms with JIT on and 27 ms with it off
  (`runs/plans-postgres.md`, `runs/plans-postgres-nojit.md`). vfs
  cannot turn JIT off on someone else's server, so the tree is unsafe
  on Postgres.
- **`values` executes as fast as `drive` but loses end to end.** At
  1,000 ranges, `EXPLAIN ANALYZE` gives 10.6 ms for `values` and
  10.5 ms for the table (JIT off; the same Nested Loop over the ranges
  with an index scan per range). The gap is on the client: building a
  statement with 2,000 binds. SQLAlchemy alone takes 17.6 ms to
  compile the 1,000-range `VALUES` statement. At 5,000 files there are
  10 such statements.

### 8.3 One bind for the whole range list

The client-side cost disappears if the range list travels as *one*
value that the engine unpacks into rows. Every engine vfs supports has
a way:

| engine | one-bind table function | measured |
|---|---|---|
| Postgres | `unnest(:los::text[], :his::text[])` (two array binds) | yes, `unnest.py` |
| SQLite | `json_each(:ranges)` (one JSON text bind) | yes, `jsonbind.py` |
| SQL Server | `OPENJSON(:ranges)` (2016+) | no |
| Oracle | `JSON_TABLE(:ranges, …)` (12c+) | no |
| MariaDB | `JSON_TABLE(:ranges, …)` (10.6+) | no |

The `count` statement end to end, in ms, median of 5 warm runs:

| caller | ranges | Postgres `values` (statements) | Postgres `unnest` | Postgres `drive` | SQLite `values` (statements) | SQLite `json_each` |
|---|---|---|---|---|---|---|
| 1 folder | 2 | 3.8 (1) | 3.2 | 3.2 | 0.5 (1) | 0.2 |
| 10 folders | 20 | 6.2 (1) | 5.1 | 4.7 | 0.9 (1) | 0.3 |
| 100 folders | 200 | 13 (1) | 6.4 | 5.6 | 4.6 (1) | 1.2 |
| 500 folders | 1,000 | 52 (1) | 12 | 16 | 23 (1) | 5.6 |
| one top folder | 2 | 4.9 (1) | 5.3 | 5.6 | 1.4 (1) | 1.0 |
| 5,000 files | 10,000 | 460 (10) | 28 | 55 | 182 (10) | 11 |

The SQLite plan (`runs/sqlite-jsonbind.md`) is the drive shape: scan
the JSON rows, then one `path` index range search per range. So one
bind gives the table's speed with none of the table's writes. The
statement text is also the same for every caller, which is the Postgres
RLS lesson from §5: per-user variation in data, not in predicate
shape. And a single bind needs no chunking, so ADR 071's clause fan
disappears for this shape.

### 8.4 What the numbers say

In plain words:

- **Today's shape grows with the arm count.** SQLite: 1 ms at 10 arms,
  200 ms at 100, 900 ms at 500, 10 s at 5,000. Postgres grows more
  slowly (15, 149, 322 ms) because of BitmapOr, but it still grows.
- **Driving from the ranges is flat in the arm count.** It grows with
  the rows the caller can see, not with how many grants produced them.
  500 folders (25,000 visible rows) costs 6 ms on SQLite and 21 ms on
  Postgres. 5,000 files (5,000 visible rows) costs 5 ms and 72 ms.
- **The per-row lookup (`stab`) is flat but slow.** It is a correlated
  subquery: one index probe per candidate row. S1 already measured that
  cost for the grant `EXISTS`. It is never the best choice.
- **The `CASE` tree is flat per row but still scans everything**, and
  JIT makes it dangerous on Postgres.
- **Below about 10 arms, today's shape is as fast as anything.** The
  crossover is somewhere between 10 and 100 arms on SQLite, and around
  100 on Postgres.

### 8.5 Limits of this probe

- Two engines. S1 found SQL Server planned a `VALUES` join as a merge
  join over a clustered index scan (`abort=TimeOut`) and paid 3.6x the
  `IN` form. A table function's row estimate is a guess on every
  engine (SQL Server assumes 50 rows for `OPENJSON`), and the plan
  must put the ranges on the outside of a nested loop. The range join
  must be checked on SQL Server, Oracle and MariaDB before it ships.
- The one-bind scripts time only the `count` statement; the probe's
  `top10` tracked `count` closely in every shape.
- 50,000 entries, one chunk each. The drive shape's cost follows the
  visible rows, so a caller who sees half of a 1M-row mount still
  reads 500k rows. That is the floor any exact statistic pays; the
  whole-mount fast path pays the same.
- No holes and no owner arms. A hole splits a range in two (the rows
  before the hole, the rows after it), so it adds ranges, not a new
  shape. Owner arms (`owner_id = X AND path in ranges`) take the same
  join with an owner column on the range and one more equality.
- Exactness rests on disjointness. A `count` or `sum` over a join
  counts a row once per matching range, so the ranges must never
  overlap. A minimal prefix set guarantees that; a compiler bug that
  emits overlapping ranges would double-count, so the prototype needs
  an oracle test for it.
- The `\x01` end marker that closes the single-row range `[p, p\x01)`
  assumes no lawful path has a control byte after a segment. A real
  compiler would carry an explicit "exact row" flag instead.

## 9. What vfs could adopt

| option | per-query cost | writes | fits ADR 071? | verdict |
|---|---|---|---|---|
| A. Range join, ranges in **one bind** (`unnest` / `json_each` / `OPENJSON` / `JSON_TABLE`) | one seek per range + visible rows | none | yes: no table, no read writes, one bind | **adopt**, above a small threshold |
| A′. Range join, ranges as a `VALUES` list | as A on the engine; client build grows with N | none | yes, chunked at the bind budget | **fallback** where A has no table function or misplans |
| B. Literal `CASE` tree | full scan, log N per row | none | yes | **reject**: Postgres JIT turns it into seconds |
| C. Per-(rights, revision) table of ranges | as A | a write on the first read of new rights | no (ADR 071 rejected staging) | not needed: A matches it without the write |
| D. Leopard-style `group_closure` table | saves ≤ 8 statements per cache miss | per membership change: ancestors × descendants rows | yes | **defer**: the walk is not the cost |
| E. Path-ordered chunk ids for glean | visibility as id ranges, intersected in Rust | renumber at reindex only | yes | **adopt for glean's lexical leg**, own spec |
| F. Visible-set cache per (rights, data revision) | ~0 on a hit | none | yes | **defer**: needs an entries revision; a move invalidates it |
| G. Materialised `visible(principal, entry)` | one probe per row | S1: 1,850x the entry table | no | stays rejected (S1) |
| H. Post-filter only (CheckBulk style) | deepening loops for rare hits | none | partly | stays a complement: `Rights.admits` already post-checks |

Notes on each:

- **A** is Oso Cloud's move (grant facts shipped as rows and joined)
  with a range join in place of an equi-join, and Supabase's move
  (the user's set computed once, bound as an array). The compiled
  ranges come straight from `Rights`, which the `RightsCache` already
  holds per `(subjects, revision)`, so the JSON or array value can be
  cached beside it. The statement text is the same for every caller.
- **A′** is what vfs can ship on an engine where the table function is
  missing or misplans. It is still flat on the engine side; its cost
  is building the statement.
- **B** looked promising on SQLite (34 ms at 500 arms) but is a trap on
  Postgres: a large `CASE` trips JIT compilation on every run.
- **C** is S1's staged table. A gives the same plan without the write.
- **D** would matter if resolves missed often: many distinct subject
  sets, or a revision that bumps constantly. Measure the `RightsCache`
  hit rate before building it. Its write cost: adding member M to
  group G inserts one row per pair (M or a group under M) × (G or a
  group above G); removing one needs a path count or a local
  recompute, because two paths can join the same pair.
- **E** removes SQL from the hottest part of glean. It is a change to
  how the index numbers chunks, so it wants its own spec. It composes
  with A: the ranges that drive the path index also map to chunk-id
  ranges.
- **F** is SpiceDB's and OpenFGA's answer: cache the answer and accept
  a short staleness window (5 s quantization, 10 s TTL). vfs has no
  entries revision to key it on, and vfs's post-check can drop a row
  wrongly included but cannot recover one wrongly left out. Not now.

## 10. What to prototype in the glean bench

1. **A range compiler.** From `Rights`, emit sorted, disjoint,
   half-open ranges: one for the arm's own row, one for its subtree, a
   split per hole, and owner arms as ranges tagged with their owner.
   Pin it with an oracle test: ranges never overlap, and a row is in
   some range exactly when `Rights.admits` says so.
2. **A one-bind range source per dialect.** Postgres `unnest` of two
   arrays (with `COLLATE "C"` on the bounds), SQLite `json_each`, SQL
   Server `OPENJSON`, Oracle and MariaDB `JSON_TABLE`. A `VALUES` list
   (option A′) behind the same interface for anything else.
3. **`_visible_corpus` as a range join.** One statement, whatever the
   grant count. Disjoint ranges make the count and length sums exact.
4. **The vector leg as a range join.** The same join feeding
   `ORDER BY distance LIMIT depth`, one statement instead of one per
   clause.
5. **A threshold.** Keep today's arms below about 10 covering
   prefixes; switch above. Measure the crossover per engine.
6. **All five engines.** Rerun the 50,000-file glean bench at 1, 5,
   100, 500 and 5,000 grants on SQLite, Postgres, MariaDB, SQL Server
   and Oracle, with plans. Check that each engine puts the ranges on
   the outside of a nested loop. SQL Server is the known risk (S1's
   `VALUES` merge join).
7. **Separately, spec path-ordered chunk ids** (option E) and measure
   `_visible_lexicon` with visibility as id ranges in Rust.

## Recommendations

| Question | Recommendation |
|---|---|
| How do mature systems keep list cost flat? | They never test every row against every grant. They start from the grants and probe an index (SpiceDB, RLS best practice, Oso Cloud), or they precompute a join (Materialize, Leopard). Their predicate text does not grow with the user's grants. |
| How many grants does a user hold? | Unmeasured anywhere. Caps put groups per user at 100 to about 9,000 and shared items in the hundreds to thousands. Design for hundreds to low thousands of covering prefixes. |
| What should vfs adopt? | **A range join with the ranges in one bind.** Compile rights to sorted disjoint byte ranges, bind them as one array or JSON value, unpack them with the engine's table function, and join on `path >= lo AND path < hi`. Keep today's arms below about 10 prefixes. Keep a chunked `VALUES` list as the fallback. |
| Does it respect ADR 071? | Yes. No table, no read that writes. It removes the clause fan for this shape, since one bind never exceeds a budget. |
| Leopard for groups? | **Not now.** The walk is cached per revision and is not the cost. Revisit if the rights-cache hit rate is low in practice. |
| Caching the visible set? | **Not now.** No entries revision to key it on. |
| For glean specifically? | Prototype the range join in `_visible_corpus` and the vector leg (§10). Then spec path-ordered chunk ids so the lexical leg's visibility becomes id ranges in Rust. |
| Stays rejected | A materialised visibility table (S1); a staged table on the read path (ADR 071); a literal `CASE` tree (Postgres JIT). |

## One-line version

Mature systems never test each row against each grant; vfs should stop
too: compile the caller's rights to sorted, non-overlapping path
ranges, send them as one bound value, and let the engine walk the
`path` index range by range, which kept 500 to 5,000 grants at 5 to
72 ms where today's OR list took 0.15 to 10 s.
