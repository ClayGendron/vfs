# vfs search-layer ground truth: glob / grep / glean / graph over media

- **Study type**: internal ground truth for the multimodal storage-and-search
  brief ([../../2026-07-25-multimodal-storage-and-search-brief.md](../../2026-07-25-multimodal-storage-and-search-brief.md)),
  search half (brief questions 7–10, plus Q6's chunk question).
- **Date**: 2026-07-25
- **Method**: close reading of the live tree only (`src/`, `tests/` are live;
  `src2/` consulted for nothing here), plus the two search-layer research
  memos already in `context/research/`. Every claim cites file:line.

---

## 0. Implementation status: what "the four verbs" means today

The verb surface is real; the implementations are uneven. Any per-verb media
analysis has to start from this table or it will analyze code that does not
exist.

| Verb | Router | Protocol family | DatabaseStorage | InMemoryStorage |
|---|---|---|---|---|
| glob | `base.py:1001-1041` | `SupportsPatternSearch` (`protocol.py:146-164`) | **live** (`reads.py:183-227`) | **live** (`memory.py:217-242`) |
| grep | `base.py:1043-1115` | `SupportsPatternSearch` (`protocol.py:166-187`) | **classified stub** (`backend.py:200-222`) | **live scan tier** (`memory.py:244-299`) |
| glean | `base.py:1117-1151` | `SupportsGlean` (`protocol.py:191-207`) | **absent** (no method; not in `_LANDED_OPS`, `backend.py:56-58`) | **absent** |
| graph | `base.py:1153-1176` | `SupportsGraph` (`protocol.py:298-309`) | **absent** | **absent** (mkedge live, `memory.py:460`; traversal not) |

Supporting machinery status:

- The **chunk/gram/embedding schema is fully provisioned** — `chunks`,
  `gram_epochs`, `posting_list` tables (`rows.py:398-483`) — but the live
  write path **mints no chunk rows yet**: `writes.py` never calls
  `Chunk.split` (its "chunk" vocabulary is bind-budget chunking,
  `writes.py:389-446`). Chunks, grams, and embeddings are model+schema-ready,
  pipeline-unwired.
- Capabilities are hand-declared per landed pass, so the router never routes
  glean/graph to the database backend (`backend.py:54-58`, `backend.py:90-91`).
- The one Result vocabulary already carries everything search needs:
  `Observation.score/matches`, `Match.start/end/match/content/score`
  (`entry.py:335-410`).

Consequence for the brief: for grep-the-index, glean, and graph, "what media
extension requires" is a question about **designs already pinned in memos and
schema**, not about shipped query code. That is the best possible timing — the
media story can land in the design before the code exists to retrofit.

## 1. glob — name-space matching; media is near-free, with two gaps

**What glob consumes today.** Nothing but namespace metadata:

- The subject is the path or the name — a slash in the pattern matches whole
  paths, a bare pattern matches names; `fnmatch` is the single match
  authority (`globbing.py:1-13`, `globbing.py:31-36`).
- The `ext` filter reads the **path-derived** extension, deliberately never a
  stored column (`globbing.py:8-9`, `globbing.py:36`; `reads.py` glob uses
  `compile_glob`, `reads.py:203`).
- The database implementation prefilters with sargable escaped `LIKE` on the
  path cache and verifies authoritatively with `fnmatch` in Python
  (`reads.py:14-17`, `reads.py:183-227`) — glob never touches content.
- Projection: the default fetched set already includes `mime_type`,
  `content_hash`, `size_bytes`, `kind` (`reads.py:51-53`,
  `reads.py:68-84`) — a glob **row** can report media metadata today.

**Media extension analysis.**

- *What exists*: media entries are ordinary entries rows, so glob works on
  them the day they exist — name/path matching, `ext` filtering
  (`*.png`, `ext=("png","jpg")`), and mime/kind **visible in output**. The
  schema even carries a composite `ix_<t>_ext_kind` index (`rows.py:359`)
  and an indexed `kind` column (`rows.py:345`).
- *Gap 1 — no mime predicate.* There is no way to ask glob for
  `mime_type LIKE 'image/%'`. Extension is a proxy that lies exactly where
  media lies (a `.bin` upload with `mime_type=image/png`; extension-less
  blobs). The verb signature (`base.py:1001-1011`) and protocol
  (`protocol.py:154-164`) take only `pattern`/`ext`. A `mime=("image/*",)`
  parameter would be a pure metadata predicate — same sargability story as
  `ext`, backed by the existing `mime_type` column (`rows.py:348`).
- *Gap 2 — no kind predicate.* `ObjectKind` is only `file | directory`
  (`paths.py:32`). If the storage design gives media entries a distinct kind
  (or keeps `file` and distinguishes by mime), glob has no kind filter
  either way. Whether that matters is downstream of the brief's Q5
  (exclusivity by kind vs by mime): **whichever axis the exclusivity rule
  picks is the axis glob must be able to filter on**, or agents cannot
  enumerate "all media under /x" without a client-side pass.

Verdict: glob is the cheap verb the brief assumed ("near-free", brief line
103) — but "free" only for name/ext addressing. Mime-prefix filtering is the
one concrete addition worth speccing, and it is the *same* addition the
result-content memo's placeholder rendering wants (media identified by mime,
result-content memo's F2 kind/mime gate).

## 2. grep — the contract that raw media can never satisfy

**The contract, precisely.** grep is defined by a two-layer discipline, and
both layers are text-typed:

1. **Authoritative match is Python `re` over stored text.** The index layer
   is only a candidate generator: "It may admit false positives but must
   never introduce false negatives — the authoritative match is always run
   in Python afterward by the caller" (`code_grams.py:6-9`). The grep-index
   memo pins "unconditional Python `re` verify" in the execution design
   (`2026-07-13-database-storage-grep-index.md:340-344`) and recommends
   Python-authoritative over engine-regex semantics (same memo, §4 gotcha 3).
   The scan tier implements exactly this: `re.compile` + per-line
   `regex.search` (`memory.py:793-828`).
2. **The match unit is the line.** `_grep_file` splits content into lines and
   matches line-by-line (`memory.py:824-828`); `Match.start/end` are
   1-indexed line bounds and `match` is the hit line (`entry.py:335-345`);
   `before_context`/`after_context` are line counts (`base.py:1057-1058`).

Why raw media can never satisfy it, stated as type facts rather than taste:

- The pattern is `str` and the corpus is `str`. Bytes cannot even *reach* the
  matcher: `Entry.content: str | None` with null-byte rejection
  (`entry.py:86`, `entry.py:132-139`), same rejection on `Chunk.content`
  (`chunk.py:50-57`). A PNG is not storable as content, so there is nothing
  for `re` to run over — this is the brief's prerequisite gap restated at
  the verb layer.
- The index stream is UTF-8 byte trigrams **of text**: newline-normalized,
  Turkic-folded, casefolded codepoints (`code_grams.py:26-48`,
  `code_grams.py:67-89`). Trigrams over raw media bytes would be
  well-defined mechanically and meaningless semantically — no line
  structure, no case, no `re` verify possible — and the verify step is not
  optional, it *is* the contract.
- The scan tier already encodes the media answer: rows with `content is None`
  or kind outside `CONTENT_KINDS` are skipped silently (`memory.py:277`,
  `CONTENT_KINDS` = `{"file","chunk","version"}`, `entry.py:41-43`). Not an
  error, not a match: invisible.

**Grep-over-derived-text: does the machinery already carry it?** Mostly yes —
this is the strongest finding of the study. Trace the pipeline:

- `Chunk` is keyed `(entry_id, chunk_index)` and carries its own text,
  line range, `content_hash`, `encoded` gram-dirty flag, and `embedding`
  (`chunk.py:32-48`, `rows.py:398-417`). Nothing anywhere asserts a chunk's
  content is a substring of the owning entry's `content` row — the linkage
  is identity (`entry_id`), not text equality. **Derived-text chunks
  attached to a media entry violate no invariant in the chunk model, the
  chunks table, or the gram index.** The posting list stores doc-ids that
  are chunk-row PKs (`rows.py:17-19`, `rows.py:399-401`); a doc-id pointing
  at OCR text is indistinguishable from one pointing at source code.
- `Chunk.split` dispatches by ext (`chunk.py:74-88`); media extensions have
  no tree-sitter grammar so they fall to the recursive splitter
  (`chunking.py:169-177`) — derived text (a transcript, OCR output) chunks
  fine through the generic path, or better, through the ext of its *derived
  form* (`.md` transcript → markdown grammar).

What does **not** just work — three genuine seams:

1. **The verify/context source.** Indexed grep's design is: intersect
   postings → fetch content → Python-verify → emit line regions with
   context (grep-index memo §6). For a text file, "fetch content" is the
   `content` table via `content_joined` (`rows.py:288-290`). A media entry
   has no text content row — so the verify and the context windows must run
   over **the derived text document itself**. Either the derived text is
   readable as a document (a sidecar entry, or a derived-artifacts table the
   grep executor can fetch from), or verify runs per-chunk over
   `chunks.content` alone — which breaks `before_context`/`after_context`
   across chunk boundaries and breaks `invert_match`/`count` semantics that
   are defined per *file*, not per chunk. **The storage half's Q6 choice
   (where derived text lives) is therefore also a grep-correctness choice**:
   grep needs a whole-document text fetch for the media entry, whatever the
   blob-home answer is.
2. **What a Match means.** Line regions in derived text index into a document
   the caller may never have read. For a transcript "line 42" is meaningful
   only against the transcript; the sibling memo's B4 (anchored media
   regions — time ranges, page/bbox) is the honest extension, and Match
   today has no anchor vocabulary beyond lines (`entry.py:335-354`).
   Minimum viable coherence: grep over media returns hits whose `path` is
   the media entry but whose regions address its derived text — the result
   must say so (e.g. matches carry the derived doc's address), or agents
   will `read` the media entry expecting the matched lines.
3. **Filter semantics.** `ext`/`globs` filters read the *entry's* path
   (`memory.py:279-285`), so `grep --ext md` would not match OCR text
   attached to a `.png` — correct, but the inverse matters: does
   `grep --ext png pattern` mean "grep the derived text of PNGs"? That reads
   naturally and should be stated as the intended semantics.

**The false-negatives-never doctrine over media — a contract statement.**
The doctrine (`code_grams.py:6-9`, `code_grams.py:415-417`) is defined
*relative to the authoritative matcher*: a false negative is a candidate
pruned that Python `re` would have matched. A media entry with no derived
text gives the authoritative matcher **no text to match** — so invisibility
is not a false negative; it is the correct value of the contract, already
implemented in the scan tier's `content is None` skip (`memory.py:277`).
The memo should state it exactly that way:

> grep's corpus is *stored text*: text-entry content plus whatever derived
> text a media entry carries. A media entry with no derived text is not in
> the corpus and matches nothing — by contract, not by accident.

But the doctrine then cuts the other way with real teeth: **once derived
text exists, it is corpus**, and an unindexed or stale derived-text chunk
*is* a false negative relative to the authoritative match over that stored
text. Freshness of derived text against the version chain (brief Q6/Q10)
is therefore a grep-soundness requirement, not a nicety — it must ride the
same machinery as ordinary content: the `encoded` dirty flag
(`rows.py:399-402`, `chunk.py:36-38`), the epoch watermark and dirty
overlay (grep-index memo §6), and the declared `grep_staleness` trait
(`protocol.py:86-96`).

## 3. glean — embeddings attach to chunk rows; multiple spaces are a schema gap

**Where embeddings attach today.** One place: the chunk.

- `chunks.embedding` column (`rows.py:412`), model field
  `Chunk.embedding: Vector | None`, "populated by the indexing pipeline,
  never at split time" (`chunk.py:36-38`, `chunk.py:48`).
- Embedding staleness needs no flag — `embedding IS NULL`
  (`rows.py:400-402`).
- No entry-level or version-level embedding exists anywhere in the schema.

**Dimension and model tracking — anticipated but half-materialized.**

- `Vector[dim, "model"]` subclasses validate length and carry a model name
  (`vector.py:64-113`); `VectorType` refuses a bind whose vector's model
  name mismatches the column's (`vector.py:216-223`) and refuses wrong
  dimensions on both read and write (`vector.py:212-215`,
  `vector.py:260-262`).
- But the tracking is **type-level, not row-level**: model identity lives in
  the column's `VectorType(model_name=...)` configuration
  (`rows.py:318-328`), one per mount via `NativeEmbeddingConfig`
  (`vector.py:48-62`) — a single space per chunks table, by construction.
  There is no `model_name` **column**, so no row can say which space its
  vector lives in, and no query can filter by space.
- Portability floor: JSON-text serialization on every engine, native
  pgvector only on demand (`vector.py:143-153`, `vector.py:184-187`) —
  and a native `vector(N)` column hard-pins one dimension, so
  **multiple spaces can never share one native column**.

**What multiple embedding spaces require.** The brief's hypothesis (text
chunks in a text space, media in a joint space, brief Q8) needs:

