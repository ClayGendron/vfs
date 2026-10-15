<!--
DIÁTAXIS TYPE: Reference (information-oriented)
THE RULE: Austere, neutral, complete. Describe the machinery; do not instruct
or explain. Structure MIRRORS the code. Accuracy is the whole job.
SOURCE TO MIGRATE FROM: docs/api.md
-->

# API reference

## Identity

`VirtualFileSystem(..., default_authority: Authority | None = None)`. The authority used for any call that passes none. When it is `None`, such calls run as `Authority.anonymous()`.

`VirtualFileSystem.session(authority: Authority) -> Session`. See [Session](session.md).

Every verb takes a keyword-only `authority: Authority | None = None`. An explicit value wins over the default. See [Authority and Principal](authority.md).

### Error kinds

| Kind | Value | Meaning |
|---|---|---|
| `unauthenticated` | `vfs.unauthenticated` | the target needs a named authority; hint: open a session with an authority, or configure a default |
| `permission_denied` | `vfs.permission_denied` | the authority may not perform the operation on the target |
| `read_only` | `vfs.read_only` | the target is read-only; distinct from authorization |

`vfs.UnauthenticatedError` is the exception class `exception_for_kind` maps to `unauthenticated`, raised by `raise_if_failed` on a result carrying that kind.

## graph

`VirtualFileSystem.graph(method, path=None, observations=None, *, depth=1, edge_types=(), edge_types_not=(), minimal=False, limit=128, columns=None, authority=None) -> Result`

A frontier walk over the edges `mkedge` authored, one seed path or many seed observations (an observation contributes its `path`). Each hop is one chunked statement per frontier chunk; the application keeps the visited set, so `depth=None` ends when nothing new is reached.

| Method | Follows |
|---|---|
| `outbound` | each edge from its `source` to its `target` — what the seeds point to |
| `inbound` | each edge from its `target` back to its `source` — what points at the seeds |
| `neighborhood` | both directions |
| `meet` | both directions from every seed until the seeds share one component; the answer is the subgraph that joins them, and `minimal=True` prunes it to the nodes that keep them connected |

| Parameter | Meaning |
|---|---|
| `depth` | hops from the nearest seed; `None` walks until the frontier empties; for `meet`, the radius per seed |
| `edge_types` | follow only these types; empty follows every authored type and never the hierarchy's `fs` edges unless named |
| `edge_types_not` | never follow these types; a type in both lists is `invalid` |
| `minimal` | `meet` only — `invalid` with any other method |
| `limit` | node rows to return per storage, nearest first; `None` returns every row; a cut is a `truncated` warning carrying `limit`, `nodes_found` and `depth_reached` |
| `columns` | the fields a node row carries beyond `path`, `kind` and `depth`; bodies never ride a walk |

Rows come in two shapes. A **node row** has no `edge_target`: `path`, `kind`, `depth` (distance from the nearest seed, seeds at 0) and the requested columns, in `(depth, path)` order. An **edge row** is the shape `mkedge` returns — `path` is the source, with `edge_target`, `edge_type`, `edge_weight` and `edge_distance` — and the edge rows are every selected edge among the returned nodes, after the node rows, in `(source, type, target)` order. An edge touching a cut node is cut too.

Rights are judged on every hop at the rung the verb table declares: a caller passes an edge only when it holds `list` on both endpoints, and a node it holds `read` on comes back whole while one it holds only `list` on comes back bare (`path`, `kind`, `depth`), its edges carrying their type and no measure. Nothing is reached through a node the caller may not name. When `meet` leaves the seeds in more than one component, an `info` record of kind `not_found` reports `seeds` and `components`.

```python
await fs.write(path="/src/app.py", content="import db", parents=True)
await fs.write(path="/src/db.py", content="import config")
await fs.write(path="/src/config.py", content="")
await fs.mkedge(source="/src/app.py", target="/src/db.py", edge_type="imports")
await fs.mkedge(source="/src/db.py", target="/src/config.py", edge_type="imports")

result = await fs.graph("inbound", "/src/config.py")
nodes = [o for o in result.observations if o.edge_target is None]
edges = [o for o in result.observations if o.edge_target is not None]
assert [(str(o.path), o.depth) for o in nodes] == [("/src/config.py", 0), ("/src/db.py", 1)]
assert [(str(o.path), str(o.edge_target), o.edge_type) for o in edges] == [("/src/db.py", "/src/config.py", "imports")]

whole = await fs.graph("inbound", "/src/config.py", depth=None)
assert len([o for o in whole.observations if o.edge_target is None]) == 3
```
