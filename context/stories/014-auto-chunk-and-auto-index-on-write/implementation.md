# 014 — Implementation notes

- **Status:** in-progress (Slice 1 complete; Slice 2 = pipeline restructure not started)
- **Date:** 2026-05-03
- **Spec:** [spec.md](./spec.md)
- **Pipeline doc:** [`docs/internals/write_pipeline.md`](../../../docs/internals/write_pipeline.md)

## Slicing plan

| Slice | Scope | Status |
|---|---|---|
| 1 | Public surface, no behavior change | done |
| 2 | Pipeline restructure in base `_write_impl` (change detect, auto-chunk, persist reorder, status population) | not started |
| 3 | Postgres trigram + bulk embed wiring (depends on story 013 phase 2 row store) | not started |
| 4 | Multi-mount router merge in `VFSClient`; delete-side delta staging | not started |

Slice 1 is mechanical — adds the API surface, hooks, and writer formatter
without changing observable write behavior. Existing tests pass unchanged
once positional `write(path, content)` callers migrate to kwargs (see
**Caller migration** below).

## Slice 1 — landed

### Constructor flags on `DatabaseFileSystem`

`src/vfs/backends/database.py` — `__init__` now accepts:

```python
DatabaseFileSystem(
    ...,
    auto_chunk: bool = True,   # default on; bool-coerced
    auto_index: bool = True,   # default on; bool-coerced
)
```

Stored as `self._auto_chunk` / `self._auto_index`. Subclasses
(`PostgresFileSystem`, `MSSQLFileSystem`) inherit without override. The
flags are not read yet by `_write_impl`; that happens in slice 2.

### `write()` signature reshape

`entries` becomes the first positional argument; `path`, `content`,
`overwrite`, `user_id` are keyword-only. Applies to:

- `VirtualFileSystem.write` (`src/vfs/base.py`)
- `VirtualFileSystem._write_impl` (`src/vfs/base.py`)
- `DatabaseFileSystem._write_impl` (`src/vfs/backends/database.py`)
- `VFSClient.write` sync wrapper (`src/vfs/client.py`)

Two call shapes:

```python
await fs.write([entry_a, entry_b])              # primary, positional
await fs.write(path="/foo.txt", content="...")  # convenience, kwargs
```

`_route_single` (`src/vfs/base.py:480`) was updated to dispatch the
resolved path through `path=` kwarg uniformly across all single-path
impls. Verified all `_*_impl` callees accept `path` as a keyword.

### `Candidate.status` field

`src/vfs/results.py` — new field:

```python
status: Literal["created", "updated", "unchanged"] | None = None
```

Propagated through `_merge_candidate` so set-algebra (`&`, `|`, `-`)
preserves status. Added to `CANDIDATE_FIELD_TO_MODEL_COLUMNS` as a
computed field (empty frozenset) — `status` is set by the write
pipeline, never read off a row.

`_write_impl` does **not** populate `status` yet. That's slice 2.

### `VFSResult.__str__` delegation + write formatter

`VFSResult.__str__` now delegates to `to_str()`. A dedicated
`_render_write` helper handles the `write` function:

```text
# Empty
write: nothing to do

# Single-entry success
write success: 1 file, 4 chunks written

  created /repo/main.py

# Multi-entry success
write success: 3 files, 6 chunks written

# Errors only
write errors:
  /repo/auth.py: file + chunks both in batch with index_content=True

# Mixed (multi-mount partial commit)
write errors:
  /docs/notes.md: pgvector dimension mismatch (mssql_docs)

write success: 2 files, 6 chunks written
```

Counts come from walking `result.candidates`, filtering to `kind in
{"file", "chunk", "edge"}`, grouping by `kind`. Version rows are
deliberately excluded from the summary. A status breakdown
(`3 files (1 created, 1 updated, 1 unchanged) written`) is appended
after the file count when the batch contains a mix of statuses.

For single-file batches, `verb = candidate.status or "wrote"` — until
slice 2 wires up status, the fallback `"wrote"` shows up.

Single-line `write success` summary uses the verb "wrote" / specific
status; never the word "candidates."

### Base-class no-op hooks

`DatabaseFileSystem` (`src/vfs/backends/database.py:425`):

```python
async def _stage_chunk_cascade(
    self,
    file_entries: Sequence[VFSEntry],
    *,
    session: AsyncSession,
) -> None: ...   # no-op default

async def _apply_index_maintenance(
    self,
    entries: Sequence[VFSEntry],
    *,
    old_entries: dict[str, VFSEntry] | None = None,
    delete_only: bool = False,
    session: AsyncSession,
) -> None: ...   # no-op default
```

