# Research: host tools as shell programs, and tools that interrupt

## The question

Can a host application define a tool the way a LangChain tool is defined, have it run as a program on a vfs shell line, and have it stop to collect a person's answer and then continue, as a LangGraph tool does with `interrupt()` and `Command(resume=...)`? And can an existing LangChain `BaseTool` or `@tool` function be mounted with no rewrite?

This memo answers four things. First, how LangChain and LangGraph do it, from their source and from executed spikes. Second, how other agent systems and shells expose host tools and let them pause. Third, what vfs already has and has planned. Fourth, a design for vfs, question by question, with a recommendation and a refused alternative for each.

Terms used throughout. A **tool** is a host-defined function with a typed argument schema. A **program** is a name the shell runs that is not a bash builtin. An **interrupt** is vfs's word for a call that stops and waits for a person; vfs never asks and never holds a call open. A **run** is one shell line, durable across a stop. A **request key** is the shell machine's `(task path, ordinal)` name for each request, a function of the line. A **fingerprint** is a sha256 of a call's verb and canonical arguments (spec 177 §3.3). **Re-entry** means calling a tool's body again from its first line.

## Sources

Every claim below is marked READ (read in the named file or page), EXECUTED (ran it; the script is named), or INFERRED (reasoning from what was read or run). Nothing is cited from memory.

Reference clones, each refreshed on 2026-11-21 with `git fetch origin` and a detached checkout of the branch `origin/HEAD` names. None was dirty.

| Clone | Default branch | Commit | Date | License |
|---|---|---|---|---|
| langgraph | main | c6335a4 (libs/langgraph 1.2.24, prebuilt 1.1.3) | 2026-11-20 | MIT |
| langchain | master | 8ff3cd3 (core 1.8.4, langchain 1.5.2) | 2026-11-20 | MIT |
| deepagents | main | 65d33b2 (0.7.41) | 2026-11-21 | MIT |
| openai-agents-python | main | 6c4e4a2 | 2026-11-20 | MIT |
| adk-python | main | 2b90353c | 2026-11-20 | Apache-2.0 |
| claude-agent-sdk-python | main | 3184360 | 2026-11-20 | MIT |
| modelcontextprotocol | main | b7e13978 | 2026-11-21 | MIT moving to Apache-2.0 (spec), CC-BY-4.0 (docs) |
| python-sdk | main | 77001c96 | 2026-11-05 | MIT |
| fastmcp | main | 5ac27a2c | 2026-11-20 | Apache-2.0 |
| eve | main | 5c52fbff40 | 2026-11-21 | Apache-2.0 |
| letta | main | 8816d3a85 (fetch returned no newer commit) | 2026-10-18 | Apache-2.0 |
| just-bash | main | ec5ab76 | 2026-11-20 | Apache-2.0 (package.json; no top-level LICENSE file) |
| just-bash-py | main | 48d111c | 2026-06-04 | Apache-2.0 (pyproject; no LICENSE file) |
| bashkit | main | 290ebb0 | 2026-11-20 | MIT |
| brush | main | c7748dd | 2026-11-19 | MIT |
| nushell | main | a661e23 | 2026-11-21 | MIT |
| mirage | main | bc64fcb5c7 | 2026-11-21 | Apache-2.0 |
| agentfs | main | 0a014eb | 2026-06-03 | MIT (sdk/rust/Cargo.toml, sdk/typescript/package.json; no top-level LICENSE file) |
| mcpfs | main | 640511e | 2026-03-06 | MIT |

Two fetches printed a ref-name conflict on a non-default branch (langchain `mdrxy/openai/require-chat-model`, eve `renovate-geistdocs/...`); the default branch updated in both.

Packages used by the spikes, installed by `uv run --no-project --with langgraph --with langchain-core` on 2026-11-21 under Python 3.13: langgraph 1.2.24, langchain-core 1.8.4, langgraph-prebuilt 1.1.3, langgraph-checkpoint 4.3.2, pydantic 2.14. These equal the versions in the clones.

Spikes, in `spikes/` beside this memo: `langgraph_resume.py` (scenarios S1 to S7) and `langchain_injection.py` (scenarios A to J). Each runs with no model, no API key and no network beyond the install.

Pages: <https://docs.langchain.com/oss/python/langgraph/interrupts>, accessed 2026-11-21.

vfs sources, all in the worktree on branch `a-call-is-interrupted-and-the-host-asks` (commit f15a2fd9): `documentation/how-to/interrupt-a-call-and-ask-a-person.md`; `context/standards/roadmap.md` §5, §10, §16; `context/specifications/active/169-*`, `170-*`, `171-*`, `177-*`. The shell, read with `git show origin/the-shell-speaks-bash:<path>` at 10224a74 (2026-11-21): `agents/2026-11-21-the-shell-speaks-bash/spec.md`, `crates/vfs-shell/src/machine/mod.rs`, `machine/exec.rs`, `machine/shell.rs`, `programs/mod.rs`, `crates/vfs-core/src/shell_binding.rs`, `src/vfs/shell/host.py`, `src/vfs/sync.py`.

## Findings A: LangChain and LangGraph

### A1. How a tool is defined

- `BaseTool` is a pydantic model with `name`, `description`, `args_schema` (a pydantic model class or a JSON-schema dict), `return_direct`, `handle_tool_error`, `handle_validation_error` and `response_format` (`"content"` or `"content_and_artifact"`). READ `langchain/libs/core/langchain_core/tools/base.py:475-554`.
- The schema a model sees is `tool_call_schema`, not `args_schema`. It is the input model with every injected argument removed. READ `base.py:677-723`. EXECUTED (`langchain_injection.py` A): for a tool with `fs: Annotated[Handle, InjectedToolArg]`, `tool_call_schema` lists only `path`, while `get_input_schema()` holds `fs` and `path` and cannot even be rendered as JSON schema (`PydanticInvalidForJsonSchema`).
- `@tool` builds a `StructuredTool` from a function, inferring the schema from the signature, and optionally from the docstring (`parse_docstring`). READ `tools/convert.py:18-90`. A `StructuredTool` holds `func`, `coroutine` or both; with only `func`, the async path runs it in an executor; with only `coroutine`, the sync path raises `NotImplementedError`. READ `tools/structured.py:121-123`, `:154`. A `BaseTool` subclass without `_arun` gets a default that runs `_run` in an executor. READ `base.py:920-933`.
- Injected arguments are hidden from the model and supplied at call time. `InjectedToolArg` is the marker (`base.py:1727`), `InjectedToolCallId` a subclass (`base.py:1757`). LangGraph adds `InjectedState`, `InjectedStore` and `ToolRuntime`, a dataclass carrying `state`, `context`, `config`, `stream_writer`, `tool_call_id`, `store` and `tools`, injected when a parameter is typed `ToolRuntime`. READ `langgraph/libs/prebuilt/langgraph/prebuilt/tool_node.py:1714-1782`, `:1805`. The injection is done by `ToolNode._inject_tool_args`, not by `BaseTool.invoke`. READ `tool_node.py:974-976`, `:1367`.
- EXECUTED (`langchain_injection.py` B to D): an injected argument is supplied on a direct `invoke` by putting it in the arguments dict; a missing one is a `ValidationError`. A tool that declares `InjectedToolCallId` refuses plain arguments (`ValueError`) and must be invoked with a full ToolCall dict (`{"name", "args", "id", "type": "tool_call"}`), which then returns a `ToolMessage`. A `ToolRuntime` built by the caller and passed in the dict is accepted.
- Results and errors. `run` turns a `ToolException` into content when `handle_tool_error` is set, a validation error likewise under `handle_validation_error`, and re-raises everything else. READ `base.py:1089-1136`. EXECUTED (G, H): with plain arguments a handled `ToolException` comes back as a plain string, indistinguishable from success; with a ToolCall it is a `ToolMessage` with `status="error"`. A plain exception propagates. `content_and_artifact` returns only the content for plain arguments and both for a ToolCall (E). A tool may return a LangGraph `Command` (F), which means "update the graph's state" and has no meaning outside a graph.

