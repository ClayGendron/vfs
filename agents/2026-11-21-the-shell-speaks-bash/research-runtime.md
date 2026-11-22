# Research Q1–Q4: fuel, pausing, memory and the cost of the runtime

Sources. Five reference repositories were cloned on 2026-11-21 as siblings of this checkout, without blobs (`--filter=blob:none`), each at its upstream default branch, and read only; no code was copied. `../wasmtime-py` (github.com/bytecodealliance/wasmtime-py) at `8202959` of 2026-11-20 ("Bump to 51.0.0"), Apache-2.0 with the LLVM exception. `../wasmtime` (github.com/bytecodealliance/wasmtime) at `fb792bf` of 2026-11-21, Apache-2.0 with the LLVM exception, as a sparse checkout of `crates/cranelift/src/func_environ.rs`, `crates/wasmtime/src/config.rs` and `crates/wasmtime/src/runtime/{store.rs,limits.rs,trap.rs}`. `../wasi_python` (the PyPI project `wasi-python`, homepage wasipython.dev) at `a85cac7` of 2026-11-17 on its default branch `dev`, Apache-2.0; the spec named this clone as present, and it was not, so it was cloned here. `../monty` (github.com/pydantic/monty) at `5f4a3df` of 2026-11-20 (v1.7.0-beta.1), MIT. `../wasmi` (github.com/wasmi-labs/wasmi) at `05d2de3` of 2026-11-19 (2.0.2), MIT or Apache-2.0. Packages measured: `wasmtime` 51.0.0 from PyPI, the `wasmtime` crate 51.0.0 and the `wasmi` crate 2.0.2. Machine: 4 cores, 15 GB, Linux 6.18 x86_64; Rust 1.97.0 with the `wasm32-unknown-unknown` target; CPython 3.13.18 in a scratch venv made with `uv`. The guest is a throwaway crate (`regex` with `std` and `unicode-perl`, a `BTreeMap` state in a `thread_local` `RefCell`, `alloc`/`dealloc`/`step` exchanging bytes through linear memory, a CPU loop, and one import `host.slice_spent() -> i32`), built `--release` with fat LTO, `panic = "abort"` and `strip`, to 462,975 bytes. Every figure is a median on this machine and moves with the machine; the ratios are what carry over. The scripts are in the session scratchpad (`research-runtime/bench_py.py`, `check2.py`, `rss.py`, `hosts/bench/src/main.rs`, `guest/src/lib.rs`), not in the repository.

## R1 How fuel and interruption are counted

### What wasmtime counts

Fuel is added by the compiler, not measured. Cranelift keeps a function-local counter in a register, adds each operator's cost to it at the end of every basic block, and stores it to the store's context only before a call, a return or an `unreachable` (`fuel_before_op` in `func_environ.rs`). Most operators cost 1; `nop`, `drop`, `block`, `loop`, `else` and `end` cost 0. At the commit studied the cost table is configurable (`Config::operator_cost`).

The counter is checked only at a function's entry and at each loop header (`fuel_check`, called from `fuel_function_entry` and `translate_loop_header`). A stretch of straight-line code after the last check runs to its end. Measured: `spin(1000)` needs 17,025 fuel; given exactly 17,025 it returns with 0 left, and given 17,024 it also returns, with no trap. The bound is therefore "at most one check interval past the limit", never "exactly the limit".

wasmtime's own documentation of `Config::consume_fuel` says the count is not precise when wasm traps, and that "embedders which need precise fuel consumption metrics should not reuse a Store after a trap". Measured: after an out-of-fuel trap, `get_fuel` reads 0. After an epoch trap the fuel counter is not written back at all: a 20 ms loop interrupted by an epoch reported 0 fuel spent, because the loop made no call that would have stored the register. wasi-python records the same fact and reports `fuel_used = None` for a call that ended on its deadline (`_fuel_used` in `_call.py`).

### Determinism

Within one build the count is a function of the starting state and the inputs. Four different `step` inputs, run in sequence in three fresh instances, spent `[541735, 826360, 13894, 3413420]` fuel each time. A second engine in the same process, compiling the module again, gave the same four numbers. The `wasmtime` crate 51.0.0 driven from Rust gave the same four numbers as `wasmtime-py` 51.0.0: the count belongs to the module and the wasmtime version, not to the host language.

The count is not a function of the line alone once the instance has history. One instance given the same 600-byte line six times spent `1330033, 816964, 815654, 817669, 819381, 819381`. The first call compiles the regex; the later ones differ by up to 0.4% because the allocator's free lists differ. The law of decision 6 ("the same line with the same replies spends the same fuel") holds when each run starts from a fresh instance, and does not hold for a reused one.

