# Principals and permissions, Phase 0: the threat model, the requirement list, and the frozen rubric

- **Status**: research memo, Phase 0 of the principals-and-permissions
  programme (`2026-09-05-principals-and-permissions-research-plan.md`
  §4). Commits us to nothing. Its job is to fix the targets every
  later memo grades against: one threat table, one requirement list by
  audience, and the thirteen-question rubric frozen. Feeds the five
  Phase 1 lens memos (L1 Unix, L2 Plan 9, L3 capabilities, L4 engines,
  L5 agent-native), the two Phase 2 studies (S1 the predicate at
  scale, S2 what ranked search leaks), the Phase 3 synthesis, spec 070,
  spec 058, ADR 021, ADR 058, and the future `serve()` spec.
- **Date**: 2026-09-05
- **Owner**: Clay Gendron
- **Question**: What must a permission design for vfs prevent, for
  whom, and how will we know whether a body of prior art helps? Three
  parts: (A) the failures on record, each mapped to the vfs surface it
  would hit and the invariant that prevents it; (B) what each of seven
  audiences must be able to express, must see in the audit, and must
  never be able to do; (C) the rubric, restated so five memos written
  in parallel grade the same way.
- **Method**: a line-level read of the repo's own records: the YoloFS
  threat model (`2026-09-04-yolofs-agent-native-filesystem-threat-model.md`
  §2, §5.0, §5.3), spec 070 (Intent, decisions 1 to 7, the research
  review's objections, the resolved `system()` bypass), ADR 021, ADR
  006, ADR 058, the Mirage memo (§B and §4.1 to §4.8), the two MCP
  memos, `standards/mission.md`, the cloud permission models memo, and
  the live seams they name (`src/vfs/permissions.py`, `ops.py`,
  `rerank.py`, `models/version.py`). Then six external primary sources
  fetched 2026-09-05: Hardy's *The Confused Deputy* (1988), Chen,
  Wagner and Dean's *Setuid Demystified* (2002, read from the USENIX
  PDF), the OWASP Top 10 for LLM Applications 2025 entry LLM06
  *Excessive Agency*, the OWASP Top 10 for Agentic Applications 2026,
  the PostgreSQL row-security and `LEAKPROOF` documentation, and the
  MCP authorization specification with its security best practices
  page (2025-11-25). No incident in Part A is invented: every example
  names its source, and where a claim is my judgment it is marked
  `[assumption]`. The full URL list with dates read is in Sources.

---

## Bottom line

