# 025 — Modularize Database Write Impl

- **Status:** draft
- **Date:** 2026-05-03
- **Owner:** Clay Gendron
- **Kind:** refactor + backend
- **Depends on:** 014 (auto-chunk and auto-index on write), existing
  `DatabaseFileSystem._write_impl` behavior
- **Enables:** safer write-pipeline maintenance; targeted backend hooks
  for Postgres/MSSQL write-side index work

## Intent

Refactor `DatabaseFileSystem._write_impl` from one long, linear method
into a small orchestrator plus named private pipeline phases, without
changing the public write contract or observable database behavior.

Story 014 made write do real orchestration: validate, resolve parents,
fetch existing rows and version hashes, detect changes, auto-chunk,
auto-index, persist, create parent directories, and invalidate graph
state. The current implementation is readable as a commented pipeline,
but its size makes future changes risky. A bug fix in auto-index now
requires editing the same method that owns path validation, version
creation, parent directory revival, overwrite semantics, and final
result shaping.

This story turns the existing comments into actual code boundaries.

## Why

- **The method has crossed the readability threshold.** The current
  `_write_impl` is already organized as phases, but each phase lives in
  the same local scope and shares many ad hoc variables.
- **Write-side maintenance will keep growing.** Auto-chunk, trigram
  staging, embeddings, native Postgres/MSSQL search maintenance, and
  future deferred compaction all attach to the same write pipeline.
- **Subclass extension points should stay narrow.** Backends should be
  able to customize index/chunk maintenance without copy-pasting the
  whole write implementation.
- **Tests should lock behavior, not method shape.** A mechanical
  refactor with focused phase helpers gives the test suite a clearer
  target and makes later behavioral stories smaller.

## Scope

### In

1. **Introduce a private write context.**

   Add a private dataclass near the database backend implementation:

   ```python
   @dataclass
   class _WriteContext:
       write_map: dict[str, VFSEntry]
       overwrite: bool
       user_id: str | None
       errors: list[str] = field(default_factory=list)
       existing_map: dict[str, VFSEntry] = field(default_factory=dict)
       latest_version_hash: dict[str, str | None] = field(default_factory=dict)
       parent_dirs: list[VFSEntry] = field(default_factory=list)
       changed_paths: set[str] = field(default_factory=set)
       unchanged_candidates: list[Candidate] = field(default_factory=list)
   ```

   The exact fields may change during implementation, but the context
   must hold shared write-pipeline state so phase helpers do not pass a
   long positional argument list.

2. **Make `_write_impl` an orchestrator.**

   Keep the public/private method signature unchanged:

   ```python
   async def _write_impl(
       self,
       entries: Sequence[VFSEntry] | None = None,
       *,
       path: str | None = None,
       content: str | None = None,
       overwrite: bool = True,
       user_id: str | None = None,
       session: AsyncSession,
   ) -> VFSResult:
       ...
   ```

   Target shape:

   ```python
   async def _write_impl(..., session: AsyncSession) -> VFSResult:
       self._require_user_id(user_id)
       try:
           entries = self._coerce_write_entries(entries, path, content, user_id)
           ctx = self._build_write_context(entries, overwrite, user_id)
           await self._write_phase_validate_chunk_parents(ctx, session)
           await self._write_phase_resolve_parent_dirs(ctx, session)
           await self._write_phase_fetch_existing(ctx, session)
           self._write_phase_detect_changes(ctx)
           if self._auto_chunk:
               await self._write_phase_auto_chunk(ctx)
           if self._auto_index:
               await self._write_phase_auto_index(ctx, session)
           out = await self._write_phase_persist(ctx, session)
       except _WriteAbort as abort:
           return self._error(abort.payload)

       if out and any(c.kind == "edge" for c in out):
           self._graph.invalidate()
       return self._error(
           self._unscope_result(
               VFSResult(
                   function="write",
                   candidates=out,
                   errors=ctx.errors,
                   success=len(ctx.errors) == 0,
               ),
               user_id,
           )
       )
   ```

   The names are illustrative, not mandatory. The important contract is
   that `_write_impl` reads as the write pipeline in order.

3. **Extract current phases without behavioral changes.**

   The implementation should preserve the existing phase order:

   1. Coerce inputs and validate write paths.
   2. Validate chunk parents.
   3. Resolve metadata root and parent directories.
   4. Fetch existing rows.
   5. Fetch latest version hashes.
   6. Detect changed, unchanged, and overwrite-rejected paths.
   7. Auto-chunk changed indexable files.
   8. Auto-index changed indexable entries.
   9. Persist chunk cascade, row inserts/updates, and parent dirs.
   10. Invalidate graph when edge candidates were written.
   11. Return the same scoped/error-handled `VFSResult` shape.

