# A call is interrupted and the host asks

A draft, written on 2026-11-21 against `dev` at `ffaede80` and the branch `the-shell-speaks-bash` at `10224a74`. It is not reviewed, and nothing is built. The two how-to guides under `documentation/how-to/` state the API this spec builds; where a guide and this spec disagree, the guide is what was agreed and this spec is wrong.

## The outcome wanted

A host stops an agent's work at the points that need a person, and the work continues from the same point with the person's answer. Three things can stop it: a policy that wants a call approved, a tool that wants to be approved before it runs, and a tool that asks a question from inside its body. A tool is a Python function the host writes, and an agent runs it by name from a shell line as it runs `grep`. A shell line that stops keeps everything it has done, and nothing in it runs twice.

## Builds on

- The rulings of 2026-11-21: VFS never asks a person and never holds a call open, it stops and the host asks; the word is "interrupt"; interrupts live in the root binding's storage; `answer` is per interrupt and `resume` is per shell line; a single call continues by being made again.
- `context/specifications/active/169-programs-the-index-and-the-vfs-views/spec.md` and `170-tools-and-mcp-servers-as-views/spec.md`, which designed `/.vfs/bin`, the manifest file, the rule that reading never runs, and the table that turns a schema into a command line.
- `context/research/2026-10-15-the-agent-shell-prior-art-and-experiments.md` section 5 and its study `studies/2026-10-15-agent-shell/03-program-abi-and-bin-namespace.md`, which found how Plan 9, rc, busybox and the agent shells resolve a name, and leaned to a `PATH` of directories searched as the caller.
- `research-approval-modes.md` and `research-tools-that-interrupt.md` in this directory, and the three spikes under `spikes/`.
- Story H3 to H5 and T3 of `context/standards/roadmap.md`, which this spec replaces in part. Decision 14 says where.

## What was found

**The earlier research designed most of the program side.** A program directory under `/.vfs`, a file per program whose content is its manual, lookup by `stat` as the caller, `list` to see a program and `read` to run it, and one table from parameters to flags are all in specs 169 and 170. Two things have changed since. That design had three places (a tool catalogue, a union view and an index of directories), because its shell had no variables. The shell is now bash, so `PATH` is a real variable a line can read and set, and `PATH` can be the union. And that design mapped a tool's request for input to "unsupported", because VFS had no way to stop.

**The shell as built cannot run a program the host adds.** On `the-shell-speaks-bash`, a command word is looked up in a fixed table of 18 names (`crates/vfs-shell/src/machine/exec.rs:980`). A word that holds a slash is always "No such file or directory" (`exec.rs:972`). `type` and `command -v` print `/usr/bin/<name>`, a path that does not exist (`builtins.rs:1987`). `PATH` is set to `/usr/bin:/bin` and nothing reads it (`src/vfs/shell/host.py:37`).

**A stopped line is its memory.** The machine does no IO and is driven by `step(replies)`, so between two steps no call is in progress. EXECUTED (`spikes/stopped_line_is_its_memory`, wasmi 2.0.2, the module built from `10224a74`): three lines were run to each point where they wait on a request, 18 points in all, inside a loop, a function, a pipeline and a command substitution. At each point the module's linear memory was copied, the instance was dropped, the bytes were written into a fresh instance that never saw `start`, and the requests were answered there. All 18 runs gave the same output and exit status as an uninterrupted run, with the same number of requests, so nothing was asked twice. The module exports no global, and none was needed. The memory was 1,179,648 bytes with about 58,000 non-zero.

**A Python function cannot be saved part-way.** EXECUTED (`spikes/langgraph_resume.py`): LangGraph enters a tool with two interrupts three times, and code before the first interrupt runs three times. No system studied saves a running Python frame. So a tool body that stops is started again from its first line, and the design must make that safe.

**Asking about everything does not work.** `research-approval-modes.md` reports that people approve 93 to 97 percent of prompts and catch 13.6 percent of dangerous commands. So approval is scoped by path, and a question from a tool is for what only a person knows.

