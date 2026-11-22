# Keep a Session for Each Conversation

This guide shows how to give each conversation an agent has a session of its own, so that VFS remembers what the agent has read from one request to the next, and how to rewind or fork that session when the conversation is edited or branched. Use it when you build a chat application, or any agent whose work on one task spans more than one request.

> **This guide describes an API that is designed and not yet built.** It is written first so that the API can be agreed before the code is written. The names on this page may still change.

**A session is VFS's side of one conversation.** Your application or its agent framework keeps the messages. VFS keeps three things for the conversation: who the agent is, what the agent has been shown, and where its shell is. The second is the important one. An agent that reads a file and changes it ten minutes later should not overwrite a change somebody else made in between, and the session is what stops it.

**A session is stored in the database, and the object in your code is only a handle to it.** A chat application usually handles each message in a new request, often in another process. A session that lived in one process's memory would forget everything between two messages. So VFS keeps the session in the database you already run, under an id you choose, and any process can pick it up by that id.

## Before You Begin

You need Python 3.11 or later with `vfs-py` installed, and you should have finished [Give an AI Agent the File System](../tutorials/give-an-ai-agent-the-file-system.md).

The examples use an agent named Scout, a person named Ada who edits the same files, and a conversation whose id is `conv_123`. Each Python block is one notebook cell, and the block after it shows what the cell prints. The calls use the synchronous file system, `VirtualFileSystem`.

## Step 1: Name the Session After the Conversation

Create the file system with one file in it, then ask for Scout's session for the conversation.

```python
from vfs import Authority, Principal, VirtualFileSystem

fs = VirtualFileSystem()
system = Authority.system()
fs.write(path="/notes/plan.md", content="Ship on Friday.\n", parents=True, authority=system)

scout_is = Authority.of(Principal("scout"))
scout = fs.session(scout_is, "conv_123")
scout.id
```

```text
'conv_123'
```

`fs.session(authority, id)` gives you the session with that id. It does not matter whether this is the first time the id has been used: the first call and the hundredth are the same call, and they return the same session. Nothing is stored until the session has something to remember, so the call itself costs nothing. Use the id your application already has for the conversation, and you never need a table that maps one id to the other. An id is a string of 1 to 255 characters. When you pass no id, VFS makes one, and `scout.id` holds it.

**A session belongs to the authority that uses it.** VFS stores a session under its owner and its id together, so the id is a name and never a key that opens anything. Another caller who passes `"conv_123"` gets a session of their own with that name, empty, and never sees Scout's. [Who Owns a Session](#who-owns-a-session) says exactly what the owner is.

## Step 2: Read a File, Then Change It

A session has every verb the file system has, with the authority filled in. Have Scout read the plan and change it.

```python
print(scout.read("/notes/plan.md"))
scout.edit("/notes/plan.md", old="Friday", new="Monday")
```

```text
Ship on Friday.

Edited /notes/plan.md
```

When the session showed Scout the file, it recorded which file it was and which version. The edit was allowed because the file was still at that version. Now let Ada change the file, and have Scout try to change it again from what it read earlier.

```python
ada = Authority.of(Principal("ada", name="Ada Lovelace"))
fs.edit("/notes/plan.md", old="Monday", new="Tuesday", authority=ada)

print(scout.edit("/notes/plan.md", old="Monday", new="Wednesday"))
```

```text
edit errors:
  ERROR /notes/plan.md: Changed since it was read — This file changed after it was last read in this conversation, so nothing was written. Read it again, then make the change. (retry: refresh)
```

Nothing was written, and the message tells the agent the one thing that will work. Your code carried no version from the read to the edit. The session did that.

**A session also refuses to change a file it has never been shown.** An agent that deletes or overwrites a file it has not looked at is guessing, so the session stops it.

```python
fs.write(path="/notes/budget.md", content="Budget: 40,000\n", authority=system)
print(scout.delete("/notes/budget.md"))
```

```text
delete errors:
  ERROR /notes/budget.md: Not read yet — This file has not been read in this conversation, so nothing was changed. Read it first, then make the change. (retry: refresh)
```

Reading the file, or listing the directory it is in, is enough. Making a new file needs no read, and neither does adding to the end of one, because neither destroys anything. A session you ask for with `fs.session(scout_is, "conv_123", strict=False)` keeps the first rule and drops the second: it still refuses to write over a file that changed, and it lets a change to an unread file through.

## Step 3: Carry On in Another Request

Have Scout read the plan again. Then stand in for the next request by asking for the session again, as a new process would.

```python
print(scout.read("/notes/plan.md"))

later = fs.session(scout_is, "conv_123")
later.edit("/notes/plan.md", old="Tuesday", new="Wednesday")
```

```text
Ship on Tuesday.

Edited /notes/plan.md
```

