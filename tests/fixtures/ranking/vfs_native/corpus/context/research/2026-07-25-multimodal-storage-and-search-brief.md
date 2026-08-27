# Multimodal storage and search: bytes in the database, media in the verbs (brief)

- **Status**: problem brief — a seed, not the memo. A full research memo
  should supersede this file; it commits us to nothing.
- **Date**: 2026-07-25
- **Owner**: Clay Gendron
- **Question**: Two halves of one gap. **Storage**: the live tree has no
  binary channel — how does vfs store media bytes in the database,
  segmented from text content the way bodies are already segmented from
  metadata, correct at 10,000-file batches on the least generous engine?
  **Search**: once media is stored, what do `glob`, `grep`, `glean`, and
  `graph` mean over it — and what does multimodal embedding capability
  make possible for `glean` in particular?

---

## Why this exists

The multimodal result-content memo
([2026-07-25-multimodal-result-content.md](2026-07-25-multimodal-result-content.md))
settled how media crosses the wire as typed blocks, then named its own
hard prerequisite: **there is no binary channel anywhere in the live
tree.** `Entry.content` and `Observation.content` are `str | None` with
null-byte rejection (`src/vfs/models/entry.py:132-139`). A PNG cannot be
stored, read, or observed. The content-channel ADR cannot land before
the storage bytes story is settled.

The owner's hypothesis, to be tested against prior art: **segment
multimodal content out in storage** — a binary sidecar beside the text
`content` table, not a widening of it — extending the segmentation move
the schema already made once (bodies leave the narrow entries row so
metadata writes never rewrite content, `src/vfs/models/rows.py:82-84`).

The search half exists because storage without retrieval is a warehouse.
Multimodal embedding models (interleaved text+image inputs, one joint
space) and late-interaction document-image retrieval have matured;
`glean` was born text-only but its `Vector` machinery
(`src/vfs/models/vector.py`) is dimension- and model-parameterized
already. The memo should say what multimodal search *will* mean per
verb, so the storage design doesn't foreclose it.

## What exists today (ground truth for the memo)

- **Segmentation precedent**: entries row is narrow metadata; bodies live
  in the `content` table (`src/vfs/models/rows.py:374`), joined by the
  one canonical `content_joined` (`rows.py:288-290`).
- **Versioning**: full snapshots + forward diffs, text-shaped
  (`versions.content`, `versions.version_diff`, `rows.py:378-396`);
  `content_hash` (sha256, `String(64)`) already on every version.
- **Chunks feed all search**: text chunks (`rows.py:398-417`) are the
  indexed/embedded unit — byte-trigram grams for grep candidates
  (`src/vfs/models/code_grams.py`), embeddings for glean.
- **Vectors are engine-portable**: `VectorType` serializes JSON-text by
  default, switches to native pgvector on demand
  (`src/vfs/models/vector.py:1-30`).
- **The four verbs**: `glob`/`grep`/`glean`/`graph` at
  `src/vfs/base.py:1001-1153`, backed by the storage protocol.
- **Lifecycle machinery**: trash → restore → 90-day sweep just landed;
  any blob story must ride it or dangle.
- **Escape-hatch seam**: `Entry.external_id` exists
  (`src/vfs/models/entry.py:73` docstring context).
- **Dialect doctrine**: byte-denominated budgets are established practice
  ([2026-07-23-mysql-support-byte-denominated-path-limits.md](2026-07-23-mysql-support-byte-denominated-path-limits.md));
  bulk-write bind budgets come from
  `storage/backends/database/dialects.py`.

## What the full memo needs to settle

### Storage

1. **The blob home.** A binary sidecar table — but keyed how?
   Entry-keyed rows (simple lifecycle, duplicate bytes across versions)
   vs hash-keyed content-addressed blobs (dedup free, immutable,
   requires GC when the last referencing version is swept). `content_hash`
   already exists; git's object store is the canonical prior art for the
   second shape. How does GC compose with the sweep verb?
2. **Dialect physics of bulk blobs.** `LargeBinary` maps to
   bytea/BLOB/varbinary(max)/LONGBLOB, but: Oracle LOB restrictions on
   `insertmanyvalues`, MySQL `max_allowed_packet`, Postgres TOAST
   behavior and the 1 GB bytea ceiling, SQL Server parameter limits.
   The 10,000-file batch contract likely forces **byte-denominated
   flush chunking** (accumulated payload bytes, not row count).
3. **Size ceilings and the external escape hatch.** A declared per-row
   cap; beyond it, reference-not-bytes (object store / `external_id`),
   projected on the wire as `resource_link`. In scope now or declared
   and deferred?
4. **Binary versioning.** No diff story for bytes — snapshot-only? With
   content addressing, versions become hash references and unchanged
   media costs nothing. Does `pack` skip media entries entirely?
5. **The exclusivity rule.** Text XOR media per entry, decided at
   construction by kind/mime (the result-content memo's F2). What does
   the storage layer enforce vs the model layer?
6. **Derived-text sidecars.** OCR text, transcripts, captions,
   thumbnails: the universal fallback that makes media greppable and
   cheap to preview. Where do they live — hidden sibling entries,
   chunk rows on the media entry, or a derived-artifacts table? Who
   produces them (extraction is a plugin-per-mime story — Tika /
   Spotlight importers / IFilter are the prior art) and how do they
   stay fresh against the version chain?

### Search

7. **Per-verb meaning over media.** `glob`: name/mime/kind filtering —
   near-free. `grep`: text-only forever, or grep-over-derived-text?
   `graph`: edges to media entries should already work — verify.
   `glean`: the real frontier — semantic search over a joint text+image
   space.
8. **Multimodal embedding reality.** Which models (interleaved
   text+image embedders, late-interaction page-image retrieval, audio
   embedding state), what dimensions/costs, and can one corpus carry
   **multiple embedding spaces** (text chunks in a text space, media in
   a joint space) — does `glean` fan out per space and fuse, or demand
   one space? `Vector`'s model-name tracking suggests coexistence was
   anticipated.
9. **Portable ANN.** pgvector is native; every major engine shipped a
   vector type recently (SQL Server, Oracle 23ai, MySQL 9). What is the
   conservative `GENERIC` floor for vector search — JSON-text +
   in-Python scan? At what corpus size does that stop being honest?
10. **Lifecycle composition.** Blobs, derived artifacts, and their
    vectors through trash → restore → sweep; staleness when a media
    entry is rewritten; what `wc`-style metrics mean for bytes
    (`size_bytes` yes, `lines` no).

## Suggested method

Same discipline as the result-content memo: parallel primary-source
studies — git object internals (public docs; the local clone is GPL —
per the license policy, study via git-scm.com/Documentation), engine LOB
+ vector docs and `sqlalchemy` (local, MIT) for what the library models,
permissively-licensed storage systems (`seaweedfs`, `juicefs`, `opendal`,
`filesystem_spec` — all local), extraction-framework architecture (Tika,
Spotlight importers, IFilter — online), multimodal embedding and
retrieval practice (online), and two internal ground-truth studies
(storage layer, search layer). Then an adversarial pass against the
production posture (batch contract, dialect floor, lifecycle). Output: a
full research memo superseding this brief, feeding the storage-bytes ADR
that gates the content-channel ADR.
