# Interrupt a Job and Ask a Person

This guide shows how to stop an agent's work at the points that need a person, show the person what would happen, and carry the work on from where it stopped once they answer. Use it when an AI agent works on files that matter, when some of its changes should wait for approval, or when a tool needs an answer that only a person can give.

> **This guide describes an API that is designed and not yet built.** It is written first so that the API can be agreed before the code is written. The names on this page may still change.

**VFS never asks a person anything, and it never waits for one.** Every call you make through VFS is a *job*. Most jobs finish inside the call that started them, and VFS keeps nothing for them. When something inside a job needs a person, VFS stops the job, saves it in the database, and returns at once. What the person must answer is an *interrupt*. Your application asks the person in whatever way it likes, records the answer, and resumes the job. The job then carries on from the point where it stopped.

Three things can interrupt a job: a *policy* you write, which looks at each operation before it runs; a tool that must be approved before it runs; and a tool that asks a question while it runs. This guide covers all three, and each one is answered and resumed in the same way.

## Before You Begin

You need Python 3.11 or later with `vfs-py` installed, and you should have finished [Control Who Can Access Files](../tutorials/control-who-can-access-files.md), because a policy works on top of the access rules that tutorial sets up.

The examples use one contract, an agent named Scout, and a person named Ada who approves Scout's work. Each Python block is one notebook cell, and the block after it shows what the cell prints. The calls use the synchronous file system, `VirtualFileSystem`, which is the one a notebook uses. The policies and tools you write are `async` functions either way, for the reason given in [Why Policies and Tools Are Async](#why-policies-and-tools-are-async).

## Step 1: Write a Policy

A policy is an `async` function marked with `@policy`. It takes one argument, the operation that is about to run, and returns a decision: allow it, deny it, or interrupt it.

```python
from vfs import Decision, Mutation, policy

@policy
async def contracts_need_a_person(op: Mutation) -> Decision:
    """A change to a contract needs a person."""
    if op.touches("/contracts"):
        return Decision.interrupt("A change to a contract needs a person.")
    return Decision.allow()
```

The type you give the argument decides which operations the policy sees. `Mutation` is every operation that changes something: a write, an edit, a delete, a move, a copy, a new directory, a restore. A policy typed this way is never asked about a read, so it costs nothing on the calls an agent makes most. Each operation has a type of its own as well, such as `EditOperation` or `DeleteOperation`, and `Operation` is every operation, reads included. A union such as `DeleteOperation | MoveOperation` covers the two.

Every operation carries the same core attributes, and each type adds the arguments of its own verb.

| Attribute | What it holds |
|---|---|
| `op.verb` | The name of the verb, such as `"edit"`, `"delete"`, or `"run"` for a tool |
| `op.paths` | Every path the operation names |
| `op.authority` | Who is making the call |
| `op.via` | Where the operation came from: `None` for a direct call, or the shell line or tool that made it |
| `op.touches(path)` | `True` when any of the paths is that path or inside it |
| Its own arguments | For an `EditOperation`, `op.path`, `op.old` and `op.new`; for a `WriteOperation`, `op.path` and the new content; and so on for each verb |

An operation is checked before your policy sees it. A call whose arguments are wrong is refused as invalid and never reaches a policy, so a policy can trust every attribute it reads. An operation is also frozen: a policy reads it and cannot change it.

**A policy must return a decision, and a policy that fails denies.** If it raises, returns anything other than a `Decision`, or takes longer than its deadline, the operation is refused, and the refusal names the policy. A broken guard therefore stops the work rather than letting it through. `@policy` checks the function when you decorate it: a function that is not `async`, or that does not take one argument typed as an operation, is refused there and then, before any file system exists.

A policy can only narrow what a caller may do. VFS checks the caller's access first, so a call the caller has no right to make is refused before any policy sees it. The `system` authority stands for your own application code, and no policy is ever applied to it.

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

You can add and remove a policy later with `fs.add_policy(contracts_need_a_person)` and `fs.remove_policy(contracts_need_a_person)`.

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

## Step 4: Look at the Job

The result carries the job that stopped, and the job carries one interrupt for each thing a person must answer.

