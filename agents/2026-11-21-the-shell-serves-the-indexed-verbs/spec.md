# The shell serves grep, find and the verbs with no Unix name from the indexed verbs

A draft, written on 2026-11-21 from the structural review of the shell (`agents/2026-11-21-the-shell-speaks-bash/reviews/structural-review.md`, finding 2) and the shell's `progress.md`. Amended and built on 2026-11-22 on the branch `the-shell-serves-the-indexed-verbs`, with the decisions below. Two departures from GNU are left for a ruling, under "Choices to confirm".

Ruled on 2026-11-22: this lands before `0.1.0b1`, when the public surface is frozen, not in the `0.1.0` gate after it. Ruled the same day: `grep`, `glob`, `search` and `traverse` are in the shell, look and feel like bash, and call the public verbs. The shell is no platform for other hosts and is not a package of its own, so the machine and the wire may change for vfs's needs.

## The outcome wanted

`grep -rn mfa /enterprise | head -20` costs one call of the `grep` verb, not one `read` for each file beneath the root, and `find /docs -name '*.md'` one call of `glob`. `glob`, `search`, `traverse`, `grant`, `revoke`, `grants`, `edit`, `mkedge` and `rmedge` run as programs of the shell, each one call of its verb as the caller.

## Builds on

The program request of `agents/2026-11-21-the-shell-speaks-bash/spec.md`: a name the machine does not run itself is a `Start` request, and the host answers `started`, `library`, `refused` or not found.

## The problem

- The library's `grep -r` and `find` walk with `list` and `read`: 200 files under a root cost 200 `read` calls, and every body is held for the line. Library `find` also makes one `stat` for every file. At the reference deployment's ten million files the roadmap's example is ten million calls.

## What was found before the build

Each was shown by a script that ran, on SQLite, at the branch's base `cbda272`.

- `ls` orders a directory's names by code point; `glob` with `*` or `**` beneath a root returns the root and every row beneath it, dotfiles included, in path order.
- The `glob` language reads `[^a]` as a set holding `^` and `a`, matches nothing for `[[:digit:]]`, expands braces, and refuses `**` inside a name. GNU `fnmatch` reads `[^a]` as a negation, knows POSIX classes, and reads braces and `**` literally or as `*`.
- The `grep` verb's regions with no context are one hit line each, `\r` kept and no newline; `-v` and a missing final newline select what the library selects; `^` and `$` are line anchors.
- The `grep` verb never matches a body stored as bytes, whatever its bytes: a UTF-8 Markdown file written with `data=` is `application/octet-stream`, `render_status` `pending`, and has no content until it is rendered. Text content cannot hold a NUL byte, so GNU's binary rule meets only bytes bodies.
- An empty pattern, and a pattern of one NUL, are refused as `unindexable_pattern` unless `allow_scan` is set.
- A caller who may list a file but not read it gets no row for it from `grep`; the library's walk prints `grep: path: Permission denied` and exits 2.
- `type grep` and `command -v grep` read the machine's program table. A name the host resolves was absent from it, so `type search` printed `not found`.
- The library's `grep -E 'ab{,1} '` selects no line; GNU grep 3.11 and the verb select the lines that hold `a` then a space, as `{,1}` means zero or one.

## Decisions

