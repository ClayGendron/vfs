# Glossary

The words VFS uses, and what each one means. **A word has one meaning here, and a meaning has one word.**

Terms are in alphabetical order. Each term has six parts.

| Part | What it holds |
|---|---|
| Name | The word itself. |
| Description | The full meaning. It says what the term is, then gives its rules, an example and its edges. It stands on its own. Another term from this page appears only as a link. |
| Types | The class or classes that are this thing in code. "None" when the thing has no class of its own. |
| Code | Every class and function whose docstring marks the term. |
| Documentation | Every page outside this reference section that links to the term. |
| Related terms | The terms this description links to, and the terms whose descriptions link to it. |

## Arm

An arm is one plain file pattern, a pattern with no `{a,b}` choices left in it. A pattern a caller writes can expand into several arms. For example, `*.{py,md}` is two arms, `*.py` and `*.md`. An arm is a plain string and has no class of its own.

An arm is one of two kinds.

| Kind | How to tell | What it matches | Example |
|---|---|---|---|
| Name arm | It has no `/` | The name of an [entry](#entry), at any depth | `*.py` |
| Path arm | It has a `/` | The whole path of an [entry](#entry), from the top of the file tree | `src/*.py` |

One pattern may expand to at most 64 arms, the value of [`MAX_PATTERN_ARMS`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/pattern_matching/glob.py). A pattern that expands past it is refused with the error "expands past the arm cap". That error is the one place a caller meets the word.

## Entry

An entry is one file or one directory in the file tree. A file is an entry with content, and a directory is an entry with none.

The path a [mount](#mount) is attached at is an entry too. It is an empty directory, stored in the mount above it. The directory is the entry. The storage backend attached there is the mount.

## Kernel

The kernel is the object that holds the file tree and answers every call on it. For each call it finds the [mount](#mount) that holds the path, checks the call against the permissions of that mount, and sends the call to the storage backend of that mount with the name of the caller. The storage backend decides what that caller may see or change. **Every call passes through the kernel, so no call reaches a storage backend unchecked.**

In code the kernel is `AsyncVirtualFileSystem`, with calls you `await`. `VirtualFileSystem` is the same kernel with plain calls. One kernel is one file tree. A kernel never holds another kernel, and two file trees are joined only through a storage backend.

The name follows the kernel of an operating system, which every call on a file passes through.

## Mount

A mount is a storage backend attached at a path in the file tree. **Every path belongs to exactly one mount, the deepest one at or above it.** With one mount at `/` and one at `/projects`, the path `/projects/app/main.py` belongs to the mount at `/projects`.

A mount is attached at an [entry](#entry), an empty directory. `fs.add_mount()` makes that directory when it is absent. **The directory is stored. The mount is not.** The mount lasts only while the file system is open. `fs.remove_mount()` removes the mount and then its directory.

While a mount is attached, its path shows the top of the mounted storage and never the directory beneath it. `fs.ls("/")` and `fs.stat("/projects")` return the same row for `/projects`. The name of a mount is never hidden from a caller who can list the directory it is in.

Adding or removing a mount is a write at its path. A read-only mount takes no new mount beneath it and loses none. The caller must also hold `read_write` at that path, as for a change to who can access it. `fs.add_mount(..., posture=...)` sets the level that everyone holds at the root of the mounted storage, before the mount can be reached. A posture set deeper in that storage stays.
