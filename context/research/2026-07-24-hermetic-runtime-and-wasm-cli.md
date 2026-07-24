# The hermetic runtime: a vfs shell, sandboxed execution, and wasm CLIs as entries

- **Status**: research memo (commits us to nothing; feeds an ADR on the
  shell surface and a spike spec for the wasm CLI mechanism)
- **Date**: 2026-07-24
- **Owner**: Clay Gendron
- **Question**: Can the vfs CLI be built as a hermetic runtime — a
  unix-flavored shell embedded in a host application (the target MVP is a
  Python LangGraph agent in a web app), with real code execution, where
  *all* filesystem access resolves through vfs and the sandbox is a hard
  security boundary? Secondarily: can developers "install" preexisting
  CLIs into vfs, and what would a spike proving the mechanism look like?
- **Evidence gathered**: four parallel line-level surveys of read-only
  sibling checkouts under `~/Git/Repos/`, cloned for this memo: `monty`
  (pydantic-monty 0.0.19, HEAD `0a5fdb7`), `wasmtime-py` (47.0.1),
  `browser_wasi_shim` plus the `WASI` spec repo (preview1 material lives
  on branch `origin/wasi-0.1` — the `main` working tree is 0.2/0.3 only),
  and `nushell`. Standing reference set consulted: `plan9`,
  `filesystem_spec`, `pyfilesystem2`, `agentfs`, `opendal`. Citations are
  repo-relative to those checkouts; our own code is cited from `src/vfs/`.

---

## 1. The end state, and the word for it

The target is a **hermetic runtime**: a process whose entire world is a
filesystem view the host constructs — Plan 9's per-process namespace, one
level up. An agent embedded in a web app gets a shell tool. It types
`grep`, not `vfs grep`. It can write and execute real code. It cannot
name the host filesystem, because in its world no such thing exists.

The architecture maps onto an OS, and the mapping is the design:

| OS concept | This system | Runs where | Trusted? |
|---|---|---|---|
| Kernel + syscalls | `Shell` object + protocol verbs | Host application (Python) | Yes — our code |
| Disk | vfs entries | Rows in the database | Data, not code |
| User-space programs | Monty scripts, wasm binaries | Sandboxed VM in a worker | No — capability-only |
| Hardware | Postgres / Oracle / etc. | Wherever the DB lives | Reached only by the kernel |

The live tree already leans this way: the protocol verb surface *is* a
shell vocabulary (`ls`, `tree`, `glob`, `grep`, `read`, `write`, `edit`,
`mkdir`, `move`, `copy`, `delete`/`restore`/`sweep` —
`src/vfs/storage/protocol.py`), a `run(path, arguments)` verb already
executes things stored in vfs, and skills materialize as plain entries
under `/.agents/skills` (`src/vfs/skills.py`). Trash + restore + sweep
and the row-grant spine mean confinement comes with *reversibility* — a
stronger safety story than a chroot's.

The kernel/user-space split is the trust boundary, and it puts the
security burden in exactly two different places:

- **The shell needs no sandbox.** It is our parser dispatching to our
  verbs. `grep` is safe not because it is confined but because the symbol
  resolves to `storage.grep()` and nothing else exists. Path traversal is
  meaningless (vfs paths are not host paths); injection is meaningless
  (no underlying `/bin/sh` is string-spliced). Its residual threat model
  is resource exhaustion — catastrophic regex, unbounded globs — handled
  by budgets and timeouts, the posture the envelope machinery already
  takes.
- **Code execution needs interpreter-level isolation.** For a hard
  boundary, in a web app, the honest options are a from-scratch
  interpreter with no syscall surface (Monty) or a wasm VM with
  capability-based WASI (wasmtime). Ruled out: `exec()` with stripped
  builtins and RestrictedPython (decades of escapes), import/io shimming
  (ergonomics, not a boundary — any C extension walks past it), and
  container fleets (a real boundary, but heavy for many agent sessions
  and not what the MVP deployment shape wants).

Everything runs inside the host application's deployment (host process
plus local worker subprocesses). The only thing that leaves is SQL.

## 2. What nushell settles about the shell surface

nushell is the strongest existing answer to "pipes carry structured
values, not bytes," and its source documents its own scars. Findings that
transfer directly:

