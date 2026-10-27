# S11 — Python anywhere: the guest Python that runs inside a web server with no root, no kernel features and nothing to install

- **Date:** 2026-10-15
- **Researcher:** S11 (vfs agent-shell study)
- **Question (Clay, 2026-10-15):** "We are going to need to revisit the guest python problem, it needs to be a solution that can run anywhere and especially run in a web server." Binding: numpy, pandas, scipy, matplotlib and the common utilities importable; runs inside an ordinary Python web server process or its unprivileged subprocesses — PaaS container, serverless host, plain Linux box, macOS laptop, Windows — with no root, no `CAP_SYS_ADMIN`, no user namespaces, no kernel mounts, no Docker, no Deno (its runtime ends in October 2027), nothing to install beyond `pip install vfs-py` plus a downloadable artifact; sandboxed so the guest reaches nothing but vfs; file access through vfs verbs under the caller's `Authority`; a matplotlib PNG back as a media row; budgets; N concurrent sessions.
- **Builds on:** study `11-python-in-vfs.md` (S10: the VFSFS Emscripten adapter, the 9P server, the bridge rules — reused, not re-proved) and ADR 086 (under revision: its sidecar needs bubblewrap, Seatbelt or a 9P mount, which "anywhere" cannot promise). Study 05 (guest interpreters) and 04 (the filesystem over the sandbox boundary) for the shapes.
- **Clones read:** none new. `pyodide` adc5b63 (`src/js/environments.ts`, `src/js/compat.ts`; the 0.28.3 npm distribution S10 fetched), `sandbox-runtime` 9a277e5 (`src/sandbox/macos-sandbox-utils.ts`, for the SBPL shape only), `cpython` fdec4df via study 11. No clone was modified. The S10 Pyodide 0.28.3 npm copy was duplicated into `experiments/s11/untrusted/pyodide-pm/` (git-ignored) with one line guarded (finding 6).
- **Packages executed, never added to vfs:** `pythonmonkey` 1.3.2 (SpiderMonkey 136 in-process; MIT), `mini-racer` 0.14.1 (`py_mini_racer`, V8 14.4 in-process; ISC), `wasmtime` 49.0.0, native `numpy 2.4.2 / pandas 3.0.5 / matplotlib 3.11.1` (macOS, via `uv run --with`), the S10 Docker image `vfs-s10-sci` (python 3.13.15, numpy 2.5.4, pandas 3.0.6, matplotlib 3.11.2) run as uid 1000 with `--cap-drop=ALL --security-opt=no-new-privileges`, node 22.14.0 as a control only.
- **Evidence labels:** `[EXECUTED]` ran here (scripts and raw outputs in `experiments/s11/`); `[READ]` read in the named checkout or document; `[FETCHED]` web, with URL and date; `[INFERRED]` reasoning from the above; `[NOT VERIFIED: why]`.
- **Machine:** Apple M1 Pro, 32 GB, macOS 26.5, CPython 3.13.11 via `uv run` (PythonMonkey runs were on 3.12.12 — finding 10 says why); Docker Desktop 29.7.2, LinuxKit kernel 7.0.12, arm64. Wall-clock numbers are memo facts, never test assertions.

---

## Summary

Two designs meet "anywhere", and both were executed end to end over the live tree with the study-11 job (pandas `read_csv` of a vfs row, matplotlib `savefig` landing as an `image/png` bytes row, `to_csv` landing as a text row, `os.listdir` over vfs).

**(C) Native CPython that sandboxes itself, with the vfs filesystem reached through a Python-level bridge.** No root, no capabilities, no namespaces, no mount, no Docker. On Linux the child calls `landlock_create_ruleset` / `landlock_add_rule` / `landlock_restrict_self` (unprivileged since kernel 5.13) and installs a seccomp-bpf filter denying `socket`, `connect`, `execve`, `execveat`, `ptrace` with `EPERM`; on macOS it calls `sandbox_init` with a deny-default Seatbelt profile. I ran it as uid 1000 with every capability dropped under Docker's default seccomp profile — the closest emulation of an unprivileged PaaS process this Mac can offer — and on macOS directly from `uv run`. Both: Landlock ABI 8 / Seatbelt applied in ~1–10 ms; a C-level `fopen("/etc/hosts")` inside the guest is **refused by the kernel**, not silently allowed; `socket()` and `execve()` return `EPERM`; threads work; numpy, pandas and matplotlib (pip's own, 112–132 MB RSS) ran the job unchanged in **0.6–1.0 s wall, 9 bridge calls, 9 verbs, 69 SQL statements** — the 9P form needed 536 `stat`s uncached. The bridge is 250 lines of guest Python (`open`, `io.open`, `os.stat/listdir/mkdir/remove/rename` routed over one inherited socket) and 150 lines of host asyncio. This is ADR 086's sidecar with the privileged parts removed: the "OS sandbox" becomes a self-applied one, the "9P mount" becomes the bridge ADR 086 pin 3 already named as the macOS floor. Its honest limits: the bridge covers Python-level file access, not C-level (`sqlite3` on a vfs path, a C library's own `fopen`), and Landlock is absent on kernels older than 5.13 (AWS Lambda reports 5.10) and under gVisor (Cloud Run gen1) — there the filesystem wall falls back to what the host already gives the web server, and seccomp still holds the network/exec wall.

**(A) Pyodide inside the Python process under an embedded JavaScript engine installed by pip.** Under **PythonMonkey** (SpiderMonkey, MIT, 14 MB wheel) Pyodide 0.28.3 loaded in **1.15 s**, numpy in 0.23 s, numpy+pandas+matplotlib in 1.2 s, and the whole job ran with S10's VFSFS adapter calling a **synchronous Python function** for every Emscripten `node_op`/`stream_op` — no SharedArrayBuffer, no Atomics, no relay thread, no sidecar: **20 bridge calls, 20 verbs, 106 SQL, the PNG as an `image/png` row**, the same counts as the Deno sidecar. The host *is* the Python process. Under **py_mini_racer** (V8, ISC, 18 MB wheel) Pyodide loaded and ran numpy, and V8's own `timeout` interrupted `while True: pass` at **300 ms** with the isolate alive afterwards — but mini_racer can only expose *async* Python functions to JS, so the synchronous filesystem bridge is impossible there without JSPI stack-switching (present in its V8; unproven). The costs are real and measured: **489 MB RSS after load, 947 MB after the job**; a wasm OOM does not crash the host but leaves the process at **3.9 GB RSS** (wasm memory never shrinks and `MAXIMUM_MEMORY` is a 4 GB build constant); **no interrupt under PythonMonkey** (the GIL is held while wasm spins — a Python timer thread never ran in 83 s of CPU, killed by hand); one realm per process; and the JavaScript door is wide open by default — from the guest, `js.python.eval('__import__("os").getpid()')` **returned the host pid and read `/etc/hosts`** — and closes only because we delete `python`, `__host`, `read`, `readbuffer`, `load`, `os` from the realm after loading, which held (`AttributeError` for each). The lock is ours to keep.

**(B) A static WASI CPython with the scientific stack linked in** is not a 2-hour job and I did not attempt it: no wasi-sdk here, and the only working path for numpy on WASI is componentize-py's build-time linker (wasi-wheels v0.0.2 and a 2026-09 DSPy-in-wasm build: numpy with lapack-lite, no BLAS, no threads, pydantic-core, pyyaml, regex, sqlalchemy). numpy+pandas alone is a 1–3 week toolchain project on that path; scipy (Fortran, no WASI flang story) and matplotlib (freetype, libpng, qhull, C++) have never been built for WASI and would be Pyodide's package work redone — **months, by us, forever**. **(D)** Node is pip-installable after all (`nodejs-wheel`, unofficial), but its permission model carried two 2026 CVEs and does not reach worker threads; Bun has no permission model; a `rusty_v8` embedding in our crate is a 38 MB static library per target plus owning the shell-mode loader; wasmer cannot run Emscripten's Pyodide; hosted sandboxes are a backend, not an answer to "anywhere".

