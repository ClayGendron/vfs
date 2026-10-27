# Review of spec 167 — the shell pipeline core, before build

Reviewer: pre-build review, 2026-10-15. Tree at `main` (`ac5c515`), working tree as found; nothing under `src/`, `tests/` or the spec was modified.

**What I read.** Spec 167 (`spec.md`, `tasks.md`); ADRs 081, 083, 084, 085, 082; the memo `2026-10-15-the-agent-shell-prior-art-and-experiments.md` §1–§5, §8, §9, §12 (and §14–§15 for sequencing); studies 01, 03, 06, 07, 09 (03 and 07 in full where the spec leans on them); the executed references `experiments/s3/abi_demo.py` and `experiments/s7/shell_session.py`; spec 155 §1–§5 (folded into 167 §5) and spec 148 with its amendment; ADR 063. Live tree: `ops.py`, `base.py` (the verbs, `_gate_params`, `_gate_entry`, `_route_single`, `_dispatch_entry`, `_admitted`, `run`), `session.py`, `params.py`, `results/{envelope,render,projection,kinds}.py`, `models/entry.py`, `storage/protocol.py`, `paths.py`, `pattern_matching/{glob,grep}.py`, `tests/base/test_gates.py`, `tests/test_ops.py`, `README.md`.

**Evidence labels.** **EXECUTED**: a script ran against the live tree; scripts and outputs are in `experiments/r167/`. **READ**: a file read, cited `file:line`. **INFERRED**: my reasoning from the two.

