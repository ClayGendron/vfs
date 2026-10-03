# Row-labelled ACLs and the LIST problem: how systems that store permissions at scale answer "which rows can I see?"

- **Status:** research memo. Commits us to nothing. Input to the fix
  for review findings 4, 6 and 7 of 2026-10-01 (the posture-hole
  blow-up in `grants.py` / `rights.py`) and to a possible amendment of
  ADR 072's compile model.
- **Date:** 2026-10-02
- **Owner:** Clay Gendron
- **Question:** vfs compiles each caller's rights from the grant rows.
  Explicit prefix grants become *arms*. The mount's open posture
  becomes one root arm, and every private sub-posture (each user's
  private home) becomes a *hole* cut out of that root arm. At about
  1,000 private homes `glean` fails, because one SQL clause carries
  every hole. `pieces()` is quadratic in holes (17 s at 10,000). The
  meet across a subject set is a cross product. The target is 100,000+
  users, each with a private home and dozens of shared folders. The
  hypothesis to test against prior art: **a caller's compiled rights
  must grow with the caller's own grants, never with the number of
  other principals; and a row-position fact such as "effective public
  level" belongs on the row, written at write time and relabelled per
  subtree when a posture changes, so the "everyone" part of a query is
  one column compare.** How do systems that store ACLs at scale answer
  LIST ("which rows may I see?") as opposed to CHECK ("may I see this
  row?")? What do they put on the row? What does write-time
  propagation cost them? Where do they hit ceilings?
- **Method:**
  1. Line-level reading of six code bases, each by its own subagent,
     with every claim cited `file:line` at the refreshed commit:
     Jackrabbit Oak's permission store and query filter; OpenSearch
     Security's document-level security; SpiceDB and OpenFGA's list
     verbs; Postgres row-level security in the rewriter and planner;
     the Linux and FreeBSD inode permission checks and name walks.
     Optional: oso, casbin, seaweedfs, juicefs, minio.
  2. Public documents, read 2026-10-02: Microsoft's SharePoint limits
     pages and the `[MS-WSSFO3]` schema spec; Windows ACE inheritance
     and `SetNamedSecurityInfo` / `TreeSetNamedSecurityInfo`
     reference pages; the NTFS move/copy permission rules; the
     Zanzibar paper (Pang et al., USENIX ATC 2019), read from the PDF
     text.
  3. No experiment was run for this memo. A parallel study is running
     spikes on SQLite and Postgres; §9 names what it should measure.
  No code was copied from any reference repo. Citations are
  `file:line` at the commits below; quotations are from documentation
  prose only.
- **Sources** (every clone refreshed to `origin/HEAD` on 2026-10-02
  unless noted; licence re-checked after the refresh):
  - `jackrabbit-oak` — `trunk`, `f67eebf` (2026-10-01), Apache-2.0.
  - `opensearch-security` — `main`, `9fc17827` (2026-10-01), Apache-2.0.
  - `spicedb` — `main`, `dbc1601` (2026-10-02), Apache-2.0.
  - `openfga` — `main`, `97943bf` (2026-09-28), Apache-2.0.
  - `postgres` — `master`, `6f3bdada` (2026-10-02), PostgreSQL licence.
  - `freebsd-src` — `main`, `d9e2caccfac1` (2026-10-02), BSD-2-Clause.
  - `linux` — **not refreshed: the clone is dirty** (13 modified files
    under `include/uapi/linux/netfilter/`, `net/netfilter/`,
    `tools/memory-model/`). Read as-is at `faeab1661` (`master`),
    GPL-2.0. The cited files are not among the dirty ones.
  - `oso` `7292df0` (2025-02-26), `casbin` `524f3f2` (2026-09-11),
    `seaweedfs` `3e679e9` (2026-10-03), `juicefs` `adcca1c`
    (2026-09-29): all Apache-2.0. `minio` `7aac2a2` (2026-02-12),
    AGPL-3.0 — studied only, as CLAUDE.md allows.
  - Web: SharePoint Server 2016/2019 software boundaries and limits
    (learn.microsoft.com, `software-boundaries-limits-2019`, updated
    2024-01-16); SharePoint Online limits (`sharepoint-online-limits`,
    2025-05-29); "Best practices for using fine-grained permissions in
    SharePoint Server" (2017-09-27); "Troubleshoot common fine-grained
    permissions issues" (2017-09-06); `[MS-WSSFO3]` AllDocs Table and
    Unique Permissions Result Set; Win32 "ACE Inheritance Rules",
    `SetNamedSecurityInfoA`, `TreeSetNamedSecurityInfoA`; KB 310316
    "Permissions when you copy and move files" (2026-02-12); "How NTFS
    Works" (Windows Server 2003 archive); an archived TechNet thread
    (2019-08-17) with an ETW trace of ACL propagation. The Zanzibar
    paper, `storage.googleapis.com/gweb-research2023-media/pubtools/5068.pdf`.
  - vfs: `src/vfs/storage/grants.py`,
    `src/vfs/storage/backends/database/rights.py`,
    `src/vfs/models/rows.py`; the review report of 2026-10-01
    (findings 4, 6, 7); sibling memos
    `2026-09-30-authz-list-filtering-prior-art.md` and
    `2026-09-30-search-document-level-security-prior-art.md`, which
    this memo extends rather than repeats.

## Terms used here

- **CHECK.** "May this caller do this to this one row?" One row, one
  answer.
- **LIST.** "Which rows may this caller see?" Many rows, a filter. A
  search, a listing, a tree, a count.
- **Label.** A fact stored on the row itself that a permission decision
  reads. A Unix inode's mode bits are a label. A SharePoint item's
  `ScopeId` is a label.
- **Compile.** Work done once per caller (or per session) to turn the
  stored grants into something a query can use. vfs's `Rights` is a
  compile.
- **Propagation.** Work done at write time to push a permission change
  down a subtree so that each row's label stays right.
- **Hole.** In vfs today, a sub-prefix cut out of an arm because a
  deeper posture row lowers the everyone level there
  (`grants.py:113-117`, `_everyone_arms` at `grants.py:309-324`).
- **Posture.** The everyone level of a prefix: open, shared, private
  (`grants.py:48-52`).

## Bottom line

1. **No studied system compiles other principals' grants into this
   caller's rights.** Oak keys its store by principal first, so a
   session reads only its own principals' entries
   (`PermissionCacheBuilder.java:51-52`). OpenSearch unions only the
   caller's mapped roles (`AbstractRuleBasedPrivileges.java:542-587`).
   SpiceDB and OpenFGA start the walk at the subject. Postgres
   substitutes `current_user` into one fixed expression. vfs is the
   outlier: `_everyone_arms` folds every private sub-posture in the
   mount into every caller's root arm (`grants.py:309-324`), and
   finding 4 is the direct consequence.
2. **"Private home under an open root" is the one shape where
   per-caller compile fails and a row label wins.** It is a deny
   expressed as an exception to a broad allow. Zanzibar-style systems
   have no deny at all: Google Drive's private objects are reached by
   a computed `owner` relation, not by subtracting them from a public
   set (paper §4.5). Unix has no deny either: a private home is simply
   a row whose mode bits say so, and `ls /home` reads 100,000 dirents
   with zero per-child checks (`fs/readdir.c:87-118`). Oak *does* have
   deny, and its own private-homes case pushes `everyone` into the
   lazy per-path mode (§1.5 below).
3. **Every system that puts a label on the row pays for it at write
   time, and the mature ones bound that cost by indirection.** NTFS
   copies inherited ACEs onto every child and the user-mode library
   walks the whole tree (`SetNamedSecurityInfo` remarks; measured
   about 500 µs per child, so about 2,000 objects/s). SharePoint puts
   a `ScopeId` on each row and a binary ACL per scope, caps scopes at
   50,000 per list, recommends 5,000, warns that "the effective number
   of scopes allowed in a particular query" can fall to "1,000 to
   2,000", and refuses ACL propagation past 500 uniquely scoped
   children. juicefs stores an ACL *id* per inode into a deduplicated
   ACL table (`pkg/meta/sql.go:91-92, 125-133`). The pattern is: the
   row carries a small handle; the handle resolves to a shared record;
   relabelling touches rows only when the handle must change.
4. **For vfs, the hypothesis holds, with a narrower label than
   "effective public level".** The cheapest label the prior art
   supports is a per-row *posture handle* that changes only when the
   nearest posture row above the path changes. That is SharePoint's
   `ScopeId` restricted to the `*` rows. The write cost is one `UPDATE
   ... WHERE path range` per posture write, which is exactly the
   subtree cost SharePoint and NTFS pay, bounded by vfs's own chunking
   rules. Explicit grants stay path ranges (ADR 072) and never touch
   the row.
5. **Two things the prior art does not settle for vfs:** whether the
   label is a level or a handle, and what happens on a move across
   labelled subtrees. §8 and the markers in §10 list them.

## 1. Apache Jackrabbit Oak: label-free store, keyed by principal, post-filtered LIST

Oak is the closest analogue because it is a tree of nodes with ACLs on
some of them, backed by a document store, and it filters query results
per session.

**What is stored.** ACL changes are mirrored into a hidden tree
`/jcr:system/rep:permissionStore/<workspace>/<principal>/<hash(path)>/<index>`
(`PermissionHook.java:45-61`; `oak-doc/.../permission/default.md:82-109`).
The principal comes first (`PermissionUtil.java:81-83`), then the Java
`hashCode` of the access-controlled path (`PermissionUtil.java:60-63`),
with collision children `c0`, `c1`, … (`PermissionStoreEditor.java:181-210`).
Each entry holds `rep:isAllow`, `rep:privilegeBits` and the
restrictions (`PermissionStoreEditor.java:261-269`). A per-principal
counter `rep:numPermissions` counts that principal's access-controlled
paths (`PermissionStoreEditor.java:217-219`). **Nothing is written on
content nodes.** Inheritance is resolved at read time.

**Write-time cost.** The `PermissionHook` diffs the changed subtree,
stops at each `rep:ACL` node, and rewrites only that ACL's entries for
the principals it names (`PermissionHook.java:89-122, 151-210`;
`PermissionStoreEditor.java:170-232`). The work is bounded by the ACL's
own size. No descendant is touched.

**Per-session compile.** One `PermissionProviderImpl` per session root
(`MutableRoot.java:132-137`). `CompiledPermissionImpl` builds one entry
provider for the user principals and one for the group principals
(`CompiledPermissionImpl.java:102-121`). The load strategy
(`CacheStrategyImpl.java:23-27, 57-73`; `PermissionCacheBuilder.java:48-121`):
a principal with at most **10** access-controlled paths is loaded
fully; if the sum over the session's principals is under **250**, a
flat path-to-entries map is built in memory; otherwise entries are
fetched lazily per path, with a miss cache of **1,000** paths
(`PrincipalPermissionEntries.java:37, 59-64`). Only the session's own
principal nodes are read (`PermissionCacheBuilder.java:51-52`;
`PermissionStoreImpl.java:141-152`).

**CHECK.** `isGranted(path)` walks from the path to the root, user
entries before group entries, deepest first, first match wins
(`CompiledPermissionImpl.java:284-381`; `PermissionEntryProviderImpl.java:95-134`;
ordering `PermissionEntry.java:88-100`). The tree form memoises a
`TreePermissionImpl` per node with a pointer to its parent's
(`CompiledPermissionImpl.java:175-216, 500-544`), and a plain
unrestricted `jcr:read` decision collapses to `ALLOW_ALL` /
`DENY_ALL` so a whole subtree can be skipped
(`ReadStatus.java:50-66`; `SecureNodeState.java:103-116`).

**LIST.** Every query row is post-filtered by CHECK. `SelectorImpl`
drops a row when `getTree(path).exists()` is false
(`query/ast/SelectorImpl.java:530-569`, the check at 563), and
`exists()` is `TreePermission.canRead()` (`SecureNodeBuilder.java:126-129`).
The Lucene cursor yields raw paths with no ACL term
(`oak-search/.../FulltextIndex.java:462-480`); `Filter.isAccessible`
is used only for spell-check and suggestion candidates and facet
counts, which would otherwise leak (`LucenePropertyIndex.java:488-540`;
`SecureSortedSetDocValuesFacetCounts.java:139-142`). So LIST cost is
(rows the index returns) × (an ancestor walk, mostly memoised).

**Invalidation.** There is no store-root hash. Every session refresh,
save or rebase calls `permissionProvider.refresh()`, which discards
the whole compile (`MutableRoot.java:239-265`;
`CompiledPermissionImpl.java:144-156`). The 250-entry cap exists
precisely so that refresh-heavy sessions do not re-read everything
(`CacheStrategyImpl.java:38-47`, OAK-9203).

**Ceilings.** The query engine's `limitReads` throws
`RuntimeNodeTraversalException` past **100,000** nodes read, and
"applies whether or not an index is used" and "depends on … access
rights" (`FilterIterators.java:65-76`; `QueryEngineSettings.java:56-60`;
`oak-doc/.../query-engine.md:351-355`). Rows dropped by the ACL
filter still count. Documentation warns that redundant group
membership "will impact performance of permission evaluation"
(`bestpractices.md:161`) and that restrictions "may heavily impact
overall read/write performance" (`restriction.md:267`).

