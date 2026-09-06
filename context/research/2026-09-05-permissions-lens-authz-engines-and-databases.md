# Permissions lens L4: authorization engines and databases

- **Status**: research memo, Phase 1 lens L4 of the principals and
  permissions programme (`2026-09-05-principals-and-permissions-research-plan.md`).
  Commits us to nothing. Feeds the Phase 3 synthesis, ADR 021 (grant
  spine, proposed), spec 058 (row grants) and study S2 (what ranked
  search leaks).
- **Date**: 2026-09-05
- **Owner**: Clay Gendron
- **Question**: When a policy engine or a database enforces "who may see
  and change which rows", where does the decision run (compiled into the
  query at one chokepoint, or checked per object), what is the unit it
  protects (a path prefix, an object id, a relation tuple, a label), how
  are groups resolved, what leaks, and which of those mechanisms survive
  vfs's dialect floor (Postgres, SQL Server, Oracle, SQLite; bounded
  statements; 10,000-row batches)? And, for the multiplayer rule
  (plan §1.1), has anyone computed the *meet* of several principals'
  rights and acted under it?
- **Method**: line-level reads of nine local clones (Oso, Casbin,
  SpiceDB, OpenFGA, django-guardian, PostgreSQL, Supabase storage,
  Cedar, OPA), each refreshed to its upstream default branch and its
  license re-checked, split across five read-only study agents plus a
  direct read of Supabase storage, Cedar and OPA; public documentation
  fetched for Zanzibar, Oracle `DBMS_RLS`, SQL Server row-level security,
  SQLite's authorizer and OPA's Compile API. Every claim carries a
  `repo:path:line` or a URL with the date read. Nothing was executed and
  nothing was copied; vfs code stays ours. ADR 021 already cites
  `rowsecurity.c:213-214`, SpiceDB's exclusion operator and Oak; spec
  070 already reviewed PostgREST and Supabase's identity pipeline. This
  memo extends both and repeats neither.
- **License**: Oso Apache-2.0 (`oso:LICENSE:1-3`; the library is
  deprecated upstream, `oso:README.md:1-3`, still receiving critical
  fixes). Casbin Apache-2.0 (`casbin:LICENSE:1`). SpiceDB Apache-2.0
  (`spicedb:LICENSE:1-3`, plus `NOTICE`). OpenFGA Apache-2.0
  (`openfga:LICENSE:2-4`, confirmed; the plan flagged it as unverified).
  django-guardian BSD (`django-guardian:LICENSE:1-2`). PostgreSQL
  licence (`postgres:COPYRIGHT:1-25`). Supabase storage Apache-2.0
  (`storage:LICENSE`). Cedar Apache-2.0 (`cedar:LICENSE`). OPA
  Apache-2.0 (`opa:LICENSE`). All study-only; copy nothing.
