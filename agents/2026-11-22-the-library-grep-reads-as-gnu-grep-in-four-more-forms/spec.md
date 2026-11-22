# The library's grep reads as GNU grep in four more forms

A draft, written on 2026-11-22 from the build and the code review of `agents/2026-11-21-the-shell-serves-the-indexed-verbs/` (`context/reviews/2026-11-22-the-shell-serves-the-indexed-verbs-code-review.md`, findings M3, L1 and L2). It is not reviewed, and nothing is built.

## The outcome wanted

The library's `grep` prints what GNU grep 3.11 prints in `C.UTF-8` for an interval with no lower bound, for `--include` and `--exclude`, for `-r` over one file, and for `-q` with an error after a match. A served `grep -r` prints what the library prints, so each fix also brings the served and the library's forms back to one answer where they now part.

## Builds on

The machine's regular-expression engine (`crates/vfs-shell/src/machine/regex.rs`) and the library's `grep` (`crates/vfs-shell/src/programs/grep.rs`).

## The problem

Each was shown by a script that ran on 2026-11-22.

- **`{,n}`.** Over the 16 lines of `LINES` in `tests/shell/test_patterns.py`, GNU grep selects lines 2 and 8 for `-E 'ab{,1} '`, as `{,1}` means zero or one. The library selects none. The `grep` verb selects lines 2 and 8, so a served `grep -r` and the library's `grep` without `-r` disagree on one pattern. `\{,n\}` in a basic pattern was not run.
- **`--include` and `--exclude`.** The library knows neither, and prints `unrecognized option` with status 2. A served `grep -r` serves both, but a form it hands back, such as an `--include` after an `--exclude` or a glob filter over a file operand, ends in the library's error where GNU prints matches. `tests/shell/test_programs.py` pins that error today.
- **`-r` over one file.** `grep -r PAT FILE` prefixes each line with the file's name in the library and in a served `grep -r`; GNU prints no name when its one operand is a file.
- **`-q` with a later error.** `grep -rq PAT a nope` prints the operand error for `nope` after a match in the library and in a served `grep -r`; GNU stops at the first match and prints nothing.

## Decisions

1. The engine reads `{,n}` as `{0,n}` in an extended pattern, and `\{,n\}` in a basic one.
2. The library takes `--include=GLOB` and `--exclude=GLOB` as GNU does: matched against a file's name, the last matching option winning, and a file that matches none included unless the first such option is an `--include`.
3. With `-r` and exactly one file operand, no name prefixes a line.
4. `-q` exits 0 at its first match, before it reads or stats any later operand.

## Tests

A corpus case under `tests/shell/cases/programs/grep/` for each form, recorded by the pinned bash image. The tests in `tests/shell/test_programs.py` that pin the library's departures today change to compare the served and the library's forms.

## Not checked

Whether `{,}` and an interval past GNU's `RE_DUP_MAX` read alike; whether GNU's `--exclude` matches a command-line file by its name's suffix as its manual says.

## One line

The library's `grep` reads `{,n}`, the glob filters, one file under `-r` and `-q` as GNU does.
