# Study 06 — Production filesystems whose metadata lives in SQL: seaweedfs and juicefs

- **Date:** 2026-10-23
- **Brief:** `00-brief.md` (filesystem-shaped API for vfs)
- **Repos (read-only, refreshed per `refresh.log`, both clean — EXECUTED `git status`):**
  - `~/Git/Repos/seaweedfs` — `master` `6c87fb70f9` (2026-10-23), Apache-2.0
  - `~/Git/Repos/juicefs` — `main` `b2a3be78a0` (2026-10-23), Apache-2.0
- **Labels:** READ = a file at that commit; EXECUTED = ran here; INFERRED = my reading.
- **Rule:** nothing copied; designs described and cited as `file:line`.

Both projects put *file metadata* in SQL and *bodies* in object/volume storage.
They made opposite keying choices — seaweedfs keys rows by **path**, juicefs by
**inode** — so they are a clean A/B on every question below.

---

## 1. The store interface

**seaweedfs `FilerStore`** (READ `weed/filer/filerstore.go:22-45`), exactly:
`GetName`, `Initialize`, `InsertEntry`, `UpdateEntry`, `FindEntry(FullPath)`,
`DeleteEntry(FullPath)`, `DeleteFolderChildren(FullPath)`,
`ListDirectoryEntries(dir, startFileName, includeStartFile, limit, eachEntryFunc)`,
`ListDirectoryPrefixedEntries(... prefix ...)`, `BeginTransaction`,
`CommitTransaction`, `RollbackTransaction`, `KvPut`, `KvGet`, `KvDelete`, `Shutdown`.
Optional capabilities: `EntryScanner.ScanEntries` (snapshot walk, `:59-61`),
`BucketAware` (`:63-67`), `Debuggable`. That is the whole store contract:
**five row verbs, one cursor listing, one children-sweep, a transaction, a KV
side table.** Everything else is composed above it:

- *Create* (`filer.go:447-537`): `FindEntry` on the full path, then
  `InsertEntry` or `UpdateEntry`; then `ensureParentDirectoryEntry` walks the
  path components upward and `FindEntry`/inserts each missing ancestor
  (`:539-560`). Parents are created *after* the child on purpose (`:497-499`).
- *Lookup* is one row: there is no component walk, because the path is the key.
- *Recursive delete* (`filer_delete_entry.go:196-286`): page the directory with
  `ListDirectoryEntries` at `PaginationSize = 1024` (`filer.go:40`), recurse into
  subdirectories, collect chunks, then one `DeleteFolderChildren` per directory
  (`:272-276`), then `DeleteOneEntry` on the directory itself (`:288-316`).
- *Rename* (`weed/server/filer_grpc_server_rename.go:37-104`): `BeginTransaction`,
  `moveEntry` → `moveSelfEntry` + `moveFolderSubEntries`, which pages the old
  directory 1024 at a time and recursively moves every descendant (`:288-321`),
  then `CommitTransaction`. **A directory rename rewrites every descendant row**
  because the row key *is* the path (INFERRED from the walk; the store has no
  prefix-rewrite verb).

**juicefs `Meta`** (READ `pkg/meta/interface.go:418-596`) is much wider — the
public interface is the POSIX surface plus admin: lifecycle (`Init`, `Load`,
`NewSession`, `CloseSession`, `FlushSession`, `GetSession`, `ListSessions`,
`CleanStaleSessions`, `CleanupTrashBefore`, `CleanupDetachedNodesBefore`,
`ScanDeletedObject`, `ListLocks`), namespace (`StatFS`, `Access`, `Lookup(parent,
name)`, `Resolve(parent, path)`, `GetAttr`, `SetAttr`, `CheckSetAttr`,
`Truncate`, `Fallocate`, `ReadLink`, `Symlink`, `Mknod`, `Mkdir`, `Unlink`,
`BatchUnlink`, `Rmdir`, `Rename`, `Link`, `Readdir`, `NewDirHandler`, `Create`,
`Open`, `Close`), data (`Read(ino, chunkIndex)`, `NewSlice`, `Write(ino, indx,
off, slice)`, `InvalidateChunkCache`, `CopyFileRange`), graph (`GetParents`,
`GetDirStat`, `GetPaths`), xattr (`GetXattr`, `ListXattr`, `SetXattr`,
`RemoveXattr`), locks (`Flock`, `Getlk`, `Setlk`), maintenance (`CompactAll`,
`Compact`, `CleanupSlices`, `WaitDeleteSlices`, `ScanSlices`, `Remove`,
`GetSummary`, `GetTreeSummary`, `Clone`, `Check`, `Chroot`, `GetFormat`,
`OnMsg`, `OnReload`, `HandleQuota`, `ScanUserGroupUsage`, `DumpMeta`,
`LoadMeta`, `DumpMetaV2`, `LoadMetaV2`, `InitMetrics`, `InitSharedMetrics`,
`SetFacl`, `GetFacl`, token verbs, `ScanChangelog`).

