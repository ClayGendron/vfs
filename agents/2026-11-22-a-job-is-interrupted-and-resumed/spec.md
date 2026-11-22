# A job is interrupted, saved, and resumed with an answer

This is a draft, written on 2026-11-22 against the branch `a-job-is-interrupted-and-resumed` at `6dae6a1d`. It is not reviewed and nothing in it is built. It is spec 7 of the nine that `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md` maps, and it owns the table `vfs_jobs`. It rests on the rulings of 2026-11-21 and 2026-11-22 that the overview lists, on the guide `documentation/how-to/interrupt-a-job-and-ask-a-person.md`, which is the public face of everything decided here, on the seven studies under `research/` beside this file, and on four of the session studies under `agents/2026-11-22-a-session-is-stored-named-and-forked/research/`. It replaces the draft of 2026-11-21, "A call is interrupted and the host asks". Every claim about today's code carries `path:line`, and the claims a decision rests on were run as probes on 2026-11-22; the probes are listed under "What the code does today".

## The outcome wanted

A host stops an agent's work at the steps that need a person. The stopped work is saved in the database the host already runs. Any process can list what is waiting, show a person what would change, and carry the work on with the person's answer. The step that is carried out is the step the person saw, done as the caller that asked for it, against the file the person saw, once.

A call that nothing interrupts costs nothing more than it costs today.

## Builds on

| Spec or story | State | What this spec needs from it |
|---|---|---|
| 0, the kernel keeps records of its own | being drafted on 2026-11-22, not seen | The kernel store, on both engines and in memory. A synchronous path whose statements are committed before the call returns, with several statements in one transaction. An update that reports how many rows it changed. An insert that does nothing when a unique index refuses it, and reports that. The creation of the two tables declared here. A sweep arm that takes a table, its expiry column and a dependent table keyed by the same id, and deletes in chunks. One clock function that every expiry reads and a test can replace. A hook that counts the statements of the kernel store, for the tests below. |
| 1, a row carries an etag | being drafted, not seen | `etag` on every row a `read` or a `stat` returns. `if_match` on `write`, `edit`, `delete` and `move`, as one etag for a call that names one path and as a mapping from path to etag for the batch forms (`write` with `entries`, `edit` and `delete` with `observations`). A mark in that mapping for "this path must hold nothing". One constructor for the refusal of a failed `if_match`, so the kernel can refuse a step with the words the storage would use. An etag that never names two versions of one entry. A statement of whether a directory's etag moves when its children change. |
| 6, a policy judges each step | being drafted, not seen | The `Step` value, with `verb`, `paths`, `authority` and `via`, which turns into JSON and back into an equal value, bytes bodies as base64. A canonical form of a step in which each body stands as its sha256, for the fingerprint of decision 26. One judging coroutine, called for the first run and for every resume, which runs every policy the step is shown to inside the asking context of decision 8 and reports one of: allow, a denial by a policy, a denial by an answer with its interrupt id, a stop with the first raiser's interrupt in policy order, or a refused answer. Policy names that are unique among the policies asked about one step, and, from the judging coroutine, the names of the session's policies that were shown the step. A module for `Step` that imports nothing from `vfs.results`, since the result envelope imports the job's values and they hold a step. A `Decision` that can carry an interrupt id, set only by `require_approval`. Failing closed for a policy that returns after its `interrupt` raised the stop. The exemption of the system authority, so that no policy runs for it. The caller's access judged before any policy is asked. |
| 2, a session is stored | being drafted, not seen | The owner key of an authority, as one function and one column type. The session's surrogate key and its type. The handle's id, key and policies. `delete` and the expiry of a session calling `cancel_session_jobs` (decision 35) before the session's rows are removed. |
| 3, the session remembers what it read | being drafted, not seen | Stamps written by session key and turn number with no handle in memory, so a job resumed by another process is remembered by its session. The `unread` refusal judged before any policy is asked. |
| 4, a session works in turns | being drafted, not seen | The turn id and turn number of a call made through a handle. `rewind` calling `cancel_session_jobs(session_key, from_turn=)` in the kernel-store transaction that removes the turns. A fork that copies no row of `vfs_jobs`. |
| 8, an interrupted line replays its replies | being drafted, not seen | Nothing. It builds on this spec: decision 37 is the frame it fills. |
| Write preconditions and the append | landed, `agents/2026-11-20-write-takes-preconditions-and-an-append/spec.md` | The rule that a write of the body a file holds is `unchanged`, which decision 23 leans on. |
| A cancelled call leaves its storage whole | landed, `documentation/maintainers/cancellation.md` | The rule that a cancelled write has changed nothing or landed whole, and the caller cannot tell which. |
| The synchronous face | landed, `src/vfs/sync.py` | One loop on one thread, and a twin for every public coroutine. |
| The shell | landed in the main, `src/vfs/shell/host.py` | `LineResult`, and a host that reads a refused verb at `result.failures[0]`. |
| Roadmap domain B, stories H1 to H5 | written, not built | Named under "Earlier decisions this reverses". |

## Terms

- **Step.** One verb about to run, with its checked arguments, as a typed and frozen value. Spec 6 owns it.
- **Policy.** An `async` function the host writes, which is shown each step before it runs. Spec 6 owns it.
- **Job.** One call through VFS. A direct verb is a job of one step. A shell line is a job of many.
- **Stored job.** A job that has a row in `vfs_jobs`. A job is stored only when it is interrupted.
- **Interrupt.** What a stopped job is waiting for: a message, a schema for the answer, and a preview. A job has at most one waiting.
- **Raiser.** The policy or tool whose `await interrupt(...)` stopped the job. Its name is `raised_by`.
- **Answer.** The value a person gives to one interrupt. It must fit the interrupt's schema.
- **Answering principal.** The authority passed to `resume`. It is who answered, never who made the call.
- **Caller.** The authority that made the call. A resumed step runs as the caller.
- **Owner key.** A string spec 2 derives from an authority's subjects and actor. Two calls have one owner when their keys are equal.
- **Kernel store.** Where the kernel keeps its own records, which spec 0 owns. On SQLite it is a database file beside the mount's file. In memory it is in memory.
- **Revision.** A counter on a job's row. Every change of state adds one to it. It is never a time.
- **Claim.** The one conditional update that moves a job from `interrupted` to `running`. Only one of two rivals changes a row with it.
- **Lease.** How long a claim holds. A job still `running` after its lease may be claimed again.
- **Preview.** A bounded description of what a step would change, computed once, when the job is stored.
- **Seen etag.** The etag an entry had when the preview was computed. The step is carried out only if the entry still has it.
- **Fingerprint.** A sha256 over the owner key, the session and the canonical form of a step. Two steps are the same when their fingerprints are equal.
- **Place.** Where a step stands inside its job. It is `"0"` for a job of one step. Spec 8 gives the place of a step inside a line.
- **Rung.** A level of the access ladder `none < list < read < add < contribute < read_write`.

## What the code does today

Read at `6dae6a1d`. The rows marked "run" were run on 2026-11-22 with Python 3.13.11, pydantic 2.12.5, SQLAlchemy 2.0.52 and SQLite 3.50.4, by `probe_spec7.py`, `probe_spec7b.py` and `probe_spec7c.py` under the session scratchpad's `specs/` directory. Statement counts leave out `BEGIN`, `COMMIT`, `PRAGMA`, `SAVEPOINT`, `RELEASE` and `ROLLBACK`, and are of an in-memory file system whose mount is open to everyone.

| Fact | How it is known |
|---|---|
| Nothing stops a call. The file system has no `resume`, no `jobs` and no `session`. A row carries no `etag`. | Run. Read, `src/vfs/base.py:251-331`. |
| Every public verb checks its arguments, finds the mount, asks the gate, and calls the storage through one method. The gate does not know who is calling: the storage judges the caller's rights when it is called. | Read, `src/vfs/base.py:20-34`, `2690-2755`, `2852-2979`. |
| A `Result` succeeds exactly when it holds no error of fatal severity. `success` is a property and is never stored. | Read, `src/vfs/results/envelope.py:387-390`. Run: a result with no error is a success. |
| A failed result is read at its first failure. The shell's host does so for every refused verb. | Read, `src/vfs/shell/host.py:495-505`. |
| An error prints as `SEVERITY locus: message — hint (retry: class)`. The hint and the retry class come from one fixed row of `KIND_CONTRACTS` for the kind. A message is the row's phrase, then `": "` and a detail. | Read, `src/vfs/results/render.py:93-125`, `src/vfs/results/envelope.py:239-285`. Run. |
| Every `ErrorKind` has a row in `KIND_CONTRACTS`, and a test builds one error of every kind with `classified` and requires its message to begin with the row's phrase. | Read, `tests/results/test_facts.py:36-52`. |
| There is no kind under `vfs.interrupt`. `vfs.cancelled` exists, with the phrase "Cancelled" and the retry class `transient`, for a line a cancel ended. | Run. Read, `src/vfs/results/kinds.py:99`, `294-299`. |
| A failed `edit` or `delete` prints its error lines alone. Only `write` prints a `write errors:` heading. A successful `edit` prints `Edited /contracts/acme.md`. | Run. Read, `src/vfs/results/render.py:62-66`, `580-588`. |
| `Principal` has `sub`, `kind` and `scopes`, and no `name`. `Authority.system()` takes no argument. | Run. Read, `src/vfs/authority.py:79-110`, `180-183`. |
| The ladder has no rung called `write`. `edit` needs `contribute`. `delete`, `move` and `restore` need `read_write`. Every rung that can change a row is above `read`. | Read, `src/vfs/ops.py:125`, `151-177`. |
| A storage answers whether a caller holds a rung at one path, through `holds`. It costs 3 statements. It reads the caller's rights once and the posture rows of the path and its ancestors in one chunked statement. | Run. Read, `src/vfs/storage/protocol.py:465-489`, `src/vfs/storage/backends/database/rights_reads.py:45-55`, `rights.py:956-996`. |
| As a named caller, a `read` of one file costs 3 statements, a `stat` 3, a `stat` of three paths in one call 3, and an `edit` 15. | Run. |
| A file's body is one unbounded value in one row. | Read, `src/vfs/models/rows.py:203-210`, `454-464`. |
| A unified diff of two texts exists, built on `difflib`. | Read, `src/vfs/models/versioning.py:48-66`. |
| The in-memory storage is the SQLite storage over a private `:memory:` database. | Read, `src/vfs/storage/backends/memory.py:1-23`. |
| A shell line never runs as the system actor. | Read, `src/vfs/shell/host.py:216-218`. |
| The sync face mirrors `ALL_OPS | MANAGEMENT_METHODS | FRONT_METHODS`, and two tests pin `FRONT_METHODS` to `{"cli"}`. | Read, `src/vfs/ops.py:110-120`, `tests/test_sync.py:231-232`, `688`, `tests/test_ops.py:290`. |
| A stop raised as a subclass of `BaseException` inside a coroutine passes an `except Exception` in that coroutine and reaches its awaiter. It does so awaited directly, as a task, under `asyncio.wait_for` and under `asyncio.timeout`. A second run with one recorded answer stops at the second question, and a third with two returns. | Run. |
| A pydantic model with a field named `schema` warns that the field shadows an attribute of `BaseModel`. | Run. |
| The JSON Schema pydantic makes for a model `Approval(approved, reason)` is not the one the guide prints. A before-validator makes the model accept `True` and `False`. `"yes"`, `1` and `None` are refused. | Run. |
| `TypeAdapter` checks and describes a model, a `TypedDict`, a dataclass, a `Literal`, `str`, `int` and `bool`. A checked value dumped as JSON and checked again is equal to itself. | Run. |
| A dataclass field declared with `compare=False` and `kw_only=True` stays out of equality and of the hash: two values that differ only in it are one member of a set. | Run. |
| On SQLite, an insert with `ON CONFLICT (owner_key, fingerprint) WHERE state IN (...) DO NOTHING` against a partial unique index inserts one row for the first of two equal steps and none for the second, and inserts again once the first row has left the indexed states. An update guarded by `state` and `revision` changes one row for the first of two rivals and none for the second. SQLAlchemy renders the same insert for Postgres. | Run on SQLite. Rendered, not run, for Postgres. |

## The problem

A host that wants a person to approve some of an agent's changes has nowhere to put the question. A verb runs or is refused. Nothing stops between the two, nothing is kept while a person thinks, and nothing can carry a step on once they have answered.

The studies show what goes wrong when this is built without care. Four findings shape every decision below.

