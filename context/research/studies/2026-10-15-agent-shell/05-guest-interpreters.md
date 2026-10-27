# S5 — Guest interpreters for agent-written code: which one first, and what each costs

- **Date**: 2026-10-15
- **Researcher**: S5 (vfs agent-shell study)
- **Question**: Which guest interpreter should the vfs shell host first for agent-written Python
  and JavaScript, behind one capability contract, and what does each candidate cost?
- **Clones read (refreshed 2026-10-15 unless noted)**: `monty` @ 2bb9f08a (v1.1.0),
  `wasmtime-py` @ 280ce73 (49.0.0), `quickjs-rs` @ 278cf32 (0.2.5, 2026-07-24),
  `llm-wasm-sandbox` @ 680c927 (0.4.4), `just-bash` @ 9ab0e0d, `bashkit` @ b7904a4,
  `amla-sandbox` @ 169384f (0.2.8), `cpython` @ fdec4df, `pyodide` @ adc5b63,
  `RustPython` @ 88f5189 (0.6.1), `quickjs-ng` @ 9b06171.
- **Packages executed from PyPI/npm** (never added to vfs): `pydantic-monty` 1.1.0 (with
  `pydantic-monty-runtime` 1.1.0), `quickjs-rs` 0.2.5 + `wasmtime` 49.0.0, `llm-wasm-sandbox`
  0.4.4 + `wasmtime` 38.0.0, `amla-sandbox` 0.2.8, `wasmtime` 49.0.0 alone, `pyodide` 0.28.3
  under node v22.14.0.
- **Evidence labels**: `[EXECUTED]` I ran it on this machine (scripts and raw outputs in
  `experiments/s5/`); `[READ]` I read it in the named checkout or document; `[INFERRED]` my
  reasoning from the above; `[NOT VERIFIED: why]` could not be checked.
- **Machine**: Apple Silicon laptop, macOS 26.5, CPython 3.13 via `uv run`. Wall-clock numbers are
  benchmark facts for this memo, not test assertions (CLAUDE.md: count operations in tests).

---

## Summary

Host **Monty first** for Python. It is the only candidate whose shape already *is* the contract
we want: the guest reaches the host only through a dict of named functions (`external_lookup`),
an importable host module (`ExternalModule`), and an `os` callback that receives normalized
absolute paths — a function table over vfs verbs, no WASI shim. It runs in a worker subprocess
pool (the host process cannot be crashed), gives a session in 0.8 ms, prints in 0.1 ms, pauses
mid-call and serializes the paused program to 2.6 KB, and is MIT, at v1.1.0, with roughly 25
commits a month and a bounty program. Its cost is the subset: no class inheritance, no
generators, no `match`, no `del`, no method decorators, and only 23 stdlib modules (no `csv`,
`enum`, `io`, `string`, `struct`). Host **QuickJS-NG second** for JavaScript, via a small wasm
guest driven by wasmtime (quickjs-rs is the model: 0.74 MB guest, 150 ms cold compile once,
0.27 ms per context, host functions by name, interruptible). **CPython-on-WASI is the escalation
path, not the first guest**: with a Wizer snapshot it runs `print('hello')` in 6 ms per call
under wasmtime-py (measured, using bashkit's 3.14.8 artifact), and epoch interruption works, but
it has *no host-function door* — a Python program inside it can only talk to the host through
WASI syscalls — so "verbs as functions" needs a guest-side shim we would have to build and ship
(bashkit built one in C for HTTP). Pyodide needs a JS runtime and cannot be interrupted outside a
worker; RustPython builds to WASI but `-c` exits 1 silently at HEAD. The contract must be
specified as a *message protocol* (verb name + JSON args → `Result.to_payload()`), not as Python
callables, so that each interpreter binds it through its own door and a swap is a binding-layer
change. Durable pause is a host concern for v1 of `run`; choose an interpreter that can do it
(Monty can) but do not put a "suspended" Result in the v1 contract. wasmtime-py's trap global is
still a module global at 49.0.0 and it **does** cross threads: in 8 threads, 18% of raising host
calls surfaced another thread's exception — guests must run one per worker process, and host
imports must never raise.

---

## Findings

### 1. Monty has moved far since July: v1.1.0, 23 stdlib modules, mounts, an OS callback, snapshots

`[READ]` July's memo saw `pydantic-monty` 0.0.19 with nine stdlib modules and no filesystem. At
2bb9f08a the workspace version is 1.1.0 (`monty:Cargo.toml:27`), tags run `v0.0.19 … v0.0.23,
v1.0.0-beta.1..3, v1.0.0, v1.0.1, v1.1.0`, and commit counts by month are 24 (Jul), 22 (Aug), 26
(Sep), 9 (first half of Oct). The README now says "a secure Python sandbox, written in Rust, for
code written by AI", "Python 3.14 sandbox", with a commercial "Full Monty" server behind it
(`monty:README.md:14-16`).

`[READ]` The stdlib is a fixed set of 23 modules: `asyncio base64 binascii bisect collections copy
dataclasses datetime functools hashlib itertools json math os os.path pathlib posixpath random re
sys time typing unicodedata` (`monty:limitations/modules.md:19-45`). Explicitly absent: `abc
argparse array contextlib csv ctypes decimal enum fractions heapq hmac http inspect io logging
multiprocessing operator pickle queue socket string struct subprocess tempfile threading
traceback unittest urllib uuid warnings weakref zipfile zlib` (`modules.md:59-69`). `functools`
is only `reduce` and `partial`; `collections` only `deque Counter defaultdict namedtuple`.

`[READ]` Language: parsed with Ruff's parser; rejected at parse time: base classes and
metaclasses, decorators on methods (`@property`, `@classmethod`, `@staticmethod`), `async with`,
`yield`/`yield from` (generator *expressions* materialize to lists), `match`, `del`, `except*`,
PEP 695 `type`, `async for`, wildcard imports, t-strings (`monty:limitations/language.md:9-44`).
Decorators on plain functions and simple classes with `__init__`/methods/class vars are
supported; dataclasses are supported.

`[EXECUTED]` Probes (`experiments/s5/bench_monty.py`, output `out_monty.txt`):

| probe | result |
|---|---|
| `class B(A)` | rejected (parse: "does not yet support class…") |
| generator `yield` | rejected |
| `match` | rejected |
| `import csv` / `import enum` | `ModuleNotFoundError` |
| `@dataclass` | ok |
| `@property` | rejected |
| `del d[k]` | rejected |
| walrus `(y := 3)` | ok |
| `open('/tmp/x')` with no mount | `PermissionError` |

`[READ]` Filesystem: "A Monty sandbox has no filesystem" — `open()` and `pathlib` raise
`PermissionError` until the host supplies either `MountDir` (a host directory mapped to a virtual
path, modes `read-only`/`read-write`/`overlay`) or an **`os` callback** that answers filesystem
operations in host code with *normalized absolute paths* (`monty:docs/filesystem.md:1-80`).
`open()` keeps no live descriptor: every read/write is a one-shot OS call the host performs and
closes (`monty:limitations/open.md:12-24`) — the same whole-file staging the July memo chose for
wasm (§4.3). The handler surface is `AbstractOS` with `__call__(name, args, kwargs, is_async)`
and `NOT_HANDLED` (`monty:crates/monty-python/python/pydantic_monty/os_access.py:179-209`).

`[READ]` Host functions: `external_lookup={'name': callable}` resolved lazily when the guest
reads an undefined name; `inputs=` for eager bindings; `external_modules=` on `checkout()` makes
`import vfs` resolve to an `ExternalModule` whose callables run on the host and whose optional
`.pyi` stubs feed Monty's type checker (`monty:docs/host-functions.md`, `_monty.pyi:633-696`,
`crates/monty-python/README.md:46-56`). With `AsyncMonty` entries may be coroutines. Values
cross as copies; the allowlist of types that cross includes `bytes` (`limitations/host-values.md`).

