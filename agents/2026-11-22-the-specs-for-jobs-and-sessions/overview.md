# The specs for jobs and sessions: what each one decides, and what they share

Written on 2026-11-22, and brought up to date after the nine specs were reconciled with each other in three rounds. The specs hold 235 decisions. None is reviewed and nothing is built. No claim about Postgres was run: each spec lists, under "Not checked", what to run. Each spec ends with its choices for the owner, and `documentation/reference/planned-api/` lists the public surface they add up to.

First written on 2026-11-22. Nine specs turn two designs into buildable work: a job that is interrupted and resumed, and a session that is stored, works in turns, and is rewound or forked. This page is their map. It says what each spec owns, the order they are built in, and the names, records and rules that more than one of them uses. A spec that needs a shared name takes it from here, and a spec that finds a shared decision wrong says so in its own text and does not quietly choose another.

The public face of both designs is written already, as two guides. They are the reference for every signature and every message an agent or a developer sees:

- `documentation/how-to/interrupt-a-job-and-ask-a-person.md`
- `documentation/how-to/keep-a-session-for-each-conversation.md`

The research is in `agents/2026-11-22-a-job-is-interrupted-and-resumed/research/` (five studies of interrupts, two of approval and tools) and `agents/2026-11-22-a-session-is-stored-named-and-forked/research/` (seven studies of sessions).

## The model

- **Step.** One verb about to run, with its checked arguments, as a typed and frozen value.
- **Policy.** An `async` function the host writes, which is shown each step before it runs and allows it, denies it, or interrupts for a person.
- **Job.** One call through VFS. A direct verb is a job of one step, and a shell line is a job of many. A job that is interrupted is stored, and is resumed later with an answer, by any process.
- **Interrupt.** What a stopped job is waiting for: a message, a schema for the answer, and a preview. A job has at most one waiting at a time.
- **Session.** VFS's side of one conversation: who the agent is, what it has been shown, and where its shell is. It is stored under its owner and an id the caller may choose. The Python object is a handle that holds no state the store does not.
- **Stamp.** A session's memory that it was shown a path at an etag. An etag names one entry at one version.
- **Turn.** One message from the user and all the agent does in answer. A turn partitions a session's work, and is the point a session is rewound or forked to.

Three things are kept apart on purpose, because the history of sessions shows designs fail where they are merged: the session's context (owner, id, parent, shell state), its record of what it saw (stamps), and the jobs it started. A job points at its session. A session does not contain its jobs.

## The specs

| # | Work directory under `agents/` | What it decides | Builds on |
|---|---|---|---|
| 0 | `2026-11-22-the-kernel-keeps-records-of-its-own` | Where the kernel's own records live on each engine, how their tables are made, the write-behind writer and the synchronous path, the sweep that removes expired records, and what `close` does to them | the log cost study |
| 1 | `2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it` | `etag` on every row with a version, and `if_match=` on `write`, `edit`, `delete` and `move` | the write preconditions |
| 2 | `2026-11-22-a-session-is-stored-named-and-forked` | The session's identity and life: `fs.session`, the owner, the id, the handle, `exists`, `sessions`, `delete`, the lifetime, and the end of `open_session`, `close` and the context manager | 0 |
| 3 | `2026-11-22-the-session-remembers-what-it-read` | Stamps: what is stamped, where stamps are stored, how a session fills in `if_match`, strict, the two refusals and their words, the bound, and the session a bare shell line gets. It rewrites the spec merged from pull request 42 | 0, 1, 2 |
| 4 | `2026-11-22-a-session-works-in-turns-and-rewinds-or-forks-at-one` | `start_turn`, the turn record, shell state kept per turn, `rewind(before=)`, `fork(id, before=)`, lineage, and what each does to stamps and jobs | 2, 3 |
| 5 | `2026-11-22-a-rewind-puts-a-sessions-files-back` | The record of what a session changed in each turn, and `rewind(before=, files=True)` | 1, 3, 4 |
| 6 | `2026-11-22-a-policy-judges-each-step` | The typed `Step` classes, `@policy`, `Decision`, how policies combine, the session's own policies, failing closed, and the system authority's exemption | the parameter table |
| 7 | `2026-11-22-a-job-is-interrupted-and-resumed` | The job record, `interrupt()`, `require_approval`, the answer schemas, the interrupted result, `resume`, `Cancel`, the two kinds, `jobs`, who may resume, the lifetime, and `resume` and `jobs` on a session | 0, 1, 6 |
| 8 | `2026-11-22-an-interrupted-line-replays-its-replies` | A shell line as a job: its inputs and its journal of replies, the replay, the divergence check, and stopping once per interrupt | 7 |

