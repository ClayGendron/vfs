# 030 — Implementation notes

- **Status:** in-progress. **Phase 1 (watermark) + Phase 2 (incremental
  re-chunk) functionally complete.** The write path works end-to-end:
  `tests/test_write_pipeline.py`, `tests/test_paths.py`, and
  `tests/test_models.py` are green (carry-forward, vacated-dir GC, versioned
  chunk paths all covered). **The full suite is NOT green** — the
  materialized-chunk-dir decision (see Decision Log, 2026-05-26) changed what
  `/.vfs/.../__meta__/chunks` contains, so ~197 tests across
  `ls`/`tree`/`glob`/`delete`/row-count assertions now need updating to expect
  the materialized chunk-version dirs. That fallout is **known and accepted**;
  it is the main Phase 2 follow-up. **Phase 3 (`index()`) not started.**
- **Date:** 2026-05-26
- **Spec:** [spec.md](./spec.md) — phasing is §6. **Spec is partly stale** (it
  predates both the versioned-chunk-path and materialized-dir decisions — see
  Decision Log).

## The load-bearing design decision (NEW, supersedes spec §2/§5.3)

**Chunks are tied to a file *version*, not just the file: `chunk → version →
file`.** Chunk paths embed the version:

```
/.vfs/src/auth.py/__meta__/chunks/<VersionNumber>/<LineStart>_<LineEnd>[@<Offset>]
```

Why this matters: the spec's original carry-forward renamed a chunk *in place*
to its new `<line_start>_<line_end>` path. A middle edit shifts many chunks
into each other's old paths, and `vfs_entries.path` is unique **per
statement** (confirmed empirically: SQLite rejects even a single multi-row
`UPDATE ... CASE` that permutes a unique column — both a shift and a swap fail
with `IntegrityError`). That forced the spec's two-phase temp-path rename =
**two flushes**.

Versioning the path dissolves the collision: a new version's chunks live under
`chunks/<N+1>/…`, a **brand-new namespace**, so carried renames, new inserts,
and stale deletes all touch disjoint paths. No temp paths, no two-phase, **one
flush**.

Carry-forward becomes: when a new-version chunk's `content_hash` matches a
previous-version chunk, **rename the existing row** to the new-version path
(update `path` / `name` / `line_start` / `line_end` / `version_number` /
`updated_at`). The row keeps its `id` / `entry_id` / `embedding` **and its
grams** — so no re-embed and no re-gram. Confirmed user decisions:

- **Superseded chunks are deleted, not kept as history** (the chunks dir only
  ever holds the current version's chunks; carried rows move to `<N+1>`, stale
  rows are deleted).
- **Embedding/grams carry by keeping the same row** (rename), never by copying.

## Current state (what's in the tree)

### Done + tested — Phase 1 watermark

- `src/vfs/models.py`: `VFSEntry.indexed_content_hash: str | None`
  (`max_length=64`).
- `src/vfs/columns.py`: `indexed_content_hash` added to the `_fetch_existing`
  load-only set.
- `src/vfs/backends/database.py` `_write_phase_persist`: stamps
  `indexed_content_hash = content_hash` on each persisted row, gated on
  `self._auto_index and persisted.index_content`.
- `tests/test_write_pipeline.py::TestIndexedContentHash` — 4 tests, green.

### Done + smoke-tested — model/path layer for versioned chunks

- `src/vfs/paths.py` `chunk_path(file_path, chunk_name, version)` — **`version`
  is now required**; builds `.../chunks/<version>/<chunk_name>`.
- `src/vfs/models.py` `chunk()` — stamps a **provisional** version
  (`self.version_number or 1`) into each chunk path and sets the chunk's
  `version_number`.
- `src/vfs/models.py` `VFSEntry.set_version(version_number)` — works for
  **file** (sets the column only; path has no version segment), **version**
  (rewrites `.../versions/<N>`), and **chunk** (rewrites
  `.../chunks/<N>/<name>`). Verified across all three kinds.

### Done — Phase 2 write pipeline (`database.py`)

The write path works end-to-end. Final shape:

- **`_write_impl` order**: `auto_chunk` → `validate_chunk_parents` →
  `fetch_existing` → `resolve_parent_dirs` → `index(ctx, …,
  compile_post_list=False)` → `persist`. `fetch_existing` runs **before**
  `resolve_parent_dirs` so chunks carry their final version (stamped inside
  `fetch_existing`) by the time dirs are resolved — this is what lets the dir
  resolver materialize the correct `chunks/<finalV>` dir (decision below).
