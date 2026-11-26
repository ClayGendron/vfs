# Vids and Preconditions

An [vid](../glossary.md#vid) is a short value on a row that names one file at one version. A change can require it, so that the change is made only when the file is still the one that was read. This page lists every name, argument and refusal of that design.

> **This page describes an API that is designed and not yet built.** It is written so the API can be agreed before the code is written. The names on this page may still change.

## The Vid

Every row that carries a `version` also carries a `vid`.

```python
row = fs.stat("/notes/plan.md", authority=ada).observations[0]
row.version, row.vid
```

```text
(3, '9f2c41d07ab35e6610c4')
```

| Name | Import | What it is |
|---|---|---|
| `Observation.vid` | on every row | `Vid` or `None`. Set whenever `version` is set, whatever `columns=` names. |
| `Vid` | `from vfs import Vid` | A string of twenty lowercase hexadecimal characters. |
| `ABSENT` | `from vfs import ABSENT` | Given in place of a vid. It requires that the path holds nothing. |
| `VidMint` | `from vfs import VidMint` | For the author of a storage backend, which mints the vids of its own rows. |

**Two vids are equal when, and only when, they name the same file at the same version in the same mount.** A vid is compared and never taken apart. No function turns it back into a version number, and it grants no right to anything.

A version alone does not do this job. When a file is moved away and another file is written at its old path, the new file can stand at the version a caller saw. A change guarded by the version would then overwrite a file the caller never read. The vid names the file as well as the version, so that change is refused.

Which state the vid on a result row names depends on the verb.

| Verb | The vid names |
|---|---|
| `read`, `stat`, `ls`, `tree`, `glob`, `grep`, `search`, `traverse` | The row as it was read |
| `write`, `edit`, `mkdir` | The row after the call |
| `move`, `copy`, `restore` | The row after the call, at its new path |
| `delete`, `sweep` | The row as it was before the call |

A row with no version carries no vid. That covers an edge row, a grant row, and the rows of a storage that does not issue vids.

## Require a Vid

`write`, `edit`, `delete`, `move` and `restore` each take `if_vid` for one path and `if_vids` for many. Both are on the asynchronous and the synchronous file system. A session has neither: it remembers the vid of each file it was shown and fills it in.

```python
write(entries=None, *, path=None, content=None, data=None,
      if_vid=None, if_vids=None,
      if_absent=False, append=False, parents=False,
      authority=None)

edit(path=None, old=None, new=None, edits=None,
     observations=None, replace_all=False, *,
     if_vid=None, if_vids=None, authority=None)

delete(path=None, observations=None, *, cascade=True,
       if_vid=None, if_vids=None, authority=None)

move(src=None, dest=None, moves=None, *,
     if_vid=None, if_vids=None, authority=None)

restore(path=None, observations=None, *,
        if_vid=None, if_vids=None, authority=None)
```

| Argument | Goes with | Meaning |
|---|---|---|
| `if_vid` | A single path | The vid the row at that path must have. `None`, the default, requires nothing. |
| `if_vids` | A batch | A mapping from a path to the vid required there. A path with no key has no precondition. |

For a `move`, the vid names the row at the source. The destination takes no precondition. For a `restore`, it names the deleted row the restore would bring back.

A caller that reads a file and changes it later passes the vid back.

```python
row = fs.read("/notes/plan.md", authority=ada).observations[0]
fs.edit(
    "/notes/plan.md",
    old="Friday",
    new="Monday",
    if_vid=row.vid,
    authority=ada,
)
```

A batch requires each of its rows the same way.

```python
rows = fs.glob("/notes/*.md", authority=ada).observations
fs.delete(
    observations=rows,
    if_vids={row.path: row.vid for row in rows},
    authority=ada,
)
```

Rows passed back as `observations=` are used for their paths only. Their own vids are ignored, so passing rows never implies a precondition. A batch of 10,000 entries with a precondition on each is a supported call and adds no statement.

`ABSENT` in place of a vid requires that the path holds nothing. On a single `write` it is another spelling of `if_absent=True`. In `if_vids` it makes one entry of a batch create-only while the others replace what is there.

The precondition is checked inside the transaction that makes the change, so no other caller can change the file between the check and the write.

### A Directory

A directory's vid is new when a direct child is made, deleted, renamed, or moved in or out. It stays the same for any change deeper down and for a change to a child's body. So a `delete` of a directory that requires its vid is refused when the directory's own listing has changed since it was read.

## What Moves a Vid

| Event | The vid |
|---|---|
| A write of a new body, an edit, an append | New |
| A write of the body the file already holds | The same |
| A move of the file | New, at the new path |
| A delete, then a restore | New |
| A delete, then a write at the same path | New |
| A copy | The copy has a vid of its own |
| A move, delete or restore of a directory above the file | The same |
| A grant, a posture change, an index pass | The same |
| The same storage mounted at another path, or opened by another process | The same |
| Another storage mounted at the path | No vid held for that path matches |

## Refusals

A refusal changes nothing. In a batch, every stale row is listed and the batch changes nothing on that mount.

| When | Kind | What the result carries |
|---|---|---|
| The vid required is not the vid of the row at the path | `vfs.conflict` | The `version` and the `vid` of the row that is there now |
| A required vid at a path a directory now holds | `vfs.conflict` | The same, for the directory |
| `ABSENT` on a `write`, over a file or directory that exists | `vfs.exists` | The `version`, `content_hash` and `vid` of what is there |
| A required vid where nothing is | `vfs.not_found` | A hint when the file is in the trash |
| A value that is not a vid, or `if_vid` used with a batch | `vfs.invalid` | Nothing. It is refused before any storage is called. |
| A precondition sent to a mount whose storage issues no vid | `vfs.unsupported` | Nothing |

An agent reads this line for a conflict.

```text
ERROR /notes/plan.md: Conflict: the vid required is not the vid of what is stored — Read the entry again, then retry. (retry: refresh)
```

**Read the file before sending the vid from a refusal back.** The refusal carries the current vid so that a caller who already holds that state can go on. A caller who sends it back without reading replaces the very change the refusal reported.

This design adds no error kind.

## What Is Removed

| Removed | Use instead |
|---|---|
| `write(if_version=...)` | Read the row and pass `if_vid=row.vid` |
| `write(if_versions={...})` | `if_vids={path: vid}` |
| The rule that one call cannot mix create-only and plain entries | `ABSENT` on the entries that must be new |

`version` stays on every row. It is still the count of a file's changes.

## Choices Still Open

Each of these is decided in the spec for now, and is the project owner's to confirm.

| Choice | Decided for now |
|---|---|
| Keep `if_version` beside `if_vid` | No. `if_version` and `if_versions` are removed. |
| Put the vid on every listing row | Yes. It costs about 30 bytes a row. |
| Let the batch forms of `edit`, `delete`, `move` and `restore` take `if_vids` | Yes |
| Carry the current vid in a conflict | Yes, beside the version |
| Refuse a vid from another mount as invalid | No. It is a conflict, like any stale vid. |
| Keep `if_absent` beside `ABSENT` | Yes |

The full design is in `agents/2026-11-22-a-row-carries-a-vid-and-a-change-can-require-it/spec.md`.
