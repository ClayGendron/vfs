# Review of spec 168 — text program kernels, before build

Reviewer: pre-build review, 2026-10-15. Tree at `main` (`ac5c515`), working tree as found. Nothing under `src/`, `crates/` or `tests/` was modified. Scripts and their outputs are in `experiments/r168/`.

**What I read, in order.** `specs/active/168-text-program-kernels/spec.md`; its parent `specs/active/167-the-shell-pipeline-core/spec.md`; ADR 082 (pins 3–5), ADR 083 (the pipe), ADR 084 pin 5 (the budgets), ADR 057 (one engine; oracles); the memo `research/2026-10-15-the-agent-shell-prior-art-and-experiments.md` §2, §4, §5, §14; study `02-program-catalog.md` (F3, F6, F7, the tier tables); `experiments/e2/commands.md` and `mine_commands.py`; study 03's exit-code table; the live seam `src/vfs/native.py`, `src/vfs/_native.pyi`, `crates/vfs-core/src/python.rs` and `lib.rs`; `tests/support/oracles/__init__.py`, `tests/test_native.py`, `tests/test_oracles.py`; `pyproject.toml`'s coverage block; `scripts/ci.sh`'s wheel budget; `.github/workflows/test.yml`.

**Evidence labels.** **EXECUTED** (a script or command ran; output beside it in `experiments/r168/`), **READ** (a file read, cited `file:line`), **INFERRED** (my reasoning from the two, or outside knowledge not checked here).

**A note on the census.** E2's `commands.md` keeps only the top 200 flags and no script text, so it cannot answer "which awk programs" or "which sed scripts". I re-ran E2's own splitter over the same transcripts with three scripts that keep E2's privacy rule. They write flag tokens and *shape labels* only, never argument text (`form_census.py`, `skeletons.py`, `awk_coverage.py`, `call_tiers.py`). The transcripts are live, so counts drift by a few between runs (this review's own probes show up as one `cut --complement` and one `cut -b`). The `.out` files are the record.

## Readiness score: 39 / 100

The score is out of 100 across eight dimensions. Each dimension has a weight. A full score means a developer could build that dimension without inventing anything.

| # | Dimension | Weight | Score | Why, in one line |
|---|---|---:|---:|---|
| 1 | Sized for one landing | 15 | 4 | 39 names, three language subsets and a diff engine; 20 names have zero measured uses (finding 1). |
| 2 | Forms precise enough to build and test | 15 | 7 | Simple flag lists are exact; `sed`, `awk`, `jq` forms are not a grammar; locale and multibyte unstated (4, 7, 8). |
| 3 | Consistent with the corpus | 10 | 4 | Adds unmeasured forms (`y`, `a i c`, `jq`) and misses the measured top forms of `awk`, `sed` and `tr` (4, 14). |
| 4 | Seam fits the live crate | 15 | 5 | `(args, chunk_iter) -> chunk_iter` cannot run under the asyncio runner and contradicts `native.py`'s own rule (2). |
| 5 | Consistent with ADRs and spec 167 | 10 | 5 | Six programs change kind, not four; kernels that write contradict "no file access"; `wc` on media contradicts 167 (3, 5, 11). |
| 6 | Acceptance criteria testable with counts | 15 | 6 | Criteria 3 and 4 name no numbers; criterion 5 mixes two metrics; no chunk-boundary law (13). |
| 7 | Bounded at scale, under the budgets | 10 | 5 | `sort` materializes and says so; `MEMORY_BYTE_BUDGET`, `tee`, `split`, `diff` cost are unaddressed (12). |
| 8 | Nothing left to invent | 10 | 3 | `xargs`, `find -exec`, operand reading, fixture recording and the oracle userland are all open (6, 7, 9, 10). |
| | **Total** | **100** | **39** | |

## Findings, most severe first

### 1. The slice is about four landings, not one — **blocking**

