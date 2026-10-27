# 13 — Spike: a static WASI CPython with numpy (and pandas) compiled in, run over vfs

- **Date:** 2026-10-16. **Researcher:** s12 (one agent, spec 173). **Wall clock:** about 65 minutes of agent effort from the first download to the last number, inside a two-day box.
- **Everything executed lives in** `experiments/s12/` — scripts (`scripts/`), the cross files and C sources (`cross/`), fixtures, the shim as used (`shim/run_vfs.py`, which imports `experiments/s4/shim.py` unchanged), and raw outputs (`outputs/*.txt|json|log`). Build trees, downloads and every artifact over a few MB are git-ignored (`experiments/s12/.gitignore`); `downloads/SHA256SUMS` pins every download.
- **Sources built (pinned, hashed in `downloads/SHA256SUMS`):** CPython 3.14.8 (python.org tarball, sha256 `c2215904…`), numpy 2.5.2 (PyPI sdist, `d482d171…`), pandas 3.0.6 (PyPI sdist, `66b07ef7…`), zlib 1.3.1 (`9a93b2b7…`), wasi-sdk 24.0 arm64-macos (`aeae9993…`, clang 18.1.2), wasi-sdk 33.0 arm64-macos (`85c997a2…`, clang 22.1.0; used only for the exception probe), wasmtime 49.0.3 CLI (`d7708ba1…`), wizer 11.0.3 (`7c54896b…`), Brett Cannon's `python-3.14.7-wasi_sdk-24.zip` (`2e064d3f…`). Build helpers in a separate uv venv (`experiments/s12/.venv-build`: Cython 3.3.0, meson 1.12.1, ninja 1.13.2, versioneer 0.29) and in a `--target` dir for the build-python (Cython 3.3.0, versioneer). wasmtime-py 49.0.0 through `uv run --with wasmtime`.
- **Clones read (read-only, never modified):** `cpython` @ fdec4df (main is 3.16.0a1+dev; its `Platforms/WASI/*` build driver and `Modules/makesetup`, `Python/import.c`, `Modules/getpath.py` were READ; the clone has no release tags, so the pinned 3.14.8 tarball was built instead — the clone stayed clean), `numpy` @ 913c140 (`git show v2.5.2:…` for pyproject and meson files), `pyodide` @ adc5b63 (numpy recipe; the other recipes have moved to `pyodide/pyodide-recipes`, read via the GitHub API at 01bd0af, 2026-10-02, MPL-2.0), `cpython-wasi-build` (release list via `gh`).
- **Evidence labels:** EXECUTED (ran here, output file named), READ (source or docs read, cited), INFERRED (my reasoning from the two).
- **Machine (benchmark facts only):** Apple arm64, 10 cores, 32 GB, macOS 26.5.2; native comparison CPython 3.13.11 with pip numpy 2.4.2 and pandas 3.0.5.

## Summary

Yes, all of it builds and runs, in about an hour, with **zero patches to CPython, numpy or pandas**. A statically linked `python.wasm` for `wasm32-wasip1` with numpy 2.5.2 compiled in as builtin modules runs `import numpy` under vfs's preview1 shim with no `dlopen`, no `.so` and no host filesystem; `numpy.loadtxt` reads a CSV from a vfs row and `savetxt` writes one back. The stretch landed too: pandas 3.0.6 (45 Cython/C++ modules) compiled in the same way, `read_csv` from a row, `groupby`, `to_csv` to a row, and a 1e6-row `groupby` at 1.3–1.9× native. The verb door is proven: a ten-line C module calls a custom wasm import `vfs.ping` that the shim binds with `Linker.define_func`. Wizer takes the binary once the entry point is a WASI reactor: a snapshot with numpy pre-imported starts in **3 ms** per call (plain `_start` with numpy: 119 ms for `pass`, 1,890 ms for `import numpy`), and the full numpy+pandas snapshot starts in **4.8 ms** and runs the whole CSV job in 120 ms with 15 verbs. The adaptations are build-recipe files (two meson cross files, a 40-line compiler wrapper that turns each extension module's shared link into a static archive, two rename headers for symbols that only collide in a static link, a C++-exception stub, a reactor `main`, a `Setup.local`, two one-function stand-ins for `ctypes` and `mmap`). What did not work, plainly: the WASI SDK that CPython 3.14 pins (24) cannot link C++ exceptions, so a `throw` aborts the interpreter (wasi-sdk 33 fixes this, EXECUTED); numpy's default integer is 32-bit on wasm32, so `arange(1e6).sum()` silently wraps; `zipimport` reopens the stdlib zip for every module and the shim re-stages the whole row each time, which is most of the plain-binary import cost and is a shim design item, not a build item.

## Go/no-go table (questions 1–7 of spec 173)

| # | Question | Verdict | Evidence |
|---|---|---|---|
| 1 | CPython builds statically for wasm32-wasip1 from its own `Tools/wasm/wasi` driver with a pinned WASI SDK, reproducing Brett's build | **GO** | EXECUTED: 3.14.8 + wasi-sdk 24 → `python.wasm` 30,654,510 B in 2 min 20 s (both Pythons); Brett's 3.14.7 is 30,522,756 B; both ran study 04's script over vfs with identical counts (86 verbs, 479 SQL, 414 preview1 calls). `outputs/02_build_cpython_floor.log`, `03_floor_study04.*`, `03_brett_study04.*` |
| 2 | numpy compiles for wasm32-wasip1 as static archives and links into `python.wasm` as builtins so `import numpy` needs no `dlopen`; patches small? | **GO** | EXECUTED: 19 module archives (13.5 MB) in 16.7 s wall; linked through `Modules/Setup.local`; **zero source patches** — a cross file, a compiler wrapper, one rename header (66 `#define`s), one C++ stub, one link flag (`-lc-printscan-long-double`). `outputs/05_*`, `06_*`, `08_import_numpy.*` |
| 3 | Runs under vfs's preview1 shim: `import numpy; arange(10).sum()`, a CSV read from a vfs row with numpy's loader; verb / preview1 / SQL counts | **GO** | EXECUTED: `import numpy` → `2.5.2`, origin `built-in`, 0 opens of any `.so`, 0 host preopens; `arange(10).sum()` → 45. The job: 344 verbs (read 279, stat 62, mkdir 1, write 2), 2,064 preview1 calls, 1,749 SQL. With the Wizer snapshot: 36 verbs, 184 preview1 calls, 209 SQL. `outputs/10_job_numpy.*`, `14_wizer_job.*` |
| 4 | Stretch: pandas builds the same way; `read_csv` from a row and `to_csv` back | **GO** | EXECUTED: 45 archives (21.7 MB) in 31 s wall; the job prints the grouped table, writes `/out/summary.csv` (128 B row), reads it back; 1e6-row groupby 9.2 ms. Needed: a 3-line rename header, zlib linked in, one-function stand-ins for `ctypes` and `mmap`. `outputs/21_job_pandas.*`, `25_pandas_wizer_job.*` |
| 5 | matplotlib and scipy: estimates with the one deciding fact each | **estimated** | matplotlib: **C++ exceptions** — wasi-sdk 24 cannot link `-fwasm-exceptions` (EXECUTED), wasi-sdk 33's sysroot can and wasmtime 49 runs the result (EXECUTED, `build/hello/throw_probe_eh33.wasm`); Agg/ft2font throw on font errors, so SDK ≥ 33 (CPython 3.15's pin) is the gate, plus freetype/libpng/qhull builds. scipy: **no Fortran compiler for wasm** — Pyodide translates with f2c and hand-patches ABI (READ, recipe cited below); months. |
| 6 | Numbers: sizes, cwasm, cold start with/without Wizer, memory, speed ratios | **measured** | Table below. Headline: numpy snapshot 50.6 MB (11.2 MB xz), 3 ms per call; plain `import numpy` 1,890 ms; `arange(1e6).sum()` 2.3× native; pandas groupby 1.4× native. |
| 7 | The `vfs` verb door: a C extension compiled in that calls a custom wasm import | **GO** | EXECUTED: `vfs.ping(21)` → 43 in the guest, host saw `[21]`; the module is 30 lines of C (`cross/vfsmodule.c`), bound with `linker.define_func("vfs", "ping", …)` in `shim/run_vfs.py`. `outputs/08_import_numpy.json` (`vfs_ping_calls`) |