- **Sources line**: `osohq/oso` @ `7292df0` (2025-02-26, archived
  upstream); `casbin/casbin` @ `34297a1` (2026-08-21); `authzed/spicedb`
  @ `9b5cdc1` (2026-09-03); `openfga/openfga` @ `450b68c` (2026-09-04);
  `django-guardian/django-guardian` @ `09eb168` (2026-09-03);
  `postgres/postgres` @ `798bdcae` (2026-09-05, a 19-devel tree, cite as
  such); `supabase/storage` @ `c015666` (2026-09-03);
  `cedar-policy/cedar` @ `144048d` (2026-09-03); `open-policy-agent/opa`
  @ `855776c` (2026-09-04). Web, all read 2026-09-05: the Zanzibar paper
  via AuthZed's annotated copy (https://authzed.com/zanzibar; the USENIX
  PDF returned 403); Oracle `DBMS_RLS` 19c reference
  (https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_RLS.html;
  the VPD concepts chapter returned 404 at both 19c and 23ai URLs);
  SQL Server row-level security
  (https://learn.microsoft.com/en-us/sql/relational-databases/security/row-level-security,
  page dated 2025-09-11); SQLite `sqlite3_set_authorizer`
  (https://www.sqlite.org/c3ref/set_authorizer.html); Cedar
  authorization semantics (https://docs.cedarpolicy.com/auth/authorization.html)
  and RFC 0095 (https://github.com/cedar-policy/rfcs/blob/main/text/0095-type-aware-partial-evaluation.md);
  OPA REST API, Compile section (https://www.openpolicyagent.org/docs/latest/rest-api/#compile-api);
  SpiceDB schema docs (https://authzed.com/docs/spicedb/concepts/schema).

---

## Bottom line

1. **Every engine that filters a list compiles the policy into the query
   at one place.** Oracle VPD appends a predicate string; SQL Server
   binds an inline table-valued function; Postgres prepends
   `securityQuals`; Oso, OPA and Cedar partially evaluate the policy with
   the resource unknown and hand the residual to SQL. ADR 021 D3 is the
   field's consensus, not a vfs quirk.
2. **Reads filter, writes check, natively, in all three big databases.**
   Postgres `USING` filters silently and `WITH CHECK` errors; SQL Server
   has `FILTER PREDICATE` and `BLOCK PREDICATE` as distinct clauses;
   Oracle has `update_check`. Spec 058's "reads filter sets, writes check
   points" is the same split.
3. **SQLite has nothing.** Its authorizer is a compile-time table and
   column gate, never per row. App-level compilation is the only floor
   that reaches every target engine.
4. **The Zanzibar family cannot list cheaply.** Check is bounded; listing
   under intersection or exclusion degenerates to one Check per candidate
   in both SpiceDB ("shearing") and OpenFGA ("phase 2"), capped at 1,000
   results and, in OpenFGA, a 3-second wall clock.
5. **Conjunctive authority exists and is executable: SpiceDB's
   intersection arrow `relation.all(permission)`.** Every subject in the
   live relation must hold the permission; an empty set denies; caveats
   AND together; a member joining narrows the next query immediately.
   This is the multiplayer rule (plan §1.1) in shipped code.
6. **The leak classes have names.** Leaky-function ordering
   (`LEAKPROOF`), planner statistics (`pg_statistic` MCVs), error
   messages, referential-integrity covert channels, `EXPLAIN` and
   timing, and SQL Server's full-text join added "to avoid leaking the
   primary keys of rows that should be filtered". vfs's BM25 idf is the
   statistics leak in our own terms; S2 should measure it.
7. **Nobody models "on behalf of".** Postgres has a three-level identity
   (authenticated, session, current) that narrows; every policy engine
   has one principal slot. The actor/subject pair is ours to add, and the
   database precedent is the audit-visible `SESSION_USER` vs
   `CURRENT_USER` split.
8. **Superuser is a bypass in databases and a principal in engines.**
   `BYPASSRLS`, Oracle's `EXEMPT ACCESS POLICY`, Supabase's
   `asSuperUser()`; versus Casbin's `r.sub == "root"` matcher term and
   Zanzibar's nothing at all. SQL Server is the outlier: no one bypasses,
   the policy must say so.

---

## Q1. Subject, actor, and "on behalf of"

**Verdict: qualified.** The actor/subject split exists inside Postgres as
a narrowing chain of identities and inside SQL Server as a shared login
plus `SESSION_CONTEXT`. No engine represents "X acting for Y" as a pair.

*Postgres keeps three identities and RLS reads the innermost.* The design
comment at `postgres:src/backend/utils/init/miscinit.c:420-458` names
them: `AuthenticatedUserId` ("determined at connection start and never
changes"), `SessionUserId` (changed only by `SET SESSION AUTHORIZATION`,
reported by `SESSION_USER`), `OuterUserId` (changed by `SET ROLE`), and
`CurrentUserId` ("the one to use for all normal permissions-checking
purposes", changed inside `SECURITY DEFINER` functions). A fourth,
pre-database identity, `SYSTEM_USER` = `auth_method:authn_id`, is set at
`miscinit.c:870-894`. Row security consults the current user, or a
view's `checkAsUser` when set:
`postgres:src/backend/rewrite/rowsecurity.c:126-127` and
`postgres:src/backend/utils/misc/rls.c:56`. So policies follow `SET
ROLE` and `SECURITY DEFINER`; they are not pinned to the login. The
`checkAsUser` field is documented as letting "rules act as setuid
gateways" (`postgres:src/include/nodes/parsenodes.h:1358-1389`).

*SQL Server's middle-tier pattern is the closest thing to a subject
carried by an actor.* The docs' scenario C: the application connects as
one login (`AppUser`), stamps the end user with
`sp_set_session_context @key=N'UserId', @value=..., @read_only=1`, and
the predicate function reads
`CAST(SESSION_CONTEXT(N'UserId') AS int)` while also pinning
`DATABASE_PRINCIPAL_ID() = DATABASE_PRINCIPAL_ID('AppUser')` (SQL Server
RLS docs, read 2026-09-05). The database principal is the actor; the
session-context value is the subject; the predicate checks both. That
is spec 070's "verify at the edge, consume as trusted data" shape with
the pair made explicit in the predicate.

*Oracle* provides the same via application context and policy groups
driven by a context: "the context that determines which application is
running" selects which policy group applies (`DBMS_RLS` reference,
`ADD_POLICY_CONTEXT`, read 2026-09-05). The VPD chapter that documents
`CLIENT_IDENTIFIER` and proxy users could not be fetched (404); see
Limits.

*Policy engines have one slot.* Oso's `allow(actor, action, resource)`
treats `actor` as a bare first argument; the `Actor` union
(`oso:polar-core/src/resource_block.rs:10`) is sugar, and a comment says
the distinction "will go away" (`resource_block.rs:110-117`). A repo-wide
search for delegation or impersonation finds only prose and a user-level
example (`oso:docs/content/any/getting-started/application/write-rules.md:106-110`).
Cedar's request is principal, action, resource, context; no actor
(Cedar authorization docs). Casbin's request is whatever
`[request_definition]` says, positionally bound
(`casbin:model/model.go:87-91`). Zanzibar's Check takes "a putative user,
often represented by an authentication token" (paper §2.4).

*System as principal versus bypass.* Databases bypass: Postgres
superusers "are always considered to have BYPASSRLS" and table owners
bypass unless `FORCE ROW LEVEL SECURITY`
(`postgres:src/backend/utils/misc/rls.c:82-121`;
`postgres:doc/src/sgml/ddl.sgml:2980-2985`); Oracle exempts `SYS` and
holders of `EXEMPT ACCESS POLICY` ("fine-grained access control
policies do not apply to users with EXEMPT ACCESS POLICY system
privilege", `DBMS_RLS` reference); Supabase's `asSuperUser()`
"impersonate[s] any subsequent chained operations as superUser bypassing
RLS rules" (`storage:src/storage/object.ts:84-86`). Engines make it a
principal: Casbin's `|| r.sub == "root"` is a matcher disjunct
(`casbin:examples/basic_with_root_model.conf:11`, test
`casbin:model_test.go:110-125` shows it holds with no policy loaded);
Oso's superuser is a policy idiom
(`oso:polar-core/benches/benchmarks/roles_policy.polar:3`); SpiceDB and
OpenFGA have no bypass anywhere, everything is a tuple or a schema rule
(searched, none found). SQL Server is the strict end: "Security policies
apply to all users, including dbo users in the database ... If high
privileged users, such as sysadmin or db_owner, need to see all rows to
troubleshoot or validate data, the security policy must be written to
allow that" (SQL Server RLS docs). Postgres's `row_security = off` is a
third shape worth naming: it does not bypass, "what it does is throw an
error if any query's results would get filtered by a policy"
(`postgres:doc/src/sgml/ddl.sgml:3253-3265`), and `pg_dump` sets it so a
backup fails loudly rather than silently omitting rows.

## Q2. Attenuation: narrowing, and whether it can widen

**Verdict: supports, with one named widening primitive.** Every
narrowing mechanism is a set intersection; the databases also ship a
deliberate widening primitive (`SECURITY DEFINER`, view owner
permissions) and it is the source of their classic leak.

*`SET ROLE` narrows and cannot escape.* The session user must hold the
`SET` option on the target role (`member_can_set_role(GetSessionUserId(),
roleid)`, `postgres:src/backend/commands/variable.c:997`;
`postgres:doc/src/sgml/ref/set_role.sgml:46-52`). With `INHERIT TRUE`,
"SET ROLE effectively drops all the privileges except for those which
the target role directly possesses or inherits" (`set_role.sgml:77-92`).
`SET SESSION AUTHORIZATION` is superuser-only and the check is against
the *authenticated* user, so a session cannot climb back:
`variable.c:879-899` ("the original authenticated user's superuserness
is what matters").

*`SECURITY DEFINER` widens, and `security_invoker` undoes it.*
`fmgr_security_definer` pushes the function owner as the current user
with `SECURITY_LOCAL_USERID_CHANGE`
(`postgres:src/backend/utils/fmgr/fmgr.c:702-711`), which also blocks
`SET ROLE` inside. A view by default checks base relations as the view
owner and applies the owner's RLS policies; `security_invoker` switches
both to the caller (`postgres:doc/src/sgml/ref/create_view.sgml:292-320`),
and the property is sticky downward ("a security invoker view will
always check its underlying base relations using the permissions of the
current user, even if it is accessed from a view without the
security_invoker property", `:301-308`). Supabase's listing functions
are all `SECURITY INVOKER`
(`storage:migrations/tenant/0050-search-v2-optimised.sql:107,345,617,695`)
while its prefix-maintenance helpers were `SECURITY DEFINER`
(`storage:migrations/tenant/0026-objects-prefixes.sql:64,82`): read paths
run as the caller, bookkeeping runs as the owner.

*Capabilities minted from a principal's rights narrow by construction.*
Supabase's signed URL is a JWT carrying `url`, `scope` and optional
`versionId`, spread *last* so "attacker-controlled metadata can never
override the intended object path, token scope, or pinned version"
(`storage:src/storage/object.ts:777-800`); the signer strips `role`,
`upsert` and `owner` claims because "signObjectUrl could be used as a
signing oracle" (`:777-782`). Verification is one function that checks
signature, scope, path binding and expiry
(`storage:src/storage/object.ts:911-947`). The token is at most what the
signer could see (`findObject` runs first under the signer's RLS,
`:763`).

*Policy engines narrow only through deny or condition.* Cedar: "If any
forbid policy evaluates to true, then the final result is Deny" and
"by default, the decision is Deny" (Cedar authorization docs); code at
`cedar:cedar-policy-core/src/authorizer/partial_response.rs:121-138`,
where a satisfied forbid decides Deny before any permit is consulted.
SpiceDB caveats narrow a grant by context, with partial evaluation and a
residual expression when context is missing
(`spicedb:pkg/caveats/eval.go:44-52,95-105`). OpenFGA conditions are
all-or-nothing: missing context is an error, not a narrower answer
(`openfga:internal/condition/eval/eval.go:68-76`). SQL Server's
`@read_only=1` on `SESSION_CONTEXT` "prevents the value from changing
again until the connection is closed" (RLS docs), the session-level pin.

*One anti-pattern to carry into the threat table.* `sqlalchemy-oso`
warns four times that SQLAlchemy's baked-query cache "can bypass
authorization by using queries from the cache"
(`oso:languages/python/sqlalchemy-oso/sqlalchemy_oso/session.py:101,170,201,269`)
and disables it (`:247`). A compiled predicate cached across principals
is a widening bug; vfs's chokepoint must key any statement cache on the
principal or keep the predicate as bound parameters.

## Q3. Where enforcement runs

**Verdict: supports ADR 021 D3.** The read/write asymmetry is native in
all three databases; the engines that can list all compile the policy
into the query; the engines that cannot compile (Zanzibar family) pay
one Check per candidate to list.

*Oracle VPD.* The policy function returns a `VARCHAR2` predicate; "The
server then produces a transient view with the text `SELECT * FROM
hr.employees WHERE P1`", and "Predicates generated from different VPD
policies for the same object have the combined effect of a conjunction
(ANDed) of all the predicates" (`DBMS_RLS` reference). Writes:
`update_check` "causes the server to also check the policy against the
value after insert or update"; `INSERT` coverage *requires* it or
`ORA-28104` is raised. Five policy types decide when the predicate is
recomputed: `STATIC` once per object and cached in the SGA;
`CONTEXT_SENSITIVE` re-evaluated when the session context changes;
`DYNAMIC` (the default) "always reexecutes the policy function upon each
statement parsing and execution". The predicate string has a byte budget:
4,000 bytes by default, 32K with `long_predicate => TRUE` (Q11).

*SQL Server.* "Filter predicates silently filter the rows available to
read operations (SELECT, UPDATE, and DELETE). Block predicates
explicitly block write operations (AFTER INSERT, AFTER UPDATE, BEFORE
UPDATE, BEFORE DELETE) that violate the predicate." "RLS filter
predicates are functionally equivalent to appending a WHERE clause."
The predicate is an inline table-valued function bound with
`SCHEMABINDING` so callers need no rights on the tables it joins. One
subtlety vfs must not repeat: "it's possible to update rows in such a
way that they'll be filtered afterward" unless an `AFTER UPDATE` block
predicate is added (all quotes: SQL Server RLS docs).

*Postgres.* `USING` quals become `securityQuals` on the range-table entry,
prepended so RLS runs before any security-barrier view quals
(`postgres:src/backend/rewrite/rewriteHandler.c:2336-2345`); `WITH CHECK`
becomes `WithCheckOption`s that raise
(`postgres:src/backend/rewrite/rowsecurity.c:277-282`: policies are
"added as WCO policies rather than security quals to ensure that an
error is raised if a policy is violated; otherwise, we might end up
silently dropping rows to be added"). The `QUAL_FOR_WCO` macro
(`rowsecurity.c:836-839`) makes `USING` the fallback write check when no
`WITH CHECK` exists. Everything the executor sees is one query; RLS is
the last rewrite pass (`rewriteHandler.c:2249-2253`).

*Oso.* `Oso.authorized_query` runs `allow(actor, action, Variable
("resource"))` with actor and action *concrete* and only the resource
unknown (`oso:languages/python/oso/polar/polar.py:273-293`), reduces the
partial results to disjunctive normal form in `Filter::build`
(`oso:polar-core/src/filter.rs:133-162`, doc comment `:23-33`: "an OR of
ANDs"), and the adapter emits joins plus one `filter(...).distinct()`
(`oso:languages/python/oso/polar/data/adapter/sqlalchemy_adapter.py:15-40`).
The docs are explicit that conditions are "applied to the query before
retrieving objects from the database"
(`oso:docs/content/python/reference/frameworks/data_filtering/sqlalchemy.md:54-58`)
and that post-filtering "isn't efficient and many times is just
impossible" (`oso:docs/content/any/guides/data_filtering/index.md:52-63`).
Two adapter defects for the record: ordering comparisons fall through to
`None` and `In` uses Python's `in` rather than `.in_()`
(`sqlalchemy_adapter.py:45-57`).

*OPA.* The Compile API partially evaluates with `unknowns` and returns
residual `queries` (disjunction of conjunctions); an empty `queries`
array means unconditionally true, an absent field means unsatisfiable
(OPA REST API docs, "Unconditional Results"). OPA 1.x adds
`POST /v1/compile/{path}` with targets `sql+postgresql`, `sql+mysql`,
`sql+sqlserver`, `sql+sqlite` and `ucast+*`
(`opa:v1/server/compile_handler.go:45-53`), going through a UCAST tree
whose operators are `and/or/not`, `exists`, and field comparisons
including `in` (`opa:internal/ucast/ucast.go:31-34`), then
`QueriesToSQL` (`opa:internal/compile/compile.go`). SQLite gets a reduced
builtin set: "sqlite doesn't support startswith/endswith/contains"
(`opa:internal/compile/constraints.go:203-204`). Mask rules produce
column masks (`compile_handler.go:77,89`).

*Cedar.* `is_authorized_partial` returns residual permits and forbids
(`cedar:cedar-policy/src/api.rs:1120-1135`, experimental); RFC 0095's
typed partial evaluation names the use case: "If the entity data is
stored in a relational database, we can retrieve the relevant resources
by translating the residuals to a SQL query" (RFC 0095, status TBD,
read 2026-09-05). The core loop is `is_authorized_core_internal`
(`cedar:cedar-policy-core/src/authorizer.rs:86-155`).

*Casbin has no compiler.* `GetAllowedObjectConditions` scans the loaded
policy, string-strips a prefix from column 1 of each row whose column 2
equals the action, and returns raw strings for the caller to splice into
SQL (`casbin:rbac_api.go:489-511`); it ignores `p.eft`, so a deny model
yields wrong conditions, and an empty result is an error because "some
data adapters' ORM return full table data by default when they receive
an empty condition" (`:485-487`). `BatchEnforce` is a sequential loop
(`casbin:enforcer.go:966-976`).

*django-guardian* compiles to a queryset filter; see Q6 and Q13.

*Zanzibar family: Check per object; listing is derived.* The paper
offers no "list all objects a user can see" API; Read returns tuples and
Expand resolves one object (paper §2.4). SpiceDB's LookupResources
dispatches directly only when the entrypoint "is not contained under an
intersection or exclusion"; otherwise it "shears" candidates through
Check (`spicedb:internal/graph/lookupresources3.go:914-934,989-1063`;
`spicedb:pkg/schema/reachabilitygraph.go:444-451`). OpenFGA's ListObjects
does reverse expansion, and "If any results yielded by reverse expansion
require further eval, then these results get dispatched to Check"
(`openfga:pkg/server/commands/list_objects.go:307-310,419-481`), with a
prose and diagram walkthrough at
`openfga:docs/list_objects/example_with_intersection_or_exclusion/example.md`.

*What each does for listing and search (Q3 meets Q4).* A compiled
predicate lists by scanning with the predicate in place, which is what
lets Supabase derive folder prefixes from visible objects on the fly
(`storage:migrations/tenant/0050-search-v2-optimised.sql:6-7`). A
per-object checker lists by enumerating candidates and checking each,
bounded by a result cap and a deadline (Q11). For ranked search the
compiled predicate must sit at the join-back before scoring; SQL Server
documents the cost as "an extra join introduced to apply row-level
security and avoid leaking the primary keys of rows that should be
filtered" for `CONTAINSTABLE` and friends (SQL Server RLS docs). That is
spec 058's ranked-search fork answered by a vendor: filter at the
join-back, accept the join.

## Q4. The unit of protection

**Verdict: supports ADR 021 D2 (path prefixes), and sharpens the
id-vs-path fork.** The field uses four units; the choice decides what a
move costs.

| Unit | Who | Evidence |
|---|---|---|
| Path prefix | Supabase, Casbin `keyMatch` | `storage:migrations/tenant/0020-list-objects-with-delimiter.sql:8,23,29` (`name COLLATE "C"` range scans); `casbin:util/builtin_operators.go:169-181` (`keyMatch` is a byte-prefix compare where `*` swallows the rest, including `/`) |
| Object id | Zanzibar, SpiceDB, OpenFGA, django-guardian | tuple `⟨object#relation@user⟩` (paper §2.1); six identity columns `(namespace, object_id, relation, userset_namespace, userset_object_id, userset_relation)` (`spicedb:internal/datastore/postgres/migrations/zz_migration.0001_1eaeba4b8a73_initial.go:23-36`); `tuple(store, object_type, object_id, relation, _user, ...)` with a `store` tenant column in the primary key (`openfga:assets/migrations/postgres/001_initialize_schema.sql:2-12`); guardian's `object_pk` is a string column (Q6) |
| Label | Casbin BLP/Biba, SQL Server, Oracle | `r.sub_level >= r.obj_level` for read, `<=` for write (`casbin:examples/blp_model.conf:14`); "Label-based access control can be implemented by using predicate-based access control" (SQL Server RLS docs) |
| Any predicate over the row | VPD, RLS, Oso, OPA, Cedar | Q3 |

*Hierarchy is a relation, evaluated per query, in the id systems.*
Neither SpiceDB nor OpenFGA has paths or prefixes; a folder tree is
`relation parent: folder` plus an arrow `parent->view`
(`spicedb:internal/services/steelthreadtesting/testdata/document-with-intersect-arrow.yaml:5-9`;
`openfga:docs/check/README.md:52-61`). Because the arrow is walked at
check time, **a move is rewriting one `parent` tuple** and every derived
right changes at once with no fan-out. SpiceDB's `optional_preconditions`
make that rewrite a compare-and-swap (`MUST_MATCH` / `MUST_NOT_MATCH`,
`spicedb:internal/services/v1/preconditions.go:18-54`); OpenFGA has only
`on_duplicate` / `on_missing` policies, no state assertion
(`openfga:pkg/server/commands/write.go:58-77`). SpiceDB's one thing
called "prefix" is a CockroachDB transaction-overlap key cut from the
namespace name, not a resource path
(`spicedb:internal/datastore/crdb/keys.go:51-58`).

*The prefix systems tried materialising the tree and went back.*
Supabase added a `storage.prefixes` table with its own RLS, generated
`level` column and `SECURITY DEFINER` maintenance triggers
(`storage:migrations/tenant/0026-objects-prefixes.sql:13-23,64,82`), then
replaced it: `search_v3` has "No dependency on prefixes table or
triggers" and "Derives common prefixes on-the-fly from objects table"
using a skip-scan over the existing `(bucket_id, name COLLATE "C")` index
(`storage:migrations/tenant/0050-search-v2-optimised.sql:1-16`, triggers
dropped at `:802-808`). Two consequences for vfs: a folder is visible
exactly when some object under it is visible (Q5), and the ancestor
chain does not need rows of its own.

*Oso's join graph cannot recurse.* A type may appear once as a relation
target (`oso:polar-core/src/filter.rs:374-388`, test `:703-720`); the
docs call self-relations "currently unsupported"
(`oso:docs/content/any/guides/data_filtering/index.md:196-198`). Folder
inheritance desugars correctly (`oso:polar-core/src/resource_block.rs:695-720`)
but cannot be filtered. A path-prefix `LIKE` avoids the recursion; an
ancestor-id list (GitLab's `traversal_ids`, already in ADR 021) is the
other escape.

*Tenancy.* Casbin scopes roles per domain,
`g(r.sub, p.sub, r.dom) && r.dom == p.dom`
(`casbin:examples/rbac_with_domains_model.conf:14`), with one role
manager per domain (`casbin:rbac/default-role-manager/role_manager.go:491-497`);
OpenFGA puts `store` in the primary key; Oracle selects policy groups
by driving context. All three make the tenant a column or a key, not a
path.

## Q5. Hide versus deny, and traversal

**Verdict: supports spec 058's `invisible` rung, and supplies the leak
taxonomy.** "Hidden" is the read default in every database; "denied" is
the write default; the exceptions are where the leaks are.

*Silent filter versus raised error, exactly.* Postgres:
"Existing table rows are checked against the expression specified in
USING, while new rows that would be created via INSERT or UPDATE are
checked against the expression specified in WITH CHECK ... Typically,
no error occurs when a row is not visible ... When a WITH CHECK
expression returns true for a row then that row is inserted or updated,
while if false or null is returned then an error occurs"
(`postgres:doc/src/sgml/ref/create_policy.sgml:44-57`). The summary
table's legend is the crispest statement: "check means that the policy
expression is checked and an error is thrown if it returns false or
null, whereas filter means that the row is silently ignored"
(`create_policy.sgml:458-466`). The exceptions turn hide into deny:
`RETURNING` ("inserted or updated rows to be returned are never
silently ignored", `:285-293`), `INSERT ... ON CONFLICT` ("the UPDATE
path will never be silently avoided", `:294-311`), and `MERGE`
(`rowsecurity.c:513-518`: "If RLS prohibits UPDATE/DELETE on the target
row, we shall throw an error instead of silently ignoring the row. This
is different than how normal UPDATE/DELETE works"). SQL Server: "For
filter predicates, the application is unaware of rows that are filtered
from the result set. If all rows are filtered, then a null set is
returned. For block predicates, any operations that violate the
predicate will fail with an error" (RLS docs).

*Supabase maps the two to 404 and 403.* A `findObject` that returns no
row raises `NoSuchKey` ("Object not found",
`storage:src/storage/database/pg.ts:1011`;
`storage:src/internal/errors/codes.ts:130-136`); a write refused by RLS
arrives as SQLSTATE `42501` and is mapped to `AccessDenied` with the
message "new row violates row-level security policy"
(`storage:src/storage/database/errors.ts:18-24`); a delete whose
`UPDATE ... RETURNING` touched nothing is reported as `AccessDenied`
(`storage:src/storage/object.ts:157`). django-guardian's view mixin
lets the developer choose: redirect to login (default), `return_403`,
`return_404`, or `raise_exception`
(`django-guardian:guardian/mixins.py:106-111,140-142`;
`django-guardian:guardian/utils.py:159-170`), so hide versus deny is a
per-view setting with no default toward hiding.

*Traversal.* Under Supabase's on-the-fly listing a prefix appears only if
a visible object exists beneath it (Q4), so a hidden subtree hides its
folder; that is the directory-execute analogue without a directory row.
Zanzibar has no visibility concept at all; Check answers yes or no and
LookupResources returns the yes set.

*The leak classes, for S2 and the threat table.*

1. **Leaky functions ordered below the barrier.** The planner may run a
   cheap user function before the policy qual and print every hidden row
   as a `NOTICE` (`postgres:doc/src/sgml/rules.sgml:2102-2136`, with the
   `tricky()` example at `COST 0.0000000000000000000001`). The fix is
   `security_level` on every qual: "a clause cannot be evaluated before
   another clause with a lower security_level value unless the first
   clause is leakproof" (`postgres:src/include/nodes/pathnodes.h:2834-2842`);
   `contain_leaked_vars` treats an unknown node as leaky ("This prevents
   an unexpected security hole if someone adds a new node type",
   `postgres:src/backend/optimizer/util/clauses.c:1499-1508`);
   `order_qual_clauses` sorts by level and lets a leakproof qual costing
   under ten `cpu_operator_cost` pretend to be level zero
   (`postgres:src/backend/optimizer/plan/createplan.c:5327-5341`). Only a
   superuser may mark a function `LEAKPROOF` "because leakproof functions
   can see tuples which have not yet been filtered out"
   (`postgres:src/backend/commands/functioncmds.c:1157-1165`). Cost:
   security-barrier subqueries are never flattened
   (`postgres:src/backend/optimizer/README:1323-1339`), and an index scan
   is refused when the operator's function is not leakproof
   (`rules.sgml:2174-2199`).
2. **Planner statistics.** `statistic_proc_security_check` allows a
   function to see `pg_statistic` values only if "the user has SELECT
   privileges on the table or column underlying the pg_statistic data
   and there are no securityQuals from security barrier views or RLS
   policies" or "the function is marked leakproof"
   (`postgres:src/backend/utils/adt/selfuncs.c:6677-6701`); otherwise
   "the functions might reveal data that the user doesn't have
   permission to see" (`:6081-6094`). Failure is a `DEBUG2` message and a
   worse plan ("There is no direct feedback about that, except that the
   plan might be suboptimal", `postgres:doc/src/sgml/planstats.sgml:737-747`).
   Null fraction and distinct counts are exempt (`planstats.sgml:749-756`).
   SQL Server: "DBCC SHOW_STATISTICS reports statistics on unfiltered
   data, and can leak information otherwise protected by a security
   policy", so viewing them is restricted to owners and admins (RLS docs).
3. **Error messages.** Unique and exclusion violations return no key
   values when RLS is enabled or the user lacks SELECT on every key
   column ("return NULL to avoid leaking data",
   `postgres:src/backend/access/index/genam.c:191-200`); foreign-key
   violations drop the `errdetail` under RLS
   (`postgres:src/backend/utils/adt/ri_triggers.c:3752-3764`); `WITH CHECK`
   violations echo only the columns the caller supplied
   (`postgres:src/backend/executor/execMain.c:2488-2506`). SQL Server's
   version: `SELECT 1/(SALARY-100000) ... WHERE NAME='John Doe'` "would
   let a malicious user know that John Doe's salary is exactly $100,000"
   through the divide-by-zero, and predicate functions must not depend on
   `SET DATEFORMAT`, `SET ANSI_WARNINGS` and similar session options
   (RLS docs, "Carefully crafted queries").
4. **Referential-integrity covert channel.** "Referential integrity
   checks ... always bypass row security"
   (`postgres:doc/src/sgml/ddl.sgml:3245-3251`); inserting a duplicate key
   reveals that the hidden value exists, and the docs recommend surrogate
   keys (`create_policy.sgml:747-764`). `SECURITY_NOFORCE_RLS` exists so
   `FORCE ROW LEVEL SECURITY` "does not mistakenly break referential
   integrity checks" (`postgres:src/backend/utils/init/miscinit.c:597-602`).
5. **`EXPLAIN`, timing and plan choice.** "they can see the query plan
   using EXPLAIN, or measure the run time of queries against the view
   ... or even, since they are also reflected in the optimizer
   statistics, the choice of plan" (`rules.sgml:2201-2215`). SQL Server
   adds Change Data Capture (leaks whole rows to the gating role), Change
   Tracking (leaks primary keys), and bans indexed views on secured
   tables "because row lookups via the index would bypass the policy"
   (RLS docs, "Cross-feature compatibility").
6. **Counts and aggregates.** Postgres has no aggregate-specific
   sentence; the guarantee is that policy expressions run "prior to any
   conditions or functions coming from the user's query" and "Rows for
   which the expression does not return true will not be processed"
   (`ddl.sgml:2963-2977`), so `count(*)` counts visible rows. Cardinality
   still leaks through class 5.

*Named for S2.* vfs's `glean` computes BM25 with a corpus-wide inverse
document frequency, and the cross-mount merge exports `lexical_stats`.
Both are class 2: a statistic computed over rows the caller cannot see,
passed to a scoring function that is not leakproof, whose output (a
score, a rank, a document-frequency count) reaches the caller. The
Postgres rule for that class is "leakproof, or computed over the
caller's visible rows only"; SQL Server's full-text rule is "add the
join before the ranking function". S2 should measure how much a score
alone reveals and cost per-visible-set statistics against coarsened idf.
The posting lists themselves (bare doc ids) are class 5 if their size
or timing is observable.

## Q6. Groups, roles, tenants

**Verdict: supports a memberships indirection resolved per query.** Every
system resolves membership at query time; none materialises it at write
time. The fork that matters is *how* the closure reaches the query: as a
join or subquery (Postgres, guardian), or enumerated into literals (Oso).

*Postgres resolves roles at plan time with inherited privileges only.*
`check_role_for_policy` matches `PUBLIC` first, then
`has_privs_of_role(user_id, roles[i])`
(`postgres:src/backend/rewrite/rowsecurity.c:952-972`), so a role granted
`WITH INHERIT FALSE` does not activate its policies until `SET ROLE`.
Any query touching RLS sets `hasRowSecurity` "so plancache can invalidate
it when necessary (eg: role changes)" (`rowsecurity.c:565-569`).

*Zanzibar resolves usersets recursively at check time and flattens the
deep ones.* A userset `⟨object#relation⟩` is a user (paper §2.1);
`_this` "includ[es] indirect ACLs referenced by usersets from tuples"
(§2.3.1); Leopard keeps `GROUP2GROUP` and `MEMBER2GROUP` sets as sorted
integer lists so membership is one intersection (§3.2.4). SpiceDB
redispatches non-terminal subjects (`spicedb:internal/graph/check.go:307-312`)
with a dispatch cache (`spicedb:internal/dispatch/caching/caching.go:56-57,154-155`)
and a depth budget of 50 (`spicedb:pkg/cmd/serve.go:157`) whose error
carries a traversal trace (`spicedb:internal/dispatch/errors.go:24-30`).
OpenFGA's depth is 25 with a breadth limit of 10 and explicit cycle
detection (`openfga:pkg/server/config/config.go:25-26`;
`openfga:internal/graph/check.go:415-419`); a computed userset does not
consume depth (`check.go:855`). Neither write path expands anything
(`spicedb:internal/services/v1/relationships.go:353-402`;
`openfga:pkg/server/commands/write.go`).

*Casbin builds the graph at load and walks it per check.* Links are
built by `buildRoleLinks` at policy load
(`casbin:model/assertion.go:73`); `HasLink` is a breadth-first walk with
a hop budget hardcoded to 10 at every construction site
(`casbin:rbac/default-role-manager/role_manager.go:312-351`;
`casbin:enforcer.go:601-613`), a chain longer than that silently resolves
false. The `g()` memo map is rebuilt per `Enforce` call
(`casbin:enforcer.go:719-732`) and is unbounded, hence
`EnableGFunctionCache` (`:651-657`).

*Oso enumerates groups into the WHERE clause.* Because the actor is
concrete during partial evaluation, `team in user.teams` is evaluated
eagerly against application data and each team becomes its own DNF
disjunct (`oso:polar-core/src/filter.rs:147-155`;
`oso:languages/python/oso/tests/resource_blocks.polar:7-13`). Joins are
only discovered on the resource side (`filter.rs:242-287`). A user in 500
teams yields a predicate proportional to 500, and the tests admit the
missing "combine into an IN" optimisation
(`oso:languages/python/oso/tests/data_filtering/test_new.py:395-403`).
This is the shape CLAUDE.md's `IN`-list budget forbids.

*django-guardian unions user and group grants in the queryset.*
`get_objects_for_user` returns the whole queryset for a superuser
(`django-guardian:guardian/shortcuts.py:678`) or when a model-level
(global) permission covers the request (`:699`); otherwise it builds one
subquery over `UserObjectPermission` and one over
`GroupObjectPermission` filtered by `group__in: user.groups.all()`
(`:728`) and ORs them into the final filter, `q |= Q(pk__in=values)`
(`:791-794`). Both are subqueries, so the statement does not grow with
the number of objects. The per-object rows carry `object_pk` as a
255-character string with a `(user, permission, object_pk)` unique key
(`django-guardian:guardian/models/models.py:56,111,176`): an id
coordinate, never a path.

*Cedar takes the hierarchy as request data.* Membership is `principal in
Group::"..."` over an entities slice supplied per request (Cedar
authorization docs); the transitive closure is computed on that slice
(`cedar:cedar-policy-core/src/transitive_closure.rs`).

*Tenants* were covered in Q4: a column (OpenFGA `store`), a domain
argument (Casbin), or a policy group (Oracle).

## Q7. Defaults on creation, ownership, move and copy

**Verdict: qualified.** No engine has a umask. Ownership is a column the
application stamps, or a relation the application writes. Move is a
permission event in every system, and the databases already check it as
"leave the old row and enter the new one".

*Ownership is stamped, not inferred.* Supabase stores `owner_id text`
(the old `owner uuid` is deprecated,
`storage:migrations/tenant/0018-add_owner_id_column_deprecate_owner.sql:1-4`);
upload takes an explicit `owner` (`storage:src/storage/object.ts:112`);
`moveObject` and `copyObject` take an `owner` parameter and write it
into the destination row (`object.ts:472-479,495-506;309-329,365-372`),
so a mover becomes the owner of what it moved unless the caller passes
the original. Zanzibar's `owner` is one tuple with no creation hook;
`permission edit = owner + editor` gives it meaning (§10 of the SpiceDB
study; both repos). django-guardian has no automatic assignment
(`assign_perm` is explicit,
`django-guardian:guardian/shortcuts.py:83`; no `post_save` hook exists). Casbin's ABAC can express ownership as `r.sub ==
r.obj.Owner` with no policy rows at all
(`casbin:examples/abac_model.conf:11`).

*Move is checked as exit plus entry.* Postgres UPDATE applies `USING` to
the old row and `WITH CHECK` to the new one ("Note that the
check_expression is evaluated against the proposed new contents of the
row", `postgres:doc/src/sgml/ref/create_policy.sgml:220-224`), which is
precisely "may I leave this subtree, may I enter that one". SQL Server
needs `BEFORE UPDATE` plus `AFTER UPDATE` block predicates for the same
pair, and warns the optimiser skips `AFTER UPDATE` "if the columns used
by the predicate function weren't changed" (RLS docs). Supabase runs the
move twice: first as a *dry run* inside `testPermission`, a transaction
that performs the `UPDATE` under the caller's RLS and then always rolls
back (`storage:src/storage/object.ts:495-506`;
`storage:src/storage/database/pg.ts:250-265`), then the real write as
superuser after the S3 copy (`object.ts:510-560`). That is a point check
performed by executing the write and discarding it, a pattern vfs could
use for `move` verification on engines where the predicate is
app-level. `copyObject` calls `canUpload` on the destination before
touching storage and then commits as superuser (`object.ts:365-392`).

*In the id systems a move is one tuple rewrite* (Q4), atomic under
SpiceDB preconditions, not conditional in OpenFGA. The failure window is
named: two operations leave "no parent (denies) or two parents
(over-grants, or under `.all()` denies)".

*Defaults.* Nothing resembling a umask or inherited ACL at creation was
found in any engine. Postgres's "no policy means deny" is the only
default: with RLS enabled and no policy "a single always-false clause (a
default-deny policy) will be added" (`rowsecurity.c:166-183,808-812`).

## Q8. Audit: what is recorded, for whom, at what version

**Verdict: qualified.** Engines record *which rule decided* and *at
which revision*, not *who for whom*. The database precedent for the
pair is `SESSION_USER` versus `CURRENT_USER`; the version precedent is
the zookie.

*Which rule.* Postgres names the violated restrictive policy in the
error because each restrictive policy gets its own `WithCheckOption`
"to allow the policy name to be included in error reports", while
permissive policies collapse into one anonymous check "since if the
check fails it means that no policy granted permission ... rather than
any particular policy being violated"
(`postgres:src/backend/rewrite/rowsecurity.c:869-874,892-897`);
restrictive policies are sorted by name so errors are deterministic
(`:646-650`). Cedar's response lists the determining policies and any
policies that errored (Cedar authorization docs). Casbin's `EnforceEx`
returns the single rule that decided (`casbin:enforcer.go:912-916,952-956`).

*Which identity.* Postgres exposes both `SESSION_USER` and
`CURRENT_USER`; `CURRENT_USER` inside a view "will always return the
invoking user, not the view owner"
(`postgres:doc/src/sgml/ref/create_view.sgml:322-337`). SQL Server notes
that dbo changes to security policies "can be audited" (RLS docs). None
records an on-behalf-of pair.

*Which version.* A zookie is "an opaque byte sequence encoding a
globally meaningful timestamp that reflects an ACL write, a client
content version, or a read snapshot" (paper §2.2); a content-change
Check "is evaluated at the latest snapshot" and returns a zookie "for
clients to store along with object contents" (§2.4.4). SpiceDB's
ZedToken is revision plus datastore id plus schema hash
(`spicedb:pkg/zedtoken/zedtoken.go:85-111`), minted by middleware on
every response (`spicedb:pkg/middleware/consistency/consistency.go:74-95`).
OpenFGA keeps a `changelog` table but exposes no token
(`openfga:assets/migrations/postgres/001_initialize_schema.sql:41-50`).
vfs's per-entry `version` stamps are the content half of a zookie; the
ACL half (which grant revision was in force) is not recorded anywhere
yet. See Q10.

## Q9. Failure modes on record

**Verdict: supports the threat table.** Every row the plan lists has a
named precedent here.

| Failure | Precedent | Where vfs would hit it |
|---|---|---|
| Confused deputy | `SECURITY DEFINER` and view-owner checks widen (Q2); Supabase's signing oracle defence (`storage:src/storage/object.ts:777-782`) | any `system()` path that runs a caller-shaped query |
| Setuid hazard | `checkAsUser` "rules act as setuid gateways" (`postgres:src/include/nodes/parsenodes.h:1358-1389`) | a mount helper running as owner |
| TOCTOU | Supabase's dry-run then superuser write is two transactions (`object.ts:495-560`); SpiceDB closes it with preconditions | move, copy, revert |
| Stale-cache widening | baked-query cache bypass (`sqlalchemy-oso/session.py:101`) | a statement cache keyed without the principal |
| RLS leak classes 1 to 6 | Q5 | `glean`, error envelopes, counts |
| New enemy | two scenarios in `spicedb:internal/datastore/crdb/README.md:60-107`; OpenFGA "turns Check and ListObjects into eventually consistent APIs" when its cache is on (`openfga:cmd/run/run.go:317`) | a grant revoked, then a write that inherits the old grant |
| Availability over correctness | OpenFGA swallows a child error when another child is definitively false (`openfga:internal/graph/check.go:224,262-268`) | a partial storage failure inside a set predicate |
| Query blow-up | Oso's DNF has no size cap and enumerates groups (Q6, Q11); `vec_of_ands` at `oso:polar-core/src/filter.rs:590-617` | the subject-set predicate at 10k |
| Pattern injection | Casbin's `regexMatch` embeds the policy value unescaped ("acme.com matches acmeXcom", `casbin:util/builtin_operators.go:67-70,475-477`) | a grant prefix used inside `LIKE` without escaping |
| Silent depth failure | Casbin resolves false past 10 hops with no error (`role_manager.go:334-351`) | a deep group tree |
| Passthrough | spec 070 already covers it; nothing new here | |

Two implementation bugs are worth recording as cautionary tales rather
than threats: Oso's adapter uses Python `in` where SQL `IN` was meant
(`sqlalchemy_adapter.py:45-57`), and Casbin's `lbac_model.conf` applies
BLP's direction to the integrity axis, which is the inverse of Biba
(`casbin:examples/lbac_model.conf:14`, pinned by `casbin:lbac_test.go:44`).
Both are what a permission predicate looks like when it is not tested
against an oracle.

## Q10. Reversibility and permission together

**Verdict: no precedent, with one near miss.** No engine asks "may this
principal revert that change". The nearest structure is Zanzibar's
content-change check, which binds a content version to an ACL snapshot.

*The near miss.* A client about to save content asks for a
content-change Check with no zookie; the answer is evaluated at the
latest snapshot and returns a zookie the client "store[s] along with
object contents and use[s] for subsequent checks" (paper §2.4.4). A
later read at `at_least_as_fresh` that zookie can never see an ACL older
than the one under which the content was written (SpiceDB
`pickBestRevision`, `spicedb:pkg/middleware/consistency/consistency.go:174-192,286-330`).
Applied to vfs: a version row could carry the grant revision under which
it was written, and a revert would be a new write checked under the
*current* grants, never a replay of the old ones.

*The databases answer only the mechanical half.* A revert is an `UPDATE`,
so it needs `USING` on the row as it is now and `WITH CHECK` on the
content being restored (Q7). Supabase pins a signed URL to a
`versionId` (`storage:src/storage/object.ts:790-797`) and lets a delete
name an exact version (`object.ts:142-150`), but the check is the same
as for the head. Whether a revert may exceed the actor's rights is
therefore answered by construction: it cannot, because it is an ordinary
write.

## Q11. Scale and portability against vfs's dialect floor

**Verdict: supports ADR 021 D3, and adds one constraint.** Native
row security exists on three of four targets and is absent on SQLite;
the engines that compile to SQL do not bound their output; the engines
that check per object bound their listing by count and clock.

| Mechanism | Postgres | SQL Server | Oracle | SQLite |
|---|---|---|---|---|
| Native row filter | RLS `USING` | `FILTER PREDICATE` (2016+) | VPD, `DYNAMIC` default | none |
| Native write check | `WITH CHECK` | `BLOCK PREDICATE` (not on Fabric or Synapse) | `update_check` | none |
| Identity for a shared login | `SET ROLE`, GUC | `SESSION_CONTEXT` | application context | none |
| Bound on the predicate | none stated | none stated | 4,000 bytes, 32K with `long_predicate` | n/a |

SQLite's only hook is `sqlite3_set_authorizer`, "invoked as SQL
statements are being compiled", with action codes per table and column;
`SQLITE_IGNORE` on a read substitutes NULL for the whole column. It is
"not performed during statement evaluation in sqlite3_step()" and has no
per-row form (SQLite docs, read 2026-09-05). So the portable floor is
app-level compilation, as ADR 021 says, and native RLS is
defence-in-depth on three engines.

*The compiled-predicate engines do not bound their output.* Oso has no
chunking, no parameter-count guard, and enumerates actor-side facts into
literals (Q6); DNF conversion is worst-case exponential and `vec_of_ands`
has no cap (`oso:polar-core/src/filter.rs:590-617`); every query ends in
`.distinct()` (`sqlalchemy_adapter.py:40`). OPA's SQL targets exist for
all four vfs engines but SQLite loses `startswith`, `endswith` and
`contains` (`opa:internal/compile/constraints.go:203-204`), which are
exactly the prefix operators a path grant needs. Casbin is in-memory and
its `BatchEnforce` is a loop.

*The per-object engines bound listing hard.* SpiceDB: 1,000 results
(`spicedb:pkg/cmd/serve.go:118`), 1,000-row datastore pages (`:129`),
500-row response batches
(`spicedb:internal/graph/lookupresources3.go:36`), a 30-second stream
watchdog that names only the listing APIs (`spicedb:docs/spicedb.md:531`),
and resumable cursors hashed to request, revision and schema
(`spicedb:internal/services/v1/permissions.go:581-586`). OpenFGA: 1,000
results and a 3-second deadline with no cursor
(`openfga:pkg/server/config/config.go:27-28`), 100 tuples per write
(`:19`), 50 checks per batch (`:76`). Supabase chunks its own lookups at
`MAX_OBJECTS_PER_LOOKUP_BATCH` (`storage:src/storage/object.ts:817-830`;
`storage:src/storage/limits.ts:22`).

*The new constraint.* If vfs ever layers Oracle VPD as defence-in-depth,
the compiled predicate is a string with a 4,000-byte budget by default.
An app-level predicate carries no such limit but is bound-parameter
limited instead (SQL Server ~2,100, Oracle's 1,000-element `IN`), so the
subject-set and grant-prefix terms must be shipped as bounded literals
or as `EXISTS` over a table, never as an enumerated list. S1 measures
which.

## Q12. Take, adapt, reject

See the table after Q13.

## Q13. Many subjects at once: conjunctive authority

**Verdict: supports the multiplayer intersection rule.** One system ships
it as an operator with exact semantics; three others supply the
component rules; none supplies ownership or audit for a set.

*SpiceDB's intersection arrow is the rule, executable.* Syntax
`relation.all(permission)`; the parser accepts only `any` and `all`
(`spicedb:pkg/schemadsl/parser/parser.go:656-692`), `any` being the plain
arrow. Documented semantics: "intersection arrow requires that all
subjects found on the left side of the arrow have the requested
permission/relation", so in `permission view = group.all(member)` "the
user must be in the member relation for all groups defined on the group
relation of a document" (SpiceDB schema docs). The evaluator
`checkIntersectionTupleToUserset`
(`spicedb:internal/graph/check.go:802-939`):

1. loads every `resource#relation` tuple (`:820-838`);
2. **returns no members if there are none** (`:842-844`): the empty set
   denies, it is not vacuously true;
3. dispatches the right side with `REQUIRE_ALL_RESULTS`, no early exit
   (`:849-867`);
4. per resource, requires every subject to be a member and breaks on
   the first miss (`:904-929`);
5. ANDs the caveats of each subject's membership and of the starting
   tuple into one conditional result (`:918-935`;
   `spicedb:internal/graph/membershipset.go:132-152`).

Constraints: the left relation must be a relation, not a permission
(`spicedb:pkg/schema/typesystem_validation.go:139-143`); it may not admit
a wildcard, transitively (`:145-162`); the reachability graph marks the
result conditional (`spicedb:pkg/schema/reachabilitygraphbuilder.go:113-118`),
so LookupResources shears through Check (Q3) and, unlike plain arrows,
without check hints ("TODO(jschorr): use check hints here",
`check.go:808`). The docs warn: "Intersection arrows can impact
performance since they require loading all results for the arrow"
(schema docs). The maintained steel-thread test composes it with
exclusion over a recursive hierarchy,
`permission view = container.all(member) - banned`
(`spicedb:internal/services/steelthreadtesting/testdata/document-with-intersect-arrow.yaml:1-15`),
and the caveated variant supplies context for two caveats through the
arrow (`spicedb:internal/services/integrationtesting/testconfigs/caveatedintersectionarrow.yaml:1-45`).

Mapped onto plan §1.1: the `subjects` relation on a *session* object is
the subject set; `permission read = subjects.all(read_on_entry)` is the
read law; a member added to the relation narrows the very next Check
because the tuple set is read live (`:820-838`), which answers the
mid-session question with "immediately"; an empty set denies, which is
the safe default for a session with no principal.

*OpenFGA: intersection is static only.* `and` intersects named operands
(`openfga:internal/graph/check.go:222-286`, at least two, boolean, no
condition propagation); `X from Y` is existential by definition ("for
each one of them evaluates the computed userset", `:860-861`). There is
no way to say "all members of the set". Its ListUsers does compute an
intersection by counting operands per user, `count + wildcardCount ==
len(childOperands)` (`openfga:pkg/server/commands/listusers/list_users_rpc.go:564-676`),
which is the `HAVING COUNT(DISTINCT principal) = n` shape S1 will test.

*Postgres restrictive policies AND, but across policies, not
principals.* "all the PERMISSIVE policy expressions are combined using
OR, all the RESTRICTIVE policy expressions are combined using AND, and
the results are combined using AND. If there are no PERMISSIVE
policies, then access is denied"
(`postgres:doc/src/sgml/ref/create_policy.sgml:681-691`); "there needs to
be at least one permissive policy to grant access to records before
restrictive policies can be usefully used" (`:151-158`). A subject set
could be expressed as one restrictive policy per principal only if the
set were known at policy-definition time, which a session's is not; the
right vfs analogue is a single predicate with the set as data.

*django-guardian's all-perms is a conjunction of rights for one user.*
With `any_perm=False` and several permissions, "the intersection of
matching object is returned" (`django-guardian:guardian/shortcuts.py:592`).
Two implementations coexist. When no global permission is mixed in,
guardian pulls every `(object_pk, codename)` row for the user and the
user's groups into Python, groups by object, keeps the objects where
`codenames.issubset(obj_codenames)`, and filters
`queryset.filter(pk__in=pk_list)` (`:741-752`): a materialised list, so
the `IN` grows with the number of qualifying objects. When a global
permission is mixed in, it instead annotates a count per object and
keeps `object_pk_count__gte=len(codenames)` (`:755-757`): the
`HAVING COUNT` shape inside the database. Only the second survives
vfs's `IN`-list budget, and it is the same shape S1 tests for a subject
set with the roles of principal and permission swapped: guardian asks
"does one user hold all n permissions", vfs asks "do all n principals
hold one permission".

*Casbin: BLP is the lattice, but the caller computes the meet.* The BLP
matcher is `(r.act == "read" && r.sub_level >= r.obj_level) || (r.act ==
"write" && r.sub_level <= r.obj_level)`
(`casbin:examples/blp_model.conf:14`, tests `casbin:blp_test.go:33-53`):
no read up, no write down. Biba is the exact dual
(`casbin:examples/biba_model.conf:14`). The "lowest clearance in the room"
rule is `sub_level = min(levels)` supplied by the caller in the request;
Casbin has no multi-subject entry point, `BatchEnforce` returns one
boolean per independent request (`casbin:enforcer.go:966-976`, test
`casbin:enforcer_test.go:509-513`), and `IN` over a slice is existential
(`casbin:abac_test.go:80`). The `[constraint_definition]` section
(`sod`, `sodMax`, `roleMax`, `rolePre`) constrains role assignment at
load time, not requests (`casbin:model/constraint.go:32-55`). Note that
BLP's write rule is *not* the meet: under "no write down" the lowest
member may write where the highest may not, so a set acting at the
lowest clearance can read the least and write the most. The plan's rule
(intersection for both read and write) is stricter than BLP and matches
Biba's read direction; neither classical model gives intersection on
both axes, which is why the plan's rule needs its own justification.

*Cedar's forbid gives the hide rule.* Because any satisfied forbid
denies regardless of permits
(`cedar:cedar-policy-core/src/authorizer/partial_response.rs:128-130`), a
set evaluated as "one forbid per member who cannot see" yields "hidden
if hidden from any member" with no new mechanism. Partial evaluation
returns `None` when a forbid is residual ("that forbid may evaluate to
true, overriding any permits", `:132-133`), the right answer for a set
whose membership is not yet known.

*Ownership, audit and mid-session change for a set.* No precedent for
ownership: the id systems have no owner concept beyond a tuple, and
Supabase stamps whatever `owner` the caller passes (Q7). No precedent
for auditing a set: every engine names one principal. Mid-session
change has the SpiceDB precedent above (immediate, because the set is
read per query) and the Zanzibar caution (a token is needed to make
"immediate" mean the same thing on every replica, Q8).

---

## Take, adapt, reject for vfs

| Item | Verdict | One line |
|---|---|---|
| Policy compiled into the query at one chokepoint | **take** | VPD, SQL Server, RLS, Oso, OPA, Cedar all do it; ADR 021 D3 stands |
| Reads filter, writes check, as two distinct clauses | **take** | `USING`/`WITH CHECK`, `FILTER`/`BLOCK`, `update_check`; keep spec 058's split and add the `RETURNING` exception: a write that returns the row must raise, never silently drop |
| Path prefix as the grant coordinate, no materialised prefix table | **take** | Supabase built `prefixes` and removed it for an on-the-fly derivation over the `COLLATE "C"` index |
| Intersection arrow semantics for the subject set | **adapt** | empty set denies; every member must hold the right; conditions AND; the set is read live per query; expect listing to cost more than checking |
| `SESSION_USER` / `CURRENT_USER` pair in the audit | **adapt** | record actor and subject as two columns the way Postgres exposes two identities; no engine records the pair, so the shape is ours |
| Zookie for content-change checks | **adapt** | stamp each version row with the grant revision in force; a revert is a new write under current grants |
| Statistics leak rule | **adapt** | idf and `lexical_stats` must be computed over the visible set or marked as a deliberate, measured leak (S2) |
| Error-message suppression under row grants | **take** | no key values, no `errdetail`, echo only caller-supplied columns; map hidden to not-found and refused-write to denied, as Supabase does |
| Dry-run write as the point check | **adapt** | Supabase's `testPermission` executes the `UPDATE` and rolls back; usable for `move` on engines where the predicate is app-level, if the second half runs in the same transaction |
| `system()` as a bypass | **take, guarded** | every database bypasses for a named role; add Postgres's `row_security = off` idea: a mode that errors if a policy would have filtered, for backups and audits |
| Statement cache keyed by principal | **take** | the baked-query bypass |
| Tuple-level deny | **reject** | already rejected in ADR 021; reconfirmed by every engine here (deny is a policy construct) |
| Groups enumerated into literals | **reject** | Oso's shape breaks the `IN`-list budget; resolve membership with `EXISTS` or a join |
| Recursive CTE for ancestry | **reject** | Oso cannot recurse, Zanzibar walks per query with a depth cap; a prefix `LIKE` or an ancestor list is bounded |
| Casbin-style label model for the set | **reject** | BLP's write rule is not the meet; the plan's intersection on both axes needs its own ADR |
| Wall-clock deadline on listing | **reject for now** | OpenFGA's 3-second cap is a service decision; a library returns a bounded page and a cursor instead |

## Limits

- Two Oracle pages returned 404 (the VPD concepts chapter at 19c and
  23ai); Oracle facts here come from the `DBMS_RLS` package reference
  only. `CLIENT_IDENTIFIER` and proxy authentication are not cited and
  are left out of Q1's evidence.
- The Zanzibar paper was read through AuthZed's annotated copy, not the
  USENIX PDF (403). Section numbers follow the paper.
- Cedar's partial evaluation was read from the clone and RFC 0095; the
  docs site has no partial-evaluation page. The feature is marked
  experimental in-tree (`cedar:cedar-policy/experimental_warning.md`).
- The Postgres tree is 19-devel, not a release; the RLS and planner
  facts cited are long-standing, but `all_rows_selectable()`
  (`postgres:src/backend/utils/adt/selfuncs.c:6382-6414`) is new.
- Oso is deprecated upstream; its two data-filtering generations coexist
  and the legacy `sqlalchemy-oso` path emits correlated `EXISTS` where
  the new one emits joins (`sqlalchemy_oso/partial.py:314-333`). Cited as
  design reading, not as a maintained reference.
- ADR 021's OpenFGA citation has drifted: `typesystem.go:628-629` is now
  inside a weighted-graph walk; the "but not" example is at
  `openfga:pkg/typesystem/typesystem.go:671-672`. The SpiceDB citations
  still resolve.
- Nothing was executed. Every performance claim is a documented limit or
  a code path, not a measurement; S1 and S2 own the numbers.
