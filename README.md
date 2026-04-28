# VFS: One Namespace for Enterprise-Scale Context Engineering

<p align="center">
  <a href="https://pypi.org/project/vfs-py/"><img src="https://img.shields.io/pypi/v/vfs-py" alt="PyPI version"></a>
  <a href="https://pypi.org/project/vfs-py/"><img src="https://img.shields.io/pypi/pyversions/vfs-py" alt="Python"></a>
  <a href="https://github.com/ClayGendron/grover/actions/workflows/test.yml"><img src="https://github.com/ClayGendron/grover/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/ClayGendron/grover/blob/main/LICENSE"><img src="https://img.shields.io/github/license/ClayGendron/grover" alt="License"></a>
  <a href="https://codecov.io/gh/ClayGendron/grover"><img src="https://codecov.io/gh/ClayGendron/grover/branch/main/graph/badge.svg" alt="Coverage"></a>
</p>

Mount data, tools, and retrieval systems behind one virtual file system so agents can search, traverse, and act across enterprise context. VFS is an all-in-one tool that defines data engineering for AI agents.

```bash
pip install vfs-py
```

> ⚠️ **Alpha:** `vfs` is under active development and the API may change. Use for research and prototyping only.

## How to Get Started

`vfs` allows you to compose a single virtual file system from multiple sources.

```python
from vfs import VFSClient, LocalFileSystem, DatabaseFileSystem
from vfs.backends import PostgresFileSystem

g = VFSClient()

localfs = LocalFileSystem()
dbfs = DatabaseFileSystem(engine_url="sqlite+aiosqlite:///knowledge.db")

g.add_mount('/workspace', localfs)
g.add_mount('/enterprise', dbfs)

g.cli('write /workspace/auth.py "def login(user, password): return authenticate(user, password)"')
g.cli('read /enterprise/security-policy.md')
g.cli('search "how does user login work?" --k 10')
g.cli('grep "authenticate" | pagerank | top 15')

g.close()
```

`PostgresFileSystem` is the explicit PostgreSQL-native backend. It keeps the same public VFS API as `DatabaseFileSystem`, but pushes lexical search, grep, glob, graph traversal, and native pgvector search into Postgres. If you pass `vector_store=`, that override still wins for vector and semantic search.

> Every CLI command maps directly to a Python method.
>
> - `g.cli('write ...')` calls `g.write()`
> - `g.cli('search ...')` calls `g.semantic_search()`
> - pipelines like `grep | pagerank | top 15` chain results through `g.grep()` → `g.pagerank(candidates)` → `result.top(15)`.

Unix has been a foundational technology in computing for over 50 years because of its enduring core design principles: a uniform namespace, small composable tools, and portability. `vfs` builds on these principles to design the platform for building agent context and performing agentic actions.

- **Agent-First Design:** `vfs` is built around having the main *user* be a large language model running in a loop over a long time horizon. Building for LLMs means that operations within the file system are versioned and reversible, tools are discoverable *files* loaded into context when needed instead of by default, and every operation can be expressed through a composable CLI — the interface LLMs are increasingly trained to use.
- **Everything is a File:** Everything within `vfs` is addressable by path and conforms to standard data types. This single abstraction enables composable operations and predictable data within `vfs`.
- **Small, Composable, and On-Demand Tools:** Building a new tool for every use case should be the exception, not the norm. All the capabilities of `vfs` can be accessed and expressed through a CLI which frees up context to build more performant and predictable agents. Specialized tools and MCPs can be assigned their own file paths in `vfs` for ultimate flexibility without the cost of filling up context.
- **BYOI (Bring Your Own Infrastructure):** `vfs` has a database-first design and can run in-process with your application or as an MCP server. No new design patterns or infrastructure required — `vfs` runs where you need it and works with your existing AI applications.

> `vfs` is in alpha, so we are actively building towards this vision. Please test it out and provide your feedback!

## The `VirtualFileSystem`

The main class of this library is `VirtualFileSystem`. It handles mounting and routing across storage backends and defines the public API surface for `vfs`. The API combines familiar file system operations with search, graph traversal, and ranking. All public methods return the same composable result type, so one method's output can be used as input to the next.

