# Review: a call that reaches several mounts bounds each mount

The two specs in this directory were read three times on 2026-11-18 and 2026-11-19, by one fresh reader that was given no summary of the work. It reran the experiments each decision rests on and checked the memo's claims against the reference clones. Nothing is built.

| What was read | Verdict |
|---|---|
| `spec.md`, first draft | Not yet |
| `spec.md`, second draft, and the first draft of the cancellation spec | Not yet, both |
| `spec.md`, third draft, and the second draft of the cancellation spec | Fit to build, both |

## What the first reading changed

The first draft stopped waiting for a late call and left it running, and then skipped that mount until the late call ended.

- **Found: a late call has no end.** No statement timeout is set anywhere in the package, so on a dead peer the call runs for ever and holds a connection and a snapshot. Every system in the memo that bounds a member also tells the member to stop. Decided: a late call is cancelled at its timeout, and nobody waits for the cancellation.
- **Found: the skip had no way back.** It was set by any late call and cleared only when the last one ended. Decided: a mount whose timed call ran late is marked, one probe is sent in each timeout, and the mark clears when a probe answers, when the mount's timeout is changed, or when the mount is removed.
- **Found: a fixed time is a ceiling on the `tree` of a large mount,** which the working agreement forbids. Decided: a `tree` is not timed. A mount's `tree` is sent only after the `stat` of its root answers.
- **Found: it was several landings.** Decided: five, and the first is the cancellation defect.
- **Found: the default of 30 seconds is not the precedent.** Almost every system in the memo has no default. The spec keeps 30 seconds and says it is its own choice. It is the first of the choices that are not yet confirmed.

## What the second reading changed

- **Found: with the first fix for the cancellation defect, a cancelled write on the in-memory storage always landed,** which no other engine does. A narrower fix was pointed to, a second connection that keeps the database alive. It was built as a spike and cut at every driver round trip. It never lost a row, and after some cuts it left the storage refusing every call until the collector ran. It is not taken. Decided: the unit of work is shielded, a cancelled unit is marked, and the commit of a marked unit is refused. Run at every round trip, a write cancelled before its commit rolled back in 79 of 79 cuts and landed in 2 of 2 cuts at the commit or after, which is what a file database does.
- **Found: the hand-over for searches would have timed a kernel stage and timed one call twice.** Decided: each call is timed where it is built, with its mount in hand.

## The cancellation defect

Found while the memo was written, and reproduced by the reader. Cancelling a call while its connection is in use makes SQLAlchemy throw the connection away, by three paths. An in-memory SQLite database lives in that one connection, so the database goes with it. After one cancelled `stat`, the next read fails with `no such table` and the next write starts an empty database. On a file database, a write cancelled at its commit had landed while its caller was told it was cancelled.

It is in the kernel today, with or without a time limit. The spec for it stands alone and is the first landing.

## Not yet confirmed

Five choices, each with its recommendation, at the foot of each spec. They are one task in `agents/tasks.md`.