```python
job = result.job
stopped = job.interrupts[0]

job.id, job.state, stopped.kind, stopped.message
```

```text
('5d0c81aa', 'interrupted', 'approval', 'A change to a contract needs a person.')
```

An approval for a change also carries a preview, which is the change as it would land.

```python
stopped.preview
```

```text
edit would change: 1 file

  /contracts/acme.md
  -Payment is due in 30 days.
  +Payment is due in 90 days.
```

**This is what you show the person.** They approve a change they can read, not the name of an operation.

| Attribute of an interrupt | What it holds |
|---|---|
| `id` | The id you answer |
| `kind` | `"approval"` for a yes or a no, or `"question"` for a tool that asks for a value |
| `message` | The text to show the person |
| `preview` | What the operation would change, or `None` when VFS cannot work that out |
| `options` | For a question, the answers allowed, or `None` when any value is allowed |
| `raised_by` | The policies or the tool that raised it |
| `paths` | The paths the operation names |
| `job_id` | The job it belongs to |
| `expires_at` | When it lapses |

## Step 5: Answer the Interrupt

Your application now asks the person: a button in a chat window, a message, an approval queue, whatever suits it. When Ada says yes, record her answer.

```python
ada = Authority.of(Principal("ada"))

fs.answer(stopped.id, allow=True, authority=ada)
```

```text
answer success: 1 interrupt

  allowed 7f3a9c2e by ada
```

The answer is recorded under Ada's name, and it is bound to this one interrupt. It answers nothing else, not even an identical edit Scout might make tomorrow. Answering the same interrupt again with the same answer reports that it is already answered and changes nothing; answering it with a different answer, or answering an interrupt that is unknown or has lapsed, is refused, and nothing is recorded.

**An agent cannot answer an interrupt.** `answer` is a method of the file system your application holds. It is not on a session, it is not a shell command, and it is never offered to an agent as a tool.

## Step 6: Resume the Job

Once every interrupt of a job is answered, resume it.

```python
fs.resume(job.id)
```

```text
edit success: 1 file

  edited /contracts/acme.md
```

The result is the one Scout's call would have returned. Hand it to Scout in whatever way your application talks to its agent.

Resuming does not make a new call. **It carries out the operation that was saved, exactly as it was when Ada saw it.** Four rules keep that safe.

- **It runs as Scout.** Ada's approval lets Scout's operation through. It does not lend Scout any of Ada's access, and if Scout lost access to the contract while the job waited, the operation is refused.
- **It changes the file Ada saw.** If the contract changed between the preview and the resume, the operation is refused as a conflict and nothing is written.
- **Your policies are asked again.** A policy whose interrupt Ada answered counts as allowing the operation. A policy that now denies it still denies it. So write a policy to give the same decision when it is asked twice about the same operation.
- **One resume wins.** If two processes resume the same job at once, one carries it on and the other is refused with the job's state. A resume of a job that has already finished returns its result again.

## Step 7: Reject an Interrupt

Have Scout try to delete the contract, and this time have Ada say no.

```python
result = scout.delete("/contracts/acme.md")
stopped = result.job.interrupts[0]

fs.answer(
    stopped.id,
    allow=False,
    reason="This contract is still in force.",
    authority=ada,
)
fs.resume(result.job.id)
```

```text
ERROR /contracts/acme.md: Permission denied — This contract is still in force. (retry: never)
```

A rejected operation is refused with the reason Ada gave, and Scout can read that reason and act on it.

## Step 8: Interrupt a Shell Line

A shell line is one job made of many operations. When one of them is interrupted, the line stops at that point. It keeps what it has already done, and it continues from the same point once the interrupt is answered.

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

The first command ran, so the note is written. The second was interrupted. The third has not run. Answer and resume as before.

```python
fs.answer(result.job.interrupts[0].id, allow=True, authority=ada)
result = fs.resume(result.job.id)
result.success, fs.read("/notes.md", authority=system).one().content
```

```text
(True, 'replaced acme\n')
```

The line carried on where it stopped: the contract was replaced and the draft was removed. **Nothing ran twice.** The note was written once. VFS saved the line's text and every answer the line had been given up to the stop, and it resumed the line by running it again against those saved answers, without repeating any of the operations they stood for. If the shell has changed so that the line would no longer take the same path, the resume is refused with a conflict that says where it diverged, and nothing more is run.

