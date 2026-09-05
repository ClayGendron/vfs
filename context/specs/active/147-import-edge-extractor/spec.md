# 147 — the import-edge extractor: language imports as `imports` rows minted at reindex

- **Status:** seed — split out of spec 138 on 2026-09-05 (Clay: the
  markdown slice is done; language imports are their own work). This
  is spec 138's slice D with its own number. Not scheduled; may land
  any time after 138 (whose seam, stamp law and publisher it reuses).
- **Born from:** spec 138 (`../../archive/138-reference-edge-extractor/spec.md`,
  slice D and the *Follow-ups, named* list); ADR 053 (the centrality
  prior is load-bearing on code only once code has reference edges);
  memo `../../../research/2026-08-26-glean-ranking-signals-and-ranker-api.md`
  §2.3.
- **Date:** 2026-09-05
- **Owner:** Clay Gendron
- **Kind:** a second extractor behind the seam spec 138 built — one
  tree-sitter kernel per language in `crates/vfs-core`, run on the
  chunk pass's offload hop; a resolver per language in
  `models/`; the same publisher (`publish_links` generalised to the
  edge type), the same stamp law.
- **Depends on:** spec 138 (landed — `extract_link_work`,
  `publish_links`, the `link_source_hash` / `link_generation` stamp
  pair, `edges.context`, `EXTRACTED_PROVENANCE`), the chunking
  grammars (tree-sitter-python is already a crate dependency), spec
  136 (the consumer).
- **Relates to:** spec 130's future BM25F anchor field (the referring
  line); the graph verb (spec 067 — this spec produces rows, it does
  not walk them).

## Intent

Spec 138 made the centrality prior exist on prose. On a bare code
tree it is still empty: nothing links a module to the modules it
imports. This spec parses import statements and mints `imports` edges
so the prior — and later the graph verb — sees the dependency
structure of a codebase without any user minting. Python first: this
repository's corpus and the accuracy study's SWE-bench corpora are
Python, so that is where the signal is measured.

## Decided semantics (inherited from 138 unless marked)

1. **Edge type** `imports`, directed source file → resolved target
   module file, `weight` = the count of import statements from source
   to target, `distance = NULL`, provenance `extracted`. Never `fs`. A
   self-import mints nothing. The referring line — the import
   statement, folded to one line, ≤ 256 chars — rides in
   `edges.context`.
2. **Resolution is path-based and in-mount.** For Python: `import
   a.b.c` and `from a.b import c` resolve to `a/b/c.py` or
   `a/b/c/__init__.py` and, when `c` is a name inside the module,
   to `a/b.py` / `a/b/__init__.py`; relative imports (`from . import
   x`, `from ..y import z`) resolve from the file's own package;
   package roots are found by walking up while `__init__.py` exists,
   then the mount root and any `src/`-style layout the resolver
   declares `[NEEDS CLARIFICATION: which roots — the file's package
   root and the mount root only, or also a declared list?]`.
   Candidates are probed by exact path in membership chunks exactly as
   138's link candidates are; no corpus path map. Stdlib and
   third-party imports resolve to nothing in the mount and mint no
   edge; their count rides the info record as `unresolved`.
3. **The pass** is 138's: extraction inside `chunk_dirty`'s offload
   hop (one body read), dirtiness from `chunked = False`, the skip from
   the stamp pair. `[NEEDS CLARIFICATION: one stamp pair for all
   extractors (generation string becomes `md:1+py:1`, so any bump
   re-extracts every document) or one pair per extractor (two more
   entry columns, independent bumps)?]` The publisher deletes only a
   re-extracted source's `extracted` out-edges of the type it owns.
4. **Languages**: Python in this spec's first slice. Each further
   language is one small kernel (the tree-sitter grammar the chunker
   already ships) plus one resolver; the seam takes a list of
   `(extension set, kernel, resolver)` so a grammar is added without
   touching the pass.

## Scope

In: the Python kernel (`import_statement`, `import_from_statement`,
relative levels, aliased and parenthesised forms; nothing inside
strings or comments), the Python resolver, the `imports` type through
the existing publisher, the stamp-law decision, an oracle in
`tests/support/oracles/` pinning the kernel, engine-leg pins, a corpus
check over this repository's `src/` and `tests/`, and the golden-set
re-score with the centrality arm now reading both edge types. Out:
symbol-level references (calls, definitions), other languages
(each a follow-up slice), name-suffix resolution of bare backticked
file names (138's follow-up; still open), walking the edges.

## Slices

- **A — the Python kernel**: `crates/vfs-core/src/imports.rs`,
  batch function on rayon, protocol bump, the `native` seam.
- **B — the resolver and the pass**: `models/imports.py`, the stamp
  decision, the publisher generalised to a type, the info record
  naming both legs.
- **C — corpus check**: edges over this repository's Python tree;
  the golden-set signal table with both edge types.

## Landing criteria

- `scripts/ci.sh 3.13` green; engine legs green; `cargo test` green.
- Ledger rows: a user-minted `imports` edge survives a rerun; a source
  change replaces its `imports` rows and leaves its `links` rows alone
  (and vice versa); a change to a target rewrites nothing; stdlib
  imports mint no edge and are counted.
- Landing note: edge, source, target and unresolved counts on this
  repository's `src/`; the reindex wall delta; the signal table.