`[READ]` Print: output goes only to a host callback `(stream, text)`; no real `sys.stdout`; chunks
of ~8 KiB or a 5 ms flush interval, always flushed before a host call and at the end of a turn
(`monty:limitations/print.md:1-60`; `print_flush_interval` on `checkout()`).

`[READ]` Limits: `ResourceLimits` has `max_feed_duration_secs`, `max_turn_duration_secs`,
`max_memory`, `max_recursion_depth`, `max_suspensions`
(`crates/monty-python/python/pydantic_monty/__init__.py:134-160`). Time budgets count execution
time, paused while suspended on the host; the dispatch loop polls every 256 instructions, native
loops every 64 items, so overshoot is bounded but real (`limitations/resource_limits.md`). The
pool adds `request_timeout` (kills the worker, `MontyCrashedError(timed_out=True)`).

`[EXECUTED]` **`max_suspensions` defaults to 1000 per checkout** and cannot be disabled: my first
1,000-host-call loop failed with `RuntimeError: suspension limit 1000 exceeded`
(`crates/monty-python/README.md:62-66`). Raising it on `checkout(limits=…)` fixed it. For vfs
this is a budget knob, and a reminder that the contract must be batch-first.

`[READ]` Security posture: "a language-level sandbox, not an OS-level one"; "no ambient
authority"; "the interpreter performs no filesystem I/O at all"; "no FFI, no C dependencies";
continuous bounty program (`monty:docs/security.md:1-40`). Host functions "run with your
process's full authority" — the capability set *is* the boundary. Snapshots are trusted input.

`[READ]` Execution model: always a worker subprocess pool, because "Monty processes can never be
made fully crash-proof against memory errors" (`_monty.pyi:578-590`); `feed_run` "blocks the
calling thread (with the GIL released)" (`_monty.pyi:723`); `max_processes` defaults to the CPU
count; a session is one checked-out worker. Worker baseline "about 2 MB plus its memory limit"
(`docs/alternatives.md`). `max_memory` enforcement depends on `monty-alloc` being the worker's
global allocator — which the pool worker has and an in-process embedder does not; bashkit held
its in-process embedding at 0.0.19 for exactly this reason
(`bashkit:knowledge/runtimes/python-builtin.md:72-110`). vfs would use the pool, so the hold does
not apply to us.

`[READ]` Snapshots: `feed_start` suspends at every host call (`FunctionSnapshot`,
`NameLookupSnapshot`, `FutureSnapshot`); `dump()` serializes idle sessions or a suspended feed
to opaque bytes; `load_snapshot` restores into a fresh session; a `{'future': …}` answer lets
other guest tasks run until a `FutureSnapshot` asks the host to settle by call id
(`monty:docs/snapshots.md:1-120`). Every snapshot carries `position`, a byte range into the
source. Only one suspension is live per session; branching = dump and restore twice.

### 2. Measured: Monty, quickjs-rs, llm-wasm-sandbox, raw wasmtime + CPython-WASI (3.12 and a 3.14 Wizer snapshot), Pyodide, amla

All scripts and raw outputs live in `experiments/s5/` (`bench_*.py`, `out_*.txt`). Commands:

```
uv run --with pydantic-monty  python -I experiments/s5/bench_monty.py
uv run --with quickjs-rs      python -I experiments/s5/bench_quickjs_rs.py
uv run --with llm-wasm-sandbox python -I experiments/s5/bench_llm_wasm_sandbox.py
uv run --with wasmtime        python -I experiments/s5/bench_wasmtime_cpython.py ~/Git/Repos/llm-wasm-sandbox/bin/python.wasm --epoch
uv run --with wasmtime        python -I experiments/s5/bench_wasmtime_cpython314_wizer.py <scratch>/python314.wasm <scratch>/root --epoch
uv run --with amla-sandbox    python -I experiments/s5/bench_amla.py
node experiments/s5/bench_pyodide_node.mjs      # from a scratch dir with `npm install pyodide@0.28.3`
```

