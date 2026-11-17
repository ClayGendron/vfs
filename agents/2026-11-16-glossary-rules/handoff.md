# Glossary rules: handoff

## Goal

The glossary in `documentation/reference/glossary.md` has written rules, and the docs build holds each rule that can be checked. The list of terms grows under review; no term is invented by the build.

## Decisions, each with its reason

1. A use of a glossary term in a page or a docstring is found by a script and fixed by review; it fails no test. Reason: glossary words such as "mount", "entry" and "arm" are ordinary English words, so a word match cannot tell a use of the term from another sense.
2. The finder reads every documentation page and every docstring under `src/vfs/`, private ones included.
3. In a page, the first use of a term links to the glossary. In a docstring, a use carries the `:term:` marker, which the export turns into a link.
4. Each term has four labelled parts after its definition: Types, Producers, Consumers, Instead of. Types are the classes that are the thing in code. A producer creates or returns the thing. A consumer takes it or acts on it. The parts are defined by meaning and not by signature: an arm is a plain string and still has producers. Types may be empty. Reason: "Seen by callers" was not understood on first reading, and "callers" already means the people and agents that use vfs.
5. A term names at least one class or function across Types, Producers and Consumers, and each name must exist. Reason: a rename must not leave the glossary pointing at nothing.
6. "Seen by callers" is dropped. A fact only it carried, such as a term that appears in one error message, moves into the definition.
7. "Referenced in" is drawn by the docs app beneath each term, folded, grouped into Pages and Python API. It is built from page links to the glossary and from `:term:` markers, and is never written into `glossary.md`. Reason: the app refuses raw HTML in a page, and a list rebuilt on every build cannot go stale.
8. The glossary is one structured Markdown page and the export checks its shape. Reason: a file per term would pass 16 children at the seventeenth term.
9. A private object is documented on a page under `documentation/maintainers/`, pulled in with the same `::: vfs.path` line the API pages use. The glossary links to that page and never to a source file on GitHub. Reason: a `:term:` marker in a private docstring needs a page to be listed from.
10. "Instead of" stays as written prose and is not tested. Reason: a banned word such as "member" is legitimate in another phrase.

## Built on the branch `glossary-rules`

- `46e9aacb`: the export refuses a term that is missing a part, has parts out of order, has an unknown or doubled part, has no definition, is out of alphabetical order or is defined twice. A heading inside a code fence is not a term. The parts it checks are the earlier three: "Seen by callers", "In code", "Instead of".
- `803b501c`: a page under `maintainers/` pulls in a private object; the export describes it under `internals`, keyed by its dotted path. Refused: a private object on any other page, a public object on a maintainer page, a path not in the source, the same object on two maintainer pages.

`tests/scripts/test_docs_export.py` passes, 34 tests. `scripts/docs.sh check` has not been run on this branch.

## Not built

1. The parts change to Types, Producers, Consumers, Instead of: `GLOSSARY_PARTS` in `scripts/docs_export.py`, its tests, and the three terms in `glossary.md`.
2. The check that each name under Types, Producers and Consumers resolves to an object on a documentation page, public or maintainer.
3. The docs app does not draw an object from `internals`; a maintainer page that pulls one in stops the build. The drawing decided: the short name as the heading, the dotted path beneath it in small type, an "Internal" badge, and one sentence on the page saying internal objects carry no compatibility promise.
4. A maintainer page for the private objects the glossary cites today: `expand_pattern`, `compile_filter`, `MAX_PATTERN_ARMS`, and the mount classes until they are renamed.
5. The export records where each `:term:` marker sits, for "Referenced in".
6. The glossary page's own renderer in the docs app: the parts as a labelled grid, public names before internal ones, "Instead of" struck through, and the folded "Referenced in" box.
7. The finder script.
8. A Maintainers page with the documentation rules, written once the rules above are built.

## The mock-up

One term, Mount, was mocked up as a single HTML page in the docs site's colours and fonts and reviewed in a browser. It showed the grid of parts, the "Internal" badge beside private names, and the "Referenced in" box open, with real Python API entries and sample pages. The file was kept in a session scratch directory and is not in the repository.

## Found on the way

- The glossary term Mount has no class of that name. The naming rules in `documentation/maintainers/how-we-name.md` and the renames in `agents/2026-11-16-public-names-follow-the-naming-rules/handoff.md` came from that.
- `StorageBackend` and `ObjectKind` are named in public signatures and are not exported.