**Build order.** 0 and 1 first, in either order, since neither needs the other. Then 6, then 7, then 8 on one line, and 2, then 3, then 4, then 5 on the other. The two lines meet in spec 7's section on sessions, which needs spec 2, and in spec 4's rule for jobs, which needs spec 7. Each spec is one or more landings that each leave the tree green.

**Left out of these nine.** Tools (`@tool`, `/.vfs/bin`, `run`): the tool design is not finished, so spec 7 states the rules a tool that interrupts must follow and builds none of them. Serving sessions and jobs over MCP. The action log (roadmap story H0), which spec 0 prepares the ground for and does not build. A private copy-on-write view of the files for a fork.

## Rulings these specs rest on

Each was made on 2026-11-21 or 2026-11-22.

1. VFS never asks a person and never waits for one. It stops, saves, and returns.
2. Nothing saved is a memory snapshot. A job is saved as serializable inputs and answers.
3. Policies and tools are `async` only.
4. A job has at most one interrupt waiting. It may be interrupted many times over its life.
5. Every interrupt names a schema for its answer. `Approval` and `Choice` are ready-made.
6. `resume` is the only public call that answers. There is no `answer`.
7. The system authority is never interrupted. Anything that would interrupt a system job fails the step.
8. A denial and a cancel have kinds of their own, `vfs.interrupt.denied` and `vfs.interrupt.cancelled`, and name the principal that answered by its `name`, never by its id.
9. An agent never sees text that invites it to resume. An interrupted result given to an agent reads as "not approved", and VFS warns the developer once.
10. A session is a stored, serializable record, not a context manager. It is asked for with an authority and an id, and the same call returns the same session whether or not it existed.
11. The id may be supplied by the caller or made by VFS.
12. A turn is started with `start_turn(id)`, and rewind and fork take `before=turn_id`.
13. A rewind restores what earlier turns saw: a file read in an earlier turn and again in a removed one is still read.
14. A rewind may also put back the files the session changed, as a separate feature wanted for 0.1.0.
15. The design is pre-release. No name or record of today's code is kept for compatibility.

## Shared decisions

### Where records live

The kernel's own records are kept by the storage of the root mount, which the kernel owns, in tables of their own. On SQLite they are in a database file beside the mount's file, never in it, because the log cost study found that kernel writes sharing the mount's file queue behind a batch for SQLite's one writer. A file system whose root storage is in memory keeps them in memory. Spec 0 owns all of this, and every other spec says "the kernel store" and names its tables.

### Records and their owners

| Table | Owner | Holds |
|---|---|---|
| `vfs_sessions` | 2 | One row per session: a surrogate key, the owner key, the id, the parent session and fork point, a counter for turn numbers, created and last-used times, the expiry |
| `vfs_session_turns` | 4 | One row per turn: the session, the turn id, its number, the shell state when it ended |
| `vfs_session_stamps` | 3 | One row per session, path and turn: the etag seen, or a mark that the session removed the path in that turn |
| `vfs_session_changes` | 5 | One row per entry a session changed in a turn: the etag before and after, and what was done |
| `vfs_jobs` | 7 | One row per stored job: its id, the caller, the session and turn if any, its state, its saved step or line, its interrupt, its expiry |
| `vfs_job_pages` | 7 | What of a stored job does not fit in its row: a large saved step, and a stored result |
| `vfs_job_replies` | 8 | The journal of a line's replies, in pages of at most 1 MiB |

A table's owner fixes its columns. Another spec that needs a column asks for it by naming the need in its own Builds on section.

### Times and counters

An order is a counter, never a clock. Turn numbers, session revisions and journal positions are integers the store hands out. A time is stored for display and for expiry only. Three studied projects had bugs from a timestamp used as an identity or a revision.

### Reads never write synchronously

