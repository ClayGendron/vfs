# Glossary

The words VFS uses, and what each one means. **A word has one meaning here, and a meaning has one word.**

Terms are in alphabetical order. Each term has four parts:

| Part | What it holds |
|---|---|
| The definition | One or two plain sentences. Another term from this page appears only as a link. |
| Seen by callers | Whether the word appears in the API, in a result, or in an error message. |
| In code | The classes and functions that define the term. A name in the public API links to its reference page, and any other name links to its file. |
| Instead of | Words that are not used for this meaning. |

## Arm

One plain file pattern, with no `{a,b}` choices in it. A pattern a caller writes can expand into several arms: `*.{py,md}` is two arms, `*.py` and `*.md`.

An arm is one of two kinds:

| Kind | How to tell | What it matches | Example |
|---|---|---|---|
| Name arm | It has no `/` | The name of an [entry](#entry), at any depth | `*.py` |
| Path arm | It has a `/` | The whole path of an [entry](#entry), from the top of the file tree | `src/*.py` |

- **Seen by callers:** in one error message. A pattern that expands past 64 arms is refused with "expands past the arm cap".
- **In code:**
    - [`expand_pattern`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/pattern_matching/glob.py) turns one pattern into its arms.
    - [`MAX_PATTERN_ARMS`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/pattern_matching/glob.py) is the most arms one pattern may expand to.
    - [`compile_filter`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/pattern_matching/glob.py) decides whether an arm is a name arm or a path arm.
- **Instead of:** member, admission.

## Entry

One file or directory in the file tree. A directory is an entry with no content.

The path a [mount](#mount) is attached at is an entry too: an empty directory, stored in the mount above it. The directory is the entry. The storage backend attached there is the mount.

- **Seen by callers:** yes. `Entry` is the record a caller builds to write a file, and `fs.write()` takes a list of them.
- **In code:**
    - [`Entry`](python-api/entry.md#vfs.Entry) is the whole record of one file or directory.
    - [`ObjectKind`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/paths.py) names the two kinds an entry can be: `file` and `directory`.
- **Instead of:** none.

## Mount

A storage backend attached at a path in the file tree. **Every path belongs to exactly one mount: the deepest one at or above it.**

With one mount at `/` and one at `/projects`, the path `/projects/app/main.py` belongs to the mount at `/projects`.

A mount added with `fs.bind()` is attached at an [entry](#entry): an empty directory that must exist first. **The directory is stored. The mount is not.** The mount lasts only while the file system is open, and `fs.unbind()` leaves the directory in place.

- **Seen by callers:** yes. `fs.bind()` attaches a mount, `fs.unbind()` removes one, and `fs.mounts()` lists them.
- **In code:**
    - [`Binding`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/base.py) is one mount: a storage backend, the path it is attached at, and its policy.
    - [`AsyncVirtualFileSystem.bind`](python-api/async-virtual-file-system.md#vfs.AsyncVirtualFileSystem.bind) attaches a mount.
    - [`MountInfo`](python-api/mounts.md#vfs.MountInfo) is one row of what `fs.mounts()` returns.
    - [`StorageBackend`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/storage/protocol.py) is what a mount attaches.
- **Instead of:** entry (for the mount itself), key.
