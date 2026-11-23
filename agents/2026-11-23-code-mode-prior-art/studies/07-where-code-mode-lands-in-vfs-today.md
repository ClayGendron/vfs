# 07 — Where a code mode lands in vfs today: what is built, what is drafted, what is absent

## The question, as this study received it

The other studies survey Cloudflare Code Mode, Anthropic's code execution with MCP and tool search, open-source code-mode projects, tools-as-files designs and tool-retrieval research. This study is the map they are laid onto: exactly what vfs has built, what it has drafted and what it lacks, for a vfs code mode in which an agent calls tools and MCP servers through the vfs bash CLI, and tools, MCP servers and their results are stored as files searchable with `glob`, `grep` and `search` like anything else. It produces four things: (1) the brief's seven points against vfs, each element built, drafted or absent; (2) the path layout vfs has decided for tools, MCP servers, programs, skills and the bin union, with every place the records disagree; (3) what the drafted `cli` tool and shell would let an agent write, with one worked multi-step example; (4) the gaps a code mode would expose. It clones nothing and reads only the vfs tree.

## Sources

- **The vfs tree** at `f0849c5` (2026-11-23, branch `research/code-mode-prior-art`). `git rev-parse HEAD` read `0ed462f` when the study began; the one commit between, `f0849c5`, adds only `agents/2026-11-23-code-mode-prior-art/studies/00-brief.md` (EXECUTED: `git diff --stat 0ed462f f0849c5`), so every `src/` and `context/` citation below holds at both. Every `path:line` is at `f0849c5`.
- **Project rules:** `AGENTS.md` ("Production posture", "The reference deployment"), `README.md`.
- **Drafted specs** under `context/specifications/active/`: `167-the-shell-pipeline-core/spec.md`, `170-tools-and-mcp-servers-as-views/spec.md` and `171-the-mcp-adapter-and-the-cli-tool/spec.md` read in full; `169-programs-the-index-and-the-vfs-views/spec.md` read in full; `172-the-wasi-python-runtime/spec.md` and `168-text-program-kernels/spec.md` read for their decisions. Also `148-sessions-narrowing-and-pending/spec.md` (head) and the archived `2026-11-09-the-verbs-take-the-names-agents-know.md` (the verb rename).
- **The roadmap**, `context/standards/roadmap.md` (fourth revision, 2026-10-28, with state rows dated 2026-11-15): domains B (human in the loop), C (identity), F (shell), G (tools), H (serving MCP). It states of itself that "nothing on this page is a decision" (`roadmap.md:6`); it is cited as the latest drafted direction, not as a ruling.
- **Research memos** under `context/research/`: `2026-10-15-the-agent-shell-prior-art-and-experiments.md` (whole), `2026-09-04-mcpfs-projecting-mcp-servers-into-a-namespace.md` (§1, §4, §5, §6), `2026-10-23-wasi-python-0-1-0-over-vfs-the-mount-and-the-tool-door.md` (§0 to §8), `2026-09-15-eve-vercel-agent-framework.md` (the code-mode rows, lines 119, 225, 227). The pre-build review of spec 170, `context/research/studies/2026-10-15-agent-shell/15-spec-170-review-before-build.md` (findings 1, 2, 14 and its questions).
- **ADRs.** Every spec above cites ADRs 081 to 086 by pin. No decision-record file exists in the tree at `f0849c5`: `context/README.md:66` says "There are no separate decision records: a decision lives in the spec that carries it", and `roadmap.md:95` says the decision records were retired on 2026-10-30 (commit `3667fec2`). The frozen ranking corpus under `tests/fixtures/ranking/vfs_native/corpus/context/decisions/` stops at ADR 057. ADR pins are therefore cited here only as the specs restate them.
- **Built code:** `src/vfs/paths.py`, `src/vfs/skills.py`, `src/vfs/ops.py`, `src/vfs/params.py`, `src/vfs/base.py`, `src/vfs/session.py`, `src/vfs/sync.py`, `src/vfs/storage/protocol.py`, `src/vfs/authority.py`, `src/vfs/permissions.py`, `src/vfs/storage/backends/database/{rights,reads,search,grep}.py`, `src/vfs/results/{envelope,render,kinds,projection}.py`, `src/vfs/deadline.py`, `pyproject.toml`.
- **Experiment** (EXECUTED here, 2026-11-23): `studies/experiments/07-vfs-today/probe.py`, output `probe.out`, run with `uv run --offline python -I` over `InMemoryStorage` through the public async API only. It probes `run`, writes under `/.agents` and `/.vfs`, `search`/`grep`/`glob` visibility, and the ladder on a stored tool manifest.

## Findings

### F1. The verbs, the `Result` and the `Authority` are built; nothing of the shell, the views or the MCP side is (READ, EXECUTED)

READ. The kernel is 25 ops (`src/vfs/ops.py:39-65`), among them `search` and `traverse` and the dead `run`; every public method is a router that runs params gate, capability, grammar and permission before dispatch (`src/vfs/base.py:2734-2800`, `_gate_params` and `_gate_entry`). An `Authority` (subjects, actor, provenance, narrowing) is a frozen value with four construction doors (`src/vfs/authority.py:116-213`); a call that names none runs as the router's `default_authority`, else as anonymous (`base.py:2991-3004`, `_admitted`). Row-level grants are compiled per call inside the verb's own transaction (`src/vfs/storage/backends/database/rights.py:1-30`). Every verb returns one `Result` with `to_payload`/`from_payload` (`src/vfs/results/envelope.py:723-790`).

READ, confirmed by search. Absent from `src/`: any `cli` method, any `vfs.shell` package, `serve`, `register_tool`, `add_mcp`, any `/.vfs/run`, `/.vfs/bin`, `/.vfs/tools` or `/.vfs/mcp` handling, `authority_from_token` (grep over `src/vfs` returns no definition of any of them). `pyproject.toml:49-68` declares no `mcp`, `wasm` or `python` extra and no `[project.scripts]`. The roadmap's state rows agree: "Nothing is built (EXECUTED 2026-11-15)" for the shell, the tools domain and the MCP front (`roadmap.md:596`, `:686`, `:761`).

