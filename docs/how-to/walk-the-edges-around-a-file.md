<!--
DIÁTAXIS TYPE: How-to guide (task-oriented)
THE RULE: Assume competence. Steps to a goal. No "why" — link to Explanation.
-->

# How to walk the edges around a file

Goal: given a file, find what points at it, what it reaches, and what joins it to another file, through the typed edges authored with `mkedge`.

## Author the edges

An edge is a typed arrow from a source file to a target file. Both must exist.

```python
await fs.write(path="/src/app.py", content="import db, config", parents=True)
await fs.write(path="/src/db.py", content="import config")
await fs.write(path="/src/config.py", content="")
await fs.write(path="/docs/setup.md", content="see config", parents=True)
await fs.mkedge(source="/src/app.py", target="/src/db.py", edge_type="imports")
await fs.mkedge(source="/src/app.py", target="/src/config.py", edge_type="imports")
await fs.mkedge(source="/src/db.py", target="/src/config.py", edge_type="imports")
await fs.mkedge(source="/docs/setup.md", target="/src/config.py", edge_type="mentions")
```

## Ask what points at a file

`inbound` follows each edge from its target back to its source. The default depth is one hop.

```python
result = await fs.graph("inbound", "/src/config.py")
nodes = [o for o in result.observations if o.edge_target is None]
assert [str(o.path) for o in nodes] == ["/src/config.py", "/docs/setup.md", "/src/app.py", "/src/db.py"]
assert [o.depth for o in nodes] == [0, 1, 1, 1]
```

The seed is the first row at depth 0. Edge rows follow the node rows; each names its source as `path` and its target as `edge_target`.

```python
edges = [o for o in result.observations if o.edge_target is not None]
assert {(str(o.path), o.edge_type) for o in edges} == {
    ("/docs/setup.md", "mentions"),
    ("/src/app.py", "imports"),
    ("/src/db.py", "imports"),
}
```

## Ask what a file reaches

`outbound` follows the arrows forward. `depth=None` walks until nothing new is reached; the visited set bounds it.

```python
result = await fs.graph("outbound", "/src/app.py", depth=None)
assert {str(o.path): o.depth for o in result.observations if o.edge_target is None} == {
    "/src/app.py": 0,
    "/src/db.py": 1,
    "/src/config.py": 1,
}
```

## Follow one kind of edge

Name the types to follow, or the types to skip. The hierarchy's own `fs` edges are followed only when you name them.

```python
only_mentions = await fs.graph("inbound", "/src/config.py", edge_types=("mentions",))
assert [str(o.path) for o in only_mentions.observations if o.edge_target is None] == ["/src/config.py", "/docs/setup.md"]

subtree = await fs.graph("outbound", "/src", edge_types=("fs",), depth=None)
assert {str(o.path) for o in subtree.observations if o.edge_target is None} == {
    "/src", "/src/app.py", "/src/config.py", "/src/db.py",
}
```

## Join two files

`meet` walks out from every seed until they share one component and returns the subgraph that joins them. Seeds come as observations.

```python
from vfs.models import Observation

seeds = [Observation(path="/docs/setup.md"), Observation(path="/src/app.py")]
joined = await fs.graph("meet", observations=seeds, depth=None)
assert {str(o.path) for o in joined.observations if o.edge_target is None} == {
    "/docs/setup.md", "/src/app.py", "/src/config.py",
}
```

When the seeds do not connect, the result carries an `info` record of kind `not_found` with `data["components"]`.

## Bound the answer

`limit` (default 128) keeps the nearest nodes and drops every edge touching a cut node; the cut is a `truncated` warning.

```python
from vfs.results import ErrorKind

cut = await fs.graph("inbound", "/src/config.py", limit=2)
assert len([o for o in cut.observations if o.edge_target is None]) == 2
assert cut.errors[0].kind == ErrorKind.truncated
assert cut.errors[0].data == {"limit": 2, "nodes_found": 4, "depth_reached": 1}
```

## Read it as text

`str(result)` draws the walk as a tree: each node under the node that reached it, the edge type and arrow on the line, the depth in brackets, and every further edge marked where its source sits.

```python
print(await fs.graph("outbound", "/src/app.py", depth=None))
```

A caller sees only the nodes its rights let it name; nothing is reached through a node it cannot. For the rights rules, read [Share a folder with grants](share-a-folder-with-grants.md).