The *irreducible* primitives are the private `engine` interface that
`baseMeta` composes over (READ `pkg/meta/base.go:76-172`): `doLookup`,
`doGetAttr`, `doSetAttr`, `doMknod`, `doLink`, `doUnlink`, `doRmdir`,
`doBatchUnlink`, `doReaddir(ino, plus, limit)`, `doRename`, `doRead`,
`doWrite`, `doTruncate`, `doFallocate`, xattr, counters, sessions, quota,
slice GC, and `newDirHandler`. Composition in `baseMeta`:

- *Recursive remove* (`pkg/meta/utils.go:300-396`): `emptyDir` loops
  `doReaddir(limit=10000)`, fans subdirectories out to goroutines bounded by
  `numThreads ≤ 255`, `BatchUnlink`s the files of each page, then `Rmdir`.
- *Directory rename* (`pkg/meta/sql.go:2640-2700`): inside one transaction,
  delete the source edge, insert the destination edge, update `node.parent` —
  **O(1) rows regardless of subtree size.**
- *Path resolve*: `Lookup` is per component; `Resolve` is optional and may
  return `ENOTSUP` (`interface.go:456-459`); `GetPaths` walks parent pointers
  (`base.go:2398-2410`).

**Path-keyed vs inode-keyed.** Path keys buy a one-row lookup for any path and
a listing keyed on `(dirhash, name)`; they cost a subtree rewrite on rename, a
separate KV record for hard links (`filerstore_hardlink.go`), a *synthesized*
inode hashed from path+ctime (`filer_inode.go:9-14`), and an `InodeToPath`
table in the FUSE adapter (`weed/mount/inode_to_path.go:12-30`). Inode keys buy
O(1) rename, natural hard links, a stable inode for FUSE, and per-row typed
attributes; they cost N lookups per path and a path-shaped wrapper
(`pkg/fs/fs.go`) for every non-FUSE front.

**Lesson for vfs:** a store contract of ~8 row/cursor verbs plus a transaction
is enough to compose walk, rename, recursive delete and listing above it; the
one decision that cannot be composed later is whether the row key is the path
or an identity.

---

## 2. The SQL schema

**seaweedfs** — one table per bucket (default `filemeta`), four columns:
`dirhash BIGINT, name VARCHAR, directory TEXT, meta BLOB, PRIMARY KEY (dirhash,
name)` (READ `weed/filer/sqlite/sqlite_store.go:60-66`;
`weed/filer/postgres/postgres_sql_gen.go:25`). `dirhash` is an md5 of the
directory string folded to int64 (`weed/util/bytes.go:91-97`). `meta` is a
protobuf of attributes **and the whole chunk list** (`entry_codec.go:45,64`);
there is no chunk table. Chunk lists beyond `ManifestBatch = 10000` fold into
manifest chunks stored as data (`manifest_batch.go:10`,
`filechunk_manifest.go:503-519`). Hard links live in the KV table.

- Child lookup: `WHERE dirhash=$1 AND name=$2 AND directory=$3`
  (`postgres_sql_gen.go:60`) — a PK seek with `directory` as a hash-collision guard.
- Recursive delete in SQL: `DELETE ... WHERE dirhash=$1 AND directory=$2`
  (`:68`) removes the **direct children of one directory**; the Filer recurses
  per subdirectory (§1). Bucket root + `CanDropWholeBucket` → `DROP TABLE`
  (`abstract_sql_store.go:366-373`).
- Directory rename in SQL: none — per-row re-insert under the new path in one
  transaction (§1).
