# User-Scoped Filesystem Implementation Plan

## Context

Grover is deployed as a web app where users share an organizational knowledge base and have private files. The mount topology:

```python
g.add_mount('/snhu', DatabaseFileSystem(engine=shared_engine))                    # shared
g.add_mount('/user', DatabaseFileSystem(engine=user_engine, user_scoped=True))    # per-user

await g.semantic_search("auth", user_id="123")
# /snhu: searches everything (ignores user_id for now)
# /user: searches only /123/** paths in DB
```

`user_id` is passed per-method-call, not per-constructor. Path-prefix approach: user "123" writing `/docs/README.md` stores it as `/123/docs/README.md`. Path stays globally unique. No schema changes. `owner_id` is the DB column on `GroverObjectBase`.

## Files to Modify

| File | What changes |
|------|-------------|
| `src/grover/paths.py` | Add `validate_user_id`, `scope_path`, `unscope_path` |
| `src/grover/results.py` | Add `GroverResult.strip_user_scope()` |
| `src/grover/base.py` | Add `user_id` to all public methods, all `_*_impl` stubs, all routing methods |
| `src/grover/backends/database.py` | Add `user_scoped` flag, scoping helpers, update all `_*_impl` overrides, BM25 scoping |
| `src/grover/vector_store.py` | Add `path_prefix` to `VectorStore.query()` protocol |
| `src/grover/databricks_store.py` | Implement `path_prefix` filtering with overfetch |
| `src/grover/graph/rustworkx.py` | Add `user_scoped` flag, per-user `_load()` filtering, `user_id` on all methods |
| `src/grover/graph/protocol.py` | Add `user_id` to all protocol method signatures |
| `src/grover/models.py` | Review all path-bearing fields for scoping correctness |
| `src/grover/query/executor.py` | Thread `user_id` through all helpers → filesystem calls |
| `tests/test_user_scoping.py` | New test file |
| `tests/test_base.py` | Update `_*_impl` overrides in helper subclasses to accept `user_id` |
| `tests/test_routing.py` | Update `_*_impl` overrides in helper subclasses to accept `user_id` |
| `tests/conftest.py` | Update shared test helpers if they override `_*_impl` methods |

---

## Phase 1: Path Scoping Utilities (`paths.py`)

Add at the bottom:

- **`validate_user_id(user_id: str) -> tuple[bool, str]`** — reject empty, `/`, `..`, `\0`, `@`, >255 chars
- **`scope_path(path: str, user_id: str) -> str`** — `"/docs/README"` + `"123"` → `"/123/docs/README"`. Root → `"/123"`
- **`unscope_path(path: str, user_id: str) -> str`** — reverse. Raises if prefix doesn't match

**Connection paths have scoped targets** — both source and target are prefixed:
- `/.vfs/123/src/main.py/__meta__/edges/out/imports/123/src/auth.py`
- `decompose_edge()` naturally gives `source=/123/src/main.py`, `target=/123/src/auth.py` — matches DB columns exactly
- Unscoping uses `decompose_edge()` → `unscope_path()` both parts → `edge_out_path()` to reconstruct

---

## Phase 2: Result Unscoping (`results.py`)

Add `GroverResult.strip_user_scope(user_id: str) -> GroverResult`:
- For each candidate, check if path is a connection path via `decompose_edge()`
- If connection: unscope source and target separately, reconstruct with `edge_out_path()`
- Otherwise: call `unscope_path(c.path, user_id)`
- Returns new `GroverResult` with unscoped paths (mirrors `add_prefix()` pattern)

---

## Phase 3: Public API + Stubs (`base.py`)

**Add `*, user_id: str | None = None` to every public method and `_*_impl` stub.** All routing methods get explicit `user_id` parameter — not relying on `**kwargs` flow.

### Public methods (30+)

```python
async def read(self, path=None, candidates=None, *, user_id=None):
    return await self._route_single("read", path, candidates, user_id=user_id)
```

### Routing methods — ALL get explicit `user_id`

**`_route_single(op, path, candidates, *, user_id=None, **kwargs)`** — pass `user_id=user_id` to `_*_impl` calls

**`_dispatch_candidates(op, candidates, *, user_id=None, **kwargs)`** — pass `user_id=user_id` to `_*_impl`

**`_route_fanout(op, candidates, *, user_id=None, **kwargs)`** — pass `user_id=user_id` to `_query_self()` impl call AND to public method calls on child mounts

**`_route_two_path(op, ops, *, overwrite, user_id=None)`** — pass to `_*_impl` and `_cross_mount_transfer`