## 2. OpenSearch Security: a stored query per role, nothing on the document

Document-level security (DLS) is a query string attached to a role.
Nothing is written on a document (`DocumentPrivileges.java:58`; the
whole `dlsfls` package has no per-document field).

**Per-request compile.** The caller's mapped roles are gathered once
(`PrivilegesEvaluatorImpl.java:240`). For each index,
`getRestriction` walks **only the caller's roles**
(`AbstractRuleBasedPrivileges.java:406-457, 526-588`), reading each
role's rule from maps precomputed at config load. The result is a
`DlsRestriction`, a list of rendered queries, OR'd as a `SHOULD`
bool with minimum-should-match 1 (`DlsRestriction.java:54-95`). A
role with no DLS on the index means no restriction
(`AbstractRuleBasedPrivileges.java:412-426`). There is **no per-user
cache**; the only caches live for one request on one node
(`PrivilegesEvaluationContext.java:56-74`). A roles-config change
swaps in a whole new `DlsFlsProcessedConfig`
(`PrivilegesConfiguration.java:197-206`).

**LIST.** Three modes (`plugins.security.dls.mode`, default
`adaptive`, `DlsFlsValveImpl.java:847-864`):
- *lucene_level*: the DLS bool is wrapped in a constant-score query
  and the user's query is pushed inside it as a `MUST`, replacing the
  shard's parsed query (`DlsFlsValveImpl.java:483-580`, 566-574).
  For get/mget a per-segment bitset is built fresh by running the DLS
  query's scorer, with Lucene's query cache turned off
  (`DlsFlsFilterLeafReader.java:145-176`, `setQueryCache(null)` at 150).
