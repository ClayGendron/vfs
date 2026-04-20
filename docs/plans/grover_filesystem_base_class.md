# Plan: GroverFileSystem — Concrete Base Class with Mount Routing

## Context

Converting `GroverFileSystem` from a Protocol to a **concrete async base class** that owns mount routing, session management, path rebasing, and `_grover` binding. The database is the default — SQL implementations live directly on `GroverFileSystem`. The filesystem object itself owns `/` — `add_mount("/")` is illegal.

**Class hierarchy:**
```
GroverFileSystem (concrete — routing + session + SQL ops, requires engine)
├── AsyncGrover(GroverFileSystem) — no engine, no storage, mount-only router
├── DatabaseFileSystem(GroverFileSystem) — empty subclass, real class
│   └── LocalFileSystem(DatabaseFileSystem) — overrides _*_impl for disk content
Grover — sync wrapper around AsyncGrover
```

## Core Constraints

### The filesystem IS the root

The object that owns a namespace IS its root. No mounting at `/`.

```python
g = AsyncGrover()                              # owns "/" (empty router)
g.add_mount("/jira", DatabaseFileSystem(...))  # /jira/* → DB
g.add_mount("/src", LocalFileSystem(...))      # /src/*  → disk

db = DatabaseFileSystem(...)                   # owns "/" (DB storage)
db.add_mount("/archive", DatabaseFileSystem(...))  # /archive/* → another DB
```

`add_mount()` enforces:
- Path must be absolute (starts with `/`)
- Path must not be `"/"`
- Path must be normalized (via `paths.py:normalize_path`)
- Exact path collision is forbidden
- Nested mounts are allowed (`/data` and `/data/archive` are valid)

### Constructor invariants

- **`GroverFileSystem(engine=...) / GroverFileSystem(session_factory=...)`** — requires one or the other. The base class owns SQL storage at its root. Not intended for direct instantiation — use `DatabaseFileSystem` instead.
- **`AsyncGrover()`** — takes no engine. Overrides `_use_session` to yield `None` (no-op — no commit, no rollback). All `_*_impl` methods accept `session=None` and return failure/empty. No special `_has_storage` branch needed in routing — the base flow works unchanged.
- **`DatabaseFileSystem(...)`** — inherits `GroverFileSystem.__init__`, passes through. This is the public name for a DB-backed filesystem.
- **`LocalFileSystem(root=..., engine=...)`** — inherits `DatabaseFileSystem.__init__`, adds disk root path. Engine defaults to SQLite at `root/.grover/grover.db`.

### Sessions never cross mounts

Each filesystem owns its own engine/session factory. When routing to a mount, the mount creates its own session. An externally provided `session` is only used when the terminal filesystem is `self`.

### `_grover` binding is caller-agnostic

Every public method stamps `result._grover = self` before returning. Chain stubs on `GroverResult` (line 328) call through to whatever `_grover` is — sync `Grover` returns `GroverResult`, async returns coroutine. Documented as intentional dual-mode. Enrichment chains (sort/top/filter/kinds) are always sync — they don't call `_grover`.

### Root discovery on mount-only routers

`AsyncGrover` has no storage, but it still owns `/` as a namespace root. To keep the namespace discoverable:

- `AsyncGrover.ls("/")` returns synthetic directory candidates for mounted roots
- `AsyncGrover.tree("/")` includes mounted roots as children
- Unmounted non-root paths on `AsyncGrover` still return `success=False`

This is the only synthetic namespace behavior in the base plan. Everything else routes to mounted filesystems or to the owner's local storage.

### No cross-mount connections — enforced at routing layer

Validation lives in the public routing methods, not the storage layer:
- **`mkedge()`** validates source and target resolve to the same terminal filesystem.
- **`write()`** checks if the path is a connection kind (via `parse_kind()`). If so, decomposes the connection path and validates source/target are same-mount.

If validation fails, returns `success=False`. The `_*_impl` layer does not validate mounts — it trusts its caller. This keeps the enforcement centralized in one place (the routing layer) rather than scattered across `_mkconn_impl`, `_write_impl`, and model validators.

### Glob is fnmatch, not SQL LIKE

Public `glob()` accepts shell-style patterns (`**/*.py`, `src/auth.*`). The `_glob_impl` translates to the backend's query language (SQL LIKE for DB, `fnmatch` for disk). This matches the design doc §5.1 and Unix convention.

