# 016 — Namespace Primitives Cleanup

- **Status:** draft
- **Date:** 2026-05-02
- **Owner:** Clay Gendron
- **Kind:** refactor · namespace foundation
- **Depends on:** 015 (router calls public API, not impl)
- **Enables:** 017, 018, 019 (topology, bind, unions all rely on a clean
  routing invariant)

## Intent

Tidy the four soft spots in today's mount primitives so the rest of
the namespace work has a clean foundation to build on. None of these
are features — they are corrections to assumptions that no longer
hold once stories 015–019 land.

The four cleanups, all in one story because they share tests and
because doing them piecemeal invites drift:

1. **Allow nested mount paths.** Today
   `_normalize_mount_path` rejects anything with a slash inside it.
   Plan 9 has no such rule and our longest-prefix matcher already
   handles depth correctly. Drop the rejection.
2. **Structured `MountError` reasons.** Mount errors are
   strings today. Add a `MountErrorKind` enum so callers (Python,
   FSP, MCP) can branch on reason without parsing English.
3. **Bind-cycle / re-entry detection.** Once
   bind exists (story 018), `bind /a /b; bind /b /a` is a foot-gun.
   Detect cycles at resolution time using `(id(fs), rel)` identity
   so this story is independent of 018 — the guard is in place when
   bind ships.
4. **Push the "exclude mounted paths" filter from the router into
   the storage layer.** The router today post-filters self-storage
   results to drop paths under a child mount. That's defensive,
   covering a case Plan 9 makes structurally impossible: walk
   consults the mount table *before* dispatching. Move the
   exclusion into `DatabaseFileSystem._scope_filter_*` so SQL
   excludes mount-hole prefixes before rows leave the DB.

## Why

- **(1)** is gating real use cases (multi-tenant trees,
  `/data/2026-04-30` snapshot mounts, `/tenants/acme/{docs,code}`).
  The single-segment rule has no design rationale; it was probably
  a temporary safety. Removing it costs nothing.
- **(2)** is a precondition for FSP error mapping. The synthesis
  memo committed to semantic error classes and an
  `error.data.class` field; mount errors are the easiest place to
  start.
- **(3)** is a future-proofing move that lets us land 018 (bind)
  without simultaneously inventing cycle detection. Story 018
  becomes a one-day change instead of a two-week one.
- **(4)** is code-size diet. Defensive filters in the router are
  what you write when you don't trust the lower layer. The right
  fix is to make the lower layer trustworthy. After this story,
  the storage layer respects mount holes natively, and the
  router's defensive filter is removed.

## Scope

### In

1. **Loosen `_normalize_mount_path`.**
   ```python
   @staticmethod
   def _normalize_mount_path(path: str) -> str:
       if not path or path == "/":
           raise MountError(MountErrorKind.InvalidPath, path,
                            detail="must not be empty or root")
       norm = normalize_path(path)             # absolute, no '..', no '//'
       if norm == "/" or norm.endswith("/"):
           raise MountError(MountErrorKind.InvalidPath, path)
       return norm
   ```
   Tests: `add_mount("/tenants/acme/docs", fs)` succeeds; existing
   single-segment tests still pass; `add_mount("/", fs)` fails;
   `add_mount("/foo/", fs)` fails; `add_mount("/foo/../bar", fs)`
   normalizes to `/bar`.

2. **`MountError` and `MountErrorKind`.**
   ```python
   class MountErrorKind(StrEnum):
       AlreadyMounted          = "mount.already_exists"
       NotMounted              = "mount.not_found"
       InvalidPath             = "mount.invalid_path"
       InvalidUri              = "mount.invalid_uri"
       InvalidFlags            = "mount.invalid_flags"
       BindCycle               = "mount.bind_cycle"
       BindIntoSelf            = "mount.bind_into_self"
       UnionWithoutCreate      = "mount.union_no_create"
       CrossMountNotPermitted  = "mount.cross_mount_forbidden"

   class MountError(VFSError):
       def __init__(self, kind: MountErrorKind, path: str | None = None,
                    *, detail: str | None = None):
           ...
       def to_jsonrpc(self) -> dict:
           return {"code": -32000, "message": str(self),
                   "data": {"class": self.kind.value, "path": self.path}}
   ```
   Replace every `ValueError(...)` and `KeyError(...)` in the
   mount-management code paths (`add_mount`, `remove_mount`,
   `_normalize_mount_path`) with the corresponding
   `MountError(kind, ...)`.

