# A rewind puts a session's files back as they were before a turn

A draft, written on 2026-11-22 from the session design in `documentation/how-to/keep-a-session-for-each-conversation.md` and the studies in `agents/2026-11-22-a-session-is-stored-named-and-forked/research/`. It is not reviewed, and nothing is built. It is wanted for 0.1.0. It holds the facts and the choices; the decisions below are leanings until they are ruled on.

## The outcome wanted

A session works through turns `msg_4`, `msg_5` and `msg_6`, and changes files in each. A rewind to before `msg_5` that asks for the files as well puts every file the session changed in `msg_5` and `msg_6` back as it was when `msg_4` ended. A file another caller changed in the meantime is left as it is and reported, never overwritten. The files put back are new versions, so the rollback is itself in the history and can be undone.

```python
scout.rewind(before="msg_5")               # the session's memory only, as the guide describes
scout.rewind(before="msg_5", files=True)   # the memory, and the files the session changed
```

## Builds on

- The session design: a session is stored, a turn partitions what it did, and `rewind(before=turn)` removes the turn and every later one from the session's memory.
- `agents/2026-11-22-the-session-remembers-what-it-read/spec.md` (pull request 42): the etag, which names one entry at one version, and `if_match=` on `write`, `edit`, `delete` and `move`.
- Version rows: every change to a body writes a row with the actor and the provenance (`src/vfs/models/rows.py`). Nothing reads them back yet; roadmap story K8 does.
- Trash and restore, which are built: a delete is soft and reversible.
- The action log (roadmap story H0), not built: one row per call, with an effect's row written with the effect.

## What the studies found

- **A rollback from whole-tree snapshots overwrites other callers' work.** opencode snapshots the whole project tree at each model step and lists a step's changes by a diff of the tree, so a change another session made during the step counts as that step's. Its issue 54026 reports a revert that silently discarded changes made by other sessions. The store also grew without bound: 15 GB in 11.5 hours (issue 55010), and 78% of a 687 MB database in one revert cell (issue 55282).
- **Codex removed file undo.** Its per-turn snapshots ran `git add -A` over a home directory and filled more than 200 GB (issue 19588). The feature was removed on 2026-04-28 (pull request 19481), and its revert now changes history only.
- **Claude's file checkpointing tracks only its own edit tools.** A change made through the shell is not undone, and directory creates, moves and deletes are not undone. Each user message is a checkpoint. The rewind offers the conversation only, the files only, or both.
- **ADK rewinds by writing forward.** An artifact is restored by writing the old version as a new one, or a tombstone where it did not exist, and effects outside ADK are left in place and listed in the guide.
- **Most turns change no file.** One 2026 study measured up to 87% of turns changing neither files nor processes, so the record of changes is small beside the record of reads.
- **What was sent cannot be unsent.** A restore cannot undo a request a tool already made to an outside system.

What VFS has that none of these had: every verb, the shell's included, goes through one router and writes a version row, so a shell write is recorded like any other; and an etag names an exact state of an exact file.

## Decisions

1. **A session records each change it makes, under its turn.** One record per entry changed: the session, the turn, the entry, the etag before, the etag after, and what was done (made, written, edited, deleted, moved from and to, directory made). It is written with the change. A tool's writes through its session are the session's changes.
2. **The rollback is per entry, and only the session's own entries.** It never takes or restores a snapshot of a tree. An entry the session did not change in the removed turns is not touched.
3. **Each entry goes back to its state before its first change in the removed turns.** A written or edited file gets its earlier body back from the version row. A file the session made is deleted, to the trash. A file the session deleted is restored. A moved file is moved back.
4. **An entry is put back only when its etag is still the one the session's last change left.** Otherwise somebody else changed it since, and it is skipped and reported with its path and the reason. This is the `if_match` check, made inside the transaction that restores.
5. **The rollback is made of ordinary changes.** Each restore is a call of a public verb as the session's authority: it is checked against the caller's rights, it writes a version, and it is logged. Nothing is rewritten or removed from the history.
6. **A preview shows the plan and changes nothing.** `rewind(before=, files=True, preview=True)` returns each entry with what would be done to it, and each entry that would be skipped with the reason.
7. **A fork never rolls files back.** `fork(before=turn)` leaves the source session and every file as they are.
8. **Effects outside VFS are not undone,** and the guide says so.

## Choices left

- **Policies.** A restore is a change, and a policy may want a person for it. Either a rollback passes through the policies and may be interrupted file by file, or a rollback is one step a policy judges as a whole. The second is simpler to answer; the first is the same rule as every other change.
- **All or some.** Either the rollback restores what it can and reports the rest, or it restores nothing unless every entry can be restored. Two mounts cannot share a transaction, so "all or nothing" can hold only within one mount.
- **Files only.** Whether there is a call that puts the files back and leaves the session's memory as it is, as Claude's rewind offers.
- **Where the record lives.** Either the action log's effect rows are the record, or the record is a table of its own. The first adds no statement; the second does not wait on H0.
- **How long a rollback stays possible.** The version rows it needs must not be pruned before the session expires, or the rollback must say which entries it can no longer restore.
- **A file changed by the session and then by another caller in a later, kept turn.** Decision 4 skips it. Whether the report should offer the difference between the two versions is open.

## Scale

- **Per file write.** One record more, written with the write. With the log as the record it is no statement more.
- **Per rollback.** Work in proportion to the entries the session changed in the removed turns, never to the corpus. A turn that wrote 10,000 entries rolls back through the same chunked builders as a 10,000-entry write.
- **Per read.** Nothing.

## Tests

- A write, an edit, a delete, a move and a made file in a turn, each put back by a rollback, on memory, SQLite and the Postgres leg.
- A change made through a shell line is put back like any other.
- A file changed by another caller after the session's change is skipped and reported, and keeps the other caller's body.
- The rollback writes new versions and removes none, counted.
- A preview changes nothing, counted as zero mutation statements.
- A rollback of a 10,000-entry turn stays within the declared statement budget.
- A rewind without `files=True` changes no file.

## One line

A session records what it changed in each turn, and a rewind can put exactly those files back, each one only if nobody else has changed it since.
