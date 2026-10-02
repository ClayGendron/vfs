<!--
DIÁTAXIS TYPE: Reference (information-oriented)
THE RULE: Austere, neutral, complete. Describe the machinery; do not instruct
or explain. Accuracy is the whole job.
-->

# Glossary

Terms used across the identity and permission surface, in alphabetical order. A term marked *planned* names designed behavior that is not yet in code.

**Actor.** The one principal doing the work in a call. Recorded on every version row. The actor may differ from the subjects when an agent works on behalf of people.

**Anonymous principal.** The principal named `anon` with kind `anonymous`. It is what a call runs as when it names no authority and the filesystem has no default. It holds only the everyone level, owns nothing, and appears only as the sole subject and actor of `Authority.anonymous()`.

**Attribution.** The record of who made a version: actor, subjects, provenance, and source identity, stored on the version row and its subject side table. Distinct from ownership.

**Authority.** The frozen value every call carries: subjects, actor, provenance, narrowing, and source identity. Built only through the four doors. See [Authority and Principal](authority.md).

**Default authority.** The `default_authority` argument to `VirtualFileSystem`. Used for any call that passes no authority. An explicit authority on a call always wins over it.

**Door.** One of the four class methods that construct an authority: `of`, `on_behalf_of`, `system`, `anonymous`. The bare constructor is not a door.

**Everyone level.** The permission level held by every principal on a path, set by posture rows. Resolved by deepest prefix.

**Grant.** A row stating that a principal or group holds a level, `read` or `read_write`, on a path prefix and everything beneath it. Additive: more rows only widen. Written by `grant`, removed by `revoke`, listed by `grants`.

**Group.** A principal id starting with `group:`. A member holds every grant its groups hold, directly or through nested groups up to eight levels deep. Membership is written by `add_member` and `remove_member`, by the system actor only.

**Hidden row.** A row the caller holds no level on. It answers `not_found`, exactly as a missing path does, and never counts in search statistics.

**Narrowing.** What a session has voluntarily given up, on top of what grants deny. Today the type has one value, `Narrowing.NONE`. A session can narrow and never widen.

**Owner floor.** The rule that a principal named in a row's `owner_id` can always read and write that row regardless of grants.

**Ownership.** The `owner_id` column on an entry row, set once at creation from the authority. One subject owns what it makes; a set, the system actor without a declaration, and anonymous own nothing.

**Posture.** A mount's or directory's everyone level: `open` (everyone reads and writes), `shared` (everyone reads), or `private` (nothing without a grant). Stored as a grant row under the reserved principal id `*`. The default is `open`.

**Principal.** One verified identity: a `sub`, a kind (`user`, `service`, `system`, `anonymous`), and a set of scope strings. See [Authority and Principal](authority.md).

**Provenance.** How an authority was proven: `edge` (verified at the transport boundary), `constructed` (built in process by trusted code), or `system` (the system actor). Recorded on every version row.

**Reserved name.** A `sub` that only one principal kind may carry: `system` for kind `system`, `anon` for kind `anonymous`. The id `*` is reserved for posture rows, and the prefix `group:` for groups; neither is ever a `sub`.

**Road directory.** A hidden directory with a visible row beneath it. It shows in listings with path and kind only, lists only its visible and road children, and refuses every write beneath it with `permission_denied`.

**Session.** A facade holding one authority and one filesystem. Every verb on it is the filesystem verb with the authority filled in. Closed is final. See [Session](session.md).

**Source identity.** The raw edge identity behind an authority, such as an issuer and subject pair. Set once at the edge, stored on version rows, never interpreted by the filesystem.

**Sub.** A principal's name. The JWT and OpenID Connect claim name for "subject", kept unchanged from the token into every column that names a principal.

**Subjects.** The set of principals whose permissions apply to a call. Non-empty except under the system actor. Bounded at `MAX_SUBJECTS`, which is 64.

**System actor.** The principal named `system` with kind `system`, the actor of `Authority.system()`. It has no subjects, bypasses grants, and stamps whatever owner a write payload declares. Mount administration runs as it.

**Unauthenticated.** The error kind `vfs.unauthenticated`. A mount-side refusal: a non-open posture answers it to the anonymous principal. Its hint names the fix: open a session with an authority, or configure a default.
