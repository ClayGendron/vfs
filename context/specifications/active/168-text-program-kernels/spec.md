# 168 — Text program kernels: the measured text programs in Rust behind their Unix names

- **Status:** draft — cut 2026-10-15 from ADR 082 pins 3–5 and the catalog study; amended the same day by the pre-build review (`research/studies/2026-10-15-agent-shell/13-spec-168-review-before-build.md`) and Clay's six decisions on it. Lands after spec 167, in three slices (168a, 168b, 168c). Not started. One `[NEEDS CLARIFICATION]` in §1.
- **Date:** 2026-10-15
- **Owner:** Clay Gendron
- **Kind:** feature (`crates/vfs-core` gains a `shell` module of stateful byte kernels fed and drained through the extension; each text program becomes a Python layer in `vfs/shell/programs/` that holds the call's `fs` around a Rust core that holds nothing; the runner gains the `xargs` builtin and the `find -exec` rewrite).
- **Depends on:** spec 167 (the ABI, the runner, the forms table, the status table, the coverage harness); ADR 057 (one engine; readable oracles in `tests/support/`); ADR 082 pins 3–5; ADR 083 pins 2, 4, 9, 10; ADR 084 pin 5 (the budgets). Spec 169 serves the names this spec leaves out (`awk`, `jq`, the uutils set).
- **Decided 2026-10-15 (Clay, on the review's six questions):**
  1. Programs with no measured use are not Rust kernels. Spec 169's uutils wasm set serves them.
  2. `awk` is a real awk, a wasm program (onetrue-awk or goawk built for WASI) installed like `jaq` by spec 169. There is no Rust awk subset. Until 169 lands, `awk` refuses with a hint.
  3. The `jq` forms kernel is dropped. `jaq` as a wasm program serves `jq` (spec 169).
  4. vfs accepts BSD's `sed -i ''` (253 of 258 measured `sed -i` uses) beside GNU's `-i[SUF]`.
  5. `cut -c` counts characters, POSIX's rule; `-b` counts bytes.
  6. A bytes-bodied `read` crosses the pipe raw, like Unix: `cat img.png | wc -l` counts newline bytes and `wc -c` prints the size. The placeholder never enters a pipe. Every kernel sees bytes; "bytes-capable" is a note on which programs mean something on binary input, never a correctness switch.
- **Research it stands on:** the memo §2, §4, §5 and study `02-program-catalog.md` (the tier-2 table, per-program costs, the uutils wasm facts); the corpus `experiments/e2/commands.md`; the review's executed census `experiments/r168/` (`form_census.out`, `skeletons.out`, `call_tiers.out`), which re-ran E2's splitter with E2's privacy rule and records every flag and every script shape.

## Intent

After this spec the measured text programs an agent pipes through run as Rust kernels on byte chunks, each under its Unix name with its real flags. The six programs spec 167 wrote in Python (`head`, `tail`, `wc`, `cut`, `nl`, the `sed` forms) move to Rust with a parity test against their old Python form. `sort`, `uniq`, `tr`, `tee`, `diff` and `cmp` arrive as new kernels. `xargs` and `find -exec` arrive as runner builtins that re-enter the union, so no program ever runs another.

The gain is honest and small. By head words, the kernels of this spec serve at most 139 of 13,746 measured calls (1.0%) that spec 167 cannot (`call_tiers.out`). `awk` was 213 of the 357 calls tier 2 unlocks; it arrives with spec 169 as a wasm program, together with `jq` and the long tail.

## 1. The programs

### 1.1 What a row is

Every program in this spec is a row in spec 167's kernel program table. A row has two layers:

- **The Python layer** (`vfs/shell/programs/<name>.py`) is the `Program`. It holds `Call.fs` and nothing else with authority. It parses argv with the row's `Forms`, resolves operands, reads them, feeds the core, drains it to stdout, and makes every write.
- **The Rust core** (`crates/vfs-core/src/shell/<name>.rs`) holds no file access, no Python objects and no policy. Bytes in, bytes out, an exit code and stderr lines.

Operands. `-` and a missing operand mean stdin. Every other operand is read with one `read` per operand batch, projecting `data` for a bytes-bodied row and `content` otherwise, so the core always receives the file's own bytes. The core is fed one input at a time, in operand order. A text-shaped program never receives a placeholder: the placeholder is a terminal render only (decision 6).

Writes. `tee F…` and `sort -o F` write once per file, at end of input, with the whole body; their file side materializes and the docstring says so. A `tee` whose downstream closes early still reads its input to the end and writes the whole body, then reports `vfs.cancelled` as info for its stdout. Every verb call a program makes counts against `VERB_CALL_BUDGET`.

Binary input. Every core sees bytes. The `binary` note on a row only says the program is meaningful on non-text input (`wc -c`, `cmp`, `head -c`, `tail -c`); the runner never changes what it feeds a core because of it.

### 1.2 The slices

**168a — the seam and the measured core.** The kernel seam (§2). The six programs that change kind, with parity tests (§3.1). `sort`, `uniq`, `tr`, `tee` as new kernels. The `awk` and `jq` refusals.

**168b — the runner builtins.** `xargs` (§1.5) and the `find -exec` and `-delete` rewrite (§1.6).

**168c — `diff` and `cmp`.** A Myers unified-diff core we own, with the line's deadline (§4).

### 1.3 The first forms

"Measured" counts are `form_census.out`'s, on 2026-10-15. A listed flag that is not measured is still GNU's flag with GNU's meaning (ADR 082 pin 5): the corpus orders forms, it never renames them. Everything else in a program's known grammar refuses `vfs.unsupported.form`, exit 2; an unknown flag is `vfs.invalid`, exit 2.

| Slice | Program | First forms | Measured | Notes |
|---|---|---|---|---|
| a | `head`, `tail` | as spec 167 | `head -N`, `tail -N`, `-n`, `-c` | moved to Rust; `tail -f` stays unsupported; `binary` |
| a | `wc` | `-l -w -c -m -L`, totals over several operands | `-l` 666, `-w` 21, `-c` 20, `-m` 3 | moved to Rust; `binary`; `-m -L` count characters (§1.4) |
| a | `cut` | `-c LIST`, `-b LIST`, `-d D -f LIST`, `-s`, `--complement`, `--output-delimiter` | `-c` 479, `-f` 10, `-d` 8 | moved to Rust; `-c` counts characters, `-b` bytes (§1.4) |
| a | `nl` | `-ba -bt -w N -s SEP -v N` | `-ba` 141, `-v` 45 | moved to Rust; `cat -n` calls the `nl` core |
| a | `sed` (forms) | §1.3.1 | `-n` 8,324, `-i` 258, `-e` 43, `-E` 29 | moved to Rust; the script is parsed before input is read |
| a | `sort` | `-n -r -u -k KEYDEF -t D -V -h -f -s -c -o F` | `-n` 84, `-r` 69, `-u` 34, `-k` 18, `-t` 7, `-V` 3, `-h` 2 | stable; materializes (§4); `-R` is out: it is random and no fixture can pin it |
| a | `uniq` | `-c -d -u -i -f N -s N -w N` | `-c` 87, `-f` 1 | streams |
| a | `tr` | `SET1 SET2`; escapes `\n \t \\ \NNN`; `-d`, `-s`, `-c`; then ranges `a-z` and classes `[:upper:]` | 132 uses: escape sets 114, literal 18; `-d` 22, `-s` 6; ranges 0, classes 0 | characters on UTF-8 (§1.4) |
| a | `tee` | `F… -a` | 105 uses, `-a` 4 | passes bytes through; writes as §1.1 |
| a | `awk` | — | 371 | refuses until spec 169: `unrecognized`, exit 127, hint "awk arrives as an installed program; for a line range use `sed -n 'A,Bp'`, for a field use `cut -d D -f N`" |
| a | `jq` | — | 0 | refuses until spec 169: `unrecognized`, exit 127, hint naming the installed `jaq` |
| b | `xargs` | `-n N -I R -0 -d D -r -t -P N` | 52 uses; `-I` 4; children `grep` 32, `wc` 9 | a runner builtin (§1.5) |
| b | `find -exec`, `find -delete` | `-exec C A… {} +`, `-exec C A… {} … ;`, `-delete` | `-exec` 7 (`+` 5, `;` 2); `-delete` 0 | a planner rewrite (§1.6) |
| c | `diff` | `-u -U N -q -w -b -i -N` | 29 uses; `-q` 4, `-u` 1 | materializes both inputs; takes the deadline (§4); `-r` is out (it walks directories) |
| c | `cmp` | `-s -l -n N` | 1 | `binary`; streams both inputs in step |

#### 1.3.1 The `sed` subset

The constructor parses the whole script before any input is read. The subset is a grammar:

- **Addresses:** `N`, `$`, `/re/`, `A,B`, `A,+N`, `A,/re/`, `/re/,$`, `/re/,/re/`.
- **Commands:** `p`, `d`, `q`, and `s/re/repl/` with flags `g`, `I`, `p` and a number `N`.
- **Lists:** commands joined by `;`, by newlines, or by repeated `-e`.
- **Flags:** `-n`, `-E`, `-e`, `-i[SUF]`, and BSD's `-i ''` (decision 4: under GNU an empty-string script means nothing useful, so accepting it changes no GNU behavior).
- **Write-back:** `-i` stays in the Python layer as spec 167 built it: a fixed-string `s///` goes through `edit`; a regex one reads, feeds the core, and writes.

A script outside the subset raises `UnsupportedForm` naming the first token outside it and its column. The kernel does not try to tell invalid sed from unimplemented sed. `y`, `a`, `i`, `c`, the hold space and labels are outside (0 measured uses); the full language is a later kind under the same name.

Measured shapes this subset serves (`skeletons.out`): `-n 'A,Bp'` 7,883; `s///` 244 and `s///g`; `/re/,/re/p` 143; `;`-joined commands 94; `A,+N` 55; `/re/,$p` 36; `Np` 21.

#### 1.3.2 Regular expressions

`sed` defaults to BRE and `-E` selects ERE. The BRE-to-ERE translator lives in Rust beside the `sed` parser; spec 167's `grep` calls it through the seam instead of keeping a Python twin. A backreference in a pattern is `UnsupportedForm` (the `regex` crate has none). A replacement's `\1`…`\9` and `&` are supported.

### 1.4 Characters and bytes

`cut -c`, `tr`, `wc -m`, `wc -L` and `nl` work on characters when the input is valid UTF-8 and on bytes otherwise (decision 5, POSIX's rule). `cut -b` always works on bytes. So `cut -c1-200`, 479 of the 490 measured `cut` uses, never splits a character and never turns a text line into invalid UTF-8.

Sorting and comparing are by code point, which for UTF-8 is byte order: `LC_ALL=C.UTF-8`. Locale collation is out of scope.

### 1.5 `xargs`

`xargs` is a runner builtin, not a `Program`. It holds no `fs`.

- **Input.** It consumes bytes. It splits on blanks and newlines with GNU's quoting rules; `-0` splits on NUL and `-d D` on `D`.
- **Batches.** A batch is at most `-n N` arguments and at most `ARGV_BYTE_BUDGET` bytes (128 KiB, GNU's own default `-s`). `-I R` makes one batch per input line and substitutes `R` in the child's arguments.
- **The child.** Its name is resolved once, at plan time, through the union, with the usual gate: a name the caller cannot list is 127, one it cannot read is 126. With no command the child is `echo`. Each batch runs the child with empty stdin.
- **Output.** `xargs` produces the child's declared shape and passes the children's chunks through unchanged, in batch order.
- **Budgets.** Each batch is one dispatch against `VERB_CALL_BUDGET`.
- **Empty input.** The child runs once with no batch arguments, as GNU; `-r` suppresses that run.
- **Accepted flags.** `-P N` is accepted and runs serially. `-t` writes each command line to stderr before it runs.
- **Status.** 0 when every child exits 0; 123 when any child exits 1–125; 124 when a child exits 255; 126 or 127 from resolution. 123 joins spec 167's `shell/status.py`.

### 1.6 `find -exec` and `-delete`

`find` is a verb builtin with no execution capability, so `-exec` never runs inside it. The planner rewrites the line before it runs:

- `find ARGS -exec C A… {} +` becomes `find ARGS -print0 | xargs -0 C A…`.
- `find ARGS -exec C A… {} … ;` becomes `find ARGS -print0 | xargs -0 -I{} C A… {} …`.
- `-delete` is `find` calling the `delete` verb on its result rows, in batches of `ROWS_PER_CHUNK`. A verb builtin calling a verb is not a program running a program.

Status is `find`'s: a child failure under `;` leaves `find` at 0; a child failure under `+` makes it 1.

### 1.7 Not in this spec

Served by spec 169's uutils wasm set (decision 1; zero measured segments): `tac`, `join`, `expand`, `unexpand`, `od`, `base32`, `md5sum`, `sha1sum`, `sha256sum`, `sha512sum`, `cksum`, `split`, `csplit`, `yes`. Not in uutils and not measured, so later and on demand: `rev`, `column`, `hexdump`, `xxd`, `strings`. `awk` and `jq` arrive as wasm programs in spec 169 (decisions 2, 3). `diff -r` walks directories and belongs with the verb builtins when demand appears.

`[NEEDS CLARIFICATION: base64 (9 uses), fold (8), paste (7) and comm (2) are measured but rare, and uutils' wasm set serves all four. Do they wait for spec 169 like the zero-use names, or become 168c kernels? Leaning: spec 169, by the same rule, since together they are under 0.04% of segments.]`

## 2. The seam

Each program's core is one stateful object in a `shell` module of `crates/vfs-core`, fed by Python and drained by Python, in the shape the crate already uses for `PostingsBuilder`. One generic class serves every program:

```
TextKernel(program: str, options: list[tuple[str, str | None]], *,
           memory_budget: int, deadline: float | None)
feed(chunk: bytes, input: int = 0) -> bool   # True: needs no more input
end_input(input: int = 0) -> None
drain(byte_cap: int) -> bytes | None         # at most byte_cap bytes pending
status() -> tuple[int, list[str]]            # exit code, stderr lines
```

- **Push, chunk by chunk.** The Python layer owns the asyncio loop: for each stdin chunk it calls `feed`, then drains with `byte_cap = BYTES_PER_CHUNK` and puts each drained buffer on stdout. Rust never pulls from a Python iterator. Only `sort`, `diff` (and `tac` when it becomes a kernel) buffer their input, inside Rust; every other core holds at most one partial line between feeds.
- **Early close.** `feed` returns `True` when the core needs no more input (`head` reached its count). The Python layer stops reading, closes its stdin, and the producer is cancelled as ADR 083 pin 10 says.
- **Refusals before input.** The constructor validates option values (a `cut` LIST, a `sort` KEYDEF, a `sed` script). It raises `_native.UnsupportedForm(program, form, column)` or `_native.InvalidForm(program, form, column)`, two exceptions declared with `create_exception!`. The Python layer maps them to `vfs.unsupported.form` or `vfs.invalid`, exit 2, before any input is fed. Python's `Forms` owns flag names; Rust owns flag values.
- **Off the GIL.** `feed`, `end_input` and `drain` run their work in `py.detach`.
- **Budgets.** `memory_budget` is `MEMORY_BYTE_BUDGET`; a core that buffers counts its bytes against it and stops with `budget_exhausted`. `deadline` is the line's `WALL_TIME_BUDGET` turned into seconds, as `ContentMatcher` takes it; past it a core stops with `vfs.timeout`.
- **Where dispatch lives.** The Python layer dispatches through `extension()`; `vfs/native.py` gains nothing, per its own rule that dispatch lives with each surface's owner. `PROTOCOL_VERSION` and `EXPECTED_PROTOCOL` go from 10 to 11. `_native.pyi` gains `TextKernel` and the two exceptions. `lib.rs`'s crate docstring gains a line for the `shell` module.

## 3. Tests

### 3.1 Parity for the six that change kind

Six names change kind: `head`, `tail`, `wc`, `cut`, `nl`, and the `sed` forms. Before the move, each 167 program is split into a pure `bytes → bytes` transform and its `fs` layer. The transform moves to `tests/support/oracles/shell/<name>.py` (ADR 082 pin 4); the `fs` layer stays in `src/` around the new core. The `sed` oracle uses Python `re`, never the engine. Its parity test runs only on patterns both engines accept; a pattern Rust refuses is `UnsupportedForm` on the kernel side and is pinned as such. `tests/test_oracles.py` walks subpackages (`pkgutil.walk_packages`), so `oracles/shell/` stays under its no-engine guard.

### 3.2 New kernels: fixtures, the split law, and cargo tests

Python oracles exist for the six above and nowhere else (ADR 057 decision 2: a readable oracle earns its place only where it pins a parity test). A new kernel is pinned by three things:

1. **Recorded fixtures.** `scripts/record_shell_fixtures.sh` runs each form under GNU coreutils and GNU sed on the Ubuntu CI image, with `LC_ALL=C.UTF-8`, and writes the outputs with the tool versions in each file's header. A CI job reruns it and diffs against the committed set; drift fails the job and uploads the new set as an artifact, which a developer reviews and commits. Tests read the committed fixtures and never run a host tool.
2. **The split law.** For every kernel and every fixture input, the output is identical however the input is cut into chunks: whole, one byte at a time, and at seeded random boundaries (the precedent is `test_fuzz_rows_identical_across_batch_boundaries`).
3. **`cargo test -p vfs-core`** covers each core's own cases.

`KNOWN_DELTAS`, beside the fixtures, lists every place vfs differs from GNU on purpose, each with its reason, so no difference is silent: character `cut -c` (§1.4); BSD `sed -i ''`, recorded by running GNU's `-i` and filed under the BSD spelling; no `sort -R`.

The Python layers in `src/` meet the 100% coverage gate, including the `UnsupportedForm`, `InvalidForm`, `budget_exhausted` and `timeout` branches. Oracles carry no coverage obligation.

## 4. Scale and the performance pins

- **Streaming cores** hold at most one partial line between feeds: `head`, `tail -n +N`, `wc`, `cut`, `nl`, `sed`, `uniq`, `tr`, `tee`'s stdout, `cmp`.
- **Materializing cores** say so in their docstring and count their buffered bytes against `MEMORY_BYTE_BUDGET`, stopping with `budget_exhausted` that names the budget and the refine move (`head`, or a narrower `grep`): `sort` (every mode), `tail -n N` (its last N lines), `diff` (both inputs), and the file side of `tee` and `sort -o`. The docstring names the future direction, an external merge sort through `/.vfs/run` scratch. That is a profile, not a declared limit.
- **`diff`** takes the deadline: Myers costs O(N·D), and a pair of 10,000-line inputs with many edits is the slow case.
- **Pins count operations, never the clock:** chunks fed, chunks drained, bytes crossing the seam (`feed` plus `drain` sizes), materializations, verb calls, child dispatches.

## Scope

In: §1.3's table, the seam, the `xargs` builtin, the `find` rewrite, the tests of §3. Out: `awk`, `jq` and the uutils set (spec 169); the full `sed` language; `diff -r`; `tar`, `gzip` and archives (wasm); `sqlite3` (wasm); `printf` beyond the whitelist; locale collation.

## Acceptance criteria

**168a**

1. Every program of slice a is a row with a forms table; `--help` renders from it; an unimplemented known form is `vfs.unsupported.form`, exit 2, and an unknown flag `vfs.invalid`, exit 2. A refused form or script calls `feed` 0 times (spied).
2. The parity tests pass for `head`, `tail`, `wc`, `cut`, `nl` and the `sed` forms against their spec 167 transforms as oracles. `tests/test_oracles.py` finds the `oracles/shell/` modules.
3. Each new kernel of slice a passes its fixtures and the split law; `KNOWN_DELTAS` lists every delta the fixtures exercise.
4. Over a 10,000-line, 640 KiB file, `cat f | sort | uniq -c | sort -rn | head -5` feeds 10 chunks to the first `sort`; each `sort` materializes once (counted); the maximum queue depth is 2 at every seam; `head` drains 1 chunk and closes; the second `sort` reports `vfs.cancelled` as info.
5. `yes`-shaped early close: a producer of unbounded bytes into `head -1` emits 1 chunk past `head`, and the producer is cancelled after at most `QUEUE_DEPTH + 1` chunks (counted).
6. `printf 'h\xc3\xa9llo\n' | cut -c1-2` prints `hé` as a `content` row; `cut -b1-2` of the same input yields a `data` row.
7. `cat img.png | wc -c` prints `size_bytes`; `cat img.png | wc -l` prints the count of 0x0A bytes in the image (decision 6).
8. `sed -i '' 's/a/b/' f` and `sed -i 's/a/b/' f` leave the same body.
9. A `sort` over input larger than a test-sized `memory_budget` stops with `budget_exhausted` naming `MEMORY_BYTE_BUDGET`.
10. `awk '{print $1}'` and `jq .` are `unrecognized`, exit 127, each with its hint.

**168b**

11. With 25 matching files, `find . -name '*.py' | xargs -n 10 grep -l TODO` calls the `grep` verb 3 times (spied); each child receives empty stdin; the `Call` type a program receives has no execution capability.
12. `xargs` returns 123 when one of three children exits 1, and 0 when all exit 0; `printf '' | xargs -r grep x` dispatches 0 children and `printf '' | xargs grep x` dispatches 1.
13. `find . -name '*.tmp' -exec rm {} +` plans as `find … -print0 | xargs -0 rm` (the plan is inspected) and deletes in batches of at most `ROWS_PER_CHUNK` per `delete` call (counted).

**168c**

14. `diff -u a b` matches its fixtures and the split law; a diff started past the deadline stops with `vfs.timeout`; `cmp -s` exits 0, 1 or 2 as GNU.

**Every slice**

15. The coverage harness's in-scope run rate rises over the rate recorded when spec 167 landed (168a and 168c together by at least one point); the flag rate covers every flag of this spec's programs with ten or more uses in `form_census.out`.
16. `scripts/ci.sh` green at 100%; `cargo test -p vfs-core` green; the wheel budget holds.

## Landing notes

(Filled in on landing.)
