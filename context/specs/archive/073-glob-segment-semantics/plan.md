# 073 — Plan: segment-aware glob at one chokepoint

Implements `spec.md`'s pinned shape (§§1–7) as four slices, each
landing green (`uv run pytest tests/ -q`, `ruff`, `ty`, and — because
this touches the database read path — the four Docker engine legs via
the `db_test` skill at the contract-changing slices). Drafted
2026-07-31 against the tree at `5630aa4`.

The normative reference implementations are `glob_like_fixed` and
`derive_ext` in `spike/verify_like_superset.py` (spec §*Verification
evidence*); the landed code mirrors them and the endgame re-runs the
spike against the landed functions.

## Tree drift ledger — spec touch points vs. today's tree

The spec was shaped 2026-07-14; four touch points have moved under it.
This plan maps onto the current tree:

1. **The memory backend touch point is retired.** ADR 028 re-platformed
   `InMemoryStorage` as a construction-only subclass of
   `DatabaseStorage` (`backends/memory.py` is 45 lines, no fnmatch).
   The only `fnmatch` in live `src/` is `storage/globbing.py`; one
   authority swap covers every leg.
2. **The conformance suite lives at `tests/support/storage_contract.py`**
   (runner: `tests/storage/test_conformance.py`), not the spec's
   `tests/storage_conformance.py`. The fnmatch-pinning rows to update
   are the glob block at `storage_contract.py:915` ff.
3. **The ext column agreement mostly resolved itself — one escape
   remains.** The spec worried the write path might not populate `ext`
   lexically for every kind. It does: `Path.ext` is lexical and
   kind-free (`paths.py:244-250`) and `Entry._derive_and_measure`
   stamps it (`entry.py:216-217`). The residual gap is that an
   explicit caller-supplied `ext` survives (`model_fields_set` check)
   while the Python ext gate is deliberately path-derived
   (`globbing.py:6-9`) — a divergent stored value would make the §7
   pushdowns unsound. Decision 3 below closes it.
4. **Grep has no live filter code to retrofit** (`grep` is a
   classified stub). 073 delivers the chokepoint and the dispatch
   contract; Pass C grep is *born* on them. The conformance assertion
   for grep's `globs`/`globs_not` stays deferred to Pass C, as the
   spec already says.

## Decisions pinned here (the spec delegated these to plan.md)

1. **Chokepoint home and shape.** `src/vfs/glob_patterns.py` (new —
   renamed from the drafted `patterns.py`, owner call at
   implementation) absorbs
   `storage/globbing.py`, so the pattern language has exactly one
   module. Split per the no-union rule (ADR 011 — policy checks
   partial, value-producers total):

   ```python
   def glob_defect(pattern: str) -> str | None: ...
   def compile_glob(pattern: str) -> re.Pattern[str]: ...
   def compile_filter(pattern: str, ext: tuple[str, ...]) -> GlobFilter: ...
   ```

   `glob_defect` returns a reason for a refusable pattern and `None`
   otherwise; the one defect at this story is mid-component `**`
   (any `/`-split component that contains `**` and is not exactly
   `**` — this also catches `***`, matching the fsspec/pyfilesystem2
   posture). `compile_glob` assumes validity, **anchors first**
   (spec resolved question, 2026-07-31 as revised: gitignore-exact —
   a path-arm pattern not starting with `/` gets a bare `/`
   prepended, so `src/*.py` is root-anchored and `**/x.py` is the
   explicit any-depth idiom; name-arm patterns are untouched), then
   wraps `glob.translate(pattern, recursive=True,
   include_hidden=True, seps="/")`. The anchoring normalization is
   inside the chokepoint so the LIKE translator and the ext deriver
   only ever see anchored patterns. `GlobFilter` migrates as-is (name-vs-path dispatch,
   path-derived ext gate, `matches`), swapping
   `fnmatch.fnmatchcase` for the compiled regex; `compile_glob`
   runs once per verb call, not per candidate.
   `storage/globbing.py` is deleted; `reads.py` imports move.
2. **Refusal site.** The `glob_defect` gate runs in `glob_rows`
   before any statement (the 072 §6 compile-first doctrine): a
   defect classifies `invalid`, names the pattern and the defect,
   and touches no rows. The router inherits the refusal through
   normal dispatch; `params.py` is untouched — pattern *content* is
   pattern-language semantics, not the 071 type/domain table.
3. **ext agreement becomes structural.** `Entry` derives `ext` from
   the path unconditionally — the explicit-override escape
   (`entry.py:216`) is removed. Nothing in `src/` or `tests/`
   supplies an explicit `ext` today, and the §7 pushdowns are sound
   only if `stored ext == extract_extension(path)` on every row; an
   override that the read side deliberately ignores is a contract
   contradiction, not a feature. Refusing a mismatched explicit
   `ext` was considered and rejected — the model already normalizes
   in this spot (directory `content` → `None`), and there is no
   caller to warn. A conformance row pins the agreement: writing an
   entry with a divergent explicit `ext` observes the lexical value.
4. **The ext-parameter pushdown is bounded, never chunked.** `ext`
   becomes `ext IN (...)` only when `len(ext) <=` the membership
   budget; a larger tuple skips the pushdown entirely (the Python
   gate stays authoritative either way). Chunking would turn a
   filter into a fan-out for a parameter that is small in every real
   call.