For the SQL backend, glob matching is implemented as:

- coarse SQL prefilter to narrow candidate rows
- Python `fnmatch` post-filter for correctness

Plain SQL `LIKE` is not sufficient to implement full shell-style glob semantics by itself.

### `.apis` is out of scope for this phase

API endpoint paths and live pass-through mounts are intentionally deferred. This plan covers the core filesystem, mount routing, SQL storage, and local-disk overrides only.

## Routing

### `_match_mount(path)` — longest-prefix match

```python
def _match_mount(self, path: str) -> tuple[str, GroverFileSystem] | None:
    for mount_path in sorted(self._mounts, key=len, reverse=True):
        if path == mount_path or path.startswith(mount_path + "/"):
            return mount_path, self._mounts[mount_path]
    return None
```

No root-mount case — `"/"` is never in `_mounts`.

### `_resolve_terminal(path)` — iterative walk

```python
def _resolve_terminal(self, path: str) -> tuple[GroverFileSystem, str, str]:
    fs = self
    prefix = ""
    rel = normalize_path(path)
    while True:
        matched = fs._match_mount(rel)
        if matched is None:
            break
        mount_path, mount_fs = matched
        prefix = prefix + mount_path
        rel = rel[len(mount_path):] or "/"
        fs = mount_fs
    return fs, rel, prefix
```

No root-mount special case. `mount_path` is always a non-root absolute path like `"/jira"`, so `rel[len("/jira"):]` correctly strips the prefix.

| Layout | Input path | terminal | rel | prefix |
|---|---|---|---|---|
| `g.add_mount("/web", db)` | `/web/page.html` | db | `/page.html` | `/web` |
| `g.add_mount("/data", db)` + `db.add_mount("/archive", arc)` | `/data/archive/old.txt` | arc | `/old.txt` | `/data/archive` |
| `g.add_mount("/jira", db)` | `/src/a.py` | g (self) | `/src/a.py` | `""` |

### `_use_session()` — proper transaction manager

```python
@asynccontextmanager
async def _use_session(self, session: AsyncSession | None = None):
    if session is not None:
        yield session  # borrowed — caller owns lifecycle
    else:
        async with self._session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise
```

`AsyncGrover` overrides to yield `None` — a no-op context manager. No commit, no rollback, no raise. The `_*_impl` methods on `AsyncGrover` accept `session=None` and return failure/empty immediately. This means the base routing code works unchanged — no `_has_storage` branch needed. The flow for an unmounted path on `AsyncGrover` is:

```
read("/unmounted") → _resolve_terminal → terminal is self (AsyncGrover)
→ _use_session(None) → yields None
→ _read_impl("/unmounted", session=None) → GroverResult(success=False, "No mount for: /unmounted")
→ _rebase_result → stamp _grover → return
```

### `_rebase_result(result, prefix)`

```python
def _rebase_result(self, result: GroverResult, prefix: str) -> GroverResult:
    if not prefix:
        return result
    rebased = []
    for c in result.candidates:
        new_path = prefix + c.path if c.path != "/" else prefix
        rebased.append(c.model_copy(update={"path": new_path}))
    return result._with_candidates(rebased)
```

### Shadow prevention in fan-out

When self has storage AND child mounts, fan-out ops must exclude self-data under mount prefixes:

```python
def _mounted_prefixes(self) -> list[str]:
    return list(self._mounts.keys())

def _exclude_mounted_paths(self, result: GroverResult) -> GroverResult:
    prefixes = self._mounted_prefixes()
    if not prefixes:
        return result
    filtered = [
        c for c in result.candidates
        if not any(c.path == p or c.path.startswith(p + "/") for p in prefixes)
    ]
    return result._with_candidates(filtered)
```

### Two merge functions with different success semantics

**Fan-out merge** — for namespace ops (glob, grep, search, graph). One failing mount shouldn't invalidate results from others:

```python
def _merge_fanout(self, results: list[GroverResult]) -> GroverResult:
    if not results:
        return GroverResult(success=True, candidates=[])
    merged = results[0]
    for r in results[1:]:
        merged = merged | r
    return GroverResult(
        success=any(r.success for r in results),  # any success = overall success
        message=merged.message,
        candidates=merged.candidates,
    )
```