| Category | Methods |
|----------|---------|
| **CRUD** | `read`, `write`, `edit`, `delete`, `move`, `copy`, `mkdir`, `mkedge` |
| **Navigation** | `ls`, `tree`, `stat` |
| **Pattern Search** | `glob`, `grep` |
| **Retrieval** | `semantic_search`, `lexical_search`, `vector_search` |
| **Graph Traversal** | `predecessors`, `successors`, `ancestors`, `descendants`, `neighborhood`, `meeting_subgraph`, `min_meeting_subgraph` |
| **Graph Ranking** | `pagerank`, `betweenness_centrality`, `closeness_centrality`, `degree_centrality`, `in_degree_centrality`, `out_degree_centrality`, `hits` |
| **Query Engine** | `run_query`, `cli` |
| **Lifecycle** | `add_mount`, `remove_mount` |

### Core Components

1. **File System.** A versioned, chunkable, permission-aware, database-backed file system for text and documents. All operations are reversible and protected against data loss.
2. **Retrieval.** Pluggable vector search and BM25 lexical search enable semantic and keyword retrieval across the file system. Embedding and indexing happen automatically on write.
3. **Graph.** Connections between files are first-class objects. Graph algorithms like PageRank, centrality, and subgraph extraction operate on the same paths as every other operation.

## How It Works

Everything in `vfs` is addressable by path. Files live in the user namespace, and metadata lives under the reserved `/.vfs/.../__meta__/...` tree:

```
/
├── workspace/
│   ├── auth.py                                       File
│   ├── utils.py                                      File
│   └── main.py                                       File
├── enterprise/
│   ├── onboarding.md                                 File
│   └── security-policy.md                            File
└── .vfs/
    └── workspace/
        └── auth.py/
            └── __meta__/
                ├── chunks/
                │   ├── login                         Chunk (function)
                │   └── AuthService                   Chunk (class)
                ├── versions/
                │   ├── 1                             Version (snapshot)
                │   └── 2                             Version (diff)
                └── edges/
                    └── out/
                        └── imports/
                            └── workspace/utils.py    Edge (dependency)
```

Metadata is explicit and opt-in. Ordinary `ls`, `glob`, and search operate on user paths. To inspect chunks, versions, or edges, browse canonical paths such as `/.vfs/workspace/auth.py/__meta__/chunks` or `/.vfs/workspace/auth.py/__meta__/edges/out`.

### Composable Results

Every operation returns a `VFSResult` with typed `Candidate` objects. Results support set algebra, so different retrieval strategies can be combined without LLM re-interpretation:

```python
# Intersection — Python files that match a semantic query
semantic = g.semantic_search("authentication")
python_files = g.glob("/workspace/**/*.py")
candidates = semantic & python_files

# Union — expand to graph neighbors
expanded = candidates | g.neighborhood(candidates)

# Re-rank by centrality
ranked = g.pagerank(candidates=expanded)
```

Or the same thing through the CLI:

```python
print(g.cli('search "authentication" | glob "/workspace/**/*.py" | nbr | pagerank'))
```

> `vfs` also provides `VFSClientAsync` as the async facade, which is the preferred path for application servers and long-running agents. The sync `VFSClient` wrapper shown in these examples is a convenience layer for scripts, notebooks, and data pipelines.

## Installation

Requires Python 3.12+.

```bash
pip install vfs-py                # core (SQLite, rustworkx, BM25)
pip install vfs-py[openai]        # OpenAI embeddings
pip install vfs-py[langchain]     # LangChain embedding provider
pip install vfs-py[postgres]      # PostgreSQL backend
pip install vfs-py[mssql]         # MSSQL backend
pip install vfs-py[pinecone]      # Pinecone vector store
pip install vfs-py[databricks]    # Databricks Vector Search
pip install vfs-py[search]        # usearch (local vector search)
pip install vfs-py[treesitter]    # JS/TS/Go code analyzers
pip install vfs-py[deepagents]    # deepagents integration
pip install vfs-py[langgraph]     # LangGraph persistent store
pip install vfs-py[all]           # everything
```

## Status and Roadmap

`vfs` is in alpha. The core file system, CLI query engine, graph algorithms, and BM25 lexical search are implemented and tested (2,157 tests, 99% coverage).

**What's coming next:**

- **MCP single-tool interface** — expose `vfs` as one MCP tool with progressive discovery via `--help`
- **Shell entrypoint** — run `vfs 'grep "auth" | pagerank | top 15'` directly from the terminal
- **`.api/` control plane** — live API pass-through for external services (Jira, Slack, GitHub) alongside synced data in the same namespace
- **LocalFileSystem** — mount local directories with files on disk and metadata in SQLite
- **More analyzers** — Markdown, PDF, email, Slack, Jira, CSV/JSON (code analyzers for Python, JS/TS, Go exist in v1)
- **Automatic embedding on write** — background indexing for semantic search without manual setup

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE](LICENSE).
