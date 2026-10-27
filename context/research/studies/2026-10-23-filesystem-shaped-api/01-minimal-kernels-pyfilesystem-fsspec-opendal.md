# Study 01 — The minimal kernel of a Python filesystem abstraction, and what is derived from it

- **Date:** 2026-10-23. **Brief:** `00-brief.md`.
- **Repos (read-only, refreshed per `refresh.log`):**
  - `~/Git/Repos/pyfilesystem2` — `master` `77a8562785` (2025-05-17), MIT.
  - `~/Git/Repos/filesystem_spec` (fsspec) — `master` `fb355c4c1b` (2026-10-23), BSD-3-Clause.
  - `~/Git/Repos/opendal` — `main` `19ba33da9e` (2026-10-23), Apache-2.0. The clone is shallow
    (298 commits, EXECUTED `git rev-list --count HEAD`). At this commit the kernel trait is named
    `Service`; the RFC filenames under `core/core/src/docs/rfcs/` still say "accessor", so
    `Access` → `Service` is a rename (INFERRED).
- **Labels:** READ = a file at the commit above; EXECUTED = ran here; INFERRED = my reading.
- No code was copied. Citations are `path:line`.

---

## 1. pyfilesystem2 — seven essentials, everything else derived

**The essential set (READ `fs/base.py:146-315`, banner "Required methods — Filesystems must
implement these methods").** Exactly seven `@abc.abstractmethod`s:

| # | Method | Shape |
|---|--------|-------|
| 1 | `getinfo(path, namespaces=None) -> Info` | stat; `"basic"` namespace always present |
| 2 | `listdir(path) -> list[str]` | names only, whole directory, no cursor |
| 3 | `makedir(path, permissions, recreate) -> SubFS` | one level |
| 4 | `openbin(path, mode="r", buffering=-1, **opts) -> BinaryIO` | the only body verb |
| 5 | `remove(path)` | files only |
| 6 | `removedir(path)` | empty dirs only; refuses `/` |
| 7 | `setinfo(path, raw_info)` | the write half of `getinfo` |

A second banner (`fs/base.py:316-319`, "Optional methods — Filesystems *may* implement") holds
`appendbytes`, `copy`, `move`, `readbytes`, `writebytes`, `scandir`, `upload`/`download`,
`getsyspath`, `geturl`, each with a default built from the seven; a third (`:1616`, "Helper
methods") holds `getbasic`, `getdetails`, `match`, `match_glob`, `tree`, `hash`.

**`openbin` is the body kernel, and bodies are handles, not values.** There is no
`readbytes`/`writebytes` primitive: `readbytes` opens `"rb"` and calls `.read()` (READ
`fs/base.py:620-640`); `writebytes` opens `"wb"` and `.write()`s (`:1383-1402`); text `open` wraps
`openbin` in `iotools.make_stream` (`:1206-1259`). The mode string is parsed by `fs.mode.Mode`
into `create`/`reading`/`writing`/`appending`/`updating`/`truncate`/`exclusive` flags (READ
`fs/mode.py:123-176`).

*Whole-body backend behind a handle.* `MemoryFS` keeps one `io.BytesIO` per file entry
(`_DirEntry.bytes_file`, READ `fs/memoryfs.py:218-231`) and hands out `_MemoryFile(io.RawIOBase)`
whose every `read`/`write`/`seek`/`truncate` takes the entry's `RLock`, seeks the shared `BytesIO`
to the handle's own `pos`, performs the op, and stores the new `pos` back (`_seek_lock`, READ
`:88-93`, `:138-202`). So a "ranged read" is `seek`+`read` over an in-memory whole body; `openbin`
only decides create/exists/truncate from the mode and returns the handle. The read-only archive
backends do the same with `iotools.RawWrapper` around a member stream (`fs/tarfs.py` `openbin`;
`fs/zipfs.py:47-60`, where pre-3.7 `seek` was emulated by re-reading; both READ). INFERRED: the
kernel never requires a backend to *store* ranges; the handle is a cursor over a body the backend
may hold whole.

*Mount composition.* `WrapFS` implements every essential by `delegate_path(path) -> (fs, path)`
then forwarding (READ `fs/wrapfs.py:88-250`). `MountFS._delegate` normalizes the path, scans its
`(mount_path, fs)` list for a prefix, strips it and returns `(fs, rest)`, else `(default_fs, path)`
where `default_fs` is a `MemoryFS` holding the mount-point directories (READ
`fs/mountfs.py:76-125`); `mount` refuses overlapping prefixes. Every verb, `openbin` included, is
one lookup then a call on the child (`:163-168`). INFERRED: because the kernel is seven
path-keyed methods, a mount table is a seven-method forwarder; no per-handle state crosses it.

**How the derived verbs are built (all READ).**

- `scandir` = `listdir` + `getinfo` per name, with an optional `page=(start, end)` applied
  client-side by `itertools.islice` (`fs/base.py:1343-1382`) — the only "pagination" in the API.
- `walk` = a `Walker` calling `fs.scandir(dir, namespaces=…)` per directory, breadth- or
  depth-first, with `check_open_dir`/`check_file` filters (`fs/walk.py:310-335`, `:448-534`).
- `glob` = a `Globber` over `fs.walk.info(...)` with the pattern translated to a regex
  (`fs/glob.py:275-345`, `:60-137`); `match`/`match_glob` are pure pattern tests honoring
  `getmeta()["case_insensitive"]` (`fs/base.py:1675-1775`).
- `copy` = `open(src,"rb")` streamed into `upload(dst)` under the FS lock (`fs/base.py:399-437`).
- `move` = if `getmeta()["supports_rename"]` and both sides have `getsyspath`, `os.rename`; else
  copy-then-`remove` (`fs/base.py:1152-1205`). Rename is an optimization hook, not a kernel verb.

**`Info` (READ `fs/info.py`).** A thin view over a raw `Mapping[namespace, Mapping[key, value]]`;
`namespaces = frozenset(raw.keys())` (`:47-54`). Namespaces in `OSFS.getinfo` (READ
`fs/osfs.py:279-307`): `basic` (`name`, `is_dir`; always present), `details` (`type`, `size`,
`accessed`/`modified`/`created`/`metadata_changed`), `access` (uid/gid/permissions),
`stat`/`lstat` (raw `os.stat` fields), `link` (`target`). A namespace may carry a `_write` list
naming the keys `setinfo` accepts (`fs/info.py:130-167`). `getmeta()` is a separate per-filesystem
dict (`case_insensitive`, `invalid_path_chars`, `max_path_length`, `read_only`, `supports_rename`,
`network`; READ `fs/base.py:727-780`).

**Lesson for vfs:** seven path-keyed verbs — one stat, one list, one mkdir, one open-handle, two
removes, one set-meta — derive walk, glob, copy, move and every byte verb, and a mount table is a
seven-method forwarder; the price is that the body verb must be a seekable handle, even over
whole-body storage.

---

## 2. fsspec — a smaller kernel, with `ls` doing almost everything

**Primitives (what a subclass must override).** `AbstractFileSystem` has no abstract methods; the
primitives are the ones whose default raises `NotImplementedError` (READ `fsspec/spec.py`):

| Primitive | Default | Line |
|-----------|---------|------|
| `ls(path, detail=True)` | raise | `:419-458` |
| `cp_file(p1, p2)` | raise | `:1251-1252` |
| `_rm(path)` (via `rm_file`) | raise | `:1386-1393` |
| `_open(path, mode, block_size, autocommit, cache_options)` | returns `AbstractBufferedFile` | `:1422-1440` |
| `created` / `modified` / `sign` / `fsid` | raise | `:1765-1771`, `:1963`, `:264` |
| `mkdir` / `makedirs` / `rmdir` | **`pass`** — "may not have directories" | `:381-417` |

Everything else is derived (READ):

- `info(path)` = `ls(parent, detail=True)` filtered to the name; if absent, `ls(path)` and, if that
  returns entries, synthesize `{"type": "directory", "size": 0}`; else `FileNotFoundError`
  (`:775-808`). `exists`/`isdir`/`isfile`/`size` wrap `info`.
- `walk` = `ls(detail=True)` per directory, `os.walk`-style with prunable `dirnames`
  (`:485-579`); `find` = `walk` flattened (`:580-617`); `glob` = regex over `find` with `maxdepth`
  computed from the first `**` (`:652-760`); `expand_path` = `glob`/`find`; `du` = `find` + sizes.
- `cat_file(path, start, end)` = `open(path,"rb")` then `seek`/`read`, negative offsets resolved
  against `.size` or a seek-to-end (`:888-936`); `cat_ranges` loops `cat_file` (`:968-1001`).
  `pipe_file(path, value)` = `open(path,"wb")`.`write` (`:937-945`); `cat`/`pipe` fan out over
  `expand_path`.
- `copy` = `expand_path` + `cp_file` per pair (`:1254-1310`); `mv` = `copy` then `rm`
  (`:1362-1385`); `rm` = `expand_path` then `rm_file` in reverse (`:1395-1413`). No rename
  primitive. Aliases (`read_bytes`, `listdir`, `stat`, `rename`, `delete`, …) at `:1911-1961`.

INFERRED from the bodies: the default `_open` returns an `AbstractBufferedFile` whose
`_fetch_range` calls back into `fs.cat_file(path, start, end)` (`:2264-2266`), and the default
`cat_file` calls `open`. The two defaults are mutually recursive, so a real backend must override
**at least one of** `_open` or `cat_file`, plus `ls` and `_rm` for a read/write store — three or
four methods in practice.

**`AbstractBufferedFile` — ranged reads and chunked writes over a whole-object store (READ
`fsspec/spec.py:1995-2404`).** The docstring says only `_upload_chunk`, `_initiate_upload` and
`_fetch_range` need overriding (`:1997-2003`).

- *Read side:* `mode == "rb"` builds `self.cache = caches[cache_type](blocksize, self._fetch_range, size)`
  (`:2076-2080`); `read(length)` asks `self.cache._fetch(loc, loc+length)` and advances `self.loc`
  (`:2268-2298`); `seek` only changes `self.loc` and is **refused in write modes** with
  `OSError(ESPIPE)` (`:2157-2182`). The cache object decides which `_fetch_range(start, end)` calls
  to issue, so a whole-object backend just slices: `MemoryFileSystem.cat_file` returns
  `bytes(self.store[path].getbuffer()[start:end])` (READ `fsspec/implementations/memory.py:366-370`).
- *Write side:* `write` appends to a `BytesIO` buffer and calls `flush` once it reaches
  `blocksize` (`:2183-2206`); `flush` defers while small, on first real flush calls
  `_initiate_upload()`, then `_upload_chunk(final=force)` and advances `self.offset`
  (`:2207-2248`); `close` does `flush(force=True)` and invalidates the dircache for the file and its
  parent (`:2378-2404`). Modes are **`rb`, `wb`, `ab`, `xb` only** (`:2072-2073`). INFERRED: a
  whole-object store implements `_upload_chunk` as "accumulate; on `final`, put the whole thing",
  which the 5 MiB `DEFAULT_BLOCK_SIZE` (`:2004`) is sized for.

**`AsyncFileSystem` (READ `fsspec/asyn.py`).** Primitives become `_ls`, `_info`, `_cat_file`,
`_pipe_file`, `_rm_file`, `_cp_file`, `_put_file`, `_get_file` (the `NotImplementedError` sites at
`:512,527,597,636,720,797,906,909`). What it adds is **fan-out**: `_cat`, `_pipe`, `_copy`, `_rm`,
`_put`, `_get`, `_sizes` build one coroutine per path and run them through
`_run_coros_in_chunks(coros, batch_size=…)` (`:362-448`), a sliding window of at most
`batch_size` in flight (`_DEFAULT_BATCH_SIZE = 128`, `_NOFILES_DEFAULT_BATCH_SIZE = 1280`,
`:324-345`). With `mirror_sync_methods = True` (`:487`) every name in `async_methods`
(`:450-472`) gets a generated sync wrapper. INFERRED: batching is a client-side concurrency cap,
not a server-side batch verb — the backend still sees one call per file.

**Listing is whole, not paged (READ).** `ls` returns the entire directory as a list
(`:419-458`); nothing in the base API carries a cursor or page token. Instead there is `DirCache`
(READ `fsspec/dircache.py:1-60`), a `MutableMapping` keyed by directory path holding the full
listing, with optional `listings_expiry_time` and an LRU `max_paths`; `_ls_from_cache` answers
`info(child)` from the parent's cached listing and raises `FileNotFoundError` if the parent was
listed and the child is absent (`spec.py:460-484`).

**Lesson for vfs:** fsspec's working kernel is `ls` + one body verb (`cat_file` or `_open`) +
`rm_file` + `cp_file`, with `info` derived from `ls(parent)` — directory listing is the
load-bearing primitive — and its batch story is a client-side window over per-file calls, with
listing never paged.

---

## 3. opendal — a typed kernel with capability flags and wrapping layers

**The kernel trait (READ `core/core/src/raw/service.rs:109-281`, `pub trait Service`).** Six
associated types bound to `oio` traits (`Reader: oio::Read`, `Writer: oio::Write`,
`Lister: oio::List`, `Deleter: oio::Delete`, `Copier: oio::Copy`, `Composer: oio::Compose`), then
thirteen functions:

| Fn | Returns | Required? |
|----|---------|-----------|
| `info()` / `capability()` | `ServiceInfo` / `Capability` | yes |
| `create_dir(ctx, path, OpCreateDir)` | `RpCreateDir` (async) | yes |
| `stat(ctx, path, OpStat)` | `RpStat` (async) | yes |
| `read(ctx, path, OpRead)` | `Self::Reader` | yes |
| `write(ctx, path, OpWrite)` | `Self::Writer` | yes |
| `delete(ctx)` | `Self::Deleter` — **no path**; paths go to the deleter | yes |
| `list(ctx, path, OpList)` | `Self::Lister` | yes |
| `copy(ctx, from, to, OpCopy)` | `Self::Copier` | yes |
| `compose(ctx, to, OpCompose)` | `Self::Composer` | default `Unsupported` |
| `rename(ctx, from, to, OpRename)` | `RpRename` (async) | yes |
| `restore(ctx, path, OpRestore)` | `RpRestore` (async) | default `Unsupported` |
| `presign(ctx, path, OpPresign)` | `RpPresign` (async) | yes |

"Required" means no default body; a backend that cannot do a verb returns
`ErrorKind::Unsupported` and leaves the capability flag false (the sqlite service does so for
`list`, `copy`, `rename`, `presign`; READ `core/services/sqlite/src/backend.rs:313-360`).
`ServiceDyn` / `Servicer = Arc<dyn ServiceDyn>` (`:283-377`) is the object-safe form layers wrap.

**The handle traits (READ `core/core/src/raw/oio/*/api.rs`).**

- `oio::Read` (`read/api.rs:37-60`): `open(range) -> (RpRead, ReadStream)` and
  `read(range) -> (RpRead, Buffer)`; a `ReadStream` yields `Buffer`s until empty. The range is a
  parameter of every read; there is no cursor in the kernel.
- `oio::Write` (`write/api.rs:28-58`): `write(Buffer)`, `copy_from(path, OpRead, range)`
  (server-side source), `close() -> Metadata`, `abort()`. A writer is a session; the object
  exists only at `close`.
- `oio::List` (`list/api.rs:29-45`): `next() -> Option<Entry>`, a pull iterator;
  `Entry = (path, Metadata)` (`entry.rs:29-113`).
- `oio::Delete` (`delete/api.rs:34-58`): `delete(path, OpDelete)` enqueues, `close()` flushes —
  the batch shape is in the handle; `Operator::delete_iter/_stream` and `Deleter::into_sink` (READ
  `types/delete/deleter.rs:108-200`) all ride one deleter.
- `oio::Copy` (`copy/api.rs:28-39`): `next() -> Option<usize>` (bytes this step), `close`, `abort`.

**Helper families turn a native shape into the trait (READ directory listings + doc headers).**
Reads: `StreamRead` ("services only need to expose their native `open(range)`",
`read/stream_read.rs:24-37`) and `PositionRead` (pread-style, `position_read.rs:28-33`). Writes:
`OneShotWrite`, `AppendWrite`, `BlockWrite`, `MultipartWrite`, `PositionWrite`. Lists: `PageList`
— the backend implements `next_page(&mut PageContext)` where `PageContext` holds `done`, a
`token: String` and `entries: VecDeque<Entry>` (`list/page_list.rs:34-59`); `FlatLister`
(recursion by re-listing), `PrefixLister`, `HierarchyLister`. Deletes: `OneShotDelete` (deletes on
`close`) and `BatchDelete` (`delete_once` + `delete_batch`, `delete/batch_delete.rs:24-58`).

**Ranged read and chunked write, as the caller sees them (READ `core/core/src/types/options.rs`,
`types/operator/operator.rs`).** `ReadOptions` carries `range: BytesRange`, `version`, six `if_*`
conditions, `concurrent`, `chunk`, `gap` (`options.rs:159-304`); `ReaderOptions` adds `prefetch`
(`:322-457`). `read_with(path).range(..)` resolves to `read_options`, which asks the service for a
`Reader`, wraps it in a `ReadContext` and calls `Reader::read(range)` (`operator.rs:679-728`).
`Reader::fetch(ranges)` merges nearby ranges (`gap`), fetches the merged ones, and slices them
back out (`types/read/reader.rs:140-200`). `WriteOptions` carries `append`, `chunk`, `concurrent`,
`if_not_exists`, `if_match`, `content_type`, `user_metadata` (`options.rs:586-828`);
`writer(path)` returns a `Writer` with `write`, `write_from`, `copy_from`, `abort`,
`close -> Metadata` (`types/write/writer.rs:139-243`). Appending is a write option, not a mode.

**Listing pages (READ).** `ListOptions { limit, start_after, recursive, versions, deleted }`
(`options.rs:131-142`); `list(path)` collects a `Vec<Entry>`; `lister(path)` returns a `Lister`
that `impl Stream` (`types/list.rs:63-66`) over the kernel's `oio::List::next`. `limit` and
`start_after` are hints the backend must declare (`list_with_limit`, `list_with_start_after`);
the page token itself never leaves `PageContext`.

**Layers (READ `core/core/src/raw/layer.rs:38-51`).** `trait Layer` has
`apply_service(Servicer) -> Servicer` and `apply_context(Servicer, OperationContext)`; a layer
returns a new `Servicer` wrapping the inner one, and `Operator::layer(L)` composes them
(`operator.rs:351`). `RetryLayer` (READ `core/layers/retry/src/lib.rs:217-233`, `:295-535`)
re-implements all thirteen fns and wraps each returned `Reader`/`Writer`/`Lister`/`Deleter` in
`RetryWrapper` so per-chunk `read`/`write`/`next`/`delete` calls are retried with exponential
backoff **when `Error::is_temporary()`** (`:35`, `:324`). `ConcurrentLimitLayer`
(`core/layers/concurrent-limit/src/lib.rs:97-249`) takes a semaphore permit per operation.
`LoggingLayer` has the same shape (`core/layers/logging/src/lib.rs:133-264`). Twenty-five layer
crates exist (EXECUTED `ls core/layers`). Four live in core and are applied implicitly:
`ErrorContextLayer`; `CompleteLayer` (fills `Metadata` and unknown entry modes,
`layers/complete.rs:26-232`); `CorrectnessCheckLayer` (refuses an argument the capability does
not declare with `ErrorKind::Unsupported` naming the flag, `layers/correctness_check.rs:60-110`);
and `SimulateLayer`, which emulates `create_dir` when `list && write_can_empty`, recursive delete
when `list && delete`, `stat` on a directory via `list`, recursive `list` via `FlatLister`, and
suffix reads (`layers/simulate.rs:30-45`, `:108-120`, `:174`, `:214-224`). INFERRED: the kernel
never changes; missing verbs are refused by name or synthesized above it, per flag and visibly.

**`Capability` (READ `core/core/src/types/capability.rs`).** One struct of ~90 fields, each a
`bool` or a size, named `verb`, `verb_with_option` or `verb_can_x`: `stat`, `read`,
`read_with_version`, `write`, `write_can_multi`, `write_can_empty`, `write_can_append`,
`write_can_copy_from`, `write_with_if_not_exists`, `write_multi_max_size`/`min_size`,
`write_total_max_size`, `create_dir`, `delete`, `delete_with_recursive`, `delete_max_size`,
`copy`, `copy_can_multi`, `compose`, `restore`, `rename`, `list`,
`list_with_limit`/`start_after`/`recursive`/`versions`/`deleted`, `presign_*`, `shared`.
Callers read it as `Operator::info().capability()` (`types/operator/info.rs:56`); the Python
binding exposes `Operator.capability()` (`bindings/python/src/operator.rs:877`).

**A SQL service is a whole-value KV map (READ `core/services/sqlite/src/`).** Capability:
`read, write, create_dir, delete, stat, write_can_empty` true, **`list: false`**
(`backend.rs:183-192`); postgresql is the same plus `shared: true`
(`core/services/postgresql/src/backend.rs:160-165`). The SQL is one row per key:
`SELECT value WHERE key = $1` (`core.rs:61`), `INSERT OR REPLACE` (`:173`; postgres
`ON CONFLICT … DO UPDATE`, `postgresql/src/core.rs:97-99`), `DELETE WHERE key = $1` (`:189`).
Two things are pushed into SQL rather than done in Rust: *ranged reads* via
`SUBSTR(CAST(value AS BLOB), $1, $2)` plus `LENGTH(...)` (`core.rs:107-156`, used by
`SqliteReader::open(range)` when the range is not full, `reader.rs:38-75`), and *stat* via
`LENGTH` for a file or `COUNT(*) WHERE instr(key, prefix) = 1` for a directory (`core.rs:72-99`,
`backend.rs:225-259`). The writer accumulates every `write(Buffer)` into a `Vec` and issues one
`set` on `close` (`writer.rs:39-57`) — append and chunking are a client-side illusion over a single
whole-value upsert. Delete is `OneShotDeleter` (`backend.rs:213`). Because `list` is false,
`SimulateLayer` cannot synthesize recursive delete or `stat_dir` for it (both gate on `cap.list`;
INFERRED from `simulate.rs:108-120`).

**Python binding (READ `bindings/python/src/`).**
`Operator.read(path, offset=, size=, concurrent=, chunk=, gap=, prefetch=, version=, if_*=)`
(`operator.rs:448-462`) maps to `ReadOptions`. `Operator.open(path, mode)` accepts **only `"rb"`
and `"wb"`**: `rb` builds a `Reader` and `into_std_read(range)`, `wb` builds a `Writer` with a
default 256 KiB chunk, anything else raises `Unsupported` (`operator.rs:339-390`). `File.seek`
works only on the reader side and may seek past EOF (`file.rs:278-313`).
`Operator.list(path, limit=, start_after=, recursive=, versions=, deleted=)` returns a
`BlockingLister` with `__next__` (`operator.rs:804-818`, `lister.rs:36-60`); `scan` is recursive
`list`. `delete`, `remove_all`, `copy`, `rename`, `create_dir`, `exists`, `stat`, `capability`,
`layer` are one-to-one with the operator; `AsyncOperator` mirrors every method (`:1075-1996`).

**Lesson for vfs:** opendal's kernel is thirteen path-keyed functions returning four typed handles
(reader, writer, lister, deleter) whose per-call arguments carry the range, the chunk, the page
hint and the precondition, with a per-flag `Capability` the layers read to refuse, retry, throttle
or simulate — and its SQL services show a row-per-path store serving ranged reads by SQL `SUBSTR`
and chunked writes by buffering to one upsert.

---

## 4. Across the three — the common kernel, and where they split

**Common primitive set (INFERRED from §1–3).** All three reduce to five concerns, each a
path-keyed call:

| Concern | pyfilesystem2 | fsspec | opendal |
|---------|---------------|--------|---------|
| stat one | `getinfo` | derived from `ls(parent)` | `stat` |
| list one directory | `listdir` | `ls` | `list` → `Lister` |
| read body | `openbin("rb")` | `_open`/`cat_file` | `read` → `Reader(range)` |
| write body | `openbin("wb")` | `_open("wb")`/`pipe_file` | `write` → `Writer` |
| delete | `remove` + `removedir` | `rm_file` (+ `rmdir`, may be no-op) | `delete` → `Deleter` |

Count: five concerns; four to seven methods depending on whether stat/list and file/dir removal
are split (pyfilesystem2: 7; fsspec: 3–4 in practice; opendal: 11 required fns, 5 of them these
concerns, plus `create_dir`, `copy`, `rename`, `presign`, `info`, `capability`).

**Universally derived (READ in each):** walk/find, glob, recursive delete, directory copy,
move-as-copy-then-delete, `exists`/`isdir`/`isfile`, text-mode open, `read_bytes`/`write_bytes`.
In all three, **rename is not a kernel requirement**: pyfilesystem2 and fsspec derive it from
copy+delete with an optional fast path (`supports_rename` / `os.rename`); opendal makes it a trait
fn a backend may answer `Unsupported` with `rename: false`. `mkdir` is optional or simulated in
two of three.

**Where they disagree.**

- *Handles vs whole-body:* pyfilesystem2's only body verb is a seekable Python handle, and
  whole-body backends emulate it with a `BytesIO` cursor. fsspec exposes both — `cat_file(start, end)`
  and `pipe_file(value)` are the value verbs, and `AbstractBufferedFile` builds the handle on top of
  them. opendal's kernel has no cursor: a read is `read(range)`, a write is a session of
  `write(buf)…close()`; the Python `File` with `seek` is a binding-level veneer.
- *Path vs fd:* all three key every kernel call by path; the only fd-like objects are the body
  handles (opendal's four typed handles), never reused for stat/list/delete. INFERRED: none has an
  inode or fd table; FUSE adapters add one (fsspec `FUSEr.cache[counter]`, READ `fsspec/fuse.py:98-109`).
- *Sync vs async:* pyfilesystem2 is sync-only with an `RLock` per FS. fsspec is sync-first with an
  async subclass whose sync methods are generated. opendal is async-first (`impl Future` on every
  fn) with a `blocking` module; RFC `6189_remove_native_blocking` (READ filename) removed the
  native blocking path.
- *Pagination:* pyfilesystem2 slices client-side (`scandir(page=)`); fsspec never pages (`ls` is
  whole, cached in `DirCache`); opendal pages inside the lister (`PageContext.token`) and exposes
  only `limit`/`start_after` hints, declared per backend.
- *Batch:* only opendal has a batch verb shape in the kernel (`Deleter`, `BatchDelete`,
  `delete_max_size`); fsspec batches by running per-file coroutines under a window; pyfilesystem2
  has none.
- *Conditions and versions:* only opendal carries `if_match`, `if_none_match`, `if_not_exists`,
  `version` on read/write/delete/stat as kernel arguments with matching capability flags.

**Lesson for vfs:** the invariant across all three is five path-keyed concerns (stat, list,
read-body, write-body, delete) from which every traversal and bulk verb is derived; the real
design choice is not the verb list but the *body shape* — cursor handle (pyfilesystem2), value
plus optional range (fsspec), or range-per-call plus write-session (opendal) — and only opendal
makes paging, batching and preconditions kernel facts with per-backend flags.

---

## 5. Errors, and how a POSIX/FUSE adapter maps them

**pyfilesystem2 (READ `fs/errors.py:73-363`).** A class tree rooted at `FSError`:
`FilesystemClosed`, `CreateFailed`, `PathError` (`NoSysPath`, `NoURL`, `InvalidPath`,
`InvalidCharsInPath`), `OperationFailed` (`Unsupported`, `RemoteConnectionError`,
`InsufficientStorage`, `PermissionDenied`, `OperationTimeout`, `RemoveRootError`,
`IllegalDestination`), `ResourceError` (`ResourceNotFound`, `ResourceInvalid` →
`FileExpected`/`DirectoryExpected`, `FileExists`, `DestinationExists`, `DirectoryExists`,
`DirectoryNotEmpty`, `ResourceLocked`, `ResourceReadOnly`). Each essential method's docstring
lists what it raises (`openbin`: `FileExpected`, `FileExists`, `ResourceNotFound`; READ
`fs/base.py:220-254`). The errno bridge runs OS → FS in `OSFS` via `convert_os_errors`, a dict
`errno → FSError` (`EACCES`→`PermissionDenied`, `ENOENT`/`EFAULT`/`ESRCH`→`ResourceNotFound`,
`ENOTEMPTY`→`DirectoryNotEmpty`, `EEXIST`→`FileExists`, `EISDIR`/`EINVAL`→`FileExpected`,
`ENOSPC`→`InsufficientStorage`, `ENETDOWN`/`ECONNRESET`→`RemoteConnectionError`,
`ENAMETOOLONG`→`PathError`, `EOPNOTSUPP`/`ENOSYS`→`Unsupported`, default `OperationFailed`),
with a `directory=True` variant remapping `ENOTDIR`/`EEXIST`/`EINVAL` to the directory classes
(READ `fs/error_tools.py:30-90`). INFERRED: the table is invertible, but pyfilesystem2 ships no
FUSE adapter.

**fsspec (READ).** No error hierarchy of its own: the base class raises builtin
`FileNotFoundError`, `FileExistsError`, `OSError(ESPIPE)`, `ValueError`, `NotImplementedError`
(`spec.py:808`, `:942`, `:2161`, `:2073`). The FUSE adapter `FUSEr(Operations)` (READ
`fsspec/fuse.py:17-140`) imports exactly two errnos: `getattr` turns `FileNotFoundError` into
`FuseOSError(ENOENT)` (`:33-35`) and `unlink` turns any `OSError` into `FuseOSError(EIO)`
(`:118-123`); every other exception escapes to fusepy, which INFERRED reports `EIO`. Its handle
model is a `dict[int, file]` counter (`:98-109`); `open` with a write flag opens `"wb"`, and
`write(offset)` does `f.seek(offset)` — which `AbstractBufferedFile.seek` refuses in write mode
(`spec.py:2161`) — so random writes fail, and `truncate` to a non-zero length raises
`NotImplementedError` (`fuse.py:111-116`). The adapter is a sequential-write, whole-rewrite
mapping, not a POSIX one.

**opendal (READ `core/core/src/types/error.rs`).** One `Error` struct: an `ErrorKind` enum of
thirteen variants — `Unexpected`, `Unsupported`, `ConfigInvalid`, `NotFound`,
`PermissionDenied`, `IsADirectory`, `NotADirectory`, `AlreadyExists`, `RateLimited`,
`IsSameFile`, `ConditionNotMatch`, `RangeNotSatisfied`, `Conflict` — plus `with_operation`,
`with_context(key, value)` (path, service), a `set_source` chain, and a
`status: Permanent | Temporary` flag (`:147`, `:364-412`, `:458`) that `RetryLayer` keys on. The
Python binding maps each kind to its own exception class under `opendal.exceptions`, `Unexpected`
as fallback (READ `bindings/python/src/errors.rs:24-110`). The in-tree `object_store` adapter maps
`NotFound`, `Unsupported`, `AlreadyExists`, `ConditionNotMatch` to that crate's variants and all
else to `Generic` (READ `integrations/object_store/src/utils.rs:28-70`). **The FUSE binary (`ofs`)
is no longer in the tree** — `CHANGELOG.md` records "remove bin/{oli,ofs} (#6689)" and "remove ofs
behavior tests" (READ `core/core/CHANGELOG.md:1059,1070`), and this shallow clone holds no history
for it (EXECUTED `git log --all -- bin/ofs` returned nothing), so its errno table could not be read.

**Lesson for vfs:** a flat, closed kind enum with context fields and a `temporary` bit (opendal)
is what layers and adapters actually switch on, and both Python projects show an errno bridge is a
small static table — but fsspec's two-errno FUSE adapter shows how little POSIX fidelity survives
when the kernel's write side is sequential-only.

---

## Design facts for the synthesis

1. READ — pyfilesystem2's whole API derives from exactly seven abstract methods: `getinfo`,
   `listdir`, `makedir`, `openbin`, `remove`, `removedir`, `setinfo` (`fs/base.py:146-315`).
2. READ — fsspec's base class has no abstract methods; `ls` is the only metadata primitive, and
   `info` is derived by listing the parent (`fsspec/spec.py:775-808`).
3. INFERRED — fsspec's default `_open` and `cat_file` are mutually recursive, so a backend's
   practical minimum is `ls` + (`_open` or `cat_file`) + `rm_file` (+ `cp_file`).
4. READ — opendal's kernel is thirteen functions and six typed handles; the read range, write
   chunk, list limit/start_after and every precondition are per-call arguments, not modes
   (`core/core/src/raw/service.rs:109-281`, `types/options.rs`).
5. READ — all three key every kernel call by path; the only stateful objects are body handles,
   and none has an fd/inode table.
6. READ — rename is a kernel requirement in none of the three: derived from copy+delete
   (pyfilesystem2 `fs/base.py:1152-1205`, fsspec `spec.py:1362-1385`) or declarable `Unsupported`.
7. READ — only opendal pages listings (`PageContext.token`), behind per-backend
   `list_with_limit`/`list_with_start_after` flags; fsspec's `ls` is whole and cached in
   `DirCache`; pyfilesystem2 slices client-side.
8. READ — opendal's sqlite/postgresql services are row-per-path whole-value stores with
   `list: false`; they serve ranged reads with SQL `SUBSTR` and chunked writes by buffering to one
   upsert on `close` (`core/services/sqlite/src/{core,writer}.rs`).
9. READ — opendal layers (retry, concurrent-limit, logging, simulate, correctness-check) wrap the
   kernel via `Layer::apply_service` and never change it; missing verbs are refused by capability
   name or synthesized from `list` + `write_can_empty`/`delete`.
10. READ — fsspec's FUSE adapter maps two errnos (`ENOENT`, `EIO`), refuses random writes
    (`seek` in write mode is `ESPIPE`) and non-zero `truncate`; opendal's `ErrorKind` is thirteen
    closed variants plus a `temporary` bit that retry keys on.
