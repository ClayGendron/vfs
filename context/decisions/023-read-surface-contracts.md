# 023. Read-Surface Contracts: Enumeration Liveness, Scope Anchors, Observation Metrics

- **Status:** accepted 2026-07-22 — decided by Clay in session (option
  picks plus direction on the POSIX question and memory's status);
  implemented and pinned the same day.
- **Date:** 2026-07-22
- **Deciders:** Clay Gendron
- **Context source:** the whole-file `reads.py` review (five-lens,
  adversarially verified) surfaced these as declared-nowhere forks:
  the two backends genuinely disagreed on meta-scope enumeration, and
  glob's anchor semantics were pinned by no spec, docstring, or test.

## Decisions

### 1. Meta-subtree hiding is a protocol semantic, not a backend feature

Default-scope enumeration (`ls`, `tree`, `glob`, `grep`) hides the
reserved `/.vfs` subtree on **every** backend; a meta-addressed anchor
serves its own subtree, and the bypass is **per-anchor, never
query-wide** — adding an anchor to a scope cannot change what other
anchors return. Declared in `storage/protocol.py`'s module docstring,
implemented in both backends, pinned in the conformance suite. Point
reads (`read`, `stat`) address meta paths directly and always bypass —
hiding is an enumeration-scope rule, not access control.

### 2. Glob/grep scope anchors behave like POSIX `find` operands

Decision rule set by Clay: "run the same command on this compute; vfs
does what it does." Executed 2026-07-22 on darwin:

- `find real/ nope/ -name '*.py'` → error for the missing operand,
  results still served for the real one, exit 1.
- `find afile.txt -name '*.txt'` → the file operand is matched itself
  (served on a hit, empty clean success on a miss, exit 0).

vfs mirrors this exactly: a **missing anchor classifies through the
descent ladder** as a per-anchor error beside the healthy anchors'
observations (partial results, failed `Result` ≈ exit 1); an existing
**file anchor is matched itself** against the pattern, never an error.
Both backends, pinned in conformance. The previous behavior — missing
anchors as silently vacuous filters — is retired: an agent globbing a
typo'd directory now learns it is missing, not empty.

### 3. `InMemoryStorage` is interim, not a long-term contract surface

The memory backend exists to exercise the protocol and conformance
suite. It is slated to be replaced by `DatabaseStorage` over an
embedded SQL engine (turso), at which point it retires. It must pass
conformance while it lives, but nothing is invested there beyond that
bar — `columns=` projection is deliberately unimplemented, and the
projection/mask contract stays pinned on the database leg. Recorded in
`memory.py`'s module docstring.

### 4. Content metrics are an `Observation` model invariant

"Content metrics belong only to content-bearing kinds" was encoded
three coincidentally-agreeing ways across `reads.py`, `writes.py`, and
`memory.py`. The rule now lives where content invariants already live:
`models/entry.py`. `CONTENT_KINDS` moved there, and `Observation`'s
before-validator nulls `size_bytes` on any known non-content kind —
the invariant is unrepresentable rather than a per-backend discipline,
and it also enforces at wire deserialization. A stamped mask still
reports the nulled metric as fetched-and-null.

### 5. Glob's ext filter reads the path-derived extension

Settled during the same review cycle: the ext filter deliberately reads
`extract_extension(path)`, never the stored `ext` column — explicit-ext
rows and extension-carrying directory names (which store `NULL`) must
match identically on every backend. An executed repro showed the
column push-down variant drops dot-named directories; the shared
semantics live in `storage/globbing.py` and the edge is pinned in
conformance.

## Consequences

- The conformance suite grew the liveness and anchor pins; a future
  backend (including the turso conversion) inherits the full contract.
- Missing-anchor classification is a behavior change on both backends:
  scoped `glob`/`grep` with a dead anchor now returns a failed result
  carrying partial observations. Callers treating empty-success as
  "directory is empty" get the correction they needed.
- Spec 072 §6 and spec 073 remain the deeper homes for glob semantics;
  they should cite this record when next revised.
