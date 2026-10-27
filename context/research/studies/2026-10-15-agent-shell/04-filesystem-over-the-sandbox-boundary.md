# The filesystem over the sandbox boundary: how a guest's file calls become vfs verbs

- **Date:** 2026-10-15
- **Researcher:** S4 (vfs agent-shell study)
- **Question:** How does a sandboxed guest program's file access (`open`, `read`, `write`, `readdir`, `stat`, `rename`, `unlink`) resolve to vfs verbs with the caller's authority, for every guest kind we may host — a WASI preview1 binary, a WASI 0.2 component, CPython on wasm, Pyodide/Emscripten, QuickJS, Monty?
- **Clones read (all at the commits in `refresh.log`, 2026-10-15):** `WASI` 463701e (preview1 witx via `git show origin/wasi-0.1:`; 0.2 wit via `git show v0.2.9:`; 0.3.2 on main), `browser_wasi_shim` b068ec2, `wasi-virt` 448f6df, `wasmtime-py` 280ce73 (checkout) and the installed wheel 49.0.0 (executed), `llm-wasm-sandbox` 680c927, `amla-sandbox` 169384f (Python side only; the bundled Rust runtime is AGPL/BUSL and was not read), `just-bash` 9ab0e0d, `bashkit` b7904a4, `lifo` 5a35d05, `deepagentsjs` 9f3bfd5, `cpython` fdec4df, `pyodide` adc5b63, `RustPython` 88f5189, `componentize-py` 9ff99da, `monty` 2bb9f08a (v1.1.0), `quickjs-rs` 278cf32 (v0.2.5), `quickjs-ng` 9b06171.
- **Evidence labels:** EXECUTED (I ran it; script and output are under `experiments/s4/`), READ (I read it in the clone at the cited line), FETCHED (web, with URL and date), INFERRED (my conclusion from the above). Anything unverified is marked `[NOT VERIFIED: why]`.
- **Experiments folder:** `experiments/s4/` — `shim.py` (the preview1-over-vfs shim), `scenarios.py` + `scenarios.json` (34 single-operation guest runs), `interpreters.py` + `interpreters.json` (real CPython and QuickJS binaries), `trap_race.py` (the wasmtime-py thread-safety test), `imports_survey.py` + `imports.json`, `catfile/` and `fsops/` (the two Rust guests, source + `bin/*.wasm`), `run1.json`.

---

## Summary

