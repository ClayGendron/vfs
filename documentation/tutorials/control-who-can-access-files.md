# Control Who Can Access Files

In this tutorial, you will make a file system private and then give two people different access to it. You will see what each person can list, read, and write, and what happens when they reach for a file they were not given.

It takes about ten minutes and runs entirely in memory in a Jupyter notebook. By the end, you will know how to close a file system, how to grant access to a folder, and how to run calls as a named person.

## Before You Begin

You need Python 3.11 or later with `vfs-py` installed, and you should have finished [Build Your First File System](build-your-first-file-system.md).

Each Python block below is one notebook cell, and the block after it shows what that cell prints.

## Step 1: Create a File System with Two Folders

Open a new notebook and run this in the first cell.

```python
from vfs import VirtualFileSystem

fs = VirtualFileSystem()

fs.write(
    path="/handbook/welcome.md",
    content="Welcome to the team.",
    parents=True,
)
fs.write(
    path="/finance/salaries.md",
    content="Salaries are reviewed every March.",
    parents=True,
)
```

```text
write success: 1 file

  created /finance/salaries.md
```

The cell prints the result of the second write. You now have a handbook that everyone should read and a finance folder that only some people should see. The `parents=True` argument creates each folder along the way.

## Step 2: Close the File System

A new file system is open, which means anyone can read and write anything in it. Close it.

```python
from vfs import Authority

system = Authority.system()

fs.set_posture("/", "none", authority=system)
```

```text
| path_prefix | principal_id | level | granted_by | granted_at                       |
| ----------- | ------------ | ----- | ---------- | -------------------------------- |
| /           | *            | none  | system     | 2026-11-13 01:19:47.493085+00:00 |
```

The time in the last column will be your own. This row says that everyone, written as `*`, now has the access level `none` from the root down. **From here on, nobody gets in without a grant.**

The `system` authority stands for your own application code. It can always see and change everything, so use it for setup like this and never hand it to a user.

Try a call with no name attached, as you made in Step 1.

```python
fs.read("/handbook/welcome.md")
```

```text
ERROR /handbook/welcome.md: Unauthenticated — This mount's posture needs a name: open a session with an authority, or configure a default. (retry: never)
```

The file system now refuses a caller it cannot name.

## Step 3: Create Two People

Open a session for each of two people, Ada and Grace.

```python
from vfs import Principal

ada = fs.open_session(Authority.of(Principal("ada")))
grace = fs.open_session(Authority.of(Principal("grace")))
```

This cell prints nothing. A session is the file system as one person sees it. It has the same calls as `fs`, and every call it makes carries that person's name.

VFS does not check passwords. Your application verifies who a person is, and then it tells VFS the name.

Neither person has a grant yet, so try to read as Grace.

```python
grace.read("/handbook/welcome.md")
```

```text
ERROR /handbook: Not found (target /handbook/welcome.md) — Check the path with ls or glob, or create the entry first. (retry: never)
```

To Grace, the file does not exist.

## Step 4: Grant Access

Give Ada read access to both folders, and give Grace read access to the handbook only.

```python
fs.grant("/handbook", "ada", "read", authority=system)
fs.grant("/finance", "ada", "read", authority=system)
fs.grant("/handbook", "grace", "read", authority=system)
```

```text
| path_prefix | principal_id | level | granted_by | granted_at                       |
| ----------- | ------------ | ----- | ---------- | -------------------------------- |
| /handbook   | grace        | read  | system     | 2026-11-13 01:19:47.617781+00:00 |
```

The cell prints the last of the three grants. A grant on a folder covers everything inside it.

## Step 5: See What Each Person Sees

List the root as Ada.

```python
ada.ls("/")
```

```text
/finance
/handbook
```

Then list the root as Grace.

```python
grace.ls("/")
```

```text
/handbook
```

It is the same file system and the same call, with two different answers. Now have each of them read the finance file. Ada first.

```python
ada.read("/finance/salaries.md")
```

```text
Salaries are reviewed every March.
```

Then Grace.

```python
grace.read("/finance/salaries.md")
```

```text
ERROR /finance: Not found (target /finance/salaries.md) — Check the path with ls or glob, or create the entry first. (retry: never)
```

Notice that the error is "Not found", and it is the same error a missing file gives. **A file that a person cannot see does not exist for them.** Grace cannot learn that there is a finance folder at all.

## Step 6: Tell Reading from Writing

Grace can read the handbook. Have her try to change it.

```python
grace.write(path="/handbook/welcome.md", content="Welcome!")
```

```text
write errors:
  ERROR /handbook/welcome.md: Permission denied — Target a path this caller may access, or request access. (retry: never)
```

This time the error is "Permission denied". Grace can see the file, so VFS tells her plainly that she may not write it.

Raise her access on the handbook to `read_write`, and have her try again.

```python
fs.grant("/handbook", "grace", "read_write", authority=system)

grace.write(path="/handbook/welcome.md", content="Welcome!")
```

```text
write success: 1 file

  updated /handbook/welcome.md
```

The write goes through. Her access to the finance folder has not changed.

## What You Did

You closed a file system and opened it again for two people, one folder at a time.

- `fs.set_posture` set what everyone gets by default. You set it to `none`.
- `fs.grant` gave one person a level of access to one folder.
- `fs.open_session` ran calls as a named person.

**Access is decided on every call, by who is asking.** A person sees only what they were granted, and everything else does not exist for them.

The same checks apply to the CLI and to an AI agent. An AI agent works through a session too, so it sees only what the person it acts for may see.

## Where to Go Next

To understand how VFS checks each call, read [How VFS Enforces Governance](../overview.md#how-vfs-enforces-governance) in the Overview.
