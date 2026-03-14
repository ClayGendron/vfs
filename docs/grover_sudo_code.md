Grover is a composable filesystem with search and graph traversal.

Setup is easy, define an async sqlalchemy engine and a mount path and pass in your database file system.

```python
from grover import Grover
from grover.backends import DatabaseFileSystem

from sqlachemy import async_engine

g = Grover()
backend = DatabaseFileSystem()


g.add_mount(
	path='documents/',
  backend=DatabaseFileSystem()
  engine=async_engine
)
```

You are then able to peform various types of operations on your filesystem, and if they have the `documents/` path, they will be routed to your `DatabaseFileSystem`.

**File Operations**

- read (single path)
- write (single path)
- edit (single path)
- delete (single path)
- move (src, target)
- copy (src, target)
- mkdir (single path)
- list_dir (single path)
- tree (single path)
- exists (single path)
- get_info (single path)
- get_permission_info (single path)
- list_versions (single path)
- read_version (single path)
- diff_versions (src, target)
- restore_version (single path)
- list_trash (single path)
- restore_from_trash (single path)
- empty_trash (single path)
- reconcile (single path)

**Graph Operations**

- add_connection (src, target)
- delete_connection (src, target)
- subgraph (nodes)
- min_meeting_subgraph (nodes)
- ego_graph (single path)
- predecessors (single path)
- ancestors (single path)
- successors (single path)
- descendants (single path)
- has_path (src, target)
- shortest_path (src, target)
- pagerank (nodes, edges)
- hits (nodes, edges)
- betweenness_centrality (nodes, edges)
- closeness_centrality (nodes, edges)
- harmonic_centrality (nodes, edges)
- katz_centrality (nodes, edges)
- degree_centrality (nodes, edges)
- in_degree_centrality (nodes, edges)
- out_degree_centrality (nodes, edges)
- community_louvain (nodes, edges)
- common_neighbors (nodes, edges)

**Search Operations**

- glob
- grep
- vector_search
- lexical_search
- hybrid_search
- search (don't implement yet)