- *filter_level*: the request itself is rewritten into a top-level
  bool, one `should` clause per (index, role query), and re-submitted
  (`DlsFilterLevelActionHandler.java:804-876`).
- *adaptive*: filter level only when a role's query contains a terms
  lookup (`DlsFlsValveImpl.java:255-281`).

**Cost model.** Per query, per shard: the caller's own DLS clauses
run as a filter. Not cached as a bitset. The shard request cache is
disabled for any DLS request (`DlsFlsValveImpl.java:354-356`). Writes
do nothing for DLS; the valve only refuses some writes on restricted
indices (`DlsFlsValveImpl.java:359-398`).

**Private homes.** With one role per user (`owner:<u>`) and one shared
role (`public:true`), the caller's compile is two clauses. The other
99,999 roles are map entries never visited. Better, the design
intends one *dynamic* role `owner:${user.name}` rendered per request
(`DocumentPrivileges.java:126-133, 157-192`): one rule for all users.
This is the clearest statement in the prior art of the principle
"the everyone part and the owner part are each one column compare,
and neither grows with the user count."

**Ceilings.** None on role count in the code. The only warnings:
computing the whole index-to-rule map "can be expensive"
(`IndexToRuleMap.java:22-24`); `statefulRules` is volatile and "should
be limited, e.g., not used in tight loops"
(`AbstractRuleBasedPrivileges.java:82-84`). A terms-lookup size cap
(`index.max_terms_count`, 65,536) lives in OpenSearch core, outside
this plugin.

## 3. SpiceDB and OpenFGA: LIST is a reverse walk from the subject, with a cap

The sibling memo of 2026-09-30 covers the algorithms. This section
adds only what bears on labels, propagation and the private-homes
shape.

**What is stored.** Tuples only, with transaction ids for MVCC:
SpiceDB's `relation_tuple(namespace, object_id, relation,
userset_namespace, userset_object_id, userset_relation, created_xid,
deleted_xid)` (`migrations/zz_migration.0001_...:23-35`,
`zz_migration.0010_add_xid8_columns.go:17-19`). **No per-object
materialised row.** A grep of both repos for Leopard, materialise and
denormalise finds nothing data-level; the only precompute is the
schema's type-level reachability graph (`pkg/schema/reachabilitygraph.go:167-170`).

**LIST.** SpiceDB `LookupResources` (`lookupresources3.go:102-230`):
start at the subject, read tuples by subject through the reverse
index `ix_relation_tuple_by_subject`
(`zz_migration.0002_add_reverse_index.go:10-11`), chunk the found
resources by 100, and re-dispatch with those as the new subjects until
the target type is reached. Candidates that reached through an
intersection or exclusion are confirmed by a bulk CHECK with hints
(`lookupresources3.go:914-935`, comment at 928-929: "This shears the
tree of results for intersections, exclusions and intersection
arrows"). Limits: `--max-lookup-resources-limit` default 1,000
(`pkg/cmd/server/server.go:136`), dispatch depth 50 (`:101`),
streamed with a cursor (`permissions.go:574-600`). OpenFGA
`ListObjects`: the same shape (`reverse_expand.go:306-480`), a Check
per candidate (`list_objects.go:442-479`), **3 s deadline and 1,000
results by default** (`pkg/server/config/config.go:27-28`), the
deadline returning a partial set silently (`list_objects.go:486-489`).
The changelog says the caps "help protect the server from excessively
long lived and large responses" (`CHANGELOG.md:1654-1656`).

**Where cost grows.** Per hop, with the out-degree of the current
frontier. For the private-homes schema `viewer = owner + parent->viewer`
with `folder:root#viewer@user:*`, ann's direct leg costs her own rows
plus the wildcard rows (`lookupresources3.go:596-607`). But once the
frontier holds `folder:root`, the arrow entrypoint reverse-reads every
`folder:*#parent@folder:root` row (`lookupresources3.go:637-700`), so
the walk fans out over every child of root: **world size**. The
1,000-result cap and the cursor are what keep that bounded. This is
the Zanzibar cost shape: a broad public grant makes LIST enumerate
the world, and the API caps the answer rather than making it cheap.

