# Study 02 — What a "real" filesystem API minimally is: the protocol shapes

- **Date:** 2026-10-23
- **Brief:** `00-brief.md` in this directory.
- **Repos (read-only, refreshed per `refresh.log`):**
  - `plan9port` master `1f1396913f` (2026-10-20) — Plan 9 Foundation / Russ Cox licence (MIT-style).
  - `libfuse` master `fe66006fbb` (2026-10-15) — LGPL-2.1 (library), study only.
  - `WASI` main `463701e0f6` (2026-10-13) — W3C Community Contributor licence; preview1 read from branch `origin/wasi-0.1` at `fae981b` (2025-12-17).
  - `sqlite` master `3d17c3f9e9` (2026-08-04) — public domain.
  - `pjdfstest` master `85a8aea9e6` (2026-08-07) — BSD-2-Clause.
- **Labels:** READ = a file at the commit above; EXECUTED = run here; INFERRED = my conclusion from what was read.
- **Nothing was copied.** Every design is described in my own words and cited by file:line.

---

## 1. 9P — a fid, a walk, ranged read and write, and a stat record

**The message set, exactly** (READ, `plan9port/include/fcall.h:80-114`): `Tversion/Rversion`, `Tauth/Rauth`, `Tattach/Rattach`, `Terror` (marked "illegal"; only `Rerror` is sent), `Tflush/Rflush`, `Twalk/Rwalk`, `Topen/Ropen`, `Tcreate/Rcreate`, `Tread/Rread`, `Twrite/Rwrite`, `Tclunk/Rclunk`, `Tremove/Rremove`, `Tstat/Rstat`, `Twstat/Rwstat`. That is thirteen request kinds. Plan 9 from User Space adds one non-standard pair, `Topenfd/Ropenfd` (`fcall.h:112-113`; `man/man9/openfd.9p`), which hands back a Unix file descriptor instead of a fid. The server dispatch in `src/lib9p/srv.c:730-742` is exactly this switch and nothing else.

**The fid model** (READ, `man/man9/0intro.9p:343-357, 388-399`): a fid is a client-chosen 32-bit number naming a "current file" on the server. It is *not* an open-file handle; a fid names any file being examined — a directory being walked, a file being stat'ed. `Twalk` takes a fid and a list of up to sixteen name elements (`walk.9p:138`), resolves them elementwise, and binds the result to `newfid`; the source fid must not already be open for I/O (`walk.9p:37-41`). Only after a walk does `Topen` prepare the fid for I/O with a mode (`open.9p:30-32`). `Tread` and `Twrite` carry `fid`, an 8-byte `offset` and a 4-byte `count` (`read.9p:9-23`) — every I/O is positional; there is no server-side file position and therefore **no seek message**: the client library's `fsseek` only changes a number in the client and "does not generate a message" (`read.9p:119-126`). `Tclunk` forgets the fid; it succeeds even when the server answers an error (`clunk.9p:31-34`). `Tremove` is defined as "a clunk with the side effect of removing the file if permissions allow" (`remove.9p:30-31`); whether other fids open on the same file keep working is left implementation-defined, and Plan 9's own servers cut them off (`remove.9p:33-40`). `Tstat` returns one stat record; `Twstat` sends one back with "don't touch" values for fields the client leaves alone (`stat.9p:229-243`).

**Directories are read with `Tread`** (READ, `read.9p:57-77`): a read on a directory fid returns an integral number of stat records, one per entry, in the same byte format `Tstat` uses. The offset must be 0 or exactly the previous offset plus the previous count — "seeking other than to the beginning is illegal in a directory". `lib9p` enforces this literally (`src/lib9p/srv.c:479-481, 509`) and keeps a per-fid cursor (`dirindex`) so a directory can be paged with repeated reads (`src/lib9p/dirread.c:15-18, 37`).

**Rename is `Twstat` with a new `name`** (READ, `stat.9p:185-190`): "the name can be changed by anyone with write permission in the parent directory; it is an error to change the name to that of an existing file". The `name` field of a stat record is one element, not a path (`stat.9p:69-72`), so a rename cannot cross directories — same-directory only, and never a replace (INFERRED from the field shape plus the "existing file" rule; `lib9p` additionally refuses changes to type, dev, qid and muid, `srv.c:665-681`). Cross-directory move in Plan 9 is a copy-then-remove done by the client.

