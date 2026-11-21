# The roadmap's acceptance for stories F1 to F4 and F7, against the branch

The spec's done-when for steps 6 and 7 asks that the acceptance of [the roadmap](../../context/standards/roadmap.md)'s stories F1 to F4 and F7 be met or reported as not met with the reason. Each criterion below is quoted in short, then marked **met**, **in part** or **not met**, with the evidence or the reason. The state is the branch `the-shell-speaks-bash` on 2026-11-21. EXECUTED means a test or a probe ran it; READ means the code or a document was read.

## F1: the renderer gaps and the vocabulary

1. A bytes row renders as `[binary …]`, never base64. **Not met:** the renderer is out of this spec's scope; the shell's `LineResult` carries stdout as text decoded with replacement.
2. `to_payload()` carries no bytes. **Not met**, for the same reason.
3. `to_str(budget=32_768)` cuts at a line with one marker. **Not met**, for the same reason.

## F2: the parser, the whole grammar

1. The weighted corpus parses 100 of 100 (**met**, EXECUTED, `crates/vfs-shell/tests/measured_corpus.rs`); the Oils scripts' parse count is published (**not met**: the prior-art memo ran 468 Oils cases, not the suite); a refusal names its construct and reason (**in part**: it is `vfs.unsupported` with `line` and `column`, and the construct and reason are in the message, not in a `construct` field or a hint).
2. A malformed case is `vfs.invalid.syntax` with `line`, `column`, `offset`, `expected`, `incomplete`, one error, a caret. **In part:** `vfs.invalid` with `line` and `column`, one error per call (EXECUTED, `tests/shell/test_host.py::test_a_line_that_cannot_run_fails_and_changes_nothing`); no `offset`, `expected`, `incomplete` or caret on the result.
3. The four parser budgets classify `vfs.budget_exhausted` on a counted input. **Met** (EXECUTED, `crates/vfs-shell/tests/laws.rs`, the budget laws; the brace expansion is refused before it is built).
4. `cmd &` is a job, `time -p` parses, `source` of a literal path is read and parsed first. **In part:** jobs and `time -p` parse (EXECUTED); `source` of any path is refused, so a literal path is not read.

## F3: the pipe, the ABI and `cli`

