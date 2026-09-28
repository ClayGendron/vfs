<!--
DIÁTAXIS TYPE: Explanation (understanding-oriented)
THE RULE: Make the design argument. Name the alternatives and why they lose.
No steps, no reference tables — link to Reference and How-to instead.
-->

# Ownership is a floor, attribution is a record

**Status.** The ownership rule is landed and every row gets an owner the way this page describes. The attribution columns are landed in the schema and the model, but no write path creates version rows yet, so nothing is recorded until version history is built.

Two different questions get asked about a row. Who may never be locked out of it? And who did this to it? VFS answers them with two different mechanisms, and this page explains why they are kept apart.

## Ownership is a floor

Every entry row has an `owner_id` column. It holds one subject name or nothing. It is set when the row is created and never changes afterwards. Moving the row does not change it. Narrowing a session does not change it.

Ownership buys exactly one thing. If the owner column holds your name, you can always read and write that row, even with no grant at all. You cannot be locked out of what you made. The project calls this the owner floor. It is deliberately small. Ownership does not let you grant the row to others, does not make you its administrator, and does not follow the row through a copy.

## Who becomes the owner

One function decides the owner for every new row, and it reads the authority, never the request payload. There are four cases.

When one subject acts as itself, that subject owns the row. Alice writes a file and Alice owns it. If the write payload declared a different owner, the declaration is ignored. Caller identity is not something a payload can override.

When a set acts through an actor, nobody owns the row. An agent writes a file for Alice and Bob. If Alice owned it, the floor would let her lock Bob out of a shared artifact. If the agent owned it, a service account would hold a floor over a person's data. So the column is empty, and every member's access comes from the grants on the directory. The row belongs to the room, the same way a file created under a group's umask belongs to the group rather than the person who happened to type the command.

When the system actor writes, the row takes whatever owner the payload declared. This is the one place the payload's owner field means anything. A migration job that copies ten thousand rows needs to preserve each row's original owner, and the system actor is the one actor that already bypasses grants, so trusting its declaration adds no new power.

When the anonymous principal writes, nobody owns the row. If anonymous owned what it made, every anonymous caller would own every anonymous row, and the floor would let any stranger overwrite any other stranger's work. An empty column is the only safe answer.

## Why ownership does not transfer

A common alternative is to let ownership follow the most recent writer, or to let an administrator reassign it. VFS does neither. The floor exists so that a person can never be locked out of their own work by a later change in policy. A floor that moves is not a floor. The one exception is overwrite: writing a new version of a file restamps the owner, because the new content is a new thing the writer made.

## Attribution is a record

Attribution answers the second question: who did this? It lives on version rows, not on the entry, because the answer changes with every edit while the owner does not.

A version row stores the actor, the provenance, and the source identity. The subjects go in a side table with one row per subject per version. A version Alice made for herself has one subject row. A version an agent made for Alice and Bob has two. A version the system actor made has none, because the system actor has no subjects. A version the anonymous principal made has one row naming `anon`, so the record is never blank.

The subjects are rows rather than a packed string because a set is a set. The question "every version Bob was a subject of" should be one join, not a string parse.

## Why the two are separate columns

It would be simpler to store one name per row and call it both owner and author. The two answers diverge too often for that. An agent writes for Alice and Bob: the author is the agent, the subjects are Alice and Bob, and the owner is nobody. A migration copies Alice's old file: the actor is the system, the subjects are none, and the owner is Alice. A row can have an empty owner and a complete audit trail. Collapsing them would force one of those facts to be wrong.

## What is missing

The versions table has carried this shape since the schema format moved to thirteen, and sweep clears the side table along with the versions it belongs to. But no verb writes a version row today. Store-on-write, reconstruction, and packing were designed under an older story and never built. Until a version history spec lands, the attribution columns describe what will be recorded, not what is.

## Further reading

- [Authority and Principal](../reference/authority.md), including the owner table.
- [How to bulk load as the system actor](../how-to/bulk-load-as-the-system-actor.md), the one path where a declared owner is honored.
- Design record in the repository: `context/decisions/064-every-version-row-names-actor-and-subjects.md`.