### A2. How `interrupt()` works

- `interrupt(value, *, response_schema=None)` reads the running config, takes the task's scratchpad, and increments the task's interrupt counter. If the scratchpad's `resume` list has an answer at this index it returns it. Otherwise, if a resume value addressed to no task is pending, it consumes it, appends it to the list and returns it. Otherwise it raises `GraphInterrupt` carrying one `Interrupt(value, id, response_schema)`. READ `langgraph/libs/langgraph/langgraph/types.py:913-1058`.
- The docstring says it plainly: the first call raises, the client resumes with `Command`, and "The graph resumes from the start of the node, **re-executing** all logic"; several interrupts in one node are matched "based on their order in the node", per task. READ `types.py:926-933`.
- The interrupt id is a hash of the task's checkpoint namespace and the number of answers the task already has, so the first and second interrupt of one task have different ids. READ `types.py:583-589`. EXECUTED (S1): the two ids differ.
- What the checkpointer stores is the answers, not the stack. Each answer is a pending write `(task_id, "__resume__", [answers so far])` on the checkpoint; on the next run the task's scratchpad is rebuilt from those writes, and a `Command(resume={id: value})` map adds the answer whose id matches the task's next slot. READ `pregel/_algo.py:1293-1363`, `types.py:1037`, `:1045`. INFERRED: nothing of the Python frame is saved, which is why the node must run again.
- `Command(graph, update, resume, goto)`: `resume` is either one value for the next interrupt or a map of interrupt ids to values. READ `types.py:842-868`. `invoke(..., version="v2")` returns `GraphOutput(value, interrupts)`; the older `result["__interrupt__"]` still works with a deprecation warning. READ `types.py:380-407`.
- `response_schema` is surfaced to the client as JSON schema; a pydantic model, TypedDict or dataclass also validates the answer, and a bad answer raises with nothing saved, "so the interrupt can be answered again". READ `types.py:996-1012`.
- `GraphInterrupt` derives from `GraphBubbleUp`, which derives from `Exception`. READ `errors.py:52`, `:104`. EXECUTED (S7). So a tool body's `except Exception` swallows it; the docs say "Do not wrap `interrupt` calls in bare try/except blocks". READ the interrupts page.
- The docs' rules, READ from the interrupts page: side effects before `interrupt` "should (ideally) be idempotent" because the node is re-run; "Place side effects after `interrupt` calls"; "Do not conditionally skip `interrupt` calls within a node"; "Do not loop `interrupt` calls using logic that isn't deterministic across executions"; "Matching is strictly index-based"; the payload "must be JSON-serializable"; resuming several at once maps "each interrupt ID to its resume value"; a durable checkpointer and the same `thread_id` are required.

### A3. What re-runs, measured

EXECUTED (`langgraph_resume.py` S1): a `@tool` that counts one effect before its first interrupt, one between the two, and one after the second, called from a one-node graph with `InMemorySaver`.

| After | Body entered | Effect before first ask | Effect between | Effect after second |
|---|---|---|---|---|
| first run (stops at ask 1) | 1 | 1 | 0 | 0 |
| first resume (stops at ask 2) | 2 | 2 | 1 | 0 |
| second resume (done) | 3 | 3 | 2 | 1 |

A tool with N interrupts is entered N + 1 times, and an effect placed before the k-th interrupt runs N + 2 − k times. This is LangGraph's documented behaviour, now counted.

EXECUTED (S3, S4): granularity is the task, not the tool. In a `ToolNode` that runs two tool calls in one task, a sibling tool with no interrupt was entered 3 times while its neighbour asked twice. With one `Send` per tool call, the shape `create_agent` uses (READ `langchain/libs/langchain_v1/langchain/agents/factory.py:2032`), the sibling was entered once.

EXECUTED (S2): an unmodified tool that calls `langgraph.types.interrupt()` outside a graph fails with `KeyError: '__pregel_scratchpad'`, after running the code before the call. `tool.invoke` sets a runnable config, so `get_config()` succeeds (READ `langgraph/config.py:17-29`), but the config has no scratchpad. INFERRED: catching `GraphInterrupt` is not enough for vfs to run such a tool; vfs must also provide the context `interrupt()` reads.

EXECUTED (S5, S6): placing a scratchpad in the config passed to `tool.invoke`, built from LangGraph's private `langgraph._internal._scratchpad.PregelScratchpad` with a recorded answer list, makes an unmodified tool behave exactly as under a graph: with 0, 1 and 2 recorded answers it raises at ask 1, raises at ask 2, and returns, entering the body once per call. It also works through `ainvoke` of a sync-only tool, which LangChain runs on an executor thread with the context copied.

### A4. Approval before the call: `HumanInTheLoopMiddleware` and `interrupt_on`

- `HumanInTheLoopMiddleware(interrupt_on={tool_name: True | False | InterruptOnConfig})` pauses before a gated tool call runs. Decisions are `approve`, `edit`, `reject` and `respond`. READ `langchain/libs/langchain_v1/langchain/agents/middleware/human_in_the_loop.py:87`, `:402-491`. In `"batched"` mode one interrupt per model turn lists every gated call and is answered with decisions by position; in `"per_call"` mode, planned to become the default, there is one interrupt per call with its own `response_schema`, answered by id. READ `:409-418`.
- A `when` predicate decides per call; it runs again on resume and must return the same answer, or the decisions no longer line up. READ `:362-392`.
- deepagents builds `interrupt_on` from filesystem permission rules whose `mode` is `"allow"`, `"deny"` or `"interrupt"`, with a `when` predicate per filesystem tool by path scope (exact or bulk). READ `deepagents/libs/deepagents/deepagents/middleware/filesystem.py:386-396`, `middleware/_fs_interrupt.py:1-48`, `graph.py:979-984`. INFERRED: this is the same shape as vfs's policy hook returning `Decision.interrupt`, applied to tool calls by name.
- In this shape the tool body is not entered until the decision exists, so it runs once. INFERRED from A3: approval before the call is the only LangChain shape in which a tool's own effects never repeat.

### A5. What a host needs to drive it

READ (`types.py:976-993`, the interrupts page): a checkpointer; `config={"configurable": {"thread_id": ...}}`, the same on every resume; the interrupts on the result (`GraphOutput.interrupts`, or the `__interrupt__` key); `Command(resume=value)` for one, or `Command(resume={interrupt.id: value, ...})` for several at once.

