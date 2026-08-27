# 140 — plan

## Approach

Collapse first, move second. Slice A makes the seam unconditional and
deletes every `else: <pure>` branch while the pure functions still
live in `src/` (unreferenced by product code). That alone turns the
tree into a one-engine tree and is what the CI matrix gates. Slice B
then relocates the now-dead-in-product code into `tests/support/
oracles/` and re-points the parity suites. Doing it in this order
means every commit is green and the risky step (the seam) is proven
before the noisy step (file moves).

## §1 The seam (`src/vfs/native.py`)

```python
try:
    from vfs import _native as _ext
except ImportError as error:
    raise ImportError(
        "vfs requires its compiled extension vfs._native; reinstall the wheel "
        "or run `uv sync --reinstall-package vfs-py`"
    ) from error

EXPECTED_PROTOCOL: Final = 4
if _ext.PROTOCOL_VERSION != EXPECTED_PROTOCOL:
    raise ImportError(
        f"vfs._native speaks protocol {_ext.PROTOCOL_VERSION} but this vfs expects "
        f"{EXPECTED_PROTOCOL}; run `uv sync --reinstall-package vfs-py`"
    )

def extension() -> Any:
    """The live extension module — the handle every surface owner dispatches through."""
    return _ext
```

`structure_grammars()` returns `frozenset(_ext.supported_grammars())`;
`chunk_spans()` calls straight through. The module keeps its
no-imports-from-vfs property.

Testing a module-level raise: a subprocess (`uv run python -c`) with
`sys.modules["vfs._native"] = None` injected via `-c` before importing
`vfs.native` reproduces "absent"; a second subprocess sets a fake
module with `PROTOCOL_VERSION = 0`. Two tests, both asserting the
error text; the seam module has no other branch, so coverage is
whole.

## §2 Dispatch sites

| file:line | today | after |
|---|---|---|
| `models/code_grams.py:183` | `if ext is not None: return ext.distinct_gram_count(...)` + loop | `return extension().distinct_gram_count(data, cap)` |
| `models/postings.py:143` | Rust builder or `PurePostingsBuilder()` | `return extension().PostingsBuilder()` |
| `models/lexical.py:135` | Rust `tokenize` or `pure_tokenize` | `return extension().tokenize(content)` |
| `models/lexical.py:252` | Rust builder or `PureLexicalBuilder()` | `return extension().LexicalBuilder()` |
| `models/lexical.py:369` | Rust `lexical_score` or `pure_score_blocks` | Rust only; the `candidates` conversion stays (spec 142 removes numpy from it) |
| `pattern_matching/grep.py:203` | `_RustMatcher` or `_PureMatcher` | `_RustMatcher` only |
| `models/chunking.py:189` | `f"{active_core()}:{CHUNK_GENERATION}"` | `f"rust:{CHUNK_GENERATION}"` — keep the literal so existing stores' generation stamps stay valid and no reindex is forced |

The `Protocol` classes (`PostingsBuilder`, `LexicalBuilder`,
`ContentMatcher`) stay: they are the typed contract the Rust classes
satisfy and the oracles implement.

## §3 Oracles — what moves and what stays

- `PurePostingsBuilder` → `tests/support/oracles/postings.py`. It uses
  `_append_varint`; the oracle gets its own copy (a five-line helper;
  duplicating it in a test is fine, the product's copy stays for
  `encode_postings`).
- `encode_postings` stays in `src/`: `PureLexicalBuilder` is leaving,
  but `lexical.py` exports it and the write side of tests build blobs
  with it. Re-check at slice B; if the only callers are tests, move it
  too.