**Scripts.** `experiments/r167/live_tree_probe.py` → `live_tree_probe.out` (sections 1–12 plus two appended one-liners); `experiments/r167/seam_probe.py` → `seam_probe.out` (drives the s3 reference's own law and runner); `experiments/r167/corpus_pin8_scan.out` (study 01's 86 admitted commands scanned for pin-8 constructs the study's regex did not test).

## Verdict

The spec is not ready to build. The direction is right. The parser, the two pipe shapes and the "the funnel is the only gate" stance are all sound. But four things a developer must decide on day one are either undefined or wrong as written.

First, one function is asked to do two jobs. `render_result` is the text that crosses a pipe (ADR 083 pin 4), and it is also the text the agent reads at the end (the cap, the empty markers, the slash). Both jobs in one place put the truncation marker into `tail` and `(empty directory)` into `wc -l`.

Second, the executed reference adds a newline to every file body that crosses a pipe, so `cat f | wc` is off by one. The memo reports "`cat f | wc -l` counts lines". It never compared the count with bash.

Third, rows into `grep` search the files' contents. In bash, `ls | grep auth` filters names. This is the single most common agent idiom, and it gives a different answer.

Fourth, nothing defines the `cli` `Result` for a list (`cd x && ls; cat f`), or its verdict. A naive merge drops rows, and it renders `cat`'s output as a path.

On top of that, the flag-to-parameter mapping a developer needs for `cp`, `mv`, `mkdir -p`, `rm`, `sed -i`, `grep -c/-L/-o`, `find` and `ls -a` is missing. In several of these the live verb answers differently from bash (EXECUTED). The slice is also four landings, not one.

One line: right design, but rewrite the seam/display split, the cat law, grep-on-stdin and the list `Result` before anyone writes `shell/run.py`.

## Readiness score: 48 / 100

| # | Dimension | Weight | Score | Why |
|---|---|---:|---:|---|
| 1 | Every behaviour precise enough to test | 15 | 7 | Programs are listed by flag; their outputs, verb calls and edge cases are not (findings 4, 7, 15) |
| 2 | Consistent with the ADRs it implements | 15 | 8 | `time`, `curl`, `[`, `source`/`exit`, stderr order, brace expansion, native semantics vs pin 3 (findings 3, 8, 12) |
| 3 | Consistent with the live tree | 15 | 7 | Task zero is mostly right but misses sites and costs (findings 1, 11, 13) |
| 4 | Internally consistent | 10 | 6 | `glob` used in a criterion but not a program; `find -iname` is in 167 but "needed by 168"; the git hint points at a command the shell lacks |
| 5 | Nothing left for the developer to invent | 15 | 5 | The list `Result`, the verdict, flag-chosen output forms, HOME, path printing, the mapping table (findings 4, 5, 7, 9) |
| 6 | Bounded at scale, honest about profile | 10 | 6 | The seam is bounded. `ls` fan-out, stderr and in-flight cancellation are not (finding 17) |
| 7 | Acceptance criteria countable, never clocks | 10 | 6 | No clocks. But criterion 7 is not countable as written, criterion 11's "run rate" is undefined, and the oracle environment is unpinned (finding 18) |
| 8 | Sized for one landing, sequenced green | 10 | 3 | Parser, runner, about sixty programs, session, renderer, `run` removal, harness and docs; spec tests sequenced before `echo` exists (finding 6) |

## Findings, most severe first

### 1. The pipe text and the agent's text are one function: the cap and the empty markers land in the pipe — **blocking**

- **Spec lines.** §1 item 2: the cap is "applied last in `render_result`". §5: `(empty directory)`, `(no matches)`, the trailing `/`. ADR 083 pin 4: rows become bytes "through the one chokepoint `render_result`".
- **Problem.** The same call renders a pipe seam, a `$( )` substitution, a `>` redirection target and the final display. Take each decoration in turn.
  - The cap. A 78,000-character `cat big.log | tail -1` would print the marker, not the last line.
  - The empty marker. `ls /void | wc -l` would print 1, not 0.
  - The slash. `$(ls)` and `ls > out.txt` would carry `dir/`.
- **Evidence.** EXECUTED `seam_probe.out` §C: `big.log` renders to 78,000 characters, and bash `tail -1` gives the last row. §D: `ls /void` crosses `b''` today, so `wc -l` gives 0. READ spec 155 §1: its budget was an opt-in `budget=None` parameter, and "a future host boundary picks its own budget". 167 dropped that shape. READ study 09 §F4: bash-tool caps "after exec, in the tool", which is the terminal only.
- **Amendment (spec §1 item 2 and §5).** Replace with:
  > "The renderer has two projections. The **byte projection** is `render_result(result, projection=…)` exactly as today, plus the placeholder of ADR 085 pin 2. It is what crosses a seam, feeds `$( )` and lands in a redirection. It adds no marker, no slash, no cap and no stderr. The **display projection** is `render_display(result, *, budget=RENDER_CHARACTER_BUDGET)`, used only at the `cli` boundary, by `Result.to_str()` and by the MCP adapter. It is the byte projection plus the empty markers, the directory slash, the collapsed errors, the stderr lines and the cap (32,768 characters), applied last, cut at a line boundary, with one marker `[output truncated: N characters removed, R rows remaining; page with head, tail or sed -n]`. The cap never cuts the errors section."

  Add a test: `cat big.log | tail -1` prints the last line; `ls /empty | wc -l` prints `0`.

### 2. The rows-to-bytes law adds a newline to every body, and a multi-row read renders headers — **blocking**

- **Spec lines.** ADR 083 pin 4: "the rows render through … `render_result` … plus a trailing newline (… `read` the body verbatim …)". Criterion 2: "`cat f | wc -l` counts lines".
- **Evidence.**
  - EXECUTED `seam_probe.out` §A, through the s3 reference's own `rows_to_bytes`:
    - `line one\nline two\n` (18 bytes) crosses as 19 bytes.
    - `no newline` (10 bytes) crosses as 11 bytes.
  - §B: the s3 runner prints `3 4 19` for `cat f | wc`, where bash prints `2 4 18`. The memo's scenario B printed `3 5 35` for a 2-line, 34-byte file, and the memo reported it as correct.
  - EXECUTED `live_tree_probe.out` §3: a two-row `read` renders `'==> /d/a.txt <==\na\n\n\n==> /d/b.txt <==\nb\n'`, so headers and blank lines would enter the pipe.
- **Scenario.** `cat a.txt > b.txt` grows the file by one byte on every copy. `cat a b | wc -l` counts headers.
- **Amendment (spec §4, new bullet, and a note to amend ADR 083 pin 4).**
  > "A `read` row crosses a byte seam as its body, verbatim. Text crosses as `content.encode()` and bytes as `data`. No header is added, no separator, and no newline. `cat` emits one chunk per operand, in operand order. Every other op crosses as its byte projection with each row's line ending in `\n`. An empty result crosses as zero bytes."

  Add tests: `cat f | wc -c` equals `size_bytes` for a text file; `cat a b | wc -l` equals the sum of the line counts.

### 3. `ls | grep auth` searches file contents; bash filters names — **blocking (product question 1)**

- **Spec lines.** ADR 083 pin 3: rows into a rows consumer pass as `observations=`. Criterion 2: "`glob '**/*.py' | grep x` passes rows as `observations=`". The Intent says "gets what bash would print". ADR 082 pin 5 says "native semantics".
- **Evidence.** EXECUTED `live_tree_probe.out` §6: `ls /src | grep auth`, run rows to rows, returns `/src/db.py:1:token = auth()` and `/src/db.py:2:auth again`. Bash prints `auth.py`. READ memo §2: `grep` is 20.9% of segments and pipes are in 74% of calls. Filtering a listing is the common case. It also flips with redirection. `ls /x 2>&1 | grep foo` makes stdout bytes (spec §4, `2>&1` merges as bytes), so that same `grep` becomes a line filter. The same text gives two meanings.
- **Amendment (spec §3, the `grep`/`rg` bullet).**
  > "`grep` and `rg` with no file operand read stdin as text: rows from the upstream stage cross by the byte projection (finding 1), so `ls | grep x` filters names and `cat f | grep x` filters the body's lines. Matching uses the same verifier as the verb (`compile_verifier`). Output for stdin input carries no file name unless `-H`. Searching the contents of a listed set is `xargs grep` (spec 168) or `grep -r x $(…)`."

  Then strike the `observations=` half of criterion 2, or move it to a vfs-only form if Clay wants it (question 1).

### 4. A program's output form depends on its flags, but `produces` is static and the terminal renders by op — **blocking**

- **Spec lines.** §3: `Program` declares `consumes`/`produces` once. ADR 083 pin 2: "Verb builtins are rows to rows". §3 lists `cat -n`, `ls -l -1 -F`, `grep -c -l -L -o -h -H`, `stat -c`, `find -print0`.
- **Evidence.**
  - EXECUTED `live_tree_probe.out` §7: `grep(output_mode="count")` renders `/e/one.txt` alone. The count rides in `score` (populated), not in the text. Bash `grep -c` prints `/e/one.txt:4`.
  - READ `render.py:177-201`: one arrangement per op, chosen by `result.op`.
  - READ `projection.py:49-59`: one default projection per op.
  - INFERRED: `grep foo f` (no `-n`) in bash prints `text`, while the op default prints `path:N:text`. `cat -n` is numbered text, not a row.
  - ADR 083 pin 7 needs every stage's shapes before the line runs, to plan the `data` projection.
- **Amendment (spec §3, the `Program` bullet).**
  > "A program declares `shapes(args) -> (consumes, produces)`, evaluated after the forms parse and before the line runs. A verb builtin produces rows only when its flags select the op's default byte projection (`grep -rn`/`-Hn`, `ls`, `ls -1`, `cat`, `find -print`, `glob`, `stat`). Any other text form (`grep -c -l -L -o -h`, `ls -l -F`, `cat -n -b`, `stat -c`, `find -print0`) produces bytes rendered by the program's own renderer, one per name (ADR 082 pin 5: two renderers for `grep`/`rg`). At the terminal, a bytes production is the one `/.vfs/run/<call-id>/stdout` row."

  Add one test per text form against the bash oracle.

### 5. The `cli` Result is undefined for lists, and its verdict is contradicted between ADR 085 and study 03 — **blocking (product question 2)**

- **Spec lines.** Intent: "The call is one `Result`". §4: extras `exit_code`, `statuses` "(the list)", `stderr`, `set_e_tripped` "(the stage index or `None`)". §1 item 1: `"cli": ("content",)`.
- **Evidence.**
  - EXECUTED `live_tree_probe.out` §11:
    - `Result.merge` of two terminal rows at the same `/.vfs/run/1/stdout` keeps one row (`['first\n']`). `cat f; cat f` merges to one row.
    - Merging an `ls` result with a `read` result gives `op=None`, so the `read` body renders as its path (the path-list fallback, `render.py:201`).
  - READ `envelope.py:557-587`: `merge` builds the result without `model_extra`, so `exit_code` would be lost.
  - READ ADR 085 pin 9: `isError = not result.success`. READ study 03, the exit-code table: "`isError = ($? != 0)`".
  - In this case the two rules disagree: `grep x f` with no match exits 1 and has no error, and so do `false` and `test -f nope`.
  - The demo puts a stage's errors both on the `Rows` chunk and in stderr (`abi_demo.py:219-220`). A last-stage error would render twice.
- **Amendment (spec §4, new "The call's Result" bullet).**
  > "The `cli` Result is built at the call's end. (a) Statements whose stdout is empty contribute nothing (`cd`, `export`, a redirected stage, a silent mutation). (b) When exactly one statement wrote stdout and its last stage is row-shaped, the Result is that stage's rows with its op. (c) Otherwise every statement's stdout, as byte projections in order, concatenates into one row at `/.vfs/run/<call-id>/stdout` with op `cli`. `_render_body` routes `cli` to `_render_read`'s verbatim arrangement. `Result.errors` carries every classified error any stage raised, at warning severity. When `$? != 0`, the first fatal fact of the stage that set `$?` keeps error severity. Classified errors never also appear in `stderr`; `stderr` holds only program-written text. `statuses` is a list per pipeline, in execution order (`[[1, 0]]` for `ls /nope | wc -l`). `set_e_tripped` is `(pipeline_index, stage_index)` or `None`. `<call-id>` is a per-session counter, or per router call for `VirtualFileSystem.cli`."

  One case is left open by question 2: a non-zero `$?` with no classified fact (`false`, `grep` with no match). Under "`success` is `$? == 0`", that case needs a fatal entry of its own. The proposal is a new `vfs.exit_status` child of an existing family, carrying `exit_code`. Under ADR 085's rule, it adds nothing, and `exit_code` rides only in extras.

  The verdict rule depends on question 2. Write one sentence either way: "`success` is `$? == 0`" or "`success` is ADR 085's derived verdict, and `$?` is advisory".

### 6. The slice is four landings, and the tasks are sequenced against their own tests — **blocking (sizing)**

- **Spec lines.** `tasks.md`: task 2 lands the spec-test files `quoting`, `expansion`, …, in the "OSH shape (script in, expected stdout and status out)". Task 4 is the runner. Task 7 brings `echo`.
- **Problem.** A spec test that asserts stdout needs the runner and `echo`/`printf`, so tasks 2–6 cannot be green at 100% coverage as ordered. The scope is a new package of about 60 programs with forms tables, a parser, a runner, session state, a renderer split, a verb removal across about 15 files, a coverage harness and docs. The 165 precedent split a smaller change into three slices.
- **Amendment (`tasks.md`).** Split into:
  - **167-A**: task zero only (findings 11, 13, 19), the display/byte split (finding 1), and `run` out. Independent and small.
  - **167-B**: kinds, the lexer and parser, parse-level spec tests (AST and refusal shape, no stdout), the caret renderer.
  - **167-C**: ABI, `Fs`, runner, the `cli` Result (finding 5), session fields, `Session.cli`/`VirtualFileSystem.cli`, and the minimal program set criteria 2–9 need: `cat ls glob grep head tail wc echo printf true false cd pwd export`, redirections and here-documents. Then the stdout spec tests.
  - **167-D**: the remaining tier-1 forms with the mapping table (finding 7), the never table, the `set -e` file.
  - **167-E**: the coverage harness, oracle fixtures and docs.

  `glob(case_mode=)` goes with D, under its own scale review (finding 11).

### 7. The flag-to-verb mapping is missing, and the live verbs answer differently from bash in many places — **should fix**

- **Spec lines.** §3 lists flags only.
- **Evidence.** All EXECUTED, `live_tree_probe.out`. Each item gives the live answer, then the bash answer.
  - §8, `cp a b` with `b` present: live `exists`; bash overwrites.
  - §8, `mv` the same way: live `exists`; bash overwrites.
  - §8, `cp a dir/`: live `exists` at `/empty`; bash copies into the directory.
  - §8, `cp dir dir2` without `-r`: live succeeds; bash refuses.
  - §10, `mkdir -p existing`: live `exists`; bash succeeds silently.
  - §10, `rm -f /nope`: live `not_found`; bash exits 0 silently.
  - §9, `sed -i 's/one/ONE/'` through `edit`: live `invalid` "Found 4 matches"; sed replaces the first match on each line.
  - §5, `ls` shows `.hidden.py`; bash hides dotfiles without `-a`.
  - READ `base.py:1326-1346`: `grep` has no parameter for `-L`, `-o`, or several `-e` patterns with `-F`.
  - READ `base.py:905`: `ls` has no sort or long-format parameters.
- **Amendment.** Add a §3.1 table "Each form, its verb call, its divergence". At minimum:

  | form | call | rule |
  |---|---|---|
  | `ls [-a\|-A] P` | `ls(P)` | drop names beginning `.` unless `-a`/`-A` |
  | `ls -l` | `ls(P, columns={kind, size_bytes, updated_at, owner_id, version})` | columns named in order, never mode bits |
  | `ls -t -S -r` | `ls(P, columns=…)` | sorted in the shell |
  | `ls -d P` | `stat(P)` | |
  | `ls -R P` | `tree(P)` | rendered as bash's sections |
  | `mkdir -p` | `mkdir(P, parents=True, exist_ok=True)` | |
  | `rm P` | `stat` first; a directory without `-r` is `wrong_kind`, exit 1 | |
  | `rm -r` | `delete(P, cascade=True)` | |
  | `rm -f` | | `not_found` swallowed, exit 0, no stderr |
  | `cp S D`, `mv S D` | `stat(D)` first; a directory `D` means dest `D/basename(S)` | a directory `S` without `-r` refuses (cp only); an occupied dest overwrites by `delete` then `copy`/`move` (needs `read_write`, not atomic; say so), or the verb gains `overwrite=` (decide); `-n` skips, exit 0 |
  | `touch P` | absent: `write(path=P, content="")`; present: no-op | |
  | `grep` | `-i`→`case_mode="insensitive"`, `-F`→`fixed_strings`, `-w`→`word_regexp`, `-v`→`invert_match`, `-A/-B/-C`→context, `-l`→`output_mode="files"`, `-c`→`"count"`, `-m`→`max_count` (per file), `--include/--exclude`→`globs`/`globs_not`, `-r P…`→`paths` | several `-e` become `(?:p1)\|(?:p2)`, escaped under `-F`; `-L` is the scope's files minus the `-l` set; `-o` re-matches in the shell with the same verifier |
  | `grep x P` | | a directory `P` without `-r` is an "Is a directory" error, exit 2 |
  | `sed -i 's/a/b/g'` | `edit(P, old=a, new=b, replace_all=True)` for a fixed string | |
  | `sed -i 's/a/b/'` (no `g`) | `read`, then first-per-line replace, then `write` | |
  | `stat -c FMT` | `stat(P)` | `%n %s %y %F` only; others `unsupported.form` |
  | `find P expr` | candidates `glob("**", paths=(P,), columns={kind, size_bytes, updated_at})` | the predicate tree is evaluated in the shell; `FANOUT_BUDGET` truncates with the warning |
  | `glean`, `graph` | | name each flag (`--limit`, `--depth`, `--edge-type`, …) |

### 8. Pathname and brace expansion "handed to `glob` unchanged" give wrong answers — **should fix (amends ADR 081 pin 4)**

- **Evidence.**
  - EXECUTED `live_tree_probe.out` §5: `glob("*.py", paths=("/src",))` returns `/src/sub/deep.py`. A slash-free pattern matches leaves at any depth (`glob.py:6-11`); bash `*.py` in `/src` matches direct children only. `*` also matches `.hidden.py`.
  - EXECUTED (appended): `expand_pattern("/d/f{1..3}.txt")` gives `('/d/f1..3.txt',)`, so ranges are not supported.
  - INFERRED: `mkdir -p d/{x,y}` names paths that do not exist yet, so a glob finds nothing. Brace expansion must be textual.
  - READ `glob.py:39`: `MAX_PATTERN_ARMS` is 64.
- **Amendment (spec §2).**
  > "Brace expansion is textual, first in POSIX order, in the shell (`{a,b}`, `{1..3}`, `{01..10}`), bounded by `ITERATION_BUDGET`. Pathname expansion runs only on a word holding an unquoted `* ? [`. The shell anchors the word at `cwd` (`<cwd>/<word>`), so glob's leaf-name rule never applies. Names beginning `.` match only a pattern component beginning `.`. A word that matches nothing stays literal (POSIX). Matches sort by path."

### 9. Relative paths, `~` and `cd` need a HOME and a guard — **should fix**

- **Evidence.**
  - EXECUTED (appended to `live_tree_probe.out`): `resolve_path("foo/bar")` gives `/foo/bar`; `'./x'` gives `/x`; `'~/x'` gives `/~/x`. The router silently roots a relative path, so a missed resolution in any builtin addresses `/` with no error.
  - READ spec §3: `cd` with no argument, and `cd -`. ADR 081 pin 4: `~` and `~/`.
  - READ `shell_session.py`: `cd` falls back to `env.get("HOME", "/")`.
  - Nothing in the spec sets HOME, PWD or OLDPWD.
- **Amendment (spec §6).**
  > "A new session's env is `HOME=/`, `PWD=<cwd>`, `USER=<actor name>`, and nothing else. `PWD` and `OLDPWD` are maintained by `cd`. `~` expands to `$HOME`. `Fs` accepts only absolute paths: a relative path reaching `Fs` is a shell bug, classified `vfs.internal`, never routed."

### 10. The system-actor refusal must judge the admitted authority — **should fix**

- **Evidence.** EXECUTED `live_tree_probe.out` §12: on a router built with `default_authority=Authority.system()`, `write(…)` with no authority succeeds as system. READ `base.py:3065-3078` (`_admitted`). Spec §6: `VirtualFileSystem.cli(…, *, authority, cwd=None)` does not say whether `authority` may be `None`.
- **Amendment (spec §6).**
  > "`authority` is required. `cli` refuses `invalid` when `self._admitted(authority).is_system`, so a default-system router cannot run a command as system by omission. `Fs` curries the admitted authority, never `None`."

### 11. Task zero is incomplete, and two items are misdescribed — **should fix**

Checked item by item against the code.

- **Item 1 is right but not sufficient.** READ `projection.py:57`: `_DEFAULT_PROJECTION["run"]` is `("path",)`. But adding `"cli": ("content",)` alone still renders a Markdown table. EXECUTED: the s3 demo prints `| content |` for its minted row, because `_render_body` (`render.py:184-201`) has no `cli` branch. Add: "`_render_body` routes `cli` to `_render_read`".
- **Item 2 is right.** EXECUTED §2 and the appended table probe:
  - A one-row bytes `read` with `data` renders `''`.
  - A default-column read of an unrendered PNG renders only the `vfs.unavailable` warning.
  - A block or table cell renders the Python repr `b'\x89PNG\r\n'` (not base64, but still a byte leak).
  - In a multi-row read, the bytes row renders an empty body.
- **Item 3 contradicts a docstring.** READ `envelope.py:22`: "`to_payload()` / `from_payload()` round-trip losslessly". No caller in `src/` uses `to_payload` today (EXECUTED grep). Add: "the module docstring states the round trip holds under `include_bytes=True`; the default is the wire". And name the parameter: `to_payload(*, include_bytes: bool = False, …)`.
- **Item 4 misses sites.** EXECUTED grep. `run` also lives in:
  - `params.py:357` (and `tests/test_params.py:24` pins `set(PARAMS) == ALL_OPS`);
  - `storage/__init__.py:21,42`; `protocol.py:514` (`_FAMILY_OPS`); `base.py:100,3032`;
  - `README.md:19,61,99,103`;
  - tests: `test_params.py:84,157,205`, `base/test_dispatch.py:1332,1657`, `base/test_authority.py:47`, `base/test_mount_admin.py` (about 15 `deny_ops={"run"}` sites used as the example mask), `base/test_mounts.py:683-693`, `base/test_gates.py:170-200` (the capability-gate test rides on `run`), `storage/test_protocol.py:100`, `storage/test_memory.py:20`, `storage/database/test_reads.py:752`, `support/base_doubles.py:116,355,363-373`.

  Two items are misdescribed:
  - "Renamed `SupportsToolCall`" has no op to map to in `_FAMILY_OPS`, and `capabilities()` speaks ops. Delete `SupportsRun` here and let spec 170 define its own capability (CLAUDE.md: speculative generality).
  - "The drift test passes with `cli` added as the meta-verb that is routed" contradicts `test_cli_and_rm_are_not_ops` (`test_ops.py:68-72`) and ADR 081's "the `cli` rule in `ops.py` stands". Write instead: "`cli` stays out of `Op`; `VirtualFileSystem.cli` joins `MANAGEMENT_METHODS` in `test_ops.py`; it has no `PARAMS` row; its refusals are minted in `shell/`".
- **Item 5 is not cheap.** READ `database/reads.py:520-537`: glob pushes a `LIKE` prefilter on `path`/`name`. Case-insensitive matching changes it per dialect (SQLite's `LIKE` is ASCII-insensitive; Postgres needs `lower()`/`ILIKE`, which defeats the btree; MSSQL/MariaDB depend on collation). That is five engine legs and a scale review. Also, spec §3 lists `find -iname` in 167, not 168. Amend: "`-iname`/`-ipath` filter in the shell over the case-sensitive `**` candidates under the fan-out budget; `glob(case_mode=)` is its own task with the engine legs".
- **Also missing from task zero.** `test_ops.py:176-180` pins glean's default projection, which §5's rank-by-default changes. The kinds docstring's producer-exclusivity rule (`kinds.py:43-44`, "only capability gates emit `unsupported`; only dispatch emits `unrecognized`") must name the shell as a producer.

### 12. Six contradictions with the ADRs — **should fix**

| Spec says | ADR says | Evidence | Fix |
|---|---|---|---|
| §3: `time -p` is a shell builtin | 081 pin 2 reserves `time`; pin 8 refuses it | EXECUTED `corpus_pin8_scan.out`: corpus id 24 uses `time uv run pytest`, so criterion 1's "86 of 100" includes a `time` command | question 7; then amend 081 pin 8 or drop `time` from §3 and make criterion 1 "85" |
| criterion 8: `curl` is `unrecognized` with a network hint | 084 pin 9 and Consequences: `curl` is `unsupported` (a capability the kernel lacks) | READ | "the never table classifies host programs `unrecognized`, exit 127, except network programs (`curl`, `wget`), which are `unsupported`, exit 126"; or amend 084 |
| §3: `test`/`[` in slice 1 | 081 pin 11: slice 2 admits "`[ ]` as a program" | READ | amend 081 pin 11 (admitting `[` with `&&` is cheap and common) |
| §3 builtins omit `exit`, `source`, `alias` | 082 pin 10 lists `exit`, `source`, `alias` as must-be-builtins; 081 pin 8 says `source` is `unrecognized` | READ | add `exit [n]`; `source`/`.`/`alias` are `unrecognized` (081 wins); amend 082 pin 10 |
| §5: "stderr lines … render after the rows" | 085 pin 9: "On error the text block leads with the errors section" | READ | "on `$? != 0` the display leads with errors, then rows, then stderr" |
| §2 / 081 pin 4: brace expansion "handed to glob unchanged" | POSIX: brace expansion is textual | finding 8 | amend 081 pin 4 |

### 13. The caret rendering breaks the renderer's one-line error invariant — **should fix**

- **Evidence.** READ `render.py:90-122`: `_error_line` collapses newlines, "so an entry can never forge a sibling error line". Spec §5 and ADR 081 pin 9: "renders the offending line with a caret under the column".
- **Amendment (spec §5).**
  > "A `vfs.invalid.syntax` error renders its one error line as today, then a two-line block built from `data` (the source line with control characters escaped, then spaces and `^` at `vfs.column`), only in the display projection. Producer keys follow the kinds rule: decide `line`/`column` or `vfs.line`/`vfs.column` and say which (`kinds.py:45-48` says producer keys are unprefixed)."

### 14. Session state: concurrency, persistence, history, and the search path — **should fix**

- **Evidence.**
  - READ `session.py:36-50`: a `__slots__` facade, "one authority … nothing more". No `child()` or `narrow()` exists (EXECUTED grep). ADR 063 rule 1 says "copy-on-write".
  - Spec 148 §4: the `surfaced` ring holds *surfaced paths*, for leak notices. Spec 167 §6 makes `history` "also" that ring, but shell history is *command lines*. Study 07's table says the entry is `(command, status, paths surfaced)`, and the spec dropped that shape.
  - ADR 082 pin 10 and spec §6: `Session.path`. ADR 081 pin 4: `$PATH`. Two sources of the same order.
- **Amendment (spec §6).**
  > "`Session.cli` calls serialize per session (one `asyncio.Lock`); a call snapshots `cwd`/`env` at start and writes them back at end, whatever the status. `cd`, `export`, `unset` and bare assignments change session state only in the call's top-level list, never inside a pipeline of two or more stages or a `( )` subshell (bash runs those in subshells). A `history` entry is `(command, exit_code, surfaced)`, where `surfaced` is at most `HISTORY_PATHS_PER_ENTRY` paths (declare it); the ring holds `HISTORY_ENTRIES` entries (declare it). Closing a session cancels a running call at its next emit. `$PATH` is the session's search order (spec 169 reads it); there is no separate `Session.path` field in this slice. Child sessions are spec 148's; this slice adds no `child()`."

  Amend ADR 063's rule 1 wording in spec 148: "copy-on-write for narrowing; shell state is mutable and grants nothing".

### 15. Programs referenced but not in the table, and one that has no backing verb — **should fix**

- `glob` is used in criterion 2 but is not in §3's verb-builtin list. Add it.
- §3's `git` hint "points at … the trash view and `restore`", but no `restore` program exists. The same goes for `edit`, `mkedge`, `rmedge` and `grants`. Either add them under their verb names (as `glean`/`graph` are), or say they are Python-only in this slice and fix the hint. Note that ADR 082 pin 2's `Fs` has no grant verbs, so `grants` needs a sentence either way.
- `test -r`/`-w` "answer the caller's rung". No verb returns a rung (EXECUTED grep: the only `level_at` is the private `storage/grants.py:169`). Write: "`-r` is a `read(P, columns={"path"})` that succeeds; `-w` is `unsupported.form` in this slice".
- `write` as a typeable program name and "`tee`'s partner": `tee` is not in this slice. Say whether `write` is user-visible.

### 16. Exit code for a verb's `permission_denied` — **should fix**

- **Evidence.** READ `abi_demo.py:162-180`: the executed reference maps `permission_denied`, `unauthenticated` and `unsupported` from any verb to 126. READ the study 03 table: 126 is "name resolves but the caller lacks `read`/execute on it". READ ADR 084 pin 2: 126 is a program the caller can list but not read. Bash `cat` on EACCES exits 1.
- **Amendment (spec §4).**
  > "A verb's failure inside a builtin is exit 1 whatever its kind, except `timeout` 124 and `cancelled` 130. 126 and 127 are only resolution outcomes. Usage errors and `unsupported.form` are 2."

### 17. Budgets and boundedness: say how each budget bites — **should fix**

- **`FANOUT_BUDGET`.** `ls` and `tree` have no row cap (READ `base.py:905-930`). `grep`'s `max_count` caps matches per file, not rows (READ `base.py:1360-1364`). Write per verb: `glob` via `max_count=FANOUT_BUDGET+1`; `ls`/`tree`/`grep` truncate after the verb returns, and the verb's own memory profile stands (say it honestly, CLAUDE.md "never design toward a cap").
- **Chunking.** READ `abi_demo.py:190-201`: the producer holds the whole verb `Result` and slices it. ADR 083 pin 9's "memory per seam is depth × chunk" is true per seam, not per stage. Write that in §4. Criterion 3 then pins the seam, which is what it can pin.
- **stderr has no budget.** Add `STDERR_BYTE_BUDGET` (or apply `STDOUT_BYTE_BUDGET`).
- **`WALL_TIME_BUDGET`.** Write: "checked before each verb call and at each emit; a verb in flight runs to completion (a cancelled mutation mid-transaction is not a state vfs defines)".
- **`STAGE_BUDGET` "per line".** Say whether it counts stages per pipeline or across the whole command string.

### 18. Acceptance criteria to tighten — **should fix**

- **Criterion 7** ("zero rights checks in the shell layer, spied") is not countable as written. Write: "every `Fs` call reaches a public router method with `authority is session.authority` (spied: N calls, N matches), and `vfs.shell` imports nothing from `vfs.storage` (an import-graph test)".
- **Criterion 4** (`cat report.pdf | grep total`) needs the `pdf` extra and a `reindex`. EXECUTED §2: an unrendered binary's default read is a `vfs.unavailable` warning "run reindex". Say so in the criterion.
- **Criterion 11**: define "run rate". Write: "the program exits with the oracle's status and its stdout bytes equal the oracle's".
- **The §7 oracle.** "Run under the host's `/bin/bash` in CI" is unpinned. macOS `/bin/bash` is 3.2 and its `wc`/`sed`/`head` are BSD (different padding and flags). Pin "bash 5.2 with GNU coreutils 9.x in a named container image", generated by a script under `tests/support/shell/`, with the fixtures committed. Tests read fixtures only.
- **Clocks.** `sleep`, `date`, `timeout` and `time` read an injectable clock in tests (performance-test rule: never assert time).
- **Missing criteria.** `>>` on an absent file; a here-document with a quoted delimiter; `$( )` with trailing newlines; `2>&1 | tail`; a truncation warning from `FANOUT_BUDGET`; a `vfs.timeout` with emitted rows kept; the placeholder grammar byte-for-byte.

### 19. The placeholder versus a rendered binary — **should fix (product question 6)**

- **Evidence.**
  - READ ADR 085 pin 2: the placeholder is "for any row whose source is bytes, whether or not `data` was fetched". READ spec 152: a read of a PDF gives the agent its rendering as `content`.
  - EXECUTED §2: a default-column read populates `source` and `content`, but `read(columns={"data", …})` does not populate `source`.
- **Problem.** For `cat report.pdf` at the terminal, the spec does not say whether to print the rendering, the placeholder, or both. The renderer's test also needs a stated predicate.
- **Amendment.**
  > "A row is bytes-sourced when `source == "bytes"` or `data` is populated. A bytes-sourced row with `content` populated prints the placeholder line, then the rendering. One with no `content` prints the placeholder alone. `text/*` and SVG print as text."

  (Adjust per question 6.)

### 20. Regex dialects for `sed` and `grep` — **should fix**

- **Evidence.** READ `pattern_matching/grep.py:1-20`: grep's language is the regex crate's, judged by Rust `ContentMatcher`, with a gate refusing what the crate refuses. EXECUTED: `vfs._native` exports no replace kernel. Spec §3 says "Rust regex replace" in a slice that is "implemented in Python".
- **Amendment (spec §3).**
  > "`sed` addresses and `s///` patterns pass the same sre-AST gate grep uses, then compile with Python `re` in this slice. The replacement grammar is sed's (`&`, `\1`–`\9`). BRE is translated to ERE by one function shared with `grep` (`\( \) \{ \} \| \+ \?`). Spec 168 replaces the Python matcher with a Rust replace kernel, and the Python one becomes the oracle."

### 21. Nits (one list)

- `>>` as "read plus write" has no version precondition, so concurrent appends lose data. Name the race, or pass the read's version.
- ADR 082 pin 2 calls `Fs` "a type" boundary. For Python builtins it is a discipline: a builtin can reach `fs._vfs` or call `Authority.system()`. It is a real boundary only for sandboxed kinds. Say so.
- `/.vfs/run/<call-id>/stdout` cannot be read in this slice (the views are spec 169). Say that ADR 083's "kept for a later read" lands with 169.
- `Result.merge` drops extras (`envelope.py:587`); any code that merges a `cli` Result loses `exit_code`.
- "The exit-code table of ADR 082's study" means study 03; name the file.
- Glean "rank by default": adopt spec 155 §5's format (`#1`, a render-only `rank` column) by reference. As written, §5 drops the detail.
- `Session.path` "stored and unused" is speculative generality; finding 14 removes it.
- `set -e` is "per call", which bash agrees with for a fresh process. Say whether `set -e` in a `( )` subshell scopes to it.
- The `Rows` chunk is "rows plus classified errors" (ADR 083 pin 1). With finding 5, errors ride to the terminal only from the stage that set `$?`. Say what a rows-to-rows consumer does with upstream errors (drop them; they went to the call's error list).

## What the spec gets right

- A static, single-pass parse that refuses before anything runs. Criterion 5 ("a refused construct after a mutation runs nothing") is exactly the property just-bash lacks.
- Two chunk shapes, one per chunk, converted only at a seam. The executed reference ran it, and the bounded-queue numbers reproduce (EXECUTED: the s3 demo again printed 10 chunks, max depth 2).
- No command policy. The funnel's gates are the only gates. The `Fs` capability curries the authority and re-enters each public router method, so `_gate_params`, `_gate_entry` and the storage rights all fire. Nothing has to reach into `_route_single` directly: `functools.partial(vfs.read, authority=a)` is the whole mechanism (READ `base.py:879-890`).
- Removing `run`. No storage implements it; the live gate tests pin a mount that runs with no rights check (READ `test_gates.py:180-188`).
- The placeholder and the payload strip close two real leaks (EXECUTED §2: base64 in `to_payload`, and a `repr` of bytes in table cells).
- Folding spec 155 into the same landing as the cap. That is right once the display/byte split (finding 1) exists, because 155's opt-in `budget=` shape is the display half.

## Questions only Clay can answer

1. **`grep` reading stdin** (finding 3). Bash-native line filter over the upstream's text (proposed: `ls | grep x` filters names), or ADR 083's content search over upstream rows? If you want the rows behaviour too, name a vfs-only spelling for it.
2. **The verdict of a command** (finding 5). Is `success`/`isError` `$? != 0` (study 03; `grep` with no match is an error), or ADR 085's "no fatal classified fact" (`grep` with no match succeeds, exit code 1 in extras)? Proposed: `$? != 0`, because a model reads exit codes the way bash taught it.
3. **Path printing.** `ls /src` prints `auth.py` in bash and `/src/auth.py` in vfs today. Proposed: bash's rule. `ls` prints names relative to its operand; `find`, `grep -r` and `glob` print paths as the operand was spelled, so absolute operands print absolute paths and the Intent example still holds.
4. **Mutation builtins' stdout.** `mkdir`, `rm`, `cp`, `mv`, `touch` and a `>` redirection print nothing in bash; vfs action results render `Created /x`. Proposed: silent, with `-v` printing the vfs line.
5. **Spec 155's decorations on the `cli` surface.** The empty markers and the directory slash are display-only after finding 1, but they still make `ls`'s terminal text differ from bash (and `ls -F` redundant). Keep them at the `cli` terminal, or keep them only for `Result.to_str()` in Python?
6. **`cat report.pdf` at the terminal** (finding 19). Placeholder plus rendering (proposed), the placeholder alone (ADR 085 pin 2 as written), or the rendering alone?
7. **`time`** (finding 12). Admit `time` as a builtin keyword now (corpus id 24 uses it; amend ADR 081 pin 8), or refuse it and count 85 of 100?
8. **`cp`/`mv` overwrite** (finding 7). Should `copy` and `move` gain `overwrite=` (atomic, judged at `contribute` on the occupied dest), or does the shell delete and then copy (not atomic, needs `read_write`)?
9. **The §7 `[NEEDS CLARIFICATION]`.** I agree with the lean: Oils suite after slice 2. At v1 most of its cases are refused constructs, and the E2-weighted harness is the better yardstick now.
10. **The split** (finding 6). Land 167 as A–E, with A first and independent?