LangGraph's functional API offers the other durable pattern: a `@task` inside an `@entrypoint` is not re-executed on resume, because its result is saved by the checkpointer. READ `langgraph/libs/langgraph/langgraph/func/__init__.py:340-341`. INFERRED: LangGraph has both models, re-run the node and cache the step, and lets the author choose by where effects are placed.

## Findings B: other systems

Section B was read by two delegated read-only studies over the clones listed above; each claim below carries the citation the study returned. The load-bearing ones were re-read for this memo: the MCP `InputRequiredResult` and SEP-2322's status, python-sdk's note that resolver bodies re-run, the MRTR warning on single use, bashkit's host-call comment, its positional refusal and its sanitised callback error, and nushell's rest positional. All held. The letta default branch holds only a README saying the code moved; its retired server was read from `origin/archive` (56ba9c255, 2026-08-13) with `git show` only.

### B1. Agent SDKs and MCP: how a tool pauses

| System | Tool and schema | Injection | Pause | What resumes | Host sends back |
|---|---|---|---|---|---|
| openai-agents | `@function_tool`; schema from signature and docstring via pydantic (`src/agents/function_schema.py:321-557`) | first parameter typed `RunContextWrapper` or `ToolContext` (`:389-411`) | approval before the call, `needs_approval` (`src/agents/tool.py:500-512`); no in-body input for plain tools | body not started; first run after approval (`run_internal/tool_execution.py:1970-1975`, `tool_planning.py:924-988`) | `RunState.approve` or `reject`, serialisable to JSON (`run_state.py:1381-1428`, `:1921`), then `Runner.run(agent, state)` |
| adk-python | `FunctionTool(func, require_confirmation=)`; schema from type hints | `tool_context: ToolContext` by type or name (`utils/context_utils.py:69-99`) | approval, and in-body `request_confirmation` (`tools/function_tool.py:529-554`); `LongRunningFunctionTool` | confirmation: the tool pipeline is re-invoked from the top with `tool_confirmation` set (`flows/llm_flows/tools/_confirmation.py:392-402`); long-running: not re-invoked, the client's response is the result (`_rearranger.py:110-135`) | `FunctionResponse("adk_request_confirmation", {confirmed, payload})` |
| claude-agent-sdk | `@tool(name, description, input_schema)` declared, not inferred, served as an in-process MCP server (`src/claude_agent_sdk/__init__.py:266-361`, `:517-645`) | none; closures | `can_use_tool` callback before the call, may rewrite input (`types.py:258-320`); a hook may `defer` (`types.py:1726-1737`); elicitation from in-process tools "not forwarded yet" (`__init__.py:583-584`) | not started; the callback is awaited live | `PermissionResultAllow(updated_input)` or `Deny(message, interrupt)` |
| MCP 2026-07-28 | `inputSchema` object root, optional `outputSchema` (`docs/specification/2026-07-28/server/tools.mdx:290-301`) | n/a | `tools/call` may return `InputRequiredResult` with `inputRequests` and an opaque `requestState` (`schema/2026-07-28/schema.ts:572-610`); SEP-2322 MRTR, Status Final (`seps/2322-MRTR.md:3`) | stateless: the server handles the retried call again; state lives only in `requestState` | the same `tools/call` with a new id, `inputResponses` and the echoed `requestState` |
| python-sdk | `@mcp.tool()`; schema from signature (`utilities/func_metadata.py:287-490`) | `Context`-typed parameter | MRTR by hand or by `Resolve` resolvers (`resolve.py:102-165`) | "Resolver bodies may re-run on every round" (`resolve.py:13-16`); answers sealed in `requestState` with AES-GCM, TTL and an argument digest (`server/request_state.py:94-405`) | the retry with `inputResponses` |
| fastmcp | `@mcp.tool()`; TypeAdapter over the signature (`tools/function_parsing.py:220-369`) | `Context` becomes a dependency | MRTR guard; tasks with `input_required` | re-run from the top per round and per task leg (`docs/servers/elicitation.mdx:396-420`, `fastmcp_tasks/handlers.py:335-400`) | retry, or `tasks/update` |
| eve | `defineTool({inputSchema, execute, approval})`, named by file (`packages/eve/src/tools/definition.ts:268-314`) | `ctx: ToolContext` | approval policy (`tools/approval/policies.ts:78-94`); in-body `ctx.ask` only in workflow tools (`execution/tools/workflow/ask.ts:124-166`) | approval: first run after re-validating input, policy and tool version (`harness/hitl/approved-calls.ts:98-148`); `ask`: the workflow replays from the start reusing recorded steps (`docs/tools/workflows.mdx:156-161`) | `session.respond([{interactionId, optionId, text}])` |
| letta (archive) | stored source text; schema from its AST and docstring (`letta/functions/functions.py:218-317`) | `agent_state` and others by parameter name | approval rule; nothing in the step runs until answered (`agents/letta_agent_v3.py:1681-1709`); no in-body input | first run after approval | `ApprovalCreate{approvals}` matched by tool call id |

Three facts from B1 shape the design.

- **Approval before the call is universal, and the body then runs for the first time.** openai-agents, ADK, the Claude SDK, eve and letta all do it. READ (citations above).
- **Input from inside a body is re-entry or replay.** ADK, MCP's MRTR, python-sdk and fastmcp re-run the body with the answers injected; eve replays a workflow from its start and serves recorded steps. No system resumes a Python or JavaScript frame. READ.
- **Nobody promises exactly once.** openai-agents (`docs/human_in_the_loop.md:222-226`), eve (`docs/execution-model-and-durability.mdx:204-210`) and the MCP MRTR page (`basic/patterns/mrtr.mdx:238-243`: the measures "do not by themselves guarantee single-use") disclaim it; ADK says at least once on resume (`apps/_configs.py:33-36`). READ. Two keep a ledger that refuses to run a call whose start was recorded and whose end was not: openai-agents (`tool_planning.py:522-526`) and eve (`harness/interrupted-attempt.ts:12-50`). That is spec 177's claim and D46's in-doubt rule.

INFERRED: MCP's MRTR has the same resume contract vfs's single call already has (the call is made again with the answers, and the server checks a digest of the arguments). An MCP server's `input_required` maps onto a vfs tool interrupt with no new mechanism, as H5 criterion 4 plans.

### B2. Shells: how a host function becomes a command

