# Python style

The style is whatever `ruff` says, plus a small set of project-specific conventions that aren't enforceable by the linter.

## Formatter

`ruff format` is the authority. Line length is **120**, docstring code blocks are reformatted to **80**. Don't argue with the formatter; if the output is ugly, restructure the code.

## Linter rule families (from `pyproject.toml`)

`F`, `E`, `W`, `I`, `N`, `UP`, `ANN`, `B`, `A`, `C4`, `DTZ`, `T20`, `SIM`, `TCH`, `RUF`, `PTH`, `PERF`.

Ignored project-wide:

- `ANN401` — explicit `Any` is allowed where it's the right answer.
- `UP046` — PEP 695 type params are incompatible with SQLModel / ABC metaclasses.

Per-file ignores:

- `__init__.py` — `F401` (re-exports are intentional).
- `tests/**` — `ANN, S101, TC001` (test annotations and `assert` are fine).
- `src_old/**`, `tests_old/**` — `ALL` (archived; do not edit).

## Type annotations

- Public APIs are fully annotated. Private helpers usually are too.
- Use `from __future__ import annotations` only where it actually helps (forward refs, heavy stub imports). Don't sprinkle it as cargo cult.
- Prefer `pathlib.Path` over `str` for filesystem paths in internal code (`PTH` enforces this for new I/O calls).
- Datetimes are timezone-aware (`DTZ` enforces). `datetime.now(tz=…)`, never `datetime.utcnow()`.

## Naming

- `snake_case` for functions, methods, variables.
- `PascalCase` for classes.
- `SCREAMING_SNAKE` for module-level constants.
- Internal-by-convention: leading underscore. Backend implementation hooks follow the `_{op}_impl` pattern (`_write_impl`, `_edit_impl`, `_route_single`, …) — that pattern is load-bearing; preserve it when adding new ops.
- `known-first-party = ["grover"]` — ruff treats `grover` as the local package for import sorting. (Will become `vfs` post-rename.)

## Imports

- Standard lib → third-party → first-party, separated by blank lines (ruff `I` enforces).
- Avoid wildcard imports.
- Avoid relative imports beyond one level (`.foo`, not `..foo.bar`).

## Comments and docstrings

- Default to no comments. Add one only when the *why* is non-obvious — a hidden constraint, an invariant, a workaround.
- Don't restate what the code does. `# increment counter` above `counter += 1` is noise.
- Don't reference tickets, PRs, or callers in code comments — that context belongs in the commit message and the PR description.
- Public methods get a one-line docstring, optionally followed by a section explaining args / returns / raises only when the signature isn't enough.

## Async

- Async is the primary path. The sync facade (`Grover` / future `VFS`) is a thin wrapper around the async core (`GroverAsync` / future `VFSAsync`).
- New backend methods are written async-first; the sync wrapper picks them up automatically.
- Don't mix `asyncio.run` inside library code. The caller owns the loop.

## Errors

- Use the exception hierarchy in `exceptions.py` — don't raise bare `RuntimeError` / `ValueError` from public surfaces.
- Failures that are part of the result contract (missing search provider, permission denied on a single candidate within a batch) become `success=False` on `Detail` / `GroverResult`, not exceptions.
- Don't add `try / except` blocks around things that "shouldn't fail." Boundaries (user input, external APIs, disk) yes; internal calls no.