- Bind parameters: every statement has a fixed 3–5 binds; the listing passes
  `limit+1` (`abstract_sql_store.go:411`). There are no `IN (...)` lists
  anywhere in the abstract store (INFERRED from reading the generator
  `postgres_sql_gen.go:50-105`). The snapshot scan is keyset-paged at 1000 rows
  on `(dirhash, name) > (?, ?)` (`abstract_sql_store_scan.go:29`;
  `sqlite_store.go:40`; `postgres_sql_gen.go:81-83`).

**juicefs** (READ `pkg/meta/sql.go:56-271`, xorm tags):
`edge(id pk, parent, name varbinary(255), inode, type; UNIQUE(parent,name);
INDEX(inode))`; `node(inode pk, type, flags, mode, uid, gid, atime/mtime/ctime
+ nsec, nlink, length, rdev, parent, access_acl_id, default_acl_id, tier_id)`;
`chunk(id pk, inode, indx, slices BLOB; UNIQUE(inode,indx))`;
`sliceRef(chunkid pk, size, refs INDEX)`; `delslices`; `delfile`; `symlink`;
`xattr(inode, name UNIQUE; value)`; `flock`/`plock`; `session`/`session2`;
`sustained`; `dirStats`; `detachedNode`; `dirQuota`; `userGroupQuota`;
`changeLog(id, entry)`; `counter`; `setting`; `acl`; `delegationToken`.

- Child lookup: `edge WHERE parent=? AND name=?` joined to `node`
  (`sql.go:1551-1575`).
- Directory rename: one edge delete + one edge insert + `node.parent`
  update in a transaction (`:2640-2700`); exchange = two edge updates (`:2672-2680`).
- Recursive delete: not in SQL — client recursion with `doReaddir(limit=10000)`
  per round and `BatchUnlink` per page (`utils.go:300-355`).
- Paging a huge directory: the dir handler fetches `DirBatchNum["db"] = 40960`
  edges per batch (`base.go:59-63`) by `name > cursor ORDER BY name LIMIT`
  (`sql.go:6321-6327`), then a second statement `WHERE edge.id IN (ids)`
  joined to `node` (`:6334-6338`). INFERRED: that `IN` list can reach 40,960
  binds — fine on sqlite3/mysql/postgres, which are the only engines
  `upsertSlice` branches for (`:1663`), and exactly the statement vfs's
  Oracle floor forbids.

**Lesson for vfs:** both engines keep the per-child SQL to a PK seek on
`(parent-key, name)` and keep every statement at a fixed bind count except one
page-sized `IN` list; the body pointer list lives *in the row* (seaweedfs) or
in a per-64 MiB `chunk` row (juicefs), never one row per block.

---

## 3. Listing at scale

**seaweedfs.** Store page = `WHERE dirhash=? AND name>? AND directory=? AND
name LIKE ? ESCAPE '!' ORDER BY name LIMIT ?` (READ
`postgres_sql_gen.go:86-94`; inclusive variant uses `>=`). The cursor is
`startFileName`; the Filer asks for `limit+1` to compute `hasMore`
(`filer_search.go:25-42`). Internal walks use `PaginationSize = 1024`
(`filer.go:40`); the gRPC `ListEntries` is a server stream (`filer.proto:19`).

FUSE (READ `weed/mount/weedfs_dir_read.go`): a `DirectoryHandle` holds an
`entryStream` plus `entryStreamOffset` (`:37`); offsets start at 2 for `.`/`..`
(`:21`); `batchSize = 1000` (`:22`). A kernel offset maps to the stream by
position: forward progress drops consumed entries (`:58-74`); a backward seek
resets (`:200-207`); a fresh handle with a non-zero offset reloads from the
start and skips (`:298-324`). Each batch resumes the store cursor at the last
*name*, so the SQL cursor is the name, not the offset. The mount lists from a
local LevelDB `metaCache` fed by filer event subscription (`weed/mount/meta_cache/`),
not from SQL directly.

