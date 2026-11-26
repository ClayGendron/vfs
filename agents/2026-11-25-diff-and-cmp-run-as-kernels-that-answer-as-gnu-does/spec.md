# `diff` and `cmp` run in the shell and answer as GNU diffutils does

A draft, written on 2026-11-25 and checked against `dev` at `27f3d24d`. It is not reviewed, and nothing is built. It serves the roadmap's 0.1.x row "Diff/cmp kernels (168c)", which "Can slip without changing a name" ([the roadmap](../../context/standards/roadmap.md), line 1202); roadmap decision D34 keeps the two programs out of the 0.1.0 table (line 1245), and no story names them. It is converted from slice 168c of [the text program kernels spec](../../context/specifications/archive/168-text-program-kernels/spec.md) (its rows for `diff` and `cmp`, lines 66-67, the `diff` deadline, line 164, and criterion 14, line 194), read through [its study](../2026-11-25-the-backlog-converted/studies/165-181/168-text-program-kernels.md) and [the reassessment of unit 168-4](../2026-11-25-the-backlog-converted/reassessment/kernels-sessions-and-deadline.md). It rests on the shell as built on `dev` from [the shell speaks bash](../2026-11-21-the-shell-speaks-bash/spec.md), and on the ruling of 2026-11-22 that the shell acts as Linux bash in every way it can ([the shell acts as bash where it refused](../2026-11-22-the-shell-acts-as-bash-where-it-refused/spec.md), line 5). It adds two program names and changes none, so it may land before or after 0.1.0.

## The outcome wanted

An agent types `diff a b`, `diff -u --label old --label new a b`, `diff <(sort a) <(sort b) | head` or `cmp -s a b` in a shell line, and gets what GNU diffutils prints for the same files: the same bytes on standard output, the same exit status (0 for the same, 1 for different, 2 for trouble) and standard error where GNU writes it.

Each file operand is read once, as the caller, through the public verbs, as `cat` and `sort` read theirs. A diff that would run too long ends the line at its fuel or its deadline, as any line ends, and a pair too large to hold ends it at its memory budget.

The check is the shell corpus: new cases under `tests/shell/cases/programs/diff/` and `tests/shell/cases/programs/cmp/`, whose records GNU diffutils made in the pinned image, pass on the crate's reference host and on the vfs host.

## Builds on

- [The shell speaks bash](../2026-11-21-the-shell-speaks-bash/spec.md), built on `dev` (the crate `crates/vfs-shell`, its `programs` module and `src/vfs/shell/host.py`). The shapes relied on, by its decision number: 4 (the machine does no IO and asks its host by request), 6 (fuel is instructions executed; spent fuel ends the line with exit 137), 7 (memory is counted, not measured), 8 (time belongs to the host; the runtime's deadline ends a slice that overruns), 9 (no recursion follows the depth of the input), 10 (programs other than builtins live in the library module), 11 (`MemoryHost` runs the whole corpus), 12 (the referee is bash, recorded in an image pinned by digest), 14 (`known_failures.txt` is exact) and 16 (a deliberate difference keeps bash's record and is named in `deltas.txt`).
- The library programs' shared helpers, built: `Prog::file`, `Prog::stat`, `Prog::stdin_chunk` and `Prog::out` (`crates/vfs-shell/src/programs/mod.rs:114`, `:137`, `:152`, `:209`), and `read_operand` (`crates/vfs-shell/src/programs/text.rs:20`).
- The recorder `scripts/shell_record.py`, built, which runs each case twice under bash 5.3 and GNU tools in `debian@sha256:07a3205e…` and refuses a case whose two runs differ (`scripts/shell_record.py:1-30`).
- [Bounded work has one home](../../context/specifications/archive/2026-11-07-bounded-work-has-one-home.md), landed: a deadline is passed as an argument and never stored on a long-lived object (`src/vfs/deadline.py:14-15`).
- No other unit of this conversion. The law below uses the read schedule and the helper of unit 168-2, decisions 1, 3 and 15; built first, it sets a field that binds nothing. Unit 168-1, which the source made this unit's base, is built on `dev`: the shell landed with its programs in Rust from the start (the reassessment, section 168-1).

## Terms

