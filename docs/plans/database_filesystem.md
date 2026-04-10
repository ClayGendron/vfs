# DatabaseFileSystem Implementation Plan

## Context

Grover's "everything is a file" redesign has a working foundation: `GroverFileSystem` base class (mount routing, session management), `GroverObject` model (unified `grover_objects` table), `paths.py` (kind detection, parent derivation), `results.py` (composable result types), and `RustworkxGraph` (in-memory graph). What's missing is the **backend that actually stores and retrieves data** — `DatabaseFileSystem`.

The base class defines 34 `_*_impl` async stubs. DatabaseFileSystem overrides these to implement kind-aware CRUD, search, and graph delegation against the single `grover_objects` table.

## Files to Create

1. **`src/grover/backends/database.py`** — DatabaseFileSystem (~400-500 lines)
2. **`src/grover/patterns.py`** — Glob utilities ported from `src_old/grover/util/patterns.py` (~146 lines, near-direct copy)
3. **`tests/test_database.py`** — Integration tests with in-memory SQLite

## Files to Read (not modify)

- `src/grover/base.py` — parent class, calling conventions
- `src/grover/models.py` — `GroverObject`, `GroverObjectBase`, validator
- `src/grover/paths.py` — `parse_kind`, `parent_path`, `connection_path`, `decompose_connection`, `version_path`
- `src/grover/results.py` — `GroverResult`, `Candidate`, `Detail`, `EditOperation`, `TwoPathOperation`
- `src/grover/graph/rustworkx.py` — `RustworkxGraph` constructor and API

## Design

### Constructor

```python
class DatabaseFileSystem(GroverFileSystem):
    def __init__(
        self,
        *,
        engine: AsyncEngine | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        model: type[GroverObjectBase] = GroverObject,
    ) -> None:
        super().__init__(engine=engine, session_factory=session_factory)
        self._model = model
        self._graph = RustworkxGraph(model=model)
```

### Internal Helpers (6 methods)

1. **`_get_object(path, session, include_deleted=False)`** → `GroverObjectBase | None`
   - `SELECT ... WHERE path = :path AND deleted_at IS NULL`

2. **`_to_candidate(obj, operation, score=None)`** → `Candidate`
   - Projects `GroverObjectBase` → `Candidate` with a `Detail` for provenance. Always includes content; downstream stages reuse it without re-querying.

3. **`_ensure_parent_dirs(path, session)`** → `None`
   - Walk up from `parent_path(path)` to `/`, batch-insert missing directory objects

4. **`_cascade_delete(path, session, timestamp)`** → `int`
   - Files: `UPDATE ... SET deleted_at WHERE parent_path = :path`
   - Dirs: `UPDATE ... SET deleted_at WHERE path LIKE :path/%`

5. **`_create_version(obj, session)`** → `None`
   - Count existing versions, create snapshot at `version_path(obj.path, n+1)`

6. **`_update_content(obj, content)`** → `None`
   - Set content + recompute `content_hash`, `size_bytes`, `lines`, `updated_at` (validator only runs on `__init__`, not attribute mutation)

### Calling Convention Summary

The base class calls `_*_impl` in three patterns:
- **`_route_single` with path**: `impl(rel_path, session=s, **kwargs)` — path as 1st positional arg
- **`_dispatch_candidates`**: `impl(candidates=group_cands, session=s, **kwargs)` — candidates as keyword
- **`_route_fanout` without candidates**: `impl(session=s, **kwargs)` — no path, no candidates

All CRUD path/candidates impls handle this via their signature: `(self, path=None, candidates=None, *, session)`.

### CRUD Implementations (11 methods)