1. **The machine knows a second kind of program, one the host resolves at every start.** `ProgramKind::Host` is listed by `type` and `command -v` as `/usr/bin/NAME`, as a library program is, and is asked of the host each time it starts. The host answers `library` to hand a start back to the library's program of the same name. The wire carries the names as `host_programs`, beside `programs`. This amends the draft's scope, which left the machine and the wire unchanged.
2. **The vfs host resolves `grep`, `find` and the nine verb programs.** The machine runs every other library program itself, as before.
3. **`grep` is served when every part of its line is served, and handed back to the library otherwise.** Served: `-r` or `-R`, with `-E`, `-F`, `-G`, `-i`, `-y`, `-n`, `-l`, `-c`, `-w`, `-h`, `-H`, `-s`, `-q`, `-e`, their long forms, `--regexp=`, `--include=`, `--exclude=` and the ignored `--color`, `--colour` and `--line-buffered`. The dialect is the last of `-E`, `-F` and `-G`, as in GNU. Handed back: no `-r`, any other option, standard input as an operand, `-c` with a glob filter, an `--include` after an `--exclude` (GNU's last-match-wins rule), a glob filter with a file operand, and any pattern construct `vfs.shell.patterns` does not serve.
4. **A pattern is served only where both matchers read it alike.** `verb_regex` writes a basic, extended or fixed pattern in the `grep` verb's language and answers `None` for back-references, `\<`, `\b`, `\w` and the other GNU escapes, POSIX bracket classes, a bracket with a backslash, a quantifier with nothing before it or after another, an empty group or alternative, an interval past 255 or out of order, and in an extended pattern a `{` that opens no interval, a `^` or `$` not at a branch's edge, and a leading `*`. `-i` is served for ASCII patterns only, since the index and the matcher fold other letters by different tables (`agents/2026-11-21-grep-reads-a-pattern-as-its-matcher-does/`). `-w` is served only for a pattern with no operator whose first and last characters are word characters, where GNU's retry after a failed boundary and the verb's `\b` agree.
5. **A served `grep` is one `stat` for each operand and one call of `grep` over every root, with `allow_scan` set.** GNU grep always answers, so an index refusal is not passed to the caller. `-c` adds one call of `glob` beneath the directory operands, so that a file with no match prints `:0`. The output follows the library's walk: operands in order, and in each directory its files before its subdirectories, by code point. A root as typed prefixes each path, and an operand-free `grep -r` prints paths without `./`, as GNU and the library do.
6. **`find` is served for a conjunction of tests.** Served: `-name`, `-iname`, `-path`, `-wholename`, `-ipath`, `-type f`, `-type d`, `-true`, a final `-print`, joined by `-a`, `-and` or nothing, with `-maxdepth` and `-mindepth` before them. A pattern is served when Python's `fnmatchcase` reads it as GNU `fnmatch` does with no flags. A served `find` is one `stat` for each start and one call of `glob` for each directory start: the first `-name` the `glob` language reads alike is the call's pattern, else `*`, and `-type d` sets the call's `kind`. Every test is then judged on each row by `fnmatchcase`, in pre-order with names by code point, as the library prints. Anything else is handed back, including a depth option after a test, about which GNU warns.
7. **An answer cut short hands the line back.** A `grep` or `glob` call that fails or carries any warning, `truncated` among them, makes the program answer `library`, so the caller sees GNU's output at the library's cost and never a partial one.
8. **A program runs at its start, and its writes are replayed in order across the feeds that follow.** `grep`'s operand errors come before its matches and `find`'s errors fall between its starts, as the library writes them, so `2>&1` interleaves them as GNU does.
9. **The verbs with no Unix name are programs in the shape of a GNU tool.** Options are read as getopt reads them, permuted, with `--` and long forms. `--help` prints a usage line and the options, with status 0. A misuse prints `name: reason`, the usage line and `Try 'name --help' for more information.`, with status 2. A refusal prints `name: path: reason` in `strerror`'s words where a kind has them, with status 1, and is kept on the line's result as a warning. The query programs, `glob`, `search` and `traverse`, print absolute paths one a line and exit 0, 1 or 2 as `grep` does. The action programs, `grant`, `revoke`, `edit`, `mkedge` and `rmedge`, print nothing when they act. A grant or edge that is not there to remove is no error, as the verbs say. A program that changes bodies or rights makes the line forget every body it holds first.
10. **`search` takes the same shape.** A limit that is no count is a misuse with status 2, where it was read as the query, and a refusal exits 2, where it exited 1.
11. **A form the verbs cannot serve falls back without a word.** Standard error is GNU's either way. This answers the draft's choice to confirm.

## Tests

- `tests/shell/test_patterns.py`: each translation; each construct left to GNU's form; a differential over 40 patterns that the verb selects the lines the library's own form selects; the `{,1}` interval pinned to GNU grep 3.11's answer.
- `tests/shell/test_programs.py`: 36 served `grep` lines and 32 served `find` lines print what the library prints, spied at one `grep` call, or one `glob` per start, and no `read` or `ls`; the forms handed back make no `grep` or `glob` call and print what the library prints; the `--include` and `--exclude` forms print GNU grep 3.11's answers; 200 files under a root are one `stat` and one `grep`, or one `stat` and one `glob`; the 78 corpus cases of `grep` and `find` match bash's records on the vfs host; a truncated answer hands the line back; each verb program is one call of its verb as the caller, prints `--help`, and words each misuse and refusal; the two departures are pinned as they are.
- `crates/vfs-shell/tests/laws.rs`: a host-resolved name is a program to `type` and is asked of the host at each start.

## Scope

The vfs host, its program table and pattern translation, the machine's program kinds, the wire and the binding.

## Choices to confirm

1. **A file the caller may list but not read.** A served `grep -r` leaves it out without a word, where GNU prints `Permission denied` and exits 2. Telling an unreadable file from one with no match needs a read of every file, or a rights query no public verb offers. Recommended: keep the silence. The names are listable anyway, and at the reference deployment one line per unreadable file is noise. The alternative is a verb or a `grep` row that names the files it skipped for rights, and the shell printing GNU's line for each.
2. **A body stored as bytes.** A served `grep -r` never matches one, where GNU matches its raw bytes and prints `Binary file ... matches`. A UTF-8 text file a caller wrote with `data=` is invisible to it until it is rendered. Recommended: keep it, since a file the shell writes is text when it is UTF-8, and record it as a departure. The alternative is a `grep` verb that also matches a bytes body raw, which is a change to the verb for every caller.
3. **`allow_scan` on every served `grep`.** It keeps GNU's promise of an answer and is never worse than the library's walk, but it lets an agent's `grep -r ''` scan every body beneath its root. Recommended: keep it.

## One line

A recursive grep in the shell is one indexed verb call, not a read of every file, and the verbs with no Unix name are programs that read like GNU tools.
