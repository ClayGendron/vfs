# Research Q5: what the bash suites cover, and what their parsers teach

Sources. Five reference repositories were cloned on 2026-11-21 as siblings of this checkout, shallow (`--depth 1`), each at its upstream default branch, and read only; no code was copied. `../brush` (github.com/reubeno/brush) at `c7748dd` of 2026-11-19, MIT. `../bashkit` (github.com/everruns/bashkit) at `290ebb0` of 2026-11-20, MIT. `../mvdan-sh` (github.com/mvdan/sh) at `95154f9` of 2026-11-18, BSD-3-Clause. `../oils` (github.com/oils-for-unix/oils) at `d114978` of 2026-11-02, Apache-2.0. `../just-bash` (github.com/vercel-labs/just-bash) at `ec5ab76` of 2026-11-20, Apache-2.0; its vendored copy of the Oils cases carries its own Apache-2.0 text. All counts below were taken from these commits with `grep`/`awk`; a figure quoted from a project's own document says so. Spot checks of bash behaviour were run on the host's bash 5.2.21, which is not the 5.3 referee the spec pins; they are indicative only.

Correction to the spec's "Not checked": the spec counted Oils at `bdc8364` (223 files, 72,692 lines, 3,966 cases). At `d114978` the suite holds 223 files, 72,733 lines and 3,971 cases. The split is 2,788 cases in 135 files that compare against bash, 1,162 in 83 YSH or Hay files, and 21 in 5 files that compare against neither.

## R5.1 How each suite is structured

### Summary table

| Project | Case format | Where the expected answer comes from | Known failures | Size |
|---|---|---|---|---|
| Oils | `#### name`, script, then `## stdout:` / `## STDOUT: … ## END` / `## stdout-json:` / `## status:` / `## stderr:`; per-shell overrides `## OK bash …`, `## N-I bash …`, `## BUG bash …` | Hand-written canonical answer (the one Oils thinks ideal), plus hand-written per-shell overrides, checked by running every listed shell | One integer per file, `## oils_failures_allowed: N`; no per-case list | 3,971 cases, 2,788 compared with bash |
| brush | YAML: `name`, `stdin` or `test_files` + `args`, optional `env`, `ignore_stderr`, `ignore_whitespace`, `min_oracle_version`, `known_failure`, `skip` | Live oracle: each case runs under the host's bash and under brush at test time; nothing is recorded. Only 203 brush-specific cases carry inline `expected_stdout` | Per case `known_failure: true`, often with a comment naming the cause; a known failure that passes is reported as "unexpected success" and fails the run | 3,658 compat cases in 122 files, 872 known failures; 207 brush-only cases |
| bashkit | `### name`, script, `### expect`, stdout, `### end`; `### exit_code: N`, `### skip: reason`, `### bash_diff: reason` | Hand-written, then checked against host bash by `just check-bash-compat`; three further scoreboards use recordings | `### skip:` (29) for gaps, `### bash_diff:` (229) for deliberate or host differences | 3,975 cases in 266 files, 1,053 of them imported from BashBox |
| mvdan/sh | Go tables: `fileTest([]string{inputs…}, langFile(AST))` for the parser, `errCase(input, langErr(msg))` for errors, `{in, want}` pairs for the interpreter | Hand-written; parser inputs are confirmed by `bash -n` (and dash, mksh, zsh), interpreter pairs by running bash 5.3 in `TestRunnerRunConfirm` | Inline markers in the expected string: `#IGNORE reason` (162) skips the bash confirm, `#JUSTERR` (214) asks bash only to fail | 724 parser groups, 423 error cases, about 1,886 + 125 interpreter pairs |
| just-bash | Oils' format, vendored (136 files, 2,728 cases), plus JSON fixtures for program comparison | Oils' answers for the spec cases; for the comparison tests, bash run once in record mode and saved to JSON (981 entries in 57 fixture files) | `## SKIP (reason):` lines inserted into the vendored files (246), 27 whole files skipped (374 cases); a SKIP case that passes fails with "UNEXPECTED PASS" | about 2,354 Oils cases run, about 2,207 expected to pass |

### Oils in detail

A case is code fed on standard input to `$SH`. The unqualified assertion is the answer Oils considers right, which is often its own (OSH) answer. Bash's actual answer is the unqualified one unless a qualifier names bash: `OK` (acceptable difference), `N-I` (not implemented), `BUG` (a verified bash bug). A runner that wants bash's answer must apply the bash-qualified overrides. Of the 2,809 shell cases, 360 carry at least one bash override (484 override lines: 191 OK, 121 N-I, 172 BUG). Status defaults to 0 when unasserted; standard error is checked only when asserted.

Oils compares against bash 5.2.21 (`test/spec-bin.sh`). Cases lean on helper programs: 335 call `argv.py`, 42 `printenv.py`, 9 `stdout_stderr.py`, 4 `read_from_fd.py` (all Python 2); 484 re-invoke `$SH` and 135 use `$TMP`; 41 call `sleep`. A harness without a process model has to shim these, as bashkit does in bash.

The known-failure record is a per-file count (`oils_failures_allowed`), 149 across the shell files, so a fix in one case can hide a regression in another.

Shell cases per area (files whose `compare_shells` lists bash, plus the five comparing to none):

