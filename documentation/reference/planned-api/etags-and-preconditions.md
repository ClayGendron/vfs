# Etags and Preconditions

An [etag](../glossary.md#etag) is a short value on a row that names one file at one version. A change can require it, so that the change is made only when the file is still the one that was read. This page lists every name, argument and refusal of that design.

> **This page describes an API that is designed and not yet built.** It is written so the API can be agreed before the code is written. The names on this page may still change.

## The Etag

Every row that carries a `version` also carries an `etag`.

```python
row = fs.stat("/notes/plan.md", authority=ada).observations[0]
row.version, row.etag
```

```text
(3, '9f2c41d07ab35e6610c4')
```

| Name | Import | What it is |
|---|---|---|
| `Observation.etag` | on every row | `Etag` or `None`. Set whenever `version` is set, whatever `columns=` names. |
| `Etag` | `from vfs import Etag` | A string of twenty lowercase hexadecimal characters. |
| `ABSENT` | `from vfs import ABSENT` | Given in place of an etag. It requires that the path holds nothing. |
| `EtagMint` | `from vfs import EtagMint` | For the author of a storage backend, which mints the etags of its own rows. |

**Two etags are equal when, and only when, they name the same file at the same version in the same mount.** An etag is compared and never taken apart. No function turns it back into a version number, and it grants no right to anything.

A version alone does not do this job. When a file is moved away and another file is written at its old path, the new file can stand at the version a caller saw. A change guarded by the version would then overwrite a file the caller never read. The etag names the file as well as the version, so that change is refused.

Which state the etag on a result row names depends on the verb.

| Verb | The etag names |
|---|---|
| `read`, `stat`, `ls`, `tree`, `glob`, `grep`, `search`, `traverse` | The row as it was read |
| `write`, `edit`, `mkdir` | The row after the call |
| `move`, `copy`, `restore` | The row after the call, at its new path |
| `delete`, `sweep` | The row as it was before the call |

A row with no version carries no etag. That covers an edge row, a grant row, and the rows of a storage that does not issue etags.

## Require an Etag

`write`, `edit`, `delete`, `move` and `restore` each take `if_match` for one path and `if_matches` for many. Both are on the asynchronous and the synchronous file system and on a session.

```python
write(entries=None, *, path=None, content=None, data=None,
      if_match=None, if_matches=None,
      if_absent=False, append=False, parents=False, authority=None)

edit(path=None, old=None, new=None, edits=None, observations=None, replace_all=False, *,
     if_match=None, if_matches=None, authority=None)

delete(path=None, observations=None, *, cascade=True,
       if_match=None, if_matches=None, authority=None)

move(src=None, dest=None, moves=None, *,
     if_match=None, if_matches=None, authority=None)

restore(path=None, observations=None, *,
        if_match=None, if_matches=None, authority=None)
```

| Argument | Goes with | Meaning |
|---|---|---|
| `if_match` | A single path | The etag the row at that path must have. `None`, the default, requires nothing. |
| `if_matches` | A batch | A mapping from a path to the etag required there. A path with no key has no precondition. |

For a `move`, the etag names the row at the source. The destination takes no precondition. For a `restore`, it names the deleted row the restore would bring back.

A caller that reads a file and changes it later passes the etag back.

```python
row = fs.read("/notes/plan.md", authority=ada).observations[0]
fs.edit("/notes/plan.md", old="Friday", new="Monday", if_match=row.etag, authority=ada)
```

A batch requires each of its rows the same way.

```python
rows = fs.glob("/notes/*.md", authority=ada).observations
fs.delete(observations=rows, if_matches={row.path: row.etag for row in rows}, authority=ada)
```

Rows passed back as `observations=` are used for their paths only. Their own etags are ignored, so passing rows never implies a precondition. A batch of 10,000 entries with a precondition on each is a supported call and adds no statement.

`ABSENT` in place of an etag requires that the path holds nothing. On a single `write` it is another spelling of `if_absent=True`. In `if_matches` it makes one entry of a batch create-only while the others replace what is there.

The precondition is checked inside the transaction that makes the change, so no other caller can change the file between the check and the write.

### A Directory

A directory's etag is new when a direct child is made, deleted, renamed, or moved in or out. It stays the same for any change deeper down and for a change to a child's body. So a `delete` of a directory that requires its etag is refused when the directory's own listing has changed since it was read.

## What Moves an Etag

| Event | The etag |
|---|---|
| A write of a new body, an edit, an append | New |
| A write of the body the file already holds | The same |
| A move of the file | New, at the new path |
| A delete, then a restore | New |
| A delete, then a write at the same path | New |
| A copy | The copy has an etag of its own |
| A move, delete or restore of a directory above the file | The same |
| A grant, a posture change, an index pass | The same |
| The same storage mounted at another path, or opened by another process | The same |
| Another storage mounted at the path | No etag held for that path matches |

## Refusals

A refusal changes nothing. In a batch, every stale row is listed and the batch changes nothing on that mount.

| When | Kind | What the result carries |
|---|---|---|
| The etag required is not the etag of the row at the path | `vfs.conflict` | The `version` and the `etag` of the row that is there now |
| A required etag at a path a directory now holds | `vfs.conflict` | The same, for the directory |
| `ABSENT` on a `write`, over a file or directory that exists | `vfs.exists` | The `version`, `content_hash` and `etag` of what is there |
| A required etag where nothing is | `vfs.not_found` | A hint when the file is in the trash |
| A value that is not an etag, or `if_match` used with a batch | `vfs.invalid` | Nothing. It is refused before any storage is called. |
| A precondition sent to a mount whose storage issues no etag | `vfs.unsupported` | Nothing |

The line an agent reads for a conflict is:

```text
ERROR /notes/plan.md: Conflict: the etag required is not the etag of what is stored — Read the entry again, then retry; a change that requires an etag takes the one that read returns. (retry: refresh)
```

**Read the file before sending the etag from a refusal back.** The refusal carries the current etag so that a caller who already holds that state can go on. A caller who sends it back without reading replaces the very change the refusal reported.

This design adds no error kind.

## What Is Removed

| Removed | Use instead |
|---|---|
| `write(if_version=...)` | Read the row and pass `if_match=row.etag` |
| `write(if_versions={...})` | `if_matches={path: etag}` |
| The rule that one call cannot mix create-only and plain entries | `ABSENT` on the entries that must be new |

`version` stays on every row. It is still the count of a file's changes.

## Choices Still Open

Each of these is decided in the spec for now, and is the project owner's to confirm.

| Choice | Decided for now |
|---|---|
| Keep `if_version` beside `if_match` | No. `if_version` and `if_versions` are removed. |
| Put the etag on every listing row | Yes. It costs about 30 bytes a row. |
| Let the batch forms of `edit`, `delete`, `move` and `restore` take `if_matches` | Yes |
| Carry the current etag in a conflict | Yes, beside the version |
| Refuse an etag from another mount as invalid | No. It is a conflict, like any stale etag. |
| Keep `if_absent` beside `ABSENT` | Yes |

The full design is in `agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/spec.md`.
