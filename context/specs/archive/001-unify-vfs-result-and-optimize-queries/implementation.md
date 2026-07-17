# 001 - Implementation Notes

This document maps the current implementation for story 001 to [spec.md](./spec.md). It also reflects the follow-up decisions recorded in [tasks.md](./tasks.md), including:

- `sort` no longer accepts `--by`; it is now just ascending/descending over the current `Entry.score`
- `grep --output ...` falls back to a Markdown table when the projection asks for entry-level metadata
- explicitly projected fields that are null for every entry append a `NOTE: ... not populated for any entries.`

## High-level result

The story landed in three layers:

1. a single `Entry` / `VFSResult` result model shared across VFS methods
2. projection-aware column narrowing through the VFS facade and SQL backends
3. CLI/query support for `--output`, hydration through `read`, and unified rendering via `to_str(...)`

The current implementation matches the intent in [spec.md](./spec.md) and the phase breakdown in [tasks.md](./tasks.md).

## 1. Unified result envelope

Spec coverage:

- [spec.md](./spec.md) "In" item 1
- [spec.md](./spec.md) "Acceptance criteria / Schema + envelope"
- [spec.md](./spec.md) "Acceptance criteria / Chaining"

Key code:

- [`src/vfs/results.py#L87-L106`](../../../src/vfs/results.py#L87-L106) defines the single row shape, `Entry`
- [`src/vfs/results.py#L250-L390`](../../../src/vfs/results.py#L250-L390) defines the unified `VFSResult` envelope and set algebra
- [`src/vfs/models.py#L216-L237`](../../../src/vfs/models.py#L216-L237) projects `VFSObjectBase` rows into immutable `Entry` values

The old `Candidate` / `Detail` chain was removed. Every public VFS method now returns a `VFSResult` with a `function` label and a flat `entries: list[Entry]`.

```python
class Entry(BaseModel):
    path: str
    kind: str | None = None
    lines: list[LineMatch] | None = None
    content: str | None = None
    size_bytes: int | None = None
    score: float | None = None
    in_degree: int | None = None
    out_degree: int | None = None
    updated_at: datetime | None = None
```

Important behavior that shipped with the new envelope:

- `VFSResult.__or__` preserves the function for same-function unions and returns `"hybrid"` for cross-function merges in [`src/vfs/results.py#L344-L379`](../../../src/vfs/results.py#L344-L379)
- overlapping paths use left-wins field merge in [`src/vfs/results.py#L328-L342`](../../../src/vfs/results.py#L328-L342)
- uniform local transforms such as `.sort()`, `.top()`, `.filter()`, and `.kinds()` live on the result object itself in [`src/vfs/results.py#L418-L447`](../../../src/vfs/results.py#L418-L447)

Tests that lock this in:

- [`tests/test_results.py#L18-L75`](../../../tests/test_results.py#L18-L75)
- [`tests/test_results.py#L100-L153`](../../../tests/test_results.py#L100-L153)
- [`tests/test_results.py#L165-L252`](../../../tests/test_results.py#L165-L252)

## 2. Persisted graph degree fields on the row

Spec coverage:

- [spec.md](./spec.md) "In" item 2

Key code:

- [`src/vfs/models.py#L126-L129`](../../../src/vfs/models.py#L126-L129) adds persisted `in_degree` and `out_degree` fields to `VFSObjectBase`
- [`src/vfs/models.py#L228-L237`](../../../src/vfs/models.py#L228-L237) includes those fields in `to_entry(...)`
- [`src/vfs/graph/rustworkx.py#L323-L346`](../../../src/vfs/graph/rustworkx.py#L323-L346) overrides the persisted values when pagerank/centrality results are produced from fresh graph computations

This matches the spec's split:

- normal object reads (`glob`, `stat`, `read`, `grep`, ranked search row fetches) can carry persisted degree values directly off the object row
- graph algorithms still get to emit their freshly computed values when they are the source of truth

The implementation intentionally does not add a backfill script. Existing rows can remain `NULL` until an external graph rebuild populates them, which is the behavior the spec called for.

## 3. Column narrowing and projection-to-column translation

Spec coverage:

- [spec.md](./spec.md) "In" items 3 and 4
- [spec.md](./spec.md) "Acceptance criteria / Query narrowing"

Key code:

- [`src/vfs/columns.py#L15-L25`](../../../src/vfs/columns.py#L15-L25) maps public `Entry` fields to model columns
- [`src/vfs/columns.py#L37-L77`](../../../src/vfs/columns.py#L37-L77) declares per-function default column sets
- [`src/vfs/columns.py#L98-L122`](../../../src/vfs/columns.py#L98-L122) computes the actual model-column set required for a function and projection
- [`src/vfs/base.py#L1147-L1376`](../../../src/vfs/base.py#L1147-L1376) exposes `columns=` on the public VFS surface for `read`, `stat`, `ls`, `tree`, `glob`, and `grep`
- [`src/vfs/base.py#L955-L995`](../../../src/vfs/base.py#L955-L995) forwards routed operations through mounts without losing the narrowed column request

The translation point is explicit:

```python
def required_model_columns(function: str, projection: tuple[str, ...] | list[str] | None = None) -> frozenset[str]:
    cols: set[str] = set(default_columns(function))
    if projection is None:
        return frozenset(cols)
    for name in projection:
        if name == "default":
            continue
        if name == "all":
            cols |= ENTRY_BACKED_MODEL_COLUMNS
            continue
        cols |= ENTRY_FIELD_TO_MODEL_COLUMNS[name]
    return frozenset(cols)
```

That let the query layer stay in `Entry` vocabulary (`path`, `updated_at`, `out_degree`) while the backends operate in model-column vocabulary.

### Database backend

The shared SQL backend does the narrowing through three helpers:

- [`src/vfs/backends/database.py#L240-L266`](../../../src/vfs/backends/database.py#L240-L266) validates and resolves a requested column set
- [`src/vfs/backends/database.py#L267-L276`](../../../src/vfs/backends/database.py#L267-L276) builds a stable `SELECT` list
- [`src/vfs/backends/database.py#L278-L302`](../../../src/vfs/backends/database.py#L278-L302) builds `Entry` values from a narrowed row

Representative read/search paths:

- [`src/vfs/backends/database.py#L845-L950`](../../../src/vfs/backends/database.py#L845-L950) for `read` and `stat`
- [`src/vfs/backends/database.py#L1151-L1237`](../../../src/vfs/backends/database.py#L1151-L1237) for `ls`
- [`src/vfs/backends/database.py#L1766-L1814`](../../../src/vfs/backends/database.py#L1766-L1814) for `glob`
- [`src/vfs/backends/database.py#L1816-L1957`](../../../src/vfs/backends/database.py#L1816-L1957) for `grep`

The important behavior is that default paths no longer use `select(self._model)` "just in case". They select only the fields needed for the function's default projection unless the caller widens them.

### MSSQL backend

The MSSQL-specific grep/glob paths honor the same contract:

- [`src/vfs/backends/mssql.py#L485-L599`](../../../src/vfs/backends/mssql.py#L485-L599) widens grep rows only as far as the projection requires
- [`src/vfs/backends/mssql.py#L647-L742`](../../../src/vfs/backends/mssql.py#L647-L742) does the same for glob

This is the "no new backend work, but both SQL backends narrow correctly" part of the spec.

Tests that lock this in:

- [`tests/test_columns.py#L17-L122`](../../../tests/test_columns.py#L17-L122)
- [`tests/test_backend_projection.py#L1-L257`](../../../tests/test_backend_projection.py#L1-L257)

## 4. CLI `--output`, stage widening, and hydration through `read`

Spec coverage:

- [spec.md](./spec.md) "In" items 5 and 6
- [spec.md](./spec.md) "Acceptance criteria / CLI projection"

Key code:

- [`src/vfs/query/parser.py#L225-L292`](../../../src/vfs/query/parser.py#L225-L292) parses the top-level `--output` flag and validates it before any backend work
- [`src/vfs/query/executor.py#L112-L123`](../../../src/vfs/query/executor.py#L112-L123) computes the per-stage column set
- [`src/vfs/query/executor.py#L125-L153`](../../../src/vfs/query/executor.py#L125-L153) threads `columns=` into `read` and `stat`
- similar stage threading continues through the rest of [`src/vfs/query/executor.py`](../../../src/vfs/query/executor.py)
- [`src/vfs/query/executor.py#L611-L671`](../../../src/vfs/query/executor.py#L611-L671) hydrates missing projected fields by making exactly one `filesystem.read(...)` call
- [`src/vfs/query/render.py#L1-L20`](../../../src/vfs/query/render.py#L1-L20) makes rendering a thin wrapper over `result.to_str(projection=plan.projection)`

The parser boundary is intentionally early:

```python
def parse_query(query: str) -> QueryPlan:
    tokens, projection = _extract_output_flag(tokenize(query))
    ast = _Parser(tokens).parse()
    return QueryPlan(ast=ast, methods=_planned_methods(ast), projection=projection)
```

The hydration path follows the spec exactly. It does not build SQL directly and it does not hydrate one row at a time:

```python
seed = VFSResult(
    function="read",
    entries=[Entry(path=e.path) for e in result.entries],
)
hydrated = await filesystem.read(
    candidates=seed,
    columns=missing_cols,
    user_id=user_id,
)
```

Why this matters:

- projection widening happens before execution, so the primary query can fetch what it needs
- if a piped result does not have a requested field, the query layer performs one focused backfill through the public `read` API
- `to_str(...)` remains pure and never performs I/O on its own

Tests that lock this in:

- [`tests/test_cli_projection.py#L1-L83`](../../../tests/test_cli_projection.py#L1-L83)
- [`tests/test_cli_hydration.py#L48-L104`](../../../tests/test_cli_hydration.py#L48-L104)
- [`tests/test_cli_hydration.py#L111-L153`](../../../tests/test_cli_hydration.py#L111-L153)
- [`tests/test_cli_hydration.py#L161-L183`](../../../tests/test_cli_hydration.py#L161-L183)
- [`tests/test_query_cli.py#L109-L147`](../../../tests/test_query_cli.py#L109-L147)

## 5. Unified rendering via `to_str(...)`

Spec coverage:

- [spec.md](./spec.md) "After this story" item 2
- [spec.md](./spec.md) "In" item 7
- [spec.md](./spec.md) "Acceptance criteria / CLI projection"

Key code:

- [`src/vfs/results.py#L152-L172`](../../../src/vfs/results.py#L152-L172) declares per-function default projections
- [`src/vfs/results.py#L184-L242`](../../../src/vfs/results.py#L184-L242) validates and resolves projection sentinels
- [`src/vfs/results.py#L457-L475`](../../../src/vfs/results.py#L457-L475) makes `to_str(...)` the single render entry point
- [`src/vfs/results.py#L490-L508`](../../../src/vfs/results.py#L490-L508) appends the null-for-all projection note
- [`src/vfs/results.py#L542-L592`](../../../src/vfs/results.py#L542-L592) renders generic Markdown tables

### Grep rendering

The grep renderer now has two deliberate modes:

- pure line-level projections (`path`, `lines`, `content`) render in ripgrep-style line output
- any entry-level metadata in the projection switches the output to a Markdown table, because those values are per-file rather than per-line

That logic lives in [`src/vfs/results.py#L633-L698`](../../../src/vfs/results.py#L633-L698).

The overlapping-context regression from review was fixed by grouping matches that share the same merged context span before emitting the lines:

```python
grouped_segments: dict[tuple[int, int], set[int]] = {}
for seg in segments:
    grouped_segments.setdefault((seg.start, seg.end), set()).add(seg.match)

for (start, end), match_lines in grouped_segments.items():
    for lineno in range(start, end + 1):
        ...
```

That prevents the same context window from being printed once per match when two hits overlap.

### Tree rendering

The ASCII tree renderer itself still lives in [`src/vfs/results.py#L701-L720`](../../../src/vfs/results.py#L701-L720), but story 001 also needed the executor to preserve `function="tree"` even when `tree --all` or `tree --include ...` falls back to recursive `ls(...)` collection:

- [`src/vfs/query/executor.py#L424-L455`](../../../src/vfs/query/executor.py#L424-L455) routes visibility-expanded tree calls through `_collect_tree(..., result_function="tree")`
- [`src/vfs/query/executor.py#L705-L736`](../../../src/vfs/query/executor.py#L705-L736) performs the recursive collection while preserving the tree envelope

Without that, the renderer would treat the result like `ls` output and lose the tree arrangement.

Tests that lock this in:

- [`tests/test_query_cli.py#L97-L107`](../../../tests/test_query_cli.py#L97-L107)
- [`tests/test_query_executor.py#L257-L280`](../../../tests/test_query_executor.py#L257-L280)
- [`tests/test_cli_hydration.py#L161-L183`](../../../tests/test_cli_hydration.py#L161-L183)

## 6. Sort cleanup after review

Spec follow-up:

- the story originally carried older sort vocabulary; the implementation now matches the corrected direction that `sort` does not have a `--by`

Key code:

- [`src/vfs/query/ast.py#L201-L203`](../../../src/vfs/query/ast.py#L201-L203) reduces `SortCommand` to `reverse: bool`
- [`src/vfs/query/parser.py#L478-L481`](../../../src/vfs/query/parser.py#L478-L481) rejects positional sort arguments and only parses ascending/descending

That lines up with the revised examples in the story and the acceptance wording around `result.sort().top(10)`.

Tests that lock this in:

- [`tests/test_query_executor.py#L594-L599`](../../../tests/test_query_executor.py#L594-L599)
- [`tests/test_query_cli.py#L77-L80`](../../../tests/test_query_cli.py#L77-L80)

## 7. Verification and acceptance coverage

The implementation is covered by both targeted and full-story tests:

- result model and renderer behavior in [`tests/test_results.py`](../../../tests/test_results.py)
- column map and projection math in [`tests/test_columns.py`](../../../tests/test_columns.py)
- per-impl SQL narrowing in [`tests/test_backend_projection.py`](../../../tests/test_backend_projection.py)
- query projection widening in [`tests/test_cli_projection.py`](../../../tests/test_cli_projection.py)
- hydration semantics in [`tests/test_cli_hydration.py`](../../../tests/test_cli_hydration.py)
- end-to-end CLI behavior in [`tests/test_query_cli.py`](../../../tests/test_query_cli.py)
- executor edge cases in [`tests/test_query_executor.py`](../../../tests/test_query_executor.py)

Latest recorded checks for this story work:

- `uv run pytest -q` -> `2219 passed, 40 skipped`
- `uv run pytest tests/test_query_executor.py tests/test_query_cli.py tests/test_results.py tests/test_cli_hydration.py -q` -> `182 passed`
- `uvx ruff format --check src/vfs/query/executor.py src/vfs/results.py tests/test_query_executor.py tests/test_query_cli.py tests/test_results.py tests/test_cli_hydration.py` -> clean

## Summary

The implementation for 001 is centered on a single flat result shape, projection-aware SQL narrowing, and a query/render pipeline that uses one shared vocabulary from parser to backend to renderer. The most important concrete changes are:

- `Entry` and `VFSResult` replacing the old chained result model
- `columns=` threading through the VFS facade and both SQL backends
- `--output` widening the primary query when possible and hydrating through `read` when necessary
- `to_str(...)` becoming the single rendering surface for CLI output
