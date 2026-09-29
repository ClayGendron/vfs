# Groups in the permission spine: max within each subject, min across the set

- **Status:** research memo. Answers Clay's question Q2 (2026-09-28).
  Commits us to nothing. Feeds spec 058 (§1 rows, §3 resolver, §8
  group administration, §11 budgets) and spec 149 (the `groups` claim
  marker).
- **Date:** 2026-09-28
- **Owner:** Clay Gendron
- **Question** (Clay, 2026-09-28): "I am thinking group is similar to
  other principals so it can stack nicely (we can also look up the
  groups attached to a user principal) but unlike multiplayer with a
  group chat acting on many principals where we take the min permission
  option, we should also be able to take the max permission option.
  Let's say Ann is in 3 different groups. We should get Ann's groups
  and present files that any of them have access to. This gets
  complicated when we have Ann and John who are each attached to their
  own groups, we need to find the max for each user, but then the min
  of them combined to act on both of them. Determine if this edge case
  is in or out of scope."
- **Method:** (1) a line-by-line re-read of spec 058, ADR 062, 063,
  064, 066, 067, `src/vfs/authority.py`, the five lens memos of
  2026-09-05 and study S1 (its scripts, not only its tables), to check
  what is already decided; (2) three read-only source studies (Unix and
  Plan 9; Postgres, SpiceDB, OpenFGA, Jackrabbit Oak, Gel, AGE) and one
  web study, each claim cited; (3) an executed model of the resolver
  with groups, in
  `studies/2026-09-28-group-permissions/` (`README.md`, `model.py`,
  `results.md`): a pointwise oracle against the prefix algebra on 3,000
  random worlds, the compiled predicate run on SQLite, a budget sweep
  to 64 subjects and 50 groups each, and a SQLite parse-limit probe.
  No Docker; no engine timing (S1 already has it). Cites and
  describes only; no code copied.
- **Sources:** refreshed to `origin/HEAD` on 2026-09-28, licenses
  re-checked after the refresh: `authzed/spicedb` @ `9145a33`
  (2026-09-24, Apache-2.0); `openfga/openfga` @ `97943bf` (2026-09-28,
  Apache-2.0); `postgres/postgres` @ `cc053b6e` (2026-09-28, PostgreSQL
  licence, `COPYRIGHT`); `apache/age` @ `fa109ef` (2026-09-18,
  Apache-2.0); `geldata/gel` @ `8519106` (2025-12-23, the upstream
  `master` head, Apache-2.0); `apache/jackrabbit-oak` @ `1480ff8`
  (2026-09-28, `trunk`, Apache-2.0). Read as found, not refreshed by
  this study (another session owns them): `linux` @ `faeab1661`
  (2026-04-18, GPL-2.0); `freebsd-src` @ `2e33355ee2bf` (2026-09-05,
  BSD-3-Clause in the files read); `plan9` @ `ed1a9c21e` (2025-10-28,
  MIT); `plan9port` @ `b6564bd9` (2026-08-26, MIT); `unix-history-repo`
  @ `e005199` (V7 snapshot, Caldera licence). Web pages, all read
  2026-09-28, listed inline where cited.

## Terms used below

- **Subject.** A person (or service) whose grants apply to a call.
  `Authority.subjects` holds one or more.
- **Subject set.** The subjects of one call. Ann alone is a set of one.
  Ann and John together are a set of two.
- **Group.** A named bundle of principals. A grant can name a group.
  Every member then holds that grant.
- **Closure.** All groups a principal reaches, directly or through
  nested groups. If Ann is in `platform`, and `platform` is in `eng`,
  Ann's closure is `{platform, eng}`.
- **Level.** One of `invisible < read < read_write`. It is a ladder:
  holding `read_write` means you also hold `read`.
- **Max within.** For one subject, the best level over every row that
  applies to them: their own grants, their groups' grants, the everyone
  (`*`) row, and the owner floor.
- **Min across.** For a subject set, the worst of the members' levels.
  This is ADR 066's intersection law.
- **Covering prefix set.** For one subject and one level, the smallest
  list of folder prefixes under which that subject holds at least that
  level.
- **Meet.** The prefix set whose coverage is the overlap of several
  covering sets. It is how the resolver computes "min across" on
  folders instead of on rows.
- **Arm.** One `path = :p OR path LIKE :p || '/%'` clause in the
  compiled `WHERE`. Two binds per arm.
- **Bind.** One `?` parameter in a SQL statement. Engines cap them:
  SQL Server at about 2,100 per statement, Oracle at 1,000 elements per
  `IN` list.

## Bottom line

1. **Clay's Ann + John case is in scope.** It is already decided. It is
   not an edge case either: it is the normal path of the resolver.
   Spec 058 §2 says a subject's level is "the **maximum** over all
   covering rows, its own and its groups'". Spec 058 §3 steps 1 to 3
   read each subject's rows and its groups' rows, build each subject's
   covering set, then take "the **meet**" across the set. ADR 067 rule 2
   says the same. So: max within each person, then min across the
   people. That is exactly Clay's rule.
2. **The algebra is exact.** The model checked it against a direct
   per-row computation on 3,000 random worlds with nested groups,
   group cycles, posture rows and awkward path characters: zero
   disagreements, and the compiled SQL on SQLite agreed row for row
   (numbers in §3).
3. **There are two easy ways to get it wrong, and both are measured.**
   Pooling every member's groups into one bag leaks: John gets Ann's
   `security` group. Dropping the owner floor for sets hides rows the
   rule says are visible. Spec 058 §3 step 4 as written does the second
   one (§4).