- **An answer reached a question it was not for.** LangGraph matched answers to questions by their order, shared one id among a task's questions, and kept a fallback for old ids. Nearly every interrupt bug it fixed in two years had this shape (`research/langgraph.md`, section F). Restate's agents layer matched a wait by its input, and a later identical tool call received an earlier call's approval (`research/restate.md`, section F).
- **Two resumes both ran.** LangGraph has no claim on a paused thread. Two processes that resumed one pause both ran the side effect, and the thread forked in silence (`research/langgraph.md`, section D, executed).
- **A predicate changed its mind and the answer was skipped.** LangChain's `when` predicate runs again on resume. When it returns false then, the reviewer's answer is skipped and the tool runs, even where they rejected it (`research/approval-modes.md`, finding 3).
- **The answerer was not checked.** ADK reverted the fix that bound a confirmation to an authenticated answerer, so whoever sends the response can approve. Vercel's approvals travel in input the client controls and needed signing (`framework-session-stores.md`, section 6; `chat-protocols.md`, section 6).

## Decisions

### 1. A job and an interrupt are records the kernel keeps, and neither is a first-class thing

A job has no path. It is not an `Entry`, and `kind` gains no member for it. It is a record about a call, reached through two methods of the file system, `resume` and `jobs`, as a grant is reached through `grant` and `grants`. The five primitives of Article 1 are untouched: a job names entries by their paths and guards them by their etags, which compose the entry's identity and its revision. A view of jobs in the namespace is left out, as the overview rules.

Reason: Article 1 makes everything first-class addressable by a path, and a job that had a path would be a sixth primitive. Article 3 keeps a concern out of the namespace when a file shape for it would be dishonest, and a thing that is answered once and then gone is not a file.

### 2. A job that finishes inside its call stores nothing, and a job is stored only when its first interrupt is raised

A call that no policy stops makes no row, mints no id and issues no statement on the kernel store. This holds for every verb, at every batch size, for a caller with a session and without one. The asking context of decision 8 is entered only around a policy, so a call that reaches no policy does not enter it.

The count is zero and a test holds it: one `read`, one `edit` and one 10,000-entry `write`, each under a policy that allows, issue zero statements on the kernel store on account of this spec, and the mount's statements are the ones the same calls issue with no policy.

Reason: about 150,000 verb calls a day arrive at the reference deployment and a person can answer a few dozen. DBOS pays two transactions for every step because it records every step (`research/dbos.md`, section E). VFS records a job only at the moment it must outlive its call.

### 3. The job id is 32 hexadecimal characters from the operating system's random source, and VFS makes it

The id is `secrets.token_hex(16)`: 128 random bits. No caller supplies it. It is made when the job is stored, never before.

An id is a name and never a credential. Decision 17 judges every `resume` against the answering principal's rights, whoever knows the id.

Reason: MCP's Tasks and its state handles require ids that cannot be guessed and are minted by the server, and both protocols studied refuse to treat possession of an id as authority (`wire-protocol-sessions.md`, sections 1 and 6). Eight characters, as the guide prints, are 32 bits: two jobs would share an id after about 65,000 jobs.

### 4. `vfs_jobs` holds one row per stored job, and `vfs_job_pages` holds what does not fit in the row

`vfs_jobs`, in the kernel store:

| Column | Type | Holds |
|---|---|---|
| `job_id` | `String(32)`, primary key | The id of decision 3. |
| `owner_key` | spec 2's column type | The owner key of the caller. |
| `session_key` | spec 2's surrogate key type, nullable | The session the call came through. |
| `session_id` | `String(255)`, nullable | That session's id, for display. |
| `turn_number` | `Integer`, nullable | The number of the turn the call was made in. |
| `turn_id` | `String(255)`, nullable | That turn's id, for display. |
| `kind` | `String(8)` | `step` or `line`. |
| `state` | `String(16)` | One of the four states of decision 5. |
| `revision` | `Integer` | 1 when stored, plus one at every change of state. |
| `fingerprint` | `String(64)` | The fingerprint of decision 26. |
| `started_by` | `String(255)` | The `sub` of the caller's actor. |
| `verb` | `String(32)` | The verb of the step the job is stopped before. |
| `path` | the path column type, nullable | The first path that step names. |
| `paths_count` | `Integer` | How many paths that step names. |
| `paths` | `LargeBinary`, nullable | Every path the step names, as a JSON array, when it is at most `JOB_INLINE_BYTES`. |
| `saved` | `LargeBinary`, nullable | The saved part, when it is at most `JOB_INLINE_BYTES`. |
| `paths_pages`, `saved_pages` | `Integer` | How many pages each part has in `vfs_job_pages`. Zero when the part is in the row. |
| `session_policies` | `Text`, nullable | The names of the session's policies that judged the step, as a JSON array. |
| `interrupt` | `LargeBinary`, nullable | The waiting interrupt, as JSON: its id, question digest, message, schema, details, raiser and preview. |
| `answers` | `LargeBinary` | The recorded answers, as a JSON array, oldest first. |
| `result` | `LargeBinary`, nullable | The stored result of a finished job. |
| `ended_by` | `Text`, nullable | Who cancelled the job, as the record of decision 27. |
| `ended_reason` | `Text`, nullable | The reason given for a cancel. |
| `attempts` | `Integer` | How many times the job has been claimed. |
| `claim_expires_at` | time with zone, nullable | When the claim's lease ends. |
| `created_at`, `updated_at`, `expires_at` | time with zone | For display and for expiry only. |

`vfs_job_pages`, in the kernel store: `job_id String(32)`, `part String(8)` (`paths` or `saved`), `seq Integer`, `data LargeBinary`, with the primary key `(job_id, part, seq)`.

Indexes on `vfs_jobs`: a unique partial index on `(owner_key, fingerprint)` where `state` is `interrupted` or `running`; `(session_key, state)`; `(owner_key, job_id)`; `(state, job_id)`; and `(expires_at)` for the sweep.

**The saved part** is one JSON document: a format number `1`, the caller's authority in full (each subject and the actor with `sub`, `kind`, `name` and `scopes`, the provenance, the narrowing and the source identity), the step as spec 6 writes it, and the seen etags as a mapping from path to an etag or to the mark for "held nothing". For a line it is what spec 8 saves.

**A part is in the row or in pages.** A part of at most `JOB_INLINE_BYTES` (65,536) is stored in its column. A larger part leaves the column null and is cut into pages of `JOB_PAGE_BYTES` (1,048,576). Pages are inserted in statements of at most `JOB_STATEMENT_PAGES` (16) pages, and of fewer where the dialect's parameter budget is smaller, so no statement carries more than 16 MiB of pages. They are read back in the same chunks, in `seq` order.

Nothing in a job's row is a memory image, and nothing is pickled. Every stored value is JSON that is checked when it is read, and the format number is what a later change of shape is keyed on.

A step's bodies are held in memory once more while the saved part is built: once for text, and about one and a third times for bytes, which are base64. No cap is declared. The direction is an encoder that writes a page at a time.

Reason for the second table: a body is one unbounded value in one row today (`src/vfs/models/rows.py:454-464`), and a 10,000-entry write at the reference deployment's mean file size is 3 to 7 GB. One value of that size is past the single-value cap of both engines, so a saved step in one column would turn an engine's cap into a limit on what can be interrupted. Reason for the separate `paths` part: a listing must judge every path of a job (decision 31) and must never read its bodies. Reason for JSON: LangGraph's and DBOS's stores revive arbitrary types, and both projects say that write access to the store is code execution (`research/langgraph.md`, section B; `research/dbos.md`, section B).

### 5. A job is in one of four states, and every change of state is one conditional update on its revision

| State | Meaning |
|---|---|
| `interrupted` | It waits for the answer to one interrupt. |
| `running` | One resume has claimed it and is carrying it on. |
| `finished` | It ran to its end. Its result, a success or a refusal, is stored. |
| `cancelled` | A principal ended it while it waited. |

| From | To | Made by | Statement |
|---|---|---|---|
| none | `interrupted` | the call that is interrupted | an insert that does nothing when the partial unique index refuses it |
| `interrupted` | `interrupted` | a resume whose run stops at an interrupt again | an update where `job_id`, `state = 'interrupted'` and `revision = n` |
| `interrupted` | `running` | a resume whose run allows the step: the claim | the same guard |
| `interrupted` | `finished` | a resume whose run refuses the step | the same guard |
| `interrupted` | `cancelled` | a resume with `Cancel`, or `cancel_session_jobs` | the same guard, or one update over a session's waiting rows |
| `running` | `finished` | the claimer, after the step | an update where `state = 'running'` and `revision = n + 1` |
| `running` | `interrupted` | a claimer whose run stops at an interrupt: a line at its next one (spec 8), or a job claimed a second time whose policies now ask | the same guard |
| `running` | `running` | a resume after the lease has ended: a second claim | an update where `state = 'running'`, `revision = m` and `claim_expires_at <= now` |
| `running` | `cancelled` | a resume with `Cancel` after the lease has ended | the same guard |
| any | deleted | the sweep, once `expires_at` has passed | spec 0's |

Every update sets `revision = revision + 1`. An update that changes no row has lost to a rival, and its caller reads the row again and answers from what it finds.

A job that waits past `expires_at` has lapsed. Lapsed is not a stored state: it is `expires_at <= now`, judged when the job is asked for, so the answer does not depend on whether the sweep has run.

Reason: the revision is a counter, as the overview requires of every order. A conditional update is the one compare-and-set both engines and the in-memory store share. On Postgres at READ COMMITTED the second of two rivals waits for the first's row lock and then finds that its `WHERE` no longer matches. On SQLite the store has one writer. The probe showed one winner on SQLite.

### 6. The job is committed before the interrupted result is returned

When the judging coroutine reports a stop, the kernel makes the id, computes the preview, builds the row and its pages, and writes them through the kernel store's synchronous path in one transaction: one insert into `vfs_jobs`, and one insert per 16 pages. The call returns its interrupted result only after that transaction has committed. A store that cannot commit fails the call with `vfs.unavailable`, and the step has not run.

A caller cancelled before the commit has no job and is raised its cancellation. A caller cancelled after the commit has a job it never heard of. That job waits, shows in `jobs`, is joined by the same step made again (decision 26), and lapses if nobody answers. A process that dies between the commit and the return leaves the same.

A file system whose root storage is in memory keeps its jobs in spec 0's in-memory store. The statements are the same, and the jobs end with the program, as the guide says.

Reason: MCP's Tasks forbid returning a task id until the task is durably created, because the answer may come from another process a moment later. LangGraph's `exit` durability mode writes nothing until the run ends, and a crash loses the pause (`research/langgraph.md`, section D, executed).

### 7. The owner of a job is the authority that made the call, and a job made through a session records its session and its turn

`owner_key` is the key spec 2 derives from the caller's `Authority.subject_names` and its actor's `sub`. A caller working for two subjects and the same caller working for one are two owners. Every anonymous caller is one owner, since they are one authority.

A call made through a session's handle stores the session's key and id, and the number and id of the turn spec 4 assigns the call. A call made on the file system stores none of the four.

A job points at its session. A session does not contain its jobs, and no row of `vfs_sessions` names one.

Reason: the overview keeps the session's context, its stamps and its jobs apart. ADK keeps a paused run inside the session's event log, and OpenAI writes a dangling tool call into the session's history, and both have a run of bugs where the two met (`framework-session-stores.md`, section 6).

### 8. `interrupt(message, schema, *, details=None)` stops its policy by raising a `BaseException`, and returns the answer once the job has it

```python
async def interrupt(
    message: str,
    schema: type[T] | Choice,
    *,
    details: Mapping[str, Any] | None = None,
) -> T: ...
```

**The asking context.** Before the judging coroutine awaits a policy, it sets one context variable to the asking context of that policy for that step: the job id when there is one, the step's place, the policy's name, a counter that starts at zero, the answers the job has recorded, the answer `resume` was just given and the interrupt it was given for, and whether the job may be interrupted at all. It resets the variable when the policy returns or raises.

**What `interrupt` does**, in order:

1. It reads the context. With none set, it raises `RuntimeError`: `interrupt` was awaited outside a policy or a tool.
2. It checks its own arguments (decision 10). A wrong one raises `ValueError`, which fails the policy closed by spec 6's rule.
3. If the context says the job may not be interrupted, it raises the refusal of decision 30.
4. It takes the counter's value as `n` and adds one to the counter. With the job id, the place and the raiser's name, `n` gives the interrupt's id (decision 9).
5. If the job has a recorded answer for that id, and the question digest stored with the answer is the digest of this message and schema, it checks the stored value against the schema and returns the checked value.
6. If this id is the interrupt `resume` was given an answer for, and the digests match, it checks the answer. A value that does not fit raises `AnswerRefused` with pydantic's message. A value that fits is marked as used and returned.
7. Otherwise it raises `Interrupted`, carrying the id's parts, the message, the schema and the details.

`Interrupted` and `AnswerRefused` are subclasses of `BaseException`, private to the package. The judging coroutine catches them around the policy it is awaiting.

**The policy runs again from its first line on every resume.** Nothing of its frame is kept. The same `await interrupt(...)` that raised on the first run returns on the next, because the job now holds the answer. Code a policy places before `interrupt` runs on every run, so the docs say what the guide says: write a policy to reach the same point when it is asked twice about the same step, and make its message a function of the step.

**A policy that swallows the stop.** A policy can catch `BaseException` or use a bare `except`. The context records that a stop was raised. A policy that returns after that, with no answer, is a failed policy, and spec 6 refuses the step and names the policy.

The context is a context variable because a policy's signature is one argument, the step, and `interrupt` is a module-level function the guide awaits with no handle. A task a policy starts copies the context, so an `interrupt` awaited inside `asyncio.gather` reads the same counter.

Reason for `BaseException`: LangGraph's `GraphInterrupt` derives from `Exception`, so a body's `except Exception` swallows the stop, and its docs warn against wrapping `interrupt` in a try block (`research/tools-that-interrupt.md`, A2). DBOS raises a `BaseException` to unwind an arbitrary body for the same reason, as `asyncio.CancelledError` does (`research/dbos.md`, section C). The probe showed the stop passing an `except Exception` and reaching the awaiter four ways. Reason for running again: no system studied saves a Python frame, and ruling 2 forbids a memory image.

### 9. An interrupt's id is derived from the job, the place, the raiser and a count, and an answer is used only for the question it answered

```text
interrupt id    = first 32 hex characters of sha256("vfs.interrupt.1" NUL job_id NUL place NUL raised_by NUL n)
question digest = sha256(message NUL canonical JSON of the schema)
```

`n` is how many times this raiser has awaited `interrupt` for this step in this run, counted from zero. The id holds nothing of the question. A recorded answer is found by its id and by nothing else.

The digest is the check. Every recorded answer stores the digest of the question it answered, and the waiting interrupt stores its own. An answer is used only when the question asked at its id has the same digest.

What a later run can find, and what follows:

| The run reaches | What happens |
|---|---|
| the same id with the same question | The answer is returned. |
| the same id with another question | The recorded answer for that id is dropped, with every later answer of the same raiser for the same step. The job is interrupted with the question now asked. |
| an interrupt with no answer before it reaches the one that was answered | The run stops there. Decision 20 says what becomes of the answer `resume` was given. |
| no interrupt at the answered id, because the policy now decides without asking or is gone | Decision 20, last two rows. |

A message that is not a function of the step, such as one that holds the time, has a new digest on every run. Its job is asked about again on every resume and is never carried on. The docs say so.

Reason: an id from the place gives each `interrupt` its own answer, which is where LangGraph arrived after two years of answers reaching the wrong question, and how Restate's awakeable ids are built (`research/langgraph.md`, section F; `research/restate.md`, section B). The digest keeps an answer from a question that has since changed, without ever choosing an answer by what it looks like: the lookup is by id and the digest can only refuse.

### 10. A schema is `Approval`, a `Choice`, or any type pydantic can check and describe, and it is stored and shown as JSON Schema

`schema` is required. `interrupt` accepts three shapes.

- **`Approval`**, a frozen pydantic model with `approved: bool` and `reason: str | None = None`. It accepts `True`, `False`, an `Approval`, and a mapping with those fields. `interrupt` returns an `Approval`. Its JSON Schema is a constant, the one the guide prints: `{'title': 'Approval', 'anyOf': [{'type': 'boolean'}, {'type': 'object', 'properties': {'approved': {'type': 'boolean'}, 'reason': {'type': ['string', 'null']}}, 'required': ['approved']}]}`.
- **`Choice(options)`**, a value and not a type. `options` is 1 to `CHOICE_OPTIONS` (100) distinct strings of 1 to 255 characters. The answer must be one of them, and `interrupt` returns it as a `str`. Its JSON Schema is `{'title': 'Choice', 'type': 'string', 'enum': [...]}`.
- **Any other type**, checked with `TypeAdapter(schema).validate_python(answer)` and described with `TypeAdapter(schema).json_schema()`: a model, a dataclass, a `TypedDict`, a `Literal`, `str`, `int`, `bool`. The answer may be anything that validates as the type, such as a mapping with a model's fields.

The bounds, each checked when `interrupt` is awaited and each a `ValueError` there: `message` is a `str` of 1 to `MESSAGE_CHARS` (2,000) characters; the schema's JSON is at most `SCHEMA_BYTES` (65,536); `details` is a mapping that turns into JSON of at most `DETAILS_BYTES` (65,536); a type that pydantic cannot describe as JSON Schema is refused.

A recorded answer is stored as the checked value dumped as JSON, at most `ANSWER_BYTES` (65,536). A larger answer is refused as `invalid` at `resume`.

`Interrupt.schema` is the JSON Schema, a plain `dict`. It is the same dictionary for the caller, for a listing and for another process, since a class cannot cross a database.

Reason: ruling 5 requires a schema on every interrupt. LangGraph, AG-UI 1.0 and MCP all carry the answer's schema as JSON Schema so the application can build its form from the interrupt alone (`chat-protocols.md`, section 6). Pydantic's own schema for `Approval` is not the guide's (probe), so the two shipped schemas are constants and a test holds them equal to the guide.

### 11. `require_approval(message, *, details=None)` is `interrupt(message, Approval)` turned into a decision that remembers which answer it came from

It awaits `interrupt(message, Approval, details=details)`. For an approval it returns `Decision.allow()`. For a refusal it returns a denial that carries the reason and the interrupt's id.

The id is what lets the kernel report the step as `vfs.interrupt.denied`, naming the principal recorded as the answerer of that interrupt. A policy that awaits `interrupt` itself and returns `Decision.deny(...)` denies as a policy does, and its refusal names the policy.

Reason: the guide's denial names the person who answered, never the policy that asked. The kernel can know which person only if the decision says which answer it came from.

### 12. The interrupted result is a `Result` with one fatal entry of the kind `vfs.interrupted`, and it carries the job

`Result` gains one field and one property.

- `job: Job | None = None`. It is set on an interrupted result and is `None` on every other.
- `interrupted`, true exactly when `job` is set and its state is `interrupted`.

An interrupted result has `ops` equal to the verb, no observation, and exactly one error: kind `vfs.interrupted`, fatal, with `path` the first path the step names and `data["vfs.interrupt"]` the record its words are composed from (decision 15). So `result.success` is `False` and `result.interrupted` is `True`, as the guide shows, and no rule of the envelope changes: the verdict is still derived from a fatal entry.

One constructor builds it, and a validator on `Result` holds the two together: a result whose `job` is interrupted and that lacks the entry gains it. Enrichment and `model_copy` keep `job`. Set algebra, `merge` and `merge_branches` clear it, as they clear `next_after`, and keep the entry, so the merged result is a plain failure. `to_payload` carries `job` and `from_payload` restores it; a job that does not validate is dropped with a warning and the entry still fails the result.

The values, each a frozen dataclass in a leaf module that imports nothing from `vfs.results`:

| `Job` | Holds |
|---|---|
| `id` | The job id. |
| `state` | `interrupted`, `running`, `finished` or `cancelled`. |
| `kind` | `step` or `line`. |
| `started_by` | The `sub` of the caller's actor. |
| `verb`, `path`, `paths_count` | The step the job is stopped before. |
| `session`, `turn` | The session id and turn id, or `None`. |
| `interrupt` | The waiting `Interrupt`, or `None` when nothing waits. |
| `created_at`, `expires_at` | Times with zone, in UTC. |

| `Interrupt` | Holds |
|---|---|
| `id` | The derived id of decision 9. |
| `message` | The text to show the person. |
| `schema` | The JSON Schema the answer must fit. |
| `preview` | A `StepPreview`, or `None` when VFS cannot work one out. |
| `details` | What the raiser attached, or `None`. |
| `raised_by` | The name of the policy or tool. |
| `step` | The step the job stopped before. It is `None` on a listed job whose saved part is in pages. |
| `job_id` | The job it belongs to. |
| `expires_at` | When the job lapses if nobody answers. |

`Interrupt` is a dataclass and not a pydantic model, because a model's field named `schema` shadows an attribute of `BaseModel` (probe).

Reason for an error entry, and so for a third kind: `success` is derived from fatal entries and nothing else (`src/vfs/results/envelope.py:387-390`), and consumers read a failed result at `failures[0]` (`src/vfs/shell/host.py:499`). A result that failed with no entry would break both. The guide's own output, an `ERROR` line that ends `(retry: never)`, is the shape of an entry whose kind has a row in `KIND_CONTRACTS`. Reason for a kind outside `vfs.interrupt.`: the guide gives that prefix to the answers that decided against the work, and a job that waits has no answer yet.

### 13. The preview is computed once, as the caller, for seven verbs, and every part of it is bounded

The preview is built when the job is stored, by calls of the public read verbs made as the caller. It is never computed again and never as the answering principal.

| Verb | The calls made | What the preview holds | Seen etags |
|---|---|---|---|
| `edit` of one file | one `stat`; one `read` when the file is text of at most `PREVIEW_BODY_BYTES` | the changed lines of the file as the edit would leave it | the file |
| `write` of one file | the same | the changed lines, or `(new)` and the first lines for a path that holds nothing | the file, or the mark that it held nothing |
| `write` of a batch, `edit` or `delete` of a batch | one `stat` of every path, in one call | one line per entry, created or changed or removed | every path |
| `delete` of one entry | one `stat`; for a directory with `cascade`, one `tree` page of `PREVIEW_BENEATH` rows | the path, and for a directory how many entries lie beneath it, or "at least 1,000" | the entry named |
| `move` | one `stat` of the source | `source -> target` | the source |
| `copy`, `mkdir`, `restore` | none | the paths | none |
| any other step | none | `preview` is `None` | none |

The bounds are declared constants. A preview lists at most `PREVIEW_CHANGES` (20) entries and counts the rest in one line. A file's lines are at most `PREVIEW_DIFF_LINES` (40), each clipped at `PREVIEW_LINE_CHARS` (160) characters. A text body over `PREVIEW_BODY_BYTES` (65,536), and every bytes body, is described by its size before and after and is not read. The lines come from `compute_diff` (`src/vfs/models/versioning.py:48`), with its headers and unchanged lines left out, and a diff of bodies at or over `MEASURE_OFFLOAD_BYTES` runs on the offload pool. The stored preview is at most `PREVIEW_BYTES` (65,536) of JSON.

`str(preview)` is the text the guide prints: `edit would change: 1 file`, a blank line, then for each entry its path indented by two spaces and its lines beneath it. The first line names the verb and what it would do: `would change` for `write` and `edit`, `would remove` for `delete`, `would rename` for `move`, `would create` for `copy` and `mkdir`, `would bring back` for `restore`.

The class is `StepPreview`. `vfs.results.preview.Preview` is the excerpt of a ranked hit and keeps its name.

Two refusals are made while the preview is built, and neither stores a job.

- A read verb that fails for a reason of the store, such as `vfs.unavailable`, fails the call with that reason.
- A step that carries an `if_match` of its own, where the etag just seen is another one, is refused with spec 1's refusal of a failed `if_match`. The step could never land, so no person is asked about it.

A step the storage would refuse for a reason only it can judge, such as an `edit` whose text is not in the file or whose file is not there, is still stored and asked about, with `preview` set to `None`. It is refused when it is carried out.

For a directory, the seen etag is the directory's own. What lies beneath it is counted for the person and is not guarded.

Reason for computing it as the caller, once: the step runs as the caller, so the caller's view is the true one, and one stored preview is what every process shows. The earlier story had the approver compute a plan as the approver, which shows a change the approver could make and the caller perhaps could not. Reason for the bounds: a preview is read by a person, and the approval study found that people who are shown more than they can read stop reading (`research/approval-modes.md`, finding 6).

### 14. The preview shows only the entries the step names, so whoever may see the job may read what it shows