4. **Use one internal abort path for phase-fatal failures.**

   Introduce a private exception:

   ```python
   class _WriteAbort(Exception):
       def __init__(self, payload: str | list[str] | VFSResult) -> None:
           self.payload = payload
   ```

   `_WriteAbort` is a control-flow signal that always represents a
   *failure* — it carries whatever shape the linear `_write_impl`
   originally passed to `self._error(...)` at that phase (a string, a
   list of strings, or a fully shaped failed `VFSResult`). The "nothing
   to do" case (empty input, no errors) is **not** an abort; phases that
   can short-circuit successfully should signal that out-of-band (e.g.
   `_build_write_context` returns `None`) so `_WriteAbort` never carries
   a `success=True` payload.

   A phase may raise `_WriteAbort(...)` only for failures that currently
   return before the persist phase, such as:

   - invalid input that leaves no writable entries with errors collected
   - duplicate path inside a single batch
   - parent directory resolution failure
   - permission rejection on a parent-dir revival
   - auto-chunk conflict (file + chunks both in batch with `index_content=True`)
   - auto-chunk runtime failure
   - index maintenance failure
   - embedding provider failure or vector-count mismatch

   `_write_impl` must pass abort payloads through `self._error(...)` so
   `raise_on_error` behavior is preserved.

5. **Keep backend extension points deliberate.**

   The extracted methods are private implementation helpers by default,
   not a broad subclass API. Backend-specific override points should
   remain the existing narrow hooks unless a new hook is justified:

   - `_apply_index_maintenance(...)`
   - `_stage_chunk_cascade(...)`
   - embedding provider configuration

   If implementation discovers that Postgres or MSSQL needs an override
   for the whole auto-index phase, the spec should be amended with the
   exact reason and the narrower hook that was insufficient.

6. **Preserve transaction and flush semantics.**

   The refactor must keep the existing persist ordering:

   - Stage chunk cascade for changed existing files before inserting new
     chunks.
   - Apply per-entry inserts/updates.
   - Flush row changes.
   - Add or revive parent directories only when the batch produced at
     least one durable non-unchanged write.
   - Flush parent directory changes.

   No phase may introduce an early database mutation before
   auto-index/provider work has succeeded, except for existing metadata
   root behavior already present in the method.

7. **Preserve partial persist behavior.**

   Per-entry failures inside the persist phase currently append
   `"Write failed for ..."` errors and continue processing other
   changed entries. The modularized persist phase must preserve that
   behavior unless a separate story changes the write contract.

8. **Keep result shaping identical.**

   The refactor must preserve:

   - `function="write"`
   - `Candidate.status` values for `created`, `updated`, and
     `unchanged`
   - `success=len(errors) == 0`
   - user-scope unscoping
   - `self._error(...)` handling for both normal and abort results
   - graph invalidation only when edge candidates are present

### Out

- No public API changes.
- No new constructor flags.
- No behavior change to auto-chunk, auto-index, overwrite handling,
  versioning, chunk parent validation, parent directory creation, or
  graph invalidation.
- No Postgres/MSSQL native write-side behavior changes unless needed
  only to preserve existing tests after extraction.
- No broad plugin architecture for write phases.
- No split into separate modules unless the implementation shows the
  file boundary itself is a real maintenance problem.

## Acceptance Criteria

1. `DatabaseFileSystem._write_impl` is a short orchestrator whose body
   reads as the ordered write pipeline.
2. Shared state flows through `_WriteContext` or an equivalent private
   context object, not a large positional argument list.
3. Phase-fatal failures are handled through one `_AbortWrite` catch site
   or an equivalent centralized mechanism.
4. Abort and final results are passed through `self._error(...)`.
5. Existing write tests pass, including:
   - `tests/test_database.py`
   - `tests/test_write_pipeline.py`
   - `tests/test_write_pressure.py`
6. The refactor adds or adjusts targeted tests only when needed to lock
   a previously implicit behavior, such as `raise_on_error` handling on
   phase abort.
7. No new public symbols are exported.
8. `PostgresFileSystem` and `MSSQLFileSystem` continue to inherit the
   shared write pipeline without copy-pasting `_write_impl`.

## Implementation Notes

- Prefer extracting the current commented blocks one at a time and
  running the write-pipeline tests after each meaningful slice.
- Keep helper names specific to write, for example
  `_write_phase_auto_index`, so they do not read as generic filesystem
  APIs.
- Be conservative with comments. The phase names should carry most of
  the structure; comments should explain ordering constraints and
  non-obvious transaction behavior.
- The first implementation should be a mechanical reshape. Any behavior
  improvement discovered during the refactor should become a separate
  story or a clearly labeled follow-up patch.