**Recommendation:** tier it, behind one program ABI, in this order. **Tier 1, the floor that runs anywhere Python runs: (C) self-sandboxed native CPython with the bridge**, the full pip ecosystem at native speed and 112 MB, with the interpreter and package set fetched by hash as ADR 086 pin 1 already says. It degrades honestly: Landlock+seccomp (Linux ≥ 5.13), Seatbelt (macOS), seccomp-only (old kernels, gVisor), a Job-object/restricted-token child on Windows `[NOT VERIFIED]`. **Tier 0, the hermetic lane for hosts that cannot spawn or must not trust a self-sandbox: (A) Pyodide in-process under PythonMonkey**, in a subprocess pool for memory and interrupt, with the door closed. Pyodide's package set, 0.5–1 GB per worker, ~1 s cold. Trigger between them: a host policy value (`python.runtime = native | pyodide`), never automatic. ADR 086 keeps its interpreter, its package set, its warm pool, its budgets and its output rules; it drops the words bubblewrap, 9P-mount-first and "a host without them cannot run Python".

---

## Findings

### 1. What "anywhere" rules out in ADR 086, and what it leaves standing (READ, INFERRED)

`[READ]` ADR 086 pins 2 and 3: bubblewrap on Linux, Seatbelt on macOS, vfs served over 9P and mounted by the kernel's v9fs client, with "a host-side mount bound in, or a FUSE adapter" as spec 172's first spike, and the consequence "a host without bubblewrap, Seatbelt or WSL2 cannot run Python until it supplies a container". `[READ]` bubblewrap needs unprivileged user namespaces (or a setuid binary); a 9P mount needs `CAP_SYS_ADMIN` in a mount namespace; FUSE needs `/dev/fuse`. `[INFERRED]` A PaaS container, a Cloud Run gen1 sandbox, a Lambda function and a shared-host web server give none of those. So the pins that must change are the *sandbox mechanism* and the *filesystem transport*; the pins that stand are the managed interpreter (1), staging (4), Authority at the host (5), budgets (7), rows out (8), no network (9), the warm pool (10), QuickJS (11). This study only re-decides 2, 3 and 6.

### 2. Candidate C on Linux, unprivileged: Landlock + seccomp apply under Docker's default profile as uid 1000 with no capabilities (EXECUTED)

`[EXECUTED]` `experiments/s11/probe_landlock_seccomp.py` → `out_probe_landlock_seccomp_docker.json`. Pure `ctypes`, no package: `docker run --user 1000:1000 --cap-drop=ALL --security-opt=no-new-privileges vfs-s10-sci python -I probe.py /usr /tmp`.

| step | result |
|---|---|
| kernel / uid | `7.0.12-linuxkit`, aarch64, uid 1000, Python 3.13.15 |
| `landlock_create_ruleset(NULL, 0, VERSION)` | **ABI 8** |
| ruleset: every FS right; `/usr` read+execute, `/tmp` read-write; `prctl(PR_SET_NO_NEW_PRIVS)`; `landlock_restrict_self` | `ok` in **0.03 ms** |
| seccomp-bpf: deny `socket connect execve execveat ptrace` → `EPERM`, arch check, everything else allow; installed with `seccomp(SECCOMP_SET_MODE_FILTER)` | `ok` in 0.13 ms |
| after: `open("/etc/passwd")` | `EACCES` |
| after: **C-level `fopen("/etc/hosts")` through `libc`** | **`EACCES`** — the kernel refuses it; the bridge is not what stands between the guest and the host |
| after: `listdir("/")`, `listdir("/etc")` | `EACCES` |
| after: write `/tmp/probe.txt` | allowed (the RW rule) |
| after: `socket(AF_INET)` | `EPERM`; `subprocess.run(["/bin/true"])` → `EPERM` |
| after: `threading.Thread().start()` | works (`clone` is not denied) |
| after: `import numpy, pandas` | numpy 2.5.4, pandas 3.0.6 in 398 ms; matplotlib Agg PNG 23,053 bytes in 395 ms |

