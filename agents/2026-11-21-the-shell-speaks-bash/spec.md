# The shell speaks bash

This spec is the design and the evaluation harness for the shell. It is written so that the autonomous pass can build the shell alone, against a fixed set of tests, a fixed set of laws and one number that only rises. It replaces the parser and executor design of [the shell pipeline core](../../context/specifications/active/167-the-shell-pipeline-core/spec.md) where the two disagree; that spec's program table, exit codes and refusal list still stand.

## The outcome wanted

A line of bash runs inside a host application, and the host stays in control of everything the line does. The line is parsed whole before anything runs. The interpreter can touch nothing by itself: no file, no process, no clock, no network. Every effect is a request the host answers or refuses. The host sets how many instructions the line may execute, how many bytes it may hold and when it must stop, and the line cannot exceed any of the three. No input can crash the host process. vfs is the first host, and the shell is built so that a second host needs no change to it.

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

6. **Fuel is instructions executed.** This is ruled. The machine runs as a WebAssembly module, and the runtime counts every instruction the module executes, as `wasi-python` counts its guest's. The host sets the fuel as a number of instructions, and the result says how many were used. When the fuel is spent the runtime stops the module, and the line ends with a budget error and exit status 137. The machine counts no steps of its own as fuel. Within one build the count is deterministic: the same line with the same replies spends the same fuel, and a test compares the two counts. Across builds the count moves with the compiler, so no test pins a number of instructions: a test pins that a declared fuel stops a line that would never end, and that the count reported is the count spent.

7. **Memory is counted, not measured.** The machine accounts for every byte it holds: variables, arrays, pipe buffers, here-documents, pending output and the AST. The host sets the budget. An expansion checks its size before it is built, so `{1..1000000000}` and a repeated substitution are refused before they allocate. Tests assert the counted bytes, never the process's memory. Behind the count stands the runtime's own limit on the module's memory, which is the hard wall: a byte the count missed ends the call there, not the process.

8. **Time belongs to the host.** The machine has no clock. `step` returns after at most a declared slice of fuel even when it needs nothing, so the host regains control at a bounded interval. The host enforces a deadline by not calling `step` again, or by `cancel()`. The Python binding releases the interpreter lock for each slice, so the event loop is never blocked for longer than one. The runtime's own deadline ends a slice that overruns, so the slice is a courtesy and the runtime is the wall.

9. **No input crashes the host.** Four walls, each with a test. The crate forbids `unsafe`. Clippy denies `unwrap`, `expect`, `panic`, unchecked indexing and unchecked arithmetic in it. The binding catches any panic that still happens, answers one classified internal error and poisons that machine. And no recursion follows the depth of the input, in the parser or the machine: each descent checks a depth budget first, because a stack overflow cannot be caught and would end the process. Two fuzz targets run a fixed number of iterations from fixed seeds in the gate: any bytes into `parse`, and any line with a host that answers at random into the machine. Inside the runtime a panic, a stack overflow or a failed allocation that still happens is a trap, which ends that call and leaves the process running; the four walls keep such traps rare, and they are all a native build has.

10. **Builtins are in the machine; programs are not.** What bash defines as a builtin (`echo`, `printf`, `test`, `[`, `read`, `cd`, `export`, `local`, `declare`, `shift`, `getopts`, `true`, `false`, `:` and the rest) runs inside the machine with no request. Every other name is a program the host resolves. Text programs (`head`, `tail`, `wc`, `cut`, `sed`, `sort`, `uniq`, `tr`) are pure transforms of chunks, in a second module any host may mount. File programs (`ls`, `cat`, `find`, `cp`, `mv`, `rm`, `grep`) are written against the machine's own file requests, so one implementation serves every host.

11. **A reference host lives in the crate.** `MemoryHost` holds a tree in memory and mounts the programs above. It is what `cargo test` runs the whole conformance corpus against, with no vfs and no Python. The vfs host is the second host: each request reaches a public router method with the caller's authority, the system actor is refused, and `vfs.shell` imports nothing from `vfs.storage`.

12. **The referee is bash.** The corpus is scripts written here, one construct to a file, walking the bash manual and the POSIX shell chapter section by section. A container image of bash 5.3 and GNU coreutils, pinned by digest, runs each script once in a fresh copy of a small seed tree, with a fixed environment, and its standard output, standard error and exit status are committed beside the script. Tests never run bash. Standard output and status are compared exactly; standard error is compared as empty or not, unless a case asks for its text.

