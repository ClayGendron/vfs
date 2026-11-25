# A line that does not parse says where, what was expected and whether its text ended too soon, and its display shows a caret

A draft, written on 2026-11-25. It is not reviewed, and nothing is built. It was checked against `dev` at `27f3d24d`. It serves roadmap story F2 at gate a, criterion 2 and the `construct` half of criterion 1 ([roadmap](../../context/standards/roadmap.md), lines 673 to 681). It is unit 167-4 of [the conversion map](../2026-11-25-the-backlog-converted/units.md), converted by rewrite from slice B of [the archived spec 167](../../context/specifications/archive/167-the-shell-pipeline-core/spec.md), section 2, and it specifies only what [the reassessment of the shell units](../2026-11-25-the-backlog-converted/reassessment/shell.md) finds unbuilt on `dev`: the structured syntax error and the `construct` field. It rests on the shell as built by [the shell speaks bash](../2026-11-21-the-shell-speaks-bash/spec.md) and on the ruling of 2026-11-22 that the shell acts as bash in every way it can.

## The outcome wanted

An agent runs `fs.cli("echo )")`. The call fails, as today, and `stderr` is the line bash prints, as today. The one fact on the result is now `vfs.invalid.syntax`, and its `data` says where the text went wrong (`line`, `column`, `offset`), what the parser wanted there (`expected`), whether the text simply ended too soon (`incomplete`), and the source line around the place (`text`, `caret`). `str(result)` ends with that line and a `^` under the place. A line holding a refused word names the word in `data["construct"]` and the reason in `data["reason"]`. No agent has to parse prose to learn any of this.

## Builds on

