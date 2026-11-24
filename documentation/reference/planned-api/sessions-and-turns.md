# Sessions and Turns

A [session](../glossary.md#session) is VFS's side of one conversation, stored under its owner and an id you choose. A [turn](../glossary.md#turn) divides a session's work into parts, one for each message from the user. This page lists every name, argument, value and refusal of that design. [Keep a Session for Each Conversation](../../how-to/keep-a-session-for-each-conversation.md) shows it in use.

> **This page describes an API that is designed and not yet built.** It is written so the API can be agreed before the code is written. The names on this page may still change.

Every call is on both the asynchronous and the synchronous file system, with the same arguments.

## Ask for a Session

```python
fs.session(authority=None, id=None, *, strict=True, policies=())
```

| Argument | Default | Meaning |
|---|---|---|
| `authority` | The file system's default authority | Who every call through the handle is made as, and who owns the session |
| `id` | VFS makes one | The session's name inside its owner |
| `strict` | `True` | Refuse a change to a file the session has not been shown |
| `policies` | None | The session's own policies, asked after the file system's |

It returns a handle, an `AsyncSession` or a `Session`. **Making a handle stores nothing and reads nothing.** The same call returns the same session whether or not it existed before, and nothing is stored until the session has something to remember. There is nothing to open and nothing to close.

| On the handle | Meaning |
|---|---|
| `session.id` | The id, as given or as made |
| `session.authority` | The authority every call is made as |
| `session.strict`, `session.policies` | As given. Neither is stored, so pass them each time. |
| `session.turn` | The id of the turn the handle is in, or `None` before one is started |
| `session.parent` | On the handle `fork` returns, the id of the session it was forked from |
| Every verb, and `cli` | The file system's call, with the authority filled in |

`delete` on a handle is the file verb. It removes a path, never the session.

### The Id

An id is 1 to 255 visible ASCII characters, with no space. It is kept exactly as given and compared byte for byte, so `Conv_1` and `conv_1` are two sessions. It must be a `str`, so an integer or a `UUID` is refused. An id VFS makes is `ses_` followed by 26 characters, from 128 random bits.

### The Owner

**A session is stored under its owner and its id together, so the id is a name and never a key.** The owner is the authority's actor and the people it acts for.

- An agent acting for Ada and the same agent acting for Grace are two owners. The same id is two different sessions for them.
- Another owner's session is answered exactly as one that does not exist.
- **An anonymous caller owns no session.** Asking for one raises an error. Give each caller a principal of its own.
- **When the people an agent acts for change, the owner changes.** If someone joins a group chat, the same id is then a new and empty session, and the agent reads files again before it changes them.
- A session stores no right. Every call is checked against its authority at the time of the call.

## What a Session Remembers

A session keeps a [stamp](../glossary.md#stamp) for each path it has been shown. A stamp records which file it was and at which version.

| Call through a session | What it stamps |
|---|---|
| `read` | Every row it returns |
| `stat`, `ls`, `tree`, `glob`, `grep`, `search`, `traverse` | The rows it returns, up to 1,024 for one call |
| A change the session makes | The file as the change left it |

When the caller states no precondition of its own, the session fills one in.

| Call | The session was shown the file | Not shown, and strict | Not shown, `strict=False` |
|---|---|---|---|
| `write` of one path | Sent with the etag it was shown | A new file is made. A file that is already there is refused as unread. | Sent as written |
| `write(append=True)` | No precondition | No precondition | No precondition |
| `edit`, `delete`, `move` | Sent with the etag it was shown | Refused as unread. Nothing is sent. | Sent as written |
| `copy`, `mkdir`, `restore` | No precondition | No precondition | No precondition |

A session takes no etag from its caller. Its `write`, `edit`, `delete`, `move` and `restore` have no `if_match` argument, because the session fills the etag in. [Etags and Preconditions](etags-and-preconditions.md) describes `if_match`, which is for a call made on the file system with no session.

A read's stamps are written a moment after the read returns, so a read costs the same with a session as without one. A change's stamps are written before the change returns. `fs.close()` writes whatever is waiting. **A program that ends after each request should close the file system before it ends.**

### The Two Refusals

| Kind | When | What an agent reads |
|---|---|---|
| `vfs.conflict.changed` | The file is no longer the one the session was shown | `Changed since it was read — This file changed after it was last read in this conversation, so nothing was written. Read it again, then make the change.` |
| `vfs.conflict.unread` | Strict, and the session was never shown the file | `Not read yet — This file has not been read in this conversation, so nothing was changed. Read it first, then make the change.` |

Nothing was changed. One read of the path clears either refusal. Neither carries the file's current version, because an agent handed one would send it straight back and write over a file it has not read. A program that does not know these kinds reads both as `vfs.conflict`.

## Turns

```python
session.start_turn(id=None) -> str
session.turns(*, after=None, limit=100) -> tuple[Turn, ...]
```

`start_turn` starts a turn and returns its id. Everything done through that handle afterwards is recorded under the turn. It stores the turn at once, so a turn in which the agent touches no file is still known.

- **Starting a turn the session already has carries it on.** A turn often spans several requests, and each of them starts the same id.
- With no id, VFS makes one, such as `turn_01JD3K7Q`.
- A turn id follows the rule for a session id, which is 1 to 255 visible ASCII characters.
- The turn is on the handle. Two handles of one session may be in two turns, and the store holds no "current turn".
- A call made through a handle with no turn started goes into the session's latest turn.

`turns` lists a session's turns, oldest first. A `Turn` has an `id`, a `number` and a `started_at`. Numbers rise, may skip, and are never used twice.

## Rewind

```python
session.rewind(*, before, files=False, preview=False) -> Rewind
```

| Argument | Meaning |
|---|---|
| `before` | A turn id. That turn and every later one are removed. |
| `files` | Also put back the files the session changed in those turns |
| `preview` | With `files=True`, return the plan and change nothing |

A rewind makes the session remember what it remembered before that turn.

- A file read in a kept turn and again in a removed one is still read.
- A file read in a kept turn and changed in a removed one is remembered as it was read, so the session's next change to it is refused until it is read again.
- The shell is where it was when the last kept turn ended.
- Waiting jobs of the removed turns are cancelled.
- **Without `files=True` it changes no file.**
- **It cannot be undone.** Fork first to keep the old line of the conversation.

A `Rewind` has `before`, `turns` (how many were removed), `jobs` (how many were cancelled) and `files`.

### Putting Files Back

With `files=True`, the files the session changed in the removed turns are put back first, and then the session's memory is rewound. [Rewind a Conversation and Put Its Files Back](../../how-to/rewind-a-conversation-and-put-its-files-back.md) shows it in use.

| In the removed turns the session | The rewind |
|---|---|
| Wrote, edited or appended to a file | Writes its earlier content, as a new version |
| Made a file or a directory | Deletes it, to the trash |
| Deleted a file or a directory | Restores it |
| Moved a file or a directory | Moves it back |

- **A file is put back only if nobody else has changed it since** the session's last change to it. Otherwise it is left as it is and reported.
- It puts back what it can and reports the rest. One file that cannot be put back does not stop the others.
- Nothing is destroyed. Replaced content is kept as a version, and a removed file goes to the trash.
- A rewind with files is one [step](../glossary.md#step), `RewindStep`, to your policies, and one job if it is interrupted.

`Rewind.files` is a result. Its `observations` hold one row for each file put back, with a `status` of `updated`, `deleted`, `created` or `unchanged`. Its `warnings` hold one entry for each file left as it is, and `data["vfs.rewind"]["reason"]` says why, as one of `changed`, `not_there`, `gone`, `path_taken`, `not_empty`, `no_version` or `partly`.

A change made without a session is not recorded, so a rewind cannot put it back. Neither can it put back rights, anything outside VFS, or a file that has been destroyed for good.

## Fork

```python
session.fork(id=None, *, before=None)
```

It makes a new session of the same owner and returns a handle to it. `before` names a turn, as for a rewind, and the fork gets the turns before it. With no `before`, it gets every turn.

| A fork copies | A fork shares | A fork leaves behind |
|---|---|---|
| The turns up to the fork point | Every file | Jobs waiting for an answer |
| What the session was shown in those turns | | The record of what the session changed |
| The shell's directory and exported variables | | |

**A fork shares the files.** A change through either session is seen by the other, whose next write to that file is refused until its agent reads it again. Forking to an id the owner already uses is refused. Removing the parent changes nothing in the fork.

## The Shell

A session keeps two things of its shell from one line to the next. They are the working directory and the exported variables. Each line behaves as a new bash process started where the last line ended. A variable that was not exported, a function, an alias and the history are gone when the line ends.

`session.cli(line, *, cwd=None, stdin=b"")` starts in the session's own directory when `cwd` is `None`.

A line run with `fs.cli(...)` and no session gets a strict session of its own for the length of the line. It is never stored.

## List and Remove Sessions

```python
fs.sessions(authority=None, *, after=None, limit=None) -> SessionPage
fs.remove_session(authority, id) -> bool
session.exists() -> bool
```

`fs.sessions` lists the caller's own sessions, 100 to a page. The system authority is shown every owner's. Each row is a `SessionInfo` with `id`, `parent`, `fork_before`, `turns`, `created_at`, `last_used_at`, `expires_at`, `actor` and `subjects`.

`fs.remove_session` removes a session at once and returns whether one was there. Its turns, its stamps and its record of changes are deleted. Its waiting jobs are cancelled. Its forks and the files it changed are untouched. Its id is free at once.

A session expires 30 days after its last use. Set the time with `VirtualFileSystem(session_lifetime=...)`. An expired session is treated as removed.

## What Is Removed

| Removed | Use instead |
|---|---|
| `fs.open_session(authority)` | `fs.session(authority)` |
| `session.close()`, `session.closed`, `with fs.open_session(...) as s` | Nothing. There is nothing to close. |

## Refusals

`start_turn`, `turns`, `rewind`, `fork`, `fs.sessions` and `fs.remove_session` manage VFS's own records. They return plain values, and raise an error that carries a result.

| When | Kind |
|---|---|
| A session id or a turn id that breaks the rule for ids | `vfs.invalid` |
| An anonymous caller asks for a session | `vfs.invalid` |
| `rewind` or `fork` names a turn the session does not have | `vfs.not_found` |
| `fork` to an id the owner already uses | `vfs.exists` |
| A change through a handle whose turn a rewind removed | `vfs.not_found` |

## Limits

| What | Value |
|---|---|
| A session id, and a turn id | 1 to 255 visible ASCII characters |
| `session_lifetime` | 30 days since the last use |
| What one session remembers | 16 MiB of stamps, about 90,000 files. The earliest turns are forgotten first. |
| Stamps left by one listing | 1,024 |
| The exported variables a session keeps | 32,768 bytes |
| A page of `fs.sessions`, and of `turns` | 100 |

In a strict session, forgetting a stamp can only cause a refusal that one read clears.

A file system whose root storage is in memory keeps its sessions in memory, even when a database is mounted beneath the root. On SQLite the sessions are in a second file beside your database.

## Mapping a Chat Stack

| Stack | Session id | Turn id |
|---|---|---|
| Vercel AI SDK | The chat `id` | The id of the last user message |
| AG-UI | `threadId` | The id of the last user message |
| LangGraph | `thread_id` | An id your application gives the run |

An edit or a regenerate is one `rewind`, to before the first message the client threw away, and then one `start_turn`. A branch into a new conversation is one `fork`. VFS never infers either from the messages.

## Choices Still Open

Each of these is decided in the specs for now, and is the project owner's to confirm.

| Choice | Decided for now |
|---|---|
| The name `fs.session` | Kept, with one exception added to the naming rules. The other choice is `fs.use_session`. |
| An anonymous caller | Owns no session |
| A changed set of people | Is a new owner, so a new and empty session |
| The characters of an id | Visible ASCII only |
| A bare shell line | Is strict, so `fs.cli("rm /f")` on a file the line has not listed is refused |
| An append to a file the session has read | Is never held to a stamp |
| A public call that writes waiting stamps | None. Closing the file system does it. |
| Shell history between lines | Not kept |
| Undo of a rewind | None |
| A fork to an id already in use | Refused |
| A rollback and the policies | One step for the whole rollback |

The full designs are in `agents/`, in the work directories for a stored session, what a session remembers, turns, and a rewind that puts files back.