- **Spec lines.** 38–61 (the table), 84–89 (Scope).
- **Problem.** The table names 39 programs. Three of them are languages (`sed`, `awk`, `jq`), and one is a diff engine. The catalog's own costs put this far past one landing. A median text program is 525 lines of Rust in bashkit. bashkit's `sed` is 4,171 lines, `awk` 10,111, and `jq` 9,820 (it vendors jaq) (READ `02-program-catalog.md` F6). The spec also asks for a Python oracle and a bash fixture set for every one of the 39.
- **Evidence.** EXECUTED `form_census.out`. These 20 names have **zero** segments in the transcripts: `tac`, `rev`, `join`, `expand`, `unexpand`, `column`, `od`, `hexdump`, `base32`, `md5sum`, `sha1sum`, `sha256sum`, `sha512sum`, `cksum`, `split`, `csplit`, `jq`, `yes`, `find -delete`, and `diff -r`. EXECUTED `call_tiers.out`: by head words, spec 168 alone unlocks at most **355 of 13,487 calls (2.6%)**. `awk` appears in **212** of them, `sort` in 102, `tr` in 66, `uniq` in 45, `diff` in 9. READ `02-program-catalog.md` F7: uutils' wasm feature set (78 utilities) covers 14 of those 20 names. The ones it lacks are `rev`, `column`, `hexdump`, `jq`, `find -delete` and `diff -r`. Spec 169 ships that set as installed programs ("the wasm set serves the names no kernel has yet", 169 spec lines 147–151), and `jaq` for `jq`.
- **Amendment (spec text).** Replace the table's framing with three slices:
  - "**168a — the seam and the measured core.** The kernel seam (§2 as amended by finding 2). The six programs that change kind (`head`, `tail`, `wc`, `cut`, `nl`, the `sed` forms), with parity tests. `sort`, `uniq`, `tr`, `tee`. The `xargs` builtin and `find -exec`/`-delete` (findings 9, 10)."
  - "**168b — the `awk` subset** (finding 4). About 60% of the calls this spec unlocks."
  - "**168c — `diff` and `cmp`**, with a deadline (finding 12)."
  - "The 20 names with no measured use are served by spec 169's uutils wasm set until demand is measured. `jq` is served by 169's `jaq` (question 3)."

### 2. The seam shape cannot be built as written — **blocking**

- **Spec lines.** 67–72.
- **Problem.** The spec says `vfs/native.py` exposes each kernel "as a function over `(args, chunk_iter) -> chunk_iter`". Three things are wrong with that.
  1. **The runner is async.** Spec 167 §4 runs one asyncio task per stage, with `asyncio.Queue` between stages. A Rust function cannot pull from a Python async iterator. Even a sync iterator would make Rust call back into Python, under the GIL, once per chunk.
  2. **`native.py` says dispatch does not live there.** READ `native.py:13-19`: "Per-surface dispatch lives with each surface's **owner**, never here." Chunking is the one stated exception.
  3. **Nothing is said about** errors, early close, output bounding, the protocol version, or the type stub.
- **Evidence.** READ `python.rs:43-89` and `:245-310`. The crate already has a streaming shape: a `#[pyclass]` that Python feeds (`PostingsBuilder.add_docs`, `LexicalBuilder.add_docs`) and then drains in capped batches (`next_batch(byte_cap)`). Heavy work runs off the GIL in `py.detach`. READ `python.rs:95-160`: `ContentMatcher` takes a wall `budget` and turns it into a deadline inside Rust. READ `python.rs:106-110`: a bad pattern today is a bare `ValueError`, so Python cannot tell "unsupported" from "invalid". EXECUTED `uv run python -c …`: the extension speaks `PROTOCOL_VERSION` 10 and exposes 19 names. EXECUTED `cargo test -p vfs-core -- --list`: 62 tests in 8 modules, 1.6 s to list.
- **Should a kernel stream chunk by chunk, or take whole buffers?** Stream, by push. One FFI call per 64 KiB chunk costs nothing next to the work. Whole buffers would break ADR 083 pin 9 for `head`, `cut` and `tr`, and break early close (`yes | head -1`). The kernels that must see everything (`sort`, `tac`, `diff`) buffer *inside* Rust and say so (finding 12).
- **Amendment (spec text).** Replace §2's first bullet with:
  > "Each kernel is one `#[pyclass]` in a `shell` module of `crates/vfs-core`, fed by Python and drained by Python, in the shape of `PostingsBuilder`:
  > ```
  > TextKernel(program: str, options: list[tuple[str, str | None]], *, memory_budget: int, deadline: float | None)
  > feed(chunk: bytes, input: int = 0) -> bool      # True: needs no more input (head reached its count)
  > end_input(input: int = 0) -> None
  > drain(byte_cap: int) -> bytes | None            # at most byte_cap bytes of pending output
  > status() -> tuple[int, list[str]]               # exit code and stderr lines, after the last end_input
  > ```
  > The constructor validates the option *values* (a `cut` LIST, a `sort` KEYDEF, a `sed` script). It raises `_native.UnsupportedForm(program, form, column)` or `_native.InvalidForm(program, form, column)`, two exceptions declared with `create_exception!`. The Python wrapper maps them to `vfs.unsupported.form` or `vfs.invalid`, exit 2, before any input is read. Python's `Forms` owns flag *names*; Rust owns flag *values*. Work in `feed`, `end_input` and `drain` runs in `py.detach`. The wrapper lives in `vfs/shell/programs/` and dispatches through `extension()`; `native.py` gains nothing. `PROTOCOL_VERSION` and `EXPECTED_PROTOCOL` go to 11; `_native.pyi` gains the class and the two exceptions."

