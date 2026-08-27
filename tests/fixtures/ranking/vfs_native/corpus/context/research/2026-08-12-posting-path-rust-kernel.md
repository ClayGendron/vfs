# The posting path after numpy: stdlib cost, a Rust kernel, and where wheels can't go

- **Status**: research memo (commits us to nothing; feeds a pending ADR on
  the grep posting-path dependency — numpy vs pure stdlib vs an optional
  Rust accelerator)
- **Date**: 2026-08-12
- **Owner**: Clay Gendron
- **Question**: numpy survives in the live tree for exactly one job — the
  trigram posting path (`decode_postings` in `src/vfs/models/postings.py`,
  and the union/intersect algebra in
  `src/vfs/storage/backends/database/grep.py`). Can we drop it for pure
  stdlib without meaningfully slowing grep? If stdlib is too slow, does a
  small purpose-built Rust extension beat both — and if we ship one with
  builds owned in GitHub Actions, where can it still not run?
- **Evidence gathered**: executed benchmarks on the 072 spike's real-code
  corpus — 990,000 chunks (~4 KB, line-aligned) drawn from 16 reference
  repos (linux, freebsd-src, postgres, gitlabhq, sqlalchemy, …), 1.8 GB
  SQLite corpus + 440 MB gram index, rebuilt from
  `context/specs/active/072-database-storage-backend/spike/build_corpus.py`
  and `build_index_sqlite.py`. Four decode+intersect arms measured at the
  planner's k=4 rarest-first choice (median of 5–7 runs, candidate counts
  asserted identical across arms), on an Apple Silicon macbook (darwin,
  Python 3.13, rustc 1.97.1). A PyO3 crate was written and built for the
  Rust arm. Distribution research ran as three parallel web surveys
  (current docs/changelogs/PEPs, August 2026): the GitHub-Actions-buildable
  wheel matrix, alternative Python runtimes, and the residual no-wheel
  platforms. Scripts, crate source, and raw JSON results are preserved in
  `studies/2026-08-12-posting-path-rust-kernel/`.

---

## 1. Where numpy actually lives

Two live modules, one story:

- `src/vfs/models/postings.py` — `decode_postings` is numpy-vectorized;
  `encode_postings` is already pure Python.
- `src/vfs/storage/backends/database/grep.py` — set algebra on decoded
  arrays: `np.unique`/`np.concatenate` for the GramOr union,
  `np.intersect1d` for the rarest-first GramAnd loop.

Nothing else in `src/` or `tests/` imports numpy — vectors/embeddings
never touch it. Dropping it is purely a posting-path question. (Context:
sqlmodel, rustworkx, and tiktoken were removed from the dependency list
the same week; numpy is the last heavyweight core dep, though it returns
transitively via the `search` extra, whose usearch requires it.)

## 2. Method

The bench mirrors the live planner faithfully: for each pattern,
`build_code_gram_query` produces the gram query; per branch, posting rows
are priced by `doc_count` and the k=4 rarest blobs are fetched — exactly
the blobs `grep_rows` would decode. Arms then run over identical blobs:

- **numpy** — vectorized varint decode + `np.intersect1d` (live design).
- **py_naive** — pure-Python varint decode of every blob, then Python set
  intersection.
- **py_fused** — decode the rarest blob into a set; stream-decode each
  later blob byte-by-byte, keeping members only (the best stdlib
  spelling — later grams never materialize full lists).
- **rust_fused** — `vfs_postings_rs.intersect_rarest`: decode the rarest
  blob to a `Vec<i64>`, then stream-decode each later blob with a
  two-pointer merge against the sorted survivors. ~60 lines of PyO3,
  abi3-py311, built by maturin in ~10 s.
- **rust_decode_only** (control) — decode in Rust, intersect via
  `np.intersect1d`, to separate the decode win from the fusion win.

Caveat on scope: the spike harness measures the decode+intersect stage
and the surrounding pipeline stages (blob fetch, content fetch, Python
`re` verify) against the spike's SQLite schema, not the live
`grep_rows` end-to-end path — the stage boundaries match the live
design, but absolute totals are spike-shaped.

