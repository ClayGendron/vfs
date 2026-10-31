# 002 - Implementation Notes

This document maps the current implementation for story 002 to [spec.md](./spec.md).

It also records the follow-up decisions that were resolved during implementation:

- story 002 shipped as a hard cut: the old child-of-file metadata paths and the `mkconn` verb are gone from the live API surface
- `edges/out` is the only writable edge namespace; `edges/in` is a readable inverse projection synthesized from canonical edge rows
- `/.vfs` is fully addressable by `read` / `stat` / `ls` / `tree`, but broad `glob` calls still hide metadata unless the caller explicitly targets `/.vfs`
- permission checks resolve both the canonical metadata path and its logical non-`/.vfs` alias so writable holes apply to projected metadata

## High-level result

Story 002 landed in five layers:

1. a canonical `/.vfs/.../__meta__/...` path contract with new helper/parsing rules
2. a hard-cut public API/query surface centered on `mkedge`
3. database-backed storage, inverse-edge projection, and graph loading in the new namespace
4. move, scoping, and permission logic updated for projected metadata paths
5. active docs, examples, and tests rewritten to the new shape

The current implementation matches the intent of [spec.md](./spec.md). Historical design notes in `docs/plans/` still preserve earlier discussion and should be treated as non-normative.

## 1. Canonical path contract

Spec coverage:

- [spec.md](./spec.md) "In" items 1 through 10, 12, 14, and 15
- [spec.md](./spec.md) "Target namespace"
- [spec.md](./spec.md) "Reserved namespace semantics"
- [spec.md](./spec.md) "Dangling edges"

Key code:

- [`src/vfs/paths.py#L21-L50`](../../../src/vfs/paths.py#L21-L50) defines the canonical metadata vocabulary (`/.vfs`, `__meta__`, `edges/{out,in}`)
- [`src/vfs/paths.py#L216-L320`](../../../src/vfs/paths.py#L216-L320) implements `meta_root(...)`, `base_path(...)`, `parent_path(...)`, and reserved-path validation
- [`src/vfs/paths.py#L328-L455`](../../../src/vfs/paths.py#L328-L455) detects `edge` kinds and constructs canonical chunk/version/edge paths
- [`src/vfs/paths.py#L477-L547`](../../../src/vfs/paths.py#L477-L547) decomposes edge paths and handles user-scope round-tripping
- [`src/vfs/paths.py#L565-L642`](../../../src/vfs/paths.py#L565-L642) treats everything after `.../edges/out/<type>/` or `.../edges/in/<type>/` as an opaque embedded endpoint path

The important path-level behavior that shipped:

- `meta_root("/src/a.py") == "/.vfs/src/a.py"`
- `meta_root("/.vfs/src/a.py/__meta__/chunks/login")` is idempotent
- `/.vfsbar/...` is not treated as metadata space because `/.vfs` matching is exact
- `parent_path(...)` now returns the literal projected parent in the new namespace instead of reconstructing a logical owner
- direct writes into arbitrary `/.vfs/...` space are rejected unless they target a valid managed metadata path
- edge endpoints can themselves be metadata paths, including chunk and version paths under `/.vfs`

Representative construction helpers:

```python
chunk_path("/src/a.py", "login")
# /.vfs/src/a.py/__meta__/chunks/login

version_path("/src/a.py", 3)
# /.vfs/src/a.py/__meta__/versions/3

edge_out_path("/src/a.py", "/src/b.py", "imports")
# /.vfs/src/a.py/__meta__/edges/out/imports/src/b.py
```

The story-specific contract tests live in [`tests/test_story_002_namespace.py#L21-L70`](../../../tests/test_story_002_namespace.py#L21-L70).

## 2. Hard-cut public API and query surface

Spec coverage:

- [spec.md](./spec.md) "In" item 5
- [spec.md](./spec.md) "Migration behavior"

Key code:

- [`src/vfs/base.py#L1285-L1311`](../../../src/vfs/base.py#L1285-L1311) exposes `mkedge(source, target, edge_type)` as the public routed mutation
- [`src/vfs/query/parser.py#L367-L378`](../../../src/vfs/query/parser.py#L367-L378) parses only `mkedge` forms and enforces source/target/type ordering
- [`src/vfs/query/executor.py#L204-L205`](../../../src/vfs/query/executor.py#L204-L205) and [`src/vfs/query/executor.py#L389-L421`](../../../src/vfs/query/executor.py#L389-L421) lower CLI/query execution to `filesystem.mkedge(...)`
- [`src/vfs/query/executor.py#L294-L308`](../../../src/vfs/query/executor.py#L294-L308) allows graph queries and subgraph results to expose `edge` rows as first-class result entries

The hard-cut behavior is explicit:

- `mkconn` is not an alias
- cross-mount edge creation is rejected at the router boundary
- the write-permission check runs against the actual canonical `edges/out/...` write path, not just the source file path

The negative compatibility test is intentional and remains in [`tests/test_story_002_namespace.py#L64-L70`](../../../tests/test_story_002_namespace.py#L64-L70): it proves `mkconn` is rejected.

## 3. Storage, projection, and graph loading

Spec coverage:

- [spec.md](./spec.md) "In" items 8 through 11 and 13
- [spec.md](./spec.md) "Dangling edges"
- [spec.md](./spec.md) "Resolution example"

Key code:

- [`src/vfs/models.py#L125-L161`](../../../src/vfs/models.py#L125-L161) defines the persisted object shape, including `edge` rows and edge columns
- [`src/vfs/models.py#L522-L574`](../../../src/vfs/models.py#L522-L574) validates long projected metadata paths, infers `kind="edge"`, and derives `source_path` / `target_path` / `edge_type` from the canonical edge path
- [`src/vfs/backends/database.py#L859-L877`](../../../src/vfs/backends/database.py#L859-L877) materializes the reserved `/.vfs` root safely under concurrent write load
- [`src/vfs/backends/database.py#L1298-L1305`](../../../src/vfs/backends/database.py#L1298-L1305) ensures the metadata root exists before parent-directory resolution
- [`src/vfs/backends/database.py#L388-L519`](../../../src/vfs/backends/database.py#L388-L519) parses and synthesizes inverse `edges/in` browse trees from canonical edge rows
- [`src/vfs/backends/database.py#L1665-L1722`](../../../src/vfs/backends/database.py#L1665-L1722) implements `_mkedge_impl(...)` and stores only canonical `edges/out` rows
- [`src/vfs/backends/database.py#L2051-L2102`](../../../src/vfs/backends/database.py#L2051-L2102) keeps `glob` metadata-hidden by default unless the caller explicitly targets `/.vfs`
- [`src/vfs/graph/rustworkx.py#L259-L288`](../../../src/vfs/graph/rustworkx.py#L259-L288) loads only `kind == "edge"` rows into the graph projection
- [`src/vfs/graph/rustworkx.py#L303-L320`](../../../src/vfs/graph/rustworkx.py#L303-L320) emits projected edge entries back out of subgraph results using `edge_out_path(...)`

This is the effective persistence model:

- outgoing edges are the canonical stored rows
- incoming edges are a required read surface, but not a second persisted copy
- dangling outgoing edges are allowed immediately
- inverse visibility attaches once the target endpoint becomes addressable

Two implementation details are worth calling out:

- projected metadata paths can exceed the old 4096-character limit, so the model allows up to 8192 for `path` and `parent_path`
- metadata is fully addressable for `stat` / `ls` / `tree`, but broad namespace scans still default to user files and directories unless `/.vfs` is explicitly requested

Story-specific integration tests for these behaviors live in [`tests/test_story_002_namespace.py#L73-L141`](../../../tests/test_story_002_namespace.py#L73-L141).

## 4. Moves, user scoping, and permissions

Spec coverage:

- [spec.md](./spec.md) "In" items 6, 7, 9, 10, and 15
- [spec.md](./spec.md) "Known host-filesystem constraint"

Key code:

- [`src/vfs/backends/database.py#L250-L270`](../../../src/vfs/backends/database.py#L250-L270) rebuilds scoped edge paths from scoped `source_path` and `target_path`
- [`src/vfs/backends/database.py#L1844-L1979`](../../../src/vfs/backends/database.py#L1844-L1979) rewrites file metadata paths, outgoing edge paths, and incoming edge targets during `move(...)`
- [`src/vfs/paths.py#L533-L547`](../../../src/vfs/paths.py#L533-L547) unscopes metadata and edge paths back to logical coordinates
- [`src/vfs/permissions.py#L257-L325`](../../../src/vfs/permissions.py#L257-L325) resolves write checks against both canonical `/.vfs/...` paths and their logical aliases

The shipped behavior here is mostly about making the projected namespace usable as a real namespace rather than as a formatter:

- writable holes like `/synthesis` also allow writes under `/.vfs/synthesis/...`
- explicit rules on `/.vfs/...` still win if the caller wants to freeze or open a specific metadata subtree
- user-scoped storage keeps unscoped logical results while storing canonical scoped edge rows internally
- file moves update chunk/version roots, outgoing edge paths, and foreign rows whose `target_path` points into the moved subtree

The most important regression coverage lives in:

- [`tests/test_directory_permissions.py`](../../../tests/test_directory_permissions.py)
- [`tests/test_user_scoping.py`](../../../tests/test_user_scoping.py)
- [`tests/test_user_scoping_bypass.py`](../../../tests/test_user_scoping_bypass.py)
- [`tests/test_database.py`](../../../tests/test_database.py)

## 5. Docs, examples, and verification

Spec coverage:

- [spec.md](./spec.md) "In" item 14
- [spec.md](./spec.md) "Acceptance criteria"

Active docs and examples were updated to describe the new namespace and verb family:

- [`README.md#L83-L110`](../../../README.md#L83-L110) now presents the `/.vfs/.../__meta__/...` tree as the canonical metadata layout
- [`docs/index.md#L197-L203`](../../../docs/index.md#L197-L203) demonstrates `chunk_path(...)`, `version_path(...)`, and `edge_out_path(...)`
- [`docs/api.md#L307-L323`](../../../docs/api.md#L307-L323) documents `mkedge` plus explicit edge browsing/deletion through metadata paths
- [`docs/architecture.md#L301-L312`](../../../docs/architecture.md#L301-L312) describes persisted edge rows and graph projection in `mkedge` terms
- [`docs/internals/fs.md#L276-L312`](../../../docs/internals/fs.md#L276-L312) describes edge handling in the filesystem protocol and background cleanup path
- [examples/repo_postgres_cli_smoke.ipynb](../../../examples/repo_postgres_cli_smoke.ipynb) was updated to show the canonical metadata tree in the CLI smoke example

Verification run during implementation:

- `uv run pytest tests/test_story_002_namespace.py -q`
- `uv run pytest -q`

Final repo-wide result after the full migration pass:

- `2253 passed, 68 skipped`

## Summary

Story 002 shipped as a true namespace migration rather than as a compatibility layer. The durable boundary is:

- canonical metadata lives under `/.vfs/<endpoint>/__meta__/...`
- `mkedge` is the only public edge-creation verb
- `edges/out` is the writable source of truth
- `edges/in` is the required readable inverse view
- routing, scoping, permissions, graph projection, docs, and tests all speak that same shape

The only intentional references to the removed surface that remain are negative tests proving `mkconn` is gone and parser tests confirming literal filenames like `.connections` are still ordinary user content.
