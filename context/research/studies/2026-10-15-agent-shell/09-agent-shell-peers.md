# S9 — The agent-shell peers, end to end: just-bash, bashkit, just-bash-py, lifo, amla-sandbox, and the hosts built on them

Date: 2026-10-15. Researcher: S9. Study: `2026-10-15-agent-shell`.

Clones read (all refreshed 2026-10-15; every clone is a shallow single-commit checkout, so
`git log` holds no history and the CHANGELOGs are the only in-repo history source):

| Clone | Commit | Licence (from `licenses.log`) |
|---|---|---|
| `~/Git/Repos/just-bash` | `9ab0e0d` (2026-10-15) | Apache-2.0 (`packages/just-bash/LICENSE`; no root file) |
| `~/Git/Repos/bashkit` | `b7904a4` (2026-10-15) | MIT |
| `~/Git/Repos/just-bash-py` | `48d111c` (2026-06-04) | Apache-2.0 (pyproject field; no root file) |
| `~/Git/Repos/lifo` | `5a35d05` (2026-10-09) | MIT (per-package `package.json`; no root file) |
| `~/Git/Repos/amla-sandbox` | `169384f` (2026-05-15) | Python MIT; the wasm runtime it downloads is AGPL-3.0 OR BUSL-1.1 (not in the clone, not read) |
| `~/Git/Repos/deepagentsjs` | `9f3bfd5` (2026-10-13) | MIT (read only for `libs/providers/node-vfs`) |

`bash-tool` (Vercel Labs) is not cloned; it was read from GitHub raw files on 2026-10-15.

Evidence labels used below: **EXECUTED** (I ran it; script and output are in `experiments/s9/`),
**READ** (I read it in a clone or on the web; cited), **INFERRED** (my conclusion from READ/EXECUTED
facts), `[NOT VERIFIED: why]`.

Experiment artefacts (all under `context/research/studies/2026-10-15-agent-shell/experiments/s9/`):
`count_lines.sh` and its output `loc.txt`; `corpus.sh` (the fixed 30-command corpus); `harness.py`
and its outputs `out/results.md`, `out/results.json`; `probe2.py` and its output `out/probe2.json`.

---

## Summary

Five projects now ship "a bash interpreter in your process, over a virtual filesystem, for an
agent". They were all built in the last ten months. Two are serious: **just-bash** (Vercel Labs,
TypeScript, 300k lines, 4.4k stars, 1.5M weekly npm downloads) and **bashkit** (Everruns, Rust,
300k lines, 2,074 commits in seven months, 97.3% of the Oils bash spec). **just-bash-py** is a
Python port of just-bash written by coding agents as a demonstration; it runs our 30-command corpus
but has fidelity bugs and no byte path. **lifo** is a different animal: a browser-as-kernel Unix
for running dev servers, with no LLM tool contract at all. **amla-sandbox** is a wasm capability
sandbox whose shell is a minor mode; its interesting idea is a constraint DSL on tool calls.

