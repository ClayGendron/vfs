# API Reference

This page tracks the current public `vfs` surface in `src/vfs`. It intentionally describes the shipped `VFSClient` / `VFSClientAsync` API rather than the older Grover facade.

## Clients

```python
from vfs import VFSClient, VFSClientAsync, VirtualFileSystem
```

| Type | Purpose |
|------|---------|
| `VFSClientAsync` | Async facade for servers, workers, and agent runtimes. Inherits `VirtualFileSystem` and returns `VFSResult(success=False, ...)` on normal failures. |
| `VFSClient` | Sync wrapper around `VFSClientAsync`. Uses a private event loop thread and sets `raise_on_error=True`, so failures raise `VFSError` subclasses. |
| `VirtualFileSystem` | The mount-aware async base class. It owns routing, path rebasing, and session injection. |

## Backends

```python
from vfs.backends import DatabaseFileSystem, MSSQLFileSystem, PostgresFileSystem
```

| Backend | Purpose |
|---------|---------|
| `DatabaseFileSystem` | Portable SQL-backed filesystem using a single `vfs_objects` table. |
| `PostgresFileSystem` | PostgreSQL-native overrides for grep, glob, lexical search, and pgvector-backed vector search. |
| `MSSQLFileSystem` | SQL Server / Azure SQL backend with native full-text and regex pushdown. |

Constructor shape for the baseline backend:

```python
DatabaseFileSystem(
    *,
    engine=None,
    session_factory=None,
    model=VFSObject,
    embedding_provider=None,
    vector_store=None,
    user_scoped=False,
    permissions="read_write",
    schema=None,
)
```

`engine` and `session_factory` are mutually interchangeable entry points for SQLAlchemy async sessions. `user_scoped=True` enables per-user path namespacing when `user_id` is supplied on operations.

## Mounting

```python
from sqlalchemy.ext.asyncio import create_async_engine

from vfs import VFSClient
from vfs.backends import DatabaseFileSystem

engine = create_async_engine("sqlite+aiosqlite:///workspace.db")

g = VFSClient()
g.add_mount("workspace", DatabaseFileSystem(engine=engine))
```

Mount paths are single segments such as `"workspace"` or `"/workspace"`. The router rebases returned paths automatically, so the mounted filesystem only sees `"/"`-relative paths internally.

## Core Methods

All client methods return `VFSResult` on success. The async and sync facades expose the same method names.

### CRUD and Navigation

| Method | Notes |
|--------|-------|
| `read(path=None, candidates=None, *, user_id=None)` | Read file content. |
| `write(path=None, content=None, objects=None, overwrite=True, *, user_id=None)` | Write one path or batch-write model objects. |
| `edit(path=None, old=None, new=None, edits=None, candidates=None, replace_all=False, *, user_id=None)` | Single or multi-edit replacement. |
| `delete(path=None, candidates=None, permanent=False, cascade=True, *, user_id=None)` | Soft or permanent delete. |
| `stat(path=None, candidates=None, *, user_id=None)` | Metadata lookup for one path. |
| `mkdir(path, *, user_id=None)` | Create a directory path. |
| `mkedge(source, target, edge_type, *, user_id=None)` | Create a canonical outgoing edge row. |
| `move(src=None, dest=None, moves=None, overwrite=True, *, user_id=None)` | Move one path or a batch of pairs. |
| `copy(src=None, dest=None, copies=None, overwrite=True, *, user_id=None)` | Copy one path or a batch of pairs. |
| `ls(path=None, candidates=None, *, user_id=None)` | Non-recursive listing. |
| `tree(path, max_depth=None, *, user_id=None)` | Recursive listing. |

### Pattern and Retrieval

| Method | Notes |
|--------|-------|
| `glob(pattern, *, paths=(), ext=(), max_count=None, candidates=None, user_id=None)` | Path matching with optional path and extension filters. |
| `grep(pattern, *, paths=(), ext=(), ext_not=(), globs=(), globs_not=(), case_mode="sensitive", fixed_strings=False, word_regexp=False, invert_match=False, before_context=0, after_context=0, output_mode="lines", max_count=None, candidates=None, user_id=None)` | Regex or fixed-string content search. |
| `semantic_search(query, k=15, *, candidates=None, user_id=None)` | Embedding-backed search using the mounted embedding provider and vector store. |
| `vector_search(vector, k=15, *, candidates=None, user_id=None)` | Raw vector lookup. |
| `lexical_search(query, k=15, *, candidates=None, user_id=None)` | BM25 or backend-native lexical ranking. |

