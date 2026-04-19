# Plan 9 & Plan 9 from User Space — Influences for VFS and FSP

> Reference repos: `/Users/claygendron/Git/Repos/plan9`, `/Users/claygendron/Git/Repos/plan9port`

## Overview

Plan 9 from Bell Labs (1980s–1990s) and Plan 9 from User Space (plan9port) codify "everything is a file" not as ideology but as operational design: the 9P protocol exposes any service—processes, network connections, synthetic filesystems—through a uniform path hierarchy, with a small set of atomic verbs (`Tread`, `Twrite`, `Tstat`, `Twalk`). VFS borrows this namespace unification and mount routing; FSP is a modern wire-format restatement of 9P's transactional semantics. Together, they are the architectural ancestors Grover builds on, not alternatives to reinvent.

## Navigation Guide

**Plan 9** (`/Users/claygendron/Git/Repos/plan9`): The original kernel-based system. Key subtrees: `sys/man/1/bind`, `sys/man/1/mount`, `sys/man/4/0intro` (file servers), `sys/man/3/srv` (service registry), `sys/src/cmd/bind.c`, `sys/src/cmd/mount.c`. Skip: graphics, the CPU protocol, device drivers—those don't apply. **Most relevant:** `sys/man/1/bind` and `sys/man/4/srv` explain union directories and the name space registry that VFS mount routing mirrors.

**Plan 9 from User Space** (`/Users/claygendron/Git/Repos/plan9port`): A Unix port of core Plan 9 userland. Key subtrees: `include/9p.h` (protocol structs), `include/fcall.h` (wire messages), `src/lib9p/` (server framework), `src/lib9p/srv.c` (902 lines; request routing), `src/lib9p/file.c` (tree walking), `src/lib9p/ramfs.c` (minimal synthetic server), `man/man3/post9pservice.3` (service lifecycle). Skip: graphics, utilities unrelated to FS. **Most relevant:** `srv.c` and `file.c` show how 9P abstracts Fid (file handle) pools and path walking; `ramfs.c` demonstrates the minimal request-handler pattern.

## File Index

| Path | Purpose |
|---|---|
| plan9port:`include/9p.h:1–150` | Core server framework: `Fid`, `Req`, `File`, `Srv`, `Readdir`, `Tree` type definitions; Req lifecycle; Fid pools for handle management |
| plan9port:`include/fcall.h:1–140` | 9P2000 protocol wire format; `Fcall` struct (request/response union); message type enums (Tread, Twrite, Tstat, Twalk, Tversion, Tattach, Tauth); `Qid` structure (path, vers, type); IOHDRSZ overhead |
| plan9port:`src/lib9p/srv.c:1–100` | Protocol dispatch: message parsing (`convM2S`), error classification, msize negotiation, tag/fid validation; version handshake (line 36–50); request dequeuing (line 52–106) |
| plan9port:`src/lib9p/srv.c:108–150` | Path walking: `filewalk` (line 108–130), incremental Qid validation per component, `walkandclone` pattern (line 132+) |
| plan9port:`src/lib9p/file.c:1–100` | File lifecycle: `allocfile`, `freefile`, `closefile`, lock ordering rules; parent-child bidirectional refs; Filelist for directory entries |
| plan9port:`src/lib9p/ramfs.c:1–100` | Minimal server: `Ramfile` struct (in-memory data), `fsread`/`fswrite` (range handling), `fscreate` (with perm), `fsopen` (truncate mode); in-memory tree ops |
| plan9port:`man/man4/9pserve.4:1–98` | Multiplexing userland servers: single 9P conversation → many clients; fid/tag cleanup on disconnect; `-n` no-auth, `-M` msize options |
| plan9port:`man/man3/post9pservice.3:1–30` | Service posting lifecycle: post to `/srv`, optional mount via 9pfuse; one fd ↔ one service |
| plan9:`sys/man/1/bind:1–200` | Union directory semantics: `-b` (prepend), `-a` (append), `-c` (creation writable), default (replace); old is alias for new; non-POSIX operation |
| plan9:`sys/man/1/mount:1–70` | 9P mount on Unix: Linux kernel module / FUSE fallback; spec arg (attach param); `/srv` as mount-point registry |
| plan9:`sys/man/3/srv:1–80` | Kernel `#s` device: registry of open fds; write fd number → bulletin board for services; per-file reference counting |
| plan9:`sys/man/4/0intro:1–15` | File server philosophy: synthesized vs. persistent storage; single server model; name space composition via bind/mount |
| plan9port:`include/fcall.h:80–115` | Request/response type enum: Tversion(100)/Rversion, Tauth(102)/Rauth, Tattach(104), Tflush(108), Twalk(110), Tread(116), Twrite(118), Tstat(124), Twstat(126); error marshalling |
| plan9port:`src/lib9p/req.c:1–50` | Request pool: tag → Req mapping; flushed-request tracking; response serialization (`convS2M`) |
| plan9port:`src/lib9p/fid.c:1–81` | Fid pool management: ulong fid ↔ Fid* map; open mode tracking; per-fid aux data (backend-specific) |
| plan9:`sys/man/4/srv:1–100` | Remote service mounts: `srv` command dials 9P port 564; posts `/srv/<name>`; optional auto-mount via `-m` |
| plan9port:`man/man4/9pserve.4:1–98` | 9pserve: acts as Plan 9 kernel on Unix; multiplexes N clients → 1 server; inherent flow-control (single conversation) |

