# 098 — Literal text at the seams: root quoting, LIKE brackets, line semantics

- **Status: implemented and committed 2026-08-13 (`a577c28`)** — all
  four slices landed in one pass. Born from the review campaign memo
  (`research/2026-08-13-glob-grep-indexing-review-campaign.md`,
  findings 4, 5, 12, 21). No open forks — every fix direction was
  verified in the campaign.
- **Landing ledger (2026-08-13):**
  - Suite 2,265 passed at 100.00% coverage; `ruff`/`ty` zero.
  - Four Docker legs green: Postgres 203 / MySQL 204 / MSSQL 205 /
    Oracle 202 (4 capability skips each). MSSQL proves §2 (the three
    bracket rows pass with the escape live); Oracle proves the
    ORA-01424 guard (brackets unescaped there, rows still green).
  - Hand-verified mutant: flipping `like_bracket_class=False` fails
    both new MSSQL bracket rows (orphaned delete, stranded move) —
    the rows detect the defect they were written for.
  - §1: `escape_glob` (class notation) lands public in
    `pattern_matching/glob.py`; `effective_pattern` and
    `composed_pattern` escape their base internally, so the keep
    closure, composed exclusions, and mount skip-suppression are
    covered at the seam; grep's root-literal member escapes at its
    splice. Audit found no other path-into-pattern splice; ADR 034's
    chained gating is a pure predicate (no row-path splicing exists
    there — nothing to escape). Campaign repro shapes re-executed:
    `[x]` serves its subtree, `{a}` no longer refuses, `data [prod]`
    serves, no sibling capture. Property row
    (`test_every_root_sees_exactly_its_prefix_subtree`) pins the
    general law; ADR 030 rationale 3 annotated restored.
  - §2: `like_bracket_class` profile fact (MSSQL only), conditional
    escape in `escape_like(text, profile)`, profile threaded through
    `descendant_filter`/`subtree_filter`/`liveness_filters`/
    `pattern_arm` and the topology/reads callers. Conformance
    battery: `a[1]b` joins `METACHAR_DIRS` (decoy `a1b`), plus the
    no-orphan cascade-delete row and the subtree-carrying move row.
  - §3: `split_lines` (\n-only, final terminator dropped) lands
    public in `pattern_matching/grep.py`; `verify` and both
    `results/render.py` sites use it. Control-character rows in
    test_grep.py (form feed span, post-`\x85` line numbers, count
    mode, CRLF control incl. the `$`-anchor law) and a render row.
    Differential battery: control-character edition, 157 case-checks
    green vs grep -E and rg -uu across four worlds (run record in the
    study). The fold-vs-verify `\r` lead is **refuted by execution**:
    both planner paths (`grams_for_fixed_string`, `_encode_run`)
    route pattern literals through the same `normalize_content` the
    indexer applies, so `\r` patterns plan the same `\n` grams the
    postings carry — the indexed tier serves a `\r` pattern
    end-to-end (verified live), no phantom grams.
  - §4: the `body == "!"` arm returns `.` (fnmatch's rule); `[!z-a]`
    joins the parity battery (stdlib byte-identical); the bounded
    fuzz folds in as a marked-slow row — exhaustive depth ≤ 6 over
    the class-machinery alphabet `[]!-az*`, 137,256 patterns,
    125,378 byte-compared, ~2.7 s. Note: bare `[!]` never reaches
    the class translator (fnmatch's scan reads it as literal `[`);
    the reachable crash was the merged inverted-range reduction.
  - **Mined and archived 2026-08-14**: residue was already
    downstream at landing — the ADR 030 rationale-3 restoration and
    the `\n`-only line law are annotated in place, the
    control-character battery edition lives in the grep differential
    study, and the parity fuzz rides `tests/` as a marked slow row.
- **Date:** 2026-08-13
- **Owner:** Clay Gendron
- **Kind:** correctness repairs where literal text (paths, content
  lines) meets a pattern language (glob, LIKE, regex) — one seam
  regression, one pre-existing standing bug, two language-edge fixes —
  plus the metachar conformance rows whose absence let all four land.
- **Depends on:** ADR 030 (rationale 3: "roots are literal and immune
  to glob metacharacters" — reaffirmed in-range and currently
  violated), ADR 031/032 (composition, the LIKE-superset doctrine),
  ADR 034 (chained gating uses the same authorities), CLAUDE.md's
  dialect-profile rule (§2's fix is a legitimate profile fact).
- **Relates to:** spec 094 (the brace/exclusion machinery the root
  splice now feeds), the standing MSSQL non-Latin1 `?`-mangling
  open-questions entry (same engine, different text seam).

## Intent

Four verified defects share one shape: text that is *literal* in the
caller's hands (a scope-root path, a directory name, a content line)
crosses into a pattern language (glob, T-SQL LIKE, regex) without
quoting, and the language reinterprets it. The worst is a regression
this arc introduced: scope roots were literal `Path`s at the base
commit and are now spliced raw into pattern text, so
`paths=("/data/[x]",)` silently serves the sibling subtree — while
ADR 030's roots-are-literal rationale was being reaffirmed in the same
range. Beside it: the pre-existing `escape_like` miss on MSSQL's `[`
class (silent empty subtrees, and cascade-delete orphaning),
`str.splitlines` line semantics that diverge from grep/ripgrep on
form feeds and Unicode line separators, and the bang-class regex crash.

One sentence: **every seam where literal text enters a pattern
language quotes it at the seam — root text glob-escapes at every
composition point, LIKE escaping covers the dialect's full metachar
set, line splitting matches the field's `\n`-only law — and the
conformance batteries gain the metachar rows that would have caught
all four.**

## Shape

### 1. Scope roots glob-escape at every composition point (memo 4, major — regression)

`composed_pattern` splices `str(root)` into pattern text, grep's
find-operand rule adds the raw root as a pattern member, and the keep
closure composes `effective_pattern(row.path, arm)` — all unquoted.
Executed consequences: sibling-subtree capture and silent root drops
(`/data/[x]`), whole-call refusals naming a brace the caller never
wrote, ADR 030's own worked example (`data [prod]`) returning silent
empty success, Next.js `[slug]` directories unglobbable.

- A public `escape_glob(text) -> str` lands in
  `pattern_matching/glob.py` beside the compile chokepoint — class
  notation (`[[]` for `[`, etc.) escapes every metachar and is
  expressible in the shipped language (verified in-campaign).
- Every composition point routes literal text through it:
  `composed_pattern`'s base, `effective_pattern`'s base, grep's
  root-literal member, composed exclusions, and the two
  verified-adjacent splice sites (mount skip-suppression composition;
  the exclusion channels) — audited as a set, not patched singly.
- Chained gating (ADR 034) composes row paths through the same
  escape.
- Conformance + namespace rows: metachar roots (`[x]`, `{a}`, `*`,
  `?`) serve exactly their own subtree on every engine, and a
  metachar root never refuses. Property-shaped: for any legal path
  `p`, `glob("**", paths=(p,))` scoped at `p` sees exactly `p`'s
  subtree.

### 2. `escape_like` covers the MSSQL bracket class (memo 5, major — pre-existing)

T-SQL LIKE treats `[...]` as a class; `escape_like` escapes only
`\ % _`. On MSSQL, `tree('/data[1]')` returns zero rows with
`success=True`; cascade delete trashes the directory row and leaves
live descendants orphaned; move composes the same filter. Verified
fix caution: unconditionally escaping `[` raises ORA-01424 on Oracle,
so the escape is **dialect-conditioned** — a `DialectProfile` fact
(MSSQL-family: bracket-class LIKE), exactly the kind of decision
SQLAlchemy takes no position on (CLAUDE.md's profile rule).

- The profile field + the conditional escape in `escape_like`.
- A bracketed-path conformance row per engine (today no test anywhere
  puts `[` in a path): tree/descend, cascade delete (no orphans),
  move — the three verified failure surfaces.
- The orphan shape from the campaign repro becomes the delete row's
  assertion.

### 3. Line semantics: split on `\n` only (memo 12, major)

`str.splitlines` breaks on `\x0b \x0c \x1c-\x1e \x85 U+2028 U+2029` —
bytes grep and ripgrep treat as ordinary in-line characters. Verified:
a pattern spanning a form feed matches nothing; every match after such
a byte carries a wrong line number (misdirects downstream edits);
`count` mode is wrong. Content round-trips byte-identical, so the fix
is wholly in match semantics:

- `match_texts` splits on `"\n"` (with trailing-empty handling),
  aligning with the index fold's own newline normalization.
- The same fix lands in `results/render.py` (lines 401/403) — or
  rendering re-introduces the skew the matcher just fixed.
- The grep differential battery gains a control-character row set
  (form feed, `\x85`, U+2028/29, and the CRLF no-change control);
  today's corpus is `\n`-only ASCII, which is why the a0290dc parity
  claim never covered this.
- Verified-adjacent lead to close or refute in the same pass: the
  fold-vs-verify `\r` asymmetry (may plan grams no posting carries —
  a planning inefficiency, not a correctness hole, if real).

### 4. The bang-class arm (memo 21, minor)

`_translate_class` omits fnmatch's `stuff == '!'` arm: a class
interior reducing to bare `!` compiles to invalid regex `[^]` and
raises raw `re.PatternError` through the public API, with
`glob_defect` wrongly returning None. The campaign's exhaustive
≤6-char fuzz (1.65M patterns) found this as the *only* parity break —
84 raising patterns, zero silent mismatches. Fix: the `body == "!"`
arm (translate to `.` per fnmatch), a parity-battery row, and fold the
bounded fuzz into the battery as a marked slow row so the parity claim
stays exhaustive at this depth.

## Verification obligations

- Suite green, coverage 100%, `ruff`/`ty` zero.
- The four campaign repros re-expressed as tests and green: metachar
  root serve/refuse shapes, MSSQL bracketed tree/delete/move, the
  form-feed and U+2028 grep shapes, the bang-class refusal.
- §1's property row and §2's bracket rows live on all four Docker
  legs (MSSQL is §2's proving engine; Oracle proves the ORA-01424
  guard).
- The 29-pattern stdlib-parity battery still byte-identical after §4;
  the folded fuzz row green.

## Touch points

`src/vfs/pattern_matching/glob.py` (§1 escape + §4 class arm),
`src/vfs/base.py` (§1 composition/root-member/keep sites),
`src/vfs/pattern_matching/grep.py` + `src/vfs/results/render.py`
(§3), `src/vfs/storage/backends/database/descent.py` +
`.../dialects.py` (§2), conformance battery + namespace batteries +
`tests/pattern_matching/test_glob.py`/`test_grep.py`, ADR 030
annotation (rationale 3 restored by §1).

## Slices

- **A** — §1 (the regression; router + pattern layer only).
- **B** — §2 (dialect profile fact + descent; independent of A).
- **C** — §3 (matcher + render + battery rows).
- **D** — §4 (one arm + battery fold; can land any time).

## Open questions

None — every fix direction was executed and verified in the campaign;
the only judgment calls (escape spelling, profile-fact shape) are
settled by verified constraints above.