- **Edit script**: the lines of each input marked changed. Everything `diff` prints is derived from it.
- **Change group**: a run of changed lines in one input together with the run facing it in the other. A normal-format block (`3c3`) is one group; a unified hunk holds one or more groups and their context.
- **Line class**: a number standing for every line equal to it under the comparison options (`-i`, `-b`, `-w`). The search compares classes, never bytes.
- **Round**: one step of the edit distance in the search: every diagonal reachable with one more edit is extended as far as equal lines allow.
- **Middle snake**: the run of equal lines through which a minimal script must pass, found by searching forward and backward at once; the search splits the problem there. This is the linear-space form of Myers' 1986 O(ND) algorithm.
- **Discard pass**: GNU's first stage, which marks changed before any search the lines that have no match in the other input, and, under GNU's own rule, some lines that match too often.
- **Expensive bound**: GNU's limit on the rounds a split may take before it settles for a good split rather than the best one; `--minimal` lifts it.
- **Boundary shift**: GNU's last stage, which slides each change group along runs of equal lines to a fixed place, so that equal scripts print the same way.

## What the code does today

- `diff` and `cmp` are not programs of the shell. On the vfs host, `diff /x /y; echo status=$?; cmp /x /y; echo status=$?` prints `status=127` twice and `bash: line 1: diff: command not found` on standard error (EXECUTED, a scratch probe through `AsyncVirtualFileSystem.cli`).
- The library's names are `cat cp cut find grep head ls mkdir mv rm sed sort tail tee touch tr uniq wc` (`crates/vfs-shell/src/programs/mod.rs:20-23`). The binding exports them as `SHELL_PROGRAMS` (`crates/vfs-core/src/python.rs:644`), and `library_programs()` hands the machine every one the vfs host does not resolve itself (`src/vfs/shell/host.py:174-176`). The host resolves neither `diff` nor `cmp`, and neither is in `UNKNOWN_PROGRAMS` or `REFUSED_PROGRAMS` (`src/vfs/shell/host.py:110-120`).
- A library program reads an operand with one `stat` and then the whole body (`text.rs:20-28`); `read_whole` checks each chunk against the line's memory budget (`crates/vfs-shell/src/machine/exec.rs:1937-1972`). `open_read` opens an operand as a descriptor, and `/dev/fd/N`, `/dev/stdin` and `/dev/null` resolve to the shell's own descriptors (`exec.rs:1975-2017`).
- The machine counts held bytes with `charge` and `release` against `memory_bytes` (`crates/vfs-shell/src/machine/io.rs:93-104`), 64 MiB by default (`crates/vfs-shell/src/machine/mod.rs:60`). The line's output is bounded by `output_bytes`, 16 MiB (`mod.rs:68`).
- `io::checkpoint` is the point where a long run hands control back when its slice is spent and where a cancel ends it (`io.rs:192-231`); the machine's loops and pipelines await it (`exec.rs:398`, `:676`). No library program awaits it today (EXECUTED, grep over `crates/vfs-shell/src/programs`).
- The runtime is the wall. It counts every instruction against the line's fuel, 20,000,000,000 by default (`crates/vfs-core/src/shell_binding.rs:33`), and ends a slice past the deadline within one 10 ms epoch tick (`shell_binding.rs:40-41`, `:440-452`). A line's deadline is 30 seconds unless the caller gives one (`src/vfs/shell/host.py:77`, `:211`, `:232`); a deadline that ends a line is `vfs.timeout`, exit 124, and spent fuel `vfs.budget_exhausted`, exit 137 (`host.py:288-297`, `shell_binding.rs:43-45`).
- Reading costs about 235 instructions a byte: `cat` of a 10,000-line, 250,000-byte file spent 58,806,555 instructions above `true`, and `cat` of two such files 117,610,266 (EXECUTED, a scratch probe of `LineResult.fuel_used`).
- The weighted sample of measured agent commands holds one `diff` line, `diff <(sort /tmp/x/a.txt) <(sort /tmp/x/b.txt) | head`, in normal format (`context/research/studies/2026-10-15-agent-shell/experiments/s1/corpus.jsonl:73`). It is one of the 28 lines that do not run (`agents/2026-11-21-the-shell-speaks-bash/progress.md:11`), and the floor of lines that run is 72 (`crates/vfs-shell/tests/measured_corpus.rs:71`).
- The form census counts 29 `diff` segments and 1 `cmp` segment; `diff`'s flags are `-n` 4, `-q` 4, `-u` 1 and `-v` 1 (`context/research/studies/2026-10-15-agent-shell/experiments/r168/form_census.out:12`, `:18`, `:149-153`).
- A corpus case may not print a file's modification time, since the recorder refuses a case whose two runs differ ([the corpus README](../../tests/shell/README.md), "Rules for a case").

