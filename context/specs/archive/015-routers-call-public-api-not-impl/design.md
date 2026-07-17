# Design: public API across mount boundaries

This is the concrete implementation design for [spec.md](./spec.md). The
architectural rule is:

```text
Across a mount boundary: public API only.
Inside one filesystem's own storage: private impl is allowed.
```

The point is to make a mounted `DatabaseFileSystem` and a mounted MCP server
look identical to the parent router. The parent passes values and receives
`VFSResult`. It never sees a SQLAlchemy session, engine, MCP transport, or
`_*_impl`.

## The key correction

`VirtualFileSystem` is currently both:

- the router base class, and
- the storage-backend base class.

So "base.py never calls `_impl`" is too strong. A direct call like
`dbfs.read("/x")` must eventually reach `dbfs._read_impl(...)`; otherwise
`read -> _route_single -> read -> ...` recurses forever.

The correct rule is narrower and stronger:

```text
No filesystem calls another filesystem's private implementation.
```

That means every route helper must branch on `fs is self`.

## Local helper

Add one explicit local self-storage helper in `VirtualFileSystem`:

```python
async def _call_local_impl(
    self,
    op: str,
    *,
    user_id: str | None = None,
    **kwargs: object,
) -> VFSResult:
    if not self._storage:
        return self._error(f"No storage backend for operation: {op}")
    async with self._use_session() as session:
        impl = getattr(self, f"_{op}_impl")
        return await impl(user_id=user_id, session=session, **kwargs)
```

This helper is intentionally local. It is valid only for `self`, never for a
child mount. A remote mount adapter simply overrides public methods and never
uses `_call_local_impl`.

## Single-path dispatch

Current shape:

```python
async with fs._use_session() as s:
    result = await getattr(fs, f"_{op}_impl")(
        path=rel,
        user_id=user_id,
        session=s,
        **kwargs,
    )
```

Target shape:

```python
if fs is self:
    result = await self._call_local_impl(
        op,
        path=rel,
        user_id=user_id,
        **kwargs,
    )
else:
    method = getattr(fs, op)
    result = await method(
        path=rel,
        user_id=user_id,
        **kwargs,
    )
return result.add_prefix(prefix)
```

The parent router still owns path resolution, permission checks, and prefix
rebasing. The terminal filesystem owns its own transaction.

## MCP target shape

The public VFS operation shape should be mechanically translatable to MCP:

```python
# Python public method call
await fs.read(path="/docs/a.md", columns=frozenset({"path", "content"}))

# MCP tools/call equivalent
await session.call_tool(
    "vfs.read",
    {
        "path": "/docs/a.md",
        "columns": ["path", "content"],
    },
)
```

The local call is still a Python method for speed. The MCP shape is the
cross-process version of the same call, not an in-process abstraction tax.

VFS results should have conversion helpers at the adapter boundary:

```python
class VFSResult(BaseModel):
    ...

    def to_mcp_tool_result(self) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text=self.to_str())],
            structured_content={
                "operation": self.function,
                "items": [c.model_dump(mode="json", exclude_none=True)
                          for c in self.candidates],
                "errors": self.errors,
            },
            is_error=not self.success,
            meta={
                "vfs/resultVersion": 1,
                "vfs/itemCount": len(self.candidates),
            },
        )

    @classmethod
    def from_mcp_tool_result(cls, result: CallToolResult) -> VFSResult:
        data = result.structured_content or {}
        return cls(
            function=data.get("operation", ""),
            candidates=[Candidate.model_validate(i) for i in data.get("items", [])],
            errors=[str(e) for e in data.get("errors", [])],
            success=not result.is_error,
        )
```

Do not make route code depend on MCP SDK classes directly. Keep the SDK at the
adapter edge so local VFS operations remain lightweight and testable.

## Candidate dispatch

Candidate operations already group by terminal filesystem. The grouped dispatch
should use the same `fs is self` branch:

```python
if fs is self:
    result = await self._call_local_impl(
        op,
        candidates=group_cands,
        user_id=user_id,
        **kwargs,
    )
else:
    result = await getattr(fs, op)(
        candidates=group_cands,
        user_id=user_id,
        **kwargs,
    )
return result.add_prefix(prefix)
```

This preserves batched reads/stats/deletes/searches per mount. It also gives a
remote mount a wire-shaped batch call instead of many per-path calls.

## Batch writes

`write(entries=[...])` is already the right API for a batch. Keep it that way:

```python
if fs is self:
    result = await self._call_local_impl(
        "write",
        entries=group_entries,
        overwrite=overwrite,
        user_id=user_id,
    )
else:
    result = await fs.write(
        entries=group_entries,
        overwrite=overwrite,
        user_id=user_id,
    )
return result.add_prefix(prefix)
```

This keeps one transaction per terminal backend for a write batch. It is also
the shape an MCP mount can implement as a single tool call.

## Two-path operations

Same-mount `move` / `copy`:

```python
if src_fs is self:
    result = await self._call_local_impl(
        op,
        ops=batch,
        overwrite=overwrite,
        user_id=user_id,
    )
else:
    result = await getattr(src_fs, op)(
        moves=batch if op == "move" else None,
        copies=batch if op == "copy" else None,
        overwrite=overwrite,
        user_id=user_id,
    )
```

Cross-mount transfer should stay batched:

```python
read_candidates = VFSResult(
    function="read",
    candidates=[Candidate(path=p) for p in src_rels],
)
read_result = await src_fs.read(candidates=read_candidates, user_id=user_id)

entries = [
    VFSEntry(path=dst_rel, content=candidate.content or "")
    for dst_rel, candidate in zip(dst_rels, read_result.candidates, strict=True)
]
write_result = await dst_fs.write(
    entries=entries,
    overwrite=overwrite,
    user_id=user_id,
)

if op == "move":
    delete_candidates = VFSResult(
        function="delete",
        candidates=[Candidate(path=p) for p in src_rels],
    )
    delete_result = await src_fs.delete(candidates=delete_candidates, user_id=user_id)
```

The cross-mount atomicity contract does not change: read, write, and delete are
separate backend transactions. The improvement is that the parent router no
longer opens those transactions or calls private methods.

## Fanout operations

Glob/grep already call public methods on child mounts. Keep that. Change only
self-storage branches from open-coded `_use_session + _*_impl` to the local
helper:

```python
self_result = await self._call_local_impl(
    "glob",
    pattern=pattern,
    paths=paths,
    ext=ext,
    max_count=self_max_count,
    columns=columns,
    user_id=user_id,
)
```

Do not call `self.glob(...)` from inside `_route_glob_fanout`; that would recurse.

## MCP filesystem mount adapter

An MCP-backed filesystem mount should override public methods it supports and
translate them to `tools/call`:

```python
class MCPFileSystemMount(VirtualFileSystem):
    def __init__(self, session: ClientSession, *, tool_prefix: str = "vfs.") -> None:
        super().__init__(storage=False)
        self._session = session
        self._tool_prefix = tool_prefix

    async def _call_vfs_tool(self, op: str, arguments: dict[str, object]) -> VFSResult:
        result = await self._session.call_tool(
            f"{self._tool_prefix}{op}",
            arguments,
        )
        return VFSResult.from_mcp_tool_result(result)

    async def read(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._call_vfs_tool(
            "read",
            {
                "path": path,
                "candidates": candidates.model_dump(mode="json") if candidates else None,
                "columns": sorted(columns) if columns else None,
                "user_id": user_id,
            },
        )
```

It should not inherit the storage route for operations it claims to support.
Unsupported operations should return `CapabilityNotSupportedError` or a failed
`VFSResult`, depending on the error policy in the later MCP mount story.

The adapter should discover capabilities during initialization:

```python
tools = await session.list_tools()
tool_by_name = {tool.name: tool for tool in tools.tools}

required = {"vfs.read", "vfs.write", "vfs.stat", "vfs.ls"}
supported = required & tool_by_name.keys()
```

Name alone is not enough for trust. Tool annotations are useful hints, but VFS
permissions still decide whether a routed operation is allowed.

## VFS as an MCP server

The reverse adapter exposes a VFS instance as an MCP server. Tools call public
methods, then convert `VFSResult` to `CallToolResult`:

```python
def install_vfs_tools(server: MCPServer, vfs: VirtualFileSystem) -> None:
    @server.tool(
        name="vfs.read",
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
    )
    async def read(path: str | None = None,
                   candidates: dict | None = None,
                   columns: list[str] | None = None,
                   user_id: str | None = None) -> CallToolResult:
        result = await vfs.read(
            path=path,
            candidates=VFSResult.model_validate(candidates) if candidates else None,
            columns=frozenset(columns) if columns else None,
            user_id=user_id,
        )
        return result.to_mcp_tool_result()

    @server.tool(
        name="vfs.write",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
        ),
    )
    async def write(path: str | None = None,
                    content: str | None = None,
                    entries: list[dict] | None = None,
                    overwrite: bool = True,
                    user_id: str | None = None) -> CallToolResult:
        result = await vfs.write(
            path=path,
            content=content,
            entries=[VFSEntry.model_validate(e) for e in entries] if entries else None,
            overwrite=overwrite,
            user_id=user_id,
        )
        return result.to_mcp_tool_result()
```