## Core Concepts (What They Did Well)

### 1. **Qid: Efficient Cache Invalidation and Handle Tracking**
The Qid type (13 bytes: 1 type byte + 4-byte path + 8-byte version) is 9P's answer to inode caching. Path identifies the object; vers stamps each state change. A client never asks "has /foo/bar changed?" — it caches the Qid from the last walk and compares on next access. This separates "where is the file?" (path) from "is my cache valid?" (vers), cutting protocol round-trips. **For VFS:** Port this to `GroverResult` metadata. Each Entry should carry a version token so agents can detect stale references without re-stat. Enables pipeline of edits without interleaving reads.

### 2. **Fid Pooling and Per-Connection Handle Isolation**
Fids are not OS file descriptors (which are per-process). They are per-connection channel IDs managed by the server. A Fid struct carries: open mode, user, file pointer, aux data (backend storage). One client can hold 100 fids to the same file in different open modes. **For VFS:** Analogous to async session/transaction scoping. The `_use_session` context manager in `base.py` mirrors Fid lifecycle—acquire, operate, release. Plan 9 names this "resource management in the protocol"; Grover calls it SQLAlchemy sessions. Both solve the same problem: transactional consistency without OS-level file table coupling.

### 3. **Incremental Path Walking with Atomic Qid Snapshots**
`Twalk` steps through path components one at a time; client can abort mid-walk. If step N fails, client retries from step N with a different name. Server holds no state across walk messages. Each Qid returned is a read-only snapshot at that instant. **For VFS:** This design underpins the "longest-prefix mount" routing in `base.py:_resolve_terminal`. The plan9 walk never resolves a mount; Grover walk does (and caches the terminal fs). But both refuse to hold path-walking state—each walk is independent. Keep this for correctness: if a mount is added mid-request, the terminal fs is determined at request entry, not mid-walk.

### 4. **Union Directories Without Symlinks**
`bind -b <new> <old>` prepends `<new>` to the union of `<old>`; reads see `<new>` first. `bind -c` marks writable. No symlinks, no ELOOP, no "follow or not" ambiguity. Reads are shadowing; writes are layered. **For VFS:** The connection graph (`/file/.connections/type/target`) is a 9P-style explicit edge list, not implicit indirection. Agents see edges, not symlink-following magic. Matches Grover's philosophy of "everything transparent in the path tree."

