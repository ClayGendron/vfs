# 073 — Glob adopts segment-aware semantics (`*` stops at `/`, `**` recurses)

- **Status:** shaped — drafted 2026-07-14 from the 072 slice-7
  design-precedent review (four-agent reference sweep over fsspec,
  pyfilesystem2, CPython, SQLite/Postgres, zoekt/codesearch, JuiceFS,
  and the `src2` quarry). Owner decision 2026-07-14: adopt full
  segment-aware glob, "the way it works for normal coding agents."
  Open questions resolved 2026-07-14 (below); the LIKE-prefilter and
  ext-pushdown soundness claims are machine-verified by
  `spike/verify_like_superset.py` (323k authoritative matches, zero
  prefilter drops; 50k matches kept by the derived-ext filter) and
  the spike itself survived a three-agent adversarial audit — fuzz,
  mutation, and differential testing against real PostgreSQL 18.0
  (see *Verification evidence*). Ready for plan.md.
- **Date:** 2026-07-14
- **Owner:** Clay Gendron
- **Kind:** contract change (pattern-language semantics on the `glob`
  verb and grep's `globs`/`globs_not` filters — no new verbs, no
  schema)
- **Depends on:** 049 (`SupportsPatternSearch`), 071 (ingress gates —
  pattern arrives as a gated `str`; malformed patterns classify, never
  raise)
- **Relates to:** 072 (slice 7 landed the database glob on the current
  semantics; Pass C grep consumes the same pattern language for its
  `globs`/`globs_not` filters — land this before or with Pass C), the
  storage conformance suite (pins the contract both backends must
  match)

## Intent

Every glob in the VFS today uses stdlib `fnmatch` semantics: `*`
crosses `/`, `?` matches `/`, and `**` is not special (two stars ≡ one
star). No one chose this — the memory backend reached for Python's
`fnmatch` module and the conformance suite then pinned what it did.
The 2026-07-14 precedent review found **zero** reference support for
that contract and four references against it:

- **fsspec** compiles globs through CPython's `glob_translate`
  (`filesystem_spec/fsspec/utils.py:713-742`, copied from CPython
  PR 106703): `*` → `[^/]*`, `**` matches any number of *whole* path
  components, and `**` inside a component raises.
- **pyfilesystem2** is segment-aware in both engines
  (`fs/wildcard.py:155` maps `*` → `[^/]*`; `fs/glob.py:80` refuses
  `**` inside `_translate`, recursion handled per component).
- **CPython's `glob`/`pathlib`** — the semantics every coding agent
  and shell user carries.
- **This project's own quarry**: `src2/vfs/patterns.py:79-91`'s
  authoritative matcher was segment-aware (`*` → `[^/]*`,
  `?` → `[^/]`, real `**`). The current fnmatch contract is a
  regression the rewrite introduced, not inherited design.

The caller-visible damage (demonstrated 2026-07-14): `/docs/*.txt`
returns files three levels deep; `*/b.txt` matches at any depth; and
`/docs/**/*.txt` **silently misses** `/docs/a.txt` because `**/` must
consume a character — the one operator callers use to be explicit
about recursion is a false friend. Both over- and under-matching, so
neither semantics is a superset of the other.

One sentence: **glob means what it means in every tool an agent
already knows — `*` within a segment, `**` across segments — compiled
at one chokepoint both backends and grep's glob filters share.**

## Shape (pinned)

1. **Semantics: CPython `glob.translate`.** `*` matches within one
   segment (`[^/]*`); `?` matches one non-separator character; `**`
   as a whole component matches zero or more components; `[seq]` /
   `[!seq]` character classes as today. Matching stays
   case-sensitive (the `fnmatchcase` posture carries over).
2. **Hidden files match.** `include_hidden=True` — this is an agent
   namespace, not an interactive shell; dotfiles are ordinary rows.
   The reserved `/.vfs` subtree stays invisible via the liveness
   scope (072 §9), which is namespace policy, not pattern policy.
