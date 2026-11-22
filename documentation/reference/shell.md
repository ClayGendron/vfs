# The Shell

`cli` runs a line of bash inside the file system. Every file the line reads, lists or writes is a call of a public verb, made as the caller. So a line can do nothing that its caller could not do with the Python API.

```python
line = "grep -rn TODO /docs | sort | head -3"
result = await fs.cli(line, authority=alice)
print(result.stdout)
```

The result carries `stdout` and `stderr` as bash prints them, `exit_code` as bash would exit, and `statuses`, each top-level pipeline's `PIPESTATUS`. `Session.cli` runs a line as the session's authority. `VirtualFileSystem.cli` is the same call without `await`.

## How a Line Runs

A line is parsed whole before anything runs. A syntax error, a refused word or a spent parse budget fails the call, and nothing in the line runs.

The interpreter does no input or output of its own. It asks for every effect as a request, and vfs answers each request with one public verb:

| The line does | vfs calls |
|---|---|
| reads a file (`cat f`, `< f`, `$(<f)`) | `read` |
| tests or lists (`[ -f f ]`, `cd d`, `*.md`, `ls`) | `stat`, `ls` |
| writes (`> f`, `>> f`, `touch f`) | `write`, with `append` or `if_absent` |
| `mkdir`, `rm`, `cp`, `mv` | `mkdir`, `delete`, `copy`, `move` |
| `grep -r`, `find` | `grep`, `glob`, as described under *The Programs* |

A line never runs as the system actor.

A redirection is opened as bash opens it, before its command runs, so a command never acts before vfs refuses its file. When the command only prints (`echo`, `:`, `true`, `printf` without `-v`, or `cat` reading an input its own redirection gives it), its file is judged with a `stat` and written with one `write` of all its bytes. Any other command could act first, so its file is opened with a `write` of no bytes, and what the command prints follows in a second `write`. Output past 8 MiB is written in more than one request.

The interpreter runs inside a WebAssembly module, in a runtime linked into vfs. The runtime is the wall around the line. It counts every instruction the line executes, holds the module's memory under a hard limit, and ends the line when its deadline passes or its call is cancelled. A fault inside the interpreter ends that line with an error; the process goes on. Each line runs in a fresh instance, one slice at a time on vfs's worker pool, so the event loop keeps serving other calls while a line computes.

## The Result

`success` says whether the line ran to its end as written. `exit_code` and `statuses` say how its commands fared. This is the contract of Python's `subprocess.run`: a program that exits 1 has still run.

So a command's non-zero status is not a failure of the call. `grep` with no match exits 1, and the call succeeds. A verb vfs refused inside the line, such as a `read` of a file that does not exist, is kept on the result as a warning, and the call still succeeds. Lines such as `cat f 2>/dev/null || touch f` and `rm -f tmp` meet a missing file on purpose and work as written.

```python
result = await fs.cli("cat /nope | wc -l", authority=alice)
assert result.success and result.exit_code == 0
assert result.statuses == [[1, 0]]
```

The call fails when the line did not run to its end: it did not parse, it holds a refused word, or a budget, the deadline or a cancel ended it. A caller who wants a failing command to fail the call checks `exit_code`, or starts the line with `set -e`.

| Field | What it holds |
|---|---|
| `stdout`, `stderr` | What the line printed to each stream, as UTF-8 text with invalid bytes replaced. |
| `exit_code` | `$?` of the line, as bash would exit; the statuses are listed below. |
| `statuses` | For each pipeline of the line's top level that set `PIPESTATUS`, in order, the `PIPESTATUS` bash reads right after it. A pipeline inside a loop, a function or a compound command adds no entry of its own, so the list is bounded by the line's text. A function definition, and a compound command that ran no pipeline, set none and add no entry. A job run with `&` adds none, and `wait` reports it. |
| `errors` | Why the line did not run to its end, and, as warnings, each distinct thing vfs refused inside it, once. Past 100 distinct refusals, the rest are counted in one `truncated` warning. |
| `fuel_used` | The instructions the line executed. |
| `ops` | Always `("cli",)`. |