## Decisions

### Programs

1. **A tool is defined with `@tool` and added to a file system.** `@tool` is a module-level decorator, as LangChain's is, and it returns a `Tool`: a name, a description from the first line of the docstring, parameters from the type hints, and the function. `VirtualFileSystem(tools=[...])`, `add_tool` and `remove_tool` are on the host's plane and never on a session. A tool is defined before any file system exists, so one tool serves several, and it is tested alone with `Tool.invoke`.
2. **`/.vfs/bin` holds every program this process can run by name.** It lists the programs the shell ships and the tools the host added. Each entry is a file whose content is the program's manual. Reading, listing and searching it never runs anything.
3. **`/.vfs/bin` is served, not stored.** A tool is a function in one process. A stored row would list tools in processes that do not have them, and every deploy would rewrite it. The router answers `stat`, `ls`, `glob` and `read` under `/.vfs/bin` from its own table. Every write under it is `invalid`. Only the access rules are stored, as grants in the root binding's grants table.
4. **`PATH` is searched, and its default is `/.vfs/bin`.** A command word is a function, then a builtin, then the first entry of that name in a `PATH` directory, looked up as the caller. A word that holds a slash names an entry directly. `type`, `command -v` and `hash` print the path that was found. Nothing found is status 127; found and not runnable is 126. This replaces the index, the union view and `Session.path` of spec 169: `PATH` is the union, and a line sets it as bash does.
5. **A name is taken once.** Adding a tool whose name is a builtin, a shipped program or another tool is refused when it is added. A name that silently ran something else would be found by an agent, not by a test.
6. **The shipped programs are for every caller; a tool follows the access rules at its path.** A shipped program can do only what its caller can, so every caller sees it and may run it, whatever the posture. A tool is host code, so a caller needs `list` on `/.vfs/bin/<name>` to see it and `read` to run it, by the ordinary rules and with no special default. On an open file system anyone may run every tool, as anyone may read every file.

### Running

7. **One public verb runs a tool: `run(path, arguments=, stdin=)`.** It is on the router today, with nothing behind it. The shell's host answers the machine's request to run a program by calling `run` as the caller, and a host can call it directly. So the gate, the policy and the log see one verb whether the tool was typed in a line or called from Python, and a tool can be built and tested before the shell lands.
8. **Parameters become the command line by one table.** The table of spec 170 section 2 stands, with one addition: a list that is the last parameter with no default takes the remaining positions, which is how `xargs` passes operands. A parameter typed `Session` or `AsyncSession` is filled in by VFS and is never on the command line.
9. **A tool's result is a program's result.** The return value is standard output: text as it is, bytes raw, anything else as one line of JSON. `ToolError` is its message on standard error and status 1. Any other exception is status 1 with one fixed line, and the detail goes to the host's log, never to the caller. A wrong argument is status 2 and the function is not called.
10. **A tool reads and writes files as its caller.** The injected session carries the caller's authority, so every call through it passes the gate and the policy. What the function does outside VFS is the host's code and VFS does not see it.
11. **A sync tool runs on a worker thread and an async tool on the kernel's loop.** A sync body on the loop thread would stall every caller, and its first call back into VFS would deadlock.

### Interrupts