| System | Registration | Typed schema | Flag rule | Stdin | Output and exit | Clash rule | Suspends |
|---|---|---|---|---|---|---|---|
| just-bash | `defineCommand`, `customCommands`; stub files in `/bin` (`packages/just-bash/src/Bash.ts:548-607`); the executor turns dotted tool paths into `ns sub-cmd` (`just-bash-executor/src/tool-command.ts:354-398`) | no; values guessed by `JSON.parse` (`tool-command.ts:44-51`) | `--k v`, `--k=v`, `k=v`, `--json`, a lone `{...}` operand; last wins; no required check (`:73-170`) | piped JSON object as the lowest layer; non-JSON ignored (`:82-92`) | `JSON.stringify(result)` and a newline, 0; a throw is `cmd: msg`, 1 | special builtins, functions, builtins, then custom; custom may shadow a bundled command and gets it as `origCommand` | async await only; approval and elicitation are awaited host callbacks |
| bashkit | `ToolDef` plus `ToolRegistry` become builtins with `help` and `discover` (`crates/bashkit-scripted-tool/src/scripted_tool/extension.rs:282-317`) | JSON schema, with `$ref`, unions, nullables (`src/tool_def.rs:767-830`) | long flags only, positionals refused (`tool_def.rs:417`); bare boolean is true, `=false` false; arrays as JSON, `a,b,c` or repeated; objects as JSON or `k=v` groups; whole object validated in the registry (`tool_registry.rs:438-441`) | raw, never bound to a property (`tool_def.rs:79-85`) | string to stdout, 0; usage or schema error 2; callback error 1, sanitised to "callback failed" (`tool_def.rs:279-290`); unknown 127; `--help` from the schema, `--dry-run` | function, special builtins, host registry, builtins (later insert wins) | **yes**: `host_call_builtin`, `start_execution`, `next_event` gives `HostCall{command, args, env, cwd, stdin}`, `resume(id, ExecResult)`; "not interpreter snapshots and cannot be serialized or resumed elsewhere" (`crates/bashkit/src/host_call.rs:1-2`) |
| brush | `ShellBuilder::builtin(name, Registration::of::<B>())` (`brush-core/src/shell/builder.rs:89-105`) | the typed struct is the schema (clap) | the parser's | `io::Read` | writes and an exit code; usage error 2 | POSIX special, function, builtin, PATH | no |
| nushell | `Command` and `PluginCommand` traits; `plugin add` | `Signature` with `SyntaxShape`, checked at parse time (`crates/nu-protocol/src/signature.rs:364-385`) | required, optional and one rest positional (rest is optional, `:655-661`); `--long` and `-s`; `.switch` for booleans, `--x=false` allowed; `--` ends flags; unknown flag a parse error; record spread `...{flag: v}` as the escape hatch; `--help` and `-h` added to every signature (`:515-536`) | a separate typed pipeline input, never an argument | values and streams; errors are values, not exit codes | latest declaration wins; `^name` forces external, `%name` forces builtin | a plugin may block on engine calls; no host-facing suspension |
| mirage | `register_cli`; `mcp_cli` makes one subcommand per MCP tool (`python/mirage/commands/cli/mcp/build.py:81-155`) | shown in help only | one optional JSON-object operand per MCP tool; bad JSON or a second operand is 2 (`call.py:98-132`) | unused for arguments | text blocks verbatim, others JSON, a newline ensured; `isError` to stderr, 1; a write bit from `readOnlyHint` | **refused at install** on a clash with builtins, keywords, commands or another CLI (`workspace/cli/registry.py:76-121`) | async await only |
| mcpfs | FUSE files for list and get tools; `mcpfs tool <srv> <tool> --flags` (`pkg/mcptool/dispatch.go:17-64`) | flat properties only | long flags, positionals refused, arrays comma-split | none | pretty JSON, 0 or 1; `isError` ignored (`pkg/mcpclient/client.go:183-205`); a read calls the tool on every `getattr` and `read` (`internal/fuse/toolnode.go:30-74`) | a resource beats a tool | no |
| agentfs, just-bash-py | no tool-as-command layer; agentfs keeps a tool-call audit table with a pending row (`sdk/rust/src/toolcalls.rs:127-160`); just-bash-py takes raw argv (`src/just_bash/types.py:204-210`) | no | raw argv | `ctx.stdin` | `ExecResult` | functions, builtins, commands | no |

Four facts from B2 shape the design.

- **No two systems agree on the flag rule, and each refuses a piece.** bashkit and mcpfs refuse positionals; nushell has them, with a rest positional; mirage takes one JSON operand; just-bash guesses types. READ. INFERRED: spec 170's table (positionals for required scalars, repeated flags for arrays, JSON for objects, `--json` for the whole object) is a superset of what the others offer, and nushell is the precedent for the rest positional added in D2.
- **Comma-splitting arrays is a trap.** bashkit and mcpfs split `a,b,c`; mcpfs ignores the item type. READ. A value that contains a comma cannot be passed. Spec 170's "never comma-split" stands.
- **A host suspension is never serialisable in any shell studied.** bashkit's host call is the closest to vfs's request model and says so in its first line. READ. INFERRED: a durable stop must be a re-walk over recorded replies, which is what the vfs machine's keys allow and bashkit's do not attempt.
- **Clashes are refused at install where it matters.** mirage refuses at install; just-bash and bashkit let a custom command shadow a bundled one silently. READ. D1 follows mirage, and mcpfs's call-on-`getattr` is the counter-example spec 170's "stat never executes" already answers.

## Findings C: what vfs has and has planned

### C1. The interrupt API being built

READ `documentation/how-to/interrupt-a-call-and-ask-a-person.md`. A policy returns `Decision.allow()`, `deny` or `interrupt(reason)`. An interrupted call returns `result.interrupted` with `Interrupt` values carrying `id`, `reason`, `op`, `paths`, `preview`, `asked_by` and `expires_at`. `fs.answer(id, allow=, reason=, authority=)` records an answer; only the file system holds `answer`, never a session or a shell command. A single call continues by being made again; the answer is used once, covers that exact call (its fingerprint) and the file the person saw. A shell line that stops is a run with a `run_id`; `session.resume(run_id)` continues it "where it stopped", and "Nothing ran twice". Interrupts live in the database and lapse after 24 hours. The guide shows a LangGraph node wrapping a vfs call. Tools are not covered: `answer` takes only `allow`, and an `Interrupt` has no payload.

### C2. The roadmap's plan

- §5 states the ruling of 2026-10-28: a run "is never re-run from the top"; each step is recorded as it finishes; `resume(run_id)` "walks the line again, but every finished step is served from the ledger" and only unfinished steps run. READ `roadmap.md:239-245`.
- The same paragraph states the exception for code vfs does not own: "a host tool, a Python guest — is re-entered from the start, with the vfs calls it already made served from the ledger as long as they are the same calls; if the code took a different path, the differing call is made fresh and marked". READ `roadmap.md:245`. Decision D42 leans the same way for 0.1.0, with full recording and memory snapshot as 0.2 options. READ `roadmap.md:1120`.
- H4 (the durable run): rules for whose authority, what is recorded (effects, expansion reads, identity triples of other reads), claim-first crash handling with `in_doubt`, and drain-then-stop per pipeline (D40). READ `roadmap.md:320-334`, `:1118-1123`.
- H5 (interrupts for every tool kind): a host tool raises `Interrupt(payload)`; its stage ends with exit 75 (`EX_TEMPFAIL`, D12); a framework's own interrupt type (LangGraph's) is caught and converted; on resume the tool is re-entered once, its interrupt calls return the recorded answers in order, and its `Fs` calls are served by fingerprint, a mismatch made fresh with one `vfs.replay_diverged` record; `producer | interrupting_tool | consumer` stops with the consumer having received exactly the producer's bytes before the stop and neither data nor end-of-stream after. READ `roadmap.md:336-345`, `:1090`.
- Domain G: a host tool runs with the host's authority; it receives the caller's `Fs` only if it declares one; it is gated by `read` on `/.vfs/tools/<name>`. READ `roadmap.md:676-684`. T3's acceptance: a `BaseTool` accepted by shape without importing `langchain_core`; the flag table; `cat` of a tool never runs it; `ToolError` → exit 1; a sync tool past its deadline → 124. READ `roadmap.md:706-715`.

