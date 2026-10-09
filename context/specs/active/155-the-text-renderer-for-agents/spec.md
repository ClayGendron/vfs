# 155 — The text renderer for agents: a render budget, empty-result markers, directory markers, collapsed fan-out errors, readable scores

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** feature (`results/render.py` and `results/projection.py`
  only; the envelope and storage are untouched)
- **Depends on:** the render seam as built (`render_result`, one
  per-arrangement renderer each), `vfs.storage.ranking.min_max` and
  `rerank.py` for the glean scale.
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

1. **A render budget.** `to_str(budget=...)` takes a character budget;
   the default is unbounded, so nothing changes for callers that do
   not ask. When the rendering exceeds the budget it is cut at a line
   boundary and ends with one note that says how much was cut and how
   to narrow: for `read`, "…N more lines; read with `offset`/`limit`";
   for `grep`/`glean`, "…N more matches; scope with `paths`, add
   `ext`, or raise `max_count`"; for `ls`/`tree`/`glob`, "…N more
   entries; narrow the pattern or scope". This is a render option, not
   a storage limit, and the no-scale-caps rule is untouched.
   `[NEEDS CLARIFICATION: should the MCP tool surface set a default
   budget (say 32,000 chars) so every host gets paging without opting
   in, while the Python API stays unbounded? Leaning yes.]`
2. **Empty is a word.** An empty `ls` renders `(empty directory)`; an
   empty `glob`, `grep` or `glean` renders `(no matches)`; an empty
   `tree` renders the root alone. An agent can now tell "nothing
   there" from "the tool said nothing".
3. **Directories carry a trailing `/`** in the path projection of `ls`,
   `glob` and `tree` when the observation's `kind` is a directory. The
   structured `path` is unchanged; only the rendered line gains the
   slash.
4. **Identical fan-out errors collapse in text only.** When two or more
   errors differ only in `source`, the renderer prints the line once
   and lists the sources: `ERROR mounts /, /course, /mine: grep
   pattern 'ab' yields no indexable literal …`. The envelope keeps
   every fact; value identity is unchanged.
5. **Glean scores read as rank.** The header prints `#1`, `#2`, … and
   the min-max-scaled score only when the caller projects `score`
   explicitly. The default glean projection becomes
   `("path", "rank", "matches")`. The lowest hit no longer prints as
   `0.0000` in the default view.
   `[NEEDS CLARIFICATION: rank only, or rank plus the raw BM25/cosine
   score before scaling? Rank only is enough for an agent; raw scores
   help a developer tuning rerankers. Leaning rank by default, raw
   under `--output score`.]`

## Scope

- `render_result(result, *, projection=None, budget=None)`; a
  `_truncate(text, budget, note)` helper at the line boundary; per-op
  note text as a small table beside `_DEFAULT_PROJECTION`.
- Empty markers in `_render_path_list`, `_render_grep`,
  `_render_glean`, `_render_tree`.
- The directory slash in `_format_field("path", …)` when the row's
  kind is known.
- Error collapse in `_render_errors`: group by every frozen field
  except `source`.
- The `rank` projection field and the glean header change.
- Tests: one per rule under `tests/results/`, counting lines and
  characters, never time.
- Out of scope: the envelope, the wire format, a storage-side limit,
  the CLI flag plumbing beyond passing `budget` through.

## Acceptance criteria

- `to_str(budget=2000)` on a 5,000-line read returns at most 2,000
  characters plus one note line, cut at a line boundary.
- `ls` of an empty directory renders `(empty directory)`; a no-hit grep
  renders `(no matches)`.
- `ls` renders `/mine/empty/` and `/mine/notes.md`.
- An unscoped unindexable grep over three mounts renders one error line
  naming four sources.
- Two glean hits render `#1` and `#2`, with no `0.0000` in the default
  view.
- `scripts/ci.sh 3.13` green.
