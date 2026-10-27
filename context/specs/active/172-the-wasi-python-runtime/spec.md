# 172 — The WASI Python runtime: a static CPython with numpy and pandas compiled in, the yearly build, the reactor host and the verb door; QuickJS for JavaScript

- **Status:** draft, **rewritten 2026-10-16 on spike 173's result**
  (study `13-wasi-python-spike.md`). The 2026-10-15 native-sidecar
  and 9P draft is withdrawn; its shape is kept as the appendix. Waits
  on Clay's three pending answers in ADR 086 and on spec 169b (the
  WASI host) landing first.
- **Date:** 2026-10-16
- **Owner:** Clay Gendron
- **Kind:** feature (`src/vfs/shell/guests/python.py`: the `python`
  program kind, the reactor entry, the door binding, the install
  command; `src/vfs/shell/guests/quickjs.py`: the JavaScript guest;
  `tests/support/guests/`: the fixtures and the verification jobs).
- **Depends on:** ADR 086 (the runtime, its pins); ADR 082 (the ABI,
  the kinds, `/opt/bin`, the suffix order); ADR 083 (bytes to bytes);
  ADR 084 (budgets, the install grant); spec 169b (the host: shim,
  staging, cache, budgets, the executor). Study 05 for QuickJS; study
  10's exit-code rule; study 13 for every number below.
- **Research it stands on:** study `13-wasi-python-spike.md` and its
  executed recipe under
  `context/research/studies/2026-10-15-agent-shell/experiments/s12/`
  (scripts, cross files, C sources, outputs); studies 04 (§5), 05,
  11 and 12 for the record of what was ruled out.

## Intent

After this spec an agent types `python3 analyze.py` and a real CPython
with numpy and pandas runs it inside WebAssembly, reaches nothing but
vfs, reads its inputs from rows under the agent's authority, writes a
CSV that lands as a text row, calls vfs verbs through an importable
`vfs` module, and is killed by its budgets; the same binary runs on
Linux, macOS and Windows and inside any web server process that can
load wasmtime; `node script.js` runs under QuickJS the same way; and
the runtime is rebuilt once a year by a CI job from pinned sources
with no patch to any upstream tree.

## 1. The yearly build (lives in `wasi_python`, not here)

**Amended 2026-10-16 (Clay):** the build is its own project,
`~/Git/Repos/wasi_python` (wasipython.dev, Apache-2.0), seeded from
the spike's recipe the same day. This section is the contract vfs
holds that project to; the scripts, pins and workflow are its. vfs
declares an optional extra `vfs-py[python]` on the `wasi-python`
wheel at a pinned, hashed version and runs the consumer gate (§6's
tests) against it.

- **The recipe is the spike's**, moved from `experiments/s12/` and
  cleaned: `00_download.sh` (fetch by URL, verify every SHA-256, fail
  on mismatch), the CPython build through its own `Tools/wasm/wasi`
  driver, zlib, the numpy and pandas meson cross builds with the
  compiler wrapper that writes each extension module as a static
  archive, `gen_inittab.py`, the one link with the generated
  `Setup.local`, the reactor link, the stdlib zip, the Wizer
  snapshot. Each step is a script; the workflow runs them in order.
- **Pins** (every one a URL plus a hash in `SHA256SUMS`): CPython,
  wasi-sdk, numpy, pandas, zlib, python-dateutil, tzdata, six, Wizer,
  the wasmtime CLI, and a `uv.lock` for the build venv (Cython, meson,
  ninja, versioneer). The toolchain line is ADR 086 pin 2
  `[NEEDS CLARIFICATION: 3.15 + wasi-sdk 33 (lean) or 3.14.8 +
  wasi-sdk 24 (proven)]`.
- **Zero upstream patches** is a gate: the workflow fails if any
  file under a source tree differs from the tarball. Adaptations are
  recipe files: the two cross files, `wasi-cc`/`wasi-cxx`,
  `python-wasi-cross`, the two rename headers, `vfsmodule.c`,
  `vfs_main.c`, the generated inittab, the `ctypes` and `mmap`
  stand-ins, and `cxa_stubs.c` only on the SDK-24 line. The two
  stand-ins are the honest upstream candidates (a one-line
  `try/except ImportError` each in pandas); the spec files them
  upstream and drops them when a release carries the fix.