wasmi counts in its own units, about five times wasmtime's on this guest (28,239,263 against 5,586,745 for the 4 KB step), and is equally deterministic across fresh instances. A fuel number is meaningful only with the runtime and its version named beside it.

### A slice per call, and how much was used

A host can set the fuel before each call and read what is left after it: `used = set - get_fuel()`. This is exact for a call that returns. `wasmtime-py` exposes `Config.consume_fuel`, `Store.set_fuel` and `Store.get_fuel` publicly, and `Store.get_fuel` works from inside a host import during the call: the counter is stored before every call, so the import reads the live value. Measured: a loop that asks the host every ~17,000 fuel whether 5,000,000 fuel has passed stopped 11,003 fuel past the mark, less than one poll interval.

What wasmtime-py does not expose: the epoch-deadline callback (`wasmtime_store_epoch_deadline_callback`, only in the private `_bindings`), fuel and epoch access through a `Caller`, `trap_on_grow_failure`, and any async call. `fuel_async_yield_interval`, the Rust API that suspends a call every N fuel instead of trapping, exists only behind the crate's `async` feature and needs `call_async`; the C function is bound in `_bindings.py`, but wasmtime-py has no async call path to use it with. wasi-python reaches the missing pieces through a declared seam (`_wasmtime_ffi.py`) of 32 private names (the epoch callback, `Caller` fuel, a reusable `wasmtime_func_call`, the store's context), checked at import, and pins `wasmtime>=50,<51`; wasmtime-py is at 51.0.0 today.

### Interruption by wall time

wasi-python runs two engines per process, one metered and one plain, because fuel changes the compiled code (`_engine` in `_engines.py`). Both enable epoch interruption. One daemon thread advances every engine's epoch every 10 ms (`TICK_S = 0.01`) while any call with a deadline runs; a call's deadline is a count of ticks; a cancel is noticed within 5 ticks through the epoch callback; and the store is closed after every call, trapped or not, because a trapped store is otherwise held by a reference cycle until the collector runs.

Measured with the public API: a thread calling `engine.increment_epoch()` while the guest ran a loop stopped it with `TrapCode.INTERRUPT` 172 to 274 µs later (five runs). The calling thread releases the GIL for the whole wasm call (`wasmtime-py` loads its library with `ctypes.cdll`): another Python thread ran 4.3 million loop iterations during one 342 ms guest call. The host import trampoline takes the GIL back for each import.

### When fuel runs out mid-call, is the instance still usable?

The runtime lets it be called again; the guest's own invariants do not survive. Four observations with `wasmtime-py`; the first was repeated with the `wasmtime` crate and with wasmi, with the same result:

| What trapped | What the next call saw |
|---|---|
| Out of fuel inside a function holding the machine's `RefCell` borrowed | The next `step` trapped `UNREACHABLE`: the borrow was never released, the new borrow panicked, and `panic = "abort"` is `unreachable`. Same in the `wasmtime` crate and in wasmi's plain call. |
| Out of fuel, any function | The shadow stack pointer (the global `__stack_pointer`) is not restored: 32 bytes lost in one trap; three traps inside a recursion lost 9,248 bytes each. |
| Shadow stack overflow (256-byte frames, depth 5,000) | `MEMORY_OUT_OF_BOUNDS`, and every later call that touches the shadow stack trapped the same way, `step` included. A function with no stack frame (`spin`) still ran. |
| Deep plain recursion (`recurse_plain(10_000_000)`) | `STACK_OVERFLOW` from wasmtime's own stack limit; the next `step` worked. |

A trap is therefore the end of that instance, not of the line's state alone. Monty reaches the same rule from the other side: its wasm host discards an instance that ends a turn without a terminating event and takes another from the pool, and its Python package runs every worker as a subprocess because "a monty process can never be made fully crash-proof against memory errors (stack overflows, allocator aborts)".

wasmi offers the one non-trapping exhaustion found. `TypedFunc::call_resumable` returns `TypedResumableCall::OutOfFuel` when fuel runs out; the host sets more fuel and calls `resume`, and the call continues where it stopped. Measured: a call holding the `RefCell` borrowed, given 10,000,000 fuel at a time, ran through 87 slices to its end, and the next `step` returned the stored variable. A plain `call` that runs out of fuel traps exactly as wasmtime's does and leaves the same poisoned borrow.

## R2 How an interpreter pauses at a host call and resumes