What they all learned, in the order they learned it, is the roadmap signal: (1) measure fidelity
against *real* bash with recorded fixtures and a spec corpus, never against your own tests; (2)
pipes carry **bytes**, not JavaScript strings or Rust `String`s — both leaders rewrote their stream
type after launch; (3) every resource needs a budget and the refusal must be explicit, never a
silent cut; (4) the tool the model sees is one string in (`command`/`commands`) and
`{stdout, stderr, exit_code}` out, with a character cap (bash-tool: 30,000 chars) and a visible
truncation marker; (5) hosts want to *inspect a command before running it* (bashkit `analyze()`,
just-bash `CommandCollectorPlugin`, open issue #244) to drive permission prompts; (6) guest
runtimes (QuickJS, CPython-in-wasm, Monty) arrive as opt-in commands behind a capability flag.
Where they hurt: no peer has a byte-typed or media-typed result — `cat image.png` is mojibake or
latin1 soup in all of them; none has permissions in the data path (bashkit says so: "permissions
would be theater", L-FS-002); none has versions, trash, or search beyond `grep`; their "database
answers the fs calls" consumers (Mintlify's ChromaFs, Convex) each re-derive an `IFileSystem`
adapter by hand, read-only or with a ~1,000-file soft cap, and give up permissions, history, and
ranked search to do it. That gap is exactly the ground vfs stands on.

---

## Findings

### F1. Shape and size of each peer (EXECUTED: `count_lines.sh` → `loc.txt`; READ for layout)

**just-bash** (`packages/just-bash/src`, TypeScript). Pipeline is `Input Script → Parser
(src/parser/) → AST (src/ast/) → Interpreter (src/interpreter/) → ExecResult`
(`just-bash:AGENTS.md:421-423`). Module sizes (lines of `.ts`, tests included):

| Area | Lines | Files |
|---|---|---|
| `src/commands` | 139,363 | 554 (82 command directories) |
| `src/interpreter` | 47,569 | 170 |
| `src/fs` (overlay-fs, read-write-fs, in-memory-fs, mountable-fs, `real-fs-utils.ts`) | 20,287 | 53 |
| `src/parser` | 10,352 | 17 |
| `src/network` | 5,727 | 18 |
| whole `src` | 300,014 | 1,106 |
| of which `*.test.ts` | 152,323 | 700 |
| `*.sh` spec cases under `src` | 46,744 | 144 |

Other modules: `src/security/` (defense-in-depth proxies, limits tests), `src/limits.ts`
(the budget table), `src/execution-output.ts` (the one output accumulator), `src/sandbox/`
(the `@vercel/sandbox`-compatible `Sandbox` class), `src/transform/` (AST transform plugins),
`src/commands/js-exec/` (QuickJS), `src/commands/python3/` (CPython 3.13 Emscripten in a worker),
`src/commands/sqlite3/` (sql.js in a worker). The monorepo also holds
`packages/just-bash-executor` (tool → bash command bridge) and `examples/bash-agent` (the AI SDK
agent). The `bash-tool` package lives in its own repo. Version 3.6.0, Node `>=20.19`, 468 commits
on `main`, 4.4k stars, 279 forks, 85 open issues, 132 open PRs (READ github.com, 2026-10-15).
Third-party notes (READ, upd.dev/FlorianBruniaux evaluation 2026-08-04): repo created 2025-12-23,
~1.5M weekly npm downloads (DepScope, 2026-07-27), bus factor 1.

**bashkit** (Rust workspace). Crates: `bashkit` (core: parser, interpreter, VFS, builtins, tool
contract), `bashkit-scripted-tool`, `bashkit-cli`, `bashkit-python` (PyO3), `bashkit-js`
(NAPI-RS), `bashkit-wasm` (browser, no WASI), `bashkit-capi` (C ABI), `bashkit-eval` (LLM eval),
`bashkit-bench`, `bashkit-coreutils-port`, `bashkit-cpython-wasm`
(`bashkit:knowledge/foundations/architecture.md:19-29`). Sizes (lines of `.rs`, inline tests
included):

| Area | Lines | Files |
|---|---|---|
| `crates/bashkit/src/builtins` | 136,761 | 209 |
| `crates/bashkit/src/interpreter` | 35,272 | 19 |
| `crates/bashkit/src/parser` | 14,160 | 9 |
| `crates/bashkit/src/fs` | 14,183 | 16 |
| `crates/bashkit/src/snapshot` | 3,350 | 6 |
| `crates/bashkit/src/terminal` | 3,087 | 4 |
| `crates/bashkit/src/network` | 2,825 | 5 |
| whole `crates/bashkit` | 299,429 | 525 |
| `bashkit-python` Rust | 7,646 | 3 (+17,899 lines of `.py` across crates) |
| `bashkit-js` | 4,810 | 5 |

6,569 `#[test]`/`#[tokio::test]` functions (EXECUTED grep). 167 builtins (README). Version 0.19.0
released 2026-10-15; 39 releases since 0.1.12 on 2026-03-21 (READ `CHANGELOG.md`). 2,074 commits,
302 stars, 30 forks (READ github.com). One author (`@chaliy`) on every PR in the 0.19.0 notes.
Bashkit credits just-bash: "Pioneered the idea of a virtual bash interpreter for AI-powered
environments" and states "No code was copied" (`bashkit:README.md:670-675`).

**just-bash-py** (Python, asyncio). `src/just_bash`: commands 22,938 lines (155 files),
interpreter 11,919, parser 4,261, `query_engine` (jq) 4,304, fs 2,604, network 513; 48,576 lines
total; tests 34,421 lines. Published on PyPI as `just-bash` 0.2.1 (EXECUTED: installed). The README
states it "is as much a demonstration of coding agents' ability to implement software given a tight
spec and high test coverage" (`just-bash-py:README.md:11`); `CLAUDE.md` instructs the agent to run
TDD and update a test-count bar chart in the README on every commit. 2,931 tests pass; the Oils
spec suite is explicitly excluded from the default run ("contains many expected failures",
`CLAUDE.md:570`). Last commit 2026-06-04.

**lifo** (TypeScript, pnpm monorepo). `packages/core/src`: 38,114 lines excluding tests
(51,614 with); shell (`lexer.ts`, `parser.ts`, `interpreter.ts`, `expander.ts`, `jobs.ts`,
`pipe.ts`, `ProcessRegistry.ts`) 6,123 lines; `kernel/vfs` 1,020 lines (`VFS.ts`, `snapshot.ts`,
`sync.ts`, providers `Dev`, `Proc`, `NativeFs`); 86 command files; `node-compat/` with 32 shims
(`fs`, `http`, `child_process`, `esbuild`, `swc`, `rollup-parse`, `tailwind-oxide` …); `sandbox/`
(the embeddable `Sandbox` API). 80 test files, 1,309 `it(` cases. v0.10.23, 424 commits, 544
stars, 4 open issues (READ github.com). Built by RapidNative for its in-browser editor.

**amla-sandbox** (Python side only). `src/amla_sandbox` 7,018 lines across 21 files: `sandbox.py`,
`bash_tool.py` (`create_sandbox_tool`), `langgraph.py` (`SandboxTool`), `capabilities/`
(`tool_call.py`, `constraints.py`, `patterns.py`), `tools/` (function → JSON-schema tool defs,
ingest from LangChain/OpenAI/Anthropic), `runtime/wasm.py` (wasmtime host), `audit.py`,
`auth.py`, `codeact.py`. 274 tests. The `_wasm/` directory in the clone holds only `__init__.py`;
the `amla_sandbox.wasm` binary is pulled from the `amla-sandbox-core` release at build time
(`.mirror-deps.json` pins `v0.2.8`; `SECRETS.md` describes SHA256 + Sigstore attestation). So the
Python clone cannot execute a shell; nothing here was EXECUTED for amla. v0.2.8 2026-05-15, 17
mirror commits, 346 stars.

### F2. Test strategy and the bash-compat corpora (READ; counts EXECUTED)

This is the model for our coverage metric, so I describe the shapes precisely.

**just-bash has three tiers** (`AGENTS.md:434`: "Cross-checking suites: recorded bash fixtures, and
bash specification conformance with known failures"):

1. *Unit tests beside each command* — 11,062 `it(`/`test(` calls outside the two corpora.
2. *Spec tests* (`src/spec-tests/`): the Oils project's `spec/*.test.sh` files, imported, Apache-2.0.
   Format: `#### Name` / code / `## stdout:` or `## STDOUT: … ## END` / `## status:` / `## OK zsh …`
   / `## N-I dash …` / `## SKIP` (`just-bash-py:tests/spec_tests/README.md:68-90` — same format).
   Size: `bash/cases` 137 files, **2,728 `####` cases, 246 marked `## SKIP`**; `awk/cases` 317
   files (onetrueawk `T.*` tests); plus `grep` (7), `sed` (5), `jq` (8) case files. The runner
   (`src/spec-tests/runner.ts:51-60`) *still runs* a `## SKIP` case and reports an
   `unexpectedPass` when it passes — so the skip list ratchets. `bash/KNOWN_LIMITATIONS.md` ranks
   the gaps by "AI Agent Use Case" (PIPESTATUS, `read -a`, `mapfile`, errexit in compounds,
   `read -d`, `printf %q`, `set -f` …) and most are now "✅ Done".
3. *Comparison tests* (`src/comparison-tests/`): 65 `*.comparison.test.ts` files, each case
   `compareOutputs(env, testDir, "cat -n test.txt")` against **real `/bin/bash`**, with results
   recorded into 57 JSON fixture files keyed by a hash of the command, holding `stdout`, `stderr`,
   `exitCode`, and `"locked": true` (`comparison-tests/fixtures/alias.comparison.fixtures.json`).
   This is the oracle tier: the fixture is the truth, bash wrote it.

**bashkit has four tiers**, documented as policy (`knowledge/operations/testing.md`,
`limitations.md`):

1. Inline Rust tests — 6,569 functions.
2. *In-repo spec cases* (`crates/bashkit/tests/spec_cases/`): 266 bash files in an Oils-like
   format of their own: `### name` / comment / code / `### expect` / output / `### end`
   (`spec_cases/bash/arrays.test.sh:1-6`). 12,276 `###` markers ÷ 3 ≈ **4,090 cases**; 65 files are
   `bashbox-*.test.sh`, the "1,044 bash-verified cases from the BashBox test suite" imported in
   0.19.0 (`CHANGELOG.md`, PR #2575). Plus awk (7), grep (3), sed (2), jq, yq, python, typescript.
3. *The upstream Oils suite as an outside yardstick*, fetched not vendored, bash column only, with
   **real bash 5.2.21 as the denominator**: "97.3%: bashkit passes 2618 of the 2692 Oils spec cases
   real bash … passes (2759 cases in 132 spec files)" and the memo records the climb
   74.2% → 78.8% → 82.1% → 86.0% → 89.0% → 92.8% → 95.8% → 97.3%, naming which files moved
   (`knowledge/operations/oils-spec.md:17-70`). Design decisions worth quoting: "Fetched, not
   vendored", "Bash column only", "Denominator is real bash".
4. *Oracle scoreboards*: "Debian-oracle scoreboard in CI with per-tool floors" (PR #2614) and
   "bash-parity oracle scoreboard with recorded real-bash output" (PR #2618), plus
   "gap telemetry from replayed agent sessions" (PR #2552): `bashkit-replay` "turns the stored eval
   runs into a replay corpus. It loads every recorded bash tool call … replays each session in
   order on a fresh `Bash`" (`knowledge/operations/eval.md:479-483`). The eval dataset is 88
   agent tasks in JSONL (58 basic across 15 categories, 8 repo, 10 hard, 12 runtime) scored by
   deterministic expectation checks over a VFS snapshot (`crates/bashkit-eval/README.md`).

Also a *negative spec*: `limitations.md` gives every intentional gap a stable ID (`L-PIPE-001`,
`L-FS-002` …) with a "Why" and an "Evidence" test, and a CI lint checks that every evidence cell
names a real test. "Absences can't be recovered from code, so they're recorded here; everything
positive is generated or tested instead" (`limitations.md:18-20`).

**just-bash-py** runs the same Oils corpus: `spec_test_results.txt` ends
"1258 failed, 1154 passed, 75 skipped … in 108.76s" — a **46% pass rate**, hidden from the
default test run.

**lifo** has 1,309 Vitest cases mirroring `src/`, no bash-compat corpus (READ `README.md`
"tests/ Mirrors src/ structure"). **amla** has 274 Python tests; the shell itself is tested
upstream in the closed runtime `[NOT VERIFIED: core repo not cloned]`.

### F3. The agent-facing contract, verbatim (READ unless marked)

**bash-tool `createBashTool`** (Vercel; wraps just-bash; READ raw GitHub `src/tools/bash.ts`,
`read-file.ts`, `write-file.ts`, `types.ts`, `tool.ts`, 2026-10-15):

- Returns `{ bash, tools: { bash, readFile, writeFile }, sandbox }`.
- `bash` input schema: one field, `command: z.string().describe("The bash command to execute")`.
  Description is generated: it opens **"Execute bash commands in the sandbox environment."**, then
  `WORKING DIRECTORY: ${cwd}`, then up to 8 of the seeded file paths and "… and N more files",
  then the optional `toolPrompt`, a "Common operations" list (`ls -la`, `find . -name '*.ts'`,
  `grep -r 'pattern' .`, `cat <file>`), and `extraInstructions`.
- Output: `CommandResult { stdout, stderr, exitCode, teeFiles? }`. The command is run as
  `cd "${cwd}" && ${command}`.
- `readFile`: "Read the contents of a file from the sandbox."; input `path` ("The path to the file
  to read"); returns `{ content }`; **no error shape, no size limit** — a thrown error propagates.
- `writeFile`: "Write content to a file in the sandbox. Creates parent directories if needed.";
  input `path`, `content`; returns `{ success: true }`.
- `README`: for analysis agents bash "may be the only tool you need to give to the agent".
- `createToolPrompt` builds `Available tools: ${sortedTools}, and more` plus one hint line per
  detected file format; `discoverAvailableTools` literally runs
  `ls /usr/bin /usr/local/bin /bin /sbin /usr/sbin 2>/dev/null` and intersects with a 15+-entry
  table (`grep`, `sed`, `awk`, `cat`, `head`, `tail`, `sort`, `uniq`, `cut`, `tr`, `wc`, `find`,
  `xargs`, `diff`, `jq` …) each with a `purpose` and `category`.
- Hooks: `onBeforeBashCall` (rewrite the command), `onAfterBashCall` (rewrite the result).
  Options: `maxOutputLength` (30,000), `maxFiles` (1,000, `WRITE_BATCH_SIZE = 20`),
  `experimentalTeeTransform` (capture each pipeline stage's stdout to `/tmp/bash-tool/`).
- Timeout: none in bash-tool; just-bash's own `maxExecutionTimeMs` applies.
- Model used in the shipped example: `anthropic/claude-haiku-4.5`, `stepCountIs(50)`, tools
  `{ bash: toolkit.bash }` only — the example gives the model *one* tool
  (`just-bash:examples/bash-agent/agent.ts:92-96`).

**bashkit `BashTool`** (EXECUTED via the Python wheel, `probe2.json`):

- `name()` = `bashkit`; `description()` = **"Run bash commands in an isolated virtual filesystem"**
  (plus ". Custom commands: a, b" when custom builtins exist; `tool.rs:1210-1228`).
- `system_prompt()` = **"bashkit: run bash commands in an isolated virtual filesystem. Returns JSON
  with stdout, stderr, exit_code. Use bash syntax; do not assume /bin/sh portability ($RANDOM,
  arrays, [[ ]] require bash). Use `source` only when current-shell state must persist; otherwise
  run scripts directly. For large multi-file writes, prefer incremental batches over one giant
  script. Limits: max_commands=10000, max_loop_iterations=10000. perl, python/python3 not
  available."** (localized en/uk; `tool.rs:1230-1300`.)
- Input schema: `{commands: string ("Bash commands to execute"), timeout_ms?: uint64 ("Optional
  per-call timeout in milliseconds")}`, required `commands` (`tool.rs:350-368`). A timeout returns
  `exit_code = 124` "matching the bash `timeout` convention" (`tool.rs:291-296`).
- Output schema: `{stdout, stderr, exit_code, error: string|null ("Error message if execution
  failed before running"), stdout_truncated: bool, stderr_truncated: bool, final_env: object|null}`
  (`tool.rs:370-410`). `help()` is Markdown with a parameter table, result table, examples, and a
  "Builtins available by default" list.
- Python result attributes: `error, exit_code, final_env, stderr, stderr_bytes, stderr_truncated,
  stdout, stdout_bytes, stdout_truncated, success, to_dict` (EXECUTED). The byte twins exist
  beside the text fields.
- Streaming: `output_stream()` emits chunks `{kind: "stdout"|"stderr", data}`; "Final truth is
  `ToolOutput`, not concatenated streamed chunks" (`knowledge/integrations/tool-contract.md`).
- Framework adapters: Python `bashkit[langchain|pydantic-ai|deepagents]`; JS subpaths
  `@everruns/bashkit/{openai,anthropic,ai,langchain}`. The LangChain input is
  `commands: str = Field(description="Bash commands to execute (like `bash -c 'commands'`)")`
  (`bashkit-python/bashkit/langchain.py:63-66`). The deepagents backend flattens the result to one
  string: `output = result.stdout + (result.stderr or "")` and appends `error` if not already in
  it (`deepagents.py:276-279`).
- State: the Rust `BashTool::execute()` "creates a fresh interpreter per call (no VFS persistence)"
  (`knowledge/operations/eval.md`, decision 2) while the Python `BashTool` keeps the VFS across
  calls — EXECUTED: `echo persisted > /tmp/t.txt` then `cat /tmp/t.txt` → `persisted`. The Python
  README's "Persistent interpreter state across calls" is the binding's behaviour.

**just-bash `Bash.exec`** (the library; READ `README.md:16-26`, `types.ts:15-40`): `exec(script,
{env, cwd, stdin, args, replaceEnv, signal, rawScript})` → `ExecResult {stdout, stderr, exitCode,
env?, stdoutKind?: "text"|"bytes"}`. "Each `exec()` call gets its own isolated shell state —
environment variables, functions, and working directory reset between calls. The filesystem is
shared across calls." The `Sandbox` class is "a drop-in replacement for `@vercel/sandbox`"
(`runCommand`, `cmd.stdout()`, `cmd.wait()`, `writeFiles`, `readFile`, `mkDir`, `stop`).

**just-bash-py** (EXECUTED): `Bash(files=, env=, cwd=, limits=, network=, fetch=,
unescape_html=True)`; `await bash.exec(cmd)` → `ExecResult(stdout, stderr, exit_code, env)`.
Unlike the TypeScript original, **env and cwd persist across `exec` calls** (`export X=1` then
`echo X=$X` → `X=1`; `cd /tmp` then `pwd` → `/tmp`). A limit breach is a raised exception
(`ExecutionLimitError: while loop: too many iterations (10000)`), not a result. There is no tool
wrapper and no description text in the package.

**lifo `Sandbox`** (READ `packages/core/src/sandbox/types.ts`): `sandbox.commands.run(cmd,
{cwd, env, signal, timeout, onStdout, onStderr, stdin})` → `{stdout, stderr, exitCode}`;
`sandbox.fs.{readFile, writeFile, readdir, stat, mkdir, rm, exists, rename, cp, writeFiles,
exportSnapshot, importSnapshot}`; `sandbox.fetch()` reaches servers *inside* the VM. There is no
LLM tool definition anywhere in the repo; the consumer is a human terminal (xterm.js) and the
RapidNative editor. Commands write text: `CommandOutputStream.write(text: string)`
(`commands/types.ts:3-5`).

**amla `SandboxTool`** (READ `langgraph.py:100-150, 425-480`): `name = "sandbox"`; the default
description is **"Execute code in a secure sandbox.\n\nSet language="javascript" (default) to run
JavaScript with:\n- async/await for tool calls: `const data = await toolName({param: "value"});`\n-
Virtual filesystem: `await fs.readFile('/workspace/data.json')`\n- Full ES2020 support\n\nSet
language="shell" to run shell commands with:\n- Utilities: grep, jq, tr, head, tail, sort, uniq, wc,
cut, cat\n- Pipes: `cat /workspace/data.json | jq '.items[]' | head -5`"**. The built description
(`_build_tool_description`) lists every registered Python function with its signature and first
docstring line, a JS example, the shell line "Run shell commands with: grep, jq, tr, head, tail,
sort, uniq, wc, cut, cat, echo", and a "LIMITS:" block from the capabilities. Input: `code: str`,
`language: "javascript"|"shell"`; `as_langchain_tool()` can also split into two tools
`sandbox_js(code)` and `sandbox_shell(command)`. Output is **one string**:
`to_tool_message()` joins stdout, `"[stderr]: …"`, `"[error]: …"`, or returns `"(no output)"`
(`langgraph.py:87-96`). Tools are callable from the shell as `tool name.func --arg val`
(`bash_tool.py` docstring).

### F4. Output discipline (READ; the overflow shapes EXECUTED)

| Peer | Cap | Where enforced | What the model sees on overflow |
|---|---|---|---|
| bash-tool | 30,000 **characters** per stream (`DEFAULT_MAX_OUTPUT_LENGTH`) | after exec, in the tool | first 30,000 chars + `\n\n[stdout truncated: N characters removed]` |
| just-bash | `maxOutputSize` 256 MiB normal / 10 MiB hardened profile, aggregate stdout+stderr bytes (`limits.ts:213,236`) | `execution-output.ts` accumulator charges the one execution budget; `control-flow.ts:95-97` | execution fails with stderr `bash: pipeline: total output size exceeded (>N bytes), increase executionLimits.maxOutputSize` (tests) |
| bashkit | `max_stdout_bytes` 1 MiB, `max_stderr_bytes` 1 MiB default; 10 MiB in the liberal profile (`limits.rs:192-193,246-247`) | byte-native `StreamData`, truncates by bytes "including in live callbacks" (`architecture.md`) | `stdout_truncated: true` in the result; per-builtin caps are explicit: `seq 1 400000` → exit 1, stderr `seq: line limit (100000) exceeded; output truncated` (EXECUTED) |
| just-bash-py | none (`ExecutionLimits` has 5 fields: call depth, command count, loop/awk/sed iterations) | — | `seq 1 400000` stops silently at 100000 with exit 0 and 588,895 bytes (EXECUTED) |
| lifo | none in `RunOptions`; `timeout` and `signal` only (fixed in 0.10.23 — they were no-ops) | — | nothing |
| amla | `max_steps` 10,000 (wasm fuel), `max_tool_result_size` 10 MB on *tool results* (`runtime/wasm.py:103,118`) | wasm host | `[error]: …` line in the string |

stderr vs stdout: every peer keeps them separate in the library result; bash-tool returns both
fields; bashkit's deepagents adapter and amla's `to_tool_message` *merge* them into one string for
the model. bashkit documents the interleaving caveat: "within one command stdout and stderr are
separate values, so a builtin that writes both … gives all its stdout first"
(`limitations.md`, "Stderr routing").

Binary output — **the question where every peer is text-only** (EXECUTED `corpus.sh` #26–27 and
`probe2.py`):

- *just-bash* (READ): "Shell pipes carry bytes, not text. Internally we represent a byte buffer as
  a JS string where `s.charCodeAt(i)` is the i-th byte … the same convention as
  `Buffer.from(s, 'latin1')`" (`encoding.ts:1-16`); `cat` marks `stdoutEncoding: "binary"`
  (`commands/cat/cat.ts:154-162`). So `ExecResult.stdout` for `cat image.png` is a latin1-shaped
  string; bash-tool passes it to the model as-is. The 3.0.0 changelog: "TS-enforced correct
  handling of utf8 on stdin. Impacts many commands" — the byte discipline was retrofitted.
- *bashkit*: `cat /tmp/img.png` (seeded through `fs().write_file(bytes)`) → `stdout` =
  `'�PNG\r\n\x1a\n\x00\x00\x00\rIHDR'` (UTF-8 replacement char) **and** `stdout_bytes` =
  `b'\x89PNG…'` intact. L-STREAM-001: "Shell words, variables, command substitution, script source,
  text-oriented builtins, and JSON tool responses cannot represent arbitrary bytes … JSON strings
  are Unicode." The tool contract's `images` field "is empty for bashkit today"
  (`tool-contract.md`).
- *just-bash-py*: `printf '\x89PNG…' > f; od -c f` shows `302 211` — it wrote the UTF-8 encoding of
  U+0089, two bytes, not the byte 0x89; and seeding bytes through `bash.fs.write_file` raised
  `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x89`. No byte path exists.
- *lifo*: `cat` calls `ctx.vfs.readFileString(path)` (`commands/fs/cat.ts:22`) and writes a
  string; yet the inode carries `data: Uint8Array`, `mime?: string` ("auto-detected"), and a
  content-addressed `chunks?: ChunkRef[]` manifest for files ≥ 1 MB (`kernel/vfs/types.ts:19-30`).
  It is the only peer that records a MIME type at all — and only the VFS knows it; the shell
  throws it away.
- *amla*: `[NOT VERIFIED: wasm binary absent from the clone]`.

### F5. Threat models and limits — what each defends, and does not (READ)

**just-bash `THREAT_MODEL.md`** (401 lines). Actors: 1A the untrusted script author ("ZERO" trust),
1B malicious data (HTTP bodies, file content, stdin), 1C a compromised dependency (out of scope).
Trust assumptions: host-provided `fs`, `fetch`, `customCommands`, transform plugins are trusted
("just-bash protects untrusted *scripts*, not untrusted *hosts*"); Node, V8, the OS; and the host
must not mutate a `ReadWriteFs` root concurrently (no descriptor-relative APIs in Node, so path
validation is not atomic). Five trust boundaries TB1–TB5 (parser, fs, network, host process,
data→key space). Defences are tabulated per surface with the file that enforces them: parser
(`MAX_TOKENS` 100K, depth 200, input 1 MB, heredoc), expansion (brace 10K, substitution depth 50,
string 10 MB, glob 100K, `**` segments ≤ 5), filesystem (root containment, symlinks default-deny,
null bytes, TOCTOU, error-path sanitising, host hard links isolated by copy-on-write), network
(off by default; per-redirect allow-list; 10 MB response; headers in null-prototype objects), code
execution (a "defense-in-depth" layer of proxies over `Function`, `eval`, `setTimeout`,
`process.*`, `WebAssembly`, `Proxy`, `WeakRef`, dynamic `import()` via loader hooks), info
disclosure (virtual pid/uid, UTC `date`, `performance.now` blocked), DoS (loops, call depth,
command count, `re2js` for linear-time regex, fd cap 1024), prototype pollution (`Map`s and
null-prototype objects everywhere), privilege escalation (`setuid` blocked). **Non-claims and
residual risks** (§4): dynamic `import()` defence "varies by runtime capability" — require
`DefenseInDepthBox.getInstance().getStatus()` to report `level: "full"`; pre-captured references
and `globalThis` reassignment bypass the proxies ("relies on no code path existing, not on the
monkey-patching being unbypassable"); job control and `trap` lightly tested; Unicode confusables
untested; Python's wasm heap "not reliably contained by Node worker `resourceLimits`" ("strong heap
containment requires process/container isolation"); custom commands that re-format errors may leak
paths; nested heredocs not fuzzed. The README adds: "All execution happens without VM isolation.
This does introduce additional risk." Recommendations still open: runtime isolation for host-realm
JS, an output CSP, a fuzz corpus for `trap`/jobs, a total memory ceiling per `exec()`.

**bashkit** keeps a living threat model with stable IDs `TM-<CAT>-<N>` across 17 categories
(DoS, ESC, INF, INJ, NET, AVAIL, ISO, INT, GIT, LOG, CRY, PY, TS, SQL, SSH, FS, SNAP, UNI) — 801
table rows (EXECUTED count) — and every mitigation site carries a `// THREAT[TM-…]` comment and a
test (`knowledge/security/threat-model.md:177-230`). Defence table (`README.md:640-653`): no
process spawning; VFS by default; allowlist network with no DNS ("hosts must appear in the
allowlist", L-NET-002); limits (commands 10K, loops 10K/1M, depth 100 with a hard 16 for nested
shells, stdout/stderr 1 MiB, input 10 MB, FS 100 MB / file 10 MB / 10K files, parser 5 s / 100K
fuel / depth 100); multi-tenant isolation per instance; `catch_unwind` around every builtin;
RealFs canonicalisation; 68 Unicode byte-boundary tests and zero-width rejection in paths. The
**explicit non-defences** are the point: "L-FS-002 | No file permission enforcement in the VFS |
Single-tenant virtual FS; permissions would be theater"; `sudo` "runs its command as the one sandbox
user" (L-SUDO-001); no outside signals (L-SIG-001); `exec` never replaces the process (L-PROC-001);
arithmetic never re-parses data as code ("a sandboxed agent shell must not execute text it only
read", L-ARITH-001, a stance); snapshots are integrity-checked with keyed HMAC APIs
(`docs/snapshotting.md:316-317`). Session caps exist too: `DEFAULT_SESSION_MAX_EXEC_CALLS` 1,000
and `DEFAULT_SESSION_MAX_COMMANDS` 100,000 (`limits.rs:407-411`).

**just-bash-py** inherits just-bash's limit *names* but only five of them, has no output cap, no
parser fuel, and no threat document; its security section is four bullets (`README.md:268-274`).
**lifo** says it plainly: the user/permission model is "a believable POSIX-ish model, not a
security boundary" (`ROADMAP.md`, phase 13); host escape hatches are planned "off by default".
**amla** claims the strongest boundary — wasm + WASI, "no network, no shell escape", every tool
call validated against `ToolCallCap(method_pattern, constraints, max_calls)` — but the runtime
that makes the claim is closed-copyleft and absent here `[NOT VERIFIED]`.

### F6. History and scars — what arrived after launch, in order (READ CHANGELOGs, issues)

**just-bash** (CHANGELOG from 2.14.3; repo born 2025-12-23). Minor-version arrivals:
3.0.0 "TS-enforced correct handling of utf8 on stdin. Impacts many commands" and executor plumbing;
3.1 sandbox capability flags; 3.2 `curl -G` and "shared aggregate budgets, liberal normal and
hardened profiles"; 3.3 `jq --arg/--argjson/--slurpfile`, user fds (`exec 3< file`, `read -u N`),
process substitution `<(cmd)`, `grep -f`, `grep -`; 3.4 `CommandContext.origCommand` so custom
commands can wrap the bundled one; 3.5 `diff` defaults to POSIX normal format (breaking),
`guarded-fetch` replaces bespoke SSRF code; 3.6 `mktemp` (with a new optional
`IFileSystem.createExclusive`), `yes` (finite: "pipeline stages here run to completion rather than
streaming"). Issues, most-commented and open (READ github, 2026-10-15): GPL dependency slipped in
(#176), accidental dependency pin exposed vulnerabilities (#210), UTF-8 mojibake via `cat`/`jq`
(#110, closed by 3.0), `js-exec` failing under Bun/Next.js (#159, #194), **"A pipeline stage cannot
end its producer: `rg … | head -4` scans the whole tree" (#415, open)**, `&>` to `/dev/stdout`
writes a file (#576), every redirect writes twice (#563), `read` mangles non-ASCII byte by byte
(#554), aborted exec loses output already printed (#515), overwriting resets mode to 0644 (#560),
chmod "does not consistently honor permissions" (#275), `ls -l` prints a hardcoded permission
column (#559), `timeout`/`xargs` drop the environment (#530), Windows support (#183), and three
remote-filesystem requests: `IFileSystem.searchFiles?()` hook (#185), async `getAllPaths()`
(#181), "expose command effect summaries for policy and audit layers" (#244). The recurring pain:
**bytes, streaming, permissions-as-metadata-only, and hosts wanting a search hook and an effect
summary**.

**bashkit** (39 releases, 2026-03-21 → 2026-10-15). 0.1.x: non-standard helper commands (`json`,
`yaml`, `log`, `assert`, `http`, `parallel`, `template`, `dotenv`); 0.6.0 **"MCP server mode
removed from CLI … The recommended path for MCP integrations is now to embed bashkit"**; 0.7
ripgrep parity (~80 PRs) and a host-owned `BuiltinRegistry`; 0.8 Python `open()` over the VFS;
0.9 keyed snapshot authentication, resource-safety sweep; 0.10 `grep -P`, DoS/panic audit;
0.12 `ExecOptions` request struct; 0.13 pluggable `HttpTransport`, `xargs -P`, eval on mira,
linear-time glob; 0.14 browser wasm package, generic mount namespaces, **"Unknown options are now
rejected like real Bash + coreutils"**; 0.14.5 `analyze()`; 0.15 content-addressed snapshot
history, C API; 0.16 **"Shell streams preserve arbitrary bytes end to end"**, "Execution
boundaries are typed, shared, and revocable", browser wasm over host-owned storage, `yq` replaces
`yaml`; 0.17 plain wasm component with no WASI, bounded work for every parsed input, sandbox
escapes closed at the host bridge; 0.18 `sed` rewritten after "a differential audit against GNU sed
4.9 found 46 mismatches"; 0.19 in-process terminals (`vi`, `less`, `nano`) and a `TerminalTool`,
CPython 3.14 in wasm, **concurrent pipelines with SIGPIPE**, symlinks, a default rootfs, awk
rewritten to gawk 5.2, 1,044 BashBox cases, Debian oracle scoreboard, gap telemetry, and
"resource refusals explicit" (PR #2452 "report resource caps instead of truncating silently").
Issues: early ones are bindings parity (Python/JS custom builtins, streaming callbacks, snapshots),
VFS mutations not persisting across calls in one session (#843), multi-hop stdin pipeline losing
data (#844), awk `print > "/dev/stderr"` writing a file (#802), Windows `touch` (#2388), and the
latest, "Support python and typescript interpreter for BashTool of langchain/deepagents" (#2702).

**just-bash-py**: `COVERAGE_AUDIT.md` lists what "silently fails" versus the TypeScript original
(`xargs -P` ignored …); `CLAUDE.md` "Known Issues: Single-quote variable expansion — Variables like
`$0` are expanded even in single quotes." Its README documents an agent-shell scar the TypeScript
original fixes in the lexer too: LLMs emit `&lt;`, `&amp;&amp;`; `unescape_html=True` by default
rewrites them in operator positions and leaves quoted/heredoc text alone (`README.md:242-266`)
`[NOT VERIFIED: whether the TS lexer's unescape is the same rule]`.

**lifo**: the 0.10.x changelog is about running Expo, Vite, Metro and tinbase (Postgres in the
browser) unmodified; 0.10.23 fixed `run()`'s `signal`/`timeout` being wired to nothing — and
because `run()` is a serial queue, "every command queued behind a long-running one … waited
forever". The roadmap's phases are benchmarks, a CLI, pluggable persistence with a WAL, a single
binary with per-VM resource limits, tunnelling, permissioned host escape hatches, embeddable UI,
package manager and wasm runtimes, a Web Worker VM, Dockerfile provisioning, users/permissions.

**amla**: the mirror has no history; the upstream monorepo is private-by-structure.

### F7. The consumers: what "a database answers the fs calls" looks like (READ web, 2026-10-15)

**Mintlify ChromaFs** (two posts). "ChromaFs is built on just-bash … It supports `grep`, `cat`,
`ls`, `find`, and `cd`, and exposes a pluggable `IFileSystem` interface. just-bash handles parsing,
piping, and flags, and ChromaFs answers the underlying filesystem calls." Backend: their existing
Chroma collection, where docs are already chunked for embeddings — `readFile` queries by page
slug, sorts chunks by `chunk_index`, joins. The directory tree is a gzipped JSON document
(`__path_tree__`) in the same collection, decompressed at init into a `Set` of paths and a `Map`
of directory → children, so "`ls`, `cd`, and `find` resolve in local memory with no network calls";
the tree is cached per site. `grep` is two-phase: grep flags (parsed with `yargs-parser`) become a
Chroma filter (`$contains` for fixed strings, `$regex` for patterns) as the *coarse* filter, the
matching chunks are prefetched into Redis, the grep arguments are rewritten to the candidate
files, and just-bash's in-memory grep is the *fine* filter. Lazy files: large OpenAPI specs in
customer S3 show in `ls`, fetched on `cat`. Access control: each entry carries `isPublic` and
`groups`; the tree is pruned with the session token before the agent sees it and the same filter
is applied to every Chroma query — "If a user lacks access to a file, that file is excluded from
the tree entirely." Writes: `writeFile`, `appendFile`, `mkdir`, `rm` all throw `EROFS` — "keeps
the system stateless, with no session cleanup and no risk of one agent corrupting another's view."
Numbers: P90 session creation **~46 s (sandbox, including a GitHub clone) → ~100 ms**; marginal
compute **$0.0137 → ~$0 per conversation**; a naive sandbox model "north of $70,000 a year" at
850,000 conversations a month; serving "hundreds of thousands of users and 30,000+ conversations
a day". Neither post states the tool schema shown to the model, versions, or any search beyond
grep. What they gave up: writes, history, ranked retrieval (they *replaced* RAG with grep), and
any permission finer than "in the tree or not".

**Convex sandbox**. "just-bash … a bash interpreter written to run inside a Node.js process", run
in a `"use node"` action. Persistence is split: "File contents live in storage" (Convex file
storage); metadata (path, size, sandbox id) in ordinary tables; contents are loaded lazily on first
read; writes, deletes and renames are collected in a change-set and flushed when the command
finishes; the cwd is saved on the sandbox record after each command ("a bit of a hack"). Clients
subscribed to the tables see the filesystem reactively. The agent gets one tool, "something like
`runBashCommand(command: string)`", described in the system prompt as a stateful terminal; failed
commands "surface their stderr just like a normal shell". No output cap; the action timeout bounds
the command. Stated limits: empty directories do not persist; a soft cap of ~1,000 files because the
action uses `.collect()`; mutations need auth hardening; no versions; no permissions; "an early-days
example". No kernel isolation, so unsuitable for untrusted binaries.

**Vercel bash-tool changelog** (2026-01-07, Malte Ubl and Andrew Qu). bash-tool is "the Bash
execution engine behind its text-to-SQL agent", open-sourced to "reduce token usage, improve
response accuracy". The thesis: "keep large context local, in a filesystem, and let the agent use
those commands to retrieve smaller slices of context on demand"; agents "tend to perform well with
Unix-style workflows such as `find`, `grep`, `jq`, and pipes". It "provides `bash`, `readFile`,
and `writeFile` tools" and runs in-memory or against `@vercel/sandbox` for a real VM. No rationale
is given for three tools; no limits are mentioned.

**justbash.dev** resolves to the package README ("Bash for Agents"); no playground, no
testimonials, no tool text beyond the bash-tool pointer.

**deepagentsjs `@langchain/node-vfs`**. Not a shell at all: a `BackendProtocolV2` over
`node-vfs-polyfill` (Vercel Labs' polyfill of the proposed `node:vfs`, nodejs/node#61478) where
"Native File Tools — `read`, `ls`, `grep`, and `glob` run directly against VFS data". The example
system prompt enumerates typed verbs: `ls`, `read_file`, `write_file`, `edit_file`, `grep`, `glob`
(`examples/sandbox/vfs-backend.ts:37-58`). bashkit ships the bridge the other way: a deepagents
backend whose `execute(command)` runs bashkit and returns `stdout + stderr` as one string
(`bashkit-python/bashkit/deepagents.py:276-279`). So the two agent frameworks that matter here
hold both shapes at once — typed verbs *and* a bash string — and nobody has unified them.

### F8. The 30-command experiment (EXECUTED; `corpus.sh`, `harness.py`, `out/results.md`)

Packages: `just-bash` 0.2.1 and `bashkit` 0.19.0 from PyPI, installed into a throwaway `uv run
--with` environment from the vfs root and executed with `python -I`; nothing imported vfs. Fixture
files were seeded through each constructor's `files=` map. One long-lived instance per engine, so
later commands saw earlier writes.

Result: **both engines ran all 30 commands**; 28/30 exited 0 in each, and the two non-zero are the
intended error probes (`cat /nonexistent` → 1, `nosuchcmd` → 127). Exit codes and error texts
match real bash: `cat: /nonexistent: No such file or directory`; just-bash-py says
`bash: nosuchcmd: command not found`, bashkit `bash: line 1: nosuchcmd: command not found`
(bash's `line N:` prefix). Pipes, heredoc-to-file, `for` with command substitution, arithmetic,
`if [ -f ]`, `jq`, `sed`, `awk -F,` with `END` sums, `cut | tr`, `uniq -c | sort -rn` all agree
byte for byte between the two engines and with what GNU would print.

Fidelity differences found (just-bash-py is wrong in each; bashkit matches GNU):

| # | Command | just-bash-py | bashkit |
|---|---|---|---|
| 24 | `mkdir -p /tmp/a/b && touch …/c.txt && ls -R /tmp/a` | `b` (recursion ignored) | `/tmp/a:\nb\n\n/tmp/a/b:\nc.txt` |
| 25 | `echo "a b c" \| xargs -n1 echo` | `a b c` (`-n1` ignored) | `a\nb\nc` |
| 26 | `printf '\x89PNG…' > f; od -c f` | `302 211 P N G …` (U+0089 as UTF-8, 11 bytes) | `211 P N G …` (byte 0x89, 8 bytes) |
| 30 | `grep -rn name /data --include=*.json` | `1:{…}` (filename omitted) | `/data/config.json:1:{…}` |
| 3 | `ls -la` | fixed `Jan 1 00:00`, owner `user user` | real mtime, no owner column |

The second probe (`probe2.py`) adds: bashkit's `command not found` carries agent-facing hints —
`docker ps` → `… command not found. Container and service management is not available in the
sandbox.`; `grpe foo` → `… Did you mean: free, grep, tree?` (Levenshtein ≤ 2, three suggestions;
`interpreter/mod.rs:905-975`, with a table for `pip`/`apt`/`npm`/`su`/`rsync`/`gcc`/`vi` …).
just-bash-py has no such hints.

### F9. The three distinctive ideas nobody else has (READ)

- **just-bash executor: one definition, three surfaces.** A tool registered as
  `"math.add": { description, execute }` is callable as `await tools.math.add({a,b})` inside
  `js-exec`, and as the bash command `math add a=2 b=3`, `echo '{"a":2}' | math add`, or
  `math add --json '{…}'` — "gh-style help, kebab-case, JSON/flag/stdin input", auto-discovered
  from GraphQL, OpenAPI, or MCP sources (`packages/just-bash-executor/README.md:38-60`).
- **bashkit `analyze()`**: a static report of every literal command name, argument, redirect target
  and function; anything containing an expansion is `null`; `eval`/`source`/`$cmd`/truncated walks
  set `isOpaque`. "If you gate on an allowlist, you must check `isOpaque`." "Analysis decides
  whether to ask; the sandbox decides what can happen." (`docs/script-analysis.md`.) Also the
  resolution order "shell function → POSIX special builtin → custom builtin → baked-in builtin →
  `$PATH`" so a host can shadow `cat` (`README.md:327-330`).
- **amla constraints on tool calls**: `ToolCallCap(method_pattern="stripe/charges/*",
  constraints=ConstraintSet([Param("amount") <= 10000, Param("currency").is_in([...])]),
  max_calls=100)`, enforced inside the runtime, and surfaced to the model as a `LIMITS:` block in
  the tool description (`capabilities/tool_call.py:1-30`, `langgraph.py:480-495`).

---

## Comparison table

| | just-bash | bashkit | just-bash-py | lifo | amla-sandbox |
|---|---|---|---|---|---|
| Language | TypeScript (Node ≥ 20.19, browser) | Rust (+ PyO3, NAPI, C ABI, wasm) | Python 3.11+ asyncio | TypeScript (browser, Node) | Python host + closed wasm runtime |
| Source size | 300k lines `.ts` (152k tests) | 299k lines `.rs` in core | 48.6k lines (34k tests) | 38k lines core (51k w/ tests) | 7k lines Python |
| Commands | ~82 dirs / README lists ~79 + `js-exec`, `python3`, `sqlite3`, `xan`, `yq` | 167 builtins (`rg`, `jq`, `yq`, `csv`, `git`, `sqlite`, `python3`, `ts` …) | 70+ (README) incl. `jq`, `yq`, `xan`, `sqlite3` | 60+ coreutils + `node`, `npm`, `npx`, `git`, `curl` | shell mode lists ~11 (`grep jq tr head tail sort uniq wc cut cat echo`) |
| FS backends | InMemoryFs (lazy files), OverlayFs (CoW over disk), ReadWriteFs, MountableFs; `IFileSystem` pluggable | InMemoryFs, OverlayFs, MountableFs, RealFs; `FsBackend` capsule; browser host storage | same four, Python | in-memory INode tree + IndexedDB; `NativeFsProvider`; `/proc`, `/dev` | in-memory VFS inside wasm |
| Runtimes | QuickJS (`js-exec`), CPython 3.13 wasm, sql.js | Monty, CPython 3.14 wasm, ZapCode TS, Turso sqlite, virtual git, ssh | none | JS via Node-compat layer (real npm, Vite, Expo) | JS inside wasm |
| Limits | profile table: normal vs hardened; 60-min deadline; 256/10 MiB output | 10K cmds, 10K/1M loops, 1 MiB out, 10 MB in, parser fuel, session caps | 5 counters, no output cap | `timeout`/`signal` only | 10K steps, 10 MB tool result, per-tool `max_calls` |
| Network | off; URL-prefix allow-list, GET/HEAD, header injection, `guarded-fetch` | off; per-domain allowlist, no DNS, pluggable `HttpTransport` | off; allow-list + SSRF ranges (`aiohttp`) | `curl` to virtual net + same-origin proxy | none |
| Tool contract | via bash-tool: `bash(command)`, `readFile(path)`, `writeFile(path, content)` | `BashTool`: `{commands, timeout_ms}` → `{stdout, stderr, exit_code, error, *_truncated, final_env}` | none shipped | none (human terminal, `Sandbox` API) | `sandbox(code, language)` → one string |
| Output cap seen by model | 30,000 chars + `[stdout truncated: N characters removed]` | 1 MiB + `stdout_truncated: true`; explicit per-builtin cap errors | none | none | fuel error line |
| Media | latin1 byte-string (`stdoutKind: "bytes"`) | `stdout_bytes` beside lossy `stdout`; `images` empty | none (UnicodeDecodeError) | inode has `mime`, `cat` decodes to text | n/a |
| Tests | 12,002 cases; 2,728 Oils bash cases (246 SKIP); 57 real-bash fixture files | 6,569 fns; ~4,090 own spec cases (1,044 BashBox); Oils 97.3% vs real bash; oracle scoreboards; 88-task LLM eval | 2,931; Oils 46% | 1,309 | 274 |
| Threat doc | `THREAT_MODEL.md`, 5 boundaries, residual-risk list | 801-row TM-ID model + L-ID limitations + per-ID tests | 4 bullets | "not a security boundary" | README claim; runtime closed |
| Licence | Apache-2.0 | MIT | Apache-2.0 | MIT | MIT / AGPL-or-BUSL runtime |
| Activity | 4.4k★, 468 commits, 85 issues, 1.5M wk downloads | 302★, 2,074 commits, 39 releases in 7 months | last commit 2026-06-04 | 544★, 424 commits | 346★, 17 mirror commits |

---

## What this means for vfs

### Copy as ideas (never code)

1. **Fidelity is measured against real bash, three ways.** Adopt all three tiers: (a) recorded
   fixtures from `/bin/bash` that the test asserts against (just-bash's `locked: true` JSON — the
   fixture is the oracle, bash wrote it); (b) the Oils `spec/` suite as an *outside* yardstick with
   real bash as the denominator and a pinned upstream commit, fetched not vendored (bashkit's
   "97.3% of what bash passes"); (c) a replay corpus of real agent sessions (bashkit's gap
   telemetry) — this is the brief's "corpus of real commands agents issue" and bashkit already
   built the harness shape: record every tool call, replay on a fresh instance, score by
   expectation checks over a snapshot. Our coverage number should be reported exactly as bashkit
   reports it: *N of M cases real bash passes*, per spec file, with the misses listed by cause.
2. **A negative spec with stable IDs.** bashkit's `L-<AREA>-<NNN>` rows ("what we deliberately do
   not do, why, and the test that proves the refusal") are the right home for "no `exec`", "no
   host signals", "no permission theater", "data is never re-parsed as code". vfs already has
   ADRs; the shell needs this table in the spec so an absent feature is a decision, not a gap.
3. **The tool contract shape.** One string in; `{stdout, stderr, exit_code}` out; a *visible*
   truncation marker; `error` as a separate field for "failed before running" (bashkit); exit 124
   on timeout; per-call `timeout_ms` optional. Keep stdout and stderr separate in the payload
   and merge only in the text rendering (both bashkit-deepagents and amla merge, and both lose
   the exit code in the process).
4. **Agent-facing `command not found`.** bashkit's hint table ("Package managers are not
   available in the sandbox", "Interactive editors are not available. Use echo/printf/cat to
   write files", `Did you mean: …`) is cheap and directly reduces wasted turns. vfs should hint
   with its own vocabulary: `docker` → "not a program here; the program table is `/bin`";
   `python` → "install it as an entry under `/bin` or ask the host".
5. **Static analysis before execution, advisory not boundary.** `analyze()`'s literal-or-null
   discipline and the `isOpaque` flag are the right primitive for the execution-policy ADR: the
   shell's parser reports what a command *statically* names; the host decides whether to prompt;
   the ladder decides what can happen. Partial reconstruction ("/tmp/" for "/tmp/$name") is
   deliberately refused — copy that refusal.
6. **Budgets and profiles, refusals explicit.** Both leaders converged on a limits table with a
   liberal and a hardened profile and on "report resource caps instead of truncating silently".
   vfs's `Result` already classifies errors as facts; the shell's overflow should be a classified
   fact on the row, never a silent cut (just-bash-py's silent `seq` at 100,000 is the anti-pattern).
7. **The `/bin` stubs and `--help`.** just-bash puts a stub for every command under `/bin` so
   `ls /bin` and `/bin/ls` work, and every command answers `--help`; bash-tool *discovers* the
   command set by running `ls /usr/bin …`. Our program table being a directory (Plan 9 style)
   satisfies this for free; `--help` per builtin should be a contract.
8. **One definition, three surfaces** (just-bash executor). A vfs verb, a host tool, or an
   installed program should be reachable the same way from the shell (`verb args`, `echo json |
   verb`, `verb --json`) and from a guest interpreter. This is the ABI ADR's seam.
9. **Hosts want two hooks**: a search hook (`IFileSystem.searchFiles?()`, just-bash #185 open,
   ChromaFs's two-phase grep) and an effect summary (#244, `analyze()`). vfs has both natively —
   `grep` *is* `storage.grep()`, and the ops vocabulary is the effect summary.

### Reject, with reasons

- **Three tools (`bash`, `readFile`, `writeFile`).** bash-tool's own README says bash "may be the
  only tool you need"; the shipped example passes only `bash`; `readFile` has no size limit and no
  error shape; `writeFile` returns `{success: true}` and loses the version. For vfs the typed
  verbs already exist as MCP tools with gates; the shell is a *projection* of them, not a parallel
  door. Ship `cli(command)` beside the verbs, not instead of them, and never a second
  `readFile` that bypasses `read`'s ladder (see the forks).
- **Text-only pipes and a latin1 "byte string".** Every peer retrofitted bytes after launch and
  still has no media type on the wire. vfs's unit of data is the row with `data` + `mime_type`;
  the pipe payload ADR should not regress to a byte string.
- **Permissions as inode metadata only.** just-bash's `chmod` "updates mode metadata but virtual
  filesystem access does not consistently honor permissions" (#275); bashkit refuses to pretend
  (L-FS-002); ChromaFs re-implements access control as tree pruning outside the shell. In vfs the
  ladder is in the data path and the shell must not grow a second one.
- **A `process.*`-style defense-in-depth layer.** It is specific to running untrusted script in
  the host realm. vfs's no-shell rule and capability-only programs make that layer unnecessary:
  the only door is the verbs.
- **An MCP server *inside* the shell package.** bashkit removed theirs in 0.6.0 ("embed bashkit"
  instead). vfs's MCP surface is the verbs; the shell is one of them.

### What vfs does that none of them do (stated carefully)

- **Permissions in the data path.** No peer enforces anything per principal inside the shell:
  just-bash modes are metadata (#275, #559, #560), bashkit declines by policy (L-FS-002), lifo says
  "not a security boundary", ChromaFs prunes the tree outside the shell with `isPublic`/`groups`,
  Convex has none. vfs: identity is a value on the call, every verb names its rung, and `grep` in
  the shell can only resolve to `storage.grep()` with the caller's authority (ADR 069, ADR 080).
- **Versions and trash.** No peer has either. bashkit has content-addressed *snapshots* (whole
  shell state, keyed HMAC), lifo tar.gz snapshots, Convex "no versions"; just-bash #174 "Tracking
  overlay changes after a command" is open. vfs rows carry `version`; `/.vfs` holds the trash view.
- **Ranked search (`glean`) and `graph`.** Every peer stops at `grep`/`rg` (ChromaFs explicitly
  *replaced* RAG with grep, and still needs Chroma's `$regex` as a coarse filter). vfs serves
  ranked search and traversal as verbs with the same authority as `read`.
- **Media rows and typed content.** lifo stores a MIME per inode and throws it away in `cat`;
  bashkit's tool contract reserves `images` and leaves it empty; just-bash hands the model latin1.
  vfs's `Observation` already carries `data` + `mime_type`, and MCP content blocks are the one
  wire target.
- **Rows in the pipe.** No peer's pipe carries anything but bytes-or-text. A `Result` of
  `Observation` rows flowing between stages (what nushell does with values) is not in any of them.
- **A real database with 10,000-file batches as a contract.** ChromaFs is read-only and caches
  the whole tree in memory; Convex caps at ~1,000 files via `.collect()`; the shells' VFS are
  in-memory trees. vfs's storage already chunks by dialect budget.

---

## Forks for the ADRs

**1. One tool `vfs(command)` versus several tools?**
Options: (a) one `cli(command)` tool; (b) `cli` plus the typed verbs as separate MCP tools; (c)
bash-tool's triad `bash`/`readFile`/`writeFile`. Evidence: bash-tool ships three but its README,
its shipped example (`tools: { bash }`), ChromaFs, and Convex all run on *one*; bashkit's contract
is one; deepagents is verbs only; amla optionally splits by *language*, not by verb. Why Vercel
ships three is undocumented (changelog gives no rationale) — INFERRED: `readFile`/`writeFile` avoid
shell quoting for large file bodies and give the AI SDK a typed `content` field, since the bash
tool caps output at 30,000 characters and quoting a multi-kilobyte file into `cat <<EOF` is
fragile. **Lean (b)**: the verbs already exist as gated MCP tools with typed rows (they are the
`readFile`/`writeFile` that bash-tool had to invent, with permissions and versions); add
`cli(command)` as the 26th tool that re-enters them. Never add a `readFile` beside `read`. Hosts
may expose only `cli` (the Vercel/ChromaFs pattern) by listing.

**2. Output cap defaults?**
Options: bash-tool's 30,000 characters per stream with a trailing marker; bashkit's 1 MiB bytes
with a boolean flag; just-bash's aggregate 256 MiB/10 MiB budget that *fails* the command. Evidence:
the only cap that was tuned for a model's context is bash-tool's 30,000 chars; bashkit's 1 MiB is
a resource cap, not a token cap, and the flag alone does not tell the model *how much* was lost;
just-bash's failure mode throws away the output entirely (#515 shows the pain). **Lean**: two
layers like just-bash-plus-bash-tool — a byte budget on the execution (a classified error fact,
work refused, not silently cut) and a *render* cap in the text projection, defaulting near
30,000 characters, with a marker that states characters removed and, because vfs has rows, *rows
remaining* and how to page (`head`/`tail`/`sed -n`, or the verb's own paging). The marker should
be one canonical string in `results/render.py`, not per command. Count bytes in the budget,
characters in the render cap.

**3. Ship a bash-compat corpus as our coverage metric?**
Options: (a) vendor the Oils `spec/` cases (Apache-2.0) as just-bash does; (b) fetch-not-vendor at
a pinned commit with real bash as the denominator, as bashkit does; (c) our own cases only; (d) a
replayed agent-session corpus. Evidence: just-bash-py shows (c) alone misleads (2,931 green unit
tests, 46% of the spec); bashkit's climb from 74% to 97% was *driven* by (b); (d) is the brief's
stated goal and bashkit has built the shape. **Lean**: (b) + (d), reported as two numbers — "cases
real bash passes that vfs passes" (parse-and-run, bash column, pinned Oils commit) and "fraction
of the agent corpus that parses and runs" — with a negative spec (stable L-IDs) for every refused
case, and the `## SKIP`-still-runs ratchet so a fixed case cannot stay skipped. The Toybox
ranking the brief names decides *which commands* enter the catalog; the Oils suite decides whether
the *shell* is bash.

**4. (Bonus, for the policy ADR) Static analysis as the prompt primitive?**
Options: none; just-bash's `CommandCollectorPlugin` (names only); bashkit's `analyze()`
(literal-or-null names, args, redirects, `isOpaque`). **Lean**: `analyze()`'s shape, produced by
our parser before `run`, with every command name resolved against the program table and the
ladder rung it would need; `isOpaque` maps to "deny or prompt".

---

## Sources

Clones (read 2026-10-15): `just-bash@9ab0e0d` — `README.md`, `THREAT_MODEL.md`, `AGENTS.md`,
`packages/just-bash/{README.md,CHANGELOG.md,AGENTS.npm.md,package.json}`,
`packages/just-bash/src/{types.ts,limits.ts,execution-output.ts,encoding.ts}`,
`src/interpreter/control-flow.ts`, `src/commands/cat/cat.ts`, `src/spec-tests/*`,
`src/comparison-tests/*`, `packages/just-bash-executor/README.md`, `examples/bash-agent/*`.
`bashkit@b7904a4` — `README.md`, `SECURITY.md`, `CHANGELOG.md`, `docs/{llm-tools,
script-analysis,snapshotting}.md`, `knowledge/{security/threat-model,operations/limitations,
operations/oils-spec,operations/eval,integrations/tool-contract,foundations/architecture}.md`,
`crates/bashkit/src/{tool.rs,limits.rs,interpreter/mod.rs}`, `crates/bashkit/tests/spec_cases/*`,
`crates/bashkit-python/{README.md,bashkit/*.py,src/lib.rs}`, `crates/bashkit-eval/README.md`.
`just-bash-py@48d111c` — `README.md`, `CLAUDE.md`, `COVERAGE_AUDIT.md`, `spec_test_results.txt`,
`src/just_bash/{bash.py,types.py}`, `tests/spec_tests/{README.md,KNOWN_LIMITATIONS.md}`.
`lifo@5a35d05` — `README.md`, `ROADMAP.md`, `PLAN.md`, `packages/core/{CHANGELOG.md,
src/sandbox/*.ts,src/commands/types.ts,src/commands/fs/cat.ts,src/kernel/vfs/types.ts}`.
`amla-sandbox@169384f` — `README.md`, `SECRETS.md`, `.mirror-deps.json`,
`src/amla_sandbox/{bash_tool,langgraph,sandbox,schema}.py`, `runtime/wasm.py`,
`capabilities/tool_call.py`, `examples/README.md`. `deepagentsjs@9f3bfd5` —
`libs/providers/node-vfs/README.md`, `examples/sandbox/vfs-backend.ts`.

Web (fetched 2026-10-15): https://www.mintlify.com/blog/how-we-built-a-virtual-filesystem-for-our-assistant;
https://mintlify.com/blog/chromafs; https://stack.convex.dev/convex-sandbox-persistent-bash-environment;
https://vercel.com/changelog/introducing-bash-tool-for-filesystem-based-context-retrieval
(2026-01-07); https://justbash.dev; https://github.com/vercel-labs/bash-tool and its raw
`README.md`, `AGENTS.npm.md`, `src/{index,tool,types,tools-prompt}.ts`,
`src/tools/{bash,read-file,write-file}.ts`; https://github.com/vercel-labs/just-bash (stats and
issue listings sorted by comments and by update); https://github.com/everruns/bashkit (stats, issues);
https://github.com/lifo-sh/lifo; https://github.com/amlalabs/amla-sandbox; third-party stats via
WebSearch: upd.dev mirror pages, depscope.dev/pkg/npm/just-bash (2026-07-27), the
FlorianBruniaux/claude-code-ultimate-guide evaluation (2026-08-04).

Executed: `experiments/s9/count_lines.sh` → `loc.txt`; `experiments/s9/harness.py` with
`corpus.sh` → `out/results.{md,json}` (just-bash 0.2.1, bashkit 0.19.0 from PyPI);
`experiments/s9/probe2.py` → `out/probe2.json`.