Acceptance (spec 173): (1) `import numpy; print(numpy.__version__)` under the shim with zero `dlopen` and zero host-filesystem access — **met** (`outputs/08_import_numpy.json`: `path_open` trace has 88 opens, none of a `.so`; the only stubbed preview1 function ever called by the plain binary is `path_readlink`, none by the snapshot; the shim never preopens a host directory — `InMemoryStorage` only). (2) CSV round trip with declared verb counts — **met**, and the PNG step is estimated with the blocking fact named (question 5). (3) Every number has a command and an output file — the executed log below names them. (4) The pipeline plan names every pinned version and every recipe file.

## Findings

### 1. The floor reproduces (EXECUTED)

`scripts/02_build_cpython_floor.sh` runs `python Tools/wasm/wasi build` from the 3.14.8 tarball with `WASI_SDK_PATH` and the wasmtime CLI on `PATH`. Output: `cross-build/wasm32-wasip1/python.wasm`, 30,654,510 bytes, sha256 `44f97ec0…`; `python.sh --version` → `Python 3.14.8`. Wall 2 min 19.75 s for the build-Python and the WASI Python together (`outputs/02_build_cpython_floor.log`).

Under the shim (`shim/run_vfs.py`), the stdlib is a **vfs row** at `/usr/local/lib/python314.zip` and argv0 is `/usr/local/bin/python.wasm`; `getpath` finds the prefix through the zip landmark (READ: `Modules/getpath.py` searches `lib/python314.zip` up from the executable dir; EXECUTED: `sys.prefix == '/usr/local'`, `sys.path == ['/usr/local/lib/python314.zip', '/usr/local/lib/python3.14', '…/lib-dynload']`). Study 04's script (read a row, write a row, listdir, stat, mkdir, rename, remove, rmdir) ran to exit 0 on our binary and on Brett's with the same counts: verbs read 49, stat 31, write 1, ls 1, mkdir 1, move 1, delete 2; 479 SQL statements; 414 preview1 calls; 79 builtin modules (`outputs/03_floor_study04.txt`, `03_brett_study04.txt`).

One false start, kept as a finding: the first zip was DEFLATE-compressed and `zipimport` died with `can't decompress data; zlib not available` — wasi-sdk ships no zlib and the WASI CPython has no `zlib` module (study 11 saw the same gap). The zip is therefore STORED (9.77 MB for the stdlib) until finding 9 links zlib in.

### 2. numpy as builtins: the design that worked, and why no patch was needed (EXECUTED, READ)

Three READ facts shaped the recipe (`cross/wasi-numpy.cross`, `scripts/wasi-cc`, `scripts/python-wasi-cross`, `cross/vfsmodule.c`, `scripts/04_link_python_numpy.sh`):

- `Python/import.c` `is_builtin()` compares the **full dotted import name** against `PyImport_Inittab` (`_PyUnicode_EqualToASCIIString(name, inittab[i].name)`), and `BuiltinImporter.find_spec` ignores the package path. So `PyImport_AppendInittab("numpy._core._multiarray_umath", PyInit__multiarray_umath)` makes `from . import _multiarray_umath` inside the `numpy._core` package resolve to a builtin. EXECUTED: `_multiarray_umath.__spec__.origin == 'built-in'`, `sys.builtin_module_names` grew from 79 to 93.
- `Modules/makesetup` accepts `*.a` tokens as libraries and bare `*.c` names as sources under `$(srcdir)/Modules/`, so a single `Setup.local` line links any number of archives — but it mangles absolute source paths (`Modules//Users/…/vfsmodule.o`), so the two C files are copied into the scratch tree's `Modules/`. `configure` copies the source tree's `Setup.local` into the build dir and `make` reads the **build-dir** copy; my first two relinks silently changed nothing because I wrote the wrong one (the pipeline script writes the build-dir copy).
- `PyImport_AppendInittab` must run before `Py_Initialize`; a `__attribute__((constructor))` in a C file linked into `libpython` runs from `__wasm_call_ctors` before `main`, so **no change to `Programs/python.c`** is needed. The constructor is made idempotent for the snapshot case (finding 7).

