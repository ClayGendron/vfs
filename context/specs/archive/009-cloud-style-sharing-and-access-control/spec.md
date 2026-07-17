# 009 — Cloud-style sharing and access control

- **Status:** draft
- **Date:** 2026-04-22
- **Owner:** Clay Gendron
- **Kind:** feature (authorization layer on top of existing `PermissionMap`)
- **Depends on:** §13.11 of `everything_is_a_file.md` (shares as a separate table), existing `src/vfs/permissions.py` (`PermissionMap`), `user_scoped=True` isolation, Article 2 error taxonomy

## Intent

Today VFS has two axes of access control:

1. **Mount-wide `PermissionMap`** — one default permission (`read` / `read_write`) plus directory-prefix overrides, enforced at the five chokepoints in `base.py`. This is *developer* configuration baked into a `VirtualFileSystem` instance; it applies to every caller identically.
2. **User scoping** — `DatabaseFileSystem(user_scoped=True)` prefixes all paths with `/{user_id}/`. This is **isolation, not sharing**. A user can only see their own subtree; there is no way to grant another user access to a path inside it, and there is no shared corpus that distinguishes principals.

The gap: **no per-principal authorization**. VFS today cannot express "Alice can edit `/wiki/synthesis/auth.md`, Bob can only read it, and the `team-research` group can comment on it." It cannot express share links, expirations, or revocations. It cannot express the SharePoint / Drive / Dropbox mental model that most enterprise knowledge lives in.

This story specifies the per-principal authorization layer for VFS — the "shares" layer that `everything_is_a_file.md` §13.11 and the `SupportsReBAC` capability have always named but never landed. It also specifies the share-link (capability-token) surface used by MCP clients and external recipients.

Non-goals of this story (handled by adjacent work):

- Identity / authentication — who the caller *is* is an input; this spec does not define how the system learns that.
- Encryption at rest or in transit — separate concern, separate story.
- Cross-VFS federation — a share on one `VFS` instance does not imply access on another.

## Why

VFS aims to unify enterprise knowledge under Unix semantics and expose it to agents. Enterprise knowledge is fundamentally *shared* knowledge. Three concrete pressures force this layer now:

- **The shared-mount question has no answer.** `DatabaseFileSystem(user_scoped=False)` on a corpus like `/snhu` is currently treated as fully public — every authenticated caller sees everything. There is no middle ground between "private to one user" and "visible to everyone who holds a client handle."
- **Cloud systems are the baseline mental model.** Every user who interacts with knowledge in 2026 already has Drive / SharePoint / Dropbox intuition. Inventing a novel authorization model (or worse, leaking a novel one through) is a product-risk against the "paired with a file-system protocol" positioning.
- **MCP and agent contexts need scoped capabilities.** An agent acting on behalf of Alice should not receive a handle that can read Bob's files, and it should not receive a handle that retains full user-level authority forever. Share links and scoped capability tokens are the natural primitive.

## Research — how the cloud systems do it

This section is normative context for the design decisions below. All findings are from [2026-04-22 research](../../learnings/2026-04-22-cloud-permission-models.md) (research notes file to be written as part of plan phase; this spec captures the pertinent conclusions).

### Google Drive (including Shared Drives)

- **Permission model.** A `Permission` has `type` (`user | group | domain | anyone`), `role` (`owner | organizer | fileOrganizer | writer | commenter | reader`), optional `expirationTime`, and `allowFileDiscovery` (searchability for domain/anyone grants). Returned with a stable `permissionId` scoped to the file.
- **Inheritance.** Folder permissions propagate to descendants. As of September 2025, a document's permissions **cannot be set more restrictive than its parent folder** — you can only add or upgrade. This is a hardening against accidental leakage through mis-scoped children.
- **Shared Drive roles are a separate role ladder.** Content Manager (default for new members) adds/edits/moves but cannot delete; Contributor adds/edits but cannot move or delete; plus Viewer / Commenter.
- **Capabilities field.** The Drive API surfaces a `capabilities{}` object on every file telling the caller what they can do (`canEdit`, `canShare`, `canDelete`, ...) *without* requiring them to try and fail. This is the cleanest cloud-system realization of Article 2 §2 ("declared capabilities").

### OneDrive / SharePoint