A preview holds lines of the files the step names and of no other file. A `copy` and a `move` show paths and no body.

Three kinds of caller can see a job (decisions 17 and 31): the system authority, the job's owner, and an authority that holds `read_write` on every path the step names. The preview was computed with the owner's rights, so the owner could read every line of it when it was made. `read_write` is above `read`, so an authority that may resume the job may read every file whose lines the preview shows, judged at the moment it asks.

The message, the details and a denial's reason are text the host's code or a person wrote, and are shown as they are.

Reason: the preview is a second road to a file's contents, and a road that asked for less than `read` would be a leak. The rule that lets a principal resume a job already asks for more.

### 15. An interrupted result turned into text reads "Not approved", and the first one in a process logs one `WARNING`

`str(result)` and `result.to_str()` of an interrupted result print one error line. For the guide's edit it is, word for word:

```text
ERROR /contracts/acme.md: Not approved — This edit needs approval before it can run ("A change to a contract needs a person."), and it has not been approved, so nothing was changed. Do not retry it or make the change another way. (retry: never)
```

The parts:

- The message is the kind's phrase, `Not approved`.
- The hint is composed from `data["vfs.interrupt"]`: `This {verb} needs {approval|an answer} before it can run ("{message}"), and it has not been approved, {so nothing was changed. Do not retry it or make the change another way.|so it was not run. Do not retry it or do it another way.}`
- `needs approval` is used when the interrupt's schema is `Approval`, and `needs an answer` for every other schema, whoever raised it.
- The first ending is used for a step that changes something, and the second for any other step.
- The retry class is `never`.

The text names no job, no id and no `resume`. For a `write`, the line stands under the `write errors:` heading the renderer already prints.

The first time in a process that an interrupted result is turned into text, one record is logged at `WARNING` on the logger `vfs.results.envelope`:

```text
an interrupted result was turned into text; handle it with result.interrupted and resume its job, since an agent that reads this text learns only that the step was not approved
```

A latch in the module makes it once for a process. `to_payload` and `to_json` log nothing, since they are for code.

Reason: ruling 9. An agent cannot resume a job, so text that named one would invite it to try. The line tells it the one thing it can act on.

### 16. `resume(job_id, answer, *, authority)` is the only public call that answers, and it returns the result the caller's call would have returned

```python
async def resume(self, job_id: str, answer: object, *, authority: Authority) -> Result: ...
```

It is a method of `AsyncVirtualFileSystem`, with a twin on `VirtualFileSystem`. It joins `FRONT_METHODS`, since it runs a verb on a caller's behalf and no storage answers it. It is not an op, so it is in no capability set, no shell line can name it, and no served tool is made from it.

`authority` is required and has no default. It is never the kernel's `default_authority`. A `None` there, or a `job_id` that is not 32 hexadecimal characters, is refused with `invalid`.

`resume` never raises for a refusal. It returns a `Result`: the result of the step when the step ran, an interrupted result when the job stops again, and a refusal otherwise. For a line it returns a `LineResult` (spec 8). There is no `answer` method. On a closed file system it answers the closed fact a verb answers. Its sync twin is served as a verb's twin is, and the twin of `jobs` as a management method's is.

What it does, in order:

1. It reads the job's row: one statement. No row, or a row past its `expires_at`, is `vfs.not_found`. The detail of a lapsed row says when it lapsed.
2. It judges who is asking (decision 17).
3. A `finished` or `cancelled` job returns its result again (decision 24). Nothing is written.
4. A `running` job whose lease has not ended is refused with `vfs.unavailable`, retryable, with `data` holding the job id and the state `running`, and the detail "the job is being resumed by another call". A retry after that call ends returns the stored result.
5. `Cancel` moves the job to `cancelled` (decision 29).
6. Otherwise it loads the saved part, runs the policies again (decision 20), and acts on what the run reports.

Reason: ruling 6. One call that records the answer and carries the job on leaves no state in which an answer is recorded and nobody has continued. Restate's awakeable is resolved by a call that learns nothing, and two resolutions queue (`research/restate.md`, section D); `resume` tells its caller what became of the job.

### 17. A job may be resumed by the system authority, and by an authority that holds `read_write` on every path the step names

The rule is judged on every `resume`, against the rights as they stand at that moment, before anything is read from the saved part and before any policy runs.

| Who asks | Answer |
|---|---|
| The system authority | It may resume, cancel and see every job. |
| An authority that holds `read_write` on every path the step names | It may resume the job and see it. |
| The job's owner, without that rung | It sees the job. A `resume` is refused with `vfs.permission_denied`, at the first path it lacks the rung on. |
| Anyone else | `vfs.not_found`, the answer a job that does not exist gets. |

A refusal records nothing and leaves the job as it was.

A step that names no path is judged at `/`. The paths are grouped by mount, and each mount's storage is asked once (decision 18). A storage that keeps no grants refuses nobody, as it refuses nobody a mount change (`src/vfs/mounts.py:355-375`).

The caller that started a job may resume it when it holds the rung. On a mount that gives everyone `read_write`, that is every caller. What keeps an agent from answering its own job is that `resume` is never offered to it.

The guide says "`write` access". The ladder has no rung of that name (`src/vfs/ops.py:125`). This spec reads it as `read_write`, the rung that deletes, moves and grants.

A job a tool interrupts will be resumable by an authority that may run the tool. That half of the rule is built with tools.

Reason: an answer must be bound to an authenticated principal that has a say over the files, or whoever holds the id can approve (`framework-session-stores.md`, section 6; `chat-protocols.md`, section 6). The right to grant access to a path is the right to decide about it. The answering principal's rights are judged and never used: the step runs as its caller.

### 18. A storage answers the rights question for many paths in one call

`SupportsHolds` gains one method.

```python
async def holds_all(self, *, paths: Sequence[Path], level: Rung, authority: Authority | None = None) -> Result: ...
```

A successful result means the caller holds `level` at every path. A failed result carries the refusal for the first path, in the caller's order, where it does not.

The database storage reads the caller's rights once, as `holds` does. It reads the posture rows of every path and of every ancestor of one in statements chunked by `membership_budget`, and judges each path in memory. `holds` becomes `holds_all` of one path.

Reason: a step can name 10,000 paths, and `holds` costs 3 statements a path (probe). The posture read already takes a list of keys and a budget (`src/vfs/storage/backends/database/rights.py:984`), so the batch form is the same statements over more keys.

### 19. An answer is checked by the policy's own `interrupt`, during the run that `resume` makes, and a wrong answer writes nothing

The schema's type lives in the policy's code. The job's row holds only its JSON Schema, and VFS carries no JSON Schema checker. So the answer is checked where the type is: `resume` hands the answer to the asking context, the run reaches the `interrupt` it was given for, and that `interrupt` checks it (decision 8, step 6).

An answer that does not fit ends the run. `resume` returns `vfs.invalid` with pydantic's message as the detail. Nothing has been written to the kernel store: the only statements issued were reads of the row and of its pages. The job is still `interrupted`, with the same interrupt and the same revision, and the person can answer again.

Reason: the guide promises that a wrong answer is refused, nothing is recorded and the job stays interrupted. Checking before any write is what makes that hold with no state to undo. LangGraph does the same: a failed validation saves nothing, so the question can be answered again (`research/langgraph.md`, section A).

### 20. A resume runs the policies again with the answers the job has, and the run ends in one of seven ways

The judging coroutine runs every policy the step is shown to, the file system's and then the session's, in the order they were added. Each runs inside an asking context that holds the job's recorded answers and the answer just given.

| The run reports | The job becomes | `resume` returns |
|---|---|---|
| The answer does not fit its schema | unchanged | `vfs.invalid` |
| A stop, after the answer was used | `interrupted`, with the answer recorded and the new interrupt waiting | an interrupted result for the same job |
| A stop, before the answer was used | `interrupted`, with the interrupt now reached waiting; the answer is not recorded | an interrupted result for the same job |
| A denial by an answer | `finished`, with the answer recorded | `vfs.interrupt.denied` (decision 27) |
| A denial by a policy | `finished`, with the answer recorded if it was used | spec 6's refusal, which names the policy |
| Allow, after the answer was used | `running`, with the answer recorded, by the claim; then `finished` | the result of the step |
| Allow, and the answer was never used | `finished`; the answer is not recorded | `vfs.conflict`: the question this job was waiting on is no longer asked, and nothing was carried out |

Each row but the first is one conditional update, guarded by the revision read in step 1. An answer that decision 9 drops is removed from `answers` by the same update.

**An answer is recorded only by the run that used it.** An answer the run never reached is checked by nothing, so it is never stored.

**An answer that is no longer asked for never lets the step through.** When a policy that asked now allows without asking, or is gone, the job ends and its step is not run. The caller makes the call again, and it is judged by the policies as they now are.

Reason for running the policies again: a rule can change overnight, and the guide promises that a policy that now denies still denies. Reason for the last row: LangChain's predicate that changes its mind on resume skips the reviewer's answer and runs the tool even where they rejected it (`research/approval-modes.md`, finding 3). Ending the job is the one outcome in which a person's "no" can never turn into a "yes".

### 21. Exactly one resume carries a job on, and the loser is refused with the job's state

The claim is the update of decision 5: `state = 'running'`, `revision = n + 1`, the answer appended to `answers`, `attempts = attempts + 1`, `claim_expires_at = now + JOB_CLAIM_SECONDS` and `expires_at = now + job_lifetime`, where `job_id` matches, `state = 'interrupted'` and `revision = n`. It is committed before the step is dispatched.

Two resumes at once both read revision `n`. Both run the policies, which change nothing. One update changes a row. The other changes none: its caller reads the row again and answers by decision 16, with `vfs.unavailable` while the winner runs, and with the stored result once it has finished.

No transaction of the kernel store is open while the step runs. The claim is one committed statement, the step runs in the mount's own transaction, and the finish is a second committed statement.

Reason: two processes that resumed one LangGraph pause both ran the side effect (`research/langgraph.md`, section D, executed). A conditional update on a counter is a claim both engines and the in-memory store give with one statement and no lock held past its commit.

### 22. The saved step is carried out as its caller, with rights judged again, and with the etags the preview saw as `if_match`

The winner rebuilds the step from the saved part, with the caller's authority as it was saved, and dispatches it through the kernel's own path for that verb. Four things follow.

- **It runs as the caller.** The storage judges the caller's rights when it is called, as for any call. A right the caller lost while the job waited refuses the step. The answering principal's authority is passed to nothing.
- **It is the step that was saved.** No argument is taken from `resume`. There is no way to edit a step before it is approved.
- **It changes the entry the person saw.** For `write`, `edit`, `delete` and `move`, the dispatch carries `if_match` with the seen etags, and the mark for "held nothing" where the preview found nothing. An entry that has changed is refused by spec 1's `if_match`, with `vfs.conflict`, and nothing is written. That refusal is the job's result, returned unchanged.
- **It runs in its session and turn**, when it has them (decision 34).

`copy`, `mkdir` and `restore` have no `if_match` and are carried out as saved. Their preview shows paths and no content, so there is nothing a person saw that could have changed, and a path that has since been taken is refused by the verb itself with `exists`.

Reason: these are the guide's four rules. Terraform refuses a saved plan whose state has moved, and GitHub dismisses an approval when new commits arrive (`research/approval-modes.md`, finding 4). The etag is the same binding for a file.

### 23. A claim is a lease of five minutes, and a job left running past it is carried on again under the same guard

`JOB_CLAIM_SECONDS` is 300. A resume that finds a `running` job whose lease has ended claims it again, with the update of decision 5, runs the policies with the recorded answers, and carries the step out. The answer it was passed is not used, since the job holds every answer it needs. A `Cancel` passed there cancels the job.

What a crash leaves, at each point:

| The process stops | The job is | The next resume |
|---|---|---|
| before the claim commits | `interrupted`, with nothing recorded | asks the policies again, with the answer it is given |
| after the claim commits, before the step's transaction commits | `running`; the step has not landed | after the lease, claims again; the step lands now |
| after the step commits, before the finish commits | `running`; the step has landed | after the lease, claims again; the step is refused by its guard, or a `write` of the same body is `unchanged` |
| after the finish commits | `finished` | returns the stored result |

A resume cancelled after its claim leaves the same as a crash at that point. The cancellation page says a cancelled write has changed nothing or landed whole and that the caller cannot tell which, so the job is left `running` and its lease frees it.

The second and third rows look the same from the job's row. The guard is what makes carrying on safe in both: a step that landed moved the etag, so a second run of it cannot change the entry again, and cannot write over what a rival wrote either.