4. **Cost stays inside budgets with one exception.** The literal
   predicate stays small because the meet shrinks as the set grows. The
   exception is the `EXISTS` fallback: the spec says it is "bounded by
   one bind", but once groups are in it needs every member's group ids
   as binds. At 64 members with 50 groups each that is about 4,700
   binds, more than twice SQL Server's cap (§5).
5. **The spec needs seven small tightenings**, listed in §12. None
   changes a decision. Two are group-specific holes worth fixing before
   implementation: user and group names can collide (§8), and the lean
   for group admin (a `read_write` grant on `/_groups/<id>`) is open to
   everyone under the default `open` posture (§10).
6. **Precedent.** Union within a principal is universal (Postgres,
   SpiceDB, OpenFGA, Windows, AWS, Google Drive, SharePoint, Plan 9).
   Union within, then intersection across independent sets, has exact
   precedents between *layers* (Windows restricted tokens, AWS
   permission boundaries and session policies, Oak's composite `AND`,
   Postgres restrictive row policies). Nobody ships it across several
   *people*: the products fall back to the asker (Teams Copilot,
   Slack AI) or filter per viewer (Glean). ADR 066 already knew this;
   this memo confirms it held up to 2026-09-28.

## 1. What the spec and ADRs already say

The question is whether the text already covers "max within, min
across". It does, in five places.

| Where | Text | What it decides |
|---|---|---|
| spec 058 §1 | "`principal_id` is a `sub` (070) or a group id" | a grant can name a group |
| spec 058 §1 | "`memberships(principal_id, group_id)`, resolved per statement … Nested groups are walked in app code to a declared depth `MAX_GROUP_DEPTH`" | where groups come from; nesting is bounded |
| spec 058 §2 | "A subject's level on a path is the **maximum** over all covering rows, its own and its groups'" | max within one subject |
| spec 058 §3 steps 1–3 | read "every subject's grant rows and its groups' rows"; "Per subject, compute the covering prefix set"; "For a set, compute the **meet**" | the per-subject union comes first; the meet is taken across subjects |
| ADR 067 rule 2 | "read the grant rows of every subject and of every group each subject belongs to … compute … the *covering prefix set* … and for a subject set the *intersection* of the members' covering sets" | the same rule, ratified |
| ADR 066 rule 2 | "a row is readable iff readable by every member, writable iff writable by every member" | min across the set |
| synthesis memo, Q6 | "groups widen a *principal's* rights everywhere (union), which is fine inside one subject's grants and forbidden across subjects, exactly the algebra Landlock uses (union within a layer, intersection across layers)" | the reasoning behind it |

So the rule Clay describes was ratified on 2026-09-06. What was *not*
checked until now: whether the resolver's shape computes it exactly,
whether its budgets hold once groups make each person's covering set
larger, and four details the text leaves open (naming, membership
source, group admin, nesting). This memo does that.

One gap in the evidence: study S1 measured subject sets and groups
**separately**. Its subject-set probe (`probe.py`, `p_set_app`) builds
each member's covering set from direct and everyone grants only
(`corpus.prefixes_of` reads `grant_flat`). Groups were a separate probe
for one principal. The combined case, sets whose members each have
groups, was never run. §5 fills that gap for size; S1's timings still
apply because the SQL shape is the same, only the arm count moves.

## 2. The worked example

Posture: private root (`*` at `/` is `invisible`), and `/public` shared
for reading. Groups:

- Ann is in `platform`, `security`, `design` and `ops`. `platform` is
  itself in `eng`, so Ann reaches `eng` through nesting.
- John is in `eng` and `sales`.

Grants:

| principal | prefix | level |
|---|---|---|
| `group:eng` | `/eng` | read_write |
| `group:security` | `/vault` | read |
| `group:design` | `/design` | read_write |
| `group:ops` | `/ops` | read |
| `group:sales` | `/sales` | read_write |
| `ann` | `/sales` | read |
| `john` | `/design` | read |
| `john` | `/home/ann/shared` | read |

Ann owns `/home/ann/diary.md` and `/home/ann/shared/plan.md`.

The model prints this table (section 1 of `results.md`). "Ann" and
"John" are each person's **max** over their own rows, their groups'
rows, the everyone row and the owner floor. "Ann + John" is the **min**
of the two.

| path | Ann (max) | John (max) | Ann + John (min) | groups pooled across the set (wrong) | owner floor only for a set of one (wrong) |
|---|---|---|---|---|---|
| `/design/mock.png` | read_write (design) | read (own grant) | **read** | read_write (LEAK) | read |
| `/eng/specs/api.md` | read_write (eng via platform) | read_write (eng) | **read_write** | read_write | read_write |
| `/home/ann/diary.md` | read_write (owner) | invisible | **invisible** | invisible | invisible |
| `/home/ann/shared/plan.md` | read_write (owner) | read (own grant) | **read** | read | invisible (over-hidden) |
| `/ops/runbook.md` | read (ops) | invisible | **invisible** | read (LEAK) | invisible |
| `/public/readme.md` | read (everyone) | read (everyone) | **read** | read | read |
| `/sales/deals.csv` | read (own grant) | read_write (sales) | **read** | read_write (LEAK) | read |
| `/vault/keys.md` | read (security) | invisible | **invisible** | read (LEAK) | invisible |

Reading the table, one row at a time:

- `/design/mock.png`: Ann's best is `read_write` through `design`.
  John's best is `read`, from his own grant. The pair gets the lower
  one: `read`. The session can show the mockup but not change it.