## The problem

An agent comparing two versions of a file, or the sorted output of two commands, types `diff`. In the shell today the line fails at that word with 127, and the agent must fall back to reading both files whole and comparing them in its own context. That costs the agent two full bodies of tokens where a diff costs the changed lines.

The cost is small at the reference deployment, and so is the demand: 30 of 13,746 measured calls are `diff` or `cmp`, about 0.2%. The roadmap therefore places the two programs at 0.1.x and D34 keeps them out of the 0.1.0 table. What the work must get right is not reach but fidelity and bounds.

- **Fidelity.** Two minimal edit scripts for one pair can differ, and so can the way each is printed. A diff that is merely correct does not print what GNU prints. GNU's output comes from three stages: the discard pass, a Myers search with an expensive bound, and the boundary shift. Matching GNU means following all three.
- **Bounds.** Myers' search costs (N+M)·D steps for inputs of N and M lines at edit distance D. A pathological pair of 100,000-line files could run for minutes. The shell already has walls for that: fuel, the deadline and the memory count. The source gave `diff` a deadline of its own; on `dev` that is both unnecessary and against the landed rule that a deadline is never stored on a long-lived object.

## Decisions

1. **`diff` and `cmp` are library programs of the shell crate.** `diff` lives in `crates/vfs-shell/src/programs/diff.rs`, with its search, and `cmp` in `crates/vfs-shell/src/programs/cmp.rs`. Both names join `NAMES` in sorted order and the dispatch of `run` (`programs/mod.rs:20-57`). No Python changes: `library_programs()` hands them to the machine because the host resolves neither (`host.py:174-176`). `PROTOCOL_VERSION` does not move, because no exported signature changes; only the contents of `SHELL_PROGRAMS` grow. Precedent: decision 10 of the shell spec, and `sort`, `uniq`, `tr` and `tee`, which landed the same way.

2. **Operands are read as the library already reads them.** A file operand is one `stat` and one `read` request, through `read_operand` (`text.rs:20-28`) for `diff`. `-` is standard input. `/dev/fd/N` is the shell's descriptor, so `diff <(sort a) <(sort b)` works. `/dev/null` is empty. No request kind is added. On the vfs host each request is a public verb called as the line's authority, so a file the caller cannot read reads as `Permission denied` and its bytes never enter the program (`host.py:1-22`).

3. **Both programs compare bytes.** Nothing is decoded as UTF-8. A line ends at `\n`, and a last line without one is kept and printed with GNU's `\ No newline at end of file` marker. `-i` folds ASCII letters only, because GNU diff folds byte by byte and leaves a byte at or above 0x80 as it is; a recorded case of `É` against `é` pins that. `-b` and `-w` read the bytes GNU reads as white space (space, tab, newline, vertical tab, form feed and carriage return). Precedent: [filters preserve bytes](../2026-11-22-shell-filters-and-matching/spec.md).

4. **The forms of `diff` that are served.** The default normal format; `-u` and `-U N` and `--unified[=N]`; `--normal`; `-q` and `--brief`; `-s` and `--report-identical-files`; `-i` and `--ignore-case`; `-b` and `--ignore-space-change`; `-w` and `--ignore-all-space`; `-a` and `--text`; `-N` and `--new-file`; `-d` and `--minimal`; `--label LABEL` and `--label=LABEL`, given at most twice; and `--`. Exactly two operands. When one operand is a directory and the other is not, the file of the same base name inside the directory is compared, as GNU does. The reason for this set: it covers every measured flag that means what the census counted (`-q`, `-u`), the five of the source's list (`-U N -w -b -i -N`), and the cheap ones that change only the comparison or the summary line.

5. **The forms of `cmp` that are served.** `-b` and `--print-bytes`; `-i SKIP` and `-i SKIP1:SKIP2` and `--ignore-initial=…`; `-l` and `--verbose`; `-n LIMIT` and `--bytes=LIMIT`; `-s`, `--quiet` and `--silent`; one or two operands, the second `-` when absent; and the two optional skip operands after them. A count is a decimal integer. That is GNU's whole option set but `--help`, `--version` and the size suffixes.

6. **Options are parsed as GNU parses them.** An option may follow an operand until `--`. A value is attached (`-U3`, `--unified=3`, `--label=x`) or the next word (`-U 3`, `--label x`). Short options bundle (`-qi`). Each program has its own parse loop, as `sort` has (`text.rs:1048-1145`), because `split_args` (`mod.rs:270`) cannot tell an option's value from an operand.