**A refusal on a second claim is marked in doubt.** When `attempts` is more than one and the step is refused, the result gains one warning of the kind `vfs.conflict`, with `data` holding the job id and `in_doubt: true`, and the detail: an earlier resume of this job stopped before it recorded its result, so the step may already have been carried out; read the entry before making the change again. A step that succeeds on a second claim landed then, and carries no warning.

A step that runs longer than the lease can be claimed a second time while the first claim still runs. The guard keeps the second from changing what the first changed. The first claimer's finish then matches no row; it returns its own result to its caller and logs one `WARNING`. The stored result is the second's. No cap on a step's length is declared. The direction is a claimer that extends its lease while its step runs.

The lease is judged by the store's clock, which is the one clock a test replaces.

Reason: a claim with no lease leaves a job `running` for 24 hours after one crash. A claim that any resume may take at once is no claim. The four ledger systems studied either refuse a step whose start was recorded and whose end was not, and ask the host, or run it again (`research/tools-that-interrupt.md`, B1). A step guarded by an etag can be run again without harm, which a tool call cannot, so VFS runs it again and says when it cannot tell.

### 24. A finished or cancelled job answers `resume` with its result again until it lapses, and the stored result is bounded

A job that finishes stores its result as the JSON of `to_payload()`, and sets `expires_at` to the moment it finished plus `job_lifetime`. A `resume` of it, by a caller decision 17 lets through, returns that result and writes nothing. The answer passed is ignored and is not checked.

A cancelled job stores no result. Its result is composed from the row, from `path`, `ended_by` and `ended_reason`, and is the `vfs.interrupt.cancelled` refusal of decision 27.

The stored result is at most `JOB_RESULT_BYTES` (1,048,576). A larger one is stored without its observations: its `ops`, its errors as `to_payload` rolls them up, and one warning of the kind `vfs.budget_exhausted.truncated` that says the rows of this job's result are not kept and how many there were. The first `resume` returns the whole result, from memory. Only a second `resume` reads the stored one.

Reason: a request that brings an answer can arrive twice, and AG-UI asks that a resume be safe to replay (`chat-protocols.md`, lesson 7). What a replay needs is the verdict, and the verdict is kept at every size. The bound is on a copy kept for replays, and never on what a job may do.

### 25. A job waits on one interrupt at a time, in the order the policies were added

When several policies want a person about one step, the judging coroutine reports the first of them in policy order. That interrupt waits. Once it is answered, the run that `resume` makes reaches the next one, and `resume` returns an interrupted result for the same job with that interrupt waiting.

One policy that awaits `interrupt` twice is asked in the same way: its first question, then, on the run after it is answered, its second.

A step that any policy denies is refused at once, and no job is stored for it.

`Interrupt.expires_at` starts again at each stop: a job lapses `job_lifetime` after it last stopped.

Reason: ruling 4. LangGraph refuses one plain answer while several questions are pending, because their order is not fixed (`research/langgraph.md`, section F). One waiting interrupt means `resume` never has to say which question an answer is for.

### 26. The same step made again by the same caller while its job waits joins that job

```text
fingerprint = sha256("vfs.job.1" NUL owner_key NUL session_key or "" NUL canonical form of the step)
```

The canonical form is spec 6's, with every body standing as its sha256. "The same step by the same caller" means an equal fingerprint: the same owner, the same session or no session on both, and the same verb with the same checked arguments. A fingerprint is computed only for a step that a policy has stopped.

The insert of decision 6 does nothing when the partial unique index holds a row with that owner and fingerprint in the state `interrupted` or `running`. The call then reads that row and answers from it.

- A row that is `interrupted` is joined: the call returns that job's interrupted result, with its current interrupt and its stored preview. No second job is made. The preview just computed is thrown away.
- A row that is `running` refuses the call with `vfs.unavailable`, retryable, naming the job in `data`: the same step is being carried out.

A job that has finished, was cancelled or has lapsed is out of the index. The same step made after that is a new call and a new job, and nothing of the old job's answers reaches it.

Two equal calls at the same moment both try the insert, and the index lets one in.

Reason: a host built on LangGraph runs its node again from the top when its graph resumes, and the node makes the call again. Without the join each run would leave a second job waiting for the same answer. Restate's agents layer rejoins a wait by the identity of the tool call for the same reason (`research/restate.md`, section D). The join ends when the job ends because an answer is bound to one job: an approval of an edit must never approve the same edit made tomorrow.

### 27. A denial and a cancel are the kinds `vfs.interrupt.denied` and `vfs.interrupt.cancelled`, and their words name the principal that answered by its name

`ErrorKind` gains three members, each with a row in `KIND_CONTRACTS`.

| Member | Value | Phrase | Retry | Hint when the entry carries no record | `path` means |
|---|---|---|---|---|---|
| `interrupted` | `vfs.interrupted` | Not approved | `never` | This step needs approval before it can run, and it has not been approved, so nothing was changed. Do not retry it or make the change another way. | the first path the stopped step names |
| `interrupt_denied` | `vfs.interrupt.denied` | Denied | `never` | This step needed approval, and the principal that answered denied it. | the first path the denied step names |
| `interrupt_cancelled` | `vfs.interrupt.cancelled` | Cancelled | `never` | This job was waiting for an answer, and the principal that answered cancelled it. | the first path of the step the job was stopped before |

No member `vfs.interrupt` is added, since nothing would produce it. A consumer that wants every decision against the work matches the string prefix `vfs.interrupt.`, with its dot.

**The record.** Each of the three entries carries `data["vfs.interrupt"]`. For a denial and a cancel it holds the job id, the reason or `None`, and who answered: `names`, the names of the answering authority's subjects that have one, in `sub` order; `others`, how many subjects are not shown; `through`, the actor's name when the actor is not a subject and has a name; and `system`, true when the system authority answered, whose name, when it has one, is then the one entry of `names`. For a job that waits it holds the job id, the verb, the message, whether the schema is `Approval`, and whether the step changes something.

**The words.** Three constructors beside `classified` build the entries. The message is the phrase, then ` by `, then *who*, then ` (through {name})` when `through` is set. The hint is composed by the renderer from the record, by one function beside the table, and falls back to the table's hint when the record is missing.

| Who answered | *who* in the message | *who* in the hint |
|---|---|---|
| One named principal | `Ada Lovelace` | `Ada Lovelace` |
| A principal with no name | `a principal` | `the principal that answered` |
| A named principal, through a named actor | `Ada Lovelace (through Approval Desk)` | `Ada Lovelace` |
| A named principal, through an actor with no name | `Ada Lovelace` | `Ada Lovelace` |
| Two named subjects | `Ada Lovelace and Grace` | the same |
| One named subject and one more | `Ada Lovelace and 1 other` | the same |
| Two named subjects and three more | `Ada Lovelace, Grace and 3 others` | the same |
| The system authority | `the system` | `the system` |
| The system authority with a name | `Nightly cleanup` | `Nightly cleanup` |

At most `NAMED_PRINCIPALS` (2) names are shown. A principal's `sub` is in no message, no hint and no record.

The hints are `This step needed approval, and {who} denied it.` and `This job was waiting for an answer, and {who} cancelled it.`, each followed by ` Reason: {reason}` when a reason was given. The lines the guide prints follow, word for word:

```text
ERROR /contracts/acme.md: Denied by Ada Lovelace — This step needed approval, and Ada Lovelace denied it. Reason: This contract is still in force. (retry: never)
ERROR /contracts/acme.md: Denied by a principal — This step needed approval, and the principal that answered denied it. (retry: never)
ERROR /contracts/acme.md: Cancelled by Ada Lovelace — This job was waiting for an answer, and Ada Lovelace cancelled it. Reason: We are renegotiating this contract. (retry: never)
ERROR /contracts/acme.md: Cancelled by Nightly cleanup — This job was waiting for an answer, and Nightly cleanup cancelled it. (retry: never)
```

A reason is at most `REASON_CHARS` (2,000) characters, and a longer one is refused as `invalid` at `resume`. The renderer already folds an entry onto one line.

Reason: ruling 8. A denial is a decision made in answer to an interrupt and not a missing right, so it is not `vfs.permission_denied`, and an agent that reads it does not look for another way in. The table owns every word a `vfs.*` error carries and stays the one place a wrong word is fixed; a phrase that needs a name is composed from fields, since no consumer may read a fact out of a message.

### 28. `Principal` takes a `name`, and `Authority.system` takes one

`Principal` gains `name: str | None = None`, keyword only, and left out of equality and of the hash. `Authority.system(name: str | None = None)` gives the system principal that name.

A name is 1 to 255 characters, is not blank and holds no control character. Any other value is a `ValueError` when the principal is made. A name plays no part in what a principal may do, in the owner key, or in any stored row but a job's record of who answered.

Reason for keeping it out of equality: two principals with one `sub` are one principal, and a subject set that held both would act for the same person twice (probe). Reason for the field: a `sub` is an id from a token and tells an agent nothing, and the guide shows a person's name wherever it reports who answered.

### 29. `Cancel(reason=None)` answers any interrupt and ends the job, and nothing the job did is undone

`Cancel` is a frozen dataclass with one field. It is no schema, and `resume` accepts it whatever the interrupt's schema is. No policy runs.

It is one update: `state = 'cancelled'`, `ended_by` the record of the answering principal, `ended_reason` the reason, and `expires_at` the moment plus `job_lifetime`, where the state is `interrupted` and the revision is the one read. A `resume` that loses to it reads the row again.

`resume` returns the `vfs.interrupt.cancelled` refusal. A cancelled job is never resumed again: every later `resume` returns the same refusal (decision 24). What the job did before it stopped stands. For a job of one step that is nothing.

A denial refuses one step, and for a job of one step the job is then `finished` with the denial as its result. A cancel ends the job where it stopped. The two differ inside a line, which spec 8 specifies.

Reason: the guide's rule. A person needs a way to stop work that fits no schema, and a question from a tool has no "no" except this.

### 30. A job of the system authority is never interrupted, and a step that would interrupt it fails with the rule's words

No policy is applied to a step of the system authority, by spec 6, so the asking context is never entered for it and no job of its is stored. This spec adds the other half, for whatever raises an interrupt without being a policy.

An asking context made for a job whose caller is the system authority is marked as one that may not be interrupted. `interrupt` awaited in it raises a refusal, and the step fails with `vfs.invalid` and the detail: the system authority is never interrupted; make this call with the authority of the person or agent the work is for. The job ends there and nothing is stored.

Until tools are built nothing reaches that branch but its own test.

The system authority still answers: it may resume, cancel and list every job.

Reason: ruling 7. The system authority stands for the host's own code. A bulk load of 10,000 files that stopped to ask a person would be a pipeline that hangs at night.

### 31. `jobs(state=None, authority=None, *, after=None, limit=None)` lists the jobs a caller may see, a page at a time

```python
async def jobs(
    self,
    state: JobState | None = None,
    authority: Authority | None = None,
    *,
    after: str | None = None,
    limit: int | None = None,
) -> JobPage: ...
```

It is a management method: it joins `MANAGEMENT_METHODS`, returns a value and raises `ValueError` for a wrong argument, as `mounts()` returns a tuple. Article 2's one envelope governs the verbs, and the management methods already stand outside it (`src/vfs/base.py:36-39`); `jobs` stands with them, and `resume`, which carries a verb out, returns the envelope. `JobState` is the `Literal` of the four states, and `state` is one of them or `None` for all. A call that names no authority runs as the default authority or as the anonymous caller, as a verb does.

`JobPage` is a frozen value that holds `jobs`, a tuple of `Job`, and `next_after`. It is iterated, indexed and measured as its tuple, so `[job] = scout.jobs(state="interrupted")` works. `str(page)` is the table the guide prints, with the columns `id`, `state`, `started_by`, `verb`, `path`, `message` and `expires_at`, drawn by the helper the grant rows use (`src/vfs/results/render.py:245`).

**What each caller is shown.** The system authority is shown every job. Any other caller is shown the jobs it owns and the jobs it may resume by decision 17. A lapsed job is shown to nobody.

**Paging.** Jobs come in `job_id` order, which is no order of time. `limit` is 1 to `JOBS_PAGE_MAX` (1,000) and is `JOBS_PAGE_ROWS` (100) when not given. `after` is the `next_after` of the page before. A page is one statement that reads at most `limit` rows after the key. For a caller that is not the system and does not own a row, the page judges that row's paths, one `holds_all` for each mount over the paths of every such row together. A page stops reading rows once it has judged `JOBS_JUDGED_PATHS` (32,768) paths. So a page can hold fewer jobs than `limit`, or none, and still set `next_after`, as a page of `ls` can.

