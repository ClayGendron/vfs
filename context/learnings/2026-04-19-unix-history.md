# Unix History — Influences for VFS and FSP

> Reference repo: `/Users/claygendron/Git/Repos/unix-history-repo`

## Overview

The Unix History repo is a reconstructed Git history spanning 1970–2025, containing V1 through V7 Research Edition, BSD releases 1–4.4, 386BSD, and FreeBSD. The Research V7 snapshot available here reveals the minimal filesystem surface that became the de-facto standard: inode-based storage, directory trees via pathname resolution, open/creat/read/write/unlink/link/stat/seek syscalls, mount/umount, and Unix permissions (uid/gid/mode). This is the proof by continuity that Grover's "everything is a file" semantics should target—not abstract elegance, but what survived 50+ years of production use in billions of systems.

## Navigation Guide

The repo is a single snapshot branch (`Research-V7-Snapshot-Development`) with hierarchical layout: `usr/sys/sys/` contains kernel source (inode, allocation, pathname resolution, syscalls). `usr/sys/h/` contains headers: `inode.h`, `dir.h`, `filsys.h`, `mount.h` define the data structures. `usr/sys/sys/sys*.c` files split the syscalls: `sys1.c` (exec), `sys2.c` (open/creat/read/write/seek/link), `sys3.c` (stat/fstat/mount/umount), `sys4.c` (unlink/chdir). Key files to ignore: device-specific code (`usr/sys/dev/`), TTY handling, and the PDP-11 assembler. The filesystem itself is 130 lines of headers and ~650 lines of kernel C.

## File Index

- `usr/sys/h/inode.h:26–47` — Core inode struct: mode, nlink, uid/gid, size, 13-entry address array (direct + indirect blocks), flags (ILOCK, IUPD, IACC, IMOUNT, IWANT, ITEXT, ICHG).
- `usr/sys/h/dir.h:4–8` — Directory entry: 16-byte struct (2-byte inode number, 14-byte name, no length prefix).
- `usr/sys/h/filsys.h:4–23` — Superblock: free-block list, free-inode list, per-filesystem locks (s_ilock, s_flock), modification flag, read-only flag, timestamps.
- `usr/sys/h/mount.h:6–11` — Mount table: device, superblock pointer, mounted-on inode pointer (minimal).
- `usr/sys/sys/iget.c:30–90` — `iget(dev, ino)` — in-core inode cache with LRU eviction, mount indirection. `iexpand()` hydrates in-core inode from disk. `iput()` decrements refcount, deallocates on last ref.
- `usr/sys/sys/iget.c:149–193` — `iupdat()` — writes dirty flags (IUPD, IACC, ICHG) to disk inode, updates atime/mtime/ctime.
- `usr/sys/sys/alloc.c:26–71` — `alloc(dev)` — block allocator with in-superblock free list; reads next block's free list when current exhausted.
- `usr/sys/sys/alloc.c:78–109` — `free(dev, bno)` — block deallocator, maintains free list stack discipline (FILO → contiguous spans).
- `usr/sys/sys/alloc.c:144–214` — `ialloc(dev)` — inode allocator, caches spare inodes in superblock; linear scan on cache miss.
- `usr/sys/sys/nami.c:20–200` — `namei(func, flag)` — pathname→inode resolution. Handles `/` prefix, loops through path components, checks execute permission, handles mount points, reads directory blocks, scans entries.
- `usr/sys/sys/nami.c:305–321` — `wdir(ip)` — writes directory entry after namei marks parent.
- `usr/sys/sys/fio.c:19–32` — `getf(fd)` — fd→file struct lookup, bounds check.
- `usr/sys/sys/fio.c:45–73` — `closef(fp)` — decrements refcount, calls device close on last ref, truncates and deallocates file if unlinked.
- `usr/sys/sys/pipe.c:25–56` — `pipe()` — allocates inode, two file structs, sets FPIPE flag. Pipes are unidirectional, backed by a regular file in the inode table.
- `usr/sys/sys/sys2.c:30–75` — `rdwr(mode)` — common read/write path: fetch file struct, check permissions, dispatch to pipe or inode path.
- `usr/sys/sys/sys2.c:80–93` — `open()/creat()` — pathname→inode via `namei()`, then `open1()` for permissions/allocation/device open.
- `usr/sys/sys/sys2.c:181–204` — `seek(fdes, off, base)` — updates file offset (absolute, relative to current, or relative to EOF).
- `usr/sys/sys/sys2.c:209–254` — `link(target, linkname)` — increments nlink, appends directory entry. No atomicity; races possible.
- `usr/sys/sys/sys3.c:18–50` — `stat()/fstat()` — copies inode+timestamps to user struct; includes st_dev, st_ino, st_mode, st_nlink, st_uid, st_gid, st_rdev, st_size, st_atime, st_mtime, st_ctime.
- `usr/sys/sys/sys3.c:131–192` — `mount(fspec, freg, ronly)` — mounts block device on directory inode, reads superblock, stores in mount table.
- `usr/sys/sys/sys3.c:197–232` — `umount(fspec)` — flushes modified inodes, closes device, clears mount entry. Fails if any inode from that device is open.
- `usr/sys/sys/sys4.c:145–193` — `unlink(fname)` — zeroes directory entry inode number, decrements nlink. Race-prone; doesn't handle mounted-on files cleanly.