`[EXECUTED]` The table. "hello" is `print('hello')` (or `console.log`) on a warm interpreter;
"loop" is `s += i` over `range(1_000_000)`; "host×1000" is the guest calling a host function
1,000 times and using its return value.

| candidate (package) | cold start | hello (warm) | loop 1e6 | host×1000 | interrupt | snapshot | RSS |
|---|---|---|---|---|---|---|---|
| **Monty** 1.1.0, worker pool | pool 5.0 ms; first checkout+feed 20 ms; warm checkout+feed 0.80 ms | 0.099 ms | 42 ms | 96 ms (96 µs/call) | `TimeoutError` at 201 ms for a 200 ms budget | 2,619 B; dump 1.2 ms, load 2.2 ms, resumed OK | worker 9–10 MB; host +2 MB |
| **quickjs-rs** 0.2.5 (QuickJS-NG in wasm, wasmtime 49) | 150 ms first Runtime+Context (JIT compile); then 0.27 ms per Context | 0.234 ms (host `print_`) | 72 ms | 283 ms (283 µs/call) | `TimeoutError: interrupted` at 201 ms | 1,310,772 B (whole linear memory) | host 33 → 91 MB |
| **llm-wasm-sandbox** 0.4.4 python.wasm (CPython 3.12.0 WLR, fuel on) | 1,319 ms | 1,202 ms (recompiles 26 MB every call) | 1,954 ms whole run | n/a (no host-fn door) | fuel trap | none | host 43 → 386 MB |
| **llm-wasm-sandbox** quickjs.wasm (qjs CLI, fuel on) | 166 ms | 140 ms | 874 ms whole run | n/a | fuel trap | none | +1 MB |
| **wasmtime-py 49 + CPython 3.12.0 WASI** (same binary, driven directly) | compile 738 ms once; `deserialize_file` 5.6 ms | 29 ms per `_start` (first 36) | ~477 ms | 1,000 `fd_write` syscalls ≈ 2.2 ms (2.2 µs each) — the only door | epoch `Trap INTERRUPT` at 206 ms | none | host 28 → 431 MB after compile |
| **wasmtime-py 49 + CPython 3.14.8 Wizer snapshot** (bashkit artifact) | compile 1,696 ms once (40.6 MB cwasm) | **6.0 ms** per call (first 13); `import csv,json,re,dataclasses,enum` 3.3 ms | ~522 ms | n/a (no host-fn door) | epoch `Trap INTERRUPT` at 201 ms | none (one instance per call) | host 29 → 415 MB after compile, 518 end |
| **Pyodide** 0.28.3 under node 22 | `loadPyodide` 1,045 ms | 0.171 ms | 166 ms | 1.8 ms (1.8 µs/call, JS FFI) | none in this mode (needs Worker + SharedArrayBuffer) | none | node 40 → 183 MB |
| **amla-sandbox** 0.2.8 (QuickJS+shell in one 15.3 MB wasm) | 1,870 ms | 1.50 ms | 71 ms | 113 ms (113 µs/call, through the constraint gate) | n/a | none | host 24 → 410 MB |
| **RustPython** 0.6.1 built to wasm32-wasip1 | compile 1,481 ms | `--version` 6 ms; `-c print(...)` exits 1, no output, no stderr | — | — | — | — | — |

Notes on the numbers:

- `[EXECUTED]` Monty's 96 µs per host call is one subprocess round trip (protobuf over a pipe).
  quickjs-rs's 283 µs is in-process but marshals through wasm memory with handle bookkeeping.
  Pyodide's 1.8 µs is a same-heap JS↔Python call — the fastest door, and the least isolated.
- `[EXECUTED]` llm-wasm-sandbox does not cache the compiled module: a warm `print('hello')` costs
  1.2 s on CPython and 140 ms on QuickJS because every `execute` recompiles. Driven directly with
  `Module.deserialize_file` the same CPython binary starts in 29 ms. Fuel costs about 1.6× on the
  Python loop (750 ms vs 477 ms) and about 6–12× on the QuickJS loop (443–874 ms vs 72 ms).
- `[EXECUTED]` The Wizer snapshot is the decisive CPython number: 6 ms per call with the
  interpreter already initialized at build time, versus 29 ms for a plain `_start`. bashkit
  reports 4.4 ms on Pulley and 0.95 ms native on a 4-vCPU x86 VM
  (`bashkit:knowledge/runtimes/cpython-wasm.md:108-116`); my 6 ms is Cranelift native on arm64
  through wasmtime-py's ctypes layer.
- `[EXECUTED]` In-process wasm RSS after a Cranelift compile is 400+ MB for CPython. The cwasm on
  disk (26–41 MB) is mmapped by `deserialize_file`, which is what a worker would do; I did not
  measure the deserialize-only RSS. `[NOT VERIFIED: needs a fresh process that only deserializes]`
- `[EXECUTED]` RustPython builds with `--ignore-rust-version` (requires rustc 1.99; 1.97.1 here)
  to a 49.8 MB wasm; `--version` works; every `-c`, `-S`, `-I`, script-file and `RUSTPYTHONPATH`
  variant exits 1 with no output. `[NOT VERIFIED: cause]`. Its README calls wasm support
  "preliminary" and targets the browser via wasm-bindgen (`RustPython:wasm/README.md:1-8`).

### 3. Candidate profiles the table does not show

