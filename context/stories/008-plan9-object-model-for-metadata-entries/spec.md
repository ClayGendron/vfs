# 008 — Unified object model for edges, versions, and chunks

- **Status:** draft
- **Date:** 2026-04-22
- **Owner:** Clay Gendron
- **Kind:** feature (object model on top of 002's namespace)

## Intent

`002` standardized the metadata namespace:

```text
/.vfs/<path>/__meta__/chunks/...
/.vfs/<path>/__meta__/versions/...
/.vfs/<path>/__meta__/edges/{out,in}/...
```

This story standardizes the object model that namespace resolves to.

1. **Unix dirent/object separation.** Listing rows are names, not full objects. `Entry` is dirent-like; `stat` resolves the underlying object.
2. **Plan 9 ordinary-file discipline.** Synthetic resources should participate in ordinary `walk`, `stat`, `read`, and, where appropriate, `write`, without introducing `ctl`, `clone`, or `wstat`-style domain APIs.
3. **Human-meaningful canonical browse paths.** The public metadata tree remains endpoint-rooted under `/.vfs/.../__meta__/...`.
4. **Stable object identity where it matters.** An edge is not just a path encoding. It has a stored identity that survives endpoint rename and is surfaced through `stat`.
5. **Per-file immutable history.** Versions are append-only snapshot-files that make rollback a first-class VFS behavior.
6. **Chunks as named views, not mini-files.** A chunk is a selector-backed subview of a file, optionally pinned to a basis version.

After this story:

- `ls`, `tree`, and `glob` stay cheap and dirent-minimal
- `stat` is the rich identity/metadata surface
- `read` is the canonical content/record surface
- edge identity is stable and not derived solely from the browse path
- versions are immutable historical file states
- chunks are named selectors over files, not detached writable blobs

## Why

- **`002` solved path representability, not ontology.** We now need a crisp answer to what an edge/version/chunk actually is.
- **Edge rename stability is load-bearing.** Path-derived edge identity makes file moves look like delete-and-recreate, which is the wrong model for authored relations.
- **Versions are the clean rollback primitive.** Append-only per-file history is a useful product guarantee and a better fit than whole-tree time travel.
- **Chunks are better modeled as addresses than as peers.** Unix and Plan 9 give strong precedent for immutable versions and file-like synthetic objects, but weak precedent for "chunk as independent file with its own writable content."
- **Listing and inspection should remain separate.** The current `Entry` row is a good dirent surface; it should not be overloaded to carry every kind-specific detail.
- **One namespace, different object semantics.** The same `/.vfs/.../__meta__/...` path family can host different object kinds as long as each kind has a clear identity and mutability model.

## Scope

### In

1. Define the unified object semantics for edges, versions, and chunks under `/.vfs/.../__meta__/...`.
2. Keep `Entry` dirent-minimal for listing operations.
3. Define the richer metadata surfaces returned by `stat` for edge/version/chunk paths.
4. Define the canonical `read` behavior for edges, versions, and chunks.
5. Standardize edge identity as a stored stable object id surfaced through `stat`, while keeping endpoint-rooted canonical browse paths.
6. Standardize versions as append-only immutable per-file snapshot-files with symbolic references such as `head`, `prev`, and `-k`.
7. Standardize chunks as selector-backed views, including live vs pinned behavior.
8. Preserve the `002` capability matrix:
   - file: `chunks/`, `versions/`, `edges/{out,in}/`
   - chunk: `edges/{out,in}/`
   - version: `edges/{out,in}/`
   - edge: no `__meta__`

### Out

- No change to the `002` path shape.
- No dump-filesystem-style whole-tree time travel.
- No global canonical edge path such as `/.vfs/__meta__/edges/<edge-id>` in this story.
- No path-derived edge identity as the source of truth.
- No direct `write(chunk, content)` semantics that treat a chunk as an independent mini-file.
- No `ctl`, `clone`, `data`, or `wstat` patterns for these metadata objects.
- No chunk-versioning or edge-versioning axes independent of file history.

## Core model

This story standardizes the following ontology:

- **file** — the primary mutable content object
- **version** — an immutable historical state of one file
- **chunk** — a named selector-backed view over one file
- **edge** — a first-class relation between two canonical endpoints

The core rule is:

- listings expose names
- `stat` exposes identity and kind-specific metadata
- `read` exposes canonical content or canonical record text
- not every object kind is writable, but where mutation is allowed it happens through `write()` on the object path

## Dirent vs object contract

### Listing contract

`ls`, `tree`, and `glob` return minimal dirent-like `Entry` rows:

- `path`
- `kind`
- any other existing generic listing fields only where already justified for that operation

They do not have to expose complete object identity, selector metadata, version counters, or edge attributes.

### Stat contract

`stat` is the rich inspection surface.

For any path that names an edge, version, or chunk object:

- `stat` must expose stable object identity
- `stat` must expose kind-specific metadata
- two different paths naming the same underlying object must report the same stable identity

This story refers to those surfaces as `EdgeStat`, `VersionStat`, and `ChunkStat`. They may be implemented as concrete Python models, a richer `Entry` variant for `stat`, or another structured payload. The requirement is semantic, not tied to one type definition.

### Read contract

`read` is the canonical content surface:

- `read(edge)` returns a small textual record describing the relation
- `read(version)` returns the historical file content at that version
- `read(chunk)` returns the resolved chunk content from the live file or pinned version

## Edges

### Design intent

An edge is a first-class relation object, not merely a source-side pathname convention.

The public canonical browse path of an edge remains:

```text
/.vfs/<source>/__meta__/edges/out/<type>/<target-without-leading-slash>
```

The inverse browse path remains:

```text
/.vfs/<target>/__meta__/edges/in/<type>/<source-without-leading-slash>
```

These paths are two names for the same underlying edge object.

### Identity

Every edge has a stored stable `edge_id`.

Required properties:

- `edge_id` is not derived solely from `(source_path, edge_type, target_path)`
- `edge_id` is identical across `edges/out` and `edges/in` views of the same relation
- renaming or moving an endpoint does not allocate a brand-new edge identity
- a backend may additionally expose a derived `edge_key` or fingerprint for deduplication, but that fingerprint is not the canonical identity

This is the main semantic correction relative to `008-a`.

### Canonical and projected paths

The user-facing canonical path is always the `edges/out/...` form.

`EdgeStat.canonical_path` must therefore always be:

```text
/.vfs/<source>/__meta__/edges/out/<type>/<target-without-leading-slash>
```

even when the caller reached the edge through the inverse `edges/in/...` view.

The path is canonical for browsing and writing. The stored `edge_id` is canonical for identity.

### `EdgeStat`

At minimum, `stat` on an edge path must expose:

| Field | Meaning |
|---|---|
| `path` | the resolved path the caller used |
| `kind` | `"edge"` |
| `edge_id` | stable stored identity for the relation |
| `attr_version` | increments on edge-attribute mutation |
| `canonical_path` | always the `edges/out/...` path |
| `view` | `"out"` or `"in"` |
| `source_path` | canonical VFS path of the edge source |
| `target_path` | canonical VFS path of the edge target |
| `edge_type` | relation label |
| `attached_to` | `"head"` or `"version:<n>"` |
| `mode` | POSIX-style mode bits |
| `updated_at` | timestamp of last edge-attribute mutation |
| `size_bytes` | size of the canonical text record returned by `read` |

If endpoint object ids exist independently from paths, the edge stat surface should also expose them.

### `read(edge)` record

`read(edge)` returns a small canonical text record.

Canonical shape:

```text
type imports
source /src/a.py
target /src/b.py
canonical /.vfs/src/a.py/__meta__/edges/out/imports/src/b.py
view out
id e:3f9c1a8b...
attr_version 3
attached head
```

The exact text format may evolve, but it must be stable, human-readable, and sufficient to inspect the edge as a first-class object.

### `write(edge, record)` semantics

`write(edge, text)` is allowed for edge attributes only.

Required behavior:

- `source`, `target`, and `type` are immutable after creation
- attempting to change `source`, `target`, or `type` fails validation before backend mutation
- attribute fields such as weight, distance, labels, or similar domain metadata may be updated through the record
- each successful attribute write bumps `attr_version`
- a write through `edges/in/...` mutates the same underlying object as a write through `edges/out/...`

### Rename / move behavior

When a file, chunk, or version endpoint is renamed or moved:

- the edge object identity remains the same
- its projected browse paths are rewritten or reprojected to the endpoint's new canonical path
- the edge is not treated as a delete-and-recreate event merely because one endpoint pathname changed

### Listing semantics

`ls` on `edges/out/<type>/` returns dirent rows naming each target under the embedded-path projection.

`ls` on `edges/in/<type>/` returns dirent rows naming each source under the embedded-path projection.

Intermediate directories under the embedded source/target path remain synthetic browse directories only. They are not user-authored directories and they never expose nested `__meta__/`.

## Versions

### Design intent

A version is an immutable historical state of a file's content.

Versions exist for safe rollback and auditable history. They are not mutable diff rows and not whole-tree snapshots.

### Canonical path

```text
/.vfs/<file>/__meta__/versions/<n>
```

`<n>` is a monotonically increasing integer per file, starting at `1`.

### Symbolic references

The following symbolic version paths are supported as synthetic references:

```text
/.vfs/<file>/__meta__/versions/head
/.vfs/<file>/__meta__/versions/prev
/.vfs/<file>/__meta__/versions/-1
/.vfs/<file>/__meta__/versions/-2
```

These resolve to the underlying numeric version at read/stat time. They are not distinct stored objects.

### `VersionStat`

At minimum, `stat` on a version path must expose:

| Field | Meaning |
|---|---|
| `path` | the resolved path the caller used |
| `kind` | `"version"` |
| `version_number` | the numeric version this path resolves to |
| `is_head` | `true` if this version is currently head |
| `owner_path` | canonical path of the owning file |
| `size_bytes` | size of the historical content |
| `content_hash` | content hash |
| `created_at` | timestamp of version creation |
| `is_snapshot` | informational backend detail for storage strategy |
| `restored_from` | optional source version number if this head was created by rollback |

### Bare-file `stat` additions

`stat(file)` on the live file path must expose:

| Field | Meaning |
|---|---|
| `version_head` | current head version number |
| `version_count` | total number of retained versions |

### Read/write semantics

- `read(file)` returns head content.
- `read(versions/<n>)` returns historical content at version `<n>`.
- `read(versions/head)` and related aliases resolve to the same underlying version content.
- `write(file, content)` is atomic, creates a new version `version_head + 1`, and flips head.
- `write(versions/<n>, ...)` is rejected for numeric and symbolic version paths alike.
- rollback is expressed as `write(file, read(versions/<n>))`; this creates a new head version rather than mutating the old version.

### Attachment behavior

Versions may act as edge endpoints.

Edges attached to a specific version endpoint are authored state on that immutable historical endpoint. They do not re-derive when the live file head changes.

Versions do not expose nested `versions/` or `chunks/`.

## Chunks

### Design intent

A chunk is a named selector-backed view over a file.

This is the main semantic correction relative to `008-a`: a chunk is not an independent writable sub-file blob. It is a named address into a file, optionally frozen to a specific version.

### Canonical path

```text
/.vfs/<file>/__meta__/chunks/<name>
```

When positional ordering matters, chunk names must be zero-padded numeric (`0000`, `0001`, `0002`, ...`) so lexical order matches ordinal order.

Non-numeric names remain legal when ordering is not meaningful.

### Live and pinned chunks

Every chunk is either:

- **live** — resolves against the current head content of the owning file
- **pinned** — resolves against a specific basis version

Pinned chunks must expose `basis_version`.

### Selector semantics

Every chunk must have selector metadata.

The selector may be represented as:

- byte range
- line range
- heading path
- page/span
- syntax-node path
- regex/search address
- another explicit selector kind defined by the backend

This story does not fix one universal selector syntax. It does require that selector metadata, not a detached content blob, is the source of truth.

### `ChunkStat`

At minimum, `stat` on a chunk path must expose:

| Field | Meaning |
|---|---|
| `path` | canonical chunk path |
| `kind` | `"chunk"` |
| `chunk_name` | final path segment |
| `ordinal` | integer position if the name is numeric; null otherwise |
| `selector_kind` | type of selector used |
| `selector_value` | serialized selector value |
| `owner_path` | canonical path of the owning file |
| `basis_version` | null for live chunks; numeric version for pinned chunks |
| `content_hash` | hash of the currently resolved chunk content, when available |
| `size_bytes` | size of the resolved chunk content, when available |
| `updated_at` | timestamp of last selector mutation or re-derivation |

If the backend can cheaply expose byte offsets or lengths for a selector kind, it may do so, but they are not the universal source of truth.

### `read(chunk)` semantics

`read(chunk)` returns the resolved chunk content:

- from current head content for live chunks
- from the pinned historical content for pinned chunks

The chunk path reads like content, not like a metadata record.

### `write(chunk, ...)` semantics

Direct `write(chunk, content)` is rejected in this story.

Reason:

- the chunk is a view, not an independent writable file
- mutating chunk content without an edit model for the parent file would be underspecified

Chunk creation, selector updates, and re-derivation may still exist through backend APIs or future stories, but this story does not standardize direct content writes to a chunk path.

### `chunks/index`

An optional read-only summary file may exist at:

```text
/.vfs/<file>/__meta__/chunks/index
```

When present, `read(chunks/index)` returns a summary of the chunk set, including at minimum:

- ordinal/name
- selector summary
- basis version when pinned
- content hash when available

Backends may synthesize this on demand.

`write(chunks/index, ...)` is rejected.

### Attachment behavior

Chunks may act as edge endpoints.

Chunks do not expose nested `chunks/` or `versions/`.

## Capability matrix

| Endpoint kind | `chunks/` | `versions/` | `edges/{out,in}/` | Structurally terminal? |
|---|---|---|---|---|
| file | ✓ | ✓ | ✓ | no |
| chunk | — | — | ✓ | no |
| version | — | — | ✓ | no |
| edge | — | — | — | yes |

This matrix is the type system. Attempts to construct metadata paths outside these rules fail validation before backend mutation.

## Cross-cutting rules

- **Listing remains minimal.** `Entry` stays dirent-like; richer fields belong on explicit `stat`.
- **Identity is surfaced, not path-encoded.** Stable object identity appears in `stat`; path shape alone is not the full identity story.
- **Synthetic references share identity.** `edges/in`, `versions/head`, `versions/prev`, and negative version aliases are alternate names for underlying objects, not second sources of truth.
- **Mutation is narrow and explicit.** `write(file, ...)` creates new versions. `write(edge, ...)` mutates edge attributes. `write(version, ...)` and `write(chunk, ...)` are rejected.
- **No `ctl`, `clone`, `data`, or `wstat`.** These metadata objects are inspected through `stat`/`read` and mutated only where the object kind explicitly allows `write`.
- **Versioning is per-file, not per-tree.** Only files have a version axis.
- **Edges are structurally terminal.** No meta-edges and no nested metadata under edge leaves.

## Acceptance criteria

A reviewer can verify this story shipped by checking the items below.

### Edge object model

- [ ] `stat` on an `edges/out/...` or `edges/in/...` path returns an `EdgeStat` with the fields defined above.
- [ ] `EdgeStat.edge_id` is identical for the canonical and inverse views of the same directed edge.
- [ ] `EdgeStat.attr_version` is identical across both views and increments only on attribute mutation.
- [ ] `EdgeStat.canonical_path` is always the `edges/out/...` form, even when queried via `edges/in/...`.
- [ ] `read(edge)` returns the documented text record with stable field order.
- [ ] `write(edge, record)` with modified attributes bumps `attr_version` and is reflected on both views.
- [ ] `write(edge, record)` that changes `source`, `target`, or `type` fails validation before backend mutation.
- [ ] Renaming or moving an endpoint does not allocate a new `edge_id`.

### Version object model

- [ ] `stat` on a bare file path includes `version_head` and `version_count`.
- [ ] `stat` on `versions/<n>`, `versions/head`, `versions/prev`, and `versions/-k` returns a `VersionStat` with `version_number` resolved to the numeric version.
- [ ] Writing a new file creates version `1`. Every subsequent `write(file, ...)` creates `version_head + 1` and flips head.
- [ ] `read(file)` == `read(versions/head)` == `read(versions/<version_head>)` for any point-in-time snapshot.
- [ ] `read(versions/prev)` == `read(versions/<version_head - 1>)` when `version_head > 1`.
- [ ] `write(versions/<n>, ...)` fails for any `n`, including symbolic aliases.
- [ ] Rollback (`write(file, read(versions/<n>))`) produces a new head version rather than mutating version `<n>`.

### Chunk object model

- [ ] `stat` on a chunk path returns a `ChunkStat` with selector metadata and owner-path metadata.
- [ ] Every chunk has a selector source of truth rather than only detached stored content.
- [ ] Ordered chunkers use zero-padded numeric names, and lexical listing order matches chunk ordinal order.
- [ ] `read(chunk)` returns resolved content from head or the pinned basis version.
- [ ] `write(chunk, ...)` is rejected.
- [ ] `read(chunks/index)` returns the summary surface when supported.
- [ ] `write(chunks/index, ...)` is rejected.

### Capability enforcement

- [ ] `ls` on an edge path shows no `__meta__/` subtree.
- [ ] `ls` on a chunk path's `__meta__/` shows only `edges/`.
- [ ] `ls` on a version path's `__meta__/` shows only `edges/`.
- [ ] Attempted writes that introduce forbidden metadata nesting fail validation before backend mutation.

### Listing minimality

- [ ] `Entry` rows returned by `ls`, `tree`, and `glob` remain dirent-minimal.
- [ ] Rich edge/version/chunk metadata is only returned by explicit `stat`.

### Mutation surface

- [ ] No public verb exposes `wstat`-style mutation of domain attributes.
- [ ] No `ctl`, `data`, or `clone` files are exposed for metadata objects.
- [ ] All allowed mutations flow through `write()` on the object's path.

## Test strategy

- `tests/test_stat_surface.py` — coverage for `EdgeStat`, `VersionStat`, and `ChunkStat` field presence, stability, and alias resolution.
- `tests/test_versions_safe_rollback.py` — every-write-versioned invariant; symbolic references; rollback producing a new head version.
- `tests/test_edge_record.py` — `read(edge)` record format; edge-attribute mutation; rejection of source/target/type changes; rename preserving `edge_id`.
- `tests/test_chunks_selector_views.py` — selector-backed chunk resolution, pinned-vs-live behavior, ordered naming, and rejection of chunk writes.
- `tests/test_chunks_index.py` — `chunks/index` summary format when present and rejection of index writes.
- `tests/test_capability_matrix.py` — forbidden metadata nesting rejected for every endpoint kind.
- `tests/test_listing_minimality.py` — `Entry` shape stays minimal across listing operations.

## Dependencies and references

- 002 — POSIX-aligned root metadata namespace (defines the path shape this story builds on)
- Current path helpers: [`src/vfs/paths.py`](../../../src/vfs/paths.py)
- Current object model: [`src/vfs/models.py`](../../../src/vfs/models.py)
- Current `Entry` shape: [`src/vfs/results.py`](../../../src/vfs/results.py)
- Unix dirent/inode separation: Ritchie, "The UNIX Time-Sharing System" (CACM 1974)
- Plan 9 `stat` / `walk` semantics: `stat(5)`, `walk(5)`
- Plan 9 lexical naming: Pike, "Lexical File Names in Plan 9, or Getting Dot-Dot Right"
- VMS-style per-file versions as historical precedent for append-only versioned filenames

## Decisions and open questions

- **Resolved:** `Entry` remains dirent-minimal; richer metadata is on explicit `stat`.
- **Resolved:** edge identity is a stored stable id, not just a hash of endpoint paths.
- **Resolved:** the `edges/out/...` path remains the user-facing canonical browse/write path.
- **Resolved:** `edges/in/...` is an alternate view onto the same underlying edge object.
- **Resolved:** versions are append-only immutable snapshot-files with symbolic references.
- **Resolved:** bare-file `stat` includes `version_head` and `version_count`.
- **Resolved:** chunks are selector-backed views, not independent writable content blobs.
- **Resolved:** direct `write(chunk, ...)` is rejected in this story.
- **Resolved:** edges are structurally terminal.
- **Open:** should chunk selector updates later be standardized as `write(chunk, record)` on selector metadata, or through a separate chunk-management API? Recommendation: separate chunk-management API unless a patch-to-parent edit model is specified.
- **Open:** should `chunks/index` be mandatory whenever ordered chunks exist, or remain opt-in? Recommendation: keep it opt-in and synthesize on first read.
- **Open:** should rollback-created versions expose `restored_from` on the public stat surface? Recommendation: yes.
- **Open:** if a backend supports stable endpoint object ids in addition to canonical paths, should edge stats expose both endpoint ids and endpoint paths? Recommendation: yes.