**juicefs.** Two shapes. `Readdir` loads the whole directory
(`doReaddir(limit=-1)`, `base.go:2346`; SQL `edge WHERE parent=?` joined to
`node`, `sql.go:2907-2941`). The FUSE path uses `NewDirHandler` → `dbDirHandler`
(`sql.go:6292-6380`) with `List(offset)` (`base.go:3991-4011`): the handler
holds one batch of up to 40,960 entries; an offset outside the batch triggers
`fetch(offset)`, which first finds the name at `offset-1` by `ORDER BY name
LIMIT 1 OFFSET n` and then pages `name > ?` (`sql.go:6309-6327`). `VFS.Readdir`
recreates the handler when `off == 0` (`vfs.go:450-455`); the FUSE adapter
reports partial buffer consumption via `UpdateReaddirOffset` (`fuse.go:387-402`).

**A directory of 1,000,000 entries** (INFERRED from the above): seaweedfs
serves 1,000 pages of 1,000, each an index range seek on the PK — bounded
per page, but a *rename* of that directory re-inserts 1e6 rows in one
transaction and a recursive delete issues ~1,000 listing pages plus one
`DELETE`. juicefs serves ~25 batches of 40,960, each two statements; a rename is
O(1); a recursive delete is 100 rounds of 10,000 with goroutine fan-out.

**Lesson for vfs:** paginate on the last *name* under the parent key, never on
a numeric offset at the SQL layer; let the adapter translate kernel offsets to
names, and pick a page size the least generous engine can bind.

---

## 4. Bodies: chunks, slices, overwrites, write-back

**seaweedfs.** The entry row carries `[]FileChunk{file_id, offset, size,
modified_ts_ns, ...}`. A read builds `NonOverlappingVisibleIntervals`
(`filechunks.go:299-309`): resolve manifests, then insert every chunk into an
interval list keyed by file offset where the newer `modifiedTsNs` wins
(`MergeIntoVisibles :265-279`); a ranged read is `ViewFromChunks(offset, size)`
(`:209-218`). A small overwrite in the middle is **a new chunk that shadows an
interval**; fully-shadowed chunks become garbage via `CompactFileChunks`
(`:69-110`).

Write path (READ `weed/mount/weedfs_file_write.go:39-110`): `Write` updates the
in-memory entry size/mtime and calls `dirtyPages.AddPage`; `PageWriter` splits by
`chunkSize` (`page_writer.go:32-46`, default `chunkSizeLimitMB = 2`,
`weed/command/mount.go:106`) into `ChunkedDirtyPages` → `UploadPipeline` with a
swap-file spill dir (`dirty_pages_chunked.go:28-41`). On flush each dirty
interval is uploaded as a new needle and appended to the handle's chunk list
(`saveChunkedFileIntervalToStorage :96-112`; `AddChunks filehandle.go:209`).
`doFlush` (`weedfs_file_sync.go:132-200`): with `-writebackCache` a
close-triggered flush is deferred to a goroutine (`:142-153`); otherwise
`FlushData` then `flushMetadataToFiler` sends the **whole entry** (attributes +
full chunk list) through `CreateEntry`/`UpdateEntry` with retry. `Release`
always routes through `doFlush` with a non-cancellable context
(`weedfs_file_io.go:142-160`). Per open file in memory: a `FileHandle` holding a
`LockedEntry` (the full entry incl. chunk list), an `entryChunkGroup`, a
`PageWriter` of dirty chunks (`filehandle.go:22-30,78-90`).

*1-byte append to a 100 MB file* (mechanism READ, cost INFERRED): the byte lands
in a dirty page for chunk index 50; flush uploads a 1-byte needle and appends
one `FileChunk{offset=100 MB, size=1}`; the metadata flush rewrites the row's
`meta` blob (≈50 chunk records at 2 MiB chunks). None of the 100 MB is re-read
or re-uploaded; cost = 1 small upload + 1 full-row `UPDATE`.

**juicefs.** A file is 64 MiB chunks (`ChunkSize = 1 << 26`,
`interface.go:41`); each `chunk` row holds a blob of 24-byte slice records
`(pos, id, size, off, len)` (`slice.go:93-101`) appended by `upsertSlice`
(`INSERT ... ON CONFLICT DO UPDATE SET slices = slices || ?`,
`sql.go:1660-1683`). A read overlays slices in insertion order so later ones
shadow earlier (`buildSlice slice.go:134-142`). Slice data lives in object
storage as blocks of `BlockSize` (default 4 MiB, `writer.go:494`).

