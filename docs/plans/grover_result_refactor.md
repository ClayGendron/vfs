# Unify result schema: `Candidate` → `Entry`, collapse `Detail` chain

## Context

Grover currently has two layered concepts on every result row:

- `Candidate` (src/grover/results.py:84): path + assorted metadata + a `details: tuple[Detail, ...]` provenance chain that accumulates one `Detail` per pipeline step, with `score` derived from the last detail.
- `GroverResult` (src/grover/results.py:147): a thin envelope — `success`, `errors`, `candidates`.

This design mixes per-row provenance with cross-function orchestration. It makes chaining powerful but the row shape hard to reason about: the score you see depends on operation history, scoring fields (`weight`, `distance`, `details[-1].score`) vary by backend, and field names (`size_bytes`, `updated_at`, `candidates`) don't match the filesystem-native vocabulary used elsewhere.

The new model, agreed during design:

- Each response is **homogeneous per function** (one grep, or one bm25, or one pagerank).
- The `function` and its metadata (query, model, edge_type, matched_terms, seed) live on the **envelope**.
- The row — now called **`Entry`** — is a flat set of directly-addressable fields.
- Chaining is **external**: callers feed `entries[].path` from one response into the next call.

This cleans up the API surface, unifies grep/glob/bm25/vector/pagerank under one row shape, and makes the result self-documenting.

## The new schema

### `Entry` (row) — 9 fields + `LineMatch` NamedTuple

```python
from typing import NamedTuple

class LineMatch(NamedTuple):
    """One matched line plus its context window. Pure positional data.

    start/end/match are 1-indexed file line numbers. `match` is the hit
    line; start/end bracket the before/after context window (equal to
    `match` when no -B/-A context is requested).
    """
    start: int
    end: int
    match: int

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

| field | type | grep | glob | bm25/vector | pagerank | read/stat/ls |
|---|---|---|---|---|---|---|
| `path` | `str` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `kind` | `str \| None` | `"file"` | `"file"`/`"dir"` | `"file"` | `"file"` | varies |
| `lines` | `list[LineMatch] \| None` | N items, one per match | null | null (v1) | null | null |
| `content` | `str \| None` | **full file text** (so `to_str` can slice) | null | chunk text | null | file content (read only) |
| `size_bytes` | `int \| None` | ✓ | ✓ | bytes of chunk | ✓ | ✓ |
| `score` | `float \| None` | match count | null | relevance | centrality value | null |
| `in_degree` | `int \| None` | ✓ (from GroverObject) | ✓ | ✓ | ✓ | ✓ |
| `out_degree` | `int \| None` | ✓ (from GroverObject) | ✓ | ✓ | ✓ | ✓ |
| `updated_at` | `datetime \| None` | ✓ | ✓ | ✓ | ✓ | ✓ |

**Why `LineMatch` is a NamedTuple, not a BaseModel.** Pure positional data, immutable, unpackable (`start, end, match = seg`), zero validation overhead. Pydantic serializes named tuples cleanly. Keeps the `(start, end, match)` triple cohesive instead of spraying three parallel nullable fields across Entry.

**No `content` on `LineMatch`.** Kept deliberately minimal — positions only. `to_str` for grep slices `entry.content` using segment positions at render time (see arrangement table below).

**One Entry per path, for every method — including grep.** This keeps the IO invariant uniform: grep returns one Entry per file with N `LineMatch` items in `entry.lines`, not one Entry per match.

**Trade-off to accept.** Grep responses ship the whole file's text in `entry.content` so `to_str` can slice. For a 50KB file with 3 matches, that's 50KB on the wire. Acceptable because (a) grep already reads the file to match, (b) JSON consumers often want the whole text anyway. If response size becomes a problem, a future optimization is to have grep populate `content` with only the matched ranges plus a per-segment offset mapping — defer until it bites.

Kept original names: `size_bytes`, `updated_at` (no rename).
Collapsed from proposed shape: `line_start` / `line_end` / `line_match` → `lines: list[LineMatch]`.
Removed from current Candidate: `id`, `lines` (prior meaning, "line count"), `tokens`, `mime_type`, `weight`, `distance`, `created_at`, `details`.
Retained from current Candidate: `kind`.

### `GroverObject` gets `in_degree` and `out_degree` columns

Per user's design, `in_degree` and `out_degree` are **persisted on the `grover_objects` row**, not computed at query-time. That means every Entry can carry them — glob, grep, read, stat, etc. — not just pagerank.

- Add `in_degree: int | None` and `out_degree: int | None` columns to the `GroverObject` model (src/grover/models.py).
- `to_entry()` reads them off the row directly.
- No migration script per the `no-migration-scripts` rule — data lifecycle (populating degrees) is managed externally. Existing rows will have nulls until the user's graph-rebuild process backfills them.
- `_score_entries` in rustworkx.py still overrides with the freshly-computed pagerank-run values when producing pagerank results.

### `GroverResult` (envelope)

```python
class GroverResult(BaseModel):
    success: bool = True
    errors: list[str] = []
    function: str                        # grep | glob | bm25 | vector | semantic | pagerank | read | stat | ls | write | delete | hybrid
    entries: list[Entry] = []            # renamed from candidates