**The pipeline type, and two rejected designs.** `PipelineData` has only
four cases — `Empty`, `Value`, `ListStream`, `ByteStream`
(nushell:crates/nu-protocol/src/pipeline/pipeline_data.rs:49). The doc
comment at pipeline_data.rs:19-46 records two designs they tried and
rejected: *"everything is a stream"* (you can no longer distinguish a
string from a one-element list, and never know whether to flatten a
source) and *"streams inside Value"* (cloning a value that holds a stream
aliases it — "observation of a value at runtime could affect other
values"). The landed compromise: **values are cheap, immutable,
thread-safe; laziness lives only in the pipeline channel, never inside a
value.** Our `Result` envelope should obey the same law — an envelope may
*hold* a materialized value or reference a stream, but the value type
itself is never lazy.

**A table is `List<Record>`,** not a distinct value kind — `Table` exists
only in the type language (nushell:crates/nu-protocol/src/ty.rs:11). One
less variant to regret.

**Typed signatures checked at parse time.** Commands declare
`input_output_types` as (input, output) pairs, and the parser threads the
type through the pipeline, failing `ls | str trim` before anything runs
(nushell:crates/nu-parser/src/type_check.rs:679). With vfs result kinds
(`src/vfs/results/kinds.py`) the same static pipe-compatibility check is
available to us, and it is exactly what an agent wants: errors at parse
time are one cheap tool-turn; errors at row 40,000 are not.

**The structured→bytes wire format is a decision, not a default.**
nushell's worst documented wart: piping structured data into an external
command renders it through the *human table formatter* with ANSI off
(nushell:crates/nu-command/src/system/run_external.rs:502-518) — the
display format doubles as the wire format, users must remember
`| to json`, and it cannot be fixed post-ship. For us the
structured→wasm-stdin direction must have a canonical serialization
declared up front (JSON lines is the obvious candidate — it is what jq
eats), with rendering reserved for the terminal hop.

**The renderer is a command, not engine magic.** A finished pipeline is
printed by invoking the ordinary `table` command
(nushell:crates/nu-protocol/src/pipeline/pipeline_data.rs:727) — so
rendering is overridable, testable, and reusable. Maps cleanly onto
`src/vfs/results/render.py` staying the single render chokepoint.

**Two error channels.** Fatal errors return `Err` from the command;
per-row failures ride *in* the stream as first-class error values
(`Value::Error`), turning fatal only on collect/drain
(nushell:crates/nu-protocol/src/value/mod.rs:184,
list_stream.rs:80-102). This is the right shape for 10k-batch pipelines:
one bad row must not kill an ETL pass, and our observation/severity
machinery is the same idea. Their `pipefail` — whether a mid-pipeline
external failure aborts — is still experimental after years; decide that
semantic early, don't inherit it.

**Interruption is built into the stream primitive** — a signal check per
item (nushell:crates/nu-protocol/src/pipeline/list_stream.rs:160), not
bolted on. And **metadata needs a lifecycle rule**: their
`PipelineMetadata::for_collect()` exists because stream provenance is
meaningless after collection. Envelope metadata crossing a pipe needs the
same defined transform.

**External processes as data**: their `complete` command turns an
execution into one record `{stdout, stderr, exit_code}` — the clean
bridge shape for wasm CLI invocations too.

Also noted as anti-lessons: source spans embedded in every value payload
(regretted, being refactored out — provenance belongs in a sidecar), and
UTF-8 sniffing plus trailing-newline trimming at collect time (behavior
that cannot be locally reasoned about; we should declare types instead of
sniffing).

## 3. Monty, verified: the code-execution sandbox

pydantic's Monty is a minimal Python interpreter in Rust, built to run
LLM-generated code. The API reference is the stub
`monty:crates/monty-python/python/pydantic_monty/_monty.pyi`.

**Correction to the working assumption: execution is not in-process.**
The Python bindings expose *only* a worker-subprocess pool
(`Monty`/`AsyncMonty`), because "a monty process can never be made fully
crash-proof against memory errors"
(monty:crates/monty-python/README.md:5-9). Still lightweight and embedded
in the deployment, but the brief's phrase is "worker pool," not
"in-process."

**Host functions are a dict.** No registration ceremony:
`session.feed_run(code, external_lookup={'grep': grep, 'read': read})`,
resolved lazily by name (monty:crates/monty-python/example.py:20-26).
With `AsyncMonty` the entries may be coroutines, and guest
`asyncio.gather(read(a), read(b))` fans out to concurrently-awaited host
coroutines (monty:crates/monty-python/tests/test_async.py:61-75) — a
direct fit for the async verb surface in
`src/vfs/storage/protocol.py`. The guest-visible capability set *is* the
security surface: Monty controls which functions exist, not what they do
— host callbacks run with host privileges (monty:CLAUDE.md:73), so the
capability set must be curated vfs verbs bound to the session principal,
never raw internals.

**Pause/resume is first-class.** `feed_start` yields a snapshot at every
host call; a snapshot can be answered with `{'future': ...}` ("pending"),
letting other guest tasks run until a `FutureSnapshot` asks the host to
settle results by call id
(monty:crates/monty-python/tests/test_feed_start.py:159-172). Snapshots
and idle sessions serialize to bytes (`dump()`/`load_snapshot()`) — a
durable-execution shape for long agent scripts, with real caveats
(single-shot resume; mounts not stored in dumps; restored future
snapshots cannot be auto-driven).

**Limits**: `ResourceLimits` TypedDict — `max_duration_secs` (execution
time, *paused while suspended on the host*, accumulating across feeds),
`max_memory` (approximate, "a budget on user-visible data, not a hard
ceiling on process RSS"), `gc_interval`, `max_recursion_depth`
(monty:limitations/resource_limits.md:10-17,65-72). No instruction-count
budget exists. Host-side backstop: `Monty(request_timeout=...)` kills the
worker and raises `MontyCrashedError`.

**The subset is real.** Fixed nine-module stdlib (`asyncio` `datetime`
`json` `math` `os` `pathlib` `re` `sys` `typing`); no imports beyond it
(monty:limitations/modules.md:1-42). Classes without inheritance, no
method decorators (`@property`, `@classmethod` rejected at parse time),
no generators (`yield` rejected; genexps materialize to lists), no
`match`, no `del`, no walrus (monty:limitations/language.md:9-40).
`asyncio` exposes exactly `run` and `gather`
(monty:limitations/asyncio.md:1-58). Fine for agent glue loops; a
ceiling for real programs — which is what the wasm tier is for.

**Security posture, stated plainly.** The contributor doctrine is
explicit — "Monty will be used to run untrusted, potentially malicious
code" (monty:CLAUDE.md:60-78) — and the architecture is defense in depth
(interpreter subset, no I/O in the interpreter crate, subprocess
isolation, watchdog). But: the project labels itself experimental and
"not ready for prime time" (monty:README.md:19) at 0.0.19, has no public
security audit, and its WebSocket remote mode **provides no sandbox at
all** — the remote may run real CPython with full host access
(monty:limitations/pool-architecture.md:16-32). Only the subprocess pool
is a candidate boundary, and the brief should pair it with least-privilege
OS posture on the worker as the second layer.

## 4. Wasm CLIs as entries: install = write, verified end to end

The mechanism for "installing preexisting CLIs": a CLI compiled to
wasm32-wasi is inert bytes with no authority — it cannot open a file
unless the host implements WASI for it. So `/bin/jq.wasm` is an ordinary
vfs entry; **install is a `write`**, versioned, permissioned, trashable,
and restorable like everything else; and at execution the binary sees
only a WASI filesystem whose implementation is our code backed by vfs
verbs. Everything below is verified against the checkouts.

### 4.1 Embedding facts (wasmtime-py 47.0.1)

- **The built-in `WasiConfig` cannot be used for the filesystem**: its
  `preopen_dir(path, guest_path)` maps *host* directories only
  (wasmtime-py:wasmtime/_wasi.py:182). We implement the
  `wasi_snapshot_preview1` import module ourselves. There is no example
  of that in the repo — no `_start` invocation anywhere — so the shim is
  original work guided by browser_wasi_shim.
- **Registration**: `Linker.define_func(module, name, ty, func,
  access_caller=True)` — store-independent, so one linker serves many
  stores (wasmtime-py:wasmtime/_linker.py:64; example
  tests/test_linker.py:141-161). `define_unknown_imports_as_traps` is
  the safety net for unimplemented preview1 names
  (wasmtime-py:wasmtime/_linker.py:210).
- **Memory access**: the host callback's first arg is a `Caller`, itself
  a `Storelike` (wasmtime-py:wasmtime/_store.py:169);
  `caller.get("memory")` fetches the guest's exported memory, and
  `Memory.read`/`Memory.write`/`get_buffer_ptr` do the byte work
  (wasmtime-py:wasmtime/_memory.py:81,103,65). The `Caller` is
  invalidated when the callback returns (wasmtime-py:wasmtime/
  _func.py:171-178) — re-fetch memory on every call, cache nothing.
  `Memory.read` silently clamps out-of-range slices
  (_memory.py:93-101); WASI EFAULT semantics need explicit bounds
  checks.
- **Traps and exits**: a host callback signals by raising; the
  trampoline stashes the exception in a **module-level global**
  `LAST_EXCEPTION` and re-raises it at the embedder boundary
  (wasmtime-py:wasmtime/_func.py:212-216). Not thread-local — so guest
  execution must be serialized per process or pushed to worker
  processes. `proc_exit` is modeled by raising our own
  `GuestExit(code)` and catching it around `_start`; note a clean
  exit-0 also arrives as an exception (`ExitTrap`,
  wasmtime-py:tests/test_trap.py:75-99).
- **Compile-once caching**: `Module.serialize()` /
  `Module.deserialize_file()` (mmap, avoids two buffer copies)
  (wasmtime-py:wasmtime/_module.py:75,140), valid only for the same
  wasmtime version and engine config (_module.py:53-56) — cache key is
  `(wasmtime version, config fingerprint, binary revision)`, and the
  per-entry revision supplies the last term. `Linker.instantiate_pre`
  additionally skips import resolution per run
  (wasmtime-py:wasmtime/_instance_pre.py:11). Per-session state cannot
  ride on the store (`Caller` exposes no `data()`) — plan a host-side
  registry keyed per invocation.
- **Budgets**: epoch interruption for wall-clock timeouts
  (`Config.epoch_interruption`, `Store.set_epoch_deadline`,
  `Engine.increment_epoch` from a watchdog —
  wasmtime-py:tests/test_store.py:32-59), `Store.set_limits(
  memory_size=...)` in bytes (wasmtime-py:wasmtime/_store.py:116), fuel
  if determinism ever matters. `TrapCode` distinguishes a timeout kill
  from a guest bug (wasmtime-py:wasmtime/_trap.py:31-33).
- **Ready-made first test**: tests/test_wasi.py:56-116 contains a WAT
  module that imports `fd_write`, builds an iovec, and checks the
  result — the exact ABI shape the shim must decode, usable as a
  fixture before any real binary runs.

### 4.2 The preview1 shim is a checklist, not a swamp

Preview1 is 46 functions (WASI:preview1/witx, branch `origin/wasi-0.1`);
browser_wasi_shim defines all 46 with a two-layer dispatch — memory
decode in `wasi.ts`, per-fd behavior on an `Fd` base class that answers
`NOTSUP` unless overridden (browser_wasi_shim:src/wasi.ts:68-912,
src/fd.ts:4-117). The honest floor for a real CLI:

- **17 must be real**: `args_sizes_get` `args_get` `environ_sizes_get`
  `environ_get` `clock_time_get` `random_get` `fd_fdstat_get`
  `fd_prestat_get` `fd_prestat_dir_name` `fd_read` `fd_write` `fd_seek`
  `fd_close` `fd_filestat_get` `path_open` `path_filestat_get`
  `proc_exit`.
- **7 more if the CLI touches directories or writes files**:
  `fd_readdir` `fd_tell` `path_create_directory` `path_remove_directory`
  `path_unlink_file` `path_rename` `fd_filestat_set_size`.
- **The rest stub with a constant errno** (`NOTSUP` 58 / `NOSYS` 52) —
  always return an int, never raise, never return `None` (a JS
  `undefined` coerces to 0; a Python `None` traps).

The invariants that would otherwise cost debugging days:

1. **The preopen handshake**: before `main`, wasi-libc scans fds 3, 4, …
   with `fd_prestat_get` and stops **only on errno `BADF` (8)** — any
   other errno aborts the binary
   (browser_wasi_shim:src/wasi.ts:329-339; WASI:application-abi.md).
   After the scan, libc longest-prefix-matches guest paths against the
   preopen table and sends the shim **relative** paths against a dirfd.
   One preopen named `/` makes arbitrary absolute paths work.
2. **EOF is success with `nread = 0`**, never an errno
   (browser_wasi_shim:src/fs_mem.ts:90-97). `fd_readdir` signals
   end-of-directory by `bufused < buf_len`, not an errno.
3. **`fd_fdstat_get` on stdout drives program behavior** — wasi-libc
   computes `isatty()` from the reported filetype and rights; jq decides
   colored output with it. Report `CHARACTER_DEVICE` for tty-like,
   anything else for pipe-like.
4. **Everything is little-endian**; results go through out-pointers;
   `fd_seek`'s out-value is *signed* 64-bit; strings are `(ptr, len)`
   with no NUL; partial counts are written to out-pointers *before*
   returning a mid-iovec error.
5. **The sandbox check is one function**: reject absolute paths and
   root-escaping `..` with `NOTCAPABLE` (76)
   (browser_wasi_shim:src/fs_mem.ts:570-595) — and in our case even a
   miss lands inside vfs's own namespace, a second wall.
6. **Symlinks, sockets, and real `poll` are absent** in the reference
   shim and unneeded for the target CLI class.

### 4.3 The staging model matches the row store

browser_wasi_shim's structure is the design to copy: `Inode` (identity +
content) split from `Fd` (per-open cursor)
(browser_wasi_shim:src/fd.ts:119-142, src/fs_mem.ts:45-167). For vfs:
**the entry row is the inode; the open handle is an in-memory buffer plus
an offset.** `path_open` stages the whole file from one vfs read; reads
and seeks run against the buffer; `fd_close` (or `_start` returning)
writes back changed buffers in one vfs write. No fd/seek emulation over
SQL, and the DB-roundtrip latency question collapses to one read and at
most one write per file touched. Per-open state is never persisted.

### 4.4 What can and cannot be installed

Works today: anything with a wasm32-wasi build — jq, sqlite, uutils
coreutils, CPython itself — plus anything in Rust/C/Zig/TinyGo a
developer compiles with the wasi target. Will never work this way: tools
needing the network, subprocesses, or unported runtimes. Those get the
explicitly different tier: **host plugins** — trusted adapters against
the Shell's builtin API, installed by the developer at deploy time (the
`pip install` trust decision), never by the agent at runtime. Two verbs
of "install," two trust levels, never blurred. A curated registry can
later make `install jq` sugar for a host-side fetch (the kernel does the
networking, deliberately) followed by `write /bin/jq.wasm`.