1. *Schema*: either (a) an embeddings side-table keyed
   `(chunk_id | entry_id, space)` with `space` naming the model, dimension
   as data, vector as JSON-text (native pgvector variant = one partial
   index or one physical column per declared space); or (b) N embedding
   columns minted from N `NativeEmbeddingConfig`s. (a) is the shape that
   survives "add a space" without DDL on the hot chunks table and mirrors
   how `posting_list` already sits beside chunks as a regenerable
   epoch-scoped store (`rows.py:468-483`). Either way, **filter-by-model
   becomes a row predicate** (`WHERE space = :s`), which today is
   impossible.
2. *Query*: glean's public contract already licenses fan-out-and-fuse. The
   docstring pins: "The caller never picks a retrieval strategy — backends
   index by vector, lexical, and graph signals and fuse the rankings
   however they see fit," with cross-entry scores only loosely comparable
   (`base.py:1127-1135`). Fusing *per-space* rankings (text-space kNN +
   joint-space kNN + lexical) is the same move one level down; rank-based
   fusion (RRF-style) rather than score mixing is the honest choice given
   the contract already disclaims score comparability. **No verb-signature
   change is needed for text queries.**
3. *The genuinely new input*: query-by-example (find images like this image)
   requires a non-`str` query, which `glean(query: str, ...)`
   (`base.py:1117-1126`, `protocol.py:198-207`) cannot carry. That is a
   wire-format question the result-content memo's typed blocks already
   answer for *outputs*; the memo should decide whether media queries enter
   scope now or are declared deferred. A path-as-query convention
   ("glean like /photos/a.png") would fit the existing signature.
