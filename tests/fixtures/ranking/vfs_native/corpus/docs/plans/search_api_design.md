# Search API Design: Findings & Architecture

> **Status:** Design complete. Method signatures ready to implement. Composable query engine deferred to future phase.

---

## Method Categories

Grover's query/search methods fall into five categories, each with a different natural input:

| Category | Methods | Natural input | What it does |
|----------|---------|---------------|--------------|
| **Pattern discovery** | `glob`, `grep` | `pattern` + `path` scope | Find files by name/content pattern |
| **Semantic search** | `vector_search`, `lexical_search`, `hybrid_search` | `query` string | Find files by meaning/keywords |
| **Navigation** | `list_dir`, `tree` | `path` to look at | Enumerate what exists at a location |
| **Graph traversal** | `predecessors`, `successors`, `ancestors`, `descendants`, `neighborhood`, `meeting_subgraph`, `min_meeting_subgraph` | A set of starting nodes | Follow relationships from starting nodes |
| **Graph scoring** | `pagerank`, `betweenness_centrality`, `closeness_centrality`, `katz_centrality`, `degree_centrality`, `in_degree_centrality`, `out_degree_centrality`, `hits` | A set of nodes to score | Rank nodes by structural importance |

Additionally:
- `list_versions` — versioning, not search. Takes a single file path.
- `search` — composite pipeline method (to be replaced by query engine later).

---

## The Uniform Model

Every method follows one rule:

1. **Receives a `FileSearchSet` (or None)** as its input scope (`candidates`)
2. **Performs its operation** within that scope
3. **Returns a `FileSearchResult`** — which IS-A `FileSearchSet`, so it can feed the next method

`None` means "everything" — operate on the full filesystem/graph. A `FileSearchSet` means "only these files."

This makes chaining completely predictable:

```python
# grep all files
g.grep("auth")

# grep only within these specific files
g.grep("auth", candidates=py_files)

# ancestors of all nodes
g.ancestors()

# ancestors of specific nodes
g.ancestors(some_set)
```

### Method Signatures

```python
# Pattern discovery — path is scope, candidates is optional filter
glob(pattern, path="/", *, candidates=None)
grep(pattern, path="/", *, candidates=None, ...)

# Semantic search — query is the question, candidates is optional filter
vector_search(query, k=10, *, candidates=None)
lexical_search(query, k=10, *, candidates=None)
hybrid_search(query, k=10, *, alpha=0.5, candidates=None)

# Navigation — path is what to look at, candidates is optional filter
list_dir(path="/", *, candidates=None)
tree(path="/", *, max_depth=None, candidates=None)

# Versioning — path is the file
list_versions(path)

# Graph traversal — candidates IS the input
ancestors(candidates)
descendants(candidates)
predecessors(candidates)
successors(candidates)
neighborhood(candidates, *, max_depth=2)
meeting_subgraph(candidates)
min_meeting_subgraph(candidates)

# Graph scoring — candidates IS the input (empty = all nodes)
pagerank(candidates)
betweenness_centrality(candidates)
# ... etc.
```

### When both `path` and `candidates` are provided

Both apply. `path` narrows the scope (directory to search within), `candidates` filters the results (only return files in this set). Example: `grep("auth", "/src", candidates=some_set)` greps under `/src` but only within files that are also in `some_set`.

---

## Composability via Set Algebra

The primary composition mechanism is **set algebra on results**, not threading `candidates` through methods:

```python
# Intersection — files matching both conditions
py_files = g.glob("**/*.py")
auth_files = g.grep("auth")
result = py_files & auth_files

# Union — files matching either condition
result = g.grep("auth") | g.vector_search("authentication")

# Pipeline — output feeds input
py_files = g.glob("**/*.py")
auth_py = g.grep("auth", candidates=py_files)  # only search .py files
deps = g.ancestors(auth_py)                      # find their dependencies
ranked = g.pagerank(deps)                        # rank by importance
```

The `candidates` parameter is useful when:
- **Pre-filtering grep** avoids reading file content for non-candidate files (performance)
- **Chaining into graph ops** where the set IS the input
- **Building pipelines** where output of one step feeds the next

For simple intersection/union, set algebra operators (`&`, `|`, `-`) are preferred.

---

## Natural Flow Direction

The typical flow is discovery → structure → action:

```
Broad discovery  →  Structural understanding  →  Action
(glob/grep/search)    (graph ops)                (read/write)
```

Reverse flows (graph → grep) are rare and handled by set algebra:

```python
related = g.descendants(some_set)
with_bugs = g.grep("FIXME") & related  # just intersect
```

---

## Composable Query Engine (Future)

All three design explorations converged on the same architecture:

### Core: Expression AST

Frozen dataclass nodes representing operations, composed with operators:

```python
from grover.query import Glob, Grep, Vector, Ancestors, PageRank

# Operator overloading builds an AST
plan = Glob("*.py") >> Grep("auth") >> Ancestors() >> PageRank()

# Fan-out with union
plan = (Grep("auth") | Vector("authentication")) >> Ancestors()

# Execute against a Grover instance
result = g.run(plan)
```

