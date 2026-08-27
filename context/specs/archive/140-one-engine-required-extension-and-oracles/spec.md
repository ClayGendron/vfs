# 140 — one engine: the extension is required, pure Python becomes a test oracle, the pure CI leg retires

- **Status: landed 2026-08-27.** Slices A–C in one landing: the seam
  requires the extension, the seven dispatch sites collapsed, the
  pure implementations moved to `tests/support/oracles/`, the pure CI
  leg retired; `scripts/ci.sh 3.11 3.13 3.14` green (3.13 at 100 %
  coverage, 2,782 passed), the 3.11 leg green by the drift skip. First
  of the three-spec arc that implements ADR 057 (140 → 141 → 142).
  Details in the landing note below.
- **Born from:** ADR 057
  (`../../../decisions/057-one-engine-the-rust-extension-is-required.md`),
  decisions 1, 2 and 5; the finding that `pydantic-core` already
  makes vfs a compiled-extension package.
- **Date:** 2026-08-27
- **Owner:** Clay Gendron
- **Kind:** structural. No verb changes shape or output on the Rust
  engine — which is now the only engine. The pure implementations
  leave `src/` for `tests/support/`, where they referee parity tests
  and nothing else.
- **Depends on:** nothing pending. Supersedes in place the pieces of
  ADR 039 (pendulum's shipped fallback, decision 6), ADR 046 (the
  pure engine's wall discipline — the Rust engine's stands), ADR 048
  §3 (chunking's declared degradation).
- **Relates to:** spec 141 (the first kernel written once, after this
  lands), spec 142 (numpy's exit), the `CLAUDE.md` engine rule.

---

## Intent

`vfs._native` is required. Importing `vfs` without it — or with a
build whose `PROTOCOL_VERSION` does not match — fails loudly with a
message that names the fix. There is no `VFS_PURE_PYTHON`, no
`active_core()`, no pure-Python runtime path, and no CI leg that
exercises one. Each pure implementation survives only where it pins
a parity test, as a readable oracle in `tests/support/`, with no
coverage obligation and the freedom to skip on interpreters other
than the one that generated the Rust tables.

Same thing in other words: today every kernel exists twice and the
seam picks one at import. After this spec every kernel exists once,
and the second copy — where it is still worth reading — is a test.

## Shape

- **§1 The seam.** `vfs/native.py` imports `vfs._native`
  unconditionally. A missing module raises `ImportError("vfs requires
  its compiled extension vfs._native; reinstall the wheel or run `uv
  sync --reinstall-package vfs-py`")` from the original error. A
  protocol mismatch raises the same class with both numbers in the
  message — never a `RuntimeWarning`, never a downgrade.
  `active_core()`, `extension()`'s `None` branch, and the
  `VFS_PURE_PYTHON` read are deleted. `extension()` stays as the one
  handle every surface owner dispatches through (it can no longer
  return `None`; its annotation says so). `structure_grammars()` and
  `chunk_spans()` lose their engine-absent branches.
  `PROTOCOL_VERSION` stays 4: the extension's surface does not change
  in this spec.

- **§2 The dispatch sites.** Every `ext = extension(); if ext is not
  None: … else: <pure>` in `src/` collapses to the Rust call:
  `code_grams.distinct_gram_count`, `postings.postings_builder`,
  `lexical.tokenize`, `lexical.lexical_builder`,
  `lexical.score_blocks`, `pattern_matching.grep.compile_verifier`,
  and `chunking.chunk_generation` (the `active_core()` prefix becomes
  the literal `rust`, or the prefix is dropped and the generation
  stamp bumps — the plan decides; existing chunk fixtures regenerate
  either way).

- **§3 The oracles.** Pure implementations move out of `src/` into
  `tests/support/oracles/` (a package; one module per surface), kept
  only where a parity test reads them:
  - `oracles/postings.py` — `PurePostingsBuilder`, `encode_postings`
    stays in `src/` if a product path still needs it (the plan
    checks; today `PureLexicalBuilder` and tests are its callers).
  - `oracles/lexical.py` — `pure_tokenize` and its helpers,
    `PureLexicalBuilder`, and a **stdlib** `pure_score_blocks` (a
    deliberately slow, obviously-correct loop; the numpy spelling is
    deleted here, ahead of spec 142, because an oracle that needs
    numpy is not an oracle under ADR 057). The 2026-08-27 study's
    `kernels_py.py` spellings are candidate starting points.
  - `oracles/grams.py` — the pure `distinct_gram_count` loop.
  - `oracles/matcher.py` — `_PureMatcher`, `_gate`, the newline walk,
    and `_line_slices`, moved verbatim so the matcher parity suite
    keeps its referee.
  - Chunking has no oracle: the character splitter is a product path
    for unknown grammars, not an engine, and stays in `src/`.
  Oracles carry `# pragma: no cover`-free code because `tests/` is
  not under coverage; they import nothing from `vfs.native`.

- **§4 The parity tests, re-homed.** `tests/test_native.py` and
  `tests/pattern_matching/test_matcher_parity.py` import their pure
  side from `tests.support.oracles`. The `needs_rust` marker and
  `FORCED_PURE` are deleted (the extension is always present).
  `TestSeamSelection` becomes two tests: the import error's message
  on a missing module, and on a protocol mismatch (both by
  monkeypatching `vfs._native` / `PROTOCOL_VERSION` and reloading
  `vfs.native` in a subprocess — the plan picks the mechanism).
  `TestChunkSeam`'s "pure engine serves no grammars" and
  `test_chunking.py`'s "pure engine degrades to the character
  splitter" / "distinct generation" tests are deleted with the
  branch they pinned. **The Unicode parity test** pins the oracle
  tokenizer against the Rust tables only when
  `unicodedata.unidata_version == _native.LEXICAL_UNICODE_VERSION`
  and skips with a printed reason otherwise — the oracle is no
  longer a product, so interpreter drift is no longer a bug. The
  divergence catalog (`TestDivergenceCatalog`: the Turkic case orbit,
  `\N{...}`) is deleted: those were the pure *engine's* residuals,
  and there is no pure engine; the Rust-authority pins stay.
  `TestPurePathSelection` is deleted.

- **§5 CI and tooling.** The `VFS_PURE_PYTHON=1` step leaves
  `.github/workflows/test.yml` and `scripts/ci.sh`; the coverage leg
  runs once, on the one engine, still at 100 %. The `pragma: no
  cover` on the seam's `except ImportError` goes with the branch.
  `CLAUDE.md`'s engine bullet drops its "until the ADR 057 spec
  lands" clause. The `test_suite` and `db_test` skills lose any
  pure-leg step.

- **§6 Docs and records.** `native.py`'s module docstring is
  rewritten (the pendulum's "complete pure implementation in every
  wheel" is gone; the seam is a required import plus a protocol
  gate). `docs/plans/everything_is_a_file.md`'s fallback mention is
  corrected. Specs 132, 135, 136 and 137 each get one line in their
  header — "re-read under ADR 057 decision 4 on 2026-08-27: <what
  changes>" — using the 2026-08-27 memo §11 table: 132's "numpy
  fallback" clause is void and its scope intersect is spec 141's
  kernel; 135's fusion is plain Python and its client-floor cosine is
  a kernel candidate; 136's power iteration is a kernel, in the
  reindex phase; 137's numpy-fallback clause is void.

## Not in scope

- No kernel moves to Rust here (141, 142). numpy stays in
  `pyproject.toml` until 142; the product still imports it in
  `postings.py`, `grep.py`, `lexical.py`.
- No change to the wheel matrix, the sdist, or maturin's layout.
- The `test_offload.py` event-loop warning is a separate one-line
  fix (a second `await storage.close()`); it may ride slice A as a
  drive-by but is not this spec's contract.

## Mutation ledger

Each row is a deliberate break the suite must catch:

- **O1** seam silently falls back on `ImportError` — killed by the
  subprocess import test asserting the error class and message.
- **O2** protocol mismatch warns instead of raising — killed by the
  mismatch test.
- **O3** an oracle imports `vfs.native` — killed by an import-graph
  assertion in `tests/support/oracles/__init__.py`'s test.
- **O4** a dispatch site keeps a dead `else` branch — killed by the
  100 % coverage gate (the branch is unreachable).
- **O5** the Unicode parity test asserts on a non-generating
  interpreter — killed by running it on 3.11 and 3.14 (skips).

## Slices

- **A** — §1 + §2 + §5: the seam and dispatch sites collapse; the CI
  leg leaves; `tests/` updated only as far as needed to stay green
  (the pure classes are still importable from `src/` in this slice).
  Gate: `scripts/ci.sh` full matrix — this is the slice that turns
  the 3.11 leg green, by the §4 skip landing here.
- **B** — §3 + §4: the oracle package; the pure code leaves `src/`;
  parity suites re-homed; ledger rows proven.
- **C** — §6: docstrings, docs, the four spec header lines, the
  `CLAUDE.md` clause, the landing note.

## Landing criteria

- `grep -rn "VFS_PURE_PYTHON\|active_core\|_PureMatcher\|Pure[A-Z][A-Za-z]*Builder\|pure_tokenize\|pure_score_blocks" src/` is empty.
- `import vfs` in an environment whose `vfs._native` is absent raises
  `ImportError` naming `uv sync --reinstall-package vfs-py`.
- `scripts/ci.sh` (full 3.11–3.14 matrix) green, 100 % coverage on
  the one engine, one test step per leg.
- `tests/support/oracles/` exists, imports nothing from `vfs.native`,
  and every parity test reads its pure side from it.
- Specs 132, 135, 136, 137 carry their ADR 057 header line.

## Landing note (2026-08-27)

- **What landed.** `vfs/native.py` imports `vfs._native` unconditionally
  and raises `ImportError` naming `uv sync --reinstall-package vfs-py`
  when the module is absent or its protocol mismatches; `active_core`,
  `_resolve`, and the `VFS_PURE_PYTHON` read are gone; `extension()`
  never returns `None`. The dispatch sites in `code_grams`, `postings`,
  `lexical` (×3), `pattern_matching/grep`, and `chunking` call the
  engine directly; `chunk_generation()` keeps the literal `rust:` stamp
  so no store re-dirties. `PurePostingsBuilder`, `pure_tokenize` and
  its helpers, `PureLexicalBuilder`, the pure gram loop, and the
  `re`-based matcher with its slice/deadline machinery now live in
  `tests/support/oracles/{postings,lexical,grams,matcher}.py`; the
  numpy `pure_score_blocks` was replaced there by a stdlib loop, and
  the oracle codec is a byte-at-a-time LEB128 decoder. `_gate` returns
  nothing (refusals only); the oracle reads the newline walk itself.
- **Tests.** `TestSeamGate` pins both import refusals in subprocesses
  (the two module-level raises carry `pragma: no cover` for that
  reason); `tests/test_oracles.py` pins that no oracle module names the
  seam (O3). The Unicode parity test is exact on the generating
  interpreter and skips elsewhere with a printed reason (O5: 3.11
  skips, 3.13 asserts, 3.14 skips). The divergence catalog, the
  pure-path-selection tests, the backtracking-wall timing test, and
  the pure chunking tests went with the engine they pinned; the
  `\N{…}` engine refusal and the class-walk branches they covered are
  pinned again in `TestLanguageGate`. The `test_offload.py` leak (a
  second `await storage.close()`) rode along.
- **CI.** The pure-Python step left `test.yml` and `scripts/ci.sh`; the
  coverage leg runs once on the one engine.
- **Records.** Specs 132, 135, 136, 137 carry their ADR 057 re-read
  line; `CLAUDE.md`'s engine bullet points at the oracles.
- **Criteria.** The `src/` grep is empty — met. `import vfs` without
  the extension raises the named `ImportError` — met (subprocess pin).
  Full matrix green, one test step per leg — 3.11/3.13/3.14 run here;
  3.12 rides the push. Oracle package isolated — met. Spec header
  lines — met.
