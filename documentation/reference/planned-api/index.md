# Planned API

This section lists the API of two features that are designed and not yet built. One is a [job](../glossary.md#job) that is interrupted to ask a person and resumed with the answer. The other is a [session](../glossary.md#session) that remembers what an agent has read, works in [turns](../glossary.md#turn), and can be rewound or forked.

> **Nothing in this section is built.** The pages are written so the API can be agreed before the code is written. Every name here may still change. The pages under [Python API](../python-api/index.md) describe the code as it is today.

## The Pages

| Page | What it covers |
|---|---|
| [Etags and Preconditions](etags-and-preconditions.md) | `etag` on every row, and `if_match` on `write`, `edit`, `delete`, `move` and `restore` |
| [Sessions and Turns](sessions-and-turns.md) | `fs.session`, what a session remembers, `start_turn`, `rewind`, `fork`, and putting files back |
| [Policies and Steps](policies-and-steps.md) | `@policy`, `Decision`, the step classes, and when a policy is asked |
| [Jobs and Interrupts](jobs-and-interrupts.md) | `interrupt`, `require_approval`, the answer schemas, `resume`, `jobs`, and a denial or a cancel |

Three guides show the API in use, and one page explains the ideas behind it.

- [Keep a Session for Each Conversation](../../how-to/keep-a-session-for-each-conversation.md)
- [Rewind a Conversation and Put Its Files Back](../../how-to/rewind-a-conversation-and-put-its-files-back.md)
- [Interrupt a Job and Ask a Person](../../how-to/interrupt-a-job-and-ask-a-person.md)
- [How Jobs, Sessions and Turns Fit Together](../../explanation/how-jobs-sessions-and-turns-fit-together.md)

## Every New Name

Each name is imported from `vfs`.

| For | Names |
|---|---|
| Etags | `Etag`, `ABSENT`, `EtagMint`, and the arguments `if_match` and `if_matches` |
| Sessions | `fs.session`, `fs.sessions`, `fs.remove_session`, `session.exists`, `SessionInfo`, `SessionPage`, and the argument `session_lifetime` |
| Turns | `session.start_turn`, `session.turn`, `session.turns`, `session.rewind`, `session.fork`, `session.parent`, `Turn`, `Rewind` |
| Policies | `policy`, `Policy`, `Decision`, `policies.review`, `fs.add_policy`, `fs.remove_policy`, `fs.policies`, and the argument `policies` |
| Steps | `Step`, `Mutation`, `Line`, and 26 step classes such as `EditStep`, `DeleteStep`, `RunStep` and `RewindStep` |
| Jobs | `interrupt`, `require_approval`, `Approval`, `Choice`, `Cancel`, `fs.resume`, `fs.jobs`, `session.resume`, `session.jobs`, `Job`, `Interrupt`, `StepPreview`, `JobPage`, and the argument `job_lifetime` |
| Principals | `Principal(..., name=)` and `Authority.system(name=)` |

## Every New Error Kind

| Kind | When |
|---|---|
| `vfs.conflict.changed` | A session's change is refused because the file changed after the agent was shown it |
| `vfs.conflict.unread` | A session's change is refused because the agent was never shown the file |
| `vfs.permission_denied.policy` | A policy denied a step, or failed |
| `vfs.interrupted` | A call was stopped to ask a person, and its job is waiting |
| `vfs.interrupt.denied` | The person who was asked said no |
| `vfs.interrupt.cancelled` | A waiting job was cancelled |

## What Is Removed

| Removed | Use instead |
|---|---|
| `fs.open_session(authority)`, `session.close()`, and `with fs.open_session(...)` | `fs.session(authority, id)`. There is nothing to close. |
| `write(if_version=...)` and `write(if_versions=...)` | `if_match` and `if_matches`, with the row's `etag` |

## What Is Not Designed Yet

- **Tools.** A function an agent can run, marked with `@tool`. The rules a tool must follow when it interrupts are written down, and the rest is not designed.
- **Sessions and jobs over MCP.** The session id and the job id will be ordinary arguments of a call.
- **A private copy of the files for a fork.** A fork shares the files with its parent.

## Where the Design Is Written

The design is nine specs under `agents/` in the repository. `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md` is their map. It says what each one decides, the order they are built in, and what they share.
