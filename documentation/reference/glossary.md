# Glossary

The words VFS uses, and what each one means. **A word has one meaning here, and a meaning has one word.**

Terms are in alphabetical order. Each term is written in three parts, and the site adds three more.

| Part | What it holds | Who writes it |
|---|---|---|
| The opening sentence | What the term means, in one sentence of at most 25 words. | A person |
| The description | The rest: the rules, an example, the edges. Another term from this page appears only as a link. | A person |
| Types | The class or classes that are this thing in code. "None" when the thing has no class of its own. | A person |
| Code | Every class and function whose docstring marks the term. | The site |
| Documentation | Every page outside this reference section that links to the term. | The site |
| Related terms | The terms this definition links to, and the terms that link to it. | The site |

## Arm

One plain file pattern, with no `{a,b}` choices in it.

A pattern a caller writes can expand into several arms: `*.{py,md}` is two arms, `*.py` and `*.md`.

An arm is one of two kinds:

| Kind | How to tell | What it matches | Example |
|---|---|---|---|
| Name arm | It has no `/` | The name of an [entry](#entry), at any depth | `*.py` |
| Path arm | It has a `/` | The whole path of an [entry](#entry), from the top of the file tree | `src/*.py` |

One pattern may expand to at most 64 arms, the value of [`MAX_PATTERN_ARMS`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/pattern_matching/glob.py). A pattern that expands past it is refused with the error "expands past the arm cap". That error is the one place a caller meets the word.

- **Types:** none. An arm is a plain string.

## Entry

One file or directory in the file tree.

A directory is an entry with no content.

The path a [mount](#mount) is attached at is an entry too: an empty directory, stored in the mount above it. The directory is the entry. The storage backend attached there is the mount.

- **Types:** `Entry`

## Mount

A storage backend attached at a path in the file tree.

**Every path belongs to exactly one mount: the deepest one at or above it.** With one mount at `/` and one at `/projects`, the path `/projects/app/main.py` belongs to the mount at `/projects`.

A mount added with `fs.bind()` is attached at an [entry](#entry): an empty directory that must exist first. **The directory is stored. The mount is not.** The mount lasts only while the file system is open, and `fs.unbind()` leaves the directory in place.

- **Types:** `MountInfo`, `base.Binding`
