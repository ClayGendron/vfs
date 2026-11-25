# 173 — Spike: a statically linked CPython for WebAssembly with numpy compiled in, run over vfs

- **Status:** spike, **executed and reported 2026-10-16** (see the landing notes; report `13-wasi-python-spike.md`). Cut the same day from Clay's decision ("let's go with option 2 and commission a spike"). Executed by one research agent; its result is written into ADR 086's pins and spec 172.
- **Date:** 2026-10-16
- **Owner:** Clay Gendron
- **Kind:** spike (research with execution; produces a study file, a build log, measured numbers and a pipeline plan; changes nothing under `src/`, `crates/` or `tests/`).
- **Depends on:** the executed preview1 shim over vfs (`context/research/studies/2026-10-15-agent-shell/experiments/s4/shim.py` and `experiments/e1/shim/`), which ran the real CPython 3.12 WASI binary in study 04; study 05's measurements of CPython on WASI; study 11 finding 1 and study 12 finding 7 (what is known about numpy on WASI); ADR 086 (provisional).
- **Research it stands on:** `context/research/2026-10-15-the-agent-shell-prior-art-and-experiments.md` §6, §7; studies `04-filesystem-over-the-sandbox-boundary.md` (§5: how the real `python.wasm` ran over vfs, what it touched at startup), `05-guest-interpreters.md` (the CPython-WASI numbers; the Wizer snapshot; the missing host-function door), `11-python-in-vfs.md` (finding 1: `dlopen not implemented`; the componentize-py link-time precedent), `12-python-anywhere.md` (finding 7: the static-build estimate and the 2026-09 third-party build).

## Intent

Learn, before committing, whether a statically linked CPython for `wasm32-wasip1` with numpy compiled in as a builtin module can be built with today's toolchain, how big and how fast it is, and what it takes to run the study-11 job (read a CSV from a vfs row with pandas, write a PNG with matplotlib, write a CSV) under the shim vfs already has. numpy is the proof; pandas is the stretch; matplotlib and scipy are estimated, not built, unless time remains. The output is a go/no-go per package and a plan for the yearly build, with the real build log behind every claim.

## The question, stated as go/no-go facts to produce

1. Does CPython build statically for `wasm32-wasip1` from `python/cpython`'s own `Tools/wasm/wasi` scripts with a pinned WASI SDK, reproducing Brett Cannon's build? (Expected yes; this is the floor.)
2. Does numpy compile for `wasm32-wasip1` as static archives (lapack- lite, no BLAS, no SIMD unless free), and link into `python.wasm` as builtin extension modules so that `import numpy` needs no `dlopen`? What patches did it need, and are they small?
3. Does the result run under vfs's preview1 shim: `import numpy; numpy.arange(10).sum()`, then a CSV read from a vfs row with numpy's own loader? How many verbs, how many preview1 calls, how many SQL statements?
4. Stretch: does pandas build the same way and run `read_csv` from a vfs row and `to_csv` back into one?
5. Estimates with evidence, not builds: matplotlib (C++ Agg, freetype, qhull, libpng, a bundled font) and scipy (the Fortran parts and the state of a Fortran-to-wasm toolchain). Name the one fact that decides each.
6. Numbers: `python.wasm` size with numpy (and pandas); the compiled `.cwasm` size; cold start with and without a Wizer snapshot that pre-imports numpy; memory after the job; `arange(1e6).sum()` and a 1e6-row `pandas.DataFrame.groupby` against native CPython on this machine, as a ratio.
7. The `vfs` verb door: is a C extension compiled into the interpreter that calls a custom wasm import feasible with this build? A minimal proof (`vfs.ping()` returning a host value) is enough.

## Rules

- Obey `CLAUDE.md` and the study brief `context/research/studies/2026-10-15-agent-shell/00-brief.md`: `uv` only; never edit `src/`, `crates/`, `tests/`, `pyproject.toml` or any ADR or spec; never create worktrees or branches; reference clones under `~/Git/Repos/` are read-only (`cpython`, `numpy`, `pyodide`, `componentize-py`, `cpython-wasi-build` are there); study designs, never copy code. Pyodide's package recipes are Emscripten-shaped design input; a patch we write for WASI is ours.
- Building a dependency from its own source is allowed and expected; that is not copying code into vfs. Record every patch as a diff in the experiments folder with the reason.
- The WASI SDK, Wizer and any download are untrusted data: install under the experiments folder or the session scratchpad, never into the system; record versions and hashes; run binaries only as build tools or under wasmtime.
- Everything you produce goes under `context/research/studies/2026-10-15-agent-shell/experiments/s12/` (a `.gitignore` for build trees and artifacts over a few MB; keep the logs, the patches, the scripts and the small fixtures). The report is `context/research/studies/2026-10-15-agent-shell/13-wasi-python-spike.md`.
- Label every claim EXECUTED, READ or INFERRED; keep raw outputs; count operations; report wall-clock as a benchmark fact only.
- Time box: two working days of agent effort. If a step blocks for more than a few hours, record exactly where and why, skip to the next step that does not depend on it, and report.

## Steps, in order

