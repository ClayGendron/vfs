# 11. The agent shell, programs and the fronts (planned)

- **Status:** living diagram, drawn 2026-10-24. **Nothing on this page
  is built.** It draws the decided target: ADRs 081 to 086 (proposed
  2026-10-15 and 2026-10-16) and specs 167 to 172; specs 167, 171 and
  172 carry rebase notes of 2026-10-24 for ADR 087.
- **Shows:** how an agent's command line becomes gated kernel calls;
  the six kinds of program behind one ABI; the pipe; the `/.vfs`
  views; the MCP adapter; the WASI mount for a Python guest.
- **Legend:** every box here is planned. The spec that lands each is
  named on it.
- **Sources:** ADR 081 (the grammar), 082 (programs and views), 083
  (the pipe), 084 (the execution policy), 085 (the content channel),
  086 (Python in vfs); specs 167, 168, 169, 170, 171, 172; the memos
  of 2026-10-15 (the agent shell) and 2026-10-23 (wasi-python over
  vfs).

## The picture: a command line becomes kernel calls

```mermaid
flowchart TB
  cmd["cli: grep -rn mfa /enterprise | head -20<br/>(the one programmatic execution door; a verb on the router and the Session)"] --> parse["Parser (shell/parse.py, spec 167 B)<br/>the whole string to an AST before anything runs<br/>bash-shaped POSIX subset; refused constructs are classified facts (ADR 081)"]
  parse --> resolve["Resolve each name (ADR 082 pin 10)<br/>shell builtins → the kernel's program table → /.vfs/bin in index order<br/>a stored program needs read on its entry: 127 cannot list, 126 cannot read"]
  resolve --> plan["Plan the pipeline (shell/run.py, spec 167 C)<br/>shapes known before running: rows or bytes per seam<br/>budgets set: stages, argv bytes, fan-out, stdout bytes, wall time"]
  plan --> run["Run the stages"]
  subgraph stages["Each stage is a Program behind one ABI (ADR 082 pin 1)"]
    abi["Call: args, env, cwd, stdin, stdout, stderr, fs, budget<br/>declares name, consumes, produces, forms"]
    fs["fs = the router's verbs curried with the caller's Authority<br/>VirtualFileSystem.bound(authority); no authority parameter, no grant verbs, absolute paths only<br/>every call re-enters the public router method, so every gate fires (ADR 084)"]
  end
  run --> stages
  stages --> gate["THE GATE (diagram 04): capability → grammar → permission, on every verb"]
  gate --> result["one cli Result: stdout then stderr as the display,<br/>rows as the structured stdout, classified errors, exit code and the status list"]
```

## The picture: six kinds behind one name

```mermaid
flowchart LR
  name["a program name, e.g. grep, sed, python3, my_tool"] --> table["the program table: (name, kind, forms, program)<br/>the name is the contract; the kind is a table row"]
  table --> k1["Verb builtin<br/>the shell's code over vfs verbs<br/>ls, cat, grep, find, mkdir ... (spec 167)"]
  table --> k2["Text program<br/>Python shell around a Rust kernel, bytes to bytes<br/>sed, awk, cut, sort, wc, diff ... (spec 168)"]
  table --> k3["Program<br/>wasm bytes stored in vfs, run in a sandbox as the caller<br/>installed by write into /opt/bin (spec 169)"]
  table --> k4["Tool<br/>a Python function the host registered, run in the host process<br/>with the host's authority (spec 170)"]
  table --> k5["MCP tool<br/>executed by a remote server, projected under /.vfs/mcp/server (spec 170)"]
  table --> k6["Skill<br/>a directory holding SKILL.md; read, never executed (spec 169a)"]
```

## The picture: the pipe and the terminal

```mermaid
flowchart LR
  p1["stage"] -->|"Rows: a frozen Result slice, op-tagged<br/>or Bytes: a buffer with a mime<br/>one shape per chunk, bounded queues (ADR 083)"| p2["stage"]
  p2 -->|"same shape passes untouched;<br/>rows render to plain text for a byte consumer;<br/>bytes become one row at /.vfs/run/call-id/stdout for a row consumer"| p3["stage"]
  p3 --> term["terminal boundary<br/>display rendering, 32,768-character cap, the binary placeholder<br/>[binary path mime sizeB vN] (ADR 085)"]
  term --> wire["MCP wire: five content blocks, verbatim<br/>one TextContent first, then typed blocks in row order<br/>structuredContent = Result.to_payload() without bytes<br/>images inline within budget, else a ResourceLink vfs:///path"]
```

## The picture: the views and the index

```mermaid
flowchart LR
  vfs["/.vfs"] --> trash["trash<br/>per mount, each backend (built)"]
  vfs --> bin["bin<br/>the union of everything callable, in index order (169a)"]
  vfs --> skills["skills<br/>the union of every skill directory on the skill index (169a)"]
  vfs --> run["run/call-id<br/>stdout rows and a status record per program run (169c)"]
  vfs --> tools["tools<br/>host-registered functions: manifest and schema as content (170)"]
  vfs --> mcp["mcp/server/{tools, resources, prompts}<br/>each connected server projected by declared shape (170)"]
  vfs --> reserved["sessions, jobs<br/>reserved, unserved"]
  bin -.->|"the index: directories the host registers, in order<br/>default /opt/bin, created at posture read; install needs add"| opt["/opt/bin/*.wasm"]
```

## The picture: the Python guest over vfs