**The paper's own answers** (Zanzibar, §2.3.1, §2.4.5, §3.2.4, §4.5):
there is no list verb. The API is Read, Write, Watch, Check, Expand.
`Expand` "is crucial for our clients to reason about the complete set
of users and groups that have access to their objects, which allows
them to build efficient search indices for access-controlled content"
(§2.4.5). Search is a client problem: "answering a search query
requires conducting ACL checks for all candidate results" (§3.2.5),
and Drive clients "often issue tens to hundreds of authorization
checks to serve a single set of search results" (§4.5). For private
objects the paper adds a `computed_userset` that infers "an object's
owner ID from the object ID prefix, which reduces space requirements
for clients such as Drive and Photos that manage many private
objects" (§4.5): the owner is derived from the row's own id, not
stored as a tuple per object. Leopard flattens *group nesting*
(`GROUP2GROUP`, `MEMBER2GROUP`, §3.2.4), not object visibility, and
"a single Zanzibar tuple addition or deletion may yield potentially
tens of thousands of discrete Leopard tuple events" (§3.2.4). Google
pays propagation for groups and refuses to pay it for objects.

## 4. Postgres row-level security: one fixed expression, index-usable when it is a column compare

**Where.** `get_row_security_policies` (`rewrite/rowsecurity.c:98`)
runs once per relation per statement from the rewriter
(`rewriteHandler.c:2267`). Policies matching the command and the
caller's roles (`rowsecurity.c:556-618, 931-949`) are combined:
permissive ones OR'd into one element, restrictive ones one element
each (`rowsecurity.c:715-792`), and prepended to the range-table
entry's `securityQuals` (`rewriteHandler.c:2332-2333`). The expression
tree is copied from the relcache into every statement
(`rowsecurity.c:736, 760`). **No per-row label, no per-caller compile,
no per-session result cache**; the plan cache merely re-rewrites when
the role or the `row_security` setting changes
(`plancache.c:738-743, 979-981`).

**Planner.** Security quals get `security_level = i`
(`initsplan.c:1944-1984`); user quals go one level above. The rule in
`optimizer/README:1237-1250`: a lower-level qual runs first unless the
higher one is leakproof. **An index scan can use the RLS qual itself**:
`match_clause_to_index` only refuses a clause that is not
`restriction_is_securely_promotable` (`indxpath.c:2601-2606`;
`restrictinfo.c:416-434`), and the RLS qual sits at the minimum level,
so it always qualifies. A user `WHERE path = $1` with a leakproof
operator is promoted to level 0 and can drive the index while the
policy runs as a filter (`createplan.c:5369-5372`).

**Cost shape, confirmed from the docs.** "This expression will be
evaluated for each row prior to any conditions or functions coming
from the user's query" (`doc/src/sgml/ddl.sgml:2955-2959`). "Since
policy expressions are added to the user's query directly, they will
be run with the rights of the user running the overall query"
(`create_policy.sgml:745-747`). The docs say nothing about index use
or performance of the policy itself.

**The important negative.** Sublinks inside `securityQuals` are
**never turned into joins**: `pull_up_sublinks` walks only the join
tree (`prepjointree.c:681-690`), while security quals go through
`SS_process_sublinks` → `make_subplan` (`planner.c:1168-1172,
1476-1477`). So a policy `USING (path LIKE ANY (SELECT prefix FROM
grants WHERE role = current_user))` becomes an uncorrelated ANY
SubPlan; `LIKE` is not hashable (`subselect.c:532-553, 801-815`), so
the prefix list is materialised once and every candidate row is
tested against every prefix: rows × prefixes, which is vfs's measured
shape of 2026-09-29. A policy `USING (NOT EXISTS (SELECT 1 FROM
private_homes h WHERE files.path LIKE h.prefix || '/%'))` is worse: a
correlated EXISTS SubPlan per row, with no hashed alternative because
`convert_EXISTS_to_ANY` needs an equality (`subselect.c:1995-2045`).
That is the posture-hole predicate, written in Postgres's own
language, and Postgres cannot make it cheap either.

**Private homes.** `USING (public OR owner = current_user)` is one
OR of two leakproof column compares, servable by a BitmapOr over an
index on `public` and one on `owner` (`restrictinfo.c:405`;
`indxpath.c` OR-clause paths). `current_user` is stable and becomes a
per-scan runtime key (`nodeIndexscan.c:607`). This is the cheapest
shape in the whole study, and it exists only because `public` is a
column on the row.

## 5. Linux and FreeBSD: the row is the label, the walk is the check

**The inode carries mode, uid, gid and the ACL.** Linux `struct inode`
holds `i_mode`, `i_uid`, `i_gid` and cached `i_acl` / `i_default_acl`
(`include/linux/fs.h:768-776`). FreeBSD's `vaccess` takes
`file_mode, file_uid, file_gid` as arguments (`sys/kern/vfs_subr.c:5655-5765`);
UFS reads the ACL from the inode's own extended attribute on each
check (`ufs_vnops.c:369-476`; `ufs_acl.c:163-171`).

**CHECK is a compare.** `acl_permission_check` (`fs/namei.c:433-492`)
first tests the cheap case "everybody has the requested rights, and
there are no ACLs to check" (comment at 440-454), then owner, ACL,
group, other. `generic_permission` (`namei.c:516-558`) falls through to
capabilities only on failure. POSIX ACL evaluation is a linear scan of
the inode's own entries (`fs/posix_acl.c:373-442`). The ACL cache is a
per-inode pointer with `ACL_NOT_CACHED` / `ACL_DONT_CACHE` sentinels
(`fs.h:607-625`; `posix_acl.c:46-186`). **Nothing is compiled per
caller, anywhere.**

