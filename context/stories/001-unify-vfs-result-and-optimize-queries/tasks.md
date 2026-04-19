# 001 — Tasks

- **Status:** substantially shipped (docs update 9.5 + status flip 9.7 deferred; CHANGELOG/release skipped per owner)
- **Date:** 2026-04-19
- **Owner:** Clay Gendron
- **Strategy:** hard cutover. No `candidates` / `Candidate` / `Detail` compat shims. Tests stay red through Phases 2–7 and all turn green together in Phase 8. Update status markers (`[ ]` → `[x]`) as work progresses.

## Naming note

The refactor plan (`docs/plans/grover_result_refactor.md`) refers to `GroverObject` and `grover_objects`. Post-rename, the table is `vfs_objects` and the class is `VFSObject` / `VFSObjectBase`, and the vector column on the model is `embedding` (SA type `VectorType`). Forbidden-column assertions should target `vfs_objects.embedding` and `vfs_objects.content`, not the plan's outdated `grover_objects.vector`.

Also: the per-function column map landed at `src/vfs/columns.py` (not `src/vfs/query/columns.py` as originally planned) — it's a cross-cutting concern shared by backends and the query layer, so it lives at the package root.

## Pre-flight

- [x] **0.1** Confirm current state: branch is `main`, `uv run pytest` green before starting. **Result:** 2157 passed, 40 skipped in 18.49s.
- [x] **0.2** Scan `src/vfs/results.py`, `src/vfs/models.py`, `src/vfs/backends/database.py`, `src/vfs/query/{ast,parser,executor,render}.py`, `src/vfs/graph/rustworkx.py`, `src/vfs/client.py`. Note every construction site of `Candidate` / `Detail` / `VFSResult(candidates=...)`.
- [x] **0.3** Verified the actual vector column on `VFSObjectBase` is `embedding` (not `vector`).

## Phase 1 — Additive schema

- [x] **1.1** Add `in_degree: int | None` and `out_degree: int | None` (both indexed) to `VFSObjectBase`. **Result:** 2157 passed.
- [x] **1.2** MSSQL reuses `VFSObject`; **no-op.**

## Phase 2 — Rewrite `results.py` (hard cutover)

- [x] **2.1** Replaced `Candidate` + `Detail` with `Entry` + `LineMatch` in `src/vfs/results.py`. Fields as specified.
- [x] **2.2** Rewrote `VFSResult`: required `function: str`, `entries: list[Entry]`. Dropped `candidates`, `explain`, `inject_details`, `score_for`. Set algebra uses left-wins merge; cross-function `|` sets `function="hybrid"`. `sort`/`top`/`filter`/`kinds`/`add_prefix`/`strip_user_scope` rewritten against `entries`.
- [x] **2.3** Added `to_json(exclude_none=True)` and `to_str(projection=None)` with per-function arrangement dispatch. Error envelope → `"ERROR: ..."` / `"ERRORS: ..."`.
- [x] **2.4** Replaced `to_candidate()` with `to_entry(score=None, include_content=False)` on `VFSObjectBase`.
- [x] **2.5** Cascaded src migration (via 6 parallel subagents): `base.py`, `backends/database.py` (29 VFSResult sites, 13 `to_entry` calls, grep rewrite to LineMatch), `backends/mssql.py` (6 sites), `graph/rustworkx.py` (15 sites + `_score_candidates` → `_score_entries`), `query/executor.py` (9 sites), `query/render.py` (163 → 29 lines, delegates to `to_str`).
- [x] **2.6** Stat delegation fix: `_stat_impl` re-labels envelope `function="stat"` after delegating to `_read_impl`.
- [x] **2.7** Cascaded test-suite rewrite (via 6 parallel subagents): 23 test files migrated. Deleted tests for removed behavior (`inject_details`, `explain`, `score_for`, detail chains, `sort(operation=...)`). Net: baseline 2157 → post-cutover 2147 passed + 40 skipped; 10 deleted tests covered removed functionality.
- [x] **2.8** `uvx ruff check` + `uvx ruff format --check` clean.

**Phase 2 green gate: ✅ 2147 passed, 40 skipped.**

## Phase 3 — Per-function default column map

