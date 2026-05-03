# 018 — bind() and BindFS: cheap aliases

- **Status:** draft
- **Date:** 2026-05-02
- **Owner:** Clay Gendron
- **Kind:** feature · namespace
- **Depends on:** 015, 016, 017
- **Enables:** 023 (per-session bind is the primary use)

## Intent

Add `bind(source, target, *, flags)` to the public API. A bind
makes the namespace at `source` also visible at `target` without
copying any data. Implementation is a tiny `BindFS` filesystem
that forwards every operation to a path inside an upstream
filesystem.

After this story:

```python
await client.bind("/tenants/acme/docs", "/docs")          # short alias
await client.bind("/tenants/acme/docs/.versions/v42", "/dump")  # snapshot
await client.bind("/shared/glossary", "/refs")            # cross-tree alias
```

## Why

- **Short paths matter for agents.** Long canonical paths
  (`/tenants/acme/docs/...`) make agent prompts noisy. A
  per-session bind to `/docs` is the cleanest fix.
- **Snapshots and dumps.** `.versions/<v>/` paths are exact
  qid-version-frozen views. Binding one of them at
  `/dump` lets agents browse a snapshot using their normal
  read/grep/search vocabulary.
- **No data movement.** Aliasing should never trigger a copy.
  Plan 9's bind is the canonical answer; we're copying it.
- **Composability.** Bind composes with unions (story 019)
  and with per-session namespaces (story 023). Without bind,
  both of those stories lose their primary ergonomic story.

## Scope

### In

1. **`BindFS(VirtualFileSystem)`.**
   Forwards every public method to the upstream filesystem with
   the source path prefixed:
   ```python
   class BindFS(VirtualFileSystem):
       def __init__(self, upstream: VirtualFileSystem, source: str):
           super().__init__(storage=False)
           self._upstream = upstream
           self._source = normalize_path(source)

       def uri(self) -> str:
           return f"bind://{quote(self._source)}"

       async def read(self, path=None, *, candidates=None,
                      user_id=None) -> VFSResult:
           if path is not None:
               path = self._source.rstrip("/") + path
           # candidates: rebase paths inside source before forwarding
           result = await self._upstream.read(
               path, candidates=self._rebase_in(candidates),
               user_id=user_id,
           )
           return result.strip_prefix(self._source)
       # ... write, stat, glob, grep, delete, edit, mkdir, mkedge,
       #     copy, move, search, query
   ```
   Path rebasing on input (mount-relative → upstream-relative)
   and on output (upstream-relative → mount-relative). Both
   directions tested.

2. **Public `bind()` API on `VirtualFileSystem`.**
   ```python
   async def bind(self, source: str, target: str, *,
                  flags: MountFlag = MountFlag.REPL,
                  permissions: PermissionMap | None = None) -> None:
       src = normalize_path(source)
       tgt = self._normalize_mount_path(target)
       if tgt == src or tgt.startswith(src + "/"):
           raise MountError(MountErrorKind.BindIntoSelf, target,
                            detail=f"target {tgt!r} is inside source {src!r}")
       fs = BindFS(self, src)
       await self.add_mount(tgt, fs, flags=flags, permissions=permissions)
   ```
   Same flow as `add_mount` (which itself routes through
   `/.mounts/ctl` after story 017). Bind cycles caught at
   resolution time by the guard from story 016.

3. **Ctl `bind` verb activates.**
   Story 017 stubbed the bind verb. This story implements it:
   ```text
   bind <source> <target> [flags=<flags>] [perms=<perms>]
   ```

4. **`/.mounts/<encoded>/backend` shows the bind.**
   `MountInfo.backend_uri` is `bind:///path/inside/source` for
   bound mounts. Agents can tell binds from real backends by
   the URI scheme.

5. **Permission inheritance.**
   By default a bind inherits the upstream's permission map for
   the source subtree. Caller can override with the
   `permissions=` kwarg — useful for "expose this writable
   subtree as read-only at this alias."

6. **No materialization.**
   Bind doesn't read, write, or copy any data at registration
   time. A test asserts that binding a 10M-row backend completes
   in O(1) time.

