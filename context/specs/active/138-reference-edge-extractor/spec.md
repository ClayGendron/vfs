# 138 — the reference-edge extractor: imports and markdown links as `edges` rows minted at reindex

- **Status:** markdown slice landed 2026-09-05 (slices A–C; see
  *Landing note*); the Python import slice (D) stays open — drafted
  2026-08-26 from ADR 053 (its consequences name the extractor as
  load-bearing for the centrality signal on code). Ninth of the glean
  arc; independent of 137 and may land any time after 136 (it produces
  the rows 136 reads). **Rescoped 2026-09-05 (Clay): markdown links
  first; language import extractors are a follow-up.** The design was
  validated by scripts over this repository before coding — see
  *Learnings* below; the semantics they changed are marked *(revised
  2026-09-05)*.
- **Born from:** ADR 053; Clay's 2026-08-26 pushback that edges need not
  be user-minted — code and markdown can be parsed for imports and
  links; memo `../../../research/2026-08-26-glean-ranking-signals-and-ranker-api.md`
  §2.3; ADR 018 (edge authoring verbs and materialised `fs` edges).
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Kind:** a new reindex producer writing typed `edges` rows; the
  markdown extractor (links and backticked paths read off the
  tree-sitter-markdown block and inline trees the crate already ships,
  one kernel in `crates/vfs-core`, run on the chunk pass's offload hop)
  lands here, the Python import extractor (tree-sitter-python, the same
  seam) follows in its own slice; the referring line captured for the
  later anchor-text field.
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

1. **Edge types** (one segment each, ADR 018's vocabulary): `links`
   (source document → resolved target path) now; `imports` (source
   file → resolved target module file) with the import extractor.
   Directed, `weight` = the count of references from source to target,
   `distance = NULL`. Never `fs`. A self-reference mints nothing
   *(revised 2026-09-05: a document linking itself is not a vote)*.
2. **Resolution is path-based and in-mount**: a markdown relative link
   or a backticked path resolves against the document's directory then
   the mount root; a link starting with `/` resolves from the root only.
   The target may be any live entry, file or directory *(revised
   2026-09-05: directory links are real references — 290 of them in
   `context/` — and the signals kernel ignores a directory's own
   in-degree, so they cost nothing there and serve the graph verb
   later)*. Resolution is an exact-path lookup under the membership
   budget — the candidate paths are computed from the link text, then
   probed in chunks against the unique `path` index — so the phase
   never holds the corpus's paths in memory *(revised 2026-09-05; the
   drafted path-map is gone)*. Unresolved references mint no edge; the
   counts are reported as one info-severity record on the reindex
   envelope, never an error. Python `import a.b.c` / `from a.b import c`
   resolution (package roots by `__init__.py`, relative imports from the
   file's package) is the import slice's.
3. **Provenance**: the `provenance` column spec 143 landed, value
   `extracted` (the value `mkedge`'s docstring already reserves). The
   extractor deletes only rows stamped `extracted` and only the
   `links` type, and only for the sources it re-extracted. A
   user-minted row on the same triple wins: the extractor's insert
   arbitrates on the unique key and drops its own row; `mkedge`
   touching an extracted triple re-stamps it with the caller's
   provenance, after which the extractor leaves it alone; `rmedge`
   removes any triple and the next extraction of the source mints it
   again if the document still links it.
4. **The phase** *(revised 2026-09-05)*: extraction rides the chunk
   pass, not a phase of its own. `chunk_dirty` already materialises
   every dirty body once for the offload hop; the markdown extractor
   parses in that same hop, so no body is read twice. The dirty signal
   is the write path's `chunked = False`, shared; the skip is the
   extractor's own stamp pair — `link_source_hash` (the body hash the
   edges were extracted from) and `link_generation` (the extractor
   version) — checked per row exactly as the chunk fingerprint is, and
   flipped in the same version-guarded flag statement as `chunked`,
   so the stamp costs no extra UPDATE. A generation bump re-dirties
   every entry once, the chunker's generation law. Per re-extracted
   source: delete its extracted `links` out-edges, bulk-insert the new
   set, both chunked under the budgets. Only a *source's* own out-edges
   are ever recomputed — never rows where the changed entry is the
   target. Rename rewrites zero edge rows (they key on ids; the body
   did not change, so nothing is re-extracted — a moved document's
   relative links keep the targets they had); delete's cascade already
   removes extracted rows in both directions. Two staleness facts are
   accepted and named: a link to a path that does not exist *yet*
   stays unresolved until the linking document next changes (or the
   generation bumps), and a moved target keeps its in-edges by id.
5. **The referring line** — the import statement or the line holding
   the link — is captured per edge (a `context` text column bounded to
   one folded line, ≤ 256 chars) so spec 130's anchor field can index
   it on the *target* entry later. Not consumed by anything in this
   spec.
6. **Languages** *(revised 2026-09-05)*: markdown first — `md` and
   `markdown` extensions; inline links and images `[t](dest)`,
   reference definitions `[label]: dest`, and backticked spans that
   look like a path (a `/` or a file extension, no whitespace). A
   scheme (`http:`, `mailto:`), a protocol-relative `//`, an
   anchor-only `#x` and everything inside fenced code are not
   references. Python imports follow in their own slice (this repo's
   own corpus and the accuracy study's SWE-bench corpora are Python);
   other grammars' import forms after that, each a small extractor
   behind one seam. The parser is tree-sitter-markdown in the Rust
   crate (its `parser` feature, which pairs the block grammar with the
   inline grammar), not a regex: links, images, reference definitions
   and code spans are tree nodes, and fenced code, indented code, HTML
   blocks and a link inside a code span fall out of the tree for free.
   The Rust kernel yields raw destinations and folded referring lines;
   the scheme/anchor filter and path-shape rule for code spans are
   applied on the way out; the regex draft became the pure-Python
   oracle that pins the kernel.

## Scope

In (this landing): the markdown extractor, resolution, provenance, the
extraction inside the chunk pass with its stamp pair, the `context`
column, tests over a fixture tree and this repository's own `context/`
and `docs/`, the measure × γ harness table spec 136 deferred. Out:
the Python import extractor (next slice), symbol-level references
(calls, definitions), other languages, walking the edges (the graph
verb), any query-side use, name-suffix resolution of bare backticked
file names (see *Learnings*).

## Learnings from the validation scripts (2026-09-05)

Two scratch scripts ran the drafted rules over this repository's own
docs (`context/`, `docs/`, `CLAUDE.md`, `README.md`: 537 markdown
files, 7.7 MB) and over the ranking golden set before any storage
code was written. What they changed:

| question | measured | consequence |
|---|---|---|
| parse cost, regex | 45 ms/MB in plain Python (0.35 s for the docs) | fast, but a hand-rolled parser that misreads indented code, mixed fences, HTML and nested brackets |
| parse cost, tree-sitter | 463 ms/MB serial for block + inline grammars (165 of it the block parse chunking already pays); 0.54 s for the whole docs corpus on rayon | **tree-sitter it is**: ten times the regex per byte, bounded and parallel, and correct on every corner the regex misses; the count agrees with the regex where the regex is right (1,109 inline links vs 1,111) |
| tree shape | `link_destination` under `inline_link`, `image`, `link_reference_definition`; `code_span` (delimiters included); `uri_autolink` and `html_tag` separate; nothing yielded inside fenced or indented code | the kernel walks the block tree with inline trees spliced in; reference-style links carry no destination themselves — their definition does |
| inline links | 1,111 found; 543 are URLs or anchors; 283 resolve, 285 do not | the unresolved are dead paths (moved or archived files) and absolute paths into other checkouts — honestly unresolved |
| backticked spans | 8,085 path-shaped; 802 resolve to files, 284 to directories | worth keeping (they are a third of the graph) but noisy: 2,252 are bare file names, 1,243 absolute paths from other machines, 1,217 root-relative paths to files that moved |
| directory targets | 290 references resolve to a directory | directories are valid targets; the signal kernel ignores a directory's own in-degree, so they cost nothing there |
| bare names (`` `base.py` ``) | a unique-suffix rule would rescue 382 more references in `context/` (1,489 repo-wide) and leave 54 (277) ambiguous | **deferred**: it needs a `name` index or a path scan plus an ambiguity policy; exact-path lookup plans on the unique `path` index and needs neither. Recorded as the first follow-up |
| self-links | 6 | dropped: a document linking itself is not a vote |
| the graph | 770 distinct edges, 1,079 references, 348 targets; 286 of 537 markdown files have zero in-degree; top in-degree `context/open-questions.md` at 30 | the sparse profile the memo measured; the prior stays present and unlinked files sit at the floor |
| golden set | 200 markdown files; 55 inline + 114 backticked references resolve | enough edges to run the measure × γ table 136 deferred |

The memo's 691 figure counted `.md` targets only over `context/` +
`docs/`; this extractor also resolves non-markdown files and
directories, which is where the difference comes from.

## Slices

- **A — the markdown extractor**: link forms and candidate-path
  resolution as pure functions in `models/links.py` with fixture tests
  (`..` links, root-relative and `/`-absolute links, backticked paths,
  fenced code, URLs and anchors, self-links, unresolvable refs).
- **B — the pass**: `extracted` provenance, the stamp pair on
  `entries`, the `context` column on `edges`, schema format 12;
  extraction inside `chunk_dirty`; delete/insert under budgets; the
  info record; engine-leg pins that the extracted rows feed spec 136's
  in-degree.
- **C — corpus check**: extract over this repository's `context/` and
  `docs/` through a real mount and record edge, source, target and
  unresolved counts in the landing note; the vfs-native golden set
  (spec 131) re-scored with the `centrality` arm on extracted edges —
  the measure × γ table.
- **D — Python imports** (follow-up, not this landing): the
  tree-sitter batch function, package-root resolution, the `imports`
  type.

## Landing criteria

- `scripts/ci.sh 3.13` green; engine legs green.
- Landing note: edge counts on this repo (the hierarchy experiment
  found 691 markdown links by regex — the scan above explains the
  difference), the unresolved rate, and the reindex wall delta.
- Ledger rows: a user-minted edge survives an extractor rerun; an
  extracted edge is replaced, not duplicated, when its source changes;
  a change to a *target* rewrites none of its in-edges; a same-body
  overwrite re-extracts nothing; no `fs` edge is ever minted here.

## Landing note — the markdown slice (2026-09-05)

**What landed.**

- `crates/vfs-core/src/links.rs`: the kernel. One `MarkdownParser` per
  rayon worker (tree-sitter-md's `parser` feature — the block grammar
  with the inline grammar spliced in under every `inline` node); a
  cursor walk that yields every `link_destination` (inline link, image,
  reference definition) and every path-shaped `code_span` with the
  referring line folded to one bounded line. Protocol 10; the
  `markdown_refs` binding and the `vfs.native.markdown_refs` seam.
- `models/links.py`: `extract_links` (the seam, then the in-mount
  filter — schemes, `//`, anchor-only; fragments and queries off),
  `link_candidates` (document directory then root; root-anchored once;
  reserved scope and the root dropped; trailing `/` insignificant),
  `link_generation()` = `md:1`, `LINK_EDGE_TYPE = "links"`,
  `MARKDOWN_EXTENSIONS`, `MAX_LINK_CONTEXT_LENGTH = 256`.
- `models/edge.py`: `EXTRACTED_PROVENANCE = "extracted"`.
- `models/rows.py`: schema format 12 — `entries.link_source_hash` and
  `entries.link_generation` (the stamp pair), `edges.context`.
- `storage/backends/database/links.py`: `extract_link_work` (runs
  inside the chunk pass's offload hop, only on markdown rows the stamp
  pair does not cover) and `publish_links` (exact-path candidate probe
  in membership chunks; per source delete the extracted `links`
  out-edges, then one arbitrated bulk insert — a collision with an
  authored row drops the extracted row). The chunk pass
  (`indexing.chunk_dirty`) calls both and flips the stamps in the same
  guarded statement as `chunked`; the generation law's re-dirty
  predicate covers the link generation too. The unresolved count rides
  the reindex envelope as one info record (`data.leg = "links"`,
  `sources`, `edges`, `unresolved`), carried through the gram phases
  by `with_notes`. `edges.insert_arbitrated` is public now; it serves
  both minters.
- Tests: `tests/models/test_links.py` (the shapes, the candidates, and
  kernel-versus-oracle parity over the 104 golden documents whose code
  spans close on their own line — the oracle in
  `tests/support/oracles/links.py` is the regex draft, and a span
  across a line break is the one shape a line reader cannot see);
  `tests/storage/database/test_links.py` (extraction, the ledger, the
  prior reading the rows, the four engine legs); the harness's
  `TestSignalArms` now reads real edges.

**Corpus check (slice C)** — this repository's `context/`, `docs/`,
`CLAUDE.md`, `README.md` through a SQLite mount:

| | |
|---|---|
| files written / markdown documents | 1,086 / 537 |
| first reindex wall (of which `publish_links`) | 3.5 s (0.36 s) |
| second reindex, nothing dirty | 0.1 s, no link record |
| extracted edges / sources / targets | 983 / 322 / 426 (197 targets are directories) |
| references folded into those edges | 1,409 |
| unresolved references | 8,511 — the backticked noise the scan predicted: bare names, absolute paths from other machines, files that moved |
| top in-degree | `context/open-questions.md` 31; `docs` and `context` 23 each; `docs/architecture.md`, the glean brief and `CLAUDE.md` 14 |

Against the memo's 691: that count was `.md` targets only over
`context/` + `docs/`; this run also resolves non-markdown files and
directories and reads two more documents, and 770 of the 983 are the
file-to-file edges the regex scan counted.

**The measure × γ table** (the study spec 136 deferred; golden set,
166 extracted edges over 200 documents, nDCG@10 / MRR@10 / recall@10;
control `glean` 0.7589 / 0.9833 / 0.4134):

| measure | γ | linear β=0.15 | linear β=0.5 | log1p β=0.5 |
|---|---|---|---|---|
| in-degree | 0.0 | 0.7571 | 0.7511 | **0.7594** |
| in-degree | 0.15 | 0.7550 | 0.7519 | 0.7591 |
| in-degree | 0.3 | 0.7556 | 0.7491 | 0.7584 |
| PageRank | 0.0 | 0.7580 | 0.7533 | 0.7573 |
| PageRank | 0.15 | 0.7581 | 0.7529 | 0.7593 |
| PageRank | 0.3 | 0.7574 | 0.7533 | 0.7593 |
| Katz | 0.0 | 0.7498 | 0.7538 | 0.7558 |
| Katz | 0.15 | 0.7530 | 0.7537 | 0.7565 |
| Katz | 0.3 | 0.7530 | 0.7539 | 0.7573 |

Read honestly: on this corpus the prior is neutral. No arm beats the
control by more than noise; every linear arm at β = 0.5 costs 0.005 to
0.010 nDCG; `log1p` holds the control and lifts recall@10 by about
0.006 across the board. The golden queries are lexical and the graph
is sparse (166 edges, most documents unlinked), so this is the
expected profile, not a verdict on the signal — the SWE-bench corpora
of the accuracy study are where the prior earns or loses its place.
The harness records `signals/centrality` (in-degree, γ = 0, log1p,
β = 0.5: 0.7594) as the gated arm; the default `Ranker` still declares
no signal.

**Gates.** `cargo test -p vfs-core` 62 passed; `scripts/ci.sh 3.13`
green at 100 % coverage; the four engine legs green for the link,
signal, edge and indexing suites (118 passed).

**Follow-ups, named.**

- Slice D, Python imports: tree-sitter-python through the same seam,
  package-root resolution, the `imports` type.
- Bare-name resolution for backticked file names (382 rescuable in
  `context/`, 54 ambiguous): needs a `name` index or a scan plus an
  ambiguity policy.
- A restored entry comes back with its extracted in-edges gone (the
  delete cascade removed them, restore mints nothing) until each
  linking document next changes or the generation bumps — the same
  law authored edges already follow, now with a way back.
