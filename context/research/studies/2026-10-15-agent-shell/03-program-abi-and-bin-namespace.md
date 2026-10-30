# S3 — The program ABI, the bin namespace, and what the pipe carries

- **Date:** 2026-10-15
- **Researcher:** S3 (agent-shell study)
- **Question:** one program ABI for every program kind (builtin, Rust kernel, wasm binary, guest script); the bin namespace programs live in; what the pipe carries.
- **Clones read (commit, from `refresh.log`):** busybox 371fe9f; toybox 6a0c0ef; uutils-coreutils 4945ecf; just-bash 9ab0e0d; bashkit b7904a4; nushell 818d4ac06; elvish 26a8bd5; PowerShell db1d0a5; lifo 5a35d05; plan9port b6564bd9; 9front a0806493 (**DIRTY, not refreshed**); mcpfs 640511e; agentfs 0a014eb; agentvfs 82663b4; WASI 463701e; componentize-py 9ff99da; modelcontextprotocol 86f6e0c6. Licences from `licenses.log`: busybox GPL-2.0 and 9front (no licence file; Plan 9 code is MIT/LPL per the `plan9` clone) were studied only; nothing was copied from any clone.
- **Evidence labels:** `READ` = read in a checkout or a fetched page; `EXECUTED` = a script in `experiments/s3/` produced the output quoted; `INFERRED` = my reasoning from READ/EXECUTED facts.
- **Experiment:** `experiments/s3/abi_demo.py` (run with `uv run python …`), output in `experiments/s3/abi_demo.out`.
- **Coordinator rule folded in (Clay, 2026-10-15):** common commands keep their native Unix names and flag semantics; one name may be served by different program kinds over time; an unimplemented form is refused with a classified `unsupported` that names the form. See §"One name, many kinds" under *What this means for vfs*.

---

## Summary