### C3. The drafted specs

- Spec 170 §1 to §2 (READ `170-*/spec.md:17-52`): registration `register_tool(fn, *, name, description, schema, stdin, mime_type, deadline, capabilities)`; `/.vfs/tools/<name>` is a manifest file; the return-value rows (`str` text, `bytes`, `None` no row, else JSON); `ToolError` versus any other exception; sync bodies on a worker thread abandoned at the deadline; and the schema-to-flags table, quoted in D2 below. §5 (`:113-133`): one router-internal door `_invoke(path, arguments, *, authority)`; gate order resolve (127), then `read` on the entry (126), then the call; "an open node lets anyone call every host tool", accepted, and locked by `posture("/.vfs/tools", "list")`. §4 (`:101-111`) maps an MCP elicitation to `vfs.unsupported` 126, which H5 flips to 75.
- Spec 169 (READ `169-*/spec.md:12`, `:84-105`): kernel names may not be shadowed by stored programs unless in `Index.prefer_stored`.
- Spec 177 (READ `177-*/spec.md:265-304`): the fingerprint is `sha256(frame(b"vfs.call.1", op, *canonical(arguments)))`, pinned by a golden test; the replay store claims a key with one `INSERT` before the call runs, so a rival send waits and a crash leaves a claim.
- Stale parts: these specs cite retired ADRs and engines other than SQLite and Postgres (spec 177's rival analysis names SQL Server, Oracle and MariaDB). READ. Their mechanisms, not their citations, are used below.

### C4. The shell as built

- The machine does no IO; `step(replies)` returns output chunks, open requests keyed by `RequestKey { task: Vec<u32>, ordinal: u32 }`, and a status. READ `crates/vfs-shell/src/machine/mod.rs:118-133`, `:232-261`, `:317-347`. The key is allocated by `Shell::key()` from the task path and a counter; a subshell forks a child path. READ `machine/shell.rs:322-334`.
- `Request` has `Read`, `Write`, `Touch`, `Stat`, `List`, `Mkdir`, `Remove`, `Copy`, `Move` and `Value`. There is no request to run a program. READ `mod.rs:146-191`. `ProgramKind` has one variant, `Library`. READ `mod.rs:71-76`. The binding maps every program name to `Library`. READ `crates/vfs-core/src/shell_binding.rs:49`.
- The program table is 18 names: `cat cp cut find grep head ls mkdir mv rm sed sort tail tee touch tr uniq wc`. READ `programs/mod.rs:19-22`. There is no `xargs`. INFERRED: the goal's example `ls ... | xargs convert` needs a library `xargs` that runs another program, so `xargs` is itself a consumer of the program seam.
- Name lookup is function, then builtin, then program; a command word containing `/` is refused with 127 before the program table is consulted. READ `machine/exec.rs:960-990`. INFERRED: `/.vfs/tools/convert --to pdf` cannot run today.
- The machine is a pinned future over `Rc` state and the Python class is `unsendable`. READ `mod.rs:268-274`, `shell_binding.rs:18`. INFERRED: a stopped machine cannot be saved to the database or moved to another process; a resume must build a new machine from the line and feed it recorded replies by key. That is what decision 5 of the shell spec intends ("the law the durable run resumes by").
- The Python host answers a step's requests one at a time, in order, each as one public verb with the caller's authority, and refuses the system actor. READ `src/vfs/shell/host.py:96-150`, `:167-180`.
- The synchronous face runs one loop on its own daemon thread and refuses a call made from that loop thread, because the call would block the loop on a future the same loop must finish. READ `src/vfs/sync.py:58-62`, `:637-638`, `:706-713`.

## The design

### D1. Registration

Facts that bind it. LangChain tools are values with a name, a description and a schema (A1). vfs registration belongs to the host, not the agent (C2, spec 170 §1). Lookup in the machine is function, builtin, program (C4).

Proposal.

```python
@fs.tool                                  # a plain function, sync or async
def convert(path: str, to: str = "pdf", *, fs: Fs) -> str:
    """Convert a document."""

fs.add_tool(some_langchain_tool)          # any BaseTool, by shape
fs.add_tools(toolkit.get_tools())         # several at once
fs.add_tool(fn, name="pdf", stdin="body", approve=True, shadow=False)
fs.remove_tool("pdf")
```

- `@fs.tool` and `add_tool` are on the file system (the admin plane), never on a session, like `answer`. A plain function's schema comes from its signature through pydantic; a parameter typed `Fs`, `AsyncFs` or `ToolContext` is injected and never in the schema.
- A LangChain tool is recognised by shape: `name`, `description`, `tool_call_schema` and `ainvoke`. The schema is `tool_call_schema`, never `args_schema`, because `args_schema` holds injected arguments and may not render as JSON schema (A1, EXECUTED). This corrects T3's "by shape (`name`, `description`, `args_schema`, `ainvoke`)".
- An MCP server's tools come through `add_mcp` (T4) and live under `/.vfs/mcp/<server>/tools/<tool>`; their bare names are not on the program table unless the host maps them (`add_mcp(..., programs={"gh-issue": "create_issue"})`), so a remote server cannot take a bare command name.
- Where a tool appears: `/.vfs/tools/<name>` as its manifest file (reading never runs it), `/.vfs/bin/<name>` in the union listing, and `<name>` on the machine's program table as a host program.
- Clashes. A bash builtin name (`echo`, `test`, `read`, `cd`, and the rest) is refused at registration with `ValueError`, because the machine would never reach the tool. A library program name (`cat`, `grep`, the 18) is refused unless `shadow=True`, matching spec 169's `prefer_stored`. A second tool of one name is refused unless the first is removed. A tool is always reachable by its path, which nothing shadows. A shell function of the same name defined on the line wins, as in bash; that is the line's own choice.

Recommendation: the decorator and `add_tool` above, LangChain by shape on `tool_call_schema`, refusal at registration for clashes. Refused: resolving clashes at call time by a priority list, because the agent would see a name that silently runs something else, and a registration error is caught by the host's tests on the first run.

### D2. Schema to command line

Facts that bind it. Spec 170 §2's table (C3). The prior art in B. A model writes the line, so the rule must be guessable from `--help` alone.

The rule, keeping spec 170's table with three changes.

| Schema property (after normalising `$ref`, nullable unions) | Command line | Notes |
|---|---|---|
| required scalar (string, integer, number, enum) | positional, in `required` order, or `--name value` | the first positional binds the first required property |
| optional scalar | `--name value` or `--name=value`; kebab alias `--max-count` | defaults are never sent; the tool applies them |
| boolean | `--name` sets true, `--no-name` sets false | never a separate value word |
| array of scalars | repeat: `--tag a --tag b`; or the rest positional when it is the last required property | never comma-split |
| object, array of objects, several-arm union | `--name '<json>'` | dotted flags (`--where.field`) deferred, as spec 170's census asks |
| bytes (`contentEncoding: base64`) | stdin, or `--name @path` | `@path` is read through vfs as the caller |
| the whole object | `--json '<object>'` or `--json -` | excludes every other binding |
| stdin present | binds to the one required property no flag set, or the one the host named (`stdin="body"`) | zero or several candidates is usage error 2 |

The three changes. First, a trailing required array takes the remaining positionals (`convert a.md b.md --to pdf`), which is how `xargs` passes operands, and how nushell's rest parameter works (B). Second, `@path` reads through vfs rather than the host disk. Third, `--help` is generated from `tool_call_schema` and the docstring, one line per property, and `-h` is an alias unless a property claims it.

Output. The tool's return value becomes stdout. A `str` is written as is, with a newline added when it has none, so `convert a | wc -l` counts one line. `bytes` are written raw. A `dict`, `list` or pydantic model is one line of JSON. `None` writes nothing. A LangChain `content_and_artifact` writes the content and keeps the artifact on the result's data. A LangGraph `Command` is exit 126 with "returns a graph Command, which a shell line cannot apply" on stderr.

Errors and exit status. vfs always invokes a LangChain tool with a ToolCall whose id is the request key, because only then does a handled `ToolException` come back distinguishable (`ToolMessage.status == "error"`, EXECUTED G). Then: success 0; `ToolError`, `ToolException` or `status="error"` → 1 with the message on stderr; any other exception → 1 with `<name>: tool failed (<ExceptionType>)` and the detail kept in the host log (spec 170 §1); a bad argument → 2 with zero tool calls; past the deadline → 124; not permitted → 126; not found → 127; stopped at an interrupt → 75 in the run's `statuses`, never delivered to the line (D6).

Recommendation: spec 170's table with the three changes. Refused: dotted flags for nested objects now, because no schema census has shown they are needed, and `--json` already reaches every shape.

### D3. The tool's own file access

Facts that bind it. A tool body runs in the host process with the host's privileges (C2). The roadmap's rule is the caller's `Fs`, and nothing wider (C3). LangChain hides a parameter annotated `InjectedToolArg` from the schema and accepts its value in the arguments dict (A1, EXECUTED B).

Proposal.

```python
@fs.tool
async def convert(path: str, to: str = "pdf", *, fs: AsyncFs) -> str:
    text = (await fs.read(path)).content          # as the caller, under the policy
    ...

@langchain_tool
def summarize(path: str, fs: Annotated[Fs, InjectedToolArg]) -> str:
    return fs.read(path).content                  # an unmodified LangChain idiom

from vfs.tools import context
def legacy(path: str) -> str:                     # cannot change its signature
    return context().fs.read(path).content
```

- The handle is a session over the caller's authority: the authority the line runs as, re-derived on resume (D45). Every call through it passes the gate and the policy, is a step of the run, and nests under the tool's row in the action log.
- It is injected three ways: by a parameter typed `Fs` or `AsyncFs` on a plain function; by a LangChain parameter annotated `InjectedToolArg` whose type is `Fs` or `AsyncFs`; and by a context variable, `vfs.tools.context()`, for code that cannot change its signature. A LangChain tool that declares `runtime: ToolRuntime` gets one built by vfs, with `context` set to the `ToolContext` and `tool_call_id` set to the request key (EXECUTED D); `state` is an empty mapping and `store` is `None`, because a shell line has neither.
- The `ToolContext` holds `fs`, `run_id`, `key` (the request key), `authority` (read-only) and `interrupt`.

Recommendation: injection by type, by `InjectedToolArg`, and by context variable, all giving the same caller-scoped session. Refused: handing the tool the host's own file system or the system actor, because a tool would then do what its caller cannot, which is the one thing vfs exists to stop.

### D4. Interrupting from inside a tool

Facts that bind it. LangGraph's `interrupt()` matches answers by index and raises an `Exception` subclass (A2). An unmodified tool's `interrupt()` needs LangGraph's scratchpad in its config (A3, EXECUTED S2, S5). vfs never asks (ruling).

Proposal.

```python
from vfs import interrupt

@fs.tool
def convert(path: str, to: str = "pdf", *, fs: Fs) -> str:
    ok = interrupt({"question": f"Convert {path} to {to}?"}, response_schema=bool)
    if not ok:
        raise ToolError("declined")
    ...
```

- `vfs.interrupt(payload, *, response_schema=None)` follows LangGraph's rules exactly, so one mental model serves both: the k-th call returns the k-th recorded answer; the first call without an answer stops the tool. The payload must be JSON. A `response_schema` (a JSON schema dict, a pydantic model, a TypedDict) is shown to the host and validates the answer at `answer` time.
- The stop is raised as `vfs.Interrupted`, a subclass of `BaseException`, not `Exception`. A body's `except Exception` then cannot swallow it, which removes LangGraph's documented foot-gun (A2). This follows `asyncio.CancelledError`, which moved to `BaseException` for the same reason. INFERRED.
- An unmodified LangChain tool that calls `langgraph.types.interrupt()` works through the adapter. The adapter invokes the tool with a config whose scratchpad holds the recorded answers and whose namespace is the run id and request key, then catches `GraphInterrupt` and converts its `Interrupt.value` and `response_schema` into a vfs interrupt (EXECUTED S5, S6). The scratchpad type and its config keys are LangGraph private names (`langgraph._internal`), so the adapter lives behind the `langchain` extra, pins a tested range of `langgraph`, and carries a conformance test that runs the S1 scenario against the shim on every supported version and fails loudly when the internals move.
- The `Interrupt` on a stopped result gains fields: `kind` (`"policy"` or `"tool"`), `program` (the tool name), `key` (the request key), `payload` (the tool's value, rendered as data), `response_schema`, and `run_id`. `reason` is the payload's `"question"` when present, else a fixed line. `preview` is `None` for a tool, because vfs cannot preview code it does not own (roadmap §5).
- `fs.answer(id, value=..., authority=)` delivers any JSON value. For a policy interrupt `allow=True` is shorthand for `value=True`; a tool interrupt requires `value=`. An answer that fails `response_schema` is refused with `vfs.invalid` and nothing is recorded, as LangGraph does.
- Who may answer a tool interrupt: the system actor, or an authority with `write` on `/.vfs/tools/<name>`. A tool interrupt names no file, so the policy rule of `write` on every path it names has nothing to check; the tool's catalogue entry is the path that stands for it.

Recommendation: `vfs.interrupt` with LangGraph's index rule and a `BaseException` stop, plus the shim adapter for unmodified LangGraph tools. Refused: implementing a LangGraph checkpointer over vfs storage and running each tool inside a one-node graph, which uses only public LangGraph API (EXECUTED S1 shows it works in one process); it would keep a second ledger beside the run record, in LangGraph's checkpoint format, for every tool call. It is the fallback if the shim's private names become unusable.

### D5. Resume

Facts that bind it. The shell machine cannot be saved, only re-walked with recorded replies (C4). LangGraph re-enters a tool N + 1 times for N interrupts and repeats effects before an interrupt (A3, EXECUTED). Approval before the call never re-enters (A4). A paused Python generator cannot be pickled (EXECUTED J), and keeping a thread parked would hold a call open, which the rulings forbid.

The rule, in three layers.

1. **The line is re-walked, and nothing with an effect is done twice.** `resume(run_id)` builds a new machine from the recorded line and config. Every request whose key is in the run record is answered from the record, with zero statements; a recorded effect is never issued again. Pipe-stage body reads are re-issued and checked against their recorded hash (D41). Builtins and expansions re-execute; they are pure functions of the line and the replies. The walk reaches the stopped request with the same key, because keys are a function of the line (shell decision 5).
2. **A completed tool stage is never entered again.** Its request key, fingerprint (tool name, manifest hash, arguments, stdin hash) and result (stdout, stderr, status) are recorded when it returns, and the re-walk serves them.
3. **A tool stopped inside its body is re-entered from its start, once per resume.** Its `interrupt()` calls return the recorded answers in order. Its vfs calls are keyed `(stage key, inner ordinal)`; a call whose fingerprint matches the record is served from it with zero statements; a call that differs is made fresh and marked with one `vfs.replay_diverged` record. Code the body runs outside vfs runs again. This is D42, and it is LangGraph's behaviour measured in A3.

Two additions make layer 3 rarer and safer.

- **Approval before the call is the default answer for a tool with effects.** `add_tool(fn, approve=True)`, or a policy rule on `call.op == "tool"`, stops the stage before the body is entered; the answer admits the call once; the body runs once. This is LangChain's `interrupt_on`, OpenAI's and ADK's approval shapes (B), and vfs's own policy interrupt (C1) applied to the tool door. With it, the rule "nothing runs twice" holds for the tool body as well.
- **`vfs.once(name, fn, *args)`** records the return value of one host-side effect in the run record, claim first, so a re-entered body is served the recorded value instead of repeating the effect. This is the pattern of LangGraph's functional `@task` (A5) and spec 177's claim. It is a later slice, not the first.

What the run must record, per run: the line, the config (cwd, env, `set -e` state, the program table with each tool's manifest hash), and the starting authority. Per request key: the fingerprint and the reply, for effects and expansion reads. Per tool stage: status (`claimed`, `stopped`, `done`), the interrupt ids it raised, the answers in order, its inner vfs calls by ordinal with fingerprint and result, and on completion its stdout, stderr and status. A tool whose manifest hash changed between the stop and the resume refuses the run `vfs.conflict`, because the code that asked is not the code that would answer.

Crashes. A tool stage is claimed (a row with status `claimed`) before the body is entered, as spec 177 claims a key. A resume that meets a `claimed` row with no recorded stop does not enter the tool: it stops the run with a `vfs.unavailable.in_doubt` interrupt naming the stage, and the host answers `done` (with the output to use) or `redo` (D46). Effects the body made outside vfs before the crash are unknowable to vfs; the interrupt says so in its reason.

Recommendation: the three layers, with approval before the call as the documented default for tools with effects, and `vfs.once` as the later opt-in. Refused, each with its reason:

| Alternative | Why refused |
|---|---|
| Never re-enter; require every interrupting tool to be split into ask-then-act | breaks every unmodified LangGraph tool that calls `interrupt()` mid-body, which the goal requires to work |
| Snapshot the tool's frame | CPython cannot save a running frame (EXECUTED J); a parked thread holds a call open, which the rulings forbid, and cannot survive a process |
| Record every side effect of the body | vfs sees only the effects that pass through vfs; the rest are invisible to it |
| Re-run the whole line from the top | the ruling of 2026-10-28 forbids it, and every earlier effect and question would repeat |

### D6. In a pipeline

Facts that bind it. A tool takes a whole arguments object, so its stdin binding needs the whole input (D2). D40: drain, then stop, per pipeline. The machine waits on an open request indefinitely and applies replies by key (C4).

The behaviour of `producer | tool_that_interrupts | consumer`.

- The tool stage reads its stdin to end-of-file before the tool is called; the bytes count against the machine's memory budget. So the producer runs to completion first, or to its own interrupt.
- The tool's stdout is written only when the tool returns. While it is stopped, the consumer receives neither data nor end-of-stream from it: `head` neither closes nor completes, and `wc` prints nothing.
- The stop leaves the run request open in the machine. The machine is never told 75. If it were, `convert x || echo failed` would run the fallback, which is wrong. INFERRED. The 75 (`EX_TEMPFAIL` of `sysexits.h`) appears only in the stopped result's `statuses`, for the host and the agent to read.
- Later statements (`;`, `&&`) are not run. Other pipelines of the same `&`-list drain to their own end or stop.
- The stopped result's `stdout` is what the line printed before the stop. The resumed result's `stdout` is the whole line's output, equal byte for byte to an uninterrupted run (H4 criterion 3); the result carries `stdout_offset`, the length already shown, so a host that streamed the first part prints only the rest.
- `xargs convert` with several operands: each `convert` is its own request key. Those that complete before a sibling stops are recorded and never re-entered. With `xargs -P 2`, two that stop together are reported together (one stop, two interrupts).

Recommendation: as above. Refused: replying 75 to the machine and letting the line continue, because it turns "waiting for a person" into "failed", and `||`, `set -e` and `$?` would act on an answer nobody gave.

### D7. Sync, async and threads

Facts that bind it. The kernel is async; the synchronous face runs a loop on its own thread and refuses a call from that thread (C4). LangChain runs a sync-only tool's `ainvoke` on an executor thread with the context copied (A1, EXECUTED S6). The machine object is `unsendable` (C4).

- The machine is stepped on the kernel's loop thread, by the async host loop, as today.
- An async tool body is awaited on the kernel loop and given `AsyncFs`. A LangChain tool is always called through `ainvoke`, so LangChain picks the thread for a sync-only tool.
- A sync tool body runs on a worker thread (`asyncio.to_thread`, which copies context variables) and is given `Fs`, a synchronous twin whose calls are submitted to the kernel loop with `run_coroutine_threadsafe`. The worker is not the loop thread, so the call cannot deadlock; if a body hands its `Fs` to code that runs on the loop thread, the facade's existing refusal answers it rather than hanging.
- The host loop answers a step's open requests concurrently (`gather`) rather than one at a time, so `xargs -P 2` runs two tools at once and two stops in one step are reported together. The replies are applied in key order, which the machine already does.
- The deadline: an async tool is cancelled; a sync tool's thread is abandoned and the stage is 124 (spec 170 §1). An abandoned thread that later calls `Fs` is refused, because its run has ended.

Recommendation: as above. Refused: running sync tool bodies on the loop thread, because one blocking body stalls every caller of the kernel, and its first `Fs` call deadlocks.

### D8. Safety

Facts that bind it. A host tool runs with the host's privileges (C2). Spec 170 accepts that an open node lets anyone call every host tool (C3).

What vfs gates.

- The call. Resolve (`list` on the entry, else 127), then `read` on `/.vfs/tools/<name>` (else 126), then the policy hook, which sees `call.op == "tool"`, the tool name and the parsed arguments, and may deny or interrupt before the body runs. Every refusal costs zero tool entries.
- The tool's vfs calls, through the injected handle, as the caller.
- The answer: only the file system holds `answer`; an agent cannot answer its own tool's interrupt.

What vfs cannot gate: anything the body does directly. Network, the host's disk, subprocesses, a database client, a closure over the host's own `fs` or the system authority. `type <name>` says "runs on the host, with the host's authority". The payload of a tool interrupt carries values the agent chose as arguments, so it is rendered as data, never placed in a prompt.

How a tool is listed and permissioned: by posture and grants on `/.vfs/tools` and its entries, as spec 170 §5.1 says. A change is proposed here: the first `add_tool` sets `/.vfs/tools` to posture `list` unless the host passes `open=True`, so a fresh node does not let anonymous callers run host code with host privileges. This changes spec 170's accepted default, so it is a choice left open, not taken here.

Recommendation: gate the call, the tool's vfs calls and the answer; say plainly what is not gated; default host tools to `list`. Refused: sandboxing tool bodies in-process, because CPython has no in-process sandbox, and the guests (T5a, T5b) are vfs's answer for code that must run under the caller's rights alone.

### D9. Build order

The smallest slice that gives "my LangChain tool is a program in `fs.cli`, and it can interrupt":

1. **The tool registry and the door, before the shell lands.** `@fs.tool`, `add_tool` for LangChain by shape, the schema-to-argv parser and `--help`, the result and exit mapping, injection of the caller's handle, and `fs.call_tool(name, argv)` as the door. Depends on nothing but `dev`. Testable alone: the flag table rows, zero tool entries on a usage error, `ToolException` → 1.
2. **`vfs.interrupt` on a bare tool call.** A bare tool call is a run of one step, as a bare verb is (H3): it stops, `answer(id, value=)` records, the same call made again re-enters with the answer. Depends on the interrupt ledger this branch builds and `answer(value=)`. The LangGraph shim adapter lands here, behind the extra, with the S1 conformance test.
3. **The shell's program seam.** In the shell work, as specified below. Depends on the shell reaching `dev`.
4. **A tool as a program in `fs.cli`, with no interrupt.** Wiring 1 into 3; `xargs` as a library program over the seam.
5. **A stopped line and `resume(run_id)`.** The run record (line, config, replies by key, tool stage rows), the re-walk, approval before the call, and the pipeline rules of D6. Depends on 2 to 4 and on the root binding's storage for the run tables (H4's slice for tools).
6. Later: `vfs.once`, MCP elicitation and `input_required` mapped to the same interrupt (H5 criterion 4), dotted flags if a census asks.

Steps 1 and 2 can be built now. Step 5 is the first that needs the durable run.

What the shell's program seam must provide, precisely.

- `ProgramKind::Host`: a name in `Config.programs` the machine does not implement and asks the host to run. A host may list a name as `Library` or `Host`, never both.
- A command word containing `/` is offered to the host as a `Host` program instead of the fixed 127, when the host has opted in (`Config.host_paths`), so `/.vfs/tools/convert` runs.
- `Request::Run { argv, cwd, env, stdin: Vec<u8> }`, keyed like any request, with the stage's stdin read to end-of-file by the machine and charged to its memory budget. `Reply::Exited { status, stdout, stderr }`. The machine writes `stdout` and `stderr` to the stage's descriptors when the reply arrives.
- A streaming form for later programs (shell spec decision 4: "start a program and feed or pull its chunks"): `Request::Start`, then `Pull` and `Feed` on its handle, each keyed. Tools do not need it; it must not change the whole-input form's keys.
- An open `Run` request may stay open across any number of steps while other requests proceed, and the machine never times it out. The host stops a line by not stepping it again.
- Keys of a re-walk equal the first walk's for the same replies, including through `xargs` children and `-P` (shell decision 5, now covering `Run`).
- `xargs` in the library programs, issuing one `Run` per batch of operands, with `-P` opening several at once.

## A proposed host-facing API, on one screen

```python
from typing import Annotated
from langchain_core.tools import tool, InjectedToolArg
from vfs import VirtualFileSystem, Fs, ToolError, interrupt

fs = VirtualFileSystem(policy=policy)

@fs.tool                                       # a vfs-native tool
def convert(path: str, to: str = "pdf", *, fs: Fs) -> str:
    """Convert a document."""
    if not interrupt({"question": f"Convert {path} to {to}?"}, response_schema=bool):
        raise ToolError("declined")
    fs.write(path=f"{path}.{to}", content=render(fs.read(path).content, to))
    return f"{path}.{to}"

@tool                                          # an unmodified LangChain tool
def publish(path: str, fs: Annotated[Fs, InjectedToolArg]) -> str:
    """Publish a converted file."""
    ...
fs.add_tool(publish, approve=True)             # asked before the body runs

agent = fs.open_session(agent_authority)
result = agent.cli("ls /reports/*.md | xargs convert --to pdf | xargs publish")
while result.interrupted:
    for it in result.interrupts:               # it.kind, it.program, it.payload, it.response_schema
        fs.answer(it.id, value=ask_a_person(it), authority=approver)
    result = agent.resume(result.run_id)
print(result.stdout)
```

## Build order

1. Tool registry, LangChain adapter by `tool_call_schema`, schema-to-argv, result mapping, handle injection, `fs.call_tool`. Now, on `dev`.
2. `vfs.interrupt` and `answer(value=)` on a bare tool call; the LangGraph shim behind the extra with its conformance test. With the interrupt ledger.
3. The shell's program seam: `ProgramKind::Host`, `Request::Run`, path-named commands, `xargs`. In the shell work.
4. Tools as programs in `fs.cli`. After 1 and 3.
5. The run record, `resume(run_id)` re-walk, tool stage rows, approval before the call, pipeline rules. After 2 to 4, in the root binding's storage.
6. `vfs.once`, MCP elicitation and `input_required`, dotted flags. Later.

## What was not checked

- The LangGraph shim was run against one version (1.2.24). Its stability across earlier and later versions is not known.
- No vfs code was written or run; every vfs behaviour above is from reading documents and the shell branch, or inferred.
- The wasm build of the shell machine was not read. Whether its module memory could be snapshotted, which would let a stopped line skip the re-walk, was not studied.
- The cost of a re-walk at the reference deployment's scale (a line with thousands of recorded requests resumed) was not measured.
- The cost of the scratchpad shim and of a ToolCall-shaped invocation per tool call was not measured.
- The LangGraph docs site was read through a fetch tool that summarises; its quotations were checked against the source docstrings where the source says the same thing (`types.py:926-933`), and not otherwise.
- Section B rests on two delegated studies. Only the claims named at the head of section B were re-read for this memo; the rest carry the studies' citations unverified here.
- The Claude Agent SDK's `defer` resume runs in its closed CLI, so how it resumes was not visible.
- No spike was run against openai-agents, ADK, MCP, fastmcp or any shell; their behaviour is READ, not EXECUTED.

## One line

A host tool is a program the shell asks the host to run, LangChain tools mount by their `tool_call_schema`, a tool interrupts with LangGraph's own index rule, and a stopped line is re-walked from its record so no effect repeats, while a tool's own body is re-entered unless it was approved before it started.
