# 057. One Engine: the Rust Extension Is Required, Pure Python Is a Test Oracle, and numpy Leaves the Core

- **Status:** accepted 2026-08-27 — decided by Clay in session ("Lets do
  B and write the ADR"), on the finding that `pydantic-core` already
  makes vfs a compiled-extension package. **Supersedes in part ADR 039**
  (decision 1's "the complete pure-Python implementation ships inside
  every wheel" and decision 6's "the pure fallback approximates the
  authority"); the pendulum's maturin mixed layout, the thin bindings,
  the fold ownership, and the verify authority stand. **Supersedes ADR
  048 §3** (chunking's "degraded pure fallback" — there is no pure
  engine left to degrade). **Supersedes ADR 055 §4's** "the numpy path
  as the pinned fallback". **Releases ADR 035's** numpy-version
  coupling of the Python floor. ADR 046's wall discipline, ingress
  maxima, and partiality law bind the Rust engine unchanged. Closes
  the "pending ADR on the grep posting-path dependency" the
  2026-08-12 memo asked for and nobody wrote.
- **Date:** 2026-08-27
- **Deciders:** Clay Gendron
- **Decided by:** human
- **Context source:** the numpy-and-Rust history trace run in session
  (timeline below); `../research/2026-08-12-posting-path-rust-kernel.md`
  (stdlib vs numpy vs a fused Rust kernel, and §5's platform tiers);
  `../research/2026-08-16-rust-accelerator-packaging.md` §5 (the
  staff-pattern survey: "the dominant Rust pattern in the field is
  *requiring* the extension outright — pydantic-core, orjson,
  cryptography, tokenizers, polars"); CI run 33037191124 (2026-08-27,
  the 3.11-only failure of
  `tests/test_native.py::TestLexicalParity::test_character_classes_match_the_interpreter`);
  and `../research/2026-08-27-rust-kernels-replace-numpy.md` (the
  per-site Rust-vs-numpy measurements that size the spec; executing
  as this record is written).

---

## Context

vfs has two engines. The Rust extension `vfs._native` is the fast
path. A complete pure-Python implementation ships beside it in every
wheel, and `vfs/native.py` falls back to it when the extension is
missing, refuses on a protocol mismatch, or is forced off by
`VFS_PURE_PYTHON=1`. ADR 039 named this the pendulum model. Its
stated purpose was reach: a Rust extension cannot load everywhere,
so the pure engine is what lets vfs run on any interpreter.

That purpose was never achievable. `pydantic>=2.0` is a hard
dependency, and pydantic v2 requires `pydantic-core`, which is
compiled Rust with no pure-Python edition. Anywhere `pydantic-core`
cannot load, vfs cannot import — before a line of our code runs.
Every platform the pure engine was meant to reach is a platform
pydantic already forecloses. The 2026-08-12 memo's one "non-fringe"
Tier 3 case, WASI, read the hermetic-runtime direction backwards:
the hermetic runtime is a sandbox vfs *hosts* (wasmtime inside the
process, so agent-generated code cannot touch the real filesystem),
not a runtime vfs *runs on*. vfs the library always runs on a normal
CPython with wheels. The record knew the field pattern — the
2026-08-16 packaging memo lists pydantic-core first among the
libraries that simply require their extension — and did not connect
it to our own dependency list.

Meanwhile the two-engine posture has been charging real costs:

- **Every kernel is written twice** and pinned byte-identical by
  parity tests. Spec 130 alone landed a tokenizer, a builder, and a
  BM25 scorer on both sides.
- **The pure engine floats with the interpreter.** The pure tokenizer
  takes `\w`, `isupper`, `islower`, `isdigit` from the running
  Python; the Rust tables are frozen at Unicode 15.1. So the engines
  genuinely tokenize differently on 3.11 (Unicode 14.0), 3.12 (15.0)
  and 3.14 (16.0) — `pure_tokenize("aჼB")` gives `['aჼb']` on
  3.11 where Rust gives `['aჼb', 'aჼ']`. CI run 33037191124 caught
  five such code points on the 3.11 leg; the tests had passed only
  because their corpora contained no drift characters. The
  byte-identical-engines invariant was false on three of four
  supported interpreters. One engine has no drift class.
- **numpy became a third tier.** It was added on 2026-08-05
  (`a474971`, spec 093) for posting decode and intersection, and it
  stayed there when the Rust engine took the index build (`91d9936`,
  2026-08-16) and the verify stage (`cba03d3`, 2026-08-17) because
  the read-path profile showed the whole posting stage at ≤ 25 ms
  against a verify stage at 82–99.7 %. Then it grew: ADR 055 made it
  the pinned fallback scorer, and it is the *only* implementation of
  `decode_postings`, grep's `intersect1d`/`unique` algebra,
  `decode_summary`, and `competing_blocks`. Four active specs (132,
  135, 136, 137) plan more. numpy is a compiled wheel with all of the
  portability cost of our own extension and none of the control — it
  cannot be the fallback, and it is slower than the Rust kernels we
  already own (fused decode+intersect 2.6 ms vs 9.7 ms; the BM25
  scorer 4 ms vs 79 ms on the full linux tree).

The rule Clay stated on 2026-08-27, which this record adopts:
performance work belongs in our own Rust code, not in a numeric
library; and "pure Python" means stdlib-only, runnable on any
interpreter — not merely pip-installable. Once the pure engine is
held to that definition, the question is whether it is worth
shipping at all.

## Options considered

- **A — keep the pure engine and make its promise true: drop pydantic
  too.** The only way "runs on any interpreter" becomes real. Pros:
  a genuinely pure-Python vfs. Cons: every model in `src/vfs/models/`
  is pydantic; the replacement is hand-written validation or
  dataclasses across the whole surface, for a property no audience
  has asked for. The hermetic-runtime direction, the one place the
  property was thought to matter, does not need it. Rejected.
- **B — require the extension, the way pydantic-core does; keep pure
  Python as a test oracle.** One shipped engine. Pros: every kernel
  written once; no interpreter-drift class of bug; numpy leaves the
  core dependencies with no stdlib twins to write; the
  `VFS_PURE_PYTHON` CI leg and its double coverage go away; the
  field-standard shape. Cons: a contributor without the extension
  cannot run vfs (maturin's sdist bootstrap and `uv sync` build it;
  pydantic contributors live with the same); free-threaded and
  wheel-less platforms build from the sdist, as ADR 039 already
  accepted. **Chosen.**
- **C — keep both engines, hold the pure one to stdlib, and write a
  stdlib twin for every Rust kernel.** The posture CLAUDE.md briefly
  held earlier on 2026-08-27. Pros: preserves ADR 039's model
  untouched. Cons: pays the double-implementation and drift costs
  forever, for a reach that pydantic-core already denies; the stdlib
  twins were measured at 3–4.5× numpy on the posting path
  (2026-08-12 memo §3–4), so the "fallback" would be the slowest
  engine of three. Rejected.
- **D — keep numpy as the fast path for array math, Rust for the
  rest.** The status quo made explicit. Rejected for the reason in
  Context: it is a third compiled tier that is slower than the one
  we own.

## Decision

**vfs requires its own Rust extension. There is one engine.**

1. **`vfs._native` is required at import.** `vfs/native.py` imports
   the extension unconditionally; a missing module or a protocol
   mismatch is an `ImportError` with a message naming the fix
   (reinstall / `uv sync --reinstall-package vfs-py`), never a silent
   downgrade. `VFS_PURE_PYTHON` is removed. `active_core()` goes with
   it — there is nothing to select. The maturin mixed layout, the
   abi3-py311 wheel per platform, the sdist that bootstraps a
   toolchain, and ADR 039's thin-binding and fold-ownership laws are
   unchanged.

2. **Pure-Python implementations become test oracles, not
   fallbacks.** A readable reference implementation earns its place
   only where it pins a parity test: the tokenizer, the gram
   extraction and gate, the postings codec, BM25 scoring, the match
   law. Those move out of `src/` into `tests/support/` (the referee
   that already holds `lexical_fidelity.py`). They carry no coverage
   obligation, ship in no wheel, and may be pinned to the interpreter
   that generated the Rust tables — a parity test that depends on the
   interpreter's Unicode version skips with a printed reason on any
   other, because the oracle is no longer a product. Where a Rust
   kernel has no readable oracle worth keeping (the fused intersect,
   `competing_blocks`), the parity test compares against a
   deliberately slow, obviously-correct loop written in the test.

3. **numpy leaves the core dependencies.** Every remaining site moves
   into `crates/vfs-core`, shaped the way the 2026-08-12 memo
   prescribed — "intersect-shaped (blobs in, survivors out), never
   decode-shaped" — so posting blobs cross the seam as bytes and
   survivors come back as bytes or a Python list, and no array type
   is exposed at the boundary. The sites, in landing order: the fused
   posting decode + rarest-first intersect + OR-union with the
   allow-list and `CANDIDATE_BUDGET` slice (`postings.py`,
   `grep.py`); the lexical summary decode and round-two block
   selection (`lexical.py`); and the deletion of `pure_score_blocks`
   (its Rust twin `lexical_score` already exists). The
   `search` extra may still pull numpy transitively through `usearch`;
   that is an extra, not core, and it is not our fallback.

4. **The rule going forward.** When a hot path needs vectorized or
   compiled speed, the answer is a kernel in our own crate. Numeric
   acceleration libraries — numpy, scipy, numba — are not a middle
   tier and do not enter `src/`. Small sets and lists stay stdlib
   Python. Active specs that planned numpy (132's lexical leg, 135's
   vector leg scored in numpy on MySQL/GENERIC, 136's power-iteration
   kernel, 137's `BM25Rerank` numpy fallback) are re-decided under
   this rule before they land: a Rust kernel where the scale is
   measured to need one, plain Python where it is not.

5. **Chunking's "absence by contract" is dissolved.** ADR 048 §3
   declared chunking the one exception to byte-identical engines
   because the pure engine had no tree-sitter. With one engine there
   is no exception to declare; structure-aware chunking is simply
   what vfs does.

## Consequences

- **The 3.11 CI failure is resolved by the model, not by a tolerance
  hack.** The pure tokenizer stops being a product on 2026-08-27; its
  parity test may legitimately skip off the table-generating
  interpreter (3.13 / Unicode 15.1 today) until the oracle move
  lands. The alternative fix — shipping the Unicode class tables to
  the pure tokenizer so both engines agree on every interpreter —
  was designed and prototyped (zero mismatches on 3.11 and 3.14) and
  is not needed once there is one tokenizer.
- **Easier:** one implementation per kernel; one coverage gate on one
  engine; no `VFS_PURE_PYTHON` leg in `scripts/ci.sh` or the Tests
  workflow; no interpreter-drift bugs; the seam stays byte-in /
  bytes-out with no `rust-numpy` and no abi3 conflict; the Python
  floor (ADR 035) no longer depends on numpy's release line.
- **Harder:** contributors need the extension built (`uv sync` does
  it; a Rust toolchain is the price, as with pydantic-core);
  free-threaded CPython and wheel-less platforms install from the
  sdist and wait for the build; a debugging session can no longer
  flip to a Python engine — the oracles in `tests/support/` are the
  readable reference instead.
- **Committed to:** the extension is required and the seam fails
  loudly; oracles live in `tests/support/` and pin parity, pinned to
  the generating interpreter where they must be; numpy is not in
  `dependencies` and does not return; every future accelerated path
  is a kernel in `crates/vfs-core`; specs 132, 135, 136 and 137 are
  re-read against decision 4 before their next slice; the spec that
  implements this (seam change, oracle move, CI-leg removal, the
  three kernels, numpy's removal from `pyproject.toml`) cites the
  2026-08-27 memo's numbers for its landing criteria.
