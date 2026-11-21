# Grep reads a pattern as its matcher does

A draft, written on 2026-11-21 from rounds 2 and 3 of the review in `agents/2026-11-21-grep-query-planner/`. It is not reviewed on its own, and nothing is built.

## The outcome wanted

A database `grep` never loses a row its matcher would return. The pattern is planned for the index, and folded into index keys, by the same parse and the same case tables that the matcher uses to verify it, so the index's candidates are always a superset of the matcher's matches.

## Builds on

`agents/2026-11-21-grep-query-planner/`: its `research.md`, its reviews, and the review scripts under `reviews/scripts/`. The grep planner designed there rests on this spec landing first.

## The problem

Each was shown by a script that ran. The pinned code is commit `5dfdcc79`, on SQLite.

- **The gram plan parses the pattern with a different parser than the matcher.** The language gate (`_gate` in `vfs/pattern_matching/grep.py`) and `build_code_gram_query` read the pattern with Python's `sre`. The matcher is the regex crate (regex-syntax 0.8.11). The gate admits syntax the two read differently: `\<`, `\>`, `\b{start}`, POSIX classes such as `[[:alpha:]]`, and nested classes. Python reads `[[:alpha:]]` as a set followed by a literal `]`, and warns `FutureWarning: Possible nested set`, but the warning never reaches the caller. Under `/fs` of the Linux sandbox, `[[:alpha:]]_count` returns 0 files where `rg` returns 751. `\<kmalloc` returns 6 files where `rg -e '\bkmalloc'` returns 421. No error and no warning reaches the caller (`reviews/scripts/round-2/r2_01_syntax_mismatch.py`).
- **The index folds case with different Unicode tables than the matcher.** The index folds with Python's `str.casefold`, after a Turkic pre-fold (Unicode 15.1 on Python 3.13). The matcher folds with regex-syntax's tables (Unicode 16). An exhaustive scan over every code point found 54 letter pairs the matcher equates and the index fold does not, among them `ɤ` with U+A7CB, `ƛ` with its capital, and the Garay letters (`reviews/scripts/round-3/r3_01_fold_orbit.py`). On a rebuilt store, the index path lost a row in each of the 4 cases tried, with no warning, where reading the same files in hand returned it (`r3_02_fold_e2e.py`).
- **The index fold moves with the interpreter.** `'Ɤ'.casefold()` is `'Ɤ'` on Python 3.11 to 3.13 and `'ɤ'` on 3.14. So an index built under one interpreter can be stale under the next, with nothing to show it. This was shown on the fold function, not end to end (`reviews/round-3.md`, M1).

## Decisions

1. **The gram plan is built over the matcher's own parse.** `build_code_gram_query`'s walk moves to `crates/vfs-core` and runs over regex-syntax's HIR, the parse the matcher compiles. Python's `sre` stops reading patterns for planning. The HIR already lowers case-insensitivity, the call's mode and an inline `(?i)` alike, to classes, Kelvin and `ſ` included (`reviews/scripts/round-2/hirdump/`). So the same walk serves the folded gram plan, and later the case-exact literal extraction the grep planner needs.
2. **Until decision 1 lands, the gate refuses what the two parsers read differently.** `\<`, `\>`, `\b{…}`, POSIX bracket classes and nested classes are refused as `invalid`, with the construct named in the message. The list is pinned by a differential test (below), and a construct the test finds is added to it.
3. **The index fold is one table, generated from the matcher's case tables.** The fold becomes a table in `crates/vfs-core`, generated from the same regex-syntax version the matcher is built with, in place of `str.casefold`. Its invariant is that every pair of code points the matcher equates under case-insensitivity folds to one key. An exhaustive test over every code point pins it. The table may merge more than the matcher does, which keeps the candidates a superset, but never less. Today's fold is full casefolding: `straße` folds to `strasse` and `ﬁ` to `fi`, while the HIR carries a pattern's literals unfolded (`reviews/scripts/round-3/r3_01b_full_vs_simple.py`). So the walk of decision 1 folds the HIR's literals with the same table it indexes bodies with.
4. **The fold's Unicode version is stored with the index generation.** An index whose stored version differs from the running table's reads as stale. The scan side then serves every row, as it does for rows the index has not seen, and the next rebuild repairs the index. A regex-syntax upgrade that changes the tables is then a rebuild, not a silent loss of rows.

## Tests

- A differential test generates patterns over a grammar that includes POSIX classes, `\<`, `\>`, `\b{…}`, nested classes, inline flags and Unicode case pairs. It checks that the gram plan's candidates contain every body the matcher matches. Until decision 1 lands, it also checks that every construct it finds diverging is refused by the gate.
- The fold invariant runs over every code point.
- The rows lost in rounds 2 and 3 become regression tests through the public `grep`: `[[:alpha:]]_count`, `\<kmalloc`, and the four Unicode pairs of `r3_02`.

## Scope

In: the language gate, the gram plan's construction, and the index fold. Out: the grep planner, the matcher itself, and the search verb's tokenizer.

## Not checked

- How often real callers use the diverging constructs. Agents trained on GNU grep write `\<` and `[[:alpha:]]` readily, so the guess is often, but it is not measured.
- Postgres. The defect is in Python and Rust, not in SQL, so it is expected to be the same there, but no Postgres leg was run.
- What a fold change costs: it forces one full rebuild of every existing index.

## Choices to confirm

1. **Decision 2: refuse now, or build decision 1 first and refuse nothing?** Recommended: refuse now. Refusing is a small change that ends the silent loss today, and the refusal list shrinks to nothing when the HIR walk lands.
2. **Decision 4: a stale fold serves every row from the scan side until a rebuild.** That is correct but slow on a large store. Alternative: refuse `grep` on a stale index until it is rebuilt. Recommended: serve from the scan side, as rows the index has not seen are served today.

## One line

The index is planned and folded by the parse and the case tables the matcher uses, so no row the matcher would return is ever ruled out first.