- **Scopes and inheritance.** The default model is that every item inherits its parent's permissions. Granting "unique permissions" on an item breaks inheritance and creates a **new permission scope**. Per-site scope count is capped (~50,000 unique scopes per list/library), and SharePoint explicitly documents the performance and governance cost of many broken-inheritance scopes.
- **Sharing link types.** Three canonical types: `SpecificPeople`, `Organization` (anyone in tenant), `Anyone` (anonymous). Creating a "People in your Organization" link on an item breaks inheritance on that item (silently, from the user's perspective). A "People with existing access" link is descriptive-only and does not break inheritance.
- **Sensitivity labels.** Documents and sites can carry labels (`General`, `Confidential`, `Highly Confidential`, ...) that are policy inputs: a `Highly Confidential` label can force the default sharing link to `SpecificPeople`, block `Anyone` links, and drive DLP detection.
- **External sharing is a tenant policy dimension.** Separately configurable from item permissions — a permission that would be valid internally can still be rejected because the tenant forbids external sharing.

### Dropbox

- **Two roles, one owner.** `viewer` / `editor` on both files and folders; exactly one `owner` per folder; creator-is-owner with transfer. Deliberate minimalism — users routinely cite the two-role ladder as the feature, not a limitation.
- **Inheritance with restricted-access holes.** Subfolders inherit parent members by default. "Restricted access" folders (Dropbox Business) break inheritance in the tightening direction and can narrow the audience; they do not broaden.
- **Shared link capabilities.** Password protection, expiration dates, revocation, download disabling, and view-only vs. edit links. Links are capability tokens — possession grants the scoped right until expiration/revocation.
- **Audit.** Admin-visible monitoring of sharing activity is a first-class feature, not an add-on.

### Synthesis — the cross-cutting invariants

Every cloud system, despite surface differences, converges on the same six invariants. VFS MUST respect all six:

1. **Principals are typed.** A grant is to a `user`, a `group`, a `domain`, or `anyone` (public). These are not interchangeable — `anyone` grants have search-discoverability implications, `domain` grants are tenant-bound, `group` grants are dynamic.
2. **Inheritance is the default; breaking inheritance is explicit, expensive, and auditable.** Users don't manage permissions per file; they manage them per folder and let the tree do the work. Unique scopes are a tool of last resort.
3. **The tightening direction is free; the loosening direction is restricted.** You can always add more restrictive permissions to a child. The modern systems increasingly forbid loosening below the parent (Drive 2025) or at least make it auditable.
4. **Sharing is a distinct primitive from permission.** Sharing is an *act* that produces one or more capabilities (a direct grant or a link). Permission is the *state* that results. Confusing the two is the source of most SharePoint complexity.
5. **Capability tokens are first-class.** "The person who holds this link" is a valid principal. Tokens have the same lifecycle primitives as grants: scope, expiration, revocation, audit.
6. **Label-driven policy beats per-item configuration.** At scale, administrators express intent through labels (sensitivity, classification, retention) and let policy convert labels into enforced permissions. Per-item ad-hoc configuration does not survive enterprise scale.

## Scope

### In

1. A per-principal authorization layer (the `Share`) that sits on top of `PermissionMap` and is consulted at the same five chokepoints in `base.py`.
2. A small, closed role ladder specific to VFS — smaller than Drive's, minimally larger than Dropbox's.
3. Inheritance semantics: a share on a directory grants the same role on every descendant, with explicit `inherited=False` ("break inheritance") as a narrowing primitive.
4. Share links as scoped capability tokens with expiration, revocation, optional password, and optional principal binding.
5. The `SupportsReBAC` capability surface (§13.11): declared on a backend the way every other capability is declared (Article 2 §2).
6. An audit trail: every share mutation and every share-link exercise produces an auditable event.
7. Integration with `user_scoped=True`: shares cross the user-scoping boundary (the whole point of a share is cross-user).
8. A label primitive that lets administrators express tenant-wide policy against share surfaces (minimal MVP; deep DLP is out).
9. Machine-readable capability advertisement — every `Entry` MUST carry a `capabilities` field telling the caller what they can do, eliminating trial-and-error.

### Out

1. Authentication. The caller's `principal_id`, group memberships, and tenant are inputs to this layer, not outputs of it. How they are obtained is defined by the hosting runtime (FSP / MCP session, CLI auth, etc.).
2. Encryption (at rest, in transit, client-side). The "Unix block device" caveat in `permissions.py` — that permissions are not a substitute for engine/table isolation — still applies.
3. Cross-tenant federation. A `Share` targeting `tenant:other-corp` is out of scope; external sharing is a `type=anyone` or `type=link` primitive only.
4. Hard link / multi-parent semantics. Share inheritance is a tree, not a DAG. This is consistent with §13.12 of `everything_is_a_file.md` ("no hard links").
5. Role-custom permissions ("writable but no delete", "comment but no download"). The role ladder is fixed and closed. If a use case forces a new role, it is added to the ladder by amendment, not by userland configuration.
6. Full DLP / policy engine. This story defines a label primitive and how it interacts with share creation; deep content-scanning, eDiscovery holds, and retention policies are separate stories.
7. Per-field / per-chunk granularity. Shares apply to namespace paths, which includes chunk, version, and edge paths by inheritance. A share that specifically hides one chunk of an otherwise-visible file is not supported.

## Core model

This story defines six concepts. They compose, and each is primitive in its own layer.

### 1. Principal

A **Principal** identifies who is making a request or who is the subject of a grant. A Principal has one of four closed types:

- `user` — a single human or service account identified by an opaque `principal_id` (the same identifier threaded through `user_scoped=True` today).
- `group` — a named collection of users. Resolution (user → groups) is supplied by the hosting runtime at session construction; VFS does not own the group store.
- `domain` — a tenant or organization. Typically resolved by the host as "every user in the tenant."
- `anyone` — public. A grant to `anyone` is the *only* way to expose a path to a caller whose Principal is unknown. An `anyone` grant MUST be explicit; there is no implicit fallback.

Principals are inputs on every public call, the same way `user_id` is threaded today. The API contract is: **every mutating or reading call receives an authenticated Principal**. A filesystem constructed with `authz="enforce"` refuses calls without one.

### 2. Role

A **Role** is a closed enum describing the subset of operations a principal may perform on a path:

- `read` — can `read`, `stat`, `ls`, `tree`, `glob`, `grep`, `search`, and traverse graph reads. Cannot mutate.
- `comment` — all of `read`, plus may `mkedge` (create `.connections/` edges) and write inside a designated annotation subtree (by convention, `/.vfs/path/__meta__/annotations/...`). Cannot mutate the target file's content or its other metadata.
- `write` — all of `comment`, plus may `write`, `edit`, `delete`, `mkdir`, `move`, `copy` on descendants. The bread-and-butter role.
- `admin` — all of `write`, plus may manage shares on the subtree: create, modify, revoke, issue share links. Cannot delete the root of a mount.
- `owner` — all of `admin`, plus may transfer ownership. A given path has **zero or one** owner at a time; ownership is distinct from `admin` because `admin` may be granted and revoked, ownership must be transferred.

Rationale for exactly five roles:

- Fewer than five leaves no room for `comment` (which is load-bearing for AI-agent use cases where an agent adds edges but is forbidden from mutating upstream content) and conflates `write` with share management.
- More than five (e.g., `fileOrganizer` vs `organizer` vs `writer` distinctions in Drive) imports Google-specific policy choices that do not map to the Unix semantics this project is committed to.
- `owner` is separate from `admin` so that transfer is a first-class operation and cannot be achieved by an `admin` grant on itself.

Roles compare as a total order: `read < comment < write < admin < owner`. A grant at a higher role implicitly includes all lower roles on the same path.

### 3. Share

A **Share** is a row authorizing one Principal at one Role on one path. Its shape:

```text
{
  share_id:    opaque stable id
  path:        absolute, normalized namespace path
  principal:   {type, id}
  role:        read | comment | write | admin | owner
  inherited:   bool (true = children inherit; false = this grant does not propagate)
  issued_by:   principal_id of the admin/owner who created it
  issued_at:   timestamp
  expires_at:  timestamp | null
  label:       optional sensitivity label (see §6)
  revoked_at:  timestamp | null
}
```

Semantics:

- A Share's `path` is a namespace path (absolute, normalized, mount-qualified). The Share resolves via longest-prefix match the same way `PermissionMap` and mount routing do — one mental model.
- `inherited=true` (default) means the grant applies to the path and every descendant.
- `inherited=false` means the grant applies **only to that exact path**, not descendants. This is the building block for breaking inheritance (see §4).
- `expires_at` is enforced at resolution time. Expired Shares do not contribute to the effective role.
- `revoked_at` tombstones the Share without deleting the audit row. Revoked Shares do not contribute to the effective role.
- Shares are addressable through the namespace under `/.vfs/path/__meta__/shares/<share_id>` (consistent with story 002's metadata namespace). `ls` on that directory enumerates shares; `stat` resolves the full Share object. This is the Plan-9-ordinary-file expression of the authorization state.

**Shares live in a dedicated storage table**, not in `vfs_objects`. §13.11 of `everything_is_a_file.md` decided this and the rationale stands: shares are ACLs (metadata *about* the namespace), not entities *in* the namespace. The `/.vfs/.../__meta__/shares/` surface is a synthetic view over that table; no kind `share` exists in the `kind` enum.

### 4. Inheritance and the unique-scope decision

Resolution of the effective role for `(principal, path)`:

1. Collect every non-revoked, non-expired Share whose `path` is equal to or a prefix of the target path.
2. If a Share has `inherited=false` and its `path != target`, drop it.
3. Filter to Shares whose Principal matches the calling Principal (direct user grant, group membership, domain match, or `anyone`).
4. Take the maximum Role across survivors. The effective role for the caller on this path is that maximum.

Two invariants this gives us:

- **Adding a Share never lowers anyone's access.** Shares only grant. There is no "deny" entry. (Rationale: see §"Rejected — deny entries" below.)
- **The most specific Share wins only if it is the highest-role.** Unlike SharePoint's broken-inheritance model, we do not let a more-specific Share *reduce* access below what a more-general Share already granted.

To **reduce** access on a descendant (the "break inheritance" primitive), VFS uses a different tool: **scoped inheritance on the grants above**, not "deny" entries. An admin who wants `/wiki` viewable by tenant but `/wiki/private/*` viewable only by Alice issues:

```
Share(path=/wiki,         principal=domain:acme, role=read, inherited=false)
Share(path=/wiki,         principal=domain:acme, role=read, inherited=true, cone_exclude=[/wiki/private])
Share(path=/wiki/private, principal=user:alice,  role=write, inherited=true)
```

Wait — that's three rows and a `cone_exclude` field, which is creeping. **Better form**: `inherited` is a three-valued `InheritanceMode`:

- `self_only` — this grant applies only to the exact path.
- `descendants` — this grant applies to every descendant but not the path itself (rare).
- `subtree` — this grant applies to the path and every descendant (default).

Combined with the rule "most-general grants resolve first; a Share on a more specific path with role ≥ strictly dominates," the admin declares intent by **granting at the most specific path** and relying on subtree semantics. The cross-cutting rule is:

> **A descendant MUST NOT have more access than its ancestor permits, unless the descendant has its own explicit grant for that Principal.**

This is the Drive-2025 rule. It is simpler than SharePoint's unique-scope model and strictly safer than Dropbox's free-inheritance model. It MUST be enforced at resolution time — a caller whose only grant is on `/wiki` MUST NOT read `/wiki/private/foo.md` unless the tenant-wide grant on `/wiki` covers that path, which (since the admin intentionally did not grant it) it does not. To make the tree shape enforce intent, the admin grants `domain:acme` at `/wiki` with `InheritanceMode.subtree`, and grants `user:alice` at `/wiki/private` with `InheritanceMode.subtree`. The resolver then sees that `domain:acme` has `read` on `/wiki/private/foo.md` (via subtree inheritance from `/wiki`) unless the admin *also* restricts the subtree — which is where the `restrict_subtree` primitive enters:

**`restrict_subtree`** is a narrowing primitive on a Share: it declares that the subtree beginning at one or more specified child paths is not covered by this grant. This is the explicit "break inheritance" signal. Any caller whose only grant is the broader one, hitting a path under a `restrict_subtree`, resolves to "no grant."

```
Share(path=/wiki,         principal=domain:acme, role=read,  mode=subtree,
      restrict_subtree=[/wiki/private])
Share(path=/wiki/private, principal=user:alice,  role=write, mode=subtree)
```

Alice has `write` on `/wiki/private/*`. Other tenant members have `read` on `/wiki` and `/wiki/*` except `/wiki/private/*`, where they have no grant. This is the one model and it covers the space.

### 5. Share links (capability tokens)

A **Share Link** is a capability token that embeds a grant:

```text
{
  token_id:     opaque stable id, the URL-safe form of which is the "link"
  secret_hash:  argon2id hash of the link secret; the secret itself is shown once
  path:         absolute namespace path
  role:         read | comment | write   (admin / owner via link are forbidden)
  principal:    {type, id} | null
                - null means "anyone who holds the link"
                - otherwise, the link is bound to a specific Principal
                  and requires the holder to authenticate as that Principal
  issued_by:    admin/owner who created it
  issued_at:    timestamp
  expires_at:   timestamp | null
  password:     argon2id hash | null (if set, an extra input is required at redemption)
  revoked_at:   timestamp | null
  label:        optional sensitivity label
}
```

Semantics:

- A Share Link is presented at session construction. The hosting runtime resolves it into an effective Principal for the duration of that session.
- A Link whose `principal=null` makes the holder an ephemeral principal `link:<token_id>` — the audit trail records both the link and any already-authenticated principal exercising it.
- Admin and owner roles MUST NOT be issuable via link. A Share Link grants at most `write`. The rationale: share management is a trust boundary; a leaked link should never be able to onboard new shares.
- `expires_at` is REQUIRED for `principal=null` links (the anonymous case); OPTIONAL but recommended for bound links. This is the "no unbounded anonymous access" rule.
- Revocation is by `revoked_at` stamp; the link becomes unusable immediately on the next resolution. Tokens are stateful on the server side — there is no bearer-JWT semantics where revocation lags.

### 6. Sensitivity label (minimal)

A **Label** is a closed enum on each path: `public | internal | confidential | restricted`. Labels are per-path, stored on the Entry, and travel with it. They feed policy:

- `public` — `anyone` grants allowed; `principal=null` links allowed.
- `internal` — `anyone` grants forbidden; `domain` grants allowed; anonymous links forbidden.
- `confidential` — `anyone` and `domain` grants forbidden; only `user` and `group` grants allowed.
- `restricted` — as `confidential`, plus `expires_at` is MANDATORY on every Share (not just links), and `admin` grants are forbidden to non-`owner` issuers.

Label policy is enforced at **share-creation time**, not at resolution time. A write that attempts to create a Share forbidden by the label fails with `PermissionDenied`. This is the "fail early" posture that keeps the resolution fast path simple.

Labels MUST be consulted automatically on path creation: a new file inherits its parent's label. A label may be changed, but only by an `owner` on that path, and the change MUST audit-log.

## What VFS MUST get right

These are the invariants. Violating any of them fails review; they are specific enough to be tested.

1. **Enforcement chokepoints do not grow.** All per-principal checks MUST happen at the existing five chokepoints (`_route_single`, `_route_write_batch`, `_route_two_path`, `_dispatch_candidates`, `mkedge`), plus the analogous read path (a new chokepoint for reads is explicitly added in this story — see §"Implementation"). No surface outside these chokepoints consults shares.
2. **Read operations are checked.** Today's `PermissionMap` does not gate reads; `MUTATING_OPS` is the only guarded set. The per-principal layer MUST gate reads as well. A caller without a grant on `/x` MUST receive `PermissionDenied` on `read`, `stat`, `ls`, `tree`, `glob`, `grep`, `search`, and graph reads; the same taxonomy Article 2 mandates.
3. **`ls` on a path the caller cannot see returns `PermissionDenied`, not an empty listing.** Hiding the existence of a path from an unauthorized caller is explicit (`allowFileDiscovery=false` on the Share, or via label `confidential` / `restricted`); the default is "you are denied, and the denial is visible."
4. **`ls` within an authorized path filters entries.** Children the caller has no grant for do not appear in the listing. This is structurally enforced by resolving each child's effective role during listing.
5. **Search cannot reveal hidden paths.** `search`, `grep`, `glob`, and vector/BM25 backends MUST apply the share filter *before* returning results. A hit on a path the caller cannot read MUST NOT be emitted, even with metadata redacted. This is the "no information leakage via result existence" rule.
6. **The graph layer filters at query time.** The existing `_visible_nodes(user_id)` / `_snapshot(user_id)` mechanism extends to also consult shares. Centrality, pagerank, and traversal results are computed over the Principal-visible subgraph only — no aggregate computed over hidden nodes leaks into visible-node scores.
7. **Capabilities are declared, not probed.** Every `Entry` MUST carry a `capabilities` field listing the operations the current Principal may perform on it. Agents MUST NOT need to try-and-fail to learn their permissions. (Article 2 §2.)
8. **Grant creation is itself gated.** Only `admin` or `owner` on a subtree may create, modify, or revoke Shares within it. The operation `mkshare` funnels through the same chokepoints as mutations.
9. **Share links MUST use hashed secrets and single-shown secrets.** The link secret is shown to the creator exactly once, at issuance. The stored form is an argon2id (or libsodium-equivalent) hash. No secret appears in logs, audit events, or error messages.
10. **Revocation is effective immediately.** Revocation produces no cache lag. Any outstanding session holding a link-derived Principal MUST fail on its next operation after the revocation timestamp. (Implementation: session resolves the link fresh on every call, or shares a revocation listener; either is compliant.)
11. **Expiration is enforced at resolution time, not at storage time.** Expired grants and links are not physically deleted; they are stored with `expires_at` in the past and filtered out at resolution. This supports audit.
12. **Audit events are first-class.** Every `mkshare`, `rmshare`, `link_issue`, `link_redeem`, `link_revoke`, and `label_change` produces an audit row. Reads are auditable on a per-label basis: `restricted` paths MUST audit every read; other labels MAY audit reads at tenant discretion. The audit surface is an opt-in capability (`SupportsAudit`) and the default implementation writes rows to a dedicated table.
13. **Label policy is enforced at share-creation time.** A `mkshare` that would violate label policy fails before the Share is persisted. No eventual-consistency window for policy violation.
14. **No share or link grants `admin` / `owner` by default.** The default role for an ambient `domain` grant (the "everyone in my company can see this" share) is `read`. Loosening the default anywhere is a written decision in `context/decisions/`.
15. **Unknown Principal is never implicit.** A call without an authenticated Principal on a filesystem with `authz="enforce"` MUST fail with `PermissionDenied` and the reason "no principal." There is no "guest" unless the tenant has issued an `anyone` grant for a specific path.
16. **The `Cannot write` classification substring remains load-bearing.** The new `PermissionDenied` errors for read operations MUST begin with a distinct substring (`Cannot read`) so the existing `_classify_error` mapping can route them. (Or, better, fix the substring brittleness in the same iteration — see open question.)
17. **Inheritance direction is narrowing-only via `restrict_subtree`.** The `restrict_subtree` primitive on a Share is the *only* way to carve a smaller audience out of a larger grant. There is no "deny" entry, no "negative ACL," and no rule-precedence mini-language.
18. **`user_scoped=True` composes with shares.** Shares on a user-scoped filesystem name **unscoped** logical paths, exactly as `PermissionMap` does today. Scoping is applied below the authorization layer. A Share targeting `/synthesis` for `user:bob` grants Bob a role on every user's `/synthesis` if the filesystem is scoped; an admin who wants to share only Bob's `/synthesis` either uses a non-scoped mount or grants on the concrete scoped path.
19. **Share administration never crosses mount boundaries.** A Share created on one `VirtualFileSystem` applies to that filesystem only. Even if two mounts share an engine (the Unix-block-device caveat), they are distinct share spaces.
20. **Role ladder is closed at the API boundary.** The five-role ladder is the entire public surface. Adding a role is an amendment to this spec, not a userland feature.

## User-facing and dev-facing customizations

VFS is a library. The customization surface is both developer-facing (the embedding app) and end-user-facing (the agent or human, via FSP/MCP or CLI).

### Developer customizations

- `VirtualFileSystem(authz="enforce" | "off" | "audit-only")`. `off` is today's behavior (shares ignored); `audit-only` logs every decision without enforcing (for staged rollouts); `enforce` is the production mode.
- `VirtualFileSystem(default_label="internal")`. Tenant-default for new paths.
- `VirtualFileSystem(principal_resolver=...)`. Callback that converts the session's authenticated user into the full Principal bundle (user + groups + domain). Owned by the host (FSP session, CLI) — VFS does not call IdPs directly.
- `VirtualFileSystem(audit_sink=...)`. Callback receiving audit events. Defaults to a dedicated table in the backing store.
- `VirtualFileSystem(label_policy=...)`. Map from label to the rules in §6. Defaults are published; tenants MAY override within the constraint that `restricted` can only be made *stricter*.
- Backend `capabilities` declaration extends by one flag: `SupportsReBAC`. Backends that don't declare it MUST be constructed with `authz="off"` — enforcing shares on a backend that can't store them is a configuration error.

### End-user customizations

Exposed as namespace operations and new public API:

- `mkshare(path, principal, role, inheritance=subtree, expires_at=None, restrict_subtree=())` — create a Share. Requires `admin` on the path.
- `rmshare(share_id)` — revoke a Share. Requires `admin` on the Share's path. Revocation stamps, does not delete.
- `mklink(path, role, principal=None, expires_at=None, password=None)` — issue a Share Link. Returns the secret once; stored form is hashed.
- `rmlink(token_id)` — revoke a link.
- `stat(path)` returns the `capabilities` field (what the caller may do) and, for `admin` callers, the full share list. Non-admin callers see only their own grant.
- `ls(/.vfs/<path>/__meta__/shares/)` enumerates shares (visible to `admin`).
- `set_label(path, label)` — only `owner` on the path may change the label.

CLI / FSP surface follows directly: one MCP tool each (`vfs.share.create`, `vfs.share.revoke`, `vfs.link.issue`, `vfs.link.revoke`, `vfs.label.set`) and the capabilities field on every `Entry` answered by `stat`.

## Threat model

This section names concrete attacks the design must defeat. Each one corresponds to at least one MUST in §"What VFS MUST get right."

| Attack | Defense |
|---|---|
| **Caller without authentication reads anyone's files** | Invariant 15: no implicit "guest." `authz="enforce"` + unresolved Principal → `PermissionDenied`. |
| **Caller reads hidden subtree via `ls`** | Invariant 4: `ls` filters by effective role. |
| **Caller enumerates hidden paths via search or grep** | Invariant 5: search backends apply the share filter *before* scoring/emission. |
| **Caller infers content of hidden file via graph centrality / pagerank** | Invariant 6: graph filters at query time; aggregates computed over visible subgraph only. |
| **Caller probes permissions via trial-and-error** | Invariant 7: `capabilities` field on every `Entry`. |
| **Leaked share link grants indefinite access** | Invariants 10, 11: revocation is immediate; anonymous links require `expires_at`. |
| **Leaked share link grants admin / ownership transfer** | Invariant in §5: links cap at `write`. |
| **Admin-grant escalation (admin grants themselves owner)** | Role ladder in §"Core model": only an `owner` may grant `owner` (and ownership transfer is a single-winner operation, not an additive grant). |
| **Share management side-channel via metadata paths** | Invariant 1: all checks at chokepoints; `/.vfs/<path>/__meta__/shares/` is a synthetic view; writes to it funnel through `mkshare`. |
| **Bypass via shared SQL engine** | Inherited from `permissions.py`: mount per engine, don't share engines across trust boundaries. This story does not fix it; Invariant 19 documents it. |
| **Bypass via `user_scoped=True` edge cases** | Invariant 18: shares composed *above* scoping. Test coverage required for the combination. |
| **Silent expiration miss (an expired grant still resolves)** | Invariant 11: expiration checked on every resolution. |
| **Log exfiltration of link secrets** | Invariant 9: secrets never leave the creation call; only hashes stored; audit log receives `token_id`, not the secret. |
| **Race between revocation and in-flight call** | Invariant 10: every call resolves shares/links fresh. No caller-side cache of authorization state; revocation-to-effect latency is one RTT. |
| **Label downgrade (an admin lowers `restricted` to `internal` to share widely)** | §6: only `owner` may change a label; label change is audited. |
| **Cross-mount data conflation** | Invariant 19: shares are per-`VirtualFileSystem`. |

## Rejected alternatives

- **Deny entries.** SharePoint, AWS IAM, and POSIX ACLs all support explicit deny. They converge on "deny always wins, precedence rules are subtle, users get confused." VFS follows the Drive / Dropbox / ReBAC convention: grants only, plus `restrict_subtree` as the one narrowing primitive. The rejected alternative's only advantage is expressive power; its costs are a precedence mini-language and a wide class of security bugs where a later-added grant silently reveals previously-hidden data.
- **Glob / regex in share paths.** Same reasoning as §3.3 of `directory_level_permissions.md`. Path prefixes only.
- **POSIX mode bits (owner/group/world rwx).** Constitution Article 3 "Rejected" list. The three-axis model cannot express `anyone` vs `domain` vs `group` distinctions that cloud systems and agents both need.
- **Custom permission levels / per-role operation whitelists.** Rejected per "Out" item 5. If a new axis is needed, extend the role ladder by amendment.
- **Bearer JWTs for share links.** JWTs optimize for stateless verification at the cost of revocation latency. VFS optimizes for revocation-in-one-RTT and accepts the stateful token table. Invariant 10 is non-negotiable.
- **Per-file permissions as rows in `vfs_objects`.** §13.11 of `everything_is_a_file.md` already rejected this. Shares are ACLs, not namespace entities.
- **Acting without an authenticated Principal (a "public VFS" mode).** This is the user-scoped-false mount today. Keeping it as `authz="off"` for small deployments is allowed but distinct from production posture. Production MUST run `authz="enforce"`.
- **Loosening children below parent (pre-2025 Drive semantics).** Adopted the hardened 2025 rule. It is a small loss of expressive power and a large win for accident-proofing.
- **Tenant-wide "external sharing off" toggle** as a VFS-level primitive. That belongs in the host's tenant policy. VFS exposes labels and the host converts policy into per-mount label defaults.

## Acceptance criteria

A caller on a `VirtualFileSystem(authz="enforce")` can, through the public API only (no driver-level or storage-level side channels):

1. As an `admin` on `/` (or `owner`), grant `user:alice` `write` on `/wiki/synthesis`. Alice can then `write` a markdown file into that subtree, read it back, and `ls` it.
2. As `user:bob` (no grant), attempt to `read` the same file and receive `PermissionDenied`. Bob's `ls /wiki/synthesis` also returns `PermissionDenied`.
3. As an `admin`, issue a share link on `/wiki/synthesis/spec.md` at role `read` with a 7-day expiration. A fresh session constructed with that link's secret can `read` the file and nothing else. After the admin calls `rmlink`, the next call on that session returns `PermissionDenied`.
4. Grant `group:research` `read` on `/wiki` with `InheritanceMode.subtree` and `restrict_subtree=[/wiki/private]`. A member of `research` can `read` files under `/wiki/drafts` but not under `/wiki/private`.
5. The same member's call to `search("auth")` does not return results whose path is under `/wiki/private`, even when those files contain the search term.
6. `stat("/wiki/synthesis/spec.md")` on a session bound to Alice returns a `capabilities` field that includes `can_write`, `can_edit`, `can_delete`, but on a session bound to Bob (with no grant) returns `PermissionDenied` — *not* a stat with capabilities all `false`.
7. Attempt to `mkshare(path=/wiki/secret/*.md, principal=anyone, role=read)` on a path labeled `restricted`. The call fails with `PermissionDenied` and a reason citing the label policy. No Share is persisted.
8. Every operation above produces audit rows with the expected `actor`, `action`, and `resource` fields. No audit row contains a link secret.
9. On a filesystem with `user_scoped=True`, granting `user:alice` on `/synthesis` lets Alice see `/bob/synthesis` — because share paths are unscoped logical paths, which is how the existing `PermissionMap` works. Tests demonstrate this is the documented behavior and is visible in the user-scoping rules.
10. A backend not declaring `SupportsReBAC` refuses construction with `authz="enforce"`. Construction with `authz="off"` succeeds, and the system behaves identically to today.

## Open questions (blocking design finalization)

1. **Per-principal share resolution cost.** Each call resolves shares across all prefix-matching rows; at N shares on a path chain and M groups on a user, resolution is O(N·M). Is this acceptable at 10^5 shares per tenant, or do we need a resolver cache invalidated on share mutation? Lean: start without cache, add when measured. Logged to `open-questions.md`.
2. **Group resolution source of truth.** The spec says the host supplies `principal.groups` via `principal_resolver`. Do we also need a VFS-native `group` primitive for groups that exist *only* inside a VFS (e.g., `/groups/research` as a file)? Lean: no — that's the host's concern. Flag in `open-questions.md` with a "revisit at adopter request" note.
3. **Should `owner` transfer be atomic with a forcing function** (i.e., a path always has exactly one owner; transferring creates+deletes in one transaction), or can a path be temporarily ownerless during migration? Lean: atomic; zero-owner states are a class of bug.
4. **Does the existing `WriteConflictError` taxonomy split into `WriteConflict` and `PermissionDenied`** (the correct Article 2 category for authorization failures), or are share-denied writes reported as `WriteConflict`? The current `check_writable` in `permissions.py` uses `"Cannot write"` → `WriteConflictError`. For authorization this is wrong — authorization failures belong in `PermissionDenied`. This spec takes the position that we MUST split; the exact migration for existing `Cannot write` messages is a plan-phase concern.
5. **Audit retention.** How long are audit rows kept, and do they travel with the filesystem or to an external sink by default? Lean: 90-day default retention in the backing store; external sink is the `audit_sink` callback. Open.
6. **Capabilities field cost on large listings.** `ls` on a 10^4-entry directory that computes `capabilities` per entry is expensive. Open question whether this is batched (share-resolver returns a prefix-keyed map) or lazily computed on `stat`. Lean: batched per-listing, include on `ls`.
7. **Label default for `user_scoped=True` mounts.** Default user-scoped data (`/alice/*`) presumably carries label `confidential` and only `user:alice` has `owner`. Does this need to be automatic at user-bootstrap time or declared per-mount? Lean: automatic and non-overridable for scoped mounts; explicit for shared mounts.

## Dependency and sequencing notes

- This story is **incompatible with `authz="off"`-assuming tests**. A new conftest fixture and a marker separating "single-principal" from "multi-principal" tests is required before rollout.
- It **does not conflict** with story 008's object model. Shares live on their own table; the `shares/` subtree under `__meta__` is a synthetic view, not a new `kind` on `vfs_objects`.
- It **does conflict** with the "shares table optional" story currently implied by `SupportsReBAC` being opt-in. This spec takes the position that `SupportsReBAC` remains opt-in per backend, but the in-memory resolution layer, the five-role ladder, the `capabilities` field, and the chokepoint hooks are always present — backends that don't support it simply always resolve to "admin on everything for the single-user case, or `authz="off"` semantics."
- A **read chokepoint** is added to the five existing chokepoints. This is a material change to `base.py` and MUST be called out prominently in the plan. The rationale is Invariant 2: today's chokepoints guard mutations only, which is sufficient for `PermissionMap` but not for per-principal reads.
- FSP (the MCP protocol layer at `/Users/claygendron/Git/Repos/fsp/`) gains three capability names (`fs.share.*`, `fs.link.*`, `fs.label.*`). Specify in the fsp-vfs synthesis memo.

## Summary

VFS ships a closed five-role ladder (`read | comment | write | admin | owner`) with four Principal types (`user | group | domain | anyone`), a single narrowing primitive (`restrict_subtree`), a per-path label (`public | internal | confidential | restricted`) that drives share-creation policy, and server-side capability tokens (share links) with mandatory expiration on anonymous links. All of it is enforced at the five existing chokepoints plus one new read chokepoint, declared through the `capabilities` field on every `Entry`, and logged through the `SupportsAudit` capability. Grants only — never deny entries. Narrower always wins, but only to narrow; broader is always the default.

The spec's twenty invariants in §"What VFS MUST get right" are load-bearing. Violating any is a security bug, not a style concern.