**The walk.** `link_path_walk` calls `may_lookup` at the top of every
component (`namei.c:2574-2600`); the fast path skips to the LSM hook
when the directory grants exec to everyone and has no cached ACL,
because "majority of real-world traversal happens on inodes which
grant it for everyone" (`namei.c:670-695`). FreeBSD's lockless
`cache_fplookup` reads `i_mode` with an atomic load and validates the
answer with the vnode sequence counter (`vfs_cache.c:6279-6330,
6350-6468`; `ufs_vnops.c:482-514`; `vn_seqc` at `sys/sys/vnode.h:138`).

**Why `ls /home` is cheap with 100,000 homes.** `iterate_dir` checks
only the directory's own read permission once at open
(`fs/readdir.c:87-118`; `namei.c:4276`) and emits every dirent with no
child check. `stat` on a child does the walk (exec on each ancestor)
and then `vfs_getattr`, which never calls `inode_permission`
(`fs/stat.c:254-263, 341-362`). So `ls -l /home` is 100,000 dcache
lookups under one already-checked parent and zero per-child mode
checks. The listing is cheap because POSIX defines it so: a readable
directory lists every name in it. vfs's visible/road/hidden model
(ADR 065, ADR 070) deliberately does not: a hidden row is absent.
That is the one place where the Unix baseline does not transfer and
vfs must pay a per-row decision on LIST.

**Propagation.** Default ACLs are copied onto a new inode at create
time only (`posix_acl.c:632-681`, `simple_acl_create` at 1036-1053);
NFSv4 inheritance on FreeBSD is computed only in `ufs_mkdir` and
`ufs_makeinode` (`subr_acl_nfs4.c:1185-1196`; `ufs_vnops.c:1980-2003,
2172, 2930`). Changing a directory's default ACL later relabels
nothing. There is no code path that could.

## 6. SharePoint and NTFS: the row carries a handle, and the documented ceilings

These are the two production systems that put a label on every row.
Their documentation is the best record of what that costs.

### 6.1 SharePoint: `ScopeId` on the row, a binary ACL per scope