`[FETCHED 2026-10-15]` Landlock facts behind the numbers: unprivileged by design since Linux 5.13 (ABI 1); ABI 2 adds `REFER` (5.19), ABI 3 `TRUNCATE` (6.2), ABI 4 network (6.7), ABI 5 `IOCTL_DEV` (6.10), ABI 6 scoping (6.12), 7–8 later (https://docs.kernel.org/userspace-api/landlock.html). The probe sizes the ruleset struct by ABI and masks rights the ABI does not know, which is the compatibility rule the kernel docs ask for. The rule set is *deny by default for every handled right*; a path not under an added rule is unreachable.

`[INFERRED]` Docker's default seccomp profile allowlists the three `landlock_*` syscalls and `seccomp`; `--security-opt=no-new-privileges` is the same bit the child sets itself. A PaaS that runs containers under Docker/containerd defaults with a kernel ≥ 5.13 gives exactly this; finding 9 lists who does.

### 3. Candidate C, the job, on Linux and on macOS: 9 bridge calls, 9 verbs, 69 SQL, the PNG as a row (EXECUTED)

`[EXECUTED]` `bridge_host.py` (the vfs process: `InMemoryStorage` + `VirtualFileSystem`, `Authority.of(Principal("agent-7"))` on every verb, SQL counted with `before_cursor_execute`) + `bridge_guest.py` (the child). Order in the child, which is the security argument: (1) take the bridge — an inherited socketpair fd on macOS; on Linux-in-Docker a TCP connect to the host made **before** the sandbox, kept as the one open socket while seccomp then denies any new `socket()`; (2) pre-import numpy, pandas, matplotlib so their shared objects are mapped; (3) self-sandbox; (4) install the bridge; (5) read the script **from vfs** and `exec` it. Outputs `out_bridge_linux_landlock.json`, `out_bridge_macos_seatbelt.json`.

| | Linux, Docker as uid 1000, cap-drop ALL, Landlock ABI 8 + seccomp | macOS, `uv run` child, Seatbelt `sandbox_init` |
|---|---|---|
| wall (spawn → done) | **0.95 s** (connect 8 ms, pre-import 504 ms, sandbox 1.0 ms, run 107 ms) | **0.64 s** (pre-import 483 ms warm; 28.8 s the first time while matplotlib built its font cache; sandbox 10.6 ms, run 111 ms) |
| guest RSS | 105 MB | 108 MB |
| bridge calls / wait | 9 / 57 ms | 9 / 30 ms |
| verbs | stat 3, read 3, ls 1, write 2 | same |
| SQL | **69** (stat 12, read 12, ls 5, write 32) | 69 |
| probes after the sandbox: C `fopen /etc/hosts` | `EACCES` | `EPERM` (once `/private/etc` left the profile; with it in, allowed — the profile decides) |
| `open /etc/passwd`, `~/.ssh/config`, `~/.zshrc` | denied | denied |
| `socket()` + `connect` | `socket` → `EPERM` | `socket` ok, `connect` → `EPERM` (`(deny network*)`) |
| `execve` | `EPERM` | `EPERM` (`(deny process-fork)` + exec only the interpreter) |
| write `/tmp` | allowed (RW rule) | denied (not in the profile; the RW scratch dir is) |
| threads | ok | ok |
| the PNG | `/out/plot.png` kind=file **mime_type=image/png** size 52,520 version 1 data_is_png content_is_none | same, 48,444 bytes |
| `summary.csv` | text row, `region,sum,mean,max…` | same |
| guest stdout | `platform: linux numpy 2.5.4 pandas 3.0.6 mpl 3.11.2` | `platform: darwin numpy 2.4.2 pandas 3.0.5 mpl 3.11.1` |

The mapping that produced the counts, one verb per operation (the staging rule from study 04 and ADR 086 pin 4, now at the Python level): `open(path)` for read → one `read` staged into a `BytesIO`; `open` for write → nothing until `close`, which is one `write` (text if UTF-8 decodes, else bytes — the `.png` became `image/png` by extension at write time, exactly as S10 observed); `os.stat`/`os.path.exists/isfile/getsize` → `stat`; `os.listdir` → `ls`; `os.mkdir` → `mkdir`; `os.remove/rmdir` → `delete(cascade=False)`; `os.rename/replace` → `move`; errors come back as `OSError(errno)` from the result kind (`not_found` → `ENOENT`, `exists` → `EEXIST`, `wrong_kind` → `ENOTDIR`, `not_empty` → `ENOTEMPTY`, `permission_denied` → `EACCES`, `read_only` → `EROFS`). The wire is 4-byte length + JSON header + raw body, no base64 (S10's rule 8).

`[EXECUTED]` The Seatbelt profile (in `bridge_guest.py`, `sandbox_macos`): `(version 1) (deny default)`, exec only the interpreter path, `file-read-metadata`, `file-read*` on `/usr/lib /usr/share /System/Library /Library/Preferences /private/var/db/timezone /dev/urandom /dev/null /dev/random` plus the interpreter prefix, `file-write*` on `/dev/null` plus one scratch dir, `sysctl-read`, two `mach-lookup` names, `signal (target self)`, `(deny network*)`, `(deny process-fork)`. Fifteen lines. `sandbox_init` returned 0 from an unprivileged child; `sandbox-exec` is deprecated as a *command* but `sandbox_init` is what Anthropic's `sandbox-runtime` and Chrome still call (`sandbox-runtime:src/sandbox/macos-sandbox-utils.ts` `[READ]`, read for the SBPL shape, not copied: theirs is allow-default with credential denies and regex folding for the 1,025-byte literal limit; ours is deny-default because a guest needs only the interpreter).

`[INFERRED]` Compared with the 9P form (study 11 finding 5: 536 `stat`s, 2,211 SQL uncached; 17 / 121 with `cache=loose`): the Python-level bridge sees only the calls Python makes, so there is no kernel revalidation to tame and no staleness window to declare. The cost moved elsewhere — finding 4.

### 4. What the Python-level bridge does not cover, and what that costs (EXECUTED, INFERRED)

The bridge patches `builtins.open`, `io.open`, `os.stat`, `os.lstat`, `os.listdir`, `os.mkdir`, `os.remove`, `os.unlink`, `os.rmdir`, `os.rename`, `os.replace`, `os.getcwd` for paths under `/vfs`; everything else keeps its native meaning, and the sandbox decides what native may touch. `[EXECUTED]` That was enough for pandas (`get_handle` opens through `open`), matplotlib (`cbook.open_file_cm` → `open`), `os.listdir`, `os.path.getsize`, and the script read itself. `[INFERRED]` Not covered, and each a known shape to add or to refuse with a classified error:

- `os.scandir`, `pathlib` fast paths that bypass `os.stat` (3.13's `Path.iterdir` uses `os.scandir`), `os.walk`, `glob` → add `scandir` (one `ls`), the rest follow.
- **C-level file access on a vfs path**: `sqlite3.connect("/vfs/t.db")`, PIL's C decoders reading from a *path* (PIL opens via Python `open`, so it works), a compiled library's own `fopen`. These go to the host kernel and are **denied by Landlock/Seatbelt** (finding 2: `fopen` → `EACCES`). That is the right failure — loud, not silent — and the rule to document: "a program that needs a real file for a C library stages it to the scratch directory and copies it back", which is what S10's 9P sqlite round trip did implicitly at clunk time.
- `open(fd)`, `os.open` + `os.read` (raw fd I/O) → not routed; a guest using them on a vfs path gets `ENOENT`/`EACCES` from the kernel.
- `mmap` on a vfs path → not possible, refuse.
- The scratch directory (`--rw`) is real host disk the sandbox allows: matplotlib's font cache (`MPLCONFIGDIR`), `tempfile`, numpy's `__pycache__` writes (none in `-I` with a read-only prefix). It is per-run, private, and the only host path the guest can write.

`[EXECUTED]` What it costs: 9 calls and ~3–6 ms of bridge wait per call including the verb and the SQL; the pre-import of the three packages (0.5 s) dominates the run, and the warm pool (ADR 086 pin 10) amortizes it.

### 5. Candidate A: Pyodide inside the Python process (EXECUTED)

#### 5a. PythonMonkey: the whole job, with a synchronous filesystem bridge and no sidecar

`[EXECUTED]` `pyodide_pm_host.py` + `pyodide_pm_shim.js` → `out_pm_job.json`. The realm is bare SpiderMonkey 136: no `process`, `Deno`, `Bun`, `require`, `fetch`, `TextDecoder`, `TextEncoder`, `performance`, `crypto`, `SharedArrayBuffer`, `Atomics` (`out_probe_pythonmonkey.txt`). Pyodide's loader has a third mode besides browser and node — **`IN_SHELL`, the d8/jsshell path**, detected by `typeof read === "function" && typeof load === "function"` (`pyodide:src/js/environments.ts:46` `[READ]`), which reads files with `read(path)` / `readbuffer(path)`, loads the lock file with `read`, and skips its script loader when `_createPyodideModule` already exists (`compat.ts:140-262`, the UMD `pyodide.js`). So the shim defines `read`, `readbuffer`, `load`, `print`, polyfills `TextEncoder`/`TextDecoder` (utf-8 and utf-16le; validated against node's natives on 2,000 random strings, 0 mismatches), `performance.now`, `crypto.getRandomValues` (entropy from `os.urandom` on the host), evaluates `pyodide.asm.js` and `pyodide.js` into the global scope, and calls `loadPyodide({indexURL: "/pyodide/"})`. Every file the loader asks for is answered by a Python function by basename from the S10 npm dir and wheel cache (`loader_reads`: lock file, stdlib zip, the wasm, then one wheel per package).

| step | ms | RSS MB |
|---|---:|---:|
| `import pythonmonkey` | 3,308 (first import on a cold wheel; later runs ~300) | 116 |
| eval `pyodide.asm.js` (1.0 MB) + `pyodide.js` | 31 + 1 | |
| **`loadPyodide`** (8.6 MB wasm + 2.4 MB stdlib) | **1,150** | 489 |
| `loadPackage` numpy, pandas, matplotlib, one call each (28 MB of wheels) | 1,199 | 778 |
| mount VFSFS at `/vfs`, read the script from vfs, run the job | 3,127 (20 bridge calls, 56 ms inside them) | 947 |
| **total** | **5.5 s wall** | 947 |

Bridge: `ops stat 13, read 3, readdir 2, write 2`; `verbs stat 13, read 3, ls 2, write 2`; **106 SQL** (stat 52, read 12, ls 10, write 32) — the same counts, to the statement, as S10's Deno-sidecar run, because VFSFS is the same adapter: only the transport changed. The PNG row: `/out/plot.png kind=file mime_type=image/png size_bytes=51795 version=1 data_is_png=True content_is_none=True`; `summary.csv` a text row; the trash empty; guest stdout `platform: emscripten numpy 2.2.5 pandas 2.3.1 mpl 3.8.4`.

The transport is the point: Emscripten's `node_ops`/`stream_ops` are synchronous, and PythonMonkey lets a JS function call a Python function **and get the return value on the same thread** (`out_probe_pythonmonkey.txt`: `sync callback: string:hello…`; a `bytearray` crosses as a `Uint8Array`, and S10's `Atomics.wait` relay disappears). The host answers each call by driving the vfs coroutine to completion on a private event loop on the same thread (`loop.run_until_complete`), since JS calls arrive outside any running loop. Three things the loader path needed that a browser or node never asks for (finding 6).

Also measured `[EXECUTED]`: `--packages numpy` alone: load 1,153 ms, numpy 231 ms, 537 MB, `numpy.__version__ == 2.2.5`; numpy+pandas 1,167 ms / 730 MB; numpy+matplotlib 758 ms / 597 MB; a **second `loadPyodide` in the same realm** (`out_pm_two.json`): 1,524 ms, **+194 MB → 724 MB** for two instances, which share the realm's globals and nothing else — no isolation between sessions in one process.

#### 5b. py_mini_racer: loads and runs numpy, interrupts at 300 ms, survives an OOM — and cannot host the synchronous bridge

`[EXECUTED]` `probe_mini_racer.py`, `probe_mini_racer_jspi.py`, `pyodide_mini_racer.py` → `out_mini_racer.json`. V8 14.4.258 has `WebAssembly`, `SharedArrayBuffer`, `Atomics`, `setTimeout`, **`WebAssembly.Suspending` and `WebAssembly.promising` (JSPI)**, and no `TextDecoder`, `performance`, `crypto`, `process`. Artifacts reached the realm as base64 strings through `eval` (62.7 MB of base64 in 397 ms, verified byte-exact against Python checksums for the wasm, the stdlib and the lock file; `mr_integrity`), which inflates memory and is not the production shape (a Rust or C host function would hand the bytes over).

| step | result |
|---|---|
| `loadPyodide` | **2,603 ms**, 738 MB RSS (≈450 MB of it the base64 staging) |
| `loadPackage(["numpy"])` | 522 ms, numpy 2.2.5, `arange(10).sum() == 45.0` |
| `import js` sees | `read readbuffer load __files __host WebAssembly` = True; `process Deno Bun require fetch` = False |
| **interrupt**: `ctx.eval("pyodide.runPython('while True: pass')", timeout_sec=0.3)` | **`JSTimeoutException` after 300 ms; `runPython('1+1')` afterwards → 2** (V8 `TerminateExecution` unwinds through wasm and Pyodide recovers) |
| OOM: append 50 MB numpy arrays until failure, `set_hard_memory_limit(1.5 GB)` | numpy `MemoryError` after 779 ms; **host alive, isolate alive**; `was_hard_memory_limit_reached() == False`; **RSS 4,560 MB after** — wasm linear memory grew to its 4 GB maximum and V8's heap limit does not count it |
| second isolate (`MiniRacer()` #2 with its own Pyodide) | 3,070 ms, +300 MB; isolates are independent V8 heaps on their own threads |

`[EXECUTED]` `wrap_py_function`'s own docstring: a Python function "should be async" and "is rendered on the JavaScript side as an async function (i.e., a function which returns a Promise)". Emscripten's filesystem ops cannot await, and mini_racer offers no way to share a buffer Python could fill while the JS thread blocks in `Atomics.wait`. `[INFERRED]` The only route to a filesystem bridge under mini_racer is a **Python-level** bridge inside the guest (the same `open`/`os` patch as finding 3) that calls an async JS host function and blocks on it with Pyodide's `run_sync`, which needs JSPI and a call stack entered through `runPythonAsync`/`callPromising` (`[FETCHED 2026-10-15]` https://pyodide.org/en/stable/usage/api/python-api/ffi.html: "Only works if JS Promise integration is enabled in the runtime … Experimental"). The engine has JSPI; whether Pyodide 0.28.3's build enables it in a bare realm was not tried `[NOT VERIFIED: not attempted; a day's experiment]`.

#### 5c. The door: `import js` reaches the host Python interpreter until we delete it, and then it does not

`[EXECUTED]` `door_probe.py` run **inside the guest** under PythonMonkey (`out_pm_door.json`), before and after closing the door:

| from the guest | before | after `delete globalThis.{python,__host,read,readbuffer,load,os,print,printErr}` |
|---|---|---|
| `js.python.eval('__import__("os").getpid()')` | **56266 — the host pid** | `AttributeError: python` |
| `js.python.eval('open("/etc/hosts").read(20)')` | **`'##\n# Host Database\n#'` — the host filesystem** | `AttributeError` |
| `js.python.exec('import sys; sys.modules["vfs"]')` | **ok — the host's vfs module, with its storage and every Authority** | `AttributeError` |
| `js.__host.readText("/pyodide/package.json")`, `js.read(...)` | the artifact table | `AttributeError` |
| `js.os.system("sh", ["-c", "head -c4 /dev/urandom …"])` | the entropy shim (host bytes, no shell) | `AttributeError` |
| `js.eval("1+1")`, `js.WebAssembly` | 2, present | still present (harmless in a bare realm) |

PythonMonkey installs a `python` global in every realm (its purpose is two-way calling); Pyodide's `js` module is the whole global object. **Under node, S10 found `process.binding`; under PythonMonkey the door is the host interpreter itself.** Each global was deletable (`delete` returned true, `typeof` undefined afterwards) and the guest then got `AttributeError`. `[INFERRED]` The wall is therefore a *list we maintain*: every host reference handed into the realm — the stdout callbacks, the bridge function, the file table — must be unreachable from `globalThis` after loading (closure-captured, then deleted), and a PythonMonkey release that adds a global adds a hole. That is a weaker wall than Deno's permission check or a kernel's Landlock, and the memo must say so.

#### 5d. Interrupt, memory and concurrency in-process: the three costs PythonMonkey cannot pay

`[EXECUTED]` `--mode interrupt` (`out_pm_interrupt.txt`): `py.setInterruptBuffer(Int32Array over a Python bytearray)`, a Python `threading.Timer` sets `buf[0] = 2` after 300 ms, then `py.runPython("while True: pass")`. The timer thread **never ran**; the process spun at 100 % of a core (1:22 CPU in 1:27 wall) until killed. SpiderMonkey executes on the calling Python thread with the GIL held; no other Python thread, no JS timer, no signal handler written in Python gets a turn. A web server that embeds this and runs a guest on a request thread stalls that thread's interpreter for the guest's lifetime. `[EXECUTED]` `--mode oom` (`out_pm_oom.json`): numpy raised `_ArrayMemoryError: Unable to allocate 47.7 MiB` after 1,253 ms, Python stayed alive (`1+1 → 2`), **RSS 3,872 MB and it stays there** — a wasm `Memory` never shrinks, and Pyodide's `MAXIMUM_MEMORY` is a 4 GB build-time constant (`pyodide.asm.js`: `new WebAssembly.Memory({initial: INITIAL_MEMORY/65536, maximum: 65536})` `[READ]`). PythonMonkey exposes no per-realm memory cap. `[EXECUTED]` One realm per process: PythonMonkey has a single global context, and two Pyodide instances in it share `globalThis` (5a).

`[INFERRED]` Therefore in-process Pyodide is only honest as **a subprocess pool**: one worker process per session (or per run), `RLIMIT_AS`/a cgroup or a watchdog on RSS for the memory budget, `SIGKILL` for the time budget, and the process boundary as the second wall behind the deleted globals. That is the same topology as the Deno sidecar (study 11 fork F4) with the JavaScript runtime now `pip install`ed instead of downloaded — which was the point of the exercise.

### 6. Pyodide's shell-mode loader is real but untended: three things a bare realm needs that node and the browser never ask for (EXECUTED, READ)

`[EXECUTED]` The first run died in `finalizeBootstrap → rawRun` with `RuntimeError: memory access out of bounds` under **both** engines, and the control — Pyodide's shell path under node with `process` hidden and node's own `fs` behind `read`/`readbuffer` (`node_shell_mode.mjs`) — died identically. So the path was broken on its own. Cause, `[READ]` `pyodide.asm.js`: Emscripten's `initRandomFill` checks `ENVIRONMENT_IS_NODE`, then `ENVIRONMENT_IS_SHELL` — and in shell mode it **shells out**: `os.system("sh", ["-c", "head -c N /dev/urandom | base64 --wrap=0"])`, a d8 extension, before ever considering `crypto.getRandomValues`. With no `os`, the `getentropy` import throws a JS error into a wasm frame, Python's hash-seed/`random` bootstrap corrupts, and the next thing is the OOB. The fix in the shim: a `globalThis.os.system` that parses `N` and returns base64 of N host-supplied bytes — no shell, no `sh`. With it, the node control loaded Pyodide and numpy in 907 ms, and so did both engines.

`[EXECUTED]` Two more. (a) `pyodide.asm.js` evaluates, at module level and unguarded, `new Int32Array(new WebAssembly.Memory({shared: true, initial: 1, maximum: 1}).buffer)` for a `syncSleep` helper (`Atomics.wait` on `EAGAIN`); SpiderMonkey under PythonMonkey has shared memory disabled → `LinkError: shared memory is disabled` at load. The copy in `experiments/s11/untrusted/pyodide-pm/` wraps that one expression in a `try` and makes `syncSleep` return false without it; nothing else was changed, and the job ran. V8 under mini_racer has `SharedArrayBuffer` and needed no patch. (b) `loadPackage` uses `btoa` (absent in both realms; polyfilled) and, under PythonMonkey, a single `loadPackage(["numpy","pandas","matplotlib"])` **never returns** while pairs and one-at-a-time calls do (`out_pm_version_triple.log` hung at 658 MB, killed) — PythonMonkey's promise/event-loop integration stalls on Pyodide's parallel wheel loads; sequential loads are the workaround and the cost is nil.

`[INFERRED]` None of this is hard, all of it is ours to carry: a shell-mode host object (~120 lines of JS, written), one guarded line in a vendored 1 MB file per Pyodide release, and a loader rule. The d8 path is in Pyodide's source but not in its CI matrix `[NOT VERIFIED: the pyodide checkout's CI config was not read for a d8 job]`.

### 7. Candidate B: a static WASI CPython with the stack linked in — not attempted, and the estimate (READ, FETCHED, INFERRED)

Toolchain here `[EXECUTED]`: no wasi-sdk, no `wasm-ld`, no `emcc`; `cargo` 1.97 with `wasm32-wasip1`; a wasi-sdk tarball could be unpacked into the scratchpad without a system change, but that is the smallest step.

What exists, read and fetched (2026-10-15):

- `[FETCHED]` dicej's `wasi-wheels` v0.0.2 (2025-10-02; studied in S10, no licence, author disowns it): numpy, pandas, pydantic-core, regex, yaml and nine more cross-compiled with wasi-sdk 27 against a forked CPython, `NPY_BLAS_ORDER=` empty (no BLAS), `-DNPY_NO_SIGNAL`, **linked only at build time by componentize-py's shared-everything linker** — the `.so` files die with `dlopen not implemented` in a plain `python.wasm` (S10 executed that).
- `[FETCHED]` A 2026-09-26 PR, `seanchatmangpt/dspy-wasm#2` "Run all of DSPy in WebAssembly with every dependency compiled to wasm32-wasip2": builds wasi-sdk 33, CPython 3.14.0 `-fPIC` for wasip2, OpenSSL 3.5.4, zlib, libyaml; cross-compiles **numpy (meson, lapack-lite)**, pydantic-core, orjson, tiktoken, tokenizers (PyO3), regex, pyyaml, sqlalchemy, aiohttp (C/Cython); notes "throws in `-fexceptions` translation units resolve to a weak report-and-terminate archive, which is C++'s contract when exceptions are unavailable". No pandas, scipy, matplotlib, Pillow. The vehicle is again componentize-py 0.25.1 (CPython 3.14), i.e. a wasm *component*.
- `[FETCHED]` Brett Cannon's plan to "try to build NumPy and pandas into a python.wasm binary" is a plan (https://opensource.snarky.ca/Talks/2024/Plumber's+Summit); the CPython WASI page lists wasip3 as blocked on WASI 0.3 and says p2 was skipped (https://opensource.snarky.ca/Python/WASI/Plans). `[READ]` `cpython:configure.ac:1352-1363` — `--enable-wasm-dynamic-linking` applies to Emscripten and WASI but wasi-libc has no `dlopen`; `:2482-2489` a `wasm32-wasi-threads` target behind `-pthread` and `--import-memory`, no prebuilt threaded CPython found.
- No search hit, in any form, for scipy's Fortran (Pyodide's recipe uses an Emscripten-targeted flang; there is no WASI flang story in evidence) or for matplotlib's freetype/libpng/qhull/Agg on wasm32-wasi. `[NOT VERIFIED: absence of evidence after four searches; a private build may exist]`.