13. **The whole suite is written here; no suite is copied.** Every case is a script written for this corpus, and bash's record is its answer, so no other project's expected outputs are needed. The Oils spec suite was measured as the candidate for a copy and not taken: 223 files, 72,692 lines and 3,966 cases, about 2,800 of them shell cases, under Apache 2.0. A copy would carry its files, its licence text and its attribution into any package the shell becomes, and its format marks each shell's differences inline, which an adapter would have to read. Two things stand in for what a copy would give. A differential fuzzer, run outside the gate, generates scripts from the grammar, runs each through the shell and through the pinned bash, and every disagreement is written up as a new case of the corpus. And for a number other projects also publish, the Oils suite is run from a pinned commit of the sibling clone when the score is measured; it is never committed and never in the gate.

14. **A red suite lives in a green tree.** `tests/shell/known_failures.txt` lists every case that does not yet pass. The gate fails when an unlisted case fails, and also when a listed case passes, so the list can only shrink and is always exact. One command prints the score: cases passing over cases total, by area and in all. That number is the measure of the work.

15. **The machine ships as a WebAssembly module, and also builds natively.** Decision 6 settles the runtime, because instructions can be counted only inside one. Because the machine does no IO and has one entry, it compiles to `wasm32-unknown-unknown` with no change, and the gate builds that target from the first crate commit. The vfs host runs the module in a WebAssembly runtime, so the runtime is part of the base install. The runtime gives four things from outside the module: the instruction count, a hard memory limit, a deadline it can enforce inside a step, and a trap in place of a process abort. The native build stays for `cargo test`, for a debugger, and for a host of another kind that accepts running with no instruction fuel. The corpus runs on both builds; the laws on fuel, memory and deadline run on the module. How the runtime is carried, and whether the host code `wasi-python` already has can drive this module too, is settled by step 0.

16. **A deliberate difference from bash is listed, with its reason.** Where the shell differs on purpose (a refused construct, `ls -l` without mode bits), the case keeps bash's record and gains a second record of the shell's own answer. `tests/shell/deltas.txt` names each such case with a one-line reason, and a test holds that the list is exhaustive. A delta is not a known failure: it passes against its own record.

17. **The budgets have declared defaults a host may lower.** They are the roadmap's: 1 MiB of source, 100,000 tokens, a depth of 200, 64 stages in a pipeline, 1,000,000 loop iterations, a function depth of 256. Fuel, bytes and the slice get their defaults in step 3, each as a named constant with the count that justified it.

18. **The fuzz targets need no special toolchain.** Each is an ordinary test driven by a seeded generator, run for a declared number of iterations on the stable compiler.

## Tests

The suite is built before the interpreter. It has five layers.

- **Conformance, own corpus.** `tests/shell/cases/<area>/<name>.sh` with its record `<name>.json`. A case that uses only builtins is the language tier and runs against `MemoryHost` under `cargo test` and against the vfs host under `pytest`. A case that uses programs is the program tier. The areas follow the manual: quoting, parameters, each expansion, word splitting, filename expansion, redirections, here-documents, pipelines, lists, each compound command, functions, arrays, arithmetic, conditional expressions, each builtin, `set -e`, exit statuses, syntax errors, refusals, budgets. The target is at least 2,000 cases before any interpreter code.
- **What the fuzzer found.** Each disagreement the differential fuzzer finds between the shell and bash becomes a recorded case under `tests/shell/cases/found/`, and stays.
- **The measured corpus.** The weighted 100-command sample from the earlier study parses 100 of 100, and its run rate is published.
- **Laws.** Equal key lists and equal fuel across two runs. Output unchanged whatever the chunk boundaries. Each budget ends a counted input at exactly its count. The two fuzz targets. The source greps of decisions 1, 4 and 9.
- **The vfs host.** Every request reaches a public verb with the admitted authority (spied, N calls and N matches). Two authorities see different `ls /`. The system actor is refused.

## Scope

The order of work. Each step ends with the gate green and the score printed.