Monty's core API is a typestate. `run` returns `RunProgress`, an enum of `FunctionCall`, `OsCall`, `NameLookup`, `ResolveFutures` and `Complete` (`run_progress.rs`). Each variant owns the whole execution state and offers only the resume methods that fit it: `FunctionCall::resume(self, result, print)`, `resume_pending` (answer later, as a future), `abort(exc)`; `ResolveFutures::resume(self, Vec<(call_id, result)>)` accepts any subset of the pending ids and refuses an id not in `pending_call_ids`. Each method consumes the suspension, so a second resume of the same one is a compile error in Rust and a `RuntimeError` in the Python binding.

Monty's call ids are a counter in its scheduler (`next_call_id`, incremented per external call in `scheduler.rs`), so they follow the program's flow and not the clock. Every suspension also carries `position`, the byte range of the expression that suspended. Both match decision 5 of the spec; the spec's key adds the loop iteration and the call path, which a flat counter does not give when several tasks issue requests in an order that depends on replies.

Monty does not suspend with Rust `async`. Its VM is a bytecode interpreter whose call frames are an explicit `Vec<CallFrame>` (`bytecode/vm/mod.rs`); a suspension takes those frames into a `VMSnapshot`, and every suspension is `serde`-serializable, which is how a paused run is dumped and loaded in another process. Its Python-level `async`/`await` is its own scheduler over host futures (`async_exec.rs`), not Rust's.

What follows for a machine written as Rust `async fn`s polled by a small executor, inside a wasm instance:

- The paused state is the compiler-generated futures in linear memory. The instance lives from one `step` to the next, so nothing has to be serialized between steps; the cost is that a paused run cannot be dumped and moved, as Monty's can. The spec's durable run resumes by replaying keys, so it does not need a dump.
- A trap in the middle of a `poll` leaves a future half-advanced, which is the poisoned-instance case of R1. The rule is the same: the instance is dropped and the line ends.
- A slice is a leaf future that calls the host import and returns `Pending` once when the slice is spent; `step` then returns with no new request, and the next `step` polls again from the same point. This is the cooperative counterpart of wasmi's resumable fuel.
- Nesting still costs stack. A boxed recursive future keeps its state on the heap, but each `poll` calls its child's `poll`, so polling a depth of N uses N native frames. The depth budget of decision 9 still has to be checked before each descent. The two stacks in a Rust wasm32 module are wasmtime's native wasm stack (`max_wasm_stack`, which wasi-python sets to 8 MiB) and Rust's shadow stack in linear memory, 1 MiB at the bottom of memory by default; the guest here has 17 pages (1.06 MiB) of initial memory.

## R3 How memory is bounded without measuring the process

wasmtime's `StoreLimits` caps each linear memory in bytes (`memory_size`; "applied to each linear memory individually"). `wasmtime-py` exposes it as `Store.set_limits(memory_size=...)`. Measured under a 32 MiB cap: a raw `memory.grow` past it returned -1 and memory stayed at 17 pages; `Vec::try_reserve_exact(64 MiB)` returned `Err`; `try_reserve_exact(8 MiB)` succeeded and memory grew to 146 pages; `vec![1u8; 64 MiB]` trapped `UNREACHABLE`; a store whose cap is under the module's initial 17 pages refuses to instantiate ("memory minimum size of 17 pages exceeds memory limits"). The Rust crate's builder also has `trap_on_grow_failure`, which wasmtime-py's `set_limits` does not offer.

In a Rust `wasm32-unknown-unknown` module a refused `memory.grow` reaches the allocator as a null pointer; an infallible collection then calls `handle_alloc_error`, whose default hook writes to a standard error that the target does not have and then aborts, and abort on this target is the `unreachable` instruction. The process survives; the instance ends with a trap. A fallible call (`try_reserve`) gets an `Err` and can answer a budget error instead. In the run measured, the instance remained callable after the allocation trap, because the failed allocation happened before any state changed; that is luck of the case, not a property, and the instance is dropped as in R1.

Monty bounds memory by counting in the allocator. `monty-alloc`'s `LimitedAllocator` is the module's `#[global_allocator]`; it tracks live bytes, the interpreter compares them with a soft limit at checkpoints and raises `MemoryError`, and a higher hard ceiling makes the allocator abort, which on wasm is a trap. Its README gives the reason for counting rather than asking the kernel: the units are the bytes the program requested, not address space. It also notes the limit of the method: only a binary or a wasm module may declare a global allocator, because in a native cdylib it would take over the host process's allocator. Monty's expansions also check their size before they build (`check_repeat_size`, `check_replace_size` in `resource_checks.rs`), as decision 7 requires.