```

Kept minimal. Dropped during review: `total`/`returned` (redundant with `len(entries)` when we're not paginating), `truncated` (no function truncates in v1), `model`/`edge_type`/`seed`/`matched_terms` (function-specific envelope clutter — if a caller needs the embedding model name, they know which call they made). Can be added later if a concrete need appears.

Rule: rows carry what's at the path, envelope carries how the response was produced.

### New methods on `GroverResult`: `to_json()` and `to_str()`

`to_json` is a thin Pydantic wrapper. `to_str` renders the response to text, with a user-controllable **projection** — the ordered list of Entry columns to include. How those columns are arranged is fixed per function (grep arranges them as `path:line_match:content`, stat as a block, read dumps content, etc.) and lives inside `to_str`. Users pick *which* columns appear; the function picks *how* they appear.

The current `RenderMode` enum in `query/ast.py` and the hard-coded branches in `query/render.py` collapse into this single primitive.

#### Vocabulary

Used consistently in code, docstrings, help text, and tests:

- **Projection** — the ordered list of Entry columns to include (`["path", "line_match", "content"]`). Named for the relational-algebra operation; extensible to modifiers (e.g., `content:80`) later without renaming.
- The CLI flag is `--output`; the `to_str` parameter is `projection=`. One word, one meaning, whether you're writing Python or shell.

```python
def to_json(self, *, exclude_none: bool = True) -> str:
    """Pydantic JSON — for APIs, caches, MCP tools."""
    return self.model_dump_json(exclude_none=exclude_none)

def to_str(self, *, projection: list[str] | None = None) -> str:
    """Render to text. projection selects Entry columns; arrangement is function-specific.

    When projection is None, uses the function's default projection.
    """
    ...
```

**Error precedence.** If `not success`, `to_str` returns `"ERROR: " + "; ".join(errors)` regardless of projection. Success-with-errors appends the error block after the body (current `render.py` behavior).

**Projection vocabulary.** Anything on `Entry` (`path`, `kind`, `lines`, `content`, `size_bytes`, `score`, `in_degree`, `out_degree`, `updated_at`) plus two sentinels:
- `all` — every Entry field that is non-null for at least one entry in the response.
- `default` — the function's default projection (lets `--output default,out_degree` mean "append out_degree to the normal view").

Unknown names in a projection raise `ValueError` at render time so typos surface early.

Projecting `lines` on its own just dumps the list. Grep's default arrangement uses `lines` + `content` together (one output line per `LineMatch`, content sliced per segment) — see the grep row in the table below.

**Per-function arrangement + default projection.** `to_str` dispatches on `self.function`:

| function | default projection | arrangement |
|---|---|---|
| `grep` | `["path", "lines", "content"]` | **one output line per `LineMatch` in `entry.lines`**, formatted `path:seg.match:<sliced content>`. The slice is `entry.content.splitlines()[seg.start-1 : seg.end]` joined with `\n`. Expands N Entries' `lines` into N × M physical output lines without changing the IO shape (still one Entry per file). |
| `glob`, `ls` | `["path"]` | one path per line (projection still applies if caller adds columns — `:`-joined) |
| `tree` | `["path"]` | ASCII tree of paths (existing `_render_tree` logic) |
| `bm25`, `lexical`, `vector`, `semantic` | `["path", "score"]` | block: first column is header, rest indented `  key: value` under it; blank line between entries |
| `pagerank`, `*_centrality`, `hits` | `["path", "score", "in_degree", "out_degree"]` | one line per entry, `\t`-joined |
| `read` | `["content"]` | dumps `entry.content` verbatim; multiple entries separated by `==> path <==` |
| `stat` | `["path", "kind", "size_bytes", "updated_at", "in_degree", "out_degree"]` | block format, same as ranked search |
| `write`, `delete`, `edit`, `move`, `copy`, `mkdir`, `mkedge` | `["path"]` | action one-liner (reuse current `_render_action`/`_verb_for`) |
| `hybrid` | `["path"]` | one path per line |

**Grep arrangement, concretely:**
```python
def _render_grep(self) -> str:
    out = []
    for entry in self.entries:
        text_lines = (entry.content or "").splitlines()
        for seg in entry.lines or []:
            block = "\n".join(text_lines[seg.start - 1 : seg.end])
            out.append(f"{entry.path}:{seg.match}:{block}")
    return "\n".join(out)