**CPython-WASI** `[READ]`: WASI is a tier-2 CPython platform (`cpython:Platforms/WASI/README.md:3`),
target triple `wasm32-wasip1` since 3.14 (`Misc/NEWS.d/3.14.0a2.rst:1664`). Building needs the
WASI SDK and a build-Python; the dev container has them. Prebuilt binaries: WebAssembly Language
Runtimes `python/3.12.0+20231211` (llm-wasm-sandbox vendors it, `scripts/fetch_wlr_python.ps1:6`)
`[NOT VERIFIED: whether WLR still publishes newer builds]`; bashkit ships CPython 3.14.8 +
WASI SDK 24 + zlib + SQLite, Wizer-initialized with ~70 modules imported and `gc.freeze()`d, as
an 18.7 MB wasm (5 MB xz) plus a 3.2 MB bytecode-only stdlib zip
(`bashkit:crates/bashkit-cpython-wasm/artifacts/MANIFEST`, `knowledge/runtimes/cpython-wasm.md`).
The guest contract is strict: one preopen `/` at fd 3, the zip at
`/usr/local/lib/python314.zip`, one instance per call. The host is 42 preview1 imports written in
Rust over bashkit's VFS, files as whole in-memory buffers written back on close
(`cpython-wasm.md:181-200`) — the S4 shim, done. HTTP leaves the guest through a custom import
module `bashkit.http_request` backed by a C function in the guest (`guest/bashkit_main.c`): this
is the only way a CPython-WASI program calls a *named host function*, and it needs a C shim
compiled into the guest.

**Pyodide** `[READ]`: full CPython + ~packages; MPL-2.0; needs a JS engine (node, Deno, browser);
interrupts need a Web Worker and a `SharedArrayBuffer` interrupt buffer
(`pyodide:docs/usage/keyboard-interrupts.md:1-30`). Monty's comparison page rates its security
"poor … Python code can run arbitrary code in the JS runtime; only Deno restricts what that
runtime reaches" and measured 2,700 ms to a new sandbox under Deno (`monty:docs/alternatives.md`).
just-bash's `python3` uses a CPython *Emscripten* build in a worker thread with the JS bridge
removed ("`import js` fails with `ModuleNotFoundError`",
`just-bash:packages/just-bash/src/commands/python3/worker.ts:2-6`).

**QuickJS-NG** `[READ]`: C engine, MIT, `QJS_VERSION_MAJOR 0` (`quickjs-ng:quickjs.h:1463`);
native limits `JS_SetMemoryLimit`, `JS_SetMaxStackSize`, `JS_SetInterruptHandler`
(`quickjs.h:515,521,1193`). Four embeddings studied:

- *quickjs-rs* (LangChain, MIT): rquickjs compiled to `wasm32-wasip1`, pure-Python wheel,
  `wasmtime>=45` the only dependency (`quickjs-rs:pyproject.toml:24`). Guest 738 KB; a separate
  1.2 MB OXC transform guest strips TypeScript. Host functions: `ctx.register` /
  `@ctx.function`, sync or async; ES modules through `normalize(base, spec)` / `load(name)`
  callbacks, "`normalize` is where sandboxing lives — return `None` to refuse"
  (`README.md:60-80`). Interrupt: a `env.host_interrupt` import polled from the guest's hot loop,
  returning 1 past a per-eval deadline (`quickjs_rs/_engine.py:250-252,484-490`); default
  `memory_limit` 64 MB, `stack_limit` 1 MB (`runtime.py:41-46`). Snapshot: "the **entire** guest
  heap … as a flat image", restore validates a `build_id`, "treat snapshot bytes as trusted
  input" (`README.md:200-240`). The PyPI page for `langchain-quickjs` 0.3.9 (2026-10-13) says
  the middleware "embeds QuickJS through PyO3 and rquickjs" with prebuilt wheels — a native
  extension, which contradicts the July clone; `[NOT VERIFIED: whether quickjs-rs moved from wasm
  to a native PyO3 extension after 278cf32]`.
- *just-bash js-exec* (Vercel Labs): the `run` npm package 2.1.3 ("Secure QuickJS-backed
  JavaScript runtime with host functions and continuations", Apache-2.0,
  `github.com/vercel-labs/run`, dependency `quickjs-wasi` 3.6.0 — unpkg package.json,
  2026-10-15). "Each run uses a fresh QuickJS context inside a worker thread"; host function
  groups become sandbox globals (unpkg README). js-exec adds Node shims (`fs`, `child_process`
  → the shell, `fetch` → the allowlisted client, `Buffer`, `path`) and a `tools` proxy: guest
  `tools.math.add({a,b})` → host `invokeTool(path, argsJson, abortSignal) → Promise<string>`
  JSON in, JSON out (`just-bash:packages/just-bash/src/types.ts:291-295`,
  `commands/js-exec/run-runtime.ts:601,1013-1019`, `js-exec.invoke-tool.test.ts`). Limits:
  64 MB memory, 8 MB sync-bridge payload (`run-runtime.ts:77-79`). `Command.trusted` is a flag:
  "Host-provided commands are trusted by default … Set this to false to select the restricted
  extension boundary", and `internalIsExtension` "marks host extensions that receive a
  least-authority budget" (`types.ts:312-324`). The threat model names the untrusted script
  author as the primary adversary and states "just-bash protects untrusted *scripts*, not
  untrusted *hosts*" (`just-bash:THREAT_MODEL.md:1.1`).
- *amla-sandbox* (Python MIT; wasm runtime AGPL-3.0 OR BUSL-1.1 — study only): QuickJS *and* a
  shell inside one 15.3 MB wasm. The host drives a stepping loop — `cmd_create`,
  `runtime_step`, `submit` — in which the guest yields JSON host operations (`tool_call`, fs,
  output) and the host answers (`amla-sandbox:src/amla_sandbox/runtime/wasm.py:1312-1375,
  1421-1470`). Tool calls pass a capability check first: `ToolCallCap(method_pattern,
  constraints=ConstraintSet([Param("amount") <= 10000, Param("currency").is_in([...])]),
  max_calls)` (`capabilities/tool_call.py:1-30`). One lock serializes all wasm access because
  "wasmtime Store is NOT thread-safe" (`wasm.py:575-577`).
