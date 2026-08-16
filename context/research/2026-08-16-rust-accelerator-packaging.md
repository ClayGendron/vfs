# Packaging an optional Rust accelerator: the two-package shape and its 2026 facts

- **Status**: research memo — slice A of the Rust-core story (spec
  103); resolves the dependency-posture fork's engineering side
  (Clay pinned the posture 2026-08-16: pure-Python fallback stays,
  accelerator optional)
- **Date**: 2026-08-16
- **Owner**: Clay Gendron
- **Question**: How does an optional Rust core ship so that
  `pip install vfs-py` keeps working everywhere with zero compiled
  requirements, while the accelerated path gets wheels for the
  platform matrix — and what do pyo3/maturin/abi3 actually support
  in 2026?
- **Evidence gathered**: web study of official docs (pyo3.rs,
  maturin.rs, packaging.python.org, PEP 803, uv docs, GitHub
  changelog) and field precedents (psycopg 3, coverage.py, msgpack,
  uvicorn/uvloop, charset-normalizer), plus a live
  `maturin generate-ci github` run (maturin 1.14.1) for the real CI
  matrix. Source links inline.

---

## 1. The shape is forced: two packages, psycopg model

A single package with a build-time "compile if possible, else pure"
trick (msgpack's setuptools pattern) is **unavailable for Rust**:
maturin builds are all-or-nothing — there is no
optional-extension mode. So the fallback posture Clay pinned forces
the psycopg 3 shape, which is also the strongest precedent in the
field ([install docs](https://www.psycopg.org/psycopg3/docs/basic/install.html)):

- **`vfs-py` stays pure** (hatchling, no compiled anything,
  installs everywhere — the guaranteed path).
- **`vfs-accel`** (import name `vfs_accel`) is a separate PyPI
  distribution: a pure-Rust maturin project whose wheel is just the
  extension module.
- `vfs-py` gains `[project.optional-dependencies] accel =
  ["vfs-accel == <lockstep version>"]` — psycopg pins its
  accelerator **exactly** (`== 3.3.5…`) and marker-gates it
  (`implementation_name != "pypy"`); release automation keeps the
  versions in lockstep.
- **Resolver fact that shapes the docs**: an extra is a hard
  dependency once requested — `vfs-py[accel]` on a platform with no
  wheel *fails loudly*, never skips (pip and uv alike; PEP 508
  markers cannot express "a wheel exists"). That is the correct
  behavior for us: plain `vfs-py` is the always-works install, and
  the extra never degrades silently.

**Import contract** (coverage.py's `no-ctracer` warning is the UX
model): the pipeline does `try: import vfs_accel` / fall back on
`ImportError`; the accelerator exposes a small integer protocol
version the Python side checks — mismatch warns once and falls
back. Which core is active is exposed for tests and diagnostics.

## 2. pyo3/abi3 facts that bound the design (August 2026)

- pyo3 **0.29.2**, maturin **1.14.1** current
  ([releases](https://github.com/pyo3/pyo3/releases)).
- **`abi3-py311` gives one wheel per platform** covering CPython
  3.11+ — and every abi3 limitation pyo3 documents clears at our
  3.11 floor, including the **buffer protocol** (supported under
  abi3 from 3.11 —
  [building & distribution](https://pyo3.rs/main/building-and-distribution)).
  Zero-copy bytes-in is therefore fully available.
- **GIL release (`allow_threads`) has no abi3 restriction** —
  rayon-parallel scanning works in abi3 wheels.
- **rust-numpy does not advertise abi3 support** and numpy itself is
  mid-flight on limited-API breakage
  ([numpy#30704](https://github.com/numpy/numpy/issues/30704)).
  **Consequence: the accelerator interface avoids rust-numpy** —
  bytes/buffer-protocol in, bytes/ints out. This also keeps the
  crate dependency-light and the seam trivial to satisfy from the
  pure path.
- **Free-threaded CPython**: PEP 803 (approved 2026) defines
  `abi3t`; pyo3 0.29 ships the features, maturin's tag support is
  landing ([maturin#3064](https://github.com/PyO3/maturin/issues/3064)).
  Until those wheels are worth building, free-threaded users simply
  get the pure path — the fallback makes this a non-event.

## 3. Repo layout and the dev loop

`crates/vfs-accel/{pyproject.toml, Cargo.toml, src/lib.rs}` in this
repo — its own `build-backend = "maturin"`; the root package keeps
hatchling untouched. Root `pyproject.toml` declares
`[tool.uv.workspace] members = ["crates/vfs-accel"]` and
`[tool.uv.sources] vfs-accel = { workspace = true }`; uv drives each
member's own backend and shares one lockfile
([uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)).
Dev loop: `uv sync --extra accel` or `maturin develop --uv`; one
contributor-docs gotcha — uv caches built wheels, so Rust edits need
`uv sync --reinstall-package vfs-accel`.

## 4. CI wheel matrix

`maturin generate-ci github` (run live) emits the full workflow;
trim to: **manylinux_2_28** x86_64 + aarch64 (the sensible 2026
floor; manylinux2014 images are EOL), musllinux_1_2 x86_64 +
aarch64, macOS arm64 + x86_64, Windows x64. **Native arm runners
are standard now** (`ubuntu-24.04-arm`, `windows-11-arm` — GA for
public repos Aug 2025) so arm wheels are built *and tested* without
QEMU. With abi3 the whole matrix is one wheel per platform,
~5–15 min wall with sccache. **Publish the sdist too**: since
maturin 1.8.4 an sdist build on a toolchain-less machine
self-bootstraps a private Rust toolchain
([maturin#2421](https://github.com/PyO3/maturin/pull/2421)), and
conda-forge automation needs the sdist.

The existing test matrix gains one leg: the suite runs with and
without `vfs-accel` on one platform, so the fallback contract stays
pinned as a first-class citizen, not a stale copy.

## 5. Addendum (same day): the recorded decision is the pendulum model, not §1's recommendation

Clay rejected the two-package ergonomics at review. A follow-up
staff-pattern survey reordered the option space: the dominant Rust
pattern in the field is *requiring* the extension outright
(pydantic-core, orjson, cryptography, tokenizers, polars); given the
pinned pure-fallback constraint, the staff-standard single-package
shape is **pendulum 3's maturin mixed layout** — the complete
pure-Python implementation ships inside every wheel beside the
extension, runtime try-imports and falls back, one distribution and
one version so skew is structurally impossible. The residual: on a
platform with no wheel, the sdist build bootstraps a Rust toolchain
(§4's maturin ≥ 1.8.4 fact) rather than installing pure, and
`vfs-py`'s build backend moves from hatchling to maturin. Two
shapes surveyed and set aside: dual-wheel single package via CI
wheel injection (bespoke surgery a staff reviewer would flag) or
via `setuptools-rust(optional=True)` (proven mechanics in the
C/mypyc world, least-trodden for Rust). Decision recorded in spec
103 §1, which also adds Clay's multi-language constraint: engine
logic lives in binding-free core crates so vfs-rs / vfs-js
bindings can share them later.

## 6. Limitations

Facts dated August 2026 — pyo3/maturin move fast (abi3t tag support
is explicitly in flight); re-verify versions at slice B. Build times
are estimates from field reports, not measured on this repo. The
exact-pin lockstep between the two packages needs release
automation that does not exist yet; until it does, releases are a
two-step manual dance and the protocol-version check is the safety
net.