**`_cross_mount_transfer(..., user_id=None)`** — pass to `_read_impl`, `_write_impl`, `_delete_impl`

**`_route_write_batch(objects, overwrite, *, user_id=None)`** — pass to `_write_impl`

### `_*_impl` stubs (28)

All get `user_id: str | None = None` before `session`:
```python
async def _read_impl(self, path=None, candidates=None, *, user_id=None, session): ...
```

### CLI entry points

```python
async def run_query(self, query, *, user_id=None, initial=None):
    plan = self.parse_query(query)
    return await execute_query(self, plan, initial=initial, user_id=user_id)
```

`user_id` is a parameter to `run_query`/`cli`, NOT part of the query string.

---

## Phase 4: Model Review (`models.py`)

**Path-bearing fields on `GroverObjectBase`:**

| Field | Scoped? | How |
|-------|---------|-----|
| `path` | Yes | Scoped by `_*_impl` before object creation |
| `parent_path` | Auto | Derived from `path` by `_rederive_path_fields()` / `_normalize_and_derive()` |
| `name` | No | Derived from `path`, not affected by prefix |
| `source_path` | Yes | For connections: scoped source. Derived naturally by `decompose_edge()` from the scoped connection path |
| `target_path` | Yes | For connections: scoped target (`/123/src/auth.py`). Derived naturally by `decompose_edge()` — no override needed |
| `original_path` | No change | Currently unused, no scoping needed |
| `owner_id` | Set | Set to `user_id` on writes in user-scoped FS |

**`_normalize_and_derive`** (line 472): The validator derives `source_path` and `target_path` from `decompose_edge(path)`. With Option B (scoped target in path), `decompose_edge("/.vfs/123/src/main.py/__meta__/edges/out/imports/123/src/auth.py")` naturally gives `target="/123/src/auth.py"` — matching the scoped value. No explicit override needed. The validator works correctly without modification.

---

## Phase 5: DatabaseFileSystem Scoping (`database.py`)

### 5a. Constructor

```python
def __init__(self, ..., user_scoped: bool = False):
    self._user_scoped = user_scoped
```

### 5b. Private helpers

```python
def _scope_path(self, path: str | None, user_id: str | None) -> str | None:
    # Returns path unchanged if not user_scoped or user_id is None or path is None

def _scope_candidates(self, candidates: GroverResult | None, user_id: str | None) -> GroverResult | None:
    # Scope all candidate paths

def _unscope_result(self, result: GroverResult, user_id: str | None) -> GroverResult:
    # result.strip_user_scope(user_id) if user_scoped

def _require_user_id(self, user_id: str | None) -> str:
    # Raises ValueError if user_scoped and no user_id; validates format

def _scope_objects(self, objects: Sequence[GroverObjectBase], user_id: str | None) -> None:
    # Mutates objects in place: scope path, source_path, target_path, set owner_id
    # Called by _write_impl and _mkconn_impl when receiving raw objects
    if not self._user_scoped or user_id is None:
        return
    for obj in objects:
        obj.path = scope_path(obj.path, user_id)
        if obj.source_path:
            obj.source_path = scope_path(obj.source_path, user_id)
        if obj.target_path:
            obj.target_path = scope_path(obj.target_path, user_id)
        obj.owner_id = user_id
        obj._rederive_path_fields()
```

### 5c. Each `_*_impl` pattern

```python
async def _read_impl(self, path=None, candidates=None, *, user_id=None, session):
    if self._user_scoped:
        self._require_user_id(user_id)
    path = self._scope_path(path, user_id)
    candidates = self._scope_candidates(candidates, user_id)
    # ... existing logic unchanged ...
    return self._unscope_result(result, user_id)
```

**Internal method calls** (edit calls read+write, copy calls read+write): pass `user_id` through.

### 5d. Connection creation (`_mkconn_impl`) — scoped source AND target

In a user-scoped FS, connections can ONLY connect files within the same user's namespace. Both source and target are verified to exist as the user's files.

**Connection path format:** both source and target are scoped:
```
/.vfs/123/src/main.py/__meta__/edges/out/imports/123/src/auth.py
```

**DB columns — all derived naturally by `decompose_edge()` from the path:**
- `source_path` = `/123/src/main.py` (scoped)
- `target_path` = `/123/src/auth.py` (scoped)

```python
async def _mkconn_impl(self, source=None, target=None, edge_type=None, *, user_id=None, session):
    if self._user_scoped and user_id:
        source = scope_path(source, user_id)
        target = scope_path(target, user_id)
        # Verify both exist as user's files
    # edge_out_path(source, target, conn_type) builds the full path
    # _normalize_and_derive decomposes it → source_path, target_path match
    ...
```

