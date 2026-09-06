# Lens L5: agent-native identity and permissions as they exist in 2026

- **Status**: research memo, Phase 1 lens L5 of the principals and
  permissions programme (`2026-09-05-principals-and-permissions-research-plan.md`).
  Commits us to nothing. Feeds the Phase 3 synthesis, spec 070, spec
  058, ADR 021, and the `serve()` spec.
- **Date**: 2026-09-05
- **Owner**: Clay Gendron
- **Question**: When an agent acts today, in the harnesses people run,
  the protocols they speak, and the identity products enterprises buy,
  who is the subject, how does authority narrow, where is the check,
  where does the ask go, what is written down, and, above all, whose
  permissions apply when one agent answers a room full of people? Does
  any of it support, qualify, or contradict the plan's hypothesis
  (subject, actor, attenuation) and its multiplayer rule (a subject set,
  intersection for read and write)?
- **Method**: primary-source reads of ten local clones (five parallel
  subagents, one per source group, every citation re-opened by the
  author for the load-bearing claims), plus a web pass over vendor
  documentation and IETF drafts. Clones are cited as `repo:path:line`.
  Web sources are cited by URL with the date read (2026-09-05). Vendor
  pages are vendor claims and are marked as such. The framing memo
  (Phase 0) does not exist yet, so the rubric is the plan's §2, used
  verbatim. What the repo already holds is cited, not redone: the
  Mirage memo §B and §4 (profiles that only narrow, hide vs deny, ask
  with a ledger, explain), the YoloFS memo (the 290-incident threat
  table, progressive permission), the branchfs, agentfs, mcpfs and afs
  memos of 2026-09-04, the two MCP memos, and spec 070's eight-lens
  research review of python-sdk and fastmcp.
- **License** (per source; study freely, copy nothing):
  `opencode` MIT; `gemini-cli` Apache-2.0 at `origin/main` (the plan's
  table says MIT; that is wrong); `deepagents` MIT; `langchain` MIT
  (read only for the human-in-the-loop middleware deepagents imports);
  `claude-agent-sdk-python` MIT; `openai-agents-python` MIT;
  `adk-python` Apache-2.0; `modelcontextprotocol` in transition, its
  `LICENSE` is a notice that new code and specification text are
  Apache-2.0, documentation is CC-BY-4.0, and unconsented older
  contributions remain MIT (`modelcontextprotocol:LICENSE:1-5`, commit
  `edeb0b74`); `A2A` Apache-2.0 (`A2A:LICENSE:1-3`, confirmed present);
  `fastmcp` Apache-2.0. OWASP documents are CC BY-SA 4.0.
