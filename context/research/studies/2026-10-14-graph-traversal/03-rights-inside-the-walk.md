# R3 — Enforcing the caller's rights inside a graph traversal

Researcher R3, 2026-10-14. Brief: `scratchpad/research/BRIEF.md`.
Script: `scratchpad/experiments/r3_visibility_shape.py`; full output: `scratchpad/experiments/r3_visibility_shape.out`.

Evidence labels: **EXECUTED** (I ran it), **READ** (I read the code or doc and cite it), **INFERRED** (my reasoning). Anything else is marked `[NOT VERIFIED: why]`.

## Summary

vfs already owns the predicate the walk needs. `Rights.admits` is the law in Python, and the storage half compiles the same rights into one of two SQL pushdowns: the **three-seek `UNION ALL` join** (one statement for any number of grants, joined on `entry_id`) where the dialect declares a range source, or a **literal `OR` of path terms** split into clauses on the generic floor. I placed both forms inside a `WITH RECURSIVE` walk over `vfs_edges` on SQLite and ran it: the predicate on the recursive member's target row cuts the walk at a hidden node, so a visible node behind a hidden one is never reached — while a walk that filters afterwards in Python **leaks it** (the post-filter variant reached `/priv/deep/e.md` through hidden `/priv/c.md`). That is the executed proof of Clay's rule: the rights must ride every hop, not run after the walk. Across engines the placement must differ in one place only: **SQL Server forbids subqueries in a recursive member**, so there the visible set has to be a prior named CTE or a temp table joined on `entry_id`, never an inline derived table; every other engine's documented restrictions concern the self-reference, not other tables. The clause fan is ruled out for recursion on every engine: a predicate split across statements breaks reachability, so the walk needs the whole predicate in one statement, which only the three-seek set (or a single clause) gives. None of the four authorization systems studied pushes a traversal into SQL recursion: SpiceDB and OpenFGA walk app-side, one flat fan-out query per hop with a depth cap (50 / 25); Oak walks a secured tree node by node and post-filters query rows; Oso compiles a policy to a flat WHERE. Postgres is the one native precedent for "the predicate rides every iteration": its rewriter attaches row-security quals to every relation RTE, recursing into every CTE body, so RLS applies inside a recursive term.

## Findings table

| # | Finding | Evidence | Status |
|---|---|---|---|
| 1 | A post-walk filter leaks nodes reached through a hidden node; the predicate inside the recursive member cuts the walk | `r3_visibility_shape.out` §(c): unguarded reaches `c,e,b`; post-filter reaches `e`; all three in-walk placements reach nothing | EXECUTED |
| 2 | The three-seek join (MATERIALIZED CTE), the inline UNION ALL derived table and the literal clauses all run inside a SQLite recursive member and agree | same, "placements agree: True"; plan: `MATERIALIZE visible` once, then `SEARCH visible USING AUTOMATIC COVERING INDEX` per step | EXECUTED |
| 3 | SQL Server disallows subqueries in a recursive member; INNER JOIN and references to previously defined CTEs are allowed; CTEs are not materialised (re-executed per reference); MAXRECURSION default 100 | learn.microsoft.com WITH page, "Guidelines for recursive common table expressions" | READ (web) |
| 4 | SQLite: the recursive table appears once in the FROM of the recursive-select and "not anywhere else … including subqueries"; no aggregates/window; other subqueries allowed | sqlite.org/lang_with.html | READ (web) + EXECUTED |
| 5 | Postgres: the only restrictions are on the self-reference (not in a subquery, outer join, INTERSECT/EXCEPT, not twice); a non-recursive CTE referenced once is inlined unless `MATERIALIZED` | `postgres:src/backend/parser/parse_cte.c:46-54,1074`; postgresql.org queries-with | READ |
| 6 | Oracle: recursive member cannot hold DISTINCT/GROUP BY/aggregates, subqueries **that refer to query_name**, or outer joins with query_name on the right; without a CYCLE clause a cycle is an error | docs.oracle.com 23 SELECT, recursive subquery factoring | READ (web) `[NOT VERIFIED: no Oracle in session]` |
| 7 | MariaDB: `max_recursive_iterations` default 1000; standard restrictions enforced as error 4008; doc page lists none explicitly | mariadb.com server-system-variables; MDEV-12360, MDEV-15894 | READ (web) `[NOT VERIFIED: JSON_TABLE or derived table inside the recursive part untested]` |
| 8 | Postgres RLS quals are attached per relation RTE and the rewriter recurses into every CTE body, so the policy rides every iteration of a recursive CTE | `postgres:src/backend/rewrite/rewriteHandler.c:2256-2270,2086-2088,2202-2208`; `rowsecurity.c:17-21`; `ddl.sgml:2952-2960` | READ `[NOT VERIFIED: no regress test pairs RLS with RECURSIVE — grep of rowsecurity.sql found none]` |
| 9 | SpiceDB: app-side loop; depth from `DepthRemaining` (default 50); one `QueryRelationships` per hop over a chunk of ≤100 resource ids; no visited set (depth bounds cycles); no `WITH RECURSIVE` in any datastore | `spicedb:internal/dispatch/dispatch.go:125-137`, `pkg/cmd/serve.go:164-170`, `internal/graph/check.go:393-420,483-512`, `lookupresources2.go:605`; grep | READ |
| 10 | OpenFGA: app-side; `DefaultResolveNodeLimit=25`, breadth 10; cycle via `VisitedPaths` keyed by tuple; reverse expand reads one `ReadStartingWithUser` per hop with a user list and optional `ObjectIDs` set; no recursive SQL | `openfga:pkg/server/config/config.go:25-26`, `internal/graph/check.go:383,415-426,474-487`, `pkg/server/commands/reverseexpand/reverse_expand.go:136,328-336,367,612-620`, `pkg/storage/storage.go:289-303` | READ |
| 11 | Oak: permission derived top-down per node (`getTreePermission(tree, parentPermission)`); a node is `exists()` iff `canRead()`; `getChildNode` continues through an unreadable node (traverse without list); `getChildNodeEntries` of an unreadable node is empty; query rows are post-filtered per row through the secured tree | `jackrabbit-oak:...PermissionProvider.java:80-90`, `SecureNodeState.java:60-61,100-121,141-153`, `query/ast/SelectorImpl.java:614-618,946-948` | READ |
| 12 | Oso: policy partially evaluated, residual becomes `Filter{root, relations (joins), conditions (DNF)}` → one SQLAlchemy WHERE; no traversal notion | `oso:polar-core/src/filter.rs:23-39`, `languages/python/sqlalchemy-oso/sqlalchemy_oso/auth.py:45-90` | READ |
| 13 | mirage: `hide` answers ENOENT before any operation and outranks every other answer; no graph verb | `mirage:python/mirage/policy/types.py:100-112`, `profile.py:290,518-526`, `constants.py:62` | READ |
| 14 | vfs today: `tree` filters in SQL (`narrow`) **and** in Python (`admits`), then derives the road from visible rows' ancestors; `ls` filters children in Python and asks `road()` for hidden child directories | `src/vfs/storage/backends/database/reads.py:224-276,715-725,795-848` | READ + EXECUTED (a) |
| 15 | Holes ride both SQL forms and `admits` | `ranges.py:85-120,122-145`, `rights.py:1012-1031`, `grants.py:468-510` | READ `[NOT VERIFIED by execution here; pinned by tests/storage/database/test_rights.py:386,411]` |
| 16 | A road-only directory is not an admitted row; vfs already decided edges/versions/locate on it answer not-found | ADR 070 rules 1–2; memo 2026-09-28 §5.2 table, §6 rule | READ |

