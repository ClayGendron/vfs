<!--
DIÁTAXIS TYPE: Reference (information-oriented)
THE RULE: Austere, neutral, complete. Describe the machinery; do not instruct
or explain. Structure MIRRORS the code. Accuracy is the whole job.
-->

# Session

Module `vfs.session`, re-exported from `vfs`. Instances come from `VirtualFileSystem.session(authority)`.

```python
from vfs import Session
```

## Construction

`VirtualFileSystem.session(authority: Authority) -> Session`. The session holds the filesystem and the authority and nothing else. The filesystem needs no `default_authority` for a session to work.

## Attributes

| Name | Type | Meaning |
|---|---|---|
| `authority` | `Authority` | the held authority |
| `closed` | `bool` | whether `close()` has run |

## Lifecycle

| Call | Behavior |
|---|---|
| `async with fs.session(a) as s` | enters; `close()` runs on exit |
| `await s.close()` | marks the session closed; idempotent |
| `async with s` after close | raises `ValueError("the session is closed and cannot reopen; open a new one")` |

## Verbs

The session defines every verb the filesystem defines: `read`, `stat`, `ls`, `tree`, `write`, `edit`, `delete`, `restore`, `sweep`, `mkdir`, `mkedge`, `rmedge`, `move`, `copy`, `glob`, `grep`, `glean`, `graph`, `run`.

Each session verb has the filesystem verb's signature with the `authority` parameter removed: the same parameter names, kinds, defaults, and order. Each delegates to the filesystem verb with `authority=self.authority`. A session call and the direct call with the same authority return equal results and reach storage with the same authority.

## Refusal on a closed session

A verb on a closed session dispatches nothing and returns a `Result` with `ops=(<verb>,)` and one error:

| Field | Value |
|---|---|
| `kind` | `vfs.invalid` |
| `message` | `the session is closed and cannot reopen; open a new one` |