1. `ls /nope | wc -l` prints `0` with `statuses`, `exit_code` and `success is False`. **Not met as written:** the result has `exit_status`, no `statuses` list, and a verb a program was refused is a warning, so the call succeeds; the shell's design keeps a program's failure out of the call's (`documentation/reference/shell.md`). The developer rules on the names.
2. A 10,000-file `ls | wc -l` in 10 chunks at queue depth 2, counted; `head -3` closes its producer, reported `vfs.cancelled`. **Not met:** pipes hold 64 KiB and the producer ends as on SIGPIPE (status 141), but neither the chunk count nor the queue depth is counted by a test.
3. Every call reaches a public verb with the admitted authority; `vfs.shell` imports nothing from `vfs.storage`; two authorities see different `ls /`. **Met** (EXECUTED, `test_every_request_reaches_a_public_verb_with_the_admitted_authority`, `test_two_authorities_see_different_listings`; READ, the import ladder in `tests/lint/test_code_shape.py`, where `vfs.shell` now imports only beneath it).
4. `cli` as the system actor is `invalid` (**met**, EXECUTED); a 65-stage line is `invalid` (**in part**: refused before it runs, classified `vfs.budget_exhausted` as the parse budget it is); `sweep` and `posture` are `vfs.unrecognized` 127 (**in part**: 127 and `command not found`, with no fact on the result); `curl` is `vfs.unsupported` 126 with the network hint (**in part**: 126 and the hint on stderr, with no fact on the result).
5. `cat img.png | wc -c` prints the size; `cat a.png > b.png` keeps the hash; `cat img.png` alone prints one placeholder. **In part:** a bytes body crosses a pipe and a redirection as its bytes (EXECUTED, `test_refusals_read_as_unix_errors` writes and reads back `\xff\xfe`); the placeholder is the renderer's (F1), not built.
6. `echo x >> f` is one `write(append=True)`; twenty concurrent lines leave twenty. **Met** (EXECUTED, `test_a_command_that_only_prints_writes_its_file_once`, and `tests/shell/test_engines.py::test_lines_that_append_at_once_lose_no_line` on SQLite; the Postgres leg runs in CI's dialect workflow and was blocked here by the image registry).
7. `Session.cli` keeps `cwd` across calls; `history` holds 1,000 entries. **Not met:** every call starts at the `cwd` it is given; no history is kept.
8. `MANAGEMENT_METHODS` lives in `ops.py` (**met**); `cli` registers in `OpGroup` as `derived` (**not met**: `cli` joins `MANAGEMENT_METHODS`, so it is no op; the developer rules on which).
9. The battery is parametrized over the engine legs. **In part:** `tests/shell/test_engines.py` runs every effect kind on SQLite and on the Postgres leg; the rest of the battery runs on memory.
10. The determinism law: keys as `(stage, ordinal)`, equal key lists over two runs, a prefix for an early close, no timestamp in a key. **In part:** a request key is the task's path and an ordinal, and two runs ask equal key lists (EXECUTED, `two_runs_of_one_line_ask_equal_key_lists`); spec 177's fingerprint and the prefix law are not built.

## F4: the program forms, `replace=`, `glob(case_mode=)`, `set -e`, the never table

1. Every row of spec 167's program forms has a test against a GNU fixture; `ls -l` prints vfs's columns. **In part:** the program tier of the corpus records GNU coreutils 9.12 for the library's 18 programs; `ls -l` is not built.
2. `move(replace=True)`. **Not met:** not built (reported in `progress.md`).
3. `glob(case_mode="insensitive")`. **Not met:** not built.
4. `set -e` stops at the first failure with its exemptions. **Met** (EXECUTED: the corpus area `errexit` holds 64 cases, none listed as failing).
5. Each never-class name returns its kind, exit code and hint; `grant`, `revoke` and `grants` have shell spellings. **In part:** `git`, `sudo`, `python3`, `python` and `perl` answer 127 with a hint; the rest answer 127 plainly; the verb spellings are `agents/2026-11-21-the-shell-serves-the-indexed-verbs/spec.md`.
6. `rm -rf /` at a bind site is `vfs.busy`, else one `delete(cascade=True)`. **In part:** `rm -r` is one `delete(cascade=True)` (EXECUTED, the spied verbs test); the bind site is not tested.
7. `trav` resolves to `traverse` before dispatch. **Not met:** not built (the indexed-verbs spec).

## F7: the language runs

1. Each control construct has a spec-test file against bash fixtures; `while read` over a pipe at counted chunks and queue depth. **In part:** the corpus areas `for`, `while`, `if`, `case`, `control` and `conditionals` hold recorded cases (EXECUTED, `scripts/shell_score.sh`); the chunk and queue counts are not counted.
2. Functions, `local`, `return`, `shift`, `getopts`, `declare`, `readonly`, `unset -f`; recursion to 256 then 137; arithmetic and `$RANDOM`. **Met**, with the cases still listed as failing in `tests/shell/known_failures.txt` named there (EXECUTED, the function-depth law).
3. Arrays, the parameter operators, extglob, `<<<`, `|&`, process substitution. **Met**, with the listed cases (EXECUTED).
4. The loop budget ends `while true; do :; done` at exactly its count (**met**, EXECUTED, the loop law); a verb call per iteration counts against `VERB_CALL_BUDGET` (**not met**: `agents/2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md`).
5. The Oils files run and their rate is published; the known deltas are exhaustive. **In part:** `known_failures.txt` and `deltas.txt` are exhaustive, held by the corpus test; the Oils rate is not measured.
6. The refusals and `a & b & wait`. **In part:** `jobs`, `fg`, `bg`, `disown`, `eval`, `exec`, `trap` and `coproc` are refused before the line runs, and `a & b & wait` runs both (EXECUTED, the corpus); `nohup` is a name not found (127), `ulimit` says it is not supported (status 1), `umask` prints `0022`, and `source` of a literal path is refused rather than read.
7. The durable run's expansion reads in a ledger. **Not met:** the machine asks its host for `time` and `random` through the `value` request, so a host can record them, but no ledger exists (H4 is not built).
8. ADR 081 and 084 amended; the glossary and the architecture page say "bash". **Not met:** documents under `context/` take no new work, and the reference page `documentation/reference/shell.md` says bash.
