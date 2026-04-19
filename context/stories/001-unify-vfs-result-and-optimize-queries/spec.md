# 001 — Unify VFSResult and optimize DB queries

- **Status:** draft
- **Date:** 2026-04-19
- **Owner:** Clay Gendron
- **Kind:** feature + migration (unifies `VFSResult`, rewires backend reads, extends CLI)

## Intent

Make `VFSResult` a uniform, chainable response shape across every public method, let the CLI print the response directly at the end of a pipeline using a caller-controlled projection, and stop every backend read from pulling the full `grover_objects` row (vectors included) when only a handful of columns are needed.

Today:

- The result envelope (`VFSResult`) carries `Candidate` + `Detail` chains whose shape varies by operation, so passing a result from one method into the next requires re-reading fields that drifted between backends.
- Every `_*_impl` in `src/vfs/backends/database.py` (and `mssql.py`) issues `select(self._model)`, materializing every column — including large vector blobs and chunk text — even when the caller only prints `path` + `score`. This is the dominant cost on repeat CLI invocations.
- The CLI renders via `query/render.py` which dispatches on a per-stage `RenderMode`. Columns the user asks for via future `--output` flags aren't queryable because the default impl never fetched them.

After this story:

- One row shape (`Entry`) and one envelope (`VFSResult`) across grep, glob, bm25, vector, pagerank, read/stat/ls, write/delete. Results compose: `result_a | result_b`, `.sort`, `.top`, `.filter` all work the same regardless of which method produced them.
- `result.to_str(projection=...)` is the one render entry point. The CLI's `--output` flag feeds `projection` directly. No more `RenderMode`.
- Each backend `_*_impl` SELECTs only the columns needed to populate that function's default projection. Vectors and chunk text are never loaded unless asked for.
- When `--output` requests a column the default impl did not fetch, the CLI issues one focused hydration query before rendering. The user sees the extra column; the default path stays narrow.

## Why

- **Chaining:** A uniform `Entry` shape removes the "which backend produced this row?" question from every downstream `.filter` / `|` / `.top` call. This is Article 5 (One result type, composable) made real.
- **Performance:** `grover_objects` rows carry `vector` blobs and full chunk content. A `glob "**/*.md"` that only needs `path` should not scan those columns. First-order fix: `select(path, kind, size_bytes, updated_at, in_degree, out_degree)` instead of `select(self._model)`.
- **Extensibility:** Once projection controls what's fetched (not just what's rendered), adding new columns (content hash, mount, author) is additive — old CLI invocations keep their fast path; new invocations opt in by naming the column.

## Scope

### In

1. Adopt the `Entry` + envelope refactor specified in [`docs/plans/grover_result_refactor.md`](../../../docs/plans/grover_result_refactor.md). That plan is the schema contract for this story.
2. **Persist graph degree on the object row.** Add `in_degree: int | None` and `out_degree: int | None` columns to `VFSObjectBase` (`src/vfs/models.py`) and index them if query patterns warrant. `to_entry()` reads them off the row directly, so every Entry — glob, grep, stat, read — can carry them without a graph round-trip. `pagerank`/centrality still override with freshly-computed values when producing their own results. Per Article 7 and the `no-migration-scripts` rule: no backfill script; existing rows hold `NULL` until the caller's graph-rebuild process populates them.
3. Introduce a `columns: frozenset[str]` (or equivalent) parameter threaded through every `_*_impl` in `src/vfs/backends/database.py` and `src/vfs/backends/mssql.py`. The parameter names which Entry fields the caller will read; the impl translates that into a narrowed `select(...)`.
4. Define a per-function **default column set** — the minimum columns needed to populate the default projection from the refactor plan's arrangement table. Impls default to this set when no override is passed.
5. CLI enrichment: the query executor / CLI pipeline computes `required_columns = default_columns(function) ∪ projection_columns(plan.projection)` and passes it to the impl before execution. If the result is produced upstream (e.g. piped from another stage) and is missing requested columns, the CLI hydrates the entries via `read` (see next bullet) before calling `to_str`.
6. **Hydration always goes through `read`.** When entries arrive missing a projected column, the CLI calls `vfs.read(paths=[...], columns={...})` — the same narrowed-SELECT path used by every other impl — and merges the returned entries back onto the pipeline result by `path`. No private backend shortcut; no second `select(self._model)`. This keeps one read path, one column-narrowing implementation, and one place to fix a bug if a column is missing from the SELECT. Extending `read` to accept a `columns=` parameter (and to honor it like every other impl in scope) is part of this story. **Where it runs:** hydration happens in the CLI / query-executor layer immediately before rendering, not inside `to_str`. `to_str` stays pure (no I/O, no fs reference) — it renders what's on the envelope.
7. Update `to_str(projection=...)` so that when the caller explicitly projects an Entry field that is `None` for all entries, the rendered output appends a clear note (for example, `NOTE: out_degree not populated for any entries.`) rather than relying on a silently blank column alone.