- [The shell speaks bash](../2026-11-21-the-shell-speaks-bash/spec.md), built on `dev` (pull request 37, `cbda2721`). Its decision 1: "The crate's errors are its own kinds, and the vfs host maps them to `vfs.*` kinds." Its decision 3: "`parse(source, limits)` returns a tree or one classified error with line, column, offset and what was expected." The crate holds the offset; this spec carries it, and what was expected, to the result.
- [The shell acts as bash where it refused](../2026-11-22-the-shell-acts-as-bash-where-it-refused/spec.md), specified on `dev` and not built. Its decision 1: "A line is parsed and run one complete command at a time, as bash does", and "`success` keeps its meaning: a syntax error on a later line means the line did not run to its end as written." So a syntax error still ends the call with a fact after that spec lands, and the fact this spec shapes is the one it reports. It also retires every word of `REFUSED`, which leaves `construct` with few or no producers (choice 2). The two land in either order (decision 12).
- [The shell closes its known failures](../2026-11-21-the-shell-closes-its-known-failures/spec.md), specified on `dev` and not built. Its decision 1 counts the parse depth by construct and its decision 3 gives every node a span; neither touches an error's shape. It makes the parser run the here-document inside a substitution inside a here-document, which removes one producer of a refusal.
- [The shell's module crosses its boundary in binary](../2026-11-21-the-shell-crosses-its-boundary-in-binary/spec.md), specified on `dev` and not built. Its decision 1: "the JSON keeps the structure only." The start error document is structure, so the keys this spec adds ride whichever wire is current.
- [The parser and interpreter account for depth and live storage](../2026-11-22-shell-parsing-and-memory/spec.md), specified on `dev` and not built. It keeps "syntax-only parse budget errors distinct (status 2)", which this spec does not change.
- The child-kind precedent: `vfs.invalid.unindexable_pattern` (`src/vfs/results/kinds.py:83`), and decision 9 of [the ruling on the kernel's public names](../../context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md), which made `vfs.unavailable.integrity` a child "so a caller that does not know it still lands on the right family".
- Unit 167-10, [the replay corpus and the reference page](../2026-11-25-a-replay-corpus-measures-shell-coverage-and-a-reference-page-lists-the-surface/spec.md), not yet written, which owns the Oils parse count of criterion 1.

## Terms

- **Place**: the three numbers that locate an error in the text given to `cli`. `line` counts from 1, `column` counts bytes from 1 within the line, `offset` counts bytes from 0 within the whole text, all in its UTF-8 encoding.
- **Start failure**: a line refused before its first command runs. On `dev` every parse failure is one.
- **End-of-input class**: bash's two messages for text that ran out, "unexpected end of file" and "unexpected EOF while looking for ...".

## What the code does today

- `ParseError::Syntax(Position, String)` holds a place and bash's message; `Position` has `line`, `column` and `offset` (`crates/vfs-shell/src/syntax/mod.rs:37-53`). Nothing names what was expected.
- About fifty-five error sites build it: 34 calls of `unexpected()`, 15 of `eof_looking_for()`, three of `unexpected_cond()`, and two direct `error()` calls (`crates/vfs-shell/src/syntax/parser.rs:264-279`, `:1166`, `:1208-1215`, `:1731`). `eof_looking_for` places the error at the end of the text.
- The wire drops the offset: `encode_start_error` writes `kind`, `message`, `line` and `column`, and a budget writes line 0, column 0 (`crates/vfs-shell-wasm/src/wire.rs:371-393`). `StartRefusal` has the same four fields (`wire.rs:646-679`).
- The binding raises `ValueError(kind, message, line, column)` (`crates/vfs-core/src/shell_binding.rs:131-146`).
- The host maps `syntax` to `vfs.invalid`, `refused` to `vfs.unsupported` and `budget` to `vfs.budget_exhausted`, with `data={"line", "column"}` for all three, and prints `bash: line N: message` (`src/vfs/shell/host.py:126-130`, `:236-245`). A budget's fact carries `line: 0, column: 0`, which the kinds rule forbids: "absence means 'not known', never a default" (`src/vfs/results/kinds.py:52`).
- A refusal's construct and reason are joined into the message (`wire.rs:376-381`), so `eval ls` reads `Unsupported: eval: dynamic evaluation: ...` with no field for either.
- The fact renderer keeps every error to one line and collapses newlines (`src/vfs/results/render.py:93-124`). `LineResult.to_str` prints stdout, stderr, then the facts (`host.py:167-171`).
- Executed on 2026-11-25 against the built extension: `echo 'abc` fails at line 1, column 10, the end of the text; an unclosed here-document parses and runs, as bash runs it; and over every corpus case bash records as a syntax error, the shell's message and bash's are of the end-of-input class together in 82 of 82. In six cases of `tests/shell/cases/syntax-errors/` (the unterminated single, double and ANSI-C quotes, backquote, parameter expansion and arithmetic expansion) bash names line 3, where the quote opened, and the shell names line 5, the end.

## The problem

F2 criterion 2 asks that each malformed line be `vfs.invalid.syntax` with `line`, `column`, `offset`, `expected` and `incomplete`, one error per call, and a caret in the display. `dev` gives `vfs.invalid` with `line` and `column`. Criterion 1 asks that a refusal name its construct in a field; `dev` puts it in prose. Article 2 of [the constitution](../../context/standards/constitution.md) fails a pattern that "forces an agent to guess, retry blindly, or parse prose to learn state". Today an agent that wants to know whether its line was cut short, or what to put where, reads bash's English.

The acts-as-bash ruling does not remove the want. It keeps `stderr` as bash prints it and keeps a syntax error as the call's failure. The structured fact sits beside bash's text, not in place of it. At the reference deployment's 150,000 verb calls a day, an agent that repairs a line from fields does so in one retry, where one that guesses from prose may take several.

## Decisions

1. **A syntax error is the child kind `vfs.invalid.syntax`.** `ErrorKind.syntax = "vfs.invalid.syntax"` joins `kinds.py` beside `unindexable_pattern`, with the contract phrase "Does not parse", retry class `never`, the hint "Fix the line where the caret points; the parser names what it expected there.", and `path_means` "None — data carries line, column and offset". `kind_family` sends a consumer that does not know it to `vfs.invalid`, so no caller breaks. `_KIND_TO_EXC` in `src/vfs/exceptions.py` maps it to `ValidationError`, which `invalid` maps to today; without the row, `exception_for_kind` would return the bare `VFSError` for an exact member. The kind stays out of `_DETAIL_REQUIRED`, as `unindexable_pattern` does; the host always passes bash's message as the detail. The phrase is not "Syntax error", because bash's message begins with those words and `classified` forbids a detail that repeats its phrase.
2. **A syntax fact's `data` holds seven keys.** `line`, `column` and `offset` are the place (Terms). `expected` is a list of strings (decision 4). `incomplete` is a bool (decision 5). `text` is the source line around the place and `caret` the index of the place's character in `text` (decision 10). `column` keeps its meaning on `dev`, bytes within the line, so no caller of today's field sees it change; the caret is placed by characters separately. The place is in the coordinates of the whole text given to `cli`, never of a piece the parser read on its own: `Parser.base` already adds the piece's start (`parser.rs:201-204`).
3. **The place is where bash's message puts it.** For an unclosed quote, backquote, substitution or expansion, the error that bash words "unexpected EOF while looking for matching" is placed at the construct's opening character, as bash names that line in each of the six corpus records above. Every other error is placed where the parser stopped, as today. `eof_looking_for` takes the opening position from its caller, which each scanner already holds. The stderr line then names bash's line for these six, by the ruling that the shell acts as bash. Precedent: bash 5.3.15's records under `tests/shell/cases/syntax-errors/`.
4. **`expected` names what the failing rule wanted, from a closed vocabulary.** The crate gains `Expected` with two forms: a token, spelled as bash spells it (`fi`, `then`, `do`, `done`, `esac`, `in`, `}`, `)`, `]]`, `]`, `))`, `'`, `"`, a backquote), and six classes spelled in angle brackets, which no bash token can be: `<command>`, `<compound command>`, `<word>`, `<name>`, `<pattern>`, `<end of command>`. Each site names its expectation as a `&'static [Expected]`, so a parse that backtracks past an error allocates nothing for it. The list is never empty. The sites map so: `expect_reserved(w)` gives `[w]`; `eof_looking_for(c)` gives `[c]`; the end of the text inside `[[` gives `]]`; a command position after `|`, `&&`, `||`, `;` or `!` gives `<command>`; text left after the top-level list gives `<end of command>`, meaning an operator, a newline or the end of the text; a redirection target, a here-document delimiter, a here-string and a conditional operand give `<word>`; the name after `for`, `select` or `function` gives `<name>`; a `case` arm gives `<pattern>`; a function body gives `<compound command>`. Precedent: ANTLR's "expecting" set and Lark's `UnexpectedToken.expected`, both a set of terminal names; the angle brackets are BNF's mark for a non-terminal.
5. **`incomplete` is true when the parser reading the whole line ran out of text with a construct open.** It is the end-of-input class, the case where an interactive bash would print its continuation prompt. A parser reading a piece on its own, a here-document body or a backquote body, never sets it, since more text after the line would not close that piece. A refusal and a budget never carry the key.
6. **The crate's error becomes a struct.** `ParseError::Syntax(SyntaxError)`, where `SyntaxError { at: Position, message: String, expected: &'static [Expected], incomplete: bool }`, in `crates/vfs-shell/src/syntax/mod.rs`. `ParseError::message()` prints what it prints today. `Expected::spelling()` gives the wire string. No identifier names a host, as `crates/vfs-shell/tests/source_rules.rs` holds.
7. **A refusal names its construct and reason as fields.** The `vfs.unsupported` fact of a start refusal gains `construct` and `reason` in `data`, the two strings `ParseError::Refused` already holds, beside `line`, `column`, `offset`, `text` and `caret`. Its message is unchanged. Its kind stays `vfs.unsupported` (choice 2). The error at `parser.rs:1731`, "here-document inside backquotes is not supported", becomes a `Refused` with the construct "a here-document inside backquotes": it is a gap of the parser, which bash runs, as the here-document refusal at `parser.rs:397-401` is, and a syntax fact would tell the agent to fix text that has nothing wrong with it.
8. **A start failure with no place carries no place.** A budget spent while the line starts has no `line` or `column` key, and its stderr is `bash: <message>`, without `line 0`. This is the kinds rule that absence means "not known" (`kinds.py:52`), applied where `dev` breaks it.
9. **The wire carries the fields once, from one encoder.** The start error document gains `offset`, `expected` (a JSON array of strings), `incomplete`, `construct` and `reason`; a key absent from a kind is left out, not written empty. `StartRefusal` gains the same fields. The binding raises `ValueError(kind, message, fields)`, with `fields` a dict of the keys present, in place of the four-tuple; the budget path at `shell_binding.rs:131-137` raises `ValueError("budget", message, {})`. One function in `wire.rs` turns a `ParseError` into these keys, so the run-time parse of the acts-as-bash spec reports a later command's error through it.
10. **`text` and `caret` are built by the host from the line it holds, under a declared window.** `CARET_WINDOW: Final = 80` characters is declared in `src/vfs/shell/host.py` beside `LINE_FACTS`. Let `i` be the index, in characters, of the place within its line and `n` the line's length. A line of at most `CARET_WINDOW` characters is `text` whole; a longer one is cut to the `CARET_WINDOW` characters starting at `max(0, min(i - CARET_WINDOW // 2, n - CARET_WINDOW))`. `caret` is `i` minus that start, and equals `len(text)` when the place is the end of the line. `text` never crosses the module's boundary, so a one-mebibyte line adds nothing to the wire and at most 80 characters to the fact. Precedent: Python's `SyntaxError` carries the source line as `text` beside the place.
11. **The caret is drawn in `LineResult.to_str`, after the facts, and nowhere else.** For a fact carrying `text` and `caret`, two lines follow the facts: `text` with every control character but a tab written as its `\xNN` escape, then a prefix and `^`. The prefix writes a tab of the shown text as a tab, an escape as four spaces and any other character as one space, so a terminal that expands tabs puts the `^` under the place. `stderr` stays bash's bytes, and the fact renderer keeps its one-line rule. Escaping keeps a control character the caller typed from moving the cursor of whoever reads the display. Precedent: archived spec 167, section 2: "In the display only, a two-line block follows it, built from `data`: the source line with control characters escaped, then spaces and `^` under `column`."
12. **This spec and the acts-as-bash spec land in either order.** The shape is keyed to `ParseError`, not to when the error is raised. Landed first, this spec reports start failures; the acts-as-bash build then reports a later command's error through decision 9's encoder, with the place still in the whole line's coordinates.
13. **The Oils parse count is unit 167-10's.** It is a figure measured outside the gate beside the Oils run rate, by decision 4 of the known-failures spec, and it shares that measurement.

## Cost

Nothing here issues a statement, takes a lock or touches storage, so the Postgres and SQLite costs are unchanged and no engine leg is needed. The work happens only when a line fails to start, once per such call. The parser builds no list at an error site (decision 4). The host encodes the line once and scans back from `offset` to the line's start, at most the text the parse already read, which `source_bytes` bounds at 1 MiB (`crates/vfs-shell/src/syntax/mod.rs:19`). The fact grows by at most `CARET_WINDOW` characters, one `expected` entry per site as built, and four small scalars. On the wire the start document grows by a few dozen bytes. A line that parses pays nothing.

## Left as it is

- The refused words of D47 and D48. The acts-as-bash spec runs every one of them; this spec only names what is refused while they stand.
- Bash's second stderr line, which quotes the offending command, and its `-c: ` prefix. The host prints one line, and the corpus compares stderr as empty or not. That is stderr parity, not the structured fact.
- The message of `(( 1 + 2` with no close, which the shell words as "unexpected end of file" and bash as "looking for matching `)'". Both are the end-of-input class, so `incomplete` agrees.
- A syntax error inside `eval`, `source` or `bash -c` text, which exists only once the acts-as-bash spec runs those words. Its place in that text is that spec's to decide.
- Arithmetic errors, which arise when an expansion runs and exit 1, not at parse.

## Tests

Written first, and seen failing. Counts and states, never clocks. No storage changes, so no Postgres leg; no rights change, and the fact holds only the caller's own text, so no leak test.

The table both layers pin, one row per line given to `cli`, the first row with one line before it:

| Line | `line` | `column` | `offset` | `expected` | `incomplete` |
|---|---|---|---|---|---|
| `echo hi`, newline, `echo 'x` | 2 | 6 | 13 | `'` | true |
| `echo 'abc` | 1 | 6 | 5 | `'` | true |
| `echo "x` | 1 | 6 | 5 | `"` | true |
| `echo $(ls` | 1 | 6 | 5 | `)` | true |
| `ls \|` | 1 | 5 | 4 | `<command>` | true |
| `a && && b` | 1 | 6 | 5 | `<command>` | false |
| `echo )` | 1 | 6 | 5 | `<end of command>` | false |
| `if true; then echo` | 1 | 19 | 18 | `fi` | true |
| `while true; done` | 1 | 13 | 12 | `do` | false |

F2 criterion 2's unclosed here-document is not a row: it parses and runs as bash runs it (executed above).

- `crates/vfs-shell/tests/syntax_errors.rs`, new:
  - `each_malformed_line_names_its_place_what_was_expected_and_whether_it_ended_too_soon`: the table through `parse`.
  - `every_syntax_error_in_the_corpus_names_an_expectation`: every case whose parse is `Syntax` has a non-empty `expected`.
  - `a_line_is_incomplete_exactly_where_bash_says_its_text_ended`: over the 61 cases of `syntax-errors`, `incomplete` equals whether bash's record is of the end-of-input class.
  - `an_unclosed_quote_or_expansion_is_placed_where_bash_places_it`: wherever bash's record and the shell's message both say "looking for matching", the error's `line` is the line bash names; it fails on `dev` in the six cases above.
  - `a_here_document_inside_backquotes_is_a_refusal`: decision 7.
- `crates/vfs-shell-wasm/tests/wire_roundtrip.rs::every_start_refusal_reads_back_as_itself`: a syntax error, a refusal and a budget through `encode_start_error` and `decode_started`, each with exactly its keys.
- `tests/shell/test_host.py`:
  - `test_a_line_that_cannot_run_fails_and_changes_nothing`: its `if then` row expects `ErrorKind.syntax`; the line before it still leaves no file.
  - `test_a_syntax_error_names_its_place_and_what_was_expected`: the table through `fs.cli`, each row's `data` holding the seven keys of decision 2.
  - `test_a_syntax_error_prints_as_bash_and_its_display_shows_a_caret`: `echo )` leaves `stderr` the one line it is on `dev`, bash's message for the stray parenthesis, and leaves `str(result)` ending with `echo )`, a newline, five spaces and `^`.
  - `test_the_caret_sits_under_the_character_at_the_offset`: a line holding a tab and a two-byte character before a stray `)`, with `text[caret] == ")"` and the prefix's tab kept.
  - `test_a_control_character_in_the_text_is_escaped_in_the_display`: an escape character before a stray `)` prints as `\x1b`, and the prefix counts it as four spaces.
  - `test_the_text_of_a_long_line_is_cut_to_the_window`: `echo `, then 200,000 `x`, then ` )`; `len(text) == CARET_WINDOW` and `text[caret] == ")"`.
  - `test_a_refusal_names_its_construct_and_reason`: `eval ls` carries `construct == "eval"`, its reason, and `offset == 0`.
  - `test_a_start_budget_names_no_place`: a line over `source_bytes` carries neither `line` nor `column`, and its stderr holds no `line 0`.
  - `test_a_syntax_error_crosses_the_wire_with_its_fields`: `from_payload(to_payload())` gives back the fact with all seven keys.
- `tests/results/test_result_laws.py::TestKindContracts::test_the_syntax_kind_is_a_child_of_invalid`: `kind_family("vfs.invalid.syntax")` is `ErrorKind.syntax`, and the string with an unknown child below it degrades to it. The table's totality tests cover the new row.
- `tests/base/test_gates.py::test_exception_for_kind_maps_known_kinds`: gains `exception_for_kind(ErrorKind.syntax) is ValidationError`.
- `cargo test -p vfs-shell`, `cargo test -p vfs-shell-wasm`, `scripts/ci.sh` and, since docstrings change, `scripts/docs.sh check`.

## Scope

In: `crates/vfs-shell/src/syntax/mod.rs` and `parser.rs`; `crates/vfs-shell-wasm/src/wire.rs`; `crates/vfs-core/src/shell_binding.rs`; `src/vfs/shell/host.py`; `src/vfs/results/kinds.py`; `src/vfs/exceptions.py`; `documentation/reference/shell.md`; the tests above.

Out:
- The Oils parse count: unit 167-10.
- The refused words: the acts-as-bash spec.
- The parse depth and spans: the known-failures spec.
- The wire's layout: the binary-boundary spec.
- Bash's stderr text beyond the line number of decision 3: the corpus and the acts-as-bash spec.
- A `bash -n` check on `cli`: the acts-as-bash spec's own choice.

## What the docs must say

- `documentation/reference/shell.md`, under "The Result": a paragraph and a table of the seven keys of a syntax fact and the five of a refusal, the rule for `incomplete`, and the `echo )` display. The sentence "`str(result)` prints the line's standard output, then its standard error, then its facts" adds "then, under a line that did not parse, the place and a caret".
- `src/vfs/results/kinds.py`, the per-kind `data` paragraph of `ErrorKind`: `invalid.syntax` carries `line`, `column`, `offset`, `expected`, `incomplete`, `text` and `caret`.
- `src/vfs/shell/host.py`: `LineResult` and `LineResult.to_str` name the caret, and `CARET_WINDOW` gets its docstring. The docstring of the binding's constructor (`shell_binding.rs:66-69`) names `ValueError(kind, message, fields)`.

## Not checked

- No test suite, `cargo test` or docs build was run in writing this spec, and bash was not run; bash's behaviour is read from the committed records.
- The rows of the table were not run through a built parser beyond the probe above, which ran the current one. Columns and offsets are counted from the text by hand.
- Whether any corpus case of the end-of-input class raises its error in a parser reading a piece on its own. If one does, decision 5 sets `incomplete` false where bash's record says the text ended, and the corpus test names that case with its reason.
- Line agreement with bash outside the "looking for matching" class: `conditional-unterminated` is placed by bash on line 3 and by the shell on line 4, and other such cases were not counted.
- Whether clippy's `result_large_err` lint fires on the larger `ParseError`; if it does, `SyntaxError` is boxed.
- How the docs export renders a new `ErrorKind` member.

## Choices to confirm

1. **Is the structured syntax fact still wanted under the acts-as-bash ruling?** The options are to build it, or to let bash's stderr be the whole answer. Side taken: build it. It is additive: a child kind degrades to `vfs.invalid` for every caller that does not know it, the keys are new, and `stderr` does not change. Nothing has been released, so removing it before the freeze costs one revert. Article 2 asks for it.
2. **How does a refusal name its construct?** The options are two `data` keys on the existing `vfs.unsupported` fact, a new kind `vfs.unsupported.construct` as F2 criterion 1 words it, or nothing, since the acts-as-bash spec retires the refused words. Side taken: the two keys. A kind is permanent once shipped, by `kinds.py`'s rule that a retired value lives on as an alias, and it would ship with its producers about to go; keys leave with the code that writes them.
3. **Does `expected` name the failing rule's wants or the grammar's whole set at the place?** Side taken: the failing rule's, one entry at most sites. It is what each site already knows, and a list leaves room to add alternatives later without changing the type. The whole set would need the grammar's follow sets computed, a larger change for a modest gain.

## One line

A line that does not parse fails as `vfs.invalid.syntax` with its place, what the parser wanted, whether its text ended too soon and the source around it, a refusal names its construct, and the display draws a caret, while stderr stays what bash prints.