- *bashkit*: no QuickJS; TypeScript via ZapCode, a Rust TS interpreter, in-process, "~2 µs cold
  start", snapshot "<2 KB", "external function suspend/resume for VFS bridging"
  (`bashkit:knowledge/runtimes/zapcode-runtime.md:28-36`); Python via Monty in-process (held at
  0.0.19, env-gated) or CPython-WASI (above).

### 4. wasmtime-py's trap global is still a module global, and it leaks across threads

`[READ]` At 280ce73 (49.0.0): `LAST_EXCEPTION: Optional[Exception] = None` at
`wasmtime-py:wasmtime/_func.py:14`; the host-call trampoline stores any `BaseException` there and
returns a generic `Trap("python exception")` (`_func.py:212-216`); `enter_wasm` and
`maybe_raise_last_exn` read and clear it (`_func.py:236-250`). Not thread-local. The foreign
calls go through `ctypes.cdll`, which releases the GIL, so threads really run guests
concurrently. quickjs-rs documents a second, unrelated global: the `FUNCTIONS` slab is "a
process-global, UNLOCKED slab … `define_func` mutates it on registration and `Store.close()`
mutates it on teardown, with no synchronization", so they register four imports once on one
shared Linker and route per-instance through a thread-local `_CUR`
(`quickjs-rs:quickjs_rs/_engine.py:183-211`).

`[EXECUTED]` `experiments/s5/probe_wasmtime_trap_global.py`: 8 threads, each with its own Store
and instance of a WAT module whose export calls a host import that raises an exception tagged
with the thread's id, 2,000 calls each, three runs:

| outcome | run 1 | run 2 | run 3 |
|---|---|---|---|
| own tag (correct) | 10,431 | 10,001 | 10,105 |
| **foreign thread's tag** | 2,816 | 2,997 | 2,993 |
| bare `WasmtimeError` (exception lost) | 2,753 | 3,002 | 2,902 |

About 18% wrong exception and 18% lost exception under contention. The July memo's §5 risk 2
is confirmed by execution, not just by reading.

`[INFERRED]` Two consequences. (a) Guest execution in one Python process must be serialized
(amla's lock) or isolated per process (Monty's pool). (b) The hazard is only reachable when a
host import *raises*. quickjs-rs never raises through the trampoline: errors become error
handles the guest sees, and the interrupt is an import that *returns* 1. A WASI shim can do the
same — every preview1 function returns an errno — except `proc_exit`, which cannot return. The
July memo modeled `proc_exit` by raising `GuestExit`, which is exactly the hazard. Option for S4
to verify: call `linker.define_wasi()` first and shadow only the filesystem functions with
`allow_shadowing`, leaving `proc_exit`, clocks and `random_get` to wasmtime's own implementation,
whose exit surfaces as a Rust-side `ExitTrap` that never touches the Python global.
`[READ]` `Linker.allow_shadowing(True)` exists (`wasmtime-py:wasmtime/_linker.py:30-35`);
`[NOT VERIFIED: that a later define_func of one `wasi_snapshot_preview1` name shadows only that
name after `define_wasi()` — untested]`

### 5. The host-function door decides the contract shape

`[READ]` Three doors exist across the candidates:

| door | who | guest sees | host sees | latency measured |
|---|---|---|---|---|
| named function table | Monty `external_lookup` / `ExternalModule`; quickjs-rs `register`; amla tools; just-bash `invokeTool`; `run` host-function groups | a function or module | a callable with typed args, or `(name, JSON)` | 96–283 µs |
| OS/syscall table | Monty `os=` callback; WASI preview1 (bashkit, S4 shim) | `open()`/`os`/`pathlib` | `(op, normalized path, args)` | 2.2 µs per `fd_write` |
| same-heap FFI | Pyodide `globals.set` | a JS object | a Python object | 1.8 µs |

`[INFERRED]` CPython-WASI offers only the second door. A CPython program cannot call a named wasm
import without a C extension in the guest. So "vfs verbs as functions" on CPython-WASI means one
of: (i) a guest-side C module compiled into the binary that calls a custom import (bashkit's
`bashkit.http_request` pattern: length-prefixed request, two-step response), (ii) a pure-Python
guest module that speaks to the host over a reserved path (`open('/.vfs/rpc', 'w')`), which the
S4 shim intercepts, or (iii) files only — verbs reachable as `open()`/`os.listdir()` over the
staged filesystem, and `grep`/`glean` not reachable at all. (i) is the right one for production
and is real build work (WASI SDK, Wizer, a C shim, a release pipeline for a 40 MB cwasm).

### 6. Pause and resume: two very different "snapshots"

`[EXECUTED]` Monty's mid-feed snapshot of a program suspended inside a host call is 2,619 bytes
and restores into a fresh session in 2.2 ms, then resumes with the host's answer. quickjs-rs's
snapshot of a trivial context is 1.31 MB because it is the whole linear memory, and it is valid
only at a quiescent point ("no in-flight `eval_async`, no pending async host calls"
`[READ]` `quickjs-rs:README.md`) — it is a *heap* snapshot, not a *continuation*. The `run` npm
package advertises "continuations" with a `continuationSecret` and `continuationAudience`
(unpkg README) `[NOT VERIFIED: mechanism]`. bashkit snapshots shell state and the VFS, not a
running program (`bashkit:docs/snapshotting.md:1-20`). CPython-WASI has none: Wizer is a
build-time snapshot, and bashkit's contract is one instance per call.

### 7. Meta's rule of two, as the capability contract's safety argument