## Core Concepts (What They Did Well)

1. **Single-level indirection for small files, double/triple for large.** The 13-entry address array (11 direct, 1 indirect, 2 double-indirect) is a clean trade-off: 5KB files fit in one block of metadata, larger files scale via pointer chasing. Grover's `grover_objects` table should mirror this: store inodes inline for small objects, reference block-like chunks for larger content.

2. **Inode as identity, not content.** An inode's (dev, ino) tuple uniquely identifies a file across its lifetime, even after deletion (if nlink > 0). This is why VFS can hand inodes to agents as persistent handles. The inode cache (`iget`/`iput`) is the "always get the in-core copy" pattern that VFS's `_resolve_terminal()` mirrors.

3. **Lightweight mount mechanism.** Mount points are first-class path prefixes with a one-line entry in the mount table. No recursive mount evaluation, no capabilities, no per-mount plugins—just a device number and a superblock pointer. This is exactly what VFS's `add_mount()` and `_match_mount()` implement.

4. **Pathname resolution as sequential directory traversal.** `namei()` walks the path one component at a time, checking permission on every intermediate directory. It's single-threaded (no parallel lookups), but the logic is transparent: read directory block, scan entries, fetch next inode, repeat. No caching, no negative entry tracking. For agents, this sequential clarity is more important than performance.

5. **Permissions as (uid, gid, mode) triples, checked inline.** The `access()` call (in nami.c context) is 3 bits: read, write, execute. Execute on a directory means "can traverse". This is why Grover's `PermissionMap` (u/g/o prefix rules) is a good fit—mode bits are a solved problem; they're not the constraint.

6. **Reference counting for resource life cycles.** Every inode and file struct has a reference count. `iput()` is called on every path end; the last caller triggers cleanup (truncate, deallocate). Pipes are just files with a flag. This pattern scales to agents: every result with a file handle needs a matching release call, or cleanup is deferred.

7. **Sync as explicit operation.** `update()` (sync syscall) iterates all inodes and superblocks, flushing dirty ones. No implicit journal, no write barriers. For Grover's database backend, explicit `await session.commit()` mirrors this—make dirty state visible, not hidden.

## Anti-Patterns & Regrets

1. **No atomicity in directory operations.** `link()`, `unlink()`, and `creat()` all write directory entries and update inode metadata in separate calls. If a crash occurs between steps, the filesystem is left inconsistent. Later systems added journaling; Grover can avoid this by batching writes to the `grover_objects` table in a single transaction before the commit.

2. **TOCTOU races in pathname resolution.** `namei()` unlocks each inode before moving to the next, specifically to avoid deadlock. This opens races: between `namei()` returning a path and the syscall acting on it, the path can be unlinked or replaced. Modern systems use file descriptor caching; Grover should warn agents: *a `glob()` result is a snapshot, not a live handle*.

3. **Sticky bit semantics are poorly specified.** The `ISVTX` flag (01000) is set on executables to keep their text in swap on exit. Later BSD repurposed it for directory deletion rights (only owner can `unlink`). No comment in the code explains which semantics apply here. For Grover, reject sticky-bit-like corner cases; use explicit permission rules, not bit flags with dual meanings.

