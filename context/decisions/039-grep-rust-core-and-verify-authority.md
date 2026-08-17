# 039. The Grep Pipeline's Rust Core: Pendulum Packaging, a Shared Verify Authority, and Re-Derived Budgets

- **Status:** accepted 2026-08-17 — the record of spec 103's decision
  set, written at slice D per the spec's own plan. Three forks were
  resolved by Clay in session across the arc: the packaging posture
  (2026-08-16, two steps), fold ownership (2026-08-16, slice B), and
  the verify authority (2026-08-17, against the spike memo's
  recommendation). ADR 033's gate, ladder, epoch lifecycle, and
  truncation discipline are untouched; this ADR re-derives one of
  033's budget values and moves the match authority 033 assumed.
  The tree-sitter chunking fork (161 s of the reindex verb) remains
  open in spec 103 — it is an embedding-pipeline question, not a
  grep one.
- **Date:** 2026-08-17 (slices B–C landed 2026-08-16/17; recorded at
  slice D)
- **Deciders:** Clay Gendron
- **Context source:** the linux-tree benchmark study
  (`../research/studies/2026-08-16-linux-grep-benchmark/`, three
  dated records in its docstring), the slice A memos (read-path
  profile, verify-stage prior art, packaging —
  `../research/2026-08-16-*.md`), and the verify-authority spike
  (`../research/2026-08-17-verify-authority-spike.md`, study under
  `../research/studies/2026-08-17-verify-authority-spike/`).
  Implemented by spec 103 slices B–D.

## The deciding argument

The 2026-08-16 benchmark put numbers on the pipeline at real scale
(93,760 files / 1.59 GB, 25 queries): a 672 s index build at
~2.4 MB/s, verify-heavy rows losing to rg, and a 102 s
wrapped-wildcard pathology — all interpreted-throughput problems, no
design problems. Rust replaces the throughput; the design questions
were *where the boundary sits* and *who judges a match*.

The authority fork was the consequential one. The spike raced four
verify shapes and recommended keeping Python `re` the sole authority
behind a Rust prefilter — sound, fast enough, no parity burden. Clay
resolved the other way on a fact the speed comparison could not see:
vfs-py, vfs-js, and vfs-rs are the roadmap, and per-language
authorities (Python `re`, JS `RegExp`, Rust regex) drift by
construction, while one verifier in the shared core cannot. The
decision trades a bounded, pinned approximation error in the pure
fallbacks for structural identity across every future surface — and
it collapses the design: no translatable-subset contract, no
Confirmed/Candidate second engine, no orbit-parity obligation. The
pattern language simply *is* the regex-crate language, ripgrep's.

## Decisions

1. **One package, the pendulum model.** `vfs-py` uses maturin's mixed
   Rust/Python layout: the complete pure-Python implementation ships
   inside every wheel and the `vfs._native` extension rides beside it
   (`abi3-py311`, one wheel per platform). The seam
   (`vfs/native.py`) try-imports, gates on `PROTOCOL_VERSION`
   (now 2), warns once and falls back; `VFS_PURE_PYTHON=1` forces the
   fallback; wheel-less platforms build from the sdist via maturin's
   self-bootstrapping toolchain. Rejected: the packaging memo's
   two-package shape (a toolchain download on exotic platforms is the
   accepted residual).

2. **The engine is binding-free; bindings are thin.** Engine logic —
   gram extraction, the distinct-gram gate, postings accumulation and
   varint encoding, and now pattern compilation and line-hit finding —
   lives in `crates/vfs-core` with no pyo3 outside the `python`
   feature. Future napi/wasm and native-Rust surfaces bind the same
   core.

3. **Python folds; the engine takes pre-folded bytes.** `casefold` is
   C-speed (~3 s of a 191 s reindex) and reproducing sre's exact
   case orbit in Rust would carry a per-CPython-version parity
   burden. One fold implementation, in `vfs.models.code_grams`;
   revisit only on measured need.

4. **The shared Rust core is the match authority.** The grep pattern
   language is the regex-crate language: backreferences,
   look-arounds, atomic groups, possessive quantifiers, conditional
   groups, `\A`/`\Z`, and the ASCII/locale flags classify `invalid` —
   ripgrep's posture. A shared sre-AST gate
   (`vfs.pattern_matching.grep`) refuses the same constructs with
   the same messages on both engines, so an extension-less install
   never serves a wider language than a wheel.

5. **Lines are presentation, not matching — enforced structurally.**
   The core parses patterns to the regex-syntax HIR, strips `\n`
   from every class (refusing patterns that can only match a line
   terminator), strips wrapping `.*`/`.*?` runs (a line matches
   `.*X.*` exactly when it matches `X`, and the wrapped form defeats
   the engine's literal prefilter — the 102 s pathology's actual
   fix), and scans bodies whole with enclosing-line recovery. No
   separate memmem stage: after the reduction, the crate's own
   literal engine prefilters at memmem speed, so no hit ever runs a
   second engine.

6. **The pure fallback approximates the authority, pinned.** It
   matches with Python `re` under the same gate and line law
   (whole-text scan only when the gate's walk proves the pattern
   cannot touch `\n`). Known residuals are cataloged and pinned
   per-engine in `tests/pattern_matching/test_matcher_parity.py`:
   the `re.IGNORECASE` Turkic case orbit (the fallback over-matches
   İ/ı where the authority and ripgrep do not) and Python-only
   spellings like `\N{...}` (served by the fallback, refused by the
   authority). Movement in a residual fails a test, never drifts
   silently.

7. **Budgets re-derived at linux scale.** `CANDIDATE_BUDGET` rises
   10,000 → **25,000**, a constant, not corpus-scaled: candidate
   cost is fetch-dominated at ~75 µs each, so 25,000 bounds a
   saturated call near ~2 s; the sweep showed every benchmark row
   whose width search semantics can justify un-truncates by 25,000,
   while the one wider row (`copyright -i`, 62% of the corpus) is
   bulk retrieval that stays loudly truncated with the refine
   guidance — and corpus-scaling would make hot-row latency grow
   with corpus size, backwards for the agent audience. The wall
   deadline now also runs inside the verify body loop (the profile
   caught 102 s against a 10 s wall when it was batch-granular).
   Big-file caps (`MAX_INDEXABLE_BYTES`, `MAX_DISTINCT_GRAMS`)
   are unchanged: the unindexable overlay tail costs ~13 ms per
   call after slice C, so no cap pressure remains.

## Consequences

- The bench gate holds: on the recorded machine every one of the 25
  rows beats rg (vfs 115–644 ms at the 10,000 budget, ≤ ~1.8 s at
  the landed 25,000, vs rg 2.0–3.6 s), the query ladder improved
  throughout (reindex build 4.7 s → 0.9 s at the 10K tier), and the
  zero-hit floor fell 631 ms → 13 ms.
- Grep behavior changed at the contract surface, knowingly: patterns
  outside the regex-crate language now refuse as `invalid` instead
  of scanning or silently matching, and case-insensitive matching no
  longer unifies the Turkic orbit on the accelerated path. Both are
  ripgrep-compatible and battery-pinned.
- The index needed no change: its fold is a superset of the
  authority's case orbit, so candidate nomination stays sound.
- The differential battery and the full suite run green on both
  sides of the seam at every landing (pinned by CI's pure-fallback
  leg), and `tests/test_native.py` plus the parity module keep the
  engines byte-identical where identity is the contract.