The meson side (numpy's vendored meson 1.11.1, READ: `vendored-meson/meson/mesonbuild/scripts/python_info.py` introspects the target Python through `sysconfig.get_config_vars()`):

- `scripts/python-wasi-cross` is the native build-Python with `_PYTHON_SYSCONFIGDATA_NAME=_sysconfigdata__wasi_wasm32-wasi`, `_PYTHON_SYSCONFIGDATA_PATH=<wasi build>/build/lib.wasi-wasm32-3.14` and `_PYTHON_HOST_PLATFORM=wasi-wasm32-wasi` — the same trick CPython's own Makefile uses for `PYTHON_FOR_BUILD` (READ: `cross-build/wasm32-wasip1/Makefile` line 425). EXECUTED: it reports `EXT_SUFFIX .cpython-314-wasm32-wasi.so`, the WASI include dir and the wasi-sdk `CC` (`outputs/04_python_wasi_cross.txt`).
- `scripts/wasi-cc` / `wasi-cxx` wrap wasi-sdk clang: they drop `-fPIC` (the objects link statically), drop `-Wl,--start-group`/`--end-group` (wasm-ld has no archive groups; the first `meson setup` failed its libm check on exactly that), and when meson links an extension module (`-shared -o X.so`) they write `X.so` as an **`ar` archive of the module's objects** plus `X.so.deps` naming the static libs it links with. numpy's `meson.build` is untouched; `py.extension_module` still believes it made shared modules.
- Cross file properties: `longdouble_format = 'IEEE_QUAD_LE'` (numpy cannot run its probe binary; `sizeof(long double) == 16` EXECUTED in `fixtures/hello.c`), `needs_exe_wrapper`, `-Dallow-noblas=true -Dblas=none -Dlapack=none -Ddisable-optimization=true -Ddisable-threading=true -Ddisable-highway=true -Ddisable-intel-sort=true -Ddisable-svml=true`, `-DNPY_NO_SIGNAL`, the three `_WASI_EMULATED_*` defines. numpy's `meson_cpu` already lists `wasm32` as a family with no features (READ: `meson_cpu/meson.build:106,122`; EXECUTED: "Disabling CPU feature detection due to unsupported architecture: wasm32").

Build facts: `meson setup` + `ninja` compiled 331 steps; **16.7 s wall, 1 min 46 s user** on ten cores (`outputs/05_numpy_build.log`). 19 archives, 13,501,368 bytes in all; `_multiarray_umath` 4.66 MB, `lapack_lite` 2.67 MB, `_umath_linalg` 2.80 MB (`outputs/05_numpy_archives.txt`). Linking 13 non-test modules (the `*_tests` and `_simd` modules are left out) into `python.wasm`: 6.4 s; the binary grew from 30,654,510 to 39,551,987 bytes (`outputs/23_sizes.txt`).

### 3. The three things that actually broke in the numpy build, and their fixes (EXECUTED)

1. **C++ exceptions in pocketfft.** `numpy/fft/pocketfft/pocketfft_hdronly.h` uses `throw`; with `-fno-exceptions` it does not compile, with `-fexceptions` clang emits calls to `__cxa_allocate_exception`/`__cxa_throw` and compiles `catch` away, and wasi-sdk 24's `libc++abi.a` defines neither symbol (EXECUTED with `fixtures/throw_probe.cpp`: `undefined symbol: __cxa_allocate_exception`). Fix: `cross/cxa_stubs.c`, ten lines, `__cxa_allocate_exception → malloc`, `__cxa_throw → report and abort()`. A C++ throw therefore traps the guest instead of unwinding. pocketfft throws only on plan sizes numpy validates first. The DSPy-wasm PR cited in study 12 hit the same wall and did the same ("weak report-and-terminate archive"). Finding 10 shows wasi-sdk 33 removes the wall.
2. **`long double` parsing.** `import numpy` trapped in `npy_longdouble_from_PyLong → strtold → long_double_not_supported → abort`, with wasi-libc's message "add -lc-printscan-long-double to the link command". That is a wasi-libc build variant, selected by a link flag; the `Setup.local` line carries `-lc-printscan-long-double`. After it: `numpy.longdouble(1)/3` prints 34 digits and `finfo(longdouble).bits == 128` (`outputs/08_import_numpy.txt`).
3. **A symbol clash that only exists in a static link.** numpy compiles `random/src/distributions/distributions.c` twice: into `libnpyrandom` (`RAND_INT_TYPE = int64_t`) and into `mtrand` with `-DNP_RANDOM_LEGACY=1` (`RAND_INT_TYPE = long`, 32-bit on wasm32). As shared objects they never meet; in one `python.wasm` the linker keeps one copy and warns once (`function signature mismatch: random_multinomial`), and `Generator.poisson` trapped with `indirect call type mismatch` because `_common.disc` called a pointer typed `int64 (*)(bitgen_t*, double)` that resolved to `mtrand`'s `i32` copy (`outputs/15_random_probe.json`, first run). 66 function names are shared (`outputs/15_shared_random_symbols.txt`). Fix: `cross/npy_random_legacy_rename.h`, injected with `-include` into every TU but active only `#ifdef NP_RANDOM_LEGACY`, prefixes the 66 names in `mtrand`'s private copy. After it, legacy (`np.random.seed/rand/binomial/randint/normal/poisson/multinomial`) and `Generator` (`random/binomial/integers/normal/poisson/choice/multinomial`) all run (`outputs/15_random_probe.json`). INFERRED: any package that builds one C file twice with different ABI macros will show the same class of clash under static linking; the linker warning is the detector, and a per-TU rename header is the fix shape.

Everything else compiled unaided: `-DNPY_NO_SIGNAL`, `-Ddisable-threading` (a harmless `NPY_BEGIN_THREADS_DESCR` macro-redefinition warning), `madvise`/`backtrace`/`dlfcn.h` probes answered "no" by meson, `complex long double` sizes (32 bytes) accepted.

### 4. Running the job over vfs: the counts and what they mean (EXECUTED)

`fixtures/job_numpy.py` makes `/out`, loads `/data/sales.csv` (36 rows, three regions, written as a vfs row from `fixtures/sales.csv`) twice with `np.loadtxt` (numeric columns and the string column), groups by region, and `np.savetxt`s a summary to `/out/summary.csv`, then reads it back. `outputs/10_job_numpy.json`:

| run | exit | verbs | preview1 calls | SQL | bytes to guest | guest memory | wall |
|---|---|---|---|---|---|---|---|
| plain `_start`, stdlib+numpy zip (13.5 MB, stored) | 0 | 344 (read 279, stat 62, mkdir 1, write 2) | 2,064 | 1,749 (read 1,395, stat 310, mkdir 12, write 32) | 36.3 MB | 40.0 MiB | 2.18 s |
| Wizer snapshot (numpy pre-imported), `vfs_run` | 0 | 36 (read 22, stat 11, mkdir 1, write 2) | 184 | 209 | — | 40.0 MiB | 0.21 s |

The written row: `/out/summary.csv`, 79 bytes, text (`content`, no `data`), `size_bytes 79`; the values match the in-guest print. Zero `.so` opens; the only stub hit by the plain binary is `path_readlink` (CPython resolving its own executable, NOSYS is harmless, same as study 04). One lesson for the shim: `np.savetxt` → `open(path, 'wt')` → `fd_close` → `fs.write` **without `parents`**, so a missing `/out` surfaces as `FileNotFoundError` at close; the program creates its directory (as any program would), and the shim could offer `parents=True` on create-opens as a policy.

**Where the 279 reads come from (INFERRED from the trace, then measured):** `zipimport` reopens the archive for every module it loads (`_get_data` → `open(archive)`), and the s4 shim stages the whole row on every `path_open`, so a 13.5 MB row is fetched 256 times for `import numpy` — 1,395 SQL statements and roughly 3.5 GB of host-side byte copies. The guest itself only pulls 36 MB through `fd_read`. The benchmark in finding 8 isolates this: a host-side cache of the zip row by (path, version) cuts `import numpy` from 1,890 ms to 1,063 ms, a bytecode-only zip cuts it to 1,213 ms, both together to **338 ms**, and the Wizer snapshot to 3 ms. The design consequence is for spec 167/172, not for this build: the staged buffer of an unchanged row should be reusable across opens (keyed by the row version the `read` already returns), or the stdlib zip should live inside the binary (wasi-vfs, as the WLR build did) — or both.

### 5. The verb door is a 30-line C module (EXECUTED)

`cross/vfsmodule.c` declares `__attribute__((import_module("vfs"), import_name("ping"))) extern int32_t vfs_host_ping(int32_t)`, exposes `vfs.ping(n)`, and is a line in `Setup.local`. The module's imports become `['vfs', 'wasi_snapshot_preview1']` (EXECUTED: `outputs/13_vfsmain_plain.json` run; the plain python.wasm's import list was checked the same way). `shim/run_vfs.py` binds it: `linker.define_func("vfs", "ping", imp.type, ping)` where `ping` returns `2n+1` and records the call. In the guest `vfs.ping(21)` → 43; on the host `vfs_ping_calls == [21]`. Everything study 05 said about door (i) holds: a named host function from CPython-WASI needs a C shim in the guest and is then an ordinary `define_func`; the shim already has the trampoline hazard notes (study 05 §4) — this door never raises through the trampoline, it returns an `i32`.

INFERRED for spec 172: the real door is one import per verb or one generic import (`vfs.call(ptr, len) -> (ptr, len)` with JSON or the `Result` wire), length-prefixed, with the same two-step response pattern bashkit uses for HTTP. The 30 lines become perhaps 150, plus a pure-Python `vfs` package on top of the C module.

### 6. pandas (the stretch) built in 31 seconds and needed five small things (EXECUTED)

`scripts/07_pandas_build.sh` with `cross/wasi-pandas.cross` (the numpy cross file with a different rename header) and the same wrapper: 55 targets, 151 ninja steps, **31.2 s wall, 3 min 19 s user**; 45 module archives, 21,667,082 bytes (`outputs/12_pandas_build.log`, `19_pandas_archives.txt`). pandas' `meson.build` is untouched. What it needed:

1. **A host-side numpy stand-in.** pandas' meson asks the target Python for `numpy.get_include()` and Cython needs numpy's `.pxd` files; the build-Python has no numpy and must not get a native one (its `_numpyconfig.h` would say `sizeof(long double) == 8`). `build/numpy-host-shim/numpy/__init__.py` is four lines (`get_include()` → an include dir assembled from numpy's sdist headers plus the three WASI-generated ones: `_numpyconfig.h`, `__multiarray_api.h`, `__ufunc_api.h`, with `NPY_SIZEOF_LONGDOUBLE 16`). Pyodide's recipe lists exactly those generated headers as its `cross-build-files` (READ, `pyodide:packages/numpy/meta.yaml`).
2. **Cython and versioneer visible to the build-Python** (`uv pip install --target build/host-pylib`; `pandas/generate_pxi.py` runs under the cross-file Python, and `Cython.Tempita` comes from the Cython wheel).
3. **Three duplicate symbols** — pandas vendors numpy's `np_datetime.c` (`is_leapyear`, `add_minutes_to_datetimestruct`, `get_datetimestruct_days`) under numpy's names; `cross/pandas_rename.h` prefixes pandas' copies. Same class as finding 3.3, detected by `wasm-ld: duplicate symbol`.
4. **`_cyutility`**, Cython 3.1+'s shared utility module, is built at the pandas build root but imported as `pandas._libs._cyutility`; `scripts/gen_inittab.py` (which now generates `cross/vfs_inittab.c` for all 58 numpy+pandas modules from the archive paths) special-cases it.
5. **Two stdlib modules pandas imports unconditionally that CPython-WASI does not have**: `ctypes` (`pandas/errors/__init__.py:8`, used only for `ctypes.WinError()` on Windows at line 807) and `mmap` (`pandas/io/common.py:27`, used only for `read_csv(memory_map=True)`). The spike ships one-function stand-ins in the zip (`cross/ctypes_stub.py`, `cross/mmap_stub.py`) and leaves the stdlib `ctypes` package out of the zip. Upstream, each is a one-line `try/except ImportError` — the honest patch candidates of this spike, both in pandas, neither applied here.

And one thing it needed from the interpreter: **zlib**. `pandas._libs.tslibs.timezones` imports dateutil, whose `zoneinfo` opens its bundled `dateutil-zoneinfo.tar.gz` through `tarfile` → `gzip module is not available` (`outputs/21_job_pandas.json`, third run). `scripts/09_build_zlib.sh` builds zlib 1.3.1 with wasi-sdk 24 (its `configure` substitutes `libtool` for the archiver on Darwin hosts, so `AR`/`ARFLAGS` go on the `make` line — the first archive was 96 bytes), and `Setup.local` gains `zlib zlibmodule.c -I… libz.a`. With zlib in, the **deflated** zip works: stdlib + numpy + pandas + dateutil + tzdata + six + the WASI `_sysconfigdata` (pandas' `compat` reads `sysconfig.get_config_var("HOST_GNU_TYPE")`) is **6,050,752 bytes** deflated versus 22,974,310 stored.

The job (`fixtures/job_pandas.py`: `read_csv('/data/sales.csv')`, `groupby('region')['sales'].agg(['sum','mean','max'])`, `to_csv('/out/summary.csv')`, read it back, then a 1e6-row `groupby`), `outputs/21_job_pandas.json`:

| run | exit | verbs | preview1 | SQL | guest memory | wall |
|---|---|---|---|---|---|---|
| plain `_start`, deflated zip (6.05 MB) | 0 | 1,181 (read 937, stat 242, mkdir 1, write 1) | 6,855 | 5,923 | 108.1 MiB | 8.21 s |
| Wizer snapshot (numpy+pandas pre-imported), `vfs_run` | 0 | 15 (read 11, stat 2, mkdir 1, write 1) | 96 | 93 | 108.0 MiB | 0.12 s |

The written row is 128 bytes of text with the same numbers native pandas gives; the 1e6-row groupby totals match native to the millidigit (`total=500316.548`). The plain run's 8.2 s is, again, 937 re-stagings of the zip row (finding 4); the snapshot run is the honest cost of the work.

### 7. Wizer takes the binary once the entry point is a WASI reactor (EXECUTED)

Three attempts, each a finding:

1. CPython's own `main` (`Programs/python.c`) cannot be pre-initialized: Wizer runs only the named init function, not `__wasm_call_ctors`, so inside Wizer the inittab constructor had not run and `import numpy` failed; and after the snapshot `_start` runs the constructors **again** and `PyImport_AppendInittab` after `Py_Initialize` is a fatal error (`outputs/14_wizer_run.json`, first run).
2. Calling `__wasm_call_ctors()` from the init function and guarding our constructor fixed the init but not `_start`: the second constructor pass re-ran libc++'s static initializers and the exit path crashed in `__cxx_global_array_dtor` (out-of-bounds memory access).
3. **A reactor** (`-mexec-model=reactor`, `cross/vfs_main.c`, `scripts/08_build_vfsmain.sh`): the runtime's `_initialize` runs the constructors exactly once, `wizer.initialize` initializes the interpreter with `PyConfig_InitIsolatedConfig`, runs `VFS_PREIMPORT` (`import encodings, io, os, sys, json, csv, re, numpy[, pandas]`) and `gc.freeze()`; `vfs_run` is the per-call export — it reads argv through `__wasi_args_get`, honours `-c code` or a script path, and flushes Python's `sys.stdout` (the first snapshot printed nothing: `fflush` flushes C stdio, not `TextIOWrapper`). The same binary runs un-snapshotted with `--init` (`outputs/13_vfsmain_plain.json`). The link command is the one `make` printed with `Programs/python.o` swapped for `Modules/vfs_main.o`; exports become `['memory', '_initialize', 'wizer.initialize', 'vfs_run']`.

Two preopen facts that cost a run each: Wizer's `--mapdir` must map **`/`** (the shim's one preopen), not `/usr/local` — wasi-libc's preopen table is populated during `_initialize` and snapshotted, so `fopen('/data/x')` after a `/usr/local`-rooted snapshot sees no preopen for `/data` and fails. And `os.environ` is **empty** after the snapshot (the environment was read at init, inside Wizer) while `sys.argv` is `['']` (the spike's `vfs_run` does not set it) — both are small follow-ups in `vfs_main.c`, not blockers. Modules not pre-imported (`csv`, `decimal`) import fine after the snapshot through the zip row (2 reads).

Wizer itself: 2.7 s for the numpy binary, 8.3 s for the pandas one; the snapshot adds the live heap to the data segments: 39.5 → 50.6 MB (numpy), 55.4 → 94.5 MB (pandas). Memory at exit is unchanged (40 MiB numpy, 108 MiB pandas job), the snapshot baseline before any work is 61.5 MiB for the pandas binary.

### 8. The numbers (EXECUTED; wall-clock is a benchmark fact, never a test assertion)

**Sizes** (`outputs/23_sizes.txt`, `25_pandas_wizer_sha.txt`; xz = what a release download weighs, `xz -9`):