7. **What is not served is refused as trouble, never misread.** This departs from Unix, so it is stated in the four parts Article 3 of [the constitution](../../context/standards/constitution.md) asks for. The principle: follow GNU where it has a convention. The deviation: `diff`'s `-r` and every other option of its directory comparison, a pair of directories, the context and side-by-side formats (`-c`, `-C`, `-y`), the script formats (`-e`, `-n`, `--ifdef`), the group and line formats, `-p`, `-F`, `-B`, `-I`, `-E`, `-Z`, `-t`, `-T`, `--strip-trailing-cr`, `--color`, `--from-file`, `--to-file`, `--speed-large-files`, `--help` and `--version`, and `cmp`'s size suffixes, `--help` and `--version`, each print `diff: the '-y' option is not supported` (with the option's own spelling, and `cmp:` for `cmp`) and exit 2. The constraint: measured demand is 30 calls in 13,746, and the formats with modification times need a time the machine's `Stat` reply does not carry. The expiry: a form is served when a measured corpus or the coverage harness of story F5 shows it in use. A word that is no GNU option at all is refused in GNU's words (`invalid option -- 'z'`, `unrecognized option '--zz'`) with GNU's usage line, and exits 2. Exit 2 is GNU's own status for trouble, so a caller that reads the status never takes a refusal for a difference. Precedent: `sed` refuses its `e` command with "the `e' command is not supported" (`crates/vfs-shell/src/programs/sed.rs:658`).

8. **The edit script is GNU's, in GNU's three stages.** First the discard pass: lines with no match in the other input are changes before any search, and lines that match too often are discarded under GNU's provisional rule. Then the search over the remaining lines: common leading and trailing lines are set aside, the middle snake is found by Myers' linear-space bidirectional search with GNU's tie-breaking between forward and backward, and a split that passes GNU's expensive bound settles for GNU's good split. `--minimal` lifts the bound. Last the boundary shift: each change group is slid up to merge with the group before it, then down as far as equal lines allow, repeated while it grows, and then back to the last place where it faces a change in the other input. The thresholds (the discard rule's counts, the expensive bound as a function of the input sizes) are GNU's, read in the study of decision 16 and cited there by file and line. They are an external system's facts, which AGENTS.md permits as constants. The reason: the 2026-11-22 ruling makes GNU the referee, and only GNU's stages print GNU's script; a merely minimal diff disagrees wherever two minimal scripts exist. A side effect is the bound: the expensive bound caps the rounds of a split, so a pathological pair costs far less than (N+M)·D.

9. **Line classes come from an ordered map.** Each line, normalized under `-i`, `-b` and `-w`, is looked up in a `BTreeMap<&[u8], u32>` that hands out class numbers in order of first sight. An ordered map makes the instructions spent a function of the input, which the shell's fuel law needs (decision 6 of the shell spec), and no map in the crate hashes (`HashMap` appears nowhere in `crates/vfs-shell/src`, EXECUTED grep). The crate takes no dependency, which `crates/vfs-shell/tests/source_rules.rs` holds.

10. **The search does not recurse.** Its subproblems wait on an explicit stack, a `Vec` of index ranges, popped until it is empty. Decision 9 of the shell spec forbids recursion that follows the input, because a stack overflow cannot be caught. Its two diagonal arrays hold 2·(N+M)+3 entries each, allocated once and reused by every subproblem.

11. **The search hands control back each round, and has no deadline of its own.** The core is a plain struct the program advances one round at a time, and the program awaits `io::checkpoint` between rounds (`io.rs:192-231`). A long search therefore returns from `step` when its slice is spent and ends at a cancel, on the native build as on the module. Fuel and the line's deadline bound it as they bound every line: the runtime ends a slice past the deadline within one epoch tick, and spent fuel ends the line with exit 137. This reverses the source's "`diff` takes the deadline": a deadline stored on the core would break the landed rule that a deadline is never stored on a long-lived object (`src/vfs/deadline.py:14-15`), and the machine has no clock to read one by (decision 8 of the shell spec). The core also counts its diagonal steps and its rounds in two `u64` fields, read by its unit tests.

12. **`diff`'s memory is counted.** Before it allocates them, `diff` charges both inputs, its line tables (an offset and a class per line) and its two diagonal arrays against the line's `memory_bytes` with `charge`, and it releases them when it ends (`io.rs:93-104`). A pair that does not fit ends the line with `Budget("memory", n)` and exit 137, as any line that holds too much does (decision 7 of the shell spec). `cmp` holds at most one chunk of each input at once.

