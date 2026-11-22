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

## Etag

An etag is a short value on a row that names one [entry](#entry) at one version. Two results show the same etag only when they saw the same file in the same state.

A caller that reads a file and changes it later passes the etag back as `if_match`. The change is made only when the file at that path still has that etag. When the file has been changed, or when a different file has come to stand at the path, nothing is changed and the call is refused with a conflict.

An etag is compared and never taken apart. It cannot be turned back into a version number, and it grants no right to anything. It changes whenever the file's version does, and it stays the same when a directory above the file is moved, deleted or restored.

The etag is part of a design that is not yet built. [Etags and Preconditions](planned-api/etags-and-preconditions.md) has its details.

## Interrupt

An interrupt is what a stopped [job](#job) is waiting for: a message for a person, the shape the answer must have, and a preview of what would change. A [policy](#policy) raises one when a [step](#step) needs a person.

An application builds its question from those three things alone, and asks the person in whatever way it likes. The answer goes back through `resume`, and the job carries on.

A job has at most one interrupt waiting. An answer belongs to that interrupt of that job and to nothing else.

The interrupt is part of a design that is not yet built. [Jobs and Interrupts](planned-api/jobs-and-interrupts.md) has its details.

## Job

A job is one call through VFS. A direct call such as `edit` is a job of one [step](#step), and a line of shell is a job of many.

Most jobs finish inside the call that started them, and VFS keeps nothing for them. A job is stored only when a step needs a person. VFS then saves the job and returns at once, and what the job waits for is its [interrupt](#interrupt).

A stored job has an id and a state. `resume` gives it an answer and carries it on, as the caller that started it, from any program that can reach the same database. A job that nobody answers lapses after a day.

A job is not a shell job. The shell's own `jobs`, `fg` and `wait` are about commands running inside one line.

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

A policy is a function the host writes that VFS shows each [step](#step) before the step runs. It allows the step, denies it with a reason, or asks for a person by raising an [interrupt](#interrupt).

The type of the policy's argument chooses the steps it is shown. A policy written for changes is never asked about a read.

A policy can only narrow what a caller may do. For a change, VFS checks the caller's rights first, and a change the caller may not make is refused before any policy is called. Every policy written for a step is asked, and one denial refuses the step.

A policy that raises an error, returns something that is not a decision, or takes too long refuses the step. No policy is asked about a step made as the system.

The policy is part of a design that is not yet built. [Policies and Steps](planned-api/policies-and-steps.md) has its details.

## Session

A session is what VFS keeps for one conversation: who the agent is, what it has been shown, and where its shell is. The host's application keeps the messages.

A session is stored by the file system, under its owner and an id the host chooses, so any program can ask for it again. The owner is the authority the session was asked for with. The id is a name inside that owner and opens nothing by itself: a caller with another authority who passes the same id gets a session of its own.

A session refuses to change a file that has changed since the agent was shown it, and a file the agent was never shown. What it remembers of each file is a [stamp](#stamp). Its work is divided into [turns](#turn), and it can be taken back to an earlier turn or forked at one.

A session stores no right. Every call made through it is checked against its authority at the time of the call. It is not a file and has no path.

The stored session is part of a design that is not yet built. [Sessions and Turns](planned-api/sessions-and-turns.md) has its details.

## Stamp

A stamp is a [session's](#session) memory that it was shown one path: as a file at one version, as a directory, or as holding nothing. For a file it holds the [etag](#etag) the file had when it was shown.

A session makes a stamp whenever a call through it returns a row, and whenever the session itself changes a file. A caller never writes one and cannot read one.

When the session later changes a file, it requires the file to still have the etag in its stamp. If the file has moved on, the change is refused and nothing is written. One read of the file makes a new stamp, and the change then goes through.

Stamps are stored with the session, one for each path and [turn](#turn). They are bounded, and a session that passes its bound forgets the oldest. A forgotten stamp can only cause a refusal.

The stamp is part of a design that is not yet built. [Sessions and Turns](planned-api/sessions-and-turns.md) has its details.

## Step

A step is one verb about to run, with the arguments VFS has already checked, as a value that cannot be changed. It is what VFS shows a [policy](#policy).

A direct call such as `edit` is one step. A line of shell makes one step for each verb it carries out. One step is not a verb: a rewind that puts a [session's](#session) files back is a single step, judged once.

Every step has its verb, the paths it names, and the authority that is calling. Each kind of step adds the arguments of its own verb, so an edit's step has the path, the old text and the new text.

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

A turn is one message from the user and everything the agent does in answer to it, kept as one part of a [session](#session).

The host starts a turn at the top of each request and gives it an id, usually the id of the user's message. Everything the session records from then on belongs to that turn: what the agent was shown, what it changed, where its shell went, and any [job](#job) that was interrupted. A turn often spans several requests, and each of them starts the same id.

A turn is the point a session is rewound to or forked at. Because each record belongs to a turn, a session can forget everything from one message onward and nothing before it.

The turn is part of a design that is not yet built. [Sessions and Turns](planned-api/sessions-and-turns.md) has its details.
