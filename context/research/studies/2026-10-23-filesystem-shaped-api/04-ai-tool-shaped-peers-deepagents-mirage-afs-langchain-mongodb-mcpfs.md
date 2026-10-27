# Study 04 — The AI-tool-shaped peers: what shape they chose, and what happened when a second consumer arrived

- **Date:** 2026-10-23
- **Brief:** `00-brief.md` (should vfs's public API become filesystem-shaped?)
- **Repos (read-only, refreshed per `refresh.log`):**
  - `~/Git/Repos/deepagents` — `main` @ `a3381668c4`, 2026-10-23, MIT
  - `~/Git/Repos/mirage` — `main` @ `02f6b99501`, 2026-10-23, Apache-2.0
  - `~/Git/Repos/afs` — `main` @ `1e9b731693`, 2026-03-24, BSL 1.1 (study only)
  - `~/Git/Repos/langchain-mongodb` — `main` @ `f9889d9baa`, 2026-10-23, MIT
  - `~/Git/Repos/mcpfs` — `main` @ `640511ef47`, 2026-03-06, MIT
- **Labels:** READ = a file at the commit above; EXECUTED = run here;
  INFERRED = my conclusion from what was read. Two `gh issue` lookups
  against `langchain-ai/deepagents` were made read-only (network).
- **Context skimmed:** `context/research/2026-09-15-filesystem-over-database-landscape-and-vfs-differentiation.md`.

The one-paragraph picture. Four of the five chose a **tool-shaped** kernel
(whole-file read/write/edit, `ls`, `glob`, `grep`, returning rows or text
for a model). One, mirage, started there (the memo of 2026-09-15 describes
it that way) and is now the opposite: a **POSIX-shaped** byte kernel
(`readdir`/`stat`/`read(offset,size)`/`write`/`rename`/`unlink`/...) with
the seven model tools, a shell, FUSE, FSKit, NFS, SFTP, HTTP, RPC and a CLI
all built *on top* of that kernel. mcpfs goes the other way and is the
control case: it proves which tool calls cannot be expressed as files.

---

## 1. The public operation set, exactly, and its shape

### deepagents (READ `libs/deepagents/deepagents/backends/protocol.py`)

`BackendProtocol` (line 404) — one abstract class, sync + `a*` async twins:

| Operation (line) | Signature | Shape |
| --- | --- | --- |
| `ls` (436) | `(path) -> LsResult{entries: list[FileInfo]}` | tool |
| `read` (454) | `(file_path, offset=0, limit=2000) -> ReadResult{file_data: FileData, total_lines, start_line, end_line, next_offset}` — **offset/limit are lines, not bytes** | tool |
| `grep` (499) | `(pattern, path=None, glob=None, *, max_count=None) -> GrepResult{matches: list[GrepMatch], truncated}` — literal substring, not regex | tool |
| `glob` (598) | `(pattern, path=None) -> GlobResult{matches: list[FileInfo], truncated, truncation_reason}` | tool |
| `write` (659) | `(file_path, content: str) -> WriteResult` — whole file, create-or-overwrite | tool |
| `edit` (685) | `(file_path, old_string, new_string, replace_all=False) -> EditResult{occurrences}` | tool |
| `delete` (722) | `(file_path) -> DeleteResult` — optional, default raises `NotImplementedError` | tool |
| `upload_files` (754) / `download_files` (786) | `list[tuple[str, bytes]]` / `list[str]` → per-file responses | tool (bulk bytes) |

`SandboxBackendProtocol` (892) adds `id` and `execute(command, *, timeout) -> ExecuteResponse` (909).
`FileData` (187) is `{content: str, encoding: "utf-8" | "base64", created_at, modified_at}`.
Nothing is handle- or byte-offset-shaped: no `open`, `stat`, `rename`, `mkdir`, directory cursor.
The model-facing tools are the same eight names (READ `middleware/filesystem.py:2031-2040`:
`ls, read_file, write_file, edit_file, delete, glob, grep, execute`).

### mirage (READ `python/mirage/vfs/base.py`, `docs/home/setup/custom-vfs.mdx`)

`BaseVFS` (base.py:43). Three required: `readdir(path) -> list[FileStat]` (273),
`read(path, *, offset=0, size=None) -> bytes` (282), `stat(path) -> FileStat` (302).
Optional (custom-vfs.mdx, "The base class"): `write(path, bytes)`, `append`,
`copy`, `truncate(path, length)`, `rename`, `unlink`, `mkdir(parents)`, `rmdir`,
`rm_r`, `dir_copy`, `setattr(mode, uid, gid, atime, mtime)`, `read_stream`,
`write_stream(atomic)`, `close`; plus **push-down hooks** `files_containing`,
`lines_containing`, `first_lines`, `last_lines`, `line_count`, `follow`,
`checksum`, `read_tree`, and a `search(SearchQuery)` for backends with one
(`python/mirage/types.py:416`). **All POSIX-shaped, all bytes**; the docstring
says every shell command "runs on the three required ones" (base.py:46-50).
The seven model tools sit above: `shell, read, write, edit, ls, grep, glob`
(READ `docs/home/access/mcp.mdx:108-116`); `read` there is line-numbered with
`offset`/`limit` (default 2000 lines), `grep` is a regex "as `grep -rn` does",
`edit` is `old_string/new_string/replace_all` (mcp.mdx:139-200).

### afs (READ `spec/afs-protocol.md`, `packages/core/src/afs.ts`)

Eight (plus rename and two batches) in §3: `read(path, filter?, startLine?, endLine?)`
(79), `list(path, filter?, maxDepth?, offset?, limit?, orderBy?, pattern?)` (111),
`stat` (148), `write(path, content: unknown, meta?, mode: replace|append|prepend|patch|create|update)` (175),
`delete` (216), `search(path, query, limit?, caseSensitive?)` (243),
`exec(path, action, args)` (270), `explain(path, format)` (317), `rename` (342),
`batchWrite`/`batchDelete` (368/386). Core implements them at `afs.ts:1302-2006`.
Content is `unknown` (JSON tree or string), line-ranged, no handles — **tool-shaped
with an `exec`/`explain` extension**. The CLI (`packages/cli/src/core/commands/`:
`ls read write delete search stat explain exec mount serve explore mcp-bridge`) and
the MCP server (`packages/cli/src/mcp/tools.ts:24-307`: `afs_read … afs_explain`)
are 1:1 wrappers of the same eight.

### langchain-mongodb (READ `libs/langchain-mongodb-deepagents-vfs/langchain_mongodb_deepagents_vfs/backend.py`)

`MongoFilesystemBackend(BackendProtocol)` (80): `grep` (279), `glob` (299), `ls` (314)
answered from Atlas; `read` (332), `write` (362), `edit` (376), `upload_files` (400),
`download_files` (412) forwarded to S3. No `delete`. Exactly deepagents' shape; the
only signature drift is that `grep`'s `pattern` is documented as a
"Natural-language or keyword query" (283) — the name stayed, the semantics changed.

### mcpfs (READ `internal/fuse/fs.go`, `internal/fuse/toolnode.go`)

A go-fuse node tree. Implemented: `dirNode.Getattr` (199), `Readdir` (205),
`Lookup` (241); `fileNode`/`toolFileNode` `Getattr`, `Open`, `Read` (355-391, 44-80).
Nothing else — no `Write`, `Create`, `Unlink`, `Setattr`. **POSIX-shaped and
read-only by omission**; its own write surface is a CLI (`mcpfs tool <server> <tool> --flags`).

**Lesson for vfs:** the model-facing verb set converges on the same eight names
everywhere; what differs is whether those eight are the kernel (deepagents, afs)
or a thin layer over a byte kernel (mirage), and only the latter also serves a kernel mount.

---

## 2. Search and edit: generic layer or per-backend primitive?

**deepagents — per backend, by design.** `grep`/`glob` are abstract on the
protocol and each backend implements them: `StateBackend` in pure Python over
its file dict (`state.py:280-291` → `utils.grep_matches_from_files` at
`utils.py:1091`), `FilesystemBackend` via ripgrep with a Python fallback
(`filesystem.py:72-86`), `BaseSandbox` by shelling `grep -rHnFZ` and parsing
stdout (`sandbox.py:2063-2089`), `CompositeBackend` by fan-out plus path
remapping and a shared `max_count` budget (`composite.py:35-60`). The protocol
docstring states why: the tools "are not just convenience wrappers around
`execute`" — they enforce literal matching, structured results, caps and
permission rules (`protocol.py:408-422`, READ). `edit` is the one verb with a
shared helper (`perform_string_replacement`, `utils.py:697`) but each backend
still owns the read→replace→write (`state.py:223`, `sandbox.py:1827`). Result
shape: rows (`GrepMatch{path, line, text, context_before?, context_after?}`,
`protocol.py:159-185`); the **middleware** renders rows to model text in three
modes (`files_with_matches | content | count`, `filesystem.py:1355-1361`).
Semantic search: none in the protocol; langchain-mongodb smuggles it in under `grep`.

**mirage — generic over the three primitives, with optional push-down.** `grep`,
`rg`, `find`, `head`, `wc` run on `readdir`+`stat`+`read`; a backend may
answer `files_containing`/`lines_containing` and "Mirage still matches each
line itself, so the output is the same" (`docs/home/integration/search.mdx:6-9`,
READ). Glob "is not a per-backend file: the mount derives `glob` from the
VFS's `readdir`" (`docs/python/vfs/new.mdx:463`). Semantic search is a separate
verb, `search --method --top-k --threshold` over `SearchQuery` (`tools.mdx`
"Search and compare"; `types.py:416`). `edit` is in the tool layer:
`read_for_edit` → `replace_text` → `write_edit`, refused with
`StaleMirageFileError` if the file changed since the session read it
(`workspace/tools/tool_operations.py:404-452`, READ). Result shape: bytes/text
(a `grep -rn` line), never rows.

