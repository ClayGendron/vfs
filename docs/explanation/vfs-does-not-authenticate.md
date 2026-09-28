<!--
DIÁTAXIS TYPE: Explanation (understanding-oriented)
THE RULE: Make the design argument. Name the alternatives and why they lose.
No steps, no reference tables — link to Reference and How-to instead.
-->

# VFS does not authenticate

**Status.** The rule that an authority carries names and never secrets is landed. The token-to-authority edge and the foreign-mount credential store are declared directions and are not yet built.

Developers arrive with an identity provider already chosen. Employees log in through Entra or Okta; consumers log in through Google or GitHub. VFS does not replace any of that, and this page explains what it does instead and how the picture extends to mounts whose far side has its own login.

## Two questions, one of which is yours

Authentication asks who you are and whether you can prove it. Authorization asks what you may do. VFS does none of the first. It does the second, but only for rows it owns.

So with an employee SSO system, the provider proves who Alice is. Your app takes the verified id and builds `Authority.of(Principal("alice"))`. VFS then decides what Alice may see using its own grant rows. The name alone is enough because VFS owns the permission model for its own tables.

## An authority carries names, never secrets

This is the rule that makes everything else on this page work. An authority is a set of verified names plus the actor and how the proof was made. It holds no token, no password, no API key. A token is proof consumed once at the edge, and it never travels down into the filesystem.

The consequence for served deployments follows directly. No served tool accepts an authority as data. The server verifies the token, builds the authority itself, and holds it server-side for the session. A remote caller never has a way to say who it is except by proving it.

## Three kinds of mount

Mounts differ in who owns the permission model on the far side.

A native mount, the database backend, is one where VFS owns the rows and the grants. The name is all it needs. Everything built so far is this kind.

A foreign mount with one shared credential is a Slack mount that talks to Slack as a bot. The bot sees whatever the bot can see, for every caller. VFS grants on top can only narrow that. This shape is allowed and it is the weak one: a shared credential is the inversion of least privilege, because everyone in the room can reach everything the bot can.

A foreign mount with per-subject credentials holds one Slack credential for each VFS subject. When Alice calls, the mount looks up Alice's credential and talks to Slack as Alice, and Slack enforces Slack's rules. VFS does not re-implement the foreign model. It defers to it.

## The lookup lives at the mount

The authority says "this is alice, proven by this issuer". The Slack mount has its own table mapping that name to a Slack credential. The table is a mount concern, not an authority concern, and the `source_identity` field is its key: the issuer plus the subject id, set once at the edge, so that alice from Entra and alice from GitHub can never be confused.

A picture helps. The authority is a passport. Each mount is a border with its own visa office. The passport proves the name. The visa office decides what that name may do there, and if it needs a local credential it keeps its own.

## What VFS can and cannot promise on a foreign mount

VFS can promise the audit: every version row names the actor and the subjects. VFS can promise tightening: a VFS grant or posture can hide part of a Slack mount from Alice. VFS cannot promise widening: no VFS grant can show Alice a channel Slack will not show her. The foreign side is a floor VFS sits above, never below.

## The connect flow, as intended

The login to a foreign system is an OAuth dance. The provider shows a consent page, redirects back to your app with a code, and the app trades the code for a token. That needs HTTP routes and a redirect URL, which only your app has. So your app runs the dance, and the backend does everything around it.

The intended shape has three parts. A credential store, a small protocol keyed by mount and source identity, holding encrypted blobs, with implementations for memory, the VFS database, and your own vault. Two connect calls on the backend: one returns the URL to send the user to, and one takes the returned code and stores the credential for that subject. And refresh inside the backend, so an expired token is renewed and rewritten without your code noticing.

Before Alice connects, a call to the foreign mount answers `unauthenticated` for that target, with a hint that says to connect. That is the same refusal a private posture gives an anonymous caller. A native mount says "I need a name"; a foreign mount says "I need a credential for this name". One concept, seen twice.

Credentials are never entries. They are never in content, never indexed, never returned by a verb, never in a result or a log. Revoking one is deleting its row.

## The open question

A set of subjects over a foreign mount has no settled answer. An agent working for Alice and Bob on Slack would need to call Slack as each and intersect the results, or the mount would refuse sets with a classified error. Nothing today needs the answer. The first foreign backend to be designed will decide it.

## Further reading

- [Identity is a value, not a session](identity-is-a-value.md) for why the authority holds what it holds.
- Design records in the repository: `context/decisions/062-authority-is-subjects-actor-and-narrowing.md` and `context/specs/active/149-serve-auth-token-to-authority/spec.md`; the credential-store direction is recorded in `context/specs/STATUS.md`.