`[READ]` Meta, "Practical AI Agent Security", 2025-10-31 (fetched 2026-10-15): agents "must
satisfy no more than two of the following three properties within a session": [A] "can process
untrustworthy inputs", [B] "can have access to sensitive systems or private data", [C] "can change
state or communicate externally"; if all three are needed "the agent should not be permitted to
operate autonomously and at a minimum requires supervision". I could not find LangChain citing
the rule in `quickjs-rs`, `deepagents`, `deepagentsjs`, `just-bash` or the `langchain-quickjs`
PyPI page `[NOT VERIFIED: the LangChain citation the brief mentions]`; the langchain-quickjs page
instead frames it as "no ambient capabilities" and "the allowlist is the security boundary", with
`tools.*` calls capped at 256 per eval.

`[INFERRED]` A guest program in vfs always has [A] (it is agent-written and reads corpus data
that may carry injections) and [B] (the corpus). So the contract must deny [C] in the sense Meta
means it: no network, no host filesystem, no process spawn, no outbound channel of any kind.
State changes *inside* vfs are the point of the tool and are governed by the ladder (ADR 080) and
trash/restore, not by the rule of two; "communicate externally" is what the guest must never do.

---

## What this means for vfs

### A. The first guest is Monty; the second is QuickJS-NG; CPython-WASI is the escalation

**Monty first** `[INFERRED from 1, 2, 5, 6]`:

- Its three doors (functions, module, `os` callback) map one-to-one onto what the shell needs:
  the vfs verbs as functions, `import vfs` with stubs the type checker uses, and `open()` over
  vfs with normalized absolute paths — no WASI shim, no C shim, no wasm build pipeline.
- It is already a process pool: the GIL is released during a feed, each session is its own
  worker, a crash is `MontyCrashedError` and a replacement, and N agent sessions are N workers
  (capped by `max_processes`, default CPU count). The wasmtime-py thread problem does not
  arise.
- Latency fits the agent loop: 0.8 ms to a session, 0.1 ms per print, 96 µs per verb call.
  Agents doing read → edit → write get a program for the cost of one tool call.
