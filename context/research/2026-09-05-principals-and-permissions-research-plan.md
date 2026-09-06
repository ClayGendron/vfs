# Principals and permissions: the research programme (proposal)

- **Status**: approved by Clay 2026-09-05, with the multiplayer
  addition (§1.1) folded in the same day; running. This is a plan for
  research, not research. It commits us to nothing and produces no
  findings; it says what we will study, how, in what order, and what
  each piece must answer. When approved, each phase below produces its
  own dated memo and this file becomes the programme's index.
- **Date**: 2026-09-05
- **Owner**: Clay Gendron
- **Feeds**: spec 070 (verified principals), spec 058 (row grants),
  ADR 021 (grant spine, proposed), ADR 058 (positioning, proposed), the
  future `serve()` spec, roadmap 023 (per-session namespaces).

---

## 1. The position we are testing

vfs's stance, in Clay's words: *an agent, AI or otherwise, is an entity
that acts on behalf of a principal.* vfs is built for safety, which
means two invariants:

1. **Every action is reversible or versioned.** This one exists
   (ADR 013/017/027: per-entry revisions, delete never destroys).
2. **Every action is scoped to a principal.** Admin is one principal
   among others. This one does not exist: `user_id` is plumbed and
   inert, and the only enforcement is per-mount path rules that treat
   every caller the same.

The research exists to get invariant 2 right, because it is the
product (ADR 058: "the access layer for agents") and because the MCP
server cannot ship before it without shipping fail-open.

### The working hypothesis (to be falsified, not assumed)

Prior art suggests a three-part shape. The research tests it:

- **Subject**: the principal on whose behalf work happens (a person, a
  team, a service, admin) — or, in the multiplayer case (§1.1), a set
  of them.
- **Actor**: the agent doing the work. An actor is not the subject. The
  audit trail names both: *actor X did this on behalf of subject Y*.
  Unix has had this split for fifty years (real uid vs effective uid);
  OAuth token exchange writes it as the `act` claim (RFC 8693).
- **Attenuation**: an actor's authority is at most its subject's, and a
  session may narrow it further and never widen it. Capabilities
  (Capsicum, WASI preopens, Landlock), macaroons and biscuits, AWS
  session policies, and Mirage's "a profile only narrows" all say the
  same thing in different vocabularies.

So effective rights = grants(subject) ∩ profile(actor) ∩ session
narrowing, enforced where the data is (ADR 006/021: compiled into the
query), attributed in the audit to both actor and subject, and never
crossing a wire as a bare identity string (070 D6/D7).

### 1.1 Multiplayer: one actor, many subjects at once

Clay's addition (2026-09-05): an agent often works on behalf of
**several principals at the same time** — Claude tagged in a group chat
is the canonical case. Every reply it writes is seen by every member,
so it must not surface what any one member cannot see, and it must not
change what any one member cannot change. The rule in one line:

> **The session's subject is a set of principals, and the session
> holds a right only when every principal in the set holds it.**