`later` is a second handle to the same session, and it knew that Scout had read the file, so the edit went through with no second read. This works across processes and machines, because what the session has seen is in the database and not in either handle. There is nothing to close and nothing to save: a handle holds nothing that the database does not, and you can drop it whenever you like.

What a session has seen is written to the database a moment after each read, not during it, so a read costs the same with a session as without one. If the process stops in that moment, the session forgets that one read, and the worst that follows is a "Not read yet" refusal and a second read.

## Step 4: Start a Turn

A *turn* is one message from the user and everything the agent does in answer to it. Start a turn at the top of each request, before the agent does anything, and give it an id.

```python
scout = fs.session(scout_is, "conv_123")
scout.start_turn("msg_4")

print(scout.read("/notes/plan.md"))
print(scout.read("/notes/budget.md"))
```

```text
Ship on Wednesday.

Budget: 40,000
```

The user sends another message, so start the next turn.

```python
scout.start_turn("msg_5")

print(scout.edit("/notes/plan.md", old="Wednesday", new="Thursday"))
print(scout.cli("cd /notes && cat budget.md"))
```

```text
Edited /notes/plan.md
Budget: 40,000
```

`start_turn(id)` starts a turn in the session, and from then on everything done through that handle is recorded under it: what the agent reads, what it changes, where its shell goes, and any job that is interrupted. A turn is a partition of the session's work, and it is the point you later rewind or fork to. Starting a turn stores one small record, so that VFS knows the order of the session's turns, including a turn in which the agent never touches a file.

Use an id your application already has for the turn, such as the id of the user's message. The same id can then name the turn in your chat history, in your agent framework and in VFS, which is what lets you rewind all three to one point. An id is a string of 1 to 255 characters, and it need only be different from the other turns of the same session. When you have no id of your own, call `start_turn()` with none, and VFS makes one and returns it.

```python
turn_id = scout.start_turn()
turn_id, scout.turn
```

```text
('turn_01JD3K7Q', 'turn_01JD3K7Q')
```

`scout.turn` holds the id of the turn the handle is in.

A turn often spans more than one request. The agent calls a tool, your application answers in a second request, and both belong to the same message. Call `start_turn` with the same id at the top of each of those requests. **Starting a turn the session already has carries that turn on.** It never makes a second turn with the same id, so a request that is sent twice does no harm.

Start a turn on every request, as the first thing you do with the session. Calls made through a handle before any turn is started on it go into the session's latest turn, or into a first turn that VFS makes when the session has none. That is where the calls in the first three steps of this guide went.

## Step 5: Rewind to Before a Turn

Chat applications let a user edit an earlier message or ask for an answer again. The conversation keeps its id, and everything from that message onward is thrown away. No chat protocol tells the server this has happened, so your application must tell VFS.

```python
scout = fs.session(scout_is, "conv_123")
scout.rewind(before="msg_5")
```

`rewind(before="msg_5")` removes turn `msg_5` and every turn after it from the session. The session then remembers exactly what it remembered when `msg_4` ended.

| | Before the rewind | After `rewind(before="msg_5")` |
|---|---|---|
| `/notes/budget.md` | read in `msg_4` and again in `msg_5` | still read, from `msg_4`; Scout can change it without reading it again |
| `/notes/plan.md` | read in `msg_4`, changed in `msg_5` | remembered as it was read in `msg_4`, so a change is refused until Scout reads it again |
| The shell's directory | `/notes`, set in `msg_5` | `/`, as it was when `msg_4` ended |
| A job waiting for an answer, started in `msg_5` | waiting | cancelled |

The second row is the rule working as it should. After the rewind, the agent's own memory of the conversation no longer holds the change it made in `msg_5`. The file does. So the session treats the file as changed since it was read, and the agent reads it again before it writes.

**A rewind changes what the session remembers. It does not change any file.** The edit Scout made in `msg_5` is still in `/notes/plan.md`. VFS records every change with its session and its turn, so that the files a session changed can be put back as they were before a turn. That is a separate feature, planned for the same release.

After a rewind, your application can start `msg_5` again with `scout.start_turn("msg_5")`, and it is a new turn. A rewind to before a turn the session has never started is refused, and the refusal names the turn, so a mistyped id never passes as a rewind that did nothing. This is one more reason to start a turn on every request.

## Step 6: Fork a Session

Some applications branch a conversation into a new one and leave the first as it was. For that, fork the session.

```python
branch = scout.fork("conv_456")
branch.id, branch.parent
```

```text
('conv_456', 'conv_123')
```

Pass `before=` to fork from an earlier point, in the same way as a rewind: `scout.fork("conv_456", before="msg_4")` gives the new session everything from before `msg_4` and nothing after.

