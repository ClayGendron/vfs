# Filesystem Architecture

## High-Level Flow

```mermaid
graph TD
    Caller["Caller"]
    Client["VFSClient / VFSClientAsync"]
    Router["VirtualFileSystem router"]
    Mount["Mounted filesystem"]
    Graph["RustworkxGraph projection"]
    Search["Embedding provider / vector store"]
    Table["vfs_objects table"]

    Caller --> Client
    Client --> Router
    Router --> Mount
    Mount --> Table
    Mount --> Graph
    Mount --> Search
```

The client does not store user content itself. It routes each operation to the mounted filesystem that owns the path, then rebase-paths the returned `VFSResult`.

## Metadata Layout

```mermaid
graph TD
    Root["/workspace/auth.py"]
    Meta["/.vfs/workspace/auth.py/__meta__"]
    Chunks["chunks/login"]
    Versions["versions/3"]
    Edges["edges/out/imports/workspace/utils.py"]

    Root --> Meta
    Meta --> Chunks
    Meta --> Versions
    Meta --> Edges
```

Files, chunks, versions, and edges all share the same path vocabulary. That is why the graph, query engine, and storage layer compose cleanly.

## Write Path

```mermaid
sequenceDiagram
    participant C as Caller
    participant R as Router
    participant F as DatabaseFileSystem
    participant DB as SQL Session
    participant G as Graph Projection

    C->>R: write("/workspace/auth.py", content)
    R->>F: write("/auth.py", content, session=...)
    F->>DB: stage version metadata
    F->>DB: write content / metadata row
    F->>DB: flush()
    F-->>R: VFSResult(success=True)
    R->>DB: commit
    R->>G: project edge or graph updates as needed
    R-->>C: rebased VFSResult
```

The important invariant is content-before-commit. Backends never own the final commit; the router does.

## Backend Responsibilities

| Layer | Responsibility |
|------|----------------|
| `VirtualFileSystem` | Mount routing, session injection, result rebasing, fanout across mounts |
| `DatabaseFileSystem` | Portable CRUD, metadata semantics, SQL prefiltering, graph delegation |
| `PostgresFileSystem` | PostgreSQL-native grep, glob, lexical search, and pgvector search |
| `MSSQLFileSystem` | SQL Server-native grep, glob, and full-text search |
| `RustworkxGraph` | In-memory projection for traversal and ranking |

For the reasoning behind these boundaries, see [Architecture](architecture.md) and [Filesystem Internals](internals/fs.md).