13. **The output is printed as GNU prints it, and written as it is made.** The normal format prints `NaM,N`, `NcM` and `NdM` blocks with `<`, `---` and `>`. The unified format prints `--- ` and `+++ ` headers and `@@ -l,s +l,s @@` hunks with N lines of context, 3 by default, and two hunks whose context would touch or overlap are one. A header shows the label, or the operand as typed when no label is given, and no modification time (choice 1). `-q` prints `Files A and B differ`, and `-s` prints `Files A and B are identical`. Every block goes to `Prog::out` as soon as it is formed, so `diff a b | head -3` ends `diff` as a closed pipe ends any program (`mod.rs:112-119`), and the line's `output_bytes` bounds what it prints.

14. **An input is binary under GNU's rule.** GNU diff takes an input with a NUL byte in the first buffer it reads as binary. The study of decision 16 reads that buffer's size, and the program scans exactly that prefix of what it already holds. Two binary inputs that differ print GNU's single `Binary files A and B differ` line and exit as GNU's record says. `-a` reads them as lines. `cmp` makes no such test: it always compares bytes.

15. **`cmp` compares in step.** It opens each operand as a descriptor with `open_read` (`exec.rs:1975`) and pulls one chunk of each at a time through `Prog::chunk(fd)`. `Prog::chunk` is the body of `Prog::stdin_chunk` (`mod.rs:152-194`) taken out to read any descriptor, and `stdin_chunk` becomes a call of it on descriptor 0. `cmp` compares the shorter of the two pending runs, keeps the rest of the longer one, and counts bytes and newlines as it goes. It stops at the first difference unless `-l` is given, at `LIMIT` bytes under `-n`, and at the end of the shorter input, where it writes GNU's EOF line to standard error. On the vfs host each open is still one read of the whole body (`host.py:13-16`); stepping bounds what the machine holds, not what the host reads.

16. **GNU is the referee, through recorded cases and one study.** The first build task is a study of GNU diffutils (`src/analyze.c`, `src/io.c`, `src/normal.c`, `src/context.c`, `src/util.c`, `src/cmp.c`) and of gnulib's `lib/diffseq.h`, cloned beside this checkout as reference repos, refreshed to their default branch, their licence (GPL-3.0-or-later) recorded, studied and never copied. It is written as `research.md` in this work directory and names, by file and line, the discard rule, the expensive bound, the tie-breaking, the shift rule, the hunk merge rule, the binary prefix and every message. The second task is the cases of the Tests section, written as `tests/shell/README.md` requires and recorded with `uv run python scripts/shell_record.py programs/diff/ programs/cmp/`. A case that does not yet pass is added to `tests/shell/known_failures.txt`, which stays exact (decision 14 of the shell spec). Every `-u` case passes `--label` twice, because a header without labels prints a modification time and the recorder refuses it.

17. **The measured floor rises with the work.** Once `diff` resolves, line 73 of the weighted sample runs, so `WEIGHTED_RUN_FLOOR` (`measured_corpus.rs:71`) is set to the count the test then measures, expected to be 73. The floor only rises.

## Cost

Nothing here adds a statement, a table, an index or a lock. The only verb calls are the reads each operand already costs a `cat`.

- **Per verb call.** A `diff` or `cmp` of two files is four public verb calls: a `stat` and a `read` for each file. Each is a single-path call whose cost is that one path. At the reference deployment's 150,000 agent verb calls a day, and with `diff` and `cmp` at the measured 0.2% of commands, an upper bound is about 330 lines a day, or about 1,300 verb calls: under 1% of the day's calls, all reads of one known path. A read never waits on a writer; these are plain `read` and `stat` calls on the existing path.
- **Per line, in fuel.** Reading costs about 235 instructions a byte (EXECUTED). Two 10,000-line files of 250,000 bytes each cost about 118,000,000 instructions to read, 0.6% of the default fuel. The search costs at most (N+M)·(D+1) diagonal steps before the expensive bound bites: at N = M = 10,000 and a tenth of the lines changed (D = 2,000) that is 40,000,000 steps, which at an estimated 15 instructions a step (INFERRED) is 600,000,000 instructions, 3% of the fuel. A pair beyond that is held to the expensive bound, and past the fuel the line ends with exit 137; the docstring states this profile and names no limit.
- **Per line, in memory.** `diff` holds both inputs, 8 bytes of offset and 4 of class per line, and two arrays of 2·(N+M)+3 entries of 8 bytes. Two 250,000-byte, 10,000-line inputs hold about 500,000 + 240,000 + 640,000 bytes, about 1.4 MB of the 64 MiB default. Two inputs past the line's `memory_bytes` end the line at that budget, which a host may raise through `limits` (`host.py:59-73`). The docstring names the future direction for inputs past it: hold only the changed middle once the common prefix and suffix are set aside. `cmp` holds two chunks of at most 64 KiB each (`crates/vfs-shell/src/machine/files.rs:16`).
- **On the vfs host.** Each open is one read of the whole body, held under `READING_BYTES`, 128 MiB, as for every program (`host.py:85-88`). Nothing new is held there.
- **Per file write, per index visit, per batch, per corpus, per lock.** None: both programs only read.
- **Engines.** No SQL is added, so the least generous engine served, SQLite or Postgres, meets only the statements `read` and `stat` already issue.