Had Ada said no, the `cat` command would have failed as a command fails in bash, and the line would have carried on. A line handles a rejection as it handles any failed command, so `cmd || fallback` works.

Three more things are true of a line that is interrupted.

- **Interrupts raised together are reported together.** When two commands in one pipeline are both interrupted, the line finishes what it can and stops once, with both interrupts on the job.
- **A job can stop more than once.** If the resumed line reaches another interrupt, `resume` returns an interrupted result again, for the same job.
- **A line resumes as whoever started it,** with that caller's access as it stands at the resume.

The loop that handles every case is short.

```python
result = scout.cli(line)
while result.interrupted:
    for stopped in result.job.interrupts:
        allow = ask_a_person(stopped)
        fs.answer(stopped.id, allow=allow, authority=ada)
    result = fs.resume(result.job.id)
```

Here `ask_a_person` stands for your own code.

## Step 9: Write a Tool That Asks a Question

A tool is an `async` function marked with `@tool`. An agent runs it by name from a shell line, as it runs `grep`. A tool can stop its job to ask a person a question, by awaiting `interrupt`.

```python
from vfs import AsyncSession, interrupt, tool

@tool
async def translate(path: str, *, files: AsyncSession) -> str:
    """Translate a report into another language."""
    text = (await files.read(path)).one().content
    language = await interrupt(
        f"Translate {path} into which language?",
        options=["french", "german"],
    )
    target = path.replace(".md", f".{language}.md")
    await files.write(path=target, content=await translate_text(text, language))
    return target

fs.add_tool(translate)
```

Here `translate_text` stands for your own code. The parameter typed `AsyncSession` is not something the agent passes: VFS fills it in with a session for whoever runs the tool, so the tool reads and writes files as its caller and is checked against the caller's access and your policies.

Add a report, then have Scout run the tool on it.

```python
fs.write(
    path="/reports/q3.md",
    content="# Third Quarter Report\n\nRevenue grew.\n",
    parents=True,
    authority=system,
)

result = scout.cli("translate /reports/q3.md")
stopped = result.job.interrupts[0]

stopped.kind, stopped.options
```

```text
('question', ['french', 'german'])
```

```python
fs.answer(stopped.id, value="french", authority=ada)
fs.resume(result.job.id)
```

```text
/reports/q3.french.md
```

An answer that is not one of the options is refused, and nothing is recorded. A person can also decline to answer, with `fs.answer(stopped.id, allow=False, reason="Ask me tomorrow.", authority=ada)`. The tool then fails with that reason on standard error and status 1, and the line treats it as any command that fails.

There is one thing to know about a tool that asks. **When the job resumes, the tool's function starts again from its first line.** VFS can save a shell line, and it cannot save a Python function part-way through. So the function runs again, and this time `interrupt` returns Ada's answer and the function carries on. Each question a tool asks has its own place in the job, so each one gets its own answer, and only its own. If a question has changed by the time the function runs again, its earlier answer is not used and the question is asked anew.

Three rules make starting again safe.

- **A tool asks before it changes a file.** Once a tool has written through its session, a call to `interrupt` fails the tool with a message naming this rule. So a tool that starts again never has a write of its own to repeat. `translate` follows the rule: it reads, then asks, then writes.
- **An answer is for the files the tool had read.** If `/reports/q3.md` changes while the question waits, Ada's answer is not used, and the question is asked again about the report as it now is.
- **What a tool does outside VFS is yours to order.** VFS cannot see a request your tool makes to another service, so it cannot keep that request from running again. Put such code after the last `interrupt`, as `translate` puts its write.

## Step 10: Have a Person Approve a Tool

Some tools should not run at all until a person says yes. Mark them with `approval=True`.

```python
@tool(approval=True)
async def publish(path: str, *, files: AsyncSession) -> str:
    """Publish a report to the company website."""
    await post_to_website((await files.read(path)).one().content)
    return f"published {path}"

fs.add_tool(publish)
```

