# 04 — Code as the action space: the research lineage, the frameworks, and the measured evidence for and against it

The question as this study received it: the older and research lineage of "code as the action space", and the measured evidence for and against it. Study at least the CodeAct paper and repository (M3ToolEval, the success-rate and turn-count deltas, which models benefit and which do not); Hugging Face `smolagents` CodeAgent (how tools are rendered into the prompt as Python signatures, the local AST executor, the remote executors, how results flow, `final_answer`, the published benchmark claims); pydantic `monty` and pydantic-ai's code mode (the Python subset, what it refuses, how host functions are exposed, resource limits); independent measurements of code mode against direct tool calling published from 2025-09 onward, with every number tied to its workload, model and measurer, and the evidence of where code actions are worse (small models, error recovery, security, latency); and shell as the action language (SWE-agent's ACI findings, terminal-bench, Vercel's bash post, mini-swe-agent's bash-only result), because the vfs code mode language is a bash-shaped shell, not Python or TypeScript. In the closing section, weigh shell against Python or TypeScript as the vfs code-mode language on the evidence, and say what the shell would need, or what guest language vfs already plans (spec 172), to match general-language code mode.

## Sources

Clones, each refreshed or cloned on 2026-11-23 and recorded in `refresh.log` and `licenses.log`:

| Clone | Upstream | Commit | Commit date | Licence |
|---|---|---|---|---|
| `/home/user/code-act` | github.com/xingyaoww/code-act | `d607f56c9cfe` | 2024-05-24 | MIT (`LICENSE`) |
| `/home/user/smolagents` | github.com/huggingface/smolagents | `5107d3aec21d` (version `1.27.0.dev0`) | 2026-11-23 | Apache-2.0 (`LICENSE`) |
| `/home/user/monty` | github.com/pydantic/monty | `cfa9cec8af83` | 2026-11-23 | MIT (`LICENSE`) |
| `/home/user/pydantic-ai` | github.com/pydantic/pydantic-ai (shallow) | `541bd91c2da3` | 2026-11-23 | MIT (`LICENSE`) |
| `/home/user/mini-swe-agent` | github.com/SWE-agent/mini-swe-agent (shallow) | `04d809ceab9d` | 2026-09-03 | MIT (`LICENSE.md`) |

Packages installed for the experiment, in a scratch virtual environment outside the repository: `pydantic-monty 1.6.0` and `smolagents 1.26.0` from PyPI, CPython 3.13.18. The script and its output are under `studies/experiments/04-code-as-action/`.

Web pages fetched and read in full on 2026-11-23:

- Anthropic, "Introducing advanced tool use on the Claude Developer Platform" (2025-11-24): https://www.anthropic.com/engineering/advanced-tool-use
- Anthropic, "Code execution with MCP" (2025-11-04): https://www.anthropic.com/engineering/code-execution-with-mcp
- FastMCP issue #4902, "Benchmark direct tools vs Tool Search vs Code Mode" (opened 2026-08-25, comments to 2026-11-22): https://github.com/PrefectHQ/fastmcp/issues/4902
- Maxim / Bifrost, MCP code-mode benchmark report: https://github.com/maximhq/bifrost-benchmarking/blob/main/mcp-code-mode-benchmark/benchmark_report.md
- Microsoft Research publication page, "The Devil Is in the Interface" (2026-08): https://www.microsoft.com/en-us/research/publication/the-devil-is-in-the-interface-evaluating-how-tool-architecture-shapes-coding-agent-behavior/
- SWE-agent documentation, "Agent Computer Interface": https://raw.githubusercontent.com/SWE-agent/SWE-agent/main/docs/background/aci.md

Pages this session could not fetch. The session's network refused `arxiv.org`, `huggingface.co`, `vercel.com`, `labs.scale.com`, `research.aimultiple.com`, `pith.science` and `object.cloud.sdsc.edu`. For these, the figures below come from web-search result summaries of the named URL, read 2026-11-23, and each is labelled **READ (search summary)**. Such a figure has not been checked against the primary page; a memo that leans on one should fetch the page first.

- CodeAct paper: https://arxiv.org/abs/2402.01030 (the per-model M3ToolEval table was recovered from the repository instead; see finding 2)
- SWE-agent paper: https://arxiv.org/abs/2405.15793
- "The Bitter Lesson of Tool Calling": https://arxiv.org/abs/2608.06370
- "From Tool Orchestration to Code Execution: A Study of MCP Design Choices": https://arxiv.org/abs/2602.15945
- "Is Bash All You Need? An Empirical Study of Tool Interfaces for Enterprise Digital Worker Agents": https://arxiv.org/pdf/2609.11999
- "Terminal Agents Suffice for Enterprise Automation": https://arxiv.org/abs/2604.00073
- "The Scaffolding Matters More Than the Interface": https://arxiv.org/pdf/2608.08654
- "Matched Capabilities, Different Behaviors": https://arxiv.org/pdf/2610.34298
- CaMeL, "Defeating Prompt Injections by Design": https://arxiv.org/abs/2503.18813
- Hugging Face, "Open-source DeepResearch": https://huggingface.co/blog/open-deep-research
- Vercel, "We removed 80% of our agent's tools" (2025-12-22): https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools
- Scale Labs, "MCP vs CLI" (2026-07-08): https://labs.scale.com/blog/mcp-vs-cli
- AIMultiple, "Code execution with MCP": https://research.aimultiple.com/code-execution-with-mcp
- Check Point Research, "When agentic glue melts" (2026-08-07): https://research.checkpoint.com/2026/when-agentic-glue-melts/
- Terminal-Bench, Terminus: https://www.tbench.ai/terminus
- SWE-bench bash-only leaderboard: https://www.swebench.com/bash-only.html; Vals.ai archived SWE-bench pages
- smolagents release notes on releases.sh (WasmExecutor removal)