## Left as it is

- The kernel's own unified diff of a version against the next, `difflib.unified_diff` in `src/vfs/models/versioning.py:57`, and the preview of roadmap story H2. They render inside the kernel, not in a line, and their format is theirs.
- The machine's slice and fuel defaults, the line's deadline and `memory_bytes`. Decision 11 leaves every bound where the shell spec set it.
- `sort`'s decoding of its input with `from_utf8_lossy` (`text.rs:1160`). It is `sort`'s, not this work's.

## Tests

Written first, and seen failing, at the layer each behaviour lives. Every test counts or compares states; none reads a clock. No storage changes, so no engine leg is added: the vfs-host tests run on the default in-memory storage, as the shell's other tests do. No right changes; the read test below holds that a file the caller cannot read stays unread.

**The corpus, against GNU.** `crates/vfs-shell/tests/corpus.rs::the_corpus_matches_the_known_failures_list` runs every new case against `MemoryHost`. Each case is `# tier: program` and `# world: none`, makes its files with `printf`, and ends each command with `echo "status=$?"`.

- `tests/shell/cases/programs/diff/`: `identical-files-print-nothing`, `one-changed-line-in-normal-format`, `added-lines-in-normal-format`, `deleted-lines-in-normal-format`, `several-groups-in-normal-format`, `unified-with-two-labels`, `unified-context-of-one`, `unified-hunks-merge-when-their-context-overlaps`, `unified-hunk-of-an-empty-side`, `no-newline-at-end-in-normal-format`, `no-newline-at-end-in-unified-format`, `a-repeated-line-added-slides-as-gnu-slides`, `a-line-repeated-many-times-is-discarded-as-gnu-discards`, `two-minimal-scripts-print-as-gnu-chooses`, `brief-says-only-that-files-differ`, `report-identical-files`, `ignore-case-folds-ascii-only`, `ignore-space-change`, `ignore-all-space`, `new-file-reads-a-missing-operand-as-empty`, `minimal-on-a-pair-with-many-repeats`, `a-missing-operand-is-trouble`, `a-missing-file-is-trouble`, `dash-reads-standard-input`, `a-file-against-a-directory-compares-its-namesake`, `process-substitution-operands`, `binary-files-differ`, `text-reads-binary-as-lines`, `options-after-operands`, `an-invalid-option-is-trouble`, `a-diff-into-head-stops-early`.
- `tests/shell/cases/programs/cmp/`: `identical-inputs-exit-zero`, `the-first-difference-names-its-byte-and-line`, `silent-prints-nothing`, `a-shorter-input-reports-eof`, `verbose-lists-every-differing-byte`, `print-bytes`, `a-limit-stops-the-comparison`, `ignore-initial-skips-each-input`, `skip-operands-skip-each-input`, `dash-reads-standard-input`, `a-missing-file-is-trouble`, `a-directory-operand-is-trouble`, `bytes-past-ascii-compare-as-bytes`.

**The laws, on the native build** (`crates/vfs-shell/tests/laws.rs`).