Write path (READ `pkg/vfs/writer.go`): `fileWriter.Write` splits by chunk
(`:376-388`); `findWritableSlice` extends the open slice when contiguous, else
opens a new one (`:184-204`); `sliceWriter.write` flushes a block when
`slen ≥ blockSize` and freezes at a full chunk (`:151-174`); `commitThread`
calls `meta.Write` per slice in creation order (`:206-230`). `VFS.Write`
invalidates the reader and attr cache (`vfs.go:855-861`); `Flush` and `Fsync`
call `writer.Flush` under the handle write lock (`:1018-1024, :1042-1060`).
After every `Write`, `numSlices % 100 == 99 || > 350` triggers async
compaction, `> maxSlices (2500)` synchronous (`base.go:2245-2251`; `:64-65`).
Per open file: a `handle` (`handle.go:164-180`) carrying a `fileWriter`
(chunkWriters → sliceWriters with pending block buffers) and a reader page cache.

*1-byte append to a 100 MB file* (mechanism READ): a new 1-byte slice → one
1-byte object PUT, then one meta transaction: `node` length/mtime update,
`chunk.slices` blob append of 24 bytes, one `sliceRef` insert
(`sql.go:3516-3562`). The 100 MB is untouched.

**Lesson for vfs:** both engines make every write an *append of a shadowing
record* (a chunk or a slice) and reconcile lazily by compaction; the body row
never grows with the file, only with the number of unmerged writes.

---

## 5. One kernel, many fronts

**seaweedfs fronts** (EXECUTED: file counts referencing the filer gRPC client,
`grep -rl "WithFilerClient\|SeaweedFilerClient"`): S3 gateway `weed/s3api` (58
files), FUSE mount `weed/mount` (14) plus WinFsp (`weed/mount/winfsp`), `weed
shell` (41), CLI commands `filer.copy/cat/backup/sync` and gateways
(`weed/command`, 15), filer HTTP + WebDAV + TUS (`weed/server`, 7), SFTP
(`weed/sftpd`, 1), HDFS client (`other/java/hdfs3`), Java client
(`other/java/client`), MQ brokers. **The shared API is the filer gRPC service**
`SeaweedFiler` (READ `weed/pb/filer.proto:13-69`): `LookupDirectoryEntry`,
`LookupDirectoryEntries`, `ListEntries` (stream), `CreateEntry`, `UpdateEntry`,
`TouchAccessTime`, `AppendToEntry`, `DeleteEntry`, `ObjectTransaction[Batch]`,
`PosixLock`, `AtomicRenameEntry`, `StreamRenameEntry`, `StreamMutateEntry`,
`AssignVolume`, `LookupVolume`, `CollectionList`, `DeleteCollection`,
`Statistics`, `Ping`. Note it is **entry-shaped, not handle-shaped**: fronts
read/write whole entries and upload chunks to volumes themselves.

FUSE adapter translation (READ `weed/mount/`): `FileHandleId → FileHandle`
map (`filehandle_map.go`); `InodeToPath` (`inode_to_path.go:12-30, 161-269`);
`DirectoryHandle` offsets (§3); LevelDB `metaCache`; `FOPEN_KEEP_CACHE` keyed
on last-seen mtime (`weedfs_file_io.go:76-80, 115-127`). Open/Read/Write/Release:
`weedfs_file_io.go:66-84, 142-160`; `weedfs_file_read.go:41-62` (chunks first,
dirty pages overlaid); `weedfs_file_write.go:39-110`. **Errno table** (READ
`weed/mount/error_classifier.go:12-52`, `grpcErrorToFuseStatus`): gRPC
`Canceled`/`DeadlineExceeded → ETIMEDOUT`, `Unavailable → EAGAIN`,
`ResourceExhausted → EAGAIN`, `PermissionDenied → EACCES`, `Unauthenticated →
EPERM`, `NotFound → ENOENT`, `AlreadyExists → EEXIST`, `InvalidArgument →
EINVAL`; else string match `"transport" → EAGAIN`; default `EIO`.
`writeErrorToFuseStatus` (`:66`) maps storage-full text to `ENOSPC`.