Both default to no-ops so the in-memory and plain-SQL backends keep
working without trigram or embedding stores. `PostgresFileSystem` and
`MSSQLFileSystem` will override in slice 3.

### `EmbeddingProvider.embed_entries`

`src/vfs/embedding.py` — added to the Protocol:

```python
async def embed_entries(self, entries: Sequence[VFSEntry]) -> Sequence[Vector]:
    """Return one vector per input entry, in input order."""
```

`LangChainEmbeddingProvider.embed_entries` is a default adapter that
extracts `entry.content` and delegates to `embed_batch`. Real bulk
behavior (sub-batching, retry, rate-limit handling) is up to the
provider implementation in slice 3.

**Order contract:** vector `i` belongs to entry `i`. Providers that
sub-batch internally must reassemble in slice order before returning;
the base class will use `zip(entries, vectors, strict=True)` to assert
length on assignment. The reference test double for input-order
preservation under sub-batching lives in slice 3 (spec AC 20).

### Caller migration

Positional `write(path, content)` is no longer supported; positional
calls now bind `entries=path`, which fails in `_write_impl`. The
following call shapes were rewritten to keyword form across the
codebase:

- `tests/` — 245 `.write("...", "...")` calls and ~270
  `_write_impl(path, content)` calls
- `examples/cli_query_demo.py`, `examples/demo_dbfs.py`
- `src/vfs/base.py` (the `_copy_impl`/`_move_impl` cross-mount write)

`entries=...` callers are unchanged. Two test files added:

- `tests/test_results.py::TestToStr` — coverage for the new write
  formatter (4 shapes + `str()` delegation + status breakdown).

### Files touched (slice 1)

```
src/vfs/backends/database.py    # auto_chunk/auto_index flags, _write_impl signature, no-op hooks
src/vfs/base.py                 # write() and _write_impl() signature, _route_single dispatch
src/vfs/client.py               # VFSClient.write() signature
src/vfs/columns.py              # status: frozenset() entry
src/vfs/embedding.py            # embed_entries Protocol method + LangChain adapter
src/vfs/results.py              # Candidate.status, __str__ delegation, _render_write
tests/                          # ~515 call-site rewrites + new write-formatter tests
examples/cli_query_demo.py
examples/demo_dbfs.py
```

### Verification

`uv run pytest` — 2457 passed, 108 skipped, no regressions.

## Slice 2 — what's next

Pipeline restructure inside `DatabaseFileSystem._write_impl`. Per the
[pipeline doc](../../../docs/internals/write_pipeline.md), this is where:

1. **Change detection becomes per-entry** — unchanged writes are a true
   no-op (no version row, no chunk cascade, no `UPDATE`, no
   `updated_at` refresh).
2. **Auto-chunk runs in-memory** when `self._auto_chunk` is True:
   - batch-fatal pre-check for `file with index_content=True` plus
     pre-built chunks for the same file
   - call `entry.chunk()` per changed indexable file; append returned
     chunks to the batch
3. **Auto-index runs in-memory + provider call** when
   `self._auto_index` is True:
   - `_apply_index_maintenance(...)` for trigram delta staging
   - one `embed_entries(...)` call per write; assign vectors to
     `entry.embedding`
4. **Single persist phase** reorders the existing logic:
   - stage delete deltas before stale chunks/content disappears
   - `DELETE` stale chunks via `_stage_chunk_cascade`
   - clear stale embeddings for files flipped to `index_content=False`
   - version cuts (existing pipeline)
   - `INSERT` files + chunks + trigram staging rows in one batch
   - `UPDATE` existing files (vectors ride along)
   - commit parent dirs
   - one `await session.flush()`
5. **Populate `Candidate.status`** on every returned candidate
   (`created` / `updated` / `unchanged`). Once populated, the
   formatter's single-file path-line will say `created /foo.py`
   instead of `wrote /foo.py`.

Slice 2 is the risky one — it rewrites the hottest write path. Cover
with the existing `test_database.py` and `test_write_pressure.py`
fleets plus new tests for the change-detection no-op (existing
`updated_at` byte-identical before and after) and the auto-chunk
conflict pre-check.

## Open follow-ups (slice 3+ deliverables)

- **Story 013 phase 2** must land before `PostgresFileSystem` can
  implement real `_stage_chunk_cascade` / `_apply_index_maintenance`
  hooks (the row-store DDL `vfs_entry_chunk_grams` does not exist yet).
- **EmbeddingProvider input-order test** (spec AC 20) — reference test
  double that proves a sub-batching provider returns vectors in input
  order even when sub-batches complete out of order. Slice 3.
- **Multi-mount partial commit** — `VFSClient.write()` flatten-and-merge
  with both blocks in `to_str()`. Slice 4.
- **Delete-side delta staging** in `_delete_impl`. Slice 4.