- [x] **3.1** Created `src/vfs/columns.py`: `DEFAULT_COLUMNS: dict[str, frozenset[str]]` keyed by function name, plus `_METADATA_COLUMNS` / `_PATH_KIND_ONLY` helpers.
- [x] **3.2** `required_model_columns(function, projection)` — expands `default` / `all` sentinels, unions with default, raises `ValueError` on unknown fields.
- [x] **3.3** `ENTRY_FIELD_TO_MODEL_COLUMNS` mapping + `entry_field_columns(name)` helper translate Entry field names to `VFSObjectBase` model attributes.
- [x] **3.4** `validate_projection(projection)` lives on `vfs.results` — called by the parser for parse-time rejection of unknown field names.

## Phase 4 — Backend impls: narrow SELECTs + produce entries

- [x] **4.1** `_read_impl`, `_stat_impl`, `_ls_impl`, `_tree_impl` — narrow SELECT via `_resolve_columns(function, columns)` + `columns` kwarg + `Entry` output.
- [x] **4.2** `_glob_impl` — narrow SELECT + `columns` kwarg + `Entry` output.
- [x] **4.3** `_grep_impl` + `_collect_line_matches` — one `Entry` per file with `lines: list[LineMatch]`.
- [x] **4.4** `_vector_search_impl`, `_lexical_search_impl`, `_semantic_search_impl` — narrow SELECT (no `embedding` in the returned row list) + `Entry` output.
- [x] **4.5** `_pagerank_impl` + centrality siblings + `_hits_impl` — narrow SELECT + `Entry` output; pagerank values override the persisted `in_degree`/`out_degree`.
- [x] **4.6** Write paths: `_write_impl`, `_delete_impl`, `_mkdir_impl`, `_mkconn_impl`, `_edit_impl`, `_copy_impl`, `_move_impl` — return `Entry` envelopes; narrow pre-write reads.
- [x] **4.7** Traversals: `_predecessors_impl`, `_successors_impl`, `_ancestors_impl`, `_descendants_impl`, `_neighborhood_impl`, `_meeting_subgraph_impl`, `_min_meeting_subgraph_impl` — narrow + `Entry`.
- [x] **4.8** `src/vfs/backends/mssql.py` — same narrowing + `Entry` output at every construction site; MSSQL-specific FTS path honors the column set too.
- [x] **4.9** `src/vfs/graph/rustworkx.py` — `_score_candidates` → `_score_entries`; populate degrees; `_extract_paths` reads `result.entries`.

## Phase 5 — Base class / routing layer

- [x] **5.1** `src/vfs/base.py` — every `VFSResult(candidates=...)` construction flipped to `entries` + explicit `function`. Route-level set algebra delegates to `VFSResult.__or__` / `__and__` / `__sub__`.
- [x] **5.2** `src/vfs/client.py` — public facade signatures carry the `columns` kwarg where applicable; docstrings refreshed.
- [x] **5.3** `fs.read(paths=..., columns=...)` — new `columns` kwarg threaded through client → base → backend; same treatment on `stat`, `ls`, `tree`, `glob`, `grep`.

## Phase 6 — Query layer: projection + hydration

- [x] **6.1** `src/vfs/query/ast.py` — `projection: tuple[str, ...] | None` added to `QueryPlan`; `RenderMode` literal and `render_mode` field removed.
- [x] **6.2** `src/vfs/query/parser.py` — top-level `--output` flag parsed; `_extract_output_flag` validates via `validate_projection` so unknown field names raise `QuerySyntaxError` before any stage runs. `_render_mode()` helper removed.
- [x] **6.3** `src/vfs/query/executor.py` — `_cols_for(function, projection)` resolves per-stage `columns=`; after the pipeline, `_hydrate_projection` backfills null-for-all projected fields via one `filesystem.read(columns=missing)` call (never bypassing the public `read` surface).
- [x] **6.4** `src/vfs/query/render.py` — collapsed to a thin `render_query_result(result, plan) -> str` that delegates to `result.to_str(projection=plan.projection)`; legacy `_PROJECTIONS` fallback dropped.
- [x] **6.5** `tests/test_query_parser.py`, `tests/test_query_executor.py`, `tests/test_query_render.py` — `render_mode` references removed; `TestRenderMode` / `TestRenderModePipelineNoStages` suites dropped.