The server adapter can also expose resources for read-only context:

```python
@server.resource("vfs://{path}")
async def read_resource(path: str) -> ReadResourceResult:
    result = await vfs.read("/" + path.lstrip("/"))
    candidate = result.file
    if candidate is None or candidate.content is None:
        raise ResourceError(result.error_message or f"No such resource: {path}")
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri=f"vfs://{path}",
                mime_type="text/plain",
                text=candidate.content,
            ),
        ],
    )
```

Resources are a view over readable files. Mutations, searches, and generic
tool execution remain tools.

## Generic MCP tool namespace

An MCP server that does not expose VFS/FSP tools can still be mounted as a
tool catalog:

```text
/tools/github/clone_repo
/tools/github/list_pull_requests
/tools/gmail/search_messages
```

`ls` lists tool entries. `read` returns the MCP `Tool` definition and input
schema. It does not execute the tool:

```python
async def read(self, path: str | None = None, ...) -> VFSResult:
    tool = self._tool_for_path(path)
    return VFSResult.from_mcp_tool_definition(tool)
```

Execution should be explicit in a later API:

```python
await vfs.call_tool("/tools/github/clone_repo", {"repo": "org/project"})
```

Do not overload normal file reads with execution side effects.

## Lifecycle

`remove_mount()` should only remove the namespace binding. It should not dispose
the child filesystem's engine:

```python
fs = self._mounts.pop(path)
self._rebuild_sorted_mounts()
```

`close()` remains the lifecycle hook that disposes engines for filesystems owned
by the current client. A caller that unmounts and wants disposal should retain
the filesystem reference it originally mounted and explicitly call
`await fs.close()`.

## Migration steps

1. Add `_call_local_impl(...)`.
2. Change `_route_single` to branch `fs is self` vs public child call.
3. Change `_dispatch_grouped_candidates` the same way.
4. Change `_route_write_batch` the same way.
5. Change `_route_two_path` and `_cross_mount_transfer`, preserving batched calls.
6. Change fanout self branches to use `_call_local_impl`; leave child fanout public.
7. Change `mkedge` to branch self vs child public call, or introduce a candidate-free
   grouped helper for same-mount edge creation.
8. Remove engine disposal from `remove_mount`; keep disposal in `close()`.
9. Add tests proving a `storage=False` remote-style mount receives public calls and
   no parent code opens its session.
10. Add `VFSResult.to_mcp_tool_result()` / `from_mcp_tool_result()` as boundary
    helpers, or document them as pending if the result-envelope story lands later.
11. Add an `MCPFileSystemMount` test double whose `call_tool` records tool names and
    JSON arguments.
12. Add a VFS MCP server registry test double that can generate `vfs.read`,
    `vfs.write`, `vfs.edit`, `vfs.delete`, `vfs.glob`, and `vfs.grep` tool
    definitions with JSON input/output schemas.

## Verification

Useful checks after implementation:

```text
No parent-to-child impl calls:
  dispatch tests mount a spy child that raises if _use_session or _*_impl is touched.

No recursive self dispatch:
  direct dbfs.read("/x") reaches _read_impl exactly once.

Batched cross-mount transfer:
  cross-mount copy calls src.read(candidates=...) once and dst.write(entries=...) once.

Lifecycle:
  remove_mount does not dispose the child engine; close does.

MCP mount shape:
  mounted MCPFileSystemMount receives session.call_tool("vfs.read", {...})
  and returns VFSResult.from_mcp_tool_result(...).

MCP server shape:
  public methods can be registered as MCP tools with JSON schemas and
  CallToolResult-compatible output.

Generic tools:
  read("/tools/server/tool_name") returns schema metadata only; execution is explicit.
```

The grep rule should be semantic, not absolute. `base.py` may contain
`self._call_local_impl(...)`, `_use_session`, and `self._*_impl` for local storage.
It must not contain code that calls those private members on a different filesystem
object.