12. **There are two kinds of interrupt.** An approval is raised by a policy, or by a tool declared with `approval=True`, before anything runs. It carries a preview where VFS can compute one, and it is answered with allow or reject. A question is raised by `interrupt()` inside a tool's body. It carries a message, optional options and optional details, and it is answered with a value or rejected. `Interrupt.kind` says which.
13. **`interrupt(message, *, options=None, details=None)` returns the answer.** It stops the tool by raising a subclass of `BaseException`, so a body's `except Exception` cannot swallow the stop. When options are given, an answer that is not one of them is refused at `answer` and nothing is recorded.
14. **A tool body that stopped is started again from its first line.** Each call to `interrupt` then returns its recorded answer, in order. An answer is matched by position and checked by content: if the call at that position asks something else, the recorded answer is not used and a new interrupt is raised. This replaces the roadmap's rule that a tool's earlier VFS calls are served from a record (D42), because of decision 15.
15. **A tool asks before it writes.** After a tool has changed anything through its session, a call to `interrupt` fails the tool with a message that names this rule. So a restarted body has no write of its own to repeat, and everything a tool does through VFS happens once. The failure shows the first time the tool runs. The rule can be relaxed later, by recording a tool's writes, with no change for a tool that already obeys it.
16. **An answer is for the files the tool had read.** The path and content hash of each file a tool read before an interrupt are stored with it. When the restarted body reads one that has changed, the answer is not used and the question is asked again. This is the rule a policy's preview already follows.
17. **Approval before a tool runs is a policy decision.** A run of a tool reaches the policy as `call.op == "run"`, with the tool's path and its arguments, and the ready-made `review` policy interrupts it. `@tool(approval=True)` asks on every run whatever the policy says, for a tool whose author knows it acts outside VFS. Either way the body is entered once, after the answer.

### The stopped line

18. **A line that stops is saved as the machine's memory.** The host keeps stepping the machine while any request can be answered, so interrupts raised together are reported together. When only interrupts remain, it stores the memory, compressed and cut into pages, with the run's row in the root binding's storage. `resume` writes the bytes into a fresh instance of the same module and hands in the answers. This replaces the roadmap's walk of the line from its start against a record of every step (H4, D41): no step is recorded, no command is run again, and the result does not depend on the line being a function of its inputs.
19. **The run's row holds what the memory does not.** The authority the line runs as; the hash of the module; each waiting request in full, with its arguments and standard input, because a restarted tool needs them again; the interrupts and their answers; when the run lapses.
20. **A resumed line runs as whoever started it.** The recorded authority is judged again by the gate at every request, so a right revoked while the line was stopped is refused. Restored memory runs only inside the module, which can do nothing but ask.
21. **A module that changed refuses the run.** When the stored hash is not the running module's, `resume` is a conflict that says the shell changed and the line must be run again.
22. **A run is saved when it stops, not while it runs.** A process that dies in the middle of a line leaves the changes made so far and no run, as any call does. A resumed run is claimed before it is restored. A resume that finds a claimed run answers `vfs.unavailable.in_doubt` and does not continue it, because the changes made after the last stop are not recorded and would be made again.
23. **A stage that is stopped has no exit status.** The machine is told nothing until the answer comes, so `tool || fallback` and `set -e` never act on an answer nobody gave. The stopped result reports status 75 for the line.

### Answers

24. **`answer(id, allow=True)`, `answer(id, allow=False, reason=)` and `answer(id, value=)`.** A rejected question makes `interrupt` raise `ToolError` with the reason, so the tool fails as a program does and the line handles it as any failed command.
25. **A single call continues by being made again; a line continues by `resume`.** A direct `run` of a tool that stops stores no request: the caller makes the same call again, and the answer is matched to the same caller and the same arguments, as for a file verb.

## What the shell work must provide

1. A request that looks a command word up: the name and the `PATH` directories, answered with the path found and whether the machine runs it itself, or with nothing found. The machine keeps the answer for the rest of the line, as bash's hash table does.
2. A request that runs a program the host owns: the path, the words, the environment, the working directory and the whole standard input, answered with a status, standard output and standard error. It may stay open across any number of steps, and the machine never times it out.
3. A command word that holds a slash goes through the same lookup, in place of the fixed 127.
4. `type`, `command -v` and `hash` print the path the lookup gave.
5. `xargs` among the shipped programs, with one run request for each batch of operands.
6. A law in the module's tests: a line that waits, moved to a fresh instance by its memory alone, continues to the same output. And a rule that the module keeps nothing outside its linear memory between two steps.