**juicefs fronts** (READ): FUSE (`pkg/fuse/fuse.go`), S3 gateway (`pkg/gateway`,
a MinIO `ObjectLayer` over `pkg/fs`, `gateway.go:79-93`), WebDAV
(`cmd/webdav.go`), Java/Hadoop SDK (`sdk/java/libjfs`), Python SDK
(`sdk/python`), the `juicefs` CLI (`cmd/*`: `rmr`, `info`, `warmup`, `clone`,
`compact`, `dump`, `load`, `fsck`, `gc`, `sync`), CSI driver (separate repo —
INFERRED). **Two shared layers:** `pkg/vfs.VFS` is inode+handle shaped
(`Lookup`, `Open`, `Read`, `Write`, `Flush`, `Release`, `Readdir`,
`vfs.go:177-1060`); `pkg/fs.FileSystem` is the path-shaped wrapper
(`Open(path)`, `Create(path)`, `Delete`, `Rmr`, `Rename`, `File.Pread/Pwrite/
Flush/Close/Readdir`, `fs.go:401-1501`) that the gateway and SDKs consume.

FUSE adapter (READ `pkg/fuse/fuse.go:254-315, 387-425`): each op builds a
context and forwards to `VFS`; **no errno table** — `Meta` and `VFS` already
return `syscall.Errno`, so the adapter does `fuse.Status(err)`. The only
normalization is in `VFS`: `ENOENT/EPERM/EINVAL` on a write → `EBADF`
(`vfs.go:853-855`). Handle table: `pkg/vfs/handle.go:164-258` (`newHandle`,
`findHandle`, `releaseHandle`; a handle carries `reader`, `writer`,
`dirHandler`, locks), with `dumpAllHandles`/`loadAllHandles` for live upgrade
(`:302, :375`).

**Lesson for vfs:** the kernel's own error vocabulary decides adapter weight —
juicefs speaks errno from the store up and the FUSE adapter is a pass-through,
while seaweedfs speaks gRPC codes and every front carries its own mapping table.

---

## 6. Search and metadata

**seaweedfs.** `filer_search.go` is name-prefix and glob only: a `*`/`?`
pattern is split into a SQL `LIKE prefix%` plus a client-side filter over
listed names (`:12-22, :78-116`). No full-text. Extended attributes and S3 tags
share `Entry.Extended map[string][]byte` (`entry.go:40`): xattrs under an
`xattr-` prefix (`weed/mount/weedfs_xattr.go:17,53`), tags via the HTTP tagging
handler (`filer_server_handlers_tagging.go:34-41`) — all inside the `meta` blob,
not queryable. An *external* index exists: `weed filer.meta.tail` ships the
metadata event stream to Elasticsearch (`weed/command/filer_meta_tail_elastic.go`).

**juicefs.** No search. `xattr(inode, name, value)` is its own table
(`sql.go:192-197`); quota tables per directory and per user/group
(`:251-266`); `GetSummary`/`GetTreeSummary` are walks (`utils.go:398-420`).

**Where an index would sit** (INFERRED): seaweedfs already has the seam — a
consumer of `NotifyUpdateEvent` (`filer_notify.go:26`), the same bus the mount
cache, `filer.sync` and `filer.meta.tail` consume; the index would be a peer
subscriber, eventually consistent. juicefs has `changeLog` (`sql.go:268-271`)
and `ScanChangelog` (`interface.go:595`); a synchronous index would instead be
a sibling table keyed by inode written inside the `doWrite`/`doSetAttr`
transactions.

**Lesson for vfs:** neither engine indexes bodies; both expose a change feed
from the metadata store that an index could follow — vfs's in-transaction
index is the thing these projects do not have.

---

## 7. Versions, trash, consistency

**seaweedfs.** S3 object versions are ordinary filer entries inside a
`.versions/` directory beside the object, with noncurrent stamps in `Extended`
(READ `weed/s3api/s3api_object_versioning.go:46-75`). TTL expiry is evaluated
lazily at read time — `FindEntry` and listing delete an expired row when they
meet it (`filer.go:775-787, 813-830`) — so there are no tombstone rows in the
store; tombstones exist only for lazily-mounted remote storage
(`filer_remote_tombstone.go`; `noteRemoteDeletion filer_delete_entry.go:201-206`).
Chunk GC is an async deletion queue of up to 100,000 file ids per batch
(`filer_deletion.go:40`) plus `volume.fsck` over the `ScanEntries` snapshot
(`filerstore.go:52-58`). Consistency: every front writes the same filer store,
so an S3 PUT is visible to the next filer read; the FUSE mount's LevelDB
`metaCache` is updated by subscribing to filer metadata events
(`weed/mount/meta_cache/meta_cache_subscribe.go`) — INFERRED: eventual within
subscription lag — and page cache reuse is gated on mtime equality
(`weedfs_file_io.go:76-80`). Multi-filer deployments replicate events through
`AggregateFromPeers` (`filer.go:220`) — eventual.

