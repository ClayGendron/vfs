# 081. The shell speaks a static, bash-shaped POSIX subset, parsed once by vfs, and refuses the rest as classified facts

- **Status:** proposed 2026-10-15 (Clay's decisions the same day: the
  five bash-isms admitted; `set -e` implemented with POSIX's
  exemptions; `&` never; the render cap at 32,768 characters). Feeds
  spec 167. Amends nothing; the `cli` meta-verb rule in `ops.py` stands.
- **Date:** 2026-10-15
- **Amended 2026-10-15** after the pre-build review of spec 167 and Clay's answers: `time` admitted as a builtin; the `cli` display rule (pin 11).
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay set the direction — "a full CLI like
  unix and plan9 have; agents shouldn't feel limited" — and ruled on
  each fork; the assistant led the research and drafted the pins)

## Context

vfs promises in its README that an agent "already knows `ls`, `grep`
and `cat`". Today the only surface is 25 Python methods. The `cli`
meta-verb is reserved in `ops.py` as a parser that turns a command
string into those verbs and re-enters through their public methods so
every gate fires on the real verb. Nothing parses yet.

The memo `research/2026-10-15-the-agent-shell-prior-art-and-experiments.md`
(§2, §3; study `01-shell-grammar.md`) measured what agents type and
what the field built:

- Across 12,627 Bash calls from 418 Claude Code transcripts, pipes
  appear in 74% of calls, `&&` in 44%, `2>&1` in 16%, `>` in 14%,
  here-documents in 12%, `$VAR` in 12%, `for` in 4.7%, `$( )` in 3.7%,
  backticks in 4.4%, `||` in 1.4%, `if` in 0.9%, `while` in 0.4%, `&`
  in 0.2%, `set` in 6 of 67,000 segments.
- A 100-command corpus weighted to those shares parsed 100 of 100 under
  mvdan-sh's bash dialect, bashkit, just-bash and just-bash-py; 98
  under mvdan-sh's POSIX dialect; 84 under lifo, with one parser hang.
  The grammar below admits 86 of 100 outright and 91 with `for`.
- The Oils bash spec suite's weight is in arrays and arithmetic (152 of
  3,966 cases) for constructs that are 1.4% of agent traffic. brush's
  heaviest compatibility file is `set -e` (159 cases).
- Plan 9's rc is the better-designed grammar (one quoting rule, lists
  as the only type, a 92-line yacc grammar) and a bash-trained model
  emits zero rc.
- Both agent-shell peers that accept `&` lie to the model: just-bash
  parses it and runs the list synchronously; bashkit polls the job
  once and files it.
- mvdan-sh's parse errors name the open construct and what would close
  it; bash's "unexpected token" tells a model nothing; nushell's
  refused-feature errors name the replacement.

## Options considered

- **A POSIX.1-2024 subset parsed by our own parser, with named
  bash-isms admitted (chosen).** Pros: parses all of measured traffic
  we choose to admit; one dialect grown by slice; static parse means
  nothing runs on a refused line. Cons: four quoting rules and the
  expansion order are ours to implement exactly.
- **rc.** Pros: one quoting rule, no re-scanning, a grammar one can
  state. Cons: 74% of traffic becomes a parse error on day one.
- **A new grammar (YSH, nushell or elvish shaped).** Pros: structured
  pipes by design. Cons: starts at 0% of traffic; nushell's respelled
  redirections alone would break 16% of calls.
- **Parse everything bash-shaped and fail when reached (just-bash's
  stance).** Pros: fewer refusals. Cons: a refused construct after a
  mutation has already run; the execution-policy ADR's pre-execution
  summary becomes unsound.

## Decision

Twelve pins.

1. **One dialect, static, single pass.** The shell parses the whole
   command string into an AST before any verb is called. No `eval`, no
   re-scanning of expansion results, no re-splitting of a substituted
   value (rc's and OSH's discipline). A refused construct anywhere in
   the string refuses the whole call before anything runs.
2. **Lexical.** Blanks delimit; `#` to end of line is a comment;
   backslash-newline continues a line; operators are longest-match
   over `|| && ;; ;& << <<- >> <& >& <> >| &> &>> | & ; < > ( )`,
   with a digit prefix on `>` and `<`. Reserved words are recognised
   only at command start: POSIX's list plus `[[`, `]]`, `function` and
   `time`, reserved now so later slices admit them without changing
   what today's words mean.
3. **Quoting, one table.** Unquoted: backslash keeps the next
   character literal; `$`, backquote, leading `~`, `* ? [`, `{a,b}`
   and the operators are special. Single quotes: every character
   literal; no quote inside. Double quotes: everything literal except
   `$`, backquote, and backslash before `$`, backquote, `"`, backslash
   or newline. `$'…'`: C escapes `\n \t \r \\ \' \xHH \ddd`, no
   expansion.
