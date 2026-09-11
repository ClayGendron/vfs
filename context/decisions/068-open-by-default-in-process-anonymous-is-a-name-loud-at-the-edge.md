# 068. Posture: Open by Default in Process, Anonymous Is a Name, Loud at the Edge

- **Status:** accepted 2026-09-06 (Clay, in conversation: "the default
  posture for storage should be open within VFS, and we should not
  require a principal to do operations on an open storage provider,
  only when shared or private"). Amends spec 070's decision 3 (landed
  the same day) and ADR 021/067's additive-only rule for the
  *everyone* level; binds spec 058 (posture and the anonymous
  principal), spec 149 (the edge refuses an open mount unless told)
  and the developer-experience story.
- **Date:** 2026-09-06
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, 2026-09-06), from Claude's assessment of
  the developer-experience question against prior art.

## Context

Spec 070 landed identity as fail-closed at the router ingress: a call
naming no authority on a router with no configured default is refused
as `unauthenticated`. Spec 058 as written starts every mount with no
grant rows, so a fresh mount shows nothing to anyone but owners and
the system actor. Together they make the five-minute path two lines
longer than it should be and, once 058 lands, make a freshly ingested
corpus invisible to the first principal who looks. Clay's stated
expectation is the opposite: information ingested into vfs is public,
read and write or at least read, unless someone says otherwise.

Prior art divides cleanly on where the fail-closed line belongs.

- **In-process libraries are open.** SQLite has no authentication; the
  process is trusted and the file's OS permissions are the gate. Git
  refuses to commit without a name, but reads the name from config
  once, never per call — a default authority, not a per-call demand.
- **Systems name the anonymous caller.** Plan 9 has the user `none`;
  Postgres has the role `public` that every role belongs to; Unix has
  no anonymous process at all, and its default umask makes new files
  world-readable. In each, "nobody in particular" is still a principal
  with a name, so the audit trail never has a blank.
- **Network services that were open by default were owned.** Redis
  and MongoDB shipped without authentication and the exposed-instance
  breaches followed; S3 flipped to block public access by default in
  2023; Firebase opens its rules in test mode and nags until they are
  locked. The lesson is not "never open". It is: open in process,
  loud at the network edge.

One consequence of 058's additive-only grants also surfaced: a public
grant at the root covers everything beneath it, so "this one folder
is private" is inexpressible. It is the first thing a developer asks
for after "make it public".

## Decision

1. **Posture is a mount fact with three values.** `open` (everyone
   reads and writes), `shared` (everyone reads; writing is by grant)
   and `private` (nothing without a grant). It is a row where the
   grants live, set at construction, changed by a verb, listed by
   `mounts()` and by `grants("/")`. It is data, not a mode knob. **The
   default is `open`.** Bulk ingest under an open mount needs no grant
   row.
2. **Posture applies per directory, deepest prefix wins.** A posture
   row on a prefix sets the *everyone* level beneath it until a deeper
   posture row says otherwise; grants widen on top. Structure
   (`PermissionMap`, op masks) still tightens for every caller. This
   amends ADR 021/067's additive-only rule for the everyone level
   only: principal and group grants stay additive and max-resolved;
   the everyone level is resolved by longest prefix, like structure.
   It compiles to a bounded predicate: the open and shared prefixes as
   `LIKE` arms, each nested tighter prefix as a `NOT LIKE` arm.
3. **Anonymous is a named principal.** `Principal("anon",
   kind="anonymous")` and `Authority.anonymous()` are the fourth
   principal kind and the fourth construction door. The anonymous
   authority has exactly one shape — the anonymous principal as sole
   subject and actor — and it holds only the everyone level. Every
   version row it writes names `anon` as actor; the audit never has a
   blank.
4. **The router substitutes anonymous; the ingress no longer
   refuses.** A call that names no authority runs under the configured
   `default_authority` if there is one, else as `Authority.anonymous()`.
   Storage still always receives an authority (070's invariant holds).
5. **Anonymous owns nothing.** Rows it creates take a NULL `owner_id`,
   the same rule as a subject set (ADR 064 rule 4). Otherwise every
   anonymous caller would own every anonymous row.
6. **A non-open posture refuses anonymous as `unauthenticated`.** The
   401 moves from the router ingress to the mount, where the posture
   lives. A mixed call over an open root and a private mount returns
   the open side's rows and an `unauthenticated` error for the private
   side — the per-target classification every verb already does. The
   hint names the fix: open a session, or configure a default.
7. **The edge is loud.** `serve()` refuses to start while any mount's
   posture is `open` unless the caller passes an explicit allow flag.
   In process, open is the right default; on a socket, open must be a
   deliberate word.

## Consequences

- The five-minute path has no identity line: `VirtualFileSystem()`
  then `write` and `glean`, anonymous throughout. The identity concept
  arrives the first time a developer writes `posture("/finance",
  "private")` and the next anonymous call there says `unauthenticated`.
- The `default_authority` constructor argument stays for the ETL
  shape (`Authority.system()`); the system actor is unchanged.
- Spec 070's decision 3 ("absence fails closed; privilege is a named
  default") is superseded for the ingress: absence is anonymous, and
  fail-closed lives at the posture. 070's `unauthenticated` kind
  stays, produced by 058's spine rather than the router gate.
- ADR 062 rule 2 ("an empty subject set denies everything") is
  untouched: the anonymous set is not empty, it is `{anon}`, and it
  holds only what posture gives everyone.
- ADR 066's intersection law is untouched: an anonymous authority is
  never a member of a set (rule 3 fixes its shape), so no meet ever
  includes it.
- Spec 058 gains the posture rows, the per-directory resolution, the
  `NOT LIKE` arms and the mount-side `unauthenticated`; spec 149 gains
  the allow flag.

## Alternatives considered

- **Keep fail-closed at the ingress and document the two extra
  lines.** Rejected: it makes the library's default posture a lie —
  the mount is open, but you must name yourself to use it — and every
  quick script starts with `Authority.system()`, which trains the
  wrong habit for the one actor that bypasses grants.
- **A mount per posture, no per-directory rule.** Keeps ADR 021/067
  intact, but the unit developers reason in is the directory, not the
  mount, and one small app would need three engines to have a private
  folder. Kept as the answer for genuinely separate tenants.
- **A per-principal deny row.** Rejected again, as in ADR 021/067:
  posture narrows the everyone level by prefix, which is what the
  "private folder" request actually is; it does not exclude one named
  person from a public place, and that stays inexpressible by design
  (use a group).
