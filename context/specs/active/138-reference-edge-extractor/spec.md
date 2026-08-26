# 138 — the reference-edge extractor: imports and markdown links as `edges` rows minted at reindex

- **Status:** ready — drafted 2026-08-26 from ADR 053 (its consequences
  name the extractor as load-bearing for the centrality signal on
  code). Ninth of the glean arc; independent of 137 and may land any
  time after 136 (it produces the rows 136 reads).
- **Born from:** ADR 053; Clay's 2026-08-26 pushback that edges need not
  be user-minted — code and markdown can be parsed for imports and
  links; memo `../../../research/2026-08-26-glean-ranking-signals-and-ranker-api.md`
  §2.3; ADR 018 (edge authoring verbs and materialised `fs` edges).
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Kind:** a new reindex producer writing typed `edges` rows; two
  extractors (Python imports via the tree-sitter grammars already in
  `crates/vfs-core` / `chunking.py`; markdown links and backticked paths
  via a small parser); the referring line captured for the later
  anchor-text field.
- **Depends on:** spec 136 (the consumer), `Edge`/`edges` (ADR 015/018),
  the chunking grammars (ADR 048) for Python `import` statements, the
  reindex phase discipline.
- **Relates to:** spec 130's future BM25F anchor field (ADR 053 F10);
  the graph verb (out of scope here — this spec produces rows, it does
  not walk them).

## Intent

Centrality over declared edges is real on a link-rich corpus and empty
on a bare code tree. Automating reference edges — which file imports
which, which document links to which — makes the prior exist on code
and prose without any user minting, and captures the referring line so
the anchor-text arm of the accuracy study has data.

## Decided semantics

1. **Edge types** (one segment each, ADR 018's vocabulary): `imports`
   (source file → resolved target module file) and `links` (source
   document → resolved target path). Both directed, `weight = 1.0` (or
   the count of references from source to target), `distance = NULL`.
   Never `fs`.
2. **Resolution is path-based and in-mount**: a Python `import a.b.c` /
   `from a.b import c` resolves against the mount's own tree (package
   roots detected by `__init__.py` or a declared source root; relative
   imports from the file's package); a markdown relative link or a
   backticked path resolves against the document's directory then the
   mount root. Unresolved references mint no edge (a count of unresolved
   is reported, never an error).
3. **Provenance**: extracted edges are distinguishable from user-minted
   ones so a reindex can replace them wholesale — either a reserved
   type prefix or a `provenance` column (decide in plan.md; ADR 018's
   authoring verbs must never delete extracted rows by accident, and the
   extractor must never delete user rows).
4. **The phase**: after `chunk_dirty` (bodies are fresh) and before the
   signals phase, for entries whose `content_hash` changed since their
   edges were last extracted (a per-entry `edges_source_hash` stamp, the
   fingerprint-skip law again): parse off the event loop through
   `call_offloaded`, delete that entry's extracted out-edges, insert the
   new set in chunked bulk inserts. Rename rewrites zero edge rows (they
   key on ids); delete's cascade already removes them.
5. **The referring line** — the import statement or the line holding
   the link — is captured per edge (a `context` text column bounded to
   one folded line, ≤ 256 chars) so spec 130's anchor field can index
   it on the *target* entry later. Not consumed by anything in this
   spec.
6. **Languages**: Python imports and markdown links first (this repo's
   own corpus and the accuracy study's SWE-bench corpora are Python);
   other grammars' import forms are a follow-up per language, each a
   small extractor behind one seam.

## Scope

In: the two extractors, resolution, provenance, the phase with
fingerprint-skip, the `context` column, tests over a fixture tree and
this repository's own `src/` and `context/`. Out: symbol-level
references (calls, definitions), other languages, walking the edges
(the graph verb), any query-side use.

## Slices

- **A — extractors**: Python import resolution and markdown link
  resolution as pure functions with fixture tests (relative imports,
  packages, `..` links, backticked paths, unresolvable refs).
- **B — the phase**: provenance, fingerprint-skip stamp, delete/insert
  under budgets, the `context` column, schema bump; engine-leg pins that
  the extracted rows feed spec 136's in-degree.
- **C — corpus check**: extract over this repository and record edge
  counts and unresolved counts in the landing note; the vfs-native
  golden set (spec 131) re-scored with the `centrality` arm on
  extracted edges.

## Landing criteria

- `scripts/ci.sh 3.13` green; engine legs green.
- Landing note: edge counts on this repo (the hierarchy experiment
  found 691 markdown links and 173 imports by regex — the extractor
  should match or explain the difference), the unresolved rate, and the
  reindex wall delta.
- Ledger rows: a user-minted edge survives an extractor rerun; an
  extracted edge is replaced, not duplicated, when its source changes;
  no `fs` edge is ever minted here.
