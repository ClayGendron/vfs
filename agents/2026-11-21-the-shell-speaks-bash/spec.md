# The shell speaks bash

This spec is the design and the evaluation harness for the shell. It is written so that the autonomous pass can build the shell alone, against a fixed set of tests, a fixed set of laws and one number that only rises. It replaces the parser and executor design of [the shell pipeline core](../../context/specifications/active/167-the-shell-pipeline-core/spec.md) where the two disagree; that spec's program table, exit codes and refusal list still stand.

## The outcome wanted

A line of bash runs inside a host application, and the host stays in control of everything the line does. The line is parsed whole before anything runs. The interpreter can touch nothing by itself: no file, no process, no clock, no network. Every effect is a request the host answers or refuses. The host sets how many steps the line may take, how many bytes it may hold and when it must stop, and the line cannot exceed any of the three. No input can crash the host process. vfs is the first host, and the shell is built so that a second host needs no change to it.

## Builds on

- `write(append=True)` and `write(if_absent=True)` are on `dev`; `>>` and `touch` stand on them.
- The roadmap's shell stories and their acceptance: [the roadmap](../../context/standards/roadmap.md), domain F.
- The earlier study, with a measured corpus of 12,627 calls and a weighted 100-command sample: `context/research/studies/2026-10-15-agent-shell/`.
- Prior art cloned beside this checkout, each to be refreshed and licence-checked before study: `../wasi_python` and `../wasmtime-py` (fuel, epoch interruption, memory limits), `../monty` (an interpreter in Rust that pauses at each external call and is resumed with its answer), `../bashkit` and `../brush` (bash in Rust), `../mvdan-sh` (the parser the corpus was measured against), `../oils` (the spec suite), `../just-bash`, `../quickjs-rs`.

## The problem

Nothing of the shell is built. The earlier spec designed a bash subset with a Python pipeline over a Rust parser. Three later rulings moved the target. The language is the whole of bash. The interpreter is Rust and does no IO. The shell may become a package of its own. The earlier spec carries no fuel, no memory accounting and no rule that keeps a panic or a deep input from taking the host down. And no test suite exists that says, case by case, what bash does: without one, an unattended build has nothing to steer by.

## Decisions

1. **A crate of its own.** The shell is a new workspace crate, `crates/vfs-shell` as a working name, that depends on neither `vfs-core` nor pyo3. `vfs-core`'s Python binding wraps it, so the wheel still holds one extension module. No identifier in the crate's source says `vfs`; a test holds that. The crate's errors are its own kinds, and the vfs host maps them to `vfs.*` kinds.

2. **Three parts, one direction.** `syntax` turns text into an AST and knows nothing of execution. `machine` runs an AST and knows nothing of any host. A host drives the machine. Nothing points backwards.

3. **The AST is whole before anything runs.** `parse(source, limits)` returns a tree or one classified error with line, column, offset and what was expected. Every node carries its span. The tree can be walked by a host before execution, so the programs, the literal paths and the globs of a line can be named and judged up front. A refused construct is refused here, with its name and its reason.

4. **The machine does no IO.** It is a state machine with one entry: `step(replies)`. It runs until it needs something or is done, and returns. What it needs is a request: open, read, write, list or stat a path; start a program and feed or pull its chunks; a value that is not a function of the line, such as the time or a random number. The host performs the request, or refuses it, and passes the reply to the next `step`. The crate's source holds no `std::fs`, `std::process`, `std::net`, `std::env`, `std::thread` or `std::time`; a test holds that. The shell therefore cannot perform an unprivileged action, because it performs no action: the host judges each request with the caller's rights.

5. **Every request has a key that is a function of the line.** The key is the request's position in the walk: the stage and the ordinal within it, with a loop's iteration and a function's call counted the same way. It never holds a timestamp, a task id or a queue position. Several requests may be open at once (the stages of a pipe, `a & b & wait`); the machine applies their replies in key order, so arrival order changes nothing. Two runs of one line over one world issue equal key lists. This is the law the durable run resumes by, and it is built in from the first executor commit.