| Area | Cases | Files |
|---|---:|---:|
| Builtins and options (`builtin-echo` 27, `builtin-printf` 63, `builtin-read` 64, `builtin-getopts` 31, `builtin-set` 24, `builtin-vars` 41, `builtin-eval-source` 23, `builtin-cd` 30, `builtin-type-bash` 31, `sh-options` 39, `xtrace` 19, `introspect` 13, `serialize` 10, others) | 534 | 23 |
| Grammar, control flow, errexit (`errexit` 36, `errexit-osh` 35, `pipeline` 26, `background` 27, `loop` 29, `case_` 13, `shell-grammar` 38, `parse-errors` 27, `command-sub`-adjacent grammar, `paren-ambiguity` 9, `func-parsing` 15, `strict-options` 17, `exit-status` 11, `fatal-errors` 5) | 369 | 22 |
| Arrays and assignment (`array` 78, `array-assoc` 42, `array-sparse` 40, `array-literal` 19, `assign` 48, `assign-extended` 39, `append` 20, others) | 338 | 14 |
| Parameters and operators (`var-op-test` 37, `var-op-strip` 29, `var-op-patsub` 28, `var-op-slice` 22, `var-op-bash` 27, `var-sub-quote` 41, `vars-special` 42, `var-ref` 31, `nameref` 32, others) | 312 | 13 |
| Interactive and invocation (`builtin-completion` 51, `prompt` 33, `sh-usage` 24, `interactive` 18, `builtin-history` 17, `builtin-fc` 14, `builtin-bind` 9) | 168 | 9 |
| Word expansion and substitutions (`brace-expansion` 55, `word-split` 55, `command-sub` 30, `process-sub` 9, `word-eval` 8, `command-sub-ksh` 4) | 161 | 6 |
| Bug reports and idioms (`bugs` 29, `ble-idioms` 26, `toysh-posix` 23, blogs, `nix-idioms`, `zsh-*`, others) | 158 | 19 |
| Conditionals (`dbracket` 49, `builtin-bracket` 52, `regex` 37, `bool-parse` 8) | 146 | 4 |
| Traps, signals, processes (`builtin-trap` 38, `builtin-trap-bash` 23, `builtin-trap-err` 23, `builtin-process` 26, `builtin-kill` 20) | 130 | 5 |
| Globs (`glob` 39, `extglob-match` 29, `extglob-files` 23, `globignore` 18, `glob-bash` 8, `nocasematch-match` 6, `globstar` 5) | 128 | 7 |
| Arithmetic (`arith` 74, `arith-context` 16, `dparen` 15, `for-expr` 9, `arith-dynamic` 4, `let` 2) | 120 | 6 |
| Redirections and here-documents (`redirect` 41, `here-doc` 36, `redirect-command` 23, `redirect-multi` 13, `redir-order` 5) | 118 | 5 |
| Quoting, tilde, bytes (`quote` 35, `nul-bytes` 16, `tilde` 14, `unicode` 7, `whitespace` 5, `comments` 2) | 79 | 6 |
| Alias | 48 | 1 |
| Total | 2,809 | 140 |

Bash-specific files (compared with bash alone): 21 files, 396 cases. They are `array-assoc` 42, `array-literal` 19, `builtin-bash` 13, `builtin-bind` 9, `builtin-completion` 51, `builtin-fc` 14, `builtin-history` 17, `builtin-trap-bash` 23, `builtin-type-bash` 31, `glob-bash` 8, `globignore` 18, `history-expand` 1, `interactive` 18, `introspect` 13, `nix-idioms` 6, `nocasematch-match` 6, `prompt` 33, `sh-options-bash` 9, `type-compat` 7, `var-op-bash` 27, `var-ref` 31. About 160 of those 396 are interactive features out of this spec's scope.

The files where bash most often diverges from Oils' canonical answer, so that a reader taking the unqualified line would take a wrong answer, are `errexit-osh` (20 cases), `array-sparse` (19), `assign-extended` (16), `array` (15), `assign` (12), `strict-options`, `sh-options`, `arith` (11 each), `builtin-umask`, `brace-expansion` (9 each), `xtrace`, `array-assoc` (8 each).

### brush in detail

Cases by directory: `builtins/` 1,466 in 50 files (344 known failures), top-level files 1,349 in 32 (407), `options/` 376 in 18 (56), `word_expansion/` 227 in 9 (36), `compound_cmds/` 176 in 11 (21), `patterns/` 64 in 2 (6). The largest files are `nameref` 230, `builtins/declare` 163, `options/set-e` 160, `builtins/trap` 124, `here` 106, `arguments` 100, `ifs` 97, `builtins/read` 85, `builtins/printf` 83, `extended_tests` 82, `errors` 82, `word_expansion/params` 79. The harness (`brush-test-harness`) runs each case in a fresh temporary directory under bash `--norc --noprofile` and under brush, and compares standard output, standard error (unless `ignore_stderr`, set on 664 cases), exit status, and the directory's files afterwards. The README states 2,500+ cases and about 470 known failures; the tree at `c7748dd` holds 3,658 and 872, of which 207 are in the newly added `nameref.yaml`. CI runs on Linux, macOS and six distribution containers, each with that platform's bash, which `min_oracle_version` (46 uses) gates. Being live, a run drifts with the runner's bash; the spec's recorded corpus does not.

### bashkit in detail

Four layers measure bash parity. The in-repo spec cases (3,975, hand-written in an Oils-like format, checked against host bash). A bash-oracle scoreboard of 106 whole scripts recorded once from bash 5.2: two runs in different empty directories must agree and the output must hold no host path before a recording is kept; it scores `match` (status and stdout, 90/106) and `strict` (also stderr text, 69/106), and a `floor.txt` fails the run when either drops. A competitor-regressions corpus imports reproducers of bug fixes found in peer interpreters each quarter, as JSON with the upstream commit, the locked output and a classification (`pass`, `bug` fixed, or `intentional_divergence` naming a limitation row). And a grammar-driven differential fuzzer (proptest) that compares against real bash, 50 cases by default and 1,000 deep, excluding `pwd`, `wc` and filesystem operations. The Oils run is described under R5.5.

### mvdan/sh in detail

The parser is tested by AST: each `fileTest` lists several spellings that must parse to one tree, and every spelling is fed to `bash -n` (when bash 5.3 is installed) to confirm bash accepts it; each `errCase` is confirmed to fail in bash, and `flipConfirm` (66 uses) marks the inputs where bash accepts what mvdan refuses. A dedicated test, `TestParseNestingLimit`, drives twelve shapes to a nesting of 1,000 (must parse) and 10,001 (must fail with "nesting is deeper than 10000 levels"). The interpreter tests are `{in, want}` pairs with hand-written output in which a trailing `exit status N` stands for the status; `TestRunnerRunConfirm` runs each pair through bash 5.3 and fails on a difference unless the pair says `#IGNORE` (the commonest reasons: `declare -p` quoting 43, "bash has no limit" 32, random or time values). The 12,627-call corpus of the earlier study was measured against this parser.