**afs — a provider verb.** `search` is one of the eight; the core fans it out
across mounts under the scope (`spec §3.6`, "Cross-mount search"; `afs.ts:1953`).
No `glob`, no `grep`, no `edit`; `write mode: "patch"` merges structured data
(spec 175-200). Result shape: `AFSEntry[]`, "provider-dependent (may include
match highlights)".

**langchain-mongodb — backend primitive replaced by an index.** `grep` is an
Atlas `$rankFusion` of full-text and vector search over pre-chunked bodies
(`search.py:105-127`); each hit is projected to a `GrepMatch` whose `line` is
the chunk's `line_start` and whose `text` is the **whole chunk** (`search.py:377-396`, READ).
Rank is list order because `GrepMatch` has no score field. `glob`/`ls` are also
served from the index, not S3.

**mcpfs — refuses search.** `search_*`/`query_*` tools are "CLI only, needs input"
(`docs/gateway-design.md:33`; `classify.go:38-40`).

**Lesson for vfs:** the two mature designs agree that search is *derivable* from
read primitives but *worth* a backend hook; the row/text split belongs in the
renderer, not in the kernel's return type.

---

## 3. The second consumer: what it cost

### deepagents: the shell is the second consumer, and it broke the rules

- **File ops reimplemented over `execute`.** `BaseSandbox.read` runs "a Python
  script on the sandbox via `execute()`" and parses stdout, text capped "to about
  500 KiB to avoid backend stdout/log transport failures" (`sandbox.py:1719-1727`, READ);
  `grep` and `glob` are shell strings parsed back (`2063-2125`). Cost, READ from
  issues: #5177 "BaseSandbox.grep silently returns zero matches on every busybox
  image (GNU-only `-Z` + `2>/dev/null || true`)" and #5112 "path globs fail because
  the inline Python command is not shell-safe" (EXECUTED: `gh issue list`).
