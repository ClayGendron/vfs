# Glossary rules: handoff

## Goal

The glossary in `documentation/reference/glossary.md` has written rules, and the docs build holds each rule that can be checked. The list of terms grows under review; no term is invented by the build.

## Decisions, each with its reason

1. A use of a glossary term in a page or a docstring is found by a script and fixed by review; it fails no test. Reason: glossary words such as "mount", "entry" and "arm" are ordinary English words, so a word match cannot tell a use of the term from another sense.
2. The finder reads every documentation page and every docstring under `src/vfs/`, private ones included.
3. In a page, the first use of a term links to the glossary. In a docstring, a use carries the `:term:` marker, which the export turns into a link.
4. Each term has three labelled parts after its definition: Types, Producers, Consumers. Types are the classes that are the thing in code. A producer creates or returns the thing. A consumer takes it or acts on it. Reason: "Seen by callers" was not understood on first reading, and "callers" already means the people and agents that use VFS.
5. A part holds names only, in backticks: an exported name or a path inside the package. No description is written or shown beside a name; the name links to its page, which describes it. Reason: a description beside each name was mocked up from the docstrings and rejected.
6. A name the page writes must be in the source, and a term names at least one. Reason: a rename must not leave the glossary pointing at nothing.
7. The build adds producers and consumers from type hints: a public function whose return hint names one of the term's types is a producer, and one whose parameter hints do is a consumer. A name the page writes is never also listed from a hint. Reason: the lists cannot go stale, and a hint cannot see a concept with no class (an arm is a string) or a function whose signature does not name the type (`bind` takes a storage and a path).
8. Types holds only classes that are the thing, never a related type. Reason: every function that takes a related type would be listed as a consumer of the term. `ObjectKind` left Entry and `StorageBackend` left Mount for this reason.
9. "Seen by callers" and "Instead of" are dropped. A fact only the first carried, such as a term that appears in one error message, moves into the definition.
10. "Referenced in" is drawn by the docs app beneath each term, folded, grouped into Pages and Python API. It is built from page links to the glossary and from `:term:` markers, and is never written into `glossary.md`. Reason: the app refuses raw HTML in a page, and a list rebuilt on every build cannot go stale.
11. The glossary is one structured Markdown page and the export checks its shape. Reason: a file per term would pass 16 children at the seventeenth term.
12. A private object is documented on a page under `documentation/maintainers/`, pulled in with the same `::: vfs.path` line the API pages use. The glossary links to that page and never to a source file on GitHub. Reason: a `:term:` marker in a private docstring needs a page to be listed from.
13. The page shows no tag for how a name was found. An "Internal" badge beside a private name and an "Also on" line for a method that exists on several classes were shown in the mock-up and are not yet ruled on.

## Built on the branch `glossary-rules`

- `46e9aacb`, `0ec4529b`, `6d55fa9a`: the export refuses a term that is missing a part, has parts out of order, has an unknown or doubled part, has no definition, is out of alphabetical order or is defined twice. A heading inside a code fence is not a term.
- `803b501c`: a page under `maintainers/` pulls in a private object; the export describes it under `internals`, keyed by its dotted path. Refused: a private object on any other page, a public object on a maintainer page, a path not in the source, the same object on two maintainer pages.
- `6d55fa9a` and the commit after it: the export writes `glossary`, one entry per term: its anchor, and under `types`, `producers` and `consumers` a list of `{name, id, page, public, generated}`. Decisions 5 to 8 are held there. The three terms in `glossary.md` are rewritten to names only.

`tests/scripts/test_docs_export.py` passes, 44 tests. `scripts/docs.sh check` has not been run on this branch, and the docs app does not read `glossary` or `internals` yet.

## What the export gives for the three terms today

- Arm: producer `pattern_matching.glob.expand_pattern`, consumer `pattern_matching.glob.compile_filter`, both written by hand, both private and on no page.
- Entry: type `Entry`; producers `Entry.with_mount`, `Entry.without_mount`, `Entry.with_content`, and as consumers `write` on five classes (`AsyncSession`, `AsyncVirtualFileSystem`, `DatabaseStorage`, `Session`, `VirtualFileSystem`), all from hints.
- Mount: types `MountInfo` and the private `base.Binding`; producers `AsyncVirtualFileSystem.bind` by hand and `mounts` on both file-system classes from hints; consumers `unbind` on both file-system classes by hand, because the hint, which returns the record removed, would list them as producers.

## Not built

1. The docs app does not draw an object from `internals`; a maintainer page that pulls one in stops the build. The drawing decided: the short name as the heading and the dotted path beneath it in small type.
2. A maintainer page for the private objects the glossary cites today: `expand_pattern`, `compile_filter` and `Binding`.
3. The export records where each `:term:` marker sits, for "Referenced in".
4. The glossary page's own renderer in the docs app: the parts as a labelled grid of linked names, and the folded "Referenced in" box. Until it exists the page shows the parts as plain list items with no links and without the names found from hints.
5. The finder script.
6. A Maintainers page with the documentation rules, written once the rules above are built.
7. A method that exists on several classes is listed once per class: `write` appears five times under Entry. Whether to group them is not ruled on.
8. A class constructor is not read for hints, so a class that takes a type in `__init__` is not listed as its consumer.

## The mock-ups

Two single HTML pages in the docs site's colours and fonts were reviewed in a browser: one term, then Arm, Entry and Mount. The second went through four rounds: tags for how a name was found were removed, then "Instead of", then the descriptions beside the names. The files were kept in a session scratch directory and are not in the repository.

## Found on the way

- The glossary term Mount has no class of that name. The naming rules in `documentation/maintainers/how-we-name.md` and the renames in `agents/2026-11-16-public-names-follow-the-naming-rules/handoff.md` came from that.
- `StorageBackend` and `ObjectKind` are named in public signatures and are not exported.
- The sync facade's methods in `src/vfs/sync.py` have no docstrings.
- The first paragraph of many docstrings reads as a note for maintainers ("Gate, brace-expand, and cap one pattern", "JSON-native"). Those paragraphs head the reference pages.
