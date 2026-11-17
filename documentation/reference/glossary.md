# Glossary

The words VFS uses, and what each one means. **A word has one meaning here, and a meaning has one word.**

Terms are in alphabetical order. Each term has five parts:

| Part | What it holds |
|---|---|
| The definition | One or two plain sentences. Another term from this page appears only as a link. |
| Types | The classes that are this thing in code. "None" when the thing has no class of its own. |
| Producers | The functions that create one or return one. |
| Consumers | The functions that take one or act on one. |
| Instead of | Words that are not used for this meaning. |

A name in the public API links to its reference page, and any other name links to its file.

## Arm

One plain file pattern, with no `{a,b}` choices in it. A pattern a caller writes can expand into several arms: `*.{py,md}` is two arms, `*.py` and `*.md`.

An arm is one of two kinds:

| Kind | How to tell | What it matches | Example |
|---|---|---|---|
| Name arm | It has no `/` | The name of an [entry](#entry), at any depth | `*.py` |
| Path arm | It has a `/` | The whole path of an [entry](#entry), from the top of the file tree | `src/*.py` |

One pattern may expand to at most 64 arms, the value of [`MAX_PATTERN_ARMS`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/pattern_matching/glob.py). A pattern that expands past it is refused with the error "expands past the arm cap". That error is the one place a caller meets the word.

- **Types:** none. An arm is a plain string.
- **Producers:**
    - [`expand_pattern`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/pattern_matching/glob.py) turns one pattern into its arms.
- **Consumers:**
    - [`compile_filter`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/pattern_matching/glob.py) decides whether an arm is a name arm or a path arm.
- **Instead of:** member, admission.

## Entry

One file or directory in the file tree. A directory is an entry with no content.

The path a [mount](#mount) is attached at is an entry too: an empty directory, stored in the mount above it. The directory is the entry. The storage backend attached there is the mount.

- **Types:**
    - [`Entry`](python-api/entry.md#vfs.Entry) is the whole record of one file or directory. A caller builds one to write a file.
    - [`ObjectKind`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/paths.py) names the two kinds an entry can be: `file` and `directory`.
- **Producers:**
    - [`Entry.with_content`](python-api/entry.md#vfs.Entry.with_content) returns a copy of an entry with its content replaced.
- **Consumers:**
    - [`AsyncVirtualFileSystem.write`](python-api/async-virtual-file-system.md#vfs.AsyncVirtualFileSystem.write) writes one file or a batch of entries.
- **Instead of:** none.

## Mount

A storage backend attached at a path in the file tree. **Every path belongs to exactly one mount: the deepest one at or above it.**

With one mount at `/` and one at `/projects`, the path `/projects/app/main.py` belongs to the mount at `/projects`.

A mount added with `fs.bind()` is attached at an [entry](#entry): an empty directory that must exist first. **The directory is stored. The mount is not.** The mount lasts only while the file system is open, and `fs.unbind()` leaves the directory in place.

- **Types:**
    - [`MountInfo`](python-api/mounts.md#vfs.MountInfo) is one row of what `fs.mounts()` returns.
    - [`Binding`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/base.py) is one mount: a storage backend, the path it is attached at, and its policy.
    - [`StorageBackend`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/storage/protocol.py) is what a mount attaches.
- **Producers:**
    - [`AsyncVirtualFileSystem.bind`](python-api/async-virtual-file-system.md#vfs.AsyncVirtualFileSystem.bind) attaches a mount at a path.
    - [`AsyncVirtualFileSystem.mounts`](python-api/async-virtual-file-system.md#vfs.AsyncVirtualFileSystem.mounts) lists the mounts.
- **Consumers:**
    - [`AsyncVirtualFileSystem.unbind`](python-api/async-virtual-file-system.md#vfs.AsyncVirtualFileSystem.unbind) removes a mount and leaves its directory in place.
- **Instead of:** entry (for the mount itself), key.
