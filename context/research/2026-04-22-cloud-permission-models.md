# Research — Cloud permission models: Drive, SharePoint, Dropbox

> **Note (extracted 2026-07-16):** this memo was extracted from story 009's
> spec (`specs/archive/009-cloud-style-sharing-and-access-control/spec.md`,
> §"Research — how the cloud systems do it") during the archive mining pass,
> and is dated to the original work. The spec cited
> `learnings/2026-04-22-cloud-permission-models.md` as its research source,
> but that memo was never written — the spec carried the synthesis inline.
> This preserves it; the text below is the spec's synthesis as written.

- **Date:** 2026-04-22
- **Status:** extracted record (preservation, not new research)
- **Scope:** how the three dominant cloud document systems — Google Drive,
  OneDrive/SharePoint, and Dropbox — model authorization and sharing,
  distilled into six cross-cutting invariants. This research was the
  normative context for story 009's per-principal authorization design
  (the five-role ladder, `restrict_subtree`, sensitivity labels, and
  capability-token share links).

## Google Drive (including Shared Drives)

- **Permission model.** A `Permission` has `type`
  (`user | group | domain | anyone`), `role`
  (`owner | organizer | fileOrganizer | writer | commenter | reader`),
  optional `expirationTime`, and `allowFileDiscovery` (searchability for
  domain/anyone grants). Returned with a stable `permissionId` scoped to the
  file.
- **Inheritance.** Folder permissions propagate to descendants. As of
  September 2025, a document's permissions **cannot be set more restrictive
  than its parent folder** — you can only add or upgrade. This is a hardening
  against accidental leakage through mis-scoped children.
- **Shared Drive roles are a separate role ladder.** Content Manager
  (default for new members) adds/edits/moves but cannot delete; Contributor
  adds/edits but cannot move or delete; plus Viewer / Commenter.
- **Capabilities field.** The Drive API surfaces a `capabilities{}` object on
  every file telling the caller what they can do (`canEdit`, `canShare`,
  `canDelete`, ...) *without* requiring them to try and fail. This is the
  cleanest cloud-system realization of Article 2 §2 ("declared
  capabilities").

## OneDrive / SharePoint

- **Scopes and inheritance.** The default model is that every item inherits
  its parent's permissions. Granting "unique permissions" on an item breaks
  inheritance and creates a **new permission scope**. Per-site scope count is
  capped (~50,000 unique scopes per list/library), and SharePoint explicitly
  documents the performance and governance cost of many broken-inheritance
  scopes.
- **Sharing link types.** Three canonical types: `SpecificPeople`,
  `Organization` (anyone in tenant), `Anyone` (anonymous). Creating a
  "People in your Organization" link on an item breaks inheritance on that
  item (silently, from the user's perspective). A "People with existing
  access" link is descriptive-only and does not break inheritance.
- **Sensitivity labels.** Documents and sites can carry labels (`General`,
  `Confidential`, `Highly Confidential`, ...) that are policy inputs: a
  `Highly Confidential` label can force the default sharing link to
  `SpecificPeople`, block `Anyone` links, and drive DLP detection.
- **External sharing is a tenant policy dimension.** Separately configurable
  from item permissions — a permission that would be valid internally can
  still be rejected because the tenant forbids external sharing.

## Dropbox

- **Two roles, one owner.** `viewer` / `editor` on both files and folders;
  exactly one `owner` per folder; creator-is-owner with transfer. Deliberate
  minimalism — users routinely cite the two-role ladder as the feature, not a
  limitation.
- **Inheritance with restricted-access holes.** Subfolders inherit parent
  members by default. "Restricted access" folders (Dropbox Business) break
  inheritance in the tightening direction and can narrow the audience; they
  do not broaden.
- **Shared link capabilities.** Password protection, expiration dates,
  revocation, download disabling, and view-only vs. edit links. Links are
  capability tokens — possession grants the scoped right until
  expiration/revocation.
- **Audit.** Admin-visible monitoring of sharing activity is a first-class
  feature, not an add-on.

## Synthesis — the cross-cutting invariants

Every cloud system, despite surface differences, converges on the same six
invariants. VFS MUST respect all six:

1. **Principals are typed.** A grant is to a `user`, a `group`, a `domain`,
   or `anyone` (public). These are not interchangeable — `anyone` grants have
   search-discoverability implications, `domain` grants are tenant-bound,
   `group` grants are dynamic.
2. **Inheritance is the default; breaking inheritance is explicit, expensive,
   and auditable.** Users don't manage permissions per file; they manage them
   per folder and let the tree do the work. Unique scopes are a tool of last
   resort.
3. **The tightening direction is free; the loosening direction is
   restricted.** You can always add more restrictive permissions to a child.
   The modern systems increasingly forbid loosening below the parent (Drive
   2025) or at least make it auditable.
4. **Sharing is a distinct primitive from permission.** Sharing is an *act*
   that produces one or more capabilities (a direct grant or a link).
   Permission is the *state* that results. Confusing the two is the source of
   most SharePoint complexity.
5. **Capability tokens are first-class.** "The person who holds this link" is
   a valid principal. Tokens have the same lifecycle primitives as grants:
   scope, expiration, revocation, audit.
6. **Label-driven policy beats per-item configuration.** At scale,
   administrators express intent through labels (sensitivity, classification,
   retention) and let policy convert labels into enforced permissions.
   Per-item ad-hoc configuration does not survive enterprise scale.

## How the spec consumed this

Story 009 turned these invariants into a design: a closed five-role ladder
(`read | comment | write | admin | owner`) with four principal types,
grants-only resolution (no deny entries) with a single narrowing primitive
(`restrict_subtree`, the Drive-2025 rule made explicit), server-side
revocable share links capped at `write`, and a four-value sensitivity label
enforced at share-creation time. Notable rejected alternatives, argued from
this research: deny entries (SharePoint/IAM precedence-rule complexity),
POSIX mode bits (cannot express `anyone` vs `domain` vs `group`), and bearer
JWTs for links (revocation latency). See the archived spec for the full
design and threat model.
