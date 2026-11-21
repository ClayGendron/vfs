# Interrupt a Call and Ask a Person

This guide shows how to stop a call before it changes anything, show a person what it would do, and let it continue once they approve. Use it when an AI agent works on files that matter, and some of its changes should wait for a person.

**VFS never asks a person anything, and it never waits for one.** It stops the call, describes what the call would do, and returns. Your application asks the person in whatever way it likes. When the person has answered, your application tells VFS, and the call goes through. A call that is stopped this way is called an interrupt.

## Before You Begin

You need Python 3.11 or later with `vfs-py` installed, and you should have finished [Control Who Can Access Files](../tutorials/control-who-can-access-files.md).

The examples use a file system in memory, one contract, an agent named Scout and a person named Ada. Each Python block below is one notebook cell, and the block after it shows what that cell prints.

## Step 1: Write a Policy

A policy is a function you write. VFS shows it every call before the call runs, and the policy returns one of three decisions: allow it, deny it, or interrupt it.

```python
from vfs import Decision

def policy(call):
    changes_a_contract = call.mutates and any(
        path.startswith("/contracts/") for path in call.paths
    )
    if changes_a_contract:
        return Decision.interrupt("A change to a contract needs a person.")
    return Decision.allow()
```

This policy interrupts every call that would change something under `/contracts`, and allows everything else. The `call` it receives says what is about to happen.

| Attribute | What it holds |
|---|---|
| `call.op` | The name of the operation, such as `"edit"` or `"delete"` |
| `call.paths` | Every path the call names |
| `call.mutates` | `True` when the call would change something |
| `call.arguments` | The arguments of the call, by name |
| `call.authority` | Who is making the call |

A policy can only narrow what a caller may do. VFS checks the caller's access first, so a call the caller has no right to make is refused before the policy sees it. **A policy must return a decision. If it returns anything else, or raises, the call is refused.**

Create the file system with the policy, and add a contract.

```python
from vfs import Authority, Principal, VirtualFileSystem

fs = VirtualFileSystem(policy=policy)
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

The `system` authority stands for your own application code, and a policy is never applied to it.

## Step 2: Make a Call That Is Interrupted

Open a session for Scout, and have it change the contract.

```python
scout = fs.open_session(Authority.of(Principal("scout")))

result = scout.edit("/contracts/acme.md", old="30 days", new="90 days")
result
```

```text
INTERRUPTED /contracts/acme.md: Interrupted (interrupt 7f3a9c2e) — A change to a contract needs a person. Answer the interrupt, then make the same call again. (retry: resume)
```

The id in your output will be different. Nothing has changed. The call did not fail and it did not run: it stopped.

The result says so in two places.

```python
result.success, result.interrupted
```

```text
(False, True)
```

## Step 3: Look at What the Call Would Do

A stopped call carries one interrupt for each thing a person must answer. Take the first.

```python
interrupt = result.interrupts[0]

interrupt.reason
```

```text
'A change to a contract needs a person.'
```

An interrupt for a change also carries a preview, which is the change as it would land.

```python
interrupt.preview
```

```text
edit would change: 1 file

  /contracts/acme.md
  -Payment is due in 30 days.
  +Payment is due in 90 days.
```

**This is what you show the person.** They approve a change they can read, and not the name of an operation.

| Attribute | What it holds |
|---|---|
| `interrupt.id` | The id you answer |
| `interrupt.reason` | The reason your policy gave |
| `interrupt.op` | The operation that was stopped |
| `interrupt.paths` | The paths it names |
| `interrupt.preview` | What the call would change, or `None` for a call that changes nothing |
| `interrupt.asked_by` | Who made the call |
| `interrupt.expires_at` | When the interrupt lapses |

## Step 4: Answer the Interrupt

Your application now asks the person. How it asks is yours to decide: a button in a chat window, a message, an approval queue. When Ada says yes, record her answer.

```python
ada = Authority.of(Principal("ada"))

fs.answer(interrupt.id, allow=True, authority=ada)
```

```text
answer success: 1 interrupt

  allowed 7f3a9c2e by ada
```

The answer is recorded under Ada's name. It lets this one call through, once.

**An agent cannot answer an interrupt.** `answer` is a method of the file system your application holds. It is not on a session, it is not a shell command, and it is never offered to an agent as a tool.

## Step 5: Make the Same Call Again

Have Scout make the call again, exactly as before.

```python
scout.edit("/contracts/acme.md", old="30 days", new="90 days")
```

```text
edit success: 1 file

  edited /contracts/acme.md
```

This time it runs. The policy is not asked again, because the answer is already on record.

The approval was for this one call, and three rules keep it that way.

- **It is used once.** If Scout makes the same call a third time, it is interrupted again.
- **It covers this exact call.** If Scout changes any argument, such as `new="120 days"`, that is a different call, and it is interrupted.
- **It covers the file the person saw.** If the contract changed between the preview and the second call, the call is refused as a conflict and nothing is written. The next attempt is interrupted again, with a new preview.

The call still runs as Scout. Ada's approval lets Scout's call through. It does not lend Scout any of Ada's access.

## Step 6: Reject an Interrupt

Have Scout try to delete the contract.

```python
result = scout.delete("/contracts/acme.md")
interrupt = result.interrupts[0]

