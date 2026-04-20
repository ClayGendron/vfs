# Filesystem Internals

This page focuses on the current filesystem mechanics in `src/vfs`: mount routing, metadata paths, session ownership, and write ordering.

## Mount Resolution

`VirtualFileSystem` routes every public operation by longest-prefix mount match:

1. normalize the caller path
2. walk mounts until the terminal filesystem is found
3. strip the accumulated mount prefix before delegating
4. rebase returned paths back to caller-visible absolute paths

Mount points are single segments such as `/workspace` or `/docs`. The root router always owns `/`, so mounting at `/` is rejected.

## Session Ownership

SQL sessions are injected by the router:

- mounted filesystems receive a session for one routed operation
- backends never create or own long-lived sessions
- backends `flush()` mutations when they need transactional visibility
- the router commits on success and rolls back on error

This matters because `DatabaseFileSystem` is designed to stay mostly stateless. Its durable state lives in the database and its transient state lives in the per-operation session.

## Storage Layout

`DatabaseFileSystem` persists everything in `vfs_objects`. The object kind is inferred from the path itself.

Examples:

```text
/workspace/auth.py
/workspace/notes/
/.vfs/workspace/auth.py/__meta__/chunks/login
/.vfs/workspace/auth.py/__meta__/versions/3
/.vfs/workspace/auth.py/__meta__/edges/out/imports/workspace/utils.py
```

This single-table model keeps CRUD, metadata inspection, and graph persistence aligned around one identity scheme.

## Write Ordering

Mutations intentionally use content-before-commit ordering:

1. stage version metadata in the session
2. write the new content or metadata row
3. flush the session
4. commit when the router exits the session context

If the write fails before commit, the router rolls back and the version record disappears with it. That is preferable to commit-first behavior, which can leave visible metadata pointing at content that was never written.

## Edges

`mkedge(source, target, edge_type)` writes a canonical outgoing edge path under:

```text
/.vfs/<source>/__meta__/edges/out/<edge_type>/<target>
```

Because edges are just persisted paths, they can be listed, inspected, and deleted through the normal filesystem operations:

```python
g.mkedge("/src/auth.py", "/src/utils.py", "imports")
g.ls("/.vfs/src/auth.py/__meta__/edges/out")
g.delete("/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py")
```

The in-memory graph is then projected from those persisted rows.

## Search Execution

`DatabaseFileSystem` uses a hybrid strategy:

- SQL prefilters narrow candidate rows cheaply
- Python remains the authoritative matcher and scorer where needed

That keeps the baseline backend portable across SQLite, Postgres, and SQL Server. Native backends then override the hot paths:

- `PostgresFileSystem` pushes grep, glob, lexical search, and pgvector search into Postgres
- `MSSQLFileSystem` pushes grep, glob, and full-text work into SQL Server

## Result Rebasing

When a routed operation returns rows from a mounted filesystem, the router rewrites them back to absolute caller-visible paths before returning the `VFSResult`.

That is why mounted backends can store and query relative paths internally while callers always see `/mount/...` paths.

## User Scoping

When `user_scoped=True`, storage paths are rewritten through `scope_path()` and validated with `validate_user_id()`:

- caller path: `/notes/today.md`
- stored path for `user_id="alice"`: `/alice/notes/today.md`

Returned entries are unscoped again before they leave the mounted filesystem, so callers do not need to know the storage prefixing rules.

## Failure Model

The two clients differ on normal failures:

- `VFSClientAsync` returns `VFSResult(success=False, errors=[...])`
- `VFSClient` raises the corresponding `VFSError` subclass

The backend behavior is the same underneath; only the facade changes how failures surface to the caller.