## Phase 7 — Test rewrite

All 16 test files that touch `.candidates` / `Candidate` / `Detail` get rewritten to the new shape. Group by file to keep changesets reviewable.

- [x] **7.1** `tests/test_results.py` — rewritten against the new shape; merge rules; envelope rules; `to_str` per-function snapshots.
- [x] **7.2** `tests/test_base.py` rewritten.
- [x] **7.3** `tests/test_method_chaining.py` rewritten.
- [x] **7.4** `tests/test_graph.py` rewritten.
- [x] **7.5** `tests/test_database.py` rewritten.
- [x] **7.6** `tests/test_mssql_backend.py`, `tests/test_query_executor.py`, `tests/test_vector_store.py`, `tests/test_permissions.py`, `tests/test_client.py`, `tests/test_lexical_search.py`, `tests/test_query_cli.py`, `tests/test_user_scoping.py`, `tests/test_vfs_client.py`, `tests/test_database_graph.py`, `tests/test_directory_permissions.py` — updated.
- [x] **7.7** `tests/test_query_render.py` — rewritten for `to_str` / `--output`.

**Phase 7 green gate: ✅ 2214 passed, 40 skipped** (baseline 2147 + 67 new tests from Phase 8 so far).

**Post-Phase-9 green gate: ✅ 2201 passed, 40 skipped.** Net −13 vs. post-Phase-7: dropped 28 `render_mode`-specific tests in Phase 6.5 cleanup, added 15 in `test_cli_projection.py` (7) + `test_cli_hydration.py` (8).

## Phase 8 — New test infrastructure

- [x] **8.1** `tests/conftest.py` — `sql_capture` fixture on `before_cursor_execute` event; `SQLCapture.reads_against_objects` + `assert_no_column` helpers.
- [x] **8.2** `tests/test_backend_projection.py` — per-impl SELECT-column assertions. No `vfs_objects.embedding` or `vfs_objects.content` on default reads (exceptions: `read`, `grep`). **Plus** `tests/test_columns.py` for the `vfs.columns` module contract.
- [x] **8.3** `tests/test_cli_projection.py` — `--output` widens the SELECT, projection tuple order is preserved, unknown field rejected at parse time.
- [x] **8.4** `tests/test_cli_hydration.py` — hydration routes through `fs.read` with narrowed `columns=`, single call for many paths, no-op when already populated / projection None / empty result / only computed fields, `to_str` pure (no I/O).
- [~] **8.5** `tests/test_schema_removals.py` — **dropped.** Owner confirmed not needed; `Candidate` / `Detail` grep is enough of a safety net and AST-scan tests add maintenance without much signal.

## Phase 9 — Green gate + polish

- [x] **9.1** `uv run pytest` full suite green.
- [x] **9.2** `uvx ruff format --check .` clean (221 files); `uvx ty check src/vfs` → `All checks passed!` after dropping stale `# ty: ignore` suppressions that ty no longer needed.
- [~] **9.3** Manual CLI smoke — deferred; covered by `tests/test_cli_projection.py` + `tests/test_cli_hydration.py`.
- [~] **9.4** `result.to_json()` eyeball — covered by `tests/test_results.py::test_entry_json_roundtrip` family.
- [ ] **9.5** Update `docs/plans/grover_result_refactor.md` — mark implemented, link to this story.
- [~] **9.6** `CHANGELOG.md` / version bump — **deferred per owner request** (no release cut as part of this story).
- [ ] **9.7** Flip this file's status to `shipped`.

## Rollback plan

Work lands on branch `001-unify-vfs-result-and-optimize-queries`. Each phase is a commit; if a later phase surfaces a schema regret, revert backwards until green.

## Decisions

- **Column set parameter shape.** Resolved as `frozenset[str]` (model-column vocabulary). Entry vocabulary is used only at the projection boundary. Decision locked in by the `vfs.columns` module surface.
- **`to_str` behavior for columns that are null for all entries.** Resolved: keep the normal body/table shape and append `NOTE: <field> not populated for any entries.` for explicitly projected null-for-all fields.