## 3. Finding: stdlib meaningfully slows interactive greps

Stage timings (decode+intersect, k=4, median; pipeline total is the full
spike ladder under the numpy arm):

| pattern | candidates | stdlib (fused) | numpy | Rust (fused) | pipeline total |
|---|---:|---:|---:|---:|---:|
| rare_ident (`EXPORT_SYMBOL_NS_GPL`) | 646 | 6.3 ms | 1.8 ms | 0.54 ms | 4 ms |
| medium_ident (`kmalloc`) | 6,052 | 31.2 ms | 9.7 ms | 2.6 ms | 29 ms |
| hot_phrase (`def __init__`) | 1,654 | 13.5 ms | 3.7 ms | 1.1 ms | 10 ms |
| punct_neq_null (`!= NULL`) | 36,779 | 45.7 ms | 13.6 ms | 4.3 ms | 128 ms |
| regex_probe (`static\s+int\s+\w+_probe`) | 23,306 | 39.7 ms | 12.5 ms | 3.5 ms | 106 ms |
| hot_ident (`return`) | 257,360 | 106.6 ms | 38.7 ms | 11.0 ms | 504 ms |

- Pure stdlib is **3–4.5× slower than numpy** at every corpus shape —
  far better than naive expectation (the numpy decode is itself ~8
  array passes, not one), but on the queries agents feel — rare/medium
  identifier greps completing in 4–30 ms end-to-end — stdlib **roughly
  doubles total latency** (medium_ident: ~29 ms → ~51 ms). It only
  hides on heavy queries where verify dominates.
- Memory is the second stdlib cost: boxed-int sets run ~4–8× the
  footprint of an int64 array on large candidate lists — a real factor
  under concurrent agent greps, though unmeasured here.

## 4. Finding: the fused Rust kernel beats everything; a thin decoder does not

- **rust_fused is 3–6.5× faster than numpy** and 10–12× faster than
  stdlib on every pattern. End-to-end: **~20–30% off the interactive
  greps** (rare_ident 32%, hot_phrase 27%, medium_ident 24%; the
  decode-heavy outlier class_prefix ~45–50%), **~2–8% off the heavy,
  verify-dominated ones**. Against a stdlib baseline (the comparison
  that matters once numpy is gone), Rust saves ~35–60% on the
  interactive class.
- **The control arm is the design lesson**: rust_decode_only barely
  beat stdlib (4.3 ms vs 6.3 ms on rare_ident) because returning
  millions of ids across the CPython boundary as boxed ints eats the
  entire win. **Fusion is the kernel; a thin decode function is not
  worth building.** Only survivors (post-gate, ≤ CANDIDATE_BUDGET)
  should ever cross the boundary.
- Verify remains the whale: regex_wrapped spends ~362 ms in Python
  `re` against ~7 ms in decode+intersect. If a compiled extension ever
  enters the tree, extending it to verification (the `regex` crate —
  the ripgrep engine) is where the next order of magnitude lives; this
  memo does not evaluate that.

## 5. Finding: where a CI-built Rust wheel can and cannot go (August 2026)

**Tier 1 — wheels just work.** With abi3-py311 collapsing the
Python-version axis, ~7 GitHub Actions jobs cover: manylinux_2_28 +
musllinux_1_2 on x86_64 and aarch64 (native arm64 runners are free on
public repos since Aug 2025), macOS arm64 + x86_64, Windows x64 + ARM64,
plus the sdist. PyPI-legal optional lanes: ppc64le, s390x, armv7l,
riscv64 (accepted summer 2025; maturin cross-compiles all four without
QEMU), i686, PyPy (`pp311`, manylinux only), iOS and Android (accepted
2025, tooling young), and browser WASM — **PEP 783 emscripten wheels
went live on PyPI 2026-04-21** and pydantic-core already publishes them.
Free-threaded CPython is the abi3 caveat: 3.13t/3.14t need
version-specific `cp314t` wheels (cibuildwheel builds them by default);
PEP 803's `abi3t` closes this properly at Python 3.15. A maximal
matrix is ~16–18 jobs; the pragmatic core is 7.

