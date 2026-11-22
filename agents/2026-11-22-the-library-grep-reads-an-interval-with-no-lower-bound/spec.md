# The library's grep reads an interval with no lower bound as GNU grep does

A draft, written on 2026-11-22 from the build of `agents/2026-11-21-the-shell-serves-the-indexed-verbs/`. It is not reviewed, and nothing is built.

## The outcome wanted

`grep -E 'ab{,1} ' f` selects the lines GNU grep selects in every form the shell runs, served or not.

## Builds on

The machine's regular-expression engine (`crates/vfs-shell/src/machine/regex.rs`) and the library's `grep` (`crates/vfs-shell/src/programs/grep.rs`).

## The problem

- Over the 16 lines of `LINES` in `tests/shell/test_patterns.py`, GNU grep 3.11 in `C.UTF-8` selects lines 2 and 8 for `-E 'ab{,1} '`, as `{,1}` means zero or one. The library's `grep` selects none. The `grep` verb selects lines 2 and 8, so a served `grep -r` and the library's `grep` without `-r` disagree on the same pattern.
- The same form in a basic pattern, `\{,1\}`, was not run.

## Decisions

1. The engine reads `{,n}` as `{0,n}` in an extended pattern, and `\{,n\}` in a basic one, as GNU does.

## Tests

A corpus case under `tests/shell/cases/programs/grep/` for `{,n}` in both dialects, recorded by the pinned bash image; and the pattern differential of `tests/shell/test_patterns.py` gains the pattern it now leaves out.

## Not checked

Whether `{,}` and an interval past GNU's `RE_DUP_MAX` read alike.

## One line

The library reads `{,n}` as zero to n, as GNU grep and the indexed `grep` already do.
