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

## Code comments

- Keep comments concise (1–2 lines). State the what/why directly.
- Do **not** reference story/spec numbers (e.g. "story 030 §5.2", "Phase 4")
  in code comments. Traceability lives in `context/stories/`, not inline.
