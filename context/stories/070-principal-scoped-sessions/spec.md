# 070 — Verified principals and principal-scoped sessions

- **Status:** draft — decisions from design discussion 2026-07-10
  recorded; `[NEEDS CLARIFICATION]` markers are unresolved forks, not
  omissions. Research review 2026-07-10 (8 repo lenses, primary
  source only: **no fatal objections**; 21 supports / 13 qualified /
  5 no-precedent / 1 contradicts — the contradiction cuts in the
  spec's favor, see review). Factual corrections from the review are
  folded into the sections below; design amendments are recorded in
  the review section and **not adopted** pending owner, except as
  noted. Decision 4 rewritten with owner 2026-07-10
  (`default_principal`; the identity mode is deleted), resolving
  three forks: the open-by-default objection, knob ownership, and
  `Principal.system()` grant bypass. Supersedes
  the identity-threading *phrasing* in 058 ("threaded as `user_id`
  through `_call_storage`") without touching 058's authorization
  semantics.
- **Date:** 2026-07-10
- **Owner:** Clay Gendron
- **Kind:** feature (identity layer — verified caller identity as a
  type, threaded through the funnel, plus a session facade)
- **Depends on:** 056 (storage mounts — one funnel, the threading
  path), 047 (router error vocabulary — the refusal this story adds)
- **Prior art:** 009 (Principal prose, `authz="enforce"` knob — April
  draft, pre-056), 058 (grants consume the caller this story
  delivers), 054 (serve() boundary this story's edge rule binds),
  023 (pre-056 `vfs.session()` for namespace overlays — terminology
  must reconcile, see Decisions), MCP authorization spec + security
  best practices (token passthrough, confused deputy)

## Intent

`user_id` today is a fully-plumbed but inert `str | None`: every
public verb accepts it, `_call_storage` forwards it verbatim into
every storage method, and nothing anywhere verifies or enforces it.
Two properties make it a liability as the MCP server approaches:

- **It is caller-asserted.** Any code path can name any user. A
  privileged layer acting on an identity it never verified is a
  confused-deputy-shaped failure. MCP's security guidance states
  the rule directly — a caller "cannot impersonate another user as
  the user ID is derived from the user token and not provided by
  the client" — and analyzes unverified-identity trust in its
  token-passthrough ban. (Its section *titled* "Confused Deputy" is
  a narrower OAuth-proxy attack; the research review records the
  precise mapping.)
- **It fails open.** `None` silently means "unscoped god-mode," so
  forgetting to pass identity grants everything instead of nothing.

The target trust model, in one line:

> **Verified at the edge. Trusted as data inside. Enforced in
> storage.**

Authentication happens once, at the wire boundary (the future
`serve()`, validating OAuth 2.1 tokens per the MCP authorization
spec). What crosses into the interior is a `Principal` — a value
type that *means* "the edge verified this." Interior layers never
re-verify; storage consumes the principal as trusted data and
enforces it by compiling it into queries (058's job). Within one
process this is misuse resistance and a legible trust contract, not
a cryptographic boundary — the real boundaries are the wire and the
database, and this story keeps both honest.

Authentication itself stays out of scope, as 009 and 058 already
state: VFS ships the type and the verification *seam*, never an IdP.

## Decisions

1. **`Principal` is a frozen value type with one sanctioned
   construction site.** A minimal shape, mirroring the token claims
   it is built from:

   ```python
   @dataclass(frozen=True, slots=True)
   class Principal:
       sub: str                              # verified subject
       scopes: frozenset[str] = frozenset()

       @classmethod
       def system(cls) -> Principal: ...     # named internal actor
   ```

   `sub` deliberately mirrors the OAuth/JWT claim name so the
   token-to-principal mapping is transparent; `owner_id` columns and
   058's `principal_id` store `sub` strings unchanged. The only
   sanctioned construction sites are the auth module's factories
   (`principal_from_token(...)`, `Principal.system()`) and tests —
   a hand-rolled `Principal(...)` literal elsewhere in `src/` is a
   review flag, pinned by a grep-able acceptance criterion rather
   than a runtime mechanism (in-process Python cannot truly forbid
   it, and pretending otherwise would misstate the trust model).

   **`Principal.system()` is wire-underivable.** No token maps to
   it: `principal_from_token` refuses a validly-signed token whose
   `sub` collides with the reserved system subject rather than
   promoting it. System exists only by in-process construction —
   which is the point: a Principal is a *local conclusion* of this
   trust domain's edge, not a portable credential, so authority
   never travels with the value (see the bypass-scope resolution in
   Open questions).

2. **Threading stays per-call through the funnel; the field swaps
   type.** `user_id: str | None = None` becomes
   `principal: Principal | None = None` on every public verb, every
   `_route_*` helper, and every storage-protocol method. The
   topology — one dispatch funnel, identity visible at the single
   chokepoint where 058 will compile it into queries — is a feature
   and survives unchanged. Instance state (identity bound into the
   `VirtualFileSystem` constructor) was considered and rejected: the
   VFS is one long-lived shared object serving many callers, and
   hiding identity from the funnel would move it away from the exact
   point where permissions and query predicates converge.

3. **Storage receives the `Principal`, not a bare string.** Backends
   consume it as trusted data — they verify nothing *of the caller's
   principal* (verification is the edge's job and interior layers
   hold no verification machinery; even token-derived data traveling
   inward is inert) and enforce everything (058's "reads filter
   sets, writes check points"). Scoped to the caller's principal
   deliberately: 009's storage-minted capability tokens (share
   links) will legitimately validate beside storage, because for
   self-issued credentials storage *is* the edge. Passing the full object rather than `sub` keeps
   scopes available at query-compile time when grants land.
   `[NEEDS CLARIFICATION]` Confirm against 058: do the SQL backends
   want the object or just `sub` at the query-construction
   chokepoint? (Lean: the object — narrowing later is free, widening
   later touches every protocol signature again.)

4. **Absence fails closed; privilege is a named, explicit
   default.** *(Rewritten with owner 2026-07-10 — the identity mode
   is deleted; this resolves the review's open-by-default
   objection.)* There is no mode knob. An identity-bearing verb (or
   session open) that reaches the router with no principal — no
   explicit argument and no configured default — is refused with a
   structured error, before resolution, before dispatch. The escape
   hatch is a constructor argument, not a mode:

   ```python
   # ETL / batch jobs — one line, then bare verbs run as system
   vfs = VirtualFileSystem(
       storage=...,
       default_principal=Principal.system(),
   )

   # App / serve() — no default configured; the session is the
   # ergonomic surface, and it requires a principal to open
   async with vfs.session(principal) as s: ...
   ```

   One rule covers both call shapes: an omitted principal falls
   back to `default_principal`; if neither exists, refuse. The two
   driving use cases: *ETL* wants admin to be easy — that is
   `default_principal=Principal.system()`, one named, greppable,
   auditable line (easy the way `sudo` is easy to type, never
   ambient); *App* wants the right thing to be the easy thing —
   the session already is that, since handing a principal to
   `session()` is the only way to get the no-identity-arg verb
   surface. Precedent: PostgREST's `db-anon-role` ("When unset
   anonymous access will be blocked" — openness as a named opt-in,
   never a default) and supabase's `asSuperUser()` (privilege as
   explicit, scoped escalation). The shape generalizes for free: a
   future public read surface is
   `default_principal=Principal.anonymous()` once 058's grants can
   express public reads — same mechanism, no new mode. And the
   former knob-ownership fork resolves by deletion: there is no
   mode for 058 to co-own — 058 enforces against whatever principal
   arrives.

   **Caller identity is not row ownership.** The ETL case makes the
   distinction sharp: a batch job runs *as* `system` but writes
   rows *owned by* many users — so `owner_id` stays data, stamped
   explicitly in the write payload by the admin path, while the app
   path derives it from the caller's principal. Conflating the two
   is how src2's `user_scoped` path rewriting got tangled.

   `[NEEDS CLARIFICATION]` Refusal kind: 047's vocabulary needs an
   *unauthenticated* kind distinct from permission-denied (the
   401/403 split — "who are you" vs "you may not"); the review adds
   PostgREST's nuance (a permission failure for an anonymous caller
   surfaces as unauthenticated) and fastmcp's not-found masking as
   inputs to that fork.

5. **`Session` is a principal-scoped facade, opened as a context
   manager.** The capability layer over the explicit spine:

   ```python
   principal = principal_from_token(token)   # the edge, once

   async with vfs.session(principal) as s:
       result = await s.read("/reports/q2.md")   # no identity arg
   ```

   `Session` holds exactly two things: the `Principal` and its
   lifecycle. Every verb on it delegates into the existing
   `_route_* → _call_storage` funnel with `principal=self._principal`
   — there is no second dispatch path, pinned by an acceptance test
   that session-mediated results equal direct-call results. Interior
   code holding a session cannot name another user, because there is
   no parameter to pass. A closed session refuses further verbs.
   Sessions are cheap per-interaction objects (SQLAlchemy's
   `Engine`/`Session` split; the VFS is the engine); the lifecycle
   exists so future per-session accumulation — locks (054
   territory), audit batching — has a deterministic close point,
   but *this story adds none of it*.
   `[NEEDS CLARIFICATION]` Is the session sugar (bare verbs keep the
   `principal` kwarg for embedding hosts and tests) or the sole
   gateway to identity-bearing verbs when no `default_principal` is
   configured? (Lean:
   sugar — enforcement is principal-*presence* at the funnel, not
   call shape; the sole-gateway rule can tighten later without a
   redesign.)
   **Terminology debt:** 023 used `vfs.session()` for per-session
   *namespace overlays* (pre-056; its mechanics no longer exist as
   written). One word, one concept: if overlays return, they become
   session state on *this* session type, not a second session class.

6. **Inbound wire rule: identity enters from the transport, never
   from tool arguments.** When `serve()` lands, it validates the
   bearer token at a `TokenVerifier`-shaped seam — audience per
   RFC 8707 (MCP's most-repeated MUST); signature, issuer, and
   expiry via OAuth 2.1 §5.2 as the MCP spec incorporates it. The
   seam is a *shape, not a guarantee*: the SDK's `TokenVerifier` is
   just `token -> AccessToken | None`, so VFS's implementation must
   enforce all four checks itself, with audience validation on by
   default (the python-sdk's flagship example ships it off behind a
   flag; do not copy that default) — and never hand-rolled (see the
   authlib row). Past the seam, `serve()` constructs the `Principal`
   and opens the session server-side. No
   served tool ever exposes a `principal`/`user_id` parameter: a
   wire caller asserting identity as data is the confused deputy
   recreated one layer up. This binds the serve() story the same way
   054's topology lock does.

7. **Outbound wire rule: no token passthrough.** An MCP-client
   backend calling a remote server never forwards the token the edge
   received (audience-bound to *this* server; the MCP spec's named
   anti-pattern). Two sanctioned shapes, chosen per trust
   relationship: **trusted subsystem** — the backend authenticates
   as itself and sends `sub` as a data field, acceptable only inside
   a mutual-trust perimeter — or **token exchange** (RFC 8693) when
   the remote is a genuinely separate party. This story ships
   neither; it records the rule and gives the exchanged-token a
   place to hang (`Principal` construction from a new token at the
   client backend). Implementation is future work. One constraint
   recorded now for that work: identities crossing as data are
   namespaced by sender — the receiver maps (issuer/client, `sub`)
   into its own principal space, never bare `sub` and categorically
   never its own `system()` (fastmcp's `(client_id, issuer,
   subject)` session triple is the reference shape).

## Research resources

Reference repos, by which part of the design each informs. All are
cloned as siblings under `~/Git/Repos/` (058's set plus older
clones; the last four shallow-cloned 2026-07-10 for the review).

| Local clone | Upstream | What to study |
| --- | --- | --- |
| `sqlalchemy/` | sqlalchemy/sqlalchemy | The `Engine`/`Session` split (`lib/sqlalchemy/orm/session.py`) and `sessionmaker` — the canonical shared-core / scoped-facade shape decision 5 copies. Also its cautionary history: the `close_resets_only` migration (lenient close retrofitted toward hard refusal) and the interception points (`do_orm_execute`, autoflush) that made the facade non-transparent. |
| `python-sdk/` | modelcontextprotocol/python-sdk | `TokenVerifier` protocol + `AuthSettings` — the edge seam decision 6 implements; one async `verify_token()` past which everything is trusted. Note: its `AccessToken` carries `client_id`/`scopes` and **no `sub`** — VFS's verifier must surface `sub` itself (subclassing is explicitly sanctioned, `provider.py`). |
| `modelcontextprotocol/` | modelcontextprotocol/modelcontextprotocol | The authorization spec (`docs/specification/2025-11-25/basic/authorization.mdx`) — audience validation and the token-passthrough MUST NOT. Security best practices moved to `docs/docs/tutorials/security/` (versioned paths are redirects). The draft (`DRAFT-2026-v1`; the 2026-07-28 RC per the MCP blog, not this repo) leaves both lines this spec relies on byte-stable: copy the seam, not class signatures. |
| `storage/` | supabase/storage | Shared with 058 — RLS policies consuming `auth.uid()`: the verified subject as trusted data inside SQL. Its `owner` → `owner_id` migration pair (tenant/0017, 0018) is the recorded cost of widening an identity field after the fact. |
| `starlette/` | encode/starlette | `starlette/authentication.py` — the minimal principal shape (~150 lines): identity and scopes as separate objects, and **anonymous as a named type** (`UnauthenticatedUser`, installed by the middleware so interior code never sees `None`), decision 4's precedent alongside Django's `AnonymousUser`. |
| `postgrest/` | PostgREST/postgrest | Edge JWT → `SET LOCAL` role + claims GUC → RLS: the full "verify once, enforce in the database" pipeline, in production since ~2015. Fail-closed reference: no token + no configured `db-anon-role` = structured 401 before any planning; anonymous access is an explicit *named* opt-in role, never a null passed through. |
| `fastmcp/` | jlowin/fastmcp | `JWTVerifier` (source lives under `fastmcp_slim/fastmcp/`, `server/auth/providers/jwt.py`) — full signature/expiry/issuer/audience/scope validation at the edge — and `get_access_token()` for how verified claims reach handlers. Also session-credential binding: the transport session id is bound to the verified `(client_id, issuer, subject)` triple; a mismatched credential answers 404, as if the session did not exist. |
| `authlib/` | authlib/authlib | RFC 7662 introspection and the RFC 9068 `JWTBearerTokenValidator` — the full claims-pinning checklist (`iss`/`aud`/`sub`/`exp` as essential; bare `JWTClaims.validate()` checks only time-based claims). **`rfc8693/` upstream is a docstring-only stub** — take token-exchange mechanics from the RFC itself or another implementation. Never hand-roll JWT validation (its docs record the CVE-2016-10555 alg-confusion bypass). |

## Research review (2026-07-10) — eight repo lenses

Eight agents, one per reference repo, graded their assigned
decisions against primary source only (repo-relative file:line
citations, verified by opening the files). 40 verdicts: 21
supports, 13 qualified, 5 no-precedent, 1 contradicts. Factual
corrections surfaced by the review are already folded into the
sections above (the Intent confused-deputy phrasing, decision 3's
"they have no token" rationale, decision 6's validation
attribution, and the authlib / modelcontextprotocol / fastmcp
table rows). Design amendments are **not adopted** — recorded
below as owner forks.

| Spec part | Verdicts |
|---|---|
| Intent trust model | postgrest **supports** (the exact pipeline, shipping since ~2015; `App.hs` verifies once, `PreQuery.hs` is the single identity-to-SQL chokepoint); mcp-spec **supports** (resource server MUST validate per request, 401 on failure) with one **qualified**: the spec's "Confused Deputy" *section* is a narrower OAuth-proxy attack — 070's concern maps to the token-passthrough analysis and the session-hijack rule ("user ID is derived from the user token and not provided by the client"), now cited instead |
| D1 — Principal type, one construction site | python-sdk **qualified** (one-site pattern confirmed at `bearer_auth.py:39-47`; but SDK's `AccessToken` has no `sub`); starlette **qualified** (identity/scopes separation supported — as *two* objects, stronger than one merged frozen value) + **supports** the stay-minimal lean (`BaseUser` is three properties, a decade in production); authlib **qualified** (`sub`+scopes shape supported; bare `JWTClaims.validate()` skips `iss`/`aud`/`sub` unless pinned); frozen-ness: **no-precedent** in both starlette and python-sdk (mutable classes; nothing argues against) |
| D2 — per-call threading, no constructor identity | sqlalchemy **qualified**: shared-core-holds-no-caller-state is direct precedent (`Engine.__init__` stores zero per-caller state, documented process-lifetime concurrent use); but SQLAlchemy's idiom for scoping is the *facade*, never a per-call kwarg on the shared core — the per-call parameter half stands on 056's funnel, not on this precedent |
| D3 — storage consumes trusted data; full object | storage **supports** ("enforced in storage" verbatim: `setScope` re-stamps GUCs per transaction, RLS consumes `auth.uid()`) + **qualified** (it ships the *raw JWT* into SQL as inert data — no-reverification is a discipline, not token absence; and it *does* verify its own signed-URL capability tokens, hence decision 3's caller-principal scoping); postgrest **supports** the full-object lean (whole `AuthResult` — all claims + role — to the single chokepoint, because RLS reads arbitrary claims) |
| D4 — named absence, fail-closed | starlette **supports** named absence (middleware installs `UnauthenticatedUser`; interior code never sees `None`) + **qualified** on fail-closed (its `requires()` is per-endpoint opt-in — an undecorated endpoint is open; 070's funnel-level mode is deliberately stronger); postgrest **supports** (no anon role configured → structured 401 before planning; anonymous is a *named least-privilege role*, opt-in); `system()` specifically: **no-precedent** (nearest analogues: supabase's `asSuperUser()`, postgrest's deliberately least-privilege authenticator role) |
| D5 — session facade | sqlalchemy **supports** the split, `sessionmaker`, and context-manager lifecycle (`__exit__` is `close()`) + **qualified** on closed-refusal (ORM `Session.close()` defaulted to reset-and-reuse for years; the `close_resets_only` retrofit toward hard refusal is the recorded warning) + **qualified** on the equality criterion (Session delegates into the same `Connection.execute`, but autoflush and `do_orm_execute` hooks broke facade transparency — the equality test is 070's own invariant, not inherited); fastmcp **supports** (production principal-scoped sessions: session id bound to the verified `(client_id, issuer, subject)` triple) |
| D5 — explicit threading vs ambient | fastmcp **contradicts** — the one contradiction: FastMCP delivers identity ambiently (ContextVars, `get_access_token()`, DI). Cuts in 070's favor for a library: FastMCP is a *framework* running handlers it does not own (ambient is its only option), and its own code documents the cost — a three-tier staleness fallback for the auth contextvar (issue #1863) plus a Redis snapshot fallback for background workers. A library that owns its funnel avoids that failure class by threading explicitly |
| D6 — inbound wire rule | mcp-spec **supports** (audience validation is the most-repeated MUST; "authorization MUST be included in every HTTP request"; best-practices states the no-identity-as-data rule nearly verbatim); python-sdk **supports** transport-only identity (header → verifier → contextvar; zero identity params in shipped tools) + **qualified** (the seam validates nothing by itself — hence the "shape, not a guarantee" wording above); fastmcp **supports**, mechanically (injected params stripped from the published schema AND wire-supplied values for them discarded) |
| D7 — outbound wire rule | mcp-spec **supports** the passthrough ban ("MUST NOT pass through the token"; the review called it the strongest-supported decision) + **qualified**: the two-shape taxonomy (trusted subsystem / RFC 8693) is 070's own contribution — MCP names the prohibition and requires "a separate token, issued by the upstream authorization server", not the mechanisms; authlib **supports** RFC 7662 and never-hand-roll (CVE-2016-10555) + **no-precedent** on RFC 8693 mechanics and the `act` claim (empty stub upstream; nothing models actor tokens) |

**Objections on record** (each grounded in a citation; none fatal):

1. **Open-by-default** (postgrest, the strongest objection): the
   Intent names fail-open as the liability, then decision 4 ships
   fail-open as the default. PostgREST has *no* configuration where
   absent identity yields unscoped access — openness is an explicit
   named opt-in (`db-anon-role`: "When unset anonymous access will
   be blocked"). Counter-evidence the review also surfaced: MCP
   itself is authorization-OPTIONAL as a whole, strict once enabled
   — so precedent splits between "open until 058" and "named opt-in
   from day one". — **Resolved with owner 2026-07-10:** decision 4
   rewritten around `default_principal`; the mode is deleted and
   absence fails closed from day one, with openness/privilege as a
   named constructor opt-in (the PostgREST shape).
2. **`None` remains a third identity state** (starlette +
   postgrest): both references *normalize absence to a named
   principal at the edge* so interior code never branches on null.
   070 names the system actor but leaves the anonymous caller as
   `None`, conflating "legacy open mode" with "anonymous caller".
3. **Closed-session finality unstated** (sqlalchemy): "refuses
   further verbs" does not say closed is *final* — no
   `reset()`/reopen, ever. SQLAlchemy's `close_resets_only`
   migration is the cost of deciding this lazily.
4. **The equality criterion must outlive this story**
   (sqlalchemy): facades are where interception accretes (autoflush,
   event hooks); the session-equals-direct test has to be a
   permanent invariant that future accumulation (locks, audit
   batching) preserves, not a one-story check.
5. **Principal lifetime vs token refresh** (fastmcp, issue #1863):
   tokens refresh under long-lived transport sessions; a Principal
   is valid only for the verification that minted it — refresh
   means a new Principal and a new session. Implied by "cheap
   per-interaction objects", stated nowhere.
6. **The serve() adapter needs one sanctioned ambient read**
   (fastmcp): MCP frameworks expose verified claims ambiently
   (`get_access_token()`); the edge adapter must perform exactly one
   ambient read, reify the Principal at session open, and interior
   code never reads ambient identity — otherwise implementers will
   recreate contextvar plumbing inward.
7. **The merged Principal keys on `sub`+scopes, not identity**
   (starlette): the same subject with a down-scoped token is a
   *different* frozen value. Identity-keyed lookups (caches, audit
   joins) must key on `sub`, never on the Principal value; and
   Principal is not a subclassing extension point — both should be
   stated, not implied.
8. **`principal_from_token` must pin its claims** (authlib +
   python-sdk): library defaults validate only time-based claims,
   and the SDK's `AccessToken` exposes no `sub` — the verifier must
   require `sub`/`exp` and pin `iss`/`aud` explicitly (the RFC 9068
   `JWTBearerTokenValidator` checklist), or the "transparent
   token-to-principal mapping" is transparent to the wrong thing.
9. **Trusted subsystem needs an audit-attribution story**
   (mcp-spec): MCP's rationale for the passthrough ban includes
   downstream logs misattributing identity; a backend acting as
   itself while carrying `sub` as data must keep per-user
   attribution downstream even inside the trust perimeter.

**Proposed amendments — not adopted, awaiting owner** (each maps to
an open question or a decision edit):

- ~~Default the identity mode to *required*, with open mode an
  explicit named opt-in at construction (postgrest).~~ **Adopted
  2026-07-10, strengthened:** the mode is deleted outright —
  decision 4's `default_principal` is the named opt-in.
- Add `Principal.anonymous()` (or an `is_authenticated` predicate),
  normalized in at the edge, so enforcing-mode interior code never
  branches on `None` (starlette, postgrest).
- State closed-is-final in decision 5, citing the
  `close_resets_only` history (sqlalchemy).
- Promote the session-equality test to a permanent invariant in the
  acceptance criteria (sqlalchemy).
- State the Principal-lifetime rule: one verification, one
  Principal; refresh → new session (fastmcp).
- Decision 6: sanction exactly one ambient read at the serve()
  adapter; forbid ambient reads past session open (fastmcp).
- Decision 1: state that identity-keyed lookups key on `sub` and
  that Principal is closed to subclassing (starlette).
- Decision 6/acceptance: require the serve()-side structural test
  that no published tool schema contains a principal/user_id
  property (fastmcp's mechanical enforcement).
- 047 refusal-kind fork: adopt the 401/403 split (python-sdk's
  `RequireAuthMiddleware`, MCP's error table), plus PostgREST's
  nuance — a permission failure for an *anonymous* caller surfaces
  as unauthenticated, not permission-denied — and record fastmcp's
  third shape (session-credential mismatch answers *not-found*,
  masking existence; starlette documents the same 404-over-403
  option for hiding layout).
- Decision 7: note RFC 7523 JWT-bearer as the implemented
  non-hand-rolled option for the trusted-subsystem shape (authlib),
  and take RFC 8693 mechanics from the RFC, not authlib.

**Evidence toward existing leans** (not new forks): the
full-Principal-at-storage lean is now double-supported (postgrest
threads all claims + role to its one chokepoint; supabase's
`owner`→`owner_id` migration is the recorded cost of widening
late) — with the note that "compiling identity into queries" may
legitimately mean per-transaction context the policy layer reads
(`SET LOCAL role` + claims GUC), not only predicate splicing. The
session-as-sugar lean is supported by sqlalchemy (direct Core path
and Session facade coexist permanently, converging on one
execution funnel). The stay-minimal claims lean is supported by
starlette (three-property user object, richness delegated until a
reader exists) — while supabase/postgrest push the other way the
moment 058's policy layer wants a `role`-like claim.

## Non-goals

- **Authentication itself.** No IdP, no login, no token issuance —
  the hosting runtime owns who the caller is; VFS owns the type and
  the seam. (Unchanged from 009/058.)
- **Authorization semantics.** Grants, levels, query predicates are
  058; share links and capability tokens are 009. This story
  delivers the *input* those layers consume.
- **The serve() transport itself** — 054 plus the future server
  story; decision 6 binds it, this story does not build it.
- **Token exchange implementation** — decision 7 records the rule
  and the seam only.
- **Conversation scoping.** Deliberately not designed here. The one
  shape constraint absorbed now: *session* is the unit of scoped
  interaction, so a future conversation scope arrives as an additive
  constructor argument on `session(...)`, not a redesign. No fields
  are reserved; the session's state surface stays principal +
  lifecycle.
- **`user_scoped` path rewriting** (src2's `/{user_id}/...`
  rewrite, still described in `permissions.py`'s docstring). Whether
  it returns as session-expressed scoping or is subsumed by 058's
  row-space model is 058's reconciliation, not this story's.

## Acceptance criteria

- No public verb, `_route_*` helper, or storage-protocol method
  accepts `user_id: str`; the parameter is
  `principal: Principal | None` everywhere identity flows.
- `Principal` is frozen and hashable; `grep -rn "Principal("` over
  `src/` hits only the auth module's factories — pinned as a test,
  not a convention.
- `principal_from_token` refuses a validly-signed token whose `sub`
  collides with the reserved system subject (structured error, not
  a promoted `Principal.system()`) — pinned as a test.
- With no `default_principal` configured, an identity-bearing verb
  called without a principal returns the structured unauthenticated
  refusal without reaching resolution or dispatch — there is no
  open mode to fall through to.
- With `default_principal` set, a call omitting the principal runs
  as that named principal — verified by asserting the funnel
  receives it, not by behavioral coincidence.
- `Session` is an async context manager: verbs on it take no
  identity argument; a session-mediated call and a direct call with
  the same principal produce equal `Result`s (no second dispatch
  path); verbs on a closed session refuse with a structured error.
- `InMemoryStorage` conforms to the new protocol signatures
  (accepts, may ignore — enforcement is 058's).
- `ruff` and `ty` clean over touched files; tests live in `tests/`.

## Open questions

- Decision 3: full `Principal` vs bare `sub` at the storage
  protocol — confirm against 058's query-construction chokepoint.
- ~~Decision 4: knob ownership~~ — **resolved with owner
  2026-07-10: the knob is deleted.** Decision 4 now ships
  `default_principal` (a named default at construction, no mode);
  058 enforces against whatever principal arrives. Still open from
  that bullet: the unauthenticated error kind in 047's vocabulary
  (see decision 4's remaining marker).
- Decision 5: session as sugar vs sole gateway (for callers with no
  `default_principal` configured).
- `[NEEDS CLARIFICATION]` Claims payload: does `Principal` carry a
  claims mapping now (frozen/hashable tension) or stay `sub` +
  `scopes` until a consumer exists? (Lean: stay minimal — add
  fields when 058/009 name a reader.)
- `[NEEDS CLARIFICATION]` Groups: does the edge resolve memberships
  into the principal at session construction (009's
  `principal_resolver`), or does 058 join a memberships table at
  query time? Decides whether `Principal` grows a `groups` field.
- ~~Does `Principal.system()` bypass 058's grants?~~ — **resolved
  with owner 2026-07-10: it bypasses 058's row-space grants, and
  only those.** The driving use case is ETL: batch jobs populating
  and updating a multi-user filesystem need to read and write
  everywhere, stamping `owner_id` per row as data (decision 4's
  caller-vs-ownership rule). Audit still attributes
  `sub="system"`. The bypass does **not** extend to structural
  configuration: path-space `PermissionMap`, mount rights masks
  (044), and topology locks (054) bind every principal, system
  included — identity-based enforcement is what admin bypasses;
  structure set by the operator binds all callers. And it never
  crosses a wire: a remote mount's far side enforces under its own
  principal space (decisions 6/7), so local admin confers nothing
  remotely. Decided explicitly per Oak's cautionary history; the
  review's PostgREST-style least-privilege-internal-actor lean was
  considered and declined for the batch/admin case.