## 5. Risks, named

1. **Monty maturity** (0.0.19, experimental, no audit). Mitigation:
   define the guest-visible capability contract once and treat the
   interpreter as swappable — CPython-on-WASI under wasmtime slots in
   behind the same contract if Monty stalls or its subset chafes.
2. **wasmtime-py's trap global is not thread-safe** — concurrent guest
   traps in one process can cross-contaminate. Serialize guest runs per
   process or use worker processes; decide before the web app is
   concurrent.
3. **Latency discipline**: whole-file staging bounds wasm I/O, but Monty
   scripts calling vfs verbs row-at-a-time remain a footgun. The
   capability set should lead with batch verbs, mirroring the 10k-batch
   write contract.
4. **Secrets hygiene**: the guest gets capabilities, never config. LLM
   keys and DB URLs must be unreachable from `external_lookup`, the WASI
   env, and error messages. Cheap now, painful to retrofit.
5. **wasm binary provenance**: install-by-write means the artifact is
   data until run, but a curated known-good registry beats agents
   fetching arbitrary binaries even so — malicious wasm can still burn
   budget and trash the workspace it is permissioned into (trash/restore
   mitigates; it does not excuse).

## 6. The proposed spike (feeds a spec)

One scenario proves the mechanism end to end, with no shell language and
no Monty — those layer on later:

    write /bin/jq.wasm        # a real prebuilt jq wasi binary, into vfs
    write /data/users.json
    cat /data/users.json | jq '.users[].name'

