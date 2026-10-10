# 076. No Producer Authors `message`; the Contract Table Composes It and the Renderer Attaches Every Locus Last

- **Status:** accepted 2026-10-10 (Clay, in conversation: "the router
  should compose the message, the message shouldn't be written by
  storage, storage should send structured data back"; on the refactor
  read, "green light"; on the record, "accept"). Amends the envelope law stated in
  `src/vfs/results/envelope.py` ("Rebase seams touch `path`/`source`/
  `data`, never `message`"), which stands; this record adds the
  producer-side half of it. Refines ADR 008 (the result-only error
  channel) and ADR 010 (the result envelope contract); nothing is
  superseded.
- **Date:** 2026-10-10
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay). Claude ran the prior-art read, drafted
  the design and this record.
- **Context source:** spec 154 as cut 2026-10-08 (the symptom);
  research memo `2026-10-10-who-composes-the-error-message.md` (the
  prior art); the live tree at `4b598bc`.

## Context

An agent reading `ERROR /mine/missing.md: Not found: /missing.md` sees
two paths and retries the wrong one. The first is the rebased locus
the renderer prints from the structured `path`. The second is the
storage's own coordinates, written into `message` by the producer.
The seam cannot fix it: by law it rewrites fields and never prose.

The cause is structural. The envelope has two construction doors and
both take prose: 67 raw `ResultError(...)` calls and 53 calls to
`classified(kind, message, ...)`, whose second positional argument is
a sentence. 109 producer sites write words, and the words collapse to
a handful of phrases: "Not found" appears with seven path variables
and one meaning. The vocabulary already carries that meaning; the
contract table already owns each kind's hint and retry class and is
consulted at render time. The message is the one piece of the line
still authored upstream.

The prior-art read found three models. Projects that stay correct
across a mount boundary either return a code and let the consumer's
table supply the words (errno, libfuse, pjdfstest) or keep the path as
a field and render the text late from fields (opendal, pyfilesystem2,
mirage). Projects that let the backend write the path into prose leak
the inner path at every sub-filesystem seam (Plan 9, fsspec, afs,
deepagents), and one of them then parses the prose to decide behaviour
(deepagents). vfs is in the third group with the second group's parts
already built.

## Options considered

- **A. Strip the path at every producer site and pin it with a test**
  (spec 154 as cut 2026-10-08). Cheap, mechanical, 51 edits. Leaves
  both doors open, so every new site can leak again and the test is
  the only guard. Treats the symptom.
- **B. One constructor with no message argument; the contract table
  owns a phrase per kind; a path-free `detail` for the two causes a
  template cannot carry; the renderer attaches locus and second entry
  from rebased fields.** Removes the class of bug: a producer cannot
  put a path in prose because there is nowhere to put prose. The wire
  shape of `ResultError` is unchanged. Costs a migration of the 109
  sites and the tests that pin text.
- **C. A class per kind** (`NotFound`, `WrongKind`), pyfilesystem2's
  exception hierarchy. Python exceptions need classes because `except`
  dispatches on type; vfs dispatches on the kind string so an unknown
  child kind from a newer peer degrades to its parent. A class per
  kind duplicates the vocabulary, fights that law, and adds nothing a
  field does not.
- **D. Compose the message in the router at the mount seam.** The
  router does not know when an error is final: errors cross nested
  mounts, merge, and roll up. Prose composed at hop one is wrong at
  hop two. Fields rebase at every hop; prose at none.

## Decision

We chose **B**. Storage returns a fact: a kind, a locus and named
fields. `KindContract` gains a `phrase`. `classified(kind, path=None,
*, target=None, detail=None, retryable=False, **fields)` is the one
general constructor for a `vfs.*` error, with `already_exists` and
`wrong_kind` kept as the two conveniences that encode a field. It
composes `message` as the phrase, filled from the fields, then `: `
and the detail when one is given. A phrase never contains a locus. A
detail is a path-free phrase, never a sentence with a locus, never a
Python keyword, and for `invalid` and `internal` it is required. The
second entry lives at `data["vfs.target"]` and both seams rebase it
with `path`'s rule. The renderer prints `SEVERITY <path>: <message>
(target <vfs.target>) — <hint> (retry: <class>)`, attaching every
locus after every rebase has run.

Composition happens at construction, not at render, because the
phrase carries no path and so timing cannot bake a wrong locus in.
`message` stays a string on the wire: MCP reads text and asks for a
concise sentence, and peers with `x.<vendor>.*` or unknown kinds keep
authoring theirs. No new wire field: `detail` is not stored apart from
the message it composed, because no consumer may parse prose and a
stored copy would invite one.

## Consequences

- **Easier:** a leak of storage coordinates into prose is impossible
  by construction, not merely tested for. Every kind's words live in
  one table beside its hint and retry class, so a wrong word is fixed
  everywhere at once. A new producer site names a kind and passes
  fields; it cannot write a sentence. Tests pin `kind`, `path` and
  `data`, which is what they were testing all along.
- **Harder:** 109 producer sites and about 27 test files migrate
  (spec 154 slices A and B). A failure whose cause is not its kind
  must find a field or a detail, which is the discipline the table
  enforces. A reader of `message` alone sees "Not found" with no path;
  the path is in the rendered line and in `path`, by design.
- **Committed to:** the envelope law now has two halves. *No seam
  touches `message`* (as before) and *no producer authors `message`*
  (this record). A raw `ResultError(...)` in `src/vfs` outside
  `src/vfs/results/` is a defect, pinned by a grep gate in the test
  suite. The `vfs.target` key is envelope machinery and rebases with
  `path`. The phrase table is normative and versioned with the
  vocabulary; a kind without a phrase cannot ship.