For the shell this gives three layers, in the order a byte meets them: the machine's own count (decision 7), which refuses before allocating and is the same in the native and the wasm build; a counting global allocator, possible only in the wasm build, which gives the exact live bytes for a law test and a second wall; and the store's `memory_size`, the hard wall, where a missed byte ends the call in a trap. Linear memory never shrinks, so the store cap bounds the high-water mark, not what is live.

## R4 What running the machine inside a wasm runtime costs

### Size added to an install

| Carrier | Download | Installed or linked | Notes |
|---|---|---|---|
| `wasmtime` 51.0.0 from PyPI | 9.5 MB (manylinux x86_64 wheel; 7.0 to 9.6 MB across the 11 platform wheels) | 30.2 MB, of which `_libwasmtime.so` is 29.7 MB | a Python dependency; a major release about monthly |
| `wasmtime` crate 51.0.0 linked into a cdylib (`cranelift`, `runtime`, `std`; thin LTO, one codegen unit, stripped) | +3.5 MB to a wheel (zlib of the delta) | +10.3 MB (10,607,048 against a 306,480-byte baseline cdylib) | the wheel budget in `scripts/ci.sh` is 50 MB |
| `wasmi` crate 2.0.2 linked the same way (`std`, `validate`) | +0.48 MB to a wheel | +1.32 MB (1,623,808 against the same baseline) | pure Rust, no code generation, no signal handlers |
| the guest module itself | 0.16 MB to a wheel (zlib) | 463 KB | the same for every carrier |

A cold build of the three probe cdylibs took 2 min 5 s on four cores, most of it cranelift.

### First load

| Step | `wasmtime-py` | `wasmtime` crate | `wasmi` crate |
|---|---|---|---|
| import | 31 to 43 ms (seven runs); RSS 21 MB after import | none beyond the extension's own load | none |
| compile the 463 KB module | 196 to 209 ms with fuel, 120 to 141 ms without; RSS +41 MB during compilation | 672 ms with the default features turned off, which drops `parallel-compilation` | 2.5 ms (wasmi translates lazily) |
| load a compiled `.cwasm` instead (1.4 MB) | 0.28 ms from a file in a cold process, RSS +3.7 MB; 0.8 to 1.0 ms from bytes | `Module::deserialize`, same mechanism | not applicable |
| instantiate (store, linker, instance) | 102 to 153 µs; 14 µs with the linker reused | 11.6 µs | 31.9 µs |
| RSS per live instance after one step | about 300 KB | not measured | not measured |

A `.cwasm` is native code tied to the exact wasmtime version and configuration; wasi-python keeps it in a cache directory it checks for ownership and mode before trusting it, and compiles in the process otherwise.

### Each call across the boundary

| Operation | `wasmtime-py` public API | `wasmtime-py` through the raw C call, arrays made once | `wasmtime` crate | `wasmi` crate |
|---|---|---|---|---|
| bare call of an export with no work | 9.7 µs | 2.0 µs | 25 ns | 76 ns |
| `step` with 64 bytes in and out (alloc, write, call, dealloc, read; about 10 µs of guest work) | 68 µs | 19 µs | 12.4 µs | 68.9 µs |
| `step` with 4 KB | 594 µs | 505 µs | 464 µs | 2,989 µs |
| host import called from the guest, reading the fuel | 9.6 µs (6.7 µs for an import that does nothing) | — | 3.9 ns | 23.8 ns |

The public `Func.__call__` rebuilds the function type and the value arrays on every call; that is most of its 9.7 µs, and it is the call wasi-python replaces through its private seam. A `step` exchange is three calls plus a write and a read, so it costs about 55 µs of boundary through the public API, about 9 µs through the raw call, and about 2 µs in the crate.

### Guest speed, with and without fuel

| Workload | wasmtime plain | wasmtime with fuel | wasmtime with fuel and epochs | wasmtime with epochs only | wasmi |
|---|---|---|---|---|---|
| 20 M rounds of a shift loop (`wasmtime-py`, 15 interleaved rounds) | 37.6 ms | 37.7 ms | 37.5 ms | 37.5 ms | 157 ms (crate) |
| 4 KB `step`, call-heavy string and regex code (`wasmtime-py`) | 469 µs | 585 µs (+25%) | 589 µs | 554 µs | 2,989 µs (crate) |