## Part A — prior art

Licences (all read-only clones under `~/Git/Repos`): spicedb Apache-2.0 (`LICENSE`, commit a1dad93 2026-10-13); openfga Apache-2.0 (`LICENSE`, 526995e 2026-10-07); jackrabbit-oak Apache-2.0 (`LICENSE.txt`, 9c7d6d0 2026-10-12); oso Apache-2.0 (`LICENSE`, last commit 7292df0 **2025-02-26** — the clone is at its upstream head; the project is no longer moving); mirage Apache-2.0 (`LICENSE`, 314f004 2026-10-13); postgres PostgreSQL licence (b128e75e 2026-10-14).

### SpiceDB — READ

- **Depth.** Every dispatchable request carries `ResolverMeta.DepthRemaining`; `CheckDepth` returns `ErrMaxDepth` when it is 0 (`internal/dispatch/dispatch.go:125-137`). Each hop dispatches with `decrementDepth(crc.parentReq.Metadata)` (`internal/graph/check.go:499`); LookupResources passes `MaximumDepth: DepthRemaining - 1` into the bulk check it runs per hop (`internal/graph/lookupresources2.go:605`). Default `--dispatch-max-depth` is 50 (`pkg/cmd/serve.go:165`). Response metadata sums `DispatchCount`, `CachedDispatchCount`, and takes the max `DepthRequired` (`dispatch.go:142-146`).
- **Cycles.** No visited set in `check.go`, `lookupresources2.go` or `lookupsubjects.go` (grep for `visited|cycle`: 0 hits in each). The depth budget is the only bound on a cyclic schema.
- **Batching per hop.** One datastore query per hop per chunk, never one per node: the direct-subject step builds one `RelationshipsFilter` with `OptionalResourceIds: crc.filteredResourceIDs` (the whole chunk) and `OptionalSubjectsSelectors` (`check.go:393-420`); the results are regrouped and re-dispatched in chunks of `dispatchChunkSize` (`check.go:483-512`, `checkdispatchset.go:92-115`), default `--dispatch-chunk-size` 100 = "maximum number of object IDs in a dispatched request" (`serve.go:164`); per-request goroutine limit `--dispatch-concurrency-limit` 50 (`serve.go:170`).
- **SQL recursion.** None. `grep -rl RECURSIVE internal/datastore --include='*.go'` returns nothing. The traversal is always an application loop of flat relationship reads.

### OpenFGA — READ

- **Depth cap.** `DefaultResolveNodeLimit = 25`, `DefaultResolveNodeBreadthLimit = 10` (`pkg/server/config/config.go:25-26`). The checker increments `Depth` per dispatch (`internal/graph/check.go:383`) and returns `ErrResolutionDepthExceeded` at the limit (`:415-416`). ListObjects' reverse expansion keeps its own counter in context and refuses at `resolveNodeLimit` (`pkg/server/commands/reverseexpand/reverse_expand.go:328-336`).
- **Cycles.** `hasCycle` keys `req.VisitedPaths` by the tuple string and answers `Allowed:false, CycleDetected:true` (`check.go:420-426, 474-487`); unions/intersections propagate `CycleDetected` (`:202-203, 274-277, 341-342`). Reverse expand dedups with `visitedUsersetsMap.LoadOrStore` (`reverse_expand.go:136, 367`).
- **Batching.** A hop is one `ReadStartingWithUser` with a `UserFilter` list (`reverse_expand.go:612-620`); the filter type carries an optional sorted `ObjectIDs` set the datastore intersects server-side (`pkg/storage/storage.go:289-303`), the fan-out-in-one-query shape. Breadth is a worker pool of `resolveNodeBreadthLimit` (`reverse_expand.go:632`).
- **SQL recursion.** None (`grep -rl RECURSIVE internal pkg --include='*.go'`: nothing).

### Jackrabbit Oak — READ