## Tests

Written first, and seen failing. Counts and states, never clocks.

- Every code block of the two how-to guides, run by the docs gate.
- A tool is in `ls /.vfs/bin`; `cat`, `stat`, `ls` and `grep` of its entry call the function zero times (spied); a write under `/.vfs/bin` is `invalid`.
- Each row of the command-line table: one passing call, and one status 2 with zero calls of the function.
- A caller below `list` gets 127, a caller at `list` gets 126, and every caller runs a shipped program under a `none` posture.
- A tool with one question is entered twice and its write lands once (versions counted); a tool that writes and then asks fails with the rule's message and its write lands once.
- A question whose file changed before the answer is asked again with a new id.
- A line stopped inside `$( )`, a loop and a pipeline resumes to output equal to an uninterrupted run's, with each request answered once (counted); two tools that stop together are one stop with two interrupts.
- A resume by another process over the same database succeeds; a resume after the module's hash changed is a conflict; a second resume of a claimed run is in doubt and runs nothing.
- An agent's session, a shell line and a served tool cannot reach `answer`.

## Scope

In: `Tool` and `@tool`; `/.vfs/bin` as a served directory with stored access rules; `run`; the command-line table; `interrupt`, the two kinds, `answer`, `interrupts`; the policy hook and `Decision`; the ready-made `review` and `strictest`; the run's row and the saved memory; `resume`.

Out: programs stored as files (a script or a module in a `PATH` directory, which the earlier research names); tools of a mounted MCP server; the action log; a preview for what a tool does; `review_irreversible`, which waits for a verb that reverts a file to an earlier version; recording a tool's writes so the rule of decision 15 can be relaxed.

## Build order

1. The policy hook, `Decision`, the interrupt's row, `answer`, the same call again, `review` and `strictest`. On `dev` as it stands.
2. `@tool`, `/.vfs/bin`, the command-line table, `run`, and `interrupt` in a tool reached by a direct `run`. On `dev` as it stands.
3. The six items the shell work must provide. On the shell's branch.
4. A tool in a shell line, the saved memory and `resume`. After 2 and 3, once the shell is on `dev` and runs as a module.

## Not checked

- The spike moved the memory under wasmi. VFS is to run the module under wasmtime, and the same move was not run there.
- The size of a saved line at the 64 MiB memory budget, and what its pages cost to write, were not measured.
- How the rights of a path with no stored row are judged today. Spec 170's review found no machinery for it and asked for a new seam; whether the rule a file's creation is judged by already serves was not read.
- Whether the machine keeps a waiting request's arguments in its memory. Decision 19 stores them outside it, which is right either way.
- The command-line table against real tools. Spec 170 asked for a census of real schemas and none was run.

## Choices to confirm

1. **Is a stopped line saved as memory, or walked again from a record?** Recommended: memory, by decision 18. It is exact and small to build. Its cost is decision 22: a line is not recoverable after a crash in its middle. The record gives that recovery, and needs every step written down as it runs and a line that is a function of its inputs.
2. **May a tool write before it asks?** Recommended: no, by decision 15. The other answer needs a record of every write a tool makes, and still cannot protect what a tool does outside VFS.
3. **Who may answer?** Recommended: the system authority; for an approval, an authority with `write` on every path the interrupt names; for a question, an authority that may run the tool.
4. **Does VFS ship an `ask_user` tool?** Recommended: no. It is four lines, the guide teaches it, and its name and options are the host's to choose.
5. **Is `/.vfs/bin` one directory for shipped programs and tools?** Recommended: yes, with `PATH=/.vfs/bin`. The other answer is two directories, `/.vfs/bin` and `/.vfs/tools`, both on `PATH`, so that one posture line closes every tool.

## One line

A tool is a function the host writes and a program in `/.vfs/bin` on `PATH`; a policy or a tool stops the work, the host asks, and a shell line continues from its saved memory with nothing run twice.