vfs files read: `README.md`; `context/specifications/active/167-the-shell-pipeline-core/spec.md` (status, intent, decisions, scope); `168-text-program-kernels/spec.md` (the `jq` lines); `170-tools-and-mcp-servers-as-views/spec.md` and `171-the-mcp-adapter-and-the-cli-tool/spec.md` (intents); `172-the-wasi-python-runtime/spec.md` (opening), all at `0ed462f`.

## Findings

### A. The research lineage: CodeAct

**1. READ — M3ToolEval is a small, composition-heavy benchmark, and its JSON baseline is not native function calling.** The harness is `scripts/eval/m3tooleval/` in `code-act @ d607f56`. It has five domains: `dna_sequencer`, `message_decoder`, `trade_calculator`, `travel_itinerary_planning` and `web_browsing`. Each defines six tools as small Python functions, for example `count_nucleotides` and `transcribe_dna_to_mrna` (`tasks/impl/dna_sequencer.py:43-78`). The notebook asserts 82 tasks across the five (`m3tooleval_analysis.ipynb`, the `n_tasks == 82` query). Every mode gets the same prompt listing each tool's description and Python signature (`tasks/base.py:57-61`). The modes differ only in the instruction. Text and JSON say "You can only invoke one tool at a time" (`base.py:68,75`). Code says "You may use for-loops, if-statements, and other Python constructs when necessary" (`base.py:76-81`). The JSON action is a `{"tool": ..., "args": [...]}` object written inside free text between `Action:` and `End Action` and parsed with `json.loads` (`base.py:69-75,200-208`). It is not a provider's native tool-calling API. Runs use temperature 0, 512 output tokens per turn, and a 10-turn limit (`main.py:22`, `main.py:80-88`). Non-code results are truncated to 2,000 characters (`base.py:226-228`).

**2. READ — The CodeAct per-model table: the gain is large for strong models and nil or negative for weak ones.** The table below is the notebook's stored LaTeX output (`scripts/eval/m3tooleval/m3tooleval_analysis.ipynb`, cell 4 @ `d607f56`). It is the paper's M3ToolEval table, recovered from the repository because arxiv.org was unreachable. The columns are success % for code, JSON and text, then average turns for each.

| Model | Code % | JSON % | Text % | Code turns | JSON turns | Text turns |
|---|---|---|---|---|---|---|
| gpt-4-1106-preview | **74.4** | 52.4 | 53.7 | **5.5** | 7.6 | 7.7 |
| gpt-4-0613 | **67.1** | 56.1 | 45.1 | **6.6** | 7.6 | 8.0 |
| claude-2 | **54.9** | 39.0 | 29.3 | **7.2** | 8.3 | 8.5 |
| gpt-3.5-turbo-0613 | **51.2** | 26.8 | 20.7 | **7.0** | 8.8 | 9.2 |
| gpt-3.5-turbo-1106 | **29.3** | 15.9 | 14.6 | **8.4** | 9.0 | 9.0 |
| gemini-pro | **22.0** | 19.5 | 11.0 | **8.8** | 9.1 | 9.5 |
| text-davinci-003 | **20.7** | 18.3 | 7.3 | 9.2 | **9.0** | 9.6 |
| claude-instant-1 | 20.7 | **31.7** | 24.4 | 8.8 | **8.6** | 8.9 |
| lemur-70b-chat-v1 | 13.4 | **15.9** | 12.2 | **9.1** | 9.3 | 9.4 |
| Llama-2-70b-chat-hf | **11.0** | 3.7 | 3.7 | **9.1** | 9.8 | 9.8 |
| mint-agent | 9.8 | **13.4** | 3.7 | **9.4** | **9.4** | 9.8 |
| text-davinci-002 | 4.9 | 4.9 | **8.5** | 9.7 | 9.8 | **9.6** |
| CodeLlama-7b-Instruct-hf | **4.9** | 2.4 | 2.4 | **9.7** | 9.9 | 9.9 |
| CodeLlama-13b-Instruct-hf | 4.9 | 4.9 | 4.9 | 9.8 | 9.8 | **9.7** |
| CodeLlama-34b-Instruct-hf | **2.4** | 0.0 | 0.0 | **9.9** | 10.0 | 10.0 |
| Mistral-7B-Instruct-v0.1 | 0.0 | **3.7** | 1.2 | 10.0 | **9.8** | 9.9 |
| Llama-2-7b-chat-hf | 0.0 | 1.2 | **2.4** | **8.9** | 9.5 | 9.6 |
| Llama-2-13b-chat-hf | 0.0 | 0.0 | 0.0 | **9.7** | 10.0 | 10.0 |

The notebook's own tally: code has the highest success for 12 models, JSON for 4 and text for 2; code has the fewest turns for 13, JSON for 3 and text for 2. The paper's headline, "up to 20% higher success" and "up to 30% fewer actions", is the top rows. gpt-3.5-turbo-0613 gains 24.4 points over JSON; gpt-4-1106-preview gains 22.0 points and takes 2.1 fewer turns (5.5 against 7.6, 28% fewer). Below about 20% success the format barely matters, and several weak models do worse with code: Mistral-7B-Instruct scores 0.0 with code against 3.7 with JSON, claude-instant-1 20.7 against 31.7. Every model at or below 13.4% sits within about one turn of the 10-turn limit in every mode; those runs mostly ran out of turns.