- `/sales/deals.csv`: the mirror image. Ann holds `read`, John holds
  `read_write`. The pair gets `read`.
- `/vault/keys.md` and `/ops/runbook.md`: only Ann can see them. The
  pair cannot. John must not learn they exist.
- `/home/ann/shared/plan.md`: Ann owns it, so her floor is
  `read_write`. John was given `read`. The pair gets `read`.

What the resolver ships for the pair (from the model):

- at `read`: arms `/public`, `/design`, `/eng`, `/sales`, plus two
  owner arms (`owner_id = ann AND under /home/ann/shared`; `owner_id =
  john AND under /ops, /vault`): 16 binds;
- at `read_write`: arm `/eng`, plus owner arms (`ann` under `/sales`,
  `john` under `/design`): 8 binds.

## 3. Why "max then min" can be computed on folders, and the check

The rule is stated per row: for each path, take each person's max,
then the min over the people. The resolver does not look at rows. It
looks at folders (prefixes) and runs once per level. Why is that the
same thing?

Because the levels form a ladder. "The pair holds at least `read` here"
means "every member holds at least `read` here". And "Ann holds at
least `read` here" means "at least one of Ann's rows, or her groups'
rows, grants `read` or better on a folder above this path". So:

- The union of Ann's own and group rows **at a level** is her covering
  set at that level. That is the max, one threshold at a time.
- The overlap of the members' covering sets is the meet. That is the
  min, one threshold at a time.

Doing it per threshold is exact. It is a standard trick: a min of maxes
over a ladder equals the answer you get by asking "at least `read`?"
and "at least `read_write`?" separately.

Two terms sit outside the prefix algebra and need their own arms:

- **The everyone rows (`*`).** They are the same for every member, so
  they factor out: min over members of max(everyone, member) equals
  max(everyone, min over members). The compiler emits them once, beside
  the meet, with `NOT LIKE` holes for lower `*` rows below them.
- **The owner floor.** It is per member. A row Ann owns is visible to
  the pair when every *other* member covers it. So each member gets one
  owner arm: `owner_id = :member AND cover(meet of the others)`. S1's
  shape (c) already compiles it that way. The model trims each owner
  arm to the folders the shared arms do not already cover, and drops
  the arm when nothing is left.

The executed check (`results.md` §2): 3,000 random worlds, sets of one
to five members, nested groups (including cycles), posture rows with
private and shared children, and path names containing `%` and `_`.
That is 454,796 (world, set, path, level) checks. The resolver
disagreed with the per-row oracle **0 times**. The compiled `WHERE`,
run on SQLite, disagreed **0 times**.

## 4. The ways to get it wrong

The model runs four wrong variants next to the right one, on the same
worlds.

| Variant | What it does | Result on the random worlds | Worked example |
|---|---|---|---|
| **Groups pooled across the set** | Collect every member's groups into one bag, give each member the whole bag, then meet | 16,746 rows shown that some member cannot see (leaks) | John inherits Ann's `security`, `design` and `ops`; Ann inherits John's `sales`: four leaks |
| **Owner floor only for a set of one** (spec 058 §3 step 4 as written: "`owner_subject` is set only for a set of one") | Drop the owner floor whenever the set has two or more members | 369 rows hidden that every member may see; no leaks (fails closed) | `/home/ann/shared/plan.md` disappears for the pair although both members may read it |
| **Posture holes only on the nearest `*` row** | Attach a lower `*` row as a `NOT LIKE` hole only to its nearest `*` ancestor | 30 leaks | (not in the example) an open root with a shared `/a` and a private `/a/b` shows `/a/b` through the root's arm |
| **Root prefix compiled literally** | Emit `path LIKE '/' || '/%'`, that is `LIKE '//%'`, for the `/` prefix | 220,865 rows hidden that should be visible | a group or posture grant at `/` admits nothing but the root itself |

The first is the one Clay's question is really about. It is the
tempting shortcut: "get everyone's groups, then intersect". It is
wrong because group membership belongs to a person, not to the room.
The union must be finished **inside each person** before the meet
starts. The spec's wording ("its groups'") already says this; step 1
should say "per subject, never pooled" in so many words.

The second is a contradiction inside spec 058 today. §2 says the owner
floor "applies per member inside a set (ADR 064 rule 4)". §3 step 4
says `owner_subject` exists only for a set of one, and `ResolvedRights`
has no field for per-member owner arms. It fails closed, so it leaks
nothing. But it hides rows the ratified rule says the pair may see,
and it makes a person's own files vanish the moment they join a room.
S1 timed the per-member form (its shape (c) includes the owner
disjuncts), so fixing the spec costs no new measurement.

The last two are not about groups, but the executed SQL found them and
they bite the everyone row, which is the one group every principal is
in (Postgres calls it `PUBLIC`, Oak `EveryonePrincipal`).

## 5. Cost at scale

The sweep (`results.md` §3) uses an S1-shaped grant corpus: 2,000
users with 5 direct grants each, 300 team groups with 5 grants each
(270 of them nested one level under 30 parents), an all-hands group
with two grants, a private root and five shared top-level folders. It
draws random subject sets of 1, 2, 5, 20 and 64 members, where every
member is in 0, 3, 10 or 50 teams plus all-hands.