**What is on the row.** `[MS-WSSFO3]` AllDocs Table: `ScopeId
uniqueidentifier NOT NULL`, "The Scope Identifier of the scope of the
document." The Unique Permissions Result Set returns `(ScopeId, Acl
varbinary(max), AnonymousPermMask bigint)`, where `Acl` is "The binary
serialization of the WSS ACL Format ACL of the security scope." So:
every row carries a scope handle; the ACL is stored once per scope;
and the anonymous level is a separate mask on the scope. This is the
"effective level on the row" idea, taken one step further: the row
holds a *pointer to* the effective ACL, not the level itself.

**The definition.** "A scope is the security boundary for a securable
object and any of its children that don't have a separate security
boundary defined. A scope contains an Access Control List (ACL)"
(SharePoint 2016/2019 limits page, "Security scope" row).

**The documented ceilings** (all from the 2016/2019 limits page unless
noted):
- "The maximum number of unique security scopes set for a list can't
  exceed 50,000. For most farms, we recommend that you consider
  lowering this limit to 5,000 unique scopes." Online: "The supported
  limit of unique permissions for items in a list or library is
  50,000. However, the recommended general limit is 5,000."
- "When the number of unique security scopes for a list exceeds the
  value of the list view threshold (set by default at 5,000 list
  items), additional SQL Server round trips take place when the list
  is viewed, which can adversely affect list view performance."
- Best-practices page: "the effective limit is much smaller than
  50,000 if many scopes exist at the same hierarchical level. This is
  because display checks for items below that hierarchical level must
  be checked against all scopes above them. This limitation can cause
  the effective number of scopes allowed in a particular query to be
  reduced to 1,000 to 2,000."
- Online: "When a list, library, or folder contains more than 100,000
  items, you can't break permissions inheritance on the list, library,
  or folder. You also can't reinherit permissions on it."
- Propagation: "The maximum number of child objects with unique
  security scopes that can be updated during ACL propagation can't
  exceed 500. … if the maximum number of child objects with unique
  scopes is greater than 500, propagation will fail with only some of
  the children with unique scopes potentially being updated."
- Scope size: "5,000 per Access Control List (ACL). The size of the
  scope affects the data that is used for a security check
  calculation. This calculation occurs every time that the scope
  changes."
- Troubleshooting page: "If the membership of a scope is changed, the
  binary ACL must be recalculated. The addition of users at a child
  item unique scope will cause parent scopes to be updated with the
  new Limited Access members, even if this ultimately results in no
  change to the parent scope membership." And: "The number of uniquely
  scoped children isn't a significant issue, and can scale to large
  numbers. However, the number of principles that will be added as
  limited access up the chain of scopes to the first uniquely
  permissioned web will be a limiting factor."

**Reading.** SharePoint's cost is not the count of labelled rows. It
is (a) the number of *distinct* scopes a query must consult, because
each scope's ACL is parsed per query, and (b) the upward propagation
of "Limited Access" memberships, which rewrites parent scopes on every
child scope change. Both are costs of putting *principals* in the
label. A label that holds only a position fact (which scope am I in)
is the cheap half; a label that holds who-may-read is the expensive
half.

### 6.2 NTFS: inherited ACEs are copied onto every child, by a user-mode walk

**The rule.** "The system automatically propagates inheritable access
control entries (ACEs) to child objects according to a set of
inheritance rules. The system places inherited ACEs in the
discretionary access control list (DACL) of the child" (ACE
Inheritance Rules). "If you are setting the discretionary access
control list (DACL) … of an object, the system automatically
propagates any inheritable access control entries (ACEs) to existing
child objects, according to the rules of inheritance"
(`SetNamedSecurityInfoA`, Remarks). The inherited ACEs are placed
"after all of the noninherited ACEs in the DACLs of the child
objects". So each child's DACL is a physical copy, not a pointer.
`TreeSetNamedSecurityInfo` exposes the walk: it rewrites "the object
specified by the pObjectName parameter and the tree of child objects
of that object", with a progress callback invoked per object and
`ProgressCancelOperation` to stop it.

**Storage.** NTFS keeps "unique security descriptors for all files
within a volume" in the `$Secure` metadata file ("How NTFS Works",
table of metadata files). Files with identical descriptors share one
record; each file record carries an id into it. This is the handle
pattern again: the row holds a small id; identical labels share a
record; relabelling a subtree rewrites ids.

**Measured cost** (archived TechNet thread, 2019-08-17; one
engineer's ETW trace, not a Microsoft figure): "it looks as though it
takes 500 microseconds to update each child, 250 microseconds of which
is spent in NTFS code. A very unreliable extrapolation might suggest
that 2000 objects could be updated per second." The same thread
establishes that "There is no support for propagating inheritance in
the NTFS driver — the functionality is implemented in a user mode
library" (`ntmarta.dll`), and that the propagation is synchronous and
sequential. The original poster observed Explorer doing "2 or 3 at
best" files per second with progress UI.

**Moves.** KB 310316: "By default, an object inherits permissions from
its parent object, either at the time of creation or when it is
copied or moved to its parent folder. The only exception to this rule
occurs when you move an object to a different folder on the same
volume. In this case, the original permissions are retained." So a
same-volume move leaves a stale label: the moved subtree keeps the
ACEs it inherited from its old parent until something rewrites it.
This is the label/ACL drift risk, documented by the vendor as default
behaviour.

## 7. The optional five, in one paragraph each

- **oso** (deprecated upstream): LIST is partial evaluation of the
  policy with the resource unbound, producing a filter plan that
  becomes SQL (`polar/polar.py:273-305`;
  `polar-core/src/data_filtering.rs:98-297`; `filter.rs:35-54`). Nothing
  on the row. Unsupported operators fail (`data_filtering.rs:230-297`).
- **casbin**: CHECK is a linear scan of every policy line through the
  matcher (`enforcer.go:821-838`). LIST returns the object *patterns*
  for the host to apply (`rbac_api.go:489-507, 666-680`). Nothing on
  the row; no index at check time.
- **seaweedfs**: per request, the bucket policy's statements are
  scanned (`policy_engine/engine.go:109-133`), then the identity's
  action strings (`auth_credentials.go:1903-1937`). `ListBuckets`
  walks every bucket and runs the full CHECK on each
  (`s3api_bucket_handlers.go:163-178`). S3 ACL grants and owner are
  stored as extended attributes on the entry
  (`s3_constants/extend_key.go:5-6`).
- **juicefs**: the inode row carries `AccessACLId` / `DefaultACLId`
  into a content-deduplicated `acl` table (`pkg/meta/sql.go:91-92,
  125-133`; `insertACL` at 5943-5964; `pkg/acl/cache.go:132`). CHECK
  is mode bits, then one ACL lookup by id (`pkg/meta/base.go:1417-1448`).
  Default ACL is copied at create (`sql.go:1890-1912`). `Readdir`
  checks the directory once and returns every child
  (`base.go:2273-2308`). The closest open-source copy of SharePoint's
  scope handle, in a filesystem over SQL.
- **minio** (AGPL, study only): the caller's named policies are
  merged into one statement list per request (`cmd/iam.go:2492-2536`;
  `cmd/iam-store.go:1588-1626`); `ListBuckets` iterates every bucket
  and evaluates one or two policies each
  (`cmd/bucket-handlers.go:305-393`). A 20 KiB cap per policy
  document (`cmd/bucket-policy-handlers.go:35, 76-77`). Nothing on the
  row.

## 8. Comparison

| system | label on the row? | per-caller compile? | write-time propagation? | LIST cost grows with |
|---|---|---|---|---|
| Oak | no | yes, per session: own principals' entries, eager under 250 | no: only the changed ACL's entries | result size × ancestor walk; capped at 100,000 reads |
| OpenSearch DLS | no | per request: caller's roles' queries OR'd | no | caller's role queries × segments |
| SpiceDB / OpenFGA | no | no (walk from subject per call; check cache by revision) | no | frontier out-degree per hop; **world size under a public parent**; capped at 1,000 / 3 s |
| Postgres RLS | only if the policy reads a column | no: one fixed expression, role substituted | no | rows × policy cost; column compare is index-served; sub-select is rows × list |
| Linux / FreeBSD | yes: mode, uid, gid, ACL on the inode | no | at create only | directory read is O(children) with zero child checks |
| SharePoint | yes: `ScopeId`; ACL per scope | no | yes: ACL per scope recalculated; Limited Access pushed up; child propagation capped at 500 | distinct scopes touched (50,000 cap, 5,000 advised, 1,000–2,000 effective) |
| NTFS | yes: full DACL copy; `$Secure` id | no | yes: whole subtree rewritten by user-mode walk (~2,000 objects/s measured) | directory read is O(children) |
| juicefs | yes: ACL id into shared table | no | at create only | directory read is O(children) |
| vfs today | no (`owner_id` only, `rows.py:409`) | yes: arms + holes + owner arms, per `(subjects, revision)` (`rights.py:144-184`, cache 256) | no | caller's grants **plus every private sub-posture in the mount** (`grants.py:309-324`) |

## 9. The private-homes case: what 100,000 private homes under an open root cost one owner

"Reader R owns `/home/r`. The root is open. Each of 100,000 homes is
private." Per system:

- **Oak.** R's session reads its own principal node and `everyone`'s.
  R has one path; `everyone` has 100,001 (the root allow plus a deny
  on each home, which is how Oak expresses a private home under an
  open root). `everyone` is over the 10-path eager limit, so it drops
  to lazy per-path lookup with a 1,000-path miss cache
  (`CacheStrategyImpl.java:57-73`; `PrincipalPermissionEntries.java:37`).
  Each row checked costs one hashed probe per ancestor level per
  principal set, with a store read for each uncached `rep:policy`
  node. A query over `/home` yields 100,000 rows, filters each, and
  sits exactly at the 100,000 `limitReads` cap. **Cost: proportional
  to the rows returned; the compile grows with `everyone`'s paths
  until the lazy mode caps it.** Oak does not scale the compile with
  the home count, but it does scale the per-row check with it.
- **OpenSearch.** Two clauses for R (or one dynamic rule). Zero per
  user. The query's cost is the two clauses per segment.
- **SpiceDB / OpenFGA.** R's direct leg is R's rows plus wildcard rows.
  The `parent->viewer` leg from `folder:root` fans out over every
  child of root. Without the cap it enumerates 100,000 homes and
  Check-shears 99,999. With the cap it stops at 1,000 results or 3 s.
  **Not proportional to R; proportional to the world; bounded by
  refusing to finish.**
- **Postgres.** With the label: `public OR owner = current_user` is one
  BitmapOr. With the hole predicate: a correlated SubPlan per row,
  rows × homes.
- **Unix.** Three checks on the walk and 100,000 dirents with no
  checks. Each home's privacy is its own mode bits.
- **SharePoint.** 100,000 scopes in one library: over the 50,000 cap,
  twenty times the advised 5,000, and past the 100,000-item point
  where inheritance can no longer be broken at all. The product's
  answer is "do not build this shape in one list."
- **NTFS.** Each home has an explicit DACL; `dir C:\home` lists
  100,000 entries with no per-child check. A posture change on the
  root rewrites 100,000 DACLs at about 2,000/s: 50 s.
- **vfs today.** `_everyone_arms` gives R one root arm with 100,000
  holes (`grants.py:309-324`). `pieces()` subtracts them in O(H²)
  (`_subtract` at `grants.py:360-371`; measured 17 s at 10,000). The
  Oracle and generic fan put every hole in one clause
  (`_units` at `rights.py:727-742`; finding 4 fails at ~1,000). The
  `RightsCache` is 256 entries keyed by `(subjects, revision)` and
  every posture write bumps the revision for everyone
  (`rights.py:78, 118-134`). **Not proportional to R; proportional to
  the number of other principals; and recomputed for every caller on
  every grant write.**

## 10. Principles distilled

Each principle names the evidence and whether vfs follows it today.

1. **A caller's compile reads only the caller's own principals.** Oak
   keys the store by principal and reads only the session's nodes
   (`PermissionCacheBuilder.java:51-52`). OpenSearch iterates
   `getMappedRoles()` (`AbstractRuleBasedPrivileges.java:542-587`).
   SpiceDB filters tuples by subject (`lookupresources3.go:796-806`).
   Postgres substitutes `current_user`. **vfs: not followed.**
   `resolve_authority` reads rows for the caller's ids *and* `*`
   (`rights.py:144-184`), which is right; but `_everyone_arms` then
   compiles every lower `*` row in the mount into the caller's root
   arm (`grants.py:309-324`). The `*` rows that *narrow* are other
   principals' privacy, not this caller's grants.

2. **A deny carved out of a broad allow is the one shape per-caller
   compile cannot absorb; the fix is a row fact, not a bigger
   compile.** Zanzibar has no deny and derives ownership from the
   object id (§4.5). Unix has no deny; privacy is the row's mode.
   Postgres makes `public OR owner = me` index-served only because
   `public` is a column. Oak, which does have deny, degrades to lazy
   per-path probes exactly in this case. **vfs: not followed.** Holes
   are a deny-by-subtraction compiled per caller.

3. **A row label should be a position fact, and small.** SharePoint's
   `ScopeId` is a handle; NTFS's `$Secure` id is a handle; juicefs's
   `AccessACLId` is a handle. The expensive labels in the study are the
   ones that hold principals (SharePoint's Limited Access push-up, NTFS's
   full DACL copy). **vfs: partly followed.** `owner_id` is a position
   fact on the row (`rows.py:409`) and the owner floor already uses it
   as a column compare (`_units` at `rights.py:735-741`). No posture
   fact is on the row.

4. **Write-time propagation must be a bounded range write, and the
   product must say what it bounds.** NTFS walks the subtree
   synchronously; SharePoint caps propagation at 500 uniquely scoped
   children and refuses to break inheritance past 100,000 items; Unix
   and juicefs refuse to propagate at all (create-time copy only).
   **vfs: no propagation exists today**, so nothing to judge; but vfs's
   own rule that no statement grows unboundedly with batch size
   (CLAUDE.md) applies to any relabel: it must be `UPDATE … WHERE path
   IN range`, chunked, under the revision lock.

5. **LIST is answered by an index seek on a row fact or a sorted range,
   never by testing each row against a list.** Postgres materialises a
   non-hashable list and tests every row (`subselect.c:538-553`); that
   is the shape ADR 072 replaced with the range join. Oak post-filters
   but memoises the ancestor walk. OpenSearch pushes the role queries
   into the Lucene query. **vfs: followed for arms** (ADR 072's range
   join, `Visibility.entries` at `rights.py:269-278`); **not followed
   for holes** on the Oracle/generic fan and the vector leg (`_units`).

6. **Caps are declared where the walk is unbounded, and the cap is on
   the answer, not on the world.** SpiceDB 1,000 results and a cursor;
   OpenFGA 1,000 results and 3 s; Oak 100,000 reads. These are
   result-side budgets. **vfs: partly followed.** The overlay and clause
   budgets are result-side; but finding 4's failure is a *statement*
   growing with the world, which CLAUDE.md forbids as a designed cap.

7. **A per-caller compile is invalidated per caller, not per world.**
   Oak discards on the session's own refresh; OpenFGA invalidates by
   `(object, relation)` and `(user, objectType)` keys after a changelog
   read (`cache_controller.go:333-345`); SpiceDB keys by revision and
   never hits old keys. **vfs: not followed.** One `grant_revision`
   bumps every cached resolution (`rights.py:118-134`), so a posture
   write by one user recompiles 100,000 users' rights on their next
   call.

8. **Public listings do not check children.** Unix `readdir`, juicefs
   `Readdir`, NTFS directory enumeration. vfs deliberately differs
   (hidden rows are absent, ADR 065). This is a vfs choice, not a flaw,
   but it means vfs must answer LIST with a per-row decision that Unix
   never makes. The row label is what makes that decision one compare.

## 11. Risks of the row-label approach, and how each system mitigates them

- **Scope explosion.** Many distinct labels make every query consult
  many scopes (SharePoint's 1,000–2,000 effective). *Mitigation:*
  keep the label a position fact with few distinct values. A posture
  handle has as many distinct values as there are posture rows, and
  the query compares a row's handle against the caller's small set of
  admitted handles — or, better, compares a row's *level* against a
  constant. SharePoint's explosion comes from principals in the
  scope; a level has three values.
- **Relabel storms.** A posture change high in the tree rewrites every
  row beneath (NTFS at ~2,000/s; SharePoint caps at 500 children and
  refuses past 100,000 items). *Mitigation:* vfs already serialises
  grant writes under the revision lock and chunks every statement.
  The storm is bounded by the subtree size, which is the honest cost;
  the risk is holding the lock for the duration. Oak and Unix avoid
  the storm entirely by never propagating, at the price of a per-row
  ancestor walk on read.
- **Label/ACL drift.** NTFS's same-volume move keeps stale inherited
  ACEs (KB 310316). Azure Search's SharePoint indexer serves "stale
  ACL data" until resync (sibling DLS memo §4.1). *Mitigation:* vfs
  has one writer path per row and a revision counter; the label must
  be written in the same transaction as the posture row and the move,
  and a parity test must assert `label == nearest posture row` over a
  random world, the way the range-join exactness test does.
- **Moves across labelled subtrees.** A move from a private home to an
  open folder must relabel the moved subtree (NTFS: explicitly does
  not by default; Unix: nothing to relabel, the inode keeps its
  mode). *Mitigation:* the move verb already rewrites `path` for every
  row in the subtree (a range update); the label is one more column in
  the same statement. The cost is already paid.
- **Two sources of truth.** The `*` rows and the row labels say the
  same thing twice. *Mitigation:* the `*` rows stay the source;
  labels are a derived, rebuildable column, like a search index. A
  rebuild statement (`UPDATE entries SET label = nearest posture`)
  must exist and be tested.
- **Group and principal churn.** Not a risk here: labels carry no
  principals, so membership changes touch no row. That is the lesson
  of SharePoint's Limited Access push-up and of every DLS vendor's
  "store a group token, not the members" (sibling DLS memo §4.2).

## 12. What the executed study should measure

The spikes running in parallel on SQLite and Postgres should answer
these, in this order:

1. **Relabel cost.** `UPDATE entries SET posture_level = :l WHERE path
   > :lo AND path < :hi` for a subtree of 1k, 100k and 1M rows, under
   the revision lock, on both engines. Wall time, lock hold time, and
   whether a concurrent reader stalls. Compare with NTFS's ~2,000/s.
2. **The everyone predicate as a column compare.** `glean` and `tree`
   for a partial caller with 100,000 private homes under an open root,
   as `posture_level >= :need OR <range join on explicit arms> OR
   owner_id = :me`. Does the planner use an index on `posture_level`
   (low cardinality, three values) or does it scan? Is a partial index
   `WHERE posture_level >= 1` better? On Postgres, is it a BitmapOr?
3. **Label or handle.** The same queries with a `posture_id` handle
   and a join to the posture row, versus a stored level. Which keeps a
   posture write cheaper (handle: no relabel when the level changes
   but the row stays; level: relabel on every level change)?
4. **The compile curve.** `resolve()` time and `pieces()` time for a
   caller with 50 explicit grants, as the number of *other* users'
   private homes goes 0, 1k, 10k, 100k. Today's curve (quadratic) and
   the post-change curve (should be flat).
5. **The meet.** A two-member authority over a group with 10,000
   grants, before and after a sorted-merge meet (finding 7).
6. **Invalidation.** How many `RightsCache` entries one posture write
   discards today, and how many after keying by `(subjects,
   principals' own revision)` — or whether the label removes the need
   to cache the posture part at all.
7. **Drift test.** A random world of posture writes, moves and
   deletes; after each, assert for every row that the stored label
   equals the nearest covering `*` row. This is the parity test the
   label needs before it ships.

## 13. Open choices the prior art leaves to vfs

- [NEEDS CLARIFICATION: **level or handle?** SharePoint, NTFS and
  juicefs store a handle to a shared record; Postgres's cheap case is
  a plain column. A stored level makes the everyone predicate one
  compare and needs a relabel on every level change; a handle makes
  the predicate a join and relabels only when the nearest posture row
  changes. The spike (§12 item 3) should decide.]
- [NEEDS CLARIFICATION: **does the owner floor also move onto the
  row's compile, or stay a separate `UNION` branch?** Postgres
  BitmapOr's the two; ADR 072 rule 3 keeps owner arms separate because
  mixing them blocks the range seeks. The label does not change that
  reasoning, but the spike should confirm on Postgres.]
- [NEEDS CLARIFICATION: **what does the trash do to the label?** Review
  finding 1 (deleted hidden rows become world-readable under the trash
  path) is a label/position question: does a row keep its home's
  posture label when reparented under `/.vfs/trash`, or take the
  trash's? NTFS's "keep on same-volume move" is the vendor default and
  is also the bug.]
- [NEEDS CLARIFICATION: **relabel under the revision lock, or
  asynchronously with a stale window?** Every search vendor accepts a
  stale window; SharePoint refuses propagation past 500 children;
  NTFS blocks the caller. vfs's write contract (10k-row batches fail
  whole at the gate) suggests synchronous and chunked, but a 1M-row
  posture change under one lock needs a measured answer.]