| artifact | `.wasm` bytes | xz | `.cwasm` (wasmtime 49, this CPU) | sha256 prefix |
|---|---|---|---|---|
| floor, Brett 3.14.7 / ours 3.14.8 | 30,522,756 / 30,654,510 | — | 16,452,384 / 16,472,344 | `d24bd98d` / `44f97ec0` |
| + numpy 2.5.2 (13 modules) + vfs door | 39,551,987 | 8,449,348 | 34,321,544 | `b81992cf` |
| + numpy, Wizer snapshot (reactor) | 50,635,154 | 11,204,068 | 55,388,896 | `24842851` |
| + numpy + pandas 3.0.6 (58 modules) + zlib | 55,218,012 | 9,849,184 | 67,894,744 | `b431d77b` |
| + numpy + pandas, Wizer snapshot | 94,501,599 | 19,673,684 | 110,614,640 | `0a074fde` |
| stdlib zip, stored / deflated | 9,771,926 / 3,485,996 (numpy incl.) | | | |
| stdlib + numpy zip, stored src / stored pyc / deflated pyc | 13,494,391 / 14,553,786 / 5,922,310 | | | |
| stdlib + numpy + pandas + deps zip, stored / deflated | 22,974,310 / 6,050,752 | | | |

Cranelift compile in-process (wasmtime-py 49, `Module.from_file`): 1.06–1.15 s for the 39.5 MB binary, 2.3–2.7 s for the 55–94 MB ones; `Module.deserialize_file` 5–100 ms. Host `maxrss` after an in-process compile: 735 MiB (numpy) to 1,474 MiB (pandas snapshot); with deserialization only, **178 MiB** (`outputs/18_bench_pyc.txt`). The `.cwasm` is bound to the wasmtime version and CPU features; a release ships the `.wasm` and compiles once per host into a cache.

**Cold start per call** (`scripts/bench_startup.py`, median of 10 in-process runs after one deserialize; the vfs store holds the zip row; `outputs/18_bench_*.txt`, `25_bench_pandas_wizer.txt`):

| binary and zip | `pass` | `print('hello')` | `import numpy` | verbs for `import numpy` |
|---|---|---|---|---|
| floor (Brett), stored src zip | 113.0 ms | 111.9 ms | n/a | — |
| numpy builtin, stored src zip | 118.6 ms | 117.7 ms | 1,889.6 ms | read 256, stat 49 |
| numpy builtin, stored **pyc** zip | 109.4 ms | 106.9 ms | 1,213.3 ms | same |
| numpy builtin, src zip + **host cache of the zip row** | 91.0 ms | 88.0 ms | 1,063.1 ms | same (0 SQL for the repeats) |
| numpy builtin, pyc zip + host cache | 77.7 ms | 77.5 ms | **338.4 ms** | same |
| numpy **Wizer snapshot**, `vfs_run` | **3.8 ms** | 3.2 ms | **3.0 ms** | none |
| numpy+pandas Wizer snapshot, `vfs_run` | 4.8 ms | 4.8 ms | 4.7 ms | none |

Study 05 measured 6 ms for bashkit's 3.14 snapshot and 29 ms for a plain `_start` on the 3.12 WLR build that embeds its stdlib; our plain 113–119 ms is the zip-as-a-row cost (14 reads and 21 stats for `pass`: the `getpath` landmark probes plus `encodings`/`site` imports through the row). INFERRED: embedding the zip or caching the row brings the plain binary to the 30 ms class; the snapshot makes the question moot.

**Speed ratios against native** (guest: `fixtures/bench_guest.py` in the plain numpy binary, `outputs/11_bench_guest.txt`; `fixtures/job_pandas.py` BENCH line; native: `scripts/bench_native.py`, `bench_native_pandas.py`, three runs, `outputs/09_bench_native.txt`, `22_bench_native_pandas.txt`; native numpy 2.4.2 and pandas 3.0.5 are the pip arm64 wheels with SIMD and Accelerate, the guest has no SIMD and lapack-lite):

| kernel | guest (wasm, wasmtime 49) | native (CPython 3.13.11) | ratio |
|---|---|---|---|
| `np.arange(1_000_000).sum()` (mean of 20) | 0.553 ms | 0.238 ms | **2.3×** |
| `np.sort` of 1e6 float64 | 72.4 ms | 36.5 ms | 2.0× |
| `(x*2+1).mean()` over 1e6 | 2.36 ms | 1.48 ms | 1.6× |
| `pd.DataFrame` build, 1e6 rows × 2 | 17.8 ms | 9.6 ms | 1.9× |
| `groupby('k')['v'].sum()`, 1e6 rows, 100 keys | 9.2 ms | 6.7 ms | **1.4×** |
| `groupby(...).agg(['mean','max','count'])` | 13.9 ms | 10.4 ms | 1.3× |

One semantic difference, found by the benchmark, not by a test: `np.arange(1_000_000).sum()` is **1,783,293,664 in the guest and 499,999,500,000 natively** — numpy's default integer is C `long`, which is 32 bits on wasm32, so the sum wrapped silently. Pyodide has the same behaviour (Emscripten is ILP32 too). This is a documented property of the platform, not a bug in the build, and it must be in the agent-facing docs (`dtype=np.int64` when it matters).

### 9. What zlib changed, and what it says about the stdlib's missing halves (EXECUTED, INFERRED)

With `zlib` built in: `gzip`, `tarfile` of `.tar.gz`, DEFLATE zips through `zipimport`, and `binascii.crc32` from zlib. The stdlib payload drops from 9.8 MB to 3.5 MB (13.5 → 3.5 with numpy; 23 → 6 with pandas). Study 11's list of absent C modules on WASI (`zlib`, `_bz2`, `_lzma`, `_hashlib`, `_ssl`, `_ctypes`, `mmap`, `_sqlite3`, `multiprocessing`) is now, by the same recipe shape, a list of libraries to build from pinned source and add as `Setup.local` lines: bz2 and xz are an afternoon each; sqlite is what bashkit did; `_ctypes` needs libffi, which has no wasm32-wasi port in the SDK — the `ctypes` stand-in stays; `mmap` has no preview1 equivalent — the stand-in stays; `_ssl`/sockets are out of scope by the no-network rule.

### 10. The two estimates: matplotlib and scipy (EXECUTED, READ, INFERRED)

**matplotlib — the deciding fact is C++ exceptions, and it has just been decided upstream.** Agg and `ft2font` are C++ that throws on error paths; Pyodide builds matplotlib 3.10.8 with `-fwasm-exceptions` and five patches (`0001-Disable-timer`, `0002-Hardcode-font-cache-path`, `0003-Pyodide-webagg-backend`, `0004-Fix-32bit-casting`, `0005-Use-system-freetype`), against Emscripten's `freetype-legacysjlj` port, with `contourpy`, `kiwisolver`, `Pillow`, `fonttools` as runtime deps (READ, `outputs/pyodide-recipes/matplotlib.meta.yaml`). On WASI: wasi-sdk 24 (CPython 3.14's pin) cannot link `-fwasm-exceptions` at all (EXECUTED: `undefined symbol: __cxa_throw, __wasm_lpad_context`), while **wasi-sdk 33's sysroot carries a second libc++ with exceptions** ("Build a sysroot that supports C++ exceptions by default", wasi-sdk PR #606, READ in the release notes; `CppExceptions.md` prescribes `-fwasm-exceptions -mllvm -wasm-use-legacy-eh=false` and `-lunwind`), and **it works**: `fixtures/throw_probe.cpp` throws and catches under the wasmtime 49 CLI and under wasmtime-py's default engine (EXECUTED, `build/hello/throw_probe_eh33.wasm`, 375,640 bytes). CPython 3.15 pins wasi-sdk 33; Brett's 3.15.0 release is built with it. So matplotlib is not reachable on the 3.14/SDK-24 line without the abort-on-throw stub (every font error would kill the interpreter), and is plausibly reachable on the 3.15/SDK-33 line. Beyond exceptions: freetype, libpng and qhull are plain C with CMake/autotools builds (days, same shape as zlib), `kiwisolver` is C++ (same recipe as numpy), Pillow is C with zlib/libjpeg (days), `contourpy` is C++. Estimate: **two to four weeks** for a first Agg-only matplotlib on the 3.15 line, with the `0004-Fix-32bit-casting` class of patch to re-derive for ILP32, plus a bundled font and a hardcoded font-cache path (Pyodide's `0002`).