### F2. `run` is the only execution verb, and no storage serves it (READ, EXECUTED)

READ. `run(path, *, arguments, authority)` is a public router method (`base.py:1605-1621`) whose docstring says "`read`/`stat`/`ls` discover a tool's definition; `run` is the only verb that executes it". It dispatches to `SupportsRun` (`base.py:2958-2961`; protocol at `src/vfs/storage/protocol.py:365-374`; family table `protocol.py:557`). Its params row takes a path and a `dict` of arguments (`src/vfs/params.py:357-361`). Its rung is `read` (`ops.py:164`), and the needs table's docstring still says "`run` waits for its own axis" (`ops.py:177-178`). The sessions and sync faces mirror it (`session.py:395-398`, `sync.py:588-595`, `sync.py:1045-1046`). The README lists it as the "Execute" verb (`README.md:73`).

EXECUTED (`probe.out`). `"run" in fs.capabilities()` is `False` on the default router. `run("/.agents/tools/deploy", arguments={...})` as the system actor returns `vfs.unsupported` at `/` ("operation 'run' is not declared by the storage mounted here"); bad arguments (`arguments="x"`) return `vfs.invalid` from the params gate first. As a caller who cannot even list the path (`bob`, below), `run` returns the same `unsupported`, because the capability gate precedes the permission gate (`base.py:2751-2790`).

READ. Spec 167 §1 item 1 deletes `run` and `SupportsRun`; spec 170 §5 says "nothing in storage executes" and replaces it with a router-internal door `_invoke` that is not an `Op`. The roadmap files this as K9 (`roadmap.md:204-207`) and lists `run`, `SupportsRun` as "live but dead" (`roadmap.md:129`).

### F3. Tools as searchable files exist today by accident of path, under `/.agents`, and the drafts retire that layout (READ, EXECUTED)

READ. `paths.py:49-54` declares `AGENTS_ROOT = "/.agents"`, `AGENT_FAMILIES = {"tools", "skills"}`, `TOOL_MANIFEST = "TOOL.md"`, with the comment "Unlike METADATA_ROOT (derived, no indexable content), /.agents holds real files, so a tool's/skill's manifest indexes normally". Path builders `tool_path`, `skill_path`, `tool_manifest_path`, `skill_manifest_path` sit at `paths.py:620-642`; `is_reserved_directory` makes the family roots and unit directories structural directories (`paths.py:686-699`). No `Tool` value object exists: `skills.py` builds `Skill` values that render `SKILL.md` and project to entries under `/.agents/skills/<name>` (`skills.py:157-212`), and nothing in `src/` calls `tool_path` or `tool_manifest_path` (grep: the only users of the agent helpers are `skills.py:31` and `skills.py:200`).

EXECUTED (`probe.out`). A `TOOL.md` written as an ordinary file at `/.agents/tools/deploy/TOOL.md` is a stored row like any other. After `storage.rebuild()`, an unscoped `search("deploy production release")` ranks it first, above `/docs/release.md`; an unscoped `grep("destructiveHint")` and `glob("**/TOOL.md")` find it. After `posture("/.agents/tools", "none")` and `grant("/.agents/tools/deploy", "alice", "read")`, Alice's search returns the manifest and Bob's does not; Bob's `read` of the manifest is `not_found` at `/.agents/tools` (existence hidden). So the live tree already gives a stored tool manifest ranked search, pattern search and per-principal visibility, with no tool-specific code.

READ. Spec 169 §a7 retires the whole family: "`AGENTS_ROOT`, `AGENT_FAMILIES`, `tool_path`, `skill_path`, `tool_manifest_path`, `skill_manifest_path` and the `/.agents` rule in `is_reserved_directory` go". The roadmap repeats it: "`/.agents` and `skills.py` exist and are retired by ADR 082 pin 6" (`roadmap.md:686`).

### F4. `/.vfs` is writable today beneath its root, hidden from unscoped search, and the drafts make it a read-only set of synthesized views (READ, EXECUTED)

READ. The reserved-space grammar refuses only the `/.vfs` root itself and paths beneath the trash head (`paths.py:840-856`). Search and grep hide the meta subtree unless the pattern or scope names it literally (`reads.py:780-789` `meta_scoped`; `search.py:302` and `grep.py:275` `hide_meta=not (gates.admissions or gates.scoped)`).

EXECUTED (`probe.out`). Writes to `/.vfs/tools/deploy/TOOL.md`, `/.vfs/bin/jq.wasm` and `/.vfs/run/1/stdout` all succeed as stored rows. An unscoped search, grep or glob does not return them; `search(..., paths=("/.vfs/tools",))` and `grep(..., paths=("/.vfs/tools",))` do. `ls /.vfs` lists `bin`, `run`, `tools` and `trash`.

READ. Spec 169 §a1 refuses every write strictly beneath `/.vfs/` except the trash head for `sweep`, makes "no stored row lives beneath `/.vfs`" an invariant, and serves `bin`, `skills`, `run` (and, from spec 170, `tools`, `mcp`) from a router-owned view table that `mounts()`, unscoped `glob **` and `grep -r /` never reach (§a2). Spec 170 §5: "tool entries are facts about one process and are synthesized; only their policy is stored". So the drafted tool catalogue is not stored, not indexed and invisible to unscoped search by construction, which is the opposite of the behaviour F3 measured for `/.agents`.

### F5. The drafted call surface: a bash-shaped line, one `cli` tool, flags derived from JSON Schema (READ)