- [NEEDS CLARIFICATION: **should per-caller `Rights` keep any
  everyone arm at all once the label exists?** If the everyone part is
  entirely a column compare, `_everyone_arms` goes, holes go, and
  `Rights` holds only explicit arms and owner arms. The `whole` fast
  path for the open-root/no-grants caller then becomes "every row's
  label admits me", which is still a scan unless the planner proves
  the predicate trivially true.]

## What this means for vfs

The hypothesis survives the prior art, with one sharpening. Every
mature system keeps a caller's compile proportional to the caller's
own grants; vfs alone folds other users' privacy into each caller's
rights, and that is the bug. The only systems that make "public or
mine" a single cheap compare are the ones that put a fact on the row:
Unix's mode bits, Postgres's `public` column, SharePoint's `ScopeId`.
Those systems pay for it with a subtree write when the fact changes,
and the serious ones bound that write and document the bound. vfs
should do the same: a small position fact on the row for the everyone
level (level or handle, to be measured), written in the same
transaction as the posture row and the move, rebuilt by one chunked
range update, and tested for drift; explicit grants stay path ranges
joined to the path index (ADR 072); owner stays a column compare. The
word "hole" leaves the compiler.

One line: compile only what is yours; put what is everyone's on the
row; bound the relabel and test it for drift.