vfs's second safety invariant, "every action is scoped to a
principal", does not exist yet: `user_id` is plumbed and inert, and
the only enforcement treats every caller the same. The threat table
below has 64 rows. Most of them are not exotic. They are the same five
failures wearing different clothes: acting with the library's own
authority instead of the caller's (Hardy's confused deputy, T12 to
T15); narrowing that leaves a way back (sendmail's setuid bug, T19 to
T21); a policy evaluated on rows the caller cannot see (Postgres's
`LEAKPROOF` class, T34 to T40); an identity or token that crosses a
wire it should not (MCP's passthrough and session rules, T26 to T33);
and checking at one moment and acting at another (T37, T57). The
multiplayer case (T58 to T64) adds one genuinely new demand: rights
that are the *intersection* of several people's, never their union.
The requirement lists say the same thing from seven seats: everyone
needs to express *who is acting for whom*, everyone needs to see
*both names in the audit*, and nobody, admin included, may widen a
session or cross a wire with a bare identity. One line: **the design
must make authority an explicit, narrowing-only, doubly-attributed
input to every statement, and the lenses must be graded on whether
their precedent does that.**

## Terms used below

- **Subject**: the principal on whose behalf work happens. A person, a
  team, a service, admin, or (multiplayer) a set of them.
- **Actor**: the agent doing the work. Not the subject.
- **Principal**: spec 070's frozen value meaning "the edge verified
  this" (`sub` plus scopes, spec 070:70-82).
- **Attenuation**: narrowing authority. A session may narrow and never
  widen.
- **Grant**: a row saying this principal has this level over this path
  prefix (spec 058:27-31; ADR 021).
- **Profile**: the document a session runs under; it only narrows what
  the mount table declares (Mirage memo §3.6, §4.5).
- **Hide vs deny**: a hidden path answers "not found" and its name
  never appears; a denied path is listed and refused (Mirage memo
  §3.7).
- **Confused deputy**: a program that holds authority from two sources
  and uses the wrong one (Hardy 1988).
- **TOCTOU**: time-of-check to time-of-use. The state changes between
  the check and the act.
- **Leakproof**: Postgres's word for a function that "reveals no
  information about its arguments other than by its return value"; only
  such functions may run before a row-security filter.
- **Audience**: the service a token was issued for. **Passthrough**:
  forwarding a token to a service it was not issued for.
- **The funnel**: vfs's one dispatch path, `_route_* → _call_storage`
  (spec 070:103-113), where the principal reaches storage.

---

## Part A. The threat table

Columns: the failure class; a concrete example or attack with its
source; the vfs surface it would hit; the invariant that must hold to
prevent it; the rubric question that governs it. Rows are grouped A to
H by the shape of the failure. Citations are `file:line` in this repo
or a named external source (URLs in Sources).

Abbreviations: `yolofs` = `2026-09-04-yolofs-agent-native-filesystem-threat-model.md`;
`070` = `specs/active/070-principal-scoped-sessions/spec.md`;
`058` = `specs/active/058-row-level-permission-grants/spec.md`;
`021` = `decisions/021-row-grant-model-spine.md`;
`006` = `decisions/006-global-namespace-tenant-permissions.md`;
`adr058` = `decisions/058-the-access-layer-for-agents-positioning.md`;
`mirage` = `2026-09-04-mirage-design-patterns.md`;
`mcp0810` = `2026-08-10-mcp-2026-07-28-stateless-revision.md`;
`mcp0419` = `2026-04-19-mcp-specification.md`;
`cloud` = `2026-04-22-cloud-permission-models.md`;
`race` = `2026-09-04-delete-vs-mkedge-race.md`;
`plan` = `2026-09-05-principals-and-permissions-research-plan.md`.

| # | Failure class | Concrete example or attack (source) | vfs surface | Invariant that must hold | Q |
|---|---|---|---|---|---|
| **A** | **The agent acts wrongly** (YoloFS, 290 public reports, Feb 2024 to Mar 2026) | | | | |
| T1 | Wrong goal | "deleted when asked to archive", 76 reports (`yolofs:156`) | `write`, `delete`, `move` | Every mutation is reversible: delete reparents into trash, a write mints a version; a future `revert` is a write under the same gate | Q10 |
| T2 | Wrong scope | "searched the whole home directory instead of the project", 50 reports (`yolofs:157`) | `glob`, `grep`, `glean`, `ls`, `tree` | Reach is bounded by the namespace and the session: what is not mounted, or is hidden from this session, is not searched, counted, or ranked | Q2, Q5 |
| T3 | Incorrect tool use | "malformed quoting wiped a drive", 27 reports (`yolofs:158`) | `run` (`EXEC_OPS`, `src/vfs/ops.py:74`) | Typed verbs take paths, not strings; `run`, the one string-taking verb, stays behind the same gate as every other verb | Q3 |
| T4 | Unfollowed instruction | 56 reports; the agent's own words: "I get focused on solving the problem and skip the step" (`yolofs:159`) | every verb | Enforcement is not an instruction. The write gate runs before dispatch (`src/vfs/permissions.py:5-10`) and the read predicate is compiled into the SELECT (`058:37-43`) | Q3 |
| T5 | Prompt injection that reads a secret | `leak.sh` reads `.env` (`yolofs:331-333`); M3 = 21 reports; secret leaks are 17 % of impacts (`yolofs:136`); OWASP ASI01 "Agent Goal Hijack" is the 2026 name for the same thing | `read`, `grep`, `glean` | A read is gated before it happens, because "reads are the effect no undo reverses" (`yolofs:602-606`); sensitive paths can `ask` | Q5, Q9 |
| T6 | Shell loophole | "policies on the file tools do not apply to shell commands", 77 reports (`yolofs:163`) | `run`, `cli` | One door: every verb, including `cli` and `run`, re-enters the router (`yolofs:442`) | Q3 |
| T7 | Effect-blind filter | the filter matches `rm` but not `unlink` or `os.remove`, 52 reports (`yolofs:164`) | every verb | Gates decide on `(op, path)` and on rows, never on command text (`yolofs:443`) | Q3, Q4 |
| T8 | Rigid policy | 130 reports: "a static up-front policy does not fit a task-dependent run" (`yolofs:166`) | session, profile | Policy can tighten during a run without a restart; it can never loosen during a run | Q2 |
| T9 | Approval fatigue | 80 reports of users enabling "YOLO mode" (`yolofs:168`) | `ask` | `ask` fires only at sensitive paths; a remembered answer lands in the right place (allow becomes a grant row, deny becomes a profile rule), never a blanket allow (`yolofs:593-601`) | Q2, Q7 |
| T10 | Uninformative approval | 31 reports: the prompt "shows the command, not its filesystem effects" (`yolofs:169`) | `explain`, every refusal `Result` | A refusal and an explanation carry the winning rule as structured `data`, not prose (`mirage:862-870`); a dry run spends nothing (`mirage:840-844`) | Q8 |
| T11 | The agent edits its own policy | YoloFS: "The agent cannot edit its own policy" (`yolofs:313`); Mirage freezes the profile "so two agents with the same profile share one object and neither can bend the other's view" (`mirage:247-249`) | mount admin (`bind`, `remount`), profile | A session's policy document is read-only to that session; a new bind never loosens an ancestor (`yolofs:607-614`) | Q2 |
| **B** | **Identity: who is acting, on whose behalf** | | | | |
| T12 | Confused deputy, the classic | Hardy 1988: the compiler, licensed to write its home directory SYSX, wrote debugging output over `(SYSX)BILL` because a user named that file; "the compiler runs with authority stemming from two sources ... It has no way to keep them apart" | the funnel under `default_principal=Principal.system()`; a backend that holds a remote mount's credential and takes a caller's path | A verb acts under the subject's authority, never the library's own; designation (the path) and authority (the principal) travel together; an actor holding two authorities must name which one it is using | Q1, Q9 |
| T13 | Confused deputy one layer up: identity as an argument | `user_id` "is caller-asserted. Any code path can name any user" (`070:38-39`); "a wire caller asserting identity as data is the confused deputy recreated one layer up" (`070:230-232`) | `serve()`, every verb's `principal` kwarg | Identity enters from the transport, never from tool arguments; no published tool schema carries a principal property (`070:229-232`, `070:371-373`) | Q1, Q3 |
| T14 | Fail-open on absent identity | "`None` silently means 'unscoped god-mode,' so forgetting to pass identity grants everything instead of nothing" (`070:47-48`) | every verb, `_call_storage` | Absence fails closed; privilege is a named, explicit default (`default_principal`, `070:131-168`); PostgREST's `db-anon-role` is the precedent (`070:159-162`) | Q1, Q2 |
| T15 | Admin as ambient authority | `Principal.system()` bypasses row grants (`070:468-483`); Postgres table owners and `BYPASSRLS` roles bypass row security (PostgreSQL row-security docs) | ETL, `sweep`, any admin verb | Admin is one principal among others: the bypass covers row grants only, never structure (`PermissionMap`, mount masks, topology locks), is audited as `system`, and never crosses a wire (`070:473-481`) | Q1, Q6 |
| T16 | Shared, long-lived service credentials | "45.6 % of agents authenticate with shared keys" (`adr058:45-46`); OWASP ASI03: "Broad, long-lived tokens convert minor hijacks into major data breaches" | `serve()`, sessions | Each session binds one verified principal; one verification, one `Principal`; a refreshed token is a new session (`070:322-326`) | Q1, Q8 |
| T17 | Actor and subject conflated in the record | `Version.created_by: str \| None` holds one string (`src/vfs/models/version.py:58`); 070 objection 9: a backend acting as itself "must keep per-user attribution downstream even inside the trust perimeter" (`070:345-349`) | versions, audit | Every version row names both the actor and the subject (or the subject set) | Q8 |
| T18 | Token reuse across workflows | OWASP ASI03 example (Palo Alto's summary of the list): "A customer-support agent reuses an admin token from a prior workflow to access restricted HR data" | sessions, cursors, ask ids | A session's rights are fixed at open and die at close; closed is final (`070:361-362`); any handle is validated against the principal on every call (`mcp0810:281-282`) | Q2, Q9 |
| **C** | **Attenuation that silently fails** | | | | |
| T19 | A privilege drop that leaves a way back | *Setuid Demystified* §7.1: sendmail 8.10.1 called `setuid(getuid())` to drop root; with the Linux SETUID capability cleared, "calling setuid(getuid()) only modified the effective uid", the saved uid stayed 0, and "the attacker is able to violate that expectation" by `setreuid(-1,0)` | session narrowing, profile, `close()` | Narrowing is permanent for the session's life: no saved authority survives to be restored; the narrowed state is verified, not assumed (§8.1.3: "A process should check the return codes") | Q2, Q9 |
| T20 | The same call means different things per platform | the uid-setting calls "are poorly designed, insufficiently documented, and widely misunderstood and misused" (abstract); `setuid` sets one uid or all three depending on the OS and on whether the caller is privileged (§8.1.1) | dialect profiles, the remote mount | "narrow" means one thing on every engine and on both sides of a wire; a mechanism whose meaning varies by dialect is disqualified before its merits are weighed (`021:26-31`) | Q2, Q11 |
| T21 | Order-dependent narrowing | §8.1.2: "a program should drop group privileges before dropping user privileges permanently. Otherwise ... the program may be unable to permanently drop group privileges" | profile composition, `_permission_layers` | Composition is most-restrictive-wins and order independent (`006:59-64`); no sequence of narrowings leaves a residual right | Q2 |
| T22 | Excessive permissions | OWASP LLM06: "Excessive Permissions – Extensions have more access rights than required for their purpose"; its fix for the email assistant is a read-only OAuth scope | the actor's profile, `Principal.scopes` | The actor's authority is at most its subject's; the profile "only narrows" (`mirage:238-266`) | Q2 |
| T23 | Excessive autonomy | OWASP LLM06: "Excessive Autonomy – Systems fail to verify and approve high-impact actions before execution" | `write`, `delete`, `mkedge`, mount admin, `sweep` | `ask` on sensitive paths; `sweep`, the only destroyer, is never on the tool surface (`yolofs:448`) | Q2, Q7 |
| T24 | Excessive functionality | OWASP LLM06: "Excessive Functionality – Extensions contain unneeded capabilities" | the `serve()` tool set, a session's verb set | A session carries an op mask; an unlisted verb is `unsupported`, not `permission_denied` (`mirage:882-885`) | Q2, Q5 |
| T25 | Scope inflation | MCP best practices, Scope Minimization: a token "carrying broad scopes (`files:*`, `db:*`, `admin:*`)" granted up front; listed mistake: "Treating claimed scopes in token as sufficient without server-side authorization logic" | `serve()`, scopes | Progressive least privilege: minimal initial scope, step-up on challenge; scopes are an input to enforcement, never the enforcement | Q2 |
| **D** | **The wire** | | | | |
| T26 | Token passthrough | MCP: "MCP servers MUST NOT accept any tokens that were not explicitly issued for the MCP server"; a server forwarding tokens unvalidated lets "a malicious actor in possession of a stolen token ... use the server as a proxy for data exfiltration" | the remote mount (an MCP-client backend) | The edge token never leaves the edge; the backend acts as a trusted subsystem or exchanges the token (RFC 8693) (`070:235-250`) | Q1, Q9 |
| T27 | Audience not validated | MCP authorization: "MCP servers MUST validate that access tokens were issued specifically for them as the intended audience, according to RFC 8707 Section 2" | `serve()`'s `TokenVerifier` seam | Audience, signature, issuer and expiry are all checked at the edge, audience on by default; the python-sdk example ships it off behind a flag and must not be copied (`070:218-228`) | Q9 |
| T28 | Session hijack, impersonation | MCP: an attacker who guesses a session id is treated "as a legitimate user"; "MCP Servers MUST NOT use sessions for authentication" and "MUST verify all inbound requests" | `serve()`, sessions | Every request is authenticated; a vfs session is bound to the verified principal, never to a transport id; `Mcp-Session-Id` no longer exists after 2026-07-28 (`mcp0810:455-458`) | Q9, Q2 |
| T29 | Session hijack, event injection | MCP: an attacker enqueues a malicious event under a known session id on server B; server A delivers it to the client as a resumed stream; `tools/list_changed` as a vector | `serve()` behind more than one server | Server-side state is keyed by `<user_id>:<session_id>` (MCP); list results never vary per connection (`mcp0810:274-278`) | Q9 |
| T30 | Bearer handles | "possession is not authorization — validate `(handle, auth_context)` per call" (`mcp0810:281-282`); FastMCP 4: "without auth, a session/handle id is a bearer capability" (`mcp0810:365-366`); servers "MUST treat `requestState` as attacker-controlled" (`mcp0810:194-195`) | cursors, ask ids, task ids, every vfs-minted handle | A handle is opaque, bound to the principal, expiring, and checked on every use (`mcp0810:411-419`) | Q9 |
| T31 | OAuth-proxy confused deputy | MCP: a static client id plus dynamic registration plus a consent cookie lets an attacker's client obtain an authorization code without consent; proxies "MUST obtain user consent for each dynamically registered client" | `serve()` only if it proxies to an upstream IdP | Per-client consent before forwarding. vfs ships no IdP (`070:401-403`), so this row binds a deployment, not the library; 070's review notes the section is narrower than 070's concern (`070:44-46`) | Q9 |
| T32 | Header and body disagree | 2026-07-28 transport: "the stated threat is a gateway authorizing on the header while the server executes the body"; servers MUST reject mismatches (`mcp0810:155-162`) | `serve()` | Authorization is decided on the same bytes that execute; a gateway's decision is never the last decision | Q3, Q9 |
| T33 | Identity crossing as a bare string | 070 D7: "identities crossing as data are namespaced by sender — the receiver maps (issuer/client, `sub`) into its own principal space, never bare `sub` and categorically never its own `system()`" (`070:246-250`) | the remote mount, both sides | The far side enforces under its own principal space; local admin confers nothing remotely (`070:478-481`) | Q1, Q6 |
| **E** | **Leaks through the data layer** | | | | |
| T34 | Non-leakproof evaluation before the policy | PostgreSQL `CREATE FUNCTION`: a function "which throws an error message for some argument values but not others, or which includes the argument values in any error message, is not leakproof"; only leakproof functions may run "ahead of the row-security check" | `grep` (a regex over content), `glean` (embedding and BM25), `run` | No caller-supplied operation runs on a row the caller cannot see: the visibility predicate "has to reach nomination, not just the final fetch" (`mirage:806-814`) | Q5, Q9 |
| T35 | Statistics leak | S2's question (`plan:219-226`): BM25 idf is corpus-wide; the cross-mount merge re-scores the union with each mount's exported `lexical_stats` (`src/vfs/rerank.py:287-302`) | `glean`, the cross-mount merge in `src/vfs/rerank.py` | Ranking statistics are computed over the visible set (or coarsened) so a score cannot reveal a term in a hidden row; S2 measures what leaks and what the fix costs | Q5, Q9 |
| T36 | Covert channel through constraints | PostgreSQL: "Referential integrity checks, such as unique or primary key constraints and foreign key references, always bypass row security ... Care must be taken ... to avoid 'covert channel' leaks of information through such referential integrity checks" | `write`, `mkdir`, `mkedge`, `move` (the `(parent_id, name)` unique index, `yolofs:498-500`) | A write that collides with a hidden entry is refused in a way that does not confirm the hidden name exists | Q5, Q9 |
| T37 | Stale-snapshot race inside the policy | PostgreSQL row-security docs: the `mallory` example; a policy sub-select read at a stale snapshot "tests the old value of mallory's privilege level and allows her to see the updated row" after revocation | grants, membership | Grant and membership reads share the snapshot of the statement they guard; a revocation is visible to the next statement; a session may not cache a grant beyond that | Q9, Q13 |
| T38 | Existence leak through the refusal kind | Mirage: an unlisted command is 127, not 126, "so an unlisted tool never leaks that it exists" (`mirage:286-288`); FastMCP answers a mismatched session with 404 (`070:378-380`) | every refusal `Result` | A hidden path reads as `not_found`, never `permission_denied`, and the `Result` "carries no hint that a rule fired" (`mirage:802-805`) | Q5 |
| T39 | Name leak in listings and errors | Mirage §3.3: a segment "leaked the name of a namespace-only ancestor whose only mount" the session could not see (`mirage:195`); "`grep -r x /` leaked a walled-off mount's contents" (`mirage:228`) | `ls`, `tree`, `mounts()`, `cross_mount` errors | A binding the principal may not see is not named anywhere: not in a listing, a tree, or a router-minted message (`mirage:815-818`) | Q5 |
| T40 | A native push-down counts what it cannot show | Mirage forks native fast paths to the guarded walk "so a push-down cannot be used to count what the session cannot see" (`mirage:290-295`) | the glob and grep planners, segment postings, `tree` totals, truncation flags | Counts, totals and truncation are computed over the visible set only | Q5 |
| T41 | One judgment for a two-path verb | Mirage's bug: `cp /protected/secret /review/deep/out` was answered by the destination's `ask`, so "a nod meant for the destination carried the protected file out" (`mirage:310-315`) | `copy`, `move`, chained verbs | Every path a verb names is judged; across subjects severity leads: a deny anywhere refuses the line (`mirage:315-318`) | Q3, Q5 |
| T42 | An answer banked against a dead run | Mirage drops an abandoned ask's answer rather than banking it "against a run that no longer exists" (`mirage:340-343`) | the ask ledger | An answer's scope is `once` or `session`; nothing reaches another session | Q2 |
| **F** | **Grants, the namespace, defaults** | | | | |
| T43 | Deny rows racing allow rows | Jackrabbit Oak's `rep:DenyACE`, "the cautionary tale spec 058 already cites" (`021:53-56`) | grants | Grant rows are additive-only; subtraction is a policy-layer expression, "never as a row that races other rows for precedence" (`021:35-41`) | Q4, Q6 |
| T44 | Prefix tenancy gamed across the scope boundary | ADR 006: rules "checked in unscoped coordinates could be gamed across the scope boundary (the `permissions.py` docstring's `/wiki/alice/synthesis` example)" (`006:24-28`) | paths, every verb | One global namespace; "Isolation is authorization, not path rewriting" (`006:38-47`) | Q4 |
| T45 | One entry, many paths | ADR 021 D2: hard links "would give an entry many paths ... making prefix coverage ambiguous — the classic POSIX hard-link permission problem" (`021:74-79`) | grants on prefixes | While grants attach to prefixes, an entry has exactly one path | Q4 |
| T46 | Loosening below the parent | cloud invariant 3: "The tightening direction is free; the loosening direction is restricted" (`cloud:93-95`); note the memo's Drive line reads "cannot be set more restrictive than its parent" (`cloud:28-31`), the opposite direction, and the L4/L5 lenses should settle which Drive enforces | grants, `move`, `copy` | A child's effective rights never exceed what its parent's policy allows; loosening is an explicit, audited act | Q7 |
| T47 | Sharing confused with permission | cloud invariant 4: "Sharing is an act ... Permission is the state that results. Confusing the two is the source of most SharePoint complexity" (`cloud:96-99`) | grants, share links | A share is a recorded act with actor, subject, scope and expiry; permission is the state it produces | Q7, Q8 |
| T48 | Grants and links that never expire | Drive's `expirationTime` (`cloud:24-25`); Dropbox links with "expiration dates, revocation" (`cloud:72-75`) | grants, sessions | Every grant and every session has a lifetime; expiry is enforced in the predicate, not by a sweeper | Q6, Q7 |
| T49 | Membership resolved once and cached | 070's open groups question: resolve "at session construction" or "join a memberships table at query time" (`070:464-467`); the enterprise case is SCIM deprovisioning `[assumption: SCIM is the source of group truth in the enterprises ADR 058 targets]` | groups, sessions | A removed member loses access no later than the next statement; anything cached is bounded by a short session | Q6, Q13 |
| T50 | Ownership by accident | 070: "a batch job runs *as* `system` but writes rows *owned by* many users — so `owner_id` stays data, stamped explicitly" (`070:170-175`); 058's open forks on NULL-owner writability and move/copy (`021:11-14`) | `write`, `mkdir`, `move`, `copy` | A new entry's owner and inherited grants are decided by rule, never by whoever happened to run the batch | Q7 |
| T51 | Break-glass without a record | Dropbox: "Admin-visible monitoring of sharing activity is a first-class feature, not an add-on" (`cloud:76-77`) `[assumption: break-glass modelled as a named, time-boxed principal]` | admin, ETL | Emergency access is a principal with a reason, a lifetime and an audit row, never a config flag | Q6, Q8 |
| T52 | Labels ignored | cloud invariant 6: "Label-driven policy beats per-item configuration" (`cloud:103-106`); a `Highly Confidential` label blocks `Anyone` links (`cloud:54-57`) | grants, share, `serve()` | A sensitivity label is a policy input the gate reads; a share a label forbids is refused | Q4, Q6 |
| **G** | **Scale, reversibility, deployment** | | | | |
| T53 | A predicate that grows with the batch | `CLAUDE.md`: Oracle's 1,000-element `IN` list, SQL Server's ~2,100 bind parameters; 10k batches are "a supported contract"; the subject-set predicate for 2, 5 and 20 principals (`plan:207-217`) | every batch verb; the grant and subject-set predicates | Every predicate chunks by `membership_budget`; a set of 20 principals over 10k rows stays bounded on every engine; S1 measures it | Q11 |
| T54 | A revert that exceeds rights | the plan's Q10: "can a revert exceed the actor's rights?"; `yolofs:550-551` proposes `revert` as "mutating, mints a version" | versions, `restore`, `revert` | A revert and a restore are writes under the same gate as any write; the version being restored must be readable to the subject | Q10 |
| T55 | Undo does not un-read | YoloFS: "A `G` record says a read happened; nothing says where the bytes went. That is the honest limit of any filesystem-tier leak defense" (`yolofs:417-419`) | `read`, `grep`, `glean`, audit | Reads are recorded per session as `(path, version)` (`mirage:916-926`) so a leak can be scoped, even though it cannot be reversed | Q8, Q10 |
| T56 | The DSN bypass | "a caller with the DSN bypasses vfs the way a process with the block device bypasses YoloFS" (`yolofs:656-657`); "Permissions are per-filesystem-instance, not per-storage" (`src/vfs/permissions.py:60-68`) | deployment | The agent holds a vfs handle, never the DSN; Postgres RLS is defense in depth where the engine has it, not the portable baseline (`021:85-96`) | Q3 |
| T57 | TOCTOU between check and act | Hardy's compiler was checked at open time under the wrong authority; MCP's DNS-rebinding note ("resolve to a safe IP during validation but to an internal IP during the actual request"); in this repo, the delete-vs-mkedge race memo names "the insert-vs-delete TOCTOU window" (`race:196`) | `explain` then `write`; a grant check then a write; liveness then `mkedge` | Check and act happen in one statement or one transaction: the write's own predicate is the check; `explain` is advisory and spends nothing | Q9, Q3 |
| **H** | **Multiplayer: one actor, a set of subjects** (`plan:56-89`) | | | | |
| T58 | A reply leaks a document one member cannot see | Claude tagged in a group chat answers from a file only some members may read; every reply "is seen by every member" (`plan:59-62`) | `glean`, `read`, `grep` in a set session | The session reads only what every member can read: a row is hidden from the session if it is hidden from any member (`plan:87-88`) | Q13, Q5 |
| T59 | A write one member could not have made | the agent edits a shared roadmap for the group; one member holds read only (`plan:61-62`) | `write`, `edit`, `delete`, `mkedge` | The session writes only where every member may write: write is an intersection over the set (`plan:66-67`) | Q13 |
| T60 | A member joins mid-session | a new member is added to the chat; text already in the agent's context was fetched under the old set (`plan:85-86`) | session, `ask`, `glean` | Joining narrows the session immediately for every later verb; what was already read is on record (T55) so the exposure is scoped, since it cannot be undone | Q13 |
| T61 | A member leaves mid-session | removing a member would widen the intersection `[assumption: the plan states the join case; the leave case follows from "a session never widens"]` | session | A session never widens; a wider set is a new session | Q13, Q2 |
| T62 | The actor's own profile is wider than the set | the bot's service account is an admin (T15, T16); Unix supplementary groups are the anti-pattern, "where membership *widens* what a process can do" (`plan:68-69`) | session, profile | Effective rights = ⋂ grants(subject_i) ∩ profile(actor) ∩ session narrowing (`plan:71-73`); the actor contributes no rights of its own | Q13, Q2 |
| T63 | Who owns what the set writes | the plan's open sub-question (`plan:84-85`) | `write`, `owner_id` | Ownership is data stamped by rule (`070:170-175`); a set-authored row records the set (or a group standing for it) as owner and the actor in the audit `[assumption on the shape; Q13 asks the lenses]` | Q13, Q7 |
| T64 | The audit of a set | the plan's open sub-question: "how the audit records a set" (`plan:85`) | versions | The version row records the actor and the whole subject set at that version; a single `created_by` string cannot hold it (`src/vfs/models/version.py:58`) | Q13, Q8 |

Three notes on the table:

1. **Row counts are YoloFS's and overlap.** The paper's Figure 4 says
   "Counts can overlap" (`yolofs:148-151`), so T1 to T10 sum past 290.
2. **Two rows are deployments, not library code.** T31 (OAuth proxy)
   and T56 (the DSN) cannot be closed by vfs alone; they are listed so
   the `serve()` spec and the deployment docs say so.
3. **What the table does not contain.** No row for process isolation,
   seccomp, or containers; the plan's §6 puts those with the harness.
   No row for authentication itself; vfs ships no IdP.

---

## Part B. The requirement list, by audience

Seven audiences. For each: what it must be able to **express**, what it
must **see in the audit**, and what it must **never** be able to do.
Each line names its source; `[assumption]` marks my judgment. The
audiences are the project's own: the mission's primary user is the
developer "building AI agents that need to operate on enterprise
knowledge over long horizons" (`standards/mission.md:12`); ADR 058's
buyer is "Platform and AI-infra teams stalled in security review"
(`adr058:217-218`); the two production audiences are agents and ETL
(`CLAUDE.md`, production posture); the wire audiences come from spec
070 D6/D7 and the two MCP memos; the multiplayer audience is the
plan's §1.1.

### B1. The individual developer embedding vfs as a library

**Must be able to express**

- Run a script as a named privileged principal in one line:
  `default_principal=Principal.system()` (`070:139-144`), "easy the way
  `sudo` is easy to type, never ambient" (`070:155-156`).
- Open a per-caller session that carries the principal so verbs take
  no identity argument (`070:184-205`).
- Declare mount-wide and per-prefix permission in code
  (`src/vfs/permissions.py:1-10`; `006:59-66`), and later per-principal
  grants as rows (`058:27-31`).
- Ask what a call would do before doing it: `explain` returns the same
  `Result` the real call would refuse with (`mirage:836-846`).
- Build a `Principal` by hand in tests, and nowhere else in `src/`
  (`070:86-92`).

**Must see in the audit**

- On every version row: the actor and the subject it acted for (T17).
- On every refusal: the rule that fired, as structured `data`, never
  only in the message (`mirage:862-870`).
- On every mutating verb: the typed observations of what changed
  (`trash_path`, `version`) (`yolofs:521-524`).

**Must never be able to do**

- Get unscoped access by omitting an argument (`070:131-137`).
- Widen a session past what the mount table declares
  (`mirage:872-881`).
- Turn `sweep` into an agent-facing verb (`yolofs:448`).
- Mint a `Principal.system()` from a token (`070:94-100`).

### B2. The enterprise admin

**Must be able to express**

- Tenants as subtrees plus grants, never as path prefixes
  (`006:38-41`, `006:88-91`).
- Typed principals: user, group, domain, anyone (cloud invariant 1,
  `cloud:84-87`).
- Groups whose membership is resolved with a bounded staleness, so a
  SCIM removal takes effect by the next statement (T49)
  `[assumption: SCIM as the membership source]`.
- A lifetime on every grant and every share link (`cloud:24-25`,
  `cloud:72-75`).
- Sensitivity labels as policy inputs that override per-item settings
  (`cloud:54-57`, `cloud:103-106`).
- Emergency (break-glass) access as a named principal with a reason and
  a time box (T51) `[assumption]`.
- Least privilege for service accounts: an agent's actor profile that
  only narrows; no shared keys (`adr058:45-48`, "the recurring phrase
  ... is **least privilege**").
- A retention rule for versions and audit rows, with `sweep` as the
  only destroyer and never on the tool surface (`yolofs:448`)
  `[assumption on retention as a rule]`.

**Must see in the audit**

- "who can reach what, which tools live where, what changed and when",
  the plane's four panels (`adr058:186-189`), answered by the
  enforcement code itself rather than a second model of it
  (`mirage:844-846`).
- Every share as an act with actor, subject, scope and expiry (cloud
  invariant 4, `cloud:96-99`).
- Every admin or batch action attributed to `system` (`070:473-474`).
- Every gated access (asked, allowed, denied, with the rule that fired)
  and every rule change: YoloFS's `G` and `C` records as the Catalog's
  feed (`yolofs:629-635`).

**Must never be able to do**

- Make any session wider than its subject, admin included (T15, T62).
- Confer local admin across a wire (`070:478-481`).
- Express a deny as a row that races grants (`021:35-41`).
- Delete audit from the agent surface (`yolofs:448`).

### B3. The ETL job and batch loader

**Must be able to express**

- Run as `system` with one greppable line, and stamp `owner_id` per row
  as data: "Caller identity is not row ownership" (`070:170-175`).
- Batches of 10,000+ entries in one call, bounded on every engine
  (`CLAUDE.md`; T53).
- Run as a named, narrower principal when the pipeline should be
  scoped, so that "admin as a principal" is a choice and not the only
  option `[assumption: the PostgREST-style least-privilege internal
  actor 070 declined for the batch case, `070:481-483`, remains
  available as an opt-in]`.

**Must see in the audit**

- Rows attributed to the job as actor and `system` as subject, with the
  stamped owner visible as data (`070:473-474`).
- The batch's own observations: which rows landed, which were refused,
  which versions were minted (`yolofs:521-524`).

**Must never be able to do**

- Bypass structure: `PermissionMap`, mount rights masks, topology locks
  "bind every principal, system included" (`070:474-478`).
- Carry admin through a remote mount (`070:478-481`).
- Learn a hidden name through a unique-constraint error (T36).
- Emit a statement whose size grows with the batch (`CLAUDE.md`).

### B4. The agent harness

**Must be able to express**

- allow, ask and deny by path and by verb: YoloFS's rule tree
  (`yolofs:304-314`), Mirage's `commands` and `paths` blocks
  (`mirage:240-246`), and the `PreToolUse`-style hook the harnesses
  already ship (`yolofs:345-351`).
- A session that binds one profile at open and only narrows
  (`mirage:872-881`), plus an op mask (`mirage:882-885`).
- A `write-ask` rung: reads free, writes asked (`yolofs:587-592`).
- An `ask` that returns a classified `permission_denied.pending`
  `Result` with an ask id, answered out of band through elicitation or
  tasks, never a blocked thread (`mirage:848-860`; `yolofs:616-622`).
- The scope of an answer: once, session, or persistent, with allow
  landing as a grant row and deny as a profile rule
  (`yolofs:593-601`).
- Tightening during a run without a restart (T8).

**Must see in the audit**

- Per-verb observations as the "introspect effects" primitive
  (`yolofs:551-555`).
- The ask ledger: pending and settled as one record type, one store
  (`mirage:331-336`).
- What the agent read, at what version (`mirage:916-926`).

**Must never be able to do**

- Edit its own policy or loosen an ancestor through `bind`/`remount`
  (`yolofs:607-614`).
- Parse `message` to learn the rule (`mirage:862-870`).
- Decide a timeout inside the gate; timeout is the host's policy
  (`yolofs:619-622`).
- Bank an answer from a run that no longer exists (`mirage:340-343`).

### B5. The MCP client and server

What identity arrives: at the server, a bearer token whose verified
claims are `sub`, scopes, `client_id`, issuer and expiry; the
python-sdk's `AccessToken` carries "no `sub`" and vfs's verifier must
surface it itself (`070:261`); the authorization spec requires
"Authorization: Bearer" on "every HTTP request from client to server,
even if they are part of the same logical session".

**Must be able to express**

- Server: act as an OAuth 2.1 resource server; validate audience,
  signature, issuer and expiry at one seam (`070:218-228`); publish
  scope challenges so clients step up rather than request everything
  (MCP authorization, Scope Challenge Handling).
- Server: construct the `Principal` and open the session server-side,
  with exactly one sanctioned ambient read at the adapter
  (`070:327-332`).
- Server: reject header/body mismatches (`mcp0810:155-162`).
- Client: send the RFC 8707 `resource` parameter and PKCE `S256` (MCP
  authorization, Resource Parameter Implementation); begin with baseline
  scopes (Scope Minimization).

**Must see in the audit**

- The principal on every request, so "the MCP Server will be
  [able] to identify or distinguish between MCP Clients" (the
  passthrough section's accountability risk, inverted).
- Scope elevation events "with correlation IDs" (MCP, Scope
  Minimization, server guidance).

**Must never cross the wire**

- The edge token, in either direction (T26; `070:235-250`).
- A `principal` or `user_id` tool argument (`070:229-232`); the
  `_meta.user_id` idea the April memo raised (`mcp0419:207`) is
  answered no by 070 D6.
- `Principal.system()` in any encoding (`070:94-100`).
- A hidden name, in a listing, a count, or an error (T38, T39).
- A handle usable without the principal that minted it (T30).

### B6. The remote mount

The rule in one line: "a remote mount's far side enforces under its
own principal space" (`070:478-481`).

**Must be able to express**

- Two shapes, chosen per trust relationship: trusted subsystem (the
  backend authenticates as itself and sends `sub` as data, inside a
  mutual-trust perimeter) or RFC 8693 token exchange for a separate
  party (`070:239-243`).
- On the receiving side, a mapping from `(issuer/client, sub)` into the
  local principal space (`070:246-250`).

**Must see in the audit**

- Per-user attribution on both sides even inside the trust perimeter
  (`070:345-349`).
- Which mount answered and under which far-side principal
  `[assumption: the cross-mount merge's provenance (`source`, `mount`
  in `rerank.py:67-84`) is the place]`.

**Must never be able to do**

- Forward the token (T26).
- Treat local admin as remote admin (`070:478-481`).
- Rank, count or export statistics over rows the caller cannot see on
  the far side (T35, T40).
- Name a binding the caller may not see in a `cross_mount` error
  (`mirage:815-818`).

### B7. The multiplayer session

The rule in one line: "The session's subject is a set of principals,
and the session holds a right only when every principal in the set
holds it" (`plan:64-65`).

**Must be able to express**

- A session opened for a set of subjects with one actor, where read
  and write are each an intersection over the set (`plan:66-67`,
  `plan:71-73`).
- A change of set during the session: a join narrows immediately; a
  leave does not widen, and a wider set is a new session (T60, T61).
- An ownership rule for what the set writes (T63) `[assumption on
  shape; Q13 is open]`.
- Hide-vs-deny for a set: hidden if hidden from any member
  (`plan:87-88`).
- How a set composes with the actor's profile and with admin
  (`plan:88-89`): the actor contributes no rights; admin in the set is
  one member like any other `[assumption: the plan asks this; the
  least-privilege reading is the only one consistent with §1.1]`.

**Must see in the audit**

- The actor and the whole set on every version row (T64).
- The set's membership at every read, recorded with `(path, version)`
  (T55, T60).
- Any mid-session change of set, as its own record `[assumption]`.

**Must never be able to do**

- Surface a row hidden from any member (T58).
- Write where any member may not (T59).
- Widen during the session (T61).
- Let the actor's own profile add a right the set lacks (T62).
- Let one member's wider personal session leak into the shared reply
  `[assumption: the group session and a member's private session are
  different sessions with different subjects]`.

---

## Part C. The frozen rubric

The thirteen questions, verbatim from the plan's §2 (`plan:101-115`),
each followed by one sentence saying what each verdict looks like, so
the five Phase 1 memos grade uniformly. The four verdicts are those
spec 070's review used (`070:5-6`): **supports**, **qualified**,
**no precedent**, **contradicts**.

**Q1.** Who is the subject, and how is "acting on behalf of" represented? Is the actor distinct from the subject?
*Supports*: the source names both and records both (real vs effective uid, RFC 8693 `act`); *qualified*: it distinguishes them in the mechanism but not in the record, or the reverse; *no precedent*: one identity only; *contradicts*: it deliberately merges actor and subject and argues for that.

**Q2.** How does authority narrow (attenuation), and can it ever widen? What is the mechanism and where does it sit (token, session, process)?
*Supports*: narrowing is a first-class operation that cannot be reversed within the same scope; *qualified*: narrowing exists but a path back exists too (a saved uid, a re-open); *no precedent*: authority is fixed at login; *contradicts*: the mechanism widens by design (supplementary groups, setuid escalation) and the source defends it.

**Q3.** Where is enforcement: one chokepoint, per call, compiled into the query, or in the kernel/hooks?
*Supports*: one chokepoint the caller cannot route around, ideally in the statement itself; *qualified*: one chokepoint with a documented bypass, or per-call checks with a discipline; *no precedent*: enforcement is advisory or in the caller; *contradicts*: many independent checks with no single owner, and the source argues that is correct.

**Q4.** What is the unit of protection: path prefix, object id, relation tuple, label?
*Supports*: the unit is stated and its coverage rule is computable at query time; *qualified*: the unit is clear but coverage needs a walk or a materialised table; *no precedent*: no per-object unit; *contradicts*: the unit conflicts with a stated vfs commitment (path-prefix tenancy, deny rows) and the source argues for it.

**Q5.** Hide vs deny: can a thing be invisible rather than refused? How does traversal interact (directory execute, walk)?
*Supports*: hidden things answer "not found", drop out of every enumeration, and the source states its leak rules; *qualified*: hide exists for some verbs (listing) but not others (search, counts, errors); *no precedent*: refusal only; *contradicts*: the source shows hiding is unachievable or harmful at its tier.

**Q6.** Groups, roles, tenants: modelled how, resolved when (at login, per query)?
*Supports*: the model and the resolution moment are both stated, with the staleness bound; *qualified*: one is stated, the other implicit; *no precedent*: no groups; *contradicts*: a resolution moment that vfs's session law cannot honour (login-time widening) and the source argues for it.

**Q7.** Defaults on creation (umask, inherited ACLs), ownership transfer, move/copy semantics
*Supports*: rules for each, and inheritance only tightens; *qualified*: rules for some, or inheritance that can loosen with an audit; *no precedent*: no defaults, every object configured by hand; *contradicts*: creation inherits the creator's full authority by default and the source defends it.

**Q8.** Audit: what is recorded, attributed to whom, at what version?
*Supports*: every change records actor, subject and version, and reads are recordable; *qualified*: one of the three is missing, or reads are not recorded; *no precedent*: no audit beyond a modification time; *contradicts*: attribution to the intermediary only, defended as sufficient.

**Q9.** Failure modes on record: confused deputy, setuid hazards, TOCTOU, RLS leaks, passthrough
*Supports*: the source names the failure and its structural fix, with an incident; *qualified*: names the failure, offers a discipline rather than a structure; *no precedent*: the class does not arise at that tier; *contradicts*: the source's own history shows the failure and no fix.

**Q10.** Reversibility and permission together: who may revert whose change, can a revert exceed the actor's rights?
*Supports*: a revert is a new change under the same gate, and the source says who may do it; *qualified*: reversibility exists but is ungated or admin-only; *no precedent*: no reversibility; *contradicts*: revert is a bypass by design and the source argues for it.

**Q11.** Scale and portability: does the mechanism survive Oracle/SQL Server caps and 10k-row batches?
*Supports*: the mechanism is bounded and engine-neutral, or the source measures it; *qualified*: bounded on one engine, or unmeasured; *no precedent*: not a database mechanism; *contradicts*: it requires an engine feature vfs's floor cannot declare (RLS as the baseline, a recursive CTE per row).

**Q12.** Take / adapt / reject for vfs, one line each
*Supports* / *qualified* / *no precedent* / *contradicts* do not apply; the memo writes one line per source item and the synthesis collects them.

**Q13.** Many subjects at once: is there any conjunctive (intersection) authority model — acting at the meet of several principals' rights? Who owns what such a session creates, how is it audited, what happens when the set changes mid-session?
*Supports*: the source computes a greatest lower bound over several principals and acts under it (restrictive policies, `cap_rights_limit`, a lowest-clearance session); *qualified*: intersection exists as an operator but not as a session's subject, or ownership and audit of the meet are unstated; *no precedent*: authority is per single principal; *contradicts*: multiple principals widen (union) and the source defends it.

---

## Sources

Repository files, read 2026-09-05, cited above as `file:line`:

- `context/research/2026-09-05-principals-and-permissions-research-plan.md`
  (§1, §1.1, §2, §4, §6).
- `context/research/2026-09-04-yolofs-agent-native-filesystem-threat-model.md`
  (§2.1 to §2.3, §3.4, §4.2, §5.0, §5.2, §5.3, §5.4, §6).
- `context/specs/active/070-principal-scoped-sessions/spec.md` (Intent,
  decisions 1 to 7, the research review's objections 1 to 9, non-goals,
  open questions).
- `context/specs/active/058-row-level-permission-grants/spec.md`
  (Intent).
- `context/decisions/021-row-grant-model-spine.md` (decisions 1 to 4,
  the groups fork).
- `context/decisions/006-global-namespace-tenant-permissions.md`.
- `context/decisions/058-the-access-layer-for-agents-positioning.md`
  (Context, decisions 1 to 8).
- `context/research/2026-09-04-mirage-design-patterns.md` (§3.3, §B:
  §3.6 to §3.13, §4.1 to §4.8).
- `context/research/2026-04-19-mcp-specification.md` (open question 3).
- `context/research/2026-08-10-mcp-2026-07-28-stateless-revision.md`
  (§2.6, §3, §5, §7, §8.2, §8.4).
- `context/standards/mission.md`.
- `context/research/2026-04-22-cloud-permission-models.md`.
- `context/research/2026-09-04-delete-vs-mkedge-race.md` (the TOCTOU
  window).
- `src/vfs/permissions.py` (module docstring), `src/vfs/ops.py` (op
  sets), `src/vfs/rerank.py` (`Statistics`, `_statistics`,
  `lexical_stats`), `src/vfs/models/version.py` (`created_by`),
  `CLAUDE.md` (production posture).

External primary sources, fetched 2026-09-05:

- Norm Hardy, *The Confused Deputy (or why capabilities might have
  been invented)*, ACM SIGOPS Operating Systems Review 22(4), October
  1988. Read from the author's page
  `http://cap-lore.com/CapTheory/ConfusedDeputy.html` (plain http; the
  https path answers 404), with the citation cross-checked against
  `https://en.wikipedia.org/wiki/Confused_deputy_problem`.
- Hao Chen, David Wagner, Drew Dean, *Setuid Demystified*, 11th USENIX
  Security Symposium, August 2002. Read from the USENIX PDF
  `https://www.usenix.org/legacy/event/sec02/full_papers/chen/chen.pdf`
  (downloaded with curl and extracted with `pdftotext`; the abstract,
  §7.1, §8.1.1 to §8.1.3 quoted). The Berkeley mirror
  `people.eecs.berkeley.edu/~daw/papers/setuid-usenix02.pdf` refused
  the connection.
- OWASP GenAI Security Project, *LLM06:2025 Excessive Agency*,
  `https://genai.owasp.org/llmrisk/llm062025-excessive-agency/`.
- OWASP GenAI Security Project, *OWASP Top 10 for Agentic Applications
  for 2026*, announced 9 December 2025,
  `https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/`.
  The OWASP page carries the date and a PDF link only; the ten names
  (ASI01 Agent Goal Hijack, ASI02 Tool Misuse & Exploitation, ASI03
  Identity & Privilege Abuse, ASI04 Agentic Supply Chain
  Vulnerabilities, ASI05 Unexpected Code Execution, ASI06 Memory &
  Context Poisoning, ASI07 Insecure Inter-Agent Communication, ASI08
  Cascading Failures, ASI09 Human-Agent Trust Exploitation, ASI10 Rogue
  Agents) and the two quoted examples were taken from three secondary
  renderings of the list, `https://docs.modulos.ai/frameworks/owasp-top-10-agentic`,
  `https://cycode.com/blog/owasp-top-10-agentic-applications/`, and
  `https://www.paloaltonetworks.com/blog/cloud-security/owasp-agentic-ai-security/`.
  The L5 lens should quote the PDF directly.
- PostgreSQL documentation, *Row Security Policies*,
  `https://www.postgresql.org/docs/current/ddl-rowsecurity.html`
  (permissive vs restrictive, `BYPASSRLS`, the referential-integrity
  covert channel, the `mallory` stale-snapshot example), and *CREATE
  FUNCTION*, the `LEAKPROOF` paragraph,
  `https://www.postgresql.org/docs/current/sql-createfunction.html`.
- Model Context Protocol, *Authorization* (2025-11-25),
  `https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization`
  (Token Handling, Token Audience Binding and Validation, Access Token
  Privilege Restriction, Scope Challenge Handling), and *Security Best
  Practices*,
  `https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices`
  (Confused Deputy Problem, Token Passthrough, Session Hijacking, SSRF
  and DNS rebinding, Scope Minimization). Fetched at the 2025-06-18
  path, which redirects to 2025-11-25.