5. **The LIKE translator stays `reads.py`-private; `derive_ext` is
   chokepoint-public.** (Revised at implementation, owner call:
   the original pin kept both in `reads.py`.) `_glob_like` speaks
   LIKE — a SQL concern beside its only consumer. `derive_ext`
   turned out to be pure pattern analysis (wildcard grammar in, a
   pattern fact out, zero SQL vocabulary), so it lives in
   `glob_patterns.py`; the tail law it must share with stored
   extensions (lowercase, non-empty, ≤32) was hoisted to
   `paths.normalize_extension`, called by both `extract_extension`
   and `derive_ext` — agreement is structural, not documented.
   Soundness is still pinned by the spike importing the landed
   functions directly (endgame).
6. **Python-floor mechanics.** `requires-python >=3.13`, ruff
   `target-version = "py313"`, `uv lock` refreshed, and any 3.12
   interpreter pins in `.github/workflows/` trued up in the same
   slice that first calls `glob.translate`.

## Slice 1 — prefilter fusion (pure loosening, green under old semantics)

`_glob_like` learns the `**`-component rule: a whole `**` component
fuses with its trailing separator into a single `%`
(`/docs/**/*.txt` → `/docs/%%.txt`); `*` → `%` and `?` → `_`
unchanged and deliberately loose; `[` classes and mid-component `**`
fall back to the escaped literal-prefix LIKE, mirroring
`glob_like_fixed`. This is a strict superset move under **both** the
old fnmatch authority and the coming segment authority, so it lands
first and alone — the zero-depth acceptance row in slice 2 depends
on it, and landing it separately keeps the semantics swap free of
prefilter risk.

- Unit rows in `tests/storage/database/test_reads.py`: the fusion
  case, the mid-component fallback, LIKE-metacharacter escaping
  including backslash, no dangling escape (spike claim 5, asserted
  structurally on the translator output).
- Suite stays green with zero conformance-row changes — that *is*
  the superset proof at this slice.

## Slice 2 — the semantics swap (the contract change)

1. `src/vfs/glob_patterns.py` lands per decision 1; `storage/globbing.py`
   deleted; `reads.py` swaps its import to `compile_filter`.
2. `glob_rows` gains the `glob_defect` gate per decision 2.
3. `pyproject.toml` floor bump per decision 6.
4. Conformance true-up in `storage_contract.py`: rows built on the
   fnmatch any-depth idiom migrate to `**/` (`*/x.py` matching
   `/a/b/x.py` becomes `**/x.py`; `*/x.py` itself now pins depth
   one); new rows pin the spec's acceptance table —
   direct-children `*`, one-level `*/`, the zero-depth `**` row
   whose **only** match is `/docs/a.txt` (the row a broken prefilter
   loses), implicit anchoring (`src/*.py` ≡ `/src/*.py` root-only;
   `**/x.py` reaches root level), dotfiles match `*`, `a**b` →
   `invalid` on both arms, bare `**` as a name-only pattern behaves
   as `*`. These anchoring rows are tightness-side pins the spike
   structurally cannot provide (an empty match set drops nothing),
   so they live here.
5. Surface text: one-line semantics statements on the `glob`/`grep`
   docstrings in `base.py`, `ops.py`, and `params.py`.

Run the four Docker legs here — this is the slice where every
engine's LIKE/regex behavior must agree with the new authority.

## Slice 3 — ext pushdowns

1. `entry.py`: derive-always `ext` per decision 3, docstring updated;
   model test drops the override path and pins the derivation.
2. `reads.py`: the `ext` parameter pushes down per decision 4; the
   pattern-derived extension filter lands as
   `ext = '<derived>' OR name = '<literal dot-suffix>'` (the OR arm
   rescues the pure-dotfile match, e.g. `*.txt` vs a file named
   `.txt` whose lexical ext is `None`), derived ext lowercased,
   mirroring `derive_ext`. Both filters AND into the existing
   prefilter; the authoritative verify is untouched.
3. Conformance rows: the dotfile-extension edge (`*.txt` matches a
   file named `.txt`; `ext=("txt",)` filters it out) on every leg;
   the decision-3 agreement row. Unit rows in `test_reads.py` cover
   the derivation boundaries (no derivable ext, `*.*`, >32-char
   tail, wildcard after the dot) where the pushdown must not fire.

Run the four Docker legs again (new SQL filter shapes).

## Slice 4 — endgame

1. Re-point `spike/verify_like_superset.py` at the landed code:
   import `_glob_like`/`_derive_ext` from
   `vfs.storage.backends.database.reads`, retire claim 1 (moot once
   the fix lands) and its old-translator copy, fix the stale run
   path in the module docstring (missing `active/` segment). Run it;
   claims 2–4 must pass against the landed functions.
2. Eradication: no `fnmatch` import anywhere in `src/vfs/`; `ruff`/
   `ty` at zero; no new suppressions.
3. `src2/vfs/patterns.py` deleted (mined — the quarry's
   segment-aware matcher is superseded by the landed chokepoint).
4. Docs true-up: spec status → landed; `STATUS.md` entry; the
   `open-questions.md` grep entry untouched (grep adoption is Pass
   C's acceptance).

## Risks and non-changes

- **sqlite's ASCII-case-insensitive LIKE** stays a superset-ward
  looseness; the unconditional verify already absorbs it (spec §6).
- **Selectivity regression on `**` patterns**: the fused `%` is
  looser than the old translation, so `**` patterns fetch more
  candidates. Bounded by the existing fan budget; correctness is
  unaffected; no new budget lands here.
- **`?` → `_` crosses `/`** in the path arm — deliberate superset,
  verifier exact.
- **`max_count`, scoping, liveness, and the meta bypass** are
  untouched; this story changes the pattern language and the
  prefilter only.
- **Cross-story**: Pass C grep must call `glob_defect` +
  `compile_filter` for `globs`/`globs_not` with the same
  name-vs-path dispatch — pinned in the spec (§5), asserted in
  conformance when Pass C lands.
