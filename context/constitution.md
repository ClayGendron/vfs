# Constitution

- **Status:** draft (v0.1) — seeded 2026-04-18 from existing project conventions
- **Purpose:** Immutable principles that constrain every spec, plan, and commit. Read before every non-trivial task.

> **Naming note.** The product is **VFS** (`pip install vfs-py`, module `vfs`). The codebase still uses the legacy name `grover` in many places (class `Grover`, `GroverFileSystem`, table `grover_objects`, package directory `src/grover/`); the rename to `vfs` is in progress. Treat "VFS" and "Grover" as the same project for the duration of the migration.

## Articles

### 1. Everything is a file

Every entity in VFS is addressable by a path and stored in the single `grover_objects` table with a `kind` discriminator (file, directory, chunk, version, connection, …). No URIs, no parallel namespaces, no special-case entities.

This is the load-bearing abstraction. New features must extend the path namespace, not introduce a sibling one.

### 2. Content before commit

In every write path (`_write_impl`, `_edit_impl`, `_replace_impl`, future equivalents), content is written to storage **before** the DB transaction commits. Never the reverse.

Phantom metadata (DB says the file exists, content is missing) is worse than an orphan file (inert, recoverable). This was reversed once in commit `f7e039a` and reverted.

### 3. Sessions are owned by VFS, not by backends

Backends call `session.flush()` only. Create / commit / close belongs to the VFS layer that initiated the operation. Backends that violate this invariant break transactional guarantees across mounts.

### 4. Permissions resolve in filesystem-relative coordinates

Permission rules live and are checked against the path *as the terminal filesystem sees it* — never against the router-side virtual path. All five mutation chokepoints in `base.py` (`_route_single`, `_route_write_batch`, `_route_two_path`, `_dispatch_candidates`, `mkconn`) call `check_writable` on the resolved terminal FS.

### 5. One result type, composable

All public methods return `GroverResult` (with `Candidate` + `Detail`). Set algebra (`&`, `|`, `-`), enrichment (`.sort`, `.top`, `.filter`, `.kinds`), and JSON serialisation are uniform across CRUD, search, graph, and ranking. New surfaces must return `GroverResult`; new result shapes must be expressed as `Detail` types, not new return types.

### 6. CLI parity

Every public Python method has a CLI equivalent reachable through `g.cli('…')`. New methods land with CLI grammar in the same change. The CLI is the contract LLM agents are trained to use; partial coverage breaks the agent-first promise.

### 7. Library, not ops tool

VFS does not write data-migration or backfill scripts for its own schema changes. New columns ship with: model field, validator-driven derivation for new writes, index, and tests. Bringing pre-existing corpora forward is the consumer's responsibility.

### 8. Tests are the gate

Lint, format, type check, and tests must all pass before any commit lands on `main`. Failing tests are never deferred. `uv run pytest` is invoked with no flags and no piping — the full output must be visible. `uvx ruff format` runs before every push.

### 9. No backwards-compatibility shims

VFS is alpha. Schema changes, API renames, and removals land cleanly. No deprecation aliases, no legacy fallbacks, no `# kept for compat` comments. Consumers pin a version.

### 10. Documentation is the source of truth

When code and a context document disagree, the default is to fix the code. The context tree describes what we are building; the codebase is its build artifact. The exception (context is wrong) requires updating the document first, then the code.

## Amendment

Articles change with a dated entry below and a one-paragraph rationale. The constitution evolves; it just evolves deliberately.

### Changelog

- **2026-04-18** — Initial draft seeded from `OLD_CLAUDE.md`, memory feedback entries, and v2 architecture notes.
