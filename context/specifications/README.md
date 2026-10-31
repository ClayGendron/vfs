# /context/specs

The SPEC stage of the pipeline described in [the context README](../README.md). A spec is the one document every change must have: a work package small enough for one developer, human or agent, that decides every choice the build needs and names the test that will pin each acceptance criterion.

## Layout

```
specifications/
  active/     # not yet landed: drafted, reviewed, building, or parked
  archive/    # landed, moved here by the landing commit under the same name; or withdrawn
  README.md
  STATUS.md   # frozen 2026-10-29
```

The state of a spec is its folder. Under `active/` it is not landed; under `archive/` it is. A parked spec stays in `active/` and its first paragraph after the title begins "Parked:" with the reason. A withdrawn spec moves to `archive/` and its first paragraph begins "Withdrawn:" with the reason.

## The shape

One file, `active/YYYY-MM-DD-descriptive-slug.md`. The title is line one and a first paragraph follows it with no header lines: it says what kind of change this is and which gates it needs, links the intention it comes from and the research it stands on (or says "none" and why), and names any spec it depends on by link. Then nine sections, in this order:

1. **The problem.** What the code does today, at a named commit, and why that is wrong or missing. Facts labelled EXECUTED or READ.
2. **Architecture.** One Mermaid block in the dialect of [the architecture pages](../architecture/README.md): solid for what exists, dashed (`planned`) for what this spec adds, dotted (`retiring`) for what it removes. Name the page the diagram will change on landing, and define any new term under it.
3. **Decisions.** Every choice the change needs, as `### N.` headings numbered from 1, each a sentence with its reason in the body. A decision that departs from a landed spec or a frozen record names it. Nothing here is open.
4. **Intent.** One paragraph beginning "After this spec, …": the observable state once it lands, in the user's terms.
5. **Design.** The files, functions, types and tests that change, with sizes where a ceiling matters, and the order of work: the tests first, then the code that passes them.
6. **Scope.** In: the decisions by number and the files by path. Out: each neighbouring thing this spec does not do, with where it belongs.
7. **Acceptance criteria.** Numbered. Each is a sentence one test can pin, and it names that test (file and node id, or conformance row) before the test exists. Counts and states, never clocks.
8. **Landing notes.** "Filled in on landing." until then. Then: the commits by sha, both reviews by link, the gate's counts, the engine legs run, measurements labelled EXECUTED, the disposition of every review finding, differences from the text above with their reasons, the architecture page and glossary entries updated, and one `**Changelog:**` line.
9. **One line.** The whole change in one sentence.

## The kind of change, in the first paragraph

The primary word is one of feature, fix, refactor, spike, process, docs. The flags each trigger a gate: **structural** (adds or removes a module, a public class, a protocol method, a lifecycle or a seam: the spec review scores structure); **changes the public API** (the docs reference is regenerated; the review checks nothing else changed); **changes the schema format** (the format bump is a criterion; the four engine legs run before landing); **needs the engine legs** (touches `storage/backends/database/`, a profile, a builder or a loop over batch input: the `db_test` cycle before landing); **touches rights** (the security lens is mandatory, with a leak test among the criteria); **touches the engine** (`cargo test -p vfs-core` and the wheel reinstall are criteria); **parallel-safe** (touches files no other active spec touches).

## Lifecycle

1. **Born** from an intention, a research memo, or directly from a defect or a reviewer's finding, as a file in `active/`.
2. **Drafted** whole: every section present, every decision made with its reason, the diagram drawn. A choice the author cannot make becomes a placeholder research memo, linked from the spec, and the spec waits. There is never a marker.
3. **Reviewed** by someone who did not write it, as a file under [reviews/](../reviews/README.md). "Fit to build" is the signature on that draft; the spec links the review.
4. **Built**, tests first, in the working tree; a decision taken during the build is appended to the Decisions section.
5. **Reviewed again** on the local unpushed commits. "Lands" is the signature on that tip.
6. **Landed** by one commit that fills the landing notes, moves the file to `archive/` with `git mv`, and links the spec and both reviews in its trailers. See [landing](../standards/landing.md).

A landed spec is retired: nothing in `archive/` governs current work. The architecture pages and the code are what a reader trusts.

## The lint

`tests/lint/test_context_shape.py` holds this shape on every direct `.md` file under `active/` and `archive/` whose name begins with a date: the name, the absence of header lines, the nine sections in order, the Mermaid fence, the gap-free decisions, the absence of any open question, resolving links, one-line paragraphs, and, for an archived spec, links from its landing notes to a spec review whose standing verdict begins "Fit to build" and a code review whose standing verdict begins "Lands".

## Before 2026-10-29

The numbered folders (`NNN-slug/spec.md`, some with a `plan.md` and a `tasks.md`) are the earlier shape. They keep their names and are not scanned by the shape lint; a ratchet in `tests/lint/allowlist.py` admits the open markers they hold today and may only shrink. A numbered spec picked up to build is converted in place: every marker becomes a numbered Decision or a placeholder memo, it gains an Architecture section, and its reviews name it by title. `STATUS.md` froze on the same day.