0. Research and spec review. The prior art above is studied for five questions: how fuel and interruption are counted, how an interpreter pauses at a host call and resumes, how memory is bounded without measuring the process, what each bash-in-Rust project's suite covers, and what running the machine inside a WebAssembly runtime costs (the size it adds to an install, the first load, and each call across the boundary, counted against about 20 calls a second at peak). The spec is reviewed before anything is built.
1. The harness: the recorder script, the seed tree, the case format, the runner with the known-failures list, the score command, and the corpus written and recorded. Every case is listed as failing. No interpreter code exists yet. The differential fuzzer joins in step 3, when there is a machine to compare.
2. The crate, its lints and greps, `MemoryHost`, the lexer and the parser, and the parser fuzz target. Every corpus script parses; every malformed case classifies.
3. The machine: simple commands, variables, quoting, the expansions, the first builtins, fuel, memory and the slice.
4. Pipelines, redirections, here-documents, lists, exit statuses, bounded queues, request keys.
5. Control flow, functions, arithmetic, arrays, the parameter operators.
6. The vfs host and `cli` on the public surface. This is the first step that edits files other work shares (`base.py`, `session.py`, `sync.py`, `ops.py`).
7. The text programs, the published numbers and the reference page.

Out of scope here: the durable run itself, tools and guests, `awk` and `jq`, and job control past the call.

How the work is run, so that it can run unattended from the first step to the last.

- **Work is committed and pushed to this branch as it goes, and one pull request is opened when the last step is done.** This is ruled: the push to this branch needs no asking, and no pull request is opened before the end. Each step is still closed by `scripts/ci.sh` green and by a code review from a fresh reviewer, whose file is committed with the step, so the final pull request is a set of steps already reviewed. `dev` is merged into the branch when it moves, so the branch does not drift.
- **The gate grows with the work.** Step 1 adds the corpus runner and the score to `scripts/ci.sh` and the workflows. Step 2 adds `cargo test -p vfs-shell`, the clippy denials and the `wasm32-unknown-unknown` build. From step 3 the corpus and the laws on fuel, memory and deadline run on the module inside the runtime. Step 6 brings the Python under the 100% coverage gate and runs the Postgres leg. The wheel budget and a line ratchet are raised only by a named entry with its reason.
- **`progress.md` in this work directory is rewritten at every commit.** It holds the step in hand, the score, what was decided inside the laws, what was reported and not taken, and what is next. A session that starts cold reads this spec and that file, and needs nothing else.
- **Inside the laws, the design is free.** The request types, the shape of the AST, the module layout and the order of cases within a step are decided as the work goes. A change to a decision above, to what a budget means, to a public name of vfs, or to a rule of `AGENTS.md` is reported and not taken.
- **What the work needs on the machine.** Docker, for the recorder in step 1 and for the Postgres leg in step 6. The stable Rust toolchain with the `wasm32-unknown-unknown` target. `uv`. The recorder pins its image by digest and writes the digest into every record.

Done when, step by step.

- Step 1: at least 2,000 cases written and recorded, every case listed as failing, and the score printed by one command.
- Steps 2 to 5: no language-tier case of the own corpus is left in the known-failures list, the laws hold, and both fuzz targets pass their declared iterations.
- Steps 6 and 7: no case is left in the known-failures list, the measured sample runs at 85% or more, the fuzzer's last declared run finds no new disagreement, the Oils rate is measured and published with its commit, and the acceptance of the roadmap's stories F1 to F4 and F7 is met or reported as not met with the reason.

## Not checked

- No prior-art clone's source was read for this spec; the five research questions are open work, not findings. Of `../wasi_python`, only the README's account of its limits was read: instructions, time, memory, output and open files each have a cap, and the result says which one ended a call. The host's limits here follow that vocabulary.
- The Oils suite was counted in the sibling clone at commit `bdc8364` of 2026-10-15, not refreshed; its files were counted and not read.
- The recorder was not written or run; Docker was not running when this was written.
- The seed cases under `tests/shell/cases/` have no record yet.
- Whether the request-and-reply shape serves a streaming program stage without copying each chunk twice across the binding is not measured.

## Choices to confirm

- How the WebAssembly runtime is carried: as a Python dependency, as `wasi-python` carries its own, or linked into the extension module. Step 0 measures the size each adds to an install, the first load and the cost of each call, and the choice follows the numbers.
- The crate's name, should it be published apart.
- The bash version pinned as referee: 5.3 is taken here.
- Whether the dependency list of the crate is empty or a short declared list (a regular-expression engine for `=~` is the first candidate). It is taken as empty until a case needs one, and each addition is reported.
None of these stops steps 0 to 5: the corpus runs on the native build under `cargo test`, and the laws on fuel, memory and deadline run on the module under a runtime taken as a test dependency, however vfs later carries it.

## One line

A Rust machine that does no IO runs bash for a host that answers every request, bounded in instructions, bytes and time, and it is built against a recorded corpus of what bash itself does, with one number that only rises.