**Unscoping connection results:** `strip_user_scope()` uses `decompose_edge()` to parse, `unscope_path()` both source and target, then `edge_out_path()` to reconstruct:
- `/.vfs/123/src/main.py/__meta__/edges/out/imports/123/src/auth.py` → `/.vfs/src/main.py/__meta__/edges/out/imports/src/auth.py`

### 5e. Write — scope objects and set `owner_id`

`_write_impl` accepts both `path + content` (single file) and `objects` (batch). Both paths need scoping:

- **Single file:** `path = self._scope_path(path, user_id)`, then construct object with `owner_id=user_id`
- **Batch objects:** `self._scope_objects(objects, user_id)` — scopes `path`, `source_path`, `target_path`, sets `owner_id`, calls `_rederive_path_fields()`
- **`_route_write_batch`** in `base.py` (line 388) passes objects through to `_write_impl` — the scoping happens inside the impl, not in routing

### 5f. Glob pattern scoping

When `candidates is None` (DB query mode):
```python
if self._user_scoped and user_id:
    if pattern.startswith("/"):
        scoped_pattern = f"/{user_id}{pattern}"
    else:
        scoped_pattern = f"/{user_id}/{pattern}"
```
Use `scoped_pattern` for SQL LIKE and regex compilation.

### 5g. Grep — add path prefix filter

When `candidates is None`, add WHERE clause to the SQL query:
```python
if self._user_scoped and user_id:
    stmt = stmt.where(self._model.path.like(f"/{user_id}/%"))
```

### 5h. BM25 Lexical Search — scope BOTH functions

**`_fetch_lexical_docs()`** (line 169): Add path prefix filter to the SQL pre-filter query. Both the candidate-hydration path (line 237) and the term-matching path (line 271) need:
```python
if self._user_scoped and user_id:
    stmt = stmt.where(self._model.path.like(f"/{user_id}/%"))
```

**`_fetch_corpus_stats()`** (line 296): Add the same path prefix filter to corpus size and average doc length queries. Without this, IDF scores are computed against the global corpus (all users), diluting user-specific relevance. The corpus statistics must reflect only the user's documents:
```python
base_where.append(self._model.path.like(f"/{user_id}/%"))
```

---

## Phase 6: VectorStore Protocol Update — `owner_id` Column Filtering

Paths in the vector store are stored with user prefix (scoped), but filtering uses the `owner_id` column, not path prefix matching.

### 6a. `vector_store.py` — add `owner_id` to protocol

```python
@dataclass(frozen=True)
class VectorItem:
    path: str
    vector: list[float]
    owner_id: str | None = None    # NEW — stored as filterable column

class VectorStore(Protocol):
    async def query(
        self, vector: list[float], *,
        k: int = 10,
        paths: list[str] | None = None,
        owner_id: str | None = None,    # NEW — filter to this owner's vectors
    ) -> list[VectorHit]: ...
```

### 6b. `databricks_store.py` — filter on `owner_id` column

Databricks Vector Search supports column filters natively:
```python
async def query(self, vector, *, k=10, paths=None, owner_id=None):
    filters = {}
    if owner_id is not None:
        filters["owner_id"] = owner_id
    resp = await asyncio.to_thread(
        idx.similarity_search,
        query_vector=vector,
        columns=[self._pk_column],
        filters=filters if filters else None,
        num_results=k,
    )
    ...
```

`upsert()` must store `owner_id` alongside each vector — the Databricks index column must include `owner_id`.

### 6c. `_vector_search_impl` — pass `owner_id`

```python
owner = user_id if self._user_scoped and user_id else None
hits = await self._vector_store.query(vector, k=k, paths=paths, owner_id=owner)
```

### 6d. Write pipeline — upsert with `owner_id`

When `_write_impl` upserts vectors, include `owner_id`:
```python
VectorItem(path=scoped_path, vector=embedding, owner_id=user_id)
```

---

## Phase 7: Graph Updates (`graph/rustworkx.py`)

### 7a. Constructor — add `user_scoped` flag + per-user tracking

```python
def __init__(self, model, ttl=3600, user_scoped: bool = False):
    self._user_scoped = user_scoped
    self._loaded_user_id: str | None = None  # track which user's data is loaded
```

### 7b. `_load()` — filter by user_id for user-scoped FS

A blank `pagerank()` on a user-scoped FS must NOT compute over all users' data. The graph must only contain the calling user's nodes and edges.

