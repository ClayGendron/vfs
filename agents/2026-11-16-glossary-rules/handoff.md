# Glossary rules: handoff

## Goal

The glossary in `documentation/reference/glossary.md` has written rules, and the docs build holds each rule that can be checked. The list of terms grows under review; no term is invented by the build.

## What an entry is

A term is written in two files: the page `documentation/reference/glossary.md` and the file `documentation/reference/glossary.json` beside it. The page holds the prose. The file holds the structured facts, as a list of `{"term", "summary", "types"}`. The two hold the same terms, each once, in the same alphabetical order.

| Part | Where it is written | Shown on the glossary page | Rule |
|---|---|---|---|
| Name | page, as a second-level heading; file, as `term` | yes | Alphabetical order, none twice, the same in both files. |
| Description | page | yes | Plain words. It stands on its own, so its first paragraph names the term. Another term appears only as a link. |
| Summary | file, as `summary` | no | One sentence of plain text, at most 25 words, ending in a full stop, with no link. It is for a link to the term to show. |
| Types | file, as `types` | yes | A list of names, each an exported name or a path inside the package, each in the source. An empty list when the thing has no class. |
| Code | found by the build | yes | Every object in the package, private ones included, whose docstring marks the term with `:term:`. |
| Documentation | found by the build | yes | Every page outside the reference section that links to the term. |
| Related terms | found by the build | yes | The terms the description links to and the terms whose descriptions link to it, in one alphabetical list. |

The file holds no other key; one is added on purpose, with its own rule.

## Decisions, each with its reason

1. A use of a glossary term in a page or a docstring is found by a script and fixed by review; it fails no test. Reason: glossary words such as "mount", "entry" and "arm" are ordinary English words, so a word match cannot tell a use of the term from another sense.
2. The finder reads every documentation page and every docstring under `src/vfs/`, private ones included.
3. In a page, the first use of a term links to the glossary. In a docstring, a use carries the `:term:` marker.
4. The summary lives in `glossary.json` and is not printed on the glossary page; the description is the only prose under a term. Reason: each is shown alone, the summary on a link to the term and the description on the page. A description that began "A directory is an entry with no content", under a sentence it leaned on, was rejected.
5. Types holds only classes that are the thing, never a related type. `ObjectKind` left Entry and `StorageBackend` left Mount. Types moved from a labelled line on the page to the file, so a reason for "none" is said in the description.
6. No description is written or shown beside a name; the name links to its page. Reason: a description beside each name was mocked up from the docstrings and rejected.
7. Code is found from `:term:` markers, not from type hints. Producers and Consumers, hand-written and then found from hints, were built and removed: commits `0ec4529b` to `44b21735` hold that code.
8. "Seen by callers" and "Instead of" are dropped. A fact only the first carried, such as a term that appears in one error message, moves into the description.
9. A row under Types or Code is the name alone. A row under Documentation carries the page's tab beneath it. Related terms stays, both directions in one alphabetical list.
10. The glossary is one Markdown page and one JSON file, and the export checks the shape of both. Reason: a file per term would pass 16 children at the seventeenth term.
11. Nothing the build finds is written into `glossary.md` or `glossary.json`. Reason: the docs app refuses raw HTML in a page, and a list rebuilt on every build cannot go stale.
12. A private object is documented on a page under `documentation/maintainers/`, pulled in with the same `::: vfs.path` line the API pages use. Reason: a private name the glossary lists needs a page to link to.

## Built on the branch `glossary-rules`

- `scripts/docs_export.py`: the rules of the table above, each a refusal that names the term or the file; `internals`, the private objects a maintainer page pulls in; `glossary`, one entry per term with `anchor`, `summary`, `types`, `code`, `documentation` and `related`. A `:term:` marker for a term the glossary lacks is refused in a private docstring as in a public one.
- `docs-app`: the glossary page places a grid of four rows, Types, Code, Documentation and Related terms, at the end of each term, in `GlossaryTerm.svelte`. An empty Types row reads "None."; an empty Code or Documentation row reads "None yet."
- `documentation/reference/glossary.md` and `glossary.json`: the three terms in the new shape.

`tests/scripts/test_docs_export.py` passes, 53 tests. `scripts/docs.sh check` passes in full on 2026-11-17: the export, the build, the type check, 22 build tests and 20 browser tests. The app's test for the new page shape was written with the app's change and was not seen failing first.

## What the build finds for the three terms today

- Arm: no type; code `AsyncVirtualFileSystem.glob`; related Entry.
- Entry: type `Entry`; code `Entry`; related Arm and Mount.
- Mount: types `MountInfo` and the private `base.Binding`, which has no page and so no link; code `AsyncVirtualFileSystem.bind`, `MountError`, `MountInfo`; related Entry.
- No page links to the glossary yet, so Documentation is empty for all three. Five docstrings in `src/` carry a marker.

## Not built

1. The tooltip: the site does not yet show a term's summary on a link to the term. The export carries it as `summary`, and the summary is shown nowhere until this is built. Its form, the browser's own `title` or a drawn card, is not decided.
2. The docs app does not draw an object from `internals`; a maintainer page that pulls one in stops the build.
3. A maintainer page for the private objects the glossary names, `Binding` today.
4. The finder script.
5. A Maintainers page with the documentation rules.
6. `expand_pattern` and `compile_filter` produce and consume arms and carry no marker, so Arm's Code does not list them.

## Found on the way

- The glossary term Mount has no class of that name. The naming rules in `documentation/maintainers/how-we-name.md` and the renames in `agents/2026-11-16-public-names-follow-the-naming-rules/handoff.md` came from that.
- `StorageBackend` and `ObjectKind` are named in public signatures and are not exported.
- The sync facade's methods in `src/vfs/sync.py` have no docstrings.
- The first paragraph of many docstrings reads as a note for maintainers ("Gate, brace-expand, and cap one pattern", "JSON-native"). Those paragraphs head the reference pages.
- On `main`, the archived spec `2026-11-14-a-row-minted-across-a-posture-change-carries-the-label-the-standing-posture-gives.md` has four dead links to specs still under `active/`, and a memo of 2026-11-09 links to two `.log` files that `.gitignore` excludes. `tests/lint/test_context_shape.py::test_links_resolve` fails on the first locally and on the second on GitHub.