6. **Fuel.** Every step of the machine spends fuel: a command, a loop iteration, an expansion, each byte an expansion produces. The host sets the fuel. When it is spent the line ends with a budget error and exit status 137. Fuel is deterministic: the same line with the same replies spends the same fuel, and a test compares the two counts.

7. **Memory is counted, not measured.** The machine accounts for every byte it holds: variables, arrays, pipe buffers, here-documents, pending output and the AST. The host sets the budget. An expansion checks its size before it is built, so `{1..1000000000}` and a repeated substitution are refused before they allocate. Tests assert the counted bytes, never the process's memory.

8. **Time belongs to the host.** The machine has no clock. `step` returns after at most a declared slice of fuel even when it needs nothing, so the host regains control at a bounded interval. The host enforces a deadline by not calling `step` again, or by `cancel()`. The Python binding releases the interpreter lock for each slice, so the event loop is never blocked for longer than one.

9. **No input crashes the host.** Four walls, each with a test. The crate forbids `unsafe`. Clippy denies `unwrap`, `expect`, `panic`, unchecked indexing and unchecked arithmetic in it. The binding catches any panic that still happens, answers one classified internal error and poisons that machine. And no recursion follows the depth of the input, in the parser or the machine: each descent checks a depth budget first, because a stack overflow cannot be caught and would end the process. Two fuzz targets run a fixed number of iterations from fixed seeds in the gate: any bytes into `parse`, and any line with a host that answers at random into the machine.

10. **Builtins are in the machine; programs are not.** What bash defines as a builtin (`echo`, `printf`, `test`, `[`, `read`, `cd`, `export`, `local`, `declare`, `shift`, `getopts`, `true`, `false`, `:` and the rest) runs inside the machine with no request. Every other name is a program the host resolves. Text programs (`head`, `tail`, `wc`, `cut`, `sed`, `sort`, `uniq`, `tr`) are pure transforms of chunks, in a second module any host may mount. File programs (`ls`, `cat`, `find`, `cp`, `mv`, `rm`, `grep`) are written against the machine's own file requests, so one implementation serves every host.

11. **A reference host lives in the crate.** `MemoryHost` holds a tree in memory and mounts the programs above. It is what `cargo test` runs the whole conformance corpus against, with no vfs and no Python. The vfs host is the second host: each request reaches a public router method with the caller's authority, the system actor is refused, and `vfs.shell` imports nothing from `vfs.storage`.

12. **The referee is bash.** The corpus is scripts written here, one construct to a file, walking the bash manual and the POSIX shell chapter section by section. A container image of bash 5.3 and GNU coreutils, pinned by digest, runs each script once in a fresh copy of a small seed tree, with a fixed environment, and its standard output, standard error and exit status are committed beside the script. Tests never run bash. Standard output and status are compared exactly; standard error is compared as empty or not, unless a case asks for its text.

13. **One suite may be copied, once, apart.** A published conformance suite is copied one time when its licence permits, under the exception this change adds to `AGENTS.md`. The files stay unmodified in `tests/shell/vendored/<suite>/`, beside the licence text and an `ATTRIBUTION.md` naming the source, the commit, the date and the licence. An adapter reads the suite's own format. A suite under a copyleft licence is not copied. The Oils spec suite is the first candidate; its licence is checked at the commit copied, and the check is recorded in the attribution file.

14. **A red suite lives in a green tree.** `tests/shell/known_failures.txt` lists every case that does not yet pass. The gate fails when an unlisted case fails, and also when a listed case passes, so the list can only shrink and is always exact. One command prints the score: cases passing over cases total, by area and in all, for the own corpus and the vendored suite apart. That number is the measure of the work.

15. **The crate builds for WebAssembly as well as natively.** Because the machine does no IO and has one entry, it compiles to `wasm32-unknown-unknown` with no change, and the gate builds that target from the first crate commit. Run natively, the walls of decisions 6 to 9 are held by the crate's own counting and lints. Run inside a WebAssembly runtime, the runtime adds a second wall from outside: its own instruction count, a hard memory limit, a deadline it can enforce mid-step, and a trap in place of a process abort on a stack overflow or a failed allocation. The machine's own fuel and byte counts stay in both, because they give the classified error and do not change with the compiler. Which of the two the vfs host runs is a choice to confirm, after step 0 measures it.