3. **One compile chokepoint.** A live `src/vfs/patterns.py`
   (resurrecting the quarry's name) exposing
   `compile_glob(pattern) -> re.Pattern[str]`, wrapping
   `glob.translate(pattern, recursive=True, include_hidden=True,
   seps="/")`. Every consumer — memory glob, database glob, Pass C
   grep's `globs`/`globs_not` — compiles here and nowhere else.
4. **Compile-first classification.** Pattern compilation happens
   before any row is touched, and a refused pattern classifies
   `invalid` naming the defect, per the 071 never-raise canon and
   the 072 §6 compile-first doctrine. Whether `**` inside a
   component (`a**b`) is refused or degraded is an open question
   below — the references split (verified 2026-07-14: CPython's
   `glob.translate` silently collapses it to `a[^/]*b`; fsspec and
   pyfilesystem2 both raise).
5. **Name-vs-path dispatch survives — and extends to grep's glob
   filters.** A pattern with no `/` still matches the leaf name (the
   sanctioned pyfilesystem2 `FS.match` shape); since names contain no
   separator, the name arm is behaviorally unchanged. A pattern with
   `/` matches the full path under the new semantics — that arm is
   where the change lives. The dispatch is load-bearing for grep:
   today its `globs`/`globs_not` filters match every pattern against
   the full path, which is harmless only because fnmatch's `*`
   crosses `/`. Under segment semantics a path-only `*.py` filter
   matches *nothing* (the leading `/` alone kills it), so grep's
   filters must adopt the same name-vs-path dispatch as the verb —
   pinned here, asserted in conformance once Pass C lands.
6. **The database LIKE prefilter keeps its structure; the translator
   becomes `**`-aware.** The prefilter-then-authoritative-verify
   structure (zoekt/codesearch doctrine, confirmed 2026-07-14) is what
   makes this semantics change safe at all: the LIKE must be a
   *superset* of the authoritative matcher — over-matching costs wasted
   row fetches, under-matching silently loses results before the
   verifier sees them. The existing char-by-char `_glob_like` is **not**
   a superset under the new semantics: `/docs/**/*.txt` translates to
   `/docs/%%/%.txt`, which still demands a literal `/` after the
   wildcard and drops the zero-depth match `/docs/a.txt` — the same
   consume-a-character trap the new semantics exists to kill, one layer
   down (demonstrated against sqlite 2026-07-14; spike claim 1). The
   fix is one rule: a whole `**` component fuses with its trailing
   separator into a single `%` (`/docs/**/*.txt` → `/docs/%%.txt`).
   The full translation: `*` → `%` and `?` → `_` (both deliberately
   loose — they cross `/` where the glob does not), `**`-component +
   separator → `%`, LIKE metacharacters escaped; `[` classes and
   mid-component `**` are inexpressible and fall back to the escaped
   literal-prefix LIKE. Soundness is machine-verified:
   `spike/verify_like_superset.py` enumerates ~22,300 patterns × 2,379
   paths (dotfiles, LIKE metacharacters *including backslash* as data
   and pattern literals, case variants, `*.*`, a >32-char extension,
   every operator placement) and finds zero prefilter drops under both
   the ANSI case-sensitive reference (Postgres posture) and sqlite's
   builtin LIKE (spike claims 2–3). Note the spike proves *soundness*
   (superset), never *tightness* — a looser translation would pass
   identically; selectivity is a performance property, pinned only by
   the listed mapping. Keep the unconditional verify even
   where a LIKE translation looks exact — sqlite's LIKE is
   ASCII-case-insensitive by default, so even an "exact" translation is
   already a superset on case alone; the verifier is load-bearing
   today, not just after this change.
7. **Extension narrowing pushes down to the indexed `ext` column.**
   The entries table already carries an indexed lexical `ext` column
   (plus a composite `(ext, kind)` index); glob currently ignores it
   and filters the `ext` parameter in Python. Two pushdowns land
   here, both pure AND-ed narrowing under the same
   prefilter-then-verify doctrine:
   - **The `ext` parameter** becomes `ext IN (...)` in SQL (the
     Python check stays — verify is unconditional). This pushdown is
     *not* spike-covered — its soundness rests on the column being
     written by the same `extract_extension` the Python check uses;
     the conformance suite asserts the agreement.
   - **A pattern-derived extension**: when the last segment's
     trailing literal (after its last wildcard) contains a dot with
     characters after it — `**/*.txt`, `[a].txt`, `?.py` — every
     possible match's extension is pinned, and the filter
     `ext = '<derived>' OR name = '<literal dot-suffix>'` narrows the
     scan. The OR arm is not optional: `*.txt` matches the pure
     dotfile `.txt`, whose lexical extension is `None`
     (`extract_extension` requires the dot past position 0) — a bare
     `ext = 'txt'` filter silently drops it. Soundness is
     machine-verified (spike claim 4: 5,556 derivable patterns,
     50,520 authoritative matches, zero drops; corpus includes
     dotfile names, `*.*`, and a >32-char extension — each kills a
     mutation-tested wrong implementation). Derived ext is
     lowercased; matching stays case-sensitive in the verifier, so
     case looseness errs superset-ward like everything else in the
     prefilter.
   This is what rescues anchor-free patterns: `**/*.txt` produces the
   unsargable `LIKE '%.txt'`, but `ext = 'txt'` is an indexed
   equality the planner can drive instead. **Column semantics pinned
   lexical**: `ext` stores `extract_extension` of the name for
   *every* kind (a directory named `docs.txt` has ext `txt`) —
   matching the live `ext`-parameter contract in both backends.
   `Path.ext` (kind-gated to files) is presentation, not the write
   rule; the 072 write path must populate the column through
   `extract_extension`, the same chokepoint the read side compares
   against.

## Verification evidence (2026-07-14)

`spike/verify_like_superset.py` pins five claims: (1) the current
char-by-char translator under-matches (the story's motivating bug,
demonstrated); (2) the fixed translator is a zero-drop superset over
323k authoritative matches; (3) sqlite LIKE ⊇ the ANSI reference
(case folding is its only looseness); (4) derived-ext narrowing keeps
every match; (5) no emitted LIKE ever contains a dangling escape.

A three-agent adversarial audit then attacked the spike itself:

- **Fuzzing**: ~11.5M randomized/exhaustive trials (deep nesting,
  unicode with case-growth under `.lower()`, newlines, `***`,
  unmatched `[`, escape chars as data) — zero counterexamples, zero
  crashes in the `glob.translate` → translator → sqlite path.
- **Mutation audit**: 12 deliberate bugs injected into copies of the
  translator and `derive_ext`; the corpus caught every unsound mutant
  after four blind spots (backslash ×2, `*.*`, >32-char ext) were
  closed with targeted corpus additions. Looser-but-sound mutants
  survive by design — the spike proves soundness, not tightness.
- **Engine fidelity**: the hand-written ANSI reference was
  differential-tested against **real PostgreSQL 18.0** (psql, psycopg
  bound params, and SQLAlchemy `.like(escape='\\')` end-to-end) plus
  DuckDB 1.5.4 — 100% agreement on ~76k corpus pairs and all
  adversarial/fuzz pairs; sqlite's ASCII case folding was the only
  divergence anywhere, always superset-ward.

Two portability facts worth pinning from that audit: Postgres errors
on a dangling-escape LIKE *data-dependently* (some rows error, others
silently drop), which is why claim 5 is load-bearing and checked
structurally; and SQLAlchemy renders the ESCAPE character inline (the
pattern is a bound parameter, the escape char is not), so
`standard_conforming_strings=off` — deprecated since Postgres 9.1 —
is an unsupported configuration.

## Touch points

- `src/vfs/patterns.py` — new module (mined from the quarry; the
  quarry keeps its escape-handling fixes noted in the 072 review).
- `src/vfs/storage/backends/memory.py` — `glob` and grep's
  `globs`/`globs_not` filtering swap `fnmatch.fnmatchcase` for the
  chokepoint.
- `src/vfs/storage/backends/database/reads.py` — `glob_rows` swaps
  its verifier; `_glob_like` gains the `**`-component fusion rule
  (§6) and refuses mid-component `**` to the literal-prefix fallback;
  the `ext` parameter and the pattern-derived extension push down to
  the indexed `ext` column (§7). The verified reference
  implementations are `glob_like_fixed` and `derive_ext` in
  `spike/verify_like_superset.py`.
- The 072 write slices populate the `ext` column lexically via
  `extract_extension` for every kind (§7) — a cross-story dependency
  to coordinate: derived-ext pushdown must not land before the
  column is written.
- `pyproject.toml` — `requires-python` bumps `>=3.12` → `>=3.13`:
  `glob.translate` landed in 3.13, and the chokepoint wraps it rather
  than vendoring a translator. (Runtime and `ty` already target 3.13;
  only the floor moves.)
- `tests/storage_conformance.py` — rows pinning fnmatch behavior
  update to pin the new contract (e.g. `*/x.py` matching `/a/b/x.py`
  becomes `**/x.py`); new rows pin the demo table: direct-children
  `*`, one-level `*/`, zero-depth `**`, dotfile matching, `a**b` →
  `invalid`.
- `src/vfs/ops.py` / `src/vfs/params.py` / skills docs — the `glob`
  and `grep` surface text states the semantics in one line.
- `src2/vfs/patterns.py` — delete once mined (fully superseded).

Greenfield note: no stored data or wire clients depend on the old
semantics; the only migration is the conformance suite and any
in-repo callers of `glob` with patterns written against fnmatch
behavior.

## Acceptance criteria

- Over the tree `{/notes.txt, /docs/a.txt, /docs/deep/nested/b.txt}`:
  `/docs/*.txt` → exactly `/docs/a.txt`; `*/b.txt` → nothing;
  `/docs/**/*.txt` → both `.txt` rows under `/docs` including the
  zero-depth one; `*.txt` (name arm) → all three.
- A conformance row whose **only** match is zero-depth under `**`
  (the `/docs/**/*.txt` → `/docs/a.txt` case) — this is the row a
  broken prefilter loses, and byte-identical memory/sqlite legs are
  what catch it.
- `**` inside a component (`a**b`) classifies `invalid` naming the
  defect — on both arms, both backends.
- A bare `**` name-only pattern matches every name (behaviorally
  `*`); pinned by a test.
- Dotfile names match `*` patterns; `/.vfs` stays excluded by the
  liveness scope, not by the pattern language.
- Memory and sqlite conformance legs byte-identical on every glob
  row; grep's `globs`/`globs_not` compile through the same
  chokepoint **with the same name-vs-path dispatch** (asserted once
  Pass C lands).
- A conformance row pinning the dotfile-extension edge: `*.txt`
  matches a file named `.txt`; `ext=("txt",)` filters it out
  (lexical extension is `None`) — identical on both backends, both
  with and without the derived-ext pushdown active.
- `spike/verify_like_superset.py` passes against the landed
  `_glob_like` and `derive_ext` (claims 2–4; claim 1 becomes moot
  once the fix lands and may be retired with the spike).
- No `fnmatch` import remains in any storage backend.
- `requires-python >= 3.13`; `ruff`/`ty` at zero; no new
  suppressions.

## Open questions — resolved 2026-07-14

- **`**` inside a component** (`a**b`) → **classify `invalid`** (the
  fsspec/pyfilesystem2 posture — loud beats hiding a typo'd
  recursion). Stdlib will not refuse it (verified: `glob.translate`
  silently collapses `a**b` to `a[^/]*b`), so the chokepoint
  pre-checks components before calling `translate`. This also keeps
  the LIKE translator's fusion rule trivially safe: only
  whole-component `**` ever reaches it.
- **`**` in a name-only pattern** (no `/`) → **treat as `*`**, for
  free: `**` compiles to `(?s:.*)` and names contain no separator
  and are never empty, so it is behaviorally identical to `*`'s
  `[^/]+`. No special-casing; pinned by a test.
- **Timing against 072 Pass C** → **land before grep.** Grep's glob
  filters are born on the right semantics *and* the right dispatch
  (§5) instead of being retrofitted.
- **`max_depth` budget on glob** → **out of scope.** This story
  changes the pattern language only.

## Deferred (recorded, not in scope)

- **Anchor-free patterns without a derivable extension scan.** A
  pattern with no literal prefix and no extension tail (`**/*rc`,
  `**/Makefile*`) defeats both the path B-tree and the §7 ext
  pushdown, and scans the path column — bounded (N rows × short
  strings) and correct, just unindexed. The common anchor-free shape
  (`**/*.py`) is already rescued by §7. The remaining scale lever is
  engine-native: `pg_trgm` GIN on the path column per story 007's
  schema, Postgres-only, a pure accelerator with zero contract risk
  because correctness lives in the verifier. Revive 007 when the
  Postgres dialect lands; no custom trigram machinery for paths (the
  013/072 posting index is content-scale doctrine, not path-scale).