**3. READ (search summary) — On single atomic calls, code is not reliably better.** The paper's API-Bank experiment isolates format familiarity from control and data flow by asking for one tool call at a time. Per a summary of the paper (arxiv.org/abs/2402.01030, via liner.com), code was the best format for 4 of 8 open models and 4 of 9 closed models, and JSON was best for 5 of 9 closed models, which the authors attribute to vendor fine-tuning on JSON calls. INFERRED from findings 2 and 3: the measured CodeAct advantage comes from composition (several calls, loops and arithmetic in one action), not from code being an easier syntax for one call.

**4. READ — CodeAct's design premises are the ones every later system restates.** The repository's comparison table (`figures/codeact-comparison-table.png`) claims four advantages for code: abundant pre-training data; control and data flow ("looping, composition of multiple tools") without inventing tools to mimic an `if`; existing software packages usable as tools; and tracebacks as automated feedback. The reference runtime is a Jupyter kernel in a Docker container per chat session (`README.md`, "Start your Code Execution Engine"). The authors also fine-tuned CodeActAgent-Mistral-7B on 7,000 multi-turn CodeAct trajectories (`README.md`), which is evidence that the weak-model gap in finding 2 is a training gap and can be closed by training.

### B. The framework lineage: smolagents CodeAgent

**5. READ — Tools are rendered as Python function stubs, all of them up front.** `Tool.to_code_prompt` (`src/smolagents/tools.py:258-287 @ 5107d3a`) writes each tool as `def name(arg: type, ...) -> type:` with the description, an `Args:` block from the input schema, and, when the tool declares an output schema, a `Returns:` block holding the JSON schema. The return type then shows as `dict`. The system prompt (`src/smolagents/prompts/code_agent.yaml:1-11,131-136`) lists every tool in one code block, with no discovery step; only managed sub-agents are added the same way (`:138-153`). Two of the prompt's rules state the role of output schemas (`code_agent.yaml:161-162`). Without a schema the model is told not to chain dependent calls in one block "as their output format is unpredictable" and to `print()` and wait for the next step. With a schema "You can confidently chain multiple tool calls". The stub adds a note "for smaller models (e.g. Mistral Small, Gemma 3, etc.)" telling them to index the structured output directly (`tools.py:267-269`).

**6. READ — The local executor is an AST interpreter with allow-lists and counters, and its authors say it is not a security boundary.** `LocalPythonExecutor` (`src/smolagents/local_python_executor.py:1716-1796`) walks the AST and refuses any node type it does not implement (`:1596-1597`). Its defaults (`:57-61`) are an output cap of 50,000 characters, 10,000,000 elementary operations, 1,000,000 `while` iterations and 30 seconds of wall time. Only `__init__`, `__str__` and `__repr__` are allowed as dunder methods. Imports are refused unless listed. The base list is `collections`, `datetime`, `itertools`, `math`, `queue`, `random`, `re`, `stat`, `statistics`, `time` and `unicodedata` (`utils.py:49-61`). A denylist blocks `os`, `subprocess`, `socket`, `sys`, `io`, `pathlib`, `shutil` and others, along with `eval`, `exec`, `compile` and `__import__` (`:130-153`). The timeout runs the code in a thread and "cannot be forcefully killed", so a timed-out snippet keeps running in the background (`:285-318`). The tutorial says it plainly: "no local python sandbox can ever be completely secure" (`docs/source/en/tutorials/secure_code_execution.md:104-108`). It gives the example of an allowed package such as Pillow being used to fill a disk.

**7. EXECUTED — smolagents' local executor lets one program make 200,000 tool calls.** A loop calling a registered `@tool` on each iteration ran to completion at 10, 10,000 and 200,000 iterations, with 200,000 host calls counted (`experiments/04-code-as-action/host_call_budgets.out`). The only bound on the number of tool calls is the operation counter.