4. **Expansions, in POSIX order.** Tilde (`~` and `~/` only; `~user`
   is refused, there are no users in a mount); parameter `$NAME`,
   `${NAME}` and the ten POSIX operators `${#p} ${p:-w} ${p:=w}
   ${p:?w} ${p:+w} ${p%w} ${p%%w} ${p#w} ${p##w}`; the special
   parameters `$? $# $@ $* $0`–`$9`; command substitution `$( )` and
   backticks; field splitting on the default `IFS` of unquoted
   expansion results; pathname expansion `* ? [ ]` plus `{a,b}` and
   `{1..3}` brace expansion, textual and first, in the shell; only
   pathname expansion goes to `glob`, anchored at the working
   directory, dotfiles hidden from `*`; quote
   removal last. No arithmetic at v1.
5. **Commands.** Simple commands with assignment prefixes and bare
   assignments; pipelines with `!`; lists with `;`, newline, `&&` and
   `||` at equal precedence, left-associative; `( list )` as a scope
   for `cd` and assignments; `{ list; }`. Redirections `< > >> >| <>
   n> n>> n< <&m >&m n>&m n<&m 2>&1`, with `&>` and `&>>` as sugar for
   `>f 2>&1`. Here-documents `<<WORD` and `<<-WORD` with the
   quoted-delimiter rule and the terminator on its own line.
6. **`set -e` exists, with POSIX's exemptions** (Clay, 2026-10-15). A
   failing command stops the call unless it is a non-last member of
   an `&&` or `||` list, the condition of `if`, `while` or `until`, a
   `!` pipeline, or a non-last pipeline stage. The mode is per-call
   state: it resets when the call returns, as a fresh bash does. The
   status list on the `Result` names the stage that tripped it.
7. **Status.** `$?` is POSIX's: the rightmost stage of a pipeline. The
   `Result` also carries every stage's status as a list (rc's
   `$status`), so the renderer can flag a masked failure under
   `cmd 2>&1 | tail -5` without changing `$?`. `$status` is the first
   fatal classified kind, or empty.
8. **Refused at v1, by name.** `if for while until case` and their
   closers, functions in both spellings, `[[ ]]`, `$(( ))`, `(( ))`,
   `select`, `coproc`, `<( )`, `>( )`, `<<<`, `|&`, `{var}>`,
   arrays, `${x/a/b}`, `${x:1:2}`, `${!x}`, `${x@Q}`, extended globs,
   and `&`: each classifies `vfs.unsupported.construct`, a child of
   `unsupported`, whose detail names the construct and, for the
   constructs a later slice admits, that slice. `time` is admitted
   as a builtin, not a keyword (`time -p cmd`; 72 corpus uses). `&` is refused
   forever: the call returns when the list has run, and the refusal
   says so. `shopt`, `eval`, `exec`, `trap`, `source` and `.` as
   commands classify `unrecognized`.
9. **Malformed text** classifies `vfs.invalid.syntax`, a child of
   `invalid`: unclosed quote, unclosed here-document, `if` without
   `fi`, trailing `|`, `&& &&`, stray `)` or `}`. The error carries no
   path. Its data holds `vfs.line`, `vfs.column` (1-based in the
   caller's string), `vfs.offset`, `vfs.construct` (the token at
   fault), `vfs.expected` (what would close it) and `vfs.incomplete`
   (true when the input ended inside an open construct). The text
   rendering prints the offending line with a caret under the column.
   Exactly one error per call, the first in source order.
10. **Parser budgets are facts.** Input size, token count, nesting
    depth and parse iterations each have a declared constant; an
    overrun classifies `vfs.budget_exhausted`, never a hang.
11. **The `cli` surface prints exactly what bash prints** (Clay,
    2026-10-15): nothing for an empty `ls`, nothing after a mutation
    unless `-v`, paths as typed relative to the working directory, no
    trailing slash without `-F`. The display rendering at the `cli`
    boundary applies the 32,768-character cap; the text that crosses a
    pipe is a plain rendering with no cap, no markers and no added
    newline on a file body. A host adapter may add one `(no output)`
    line. The spec 155 markers stay on the verb tools. Shell state
    never persists between `cli` calls on a wire; each call starts at
    `workdir`, default `/`.
12. **Growth by slice, measured.** Slice 1 is everything above. Slice
    2 admits `for`, `if`, `while`, `until`, `case` with `;;` and `;&`,
    `break` and `continue` as keywords (`[ ]` and `test` are programs
    in slice 1), `[[ ]]`
    with `=~`. Slice 3 admits functions, `local`, `return`, `$(( ))`.
    Slice 4 admits a long-tail construct only when a measured corpus
    shows it above about 1%. A construct moves from pin 8 to admitted
    by amending this ADR's slice list, never by silent acceptance.

## Consequences

- An agent's existing bash habits parse. The 14 of 100 weighted
  commands that do not are refused before anything runs, with a
  message that says what to rewrite.
- `set -e` costs a real implementation and its own spec-test file,
  pinned against brush's and Oils' cases. It buys the most expansive
  surface, which is what Clay asked for.
- Because the parse is static, the execution-policy ADR can summarise
  a call (which programs, which verbs, which paths) before it runs.
- The parser is ours to maintain, including the expansion order. The
  spec-test corpus (script in, stdout and status out) is the contract.
- `&` never exists. When programs run long, the job model of the
  session study (files under `/.vfs/jobs`, MCP tasks as the wire)
  gives a background channel without a grammar change.