- `diff_and_cmp_print_the_same_whatever_the_chunk_boundaries`: a line of `diff`, `diff -u --label a --label b` and `cmp -l` over two files of `world()` prints the same as whole under `read_chunks` of `[1]`, `[2]`, `[3]` and `[5]`, each run through the helper `chunked` of unit 168-2's decision 15, which fails a run that asks no more reads than the whole run; a 64-byte size is added only with files longer than 64 bytes, beside the existing `output_is_the_same_whatever_the_chunk_boundaries`.
- `a_diff_past_the_memory_budget_ends_the_line_at_its_count`: with `memory_bytes` of 1 MiB, a `diff` of two 600 KB files ends `Budget("memory", 1048576)`, and the same pair at 4 MiB exits 1.
- `a_long_diff_hands_control_back_each_round_and_cancel_ends_it`: with `slice: 1`, a line that generates two pathological inputs with builtin loops into `<(…)` and runs `diff` over them returns `Running` with no request on more steps than the same line with `cmp` in its place, by at least the rounds the unit test below counts for that pair; a `cancel` during the search ends it `Cancelled, 130`.

**The core, as unit tests** (`#[cfg(test)] mod tests` in `crates/vfs-shell/src/programs/diff.rs`, as `sed.rs:2312` has).

- `an_edit_script_rebuilds_the_second_input`: over 2,000 pairs from a fixed seed, applying the script's deletions and insertions to the first input yields the second, in both formats.
- `a_script_is_minimal_where_no_line_repeats_often`: for pairs whose every line occurs at most twice, so the discard pass drops only unmatched lines, the script's changed lines equal N + M − 2·L, where L is a longest common subsequence computed in the test by the quadratic table.
- `one_changed_line_in_ten_thousand_takes_steps_in_proportion_to_the_lines`: the counted diagonal steps for a 10,000-line pair with one line changed are at most 2·(N+M).
- `the_expensive_bound_caps_a_pathological_pair`: on a 20,000-line pair of repeated short lines, the steps counted under the default are at most a tenth of those under `--minimal`.
- `the_search_stack_holds_ranges_not_frames`: the largest depth of the subproblem stack for that pair is at most ⌈log2(N+M)⌉ + 1.

**On the vfs host** (`tests/shell/test_programs.py`).

- `test_a_diff_or_cmp_case_runs_on_the_vfs_host_as_bash_recorded_it`: every case under `programs/diff/` and `programs/cmp/` not in `known_failures.txt` prints its record's standard output and status through `run_line`, built as `test_a_grep_or_find_case_runs_on_the_vfs_host_as_bash_recorded_it` is (`:232-256`).
- `test_a_diff_of_two_files_is_a_stat_and_a_read_of_each_as_the_caller`: with `_spy` (`:48`) on every verb, `diff /work/a /work/b` and `cmp /work/a /work/b` each call `stat` twice and `read` twice, all as the line's authority, and nothing else.
- `test_a_diff_of_a_file_the_caller_cannot_read_prints_none_of_it`: under posture `none`, with `list` on `/s` and `read` on `/s/open.txt` only, `diff /s/open.txt /s/secret.txt` and `cmp /s/open.txt /s/secret.txt` print `Permission denied` for the secret file, exit 2, and no byte of its body appears in the result, built as `test_a_served_grep_leaves_out_a_file_the_caller_may_list_but_not_read` is (`:554`).

**The walls** (`tests/shell/test_host.py`).

- `test_a_diff_ends_at_the_lines_fuel_or_deadline_as_any_line_does`: two pathological 20,000-line files are written as the system actor; `diff` over them under `fuel=10**8` ends `budget_exhausted` naming fuel with exit 137; under `fuel=10**15` and a deadline of 0.05 seconds it ends `timeout` with exit 124; under the defaults it exits 1 with `fuel_used` above 10**8, which shows the search, not the reads, spent the fuel. After each, `echo after` runs on the same storage, as in `test_each_wall_ends_a_line_and_the_process_goes_on` (`:598`).

**The sample** (`crates/vfs-shell/tests/measured_corpus.rs`). `the_weighted_sample_runs_at_its_floor` passes at the raised floor of decision 17.

After the Rust edits, the environment is rebuilt with `uv sync --all-extras --group dev --reinstall-package vfs-py` before the Python tests run, as AGENTS.md requires.

## Scope

In:

- `crates/vfs-shell/src/programs/diff.rs` and `crates/vfs-shell/src/programs/cmp.rs`, new.
- `crates/vfs-shell/src/programs/mod.rs`: `NAMES`, the dispatch in `run`, and `Prog::chunk`.
- `tests/shell/cases/programs/diff/` and `tests/shell/cases/programs/cmp/`, the scripts and their records; `tests/shell/known_failures.txt` where a case does not yet pass.
- `crates/vfs-shell/tests/laws.rs`, `crates/vfs-shell/tests/measured_corpus.rs`, `tests/shell/test_programs.py`, `tests/shell/test_host.py`.
- `research.md` in this work directory, the study of decision 16.
- `documentation/reference/shell.md`.