| A fork copies | A fork shares | A fork leaves behind |
|---|---|---|
| What the session has seen | Every file | Jobs waiting for an answer |
| The shell's directory and variables | | |
| Its turns, up to the fork point | | |

**A fork shares the files.** There is one file system, and both sessions work on it. If the branch changes a file, the original conversation sees the change, and its next write to that file is refused until its agent reads the file again. Each session is protected from the other's changes. Neither has a private copy.

A job that is waiting for a person stays with the session that started it. The question was put to a person once, and a fork must not put it twice.

## Step 7: Resume a Job Through Its Session

When a call is interrupted to ask a person something, its job belongs to the session that made the call, and is recorded under the turn. [Interrupt a Job and Ask a Person](interrupt-a-job-and-ask-a-person.md) covers interrupts in full. With a session, the request that brings the person's answer needs only the conversation's id. Suppose a call in this conversation was interrupted, and Ada has now said yes.

```python
scout = fs.session(scout_is, "conv_123")
[job] = scout.jobs(state="interrupted")
result = scout.resume(True, authority=ada)
```

`scout.resume(answer, authority=...)` resumes the one job the session has waiting. The `authority` is the principal who answered, never the agent. If more than one job is waiting, which happens when an agent makes several calls at once, the call is refused and names them, and you pick one with `scout.resume(answer, job=job.id, authority=ada)`. The job carries on as Scout, in the turn it started in, and what it writes is remembered by the session as Scout's own work.

`resume` and `jobs` are for your application's code. Do not offer them to the agent as tools.

## Find, Expire and Delete Sessions

`fs.sessions(scout_is)` lists the sessions Scout owns, with each one's id, parent, number of turns and time of last use. The system authority may list every session. `scout.exists()` says whether a session has stored anything yet.

A session that is not used for 30 days expires. You set the time with `VirtualFileSystem(session_lifetime=...)`. An expired session is deleted with what it had seen, and its waiting jobs are cancelled. If its id is used again, a new and empty session starts under that id, and the agent reads files again before it changes them. `scout.delete()` does the same at once.

A session also has a limit on how much it remembers. When a long conversation passes it, the session forgets the files it has gone longest without touching. Forgetting never lets a write through that would have been refused. It can only cause a "Not read yet" refusal, which one read clears.

## Who Owns a Session

The owner of a session is the whole authority: the agent, and the people it acts for. Scout working for Ada and Scout working for Grace are two owners, so `fs.session(authority, "conv_123")` is two different sessions for them, and neither can reach the other's by knowing its id. Every call through a session is still checked against what its authority may do at the time of the call. A session stores no rights, so taking a right away from Scout takes effect on Scout's next call.

## Calls at the Same Time

An agent often makes several calls at once within a turn, and a session allows it. Each call records what it saw for its own files, and two calls that touch different files do not meet. Two calls that change the same file meet at the file, where the second is refused as changed.

Two whole turns running on one session at the same time is a different matter. It happens when a user sends a message from two devices at once. VFS does not put turns in a queue. Your application should run one turn of a conversation at a time, as chat frameworks advise.

## Use It With a Chat Framework

Every chat protocol already carries the two ids a session needs.

| Your stack | Session id | Turn id |
|---|---|---|
| Vercel AI SDK | the chat `id` | the id of the user's message |
| AG-UI | `threadId` | `runId` |
| LangGraph | `thread_id` | an id your application gives the run |
| Your own | the conversation's id | the user message's id |

A request handler therefore begins with two lines: `scout = fs.session(authority, session_id)` and `scout.start_turn(turn_id)`.

These ids often come from the browser. That is safe, because the session id is only a name inside its owner. Check who the user is in your own code, build the authority from that, and pass the id as it came.

To rewind a whole stack to one point, use the turn's id in each layer: cut your chat history before the message, take your agent framework back to the checkpoint it saved for that turn, and call `scout.rewind(before=turn_id)`.

## Work Without a Session

A session is never required. A call made on the file system with `authority=` works as it always has: it remembers nothing, and it guards a write only when you pass the version you expect. A shell line run with `fs.cli(...)` and no session guards itself for the length of the line, so a command that reads a file and writes it back is still protected.

## What to Remember

- A session is VFS's side of one conversation: who the agent is, what it has seen, and where its shell is. Your application keeps the messages.
- `fs.session(authority, id)` gives you the session with that id, new or not. It is stored in the database, and the object is a handle.
- A session refuses to change a file that changed since the agent read it, and a file the agent has never read.
- Call `start_turn(id)` at the top of every request. `rewind(before=turn)` takes the session back, and `fork(id, before=turn)` starts a new session from that point.
- A rewind and a fork change what a session remembers. They never change a file, and a fork shares the files.
- A session belongs to its authority. Its id is a name, never a key.
