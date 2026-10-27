# S10 — Python in vfs: which runtime can run numpy, pandas, scipy and matplotlib over vfs rows, and what each costs

- **Date:** 2026-10-15
- **Researcher:** S10 (vfs agent-shell study)
- **Question (Clay, 2026-10-15):** "Is it WASI Python, is it Monty, is it another option? I want to be able to run things like numpy, pandas, scipy, matplotlib and the common utilities as well from within vfs." The decisions that bind: agents run code as a program in the vfs shell; every file access resolves to vfs verbs with the caller's `Authority` (no host filesystem, no ambient authority); output is rows (a PNG is a media row, bytes plus mime, projected to an MCP image block, never base64 text); budgets enforceable; N concurrent sessions in one host; no network in the guest at v1.
- **Builds on:** study 05 (guest interpreters; the measurements there are not repeated) and study 04 (the preview1 shim over the live tree; its syscall table and staging rule are extended, not re-measured).
- **Clones read (shallow, read-only; see `refresh.log` and `licenses.log`, S10 wave):** `cpython-wasi-build` 7ce0aaf (MIT; release assets v3.14.7 executed), `langchain-sandbox` fac037c (MIT; archived upstream), `microsandbox` 0feec23 (Apache-2.0), `wasi-wheels` b28844f (dicej; **no licence** — read, then deleted per the brief; cited from its README and release metadata). Already-cloned: `just-bash` 9ab0e0d, `pyodide` adc5b63, `cpython` fdec4df, `plan9port` b6564bd9 (built in a scratch copy, read-only clone untouched), `linux` (fs/9p, net/9p, Documentation/filesystems/9p.rst), `sandbox-runtime` 9a277e5, `sandbox-sdk` a080a65, `monty` 2bb9f08a (via study 05).
- **Packages executed, never added to vfs:** `pyodide` 0.28.3 (npm, under node v22.14.0 and Deno 2.5.2), `wasmtime` 49.0.0 (`uv run --with`), Brett Cannon's `python-3.14.7-wasi_sdk-24.zip`, dicej's `numpy-wasi.tar.gz` (v0.0.2), a native `numpy-2.5.4` macOS wheel, the Docker image `python:3.13-slim` plus pip (numpy 2.5.4, pandas 3.0.6, scipy 1.18.1, matplotlib 3.11.2, Pillow 12.3.0, PyYAML 6.0.3, openpyxl 3.1.5, python-docx 1.2.0, beautifulsoup4 4.15.0, python-dateutil 2.9.0, pydantic 2.14.1). Untrusted artifacts live under `experiments/s10/pyodide_untrusted/` (git-ignored) and the session scratchpad.
- **Evidence labels:** `[EXECUTED]` ran on this machine (scripts and raw outputs in `experiments/s10/`); `[READ]` read in the named checkout or document; `[FETCHED]` web, with URL and date; `[INFERRED]` my reasoning from the above; `[NOT VERIFIED: why]` could not be checked.
- **Machine:** Apple Silicon laptop, macOS 26.5, CPython 3.13 via `uv run`; Docker Desktop 29.7.2 (LinuxKit kernel 7.0.12). Wall-clock numbers are benchmark facts for this memo, not test assertions.

---

## Summary