- **Top-down permission per node.** `PermissionProvider.getTreePermission(tree, parentPermission)` builds a node's permission from its parent's (`oak-security-spi/.../PermissionProvider.java:80-90`); `TreePermission.getChildPermission(childName, childState)` descends (`TreePermission.java:42`). So access is evaluated at **every** node on the way down.
- **Does a denied intermediate hide its subtree?** Partly. `SecureNodeState.exists()` is `treePermission.canRead()` (`oak-core/.../SecureNodeState.java:60-61`). `getChildNode(name)` wraps the child in its own permission regardless of whether *this* node is readable (`:113-121`), so a direct path lookup continues **through** an unreadable node — the Unix `0711` shape (traverse without list). `getChildNodeEntries()` returns the raw entries under `canReadAll`, a filtered iterable under `canRead`, and `emptyList()` otherwise (`:141-153`), so an unreadable node **lists** nothing. Enumeration is cut; addressed access is not.
- **Query engine.** Rows come from the index unsecured; `SelectorImpl.evaluateTypeMatch` resolves each row's path through `query.getTree(path)` — the session's secured tree — and drops the row when `!ct.exists()` (`oak-core/.../query/ast/SelectorImpl.java:614-618, 946-948`). That is per-row post-filtering, not index-level. `FilterImpl` and `ExecutionContext` have no permission hooks (grep: none).

### Oso — READ

Data filtering partially evaluates the policy with `resource` unbound (`authorize_model`: `query_rule("allow", actor, action, Variable("resource")` under a `TypeConstraint`, `sqlalchemy_oso/auth.py:45-90`), and the core turns the partial results into `Filter{root, relations, conditions}` — joins plus an OR-of-ANDs (`polar-core/src/filter.rs:23-39`) — which the SQLAlchemy adapter renders as one WHERE on the model. It is a flat per-table predicate; there is no traversal, so nothing here says how a filter would ride a recursive query. It is the same "compile rights to a pushdown" shape ADR 067 chose.

### mirage — READ

