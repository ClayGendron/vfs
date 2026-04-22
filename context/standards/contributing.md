# Contributing

This is the practical "how to land good changes here" guide. It sits above style and tooling and below story-specific design.

Read this with:

- `standards/python-style.md`
- `standards/testing.md`
- `standards/tooling.md`
- `standards/commits-and-prs.md`

## Default stance

Contributions here should be:

- small enough to review
- large enough to complete one coherent behavior change
- tested at the layer where the behavior actually lives
- aligned with the existing public contract unless the change explicitly updates that contract

Do not treat the repo as greenfield. Match the existing architecture first, then improve it deliberately.

## Start from the real contract

Before changing code:

1. find the authoritative public surface
2. find the baseline implementation
3. find the tests that currently pin behavior
4. find the story, decision, or doc that explains the intended direction

In practice, that usually means reading:

- the relevant backend or module in `src/vfs/`
- the mirrored test file in `tests/`
- the story in `context/stories/`
- any standards doc that constrains the work

If code, tests, and story disagree, do not guess. Resolve the active contract first.

## Reusable best practices learned in this repo

### Preserve the portable baseline

`DatabaseFileSystem` is the portable baseline. Backend-specific acceleration belongs in the backend subclass, not in the shared implementation.

Use this pattern:

- keep the generic behavior correct in the shared layer
- override only the backend-specific hot path
- preserve the same `VFSResult` / `Entry` contract at the boundary

That keeps SQLite, Postgres, and MSSQL from drifting into different products.

### Push backend-native work down without changing the API

When a backend can do something natively, prefer:

- same public method
- same return shape
- different internal execution path

Callers should not need to know whether an operation ran in Python, SQLAlchemy, PostgreSQL, or a search engine.

### Never do request-path provisioning

Schema artifacts, extensions, generated columns, indexes, SQL functions, and similar backend setup should be provisioned explicitly, then verified at runtime.

Preferred pattern:

- `install_*()` for explicit setup in tests / local setup / deploy tooling
- `verify_*()` for request-time safety checks
- normal request handling assumes the artifacts already exist

This repo already follows that pattern for native Postgres search. Reuse it for new backend-native capabilities.

### Tests should match the layer being changed

If you change:

- shared behavior: add or update baseline tests
- backend-native behavior: add backend integration coverage
- public API semantics: update both behavior tests and docs

Do not stop at unit tests if the change depends on real database behavior, query planning, generated columns, SQL functions, or driver quirks.

### Prefer proving equivalence over rewriting behavior

For optimizations and pushdown work, the job is usually:

- keep semantics stable
- move execution to a better layer

That means tests should compare native behavior to the baseline contract, especially around:

- empty inputs
- unknown paths
- multi-seed union behavior
- user scoping
- deterministic ordering
- edge-case namespace encodings

### Follow the real namespace model

Path and metadata conventions in this repo are load-bearing.

Examples:

- metadata lives under `/.vfs/.../__meta__/...`
- edge projections use `__meta__/edges/in` and `__meta__/edges/out`
- user-scoped storage must scope internally and unscope results at the boundary

Do not invent alternate encodings because they seem cleaner. Check `src/vfs/paths.py` and the matching tests first.

### Make result shaping boring

The internal implementation can be complex. The returned result should not be.

Prefer:

- `VFSResult(function=..., entries=[...])`
- stable ordering when the backend can return rows in arbitrary order
- minimal row shaping in Python after native execution

Avoid backend-specific response shapes leaking outward.

### Respect fixture conventions

Fixtures in `tests/conftest.py` are part of the architecture. If a new backend-native feature needs explicit setup, wire it into the fixture layer instead of open-coding setup in every test.

That keeps integration tests consistent and makes failures easier to localize.

### Update docs when the capability meaningfully changes

If the shipped behavior changes in a way contributors or users need to know, update the nearest durable doc in the same change:

- README for user-facing capability claims
- `context/stories/...` for implementation prototypes or story notes
- standards docs for reusable team practice

## Typical workflow for a strong contribution

1. Read the target module and its mirrored tests.
2. Read the relevant story, decision, and standards docs.
3. Identify the contract you must preserve.
4. Implement the smallest architectural change that satisfies the story.
5. Add tests at the real execution layer.
6. Run format, lint, types, and the narrowest meaningful test slice first.
7. Run the broader suite when the change touches shared behavior.
8. Update the nearest docs before closing the change.

## Review checklist

Before calling a change done, ask:

- Does this preserve the public contract?
- Does it follow the existing layering instead of bypassing it?
- Is provisioning explicit and verification separate from request handling?
- Are tests exercising the actual backend or runtime behavior that changed?
- Did I reuse existing path, scoping, and result-shaping conventions?
- Did I update the docs that now make different claims?

If any answer is "no", the change is probably not ready.
