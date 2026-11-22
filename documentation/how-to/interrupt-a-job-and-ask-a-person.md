# Interrupt a Job and Ask a Person

This guide shows how to stop an agent's work at the points that need a person, show the person what would happen, and carry the work on from where it stopped once they answer. Use it when an AI agent works on files that matter, when some of its changes should wait for approval, or when a tool needs an answer that only a person can give.

> **This guide describes an API that is designed and not yet built.** It is written first so that the API can be agreed before the code is written. The names on this page may still change.

**VFS never asks a person anything, and it never waits for one.** Every call you make through VFS is a *job*, and every verb the job carries out is a *step*. A direct call such as `edit` is a job of one step; a shell line is a job of many. Most jobs finish inside the call that started them, and VFS keeps nothing for them. When a step needs a person, VFS stops the job before that step, saves the job in the database, and returns at once. What the person must answer is the job's *interrupt*. Your application asks the person in whatever way it likes, then resumes the job with the answer, and the job carries on from the step where it stopped.

A job has at most one interrupt waiting at a time. It may be interrupted several times over its life, once for each step that needs a person, and each time it waits for one answer.

Two things can interrupt a job: a *policy* you write, which looks at each step before it runs, and a *tool*, which can stop its job to ask for something while it runs. Both interrupt in the same way, and every interrupt is resumed in the same way.

## Before You Begin

You need Python 3.11 or later with `vfs-py` installed, and you should have finished [Control Who Can Access Files](../tutorials/control-who-can-access-files.md), because a policy works on top of the access rules that tutorial sets up.

The examples use one contract, an agent named Scout, and a person named Ada who approves Scout's work. Each Python block is one notebook cell, and the block after it shows what the cell prints. The calls use the synchronous file system, `VirtualFileSystem`, which is the one a notebook uses. The policies and tools you write are `async` functions either way, for the reason given in [Why Policies and Tools Are Async](#why-policies-and-tools-are-async).

## Step 1: Write a Policy

A policy is an `async` function marked with `@policy`. It takes one argument, the step that is about to run, and returns a `Decision`: `Decision.allow()` or `Decision.deny(reason)`. When the policy needs a person before it can decide, it asks for the person's answer and decides once it has it.

```python
from vfs import Decision, Mutation, policy, require_approval

@policy
async def contracts_need_a_person(step: Mutation) -> Decision:
    """A change to a contract needs a person."""
    if step.touches("/contracts"):
        return await require_approval("A change to a contract needs a person.")
    return Decision.allow()
```

`require_approval` interrupts the job with a yes-or-no question. When the job is resumed with the person's answer, the policy runs again, `require_approval` returns `Decision.allow()` for a yes and `Decision.deny(reason)` for a no, and the policy returns that decision. [Interrupt With Any Answer](#interrupt-with-any-answer) shows the general form, for a policy that needs more than a yes or a no.

The type you give the argument decides which steps the policy sees. `Mutation` is every step that changes something: a write, an edit, a delete, a move, a copy, a new directory, a restore. A policy typed this way is never asked about a read, so it costs nothing on the calls an agent makes most. Each verb has a step type of its own as well, such as `EditStep` or `DeleteStep`, and `Step` is every step, reads included. A union such as `DeleteStep | MoveStep` covers the two.

Every step carries the same core attributes, and each type adds the arguments of its own verb.

| Attribute | What it holds |
|---|---|
| `step.verb` | The name of the verb, such as `"edit"`, `"delete"`, or `"run"` for a tool |
| `step.paths` | Every path the step names |
| `step.authority` | Who is making the call |
| `step.via` | Where the step came from: `None` for a direct call, or the shell line or tool that made it |
| `step.touches(path)` | `True` when any of the paths is that path or inside it |
| Its own arguments | For an `EditStep`, `step.path`, `step.old` and `step.new`; for a `WriteStep`, `step.path` and the new content; and so on for each verb |

A step is checked before your policy sees it. A call whose arguments are wrong is refused as invalid and never reaches a policy, so a policy can trust every attribute it reads. A step is also frozen: a policy reads it and cannot change it.

**A policy must return a decision, and a policy that fails denies.** If it raises, returns anything other than a `Decision`, or takes longer than its deadline, the step is refused, and the refusal names the policy. A broken guard therefore stops the work rather than letting it through. `@policy` checks the function when you decorate it: a function that is not `async`, or that does not take one argument typed as a step, is refused there and then, before any file system exists.