4. **Mode bits don't cover all access patterns.** What should `stat()` return for a character device's size? What does read/write permission mean for a block device? Unix punted to device drivers (`ioctl` chaos), which became unmaintainable. Grover's `kind` discriminator (file, directory, chunk, version, connection, api) is cleaner: each kind knows its own semantics.

5. **Inode numbers are reused.** Once an inode is deallocated, its number can be assigned to a new file. There's no generation counter. Agents holding old inode numbers can accidentally operate on newer files. Modern systems add 64-bit inodes + generation fields. Grover should use UUIDs or (dev, ino, version) triples where agents are involved.

6. **Pipes are files, but not really.** Pipes use the inode machinery but bypass normal read/write (`readp`/`writep`), have special rules (ESPIPE on seek), and their size field is overloaded (current fill level, not capacity). Agents will be confused. If Grover models pipes, make them a distinct object type, not a file-like hack.

7. **Global inode table with fixed size.** `iget()` scans `inode[NINODE]` linearly, panicking if full. This is a capacity cliff, not a graceful degrade. Grover's database backend should use per-session caches and auto-scale; don't mimic this limit.

8. **Read-only filesystems are half-supported.** The `s_ronly` flag prevents superblock updates and inode writes, but doesn't prevent `creat()` or `unlink()` from *attempting* the operation (they just fail partway through). No up-front `EROFS` check. For Grover, if a mount is read-only, the permission rules should reject writes immediately, not after partial updates.

## Implications for VFS (Implementation)

1. **Inode shape is (dev, number, in-core cache, dirty flags, reference count).** Grover's `VFSObject` model should include: `path` (identifies object), `kind` (type), `version_number` (generation), `size`, `detail` (extension-specific), `mtime`, `ctime`. The inode's 13-entry address array maps to: if `size <= block_size * 11`, store content inline in `grover_objects.content`; otherwise, allocate chunks and reference them by chunk_name in `detail`.

2. **Mount routing should use longest-prefix matching on absolute paths.** Grover's `_resolve_terminal()` already does this; the Unix approach confirms it's correct. Each mount binds one directory prefix to a filesystem. Paths under that prefix are rebased relative to the mount's root. No recursive mounts or relative mounts.

3. **Permissions are (path prefix → rule) not (inode → bits).** Unix mode bits apply per-file. Grover's `PermissionMap` applies per-path-prefix, which is more practical for agents: "everything under `/data/` is read-only" is one rule, not a bitmap on each inode. However, preserve the Unix semantics: check on every component traversal in `namei()`, not just the target. Grover's `access()` at-path-level is correct.

4. **Reference counting is essential for cleanup.** Every operation that returns a file handle (result entry) should pair with a release (via garbage collection or explicit close). `iput()` is the pattern: refcount--, allocate on last ref. For Grover, `VFSResult` entries are ephemeral (no explicit close), but underlying backends should maintain reference counts on database sessions to prevent resource leaks.

5. **Dirty flags (IUPD, IACC, ICHG) are per-inode, not per-block.** Unix batches updates: all modifications to a file set a flag, and `iupdat()` is called opportunistically (on `iput()`, or periodically by `sync()`). Grover should follow this: mark backends' ORM objects as dirty, then batch-commit in `_use_session()` context manager. Don't commit per-operation.

6. **Directory entries should be opaque to agents.** Unix stores (inode_number, name) in a directory. Agents shouldn't parse directory blocks. Grover's `ls()` returns `Entry` objects with kind/size/hash; agents work with these, not raw directory blocks. Hide the inode number; expose the normalized path.

7. **Seek is independent of read/write permissions.** Agents should be able to reposition a file handle without reading. In Grover, `seek()` is implicit (the agent asks for a byte range), but don't tie seek capability to read permission in the permission rules.

## Implications for FSP (Protocol)

1. **The minimal op set is: CRUD + navigation + search.** Unix proved over 50 years that this surface is sufficient: open/creat, read/write, unlink/delete, link (connections in Grover), stat, ls/tree, find/glob, grep. FSP exposes all of these. Don't add `chmod`, `chown`, `umask`, `access()`—they're OS-specific and agents don't need them. The `PermissionMap` is the agent-friendly answer.

2. **Error messages should include before/after context, not errno codes.** FSP's `FSPResult` has `ok`, `path`, `data`, `error`, `meta`. When an operation fails, include the path that failed, what the agent tried to do, and why. Unix returns a 2-digit errno; agents waste a turn probing "what went wrong". Follow the SWE-agent pattern: `"Cannot write /path/to/file: already exists (remove first with `delete`)".`