Selected columns (the full table is in `results.md` §3; level `read`;
20 random sets per cell; "fallback" is the per-member `EXISTS` with
each member's id list):

| members | groups each | ids fetched | walk statements | folders per member | meet arms | literal binds (median / max) | fallback binds (median / max) | fallback over SQL Server's 2,099 |
|---|---|---|---|---|---|---|---|---|
| 1 | 0 | 3 | 2 | 7 | 7 | 25 / 25 | 4 / 4 | 0 of 20 |
| 2 | 0 | 4 | 2 | 7 | 2 | 36 / 36 | 8 / 8 | 0 of 20 |
| 64 | 0 | 66 | 2 | 7 | 2 | 14 / 14 | 256 / 256 | 0 of 20 |
| 1 | 10 | 21 | 3 | 56 | 56 | 123 / 139 | 22 / 24 | 0 of 20 |
| 2 | 10 | 37 | 3 | 52 | 22 | 195 / 232 | 44 / 47 | 0 of 20 |
| 20 | 10 | 183 | 3 | 54 | 6 | 40 / 64 | 429 / 443 | 0 of 20 |
| 64 | 10 | 335 | 3 | 54 | 3 | 20 / 45 | 1,387 / 1,405 | 0 of 20 |
| 1 | 50 | 72 | 3 | 128 | 128 | 268 / 287 | 73 / 78 | 0 of 20 |
| 2 | 50 | 116 | 3 | 126 | 88 | 394 / 458 | 147 / 153 | 0 of 20 |
| 5 | 50 | 197 | 3 | 128 | 60 | 217 / 269 | 367 / 376 | 0 of 20 |
| 20 | 50 | 315 | 3 | 127 | 32 | 128 / 146 | 1,467 / 1,484 | 0 of 20 |
| 64 | 50 | 366 | 2 | 127 | 24 | 103 / 122 | 4,697 / 4,750 | **20 of 20** |

What the numbers say, in plain words:

- **Reading the rows is cheap.** The resolver fetches the grant rows of
  every subject and every group in their closures. Even at 64 members
  with 50 groups each, that is a few hundred distinct ids: one `IN`
  statement on Oracle (cap 1,000) and on SQL Server (cap 2,000). The
  membership walk is one statement per nesting level, so two or three.
  Both are chunked by `membership_budget` anyway, so there is no cliff.
- **Groups make each person's covering set bigger.** With 50 groups a
  person covers well over a hundred folders instead of about seven.
- **The meet makes the set's predicate smaller.** The more people, the
  fewer folders they all share. At 64 members the literal predicate is
  smaller than at 5. This is S1's finding, and it survives groups.
- **The owner arms are the costly part for small sets.** For two
  people, each owner arm carries the part of the *other* person's
  covering set that the shared arms do not already cover. That makes a
  pair about 1.5 times the binds of one person (394 against 268 at 50
  groups). The largest literal in any sampled cell is 458 binds, far
  inside SQL Server's 2,099.
- **The fallback is the one that breaks.** Spec 058 §3 step 4 says the
  `EXISTS` fallback is "bounded by one bind". That is true for a person
  with no groups. With groups, each member's `EXISTS` must list that
  member's ids (`principal_id IN (:sub, :g1, …)`), because ADR 067
  forbids the membership subquery (S1: 35 s on Postgres, 188 s on
  MariaDB). The binds then grow with members times groups. At 64
  members with 50 groups each it needs about 4,700 binds, over SQL
  Server's 2,099 in every sample. So the fallback, the thing that is
  meant to be safe when the literal is too big, is the thing that
  breaks.

A second budget finding, from executing the predicate
(`results.md` §4): SQLite 3.50.4 parses the literal predicate up to **998 arms** (1,996 binds); 999 do not (a direct try at 1,000 arms fails with "Expression tree is too large (maximum depth 1000)"). Spec 058 derives `MAX_PREFIX_ARMS`
from binds alone, `(parameter_budget − other binds) // 2`. On SQLite
that is about 16,300 arms, sixteen times what SQLite will parse. The
reason is the expression-depth cap (`SQLITE_MAX_EXPR_DEPTH`, 1,000):
a long `OR` chain is a deep tree. `dialects.py` already models this
as `expression_depth_budget` and caps glob fans through `arm_budget`
(200 arms, "the measured OR-fan sweet spot"). The prefix cap should be
derived the same way. With groups this is not theoretical: a pair at
50 groups each already ships about 200 arms, and a person with a
heavier grant set than the sweep's five per team would pass SQLite's
998.

**The fix for the fallback** that keeps one bind: stage the resolved
arms, not the visibility. Write the meet's prefixes (and the owner arms)
once per `(authority fingerprint, grant_revision)` into a small keyed
table, and let the fallback be one correlated `EXISTS` against it with
a single bind for the key. This is the shape S1 called "flat expanded
(`EXISTS` over `grantgx`)": one bind, and the fastest of the three group
encodings on every engine (Postgres grep pass 43.5 ms against 109 ms
for the literal group list). It is not the rejected materialised
visibility table: it holds a few hundred prefixes per authority, not
one row per visible entry. The memo key ADR 067 rule 7 already names
is its key. A declared cap on groups per principal is the other way
out, and it is the wrong one: CLAUDE.md forbids designing toward a
scale cap no engine imposes.

## 6. Precedent: a group stacks onto a person (max within)

**Almost every system unions a person's own rights with their groups'.**
The interesting cases are the ones that do not.

- **Unix does not take the max across owner, group and other.** It
  picks exactly one class, in order. Linux: "Are we the owner? If so,
  ACL's don't matter"; the owner is checked against the owner bits
  only and the function returns (`linux:fs/namei.c:461-467`); a group
  member is checked against the group bits only (`:484-488`); one class
  decides (`:491`). FreeBSD's `vaccess` is the same, with the comment
  "check the groups (first match)"
  (`freebsd-src:sys/kern/vfs_subr.c:5680-5718`). V7 shifts the mode
  once for non-owners and again for non-members, then tests one class
  (`unix-history-repo:usr/sys/sys/fio.c:164-170`). So an owner whose
  owner bits say no is refused even when "other" says yes.
- **Unix does union across groups.** A process belongs to all its
  supplementary groups at once: `in_group_p` is true on the fsgid or
  any supplementary hit (`linux:kernel/groups.c:227-235`), a binary
  search over a sorted array (`:92-111`); FreeBSD `groupmember` the same
  (`freebsd-src:sys/kern/kern_prot.c:1811-1820`). Caps: 65,536 groups
  on Linux (`linux:include/uapi/linux/limits.h:7`), 1,023 on FreeBSD
  (`freebsd-src:sys/sys/syslimits.h:56`).
- **POSIX ACLs union group entries, but per entry.** Among the owning
  group and named groups, access is granted if *one* matching entry
  holds all the requested bits (`linux:fs/posix_acl.c:399-415`;
  FreeBSD's comment: "Group match is best-match, not first-match",
  `freebsd-src:sys/kern/subr_acl_posix1e.c:220-269`). Read from one
  group plus write from another does not add up to read-write. vfs's
  levels are a ladder, so "the best single row" and "the union of rows"
  are the same thing; the distinction does not arise.
- **Plan 9 takes the OR, the opposite of Unix.** "When the owner
  attempts to do something to a file, the owner, group, and other
  permissions are consulted, and if any of them grant the requested
  permission, the operation is allowed" (`plan9:sys/man/5/0intro:555-560`);
  fossil implements it one bit at a time
  (`plan9:sys/src/cmd/fossil/9p.c:37-58`). So Plan 9 is a true max
  within a person. Its groups do **not** nest: `_groupMember` scans a
  flat list (`plan9:sys/src/cmd/fossil/9user.c:140-161`).
- **Postgres ORs privilege bits over the whole role closure.**
  `aclmask` ORs in the entries of the user and `PUBLIC`, then every ACL
  entry whose grantee the user "has privileges of"
  (`postgres:src/backend/utils/adt/acl.c:1466-1497`). The closure is a
  cached breadth-first walk of `pg_auth_members` that follows only
  inheritable grants (`roles_is_member_of`, `acl.c:5187-5306`, the
  `inherit_option` skip at `:5261`). There is no deny.
- **SpiceDB and OpenFGA union group usersets.** SpiceDB dispatches every
  `group:eng#member` subject on a relation and unions the results
  (`spicedb:internal/graph/check.go:452-500`, `union` at `:1073-1117`);
  OpenFGA's `union` returns on the first allowed child
  (`openfga:internal/graph/check.go:160-219`). Zanzibar states the
  model: "Groups can contain other groups" and userset rewrites combine
  "by operations such as union, intersection, and exclusion" (USENIX
  ATC '19, https://www.usenix.org/system/files/atc19-pang.pdf, pp. 34,
  36).
- **Windows** puts the user SID and "SIDs for the groups of which the
  user is a member" in one token and matches every ACE against all of
  them (https://learn.microsoft.com/en-us/windows/win32/secauthz/access-tokens;
  …/how-dacls-control-access-to-an-object).
- **AWS IAM:** "If multiple policies apply to a request, AWS applies a
  logical `OR`"; "Any user in that user group automatically has
  *Admins* group permissions"
  (https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html;
  …/id_groups.html).
- **Google Drive:** a direct grant "more permissive than the role
  granted through their membership … becomes the *effective role*";
  and a removed user "can still open the file if they are part of a
  group with access"
  (https://developers.google.com/workspace/drive/api/guides/manage-sharing;
  https://support.google.com/drive/answer/14254362).
- **SharePoint:** access comes "directly through an individual role
  assignment, or indirectly through membership in either a domain group
  or a SharePoint group", and roles on one object accumulate
  (https://learn.microsoft.com/en-us/sharepoint/dev/general-development/authorization-users-groups-and-the-object-model-in-sharepoint).
- **The exception: Jackrabbit Oak orders users before groups, with
  deny.** User entries are evaluated before group entries and the first
  decision on a privilege bit wins
  (`jackrabbit-oak:oak-core/.../permission/CompiledPermissionImpl.java:356-376`,
  `:435-445`; documented: "user principals always take precedence over
  group principals",
  `oak-doc/src/site/markdown/security/permission/evaluation.md:32-43`).
  That ordering only matters because Oak has deny entries. vfs grants
  are additive-only (ADR 021, 067), so there is nothing for an order to
  decide, and the max is the whole answer.

For vfs: Clay's "max within" is the field's default, and Plan 9 and
Postgres are the clean versions of it. Unix's first-match is the one
counterexample, and it exists because Unix classes can *deny* (a
`rwx---rwx` file refuses its group). vfs has no deny rows, so it takes
Plan 9's rule, not Unix's.

## 7. Precedent: union within each, intersection across (the combined case)

Clay's combined rule has two layers: a union inside each party, then an
intersection across the parties. The field has this shape, but always
between **layers of one principal**, never across several people.

| System | The unioned sets | The intersection | Source |
|---|---|---|---|
| Windows restricted tokens | the token's enabled SIDs (user plus groups); the restricting SIDs | "the system performs two access checks … Access is granted only if both access checks allow the requested access rights" | https://learn.microsoft.com/en-us/windows/win32/secauthz/restricted-tokens |
| AWS permission boundaries | identity policies (user plus its groups, OR'd); the boundary | "the resulting permissions are the intersection of the two categories" | https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html |
| AWS session policies | the role's identity policies; the session policy | "The permissions for a session are the intersection of the identity-based policies … and the session policies" | https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html |
| AWS SCPs and RCPs | the principal's policies; the organisation's | "an action must be allowed by all three policy types" | reference_policies_evaluation-logic.html |
| Microsoft delegated permissions | the app's granted scopes; the user's rights (including via groups) | "there's an intersection between what the user is allowed to do and what the application is allowed to do" | https://learn.microsoft.com/en-us/security/zero-trust/develop/developer-strategy-delegated-permission |
| Jackrabbit Oak composite authorization | each configured model's grants | `AND` (the default): "Break as soon as any one of the aggregated permission providers denies" | `jackrabbit-oak:oak-core/.../composite/CompositeAuthorizationConfiguration.java:82-110` |
| Postgres row security | permissive policies OR'd | restrictive policies AND'd on top | `postgres:src/backend/rewrite/rowsecurity.c:79-83` |
| SpiceDB | any userset union | `&` and the intersection arrow `.all()`: every branch, every subject | `spicedb:internal/graph/check.go:539-557`, `:1120-1172`, `:888-900` |

AWS has one caveat worth knowing: a resource policy that names the
session gets "all the permissions of the resource-based policy *plus*
the intersection", so AWS's intersection is not pure (access_policies.html).
vfs's is pure: ADR 062 rule 1 gives the actor nothing.

**Across several people, nobody ships it.** The web study found:

- Microsoft 365 Copilot in Teams group chats: "Responses from Copilot
  are grounded in the data of the person who asks"; when a source is
  "*not* available to all members of the chat", the asker gets a
  private preview to "Approve" or "Reject"
  (https://support.microsoft.com/en-us/teams/chat-channels/how-to-use-microsoft-365-copilot-in-teams-group-chats).
  The asker's union, a leak gate, no intersection.
- Slack AI uses "Slack data that members have access to at the time of
  request", meaning the requester
  (https://slack.com/help/articles/28310650165907-Security-for-AI-features-in-Slack).
- Glean filters per viewer after the fact: "each recipient still only
  sees the sources they're individually authorized to access"
  (https://docs.glean.com/security/security-principles).
- A Cloud Security Alliance post (2026-04-15) *argues* for "the
  intersection of all recipients' permissions before data leaves the
  retrieval layer", and names no product that does it
  (https://cloudsecurityalliance.org/blog/2026/04/15/when-ai-agents-serve-shared-workspaces-authorization-must-follow-the-audience).

So ADR 066's reading still holds on 2026-09-28: the intersection across
people is vfs's own rule, and the union within each person underneath
it is everyone's rule. Composing them is new only in that nobody has
put several humans on the intersection side.

## 8. Naming: a user `eng` and a group `eng`

Spec 058 stores grants and memberships under one `principal_id` column.
`Principal` has no group kind; `sub` is whatever the identity provider
says. So nothing stops a user whose `sub` is `eng` and a group named
`eng`.

That is a real hole, not a style issue. The resolver reads
`principal_id IN (:sub, :g1, …)`. If the user `eng` exists, their `sub`
matches every row granted to the **group** `eng`, whether or not they
are a member. A membership row `(eng, …)` is also ambiguous: is it the
user joining, or the group nesting?

How others avoid it:

| System | Users and groups | How a collision is avoided |
|---|---|---|
| Postgres | one namespace: "there are only roles. Any role can act as a user, a group, or both" (`postgres:doc/src/sgml/user-manag.sgml:18-21`; unique `pg_authid_rolname_index`) | a name is one role; it cannot be two things |
| Plan 9 | one namespace: each `/adm/users` line "defines a user and a group" (`plan9:sys/man/6/users:28-33`) | same: every user *is* a group |
| Unix | two: `/etc/passwd` uids and `/etc/group` gids (`unix-history-repo:etc/passwd`, `etc/group`) | the check knows which space it is asking |
| SpiceDB, OpenFGA | typed objects: `user:ann`, `group:eng#member` (`spicedb:pkg/tuple/structs.go:24-28`; `openfga:pkg/tuple/tuple.go:304`) | the type is part of the id |
| Windows | SIDs, globally unique, with the issuing authority inside | a name is never the key |

vfs cannot copy Postgres or Plan 9. They own their user list. vfs does
not: `sub` comes from someone else's identity provider (070, 149), and
several issuers may one day share a storage. So vfs cannot promise that
no user is ever called `eng`.

**Recommendation: a typed prefix in the one column.** A group id is
stored as `group:<name>` (SpiceDB and OpenFGA's shape, flattened into
the string). `Principal.__post_init__` refuses a `sub` that starts with
`group:`, exactly as it already refuses `system` and `anon`, and spec
149's edge refuses such a token. `*` stays the posture row. Why a
prefix and not a second `principal_kind` column: the resolver's
`principal_id IN (…)` stays a single-column `IN`, chunkable by
`membership_budget` on every engine (SQL Server has no row-value
`IN`), one bind per id, and the `(principal_id, path_prefix)` index
stays as S1 measured it.

## 9. Where membership comes from

Two sources are possible: a `memberships` table inside vfs (what ADR
067 rule 3 chose), or the `groups` claim in the caller's token (spec
149's open marker).

| System | Source of membership | When it is read |
|---|---|---|
| Postgres | its own catalog, `pg_auth_members` | per check, from a cache invalidated on change (`acl.c:5087-5118`) |
| Plan 9 | its own `/adm/users` | per check (`9user.c:140-161`) |
| Unix | `/etc/group`, NSS or LDAP | at login, frozen in the credential |
| Windows / AD | the directory | at logon, frozen in the token; "no more than 1,024 SIDs" (https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/logging-on-user-account-fails) |
| SpiceDB, OpenFGA, Zanzibar | their own tuples | per check, live |
| AWS IAM | IAM groups, not the token | per request; "IAM groups per user … 10", and groups do not nest (https://docs.aws.amazon.com/general/latest/gr/iam-service.html) |
| Entra ID | a `groups` claim in the token | at issue; past "150 for SAML tokens, 200 for JWT tokens" the claim is replaced by an overage pointer and the app "must use Microsoft Graph" (https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference) |
| Okta | a filtered `groups` claim | at issue; "the groups claim has a limit of 100" and the request fails beyond it |

**Recommendation: the table is the only source of rights in this
landing. The token's `groups` claim is ignored** (spec 149's lean). Four
reasons, the first specific to Clay's case:

1. **In a multiplayer session, the token can only speak for one
   person.** Ann's token lists Ann's groups. The session also needs
   John's groups, and no token in the field carries two subjects (ADR
   062). Only a table vfs reads can supply every member's groups. So a
   claim-based design cannot compute Ann + John at all.
2. **Remote mounts re-derive under their own table** (ADR 062 rule 6).
   A claim is the near side's opinion.
3. **Claims go stale and get truncated.** They are frozen at issue
   (the AD token problem) and silently overflow (Entra's 200, Okta's
   100).
4. **The memo key cannot see a claim.** Resolved rights are cached per
   `grant_revision` (ADR 067 rule 7). A membership row bumps it; a
   claim does not.

Per-call cost of the table: one statement per nesting level for the
walk plus one chunked fetch of grant rows, both only on a cache miss
(§5: two to three walk statements and one fetch of at most 366 ids,
at 64 members with 50 groups each). The follow-up that makes identity-provider groups useful
is a **sync**, not a claim: a system-actor job (SCIM-shaped) that
writes membership rows, attributed and revision-bumping like any other
widening.

## 10. Who administers a group

Spec 058 §8 leaves one marker: who may call `add_member` and
`remove_member`. The lean is "a group is a principal whose own
`read_write` grant on a reserved `/_groups/<id>` path is the admin
right, so no new scope".

First, what is at stake. Adding someone to a group hands them every
grant the group holds. That bypasses `grant`'s attenuation rule ("may
grant at most its own level"), because the admin is not granting a
level on a path; they are copying a whole bundle. So group admin is at
least as powerful as the union of the group's grants.

**The lean has a hole under the default posture.** ADR 068 makes `open`
the default: a `*` row at `/` with `read_write`. `/_groups/eng` is
under `/`. So on a fresh mount *everyone* holds `read_write` on every
`/_groups/<id>` path, and anyone could add themselves to any group.
It can be patched (carve `/_groups` out of the posture, or ignore `*`
rows for this check), but the patch is a special case in the one
function ADR 067 wants to keep uniform. It also puts a principal-admin
concept in the file tree, where `ls /` and `grants("/")` will show it.

The options, against precedent:

| Option | Precedent | For | Against |
|---|---|---|---|
| System actor only | Plan 9: `/adm/users` "can only be changed via console commands" (`users(6):66-71`; `uname` is console-only, `9user.c:945`); Unix: root edits `/etc/group` | no new concept; the system actor already exists and is stamped (ADR 062 rule 4); matches how ETL and provisioning already run | a person cannot manage their own team without an operator or a sync job |
| A declared scope, `groups:admin` | Entra "Groups Administrator"; `Principal.scopes` already exists | edge-verified; global and simple | all-or-nothing across every group |
| Per-group leader or `ADMIN OPTION` | Plan 9 leaders (`9user.c:276-306`; an empty leader means every member leads); Postgres: "Only roles with the ADMIN option on role … may grant this role" (`postgres:src/backend/commands/user.c:2124-2185`), and a `CREATEROLE` creator gets `ADMIN` on what it creates (`:538-588`) | scoped per group; the best long-term shape | needs a column on `memberships` (`admin`), a rule for the first admin, and a rule against an admin granting admin back to its grantor (Postgres refuses that too, `user.c:1765-1829`) |
| `read_write` on `/_groups/<id>` (the spec's lean) | none found | reuses grants | open to everyone under the default posture; mixes principal admin into the path space |

**Recommendation for this landing: system actor only.** It is what
Plan 9 and Unix ship, it needs no new concept, and it closes the
marker without the posture hole. Design the `memberships` row so the
Postgres/Plan 9 shape can follow without a migration: give it
`granted_by` and `granted_at` now (a membership widens exactly like a
grant, and ADR 063 rule 2 says widening is attributed), and leave a
nullable `admin` flag for the follow-up spec that adds per-group
admins.

## 11. Nested groups

Spec 058 §1 says: walk nesting to `MAX_GROUP_DEPTH`; refuse a deeper
nesting at membership write; never truncate at read.

| System | Nesting | Depth bound | Cycles |
|---|---|---|---|
| Postgres | yes | **none**; the walk has no counter (`acl.c:5187-5306`) | refused at write: "role … is a member of role …" (`user.c:1749-1761`), serialised by a lock on the role (`:1711-1717`) |
| Jackrabbit Oak | yes | none | refused at write (`GroupImpl.java:127-135`, `:362-364`); skipped with a log line at read (`MembershipProvider.java:204-208`) |
| SpiceDB | yes | 50 hops by default, `--dispatch-max-depth` (`spicedb:pkg/cmd/serve.go:158`); the error is "max depth exceeded" | not detected; a cycle runs into the depth limit (`internal/dispatch/errors.go:25-27`); docs: "SpiceDB does not support cyclical relationships" |
| OpenFGA | yes | 25 deep, 10 wide (`openfga:pkg/server/config/config.go:25-26`) | detected per request and resolved as not-allowed (`internal/graph/check.go:419-428`, `:476-489`) |
| Windows / AD | yes | no official depth; the token caps at 1,024 SIDs, and nesting multiplies the count | n/a |
| AWS IAM, Cognito | **no**: "User groups can't be nested"; Cognito "Groups cannot be nested" | n/a | n/a |
| Plan 9 | **no**: a flat member list | n/a | n/a |

The shape in spec 058 is right. It is Postgres's (refuse at write)
plus SpiceDB's (a declared depth with a classified error). Three
details to add:

- **Refuse cycles at write, like depth.** The model's walk terminates
  on a cycle because it keeps a visited set (`results.md` §5), so a
  cycle is harmless to the reader. But a cycle is always a mistake,
  and Postgres and Oak both refuse it. Same refusal kind as depth.
- **Serialise membership writes.** Two concurrent writes can each pass
  the depth check and together exceed it (write skew). Postgres takes a
  lock per role. vfs already has a natural lock: every membership write
  bumps `grant_revision`, so update that counter row first and do the
  depth and cycle check under its lock.
- **Keep a read-side check that refuses, not truncates.** If the
  invariant is ever broken (a restore, a hand edit), the walk should
  answer `vfs.budget_exhausted.authority` rather than silently stop.
  §11 of the spec already says so.

**The value.** The walk costs one statement per level on a cache miss.
The sweep's realistic corpus needs two or three. A cap of 8 leaves
plenty of room for org charts (team, department, division, company)
and keeps a cache miss under ten statements. The model shows the
behaviour: a 13-deep chain is refused under caps of 4 and 8 and walked
under 16. The exact number is Clay's call; the point is that it is
small and declared, like SpiceDB's and OpenFGA's, and unlike
Casbin's hard-coded 10 that silently answers false.

## 12. Verdict and spec text to tighten

**Verdict: in scope. Already decided. Implement it in spec 058 as
written, with the tightenings below.** Leaving it out would leave a
real hole: either a room's members would lose their group rights
(every shared team folder invisible to the agent), or an implementer
would take the shortcut of pooling groups across the room, which
leaks (§4). The correct rule is also the cheap one: the meet shrinks
the predicate as the room grows (§5).

The tightenings, none of which changes a ratified decision:

1. **§3 step 1: say "per subject, never pooled".** Each subject's
   closure is its own. Fetch all ids (every subject, every closure
   group, `*`) in **one** chunked `IN`, not "one indexed statement per
   subject" (64 statements for a room of 64). Add the membership walk:
   one chunked statement per nesting level.
2. **§3 step 4: owner arms per member.** Replace `owner_subject: str |
   None` with per-member owner arms (`owner_id = :s_i AND cover(meet of
   the others)`, trimmed of what the shared arms cover). This is what
   §2 and ADR 064 rule 4 already say, and what S1 timed.
3. **§3 step 4: the fallback is not one bind once groups exist.**
   Either stage the resolved arms in a keyed table per `(authority
   fingerprint, grant_revision)` and use one correlated `EXISTS` (one
   bind; S1's fastest group shape), or state the fallback's real bind
   count and give it its own fallback. Recommendation: stage.
4. **§3: derive `MAX_PREFIX_ARMS` from binds and expression depth.**
   Use the same `arm_budget` the glob fan uses. The bind-only formula
   gives about 16,300 arms on SQLite, which parses at most 998.
5. **§1: coverage of `/`.** The root prefix compiles to "true", not to
   `path LIKE '//%'`. This matters for any group or posture grant at
   `/`.
6. **§0: posture holes attach to every covering `*` arm**, not only the
   nearest one.
7. **§1 and §8: groups are `group:<name>`; memberships carry
   `granted_by` and `granted_at`; `add_member`/`remove_member` are
   system-actor only in this landing**, with cycles and over-depth
   refused at write under the revision counter's lock.

## Recommendations

| Question | Recommendation |
|---|---|
| Is Ann + John in scope? | **In.** Already decided by 058 §2–§3 and ADR 066/067; tighten the text as in §12. |
| Group naming | **`group:<name>`** in the one `principal_id` column; `Principal` refuses a `sub` with that prefix, as it refuses `system` and `anon`. |
| Membership source | **The `memberships` table only.** Ignore the token's `groups` claim for rights (149's lean). IdP groups arrive later by a system-actor sync that writes rows. |
| Group admin, this landing | **System actor only.** Add `granted_by`, `granted_at` to memberships now; a per-group `admin` flag (Postgres `ADMIN OPTION`, Plan 9 leader) is a follow-up. Drop the `/_groups/<id>` lean: the default `open` posture makes everyone its admin. |
| Nesting | **Keep `MAX_GROUP_DEPTH` with refusal at write**; refuse cycles at write too; serialise under the revision row's lock; read side refuses, never truncates. A value around 8. |
| Fallback | **Stage the resolved arms** per `(authority fingerprint, grant_revision)` so the `EXISTS` fallback stays one bind with groups. |

## One-line version

Ann + John is in scope and already decided: each person's rights are
the max over their own and their groups' grants, the room gets the min
of those, the resolver computes it exactly on folders, and the spec
needs only tightening, chiefly per-member owner arms, a one-bind
fallback that survives groups, typed `group:` ids, and system-only
group admin for now.