### just-bash in detail

The Oils cases were vendored in December 2025 and edited in place: 246 `## SKIP` lines were inserted, and 27 files are skipped whole by the runner. The most common skip reasons are interactive invocation (48), `history` (29), shell invocation (15 + 5), `python2` helpers (14), and "alias expansion not implemented - parsing happens before execution" (14, all of `alias.test.sh` that is not passing). The program-comparison fixtures record bash once (`RECORD_FIXTURES=1`), may be `locked` against re-recording, and replay without bash. Editing a copy of an upstream suite in place is the maintenance cost spec decision 13 avoids.

## R5.2 Parser architecture lessons

### The shape of each parser

- Oils: a hand-written recursive-descent command parser (`osh/cmd_parse.py`, 2,889 lines) over a word parser (`osh/word_parse.py`, 2,378) over a lexer with explicit lexer modes (`ShCommand`, `DQ`, `SQ`, `Arith`, `DBracket`, `BashRegex`, `Backtick`, `VSub`, `ExtGlob`, `FuncParens`…) generated from regular expressions (`frontend/lexer_def.py`). Arithmetic is a Pratt (TDOP) parser whose tokens are words (`osh/arith_parse.py`, `osh/tdop.py`), so `$x` and `${a[i]}` inside arithmetic are word parts. `[[ ]]` is a small recursive-descent parser over words (`osh/bool_parse.py`: Expr, Term, NegatedFactor, Factor).
- mvdan/sh: one hand-written recursive-descent parser (`syntax/parser.go`, 3,592 lines, plus `parser_arithm.go`) with a byte-level lexer whose behaviour is switched by a `quote` state (`hdocBody`, `dblQuotes`, `paramExpRepl`, `arithmExpr`, `testExpr`, `switchCase`, `arrayElems`…).
- bashkit: a hand-written recursive-descent parser (14,160 lines across `parser/`), with a separate lexer.
- brush: a hand-written tokenizer (2,729 lines) feeding a PEG grammar (`rust-peg`) for commands; words stay raw text in the AST (`Word { value: String }`) and are parsed by a second PEG grammar at expansion time, memoised by an LRU cache of 64 entries.
- just-bash: a hand-written recursive-descent parser in TypeScript split by concern (lexer, command, compound, conditional, arithmetic, expansion and word parsers, 10,352 lines).

### Here-documents

- The robust pattern, used by Oils and mvdan/sh: on `<<WORD` push a pending redirect onto a list; when the command parser next consumes a newline token, read the bodies of all pending redirects in order from the following lines, then clear the list. Oils keeps `pending_here_docs` in the command parser and fills each `HereDoc` node's `stdin_parts` on the newline (`_ParseHereDocBody`). The delimiter is quote-removed statically; if any character of it was quoted (`'EOF'`, `"EOF"`, `\EOF`, `E"O"F`), the body is literal lines; otherwise the body lines are re-lexed in a here-document mode as a double-quoted-like word (`$`, backquote and backslash before `$`, `` ` ``, `\` or newline are special; `"` is literal).
- Nested constructs need their own pending list. mvdan/sh records `buriedHdocs`, the length of the pending list when a nested parse starts (`preNested`), so a newline inside `$(...)` reads only the bodies opened inside it, and the outer ones stay pending for the outer newline. Brush handles `$(cat <<EOF)` (the body after the line holding the `)`) by setting the rest of the line aside, reading the bodies, and putting the rest back.
- bashkit reads the body the moment it sees the delimiter, by scanning ahead in the lexer and re-injecting the rest of the line; its own threat note (TM-DOS-064) charges each re-injected character because repeated here-documents on one line otherwise make the work quadratic. The pending-list design has no such cost.
- Brush's known failures in this area are a list of edge cases to record: the body's `)` inside a command substitution inside arithmetic; an unterminated `${` in a body; a here-document opened in a command substitution followed by a line continuation; a body whose substitution does not parse (bash fails the command); `$'…'` as the delimiter; a body ended by end of input (bash warns and accepts); a body closed on the line that holds the tag followed by the substitution's `)`.

### `$(...)`, case patterns and nested quotes