A policy can only narrow what a caller may do. VFS checks the caller's access first, so a call the caller has no right to make is refused before any policy sees it.

## Step 2: Create the File System

Pass your policies when you create the file system, and add a contract.

```python
from vfs import Authority, Principal, VirtualFileSystem

fs = VirtualFileSystem(policies=[contracts_need_a_person])
system = Authority.system()

fs.write(
    path="/contracts/acme.md",
    content="Payment is due in 30 days.\n",
    parents=True,
    authority=system,
)
```

```text
write success: 1 file

  created /contracts/acme.md
```

The `system` authority stands for your own application code. No policy is applied to it, and its jobs are never interrupted, as [The System Authority Is Never Interrupted](#the-system-authority-is-never-interrupted) explains. You can add and remove a policy later with `fs.add_policy(contracts_need_a_person)` and `fs.remove_policy(contracts_need_a_person)`.

## Step 3: Make a Call That Is Interrupted

Open a session for Scout, and have Scout change the contract.

```python
scout = fs.open_session(Authority.of(Principal("scout")))

result = scout.edit("/contracts/acme.md", old="30 days", new="90 days")
result
```

```text
INTERRUPTED /contracts/acme.md: Interrupted (job 5d0c81aa) — A change to a contract needs a person. The job waits for a person and continues when it is resumed. (retry: resume)
```

The id in your output will be different. Nothing has changed. The call did not fail and it did not run: it stopped, and its job was saved. This is also the text Scout sees, so an agent learns that a person has been asked and that it does not need to try again.

```python
result.success, result.interrupted
```

```text
(False, True)
```

## Step 4: Look at the Interrupt

The result carries the job that stopped, and the job carries its interrupt.

```python
job = result.job
waiting = job.interrupt

job.id, job.state, waiting.message, waiting.raised_by
```

```text
('5d0c81aa', 'interrupted', 'A change to a contract needs a person.', 'contracts_need_a_person')
```

An interrupt before a change carries a preview, which is the change as it would land.

```python
waiting.preview
```

```text
edit would change: 1 file

  /contracts/acme.md
  -Payment is due in 30 days.
  +Payment is due in 90 days.
```

**This is what you show the person.** They approve a change they can read, not the name of a verb.

Every interrupt also carries the schema its answer must fit, as JSON Schema, so your application can build the form it shows the person from the interrupt alone.

```python
waiting.schema
```

```text
{'title': 'Approval', 'anyOf': [{'type': 'boolean'}, {'type': 'object', 'properties': {'approved': {'type': 'boolean'}, 'reason': {'type': ['string', 'null']}}, 'required': ['approved']}]}
```

| Attribute of an interrupt | What it holds |
|---|---|
| `message` | The text to show the person |
| `schema` | The JSON Schema the answer must fit |
| `preview` | What the step would change, or `None` when VFS cannot work that out |
| `details` | Anything else the policy or tool attached, or `None` |
| `raised_by` | The policy or tool that raised it |
| `step` | The step the job stopped before |
| `job_id` | The job it belongs to |
| `expires_at` | When the job lapses if nobody answers |

## Step 5: Resume the Job With the Answer

Your application now asks the person: a button in a chat window, a message, an approval queue, whatever suits it. When Ada says yes, resume the job with her answer.

```python
ada = Authority.of(Principal("ada", name="Ada Lovelace"))

fs.resume(job.id, True, authority=ada)
```

```text
edit success: 1 file

  edited /contracts/acme.md
```

The principal's `name` is a label for people and agents to read. VFS uses it wherever it reports who answered a job, and it plays no part in what the principal may do. A principal with no name is reported simply as a principal; its id is never shown, because it tells an agent nothing.

`resume` does two things in one call. It records Ada's answer to the job's interrupt, under her name, and it carries the job on from the step where it stopped. The result is the one Scout's call would have returned. Hand it to Scout in whatever way your application talks to its agent.

The answer must fit the interrupt's schema. One that does not is refused with the reason, nothing is recorded, and the job stays interrupted, so the person can answer again. The answer is bound to this job's interrupt and to nothing else, not even an identical edit Scout might make tomorrow.

**An agent cannot resume a job.** `resume` is a method of the file system your application holds. It is not on a session, it is not a shell command, and it is never offered to an agent as a tool.

Resuming does not make a new call. **It carries out the step that was saved, exactly as it was when Ada saw it.** Four rules keep that safe.

- **It runs as Scout.** Ada's answer lets Scout's step through. It does not lend Scout any of Ada's access, and if Scout lost access to the contract while the job waited, the step is refused.
- **It changes the file Ada saw.** If the contract changed between the preview and the resume, the step is refused as a conflict and nothing is written.
- **Your policies are asked again.** Each policy runs again with the answers the job has been given, so `require_approval` returns Ada's decision rather than interrupting a second time. A policy that now denies the step still denies it. So write a policy to reach the same point when it is asked twice about the same step.
- **One resume wins.** If two processes resume the same job at once, one carries it on and the other is refused with the job's state. Resuming a job that has already finished returns its result again, and records nothing.

## Step 6: Deny a Change

Have Scout try to delete the contract, and this time have Ada say no, with a reason.

```python
from vfs import Approval

result = scout.delete("/contracts/acme.md")

fs.resume(
    result.job.id,
    Approval(approved=False, reason="This contract is still in force."),
    authority=ada,
)
```

```text
ERROR /contracts/acme.md: Denied by Ada Lovelace — This step needed approval, and Ada Lovelace denied it. Reason: This contract is still in force. (retry: never)
```

`Approval` is the schema `require_approval` asks with. It accepts `True` or `False`, or an `Approval` with a reason. Without a reason, the message ends after "Ada Lovelace denied it." Had Ada's principal carried no name, the message would read "Denied by a principal — This step needed approval, and the principal that answered denied it."

The message names the principal the answer was given for. When an application answers on a person's behalf, with `Authority.on_behalf_of({ada_principal}, actor=approval_desk)`, the person made the decision and the application passed it on, so the message names both: "Denied by Ada Lovelace (through Approval Desk)". An actor with no name is left out.

**A denial is a decision made in answer to the interrupt, not a missing right, and the result says so.** Its kind is `vfs.interrupt.denied`, not `vfs.permission_denied`. Scout had the right to delete the contract; the principal who was asked said no. An agent that reads this result knows the change was decided against, so it does not look for another way to make it, and the reason tells it why.

## Cancel a Job

A person can also stop the whole job rather than answer its interrupt. Resume the job with `Cancel`, whatever the interrupt's schema is.

```python
from vfs import Cancel

result = scout.edit("/contracts/acme.md", old="30 days", new="45 days")

fs.resume(result.job.id, Cancel(reason="We are renegotiating this contract."), authority=ada)
```

```text
ERROR /contracts/acme.md: Cancelled by Ada Lovelace — This job was waiting for an answer, and Ada Lovelace cancelled it. Reason: We are renegotiating this contract. (retry: never)
```

`Cancel()` with no reason cancels the job too, and the message ends after "Ada Lovelace cancelled it." With no name on the principal, it reads "Cancelled by a principal".

A denial and a cancel differ in how much they stop. **A denial refuses one step, and the job carries on. A cancel ends the whole job where it stopped.** In a shell line, a denied step fails as a command fails and the line goes on to its next command, while a cancelled line runs nothing more. Either way, what the job did before it stopped stands: a cancel undoes nothing. Its kind is `vfs.interrupt.cancelled`, and a job that is cancelled cannot be resumed again.

| Kind | What happened | What it stops |
|---|---|---|
| `vfs.interrupt.denied` | A step needed approval, and the principal that answered said no | That step |
| `vfs.interrupt.cancelled` | The principal that answered cancelled the job while it waited | The whole job |

Both kinds sit under `vfs.interrupt`, the kinds that mean the answer to an interrupt decided against the work. Your application and your agent can match that prefix to tell such a decision from a refusal by an access rule or a policy.

## Interrupt With Any Answer

An approval is one kind of answer. A policy or a tool can ask for any answer it needs, by awaiting `interrupt` with a message and a schema. The schema is required: it says what the person must send back, and VFS refuses an answer that does not fit it. `interrupt` stops the job the first time it is reached. When the job is resumed, it returns the answer, already checked against the schema and of the schema's type.

This policy lets a change to a contract through only when a person names the ticket that authorises it.

```python
from pydantic import BaseModel
from vfs import interrupt

class Ticket(BaseModel):
    number: str

@policy
async def contract_changes_need_a_ticket(step: Mutation) -> Decision:
    """A change to a contract needs the ticket that authorises it."""
    if not step.touches("/contracts"):
        return Decision.allow()
    ticket = await interrupt("Which ticket authorises this change?", Ticket)
    if not ticket.number.startswith("LEGAL-"):
        return Decision.deny(f"{ticket.number} is not a legal ticket.")
    return Decision.allow()
```

The person's answer is a `Ticket`, or anything that validates as one, such as a dictionary with the same fields.

```python
result = scout.edit("/contracts/acme.md", old="90 days", new="60 days")
fs.resume(result.job.id, {"number": "LEGAL-142"}, authority=ada)
```

A schema can be any type pydantic can check: a model, a dataclass, a `TypedDict`, a `Literal`, or a plain `str`, `int` or `bool`. VFS ships two that are used often.

| Schema | The answer it takes | `interrupt` returns |
|---|---|---|
| `Approval` | `True`, `False`, or `Approval(approved=..., reason=...)` | An `Approval` |
| `Choice(options)` | One of the options | That option, as a `str` |

`require_approval(message)` is `interrupt(message, Approval)` turned into a decision, so most policies never need the long form.

## Step 7: Interrupt a Shell Line

A shell line is one job of many steps. When a step needs a person, the line stops before it. It keeps what it has already done, and it continues from the same point once the job is resumed.

Add a draft, then have Scout run a line that notes the change, replaces the contract with the draft, and removes the draft.

```python
fs.write(
    path="/drafts/acme.md",
    content="Payment is due in 60 days.\n",
    parents=True,
    authority=system,
)

result = scout.cli(
    'echo "replaced acme" >> /notes.md; '
    "cat /drafts/acme.md > /contracts/acme.md; "
    "rm /drafts/acme.md"
)
result
```

```text
INTERRUPTED /contracts/acme.md: Interrupted (job 2b9e6f10) — A change to a contract needs a person. The job waits for a person and continues when it is resumed. (retry: resume)
```

The first command ran, so the note is written. The second was interrupted. The third has not run. Resume as before.

```python
result = fs.resume(result.job.id, True, authority=ada)
result.success, fs.read("/notes.md", authority=system).one().content
```

```text
(True, 'replaced acme\n')
```

The line carried on where it stopped: the contract was replaced and the draft was removed. **Nothing ran twice.** The note was written once. VFS saved the line's text and every reply the line had been given up to the stop, and it resumed the line by running it again against those saved replies, without repeating any of the steps they stood for. If the shell has changed so that the line would no longer take the same path, the resume is refused with a conflict that says where it diverged, and nothing more is run.

Had Ada said no, the `cat` command would have failed as a command fails in bash, printing that Ada Lovelace denied it and her reason, and the line would have carried on. A line handles a denial as it handles any failed command, so `cmd || fallback` works. Had Ada cancelled the job, the line would have stopped there, and `rm /drafts/acme.md` would never have run.

**A line can stop more than once.** If a later step also needs a person, the resumed line stops again before it, and `resume` returns an interrupted result for the same job. When two commands in a pipeline each need a person, the job stops for the first one, and for the second after it is resumed. The loop that handles every case is short.

```python
result = scout.cli(line)
while result.interrupted:
    answer = ask_a_person(result.job.interrupt)
    result = fs.resume(result.job.id, answer, authority=ada)
```

Here `ask_a_person` stands for your own code. A resumed line runs as whoever started it, with that caller's access as it stands at the resume.

## Step 8: Write a Tool That Asks a Question

A tool is an `async` function marked with `@tool`. An agent runs it by name from a shell line, as it runs `grep`. A tool asks a person for something in the same way a policy does, by awaiting `interrupt`.

```python
from vfs import AsyncSession, Choice, tool

@tool
async def translate(path: str, *, files: AsyncSession) -> str:
    """Translate a report into another language."""
    text = (await files.read(path)).one().content
    language = await interrupt(
        f"Translate {path} into which language?",
        Choice(["french", "german"]),
    )
    target = path.replace(".md", f".{language}.md")
    await files.write(path=target, content=await translate_text(text, language))
    return target

fs.add_tool(translate)
```

Here `translate_text` stands for your own code. The parameter typed `AsyncSession` is not something the agent passes: VFS fills it in with a session for whoever runs the tool, so the tool reads and writes files as its caller, checked against the caller's access and your policies.

Add a report, then have Scout run the tool on it.

```python
fs.write(
    path="/reports/q3.md",
    content="# Third Quarter Report\n\nRevenue grew.\n",
    parents=True,
    authority=system,
)

result = scout.cli("translate /reports/q3.md")
result.job.interrupt.message
```

```text
'Translate /reports/q3.md into which language?'
```

```python
fs.resume(result.job.id, "french", authority=ada)
```

```text
/reports/q3.french.md
```

There is one thing to know about a tool that asks. **When the job resumes, the tool's function starts again from its first line.** VFS can save a shell line, and it cannot save a Python function part-way through. So the function runs again, and this time `interrupt` returns Ada's answer and the function carries on. Each `interrupt` a tool reaches has its own place in the job, so each one gets its own answer, and only its own. If the question at that place has changed by the time the function runs again, its earlier answer is not used, and the job is interrupted anew.

Three rules make starting again safe.

- **A tool asks before it changes a file.** Once a tool has written through its session, a call to `interrupt` fails the tool with a message naming this rule. So a tool that starts again never has a write of its own to repeat. `translate` follows the rule: it reads, then asks, then writes.
- **An answer is for the files the tool had read.** If `/reports/q3.md` changes while the job waits, Ada's answer is not used, and the job is interrupted again about the report as it now is.
- **What a tool does outside VFS is yours to order.** VFS cannot see a request your tool makes to another service, so it cannot keep that request from running again. Put such code after the last `interrupt`, as `translate` puts its write.

A question has no "no": the person either answers it in the shape the schema asks for, or cancels the job with `Cancel`. A tool fails as a program fails. When it raises `ToolError`, the message goes to standard error and the status is 1, and the line treats it as any command that fails.

## Step 9: Have a Person Approve a Tool

Some tools should not run at all until a person says yes. Mark them with `approval=True`.

```python
@tool(approval=True)
async def publish(path: str, *, files: AsyncSession) -> str:
    """Publish a report to the company website."""
    await post_to_website((await files.read(path)).one().content)
    return f"published {path}"

fs.add_tool(publish)
```

Every run of `publish` interrupts its job with an `Approval` before the function is called, and the function runs once, after the answer. A policy can ask for the same approval without a change to the tool: a run of a tool reaches your policies as a `RunStep`, whose `step.tool` is the tool's name and whose `step.arguments` are the arguments it was given.

```python
from vfs import RunStep

@policy
async def review_publishing(step: RunStep) -> Decision:
    if step.tool == "publish":
        return await require_approval(f"Publish {step.arguments['path']}?")
    return Decision.allow()
```

## Combine Policies

A file system can hold any number of policies. Each step is shown to every policy whose type covers it, and the strictest decision wins: one denial refuses the step, whatever the others decide. When no policy denies and some need a person, the job is interrupted for the first of them, in the order the policies were added, and for the next one after it is resumed. A step that one policy denies is refused at once, and no person is asked about it.

**With no policy, nothing is interrupted.** That is the default, and it is the mode to use when an agent should work without stopping.

VFS ships one policy ready to use. `policies.review` allows every read and requires approval for every change under the paths you give it, and for every run of a tool.

```python
from vfs import policies

fs = VirtualFileSystem(
    policies=[policies.review(paths=["/contracts", "/finance"]), review_publishing],
)
```

Give it the folders that matter. Over a whole file system it asks too often, and a person who is asked all day stops reading what they approve.

A session can carry policies of its own, which is how one application runs a careful agent beside a free one.

```python
careful = fs.open_session(
    Authority.of(Principal("scout")),
    policies=[policies.review(paths=["/"])],
)
```

A session's policies are added to the file system's, and asked after them. **A session can ask for more review. It can never ask for less.**

## The System Authority Is Never Interrupted

The `system` authority stands for your own application, so no policy is applied to its steps, and a job it starts can never be interrupted. When something would interrupt a system job anyway, such as a tool that awaits `interrupt` or a tool marked `approval=True` run directly with `run`, the step fails with an error that names this rule, and the job ends there. A shell line never runs as the system authority, so this happens only when your own code runs a tool that asks.

To run such a tool from your own code, run it with the authority of the person or agent the work is for. The job can then be interrupted and resumed like any other.

## Find Jobs That Are Waiting

A job that is interrupted is stored in the database, so the answer does not have to come from the program that made the call. A person can answer from another process, or the next morning. List the jobs that are waiting.

```python
fs.jobs(state="interrupted", authority=ada)
```

```text
| id       | state       | started_by | verb | path               | message                                | expires_at                |
| -------- | ----------- | ---------- | ---- | ------------------ | -------------------------------------- | ------------------------- |
| 91aa3c57 | interrupted | scout      | edit | /contracts/acme.md | A change to a contract needs a person. | 2026-11-23 15:04:11+00:00 |
```

Called with a person's authority, `fs.jobs` lists only the jobs that person may resume, so an approval screen is built from this one call.

A file system that keeps its files in memory keeps its jobs in memory too, and they end with the program. To resume a job from another process, create the file system on a database, as shown in [Keep Your Files in a Database](../tutorials/keep-your-files-in-a-database.md).

## Who May Resume, and for How Long

A person may resume a job interrupted before a change when they have `write` access to every path the step names. A person may resume a job a tool interrupted when they may run that tool. Anyone else is refused, and nothing is recorded. The `system` authority may resume any job.

A job that waits lapses 24 hours after it stopped. Change the time when you create the file system, with `VirtualFileSystem(job_lifetime=timedelta(hours=72))`. To give up on a job before then, resume it with `Cancel`, as [Cancel a Job](#cancel-a-job) shows; your application can do that as the `system` authority when nobody is going to answer. The agent then reads "Cancelled by the system". Give the system principal a name, with `Authority.system(name="Nightly cleanup")`, and it reads "Cancelled by Nightly cleanup". A lapsed or cancelled job cannot be resumed, and nothing it was waiting to do is done.

## Use It Inside a LangGraph Application

An application built on LangGraph has its own `interrupt()` and `Command(resume=...)`, and the two fit together. LangGraph runs a node again from the top when it resumes the graph. When the node makes Scout's call again, VFS sees the same step by the same caller while its job is still waiting, and returns that job rather than starting a second one.

```python
from langgraph.types import interrupt as ask

async def change_contract(state):
    result = await scout.edit(state["path"], old=state["old"], new=state["new"])
    while result.interrupted:
        waiting = result.job.interrupt
        answer = ask({"message": waiting.message, "schema": waiting.schema, "preview": str(waiting.preview)})
        result = await fs.resume(result.job.id, answer, authority=ada)
    return {"outcome": str(result)}
```

This node is `async`, so here `fs` is an `AsyncVirtualFileSystem` and `scout` a session opened on it, and every call is awaited. The first time the node runs, the edit is interrupted, and `ask` stops the graph with the message, the schema and the preview. When your application resumes the graph, the node runs again: the edit returns the same waiting job, `ask` returns the person's answer, and the job is resumed with it. If the node runs again after that, resuming a finished job returns its result and records nothing, so the node is safe to run again.

## Why Policies and Tools Are Async

VFS runs every call on one asynchronous kernel. The synchronous file system you use in a notebook is a thin wrapper that hands each call to that kernel and waits for it. Your policies and tools run inside the kernel, so they are `async` functions, and a tool's session is the asynchronous `AsyncSession`. A synchronous function there would hold up every other call while it ran, and a synchronous tool calling back into VFS could wait forever on itself.

An `async` function can still stall the kernel if it does slow work without awaiting. If your policy or tool calls a library that blocks, such as one that reads a large file from disk or makes a network request without `await`, run that part on a thread.

```python
import asyncio

@tool
async def checksum(path: str) -> str:
    """Print the checksum of a file on the host's disk."""
    return await asyncio.to_thread(compute_checksum, path)
```

## What to Remember

Every call through VFS is a job, and every verb it carries out is a step. A policy, marked `@policy`, sees each step before it runs and allows it or denies it. A policy or a tool that needs a person awaits `interrupt` with a message and the schema of the answer it needs. VFS never asks and never waits: it stops the job before the step, saves it, and returns, and a job waits on one interrupt at a time. Your application asks the person, and `resume` records the answer and carries the job on, as its caller, against what the person saw, with nothing run twice. The principal that answers can deny a step, which refuses that step, or cancel the job, which ends it. Both are reported as that principal's decision, by its name when it has one, under `vfs.interrupt`, and never as a missing right.