`[INFERRED]` The estimate, plainly. A **numpy-only** static link is feasible on the componentize-py path: 1–3 weeks for someone who has not done it (wasi-sdk, a `-fPIC` CPython, meson cross file, lapack-lite, the component link, and then a `wasi:filesystem` host in wasmtime-py instead of study 04's preview1 shim, since the output is a component). Adding **pandas** (Cython) is another week on dicej's evidence. **scipy** needs a Fortran compiler for wasm32-wasi that nobody ships, plus OpenBLAS or a reference BLAS built for it: a quarter at least. **matplotlib** needs freetype, libpng, qhull and a C++ build with exceptions emulated: weeks, with the C++-exceptions caveat the DSPy PR hit. **Pillow**, **lxml**, **PyYAML** (libyaml), **pydantic-core** (PyO3; done by both prior efforts): days each. Threads: none (wasi-threads CPython unbuilt; numpy/scipy would be single-threaded anyway); BLAS: none (lapack-lite); `dlopen`: none, so the whole set is one binary, rebuilt whenever any package changes, and `pip install` of a C extension by a host is impossible by construction. Total for the named set: **months, by us, and then maintained by us at every numpy/scipy/matplotlib release** — the exact thing Pyodide's team does with a bigger team. This is the months-scale build pipeline the brief asked to be called by its name. I did not spend two hours on it because the two-hour version (numpy alone, without the component linker) is the one S10 already proved cannot load.

### 8. Candidate D, one paragraph each (FETCHED, READ, INFERRED)

- **Pyodide under Node with `--permission`.** Node *is* pip-installable: `nodejs-wheel` / `nodejs-wheel-binaries` (unofficial, Linux x86_64/aarch64 glibc and musl, macOS, Windows) and `nodejs-bin` (`[FETCHED 2026-10-15]` https://pypi.org/project/nodejs-wheel/, https://pypi.org/project/nodejs-bin/), so "pip can't install node" is false. The fact that rules it to the back: the permission model's 2026 record — CVE-2026-58043 (High: path matching over-grants filesystem access across prefix boundaries; Red Hat's mitigation is "do not use `--permission`") and CVE-2026-58039 — and its documented gaps, "does not inherit to a worker thread" and "existing file descriptors … bypass the Permission Model" (`[FETCHED]` https://access.redhat.com/security/cve/CVE-2026-58043, https://nodejs.org/api/permissions.html). S10's VFSFS runs in a Worker; the model does not follow it there. Node is a fine *transport* for Pyodide (the S10 shape, 1 s, no patches) once the wall is the OS sandbox of candidate C around the node process — then it is candidate C with a JavaScript runtime in the middle.
- **Bun.** `[FETCHED 2026-10-15]` No permission or sandbox model (https://www.safeguard.sh/resources/blog/nodejs-deno-bun-security-model-comparison, secondary; Bun's docs list none). Out as a wall; same status as node as a transport.
- **A `rusty_v8`/`deno_core` embedding in `crates/vfs-core`.** `[EXECUTED]` `gh release view denoland/rusty_v8` v152.2.0 (2026-08-20): `librusty_v8_release_{aarch64-apple-darwin,x86_64-unknown-linux-gnu}.a.gz` 37–38 MB each (debug 78–100 MB), one per target, downloaded by the build script. Cost to own: a 40 MB static V8 per target in our wheel build, Deno's maintenance cadence for `rusty_v8` after Cloudflare ("rusty_v8 remains supported" per the acquisition coverage `[FETCHED]` https://thenewstack.io/cloudflare-acquires-deno-ryan-dahl/), the shell-mode host object of finding 6 rewritten in Rust, and the same door-closing list. What it buys over `mini_racer`: synchronous host functions (so the Emscripten bridge works, as under PythonMonkey) and our own isolate-per-session, interrupt and memory accounting. It is the right *eventual* home if tier 0 earns traffic; it is not a v1 move.
- **wasmer with the Emscripten ABI.** `[EXECUTED]` wasmtime 49 refuses `pyodide.asm.wasm` outright ("legacy_exceptions feature required for `try` instruction"); Pyodide 0.28 is built with Emscripten exception handling and JSPI-era features. `[INFERRED]` wasmer's Emscripten support targets old Emscripten ABIs and no JS; Pyodide's runtime *is* 1 MB of JavaScript. Out.
- **Hosted sandboxes (E2B, Modal, Daytona).** `[INFERRED from S10 finding 7]` A native-CPython tier someone else operates, reachable only over the network, with a per-file API or — once they can open a TCP connection to the host — the bridge of finding 3 or S10's 9P server. They are a backend for the same program ABI a host may select; they do not satisfy "runs in a web server with nothing to install", and they are not free.

### 9. Where the self-sandbox works: the Landlock / seccomp / Seatbelt support matrix (FETCHED, EXECUTED, INFERRED)

The rule: **seccomp-bpf** needs nothing (every Linux since 3.5; `PR_SET_NO_NEW_PRIVS` makes it unprivileged) but is blind to paths; **Landlock** needs kernel ≥ 5.13 and a runtime that does not filter the three syscalls; **Seatbelt** needs macOS; the kernel a *container* sees is the host's (or the microVM's), never the image's.

| host | what runs your process | Landlock | seccomp | source, date |
|---|---|---|---|---|
| plain Linux box / VM, kernel ≥ 5.13 | your process | yes | yes | kernel docs `[FETCHED]` |
| Docker/containerd default profile, non-root, cap-drop ALL | shared host kernel | **yes, executed (ABI 8)** | **yes, executed** | finding 2 |
| Fly.io Machines | Firecracker microVM, own kernel, root available | yes if the guest kernel ≥ 5.13 `[NOT VERIFIED: Fly does not publish the guest kernel version]` | yes | https://community.fly.io/t/why-are-fly-machines-running-as-firecracker-microvms-configured-with-privileged-true/26380 `[FETCHED 2026-10-15]`: "full virtual machines each running an independent Linux kernel, in which you get root" |
| Google Cloud Run **gen1** | **gVisor** (user-space kernel) | **no** — `landlock_*` are not in gVisor's syscall table (unlisted → `ENOSYS`); `seccomp` is "Partial Support: only SECCOMP_SET_MODE_FILTER with flags 0 or TSYNC" — which is exactly what we use | partial, usable | https://gvisor.dev/docs/user_guide/compatibility/linux/amd64/ `[FETCHED 2026-10-15]`; https://docs.cloud.google.com/run/docs/about-execution-environments: "The first generation execution environment is based on gVisor" |
| Google Cloud Run **gen2** (the only option for jobs; selectable for services, ≥ 512 MiB) | microVM, "full Linux compatibility, including support for all system calls, namespaces, and cgroups" | yes if its kernel ≥ 5.13 `[NOT VERIFIED: version unpublished]` | yes | same page `[FETCHED 2026-10-15]` |
| AWS Lambda | Firecracker microVM; a July 2025 in-function `uname -a` reported **`5.10.238-254.954.amzn2`** | **no (5.10 < 5.13)** `[INFERRED from the reported kernel]` | yes (Lambda's own sandbox is "cgroups, namespaces, seccomp" per the AWS logical-separation whitepaper) | https://builder.aws.com/content/30KEyOYDW110zofDWMz3SS4XhKq/aws-lambda-deep-dive-to-the-operating-system-level (2025-07-24, secondary) `[FETCHED]`; https://docs.aws.amazon.com/whitepapers/latest/logical-separation/serverless-and-containers.html |
| AWS Fargate | Firecracker microVM, platform 1.4 | `[NOT VERIFIED: guest kernel version not published]` | yes | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/platform_versions.html `[FETCHED]` |
| Heroku dynos | "OS containerization with additional custom hardening"; ephemeral filesystem; no kernel, user or seccomp statement | `[NOT VERIFIED: host kernel unpublished]` | likely `[INFERRED]` | https://devcenter.heroku.com/articles/dyno-isolation (last updated 2024-12-03) `[FETCHED]` |
| Railway, Render | containers; neither publishes runtime, kernel or seccomp facts | `[NOT VERIFIED]` | `[NOT VERIFIED]` | two searches, no primary source |
| Azure Container Apps | Kubernetes-hosted containers | `[NOT VERIFIED]` | `[NOT VERIFIED]` | no primary source found |
| Vercel Fluid / Netlify functions | Vercel: "isolation boundary" per function instance, microVMs for the traditional model, no kernel facts | `[NOT VERIFIED]` | `[NOT VERIFIED]` | https://vercel.com/docs/fluid-compute `[FETCHED]` |
| macOS laptop | your process | Seatbelt, **executed** | — | finding 3 |
| Windows | your process | **no Landlock, no seccomp, no Seatbelt**; the shape is a child with a restricted token (`CreateRestrictedToken`) inside a Job object (active-process limit 1, `JOB_OBJECT_SECURITY_*`) and, on Windows 10+, an AppContainer/LowBox token — Chromium's sandbox design, callable from `ctypes` | — | https://chromium.googlesource.com/chromium/+/trunk/sandbox/win/src/restricted_token_utils.cc, https://learn.microsoft.com/en-us/windows/desktop/api/WinNT/ns-winnt-jobobject_security_limit_information `[FETCHED 2026-10-15]`; **`[NOT VERIFIED: no Windows machine; nothing executed]`** |

`[INFERRED]` The degradation ladder for candidate C, to be stated per run as a fact the agent can read: **full** (Landlock + seccomp, or Seatbelt): the guest reaches the interpreter tree read-only, one scratch dir, and vfs; **network-and-exec only** (seccomp without Landlock: Lambda, gVisor, pre-5.13 kernels): the guest can *read* whatever the web server's uid can read — the host's own container contents, which on Lambda is a read-only image plus `/tmp` — and cannot connect, spawn or trace; **none** (Windows until the token/job slice lands): refuse `python3` unless the host sets `python.sandbox = none` knowingly. In-process Pyodide (tier 0) does not depend on any of this and is the lane for a host that will not accept "network-and-exec only".

### 10. Maturity facts for the two embedded engines (EXECUTED, FETCHED)

| | PythonMonkey (Distributive) | py_mini_racer (bpcreech) |
|---|---|---|
| engine | SpiderMonkey 136 (`libmozjs-136a1`) | V8 14.4.258 |
| licence | MIT (PyPI; GitHub API `NOASSERTION`) | ISC |
| wheel | 14.1 MB macOS arm64, 21.4 MB manylinux x86_64; cp38–cp314 | 17.7–21.2 MB, `py3-none` per platform; ≥ 3.10 |
| repo | 972 stars, pushed 2026-10-15, 56 open issues, v1.3.2 2026-06-16 | 218 stars, pushed 2026-02-02, 11 open issues, 0.14.1 |
| **Python 3.13** | **broken for promises**: `RuntimeError: PythonMonkey cannot find a running Python event-loop to make asynchronous calls` inside `asyncio.run` — executed on 3.13.11; fine on 3.12.12; upstream #469 (open since 2025-01-22) and #507 (2026-05-28) | works on 3.13 |
| sync Python ← JS | **yes** (the bridge) | no (Promise only) |
| per-session isolation | one realm per process | one isolate per `MiniRacer()`, own thread |
| interrupt | none in-process (GIL) | `timeout_sec`, executed |
| memory cap | none | V8 heap only; wasm memory uncounted (executed) |
| JSPI | no (`WebAssembly.Suspending` undefined) | yes |
| process exit | needs `os._exit` (event-loop thread) | needs `ctx.close()` or the process hangs at exit (executed, twice) |

`[INFERRED]` Neither is a dependency to add to `vfs-py` by default: both are optional extras (`vfs-py[pyodide]`), and PythonMonkey's 3.13 bug alone disqualifies it from a default install of a library whose own CI gate is 3.13. The 3.13 bug is in the promise path (loading); the synchronous bridge path and `runPython` are unaffected `[NOT VERIFIED: a loader that avoids awaiting (polling the promise through a sync JS callback) was not tried]`.

---

## What this means for vfs

### A. The decision table

| | **(C) self-sandboxed native CPython + Python-level bridge** | **(A1) Pyodide in-process, PythonMonkey** | (A2) Pyodide in-process, mini_racer | (B) static WASI CPython | (D1) Pyodide under pip-installed Node | S10's Deno sidecar (reference) |
|---|---|---|---|---|---|---|
| numpy, pandas, scipy, matplotlib | all, pip's latest (executed: numpy 2.5.4 / pandas 3.0.6 / mpl 3.11.2 Linux; 2.4.2 / 3.0.5 / 3.11.1 macOS) | Pyodide 0.28.3's: numpy 2.2.5, pandas 2.3.1, matplotlib 3.8.4 executed; scipy 1.14.1 loadable (S10, +450 MB) | numpy executed; the rest loadable | numpy feasible, pandas plausible, scipy/matplotlib never built | all four (S10) | all four (S10) |
| the eight utilities | all | all (S10; openpyxl, python-docx as pure wheels) | same | pydantic-core, PyYAML, lxml-class: weeks each | all | all |
| runs in a web server, unprivileged: Linux PaaS | **yes** (executed as uid 1000, cap-drop ALL) | **yes** | yes | yes (wasmtime-py) | yes | no (Deno ending) |
| … Cloud Run gen1 (gVisor) | seccomp-only mode | yes | yes | yes | yes | — |
| … Lambda | seccomp-only mode (5.10) | yes if the 512 MB–10 GB memory fits | yes | yes | yes | — |
| … macOS laptop | **yes** (executed) | yes | yes | yes | yes | — |
| … Windows | `[NOT VERIFIED]` token+job child | yes `[INFERRED: pure wheels + a Windows PythonMonkey wheel]` | yes | yes | yes | — |
| isolation / what a hostile script reaches | kernel-enforced: the interpreter tree RO, one scratch dir, vfs; no net, no exec, no ptrace; threads yes | **a deleted-globals list**: with the door open, the host interpreter (executed); closed, a bare realm + wasm; second wall = the worker process | same door minus `python`; isolate per session | wasm sandbox, preview1 shim only | Node permission model (CVE-2026-58043) or an OS sandbox around node | Deno permissions |
| start | **0.6–1.0 s** incl. 0.5 s pre-import; 7 ms bare | **1.15 s + 0.2–1.2 s packages**; 0.17 ms per `runPython` warm | 2.6 s (base64 staging inflates it) | 6 ms after a Wizer snapshot (S05) | ~1 s | ~1 s |
| memory per session | **105–132 MB** | **489 MB base, 947 MB after the job**, 1 GB+ with scipy; balloons to 3.9 GB on an OOM and stays | 738 MB (staging) / +300 MB per isolate | ~415 MB (S05) | 505 MB (S10) | 505 MB |
| concurrency | one process per run; the OS does the rest | one realm per process → **subprocess pool**; GIL held while running | isolates on threads in one process | one per process (trap global, S04) | Workers | Workers |
| interrupt | `SIGKILL`/`alarm` from the host | **none in-process**; kill the worker | **300 ms, executed** | epoch | interrupt buffer (S10: 305 ms) | same |
| memory budget | `RLIMIT_AS`, cgroup, or the host watches RSS | process-level only | process-level (V8 limit misses wasm) | `Store.set_limits` | `--max-old-space-size` misses wasm | same |
| bridge shape | Python-level: `open`/`io.open`/`os.*` over one inherited fd, length-prefixed frames, whole-file staging; 9 calls / 69 SQL for the job | **Emscripten VFSFS → sync Python call**; 20 calls / 106 SQL | Python-level inside the guest over JSPI `run_sync` `[NOT VERIFIED]` | preview1 shim (S04) | VFSFS + SAB relay (S10) | same |
| C-level file access on vfs paths | **denied by the kernel** (stage to scratch) | works through VFSFS (sqlite3, fonts) | — | works through the shim | works | works |
| artifact and where it ships | python-build-standalone + a uv-pinned package set, fetched by hash into `$VFS_HOME` (ADR 086 pin 1 unchanged); ~430 MB on disk | 12 MB core + 28–36 MB of wheels fetched by hash; engine wheel 14–21 MB via `pip install vfs-py[pyodide]` | same + 18 MB | a 40+ MB `.wasm` per release, built by us | nodejs-wheel ~50 MB + Pyodide | Deno binary + Pyodide |
| vfs must build and maintain | the guest bridge (250 lines), the host (150), the Linux/macOS/Windows self-sandbox (200), the degradation report | the shell-mode host object (120 lines JS), one guarded line per Pyodide release, the door-closing list, a worker pool | the above minus the sync bridge, plus a JSPI bridge | a months-scale toolchain, forever | a node launcher plus an OS sandbox anyway | — |
| licence | PSF + each package | MPL-2.0 (Pyodide) + MIT (PythonMonkey) | + ISC | PSF | + MIT (Node) | MIT (Deno) |
| maturity | kernels and libc; Landlock in every major distro kernel since 2021 | Pyodide mature; PythonMonkey 1.3 with an open 3.13 bug and a parallel-load stall | mini_racer stable, small | CPython WASI tier 2; package story absent | Node stable; permission model with 2026 CVEs | ending 2027 |

### B. The tiered recommendation and the triggers

Both tiers are programs of study 03's ABI (argv, stdin, env, the filesystem capability in; stdout, stderr, exit code out), named `python3`, with the runtime a host choice visible in `python3 --version`.

**Tier 1 — the floor, on by default: self-sandboxed native CPython with the Python-level bridge.** Everything ADR 086 pins 1, 4, 5, 7–10 already say, with pins 2, 3 and 6 replaced:

- *Pin 2 →* The sidecar sandboxes **itself**, needing no privilege: Landlock (filesystem, deny-default, the interpreter tree read-only, one scratch dir read-write) plus seccomp-bpf (`socket`, `connect`, `execve`, `execveat`, `ptrace` → `EPERM`; `PR_SET_NO_NEW_PRIVS`) on Linux; `sandbox_init` with the deny-default profile of finding 3 on macOS; a restricted-token child in a Job object on Windows as a later slice. bubblewrap, containers and microVMs become *optional outer walls* a host may add, never prerequisites. Each run reports its wall as a fact: `full`, `network-and-exec only` (no Landlock: kernel < 5.13 or gVisor), or `none` (refused unless the host opts in).
- *Pin 3 →* The transport is the Python-level bridge over one inherited fd (socketpair on POSIX; a named pipe on Windows), the whole-file staging of pin 4 applied at `open`/`close`, with the coverage list of finding 4 as the contract and C-level access on a vfs path refused by the kernel, loudly. The 9P server stays as the second form for hosts that *can* mount (ADR 086's consequences: "vfs becomes a file server any sandbox can mount") but is no longer on the critical path.
- *Pin 6 →* No cache to tame; the bridge counts verbs (`VERB_CALL_BUDGET` stays in pin 7).

**Tier 0 — the hermetic lane, opt-in: Pyodide in-process under PythonMonkey, in a worker-process pool.** Installed by `pip install vfs-py[pyodide]`; the 12 MB core and the pinned wheel set fetched by hash like the native tier's packages. One worker process per session (memory and interrupt live at the process boundary), VFSFS as the adapter with the synchronous bridge, the door closed by the deletion list after load, package loads sequential, `python3 --version` reporting "Pyodide 0.28.3 (CPython 3.13.2, emscripten; no threads; N packages)". Honest limits: 0.5–1 GB per worker, ~1 s cold, no threads, Pyodide's set, the deleted-globals wall, PythonMonkey's 3.13 bug until fixed upstream (or a non-awaiting loader).

**The trigger between tiers is a host policy value, never automatic:** `python.runtime = native | pyodide`. Native is the default wherever the self-sandbox reports `full` or the host accepts `network-and-exec only`; Pyodide is what a host chooses when it will not run a native interpreter at all (a shared multi-tenant web process that wants the wasm wall, a Windows host before the token slice, a host whose policy forbids `execve` of anything). The refusal names the other tier, as study 11 fork F3 chose. There is no `--native` flag for the agent.

**What stays rejected:** WASI CPython as the scientific tier (finding 7); Pyodide under bare node or Bun as a wall (finding 8); a `rusty_v8` embedding at v1 (the eventual home for tier 0 if it earns traffic); automatic fallback on `ImportError`.

### C. What works where (the exact matrix)

| host | tier 1 native, wall | tier 0 Pyodide in-process | scipy / threads / pip's long tail |
|---|---|---|---|
| Linux PaaS container, kernel ≥ 5.13, default seccomp (Fly, gen2 Cloud Run, most Kubernetes, Docker) | **full** (executed) | yes | native yes |
| Cloud Run gen1 (gVisor) | network-and-exec only | yes | native yes |
| AWS Lambda (5.10 kernel reported) | network-and-exec only; `/tmp` is the scratch dir; 512 MB–10 GB | yes if memory allows | native yes, single run per invocation |
| plain Linux box / VM | full | yes | yes |
| macOS laptop | **full** (Seatbelt, executed) | yes (3.12 today; 3.13 pending the upstream bug) | yes |
| Windows | none until the token/job slice `[NOT VERIFIED]` → tier 0 is the lane | yes `[INFERRED]` | via tier 0 only |
| any host, hostile multi-tenant | add the host's outer wall (container/microVM) around tier 1, or use tier 0's process pool | yes | — |

### D. The bridge rules carried forward (each executed here or in S10)

1. **Whole-file staging at the Python level**: `open` for read is one `read`; `close` of a dirty buffer is one `write`; `stat`/`ls`/`mkdir`/`delete(cascade=False)`/`move` one-to-one; errno from the result kind. The same table as S10 rule 2 and ADR 086 pin 4, one layer up.
2. **The bridge fd is taken before the sandbox; the sandbox then forbids any new socket.** Order is the argument.
3. **Authority is bound in the host; the guest sends paths.** Unchanged (S10 rule 3, ADR 086 pin 5).
4. **Text versus bytes by extension at write time**, never a sniff alone (S10 rule 4; executed again: `.png` → `image/png`, `.csv` → text).
5. **C-level access to a vfs path is refused by the kernel, and the refusal is reported** as `unsupported.native_file_access` naming the scratch-and-copy pattern.
6. **The scratch dir is the only writable host path**, per run, deleted after; `MPLCONFIGDIR`, `TMPDIR`, `HOME` point at it.
7. **Pre-import before the sandbox** (so `.so` files are mapped; Landlock then needs only read rights on the tree), and the warm pool holds pre-imported interpreters.
8. **Tier 0: sequential package loads; the deletion list runs after load and before the first guest statement; one worker process per session.**

---

## Forks for the ADRs

**F1. Which Python is the floor at v1?** Options: (a) self-sandboxed native CPython with the Python-level bridge (tier 1); (b) Pyodide in-process under PythonMonkey; (c) ADR 086 as written (bubblewrap/Seatbelt + 9P). *Lean: (a).* It is the only candidate that runs pip's whole ecosystem at 112 MB, was executed unprivileged on Linux and macOS, and whose wall is the kernel's, not ours. (c) cannot run in a PaaS process; (b) costs 0.5–1 GB and a maintained door list, and is the right second lane, not the floor.

**F2. The sandbox mechanism of ADR 086 pin 2.** Options: (a) self-applied Landlock+seccomp / Seatbelt, with bubblewrap, containers and microVMs as optional outer walls; (b) bubblewrap required on Linux; (c) containers required. *Lean: (a).* Executed as uid 1000 with no capabilities; (b) needs user namespaces a PaaS may not grant; (c) is what "anywhere" forbids.

**F3. The transport of ADR 086 pin 3.** Options: (a) the Python-level bridge over an inherited fd as the first form, 9P as the second for hosts that can mount; (b) 9P first, bridge as the fallback (ADR 086 today); (c) bridge only. *Lean: (a).* 9 calls / 69 SQL against 536 `stat`s; no mount, no cache, no staleness; and 9P stays the door for microVMs and hosted sandboxes.

**F4. What the bridge does about C-level access to vfs paths.** Options: (a) refuse loudly (kernel denial + a classified error naming the scratch pattern); (b) extend the bridge to `os.open`/`os.read`/`os.write` fds; (c) a FUSE/9P mount when available. *Lean: (a) at v1, (b) when a profile shows a program class that needs it* (sqlite over vfs rows is the first candidate, and S10's clunk-time staging shows the shape), (c) only on hosts that can mount.

**F5. Degradation without Landlock (Lambda, gVisor, kernels < 5.13).** Options: (a) run with seccomp only and report `network-and-exec only` as a fact; (b) refuse; (c) refuse unless the host opts in. *Lean: (c).* The guest can read what the web server reads; that is a host's call to make knowingly, not a silent default and not a blanket refusal that strands Lambda.

**F6. Tier 0's engine.** Options: (a) PythonMonkey (sync bridge, realm per process); (b) py_mini_racer (isolates, interrupt, no sync bridge → JSPI); (c) our own `rusty_v8` embedding; (d) pip-installed Node as transport with the OS sandbox as the wall. *Lean: (a) at v1, (c) named as the future if tier 0 earns traffic.* (a) ran the job today; (b) needs an unproven JSPI bridge; (c) is 40 MB of V8 per target and the same shell-mode host object in Rust; (d) adds a runtime without adding a wall.

**F7. Tier 0 topology.** Options: (a) in the web server process; (b) one worker process per session, a pool; (c) one per run. *Lean: (b).* In-process means no interrupt, no memory cap, a 3.9 GB balloon after one OOM, and the GIL held for the guest's lifetime (executed).

**F8. The door-closing list as a contract.** Options: (a) a tested list of globals deleted after load, pinned by a test that runs `door_probe.py`'s checks in CI against the vendored Pyodide and PythonMonkey versions; (b) a patched Pyodide build without `js`; (c) trust the engine. *Lean: (a).* The escape was executed; the closure was executed; (b) gives up `js` and forks Pyodide; (c) is what S10 found under node.

**F9. The Pyodide vendoring rule.** Options: (a) vendor the npm core with the one guarded line and the shell-mode host object, upstream both; (b) unpatched Pyodide under an engine with shared memory (mini_racer) only; (c) wait for upstream. *Lean: (a)*, with the patch offered upstream (guard the probe; prefer `crypto.getRandomValues` before `os.system` in shell mode).

**F10. The trigger.** Options: (a) host policy `python.runtime`, refusal names the other tier; (b) automatic by sandbox capability; (c) agent choice. *Lean: (a)*, as study 11 F3; (b) hides a security posture change behind a kernel version.

**F11. Does vfs invest in a WASI scientific build?** Options: (a) no; (b) numpy-only via componentize-py as a hermetic third lane; (c) the full stack. *Lean: (a).* (b) is weeks for a lane that serves numpy and nothing the question named; (c) is months, forever, and Pyodide already exists.

**F12. Windows.** Options: (a) tier 0 only until a restricted-token/Job-object child is built and executed; (b) WSL2 as ADR 086 says; (c) refuse. *Lean: (a)*, with (b) as the documented path for a laptop that has it. Nothing on Windows was executed here.

---

## Sources

- **Experiments (`experiments/s11/`):** `probe_mini_racer.py` → `out_probe_mini_racer.txt`; `probe_mini_racer_jspi.py` → `out_probe_mini_racer_jspi.txt`; `probe_pythonmonkey.py` → `out_probe_pythonmonkey.txt`; `probe_landlock_seccomp.py` → `out_probe_landlock_seccomp_docker.json`; `bridge_guest.py` + `bridge_host.py` → `out_bridge_linux_landlock.json` (Docker, uid 1000, cap-drop ALL, no-new-privileges, Landlock+seccomp), `out_bridge_macos_seatbelt.json` (Seatbelt); `pyodide_pm_shim.js` + `pyodide_pm_host.py` + `door_probe.py` → `out_pm_version.json`, `out_pm_version_pandas.json`, `out_pm_version_mpl.json`, `out_pm_version_triple.log` (hang), `out_pm_job_numpy.json`, **`out_pm_job.json`**, `out_pm_door.json`, `out_pm_two.json`, `out_pm_interrupt.txt`, `out_pm_oom.json`; `pyodide_mini_racer.py` → `out_mini_racer.json`; `node_shell_mode.mjs` (the node control for Pyodide's shell path). `untrusted/pyodide-pm/` (git-ignored): the S10 npm copy with the guarded shared-memory probe. The s10 wheel cache and image were reused (`experiments/s10/pyodide_untrusted/`, `vfs-s10-sci:latest`).
- **Clones (read-only):** `pyodide` adc5b63 — `src/js/environments.ts:25-110`, `src/js/compat.ts:85-100,140-262`; the 0.28.3 distribution's `pyodide.asm.js` (`initRandomFill`, the `syncSleep` shared-memory probe, `callMain`, `ENVIRONMENT_IS_SHELL`), `pyodide.js` (`installStdlib`, `_createPyodideModule` guard); `sandbox-runtime` 9a277e5 — `src/sandbox/macos-sandbox-utils.ts` (SBPL shape); `cpython` fdec4df via study 11 (`configure.ac:1352-1363,2482-2489`).
- **vfs:** `context/decisions/086-*.md`; `context/specs/active/172-*/spec.md`; studies `04`, `05`, `11`; `src/vfs/base.py` verbs, `src/vfs/authority.py`.
- **Web (fetched 2026-10-15):** Cloudflare–Deno: https://thenewstack.io/cloudflare-acquires-deno-ryan-dahl/, https://linuxiac.com/?p=220895 (runtime development ends October 2027; Deno Deploy ~April 2027; rusty_v8 supported). gVisor syscall table: https://gvisor.dev/docs/user_guide/compatibility/linux/amd64/. Cloud Run generations: https://docs.cloud.google.com/run/docs/about-execution-environments. Lambda: https://builder.aws.com/content/30KEyOYDW110zofDWMz3SS4XhKq/aws-lambda-deep-dive-to-the-operating-system-level (2025-07-24, secondary), https://docs.aws.amazon.com/whitepapers/latest/logical-separation/serverless-and-containers.html, https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html. Fly: https://community.fly.io/t/why-are-fly-machines-running-as-firecracker-microvms-configured-with-privileged-true/26380, https://fly.io/learn/firecracker-vm.md. Heroku: https://devcenter.heroku.com/articles/dyno-isolation. Vercel: https://vercel.com/docs/fluid-compute. Fargate: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/platform_versions.html. Landlock: https://docs.kernel.org/userspace-api/landlock.html. Node permission model: https://access.redhat.com/security/cve/CVE-2026-58043, https://www.herodevs.com/vulnerability-directory/cve-2026-58039, https://nodejs.org/api/permissions.html. Node on PyPI: https://pypi.org/project/nodejs-wheel/, https://pypi.org/project/nodejs-bin/. Bun: https://www.safeguard.sh/resources/blog/nodejs-deno-bun-security-model-comparison (secondary). Pyodide `run_sync`: https://pyodide.org/en/stable/usage/api/python-api/ffi.html. WASI numpy prior art: https://github.com/seanchatmangpt/dspy-wasm/pull/2 (2026-09-26), dicej/wasi-wheels releases (v0.0.2 2025-10-02; no licence, studied in S10), https://opensource.snarky.ca/Talks/2024/Plumber's+Summit, https://opensource.snarky.ca/Python/WASI/Plans. rusty_v8 release assets via `gh release view denoland/rusty_v8` (v152.2.0, 2026-08-20). Windows sandbox shape: https://chromium.googlesource.com/chromium/+/trunk/sandbox/win/src/restricted_token_utils.cc, https://learn.microsoft.com/en-us/windows/desktop/api/WinNT/ns-winnt-jobobject_security_limit_information. PythonMonkey: https://pypi.org/project/pythonmonkey/ (1.3.2, MIT), issues #469 and #507 via the GitHub API; py_mini_racer: https://pypi.org/project/mini-racer/ (0.14.1, ISC).
