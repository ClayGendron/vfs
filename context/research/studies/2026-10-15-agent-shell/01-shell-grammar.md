# S1 — The shell grammar the vfs agent shell should speak at v1, and how it grows

- Date: 2026-10-15
- Researcher: S1 (shell grammar)
- Clones read (commit, date): `oils` bdc8364 (2026-10-14), `mvdan-sh` 0e8ea6f (2026-10-12),
  `brush` c495882 (2026-10-15), `nushell` 818d4ac06 (2026-10-15), `elvish` 26a8bd5 (2025-07-14),
  `PowerShell` db1d0a5 (2026-10-14), `just-bash` 9ab0e0d (2026-10-15), `bashkit` b7904a4
  (2026-10-15), `just-bash-py` 48d111c (2026-06-04), `lifo` 5a35d05 (2026-10-09),
  `plan9port` b6564bd9 (2026-08-26), `9front` a0806493 (DIRTY clone, not refreshed; cited at that
  commit only for a diff against plan9port). `plan9` (DIRTY, ed1a9c21e) was not read; rc is cited
  from plan9port. `bash` was not cloned; bash semantics come from the POSIX text, mvdan-sh's
  `LangBash` and brush.
- Evidence labels: **EXECUTED** (a script ran and the number is its output), **READ** (a file or
  spec was read and is cited), **INFERRED** (my judgement from the evidence). Every claim below
  carries one. Measured command frequencies come from experiment e2
  (`experiments/e2/commands.md`, 418 Claude Code transcripts, 12,627 Bash tool calls) and are
  labelled **EXECUTED (e2)**.
- Scripts and outputs: `experiments/s1/` — `corpus.jsonl` (100 commands weighted to the e2
  shares), `corpus-coverage.jsonl` (100 commands that deliberately touch the rare constructs),
  `bad.jsonl` (10 malformed commands), `corpus_stats.py`, `patch_corpus.py`, `mvdan_parse/`
  (Go runner), `run_ts.ts` + `run_ts_driver.ts` (bun runner for just-bash and lifo), `run_py.py`
  (shlex floor and just-bash-py), `summarize.py`, and `results/*.summary.md`.

## Summary

The vfs shell should speak a **static, bash-shaped subset of the POSIX shell command language**,
parsed by our own parser, with the bash-isms agents actually type admitted on purpose and the rest
refused with a classified error. The measured traffic settles the v1 line: pipes appear in 74% of
agent calls, `&&` in 44%, `2>&1` in 16%, `>` in 14%, here-documents in 12%, `$VAR` in 12%; the
control-flow keywords, functions, arithmetic, `[[ ]]`, `&` and `<( )` together touch under 10%
(EXECUTED, e2). So v1 is the **pipeline core**: words with the three POSIX quotings plus `$'…'`,
parameter expansion, `$( )` and backticks, globs and `{a,b}`, pipelines with `!`, the four list
operators `;` newline `&&` `||`, the file redirections including `2>&1` and `n>&m`, here-documents,
`( )` and `{ }` groups, and assignments. That grammar admits 86 of the 100 commands in the
weighted corpus outright (EXECUTED); adding `for` lifts it to 91. Control flow is the second slice,
functions and arithmetic the third, process substitution and arrays the last; `&` never becomes a
background job (the hermetic runtime has no process to detach), `set -e` does not exist as a mode,
and `pipefail` is answered by reporting every stage's status on the envelope rather than by a
flag. Plan 9's rc is the better-designed grammar — one quoting rule, lists as the only type, a
yacc grammar of 92 lines — but a model trained on bash produces zero rc, so rc is design input
(the list-valued `$status`, the `''` escape, no re-scanning) and not the surface. Parse errors are
facts: a new `vfs.invalid.syntax` kind, a path-free detail that names the construct and what must
follow it (mvdan-sh's style, not bash's "unexpected token"), line and column, and an `incomplete`
flag.

## Findings

### 1. The POSIX shell command language, feature by feature, ranked by what agents type

POSIX.1-2024 (Issue 8) chapter 2 was read via WebFetch in five slices on 2026-10-15
(READ, URL in Sources). The frequencies are EXECUTED (e2) unless marked INFERRED.