Read and write are each an intersection over the set. This is
least-privilege across people, and it is the opposite of Unix
supplementary groups, where membership *widens* what a process can do.
The hypothesis absorbs it without a new mechanism: attenuation is
already an intersection, so a subject set is just one more term —
effective rights = ⋂ grants(subject_i) ∩ profile(actor) ∩ session
narrowing. What is genuinely new, and what the lenses must look for, is
the prior art for *conjunctive* authority: where has anyone computed the
greatest lower bound of several people's rights and acted under it?
Candidate precedents to test: multi-level security sessions at the
lowest clearance in the room (Bell–LaPadula), Postgres *restrictive*
policies (AND), SpiceDB's intersection operator, Landlock's stacked
rulesets, Capsicum's `cap_rights_limit` (rights only intersect),
macaroon caveats (conjunctive by construction), Slack Connect and Teams
shared channels (a document in a shared channel is governed by the
meet of the organisations' policies), and Google Docs in a meeting.

Open sub-questions the set case adds, numbered into the rubric as Q13:
who owns a row the set writes; how the audit records a set; whether a
principal joining mid-session narrows the session immediately;
whether hide-vs-deny for a set is "hidden if hidden from any member"
(the leak rule says yes); and how a set of subjects composes with the
actor's own profile and with admin.

If the hypothesis survives, 070 and 058 get rewritten around it. If
it breaks somewhere, the research says where and why.

## 2. The questions every lens must answer

One fixed rubric, so memos are comparable and the synthesis is a table
rather than a re-read. Each lens memo answers all thirteen, with
file:line or document citations, and says *no precedent* when that is
the honest answer.

| # | Question | Why vfs needs it |
|---|---|---|
| Q1 | Who is the subject, and how is "acting on behalf of" represented? Is the actor distinct from the subject? | 070's `Principal` shape |
| Q2 | How does authority narrow (attenuation), and can it ever widen? What is the mechanism and where does it sit (token, session, process)? | the session/profile law; roadmap 023 |
| Q3 | Where is enforcement: one chokepoint, per call, compiled into the query, or in the kernel/hooks? | ADR 021 D3, the funnel |
| Q4 | What is the unit of protection: path prefix, object id, relation tuple, label? | ADR 021 D2, the ids-vs-paths fork |
| Q5 | Hide vs deny: can a thing be invisible rather than refused? How does traversal interact (directory execute, walk)? | 058's `invisible` rung, the Mirage leak rules |
| Q6 | Groups, roles, tenants: modelled how, resolved when (at login, per query)? | ADR 021's open groups fork |
| Q7 | Defaults on creation (umask, inherited ACLs), ownership transfer, move/copy semantics | 058's open forks |
| Q8 | Audit: what is recorded, attributed to whom, at what version? | actor/subject attribution, ADR 013 |
| Q9 | Failure modes on record: confused deputy, setuid hazards, TOCTOU, RLS leaks, passthrough | the threat model |
| Q10 | Reversibility and permission together: who may revert whose change, can a revert exceed the actor's rights? | the two invariants meet here |
| Q11 | Scale and portability: does the mechanism survive Oracle/SQL Server caps and 10k-row batches? | CLAUDE.md posture |
| Q12 | Take / adapt / reject for vfs, one line each | the synthesis |
| Q13 | Many subjects at once: is there any conjunctive (intersection) authority model — acting at the meet of several principals' rights? Who owns what such a session creates, how is it audited, what happens when the set changes mid-session? | §1.1 multiplayer |

## 3. What the repo already holds (do not repeat)

| Done | Where | Coverage |
|---|---|---|
| Cloud sharing models (Drive, SharePoint, Dropbox) | `2026-04-22-cloud-permission-models.md` | six invariants; the role ladder |
| Identity plumbing, 8 repo lenses (postgrest, starlette, authlib, python-sdk, fastmcp, sqlalchemy, supabase storage, mcp spec) | spec 070 §Research review | 070's D1–D7; the fail-open objection |
| Grant spine evidence (Postgres RLS, SpiceDB, OpenFGA, Oak) | ADR 021 | four decisions, groups fork open |
| Mirage profiles, hide/show/ask, explain | `2026-09-04-mirage-design-patterns.md` §B | narrowing-only profiles, anchor-depth rules |
| YoloFS 290-incident threat model, staging, progressive permission | `2026-09-04-yolofs-...md` | the threat-model table |
| MCP auth spec, 2026-07-28 stateless revision | `2026-04-19-mcp-specification.md`, `2026-08-10-mcp-...md` | OAuth 2.1, passthrough ban, elicitation |
| branchfs, agentfs, mcpfs, afs | four 2026-09-04 memos | fork/commit, disaggregated state, projection |

**Thin or missing**, and therefore the work:

- The April Unix and Plan 9 memos are about the filesystem, not the
  permission system. On permissions they say two lines each ("mode bits
  are solved", "don't adopt 9P omode"). Nothing on real/effective uid,
  setuid's history, `access()` TOCTOU, directory execute as traverse,
  supplementary groups, umask, NFSv4/POSIX ACLs, jails, Capsicum,
  Landlock, LSM hooks. Nothing on Plan 9's `none` user, per-attach
  authentication, factotum holding keys the process never sees, or
  per-process namespaces as the isolation unit.
- **Capabilities and delegation tokens are unstudied**: Dennis & Van
  Horn, Hardy's confused deputy, Capsicum, WASI preopens, macaroons,
  biscuit, Kerberos constrained delegation, AWS STS session policies and
  `SourceIdentity`, RFC 8693 token exchange in practice.
- **Authorization engines beyond Zanzibar**: Oso (policy compiled to
  SQL filters is exactly 058's problem), Casbin (RBAC/ABAC and the
  BLP/Biba label models), Cedar, OPA, django-guardian, Postgres
  `LEAKPROOF`, Oracle VPD, SQL Server RLS predicates.
- **Agent-native identity as it exists in 2026**: harness permission
  systems (Claude Code allow/ask/deny and hooks, opencode's
  `permission`, gemini-cli's policy engine, deepagents' interrupts),
  Microsoft Entra Agent ID, Okta/Auth0 "Auth for GenAI" (token vault,
  CIBA async approval), the IETF on-behalf-of-user drafts for agents,
  WIMSE and SPIFFE workload identity, A2A agent cards and auth schemes,
  OWASP's agentic top 10 and "excessive agency".
- **Enterprise requirements as a list**: tenants, SCIM groups, expiry,
  break-glass, sensitivity labels, audit retention, least privilege
  for service accounts. Named in passing everywhere, collected nowhere.

## 4. The programme

### Phase 0 — framing memo (half a session)

One short memo that consolidates the threat model and the enterprise
requirement list so every later lens grades against the same targets:

- The threat table: YoloFS's root-cause taxonomy, Hardy's confused
  deputy, MCP's passthrough and session-hijack rules, OWASP agentic
  top 10, "Setuid Demystified" (Chen, Wagner, Dean 2002), RLS leak
  classes. Each row: the failure, the vfs surface it would hit, the
  invariant that must hold.
- The requirement list: the individual developer, the enterprise admin,
  the ETL job, the agent harness, the MCP client, the remote mount. Each
  audience: what it needs to express, what it needs to see in the
  audit, what it must never be able to do.
- The rubric above, frozen.

### Phase 1 — five lens memos (one subagent each, in parallel)

Each memo is a deep read of primary sources with the twelve questions
answered. Clones are refreshed to their upstream default branch and
licenses re-checked before any agent starts (CLAUDE.md rule).

| Lens | Sources (local clones unless noted) | Emphasis |
|---|---|---|
| **L1 Unix lineage** | `unix-history-repo` (V7 `sys/sys/`), `freebsd-src` (`sys/kern/kern_prot.c`, `vfs_subr.c`, NFSv4 ACL, `kern_jail.c`, Capsicum `sys_capability.c`), `linux` (`security/landlock`, `security/commoncap.c`, LSM hooks, `fs/namei.c`), `pjdfstest` (as a conformance-suite model) | real/effective/saved uid; setuid history; `access()` vs `open()`; directory `x` as traverse; groups; umask; ACL allow/deny ordering; jails as tenant layer; Capsicum and Landlock as narrowing-only |
| **L2 Plan 9** | `plan9` (`sys/src/9/port/auth.c`, `chan.c`, `sysfile.c`, `devcons.c`; `sys/src/cmd/auth/`, factotum), `plan9port` (`9pserve`, `lib9pclient`), the papers (*Security in Plan 9*, *The Use of Name Spaces in Plan 9*) | per-attach identity (Tauth/Tattach uname/aname); the `none` user; factotum as the credential the process never holds; per-process namespaces as isolation; `cpu`/`rx` running *as* a user; what the 9P `omode` fails to express |
| **L3 Capabilities and delegation** | `freebsd-src` Capsicum, `WASI` (preopens, `path_open` rights), `wasmtime-py`, `monty`; papers and public docs for Dennis & Van Horn 1966, Hardy 1988, macaroons (Birgisson 2014), biscuit, Kerberos S4U2Proxy, AWS STS `AssumeRole`/session policies/`SourceIdentity`/`ExternalId`, RFC 8693 and the `act` claim; `authlib` for RFC 8693 mechanics | attenuation as a first-class operation; caveats vs policies; who holds the token; the confused deputy solved structurally; delegation chains in the audit |
| **L4 Authorization engines and databases** | `oso` (Polar; `authorized_query` data filtering), `casbin` (models incl. BLP/Biba), `spicedb`, `openfga` (license to confirm), `django-guardian`, `postgres` (`rowsecurity.c`, `LEAKPROOF`, `security_invoker`), `postgrest` (already reviewed; cite only), `storage` (supabase), public docs for Cedar, OPA, Oracle VPD, SQL Server RLS, Zanzibar (zookies vs our version stamps) | policy compiled into SQL predicates; groups resolution; relation vs prefix; consistency tokens; the leak classes; portability against our dialect floor |
| **L5 Agent-native, 2026** | `mirage` (§B done; cite), `agentfs`, `branchfs`, `mcpfs`, `afs` (cite the memos), `opencode/packages/opencode/src/permission`, `gemini-cli` policy engine (Apache-2.0; the local clone was dirty with an unrelated working tree and was read from `origin/main`), `deepagents` interrupts, `A2A` auth schemes and agent cards, `modelcontextprotocol` 2026-07-28 auth + elicitation, `fastmcp`; web: Claude Code and Claude Agent SDK permission docs, Microsoft Entra Agent ID, Okta/Auth0 Auth for GenAI (token vault, CIBA), IETF `draft-oauth-ai-agents-on-behalf-of-user`, WIMSE, SPIFFE, OWASP agentic top 10, YoloFS (cite the memo) | how harnesses express allow/ask/deny today; where the ask goes (elicitation); agent-as-actor vs agent-as-service-account; what enterprises are being sold as "agent identity"; what A2A and MCP each assume about the caller |

To clone (read-only, license first): `cedar-policy/cedar` (Apache-2.0),
`open-policy-agent/opa` (Apache-2.0), `biscuit-auth/biscuit`
(Apache-2.0), `anthropics/claude-agent-sdk-python` (MIT),
`openai/openai-agents-python` (MIT), `google/adk-python` (Apache-2.0),
`spiffe/spiffe` (Apache-2.0). `claw-code` has no LICENSE file: per the
standing rule it is studied through public docs or not at all, and the
clone is deleted. `openfga` and `A2A` show no license text at the
expected path: confirm before use.

### Phase 2 — two measured studies (rerunnable, under `research/studies/`)

Research means new investigation. Two experiments the design cannot be
pinned without:

- **S1 The predicate at scale.** Build a synthetic entry table
  (100k and 1M rows, deep paths, 10k principals, prefix grants with
  realistic skew) on SQLite, Postgres, SQL Server and Oracle (the
  containers already run). Measure, per engine: the read predicate
  (owner OR EXISTS prefix grant) on `list`/`glob`/`grep`/`glean`
  join-back; the write point check; a materialised ACL table
  (Zanzibar-shaped) vs the computed prefix EXISTS; the cost of a groups
  join; the **subject-set predicate** (a right held by every principal
  in a set of 2, 5 and 20 — as nested EXISTS, as a grouped
  `HAVING COUNT(DISTINCT principal) = n`, and as a pre-resolved
  visible-prefix set computed in app code and shipped as a bounded
  literal); and whether any shape breaks the bind-parameter and
  `IN`-list budgets at a 10k batch. Output: a table that decides
  ADR 021 D2/D3 and the multiplayer predicate on numbers rather than
  lean.
- **S2 What ranked search leaks.** Under row grants, `glean` computes
  BM25 over corpus-wide statistics. Do idf and the cross-mount merge's
  exported `lexical_stats` reveal terms of rows the caller cannot see?
  Measure the information an adversarial principal recovers from
  scores alone, then cost the mitigations: per-principal statistics,
  visible-set statistics, coarsened idf. This is the RLS `LEAKPROOF`
  question in vfs's own terms and nobody has asked it of a
  permissioned search filesystem.

Optional, if L5 raises it: **S3 the wire spike** — run `python-sdk` and
`fastmcp` behind a real OAuth 2.1 flow and record which claims actually
arrive at the server, the way the 2026-08-17 verify-authority spike did.

### Phase 3 — synthesis and the decision records (one session)

- One synthesis memo: the twelve questions as a table across the five
  lenses, the two studies' numbers, the hypothesis verdict, and the
  threat table with each row's answer.
- Proposed ADRs for Clay to ratify, each short:
  - **The authority model**: subject, actor, attenuation; the
    intersection law; admin as a principal; what an agent-as-service-
    account is when an enterprise wants one.
  - **The enforcement spine**: ADR 021 ratified, amended or replaced on
    S1's numbers; the groups fork closed.
  - **The session law**: a session narrows and never widens; the profile
    document's shape; where the ask goes.
  - **Attribution**: what every version row records about actor and
    subject; who may revert what.
  - **Visibility**: hide vs deny, and what S2 says about search.
  - **Multiplayer**: the subject set, the intersection law for read and
    write, ownership and attribution of what a set creates, and the
    mid-session change rule.
- Then rewrite 070 and 058 as a spec family against the ADRs, and seed
  the `serve()` auth spec.

## 5. Order and cost

| Phase | Effort | Parallel? | Clay's decision point |
|---|---|---|---|
| 0 framing | half a session | — | approve the rubric and the lens list |
| 1 five lenses | one session wall-clock | five subagents | — |
| 2 two studies | one to two sessions | S1 and S2 in parallel | — |
| 3 synthesis + ADRs | one session | — | ratify the ADRs |

Roughly four sessions before any spec is rewritten. That is the price
of a design that has to hold for enterprises, individuals, ETL, agents,
MCP and remote mounts at once, and it is cheaper than a second rewrite
of the storage funnel.

## 6. What this programme is not

- Not an authentication design. vfs verifies at the edge and ships no
  IdP (070's standing non-goal). The lenses study how identity arrives,
  not how to issue it.
- Not a sandbox. Process isolation, seccomp and container boundaries
  are the harness's business; vfs's boundary is the data.
- Not a rewrite of the reversibility story. Invariant 1 stands; the
  research only asks how it meets invariant 2 (Q10).