3. **Stat should include kind, size, and timestamps, not st_dev/st_ino.** Agents don't understand device numbers or inode identities. The `kind` (file, directory, chunk, version) tells them what operations are legal. Include `mtime`, `ctime`, but not `atime` (updating atime on read causes write amplification; agents don't care about access time).

4. **Glob and grep should cap results at ~50 entries, with guidance on refinement.** Unbounded searches flood the agent's context. If a glob or grep returns the cap, reply with: `"Glob returned 50 results (limit reached). Refine with --paths or --globs to narrow."` This mirrors SWE-agent's finding that agents succeed with bounded, predictable output.

5. **Paths should be absolute from the root of the namespace, not relative.** Unix allows `.` and `..` and `~`-expansion; FSP (and Grover) should flatten all paths to `/absolute/form`. Agents learn one path syntax this way. No relative paths, no magic prefixes.

6. **Write operations should return the written content (or a diff) in the response.** After `write()` or `edit()`, echo the affected lines with context. Agents then confirm the change without issuing a follow-up `read()`. This is the SWE-agent "echo the edited region" principle.

7. **Mount points are namespace prefixes, not capabilities.** FSP doesn't expose `mount()`/`umount()` syscalls. Instead, the server initializes mounts at startup. Agents see a unified namespace; which backend serves `/data/` vs. `/search/` is opaque. This simplifies the protocol: no "mount a new database" op, no negotiation. Mounts are admin-time, not runtime.

8. **Connection objects (Grover's alternative to symlinks) should be first-class in the protocol.** Unix's `link()` increments nlink; FSP should have `mkconn(src, target, type)` that creates an edge in the graph. Agents reason about connections as metadata, not indirection. The `type` field allows semantic differentiation (e.g., "references", "related_to", "depends_on").

## Open Questions

1. **When should `mtime` be updated—on every write, or on explicit flush?** Unix updates on each `write()`. Grover batches via `iupdat()`. For agents, stale `mtime` could lead to wrong decisions ("is this up-to-date?"). Clarify: agents should ask for `mtime`, not assume it's current.

2. **How deep should path normalization go?** Unix allows `//` (carve-out, not flattened in all systems), `.` and `..` (resolved by `namei()`), and symlinks (not in early Unix, added later). Grover flattens `//` explicitly. Should the protocol warn agents if they use `.` or `..`? Or silently resolve them? Document.

3. **What's the contract on error atomicity?** If a batch write (e.g., `write(objects=[...])`) partially succeeds, should Grover roll back, or return partial success with per-object errors? Unix has no batch write; each file is independent. Document whether Grover is all-or-nothing or best-effort per-object.

4. **Should agents be able to query mount points?** FSP doesn't expose `/proc/mounts`-like views. Agents might want to know which paths are read-only, or which mount serves which prefix. Consider a read-only `list_mounts()` that returns `[{prefix, backend_type, readonly}]`.

5. **Is `seek()` needed, or should `read()` take a byte range?** Unix `seek()` changes the file pointer, then `read()` uses it. Agents would prefer `read(path, start=0, end=100)` (no state). FSP should clarify if `seek()` is available, or if byte-range reads are the only way.

6. **How do agents detect when they've reached the "end" of a directory or search results?** Unix `readdir()` returns entries until EOF. Grover's `ls()` returns all entries (bounded). If agents expect pagination, is there a `max_count` parameter, or do they truncate results themselves? Clarify in CLI documentation.

---

## Summary

Research V7 Unix achieved durability through minimal, composable operations (open/read/write/unlink/stat/mount) backed by transparent data structures (inode + directory tree). The filesystem's 650-line kernel proved that simplicity, not sophistication, is the key to long-lived systems. Grover's VFS borrows the architecture (mount routing, inode-like reference counting, permission rules per-path), while learning the anti-patterns (avoid TOCTOU races, batch writes, clarify atomicity). FSP translates this to an agent-friendly protocol: bounded results, explicit error context, unified absolute paths, and no magic (no symlinks, no `chmod`, no inode numbers exposed). The "everything is a file" pitch to an LLM agent only works if the filesystem behaves like Unix—30 syscalls, one namespace, clear error semantics. This memo grounds that promise in 50 years of proof.