**WASI CPython cannot meet the requirement today, and nothing short of a build project of Pyodide's size changes that.** I ran Brett Cannon's prebuilt CPython 3.14.7 for `wasm32-wasip1` under wasmtime. It imports the pure-Python standard library, but `_sqlite3`, `zlib`, `_bz2`, `_lzma`, `_ssl`, `_ctypes`, `mmap` and `multiprocessing` are absent, a thread cannot start ("can't start new thread"), and no C extension can be loaded at all: a native numpy wheel is refused for its file suffix, and the only WASI-targeted numpy build that exists (dicej's unlicensed, unmaintained `wasi-wheels` proof of concept) gets to the loader and dies with `ImportError: dlopen not implemented`. There is no `dlopen` in wasi-libc, no package index of WASI wheels, and no one building numpy, pandas, scipy or matplotlib for WASI. WASI CPython stays what study 05 found it to be: a fast, interruptible guest for stdlib-only scripts behind the preview1 shim.

**Two runtimes do meet it, and both were proven end to end over the live tree.** (1) **Pyodide** (CPython compiled with Emscripten, MPL-2.0) ships numpy 2.2.5, pandas 2.3.1, scipy 1.14.1, matplotlib 3.8.4 and every one of the eight "common utilities" (Pillow, PyYAML, beautifulsoup4, dateutil, pydantic, sqlite3, lxml built in; openpyxl and python-docx as pure-Python wheels) among 266 packages. I built an Emscripten filesystem (`VFSFS`) whose every `node_op`/`stream_op` blocks on a `SharedArrayBuffer` until a Python host has answered it with a vfs verb under an `Authority`: a pandas `read_csv` of a vfs row, a matplotlib `savefig` that landed as a bytes row with `mime_type image/png`, and a `to_csv` that landed as a text row, in 20 bridge calls, 20 verbs and 106 SQL statements. Cost: a JavaScript runtime as a sidecar, ~1 s cold start, 505 MB RSS for numpy+pandas+matplotlib (1 GB with scipy), no threads, and — the decisive isolation fact — under plain node `import js` hands the guest `process.env.HOME` and `process.binding`; under Deno with no permissions the same door answers `NotCapable` for env, file and process access. The sidecar must be Deno, not node. (2) **Native CPython in a Linux sandbox with vfs mounted through 9P.** I wrote a 9P2000 server over `VirtualFileSystem` (380 lines, whole-file staging, one Authority per connection) and mounted it with the Linux kernel's own v9fs client inside a Docker container: the same agent script ran unchanged on pip's numpy 2.5.4 / pandas 3.0.6 / matplotlib 3.11.2 in 2.4 s, the PNG landed as the same `image/png` bytes row, `rm` landed in the trash, `mv` was one `move`, and a sqlite3 database file round-tripped through clunk-time writes. This is the full ecosystem and the strongest isolation, at the cost of an OS-level sandbox (Linux servers natively; macOS laptops through Docker Desktop or a microVM) and a chatty kernel client (7–17 `stat`s per operation without caching; `cache=loose` cut a job from 536 stats to 17).

**Recommendation:** tier it, behind the one program ABI. Pyodide-under-Deno is the Python that ships with vfs and runs on every laptop and server; native CPython over 9P is the escalation a host enables when it has a sandbox, triggered by a package outside Pyodide's set, a need for threads or more than a gigabyte, or a long job. Monty is not needed on the critical path; WASI CPython keeps the stdlib-only program slot. Base64 appears exactly once, in the MCP `ImageContent` block minted at the wire.

---

## Findings

### 1. CPython-on-WASI: the stdlib minus its compressed and crypto halves, no threads, and no door for C extensions (EXECUTED, READ)

`[EXECUTED]` `experiments/s10/wasi_cpython_probe.py` → `out_wasi_probe_plain.txt`. Brett Cannon's `python-3.14.7-wasi_sdk-24.zip` (14.3 MB; unpacked 40 MB: `python.wasm` 30.5 MB plus `lib/python3.14`, an **empty** `lib-dynload/`) under wasmtime-py 49.0.0, with the unpacked directory preopened at `/usr/local` so `getpath` finds its landmarks (preopened at `/` with `-I`, the interpreter dies with "No module named 'encodings'" because `-I` ignores `PYTHONHOME`; the layout, not the shim, decides). Compile 0.11 s (cached), the whole 60-import probe 0.82 s, exit 0, `sys.platform == "wasi"`.

| group | result |
|---|---|
| pure stdlib: json csv re decimal dataclasses enum datetime zoneinfo tomllib tarfile zipfile io tempfile shutil glob argparse array struct math statistics fractions uuid asyncio pyexpat xml.etree | all import |
| C modules **absent**: `_sqlite3` (so `sqlite3`), `zlib` (so `gzip`), `_bz2`, `_lzma`, `_hashlib` (`hashlib` falls back to the built-in digests), `_ssl`, `_ctypes`, `mmap`, `multiprocessing` | `ModuleNotFoundError` |
| threads | `threading` imports; `Thread().start()` → `RuntimeError: can't start new thread`; `os.cpu_count() == 1`; no `os.fork` |
| socket, select, subprocess, signal | import (the modules exist); no sockets or processes behind them `[INFERRED from preview1's sock_* stubs; not exercised]` |
| extension loader | `importlib.machinery.EXTENSION_SUFFIXES == ['.cpython-314-wasm32-wasi.so', '.abi3.so', '.so']`; `_imp.create_dynamic` present — the build is configured for dynamic loading, the libc underneath is not |

`[EXECUTED]` `out_wasi_probe_native_numpy.txt`: a native `numpy-2.5.4-cp314-cp314-macosx_14_0_arm64.whl` unpacked onto `sys.path` → `ModuleNotFoundError: No module named 'numpy._core._multiarray_umath'` (its `.cpython-314-darwin.so` matches no suffix), wrapped in numpy's "Importing the numpy C-extensions failed" message.

`[EXECUTED]` `out_wasi_probe_wasiwheels_numpy.txt`: dicej's `numpy-wasi.tar.gz` (v0.0.2, 2025-10-02; 19 `.cpython-314-wasm32-wasi.so` files) unpacked onto `sys.path` → the suffix matches, the loader runs, and the chain ends in **`ImportError: dlopen not implemented`**. That is the exact reason: wasi-libc's `dlopen` is a stub; a WASI binary links everything at build time.

`[READ]` (README and `Makefile` read before the clone was deleted; release page via the GitHub API) `wasi-wheels` is "an experimental proof-of-concept that Python packages containing native extensions can be cross-compiled for WASI and used with componentize-py. It is not being actively maintained; the packages are out-of-date … might not even build anymore. Do not rely on these builds for anything serious." Its numpy build compiles with `--target=wasm32-wasip2 -shared` against `libpython3.14.so` from a fork (`dicej/cpython`), `NPY_BLAS_ORDER=` and `NPY_LAPACK_ORDER=` empty (no BLAS), `-DNPY_NO_SIGNAL`, WASI SDK 27; the `.so` files are meant to be linked into one component by componentize-py's shared-everything dynamic linker at build time, never loaded at run time. The repo has 14 packages (numpy, pandas, pydantic-core, regex, sqlalchemy, tiktoken, yaml, aiohttp and friends), one maintainer, and no licence file (GitHub API: `license: null`). `[FETCHED 2026-10-15]` Brett Cannon's 2024 Plumber's Summit notes list "try to build NumPy and pandas into a `python.wasm` binary" as a plan and name the gap: "Python developers expect to download a `.whl` file w/ a `.so` and be done", but on WASI componentize-py "needs to add a step to embed the `.so` into `python.wasm`" (https://opensource.snarky.ca/Talks/2024/Plumber's+Summit). The CPython Discourse threads say the same: "there is no official story in Python-WASI land yet for dynamic linking" (https://discuss.python.org/t/cpython-now-compiles-and-passes-under-wasi-sdk-21/48514, fetched 2026-10-15).

`[READ]` `cpython:configure.ac:1352-1363`: `--enable-wasm-dynamic-linking` "only applies to Emscripten and WASI"; `:2482-2489` a `wasm32-wasi-threads` target exists behind `-pthread` and `--import-memory`. `cpython:Platforms/WASI/README.md:3`: WASI is tier 2. `cpython:Platforms/WASI/config.site-wasm32-wasi:63` pins `ac_cv_func_pthread_getcpuclockid=no`. No prebuilt threaded WASI CPython was found `[NOT VERIFIED: a wasi-threads CPython build may exist somewhere; Brett's releases are single-threaded]`.

`[READ]` `cpython-wasi-build` releases (via `gh release list`, 2026-10-15): CPython 3.15.0 with WASI SDK 33 (2026-10-09), 3.14.7 and 3.13.15 with WASI SDK 24 (2026-08-07); each is one `python.wasm` plus the pure stdlib. MIT.

`[INFERRED]` What would change the verdict, in order of plausibility: (a) **a static bundle** — our own `python.wasm` with numpy, pandas, matplotlib, Pillow, zlib, libpng, freetype and sqlite linked in, which is exactly Pyodide's job redone against wasi-sdk instead of Emscripten, by us, with Pyodide's years of per-package patches to re-derive; (b) wasi-libc gaining a real `dlopen` for WASI 0.2/0.3 components (componentize-py's build-time linking is the only form today); (c) a maintained WASI wheel index on PyPI (the Discourse thread https://discuss.python.org/t/support-wasm-wheels-on-pypi/21924 is a request, not a plan). None is on a roadmap I could find. The honest statement: the scientific stack's wasm effort is Emscripten's, and it is called Pyodide.

### 2. Pyodide ships the whole named stack, and it renders PNGs headless into bytes (EXECUTED, READ, FETCHED)

`[EXECUTED]` `experiments/s10/bench_pyodide_sci.mjs` → `out_pyodide_sci.json`. Pyodide 0.28.3 (`pyodide-lock.json`: CPython 3.13.2, `platform emscripten_4_0_9`, abi `2025_0`, 343 lock entries) under node 22; packages fetched once from the jsdelivr CDN into a cache (36 MB for everything used), then loaded from disk.

| step | cold (CDN) | warm (cache) | RSS delta |
|---|---:|---:|---:|
| `loadPyodide` (12 MB npm core) | 989 ms | 966 ms | 182 MB total |
| numpy 2.2.5 (3.1 MB wheel) | 527 ms | 214 ms | +56–74 MB |
| pandas 2.3.1 (5.3 MB) + dateutil, pytz, six | 1,941 ms | 374 ms | +136–171 MB |
| matplotlib 3.8.4 (6.7 MB) + Pillow, fonttools, kiwisolver, contourpy, cycler, pyparsing, packaging | 1,787 ms | 263 ms | +78 MB |
| scipy 1.14.1 (13.3 MB) + libopenblas 0.3.26 | 7,148 ms | 1,217 ms | +447–469 MB |
| Pillow, PyYAML, bs4, dateutil, pydantic 2.10.6 + pydantic_core, sqlite3, lxml 6.0.0, micropip | — | 1,734 ms | +141 MB |
| `micropip.install(["openpyxl", "python-docx"])` from PyPI (pure-Python wheels) | 966 ms | — | — |
| **everything above loaded** | | | **1,041 MB RSS** |

Imports after loading: `numpy 2.2.5, pandas 2.3.1, scipy 1.14.1, matplotlib 3.8.4, PIL 11.3.0, yaml 6.0.2, openpyxl 3.1.5, docx 1.2.0, bs4 4.13.3, dateutil 2.9.0.post0, pydantic 2.10.6, sqlite3 ok, lxml 6.0.0, ctypes 1.1.0, zlib 1.0`; `threading` and `multiprocessing` import but `Thread().start()` → `RuntimeError: can't start new thread`; `ssl` is absent; `socket` imports.

`[EXECUTED]` matplotlib with `matplotlib.use("agg")`, `fig.savefig(io.BytesIO(), format="png")`: a 17,537-byte PNG (`89504e470d0a1a0a`) in 94 ms of Python, 716 ms wall on first use (font cache); the bytes crossed to JavaScript as a `Uint8Array` of the same length. No `matplotlib_pyodide` browser backend is involved; Agg renders in wasm.

`[EXECUTED]` A second `loadPyodide` in the same node process worked (814 ms; RSS 1,045 → 1,118 MB). Pyodide instances are per JavaScript realm; two in one thread share nothing but the process.

`[FETCHED 2026-10-15]` https://pyodide.org/en/0.28.2/usage/packages-in-pyodide.html: 266 packages built for 0.28.2, among them scikit-learn 1.7.0, statsmodels 0.14.4, sympy 1.13.3, networkx 3.4.2, xarray, opencv-python 4.11, h5py, lightgbm, xgboost, sqlalchemy 2.0.39, cryptography 45, orjson, regex, tiktoken, PyMuPDF, requests 2.32 (over a JS `fetch` shim), openai 1.68. **Not** in the set: polars, pyarrow, duckdb, seaborn (pure Python; micropip-installable), plotly (pure Python), xlsxwriter and tabulate (pure Python), torch. `[READ]` pyodide release assets (GitHub API): `pyodide-0.28.3.tar.bz2` 352 MB (every package, for offline hosting), `pyodide-core-0.28.3.tar.bz2` 5.3 MB.

`[READ]` `just-bash:packages/just-bash/src/commands/python3/worker.ts:49-50` runs a plain CPython-Emscripten build (`vendor/cpython-emscripten/python.wasm` + `python313.zip`, 9.9 MB total), **not Pyodide**: no numpy, no packages, and "`import js` fails with `ModuleNotFoundError`" (`worker.ts:6`). That is the trade: just-bash removed the JS door by building its own interpreter without Pyodide's FFI, and gave up the package set. Cloudflare's Python Workers are the opposite trade (Pyodide, "a subset of popular packages including … Numpy", `[FETCHED 2026-10-15]` https://blog.cloudflare.com/python-workers).

### 3. The vfs bridge for Pyodide works: 20 bridge calls, 20 verbs, 106 SQL statements for a read-CSV, write-PNG, write-CSV job (EXECUTED)

`[EXECUTED]` `experiments/s10/pyodide_vfs_host.py` (Python host: `InMemoryStorage` + `VirtualFileSystem`, an `Authority.of(Principal("agent-7", kind="agent"))` on every verb, SQL counted with `before_cursor_execute`), `pyodide_bridge_main.mjs` (node main thread: relays over stdio JSON lines, wakes the worker through a 32 MiB `SharedArrayBuffer` with `Atomics.notify`), `pyodide_bridge_worker.mjs` (the Worker: loads Pyodide, defines **`VFSFS`**, an Emscripten filesystem object with `node_ops` {getattr, setattr, lookup, mknod, rename, unlink, rmdir, readdir} and `stream_ops` {open, close, read, write, llseek}, mounts it at `/vfs`, `chdir`s there, and runs the script **read from vfs itself** at `/vfs/scripts/job.py`), and `guest_job.py` (the agent's program: `pd.read_csv`, a groupby, `fig.savefig("/vfs/out/plot.png")`, `summary.to_csv`, `os.listdir`). Output `out_pyodide_vfs_bridge.json`:

```
exit 0; wall 5.0 s = loadPyodide 976 ms + loadPackages(numpy, pandas, matplotlib) 863 ms + run 2,816 ms
bridge calls 20, total wait inside the Worker 62 ms (≈3 ms per call incl. the vfs verb and base64/JSON over two pipes)
ops: stat 13, read 3, readdir 2, write 2        verbs: stat 13, read 3, ls 2, write 2
sql: 106 = stat 52 (4 each) + read 12 (4 each) + ls 10 (5 each) + write 32 (16 each)
png row: /out/plot.png kind=file mime_type=image/png size_bytes=51795 version=1 data_is_png=True content_is_none=True
summary row: /out/summary.csv text, content "region,sum,mean,max\n…"
trash: []        RSS of the Worker's process: 505 MB
```

The mapping that produced those counts, one verb per operation: `lookup` and `getattr` → `stat`; `readdir` → `ls`; `open` without `O_TRUNC` → one `read` with `columns={content,data,kind,size_bytes,mime_type,version,updated_at}` staged into the node; `mknod` of a file → no verb (minted at close); `close` of a dirty node → one `write` (`content=` if the bytes decode as UTF-8, else `data=`); `unlink`/`rmdir` → `delete(cascade=False)`; `rename` → `move`; `mkdir` → `mkdir`; `setattr(size)` → read + write; mode and times accepted and ignored. Errors cross as Emscripten errno numbers (ENOENT 44, EEXIST 20, ENOTDIR 54, ENOTEMPTY 55, EACCES 2, EROFS 69, EFBIG 22), the same WASI numbering study 04 used.

`[EXECUTED]` Two lessons the counts taught. (a) The first run made **52 `readdir("/")` calls**: the mount root's `getattr` returned a fresh `mtime` each time, so importlib's `FileFinder` cache for `sys.path[0]` (the cwd, `/vfs`) was invalidated on every import and re-listed the directory. A stable mtime for the root brought it to 1. Any adapter that invents timestamps will see this; the fix is to answer the root like any row. (b) The mime was not set by the write call (`write(data=…)` returned `mime None` in the trace) but the stored row read back as `image/png`: the extension of the target path decides at write time, which is exactly study 04's lean (extension as tie-break, never a sniff alone). `summary.csv` written as UTF-8 became a text row that `grep` can see.

`[EXECUTED]` `experiments/s10/pyodide_interrupt_and_door.mjs` → `out_pyodide_interrupt_and_door.json`: with `py.setInterruptBuffer(sab)` and the main thread setting `buf[0] = 2` after 300 ms, `while True: pass` raised `KeyboardInterrupt` at **305 ms**; `worker.terminate()` ended a second runaway at the same point. Budgets are enforceable from outside the Worker: time by the interrupt buffer (cooperative, polled by the interpreter) and by `terminate()` (unconditional); output by the host counting bytes on the stdout callback; memory only at the process level (see finding 4).

### 4. Isolation: under node, `import js` is the whole host; under Deno with no permissions, it is a locked door (EXECUTED, READ)

`[EXECUTED]` Same script, mode `door`, under node 22: from Python, `js.process.pid` = the real pid, `js.process.env.HOME` = `/Users/claygendron` (the **host** home, while `os.environ["HOME"]` inside the sandbox says `/home/pyodide`), `js.process.cwd()` = the host directory, `js.process.argv[0]` = the node binary, `hasattr(js.process, "binding") == True`, and `fetch`, `Buffer`, `WebAssembly` on the global. Anything node can do, the guest can do. Pyodide's own docs say the same of its CLI: "Execution is not sandboxed, this Pyodide Python has direct access to the native …" (`pyodide:docs/usage/cli.md:13`, `[READ]`).

`[EXECUTED]` `experiments/s10/pyodide_deno_door.ts` → `out_pyodide_deno_door.json`: `deno run --no-prompt --allow-read=<the pyodide npm cache>` (Deno 2.5.2, `npm:pyodide@0.28.3`, load 1,106 ms). `import js` succeeds and `js.Deno` exists, but `Deno.env.get("HOME")` → `NotCapable: Requires env access`, `Deno.readTextFileSync("/etc/hosts")` → `NotCapable: Requires read access`, `Deno.Command("id")` → `NotCapable: Requires run access`, a read outside the allowed directory → `NotCapable`. Only `Deno.cwd()` answered (a path string). The permission model is the boundary, and it holds against the guest's JavaScript, not just its Python.

`[READ]` `langchain-sandbox:libs/sandbox-py/langchain_sandbox/pyodide.py:95-101,179-186,227-229`: the Deno subprocess gets `--allow-read=node_modules --allow-write=node_modules` by default and nothing else; `allow_env/net/run/ffi` default `False`; memory is bounded with `--v8-flags=--max-old-space-size=<MB>` (which caps the JavaScript heap, not wasm linear memory `[INFERRED]`). Its README (`:1-40`) says the package is "no longer maintained", recommends "sandbox APIs or LLM provider APIs", and lists "File access: Currently not supported" — it never built a filesystem bridge; code goes in as a string, output comes back as strings. Monty's comparison page rated Pyodide's security "poor … only Deno restricts what that runtime reaches" (study 05, finding 3) — the executed facts above agree with both halves.

`[INFERRED]` The Pyodide tier's walls, from the outside in: Deno permissions (no env, no net, no run, no ffi, read only the pyodide cache); an OS wrapper on the sidecar process for the second wall and the memory cap (`srt`'s seatbelt profile on macOS and bubblewrap on Linux, `sandbox-runtime:README.md:5,107-108` `[READ]`; or a cgroup); and vfs's own gates, which the bridge re-enters through the public verbs so every rung and grant fires. There is no need to patch Pyodide to remove `js`; there is a need to never run it under bare node.

### 5. 9P: the Linux kernel mounted vfs, and native CPython with pip's numpy, pandas and matplotlib ran the same job unchanged (EXECUTED, READ)

`[EXECUTED]` `experiments/s10/p9_server.py`: a 9P2000 server over `VirtualFileSystem` (asyncio TCP; `Tversion Tauth Tattach Tflush Twalk Topen Tcreate Tread Twrite Tclunk Tremove Tstat Twstat`; qid.path = a SHA-1 of the vfs path, qid.version = the row version; the stat's `uid/gid/muid` = the attach `uname`; mode 0644/0755 invented from kind, as study 04 found there is nothing else to put there). Staging: `Topen` of a file is one `read`; `Twrite` edits the staged buffer; `Tclunk` of a dirty buffer is one `write`; `Topen` of a directory is one `ls` whose rows (size, version, mtime) are enough to encode every stat entry, so a listing is one verb; `Twalk` is one `stat` per element; `Tcreate` of a file mints nothing until clunk but is visible to `Twalk`/`Tstat` from the session's pending table (the first version minted the row at clunk only, and Linux's create sequence — Tcreate, then a fresh Twalk to the new name — got ENOENT; the pending table fixed it with zero extra verbs); `Tremove` is `delete(cascade=False)`; `Twstat` with a name is `move`, with a length a read + write, otherwise accepted and ignored. Error strings are Plan 9's, which Linux maps to errnos (`linux:net/9p/error.c:121-137` `[READ]`: "file does not exist" ENOENT, "file already exists" EEXIST, "not a directory" ENOTDIR, "directory is not empty" ENOTEMPTY, "permission denied" EACCES).

`[EXECUTED]` plan9port's `9p` (built in a scratch copy, `experiments` left untouched): `9p -a 'tcp!127.0.0.1!5640' ls -l /`, `ls /data`, `stat /data/sales.csv`, `read /data/sales.csv` all correct (`'sales.csv' … q (1692a0d0e08b9a30 1 ) m 0644 … l 540`). `9p write` opens with OWRITE and no create, so a new file cannot be made through it; `9p read /nope` printed nothing and exited 139 `[NOT VERIFIED: a client-side crash on the Rerror path on macOS; the server sent "file does not exist"]`. Report `out_p9_plan9port.json`.

`[EXECUTED]` Docker Desktop's Linux kernel has the 9P client built in (`/proc/config.gz`: `CONFIG_NET_9P=y`, `CONFIG_NET_9P_FD=y`, `CONFIG_9P_FS=y`; `/proc/filesystems` lists `9p`, `fuse`, `nfs`). From a `python:3.13-slim` image with the eleven packages pip-installed (433 MB of site-packages), with `--cap-add SYS_ADMIN`:

```
mount -t 9p -o trans=tcp,port=5640,version=9p2000,uname=agent-7,aname=/,dfltuid=0,dfltgid=0 192.168.65.254 /mnt/vfs
```

Two things the kernel insists on: the server must be an **IP address** (the kernel does not resolve names; `host.docker.internal` fails with "bad option"), and it must be **IPv4** (the v6 address Docker hands out answered "Network is unreachable"). Then `ls -la /mnt/vfs` showed `data out scripts`, `head` read the CSV, `echo > /mnt/vfs/out/hello.txt` created a row, `rm` moved it to `/.vfs/trash`, `mkdir` and `mv` (one `move` through `Twstat`) worked, and **sqlite3 created a database file**: `t.db-journal` 512 B then 8,720 B, `t.db` 8,192 B, each minted at clunk, the journal deleted to the trash, `select count(*)` answered 1. Then the agent's job, unchanged, `VFS_ROOT=/mnt/vfs python /mnt/vfs/scripts/job.py`:

```
platform: linux numpy 2.5.4 pandas 3.0.6 mpl 3.11.2
png magic ok: True size: 52520       listing /out: ['plot.png', 'summary.csv']
job exit 0 wall 2.39s                (python + numpy + pandas start 0.19 s; the four imports warm 0.47 s)
png row: /out/plot.png mime_type=image/png size_bytes=52520 version=1 data_is_png=True content_is_none=True
```

`[EXECUTED]` The cost, three ways (`out_p9_linux_v9fs_job.json`, `..._cacheloose.json`, `out_p9_microops_per_op.txt`):

| run | T-messages | vfs verbs | SQL |
|---|---|---|---:|
| the job, no cache, script on the mount (`sys.path[0]` = `/mnt/vfs/scripts`) | Tstat 354, Twalk 196, Tclunk 194, Topen 7, Tread 26, Tcreate 2, Twrite 2 | **stat 536**, read 4, ls 3, write 2 | 2,211 |
| the job, `cache=loose`, script copied off the mount | Tstat 10, Twalk 16, Tclunk 14, Topen 4, Tread 7, Tcreate 2, Twrite 2 | stat 17, read 3, ls 1, write 2 | **121** |
| mount only | Tstat 3, Tclunk 1 | stat 4 | 16 |

Per shell operation, one fresh server and mount each (`p9_microops.sh`; subtract the 4 stats / 16 statements the mount costs):

| operation (no cache) | T-messages | verbs | SQL |
|---|---|---|---:|
| `cat data/sales.csv` | Tstat 6, Twalk 3, Topen 1, Tread 3, Tclunk 4 | stat 9, read 1 | 40 |
| `ls out` | Tstat 7, Twalk 3, Topen 1, Tread 1, Tclunk 4 | stat 10, ls 1 | 45 |
| `stat data/sales.csv` | Tstat 6, Twalk 2, Tclunk 3 | stat 9 | 36 |
| `echo abc > out/new.txt` | Tstat 5, Twalk 4, Tcreate 1, Twrite 1, Tclunk 4 | stat 7, write 1 | 44 |
| `mkdir out/d` | Tstat 5, Twalk 4, Tcreate 1, Tclunk 4 | stat 10, mkdir 1 | 53 |
| `rm scripts/job.py` | Tstat 8, Twalk 5, Tremove 1, Tclunk 5 | stat 13, delete 1 | 62 |
| `mv data/sales.csv data/sales2.csv` | Tstat 8, Twalk 10, Twstat 1, Tclunk 8 | stat 17, move 1 | 91 |
| `python -c 'open("data/sales.csv").read()'` | Tstat 11, Twalk 4, Topen 2, Tread 7, Tclunk 5 | stat 14, ls 1, read 1 | 65 |
| `python -c 'open("out/x.bin","wb").write(bytes(range(256)))'` | Tstat 10, Twalk 5, Topen 1, Tread 4, Tcreate 1, Twrite 1, Tclunk 5 | stat 11, ls 1, write 1 | 65 |

`[INFERRED]` The pattern: the real work is always **one verb** (a read, a write, a move), exactly study 04's staging rule, and the overhead is the Linux client's revalidation — a `Twalk` + `Tstat` per path element per syscall in legacy mode without a cache (`linux:Documentation/filesystems/9p.rst:136,196-203` `[READ]`: `cache=none` is the default; `version=9p2000` is "Legacy mode"). Three cheap mitigations, in order: `cache=loose` on the mount (536 → 17 stats on the job, at the cost of a staleness window the ADR must name); a `stat` memo in the server keyed on (path, version) that answers repeated walks without a verb; and 9P2000.L, which adds `Tgetattr`/`Tlopen`/`Treaddir` with fewer round trips but a bigger message set `[NOT VERIFIED: not implemented; the kernel source and the 9p.rst text were read]`. The `stat` verb itself is 4 statements, so even the uncached job is 2,211 statements for a two-second run.

`[READ]` Where 9P is mountable: Linux v9fs over tcp, unix, fd and virtio (`9p.rst:45-65,115-130`); a microVM's virtio-9p device; plan9port's `9pfuse` (needs FUSE; macFUSE is not installed here and must not be); 9front natively. microsandbox mounts host directories through virtiofs (`microsandbox:docs/sandboxes/volumes.mdx:193` "Directory volumes mount through virtiofs"), exposes a per-file `fs` API over its agent channel (`docs/sandboxes/filesystem.mdx:8-10`), runs on Apple Silicon, Linux with KVM and Windows WHP (`sdk/python/README.md`), and is "still beta software" (`README.md`); its guest kernel's 9P support is `[NOT VERIFIED: the kernel config was not read]`. Cloudflare's sandbox-sdk 1.0 reduced itself to "file operations and bucket mounts" (`sandbox-sdk:README.md:81`) with `S3Mount` and a `sandbox-shim` protocol — a different filesystem bridge, no 9P. Anthropic's `sandbox-runtime` is a policy wrapper (seatbelt on macOS, bubblewrap on Linux; `README.md:107-108`), not a mount; it is the right second wall around either tier's sidecar.

### 6. Native CPython's own numbers, for the comparison table (EXECUTED)

`[EXECUTED]` In the container: bare `python -c pass` 7 ms; `python -c 'import numpy, pandas'` 191 ms; the four scientific imports warm 0.47 s; a process that imports all eleven packages peaks at **112 MB** RSS (`resource.ru_maxrss`); site-packages 433 MB on disk; threads, processes, sockets and every C extension pip can build. Isolation is whatever the host wraps it in — a container (shared kernel), gVisor, bubblewrap, a microVM (own kernel).

### 7. Monty and the others, briefly (READ, EXECUTED in study 05)

- **Monty** (study 05): a Rust interpreter of a Python subset with no C ABI by design ("no FFI, no C dependencies", `monty:docs/security.md`); numpy can never import because there is nothing to import it into. It also lacks `csv`, `io`, `enum`, `struct`, generators and class inheritance. Its strengths are real — 0.8 ms sessions, 10 MB workers, 2.6 KB continuations, a process pool with memory limits, no JavaScript door — and they buy a fast lane for one-liners and small text transforms, which Pyodide's warm `runPython` (0.17 ms) also covers once a worker is loaded. `[INFERRED]` Keeping two Pythons means two subsets to explain; Monty earns a slot only if the host cannot carry a Deno sidecar at all. Lean: not on the critical path; the message-protocol contract (study 05 §B) keeps the binding cheap if it returns.
- **RustPython** (study 05): `-c` exits 1 silently at HEAD on WASI; no C extensions either way (it has its own extension ABI and no numpy). Out.
- **GraalPy** `[FETCHED 2026-10-15]`: runs numpy through its own `graalpy`-tagged wheels (https://www.graalvm.org/jdk23/reference-manual/python/Native-Extensions/ — "experimental", CPython wheels "not binary compatible"); it is a JVM or native-image runtime, not a wasm one; GraalWasm is a separate project (a wasm *host* on the JVM). It is a native tier with a different, smaller ecosystem and a JVM. Out.
- **MicroPython-wasm** `[FETCHED 2026-10-15]`: `ulab` is "numpy-compatible" subset for microcontrollers, "not quite a port of NumPy" (https://hackster.io/news/zoltan-voros-ulab-brings-numpy-style-fast-math-to-micropython-in-just-25kb-of-compiled-code-aa52a81cd269), no pandas, no matplotlib. Out.
- **"Python in a wasm component with numpy"**: componentize-py plus wasi-wheels is the only such claim, and finding 1 is what it rests on. A build-time-linked component with numpy and pandas may still be buildable from dicej's 2025-10-02 refresh `[NOT VERIFIED: not attempted; the clone had no licence and the README disowns it]`; matplotlib and scipy have never been built for it.
- **Hosted sandboxes** `[FETCHED 2026-10-15]` (E2B on Firecracker, Modal on gVisor, Daytona containers or VMs; pricing and session caps per https://www.beri.net/article/e2b-vs-modal-vs-daytona-agent-sandbox-pricing-isolation-2026 and https://www.alexcloudstar.com/blog/sandboxing-ai-generated-code-execution-2026/): each is a native-CPython tier someone else operates, with a per-file upload/download API; `[INFERRED]` any of them can mount vfs over 9P the moment the sandbox can open a TCP connection to the host (E2B and Modal sandboxes have outbound networking by default), which makes them backends for the same program ABI, chosen by the host, with no vfs code change beyond the 9P listener's address.

---

## What this means for vfs

### A. The decision table

| | CPython on WASI (own build or Brett's) | **Pyodide under Deno** (sidecar) | **Native CPython + 9P** (container / microVM / bwrap) | Monty | RustPython / GraalPy / MicroPython |
|---|---|---|---|---|---|
| numpy, pandas, scipy, matplotlib | **none** (dlopen not implemented; no builds exist) | all four, versions above | all, latest pip | none, by design | none on wasm; GraalPy native only |
| the eight utilities | bs4, dateutil, openpyxl yes (pure); Pillow, PyYAML-C, lxml → python-docx, pydantic-core, sqlite3 **no** | all eight (two via pure wheels) | all | none | — |
| stdlib gaps | no sqlite3, zlib, bz2, lzma, ssl, ctypes, mmap, multiprocessing; no threads | no ssl, no threads; sqlite3 and zlib present | none | 23 modules total | — |
| cold start | 6 ms per call after a 1.7 s Wizer compile (study 05) | ~1.0 s + 0.2–1.2 s per package group, warm cache | 7 ms bare; 0.19 s with numpy+pandas; plus the sandbox's own boot (container ≈ 0.5–1 s, microVM "under 100 ms" per microsandbox's claim `[NOT VERIFIED]`) | 0.8 ms | — |
| memory per session | ~415 MB after compile in-process (study 05); mmapped cwasm in a worker less `[NOT VERIFIED]` | 182 MB base; 505 MB with numpy+pandas+matplotlib; 1,041 MB with scipy | 112 MB for all eleven packages imported; plus the sandbox | 10 MB | — |
| concurrency | one guest per process (wasmtime-py trap global) | one Pyodide per Worker; N Workers per Deno process or N sidecars; no snapshot, so a warm pool | one process per session; the OS does the rest | a worker pool | — |
| interrupt / budget | epoch trap; store limits | interrupt buffer (305 ms measured), `terminate()`; memory only at process level | kill, `ulimit`, cgroups, timeout | time, memory, suspensions | — |
| file access → vfs verbs with Authority | preview1 shim (study 04), one Authority per run | VFSFS adapter + SAB bridge + stdio to the host; one Authority per session, bound in the host | 9P server; one Authority per connection, bound by the host to the listener | `AbstractOS` callback | — |
| PNG back as a row | bytes through `fd_write`/close → `write(data=)` | `savefig("/vfs/out/plot.png")` → close → `write(data=)` → `image/png` row (executed) | same, via `Tclunk` (executed) | bytes value from a host function | — |
| isolation | wasm sandbox; no ambient host at all | Deno permissions (holds, executed); under node **none** | kernel namespaces / gVisor / VM; strongest with a microVM | language sandbox, process pool | — |
| what to build/ship | a WASI SDK + Wizer pipeline, a 40 MB cwasm per wasmtime version (study 05) | a Deno binary + 12 MB core + 36 MB of wheels (or the 352 MB full dist offline); a VFSFS adapter (~300 lines) and a host bridge | a sandbox runtime, a 433 MB image, the 9P server (~380 lines) | `pydantic-monty` + a 27 MB runtime wheel | — |
| platforms | anywhere wasmtime runs | anywhere Deno runs (macOS, Linux, Windows) | Linux natively; macOS via Docker Desktop (proven) or microsandbox (Apple Silicon); Windows via WSL/WHP `[NOT VERIFIED]` | macOS, Linux, Windows | — |
| licence | PSF; MIT (Brett's) | MPL-2.0 (Pyodide), MIT (Deno) | PSF + each package | MIT | MIT / UPL / MIT |
| maturity | tier-2 CPython platform; package story absent | 0.28, years of per-package patches, 266 packages, used in production by Cloudflare and JupyterLite | the ecosystem itself | 1.1.0, fast-moving | preliminary / experimental |

### B. The recommendation, tiered, behind one program ABI

The brief's ABI (study 03) gives a program argv, stdin, env and the filesystem capability, and takes back stdout, stderr and an exit code. Both tiers below are programs of that shape. The kind is a table row, invisible on the pipe, as study 03 said: `python3` is one name, and which runtime answers is a host choice.

**Tier 1 — Pyodide under Deno, the Python that ships with vfs.** A sidecar process per host (or per session), spawned by vfs with `deno run --no-prompt --allow-read=<pyodide cache>` and nothing else, running a Worker per session with the VFSFS adapter mounted at `/vfs`. It serves numpy, pandas, scipy, matplotlib, Pillow, PyYAML, bs4, dateutil, pydantic, sqlite3, lxml and any pure-Python wheel the host pre-stages (openpyxl, python-docx, seaborn, plotly, tabulate). It runs on every laptop and server that can run a static Deno binary, needs no kernel features, and its isolation is Deno's permission check plus vfs's gates. Its honest limits: ~1 s cold, 0.5–1 GB per session, no threads, no `ssl`/sockets (no network is the v1 rule anyway), no snapshot, and a JavaScript runtime in the dependency closure of a Python library.

**Tier 2 — native CPython over 9P, the escalation.** The host runs a sandbox it already trusts (a container on a Linux server, microsandbox or Docker Desktop on a laptop, gVisor, a hosted sandbox), vfs listens for 9P on a per-session socket bound to the session's `Authority`, and the guest kernel mounts it. Everything pip has, threads and processes included, 112 MB for the whole stack, and the strongest wall. Its honest limits: an OS dependency vfs cannot pip-install, a chatty kernel client that wants `cache=loose` or a server-side stat memo, and whole-file staging that a seek-heavy program (sqlite over a large database) will feel.

**The trigger from tier 1 to tier 2**, as a classified refusal the agent can read: a package outside Pyodide's set that is not pure Python; `Thread().start()` or `multiprocessing`; a staging budget or memory budget exceeded; a run past the sidecar's time budget; or a host policy that says "native only". The refusal names the tier that would work (`unsupported.runtime: python3 here is Pyodide 0.28 (CPython 3.13, no threads, 266 packages); the host offers/does not offer a native sandbox`), the same shape study 05 gave Monty's subset errors.

**WASI CPython** keeps exactly the slot study 05 and 10 gave it: stdlib-only Python *programs* installed as `/.agents/bin/*.py` or bundled in a `.wasm`, run under the preview1 shim with epoch interrupts — fast, hermetic, and never the scientific tier. **Monty** is not needed on the critical path (finding 7).

### C. The exact import lists per tier

Tier 1 (Pyodide 0.28.3, executed): `numpy 2.2.5, pandas 2.3.1, scipy 1.14.1, matplotlib 3.8.4 (Agg), PIL 11.3.0, yaml 6.0.2, bs4 4.13.3, dateutil 2.9.0, pydantic 2.10.6, sqlite3, lxml 6.0.0, openpyxl 3.1.5*, docx 1.2.0*` (* pure-Python wheels the host pre-stages; micropip from PyPI needs network, which v1 denies). Also in the lockfile and loadable: scikit-learn, statsmodels, sympy, networkx, xarray, opencv-python, h5py, lightgbm, xgboost, sqlalchemy, cryptography, orjson, regex, tiktoken, PyMuPDF, requests (over a fetch shim that v1's no-network rule makes inert). Cannot: threads (`can't start new thread`), `ssl`, sockets, `subprocess`, polars, pyarrow, duckdb, torch, any C-extension wheel not on the Pyodide list.

Tier 2 (native, executed with these versions): `numpy 2.5.4, pandas 3.0.6, scipy 1.18.1, matplotlib 3.11.2, Pillow 12.3.0, PyYAML 6.0.3, openpyxl 3.1.5, python-docx 1.2.0, beautifulsoup4 4.15.0, python-dateutil 2.9.0, pydantic 2.14.1` and the rest of pip. Cannot: reach the host (the sandbox's job), reach the network (the sandbox's policy), see any file that is not a vfs row the Authority may see (the 9P server's job).

WASI CPython (Brett 3.14.7, executed): the pure stdlib minus `sqlite3, gzip/zlib, bz2, lzma, ssl, ctypes, mmap, multiprocessing`; pure-Python packages (bs4, dateutil, openpyxl, tomli, attrs…); no C extensions, no threads.

### D. The filesystem-bridge design for tier 1 (the shape that ran)

```
Python host (vfs process)                           Deno sidecar
──────────────────────────                          ──────────────────────────────────────────────
session = {Authority, budget, cwd}                  main thread: relay
  ▲ verb calls (async), one per request               ▲ postMessage({req})     ▼ SAB bytes + Atomics.notify
  │ stat / ls / read(columns=…) / write / mkdir /   Worker (one per session): Pyodide + VFSFS at /vfs
  │ delete(cascade=False) / move                      node_ops: lookup,getattr→stat  readdir→ls  mknod(file)→none
  │                                                   mkdir→mkdir  unlink,rmdir→delete  rename→move
  └── stdio JSON lines (or a Unix socket) ──────────  stream_ops: open→read (stage)  close(dirty)→write  read/write/llseek→buffer
```

Rules, each one executed above or carried from study 04:

1. **Sync in the guest, async in the host.** Emscripten's `node_ops`/`stream_ops` are synchronous; the Worker blocks on `Atomics.wait`; the relay and the host are asynchronous. The same shape as just-bash's HOSTFS and study 04's thread hop; no MEMFS-plus-`syncfs` (writes invisible until a sync would break "a write mints a version at close").
2. **Whole-file staging, one verb per open and one per dirty close**, with a staging budget that answers `EFBIG` (16 MiB in the experiment; the ADR sets it against the session's memory budget). `mknod` mints nothing; `close` mints the row; a created-and-never-written file still lands as an empty row.
3. **Authority is bound in the host at session start and never crosses.** The guest sends paths; the host supplies the Authority on every verb. `uname`-style identity strings do not exist in this protocol. Attribution of write-back: the agent's Authority unchanged, with the program path in `source_identity` (study 04 fork Q4).
4. **Text versus bytes by extension at write time** (observed: `.png` → `image/png` bytes row; `.csv` → text row), never a sniff alone; the UTF-8 decode is the fallback for extensionless names.
5. **The mount root answers like a row** (stable mtime); importlib lists `sys.path[0]` on every cache miss and a moving mtime makes every import a `ls`.
6. **`/vfs` is the mount point and the cwd; `/.vfs` is hidden** (a path predicate in `lookup`, zero cost; study 04 fork Q3); `/.agents` read-only.
7. **Budgets:** time by the interrupt buffer with `terminate()` as the backstop; output bytes counted by the host on the stdout/stderr callbacks; memory by an OS limit on the sidecar; host calls by a per-session counter (Monty's `max_suspensions` lesson).
8. **Framing:** base64-in-JSON over two pipes cost ≈3 ms per call here, fine for 20 calls, wrong for a 10,000-row loop; the production relay uses length-prefixed binary frames over a Unix socket and the SAB carries raw bytes. A measured decision, not a v1 blocker.
9. **Pre-staged wheels, no network:** the host's package cache (36 MB for the named set) is the only thing `--allow-read` admits besides the core; `micropip` is absent from the session unless the host grants `--allow-net` to an allow-list, which v1 does not.

For tier 2 the bridge is the 9P server, with two rules of its own: the **Authority is bound to the listener**, one socket per session, and the attach `uname` is logged, never trusted (a sandbox can send any string); and a **stat memo keyed on (path, version)** or `cache=loose` is on by default, with the staleness window stated in the mount's docstring.

### E. The media round trip, proven twice

A program wrote `/out/plot.png` through an ordinary `open(..., "wb")`; the adapter's close handed the host 51,795 bytes (Pyodide) or 52,520 bytes (native over 9P); the host called `write(path=…, data=…)`; the row came back from `read(columns={data, mime_type, …})` with `kind=file, mime_type=image/png, content=None, data[:8]=89504e470d0a1a0a`; and the host minted `{"type": "image", "mimeType": "image/png", "data": <base64>}` — the MCP `ImageContent` shape — from the row at the boundary. Base64 exists nowhere else: not in the row, not in the text rendering (which gets the placeholder, study 08), not in the pipe. The sibling `summary.csv` landed as a text row the lexical index can see. The same `Result` carries both rows; the MCP adapter emits one text block and one image block (study 08's one-text-block-first lean).

### F. What to adopt and what to reject

Adopt: Pyodide under Deno as the shipped Python; the VFSFS adapter as the fourth adapter over the one filesystem capability (study 04 §B: preview1, Emscripten, Monty's `AbstractOS`, QuickJS's table — now the Emscripten one is executed); the 9P server as the fifth, and the one that makes any kernel-mountable sandbox a vfs client; the tier trigger as a classified refusal; the extension-decides-mime rule; the stable-root-mtime rule.

Reject: WASI CPython as the scientific tier (finding 1); Pyodide under node (finding 4); `MountDir`/host-directory preopens in any tier (vfs is the filesystem); a whole-corpus copy-in/copy-out (E2B's and microsandbox's per-file API shape) as the integration — it duplicates the corpus and loses versions, the trash and the Authority; building our own CPython-Emscripten without Pyodide's packages (just-bash's choice) — it gives up the only thing this question asks for.

---

## Forks for the ADRs

**F1. Which Python ships with vfs?** Options: (a) Pyodide under Deno as a sidecar; (b) WASI CPython, scientific stack deferred until the ecosystem builds it; (c) Monty first, as study 05 leaned, with the scientific stack only in a native tier. *Lean: (a).* It is the only in-process-class runtime that imports all five named packages today (finding 2), its bridge to vfs rows is executed (finding 3), and Deno makes its one door a wall (finding 4). (b) cannot import numpy (finding 1) and nothing on any roadmap changes that. (c) would ship a subset that cannot read a CSV with `csv`.

**F2. Does vfs own a native tier, and where does it draw the sandbox line?** Options: (a) vfs ships the 9P server and a tier-2 contract; the host supplies the sandbox (container, microVM, bwrap, hosted); (b) vfs ships a sandbox too (microsandbox or `srt` as a dependency); (c) no native tier at v1. *Lean: (a).* The 9P server is 380 lines over the verbs and was mounted by a stock kernel (finding 5); sandboxes are host property (Docker on servers, microsandbox or Docker Desktop on laptops, E2B in the cloud), each with its own operator story, none pip-installable. (c) leaves threads, polars, torch and 433 MB of pip with no home.

**F3. The tier trigger.** Options: (a) the agent chooses (`python3 --native`); (b) the host chooses by policy, the agent gets a refusal that names the other tier; (c) automatic fallback on `ImportError`. *Lean: (b).* Automatic fallback (c) re-runs side-effecting programs; agent choice (a) is a capability the host must still gate. A refusal with the next move is study 05's pattern for Monty's subset and costs nothing.

**F4. Sidecar topology for tier 1.** Options: (a) one Deno process per vfs host, a Worker per session; (b) one Deno process per session; (c) a warm pool of pre-loaded Workers checked out per run. *Lean: (c) over (a).* A session is 0.5–1 GB and ~2 s to load with packages (finding 2); agents run many short programs; a pool amortizes the load and `terminate()` recycles a runaway. Per-session processes (b) buy an OS memory cap per session at the cost of a cold start each; worth it only where the host wants cgroups per agent.

**F5. Transport between the sidecar and the vfs host.** Options: (a) stdio JSON lines with base64 (the experiment); (b) a Unix socket with length-prefixed binary frames; (c) in-process, by embedding V8/Deno in the Python process. *Lean: (b) at v1*, (a) proved the shape. (c) is a large native dependency for a 3 ms saving per call.

**F6. 9P dialect and caching.** Options: (a) 9P2000 legacy with `cache=loose` and a server-side stat memo; (b) 9P2000.L; (c) 9P2000.u. *Lean: (a).* Legacy 9P2000 is the smallest message set, plan9port and Linux both speak it, and the two mitigations bring the job to 17 stats (finding 5). .L is the better kernel client (fewer round trips, real `getattr`) and the named future when a profile shows the walk cost.

**F7. How a 9P connection gets its Authority.** Options: (a) trust `uname` at Tattach; (b) one listener per session, Authority bound in the host, `uname` logged only; (c) Tauth with a bearer token the host minted. *Lean: (b)*, with (c) as the form for a hosted sandbox that reaches vfs over a shared port. Identity is a value on the call; a string from the guest is not one.

**F8. What `python3` means in the text surface.** Options: (a) `python3 --version` reports "Pyodide 0.28 (CPython 3.13.2, emscripten; no threads; 266 packages)"; (b) it reports plain "Python 3.13.2". *Lean: (a).* Study 05's rule for Monty applies: the subset is a product fact to document, not to hide, and an agent that reads it stops trying `threading`.

**F9. Monty's role.** Options: (a) drop; (b) keep as `python3 --lite` for one-liners; (c) keep as the only Python where no Deno is available. *Lean: (a) at v1, (c) as the documented fallback if a host cannot spawn Deno.*

**F10. Does vfs invest in a WASI scientific build?** Options: (a) no; (b) a static `python.wasm` with numpy, pandas, matplotlib linked in, our build; (c) componentize-py + wasi-wheels refreshed. *Lean: (a).* (b) is Pyodide's job redone against a toolchain with no `dlopen`, no threads and no BLAS story, and every patch is ours to carry; (c) is an unlicensed proof of concept its author disowns. Revisit if WASI gains dynamic linking or a maintained wheel index appears.

---

## Sources

- Clones (read-only; commits and licences in `refresh.log` / `licenses.log`, S10 wave): `cpython-wasi-build` 7ce0aaf (MIT; `README.md` absent, `LICENSE`, `.github/workflows/release.yml`; releases via `gh release list`/`view`); `langchain-sandbox` fac037c (MIT; `README.md:1-40`, `libs/sandbox-py/langchain_sandbox/pyodide.py:73-101,179-248`, `libs/pyodide-sandbox-js/main.ts:188-216`); `microsandbox` 0feec23 (Apache-2.0; `README.md`, `sdk/python/README.md`, `docs/sandboxes/{volumes,filesystem,overview}.mdx`, `COMPATIBILITY.md:119`); `wasi-wheels` b28844f (no licence; `README.md`, `Makefile`, `numpy/build.sh`, `.gitmodules` read before deletion; releases via the GitHub API: v0.0.2 2025-10-02 `numpy-wasi.tar.gz`, `latest` 2024-03-06 fourteen tarballs); `just-bash` 9ab0e0d (`packages/just-bash/src/commands/python3/worker.ts:1-60,178-671,1308-1414`, `src/commands/worker-bridge/protocol.ts:1-60,125-410`, `vendor/cpython-emscripten/`); `pyodide` adc5b63 (`docs/usage/cli.md:13`, `docs/usage/keyboard-interrupts.md`, `src/js/api.ts`, `src/js/nativefs.ts` via study 04); `cpython` fdec4df (`Platforms/WASI/README.md:3,37-57`, `Platforms/WASI/config.site-wasm32-wasi:63`, `configure.ac:1352-1363,2482-2489`); `plan9port` b6564bd9 (`src/cmd/9p.c` usage, built in a scratch copy with `./INSTALL -b`); `linux` (`Documentation/filesystems/9p.rst:45-65,115-262`, `fs/9p/v9fs.c:69-71,362`, `net/9p/error.c:45-137`, `net/9p/client.c:1437-1511`); `sandbox-runtime` 9a277e5 (`README.md:1-160`); `sandbox-sdk` a080a65 (`README.md:13-92`); `monty` 2bb9f08a via study 05.
- vfs live tree: `src/vfs/base.py` (`read`, `stat`, `ls`, `write`, `delete`, `mkdir`, `move`, every one with `authority=`), `src/vfs/authority.py` (`Authority.of`, `Principal`), `src/vfs/results/kinds.py:58-74`, `src/vfs/storage/backends/memory.py`; `context/research/studies/2026-10-15-agent-shell/{04,05,10}-*.md`.
- Web (fetched 2026-10-15): Pyodide packages for 0.28.2 https://pyodide.org/en/0.28.2/usage/packages-in-pyodide.html; Brett Cannon, Plumber's Summit 2024 https://opensource.snarky.ca/Talks/2024/Plumber's+Summit; CPython Discourse on WASI SDK 21 and dynamic linking https://discuss.python.org/t/cpython-now-compiles-and-passes-under-wasi-sdk-21/48514; "Support WASM wheels on PyPI" https://discuss.python.org/t/support-wasm-wheels-on-pypi/21924; componentize-py announcement (wasi-wheels as the numpy source) https://www.fermyon.com/blog/introducing-componentize-py; componentize-py meeting notes https://hackmd.io/3ZktfALiSZWn41ad7y3gnA; GraalPy native extensions https://www.graalvm.org/jdk23/reference-manual/python/Native-Extensions/; ulab https://hackster.io/news/zoltan-voros-ulab-brings-numpy-style-fast-math-to-micropython-in-just-25kb-of-compiled-code-aa52a81cd269; Cloudflare Python Workers https://blog.cloudflare.com/python-workers; hosted-sandbox comparisons https://www.beri.net/article/e2b-vs-modal-vs-daytona-agent-sandbox-pricing-isolation-2026 and https://www.alexcloudstar.com/blog/sandboxing-ai-generated-code-execution-2026/ (secondary, pricing and isolation claims not independently verified).
- Experiments (`experiments/s10/`): `wasi_cpython_probe.py` → `out_wasi_probe_{plain,native_numpy,wasiwheels_numpy}.txt`; `bench_pyodide_sci.mjs` → `out_pyodide_sci.json`; `pyodide_vfs_host.py` + `pyodide_bridge_main.mjs` + `pyodide_bridge_worker.mjs` + `guest_job.py` → `out_pyodide_vfs_bridge.json`; `pyodide_interrupt_and_door.mjs` → `out_pyodide_interrupt_and_door.json`; `pyodide_deno_door.ts` → `out_pyodide_deno_door.json`; `p9_server.py` → `out_p9_plan9port.json`, `out_p9_linux_v9fs.json` (shell ops + sqlite), `out_p9_linux_v9fs_job.json`, `out_p9_linux_v9fs_job_cacheloose.json`, `out_p9_linux_v9fs_microops.json`; `p9_microops.sh` → `out_p9_microops_per_op.txt`. The Docker image was built from `python:3.13-slim` plus `pip install numpy pandas scipy matplotlib pillow pyyaml openpyxl python-docx beautifulsoup4 python-dateutil pydantic` (Dockerfile in the session scratchpad). `pyodide_untrusted/` (the npm install, the wheel cache, the Deno cache; 49 MB) is git-ignored.