- The parser must parse the body of `$(...)` with the command parser, recursively, not find its end by counting parentheses. Oils does this: on `$(` it creates a child command parser that shares the lexer and the line reader, and pushes a lexer hint translating `)` to an end-of-substitution token, so the `)` ending a case pattern is consumed by the case grammar before the hint can fire. mvdan/sh does the same through its recursive descent. Brush finds the body by tokenizing and counting parentheses, and its compat suite carries the consequence as known failures (issue #1052): `echo "$(case x in x) echo matched;; esac)"` closes the substitution at the pattern's `)`.
- Backquotes are the opposite: their body is text first. Oils collects the body, removing the backslash from `` \` ``, `\\`, `\$` (and `\"` only when the backquotes are inside double quotes), then parses that string with a fresh parser. Nested quoting inside `$(...)` needs no special case once the body is parsed by the command parser: double quotes inside `"$(echo "a b")"` open a new quoting context.
- Bash 5.2+ parses a command substitution's body at parse time (a syntax error inside it is a syntax error of the whole command), and bashkit raises a failed `$(...)` body as a whole-script error for that reason. Brush defers the parse to execution, so such an error surfaces late.

### `$((…))` against `$( (…) )`, and `((…))` against `( (…) )`

- Bash decides by the close: `$((` or `((` whose matching close is `))` (adjacent) is arithmetic; one closed by `) )` is a command substitution or nested subshell. Oils' `paren-ambiguity` file pins it: `(( echo 1 … ) )` runs commands, the same text closed by `))` is a parse error (status 2), and real scripts write `((grep …) | head)`, `((pkg-config …) || (pkgconf …))`, `$((which a || echo b)2>/dev/null)`.
- Oils looks ahead on the current line for a matching `))` (`LookAheadDParens`) for `((`; for `$((` it commits to arithmetic. mvdan/sh lexes `$((` and `((` greedily as arithmetic and asks the writer to put a space. bashkit and just-bash scan the body counting `((`/`))` and single parentheses before choosing. A hand-written parser in Rust can do bash's rule exactly: on `((` or `$((`, save the position, try to parse arithmetic up to `))`; on failure, rewind and parse as `(` + `(`. Rewinding needs a lexer whose position can be saved and restored; here-document bodies pending at that point make rewinding across a newline unsafe, so the attempt should stop at the first newline token and commit to the command reading.

### `[[ ]]`

- Inside `[[ ]]` the lexer changes mode: no word splitting and no globbing of operands; `<` and `>` are string comparisons, not redirections; `(` `)` group; `&&` `||` `!` are operators; an unquoted right side of `==`/`!=` is a pattern, and a quoted part of it is literal. Oils uses lexer mode `DBracket` and `bool_parse.py`.
- The right side of `=~` needs its own lexer mode (`BashRegex` in Oils): `(`, `)` and `|` are literal regex text there, spaces are allowed only inside parentheses, quoted parts are matched literally, and the operand cannot start with `)`.
- Unary versus binary is decided by position and by the operator table (`-f x` against `x -eq y`); `[[ -f ]]` with one word is a string test of `-f`.
- The `test`/`[` builtin is the same grammar evaluated over already-expanded strings at run time, with POSIX's argument-count rules (one, two, three, four arguments); Oils reuses the parser with `ParseForBuiltin`. `test` cannot be parsed ahead of time because its words come from expansion.

### Arithmetic

- Bash's arithmetic is dynamic in three ways a static parse must model. Text expansion happens first: `x='1 + 2'; echo $(( $x * 3 ))` is 7, because `$x` expands to text before the expression is parsed (verified on bash 5.2). A bare name is evaluated recursively as an expression: `$(( x * 3 ))` with the same `x` is 9. And double-quoted text inside arithmetic is re-parsed (`$(( "1 + 2" * 3 ))` is 7), while single quotes are an error. Oils parses the expression statically and falls back to a run-time parse of expanded text only for those forms (`arith-dynamic.test.sh`); bashkit keeps the arithmetic as a string in the AST (`ArithmeticExpansion(String)`) and parses it at evaluation.
- The design that serves both a whole AST and bash's semantics: parse arithmetic statically into an expression tree whose leaves are words; at run time, if a leaf contains an unquoted expansion that produced operator characters, or a variable's value is not a plain integer, parse that text with the same arithmetic parser under the same depth budget. Bash caps recursive evaluation at 1,024 levels ("expression recursion level exceeded"); brush mirrors that cap for variable dereference chains (`MAX_VARIABLE_DEREF_DEPTH = 1024`); bashkit caps recursive arithmetic at 50 levels and so fails Oils' `ble-idioms #recursive arith`.
- `a[$(cmd)]` and `$(( a[$(cmd)] ))` read from variable data run commands in bash. bashkit refuses this on purpose (L-ARITH-001) and counts the cases as misses; a host-mediated shell would at least route those commands through the host as requests.
- Integers are 64-bit two's complement with wrapping (`$(( 2**63 ))` wraps), shifts are masked like C on x86-64, division by zero is an error that aborts the current command, and `010` is octal, `0x10` hexadecimal, `64#z` base 64. just-bash skips seven Oils cases on 64-bit integer edges because JavaScript lacks them.

### Aliases

- Bash expands aliases while reading, on the first word of a simple command and after an alias whose value ends in a blank, and only when `expand_aliases` is on, which it is not by default in a non-interactive shell. Because bash reads and parses one top-level command at a time, an alias defined on a line applies from the next line, not later on the same line (`alias sayhi='echo hello'; sayhi same line` fails; the next line works: Oils `alias.test.sh`).
- Oils expands at the end of `ParseSimpleCommand` and re-parses the alias text with `ParseCommand`; it fails the cases where an alias holds an opening keyword or brace (`alias LBRACE='{'`) or several lines. mvdan/sh expands at run time on the argument list, so an alias value that is not plain words cannot work. just-bash marks 14 alias cases unimplementable because it parses before executing. bashkit parses the whole script but, before each top-level command, compares the parse options (the alias table when `expand_aliases` is on, and `extglob`) with those used, and re-parses the rest of the source when they changed; this passes every Oils alias case but 1 or 7 depending on the run.

### Reserved words, `case` and function definitions

- A reserved word (`if then else elif fi do done case esac while until for in select function time { } [[ ]] !`) is recognised only as the first word of a command, after a separator, or in the positions the grammar names (`in` after `for name` or `case word`, `do` after the `for` list); elsewhere it is a plain word (`echo if fi`). bashkit's design note states the rule; Oils carries it through `CommandKind`/`CommandId` on each word.
- `}` closes a group only in command position; `{` must be followed by a blank; `{a,b}` is a word. `!` negates only a pipeline at command start.
- `case` patterns: an optional leading `(`, alternatives split by `|`, the pattern words read in a mode where `)` ends the list; terminators `;;`, `;&` (fall through to the next body), `;;&` (test the next pattern). `esac` is recognised as the first word of a pattern list, and `case x in esac) …` is legal only in the forms bash allows.
- Function definitions: `name() compound-command [redirections]`, `function name compound-command`, `function name() …`; the body is any compound command, not only `{ }`, and redirections after the body apply on each call.

### Process substitution, brace expansion, extglob

- `<(…)` and `>(…)` are word parts parsed like `$(…)`, valid where a word is, including after redirection operators (`< <(cmd)`). brush handles them only in simple commands (a known failure).
- Brace expansion is a separate pass over a parsed word. Oils detects it on the word tree after parsing (`osh/braces.py`), mvdan/sh in `SplitBraces` (a malformed brace is left literal; nesting deeper than the parser's limit is left literal too), brush in a PEG rule. Doing it at parse time on the word tree lets a host see the expansions statically, and lets the size check of spec decision 7 run before allocation, because the count of `{1..N}` is known from the tree.
- Extended globs `@( ) *( ) +( ) ?( ) !( )`: Oils parses them statically as a word part (`ExtGlob`), with arms that are words, so `@("${u:-a  b}")` keeps its quoting. Bash only lexes them when `extglob` is on when the command is read: `shopt -s extglob; echo @(a|b)` on one line is a syntax error (verified), while on two lines it works. bashkit parses with the `extglob` option of the moment and re-parses the remainder when it changes. `!(` collides with `! (subshell)`, which is why the option must be known.

### Depth limits and stack overflow

- mvdan/sh caps nesting at 10,000 (`maxNesting`), counted by `enterNode` on every statement, word and expression level; Go grows goroutine stacks, so the depth is safe in Go but not in Rust or WebAssembly. Its twelve test shapes are a ready list for this project's depth law: nested `(`, nested function bodies, nested `$(`, nested `${a:-`, long `&&` chains, long pipelines, long `elif` chains, nested arithmetic parentheses, chained `a=` assignments, long `1+1+…` chains, repeated `!` in `[[ ]]`, long `&&` chains in `[[ ]]`.
- just-bash: `MAX_PARSER_DEPTH = 200`, `MAX_TOKENS = 100,000`, `MAX_INPUT_SIZE = 1,000,000`, `MAX_PARSE_ITERATIONS = 1,000,000`; the first three are the defaults this spec adopts (decision 17). Its depth test drives `$(( !!!…1 ))`, `$(( ((…1)) ))`, `[[ ! ! … x ]]` and `[[ ( ( … x ) ) ]]`.
- bashkit: parser depth 100 hard-capped, parser operations 100,000, parser timeout 5 s, substitution depth 32, subshell depth 32. Its function depth has a hard ceiling of 16, because "100 nested interpreter frames overflow a 2 MiB host stack before the configurable counter fires" (TM-DOS-020): its executor recurses through boxed futures. On native targets it grows the stack on demand with `stacker` (512 KiB red zone, 4 MiB segments); its own note says `stacker` cannot switch stacks on WebAssembly, so there only the caps protect it.
- brush: the tokenizer bounds its own recursion at 32 nested expansions (`MAX_EXPANSION_NESTING`), and its comment warns that later passes over the word recurse as deeply with frames over 100 KiB per `${…}` level in an unoptimised build. Its word grammar memoises `${…}` and brace rules because a failure inside one of about 20 alternatives is otherwise rediscovered by each, "taking time exponential in the nesting depth".
- Oils sets no parser limit; it relies on Python's recursion error (and the C++ build's stack).
- The lesson for this project: a depth budget checked on entry to every recursive parse function is necessary but not sufficient. Chains that a parser builds iteratively (`a && b && c`, `a | b | c`, `1+1+…`, `elif`) still yield trees as deep as the chain if the node type is binary, and the executor and every later walk then recurse over them. Either the AST stores chains as flat lists (an and-or list as `Vec<(op, pipeline)>`, a pipeline as `Vec<command>`, `elif` arms as a `Vec`), or the depth budget counts those levels too.

## R5.3 Execution-model lessons

### Words and expansions

- Oils' word is a list of parts (`CompoundWord`) with parts `Literal`, `EscapedLiteral`, `SingleQuoted`, `DoubleQuoted` (holding parts), `SimpleVarSub`, `BracedVarSub` (name, prefix op, index, suffix op whose argument is itself a word), `CommandSub` (a command tree), `TildeSub`, `ArithSub` (an expression tree), `BracedTuple`/`BracedRange` (brace expansion), `ExtGlob` (arms of words), `BashRegexGroup`. Evaluation produces a list of pieces each tagged quoted or unquoted, then splits only unquoted expansion output on IFS, then globs only unquoted pattern characters, then removes quotes. mvdan/sh's `WordPart` set is the same idea (`Lit`, `SglQuoted`, `DblQuoted`, `ParamExp`, `CmdSubst`, `ArithmExp`, `ProcSubst`, `ExtGlob`, `BraceExp`); just-bash's too, with a `GlobPart`.
- bashkit flattens: a `Word` holds parts plus a word-level `quoted: bool` and `has_unquoted_glob: bool`, and parameter-operator operands are kept as strings re-parsed later. Its open skips name the cost: "TODO quoted/unquoted word joining at split", "word splitting in default values". brush keeps the word as raw text until expansion. Both lose the per-part quoting a tree keeps.
- Quoting must be a property of each piece of output, not of the word: `"$a"*.txt` splits nothing and globs the `*`; `${v:-"d e"}` unquoted splits into two fields while the inner quotes protect against globbing (verified: `wc -w` gives 2); `"$@"` inside a word joins its first and last element to the surrounding text (`"-$@-"`); an empty unquoted expansion vanishes but `""` stays an empty field.

### `set -e`

- Oils and brush both model errexit as a context flag pushed by the constructs that disable it: the condition of `if`, `elif`, `while`, `until`; every command of an `&&`/`||` list but the last; a pipeline prefixed by `!`. Oils pushes `ctx_ErrExit` with the token that disabled it; brush passes `suppress_errexit` in its execution parameters. The flag is inherited by everything called inside, functions included: `f || true` runs all of `f` with errexit off, and `if f; then` likewise (verified: `in-f` printed twice).
- A command substitution does not inherit errexit unless `inherit_errexit` is set (verified: `x=$(false; echo sub)` gives `sub`). `local x=$(false)` and `export x=$(false)` mask the status (the status is the builtin's, 0); `x=$(exit 4)` keeps it (verified: 0 and 4). `(( i++ ))` with `i=0` returns 1 and ends a script under `set -e` (verified). A subshell's failure ends the parent only when the subshell's own status is non-zero after its errexit runs.
- brush's known failures here: an `&&` list as the last command of a `for` loop, division by zero in `(( ))`, `$(( exit 5 ))` parsed as arithmetic. just-bash lists "errexit in compound commands" as the top pending item of its priority list.

### Pipelines when stages are builtins

- brush runs every stage in a cloned `Shell` (`shell.clone()`) as an asynchronous task joined by OS pipes, except the last stage when `lastpipe` is on (and job control off); `PIPESTATUS` is set when all stages are waited for. mvdan/sh runs each stage in a goroutine on a copied runner (`r.subshell`) with an `io.Pipe`, and the last stage in a subshell too unless `lastpipe`.
- bashkit polls all stages concurrently on one task with no threads; a pipe is a shared byte buffer of 4 KiB (`PIPE_CAPACITY`), chosen below Linux's 64 KiB so that an endless producer into `head` wastes little of the command budget; a write to a closed reader becomes status 141. Its note records the one visible difference: a producer that writes between 4 and 64 KiB into a reader that quits early exits 141 where bash usually exits 0.
- just-bash runs stages one after another, passing each stage's whole output as the next stage's input string. That cannot stop `yes | head -1` or `while :; do echo; done | head -1`, and interleaves standard error by stage rather than by time. brush carries "Endless producer into head" as a known failure for the same reason in one path.
- For a machine with one `step` entry and keyed requests, the bashkit shape fits: stages are coroutines inside the machine, a pipe is a bounded byte queue counted in the memory budget, a stage blocked on a full or empty queue yields to the next runnable stage, and a stage that needs the host issues a request with its stage key. Bounded queues make the output independent of chunk boundaries only if no builtin's output depends on how much it could write at once, which the spec's chunk-boundary law then tests.

### Subshell state

- Every project copies state for a subshell, a pipeline stage, `$(…)` and `( … )`. brush clones the whole `Shell`; mvdan/sh copies fields by hand and puts variables behind a copy-on-write overlay (`overlayEnviron` with `shared` and `sharedParent` flags, copied on first write); bashkit forks with copy-on-write shared state and charges the owned fork fields to its memory budget before forking (`pipeline_admission.rs`).
- A copy-on-write overlay is the right fit for a memory-counted machine: a subshell costs its writes, not the size of the parent's variables, and the budget can charge each write.
- State a subshell must not leak: variables, functions, aliases, options, the working directory, traps (reset except ignored signals; the `EXIT` trap of a subshell runs at the subshell's exit, a brush known failure), `$_` (just-bash saves and restores it around pipelines), and `$BASHPID` changes while `$$` does not.

### `$?` and `PIPESTATUS`

- `$?` is the status of the last pipeline, which is its last stage's status, or with `pipefail` the rightmost non-zero status; `!` inverts it. `PIPESTATUS` holds every stage's status after a pipeline (verified: `false | true` gives `1 0`) and is overwritten by the next command, including a simple command (`PIPESTATUS` is then a one-element array). bashkit seeds `PIPESTATUS` at start where bash leaves it unset (an Oils miss), just-bash notes the same difference.
- A command's status after an expansion failure, an assignment-only command (`x=$(exit 3)` makes `$?` 3), `return` without an argument (the last status), and a special builtin's error in a non-interactive shell (fatal only in POSIX mode; in default bash the script goes on, verified for `shift 5 6` at status 1, `set -o bogus` at status 2 and a readonly assignment at status 1) are each a case to record.

### `read` from pipes

- `echo hi | read x` leaves `x` unset in the parent (verified: `[]`), because the last stage runs in a subshell unless `lastpipe` is on. `while read line; do …; done < file` with a body that also reads standard input shares one input stream: bash reads a pipe byte by byte so that it never consumes past the delimiter, and seeks back on a regular file. brush's `read` reads one byte at a time; just-bash threads a shared standard-input position (`groupStdin`) through pipeline stages and compound commands so that `{ read a; cat; } < file` gives `cat` the rest.
- In this machine a redirected or inherited standard input is a host stream with a position. `read` must consume exactly up to and including its delimiter (`-d`, `-n`, `-N`), and a following builtin or program must see the remainder; the request for "read until delimiter" belongs in the request set, or the machine must hold a look-ahead buffer per stream and count it.

## R5.4 Where each reports the most failures (hard spots)

- Oils' own OSH (allowed failures by file): `builtin-history` and `array-assign` 9 each, `prompt` 8, `var-op-bash` and `nameref` 7 each, `assign-deferred` and `ble-idioms` 5 each, `globstar`, `command-sub-ksh`, `builtin-bash` 4 each.
- brush (known failures by file): `nameref` 207 of 230, `builtins/declare` 86 of 163, `signals` 51, `builtins/trap` 35, `arguments` 30, `errors` 23, `options/extdebug` 19, `builtins/compgen` 19, `options/functrace` 17, then `params`, `prompt`, `history`, `export` 15 each, `kill` 13, `path_search`, `for` (break and continue counts and scoping, 12), `wait`, `printf` 12, `here` 11, `set`, `read`, `jobs` 11. Its document adds about ten IFS edge cases (non-whitespace IFS, empty fields, mixed separators), about eight `printf` specifiers, division by zero under errexit, and complex alias expansion.
- bashkit's first Oils run (74.2%) missed most in `builtin-completion` 34, `array` 25, `prompt` 25, `builtin-trap-bash` 19, `globignore` 16, `word-split` 16, `var-ref` 15, `builtin-cd` 14, `alias` 13, `dbracket` 13, `builtin-type-bash` 12, `sh-options` 11, `vars-special` 11, `array-assign` 10, `array-sparse` 10, `var-sub-quote` 10, `array-assoc` 9, `builtin-read` 9, `builtin-trap` 9, `introspect` 9, `nul-bytes` 9. Its remaining 74 misses at 97.3% are host files and processes (37), out of scope by design (10), bytes that are not UTF-8 (8), bash bugs Oils pins (7), harness artifacts (6), and two each of parser gaps (a nested array literal; `[hello"]"` read as a glob class), arrays and namerefs, and nested field trees (`${a:-${a:-"1 2" "3 4"}5}`).
- just-bash (per-case skips, excluding whole files): `alias` 14, `nul-bytes` 13, `builtin-printf` 9, `toysh-posix` 7, `unicode`, `sh-options`, `builtin-trap` 6 each, `whitespace` 5; its document lists "right brace in default value" (46 cases), extglob (50), IFS edge cases (about 8), here-document edge cases (several here-documents on one line, a here-document after a function definition), and JavaScript strings losing bytes and 64-bit integers.
- mvdan/sh (`#IGNORE` reasons): `declare -p` quoting 43, deliberate limits 32, expansions evaluated in turn rather than together (7 + 3), random values, glob prefixes, words not split on IFS.

Across the five, the areas that recur are: namerefs and `declare` attributes; IFS splitting with non-whitespace separators and empty fields; arrays (sparse indices, negative indices, `"${a[@]}"` in nested contexts, associative keys from expansions); quoting inside parameter-operator words; here-document edge cases; traps and `set -e` interactions; aliases; `break`/`continue` counts; `printf` formats; bytes that are not valid UTF-8 and NUL; and bash's exact error-message text and status per error kind.

## R5.5 Published pass rates and oracle approaches

- bashkit publishes 97.3% against Oils: it passes 2,618 of the 2,692 Oils cases that real bash 5.2.21 passes, out of 2,759 cases in 132 files whose `compare_shells` lists bash, at Oils `57d3f0d088c3` on 2026-10-09 (`knowledge/operations/oils-spec.md`; result file `scripts/oils-spec/results/oils-spec-linux-x86_64-20261009T010244Z.md`). Over all 2,759 cases it passes 2,628 (95.3%). The run history is 74.2%, 78.8%, 82.1%, 86.0%, 89.0%, 92.8%, 95.8%, 97.3% within about a day, and 72 of the 132 files pass every case bash passes.
- How it is computed: `scripts/oils-spec/run.py` fetches the pinned Oils commit at run time (never vendored), parses the files as Oils' `test/sh_spec.py` does, takes the bash-qualified overrides over the generic answers, treats an unasserted status as 0 and checks standard error only when asserted. Real bash runs each case the Oils way (code on standard input, `SH=bash`, `TMP`, `REPO_ROOT`, `LC_ALL=C.UTF-8`, a fresh directory); the cases real bash fails (66 at the first run: `python2` missing, root making `-r`/`-w` true, version drift past 5.2, missing locales) leave the denominator, so the headline is "cases bashkit passes over cases bash passes". bashkit runs as `bashkit -c CODE bash` with the variables glued onto the first line so `$LINENO` agrees, and with bash re-implementations of the Python 2 helpers used by both shells. Each miss is classed `signals`, `processes`, `interactive`, `host` or `behavior` by keyword (first run: 530, 110, 27, 19, 10). It is a measurement with no floor and no CI gate, because the runner's bash moves the denominator. The `-c` invocation itself costs cases: under `-c` bash ends on a fatal expansion error with 127 and `$-` holds `c`.
- brush runs bash as the oracle live on every case and every pull request, comparing stdout, stderr, status and the files left in the directory; it publishes counts (2,500+ cases, about 470 known failures in its document; 3,658 and 872 in the tree) and no percentage. It targets bash 5.3+.
- mvdan/sh confirms its hand-written expectations against an installed bash 5.3 (`TestRunnerRunConfirm`, `confirmParse` with `bash -n`), failing CI when `REQUIRE_SHELLS=1` and the shell is missing.
- just-bash publishes no rate; its runner fails on an unexpected pass of a skipped case, as spec decision 14 requires.

## What follows for the build

### Parser

- Hand-written recursive descent over a mode-switching lexer, with the modes Oils names: command, double-quoted, here-document body, arithmetic, `[[ ]]`, `=~` right side, parameter-operator word, backquote body, case pattern, array literal. The lexer position is a plain offset that can be saved and restored, for the `((` decision.
- A word is a tree of parts, never a string: literal, escaped literal, single-quoted, double-quoted (parts), `$'…'`, `$"…"`, simple and braced parameter (name, index as a word or arithmetic tree, prefix operator, suffix operator with its argument as a word parsed in the operator's own mode), command substitution (a command tree), backquote substitution (a command tree parsed from the unescaped body), arithmetic substitution (an expression tree), process substitution, tilde, brace expansion (alternatives and ranges, found by a pass on the word tree after parsing), extglob (arms as words). Each part carries its span. Quoting is a property of the part, so expansion can tag each output piece quoted or unquoted.
- Here-documents: a pending list in the command parser, filled at the next newline token, with a saved length at the start of each nested parse so a nested newline reads only its own bodies; delimiter quote-removal decides literal against expanded body; `<<-` strips leading tabs from body lines and the delimiter line; a body ended by end of input follows bash (warning on standard error, body accepted).
- `$(…)` and `<(…)`/`>(…)` bodies parsed by the command parser recursively, with `)` as the end token of that sub-parse; `case` patterns inside then need no special case.
- `((`/`$((`: try arithmetic to a matching `))` on the same line; on failure rewind and parse as nested subshell or command substitution; record every example of Oils' `paren-ambiguity` file in the corpus.
- Arithmetic: a Pratt parser over tokens whose operands are word parts; at run time, a leaf whose expanded text is not a plain integer is parsed by the same parser under the same depth budget, and a name's value is evaluated recursively up to bash's 1,024 levels or the declared depth, whichever is lower.
- Reserved words recognised only in command position and the grammar's named positions; `{`/`}`/`!`/`[[` likewise.
- The AST stores chains flat (`and_or: Vec`, `pipeline: Vec`, `if` arms `Vec`, `case` arms `Vec`, word parts `Vec`) so that no chain makes a deep tree; the depth budget counts only true nesting (compound commands inside compound commands, substitutions inside words, parentheses in arithmetic and `[[ ]]`, operator arguments inside parameter operators, unary operator runs).
- Every recursive parse function takes the depth from one counter and refuses before descending; the twelve mvdan/sh shapes and the four just-bash shapes, at the budget and one past it, are the depth law's inputs. A token counter and an input-size check run before any allocation proportional to input.
- Parse-time options: bash reads one top-level command at a time, so `shopt -s extglob`, `alias` with `expand_aliases`, and a syntax error all act per top-level command. Two consistent choices exist. (a) Parse the whole line into a sequence of top-level commands, keeping the prefix that parsed and the classified error after it; the machine runs the prefix and then ends with status 2 and bash's message, which is what bash does (verified: `echo a`, then `if` with no `fi`, prints `a` and exits 2). Extglob is parsed unconditionally, and a top-level command that used it while `extglob` was off ends with bash's syntax error when it is reached; aliases are refused as a construct, or applied by re-parsing the remainder as bashkit does. (b) Refuse the line outright on any syntax error, as a listed delta. Choice (a) keeps bash's records exact; choice (b) is simpler and contradicts every recorded syntax-error case with earlier output. Spec decision 3 ("returns a tree or one classified error") reads as (b); the difference must be reported and settled, not taken silently.

### Machine

- Non-recursive execution: an explicit frame stack in the heap (a continuation per compound command, function call, substitution and pipeline stage), so that function depth 256 (decision 17) does not depend on native stack size. bashkit's hard ceiling of 16 function frames, and its note that `stacker` cannot help on WebAssembly, are the measured reason; the machine is a WebAssembly module, where only the caps or an explicit stack protect it.
- Variables behind a copy-on-write overlay per subshell, each write charged to the memory budget; subshells, pipeline stages and `$(…)` share the parent's scopes until they write.
- Pipeline stages as coroutines with bounded byte queues counted in memory; a stage blocked on a queue yields; the last stage in the current shell only with `lastpipe`; a write to a queue whose reader finished gives status 141; `PIPESTATUS` written when the last stage ends.
- Errexit as a disabled-context counter carried in each frame: pushed by conditions, non-final `&&`/`||` members and `!`; inherited by calls; reset in command substitutions unless `inherit_errexit`; the status-masking builtins (`local`, `export`, `declare`, `readonly`) noted per case.
- Standard input as a host stream with a position shared by everything that inherits it, with `read` consuming exactly to its delimiter.
- Word expansion yields pieces tagged quoted/unquoted and splittable/globbable; IFS splitting follows POSIX's whitespace and non-whitespace rules exactly, including that a trailing non-whitespace separator ends a field without making an empty one (verified: `IFS=:` on `a::b:` gives 3 fields).
- Size checks before building: brace ranges, `printf` widths, repeated substitutions and string repetition compute their output size from the tree and arguments and refuse before allocating.

### The corpus harness

- Record once, replay forever, as bashkit's bash-oracle and just-bash's fixtures do; keep a recording only when two runs in different empty directories agree and it holds no host path, which bashkit uses to keep clock-, pid- and directory-dependent cases out.
- Score "passes over cases", and also report the number bash itself fails on the Oils run, since bash 5.3 will fail some Oils cases that pin 5.2 or Python 2 helpers. bashkit's numbers (2,759 cases in 132 files at its pin, 66 that bash fails) are the comparison to publish against.
- Run the recorder as a script file (`bash case.sh`), not `-c`, and say so in the format: `$-`, `$0`, `BASH_SOURCE`, `LINENO`, the message prefix `case.sh: line N:` and the status of fatal errors all differ between the two.
- Known failures as an exact per-case list, failing on an unexpected pass (brush, just-bash), never a per-file count (Oils).

### Thirty bash behaviours an interpreter typically gets wrong

1. A syntax error later in a script does not stop earlier top-level commands from running; the script then exits 2.
2. `shopt -s extglob` and `alias` take effect from the next top-level command, not later on the same line.
3. Aliases are off in non-interactive shells until `shopt -s expand_aliases`.
4. `$(case x in x) …;; esac)` closes at the substitution's `)`, not the pattern's.
5. `$((…))` closed by `) )` is a command substitution of a subshell; closed by `))` it is arithmetic.
6. Here-document bodies start after the line holding the operator, and several on one line are read in order.
7. A here-document opened inside `$(…)` has its body after the line holding the `)`.
8. Any quoted character in a here-document delimiter makes the whole body literal.
9. `<<-` strips leading tabs only, from body and delimiter lines.
10. `x='1 + 2'; $(( $x * 3 ))` is 7, but `$(( x * 3 ))` is 9.
11. Arithmetic on a name evaluates its value as an expression, recursively.
12. `(( expr ))` returning 0 is status 1, so `(( i++ ))` from 0 ends a `set -e` script.
13. `set -e` is off for the whole of a function called in an `if` condition or before `||`/`&&`.
14. `local x=$(false)` has status 0; `x=$(false)` has status 1.
15. Command substitutions do not inherit `set -e` unless `inherit_errexit` is set.
16. `echo hi | read x` leaves `x` unset unless `lastpipe` is on.
17. `PIPESTATUS` is overwritten by every command, including a simple command.
18. `pipefail` takes the rightmost non-zero status, not the first.
19. IFS whitespace collapses; IFS non-whitespace makes empty fields between adjacent separators but not after a trailing one.
20. An unquoted empty expansion disappears; `""` and `"$empty"` stay as empty arguments.
21. `"$@"` with no parameters is no word at all; `"$*"` is one empty word; `"-$@-"` attaches text to the first and last element.
22. `${v:-"a b"}` unquoted still splits on IFS outside the inner quotes, and the inner quotes stop globbing.
23. Quoted parts of a `[[ x == pat ]]` right side and of `case` patterns match literally; unquoted parts are patterns.
24. The `=~` right side treats quoted text literally, and a failed match empties `BASH_REMATCH` (verified).
25. `<` and `>` inside `[[ ]]` compare strings by the locale's collation; in `test` they are redirections unless escaped.
26. `case` terminators `;&` fall through and `;;&` test the next pattern.
27. Brace expansion happens before parameter expansion, so `{1..$n}` is not a range.
28. `break N` and `continue N` clamp N to the loop depth and act only on loops of the current function.
29. Functions, variables, options, traps and the working directory set in a subshell or pipeline stage do not reach the parent, and an `EXIT` trap in a subshell runs when the subshell exits.
30. Error text and status per error kind, outside POSIX mode: a special builtin's usage error and a bad substitution fail that command and the script goes on (verified), a syntax error ends the script with status 2, a command not found is 127, a non-executable file is 126, and each message carries the prefix `script: line N:`.

One line: parse words into trees of quoted parts, read here-document bodies from a pending list at the next newline, parse `$(…)` bodies with the real command parser, keep chains flat and the executor's stack in the heap, and record bash as the referee, minding that bash reads and acts on one top-level command at a time.
