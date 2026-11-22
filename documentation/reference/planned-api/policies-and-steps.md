# Policies and Steps

A [policy](../glossary.md#policy) is a function you write that VFS shows each [step](../glossary.md#step) before the step runs. The policy allows the step, denies it, or asks for a person. This page lists every name, argument, value and refusal of that design. [Interrupt a Job and Ask a Person](../../how-to/interrupt-a-job-and-ask-a-person.md) shows it in use.

> **This page describes an API that is designed and not yet built.** It is written so the API can be agreed before the code is written. The names on this page may still change.

Every name is imported from `vfs`.

## Write a Policy

```python
from vfs import Decision, DeleteStep, MoveStep, Mutation, policy

@policy
async def contracts_need_a_person(step: Mutation) -> Decision: ...

@policy(name="frozen", timeout=30.0)
async def contracts_are_frozen(step: DeleteStep | MoveStep) -> Decision: ...
```

| Keyword of `@policy` | Default | Meaning |
|---|---|---|
| `name` | The function's own name | What a refusal and an interrupt call the policy |
| `timeout` | 10 seconds | How long one asking may take before the step is refused |

The function must be defined with `async def` and take one argument, annotated with a step class or a union of them. `@policy` checks this where the function is defined, before any file system exists, and raises `TypeError` when it does not hold. It returns a `Policy`, a frozen value with a `name`, a `timeout` and `covers`, the set of step classes it is shown. `await a_policy(step)` calls the function, so a policy can be tested alone.

**The type of the argument is the only thing that chooses the steps a policy sees.** A policy typed `Mutation` is never called for a read, so it adds nothing to the calls an agent makes most.

## Decision

```python
Decision.allow()
Decision.deny(reason)
```

There is no third value. A policy that needs a person awaits `interrupt` or `require_approval`, which [Jobs and Interrupts](jobs-and-interrupts.md) describes, and returns a decision once it has the answer. A `Decision` has `allowed` and `reason`. The reason of a denial is a string that is not blank, and it is carried whole into the refusal.

## Give a File System Its Policies

```python
VirtualFileSystem(..., policies=[contracts_need_a_person])

fs.add_policy(a_policy)
fs.remove_policy(a_policy)
fs.policies()                      # a tuple, in order

fs.session(authority, id, policies=[...])
```

Policies are kept and asked in the order they were added. A change to the list is seen by the next step. Two different policies may not share a name. Nothing about a policy is stored: each process holds its own list, and a session's policies are passed each time the session is asked for.

A session's policies are asked after the file system's. A session can add a policy and can never remove one, so it can ask for more review and never for less.

One ready-made policy ships.

```python
from vfs import policies

policies.review(paths=["/contracts", "/finance"])
```

It asks for a person's approval before any change under one of its paths, and before any run of a tool. It is never asked about a read.

## Step

VFS builds a step and hands it to a policy. A step is frozen: a policy reads it and cannot change it. It is built after the call's arguments and paths are checked, so a policy can trust what it reads.

| Attribute | Type | Meaning |
|---|---|---|
| `step.verb` | `str` | The verb's name, such as `"edit"`, or `"rewind"` |
| `step.paths` | Tuple of paths | Every path the step names |
| `step.subtree` | `bool` | True when the step acts on everything beneath its paths, as a delete of a directory does |
| `step.authority` | `Authority` | The caller |
| `step.via` | `Line` or `None` | The shell line that made the step, with its `text` and `cwd`, or `None` for a direct call |
| `step.touches(path)` | `bool` | True when a path the step names is `path` or beneath it, or when the step acts on everything beneath one of its paths and `path` is beneath that |
| `step.parameters()` | Mapping | The verb's arguments, so the same call can be made again |
| `step.to_payload()` | `dict` | The step as JSON-native data |

Each step class adds the arguments of its own verb. An `EditStep` has `path`, `old`, `new` and `edits`. A `WriteStep` has `path`, `content`, `entries`, `if_match` and the rest. For `GlobStep`, `GrepStep` and `SearchStep`, the folders the search is scoped to are `step.roots`.

### The Step Classes

There are 26 step classes: one for each of the 25 verbs, and `RewindStep`. `Step` is the base of them all, and `Mutation` is the base of the 16 that change something.

| Group | Classes |
|---|---|
| Under `Mutation` | `WriteStep`, `EditStep`, `DeleteStep`, `RestoreStep`, `SweepStep`, `MkdirStep`, `MkedgeStep`, `RmedgeStep`, `MoveStep`, `CopyStep`, `GrantStep`, `RevokeStep`, `SetPostureStep`, `AddMemberStep`, `RemoveMemberStep`, `RewindStep` |
| Not under `Mutation` | `ReadStep`, `StatStep`, `LsStep`, `TreeStep`, `GlobStep`, `GrepStep`, `SearchStep`, `TraverseStep`, `GrantsStep`, `RunStep` |

`RewindStep` is the one step that is no verb. It is a rewind that puts a session's files back, and a policy is asked about it once, as a whole. `RunStep` is a run of a tool. It is in no group, so a policy names it directly, as `Mutation | RunStep`.

## When a Policy Is Asked

A policy is asked once for each call of a verb, after VFS has checked the call's arguments and before any storage is asked to act.

- **Only a policy typed for the step is asked.** With no policy, or none typed for the verb, a call pays nothing more.
- **Every policy typed for the step is asked,** one after another: the file system's in the order added, then the session's. One denial refuses the step. When several deny, the result carries each one's reason.
- **For a change, the caller's rights are proven first.** A change the caller may not make is refused in the usual words and reaches no policy. This costs about four reads for a write of one file.
- **For a read, nothing is proven first.** A read is filtered by the caller's rights when it is answered.
- **No policy is asked about a step of the system authority.**
- **Each verb a shell line makes is a step,** with `via` set to the line. That includes the checks the shell makes on its way: `cat /a; echo x > /b; rm /c` makes four `stat` steps beside one read, one write and one delete. The line itself is not a step.
- **A policy is asked again when its job is resumed.** So what it asks a person, and whether it asks, must depend only on the step and on the answers it has been given.
- **A policy may call its own file system only as the system authority.**

## Refusals

A step a policy refuses changes nothing, and nothing is sent to any mount.

| When | Kind | Message |
|---|---|---|
| The policy returned `Decision.deny(reason)` | `vfs.permission_denied.policy` | `Refused by a policy: <reason> (policy <name>)` |
| The policy raised an error | `vfs.permission_denied.policy` | `the policy <name> failed, so the step was refused` |
| The policy returned something that is not a decision | `vfs.permission_denied.policy` | `the policy <name> returned no decision, so the step was refused` |
| The policy did not answer within its timeout | `vfs.permission_denied.policy` | `the policy <name> did not decide within <seconds> seconds, so the step was refused` |
| A policy called its file system as a caller other than the system authority | `vfs.invalid` | |

**A policy that fails refuses the step.** A broken guard stops the work. The message never holds an exception's text.

The line an agent reads for a denial is:

```text
ERROR /contracts/acme.md: Refused by a policy: Contracts are frozen until Friday. (policy contracts_are_frozen) — A rule of this file system refused this step, so nothing was changed. Do not retry it or make the change another way. (retry: never)
```

A "no" from a person, given through `require_approval`, is not this kind. It is `vfs.interrupt.denied`.

## Limits

| What | Value |
|---|---|
| A policy's timeout | 10 seconds, or `@policy(timeout=...)` |
| The longest one step can wait on its policies | The sum of their timeouts, since they are asked one after another |
| The number of policies | No limit |

A policy that never awaits cannot be stopped at its timeout. Every call on that file system waits while it runs, and VFS logs one `WARNING` that it held the event loop.

## For the Author of a Storage Backend

A storage that keeps grants answers one new question, `admits`, with its rights check and nothing else. It writes nothing, reads no file body and takes no lock. A storage that keeps grants and lacks it has every change a policy is typed for refused as unsupported on its mount. The three storages that ship have it.

## Choices Still Open

Each of these is decided in the spec for now, and is the project owner's to confirm.

| Choice | Decided for now |
|---|---|
| Prove a caller's rights before asking a policy about a change | Yes, at about four reads a guarded change |
| Prove them again before the policies are asked at a resume | No |
| Judge the shell line itself as a step | No. Only the verbs it makes are steps. |
| A policy's timeout | 10 seconds |
| One kind for a denial and for a failed policy | Yes, `vfs.permission_denied.policy` |
| What a policy may call | Its file system, as the system authority only |
| Ask every policy even after one denies | Yes, so the refusal gives every reason |

The full design is in `agents/2026-11-22-a-policy-judges-each-step/spec.md`.