### 3. Programs that touch files are not kernels; who reads and writes is unstated — **blocking**

- **Spec lines.** 32–36 ("`consumes = produces = bytes` … a Rust function over a byte stream"), 47 (`tee`), 43 (`sort -o F`), 51 (`diff -r`), 54 (`sha256sum` reads `stat`), 55 (`split`, "many `write`s").
- **Problem.** ADR 082 pin 3 says a text kernel has "no file access". But every text program takes file operands (`sort f`, `wc -l a b c`, `cut -c1-200 f`). And `tee`, `sort -o`, `split`, `csplit`, `md5sum -c`, `diff a b`, `paste`, `comm` and `join` read or write files by name. The spec does not say where those calls happen. A developer must invent the split. They also must invent how `tee` writes. vfs `write` takes a whole body, so a per-chunk append would be a read plus a write each time.
- **Evidence.** READ ADR 082 `:95-101`; ADR 083 pin 7 (the producer projects `data` only for a byte-shaped consumer); ADR 084 pin 5 (`VERB_CALL_BUDGET` 10,000 per program run).
- **Amendment (spec text).** Add to §1:
  > "A row is a Python program holding `Call.fs` around a Rust core that holds nothing. The Python layer resolves operands (`-` is stdin). It reads each operand with `read`, projecting `data` for a bytes-capable form and the rendering or placeholder for a text-only form. It feeds the core one input at a time. It makes every write. `tee F` and `sort -o F` write once, at end of input, with the whole body; they materialize the file side and say so. `split` and `csplit` send one batched `write` per `ROWS_PER_CHUNK` outputs, never one call per file. Every verb call counts against `VERB_CALL_BUDGET`. `diff -r` is out: it walks directories, has no measured use, and belongs with the verb builtins."

### 4. The `sed`, `awk` and `jq` "forms" are not bounded, and the forms table cannot refuse them — **blocking**

- **Spec lines.** 57–59; criterion 1 (lines 93–95).
- **Problem.** Spec 167's `Forms` is an option grammar: short, long, takes-value, repeatable, exclusive groups (167 lines 96–100). For `sed` and `awk`, the "form" lives *inside the script*, not in a flag. So the table cannot refuse `sed 'y/a/b/'` or an awk `getline`. Something must parse the script before input is read. The spec does not say what. It also does not bound the subsets. "Ranges" and "pipes" are not grammar. And the listed forms are the catalog's INFERRED list, not the measured one.
- **Evidence (awk).** EXECUTED `skeletons.out`, `awk_coverage.out`. 364 awk programs reduce to **111 distinct shapes**. The top shape is `NR>=A && NR<=B {print NR": "$0}`, with **70** uses (plus 15 with `printf` and 9 more with `&& /re/`). The spec does not list it. Next is `/re/,/re/` with 61. `!seen[$0]++` has **0** uses and `NR==N` has 0. The spec's forms, read generously, serve **95 of 364 programs (26%)**. A small grammar subset serves **349 (96%)**: patterns with `NR`/`$N` comparisons, regex, `~`, ranges, `&& || !`; actions with `print` and `printf` over concatenation, assignment, `+=`, `++`, `next`, `exit`, `sub`/`gsub`; `BEGIN`/`END`; scalar variables. The subset leaves out arrays, user functions, loops, `getline`, `split` and `substr`.
- **Evidence (sed).** EXECUTED `skeletons.out`. `y` and `a i c` have **0** uses, yet the spec adds them. Measured shapes the spec omits: `;`-separated commands (`-n '1,5p;10,20p'`, **94**); GNU's `addr,+N` (**55**); `/re/,$p` (**34**); `A,/re/p`. Also, **253 of 258** `sed -i` uses are the BSD spelling, `-i ''` (finding 7).
- **Evidence (jq).** EXECUTED `form_census.out`: **0** segments. Spec 169 already ships `jaq` (169 lines 153–154, criterion 6).
- **Amendment (spec text).** Replace the three rows with:
  > "`sed` and `awk` scripts are parsed in Rust by the kernel constructor, before any input is read. The subset is a grammar, stated below. A script outside it raises `UnsupportedForm` naming the first token outside the subset and its column. The kernel does not try to tell invalid awk from unimplemented awk, because only the full parser could. **`sed` subset:** addresses `N`, `$`, `/re/`, `A,B`, `A,+N`, `A,/re/`, `/re/,$`; commands `p`, `d`, `q`, `s///` with flags `g`, `I`, `p`, `N`; commands joined by `;`, newlines or repeated `-e`; flags `-n`, `-E`, `-e`, `-i[SUF]`, plus BSD `-i ''` (question 4). **`awk` subset:** as listed above, with `-F` (a single character or `\t`) and `-v`. **`jq`:** served by spec 169's `jaq`; no forms kernel."