- `_write_phase_auto_chunk` no longer gates on `changed_paths` — it chunks every
  `index_content` file; unchanged files produce chunks that carry forward as
  no-ops.
- **`_stamp_chunk_versions(ctx)`** (new, called at the end of `fetch_existing`):
  computes the new version per file (new → `1`; changed/revived →
  `existing.version_number + 1`; unchanged → `existing.version_number`) and
  calls `chunk.set_version(v)` on **every** chunk in `write_map` (auto + caller),
  then rebuilds `write_map` once and drops the provisional chunk paths from
  `changed_paths`. **No `ctx.new_versions` map** — the version lives on the rows
  (owner decision 2026-05-26).
- **`_classify_chunks`** rewritten to match by **`(base_path, content_hash)`**
  (stable across versions), fetching existing chunks at
  `chunks/<existing.version_number>`. Produces `ctx.carry_renames`,
  `ctx.stale_chunks`, and `ctx.vacated_chunk_dirs` (old version dirs with no
  surviving chunk).
- `_fetch_existing_chunks(chunk_dirs)` returns **narrowed ORM rows** (now incl.
  `path`; `content` only when `_auto_index`) so a carry mutates the row in place.
- `_stage_chunk_delete_deltas` takes ORM rows (reads `.id` as `doc_id`).
- `_write_phase_auto_index` renamed to **`index(self, ctx, session, *,
  compile_post_list=True)`** (write-path call passes `False`). De-index targets
  `ctx.stale_chunks`. *(Phase 3 will rename this to a private helper — see
  Open questions.)*
- **`_write_phase_persist`** applies the reconcile in **one flush**:
  `session.delete` stale chunks; mutate carried rows
  (`path`/`name`/`parent_path`/`line_start`/`line_end`/`version_number`/
  `updated_at`) to the new chunk's; `_delete_vacated_chunk_dirs` removes emptied
  `chunks/<oldV>` dir rows; then the existing flush emits inserts/carries/deletes
  together. Old/new version namespaces are disjoint, so nothing collides.
- `_WriteContext` gained `existing_chunks`, `stale_chunks`, `carry_renames`,
  `vacated_chunk_dirs`.
- Removed the dead `_StaleChunk`/`_delete_stale_chunks` and the unused
  `update`/`delete` sqlalchemy imports.

### NEW decision this session — materialized chunk dirs under `/.vfs/`

The owner wants real directory rows for the metadata tree under `/.vfs/`. The
`__meta__` and `versions` dirs were already materialized (via the
`version_path(p, 1)` ancestor hack in `resolve_parent_dirs`); this extends the
same mechanism to the **chunk** subtree. With chunks in `write_map` at their
final version, `resolve_parent_dirs` now creates `chunks` and `chunks/<v>` dir
rows (and includes carry-rename targets so a pure-carry re-chunk still
materializes `chunks/<newV>`). On re-chunk, the emptied `chunks/<oldV>` dir is
deleted (`vacated_chunk_dirs`). Explicit `kind="directory"` survives the model
validator (`parse_kind` would say "chunk" for `chunks/<v>`, but explicit kind
wins).

### Known fallout — full suite red (~197 failures, accepted)

Materializing chunk dirs changed the contents of `__meta__/chunks`, so a large
set of `ls`/`tree`/`glob`/`delete`/row-count assertions across the suite now see
extra directory rows and fail. `tests/test_write_pipeline.py`,
`tests/test_paths.py`, and `tests/test_models.py` are **green**. The rest is the
primary Phase 2 follow-up: walk the failures and update expectations to the
materialized-dir reality (or revisit the decision if the fallout is undesirable).

## What the next dev needs to do

1. **Triage the ~197 suite failures** from materialized chunk dirs; update
   `ls`/`tree`/`glob`/`delete`/count expectations. Confirm `delete` cascades
   over the new dir rows correctly.
2. **Phase 3 — `index()`** (see Open questions for the naming split).
3. **Rewrite `spec.md`** §2 non-goal / §4.4 / §5.2 / §5.3 to the versioned-path
   + materialized-dir design (currently describes the superseded in-place rename).

## Open design questions