The statement reads every column but `result`, and `saved` only where it is in the row. A job whose paths are in pages has those pages read, and never its saved part. A listed job carries `interrupt.step` when its saved part is in the row, and `None` when it is in pages; its preview, `verb`, `path` and `paths_count` are there either way.

A listing for an approver costs in proportion to the rows it reads and not the rows it shows, since rights are not an index. No cap is declared. The direction is an index of jobs by the directories their paths lie in.

Reason: Article 2 requires every listing to take a limit and return a cursor. MCP removed `tasks/list` because it had no owner to scope a listing to (`wire-protocol-sessions.md`, section 6). VFS has one, the authority, and the rule that lets a principal resume a job is the rule that lets it see one, so an approval screen is one call.

### 32. On a session, `resume(answer, *, job=None, authority)` resumes the one waiting job, and `jobs(state=None, *, after=None, limit=None)` lists the session's jobs

Both are methods of the session handle, async and sync.

`session.jobs` lists the jobs whose `session_key` is the handle's, by the index on `(session_key, state)`, to the handle's own authority, which owns them. It pages as `fs.jobs` does.

`session.resume`:

- With `job` not given, it reads the session's jobs in the state `interrupted`, at most eleven. None is `vfs.not_found`, with the detail that no job is waiting in this session. One is resumed. More than one is refused with `vfs.invalid`, whose detail gives the count and names up to ten of them by id and tells the caller to pass `job=`.
- With `job` given, a job that is not of this session is `vfs.not_found`.
- `authority` is the answering principal, required as on the file system. It is never the handle's own authority by default.

It then does what `fs.resume` does, with the handle's policies in hand (decision 33).

Reason: a request that brings a person's answer holds the conversation's id and often nothing else. The refusal when several wait is LangGraph's: it will not guess which of several pending questions one answer is for.

### 33. A job its session's policies judged is resumed through a handle that carries policies of the same names

A session's policies are code, so they are not stored. When a step is judged by any policy of its session, the names of the session's policies are stored on the job, in `session_policies`.

- `fs.resume` of such a job is refused with `vfs.invalid`: this job was judged by its session's policies, and is resumed with `session.resume` on a handle that carries them.
- `session.resume` is refused with `vfs.invalid` when the names of the handle's policies are not the stored names, and the detail lists both.
- A job whose session has no policies, and a job with no session, is resumed from either.

Reason: the guide promises that a session can ask for more review and never for less. A resume that could not see the session's policies would carry a step out without asking them again, which is less.

### 34. A resumed job stays in its turn, and what it writes is remembered by its session

A job made through a session is carried out in that session and in the turn it was made in, whichever process resumes it and whether or not a handle exists there. The dispatch of decision 22 carries the stored `session_key` and `turn_number`, and spec 3 records the step's writes for that session and turn as the caller's own work.

A turn started after the job was stored does not move it. `turn_number` is written once.

The session's `unread` refusal was judged when the call was made, before any policy was asked. It is not judged again at the resume. The etag guard of decision 22 carries the protection from there.

A job being carried out at the moment its session is deleted finishes. What it would have had the session remember is dropped by spec 3, since the session is gone.

Reason: the sessions guide says a resumed job carries on as its caller, in the turn it started in, and that what it writes is the session's own work. A stamp kept by whichever handle happened to be in memory would be lost on every resume from another process (`wire-protocol-sessions.md`, lesson 9).

### 35. A session's delete, its expiry and a rewind cancel its waiting jobs through one call, and a fork takes none

```python
async def cancel_session_jobs(store, session_key, *, from_turn: int | None = None, reason: str) -> int: ...
```

It is private to the package, in the module that owns the job record. `store` is the kernel store, or a transaction of it that the caller has open, as spec 0 names the two. It is one update: every job of that session in the state `interrupted`, and with `turn_number >= from_turn` when a turn is given, becomes `cancelled`, with `revision = revision + 1`, `ended_by` the unnamed system, `ended_reason` the reason, and `expires_at` the moment plus `job_lifetime`. It returns how many rows it changed. It is one statement at any number of jobs, over the index on `(session_key, state)`, with no list of ids.

| Caller | When | `from_turn` | Reason passed |
|---|---|---|---|
| spec 2, `session.delete()` | before the session's rows are removed | none | the session was deleted |
| spec 2, the expiry of a session | before the session's rows are removed | none | the session expired |
| spec 4, `rewind(before=)` | in the transaction that removes the turns | the number of the first turn removed | the session was rewound to before the turn this job was made in |

A `resume` of a job cancelled this way returns "Cancelled by the system", with the reason.

A job that is `running` at that moment is not touched, and finishes. A resume that races the call meets the revision guard: one of the two changes the row.

**A fork takes no job.** `fork` copies no row of `vfs_jobs` and changes none. A job stays with the session that started it, in its turn. A fork that leaves a turn out of the new session has left that turn's jobs behind with it.

Reason: ACP cancels every pending permission request when a session closes, and copies no live work into a fork (`wire-protocol-sessions.md`, sections 4 and 6). LangGraph's whole-thread copy carries a waiting interrupt into the copy, where two threads can then answer one question (`langgraph-threads.md`, lesson 8). A question was put to a person once, and a fork must not put it twice.

### 36. A waiting job lapses `job_lifetime` after it stopped, 24 hours by default, and the sweep removes it

`job_lifetime` is an argument of `AsyncVirtualFileSystem` and `VirtualFileSystem`, a `timedelta`, `JOB_LIFETIME` (24 hours) when not given. A value that is not a `timedelta` greater than zero is a `ValueError` when the file system is made.

`expires_at` is set to the moment plus `job_lifetime` each time a job stops, when it is claimed, and when it finishes or is cancelled. So a waiting job lapses that long after it last stopped, and a finished or cancelled job is kept that long for replays.

A lapsed job cannot be resumed, joined or listed, from the moment `expires_at` passes. Nothing it was waiting to do is done. Its row and its pages are deleted by the kernel store's sweep, which this spec registers `vfs_jobs` with: the expiry column `expires_at`, and `vfs_job_pages` as the dependent table by `job_id`. The sweep's schedule and its chunks are spec 0's.

Nobody is told that a job lapsed. A host that will not wait resumes it with `Cancel`, and can do so as the system authority, which the caller then reads as "Cancelled by the system", or as "Cancelled by Nightly cleanup" with `Authority.system(name="Nightly cleanup")`.

Reason: LangGraph went two years with no way to remove old state, and its threat model lists retention as unbounded (`research/langgraph.md`, section D). MCP asks for a stated lifetime on every durable handle. A lapse is judged from the row when the job is asked for, so the sweep is collection and never a verdict.

### 37. A line's job uses the same record, states and claim, and spec 8 supplies what is saved and how it is carried on

A job has a `kind`. The kind `step` is this spec's. The kind `line` is spec 8's. What every kind shares is here, as functions private to the package:

| Function | Does |
|---|---|
| `store_job` | Decision 6: makes the id, writes the row and the pages, joins on the index. |
| `load_job` | Reads a row, and its pages when asked. |
| `stop_again` | The transitions into `interrupted`, with the answer and the new interrupt. |
| `claim` | Decision 21. |
| `finish` | The transition into `finished`, with the stored result of decision 24. |
| `cancel` | Decision 29. |

A kind is one object with three methods: it encodes what it saves, it decodes it, and it carries a claimed job on, given the asking context and the dispatch of decision 22. `resume` reads the row's `kind` and hands the job to it.

For a line, the fingerprint is over the line's own inputs, the place of a step is its position in the line, `verb` and `path` are those of the step the line is stopped before and change at each stop, and the row moves from `running` back to `interrupted` when the resumed line reaches its next interrupt. `vfs_job_replies` is spec 8's table and is registered with the sweep by spec 8.

Reason: the overview gives the line to spec 8 and the record to this spec. One claim and one set of states mean `resume`, `jobs`, the session's calls and the sweep need no second road for a line.

### 38. Tools are not built here, and a tool that interrupts will follow five rules

The tools spec can cite these by number.

1. **A tool that stopped is started again from its first line.** Nothing of its frame is kept. Each `interrupt` it reaches is found by its derived id (decision 9), and returns its answer.
2. **A tool asks before it changes a file.** Once a tool has written through its session, `interrupt` fails the tool with a message that names this rule. So a tool that starts again has no write of its own to repeat.
3. **What a tool does outside VFS comes after its last `interrupt`.** VFS cannot see it and cannot keep it from running again.
4. **An answer is for the files the tool had read.** If one has changed when the tool runs again, the answer is not used and the job is interrupted again.
5. **A tool run as the system authority cannot interrupt.** The step fails with the words of decision 30.

A tool's interrupt is resumed by an authority that may run the tool, and reads to an agent as "needs an answer" (decision 15).

Reason: the tool design is not finished, and the overview leaves it out of the nine. Every system studied re-enters a tool body and none promises that a body runs once (`research/tools-that-interrupt.md`, B1), so the rules that make re-entry safe are fixed before a tool is.

### 39. Four landings, in this order

1. **The words.** `Principal.name` and `Authority.system(name=)`. The three kinds, their rows, the three constructors and the composed hints. `Approval`, `Choice`, `Cancel`. `Job`, `Interrupt`, `StepPreview` and `JobPage`. `Result.job` and `Result.interrupted`, and the `WARNING`. Nothing produces an interrupted result yet.
2. **The record.** The two tables, the parts and pages, the transitions, the lease, the sweep registration, `cancel_session_jobs`, and `holds_all`. After spec 0.
3. **Interrupting and resuming a step.** The asking context, `interrupt`, `require_approval`, the preview, the stored job and the join, `resume` and `jobs` on both faces, and `job_lifetime`. After specs 1 and 6.
4. **Sessions.** The session and the turn on a job, `session.resume` and `session.jobs`, the rule of decision 33, and the three callers of `cancel_session_jobs`. After specs 2, 3 and 4.

Reason: each leaves the tree green and is tested alone. The first changes no behaviour. The second is exercised through its functions before any call can be interrupted. The fourth waits for the session specs without holding the third.

## Cost

Costed against the reference deployment in the working agreement.

**Per verb call, about 150,000 a day.** A call that is not interrupted issues no statement on the kernel store, makes no id, computes no fingerprint and builds no preview. What a policy costs to ask is spec 6's.

**Per file write, about 1,050,000 a day, and per batch, 100 a night.** Nothing, unless a policy stops the write. The nightly batch runs as whatever authority the host gives it. As the system authority it is never interrupted.

**Per index visit and per corpus.** Nothing. The sweep of lapsed jobs is one arm of spec 0's sweep.

**An interrupt.** For an `edit` of one small text file by a named caller:

| What | Statements |
|---|---|
| The preview: one `stat` and one `read`, as the caller | 6 on the mount, as the probe counted them |
| The stored job | 1 on the kernel store, in one committed transaction |
| A join, in its place | 2 on the kernel store: the insert that does nothing, and the read |

A 10,000-entry `write` that is interrupted: one `stat` of 10,000 paths, which the storage chunks; one insert of the row; and one insert for each 16 MiB of the two parts. At a median file of 4 KB the saved part is about 40 MB and the paths under 1 MB: four statements on the kernel store. Its bytes are written once more than a write that was not interrupted would write them, and are deleted by the sweep.

**A resume.** For the same `edit`, approved:

| What | Statements |
|---|---|
| The read of the row | 1 on the kernel store |
| Who may resume: one `holds_all` | 3 on the mount |
| The policies, asked again | none of this spec's |
| The claim | 1 on the kernel store, committed |
| The step, with `if_match` | the verb's own |
| The finish | 1 on the kernel store, committed |

So three statements on the kernel store. A resume that stops again, one that is denied and one that cancels are two. A wrong answer, a finished job and a refused principal are one. A resume of a paged job reads its pages in statements of 16 pages.

**How many.** No measurement gives the share of calls a host's policies will stop; it is an *assumption*. A person can answer a few dozen a day. As a ceiling, about one agent call in four changes something, 37,500 a day and about 5 a second at the peak. If every one were interrupted, the kernel store would take about 5 inserts a second at the peak, each one statement in one commit, and two updates for each job a person then answers. `vfs_jobs` would hold at most two days of rows, about 75,000: a day of waiting and a day kept for replays.