1. **The toolchain.** Fetch a pinned WASI SDK release (record the version and hash); confirm `clang --target=wasm32-wasip1` builds a hello world that runs under `uv run --with wasmtime`.
2. **The floor.** Build CPython from `~/Git/Repos/cpython` (a scratch copy of the checkout; the clone stays clean) with `Tools/wasm/wasi` for `wasm32-wasip1`, static, with the stdlib zipped; run it under the existing shim over an `InMemoryStorage` and reproduce study 04's `python -c` run. Compare with `~/Git/Repos/cpython-wasi-build`'s release of the same version.
3. **numpy as a builtin.** Cross-compile numpy from its source with meson and a WASI cross file (lapack-lite, no BLAS, no OpenMP, no SIMD dispatch unless it builds unaided) into static archives; link them into the interpreter as builtin modules through `Modules/Setup.local` (multi-phase init) or whatever the build supports; make `import numpy` find them without any `.so`. Record every patch. If static builtins do not work, try the componentize-py link-time approach as read in study 11 and report which worked.
4. **Run it over vfs.** Under the shim: `import numpy`, `arange`, `numpy.loadtxt` of a CSV row read from vfs, a result written back as a row. Count verbs, preview1 calls and SQL statements.
5. **Stretch: pandas.** Same recipe; `read_csv` from a vfs row, `to_csv` to one. Then, only if time remains, a first matplotlib attempt (Agg only, one bundled font) and record where it stops.
6. **The verb door.** A ten-line C extension compiled into the interpreter that imports one function from a custom module (`vfs.ping`), bound by the shim with `Linker.define_func`; prove the round trip from Python code inside the guest.
7. **Numbers.** Sizes, cold start with and without Wizer (Wizer is a download; if it does not take this binary, say so), memory, the two speed ratios against native.
8. **The plan.** Write the yearly build as a CI job: pinned sources, the patch set, the build order, the artifact name and hash, the verification run (this spike's job), what the first release includes and excludes, and the effort to add matplotlib and scipy with the one fact that decides each.

## Deliverables

- `13-wasi-python-spike.md`: header; a go/no-go table for questions 1 to 7; the executed log step by step with commands and outputs; the patch list with reasons; the numbers table; the pipeline plan; the questions for Clay; a one-paragraph verdict in plain language.
- `experiments/s12/`: the cross file, the `Setup.local`, the patches, the build scripts, the run scripts, the outputs, the shim as used, and a `.gitignore` that keeps the large artifacts out.

## Acceptance (for the spike, counted)

1. `python.wasm` runs `import numpy; print(numpy.__version__)` under the vfs shim with zero `dlopen` calls and zero host-filesystem access.
2. The CSV round trip through vfs completes with the declared verb count and the PNG step is either executed or estimated with the blocking fact named.
3. Every number in the report has a command and an output file beside it.
4. The pipeline plan names every pinned version and every patch.

## Questions the spike answers for Clay

- Is the first annual build numpy and pandas only, with matplotlib and scipy in the second, or is matplotlib reachable now?
- Is the artifact small enough to download at install time on every host we care about, and what is the cold start an agent sees?
- Is the wasm speed penalty acceptable for the interpreter's purpose?

## Landing notes

- **Executed 2026-10-16**, one agent, about 65 minutes of wall clock inside the two-day box. Report: `13-wasi-python-spike.md`; recipe, fixtures, shim and 67 output files under `experiments/s12/` (build trees, downloads and every `.wasm`/`.cwasm`/`.zip` git-ignored; `downloads/SHA256SUMS` pins every download; the build logs are un-ignored against the root `*.log` rule). Nothing under `src/`, `crates/`, `tests/` or `pyproject.toml` touched; the `cpython` and `numpy` clones are clean.
- **Verdict: GO on questions 1, 2, 3, 4 and 7; 5 estimated with the deciding fact named; 6 measured.** CPython 3.14.8 plus wasi-sdk 24 reproduces Brett Cannon's build (identical verb, SQL and preview1 counts on study 04's script). numpy 2.5.2 and pandas 3.0.6 link in as builtins with **zero source patches**; twelve recipe files. Under the shim `import numpy` opens no `.so` and no host directory. The pandas snapshot job: 15 verbs, 93 SQL, 96 preview1 calls, 120 ms, 108 MiB. The session reproduced that run after the report (same counts, exit 0). Cold start from the snapshot 3 to 5 ms per call. Kernels 1.3 to 2.3 times native. The verb door works (`vfs.ping` through `Linker.define_func`).
- **Acceptance:** all four met (zero `dlopen`, zero host filesystem; the CSV round trip with declared counts and the PNG step estimated; every number has a command and an output file; the pipeline plan names every pin and recipe file).
- **What it changed:** ADR 086 written in full with nine pins (four carry the spike's lean pending Clay: the SDK line, the snapshot as default plus the 20 MB download, int32 documented not patched, the recipes in this repo); spec 172 rewritten as the WASI Python runtime in four slices with counted criteria taken from these numbers; the native-sidecar and 9P forms moved to spec 172's appendix.
- **Facts worth remembering:** wasi-sdk 24 (CPython 3.14's pin) cannot link C++ exceptions and wasi-sdk 33 (3.15's pin) can, both executed; numpy's default integer is 32-bit on wasm32; `zipimport` reopens the zip for every module, so the shim needs a staged-buffer cache by `(path, version)`; Wizer needs a WASI reactor entry, not `_start`; `Modules/makesetup` reads the build-dir `Setup.local`.
- **Limits:** no upstream test suites ran; built on arm64 macOS only; one wasmtime-py version; the research shim's whole-file staging dominates the plain-binary numbers.