**juicefs.** Trash is on by default: an unlink or overwriting rename moves the
edge under `/.trash/YYYY-MM-DD-HH/<parent ino>-<ino>-<name>` (READ
`docs/en/security/trash.md`; `trashEntry base.go:3127`; rename-into-trash
`sql.go:2694-2695`), expired by `CleanupTrashBefore` from a client background
job. Deferred data deletion rides `delfile` and `delslices` rows
(`sql.go:181-185, 233-237`); `sustained` keeps open-but-unlinked inodes alive
per session (`:227-231`); `DumpMetaV2`/`LoadMetaV2` give backup/restore;
`changeLog` gives a replayable log. Documented consistency (READ
`docs/en/guide/cache.md:16-71`): **close-to-open** by default — `open` always
queries the metadata service, kernel attribute cache is 1 s, `--open-cache`
weakens it; `architecture.md:74` calls the metadata layer strongly consistent.
S3 gateway and SDKs share the same `Meta`, so a gateway PUT is seen by a FUSE
`open` on another node (docs READ; the shared-path INFERRED from `gateway.go:79`).

**Lesson for vfs:** both keep deleted data reachable for a window by *moving
the name* (a `.versions/` or `.trash/` directory) rather than flagging the row,
and both define cross-front consistency at the metadata store with caches
invalidated by event or by open.

---

## Design facts for the synthesis

1. READ — seaweedfs's whole store contract is 16 methods: 5 row verbs, 2 cursor listings, 1 children-sweep, a transaction, 3 KV verbs (`filerstore.go:22-45`).
2. READ — juicefs's SQL engine is ~50 private `do*` primitives under a ~90-method POSIX `Meta`; recursion, trash, quota and compaction are composed in `baseMeta` (`base.go:76-172`).
3. READ — Path-keyed rows make a directory rename an O(subtree) re-insert in one transaction (`filer_grpc_server_rename.go:288-321`); inode-keyed edges make it O(1) (`sql.go:2640-2700`).
4. READ — Both key the child lookup on `(parent-key, name)`: seaweedfs PK `(dirhash, name)`, juicefs `UNIQUE(parent, name)` on `edge`.
5. READ — Every listing is keyset-paged on the last *name* (`name > ? ORDER BY name LIMIT ?`); page sizes 1,000–1,024 (seaweedfs) and 40,960 (juicefs).
6. READ — Kernel readdir offsets are positions in an adapter-held stream that resumes the SQL cursor by name (`weedfs_dir_read.go:58-74`; `sql.go:6309-6327`).
7. READ — Body pointers never become one row per block: seaweedfs stores the chunk list in the entry blob (manifest beyond 10,000), juicefs one `chunk` row per 64 MiB holding appended 24-byte slice records.
8. READ — A write is an appended shadowing record; readers overlay by timestamp (seaweedfs) or insertion order (juicefs); compaction is lazy and threshold-driven (`base.go:2245-2251`).
9. READ — Whole-file write-back happens at flush/close: the FUSE handle buffers dirty pages and the metadata row is rewritten once (`weedfs_file_sync.go:132-200`; `writer.go:206-230`).
10. READ — seaweedfs's shared front-end API is entry-shaped gRPC (`filer.proto:13-69`); juicefs's is inode+handle (`pkg/vfs`) with a path-shaped wrapper (`pkg/fs`) for S3/SDKs.
11. READ — Error vocabulary sets adapter cost: errno from the store up means a pass-through FUSE adapter (juicefs); gRPC codes mean a mapping table per front (`error_classifier.go:12-52`).
12. INFERRED — Neither engine indexes bodies; both expose a change feed (`NotifyUpdateEvent`, `changeLog`) that an index would subscribe to, eventually consistent — an in-transaction index is the gap vfs fills.