### Out

- Cross-router binds (binding a path from a different
  `VFSClient`). Not in scope; binds are local to one router.
- Recursive bind (binding `/a` to `/b` while `/a` itself
  contains binds). Should work via the cycle guard but not a
  story focus.
- Bind to a nonexistent source. Bind succeeds; reads from the
  alias get `NotFoundError`. Same as Plan 9.
- Auto-rebase of `.versions/` etc. inside the bind. The
  upstream filesystem handles those paths natively; the bind
  just forwards.

## Acceptance Criteria

1. **`bind(src, tgt)` succeeds.** Subsequent `read(tgt + ...)`
   returns the same data as `read(src + ...)` byte-for-byte.

2. **`stat` consistency.** `stat("/dump/x.md")` returns the same
   `Detail` as `stat("/tenants/acme/docs/x.md")` except for `path`
   (rebased to the alias).

3. **`glob("/docs/**")` returns rebased paths.** Every candidate
   has `path` starting with `/docs/`, never with the source.

4. **`grep` works through binds.** Pattern hits inside the
   upstream's content are returned with rebased paths and
   correct line numbers.

5. **Search works through binds.** `search(query=..., paths=("/docs/",))`
   reaches the upstream backend and returns paths rebased to
   `/docs/`.

6. **Write through a bind writes to the upstream.** `write("/docs/foo.md",
   "hi")` creates `/tenants/acme/docs/foo.md` in the upstream
   backend. A second client reading the upstream sees the write.

7. **Bind cycle guard fires.** `bind("/a", "/b"); bind("/b", "/a")`
   succeeds at registration but `read("/a/x")` raises
   `MountError(BindCycle)`.

8. **Bind-into-self refused.** `bind("/a", "/a/b")` raises
   `MountError(BindIntoSelf)` at registration.

9. **`MountInfo.backend_uri` shows the bind.**
   `read("/.mounts/<encoded>/backend")` returns
   `bind:///tenants/acme/docs`.

10. **Permission override works.**
    `bind("/scratch", "/snap", permissions=read_only())` makes
    `/snap` reject writes but `/scratch` continues to accept them.

11. **No materialization.** A bind of a 10M-row backend completes
    in <100ms (constant time, not proportional to row count).

12. **Compose with other binds.** `bind("/a/b", "/c"); bind("/c",
    "/d")` — `read("/d/x")` ultimately resolves through the chain
    and finds `x` under `/a/b/`.

## Risks

- **Path-rebasing math is fiddly.** Off-by-one with leading slashes
  is the classic bug. Property-based tests with random `(source,
  target, sub)` triples catch most.
- **Edit/copy/move through binds.** These touch two paths; both
  need rebasing. Cross-mount edit between two binds in the same
  router is the trickiest case — defer to upstream backends.
- **Result rebasing across `Detail` chains.** A multi-step
  `VFSResult` (e.g., from a query that crossed multiple
  operations) carries `Detail` provenance with paths. `BindFS`
  rebases the candidate `path` but must also rebase any path-
  shaped fields inside `Detail`. Audit `results.py`.

## Open Questions

1. **Should `bind` be reversible — a way to enumerate "where is
   /docs really?"** Default: yes, via `MountInfo.backend_uri`
   which carries the source path. No new API needed.

2. **Should `bind` preserve `index_content` and other
   write-pipeline metadata?** Default: it's a forward, not a
   transform. Anything that matters at write time is set by the
   caller and the upstream sees it as-is.

3. **What does `bind("/", target)` mean — bind the whole
   namespace?** Default: refuse with `MountError(InvalidPath)`.
   Whole-namespace aliases are too easy to misuse.

## References

- `src/vfs/base.py:104` — `add_mount` (target of `bind`)
- `src/vfs/base.py:150` — `_resolve_terminal` (carries the cycle guard)
- `src/vfs/results.py` — `Detail`, `Candidate` (path rebasing surface)
- Plan 9 `bind(2)` — manual page, defines BEFORE / AFTER / REPL / CREATE
- `docs/plan9-mount-namespace-recommendations.html` — Rec 06