`str(result)` prints the line's standard output, then its standard error, then its facts.

`cli` is no mount's operation. It is not in `capabilities()`, and a mount's `deny_ops` refuses to name it. Each verb inside the line is judged and masked as its own operation, so a mount's mask holds inside a line as it holds outside one.

## The Language

The shell speaks bash 5.3: pipes, lists, redirections, here-documents, `for`, `while`, `until`, `if`, `case`, `select`, functions, `[[ ]]`, `(( ))`, arithmetic, indexed and associative arrays, the parameter operators, brace, tilde and pathname expansion, command and process substitution, `&` and `wait`, and bash's builtins. Where it still differs from bash, the case is named in the corpus's list of known failures, described at the end of this page.

These words are refused, because they have no meaning inside one call:

| Word | Why |
|---|---|
| `eval`, `source`, `.` | A line is parsed whole before it runs. |
| `exec` | A line cannot replace its own process. |
| `trap` | A line receives no signals. |
| `jobs`, `fg`, `bg`, `disown`, `suspend`, `coproc` | Job control does not reach past the call. |
| `alias`, `unalias` | Aliases are not expanded in a non-interactive shell. |

## The Programs

These programs run inside the shell and print what GNU coreutils, grep, sed and findutils print: `cat`, `cp`, `cut`, `find`, `grep`, `head`, `ls`, `mkdir`, `mv`, `rm`, `sed`, `sort`, `tail`, `tee`, `touch`, `tr`, `uniq` and `wc`.

### `grep -r` and `find`

vfs serves `grep -r` and `find` from its indexed verbs, so a search of a large tree costs one call, not one call per file.

- `grep -r` is one call of `grep`. It is served with the options `-E`, `-F`, `-G`, `-n`, `-l`, `-c`, `-h`, `-H`, `-s`, `-q`, `-e` and `-R`, their long forms, and `--include` and `--exclude`. `-i` is served for a pattern of ASCII that holds no `i`, no `k` and no bracket, since GNU folds `i` with the dotless `ı` and the indexed `grep` does not, and the indexed `grep` folds `k` with the Kelvin sign and GNU does not. `-c` adds one call of `glob`, to print the files that hold no match.
- `find` is one `stat` and one call of `glob` for each place it starts from. It is served with `-name`, `-iname`, `-path`, `-ipath`, `-wholename`, `-type f`, `-type d`, `-maxdepth`, `-mindepth`, `-true` and `-print`, joined by `-a`.

Any other form runs as the shell's own program, which reads the tree with one `read`, `ls` or `stat` for each entry. That includes `grep`'s `-v`, `-o`, `-x`, `-w` and context lines, `find`'s `-o`, `!` and `-prune`, and a pattern construct the two matchers read differently, such as `\<`, `\w` or `[[:alpha:]]`. Either way the output is what the shell's own program prints, in its order. Only the cost differs. The shell's own `grep` knows no `--include` or `--exclude`, so a form of those that is not served ends in `unrecognized option`, as when a `--include` follows an `--exclude`.

A served `grep -r` differs from GNU grep in two cases. No verb can tell these cases apart without reading every file:

| Case | GNU grep | A served `grep -r` |
|---|---|---|
| A file the caller may list but not read | prints `Permission denied` and exits 2 | leaves the file out, and `-c` counts it 0 |
| A body stored as bytes, not as text | matches its raw bytes and prints `Binary file ... matches` | never matches it |

A file the shell writes is stored as text when it is UTF-8. So the second case meets only bodies a caller wrote as bytes.

### The verbs with no Unix name

vfs runs these programs itself. Each is one call of its verb, as the caller. Each takes its options as GNU tools do and prints its options with `--help`. A misuse prints its reason and a usage line, and exits 2. A refusal prints `name: path: reason`, and exits 1.