**`ensure_fresh(session, *, user_id=None)`** — reload if user_id changed OR TTL expired:
```python
async def ensure_fresh(self, session, *, user_id=None):
    if self._user_scoped and user_id != self._loaded_user_id:
        await self._load(session, user_id=user_id)
        return
    if self._loaded_at is not None and (time.monotonic() - self._loaded_at) < self._ttl:
        return
    await self._load(session, user_id=user_id)
```

**`_load(session, *, user_id=None)`** — add path prefix filter:
```python
stmt = select(self._model).where(
    self._model.kind == "edge",
    self._model.deleted_at.is_(None),
)
if self._user_scoped and user_id:
    stmt = stmt.where(self._model.path.like(f"/{user_id}/%"))
...
self._loaded_user_id = user_id
```

Both `source_path` and `target_path` DB columns store scoped values (derived naturally from the scoped connection path). The graph uses these columns directly — edges are correctly scoped:
```python
src = obj.source_path   # "/123/src/main.py" (scoped)
tgt = obj.target_path   # "/123/src/auth.py" (scoped)
```

### 7c. Graph methods — accept `user_id`

All graph methods get `user_id: str | None = None` and pass it to `ensure_fresh()`:
```python
async def predecessors(self, candidates, *, session, user_id=None):
    await self.ensure_fresh(session, user_id=user_id)
    ...
```

DatabaseFileSystem graph `_*_impl` methods pass `user_id` through to the graph.

---

## Phase 8: Query Executor (`query/executor.py`)

Add `user_id: str | None = None` to:
- `execute_query()`, `_execute_node()`, `_execute_stage()`
- All helper functions: `_read_like`, `_execute_transfer`, `_execute_mkconn`, `_execute_tree`, `_execute_glob`, `_execute_grep`, `_execute_lexical`, `_execute_graph_traversal`, `_execute_rank`, `_collect_tree`

Every `filesystem.xxx(...)` call gets `user_id=user_id`. The `user_id` is NOT in the query string — it's passed as a parameter to `run_query()` / `cli()`.

---

## Phase 9: Tests

### 9a. Existing test signature updates

`test_base.py` and `test_routing.py` have helper subclasses (e.g., `DummyFS`) that override `_*_impl` methods. Once routing passes `user_id`, these overrides must accept it — even when `user_id=None`:

```python
# Before:
async def _read_impl(self, path=None, candidates=None, *, session):

# After:
async def _read_impl(self, path=None, candidates=None, *, user_id=None, session):
```

This is mechanical but must be done for ALL overridden `_*_impl` methods in test helpers, or they'll raise `TypeError` when routing passes `user_id=None`.

### 9b. New test file (`tests/test_user_scoping.py`)

**Path utility tests:**
- `validate_user_id` — rejects empty, `/`, `..`, `\0`, `@`; accepts alphanumeric, UUID
- `scope_path` / `unscope_path` — basic paths, root, already-scoped

**DatabaseFileSystem integration tests:**
- Two users write same logical path — read isolation verified
- `ls`, `glob`, `grep`, `tree` — only user's files returned
- `delete`, `move`, `copy`, `edit` — scoped correctly
- `mkedge` — source/target verified as user's files, connection path has scoped source AND target, `decompose_edge()` matches DB columns, unscoping strips both
- `owner_id` set on writes
- `user_id=None` on scoped FS raises `ValueError`
- `user_id` on non-scoped FS is ignored
- BM25 lexical search uses per-user corpus stats
- Vector search with `path_prefix` filtering

**Graph tests:**
- Connections load with correct scoped endpoints
- Traversal stays within user namespace
- Two users' graphs don't leak

**Mount integration tests:**
- Mixed mount (shared + user-scoped) — glob/search finds files from both
- Query engine with `user_id` parameter

---

## Implementation Order

1. Phase 1 (paths.py) — no deps
2. Phase 2 (results.py) — depends on Phase 1
3. Phase 4 (models.py review) — independent, inform Phase 5
4. Phase 3 (base.py) — independent
5. Phase 6 (vector_store.py, databricks_store.py) — independent
6. Phase 7 (rustworkx.py) — independent
7. Phase 5 (database.py) — depends on Phases 1-4, 6-7
8. Phase 8 (executor.py) — depends on Phase 3
9. Phase 9 (tests) — depends on all

Phases 1-4 and 6-7 can be parallelized.

## Verification

```bash
uv run pytest tests/test_user_scoping.py
uv run pytest
uvx ruff check src/ tests/
uvx ty check src/
```