- `decode_postings` / `decode_varints` stay in `src/` until spec 141
  (grep's live path calls them).
- `pure_tokenize`, `_emit`, `_identifier_parts`, `_case_boundary`,
  `_TermList`, `PureLexicalBuilder` → `tests/support/oracles/lexical.py`.
  `pure_score_blocks` is rewritten here as a stdlib loop (per block,
  per posting: `score[doc] += idf * weight(tf, dl)`; sort by
  `(-score, doc)`; take `k`) — the study's `score_blocks_full`. The
  oracle takes `candidates` as a `set[int] | None`; the parity test
  converts.
- `distinct_gram_count`'s pure loop → `tests/support/oracles/grams.py`.
- `_PureMatcher`, `_gate`, `_walk_newline_capable`,
  `_class_admits_newline`, `_line_slices`, `_as_text`, `_escape_fixed`
  → `tests/support/oracles/matcher.py`. `pattern_matching/grep.py`
  keeps `_RustMatcher`, `_as_bytes`, `filter_candidates`,
  `split_lines`, `verify`, `match_texts`.
- Oracles may import from `vfs.models.*` public names (`ScoreBlock`,
  `iter_byte_trigrams`, `fold_content`, `BLOCK_SIZE` …) — that is the
  product's data model, not the engine. They must not import
  `vfs.native`. A test in `tests/support/oracles/test_isolation.py`
  walks `sys.modules` after importing the package and asserts.

## §4 Tests

- `tests/test_native.py`: drop `FORCED_PURE`, `needs_rust`, `_native`
  as optional; import oracles. `TestSeamSelection` → the two
  subprocess tests. `TestChunkSeam`: keep the Rust-path tests, drop
  the pure ones. `TestLexicalParity.test_character_classes_match_the_interpreter`
  → gated: `if unicodedata.unidata_version != _native.LEXICAL_UNICODE_VERSION:
  pytest.skip(f"oracle tokenizer follows the interpreter (Unicode
  {unicodedata.unidata_version}); tables are {…}")`, then the existing
  body with the tolerance removed (exact on the generating
  interpreter). `test_tokens_identical` and the fuzz test: same gate
  (their corpora happen not to drift, but the contract is now "equal
  on the generating interpreter"; keep them running elsewhere only if
  they stay green on 3.11–3.14 — check in slice B).
- `tests/pattern_matching/test_matcher_parity.py`: `pure_verifier`
  builds the oracle's `_PureMatcher`; `needs_rust` dropped;
  `TestDivergenceCatalog` and `TestPurePathSelection` deleted; the
  backtracking-residual timing test (`elapsed < 3.0`) is an oracle
  property and goes with the catalog.
- `tests/models/test_chunking.py`: `needs_structure` marker deleted
  (always structural); the two pure-engine tests deleted;
  `regen.py`'s `active_core()` guard deleted.
- `tests/storage/database/test_offload.py:439`: second
  `await storage.close()` (drive-by; separate commit).

## §5 CI

- `.github/workflows/test.yml`: delete the `Tests (pure-Python
  engine)` step and its `env`.
- `scripts/ci.sh`: delete the `tests pure-python` step; the coverage
  leg keeps lint, format, types, tests+cov, wheel size.
- `pyproject.toml` `[tool.coverage.report] exclude_lines`: nothing to
  add; the seam's `pragma: no cover` line is deleted with the branch.
- Skills: `.claude/skills/test_suite` and `db_test` — remove the
  pure-leg mention if present.

## Trade-offs

- **Subprocess tests for the seam** cost ~0.5 s each but are the only
  honest way to test a module-level raise without `importlib.reload`
  games that leak state into the rest of the suite.
- **Keeping `rust:` in the chunk generation stamp** is a small oddity
  (a literal that used to be a variable). The alternative — dropping
  the prefix and bumping `CHUNK_GENERATION` — forces a reindex of
  every store for no behavior change. Keep the literal; note it in
  the docstring.
- **Oracle scorer in stdlib** is ~11× slower than the Rust scorer on
  the 3-term/1,553-block shape (47 ms vs 4 ms measured). Parity tests
  run it on fixture corpora, not linux; fine.

## Verification

1. Slice A: `scripts/ci.sh` (full matrix). The 3.11 leg must go green
   via the §4 skip; 3.12 and 3.14 must stay green.
2. Slice B: `uv run pytest tests/test_native.py tests/pattern_matching
   tests/models -q` on 3.11, 3.13, 3.14 (`UV_PROJECT_ENVIRONMENT=.venv-ci/<v>`),
   then `scripts/ci.sh 3.13` at 100 %.
3. The landing-criteria grep over `src/`.