**Batch merge** — for candidate CRUD (read, delete, edit on result sets). Partial failure must be visible:

```python
def _merge_batch(self, results: list[GroverResult]) -> GroverResult:
    if not results:
        return GroverResult(success=True, candidates=[])
    merged = results[0]
    for r in results[1:]:
        merged = merged | r
    return GroverResult(
        success=all(r.success for r in results),  # all must succeed
        message=merged.message,
        candidates=merged.candidates,
    )
```

Note: individual candidate failures are tracked in `Detail.success` on each candidate, so even with `success=False` on the overall result, the caller can inspect which candidates succeeded.

## 4 Routing Patterns in Public Methods

### Case 1: Single-path ops (read, stat, write, edit, delete, mkdir, mkedge)

```python
async def read(self, path: str | None = None, candidates: GroverResult | None = None,
               *, session: AsyncSession | None = None) -> GroverResult:
    if candidates:
        return await self._dispatch_candidates("read", candidates, session=session)
    fs, rel, prefix = self._resolve_terminal(path)
    use_session = session if fs is self else None
    async with fs._use_session(use_session) as s:
        result = await fs._read_impl(rel, session=s)
    result = self._rebase_result(result, prefix)
    result._grover = self
    return result
```

### Case 2: Two-path ops (move, copy)

```python
async def copy(self, src: str, dest: str, *, session: AsyncSession | None = None) -> GroverResult:
    src_fs, src_rel, src_pfx = self._resolve_terminal(src)
    dst_fs, dst_rel, dst_pfx = self._resolve_terminal(dest)
    if src_fs is dst_fs:
        use_session = session if src_fs is self else None
        async with src_fs._use_session(use_session) as s:
            result = await src_fs._copy_impl(src_rel, dst_rel, session=s)
        result = self._rebase_result(result, dst_pfx)
    else:
        # Cross-mount: content-only transfer
        async with src_fs._use_session() as s1:
            src_result = await src_fs._read_impl(src_rel, session=s1)
        if not src_result.success:
            src_result._grover = self
            return src_result
        async with dst_fs._use_session() as s2:
            result = await dst_fs._write_impl(dst_rel, src_result.content or "", session=s2)
        result = self._rebase_result(result, dst_pfx)
    result._grover = self
    return result
```

### Case 3: Candidate ops (chained read, stat, edit, delete, ls)

```python
async def _dispatch_candidates(self, op: str, candidates: GroverResult,
                                *, session: AsyncSession | None = None, **kwargs) -> GroverResult:
    groups = self._group_by_terminal(candidates)
    results = []
    for fs, prefix, paths in groups:
        use_session = session if fs is self else None
        async with fs._use_session(use_session) as s:
            batch_impl = getattr(fs, f"_{op}_batch_impl")
            r = await batch_impl(paths, session=s, **kwargs)
        results.append(self._rebase_result(r, prefix))
    merged = self._merge_batch(results)  # batch CRUD: all must succeed
    merged._grover = self
    return merged
```

Grouping by `(id(fs), prefix)`:
```python
def _group_by_terminal(self, candidates: GroverResult) -> list[tuple[GroverFileSystem, str, list[str]]]:
    groups: dict[tuple[int, str], tuple[GroverFileSystem, list[str]]] = {}
    for c in candidates:
        fs, rel, prefix = self._resolve_terminal(c.path)
        key = (id(fs), prefix)
        if key not in groups:
            groups[key] = (fs, [])
        groups[key][1].append(rel)
    return [(fs, pfx, paths) for ((_id, pfx), (fs, paths)) in groups.items()]
```

### Case 4: Namespace ops (glob, grep, search, tree, graph)

```python
async def glob(self, pattern: str, candidates: GroverResult | None = None,
               *, session: AsyncSession | None = None) -> GroverResult:
    if candidates:
        return await self._dispatch_candidates("glob", candidates, session=session, pattern=pattern)
    results = []
    # Query self (with shadow filtering)
    async with self._use_session(session) as s:
        self_result = await self._glob_impl(pattern, session=s)
    results.append(self._exclude_mounted_paths(self_result))
    # Fan out to each mount
    for mount_path, mount_fs in self._mounts.items():
        r = await mount_fs.glob(pattern)
        results.append(self._rebase_result(r, prefix=mount_path))
    merged = self._merge_fanout(results)  # fan-out: any success = overall success
    merged._grover = self
    return merged
```