- **Sources line**: `opencode` @ `7c2199d84a` (origin/dev, 2026-09-05,
  clean). `gemini-cli` **dirty and not refreshed**: `HEAD` is
  `d42e3f1e7` (2025-08-01, before the policy engine existed) and the
  working tree has been overwritten by an unrelated project ("DATUM
  CLI", 598 dirty entries, `LICENSE` modified); nothing was touched,
  and every gemini-cli citation below is read from `origin/main` @
  `85aca163f` (2026-09-04) with `git show`, written
  `gemini-cli@origin/main:path:line`. `deepagents` @ `0b7b3a5b7`
  (2026-09-06 UTC, clean); `langchain` @ `43bed06205` (2026-08-25).
  `claude-agent-sdk-python` @ `b1b838b` (2026-09-04, clean).
  `openai-agents-python` @ `1d471a4` (2026-09-05, clean). `adk-python`
  @ `a119dd7` (2026-09-05, clean). `modelcontextprotocol` @ `e76e9c57`
  (2026-09-04, clean; the 2026-07-28 release, `draft` identical).
  `A2A` @ `98853be` (2026-09-01, clean; v1.0 spec). `fastmcp` @
  `e3fb4af` (2026-09-04, clean; the library now lives under
  `fastmcp_slim/fastmcp/`, not `src/`). Web: Microsoft Learn (Entra
  Agent ID, Teams shared channels, Copilot), Auth0 and Okta docs,
  IETF datatracker, OWASP GenAI Security Project, code.claude.com and
  claude.com/docs (Claude Code, Claude Tag), slack.com/help and
  docs.slack.dev, support.google.com, all read 2026-09-05.

---

## Bottom line

1. **Nobody in the harness tier has a subject.** opencode, gemini-cli,
   deepagents, the OpenAI Agents SDK and the Claude Agent SDK carry no
   user principal in their permission engines. The only identity that
   reaches a decision is *which agent* is asking. Google ADK is the one
   exception: `user_id` is a property of the session.
2. **The identity tier has the actor/subject split, and ships it.**
   Entra Agent ID makes an agent a directory object with a mandatory
   human sponsor, and an on-behalf-of token whose `sub` is the user with
   an agent facet in the claims. The IETF drafts write it as `act`. The
   hypothesis's Q1 shape is what enterprises are being sold.
3. **Every session in every harness can widen, by a human click.**
   "Always allow" appends an allow rule in all six; three persist it to
   disk; the Claude SDK lets the *callback* answer with
   `setMode(bypassPermissions)` to user settings. Delegation chains do
   not attenuate: subagents in opencode, deepagents and gemini-cli get
   their own rule set, not the parent's intersection.
4. **Enforcement sits in the harness or the tool, cooperatively.**
   deepagents says it in the docstring: "Direct backend usage does not
   currently incorporate permissions." MCP, A2A and OWASP all say the
   check belongs in the resource server, before any query.
5. **Q13, the multiplayer case: no vendor computes an intersection.**
   Every token in every identity system has exactly one subject. The
   two working answers in the field are Claude Tag's "the channel's own
   content and a shared service account, never a person's permissions"
   and Microsoft Copilot's "ground on the asker, detect that others
   cannot see the sources, preview to the asker before sharing".
   Both are approximations of the meet. Neither is the meet.
6. The hypothesis survives with two edits: attenuation is a law about
   what the *session* may do to itself, not about what the *subject*
   may grant; and the subject set is a vfs-local session construct that
   can never cross a wire as a token.

---

## Q1. Who is the subject; how is "acting on behalf of" represented; is the actor distinct?

**Verdict: qualified.** The identity tier supports the split and ships
it. The harness tier has no subject at all. The protocol tier has the
subject (the token's `sub`) and no actor.

**Harnesses.** opencode's permission request carries `sessionID`,
`permission`, `patterns`, `metadata`, `always` and a tool reference,
nothing about a person (`opencode:packages/schema/src/v1/permission.ts:27-35`).
The server has one shared password
(`opencode:packages/opencode/src/server/auth.ts:18-33`), and a session
records an `agent` but no user
(`opencode:packages/opencode/src/session/session.ts:236-243`).
gemini-cli's `PolicyRule` has a `subagent` field and no user field
(`gemini-cli@origin/main:packages/core/src/policy/types.ts:114-193`);
the closest thing to "the user did this" is that slash-command tool
calls are flagged `isClientInitiated` and skip the ask
(`gemini-cli@origin/main:packages/core/src/scheduler/policy.ts:76-88`).
deepagents uses LangGraph's `user.identity` only to namespace a store
(`deepagents:libs/deepagents/deepagents/backends/store.py:117,148`).
The OpenAI Agents SDK's `RunContextWrapper.context` is whatever object
the app supplies (`openai-agents-python:src/agents/run_context.py:72-80`);
the docs' example puts `user_id` in it, the SDK never reads it. The
Claude Agent SDK has `ClaudeAgentOptions.user`, "Optional user
identifier associated with the session", consulted by nothing
(`claude-agent-sdk-python:src/claude_agent_sdk/types.py:2141`); what
does flow into the permission channel is `agent_id`, which names the
sub-agent asking (`types.py:217, 296-309`).

Google ADK is the exception. `Session` has `app_name`, `user_id`, `id`
(`adk-python:src/google/adk/sessions/session.py:39-56`);
`InvocationContext.user_id` is derived from the session
(`src/google/adk/agents/invocation_context.py:399-405`); session lookup
is keyed `(app_name, user_id, session_id)`
(`src/google/adk/sessions/base_session_service.py:92-96`). Credentials
a tool obtains through the OAuth dance are stored per `(app, user)`
(`src/google/adk/auth/credential_service/in_memory_credential_service.py:58-68`).
So ADK's agent acts *as* the user with the user's own credential; there
is no separate actor claim.

**Protocols.** MCP's core is OAuth 2.1 resource-owner delegation. The
subject is the token's `sub`; "user identification MUST be derived from
credentials acquired via MCP authorization when possible (e.g. `sub`
claim)" (`modelcontextprotocol:docs/specification/2026-07-28/client/elicitation.mdx:478`).
The one place the spec distinguishes caller kinds is step-up: "Clients
acting on behalf of a user SHOULD attempt the step-up authorization
flow. Clients acting on their own behalf (`client_credentials` clients)
MAY" (`docs/specification/2026-07-28/basic/authorization/index.mdx:383-384`).
Agent identity is roadmap, not spec: "more and more of the callers are
agents running as cloud workloads with their own identity, acting on
behalf of a user who isn't present, or delegating narrower authority to
sub-agents", with DPoP, Workload Identity Federation, the ID-JAG grant
and "standard token exchange" named as the path
(`modelcontextprotocol:blog/content/posts/2026-08-22-mcp-roadmap.md:57-61`).
The two shipped auth extensions split the world exactly along the
hypothesis's line: Enterprise-Managed Authorization keeps the human as
`sub` and lets the IdP broker access without a consent screen
(`docs/extensions/auth/enterprise-managed-authorization.mdx:42-72`);
OAuth Client Credentials makes the workload the subject and says "If
your integration has a human user who should explicitly authorize
access, use the standard MCP authorization flow instead"
(`docs/extensions/auth/oauth-client-credentials.mdx:26-31, 52-58`).

A2A refuses the question at the payload level: "Identity information is
handled at the protocol layer, not within A2A semantics"
(`A2A:docs/specification.md:1873`); the authenticated identity "could
represent an end user, a client application, or both"
(`A2A:docs/topics/enterprise-ready.md:70-72`). No on-behalf-of field,
no per-task user context.

fastmcp defines the principal as the `(client_id, issuer, subject)`
triple and says why: "Two users of one OAuth client are distinct
principals whenever the token verifier supplies a subject"
(`fastmcp:fastmcp_slim/fastmcp/server/sessions.py:139-148`). It has no
token-exchange or actor helper; the only on-behalf-of guidance is prose
in the proxy docs (use RFC 8693 or Azure OBO with the upstream token as
the assertion, `fastmcp:docs/servers/auth/oauth-proxy.mdx:816-820`).

**Identity products (vendor claims).** Microsoft Entra Agent ID, GA per
Microsoft (https://learn.microsoft.com/en-us/entra/agent-id/whats-new-agent-id),
defines four directory objects: blueprint, blueprint principal, agent
identity, agent user
(https://learn.microsoft.com/en-us/entra/id-governance/agent-id-governance-overview).
An agent identity "is the primary identity an AI agent uses to
authenticate"; it has no credentials of its own and is "Analogous to a
service principal"
(https://learn.microsoft.com/en-us/entra/agent-id/key-concepts;
https://learn.microsoft.com/en-us/entra/agent-id/sign-in-audit-logs-agents).
Microsoft documents three modes of operation: on behalf of a signed-in
user, autonomously as its own service principal, and autonomously as
its own *user* account (an agent with a mailbox)
(https://learn.microsoft.com/en-us/entra/agent-id/agent-oauth-protocols).
"'On-behalf-of' describes the authentication flow, not the type of
agent" (https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id).
In the OBO token "the token represents the user while also identifying
the calling application or agent"; every token "has exactly one subject
and one audience" (same page). The agent marker is the
`xms_par_app_azp` claim naming the blueprint
(https://learn.microsoft.com/en-us/entra/agent-id/how-to-validate-agent-tokens-downstream-api).
Microsoft says plain service principals are "not recommended for AI
agents" because there is "no enforced sponsorship, no agent-aware audit
entries" (key-concepts). So the enterprise is being sold **both**,
layered: the agent is its own directory principal with a mandatory
human sponsor, and it borrows a user's authority through OBO when a
user is present.

Auth0's Token Vault is the pure actor-for-user shape: per-user
third-party tokens, retrieved by an RFC 8693-style exchange, "the agent
only has the permissions that the user has granted"
(https://auth0.com/ai/docs/intro/token-vault). The vault "does not
create a shared organization account"; every member connects their own.
Okta's Cross App Access (XAA) and the IETF Identity Assertion
Authorization Grant (ID-JAG, `draft-ietf-oauth-identity-assertion-authz-grant-04`,
WG-adopted, 2026-05-21) carry `sub` = the user and `client_id` = "the
OAuth 2.0 client ... that will act on behalf of the resource owner"
(https://datatracker.ietf.org/doc/html/draft-ietf-oauth-identity-assertion-authz-grant-04).
The IETF's agent-specific drafts all write the actor as RFC 8693's
`act`: the expired WSO2 draft (`draft-oauth-ai-agents-on-behalf-of-user-02`,
`sub` = user, `act.sub` = the agent, with front-channel consent naming
the actor); the actor profile (`draft-mcguinness-oauth-actor-profile-00`,
`act` requires `sub` and `iss`, recommends `sub_profile` with values
like `ai_agent`, delegation chains as nested `act` objects); and the
transaction-token profile for agents
(`draft-araut-oauth-transaction-tokens-for-agents-02`, `sub` =
principal, `act` = agent, autonomous agents have no `act`). WIMSE gives
the workload its own identity token (WIT, `sub` = the workload) and
carries the user separately in a transaction token
(`draft-ietf-wimse-arch-08` §3.4.6 and §3.4.7;
`draft-ietf-oauth-transaction-tokens-08`).

**What this says about 070's `Principal`.** The field is right and the
shape is one claim short. Every system that has the split records the
actor as a second claim beside `sub` (Entra's blueprint claim, the
`act` object). 070's `Principal(sub, scopes)` has no actor slot.
Whether vfs needs one on the wire is a Phase 3 question; that it needs
one in the audit row is Q8's answer.

## Q2. How does authority narrow, and can it widen? Mechanism and where it sits.

**Verdict: qualified for sessions; contradicts for delegation chains.**
Every harness lets a session grow its own allow set, but always at a
human's hand and never past the human's own authority. Subagents,
however, are not attenuated by their parents in three of the six.

**Where the rules sit and how they narrow.**

| Harness | Rule shape | Priority | Modes |
|---|---|---|---|
| Claude Code | `allow`/`ask`/`deny` arrays; `Tool(specifier)` | deny, then ask, then allow; first match; specificity does not reorder | `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions` |
| opencode | `(permission, pattern, action)` triples | **last match wins** over concatenated rulesets, default `ask` | `--auto` / `--yolo` auto-reply |
| gemini-cli | TOML rules with `priority`, tiers default 1 < extension 2 < workspace 3 < user 4 < admin 5 | sorted by priority, first match; default ask (interactive), deny (non-interactive), allow (yolo) | `plan < default < autoEdit < yolo` |
| deepagents | `FilesystemPermission(operations, paths, mode)` | first match, **default allow** | none |
| OpenAI Agents | `needs_approval`, guardrails, MCP `require_approval`, tool filters | per call | none |
| Claude Agent SDK | `allowed_tools`, `disallowed_tools`, `can_use_tool`, hooks | CLI rules first; callback only when the CLI would ask | the CLI's six |

Claude Code's precedence is documented as "Rules are evaluated in order:
deny, then ask, then allow. The first match in that order determines
the outcome, and rule specificity doesn't change the order"
(https://code.claude.com/docs/en/permissions). Settings layers can only
narrow past a managed file: "If a tool is denied at any level, no other
level can allow it"; managed settings "Nothing you set overrides them";
`auto` and `bypassPermissions` "don't take effect from project or local
settings" (https://code.claude.com/docs/en/settings,
https://code.claude.com/docs/en/permission-modes). A `PreToolUse` hook
returning `allow` cannot override a deny or ask rule, but a blocking
hook does override an allow rule (https://code.claude.com/docs/en/hooks).
This is the one harness whose *policy layers* are narrowing-only by
documented design, and it matches Mirage's "a profile only narrows"
(Mirage memo §3.6).

opencode is the opposite: `evaluate` is `rulesets.flat().findLast(...)`
with a default of `ask`
(`opencode:packages/opencode/src/permission/index.ts:28-38`), and the
per-agent ruleset is `merge(defaults, agentOverrides, userConfig)` with
user config last (`opencode:packages/opencode/src/agent/agent.ts:119-152`),
so a user's `edit: allow` silently beats the built-in plan agent's
`edit: {"*": "deny"}` (`agent.ts:171-175`). deepagents is first-match
with `return "allow"` when nothing matches
(`deepagents:libs/deepagents/deepagents/middleware/filesystem.py:421-433`),
so an early allow beats a later catch-all deny
(`deepagents:libs/deepagents/tests/unit_tests/test_permissions.py:497,504,608`).

**Widening inside a session.** All six.

- Claude Code: "Yes, and don't ask again" writes an `allow` rule to
  `.claude/settings.local.json` at the repo root, applied across the
  repository and its worktrees (https://code.claude.com/docs/en/permissions).
- Claude Agent SDK: `PermissionResultAllow.updated_permissions` carries
  `PermissionUpdate` objects whose `type` may be `setMode` and whose
  `destination` may be `userSettings`, `projectSettings`,
  `localSettings` or `session`
  (`claude-agent-sdk-python:src/claude_agent_sdk/types.py:109-140, 238-244`);
  `ClaudeSDKClient.set_permission_mode("bypassPermissions")` is a
  one-liner (`src/claude_agent_sdk/client.py:284-309`). The SDK
  serializes whatever the callback returns
  (`src/claude_agent_sdk/_internal/query.py:518-522`). The gate and the
  escalator are the same API, and the caller is code, not necessarily
  a person. The CLI may refuse some of this; the SDK cannot tell us.
- opencode: `reply: "always"` appends allow rules for the tool's
  `always` patterns to an in-memory list consulted after config, so it
  wins by last-match (`opencode:packages/opencode/src/permission/index.ts:73,145-151`).
  For `edit`, `read`, `glob` and `grep` the `always` pattern is `"*"`
  (`opencode:packages/opencode/src/tool/edit.ts:105`,
  `tool/read.ts:258`): one click whitelists the whole tool for the
  session. The auto mode can be toggled from the palette mid-session
  (`opencode:packages/tui/src/app.tsx:947-949`).
- gemini-cli: `ProceedAlways` adds an in-memory allow rule at workspace
  tier priority 3.95; `ProceedAlwaysAndSave` also appends it to a TOML
  file (`gemini-cli@origin/main:packages/core/src/policy/config.ts:745-802`).
  The added rule is restricted "to the current mode and more permissive
  modes" (`gemini-cli@origin/main:packages/core/src/scheduler/policy.ts:130-146`),
  sensitive tools cannot be widened without a command prefix
  (`config.ts:734-739`), and `disableAlwaysAllow` turns it off
  (`policy/types.ts:311`). "Always allow" on an edit tool flips the
  whole session into `AUTO_EDIT` (`scheduler/policy.ts:190-201`). The
  approval mode is a mutable field switched by `Config.setApprovalMode`,
  refused for privileged modes only in an untrusted folder
  (`gemini-cli@origin/main:packages/core/src/config/config.ts:2784-2793`).
- OpenAI Agents: `approve_tool(item, always_approve=True)` makes a
  sticky allow per tool identity for the rest of the run
  (`openai-agents-python:src/agents/run_context.py:57-70, 1043-1063`),
  persisted through `RunState.to_json()`.
- deepagents: no runtime widening; decisions are one-shot interrupts.

**Delegation chains.** opencode's subagent ruleset is the parent's
*deny* and `external_directory` rules plus the subagent's own rules;
the docstring says "Parent agent restrictions only govern that agent;
the subagent's own permissions determine its capabilities"
(`opencode:packages/opencode/src/agent/subagent-permissions.ts:4-26`).
deepagents: "Subagents inherit these rules unless they specify their
own `permissions` field, which replaces the parent's rules entirely"
(`deepagents:libs/deepagents/deepagents/graph.py:482-483`), and a
subagent's own `interrupt_on` can switch human review off
(`deepagents:libs/deepagents/tests/integration_tests/test_hitl.py:151-170`).
gemini-cli's rules can name a `subagent` and be more permissive than
the main agent's, though plan mode's catch-all deny still holds
(`gemini-cli@origin/main:packages/core/src/policies/plan.toml:76-80`).
Nobody intersects a child's authority with its parent's. This is the
part of the hypothesis the harnesses contradict: attenuation along the
actor chain is not a law anywhere in this tier.

**Identity tier.** Entra: delegated access "ensures the agent can't
exceed that user's access"; hard ceilings block privileged roles and
four Graph permissions such that "even an administrator can't consent
to give an agent those permissions"
(https://learn.microsoft.com/en-us/entra/agent-id/authorization-agent-id).
Consent is per blueprint, not per agent; a child agent cannot run an
interactive consent flow (`AADSTS82014`)
(https://learn.microsoft.com/en-us/entra/agent-id/agent-on-behalf-of-oauth-flow).
Widening is governance-shaped: the agent "can programmatically request
an access package", routed to approvers, with expiry
(agent-id-governance-overview). Auth0 CIBA is per-transaction widening
by the user (a token bound to `authorization_details`,
https://auth0.com/docs/get-started/authentication-and-authorization-flow/client-initiated-backchannel-authentication-flow/user-authorization-with-ciba).
MCP step-up: the client unions previously granted scopes with the
challenge and re-authorizes; the best-practices tutorial recommends
starting minimal and elevating incrementally, and lists "Treating
claimed scopes in token as sufficient without server-side authorization
logic" as a common mistake
(`modelcontextprotocol:docs/docs/2026-07-28/tutorials/security/security_best_practices.mdx:874-985`).
fastmcp's `require_roles` deliberately cannot be stepped up and
suppresses the scope hint (`fastmcp:fastmcp_slim/fastmcp/utilities/authorization.py:107-140, 170-181`).

**The restatement the evidence forces.** In every case the widening is
a *grant by the subject* (or by an approver above the subject), and the
result never exceeds the subject's own authority. That is already the
YoloFS memo's item 2 in §5.3: "allow and remember" is a grant row;
"deny and remember" is a profile rule. The hypothesis's "a session may
narrow and never widen" holds if "session" means the profile document
and the actor's own doing. It does not hold as a statement about what
happens during a session, because the subject is in the room and may
grant. The law should read: **the session never widens itself; only a
principal with the authority may widen it, and that lands as a grant
attributed to that principal, never as session state.** The Claude SDK
case is the warning: when the ask channel and the grant channel are
the same API, a callback that is code can escalate.

## Q3. Where is enforcement?

**Verdict: supports.** Harness, tool loop, or resource server; the
sources that think about it hardest put the check at the resource,
before any query. Nothing enforces at the data in this tier except by
saying that is where it should be.

- Claude Code: the harness. "Permission rules are enforced by Claude
  Code, not by the model" (https://code.claude.com/docs/en/hooks). Read
  and Edit deny rules also catch recognised file commands inside Bash,
  but "don't apply to arbitrary subprocesses that read or write files
  indirectly"; the OS sandbox (Seatbelt, bubblewrap) is the answer for
  those (https://code.claude.com/docs/en/permissions,
  https://code.claude.com/docs/en/sandboxing).
- gemini-cli: the scheduler runs hooks, then `checkPolicy`, then the
  tool's `shouldConfirmExecute`
  (`gemini-cli@origin/main:packages/core/src/scheduler/scheduler.ts:639-701`);
  decisions travel over a `MessageBus` that auto-answers allow and deny
  and forwards only `ASK_USER` to the UI
  (`packages/core/src/confirmation-bus/message-bus.ts:104-157`). A
  subagent's bus is a derived, untrusted bus that strips
  `forcedDecision` (`message-bus.ts:52-78`). Path confinement uses
  `realpathSync` on roots and targets
  (`packages/core/src/utils/workspaceContext.ts:127-146`).
- opencode: inside each tool, cooperatively. Tools call `ctx.ask(...)`
  before acting (`opencode:packages/opencode/src/tool/edit.ts:102-110`,
  `tool/shell.ts:627`, `tool/write.ts:54`); a tool that forgets is
  unguarded, and `bypassAgentCheck` / `bypassCwdCheck` flags skip
  checks (`tool/task.ts:119`, `tool/read.ts:251`). The "sandbox" is a
  `containsPath` string check with no realpath
  (`opencode:packages/opencode/src/project/instance-context.ts:18-24`).
- deepagents: the tool layer, and it says so. "`FilesystemMiddleware`
  applies these permissions at the tool level for its built-in
  filesystem tools, not at the backend level. Direct backend usage does
  not currently incorporate `permissions`"
  (`deepagents:libs/deepagents/deepagents/graph.py:485-488`). The
  constructor refuses permissions on execute-capable backends rather
  than leave the hole silently
  (`deepagents:libs/deepagents/deepagents/middleware/filesystem.py:1741-1748`),
  and `LocalShellBackend.execute` "can access any path"
  (`backends/local_shell.py:287-288`).
- OpenAI Agents: the runner's tool loop, in process; bypassable only by
  not using the runner.
- ADK: the tool itself. `FunctionTool.run_async` checks the confirmation
  and returns an error dict when it is missing
  (`adk-python:src/google/adk/tools/function_tool.py:267-289`).
- MCP: "MCP servers MUST validate access tokens before processing the
  request ... and take all necessary steps to ensure no data is
  returned to unauthorized parties"
  (`modelcontextprotocol:docs/specification/2026-07-28/basic/authorization/security-considerations.mdx:120`).
- A2A §13.1 is the strongest normative sentence in the whole set:
  authorization checks "MUST occur before any database queries or
  operations that could leak information about the existence of
  resources outside the caller's authorization scope"
  (`A2A:docs/specification.md:3081-3108`).
- OWASP LLM06 mitigation 7: enforce authorization in downstream
  systems, not in the LLM
  (https://genai.owasp.org/llmrisk/llm062025-excessive-agency/).

The pattern is the YoloFS study's H1 row (effect-blind filters, shell
loopholes) reproduced in code: string-matched command rules with
documented gaps, path checks without realpath, tools that must remember
to ask. Each harness's own documentation names the layer below it as
the real boundary. vfs's claim, that the data layer is the only place
the check is not bypassable (ADR 021 D3, ADR 058), is what A2A §13.1
and OWASP #7 say in prose and what deepagents concedes in its
docstring.

## Q4. What is the unit of protection?

**Verdict: qualified.** Tool name plus argument pattern in the
harnesses; path globs where files are involved; OAuth scopes and
relation tuples in the identity tier. Nothing protects by object id.

Claude Code rules are `Tool(specifier)` with path anchors (`//abs`,
`~/home`, relative to the settings file, relative to cwd) and prefix
or glob forms; a deny `Read(./secrets/**)` matches at any depth while
the same string as an allow matches only at the anchored location
(https://code.claude.com/docs/en/permissions). opencode's unit is a
`(permission, pattern)` pair, with bash patterns derived by parsing the
command with tree-sitter, one per simple command
(`opencode:packages/opencode/src/tool/shell.ts:392-411`). gemini-cli
matches `toolName`, `mcpName`, `argsPattern` (a regex over
stable-stringified args) and `toolAnnotations`
(`gemini-cli@origin/main:packages/core/src/policy/types.ts:114-193`).
deepagents protects absolute virtual paths by glob, no `..`, no `~`
(`deepagents:libs/deepagents/deepagents/middleware/filesystem.py:386-420`).
Auth0 FGA for RAG protects by relation tuple, `(user, viewer, doc:id)`
(https://auth0.com/ai/docs/intro/authorization-for-rag). Entra protects
by directory object and Graph permission. Claude Code's
`additionalDirectories` and `blockReadsOutsideWorkingDirectories` are
prefix scopes (https://code.claude.com/docs/en/settings).

ADR 021 D2 (grants on path prefixes) is consistent with every file
rule here. The qualification: the harnesses use patterns with anchor
semantics, not bare prefixes, and Mirage's anchor-depth rule (Mirage
memo §3.6) is the only one of them with a principled precedence. vfs
grants stay prefixes by decision; the pattern grammar is a profile
concern, not a grant concern.

## Q5. Hide vs deny; where does the ask go?

**Verdict: supports.** Hide exists at the tool level in two harnesses;
every ask flow is a pause with a small option set; MCP's ask is now a
result type with a principal-bound state blob, which is exactly the
shape a `pending` Result needs.

**Hide.** Claude Code: a bare tool name in `deny` "removes the tool from
Claude's context entirely" (https://code.claude.com/docs/en/permissions).
opencode hides from the model any tool whose last `*` rule is `deny`
(`opencode:packages/opencode/src/permission/index.ts:204-219`). MCP's
stateless rules let `tools/list` "vary by the authorization presented"
(MCP stateless memo §5). A2A §13.1 treats existence leakage as the
thing the check must prevent. None of the harnesses hides *paths* from
a listing per principal; that remains Mirage's contribution (§3.7).

**Ask flows, side by side.**

| System | Who is asked, over what | Options | Unanswered |
|---|---|---|---|
| Claude Code | the terminal user; `permission_prompt_tool` (an MCP tool) in headless; `--permission-prompts none` denies | once, always (writes a rule), deny; hook `updatedInput` rewrites the call | n/a interactive |
| Claude Agent SDK | `can_use_tool` over the control protocol | allow (with `updated_input`, `updated_permissions`), deny (with `interrupt`) | `anyio.fail_after(60.0)` then `Exception("Control request timeout")` (`_internal/query.py:598-643`): a crash, not a deny |
| opencode | whoever posts to `/permission/{id}/reply` (TUI, headless, ACP editor) | `once`, `always`, `reject` (+ message fed to the model) | TUI blocks forever; `run` without `--auto` auto-rejects; ACP without the capability auto-rejects (`opencode:packages/opencode/src/acp/permission.ts:56-59`) |
| gemini-cli | UI listener on the bus | `ProceedOnce`, `ProceedAlways`, `ProceedAlwaysAndSave`, `ProceedAlwaysServer`, `ProceedAlwaysTool`, `ModifyWithEditor`, `Cancel` (`gemini-cli@origin/main:packages/core/src/tools/tools.ts:1094-1101`) | 60 s bus timeout rejects; no listener means immediate `confirmed:false` (`message-bus.ts:138-153, 226-237`) |
| OpenAI Agents | nobody; the run stops with `RunResult.interruptions` | `approve`, `reject` (+ message), sticky variants; resume with `Runner.run(agent, state)` | a paused state is data; no timeout |
| ADK | the client, via a synthetic `adk_request_confirmation` function call it must answer | `confirmed` true/false with payload; the tool is **re-executed** with the answer attached and the arguments must match (`adk-python:src/google/adk/flows/llm_flows/request_confirmation.py:255-365`) | nothing; the error sits in history |
| deepagents | whoever resumes the LangGraph checkpoint | `approve`, `edit`, `reject`, `respond` | parked in the checkpointer |
| MCP | the user, through the client, via MRTR `InputRequiredResult` carrying an `ElicitRequest` and opaque `requestState` | `accept`, `decline`, `cancel` | n/a |
| A2A | the client agent, via `TASK_STATE_AUTH_REQUIRED`; may chain up to its own client | undefined by the protocol | undefined |
| Auth0 CIBA | the user, by push or email, with a 64-character `binding_message` | approve, reject | `requested_expiry` 1 to 259,200 s, default 300 |

Three facts matter for vfs. First, MCP's `requestState` rules: servers
MUST treat it as attacker-controlled, MUST integrity-protect it when it
influences authorization, and SHOULD embed "the authenticated
principal, rejecting state presented by a different principal", a TTL
and a request digest
(`modelcontextprotocol:docs/specification/2026-07-28/basic/patterns/mrtr.mdx:224-240`).
The spec never says a human must answer; "the protocol does not
mandate any specific user interaction model"
(`client/elicitation.mdx:22-24`), and "MCP servers MUST NOT rely on URL
mode elicitation to authorize users for themselves"
(`elicitation.mdx:503`). Second, A2A §7.6.4: the `AUTH_REQUIRED`
transition "by itself" authorizes nothing, and a credential obtained
in that state "MUST NOT be assumed to authorize subsequent messages on
the Task" (`A2A:docs/specification.md:1964-1972`). That is Mirage's
`ONCE` scope stated as a protocol rule. Third, ADK's re-execution with
argument match, and its refusal to honour a response for a call "this
session never requested" because "the response would get to choose
both the credential it is exchanged with and the endpoint"
(`adk-python:src/google/adk/auth/auth_preprocessor.py:139-146`): the
ask is bound to the exact request, compared field by field, which is
Mirage's ledger rule (§3.9) rediscovered.

The Mirage memo's proposal, `vfs.permission_denied.pending` with a
ledger scoped `once`/`session` (§4.3), sits comfortably on all of this.
The MCP stateless memo's caution (§8.5: keep vfs tools
`resultType: "complete"` until a need exists) still stands; the need
would be an `ask` rung, and when it comes the wire shape is MRTR with
a principal-bound `requestState`.

## Q6. Groups, roles, tenants: modelled how, resolved when?

**Verdict: qualified.** The identity tier resolves groups at token
issuance and hands the result down as scope or claim; the harnesses
have no groups; the protocols carry a tenant as a routing key, not an
authorization fact.

Entra: an agent's user account "can be added to Microsoft Entra
groups, including dynamic groups" but not role-assignable ones
(https://learn.microsoft.com/en-us/entra/agent-id/agent-users); groups
can be sponsors; Conditional Access for OBO targets "users and groups"
(conditional-access/agent-id); access packages can grant an agent
"Security Group memberships". Enterprise-Managed Authorization's whole
pitch is that access is "scoped to the user's groups and roles" with
decisions living "in the IdP admin console"
(`modelcontextprotocol:blog/content/posts/enterprise-managed-auth/index.md:63-81`).
The ID-JAG is issued only if "the user still exists and is active, and
that the user is assigned the Resource Application"
(https://developer.okta.com/blog/2025/06/23/enterprise-ai). gemini-cli
has tiers, not groups: admin policy directories are integrity-hashed
(`gemini-cli@origin/main:packages/core/src/policy/integrity.ts:31-40`).
A2A's new `tenant` field is opaque, echoed verbatim, "semantics
entirely server-defined" (`A2A:docs/topics/multi-tenancy.md:74-108`).
Claude Tag scopes credentials at channel, workspace or org
(https://claude.com/docs/claude-tag/concepts/agent-identity). Auth0's
RAG samples model only `user` and `user:*`; group usersets exist in
OpenFGA but are not demonstrated (looked for, not found).

For ADR 021's open groups fork this is mild evidence for the "resolve
at the edge" lean: every shipping system resolves membership at login
and ships a flat result. It is not evidence against a memberships
table, because the IdP *is* a memberships table; it is evidence that
the query-time predicate should not have to walk one.

## Q7. Defaults on creation, ownership transfer, move and copy

**Verdict: no precedent** for file creation defaults. Two adjacent
facts are worth recording.

Ownership transfer: Entra requires at least one sponsor per agent, and
"sponsorship of the agent identities is automatically transferred to
their manager" when the sponsor leaves
(https://learn.microsoft.com/en-us/entra/agent-id/agent-owners-sponsors-managers).
Creation in a shared space: Claude Tag artifacts are readable by
"Anyone with access to the source Slack channel"
(https://claude.com/docs/claude-tag/concepts/security-and-data); in
Slack Connect "Messages can only be edited or deleted by someone from
the organization from where they were sent"
(https://slack.com/help/articles/115004152843); in Teams shared
channels, content follows the host team's policies. So the field's
default for a thing created in a group context is "owned by the
sender, visible to the room". That is the input Q13's ownership
sub-question needs.

## Q8. Audit: what is recorded, attributed to whom, at what version?

**Verdict: qualified.** Only Entra records actor and subject as
separate fields, and even it attributes risk to the user in OBO.
Harnesses record the decision and, sometimes, the rule; almost none
record who decided.

- Entra: `agentType` on `initiatedBy`, `performedBy` and
  `targetResources` with values `agenticApp`, `agenticAppInstance`,
  `agentIdentityBlueprintPrincipal`, `agentIDuser`; `blueprintId`
  correlates instance to template
  (https://learn.microsoft.com/en-us/entra/agent-id/sign-in-audit-logs-agents).
  But by default "Operations initiated by agent identities appear as
  service principals" and Graph activity logs "don't currently separate
  agent identities" (https://learn.microsoft.com/en-us/entra/agent-id/faq).
  In OBO "risky activity is attributed to the user rather than the
  agent" so remediation hits the user session "without disrupting the
  agent for other users"
  (https://learn.microsoft.com/en-us/entra/id-protection/concept-risky-agents).
- Claude Code: OpenTelemetry `claude_code.tool_decision` with
  `decision`, `source` (`config`, `hook`, `user_permanent`,
  `user_temporary`, `user_abort`, `user_reject`), `tool_name`,
  `tool_use_id`; standard attributes include `session.id`, `user.id`,
  `organization.id` (https://code.claude.com/docs/en/monitoring-usage).
  This is the richest decision record in the set: it names the rule
  source and the human's scope of answer.
- gemini-cli: `ToolCallEvent.decision` in `accept|reject|modify|auto_accept`;
  every rule carries `source`, dynamic rules are tagged
  `'Dynamic (Confirmed)'` (`gemini-cli@origin/main:packages/core/src/policy/config.ts:752`).
  No record of which human answered.
- opencode: `permission.asked` and `permission.replied` bus events with
  `sessionID`, `requestID`, `reply` (`opencode:packages/schema/src/v1/permission.ts:61-65`).
  Nothing records who replied.
- OpenAI Agents: `FunctionSpanData` is `name, input, output, mcp_data`
  (`openai-agents-python:src/agents/tracing/span_data.py:143-160`); no
  decision, no identity. The durable record of approvals is the
  serialized `RunState`.
- ADK: OTel spans carry tool name, agent name, call id and
  `gen_ai.conversation.id`; `user_id` is not on the span
  (`adk-python:src/google/adk/telemetry/tracing.py:224-342`).
- fastmcp: `enduser.id = token.client_id`, ignoring `subject`
  (`fastmcp:fastmcp_slim/fastmcp/server/telemetry.py:43-56`). The span
  names the actor as the end user.
- MCP: "Log elevation events (scope requested, granted subset) with
  correlation IDs" (`security_best_practices.mdx:914-915`); OTel
  context in `_meta` (SEP-414). Logging as a protocol feature is
  deprecated.
- Claude Tag: "There is no per-action log of every task and who asked";
  actions in connected tools appear under the service account in that
  tool's own logs (https://claude.com/docs/claude-tag/admins/audit).

The lesson for ADR 013's version row: record the actor and the subject
as two fields, record the rule or grant that decided, and record the
scope of any human answer (`once`, `session`, `persisted`). Entra's
"appears as a service principal by default" and fastmcp's `enduser.id`
are the two ways to get it wrong, and they are the common ways.

## Q9. Failure modes on record

**Verdict: supports.** The field's taxonomy and the harnesses' own bug
comments line up with the plan's threat model; the new rows are all
about widening and delegation.

**OWASP.** LLM06:2025 Excessive Agency names three causes, excessive
functionality, excessive permissions, excessive autonomy, and eight
mitigations, of which #5 is "execute extensions in the individual
user's context" and #7 is "enforce authorization in downstream systems"
(https://genai.owasp.org/llmrisk/llm062025-excessive-agency/). The
"OWASP Top 10 for Agentic Applications for 2026" was released
2025-12-09 (https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/);
the primary page serves only a PDF, so the item names below are from a
secondary mirror cross-checked against OWASP's own Q1-2026 exploit
round-up, which cites ASI01, ASI03 and ASI10 by name.

| OWASP item | vfs surface | Invariant that must hold |
|---|---|---|
| LLM06 excessive permissions | every verb | effective rights = grants(subject) ∩ profile(actor) ∩ session; the agent never holds more than its subject |
| LLM06 excessive autonomy | `write`, `delete`, `move`, `mkedge`, `run` | `ask` rung on sensitive prefixes (YoloFS §5.3 item 1); delete never destroys (ADR 027) |
| ASI01 goal hijack | `read` (prompt injection through content), then any write | reads gated by the subject's grants (spec 058), so injected text cannot widen |
| ASI02 tool misuse | `run`, `cli` | one door; `run` behind the same gate (YoloFS H1 row) |
| ASI03 identity and privilege abuse | `serve()` edge, `Principal` | identity from the transport only (070 D6); no `principal` tool parameter; `system()` wire-underivable |
| ASI04 supply chain | mounts, MCP-client backends | outbound token rule (070 D7); a mount's declared mode is a ceiling (Mirage §3.6) |
| ASI05 code execution | `run` | not vfs's boundary (plan §6); the namespace is the bounded view |
| ASI06 memory and context poisoning | any write to a path an agent later reads | versions plus attribution: every row names actor and subject (Q8) |
| ASI07 insecure inter-agent communication | the subagent chain, A2A | attenuation along the chain, which no harness does (Q2) |
| ASI08 cascading failures | fan-out, bulk verbs | fail closed on a missing principal (070 D4); row caps |
| ASI09 human-agent trust exploitation | the `ask` flow | the ask is bound to the exact request and spends nothing on a dry run (Mirage §3.9, §3.10; ADK's argument match) |
| ASI10 rogue agents | long-lived sessions | a session cannot edit its own policy (YoloFS §5.3 item 4); one verification, one Principal (070 objection 5) |

**Harness bugs on record.** opencode's arity table has no entry for
`bash -c`, `sh -c`, `eval`, `xargs`, `sudo` or `python -c`, so one
"always" on `bash -c "rm -rf x"` yields the rule `bash *`
(`opencode:packages/opencode/src/permission/arity.ts:1-9, 24-160`,
`tool/shell.ts:409`); `cd`-only commands are never asked
(`opencode:packages/opencode/test/tool/shell.test.ts:953`); the plugin
hook `permission.ask` is declared and never called. gemini-cli's tests
name spoofed MCP server names, redirection bypass, `dir_path` escaping
the workspace, chained git in untrusted workspaces, and infinite
recursion on command substitution
(`gemini-cli@origin/main:packages/core/src/policy/policy-engine.test.ts:804, 1332-1440, 1500, 1621, 1858`);
its docs call workspace-tier TOML insecure. deepagents fixed a `path="."`
bypass of bulk interrupts and an absolute-pattern glob bypass
(`deepagents:libs/deepagents/deepagents/middleware/_fs_interrupt.py:119-134`).
The Claude SDK's hooks on one event "dispatch concurrently"
(`claude-agent-sdk-python:src/claude_agent_sdk/types.py:2131-2136`), its
`can_use_tool` is silently shadowed by whole-tool allows
(`types.py:1834-1862`), and skill names injected into `--allowedTools`
once added rules (`CHANGELOG.md:171`). OpenAI's run-state schema log
shows repeated hardening of sticky approvals (server-label scoping,
exact-call override).

**Protocol threats beyond the ones already covered.** MCP renamed
session hijacking to *state handle hijacking*: "MCP servers MUST NOT
treat possession of a state handle as authentication"; key stored
state as `<user_id>:<handle>` from the verified token
(`modelcontextprotocol:docs/docs/2026-07-28/tutorials/security/security_best_practices.mdx:516-557`).
Elicitation URL cross-user binding: the server "MUST ensure that the
user who started the elicitation request ... is the same user who
completes the authorization flow" (`client/elicitation.mdx:641-660`).
A2A names credential exposure along delegation chains, in-band
credentials "exposing those credentials to each agent"
(`A2A:docs/specification.md:1953-1962`), and push-notification webhooks
where the server authenticates to the client with a secret the client
handed it (`specification.md:3111-3142`). "A task is not a higher-trust
channel" (`modelcontextprotocol:seps/2663-tasks-extension.md:958`).

## Q10. Reversibility and permission together

**Verdict: no precedent.** No source links the right to revert to the
rights of the actor or the subject. The nearest things are edit-before-
approve (gemini-cli `ModifyWithEditor`, deepagents `edit`, the Claude
SDK's `updated_input`), which change the action before it happens, and
the YoloFS staging model (YoloFS memo §3.2, §5.1), which is already in
the repo. Nobody asks whether a revert may exceed the reverter's
rights. The two invariants meet nowhere in this tier.

## Q11. Scale and portability

**Verdict: qualified.** Nothing here touches SQL caps. One precedent
bears directly on S1: Auth0 and OpenFGA document two shapes for
permission-filtered retrieval, pre-filter ("list objects" once, then
intersect with candidates) and post-filter (search, then batch-check
each hit), and recommend pre-filter at scale because one call "returns
the full set of documents the user can read"
(https://openfga.dev/docs/use-cases/rag-authorization;
https://auth0.com/blog/genai-langchain4j-java-openfga-rag/). That is the
plan's "pre-resolved visible-prefix set shipped as a bounded literal"
option, and it is the shape a subject set makes cheapest: intersect
the per-principal visible sets in app code, ship one literal. Entra
caps non-Microsoft platforms at 250 agent identities per blueprint
(FAQ), a product limit, not a mechanism one. Claude Tag caps context at
20 channel messages or 50 thread replies
(https://slack.com/help/articles/53532192117267). Neither says anything
about a 10k batch.

## Q12. Take, adapt, reject

See the table after Q13.

## Q13. Many subjects at once: whose permissions apply in a group?

**Verdict: no precedent** for a computed intersection. Two documented
approximations exist, and they are the two halves of the meet:
restrict to what the *space* holds (Claude Tag), or ground on the asker
and *detect* the divergence before sharing (Microsoft). Governance of
shared spaces between organisations is single-owner, not
most-restrictive, in both Slack and Teams. Every identity token has
exactly one subject, so a subject set cannot exist on the wire.

**What each vendor documents.** Graded against the intersection rule:
*meet* (rights only where every member has them), *space-only* (an
implicit meet, by restricting to content the room itself holds),
*asker* (the asker's rights, reply visible to all: leaks), *asker,
private* (the asker's rights, reply visible only to the asker: no
leak, no group), *undocumented*.

| Surface | Whose permissions | Grade |
|---|---|---|
| Claude Tag in a Slack channel (public beta) | "Claude acts with its own service accounts, rather than as a specific user"; "What it can reach depends on the channel you're in, not on who you are"; "What Claude can do never changes based on who asked" (https://claude.com/docs/claude-tag/concepts/agent-identity). Reads the thread, channel history, pinned items, and public-channel keyword search "the same search any Slack user has" (https://claude.com/docs/claude-tag/concepts/how-it-works). Personal connectors never apply in channels; admin-attached service credentials do, and "whatever the connected account can read or write is available to every member of those channels" (https://claude.com/docs/claude-tag/concepts/security-and-data) | **space-only** for Slack content; **widening past the meet** for connected tools (a shared credential every member may drive) |
| Claude Tag, guest and Slack Connect channels | Disabled by default in any channel with a guest; search is unavailable there because "Search results could include content from channels the guests can't see, the same reason Claude doesn't search private channels"; "Claude doesn't operate in Slack Connect channels ... this isn't configurable" (security-and-data) | the leak rule, applied by **disabling the feature** rather than filtering |
| Claude Tag, DM | the person's own claude.ai account and connectors | asker, private |
| Earlier "Claude Code in Slack" (per user, Pro/Max) | "Each session runs under your own Claude account"; "Users can only access repositories they've personally connected"; reply lands in the channel (https://code.claude.com/docs/en/slack) | **asker** (leak risk to other members) |
| Slack AI / Slackbot | "only use Slack data that members have access to at the time of request"; "Summaries and Slackbot responses will never contain content that you could not otherwise see"; summaries are private to the requester (https://slack.com/help/articles/28310650165907) | asker, private |
| Slack Real-Time Search API (third-party agents) | "your app performs the search on behalf of the authenticated user"; from a Slack Connect channel the scope is "only the channel where it was invoked" (https://docs.slack.dev/apis/web-api/real-time-search-api/) | asker for search scope; **space-only** in Slack Connect; what the app posts is undocumented |
| Microsoft 365 Copilot in a Teams group chat | "Responses from Copilot are grounded in the data of the person who asks"; if every member can access the sources "the full response will automatically be shown to all chat members"; if not, the asker "will receive a preview of the Copilot response before it is shared more broadly" with Approve/Reject, because "Copilot's response may include information that not everyone in the chat has permission to access" (https://support.microsoft.com/en-us/office/copilot-in-teams-chats-2c613de4-cd26-4ae3-9e4b-6905d745d991) | **asker with a leak gate**: the set difference is detected and a human decides |
| Copilot in meetings and the side panel | private chat with Copilot; attendees excluded from the transcript cannot use Copilot; no Copilot in meetings hosted outside the organisation (https://support.microsoft.com/en-us/teams/copilot/catch-up-on-meetings-with-microsoft-365-copilot-in-teams) | asker, private; **membership narrows access** (excluded attendee gets nothing) |
| Gemini in Chat and Ask Gemini in Meet | "Gemini has the same access to Workspace data as you do"; responses "are private to that user" (https://support.google.com/a/users/answer/17010577; https://support.google.com/meet/answer/16024610) | asker, private |
| Gemini "Take notes for me" | derived from meeting speech only; the host chooses recipients (https://support.google.com/meet/answer/14754931) | space-only, host-distributed |
| Teams shared channels (governance) | "Supported conditional access policies from the host organization can be applied to B2B direct connect users. (The external organization's policies aren't used.)"; DLP, retention, labels, communication compliance all inherit from the host; information barriers do not apply to external participants; new members "can see all conversations (even old conversations)" (https://learn.microsoft.com/en-us/microsoftteams/shared-channels) | **host-governed**, not the meet; joining widens the joiner's view of history |
| Slack Connect (governance) | retention "will only apply to messages and files ... sent by your members"; "Messages can only be edited or deleted by someone from the organization from where they were sent"; each org's DLP and eDiscovery reach its own content (https://slack.com/help/articles/115004152843) | **per-sender**, not the meet |
| Entra, Auth0, Okta, IETF | "Each access token has exactly one subject and one audience" (conditional-access/agent-id); the actor profile draft rules concurrent delegation to multiple actors out of scope; Entra's "Batch operations on behalf of multiple users" use case is one OBO token per user, looped (https://learn.microsoft.com/en-us/entra/msidweb/agent-id-sdk/agent-identities) | no construct |
| The six harnesses, MCP, A2A | nothing; one implied user per session; MCP allows one connection to carry several conversations but the principal is the token on each request (`modelcontextprotocol:docs/specification/2026-07-28/basic/index.mdx:193-194`) | no construct |

The plan's phrase "a document in a shared channel is governed by the
meet of both organisations' policies" is not what either vendor
documents. Teams says the host governs and "the external organization's
policies aren't used". Slack says each organisation governs its own
members' messages. The phrase "most restrictive setting applies"
appears in neither help centre (looked for, not found).

**The sub-questions the plan numbered into Q13.**

*Who owns a row the set writes?* Claude Tag: actions in connected tools
appear "under the service account"; artifacts are readable by anyone
with channel access. Slack Connect: the sender's organisation owns the
message. Teams: the host team's policy owns the channel. The field's
answer is "the actor owns it, the room can see it". Nobody attributes a
group-created thing to the group.

*How is the set audited?* Claude Tag: "There is no per-action log of
every task and who asked" (admins/audit). Microsoft logs to the asker
(Copilot grounding is the asker's). Nobody records the room as a
subject.

*Does a principal joining mid-session narrow immediately?* The
evidence runs the other way for *reading history*: Teams new members
see all old conversations; Claude Tag "A bundle on a public channel
grants its access to anyone who joins"; Claude Tag public-channel
memory stays shared even after the channel is made private
(https://claude.com/docs/claude-tag/users/memory). For *future
actions*, Claude Tag has one narrowing rule: a restricted member's
replies "don't reach Claude as content"
(https://claude.com/docs/claude-tag/admins/restrict-access), and
Copilot in meetings excludes attendees who lack transcript access. So
the field's join rule is "joining widens the joiner, never narrows the
room". vfs's intersection rule would be the first to say the opposite,
and it must decide whether a joiner re-grades what the session already
surfaced.

*Hide vs deny for a set?* Claude Tag's guest rule is the leak rule in
practice: the feature that could surface hidden content is turned off,
not filtered. Microsoft's preview gate is the deny form: the reply is
withheld, and "all chat members will receive a message indicating a
response could not be shared", which itself confirms that something
existed. That is exactly the leak Mirage's hide rules forbid (§3.7).
The set case therefore has two shipped precedents and they choose
opposite answers; the plan's "hidden if hidden from any member" has
Claude Tag on its side.

*How does a set compose with the actor's profile and with admin?*
Claude Tag composes by *replacing* the members with a service
account: profile(actor) is the whole answer and the set contributes
nothing except the channel's own content. Microsoft composes by
picking one member (the asker) and testing the others. Nobody
intersects members with an actor profile.

**The read for the hypothesis.** The plan asked where anyone has
computed the greatest lower bound of several people's rights and acted
under it. In this tier, nobody. What ships instead:

1. **Space-only** (Claude Tag, Slack RTS in Slack Connect, Gemini
   notes): the room's own content is, by construction, visible to every
   member, so it is a subset of the meet. Cheap, leak-free, and it
   answers no question that needs a member's private grants.
2. **Asker plus leak gate** (Microsoft): compute with one member's
   rights, then test the reply's sources against the others, and ask
   the asker. This is the `ask` flow standing in for the intersection
   predicate. It detects the set difference rather than avoiding it,
   and its refusal message leaks existence.
3. **Service account per room** (Claude Tag's connected tools): the
   actor's own principal, shared by the room. This is OWASP LLM06
   mitigation #5 deliberately inverted, and Anthropic documents the
   consequence in one sentence. It is the opposite of the intersection
   rule: any member can drive the whole credential.

The intersection rule is stricter than all three and subsumes the
first two: space-only content passes it trivially, and the leak gate
becomes unnecessary because the reply was computed under the meet.
What the field adds is the *join* question and the *existence* leak
in refusals, neither of which the plan's §1.1 has answered yet.

## Take / adapt / reject for vfs

| # | Finding | Source | Verdict |
|---|---|---|---|
| 1 | Record actor and subject as two fields on every version row, plus the rule or grant that decided, plus the scope of any human answer | Entra `agentType`; Claude Code `tool_decision.source`; fastmcp's `enduser.id` mistake | **take** (ADR 013 attribution) |
| 2 | Restate the session law: the session never widens *itself*; a principal with the authority may widen, and that lands as a grant attributed to them | all six harnesses' "always allow"; YoloFS §5.3 item 2 | **take** (the session ADR) |
| 3 | Attenuation along the actor chain is a law vfs must state, because no harness does: a subagent's profile is the parent's profile intersected with its own | opencode `subagent-permissions.ts`; deepagents `graph.py:482`; gemini `subagent` rules | **take** (the session ADR; OWASP ASI07) |
| 4 | The ask channel and the grant channel must be different APIs | Claude SDK `PermissionResultAllow.updated_permissions` with `destination=userSettings` | **take** (spec 054 `serve()`, the `pending` kind) |
| 5 | A pending ask is bound to the exact request, compared field by field, and re-executed against the same arguments; a stale or foreign answer is dropped | ADK `auth_preprocessor.py:139-146`, `request_confirmation.py`; A2A §7.6.4; Mirage §3.9 | **take** (the ask ledger) |
| 6 | The wire shape for `ask` is MRTR: `input_required` plus a `requestState` that embeds the principal, a TTL and a request digest, integrity-protected | `mrtr.mdx:224-240` | **adapt** when an `ask` rung exists; keep tools `complete`-only until then (MCP stateless memo §8.5) |
| 7 | The subject set is a vfs-local session construct; it never crosses a wire as a token | every identity system has one `sub` | **take** (070 D6 extended to the multiplayer ADR) |
| 8 | Space-only as the *default* for a group session: what the room itself holds passes the meet trivially | Claude Tag, Slack RTS in Slack Connect | **adapt**: it is a special case of the intersection, worth naming as the zero-grant baseline |
| 9 | A refusal in a group must not confirm existence; hide-for-any-member is the rule | Microsoft's "could not be shared" message vs Claude Tag's disabled search; Mirage §3.7 | **take** (the visibility ADR; spec 058 `invisible`) |
| 10 | Joining a session narrows the room's future rights and must not re-grade what was already surfaced; the ADR must say which | Teams and Claude Tag widen the joiner instead | **take** as an open decision for the multiplayer ADR |
| 11 | A per-room service account is a *third* principal kind (an actor with its own grants, no subject), and it is what one vendor ships | Claude Tag agent identity | **adapt**: model it as an actor whose profile is its whole authority, sponsored by an admin principal, never as a way around the subject set |
| 12 | Enterprise agent identity = directory principal with a mandatory human sponsor, plus OBO when a user is present | Entra Agent ID | **adapt** for the "agent-as-service-account" question in the authority ADR: a vfs service principal carries a sponsor field in the audit |
| 13 | Pre-filter (resolve the visible set once, ship a literal) over post-filter (check each hit) for permissioned retrieval | OpenFGA / Auth0 RAG guidance | **adapt** into S1's candidates for the subject-set predicate |
| 14 | Groups resolve at the edge into the Principal; the query-time predicate does not walk a membership graph | Entra, EMA/XAA, every harness | **adapt** as evidence toward ADR 021's user-only lean; not decisive |
| 15 | A 60 s timeout that *crashes* the run, or blocks forever, or auto-rejects, depending on the host | Claude SDK, opencode, gemini-cli | **reject** all three as storage behaviour; a pending ask is a Result and timeout is the host's policy (YoloFS memo §5.3) |
| 16 | Last-match-wins rulesets with user config appended last; first-match with a default of allow | opencode; deepagents | **reject**; Claude Code's deny-then-ask-then-allow and Mirage's anchor depth are the precedents to keep |
| 17 | Command-string prefix rules and arity tables | opencode `arity.ts`; Claude Code Bash rules | **reject** for vfs verbs (typed paths, no shell); keep only for `run` and behind the same gate |
| 18 | The tenant as an opaque routing key echoed by the client | A2A `tenant` | **reject** as an authorization input; 070 D6 already forbids identity as data |

## Limits

- The gemini-cli clone is not a gemini-cli checkout. Every citation is
  from `origin/main` via `git show`, never a working file. Nothing was
  refreshed or restored; the dirty tree is Clay's to sort out.
- The Claude Agent SDK is a thin client; the CLI owns the engine. The
  SDK's types and wire format permit escalation from the callback, but
  whether the CLI honours a `setMode(bypassPermissions)` from a callback
  is not knowable from this repo. The finding is about the API shape.
- The OWASP Agentic Top 10 item names come from a secondary mirror,
  cross-checked against OWASP's own round-up for three of the ten. The
  "Threats and Mitigations" v1.1 with T16 and T17 is unconfirmed; the
  primary page still shows v1.0.
- Everything from Microsoft, Auth0, Okta, Anthropic, Slack and Google
  is a vendor claim about documented behaviour, not observed behaviour.
  Okta XAA is marked Early Access in its own admin docs while the
  product page claims broad adoption.
- Claude Tag is a public beta and its documentation changed
  generations during 2026; the earlier per-user Slack app's help page
  now redirects. What the earlier app used for Slack search (the
  tagger's token or the bot token) is not documented.
- No Anthropic page says "Claude will only access channels and files
  the user has access to" in those words; the closest is Claude Tag's
  "the same search any Slack user has".
- Google documents no surface where Gemini posts into a shared space;
  every documented surface is a private side panel. Group-space
  behaviour is undocumented, not absent.
- Neither Slack nor Microsoft documents Copilot or Claude behaviour in
  a *cross-organisation* shared channel beyond Claude Tag's blanket
  refusal and Copilot's "no meetings hosted outside the organisation".
- The IETF drafts on agent identity are, except ID-JAG and identity
  chaining, individual submissions; two have expired. They show the
  direction of the vocabulary (`act`, `sub_profile`, nested chains),
  not a standard.
- Nothing in this lens measures anything. Q11 is a pointer to S1, not
  an answer.