```

When a projection is supplied, the function's arrangement still applies — it just draws from the user's chosen column list. For example, `grep --output path,lines,out_degree` produces one output line per `LineMatch` with the out_degree column appended.

### CLI / parser integration

The current `RenderMode` field on `QueryPlan` (ast.py:234) and the `_render_*` dispatch in `render.py` become:

1. Delete `RenderMode` from `query/ast.py`.
2. `QueryPlan` carries a single optional override: `projection: tuple[str, ...] | None`. When None, `to_str` applies the function's default projection.
3. `query/render.py` collapses to a single call: `result.to_str(projection=plan.projection)`. The helper functions (`_render_ls`, `_render_tree`, `_render_stat`, `_render_content`, `_render_action`, `_render_query_list`) move into `results.py` as private arrangement helpers dispatched by `self.function`.
4. Add one pipeline-terminal flag to the query parser (`query/parser.py`), applied to the final result regardless of the last stage:
   - `--output <comma-list>` → `plan.projection`. Accepts any Entry field name plus `all` / `default`. Example: `--output path,line_match,content,out_degree`.

   **No short alias.** `-o` stays free for future use (e.g. `--output-file`), and ripgrep already uses `-o` for `--only-matching` inside grep — avoiding shadowing keeps rg muscle memory intact.

5. The parser's existing per-command render-mode mapping becomes unused and is removed. Each stage no longer declares a render mode; `to_str` asks the envelope for its function and dispatches internally.

This preserves backwards-compatible CLI behavior (no flag → same output as today for each command) while making every column user-selectable. For example:
- `grover vector_search "auth" --output path,score,out_degree` — ranked hits with the degree column appended.
- `grover grep "hydrate" --output default,updated_at` — grep output with an extra timestamp column.
- `grover stat /docs/foo.md --output all` — every populated field shown.
- `grover pagerank --output path,score` — ranked list with just path + score.

### Extensibility hooks (not v1, worth naming)

- **Projection modifiers.** `content:80` to truncate content to 80 chars; `path:basename` to show only the leaf. The `field[:modifier]` syntax slots into the projection list without changing the flag. Calling them "projection modifiers" stays consistent with the vocabulary.
- **Render-time filters.** `--where "score>0.5"` to filter entries at render time. Out of scope for this migration (caller can use `top`/`filter` stages today), but the `to_str(projection=)` signature leaves a second parameter slot for it.

## Provenance: drop `Detail` entirely

Per user's answer, we drop the details chain. The current function's outcome is already on the envelope (`function`, `score` on each entry); prior operations' context is not preserved across calls. This removes:

- `Detail` class (src/grover/results.py:63)
- `Candidate.score` property + `Candidate.score_for()` (results.py:118, 126) — `score` becomes a direct Entry field
- `GroverResult.explain(path)` (results.py:187)
- `GroverResult.inject_details(prior)` (results.py:360)
- `sort(operation=...)` parameter (results.py:316) — sort by `score` only

Set algebra (`&`, `|`, `-`) stays (per user's answer). New merge rule on overlapping paths: **left entry wins** (no detail-chain merge to do). Envelope for merged results: left envelope's `function` is preserved; if left.function != right.function, the merged envelope's function becomes `"hybrid"`.

## Per-function construction changes

### `_grep_impl` + `_collect_line_matches` (backends/database.py:1724, 1850)

**One Entry per file** (matching every other method's IO invariant). Each Entry carries:
- `content` = full file text (so `to_str` can slice at render time).
- `lines` = `list[LineMatch]`, one `LineMatch(start, end, match)` per matched line. `match` is the hit line; `start`/`end` bracket the `-B`/`-A` context window, equal to `match` when no context is requested.
- `score` = match count (i.e. `len(entry.lines)`).

This replaces the current `Detail.metadata["line_matches"]` dict structure with a typed `LineMatch` NamedTuple list on Entry. `_collect_line_matches` becomes `_collect_line_segments` (or similar) and returns `list[LineMatch]` for each file's Entry. Overlapping context windows should still be merged (current `_build_line_matches_with_context` logic) so segments never overlap.

### `_glob_impl` (backends/database.py:1652)
Already returns one Entry per path. Add `size`, `updated_date`, `kind` from the row (already available on `GroverObject`). `score`, `line_*`, `in/out_degree`, `content` stay null.

### `_vector_search_impl`, `_lexical_search_impl` (backends/database.py:1943, 1977)
Set `score` directly. `line_*` stays null in v1 (per user's answer). `content` = chunk text when the vector store / BM25 pipeline already carries it. `in_degree`/`out_degree` come from the underlying `GroverObject` row.

### `_centrality_impl` / pagerank (graph/rustworkx.py:334, 803)
`_score_candidates` becomes `_score_entries`. Populate `score` directly. `in_degree`/`out_degree` come from the graph run (overriding the persisted `GroverObject` values, since pagerank is computing over a possibly-filtered subgraph). `line_*` null.

### `read` / `stat` / `ls` / `write` / `delete` (backends/database.py:790, 805, 833, 1016, 1019, 1141, 1170, 1246, 1248, 1253)
Drop-in rename: `to_candidate()` → `to_entry()` on `GroverObjectBase` (models.py:219). Keep `size_bytes`, `updated_at` names. Drop `id`, `lines`, `tokens`, `mime_type`, `created_at`. Read `in_degree`/`out_degree` from the row. Envelope `function` set per operation.

## Files to change

- `src/grover/results.py` — add `LineMatch` NamedTuple, rewrite `Candidate` → `Entry` (9 fields, with `lines: list[LineMatch] | None`), delete `Detail`, update `GroverResult` envelope, simplify `_merge_candidate` to `_merge_entry` (left wins, no detail concat), add `function` envelope field, add `to_json()` and `to_str(projection=)` methods with per-function arrangement dispatch, rewrite `sort` to drop `operation=` branch, remove `explain`/`inject_details`, rename `candidates` → `entries` everywhere.
- `src/grover/models.py` — add `in_degree: int | None` and `out_degree: int | None` columns to the `GroverObject` SQLAlchemy model; `to_candidate()` → `to_entry()` (line ~219), drop dropped fields, read new degree columns.
- `src/grover/backends/database.py` — 10+ construction sites (lines listed above). Biggest behavior change is `_collect_line_matches`: one Entry per matched line with line_start/line_end/line_match.
- `src/grover/backends/mssql.py` — 3 sites (305, 567, 722). Same field mapping as database.py.
- `src/grover/graph/rustworkx.py` — `_score_candidates` → `_score_entries`, populate `in_degree`/`out_degree`, `_extract_paths` reads `result.entries` not `result.candidates`.
- `src/grover/query/executor.py` — `Candidate` → `Entry`, `.candidates` → `.entries`, `_paths_result` builds Entry instead of Candidate.
- `src/grover/query/ast.py` — delete `RenderMode` type alias; add `projection: tuple[str, ...] | None` to `QueryPlan`. Remove the per-stage render-mode assumption.
- `src/grover/query/parser.py` — add `--output` top-level flag that populates `QueryPlan.projection`. Remove per-command render-mode assignment.
- `src/grover/query/render.py` — collapses to a single thin function: `render_query_result(result, plan)` calls `result.to_str(projection=plan.projection)`. Existing `_render_*` helpers move into `results.py` as arrangement helpers dispatched by `self.function`.
- `src/grover/client.py` — public facade; update any docstrings or method signatures that reference `candidates` / `Candidate` / `Detail`.
- `tests/test_results.py` — largest test file; rewrite for new shape. Drop Detail tests. Rewrite merge tests for left-wins rule. Add envelope tests (function, model, edge_type).
- `tests/test_lexical_search.py`, `tests/test_query_executor.py` — update assertions against new field names.
- Any docstrings in `results.py` that reference the old shape (module docstring lines 1–14 in particular).

## Migration order (one branch, reviewable commits)

1. Add `in_degree` / `out_degree` columns to `GroverObject` (models.py). Harmless additive change.
2. Introduce `Entry` next to `Candidate` in `results.py`; add `function`/`query`/`elapsed_ms` envelope fields and `entries` alongside `candidates`.
3. Swap backend construction sites one module at a time (database.py, mssql.py, rustworkx.py), each commit green. Update `to_candidate()` → `to_entry()`.
4. Rework grep: one Entry per file with `content` = full file text and `lines: list[LineMatch]` populated from `_collect_line_segments` (its own commit — the one shape change worth isolating).
5. Implement `to_json` and `to_str(projection=)` on `GroverResult` with the arrangement helpers moved out of `render.py` and dispatched by `self.function`.
6. Rewire CLI: delete `RenderMode`, add `--output` to parser, collapse `render.py` to a single call-through.
7. Remove `Candidate`, `Detail`, `candidates` alias, `explain`, `inject_details`, `score_for`, `sort(operation=...)`.
8. Update tests last; all tests green.

## Verification

- `uv run pytest` — full suite. All of `tests/test_results.py`, `tests/test_lexical_search.py`, `tests/test_query_executor.py` must pass against new shape.
- Smoke the CLI: `grover glob "**/*.md"`, `grover grep "hydrate" /docs`, `grover semantic_search "auth"`, and a pagerank run — verify `result.to_json()` has `function` + `entries` (with `lines: [[start, end, match], ...]` or object-form on grep) and `result.to_str()` renders the per-function default.
- Grep-specific: one Entry per matched file in JSON; `to_str` expands to one output line per `LineMatch`. Multi-match file + `-C 2` renders correctly with merged context windows.
- CLI composition checks:
  - `grover vector_search "auth" --output path,score,out_degree` — out_degree column appears.
  - `grover grep "hydrate" --output default,updated_at` — timestamp appended to grep output.
  - `grover pagerank --output path,score` — ranked list with just path + score.
  - `grover stat /docs/foo.md --output all` — every populated field shown.
  - `grover grep "hydrate" --output bogus` — raises `ValueError: unknown field 'bogus'`.
- `uvx ty` — type-check the new schema and everywhere field names changed.
- Eyeball `result.to_json()` for each function to confirm no leftover `candidates` / `details` keys.
- Add `to_str` snapshot tests per function in `tests/test_results.py` — one per function default, plus a handful exercising `projection=` overrides and the `all` / `default` sentinels. Cheap regression detection for the LLM-facing rendering.

## Explicit non-goals

- Not plumbing chunk line ranges through vector store / BM25 in this migration (deferred per user's answer).
- Not adding `id`, `content_hash`, `mount`, `author`, or `created_date` to Entry — design discussion considered and declined them.
- Not writing a migration script to backfill `in_degree`/`out_degree` on existing `grover_objects` rows — per the `no-migration-scripts` rule, the user's graph-rebuild process handles data lifecycle.
- Not changing MCP tool shape (no MCP layer exists today; serialization stays Pydantic + the new `to_json`/`to_str`).
- Not adding hybrid search as a first-class function — `function="hybrid"` appears only as the merged-envelope marker for `result_a | result_b` across functions.
