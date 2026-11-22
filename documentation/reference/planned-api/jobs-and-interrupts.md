# Jobs and Interrupts

A [job](../glossary.md#job) is one call through VFS. A job that needs a person is stopped before the [step](../glossary.md#step) that needs them, saved, and resumed later with the person's answer. What it waits for is its [interrupt](../glossary.md#interrupt). This page lists every name, argument, value and refusal of that design. [Interrupt a Job and Ask a Person](../../how-to/interrupt-a-job-and-ask-a-person.md) shows it in use.

> **This page describes an API that is designed and not yet built.** It is written so the API can be agreed before the code is written. The names on this page may still change.

Every name is imported from `vfs`.

## Raise an Interrupt

A [policy](../glossary.md#policy) raises an interrupt by awaiting one of two functions. Both are `async` and have no synchronous form.

```python
async def interrupt(message, schema, *, details=None)
async def require_approval(message, *, details=None) -> Decision
```

| Argument | Type | Meaning |
|---|---|---|
| `message` | `str`, 1 to 2,000 characters | The text to show the person |
| `schema` | `Approval`, a `Choice(...)`, or any type pydantic can check | The shape the answer must have |
| `details` | A mapping of at most 65,536 bytes as JSON, or `None` | Anything else to attach |

The first time a policy reaches `interrupt`, the policy stops and the job is interrupted. When the job is resumed, the policy runs again from its first line, and the same `await` returns the answer, already checked against the schema. So a policy must reach the same interrupt when it is asked twice about the same step.

`require_approval(message)` is `interrupt(message, Approval)` turned into a decision. It returns `Decision.allow()` for a yes, and a denial carrying the person's reason for a no.

**The message should depend only on the step.** A message that holds the time, or anything else that differs between two runs, is taken for a new question on every resume, and its job never carries on.

## Answer Schemas

| Name | What it is | What an answer may be |
|---|---|---|
| `Approval` | A yes or a no, with an optional reason | `True`, `False`, or `Approval(approved=..., reason=...)` |
| `Choice(options)` | One of 1 to 100 strings | One of the options, as a `str` |
| Any pydantic-checkable type | A model, a `TypedDict`, a dataclass and so on | A value that fits it |
| `Cancel(reason=None)` | Not a schema. It answers any interrupt and ends the whole job | |

A schema is stored and shown to your application as JSON Schema, so a form can be built from it.

## The Interrupted Result

A call that is interrupted returns at once. Its result carries the job.

| Name | Type | Meaning |
|---|---|---|
| `result.interrupted` | `bool` | True when the job is waiting for an answer |
| `result.job` | `Job` or `None` | The job. Also set on every result `resume` returns. |
| `result.success` | `bool` | False for an interrupted result |

An interrupted result holds one error, of the kind `vfs.interrupted`. Nothing was changed by the step.

### Job

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | 32 hexadecimal characters, made by VFS |
| `state` | `str` | `interrupted`, `running`, `finished` or `cancelled` |
| `kind` | `str` | `step` for one verb, `line` for a shell line, `rewind` for a rewind that puts files back |
| `started_by` | `str` | The caller that made the call |
| `verb`, `path`, `paths_count` | | The step the job is stopped before |
| `turn` | `str` or `None` | The [turn](../glossary.md#turn) the call was made in, when it came through a session |
| `interrupt` | `Interrupt` or `None` | What the job is waiting for |
| `created_at`, `expires_at` | `datetime` | When it was stored, and when it lapses |

### Interrupt

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | The interrupt's own id |
| `message` | `str` | The text to show the person |
| `schema` | `dict` | The JSON Schema the answer must fit |
| `preview` | `StepPreview` or `None` | What the step would change |
| `details` | Mapping or `None` | What the policy attached with `details=` |
| `raised_by` | `str` | The name of the policy that raised it |
| `step` | `Step` or `None` | The step the job stopped before |
| `job_id` | `str` | The job it belongs to |
| `expires_at` | `datetime` | When the job lapses if nobody answers |

### StepPreview

`str(preview)` is text to show a person.

```text
edit would change: 1 file

  /contracts/acme.md
  -Payment is due in 30 days.
  +Payment is due in 90 days.
```

A preview exists for `write`, `edit`, `delete`, `move`, `copy`, `mkdir`, `restore` and a rewind that puts files back. For any other verb it is `None`. It lists at most 20 entries and counts the rest, and shows at most 40 lines of one file. It is worked out once, as the caller, when the job is stored. It shows only the entries the step names, so whoever may see the job may read what it shows.

## Resume a Job

```python
fs.resume(job_id, answer, *, authority) -> Result
session.resume(answer, *, job=None, authority) -> Result
```

| Argument | Meaning |
|---|---|
| `job_id` | The job, from `result.job.id` or from `jobs` |
| `answer` | A value that fits the interrupt's schema, or a `Cancel` |
| `authority` | The principal that answered. It is required, and it is never taken from a default. |
| `job` | On a session, which job to resume. Needed only when the session has more than one waiting. |

`resume` is the only call that answers. It returns the result the first call would have returned: the step's result when the step ran, another interrupted result when the job stops again, and a refusal otherwise.

- **The step runs as the caller that made the call,** never as the principal that answered. The caller's rights are checked again when it runs.
- **The file must still be as the preview showed it,** for `write`, `edit`, `delete` and `move`. If it changed, nothing is written and the result is a conflict.
- **The policies are asked again** on every resume, with the answers given so far.
- **Of two resumes at once, one carries the job on.** The other is refused and may try again.
- **A finished or cancelled job returns its result again** and records nothing.
- **A wrong answer changes nothing.** The job stays interrupted, and the person can answer again.

### Who May Resume

The system authority may resume any job. Any other authority must hold `read_write` on every path the step names. A caller may answer its own job when it holds that level. **So the rule that an agent cannot approve its own work rests on your application: never offer `resume` to an agent as a tool.** It is not a shell command, and a session handed to a tool does not carry it.

A job that a session's own policies judged is resumed with `session.resume`, on a handle given the same policies.

## List Jobs

```python
fs.jobs(state=None, authority=None, *, after=None, limit=None) -> JobPage
session.jobs(state=None, *, after=None, limit=None) -> JobPage
```

The system authority is shown every job. Any other caller is shown the jobs it started and the jobs it may resume. `session.jobs` lists the jobs made through that session. A page holds at most `limit` jobs, 100 by default and 1,000 at most, and `page.next_after` is passed as `after` to read the next one.

## Denial and Cancel

| Kind | When | What an agent reads |
|---|---|---|
| `vfs.interrupt.denied` | The principal said no to an approval | `Denied by Ada Lovelace — This step needed approval, and Ada Lovelace denied it. Reason: …` |
| `vfs.interrupt.cancelled` | A principal resumed with `Cancel`, or the job's session was removed, expired, or rewound past its turn | `Cancelled by Ada Lovelace — This job was waiting for an answer, and Ada Lovelace cancelled it. Reason: …` |

A denial refuses one step. A cancel ends the whole job and undoes nothing the job already did. Match the prefix `vfs.interrupt.`, with its dot, to tell a person's decision from a refusal by an access rule or a policy.

The words name the principal by its `name`, and never by its id.

| Who answered | Shown as |
|---|---|
| A principal with a name | `Ada Lovelace` |
| A principal with no name | `a principal` |
| A named principal acting through a named actor | `Ada Lovelace (through Approval Desk)` |
| The system authority | `the system`, or its name |

`Principal(sub, ..., name=None)` and `Authority.system(name=None)` take the name. A name is a label only. It plays no part in what a principal may do.

## What an Agent Reads

An interrupted result is for your application's code. If it is turned into text for an agent, the agent reads only that the step was not done.

```text
ERROR /contracts/acme.md: Not approved — This edit needs approval before it can run ("A change to a contract needs a person."), and it has not been approved, so nothing was changed. Do not retry it or make the change another way. (retry: never)
```

For a step made by a shell line, the text says that this command was not run and that the commands before it in the line ran. The text never names a job or `resume`. The first time in a process that an interrupted result is turned into text, VFS logs one `WARNING` for the developer.

## Other Refusals

| Kind | When |
|---|---|
| `vfs.invalid` | The answer does not fit the schema; `resume` is called with no authority; several jobs wait in a session and no `job=` is given; something would interrupt a job of the system authority |
| `vfs.not_found` | No job has that id, the job has lapsed, or the caller may not see it |
| `vfs.permission_denied` | The caller lacks `read_write` on a path the step names |
| `vfs.unavailable` | Another `resume` is carrying the job on. Try again. |
| `vfs.conflict` | The file changed after the preview, or the policy no longer asks the question the job was waiting on |

## Limits

| What | Value |
|---|---|
| `job_lifetime`, how long a job waits and how long a finished job is kept | 24 hours. Set with `VirtualFileSystem(job_lifetime=...)`. |
| A message, and a reason | 2,000 characters |
| A schema, `details`, and an answer, as JSON | 65,536 bytes each |
| The stored result of a finished job | 1 MiB. A larger one comes back without its rows. |
| How long one `resume` holds a job before another may carry it on | 300 seconds |

- **A call that nothing interrupts stores nothing** and costs nothing more.
- **The system authority is never interrupted.** A step of its own that would be interrupted fails instead.
- **A lapse is silent.** A lapsed job cannot be resumed or listed, and what it was waiting to do is not done.
- **A file system whose root storage is in memory keeps its jobs in memory,** and they end with the program.
- **The same step made again by the same caller while its job waits returns that job.**

## Choices Still Open

Each of these is decided in the spec for now, and is the project owner's to confirm.

| Choice | Decided for now |
|---|---|
| The level that lets a principal resume | `read_write` on every path the step names |
| May a caller answer its own job | Yes, when it holds that level |
| A parent kind for `vfs.interrupt.denied` and `vfs.interrupt.cancelled` | None. They are matched by prefix. |
| What a lapsed job answers | `vfs.not_found`, with no notice to anyone |
| An answer to a question the policy no longer asks | The job ends with a conflict, and its step is not run |
| The words for a question that is not an approval | The same "Not approved" words |

The full design is in `agents/2026-11-22-a-job-is-interrupted-and-resumed/spec.md`, and a shell line's replay is in `agents/2026-11-22-an-interrupted-line-replays-its-replies/spec.md`.