**Per lock.**

| Question | Answer |
|---|---|
| What is locked | One row of `vfs_jobs`, by one update. On SQLite, the kernel store's file for the length of that commit. |
| For how long | One commit. No transaction of the kernel store is open while a step, a policy or a person runs. |
| Who waits | Another writer of the kernel store: a job being stored, a flush of stamps. On Postgres, only a rival on the same job's row. |
| Who does not wait | Every read, list, glob, grep and search, and every writer of the mount. On SQLite the kernel store is a file of its own, so no call on the mount's file queues behind a job, and no job queues behind a batch. |

**Memory.** An interrupted step's saved part is built whole, beside the step. A listing page holds at most `limit` rows, each bounded by the constants of decisions 10 and 13.

## Left as it is

- **`plan=` on every changing verb** (roadmap H2). The preview here is built for an interrupt and bounded for a person. A verb that returns its own plan is a change of its own.
- **A view of jobs in the namespace**, `/.vfs/jobs`. The overview leaves it out.
- **Tools**, the kind `run`, and a tool's interrupt. Decision 38 fixes the rules and builds nothing.
- **Serving `resume` and `jobs` over MCP.** The job's fields map onto AG-UI's interrupt and MCP's Tasks, and the adapter is not built.
- **An answer remembered for later calls**, for a session or for good. Each product studied chooses its own meaning of "the same action", and a remembered approval is consent, not a right (`research/approval-modes.md`, finding 5). A host keeps it in its own policy.
- **Editing a step before approving it.** A denial's reason is how a person says "do it differently".
- **A step the storage would refuse for a reason only it can judge** is still asked about (decision 13).
- **What lies beneath a directory** is not guarded by the preview's etag (decision 13).
- **A source of `copy`** is not guarded (decision 22).
- **A heartbeat that extends a claim** (decision 23), **an encoder that writes a page at a time** (decision 4) and **an index of jobs by directory** (decision 31). Each is the named direction of a profile stated above.
- **A job raised by a kernel reached through a storage.** No such storage ships. Its job would be in the inner kernel's store and its paths would not be rebased.
- **Telling a caller that its job lapsed.** A lapse is silent (decision 36).

## Tests

Each is written and seen failing before the code. Counts are of statements on the kernel store, taken by spec 0's hook, and on the mount, taken by the `before_cursor_execute` listener `tests/storage/database/test_writes.py` uses; of rows; of calls to a spied policy; and of log records. Never of time: every expiry is reached by replacing the store's clock. A test under `tests/jobs/` that touches the store runs on SQLite and on the Postgres leg.

`tests/test_authority.py`:

- `test_a_name_is_kept_and_plays_no_part_in_equality`: two principals that differ only in `name` are equal and are one member of a set; a blank name, a 256-character name and a name with a newline each raise `ValueError`.
- `test_the_system_authority_takes_a_name`: `Authority.system(name=...)` is the system authority and its actor carries the name.

`tests/results/test_facts.py` and `tests/results/test_render.py`:

- The existing tests over every `ErrorKind` pass with three more members.
- `test_the_interrupt_words_are_the_guides`: each line of decisions 15 and 27 is compared with its string, character for character, for every row of the table of who answered, with a reason and without one. Counted: 9 forms of who, times 2 kinds.
- `test_an_entry_with_no_record_prints_the_tables_hint`.
- `test_no_interrupt_word_holds_a_sub`: a principal whose `sub` is a marker string answers; the marker is in no message, hint or record.

`tests/results/test_results.py` and `tests/results/test_result_laws.py`:

- `test_an_interrupted_result_fails_and_says_it_is_interrupted`: `success` is `False`, `interrupted` is `True`, and there is exactly 1 error.
- `test_a_job_without_its_entry_gains_it` and `test_set_algebra_clears_the_job_and_keeps_the_failure`.
- `test_an_interrupted_result_survives_the_payload`: `from_payload(to_payload())` is equal.
- `test_turning_an_interrupted_result_into_text_warns_once`: three calls of `str` log 1 record at `WARNING`; `to_payload` and `to_json` log 0.

`tests/jobs/test_asking.py`:

- `test_the_two_shipped_schemas_are_the_guides`: `Approval`'s and a `Choice`'s JSON Schema equal the dictionaries of decision 10.
- `test_approval_takes_a_bool_a_model_and_a_mapping`, and refuses `"yes"`, `1` and `None`.
- `test_interrupt_outside_a_policy_raises`.
- `test_a_stop_passes_except_exception`: a policy with `except Exception` around `interrupt` is stopped; the stop is caught 0 times.
- `test_a_policy_that_swallows_the_stop_is_refused`: the step is refused and names the policy; 0 jobs are stored.
- `test_each_interrupt_has_its_own_id`: a policy that asks twice gives two ids; the same job, place, raiser and count give the same id in a second process.
- `test_a_message_or_schema_over_its_bound_fails_the_policy`: one case per bound of decision 10.
- `test_interrupt_in_a_context_that_may_not_be_interrupted_names_the_rule`.

`tests/jobs/test_record.py`:

- `test_a_job_is_one_insert`: storing a job of one small step issues 1 statement in 1 transaction, counted.
- `test_a_part_over_the_inline_bound_is_paged`: a saved part of 40 MiB is 40 rows of `vfs_job_pages` written in 3 statements, and no statement carries more than 16 pages; it reads back equal.
- `test_every_transition_is_guarded_by_the_revision`: for each row of decision 5's table, the update with the right revision changes 1 row and the same update again changes 0.
- `test_two_claims_change_one_row`: 20 concurrent claims of one job: 1 changes a row, 19 change none.
- `test_a_lapsed_job_is_not_found_before_and_after_the_sweep`: with the clock moved past `expires_at`, `load_job` answers none with the row still there, and the same after the sweep deleted 1 job row and its page rows.
- `test_cancel_session_jobs_is_one_statement`: 1,000 waiting jobs of one session are cancelled by 1 statement; with `from_turn=3`, the jobs of turns 1 and 2 are left, counted; a `running` job is left.
- `test_nothing_stored_is_pickled`: every stored column of a job decodes as JSON.

`tests/storage/test_conformance.py`:

- A row of the storage contract for `holds_all`: it agrees with `holds` path by path over a tree with a grant, a deeper posture of `none` and a path that holds no row; 10,000 paths issue a number of statements that does not grow with the paths beyond the chunks of `membership_budget`, counted with the budget narrowed.

`tests/jobs/test_interrupt.py`:

- `test_a_call_no_policy_stops_stores_nothing`: a `read`, an `edit` and a 10,000-entry `write` under a policy that allows issue 0 statements on the kernel store, and the mount's count equals the count with no policy. The batch case is marked `slow`.
- `test_an_interrupted_edit_changes_nothing_and_is_stored_before_it_returns`: the file's version is unchanged; the mount saw 0 mutation statements; the kernel store saw 1 statement and its commit before the call returned, asserted on the hook's order.
- `test_a_store_that_cannot_commit_fails_the_call`: with the insert made to fail, the call is `vfs.unavailable` and 0 rows are stored.
- `test_the_preview_is_the_guides`: `str(preview)` of the guide's edit equals its text.
- `test_the_preview_is_bounded`: a 10,000-entry write lists 20 entries and counts 9,980; a file of 500 changed lines shows 40; a body over the bound and a bytes body show sizes and issue 0 `read` calls, spied.
- `test_the_preview_is_computed_as_the_caller`: every read verb the preview calls carries the caller's authority, spied.
- `test_a_step_whose_own_if_match_is_stale_is_refused_and_not_stored`: 0 jobs.
- `test_the_same_step_made_again_joins_its_job`: the second call returns the first job's id; 1 row; the join issues 2 statements. With another session, another owner or one changed argument, a second job is stored.
- `test_twenty_equal_calls_at_once_make_one_job`: 1 row and 20 results with one id.
- `test_the_same_step_after_its_job_finished_is_a_new_job`.
- `test_a_system_call_is_never_interrupted`: 0 policy calls, spied, and 0 jobs.
- `test_an_interrupted_ten_thousand_entry_write_is_saved_in_bounded_statements`: marked `slow`.

`tests/jobs/test_resume.py`:

- `test_an_approved_edit_lands_once_as_its_caller`: the version rises by 1; the storage was called with the caller's authority and never the answering principal's, spied; the kernel store saw 3 statements.
- `test_a_wrong_answer_writes_nothing`: `vfs.invalid`; 0 writing statements on the kernel store; the revision is unchanged; a second, right answer lands.
- `test_a_principal_without_read_write_is_refused`: an owner without the rung is `permission_denied`; a stranger is `not_found`; in both, 0 statements are written and the policy is asked 0 times.
- `test_the_system_resumes_any_job`.
- `test_two_resumes_at_once_carry_the_job_on_once`: 20 concurrent resumes: the version rises by 1; 1 result is the step's and 19 are `vfs.unavailable` or the stored result; the step was dispatched 1 time, spied.
- `test_a_finished_job_returns_its_result_and_writes_nothing`: 1 statement, the read.
- `test_a_stored_result_over_its_bound_keeps_the_verdict`: a result of 10,000 rows is stored without rows, with 1 warning.
- `test_the_file_changed_since_the_preview`: `vfs.conflict` from `if_match`; 0 mutation statements; the rival's body stands.
- `test_a_right_lost_while_the_job_waited_refuses_the_step`.
- `test_a_policy_that_now_denies_still_denies`, `test_a_second_policy_interrupts_after_the_first_is_answered` (the same job id, the second policy's message, policies asked in order, spied) and `test_one_policy_that_asks_twice_is_asked_one_question_at_a_time`.
- `test_an_answer_no_longer_asked_for_ends_the_job`: with the policy removed, a "no" and a "yes" both end in `vfs.conflict`, and the step is dispatched 0 times.
- `test_a_question_that_changed_is_asked_again`: the answer is not recorded; the job waits on the new question.
- `test_a_denial_names_the_principal_and_finishes_the_job`, `test_a_cancel_ends_the_job_whatever_the_schema` and `test_a_cancelled_job_is_never_resumed`.
- `test_a_crash_at_each_point`: with a fault raised at each of the four points of decision 23 and the clock moved past the lease, the next resume leaves the file changed exactly once, counted by its version; the third point's result carries 1 `in_doubt` warning, and for a `write` is `unchanged` with none.
- `test_a_running_job_inside_its_lease_refuses_a_second_resume`.
- `test_a_job_stopped_by_one_process_is_resumed_by_another`: a second file system over the same SQLite file, and through the sync face.
- `test_a_lapsed_job_is_not_resumed_and_its_step_is_not_run`.

`tests/jobs/test_listing.py`:

- `test_each_caller_is_shown_its_own_jobs_and_the_ones_it_may_resume`: the counts for the system, an owner, an approver and a stranger over one set of jobs.
- `test_a_page_is_one_statement_and_one_rights_question_a_mount`: counted; a page over jobs that name 40,000 paths stops after 32,768 and sets `next_after`.
- `test_a_listing_reads_no_saved_part`: with a paged job in the page, 0 rows of the `saved` part are read.
- `test_the_table_is_the_guides`: the columns of `str(page)`.
- `test_a_wrong_state_or_limit_raises`.

`tests/jobs/test_session_jobs.py`:

- `test_a_job_made_through_a_session_records_its_session_and_turn`.
- `test_session_resume_takes_the_one_waiting_job`, and with two waiting is `invalid` and names both; with `job=` of another session is `not_found`.
- `test_a_job_judged_by_session_policies_is_resumed_through_its_session`: `fs.resume` is `invalid`; a handle with other policy names is `invalid`; the right handle lands the step.
- `test_a_resumed_job_is_remembered_by_its_session_from_another_process`: after a resume by a file system that never held the handle, the session's next write to that file needs no read, and the stamp is under the job's turn.
- `test_delete_expiry_and_rewind_cancel_waiting_jobs`: each cancels in 1 statement, and the job then reads "Cancelled by the system"; a rewind leaves the jobs of earlier turns.
- `test_a_fork_takes_no_job`: 0 rows changed, and the new session lists 0 jobs.

`tests/test_sync.py` and `tests/test_ops.py`:

- The twin tests pass with `resume` in `FRONT_METHODS` and `jobs` in `MANAGEMENT_METHODS`, and the two pins of `FRONT_METHODS` read `{"cli", "resume"}`.

The docs gate runs every code block of the guide's steps 1 to 6, "Cancel a Job", "Interrupt With Any Answer", "Combine Policies", "Find Jobs That Are Waiting" and "Who May Resume", once the guide is amended as "Where this spec disagrees with the overview or the guides" lists.

## Scope

In: `src/vfs/authority.py` (the name); `src/vfs/results/kinds.py` (three kinds, their rows, the composed hints); `src/vfs/results/envelope.py` (three constructors, `job`, `interrupted`, the validator, the `WARNING`); `src/vfs/results/render.py` (the hint, and the table helper made public); a new package `src/vfs/jobs/` with `values.py` (`Job`, `Interrupt`, `StepPreview`, `Approval`, `Choice`, `Cancel`: a leaf that imports nothing from `vfs.results`, since the envelope imports it), `asking.py` (`interrupt`, `require_approval`, the context, the ids), `record.py` (the tables, the parts, the transitions, `cancel_session_jobs`), `preview.py`, `listing.py` (`JobPage` and `jobs`, which draws its table with the renderer's helper), and `running.py` (the stored job, the join, `resume`, the kinds); `src/vfs/base.py` and `src/vfs/sync.py` (`resume`, `jobs`, `job_lifetime`, as thin methods); `src/vfs/session.py` and `src/vfs/sync_session.py` (`resume`, `jobs`); `src/vfs/ops.py` (the two sets); `src/vfs/storage/protocol.py` and the database backend (`holds_all`); `src/vfs/__init__.py` (the exports `Approval`, `Cancel`, `Choice`, `Interrupt`, `Job`, `JobPage`, `StepPreview`, `interrupt`, `require_approval`); the tests above; the docs below. `base.py` and `sync.py` are on the size list in `tests/lint/allowlist.py`, and their entries rise with the methods added. The Rust crate is not touched.

Out: everything under "Left as it is"; the `Step` classes, `@policy`, `Decision` and the judging coroutine (spec 6); the kernel store and its sweep (spec 0); `etag` and `if_match` (spec 1); the session and the turn (specs 2 to 4); a line's job (spec 8).

The four landings of decision 39 are each green alone. The first needs nothing unbuilt.

## What the docs must say

- Every call is a job. A job that nothing interrupts is not stored and costs nothing.
- An interrupted result is for the host's code: check `result.interrupted`, show `result.job.interrupt` to a person, and call `resume`.
- `resume` records the answer and carries the job on as its caller, against the entry the person saw. One resume wins. A wrong answer changes nothing.
- A policy runs again from its first line on every resume, so its message is a function of the step.
- A denial refuses a step, a cancel ends a job, and both name who answered by name.
- A job is resumed by the system authority or by a principal with `read_write` on every path its step names.
- A waiting job lapses after `job_lifetime`, and lapses in silence.

Pages: the docstrings of `resume`, `jobs`, `interrupt`, `require_approval`, `Approval`, `Choice`, `Cancel`, `Job`, `Interrupt`, `StepPreview` and `JobPage`, which are the reference; a new `documentation/reference/python-api/jobs.md` that lists them, since an exported name on no page fails the docs gate; `authority.md` for `name`; `results.md` for `job` and `interrupted`; the `ErrorKind` docstring for the three kinds and their records; `virtual-file-system.md`, `async-virtual-file-system.md` and `sessions.md`, which take the new methods from their docstrings; `documentation/reference/access-levels.md`, one row for "resume another caller's job" under `read_write`; `documentation/reference/glossary.json`, two terms: **Job**, "One call through VFS. A job that is interrupted is stored, and is resumed later with an answer.", type `Job`; and **Interrupt**, "What a stopped job waits for: a message, a schema for the answer, and a preview.", type `Interrupt`. The guide is amended as "Where this spec disagrees with the overview or the guides" lists.

## Earlier decisions this reverses

Roadmap domain B, read at `context/standards/roadmap.md:239-390` and `1220-1276`.

| Story or decision | What this spec does |
|---|---|
| H1, the interrupt record | Settles it. The model of its criterion 4 is decisions 2 to 9. No kind `vfs.pending` is added (criterion 2): the kinds are decisions 12 and 27. The ledger is the kernel store and not the mount's schema (criterion 5). |
| H2, `plan=` | Leaves it. Decision 13 builds a preview for an interrupt alone. |
| H3, the hook, `pending` and `answer` | Amends it. The hook is spec 6. `answer` and the call made again with a ticket become `resume` (criteria 4 and 5). The approver's plan computed as the approver becomes one preview computed as the caller. The rung an approver needs stays `read_write`. A gate refusal that a principal could lift (criterion 3) is not made an interrupt. |
| H4, the durable run | Settles the record, the claim, whose authority a resume runs under, and the lifetime. Leaves the line to spec 8. Drops the `/.vfs/jobs` view (criterion 9) and `cancel(run_id)` (criterion 11), which is `resume` with `Cancel`. Replaces the in-doubt ask (criterion 7) with the lease and the guard of decision 23. |
| H5, every tool kind | Leaves it, with the rules of decision 38. |
| D9 | Settled as leaned: VFS carries the stop and never asks. |
| D10 | Amended. The kind is `vfs.interrupted`, with the retry class `never` and no new class `resume`. The record is in the kernel store. The lifetime is 24 hours. |
| D41, what a run records | Left to spec 8. |
| D42, how a tool resumes | Amended for host tools by rules 1 and 2 of decision 38: no record of a tool's earlier calls is kept. Guests are left. |
| D43, where the ledger lives | Settled: the kernel store. `RUN_LEDGER_BYTES` is not adopted; a saved part is paged and has no budget. |
| D44, `answer` and `resume` | Reversed by ruling 6: `resume` is the only call that answers. |
| D60, memory or a walk | Left to spec 8. Nothing this spec stores is a memory image (ruling 2). |
| D61, may a tool write before it asks | Settled as leaned: no (rule 2). |
| D62, who may answer | Settled: the system authority, and `read_write` on every path; the tool half waits for tools. |
| D63, D64, D65 | Left to the tools spec. |

In the code and its tests: `FRONT_METHODS` is pinned to `{"cli"}` at `tests/test_sync.py:688` and `tests/test_ops.py:290`, and gains `resume`. The envelope's docstring says a `vfs.*` error is built only by `classified` and its two conveniences (`src/vfs/results/envelope.py:99-101`); there are now five. `Principal` equality was over every field (`src/vfs/authority.py:79-89`); `name` is outside it.

The draft of 2026-11-21 is replaced. Its two kinds of interrupt become one with a schema. Its `answer`, and a single call that continues by being made again, become `resume`, and the call made again joins its job. Its in-doubt refusal becomes decision 23. Its saved memory of a stopped line is refused by ruling 2.

## Choices for the owner

Each is decided above, and the decision stands until it is ruled on.

1. **The rung that lets a principal resume.** Taken: `read_write` on every path the step names. The guide's word is `write`, which is no rung.
2. **May a caller answer its own job?** Taken: yes, when it holds the rung, since the guide states no exception. The other answer refuses an authority whose owner key is the job's.
3. **A third kind for a job that waits.** Taken: `vfs.interrupted`, outside the `vfs.interrupt.` prefix. The other answer is a result that fails with no error entry, which the envelope and the shell's host do not allow today.
4. **The length of a job id.** Taken: 32 hexadecimal characters. The guide prints 8.
5. **The lease.** Taken: 300 seconds, with no heartbeat. A longer step can be claimed twice, safely and with a result that may be marked in doubt.
6. **What a lapsed job answers.** Taken: `vfs.not_found`, with a detail while the row is still there. The other answer keeps a record of a lapsed job so that it can say "lapsed" for longer.
7. **A job judged by its session's policies is resumed only through its session.** Taken: yes. The other answer lets `fs.resume` carry it on without asking those policies again.
8. **An answer that is no longer asked for ends the job.** Taken: yes, with `vfs.conflict` and nothing carried out. The other answer carries the step out when the policies now allow it, which can turn a person's "no" into a "yes".
9. **A listing for an approver reads every waiting job.** Taken: yes, a page at a time, with no index by rights.
10. **The words for a question.** Taken: the guide's, read to the letter: only "needs approval" changes, so a question still reads "Not approved" and "it has not been approved". Better words would be "it has not been answered".
11. **The class name `StepPreview`.** Taken, because `Preview` is the excerpt of a ranked hit. The other answer renames that one.
12. **A lapse is silent.** Taken: yes. The other answer has the sweep cancel a lapsed job as the system, so its caller reads why.

## Where this spec disagrees with the overview or the guides

1. **The overview lists six tables. This spec adds a seventh, `vfs_job_pages`.** A saved step can hold 10,000 bodies, a body is one unbounded value today (`src/vfs/models/rows.py:454-464`), and the reference deployment's mean puts such a step at 3 to 7 GB, past either engine's cap on one value. The overview's table should gain the row, owned by spec 7.
2. **The overview and the guide name two new kinds. This spec adds a third, `vfs.interrupted`.** `success` is derived from fatal entries alone (`src/vfs/results/envelope.py:387-390`), the shell's host reads `failures[0]` (`src/vfs/shell/host.py:499`), and the guide's own output for an interrupted result is an error line with a retry class. The overview's list of kinds should gain it.
3. **The overview gives `fs.jobs(state=None, authority=None)` and `session.jobs(state=None)`. Both gain `after=None` and `limit=None`, keyword only.** Article 2 requires every listing to take a limit and return a cursor.
4. **The overview says a record asked for by another owner is answered as one that does not exist.** For a job that holds except for an authority that may resume it, which sees it (decision 17). The overview's sentence should name the exception.
5. **The guide says "`write` access to every path the step names".** The ladder has no rung `write` (`src/vfs/ops.py:125`). The guide should say "`read_write` access".
6. **The guide prints job ids of 8 characters**, `5d0c81aa` and `91aa3c57`. It should print 32, or say that its ids are shortened.
7. **The guide prints `edit success: 1 file` and `edited /contracts/acme.md` for the resumed edit.** An edit prints `Edited /contracts/acme.md` today (`src/vfs/results/render.py:580-588`, run), as the sessions guide shows. This spec changes no verb's own text. The guide should print `Edited /contracts/acme.md`.
8. **The guide's LangGraph section says that if the node runs again after the job has finished, "resuming a finished job returns its result and records nothing, so the node is safe to run again".** The node's first line makes the edit again. With its job finished, that is a new call and a new job (decision 26), and the node resumes the new job, never the finished one. The edit is then refused because its text is no longer in the file, and an append would land twice. The guide should say: "If the node runs again after the job has finished, its call is a new call and a new job. Make the node's step one that is safe to make twice, or keep the job's outcome in your graph's state before the node returns."
9. **The guide says `fs.jobs`, called with a person's authority, lists only the jobs that person may resume.** It also lists the jobs that caller started. The guide should say "the jobs that person started or may resume".
10. **The guide says resuming a finished job returns its result again.** A result over 1 MiB is returned again without its rows (decision 24). The guide should add that a very large result comes back as its verdict and its errors.
11. **The guide shows no way to attach `details`.** This spec gives `interrupt` and `require_approval` a keyword `details`. The guide's table of an interrupt's attributes should say so.

## Not checked

- Specs 0, 1, 2, 3, 4, 6 and 8 were being written on the same day and were not seen. Every shape this spec takes from them is stated as a need under "Builds on", and none was read.
- Nothing was built. No transition, claim or join was run on Postgres. That a rival's update under READ COMMITTED waits and then matches no row is read from the engine's documented behaviour. The insert that joins was rendered for Postgres and run only on SQLite.
- `holds_all` was not built. Its statement count is read from `held`, `grant_refusal` and `posture_rows`, and the count of the rights read it shares with `holds` was measured only as part of the 3 statements of one `holds`.
- The stop raised as a `BaseException` was run on Python 3.13 alone. The 3.11 and 3.12 forms of `asyncio.wait_for` were not run.
- The time a diff of two 64 KiB bodies takes, and the time to build and write a saved part of several gigabytes, were not measured.
- The share of calls a host's policies stop at the reference deployment has no source.
- Whether a directory's etag moves when its children change is spec 1's, and decides only how much decision 13's guard on a directory catches.
- Whether a checked value of every type pydantic accepts dumps to JSON that checks back to an equal value was run for one model. A type whose JSON form does not check back would have its answer dropped and asked for again by decision 9, which is safe and was not run.
- The clocks of two processes are assumed to agree to well within the 300 seconds of a lease.

## One line

A call that needs a person is stored as its step and its answers, never its memory; one resume, by a principal with a say over the files, carries the saved step out once, as its caller, against the entry the person saw.