Every peer that runs commands over a virtual filesystem — just-bash, bashkit, lifo, nushell's plugins, WASI's `command` world, busybox and toybox's applet tables — gives a program the same six things and takes back the same three: **in:** argv, an environment, a cwd, a stdin stream, a filesystem capability; **out:** a stdout stream, a stderr text channel, an exit code. The ABI for vfs is that six-in/three-out shape, with two vfs-specific decisions on top. First, the filesystem capability *is* the verb set already bound to the caller's `Authority` — a program never holds or passes identity (ADR 069's no-side-door rule becomes a type: there is no parameter to widen). Second, the pipe carries **chunks of exactly one of two shapes**: `Rows` (a `Result` slice — rows plus classified errors, op-tagged) or `Bytes` (a buffer with a mime). A program declares which shape it consumes and which it produces, and the shell converts at a seam only when the shapes differ, by two laws. Rows become bytes only for a byte-shaped consumer, through the one render chokepoint with the producing op's default projection — which is what makes `ls | wc -l` count entries and `cat f | wc -l` count lines, exactly as Unix does — except that one bytes-bodied `read` row crosses raw with its mime (PowerShell's BytePipe lesson). Bytes become rows only for a row-shaped consumer, as exactly one row, sniffed into `content` XOR `data` with a mime. I built the ABI and the two laws as a Python reference over the live `InMemoryStorage` and ran six pipelines plus a 10,000-row one (EXECUTED): the laws hold, the verb builtins consume upstream rows without re-parsing text (`glob | grep`), bounded queues keep the 10k pipeline at two chunks in flight, and PIPESTATUS/pipefail fall out. The exercise also exposed four things the live tree must change before a shell can ship: `run` rows render their synthetic path instead of their content; `read` elides `data` unless projected, so a byte-shaped `cat` must ask for it; the media placeholder rule of the July memo is not in `render.py` yet; and a program's output row needs an address, which I propose to give it under `/.vfs/run/<call>/stdout` (nu-mcp's `$history.N` handle, done the vfs way). The bin namespace should be a Plan 9 union — the kernel's program table first, then `$PATH` directories in the namespace, default `/.agents/bin` as a third reserved family — resolved by name with the caller's authority, so a program the caller cannot `list` is 127 and one it can list but not `read` is 126. Builtins are not stored entries; `type`/`which`/`help` answer from the union. One name is served by whatever kind the union resolves to today; a form the kind does not implement is refused with `vfs.unsupported.form`, exit 2.

---

## Findings

### F1. One binary, many names: the applet table is the program table (READ)

Three production multicall binaries keep a static table of `(name, entry point, declared grammar, flags)` and dispatch by name.

- **busybox**: `applets.src.h` documents the row — "name — applet name as it is typed on command line; main — corresponding `<applet>_main`; l — location to install link to; s — suid type" (busybox:include/applets.src.h:9-24). The table is built by re-expanding one macro list into `struct bb_applet applets[]` (applets.src.h:76-81). `run_applet_no_and_exit` sets `applet_name`, checks `--help`, counts argv, calls `applet_main[applet_no](argc, argv)` and dies with its return value as the process status (busybox:libbb/appletlib.c:953-973). `find_applet_by_name` is a linear scan over a sorted packed string table (appletlib.c:177-230).
- **toybox**: `NEWTOY(name, opts, flags)` expands three ways — a prototype, a `toy_list[]` row `{#name, name##_main, OPTSTR_##name, flags}`, and a flag-bit header (toybox:toys.h:77-82, main.c:8-21). `toy_find` is a binary search over the sorted table, and the multiplexer name works as a prefix (main.c:30-60). A name that resolves to nothing sets `toys.exitval = 127` and prints help (main.c:163-168). `toy_exec_which` runs the found command *in process* unless the flags forbid it or stack depth is "getting noticeable" (main.c:270-296) — a recursion-aware inline exec.
- **uutils**: a build-generated `util_map()` from name to `(uumain, uu_app)`; the multicall `main` matches the binary name's suffix, else takes the first argument as the util name (uutils-coreutils:src/bin/coreutils.rs:55-96). Each util is a crate exposing `pub fn uumain(args: impl Args) -> i32` and `uu_app() -> clap::Command` (src/uu/wc/src/wc.rs:383-392); the `bin!` macro makes a `main` that calls `uumain` and `std::process::exit(code)` (src/uucore/src/lib/lib.rs:219-262). `UError::code()` defaults to 1 (src/uucore/src/lib/mods/error.rs:170-223).

busybox's NOFORK/NOEXEC doc makes the point that matters for vfs: "shell builtins use these tricks regardless … In effect, builtins are 'always NOFORK'" (busybox:docs/nofork_noexec.txt:1-40). Whether a name runs inline, forks, or execs is an *execution strategy* chosen by the table row's flags; the caller types the same name either way. That is the coordinator's "one name, many kinds" rule already in production.

### F2. The flag grammar can be declared, not hand-parsed (READ)

toybox's get_opt string is a complete declarative grammar in one string: flag letters become bits, suffixes type the argument (`:` string, `#` long with `<low>high=default`, `*` list, `@` counter), prefixes set argument-count bounds (`<1`, `>9`), `^` stops at the first non-option, and trailing `[-abc]`/`[+abc]`/`[!abc]` groups declare switch-off, synonym and mutual-exclusion sets (toybox:lib/args.c:12-100). Real rows: `NEWTOY(wc, "Lcmwl", …)` (toys/posix/wc.c:7); grep's string declares every long option, the `-C#` context args and `[!wx][!EF]` exclusions, plus `TOYFLAG_ARGFAIL(2)` so a usage error exits 2 (toys/posix/grep.c:10). nushell's `Signature` goes further: positional, named, rest, and `input_output_types: Vec<(Type, Type)>` checked by the parser before anything runs (nushell:crates/nu-protocol/src/signature.rs:360-377). bashkit offers `ClapBuiltin` — derive a `clap::Parser` struct, get a context with `stdout`, `stderr`, `exit_code` fields (bashkit:crates/bashkit/src/builtins/mod.rs:1450-1500). Three independent designs agree: **the accepted forms of a program are data the shell can read**, which is the hook the coordinator's "refuse an unimplemented form, by name" needs.

### F3. Every command context is the same six-tuple (READ)

| system | args | env | cwd | stdin | fs capability | out |
|---|---|---|---|---|---|---|
| just-bash `Command.execute(args, ctx)` (just-bash:packages/just-bash/src/types.ts:312-324) | `string[]` | `Map<string,string>` (a Map "to prevent prototype pollution", types.ts:177) | `cwd: string` | `stdin: ByteString` — "Pipelines carry bytes … choose a conversion at the use site" (types.ts:185-199) | `fs: IFileSystem` + optional `exec`, `fetch`, `invokeTool` | `ExecResult {stdout, stderr, exitCode, stdoutKind: "text"\|"bytes"}` (types.ts:15-45) |
| bashkit `Builtin::execute(ctx) -> Result<ExecResult>` (bashkit:crates/bashkit/src/builtins/mod.rs:1353-1366) | `&[String]` | `&HashMap` read-only + `variables` mutable | `&mut PathBuf` | `Option<&StreamData>` (bytes canonical, mod.rs:961-965) | `fs: Arc<dyn FileSystem>` — "a revocable view: cloned handles fail after the current execution completes" (mod.rs:954-959) | `ExecResult {stdout: StreamData, stderr, exit_code, stdout_truncated…}` (interpreter/state.rs:65-80); `Err` = fatal host error |
| lifo `Command = (ctx) => Promise<number>` (lifo:packages/core/src/commands/types.ts:12-35) | `args` | `Record` | `cwd` | `stdin?: {read(), readAll()}` | `vfs: VFS` | `stdout.write`, `stderr.write`, the number is the exit code; `signal: AbortSignal` |
| WASI `wasi:cli/command@0.2.0` (componentize-py:wit/deps/cli-0.2.0/{command,run,environment,stdio,exit}.wit) | `get-arguments` | `get-environment: list<tuple<string,string>>` — "should return the same values each time" | `initial-cwd` | `get-stdin: input-stream` | `wasi:filesystem/imports` (preopens) | `get-stdout`/`get-stderr` streams; `exit(status: result)`; `run: func() -> result` |
| toybox/busybox/uutils | `argv` | process env | process cwd | fd 0 | the OS | fd 1, fd 2, `exit(n)` |

The convergence is total. Two details matter for vfs:

- **Trust is a property of the program, decided by the host.** just-bash: "Host-provided commands are trusted by default … Set this to false to select the restricted extension boundary. Built-in commands should generally remain untrusted" (types.ts:313-321; `defineCommand(name, execute, {trusted})`, custom-commands.ts:100-106; registration, Bash.ts:568-583); the threat model states the boundary "protects untrusted *scripts*, not untrusted *hosts*" (just-bash:THREAT_MODEL.md:35). bashkit's execution boundaries are "typed, shared, and revocable … host capabilities stop working when their execution ends" (bashkit:CHANGELOG.md:598-604; src/execution_capability.rs:38-178; docs/custom_builtins.md:1-8).
- **Dynamic names resolve through a hook, not a static table.** bashkit's `CommandResolver::resolve(name) -> Option<Arc<dyn Builtin>>` is "called on every unresolved command" so a host can serve `tool-*` names lazily (builtins/mod.rs:540-568). just-bash's `LazyCommand` loads on first use (custom-commands.ts:33-41).

### F4. What the pipe carries, in five designs (READ)

- **just-bash**: stages run **sequentially**; the whole stdout of stage *i* becomes the stdin string of stage *i+1* (just-bash:packages/just-bash/src/interpreter/pipeline-execution.ts:33-100, `result = await executeCommand(command, stdin, !isFirst)` at :98). The pipe contract is bytes: "the next command's stdin is a byte buffer. `stdoutAsBytes` consults the upstream's explicit `stdoutKind`" (:199-215). PIPESTATUS and pipefail are computed from the per-stage codes (:190-196, 245-276). Output is charged to a shared budget (`internalOutputAccounting`, types.ts:50-59). No streaming, no backpressure — correct and simple at agent scale.
- **bashkit**: "bytes are canonical. Text decoding only happens at an explicit consumer boundary; invalid UTF-8 is never rewritten in transport" (bashkit:crates/bashkit/src/stream.rs:1-5); every buffer is admitted against an execution budget before it grows (stream.rs:20-95). `ExecResult` carries `stdout_truncated` (interpreter/state.rs:74-77).
- **lifo**: an async channel of string chunks with one pending reader (lifo:packages/core/src/shell/pipe.ts:1-55); stages run concurrently as `Process` records with pid/ppid/status/abortController (shell/ProcessRegistry.ts:5-45).
- **nushell**: `PipelineData` has four cases, `Empty`, `Value`, `ListStream`, `ByteStream`; the doc comment records the two rejected designs (everything-a-stream; streams-inside-values) (nushell:crates/nu-protocol/src/pipeline/pipeline_data.rs:19-54). Across the plugin boundary the same shape is a header plus stream messages: `PipelineDataHeader::{Empty, Value, ListStream, ByteStream}` and `StreamData::{List(Value), Raw(Result<Vec<u8>, LabeledError>)}` — **each stream is one shape** (nu-plugin-protocol/src/lib.rs:132-145, 350-353). Flow control is explicit: the consumer sends `Ack` per message, the producer blocks past a high-pressure mark of 100 list values or 50 raw buffers (nu-plugin-core/src/interface/mod.rs:25-31, stream/mod.rs:296-357); `Drop` lets the consumer close early (lib.rs:409-420). A `ByteStream` carries its coercion colour `Binary|String|Unknown` on the stream (byte_stream.rs:100-114).
- **elvish**: a `Port` "always consists of a byte band and a channel band" (elvish:pkg/eval/port.go:17-33); the pipeline wires an `os.Pipe` *and* a buffered `chan any` between every pair of forms (compile_effect.go:106-135); `put` writes the value band, `echo` the byte band (builtin_fn_io.go:62-70, 234-241). The July memo already reproduced the cost: cross-band order is nondeterministic and band mismatch deadlocks. I did not rerun that.
- **PowerShell**: a cmdlet is three overridable hooks, `BeginProcessing` / `ProcessRecord` / `EndProcessing`, and `StopProcessing` to interrupt them; output is `WriteObject`, errors `WriteError`, and warnings/verbose/information are separate typed channels (PowerShell:src/System.Management.Automation/engine/cmdlet.cs:141-197, 346-490, 1762-1801). The per-record hook is the streaming unit.

### F5. The bin namespace in Plan 9, and in the agent-shell peers (READ)

- **Union directories, not PATH.** The names paper: "A directory with several services mounted is called a *union* directory and is searched in the specified order … The binaries for a given architecture are contained in a directory named by the architecture, for example `/mips/bin`; in use, that directory is bound to the conventional location `/bin` … A directory of private binaries is usually unioned with `/bin`. (Compare this to the *ad hoc* and special-purpose idea of the `PATH` variable, which is not used in the Plan 9 shell.)" (9front:sys/doc/names.ms:352-400; clone dirty at a0806493 — the paper text is upstream's).
- **rc still has `$path`.** The rc paper documents `path=(. /bin)` (9front:sys/doc/rc.ms:119); `rcmain` sets `path=(/bin .)` by default and `path=/bin` under `-p` (9front:rc/lib/rcmain:12-16). `searchpath(w, "path")` returns the `$path` list unless the word is absolute, `./`, `../` or a `#` device name, in which case the list is the single empty prefix (9front:sys/src/cmd/rc/simple.c:134-146; plan9port:src/cmd/rc/simple.c:100-111). `Xsimple` resolves a word as **function → builtin → exec** in that order (plan9port:simple.c:20-70). So the union is *where binaries live*; `$path` is the *order of directories to search*, and the two compose.
- **`/env` as files.** rc functions persist as `/env/fn#<name>` files and are re-sourced at startup (9front:sys/src/cmd/rc/plan9.c:57, 127-130). Shell state is namespace state.
- **just-bash fakes the union with stubs.** Registering a command writes `/bin/<name>` and `/usr/bin/<name>` stub files "so PATH-based resolution, `which`, `command -v`" work (just-bash:packages/just-bash/src/Bash.ts:584-600); resolution walks `PATH` with default `/usr/bin:/bin` (interpreter/command-resolution.ts:34-110).
- **mcpfs projects tools by shape.** A tool becomes a static file (no required params, read-only), a template directory (required params, read-only), or CLI-only (writes, searches), decided by name verbs and the JSON Schema `required` list (mcpfs:internal/toolfs/classify.go:10-58; README "Classification rules"). The read-only projections are files; everything with arguments stays a command. That is the right split for vfs's `/.agents/tools` versus `/.agents/bin`: a tool's *answer* may be a file; a *program* is always invoked.
- **agentfs** has no program model — only an insert-only `tool_calls` audit table (agentfs:SPEC.md:15-61). **agentvfs** proxies host commands and returns a structured `ExecutionResult {exit_code, stdout, stderr, changed_files, checkpoint, timed_out, …}` (agentvfs:src/runtime/execution.rs:160-178) — the `complete`-record shape again, plus "which files changed", which vfs gets for free from versions.

### F6. Exit codes and error channels (READ)

- POSIX.1-2024 §2.8.2: "If the command is not found, the exit status shall be 127. Otherwise, if the command name is found, but it is not an executable utility, the exit status shall be 126." §2.9.2: the pipeline's status is "the exit status of the last (rightmost) command" unless `pipefail` is set, in which case zero only "if all commands in the pipeline returned an exit status of 0"; the shell "shall use the pipefail setting at the time it begins execution of the pipeline" (https://pubs.opengroup.org/onlinepubs/9799919799/utilities/V3_chap02.html, fetched 2026-10-15).
- toybox: unknown → 127 (main.c:163-168); `error_exit` prints and exits with `toys.exitval` (lib/lib.c:47-56); `TOYFLAG_ARGFAIL(2)` for grep's usage errors. uutils: `UError::code` default 1. just-bash and bashkit: 127 for command not found (bashkit:crates/bashkit/src/interpreter/mod.rs:935-941, 4648).
- nushell has two error channels: a command returns `Err` for fatal failure, and per-row failures ride *in* the stream as error values (July memo §2; `StreamData::Raw(Result<Vec<u8>, LabeledError>)` carries a per-buffer error on the wire too, lib.rs:352).
- MCP 2026-07-28 splits errors in two: **protocol errors** (unknown tool, malformed request, server errors) are JSON-RPC errors "models are less likely to be able to fix"; **tool execution errors** (API failures, input validation, business logic) are results with `isError: true`, and "Clients SHOULD provide tool execution errors to language models to enable self-correction" (modelcontextprotocol:docs/specification/2026-07-28/server/tools.mdx:740-785).

### F7. Environment, arguments, identity (READ)

- WASI's environment is a list of string pairs that "should return the same values each time it is called" (environment.wit) — a frozen snapshot, not a live mapping. just-bash copies the env into a `Map` and separates `exportedEnv` (types.ts:177-184); bashkit gives `env` read-only and shell `variables` mutable (mod.rs:937-947).
- **Nothing identity-shaped rides in env in any peer.** just-bash threads `jsBootstrapCode` and the `invokeTool` hook "through the context chain instead of shell env to prevent user access/injection via environment variables" (types.ts:277-297). bashkit's VFS handle is a revocable capability on the context, not a path or a token (mod.rs:954-959). vfs's rule — identity is a value on the call, never in a string (`authority.py:1-24`) — is the same rule stated as a type.
- argv conventions: busybox/toybox/uutils receive argv including argv[0]; just-bash, bashkit and lifo pass `args` *without* the command name (types.ts:322; mod.rs:932-935). The shell has already done word splitting, quoting and globbing; the program sees words. just-bash's `CommandExecOptions.args` "bypass shell parsing entirely — no escaping, splitting, or globbing" (types.ts:118-123).

### F8. The vfs tree today, measured against the ABI (READ + EXECUTED)

- `run` exists as a verb at `Needs("read")` with the note "`run` waits for its own axis" (src/vfs/ops.py `VERB_RUNGS`); the router routes it to `SupportsRun.run(path, arguments, authority)` and no shipped storage implements it (src/vfs/base.py:1548-1564, 3032-3035; src/vfs/storage/protocol.py:346-355).
- The reserved capability tree has exactly two families, `tools` and `skills`, each a *directory unit* with a manifest (src/vfs/paths.py:51-54; `is_reserved_directory`, paths.py:684-697; `Skill.to_entries`, src/vfs/skills.py).
- `Observation` is frozen and not open; `data`/`content` are XOR; `mime_type` is on the row; bytes cross the wire as base64 (src/vfs/models/entry.py:376-420). `Result` is open (`extra='allow'`) and already carries non-row answers as extras — `grants=`, `members=` — rendered by their own arrangement (src/vfs/results/envelope.py:280-300; render.py `_render_grant_rows`).
- `_DEFAULT_PROJECTION["run"] = ("path",)` (src/vfs/results/projection.py:49-61).
- `render.py` has no placeholder rule for a bytes-bodied row: grep for "placeholder" returns nothing (EXECUTED, 2026-10-15); `_render_read` prints `content or ""`.
- `read` elides `data` unless the column is projected: scenario C of the experiment returned a row with `data=None` and a transient warning "the binary awaits a rendering; run reindex" (src/vfs/storage/backends/database/reads.py:627) until `Cat` asked for `columns={"data", …}` (EXECUTED — see F9, scenario C, before and after the fix).
- The e2 corpus (experiments/e2/commands.md, 12,627 bash calls from 418 transcripts) ranks `grep` 20.9%, `head` 15.8%, `echo` 13.4%, `sed` 12.1%, `cd` 9.3%, `tail` 4.1%, `cat` 3.9%, `ls` 3.1%, `wc` 0.9%, `cut` 0.7%, `awk` 0.5%, `find` 0.4%, `sort` 0.3%. The top text programs are all byte-shaped filters.

### F9. The experiment: the ABI and the two laws, executed (EXECUTED)

`experiments/s3/abi_demo.py` defines, as Python Protocols:

- `Chunk = Rows(result: Result) | Bytes(data: bytes, mime_type)`; a stream is `AsyncIterator[Chunk]`; `ROWS_PER_CHUNK = 1000`.
- `Fs` — `ls/read/glob/grep/write`, each re-entering the public router method with one bound `Authority` (`BoundFs`).
- `Call(args, env, cwd, stdin, stdout: Sink, stderr: TextSink, fs)`.
- `Program(name, consumes: Shape, produces: Shape, main(call) -> int)`.
- Programs: `ls`, `cat`, `glob`, `grep` (verb builtins, rows→rows); `wc` (text kernel, bytes→bytes, counts chunks it sees); `id.wasm` (wasi stub: stages all of stdin, echoes it, `--exit N`, `--stderr`).
- Laws: `rows_to_bytes` (single bytes-bodied `read` row → raw; else `result.to_str()` + newline) and `bytes_to_rows` (one row at `/.vfs/run/<stage>/stdout`, UTF-8-without-NUL → `content`, else `data` + `sniff_mime`).
- Runner: one task per stage, `asyncio.Queue(maxsize=2)` between stages, PIPESTATUS, `$?` = last, pipefail = rightmost non-zero, stderr lines prefixed by program name in arrival order.

Output (`experiments/s3/abi_demo.out`), condensed:

| scenario | result |
|---|---|
| A `ls /src \| wc -l` | wc received `'/src/README.md\n/src/auth.py\n/src/db.py\n'` (scenario H prints the bytes) and emitted `3\n`; the terminal row is `path=/.vfs/run/2/stdout mime=text/plain content='3\n'`; **default render printed the path**, projection `content` printed a Markdown table |
| B `cat /src/auth.py \| wc` | `3 5 35` — the read row crossed as its body, not as a table |
| C `cat /img/logo.png \| id.wasm` | before the fix: `data=None`, a transient WARNING crossed as text. After projecting `data`: 32 raw bytes crossed; stdout sniffed to `mime=image/png`, `data_len=32`, `content=None`, `populated=[data, kind, mime_type, path, size_bytes]`; the terminal **printed only the synthetic path** (no placeholder rule exists) |
| D `glob '**/*.py' \| grep auth` | `/src/auth.py:2:    return 'auth ok'`; `ops=('grep',)`; grep scoped to the 2 upstream rows via `observations=`, no text parsed |
| E `ls /nope \| wc -l` | stderr `ls: ERROR /nope: Not found — Check the path … (retry: never)`; `PIPESTATUS=[1, 0] $?=0 pipefail=1`; wc still ran. First run printed `1` — it counted the rendered error line (awkwardness 5); after the one-line fix (errors never cross a byte seam) the committed output prints `0`, as Unix does |
| F `cat /src/db.py \| id.wasm --exit 3 --stderr boom` | stderr `id.wasm: boom`; `PIPESTATUS=[0, 3] $?=3`; the body came back as a row whose Markdown-table render squashed its newlines |
| G 10,000 files, `ls /big \| wc -l` | `10000`; `ls` emitted 10 chunks, `wc` saw 10 byte chunks, **max queue depth 2** — the producer never ran more than two chunks ahead |

What the exercise taught — where it was awkward:

1. **A program's output needs an address.** `Observation.path` is required, so `bytes_to_rows` had to mint one. I used `/.vfs/run/<stage>/stdout`. It is a derived view under the reserved meta root, like the trash view — and it is useful: a large output can be elided at the boundary and read back later by path (nu-mcp's `$history.N`, July memo §2.2, done as a vfs path).
2. **`run` rows do not render.** The default projection for `run` is `("path",)`, so `ls | wc -l` printed `/.vfs/run/2/stdout`; asking for `content` fell into the Markdown-table arrangement, which squashes newlines by design (render.py `_escape_table_cell`). Program output needs the verbatim arrangement `read` has.
3. **`read` elides `data` by default.** Right for an agent reading a PDF; wrong for a byte-shaped consumer. The `cat` builtin must project `data` (and `content`, `mime_type`, `size_bytes`) when its consumer is byte-shaped. The shape of the *consumer* decides what the *producer* fetches — a planning fact the shell knows before running.
4. **No placeholder rule yet.** The png row rendered as its path alone. The July memo's Q6 rule (path + mime + size, never base64) is not in `render.py`. The content-channel ADR (5) owns it; the shell depends on it.
5. **Errors crossing a byte seam become text.** In E, `ls /nope` produced zero rows and one fatal fact; `rows_to_bytes` rendered the result, whose text is the error line, and `wc -l` counted it. In Unix the error would be on fd 2 and `wc` would print 0. The law must be: **errors never cross a byte seam** — they go to the stage's stderr, and only rows render into the pipe. The stage already wrote the same line to stderr, so the fix was one line — render `Result(ops, observations)` without errors — and the rerun printed `0` (the committed `abi_demo.out`). Noted as a rule below.
6. **Chunked rendering changes ordering semantics.** `_render_path_list` sorts rows by path per call; rendering per chunk sorts per chunk. It was invisible here because `ls` returns rows already path-ordered, but a globally-sorted arrangement (`tree`, a merged fan-out) cannot stream. The rule: an arrangement that needs the whole result materializes (and says so); the row-ordered ones stream.
7. **`wc -l` after `ls` counted entries; after `cat` it counted lines.** That is the point of the row→bytes law: the producing op's default projection *is* its Unix stdout. No special case was needed.
8. **The exit code of a verb failure is a mapping, not a fact the storage knows.** `exit_code_for(result)` walks the fatal facts' families. It belongs in the shell, in one table (below).

---

## What this means for vfs

### The ABI — one typed signature

Written as the Python shape the kernel implements; the Rust kernel, the wasm host and the guest interpreters bind to the same fields (next section).

```python
Shape = Literal["rows", "bytes"]

class Chunk:                     # exactly one of the two, never both
    Rows(result: Result)         # a slice: rows + classified errors, op-tagged
    Bytes(data: bytes, mime_type: str | None)

class Fs(Protocol):              # the verb capability, bound to ONE Authority
    async def ls(path, *, columns) -> Result
    async def read(path, *, columns) -> Result
    async def glob(pattern, *, observations, …) -> Result
    async def grep(pattern, *, observations, …) -> Result
    async def glean(…) / graph(…) / stat(…) / tree(…) -> Result
    async def write(path | entries, *, content | data, …) -> Result
    async def edit(…) / mkdir(…) / move(…) / copy(…) / delete(…) -> Result
    # No authority parameter exists. No run(). No grant family.

@dataclass(frozen=True)
class Call:
    args: tuple[str, ...]        # argv[1:], already split/quoted/globbed by the shell
    env: Mapping[str, str]       # a frozen snapshot; never carries identity or secrets
    cwd: Path                    # the shell's working directory, a canonical Path
    stdin: AsyncIterator[Chunk]  # chunks of the program's declared `consumes` shape
    stdout: Sink                 # emit(chunk) of the declared `produces` shape; awaits backpressure
    stderr: TextSink             # write(text); text only; never rows, never bytes
    fs: Fs                       # the only door to the namespace
    budget: Budget               # deadline, cancel token, output byte cap — read-only

class Program(Protocol):
    name: str                    # the native Unix name the agent types
    consumes: Shape
    produces: Shape
    forms: Forms                 # the declared flag grammar; what this kind implements
    async def main(self, call: Call) -> int   # the exit status; nothing else is returned
```

Field by field:

- `args`: words. The shell owns parsing (ADR 1's grammar); a program never sees quotes or `$VAR`. argv[0] is not included; `name` already says what was typed (just-bash, bashkit, lifo convention).
- `env`: a copy, frozen for the call (WASI's "same values each time"). `PATH`, `HOME`, `PWD`, user exports. **Never** an authority, token, database URL or model key — those are unreachable by construction (hermetic memo §5 risk 4; just-bash's `jsBootstrapCode` precedent).
- `cwd`: a `Path`. Relative arguments resolve against it in the program, with `Path.joinpath`.
- `stdin`/`stdout`: the pipe (next section). A program that ignores stdin (`ls`) still receives one; the runner drains it. `emit` awaits, so a slow consumer slows the producer (G: depth never exceeded 2).
- `stderr`: text, line-oriented, never structured. It carries the rendered error lines of a verb result and a program's own diagnostics. It never enters the pipe (`|&` is a shell-surface question; if ADR 1 adopts it, stderr text becomes a `Bytes` chunk at that seam).
- `fs`: the capability. It is `VirtualFileSystem` with the call's `Authority` curried in, so every verb re-enters the public method and every gate fires (ops.py's `cli` rule). It exposes no `run` (a program does not spawn — `xargs`/`find -exec` are shell builtins that resolve names through the union, bashkit's `ExecutionPlan` pattern) and no grant verbs.
- `budget`: deadline and cancellation (just-bash `AbortSignal`, nushell's per-item signal check, bashkit's `ExecutionDeadline`) plus an output cap; exceeding it classifies `vfs.budget_exhausted.truncated` on the stage and exits 124/130 (table below).
- Return: an `int`. Rows and errors have already gone out through `stdout`/`stderr`. The envelope's verdict for the whole command is derived from exit codes, never asserted.

### The three program kinds, and how each binds the ABI

| kind | lives | consumes/produces | `fs` binding | args/env | exit |
|---|---|---|---|---|---|
| **Builtin** (verb program) | kernel, Python, `src/vfs/shell/programs/` | rows → rows (most); `write`-family consume bytes too (`echo x \| write /f`) | direct: `call.fs.<verb>(…)`; emits `Rows(result)` in `ROWS_PER_CHUNK` slices; errors → stderr lines + exit code via the table | Python | `exit_code_for(result)` |
| **Kernel** (text program) | `crates/vfs-core`, exposed through the `vfs/native.py` seam; a thin Python `Program` wrapper streams byte chunks in and out | bytes → bytes (`wc`, `head`, `tail`, `sed`, `cut`, `sort`, `uniq`, `tr`, `nl`, `grep -c`…) | none — a text filter touches no file; a form that needs a file (`sed -i`, `sort -o`) is a *builtin* that reads/writes through `fs` and calls the kernel on bytes | argv parsed by the declared `forms` grammar (toybox-style option string, F2) | the kernel's code; usage error 2 |
| **Guest** (wasm binary, guest script) | an entry in the bin namespace: `/.agents/bin/jq.wasm`, `/.agents/bin/report.py`; executed by `run` | bytes → bytes, always (murex/TermKit lesson: externals never speak rows) | **wasm**: our preview1/`wasi:cli` shim implements `path_open`/`fd_read`/`fd_write`… over `call.fs.read`/`write` with whole-file staging (hermetic memo §4.3); one preopen named `/`. **Script** (Monty, QuickJS, CPython-on-WASI): `external_lookup`/host functions are the `Fs` methods, nothing else | `args_get`/`environ_get` (wasm) or an injected `sys.argv`/`os.environ` snapshot (script) | `proc_exit`/`exit(status)` or the script's return; a trap or timeout maps by the table |

The kind is invisible on the pipe: a consumer sees chunks of the declared shape, never the implementation. That is what lets a name change kind (next section).

### One name, many kinds over time (the coordinator's rule)

1. **The name is the contract; the kind is a table entry.** The union (next section) resolves `sed` to *whatever row the kernel table or the bin directory holds today*: a builtin that covers the measured forms (e2: `sed -n '…p'`, `sed -i`, substitutions), later a Rust kernel, later a wasm build of real sed installed at `/.agents/bin/sed.wasm` and promoted by the host. The agent types `sed` throughout. This is busybox/toybox's model (F1): the row's flags choose the strategy; the name does not change.
2. **Forms are declared, so the shell can refuse by name.** Each program row carries `forms: Forms` — a declarative grammar in toybox's option-string style (F2), extended with a `supported` subset when the implementation covers only some forms. On parse, the shell checks the typed flags against `forms`; a flag the grammar knows but this kind does not implement produces a classified `vfs.unsupported.form` fact with `data={"program": "sed", "form": "-i", "kind": "builtin"}` and the detail naming the form; the stage exits **2** (toybox's `TOYFLAG_ARGFAIL(2)` and GNU grep's usage code), stderr gets the one line with the contract hint ("the form is not implemented by this program yet"). A flag the grammar does not know at all is `vfs.invalid` (the caller's typo), also exit 2. The child kind degrades to `vfs.unsupported` for older clients (`kind_family`). `ErrorKind`'s producer-exclusivity rule ("only capability gates emit `unsupported`") holds: the forms check *is* a capability gate.
3. **Parity is a test, not a promise.** When a name changes kind, the old implementation becomes the oracle in `tests/support/oracles/` and a parity test pins the new one over the e2 corpus forms (ADR 057's pattern). The agent-facing surface — name, forms, exit codes, stdout bytes — is the test's assertion.
4. **Growth is additive.** Adding a program is adding a row (kernel table) or writing an entry (bin dir). Adding a form is widening `forms.supported`. Neither touches the shell's parser, the pipe, or the seams. "Capability grows by adding programs without touching the shell" holds by construction.

### The bin namespace

**Where.** A third reserved family: `AGENT_FAMILIES = {"tools", "skills", "bin"}`, root `/.agents/bin`. Unlike `tools` and `skills`, whose unit is a *directory* with a manifest, `bin`'s unit is a **file**: `/.agents/bin/<name>` or `/.agents/bin/<name>.<ext>` whose body is the program (a `.wasm` binary as `data`; a script as `content`). The name the agent types is the file name without its extension; `jq.wasm` serves `jq`. Why not a top-level `/bin`: agents ingest whole repositories at `/`, and `bin/` is an ordinary directory in thousands of them; a reserved `/bin` would collide with user data on the first `write /bin/setup.sh`. The `/.agents` tree is the one place vfs already owns, its rules already exist (`is_reserved_directory`), and it is what the eve/skills convergence put there (open question "Where does an agent's bundle live").

**The union, in order (Plan 9's `/bin`, rc's `$path`):**

1. **Shell builtins that must be builtins** — the words that change shell state: `cd`, `export`, `unset`, `exit`, `set`, `source`, `alias`. Not programs; not in the table; the shell handles them before resolution (rc's `Xsimple`: function → builtin → exec).
2. **The kernel program table** — the verb builtins and the Rust kernels compiled into vfs: `ls`, `cat`, `grep`, `head`, `sed`, … A static sorted table of `(name, kind, forms, program)` — busybox's applet table in Python.
3. **`$PATH`**, a colon-separated list of *namespace* directories, default `/.agents/bin`. Each is searched in order with `stat` under the caller's authority; the first entry whose name matches wins. A mount's own `/proj/.agents/bin` joins when the agent or host puts it on `PATH` — so the bin directory is **per-namespace, not per-mount**; mounts contribute by being listed. Identity threads through unchanged, since every `stat` and `read` is a verb call.

A word with a slash (`/.agents/bin/jq.wasm`, `./x.wasm`) skips the union and names the entry directly (rc's `searchpath` rule).

**Shadowing.** Layer 2 precedes layer 3 by default: a stored entry can *add* a name but cannot shadow a kernel name. Promotion of a stored program over a kernel name (the "wasm build of the real program tomorrow" case) is a **host decision** — `VirtualFileSystem(shell=…, prefer_stored=("sed",))` or a mount-level setting — never an agent's write. Rationale: a shared namespace is multi-principal; an agent that could shadow `grep` for everyone by writing one file is the supply-chain hole Plan 9 avoids by making the union order per-process. Agents get the same effect privately by prepending their own directory to `PATH` (`$HOME/bin`), which shadows for *their* session only.

**What `run` does.** `run` is the verb that executes a stored program. The `cli` meta-verb reduces `jq .x < f` to: resolve `jq` through the union → a bin-dir entry `/.agents/bin/jq.wasm` → `run("/.agents/bin/jq.wasm", arguments={"argv": [".x"], "stdin": …})`, which the shell's `SupportsRun` implementation (the wasm host or the guest runtime) serves by binding the ABI above. Builtins and kernels do not go through `run`; they are the shell's own code. So "is this name a program the caller may execute?" has two answers: a kernel name is always executable (the verbs it calls gate themselves); a stored name needs the rungs below.

**The rungs.** To *resolve* a stored program the caller needs `list` on its entry (the row must be visible; ADR 066's hidden rows make an unlisted program simply not found). To *execute* it the caller needs `read` on the entry (`run`'s current `Needs("read")`) — the bytes are the program — plus whatever execute policy ADR 4 adds on `run`'s own axis. The program then holds exactly the caller's authority for every verb it calls: no ambient widening, no setuid (busybox's `BB_SUID_*` column is the thing we deliberately do not have).

**Listing.** `ls /.agents/bin` shows the stored layer (ordinary entries). The kernel layer is not stored, so it is not listed there; the shell's `type`, `which`, `command -v` and `help` answer from the whole union. This is Plan 9's own split (rc builtins are not in `/bin`), and it avoids a synthetic read-only mount for v1. If agents turn out to `ls` the bin dir expecting builtins, a `ProgramTable` storage mounted beneath `/.agents/bin` is the Plan 9-pure answer; it is a fork below, not a v1 need.

### The pipe payload and the two laws

**Decision: one ordered stream of chunks, each chunk Rows or Bytes, never both; a program declares its shape on each side; conversion happens only at a seam where the shapes differ.** This is nushell's `PipelineData` restricted to the two cases vfs has (a `Result` slice is the `ListStream` of rows; `Empty` is an empty slice; `Value` is a one-row slice), with nushell's law kept intact: *values are never lazy; laziness lives only in the channel.* A `Result` in a chunk is a complete, frozen envelope. It is **not** elvish's two parallel bands — one ordered sequence is what keeps "stderr line 3 came after row 2" meaningful and avoids the band-mismatch deadlock.

**Rows → bytes** (fires only when the consumer is byte-shaped):

1. If the chunk is a single `read` row whose body is `data`, the bytes cross **raw** with the row's `mime_type` on the `Bytes` chunk (scenario C). A byte program asked for the file; it gets the file. This is PowerShell's `PSNativeCommandPreserveBytePipe`, built in from day one instead of eighteen years later.
2. Otherwise the chunk's **rows** render through the one chokepoint, `render_result`, with the producing op's default projection, plus a trailing newline (scenarios A, B, H). `ls` → one path per line; `read` → the body verbatim (or `==> path <==` blocks for several); `grep` → `path:line:text`; `stat` → its block. This is the canonical, width- and ANSI-independent text the MCP text block already carries, so the display-format-as-wire-format wart does not apply: the renderer *is* the wire's text projection by design (render.py module docstring).
3. **Errors never cross a byte seam.** The slice's `errors` go to the producing stage's stderr as rendered lines; only `observations` render into the pipe (awkwardness 5). A fatal verb failure with zero rows yields zero bytes downstream and a non-zero PIPESTATUS entry.
4. A bytes-bodied row in a multi-row render becomes the placeholder (path, mime, size) once ADR 5 lands the rule in `render.py`; until then it renders as its path, which is what the experiment shows.
5. For consumers that want structure rather than text — `jq` — the explicit builtin `to-json` (nushell `to json`, elvish `to-json`) emits `Result.to_payload()` as one `Bytes` chunk of `application/json`, and `from-json` reverses it. Rows stay the default; JSON is asked for. (Fork below.)

**Bytes → rows** (fires only when the consumer is row-shaped, including the terminal boundary):

1. The whole byte stream of the stage becomes **exactly one row** (a program output is one thing, nushell's `complete` record), minted at end of stream so a split UTF-8 sequence cannot be mis-sniffed.
2. Valid UTF-8 without NUL → `content`, `mime_type` the producer's or `text/plain`; anything else → `data`, `mime_type` from `sniff_mime` with the producer's declared mime as the fallback (scenario C: 32 raw bytes → `image/png`). `populated` = the fields set.
3. The row's path is `/.vfs/run/<call-id>/stdout`, a derived address under the meta root; `kind="file"`. The same call's `stderr` text and exit code ride as **extras** on the `Result` (`exit_code=`, `pipestatus=`, `stderr=`), the `grants=` precedent — facts about the execution, not rows of the namespace.
4. `_DEFAULT_PROJECTION["run"]` becomes `("content",)` and `_render_body` routes `run` to the verbatim arrangement `read` uses (awkwardness 2). A bytes-bodied output row renders the placeholder like any other.
5. Budget: if the output exceeds the boundary cap, the row is elided to the placeholder and the full bytes are retained at the `/.vfs/run` path for a `read` later (nu-mcp's handle; July memo Q5). Retention policy is ADR 5's.

**Same shape** → the chunk passes untouched. Rows → rows is the verb-chain case (`glob | grep`, scenario D): the consumer receives `Observation`s and passes them as `observations=`; no path is ever re-parsed from text. Bytes → bytes is the text-filter chain (`cat f | sed | head`): raw bytes, no decoding, bashkit's "bytes are canonical" rule.

**The producer fetches what the consumer needs.** The shell knows both shapes before it runs the pipeline, so a `read`/`cat` whose consumer is byte-shaped projects `data` (awkwardness 3), and one whose consumer is row-shaped keeps the elide-by-default posture. Planning, not sniffing.

### Exit code, stderr, isError — the one table

| event | `$?` of the stage | stderr | `success` of the stage's Result | MCP `isError` (whole command) |
|---|---|---|---|---|
| verb result succeeds, no errors | 0 | — | true | false |
| verb result succeeds with warnings/info | 0 | the warning/info lines | true | false |
| verb result fails (`not_found`, `exists`, `wrong_kind`, `invalid`, `conflict`, `busy`, `cross_mount`, `unavailable`…) | **1** | the error lines | false | true if this is `$?` |
| program's own non-zero exit | its code | its stderr text | n/a (bytes) | true if this is `$?` |
| unknown flag (`vfs.invalid`) or unimplemented form (`vfs.unsupported.form`) | **2** | one line naming the form | false | true |
| name not resolvable in the union; stored entry not `list`-able | **127** | `<name>: command not found` | `vfs.not_found` on the shell's own result | true |
| name resolves but the caller lacks `read`/execute on it; `run` refused (`permission_denied`, `unauthenticated`, `unsupported` from the backend, `deny_ops`) | **126** | the error line | false | true |
| deadline passed (`vfs.timeout`) | **124** (GNU `timeout`) | the error line | false | true |
| cancelled (`vfs.cancelled`) | **130** (128 + SIGINT) | the error line | false | true |
| output cap hit (`vfs.budget_exhausted.truncated`) | 0 if the program finished, with the warning; else the code above | the warning line | true (warning) | false |
| a Python exception escaping a builtin | **1**, `vfs.internal` with the detail | the error line | false | true — and a bug to fix (ADR 076: raw exceptions are bugs) |

Composition: `$?` of a pipeline is the last stage's code, or the rightmost non-zero when `pipefail` is set, evaluated with the setting at pipeline start (POSIX §2.9.2). `PIPESTATUS` is the vector. The MCP tool result for a command is: `isError = ($? != 0)`; `content[0]` the text rendering of the terminal `Result` (rows) followed by the stderr lines, in that order; `structuredContent` the terminal `Result`'s payload with the `exit_code`/`pipestatus`/`stderr` extras. A verb name the server does not know stays a JSON-RPC protocol error (MCP's own split); everything a model could fix — including 127 — is a tool execution error.

### Streaming and chunking — the rule

- A producer hands the pipe at most `ROWS_PER_CHUNK` rows per `Rows` chunk (1000 in the experiment; the real number is a declared constant, like `in_list_budget`) and at most `BYTES_PER_CHUNK` per `Bytes` chunk (64 KiB is the conventional pipe buffer).
- Each seam is a bounded queue of depth `QUEUE_DEPTH` (2 in the experiment). Memory per seam is therefore bounded by `depth × chunk`, independent of batch size — the 10,000-row `ls` ran with a maximum depth of 2 (scenario G). This is nushell's Ack high-pressure mark in process; across a worker process (the wasm host — wasmtime-py's trap global is not thread-safe, hermetic memo §4.1) it becomes the same Ack protocol over the pipe.
- A row-shaped consumer that *must* see everything (grep scoping, a global sort, `tree`) materializes, and its memory is the batch; that is honest and stated in the program's docstring (CLAUDE.md: name the profile, never a cap). Everything else streams.
- Arrangements that are order-sensitive across chunks (`tree`, `_render_path_list`'s per-call sort) either receive path-ordered rows from storage (true for `ls`, `glob`) or materialize; the renderer is not changed to stream.
- Performance pins count chunks, rows and verb calls — scenario G's "10 chunks, depth 2" is the shape of the test — never seconds.
- A consumer may stop early (`head -3`): closing its stdin cancels the producer at its next `emit` (nushell's `Drop`; elvish's `readerGone`), and the producer's stage reports `vfs.cancelled` as *info*, not failure — `yes | head -1` is a success in every shell.

### What to adopt, what to reject

Adopt: the six-in/three-out ABI (every peer); the applet table with declared forms (busybox, toybox, uutils, nushell `Signature`); two pipe shapes with values-never-lazy (nushell); bytes-canonical between byte programs (bashkit, just-bash); raw byte pass-through for a single file body (PowerShell BytePipe); Ack-bounded streaming (nushell plugins); union-ordered resolution with `$path` (Plan 9 rc); revocable, bound capability as the only door (bashkit, just-bash `trusted: false`, WASI preopens); the `complete`-record shape for a program's execution facts as `Result` extras (nushell, agentvfs); stderr as a separate text channel that never enters the pipe (POSIX).

Reject: two parallel bands per pipe (elvish — nondeterministic order, deadlocks); the human table formatter as the structured→external wire (nushell's wart) — our renderer is canonical and ANSI-free, and JSON is explicit via `to-json`; stub files for builtins in the bin directory (just-bash) — they rot on upgrade and lie about permissions; a top-level `/bin` (collides with ingested repositories); agents shadowing kernel names by a write; identity or secrets in `env`; programs that spawn programs directly (`xargs`/`find -exec` are shell builtins that re-enter the union); sequential whole-string pipes (just-bash) at 10k-row scale — fine for them, not for a 10,000-file batch contract.

---

## Forks for the ADRs

1. **Rows, bytes, or both-tagged in the pipe?** (a) rows only, every text program consumes a rendering; (b) bytes only at v1, structure later (open question "Shell pipe payload"); (c) both, each chunk one shape, programs declare shapes, two laws at the seams. **Lean (c)**: it is what nushell landed after rejecting (a)'s cousin, it made `ls | wc -l` and `cat f | wc -l` both correct with no special case (EXECUTED), and (b) would force `glob | grep` to re-parse paths from text — the one thing the envelope was built to avoid.
2. **The structured→bytes form for structure-wanting programs.** (a) JSON lines by default at every row→bytes seam (the July lean); (b) canonical text by default, `to-json`/`to-payload` explicit. **Lean (b)**: the e2 corpus is 80% text filters that want text; JSON-by-default would print JSON to the agent whenever a verb feeds `head`. Sub-fork: whether a program may declare `consumes: "json"` so `jq` gets the payload without `to-json`. Lean: not at v1.
3. **May a program call verbs directly, or only through the `Fs` capability?** (a) builtins import the router and pass `authority` themselves; (b) every kind, builtins included, gets only `call.fs`. **Lean (b)**: one door, and a builtin cannot even *express* a widened call. The cost is one more object; the gain is that "no side door" is a type, not a review rule.
4. **Are builtins entries in the bin directory?** (a) yes, as stub entries (just-bash); (b) yes, via a synthetic read-only `ProgramTable` storage mounted under `/.agents/bin` and unioned with the stored layer (Plan 9 pure); (c) no — the stored layer is listed by `ls`, the whole union by `type`/`which`/`help`. **Lean (c) for v1, (b) if agents prove to `ls` the bin dir expecting builtins.** (a) is rejected: stubs rot on upgrade and misreport permissions.
5. **Per-mount or per-namespace bin directory?** (a) every mount's `/.agents/bin` auto-joins the union; (b) the union is `$PATH`, default the root's `/.agents/bin`; a mount joins by being listed. **Lean (b)**: auto-joining a mounted stranger's bin directory is exactly how a mounted repository would inject a `grep`; `PATH` keeps it opt-in and per-session (Plan 9's per-process namespace).
6. **Who may shadow a kernel name?** (a) stored entries win (latest install wins); (b) kernel wins; the host promotes a stored program by configuration; agents shadow only via their own `PATH` prefix. **Lean (b)** — the supply-chain argument above.
7. **The output row's address.** (a) a synthetic `/.vfs/run/<id>/stdout` path, readable later under budget; (b) a row with a nominal path and the bytes only in extras; (c) no row — the execution facts live only in extras and the terminal renders them. **Lean (a)**: it keeps `| write /out.txt` and `| head` working on rows, and the read-it-back handle is the only scalable answer to large outputs.
8. **The exit code of a failed verb.** (a) always 1; (b) per-family codes (the table: 1/2/124/126/127/130). **Lean (b)**: 126/127 are POSIX, 124/130 are the universal conventions agents already know, and the family map is six lines.
9. **Which family is `unsupported.form`?** (a) a child of `vfs.unsupported` (degrades gracefully, keeps producer exclusivity by calling the forms check a capability gate); (b) a child of `vfs.invalid` (the caller sent something this program cannot take). **Lean (a)**: the caller did nothing wrong; the program is not yet able — "retry: never, use another form" is the honest hint.
10. **Early close.** Does `head -3` cancelling `cat bigfile` report `cancelled` as info (lean), or nothing at all?

---

## Sources

- busybox @ 371fe9f (GPL-2.0, studied only): `include/applets.src.h:9-24, 76-81`; `libbb/appletlib.c:177-230, 953-973`; `docs/nofork_noexec.txt:1-40`.
- toybox @ 6a0c0ef (0BSD): `toys.h:77-119`; `main.c:8-21, 30-60, 163-168, 270-296`; `lib/args.c:12-100`; `toys/posix/wc.c:7`; `toys/posix/grep.c:10`; `lib/lib.c:47-56`.
- uutils-coreutils @ 4945ecf (MIT): `src/bin/coreutils.rs:55-96`; `src/uucore/src/lib/lib.rs:219-262`; `src/uucore/src/lib/mods/error.rs:170-223`; `src/uu/wc/src/wc.rs:383-392`.
- just-bash @ 9ab0e0d (Apache-2.0): `packages/just-bash/src/types.ts:15-45, 118-123, 170-330`; `custom-commands.ts:33-41, 100-106`; `Bash.ts:568-600`; `interpreter/pipeline-execution.ts:33-100, 190-215, 245-276`; `interpreter/command-resolution.ts:34-110`; `THREAT_MODEL.md:35`.
- bashkit @ b7904a4 (MIT): `crates/bashkit/src/builtins/mod.rs:540-568, 931-971, 1353-1500`; `src/stream.rs:1-95`; `src/interpreter/state.rs:65-80`; `src/interpreter/mod.rs:935-941, 4648`; `src/execution_capability.rs:38-178`; `docs/custom_builtins.md:1-80`; `CHANGELOG.md:598-604`.
- nushell @ 818d4ac06 (MIT): `crates/nu-protocol/src/pipeline/pipeline_data.rs:19-54`; `pipeline/byte_stream.rs:100-114`; `pipeline/list_stream.rs:16-28`; `signature.rs:360-377`; `engine/command.rs:56-116`; `crates/nu-plugin-protocol/src/lib.rs:132-145, 214-220, 299-321, 350-353, 409-432`; `crates/nu-plugin-core/src/interface/mod.rs:25-31`; `interface/stream/mod.rs:296-357`.
- elvish @ 26a8bd5 (BSD-2): `pkg/eval/port.go:17-33, 80-140`; `pkg/eval/compile_effect.go:85-145`; `pkg/eval/builtin_fn_io.go:55-70, 234-241`; `pkg/eval/callable.go:4-7`; `pkg/eval/frame.go:22-37, 91-110`.
- PowerShell @ db1d0a5 (MIT): `src/System.Management.Automation/engine/cmdlet.cs:33, 141-197, 346-490, 1762-1801`.
- lifo @ 5a35d05 (MIT per package.json): `packages/core/src/commands/types.ts:1-35`; `shell/ProcessRegistry.ts:5-80`; `shell/pipe.ts:1-55`.
- plan9port @ b6564bd9 (MIT): `src/cmd/rc/simple.c:15-130`.
- 9front @ a0806493 (**DIRTY clone, not refreshed**; no licence file — studied only): `sys/doc/names.ms:352-400, 580-595`; `sys/doc/rc.ms:119`; `rc/lib/rcmain:12-16`; `sys/src/cmd/rc/simple.c:134-160`; `sys/src/cmd/rc/plan9.c:50-70, 115-140`.
- mcpfs @ 640511e (MIT): `README.md:1-60`; `internal/toolfs/classify.go:1-120`.
- agentfs @ 0a014eb: `SPEC.md:15-124`. agentvfs @ 82663b4 (MIT): `README.md:30-60, 104-135`; `src/runtime/execution.rs:160-178`.
- WASI @ 463701e and componentize-py @ 9ff99da (Apache-2.0): `componentize-py/wit/deps/cli-0.2.0/{command,run,exit,environment,stdio,imports}.wit`; `componentize-py/examples/cli/app.py`, `README.md`.
- modelcontextprotocol @ 86f6e0c6: `docs/specification/2026-07-28/server/tools.mdx:380-500, 736-785`.
- POSIX.1-2024 Shell Command Language §2.8.2, §2.9.1, §2.9.2: https://pubs.opengroup.org/onlinepubs/9799919799/utilities/V3_chap02.html (fetched 2026-10-15).
- vfs live tree (this repo, 2026-10-15): `src/vfs/ops.py`; `src/vfs/base.py:334-362, 879-947, 1548-1564, 3032-3035`; `src/vfs/storage/protocol.py:346-355`; `src/vfs/results/envelope.py`; `src/vfs/results/render.py`; `src/vfs/results/projection.py:49-61`; `src/vfs/results/kinds.py`; `src/vfs/models/entry.py:376-420`; `src/vfs/models/media.py:85-110`; `src/vfs/paths.py:51-54, 684-697`; `src/vfs/skills.py`; `src/vfs/authority.py:1-24`; `src/vfs/storage/backends/database/reads.py:627`; `context/research/2026-07-24-hermetic-runtime-and-wasm-cli.md` §1-§4; `context/research/2026-07-25-multimodal-result-content.md` §2.1-2.3, §4; `context/open-questions.md` ("Per-path / per-principal execute policy", "Shell pipe payload", "Where does an agent's bundle live"); `experiments/e2/commands.md` (the measured corpus).
- Experiment: `experiments/s3/abi_demo.py`, output `experiments/s3/abi_demo.out` (EXECUTED 2026-10-15 with `uv run python`).
