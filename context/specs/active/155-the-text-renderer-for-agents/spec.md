# 155 — The text renderer for agents: a render budget, empty-result markers, directory markers, collapsed fan-out errors, readable scores

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo;
  revised 2026-10-08 after a review against `0760fe9` (the real verb
  parameters, `rank` as a render-only column, where the slash lives,
  the grouping key, the empty `tree`, no CLI or MCP surface yet)
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** feature (`results/render.py` and `results/projection.py`;
  the envelope's wire format and the storage are untouched;
  `Observation` gains no field)
- **Depends on:** the render seam as built (`render_result(result, *,
  projection=None)`, one per-arrangement renderer each; `to_str` on
  `Result`), `vfs.storage.ranking.min_max` and `rerank._scaled_rows`
  for the glean scale, `ALWAYS_ON_FIELDS = {path, kind, version}`
  (`reads.py` L84) so every row carries its kind. Lands after 154, whose
  message rewrite the error examples below assume.
- **Research it stands on:**
  `../../../research/2026-10-08-smartowl-workspace-integration-issues.md`
  items 9–13; Anthropic's tool-design guidance on paging and
  truncation notes (cited there).

## Intent

`Result.to_str()` is the only thing an agent reads. Today it can
return 100,000 characters from one `read`, renders an empty directory
and a no-hit search as the empty string, shows a directory and a file
the same way in `ls`, repeats one error once per mount, and prints the
lowest glean hit as `0.0000`. Each is a rendering choice, not a
storage fact, so each fix lives in the renderer and changes no
envelope, no row, no statement.

One line: the text surface is bounded, never silent, and never
misleading about kind or rank.

## Decided semantics

1. **A render budget.** `to_str(budget=...)` and
   `render_result(..., budget=...)` take a character budget; the
   default is `None`, unbounded, so nothing changes for callers that do
   not ask. When the rendering exceeds the budget it is cut at a line
   boundary and ends with one note that says how much was cut and, for
   verbs that have one, the parameter that narrows:
   - `read`: `…N more lines` with no parameter hint. `read` takes only
     a path today (`params.py` L113–118); a paged read is its own spec.
   - `grep`: `…N more matches; scope with paths, add ext or globs, or
     set max_count`.
   - `glean`: `…N more hits; scope with paths, add ext or globs, or
     lower limit` (`glean` has `limit`, not `max_count`).
   - `glob`: `…N more entries; scope with paths or set max_count`.
   - `ls`: `…N more entries; list a subdirectory`.
   - `tree`: `…N more entries; lower max_depth`.
   The budget trims a fully rendered body: the content already lives
   on the observation, so the transient cost is at most twice it. A
   renderer that stops at the budget is the future direction, not a
   declared limit. There is no CLI and no MCP server in `src/vfs`
   today, so no surface sets a default; a future host boundary picks
   its own budget.
2. **Empty is a word.** An empty `ls` or `tree` renders `(empty
   directory)`; an empty `glob`, `grep` or `glean` renders `(no
   matches)`. `tree` never returns the root as an observation
   (`descendant_filter` is strict), and the envelope does not carry the
   request, so the root cannot be printed alone. An agent can now tell
   "nothing there" from "the tool said nothing".
3. **Directories carry a trailing `/`** in the rendered path of `ls`,
   `glob` and `tree` when the observation's `kind` is `directory`. The
   structured `path` is unchanged; only the rendered text gains the
   slash. It is added in `_render_rows` (the path-only branch at
   `render.py` L225 and the table cell) and in `_render_tree`'s node
   names, read from `o.kind`; `_format_field(name, value)` never sees
   the row and is not the place.
4. **Identical fan-out errors collapse in text only.** The renderer
   groups errors by `(kind, severity, retryable, path, message)` and
   prints one line per group with the sources listed: `ERROR mounts
   /, /course, /mine: <message> — <hint> (retry: never)`. An entry
   carrying `data` never collapses. The envelope keeps every fact;
   value identity and the wire format are unchanged. This layers on
   the existing wire rollup (`_rolled_errors`, applied only by
   `to_payload(max_errors=…)`, keyed on kind, severity and retryable):
   a rolled entry's message differs, so it never merges, and its
   `[+N more rolled up]` suffix stays.
5. **Glean scores read as rank.** `rank` is a render-only column:
   `validate_projection` admits the name, `resolve_projection` keeps
   it, backends ignore it (`effective_columns` already intersects with
   the entry fields), and `_render_glean` synthesizes `#1`, `#2`, …
   from list position. The default glean projection becomes
   `("path", "rank", "matches")`; the min-max-scaled score prints only
   when the caller projects `score`
   (`projection=("path", "score", "matches")`). The lowest hit no
   longer prints as `0.0000` in the default view.
   `[NEEDS CLARIFICATION: rank only by default, or rank plus the raw
   BM25/cosine score before scaling? Rank is enough for an agent; raw
   scores help a developer tuning rerankers. Leaning rank by default,
   raw under an explicit `score` projection.]`

## Scope

- `render_result(result, *, projection=None, budget=None)` and
  `to_str(*, projection=None, budget=None)`; a `_truncate(text,
  budget, note)` helper at the line boundary; the per-verb note text as
  a small table beside `_DEFAULT_PROJECTION`.
- Empty markers in `_render_path_list`, `_render_grep`,
  `_render_glean`, `_render_tree`. `tests/results/test_render.py`
  L365 pins empty glean → `""` and flips.
- The directory slash in `_render_rows` and `_render_tree`.
- Error collapse in `_render_errors`, keyed as rule 4 says.
- The `rank` render column in `projection.py`; the glean header
  change; the stale `--output` comment at `projection.py` L45 goes.
- Tests: one per rule under `tests/results/`, counting lines and
  characters, never time.
- Out of scope: the envelope, the wire format, a storage-side limit, a
  paged `read`, any CLI or MCP plumbing.

## Acceptance criteria

- `to_str(budget=2000)` on a 5,000-line read returns at most 2,000
  characters plus one note line, cut at a line boundary.
- `ls` of an empty directory renders `(empty directory)`; a no-hit grep
  renders `(no matches)`; an empty `tree` renders `(empty directory)`.
- `ls` renders `/mine/empty/` and `/mine/notes.md`.
- An unscoped unindexable grep over a root and two mounts renders one
  error line naming three sources.
- Two glean hits render `#1` and `#2`, with no `0.0000` in the default
  view; `projection=("path", "score")` still prints the scaled score.
- `scripts/ci.sh 3.13` green.
