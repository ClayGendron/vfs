# Rewind a Conversation and Put Its Files Back

This guide shows how to take a conversation back to an earlier point and put the files the agent changed back as they were. Use it when your chat application lets a user edit an earlier message or throw away an answer, and the agent's work on files should be thrown away with it.

> **This guide describes an API that is designed and not yet built.** It is written first so that the API can be agreed before the code is written. The names on this page may still change.

**A rewind puts back only what the session itself changed, and only where nobody else has changed it since.** VFS records every change a [session](../reference/glossary.md#session) makes, under the [turn](../reference/glossary.md#turn) it was made in. A rewind walks that record backwards. It never restores a snapshot of a whole directory, so it cannot overwrite another person's work.

## Before You Begin

You should have finished [Keep a Session for Each Conversation](keep-a-session-for-each-conversation.md), because this guide builds on its session and its turns.

The examples use an agent named Scout and a person named Ada. Each Python block is one notebook cell, and the block after it shows what the cell prints.

## Step 1: Have the Agent Change Some Files

Start a file system with two files, and let Scout work through two turns.

```python
from vfs import Authority, Principal, VirtualFileSystem

fs = VirtualFileSystem()
system = Authority.system()
fs.write(path="/notes/plan.md", content="Ship on Friday.\n", parents=True, authority=system)
fs.write(path="/notes/old.md", content="Last year's plan.\n", authority=system)

scout_is = Authority.of(Principal("scout"))
scout = fs.session(scout_is, "conv_123")

scout.start_turn("msg_1")
scout.read("/notes/plan.md")
scout.ls("/notes")

scout.start_turn("msg_2")
scout.edit("/notes/plan.md", old="Friday", new="Monday")
scout.write(path="/notes/risks.md", content="No risks yet.\n")
scout.delete("/notes/old.md")
```

In turn `msg_2` Scout edited one file, made one and deleted one. The user now edits message 2, so everything Scout did in answer to it should go.

## Step 2: See What a Rewind Would Do

Ask for a preview first. It returns the plan and changes nothing.

```python
plan = scout.rewind(before="msg_2", files=True, preview=True)
[(row.path, row.status) for row in plan.files.observations]
```

```text
[('/notes/old.md', 'created'), ('/notes/risks.md', 'deleted'), ('/notes/plan.md', 'updated')]
```

Each row is a file the rewind would put back, with what would happen to it.

| `status` | What it means |
|---|---|
| `updated` | The file stays where it is and gets its earlier content back |
| `deleted` | A file the session made goes to the trash |
| `created` | A file the session deleted or moved comes back at its earlier path |
| `unchanged` | The file is already as it was |

A preview does not show the text that would change. It shows which files would be touched and how.

## Step 3: Rewind the Session and Its Files

Make the same call without `preview`.

```python
done = scout.rewind(before="msg_2", files=True)
done.turns, done.jobs, len(done.files.observations)
```

```text
(1, 0, 3)
```

The files went back first, and then the session forgot turn `msg_2`. `done.turns` is the number of turns removed, and `done.jobs` is the number of waiting jobs that were cancelled.

```python
print(scout.read("/notes/plan.md"))
```

```text
Ship on Friday.
```

**Nothing was destroyed.** The content that was replaced is still kept as an earlier version of the file. The file Scout made is in the trash, where it can be restored. A rewind writes new versions and removes none, so the history shows what happened and a person can undo any part of it by hand.

Without `files=True`, a rewind changes only what the session remembers and touches no file, as the session guide describes.

## Step 4: A File Somebody Else Changed Is Left Alone

Run Step 1 again on a new file system, so that turn `msg_2` is there once more. This time, have Ada edit the plan after Scout did and before the rewind.

```python
ada = Authority.of(Principal("ada", name="Ada Lovelace"))
fs.edit("/notes/plan.md", old="Monday", new="Tuesday", authority=ada)

done = scout.rewind(before="msg_2", files=True)
[(w.path, w.data["vfs.rewind"]["reason"]) for w in done.files.warnings]
```

```text
[('/notes/plan.md', 'changed')]
```

The plan was left exactly as Ada wrote it, and the report says so. The other two files were put back. One file that cannot be put back never stops the rest.

Each file that was left has a warning with a reason.

| `reason` | Why the file was left |
|---|---|
| `changed` | Somebody changed it after the session's last change |
| `not_there` | It is no longer at the path the session left it at |
| `gone` | A file the session deleted has since been destroyed for good |
| `path_taken` | Something the session did not put there stands at its earlier path |
| `not_empty` | A directory the session made now holds files the session did not make |
| `no_version` | Its earlier content is no longer kept |
| `partly` | It was put back as far as a change that somebody else made in between |

A file is also left when Scout no longer has the right to change it, or when its mount is read-only. The warning then carries the usual refusal for that.

## Step 5: Let a Policy Review a Rewind

A rewind that puts files back is one [step](../reference/glossary.md#step) to your policies. A [policy](../reference/glossary.md#policy) written for every change sees it once, as a whole, and can ask for a person.

```python
from vfs import Decision, Mutation, policy, require_approval

@policy
async def contracts_need_a_person(step: Mutation) -> Decision:
    if step.touches("/contracts"):
        return await require_approval("A change to a contract needs a person.")
    return Decision.allow()
```

`step.touches("/contracts")` is true when any file the rewind would put back is under `/contracts`. When the policy asks for a person, nothing is put back, and the session's memory is not rewound either.

```python
done = scout.rewind(before="msg_2", files=True)
done.files.interrupted
```

```text
True
```

Your application asks the person and resumes the job, as [Interrupt a Job and Ask a Person](interrupt-a-job-and-ask-a-person.md) shows. When the job is resumed, the plan is made again and every file is checked again. A file that changed while the job waited is left alone. So a resumed rewind can do less than the person saw, and never more.

If a policy denies the rewind outright, nothing is put back and `rewind` raises. Your application can then rewind the session's memory alone.

No policy is asked about a rewind made as the system authority.

## What a Rewind Does Not Put Back

- **A change made without a session.** A call on the file system with `authority=`, or a shell line run with `fs.cli`, is not recorded under any session.
- **Anything outside VFS.** A request a tool sent, a message, or a process that was started cannot be undone.
- **Rights.** Grants, revokes, postures and memberships are not put back.
- **A file destroyed for good.** A file the session deleted that has since been swept from the trash is reported as `gone`.
- **Dates.** A file put back shows the time it was put back as its last change.

A fork puts back only what the fork itself changed, never what its parent changed.

## What to Remember

- `rewind(before=turn, files=True)` puts back the files the session changed from that turn on, then rewinds the session's memory.
- Add `preview=True` to see the plan first. It changes nothing.
- A file somebody else changed is left alone and reported in `done.files.warnings`.
- Nothing is destroyed: replaced content is kept as a version, and removed files go to the trash.
- A rewind with files is one step to your policies, and it can be interrupted and resumed like any other.
