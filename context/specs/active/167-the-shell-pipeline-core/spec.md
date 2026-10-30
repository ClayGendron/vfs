# 167 — The shell: the pipeline core, the verbs and builtins as programs, and the `cli` meta-verb

- **Status:** draft — cut 2026-10-15 from ADRs 081, 083, 084 and 085 (proposed the same day) and the memo they stand on. Amended the same day by the pre-build review (`../../../research/studies/2026-10-15-agent-shell/12-spec-167-review-before-build.md`) and Clay's eleven decisions on it (recorded under *Decisions of 2026-10-15* below). Five slices, A to E, landing in order. The content of `0.1.0a1` (spec 166 amended). Not started. No open `[NEEDS CLARIFICATION]`.
- **Date:** 2026-10-15
- **Owner:** Clay Gendron
- **Kind:** feature (a new package `src/vfs/shell/`: the parser, the program table, the pipeline runner, the `cli` meta-verb; the renderer's placeholder and budget; `overwrite=` on `copy` and `move`; `case_mode` on `glob`; four session fields; the removal of `run` and `SupportsRun`; a coverage harness under `tests/`).
- **Depends on:** ADR 081 (the grammar), ADR 083 (the pipe), ADR 084 (the gate order and budgets), ADR 085 (the placeholder, the cap), ADR 082 pins 1–5 and 10–13 (the ABI and resolution; the `/.vfs` views themselves are spec 169). Spec 148's amendment (the session fields, in §7 here). Spec 155 folds into slice A. Each ADR carries the amendments listed under *ADR amendments this spec needs*.
- **Decisions it implements:** ADRs 081, 083, 084 (pins 1, 3, 4, 5, 6, 9), 085 (pins 2, 3, 9, 10); ADR 082 pin 12 (`run` retired).
- **Research it stands on:** `../../../research/2026-10-15-the-agent-shell-prior-art-and-experiments.md` §2–§5, §8, §9 and the studies `01-shell-grammar.md`, `02-program-catalog.md`, `03-program-abi-and-bin-namespace.md`, `06-execution-policy.md`, `07-session-state.md`, `09-agent-shell-peers.md`, `12-spec-167-review-before-build.md`; the executed references `experiments/s3/abi_demo.py`, `experiments/s7/shell_session.py` and `experiments/r167/`; the corpus `experiments/e2/commands.md`.

## Intent

After this spec an agent types `grep -rn "mfa" /enterprise | head -20` and gets exactly what bash would print. Every verb is gated as if the agent had called `grep` through the Python API. The call returns one `Result`. Its display is stdout, then stderr, as bash prints them. Its rows are the structured form of stdout. Its errors are the classified facts. A refused construct refuses before anything runs and says what to rewrite. A media file crosses a pipe as its raw bytes, like Unix, and prints a placeholder at the terminal, never base64. About 87% of the measured agent command segments run after this spec.

## Decisions of 2026-10-15 (Clay, on the review)

These settle the review's product questions. Every section below follows them.

1. **`grep` on a pipe filters the rendered lines, exactly as bash does.** `ls | grep x` filters names. Rows pass between programs as `Observation`s only through an explicit form: `xargs` (spec 168), or a verb called with rows explicitly (the Python API's `observations=`). Never silently.
2. **The `cli` surface prints exactly what bash prints.** Nothing for an empty `ls`. Nothing after a mutation unless `-v`. Paths as typed, relative to `cwd`. No trailing slash without `-F`. Spec 155's markers stay on the verb tools, not on `cli`. A host adapter may add one `(no output)` line.
3. **A single bytes-bodied read crosses the pipe raw, like Unix.** `cat img.png | wc -l` counts newline bytes; `wc -c` is the size; `cat a.png > b.png` is exact; `cat report.pdf | grep` searches the bytes. The placeholder appears only in a multi-row render and at the terminal display. The rendering is `cat --rendered` (or the read tool).
4. **No shell state persists between `cli` calls over the wire.** Each call starts at `workdir`, default `/`. The in-process `Session` keeps `cwd` and `env` for Python hosts.
5. **`time` is admitted** as a builtin keyword.
6. **The verdict is `isError = not result.success`.** A program's own non-zero exit (`grep` with no match, `false`) is not a failure. `$?` is separate. A stage's classified fatal error is in `Result.errors`.
7. **`copy` and `move` gain `overwrite=`.** The flag-to-call table is §4.1.
8. **Two projections.** A plain pipe rendering, and a display rendering at the `cli` boundary with the 32,768-character cap. The pipe adds no newline to a file body.
9. **`Fs` refuses relative paths.** The system-actor refusal checks the authority the router actually uses.
10. **`SupportsRun` is deleted, not renamed.** `cli` goes in the drift test's `MANAGEMENT_METHODS`. `glob(case_mode=)` is its own task with all five engine legs.
11. **The Oils spec suite** is fetched as a second yardstick after slice 2 of ADR 081, when control flow exists.

## Slices and landing order

Five slices. Each lands green on its own (`scripts/ci.sh`); C and D also run the four engine legs before landing.

| Slice | Name | Sections | Needs |
|---|---|---|---|
| **A** | The renderer and the vocabulary | §1 | nothing |
| **B** | The parser | §2 | nothing (lands before or after A) |
| **C** | The pipe, the ABI and `cli` | §3, §5, §6, §7, the minimal programs of §4 | A and B |
| **D** | The program forms | the rest of §4, §4.1, `overwrite=`, `case_mode` | C |
| **E** | The coverage harness and the docs | §8 | D |

## 1. Slice A — the renderer and the vocabulary (the live-tree gaps)

None of this is a shell feature. Each item is a precondition.

1. **`run` and `SupportsRun` leave the tree.** `run` leaves `Op`, `EXEC_OPS` (the class goes; `ALL_OPS` is the union of the three that remain), `VERB_RUNGS`, `PARAMS` in `params.py`, `_DEFAULT_PROJECTION`, `base.py` (the method, the dispatch arm, the import), `session.py`, and `README.md` (lines 19, 61, 99, 103). `SupportsRun` is deleted from `protocol.py`, `_FAMILY_OPS` and `storage/__init__.py`. Spec 170 defines its own capability for the storage-executed kind. The `ops.py` docstring loses the `EXEC_OPS` line and "`run` waits for its own axis".
2. **The tests that used `run` move to a live op.** `test_ops.py` (the vocabulary, `test_a_read_never_mints`, the default-projection test, the agent-surface table), `test_params.py:84,157,205`, `base/test_dispatch.py:1332,1657`, `base/test_authority.py:47`, `base/test_gates.py:170-200` (the capability-gate tests ride on a declared-but-absent op instead, e.g. `glean`), `base/test_mount_admin.py` (the `deny_ops={"run"}` examples become `{"edit"}` or `{"mkedge"}`), `base/test_mounts.py:683-693`, `storage/test_protocol.py:100`, `storage/test_memory.py:20`, `storage/database/test_reads.py:752`, and `support/base_doubles.py:116,355,363-373`.
3. **The placeholder of ADR 085 pin 2**, in `render.py`, for every bytes-sourced row. A row is bytes-sourced when `source == "bytes"` or `data` is populated (a read with `columns={"data", …}` does not populate `source`). Grammar: `[binary <path> <mime> <size>B v<version>[ -- <description>]]`, ASCII, one line, no `|`. It replaces the empty body in `_render_read`, the `repr` of bytes in `_render_block` and in table cells (`_format_field`), and the bare `vfs.unavailable` line for an unrendered binary. A bytes-sourced row with `content` populated (a rendering) prints the placeholder, then the rendering. `text/*` and SVG print as text. Base64 and a bytes `repr` never reach `to_str()`.
4. **The budget of spec 155 §1, opt-in.** `render_result(result, *, projection=None, budget=None)` and `to_str(*, projection=None, budget=None)`. `None` is unbounded. A budget cuts at a line boundary and ends with one marker: `[output truncated: N characters removed, R rows remaining; page with head, tail or sed -n]`. The errors section is never cut. `RENDER_CHARACTER_BUDGET = 32_768` is a declared constant in `render.py`; the `cli` display (§6) and the MCP adapter (spec 171) pass it. Nothing else does.
5. **Spec 155 §2–§5 for the verb tools**: `(empty directory)` and `(no matches)`, the directory slash in `ls`, `glob` and `tree`, collapsed fan-out errors, and `rank` by default for `glean` (`("path", "rank", "matches")`, `#1`, `#2`, …). These decorate `render_result` only. The shell never calls `render_result` for a pipe or for `cli` stdout (§5). `test_ops.py:176-180` moves with the glean projection.
6. **`Result.to_payload(*, include_bytes: bool = False, exclude_none= True, max_errors=None)`.** By default every row's `data` is stripped and `"data"` leaves its populated mask, so a round trip rebuilds an honest "not fetched" row. `include_bytes=True` keeps bytes for in-process round trips and the existing law tests. The `envelope.py` module docstring says the lossless round trip holds under `include_bytes=True`. `to_json` follows `to_payload`.
7. **The kinds module names the shell as a producer.** The producer-exclusivity rule (`kinds.py:43-44`) gains: "the shell emits `unsupported.construct`, `unsupported.form` and `unrecognized` for program names".

## 2. Slice B — the parser (`shell/parse.py`)

- One pass over the command string into an AST shaped after mvdan-sh's: `Script → list[Stmt]`, `Stmt{cmd, redirs, negated}`, `Cmd = Simple{assigns, words} | Pipeline{stmts, timed} | AndOr{op, left, right} | Subshell{list} | Group{list}`, `Word = list[Part]`, `Part = Lit | Single | Double | Dollar | Param{name, op, word} | CmdSubst{list} | Tilde | Glob | Brace`.
- Admits exactly ADR 081 pins 2–5, plus `time [-p]` before a pipeline (decision 5). Refuses the rest of pin 8 at parse time as `vfs.unsupported.construct` and malformed text as `vfs.invalid.syntax`, with pin 9's fields. Both kinds join `KIND_CONTRACTS` with phrase, retry class and hint, and so does `vfs.unsupported.form` (§3). The data keys follow the kinds rule: producer keys are unprefixed (`line`, `column`, `offset`, `construct`, `expected`, `incomplete`).
- **The caret.** A `vfs.invalid.syntax` error renders its one error line as today (`_error_line` keeps its one-line rule). In the display only, a two-line block follows it, built from `data`: the source line with control characters escaped, then spaces and `^` under `column`.
- Parser budgets: `INPUT_BYTE_BUDGET` 1 MiB, `TOKEN_BUDGET` 100,000, `DEPTH_BUDGET` 200, `ITERATION_BUDGET` 1,000,000; an overrun is `vfs.budget_exhausted`, never a hang. Tests feed counted inputs.
- `set -e` parses as the builtin `set` with `-e`/`+e`; the runner owns the semantics (§5).
- Parse-level spec tests in `tests/shell/spec/parse/` assert the AST or the refusal (kind, line, column, construct), never stdout: `quoting`, `expansion`, `redirect`, `heredoc`, `pipeline`, `lists`, `errors`, `refused`. The stdout tests come with slice C.

## 3. Slice C — the program ABI and the table (`shell/programs/`)

- **`Program`** as ADR 082 pin 1: `name`, `forms`, `async main(call) -> int`, and `shapes(args) -> tuple[Shape, Shape]` (consumes, produces), evaluated after the forms parse and before the line runs. The runner plans every seam from the shapes (ADR 083 pin 7).
- **`Call{args, env, cwd, stdin, stdout, stderr, fs, budget}`.**
- **`Fs`** is the router's public verbs, curried with the call's admitted authority (`VirtualFileSystem._admitted(authority)`, never `None`). It has no authority parameter, no grant verbs and no developer verbs. Every call re-enters the public router method, so `_gate_params`, `_gate_entry` and the storage rights fire. `Fs` accepts only absolute paths: a relative path reaching it is a shell bug, classified `vfs.internal`, never routed (the router would silently root it). `VirtualFileSystem.bound(authority) -> Fs` is the one new router method; it is synchronous and not a verb. For `Session.cli`, `Fs` delegates through the session, so a closed session refuses the next verb. For a builtin written in Python, `Fs` is a discipline, not a sandbox (the code could reach the router); it is a boundary for the sandboxed kinds of spec 169.
- **`Forms`**: a declarative option grammar (short, long, takes-value, repeatable, exclusive groups) plus `supported`. The same table answers `--help`. An unimplemented form refuses `vfs.unsupported.form` (naming the program, the form and the kind), exit 2. An unknown flag is `vfs.invalid`, exit 2. Cosmetic flags (`--color`, `--line-buffered`) are accepted and ignored.
- **The table** is a sorted tuple of rows `(name, kind, forms, program)`. `type`, `which`, `command -v` and `help` answer from it (and from `/.vfs/bin` once spec 169 lands).
- **Exit codes** (`shell/status.py`, one table). 0 success. 1 any verb failure inside a builtin, whatever its kind (`permission_denied` included). 2 usage, unknown flag or `unsupported.form`. 124 `vfs.timeout`. 126 a known program the kernel cannot run (`unsupported`, e.g. `curl`) and, from spec 169, a resolved entry the caller cannot read. 127 an unknown name. 130 `vfs.cancelled`. A program's own code otherwise.

## 4. The programs (minimal set in slice C, the rest in slice D)

Every program prints what its GNU counterpart prints (decision 2). Paths print as the operand was typed: `ls P` prints names relative to `P`; `find`, `grep -r` and `glob` print paths with the operand as typed (`.`-relative under `.`, absolute under an absolute operand). Mutations print nothing unless `-v`.

- **Slice C's minimal set:** `cat` (operands, `-`, `--rendered`), `ls` (`-1 -a -A -d`), `glob`, `grep` (the §4.1 core: `-n -r -i -v -l -c -E -F -w -e -h -H --include --exclude`), `head -n -c`, `tail -n -c`, `wc -l -w -c`, `echo -n -e -E`, `printf`, `true`, `false`, `:`, `cd`, `pwd`, `export`, `unset`, `exit`, `time -p`, and the redirections and here-documents of §5.
- **Verb builtins** produce rows in their default form. A verb builtin that reads stdin (`grep`, `rg`, `cat` with no operand or `-`) consumes bytes (decision 1). Slice D adds: `cat -n -b -s`; `ls -l -R -t -S -r -F`; `grep`/`rg` in full (`-L -o -q -s -m -A -B -C`, BRE to ERE, `-P` unsupported; `rg -g -t -T --no-heading --heading --files`); `find` (`-name -iname -path -ipath -type -not ! -o -a -maxdepth -mindepth -prune -print -print0 -newer -size -empty`; `-exec` and `-delete` wait for spec 168's `xargs`); `mkdir -p -v`; `rm -r -R -f -v`; `cp -r -R -n -v`; `mv -f -n -v`; `touch`; `stat -c`; `file -b --mime-type`; `tree -L -a -d -I -P`; `restore`; `glean` and `graph` under their verb names (§4.1).
- **Flag-chosen text forms produce bytes.** A verb builtin produces rows only when its flags select its default rendering (`grep -rn`, `ls`, `ls -1`, `cat`, `find -print`, `glob`, `stat`). Any other text form (`grep -c -l -L -o -h`, `ls -l -F`, `cat -n -b`, `stat -c`, `find -print0`) produces bytes through the program's own renderer. `grep` and `rg` have one renderer each (ADR 082 pin 5).
- **Read-shaped text forms (bytes → bytes, Python in this spec, Rust kernels in spec 168 behind the same names, the Python versions then moving to `tests/support/oracles/`):** `head -n -N -c -q -v`, `tail -n -N -n +N -c -q -v` (`-f` unsupported), `sed -n 'A,Bp' 'Ap' '/re/p' '/re/,/re/p' 'Nq' '/re/d' 'Nd' '$p'`, `sed 's/x/y/[gI]'`, `sed -i`, `wc -l -w -c -m -L`, `cut -c -b -d -f -s`, `nl -ba -bt -w -s -v`, `cat -n`'s numbering shared with `nl`.
- **Regex dialect.** `grep`, `rg` and `sed` share one language: grep's (`pattern_matching/grep.py`, the regex crate's, behind its sre-AST gate). `sed` addresses and `s///` patterns pass the same gate and compile with Python `re` in this spec. The replacement grammar is sed's (`&`, `\1`–`\9`). One shared function translates BRE to ERE (`\( \) \{ \} \| \+ \?`). Spec 168 replaces the Python matcher with a Rust replace kernel; the Python one becomes the oracle.
- **`grep` over stdin** matches the decoded lines with the same verifier the verb uses (`compile_verifier`). Input that is not UTF-8 or holds NUL prints `Binary file (standard input) matches`, as GNU grep does. No file name prints unless `-H`.
- **Shell builtins:** `cd` (`stat` at `list` plus a kind check; `cd -` through `OLDPWD`; `cd` alone to `$HOME`), `pwd`, `echo`, `printf` (`%s %d %f %x %%`), `export`, `unset`, `env`, `printenv`, `set -e +e`, `true`, `false`, `:`, `exit [n]`, `test`/`[` (`-f -d -e -s -z -n -r -w`, `= !=`, `-eq -ne -lt -gt`), `which -a`, `type`, `command -v`, `help`, `sleep`, `timeout`, `time -p`, `date +FMT -u -d`, `basename -s -a`, `dirname`, `seq -s -w`, `whoami` (the caller's principal), `hostname` and `uname` (constants naming the node), `history`. `test -r P` is a `read(P, columns={"path"})` that succeeds; `test -w` is `unsupported.form` in this spec. `sleep`, `date`, `timeout` and `time` read an injectable clock.
- **Probes and swallowing forms raise no fact.** `test`, `[`, `command -v`, `which` and `type` answer by exit code only. `rm -f` on a missing path and `mkdir -p` on an existing directory are success.
- **Never class** (`unrecognized`, exit 127, with the hint the catalog names): `uv`, `git`, `docker`, `ps`, `sudo`, `chmod`, `python3` until spec 172, `source`, `.`, `alias`, `eval`, `exec`, `trap`, `shopt`, the developer-plane verbs (`sweep`, `posture`, `add_member`, `remove_member`), and the rest of the catalog's never table. `git` points at `stat`'s version, the trash view and `restore`; `perl -pi` points at `sed -i`. The verbs with no Unix name that stay out of this spec (`edit`, `mkedge`, `rmedge`, `grant`, `revoke`, `grants`) are `unrecognized` with a hint naming the verb tool. Network programs (`curl`, `wget`) are `unsupported`, exit 126, with the network hint (ADR 084 pin 9).
- `write` is not a program name. `>` and `>>` are its only spelling in this spec.

### 4.1 Each form, its verb call, its rule (slice D)

| Form | Call | Rule |
|---|---|---|
| `ls [-a\|-A] P` | `ls(P)` | names beginning `.` drop unless `-a`/`-A` |
| `ls -l` | `ls(P, columns={kind, size_bytes, updated_at, owner_id, version})` | the long format prints those columns in that order, never mode bits |
| `ls -t -S -r` | `ls(P, columns=…)` | sorted in the shell |
| `ls -d P` | `stat(P)` | |
| `ls -R P` | `tree(P)` | rendered as bash's per-directory sections |
| `mkdir P` | `mkdir(P)` | |
| `mkdir -p P` | `mkdir(P, parents=True, exist_ok=True)` | |
| `rm P` | `stat(P)`, then `delete(P, cascade=False)` | a directory without `-r` is `wrong_kind`, exit 1 |
| `rm -r P` | `delete(P, cascade=True)` | |
| `rm -f P` | as above | `not_found` is success, exit 0, no stderr |
| `cp S D`, `mv S D` | `stat(D)` first; a directory `D` means the destination `D/basename(S)`; then `copy`/`move(..., overwrite=True)` | `cp` of a directory `S` without `-r` refuses "omitting directory", exit 1 |
| `cp -n`, `mv -n` | `overwrite=False` | an occupied destination is skipped, exit 0 |
| `touch P` | absent: `write(path=P, content="")`; present: `stat(P)` | no other effect on a present file |
| `grep` | `-i`→`case_mode="insensitive"`, `-F`→`fixed_strings`, `-w`→`word_regexp`, `-v`→`invert_match`, `-A/-B/-C`→context, `-l`→`output_mode="files"`, `-c`→`output_mode="count"`, `-m`→`max_count` (per file), `--include`→`globs`, `--exclude`→`globs_not`, `-r P…`→`paths` | several `-e` become `(?:p1)\|(?:p2)`, each escaped under `-F`; `-L` is the scope's files minus the `-l` set; `-o` re-matches in the shell with the same verifier |
| `grep x P` | | a directory `P` without `-r` prints "Is a directory", exit 2 |
| `sed -i 's/a/b/g'` | fixed string: `edit(P, old=a, new=b, replace_all=True)` | |
| `sed -i 's/a/b/'` (no `g`), any regex | `read(P)`, first-per-line replace, `write(P)` | |
| `stat -c FMT` | `stat(P)` | `%n %s %y %F` only; any other directive is `unsupported.form` |
| `find P expr` | candidates from `glob("**", paths=(P,), columns={kind, size_bytes, updated_at})` | the predicate tree runs in the shell; `-iname`/`-ipath` filter case-insensitively over those candidates; `FANOUT_BUDGET` truncates with the warning |
| `glean Q [P…]` | `glean(Q, paths=(P…,))` | `--limit N`, `--ext X`, `--glob G`, `--exclude G` |
| `graph METHOD P` | `graph(METHOD, P)` | `--depth N`, `--edge-type T`, `--not-edge-type T`, `--limit N`, `--minimal` |
| `restore P` | `restore(P)` | |

**`copy` and `move` gain `overwrite: bool = False`** (decision 7), a verb change on the router, the params table, the protocol and both backends. An occupied destination under `overwrite=True` is judged as `write` judges an occupied target (`contribute`, or the owner floor), and the replaced body is kept as a version. A file over a directory, or a directory over a file, is `wrong_kind`. The Python default stays `False`, so no caller changes behaviour.

**`glob` gains `case_mode`** as its own task (decision 10): the protocol, both backends, and a per-dialect prefilter (SQLite's `LIKE` is ASCII-insensitive; Postgres needs `lower()`, which skips the btree; SQL Server and MariaDB follow collation), with all five engine legs and a scale review. `find -iname` does not wait for it.

## 5. Slice C — the pipeline runner (`shell/run.py`)

- **ADR 083 as amended.** One task per stage. `asyncio.Queue(maxsize=QUEUE_DEPTH)` between stages. `ROWS_PER_CHUNK` 1,000, `BYTES_PER_CHUNK` 64 KiB and `QUEUE_DEPTH` 2 are declared constants. A verb returns a whole `Result` and the producer slices it, so memory is bounded per seam (`QUEUE_DEPTH × chunk`), not per stage. A stage's docstring says when it materializes.
- **Every seam in this spec is rows → bytes or bytes → bytes** (decision 1). No program in this spec consumes rows from a pipe. The rows → rows pass (ADR 083 pin 3) needs an explicit form (`xargs`, spec 168).
- **The plain projection** (decision 8) is what crosses a seam, fills a `$( )`, lands in a redirection, and becomes `cli` stdout. It is bash's text, made by the producing program's own renderer, never `render_result`:
  - A `read` row crosses as its body, verbatim. Text crosses as `content.encode()`. A bytes-sourced row crosses as `data` (the producer projects `data` when its consumer is byte-shaped, ADR 083 pin 7). No header, no separator, no added newline. `cat` emits one chunk per operand, in operand order.
  - Any other row crosses as one line per row, each ending in `\n`, with the path as typed (§4).
  - An empty result crosses as zero bytes.
  - A bytes-sourced row inside a multi-row text render prints the placeholder.
- **Errors.** A stage's classified errors render to its stderr as `<program>: <error line>` and never into the pipe. A failed verb with zero rows yields zero bytes downstream and a non-zero status.
- **Early close.** A consumer that stops (`head -3`) closes its stdin. The producer is cancelled at its next emit and reports `vfs.cancelled` at info severity, which is not a failure.
- **Redirections.** `>` and `>>` into a path are a `write` of the stage's plain bytes (`>>` is a `read` then a `write` in this spec, with no version precondition, so concurrent appends can lose data; the docstring says so). `<` from a path is a `read` whose body feeds the first stage as bytes. `2>&1` merges the stage's stderr lines into its stdout as bytes. `n>&m` works on the two streams only. A redirected stage writes nothing to stdout.
- **Here-documents** feed stdin as bytes after the quoted-delimiter rule.
- **`$( )`** runs the inner list and substitutes its plain stdout with trailing newlines stripped. Non-UTF-8 bytes decode lossily and NUL is dropped, as bash drops it.
- **Expansion** (amends ADR 081 pin 4):
  - Brace expansion is textual, first in POSIX order, in the shell (`{a,b}`, `{1..3}`, `{01..10}`), bounded by `ITERATION_BUDGET`.
  - Tilde: `~` and `~/` expand to `$HOME`.
  - Pathname expansion runs only on a word holding an unquoted `* ? [`. The shell anchors the word at `cwd` (`<cwd>/<word>`), so glob's leaf-name rule never applies. A name beginning `.` matches only a component beginning `.`. A word matching nothing stays literal (POSIX). Matches sort by path and print as typed.
  - Every path-shaped operand resolves against `cwd` in the shell before `Fs`.
- **State scope.** `cd`, `export`, `unset` and bare assignments change the call's state only in its top-level list. Inside a pipeline of two or more stages, or a `( )` subshell, they change a copy (bash runs those in subshells). `set -e` is per call and scopes to a subshell.
- **Status.** `$?` is POSIX's: the rightmost stage of the last pipeline. `set -e` follows ADR 081 pin 6.
- **Budgets** (ADR 084 pin 5):
  - `STAGE_BUDGET` (64 stages in one pipeline) and `ARGV_BYTE_BUDGET` refuse `invalid` before anything runs.
  - `FANOUT_BUDGET` truncates with the `budget_exhausted.truncated` warning. `glob` passes `max_count=FANOUT_BUDGET + 1`. `ls`, `tree` and `grep` (whose `max_count` is per file) truncate after the verb returns, and the verb's own memory profile stands.
  - `STDOUT_BYTE_BUDGET` and `STDERR_BYTE_BUDGET` (4 MiB each per stage) truncate with the warning.
  - `WALL_TIME_BUDGET` is one deadline across the line, checked before each verb call and at each emit. A verb in flight runs to completion. An expiry classifies `vfs.timeout`, exit 124, and keeps what was already emitted. Tests drive the deadline through an injectable clock, never a real one.

## 6. Slice C — the `cli` Result and its display

- **`ops == ("cli",)`.**
- **`observations` is stdout in structured form.** (a) When exactly one statement wrote stdout and its last stage produced rows, these are those rows, with absolute paths. (b) Otherwise it is one row at `/.vfs/run/<call-id>/stdout`, holding all statements' stdout in order: `content` when the bytes are UTF-8 without NUL, else `data` with a sniffed mime. Statements that wrote nothing contribute nothing. `<call-id>` is a per-session counter for `Session.cli` and a per-router counter for `VirtualFileSystem.cli`. The row cannot be read back in this spec (the `/.vfs/run` view is spec 169).
- **`errors`** holds every classified fact any stage raised, at its own severity, in arrival order, with no duplicates (decision 6). A program's own non-zero exit adds nothing.
- **`success`** is the envelope's derived verdict. So `isError = not result.success` (ADR 085 pin 9). `grep zzz f` and `false` succeed, with `exit_code` 1. `cat /nope` fails. `ls /nope | wc -l` fails, with `exit_code` 0.
- **Extras:**
  - `exit_code: int` (`$?`);
  - `statuses: list[list[int]]` (one list per pipeline, in execution order: `[[1, 0]]` for `ls /nope | wc -l`);
  - `set_e_tripped: tuple[int, int] | None` (pipeline index, stage index);
  - `stdout: str | None` (the plain text of case (a), which the display prints; absent in case (b), where the row is the stdout);
  - `stderr: str` (the stderr lines in arrival order).
- **The display projection** (decision 8) is `render_result` for the `cli` op, and the only text the `cli` boundary shows. It prints stdout (the `stdout` extra, or the row's text, or the placeholder for a non-text row), then the stderr lines. It applies `RENDER_CHARACTER_BUDGET` (32,768). When the cap bites, stdout is cut first, at a line boundary, with the slice A marker, and stderr is kept whole up to 4,096 characters. It adds nothing else: no empty marker, no slash, no table (decision 2). Classified errors appear once, as their stderr lines. An empty display is the empty string; a host adapter may print `(no output)` in its place.
- **The pipe is never capped.** The cap exists only in the display.

## 7. Slice C — the session and the entry points (amends spec 148)

- **`VirtualFileSystem.cli(command: str | Sequence[str], *, authority: Authority, workdir: str = "/") -> Result`.** `authority` is required. Every call starts fresh: `cwd = workdir`, the default env, no history (decision 4). This is the wire's shape (spec 171).
- **`Session.cli(command | argv, *, workdir: str | None = None) -> Result`.** The in-process `Session` keeps `cwd: Path` (default `/`), `env: dict[str, str]` with an `exported: set[str]`, `last_status` (`$?` and `$status`), and `history` across calls, for Python hosts. `workdir` overrides `cwd` for one call.
- **The argv form** bypasses parsing (ADR 082 pin 12): no expansion, no redirection.
- **The system actor.** Both entry points refuse `invalid` when `self._admitted(authority).is_system` (a default-system router cannot run a command as system by omission). `Fs` curries that admitted authority.
- **The default env.** `HOME=/`, `PWD=<cwd>`, `USER=<actor name>`, nothing else. `cd` maintains `PWD` and `OLDPWD`. `$PATH` is the session's search order for spec 169; there is no separate `Session.path`.
- **Concurrency.** `Session.cli` calls serialize per session (one `asyncio.Lock`). A call snapshots `cwd` and `env` at start and writes them back at end, whatever its status. Closing the session cancels a running call at its next emit.
- **History.** One entry per call: `(command, exit_code, surfaced)`, where `surfaced` is at most `HISTORY_PATHS_PER_ENTRY` (256) paths. The ring holds `HISTORY_ENTRIES` (1,000) entries. Spec 148's leak notice reads `surfaced`; the `history` builtin prints `command` and `exit_code`.
- **None of these fields changes a right.** Rights are re-derived per call. Shell state is mutable and grants nothing; spec 148's copy-on-write rule governs the narrowing only. Child sessions are spec 148's; this spec adds no `child()`.
- **The drift test.** `cli` stays out of `Op`. `VirtualFileSystem.cli` joins `MANAGEMENT_METHODS` in `test_ops.py`, and `bound` is synchronous. `cli` has no `PARAMS` row; its refusals are minted in `shell/`.

## 8. Slice E — the coverage harness (`tests/support/shell/`)

- A generator that synthesizes a replay corpus from the recorded `(command, flag, construct)` distribution of `experiments/e2/commands.md` over a fixture mount (source files, markdown, JSON, a PDF, an image), because the corpus records no arguments.
- Four rates on calls, reported in total and in scope, counts only:
  - parse: the line parses;
  - resolve: every name resolves, with the refusal rate beside it;
  - flag: every form is supported;
  - run: the exit status equals the oracle's, and the stdout bytes equal the oracle's.
- **The oracle.** A script under `tests/support/shell/` runs the text-program forms under bash 5.2 and GNU coreutils 9.x in a named, pinned container image, and commits the outputs as fixtures. Tests read the fixtures only and never run bash (just-bash's locked fixtures). macOS's `/bin/bash` 3.2 and the BSD tools are not the oracle.
- The Oils spec suite at a pinned commit becomes a second yardstick after ADR 081's slice 2 (decision 11). At v1 most of its cases are refused constructs by design.

## Scope

In: everything above. Out: text kernels in Rust (168); `xargs` and the explicit rows form (168); `/.vfs/bin`, `/.vfs/run` and the other views, installed programs, the wasm host (169); tools and MCP mounts (170); the MCP adapter and `serve()` (171); guests (172); control flow, functions, arithmetic (ADR 081's later slices); `&`, jobs, `/.vfs/jobs`; `set -o pipefail` as a mode (the status list covers it); `test -w`.

## Acceptance criteria

Counts, never clocks. Each is tagged with its slice.

1. **(A)** `run` is gone from `Op`, `VERB_RUNGS`, `PARAMS`, the router, the session, the protocol, `storage/__init__` and the README. `SupportsRun` does not exist. The drift tests pass.
2. **(A)** A bytes row renders the placeholder byte-for-byte in `_render_read`, `_render_block` and a table cell. No `to_str()` output contains base64 or a bytes `repr`. `to_payload()` carries no bytes and no `"data"` in a populated mask; `to_payload(include_bytes =True)` round-trips.
3. **(A)** `to_str(budget=N)` cuts at a line boundary with the marker and keeps the errors section. `to_str()` is unbounded. Spec 155's criteria hold for the verb tools.
4. **(B)** Every parse-level spec test passes. The weighted 100-command corpus of study 01 parses 86 of 100 (`time` admitted). The 14 refusals carry `vfs.unsupported.construct` with line, column and construct. Each parser budget classifies `vfs.budget_exhausted` on a counted input.
5. **(C)** `ls /d | wc -l` counts entries. `cat f | wc` equals the oracle's bytes. `cat f > g` leaves `g` with `f`'s `content_hash`. `ls /nope | wc -l` prints `0`, with `statuses == [[1, 0]]`, `exit_code == 0`, `success is False`, and the `not_found` in `errors`.
6. **(C)** `ls /src | grep auth` prints the names containing `auth`. `glob '**/*.py' | grep x` filters paths. No verb receives `observations=` from a pipe (spied: zero calls).
7. **(C)** A 10,000-file `ls | wc -l` prints `10000` in 10 chunks, at a maximum queue depth of 2 (counted).
8. **(C)** `cat img.png | wc -l` prints the count of `\n` bytes in the file. `cat img.png | wc -c` prints `size_bytes`. `cat a.png > b.png` leaves equal `content_hash`es. `cat report.pdf | grep total` searches the raw bytes. With the `pdf` extra and after `reindex`, `cat --rendered report.pdf | grep total` searches the rendering. `cat img.png` alone displays exactly one placeholder line.
9. **(C)** A refused construct after a mutation (`write x; for …`) runs nothing: zero `write` calls (spied), and the file is absent.
10. **(C)** The `cli` display equals bash. An empty `ls` displays `""`. `mkdir /x` displays `""`, and `mkdir -v /x` displays the line. `cd /src && ls` prints basenames. A second `VirtualFileSystem.cli` call starts at `/`. `Session.cli` keeps `cwd` across calls.
11. **(C)** Every `Fs` call reaches a public router method whose `authority` is the admitted authority (spied: N calls, N matches). `vfs.shell` imports nothing from `vfs.storage` (an import-graph test). Two sessions with different authorities see different things through `cli`.
12. **(C)** `cli` is `invalid` under `Authority.system()` passed explicitly, and on a default-system router with no authority. `sweep` and `posture` are `unrecognized`; `curl` is `unsupported` with the network hint. A 65-stage pipeline is `invalid`. A relative path reaching `Fs` is `vfs.internal`.
13. **(C)** The display caps at 32,768 characters with the marker and keeps stderr. `cat big.log | tail -1` prints the last line (the pipe is never capped).
14. **(C)** `grep zzz f` succeeds with `exit_code == 1`. `false` succeeds with `exit_code == 1`. `cat /nope` fails.
15. **(C)** One stdout spec test exists per area (`quoting`, `expansion`, `redirect`, `heredoc`, `pipeline`, `lists`, `errors`), each asserting stdout and status against the oracle fixtures. These cover `>>` on an absent file, a quoted-delimiter here-document, `$( )` with trailing newlines, `2>&1 | tail`, a `truncated` warning, and a `vfs.timeout` with its emitted rows kept.
16. **(D)** Every row of §4.1 has a test against the oracle. `copy`/`move(overwrite=)` and `glob(case_mode=)` pass on all five engine legs.
17. **(D)** `set -e` stops at the first failing statement, and every POSIX exemption in `tests/shell/spec/set-e` holds (pinned against brush's and Oils' cases by hand, never copied).
18. **(D)** Each never-class name returns its kind, its exit code and its hint.
19. **(E)** The harness reports the four rates. The in-scope run rate is at least 85% on the synthesized corpus.
20. **(all)** `scripts/ci.sh` is green at 100% coverage after every task. The four engine legs are green before C and D land.

## ADR amendments this spec needs

- **081 pin 2 and pin 8:** `time` is admitted as a keyword before a pipeline (`time [-p]`). It leaves pin 8's refused list.
- **081 pin 4:** brace expansion is textual and runs first in the shell. Only pathname expansion goes to `glob`, anchored at `cwd`.
- **081 pin 11:** `test` and `[` land in slice 1 as programs.
- **082 pin 2:** `Fs` takes absolute paths only. It is a type boundary for the sandboxed kinds and a discipline for Python builtins.
- **082 pin 10:** `source`, `.` and `alias` are not builtins; they are `unrecognized` (081 pin 8). `exit` stays.
- **082 pin 12:** `SupportsRun` is deleted. Spec 170 defines the storage-executed kind's capability.
- **083 pin 2:** verb builtins produce rows. One that reads stdin consumes bytes. A program's shapes may depend on its flags (`shapes(args)`).
- **083 pin 3:** rows pass to a rows consumer only through an explicit form (`xargs`, or `observations=` in the Python API), never on a plain pipe.
- **083 pin 4:** rows become bytes through the producing program's own renderer, which prints bash's text with paths as typed. A `read` row crosses as its body verbatim, with no added newline. A bytes-sourced `read` row crosses raw.
- **083 pin 6:** the terminal is the `cli` Result of spec 167 §6 (rows in case (a), one `/.vfs/run` row in case (b)).
- **084 pin 3:** the system-actor refusal checks the admitted authority, including the router's default.
- **085 pin 2:** the placeholder appears in `render_result` for verb tools, in multi-row plain renders and at the `cli` display. A single bytes-bodied read crosses a pipe raw.
- **085 pin 3:** the cap is an opt-in `budget` on `render_result`; the `cli` display and the MCP adapter pass 32,768. A pipe is never capped.
- **085 pin 9:** on the `cli` surface, the text is stdout then stderr, as bash prints them. "Errors lead" applies to the verb tools. A program's non-zero exit is not an error.
- **085 pin 10:** the flag is `include_bytes=False` by default.

## Landing notes

(Filled in on landing, per slice.)

## Rebase notes of 2026-10-24 (ADR 087 and specs 174–181)

ADR 087 (the kernel and its promises, proposed 2026-10-24) and the eight specs cut from it touch this spec in the places below. Each note names the spec that owns the change; nothing here is built yet.

- **`>>` is one guarded call (174).** The Redirections section's read-then-write, which this spec admitted could lose a concurrent append, becomes `write(data=…, append=True)`: the read and the write run inside one storage transaction at the `add` rung. `touch` becomes `write("", if_absent=True)`, which also closes the gap where a `stat` then a `write` could empty a file a rival had just created. The regex `sed -i` form passes `if_version=` from its read (174, 181).
- **`overwrite=` on `copy` and `move` (task zero / decision 7).** ADR 087 pin 3 names the flag `replace=`; the name is an open marker in spec 181. Pin 17 (a lean, pending Clay) settles the identity question this task left open: on a replace the destination keeps its `entry_id` and history, the source is tombstoned, edges follow the source into the trash, and a directory over a directory is refused `exists` (181). The task adds its own rows to the replay table, and `copy(replace=True)` is key-only unless 174's `unchanged` covers it (177). The flag declares the `transfer_replace` feature at the seam (179).
- **`head` and `tail` with a file operand read through `read(range=)` (178):** `-c` directly, `-n` by doubling windows. §4.1 gains four rows.
- **Listings page (176).** `ls`, `tree` and `glob` page at `ROWS_PER_CHUNK`, the same constant as `LISTING_PAGE`, emitting one chunk per page; the programs gain `--after` and `--limit`; `glob` drains by pages instead of `max_count`.
- **Integrity at the terminal (175).** `cat` of a damaged file prints the bash EIO line and exits 1. `cli` answers `scrub`, like `sweep`, as `unrecognized`; a new `in_doubt` kind (177) falls under the `unavailable` exit code.
- **The history verb is `versions` (180),** so the shell's bash `history` builtin keeps its meaning.
- **`ls -l` prints a real `owner_id` (181);** today the column is silently dropped.
- **`SupportsRun` leaves with whichever of this spec and 179 lands first (179).**
