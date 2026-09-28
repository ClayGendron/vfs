<!--
DIÁTAXIS TYPE: Explanation (understanding-oriented)
THE RULE: Make the design argument. Name the alternatives and why they lose.
No steps, no reference tables — link to Reference and How-to instead.
-->

# Open in process, loud at the edge

**Status.** The anonymous principal, the default authority, and the rule that storage always receives an authority are landed. Posture, grants, and the mount-side refusal are the declared design and are not yet built. This page describes both and says which is which.

A library that runs inside your process and a service that listens on a socket need opposite defaults. VFS is both, so it has to pick a line and say where the line is. This page explains the choice: open by default in process, a named principal for nobody in particular, and a loud refusal at the network edge.

## The five-minute path

The first thing a developer does with VFS is make a filesystem, write a file, and search for it. Nothing about that task involves identity. If the library demanded a name before the first write, every quick script would start with the system actor, which is the one identity that bypasses every grant. That trains the wrong habit for the sake of a rule nobody asked for.

So a call that names nobody runs. The router fills the missing authority in three steps. If the call passed one, that wins. If the filesystem was built with a default, that is used. Otherwise the call runs as the anonymous principal.

The default is the git config shape. Git refuses to commit without a name, but it reads the name from configuration once rather than asking on every commit. A filesystem built with `default_authority=Authority.of(me)` is the same idea for a single-user app, and one built with `Authority.system()` is the batch shape.

## Nobody still has a name

The anonymous principal is a real principal. Its name is `anon`, its kind is `anonymous`, and no other principal may use that name or that kind. When an anonymous call writes a version, the record says `anon` did it. The audit never has a blank.

This is old practice. Plan 9 has the user `none`. Postgres has the role `public`, which every role belongs to. Neither system has a caller with no name, because a nameless caller is a hole in every log and every policy. VFS follows them.

The anonymous authority has exactly one shape. Anonymous is the sole subject and also the actor. It cannot join a set, cannot act for someone else, and nobody can act for it. This keeps the rule that a set of subjects sees only what every member sees, because no set ever contains anonymous.

Anonymous owns nothing. A row it creates has no owner, for the reason [Ownership is a floor, attribution is a record](ownership-and-attribution.md) gives: otherwise every stranger would own every other stranger's work.

## Posture is the everyone level

This section describes the declared design. Posture does not exist in code yet.

A posture is one word per mount: `open`, `shared`, or `private`. Open means everyone reads and writes; it is the default. Shared means everyone reads and writing needs a grant. Private means nothing without a grant. Posture is stored as data, a grant row whose principal is the reserved id `*` meaning everyone, not as a mode flag on the object. That means it can be listed, changed by a verb, and reasoned about like any other grant.

Posture applies per directory, and the deepest prefix wins. A mount open at its root with a private row on `/finance` lets everyone work everywhere except `/finance`. This is the one place a grant row can narrow. Every other grant only widens, and a subject's level is the maximum over its rows. The everyone level is resolved by longest prefix instead, the same way structural restrictions resolve, because "make this one folder private" is the first thing a developer asks for after "make it public", and additive rows alone cannot express it.

The anonymous principal holds only the everyone level. Nothing else can be granted to it. On an open mount that is enough to work. On a shared mount it can read. On a private mount, or a private prefix, it sees nothing.

## Where the refusal lives

For one day the router refused any call that named nobody. That rule moved. The refusal now belongs to the mount, next to the posture, because that is where the policy lives and because the answer is per target. A single call that spans an open root and a private mount returns the open side's rows and one `unauthenticated` error for the private side, which is the same per-target classification every verb already does for other errors.

The error's hint names the fix: open a session with an authority, or configure a default. Identity arrives in a developer's mental model at the moment they set a posture and the next anonymous call says "who are you", not at the first line of the first script.

## Loud at the edge

Open by default is the right call for a library. It is the wrong call for a socket. Redis and MongoDB shipped listening without authentication and the exposed-instance breaches followed. S3 flipped to block public access by default. Firebase opens its rules in test mode and warns until they are locked. The lesson is not that open is wrong. The lesson is that open must be a deliberate word once a network is involved.

So `serve()` will refuse to start while any mount's posture is open, unless the caller passes an explicit allow flag. In process, open is the default and needs no ceremony. On a socket, open is something you have to say.

## The alternatives that lost

Keeping the ingress refusal and documenting the two extra lines makes the library's default a lie: the mount is open, but you must name yourself to use it.

One mount per posture, with no per-directory rule, keeps every grant additive. But developers reason in directories, not mounts, and a small app would need three engines to have one private folder. It remains the answer for genuinely separate tenants.

A per-person deny row would let you exclude one named person from a public place. That stays inexpressible on purpose. Posture narrows the everyone level by prefix; excluding a person is a group's job.

## Further reading

- [How to run calls as a principal](../how-to/run-calls-as-a-principal.md).
- [Glossary](../reference/glossary.md) for posture, everyone level, and the anonymous principal.
- Design record in the repository: `context/decisions/068-open-by-default-in-process-anonymous-is-a-name-loud-at-the-edge.md`; the posture design is `context/specs/active/058-row-level-permission-grants/spec.md`.