**What 9P deliberately has no message for** (READ of the complete enum above): no search or query, no hard or symbolic link, no seek, no fsync/flush-to-disk (`Tflush` cancels an outstanding request, `flush.9p`; durability is the server's business), no locking beyond `DMEXCL` on open (`open.9p:79-84`), no xattr, no ioctl. Everything not in the thirteen messages is expressed as a file.

**Non-file operations go through control files** (READ): acme's per-window filesystem declares a `ctl` file (`src/cmd/acme/fsys.c:85`) and its write handler parses newline-separated text commands — `lock`, `unlock`, `clean`, `dirty`, `show`, `name <f>`, `font <f>`, `dump`, `delete`, `get`, `put`, `dot=addr`, `addr=dot`, `limit=addr`, `mark`, `menu` (`src/cmd/acme/xfid.c:622-814`). The manual states the convention: "Text messages may be written to ctl to affect the window. Each message is terminated by a newline and multiple messages may be sent in a single write" (`man/man4/acme.4:191-195`). A verb is a line written to a file; its reply, if any, is read back from a sibling file.

**Lesson for vfs:** 9P shows that a complete file protocol is thirteen messages built on one idea — a client-named handle that is *resolved first* (walk), then opened, then read or written by explicit offset and count — and that every operation not in that set, including anything like search, is a text command written to a control file rather than a new message.

---

## 2. libfuse — two APIs because the kernel speaks inodes and programs speak paths

**Why two APIs** (READ, `libfuse/doc/mainpage.dox:19-29`): the high-level API is synchronous and lets callbacks "work with file names and paths instead of inodes", returning when the callback returns; the low-level API is asynchronous, "must work with inodes", and replies explicitly through `fuse_reply_*`. The kernel protocol is inode-shaped (`lookup(parent, name) -> inode`, then every call by inode, with `forget(ino, nlookup)` reference counting, `include/fuse_lowlevel.h:278-290`), so the high-level library keeps its own name tree — `struct node` with `parent`, `name`, `nodeid`, `nlookup`, `open_count` (`lib/fuse.c:137-149`) — and rebuilds a path for each call (`lib/fuse.c:1212 get_path`), holding per-path locks to keep rename and unlink coherent (`lib/fuse.c:972-1090`). The price of path-shaped callbacks is that the library, not the backend, owns the inode-to-path map. The two hello examples make the shape difference concrete: `example/hello.c:138-142` registers five path callbacks and `read` returns a byte count (`hello.c:126-134`); `example/hello_ll.c:221-229` needs `lookup` as well and answers with `fuse_reply_attr`, `fuse_reply_entry`, `fuse_reply_buf` (`hello_ll.c:81-130`).

**The `fuse_operations` members** (READ, `include/fuse.h:360-892`), marked for a whole-file database backend:

| Member (fuse.h line) | Class | Note |
|---|---|---|
| `getattr` 372, `readlink` 382, `mkdir` 398, `unlink` 401, `rmdir` 404, `statfs` 527, `access` 671, `init` 652, `destroy` 660 | **trivial** | a row lookup, an insert, a delete; `readlink` only if symlinks exist |
| `mknod` 390, `symlink` 407, `link` 421, `chmod` 428, `chown` 438, `setxattr`..`removexattr` 581-590, `bmap` 739, `ioctl` 742/761, `poll` 780, `lock` 715, `flock` 829, `fallocate` 839, `lseek` 863, `statx` 873, `syncfs` 892 | **optional / refuse** | ENOSYS is a valid answer; mode bits and links are the backend's choice |
| `open` 497, `create` 683, `read` 508, `write` 520, `read_buf` 809, `write_buf` 792, `flush` 557, `release` 571, `fsync` 578, `opendir` 600, `readdir` 624, `releasedir` 632, `fsyncdir` 642 | **handles** | `fuse_file_info.fh` is a backend-chosen 64-bit token set in `open`/`create`/`opendir` and returned on every later call (`fuse_common.h:122-125`); "filesystem may also implement stateless file I/O and not store anything in fi->fh" (`fuse.h:481-483`) |
| `rename` 418 | **POSIX to emulate** | `RENAME_NOREPLACE` means refuse if target exists; `RENAME_EXCHANGE` means swap both atomically, "both must exist and neither may be deleted" (`fuse.h:410-417`); plain rename replaces |
| `unlink` of an open file | **POSIX to emulate** | the high-level library hides it for you: unless `hard_remove` is set, an open file being unlinked is renamed to `.fuse_hiddenXXXX` and really removed on last release (`lib/fuse.c:2426, 2447, 3017-3018`; the same for a rename target, `3104-3106`); with `hard_remove`, reads and writes on the unlinked fd return ENOENT (`fuse.h:185-191`) |
| `truncate` 448, `utimens` 730 | **POSIX to emulate** | both arrive with `fi` NULL when the file is not open, so they are path-keyed; `truncate` to a size is a byte-range operation on the body |
| `readdir` 624 | **POSIX to emulate** | two modes: ignore the offset and return the whole directory in one call, or track per-entry offsets and page (`fuse.h:607-619`) |
| `flush` 557, `fsync` 578 | **POSIX to emulate** | `flush` fires once per close of a descriptor — possibly many times per open, possibly never, errors may be dropped (`fuse.h:549-556`); `release` fires exactly once per open and its return value is ignored (`fuse.h:559-570`) — so a write-back-at-close backend must do the durable write in `flush` *and* tolerate repeats |

**`direct_io` vs the page cache** (READ, `include/fuse_common.h:62-69, 110-115, 296-301`): by default the kernel page cache sits between the program and the backend — reads are served from cached pages and `read` callbacks arrive page-aligned; the cache is dropped on each open unless `keep_cache` is set. `direct_io`, set per open by the backend, bypasses the cache: every `read`/`write` syscall reaches the backend with the caller's own offset and size, and the file's `st_size` does not have to be truthful (`doc/README.stream:17-39` documents a stream file that *requires* `direct_io` because its size is unknown). The 2026 changelog spells out the trade: without auto-invalidation, "to see changes made outside the kernel ... set `fi->direct_io` in `open()`" (`doc/ChangeLog-API.rst:33-39`). For a whole-file backend it matters because the kernel will otherwise issue many small page-sized reads of a body the backend fetched whole, and will cache a version the database may have moved past.

**Lesson for vfs:** FUSE's path API survives only because the library owns a private inode-to-path tree and a hidden-rename trick; the real protocol underneath is handle-and-inode shaped, and the three POSIX behaviours a database must emulate are rename-with-flags, unlink-of-an-open-file, and the flush/release pair that decides when a whole-file write-back is durable.

---

## 3. WASI — preview1's fd-and-rights table versus 0.2/0.3's descriptor resource

**Preview1** (READ, `origin/wasi-0.1:preview1/docs.md`): forty-six functions, of which the filesystem ones are `fd_advise fd_allocate fd_close fd_datasync fd_fdstat_get fd_fdstat_set_flags fd_fdstat_set_rights fd_filestat_get fd_filestat_set_size fd_filestat_set_times fd_pread fd_prestat_get fd_prestat_dir_name fd_pwrite fd_read fd_readdir fd_renumber fd_seek fd_sync fd_tell fd_write path_create_directory path_filestat_get path_filestat_set_times path_link path_open path_readlink path_remove_directory path_rename path_symlink path_unlink_file`. `path_open(fd, dirflags, path, oflags, fs_rights_base, fs_rights_inheriting, fdflags) -> fd` (docs.md:2141) carries two 64-bit `rights` bitmaps (docs.md:288-292, thirty named rights) — capability bits per descriptor. `fd_read(fd, iovs)` is `readv` with a kernel-side position (docs.md:1818-1820) beside `fd_pread(fd, iovs, offset)` (docs.md:1708) and `fd_seek`/`fd_tell` (docs.md:1913-1915). `fd_readdir(fd, buf, buf_len, cookie)` fills a byte buffer with `dirent` records each carrying `d_next`, the cookie to resume from, "potentially truncating the last directory entry" so the caller can grow its buffer (docs.md:1844-1853, 606). `path_rename(fd, old, new_fd, new)` is `renameat` (docs.md:2249-2251); `path_link` is `linkat` (docs.md:2107-2109).

**0.2 / 0.3** (READ, `proposals/filesystem/wit/types.wit`, package `wasi:filesystem@0.3.2` on main; every function is `@since(version = 0.3.0)` because 0.3 re-based the API on component-model streams — 0.2's `read-via-stream` returned an `input-stream`; the shapes below are the same): a `descriptor` is a resource (types.wit:311). Reading is `read-via-stream(offset)` — "similar to pread" — and writing `write-via-stream(offset)` / `append-via-stream` (types.wit:312-363); there is **no seek, no tell, no position** on a descriptor. `stat`/`stat-at` return `descriptor-stat` and explicitly "do not return device and inode information" (types.wit:462-472); `is-same-object` replaces the `st_dev`/`st_ino` comparison (types.wit:616-622); `metadata-hash` is a "hash of the last-modification timestamp and file size" that may include a secret, with properties that are "encouraged" but "none ... required" (types.wit:623-644). `open-at(path-flags, path, open-flags, flags)` keeps four open flags — `create`, `directory`, `exclusive`, `truncate` (types.wit:153-163) — and one path flag, `symlink-follow` (types.wit:145-149); the thirty rights became four `descriptor-flags` of which `mutate-directory` is the write capability on a directory (types.wit:74-112). `read-directory()` returns a `stream<directory-entry>` of `{type, name}` — no cookie, no inode, no buffer-packing (types.wit:182-189, 442). `rename-at`, `link-at`, `symlink-at`, `unlink-file-at`, `remove-directory-at`, `create-directory-at`, `set-size`, `set-times`, `sync`, `sync-data`, `advise` complete the set (types.wit:369-610). Dropped relative to POSIX: `fd_seek`/`fd_tell`, `fd_renumber`, the rights bitmaps, inode and device numbers, `chmod`/`chown` (never in WASI), `fd_allocate` (was in preview1, gone). Added: streams, `metadata-hash`, `is-same-object`. The header gives the why: the API "prioritizes compatibility over portability" — paths may be case-folded, "deleting (unlinking) a file may fail if there are other file descriptors open", atomicity under concurrent writers is unspecified, and "users that need well-defined, portable semantics should use a key-value store or a database instead" (types.wit:22-34). All paths are relative to a descriptor; a leading `/` or an escape via `..` fails with `not-permitted` (types.wit:12-17).

**What vfs must serve for CPython** (READ of the vfs memo `2026-10-23-wasi-python-0-1-0-over-vfs-the-mount-and-the-tool-door.md:78-84`, mapping INFERRED): wasi-python's mount provider has eight methods — `stat`, `list`, `read`, `write`, `mkdir`, `remove`, `rmdir`, `rename` — and the runner stages a file whole at `path_open` and hands it back whole at `fd_close`/`fd_sync`/run end (memo row "Spec 169b §b4–b5"). So preview1's `path_filestat_get`/`fd_filestat_get` → `stat`; `fd_readdir` → `list` (the runner pages the cookie); `path_open` + `fd_read`/`fd_pread`/`fd_seek` → one `read` of the whole body; `fd_write`/`fd_pwrite` + `fd_filestat_set_size` + `fd_close`/`fd_sync` → one `write` of the whole body; `path_create_directory` → `mkdir`; `path_unlink_file` → `remove`; `path_remove_directory` → `rmdir`; `path_rename` → `rename`. `path_link`, `path_symlink`, `path_readlink`, `fd_fdstat_set_rights`, `fd_advise`, `fd_allocate` need no provider method. The memo's experiment 2 found the one semantic gap in this mapping: `os.replace` onto an existing file got `FileExistsError` because `move` refuses where POSIX replaces (memo:167-171).

**Lesson for vfs:** the newest filesystem standard already moved to vfs's position — no seek, no inode numbers, reads and writes by explicit offset, a relative-path capability per directory, and a written warning that a database is where well-defined semantics live — and CPython runs on eight whole-file provider calls, so a store needs ranged reads only when it wants to stop staging bodies whole.

---

## 4. SQLite's VFS — the smallest OS interface a storage engine wrote for itself

**`sqlite3_io_methods`** (READ, `sqlite/src/sqlite.h.in:854-876`): `xClose`, `xRead(file, buf, iAmt, iOfst)`, `xWrite(file, buf, iAmt, iOfst)`, `xTruncate(size)`, `xSync(flags)`, `xFileSize(*pSize)`, `xLock(level)`, `xUnlock(level)`, `xCheckReservedLock`, `xFileControl(op, arg)`, `xSectorSize`, `xDeviceCharacteristics`; version 2 adds `xShmMap`/`xShmLock`/`xShmBarrier`/`xShmUnmap` for WAL; version 3 adds `xFetch`/`xUnfetch` for memory-mapped pages. Every read and write is positional — there is no file position and no seek. A short read must zero-fill the rest of the buffer and return `SQLITE_IOERR_SHORT_READ`, or "will eventually lead to database corruption" (sqlite.h.in:847-851).

**`sqlite3_vfs`** (READ, `sqlite.h.in:1513-1545`): `iVersion`, `szOsFile`, `mxPathname`, `zName`, then `xOpen(name, file, flags, *outFlags)`, `xDelete(name, syncDir)`, `xAccess(name, flags, *out)`, `xFullPathname(name, nOut, out)`, the four `xDl*` loader hooks, `xRandomness`, `xSleep`, `xCurrentTime`, `xGetLastError`, `xCurrentTimeInt64`, and three `x*SystemCall` test hooks. `xOpen` flags carry the file's *role* (`MAIN_DB`, `TEMP_DB`, `WAL`, journals) plus `DELETEONCLOSE` and `EXCLUSIVE`+`CREATE` for O_EXCL semantics (sqlite.h.in:1398-1447, 606-607). `xAccess` answers only "exists" or "readable and writable" (sqlite.h.in:1462-1472).

**Deliberately absent** (INFERRED from the complete struct listings): no directory creation or listing, no rename, no link, no stat beyond size, no mode bits or times, no handles other than the opened `sqlite3_file`. Directories exist only implicitly: `unixDelete` opens the parent directory to `fsync` it when `syncDir` is set (`src/os_unix.c:6829-6850`), and the journal is a sibling name derived from `xFullPathname` plus a suffix (sqlite.h.in:1386). The engine needs *one* file per role, found by name, read and written by range, truncated, synced, and locked — nothing a hierarchy would add.

**`memdb.c` over one growable buffer** (READ, `src/memdb.c:13-14, 71-81`): "a database is held as a contiguous block of memory" — a `MemStore` with `sz` (logical size), `szAlloc` (allocation), `szMax` (cap), `aData`, a mutex, and a refcount. `memdbRead` copies the range out, and when the range runs past `sz` it zero-fills and returns the short-read code exactly as the contract demands (`memdb.c:252-269`). `memdbWrite` grows the allocation through `memdbEnlarge` (refusing with `SQLITE_FULL` past `szMax`), zero-fills any gap between the old `sz` and the write offset, and bumps `sz` (`memdb.c:274-330`). `memdbTruncate` only ever shrinks `sz` — growing is reported as corruption (`memdb.c:331-347`). `xDelete` always fails and `xAccess` always answers "no such file" because nothing exists on disk (`memdb.c:628-656`). Ranged I/O over a single whole buffer is the whole implementation; `sqlite3_serialize`/`sqlite3_deserialize` move that buffer in and out as one blob.

**Lesson for vfs:** a serious engine's whole OS contract is ranged read/write/truncate/sync/lock on a file found by name — no directories, no rename, no listing — and `memdb.c` proves that contract can be served over one whole in-memory buffer, which is exactly the shape of a `content`/`data` column with offset arithmetic in front of it.

---

## 5. pjdfstest — which POSIX families a link-less, mode-less, whole-file store can pass

The suite is one directory per syscall (READ, `pjdfstest/tests/`): `chflags chmod chown ftruncate granular link mkdir mkfifo mknod open posix_fallocate rename rmdir symlink truncate unlink utimensat` (EXECUTED count: rename 25, unlink 15, open 27, mkdir 13, rmdir 16, truncate 15, chmod 13, link 18, symlink 13). Most files in each family pin an errno (`ENAMETOOLONG`, `ENOENT`, `ENOTDIR`, `EACCES`, `ELOOP`, `EROFS`, `EPERM` on immutable flags, `EFAULT`); the semantic pins are a minority. Verdicts are INFERRED against the shape in the brief: SQL rows, tombstones, whole bodies, no links, no mode bits, a permission ladder instead of `rwx`.

| Family (file) | Semantics pinned | vfs shape |
|---|---|---|
| `rename/00.t:24-33` | rename keeps the inode and link count; `ENOENT` at the old name | pass by construction for the name move; the inode/nlink assertion needs a stable row identity surfaced in `stat` |
| **`rename/23.t:5, 24-31`** | **rename onto an existing file succeeds and the old target's link count drops** (the rename-over-existing-file pin) | pass with emulation: `move` must replace, not refuse (today it answers `vfs.exists`, memo:167-171); the nlink part fails by design |
| `rename/14.t:4`, `rename/13.t:4`, `rename/20.t:4` | `EISDIR` when target is a directory and source is not; `ENOTDIR` the other way; `EEXIST`/`ENOTEMPTY` when target is a non-empty directory | pass with emulation: kind checks before the move |
| `rename/18.t:4`, `rename/19.t:4`, `rename/24.t:4` | `EINVAL` renaming into one's own subtree or `.`/`..`; a moved directory's `..` is updated | pass with emulation (subtree check); `..` is a path fact, trivial |
| `rename/21.t:4`, `rename/04-10`, `unlink/06-11`, `mkdir/06`, `rmdir/09-11` | `EACCES`/`EPERM` from `rwx` bits, sticky bits, immutable flags, uid ownership | fail by design — no mode bits or uids; the ladder refuses differently and would have to be mapped onto `EACCES` |
| **`unlink/14.t:5, 19-29`** | **an open file is not freed by unlink: `fstat` on the fd still works and reads/writes through it still succeed** (the unlink-of-open-file pin) | pass with emulation only if the staged body belongs to the open handle, not the path (FUSE's hidden-rename trick, §2); fails if the handle re-resolves the path per call |
| `unlink/00.t` | unlink removes regular files, symlinks, fifos and sockets | pass for regular files; fifos, sockets and symlinks fail by design |
| `open/00`, `open/22` ("EEXIST when O_CREAT and O_EXCL were specified and the file exists"), `open/26` ("open can create files with 0000 mode") | create-if-absent, exclusive create, mode at create | pass with emulation for create and `O_EXCL`; mode fails by design |
| `truncate/00` ("decrease/increase file size"), `ftruncate/*` | truncate shrinks and zero-extends; `EISDIR` on a directory; `EINVAL` negative; `EFBIG` | pass with emulation: a whole-body rewrite with zero padding |
| `mkdir/00`, `mkdir/10` (`EEXIST`), `rmdir/00`, `rmdir/06` (`ENOTEMPTY`), `rmdir/13` (`EBUSY` on a mount point) | create, exists, non-empty refusal, mount point busy | pass by construction (vfs has mounts, so `EBUSY` is natural) |
| `link/00` ("link creates hardlinks"), `link/10` (`EEXIST`), `link/05` (`EMLINK`), `symlink/00`, `symlink/08` (`EEXIST`) | hard and symbolic links, counts | fail by design — vfs has edges, not links; `mkedge` is not `link` |
| `chmod/00`, `chmod/12` (SUID/SGID), `chown/*`, `chflags/*` | mode bits, setuid clearing, ownership, immutable flags | fail by design |
| `utimensat/*` | set atime/mtime, `UTIME_NOW`/`UTIME_OMIT` | pass with emulation only if `stat` exposes writable times; vfs's times are version facts |
| `*/01-03` across every family | `ENAMETOOLONG` at `PATH_MAX`/`NAME_MAX`, `ENOTDIR` on a file in the prefix, `ENOENT` | pass with emulation: the path kernel already refuses bad shapes; the limits must be declared numbers |

**Lesson for vfs:** pjdfstest's semantic pins fall into three bins — name-tree rules (pass or emulate cheaply), the two handle-coupled rules rename-replace and unlink-while-open (emulable only if a handle owns its staged body), and the mode/uid/link families (fail by design and should be declared so, not approximated).

---

## 6. Synthesis — the operation set shared by all four protocols

Columns: 9P (`fcall.h`), FUSE high-level (`fuse.h`), WASI 0.2/0.3 (`types.wit`), SQLite VFS (`sqlite.h.in`). READ for each cell; the "shared" column is INFERRED.

| Operation | 9P | FUSE high-level | WASI 0.3 | SQLite VFS | Shared by all four |
|---|---|---|---|---|---|
| resolve a name | `Twalk` | `getattr` (library `lookup`) | `open-at`/`stat-at` relative to a descriptor | `xFullPathname` + `xAccess` | yes |
| stat / size | `Tstat` | `getattr` | `stat` | `xFileSize` (+ `xAccess` exists) | yes (size only in SQLite) |
| open a handle | `Topen` | `open`/`create` → `fi->fh` | `open-at` → `descriptor` | `xOpen` → `sqlite3_file` | yes |
| ranged read | `Tread(offset,count)` | `read(buf,size,off)` | `read-via-stream(offset)` | `xRead(buf,iAmt,iOfst)` | **yes — every one is positional** |
| ranged write | `Twrite(offset,count)` | `write(buf,size,off)` | `write-via-stream(offset)`, `append-via-stream` | `xWrite(buf,iAmt,iOfst)` | yes |
| truncate | `Twstat` length | `truncate` | `set-size` | `xTruncate` | yes |
| close | `Tclunk` | `flush`+`release` | drop the resource | `xClose` | yes |
| create a file | `Tcreate` | `create`/`mknod` | `open-at` with `create`(+`exclusive`) | `xOpen` `CREATE`(+`EXCLUSIVE`) | yes |
| delete a file | `Tremove` | `unlink` | `unlink-file-at` | `xDelete` | yes |
| seek / position | none | none (`lseek` optional, for holes) | none | none | **none — absent everywhere** |
| sync | none (`Tflush` cancels) | `fsync`, `fsyncdir` | `sync`, `sync-data` | `xSync` | three of four |
| lock | `DMEXCL` on open | `lock`, `flock` | none | `xLock`/`xUnlock` | three of four |
| mkdir / rmdir | `Tcreate` `DMDIR` / `Tremove` | `mkdir` / `rmdir` | `create-directory-at` / `remove-directory-at` | none | three of four |
| list a directory | `Tread` on a dir fid (stat records, offset-chained) | `readdir` (offset or whole) | `read-directory` (stream, no cookie) | none | three of four |
| rename | `Twstat` name, same dir, never replace | `rename(flags)`: replace, `NOREPLACE`, `EXCHANGE` | `rename-at` | none | three of four, three different contracts |
| set times / mode | `Twstat` | `utimens`, `chmod`, `chown` | `set-times` | none | mode: two of four |
| hard / sym link | none | `link`, `symlink`, `readlink` | `link-at`, `symlink-at`, `readlink-at` | none | two of four |
| content identity | qid version | `st_ino` | `metadata-hash`, `is-same-object` | none | — |
| out-of-band control | `ctl` file writes | `ioctl` | none | `xFileControl` | three of four |
| search / query | none | none | none | none | **none — absent everywhere** |

**The shared core is nine operations:** resolve, stat, open, ranged read, ranged write, truncate, close, create, delete. Sync, lock, mkdir/rmdir, list and rename are in three of four.

**Against vfs's verbs** (READ, `src/vfs/base.py:879-1651`: `read stat ls tree write edit delete restore sweep mkdir mkedge rmedge move copy glob grep glean graph run grant revoke grants posture add_member remove_member`, plus `bind`/`add_mount` and `locate`):

- *vfs lacks, from the shared core:* an **open handle** and **close** (every verb re-resolves the path; nothing owns a staged body, which is what the `unlink/14.t` and rename-replace pins turn on); **ranged read and write by offset and count** (bodies are whole); **truncate** (only as a whole rewrite); and from the three-of-four tier: **sync** as an explicit durability point (a write commits or it does not), **lock** (no `DMEXCL`/advisory lock), **rename-replace** and **`RENAME_EXCHANGE`** contracts (`move` refuses an existing target), and a **directory cursor** (`ls` returns everything; 9P chains offsets, FUSE offers offsets, preview1 cookies). Mode bits, uids, links and symlinks are absent too, but §5 shows they are absent by design.
- *vfs has, that none of the four protocols has:* **search verbs** (`glob`, `grep`, `glean`, `graph`) — every protocol studied has zero query messages; **`tree`** (recursive listing in one call); **`edit`** (search-and-replace as a server-side verb); **`copy`** (only FUSE's optional `copy_file_range` comes close); **versions** minted by every write and a **trash** (`restore`, `sweep`); a **permission ladder** with its own verbs (`grant`, `revoke`, `grants`, `posture`, members) where the protocols carry only mode bits or rights bitmaps on a descriptor; **edges** (`mkedge`, `rmedge`, `graph`) distinct from links; **batched multi-path calls** (10,000 rows in one `write`/`read`; every protocol is one object per message); **`run`**; and a **classified `Result` envelope** where every protocol returns one errno-shaped code.

**Lesson for vfs:** the four protocols agree on a nine-operation handle-and-range core and agree equally that search, batches, versions and a trash are *not* filesystem operations — vfs's extra verbs are the part no file protocol would absorb, and its missing ones are exactly the handle, the byte range and the rename-replace contract.

---

## Design facts for the synthesis

1. READ — 9P is thirteen request messages; a fid is resolved by `Twalk` before `Topen`, and all I/O is `Tread`/`Twrite` with an explicit 8-byte offset and 4-byte count (`fcall.h:80-114`, `read.9p:9-23`).
2. READ — None of 9P, WASI 0.3 or the SQLite VFS has a seek; a file position exists only in the client (`read.9p:119-126`, `types.wit:312-363`, `sqlite.h.in:854-876`).
3. READ — 9P reads a directory as offset-chained stat records through the same `Tread`; the offset must continue the previous read (`read.9p:57-77`, `lib9p/srv.c:479-481`).
4. READ — 9P rename is `Twstat` with a one-element name, same directory, error on an existing target; cross-directory move is client-side copy-then-remove (`stat.9p:69-72, 185-190`).
5. READ — Every non-file operation in Plan 9 is a newline-terminated text command written to a `ctl` file (`acme/xfid.c:622-814`, `acme.4:191-195`).
6. READ — FUSE's path-shaped API is a library layer over an inode protocol: the library keeps its own name tree and hides unlink-of-an-open-file by renaming to `.fuse_hidden*` (`lib/fuse.c:137-149, 2426, 3017-3018`); `flush` may fire many times or never while `release` fires exactly once with its result ignored (`fuse.h:549-570`).
7. READ — FUSE `rename` carries `RENAME_NOREPLACE` and `RENAME_EXCHANGE`; plain rename replaces (`fuse.h:410-417`); `direct_io` per open bypasses the page cache so each syscall reaches the backend with the caller's offset and size (`fuse_common.h:62-69, 296-301`).
8. READ — WASI 0.3 dropped rights bitmaps, seek, inode and device numbers, and `chmod`; it added `metadata-hash` and `is-same-object`, and its header says that well-defined portable semantics belong in "a key-value store or a database instead" (`types.wit:22-34, 462-472, 616-644`).
9. READ — The SQLite VFS has no directory, rename, list or stat beyond size; `memdb.c` serves the whole contract as ranged copies over one growable buffer with zero-filled short reads (`sqlite.h.in:1513-1545`, `memdb.c:252-347`).
10. INFERRED — pjdfstest's handle-coupled pins (`rename/23.t` replace-over-existing, `unlink/14.t` I/O after unlink) are passable only when an open handle owns its staged body; the mode, uid and link families fail by design for a row-backed, link-less store and should be declared unsupported rather than approximated.