4. *Chunking media for the joint space*: a media entry's "chunks" in a joint
   space are not text splits (a page image, a crop, an audio window).
   Today's chunk row demands `content: str` NOT NULL and line ranges
   (`rows.py:407-413`) — a media chunk would need either a parallel
   media-chunk table or a relaxation of the chunk row (content nullable,
   region columns). This is the chunk-layer twin of the storage half's
   sidecar decision and should be settled with it.

## 4. graph — edges are identity triples; media works unchanged

**Verification the brief asked for.** Edges carry no content and no path:
narrow ID triples `(source_id, target_id, edge_type)` with weight/distance,
both traversal directions indexed (`rows.py:419-435`, the comment at
`rows.py:419-421`: "No path columns — liveness and addressing come from
joining entries"). The `Edge` model validates endpoints only as non-root,
non-meta user-space paths (`edge.py:35-48`) — nothing inspects kind, mime,
or content. A media entry is an ordinary entries row with an `entry_id`
(`rows.py:334-365`), so:

- `mkedge(media → anything)` and `(anything → media)` are **valid by
  construction** the day media entries exist. (Caveat: `mkedge` is a stub on
  DatabaseStorage, `backend.py:383-391`; the memory backend stores edges
  keyed by path triple, `memory.py:106-108`, `memory.py:460`.)
- Traversal, when it lands, joins edges to entries by identity; media rows
  join like any rows. The graph verb's contract — per-entry subgraph, method
  validated against a traversal vocabulary, analytics are index-time data
  (`base.py:1162-1169`) — is media-indifferent. **Verified: nothing to
  change.**

**What media-derived edges could mean.** The extraction pipeline (brief Q6)
is an edge *producer*, and the edge schema is already sufficient for all of
it: `derived_from` (derived-text sidecar entry → its media source — the
natural representation if derived text is a sibling entry; if derived text
is chunk rows on the media entry, no edge is needed at all), `depicts` /
`mentions` (media → entities extracted from EXIF/captions/transcripts),
`thumbnail_of`, `page_of` (per-page images of a PDF). All are typed,
directed, optionally weighted (confidence in `weight`) — exactly the
existing columns. The one pending schema item is pre-existing and
media-independent: `Edge.version` has no column yet
(`rows.py:104-108`).

One design note: if derived text becomes hidden sibling entries, the
`derived_from` edge becomes lifecycle-critical (sweep of the media entry
must find its derived artifacts) — which argues for either the
derived-artifacts table (explicit FK lifecycle) or edges plus a declared
cascade rule. Dangling edges after a permanent delete are already a general
problem the trash arc handles by identity, not a new media problem.

## 5. Answers to the brief, numbered

- **Q6 (derived text, the chunk question)**: derived-text chunks on a media
  entry *just work* for candidate generation and embedding — chunk identity
  is `entry_id`, not content lineage (§2). They do **not** just work for
  grep's verify/context/invert semantics, which need a whole-document text
  fetch; the derived-text home must be readable as a document, and Match
  regions must be declared as addressing it (§2 seams 1–2).
- **Q7 (per-verb meaning)**: glob — works now; add a mime-prefix predicate
  (and a kind predicate if the exclusivity rule is kind-based) (§1). grep —
  text-only *by contract*; media participates exactly through derived text;
  no-derived-text ⇒ invisible, stated as contract (§2). glean — the frontier
  is real but the verb contract already accommodates fan-out-and-fuse; the
  schema does not yet accommodate multiple spaces (§3). graph — unchanged;
  media-derived edges are producers for the existing schema (§4).
- **Q8 (multiple spaces)**: anticipated by `Vector`'s model tracking but
  blocked by type-level-only model identity and the one-column-one-space
  chunks schema; requires a space-keyed embeddings store and row-level model
  identity; fusion is in-contract (§3).
- **Q10 (lifecycle/staleness)**: for search specifically, derived-text
  freshness is a *soundness* requirement once derived text exists (§2);
  embedding staleness already has its idiom (`embedding IS NULL`), gram
  staleness its flag + watermark; media needs the same three hooks wired to
  the version chain, plus `lines` declared meaningless for media (`lines`
  is computed from text today, `entry.py:118-127`, and the Observation
  layer already nulls metrics for non-content kinds, `entry.py:412-434`).

## 6. Smallest-contract summary

The four verbs partition cleanly over media, and the partition can be stated
in one sentence each:

- **glob** matches *names and metadata* — media joins by existing, needs a
  mime predicate to be addressable as media.
- **grep** matches *stored text* — media joins exactly by carrying derived
  text; without it, invisible by contract.
- **glean** ranks *indexed representations* — media joins by being embedded
  into some space; the fusion contract already covers many spaces, the
  schema does not yet.
- **graph** walks *identities* — media joined the day it got an `entry_id`.