### 5. **Multiplexing at Protocol Level, Not OS Level**
`9pserve` and `post9pservice` take a single server fd and multiplex N clients via 9P tagging. No threads, no processes—just message dispatch by tag and fid. When a client exits, the OS closes the underlying connection, and `9pserve` flushes orphaned tags. **For VFS:** Grover's `_mounts` dict is a static dispatch table. FSP is a protocol layer, not a multiplex. But the principle holds: FSP should support tagged requests and explicit flushing so agents can timeout/cancel without leaving server state (connections) dangling.

### 6. **Synthetic Filesystems are First-Class**
`ramfs` (in-memory tree), `fossil` (block storage with venti backend), `exportfs` (remote namespace relay)—all implement the same `Req` handler interface. A server is just a set of function pointers (`fsread`, `fswrite`, `fscreate`, etc.). No distinction between "real" and "virtual" — all are synthesized. **For VFS:** The `_*_impl` terminal pattern in `base.py` is this. A `DatabaseFileSystem._write_impl` is no more "real" than a future `GraphFileSystem._write_impl`. Subclasses are just different backends; the protocol is invariant.

### 7. **Error Strings, Not Errno Codes**
9P returns freeform error strings in `Rerror` (the `ename` field is a C string). No numeric codes, no locale translation, no errno aliasing. Clients parse strings for retryability semantics. **For VFS:** Grover's `_classify_error` function maps error strings to semantic categories (`NotFoundError`, `WriteConflictError`, etc.). Plan 9 stopped at strings; Grover adds structured intent. Both reject errno enums.

## Anti-Patterns & Regrets

### 1. **Message Size Negotiation (Tversion) as a Kludge**
Clients and servers negotiate `msize` (max message size) during `Tversion` handshake. This was born from a lack of true framing in early Plan 9 networks. Modern FSP over MCP shouldn't re-invent this: MCP has length-prefixed JSON. **For FSP:** Don't expose msize negotiation. Assume MCP transports handle framing; cap single responses at a reasonable size (e.g., 10MB for bulk reads) and paginate/stream larger results. Negotiation adds a round-trip.

### 2. **Fid-as-Cursor Anti-Pattern**
A Fid can be opened in O_RDONLY and then a Twalk issued on the same Fid. The Fid becomes a "cursor" at both the file and a sibling. This dual state is confusing and rarely used. Unix doesn't support it. **For FSP/VFS:** Disallow this. A path operation and a read operation should not share state. Keep them separate.

### 3. **Wstat (Metadata Update) Complexity**
`Twstat` updates mode, mtime, uid/gid, etc. in a single message. If the array is malformed (size mismatch), the entire wstat fails. Partial updates aren't possible. **For FSP:** Provide separate operations for metadata changes (one per kind: permissions, mtime, owner). Avoid the monolithic stat struct.

### 4. **No Streaming / Full Message in Kernel**
9P reads the entire Tread message into kernel space before calling the handler. There's no streaming or callback-on-partial-buffer. Bulk reads of large files require many round-trips. **For FSP:** Streaming is essential for agents working with large code files. Use chunked/streaming responses with explicit end-of-data marker.

### 5. **Union Directory Creation Semantics are Surprising**
`bind -c` marks a directory as writable, but the write goes to the *first* `-c`-marked directory in the union, not the most recently bound one. If multiple directories are `-c`-marked, the behavior is non-obvious. **For VFS:** Directory-level write permissions in `PermissionMap` are simpler—a path prefix either allows write or doesn't. Don't emulate union shadowing; be explicit.

### 6. **Namespace Isolation via Name Space Groups**
Plan 9 has name space groups: a process can inherit the parent's namespace and fork a new isolated one. There's no per-user namespace in a single login session. **For Grover:** User-scoped VFS is better—one `DatabaseFileSystem(user_scoped=True)` per user, not per process. Avoids the namespace-group complexity of Plan 9.

## Implications for VFS (Implementation)