**Tier 2 — no wheel possible; sdist works only with cargo +
crates.io.** PyPI's upload validator structurally rejects platform tags
for all BSDs, illumos/Solaris, AIX, and Haiku — pip always falls back
to sdist there. Builds succeed via ports systems (FreeBSD ports ships
pydantic-core and orjson today; Rust is tier-2-with-host-tools on
FreeBSD/NetBSD-amd64/illumos), but bare `pip install` fails without a
local toolchain. Also here: Termux (bionic libc — manylinux never
applies), loongarch64 (toolchain ready, warehouse acceptance pending),
and **air-gapped corporate networks — a Rust sdist build needs
crates.io at build time, a second supply chain PyPI mirrors don't
cover** (mitigation: publish a `cargo vendor`-ed sdist). Old-glibc
Linux (Amazon Linux 2, RHEL 7 ELS) is mitigable by also shipping a
manylinux2014/glibc-2.17 x86_64 wheel.

**Tier 3 — cannot run, full stop.**

- **WASI**: CPython's WASI build has no dynamic loading — extension
  modules cannot load at all; static-linking into a bespoke interpreter
  is the only path, with no wheel tag and no pip story. Given the
  hermetic-runtime direction (wasmtime-py, browser_wasi_shim, monty in
  the reference list), this is the one non-fringe entry: **a required
  Rust kernel forecloses vfs-under-WASI entirely; a pure-Python
  fallback is the only mechanism there.** (Browser-side Pyodide is
  fine — that's emscripten, Tier 1.)
- Platforms Rust has no target for: HP-UX, AIX < 7.2, alpha/hppa/ia64,
  32-bit SPARC — C-only legacy Unix, irrelevant to a Python ≥ 3.11
  package in practice.
- MicroPython/Jython/IronPython — moot; they cannot run vfs regardless.

Key sources: PyPI warehouse tag validator
(`warehouse/utils/wheel.py`); PEP 783 (emscripten wheels, accepted;
live 2026-04-21); PEP 803 (`abi3t`, Final, targets 3.15); PyO3
free-threading guide (abi3 ignored on 3.13t/3.14t); cibuildwheel
platforms/changelog (v4.2.0, cp314t default, riscv64, iOS/Android);
GitHub changelog (arm64 runners GA 2025-08-07); Brett Cannon,
"WebAssembly and its platform targets" (WASI static-link-only);
pydantic "Building Emscripten wheels" (maturin pipeline); LWN 845535
(the 2021 cryptography-Rust platform fight and its aftermath);
rust-lang platform-support table (tier assignments cited above).

## 6. Shape of the decision this feeds

The measurements and the distribution survey point the same direction,
but the choice is Clay's to make in an ADR:

1. **Keep numpy** — zero work; fine performance; core install stays
   heavyweight and numpy remains a compiled dep with its own (excellent)
   wheel matrix. Forecloses nothing except slimness.
2. **Pure stdlib only** — most portable core (universal wheel,
   WASI-viable); costs ~2× on interactive indexed greps and ~4–8× memory
   on hot candidate lists.
3. **Optional Rust accelerator over a stdlib floor** — the
   pydantic-core-style split inverted: pure-Python codec as the
   *required* baseline (portability floor, WASI path stays open), the
   fused kernel as an optional wheel (`vfs-postings` extra or
   auto-detected import) serving everywhere wheels reach. Owning ~7 CI
   jobs covers the wheel side; the stdlib floor covers the rest. The
   fused-kernel finding binds any implementation: the accelerator API
   must be intersect-shaped (blobs in, survivors out), never
   decode-shaped.

A "Rust required" posture (option 3 without the floor) is the one shape
the evidence argues against: it buys no more speed than the accelerator
and inherits every Tier 2/3 gap as a hard installation failure.