Fuel costs nothing on a tight loop and about a quarter on code that calls often, because the counter is stored and reloaded around every call. Epochs on top of fuel add under 1%. On this machine wasmtime spends 0.083 ns per unit of fuel on the call-heavy step and 0.11 ns on the loop; 10,000,000 fuel is about 1 ms of guest work. wasmi runs the same module 4.2 times slower on the loop and 6.4 times slower on the step.

### Against the reference deployment's peak

The peak is about 20 verb calls a second. Take a line as one fresh instance and 20 steps (requests answered plus slices). Through `wasmtime-py`'s public API that is 0.15 ms to instantiate and 20 × 55 µs = 1.1 ms of boundary, about 1.3 ms a line and 25 ms a second at peak, 2.5% of one core. Through the crate it is 0.012 + 20 × 0.002 ms, about 0.05 ms a line, 1 ms a second. Compilation is paid once a process: 0.2 s through `wasmtime-py`, or 0.3 ms from a `.cwasm`. The boundary is affordable on every carrier. What differs is the guest's own compute: a line that spends 1 ms in the machine under wasmtime spends about 6 ms under wasmi, 120 ms a second at peak if every call were that heavy, and the 1,000,000-iteration loop budget makes the heavy case reachable.

## What follows for the build

(a) How the host carries the runtime. Link the `wasmtime` crate into `vfs-core`'s pyo3 extension and embed the machine's module in it. It adds 10.3 MB to the extension and about 3.5 MB to the wheel, against `wasmtime-py`'s 9.5 MB download and 30 MB installed. It gives a 25 ns call and a 4 ns host import, against 9.7 µs and 6.7 to 9.6 µs from Python. It reaches every API the shell needs in public Rust (`Caller::get_fuel`, the epoch-deadline callback, `ResourceLimiter` with `trap_on_grow_failure`, `fuel_async_yield_interval`), where `wasmtime-py` needs wasi-python's 32-name private seam. And it removes a monthly-major Python dependency whose range already conflicts with wasi-python's pin (`<51`). Turn on the crate's `parallel-compilation` feature, or precompile the module at build time and deserialize it at first use (0.3 ms). The deserialize call is `unsafe` and belongs in the host binding, never in the shell crate. wasmi is the fallback when size or build time decides: it adds 1.3 MB, compiles in 2.5 ms, uses no signal handlers, and pauses on fuel without trapping. It costs 4 to 6 times the guest compute, and its fuel units are its own. `wasmtime-py` is adequate as the test-only runtime that the spec's "Choices to confirm" allows: through it, the boundary costs 2.5% of a core at peak. wasi-python's public `run()` runs only its own CPython artifacts, so its host code cannot drive this module. What carries over from it is its patterns: one metered and one plain engine, a 10 ms epoch ticker thread, a deadline counted in ticks, and the store closed after every call.

(b) The step slice as a host import. Yes: `host.slice_spent() -> i32`, or a `fuel_left() -> i64`, polled by the machine at its safe points (each command, each loop iteration, each chunk of an expansion). A leaf future returns `Pending` once when it answers yes. In the crate the import costs 3.9 ns, so it can be polled at every safe point. The measured overshoot is under one poll interval: 11,003 fuel past a 5,000,000 mark. Do not make the slice a fuel trap: a trap poisons the instance (R1). Under `wasmtime-py` the same import costs 6.7 to 9.6 µs, which would force coarse polling; this is one more reason for the in-extension runtime. `fuel_async_yield_interval` with `call_async` is the other route the crate opens, a slice with no import at all. It needs the `async` feature and a fiber stack per suspended call, and it was not measured here.

(c) The default fuel slice, and whether fuel-trap recovery is possible. Recovery is not possible. After a fuel trap the runtime answers calls, but the guest has lost a borrow, its shadow-stack pointer, or both; wasmtime's documentation says not to trust the count after a trap; and the count reads 0 after a fuel trap and is stale after an epoch trap. So the line's total budget is the store's fuel; its trap is the budget error with status 137; and the instance is dropped. Each line runs in a fresh instance: 12 µs in the crate, 0.1 to 0.15 ms through `wasmtime-py`. A fresh instance is also what makes the fuel law hold, since a reused instance moved the count by up to 0.4% on an identical line. As a starting point for step 3, take a slice of 10,000,000 fuel, about 1 ms of guest work here, for a boundary overhead of about 0.2% in the crate (about 6% through `wasmtime-py`'s public API). The epoch ticker stays the wall under it: at a 10 ms tick it stops a runaway slice within about a tick plus 0.3 ms.