### 1. **Mount Routing: The Qid-Version Pattern**
VFS should cache the terminal fs for a given path prefix *and* include a version number in the mount registry. If a mount is added/removed, bump the version. This allows agents to detect "mount table changed" without re-resolving on every operation. This is 9P's Qid versioning applied to the mount table.

**Action:** Add a `_mount_version: int` field to `VirtualFileSystem`. Increment on `add_mount`/`remove_mount`. Cache `(prefix, version)` in `_resolve_terminal` results. If version changed, re-resolve.

### 2. **Fid Pooling Analogy: Session Scoping**
The Fid pool in `srv.c` is exactly what `_use_session` does. Plan 9 binds Fid → File → user; Grover binds session → transaction → user_id. Both are right. Keep the session model; it's proven.

### 3. **Incremental Path Walking: Don't Lose It**
`_resolve_terminal` walks mount prefixes longest-first. This is good. But the entry point (`public` methods like `read`, `write`) should always re-resolve at request entry, never cache a terminal fs across multiple public-method calls. Reason: a mount could be added between the glob and the read. Plan 9 can't add mounts mid-request, but Grover can. So be strict: each public method re-resolves.

**Action:** Audit all public methods to confirm they re-resolve, never reuse a terminal fs from a prior call.

### 4. **Backend Handlers: The _*_impl Pattern is Correct**
`ramfs.fsread`, `ramfs.fswrite`, `ramfs.fscreate` are the `_*_impl` pattern. Stick with it. Each backend (DatabaseFileSystem, LocalFileSystem, CachedFileSystem) overrides the set of handlers it needs; base class raises NotImplementedError. This is the proven design.

### 5. **Error Propagation: Leverage the GroverResult Union**
9P returns error strings; Grover returns `VFSResult(success=False, errors=[...])`. This is an upgrade: structured intent. But like 9P, errors should *stop* the operation and return early. No partial success. If a glob across multiple mounts has one mount fail, the entire glob result fails. Plan 9 does this; adopt it.

**Action:** Ensure `_merge_results` propagates `success=False` if any input has `success=False`. Test: cross-mount glob with one mount down should fail, not return partial results.

### 6. **Permission Model: Don't Adopt 9P Mode Bits**
9P Fid has `omode` (0–3, representing read/write/read+write/execute). Grover has `PermissionMap` (path prefix → read/read_write). Grover's model is cleaner because it's not per-fid-per-user, it's per-path-per-deployment. Don't change it.

### 7. **Cross-Mount Operations: Explicit Layering**
`_cross_mount_transfer` (base.py:559–608) does read → write → delete. This is not atomic—writes commit before deletes. Plan 9 has no concept of cross-mount operations (mounts don't cross in the kernel's path walk). But for Grover, make the non-atomicity explicit in the docstring and tests. Agents will try cross-mount moves; they must understand the hazard.

## Implications for FSP (Protocol)

### 1. **9P Message Framing is Overcomplicated; MCP is Better**
9P uses a 4-byte little-endian length prefix + message + no trailer. This is actually fine, but the Tversion negotiation around msize is kludgy. MCP uses JSON over a transport with framing (stdio, HTTP). Stick with MCP; don't re-invent wire framing.

**Action:** FSP messages are MCP tools. Each tool (read, write, glob, grep) maps to a handler. Return results in `FSPResult` (ok, path, data, error, meta). No size negotiation.

### 2. **Fid Abstraction: Use Opaque String Handles**
9P Fids are 32-bit integers. Clients and servers coordinate allocation (client suggests, server approves). For FSP over MCP, use opaque string handles (UUIDs or base64-encoded state). This avoids the "fid already in use" failure mode and makes the protocol more resilient to out-of-order messages.

**Action:** If FSP ever implements stateful open handles (for streaming reads), use opaque string handles, not integers. But for now, FSP is stateless per tool invocation—no handles needed.