```mermaid
flowchart LR
  guest["wasi-python guest<br/>CPython 3.14 or 3.15 (ADR 086 pin 2, a lean) on wasm32-wasip1, numpy, pandas, scipy, matplotlib compiled in<br/>no threads, no network, no dlopen"] -->|"file calls: open, read, write, readdir ...<br/>staged whole at open, handed back whole at close"| mount["Mount(VfsProvider(session), '/')<br/>wasi-python's mount protocol over one vfs Session<br/>every call carries the caller's Authority; /.vfs hidden"]
  guest -->|"host::call with opaque JSON frames<br/>the tool protocol: list and call"| door["the verb door<br/>vfs verbs bound to the caller's authority, Result wire frames"]
  mount --> session["vfs Session(authority)"]
  door --> session
  session --> gate["THE GATE"]
  runner["wasi-python's runner: run, run_async, Session<br/>wasmtime, fuel, deadline, memory, output and call budgets"] --> guest
```

## Reading the picture

The shell is a front. It owns a parser, a program table, a pipeline
runner and a terminal rendering. It owns no stored fact and no
permission check. Every verb a command resolves to re-enters the
public router method, so the gate fires exactly as it would for a
Python caller. That is the execution policy: the gate order is the
policy, and executing a stored program is `read` on its entry
(ADR 084).

One name can be served by several kinds over time. `grep` is a verb
builtin today; `sed` is a Rust text kernel; a wasm program is bytes
installed under `/opt/bin`; `python3` is the wasi-python wheel's own
runner behind a thin `python` kind; a host's function is a tool; a
remote server's tool is an MCP tool. The kind is invisible on the pipe. A
program cannot hold more than its caller: its filesystem capability is
the verb set closed over the caller's `Authority`, and there is no
parameter through which to widen it.

The pipe carries rows or bytes, one shape per chunk, and converts only
at a seam. `ls | grep auth` filters rendered lines exactly as bash
does. A single binary read crosses a pipe raw, like Unix, and prints a
placeholder at the terminal, never base64. On the MCP wire the result
is MCP's five content blocks and nothing else.

`/.vfs` grows from one view (the trash) to a catalogue: everything
callable under `bin`, the host's tools, connected MCP servers, skills,
and the records of program runs. The catalogue views are router-owned
and read-only. Installing a program is a `write` into an indexed
directory under the ladder.

The Python runtime is a separate project, `wasi_python`, consumed as a
wheel. Its 0.1.0 release already ships the two seams vfs needs: a
mount protocol that makes a `Session` the guest's whole filesystem, and
a tool protocol through which guest code calls vfs verbs. Both carry
the caller's `Authority`. vfs's remaining work is bookkeeping: an errno
table, `move`'s replace rule, and the `python` program kind.

## Terms this diagram introduces

| Term | Meaning |
|---|---|
| **cli** | The meta-verb that takes a command string or argv and runs it through the shell. The one programmatic execution door. Refuses the system actor. |
| **Program** | Anything callable by name from the shell: one ABI, six kinds. |
| **ABI** | The one shape every program implements: `args`, `env`, `cwd`, `stdin`, `stdout`, `stderr`, `fs`, `budget` in; `stdout`, `stderr`, an exit code out. |
| **Filesystem capability (`fs`)** | The vfs verb set curried with the caller's `Authority`. No authority parameter, no grant verbs, absolute paths only. |
| **Verb builtin** | A program written as shell code over vfs verbs. |
| **Text kernel** | A program whose core is bytes-to-bytes Rust in `vfs-core`, with a thin Python layer for operands. |
| **Forms** | A program's declared option grammar and the subset this kind implements; an unimplemented form refuses `unsupported.form`. |
| **Pipe, chunk** | One ordered stream per seam; each chunk is `Rows` or `Bytes`, never both. |
| **Placeholder** | The one-line stand-in a binary row prints at a text boundary: `[binary <path> <mime> <size>B v<version>]`. |
| **Render cap** | 32,768 characters at the `cli` display and the MCP adapter; a pipe is never capped. |
| **View** | A `/.vfs` head the router serves from its own table: `bin`, `skills`, `run`, `tools`, `mcp`. |
| **Index** | The ordered list of directories whose entries feed `/.vfs/bin`. Default `/opt/bin`. |
| **Execution policy** | The gate order, fired on every verb a command resolves to. Executing a program is `read` on its entry. No `ask` inside vfs. |
| **Budget** | A declared constant with a classified outcome: stages, argv bytes, fan-out, stdout bytes, wall time, fuel, verb calls, memory, staging bytes. |
| **Five blocks** | MCP's content block types, the only wire: text, image, audio, resource link, embedded resource. |
| **Mount protocol, tool protocol** | wasi-python's two embedder seams: serve the guest's filesystem; let guest code call host functions. |
| **Verb door** | The host function behind `host::call` that carries vfs verb calls as `Result` wire frames. |

## Landing order (as the specs stand on 2026-10-24)

1. Spec 167 slices A to E: the renderer gaps, the parser, the pipe and
   `cli`, the program forms, the harness. `run` and `SupportsRun`
   retire in slice A.
2. Spec 168: the text kernels in Rust.
3. Spec 169a: the views and the index; 169b: generic wasm programs
   (narrowed by the 2026-10-23 memo); 169c: `/.vfs/run`.
4. Spec 171: the MCP adapter and `serve()`.
5. Spec 170: tools and MCP servers as views (one small study still
   owed).
6. Spec 172: the `python` kind over wasi-python; QuickJS for
   JavaScript.

## Open

- Spec 170 needs one small study before it is shaped.
- ADR 086 pins 2, 5 and 8 are leans pending Clay.
- `serve()`'s refusal to start on an open mount is not yet built
  (`docs/explanation/open-in-process-loud-at-the-edge.md`).
