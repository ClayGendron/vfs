# Reducing Delegation Boilerplate

Grover's layered architecture — Facade → Filesystem → Provider — is intentional. The `g.pagerank()` API with automatic mount routing is the product. But maintaining that API currently requires touching 4-6 files per new method, and ~1,400 lines of the codebase are pure mechanical forwarding.

This plan eliminates the boilerplate while preserving the exact same public API.

## Principles

- **No public API changes.** `g.write()`, `g.pagerank()`, `g.glob()` all keep working identically.
- **Each phase is independently shippable.** If we stop after any phase, the codebase is better than before.
- **Tests must pass after every phase.** No "WIP" commits.
- **No new dependencies.** All solutions use standard Python (decorators, descriptors, `__getattr__`).

---

## Phase 1: Auto-Generate the Sync Wrapper

**Goal:** Replace ~600 lines of hand-written `_run()` stubs in `Grover` with automatic generation.

**Current state:** Every public method on `Grover` looks like:

```python
def method(self, *args, **kwargs) -> ReturnType:
    return self._run(self._async.method(*args, **kwargs))
```

45+ methods, each 2-10 lines (more for methods with many parameters that are spelled out explicitly). Total ~600 lines.

**Approach:** Use `__getattr__` on `Grover` to dynamically wrap any `GroverAsync` method:

```python
class Grover:
    _SYNC_METHODS = frozenset({
        "read", "write", "edit", "delete", "list_dir", "exists",
        "glob", "grep", "pagerank", ...
    })

    def __getattr__(self, name: str):
        if name in self._SYNC_METHODS:
            async_method = getattr(self._async, name)
            @functools.wraps(async_method)
            def wrapper(*args, **kwargs):
                return self._run(async_method(*args, **kwargs))
            return wrapper
        raise AttributeError(name)
```

Keep `__init__`, `close()`, and `_run()` as explicit methods. Everything else is generated.

**Alternative:** If `__getattr__` hurts IDE autocompletion too much, use a class decorator that generates the methods at class definition time and attaches proper type stubs. Or maintain a `.pyi` stub file for the `Grover` class.

**Files changed:**
- `src/grover/client.py` — rewrite `Grover` class (shrink from ~625 to ~50 lines)

**Testing:**
- All existing tests that use `Grover` (sync) continue to pass unchanged
- Add a test that verifies every public method on `GroverAsync` has a corresponding sync method on `Grover`

**Lines saved:** ~550-575

---

## Phase 2: Graph Delegate Factory

**Goal:** Replace 19 hand-written graph delegation stubs in `GraphOpsMixin` with a factory function.

**Current state:** Every graph query method follows one of two patterns:

```python
# Pattern A: path-based resolve (traversal — predecessors, successors, etc.)
async def method(self, path, ...) -> FileSearchResult:
    gp, mount = self._ctx.resolve_graph_with_mount(path)
    async with self._ctx.session_for(mount) as sess:
        return await gp.method(path, ..., session=sess)

# Pattern B: any-mount resolve (centrality — pagerank, betweenness, etc.)
async def method(self, *, path=None, candidates=None, ...) -> FileSearchResult:
    gp, mount = self._ctx.resolve_graph_any_with_mount(path)
    async with self._ctx.session_for(mount) as sess:
        return await gp.method(candidates, ..., session=sess)
```

19 methods, ~200 lines, all following these two templates.

**Approach:** A descriptor or factory function:

```python
def _graph_op(provider_method: str, *, resolve: str = "path"):
    """Create a facade method that delegates to GraphProvider."""
    async def delegate(self, *args, **kwargs):
        path = kwargs.pop("path", args[0] if args and resolve == "path" else None)
        if resolve == "path":
            gp, mount = self._ctx.resolve_graph_with_mount(path)
        else:
            gp, mount = self._ctx.resolve_graph_any_with_mount(path)
        async with self._ctx.session_for(mount) as sess:
            return await getattr(gp, provider_method)(*args, session=sess, **kwargs)
    return delegate
```

Then:

```python
class GraphOpsMixin:
    predecessors = _graph_op("predecessors", resolve="path")
    successors = _graph_op("successors", resolve="path")
    pagerank = _graph_op("pagerank", resolve="any")
    betweenness_centrality = _graph_op("betweenness_centrality", resolve="any")
    # ... etc — 1 line per method
```

Connection methods (`add_connection`, `delete_connection`) keep their explicit implementations since they have write validation + worker scheduling logic.

**Files changed:**
- `src/grover/api/graph_ops.py` — replace 19 stubs with factory + declarations

**Testing:**
- All existing graph tests pass unchanged
- Add a test that verifies all `GraphProvider` query methods are exposed on `GroverAsync`

**Lines saved:** ~150-170

---

## Phase 3: Multi-Mount Iteration Helper

**Goal:** Extract the repeated "if root iterate all mounts, else resolve single mount" pattern into a reusable helper.

**Current state:** 6+ methods in `SearchOpsMixin` and `FileOpsMixin` duplicate this pattern:

```python
if path == "/":
    combined = FileSearchResult(...)
    for mount in self._ctx.registry.list_visible_mounts():
        result = await mount.filesystem.method(...)
        combined = combined | result.rebase(mount.path)
    return combined
else:
    mount, rel_path = self._ctx.registry.resolve(path)
    result = await mount.filesystem.method(rel_path, ...)
    return result.rebase(mount.path)
```

Appears in: `glob`, `grep`, `vector_search`, `lexical_search`, `tree`, `list_trash`, `empty_trash`, `list_dir` (partially).

**Approach:** Add a helper to `GroverContext`:

```python
async def across_mounts(
    self,
    path: str,
    method: str,
    *args,
    combine: Callable = operator.or_,
    filter_mount: Callable[[Mount], bool] | None = None,
    **kwargs,
) -> FileSearchResult:
    """Route to one mount or iterate all visible mounts at root."""
    ...
```