- **Permissions cannot see the shell.** `_set_permissions` raises
  `NotImplementedError("FilesystemMiddleware does not yet support permissions with
  backends that provide command execution ... Tool-level permissions for the execute
  tool are not implemented")` unless every rule path sits under a non-sandbox
  `CompositeBackend` route (`middleware/filesystem.py:2054-2062`, carve-out at `739-754`, READ).
  `LocalShellBackend` says it plainly: "shell access is unrestricted and can bypass
  filesystem restrictions" and "`virtual_mode=True` and path-based restrictions
  provide NO security with shell access enabled" (`backends/local_shell.py:68-86`, READ).
  Issue #3191 reports exactly that path (EXECUTED lookup).
- **No FUSE, CLI-as-fs, or sync client exists**; `grep -ri "fuse|posix|real filesystem"`
  over `docs/` and READMEs returns nothing (EXECUTED). `CompositeBackend` is the only
  routing layer and it remaps paths in every result (`composite.py:35-45`).
- The large-result **offload** writes tool output back into the filesystem
  (`ExecuteOffloadResult`, `protocol.py:857`; `middleware/_blob_offload.py`) — a
  second *writer* of the tree that is not the model.

### mirage: one byte kernel, eight front doors, and the costs are documented

READ `docs/home/access/overview.mdx` table: in-app, HTTP, MCP, RPC, CLI, SSH
(`ssh`, `sftp`, `scp`, `sshfs`), FUSE/FSKit, and (`docs/python/setup/fuse.mdx:62`)
an NFSv3 server in Rust (`rust/mirage-rs/src/nfs/`, adapted from `nfsserve`).
Everything routes through one `Dispatcher` ("FUSE and `ws.vfs` reach here without
passing `Workspace.dispatch`", `dispatcher.py:820-833`) and one `MountCore`
("Protocol-neutral mount logic shared by every kernel adapter ... SFTP and
codex-exec await the core", `mount/core.py:56-62`). What the kernel adapters cost:
- **Handles and buffering** the VFS does not have: `MountCore` keeps a `FileTable`
  of handles, per-file hydration futures, pending-mutation chains and buffered
  writes that land on `flush`/`release` (`core.py:100-115`, `865-964`, READ).
- **Size.** API-backed files cannot `stat` a size without rendering; FUSE is
  mounted with `direct_io` and `attr_timeout=0` so the kernel reads to EOF
  (`docs/python/setup/fuse.mdx:173-181`); FSKit has no `direct_io`, so
  "size-unknown files read as empty" (157-162); the NFS mount is read-only (62).
  The flag `sizes_always_known` exists on `BaseVFS` for this alone (`base.py:98-112`).
- **Policy loses a layer.** An op-only entry point "cannot apply" command-level
  rules; "path rules, hides and modes still hold" (`core.py:86-96` warning, READ).
- **Full scans.** Glob/`find` over `readdir` are refused past `full_scan_limit`
  (`new.mdx:463`; commit `12c0dc0255` 2026-10-23 "stop every walk at the mount's
  full_scan_limit", READ `git log`).
- The **hierarchy kit** is not a mount: it is a scope table that builds
  `readdir`/`stat`/`read` for an API tree of `<label>__<id>` directories
  (`make_readdir`, `make_stat`, `make_read(parented=True)`, `new.mdx:395-461`).

### afs: a wire protocol, a CLI, an MCP server, a web explorer — and no kernel mount

Single-endpoint JSON-RPC (`spec §10.1`, `POST /rpc`), a planned REST binding (§10.2
"Planned"), ndjson streaming only for `exec` (990-997), binary bodies **not** in
JSON — "`content` omitted ... use separate binary endpoint" (824, 939-944). The
non-model clients are the CLI (`packages/cli/src/core/commands/`), the MCP server
(`packages/cli/src/mcp/`), and the explorer websocket UI (`packages/explorer/src/ws-server.ts`).
All are the eight verbs again; nothing needs a handle, so nothing paid for one.
No FUSE/POSIX anywhere (`grep -i fuse|posix` over README, spec, cli: no hits, EXECUTED).

### langchain-mongodb: the second party is a *producer*

The only consumer is deepagents' tool loop, but S3 changes from outside arrive via
a polling or SQS **watcher** (`watcher/polling.py`, `watcher/sqs.py`) that re-chunks
and re-embeds (`sync.py`). The index is a sidecar that can lag the bytes — the
README says `grep/glob/ls` "block until ready" (README "Quickstart").

### mcpfs: tools as files — what a filesystem can and cannot say

Implements only lookup/readdir/getattr/open/read. Writes and searches are "not
mounted — CLI proxy only" because they need parameters a path cannot carry
(`docs/gateway-design.md:25-33`, `:100`; `classify.go:33-50`, READ). Cost of the
POSIX side: `Getattr` must **call the tool** to learn the size, and `Read` calls it
again (`fs.go:355-391`, `toolnode.go:30-66`); the `Cache` type exists but
`NewCache` is never referenced outside its own file (EXECUTED `grep -rn NewCache`),
so every `ls -l` and every `cat` is one or two live RPCs (INFERRED from the two).

**Lesson for vfs:** the second consumer always arrives as a *kernel* (a shell, a
mount, a sync daemon), and a tool-shaped core either reimplements its verbs per
transport (deepagents) or adds a byte kernel underneath (mirage); only the byte
kernel keeps one policy chokepoint.

---

## 4. Permissions and views: where the gate sits

| Project | Mechanism | Enforced in | Hidden path reads as |
| --- | --- | --- | --- |
| deepagents | `FilesystemPermission{operations, paths, mode: allow/deny/interrupt}` (`middleware/filesystem.py:368-405`), `_check_fs_permission` (409) on the tool path, results filtered post hoc (`757`) | **tool middleware**; backends know nothing | "permission denied" text; `glob` docstring warns a backend returning a relative path "silently bypasses every deny rule" (`protocol.py:648`) |
| mirage | profile `paths.hide`/`paths.show`, `mounts.mode`, `commands.allow/ask/deny` (`docs/home/profiles.mdx`) | **the one Dispatcher**, before any mount: `path_visible`/`leads_hidden` → `hidden_refusal` (`dispatcher.py:1599-1616`); hides "also appl[y] to direct VFS operations", command lists "do not govern ... direct VFS calls" (profiles.mdx "Rule matching") | `ENOENT` — "as if it did not exist"; refusal reason travels beside the result, "never in stderr" (`explain.mdx`); `explain.vfs.read(path)` previews the decision |
| afs | provider-declared `accessMode` (readonly/create/append/readwrite), `visibility: full|meta`, action severity policy (`spec §5`) | **core compositor** before the provider (`afs.ts:554-580`; `1606`, `1982` for `meta`) | `AFS_ACCESS_MODE`; `meta` hides content but not existence |
| langchain-mongodb | `s3_prefix` scoping only (README "Configuration") | constructor | n/a |
| mcpfs | none; mode `0444`, server token is the identity (`fs.go:363`) | — | — |

Two of five put the gate *inside* the single primitive path (mirage, afs); the
tool-wrapped one (deepagents) has the documented bypass (shell) and the
documented foot-gun (relative paths). vfs's ladder-at-one-chokepoint (brief) is
the mirage/afs placement.

**Lesson for vfs:** a view that must hold for every consumer has to live below
the verbs, at the one place every verb and every transport passes.

---

## 5. Bodies and size

- **deepagents.** Whole-file `str`, `encoding` utf-8 or base64 (`FileData`,
  `protocol.py:187-200`). `read` windows are **lines**: tool default 100, backend
  default 2000 (`filesystem.py:1079`, `protocol.py:457`); the middleware adds the
  gutter and splits lines over 5000 chars into `5.1`, `5.2` rows (`utils.py:242, 363`).
  Any tool result is cut at 20,000 tokens × 4 chars (`utils.py:243, 765-782`).
  Binary is by extension: images/PDF/audio/video become content blocks, video
  up to 1 GiB (`utils.py:177, 452`; `filesystem.py:290-350`). Sandbox reads cap
  text at ~500 KiB (`sandbox.py:1723`). No streaming, no byte ranges; bulk bytes
  only via `upload_files`/`download_files`.
- **mirage.** Bytes everywhere. `read(offset, size)` is honoured only when the
  VFS sets `reads_ranges`, "the caller otherwise reads the whole file and slices
  it" (`base.py:289-291`); `read_stream`/`write_stream(atomic)` for large bodies
  (310-330); every command's output capped at 2,000 lines / 600 s by default
  (`docs/home/core/output-limits.mdx:7-9`); the MCP `read` is numbered lines
  with `offset`/`limit` (mcp.mdx:143-145). A 100 MB file over FUSE is read in
  chunks through `_read_chunk` (`core.py:1038`); size-unknown files are the
  documented hole (§3).
- **afs.** `content: unknown`; `startLine`/`endLine` for text (`type.ts:245-258`);
  binary "MUST NOT be base64-encoded inside JSON" — `content: null` plus
  `meta.contentType`/`meta.size`, bytes via a separate `GET` (spec 939-944).
- **langchain-mongodb.** Hard cap `MAX_READ_BYTES = 64 MiB` on read **and**
  write (`backends/base.py:24`; `s3.py:115-128, 145-149`). `read` does a HEAD,
  then fetches the **whole** object and slices lines in Python because "line-offset
  slicing needs the whole decoded object, so a byte Range can't substitute"
  (`backend.py:343-357`, READ) — the S3 `Range` support in the store (`s3.py:98-103`)
  goes unused by the protocol's line-shaped read.
- **mcpfs.** The whole tool result is materialised per `Getattr` and per `Read`
  and sliced by offset in memory (`fs.go:371-385`); no cap.

**Lesson for vfs:** a line-shaped read forces whole-body decode on every backend
that stores bytes; a byte-shaped read lets the renderer choose lines without
the kernel paying for them.

---

## 6. Roadmaps and regrets

- **deepagents** is deepening the tool shape, not leaving it: the last 25
  commits on `protocol.py` add `truncated` flags, context lines, pagination
  metadata, `max_count`, exit codes (READ `git log`). The one explicit position
  statement defends tools over the shell (`protocol.py:408-422`). The recorded
  gap is permissions + execute: "does not **yet** support" (`filesystem.py:2055`).
  No issue or doc asks for a POSIX/FUSE face (EXECUTED search, §3).
- **mirage** moved the other way since the 2026-09-15 memo and keeps going:
  README now says agents reach it through "a real mountpoint over FUSE and
  FSKit" plus the shell; the last day's commits are kernel-flavoured ("Write a
  program's output into its files as it runs", `full_scan_limit`, hidden mount
  roots; `git log` 2026-10-23). Recorded regrets are about the *mount* side:
  FSKit size-unknown files "read as empty", NFS read-only, op-only entry points
  losing command rules (§3). No wish recorded to be *less* filesystem-shaped.
- **afs** is a spec with a planned REST binding (§10.2) and no kernel ambition;
  the clone is a single squashed commit dated 2026-03-24 with a `scripts/sync-oss.ts`,
  so public history is flattened and seven months quiet (INFERRED: mirrored from
  a private tree; stalled or private).
- **langchain-mongodb** reserves an `llm` parameter "for future agent LLM
  integration" (README), ships no `delete`, and its newest commit is a path
  convention patch — "strip leading slash in grep/ls/glob so agent path calls
  match" (`f9889d9`, 2026-10-23, READ). INFERRED: the pain is the seam between
  deepagents' absolute virtual paths and S3's relative keys, i.e. the adapter
  pays for not owning the namespace.
- **mcpfs** has three days of history (2026-03-04..06) and one design doc whose
  settled rule is "Write tools always go to CLI proxy" (`gateway-design.md:100`).
  No regret recorded; INFERRED the project accepted that a path cannot carry
  a parameterised call and stopped there.

**Lesson for vfs:** nobody who built the tool shape first has written down a
wish for POSIX, and the one project that added a POSIX kernel wrote down only
mount-side regrets — the shape change itself is not among them.

---

## Design facts for the synthesis

1. READ — deepagents' kernel is eight whole-file verbs with **line** windows; no handle, byte offset, `stat` or `rename` exists on `BackendProtocol` (`protocol.py:404-806`).
2. READ — deepagents makes `grep`/`glob` abstract per backend and reimplements them four ways (dict scan, ripgrep, shell string, composite fan-out); two shell-string bugs reached issues (#5112, #5177).
3. READ — deepagents refuses path permissions on any backend with `execute` (`middleware/filesystem.py:2054-2062`) and documents that the shell bypasses path rules (`local_shell.py:68-86`).
4. READ — mirage's kernel is `readdir`/`stat`/`read(offset,size)` over bytes with optional POSIX verbs and push-down hooks; `ls`, `grep`, `glob`, `head`, `wc` and the seven model tools are all derived above it (`vfs/base.py`, `custom-vfs.mdx`).
5. READ — mirage serves MCP, HTTP, RPC, CLI, SSH/SFTP/SSHFS, FUSE, FSKit and NFS from one `Dispatcher` and one `MountCore`; hide/show is enforced in the dispatcher before any mount (`dispatcher.py:1599-1616`).
6. READ — mirage's mount-side costs are a handle table with buffered writes, a `sizes_always_known` flag, FSKit size-unknown files reading empty, NFS read-only, and command-level rules unenforceable at op-only entry points.
7. READ — mirage's `edit` and stale-write refusal live in the tool layer over `read`/`write` with a per-session version tracker (`tool_operations.py:243-257, 404-452`), not in the kernel.
8. READ — afs enforces access mode and `meta` visibility in the core compositor before the provider (`afs.ts:554-580, 1606, 1982`) and keeps binary bodies out of the JSON wire (spec 939-944).
9. READ — langchain-mongodb's line-shaped `read` fetches the whole object (64 MiB cap) and leaves S3 byte ranges unused (`backend.py:343-357`); its `grep` returns whole chunks as `GrepMatch` rows ranked by list order (`search.py:377-396`).
10. INFERRED — mcpfs is the boundary proof: list/get tools map to `readdir`/`read`, but create/update/delete/search cannot be paths and are pushed to a CLI; a filesystem face needs a separate verb door for parameterised actions.
