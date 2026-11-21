# The Shell

`cli` runs a line of bash inside the file system. Every file the line reads, lists or writes is a call of a public verb, made as the caller. So a line can do nothing that its caller could not do with the Python API.

```python
result = await fs.cli("grep -rn TODO /docs | sort | head -3", authority=alice)
print(result.stdout)
```

The result carries `stdout` and `stderr` as bash prints them, and `exit_status` as bash would exit. `Session.cli` runs a line as the session's authority. `VirtualFileSystem.cli` is the same call without `await`.

## How a Line Runs

A line is parsed whole before anything runs. A syntax error, a refused word or a spent parse budget fails the call, and nothing in the line runs.

The interpreter does no input or output of its own. It asks for every effect as a request, and vfs answers each request with one public verb:

| The line does | vfs calls |
|---|---|
| reads a file (`cat f`, `< f`, `$(<f)`) | `read` |
| tests or lists (`[ -f f ]`, `cd d`, `*.md`, `ls`) | `stat`, `ls` |
| writes (`> f`, `>> f`, `touch f`) | `write`, with `append` or `if_absent` |
| `mkdir`, `rm`, `cp`, `mv` | `mkdir`, `delete`, `copy`, `move` |

A line never runs as the system actor.

A program's own non-zero status is not a failure of the call: `grep` with no match exits 1, and the call still succeeds. A verb that a program was refused, such as a `read` of a file the caller may not see, is kept on the result as a warning.

## The Language

The shell speaks bash 5.3: pipes, lists, redirections, here-documents, `for`, `while`, `until`, `if`, `case`, `select`, functions, `[[ ]]`, `(( ))`, arithmetic, indexed and associative arrays, every parameter operator, brace, tilde and pathname expansion, command and process substitution, `&` and `wait`, and the builtins bash defines.

These words are refused, because they have no meaning inside one call:

| Word | Why |
|---|---|
| `eval`, `source`, `.` | A line is parsed whole before it runs. |
| `exec` | A line cannot replace its own process. |
| `trap` | A line receives no signals. |
| `jobs`, `fg`, `bg`, `disown`, `suspend`, `coproc` | Job control does not reach past the call. |
| `alias`, `unalias` | Aliases are not expanded in a non-interactive shell. |

## The Programs

These programs run inside the shell and print what GNU coreutils, grep, sed and findutils print: `cat`, `cp`, `cut`, `find`, `grep`, `head`, `ls`, `mkdir`, `mv`, `rm`, `sed`, `sort`, `tail`, `tee`, `touch`, `tr`, `uniq` and `wc`. Any other name exits 127 with `command not found`.

## Exit Statuses

| Status | Meaning |
|---|---|
| 0 | The last command succeeded. |
| 1 to 125 | The last command's own status. |
| 2 | The line did not parse, or it holds a refused word. |
| 127 | A command was not found. |
| 130 | The line was cancelled. |
| 137 | A budget ended the line. |

## Budgets

A line runs under budgets. A host may set each of them, lower or higher.

| Budget | Default |
|---|---|
| Source text | 1 MiB |
| Tokens | 100,000 |
| Nesting depth | 200 |
| Stages in one pipeline | 64 |
| Loop iterations in the line | 1,000,000 |
| Nested function calls | 256 |
| Bytes the shell holds at once | 64 MiB |

## How Closely It Follows Bash

The shell is tested against a corpus of 3,320 scripts, each recorded once by bash 5.3 and GNU coreutils in a pinned container image. A run compares standard output and the exit status exactly, and standard error as empty or not.