Success criteria: binary and data live only in vfs (assert zero host
preopens and no host file access); command resolution walks a vfs
`PATH`; argv/stdin/stdout wire through; guest `path_open`/`fd_read`
round-trip through vfs reads with whole-file staging; a written output
file lands back in vfs on close; exit codes surface (including the
clean-exit-as-exception path); epoch timeout kills a spinning binary
and is distinguishable from a crash; the compiled module caches keyed on
entry revision. First test before any real binary: the fd_write WAT
fixture from wasmtime-py's own suite. Fallback if no well-behaved
prebuilt jq exists: compile a trivial Rust wasi CLI — which doubles as
proof of the "developers bring their own tools" story.

## 7. Open questions

- [NEEDS CLARIFICATION: guest-runtime bet — Monty worker pool first with
  CPython-on-WASI behind the same capability contract later, both from
  day one, or wasm-only until Monty matures?] → pointer filed in
  `open-questions.md`.
- [NEEDS CLARIFICATION: pipe payload semantics — Result envelopes in the
  pipe with a declared canonical serialization (JSON lines?) at the
  structured→wasm-stdin boundary, or bytes-only pipes at v1?] → pointer
  filed in `open-questions.md`.
- Scope of the spike spec (wasm-exec mechanism only, as proposed, vs.
  bundling a minimal shell parser) is a spec-authoring decision, not a
  research fork; the spike as drawn assumes mechanism-only.