Out:

- `diff -r` and the comparison of two directories: a spec of its own when a measured corpus asks for it, since it lists directories and reaches the verb builtins.
- The context and side-by-side formats, and modification times in a header (choice 1).
- `diff3`, `sdiff` and `patch`: no measured use.
- `sort`, `uniq`, `tr` and `tee` under the split law, and the `awk` and `jq` hints: unit 168-2, [its spec](../2026-11-25-sort-uniq-tr-and-tee-run-as-kernels-pinned-by-gnu-fixtures/spec.md).
- The coverage harness's rate: story F5.
- `--help` and `--version` for the library's programs as a whole; decision 7 refuses them here as `sort` and the others do not yet serve them either.

## What the docs must say

- `documentation/reference/shell.md:80`, "The Programs": the list gains `cmp` and `diff`, and the sentence names GNU diffutils beside coreutils, grep, sed and findutils.
- A subsection under it, "`diff` and `cmp`": the served forms of decisions 4 and 5; that a form outside them exits 2 with "is not supported"; that a unified header shows no modification time; and that a diff too large or too slow ends the line at its memory, fuel or deadline, as any line ends.
- The docstrings of `diff.rs` and `cmp.rs` state each program's cost profile (decision 11, the Cost section) and name no spec.

## Earlier decisions this reverses

- The source's "`diff` takes the deadline" and the `TextKernel(..., deadline)` constructor ([the source](../../context/specifications/archive/168-text-program-kernels/spec.md), lines 45, 128, 139, 164). Replaced by decision 11: the line's fuel and deadline bound the search, and the core stores none.
- The source's two layers, a Python program over a Rust core in `crates/vfs-core/src/shell/` (its section 1.1). Replaced by decision 1: one library program in the shell crate.
- The source's recorded fixtures from `scripts/record_shell_fixtures.sh` on the CI image (its line 152). Replaced by decision 16: the one recorder and its pinned image.

## Not checked

- No case was recorded, and Docker was not run. That the pinned image holds GNU diffutils is INFERRED from its package being essential in Debian; its version was not read.
- GNU's internals named in decisions 8 and 14 (the discard rule, the expensive bound, the tie-breaking, the shift rule and the binary prefix) are written from the published algorithm and the GNU manual's account of it, not read from a pinned commit of diffutils or gnulib. The study of decision 16 reads them; where it disagrees, the study wins and the decision's wording follows it.
- Whether the GNU hosts that serve diffutils and gnulib are reachable from a build session.
- The 15 instructions a diagonal step costs is an estimate. The 235 instructions a read byte costs was measured.
- That line 73 of the weighted sample counts as run once `diff` resolves, since its two `sort` stages read files that `MemoryHost` does not hold; the floor is set to whatever the test then measures.
- That the step counts of the slice law separate `diff` from `cmp` by the margin stated; the margin is set from the unit test's round count when the test is written.
- `cargo test`, `pytest` and `scripts/docs.sh check` were not run.

## Choices to confirm

1. **What a unified header shows after the label.** GNU prints a tab and the file's modification time. The machine's `Stat` reply carries a kind and a size and no time (`crates/vfs-core/src/shell_binding.rs:20-21` imports the reply shapes), so printing it needs the reply and the wire to carry `updated_at`. The options: no time, as GNU itself prints when `--label` is given; or a time from an extended `Stat` reply. Side taken: no time. It changes no wire, and adding the time later is an additive field of one reply, while a time added now would need its wire change reviewed before this work can land.
2. **A pair of directories.** GNU compares two directories file by file without recursing, printing `Only in` and `Common subdirectories` lines. The options: refuse it with exit 2 (decision 7), or serve it from `ls` of both. Side taken: refuse. Serving it later is additive, and it has no measured use.
3. **The served flag set.** Decision 4 stops short of `-B`, `-E`, `-Z`, `-I` and `--strip-trailing-cr`, which only change which lines compare equal. The options: refuse them now (decision 7), or serve them now. Side taken: refuse. Each can be served later without changing what a served form prints.

## One line

`diff` and `cmp` join the shell's library as byte-faithful programs that follow GNU diffutils' discard, Myers search and boundary shift, read each operand once as the caller, and are bounded by the line's existing fuel, deadline and memory count, with GNU's recorded answers as the referee.