- **Verification in the workflow** is this repo's shim running the
  spike's jobs (§6's tests) against the fresh artifact before it is
  published.
- **Artifacts**: `vfs-python-<pyver>-numpy<ver>-pandas<ver>-wasm32-
  wasip1.wasm` (plain reactor), `…-wizer.wasm` (snapshot),
  `python3XY.zip`, `SHA256SUMS`, `MANIFEST` (every pin, every recipe
  file's hash, the Wizer command line, `SOURCE_DATE_EPOCH`), xz. The
  `.cwasm` is never an artifact. The workflow runs on
  `workflow_dispatch` and a yearly cron; a build is reproducible
  byte for byte from the manifest `[NEEDS CLARIFICATION: verify
  reproducibility across the macOS build the spike made and the
  Linux build the workflow makes; CPython's driver sets
  SOURCE_DATE_EPOCH already]`.

## 2. The install and the program kind

- **`vfs python install`** (spec 171's CLI, or a Python entry point
  until it lands) takes the artifacts from the installed `wasi-python`
  wheel (`wasi_python.artifacts()`; the release-asset download is the
  fallback when the extra is absent, hash-verified) and writes as the
  system actor the binary at
  `/opt/bin/python3.wasm` and the zip at `/opt/lib/python3XY.zip`
  (CPython's `getpath` finds the prefix from the binary's directory
  through the `lib/python3XY.zip` landmark; the spike ran with this
  layout under `/usr/local`). `--snapshot` (default per ADR 086 pin
  5) installs the Wizer binary; `--plain` the reactor; both may be
  installed, the snapshot wins at resolution. An install needs the
  `add` grant on `/opt/bin` (ADR 084).
- **The `python` program kind** in spec 169's table: names `python3`,
  `python`; forms `-c code`, `-m module`, `-I`, `-u`, `script args`,
  stdin as `sys.stdin`; the guest suffix `.py` resolves to it (ADR
  082 pin 10's order: `.wasm`, then guest suffixes, then none).
  `python3 --version` prints the real version, the build date and
  the package set from the manifest, which the install stores as a
  row beside the binary. `pip`, `uv` and `python3 -m pip` are
  `unsupported` with the host-side hint (ADR 082 pin 4).
- **An import outside the set** (`import scipy`, `import matplotlib`)
  is a `ModuleNotFoundError` in the guest whose message names the set
  and the install command; the stage carries one `unsupported` error
  naming the module so the shell's verdict is classified, not a bare
  traceback.

## 3. The host, extended (over spec 169b)

- **The reactor entry.** The program row's kind says `entry=
  vfs_run`: the host calls no `_start`; for the plain reactor it
  calls `_initialize` then `vfs_run`, for the snapshot `vfs_run`
  alone. `vfs_run` reads argv through the WASI args calls and the
  environment through the WASI env calls on every call (the spike's
  `vfs_main.c` left `sys.argv` unset and `os.environ` empty after a
  snapshot; this spec sets both per call), runs `-c`, `-m` or the
  script, flushes Python's `sys.stdout` and `sys.stderr`, and
  returns the exit code, which the host records before any trap.
- **The snapshot's preopen** is `/`, the shim's one preopen, baked at
  snapshot time; the host asserts the module's preopen table matches
  before the first run and refuses the binary otherwise.
- **The staged-buffer cache.** The shim keeps the staged bytes of an
  unchanged row across opens within a run, keyed by `(path, version)`
  from the `read` that staged it, invalidated by the run's own writes
  to that path. The spike measured `import numpy` through the zip
  row at 1,890 ms with 256 re-stagings and 338 ms with the cache plus
  a bytecode zip; the snapshot makes the first import moot and the
  cache serves everything imported after it. Budgeted by
  `STAGING_BYTE_BUDGET` like any staged buffer.
  `[NEEDS CLARIFICATION: bytecode-only zip (faster imports, 5.9 MB
  deflated) or source zip (3.5 MB); leaning bytecode.]`
- **The door import** (§4) is bound beside the preview1 imports with
  `Linker.define_func`; a binary importing any other module than
  `wasi_snapshot_preview1` and `host` is refused at load with
  `unsupported` naming the import.
- Everything else is spec 169b unchanged: whole-file staging, the
  errno table, the epoch deadline (124), the memory limit (137), a
  guest abort (134), fuel, the content-hash cache, one guest per
  process, `/.vfs` hidden from the guest, the ladder as errno.

## 4. The `vfs` door

- **In the guest:** `wasi_python`'s neutral door, a C module
  compiled into the interpreter exposing one function,
  `_host.call(frame: bytes) -> bytes`, over one custom import
  `host::call(ptr, len, out_ptr_ptr, out_len_ptr) -> i32` with
  the two-step response (the guest allocates, the host writes) that
  bashkit uses for HTTP. A pure-Python package `vfs` in the zip
  wraps it: `vfs.read(path)`, `vfs.write(path, content)`, `vfs.ls`,
  `vfs.glob`, `vfs.grep`, and the rest of the verb table, each
  building a request frame and decoding a `Result`.
- **On the host:** the frame is the `Result` wire of spec 171's
  adapter (verb name plus JSON arguments in, the `ResultPayload`
  out), executed through the call's bound `Fs` (ADR 082 pin 2: the
  caller's authority, every gate fires). The door never raises
  through the trampoline: a refused call is a classified `Result`
  the guest decodes; a host fault returns a frame with
  `vfs.internal` and the stage records it.
- **Budgets:** every door call counts toward `VERB_CALL_BUDGET`; the
  frame size toward `STAGING_BYTE_BUDGET`.
- The verb door and the preview1 file calls are the only two ways
  out of the guest; both are gated by the same authority.

## 5. The documented semantics

The agent-facing reference (`docs/reference/shell.md`'s Python
section) states: the package set and versions; numpy's default
integer is 32-bit on wasm32 and `arange(1_000_000).sum()` wraps
(use `dtype=np.int64`); no threads, no `ctypes`, no `mmap`, no
sockets, no `multiprocessing`; kernels run single-threaded without
SIMD or BLAS at roughly 1.3 to 2.3 times native; on the SDK-24 line
a C++ `throw` inside numpy's FFT aborts the run with exit 134
(absent on the SDK-33 line). `python3 --version` carries the same
facts in one line.

## 6. QuickJS

- The `quickjs` program kind: `node`, `js`; a wasm guest built from
  QuickJS-NG under the same host and the same door (`host::call`),
  with a module loader serving `.js` entries from the index, the
  interrupt import for the deadline, and a 64 MB heap cap; exit
  codes recorded before raising. `[NEEDS CLARIFICATION: QuickJS-NG
  built as a wasm artifact by the same yearly workflow (lean), or the
  quickjs-rs shape as a native dependency; study 05 measured the
  native shape only.]`

## Scope

In: the above. Out: matplotlib (second build, gated on the SDK-33
line, with freetype, libpng, qhull, kiwisolver, contourpy, Pillow as
further archives; two to four weeks); scipy (f2c-translated Fortran
and OpenBLAS; a quarter; not scheduled); threads and `wasi-threads`;
BLAS and SIMD; `_ctypes`, `mmap`, `_sqlite3`, bz2, lzma, `_ssl` and
sockets; pip inside the guest; network; Pyodide; Monty; a native
sidecar; the 9P server; the bridge.

## Slices

- **172a — the build.** Moved out to `wasi_python` (amended
  2026-10-16). What remains here: the `vfs-py[python]` extra, the pin
  and its hash in the lockfile, and the consumer gate.
- **172b — the install and the kind.** The install command, the
  rows under `/opt`, the `python` kind and its forms, `--version`,
  the refusals.
- **172c — the host extension and the door.** The reactor entry, the
  per-call argv and env, the staged-buffer cache, the `host::call`
  import, the guest `_vfs` module and the `vfs` package, the frame
  wire.
- **172d — QuickJS and the docs.** The `quickjs` kind, the reference
  section, the test fixtures as `slow` tests.

## Acceptance criteria (counted; the numbers are the spike's)

1. `python3 -c "import numpy; print(numpy.__version__)"` runs under
   the shim with zero `path_open` of any `.so`, zero host preopens
   beyond the vfs root, and `numpy.__spec__.origin == 'built-in'`.
2. The numpy CSV job (`loadtxt` from a row, `savetxt` to a row) on
   the snapshot completes with exit 0 in at most 36 verbs and 209
   SQL statements; the written row is text with the declared bytes.
3. The pandas CSV job (`read_csv`, `groupby`, `to_csv`, read back,
   a 1e6-row groupby) on the snapshot completes with exit 0 in at
   most 15 verbs and 93 SQL statements; the groupby total matches
   native pandas.
4. Both `numpy.random` APIs (legacy and `Generator`) run the probe
   (`seed/rand/binomial/randint/normal/poisson/multinomial`) without
   a trap.
5. `import csv, decimal` after the snapshot imports from the zip row
   in at most 2 reads; with the staged-buffer cache a second import
   of any module in the same run issues zero reads.
6. `vfs.read`, `vfs.write` and `vfs.ls` from guest code round-trip
   through the door; a `vfs.write` to a path the caller cannot write
   returns a `permission_denied` `Result` in the guest and the stage
   carries the error even when the script exits 0.
7. A `.py` script writing to a path the caller cannot write gets the
   errno on close and the stage carries `permission_denied` even
   when the program exits 0.
8. A spinning script is killed with `timeout` (124); one exceeding
   memory with `budget_exhausted` (137); one exceeding
   `VERB_CALL_BUDGET` through the door likewise.
9. `python3 -c "import scipy"` reports `unsupported` naming the
   module and the package set; `python3 -m pip install x` reports
   `unsupported` with the host-side hint.
10. `sys.argv` and `os.environ` inside a snapshot run reflect that
    call's argv and the shell's env, not the snapshot's.
11. The workflow's zero-patch gate fails on a one-byte change to any
    source tree; the manifest hash matches the installed rows.
12. `node -e 'vfs.ls("/")'` under QuickJS returns rows; a runaway
    loop is interrupted.
13. `scripts/ci.sh` green at 100%; the guest tests are `slow` and run
    on the engine legs.

## Landing notes

(Filled in on landing.)

## Appendix — the withdrawn forms (record only)

The 2026-10-15 draft of this spec was a native CPython sidecar: a
`vfs python install` of python-build-standalone plus a uv-locked
package set; a pool of warm interpreters; bubblewrap on Linux and
Seatbelt on macOS with generated policies; vfs reached either by a
9P2000 server (`experiments/s10/p9_server.py`, 380 lines, mounted by
Docker's Linux kernel with `CAP_SYS_ADMIN`) or by a user-space bridge
(an import hook and `open`/`os` replacements over a Unix socket; C-level
`fopen` not intercepted); Windows through WSL2 only. Study 12 then
executed the self-sandboxing subprocess (Landlock plus seccomp, 0.95 s
and 105 MB for the job; Seatbelt 0.64 s) and found its wall absent on
gVisor (Cloud Run gen1), Lambda's 5.10 kernel and Windows. Both forms
are withdrawn by ADR 086. The 9P server and its per-operation cost
tables stay in `experiments/s10/` and study 11 §B as a possible second
transport for hosts that can mount; nothing in this spec depends on
them.

## Rebase notes of 2026-10-24 (ADR 087 and specs 174–181)

ADR 087 and the eight specs cut from it touch the guest's door and
the mount provider in the places below. Each note names the owning
spec; nothing is built. Spec 169b narrows to generic WebAssembly
programs, as the 2026-10-23 wasi-python memo says.

- **Close-time write-back carries a precondition (174).** Every
  write-back passes `if_version=` from the open-time `read`, or
  `if_absent=True` when the open found no row. A `conflict` maps to
  errno `STALE` (spec 169 §b7 already does) and an `exists` to
  `EEXIST`. A pure `O_APPEND` descriptor flushes as `append=True`.
  Spec 169's criterion 8 changes: a same-bytes reinstall now reports
  `unchanged` and no longer advances the version.
- **Integrity (175).** A guest read of a damaged body fails with
  `EIO`. The write-back can key its cache on the returned
  `content_hash` without a `stat`.
- **Paging (176).** The guest's `vfs.ls` passes `after` and `limit`
  through; the provider's `list` drains pages; spec 169 §b4's
  `O_DIRECTORY` drains `ls` pages.
- **Ranges (178, 179).** Whole-file staging stays at v1. A ranged
  `fd_read` waits on wasi-python's mount protocol growing a ranged
  provider call, which is that project's decision; once it exists, the
  provider uses `read_range` where the mount declares the feature.
- **Features (179).** The write-back is refused on a mount without the
  `write_preconditions` feature.
- **The staged-buffer cache keys by `entry_id` (181),** fetched in the
  same open-time read; `(path, version)` repeats after a rename or a
  sweep. Pack never changes a version's text, so `(entry_id, version)`
  stays a valid key (180).
