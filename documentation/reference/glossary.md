# Glossary

The words VFS uses, and what each one means. **A word has one meaning here, and a meaning has one word.**

Terms are in alphabetical order. Each term has six parts.

| Part | What it holds |
|---|---|
| Name | The word itself. |
| Description | The full meaning. It says what the term is, then gives its rules, an example and its edges. It stands on its own. Another term from this page appears only as a link. |
| Types | The class or classes that are this thing in code. "None" when the thing has no class of its own. |
| Code | Every class and function whose docstring marks the term. |
| Documentation | Every page outside this reference section that links to the term. |
| Related terms | The terms this description links to, and the terms whose descriptions link to it. |

## Arm

An arm is one plain file pattern, a pattern with no `{a,b}` choices left in it. A pattern a caller writes can expand into several arms. For example, `*.{py,md}` is two arms, `*.py` and `*.md`. An arm is a plain string and has no class of its own.

An arm is one of two kinds.

| Kind | How to tell | What it matches | Example |
|---|---|---|---|
| Name arm | It has no `/` | The name of an [entry](#entry), at any depth | `*.py` |
| Path arm | It has a `/` | The whole path of an [entry](#entry), from the top of the file tree | `src/*.py` |

One pattern may expand to at most 64 arms, the value of [`MAX_PATTERN_ARMS`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/pattern_matching/glob.py). A pattern that expands past it is refused with the error "expands past the arm cap". That error is the one place a caller meets the word.

## Entry

An entry is one file or one directory in the file tree. A file is an entry with content, and a directory is an entry with none.

The path a [mount](#mount) is attached at is an entry too. It is an empty directory, stored in the mount above it. The directory is the entry. The [storage](#storage) attached there is the mount.

## Interrupt

An interrupt is a question that a person must answer before VFS goes on. It comes up when an agent tries something that needs a person's say, such as an edit to a contract. VFS stops the [job](#job) before anything is changed and hands the interrupt back to the application.

An interrupt has three parts.

| Part | What it is |
|---|---|
| Message | The question, in words a person can read |
| Schema | The form the answer must take, such as approve or deny |
| Preview | What would change if the person says yes |

The application shows these to a person in whatever way it likes, such as a chat window, an email or a ticket. VFS does not ask the person and does not wait for them. When the person answers, the application passes the answer to `resume`, and the job carries on from where it stopped.

A job waits on one interrupt at a time. An answer is for that one interrupt and cannot be used on another job. An interrupt is raised by a [policy](#policy), when the policy sees a [step](#step) that needs a person.

The interrupt is part of a design that is not yet built. [Jobs and Interrupts](planned-api/jobs-and-interrupts.md) has its details.

## Job

A job is one piece of work a caller asks VFS to do. One call is one job. A call such as `edit` is a job with one [step](#step). A line of shell such as `cp a b && rm a` is a job with several.

Almost every job starts and finishes inside its call, and VFS keeps no record of it. A job is saved only when it has to stop and ask a person something. VFS then saves the job in the database and returns at once. The question it left behind is the job's [interrupt](#interrupt).

A saved job has an id. The application passes that id and the person's answer to `resume`, and the job carries on as the caller that started it. Any program that can reach the same database can do this, so the person may answer hours later and from another server. A job that nobody answers within a day is ended.

A job here is not a shell job. The shell commands `jobs`, `fg` and `wait` are about commands running inside one line.

The job is part of a design that is not yet built. [Jobs and Interrupts](planned-api/jobs-and-interrupts.md) has its details.

## Kernel

The kernel is the object that holds the file tree and answers every call on it. For each call it finds the [mount](#mount) that holds the path, checks the call against the permissions of that mount, and sends the call to the [storage](#storage) of that mount with the name of the caller. The storage decides what that caller may see or change. **Every call passes through the kernel, so no call reaches a storage unchecked.**

In code the kernel is `AsyncVirtualFileSystem`, with calls you `await`. `VirtualFileSystem` is the same kernel with plain calls. One kernel is one file tree. A kernel never holds another kernel, and two file trees are joined only through a storage.

The name follows the kernel of an operating system, which every call on a file passes through.

## Mount

A mount is [storage](#storage) attached at a path in the file tree. **Every path belongs to exactly one mount, the deepest one at or above it.** With one mount at `/` and one at `/projects`, the path `/projects/app/main.py` belongs to the mount at `/projects`.

A mount is attached at an [entry](#entry), an empty directory. `fs.add_mount()` makes that directory when it is absent. **The directory is stored. The mount is not.** The mount lasts only while the file system is open. `fs.remove_mount()` removes the mount and then its directory.

While a mount is attached, its path shows the top of the mounted storage and never the directory beneath it. `fs.ls("/")` and `fs.stat("/projects")` return the same row for `/projects`. The name of a mount is never hidden from a caller who can list the directory it is in.

Adding or removing a mount is a write at its path. A read-only mount takes no new mount beneath it and loses none. The caller must also hold `read_write` at that path, as for a change to who can access it. `fs.add_mount(..., posture=...)` sets the level that everyone holds at the root of the mounted storage, before the mount can be reached. A posture set deeper in that storage stays.

## Policy

A policy is a rule that the application writes as a Python function. VFS calls the function just before each [step](#step) runs, and the function gives one of three answers.

| Answer | What happens |
|---|---|
| Allow | The step runs |
| Deny | The step is refused, and the agent is told the reason |
| Ask a person | The step stops and waits for an answer, as an [interrupt](#interrupt) |

For example, one policy can let an agent edit any file and ask a person before an edit under `/contracts`.

A policy chooses the steps it sees by the type of its argument. A policy written for deletes is never called for a read.

A policy can take access away and can never give it. For a change, VFS first checks that the caller is allowed to make the change at all, and it calls a policy only when the caller is. When several policies see one step, every one of them is asked, and one "deny" is enough to refuse the step.

A policy that breaks refuses the step. That covers a policy that raises an error, one that returns something other than the three answers, and one that takes longer than ten seconds. Policies are not called for work VFS does as the system.

The policy is part of a design that is not yet built. [Policies and Steps](planned-api/policies-and-steps.md) has its details.

## Session

A session is the record VFS keeps of one conversation with an agent. It remembers which files the agent has seen and which directory the agent's shell is in. It does not hold the messages. Those stay with the application.

A session has an id. The application usually gives it the id it already has for the conversation, such as `conv_123`. VFS saves the session in the database, so the next request can ask for the same id and get the same session back, on any server.

A session belongs to its owner, the caller it was made for. The id is only a name, and knowing an id does not let a caller into another caller's session. A different caller who passes the same id gets a new, empty session of its own.

A session protects files from stale changes. It refuses to change a file that has changed since the agent last saw it, and it refuses to change a file the agent never saw. The note it keeps for each file is a [stamp](#stamp). A session's work is split into [turns](#turn), and a session can be taken back to an earlier turn or copied from one.

A session gives no access to anything. Every call made through it is checked against what its owner may do at that moment. A session is not a file and has no path.

The stored session is part of a design that is not yet built. [Sessions and Turns](planned-api/sessions-and-turns.md) has its details.

## Stamp

A stamp is a note that a [session](#session) keeps about one path. The note says that the agent has seen the path, and what was there when it did. What was there is a file, a directory, or nothing. For a file, the stamp keeps the file's [vid](#vid).

A session writes its stamps by itself. It writes one each time a call shows the agent a file or a listing, and each time the session changes a file. A caller never writes a stamp and cannot read one.

Stamps are how a session catches a stale change. Before it changes a file, the session checks that the file still has the vid in its stamp. If somebody else has changed the file, the change is refused and nothing is written. The agent reads the file again, which makes a new stamp, and the change then goes through.

Stamps are saved with the session, one for each path in each [turn](#turn). A session keeps a limited number of them, and when it has too many it drops the oldest. Losing a stamp is safe. The worst that follows is a refusal, and the agent reads the file again.

The stamp is part of a design that is not yet built. [Sessions and Turns](planned-api/sessions-and-turns.md) has its details.

## Step

A step is one action that VFS is about to take, such as an edit of `/contracts/acme.md`. VFS describes the action before it happens, so that a [policy](#policy) can look at it and decide whether it may run.

A direct call such as `edit` makes one step. A line of shell makes one step for each action it carries out. A step is usually one verb, and a rewind is the exception. A rewind that puts a [session's](#session) files back may restore many files, and it is still one step that is judged once.

A step holds what a policy needs to judge it. Every step says which verb it is, which paths it names, and who is calling. Each kind of step adds the arguments of its own verb, so the step for an edit also has the old text and the new text.

A step cannot be changed. A policy reads it and decides, and nothing more. VFS builds the step after it has checked the call's arguments, so what a policy reads is what will run.

The step is part of a design that is not yet built. [Policies and Steps](planned-api/policies-and-steps.md) has its details.

## Storage

A storage is an object that keeps [entries](#entry) and answers the calls made on them. It is where the files are held. **A storage has no place in the file tree until it is attached as a [mount](#mount).** The [kernel](#kernel) then sends it every call on a path that mount holds.

A storage knows only its own paths, which start at its own root. The mount gives that root a path in the file tree. The same storage attached at `/data` or at `/archive` holds the same entries.

A storage also decides what each caller may see or change. The kernel passes it the name of the caller with every call.

In code a storage is any object with the members of `StorageBackend`. It has a name and a description, it can be read, and it declares the other calls it answers. Four classes come with VFS.

| Class | Where the entries are kept |
|---|---|
| `SQLiteStorage` | A SQLite database, in the file its path names |
| `PostgresStorage` | A Postgres database, named by a URL |
| `InMemoryStorage` | A SQLite database in memory, which is gone when the storage is closed |
| `DatabaseStorage` | Any SQL database SQLAlchemy reaches. The three above are built on it, and a database other than SQLite and Postgres is fit for testing only |

A kernel that is given no storage makes an `InMemoryStorage` for its root. A storage can also wrap another kernel, and that is the only way two file trees are joined.

## Turn

A turn is one message from the user together with everything the agent does to answer it. A [session](#session) is a series of turns, one after another.

The application starts a turn at the start of each request. It calls `start_turn` with an id, usually the id of the user's message. From then on, everything the session records is marked with that turn. That covers the files the agent saw, the files it changed, where its shell went, and any [job](#job) that stopped to ask a person. One turn can run over several requests, and each request starts the same id again.

Turns are what let a conversation go back. When a user edits an earlier message, the application rewinds the session to before that message's turn. The session forgets everything from that turn on and keeps everything before it. A fork uses a turn in the same way. It copies the session up to that turn into a new session and leaves the first one as it is.

The turn is part of a design that is not yet built. [Sessions and Turns](planned-api/sessions-and-turns.md) has its details.

## Vid

A vid is a short code that VFS returns with every [entry](#entry). The name is short for version and id. The code stands for one file at one version, so when the file changes, its vid changes too.

A vid lets a change say "only if this file is still the one that was read". A [session](#session) does this by itself. It keeps the vid of each file it was shown and sends it with each change, so an agent never handles a vid. Code that works without a session can pass one by hand, as `if_vid`. If the file still has that vid, the change is made. If the file has a different vid, nothing is changed and the call is refused with a conflict. The file is then read again and the change tried once more.

For example, an agent reads `/notes/plan.md` and edits it a minute later. If a teammate saved the file in that minute, the vid no longer matches and the edit is refused. The teammate's work is not written over. The same happens when the file was deleted and a new file was made at the same path.

A vid is only for comparing. A caller cannot read a version number out of it, and holding one gives no access to the file. Moving, deleting or restoring a directory above a file leaves the file's vid as it was.

No change has to carry a vid. A change sent without one is made as it is sent.

Every row a call returns with a version carries its vid today, as `Observation.vid`, and `write` takes one back as `if_vid`. The same argument on `edit`, `delete`, `move` and `restore` is part of a design that is not yet built. [Vids and Preconditions](planned-api/vids-and-preconditions.md) has its details.