### Three surfaces, one engine

```
                    ┌─────────────┐
 String syntax ───▶ │             │
                    │   AST       │ ──▶ Evaluator ──▶ FileSearchResult
 Builder API ─────▶ │  (frozen    │
                    │  dataclasses)│
 Dict/JSON ───────▶ │             │
                    └─────────────┘
```

**Surface 1: Operator overloading** (Python code)
```python
result = g.run(Glob("*.py") >> Grep("auth") >> Ancestors() >> PageRank())
```

**Surface 2: Fluent builder** (IDE autocomplete)
```python
result = Q.grep("auth", glob_filter="**/*.py").ancestors().pagerank().where("score", ">", 0.01).limit(20).execute(g)
```

**Surface 3: GQL string syntax** (REST APIs / agents)
```sql
GREP "auth" IN "**/*.py"
|> ANCESTORS
|> PAGERANK
|> WHERE score > 0.01
|> ORDER BY score DESC
|> LIMIT 20
```

### AST node hierarchy

```
QueryNode (abstract base)
├── Discovery: GlobNode, GrepNode, VectorSearchNode, LexicalSearchNode, TreeNode, FilesNode
├── Transform: GraphTraversalNode, GraphScoringNode, VersionsNode
├── Filter: WhereNode, OrderByNode, LimitNode, OffsetNode
├── Composite: PipelineNode (A >> B), SetOpNode (UNION/INTERSECT/EXCEPT), WithNode (CTEs)
└── Predicate: ComparisonNode, LogicalNode (inside WHERE)
```

### Key design decisions

- **Pipeline-first, not SQL.** The `|>` pipe operator maps 1:1 to Grover's `FileSearchSet → FileSearchResult` pattern. SQL's `SELECT...FROM...WHERE` is the wrong frame — Grover has one entity type (files) with multiple access paths.
- **Evidence accumulates.** Each pipeline stage adds evidence to files. `WHERE score > X` inspects the evidence chain. Full provenance is always available via `explain(path)`.
- **CTEs via `WITH...AS`.** Named intermediate results for complex queries.
- **WHERE/ORDER BY/LIMIT** as first-class pipeline stages, not just SQL sugar.

### Implementation order (when we build this)

1. AST dataclasses (`grover/query/ast.py`)
2. Evaluator — recursive tree-walk dispatching to existing Grover methods
3. Operator overloading (`>>`, `|`, `&`) on AST nodes
4. Builder API (`Q` class)
5. JSON serialization (`to_dict()` / `from_dict()`)
6. String parser (lark or hand-rolled)

---

## Review Findings: Bugs in Current Implementation

The code review surfaced these issues with the current `candidates` implementation:

### Confirmed bugs

1. **`list_versions` missing `rebase(mount.path)`** in `api/file_ops.py` — version paths are mount-relative instead of absolute virtual paths.
2. **`vector_search` missing `rebase(mount.path)`** in `api/search_ops.py` — search result paths are mount-relative. (Pre-existing bug, not introduced by candidates change.)
3. **`UserScopedFileSystem.list_versions`** doesn't restore user-facing paths from stored paths — leaks internal `/{user_id}/` prefix.

### Design issues

4. **Silent error swallowing** in multi-path union logic — if 3 of 5 paths fail, caller gets `success=True` with partial results and no indication of failures.
5. **`search()` pipeline** doesn't check `success` before forwarding failed `FileSearchResult` as candidates to the next stage.
6. **`__bool__` divergence** — `FileSearchSet.__bool__` checks file count only; `FileSearchResult.__bool__` also checks `success`. Latent trap for `if candidates:` checks.
7. **Empty candidates vs None** — `list_dir`/`tree` in `DatabaseFileSystem` treat empty `candidates.paths` as "default to root" rather than "nothing matches." Contradicts the empty-means-nothing contract.

---

## DX Review Findings

### What worked well
- `FileSearchResult` inheriting from `FileSearchSet` enables Liskov substitution — any result feeds into any method
- Set algebra operators (`&`, `|`, `-`, `>>`) are powerful and natural
- Graph ops taking `FileSearchSet` as primary input is correct — "traverse from these nodes" is inherently a set operation

### What didn't work
- Replacing `path: str` with `candidates: FileSearchSet` on `list_dir`/`tree`/`list_versions` made the 80% use case worse: `list_dir("/project")` became `list_dir(FileSearchSet.from_paths(["/project"]))`
- The parameter name `candidates` is search jargon — confusing for navigation methods
- `None` semantics vary: "no filter" for glob/grep, "list root" for list_dir, "all mounts" for tree

### Resolution
Keep `path: str` as the primary input for methods that naturally take a path. Add `candidates` as an optional keyword filter. This preserves ergonomics while enabling composability:

```python
g.list_dir("/project")                              # simple — just works
g.grep("auth", candidates=g.glob("**/*.py"))        # composable — candidates filters
g.ancestors(g.grep("auth"))                          # graph ops — set IS the input
```