| Program | What it prints |
|---|---|
| `glob [-t f\|d] [-n MAX] PATTERN [PATH...]` | The matching paths, one a line, in path order. |
| `search [-n LIMIT] QUERY [PATH...]` | The paths `search` ranks first, best first. |
| `traverse [-e] [-m] [-d DEPTH\|all] [-t TYPE]... [-T TYPE]... [-n LIMIT] METHOD PATH...` | The nodes the walk reaches, nearest first; with `-e`, `SOURCE`, `TYPE` and `TARGET` for each edge, separated by tabs. |
| `grants PATH` | `PATH`, `PRINCIPAL` and `LEVEL` for each grant that decides access at `PATH`, separated by tabs. |
| `grant PATH PRINCIPAL LEVEL`, `revoke PATH PRINCIPAL` | Nothing, when the grant is given or removed. |
| `edit [-a] PATH OLD NEW` | Nothing, when the edit applies. `-a` replaces every `OLD`. |
| `mkedge -t TYPE SOURCE TARGET`, `rmedge -t TYPE SOURCE TARGET` | Nothing, when the edge is made or removed. |

`glob`, `search` and `traverse` print absolute paths, and exit 0 when they print something, 1 when they find nothing and 2 on trouble, as `grep` does.

### Other names

The interpreter asks vfs for every other name, and vfs answers in one of two ways:

| Name | What happens |
|---|---|
| `curl`, `wget` | Refused, exit 126: the line prints that network access is not available. |
| `git`, `sudo`, `python3`, `python`, `perl`, and any other name | Exit 127, `command not found`. For the first five, a hint follows at what does the work here. |

## Exit Statuses

| Status | Meaning |
|---|---|
| 0 | The last command succeeded. |
| 1 to 125 | The last command's own status. |
| 2 | The line did not parse, or it holds a refused word. |
| 126 | vfs knows the program and will not run it. |
| 127 | A command was not found. |
| 124 | The line's deadline passed. |
| 130 | The line was cancelled. |
| 137 | A budget ended the line. |

## Budgets

A line runs under budgets. `cli` runs every line at these defaults; `vfs.shell.run_line` takes each of them, lower or higher. The shell is for an agent's lines, not for bulk work: a loop over ten thousand files is ten thousand verb calls, where the batch verbs (`write` with many entries, `copy` and `move` with many pairs) do the same work in one call.

| Budget | Default |
|---|---|
| Source text | 1 MiB |
| Tokens | 100,000 |
| Nesting depth | 200 |
| Stages in one pipeline | 64 |
| Loop iterations in the line | 1,000,000 |
| Nested function calls | 256 |
| Compound commands and substitutions open inside one another | 1,000 |
| Bytes the shell holds at once | 64 MiB |
| Bytes written to standard output and error | 16 MiB |
| Instructions executed | 20,000,000,000, about five seconds of work |
| Memory of the module | 256 MiB |
| Seconds from the line's start to its end, its verbs included | 30 |

Moving bytes between the interpreter and vfs costs instructions too: about 270 for each byte `cat` reads, and about 1,100 for each byte `grep` searches. So under the default budget a line reads tens of megabytes, not more. A served `grep -r` moves what it matches, and a served `find` what its first `-name` matches, or every entry beneath its start when it has none; it holds all of it before the line reads the first, so `| head` does not make it stop early, as it does the shell's own program. A form the shell's own program runs reads every entry beneath its root, which bounds it to thousands of files a line.

The instruction count is a function of the line and its replies, and the result reports it as `fuel_used`. An arithmetic expression or a `[[ ]]` condition counts each link of a long chain, such as `1+1+1`, against the parse depth, so a chain thousands of links long is an error rather than a crash. A regular expression that cannot be matched within its own budget fails with status 2 and says so; it never answers "no match".

## How Closely It Follows Bash

The shell is tested against a corpus of 3,339 scripts, each recorded once by bash 5.3 and GNU coreutils in a pinned container image, 13 of them found by a differential fuzzer that runs generated scripts through the shell and through bash. A run compares standard output and the exit status exactly, and standard error as empty or not. 3,218 of the 3,339 pass; the other 121 are listed by name in `tests/shell/known_failures.txt`, and the corpus test fails when a listed case starts to pass or an unlisted one fails.