interrupt.preview
```

```text
delete would remove: 1 file

  /contracts/acme.md
```

This time Ada says no.

```python
fs.answer(
    interrupt.id,
    allow=False,
    reason="This contract is still in force.",
    authority=ada,
)
```

```text
answer success: 1 interrupt

  rejected 7c1d04b9 by ada
```

When Scout makes the call again, it is refused, and the refusal carries Ada's reason.

```python
scout.delete("/contracts/acme.md")
```

```text
ERROR /contracts/acme.md: Permission denied — This contract is still in force. (retry: never)
```

An agent reads that reason and can act on it.

## Step 7: Interrupt a Shell Line

A shell line is many calls. When one of them is interrupted, the line stops at that point. It keeps what it has already done, and it continues from the same point once the interrupt is answered.

Add a draft, then have Scout run a line that notes the change, replaces the contract with the draft, and removes the draft.

```python
fs.write(
    path="/drafts/acme.md",
    content="Payment is due in 60 days.\n",
    parents=True,
    authority=system,
)

line = (
    'echo "replaced acme" >> /notes.md; '
    "cat /drafts/acme.md > /contracts/acme.md; "
    "rm /drafts/acme.md"
)
result = scout.cli(line)
result
```

```text
INTERRUPTED /contracts/acme.md: Interrupted (interrupt 2b9e6f10, run 5d0c81aa) — A change to a contract needs a person. Answer the interrupt, then resume the run. (retry: resume)
```

The first command ran, so the note is written. The second was interrupted. The third has not run.

A line that stops is a run, and every interrupt it raises carries the run's id. Answer the interrupt as before, then resume the run.

```python
interrupt = result.interrupts[0]

fs.answer(interrupt.id, allow=True, authority=ada)
result = scout.resume(interrupt.run_id)
result.success
```

```text
True
```

The line continued where it stopped. The contract was replaced and the draft was removed. **Nothing ran twice:** the note was written once.

```python
fs.read("/notes.md", authority=system)
```

```text
replaced acme
```

Three things are true of every run.

- **Interrupts raised together are reported together.** When two commands in one pipeline are both interrupted, the line finishes what it can and stops once, with both interrupts on the result.
- **A line can stop more than once.** If the resumed line reaches another interrupt, `resume` returns a stopped result again. Answer and resume until `result.interrupted` is `False`.
- **A resumed line runs as whoever started it.** It has Scout's access when it starts and Scout's access when it resumes.

The loop that handles every case is short.

```python
result = scout.cli(line)
while result.interrupted:
    for interrupt in result.interrupts:
        allow = ask_a_person(interrupt)
        fs.answer(interrupt.id, allow=allow, authority=ada)
    result = scout.resume(result.interrupts[0].run_id)
```

Here `ask_a_person` stands for your own code.

## Find Interrupts That Are Waiting

An interrupt is stored in the database, so the answer does not have to come from the program that made the call. A person can answer from another process, or the next morning. Have Scout raise one more, and then list what is waiting.

```python
scout.edit("/contracts/acme.md", old="60 days", new="45 days")

fs.interrupts(authority=system)
```

```text
| id       | op     | path               | asked_by | reason                                  | expires_at                |
| -------- | ------ | ------------------ | -------- | --------------------------------------- | ------------------------- |
| 91aa3c57 | edit   | /contracts/acme.md | scout    | A change to a contract needs a person.  | 2026-11-22 15:04:11+00:00 |
```

The result's `interrupts` attribute holds the same `Interrupt` values a stopped call carries, so an approval screen is built from this one call. Called with a person's authority, it lists only the interrupts that person may answer.

A file system that keeps its files in memory keeps its interrupts in memory too, and they end with the program. To answer from another process, create the file system on a database, as shown in [Keep Your Files in a Database](../tutorials/keep-your-files-in-a-database.md).

## Who May Answer, and for How Long

A person may answer an interrupt when they have `write` access to every path it names. Anyone else is refused, and nothing is recorded. The `system` authority may always answer.

An interrupt lapses 24 hours after it is raised. A call made after that is interrupted again, with a new id. Change the time when you create the file system.

```python
fs = VirtualFileSystem(policy=policy, interrupt_hours=72)
```

## Use It with LangGraph

LangGraph has its own `interrupt()` and `Command(resume=...)`. The two fit together, because LangGraph runs a node again from the top when it resumes, and VFS expects the same call to be made again.

```python
from langgraph.types import interrupt as ask

def change_contract(state):
    result = scout.edit(state["path"], old=state["old"], new=state["new"])
    if result.interrupted:
        stopped = result.interrupts[0]
        approved = ask({"reason": stopped.reason, "preview": str(stopped.preview)})
        fs.answer(stopped.id, allow=approved, authority=ada)
        result = scout.edit(state["path"], old=state["old"], new=state["new"])
    return {"outcome": str(result)}
```

The first time the node runs, the edit is interrupted, and `ask` stops the graph with the reason and the preview. When your application resumes the graph with `Command(resume=True)`, the node runs again from the top. The edit is interrupted again and returns the same interrupt, because it is still waiting. This time `ask` returns the person's answer, the answer is recorded, and the edit goes through.

## What to Remember

VFS stops a call and describes it. Your application asks the person and records the answer. The same call then runs once, as the caller, against the file the person saw.
