# How we document

This page holds the rules for the documentation of VFS. Today it covers the [glossary](../reference/glossary.md). The rules exist so that a word has one meaning, and a meaning has one word, on every page and in every docstring.

## What belongs in the glossary

A word gets a glossary term when either of these is true.

- **An outsider would not know it.** "Arm" is not a word a new reader brings with them.
- **It has a specific meaning in VFS.** "Mount" and "entry" are ordinary words, and VFS means one exact thing by each.

A term points at the code that is the thing. Where a class is the thing, the term names that class.

The list of terms grows by review. The build finds what uses a term, and it never adds a term.

## Where a term is written

A term is written in two files that sit side by side.

| File | What it holds |
|---|---|
| `documentation/reference/glossary.md` | The term's name as a second-level heading, and under it the description |
| `documentation/reference/glossary.json` | A list with one object for each term, holding `term`, `summary` and `types` |

Both files hold the same terms, each once, in the same alphabetical order.

## The parts of a term

| Part | Where it comes from | On the glossary page | Rule |
|---|---|---|---|
| Name | Both files | Yes | The same word in both files |
| Description | `glossary.md` | Yes | Plain words. It stands on its own, so its first paragraph names the term. Another term appears only as a link |
| Summary | `glossary.json` | No | One sentence of plain text, at most 25 words, ending in a full stop, with no link in it |
| Types | `glossary.json` | Yes | The class or classes that are the thing, each an exported name or a path inside the package. An empty list when the thing has no class |
| Code | The build | Yes | Every class and function, private ones included, whose docstring marks the term |
| Documentation | The build | Yes | Every page outside the reference section that links to the term |
| Related terms | The build | Yes | The terms the description links to and the terms whose descriptions link to it, in one alphabetical list |

`glossary.json` holds no other key. A new key is added on purpose, with a rule of its own.

## Using a term

**In a page, the first use of a term links to the glossary.** The page is then listed under the term's Documentation.

```
A [mount](../reference/glossary.md#mount) is attached at a path.
```

**In a docstring, a use of a term carries the `:term:` marker.** This holds for every docstring under `src/vfs/`, private ones included. The class or function is then listed under the term's Code. A marker can carry its own wording, so the second line below shows "arms" and points at the term Arm.

```
Attach a storage backend as a :term:`mount`.
Expand one pattern into its :term:`arms <arm>`.
```

**A missed link or marker fails no test.** Review finds it. "Mount", "entry" and "arm" are ordinary English words, so a word match cannot tell the term from another sense of the word.

## What the build refuses

`scripts/docs.sh check` stops on each of these, and the message names the term or the file.

- A term that is in one of the two files and not in the other, or the two files in a different order.
- A term defined twice, or out of alphabetical order.
- A term with no description, or with a description that does not name the term in its first paragraph.
- A key in `glossary.json` other than `term`, `summary` and `types`.
- A summary of more than 25 words, with no full stop at its end, or with a link in it.
- A type that is not in the source.
- A `:term:` marker, in a public or a private docstring, for a term the glossary does not define.

## Why the glossary is built this way

- **The summary is not printed on the glossary page.** The summary is what a link to the term shows, and the description is what the page shows. Each one is read alone, so each one stands on its own. A description that leaned on a sentence printed above it was tried and rejected.
- **Types holds only the classes that are the thing.** A related type is left out. `StorageBackend` is what a mount is attached to, and it is not a mount.
- **Code is found from `:term:` markers, not from type hints.** Lists of the functions that take a type and the functions that return it were built from the type hints and then removed. A marker is put where the docstring uses the word, so it says the term matters there.
- **A row under a term is a name and nothing else.** A description beside each name was mocked up from the docstrings and rejected. The name links to its own page, and the page describes it.
- **The glossary is one page and one file.** A file for each term would pass 16 files in one folder at the seventeenth term.
- **Nothing the build finds is written back into the two files.** A list that is made again on every build cannot go stale.
