<!--
DIÁTAXIS TYPE: Explanation (understanding-oriented)
THE RULE: Make the design argument. Name the alternatives and why they lose.
No steps, no reference tables — link to Reference and How-to instead.
-->

# Identity is a value, not a session

**Status.** Everything on this page is landed, and so is the enforcement that acts on it: grants and posture on the database backend. See [How to share a folder with grants](../how-to/share-a-folder-with-grants.md).

Every call into VFS carries one value that says who the call is for and who is making it. That value is an `Authority`. This page explains what it holds, why it holds those things and not others, and why it is a frozen value rather than a session object that remembers a decision.

## The problem with a bare user id

The first design passed a string called `user_id` on every verb. A string is easy to pass and easy to store. It also carries nothing. It cannot say whether the name was verified or typed. It cannot say that an agent did the work for two people at once. It cannot say that the caller chose to give up some of its rights for this task. Every one of those facts matters to a permission system, and a string has nowhere to put them.

So the string became a value with four parts.

## The four parts

**Subjects** are the people or services whose permissions apply. It is a set, never empty except in one case, and bounded at sixty-four members. When Alice reads a file, Alice is the only subject. When an agent works in a chat room with Alice and Bob, both are subjects.

**The actor** is the one identity doing the work. When Alice reads a file, Alice is the actor. When an agent works for Alice and Bob, the agent is the actor. The actor and the subjects are kept apart on purpose. Merging them would either hide the agent, by saying Alice did it, or hide the people, by saying the agent did it. A record that names only one of them is a lie by omission.

**Provenance** says how the identity was proven. `edge` means a verified token at the network boundary. `constructed` means trusted code in your process built it. `system` means the one actor that bypasses grants. Provenance is a claim, and the only claim a shape check can confirm is that `system` goes with the system actor.

**Narrowing** is what the caller has voluntarily given up. Grants are what other people gave you; narrowing is what you chose not to use. Today the type exists with one value, nothing narrowed. It sits on the authority so that the slot is already on every call when narrowing arrives.

A fifth field, `source_identity`, records the raw edge identity, such as an issuer and a subject id, for the audit trail. It is set once at the edge and never interpreted.

## Why `sub` and not `name`

A principal's name field is `sub`. That is the JWT and OpenID Connect claim for "subject". Every identity token from Entra, Okta, Auth0, or GitHub has one. Naming the field after the claim makes the copy a straight line: the token's `sub` becomes the principal's `sub` unchanged, and that same string lands in the owner column and in grant rows. Anyone reading a row can match it to a token without a translation table. The cost is a little jargon for readers who have not seen a token. That trade was taken deliberately.

## Why a frozen value

An authority is immutable and hashable. Two authorities built from the same subjects in a different order are equal. There is no method on it that checks a permission, and nothing inside it caches a decision.

The alternative is a session object that resolves rights once and remembers them. That is faster, and it is how many web frameworks work. VFS rejects it because rights change underneath a long-lived agent. A grant revoked at noon must take effect on the next call, not when the agent restarts. Re-deriving rights from a value on every call is the only way to guarantee that, and the cost is paid by a memo keyed on a grant revision, not by the type.

A frozen value also makes the authority safe to thread. The router passes it to storage on every call, and two calls with two authorities reach storage as two different values. Nothing is stored on the filesystem object between calls.

## Why four doors instead of a constructor

You never call the `Authority` constructor. You call one of four class methods: `of` for one identity acting as itself, `on_behalf_of` for an actor working for a set, `system` for the batch actor, and `anonymous` for nobody in particular. The reference page lists them: [Authority and Principal](../reference/authority.md).

The doors exist so that the rules run in one place. Every authority passes through the same construction hook, and that hook checks six rules: the system principal is never a subject, the set is non-empty unless the actor is system, the system actor acts for nobody, the set is bounded, the system provenance belongs to the system actor alone, and the anonymous principal has exactly one shape. A violation raises a `ValueError` rather than returning a structured error, because a violation can only come from a bug in the code that builds authorities, never from a request.

A test in the repository scans every source file for a bare `Authority(` call outside the module that defines it. That is how the project knows nobody added a fifth door quietly.

## Where the trust boundary is

Python has no private constructor. Code running in your process can call `Authority(...)` directly and forge a provenance. The doors cannot stop it.

That is fine, because the class is not the security boundary. The process is. Code in your process already holds the database credentials. It can already call `Authority.system()` and bypass every grant. It can already open the database and edit rows. Forging a provenance gains it nothing it does not have, and the only damage is a false line in an audit trail that the same code owns.

The boundary that matters is the network. There, no tool ever accepts an authority as data. The server verifies a token, builds the authority itself, and holds it server-side. A remote client never has a constructor to call. The same rule applies between mounts: a remote mount receives verified names, never a forwarded token or a forwarded authority, and maps those names into its own principal table.

A stricter door, a module-private token the constructor demands, is planned for the day the edge factory exists and `edge` provenance means something. Until then it would guard an empty room.

## What identity is not

Identity is not ownership. Ownership is a column on a row, set once, and it means only that the owner can never be locked out of what they made. Identity is not the audit record either. The audit record is what a version row stores about who did what. Both derive from the authority; neither is the authority. [Ownership is a floor, attribution is a record](ownership-and-attribution.md) covers them.

## Further reading

- [Authority and Principal](../reference/authority.md), the fields, doors, and rules.
- [How to run calls as a principal](../how-to/run-calls-as-a-principal.md).
- Design records in the repository: `context/decisions/062-authority-is-subjects-actor-and-narrowing.md` and `context/decisions/063-a-session-never-widens-itself.md`.