`Hide` "answer[s] as though the path did not exist", "outranks every other answer", "never rendered as a refusal", raising ENOENT at the entry point (`python/mirage/policy/types.py:100-112`); a profile's `hide` is "what the profile makes nonexistent" (`policy/profile.py:290`), and a mount a profile must not touch "reads as nonexistent rather than as a permission error naming something the profile cannot see" (`:518-526`). The hide arm is answered before any operation (`policy/constants.py:62`). mirage has no graph verb; its hide is a path projection in front of every command. Same family as ADR 065. `[NOT VERIFIED: whether mirage's find/glob walk skips descendants of a hidden directory or only the matched names — I did not trace glob_walk.]`

### Postgres RLS and recursive CTEs — READ

- The policy expression "will be evaluated for each row prior to any conditions or functions coming from the user's query" (`doc/src/sgml/ddl.sgml:2952-2960`); `queries.sgml` says nothing about RLS (grep: none).
- Mechanism: `rowsecurity.c` returns the quals "for each RTE in the query" (`src/backend/rewrite/rowsecurity.c:17-21`). `fireRIRrules` loops the range table and calls `get_row_security_policies` for every `RTE_RELATION` (`rewriteHandler.c:2256-2270`), recurses into `RTE_SUBQUERY` (`:2086-2088`), and then "Recurse into subqueries in WITH": `cte->ctequery = fireRIRrules(cte->ctequery, …)` for every CTE (`:2202-2208`). A recursive CTE's body is a `Query` whose range table holds the relation referenced by the recursive term, so the security qual is attached there and **runs on every iteration**. This is the native analogue of "the predicate rides every hop". No regression test combines RLS with `RECURSIVE` (`grep -i recursive src/test/regress/sql/rowsecurity.sql`: none) `[NOT VERIFIED by execution: no Postgres in this session]`.
- Parser rules for the recursive term (`src/backend/parser/parse_cte.c:46-54, 1074`): the self-reference "must not appear within a subquery", "within an outer join", "within INTERSECT/EXCEPT", in the non-recursive term, or more than once. Nothing restricts *other* subqueries, derived tables or `unnest` joins in the recursive term.

### Unix / Plan 9 heritage and what vfs already decided — READ

Memo `context/research/2026-09-28-traverse-visibility-unix-plan9.md` §5–6 and ADR 070:

- Traverse, list and read are three separate rights everywhere studied; the check comes before the lookup; reaching a deep path needs no right on its ancestors (ADR 070 Context).
- vfs chose (b′): a directory is **on the road** when a visible row lies beneath it; it shows as a **bare name** (path, kind) in `ls`, `glob`, `tree`, `stat`; listing it shows only visible and road children; every write beneath it is `permission_denied` decided before lookup; a hidden directory with nothing visible beneath stays absent (ADR 070 Decision 1–5).
- The memo's verb table (§5.2) and its rule for spec 058 (§6) say explicitly: "versions, edges, `locate` on `/projects` → **not-found: traverse is not read**" and "Its versions, edges and locate answer not-found". So for a road-only directory, vfs has already decided that edge-shaped verbs treat it as absent.
- Mirror for a graph walk (INFERRED, consistent with the above): a hidden intermediate **node** cuts the walk. A road-only directory is not an admitted node (see Part B Q4), and vfs's own rule says edges on it are not-found. Oak is the counter-precedent (addressed traversal continues through an unreadable node), but Oak's listing of that node is empty, and vfs's road already captures the useful half of that (an agent can walk down by name) in the listing verbs.

## Part B — vfs internals

### Q1. The SQL forms the visibility predicate takes today, and when each is used — READ + EXECUTED

Two compiled forms, one chooser, one authority.

**Form A: the three-seek `UNION ALL` join** — `visible_entries(entry, ranges, need, profile, scope)` (`ranges.py:85-120`), returned by `Visibility.entries(scope)` (`rights.py:411-422`) when `profile.range_source is not None` and the rights are neither `whole` nor `empty`. One `SELECT entry_id` branch per source:
1. the everyone leg: `everyone_level >= :need` through the `(everyone_level, path)` index, with `hole_free(...)` — true outright without holes, else `NOT EXISTS` over the unpacked hole pieces (`ranges.py:122-145`);
2. the caller's own pieces (`ranges.arms`): the exact paths as one bound list unpacked by the dialect's table function (`point_rows`, `ranges.py:276-294`) joined `path = value`, and the open ranges likewise (`open_rows`, `:297-315`) joined `lo < path < hi`, each with `everyone_level < :need` so branches stay disjoint;
3. the same for `holed_arms` with `everyone_level >= :need` (rows in a hole admitted by the pieces whatever the label);
4. per owner arm, the owner's pieces with `owner_id = :owner AND everyone_level < :need`; and `holed_owners` likewise.
The branches are `UNION ALL`-ed; the result is a derived table (`.subquery("visible")`) or, where the profile declares `range_fence`, a CTE with that prefix — SQLite's `MATERIALIZED` (`dialects.py:426-428`). Join keyword, index pin and hints are profile facts: `CROSS JOIN` (SQLite), plain `JOIN` (Postgres, Oracle), `INNER LOOP JOIN` (SQL Server), `STRAIGHT_JOIN … FORCE INDEX` (MariaDB), Oracle's `INDEX`/`CARDINALITY`/`NO_MERGE LEADING USE_NL` hints (`dialects.py:238-275`, `ranges.py:_range_select`). Consumers join it on `entry_id` (`Visibility.narrow`, `rights.py:424-434`). The statement text never changes with the caller's grants. EXECUTED: Part C (b1) prints the compiled statement for SQLite, Postgres (`unnest(ARRAY[...]) … COLLATE "C"`), SQL Server (`OPENJSON … WITH (lo nvarchar(max) …)` cast through the UTF-8 collation), MariaDB (`JSON_TABLE … CAST(... AS BINARY)`), Oracle (`JSON_TABLE` over the CLOB bind with the hints).

**Form B: the literal `OR` of path terms, split into clauses** — `visibility_clauses(entry, rights, profile, parameter_budget)` (`rights.py:340-366`), returned by `Visibility.clauses()`. `_units` (`rights.py:1012-1031`) builds the units: the everyone level alone (1 bind) — or, with holes, the everyone level AND each piece of the mount outside the holes; one unit per piece of the arms (a point spends 1 bind, an open range 2, `_piece_units` `:1034-1043`); and per owner arm, groups of at most `_OWNER_PIECES_PER_UNIT = 50` pieces under `owner_id = :owner`. Units are packed into clauses under `bind_cap = membership_budget/2` and `arm_budget(profile, parameter_budget, 1)`. Clauses are **disjunctive**: a caller runs the statement once per clause and merges. Used when the dialect has no range source (`GENERIC`), when `rights.empty` (the everyone term alone decides, one clause), and on the vector leg. EXECUTED: Part C (b2) shows bob's rights as one clause of 13 binds.

**Chooser:** `Visibility.narrow(stmt, scope)` (`rights.py:424-434`) — join to `entries()` where available, else one statement per clause, `[stmt]` when every row passes. Every read verb then still checks each fetched row with `Visibility.admits` → `Rights.admits(path, owner_id, everyone_level)` (`rights.py:398-399`, `grants.py:468-481`). `tree` does exactly this: `_visible_rows` runs `view.narrow` and keeps only rows `view.admits` (`reads.py:715-725`).

### Q2. Can each form sit inside the recursive member, per engine — EXECUTED on SQLite, READ elsewhere

Setting: the recursive member joins `walk` → `vfs_edges` (on `source_id = walk.entry_id AND edge_type = :t`) → `vfs_entries AS t` (on `t.entry_id = target_id AND t.deleted_at IS NULL`) and must admit `t` by the caller's rights.

**SQLite — EXECUTED.** All three placements run and agree (Part C §(c)):
- *Placement 1, materialised CTE*: `WITH RECURSIVE visible AS MATERIALIZED (…union…), walk(entry_id, depth) AS (anchor UNION ALL step JOIN visible ON visible.entry_id = t.entry_id)`. The plan computes `MATERIALIZE visible` once (every branch an index seek: `ix_vfs_entries_everyone_path`, `ix_vfs_entries_path`, `ix_vfs_entries_owner_id`), then each recursive step probes it with `BLOOM FILTER ON visible` + `SEARCH visible USING AUTOMATIC COVERING INDEX (entry_id=?)`. This is the shape to ship on SQLite.
- *Placement 2, inline derived table*: legal (SQLite forbids only the recursive table inside a subquery, lang_with.html) and correct, but the `ranges.py` docstring measured the unfenced union being pushed into every outer branch (3.9 s vs 35 ms); keep the fence.
- *Placement 3, literal clauses on `t`*: legal and correct when the rights fit one clause.

**Postgres — READ `[NOT VERIFIED on a live server]`.** The parser restricts only the self-reference (`parse_cte.c:46-54`); a derived table, an `unnest(...)` join or a prior CTE in the recursive term is allowed. A prior CTE referenced once is **inlined** by default (queries-with: folded "if the parent query references the WITH query just once"), so `visible` would be re-planned as a join inside each iteration; spell it `AS MATERIALIZED` to compute it once. `view.prepare()` already issues `SET LOCAL jit = off` for a partial caller (`dialects.py:456`). The RLS rewriter is the precedent that a per-relation predicate inside a recursive body is a normal thing for this engine (`rewriteHandler.c:2202-2208`).

**MariaDB — READ `[NOT VERIFIED]`.** The documented recursive-CTE page states no restriction list; violations surface as error 4008 (standard restrictions; MDEV-12360 shows a left join with the recursive reference on the left refused, MDEV-15894 aggregates in the anchor). `max_recursive_iterations` defaults to 1000 (server-system-variables page) — a walk's depth must stay under it or raise the session variable. The `ranges.py` docstring rules out `entry_id IN (union)` here (seconds); the join form is what to use. Whether `JSON_TABLE` or an inline derived table is accepted inside the recursive part is untested; the safe shape is a prior CTE (MariaDB materialises CTEs referenced from a recursive part into a temporary table) or a temp table, joined on `entry_id`.

**SQL Server — READ.** "The following items aren't allowed in the CTE_query_definition of a recursive member: SELECT DISTINCT, GROUP BY, PIVOT, HAVING, Scalar aggregation, TOP, LEFT/RIGHT/OUTER JOIN (INNER JOIN is allowed), **Subqueries**, a hint applied to a recursive reference." So **placement 2 is impossible** here: the inline `UNION ALL` derived table is a subquery. Two legal placements remain: (a) "A CTE can reference itself and previously defined CTEs in the same WITH clause" — a prior `visible` CTE joined with `INNER JOIN`; but "Query results from common table expressions aren't materialized. Each outer reference … requires the defined query to be re-executed", and the page recommends "a temporary object" for repeated references — inside a recursive member the union would be spooled or re-run per iteration; (b) **materialise the visible set into a `#temp` table (or table variable) with a primary key on `entry_id`** in the same transaction and `INNER JOIN` it in the recursive member — the documented remedy. `MAXRECURSION` default 100, max 32767, `0` unlimited: the walk's `depth` argument must either stay ≤ 100 or set `OPTION (MAXRECURSION n)`. `OPENJSON` is a rowset function, not a subquery, so the literal clauses (placement 3) and a TVF join should be legal `[NOT VERIFIED: TVF join inside a recursive member untested]`. `INNER LOOP JOIN` (the profile's range join) is an inner join, allowed.

