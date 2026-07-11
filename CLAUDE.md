# Project guidance for Claude Code

## Current state: greenfield rebuild, green tree

The repo is being rebuilt around solid fundamentals — **paths, models, base,
results, and storage** — built around an MCP design. The live tree is fully
green: the `tests/` suite passes, and `ruff` and `ty` are at zero across
`src/` and `tests/`. **Keep it that way** — a broken import, a failing test,
or a new lint/type error in the live tree is a regression to fix, not
expected refactor noise.

A green tree is an invariant, not a constraint on ambition. **This is still
greenfield work: do not discount ideas because they would require a big
refactor, churn a lot of files, or take significant resources.** There is no
legacy to protect and no users to migrate — evaluate ideas on where the
fundamentals should end up, propose the right design, and treat the cost of
getting there as a planning detail, not a reason to shrink the idea. Green
means each landing leaves the tree working; it does not mean changes must be
small.

### Live code vs archived reference: `src/`+`tests/` vs `src2/`+`tests2/`

- **`src/` and `tests/` are live.** New and updated code and tests go here;
  `tests/` is the only suite worth running.
- **`src2/` and `tests2/` are archived pre-refactor code, kept as a quarry**
  to mine while building out the live tree. Do **not** run, lint, fix, or
  port-fix them — they reference names that no longer exist by design, and
  tooling config already excludes them. When a file has been fully ported or
  superseded, it can go.

## Tooling

- This is a **uv** project. Run Python and tooling through `uv` — e.g.
  `uv run python ...`, `uv run pytest ...`. Do not invoke the interpreter or
  `pip` directly, and do not manually `source .venv`.
- **`ruff` and `ty` must stay at zero across `src/` and `tests/`.** They
  currently pass clean; leave them that way after every change. `src2/` and
  `tests2/` are excluded in `pyproject.toml` — never chase errors there.

## Git workflow

- Do **not** auto-create a branch before committing. Commit to the current
  branch as-is — including `main` — unless I explicitly ask for a new branch.
- Commit or push only when I ask.

## Project memory

- **All project knowledge lives in this repo — never outside it.** Do not
  write memory files to `~/.claude/projects/*/memory/` or any other
  out-of-repo location; if any exist, delete them. Durable context belongs
  in `context/` (stories, decisions, learnings) or this file, where it is
  versioned and visible to everyone.

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

- Inline comments and comment blocks are **2 lines maximum** — this includes
  multi-line `#` blocks above a statement. State the what/why directly; if it
  needs more room, it belongs in a docstring.
- Do **not** reference story/spec numbers (e.g. "story 030 §5.2", "Phase 4")
  in code comments **or docstrings**. Traceability lives in
  `context/stories/`, not inline.