**8. READ — Remote executors ship the tools into the sandbox, credentials included.** `RemotePythonExecutor.send_tools` (`src/smolagents/remote_executors.py:95-113`) installs each tool's declared pip requirements in the sandbox, then sends the tool's source (`get_tools_definition_code`, `tools.py:1335`) to run there. The executors are E2B, Docker, Modal and Blaxel (`remote_executors.py:335,551,726,859`; `agents.py:1518`). So a tool runs inside the sandbox with whatever credentials it needs. The tutorial gives two options (`secure_code_execution.md:113-121`). Sandboxing only the snippets "doesn't support multi-agents and still requires passing state data". Sandboxing the whole agent "may require passing sensitive credentials (like API keys) to the sandbox environment". Variables cross the boundary by JSON serialization, with pickle only by opt-in and flagged as unsafe (`remote_executors.py:56-66,115-130`). The Pyodide-in-Deno `WasmExecutor` is gone. EXECUTED: no class by that name in the installed 1.26.0 or on `main`. READ (search summary of releases.sh): it was added in v1.20.0 and removed in v1.26.0 (2026-05-29, "Remove remote WasmExecutor", #2321), after v1.25.0 patched a remote-executor vulnerability.

**9. READ — Results flow through `print()`, and `final_answer` is an exception.** The model is told to `print()` whatever it needs. Printed text comes back as the step's `Observation`, and variables and imports persist between steps (`code_agent.yaml:7-10,167`). `final_answer(x)` raises `FinalAnswerException`. It subclasses `BaseException` "to prevent being caught by generic `except Exception` clauses in agent-generated code" (`local_python_executor.py:1600-1608`). Remote executors patch the tool into the same exception (`remote_executors.py:96-97`).

**10. READ — smolagents' published claims rest on CodeAct and on its own unpublished-in-repo benchmark.** The README cites "30% fewer steps" by linking the CodeAct paper (`README.md:248`), so that figure is finding 2, not a new measurement. The repository's benchmark harness runs three arms on a mixed question set (`examples/smolagents_benchmark/run.py:126-145`), each with `max_steps=10`. `code` is a CodeAgent with search and visit-page tools. `tool-calling` is a ToolCallingAgent with the same tools plus a `PythonInterpreterTool`. `vanilla` is the bare model. The scoring notebook stores no outputs (`score.ipynb`). READ (search summary of huggingface.co/blog/open-deep-research): the Open Deep Research post reported 55.15% on the GAIA validation set with a CodeAgent. Secondary reports say a JSON-action agent scored about 33%; their wording conflicts on whether that was the validation or the test set. All of these are the vendor's own figures.

### C. The sandbox built for code mode: Monty and pydantic-ai CodeMode

**11. READ — Monty is a language-level sandbox with no ambient authority.** In Monty's words: "sandboxed code cannot express an operation that touches the host, because the interpreter implements no such operation" (`docs/security.md:12-28 @ cfa9cec`). The guest reaches the host three ways (`security.md`, "The three host-access mechanisms").

- Host functions: an unknown name resolves against `external_lookup`. Execution suspends, the host function runs "with your process's full authority", and execution resumes with the result. Monty "cannot guarantee that what you handed it is safe".
- Host objects: `ClassInstance` and `ClassType` wrappers expose attributes and methods through allow-lists that default to nothing.
- The filesystem: per-feed `MountDir` mounts of host directories, or an `os` callback that answers filesystem calls in host code (`docs/filesystem.md:1-12`).

**12. READ — What Monty refuses: no generators, no metaclasses, no third-party packages.** It rejects these at parse time (`docs/limitations/index.md`):

- metaclasses;
- decorators on methods, so no `@property`, `@classmethod` or `@staticmethod`;
- `yield` (generator expressions are materialized to lists);
- `del`, `except*`, PEP 695 `type`, `async with`, `async for` and t-strings.

Other gaps: no user-defined exception classes, no function attributes, and no `compile`, `globals` or `__import__`. `eval` and `exec` exist, but only on source text (`docs/limitations/eval_exec.md`). There are no third-party packages, no `sys.path` and no site-packages. The standard library is a fixed set of about 30 modules, including `json`, `re`, `csv`, `datetime`, `collections`, `itertools` and `asyncio` (`docs/limitations/modules.md`). Monty bundles the `ty` type checker, which can check a snippet against stubs before it runs (`docs/type-checking.md:1-8`).

**13. READ — Monty's limits are per session, and two of them cannot be turned off.** `docs/resource-limits.md:52-62` lists `max_memory`, `max_feed_duration_secs`, `max_turn_duration_secs`, `max_recursion_depth` (default 1,000), `gc_interval`, `max_suspensions` (default 1,000) and `max_total_sleep_secs`. A suspension is any host round trip: an external call, an `os` callback, a name lookup or a future resolution. `max_recursion_depth` and `max_suspensions` "cannot be disabled". Allocations whose size is predictable are checked before they happen (`resource-limits.md`, "Memory"). Execution can pause at a suspension and be serialized to bytes, then resumed in another process (`docs/snapshots.md`). Snapshots are not authenticated, so only trusted bytes may be restored. The vendor's start-latency table (`docs/index.md:36-41`), not independently measured, covers a new sandbox plus ten REPL commands:

| Runtime | Time |
|---|---|
| Monty, pool already open | 1.2 ms |
| WASI / wasmtime | 200 ms |
| local Docker | 900 ms |
| a sandboxing service | 1,900 ms |
| Pyodide in Deno | 2,700 ms |

**14. EXECUTED — Monty stops a program at its 1,001st host call, and has no ambient filesystem.** With the default limits, a loop calling one host function per iteration completed at 10, 500, 999 and 1,000 iterations. At 1,001, 2,000 and 10,000 iterations it was refused after exactly 1,000 host calls: `RuntimeError: suspension limit 1000 exceeded`. `import os; os.listdir('/')` with nothing configured raised `PermissionError: Permission denied: '/'` (`experiments/04-code-as-action/host_call_budgets.out`). INFERRED: a code-mode program that loops over a 10,000-file batch and calls a tool per file does not fit Monty's default budget. The same program in smolagents (finding 7) is not bounded by call count at all.

**15. READ — pydantic-ai's CodeMode folds tools into one `run_code` tool, typed and type-checked.** The source is `src/pydantic_ai_harness/pydantic_ai_harness/code_mode/README.md @ 541bd91`. Selected tools leave the model's tool list and become `async def` functions inside one `run_code` tool, which runs the snippet in Monty (`README.md:28-42,116-140`).

- **Catalog:** rendered from each tool's JSON schema as `TypedDict` definitions plus function signatures (`_toolset.py:1682-1705`). The same stubs drive `ty` before the first snippet runs (`_toolset.py:1708-1721`).
- **Missing return schema:** the stub shows `-> Any`, and CodeMode warns that "the model must guess the result's shape" (`README.md:984-988`).
- **Return value:** the snippet's last expression, with printed text alongside (`README.md:211-235`).
- **Defaults:** 30 seconds of execution time, not counting time waiting on tools; a 256 MiB heap; and `max_tool_calls` of 100 nested calls per `run_code` (`README.md:237-262`).
- **Partial failure:** when the budget is exceeded or a snippet fails, the retry lists every nested call started and whether it returned, "did not finish (a tool can apply a change before it stops)", or was denied. Replaying completed calls "repeats side effects", and "Nothing restarts or replays automatically".

**16. READ — pydantic-ai keeps approval, shell and code tools out of code mode.** Three kinds of tool stay native, not callable from code, under the default selector (`README.md:132-140,970-983`):

- tools marked `requires_approval=True`, and external tools;
- `Shell`'s `run_command` and `start_command`, "so the model never quotes shell inside Python";
- any other code-execution tool.

On discovery, tools marked `defer_loading` stay out of `run_code` until Tool Search finds them. The catalog then grows by appending to the instructions, so the cached prompt prefix survives (`README.md:142-175`). Two more features overlap tool latency with generation (`README.md:353-412`): an `eager` mode that runs each statement as it streams, and a `speculate` mode that starts side-effect-free calls whose arguments are literals before the snippet is finished. REPL state persists across `run_code` calls in a run, and can be stored across runs as Monty's opaque dump (`README.md:312-352`).

### D. Independent and vendor measurements since 2025-09

**17. The measurements, each with its workload, model and measurer.** The numbers differ in kind (input tokens, total tokens, task success) and so cannot be pooled.

| Who measured | Workload, model | Result | Label |
|---|---|---|---|
| Anthropic (vendor), 2025-11-24 | "complex research tasks", internal evals; Claude, programmatic tool calling (PTC) vs direct calls | average tokens 43,588 → 27,297 (−37%); internal knowledge retrieval 25.6% → 28.5%; "GIA benchmarks" 46.5% → 51.2% | READ (anthropic.com) |
| Anthropic (vendor), 2025-11-04 | one worked example: a Drive transcript copied into Salesforce | 150,000 → 2,000 tokens (−98.7%); no method given, so illustrative | READ (anthropic.com) |
| Maxim / Bifrost (vendor of a gateway), 2026 | 64–65 queries per round over 96 / 251 / 508 MCP tools; claude-sonnet-4-6; code mode in **Starlark** | input tokens −58.2% / −84.5% / −92.8%; output tokens −3.7% / **+35.3%** / **+72.2%**; wall clock −26.8% / −6.8% / −17.1%; pass rate 100/100, 98.5/100, 100/100; one R3 query (14.3M → 245k tokens) drives much of the R3 reduction; simple R1 queries about 7% slower | READ (github.com) |
| AIMultiple (independent), 2026 | Bright Data MCP server; model not stated in the snippets | input tokens 771K → 165K (−78.5%); total −77.4%; output tokens 2.2× higher; latency 9.66 s → 10.37 s; success 100% both | READ (search summary) |
| FastMCP issue #4902 (community), 2026-08-25 | 12 tasks at four call depths; model not named; FunctionAgent and ReAct agents | FunctionAgent input tokens about −68%; latency 12.8 s → 16.9 s (**+32%**); tool-call accuracy 0.75 → 0.76; under ReAct, **7 of 12 code-mode tasks scored 0** on tool accuracy; the author: "I don't think those numbers generalize" | READ (github.com) |
| FastMCP #4902 comment (community), 2026-11-21 | scripted policy, no model, so exposure only; 16 tasks | mean input tokens, direct vs code mode: 4.0k vs 5.3k at 10 tools, 26.8k vs 11.0k at 100, 128k vs 35.4k at 500; code mode breaks even near 10–20 tools depending on depth | READ (github.com) |
| Patel, Sen, Lumer, Subbiah, "The Bitter Lesson of Tool Calling" (arXiv 2608.06370), 2026-08 | BFCL v4, 14 models over 20 months of releases; typed Python stubs | PTC matches or beats native JSON on 11 of 14; the three that do not are older GPT models; under fan-out PTC is at least JSON on 13 of 14; under context flooding JSON drops about 2.3% while PTC holds; PTC uses 1.5× the input tokens on the chaining ablation; BFCL stubs echo their arguments; ablations have n = 31–52 per condition | READ (search summary) |
| Felendler et al., Ben-Gurion University (arXiv 2602.15945), 2026-02 | MCP-Bench over 10 servers; code-execution MCP (CE-MCP) vs tool calling | CE-MCP "significantly reduces token usage and execution latency"; slightly lower task fulfilment on a three-server subset; more latency outliers during dynamic tool discovery; 16 attack classes (finding 20) | READ (search summary) |
| Xu et al., Purdue / Microsoft Research / U. Chicago, "The Devil Is in the Interface" (arXiv 2608.11386), 2026-08 | repository-level issue fixing; six tool architectures; three actors; 11,700 trajectories | against a **bash-only** agent, "Python CodeAct-style interfaces achieve similar task performance with **41.6% fewer steps and 56.3% lower token usage**"; structured low-level interfaces improve consistency across repeated attempts "by up to 4.7×"; natural-language search raises access to relevant files by more than 11% | READ (microsoft.com abstract) |
| "Is Bash All You Need?" (arXiv 2609.11999), 2026-09 | The Agent Company and APEX-Agents; five interfaces: typed tools, typed tools + bash, bash, bash + synthesized tools, PTC over a fixed typed catalog | **bash alone** +21.8 to +24.5 points on The Agent Company and +4.8 to +7.4 on APEX-Agents, with 19–72% fewer total tokens; adding typed tools or tool synthesis to bash showed no gain; PTC used fewer tokens than typed calls at similar quality and "generally trailed bash alone"; recommendation: bash where execution can be isolated, PTC where compliance requires a fixed catalog | READ (search summary) |
| Bechard et al., ServiceNow / Mila (arXiv 2604.00073), 2026-03 | ServiceNow, GitLab, ERPNext; web agents vs MCP tool agents vs a terminal agent calling APIs | the terminal agent beats MCP agents and matches web agents at much lower cost; persistent filesystem memory and skills help | READ (search summary) |
| Scale Labs, 2026-07-08 | 50 long-horizon tasks (50–100 tool calls each) in two enterprise environments; MCP vs CLI on the same backends | no default winner; CLI helps weaker models on retrieval-heavy tasks and is neutral or worse on targeted ones; with GPT-5.4 reasoning on, the gap "collapses to almost zero"; hybrid routing beat both | READ (search summary) |
| "The Scaffolding Matters More Than the Interface" (arXiv 2608.08654) | one software task, seven scaffolds, five models | 13 paired MCP-to-CLI cost ratios span 0.43× to 29×; one local 27B model varied 139× in cost across scaffolds | READ (search summary) |
| Shi, Pang, Li, "Matched Capabilities, Different Behaviors" (arXiv 2610.34298) | MCP and CLI rendered from one action contract; six models; three environments | interface changes action selection, failure paths and recovery; a secondary write-up reports divergence in 94.3% of 2,004 paired episodes | READ (search summary) |

INFERRED: three results hold across the independent and vendor numbers.

- The input-token saving of code mode is robust once the catalog is large. It does not exist at about 10 tools, where code mode costs more.
- Output tokens rise, by up to 2.2×, because the model writes the program.
- Task success is flat or modestly better for frontier models. It is worse in one reported agent loop (ReAct, 7 of 12 at zero) and for older models.

### E. Where code actions are worse

**18. Weak and older models.** READ: in the CodeAct table (finding 2), models under about 20% success gain nothing from code, and Mistral-7B-Instruct, claude-instant-1, lemur-70b and mint-agent do better with JSON. READ (search summary of 2608.06370): the three models for which PTC does not match JSON are older GPT generations, and "viability divides along model generation lines". READ: smolagents carries a special note in every structured-output stub for "smaller models" (`tools.py:267-269`). READ (search summary of smolagents documentation and the Hugging Face agents course): the guidance is that weaker models often do better with the JSON `ToolCallingAgent`; no controlled small-model study was found.

**19. Error recovery and side effects.** In a direct tool call, one failure is one failed call the model sees at once. In a program, a failure lands mid-program, after some calls have already run.

- READ (FastMCP #4902): the ReAct agent's collapse to zero tool accuracy on 7 of 12 tasks.
- READ: pydantic-ai documents what happens when a snippet fails part-way (`README.md:256-262,353-401`). A tool "can apply a change before it stops". Replaying "repeats side effects". A timeout resets the REPL and loses its variables. Eager execution's side effects "can't be undone".
- READ: smolagents' thread timeout leaves a timed-out snippet running in the background (finding 6).
- READ (Bifrost report): the one failure with code mode off was a model retrying a malformed call 60 times. That failure class belongs to direct calling, not to code.

**20. Security: code mode moves prompt injection from text into a program.**

- READ (search summary of 2602.15945): code execution moves adversarial influence "into model-generated code and runtime feedback loops". The paper names 16 attack classes in five execution phases, among them "exception-mediated code injection" and "unsafe capability synthesis". Its mitigations are containerized sandboxing, code validation before execution, and semantic gating after execution.
- READ (search summary of research.checkpoint.com, 2026-08-07): Check Point found five memory-corruption bugs in workerd's native glue. One chain started from a single prompt injection, steered the model to write attacker-controlled TypeScript, and escaped a Code Mode sandbox through a use-after-free in `node:zlib`. Because workerd also isolates Workers tenants, the bugs carried cross-tenant risk; Cloudflare patched them.
- READ: the smolagents tutorial lists prompt injection from browsed pages as a route to malicious code (`secure_code_execution.md:32-38`). Monty's docs warn that a host function taking a path or URL is "an unconstrained filesystem or network primitive that you wrote" (`security.md`, "Host functions").
- READ (search summary of 2503.18813): CaMeL points the other way. It runs the plan as code in a custom Python interpreter that tracks the provenance of each value and enforces policies on every tool call. It solved 77% of AgentDojo tasks with provable security, against 84% undefended (67% in v1). It needs full return schemas for its tools.

**21. Latency and human approval.**

- READ: code mode was slower end to end in FastMCP #4902 (+32%), AIMultiple (+7%) and Bifrost's simple queries (about +7%). It was faster on Bifrost's heavier rounds.
- READ: Anthropic lists the cases where PTC is "less beneficial": single-tool invocations, tasks where the model "should see and reason about all intermediate results", and quick lookups with small responses (advanced-tool-use post).
- READ: for human approval, pydantic-ai keeps approval-required tools native by default (finding 16). Under eager and speculative execution, "hooks, approval, and guardrails on `run_code` can't stop a call already started" (`README.md:513-514`, "Speculative execution").

### F. Shell as the action language

**22. READ — SWE-agent: an interface designed for the agent beat a bare shell, and every gain came from bounding output.** The repository's ACI page (`docs/background/aci.md`, fetched from raw.githubusercontent.com) lists four findings:

- a linter on every edit that refuses syntactically broken code;
- a file viewer showing 100 lines per turn;
- a search command that lists only the files that match ("Showing the model more context about each match proved to be too confusing");
- the message "Your command ran successfully and did not produce any output" when a command prints nothing.

READ (search summary of arxiv.org/abs/2405.15793 and summaries of it), all with GPT-4 Turbo:

| Configuration | Resolved |
|---|---|
| SWE-agent on SWE-bench Lite | 18.0% |
| shell-only agent on Lite | 11.0% |
| SWE-agent, full set | 12.47% (286 of 2,294) |
| no linting | 15.0% |
| 30-line window | 14.3% |
| full-file view | 12.7% |
| summarized search | 18.0% |
| no search | 15.7% |
| iterative search | 12.0% |

The three search rows are reported by one secondary summary only.

**23. READ — mini-swe-agent: one bash command per turn, no tool-calling API, no persistent shell.** The system prompt asks for "exactly ONE bash code block with ONE command (or commands connected with && or ||)" (`src/minisweagent/config/default.yaml:1-17 @ 04d809c`). Each action is a fresh `subprocess.run`, so `cd` and `export` do not persist; the agent prefixes them to each command (`docs/faq.md:36-48,102-119`). The FAQ gives the reasons a live shell session was dropped: knowing when a command has finished, recovering a killed shell, and interrupting a command all proved flaky. Output over 10,000 characters is cut to its first and last 5,000. A warning tells the model to use `head`, `tail`, `sed`, a narrower `grep`, or a redirect to a file (`default.yaml:115-140`). The README claims ">74%" on SWE-bench Verified with this bash-only agent (`README.md`). READ (search summary): the swebench.com "bash only" leaderboard ranks models inside mini-swe-agent; Vals.ai's archived copy, as of September 2026, lists Claude Opus 5 at 97.0%. The SWE-agent README now headlines the minimal agent over its own ACI (WebFetch of github.com/SWE-agent/SWE-agent).

**24. READ (search summaries) — Vercel d0 and Terminus.** Vercel's text-to-SQL agent d0 went from 18 specialized tools to two: a sandboxed bash command and SQL execution. The team reported the change as 3.5× faster, 100% success and 37% fewer tokens, on d0's analytics questions. These figures come from secondary write-ups; vercel.com was not reachable. Terminus, Terminal-Bench's reference agent, has one tool, a tmux session it sends keystrokes to. At its May 2025 release it ranked second on Terminal-Bench, behind Claude Code only.

**25. INFERRED from findings 22 to 24 — "bash" in these results is bash plus every interpreter on the machine.** A mini-swe-agent or Terminus action is one command line. That line can be a here-document Python script, a `python -c`, `jq`, `awk`, or a compiler and test runner. These agents do the data transformation that code mode's Python does by launching an interpreter from the shell. The bash-only wins in findings 17 and 23 therefore measure bash with Python one keystroke away, not a pipe-and-text shell alone. "The Devil Is in the Interface" is the cleanest head-to-head between a Python CodeAct interface and bash-only. It found equal success, with Python using 41.6% fewer steps and 56.3% fewer tokens.

### G. Where the vfs specs stand

**26. READ — The vfs shell as drafted has pipes and command substitution, but no control flow yet.** Spec 167's intent is bash-exact output for commands like `grep -rn "mfa" /enterprise | head -20`. Every verb is gated as if called through the Python API, and the call returns one `Result` (`167/spec.md`, Intent). The spec includes `$( )`, here-documents, redirections and a 32,768-character display cap. Control flow, functions and arithmetic are deferred to "ADR 081's later slices" (`167/spec.md:186`). Decision 4: "No shell state persists between `cli` calls over the wire". Decision 2: an empty `ls` prints nothing, and a host adapter "may add one `(no output)` line". Spec 168 refuses `jq` until spec 169 serves it as the `jaq` wasm program (`168/spec.md:11,62`). Spec 170 runs a tool as `<name> --arg value`; `cat` of a tool shows its manifest, and a tool runs only when typed as a command (`170/spec.md`, Intent). Spec 172 plans a WASI CPython with numpy and pandas. Its programs read inputs from rows under the agent's authority and call vfs verbs through an importable `vfs` module. QuickJS serves `node` the same way (`172/spec.md`, Intent).

## What this means for a vfs code mode

All of this section is INFERRED from the findings above.

**The evidence splits code mode's gains into three sources, and the shell can get two of them on its own.**

1. **Context.** The model does not load the whole catalog, and intermediate results stay out of its context. This is where the token numbers come from (findings 13 and 17). Any language that runs several calls per model turn and prints only a summary gets this gain. A vfs pipeline such as `search ... | grep ... | head` keeps intermediate rows out of the model's context, the same as a Python program that filters a list.
2. **Composition.** Loops, variables, conditionals and arithmetic between calls in one turn. This is CodeAct's measured advantage (findings 2 and 3), and the source of the step reductions (finding 17, "Devil"). Bash has composition, but spec 167 does not yet. Without `for`, `if` and functions, a vfs program cannot express "for each of these ten tools, call it and keep the ones whose result says X" in one turn. The model would take a turn per item, which is the direct-tool-calling cost code mode exists to remove.
3. **Prior.** Models know the language from pre-training. Bash is at least as well trained as Python for agent work (findings 23 and 17, "Is Bash All You Need"). So the shell form costs nothing here, and may help with models that have no tool-calling API (mini-swe-agent).

**A pipe-and-text shell is weakest exactly where tool results are structured.** MCP results are JSON. Both the frameworks and the measurements say that chaining calls inside one program needs a known output shape:

- smolagents tells the model not to chain calls whose output has no schema (finding 5);
- pydantic-ai warns that a tool with no return schema leaves the model to "guess the result's shape" (finding 15);
- CaMeL needs full return schemas (finding 20).

A shell that turns each result into lines of text forces the model to parse text between calls. Text parsing is where shell pipelines fail without warning; "Devil" reports variable bash pipelines and up to 4.7× less consistency than structured interfaces (finding 17). The vfs shell would need four things to reach general-language code mode, in this order:

1. Control flow and shell functions (ADR 081's later slices).
2. A structured-data program on the pipe (`jaq`, spec 169), so a JSON result can be filtered by field rather than by regex.
3. A tool's output schema shown by `cat` of its manifest (spec 170), so the model knows the shape before it writes the program.
4. The spec 172 `python3` guest with its `vfs` module, as the general-language step up for anything that needs data structures. That guest is the move every bash-only agent in findings 22 to 25 makes when it writes `python -c`.

With 1 to 4 in place, the vfs shell is the "bash with an interpreter one keystroke away" that won the bash-only comparisons, not the pipe-only shell that none of them measured.

**Shell or Python as the front door: the evidence does not pick a winner. It does say that the shell is not the losing choice.** Two of the strongest results point opposite ways.

- Bash alone beat PTC over a fixed typed catalog, with 19 to 72% fewer tokens ("Is Bash All You Need").
- Python CodeAct used 56% fewer tokens than bash alone at equal success ("Devil").

The difference is plausibly what each arm could reach. Bash with a full machine beats Python restricted to a catalog. Python with the same repository beats bash for steps. A vfs code mode would give the shell the namespace (the catalog as files, grep-able), and a Python guest the same namespace through `vfs`. That covers both winning arms, provided the guest is reachable from the shell in one command.

**The vfs design answers the authority question the sandboxes leave open.** Every sandbox here leaves per-user authority to the host function:

- Monty's host functions run with full process authority (finding 11);
- smolagents ships tool code and its credentials into the sandbox (finding 8);
- pydantic-ai's nested calls inherit the run's context (finding 15).

In vfs, every verb a shell program or the `vfs` module calls goes through the `Authority` check before dispatch, per request (spec 171). The interpreter is the enforcement point, which is CaMeL's design (finding 20) without CaMeL's provenance tracking. This is the strongest claim vfs can make against the field. A memo should state it with its limit: a prompt-injected program with write rights can still write anything those rights allow. The attack classes in 2602.15945 about code synthesized from tool output apply to a shell program as much as to TypeScript.

**Two scale points follow from the reference deployment.**

- **Host-call budgets.** Monty stops a program at 1,000 host calls (finding 14), and pydantic-ai at 100 tool calls per `run_code` (finding 15). Both are far below the 10,000-file batch vfs supports as a contract. smolagents has no such bound (finding 7). A vfs program that loops `for f in $(ls ...); do stat $f; done` over 10,000 paths issues 10,000 verb calls. The same work is one chunked verb call (`stat` on a batch, or `xargs` into one call, spec 168). The shell should steer loops toward the batched form, and its budget should count verb calls, which the per-verb-call multiplier prices.
- **Output.** Bounded output is the most replicated finding in the shell lineage: SWE-agent's 100-line window and file-only search results, mini-swe-agent's 10,000-character cap with a head and tail and a hint (findings 22 and 23). Spec 167 has the 32,768-character display cap. One detail diverges. SWE-agent found an explicit "ran successfully and did not produce any output" message helpful; spec 167 decision 2 prints nothing and leaves `(no output)` optional for the adapter. The MCP `cli` adapter should probably add it.

**Weak models and failure need explicit handling.** Code mode should stay opt-in beside the plain verb tools (spec 171 already exposes both). The weak-model evidence (finding 18) and the ReAct collapse (finding 19) say a single `cli` tool should not be the only door. A failed program should come back the way pydantic-ai reports one: every call started, and whether each returned, did not finish, or was refused. A vfs `Result` with classified per-stage errors is close to this already. Writes that need a person's approval should not run inside a program unattended (finding 16).

## What this study does not settle

- The primary arXiv papers (CodeAct's API-Bank table, SWE-agent's ablations, "The Bitter Lesson of Tool Calling", "Is Bash All You Need?", the CE-MCP threat model) were not fetchable from this session. Their numbers here are from search summaries and need checking against the PDFs before a memo cites them as fact. The CodeAct M3ToolEval table is the exception: it was recovered from the repository.
- No measurement exists of a pipe-and-text shell without an interpreter against Python code mode. Every bash-only result had Python, `jq` and `awk` available. Whether the spec 167 shell alone, without control flow, keeps code mode's composition gain is unmeasured. A head-to-head on vfs workloads (the same tasks, through `cli` with and without control flow and `jaq`, against a Monty `run_code` over the verbs) is the experiment that would settle it.
- Small-model behaviour on a vfs shell is unmeasured. The only controlled small-model evidence is CodeAct's 2023-era open models.
- Whether a grep-able tool catalog under `/.vfs` discovers tools better than a `search_tools` call is another study's subject. The FastMCP scripted harness shows only that ranking errors (a stale `find_customer_legacy` chosen silently) occur at 500 tools.
- The security claim is unmeasured. That per-request `Authority` on every nested verb call blunts the CE-MCP attack classes is reasoning from design, not an executed attack.

## One line

Code as the action space wins on composition and context for strong models, about 20 points of success and 30 to 56% fewer steps or tokens in the measured cases, and loses for weak models and in some agent loops. The bash-only wins that make a shell attractive were bash with Python one keystroke away. So a vfs shell needs control flow, a JSON program, output schemas and the spec 172 Python guest to match general-language code mode, while per-request authority on every nested call is the advantage vfs can claim that no sandbox studied here has.