| Feature (POSIX §) | What the spec says | What an agent uses it for | Share of agent calls |
|---|---|---|---|
| Backslash quoting §2.2.1 | `\` keeps the next character literal; `\`+newline is a line continuation | escaping a `"` or `$` inside a `-c` string; wrapping a long pipeline | INFERRED: rare, under 3% |
| Single quotes §2.2.2 | every character literal; a `'` cannot appear inside | `sed -n '100,150p'`, `awk '{print $1}'`, `-k "grep and not slow"` | INFERRED: 30–40% (in most sed/awk/python -c calls) |
| Double quotes §2.2.3 | literal except `$`, backquote, `\` (and `\` only before `$ \` " \ newline`) | `grep -n "def route("`, `echo "exit=$?"` | INFERRED: 40–50% |
| `$'…'` §2.2.4 | **new in 2024**: C escapes `\n \t \xHH \ddd` | `printf $'a\tb'`; rare | INFERRED: under 1% |
| Token rules §2.3 | 10 rules; operators are longest-match; `#` starts a comment; `$'` starts quoting (rule 4) | — | — |
| Reserved words §2.4 | `! { } case do done elif else esac fi for if in then until while`; recognised only at command start | — | — |
| Special parameters §2.5.2 | `$@ $* $# $? $- $$ $! $0` | `$?` after a pipeline, `"$@"` in a function | `$?`: INFERRED 2–3%; the rest under 1% |
| Shell variables §2.5.3 | `HOME IFS PATH PWD PS1 PS2 PS4 LINENO PPID ENV LANG LC_*` | `$HOME`, `$PWD` | part of the 12% `$VAR` |
| Word-expansion order §2.6 | (1) tilde, parameter, command and arithmetic, left to right; (2) field splitting; (3) pathname expansion unless `set -f`; (4) quote removal last | `for f in $(find …)` relies on (2); `ls *.py` on (3) | glob `*` 25% |
| Tilde §2.6.1 | lone `~` → `$HOME`; `~name` via `getpwnam` | `ls ~/Git/Repos` | INFERRED 3–5% |
| Parameter expansion §2.6.2 | `${p} ${#p} ${p:-w} ${p:=w} ${p:?w} ${p:+w} ${p%w} ${p%%w} ${p#w} ${p##w}`; no colon = test unset only | `${VAR:-default}`, `${PIPESTATUS[0]}` (bash) | `$VAR` 12% total; the operators INFERRED under 2% |
| Command substitution §2.6.3 | `$(cmd)` and `` `cmd` ``; trailing newlines stripped; inside backquotes `\` is literal except before `$ \` \` | `echo "$(date)"`, `"$(cat <<'EOF' …)"` commit messages | `$( )` 3.7%, backticks 4.4% |
| Arithmetic §2.6.4 | `$((expr))`, signed long | counters | 0.6% |
| Field splitting §2.6.5 | on `IFS`; unset `IFS` = space, tab, newline; empty `IFS` = no splitting | implicit in `for f in $(…)` | with the 4.6% `for` |
| Pathname expansion §2.6.6, §2.14 | `* ? [...]`; a quoted character matches itself | `src/vfs/*.py`, `--include=*.py` | 25% |
| Quote removal §2.6.7 | last step; the shell remembers which characters were quoted (matters for `case`) | — | — |
| Redirection §2.7 | `< > >| >> << <<- <& >& <>`, optional `n` prefix (IO_NUMBER), optional `{var}` location | `2>&1` 16%, `>` 14%, `<` 5%, `>>` 1.7% | heredoc `<<` 12% |
| Here-document §2.7.4 | `<<word`; quoted delimiter = no expansion; `<<-` strips leading tabs; body ends at a line equal to the delimiter | writing a file, feeding `python -`, a commit message | 12% |
| Shell errors §2.8.1 | a syntax error exits a non-interactive shell; "command not found" = 127; non-executable = 126 | the agent reads 127 as "tool missing" | — |
| Simple command §2.9.1 | assignments and redirections saved; first non-assignment word expanded; redirections performed; a command with no name has status of the last `$( )` or 0 | `FOO=bar cmd`, `X=1; …` | assignment prefix INFERRED 2% |
| Pipeline §2.9.2 | `[!] cmd1 [| cmd2 …]`; status = rightmost, unless `pipefail` (**in POSIX 2024**): then the rightmost failing stage; `!` negates | the dominant shape: `cmd 2>&1 \| tail -5` | 74% |
| Lists §2.9.3 | `;` and newline sequence; `&` async (status 0, no wait); `&&` and `\|\|` equal precedence, left-associative | `cd X && cmd \| head` | `&&` 44%, `\|\|` 1.4%, `&` 0.2% |
| Compound commands §2.9.4 | `( list )` subshell; `{ list; }` group; `for name [in words] do … done`; `case word in pat) … ;; esac` (`;&` added, `;;&` not); `if … then … [elif] [else] fi`; `while`/`until … do … done` | `( cd x && … )` subshell, `for f in …` | `( )` 28% (mostly literal parens in python -c and grep patterns, INFERRED from the regex), `for` 4.6%, `if` 0.9%, `case` 0.5%, `while` 0.4% |
| Function §2.9.5 | `fname ( ) compound-command [redirects]`; expanded at call time | small helpers in long scripts | 1.2% |
| Grammar §2.10 | yacc productions `complete_command → list → and_or → pipeline → pipe_sequence → command …`; the grammar wins over the prose | — | — |
| `set -e` (set utility) | exit on a failing command, except any non-last command of an AND-OR list, the condition of `while/until/if/elif`, a `!` pipeline, a non-last pipeline stage | `set -euo pipefail` at the top of a script | INFERRED under 1% (`set` is 6 of 67,000 segments in e2) |
| Special built-ins §2.15 | `break : continue . eval exec exit export readonly return set shift times trap unset` | `export`, `unset`, `source`/`.` | `unset` 0.3%, `export` 0.1%, `.` + `source` 0.15% |

Two POSIX facts matter for vfs design and were **not** in my prior knowledge: `$'…'` and
`pipefail` are both standard in Issue 8 (READ, §2.2.4 and §2.9.2). A "POSIX subset" therefore
already includes the two bash-isms agents most often reach for in quoting and status handling.

### 2. Plan 9 rc: what Duff simplified, and whether it is a better v1

Read: Duff's paper via `https://9p.io/sys/doc/rc.html` (the cat-v mirror returned HTTP 402),
`plan9port/src/cmd/rc/syn.y` (92 lines), `lex.c`, `man/man1/rc.1`. (READ)

- **One quoting rule.** A word is quoted only with `'…'`, and a literal apostrophe is a doubled
  `''` (`lex.c:348-369`; `rc.1:160-162`). There are no double quotes and no backslash escapes
  inside words; outside quotes a backslash is just a character except that `\`+newline is a
  continuation (`lex.c:70-80`). Variables are substituted *after* parsing and never re-split, so
  `"$x"` is unnecessary (paper §28: "Input is never scanned more than once").
- **Lists are the only type.** `$x` is a list, `$#x` its length, `$"x` the space-joined string,
  `$x(2)` a subscript, `(a b c)` a literal list, and `^` concatenates with distribution over lists;
  rc inserts `^` between adjacent words ("free carets", `lex.c:199-215`). `$ifs` is used only to
  split command-substitution output (paper §9).
- **Command substitution** is `` `{cmd} `` — a unary brace form, so it nests with no escapes.
  Non-linear pipelines `<{cmd}` and `>{cmd}` are the `syn.y:89` `REDIRW` token (9front's dirty
  clone has dropped that token and handles `<{` differently, `9front/sys/src/cmd/rc/syn.y` diff
  lines 2, 22, 39; READ, cited at a0806493).
- **Redirections** `< > >> <>`, with fd selection as `>[2]`, `>[2=1]`, `|[2]` (`rc.1:308-340`,
  `rc.1:374-400`).
- **Control flow** is C-shaped: `if(list) cmd`, the separate `if not` clause, `for(i in list)
  cmd`, `while(list) cmd`, `switch(word){ case pat … }`, `fn name { … }`, `~ subject patterns`
  (`syn.y:43-72`). Keywords are recognised anywhere a command starts; `!` and `@` (subshell) are
  unary command operators (`rc.1:400-430`).
- **Status is a string**, empty on success; a pipeline's status is the `|`-joined list of its
  stages' statuses, true when every element is empty or `0` (paper §11).
- **Grammar size.** `syn.y` is 92 lines with eleven precedence levels (`syn.y:5-11`). Duff's
  stated wins: no re-scanning, no four quoting types, no `IFS`-splitting of substituted values
  (and so no `IFS` injection), signal handlers as functions, and a grammar one can state exactly.
  He concedes `if not` is "admittedly feeble".

**Is rc a better v1 for an LLM trained on bash?** No (INFERRED, from the e2 data). Every one of
the 12,627 measured calls is bash; a model will keep emitting `"$x"`, `$(…)`, `2>&1`, `&&`, and
`do … done`. An rc surface would turn 74% of traffic into parse errors on day one. rc's *ideas*
transfer without its syntax: single-pass parsing with no rescanning (we must do this anyway: the
shell string is one `cli` call, never `eval`-ed), never re-splitting substituted values (OSH's
"simple word evaluation" is the same idea, §3), the list-valued pipeline status (§6 of "What this
means"), and the refusal to have four quoting rules — which we cannot adopt, but we can keep the
rule set to one table (below).

### 3. The modern re-implementations

**oils / OSH / YSH** (READ, `oils@bdc8364`). OSH is a bash-compatible parser that parses
*statically* — "you get syntax errors up front. In shell, syntax errors can occur at runtime"
(`doc/ysh-vs-shell.md:12-16`). Its spec suite is the largest shell conformance corpus we have:
**229 files and 3,966 `####` cases** (EXECUTED, `grep -c '^#### ' spec/*.test.sh`). The heaviest
files tell us where bash's complexity actually lives: `array` 78, `arith` 74, `builtin-read` 64,
`builtin-printf` 63, `word-split` 55, `brace-expansion` 55, `builtin-bracket` 52, `dbracket` 49,
`assign` 48, `alias` 48, `var-sub-quote` 41, `redirect` 41, `here-doc` 36, `errexit` 36,
`quote` 35, `pipeline` 26, `background` 27, `shell-grammar` 38, `parse-errors` 27. Arrays plus
arithmetic alone are 152 cases — 3.8% of the suite for constructs that are 1.4% of agent traffic.
YSH's design arguments (`doc/ysh-vs-shell.md:20-90`): three sublanguages (command, word,
expression) instead of four (command, word, arith, bool); `{ }` instead of `then fi`/`do done`;
keywords `var`/`setvar` instead of assignment builtins; procs with true local scope instead of
dynamic scope; **multiline strings replace here-docs**; **`fork` and `forkwait` builtins replace
`&` and `( )`**; simple word evaluation replaces implicit splitting and dynamic globbing. Known
static-parsing differences worth copying (`doc/known-differences.md:91-110, 155`): `$((` is always
arithmetic (write `$( (` for a subshell in a command sub), and a here-doc terminator must be on
its own line. Parse errors exit with status 2 (`spec/parse-errors.test.sh`), and the error printer
shows the offending line with a caret under the token (`display/ui.py:109-134`).

**mvdan-sh** (READ, `mvdan-sh@0e8ea6f`). A Go parser, formatter (`shfmt`) and interpreter with
five dialects: `LangBash`, `LangPOSIX`, `LangMirBSDKorn`, `LangBats`, `LangZsh`
(`syntax/parser.go:29-104`). The AST (`syntax/nodes.go`) is the cleanest reference for ours:
`File → Stmt{Cmd, Redirs, Background, Negated, Coprocess}`; `Command` is one of `CallExpr`
(words + assigns), `Subshell`, `Block`, `IfClause`, `WhileClause`, `ForClause` (`WordIter` or
`CStyleLoop`), `BinaryCmd` (`&&`, `||`, `|`, `|&`), `FuncDecl`, `CaseClause`, `TestClause`
(`[[ ]]`), `DeclClause`, `ArithmCmd`, `TimeClause`, `CoprocClause`, `LetClause`; a `Word` is a
list of `WordPart`: `Lit`, `SglQuoted`, `DblQuoted`, `ParamExp`, `CmdSubst`, `ArithmExp`,
`ProcSubst`, `ExtGlob`, `BraceExp` (`nodes.go:223-1093`). Dialect gating is one helper,
`checkLang` (`parser.go:1092-1108`), called at **37 sites** (EXECUTED count). What it refuses
under `LangPOSIX` is exactly the bash-ism list: `${|stmt;}` command subs, extended globs
(`parser.go:1430`), `${!foo}` (1577), arrays (1606, 2043), `${x/a/b}` search-and-replace (1630),
`${x:1:2}` slicing (1665), `${x@Q}` and other expansion operators (1683-1694), `{varname}>` fd
redirects (2122), `&>`, `&>>`, `>|`-style extras (2127-2129), here-strings `<<<` (2150),
`for … { }` (2520), C-style `for ((…))` (2538), `=~` regex tests (2742), the `declare`-family
and `function` keywords (2960, 2987). Its parser does not backtrack: `$((` is always arithmetic
(README "Caveats"). Error types: `ParseError{Filename, Pos, Text, Incomplete}` and
`LangError{Pos, Feature, Langs, LangUsed}` (`parser.go:1014-1050`); `Incomplete` is true when the
input ended inside an unfinished construct (`parser.go:968-973, 1084`).

**brush** (READ, `brush@c495882`). A Rust bash reimplementation whose `brush-parser` is a PEG
grammar (`brush-parser/src/parser/peg.rs`, 839 lines) over a hand-written tokenizer. It stages
features with two switches, not a dialect enum: `ParserOptions{enable_extended_globbing,
posix_mode, sh_mode, …}` (`parser/mod.rs:25-50`) and a single PEG predicate
`non_posix_extensions_enabled()` (`peg.rs:732`) consulted at **17 rule sites** (EXECUTED count):
`pipeline_timed`, `|&`, `compound_command` extras, `io_filename` process substitution,
`assignment_word` arrays and `+=`, and so on. Its AST (`ast.rs`, 2,485 lines) is POSIX-named:
`Program → CompleteCommand → AndOrList → Pipeline → Command → {Simple, Compound, Function,
ExtendedTest}` with `IoRedirect{IoFile, HereDocument, OutputAndError, ProcessSubstitution}`
(`ast.rs:1539-1700`). Errors: `ParseError::{ParsingNear(line, col), ParsingAtEndOfInput,
Tokenizing{inner, position}}` with an optional miette pretty-printer (`error.rs:5-65`). Its test
corpus is **132 YAML files, 3,158 cases** that run the same script under brush and real bash and
diff stdout, stderr, status and filesystem (EXECUTED count; `README.md:107-110`). The heaviest
files: `nameref` 230, `set-e` 159, `declare` 136, `ifs` 97, `trap` 92, `here` 87, `printf` 74,
`set-u` 69, `read` 69, `command_substitution` 57, `redirection` 48, `arrays` 46, `pipelines` 24
— again, the hard cases are in the builtins and the variable machinery, not in the pipeline
grammar. Its compatibility reference (`docs/reference/compatibility.md:11-112`) lists what a
"full bash" means in 2026: `select`, `wait -n`, `disown` and signal traps still missing.

**nushell** (READ, `nushell@818d4ac06`). The grammar is a pipeline of *values*, not bytes, and it
refuses the bash operators by name with a hint: `ParseError::ShellAndAnd` ("instead of '&&', use
';' or 'and'"), `ShellOrOr` ("use 'try' or 'or'"), `ShellErrRedirect` ("use 'err>' instead of
'2>'"), `ShellOutErrRedirect` ("use 'out+err>' instead of '2>&1'")
(`crates/nu-protocol/src/errors/parse_error.rs:125-145`). The redirection tokens are words:
`out>`, `o>`, `err>`, `e>`, `out+err>`, `o+e>`, and the pipe variants `e>|`, `o+e>|`
(`crates/nu-parser/src/lex.rs:854-897, 1285`). The lesson for us is the *error shape*: a refused
bash-ism is a first-class error variant that names the construct and the replacement, not a generic
"unexpected token".

**elvish** (READ, `elvish@26a8bd5`). `Chunk → Pipeline{Forms, Background} → Form{Head, Args,
Opts, Redirs}` (`pkg/parse/parse.go:86-200`); redirections are only `< > >> <>` with an `&fd`
right-hand side (`parse.go:204-245`); single quotes use rc's `''` doubling and double quotes take
C escapes (`parse.go:476-540`); output capture is `(cmd)` and exception capture `?(cmd)`
(`parse.go:464, 716-726`). Elvish, like nushell, keeps `|` and `&` and drops `&&`/`||` in favour
of `and`/`or` on values. Pipes survive every redesign; the list operators do not.

**PowerShell** (READ, briefly, `PowerShell@db1d0a5`). The tokenizer has `AndAnd`/`OrOr` tokens
(added in PowerShell 7; `token.cs:159-162`) and typed redirection tokens — `FileRedirectionToken`
(stream, append) and `MergingRedirectionToken` (from-stream, to-stream) for `2>&1`
(`token.cs:1500-1550`). An object pipeline still spells its redirects the bash way; that is the
only grammar fact we need from it.

### 4. The agent-shell peers, and the feature matrix

**just-bash** (READ, `just-bash@9ab0e0d`, Apache-2.0). A TypeScript bash interpreter over a
virtual filesystem. The parser (`packages/just-bash/src/parser/`, 11,470 lines including tests)
is a hand-written recursive descent with a separate arithmetic parser (1,170 lines), expansion
parser (1,115) and conditional parser (466). Its AST (`ast/types.ts`) covers everything mvdan's
does: `IfNode`, `ForNode`, `CStyleForNode`, `WhileNode`, `UntilNode`, `CaseNode`, `SubshellNode`,
`GroupNode`, `ArithmeticCommandNode`, `ConditionalCommandNode` (`[[ ]]`), `FunctionDefNode`,
`HereDocNode`, `ProcessSubstitutionPart`, `BraceExpansionPart`, `TildeExpansionPart`, and a full
`ParameterOperation` set including bash's `${!x}` indirection, `${x@Q}` transforms and `${!arr[@]}`
(`ast/types.ts:132-500`). Redirection operators admitted: `< > >> >& <& <> >| &> &>> <<< << <<-`
(`ast/types.ts:272-284`). `$'…'` is lexed (`parser/lexer.ts:1150-1158`). Parse errors are
`ParseException(message, line, column, token?)` whose text is `Parse error at L:C: message`
(`parser/types.ts:74-85`); the parser is bounded by `MAX_INPUT_SIZE` 1 MB, `MAX_TOKENS` 100k,
`MAX_PARSE_ITERATIONS` 1M and `MAX_PARSER_DEPTH` 200 (`parser/types.ts:10-13`), which the threat
model lists as its parser-DoS defence (`THREAT_MODEL.md:95-103`). It refuses nothing at parse
time on purpose: the only "unsupported" in the parser is floating point in arithmetic
(`arithmetic-parser.ts:910`). **`&` parses but does not run in the background**: `StatementNode.
background` is set by the parser and read only by the AST serializer (`transform/serialize.ts:51`);
no interpreter file reads it (EXECUTED grep), `wait` is a no-op stub (`builtin-dispatch.ts:643`),
and the threat model says job control is "not systematically tested" (`THREAT_MODEL.md:262-266`).
The README's advertised shell features are the v1 list below almost verbatim: pipes, `> >> 2>
2>&1 <`, `&& || ;`, `$VAR ${VAR} ${VAR:-default}`, `$1 $@ $#`, globs, `if`, functions, `local`,
`for/while/until` (`packages/just-bash/README.md:119-131`).

**bashkit** (READ, `bashkit@b7904a4`, MIT). A Rust interpreter with "substantial IEEE 1003.1-2024
compliance" and 167 built-in commands (`README.md:16-17, 159`). Its parser (`crates/bashkit/src/
parser/`, 14,160 lines) has a fuel budget (`budget.rs`) and an AST with `ListOperator::{And, Or,
Semicolon, Background}` (`parser/ast.rs:99-108`), `CompoundCommand` including `Coproc`, `Time`,
`Select`, `ArithmeticFor` (`ast.rs:112-230`), and `RedirectKind::{Output, Clobber, Append, Input,
HereDoc, HereDocStrip, HereString, DupOutput, DupInput, OutputBoth, ReadWrite}` (`ast.rs:629-655`).
Advertised features (`README.md:183-204`): `$( )` and backticks, `$(( ))`, `declare -i`, `let`,
`| > >> < <<< 2>&1 &>`, POSIX and bash functions with `FUNCNAME`, indexed and associative arrays,
brace expansion including `{1..10}`, extended globs, `<( )`, `set -euxo pipefail`, `shopt`,
`[[ ]]` with `=~`. Errors are `Error::Parse{message, line, column}` rendered as `parse error at
line L, column C: message` (`error.rs:25-35`), and the messages deliberately mimic bash:
"syntax error near unexpected token `)'" and "syntax error: unexpected end of file"
(`parser/mod.rs:352-382`). **`&` runs the job once, synchronously, then files it**: the
interpreter polls the future a single time; if it is already finished the output is appended to
the parent's and a "finished" job is recorded, otherwise it is parked in a job table, and "background
commands always return exit code 0 to the parent" (`interpreter/mod.rs:8236-8275`). `analyze()`
reports command names, arguments and redirect targets before running, for permission prompts
(`README.md:125-138`).

**just-bash-py** (READ, `just-bash-py@48d111c`, Apache-2.0). A Python port of just-bash's parser
(`src/just_bash/parser/parser.py`, 2,912 lines; `lexer.py` 1,308). Its own run of the oils spec
suite is mostly red (`spec_test_results.txt`), so it is a corpus datum, not a reference. Its
`ParseException` carries line and column in the message.

**lifo** (READ, `lifo@5a35d05`, MIT). A browser Unix with a 508-line parser
(`packages/core/src/shell/parser.ts`). Tokens: `&> && & || | 2>&1 >&2 2>> 2> >> >&1 > < ;; ; ( )`
(`shell/lexer.ts:57-153`); reserved words `if then else elif fi for in do done while until case
esac` (`parser.ts:33-36`); `parseCommand` dispatches to `if/for/while/until/case`, a function
definition when it sees `name ( )`, a `{` group, else a simple command — **there is no subshell
production, no here-document, no process substitution** (`parser.ts:178-206`), and `&` is the
background flag on a list (`parser.ts:129-154`), executed as a real async job with a job table
and abort controller (`shell/interpreter.ts:136-175`). Errors are `ParseError(message, pos)` with a
character offset only. Its no-progress guard exists only at top level (`parser.ts:99-121`), which
is why a `( … )` inside a `do … done` body hangs it (EXECUTED, finding 5).

**Feature matrix.** Columns: POSIX 2024 (the spec), bash (mvdan-sh `LangBash` as proxy, plus
brush), rc, just-bash, bashkit, lifo, OSH. `Y` admitted, `N` refused or absent, `~` partial or
different spelling. Citations are to the files named above; the e2 share is the last column.

| Feature | POSIX | bash | rc | just-bash | bashkit | lifo | OSH | e2 share |
|---|---|---|---|---|---|---|---|---|
| `'…'` single quotes | Y | Y | Y (`''` escape) | Y | Y | Y | Y | — |
| `"…"` double quotes | Y | Y | N | Y | Y | Y | Y | — |
| `\` escape | Y | Y | ~ (newline only) | Y | Y | Y | Y | — |
| `$'…'` | Y (2024) | Y | N | Y `lexer.ts:1150` | Y | N | Y | <1% |
| `$VAR ${VAR}` | Y | Y | Y (lists) | Y | Y | Y | Y | 12% |
| `${VAR:-w}` family | Y | Y | N | Y | Y | ~ | Y | <2% |
| `${x/a/b} ${x:1:2} ${!x} ${x@Q}` | N | Y (`checkLang` 1630/1665/1577/1683) | N | Y | Y | N | Y | <1% |
| `$( )` | Y | Y | `` `{ } `` | Y | Y | Y | Y | 3.7% |
| backticks | Y | Y | N | Y | Y | Y | Y | 4.4% |
| `$(( ))` | Y | Y | N | Y | Y | N | Y | 0.6% |
| tilde `~` | Y | Y | N | Y | Y | Y | Y | ~4% |
| glob `* ? [ ]` | Y | Y | Y (`[~…]` negation) | Y | Y | Y | Y | 25% |
| extglob `@( )` | N | Y (1430) | N | Y | Y | N | Y | 0% |
| `{a,b}` `{1..3}` | N | Y | N | Y | Y | Y | Y | 0.9% |
| field splitting on IFS | Y | Y | N (only `` ` ``) | Y | Y | ~ | Y (strict opts) | implicit |
| `\|` pipeline, `!` | Y | Y | Y | Y | Y | Y | Y | 74% |
| `\|&` | N | Y | `\|[2]` | Y | Y | N | Y | 0% |
| `;` newline | Y | Y | Y | Y | Y | Y | Y | — |
| `&&` `\|\|` | Y | Y | Y | Y | Y | Y | Y | 44% / 1.4% |
| `&` background | Y | Y | Y | Y parse, N run | ~ (sync then job table) | Y (real job) | Y | 0.2% |
| `> >> <` | Y | Y | Y | Y | Y | Y | Y | 14/1.7/5% |
| `n>` `n>&m` `2>&1` | Y | Y | `>[2=1]` | Y | Y | ~ (fixed set) | Y | 16% |
| `>\|` `<>` `<&` | Y | Y | `<>` only | Y | Y | N | Y | 0% |
| `&>` `&>>` | N | Y (2127) | N | Y | Y | Y (`&>`) | Y | 0% |
| `<<` `<<-` here-doc | Y | Y | Y | Y | Y | **N** | Y | 12% |
| `<<<` here-string | N | Y (2150) | N | Y | Y | N | Y | 0% |
| `<( )` `>( )` | N | Y | `<{ }` | Y | Y | N | Y | 0.1% |
| `( )` subshell | Y | Y | `@` | Y | Y | **N** | Y | 28% (regex includes literal parens) |
| `{ ; }` group | Y | Y | `{ }` | Y | Y | Y | Y | — |
| `if/elif/else/fi` | Y | Y | `if( ) / if not` | Y | Y | Y | Y | 0.9% |
| `for … do done` | Y | Y | `for( )` | Y | Y | Y | Y | 4.6% |
| `for (( ; ; ))` | N | Y (2538) | N | Y | Y | N | Y | 0% |
| `while` `until` | Y | Y | `while( )` | Y | Y | Y | Y | 0.4% |
| `case … esac`, `;&` | Y | Y | `switch` | Y | Y | Y (`;;` only) | Y | 0.5% |
| `[[ ]]`, `=~` | N | Y (2742) | `~` | Y | Y | N | Y | 0.8% |
| `name() { }` | Y | Y | `fn` | Y | Y | Y | Y | 1.2% |
| `function name` | N | Y (2987) | N | Y | Y | N | Y | (in 1.2%) |
| arrays `a=(…)` `${a[@]}` | N | Y (1606, 2043) | Y (every var) | Y | Y | N | Y | 0.8% (`PIPESTATUS`) |
| `declare local export` as keywords | N | Y (2960) | N | Y | Y | ~ | Y | 0.1% |
| `time` | ~ | Y | N | Y | Y | N | Y | 0.05% |
| `coproc` | N | Y | N | N | Y | N | Y | 0% |
| `set -e` | Y | Y | N | Y | Y | ? | Y | <0.1% |
| `set -o pipefail` | Y (2024) | Y | N (list status) | Y | Y | ? | Y | <0.1% |
| parse-error position | — | line:col | line | line:col + token | line:col | char offset | line:col + caret | — |
| parser budget | — | — | — | tokens/depth/iterations | fuel | none | token length cap | — |

### 5. EXPERIMENT: 100 weighted agent commands through seven parsers

Method (EXECUTED). `corpus.jsonl` holds 100 commands written to mirror the e2 construct shares;
`corpus_stats.py` applies e2's own regexes and shows the fit: pipe 75% vs 74.3%, `&&` 44% vs
44.5%, `( )` 28% vs 27.9%, glob 24% vs 25.2%, `2>&1` 17% vs 16.4%, `>` 15% vs 14.2%, heredoc
12% vs 12.1%, `$X` 13% vs 12.1%, `<` 3% vs 4.8%, `for` 5% vs 4.6%, backticks 4% vs 4.4%, `$( )`
5% vs 3.7%, and one command each for `if case while function [[ $(( & <( {a,b}` (every one of
those is under 1.3% in e2). Median segments per command 3 (e2: about 4). `corpus-coverage.jsonl`
is the earlier, unweighted set that touches every construct at least once; `bad.jsonl` is ten
malformed inputs. Parsers: mvdan-sh in `LangBash` and `LangPOSIX` (Go, `mvdan_parse/`), bashkit
(`Parser::new(src).parse()`, built in the scratchpad with `default-features = false`), just-bash
(`parser.ts:parse`), lifo (`lex` then `parse`), just-bash-py, and Python `shlex.split` as a floor
(it only tokenizes; "admitted" means no unterminated quote). oils' `osh -n` was **not** run: the
dev tree needs a Python 2 interpreter that is not installed [NOT VERIFIED: `bin/osh` requires
`python2`]. Each parser ran in its own process with a 20 s timeout after the first run hung.

Results on the weighted corpus (`results/corpus.summary.md`):

| parser | admitted / 100 | refused |
|---|---:|---|
| mvdan `LangBash` | 100 | — |
| bashkit | 100 | — |
| just-bash | 100 | — |
| just-bash-py | 100 | — |
| mvdan `LangPOSIX` | 98 | 23 `${PIPESTATUS[0]}` ("arrays are a bash/mksh/zsh feature"), 73 `<( )` ("`<` must be followed by a word") |
| lifo | 84 | 12 here-documents ("Expected Word but got RedirectIn"), 3 subshells `( )` ("unexpected token '('"), `<( )`, and **one hang** (95: a subshell inside a `for` body, killed at 20 s) |
| shlex | 100 | — (a floor, not a parse) |

On the coverage corpus: bash-family 100, POSIX 96 (refuses `<( )`, `function`, `&>`, arrays),
lifo 93. On the malformed set (`results/bad.summary.md`): mvdan refuses 8 of 10 (it admits an
unterminated here-document at EOF, as bash does, and `'it''s'`, which is valid), bashkit 7,
just-bash-py 6, just-bash 3 (it admits a stray `)`, a trailing `|`, `&& &&` and `$((1 +))` — it
defers those to run time), lifo 4, shlex 1.

What the numbers say (INFERRED from EXECUTED): a bash-shaped grammar parses the whole of
realistic agent traffic; a POSIX-only grammar loses only the bash-isms that are already rare
(arrays, `<( )`, `function`, `&>`); the one peer without here-documents and subshells (lifo)
loses 16% of traffic — here-documents and `( )` are v1, not later. Counting the weighted corpus
by construct: 86 of 100 commands contain **no** control flow, function, arithmetic, `[[`, `&`,
`<( )` or array subscript and so parse under the v1 grammar proposed below (EXECUTED, the
regex check at the end of this study; the 14 others are ids 23, 30, 31, 44, 73, 80–84, 86, 94,
95, 99); adding `for` makes it 91. Against e2's
shares the same bound is at least 1 − (4.6 + 1.2 + 0.9 + 0.8 + 0.6 + 0.5 + 0.4 + 0.2 + 0.1)% ≈
91% if those constructs never overlap, higher if they do.

### 6. Error reporting

How each parser reports a syntax error (READ and EXECUTED on `bad.jsonl`):

| parser | shape | example for `if [ -f x ]; then echo yes` |
|---|---|---|
| mvdan-sh | `ParseError{Pos{line,col,offset}, Text, Incomplete}`; text names the construct and what must follow | `cmd:1:1: \`if\` statement must end with \`fi\`` |
| bashkit | `Error::Parse{message, line, column}`; bash's wording | `parse error at line 2, column 1: syntax error: unexpected end of file` |
| just-bash | `ParseException{line, column, token}` | `Parse error at 1:27: Expected FI, got EOF` |
| just-bash-py | same, prose | `Expected 'fi' to close if statement at line 1, column 27` |
| lifo | `ParseError(message, pos)` char offset | `Expected 'fi' but got ''` |
| brush | `ParsingNear(line, col)` / `ParsingAtEndOfInput`, optional miette caret | `syntax error at line 1 col 27` |
| OSH | status 2, line, caret under the token (`display/ui.py:109-134`) | — (not run) |
| nushell | typed variant per refused bash-ism with a replacement hint | "instead of '&&', use ';' or 'and'" |

mvdan's is the best LLM-facing text: it says which construct is open and what would close it, at
a line and column, and it separates "the input ended early" (`Incomplete`) from "the input is
wrong". bash's "syntax error near unexpected token `)'" (which bashkit copies) tells a model
nothing it can act on. nushell adds the one thing mvdan lacks: a refused-feature error that names
the alternative.

vfs already has the frame for this (READ, `src/vfs/results/kinds.py`): errors are a kind from a
hierarchical vocabulary plus a path-free detail; the renderer, not the producer, writes the
prose; an unknown child kind degrades to its parent (`kind_family`); `invalid` means "the caller's
input is wrong and the caller can fix it", `unrecognized` is emitted only by dispatch,
`unsupported` only by capability gates; `KIND_CONTRACTS` holds the phrase, retry class and hint.

## What this means for vfs

### The v1 grammar (ADR 1), named operator by operator

The shell is our own parser, single pass, no re-scanning, no `eval`, producing an AST that
dispatches to vfs verbs and installed programs. It admits a **static bash-shaped subset of POSIX
2024**. Everything below is admitted at v1; the list after it is refused with a classification.

Lexical. Blanks delimit; `#` to end of line is a comment; `\`+newline is a continuation; operator
tokens are longest-match: `|| && ;; ;& << <<- >> <& >& <> >| &> &>> | & ; < > ( )`; `n>` and
`n<` with a digit prefix. Reserved words recognised only at command start (POSIX §2.4 list plus
`[[ ]] function time`, reserved so a later slice can admit them without changing what today's
words mean).

Words. The quoting rule set (one table, adopted as written):

| Inside | What stays literal | What is special | Ends at |
|---|---|---|---|
| unquoted | everything else | `\` (next char literal), `$`, `` ` ``, `~` at word start, `* ? [` globs, `{a,b}`, the operators | blank or operator |
| `'…'` | every character | nothing; a `'` cannot appear | the next `'` |
| `"…"` | everything else, including blanks and globs | `$`, `` ` ``, and `\` only before `$ \` " \` and newline | the next unescaped `"` |
| `$'…'` | everything else | `\n \t \r \\ \' \xHH \ddd` C escapes; no expansion | the next unescaped `'` |

Expansions, in POSIX order: tilde (`~` and `~/` only; `~user` refused, there are no users in a
mount); parameter `$NAME ${NAME}` and the ten POSIX operators `${#p} ${p:-w} ${p:=w} ${p:?w}
${p:+w} ${p%w} ${p%%w} ${p#w} ${p##w}`; the special parameters `$? $# $@ $* $0-$9`; command
substitution `$(…)` and `` `…` `` (backticks are 4.4% of traffic, more than `$( )`; refusing
them would be a pure loss); then field splitting on the default `IFS` of unquoted expansion
results; then glob `* ? [ ]` and `{a,b}`, `{1..3}` brace expansion (vfs's `glob` verb already
speaks `{a,b}`, so the shell hands the pattern down unchanged); then quote removal. No
`$((…))` at v1.

Commands. Simple commands with assignment prefixes `NAME=word cmd` and bare assignments
`NAME=word`; pipelines `[!] cmd | cmd …`; lists with `;`, newline, `&&`, `||`, equal precedence,
left-associative, exactly as POSIX §2.9.3; `( list )` subshell as a scope for `cd` and
assignments; `{ list; }` group. Redirections: `< > >> >| <> n> n>> n< <&m >&m n>&m n<&m 2>&1`,
`&>` and `&>>` as sugar for `>f 2>&1`, and here-documents `<<WORD` / `<<-WORD` with the
quoted-delimiter rule and the terminator on its own line (OSH's rule). `$'…'`. Comments.

Refused at v1, each with its classification (the kinds are proposed children of existing kinds;
`kind_family` degrades them for an older peer):

| Construct | Kind | Detail the renderer gets |
|---|---|---|
| `if for while until case` and their closers, `function`, `name() {`, `[[ ]]`, `$(( ))`, `(( ))`, `select`, `coproc`, `time` | `vfs.unsupported.construct` | the construct's name and the slice that will admit it ("`for` loops arrive with control flow") |
| `<( )` `>( )`, `<<<`, `\|&`, `{var}>` | `vfs.unsupported.construct` | name + the v1 spelling (`cmd 2>&1 \| x` for `\|&`) |
| arrays `a=( )` `${a[i]}`, `${x/a/b}` `${x:1:2}` `${!x}` `${x@Q}`, extglob `@( )` | `vfs.unsupported.construct` | name |
| `&` (background) | `vfs.unsupported.construct` | "no background jobs; the call returns when the list has run" |
| `set` `shopt` `eval` `exec` `trap` `source` `.` as commands | `vfs.unrecognized` (dispatch: no such program) | the hint names the nearest vfs verb or says the option does not exist |
| malformed text: unclosed quote, unclosed here-document, `if` without `fi`, trailing `\|`, `&& &&`, stray `)` or `}` | `vfs.invalid.syntax` | line, column, what was open and what must follow it, `incomplete` true when input ended inside a construct |

### Staged growth plan

The brief's suggested order (v1 → pipes → control flow → functions → here-docs → arithmetic) is
corrected by the measurement: **pipes, lists, redirections and here-documents are v1**. Slices,
each one its own landing with its own spec-test file in the OSH/brush style (script in, expected
stdout and status out):

1. **v1 — the pipeline core** (above). Covers 86% of the weighted corpus (EXECUTED) and about
   91% by e2 shares (INFERRED). Ships with the verbs as builtins and the text programs.
2. **Control flow**: `for … in … do … done` (4.6%), `if/elif/else`, `while`, `until`, `case`
   with `;;` and `;&`, `break`/`continue` as keywords (OSH's choice, `known-differences.md:192`),
   `[ ]`/`test` as a program (not grammar), `[[ ]]` as grammar with `=~`. Raises coverage to
   about 97%.
3. **Functions and arithmetic**: `name() { }` and `function name { }`, `local`, `return`, `"$@"`
   positional parameters inside a function, `$(( ))` and `(( ))` with POSIX's signed-long
   semantics; `$'…'` is already in.
4. **The long tail**: `<( )` (needs the pipe payload ADR: a process substitution is a named
   stream), `<<<`, arrays and the bash parameter operators, `select`, `time` as a keyword.
   Each is admitted only when a measured corpus shows it above about 1%.

Never: `&` background jobs, `coproc`, `trap`, `eval` of a string, `exec`, `fc`/history,
`set -e`/`set -o` as modes (see the forks).

### The parse-error contract

A parse error is a `ResultError` with:

- `kind`: `vfs.invalid.syntax` (child of `vfs.invalid`; retry class `never`; phrase "Invalid
  syntax"; hint "Fix the command text at the reported position and resend it"), or
  `vfs.unsupported.construct` (child of `vfs.unsupported`; retry `never`; phrase "Unsupported
  construct"; hint "Rewrite without the named construct; see the detail for the v1 spelling").
- `path`: `None` — a parse error implicates no entry; `source` carries the locus.
- `data` (all `vfs.`-prefixed, absence means unknown): `vfs.line`, `vfs.column` (1-based, in the
  caller's string), `vfs.offset` (0-based code points), `vfs.construct` (the token or keyword at
  fault, e.g. `if`, `"`, `<<EOF`), `vfs.expected` (what would have closed it: `fi`, `"`, `EOF`),
  `vfs.incomplete` (`true` when the input ended inside an open construct — the here-document and
  unclosed-quote cases, which an agent fixes by appending, not by rewriting).
- The text rendering prints the offending line and a caret under the column (OSH's
  `_PrintCodeExcerpt`), because the model sees the string it sent, not a file.
- Exactly **one** error per call: the first, in source order, like every parser studied. The shell
  never runs a partially parsed command (OSH's "static parsing"; the no-shell rule needs the whole
  AST before any verb is called).
- A refused construct is detected at parse time, not when reached, so `echo hi; for …` fails before
  `echo` runs. This is the property that lets the host's execution-policy ADR reason about a
  command before anything executes (bashkit's `analyze()` is the same bet).

### What to adopt and what to reject

Adopt: mvdan-sh's AST shape and error wording; brush's one-predicate feature staging
(`non_posix_extensions_enabled` becomes our per-slice gate); OSH's static parse, the `$((`-is-
always-arithmetic rule and the here-doc-terminator-on-its-own-line rule; nushell's named
refusal-with-replacement errors; just-bash's parser budgets (input size, token count, depth,
iterations) as `vfs.budget_exhausted` facts; rc's list-valued status (below) and its "never
re-scan, never re-split" discipline.

Reject: rc's syntax as the surface; nushell's `out>`/`err>` respellings (they would break 16% of
traffic for no gain in a text pipe); bashkit's bash-worded errors; lifo's grammar (no here-docs,
no subshells, a parser that can hang); a dialect enum (`LangBash`/`LangPOSIX`) — vfs has one
dialect, grown by slice; `eval`, `source`, `exec`, `trap`, history — none has a meaning inside a
single `cli` call.

## Forks for the ADRs

1. **POSIX subset vs rc vs an own grammar?** Options: (a) a POSIX-2024 subset parsed by our own
   parser with named bash-isms admitted; (b) rc; (c) a new grammar (YSH-, nushell- or
   elvish-shaped). Lean: **(a)**. The measured traffic is 100% bash-shaped and the subset parses
   all of it that we choose to admit (EXECUTED); rc and a new grammar start at 0%. rc's ideas
   come in as semantics, not syntax.
2. **Which bash-isms at v1?** `$( )` — yes (POSIX anyway). Backticks — yes (4.4%, more than
   `$( )`). `{a,b}` — yes (0.9%, and `glob` already speaks it). `$'…'` — yes (POSIX 2024).
   `&>` — yes as sugar (zero cost, LLMs type it). `[[ ]]` — slice 2, with control flow (0.8%).
   Arrays — slice 4; the only measured use is `${PIPESTATUS[0]}`, which the status list on the
   envelope replaces. Lean: admit the first five at v1, refuse the rest with
   `vfs.unsupported.construct`.
3. **Does `set -e` exist?** Options: (a) a real `errexit` mode with POSIX's exemption list;
   (b) no mode — `&&` is the agent's errexit and a multi-line script stops at the first failing
   *list* only if the agent wrote `&&`; (c) errexit always on. Lean: **(b)** for v1. `set` is 6
   of 67,000 measured segments; errexit's exemptions are the single largest test file in brush
   (159 cases) and 71 cases in OSH; and a mode that changes the meaning of every later line
   inside one call is exactly the hidden state the static parser avoids. Revisit only if measured
   scripts grow long enough to need it.
4. **`pipefail`, or rc's status list?** Options: (a) POSIX default, status of the rightmost
   stage; (b) `pipefail` on by default; (c) rightmost status for `$?` **plus** every stage's
   status on the `Result` (`statuses: [1, 0]`, rc's list), so the renderer can flag "stage 1
   failed" under `uv run pytest 2>&1 | tail -5` without changing `$?`. Lean: **(c)**. It keeps
   `$?` bash-compatible for the model and makes the common masking bug visible in the text
   rendering and the MCP payload.
5. **Does `&` exist at all?** Options: (a) real background jobs with a job table (lifo); (b)
   parse-and-run-synchronously (just-bash, bashkit's "poll once"); (c) refuse at parse time.
   Lean: **(c)**. 0.2% of calls; the hermetic runtime has no process to detach and no terminal to
   return to; silently running it synchronously (b) lies to the model about what happened. The
   refusal names the fact: the call returns when the list has run.
6. **Static refusal vs run-time refusal of unsupported constructs?** Options: (a) refuse at parse
   time, nothing runs (OSH, mvdan); (b) parse everything bash-shaped and fail when reached
   (just-bash's choice for arithmetic errors). Lean: **(a)**; it is what makes the policy ADR's
   pre-execution analysis sound.
7. **One error or many?** Options: (a) first error only; (b) collect all. Lean: **(a)**, every
   parser studied does it, and a second error after a missing `fi` is usually noise.

## Sources

- POSIX.1-2024 (IEEE Std 1003.1-2024, Open Group Base Specifications Issue 8), Chapter 2 Shell
  Command Language, `https://pubs.opengroup.org/onlinepubs/9799919799/utilities/V3_chap02.html`,
  fetched 2026-10-15 in five slices (offsets 0, 8000, 25000, 60000, 100000, 160000, 200000).
  Sections 2.10.2 grammar productions were summarised by the fetch tool, not quoted verbatim
  [NOT VERIFIED: productions not seen in full].
- Tom Duff, "Rc — The Plan 9 Shell", `https://9p.io/sys/doc/rc.html`, fetched 2026-10-15
  (`https://doc.cat-v.org/plan_9/4th_edition/papers/rc` returned HTTP 402).
- `plan9port@b6564bd9` `src/cmd/rc/syn.y`, `lex.c`, `man/man1/rc.1`; `9front@a0806493` (DIRTY)
  `sys/src/cmd/rc/syn.y` for the diff only.
- `oils@bdc8364` `spec/*.test.sh` (counted), `doc/ysh-vs-shell.md`, `doc/known-differences.md`,
  `doc/parser-architecture.md`, `display/ui.py`, `spec/parse-errors.test.sh`.
- `mvdan-sh@0e8ea6f` `syntax/parser.go`, `syntax/nodes.go`, `README.md`.
- `brush@c495882` `brush-parser/src/{parser/mod.rs,parser/peg.rs,ast.rs,error.rs,tokenizer.rs}`,
  `brush-shell/tests/cases/**/*.yaml` (counted), `docs/reference/compatibility.md`, `README.md`.
- `nushell@818d4ac06` `crates/nu-parser/src/lex.rs`, `crates/nu-protocol/src/errors/parse_error.rs`.
- `elvish@26a8bd5` `pkg/parse/parse.go`.
- `PowerShell@db1d0a5` `src/System.Management.Automation/engine/parser/token.cs`.
- `just-bash@9ab0e0d` `packages/just-bash/src/{parser/*.ts,ast/types.ts,interpreter/*.ts,
  transform/serialize.ts}`, `packages/just-bash/README.md`, `THREAT_MODEL.md`.
- `bashkit@b7904a4` `crates/bashkit/src/{parser/*.rs,error.rs,interpreter/mod.rs}`, `README.md`.
- `just-bash-py@48d111c` `src/just_bash/parser/*.py`, `spec_test_results.txt`.
- `lifo@5a35d05` `packages/core/src/shell/{lexer,parser,interpreter,types}.ts`, `README.md`.
- vfs: `src/vfs/results/kinds.py`, `src/vfs/ops.py`; `experiments/e2/commands.md` and
  `experiments/e2/mine_commands.py` (the construct regexes reused in `corpus_stats.py` and
  `summarize.py`).
- Experiment outputs: `experiments/s1/results/{corpus,corpus-coverage,bad}.{mvdan,bashkit,ts,py}.jsonl`
  and the three `*.summary.md`, produced 2026-10-15.
