# Python style

The style is whatever `ruff` says, plus a small set of project conventions the linter cannot hold. The coding patterns themselves (gates, `Result`, budgets, seams) live in [how-we-code.md](how-we-code.md); this page is about the surface of the code. Every claim here is checked against `pyproject.toml` and [CLAUDE.md](../../CLAUDE.md), and where they disagree with this page, they win.

## Formatter

`ruff format` is the authority. Line length is **120**, and code blocks inside docstrings are reformatted to **80**. Do not argue with the formatter; if the output is ugly, restructure the code.

## Linter rule families (from `pyproject.toml`)

`F`, `E`, `W`, `I`, `N`, `UP`, `ANN`, `B`, `A`, `C4`, `DTZ`, `T20`, `SIM`, `TCH`, `RUF`, `PTH`, `PERF`.

Ignored project-wide: `ANN401`, because an explicit `Any` is allowed where it is the right answer.

Per-file ignores:

- `__init__.py`: `F401` (re-exports are intentional).
- `tests/**/*.py`: `ANN`, `S101`, `TC001` (test annotations and `assert` are fine).
- `src2/**/*.py` and `tests2/**/*.py`: `ALL` (archived; never edit, lint or port-fix them).
- `context/**/*.py`: `ALL` (throwaway spike and benchmark code under research studies).

## Type annotations

- Public APIs are fully annotated, and private helpers usually are too. `ty` checks `src/` and `tests/` and must stay at zero.
- Every module begins with `from __future__ import annotations` directly after its docstring, as the layout rule in [CLAUDE.md](../../CLAUDE.md) ("File organization") puts it; the package `__init__.py` files that only re-export names are the one place it is absent.
- Typing-only imports go in a top-level `if TYPE_CHECKING:` block, never inside a function.
- Prefer `pathlib.Path` over `str` for host filesystem paths in internal code (`PTH` holds this for new I/O calls). A vfs namespace path is the branded `vfs.paths.Path`, a `str` subclass, which is a different thing.
- Datetimes are timezone-aware (`DTZ` holds this): `datetime.now(tz=...)`, never `datetime.utcnow()`.

## Naming

- `snake_case` for functions, methods and variables.
- `PascalCase` for classes.
- `SCREAMING_SNAKE` for module-level constants.
- A leading underscore marks a name internal to its module; the public surface sits above the "Internal helpers" banner and the private functions below it.
- `known-first-party = ["vfs"]`, so `ruff` sorts `vfs` imports as the local package.

## Imports

- All imports at the top of the file, stdlib, then third-party, then first-party, then the `TYPE_CHECKING` block (`I` holds the order). No mid-file or function-local imports, ever; see [CLAUDE.md](../../CLAUDE.md), "Imports".
- Absolute imports only (`from vfs.paths import Path`); no module under `src/vfs/` uses a relative import.
- No wildcard imports.

## Comments and docstrings

- Default to no comments. Add one only when the *why* is not obvious: a hidden constraint, an invariant, a workaround.
- A comment or comment block is two lines at most; if it needs more room, it belongs in a docstring. See [CLAUDE.md](../../CLAUDE.md), "Code comments".
- Code names no document: no spec, story or decision number, and no `context/` path, in a comment or docstring. The document cites the code, not the other way round.
- A public function or method gets a one-line docstring, followed by a section on arguments, returns and failure modes only when the signature is not enough.

## Async

- `VirtualFileSystem` is the async router (`src/vfs/base.py:357`); every verb on it is `async def`, and there is no sync facade.
- Backend protocol methods are `async def`; a builder beneath them is a plain `async` function that takes the op's live session.
- Never call `asyncio.run` inside library code. The caller owns the loop.

## Errors

- Every op returns a `Result`; a failure is a classified row, never an exception. Exceptions are allowed at two places only, a constructor refusing a bad argument and `raise_if_failed` at the caller's boundary. The rule and the files that show it are in [how-we-code.md](how-we-code.md), "Boundaries: gate, parse, classify".
- Do not add `try` / `except` around things that cannot fail. Boundaries (caller input, drivers, disk) yes; internal calls no.