Then search methods become:

```python
async def glob(self, pattern, path="/", ...) -> FileSearchResult:
    return await self._ctx.across_mounts(
        path, "glob", pattern, **kwargs
    )
```

Methods with special pre/post logic (like `grep` with `count_only`) keep their explicit code but use the helper for the mount iteration portion.

**Files changed:**
- `src/grover/api/context.py` — add `across_mounts()` helper
- `src/grover/api/search_ops.py` — simplify 4-5 methods
- `src/grover/api/file_ops.py` — simplify `tree`, `list_trash`, `empty_trash`

**Testing:**
- All existing search and file operation tests pass unchanged
- Add a test for `across_mounts` with multiple mounts

**Lines saved:** ~100-120

---

## Phase 4: Provider Delegate Factory for DatabaseFileSystem

**Goal:** Replace ~20 pass-through methods in `DatabaseFileSystem` that just forward to a sub-provider.

**Current state:** Chunk, version, and storage methods are pure delegation:

```python
async def replace_file_chunks(self, path, chunks, *, session=None):
    return await self.chunk_provider.replace_file_chunks(path, chunks, session=session)

async def delete_file_chunks(self, path, *, session=None):
    return await self.chunk_provider.delete_file_chunks(path, session=session)
```

~20 methods like this, each 2-5 lines.

**Approach:** Same factory pattern:

```python
def _delegate_to(provider_attr: str, method_name: str):
    """Create an async method that forwards to a provider."""
    async def delegate(self, *args, **kwargs):
        provider = getattr(self, provider_attr)
        return await getattr(provider, method_name)(*args, **kwargs)
    delegate.__name__ = method_name
    return delegate
```

Then:

```python
class DatabaseFileSystem:
    # Chunk provider delegation
    replace_file_chunks = _delegate_to("chunk_provider", "replace_file_chunks")
    delete_file_chunks = _delegate_to("chunk_provider", "delete_file_chunks")
    list_file_chunks = _delegate_to("chunk_provider", "list_file_chunks")
    write_chunk = _delegate_to("chunk_provider", "write_chunk")
    write_chunks = _delegate_to("chunk_provider", "write_chunks")

    # Version provider delegation
    list_versions = _delegate_to("version_provider", "list_versions")
    get_version_content = _delegate_to("version_provider", "get_version_content")
    # ... etc
```

Methods that add logic beyond delegation (e.g., `restore_version` which reads then writes) stay explicit.

**Files changed:**
- `src/grover/backends/database.py` — replace ~20 pass-throughs with factory declarations

**Testing:**
- All existing filesystem tests pass unchanged

**Lines saved:** ~100-150

---

## Phase 5: UserScopedFileSystem Proxy Pattern

**Goal:** Replace 19 near-identical method overrides with a centralized scoping wrapper.

**Current state:** Every override follows:

```python
async def method(self, path, *, user_id=None, session=None, **kwargs):
    self._require_user_id(user_id)
    resolved = self._resolve_path(path, user_id)
    await self._check_share_access(resolved, user_id, session)
    result = await super().method(resolved, session=session, **kwargs)
    return self._restore_path(result, path)
```

19 methods, ~700 lines total, same structure everywhere.

**Approach:** A `_scoped_call` helper + `__getattr__` or explicit thin wrappers:

```python
async def _scoped_call(self, method_name, path, *, user_id, session, **kwargs):
    """Resolve path, check access, delegate to super, restore path."""
    self._require_user_id(user_id)
    resolved = self._resolve_path(path, user_id)
    await self._check_share_access(resolved, user_id, session)
    method = getattr(super(), method_name)
    result = await method(resolved, session=session, **kwargs)
    return self._restore_path(result, path)
```

Methods with special behavior (e.g., `list_dir` handling `/@shared`, `move` updating share paths) keep explicit implementations. The ~12 methods that are pure resolve→delegate→restore use the helper.

**This is the highest-risk phase** because `UserScopedFileSystem` has subtle path manipulation and permission logic. Each method override may have edge cases that aren't immediately obvious.

**Files changed:**
- `src/grover/backends/user_scoped.py` — add `_scoped_call`, simplify ~12 methods

**Testing:**
- All existing user-scoped and sharing tests pass unchanged
- Add a parametrized test that verifies all scoped methods reject missing `user_id`
- Add a test that verifies path restoration works for each method

**Lines saved:** ~250-300

---

## Phase Summary

| Phase | Target | Lines Saved | Risk | Dependency |
|-------|--------|------------|------|------------|
| 1 | Sync wrapper auto-generation | ~550 | Low | None |
| 2 | Graph delegate factory | ~160 | Low | None |
| 3 | Multi-mount iteration helper | ~110 | Low | None |
| 4 | Provider delegate factory | ~125 | Low | None |
| 5 | UserScoped proxy pattern | ~275 | Medium | None |
| **Total** | | **~1,220** | | |

Phases 1-4 are independent and can be done in any order. Phase 5 is independent but riskier so it goes last.

### Type Stub Consideration

Phases 1, 2, and 4 use dynamic method generation which can hurt IDE autocompletion and type checking. Two options:

- **Option A:** Maintain `.pyi` stub files with explicit signatures. Adds a maintenance surface but gives full IDE support.
- **Option B:** Use class decorators that generate methods at import time (not runtime `__getattr__`). Tools like `ty` and `pyright` can sometimes follow these. Slightly more code but better static analysis.

The choice depends on how important IDE autocompletion is for Grover's users. If Grover is primarily consumed by AI agents (which don't need autocomplete), Option A with minimal stubs is fine. If human developers use it directly, Option B is worth the extra complexity.
