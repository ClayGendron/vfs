# E1 — The wasm program spike, executed: a real CLI stored in vfs, run under wasmtime, served by vfs verbs

- **Date**: 2026-10-15
- **Researcher**: E1 (the executed spike)
- **Feeds**: the July memo `context/research/2026-07-24-hermetic-runtime-and-wasm-cli.md` §4 and §6, which proposed this spike and never ran it. Everything "verified" there was read-verified. Everything here ran.
- **Clones read**: `wasmtime-py` @ `280ce73b0e89c9522e75168553d4050a681d08c3` (2026-09-24, refreshed 2026-10-15; the installed wheel is wasmtime 49.0.0 from PyPI via `uv run --with wasmtime`). No other clone was needed; the shim is original work.
- **Toolchain**: cargo 1.97.1, target `wasm32-wasip1`, Python 3.13.11, wasmtime-py 49.0.0, vfs live tree at `ac5c515`.
- **Evidence labels**: **[EXECUTED]** ran in this session, output in `experiments/e1/outputs/`; **[READ]** read from a checkout or doc; **[INFERRED]** my reasoning; `[NOT VERIFIED: why]` where I could not.
- **Everything is under** `context/research/studies/2026-10-15-agent-shell/experiments/e1/`: `shim/vfs_wasi.py` (the preview1 shim, 627 lines), `shim/host.py` (engine, cache, resolve, run, spies, 203 lines), `step1_floor.py` … `step9_hostcall_bench.py`, `extra_checks.py`, `guest/` (five Rust wasi programs, 77 lines of Rust in all), `downloads/jaq/bin/jaq.wasm` (built from crates.io, untrusted data, only ever run under wasmtime), `outputs/*.txt` (every run's output).

## Summary

The mechanism works end to end, with real binaries, and it is small. A `wasm32-wasip1` program is an ordinary vfs entry (install is one `write` with `data=`); the host resolves it with one `ls` of a bin directory, reads its bytes back with `read(columns={"data"})`, compiles it once and caches the compiled module keyed on the entry's version, and runs it under wasmtime with a WASI preview1 shim whose filesystem is the vfs verbs. `upper in.txt out.txt` read its input with one `stat` + one `read`, wrote its output with one `stat` + one `write` (the output row got version 1, then version 2 on the second run), printed the line count on stdout and exited 0; a missing input exited 1 with the guest's own message; `jaq` (a jq clone, 3.7 MB, built from crates.io, the memo's exact scenario) ran `cat users.json | jaq '.users[].name'` from stdin and from a file argument; a spinning guest was killed by the epoch deadline at 0.66 s with `TrapCode.INTERRUPT`, distinguishable from a Rust abort (`UNREACHABLE`) and a raw out-of-bounds store (`MEMORY_OUT_OF_BOUNDS`); a greedy guest hit `Store.set_limits(memory_size=32 MiB)` and aborted; the compiled-module cache turned a 285–411 ms compile of jaq into a 1–17 ms deserialize; a three-stage pipe moved bytes between wasm stages with the vfs row rendered to bytes once at the pipe's entry and parsed back once at its exit. The shim implemented 35 of preview1's 46 functions for real and stubbed 11; the six binaries together import 23 distinct names and called 20 at runtime. Two things the memo did not foresee shaped the design: vfs verbs are async while wasmtime host callbacks are sync, so a guest run is a worker thread that posts each verb onto the event loop; and the `/.agents/bin` path was **not** refused by the live path rules, so the bin namespace is an open decision, not a forced one. The memo's thread-safety worry is real and now measured — 13.4 % of concurrent `proc_exit` outcomes were wrong across four threads — and it is defused for exit codes by recording the code in per-run state before raising (8000/8000 correct). The per-host-call floor in Python is 6.2 µs against 2.0 µs for wasmtime's own Rust preview1 (3×), and 14.7 µs for a decoding `fd_write`; that is cheap next to the 5–25 ms a vfs verb costs on in-memory SQLite, so the shim can stay in Python for now and the database, not the trampoline, is the latency to design around.

## Findings

### 1. The floor: wasmtime-py's own fd_write fixture under our shim **[EXECUTED]**

`step1_floor.py` registers `wasi_snapshot_preview1.fd_write` with `Linker.define_func(..., access_caller=True)`, decodes the iovec array from `caller.get("memory")`, and instantiates the WAT module from `wasmtime-py:tests/test_wasi.py:56-116` (the module's `start` function writes to fd 1 and fd 2). No `WasiConfig`, no `define_wasi`. Output (`outputs/step1.txt`):

```
stdout: Hello, stdout!
stderr: Hello, stderr!
STEP 1 OK: guest fd_write landed in the host's own buffers (no WasiConfig used)
```

The ABI shape the memo described is right: iovec = `(u32 ptr, u32 len)` pairs, little-endian, the count written to an out-pointer, errno returned as an i32.

### 2. Real binaries: five of our own and one from the world **[EXECUTED]**

`cargo new --bin` × 5 in `guest/`, `cargo build --release --target wasm32-wasip1`, 2.2 s for all five (`opt-level = "s"`, LTO):

| binary | size | what it does | preview1 imports |
|---|---|---|---|
| `upper.wasm` | 82,980 B | reads argv[1], uppercases, writes argv[2], prints line count, exit 0 | 13 |
| `spin.wasm` | 37,367 B | loops forever (`black_box` keeps the loop) | 4 |
| `echo-stdin.wasm` | 66,338 B | copies stdin to stdout, byte count on stderr | 5 |
| `alloc.wasm` | 49,221 B | grows a Vec 1 MiB at a time until the host refuses | 4 |
| `fsops.wasm` | 103,783 B | `ls`, `mv`, `rm`, `rmdir`, `mkdir`, `stat`, `append`, `seek` | 20 |
| `jaq.wasm` | 3,726,466 B | jq clone, crates.io `jaq` 1.6.0, MIT | 19 |

**The real-world binary.** No official jq release ships a wasi build (web search 2026-10-15, below). `rockwotj/jq-wasi` on GitHub publishes only `libjq-wasi.tar.gz` (a library archive, not a CLI) and carries no licence (`spdx_id: NOASSERTION`), so under the study rules I did not download it. `jaq` from crates.io, the Rust jq clone, is MIT. `cargo install jaq --target wasm32-wasip1` failed three ways before it worked, and each failure is a finding about the "install any CLI" story:

- 3.1.1 default features: `libmimalloc-sys` runs a C build script; there is no C toolchain for wasi on this machine (`outputs/jaq-install.log`).
- 3.1.1 `--no-default-features`: `fd-lock 4.0.4` (pulled by the REPL's line editor) has no wasi port — `cannot find 'unix' in 'os'` (`outputs/jaq-install-nodefault.log`).
- 1.6.0 `--no-default-features`: builds. `outputs/jaq-install-1.6.0.log`, binary at `downloads/jaq/bin/jaq.wasm`.

So "anything with a wasm32-wasi build" (memo §4.4) means "anything whose dependency closure stays inside wasi-libc and Rust std's wasi port"; a REPL, a file lock, a custom allocator, or a C build script breaks it. The wasi target is a real portability filter, not a checkbox.

Imports (`outputs/imports.txt`, `outputs/imports-jaq.txt`): the union over the six binaries is 23 distinct preview1 names. Every binary exports `memory`, `_start`, `__main_void`.

### 3. Store and resolve: install is a write, and `/.agents/bin` was not refused **[EXECUTED]**

`step3_4_store_run.py`, output in `outputs/step3_4.txt`.

**3a. The namespace question.** The task said: if `/.agents/bin` is refused by the path rules, fall back to `/bin` and report the refusal verbatim. It was **not** refused:

```
[write /.agents/bin/upper.wasm parents=True] success=True rows=1
  row path=/.agents/bin/upper.wasm kind=file version=1 populated=['kind', 'path', 'size_bytes', 'status', 'version'] size=82980
[mkdir /.agents/bin parents=True] success=False rows=0
  error kind=vfs.exists severity=error path=/.agents/bin message='Already exists'
[ls /.agents] success=True rows=2
  row path=/.agents/bin kind=directory version=1 ...
  row path=/.agents/tools kind=directory version=1 ...
```

**[READ]** `src/vfs/paths.py:51-52` declares `AGENT_FAMILIES = frozenset({"tools", "skills"})`, and `is_reserved_directory` (`paths.py:684-697`) only classifies `/.agents`, the two family roots and their unit directories as structurally-directory. Nothing refuses a third family name. A write of `/.agents/bin/upper.wasm` with `parents=True` mints `/.agents/bin` as an ordinary directory. The `vfs.exists` above is the second call's expected answer, not a refusal. So the bin namespace ADR gets a free choice: `/bin` (Plan 9 style, what the rest of this spike used), `/.agents/bin` (a third agent family, which would need adding to `AGENT_FAMILIES` to get the family's reservation rules), or `/.agents/tools/<name>/<name>.wasm` (a tool unit — this also wrote successfully). Nothing in the live tree forces any of them.

**3b. Install = write.** Six `write(path="/bin/<name>.wasm", data=bytes, parents=True)` calls, each `status=created version=1`. The write echo carries `kind, path, size_bytes, status, version` only (no mime, no source); the `ls` row afterwards shows `mime=application/octet-stream source=bytes` — vfs classified the body as bytes from the write, not from the extension (`.wasm` is not in its mime table; `[NOT VERIFIED: whether a mime for .wasm is intended]`).

**3c. Resolve.** `ls /bin` (6 rows, `path, kind, version, size_bytes, mime_type, source, content_hash, timestamps`) and `glob /bin/upper.*` (1 row) both work as the lookup; the host's `resolve()` does one `ls` of the bin directory and matches `<bin_dir>/<name>.wasm`. One directory, one verb. A multi-directory `PATH` is one `ls` per directory until a hit — the memo's "resolution walks a vfs PATH".

**3d. Reading the bytes back — the projection rule, verbatim.** This is the thing a caller has to know:

```
[read /bin/upper.wasm (no projection)] success=True rows=1
  error kind=vfs.unavailable severity=warning path=/bin/upper.wasm message='Unavailable: the binary awaits a rendering; run reindex'
  row ... populated=[... 'content' ...] data=NoneB content=None
[read /bin/upper.wasm columns={data}] success=True rows=1
  row ... populated=['data', 'kind', 'path', 'version'] data=82980B content=None
```

An unprojected `read` of a bytes body returns `content=None` with a `vfs.unavailable` **warning** (severity warning, `success=True`) — the text rendering is what `read` serves by default, and a `.wasm` has none. The bytes come only with `columns=frozenset({"data"})`. **[READ]** `src/vfs/storage/backends/database/reads.py:100-145`: `BODY_FIELDS = {"content", "data"}`, `effective_columns(None)` adds `content` and never `data`; a concrete projection fetches `columns & BODY_FIELDS`. The identity fields `path, kind, version` ride on every projection, so `read(columns={"data"})` is enough for the host to get bytes **and** the version it keys the cache on.

The same rule bites the shim on every guest `path_open`: a row written with `content=` has `data=None` and a row written with `data=` has `content=None` (both shown above for `/data/in.txt` and `/data/blob.bin` under `columns={data,content}`). The shim projects both and takes `data` if present, else `content.encode("utf-8")`. The guest sees bytes either way.

### 4. Run: argv, stdin, stdout, exit codes, file reads and writes over vfs **[EXECUTED]**

The runner (`shim/host.py`) does per run: resolve (1 `ls`), load (cache hit, or 1 `read` + compile + serialize), build a `VfsWasi` shim instance (argv, env, a stdin bytes buffer, stdout/stderr bytearrays, an fd table with fd 3 = the one preopen `/`), a fresh `Linker` with all 46 preview1 names defined, `define_unknown_imports_as_traps`, a `Store` with an epoch deadline and optional memory limit, then `instantiate` and call `_start` **on a worker thread** (`loop.run_in_executor`). Every vfs verb the shim needs is posted to the event loop with `asyncio.run_coroutine_threadsafe(...).result()`.

**4a. `upper /data/in.txt /data/out.txt`** (`/data/in.txt` = `"alpha\nbeta\ngamma\n"`):

```
=== upper /data/in.txt /data/out.txt (first run: compile)
  exit=0 trap=None timed_out=False
  stdout=b'3\n'
  module=compiled (52.5 ms)  run=246.2 ms
  shim verbs per guest path: {"/data/in.txt": ["stat", "read"], "/data/out.txt": ["stat", "write"]}
  all vfs verb calls this run (incl. resolve+load): {'ls': 1, 'read': 2, 'stat': 2, 'write': 1}
  SQL statements this run: 42
  preview1 calls: {'args_get': 1, 'args_sizes_get': 1, 'fd_close': 2, 'fd_fdstat_get': 2, 'fd_filestat_get': 1,
                   'fd_prestat_dir_name': 1, 'fd_prestat_get': 2, 'fd_read': 2, 'fd_write': 2, 'path_open': 2}
[stat /data/out.txt] ... version=1 size=17 source=text
[read /data/out.txt] ... content='ALPHA\nBETA\nGAMMA\n'
=== upper again (second run: cache hit; out.txt gets a new version)
  exit=0  stdout=b'3\n'  module=deserialized (0.6 ms)  run=121.1 ms
  all vfs verb calls this run: {'ls': 1, 'read': 1, 'stat': 2, 'write': 1}   SQL statements: 35
[stat /data/out.txt] ... version=2
```

The output file landed in vfs with a body of `ALPHA\nBETA\nGAMMA\n`, version 1 then version 2. Exit 0 arrived as `_start` returning normally — the Rust runtime does not call `proc_exit` on a clean `main` return (no `proc_exit` in the call counts). `fd_prestat_get` was called twice: once for fd 3 (our preopen) and once for fd 4, which returned `BADF` and ended wasi-libc's scan — the memo's handshake rule 1, confirmed.

**Verb calls per guest file: 2.** The memo promised "one read and at most one write per file" (§4.3). The natural shim does **one `stat` + one `read`** for an input and **one `stat` + one `write`** for an output, because `path_open` must know (a) does the path exist, (b) is it a directory, (c) do `O_CREAT`/`O_EXCL`/`O_TRUNC` apply — before it knows whether to read at all. **[INFERRED]** This folds to one verb per file: call `read(columns={data,content})` first and classify from the result's error kind (`vfs.not_found` → `NOENT` or create; `vfs.wrong_kind` → it is a directory). vfs's classified errors carry exactly the facts a `stat` would. I left the two-verb shape in because it is the honest reading of the POSIX call sequence; the fold is an optimization the spec can take.

**SQL statements: 35 for a warm run, 42 cold** (the 7 extra is the binary `read` for the compile). `extra_checks.py` groups the 35: `5 × BEGIN`, `5 × SELECT max(vfs_principal_revisions.revision)`, `5 × SELECT vfs_relabels…`, `5 × SELECT vfs_grants…` — that is 20 of 35 statements, four per verb, the transaction open plus the authority preamble (principal revision, relabels, grants) that every verb runs; the remaining 15 are the verbs' own reads and the write's `SAVEPOINT / DELETE vfs_content / DELETE vfs_blobs / INSERT vfs_content / UPDATE / RELEASE`. Per verb: `ls` 6, `stat` 5, `read` 5, `write` 14. **[INFERRED]** A program that touches *k* files costs about 5 + 4k vfs verbs and ~10k SQL statements; a program that touches none (jaq on stdin) costs one `ls` and 6 statements — the pipe of §8 is the cheap path.

**Latency** (bench facts on in-memory aiosqlite, never a test): a run that does only `ls` + `stat` (missing input) is 24 ms; `ls` + `stat` + `read` + `stat` + `write` is 65–121 ms; the no-file jaq run is ~0.4 ms of guest time. Each verb is two thread hops (worker → loop → aiosqlite's thread and back). The database is the latency, not wasm and not Python.

**4b. Exit codes and the guest's own error paths.**

```
=== upper /data/missing.txt (guest's own error path)
  exit=1  stderr=b'upper: /data/missing.txt: No such file or directory (os error 44)\n'
  shim verbs per guest path: {"/data/missing.txt": ["stat"]}
=== upper with no args (usage -> exit 2)
  exit=2  stderr=b'usage: upper IN OUT\n'   (no vfs verbs beyond resolve)
=== upper on a bytes body (invalid UTF-8 -> guest error)
  exit=1  stderr=b'upper: /data/blob.bin: stream did not contain valid UTF-8\n'
=== jaq '.[' (syntax error -> jaq's own exit code)
  exit=3  stderr=b'Error: expected closing bracket\n  ...unclosed delimiter [ ...'
```

The vfs `ErrorKind` → errno table is a straight mapping (`src/vfs/results/kinds.py:35-57` names the errno in each member's comment: `not_found` ENOENT 44, `exists` EEXIST 20, `wrong_kind` ENOTDIR/EISDIR, `not_empty` ENOTEMPTY 55, `permission_denied` EACCES, `read_only` EROFS, `unsupported` ENOTSUP, `invalid` EINVAL, `cross_mount` EXDEV). The guest's libc turned 44 into "No such file or directory" by itself. **Errors are facts (ADR 076) survive the wasm boundary as errno facts.**

**4c. Directory and mutation calls (`fsops`)** — every one went through a vfs verb and came back with the right answer:

| guest call | shim verbs | result |
|---|---|---|
| `ls /data` | `stat`, `ls` | `f blob.bin / f in.txt / f out.bin / f out.txt / f users.json` |
| `stat /data/in.txt` | `stat` | `f 17 bytes` |
| `mkdir /data/sub` | `mkdir` | exit 0 |
| `mv /data/out.txt /data/sub/moved.txt` | `move` | exit 0 |
| `append /data/sub/moved.txt delta` | `stat`, `read`, `write` | exit 0 (row version advanced) |
| `seek` (SeekFrom::End(-4), read) | `stat`, `read` | `lta\n` |
| `rm /data/sub/moved.txt` | `stat`, `delete` | exit 0 → row in `/.vfs/trash` |
| `rmdir /data/sub` | `delete(cascade=False)` | exit 0 |
| `rmdir /data` (not empty) | `delete(cascade=False)` | exit 1 `Directory not empty (os error 55)` |
| `ls /nope` | `stat` | exit 1 `No such file or directory (os error 44)` |
| `stat ../../etc/passwd` | **none** | exit 1 `Capabilities insufficient (os error 76)` |

Two details. The guest's `rm` lands in vfs's trash (`ls /.vfs/trash` shows `/data/sub/moved.txt` v5 and `/data/sub` v4) — a wasm program's delete is as recoverable as an agent's. And the `..` escape never reached vfs: the shim's resolver answered `NOTCAPABLE` (76) on its own, with zero verb calls — the memo's "one function" sandbox check (rule 5), and even a miss would land inside the namespace.

**4d. jaq, the memo's scenario.** `cat /data/users.json | jaq '.users[].name'` → `"ada"\n"grace"\n`, exit 0, **zero file verbs** (stdin only); `jaq -c '[.users[].name]' /data/users.json` → `["ada","grace"]`, with `/data/users.json: [stat, read, stat, read]` — jaq opens its file argument twice (its own doing; the shim stages the whole body twice). **[INFERRED]** A per-run staging cache keyed on path would halve that; whether that is correct depends on whether a guest may observe its own writes through a second open — it may, so the cache must be write-through to the staged buffer, not to vfs.

**Text vs bytes write-back.** The guest only ever hands the shim bytes. I ran both policies: `text_writeback=True` (decode as UTF-8 → `write(content=)`, fall back to `data=` if it does not decode) produced `/data/out.txt` with `source=text` and a readable `content`; `text_writeback=False` (`write(data=)`) produced `/data/out.bin` with `source=bytes mime=application/octet-stream` and `read /data/out.bin` returning the `vfs.unavailable: the binary awaits a rendering; run reindex` warning with `content=None`. The second is almost certainly wrong for a text tool's output: it hides the text from `grep` and `glean` until a reindex. This is a program-ABI decision (fork F3).

### 5. Timeout and memory limits **[EXECUTED]**

`step5_limits.py`, `outputs/step5.txt`. `Config.epoch_interruption = True`; a daemon thread calls `Engine.increment_epoch()` every 20 ms; each `Store.set_epoch_deadline(ceil(timeout / tick))`.

```
### timeout: spin with timeout_s=0.5
  wall=0.66s exit=None trap_code=TrapCode.INTERRUPT timed_out=True
### memory limit: alloc with memory_bytes=32 MiB
  exit=None trap_code=TrapCode.UNREACHABLE timed_out=False
  stderr=b'memory allocation of 16777216 bytes failed\nnote: run with `RUST_BACKTRACE=1` ...'
### raw guest bug: a WAT module storing out of bounds
  trap_code=TrapCode.MEMORY_OUT_OF_BOUNDS
### a second store on the same engine, run after the kill, still works
  second spin: trap_code=TrapCode.INTERRUPT timed_out=True
```

Three facts. (1) The kill is distinguishable: `Trap.trap_code` is `INTERRUPT` for our deadline, `UNREACHABLE` for a guest abort, `MEMORY_OUT_OF_BOUNDS` for a raw bug; `Trap.message` is the same `error while executing at wasm backtrace:` for all three, so the **code, not the message**, is the classifier. (2) A memory limit does not produce a memory trap: `memory.grow` returns −1, Rust's allocator prints its message to stderr through our `fd_write`, then aborts with `unreachable`. So "out of memory" is reported by the guest on stderr and arrives as `UNREACHABLE`; a host that wants to say "out of memory" must note that `set_limits` was hit (wasmtime-py exposes no counter; `[NOT VERIFIED: whether a ResourceLimiter callback is reachable from Python]`). (3) **Without `set_limits`, `alloc` reached 1024 MiB of host memory before wasm32's own 4 GiB ceiling stopped it** (`outputs/extra.txt`: `last progress line=['alloc: 1024 MiB']`); the host limit is the only thing that bounds host RAM, and it must be set on every store.

The epoch is engine-global: one ticker thread serves every store, and each store's deadline is its own count. Stores created after a kill run normally. **[INFERRED]** The epoch only fires at wasm loop headers and function entries; a guest blocked inside a host callback — that is, inside a vfs verb — is not interrupted until the verb returns. The verb's own timeout is the cap there; the shell's deadline must be the sum of the guest deadline and the verb deadline, or the verb must take the remaining budget.

### 6. The compiled-module cache **[EXECUTED]**

`step6_cache.py`, `outputs/step6.txt`. Key = `sha256(wasmtime version | config fingerprint | entry path | entry version)`, value = `Module.serialize()` on the host disk.

```
  jaq    v1 cold : compiled        411.2 ms  wasm=3726466 B  cwasm=8913912 B
  jaq    v1 warm : deserialized      1.7 ms
  upper  v1 cold : compiled         13.6 ms  wasm=82980 B    cwasm=274376 B
  upper  v1 warm : deserialized      0.2 ms
### deserialize(bytes) vs deserialize_file (mmap) vs compile, jaq, 5 reps each
  compile              min=   284.7 ms  max=   352.0 ms
  deserialize(bytes)   min=    16.6 ms
  deserialize_file     min=    15.4 ms
### cache poisoning check: a cwasm from a different engine config is refused
  refused: 'Module was compiled with epoch interruption but it is not enabled for the host'
```

Compile is 20–200× the cost of deserialize; the compiled artifact is 2.4–3.3× the wasm's size. wasmtime checks the engine configuration itself on deserialize (the refusal above), so the config term in our key is belt-and-braces, not load-bearing; the wasmtime-version term is load-bearing (`[READ]` `wasmtime-py:wasmtime/_module.py:53-56`).

**What the memo got wrong about the key.** It said "the per-entry revision supplies the last term". A same-bytes rewrite advanced the version anyway:

```
### rewrite /bin/upper.wasm (same bytes, overwrite=True) -> does the version advance?
  write: status=updated version=2
  load after same-bytes rewrite: version=2 compiled 15.9 ms key=acea2980f7e8
```

Keying on version recompiles on every reinstall, including a no-op one. The row carries `content_hash` on every `ls`/`stat`; key on that instead and the same bytes under two versions — or two paths, or two mounts — share one compiled module. **[EXECUTED]** `content_hash` is the SHA-256 of the body: for `/bin/upper.wasm` it equals `sha256(bytes)` (`4fd2b1aa0b2f5ee0…`), and for a text row it equals `sha256` of the UTF-8 text (`8f434346648f6b96…` for `"hi"`), so one key rule serves both body kinds.

### 7. Concurrency: the `LAST_EXCEPTION` global, measured and defused **[EXECUTED]**

**[READ]** `wasmtime-py:wasmtime/_func.py:14` still declares `LAST_EXCEPTION: Optional[Exception] = None` at module level; the trampoline stores the callback's exception there at `:213-216` and `maybe_raise_last_exn` at `:245-249` reads and clears it. Not thread-local. The memo's worry stands in the refreshed checkout. Also **[READ]** `wasmtime/_ffi.py:38` loads the library with `cdll`, so the GIL is released while wasm executes — two guests on two threads really do run at once, which is what makes the race reachable.

**Part A** (`step7_threads.py`, `outputs/step7.txt`): four threads, each running a one-instruction guest `proc_exit(10+i)` 2000 times:

```
    6931/8000  own code
     805/8000  other: WasmtimeError            (the global was already consumed; a bare trap arrived)
     264/8000  WRONG code  (e.g. "WRONG code 11 (wanted 13)")
```

13.4 % wrong. The two failure shapes are exactly what the global predicts: thread A raises thread B's `GuestExit` (wrong code), and B — finding the global empty — gets the bare `WasmtimeError: error while executing at wasm backtrace:` (`outputs/extra.txt`).

**Part B**: two real `upper` guests on two files, 20 concurrent rounds through the vfs loop: **0 mismatches**, both output rows at version 20 with the right bodies. The window is between a callback's raise and the embedder's re-raise; for a 100 ms run that touches the database the window is tiny; for a 10 µs run it is the whole run.

**Part 7b, the fix** (`step7b_recorded_exit.py`, `outputs/step7b.txt`): record the exit code in the per-run shim state *before* raising, and have the embedder read that state on **any** exception, ignoring which exception object arrived: **8000/8000 own code**. The identity of the exception is the only thing the race corrupts, and nothing needs it. What this does not cover: a genuine host exception (a shim bug) can still be attributed to the wrong run; and a `Trap` with a real `trap_code` (INTERRUPT, UNREACHABLE) is not routed through `LAST_EXCEPTION` at all, so timeouts and aborts are never cross-contaminated. **[INFERRED]** The upstream fix is a `threading.local()` in place of the global; until then the recorded-state pattern plus "never trust the exception's identity for the exit code" is sufficient for one process with many guests.

### 8. The pipe: bytes between wasm stages **[EXECUTED]**

`step8_pipe.py`, `outputs/step8.txt`:

```
entry: /data/users.json -> 61 bytes (body was text)
  jaq .users[].name            exit=0 stdout=b'"ada"\n"grace"\n"\xc3\xa9dith"\n'
  echo-stdin                   exit=0 stdout=(same 23 bytes)   stderr=b'echo-stdin: 23 bytes\n'
  jaq -R -r ascii_upcase       exit=0 stdout=b'"ADA"\n"GRACE"\n"\xc3\xa9DITH"\n'
exit: write /data/names.txt v1 status=created
verb calls for the whole pipeline: {'ls': 3, 'read': 2, 'write': 1}
### a bytes-only stage: echo-stdin on a 1 MiB binary payload
  exit=0 out==in: True (1048576 B) fd_read calls=17 fd_write calls=5 run=4.2 ms
```

How the boundary felt, for S3: inside the pipe there are no rows, only bytes, and the mechanism needs nothing else — stdout of stage *n* is a `bytes`, stdin of stage *n+1* is a buffer the shim serves through `fd_read` (64 KiB reads: 17 calls for 1 MiB). The rows exist only at the two ends. At the entry the shell rendered one row to bytes (`content.encode("utf-8")` for a text body, `data` for a bytes body — the same two-body rule as §3d); at the exit it parsed bytes back into one row (`write(content=)` because it decoded). UTF-8 survived end to end (`édith`). Three stages cost one `ls` each for resolution plus one `read` and one `write` — a wasm stage that reads only stdin is the cheapest thing in the shell. **[INFERRED]** If the pipe payload is rows (ADR 3), a wasm stage is a row→bytes→row adapter with a declared rendering at each end: the shell renders the incoming rows to text with the one renderer (`results/render.py`) and lifts the outgoing bytes into rows by a declared rule (lines → rows is the Unix default; JSON-lines → rows is the jq default). The adapter is where the placeholder rule for media applies: a wasm program never sees a `data` column, it sees the placeholder text.

### 9. The host-call floor: Python vs Rust, measured **[EXECUTED]**

`step9_hostcall_bench.py`, `outputs/step9.txt`. A WAT guest calls `fd_write` with a 1-byte iovec 200,000 times:

```
  python fd_write (decode iovec + copy)               2932.6 ms   14.66 us/call
  python no-op host call                              1239.9 ms    6.20 us/call
  wasmtime built-in Rust fd_write (to a host file)     404.6 ms    2.02 us/call
  Python trampoline floor ~6.20 us/call vs Rust host ~2.02 us/call -> 3x
```

The Python trampoline costs ~6 µs per host call before any work; a real `fd_write` is ~15 µs. wasmtime's own Rust preview1 writing to a host file is ~2 µs. For the programs here the host-call counts are tiny (10 calls for `upper`, 22 for a 1 MiB `echo-stdin`) — 0.3 ms of trampoline against 24–121 ms of vfs verbs. The ratio flips only for a guest that makes host calls in a tight loop (a line-at-a-time filter calling `fd_write` per line on a 10 MB input: ~1.5 s in Python, ~0.3 s in Rust).

### 10. The preview1 table: what the binaries need, what the shim did **[EXECUTED]**

The memo said 17 must be real, 7 more for directories and writes, the rest stubbed. The binaries said:

| preview1 function | memo | imported by (of 6 binaries) | called at runtime | shim |
|---|---|---|---|---|
| `args_get`, `args_sizes_get` | 17 | 3 | yes | real |
| `environ_get`, `environ_sizes_get` | 17 | 6 | `sizes` only (jaq) | real |
| `clock_time_get` | 17 | 1 (jaq) | no | real |
| `clock_res_get` | — | 0 | no | real (trivial) |
| `random_get` | 17 | 1 (jaq) | yes (jaq) | real |
| `fd_fdstat_get` | 17 | 3 | yes | real (tty flag drives filetype) |
| `fd_prestat_get`, `fd_prestat_dir_name` | 17 | 3 | yes | real (one preopen `/`, BADF ends the scan) |
| `fd_read`, `fd_write` | 17 | 6 / 6 | yes | real (buffers; EOF = 0 + SUCCESS) |
| `fd_seek` | 17 | 1 (fsops) | yes | real (signed i64 out) |
| `fd_close` | 17 | 3 | yes | real (flush → `write`) |
| `fd_filestat_get` | 17 | 3 | yes | real (from the buffer) |
| `path_open` | 17 | 3 | yes | real (`stat` + `read`, or empty under CREAT) |
| `path_filestat_get` | 17 | 2 | yes (fsops) | real (`stat`) |
| `proc_exit` | 17 | 6 | yes | real (raise; code recorded) |
| `fd_readdir` | +7 | 1 (fsops) | yes | real (`ls`; truncated last dirent) |
| `fd_tell` | +7 | **0** | no | real (trivial) |
| `path_create_directory` | +7 | 1 | yes | real (`mkdir`) |
| `path_remove_directory` | +7 | 1 | yes | real (`delete(cascade=False)`) |
| `path_unlink_file` | +7 | 2 | yes (fsops) | real (`stat` + `delete`) |
| `path_rename` | +7 | 2 | yes (fsops) | real (`move`) |
| `fd_filestat_set_size` | +7 | **0** | no | real (truncate the buffer) |
| `path_link` | — | **1 (jaq)** | no | stub NOTSUP |
| `fd_pread`, `fd_pwrite`, `fd_renumber`, `fd_sync`, `fd_datasync`, `fd_advise`, `fd_fdstat_set_flags`, `fd_fdstat_set_rights`, `fd_filestat_set_times`, `sched_yield` | — | 0 | no | real or accept-and-succeed (cheap on buffers) |
| `fd_allocate`, `path_filestat_set_times`, `path_readlink`, `path_symlink`, `poll_oneoff`, `proc_raise`, `sock_accept`, `sock_recv`, `sock_send`, `sock_shutdown` | rest | 0 | no | stub NOTSUP |

Totals: 46 names registered; **35 real, 11 stubs**; 23 distinct names imported across six binaries; **20 called at runtime**; **no stub was ever hit** (`STUBBED` appears in no output). Against the memo: all 17 "must be real" were imported by at least one binary and 15 of them were called (`clock_time_get` and `environ_get` were linked but not called); of the "+7", `fd_tell` and `fd_filestat_set_size` were imported by nothing (Rust's `fs::write` does not need them); `path_link` is a name the memo did not list and jaq links it. The memo's rules 1–5 (BADF ends the scan, EOF is success with 0, `fd_fdstat_get` on stdout, little-endian with signed seek, one sandbox function) all held; rule 3's claim that jaq colours on a tty did not reproduce with jaq 1.6 (`stdout_is_tty=True` and `False` gave identical plain output; `[NOT VERIFIED: jaq 1.6 may need -C; jq proper was not run]`).

### 11. What the memo got wrong or missed

1. **Sync callbacks, async verbs.** Not mentioned. vfs verbs are coroutines; wasmtime calls host functions synchronously on the thread that called `_start`. The guest therefore runs on a worker thread and every verb is `run_coroutine_threadsafe(...).result()` onto the loop. It works, it costs two thread hops per verb, and it means a guest run is `await loop.run_in_executor(None, guest)` from the shell. A Rust host would have the same shape (the pyo3 side would need to re-enter the loop) unless the storage call is made sync. **[EXECUTED + INFERRED]**
2. **One verb per file is two.** `path_open` needs existence and kind before it can read or create; the natural shim does `stat` + `read` / `stat` + `write`. Foldable to one (classify from the read's error kind). **[EXECUTED]**
3. **The bytes/text duality lands in the shim.** A row has `content` XOR `data`; the guest wants bytes in and gives bytes out. The shim decodes/encodes at both edges. Which body a guest's output becomes is an ABI decision, and `write(data=)` for text output hides it from `grep` until a reindex. **[EXECUTED]**
4. **The cache key should be the content hash, not the version.** A same-bytes rewrite is a new version. **[EXECUTED]**
5. **`/.agents/bin` is not refused.** The memo assumed `/bin`; the task assumed a refusal; neither is forced by the live tree. **[EXECUTED]**
6. **Out-of-memory is a guest abort, not a memory trap**, and without `set_limits` a guest takes a gigabyte before wasm32 stops it. **[EXECUTED]**
7. **The `LAST_EXCEPTION` race is 13 % under contention and is defused by recording the exit code before raising.** The memo's "serialize guest execution per process" is one option; it is not the only one. **[EXECUTED]**
8. **`Store` now takes `data=`** (`wasmtime-py:wasmtime/_store.py:15,39`) but `Caller` still does not expose it; per-run closures on a per-run `Linker` are fine and were used. The memo's "plan a host-side registry keyed per invocation" is unnecessary. **[READ]**
9. **Clean exit is not an exception when you own `proc_exit`.** `_start` returns normally on a clean Rust `main`; `ExitTrap` is a `define_wasi()` artefact. **[EXECUTED]**
10. **jq's "wasm32-wasi build" does not exist as a downloadable, licensed CLI** (2026-10-15); jaq 1.6 does, after two dependency-closure failures. The install story needs a curated registry more than the memo allowed. **[EXECUTED]**
11. **`fd_tell` and `fd_filestat_set_size` are not needed for "writes files"**; `path_link` is linked by real tools and must at least exist as a stub, else `define_unknown_imports_as_traps` makes instantiation itself trap. **[EXECUTED]**

### 12. The vfs refusals and surprises, verbatim

- `read /bin/upper.wasm` (no projection): `error kind=vfs.unavailable severity=warning path=/bin/upper.wasm message='Unavailable: the binary awaits a rendering; run reindex'` with `content=None` — a **warning on a success**, and no bytes. Bytes need `columns=frozenset({"data"})`.
- `write(path="/.agents/bin/upper.wasm", data=..., parents=True)`: **`success=True`**, no refusal. `mkdir("/.agents/bin", parents=True)` afterwards: `kind=vfs.exists message='Already exists'` (expected).
- `write(path="/.agents/tools/upper/upper.wasm", data=..., parents=True)`: `success=True` — a tool unit accepts a binary.
- `write(..., data=)` echo rows carry no `mime_type`/`source` (populated = `kind, path, size_bytes, status, version`); `ls` shows `mime=application/octet-stream source=bytes`.
- `delete("/data", cascade=False)` on a non-empty directory: `vfs.not_empty` → errno 55 → the guest's `Directory not empty`. `delete(cascade=True)` (the default) would have succeeded — the shim must pass `cascade=False` for `rmdir` semantics, or a guest's `rmdir` becomes `rm -rf`.
- A guest `rm` lands in `/.vfs/trash` like any delete; a guest cannot sweep.
- `StatementSpy` had to reach `storage._host._engine` (the `EngineHost`'s engine) to attach `before_cursor_execute`; there is no public statement counter.

## What this means for vfs

**Adopt the mechanism as proven.** A program is an entry; install is `write(data=)`; resolve is one `ls` of a bin directory; load is `read(columns={"data"})` plus a compiled-module cache; run is a worker thread with a per-run shim, a per-run `Linker`, a per-run `Store` with an epoch deadline and a memory limit, and vfs verbs posted to the loop. The whole thing is 830 lines of research Python; a production shim will be the same shape with the folds below.

**Names and shapes to carry into the spec:**

- `Program` row: `kind=file`, `source=bytes`, `mime=application/wasm` (declare it; today it is `application/octet-stream`), resolved from a bin directory by basename without the `.wasm` suffix.
- `RunResult` ⊂ `Result`: `exit_code: int | None`, `stdout: bytes`, `stderr: bytes`, `trap: Literal["interrupt","unreachable","memory","none"]`, `timed_out: bool`, plus the verb and statement counts as observability fields (counts, never clocks, are what a test pins).
- The errno table is the `ErrorKind` table; keep the two in one place so a new kind gets its errno when it is minted.
- `path_open` folds to one verb by reading first and classifying `not_found` / `wrong_kind`; `rmdir` must pass `cascade=False`; `unlink` of a directory is `ISDIR` before any verb.
- Output write-back: decode as UTF-8 → `content=`; else `data=`; the mime from the extension. Make the rule explicit in the ABI ADR rather than letting the shim decide (fork F3).
- Cache key: `(wasmtime version, config fingerprint, content_hash)`; the store can live on host disk or as rows under `/.vfs/` (fork F5).
- Exit code lives in per-run shim state, written before `proc_exit` raises; the embedder never reads it from the exception. Until wasmtime-py makes `LAST_EXCEPTION` thread-local, that plus "trap codes are never cross-contaminated" is the concurrency story for one process.
- Every store gets `set_limits(memory_size=…)` and an epoch deadline; the ticker thread is one per engine; the guest deadline does not cover time inside a verb, so the verb budget is part of the run budget.

**Python host or Rust host for the shim?** Python, for now, with the numbers to revisit: the trampoline is 6 µs/call and a decoding `fd_write` 15 µs/call against 2 µs for Rust (3–7×); the programs in this class make 10–30 host calls per run; a vfs verb is 5–25 ms on in-memory SQLite and more on a server. The shim's cost is below 1 % of a run that touches a file. The case for Rust arrives with (a) a line-at-a-time guest on megabyte inputs (host calls in the hundreds of thousands: ~1.5 s Python vs ~0.3 s Rust per 10 MB) or (b) the moment the shell wants to run many guests in one process without the GIL serializing the Python half of every host call. When it does, the Rust shim belongs in `crates/vfs-core` behind the one engine seam (ADR 057), and it should keep the staging model: the Rust side owns the buffers and the fd table and calls back into Python only for the verbs — which are the slow part anyway. `[NOT VERIFIED: a Rust shim under pyo3 still has to enter the asyncio loop for each verb; the thread-hop cost would remain]`.

**Reject:** keying the cache on version; `write(data=)` for text output; `cascade=True` on `rmdir`; relying on `Trap.message` to classify; trusting the exception object for the exit code; running any store without `set_limits`.

## Forks for the ADRs

**F1 (bin namespace ADR). Where do programs live?** Options: (a) `/bin` — Plan 9 style, what this spike used, no path-rule change; (b) `/.agents/bin` — a third `AGENT_FAMILIES` member, gets the family's reserved-directory classification and can share the permission posture of tools and skills; (c) `/.agents/tools/<name>/<name>.wasm` — a program is a tool unit with a manifest, discoverable by the existing `TOOL.md` indexing. All three wrote successfully today. **Lean: (b)** — a program is agent-facing capability like a tool or skill, it should be reserved like one, and the shell's `PATH` is then a list of family directories; (c) is attractive once a manifest (argv schema, rung needed, declared verbs) matters, and (b) does not preclude a `<name>/` unit inside it.

**F2 (bin namespace ADR). Resolution: basename, or basename with extension?** `upper` → `/bin/upper.wasm` by one `ls`. Options: strip a known suffix set (`.wasm` now, interpreter suffixes later); or require the exact filename. **Lean: strip**, with the suffix selecting the runtime (`.wasm` → wasmtime; later `.py` → Monty), which is the hermetic-runtime direction's natural dispatch.

**F3 (program ABI ADR). What does a program's written file become?** Options: (a) always `data=` (faithful bytes, invisible to `grep` until reindex); (b) decode UTF-8 → `content=`, else `data=` (what this spike did; text tools' output is text); (c) decide by the target's extension/mime. **Lean: (b) with (c) as the tie-break** — a `.png` that happens to decode must not become text.

**F4 (program ABI ADR). What does a program read?** `data` if present, else `content` encoded as UTF-8 — the spike's rule. The open question is media rows: does a program opening a `.png` row get its bytes (the row's `data`) or the renderer's placeholder text? **Lean: bytes through `path_open`, placeholder through stdin** — a file open is the program asking for the artefact; a pipe is the shell's row stream, and S3's placeholder rule governs the stream.

**F5 (program ABI ADR). Where does the compiled-module cache live, and who owns it?** Options: host disk keyed by content hash (this spike); rows under `/.vfs/` so a multi-host deployment shares it; no cache (285–411 ms per jaq run). **Lean: host disk now, keyed on `content_hash`**, with the `/.vfs/` option left open — wasmtime already refuses a mismatched engine, so a shared store is safe; whether a 9 MB cwasm per program version belongs in the database is a storage-cost question.

**F6 (policy ADR). What rung does `run` need, and what does the program's own authority look like?** The spike ran every verb with the caller's authority (`authority=None`, the default). The mechanism needs: the rung to execute (`run` on the program row — `read` suffices to fetch the bytes today, which means anyone who can read a program can run it unless `run` is gated separately); the authority the program's verbs carry (the caller's, as the brief says — this spike did exactly that, and the `..` escape and `rmdir /data` refusals show the two walls); and the budgets (deadline, memory, and a verb budget — the epoch does not cover time inside verbs). **Lean**: `run` requires `read` on the program **and** an explicit execute grant on its directory (a host that wants to deny programs denies the directory); verbs carry the caller's authority unchanged; the deadline, memory cap and verb-count cap are policy values on the run, not on the program.

**F7 (policy ADR). One guest at a time per process, or many?** Measured: the `LAST_EXCEPTION` race is real (13.4 %) and defused for exit codes by per-run state; trap codes are never affected; a genuine shim exception could still be misattributed. Options: a process-wide run lock (simple, serializes CPU); many guests with the recorded-state rule (what Part B did, 0 mismatches); worker processes. **Lean: many guests with the recorded-state rule**, and file an upstream issue for a thread-local — the fix is three lines.

**F8 (pipe payload ADR, for S3). The wasm stage as a row→bytes→row adapter.** The mechanism needs exactly: a renderer from the incoming rows to bytes (the one renderer, text only, placeholders for media) and a lifter from bytes to rows (lines by default; JSON-lines when the stage declares it). Nothing inside the pipe needs rows. **Lean**: declare the two edges on the program (a manifest field or a suffix convention) and never let a program see a `data` column through stdin.

**F9 (content channel ADR). Mime for `.wasm`.** `application/wasm` is the IANA type; today vfs stores `application/octet-stream`. **Lean**: add it, so the resolver can also check the mime and refuse a text file named `x.wasm`.

## Sources

- `wasmtime-py` @ `280ce73b0e89c9522e75168553d4050a681d08c3` (refreshed 2026-10-15): `wasmtime/_func.py:14,213-216,245-249` (`LAST_EXCEPTION`), `wasmtime/_ffi.py:38` (`cdll`), `wasmtime/_store.py:15,39,109,116` (`Store(data=)`, `set_epoch_deadline`, `set_limits`), `wasmtime/_module.py:49,76,140` (`deserialize`, `deserialize_file`, `serialize`), `wasmtime/_trap.py:9-31,158` (`TrapCode`, `trap_code`), `wasmtime/_memory.py:81-137` (`read`, `write`, `data_len`), `tests/test_wasi.py:56-116` (the fd_write fixture).
- vfs live tree @ `ac5c515`: `src/vfs/paths.py:51-52,684-697`; `src/vfs/storage/backends/database/reads.py:89-145`; `src/vfs/results/kinds.py:24-57`; `src/vfs/base.py:334-380,879-935,935-975,1030-1045,1112-1125,1204-1218,1548-1565`; `src/vfs/storage/backends/database/engine.py:120-181`; `src/vfs/storage/backends/database/backend.py:178-221`.
- `context/research/2026-07-24-hermetic-runtime-and-wasm-cli.md` §4.1–4.4, §5, §6.
- crates.io `jaq` 1.6.0 (MIT) — `cargo info jaq` 2026-10-15; `jaq` 3.1.1 features `default = [mimalloc]`.
- Web search 2026-10-15, "jq wasm32-wasi prebuilt binary": no official jq wasi release; [rockwotj/jq-wasi](https://github.com/rockwotj/jq-wasi) (releases: `libjq-wasi.tar.gz` only; licence `NOASSERTION` per the GitHub API, not downloaded); [paolosimone/jq-wasm](https://github.com/paolosimone/jq-wasm) (Emscripten, not WASI); Wasmer packages `lhauspie/jq`, `syrusakbary/jq` (registry-hosted, not a plain file).
- WASI preview1 witx constants (errno, filetype, oflags, fdflags, rights, struct layouts) as encoded in `shim/vfs_wasi.py`; cross-checked against the behaviour of wasi-libc in the six binaries (every call agreed; no stub hit; no EFAULT-class trap).
