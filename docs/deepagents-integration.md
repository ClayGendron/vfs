# Integrating VFS with `deepagents`

Audience: the grover/VFS team. This doc explains what the
[`deepagents`](https://github.com/langchain-ai/deepagents) framework expects
from a filesystem backend, where the impedance gaps with VFS sit, and what
shape an adapter should take so a deepagents agent can be pointed at a VFS
mount and "just work" — while still surfacing VFS's agentic features
(versioning, edges, semantic/BM25 search, the query DSL).

---

## 1. How deepagents talks to a filesystem

deepagents exposes a fixed set of FS-shaped tools to the LLM and routes the
calls to a pluggable **backend**. Concretely:

- Tools (`read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep`,
  optionally `execute`) are registered by `FilesystemMiddleware`
  (`libs/deepagents/deepagents/middleware/filesystem.py`).
- Each tool dispatches to a backend implementing `BackendProtocol`
  (`libs/deepagents/deepagents/backends/protocol.py`). Sandboxes additionally
  implement `SandboxBackendProtocol` and add `execute()`.
- Built-in backends are `StateBackend` (in-memory state), `StoreBackend`
  (LangGraph `BaseStore`), `FilesystemBackend` (real disk),
  `LocalShellBackend` (disk + subprocess), the remote sandboxes
  (`LangSmithSandbox`, `ModalSandbox`, `DaytonaSandbox`), and a
  `CompositeBackend` that routes by path prefix.
- Paths are absolute strings starting with `/`. There is no URI scheme — the
  backend owns the namespace.

A new backend needs to subclass `BackendProtocol` and implement six methods
(plus their `a*` async variants). The full surface, with the contract:

| Method | Signature (sync) | Returns |
|---|---|---|
| `read` | `read(file_path: str, offset: int = 0, limit: int = 2000)` | `ReadResult(error, file_data)` |
| `write` | `write(file_path: str, content: str)` | `WriteResult(error, path)` |
| `edit` | `edit(file_path: str, old_string: str, new_string: str, replace_all: bool = False)` | `EditResult(error, path, occurrences)` |
| `ls` | `ls(path: str)` | `LsResult(error, entries: list[FileInfo])` |
| `glob` | `glob(pattern: str, path: str = "/")` | `GlobResult(error, matches: list[FileInfo])` |
| `grep` | `grep(pattern: str, path: str \| None, glob: str \| None)` | `GrepResult(error, matches: list[GrepMatch])` |

Each method has an `a<name>` async counterpart. The default `a*` impls just
`asyncio.to_thread` the sync version, so an async-native backend can override
the async methods directly and leave the sync ones to wrap them — or the
other way around.

Result dataclasses live in `protocol.py`:

- `ReadResult.file_data` is a `FileData` TypedDict:
  `{"content": str, "encoding": "utf-8" | "base64", "created_at"?, "modified_at"?}`.
- `FileInfo` TypedDict: `{"path": str, "is_dir"?: bool, "size"?: int, "modified_at"?: str}`.
- `GrepMatch` TypedDict: `{"path": str, "line": int, "text": str}` (1-indexed).
- Errors are returned as plain strings on `.error`. Standardized literals
  (`file_not_found`, `permission_denied`, `is_directory`, `invalid_path`)
  exist in `FileOperationError` and should be preferred for the recoverable
  cases — the LLM can then react to them.

deepagents also supports optional `upload_files` / `download_files` for batch
binary I/O. Implementing these lets host code move binaries in/out of VFS
without going through the LLM tool surface.

---

## 2. Where VFS and deepagents agree, and where they don't

### Maps cleanly

| deepagents tool | VFS method | Notes |
|---|---|---|
| `read_file` | `VirtualFileSystem.read(path)` | Both async-friendly; VFS returns content via `VFSResult.content` |
| `write_file` | `VirtualFileSystem.write(path, content, overwrite=False)` | deepagents semantics are "fail if exists" — pass `overwrite=False` |
| `edit_file` | `VirtualFileSystem.edit(path, old, new, replace_all=...)` | Field-for-field match |
| `ls` | `VirtualFileSystem.ls(path)` | VFS returns `Candidate` rows; flatten to `FileInfo` |
| `glob` | `VirtualFileSystem.glob(pattern, paths=(base,))` | VFS supports `**` and ext filters; ignore extras |
| `grep` | `VirtualFileSystem.grep(pattern, globs=(glob,), paths=(path,), fixed_strings=True)` | deepagents grep is **literal**, not regex — set `fixed_strings=True` |

### Doesn't map (and that's fine)

These are VFS-only and have no deepagents tool counterpart — but they are the
reason a team would pick VFS over `FilesystemBackend`. Surface them as
**custom tools** alongside the filesystem tools (see §5).

- `semantic_search`, `lexical_search`, `vector_search`
- `predecessors` / `successors` / `ancestors` / `descendants` / `neighborhood`
- `pagerank` / `betweenness_centrality` / `closeness_centrality` / `hits`
- `mkedge`
- `tree`, `stat`
- Versioning (history/snapshot reads under `/.vfs/.../__meta__/versions/`)
- The query DSL via `run_query()` / `cli()`

### Friction points to plan for

1. **Async vs sync.** VFS is async-first (`VFSClientAsync`). The
   `BackendProtocol.read/write/edit/ls/glob/grep` methods are sync by
   default. Override the `a*` variants to call VFS directly and leave the
   sync versions as `asyncio.run(...)` shims (or raise from sync paths).
   deepagents' middleware uses the async path inside the agent loop, so
   overriding `aread`, `awrite`, etc. is the high-leverage move.
2. **Literal grep.** deepagents' `grep` is literal substring matching. Pass
   `fixed_strings=True` to `VirtualFileSystem.grep` and ignore regex
   metacharacters. (If you want to opt into regex, expose a separate custom
   tool — don't redefine `grep`.)
3. **Glob semantics.** deepagents callers pass a base `path` plus a
   `pattern`. VFS's `glob` takes an absolute pattern plus optional `paths=`
   filter. Join them deliberately: if `pattern` starts with `/`, pass it
   through; otherwise prepend `path` (treating `/` as default).
4. **`FileInfo` flattening.** VFS `Candidate` rows are richer than
   `FileInfo`. Collapse to the four fields deepagents understands:
   ```python
   FileInfo(
       path=c.path,
       is_dir=(c.kind == "directory"),
       size=c.size_bytes,
       modified_at=c.updated_at.isoformat() if c.updated_at else None,
   )
   ```
   Don't leak `chunk` / `version` / `edge` rows into `ls` / `glob` results
   unless the agent explicitly asked for them — they live under `/.vfs/` and
   should stay there. Filter them out by default.
5. **Encoding.** deepagents uses `{"content": str, "encoding": "utf-8" |
   "base64"}`. VFS stores text. Map directly to `"utf-8"`. If a binary read
   path is added later, base64-encode at the adapter boundary.
6. **`offset`/`limit` on read.** deepagents' `read` is line-paginated
   (default 2000 lines). VFS returns full content. Slice in the adapter
   before returning.
7. **Error normalization.** Translate VFS exceptions to the standardized
   `FileOperationError` literals where possible:
   - `NotFoundError` → `"file_not_found"`
   - `WriteConflictError` (path exists + `overwrite=False`) →
     a descriptive string ("file exists") since deepagents has no
     `already_exists` literal — the agent reads the message
   - `permissions.read_only` rejections → `"permission_denied"`
   - `MountError` / `ValidationError` → `"invalid_path"`
8. **`is_directory` on read.** If the agent reads a path that resolves to a
   `kind="directory"` row, return `error="is_directory"`.
9. **Path normalization.** VFS expects rooted absolute paths. deepagents
   tool prompts already require absolute paths starting with `/`, so the
   contracts agree — but the adapter should still defensively reject
   relative paths and return `"invalid_path"` rather than passing through.

---

## 3. The adapter: shape and skeleton

The recommended deliverable from the VFS side is a **package**
`vfs.integrations.deepagents` (or a separate `vfs-deepagents` distribution)
exposing one class:

```python
class VFSBackend(BackendProtocol):
    def __init__(self, vfs: VFSClientAsync, *, user_id: str | None = None,
                 hide_meta: bool = True): ...
```

Skeleton — illustrative, not exhaustive:

```python
from deepagents.backends.protocol import (
    BackendProtocol, ReadResult, WriteResult, EditResult,
    LsResult, GlobResult, GrepResult, FileInfo, GrepMatch,
)
from vfs import VFSClientAsync
from vfs.exceptions import (
    NotFoundError, WriteConflictError, ValidationError, MountError,
)

META_PREFIX = "/.vfs/"

class VFSBackend(BackendProtocol):
    def __init__(self, vfs: VFSClientAsync, *, user_id=None, hide_meta=True):
        self._vfs = vfs
        self._user_id = user_id
        self._hide_meta = hide_meta

    async def aread(self, file_path, offset=0, limit=2000):
        if not file_path.startswith("/"):
            return ReadResult(error="invalid_path")
        try:
            res = await self._vfs.read(file_path, user_id=self._user_id)
        except NotFoundError:
            return ReadResult(error="file_not_found")
        # If the resolved candidate is a directory, signal it.
        cand = next(res.iter_candidates(), None)
        if cand and cand.kind == "directory":
            return ReadResult(error="is_directory")
        text = res.content or ""
        lines = text.splitlines()
        sliced = "\n".join(lines[offset : offset + limit])
        return ReadResult(file_data={"content": sliced, "encoding": "utf-8"})

    async def awrite(self, file_path, content):
        try:
            await self._vfs.write(
                file_path, content, overwrite=False, user_id=self._user_id,
            )
        except WriteConflictError as e:
            return WriteResult(error=str(e))
        except (ValidationError, MountError):
            return WriteResult(error="invalid_path")
        return WriteResult(path=file_path)

    async def aedit(self, file_path, old_string, new_string, replace_all=False):
        try:
            res = await self._vfs.edit(
                file_path, old=old_string, new=new_string,
                replace_all=replace_all, user_id=self._user_id,
            )
        except NotFoundError:
            return EditResult(error="file_not_found")
        # VFSResult.success carries whether the replacement applied.
        if not res.success:
            return EditResult(error="; ".join(res.errors) or "edit failed")
        # Occurrences: derive from result if VFS exposes it; otherwise 1 / N.
        return EditResult(path=file_path, occurrences=None)

    async def als(self, path):
        try:
            res = await self._vfs.ls(path, user_id=self._user_id)
        except NotFoundError:
            return LsResult(error="file_not_found")
        return LsResult(entries=[self._to_file_info(c) for c in res.iter_candidates()
                                 if self._visible(c.path)])

    async def aglob(self, pattern, path="/"):
        abs_pattern = pattern if pattern.startswith("/") else f"{path.rstrip('/')}/{pattern}"
        res = await self._vfs.glob(abs_pattern, user_id=self._user_id)
        return GlobResult(matches=[self._to_file_info(c) for c in res.iter_candidates()
                                   if self._visible(c.path)])

    async def agrep(self, pattern, path=None, glob=None):
        kwargs = {"fixed_strings": True, "user_id": self._user_id}
        if path is not None: kwargs["paths"] = (path,)
        if glob is not None: kwargs["globs"] = (glob,)
        res = await self._vfs.grep(pattern, **kwargs)
        matches: list[GrepMatch] = []
        for c in res.iter_candidates():
            if not self._visible(c.path): continue
            for lm in (c.lines or []):
                # LineMatch = (start, end, match) — 1-indexed
                matches.append({"path": c.path, "line": lm.match,
                                "text": (c.content or "").splitlines()[lm.match - 1]
                                        if c.content else ""})
        return GrepResult(matches=matches)

    # Sync stubs — agent loop uses the a* variants
    def read(self, *a, **kw): return _run(self.aread(*a, **kw))
    def write(self, *a, **kw): return _run(self.awrite(*a, **kw))
    def edit(self, *a, **kw): return _run(self.aedit(*a, **kw))
    def ls(self, *a, **kw): return _run(self.als(*a, **kw))
    def glob(self, *a, **kw): return _run(self.aglob(*a, **kw))
    def grep(self, *a, **kw): return _run(self.agrep(*a, **kw))

    def _visible(self, path: str) -> bool:
        return not (self._hide_meta and path.startswith(META_PREFIX))

    def _to_file_info(self, c) -> FileInfo:
        info: FileInfo = {"path": c.path}
        if c.kind is not None:
            info["is_dir"] = (c.kind == "directory")
        if c.size_bytes is not None:
            info["size"] = c.size_bytes
        if c.updated_at is not None:
            info["modified_at"] = c.updated_at.isoformat()
        return info
```

`_run` is a small helper that schedules the coroutine on a worker loop —
mirror what `VFSClient` already does internally so behavior is consistent
between the two clients.

---

## 4. Wiring it into a deepagents agent

Once the adapter is published, the agent author writes:

```python
from deepagents import create_deep_agent
from deepagents.middleware.filesystem import FilesystemMiddleware
from vfs import VFSClientAsync
from vfs.integrations.deepagents import VFSBackend

vfs = VFSClientAsync()
vfs.add_mount("/data", DatabaseFileSystem(engine_url="postgresql+asyncpg://..."))

backend = VFSBackend(vfs, user_id="alice")

agent = create_deep_agent(
    model="claude-sonnet-4-6",
    middleware=[FilesystemMiddleware(backend=backend)],
    # ...
)
```

Two compositions worth highlighting in the docs:

1. **VFS for content, state for scratch.** Use `CompositeBackend` to route
   `/data/**` and `/memories/**` to `VFSBackend` and leave everything else
   on `StateBackend` so transient agent scratch doesn't churn VFS rows:
   ```python
   from deepagents.backends.composite import CompositeBackend
   from deepagents.backends.state import StateBackend

   backend = CompositeBackend(
       default=StateBackend(),
       routes={"/data/": VFSBackend(vfs), "/memories/": VFSBackend(vfs)},
   )
   ```
2. **Sandbox + VFS.** A remote sandbox handles `execute()`; VFS handles
   durable storage. Route `/workspace/` to the sandbox and `/data/` to VFS
   with the same `CompositeBackend` pattern.

---

## 5. Surfacing the agentic features as custom tools

This is where VFS earns its keep over a flat backend. Ship a companion
middleware (e.g. `VFSToolsMiddleware`) that registers extra LangChain tools
on top of the standard six. Suggested first set:

| Tool | Backed by | Why |
|---|---|---|
| `vfs_semantic_search(query, k=15, paths=None)` | `vfs.semantic_search` | Natural-language retrieval over the same namespace |
| `vfs_lexical_search(query, k=15, paths=None)` | `vfs.lexical_search` | BM25 fallback for keyword/code identifier hits |
| `vfs_neighborhood(path, depth=2)` | `vfs.neighborhood` | Pull related files via edges instead of guessing paths |
| `vfs_pagerank(scope=None, top=10)` | `vfs.pagerank` | "What are the most central files in this corpus?" |
| `vfs_history(path)` | `ls /.vfs/{path}/__meta__/versions/` | Read prior versions without leaving the FS abstraction |
| `vfs_query(query)` | `vfs.run_query` / `vfs.cli` | Power tool: full DSL, returns rendered text |

Design notes:

- Return `VFSResult.to_str(projection=...)` (or a curated dict) so the LLM
  sees compact text, not nested objects.
- Keep these tools **separate** from the standard FS tools. The
  deepagents tool prompts are tuned for the literal six — overloading
  them confuses the model. New names, new docstrings.
- `vfs_query` is the most powerful single tool you can ship. The DSL
  composes (`grep "auth" | glob "*.py" | pagerank | top 10`) and is far
  cheaper than chaining tool calls. It's also the easiest tool to
  document for an LLM because it's "shell-shaped".

---

## 6. Permissions, multi-tenancy, and HITL

deepagents has its own `PermissionMiddleware`
(`libs/deepagents/deepagents/middleware/permissions.py`) that gates the six
standard tools by glob rules. VFS has its own `PermissionMap`. Don't try to
unify them — let each enforce its layer:

- **deepagents permissions** decide whether a *tool call* is allowed (e.g.
  no writes outside `/scratch/`).
- **VFS permissions** decide whether a *backend op* is allowed (e.g. the
  `/synthesis` mount is read-only globally).

The adapter should pass `user_id` through verbatim. If the host wants
per-user scoping, configure the underlying VFS backend with
`user_scoped=True` and the same `user_id`. Document this in the README so
deployers don't try to do it twice.

For risky ops (edits, deletes), recommend that integrators stack
`HumanInTheLoopMiddleware` from deepagents on top of the FS tools. VFS's
soft-delete + versioning are a strong safety net (any bad edit is
recoverable from `/.vfs/.../__meta__/versions/`), but HITL still wins for
production.

---

## 7. Testing checklist

The deepagents repo has a backend test suite under
`libs/deepagents/tests/unit_tests/backends/` — run the equivalent contract
tests against `VFSBackend`:

- [ ] `read` of a missing path returns `ReadResult(error="file_not_found")`.
- [ ] `read` of a directory path returns `ReadResult(error="is_directory")`.
- [ ] `read` with `offset=N, limit=M` returns the right line slice.
- [ ] `write` to a new path succeeds; second write to the same path returns
      a non-empty `WriteResult.error`.
- [ ] `edit` with a unique `old_string` rewrites the file; non-unique
      `old_string` with `replace_all=False` errors.
- [ ] `ls` of a directory returns only direct children, with
      `is_dir`/`size`/`modified_at` populated where VFS knows them.
- [ ] `ls` does **not** leak `/.vfs/` rows when `hide_meta=True`.
- [ ] `glob("*.py", "/src")` and `glob("/src/**/*.py")` return the same set.
- [ ] `grep("TODO", glob="*.py")` returns 1-indexed line numbers and the
      raw line text.
- [ ] All operations are idempotent under repeated calls and respect
      `user_id` scoping.
- [ ] An agent run end-to-end with `create_deep_agent` against a real VFS
      mount (SQLite is enough for CI) actually finishes a small task —
      e.g. "list files under /data, find the one mentioning 'foo', edit it
      to say 'bar'."

---

## 8. Open questions for the VFS team

These are real choices the integration forces you to make. Resolve them
before publishing the package:

1. **Edit occurrences.** Does `VirtualFileSystem.edit` return a count of
   replacements? deepagents' `EditResult.occurrences` is optional but the
   LLM uses it. If not, decide whether to add it to the VFS API or always
   return `None`.
2. **Encoding policy.** Will VFS ever store non-UTF-8 content? If yes,
   define how the adapter signals `"base64"` to deepagents.
3. **Meta visibility.** Default to hiding `/.vfs/` from `ls`/`glob`/`grep`?
   I'd argue yes — the LLM will get distracted by chunk and version rows
   in normal listings — and provide opt-in via the custom tools above.
4. **Sync wrapper strategy.** Reuse `VFSClient`'s background-loop trick or
   require the host to provide a loop. The first is friendlier; the second
   composes better with frameworks that own their loop.
5. **Distribution.** Ship inside `vfs` (`vfs.integrations.deepagents`) or as
   a separate `vfs-deepagents` package? Separate packages avoid pulling
   `langchain` into core VFS — probably the right call.
6. **Versioned read tool.** Should `read` accept an optional `version=` arg
   (mapped to a version-row read) or stay strictly current-version, with
   history exposed only via the custom `vfs_history` tool? deepagents' tool
   schema is fixed, so the answer is "history goes through a custom tool".

---

## 9. What would actually make a deepagents engineer pick this up

Switching gears — here's the read from the other side of the table. If
you're building VFS and want a deepagents engineer to *pull* the package
rather than politely nod and keep using `FilesystemBackend`, the pitch
needs to attack the things that actually keep us up at night. The
contract-level adapter in §3 is necessary but not sufficient. The features
below are what make VFS *compelling*, in rough order of how often they
come up in real deepagents engineering work.

### 9.1 Versioning as a first-class undo

Every deepagents demo has the same scary moment: the agent calls
`edit_file` on something important, gets it wrong, and there is no clean
way back. The current answers are all bad — wrap everything in HITL
(slow), snapshot the working tree before each turn (clunky), or just hope
git is clean (not always true). VFS's automatic per-write versioning is
the single feature most likely to make an engineer say "oh, I'd actually
build on this."

What sells it isn't "we have versioning." Every store has versioning.
What sells it is the **ergonomics for an agent**:

- A built-in `vfs_undo(path, steps=1)` tool that an LLM can call mid-run.
  No checkpointer dance, no human in the loop, no separate API. The
  agent says "that edit was wrong, undo it" and continues.
- A `vfs_diff(path, from=N, to=M)` tool that returns a unified diff so
  the agent can *reason about its own edits*. This unlocks
  self-correction loops in a way that snapshotting state cannot.
- Cheap branching: "explore two refactors, keep the better one." If
  branches are a real primitive (not just `git worktree` energy) this is
  a category-defining feature for multi-agent / planner-executor setups.
- A guarantee that `delete` is recoverable by default. Soft-delete with
  `permanent=True` as the explicit opt-in is exactly the right default
  for an LLM caller — you're inverting the dangerous default.

If VFS ships these as *tools the LLM can call*, not as APIs the host has
to wire up, that's the wedge. Most stores stop at "we store history."
Stop at "the agent can use the history."

### 9.2 The query DSL is the actual product

deepagents' standard tool surface is six tools. Every additional tool
costs context window and confuses the model. The thing the framework is
quietly bad at is **composition** — `grep` then filter by glob then sort
by recency takes three turns and a lot of token spend.

VFS's `run_query("grep 'auth' | glob '*.py' | pagerank | top 10")` is, to
a deepagents engineer, the most interesting thing in the whole package.
One tool, one round-trip, composable, shell-shaped (LLMs are *very* good
at shell-shaped DSLs because of training data). If the docs lead with
this — not "we have a database" — engineers will get it instantly.

Concrete asks to make this land:

- A bulletproof grammar reference an LLM can be shown in a system prompt
  in <500 tokens. If the DSL needs a 4-page manual, it loses.
- Per-step error messages that say "stage 3 (`pagerank`) got 0 candidates
  because stage 2 (`glob '*.pyx'`) returned nothing." LLMs recover from
  good error messages and spiral on bad ones.
- A `dry_run=True` mode that returns the query plan as text so the agent
  can validate before executing. Cheap, huge for trust.
- An `explain` step (`grep "auth" | explain`) that returns the SQL or
  execution plan. Lets the agent reason about cost.

The DSL is also how you escape "tool soup." Instead of shipping ten
custom tools (semantic_search, lexical_search, pagerank, neighborhood…)
you ship *one* tool that exposes them all via composition. That is a
strictly better story for context window economy.

### 9.3 Retrieval that lives in the same namespace

Right now in deepagents, "give the agent a vector store" is a separate
project from "give the agent a filesystem." Two abstractions, two paths,
two tools, and the model has to remember which is which. RAG sits beside
the FS, not inside it.

VFS collapsing semantic + lexical + filesystem into one namespace is
philosophically the right move. The pitch:

- **One mental model for the LLM.** Paths are paths. Whether the result
  came from `glob`, `grep`, or `semantic_search`, the next tool call is
  `read_file(path)`. No "now switch to the vector tool" cognitive
  overhead.
- **Hybrid by construction.** `semantic_search & glob("**/*.py")` is a
  one-liner because results are sets of paths. In deepagents today this
  is a custom function in the host.
- **Retrieval that respects ACLs.** If permissions are enforced at the
  FS layer, vector search inherits them for free. Today, RAG ACLs are a
  recurring pain point — anyone shipping multi-tenant RAG ends up
  reimplementing this.

The feature that closes this: **automatic chunk + embed on write**.
deepagents agents write files constantly (research notes, scratch
analyses, plans). If those become searchable the moment they're written,
without the host running an indexing job, that is a step-change in
agent capability over a long horizon. "The agent's own scratchpad
becomes its memory" is the headline.

### 9.4 Edges turn the FS into a knowledge graph the agent can use

Everyone has graph-shaped data. Almost no one exposes it to the agent.
The pattern today is: scrape, build a graph offline, dump into Neo4j,
build a separate retriever, give the agent yet another tool. By the
time the agent uses it, the graph is stale.

VFS letting the agent both *traverse* edges (`successors`,
`neighborhood`) and *create* them (`mkedge`) is the feature that turns
the FS into a live knowledge graph. The "agent writes its own edges as
it learns" loop is genuinely new. Use cases that immediately get easier:

- Code understanding: agent reads a file, declares `imports` /
  `calls` / `extends` edges, future agents traverse them instead of
  re-parsing.
- Research: agent reads a doc, declares `cites` / `contradicts` edges,
  next agent does `neighborhood(doc, depth=2)` instead of re-searching.
- Planning: tasks as nodes, dependencies as edges, `predecessors` is
  "what blocks me", `descendants` is "what unblocks if I finish this."

PageRank/centrality on top is what makes this *more* than a graph DB.
"Show me the most central files" is a question deepagents engineers
build by hand all the time and ship something worse than what VFS gives
for free.

The thing to nail in the pitch: **edges are cheap to write and cheap to
read**. If `mkedge` costs a round trip and a transaction, agents won't
bother. If it's effectively free, agents will write a *lot* of them and
the graph compounds.

### 9.5 Reversibility as a design stance

Stepping up a level: the feature that ties everything above together is
that VFS is **reversible by default**. Versioned writes, soft deletes,
edges as data (deletable, queryable), the query DSL as composable
read-only-by-default — every primitive is built so that an agent acting
in good faith with imperfect judgment can't do permanent damage.

This is the philosophical pitch, and it's the one that will resonate
with deepagents engineers who've watched an agent `rm -rf` a directory
in a sandbox. The deepagents framework leans hard on HITL because the
underlying filesystem (real disk, sandbox, state) doesn't give you a
safety net. VFS *is* the safety net. That changes the risk calculus on
running agents with fewer approval gates, which is the actual unlock for
shipping autonomous work.

Make sure the docs say this out loud. "VFS is the first filesystem
designed for an agent that will sometimes be wrong" is a better tagline
than any feature list.

### 9.6 The "everything is a file" promise has to be real

VFS's most distinctive design choice — versions, chunks, edges,
embeddings all addressable as paths under `/.vfs/` — is also the easiest
thing to undersell. If the agent can *only* reach this metadata through
custom tools, the philosophical claim falls apart and it's just another
DB with a path-shaped key.

The compelling version: an agent debugging a bad edit can literally
`read_file("/.vfs/src/auth.py/__meta__/versions/3")` and see the prior
content, with no new tool, no new mental model. An agent exploring a
codebase can `ls("/.vfs/src/auth.py/__meta__/edges/out/imports")` and
see what the file imports. The standard six tools become arbitrarily
powerful because the namespace itself carries the structure.

For this to work in practice:

- Metadata paths need to be **stable and documented**. If the layout
  changes between versions, every prompt that references it breaks.
- A "metadata cheat sheet" belongs in the system prompt — five lines
  the model can be primed with. Bake it into `VFSToolsMiddleware`.
- The `hide_meta=True` default I recommended earlier needs an obvious
  escape hatch (`hide_meta=False` or per-call `include_meta=True`)
  because half the value is the agent reaching into `/.vfs/`
  deliberately.

### 9.7 What does *not* matter (don't lead with these)

Worth being explicit, because it's where every database product
mistakenly leads:

- **"SQL-agnostic, runs on Postgres/MSSQL/SQLite."** A deepagents
  engineer cares about agent behavior, not your storage portability.
  Mention it in passing under "deployment."
- **Raw performance numbers.** Agent latency is dominated by the LLM,
  not the FS. Don't benchmark against ext4.
- **"Enterprise-scale."** Code red. Means nothing to the audience. The
  audience is one engineer trying to get an agent to stop deleting
  things.
- **Schema diagrams of `vfs_entries`.** Internal detail. The pitch is
  the namespace and the agent UX, not the table layout.

### 9.8 The three-bullet pitch

If the README's first three bullets aren't approximately these, the
positioning is off:

1. **Every agent edit is reversible** — versioned writes, soft deletes,
   undo as a tool the LLM can call.
2. **One namespace for files, search, and graph** — `read_file`,
   `semantic_search`, `pagerank`, and `neighborhood` all return paths;
   the agent never context-switches between abstractions.
3. **A composable query DSL** — `grep | glob | pagerank | top 10` in
   one tool call, instead of three turns of tool soup.

Everything else is supporting evidence.

---

## TL;DR

Subclass `BackendProtocol`, override the six `a*` methods to call
`VFSClientAsync`, normalize errors, hide `/.vfs/` from default listings,
and ship a separate middleware that exposes `semantic_search`, graph
traversal, and `run_query` as custom tools. The standard deepagents agent
loop will then drive VFS as its filesystem with no further changes — and
agents that opt into the extra tools get the full Grover experience.