`AsyncGrover`'s `_glob_impl` returns empty result, so self-query contributes nothing — only mounts contribute.

## Override Points

**Single-path `_*_impl`** — core override point. Session is `None` for no-storage backends (AsyncGrover):
```python
async def _read_impl(self, path: str, *, session: AsyncSession | None) -> GroverResult: ...
```

**Batch `_*_batch_impl`** — defaults to loop, override for SQL `WHERE IN`:
```python
async def _read_batch_impl(self, paths: list[str], *, session: AsyncSession | None) -> GroverResult:
    results = [await self._read_impl(p, session=session) for p in paths]
    return self._merge_batch(results)
```

### LocalFileSystem reuse boundary

`LocalFileSystem` should not reuse `super()._write_impl()` for normal user files if that would also persist file bytes into `grover_objects.content`.

Instead, the base SQL implementation should be split into lower-level helpers for:

- metadata row creation/update
- version recording
- chunk/connection persistence
- directory bookkeeping

`LocalFileSystem` reuses those helpers while doing actual file-byte reads/writes against disk. Metadata-only paths (`.chunks`, `.versions`, `.connections`) can still delegate directly to the SQL implementation.

| _impl | GroverFileSystem (SQL) | AsyncGrover | LocalFileSystem |
|---|---|---|---|
| `_read_impl` | SELECT from grover_objects | `success=False` | disk for files, SQL for metadata paths |
| `_write_impl` | INSERT/UPDATE grover_objects | `success=False` | disk bytes + shared metadata/version helpers |
| `_delete_impl` | soft-delete (deleted_at) | `success=False` | unlink + shared metadata helpers |
| `_ls_impl` | SELECT WHERE parent_path | `success=False` | os.listdir + SQL metadata children |
| `_stat_impl` | SELECT (no content) | `success=False` | os.stat + SQL metadata fields |
| `_edit_impl` | string replace in content col | `success=False` | disk replace + shared metadata/version helpers |
| `_glob_impl` | fnmatch → SQL LIKE translation | empty result | os.walk + fnmatch |
| `_grep_impl` | SQL WHERE content LIKE/REGEXP | empty result | disk regex |
| `_move_impl` | UPDATE path | `success=False` | os.rename + shared metadata helpers |
| `_copy_impl` | INSERT (clone) | `success=False` | shutil.copy + shared metadata helpers |
| `_mkdir_impl` | INSERT kind=directory | `success=False` | os.makedirs + shared metadata helpers |
| `_mkconn_impl` | INSERT kind=connection | `success=False` | inherited |
| `_tree_impl` | recursive CTE | empty result | os.walk tree |
| `_semantic_search_impl` | vector search | empty result | inherited |
| `_vector_search_impl` | vector search | empty result | inherited |
| `_lexical_search_impl` | FTS query | empty result | inherited |
| graph ops | graph provider query | empty result | inherited |

### mkedge cross-mount validation

```python
async def mkedge(self, source: str, target: str, edge_type: str,
                 *, session: AsyncSession | None = None) -> GroverResult:
    src_fs, src_rel, src_pfx = self._resolve_terminal(source)
    tgt_fs, tgt_rel, tgt_pfx = self._resolve_terminal(target)
    if src_fs is not tgt_fs:
        result = GroverResult(success=False,
            message=f"Cross-mount connections not supported: {source} and {target} resolve to different filesystems")
        result._grover = self
        return result
    use_session = session if src_fs is self else None
    async with src_fs._use_session(use_session) as s:
        result = await src_fs._mkconn_impl(src_rel, tgt_rel, edge_type, session=s)
    result = self._rebase_result(result, src_pfx)
    result._grover = self
    return result
```

## Implementation Phases

### Phase 1: Routing infrastructure

Rewrite `src/grover/protocol.py` — Protocol → concrete base class.