The mapping works, and it was executed, not just read. A 250-line Python shim that implements the `wasi_snapshot_preview1` import module over the live `VirtualFileSystem` ran a 20-line Rust program, then a 34-operation Rust test program, then the real **CPython 3.12 `python.wasm` (26 MB) and the real `qjs` WASI binary** — all reading, writing, listing, stat-ing, renaming and deleting rows in an `InMemoryStorage` through ordinary vfs verbs, with exit codes, errno values and the trash all behaving. **Whole-file staging holds**: one `path_open` is one `read` (5 SQL statements), one `fd_close` of a dirty buffer is one `write` (16 statements), a directory open is one `ls` (6 statements), and nothing between open and close touches the database. The July memo's "17 must be real + 7" checklist is confirmed exactly: Rust guests import 16–21 preview1 functions, `qjs` 23, CPython 43 of 46 — but the union of what all three actually *called* is the memo's 24 names and no others (one stubbed call, `path_readlink`, was harmless). Two things the memo could not know: (1) the **guest's filestat has no mode bits at all** — preview1 carries only a filetype, and CPython printed `st_mode == 0o100000`; so "mode bits synthesized from kind + rung" is not a vfs decision, the guest's libc does it; (2) **wasmtime-py is not safe for concurrent guests in one process** — I reproduced the trap-global race (128 of 600 concurrent runs received the *other* thread's exit code) and a second race in the installed wheel's handle slab. The filesystem ABI we should expose to every guest kind is the vfs verb set itself, not POSIX; the preview1 shim, the Emscripten `node_ops` adapter, Monty's `AbstractOS` handler and QuickJS's host-function table are four thin adapters over that one interface. Where ours differs from just-bash's `IFileSystem` and Node 26's `node:vfs` provider: rows (text XOR bytes, with a MIME type), an authority value on every call, delete-to-trash, a version per write, and no mode, uid, symlink or hard link at all.

---

## Findings

### 1. Preview1 is 46 functions; the observed demand is 16–43, and the real floor is 25 (EXECUTED, READ)

READ: `WASI:preview1/witx/wasi_snapshot_preview1.witx` on `origin/wasi-0.1` declares 46 `@interface func` exports (counted with `grep -c`). The preview1 application ABI (`WASI:application-abi.md`, same branch) says a *command* exports `_start`, must export `memory`, gets fds 0/1/2 as streams, and "may" get preopen fds inspectable with `fd_prestat_get`/`fd_prestat_dir_name`.

EXECUTED (`imports_survey.py` → `imports.json`): the preview1 imports each binary actually declares:

| Binary | Bytes | preview1 imports |
|---|---|---|
| `catfile` (Rust, this study) | 118,919 | 16: args_get args_sizes_get environ_get environ_sizes_get fd_close fd_fdstat_get fd_filestat_get fd_prestat_dir_name fd_prestat_get fd_read fd_readdir fd_seek fd_write path_filestat_get path_open proc_exit |
| `fsops` (Rust, this study) | 159,382 | 21: the 16 above + fd_filestat_set_size path_create_directory path_remove_directory path_rename path_unlink_file |
| `quickjs.wasm` (qjs-wasi, from the llm-wasm-sandbox clone) | 1,427,671 | 23: + clock_time_get fd_fdstat_set_flags path_filestat_set_times poll_oneoff (and the file verbs) |
| `python.wasm` (CPython 3.12, WLR build, same clone) | 26,267,204 | 43: all 46 minus `fd_fdstat_set_rights`, `fd_renumber`, `proc_raise` |

EXECUTED (`interpreters.json`, `scenarios.json`): what each guest *called* at runtime, over the whole scenario set:

- Rust guests (all 34 scenarios): args_get, args_sizes_get, fd_close, fd_fdstat_get, fd_filestat_get, fd_filestat_set_size, fd_prestat_dir_name, fd_prestat_get, fd_read, fd_readdir, fd_seek, fd_write, path_create_directory, path_filestat_get, path_open, path_remove_directory, path_rename, path_unlink_file, proc_exit — 19 functions, never environ_* (Rust reads env lazily).
- CPython: 22 functions: the above plus clock_time_get (2 calls), environ_get/environ_sizes_get (**445 calls each** — one pair per `getenv`; wasi-libc does not cache), fd_tell, random_get, and one **stubbed** call, `path_readlink` (answered `NOSYS` 52; CPython carried on).
- `qjs`: 13 functions incl. clock_time_get ×3.

INFERRED: the July memo's "17 must be real + 7 for directories and writes" is confirmed exactly, not revised: the union of every preview1 function *called* across Rust std, CPython and `qjs` is 24 names, and it is the memo's 24 to the letter (the shim implemented six more — `fd_fdstat_set_flags`, `fd_renumber`, `fd_sync`, `fd_datasync`, `sched_yield`, `fd_advise` — and none was called). Every other preview1 name may answer `NOSYS` (52) as long as it *returns an int*. The functions CPython imports but never called in a file-centric script — `fd_pread`/`fd_pwrite`, `fd_sync`/`fd_datasync`, `fd_advise`/`fd_allocate`, `path_link`/`path_symlink`, `poll_oneoff` (only `time.sleep`), `sock_*` — can stay stubs until a program proves it needs them.

### 2. The preopen handshake and path judgment, as observed (EXECUTED, READ)

EXECUTED (`run1.json`, `scenarios.json`, every run): with one preopen `"/"` at fd 3, wasi-libc called `fd_prestat_get(3)` → ok, `fd_prestat_dir_name(3)`, then `fd_prestat_get(4)` → my shim answered `EBADF` (8) and the scan stopped; `_start` proceeded. This is exactly the rule the memo cited (browser_wasi_shim `src/wasi.ts:329-339` returns BADF for an unknown fd, READ).

EXECUTED: every guest path arrived **relative to dirfd 3**: `/data/hello.txt` → `path_open(dirfd=3, "data/hello.txt")`; a relative guest path `data/hello.txt` arrived identically (wasi-libc's cwd is the first preopen; `std::env::current_dir()` printed `"/"`, scenario `cwd`). `/data/../../etc/passwd` and `../etc/passwd` both arrived as paths containing `..` that escape the base; the shim refused them with `NOTCAPABLE` (76) before any verb ran (0 SQL statements), and Rust reported "Capabilities insufficient (os error 76)".

READ, the spec's own words for what the judgment must be: WASI 0.2/0.3 `types.wit` preamble (`WASI:proposals/filesystem/wit/types.wit:12-19`): "All paths in WASI are relative paths ... If a `path` argument ... starts with `/`, or if any step of resolving a `path`, including `..` and symbolic link steps, reaches a directory outside of the base directory ... the function fails with `error-code::not-permitted`." `path-resolution.md` (same dir, lines 12-21): "it's not permitted to use paths that temporarily step outside the sandbox with something like `../../../stuff/here`, even if the final resolved path is back inside the sandbox". Preview1 has no such sentence; `NOTCAPABLE` is what browser_wasi_shim chose (`src/fs_mem.ts:574-587`, READ) and it is what wasi-libc/Rust map to a sensible message. INFERRED: for vfs the rule is the same and it is cheap — the preopen is `/`, so `..` past the root is the only escape and it is refused by string arithmetic before vfs is consulted; even a miss would land inside vfs's own namespace, the second wall the memo named.

EXECUTED: the guest could list `/.vfs/trash` (`scenario "hidden /.vfs"`: `ls` returned the two trashed names, `made` and `moved.txt`). The shim does nothing to hide reserved trees today; that is a fork (§Forks, Q3).

### 3. Whole-file staging holds, with one verb per open (EXECUTED)

The shim (`experiments/s4/shim.py`): `path_open` stages the whole row; `fd_read`/`fd_seek`/`fd_write`/`fd_filestat_set_size` run on an in-host `bytearray` plus an offset; `fd_close` (or `_start` returning, or `proc_exit`) writes a dirty buffer back with one `write`. SQL statements were counted on the SQLAlchemy engine (`before_cursor_execute`) and attributed to the verb in flight. First version probed with `stat` before every open; the final version issues **one verb per open** and classifies the verb's own `ResultError` instead (`vfs.not_found` → ENOENT, `vfs.wrong_kind` → directory → `ls`). The cost table (final run, `scenarios.json`; InMemoryStorage is the same `DatabaseStorage` code path production engines run, so the statement counts transfer):

| Guest operation (Rust std) | Verbs issued | SQL statements | Bytes guest↔host | Result |
|---|---|---|---|---|
| `cat` 27-byte file | read 1 | 5 | 27 out | exit 0 |
| `cat` missing | read 1 | 5 | 0 | errno 44 ENOENT, exit 2 |
| `cat` a directory | read 1, ls 1 | 11 | 0 | errno 31 EISDIR |
| `stat` file / dir | stat 1 | 5 | 0 | len, is_dir, mtime ok |
| write new 6 bytes (`fs::write`) | write 1 | 16 | 6 in | version 1 |
| overwrite | write 1 | 16 | 7 in | version 2 |
| append 5 bytes | read 1, write 1 | 21 | 5 in | version 3, content concatenated |
| patch 2 bytes at offset 2 | read 1, write 1 | 21 | 2 in | version 4, `seZZnd\n...` |
| range read 6 bytes at offset 6 | read 1 | 5 | 6 out | `from v` |
| truncate to 3 (`set_len`) | read 1, write 1 | 21 | 0 | version 5, `seZ` |
| read a 1,024-byte bytes row | read 1 | 5 | 1,024 out | head `[0,1,2,3]` |
| write 4 bytes incl. `\x00\xff` via stdin→file | write 1 | 16 | 4 in | lands as a **bytes** row; read back `[0,1,255,254]` |
| `mkdir` | mkdir 1 | 13 | | |
| `mkdir` existing | mkdir 1 | 6 | | errno 20 EEXIST |
| `read_dir` of 8 entries | ls 1 | 6 | 67 out | one `fd_readdir` |
| `rename` | move 1 | 23 | | version bumps |
| `remove_file` | stat 1, delete 1 | 14 | | row now in `/.vfs/trash` |
| `remove_dir` empty / non-empty | stat 1, delete 1 | 16 / 13 | | ok / errno 55 ENOTEMPTY |
| `cat` 8 MiB text row | read 1 | 5 | 8,388,600 out | 0.0135 s wall (noted, not asserted) |
| read 1 byte at offset 4,000,000 of the 8 MiB row | read 1 | 5 | 1 out | still staged 8 MiB |
| append 4 bytes to the 8 MiB row | read 1, write 1 | 21 | 4 in | wrote back 8,388,604 bytes, 0.039 s |
| `read_dir().count()` over 2,000 entries | ls 1 | 6 | | **17** `fd_readdir` calls (4,096-byte guest buffer), one verb |
| stdin → uppercase stdout; env; `exit 7` | none | 0 | | exit 7 surfaced |

INFERRED, the three limits of staging the numbers expose: (a) a 1-byte read of a large row costs the whole row (8 MiB staged for 1 byte) — acceptable for the CLI class (jq, grep, cat read everything anyway) and wrong for a seek-heavy program (sqlite3 over a database file); (b) a tiny append to a large row is a read-modify-write of the whole row, twice the row in bytes across the boundary and a new version holding a full copy — vfs's `edit` verb exists precisely for this and the shim cannot reach it from a byte interface; (c) two `open`s of the same path in one guest get two independent buffers and the last `fd_close` wins — the same hazard POSIX has without `O_APPEND`, only coarser, because the lost update is the whole file rather than a byte range. None of these is a correctness bug for the program class the memo targets; all three are the arguments for the "chunked streaming" fork (§Forks, Q2).

### 4. The errno plumbing is real and vfs already names it (EXECUTED, READ)

READ: `src/vfs/results/kinds.py:58-91` annotates every `ErrorKind` with its POSIX errno in a comment — `not_found` ENOENT, `exists` EEXIST, `wrong_kind` ENOTDIR/EISDIR, `not_empty` ENOTEMPTY, `permission_denied` EACCES/EPERM, `read_only` EROFS, `unsupported` ENOSYS/ENOTSUP, `invalid` EINVAL, `cross_mount` EXDEV, `busy` EBUSY, `conflict` ESTALE, `unavailable` EIO, `timeout` ETIMEDOUT, `cancelled` ECANCELED/EINTR. The preview1 numbering (`browser_wasi_shim:src/wasi_defs.ts:12-88`, READ, matches the witx order): ENOENT 44, EEXIST 20, ENOTDIR 54, EISDIR 31, ENOTEMPTY 55, EACCES 2, EPERM 63, EROFS 69, ENOSYS 52, ENOTSUP 58, EINVAL 28, EXDEV 75, EBUSY 10, EIO 29, ESPIPE 70, EBADF 8, NOTCAPABLE 76.

EXECUTED: the guest-visible messages prove the chain `vfs ErrorKind → errno → libc → Rust io::Error`: "No such file or directory (os error 44)", "Is a directory (os error 31)", "File exists (os error 20)", "Directory not empty (os error 55)", "Capabilities insufficient (os error 76)". An unmapped kind fell to EIO (29); that is what the bytes-row read produced before I asked for the `data` column (Finding 7).

### 5. Real CPython and real QuickJS ran over vfs (EXECUTED)

`interpreters.py`: the two binaries come read-only from the `llm-wasm-sandbox` clone (`bin/python.wasm`, `bin/quickjs.wasm`); nothing was copied into the vfs repo.

**CPython 3.12.0, `sys.platform == "wasi"`**, argv `python -I -X utf8 -c <script>`, env `PYTHONUTF8=1 PYTHONHASHSEED=0 LC_ALL=C.UTF-8`, one preopen `/`:

- Compile 0.84 s (26 MB module; `Module.serialize` would cache this), run 0.17 s, exit 0, no trap.
- The script read `/data/hello.txt`, wrote `/data/py.out` (one `write`), `os.listdir('/data')` (one `ls`), `os.stat` (`st_size 27`, **`st_mode 0o100000`**), `os.mkdir`, `os.rename`, `os.remove`, `os.rmdir` — after which `/.vfs/trash` held `/data/pydir` and `/data/pydir/moved.out`.
- Verbs: read 4, stat 11, write 1, ls 1, mkdir 1, move 1, delete 2; 154 SQL statements in total (read 20, stat 55, write 16, ls 6, mkdir 13, move 24, delete 20).
- **What CPython touches at startup through the shim** (the full trace is in `interpreters.json`): `path_open("pyvenv.cfg")` ×2, `path_open("pybuilddir.txt")`, `path_filestat_get` on `Modules/Setup.local`, `lib/python312.zip`, `lib/python3.12/os.py`, `lib/python3.12/os.pyc`, `lib/python3.12/lib-dynload`, `pyvenv.cfg` ×2 — the `getpath` landmark search, nine probes, all answered ENOENT by vfs. The interpreter still found its standard library, because the WLR build embeds it: `strings python.wasm` contains `wasi_vfs_pack_fs` and `wasi_vfs_embed_linked_storage_new_dir` (EXECUTED), the wasi-vfs symbols, and llm-wasm-sandbox fetches this binary with `scripts/fetch_wlr_python.ps1` (READ, `docs/PUBLISHING.md:25`). So the stdlib never crossed the vfs boundary; only the user's files did.
- One stubbed import was called: `path_readlink` (CPython resolving its own executable path); `NOSYS` was harmless.
- `environ_get`/`environ_sizes_get` were called 445 times each. Cheap, but a reminder that the WASI env is a hot path and must never carry a secret (memo §5 risk 4).

**quickjs-ng `qjs` (WASI build)**, argv `qjs --std -m /data/main.mjs` where the module imports `qjs:std` and `qjs:os` (quickjs-ng's names — the first attempt with `'std'` failed with "could not load module filename 'std'" and the shim saw `path_open("std")`: the module loader looks for a *file* first):

- Compile 0.13 s, run 0.04 s, exit 0. The script itself was loaded from vfs (`path_open("data/main.mjs")` → read), `std.loadFile('/data/hello.txt')` → read, `std.open('/data/js.out','w')` → write on close, `os.readdir('/data')` → ls (it printed `.` and `..` too — preview1 readdir conventionally includes them), `os.stat` → `mode 100000`.
- Verbs: read 2, write 1, ls 1, stat 1; 37 SQL statements.

INFERRED: the preview1 shim is one adapter for three guest kinds at once — native wasi binaries, CPython-on-WASI, and QuickJS-on-WASI — because all three sit on wasi-libc. `quickjs-libc`'s `std`/`os` modules call libc, which calls preview1, which calls us (READ: `quickjs-ng:quickjs-libc.c` registers `open`, `loadFile`, `writeFile`, `readdir`, `stat`, `remove`, `rename`, `mkdir`, `readlink`, `symlink`, `realpath`, `getcwd`, `chdir`, `exec`, `pipe`, `dup2` …; the `exec`/`pipe`/`popen` family would hit stubs and fail cleanly).

### 6. There are no mode bits to synthesize: preview1 has filetype only (READ, EXECUTED)

READ: `WASI:preview1/witx/typenames.witx` `$filestat` = `dev u64, ino u64, filetype u8, nlink u64, size u64, atim, mtim, ctim` (64 bytes; offsets 0/8/16/24/32/40/48/56 per `browser_wasi_shim:src/wasi_defs.ts:283-291`). `$filetype` = unknown 0, block_device 1, character_device 2, directory 3, regular_file 4, socket_dgram 5, socket_stream 6, symbolic_link 7. `$fdstat` = filetype u8 @0, fdflags u16 @2, rights_base u64 @8, rights_inheriting u64 @16 (24 bytes). No uid, gid or permission field exists anywhere in preview1; WASI 0.2's `descriptor-stat` likewise has type, link-count, size and three optional timestamps (`types.wit:118-143`).

EXECUTED: CPython printed `oct(st_mode) == '0o100000'` (S_IFREG with zero permission bits) and `qjs` printed `mode 100000`; Rust's `metadata().permissions().readonly()` printed `true` for both a file and a directory. INFERRED: wasi-libc builds `st_mode` from the filetype alone and leaves permission bits zero; Rust's std derives `readonly` from that `[NOT VERIFIED: the Rust std wasi fs source was not located in the installed rust-src 1.95 layout]`. The consequence for the design: the brief's "mode bits synthesized from kind + ladder rung" is not something the host does in preview1 or 0.2 — there is no field to put it in. The rung reaches the guest as an **errno** on the operation (EACCES / EROFS on write, ENOENT on a row the caller cannot even list), never as a bit in `stat`. Programs that `chmod` get a no-op (CPython itself ignores `chmod` on WASI: `cpython:Modules/posixmodule.c:4174-4178` "WASI SDK 15.0 does not support chmod. Ignore missing syscall for now.", READ) — the shim can answer `fd_filestat_set_times`/`path_filestat_set_times` with success and store nothing.

### 7. Binary rows need an explicit column; write-back must decide text vs bytes (EXECUTED, READ)

EXECUTED (probe in the session, then `scenarios.json`): `fs.read(path="/data/bytes.bin")` on a row written with `data=` returned no observation and the error `vfs.unavailable: "Unavailable: the binary awaits a rendering; run reindex"` (`render_status='pending'`). `fs.read(..., columns=frozenset({"data"}))` returned the 1,024 bytes. The shim therefore reads every open with `columns={"content","data","kind","size_bytes","mime_type","version","updated_at"}`; a text row answers `content` with `data=None`, a bytes row answers `data`. On close the shim tries `utf-8` and writes `content=` on success, `data=` on failure; the 4-byte `\x00\x01\xff\xfe` write landed as a bytes row (`mime_type application/octet-stream`) and read back exactly. READ: `Entry` carries `content: str | None` XOR `data: bytes | None` with `source: "text" | "bytes"` (`src/vfs/models/entry.py:88-93`).

INFERRED: the sniff is the wrong long-term rule (a UTF-8-valid PNG is impossible, but a UTF-8-valid `.bin` is not, and a text row with a stray byte would flip to bytes). The guest cannot tell us; the host can: the *program table entry* that launched the program, or the extension of the target path, or an explicit `--binary` on the shell's redirect, should decide. This is a decision for the content-channel ADR, not the shim.

### 8. Preview1 is synchronous, vfs verbs are coroutines: the bridge is a thread hop, and every precedent does the same (EXECUTED, READ)

EXECUTED: the shim runs `_start` on a worker thread (`loop.run_in_executor`) and every host function that needs a verb calls `asyncio.run_coroutine_threadsafe(coro, loop).result()`. wasmtime-py's ctypes calls release the GIL, so the event loop keeps running while the guest blocks; it worked for every scenario including the 26 MB CPython run.

READ, the precedents, which all face the same shape: just-bash runs CPython-Emscripten in a `worker_thread` and bridges its synchronous Emscripten FS to the async `IFileSystem` over a `SharedArrayBuffer` + `Atomics` protocol (`just-bash:packages/just-bash/src/commands/worker-bridge/protocol.ts:2-210`; the custom Emscripten filesystem `HOSTFS` in `commands/python3/worker.ts:396-412` implements `node_ops`/`stream_ops` over `backend.readFile`/`backend.writeFile`, whole-file, with an `EFBIG` cap at `maxFileSize`, `worker.ts:460-466`, `553-580`). Pyodide's `mountNativeFS` reuses MEMFS for all synchronous `node_ops` and reconciles with the async File System Access API only in `syncfs` (`pyodide:src/js/nativefs.ts:37-60`, `api.ts:569-595`) — a different trade: writes are invisible to the host until an explicit sync. Monty's host handler is a plain callable with an `is_async` flag; under `AsyncMonty` it may return a coroutine (`monty:crates/monty-python/python/pydantic_monty/__init__.py:369-393`).

### 9. wasmtime-py cannot host concurrent guests in one process: two races, one reproduced from the memo and one new (EXECUTED, READ)

EXECUTED (`trap_race.py`): two threads each ran `fsops exit 11` / `fsops exit 22` through `proc_exit` → `raise GuestExit(code)`; linker setup serialized under a lock, only `_start` concurrent.

```
rounds per thread: 300     thread expecting 11: {22: 35, 11: 233, -1: 32}   thread expecting 22: {-1: 41, 22: 239, 11: 20}   mismatches: 128
rounds per thread: 2000    mismatches: 921 of 4000
```

A thread received the *other* guest's `GuestExit` (wrong code) or a bare `Trap("python exception")` with the Python exception already consumed (`-1`). READ, the cause is unchanged in the checkout: `wasmtime-py:wasmtime/_func.py:14` `LAST_EXCEPTION: Optional[Exception] = None` is module-global; the trampoline stores into it at `:213-214` and `maybe_raise_last_exn` reads-and-clears it at `:245-249`; the ctypes boundary releases the GIL in between.

EXECUTED, the new one: the first version of the race test (without the setup lock) crashed inside `define_func` with `TypeError: list indices must be integers or slices, not tuple` at `_slab.py:22` of the **installed wheel 49.0.0**, whose `Slab.allocate` keeps a free list across three statements. READ: the checkout at 280ce73 has replaced it with a dict and an `itertools.count` (`wasmtime/_slab.py:8-48`, docstring: "safe to use from many threads"), so a release after 49.0.0 fixes the slab race but not the trap global. quickjs-rs hit the same slab race independently (`quickjs-rs:quickjs_rs/_engine.py:290-294`: "we do NOT define_func per instance (that raced wasmtime-py's global slab)").

INFERRED: until the trap global is thread-local upstream, a Python host runs **one guest at a time per process** (a lock around `_start`, which also serializes a 26 MB CPython run against a 100 KB `cat`), or one process per concurrent guest. This is the strongest single argument in the Python-vs-Rust fork (§Forks, Q1).

### 10. WASI 0.2 and 0.3 change the shape, not the semantics (READ)

READ (`git show v0.2.9:proposals/filesystem/wit/types.wit`): the `descriptor` resource replaces fds and rights bits. `read(length, offset) -> result<tuple<list<u8>, bool>, error-code>` (the bool is EOF), `write(buffer, offset) -> filesize`, `read-via-stream(offset) -> input-stream`, `write-via-stream`, `append-via-stream`, `read-directory() -> directory-entry-stream` whose `read-directory-entry() -> option<directory-entry>` replaces cookies, `stat`, `stat-at(path-flags, path)`, `open-at(path-flags, path, open-flags, descriptor-flags) -> descriptor`, `create-directory-at`, `unlink-file-at`, `remove-directory-at`, `rename-at(old, new-descriptor, new)`, `symlink-at`, `link-at`, `readlink-at`, `set-size`, `set-times`, `sync`, `sync-data`, `advise`, `get-flags`, `get-type`, `is-same-object`, `metadata-hash`. `open-flags` = create, directory, exclusive, truncate; `path-flags` = symlink-follow; `descriptor-flags` = read, write, file-integrity-sync, data-integrity-sync, requested-write-sync, mutate-directory. `error-code` is a 37-member variant (access, already, bad-descriptor, busy, deadlock, quota, exist, file-too-large, illegal-byte-sequence, in-progress, interrupted, invalid, io, is-directory, loop, too-many-links, message-size, name-too-long, no-device, no-entry, no-lock, insufficient-memory, insufficient-space, not-directory, not-empty, not-recoverable, unsupported, no-tty, no-such-device, overflow, not-permitted, pipe, read-only, invalid-seek, text-file-busy, cross-device). `preopens.get-directories() -> list<tuple<descriptor, string>>` replaces the fd-3-and-up scan. On `main`, `wasi:filesystem@0.3.2` (`WASI:proposals/filesystem/wit/types.wit:1`, promoted by "Promote WASI 0.3 to the primary preview (#929)") makes the same methods `async` and returns `stream<u8>`/`future<result>`.

READ: wasmtime-py has a component-model `Linker` with `add_wasip2()` (host-backed WASI, same host-directory limitation as preview1's `WasiConfig`), `LinkerInstance.add_func`, `add_resource` and `define_unknown_imports_as_traps` (`wasmtime-py:wasmtime/component/_linker.py:67-106, 151-211`). Serving our own `wasi:filesystem` resource from Python through `add_resource`/`add_func` looks possible `[NOT VERIFIED: no test in the clone defines a resource-typed WASI interface from Python; not attempted]`. wasi-virt virtualizes the filesystem *into* the component as a static read-only index with optional host passthrough (`wasi-virt:virtual-adapter/src/io.rs:149-213`, `README.md` "Filesystem: Mount a read-only filesystem, configure host filesystem preopen remappings or pass-through") — no custom-provider hook, so it is a way to embed a stdlib in a component, not a way to reach vfs. componentize-py embeds CPython as a component and says so itself: "we do not yet include a virtual filesystem in the component" (`componentize-py:src/lib.rs:827-831`); its `wasi:filesystem/` imports pass to the host (`lib.rs:1317-1325`).

INFERRED: for us 0.2/0.3 is the *same adapter* with a nicer surface: `open-at` is `path_open` without rights bits; `read(length, offset)` on a staged buffer is trivial; `read-directory` is a materialized `ls` handed out one entry at a time; `not-permitted` is `NOTCAPABLE`; `cross-device` is `EXDEV`. Nothing in the mapping table changes.

### 11. The reference shim's design, confirmed line by line (READ)

`browser_wasi_shim`: `Fd` is the per-open object with every preview1 method defaulting to `NOTSUP` (`src/fd.ts:4-117`); `Inode` is identity + content with `path_open(oflags, rights, fdflags)` and `stat()` (`fd.ts:119-142`). `OpenFile` keeps `file_pos`; `fd_write` grows the backing array and writes at the cursor (`fs_mem.ts:135-150`); `File.path_open` empties the data on `OFLAGS_TRUNC` and seeks to the end on `FDFLAGS_APPEND` (`fs_mem.ts:537-556`); `fd_filestat_set_size` resizes (`fs_mem.ts:85-88`). Directory listing emits `.` (cookie 0 → d_next 1) and `..` (cookie 1 → d_next 2) then the entries at cookie-2 (`fs_mem.ts:195-240`); the dispatcher packs 24-byte heads (`d_next u64 @0, d_ino u64 @8, d_namlen u32 @16, d_type u8 @20`) + name until the buffer is full and sets `bufused = buf_len` on truncation so the guest re-asks with the last `d_next` (`wasi.ts:437-494`). `ConsoleStdout` reports `FILETYPE_CHARACTER_DEVICE` with only `RIGHTS_FD_WRITE` (`fs_mem.ts:791-795`). `PreopenDirectory.fd_prestat_get` returns the name (`fs_mem.ts:514-519`). My shim follows all of this; the 2,000-entry listing needing 17 `fd_readdir` round trips (4,096-byte guest buffer, ~24+name bytes per entry) is the cookie protocol working as designed.

### 12. The prior-art filesystem ABIs for agent shells (READ, FETCHED)

**just-bash `IFileSystem`** (`just-bash:packages/just-bash/src/fs/interface.ts:130-335`), async-only ("Sync method are not supported and must not be added"): `readFile(path, encoding?) → string`, `readFileBytes?(path) → ByteString`, `readFileBuffer(path) → Uint8Array`, `writeFile(path, string|Uint8Array)`, `appendFile`, `exists`, `stat → {isFile,isDirectory,isSymbolicLink,mode,size,mtime,dev?,ino?,identity?}`, `mkdir(path,{recursive})`, `createExclusive?(path,{mode,directory})` (the `mktemp` primitive, documented as a TOCTOU fix), `readdir → string[]`, `readdirWithFileTypes? → {name,isFile,isDirectory,isSymbolicLink}[]`, `rm(path,{recursive,force})`, `cp`, `mv`, `resolvePath`, `getAllPaths` (for glob), `chmod`, `symlink`, `link`, `readlink`, `lstat`, `realpath`, `utimes`. Entries are `{type:'file', content, mode, mtime}` / `directory` / `symlink` / lazy file. Four backends under `src/fs/`: `in-memory-fs`, `overlay-fs`, `mountable-fs`, `read-write-fs`. Whole-file everywhere: `cat` concatenates `readFile` results into one string (`commands/cat/cat.ts:113-146`). The threat model names the fs layer "TB2 — Interpreter → Filesystem" and relies on root containment, symlink default-deny and `sanitizeError` (`THREAT_MODEL.md:83, 123-131`).

**Node `node:vfs`** — FETCHED 2026-10-15: the proposal PR nodejs/node#61478 (Matteo Collina, opened 2026-01-22) is closed with "Most of it has been implemented and it landed in core"; the shipped docs at https://nodejs.org/api/vfs.html say the module was **added in Node v26.4.0, Stability 1, behind `--experimental-vfs`**. `vfs.create([provider])`, `VirtualFileSystem`, `VirtualProvider`, `MemoryProvider`, `RealFSProvider(root)`, `ZipProvider`, `ComposableProvider(layers)` (the overlay). A provider implements "the essential primitives, such as `open`, `stat`, `readdir`, `mkdir`, `rmdir`, `unlink`, `rename`" in sync/async pairs; `readFile`, `writeFile`, `exists`, `copyFile`, `access` are derived; capability flags `readonly`, `supportsSymlinks`, `supportsWatch`; file handles carry `read`, `write`, `fstat`, `ftruncate`, `close`. Mount points are allocated under `/dev/null/vfs/N` and `require`/`import` resolve through them. The docs say in so many words: "The VFS is not a sandbox or access-control mechanism." The deepagentsjs backend sits on the Vercel polyfill of the pre-merge API, whose `VirtualProvider` is **fd-based and synchronous** (`openSync`, `readSync(fd, buffer, offset, length, position)`, `writeSync`, `closeSync`, `statSync`, `fstatSync`, `readdirSync`, `mkdirSync`, `rmdirSync`, `unlinkSync`, `renameSync`, `readlinkSync`, `symlinkSync`, `realpathSync`, `truncateSync`, `utimesSync`, `chmodSync`; `deepagentsjs:libs/providers/node-vfs/src/node-vfs-polyfill.d.ts:33-150`).

**bashkit `FileSystem`** (`bashkit:crates/bashkit/src/fs/traits.rs:256-280`, async Rust): `read_file → Vec<u8>`, `write_file(&[u8])`, `append_file`, `mkdir(recursive)`, `remove(recursive)`, `stat`, `lstat`, `read_dir → Vec<DirEntry>`, `exists`, `rename`, `copy`, `symlink`, `read_link`, `chmod(u32)`, `set_modified_time`, plus `FileSystemExt` with `vfs_snapshot`/`vfs_restore`, `limits`, `usage`, `mkfifo`. The Python binding exposes an accessor (`bash.fs()` with `read_file`/`write_file`/`copy`/`exists`, `crates/bashkit-python/README.md:156-177`) and lazy Python-provided files (`PythonLazyFilesFs`, `src/lib.rs:805-930`), not a Python-implemented backend.

**lifo** (`lifo:packages/core/src/kernel/vfs/types.ts`): synchronous `VirtualProvider { readFile → Uint8Array, readFileString, writeFile?, exists, stat, readdir → Dirent[] }` and `MountProvider` adding `unlink, mkdir, rmdir, rename, copyFile`; an `INode` with `mode`, `mime?`, content-hash `blobRef` and a chunk manifest for files ≥ 1 MB; six error codes (ENOENT, EEXIST, ENOTDIR, EISDIR, ENOTEMPTY, EINVAL).

**Monty `AbstractOS`** (`monty:crates/monty-python/python/pydantic_monty/os_access.py:179-760`): `path_exists/is_file/is_dir/is_symlink`, `path_open(path, mode) → MontyFileHandle`, `path_read_text/read_bytes/write_text/write_bytes/append_text/append_bytes(path | handle)`, `path_mkdir(parents, exist_ok)`, `path_unlink`, `path_rmdir`, `path_iterdir`, `path_scan`, `path_stat → StatResult(size, mode, mtime)`, `path_rename`, `path_resolve`, `path_absolute`, `getenv`, `get_environ`, `date_today`, `datetime_now`, `urandom`, `time`, `sleep`. The sandbox never holds an fd: `MontyFileHandle` is "a plain data holder — Monty never gives the host a live OS file descriptor" (`_monty.pyi:352-406`). Host directories mount via `MountDir(host_path, virtual_path, mode='read-only'|'read-write'|'overlay')` backed by `cap_std` (`monty-fs/src/lib.rs` header); anything no mount covers goes to the `os=` handler (`_monty.pyi:759-761`).

Comparison (yes/no/notes):

| Family | just-bash | Node 26 `node:vfs` | bashkit | lifo | Monty `AbstractOS` | **vfs today** |
|---|---|---|---|---|---|---|
| whole-file read / write | yes / yes | derived | yes / yes | yes / yes | yes / yes | `read` / `write` |
| byte-range read, cursor | no (whole) | fd `read(pos)` | no | no | handle `position` | no (`edit` is text-anchored) |
| append | yes | via flags | yes | no | yes | no (read+write) |
| stat fields | mode,size,mtime,ino | `fs.Stats` synthetic | Metadata | mode,size,mime | size,mode,mtime | kind,size,version,hash,mime,times |
| readdir with types | yes (optional) | `withFileTypes` | yes | yes | iterdir/scan | `ls` rows (kind) at `list` rung |
| mkdir / rm / rename | yes | yes | yes | yes | yes | `mkdir` / `delete`→trash / `move` |
| symlink / hardlink | yes / yes | flag / yes | yes / no | no | is_symlink only | **no / no** |
| chmod / utimes | yes / yes | yes / yes | yes / yes | no | no | **no / no** (answer ok, store nothing) |
| text vs bytes bodies | string ∣ Uint8Array | Buffer | bytes | bytes (+mime) | str ∣ bytes | **row: content XOR data + mime_type** |
| authority on the call | no (host-trusted) | no ("not a sandbox") | no | no | no (per-feed mounts) | **`Authority` value on every verb** |
| trash on delete | no | no | no | no | no | **yes, `/.vfs/trash`, restorable** |
| versions on write | no | no | snapshots (whole fs) | no | no | **yes, one per write** |
| sync or async | async only | both | async | sync | sync, async under AsyncMonty | async |
| realpath / `..` rule | realpath, root containment | realpath | n/a | normalize | `path_resolve` | normalize; `..` past `/` refused by the shim |

### 13. What CPython-on-WASI and Pyodide need from a filesystem (READ)

CPython: the WASI build runs with the checkout mapped as `/` ("Map the checkout to / to load the stdlib from /Lib", `cpython:Platforms/WASI/__main__.py:20-26`); the import system stats and lists directories as a matter of course (`importlib/_bootstrap_external.py:148-161 _path_stat`, `:1414 _os.listdir`, `:1460 _os.scandir`) — one `path_filestat_get` per candidate and one `fd_readdir` per `sys.path` entry on first import. The non-test stdlib is 765 `.py` files plus 125 in `encodings/` (counted). `posixmodule.c` has only four `__wasi__` sites — `linkat` disabled (`:627-631`), `chmod` ignored (`:4174`), `posix_fallocate` excluded (`:13671`) — the rest is `configure`-time feature detection. Three ways to feed the stdlib: preopen it from vfs (765+ rows read through the shim on first import; a real cost), embed it with wasi-vfs as WLR does (what I ran; zero vfs traffic), or RustPython's `freeze-stdlib` (`RustPython:README.md:118-144`: `cargo build --target wasm32-wasip1 --features freeze-stdlib`, the stdlib inside the binary; its browser build has no filesystem at all, `crates/stdlib/src/lib.rs:72-76`).

Pyodide/Emscripten: an Emscripten filesystem is an object with `mount(mount)`, `createNode(parent, name, mode, dev)`, `node_ops` {getattr, setattr, lookup, mknod, rename, unlink, rmdir, readdir, symlink, readlink} and `stream_ops` {read, write, llseek, mmap, msync}, **all synchronous** (FETCHED 2026-10-15, https://raw.githubusercontent.com/emscripten-core/emscripten/main/src/lib/libmemfs.js). Pyodide exposes `pyodide.FS` and `FS.filesystems.{MEMFS, IDBFS, NODEFS, PROXYFS, WORKERFS}` (`pyodide:src/js/api.ts:160-176`), `mountNodeFS` (NODEFS over a host dir, `:629-648`), `mountNativeFS` (MEMFS + async `syncfs` reconcile, `:569-595`, `nativefs.ts`). just-bash's `HOSTFS` is the working precedent for "an Emscripten FS over an agent-shell filesystem": whole-file `readFile`/`writeFile` per node op, EFBIG cap, plus a Python-level `builtins.open`/`os.*` redirect to a `/host` prefix (`worker.ts:701-723`).

### 14. What the two Python sandboxes did and did not virtualize (READ)

llm-wasm-sandbox: `linker.define_wasi()` with `WasiConfig.preopen_dir(host_dir, "/app")` on a **real temp directory**, a read-only copy for data, stdout/stderr to log files, `store.set_fuel(2_000_000_000)` and `set_limits(memory 128 MB)` (`sandbox/host.py:120-180`, `policies.py:20-41`). Nothing is virtualized: the guest sees real host directories, files come back by reading the temp dir. amla-sandbox (Python side): `_define_minimal_wasi` provides only `clock_time_get`, `random_get`, `fd_write` (stderr), `environ_*`, `fd_prestat_get → EBADF`, `sched_yield`, `proc_exit`; `fd_filestat_get`/`path_filestat_get` are `NOSYS` (`src/amla_sandbox/runtime/wasm.py:648-865`). Its "/workspace" lives inside the guest's own in-memory VFS and is filled through its SDK (`fs.writeFile('/workspace/...')` in `examples/`), never through WASI. Neither is a precedent for our question; both confirm that `WasiConfig` cannot be bent to a virtual store.

---

## What this means for vfs

### A. The syscall → verb mapping table

The host holds: an fd table (0–2 streams, 3 = preopen `/`, 4+ opens), one `Authority` for the whole run, and a staged buffer per open file. Every row below was executed unless marked.

| preview1 call (0.2 equivalent) | vfs answer | Errno vocabulary | Notes |
|---|---|---|---|
| `fd_prestat_get(3)` / `fd_prestat_dir_name` (`preopens.get-directories`) | constant: one preopen named `/` | 4+: `BADF` ends the scan | the only preopen; wasi-libc then sends relative paths |
| `fd_fdstat_get` | synthesized: stdio = `character_device` with read xor write rights (isatty-like); file = `regular_file`, all rights; dir = `directory` | `BADF` | rights are advisory: the ladder is enforced by the verb, not here |
| `path_open` plain (`open-at` without create/truncate) | **one `read`** with `columns={content,data,kind,size_bytes,mime_type,version,updated_at}` → staged buffer | `vfs.not_found`→`NOENT`; `wrong_kind` + write rights→`ISDIR`; `wrong_kind` read-only→ becomes a directory open (one `ls`); `permission_denied`/`unauthenticated`→`ACCES`; `read_only`→`ROFS` | the `read` is gated at the `read` rung; a row the caller may only `list` answers `ACCES` |
| `path_open` with `O_DIRECTORY` | **one `ls`** → materialized entry list (`list` rung) | `NOENT`, `NOTDIR` | names + kinds only, which is exactly the `list` rung's promise |
| `path_open` with `O_CREAT|O_TRUNC` | **no verb**; empty dirty buffer | — | the `write` happens at close; `add` rung for a fresh name, `contribute` for an occupied one, judged then |
| `path_open` with `O_CREAT` only | one `read` (stage if present) | as plain | append/patch semantics |
| `path_open` with `O_EXCL` | one `stat` then create-on-close | present→`EXIST` | the only open that needs an existence probe |
| `path_open` with `O_TRUNC` on an existing row | one `read` (to learn kind), buffer emptied, dirty | | could be optimized to zero verbs if kind were known |
| `fd_read` / `fd_pread` / `fd_seek` / `fd_tell` (`read(length, offset)`) | buffer only | EOF = success with `nread = 0`; `SPIPE` on stdio seek; `ISDIR` on a dir fd | zero database traffic between open and close |
| `fd_write` / `fd_pwrite` (`write(buffer, offset)`) | buffer only; `FDFLAGS_APPEND` moves the cursor to the end first; writes past the end zero-fill | `BADF` on a read-only open | |
| `fd_filestat_set_size` (`set-size`) | buffer resize, dirty | | |
| `fd_filestat_get` on a file (`stat`) | from the staged buffer: `regular_file`, size = `len(buf)` (unflushed writes included), times from the row | | CPython and Rust both call it right after open to size their reads |
| `path_filestat_get` (`stat-at`) | **one `stat`** (`list` rung) → filetype from `kind`, size from `size_bytes`, atim=mtim=ctim from `updated_at`, `nlink=1`, `ino` = a stable per-path number, `dev=0` | `NOENT` | **no mode bits exist in the struct** — the guest's libc invents `S_IFREG|0` |
| `fd_close` (`drop descriptor`) | dirty buffer → **one `write`** (`content=` if the body is the host's declared text, else `data=`); clean → nothing | `permission_denied`→`ACCES`, `read_only`→`ROFS`, `conflict`→`IO` (retry is the shell's job) | this is where the version is minted and where the rung is judged for a create |
| `_start` returns / `proc_exit` | flush every dirty open, then the exit code | | a program that exits without closing still lands its writes |
| `fd_readdir` (`read-directory` → `directory-entry-stream`) | the materialized `ls` from the open, encoded as `.`, `..`, then entries; cookie = index; truncation sets `bufused = buf_len` | `NOTDIR` | 2,000 entries = 17 round trips, one verb |
| `path_create_directory` (`create-directory-at`) | `mkdir(path)` | `exists`→`EXIST`, `not_found`→`NOENT` (parent) | `add` rung |
| `path_unlink_file` (`unlink-file-at`) | `stat` to refuse a directory, then **`delete`** → the row moves to `/.vfs/trash` | dir→`ISDIR`; `NOENT` | `read_write` rung; restorable, unlike POSIX |
| `path_remove_directory` (`remove-directory-at`) | `stat`, then `delete(cascade=False)` | `not_empty`→`NOTEMPTY`; file→`NOTDIR` | |
| `path_rename` (`rename-at`) | **`move(src, dest)`** | `cross_mount`→`XDEV`; `exists`/`wrong_kind` as POSIX | across mounts the guest's libc gets EXDEV and falls back to copy+unlink itself, which is a `copy` + `delete` for us — correct, and it leaves a trash row |
| `path_symlink` / `path_link` / `path_readlink` (`symlink-at`, `link-at`, `readlink-at`) | not supported | `NOTSUP` (58) — never `NOSYS`, so the program knows the *operation* is unsupported, not the call | vfs has no links; `path_readlink` answered `NOSYS` to CPython harmlessly, `NOTSUP` is the better word |
| `fd_filestat_set_times` / `path_filestat_set_times` (`set-times`) | success, store nothing | | `touch` works; mtime stays the write time |
| `fd_fdstat_set_flags` | append flag on the open | | |
| `fd_sync` / `fd_datasync` (`sync`) | success (the real sync is `fd_close`) | | a program that `fsync`s before close still sees its write only on close — see Forks Q2 |
| `fd_advise` / `fd_allocate` | success / `NOTSUP` | | |
| `fd_renumber` | table move, flushing the victim | | |
| `args_*`, `environ_*`, `clock_*`, `random_get`, `sched_yield` | host constants | | the env must carry nothing secret: CPython read it 445 times |
| `poll_oneoff` | `NOSYS` today; a clock-only implementation (sleep) is the honest minimum | | |
| `sock_*`, `proc_raise` | `NOSYS` | | no network, no signals |

The ladder maps onto errno exactly once, at the verb: `none` → `NOENT` on everything (the row is invisible); `list` → `stat`/`ls` succeed, `read` answers `ACCES`; `read` → opens succeed, close-with-dirty answers `ACCES`; `add` → creating a fresh name succeeds, overwriting answers `ACCES`; `contribute` → overwrite succeeds, `delete`/`move` answer `ACCES`; `read_write` → everything. A read-only mount answers `ROFS` to every write-shaped call. No call needs a new gate: the shim re-enters the public methods, so every existing gate fires (the no-shell rule holds by construction).

### B. The one filesystem ABI the shell exposes to every guest kind

Name it the **filesystem capability** and make it the vfs verb set, not POSIX. Every guest adapter is a thin layer over these seven calls, all carrying the run's `Authority`:

```
read(path)                         -> Row | ErrorKind     # content XOR data, mime_type, kind, size, version
write(path, body, text_or_bytes)   -> Row | ErrorKind     # mints a version; add/contribute judged here
ls(path)                           -> [ (name, kind) ]    # the list rung's exact promise
stat(path)                         -> Row-without-body
mkdir(path)                        -> Row
delete(path, cascade)              -> Row (tombstoned)    # to the trash, never destroyed
move(src, dest)                    -> Row | cross_mount
```

Where ours differs from the two precedents the brief names:

- **just-bash `IFileSystem`** has 25 methods because it reproduces POSIX for a bash interpreter: `chmod`, `utimes`, `symlink`, `link`, `readlink`, `lstat`, `realpath`, `createExclusive`. Ours has none of these as verbs; the adapters answer them (`chmod`/`utimes` → success-and-forget, link family → `NOTSUP`, `createExclusive` → `write(overwrite=False)` which vfs already has). just-bash's `readFileBytes` vs `readFile` split is the same text-vs-bytes decision we face; they push it to the caller, we carry it on the row (`source`, `mime_type`) and the adapter reads both columns.
- **Node 26 `node:vfs`** is fd-based and says it is "not a sandbox". Ours is path-based at the ABI and fd-based only inside the preview1 adapter; and ours *is* the sandbox: the authority is on the call, so there is no door for a guest to reach a row the caller cannot.
- Rows, authority, trash, versions, media: no precedent has any of the five. The adapters must not hide them — a `rm` that lands in the trash and a `write` that mints a version are features the shell's own `ls /.vfs/trash` and `stat` already expose.

Reject: exposing a POSIX fd interface as *the* ABI (Node's choice). It would force every guest kind that has no fds (Monty, QuickJS via `host_call`) to fake them, and it hides the row.

### C. The staging rule and its limits

Adopt, as the rule for v1: **open stages the whole row with one `read`; close writes the whole buffer with one `write`; nothing in between touches storage.** Measured cost: 5 statements per file read, 16 per file written, 6 per directory listed; a 2,000-entry listing is one verb; an 8 MiB row round-trips in tens of milliseconds on the dev engine (noted, not a test assertion).

Limits to state in the spec, each with its mitigation:

1. **Large rows.** A 1-byte read stages the whole row. Mitigation now: a per-run staging budget (bytes staged per open and in total) that answers `FBIG` (22) past the cap — just-bash's `EFBIG` precedent — sized against `Store.set_limits(memory_size)` so the guest cannot ask for more than its own memory anyway. Later: chunked reads (Forks Q2).
2. **Partial writes.** Append/patch/truncate are read-modify-write of the whole row and mint a version holding a full copy. Correct; costly for logs. Mitigation later: detect the pure-append pattern (cursor started at end, no seeks) and route to an append-shaped `edit`.
3. **Concurrent opens of one path.** Two opens in one guest, or two guests, each flush a whole buffer; last close wins. vfs's `conflict` (ESTALE) on a version precondition is the hook: flush with the staged `version` as the precondition and surface `conflict` as `IO` with a shell-level retry policy; today the shim does not pass a precondition `[NOT VERIFIED: whether write() accepts an expected version — not checked]`.
4. **`fsync` before close** is a no-op; a program that writes, syncs, then crashes (traps) loses the write unless the host flushes on trap too. Rule: flush dirty buffers on *every* exit path including traps and epoch kills, and say so.
5. **Text vs bytes on write-back** is decided by the host, never sniffed (Finding 7).

### D. Per-guest-kind binding notes

1. **WASI preview1 binary** (proven: Rust std, CPython 3.12, qjs). The shim in `experiments/s4/shim.py` is the design: bind every import the module declares (`Module.imports` gives the exact `FuncType`, so no hand-typed signatures), real for the memo's 24, `NOSYS`/`NOTSUP` stubs for the rest; one preopen `/`; worker thread + `run_coroutine_threadsafe`; `proc_exit` as an exception caught around `_start`; flush on every exit path. Epoch deadline and `set_limits` are per `Store` (E1's spike covers them).
2. **WASI 0.2 component.** Same table, resource-shaped: `open-at` → `read`/`ls`, `read(len, off)` → buffer, `read-directory` → one `ls` handed out an entry at a time, `not-permitted` for escapes, `cross-device` for mounts. Host side: wasmtime-py's component `Linker` (`add_func`, `add_resource`) in principle; not attempted. Until a component guest exists, do not build it — componentize-py has no vfs and wasi-virt only embeds static files, so a 0.2 component today is served `wasi:filesystem` by the host or not at all.
3. **CPython on WASI.** Runs under adapter 1. Decide where the stdlib lives: embedded (wasi-vfs, as WLR; zero vfs traffic, 26 MB module, cache the compiled artifact by binary revision) is the right default; serving it from vfs rows is possible but costs hundreds of `stat`/`read` verbs on first import. Hash seed and `random_get` are needed; `path_readlink` must answer `NOTSUP`.
4. **Pyodide / Emscripten.** Only if we host a JS runtime. The adapter is an Emscripten filesystem object: `node_ops.lookup/getattr/readdir` → `stat`/`ls`, `stream_ops.open` → `read` into the node's buffer, `close` → `write`, `mknod`/`unlink`/`rmdir`/`rename` → `mkdir`/`delete`/`move`, all **synchronous** and therefore needing a sync bridge (just-bash: `SharedArrayBuffer` + `Atomics`; Pyodide: MEMFS + batched `syncfs`). Reject MEMFS-plus-syncfs for us: writes invisible until an explicit sync break "a `write` mints a version at close".
5. **Monty** (v1.1.0 — the July memo studied 0.0.19; it now has a filesystem story). No syscalls: pass an `AbstractOS` subclass as `os=` whose `path_read_text/read_bytes` → `read`, `path_write_*`/`append_*` → `write` (append = read+write), `path_iterdir`/`path_scan` → `ls`, `path_stat` → `stat` (`StatResult.file_stat(size, mode=0o644, mtime)` — here a mode *is* asked for; answer a constant from kind), `path_mkdir/unlink/rmdir/rename` → `mkdir/delete/move`, `path_open` → a `MontyFileHandle` the host routes on. Under `AsyncMonty` the handler returns coroutines, so **no thread hop is needed**: this is the only guest kind whose file access can `await` the verbs directly. Do not use `MountDir` (it mounts host directories through cap_std, which is the thing vfs replaces).
6. **QuickJS.** Two routes, both proven or read: (a) the `qjs` WASI reactor/command build goes through wasi-libc to adapter 1 (`qjs:std`/`qjs:os` file calls executed above; the reactor build exists upstream, `quickjs-ng:CMakeLists.txt:397-420`); (b) quickjs-rs's single `env.host_call(name, this, argc, argv)` import dispatching host functions by name with handle-typed values, async host calls awaited by the guest, memory limit and interrupt (`quickjs-rs:quickjs_rs/_engine.py:246-262, 430, 1323`), and the whole-linear-memory snapshot (`:967-1003`, header-validated with a `build_id`). Route (b) is the function-table shape: expose the seven calls as `vfs.read(...)` etc.; route (a) gives a program-class guest (`jq`-like scripts) for free. Pick (a) for `/bin` programs and (b) for an interactive JS runtime, if we ever want one.

---

## Forks for the ADRs

**Q1. Python host (wasmtime-py) or a Rust host in `crates/vfs-core` for the preview1 shim?**
Options: (a) Python now, as the experiment stands; (b) Rust now, a `wasmtime` crate embedding behind the pyo3 seam; (c) Python now with a one-guest-per-process rule, Rust when concurrency is needed.
Evidence: the Python shim is ~250 lines and ran everything; its cost is not speed (CPython ran in 0.17 s) but **concurrency** — the trap global cross-contaminates concurrent guests (128/600) and the installed wheel's slab races on setup. A Rust host owns its traps and can run many stores on many threads; it also moves the GIL out of every `fd_write`. Lean: **(c)**. Ship Python with a process-wide guest lock (and worker processes if the web app needs parallel guests), and name the Rust host as the direction once there are two programs running at once — the memo's "performance work goes in our own Rust crate" rule applies the moment the shim is on a hot path.

**Q2. Whole-file staging or chunked streaming?**
Options: (a) whole-file, with a staging budget and `FBIG`; (b) chunked reads over a row's chunks (vfs stores chunks) with whole-file writes; (c) full byte-range reads and writes.
Evidence: whole-file is one verb per open and matched every program tested; the three limits (large rows, append cost, last-close-wins) are real but belong to a program class (databases, log appenders) that is not in the first catalog. Lean: **(a) at v1**, with the budget declared, and (b) as the named future direction for `read` of large bytes rows (the 1-byte-costs-8-MiB case) — never (c), which would re-create a block device over SQL.

**Q3. May a guest see `/.vfs` and `/.agents`?**
Options: (a) the same namespace the agent sees (today: the guest listed `/.vfs/trash`); (b) hide the reserved trees from the preopen (`NOENT`); (c) hide `/.vfs`, show `/.agents` read-only.
Evidence: nothing in the shim distinguishes them; a program given `/` sees what the authority sees. Lean: **(c)** — `/.vfs` is metadata the shell's own verbs render (`ls /.vfs/trash` is a shell builtin's job, not `cat`'s), while `/.agents/{tools,skills}` is user space a program may legitimately read (a `jq` over a `TOOL.md`). The rule is a path predicate in `resolve()`, zero cost.

**Q4. How is a guest's write-back attributed?**
Options: (a) the run's `Authority` unchanged (actor = the agent, provenance `constructed`); (b) a derived authority with `source_identity` naming the program (`/bin/jq.wasm@<version>`); (c) a new `Provenance` literal (`"program"`).
Evidence: `Authority` is `subjects, actor, provenance ∈ {"edge","constructed","system"}, narrowing, source_identity` (`src/vfs/authority.py:40, 116-130`), frozen and re-derived per call; the shim passes the same authority to every verb today. Lean: **(b)** — the subjects and actor are the agent's (the program holds no authority of its own, the no-shell rule), and `source_identity` already exists to say *how* the proof was carried; stamping the program path and revision there costs nothing and gives the trash and versions a provenance line without a schema change. (c) is worth it only if a verb should ever *behave* differently for a program than for the agent, and nothing in this study needs that.

**Q5 (new). Where does the text-vs-bytes decision for a guest's write live?**
Options: (a) sniff UTF-8 (the experiment); (b) the shell's redirect/program entry declares it; (c) the target's extension decides.
Lean: **(b)** with (c) as the default when nothing is declared; never (a). This is the content-channel ADR's call.

---

## Sources

- Clones (read-only, commits above): `~/Git/Repos/WASI` (`origin/wasi-0.1` via `git show` for preview1; `v0.2.9` via `git show` for 0.2; main for 0.3.2 and `path-resolution.md`), `browser_wasi_shim`, `wasi-virt`, `wasmtime-py`, `llm-wasm-sandbox` (incl. `bin/python.wasm`, `bin/quickjs.wasm` executed read-only), `amla-sandbox` (Python package only), `just-bash`, `bashkit`, `lifo`, `deepagentsjs`, `cpython`, `pyodide`, `RustPython`, `componentize-py`, `monty`, `quickjs-rs`, `quickjs-ng`.
- vfs live tree: `src/vfs/ops.py`, `src/vfs/base.py`, `src/vfs/authority.py`, `src/vfs/models/entry.py`, `src/vfs/paths.py`, `src/vfs/results/kinds.py`, `src/vfs/results/envelope.py`, `src/vfs/storage/backends/memory.py`, `src/vfs/storage/backends/database/engine.py`; `context/research/2026-07-24-hermetic-runtime-and-wasm-cli.md` §4–§6.
- Toolchain executed: `uv run --with wasmtime` (wasmtime wheel 49.0.0, Python 3.13.11), `cargo 1.97.1` with `wasm32-wasip1`, rust-src of toolchain 1.95.0.
- FETCHED 2026-10-15: https://github.com/nodejs/node/pull/61478 (Node VFS proposal; closed, "landed in core"); https://nodejs.org/api/vfs.html (`node:vfs`, added v26.4.0, Stability 1); https://raw.githubusercontent.com/emscripten-core/emscripten/main/src/lib/libmemfs.js (Emscripten MEMFS `node_ops`/`stream_ops`, synchronous).
- Experiment scripts and outputs: `experiments/s4/shim.py`, `scenarios.py` → `scenarios.json`, `interpreters.py` → `interpreters.json`, `trap_race.py`, `imports_survey.py` → `imports.json`, `run1.json`, `catfile/src/main.rs`, `fsops/src/main.rs`, `bin/catfile.wasm`, `bin/fsops.wasm` (the cargo `target/` dirs are git-ignored; `cargo build --release --target wasm32-wasip1` in each crate rebuilds them).