### 3. **Tagged Requests and Flushing**
9P tags (16-bit transaction IDs) allow clients to multiplex requests and flush (cancel) on timeout. MCP doesn't expose tagging at the tool level, but agents could be slow. FSP should support an optional `timeout` parameter on long-running ops (glob, grep on large trees) with explicit timeout semantics.

**Action:** Add `max_wait_ms` to glob, grep, and search operations. If exceeded, return partial results + "timed out" flag in FSPResult. Don't hang.

### 4. **Walk vs. Attach: Separate Root and Path Resolution**
9P has `Tattach` (claim the root of the tree) and `Twalk` (navigate from there). FSP methods (read, write, glob) all take a `path` string. No separate attachment. This is fine—simpler for agents. But internally, FSP implementations should mimic Attach: validate the root user/namespace, then walk.

**Action:** FSP server (when implemented) should validate user_scoped VFS at attach time, then all paths are relative to the user's root.

### 5. **Qid Versioning for Cache Invalidation**
Include a `version` token in FSPResult entries (matching VFS Qid.vers semantics). Agents can cache entry metadata and check version on next access. This cuts stat calls.

**Action:** FSP `Entry` type should have `version: str` field (opaque version token). On path operations, include it. Document: "if version matches cached entry, metadata is unchanged."

### 6. **Error Handling: Lean on Semantic Classes, Not Errno**
9P returns error strings; FSP should map to semantic classes. FSPResult has `error: str` (for display) and implicit semantic class (NotFoundError, WriteConflictError, etc.) inferred from context. Plan 9 doesn't have this; Grover does. Use it in FSP.

**Action:** FSPResult.error is a human string; FSPResult.ok==False can map to an enum (NotFound, WriteConflict, Invalid, etc.) or clients infer from context. Document the mapping.

### 7. **Union Directory Representation**
Union directories (bind -b/-a) don't exist in FSP as a first-class concept. But FSP implements the *effect*: a path can resolve to different backends (mounts). When a client lists a mount point, they see the union of self + mounted backends. This matches bind behavior without naming it. Keep it implicit.

### 8. **Service Registry and Posting**
9P has `/srv` (kernel device). FSP doesn't. But the pattern is valuable: agents should be able to "post" a service (mount a new backend) at runtime. FSP should expose `add_mount(path, backend_config)` as a tool, so agents can dynamically extend the namespace.

**Action:** Future FSP roadmap: `add_mount`, `remove_mount` tools (not just read/write/glob). Same mount semantics as VFS `add_mount`.

## Open Questions

1. **Version Token Semantics:** Should VFS include a per-object version in every GroverResult entry? Qid.vers is per-file; agents need per-directory-entry granularity. Design the version string format before exposing it.

2. **Cross-Mount Atomicity:** The non-atomic read→write→delete in move/copy is a hazard. Can it be documented clearly enough that agents understand the risk? Or should moves across mounts be disallowed?

3. **Union Directory Shadowing in FSP:** When FSP lists a mount point, should entries from self shadow entries from mounts (like bind)? Or should FSP merge/sort them (like FUSE overlayfs)? Current VFS behavior: self is shadowed by mounts (see `_exclude_mounted_paths`). Is this the right trade-off?

4. **Streaming Large Files:** 9P's multi-round-trip for large reads is a legacy problem. FSP should stream, but how to signal end-of-data over MCP without a framing protocol? Use explicit `done: bool` in result? Chunked transfer encoding?

5. **Fid State Isolation:** Plan 9 isolates Fid state per connection, not per user. Grover uses user_scoped VFS. Is per-user enough, or should FSP/VFS track per-connection isolation? (Unlikely to matter for agent use, but worth naming.)

6. **Authentication Model:** 9P has Tauth (explicit auth message). Grover has user_id as a parameter. FSP should clarify: is auth out-of-band (MCP caller authenticated by harness) or in-protocol (FSP carries credentials)? Current design: out-of-band. Document this.
