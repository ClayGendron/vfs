# Project guidance for Claude Code

## Current state: major refactor in progress

The repo is being rebuilt bit by bit. **Things being broken — failed imports,
unresolved references, tests not collecting — is expected.** Do not treat a
broken import or a non-running suite as a blocker or a regression to fix unless
I ask. Flag it if relevant, then keep moving.

The goal of the refactor is to land solid fundamentals — **paths, models,
base, and database** — built around an MCP design. Evaluate work against where
those fundamentals are heading, not against keeping the whole tree green.

## Tooling

- This is a **uv** project. Run Python and tooling through `uv` — e.g.
  `uv run python ...`, `uv run pytest ...`. Do not invoke the interpreter or
  `pip` directly, and do not manually `source .venv`.

## Git workflow

- Do **not** auto-create a branch before committing. Commit to the current
  branch as-is — including `main` — unless I explicitly ask for a new branch.
- Commit or push only when I ask.

## Imports

- **All imports go at the top of the file. No mid-file or function-local
  imports, ever** — not in functions, methods, `TYPE_CHECKING` aside, or to
  dodge a cycle. If an import is only needed for typing, still place it at the
  top (under a top-level `if TYPE_CHECKING:` block). A real import cycle is a
  structural problem to fix, not to paper over with a deferred import.

## File organization

Lay every module out top-to-bottom in this order:

1. **Module docstring** — what the module is for, with a short example when the
   shape isn't obvious.
2. **`from __future__ import annotations`**, then **imports** — stdlib, then
   third-party, then a trailing `if TYPE_CHECKING:` block (see *Imports* above).
3. **Module constants and shared types** — type aliases (`ObjectKind`), small
   `NamedTuple` types used across the module (`EdgeParts`), and hard-coded
   values (`METADATA_ROOT`, frozensets). A derived or private constant
   (`_EXTENSIONLESS_FILES_LOWER`) sits directly under the public name it comes
   from, not down in the helpers.
4. **Public API, grouped by concern.** Introduce each group with a three-line
   banner comment:

   ```python
   # ---------------------------------------------------------------------------
   # Normalization and validation
   # ---------------------------------------------------------------------------
   ```

   Order groups by the flow a caller follows (gate → normalize/validate →
   construct → decompose → query). A private type bound to a single group
   (`_EdgePathParts`) lives in that group, beside its user.
5. **Internal helpers last** — one trailing `# Internal helpers` banner holding
   the private `_`-prefixed functions, ordered roughly by first use. This keeps
   the public surface up top and the plumbing out of the way.

The split is by visibility and concern, not by kind: public functions live with
the section they serve; only private *functions* are deferred to the end —
private *types and constants* stay next to what they support.

## Code comments

- Keep comments concise (1–2 lines). State the what/why directly.
- Do **not** reference story/spec numbers (e.g. "story 030 §5.2", "Phase 4")
  in code comments. Traceability lives in `context/stories/`, not inline.