A read verb adds no synchronous statement for any record on this page. What a read leaves behind (a stamp) goes through spec 0's write-behind writer. A change writes its records with the change. This is the bar the log cost study set and met for the action log, and spec 3 must show it holds for stamps by a counted test.

### The public names

```python
fs.session(authority=None, id=None, *, strict=True, policies=())   # a handle; no I/O
session.id      session.turn      session.parent      session.exists()
fs.sessions(authority=None, *, after=None, limit=None)
fs.remove_session(authority, id)

session.start_turn(id=None)     # returns the turn id
session.turns(*, after=None, limit=100)
session.rewind(*, before, files=False, preview=False)
session.fork(id=None, *, before=None)

session.resume(answer, *, job=None, authority)      session.jobs(state=None, *, after=None, limit=None)
fs.resume(job_id, answer, *, authority)             fs.jobs(state=None, authority=None, *, after=None, limit=None)

fs.add_policy(policy)      fs.remove_policy(policy)      fs.policies()

VirtualFileSystem(policies=[...], session_lifetime=..., job_lifetime=...)
```

The value types are `Etag`, `ABSENT`, `SessionInfo`, `SessionPage`, `Turn`, `Rewind`, `Policy`, `Decision`, `Step` and its 26 classes, `Mutation`, `Line`, `Job`, `Interrupt`, `StepPreview`, `JobPage`, `Approval`, `Choice` and `Cancel`. A storage names where the kernel's records live through `RecordPlace` and its own `record_place`. Removing a session is `fs.remove_session`, because `delete` on a handle is the file verb.

Every one exists on the asynchronous kernel and on the synchronous face, and the parity test covers them. What each returns follows the convention the management methods have today, which the owning spec reads from the code and states. `fs.session` is a noun used as a method, which `documentation/maintainers/how-we-name.md` forbids today with `session()` as its example; spec 2 carries the amendment to that page, with `use_session` as the choice if the amendment is refused.

### Ownership

The owner of a session or a job is the whole authority that made it: its subjects and its actor. The owner key is derived from `Authority.subject_names` and the actor's `sub`. A record asked for by another owner is answered exactly as a record that does not exist. An id is a name and never a credential. Spec 2 owns the derivation, and spec 7 uses the same one.

### Error kinds

- `vfs.conflict.unread` and `vfs.conflict.changed`: spec 3.
- `vfs.permission_denied.policy`: spec 6.
- `vfs.interrupted`, `vfs.interrupt.denied` and `vfs.interrupt.cancelled`: spec 7.
- A session, turn or job that does not exist, or belongs to another owner: `vfs.not_found`, with no new kind.

Each new kind takes a row in `KIND_CONTRACTS` with its phrase, its retry class and its hint for an agent, and the guides hold the words.

### Defaults

| Name | Value | Owner |
|---|---|---|
| The longest session id and turn id | 255 characters | 2, 4 |
| `session_lifetime` | 30 days since last use | 2 |
| `job_lifetime` | 24 hours | 7 |
| The bound on what one session remembers | set by spec 3, in bytes, never in entries | 3 |

### The constitution

Article 1 allows five first-class things, and requires everything first-class to have a path. A session, a turn and a job are not first-class. They are records the kernel keeps about calls, reached through management methods as grants and postures are, and they add no primitive. Each spec states this as a numbered decision. The etag composes two things the constitution already has, the entry's identity and its revision. A view of jobs or sessions in the namespace is left out of these nine.

## What every spec carries

The shape is the one `agents/2026-11-20-write-takes-preconditions-and-an-append/spec.md` has: the outcome wanted, terms, what the code does today (with `path:line`), the problem, decisions as `### N.` headings that are each a sentence and whose body ends in its reason, cost at the reference deployment's multipliers, what is left as it is, tests named by file and case and counted never timed, scope, what the docs must say, earlier decisions it reverses, what was not checked, and one line.

A spec decides every choice a developer would otherwise invent: each default, error kind, column, name and message. A choice that belongs to the owner of the project is decided too, and listed once more under a last heading, "Choices for the owner", with the decision the spec takes until it is ruled on.

A spec covers both engines and the in-memory storage, a 10,000-entry batch, the synchronous face, and the reference deployment's multipliers in `AGENTS.md`. It is written in an impersonal voice and names no person.