### 5. Six programs change kind, not four, and the old code cannot become an oracle as written — **should fix**

- **Spec lines.** 25–26 ("the four programs … `head`, `tail`, `sed` forms, `wc`"), criterion 2.
- **Problem and evidence.**
  - READ 167 lines 117–124: spec 167 also writes `cut -c -b -d -f -s` and `nl -ba -bt -w -s -v` in Python, and `cat -n` shares `nl`'s numbering. So six names change kind. `cat -n`'s side of the shared code is unstated.
  - The 167 code mixes the transform with `fs` calls: `sed -i` goes through `edit` or `read` plus `write`; `head file` calls `read`. Under ADR 082 pin 4 the old code becomes the oracle, so it must first be split into a pure transform.
  - READ 167 line 121: 167's regex `s///` is "Rust regex replace". An oracle that calls the engine referees nothing, and `test_oracles.py:12-18` forbids it. If the oracle uses Python `re` instead, the two engines differ: Python `re` accepts backreferences and lookaround that Rust `regex` refuses (INFERRED, documented behavior of both crates).
  - EXECUTED (scratch package): `pkgutil.iter_modules` is not recursive, so it returns `['a', 'sub']` and never `sub.b`. The guard at `test_oracles.py:13` would not check modules in `tests/support/oracles/shell/`.
- **Amendment (spec text).** "Six names change kind: `head`, `tail`, `wc`, `cut`, `nl`, and the `sed` forms. `cat -n` calls the `nl` kernel. Before the move, each 167 program is split into a pure `bytes → bytes` transform and its `fs` layer. The transform moves to `tests/support/oracles/shell/` and the `fs` layer stays in `src/`. The `sed` oracle uses Python `re`. The parity test runs only on patterns both engines accept, and a pattern Rust refuses is `UnsupportedForm` on the kernel side. `test_oracles.py` switches to `pkgutil.walk_packages`."

### 6. A Python oracle for every kernel brings back the cost ADR 057 removed — **should fix**