3. **Cycle / re-entry detection in `_resolve_terminal`.**
   ```python
   def _resolve_terminal(self, path):
       fs = self
       rel = normalize_path(path)
       prefix = ""
       visited: set[tuple[int, str]] = set()
       while True:
           key = (id(fs), rel)
           if key in visited:
               raise MountError(MountErrorKind.BindCycle, path,
                                detail=f"cycle through {prefix}{rel}")
           visited.add(key)
           matched = fs._match_mount(rel)
           if matched is None:
               return fs, rel, prefix
           mount_path, mount_fs = matched
           fs = mount_fs
           prefix += mount_path
           rel = rel[len(mount_path):] or "/"
   ```
   No bind exists yet, so the guard is dormant on `main`. It
   activates the day 018 ships.

4. **Move "exclude mounted paths" into the storage layer.**
   Today's `_exclude_mounted_paths` (`base.py:1029`) post-filters
   `VFSResult.candidates`. Replace with a SQL-level scope
   filter that lives on `DatabaseFileSystem`:
   ```python
   def _scope_filter_mount_holes(self, q):
       holes = self._mount_holes_for_self()    # set[str]: child roots
       if not holes:
           return q
       return q.where(sa.and_(*[
           sa.not_(VFSEntry.path.like(f"{h}/%"))
           for h in holes
       ]))
   ```
   The router exposes `_mount_holes_for_self()` so the backend
   knows which prefixes to exclude. The post-filter
   `_exclude_mounted_paths` stays for one release as a
   belt-and-suspenders defense, then comes out in a follow-up.

### Out

- Adding `bind()` (story 018).
- Union mount flags (story 019).
- Topology resource (story 017).
- Removing `_*_impl` (already happened in 015).
- Engine-disposal-on-unmount (already removed by 015).

## Acceptance Criteria

1. **Nested mount paths work.** `add_mount("/tenants/acme/docs", fs)`
   succeeds; `read("/tenants/acme/docs/x.md")` resolves to `fs`'s
   `read("/x.md")`. Tests cover three- and four-level mounts.

2. **`MountError` is the only exception type from mount management.**
   Grep over `src/vfs/base.py` confirms `add_mount`, `remove_mount`,
   `_normalize_mount_path`, and any future bind path raise
   `MountError`, not `ValueError` / `KeyError` / `RuntimeError`.

3. **`MountError.to_jsonrpc()` has stable JSON shape.**
   Snapshot test asserts `{"code": -32000, "message": "...",
   "data": {"class": "mount.invalid_path", "path": "/"}}` for the
   four primary error kinds.

4. **Bind cycle detection is in place.** A unit test that injects
   a deliberately cyclic `_mounts` dict and calls `_resolve_terminal`
   returns `MountError(BindCycle)` instead of recursing
   indefinitely.

5. **SQL scope filter excludes mount holes.** A glob from a router
   that has `/data` mounted on a `DatabaseFileSystem` and
   `/data/archive` mounted as a separate filesystem returns no
   `/data/archive/*` rows from the parent backend.

6. **The post-filter still passes.** `_exclude_mounted_paths`
   stays for one release; tests confirm it is a no-op
   (filters zero rows because the SQL already excluded them).

7. **No public API additions.** No new methods on
   `VirtualFileSystem`, `VFSClient`, or `VFSClientAsync`.
   `MountError` and `MountErrorKind` are the only new symbols.

## Risks

- **Existing callers may catch `ValueError`/`KeyError`.** Migration
  note in changelog: catch `MountError` (a `VFSError` subclass).
  `MountError` continues to inherit from `VFSError`, so `except
  VFSError` keeps working.
- **Nested mounts may surface latent path-handling bugs.**
  Run the existing fanout tests at `/a/b/c/...` depth to catch
  any place that assumed single-segment mount paths.
- **Backend scope filter is a SQL-level invariant.** A backend
  that doesn't implement it (a future memory-FS) needs a Python
  fallback. Provide a default impl on `DatabaseFileSystem` that
  works for any subclass; document the expectation.

## Open Questions

1. **Should we delete `_exclude_mounted_paths` immediately** rather
   than keeping it for one release as a fallback? Default: keep
   for one release; remove in story 020 cleanup.

2. **Does `MountError` belong in `vfs.exceptions` or in a new
   `vfs.mount` module?** Default: `vfs.exceptions`, keep with
   the rest of the error class hierarchy.

3. **Should `_resolve_terminal` cap the `visited` set size** to
   guard against pathological mount tables? Default: no, bind
   cycles are the only realistic source.

## References

- `src/vfs/base.py:89` — `_normalize_mount_path` (the rejection)
- `src/vfs/base.py:104` / `:117` — `add_mount` / `remove_mount`
- `src/vfs/base.py:150` — `_resolve_terminal` (gets the cycle guard)
- `src/vfs/base.py:1029` — `_exclude_mounted_paths` (the filter to push down)
- `src/vfs/exceptions.py` — current `MountError` (string-only)
- `docs/plan9-mount-namespace-recommendations.html` — Recs 01, 08, 09, 10
