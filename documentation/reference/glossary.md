# Glossary

The words VFS uses, and what each one means. **A word has one meaning here, and a meaning has one word.**

Terms are in alphabetical order. Each term has six parts.

| Part | What it holds | Where it comes from |
|---|---|---|
| The name | The word itself. | This page |
| The description | The full meaning: what the term is, then its rules, an example and its edges. It stands on its own. Another term from this page appears only as a link. | This page |
| Types | The class or classes that are this thing in code. "None" when the thing has no class of its own. | `glossary.json`, the file beside this page |
| Code | Every class and function whose docstring marks the term. | The docstrings |
| Documentation | Every page outside this reference section that links to the term. | The pages |
| Related terms | The terms this description links to, and the terms whose descriptions link to it. | This page |

`glossary.json` also holds a one-sentence summary of each term, of at most 25 words.

## Arm

An arm is one plain file pattern: a pattern with no `{a,b}` choices left in it. A pattern a caller writes can expand into several arms: `*.{py,md}` is two arms, `*.py` and `*.md`. An arm is a plain string and has no class of its own.

An arm is one of two kinds:

| Kind | How to tell | What it matches | Example |
|---|---|---|---|
| Name arm | It has no `/` | The name of an [entry](#entry), at any depth | `*.py` |
| Path arm | It has a `/` | The whole path of an [entry](#entry), from the top of the file tree | `src/*.py` |

One pattern may expand to at most 64 arms, the value of [`MAX_PATTERN_ARMS`](https://github.com/ClayGendron/vfs/blob/main/src/vfs/pattern_matching/glob.py). A pattern that expands past it is refused with the error "expands past the arm cap". That error is the one place a caller meets the word.

## Entry

An entry is one file or one directory in the file tree. A file is an entry with content, and a directory is an entry with none.

The path a [mount](#mount) is attached at is an entry too: an empty directory, stored in the mount above it. The directory is the entry. The storage backend attached there is the mount.

## Mount

A mount is a storage backend attached at a path in the file tree. **Every path belongs to exactly one mount: the deepest one at or above it.** With one mount at `/` and one at `/projects`, the path `/projects/app/main.py` belongs to the mount at `/projects`.

A mount added with `fs.bind()` is attached at an [entry](#entry): an empty directory that must exist first. **The directory is stored. The mount is not.** The mount lasts only while the file system is open, and `fs.unbind()` leaves the directory in place.