**Oracle — READ `[NOT VERIFIED]`.** The recursive member may not contain DISTINCT/GROUP BY/model/aggregates, "Subqueries that refer to query_name", or "Outer joins that refer to query_name as the right table". Other subqueries, `JSON_TABLE` joins and references to other named subqueries in the same WITH are not forbidden by the listed rules. Spell `visible` as a prior named subquery with `/*+ MATERIALIZE */` (the derived hint `NO_MERGE({visible})` the profile already carries does the same for a derived table). **Cycles:** "If you omit the CYCLE clause, then the recursive WITH clause returns an error if cycles are discovered" — authored edges can cycle, so the Oracle walk needs `CYCLE entry_id SET … TO … DEFAULT …` (R-traversal's topic, flagged because a hidden node is the one cycle breaker rights provide for free: a cycle through a hidden node never forms).

**The two alternatives, weighed.**
- *Materialise once, join by `entry_id`* (prior CTE with a fence, or temp table): one statement for any rights; the visible set is computed once per statement (or once per transaction with a temp table) and probed per hop by key; works on every engine including SQL Server; it is the `ranges.py` docstring's own instruction ("Statements that read chunk-side tables join the result as a derived table on entry_id"). What the docstring rules out is the **`entry_id IN (SELECT … FROM union)`** spelling — it "plans badly on some engines (seconds on MariaDB), so it is not offered". Join, never `IN`.
- *Filter the frontier per hop in the app* (the SpiceDB/OpenFGA shape): no recursion at all; per hop, one flat statement per chunk of the frontier — `membership(entry_id, chunk)` on `vfs_edges`, joined to `vfs_entries` and to the visible set — merged in Python with a visited set. Correct on every engine with no recursion restrictions, and the natural fallback for the generic floor (no range source, several clauses). Cost: `depth × ceil(frontier / membership_budget)` statements; Oracle's 1,000-element cap means a 10k frontier is 10 statements per hop. SpiceDB caps a hop at 100 ids, OpenFGA bounds breadth at 10 workers — both pay this shape in production.

**A rule that falls out (INFERRED, important):** the clause fan cannot serve a walk. Clauses are disjunctive statements merged afterwards; a path whose intermediate node is admitted by clause 1 and whose next node is admitted by clause 2 is found by neither statement. For recursion the predicate must be **whole in one statement** — the three-seek set (one statement for any rights) or a single clause. On the generic floor with more than one clause, the walk must go app-side per hop (where merging per hop is sound), or the predicate must be materialised into a temp table from the clauses (one `INSERT … SELECT entry_id … WHERE clause_i` per clause) and joined.

### Q3. Does a Python post-check still make sense, and what does it cost — EXECUTED + INFERRED

Yes, but as the belt, never the enforcement. The executed run shows why: filtering after the walk reached `/priv/deep/e.md` through hidden `/priv/c.md` (`r3_visibility_shape.out` §(c), "post-filter only"). A post-check can drop a hidden node from the output; it cannot un-walk the hop that went through it. So the SQL predicate inside the recursion is what enforces Clay's rule, and `Rights.admits` on every emitted row is defence in depth — exactly the posture `tree` holds today (`_visible_rows`, `reads.py:720-723`), and what the parity test pins: the join "admits exactly what the rights admit" (`tests/storage/database/test_rights.py:184-207`). For the cut to hold, the SQL form must be **exact**, not a superset; the parity tests say it is, so the post-check should never drop a row — make it a loud invariant (a warning or a counter), not a silent filter.

Cost at 10k seeds, counted in operations (never time): the walk must project `RIGHTS_FIELDS` (`path`, `owner_id`, `everyone_level`) for every emitted node — wider rows; then one `Rights.admits` per row: at most one `contains` bisect over the holes, one over the spans, one over the owner's range set (`grants.py:468-481`, `contains` `:331`), each `O(log pieces)` with pieces bounded by the caller's grants, not the batch. For a result of R rows that is 3R bisects — linear in the output, independent of seed count. The seeds themselves are judged by the anchor (seed ∩ visible), so a hidden seed yields no row and no hop.

### Q4. The road case — READ + EXECUTED

What `tree` does today (EXECUTED, Part C (a)): bob holds `read` on `/priv/deep` only; `tree("/")` returns `/priv` as a **bare** observation (no version, no size — `road_observation`), then `/priv/deep`, `/priv/deep/d.md`, `/priv/deep/e.md` as visible rows. Mechanism (`reads.py:224-276`): the subtree is read under the view (`_visible_rows`), and `bare` is the set of each visible row's ancestors below the tree root that are not themselves visible (`_ancestors_below`) — the road is **derived from visible rows' paths after the fetch**, not admitted by the predicate. `ls` (`_children_by_parent`, `reads.py:795-848`) asks `view.road(session, hidden)` (`rights.py:436-460`: existing arm roots' ancestors, owner-floor rows beneath a candidate, everyone-level rows beneath) and lists a hidden child directory as a bare name only when it is on the road. `Visibility.admits` is **false** for a road directory: `/priv` has `everyone_level 0`, is outside bob's spans, and bob does not own it. The three-seek set excludes it (Part C (b1): the join admits exactly `/priv/deep`, `/priv/deep/d.md`, `/priv/deep/e.md`).

So in a graph walk over `fs` edges with the predicate on every hop, `/priv` cuts the walk: `descendants(/)` would never reach `/priv/deep`. Three ways to handle it:
1. **Road is a listing concept; the walk treats a road directory as absent.** This is what vfs already decided for edge-shaped verbs: "versions, edges, `locate` on `/projects` → not-found: traverse is not read" (memo §5.2, §6; ADR 070 rule 2 lists only `ls`, `glob`, `tree`, `stat`). A seed at a road directory answers not-found; a hidden directory between two visible nodes cuts an fs walk. Consequence to state honestly: `graph(descendants over fs)` and `tree` differ exactly at a road directory.
2. **Make the road a traversable-but-bare node in the walk.** The predicate on an intermediate fs hop becomes "admitted OR a visible row lies beneath"; the "beneath" test is a correlated `EXISTS` over the visible set by path range — a subquery (illegal in a SQL Server recursive member) and a per-hop range probe elsewhere. Possible, but it is a second, more expensive predicate and it only matters for `fs` edges.
3. **Route fs-typed hierarchy walks to the subtree scan.** For `edge_type = fs`, "descendants of p to depth d" is `tree(p, max_depth=d)` by construction (the mirror is one `fs` edge per non-root entry, `edges.py` docstring), and `tree` already computes the road. Ancestors over fs is the ancestor chain of a path (`descent.ancestor_chain`), which the descent ladder already judges with `seen_kinds` (road directories read as directories, `rights.py:462-476`).

Recommendation for the graph verb: **(1) for the walk, (3) for fs-only walks.** A hidden node is absent on every edge type inside the recursive walk, matching ADR 065 rule 1 and the memo's not-found row for edges on a road directory; and the graph verb documents that hierarchy-with-road is `tree`'s job. If Clay wants `descendants over fs` to equal `tree`, dispatch that method to the subtree scan rather than teaching the recursion about the road.

### Q5. Holes ride along — READ `[NOT VERIFIED by execution here]`

Yes, in all three places, as one predicate:
- `Rights.admits` ignores the stored label inside a hole: `everyone_level >= need and not contains(self.holes, path)` (`grants.py:468-481`); `Rights.ranges()` computes `holes`, `holed_arms` (spans ∩ holes) and `holed_owners` (`grants.py:483-510`).
- The three-seek set: the everyone leg carries `hole_free(path, ranges.holes, profile)` — `NOT EXISTS` over the unpacked hole pieces through the range source, or the literal negation on the floor (`ranges.py:122-145`); `holed_arms` and `holed_owners` are two more `UNION ALL` branches with `everyone_level >= need` (`ranges.py:109-114`). The hole is one bound value like every other piece set.
- The clause fan: with holes, `_units` replaces the everyone unit by `(everyone_level >= need) AND <piece outside the holes>` for each piece of `subtract(FULL, holes)` (`rights.py:1012-1031`), so the fan still splits it.
- The cache key carries the in-flight marks (`RightsKey.marks`, `rights.py:168-173`, `resolve_authority` `:298, 312-324`), so a walk compiled during a relabel sees the same predicate as every other verb. Pinned by `test_the_clause_fan_fences_a_hole_out_of_the_everyone_leg` (`test_rights.py:411`) and `test_reads_match_the_oracle_while_a_posture_relabel_is_held_midway` (`:386`). In Part C the holes were empty (`holes=Pieces(points=(), opens=())`); I did not hold a relabel midway.

Two further requirements for the walk that fall out of reading the forms:
- **The anchor must be judged too.** My script's anchor was the bare seed id; a hidden seed must yield no row, so the anchor is `seeds ∩ visible` (join, not `IN`), with the seed list bound as one value through the dialect's table function (`point_rows` style) and chunked by `membership_budget` — 10 statements per 10k seeds on Oracle's 1,000-element cap.
- **The liveness term rides every hop** (`t.deleted_at IS NULL`, `descent.tombstone_side`): a tombstoned endpoint hides its edges, as every edge reader does (`edges.py` docstring).

## Part C — executed check

Script: `scratchpad/experiments/r3_visibility_shape.py` (run as `uv run python <script> <scratch>/experiments` from the vfs root; SQLite file under the scratchpad). Setup: five files under `/pub` and `/priv/deep`; posture `private` at `/`; `bob` granted `read` on `/priv/deep` only; authored `cites` edges `d→c`, `c→e`, `d→b`.

Output (the Postgres/SQL Server/MariaDB/Oracle compiled statements are in the `.out` file; abbreviated here):

```
=== (a) tree('/') for bob ===
  /priv                  kind=directory  BARE (road)
  /priv/deep             kind=directory  visible row
  /priv/deep/d.md        kind=file       visible row
  /priv/deep/e.md        kind=file       visible row

=== bob's compiled read rights ===
  level=read need=1 whole=False empty=False
  spans=(('/priv/deep', '/priv/deep\x00'), ('/priv/deep/', '/priv/deep0')) roots=('/priv/deep',) holes=()
  owner_arms=(OwnerArm(owner='bob', prefixes=('/',)),)
  ranges=Ranges(arms=Pieces(points=('/priv/deep',), opens=(('/priv/deep/', '/priv/deep0'),)),
                owners=(('bob', Pieces(points=('/', '/priv/deep0'),
                         opens=(('/', '/priv/deep'), ('/priv/deep', '/priv/deep/'), ('/priv/deep0', '0')))),),
                holes=Pieces(points=(), opens=()), holed_arms=Pieces(points=(), opens=()), holed_owners=())

=== (b1) three-seek UNION ALL join, SQLite (range_source=json_each, fence MATERIALIZED) ===
WITH visible AS MATERIALIZED
(SELECT vfs_entries.entry_id AS entry_id FROM vfs_entries WHERE vfs_entries.everyone_level >= 1
 UNION ALL SELECT vfs_entries.entry_id FROM json_each('["/priv/deep"]') AS pts CROSS JOIN vfs_entries
   ON vfs_entries.path = pts.value AND vfs_entries.everyone_level < 1
 UNION ALL SELECT vfs_entries.entry_id FROM json_each('[["/priv/deep/", "/priv/deep0"]]') AS rng CROSS JOIN vfs_entries
   ON vfs_entries.path > json_extract(rng.value, '$[0]') AND vfs_entries.path < json_extract(rng.value, '$[1]') AND vfs_entries.everyone_level < 1
 UNION ALL SELECT vfs_entries.entry_id FROM json_each('["/", "/priv/deep0"]') AS pts CROSS JOIN vfs_entries
   ON vfs_entries.path = pts.value AND vfs_entries.owner_id = 'bob' AND vfs_entries.everyone_level < 1
 UNION ALL SELECT vfs_entries.entry_id FROM json_each('[["/", "/priv/deep"], ["/priv/deep", "/priv/deep/"], ["/priv/deep0", "0"]]') AS rng CROSS JOIN vfs_entries
   ON vfs_entries.path > json_extract(rng.value, '$[0]') AND vfs_entries.path < json_extract(rng.value, '$[1]') AND vfs_entries.owner_id = 'bob' AND vfs_entries.everyone_level < 1)
 SELECT vfs_entries.path FROM vfs_entries JOIN visible ON visible.entry_id = vfs_entries.entry_id
  -> rows the join admits: ['/priv/deep', '/priv/deep/d.md', '/priv/deep/e.md']

=== (b1) as postgresql (unnest) ===   ... FROM unnest(ARRAY['/priv/deep']) AS anon_1(value) JOIN vfs_entries ON vfs_entries.path = (anon_1.value COLLATE "C") AND ...
=== (b1) as mssql (openjson) ===      ... FROM OPENJSON('[["/priv/deep/", "/priv/deep0"]]') WITH (lo nvarchar(max) '$[0]', hi nvarchar(max) '$[1]') AS rng INNER LOOP JOIN vfs_entries ON vfs_entries.path > CAST(rng.lo COLLATE Latin1_General_100_BIN2_UTF8 AS VARCHAR(1024)) AND ...
=== (b1) as mariadb (json_table) ===  ... FROM JSON_TABLE('["/priv/deep"]', '$[*]' COLUMNS (value VARCHAR(1024) PATH '$')) AS pts STRAIGHT_JOIN vfs_entries FORCE INDEX (ix_vfs_entries_path) ON vfs_entries.path = CAST(pts.value AS BINARY) AND ...
=== (b1) as oracle (json_table_clob) === SELECT /*+ INDEX(vfs_entries ix_vfs_entries_everyone_path) */ ... UNION ALL SELECT /*+ CARDINALITY(pts 1) */ ... FROM JSON_TABLE('["/priv/deep"]', '$[*]' COLUMNS (value VARCHAR2(1024) PATH '$')) pts JOIN vfs_entries ON ...

=== (b2) literal OR clauses — the generic floor (no range source) ===
  clause 0 (13 binds): vfs_entries.everyone_level >= 1 OR vfs_entries.path = '/priv/deep'
    OR vfs_entries.path > '/priv/deep/' AND vfs_entries.path < '/priv/deep0'
    OR vfs_entries.owner_id = 'bob' AND (vfs_entries.path = '/' OR vfs_entries.path = '/priv/deep0'
       OR vfs_entries.path > '/' AND vfs_entries.path < '/priv/deep' OR vfs_entries.path > '/priv/deep' AND vfs_entries.path < '/priv/deep/'
       OR vfs_entries.path > '/priv/deep0' AND vfs_entries.path < '0')

=== stored edges (path form) ===
  / -[fs]-> /pub ; / -[fs]-> /priv ; /pub -[fs]-> /pub/a.md ; /pub -[fs]-> /pub/b.md ; /priv -[fs]-> /priv/c.md
  /priv -[fs]-> /priv/deep ; /priv/deep -[fs]-> /priv/deep/d.md ; /priv/deep -[fs]-> /priv/deep/e.md
  /priv/c.md -[cites]-> /priv/deep/e.md ; /priv/deep/d.md -[cites]-> /pub/b.md ; /priv/deep/d.md -[cites]-> /priv/c.md

=== (c) WITH RECURSIVE successors(/priv/deep/d.md, depth 3) over cites edges, on SQLite ===
  bob may see only /priv/deep/*. Chain d -> c(hidden) -> e; d -> b(hidden).
  no rights at all                                 reached=[('/priv/c.md', 1), ('/priv/deep/e.md', 2), ('/pub/b.md', 1)]
  post-filter only (Python admits after the walk)  reached=['/priv/deep/e.md']  <- e leaks through hidden c
  placement 1 (materialised CTE)                   reached=[]
  placement 2 (inline UNION ALL derived table)     reached=[]
  placement 3 (literal clauses on the target)      reached=[]
  placements agree: True ; the walk is cut at c, so e is NOT reached: True

=== EXPLAIN QUERY PLAN, placement 1 ===
  CO-ROUTINE walk / SETUP / SCAN CONSTANT ROW / RECURSIVE STEP
  MATERIALIZE visible
    SEARCH vfs_entries USING INDEX ix_vfs_entries_everyone_path (everyone_level>?)
    SCAN pts VIRTUAL TABLE INDEX 1: / SEARCH vfs_entries USING INDEX ix_vfs_entries_path (path=?)
    SCAN rng VIRTUAL TABLE INDEX 1: / SEARCH vfs_entries USING INDEX ix_vfs_entries_path (path>? AND path<?)
    SCAN pts VIRTUAL TABLE INDEX 1: / SEARCH vfs_entries USING INDEX ix_vfs_entries_path (path=?)
    SCAN rng VIRTUAL TABLE INDEX 1: / SEARCH vfs_entries USING INDEX ix_vfs_entries_owner_id (owner_id=?)
  SCAN walk
  SEARCH vfs_edges USING COVERING INDEX sqlite_autoindex_vfs_edges_1 (source_id=?)
  SEARCH t USING INDEX ix_vfs_entries_entry_id (entry_id=?)
  BLOOM FILTER ON visible (entry_id=?)
  SEARCH visible USING AUTOMATIC COVERING INDEX (entry_id=?)
```

Two things the run surfaced beyond the brief: the seed literal must be bound through `ULIDKey` (identity is binary-16 on disk; an untyped text literal matched nothing), and the recursive step seeks `vfs_edges` through the unique `(source_id, target_id, edge_type)` index rather than `ix_vfs_edges_fwd` on this tiny table — plan shape at scale is R-traversal's question.

## Open questions

1. Live-engine verification of the recursive placement on Postgres, MariaDB, SQL Server and Oracle (`scripts`/`db_test` legs): the inline derived table on MariaDB and Oracle; the `#temp` join on SQL Server; `MATERIALIZED` vs inlined `visible` on Postgres inside a recursive term.
2. Whether a TVF join (`OPENJSON`, `JSON_TABLE`) is accepted inside a SQL Server / MariaDB recursive member — decides whether the seed list can be bound inline in the anchor there or must be a temp table too.
3. Oracle's `CYCLE` clause and the depth column: whether a `depth` column in the WHERE of the recursive member changes Oracle's cycle detection (the doc defines cycles over "the columns … referenced in the WHERE clause of the recursive member").
4. Whether `graph(descendants over fs)` should equal `tree` at a road directory (Q4 option 3) — Clay's call.
5. A `Visibility.walk_source()` API shape: the same `visible_entries` statement, fenced per engine (`MATERIALIZED` on SQLite/Postgres, `/*+ MATERIALIZE */` on Oracle, a temp table on SQL Server/MariaDB) — a new profile fact alongside `range_fence`, since the fence that serves a flat join (Postgres: none) is not the one a recursion wants.

## Recommendation

**Put the caller's visible-entry set, computed once as the three-seek `UNION ALL`, inside the walk as a named set joined on `entry_id` in the recursive member — never as `IN (...)`, never as a disjunctive clause fan, and never as a filter after the walk.** The anchor joins the chunked seed list to the same set, so hidden seeds start nothing; the liveness term rides each hop; every emitted row still passes `Rights.admits` as a loud invariant.

Per engine, the one place it differs is how the set is spelled so it is computed once:

| Engine | Placement | Precedent it stands on |
|---|---|---|
| SQLite | prior CTE `visible AS MATERIALIZED`, `JOIN visible ON visible.entry_id = t.entry_id` in the recursive member | EXECUTED here: materialised once, probed per step by automatic index; `ranges.py`'s measured fence |
| Postgres | prior CTE `visible AS MATERIALIZED` joined in the recursive term; `SET LOCAL jit = off` already issued | RLS quals attached to every relation RTE inside CTE bodies (`rewriteHandler.c:2202-2208`); parser restricts only the self-reference |
| Oracle | prior named subquery with `/*+ MATERIALIZE */` (or the existing `NO_MERGE`/`LEADING`/`USE_NL` derived hints), joined in the recursive member; `CYCLE` clause on `entry_id` | Oracle's listed restrictions forbid only subqueries/outer joins that refer to `query_name` `[NOT VERIFIED live]` |
| MariaDB | prior CTE joined in the recursive part (MariaDB materialises it); depth under `max_recursive_iterations` (1000) | `ranges.py` docstring: join, not `IN` (seconds on MariaDB) `[NOT VERIFIED live]` |
| SQL Server | `SELECT entry_id INTO #visible` (PK on `entry_id`) in the transaction, `INNER JOIN #visible` in the recursive member; `OPTION (MAXRECURSION n)` for depth > 100 | Microsoft: subqueries are not allowed in a recursive member; CTEs are not materialised; "consider using a temporary object" |
| Generic floor (no range source) | if the rights fit one clause, the clause as a WHERE on the target row; otherwise the app-side per-hop frontier walk, one flat chunked statement per hop, visited set in Python | SpiceDB/OpenFGA's fan-out-per-hop loop (`check.go:393-420`, `reverse_expand.go:612-620`); vfs's own chunked-membership discipline |

For `fs`-typed hierarchy walks, route to the subtree scan (`tree`'s shape), where the road is already computed; inside the recursive walk a road-only directory is absent, as vfs already decided for edges on it (memo §5.2, §6).