- **`index()` naming split (Phase 3).** The earlier note wanted "one unified
  method," but the public deferred entry must be
  `VirtualFileSystem.index(path=…, force=…, user_id=…)` → backend `_index_impl`,
  while the write-path indexer is `index(self, ctx, session, *,
  compile_post_list)`. Two incompatible signatures can't be one method (the
  subclass would shadow the public API). **Plan:** rename the write-path method
  to a private helper, add the public `index()`/`_index_impl`, and factor the
  shared "stage gram adds + embed" core so inline and deferred produce identical
  index contents. `compile_post_list=True` (flush to posting blocks) is Phase 4,
  gated on 013 Phase 5.
- **Empty `chunks` parent dir.** When a file fully de-indexes (all chunks stale,
  no new chunks), `chunks/<oldV>` is deleted but the parent `chunks` dir is left
  (now empty). Decide whether to GC it too.

## Phasing (unchanged from spec §6, with the versioned-path amendment)

| Phase | What ships | State |
|---|---|---|
| 1 — watermark column | `indexed_content_hash` + stamp | **done** |
| 2 — incremental re-chunk | versioned chunk paths + carry-forward rename + materialized chunk dirs (one flush) | **functional; full suite red (see fallout)** |
| 3 — `index()` deferred (delta-log MVP) | public `index()`/`_index_impl`: scope scan + orphan GC | not started |
| 4 — `index()` flush/GC on posting blocks | `compile_post_list=True` onto 013 Phase 5 | not started (gated) |

## Decision Log (this story, beyond spec.md §9)

- **2026-05-25** — Phase 1 watermark landed; stamp in `persist` gated on
  `auto_index and index_content`.
- **2026-05-26** — Carry-forward switched from in-place
  `<line_start>_<line_end>` rename to **version-addressed chunk paths**
  (`chunks/<version>/<name>`). Reason: per-statement unique-`path` enforcement
  (verified on SQLite) made the spec's in-place rename require a two-phase
  temp-path sequence (two flushes); a fresh version namespace makes the rename
  collision-free in **one flush**.
- **2026-05-26** — `chunk_path` requires `version`; added `VFSEntry.set_version`
  for file/version/chunk.
- **2026-05-26** — Superseded chunks are **deleted on supersede** (no chunk
  history); embeddings/grams **carry by keeping the same row** (rename), not by
  copying.
- **2026-05-26** — `_write_phase_auto_index` renamed to `index(…)`; the write
  path calls it with `compile_post_list=False`. *(Superseded by the Phase 3
  naming-split plan in Open questions: write-path indexer becomes private, public
  `index()` is added separately — the signatures can't unify.)*
- **2026-05-26** — Chunk version computed **once per file** via
  `_stamp_chunk_versions` in `fetch_existing` and stamped onto **all** chunks
  (caller + auto) uniformly; the version lives on the rows, **no `ctx.new_versions`
  map** (owner pushed back on `_WriteContext` bloat).
- **2026-05-26** — `_write_impl` reordered so `fetch_existing` precedes
  `resolve_parent_dirs` (chunks carry their final version before dirs resolve).
- **2026-05-26** — **Materialize chunk dirs under `/.vfs/`** (owner decision):
  `resolve_parent_dirs` creates `chunks` and `chunks/<v>` directory rows (incl.
  carry-rename targets); re-chunk deletes the emptied `chunks/<oldV>` dir
  (`vacated_chunk_dirs`). This changed `__meta__/chunks` contents and turned the
  full suite red (~197 failures) — accepted as Phase 2 follow-up.

## Files touched

```
context/stories/030-incremental-chunk-indexing/
  spec.md            (PARTLY STALE — predates versioned-path decision; needs rewrite of §2 non-goal, §4.4, §5.2, §5.3)
  implementation.md  (this file)
src/vfs/paths.py            chunk_path: version required; _split_nested_endpoint handles 2-segment chunk paths
src/vfs/models.py           indexed_content_hash; chunk() versioned + provisional version; set_version (file/version/chunk)
src/vfs/columns.py          indexed_content_hash in _fetch_existing load-only
src/vfs/backends/database.py  Phase 1 stamp; Phase 2: reorder, _stamp_chunk_versions, _classify_chunks rewrite,
                              persist reconcile (carries/stale/vacated-dirs), _delete_vacated_chunk_dirs, index() rename
tests/test_write_pipeline.py  TestIndexedContentHash (Phase 1) + versioned-path/carry-forward coverage (green)
tests/test_paths.py           chunk_path(version) signature + versioned endpoint tests (green)
```
