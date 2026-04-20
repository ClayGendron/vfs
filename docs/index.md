# vfs

**The virtual file system for agents.** `vfs` gives applications and agent loops one path-based interface for CRUD, search, graph traversal, and composable CLI-style queries.

!!! warning "Alpha"
    `vfs` is still in alpha. Expect API changes while the core filesystem, query engine, and native database backends settle.

The docs site is published on GitHub Pages at `https://claygendron.github.io/vfs/`.

## Install

```bash
pip install vfs-py
pip install "vfs-py[postgres]"  # PostgreSQL-native search + pgvector
```

Requires Python 3.12+.

## Quick Start

```python
from sqlalchemy.ext.asyncio import create_async_engine

from vfs import VFSClient
from vfs.backends import DatabaseFileSystem, PostgresFileSystem

workspace_engine = create_async_engine("sqlite+aiosqlite:///workspace.db")
docs_engine = create_async_engine("postgresql+asyncpg://localhost/vfs_docs")

g = VFSClient()
g.add_mount("workspace", DatabaseFileSystem(engine=workspace_engine))
g.add_mount("docs", PostgresFileSystem(engine=docs_engine))

g.write("/workspace/auth.py", "def login(user):\n    return user\n")
g.write("/docs/notes.md", "# Auth notes\n\nLogin is implemented in auth.py.\n")
g.mkedge("/docs/notes.md", "/workspace/auth.py", "references")

matches = g.grep("login", paths=("/workspace", "/docs"))
ranked = g.pagerank(candidates=matches | g.neighborhood(candidates=matches))
print(ranked.top(10).to_str())

print(g.cli('grep "login" | nbr | pagerank | top 10'))

g.close()
```

`VFSClientAsync` exposes the same API without the sync wrapper. It is the preferred facade for application servers and long-running agent processes.

## Core Ideas

- **Everything is addressed by path.** User content lives in ordinary paths like `/workspace/auth.py`.
- **Metadata is explicit.** Chunks, versions, and edges live under canonical `/.vfs/.../__meta__/...` paths instead of being hidden behind side channels.
- **Results compose.** Every operation returns a `VFSResult`, so grep output can be piped into graph traversal, ranking, or further filtering without reshaping the data.
- **Mounts are first-class.** One client can route across multiple mounted filesystems and rebase paths automatically.

## Metadata Namespace

`vfs` reserves `/.vfs/<endpoint>/__meta__/...` for metadata paths:

```text
/
├── workspace/
│   └── auth.py
└── .vfs/
    └── workspace/
        └── auth.py/
            └── __meta__/
                ├── chunks/
                │   └── login
                ├── versions/
                │   └── 3
                └── edges/
                    └── out/
                        └── references/
                            └── docs/notes.md
```

Helper functions in `vfs.paths` build and decode these paths:

```python
from vfs.paths import chunk_path, decompose_edge, edge_out_path, version_path

chunk_path("/workspace/auth.py", "login")
version_path("/workspace/auth.py", 3)
edge = edge_out_path("/workspace/auth.py", "/docs/notes.md", "references")

parts = decompose_edge(edge)
assert parts.source == "/workspace/auth.py"
assert parts.target == "/docs/notes.md"
assert parts.edge_type == "references"
```

## Backends

`vfs` currently ships three database-backed filesystems:

- `DatabaseFileSystem` is the portable SQL baseline. It stores files, directories, chunks, versions, and edges in one `vfs_objects` table.
- `PostgresFileSystem` keeps the same public API but pushes grep, glob, lexical search, and native vector search into PostgreSQL when the schema supports it.
- `MSSQLFileSystem` provides the same API for SQL Server and Azure SQL with native full-text and regex pushdown.

All three work behind the same client and return the same `VFSResult` envelope.

## Result Model

`VFSResult` is the common result type for reads, writes, listings, searches, and graph algorithms.

```python
result = g.grep("login", paths=("/workspace",))
result.success
result.function
result.entries

top = result.top(5)
merged = result | g.glob("**/*.py", paths=("/workspace",))
print(top.to_str())
```

Each row is an `Entry` with a stable set of fields such as `path`, `kind`, `content`, `lines`, `score`, `in_degree`, `out_degree`, and `updated_at`.

## Query Engine

The query engine accepts CLI-style strings and executes them against the same mounted filesystems:

```python
plan = g.parse_query('grep "login" | nbr | pagerank | top 10')
result = g.run_query('grep "login" | nbr | pagerank')
rendered = g.cli('grep "login" | nbr | pagerank | top 10')
```

Useful stages include `grep`, `glob`, `search`, `lexical_search`, `pred`, `succ`, `nbr`, `meetinggraph`, `pagerank`, and `top`.

## Next Pages

- [API Reference](api.md) for the current client, backend, result, and query interfaces.
- [Architecture](architecture.md) for the routing, storage, and graph design.
- [Filesystem Internals](internals/fs.md) for the write path, session model, and storage details.
- [Contributing](contributing.md) for local setup and release workflow.