**scipy — the deciding fact is Fortran, and the only wasm answer is f2c.** Pyodide's scipy 1.18.0 recipe clones `hoodmane/f2c`, exports `F2C_PATH`, applies five patches and some twenty `sed` rewrites that change Fortran-called C declarations from `void` to `int` (`outputs/pyodide-recipes/scipy.meta.yaml`), requires `libopenblas` and `libboost` as hosts and a `gfortran` "executable" that is their f2c driver, and pins `meson < 1.10`. Nothing in that is Emscripten-specific — f2c is C, OpenBLAS's LAPACK is Fortran that f2c handles — so the path exists for WASI, and it is **months**: OpenBLAS via f2c for wasm32-wasi (no SIMD kernels), scipy's own Fortran (fitpack, odrpack, arpack, propack, quadpack) through f2c with the ABI fixes re-derived against the WASI ABI, and C++ parts that need wasi-sdk 33's exceptions. Not a first-year item.

### 11. What this spike did not do (honest limits)

- No test suites ran: not CPython's, not numpy's (`numpy.test()` needs pytest and the `_tests` modules I left out), not pandas'. The evidence is the probes and the jobs above. The first release gate should run numpy's and pandas' own test subsets under the shim.
- No threads (`-Ddisable-threading`, no `wasi-threads` CPython); no BLAS (lapack-lite; `linalg.det` and friends work, slowly at scale); no SIMD (`-Ddisable-optimization`); C++ `throw` aborts on the SDK-24 build.
- The shim is the s4 research shim (whole-file staging, no staged-buffer cache); its costs dominate the plain-binary numbers and are a spec 167/172 design item.
- Built on arm64 macOS only; the CI plan below runs on Linux and must reproduce the hashes from the same pinned sources (the `.wasm` should be byte-identical given `SOURCE_DATE_EPOCH`, which CPython's driver already sets; not verified here).
- One wasmtime-py version (49.0.0); `.cwasm` files are not portable across versions.

## The executed log, step by step

Every command is in `experiments/s12/scripts/` and every output in `experiments/s12/outputs/`; this is the order they ran, with the one-line result.

1. `scripts/00_download.sh` → `outputs/00_download.log`, `downloads/SHA256SUMS`: seven downloads in parallel, hashes recorded; numpy's and pandas' match the PyPI JSON digests; Brett's zip matches the copy study 11 left in the scratchpad (`2e064d3f…`).
2. Toolchain unpacked under `build/tools/`; `fixtures/hello.c` → `build/hello/hello.wasm` (143,087 B); `uv run --with wasmtime python scripts/01_hello.py` → `hello from wasm32-wasip1, argc=2, sizeof(long double)=16` (`outputs/01_hello.txt`).
3. `scripts/02_build_cpython_floor.sh` → `python.wasm` 30,654,510 B, `Python 3.14.8`, 2 min 20 s (`outputs/02_build_cpython_floor.log`, `cpython-floor-logs/`).
4. `scripts/make_stdlib_zip.py` (STORED after the zlib false start) → `python314-src.zip` 9,771,926 B; Brett's `python314-brett-src.zip` 9,471,478 B (`outputs/zip_*.txt`).
5. `shim/run_vfs.py --script /data/study04_script.py` on ours and on Brett's → both exit 0, 86 verbs, 479 SQL, 414 preview1 (`outputs/03_floor_study04.*`, `03_brett_study04.*`).
6. `scripts/python-wasi-cross -c "import sysconfig…"` → `.cpython-314-wasm32-wasi.so`, WASI include dir (`outputs/04_python_wasi_cross.txt`).
7. `scripts/03_numpy_build.sh` (three runs: `--start-group` failure, `-fno-exceptions` failure, success) → 19 archives (`outputs/05_numpy_build.log`, `05_numpy_archives.txt`).
8. `scripts/04_link_python_numpy.sh` (five runs; the first two changed nothing — wrong `Setup.local`, absolute source paths — then `strtold`, then the idempotent constructor, then the random rename) → final `python-numpy.wasm` 39,551,987 B, `b81992cf…` (`outputs/06_link_numpy.log`, `06_make.log`).
9. `scripts/05_numpy_install_zip.sh` → `python314-numpy.zip` 13,494,391 B (`outputs/07_numpy_zip.log`).
10. `shim/run_vfs.py -c "import sys, vfs … import numpy …"` → `ping: 43`, `numpy 2.5.2`, `45 int32`, det/fft/random, 128-bit longdouble, `built-in` (`outputs/08_import_numpy.*`).
11. `shim/run_vfs.py --script /data/job_numpy.py` → the grouped summary, `/out/summary.csv` written and read back (`outputs/10_job_numpy.*`).
12. `fixtures/bench_guest.py` in the guest and `scripts/bench_native.py` ×3 natively (`outputs/11_bench_guest.*`, `09_bench_native.txt`).
13. The `numpy.random` probe before and after the rename header (`outputs/15_random_probe.json`, `15_*_symbols.txt`, `cross/npy_random_legacy_rename.h`).
14. `scripts/08_build_vfsmain.sh` (command model, then reactor) → `python-vfsmain.wasm`; Wizer (four runs: ctors, dtors, stdout flush, preopen root) → `python-wizer.wasm` 50,635,154 B (`outputs/13_*`, `14_*`).
15. `scripts/bench_startup.py` on the floor (Brett), the numpy binary with four zip/cache variants, and the snapshot (`outputs/18_bench_*.txt|json`).
16. `scripts/07_pandas_build.sh` (four runs: versioneer, Cython in the build-Python, headers, success) → 45 archives in 31 s (`outputs/12_pandas_build.log`, `19_pandas_archives.txt`).
17. `scripts/gen_inittab.py` → `cross/vfs_inittab.c` (58 modules); `scripts/04b_link_python_pandas.sh` (three runs: duplicate symbols, `_cyutility`, zlib) → `python-pandas.wasm` 55,218,012 B (`outputs/20_*`).
18. `scripts/09_build_zlib.sh` (two runs: empty archive, fixed) → `libz.a` 101,002 B.
19. The pandas zip (stored, then deflated with zlib in; `_sysconfigdata`, `ctypes` and `mmap` stand-ins added one run at a time) → `shim/run_vfs.py --script /data/job_pandas.py` exit 0 (`outputs/21_job_pandas.*`, `24_deflated_pandas.json`, `zip_pandas*.txt`); `scripts/bench_native_pandas.py` ×3 (`outputs/22_bench_native_pandas.txt`).
20. `MAKELOG=… OUT=python-pandas-vfsmain.wasm VFS_PREIMPORT="… numpy, pandas" scripts/08_build_vfsmain.sh`; Wizer → `python-pandas-wizer.wasm` 94,501,599 B; the job on the snapshot (120 ms, 15 verbs) and its cold-start bench (`outputs/25_*`).
21. wasi-sdk 33 downloaded and the exception probe built and run (`outputs/23_sizes.txt` lists `throw_probe_eh33.wasm`; the transcript of the run is in this report's finding 10).

## The patch list (zero upstream diffs; twelve recipe files)

No file in the CPython 3.14.8, numpy 2.5.2, pandas 3.0.6 or zlib 1.3.1 trees was modified. Every adaptation is a file we wrote, kept under `experiments/s12/cross/` or `scripts/`:

| file | lines | what it does | why |
|---|---|---|---|
| `cross/wasi-numpy.cross` | 30 | meson cross file: wrapper compilers, `longdouble_format = IEEE_QUAD_LE`, `-D_WASI_EMULATED_*`, `-DNPY_NO_SIGNAL`, `-fexceptions`, the legacy rename `-include` | numpy cannot run a probe binary; wasi-libc's emulated signal/clock/getpid |
| `cross/wasi-pandas.cross` | 30 | the same with the pandas rename header | |
| `scripts/wasi-cc`, `wasi-cxx` | 45 | drop `-fPIC`; drop `--start-group/--end-group`; on `-shared -o X.so` write an `ar` archive + `X.so.deps` | static builtins without touching any `meson.build` |
| `scripts/python-wasi-cross` | 12 | native build-Python answering with the WASI `_sysconfigdata` (+ Cython/versioneer on `PYTHONPATH`) | meson introspection of the target |
| `cross/cxa_stubs.c` | 18 | `__cxa_allocate_exception`, `__cxa_throw` → report and abort | wasi-sdk 24 has no C++ EH runtime; superseded by wasi-sdk 33 |
| `cross/npy_random_legacy_rename.h` | 72 | 66 `#define`s active under `NP_RANDOM_LEGACY` | `distributions.c` is built twice with different `RAND_INT_TYPE` |
| `cross/pandas_rename.h` | 7 | 3 `#define`s | pandas vendors numpy's `np_datetime.c` under numpy's names |
| `cross/vfsmodule.c` | 70 | the `vfs.ping` door; a guarded constructor registering numpy's 13 dotted names | the verb door; inittab before `Py_Initialize` with no change to `Programs/python.c` |
| `scripts/gen_inittab.py` → `cross/vfs_inittab.c` | 35 → 70 | generated constructor for all 58 numpy+pandas modules, dotted names from archive paths (`_cyutility` special-cased) | |
| `cross/vfs_main.c` | 95 | reactor entry: `wizer.initialize` (init + pre-imports + `gc.freeze`), `vfs_run` (argv via `__wasi_args_get`, `-c`/script, Python-level flush) | Wizer needs ctors once and no `_start` |
| `cross/Setup.local.generated`, `Setup.local.pandas.generated` | 3 | `*static*`; `vfs …c …a -lc++ -lc++abi -lc-printscan-long-double`; `zlib zlibmodule.c -I… libz.a` | the one link |
| `cross/ctypes_stub.py`, `cross/mmap_stub.py` | 5 + 9 | one-function stand-ins in the zip | pandas imports both unconditionally; upstream fix is a one-line `try/except` each (not applied) |
| `build/numpy-host-shim/numpy/__init__.py` (regenerated by the build) | 5 | `get_include()` → the WASI headers | pandas' meson asks the build-Python for numpy |
| `scripts/09_build_zlib.sh` | 12 | zlib 1.3.1 static with `AR=llvm-ar ARFLAGS=rc` on the make line | zlib's configure picks `libtool` on Darwin |

## The yearly build as a CI job (the plan)

**Name:** `vfs-python` release workflow, `workflow_dispatch` plus a yearly cron (first week of January), on `ubuntu-24.04` (x86_64; the artifact is `wasm32-wasip1`, host-independent), about 10 minutes on a 4-core runner from these timings (CPython 2–3 min, numpy 1 min, pandas 2 min, links and snapshots 1 min, verification 2 min).

**Pinned inputs (all by URL + sha256 in `downloads/SHA256SUMS`, verified before use):** CPython 3.14.8 (`c2215904…`) — or 3.15.x when the SDK-33 line is chosen; wasi-sdk 24.0 (`aeae9993…` is the arm64-macos tarball; the Linux x86_64 tarball gets its own pin) — or 33.0; numpy 2.5.2 (`d482d171…`); pandas 3.0.6 (`66b07ef7…`); zlib 1.3.1 (`9a93b2b7…`); python-dateutil 2.9.0.post0, tzdata 2026.5, six 1.17.0 (pure wheels, hashed); wizer 11.0.3; wasmtime CLI 49.0.3 (CPython's driver wants one on `PATH`); build venv: Cython 3.3.0, meson 1.12.1, ninja 1.13.2, versioneer 0.29 (a `uv.lock` for the venv); wasmtime-py pinned to vfs's own dependency for verification.

**Steps, in order (each is a script in `experiments/s12/scripts/`, to be moved under `scripts/wasi-python/` in the repo when spec 172 lands):**

1. `00_download.sh` — fetch and verify hashes; fail on mismatch.
2. `02_build_cpython_floor.sh` — build-Python and WASI Python with `Tools/wasm/wasi build`; record `python.wasm` hash as the floor.
3. `09_build_zlib.sh` — zlib static archive.
4. `03_numpy_build.sh` — meson cross build with `cross/wasi-numpy.cross` and the wrapper; archives.
5. `07_pandas_build.sh` — with `cross/wasi-pandas.cross`, the numpy host stand-in (assembled from numpy's sdist headers plus the three generated ones), Cython and versioneer on the build-Python's path.
6. `gen_inittab.py` over both build trees → `vfs_inittab.c`; `04b_link_python_pandas.sh` writes the build-dir `Setup.local` (archives, deps, `-lc++ -lc++abi -lc-printscan-long-double`, the zlib line, `vfsmodule.c`, `cxa_stubs.c` until SDK 33) and `make`s `python.wasm`; a numpy-only variant is the same script with one build tree.
7. `08_build_vfsmain.sh` — the reactor link (`-mexec-model=reactor`, `vfs_main.o` in place of `Programs/python.o`).
8. `make_stdlib_zip.py --deflate --skip ctypes` with `--extra` numpy, pandas (pure tree from the sdist), dateutil/tzdata/six, the WASI `_sysconfigdata`, the two stand-ins; bytecode-only (`--pyc` with the build-Python) once the pyc-vs-src size question is settled (pyc deflated is 5.9 MB vs 3.5 MB src for the numpy set; sources are smaller because 3.14 pycs are large, and imports are faster from pyc).
9. Wizer: `--allow-wasi --wasm-bulk-memory true --init-func wizer.initialize --mapdir /::<root with usr/local/lib/python314.zip>`; `VFS_PREIMPORT` lists the pre-imports (`numpy`, `pandas`, and the stdlib set an agent touches first).
10. Verification = this spike's runs under the vfs shim, as a pytest module marked `slow`: study 04's script, `import numpy` with zero `.so` opens, the numpy CSV job, the pandas CSV job, the `numpy.random` probe (both APIs), `vfs.ping`, a post-snapshot stdlib import, and the counted verb/SQL/preview1 numbers as operation counts (never wall-clock). Add numpy's and pandas' own test subsets as a second gate when they run under the shim.
11. Artifacts: `vfs-python-<pyver>-numpy<ver>-pandas<ver>-wasm32-wasip1.wasm` (plain reactor) and `…-wizer.wasm` (snapshot), `python314.zip`, `SHA256SUMS`, `MANIFEST` (every pin, every recipe file hash, the wizer command line, `SOURCE_DATE_EPOCH`), xz-compressed as release assets (8–20 MB). The `.cwasm` is **not** an artifact; vfs compiles once per host into its cache keyed by wasmtime version (study E1's cache design).

**What the first release includes:** CPython 3.14.8, numpy 2.5.2, pandas 3.0.6, zlib, dateutil/tzdata/six, the `vfs` door, the Wizer snapshot. **Excludes:** matplotlib, scipy, Pillow, threads, BLAS, SIMD, `_ctypes`, `mmap`, sockets/`_ssl`, `_sqlite3` (bashkit has a recipe; an afternoon when wanted), bz2/lzma (an afternoon each).

**Effort to add, with the deciding fact:** matplotlib — move to the CPython 3.15 / wasi-sdk 33 line (C++ exceptions, EXECUTED to work), then freetype, libpng, qhull, kiwisolver, contourpy, Pillow as further `Setup.local` archives with Pyodide's patch set as the reading list: 2–4 weeks. scipy — f2c-translated Fortran and OpenBLAS, Pyodide's recipe as the map: a quarter, not in the first year unless an agent workload demands it.

**Maintenance shape:** every pin is one line; the recipe files are small and target build systems (meson, makesetup), not source; the two rename headers and the two stand-ins are the only things that can rot when numpy or pandas change a file, and the linker (duplicate-symbol or signature-mismatch) or the import (ModuleNotFoundError) says so loudly.

## Questions for Clay

1. **3.14 + SDK 24 now, or 3.15 + SDK 33?** 3.14.8 is what this spike proved end to end and what Brett's 3.14.7 release matches; 3.15.0 (released 2026-10-09 with SDK 33) brings real C++ exceptions, which matplotlib needs and which turn pocketfft's abort-on-throw into a proper Python exception. My lean: build the first release on 3.15 + SDK 33 and re-run this recipe (the numpy 2.5.2 classifiers list 3.15; pandas 3.0.6 requires ≥3.11), accepting a day of re-verification.
2. **Is the first annual build numpy + pandas only?** Yes on the evidence: both are in, matplotlib is a second-release item gated on the SDK line and three C libraries, scipy is a third-year item.
3. **Install-time download size:** 8.4 MB xz (numpy), 9.8 MB (numpy+pandas), 11–20 MB for the snapshots, plus a 3.5–6 MB zip. Is a 20 MB optional download at install time acceptable on every host we care about, or should the snapshot be an opt-in second download?
4. **Cold start an agent sees:** 3–5 ms per call from the snapshot after a one-time compile per host (1–2.5 s, cached as `.cwasm`); 80–120 ms per call from the plain binary with a cached zip row; 1.1–1.9 s for the first `import numpy` without the snapshot. Is the snapshot the default guest, with the plain binary kept for debugging?
5. **The speed penalty:** 1.3–2.3× native on numpy and pandas kernels, single-threaded, no SIMD, no BLAS. For an interpreter whose purpose is a sandboxed read → compute → write loop over vfs rows, I read that as acceptable; the honest caveats are int32 default integers and the absence of threads.
6. **The int32 default integer** (wasm32 is ILP32): document it, or carry a numpy patch that makes the default `int64` on wasm32? Pyodide documents it. My lean: document it in the agent-facing surface and leave numpy alone.
7. **The shim's zip-row cost** (256 re-stagings per `import numpy`): a staged-buffer cache keyed by `(path, version)` in the spec 167 shim, embedding the zip in the binary with wasi-vfs, or both? The snapshot sidesteps it for the pre-imported set only.
8. **Where do the recipe files live** when spec 172 lands — `scripts/wasi-python/` in this repo with the workflow, or a separate `vfs-python` repo that publishes releases this repo downloads? My lean: this repo, because the verification is this repo's shim and tests.

## Verdict, in plain words

It works, and it was not hard. A single `python.wasm` with numpy and pandas inside builds from pinned sources in about ten minutes, without changing one line of CPython, numpy or pandas. It runs over vfs through the same preview1 shim study 04 wrote, reads and writes rows, never opens a shared library, never touches the host disk. With a Wizer snapshot it starts in three to five milliseconds, which is faster than every candidate study 05 measured. Compute is one and a half to two times slower than native, with no threads and 32-bit default integers. The things that did not work were all small and all had a name: a wasi-libc link flag for `long double`, two symbol clashes that only exist in a static link, a C++ exception runtime that the older SDK lacks and the newer one has, two stdlib modules pandas assumes and WASI does not have, and zlib. matplotlib needs the newer SDK and three C libraries, weeks. scipy needs Fortran through f2c, months. Go on numpy and pandas for the first yearly build.

## Sources

- CPython 3.14.8 tarball (python.org, sha256 `c2215904f02b…`); `Tools/wasm/wasi/__main__.py` (WASI_SDK_VERSION = 24), `Modules/makesetup`, `Modules/getpath.py`, `Python/import.c` `is_builtin()`; the `cpython` clone @ fdec4df for `Platforms/WASI/*` (3.16 main; SDK 34 pin) — READ.
- numpy 2.5.2 sdist (PyPI, `d482d171c406…`); `numpy/meson.build`, `numpy/_core/meson.build` (`longdouble_format` property, `_multiarray_umath` target), `numpy/random/meson.build` (`mtrand` with `-DNP_RANDOM_LEGACY=1`), `meson_cpu/meson.build` (`wasm32`), `doc/source/building/cross_compilation.rst`, `vendored-meson/meson/mesonbuild/scripts/python_info.py` — READ.
- pandas 3.0.6 sdist (PyPI, `66b07ef7315a…`); `meson.build` (`_cyutility`), `pandas/errors/__init__.py:8,807`, `pandas/io/common.py:27,1200`, `pandas/compat/_constants.py:21` — READ.
- zlib 1.3.1 (github.com/madler/zlib release, `9a93b2b7dfda…`) — built.
- wasi-sdk 24.0 and 33.0 release tarballs (github.com/WebAssembly/wasi-sdk); release notes for wasi-sdk-33 (PR #606 "Build a sysroot that supports C++ exceptions by default") and `CppExceptions.md` (fetched via the GitHub API, 2026-10-16) — READ; the exception probe — EXECUTED.
- wasmtime 49.0.3 CLI (`-W exceptions` listed in `-W help`), wasmtime-py 49.0.0; wizer 11.0.3 (`--help`: `--init-func`, `--keep-init-func`; no `_initialize` note) — READ/EXECUTED.
- Brett Cannon, `cpython-wasi-build` releases (v3.14.7 SDK 24, v3.15.0 SDK 33; MIT) — fetched via `gh`.
- Pyodide: `pyodide:packages/numpy/meta.yaml` @ adc5b63 (numpy 2.4.6, cross file, `cross-build-files`); `pyodide/pyodide-recipes` @ 01bd0af (2026-10-02, MPL-2.0): `packages/matplotlib/meta.yaml` (3.10.8, five patches, `-fwasm-exceptions`, `freetype-legacysjlj`), `packages/scipy/meta.yaml` (1.18.0, f2c, five patches, the `void→int` rewrites, `libopenblas`, `libboost`, `meson < 1.10`), `packages/pandas/meta.yaml` (3.0.2, `-Werror=mismatched-*`, `-Oz`) — READ at the cited commit; no copies are kept (reference material is cited, never copied).
- Studies 04 (§5), 05 (§2–§5), 11 (finding 1, §B), 12 (finding 7) of this series; spec 173; ADR 086 (provisional).