- **The language.** Spec 167 §2 admits pipelines, `;` `&&` `||`, `( )` and `{ }`, redirections, here-documents, `$( )` and backticks, the POSIX `${…}` forms, quoting, globs and braces, `time`, `set -e`, and refuses `if`/`for`/`while`/`case`, functions, `[[ ]]`, `$(( ))`, `<( )`, `<<<`, arrays and `&` at parse time as `vfs.unsupported.construct`, "before anything runs". The roadmap reverses the refusals: "the shell speaks bash — the whole language" (`roadmap.md:51`, F7 at `roadmap.md:642`), as a sixth slice no spec yet carries (`roadmap.md:102`).
- **Entry points.** `VirtualFileSystem.cli(command | argv, *, authority, workdir="/")` with `authority` required and a fresh state every call; `Session.cli` keeps `cwd`, `env`, `last_status`, `history` in memory (167 §7). The system actor is refused (167 §7; 171 §0).
- **What a program sees.** `Call{args, env, cwd, stdin, stdout, stderr, fs, budget}`, where `fs` is "the router's public verbs, curried with the call's admitted authority" and accepts absolute paths only (167 §3). The pipe carries rows or bytes; `grep` on a pipe filters rendered lines "exactly as bash does", and rows pass between programs only through an explicit form (`xargs`, spec 168) (167 decision 1).
- **Tools as commands.** A host function registered once is `/.vfs/tools/<name>` and runs as `<name> --arg value`; an MCP tool is `/.vfs/mcp/<server>/tools/<tool>` and runs by name or path (170 Intent, §1, §3). One flag per top-level schema property, kebab aliases, `$ref` resolved one level, nullable unions collapsed, arrays by repeated flags, objects as JSON, positionals bound to required scalars, stdin bound to the one unset required string/base64/object property, `--json '<object>'` and `--json -` as the whole-arguments escape, `--help` rendering one line per property; every client-side failure is `vfs.invalid`, exit 2, with zero wire calls (170 §2).
- **Over MCP.** `serve()` exposes the agent-facing verbs as tools plus one `cli` tool, or only `cli` with `tools={"cli"}` (171 §0). The `cli` input is `{command}` or `{argv}`, optional `workdir` and `timeout_ms` that can only shorten the 10 s deadline (171 §1.4). Its description is about 2,300 characters, verbatim in the appendix (171:213-263). The verdict is `isError = not result.success`; a program's own non-zero exit is not an error (171 decision 1, §3).
- **How many tools up front.** 21 tools on the default router per the roadmap (`roadmap.md:768`, which calls spec 171's own count of 19 on an unknown dialect stale), or 1 with `tools={"cli"}`. Tool and MCP-tool names reach the model only through the shell (`ls /.vfs/bin`, `type`, `help`, `--help`), never as MCP tools of the vfs server.

### F6. The drafted discovery surface: `ls`, `type`, `grep` over manifests; ranked search over tools is out of scope (READ)

- `/.vfs/bin` lists every callable with `callable_kind` (`program`, `tool`, `mcp`, `skill`) and `resolved` (169 §a3; 170 §6). Resolution is one batched `stat` over directories × suffixes, never an `ls` (169 §a5). `type`, `which -a`, `help` and `--help` render the manifest or schema (170 §6).
- A tool entry's content is its manifest: name, description, input schema, trust line, declared capabilities (host tools, 170 §1); `title`, `description`, `inputSchema`, `outputSchema`, icons, annotations, rendered as untrusted text (MCP tools, 170 §3.2). `cat`, `stat`, `ls`, `glob` and `grep` never execute (170 §1; review 15 finding 1, which made this blocking after the mcpfs memo §5 called call-on-stat "the single most consequential design error").
- "The catalogue views serve `read`, `stat`, `ls`, `tree`, `glob` and `grep` over their manifests; `grep` scans the rendered manifests in memory. `glean` over the catalogues is a later item" (170 §6; `glean` is today's `search`). The review that added the line asked the open question in the code-mode case's own words: should ranked search "rank tool descriptions (the 'find the right tool among 500' case)? Proposed: `grep` now, `glean` later" (review 15, question 4).
- Listing freshness: `tools/list` is fetched at connect and refreshed when stale, never more than once per `cli` call and never more often than `MCP_LIST_FLOOR_MS`, 30 s by default (170 §3.3 rule 3).

### F7. The drafted execution surface: no operating system, in-process verbs, host tools in the host, guests in wasm (READ)

- The shell is not a computer: "no host operating system, no network, no package manager, no processes that outlive the call" (171 appendix). `curl`/`wget` are `unsupported` 126 with the network hint; `git`, `uv`, `docker`, `sudo`, `python3` (until 172) are `unrecognized` 127 with hints (167 §4).
- Budgets per line: `STAGE_BUDGET` 64, `FANOUT_BUDGET` 10,000 paths per stage, `STDOUT_BYTE_BUDGET` and `STDERR_BYTE_BUDGET` 4 MiB per stage, `WALL_TIME_BUDGET` one deadline across the line, parser budgets 1 MiB input, 100,000 tokens, depth 200 (167 §2, §5). The wall budget exists today as a constant, `WALL_TIME_BUDGET: Final = 10.0` (`src/vfs/deadline.py:36`).
- A host tool runs in the host process with the host's authority; a sync tool runs in a worker thread and is abandoned, not killed, at its deadline (170 §1). It "is the one callable kind that may hold more than its caller".
- An MCP tool runs on its server; vfs is the client through the official SDK, one supervisor task per connection, never auto-retrying a `tools/call` because "a cancelled `tools/call` may have run" (170 §3.3).
- Guests: a WASI preview1 host with fuel 2 × 10⁹, memory 256 MiB, 10,000 verb calls per run (169b §b8), moved to 0.2 by the roadmap (T6, `roadmap.md:745`); a Python guest over the wasi-python runner, whose two doors are a mount (every file call becomes a verb under one `Session`) and a tool protocol (`from host import tools`), executed over public APIs with Alice refused and Bob granted (wasi-python memo §2 to §4); in 0.1.0 per `roadmap.md:725`.

### F8. The drafted authority story: the caller's rights at the entry, the host's or the server's rights beyond it (READ)

- **The gate on a call.** `_invoke(path, arguments, *, authority)`: resolve (127 if the caller cannot `list` the entry), then `read` on the entry (126), then the call (170 §5). Since a catalogue entry has no row, a new seam `SupportsGrants.rungs_at(paths, *, authority)` answers the caller's rung at synthesized paths, one chunked statement per `membership_budget` slice (170 §5.1; roadmap I3a).
- **The default is open.** "On a fresh node everyone holds `read_write` at `/`, so every caller, anonymous included, can call every registered tool and every MCP tool, and a host tool runs with the host's authority. This is accepted." Two `posture` lines lock it (170 §5.1). The router's built default is `permissions="read_write"` (`base.py:369`).
- **Remote identity.** "A server's identity is the connection's: every vfs caller who may call its tools acts through the one credential the host configured" (170 §3.1). Credentials are per-server configuration and never touch `os.environ` (170 §3.1, from the mcpfs memo §5). The roadmap's I4 replaces this with a `CredentialResolver.resolve(server, authority)` and one connection per `(server, principal)`, refuses a subject set over a per-user server, and moves OAuth to 0.2 as T7 (`roadmap.md:408-416`, `:749`).
- **Inbound identity over MCP.** Per request: a verified token becomes `authority_from_token(claims)` (spec 149, unbuilt), no token is anonymous, the system actor is refused, and a handler never passes `authority=None` (171 §0, decision 8).

### F9. The drafted result story: rows, a per-call record in memory, no state across wire calls (READ)

- A host tool's return becomes rows: a `Result` passes through, `str` is one text row, `bytes` one bytes row, `None` no row, anything else one JSON row (170 §1). MCP blocks become rows at `/.vfs/run/<call-id>/<i>`; `structuredContent` "rides as the `Result` extra `structured` … never as a row", except when `content` is empty (170 §4).
- A `cli` call's `observations` are the last stage's rows when one statement wrote stdout and produced rows, else one row at `/.vfs/run/<call-id>/stdout`, which "cannot be read back in this spec" (167 §6). Spec 169c then serves `/.vfs/run/<call-id>/{stdout,status}` from a router-memory ring: 64 calls per exact `Authority` value, 64 MiB across authorities, least-recently-used eviction, lost on restart, not shared across processes, readable only by an equal `Authority` (169 §c1). The roadmap's T2 rewrites the record as rows in the root binding's storage (`roadmap.md:700-702`).
- No shell state persists between `cli` calls over the wire; "use absolute paths across calls" (167 decision 4; 171 §1.4 and appendix).
- The display is stdout then stderr, capped at 32,768 characters; "the pipe is never capped" (167 §6). On the verb tools, `structuredContent` carries exactly the rows the capped text showed (171 §2.2), because a 10,000-row `ls` is 1,790,064 characters of payload against 32,768 of text (171 §2.2, citing its probe `r171/p1`).
- Live-tree gaps the drafts depend on: `to_payload` has no `include_bytes` flag and dumps every populated field (`envelope.py:723-751`), and no binary placeholder exists in `render.py` (grep finds none; 167 §1 items 3 and 6 draft both).

### F10. Evidence and the action log: a measured command corpus, no call log (READ)

- The shell's whole shape rests on one measured corpus: 12,627 Bash calls from 418 transcripts; nine commands make 86% of segments; pipes in 74% of calls, `&&` in 44%; control flow, functions, arithmetic, arrays and `&` under 10% (agent-shell memo §1, §2). Spec 167's harness reports parse, resolve, flag and run rates "counts only" against bash 5.2 fixtures (167 §8).
- No measurement in the tree compares tokens, latency or accuracy of `cli` against per-verb tools or against direct MCP tool calls. The mcpfs memo explicitly declines mcpfs's "`ls` costs 0 tokens" as "a claim about rendered size, not a measurement of agent behavior" (mcpfs memo §5).
- There is no call log: "No `import logging` in `src/vfs` (EXECUTED 2026-11-15); no table records a call" (`roadmap.md:103`). H0 drafts an action log; L0 commissions the spike that prices it (`roadmap.md:269-287`).

### F11. Failure handling and human approval: classified refusals are drafted, approvals are not (READ)

- Refusals are classified before anything runs (`unsupported.construct`, `invalid.syntax`, budgets), the exit-code table is fixed (0, 1, 2, 124, 126, 127, 130), and a refused line after a mutation runs nothing (167 §2, §3, criterion 9).
- A tool's own failure: `ToolError` exits 1 with the message; any other exception exits 1 with a generic line and the detail stays on the host (170 §1). MCP `isError` is exit 1 with text on stderr and no kind minted (170 §4).
- Approval: spec 170 maps elicitation and `input_required` to `vfs.unsupported` 126, "no ask inside vfs" (170 §4). MCP tool annotations are rendered into the manifest and drive nothing. On the served side, `readOnlyHint` and `destructiveHint` are derived from `ops.py` for vfs's own verb tools, and "`cli` is neither read-only nor marked destructive" (171 §1.3). The roadmap's domain B drafts `pending`, a preview (`plan=`), a policy hook before dispatch and a durable run ledger, and H5 flips the elicitation row to `vfs.pending` 75 (`roadmap.md:227-346`); its state table marks every piece missing (`roadmap.md:257-265`).
- Prompt injection: every server manifest line is rendered as data, control characters removed, each description capped at `MANIFEST_DESCRIPTION_BUDGET`, prefixed by its provenance line; "vfs never places manifest text in a system prompt" (170 §6). Built today: `Skill` rejects angle brackets in every frontmatter string as "a prompt-injection vector" (`skills.py:40-42`, `:219-223`).
- Name capture: catalogue views sit after every stored program directory in the union, so "a remote server cannot take over a bare command name that a kernel program or a stored program already answers"; an MCP tool is always reachable by its full path (170 §6).

### Table 1. The seven points against vfs

Status: **Built** (cite code), **Drafted** (cite spec or roadmap story), **Absent** (in neither).

| Point | Element | Status | Where |
|---|---|---|---|
| 1 Call surface | Python verbs, one gate, one `Result` | Built | `base.py:904-1620`, `ops.py:39-65` |
| 1 | `run(path, arguments)` execution verb | Built, dead: no storage declares it; to be deleted | `base.py:1605-1621`, `protocol.py:365-374`; probe P1; 167 §1.1 |
| 1 | Bash-shaped language, static parse, refusals before run | Drafted (subset); full bash drafted only on the roadmap | 167 §2; `roadmap.md:51`, F7 |
| 1 | `VirtualFileSystem.cli` / `Session.cli` | Drafted | 167 §7 |
| 1 | JSON Schema → flags, `--json`, stdin binding, `--help` | Drafted | 170 §2 |
| 1 | One `cli` MCP tool beside the verb tools; `tools={"cli"}` | Drafted | 171 §0, §1.4, appendix |
| 1 | Code in Python calling verbs and tools (`from host import tools`) | Drafted (executed over public APIs, not built) | wasi-python memo §2–§4; `roadmap.md:725` T5a |
| 1 | TypeScript/JavaScript code calling typed tool functions | Drafted only as a QuickJS guest over the same door; no typed API generation | 172 §6; `roadmap.md:735` T5b |
| 1 | Typed function stubs generated from schemas (Code Mode's shape) | Absent | — |
| 2 Discovery | Tool manifest as a stored, indexed file (`/.agents/tools/<n>/TOOL.md`) | Built as path helpers only; works as ordinary rows; retired on paper | `paths.py:49-54`, `:620-642`; probe P2, P4; 169 §a7 |
| 2 | Skills as stored `SKILL.md` units | Built | `skills.py:157-212` |
| 2 | `/.vfs/tools`, `/.vfs/mcp/<s>/{tools,resources,prompts}` views | Drafted | 170 §1, §3.2 |
| 2 | `/.vfs/bin` union with `callable_kind`, `type`, `which`, `help` | Drafted | 169 §a2–§a5; 170 §6 |
| 2 | `grep` over manifests (in memory) | Drafted | 170 §6 |
| 2 | Ranked `search` over tool and MCP manifests | Absent from the drafts ("a later item"); works today only for stored `/.agents` rows | 170 §6; review 15 Q4; probe P4 |
| 2 | Tool-listing freshness (`ttlMs`, 30 s floor) | Drafted | 170 §3.3 |
| 3 Execution | In-process shell, no OS, no network, line budgets | Drafted (only `WALL_TIME_BUDGET` 10 s is a built constant) | 167 §5; `deadline.py:36` |
| 3 | Host tools in the host process, worker thread, deadline | Drafted | 170 §1 |
| 3 | MCP client: supervisor, reconnect, no auto-retry | Drafted (needs a spike first) | 170 status line, §3.3 |
| 3 | Wasm programs under fuel, memory, verb budgets | Drafted; 0.2 on the roadmap | 169b; `roadmap.md:745` |
| 3 | Python guest with numpy/pandas, no network | Drafted (executed in a memo) | 172; wasi-python memo |
| 4 Authority | `Authority` value, row-level grants per call | Built | `authority.py:116-213`; `rights.py` |
| 4 | Program `Fs` = verbs curried with the caller's authority | Drafted | 167 §3 |
| 4 | Gate on a tool call: `list` to resolve, `read` to call; `rungs_at` | Drafted | 170 §5, §5.1 |
| 4 | Host tool holds the host's authority; caller's `Fs` only if declared | Drafted | 170 §1 |
| 4 | One host credential per MCP server, never in `os.environ` | Drafted | 170 §3.1 |
| 4 | Per-principal credential resolver; OAuth on demand | Drafted on the roadmap only (I4 in 0.1.0, T7 in 0.2) | `roadmap.md:408`, `:749` |
| 4 | Token → `Authority` per MCP request, system actor refused | Drafted | 171 §0; spec 149 |
| 5 Results | `Result`, `to_payload`, `from_payload` | Built (bytes unbounded in payload) | `envelope.py:723-790` |
| 5 | Placeholder for bytes, 32,768-character display cap | Drafted | 167 §1.3–§1.4, §6 |
| 5 | Tool and MCP results as rows at `/.vfs/run/<call-id>/<i>` | Drafted | 170 §1, §4 |
| 5 | Run record readable later (`/.vfs/run`) | Drafted as an in-memory ring; as rows on the roadmap | 169c; `roadmap.md:700` T2 |
| 5 | `structuredContent` as the `structured` extra, not in the pipe | Drafted | 170 §4 |
| 5 | Result redirected into a namespace file (`> /work/x.json`) | Drafted (a `write` of the plain bytes) | 167 §5 Redirections |
| 5 | Shell state across calls | Drafted in-process only; none over the wire | 167 decision 4, §7 |
| 5 | Agent-written code saved as a reusable command or skill | Absent (no shell-script kind; `source` and `.` are `unrecognized`; skills are read-only) | 167 §4 never class; `roadmap.md:680` |
| 6 Evidence | Command corpus (12,627 calls) and coverage rates | Built as research; harness drafted | memo §2; 167 §8 |
| 6 | Token, latency or accuracy measurement of `cli` vs tools | Absent | — |
| 6 | Action log of every call | Absent; drafted on the roadmap (H0, L0) | `roadmap.md:103`, `:269-287` |
| 7 Failure | Classified refusals before run; exit-code table | Drafted | 167 §2–§3 |
| 7 | Manifest text as untrusted data; provenance line | Drafted | 170 §6 |
| 7 | No auto-retry of `tools/call` | Drafted | 170 §3.3 rule 4 |
| 7 | Human approval of a side effect | Absent from 167/170/171 (elicitation is 126); drafted on the roadmap (H2–H5) | 170 §4; `roadmap.md:227-346` |
| 7 | A static effect summary of a parsed line for a harness prompt | Absent (named as an idea to copy, never drafted) | memo §11 "Copy as ideas" |

### Table 2. The path layout, and where the records disagree

| What | Today in `src/` (built) | Drafted | Disagreement |
|---|---|---|---|
| Host tools | `/.agents/tools/<name>/` unit, `TOOL.md` manifest (`paths.py:16`, `:620-637`); no producer | `/.vfs/tools/<name>`, a synthesized file whose content is the manifest (170 §1) | 169 §a7 retires `/.agents`; the README still shows `/.agents/tools/<name>/` as "a tool an agent can discover and run" (`README.md:108`); the eve memo's code-mode row rests on "`/.agents/tools/<name>/TOOL.md` already is" that pattern (eve memo line 225) |
| MCP servers | nothing | `/.vfs/mcp/<server>/tools/<tool>`, `resources/<n>`, `prompts/<p>`, a router-owned catalogue, not a mount (170 §3.1, §5) | The mcpfs memo §4.1 kept spec 034's materialization (every tool as a stored `/.agents/tools/<name>/TOOL.md`) and a scope table of view paths; spec 170 §5 rejects materialization. The README says MCP servers mount "as just another backend" (`README.md:131`); 170 §5 makes that only the vfs-protocol case (roadmap 020) |
| Skills | `/.agents/skills/<name>/SKILL.md` (`paths.py:17`, `:629-642`; `skills.py:200-212`) | `/.vfs/skills/<name>/`, a view over index containers whose children hold `SKILL.md`; `Skill.to_entries(at=container)` (169 §a7) | as for tools |
| Programs | nothing | `/opt/bin`, minted by the host as the system actor at posture `read`, plus the session's `$PATH`; `jq.wasm` serves `jq` (169 §a4–§a6) | The agent-shell memo proposed `/.agents/bin` as a third family (memo §5, §8); 169 chose `/opt/bin`. 169's Depends line names `Session.path`, while 167 §7 says "there is no separate `Session.path`" |
| The bin union | nothing | `/.vfs/bin`: builtins, then the kernel table, then session `$PATH`, then the index, then the catalogue views (169 §a5; 170 §6) | — |
| Python guest | nothing | 172 §2: `/opt/bin/python3.wasm` and `/opt/lib/python3XY.zip` as rows | The wasi-python memo §1 and §6: nothing needs to be a vfs row; the artifact set rides in the wheel; `import vfs` cannot ship in the zip, the door is `from host import tools` |
| Program and tool output | `/.vfs/run/...` is a lawful stored path today (probe P3c) | `/.vfs/run/<call-id>/stdout`, `/<i>`, `status`; writes refused (167 §6; 169 §a1, §c1; 170 §4) | `<call-id>` is "a per-session counter … a per-router counter" in 167 §6 and "a ULID" in 169 §c1; an in-memory ring in 169c and rows in roadmap T2 |
| Stopped runs | nothing | `/.vfs/jobs/<run_id>/asks/<ticket>` (roadmap H4) | 169 §a1 reserves `jobs` unserved; the agent-shell memo §9 put jobs out of scope at v1 |
| Trash | `/.vfs/trash` view (`paths.py:47`, `:766-823`) | unchanged | — |
| Writes under `/.vfs` | refused only at `/.vfs` and under the trash head (`paths.py:840-856`); probe P3 stores rows at `/.vfs/tools`, `/.vfs/bin`, `/.vfs/run` | every write beneath `/.vfs/` refused `invalid` (169 §a1) | the live tree and the draft differ; 169 notes "there is no production data to migrate" |
| Verb names | `search`, `traverse` (`ops.py:39-65`), renamed on 2026-11-12 | 167 §4.1, 170 §6, 171 §0 and the `cli` description say `glean` and `graph` | the three specs predate the rename (archived spec "the verbs take the names agents know") |
| `cli` keyword | — | 167 §7: `workdir=`; 171 §1.4: "calls `fs.cli(command \| argv, authority=…, cwd=workdir)`" | minor naming drift |
| `vfs serve` | — | 171 decision 7: `serve()` only | roadmap M2 reverses it (`roadmap.md:777`) |
| Elicitation / `input_required` | — | 170 §4: `vfs.unsupported` 126 | roadmap H5: `vfs.pending` 75 |
| MCP credentials | — | 170 §3.1: one per server | roadmap I4: one per `(server, principal)` |
| The grammar | — | 167: subset, `for`/`if` refused; 171's description says so | roadmap F7: the whole language |

### F12. What the drafted `cli` and shell would let an agent write (READ, with the example INFERRED from the drafts)

READ. Under specs 167 and 170 together, one `cli` call can: run any number of verb builtins (`cat`, `ls`, `grep`, `find`, `stat`, `search`, `traverse`, `mkdir`, `rm`, `cp`, `mv`, `touch`) and text programs (`head`, `tail`, `sed -n`, `sed -i`, `wc`, `cut`, `nl`); call a host tool or an MCP tool by name or by path with flags from its schema; feed a tool from a file with `<` or from an upstream stage by stdin binding; write any stage's output into a namespace file with `>` or `>>`; substitute output into arguments with `$( )`; chain with `&&`, `||` and `;`; and get back stdout then stderr capped at 32,768 characters, `exit_code`, `statuses`, and the classified errors. Under spec 167 it cannot loop or branch; under the roadmap's F7 it could. It cannot run `jq` or `awk` in 0.1.0 (168 decisions 2 and 3; `roadmap.md:745`), `sort`, `uniq` and `tr` arrive only with 168a, and `python3` only with 172/T5a.

The worked example. Task: "Find the open incidents in the GitHub server, save them, pull the three most relevant runbook passages from our own docs, write a summary note, and post it to the ops channel." Written for one `cli` call, in spec 167 grammar and spec 170 calling convention; the GitHub and Slack servers, their tool names and their property names are illustrative, not real schemas:

```sh
mkdir -p /work/incidents && cd /work/incidents && \
/.vfs/mcp/github/tools/search_issues --query 'label:incident is:open' --per-page 20 > open.json && \
grep -o '"title": *"[^"]*"' open.json | head -5 && \
search 'payments failover runbook' /runbooks --limit 3 > runbooks.txt && \
printf '# Open incidents, %s\n\n' "$(date +%F)" > summary.md && \
grep -o '"title": *"[^"]*"' open.json >> summary.md && \
cat runbooks.txt >> summary.md && \
/.vfs/mcp/slack/tools/post_message --channel ops-incidents < summary.md
```

What each step is, by the drafts (INFERRED from the cited sections):

| Step | What runs | Gate and effect |
|---|---|---|
| `mkdir -p`, `cd` | `mkdir(parents=True, exist_ok=True)`; `cd` is `stat` at `list` plus a kind check (167 §4.1, §4) | `add` on `/work` for a fresh directory |
| `search_issues … > open.json` | resolution by path (no shadowing), `_invoke`: `list` then `read` on `/.vfs/mcp/github/tools/search_issues`, then `tools/call` with `{"query": …, "per_page": 20}` via the kebab alias (170 §2, §5) | the remote sees the host's one credential for `github` (170 §3.1); the text blocks cross the pipe as bytes; `structuredContent` rides as an extra and does not reach `open.json` (170 §4); the redirect is a `write` of those bytes, `add` on the directory, a versioned row (167 §5) |
| `grep -o … \| head -5` | `grep` reading a file operand (`read` at `read`), `-o` re-matching in the shell (167 §4.1); `head` a bytes program | correct only if the server's text block puts each title on a line `grep -o` can reach; a single-line JSON blob still works for `-o`, but `head -n` counts lines, not records |
| `search … > runbooks.txt` | the ranked-search verb builtin, `--limit 3` (167 §4.1, `glean` row) | only rows the caller may `read` are ranked (`ops.py:149`); the rendered rows land in a file |
| `printf … "$(date +%F)"` | builtins, `$( )`, `>` (167 §4, §5) | a `write` |
| `>>` twice | read then write in 167 §5 ("concurrent appends can lose data"), `write(append=True)` after spec 174 (167 rebase note) | each append is a new version of `summary.md` |
| `post_message --channel … < summary.md` | `<` is a `read` fed as stdin; stdin binds to the one unset required string property, say `text` (170 §2) | a remote side effect with no approval step, no preview, no ask (170 §4); a re-sent line posts again (171 rebase note on 177) |

What comes back (167 §6): several statements wrote stdout, so the `Result` holds one row at `/.vfs/run/<call-id>/stdout` with the five titles; `exit_code` is the last stage's; `statuses` lists every pipeline. The durable artefacts are `open.json`, `runbooks.txt` and `summary.md`, ordinary versioned rows under the caller's grants and found by `grep` at once and by `search` after the next index pass. The tool results themselves at `/.vfs/run/<call-id>/<i>` are, under 169c, an in-memory record only the same `Authority` can read. The next `cli` call over the wire starts at `/` and must say `/work/incidents/summary.md` in full (171 appendix, "State").

### F13. The gaps a code mode would expose (INFERRED, each grounded in the READ findings above)

1. **Tool results as files.** The drafts give two homes. The ephemeral one, `/.vfs/run/<call-id>/<i>`, is an in-process ring of 64 calls per exact `Authority` value, lost on restart, unreadable by any other authority, never indexed and hidden from unscoped search (169 §c1, §a1–§a2); spec 167 alone cannot read it back at all (167 §6). The durable one is whatever the agent redirects into the namespace with `>`, which is governed, versioned and searchable like every file. So "results stored as files, searchable like anything else" holds only for results the agent chose to save, at a path it chose, and only after the next index pass for `search`. The roadmap's T2 (rows in the root binding) and H0 (an action log) would make the ephemeral record durable, which raises a retention question the reference deployment prices: about 150,000 agent verb calls a day (`AGENTS.md`, reference deployment), each `cli` line holding several, each record capped at `STDOUT_BYTE_BUDGET` 4 MiB. Who may read a run record when the authority is a subject set, or when an MCP client presents the same principal through a fresh token per request, is not stated: "only an equal `Authority`" depends on how the token edge builds the value (171 §0; `authority.py:116-150`).
2. **Searchability of MCP tool definitions.** The drafted views serve `ls`, `stat`, `read`, `glob` and in-memory `grep`, and are reached by no unscoped fan-out; ranked `search` over manifests is "a later item" (170 §6). The code-mode case that motivates tool search, picking the right tool among hundreds, therefore gets `grep -ri` over manifest text and `ls /.vfs/bin`. The live tree's `/.agents` rows already get ranked search, `grep`, `glob` and per-principal visibility (probe P4, P5), and the drafts retire them (169 §a7). The choice is between a synthesized catalogue with a ranked leg of its own (no rows, so no BM25 postings, no embeddings, and rights through `rungs_at`) and spec 034's materialization of manifests as stored rows, which spec 170 §5 rejected because "tool entries are facts about one process". A ranked leg over a synthesized view also has to keep a hidden tool out of other callers' search statistics, the property the roadmap pins for rows (`roadmap.md:774`, M1 criterion 7).
3. **Structured data between calls.** The pipe is bytes (167 decision 1). An MCP tool's `structuredContent` never enters the pipe while text blocks exist (170 §4), so a stage after a tool sees the server's prose rendering, not its JSON. No JSON program exists in 0.1.0: the `jq` kernel was dropped for a wasm `jaq` (168 decision 3), and the wasm host moved to 0.2 (`roadmap.md:745`). The agent-shell memo left "may a program declare `consumes: "json"`" unadopted at v1 (memo §13, ADR 3). JSON can flow into a tool (`--json -`, and stdin bound to an object property, 170 §2) but not out of one into a program except as text. The structured escape is the Python guest, whose tool protocol returns `to_payload()` dicts (wasi-python memo F4); that makes a vfs code mode's structured half Python, not shell.
4. **Credentials for remote MCP servers.** Spec 170 has one host credential per server, so every caller with `read` on a tool entry acts at the remote as the host (170 §3.1). The per-principal resolver (I4) and OAuth (T7, 0.2) are roadmap stories without a spec. No secret enters a sandbox because no sandbox stands between the shell and the MCP client: the client is host code, and the rule is only that credentials never reach `os.environ`, a row, a result or a log (170 §3.1; I4 criterion 5). At the reference deployment's 1,000 people, I4's one connection per `(server, principal)` is up to 1,000 connections and `tools/list` caches per server, a cost no draft prices.
5. **Per-user authority on an MCP call.** vfs judges the caller at the entry (`list` to see, `read` to call) and nowhere after: what the remote tool reads or changes is outside the ladder, and its results come back as rows vfs did not gate (170 §4, except a vfs server's `dev.vfs/path`). A fresh node lets anyone, anonymous included, call every tool with the host's or the server's authority until the host sets two postures (170 §5.1). This is the one place where vfs's thesis, "permissions enforced before anything is dispatched" on the data itself (`README.md:13`), stops at the door.
6. **Approval of side effects.** In specs 167, 170 and 171 nothing stops a side effect for a human: elicitation is `unsupported` (170 §4), MCP annotations are text in a manifest, and over the wire the harness sees one `cli` tool that is "neither read-only nor marked destructive" (171 §1.3), so a host that approves per tool call approves a whole line, `post_message` and all, or none of it. The roadmap's `pending`, preview, policy hook and durable run (H2–H5) would answer this inside vfs, and are the largest drafted-but-unspecced block in the code-mode path. The static parse and the resolution of every name before anything runs (167 §2–§3) make a pre-flight effect summary of a line possible, the "static `analyze()` summary" the agent-shell memo listed as an idea to copy (memo §11); no draft carries it.
7. **Replay.** A re-sent `cli` line runs again (171 rebase note on spec 177), and `tools/call` is never auto-retried (170 §3.3). A code-mode client that retries a timed-out call can duplicate a remote side effect; only vfs's own verbs have a replay contract (spec 177).
8. **Reusable code.** Nothing lets an agent save a working line as a named command: there is no shell-script program kind (169 §a5 suffixes are `.wasm` and 172's), `source` and `.` are `unrecognized` (167 §4), and skills are read-only documents (`roadmap.md:680`). A Python script stored as a row and run with `python3 script.py` is the only drafted reuse path (172; T5a).
9. **Evidence.** vfs has no measurement of its own for the claim a code mode rests on (fewer tokens, fewer round trips, better accuracy than per-tool calls), and no call log to measure it from (F10). Spec 167's harness measures bash fidelity, not task success.

## What this means for a vfs code mode

INFERRED, kept apart from the evidence above.

- **The substrate is the strongest part, and it is already built.** A gated verb set, one `Result`, an `Authority` value judged on every row, versions and trash: that is what Code Mode's designs bolt onto a sandbox from outside. The call surface (a shell over those verbs) and the tool catalogue (views under `/.vfs`) are fully drafted and entirely unbuilt.
- **The drafts chose discovery by browsing over discovery by search.** `ls`, `type`, `--help` and in-memory `grep` are drafted; ranked search over tools is not. The live tree's accidental `/.agents` behaviour (stored manifests that `search` ranks and grants hide) is closer to "tools are files, searchable like anything else" than the drafted views are. Reconciling the two is the first decision a vfs code mode needs, and the other studies' evidence on tool retrieval bears directly on it.
- **"Results as files" is a redirect, not a default.** The vfs-shaped answer to Code Mode's "keep intermediate results out of the context" is already in the grammar: `tool … > /work/x.json` puts a result in a governed, versioned, searchable file and prints nothing. What is missing is a durable, readable default home for results the agent did not redirect, and its retention and visibility rules at 150,000 calls a day.
- **The shell is a weak language for JSON.** Without `jq` in 0.1.0 and with `structuredContent` kept off the pipe, multi-step data work between tools falls to `grep -o` over prose or to the Python guest. A code mode that wants the shell to be the language either needs a JSON program in the first release or must say the Python guest is the structured half.
- **Authority survives the hop into a tool only at the door.** The caller's rung decides whether a tool may be called; the tool then runs as the host or as the server's one credential. Per-principal credentials (I4) are the piece that would let "per-user permissions survive the hop" for MCP; it has a story but no spec.
- **Approval is the open seam.** The brief's seventh point, human approval of side effects, has no answer in the three core specs and a large answer on the roadmap. A single `cli` tool hides every effect from a harness's per-tool approval, so either vfs provides the stop (`pending`) or a host loses approval granularity by adopting `cli`.

## What this study does not settle

- Whether the roadmap's reversals (full bash, `/.vfs/run` as rows, per-principal credentials, `pending` for elicitation, `vfs serve`) are decided: the roadmap says none of its content is a decision, and the specs it amends were not rewritten.
- The cost of a ranked-search leg over synthesized catalogues against stored manifests, at the reference deployment's scale or at a realistic catalogue size; no catalogue census exists (spec 170's "real-server schema census" is commissioned, not run).
- How an `Authority` built per MCP request compares for equality across requests, which decides who can read a `/.vfs/run` record over the wire.
- Any token, latency or accuracy number for `cli` against per-verb tools or direct MCP calls; none exists in the tree, and this study ran none.
- The ADR pins themselves: ADRs 081 to 086 are cited everywhere and present nowhere, so this study read them only through the specs' restatements.

## One line

vfs has built the gated verbs, the `Result` and the per-row `Authority` that a code mode needs underneath, has drafted the shell, the `cli` tool and tools-as-views in detail, and lacks four things a code mode would hit at once: ranked search over tool definitions (the drafts retire the stored `/.agents` manifests that `search` already ranks today), a durable default home for tool results, a structured-data path between tool calls in the shell, and any approval or per-user credential at the point a tool's side effect leaves vfs.