**Contents:**
- `__init__(engine, session_factory)` — requires one
- `_mounts`, `add_mount()` (with validation: absolute, not "/", normalized, exact duplicate forbidden, nesting allowed), `remove_mount()`
- `_match_mount()`, `_resolve_terminal()`
- `_use_session()` — borrow or create with commit/rollback (overridden by AsyncGrover to yield None)
- synthetic root discovery helpers for `ls("/")` and `tree("/")` on `AsyncGrover`
- `_rebase_result()`, `_exclude_mounted_paths()`
- `_merge_fanout()` — any success = True (for namespace ops)
- `_merge_batch()` — all success = True (for candidate CRUD)
- `_group_by_terminal()`, `_dispatch_candidates()`
- All public methods (4 routing patterns) calling `_*_impl`
- Connection validation in `mkedge()` and `write()` — cross-mount check at routing layer
- All `_*_impl(path, *, session: AsyncSession | None)` and `_*_batch_impl` — raise `NotImplementedError`

### Phase 2: AsyncGrover + DatabaseFileSystem + Grover

Create `src/grover/client.py`:
- `AsyncGrover(GroverFileSystem)` — no engine, `_use_session` yields `None` (no-op), all `_*_impl` accept `session=None` and return failure/empty
- `DatabaseFileSystem(GroverFileSystem)` — `pass` (empty subclass)
- `Grover` — sync wrapper, event loop in daemon thread, `_run()` bridge

Update `src/grover/__init__.py` — exports.

### Phase 3: SQL implementations

Implement `_*_impl` and `_*_batch_impl` on `GroverFileSystem` using `GroverObject` from `models.py`.

Key: `_*_batch_impl` overrides default loop with single `WHERE path IN (...)` queries.

Graph and search `_impl` depend on providers (rustworkx, vector stores) — stubbed as empty results until providers are wired.

### Phase 4: Tests

**`tests/test_routing.py`** — routing with mock `_*_impl` overrides:
1. Single mount dispatch + prefix stripping + rebasing
2. Nested mounts (2+ levels) — iterative resolution
3. Longest prefix wins
4. `add_mount("/")` raises ValueError
5. `add_mount` validates: absolute, normalized, exact duplicate forbidden, nesting allowed
6. Unmounted path on AsyncGrover → `success=False`
7. Unmounted path on GroverFileSystem → local `_impl`
8. Session isolation: terminal creates own, borrowed reused when fs is self
9. Session commit on success, rollback on error
10. Fan-out: glob/grep queries all mounts + self, unions results
11. Shadow prevention: self-data under mount prefix excluded
12. Candidate grouping by `(fs_id, prefix)`, same FS at two points
13. Candidate session reuse when all resolve to self
14. Two-path same mount → fast path
15. Two-path cross mount → content transfer
16. mkedge cross-mount → `success=False`
17. `_grover` stamped on all results, points to outermost caller
18. Partial fan-out failure: one mount fails, merged result still `success=True`
19. Async `_grover` chaining: chain stub returns awaitable
20. `AsyncGrover.ls("/")` returns mounted roots as synthetic directories
21. `AsyncGrover.tree("/")` includes mounted roots

**`tests/test_sql.py`** — SQL implementations:
22. Write + read round-trip
23. Write + glob finds it (fnmatch pattern, SQL prefilter + Python post-filter)
24. Write + grep matches content
25. ls returns children (metadata hidden by default)
26. delete soft-deletes
27. mkedge creates connection with correct kind/source/target
28. Batch read `WHERE IN`
29. stat returns metadata without content

## Files

| File | Action | Phase |
|------|--------|-------|
| `src/grover/protocol.py` | **Rewrite** | 1, 3 |
| `src/grover/client.py` | **Create** | 2 |
| `src/grover/__init__.py` | **Modify** | 2 |
| `tests/test_routing.py` | **Create** | 4 |
| `tests/test_sql.py` | **Create** | 4 |

## Existing code to reuse

- `paths.py:normalize_path()` (line 157) — mount path normalization
- `paths.py:parse_kind()` (line 238) — LocalFileSystem dispatch
- `paths.py:edge_out_path()` (line 389) — mkedge path building
- `paths.py:decompose_edge()` (line 426) — connection parsing
- `results.py:GroverResult._with_candidates()` (line 259) — rebasing
- `results.py:GroverResult.__or__()` (line 227) — merging
- `results.py:GroverResult._grover` (line 134) — binding
- `models.py:GroverObject` — SQL table model

## Verification

1. `uv run pytest tests/test_routing.py` — routing tests pass
2. `uv run pytest tests/test_sql.py` — SQL tests pass
3. `uv run pytest` — all existing tests still pass
4. `uvx ruff check src/ tests/` — clean
5. `uvx ruff format --check src/ tests/` — clean