### Graph Traversal and Ranking

| Method | Notes |
|--------|-------|
| `predecessors(path=None, *, candidates=None, user_id=None)` | Immediate inbound neighbors. |
| `successors(path=None, *, candidates=None, user_id=None)` | Immediate outbound neighbors. |
| `ancestors(path=None, *, candidates=None, user_id=None)` | Recursive inbound traversal. |
| `descendants(path=None, *, candidates=None, user_id=None)` | Recursive outbound traversal. |
| `neighborhood(path=None, *, candidates=None, depth=2, user_id=None)` | Radius-limited expansion. |
| `meeting_subgraph(candidates, *, user_id=None)` | Union of connecting paths between candidates. |
| `min_meeting_subgraph(candidates, *, user_id=None)` | Reduced meeting graph variant. |
| `pagerank(*, candidates=None, user_id=None)` | PageRank over the mounted graph projection. |
| `betweenness_centrality(*, candidates=None, user_id=None)` | Betweenness scoring. |
| `closeness_centrality(*, candidates=None, user_id=None)` | Closeness scoring. |
| `degree_centrality(*, candidates=None, user_id=None)` | Degree scoring. |
| `in_degree_centrality(*, candidates=None, user_id=None)` | Inbound degree scoring. |
| `out_degree_centrality(*, candidates=None, user_id=None)` | Outbound degree scoring. |
| `hits(*, candidates=None, user_id=None)` | HITS authority / hub scoring. |

### Query Engine

| Method | Notes |
|--------|-------|
| `parse_query(query)` | Parse a CLI-style query string into a `QueryPlan`. |
| `run_query(query, *, user_id=None, initial=None)` | Execute the parsed plan and return `VFSResult`. |
| `cli(query, *, user_id=None, initial=None)` | Execute and render to text. |

The query parser lives in `vfs.query` and supports stage aliases such as `search`, `grep`, `pred`, `succ`, `nbr`, `meetinggraph`, `pagerank`, and `top`.

## Results

```python
from vfs.results import EditOperation, Entry, LineMatch, TwoPathOperation, VFSResult
```

| Type | Purpose |
|------|---------|
| `VFSResult` | Unified envelope with `function`, `entries`, `success`, and `errors`. |
| `Entry` | Flat row shape used by every function. Fields are populated opportunistically by the producing operation. |
| `EditOperation` | Immutable batch edit descriptor for `edit()`. |
| `TwoPathOperation` | Immutable `(src, dest)` pair for `move()` and `copy()`. |
| `LineMatch` | `(start, end, match)` tuple for grep output with context windows. |

Useful `VFSResult` helpers:

```python
result.paths
result.content
result.file
result.top(10)
result.sort("score", reverse=True)
result.filter(lambda entry: entry.kind == "file")
result.to_json()
result.to_str()

combined = result | other
intersected = result & other
diffed = result - other
```

## Path Helpers

```python
from vfs.paths import (
    chunk_path,
    decompose_edge,
    edge_in_path,
    edge_out_path,
    version_path,
)
```

Canonical metadata paths:

| Entity | Helper |
|--------|--------|
| Chunk | `chunk_path("/src/auth.py", "login")` |
| Version | `version_path("/src/auth.py", 3)` |
| Outgoing edge | `edge_out_path("/src/auth.py", "/src/utils.py", "imports")` |
| Incoming edge | `edge_in_path("/src/auth.py", "/src/utils.py", "imports")` |

`decompose_edge()` turns a canonical edge path back into `source`, `target`, and `edge_type`.

## Error Model

```python
from vfs import GraphError, MountError, NotFoundError, ValidationError, VFSError, WriteConflictError
```

- `VFSClientAsync` returns failed `VFSResult` values for normal operational failures.
- `VFSClient` raises the corresponding `VFSError` subclass instead.
- Mount routing, validation, and graph execution errors are normalized through the shared exception hierarchy.

## Related Modules

- `vfs.query` exposes `QueryPlan`, `parse_query`, `execute_query`, and `render_query_result`.
- `vfs.permissions` exposes `PermissionMap` and the path-level permission helpers.
- `vfs.models` defines `VFSObject` and backend-facing storage models.
- `vfs.graph` exposes the in-memory graph provider used by `DatabaseFileSystem`.
