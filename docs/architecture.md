# Architecture Guide

This guide describes the current `vfs` architecture as implemented in `src/vfs`.

## Router-First Design

`VirtualFileSystem` is the core async router. It owns:

- mount registration and longest-prefix path resolution
- path rebasing between mounted filesystems and caller-visible absolute paths
- session injection for SQL-backed filesystems
- fanout and regrouping when a result spans multiple mounts

`VFSClientAsync` is just `VirtualFileSystem(storage=False)`: a pure router with no local storage of its own. `VFSClient` wraps that async router in a dedicated event loop thread for synchronous callers.

## Storage Model

`DatabaseFileSystem` is the portable baseline backend. It stores every persisted entity in one `vfs_objects` table:

- files and directories
- chunk rows
- version rows
- edge rows

The path determines the entity kind. User content uses ordinary paths, while metadata uses the explicit `/.vfs/<endpoint>/__meta__/...` namespace.

That design keeps one identity model across CRUD, search, and graph traversal: if two operations refer to the same path, they are talking about the same object.

## Metadata Namespace

The reserved metadata layout is:

```text
/.vfs/<endpoint>/__meta__/
├── chunks/<name>
├── versions/<number>
└── edges/
    ├── out/<type>/<target>
    └── in/<type>/<source>
```

The explicit namespace is a design choice, not an implementation leak. It makes chunks, versions, and edges inspectable with the same `read`, `ls`, `tree`, `glob`, and `delete` operations as ordinary files.

## Native Backends

`PostgresFileSystem` and `MSSQLFileSystem` inherit from `DatabaseFileSystem` and keep the same public API. They override only the operations where the database can do materially better:

- `glob`
- `grep`
- `lexical_search`
- `vector_search` / `semantic_search` where native vector support exists

The portable baseline still defines the semantics. Backend-native implementations are pushdown optimizations, not separate products.

## Graph as a Projection

Each `DatabaseFileSystem` owns an internal `RustworkxGraph`. The graph is a projection over persisted paths:

- persisted edge rows define the durable graph structure
- chunk and version paths participate through the same path identity model
- graph algorithms operate on ordinary absolute paths and return `VFSResult`

This keeps graph traversal composable with search and CRUD. A `grep()` result can feed directly into `neighborhood()`, `meeting_subgraph()`, or `pagerank()` without conversion.

## Query Engine

The query engine lives in `vfs.query`:

1. `parse_query()` converts a CLI-style string into a `QueryPlan`.
2. `execute_query()` runs each stage against the mounted router.
3. `render_query_result()` or `VFSResult.to_str()` renders the final envelope.

Because every stage returns `VFSResult`, the same envelope flows through grep, search, graph expansion, ranking, and top-k truncation.

## Result Model

`VFSResult` and `Entry` are the common output vocabulary:

- `VFSResult.function` records how the rows were produced
- `VFSResult.entries` is the flat row list
- `Entry` fields such as `path`, `content`, `lines`, `score`, `in_degree`, and `out_degree` are populated as needed

This flattened result model is what makes set algebra and multi-stage query execution practical. Search output, graph output, and filesystem listings all share the same row type.

## Sessions and Transactions

Sessions are owned by the router, not by the backend instance:

- the mounted filesystem receives a session for the duration of one routed operation
- backends call `flush()` when needed but do not own `commit()` / `rollback()`
- the router commits on success and rolls back on error

That separation keeps `DatabaseFileSystem` effectively stateless apart from its configured engine, model, permissions, and optional providers.

## Permissions and User Scoping

`vfs` supports two related access layers:

- path-based permissions through `PermissionMap`
- per-user namespacing through `user_scoped=True`

When user scoping is enabled, caller-visible paths are rewritten through `scope_path()` and restored through `unscope_path()` so the external interface stays stable while storage remains partitioned by user.

## Write Ordering

Mutations follow content-before-commit ordering:

1. stage version metadata
2. write the new content or metadata row
3. `flush()` the session
4. commit at the router boundary

This avoids committed metadata pointing at missing content. The deeper rationale is in [Filesystem Internals](internals/fs.md).