### Out

- No migration script for `in_degree` / `out_degree` backfill (Article 7, and the `no-migration-scripts` rule).
- No new backends. MSSQL and SQLite/Postgres paths both get the narrowed-select treatment; no new dialect work.
- No MCP layer changes — serialization stays Pydantic.
- Chunk line-range plumbing through the vector store / BM25 is still deferred (same non-goal as the refactor plan).

## Acceptance criteria

A reviewer can verify this story shipped by running the checks below. Each must pass.

### Schema + envelope

- [ ] `result.to_json()` and `result.to_str()` work for every public method in `src/vfs/client.py` and produce output matching the per-function table in the refactor plan.
- [ ] `result_a | result_b` (same function) preserves `function` on the envelope; cross-function merges produce `function="hybrid"`.
- [ ] `Candidate`, `Detail`, `candidates`, `explain`, `inject_details`, `score_for`, `sort(operation=...)` are all removed.

### Chaining

- [ ] A CLI pipeline `vfs glob "**/*.md" | vfs grep "hydrate"` (or the Python equivalent) passes `entries[].path` from stage 1 into stage 2 without either stage needing to know the other's shape.
- [ ] `result.sort().top(10)` works identically on output from `grep`, `vector_search`, and `pagerank`.

### Query narrowing

- [ ] No `_*_impl` in `src/vfs/backends/database.py` calls `select(self._model)` on a read path when a smaller column set suffices. Verified by code review + a unit test that inspects the compiled SQL of each impl for the absence of `grover_objects.vector`, `grover_objects.content`, etc. when those fields are not in the requested column set.
- [ ] `vfs glob "**/*.md"` on a corpus with ≥1 MB vector blobs per row runs measurably faster than `main` on the same corpus (rough target: 3× on a cold cache; capture a timing in the PR body, don't block on an exact number).
- [ ] Every public method's default-path SELECT lists columns explicitly. No "fetch everything just in case."

### CLI projection

- [ ] `vfs grep "hydrate" --output default,updated_at` includes `updated_at` in the impl's SELECT and renders a per-entry Markdown table, since projecting entry-level fields opts out of rg-style line output.
- [ ] `vfs vector_search "auth" --output path,score,out_degree` renders `out_degree` without issuing a second `SELECT *`; the narrowed SELECT already covers it.
- [ ] `vfs stat /docs/foo.md --output all` works and pulls exactly the columns needed to display every populated field.
- [ ] `vfs grep "hydrate" --output bogus` raises `ValueError: unknown field 'bogus'` at parse time, before any query runs.
- [ ] Piping a stage's output into a projection that needs columns it didn't fetch triggers **one** hydration call through `vfs.read(paths=[...], columns={...})` (not N, not a direct `select(self._model)` bypass), keyed on `path`, before rendering.
- [ ] `vfs.read` accepts and honors a `columns=` parameter, narrowing its SELECT to exactly the requested Entry fields.
- [ ] A unit test asserts the hydration path in the CLI calls `read` with the computed column set and does not construct its own SQL.

### Tests + lint gate

- [ ] `uv run pytest` fully green.
- [ ] `uvx ruff format --check .` and `uvx ty` clean.
- [ ] `tests/test_results.py` has `to_str` snapshot tests per function (default projection + a handful of override projections).
- [ ] A new `tests/test_backend_projection.py` (or equivalent) asserts the SELECT column lists for each `_*_impl` match the declared default column set.

## Test strategy

The acceptance criteria are the *what*. This section is the *how* — a test spec per aspect: what the test asserts, what it catches if it fails, and what instrument it uses. Implementation belongs in `plan.md` / `tasks.md`, not here.

### What we must get right (risk table)

| Risk | What goes wrong if we miss it | Test that catches it |
|---|---|---|
| Vectors or full content leak into default reads | `glob`/`ls`/`stat`/`pagerank` stay slow; story shipped in name only | Per-impl SELECT-column assertions |
| `--output` doesn't widen the SELECT | User adds `--output out_degree`, gets nulls, silently | CLI-projection → SELECT assertion |
| Hydration bypasses `read` | Two places to fix a column bug; divergence creeps in | Monkeypatched `read` spy; assert single call with `columns=` |
| Stale `Candidate`/`Detail` references linger | Import errors; downstream consumer breakage | Source-tree text scan |
| `to_str` drifts from documented arrangement | CLI output changes; agents trained on old shape break | Snapshot tests per function |
| Cross-function `|` doesn't produce `function="hybrid"` | Merged envelopes carry a misleading function name | Set-algebra unit test |
| Hydration fires N times instead of once | CLI latency spikes on large piped results | `read`-call counter test |
| Unknown projection field discovered late | Query runs, user waits, then typo error | Parser unit test |
| `to_str` silently renders an all-`None` column | Caller thinks data is missing from source, not the query | Null-column render test |

### Primary instrument: SQL capture fixture

Most narrowing and CLI-projection tests depend on the same building block: a pytest fixture that listens on the SQLAlchemy engine's `before_cursor_execute` event and records every SQL statement issued during a test. A helper on top of the fixture filters to SELECTs against `grover_objects`. Lives in `tests/conftest.py`. Every narrowing-flavored test reuses it rather than re-implementing capture.

### 1. Schema unification

- **`test_every_public_method_returns_entry_envelope`** — Parametrized over every public method on the FS. Each call must return a `VFSResult` whose `function` is set and whose `entries` are `Entry` instances. Catches regressions where one method returns the old shape or forgets to set `function`.
- **`test_no_lingering_candidate_detail_references`** — Scans `src/vfs/` for forbidden identifiers (`Candidate`, `Detail`, `.candidates`, `.inject_details`, `.score_for`, `.explain(`). Zero tolerance. Catches drift from Article 9 (no compat shims).
- **`test_entry_json_roundtrip`** — `Entry.model_validate_json(entry.model_dump_json()) == entry` for each function's typical entry. Catches field/type drift in the schema.

### 2. Chaining and set algebra

- **`test_union_same_function_preserves_function`** — `(grep | grep).function == "grep"`.
- **`test_cross_function_merge_is_hybrid`** — `(grep | vector).function == "hybrid"`.
- **`test_overlap_left_entry_wins`** — Merging two results that share a path keeps the left entry's fields. No detail-chain merge to do.
- **`test_sort_top_uniform_across_functions`** — Parametrized over `grep`, `vector`, `pagerank`. `.sort().top(n)` returns the same shape and ordering regardless of producing function.
- **Pipeline smoke (manual, in PR checklist):** `vfs glob "**/*.md" | vfs grep "hydrate"`; `vfs vector_search "auth" | vfs stat`. Confirms path-based chaining works across real method boundaries.

### 3. Query narrowing per impl (the big one)

The heart of the performance promise. Each impl gets its own test that runs the method with its default projection and inspects the captured SQL.

One test per impl, each asserting:

- `grover_objects.vector` **not** in the statement.
- `grover_objects.content` **not** in the statement — except `read` and `grep`, which legitimately need content.
- The SELECT contains exactly the columns declared in the per-function default column map (no missing, no extras).

Covered impls: `glob`, `ls`, `stat`, `read`, `grep`, `vector_search`, `lexical_search`, `pagerank`, `write`, `delete`.

A separate **parametrized "declared-vs-actual" test** iterates over the `default_columns(function)` map and asserts the impl's observed SELECT matches it set-equal. Catches drift between the declared default (which flows into `--output default`) and what the impl actually fetches. Without this, the two can silently diverge.

### 4. CLI projection parsing

- **`test_unknown_projection_field_rejected_at_parse_time`** — `--output bogus` raises `ValueError` with `"unknown field 'bogus'"` before any query executes.
- **`test_default_sentinel_expands_to_function_default`** — `--output default,updated_at` on a `grep` plan produces the grep default column set plus `updated_at`.
- **`test_all_sentinel_is_preserved_for_render_time_resolution`** — `--output all` stays symbolic on the plan; resolution to concrete columns happens when we know the populated fields.
- **`test_projection_tuple_ordering_is_preserved`** — Order matters for `to_str` arrangement. `--output path,score,out_degree` differs from `--output out_degree,score,path`.

### 5. CLI projection → narrowed SELECT

Proves the `--output` flag reaches the impl's column-narrowing code, not just the renderer.

- **`test_output_widens_select`** — Parametrized: `--output default,updated_at` on several functions. Captured SQL must include `grover_objects.updated_at`. Forbidden columns still absent.
- **`test_output_does_not_trigger_secondary_query`** — `--output path,score,out_degree` on `vector_search` produces at most the baseline statement count for that function; no extra hydration round-trip fires when the column could have been included in the primary SELECT.

### 6. Hydration via `read`

Proves the hydration contract: when entries arrive missing a projected column, the executor calls `fs.read(paths=[...], columns={...})` exactly once, with the right columns.

- **`test_hydration_routes_through_read_with_columns`** — Monkeypatches `fs.read` with a spy. Feeds an upstream result missing `out_degree`. Renders with projection requiring it. Asserts exactly one spy call whose `columns=` argument contains `out_degree`.
- **`test_hydration_single_batch_for_many_paths`** — Same setup, 500 upstream entries. Asserts exactly one `read` call (not 500). Catches per-entry-loop regressions.
- **`test_hydration_does_not_emit_select_star`** — During hydration, captured SQL must not contain `grover_objects.vector` or `grover_objects.content` unless they were actually requested. Hydration inherits `read`'s narrowing discipline.
- **`test_hydration_is_noop_when_columns_already_present`** — Upstream already has the requested columns populated. Spy asserts `read` is **not** called. Avoids the "always hydrate" footgun.
- **`test_to_str_does_not_call_read`** — Monkeypatch guard: `to_str` is pure. If `to_str` ever tries to hydrate on its own, this test fires.

### 7. `to_str` per-function arrangement

Snapshot tests (one file per function under `tests/snapshots/to_str/`) covering:

- Default projection per function: `grep`, `glob`, `ls`, `tree`, `stat`, `vector_search`, `lexical_search`, `pagerank`, `read` (single-entry), `read` (multi-entry), `write`, `delete`.
- Override variants: `grep --output default,updated_at`, `stat --output all`, `pagerank --output path,score`.
- Error envelope: `success=False, errors=["boom"]` → `ERROR: boom`, ignoring projection.
- Grep multi-match file with `-C 2`: merged context windows render correctly, one output line per `LineMatch`.

Snapshots are cheap regression detection for the LLM-facing rendering surface.

### 8. Null-column projection handling

- **`test_to_str_with_column_null_for_all_entries_notes_it`** — Render a projection that explicitly includes a column where every entry has `None`. The output keeps the table/body shape but also appends a clear note naming the unpopulated field(s), catching silent blank-column regressions.

### 9. Performance (informational, not a CI gate)

Not pass/fail — flaky on shared runners. Reviewer captures a before/after timing in the PR body:

- Same corpus, ≥1000 rows, realistic (≥1 KB) vectors.
- `time vfs glob "**/*.md" >/dev/null` on `main` vs. this branch, cold cache.
- Record the ratio; target ≥3×, don't block on exact number.

### Running the tests

Per `grover-tooling-rules`: `uv run pytest` with no flags, no piping. The narrowing and hydration suites are targetable by path for local iteration, but the final gate is the full suite plus `uvx ruff format --check .` and `uvx ty`.

## Dependencies and references

- **Foundation plan:** [`docs/plans/grover_result_refactor.md`](../../../docs/plans/grover_result_refactor.md). Treat its schema and migration order as the starting point; this story extends it with the query-narrowing and CLI-enrichment work.
- **Constitution articles:** 5 (One result type, composable), 6 (CLI parity), 7 (Library, not ops tool), 8 (Tests are the gate), 9 (No backwards-compatibility shims).
- **Related context docs:** `docs/plans/search_api_design.md`, `docs/plans/search_ops_plan.md`, `docs/plans/lazy_query_builder.md` — historical prior art on narrowing reads; cross-check any conclusions that still apply.

## Decisions and open questions

- **Column set parameter shape.** Resolved in implementation as `frozenset[str]` in model-column vocabulary, with translation from Entry-field vocabulary at the projection boundary.
- **Hydration batch size.** `read(paths=[...])` already handles batching today; the CLI hydration path inherits whatever chunking `read` uses. If MSSQL parameter limits bite, the fix lands in `read`, not in the CLI. [parked]
- **`to_str` behavior for columns that are null for all entries.** Resolved in implementation as: keep the normal body/table shape and append a one-line `NOTE: ... not populated for any entries.` block for explicitly projected fields.