- **Spec lines.** 73–75, criterion 2 ("for every kernel against its Python reference and its bash fixture").
- **Is there a coverage conflict?** No. READ `pyproject.toml:156-164`: coverage measures `src/vfs` and omits `tests/*`, so oracles carry no coverage obligation, as ADR 057 says. The Python wrappers in `src/` must still reach 100%, including the `UnsupportedForm` and `InvalidForm` branches.
- **The real conflict is cost.** READ ADR 057 Context: "Every kernel is written twice" was the first cost it removed. Decision 2 keeps a readable oracle "only where it pins a parity test". Where none is worth keeping, the test uses "a deliberately slow, obviously-correct loop written in the test". ADR 082 pin 4 asks for an oracle only "when a name changes kind". A new kernel already has a better referee in the recorded userland fixture. A Python twin of ~33 programs (just-bash's median is 233 lines each, F6) adds about 7,000 lines that test nothing the fixture misses.
- **Amendment (spec text).** "Python oracles exist for the six names that change kind (finding 5) and nowhere else. A new kernel is pinned by three things: its recorded fixtures (finding 7); a chunk-boundary law, meaning the output for any split of the input into chunks equals the output for the whole input (the precedent is `test_fuzz_rows_identical_across_batch_boundaries`, `test_native.py:405`); and its own `cargo test` cases."

### 7. The "bash oracle" is really a userland oracle, and its flavor and locale are not pinned — **should fix**

- **Spec lines.** 74–75; 167 §7 (lines 203–207); criterion 2.
- **Problem.** `/bin/bash` is not what produces the output; `cut`, `sort`, `sed` and `awk` do. Which ones they are depends on the host.
- **Evidence.** EXECUTED on this Mac: `/bin/bash` 3.2.57; `sort` is "2.3-Apple"; `cut --complement` fails with "illegal option"; `awk` is one-true-awk 20200816. The same `sort` gives `a A b B` under `en_US.UTF-8` and `A B a b` under `C`. READ `.github/workflows/test.yml:26`: CI runs on `ubuntu-latest`, which has GNU coreutils, GNU sed, and (INFERRED) `mawk` as `awk`. The corpus itself is BSD-shaped: 253 of 258 `sed -i` uses are `-i ''` (EXECUTED `skeletons.out`). Under GNU sed, that spelling reads `''` as the script and `s/x/y/` as a file. Spec 167 also says fixtures are "recorded in CI … never live in a test run", but a CI job cannot commit files.
- **Amendment (spec text).** "Fixtures are recorded by `scripts/record_shell_fixtures.sh`, run by a developer in a pinned Linux container, and committed. They use GNU coreutils and GNU sed at named versions, and one named `awk` (question 2). They run under `LC_ALL=C.UTF-8`, which collates by code point and counts UTF-8 characters. Each fixture file records the tool versions in its header. Every place vfs deliberately differs from GNU is listed in a `KNOWN_DELTAS` table beside the fixtures, never silently: the BSD `-i ''` spelling, character `cut -c` (finding 8), and no `sort -R`."

### 8. Multibyte behavior is unstated, and the top `cut` form can print a placeholder instead of text — **should fix**

- **Spec lines.** 42 (`cut`), 45 (`tr`), 48 (`rev`), 50 (`fold`), 41 (`wc -m -L`).
- **Problem.** `cut -c1-200` is **479 of 490** `cut` uses (EXECUTED `form_census.out`). Agents use it to trim long lines. GNU `cut -c` counts bytes (INFERRED from GNU documentation: "-c … currently the same as -b"). Cutting by bytes can split a UTF-8 character. ADR 083 pin 6 then turns that output into a `data` row, and the renderer prints the media **placeholder** instead of the text.
- **Evidence.** EXECUTED: `printf 'h\xc3\xa9llo\n' | LC_ALL=C cut -c1-2` gives `68 c3 0a`, which is invalid UTF-8. Under a UTF-8 locale, BSD `cut` gives `68 c3 a9 0a`, which is `hé`.
- **Amendment (spec text).** "`cut -c`, `tr`, `rev`, `fold`, `wc -m` and `wc -L` work on characters when the input is valid UTF-8 and on bytes otherwise. `cut -b` always works on bytes. This is a declared delta from GNU's byte `-c`, listed in `KNOWN_DELTAS`. Test: `cut -c1-2` of `héllo` prints `hé` as a `content` row."

### 9. `xargs` is under-specified — **should fix**

- **Spec lines.** 56; criterion 4.
- **Evidence.** EXECUTED `form_census.out`: 52 `xargs` segments. The child is `grep` in 32 and `wc` in 9. The only flag seen is `-I{}` (4); `-n -0 -r -d -P -t` are unmeasured. READ study 03 lines 707–722: the exit-code table has no 123, which is GNU's code for "a child failed". READ ADR 084 pin 5: `ARGV_BYTE_BUDGET` is 128 KiB, the same as GNU xargs' default `-s` (131,072 bytes; INFERRED from GNU's docs).
- **What a developer would have to invent.** What xargs receives (rows or bytes), how batches form, what the child's stdin is, what shape xargs produces, and what status it returns.
- **Amendment (spec text).**
  > "`xargs` is a runner builtin, not a `Program`, and it holds no `fs`. It consumes bytes. It splits on blanks and newlines with GNU quoting; `-0` splits on NUL and `-d D` on D. A batch is at most `-n N` arguments and at most `ARGV_BYTE_BUDGET` bytes. `-I R` makes one batch per input line and substitutes R. The child name is resolved once, at plan time, through the union with the usual gate (127 or 126). Each batch runs the child with empty stdin. xargs produces the child's declared shape and passes the children's chunks through in order. Each batch counts as one dispatch against `VERB_CALL_BUDGET`. Status, as GNU: 0; 123 if any child exited 1–125; 124 if a child exited 255; 126 or 127 from resolution. With no input, the child runs once unless `-r` is given. `-P` is accepted and runs serially. `-t` echoes each command line to stderr. With no command, the child is `echo`. Add 123 to `shell/status.py`."
  
  Criterion 4 becomes: "With 25 matching files, `find . -name '*.py' | xargs -n 10 grep -l TODO` calls the `grep` verb 3 times (spied). The child receives empty stdin. No `Program` is handed an execution capability (the `Call` type has none)."

### 10. `find -exec` and `-delete`: "a shell loop" is undefined — **should fix**

- **Spec line.** 60.
- **Evidence.** EXECUTED `form_census.out`: `-exec` has 7 uses (`rm` 4, `cat` 2, `sh` 1; terminator `+` 5, `;` 2). `-delete` has 0. `find` is a verb builtin with no execution capability (ADR 082 pin 2), so `-exec` cannot run inside it.
- **Amendment (spec text).** "The planner rewrites `find ARGS -exec C A… {} +` as `find ARGS -print0 | xargs -0 C A…`, and rewrites `-exec C A… {} … ;` as `xargs -0 -I{} C A… {} …`. `-delete` is `find` calling the `delete` verb on its result rows in batches. That is a verb builtin calling a verb, not a program running a program. Status is find's: `;` failures leave find at 0, and a `+` failure makes it 1."

### 11. `wc` on a media row contradicts spec 167 — **should fix (product choice)**

- **Spec line.** 41 ("bytes-capable (`-c` counts `size_bytes` of a media row)").
- **Evidence.** READ 167 criterion 4: `cat img.png | wc -l` prints **1**, and `cat img.png | wc -c` prints `size_bytes`. If `wc` is bytes-capable as a whole program, `-l` counts the 0x0A bytes inside the PNG, which is what GNU does. That breaks 167's "1". If it is text-only, `-c` counts the placeholder. One `consumes` per program cannot give both answers.
- **Amendment.** Either "`bytes_capable` is declared per form in the forms row: `wc -c` reads `data` and `-l -w -m -L` read the placeholder; a mixed `-lc` reads `data`", or amend 167 criterion 4 to the native count. See question 6.

### 12. Materializing kernels and the budgets — **should fix**

- **Spec lines.** 78–82.
- **Evidence.** READ ADR 084 pin 5: `MEMORY_BYTE_BUDGET` is 256 MiB and `VERB_CALL_BUDGET` is 10,000 per program run; both trip `budget_exhausted`. READ ADR 083 pin 9: a consumer that must see everything materializes and says so. The spec names only `sort`.
- **Amendment (spec text).** "These materialize, each with a docstring that says so: `sort` (every mode), `tac`, `column -t`, `diff`, `comm`/`join`/`paste` over file operands, and the file side of `tee` and `sort -o`. Each counts its buffered bytes against `MEMORY_BYTE_BUDGET` (the `memory_budget` constructor argument) and stops with `budget_exhausted`, naming the budget and the refine move (`head`, or narrow the `grep`). The docstring names the future direction: an external merge sort through `/.vfs/run` scratch. That is not a declared limit. `diff` takes the line's deadline, as `ContentMatcher` does (`python.rs:95-160`), because Myers costs O(N·D) and a 10,000-line pair with many edits is the slow case."

### 13. The acceptance criteria do not count — **should fix**

- **Criterion 3** names no numbers. Replace it with: "Over a 10,000-line, 640 KiB file, `cat f | sort | uniq -c | sort -rn | head -5` passes 10 chunks into the first `sort`; each `sort` materializes once (counted); the maximum queue depth is 2 at every seam; `head` emits 1 chunk and closes; the second `sort` is cancelled with `vfs.cancelled` as info."
- **Criterion 4.** See finding 9.
- **Criterion 5** mixes two metrics. The intent's 87% → 89% is a share of *segments*. "In-scope run rate" is a share of *calls* (167 §7), and 167 sets its own bar at 85%. EXECUTED `call_tiers.out`: 168 can add at most 2.6% of all calls, and 60% of those need `awk`. So 88% is reachable only with the broad `awk` subset of finding 4. Replace it with: "The harness's in-scope run rate rises by at least 2 points over the rate recorded when 167 landed, and the flag rate covers every flag in `form_census.out` with ten or more uses."
- **Missing tests.** Add: the chunk-boundary law for every kernel (finding 6). Early close: `yes | head -1` emits 1 chunk, and `yes` is cancelled after at most `QUEUE_DEPTH + 1` chunks. `UnsupportedForm` raised before any input is fed (spied `feed`, 0 calls). "Bytes copied" in §3 is undefined: define it as bytes crossing the FFI seam, or drop it.

### 14. The simple programs' first forms versus the corpus — **should fix (one gap), otherwise fine**

The lists are mostly GNU supersets of what was measured. That is allowed under ADR 082 pin 5 (native flags; the corpus only orders). One measured form is missing, and one listed flag cannot be pinned.

| Program | Measured (EXECUTED `form_census.out`) | Spec lists, not measured | Gap |
|---|---|---|---|
| `cut` | `-c` 479, `-f` 10, `-d` 8 | `-b -s --complement --output-delimiter` | none |
| `sort` | `-n` 84, `-r` 69, `-u` 34, `-k` 18, `-t` 7, `-V` 3, `-h` 2 | `-f -s -c -R -o` | `-R` is random and cannot match a fixture; give it a seed under test, or leave it out |
| `uniq` | `-c` 87, `-f` 1 | `-d -u -i -s -w` | none |
| `tr` | 132 uses: **escape sets** (`'\n'`) 114, literal 18; `-d` 22, `-s` 6; **classes 0, ranges 0** | classes, ranges | **escapes are not listed**: add "`\n \t \\ \NNN` escapes" to the first forms |
| `nl` | `-ba` 141, `-v` 45 | `-bt -w -s` | none |
| `tee` | 105 uses, `-a` 4 | — | none |
| `diff` | `-q` 4, `-u` 1 | `-r -w -b -i -N` | `-r` is out (finding 3) |
| `wc` | `-l` 666, `-w` 21, `-c` 20, `-m` 3 | `-L` | none |

### 15. One BRE translator, not two — **should fix**

- **Evidence.** READ 167 line 108: `grep` translates BRE to ERE (in Python, in slice 167). `sed` defaults to BRE too. Its script is parsed in Rust (finding 4), so a second translator would appear in Rust. Two translators drift, as ADR 057 found for the two tokenizers. Rust `regex` has no backreferences in patterns (INFERRED, documented).
- **Amendment.** "The BRE-to-ERE translator lives in Rust, beside the `sed` parser. `grep`'s Python translation calls it through the seam. A backreference in a pattern is `UnsupportedForm`."

### 16. Nits

- §1's header says every row is `consumes = produces = bytes`. That is false for `xargs` (finding 9) and for the writers (finding 3).
- `yes` "refused without one" is ambiguous at the terminal boundary and under `>`. Simpler: `yes` runs under the call's budgets like any program, and the wall budget ends it.
- `sha256sum` reading `content_hash` off `stat`: READ `models/version.py:74,79`, the hash is SHA-256 of `content.encode()` or of `data`. ADR 083 pin 4 adds "a trailing newline" when rows render. Pin a test that `sha256sum f` equals `cat f | sha256sum` for a file with no final newline, or the shortcut and the stream disagree.
- §2 should say the kernel module is `crates/vfs-core/src/shell/` and that `lib.rs`'s crate docstring gains a line for it.
- 167 line 63 says `find -iname` is 168's, but `-iname` is in 167's own `find` list (167 line 110).
- `crates/vfs-core/Cargo.toml` still says the module is `vfs._accel` (stale; outside this spec).
- The wheel budget is not at risk. EXECUTED: the last release wheel is 9.4 MB against a 50 MB budget (`scripts/ci.sh:25`).

## What the spec gets right

- **One name, many kinds**, with a parity test at the swap. It is the right way to move 167's Python to Rust without changing what agents type.
- **Text kernels have no file access.** Once finding 3 splits the Python layer from the Rust core, the ADR 069 no-side-door rule holds for every kernel by type.
- **`xargs` is a builtin that re-enters the union**, not a program that spawns programs. That is the right shape, and `find -exec` can reuse it (finding 10).
- **`sort` says it materializes**, and the performance pins count operations, never the clock (CLAUDE.md, ADR 083 pin 9).
- **The full `sed`, `awk` and `jq` languages are deferred.** That is right. The fix is only to bound the subsets by grammar and by measurement (finding 4).

## Questions only Clay can answer

1. **The long tail.** Should the 20 names with no measured use be hand-written Rust kernels in 168, or be served by spec 169's uutils wasm set until a use shows up? *Proposed:* uutils serves them. 168 writes kernels only for measured names.
2. **`awk`.** Build the measured grammar subset in Rust now (96% of measured programs; about 60% of the calls 168 unlocks)? Or ship a wasm `awk` (one-true-awk or goawk) in 169? And which `awk` is the fixture oracle (gawk, mawk, or one-true-awk)? *Proposed:* the Rust subset as 168b, with one-true-awk as the oracle because it is the POSIX reference and is what this Mac runs.
3. **`jq`.** Drop the forms kernel and let 169's `jaq` be the default `jq`? *Proposed:* yes, since it has 0 measured uses and a second `jq` would need its own parity test.
4. **GNU or BSD as "native".** The fixtures are GNU, but the agents typed BSD's `sed -i ''` 253 times out of 258. Accept the BSD spelling as a declared delta? *Proposed:* yes. An empty-string script means nothing useful to GNU, so accepting it changes no GNU behavior.
5. **Characters or bytes for `cut -c`.** GNU cuts bytes, which can print a placeholder in vfs. Use characters on valid UTF-8 as a declared delta? *Proposed:* yes.
6. **`wc` on an image.** Should `cat img.png | wc -l` print 1 (spec 167's criterion; needs a per-form shape) or the count of newline bytes (GNU)? *Proposed:* per-form, keeping 167's answer, since an agent asking for the lines of an image wants the placeholder's one line.

## Verdict

Spec 168 is not ready to build. Its direction is right. One name with many kinds, kernels with no file access, `xargs` as a builtin, and counted performance pins all fit the ADRs and the live crate. But four gaps block it. It is about four landings packed into one, and 20 of its 39 names have no measured use. Its seam signature cannot run under the asyncio runner and ignores the crate's own feed-and-drain pattern. It never says who reads operands or makes writes for the programs that need files. And the `sed`, `awk` and `jq` "forms" are neither a grammar nor the measured shapes: the listed awk forms serve 26% of real programs, while a small stated subset serves 96%. Fix those four, settle the six questions, and pin the oracle's userland and locale. Then slice 168a (the seam, the six moved programs, `sort`, `uniq`, `tr`, `tee`, `xargs`) can land in one pass. In one line: right idea, too big, and the seam and script subsets need to be written down before anyone builds.

## Executed scripts

- `experiments/r168/form_census.py` → `form_census.out`: segments per program, every flag token, sed and awk shape labels, `xargs` children, `find -exec` children and terminators, `tr` set shapes.
- `experiments/r168/skeletons.py` → `skeletons.out`: awk and sed scripts reduced to language-only skeletons (strings → `S`, regex → `/R/`, numbers → `N`, names → `v`, shell expansions → `$(C)`/`$v`), shapes seen fewer than 3 times omitted; the BSD `-i ''` count.
- `experiments/r168/awk_coverage.py` → `awk_coverage.out`: the spec's listed forms against the proposed subset (95 vs 349 of 364).
- `experiments/r168/call_tiers.py` → `call_tiers.out`: calls that need only tier-1 plus tier-2 heads (355 of 13,487), and which tier-2 heads they need.
- Inline: `cargo test -p vfs-core -- --list` (62 tests, 8 modules); `uv run python` against `vfs.native.extension()` (protocol 10, 19 names); host userland probes (`sort --version`, `cut --complement`, `cut -c` on `héllo` in C and UTF-8 locales, `sort` under two locales); `pkgutil.iter_modules` on a scratch package (not recursive); the last release wheel's size (9.4 MB).