| Method | Kind-awareness | Notes |
|--------|---------------|-------|
| `_read_impl` | All kinds: return content (file/chunk/version), metadata (connection/dir) | Skips re-fetch for already-hydrated candidates |
| `_stat_impl` | Delegates to `_read_impl`, strips content from returned candidates | Thin wrapper, no separate DB query |
| `_write_impl` | Files and chunks (paths with `.chunks/` allowed). Auto-version on file overwrite | Calls `_ensure_parent_dirs`, `_create_version` for files |
| `_edit_impl` | Files/chunks only. Apply `EditOperation` list, auto-version | String replace with `replace_all` flag |
| `_ls_impl` | Dir → children. File → its metadata children (`.chunks/`, `.versions/`, `.connections/`) | `WHERE parent_path = :path` |
| `_delete_impl` | Cascade to metadata children. Soft-delete via `deleted_at` | Graph cleanup for connection rows |
| `_mkdir_impl` | Create directory object, idempotent. Force `kind="directory"` | `_ensure_parent_dirs` |
| `_move_impl` | Batch `TwoPathOperation`. Reparent children via SQL string replace | `UPDATE path = REPLACE(path, old, new)` for children |
| `_copy_impl` | Copy content only, no metadata children | New object at dest |
| `_mkconn_impl` | Create/update connection object + graph edge | Uses `connection_path()` from paths.py |
| `_tree_impl` | Recursive ls via `WHERE path LIKE :path/%` | Optional `max_depth` via slash counting |

### Search Implementations (5 methods)

| Method | Implementation |
|--------|---------------|
| `_glob_impl` | SQL LIKE pre-filter via `glob_to_sql_like()`, Python regex post-filter via `compile_glob()`. Uses `column.like(pattern, escape="\\")` — portable across dialects. Files/dirs only by default |
| `_lexical_search_impl` | SQL LIKE pre-filter (`WHERE content LIKE '%term%'` per token), then Python BM25 scoring (k1=1.5, b=0.75, doc length norm). Portable baseline — `PostgresFileSystem`/`MSSQLFileSystem` can override with native FTS later |
| `_grep_impl` | Calls `_lexical_search_impl` for DB pre-filter + BM25 ranking, then Python regex post-filter for line-by-line matching, line numbers in `Detail.metadata` |
| `_semantic_search_impl` | Stub → error "requires search provider" |
| `_vector_search_impl` | Stub → error "requires search provider" |

### Graph Implementations (16 methods)

All delegate to `self._graph`. Pattern for traversal (5 methods):

```python
async def _predecessors_impl(self, path=None, candidates=None, *, session):
    target = self._build_graph_input(path, candidates)
    return await self._graph.predecessors(target, session=session)
```

Helper `_build_graph_input(path, candidates)` constructs a `GroverResult` from either a path or existing candidates.

Subgraph (2) and centrality (9) follow the same delegation pattern with `candidates or GroverResult()`.

### patterns.py

Direct port of `src_old/grover/util/patterns.py` — 3 public functions:
- `glob_to_sql_like(pattern, base_path="/")` → `str | None`
- `compile_glob(pattern, base_path="/")` → `re.Pattern | None`
- `match_glob(path, pattern, base_path="/")` → `bool`

Only change: import `normalize_path` from `grover.paths` instead of `grover.util.paths`.

## Implementation Order

1. **`src/grover/patterns.py`** — port glob utilities (zero deps on new code)
2. **`src/grover/backends/__init__.py`** + **`database.py`** — internal helpers first, then CRUD, then search, then graph delegation
3. **`tests/test_database.py`** — write tests alongside each group

### Test groups (in order):
1. Write + Read (foundation — files and chunks via write)
2. Stat (delegates to read, strips content)
3. Ls + Mkdir + Tree (ls on file shows `.chunks/`, `.versions/`, `.connections/`)
4. Edit (depends on read + write + versioning)
5. Delete (cascade logic)
6. Auto-versioning (write overwrites create versions)
7. Move + Copy
8. Mkconn (connection creation + graph sync)
9. Glob + Grep + Lexical search
10. Graph delegation (add connections via mkconn, query via predecessors/successors/etc.)

### Test fixture:

```python
@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()

@pytest.fixture
async def db(engine):
    return DatabaseFileSystem(engine=engine)
```

## Deferred (out of scope)

- `PostgresFileSystem` / `MSSQLFileSystem` — dialect-specific subclasses with native FTS, regex GLOB, etc.
- Search providers (semantic/vector) — stub errors for now
- Analyzers / BackgroundWorker — no auto-chunking or auto-connection extraction
- Diff-based versioning — all versions are full snapshots
- LocalFileSystem — disk-backed subclass
- UserScopedFileSystem — multi-tenant wrapper
- CLI / MCP tool
- Embedding population