- Pause/resume and typed snapshots exist if we later want them, at kilobytes.
- Cost: the subset. Agents will write `class B(A)`, generators, `match`, `import csv`, `enum`,
  `@property`; each is a parse-time or import-time error the shell must render as a classified
  error with the next move ("this guest runs Monty's Python subset; the full interpreter is
  `python3 --full` / rung X"). The subset is a product fact to document, not to hide.
- Cost: a 27.5 MB worker binary (`pydantic-monty-runtime`, measured on disk arm64; docs say the
  download is ~4.5 MB) as a dependency. Pin it. Monty's own security hold story (bashkit) is about
  in-process embedding and does not apply to the pool.

**QuickJS-NG second** (JavaScript) `[INFERRED from 2, 3]`:

- A 0.74 MB wasm guest compiled once (150 ms) then 0.27 ms per context, with named host
  functions, a module-loader callback that can serve `/bin/*.js` entries straight from vfs, an
  interrupt import, a 64 MB heap cap, and MIT everywhere. quickjs-rs is the reference shape;
  whether we depend on it or build our own guest in `crates/` is a packaging decision (ADR 057
  says our engine work lives in our crate; a wasm guest is a *program*, not engine code — it can
  be a dependency as long as the binding is ours).
- Run it in the same worker-process pool as Monty, one guest per worker, host imports never
  raising (finding 4).

**CPython-WASI as the escalation** (full Python, when the subset chafes) `[INFERRED from 2, 3, 5]`:

- The Wizer path makes it fast enough (6 ms per call measured; 1–4 ms claimed by bashkit) and
  epoch interruption works. But it needs the S4 shim (preview1 over vfs verbs) *and* a guest-side
  C module for verb calls, a WASI-SDK/Wizer build pipeline, and a 40 MB cwasm artifact per
  wasmtime version. That is a project of its own; it should land behind the same contract after
  the shell, pipes and Monty are proven.
- Not Pyodide (needs node/Deno, uninterruptible outside a worker, `import js` is a door into the
  host runtime), not RustPython (preliminary; `-c` does not run at HEAD).

**Swap cost with the contract held constant**: if the contract is a message protocol (below), a
swap is a binding layer: Monty binds verbs as `ExternalModule` callables and `os=`; QuickJS binds
them as registered globals and a module loader; CPython-WASI binds them as a guest module over a
custom import plus the preview1 shim. The host side — `Authority` binding, budgets, stdout rows,
error classification — is shared and written once. The guest side differs per interpreter and
is the swap cost: for Monty it is a `.pyi` stub; for QuickJS a `.d.ts`; for CPython-WASI a C
shim plus a `.py` module.

### B. The capability contract (what every guest sees), as a typed list

`[INFERRED from 1, 3, 5, 7; S3 owns the ABI, this is what the interpreter needs from it]`

```
GuestProgram:                         # one run of agent-written code
  language:  Literal["python", "javascript"]
  source:    str                      # the program; for Monty, fed as one feed
  argv:      list[str]                # after the interpreter name
  stdin:     RowStream                # rows in (text rows or typed rows); never host bytes
  env:       Mapping[str, str]        # only names the shell declares; never os.environ
  cwd:       str                      # a vfs path
  budget:    Budget                   # below

Budget:
  max_duration:   float               # execution seconds (Monty max_feed_duration; epoch for wasm)
  max_memory:     int                 # bytes (Monty max_memory; Store.set_limits / memory_limit)
  max_host_calls: int                 # Monty max_suspensions; our own counter elsewhere
  max_stdout:     int                 # bytes before truncation is reported as an error row

VerbTable (the guest module `vfs`):   # exactly ops.py minus DEVELOPER_OPS, no `cli`
  read(paths | patterns, ...)      -> Payload
  write(entries: list[Entry], ...) -> Payload      # batch-first: 10,000 entries in one call
  edit(...), glob(...), grep(...), glean(...), graph(...), list/ls, move, copy, trash, restore …
  # every verb: bound to the caller's Authority at the host; the guest never names a principal;
  # every verb: returns Result.to_payload() — rows + classified errors — the MCP structured wire;
  # media rows cross as rows: {content: None, data: bytes, mime_type: ...}; never base64 text;
  # no verb takes or returns a host path, URL, or config value.

FileTable (what `open()` / `os` / `pathlib` see):
  one-shot ops: open/exists/stat/listdir/read/write/append/mkdir/remove/rename
  -> each is one vfs verb call with the Authority; whole-file staging; paths normalized absolute

StdStreams:
  stdout -> RowStream of text rows (one row per line, or one row per chunk when not line-shaped)
  stderr -> error rows (classified "guest_stderr"), never merged into stdout
  exit_code -> int in the Result's summary; non-zero is a fact, not an exception (ADR 076)

Denied, by construction (rule of two: no [C]):
  network, host filesystem, host env, process spawn, host modules other than `vfs`,
  config/secrets (LLM keys, DB URLs are not in any mapping the binding layer reads),
  the `cli` meta-verb from inside a guest (no nested shell; see fork 5).
```

Binding notes per interpreter:

- Monty: `VerbTable` is an `ExternalModule('vfs', attrs={...}, stubs=<.pyi>)` on `checkout()`;
  `FileTable` is an `AbstractOS` subclass passed as `os=`; `StdStreams` is `print_callback`;
  `Budget` is `ResourceLimits` plus the pool's `request_timeout`. No `MountDir` — vfs has no host
  directory to mount.
- QuickJS: `VerbTable` registered as a `vfs` global (sync and async forms); `FileTable` not
  offered (JS has no `open()` builtin) — a tiny `fs` shim over `vfs.read/write` if agents expect
  Node; `StdStreams` is a registered `console`; `Budget` is the interrupt import + memory limit.
- CPython-WASI (later): `VerbTable` is a guest `vfs` C module over a custom import module;
  `FileTable` is the preview1 shim; `StdStreams` is `fd_write`; `Budget` is epoch + store limits.

### C. Rules to adopt, and what to reject

Adopt:

1. **One process per guest at a time; a pool of worker processes** (Monty's shape, extended to
   wasm guests). Never run two guests on two threads of one Python process (finding 4).
2. **Host imports never raise** into a wasm guest; they return error codes (quickjs-rs's
   discipline). Exceptions are for the Python side of the boundary only.
3. **Batch-first verbs in the guest table**, with `max_host_calls` as a budget the agent can see
   in the error when it trips (Monty's 1,000 default is a sane floor; make it ours and name it).
4. **The subset is documented at the surface**: `python3 --version` inside the shell reports
   "Monty 1.1.0 (Python 3.14 subset)" and the rejection errors carry the next move.
5. **Compile-once cache keyed on (wasmtime version, config fingerprint, binary revision)** for any
   wasm guest, as the July memo said; never compile per run (llm-wasm-sandbox's 1.2 s per call).

Reject:

- Pyodide and RustPython as hosts (finding 2, 3).
- Mounting host directories into any guest (`MountDir`, `WasiConfig.preopen_dir`): vfs is the
  filesystem; the only `FileTable` is the verb-backed one.
- Fuel as the default budget for Python guests: 1.6× on loops and it cannot interrupt a blocking
  host call; epoch (wasm) and execution-time limits (Monty) are enough. Keep fuel for the
  deterministic-replay case if it ever matters.
- A whole-memory snapshot as the pause mechanism (1.3 MB per trivial context; trusted input).

---

## Forks for the ADRs

**Fork 1 — Monty-first vs CPython-WASI-first vs QuickJS-first.**
Options: (a) Monty first, QuickJS second, CPython-WASI as escalation; (b) CPython-WASI first
because full Python; (c) QuickJS first because it is the cheapest wasm guest and JS agents exist.
*Lean: (a).* The evidence: Monty's doors are the contract (no shim, no C), 0.8 ms sessions, pool
isolation for free, 2.6 KB snapshots; CPython-WASI costs a shim + a guest C module + a build
pipeline before the first verb call works; QuickJS is right for JS but vfs is a Python library
serving Python-writing agents first. The subset is the price and it is a documented one.

**Fork 2 — One interpreter per process vs a worker pool.**
Options: (a) one long-lived interpreter in the serving process, guests serialized behind a lock
(amla); (b) a pool of worker processes, one guest per worker at a time, sessions checked out
(Monty); (c) one process per session for its lifetime. *Lean: (b).* (a) caps concurrency at one
guest per process and still runs untrusted code in the serving process; (c) pays a process per
idle session. (b) is what Monty already implements; for wasm guests the worker mmaps the cwasm
and holds one Store at a time, and the 18%/18% exception contamination cannot occur.

**Fork 3 — Is pause/resume in scope for v1 of `run`?**
Options: (a) yes: `run` can return a "suspended" Result with a snapshot id, and a later call
resumes it with a value; (b) no: a `run` either completes or fails within its budget; waiting on
a subagent is the host loop's job (the agent calls a tool, gets a result, and runs a *new*
program). *Lean: (b) for v1*, with the interpreter choice keeping (a) open. Argument: the durable
unit in every host we studied is the agent turn (LangGraph state, deepagents, the MCP tool call),
not a program counter inside a guest; Monty's `FunctionSnapshot` + `dump()` make (a) a few-day
addition later, and quickjs-rs shows the alternative (heap images) is the wrong primitive. The
v1 contract should leave one hole: `Result` classification gains a reserved
`suspended` kind only when (a) lands, never speculatively.

**Fork 4 — Where the verb table lives in the guest namespace.**
Options: (a) `import vfs` (Monty `ExternalModule`, QuickJS module loader), (b) bare globals
(`read(...)`, `grep(...)`), (c) both. *Lean: (a).* A module carries stubs for Monty's type
checker, keeps the global namespace clean for the agent's own names, and is the same spelling in
Python and JavaScript. just-bash's `tools.*` proxy and amla's `stripe_listTransactions` globals
show both work; a module is the one that survives a third interpreter.

**Fork 5 — May a guest re-enter the shell (`vfs.sh("ls | grep x")`)?**
Options: (a) no nested shell: the program table is the shell's, the guest gets verbs only;
(b) yes, through the `cli` meta-verb with the same Authority (just-bash's `child_process.exec`
→ its own shell; amla's `shell.run`). *Lean: (a) for v1.* ADR 069's no-shell rule is an
enforcement property; a guest that can spawn shell lines reintroduces quoting and parsing inside
untrusted code. Revisit when pipes exist and the pipe payload (S3) is a row stream the guest can
produce directly.

**Fork 6 — Depend on quickjs-rs, or build our own QuickJS-NG guest.**
Options: (a) depend on `quickjs-rs` (pure Python + wasmtime; MIT); (b) build a `wasm32-wasip1`
guest from `quickjs-ng` in our tree and bind it ourselves. *Lean: start with (a) to prove the
contract, decide (b) when the binding layer is stable;* note the unverified sign that quickjs-rs
may have become a native PyO3 extension after July, which would change its isolation story.

---

## Sources

- `monty` @ 2bb9f08a (2026-10-15, MIT; commercial Full Monty separate): `README.md`,
  `Cargo.toml:27`, `limitations/{modules,language,resource_limits,print,open,host-values,
  filesystem}.md`, `docs/{security,filesystem,host-functions,snapshots,alternatives}.md`,
  `docs/api/python/{pools,os}.md`, `crates/monty-python/python/pydantic_monty/{_monty.pyi,
  __init__.py,os_access.py}`, `crates/monty-python/README.md`, `crates/monty-wasm-runtime/Cargo.toml`.
- `wasmtime-py` @ 280ce73 (2026-09-24, Apache-2.0, 49.0.0): `wasmtime/_func.py:14,212-250`,
  `wasmtime/_ffi.py:1`, `tests/test_store.py:18-48`.
- `quickjs-rs` @ 278cf32 (2026-07-24, MIT, 0.2.5): `README.md`, `pyproject.toml:7,24`,
  `quickjs_rs/{runtime,_engine,context,snapshot,threading}.py`, `tests/test_threading.py`,
  `benchmarks/README.md`, `.github/THREAT_MODEL.md`.
- `llm-wasm-sandbox` @ 680c927 (2025-11-27, MIT, 0.4.4): `README.md`, `pyproject.toml:43`,
  `sandbox/{host,runtime_paths}.py`, `docs/FUEL_BUDGETING.md`, `scripts/fetch_wlr_python.ps1:6-7`,
  `bin/{python,quickjs}.wasm` (26,267,204 and 1,427,671 bytes).
- `just-bash` @ 9ab0e0d (2026-10-15, Apache-2.0): `THREAT_MODEL.md`, `packages/just-bash/
  package.json:121`, `src/types.ts:291-331`, `src/commands/js-exec/{README.md,run-runtime.ts,
  js-exec.invoke-tool.test.ts}`, `src/commands/python3/{python3.ts,worker.ts}`.
- `bashkit` @ b7904a4 (2026-10-15, MIT; embedded CPython PSF): `knowledge/runtimes/
  {cpython-wasm,python-builtin,zapcode-runtime}.md`, `crates/bashkit-cpython-wasm/{README.md,
  src/lib.rs,artifacts/MANIFEST}`, `docs/{snapshotting,custom_builtins_js}.md`,
  `crates/bashkit-scripted-tool/README.md`.
- `amla-sandbox` @ 169384f (2026-05-15; Python MIT, wasm runtime AGPL-3.0 OR BUSL-1.1 — study
  only): `README.md`, `src/amla_sandbox/{sandbox.py,runtime/wasm.py,capabilities/tool_call.py,
  _wasm/__init__.py}`, `examples/constraints.py`.
- `cpython` @ fdec4df (PSF): `Platforms/WASI/README.md`, `Misc/NEWS.d/3.14.0a2.rst:1664`.
- `pyodide` @ adc5b63 (MPL-2.0): `docs/usage/keyboard-interrupts.md`, `Makefile.envs:4`.
- `RustPython` @ 88f5189 (MIT, 0.6.1): `README.md:111-144`, `wasm/README.md`.
- `quickjs-ng` @ 9b06171 (MIT): `quickjs.h:515,521,1193,1463`.
- vfs: `context/research/2026-07-24-hermetic-runtime-and-wasm-cli.md` §3, §4.1, §5, §6.
- Web (all fetched 2026-10-15): Meta, "Practical AI Agent Security" (Agents Rule of Two),
  https://ai.meta.com/blog/practical-ai-agent-security/ (published 2025-10-31);
  `langchain-quickjs` on PyPI, https://pypi.org/project/langchain-quickjs/ (0.3.9, 2026-10-13);
  `run` 2.1.3 on unpkg, https://unpkg.com/run@2.1.3/package.json and `/README.md`
  (Apache-2.0, `vercel-labs/run`, dependency `quickjs-wasi` 3.6.0).
- Experiments (this folder): `bench_monty.py` → `out_monty.txt`; `bench_quickjs_rs.py` →
  `out_quickjs_rs.txt`; `bench_llm_wasm_sandbox.py` → `out_llm_wasm_sandbox.txt`;
  `bench_wasmtime_cpython.py` → `out_wasmtime_cpython312.txt`, `out_wasmtime_rustpython.txt`;
  `bench_wasmtime_cpython314_wizer.py` → `out_wasmtime_cpython314_wizer.txt`; `bench_amla.py` →
  `out_amla.txt`; `bench_pyodide_node.mjs` → `out_pyodide_node.txt`;
  `probe_wasmtime_trap_global.py` → `out_trap_global_probe.txt`. Untrusted artifacts (the
  unpacked bashkit CPython snapshot, the RustPython build, the pyodide npm install) were kept in
  the session scratchpad, never in the repo, and run only under wasmtime or node.