## Tests

The suite is built before the interpreter. It has five layers.

- **Conformance, own corpus.** `tests/shell/cases/<area>/<name>.sh` with its record `<name>.json`. A case that uses only builtins is the language tier and runs against `MemoryHost` under `cargo test` and against the vfs host under `pytest`. A case that uses programs is the program tier. The areas follow the manual: quoting, parameters, each expansion, word splitting, filename expansion, redirections, here-documents, pipelines, lists, each compound command, functions, arrays, arithmetic, conditional expressions, each builtin, `set -e`, exit statuses, syntax errors, refusals, budgets. The target is at least 2,000 cases before any interpreter code.
- **Conformance, vendored.** The copied suite through its adapter, scored apart.
- **The measured corpus.** The weighted 100-command sample from the earlier study parses 100 of 100, and its run rate is published.
- **Laws.** Equal key lists and equal fuel across two runs. Output unchanged whatever the chunk boundaries. Each budget ends a counted input at exactly its count. The two fuzz targets. The source greps of decisions 1, 4 and 9.
- **The vfs host.** Every request reaches a public verb with the admitted authority (spied, N calls and N matches). Two authorities see different `ls /`. The system actor is refused.

## Scope

The order of work. Each step ends with the gate green and the score printed.

0. Research and spec review. The prior art above is studied for five questions: how fuel and interruption are counted, how an interpreter pauses at a host call and resumes, how memory is bounded without measuring the process, what each bash-in-Rust project's suite covers, and what running the machine inside a WebAssembly runtime costs (the size it adds to an install, the first load, and each call across the boundary, counted against about 20 calls a second at peak). The spec is reviewed before anything is built.
1. The harness: the recorder script, the seed tree, the case format, the runner with the known-failures list, the score command, the vendored suite with its licence record, and the corpus recorded. Every case is listed as failing. No interpreter code exists yet.
2. The crate, its lints and greps, `MemoryHost`, the lexer and the parser, and the parser fuzz target. Every corpus script parses; every malformed case classifies.
3. The machine: simple commands, variables, quoting, the expansions, the first builtins, fuel, memory and the slice.
4. Pipelines, redirections, here-documents, lists, exit statuses, bounded queues, request keys.
5. Control flow, functions, arithmetic, arrays, the parameter operators.
6. The vfs host and `cli` on the public surface. This is the first step that edits files other work shares (`base.py`, `session.py`, `sync.py`, `ops.py`).
7. The text programs, the published numbers and the reference page.

Out of scope here: the durable run itself, tools and guests, `awk` and `jq`, and job control past the call.

## Not checked

- No prior-art clone's source was read for this spec; the five research questions are open work, not findings. Of `../wasi_python`, only the README's account of its limits was read: instructions, time, memory, output and open files each have a cap, and the result says which one ended a call. The host's limits here follow that vocabulary.
- The licence of the Oils spec suite was not checked at a refreshed commit.
- The recorder was not written or run; Docker was not running when this was written.
- The seed cases under `tests/shell/cases/` have no record yet.
- Whether the request-and-reply shape serves a streaming program stage without copying each chunk twice across the binding is not measured.

## Choices to confirm

- Whether the vfs host runs the machine natively or inside a WebAssembly runtime. Natively costs nothing at install or per call, and a missed depth check or a missed byte count ends the host process. Inside a runtime, those become a trap, and the runtime joins the base install and the latency of every `cli` call.
- The crate's name, should it be published apart.
- The bash version pinned as referee: 5.3 is taken here.
- Whether the dependency list of the crate is empty or a short declared list (a regular-expression engine for `=~` is the first candidate).

## One line

A Rust machine that does no IO runs bash for a host that answers every request, bounded in steps, bytes and time, and it is built against a recorded corpus of what bash itself does, with one number that only rises.
