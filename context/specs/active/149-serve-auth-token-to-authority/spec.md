# 149 — `serve()` auth: a token in, an `Authority` out, and nothing identity-shaped on the wire

- **Status:** seed — born 2026-09-06 from ADR 062 rule 6 and spec
  070's wire rules (its July decisions 6 and 7), ratified by Clay the
  same day. Not scheduled; sequenced after 070 and 058, alongside the
  MCP server spec that replaces cancelled 054/056-C. `[NEEDS
  CLARIFICATION]` markers are unresolved forks.
- **Born from:** spec 070 §7 (restated wire rules), ADR 062 rule 6
  (the pair survives every boundary; remote mounts re-derive from
  attested names), ADR 066 rule 3 (the set never crosses as a token),
  lens L3 (RFC 8693 `act`, `SourceIdentity`, SPIFFE), lens L5 (MCP
  2026-07-28 authorization, MRTR, Entra OBO, the IETF on-behalf-of
  drafts), the MCP memos
  (`../../../research/2026-04-19-mcp-specification.md`,
  `../../../research/2026-08-10-mcp-2026-07-28-stateless-revision.md`),
  the verify-authority spike (`../../../research/2026-08-17-verify-authority-spike.md`)
- **Date:** 2026-09-06
- **Owner:** Clay Gendron
- **Kind:** feature (the edge: token verification, authority
  construction, the subject-set attestation, the outbound rule for
  remote mounts)
- **Depends on:** 070 (`Authority`, `authority_from_token` is this
  spec's factory), the MCP server spec (transport), 148 (`pending`'s
  wire shape rides here)

## Intent

Authentication happens once, at the wire. What crosses inward is an
`Authority`, which means "the edge verified this". This spec builds
the edge: a `TokenVerifier`-shaped seam that enforces all four checks
itself (audience per RFC 8707 on by default, signature, issuer,
expiry; never hand-rolled), a factory that turns verified claims into
an authority, and the rule that no served tool ever accepts identity
as data.

## Decided semantics (from the ADRs and 070)

1. **Inbound.** `authority_from_token(claims) -> Authority`: `sub` is
   the subject; an `act` claim names the actor (RFC 8693), else actor
   = subject; `kind` from a declared claim or the client registration
   (`service` for an agent's own identity, with its sponsor recorded);
   `source_identity` set once here; `provenance = edge`. A token whose
   `sub` is the reserved system name is refused. Groups are **not**
   read from the token (ADR 067 rule 3 resolves them on the spine)
   `[NEEDS CLARIFICATION: accept a `groups` claim as a hint that the
   spine verifies against memberships, or ignore it; lean: ignore]`.
2. **The subject set on the wire.** No token carries a set. A host
   that runs one agent for a room (Claude Tag's shape) is a **trusted
   subsystem**: its own verified `service` token, with a declared
   scope, may name the members as data, and the authority is built
   with `provenance = constructed`? `[NEEDS CLARIFICATION: a fourth
   provenance value `attested` (named by a verified subsystem) rather
   than `constructed`; lean: add `attested`, since the audit must
   distinguish "the edge saw each member" from "a subsystem vouched
   for the list"]`. Members unknown to this principal space hold
   nothing, so the meet is empty and the session denies (ADR 066
   rule 3).
3. **No served tool exposes an `authority` parameter.** The server
   opens the session server-side; MCP's own session id is bound to the
   verified `(client_id, issuer, sub)` triple; a refresh mints a new
   authority and a new session.
4. **Outbound.** A remote-mount backend never forwards the inbound
   token. Two shapes per trust relationship: trusted subsystem (the
   backend authenticates as itself and sends the verified names as
   data, mapped by the receiver into its own space as `(issuer, sub)`)
   or RFC 8693 token exchange. The receiver never maps anything to its
   own `system()`.
5. **`pending` on the wire** is MRTR's `input_required` with a
   `requestState` that embeds the principal, a TTL and the request
   digest, integrity-protected (L5 take row 6); until an ask rung
   exists, served tools are `complete`-only.
6. **Refusals.** An absent or invalid token is `vfs.unauthenticated`
   (401); a valid token whose authority may not act is
   `permission_denied` (403) or `not_found` for a hidden target (ADR
   065). Unknown principal and wrong proof are indistinguishable at
   the edge (Plan 9's enumeration defence).

## Non-goals

- Token issuance, login, an IdP.
- The transport itself (the MCP server spec).
- Cross-app access, CIBA, token vaults: enterprise follow-ups the
  seam must not preclude.

## Open questions

- The two markers above; whether `authority_from_token` lives in
  `vfs/authority.py` (070) or a `vfs/serve/` package.
