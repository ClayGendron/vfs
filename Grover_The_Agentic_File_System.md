# `grover`: The Agentic File System

```bash
pip install grover
```

`grover` is an in-process file system that mounts data from multiple sources to enable agentic search and operations through a Unix-like interface.

Unix has been a foundational technology in computing for over 50 years because of its enduring core design principles: a uniform namespace, small composable tools, and portability. `grover` builds on these principles to design the platform for building agent context and performing agentic actions.

- **Agent-First Design:** `grover` is built around having the main *user* be a large language model running in a loop over a long time horizon. Building for LLMs means that operations within the file system are versioned and reversible, tools are discoverable *files* loaded into context when needed instead of by default, and every operation can be expressed through a composable CLI — the interface LLMs are increasingly trained to use.
- **Everything is a File:** Everything within `grover` is addressable by path and conforms to standard data types. This single abstraction enables composable operations and predictable data within `grover`.
- **Small, Composable, and On-Demand Tools:** Building a new tool for every use case should be the exception, not the norm. All the capabilities of `grover` can be accessed and expressed through a CLI which frees up context to build more performant and predictable agents. Specialized tools and MCPs can be assigned their own file paths in `grover` for ultimate flexibility without the cost of filling up context.
- **BYOI (Bring Your Own Infrastructure):** `grover` has a database-first design and can run in-process with your application or as an MCP server. No new design patterns or infrastructure required — `grover` runs where you need it and works with your existing AI applications.

Okay, lets get into how it works.

> `grover` is in alpha, so we are actively building towards this vision. Please test it out and provide your feedback!

## The `GroverFileSystem`

The main class of this library is `GroverFileSystem`. It handles mounting and routing across storage backends and defines the public API surface for `grover`. The API combines familiar file system operations with search, graph traversal, and ranking. All of the following public methods return the same result type so one method's output can be used as input to the next (with the exception of the `cli` method).

**CRUD**

`read`, `write`, `edit`, `delete`, `move`, `copy`, `mkdir`, `mkconn`

**Navigation**

`ls`, `tree`, `stat`

**Pattern Search**

`glob`, `grep`

**Retrieval**

`semantic_search`, `lexical_search`, `vector_search`

**Graph Traversal**

`predecessors`, `successors`, `ancestors`, `descendants`, `neighborhood`, `meeting_subgraph`, `min_meeting_subgraph`

**Graph Ranking**

`pagerank`, `betweenness_centrality`, `closeness_centrality`, `degree_centrality`, `in_degree_centrality`, `out_degree_centrality`, `hits`

**Query Engine**

`run_query`, `cli`

## One Minute Setup

A basic, multi-backend file system can be setup easily with `grover`.

```python
from grover import Grover, LocalFileSystem, DatabaseFileSystem

g = Grover()

localfs = LocalFileSystem()
dbfs = DatabaseFileSystem(engine_url="sqlite+aiosqlite:///knowledge.db")

g.add_mount('/workspace', localfs)
g.add_mount('/enterprise_knowledge_base', dbfs)

read_result = g.read('/workspace/README') # routes to localfs
write_result = g.write('/workspace/test.py', 'print("Hello, World!")') # routes to localfs
grep_result = g.grep("Hello") # searches both localfs and dbfs
```


