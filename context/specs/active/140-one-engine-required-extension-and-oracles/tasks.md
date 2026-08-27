# 140 — tasks

## Slice A — the seam collapses, the pure leg retires

- [ ] A1 `src/vfs/native.py`: unconditional import; `ImportError` on
      absent / protocol mismatch with the fix in the message; delete
      `_resolve`, `active_core`, the `VFS_PURE_PYTHON` read;
      `extension()` returns the module (annotation `Any`, never
      `None`); `structure_grammars` / `chunk_spans` call straight
      through; rewrite the module docstring.
- [ ] A2 Collapse the seven dispatch sites (plan §2 table); delete
      each dead `else`; `chunking.chunk_generation` → `f"rust:{…}"`
      with a docstring line on why the literal.
- [ ] A3 `tests/test_native.py`: gate
      `test_character_classes_match_the_interpreter` (and, if they
      drift, the two token-parity tests) on
      `unidata_version == LEXICAL_UNICODE_VERSION`; replace
      `TestSeamSelection` with the two subprocess tests; drop
      `FORCED_PURE` / `needs_rust`; drop the pure `TestChunkSeam`
      tests.
- [ ] A4 `tests/models/test_chunking.py` + `fixtures/chunking/regen.py`:
      drop `needs_structure`, the two pure-engine tests, the
      `active_core()` guard.
- [ ] A5 `tests/pattern_matching/test_matcher_parity.py`: drop
      `needs_rust`, `TestPurePathSelection`; leave the rest for B.
- [ ] A6 `.github/workflows/test.yml`, `scripts/ci.sh`: delete the
      pure-Python step; `.claude/skills/{test_suite,db_test}`: remove
      the pure-leg step if present.
- [ ] A7 Drive-by, own commit: `tests/storage/database/test_offload.py`
      second `await storage.close()` after line 439.
- [ ] A8 Gate: `scripts/ci.sh` full matrix green; 100 % coverage on
      3.13; 3.11 and 3.14 green.

## Slice B — the oracles

- [ ] B1 Create `tests/support/oracles/{__init__,postings,lexical,grams,matcher}.py`;
      move `PurePostingsBuilder`, `pure_tokenize` + helpers,
      `PureLexicalBuilder`, the pure gram loop, `_PureMatcher` + gate
      + walk + slices out of `src/`.
- [ ] B2 Write the stdlib `pure_score_blocks` oracle (plan §3);
      delete the numpy one from `src/vfs/models/lexical.py`.
- [ ] B3 Decide `encode_postings`' home (stays if any product caller
      remains; else moves).
- [ ] B4 Re-point `tests/test_native.py`,
      `tests/pattern_matching/test_matcher_parity.py`,
      `tests/models/test_lexical.py`, `tests/models/test_postings.py`
      at the oracles; delete `TestDivergenceCatalog` and the
      backtracking-residual timing test.
- [ ] B5 `tests/support/oracles/test_isolation.py`: the package
      imports nothing from `vfs.native` (ledger O3).
- [ ] B6 Prove ledger rows O1–O5 (O4 is the coverage gate; O5 is the
      3.11/3.14 run).
- [ ] B7 Gate: 3.11 / 3.13 / 3.14 targeted runs, then `scripts/ci.sh 3.13`.

## Slice C — records

- [ ] C1 `CLAUDE.md`: drop the "until the ADR 057 spec lands" clause
      from the engine bullet.
- [ ] C2 `docs/plans/everything_is_a_file.md`: correct the fallback
      mention.
- [ ] C3 Header line in specs 132, 135, 136, 137 (spec §6 wording).
- [ ] C4 Landing note in `spec.md`; `STATUS.md` entry; move the folder
      to `archive/`.