Every run of `publish` is interrupted with an approval before its function is called, and the function runs once, after the answer. A policy can ask for the same approval without a change to the tool: a run of a tool reaches your policies as a `RunOperation`, whose `op.tool` is the tool's name and whose `op.arguments` are the arguments it was given.

```python
from vfs import RunOperation

@policy
async def review_publishing(op: RunOperation) -> Decision:
    if op.tool == "publish":
        return Decision.interrupt(f"Publish {op.arguments['path']}?")
    return Decision.allow()
```

## Combine Policies

A file system can hold any number of policies. Each operation is shown to every policy whose type covers it, and the strictest answer wins: a denial wins over an interrupt, and an interrupt wins over an allow. The order you list them in does not matter. When several policies interrupt the same operation, the person is asked once, and the interrupt names every policy that raised it.

**With no policy, nothing is interrupted.** That is the default, and it is the mode to use when an agent should work without stopping.

VFS ships one policy ready to use. `policies.review` allows every read and interrupts every change under the paths you give it, and every run of a tool.

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

A session's policies are added to the file system's, and the strictest answer still wins. **A session can ask for more review. It can never ask for less.**

## Find Jobs That Are Waiting

A job that is interrupted is stored in the database, so the answer does not have to come from the program that made the call. A person can answer from another process, or the next morning. List what is waiting.

```python
fs.jobs(state="interrupted", authority=system)
```

```text
| id       | state       | started_by | verb | path               | interrupts | expires_at                |
| -------- | ----------- | ---------- | ---- | ------------------ | ---------- | ------------------------- |
| 91aa3c57 | interrupted | scout      | edit | /contracts/acme.md | 1          | 2026-11-23 15:04:11+00:00 |
```

To build an approval screen, list the interrupts themselves. Called with a person's authority, `fs.interrupts` lists only the interrupts that person may answer.

```python
fs.interrupts(authority=ada)
```

A file system that keeps its files in memory keeps its jobs in memory too, and they end with the program. To resume a job from another process, create the file system on a database, as shown in [Keep Your Files in a Database](../tutorials/keep-your-files-in-a-database.md).

## Who May Answer, and for How Long

A person may answer an approval when they have `write` access to every path it names. A person may answer a tool's question when they may run that tool. Anyone else is refused, and nothing is recorded. The `system` authority may always answer.

A job that waits lapses 24 hours after it stopped, and its interrupts lapse with it. Change the time when you create the file system, with `VirtualFileSystem(job_lifetime=timedelta(hours=72))`. To give up on a job before then, cancel it with `fs.cancel(job.id)`. A lapsed or cancelled job cannot be resumed, and nothing it was waiting to do is done.

## Use It Inside a LangGraph Application

An application built on LangGraph has its own `interrupt()` and `Command(resume=...)`, and the two fit together. LangGraph runs a node again from the top when it resumes the graph. When the node makes Scout's call again, VFS sees the same operation by the same caller while its job is still waiting, and returns that job rather than raising a second interrupt.

```python
from langgraph.types import interrupt as ask

async def change_contract(state):
    result = await scout.edit(state["path"], old=state["old"], new=state["new"])
    if result.interrupted:
        for stopped in result.job.interrupts:
            approved = ask({"message": stopped.message, "preview": str(stopped.preview)})
            await fs.answer(stopped.id, allow=approved, authority=ada)
        result = await fs.resume(result.job.id)
    return {"outcome": str(result)}
```

This node is `async`, so here `fs` is an `AsyncVirtualFileSystem` and `scout` a session opened on it, and every call is awaited. The first time the node runs, the edit is interrupted, and `ask` stops the graph with the message and the preview. When your application resumes the graph, the node runs again: the edit returns the same waiting job, `ask` returns the person's answer, the answer is recorded, and the job is resumed. If the node runs a third time, answering an interrupt that already holds the same answer changes nothing, so the node is safe to run again.

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

Every call through VFS is a job. A policy, marked `@policy`, sees each operation before it runs, and allows it, denies it, or interrupts it. A tool, marked `@tool`, can need approval or ask a question with `interrupt`. VFS never asks and never waits: it stops the job, saves it, and returns. Your application asks the person, records the answer with `answer`, and carries the job on with `resume`, which runs the saved work as its caller, against what the person saw, with nothing run twice.
