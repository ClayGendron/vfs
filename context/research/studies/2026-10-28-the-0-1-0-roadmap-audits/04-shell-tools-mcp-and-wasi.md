# Audit: the agent shell, programs and the three tool kinds, the MCP adapter, the WASI Python runtime

- **Date:** 2026-10-28. Tree at `90f5883` (last three commits are `context/` docs only; code last moved at `ba77449`).
- **Method:** read-only. Every claim is labelled READ (I read the file), EXECUTED (I ran it here), or INFERRED (my reasoning). `src2/` and `tests2/` were not consulted.
- **One-line verdict:** nothing in this domain is built. The design is decided to an unusual depth (seven proposed ADRs, six drafted specs with counted criteria and a pre-build review each, one executed spike, two executed experiment sets), but the live tree has no `shell/`, no `mcp/`, no `views.py`, no Rust `shell` module, no `cli`, no placeholder, no `pending`, and still carries the retired `run` verb. Three places the decided record contradicts Clay's 0.1.0 themes: "no `ask` inside vfs" (ADR 084 pin 4) versus interrupts with a human in the loop; "a server's identity is the connection's" (spec 170 §3.1) versus MCP servers that authenticate as the user; "`serve()` only, no `vfs serve`" (spec 171 decision 7) versus "easy to serve".

---

## 1. Built today

### 1.1 What exists in `src/` (all EXECUTED unless noted)

| Item | Evidence | State |
|---|---|---|
| `src/vfs/shell/`, `src/vfs/mcp/`, `src/vfs/views.py` | `import vfs.shell` / `vfs.mcp` / `vfs.views` each `ModuleNotFoundError` | **missing** |
| `VirtualFileSystem.cli`, `VirtualFileSystem.bound` | `hasattr` both `False`; `hasattr(..., "run")` `True` | **missing** |
| Rust `shell` module (`TextKernel`, `UnsupportedForm`) | `ls crates/vfs-core/src`: `chunk grams lexical lexical_tables lib links postings python signals vectors verify` — no `shell.rs`; grep for `mod shell`/`TextKernel` empty (READ) | **missing** |
| The `run` verb | `ops.py:55` in `Op`; `ops.py:85` `EXEC_OPS = {"run"}`; `ops.py:103` in `ALL_OPS`; `ops.py:156` `VERB_RUNGS["run"] = Needs("read")` with the docstring "`run` waits for its own axis"; `base.py:1571-1587` the method; `base.py:3055-3057` dispatch to `SupportsRun`; `storage/protocol.py:346-356` the protocol, `:514` in `_FAMILY_OPS`; `storage/__init__.py:21,42`; `params.py:357-361`; `results/projection.py:57` default projection `("path",)`; `session.py:381` (READ) | **built, slated for removal** (ADR 082 pin 12; spec 167 slice A task 1) |
| No storage implements `SupportsRun` | README:19 says so; the only backends are `DatabaseStorage` and `InMemoryStorage` (`storage/backends/__init__.py:12`) (READ) | the verb is dead code |
| Tests pinning `run` | `tests/base/test_gates.py:172-190` (routing through a `RunnerStorage` double, no rights check), `tests/test_ops.py:97,176-180,225`, plus `test_params.py`, `test_dispatch.py`, `test_mounts.py`, `test_mount_admin.py`, `test_authority.py`, `storage/test_protocol.py`, `storage/test_memory.py`, `storage/database/test_reads.py`, `support/base_doubles.py` (READ via grep) | 12 test files touch it; spec 167 §1 item 2 lists the moves |
| `ops.py` docstring reserves `cli` | `ops.py:15-18`: "`cli` is deliberately absent: it is a meta-verb that parses a command string into these ops and re-enters through their public methods" (READ) | the contract is written, the code is not |
| `DEVELOPER_OPS` | `ops.py:98-102`: `sweep, posture, add_member, remove_member` "never registered on any agent-facing tool surface (MCP serve, CLI)" (READ) | built; spec 171's `AGENT_OPS = ALL_OPS - DEVELOPER_OPS` is not yet a constant. EXECUTED: `len(ALL_OPS - DEVELOPER_OPS) == 21` today (20 once `run` goes) |
| `/.agents` tree and `skills.py` | `paths.py:51-52` `AGENTS_ROOT = "/.agents"`, `AGENT_FAMILIES = {tools, skills}`; `paths.py:618-640` `tool_path`, `skill_path`, `tool_manifest_path`, `skill_manifest_path`; `paths.py:684-697` `is_reserved_directory`; `skills.py:1-20` writes `/.agents/skills/<name>/SKILL.md`; `models/entry.py` consults `is_reserved_directory` (READ) | **built, slated for retirement** (ADR 082 pin 6; spec 169a §a7: `Skill.to_entries(at=container)`) |
| The trash view `/.vfs/trash` | `base.py:1066,1113-1126`; architecture 11 names it as "the precedent for a derived view" (READ) | built; the only view today |
| Renderer | `render.py:42` `render_result(result, *, projection=None)` — no `budget`; `_render_read` `render.py:310-321` prints `content or ""`, so a bytes row renders as an empty body; grep for `binary`/`budget`/`placeholder` in `render.py` returns nothing (EXECUTED/READ) | gaps the shell depends on (spec 167 slice A items 3-5; ADR 085 pins 2-3) |
| Envelope wire | `envelope.py:723` `to_payload(self, *, exclude_none=True, max_errors=None)` — no `include_bytes`; `from_payload` `:753`; `to_json` `:795` (EXECUTED signature) | `to_payload` still inlines base64 unbounded when `data` is projected (memo §12 item 3) |
| Kinds | `results/kinds.py` has `unsupported`, `unrecognized`, `budget_exhausted`, `truncated`, `authority_budget`, `timeout`, `cancelled`; **no** `invalid.syntax`, `unsupported.construct`, `unsupported.form`, `pending`, `WASI_ERRNO` (READ via grep) | spec 167 B, 148, 169b each add some |
| Authority | `authority.py:65` `Narrowing` enum with one value `NONE`; `:40` `Provenance = edge\|constructed\|system`; `Authority.system()`, `Authority.anonymous()`, `is_system` (READ) | built; `authority_from_token`, `TokenVerifier`, `attested` provenance (spec 149) **missing** |
| Session | `session.py:36-429`: authority + lifecycle + one method per verb (incl. `run`); no `cwd`, `env`, `history`, `last_status`, `cli` (READ) | spec 167 §7 adds the four fields and `cli` |
| `deny_ops` | `base.py:869-884` masks mutating/exec ops, refuses read-family masks; `deny_ops=["jq"]` would be accepted and do nothing (spec 169 §a6) (READ) | built; ADR 084 pin 8 moves program masking to `Index.masked` |
| `_admitted` default-authority fallback | `base.py:3088-3100` (READ) | built; spec 171 §0 requires the wire never reach it |
| Optional extras | `pyproject.toml:49-65`: openai, langchain, embed-local, postgres, mssql, mariadb, oracle, pdf, docx, pptx, xlsx, documents, all. No `mcp`, `wasm`, `python`; no `[project.scripts]` (READ) | all three extras planned (170 §7, 169b §b1, 172 §1) |
| Docs | `docs/how-to/expose-over-mcp.md` is **6 lines**: a Diátaxis comment and a title, no body (READ, `wc -l`). README:19,61,96-103 still advertise the `run` verb and `/.agents/tools/<name>/`; README:116-134 "Where this is heading: MCP-native" describes spec 034's shape (READ) | stale against ADRs 082/084 |

### 1.2 What exists as executed research (not code)

- **The wasm program mechanism ran** (READ: memo 2026-10-15 §1, §6; study 10): a jq clone built for wasm, stored as an entry, resolved from a bin directory, run under wasmtime from Python with every file call served by vfs verbs, errno, trash, versions, timeouts, memory limits, a compiled-module cache, a three-stage pipe; shim 627 lines under `context/research/studies/2026-10-15-agent-shell/experiments/`.
- **The ABI and the two pipe laws ran** over the live `InMemoryStorage` (READ: ADR 083 context; `experiments/s3/abi_demo.py`, `s7/shell_session.py`).
- **Spike 173 executed 2026-10-16** (READ: spec 173 landing notes): CPython 3.14.8 + numpy 2.5.2 + pandas 3.0.6 as builtins, zero upstream patches, `import numpy` under the shim with zero `.so` opens; pandas CSV job 15 verbs / 93 SQL / 120 ms; verb door proven.
- **wasi-python 0.1.0 over vfs executed 2026-10-23** (READ: memo 2026-10-23 §3-§4): a pandas job, a mkdir/rename/remove cycle, a refused write into a read-only mount, a hidden `/.vfs`, a ladder-gated read (Alice refused, Bob granted) and three verb tools all ran through **today's public APIs of both projects with no change to either**; 40 verbs counted. The clone `~/Git/Repos/wasi_python` is **not present in this container** (EXECUTED: `ls ~/Git/Repos` fails), so I could not re-verify; the memo's `.out` files are the evidence.

### 1.3 Rating

| Piece | Rating |
|---|---|
| Shell (parser, pipe, `cli`, programs) | **missing** (design complete) |
| Renderer placeholder and cap; `to_payload(include_bytes=)` | **missing** (precondition gaps) |
| `run` retirement | **planned** (built thing to delete) |
| `/.vfs` views, index, resolution, install | **missing** (trash view is the one precedent) |
| Host tools as files (ToolView) | **missing** |
| MCP servers as views (McpView) | **missing**; spec says one small study owed (mostly done in review 15) |
| MCP adapter and `serve()` | **missing** |
| Token-to-authority edge (149) | **missing** (seed spec) |
| `pending` / interrupts (148) | **missing** (seed spec; contradicts ADR 084 pin 4 as written) |
| WASI Python guest | **planned**; mechanism **proven twice** (spike 173; memo 2026-10-23); spec 172 **stale** |
| Generic wasm host (169b) | **planned**; mechanism proven (study 10); whether still wanted is open (memo 2026-10-23 Q2) |
| Text kernels in Rust (168) | **missing** |

---

## 2. In flight: the specs and ADRs that touch this domain

All status lines are READ from the file headers on 2026-10-28.

### 2.1 ADRs (all "proposed", none ratified in code)

| ADR | Status line | What it decides for this domain |
|---|---|---|
| 081 the shell grammar | proposed 2026-10-15, amended the same day | twelve pins: a static bash-shaped POSIX subset parsed once; the refused list (pin 8); `set -e` with POSIX exemptions; `&` never; 32,768-character render cap; growth by slice (pin 12) |
| 082 programs, tools, the index | proposed 2026-10-15, amended | one ABI, six kinds, `/.vfs` views, `/opt/bin` index, resolution order and gating, `run` retired, `cat` never runs a tool, trust shown |
| 083 the pipe | proposed 2026-10-15, amended | rows or bytes per chunk, conversion only at a seam, errors never cross a byte seam, bounded queues, early close |
| 084 the execution policy | proposed 2026-10-15, amended | the gate order is the policy; executing is `read` on the entry (126/127); a program never holds more than its caller, **tools excepted**; **no `ask` inside vfs** (pin 4); the budget set (pin 5); masking (pin 8); kill exit codes |
| 085 the content channel | proposed 2026-10-15, amended | the placeholder; the cap; MCP's five blocks only; per-result budgets; `isError = not success`; minimal `resources`; `vfs:///` |
| 086 Python in vfs | proposed 2026-10-16, written on spike 173; pins 2, 5, 8 are leans pending Clay | static WASI CPython, yearly build by `wasi_python`; **pins 1, 2, 4, 6, 7 are now false per the 2026-10-23 memo** (§1 table) |
| 087 the kernel | proposed 2026-10-24; six leans pending Clay | fronts are facets; `cli`, the MCP tool surface and the WASI mount are fronts; rebase notes on 167, 171, 172 |

### 2.2 Specs

| Spec | Status line (READ) | What it would change |
|---|---|---|
| **167** the shell pipeline core | draft, cut 2026-10-15, amended by review 12 + Clay's eleven decisions; "Five slices, A to E, landing in order. The content of `0.1.0a1`. Not started. No open `[NEEDS CLARIFICATION]`." `tasks.md`: 20 tasks. Rebase notes 2026-10-24. | A: `run` out, placeholder, `budget=`, `to_payload(include_bytes=False)`, spec 155 markers. B: `shell/parse.py` + three kinds. C: `Program`/`Call`/`Fs`/`Forms`, `shell/run.py`, `shell/status.py`, `cli` on router and `Session`, the minimal programs. D: the forms table §4.1, `copy/move(overwrite=)`, `glob(case_mode=)`, `set -e`, the never table. E: harness + `docs/reference/shell.md`. |
| **168** text program kernels | draft; lands after 167 in three slices; "Not started. One `[NEEDS CLARIFICATION]` in §1" (base64/fold/paste/comm) | `crates/vfs-core/src/shell/` `TextKernel` seam; `head tail wc cut nl sed` move to Rust with the Python forms as oracles; `sort uniq tr tee` new; `xargs` and the `find -exec` rewrite; `diff cmp`; `awk`/`jq` refuse with hints until 169 |
| **169** programs, the index, the views | draft; lands after 167, three slices plus a post-171 section; "Not started. One `[NEEDS CLARIFICATION]` in §b8" (exit 134). **Narrowed 2026-10-23** (memo §6 item 4; ADR 087 consequences) to generic wasm for 169b | a: `VIEW_HEADS`, router `_views`, `/.vfs/bin`, `/.vfs/skills`, `Index`, union resolution, `application/wasm` by magic, install refusals, `/.agents` retired. b: a Python preview1 host (`shell/wasi/`), `WASI_ERRNO`, budgets, cache. c: `/.vfs/run`. After 171: uutils, jaq, a wasi awk, `vfs install`. |
| **170** tools and MCP servers as views | draft; "Lands after spec 169 and with or after spec 171 §2. Not started. **Needs one small study before it is built**, three pieces" (supervisor spike on 3.11/3.13; a real-server schema census; legacy servers under `mode="auto"`) | `ToolView` (`register_tool`, LangChain `BaseTool` by shape), `McpView` (`add_mcp`), the schema-to-flags table, the inbound block table and failure map, `_invoke`, `rungs_at`, the `mcp` extra; `SupportsRun` deleted |
| **171** the MCP adapter and `serve()` | draft; "Lands after spec 167; independent of 168–170. Not started." One marker in §3 already answered by a decided default. Rebase notes 2026-10-24. | `src/vfs/mcp/`: `serve(fs, *, transport, authority, token_verifier, host, port, tools, allow_open)`; `AGENT_OPS`; `input_schema(op)` from `PARAMS`; `ResultPayload`; `to_call_tool_result`/`from_call_tool_result`; `resources`; the `vfs:///` codec; errors-first rendering; vendored MCP schemas |
| **172** the WASI Python runtime | draft, rewritten 2026-10-16 on spike 173; waits on ADR 086's pending answers and on 169b. **Stale** per memo 2026-10-23 ("Everything in spec 172 about the build, the host, the door and the install is stale") | would shrink to: `VfsProvider(session, loop)` + `verb_tools(session)` + `run_async` with `RunBudgets` + the `python` kind; `vfs-py[python]` pinned to `wasi-python==0.1.0` |
| **173** spike | "executed and reported 2026-10-16"; GO on 1-4, 7 | done; its numbers feed ADR 086 and 172 |
| **148** sessions, narrowing, `pending` | seed, born 2026-09-06, "Not scheduled"; amended 2026-10-15: the four shell fields move to 167 §7; "`pending` maps to the MCP tasks extension's `input_required`"; close cancels | `Narrowing` content; child sessions; the `pending` kind with a request digest and TTL; the **ask ledger** (grant rows or one-shot allowances keyed by digest, written through the grant channel) |
| **149** `serve()` auth | seed, "Not scheduled"; amended 2026-10-15 by spec 171 (no sessions; authority per request; no token is anonymous) | `authority_from_token(claims)`; `TokenVerifier`; the system `sub` refused; **outbound: never forward the inbound token** (rule 4); **`pending` on the wire is MRTR `input_required`; "until an ask rung exists, served tools are `complete`-only"** (rule 5); the open-mount refusal |
| archived 027 embedded code execution | draft (archived) | QuickJS `exec` verb; superseded by ADR 086 pin 9 / spec 172 §6 |
| archived 034 MCP-native mounts | draft (archived) | two modes; spec 170 §5 separates them: a vfs-protocol server is a routing mount (roadmap 020, out of scope); any other server is a catalogue under `/.vfs/mcp`; `updatedb` materialization not taken |
| archived 039 execute tier | "closed as superseded, 2026-08-25" | dissolved by ADR 084 (no `execute` level, no rights set) |
| archived 045 verb wire contract | "cancelled and archived 2026-09-05" | the schema half is spec 171 §1 (`input_schema(op)` from `PARAMS`; a drift test) |
| archived 054 serve locks topology | "cancelled and archived 2026-09-05" | the one-line rule survives in 171 §0 (ADR 022): no served tool and no kernel program names a mount-admin verb |

### 2.3 Kernel specs that reach into this domain (rebase notes, READ)

174 (`>>` becomes `write(append=True)`; `touch` becomes `write("", if_absent=True)`; regex `sed -i` passes `if_version=`; the `write` tool gains `if_version/if_absent/append`), 176 (`ls`/`tree`/`glob` page at `ROWS_PER_CHUNK`; `--after/--limit`; the adapter sets `next_after`), 177 (replay table, `idempotentHint`, the `cli` description gains "a re-sent line runs again"), 178 (`head`/`tail` on a file operand read through `read(range=)`), 179 (`SupportsRun` leaves with whichever of 167/179 lands first), 180 (`versions` so the shell's `history` keeps its meaning), 181 (`ls -l` prints `owner_id`; `entry_id` in `columns`). The decided landing order for 174–181 is "in the order of harm" and precedes none of 167–172 explicitly; see Risks §4.9.

---

## 3. Gaps against the 0.1.0 themes

### 3.1 Theme 8: a fully functional bash-like CLI composing through the public APIs

**Decided meaning of "fully functional"** (READ: ADR 081 pins 1-12; spec 167 §2, §4):

- *Admitted at slice 1:* simple commands with assignment prefixes; pipelines with `!`; lists `; && ||` newline; `( )` and `{ }`; redirections `< > >> >| <> n> n>> n< <&m >&m 2>&1 &> &>>`; here-documents `<<` `<<-`; quoting (single, double, `$'…'`); tilde `~` `~/`; `$NAME`, `${NAME}`, the ten POSIX `${…}` operators; `$? $# $@ $* $0-$9`; `$( )` and backticks; field splitting; `* ? [ ]` globs and `{a,b}` `{1..3}` brace expansion (textual, first, in the shell); `set -e` with POSIX exemptions; `time [-p]` as a builtin.
- *Refused at slice 1, by name, as `vfs.unsupported.construct` before anything runs:* `if for while until case` and closers, functions (both spellings), `[[ ]]`, `$(( ))`, `(( ))`, `select`, `coproc`, `<( )`, `>( )`, `<<<`, `|&`, `{var}>`, arrays, `${x/a/b}`, `${x:1:2}`, `${!x}`, `${x@Q}`, extended globs, `~user`, and `&` ("refused forever"). `shopt eval exec trap source .` and `alias` are `unrecognized` (127).
- *Growth:* slice 2 admits `for if while until case break continue [[ ]]`; slice 3 functions, `local`, `return`, `$(( ))`; slice 4 by corpus evidence above about 1%. The measured corpus (12,627 calls) parses 86 of 100 weighted commands at slice 1, 91 with `for`.
- *Malformed text* is `vfs.invalid.syntax` with `line`, `column`, `offset`, `construct`, `expected`, `incomplete` and a caret in the display.

**Slice order** (READ spec 167): A renderer and vocabulary; B parser (A and B independent); C the pipe, the ABI and `cli` with the minimal programs; D the program forms (`overwrite=`, `case_mode`, `set -e`, the never table); E the harness and docs. C and D run the four engine legs before landing.

**Budget constants, all declared** (READ ADR 084 pin 5; specs 167 §2/§5/§7, 169 §b8/§c1, 171 §2.2, 170 §3.3): `STAGE_BUDGET` 64; `ARGV_BYTE_BUDGET` 128 KiB; `FANOUT_BUDGET` 10,000; `STDOUT_BYTE_BUDGET` and `STDERR_BYTE_BUDGET` 4 MiB per stage; `WALL_TIME_BUDGET` 10 s per line (exit 124); `FUEL_BUDGET` 2×10⁹; `VERB_CALL_BUDGET` 10,000 (exit 137); `MEMORY_BYTE_BUDGET` 256 MiB; `STAGING_BYTE_BUDGET` 256 MiB (`FBIG`); parser `INPUT_BYTE_BUDGET` 1 MiB, `TOKEN_BUDGET` 100,000, `DEPTH_BUDGET` 200, `ITERATION_BUDGET` 1,000,000; pipe `ROWS_PER_CHUNK` 1,000, `BYTES_PER_CHUNK` 64 KiB, `QUEUE_DEPTH` 2; `RENDER_CHARACTER_BUDGET` 32,768 (stderr kept whole to 4,096); `HISTORY_ENTRIES` 1,000, `HISTORY_PATHS_PER_ENTRY` 256; `RUN_RETENTION_CALLS` 64, `RUN_RETENTION_BYTES` 64 MiB; wire: 1 MiB per block, 4 MiB per result, 8 blocks, `LINK_BUDGET` 64, `PAYLOAD_ERROR_BUDGET` 100, `RESOURCE_READ_BYTE_BUDGET` 12 MiB; `MCP_LIST_FLOOR_MS` 30 s; `WASM_CACHE_BYTE_BUDGET` 1 GiB.

**Exit-code table** (`shell/status.py`, READ 167 §3, 168 §1.5, 169 §b8): 0; 1 any verb failure inside a builtin; 2 usage/unknown flag/`unsupported.form`; 123 `xargs` child failed; 124 `vfs.timeout`; 126 known but cannot run (`unsupported`, masked, cannot `read` the entry, not a wasm module); 127 unknown name / cannot `list`; 130 `vfs.cancelled`; 134 guest abort; 137 fuel, memory or verb-call kill.

**Which program is which kind** (READ 167 §4, 168 §1.3, 169 final section):

- *Verb builtins (167 C/D, Python over verbs, produce rows):* `cat ls glob grep rg find tree stat file mkdir rm cp mv touch restore glean graph`; `-exec`/`-delete` on `find` wait for `xargs` (168b).
- *Shell builtins (167):* `cd pwd echo printf export unset env printenv set -e true false : exit test [ which type command -v help sleep timeout time date basename dirname seq whoami hostname uname history`.
- *Read-shaped text forms, Python in 167, Rust kernels in 168a behind the same names:* `head tail sed wc cut nl`.
- *New Rust kernels (168):* a `sort uniq tr tee`; b `xargs` (a runner builtin) and the `find -exec` rewrite; c `diff cmp`.
- *Installed wasm programs (169, after 171):* `awk` (371 measured uses, 213 of the 357 tier-2 calls), `jq` via jaq, uutils' `feat_wasm` set (`tac join expand unexpand od base32 md5sum sha*sum cksum split csplit yes pr fmt tsort numfmt shuf`), plus `base64 fold paste comm` leaning there.
- *Never (127 with a hint):* `uv git docker ps sudo chmod`, `python3` until 172, `source . alias eval exec trap shopt`, the developer-plane verbs; `curl wget` are `unsupported` 126. Verbs with no Unix name (`edit mkedge rmedge grant revoke grants`) are `unrecognized` with a hint naming the verb tool. `write` is never a program name (`>` and `>>` only).

**Realistic 0.1.0 cut** (INFERRED from the measured shares in 167/168): spec 167 A-E alone covers about 87% of measured segments; 168a adds the four most-used missing text programs (`tr` 132, `tee` 105, `uniq` 87, `sort` ~200 measured flag uses) and the Rust move for six names; 168b (`xargs`, 52 uses) is what makes `find -exec` and rows-to-verb work and is the one explicit rows form; 168c (`diff`/`cmp`, 30 uses) can slip. `awk` is the single largest hole and is blocked on a wasm host (169b), see §6 Q6.

**Gap summary for theme 8:** everything. Dependency chain inside the theme is A/B → C → D → E, then 168a → 168b.

### 3.2 Theme 7: everything is a file, including tools, under one permission structure

Decided (READ ADR 082 pins 6-11, ADR 084 pins 2, 7, 8; spec 169a; spec 170 §5.1):

- Tools are files at `/.vfs/tools/<name>` and `/.vfs/mcp/<server>/tools/<tool>`; programs are files anywhere on the index (default `/opt/bin`); skills are directories on the skill index; everything callable is listed under `/.vfs/bin` with `callable_kind` and `resolved`.
- One permission structure: executing or calling is **`read` on the entry** (126 if `list` only, 127 if below `list`), issued on every run; installing is `write` under the ladder (`add` on `/opt/bin`, which the host mints at posture `read`); masking is `Index.masked` (not `deny_ops`); tool and MCP entries "follow the regular posture rules at their paths, no special default".
- The machinery that makes a catalogue entry obey the ladder without a stored row: `SupportsGrants.rungs_at(paths, *, authority)` (spec 170 §5.1), a new chunked statement shape with the four engine legs; policy rows for `/.vfs` paths live in the root binding's grants table (169a §a1).
- **Stated plainly in 170 §5.1 and worth Clay's eye:** on a fresh node (posture `read_write` at `/`) **anyone, anonymous included, can call every host tool and every MCP tool**, and a host tool runs with the host's authority. The host locks it with two `posture(..., "list")` lines. See §6 Q4.

Gaps: 169a (views, index, union, install refusals), 170 (`ToolView`, `McpView`, `_invoke`, `rungs_at`), 169c (`/.vfs/run` so program output has an address). `cat` of a tool never runs it (ADR 082 pin 13) — decided, pins the "read never executes" half.

### 3.3 Theme 4: three tool kinds, all interruptible — mapped onto ADR 082's six kinds

| Clay's kind | ADR 082 kind(s) | Spec that lands it | Decided permission | Decided identity the code runs under |
|---|---|---|---|---|
| (a) host-program tools, LangChain-shaped | kind 4 **tool** | 170 §1 (`register_tool`, LangChain `BaseTool` accepted by shape: `name`, `description`, `args_schema`, `ainvoke`) | `read` on `/.vfs/tools/<name>`; `vfs.invalid` exit 2 before any call on bad args; `ToolError` → exit 1; plain exception → exit 1 generic stderr; deadline → `vfs.timeout` 124 | **the host's own authority** (ADR 084 pin 3's one exception), receiving the caller's `Fs` only if it declares a parameter typed `Fs`; the trust line in `type` says "runs on the host, may reach the network" |
| (b) mounted MCP servers that authenticate as the user | kind 5 **MCP tool** | 170 §3 (`add_mcp(name, server=, credentials=)`, `McpView`), with 171 §2.6 `from_call_tool_result` | `read` on `/.vfs/mcp/<server>/tools/<tool>`; the failure map of 170 §4 (`-32602`→`invalid` 2; `-32601`→`not_found` 127; elicitation/`-32021`→`unsupported` 126; transport→`unavailable.backend` 1; wall→`timeout` 124) | **the connection's one credential, configured by the host** (170 §3.1: "A server's identity is the connection's: every vfs caller who may call its tools acts through the one credential the host configured. `tools/list` is therefore one list per server, not per caller."). **Not as the user.** |
| (c) CLI tools embedded or installed in vfs | kinds 1 **verb builtin**, 2 **text program** (embedded); kind 3 **program** (installed `.wasm`); kind 6 **skill** (read only); the `python` kind (172) | 167, 168 (embedded); 169a/b, the post-171 section, 172 (installed) | embedded: the verb's own gate on every call; installed: `read` on the entry (126/127), install at `add` | **the caller's authority, never more** (ADR 082 pin 2, ADR 084 pin 3: `Fs` is the verb set curried with the caller's `Authority`; a type boundary for sandboxed kinds, a review discipline for Python builtins) |

**"MCP servers authenticating as the user" — where decided or not (READ):**

- *Decided against, at v1, for catalogue servers:* spec 170 §3.1 (quoted above); credentials are per-server config passed to the transport, never `os.environ`; `remove_mcp` is the credential-rotation path (review 15 line 226).
- *Decided for the other direction only:* spec 149 rule 4 is about a **remote vfs mount** (a server speaking the vfs protocol, roadmap 020): "never forward the inbound token; trusted subsystem (backend authenticates as itself, sends verified names as data) or RFC 8693 token exchange". That is not McpView.
- *Named but deferred:* spec 149 non-goals: "Cross-app access, CIBA, token vaults: enterprise follow-ups the seam must not preclude." ADR 062 context mentions Entra OBO and RFC 8693 `act`.
- *Not decided anywhere:* per-caller MCP connections; a credential store keyed by principal; the MCP 2026-07-28 client-side OAuth 2.1 authorization flow (which needs a browser round trip, i.e. a human in the loop — an interrupt); whether `tools/list` is per caller when identity is per caller; pass-through of the served HTTP bearer token to an upstream server (which 149 rule 4's spirit forbids and RFC 8707 audience binding would refuse anyway, INFERRED).
- *Consequence:* theme 4(b) needs a new ADR and a story (§5 S12). The seam 170 draws (`credentials=` per server, one supervisor per connection) does not preclude it but does not provide it.

**Interrupts and human-in-the-loop — reconciling ADR 084 pin 4 with Clay's requirement (READ + INFERRED):**

What the record says today, in one place each:

1. ADR 084 pin 4: "**No `ask` inside vfs.** vfs allows or classifies. A host that wants a human in the loop uses its own tool-permission layer; the static parse of ADR 081 gives it an exact summary of which programs, verbs and paths a call names before anything runs."
2. Spec 148 rule 5: a verb the grants refuse but a principal could allow answers a `Result` with a `pending` record (digest of verb + canonical arguments + authority shape + grant revision, plus a TTL); answers are grant rows or one-shot allowances in an **ask ledger** keyed by digest, written through the grant channel, never through the session; a re-run with a live allowance proceeds once. Amended 2026-10-15: `pending` maps to the MCP tasks extension's `input_required`.
3. Spec 149 rule 5: `pending` on the wire is MRTR `input_required` with an integrity-protected `requestState`; "until an ask rung exists, served tools are `complete`-only."
4. Spec 170 §4: an elicitation request from a mounted server is `vfs.unsupported`, exit 126 ("no ask inside vfs, ADR 084 pin 4"); McpView passes no elicitation callback.
5. Spec 171 scope: MRTR (`input_required`) and tasks are out.
6. MCP memo 2026-08-10 §8.5: the one interactive primitive vfs might want "maps to MRTR elicitation, but ADR 027 (delete never destroys) was designed precisely so no verb on the agent surface needs a confirmation gate... stay `complete`-only until a concrete need exists."
7. Mirage memo §4.3 (adopted as a recommendation, never built): an ask is `vfs.permission_denied.pending` with `data['vfs.ask_id']`, `retry_class=refresh`, and one ledger record type for pending and settled with `scope ∈ {once, session}`.

The reconciliation that keeps every pin honest (INFERRED): "no `ask` *decided* inside vfs" stays true — the kernel never blocks a call waiting on a human, never auto-rejects on timeout, and never decides the answer. What Clay asks for is that vfs *carry* an interrupt as a first-class, resumable, classified outcome. Spec 148 already has the shape (`pending` + digest + ledger); it was deferred, not refused. ADR 084 pin 4 needs one amending sentence: "vfs never asks; a tool, a server or a grant check may *suspend* a call into a `pending` `Result` that a host answers through the ledger." The MCP memo's "until a concrete need exists" is answered: the need is themes 1 and 4.

What an interrupt looks like per tool kind, and whether the pipe can suspend:

- **Host tool (kind 4).** The function raises an `Interrupt(payload)` (LangChain's `interrupt()` shape: a JSON-serialisable question, resumed by re-running the node with the answer). The `_invoke` door catches it and mints one error `vfs.pending` on the stage's `Result` with `data = {digest, ttl, payload, stage, program}`. The stage ends with a new row in `shell/status.py` (proposal: **75**, sysexits `EX_TEMPFAIL`, "temporary failure, try again later" — nothing in bash's 124/126/127/128+n says "waiting"; see §6 Q2). Resume: the host writes an allowance keyed by the digest (one-shot) or a grant, then re-issues the same `cli` line or tool call; the door finds the live allowance, passes the answer to the tool as its resume value, and the stage runs. This is exactly LangChain's model: the interrupted node re-executes from its start on resume, so a tool must be written so its pre-interrupt side effects are idempotent (spec 177's replay table makes vfs's own verbs so).
- **MCP server elicitation (kind 5).** Under 2026-07-28 the server answers `tools/call` with `resultType: "input_required"` carrying `inputRequests` (an `ElicitRequest`) and an opaque `requestState`; the client answers by retrying the original request with `inputResponses` + `requestState` (MCP memo §3). vfs as client: the supervisor task maps that result to `vfs.pending` with `data = {digest, inputRequests, requestState, server, tool}` instead of 170 §4's `unsupported` 126; on resume with a live allowance whose answer is the `inputResponses`, vfs re-sends `tools/call` with the state attached. For a legacy (2025-06-18) server elicitation is a server-to-client request mid-call; vfs can either keep refusing it (`unsupported`) or hold the call open only for an in-process `Session` caller. MCP's own rule "MRTR retry results MUST NOT be cached" matches the ledger's one-shot scope.
- **A shell pipeline suspended mid-stage (kinds 1-3).** The pipe is one asyncio task per stage with `asyncio.Queue(maxsize=2)` seams, Rust `TextKernel` objects holding partial lines, materialising `sort`s, and wasm guest instances with staged buffers (ADR 083; specs 167 §5, 168 §2, 169 §b8-b10). None of that state is serialisable, and the wire's `cli` is stateless by decision (167 decision 4; 171 decision 2). So **the pipe/ABI design cannot suspend and resume a pipeline across calls**; an interrupt must end the `cli` call with a resumable `pending` `Result`: the pending stage stops, producers upstream are cancelled at their next emit as `vfs.cancelled` info (ADR 083 pin 10), stdout already emitted is kept (as the `timeout` rule already does, 167 §5), the `Result` carries `pending` with the stage index and the exact program and argv, `exit_code` 75, `statuses` with the stage marked. Resume re-runs the whole line; statements before the pending stage run again, which is safe exactly where spec 177's replay contract says it is (and the `cli` description already gains "a re-sent line runs again"). Two refinements are possible without changing the design: (i) in process, `Session.cli` may hold the suspended pipeline as a live awaitable for a Python host (Jupyter) that answers in the same process — an option on `Session`, never on the wire; (ii) once `/.vfs/jobs` and the MCP tasks extension land, a suspended line becomes a task in status `input_required` and resumption is `tasks/update` — the shape ADR 081 pin 12 and memo §9 already reserved for long-running work. Both are later than 0.1.0 (INFERRED).
- **Grant-refusal interrupts (any kind).** Spec 148's original case: a verb refused by the ladder that a principal could allow. The `cli` renders it as the stderr line plus the `pending` error; the digest is the verb, canonical arguments, authority shape and grant revision; a `grant` row or a one-shot allowance admits the re-run. This is where "one permission structure" and "interrupts" meet: an interrupt is a *classified refusal that names its own remedy*.

Open for Clay: whether `pending` is a child of `permission_denied` (Mirage's lean, degrades gracefully for old consumers) or a top-level kind (spec 148's wording); the exit code; where the ledger lives (storage per mount, or the router — spec 148's open question); the TTL. See §6 Q1-Q3.

### 3.4 Theme 6: easy to serve vfs as an MCP server

Planned surface (READ spec 171): `tools/list` = `(fs.capabilities() & AGENT_OPS) | {"cli"}` ∩ `tools` — 21 tools on the default router after `run` goes (20 verbs + `cli`), 19 on an unknown dialect, 1 with `tools={"cli"}`; input schemas projected from `PARAMS` (never from signatures: `func_metadata` fails on 7 of 20 verbs and exposes `authority` on 13); `authority`, `observations`, `provenance` withheld; `outputSchema` = `ResultPayload`; `readOnlyHint`/`destructiveHint` derived from `ops.py`; the `cli` tool `{command | argv, workdir, timeout_ms}`, fresh shell per call, `timeout_ms = min(…, 10 s)`; one `TextContent` first then typed blocks; `structuredContent` carries the shown rows plus one truncation warning; `resources` minimal (`vfs:///{+path}`); the 2,300-character `cli` description in the appendix.

Auth edge (READ 171 §0, 149): streamable HTTP → `authority_from_token(get_access_token())`; no token → `Authority.anonymous()` judged by the ladder; invalid token → HTTP 401 `vfs.unauthenticated`; stdio → `serve(authority=…)` once; a handler never passes `authority=None` (spy test); the system actor refused before binding a transport, both as the stdio authority and as `fs.default_authority`.

Open-mount refusal: `serve()` refuses to start while any bound mount's posture is `open` unless `allow_open=True`, naming the mounts (149; 171 §0; `docs/explanation/open-in-process-loud-at-the-edge.md` says "Not yet built").

Transport: `transport: Literal["stdio", "http"]` over the official `mcp` SDK (`mcp>=2.3,<3`, `mcp-types` 2.x, speaking 2026-07-28 and the legacy handshake); `Server(cache_hints=…)` because the SDK rejects a `tools/list` without `ttlMs`.

One-line entry point: **decided against at v1** — 171 decision 7: "`serve()` only at v1. No `vfs serve` command"; the reason given is that a console command "needs a way to build the router (a database URL, mounts). Nothing in the spec says how" (review 16 line 184). There is no `[project.scripts]` in `pyproject.toml` (READ). So the honest one-liner today would be `await serve(fs, transport="stdio", authority=Authority.of(me))` inside a Python file, not a shell command. Theme 6 asks for more; see §5 S13 and §6 Q5.

What 171 excludes that themes 1/4 need: MRTR `input_required` and tasks (§3.3), a sealed `cli` session handle (so `cd` persists across calls), `listChanged`.

### 3.5 WASI Python (specs 172/173): 0.1.0 item or later — the evidence

- EXECUTED by the record, not by me: spike 173 (2026-10-16) built and ran the static CPython over vfs's shim; the 2026-10-23 memo ran wasi-python 0.1.0's own runner over a vfs `Session` through **public APIs only**, 40 verbs, no change to either tree, the ladder reaching the guest (Alice/Bob), refused writes recorded, `/.vfs` hidden.
- Size (READ memo §1 table): the `wasi-python` wheel is about **94 MB download, 250 MB unpacked**; the artifact set rides in the wheel (`wasi_python.artifacts()`), so **nothing needs to be a vfs row** and the vfs wheel budget is untouched (spec 166 amendment 2026-10-16).
- Package set (READ): CPython 3.15.0, numpy 2.5.2, pandas 3.0.6, scipy, scikit-learn, statsmodels, matplotlib, sqlite3, bz2, lzma plus about forty pure-Python packages — far beyond ADR 086 pin 1.
- What vfs still has to write (READ memo §6 items 1-3): `WASI_ERRNO` (24 kinds map one-to-one onto wasi_python's `Errno`, EXECUTED there); `move(replace=)`; the `python` program kind as a thin adapter — `VfsProvider(session, loop)` (eight provider methods, hidden tree, errno map, text-or-bytes write-back rule, a per-run stat/body cache) and `verb_tools(session)`; `RunBudgets` mapped field by field onto `deadline_s`, `memory_bytes`, `fuel`, `max_file_calls`, `max_tool_calls`, `output_bytes`; `trapped` mapped onto 124/137/134; `files.refused` folded into the stage.
- Known costs (READ memo F9-F11): two `write` verbs and two versions per guest-created file; `os.replace` fails `EEXIST` until `replace=` lands; matplotlib needs a writable `HOME`.
- Guest-side API at v1: `from host import tools` with tool names equal to verb names; `import vfs` inside the guest needs a wasi_python change (read-only mount `import_path`) — Q1 of that memo, pending Clay.
- Verdict (INFERRED): the mechanism is proven and the remaining work is a medium adapter, so the Python guest **can** be a 0.1.0 item behind `vfs-py[python]`; it needs 167 C (the `cli`/ABI it plugs into), 169a (name resolution for `python3`), the ADR 086 amendment, and a rewrite of spec 172. The generic wasm host (169b, our own preview1 shim) is a separate, larger question (Q6).

---

## 4. Risks: wrong, stale or contradictory

1. **ADR 084 pin 4 / 149 rule 5 / 170 §4 / 171 scope / MCP memo §8.5 versus themes 1 and 4.** The record says no `ask`, complete-only tools, elicitation refused as `unsupported`. Clay's 0.1.0 wants interruptible tools with a human in the loop. Needs an ADR amendment and a story (S11) before 170 and 171 are built, or both will have to be reopened. (READ)
2. **Spec 170 §3.1 versus theme 4(b).** "A server's identity is the connection's… one list per server, not per caller." Per-user MCP identity is undecided (§3.3). Building McpView as drafted and retrofitting per-caller connections later changes the supervisor model (one task per server) and the listing cache. (READ)
3. **Spec 171 decision 7 versus theme 6.** No `vfs serve` and no `python -m vfs.mcp`; the reason (no router-construction story from a URL) is real and belongs to another domain (storage/host configuration). (READ)
4. **Default is wide open for host tools.** Spec 170 §5.1: on a fresh node anyone, anonymous included, calls every registered tool, which runs with the host's authority and may reach the network. Accepted in the spec with a two-line lock; a `list` default posture for `/.vfs/tools` and `/.vfs/mcp` would invert it. (READ; recommendation INFERRED)
5. **ADR 086 and spec 172 are stale against wasi-python 0.1.0** (memo 2026-10-23 §1): pins 1, 2, 4, 6, 7 false (package set, toolchain, rows under `/opt`, our own host, a `vfs` package in the zip). Architecture 11's Python-guest diagram is drawn from the memo (correct), but the "landing order" there still says 169b before 172 and `/opt/bin/python3.wasm` appears in ADR 086 pin 4. Spec 169b's own status does not yet say it is narrowed. (READ)
6. **README is stale on this domain:** advertises the `run` verb (lines 19, 61, 99, 103), `/.agents/tools/<name>/` (96), and spec 034's "MCP-native" direction (116-134). `paths.py:8-17` documents `/.vfs/mounts/data.json`, which `ls /.vfs/mounts` answers `not_found` (memo §12 item 9). (READ)
7. **`docs/how-to/expose-over-mcp.md` is a 6-line stub** with a title and no steps. If mkdocs lists it, it is a published empty page. (READ)
8. **A built contract asserts the opposite of ADR 084 pin 2:** `tests/base/test_gates.py:182-190` pins that a mount declaring `run` executes with no rights check; `VERB_RUNGS["run"]` is read by no gate (memo §12 item 5). Harmless only because no storage implements `SupportsRun`. Removed by 167 A. (READ)
9. **Ordering between the kernel specs (174-181) and the shell specs.** 167 §5 admits `>>` as a racy read-then-write and `touch` as `stat`-then-`write`; the rebase says 174 replaces both. 167 C/D also pre-date 176 (paging), 178 (`head`/`tail` by range) and 181 (`owner_id`). If 167 lands first it ships known-racy forms and then changes; if 174-181 land first, 167 waits on eight specs. Clay has not ordered the two families against each other. (READ; INFERRED risk)
10. **Naming drift:** 167 and 169 say `overwrite=`; ADR 087 pin 3 and spec 181 say `replace=`; pin 17 (which identity survives) is a lean pending Clay. The WASI provider's `rename` and the shell's `mv` both wait on it. (READ)
11. **`/.vfs/run` records are router memory** (169c): lost on restart, not shared across processes. An HTTP `serve()` with more than one worker would mint `vfs:///.vfs/run/<id>/…` links that another worker cannot read. Named as a future in the spec, but it bites the wire first. (READ; INFERRED)
12. **SDK version pins are speculative:** 171 pins `mcp>=2.3,<3` and `mcp-types` 2.x (2026-07-28 revision); 170 lists a heavy dependency closure (starlette, uvicorn, sse-starlette, pyjwt+cryptography, opentelemetry-api, httpx2, jsonschema; pydantic ≥ 2.12). Re-verify at build; the memo's 8.6 says "the tasks question and the stack question are the same question" and deserves its own pass if tasks come in with interrupts. (READ)
13. **Spec 170's `rungs_at`** is a new chunked statement shape (one per `membership_budget` slice) with four engine legs; it is the only piece of 170 that touches SQL and it gates the 126/127 split for tools. (READ)
14. **Several exit-code producers, one table.** 167 (0/1/2/124/126/127/130), 168 (123), 169 (134/137), and a possible 75 for `pending` (this audit). Fine as long as `shell/status.py` stays the one table and ADR 084 pin 9's kind list is amended for `pending`. (READ)
15. **Spec 170's "one small study" is mostly done** in review 15 (flag table from executed schemas, error map, client lifecycle); what remains is the supervisor spike on 3.11/3.13 and two censuses, "an afternoon each". The spec header still says "needs one small study before it is built". (READ)
16. **Reference clone absent here.** `~/Git/Repos` does not exist in this container, so neither `wasi_python` nor the MCP SDK could be re-read; everything about them is READ from the memos. (EXECUTED)

---

## 5. Proposed roadmap stories (dependency-ordered)

Sizes: S ≤ 1 day, M 2-4 days, L 1-2 weeks, XL > 2 weeks of agent effort (INFERRED from the specs' task counts and criteria counts). Every acceptance criterion counts operations or names a kind and an exit code; none reads a clock.

### S1 — Retire `run` and land the renderer gaps (spec 167 slice A). **M.** Depends on: nothing (179 may delete `SupportsRun` first; whichever lands first).
*Why.* Every front in this domain stands on three live-tree gaps: a bytes row renders empty, `to_payload` carries unbounded base64, and the dead `run` verb sits where `cli` goes. Landing these first lets B and C proceed in parallel and makes the README true.
*Acceptance.*
1. `run` is absent from `Op`, `EXEC_OPS` (the class is gone; `ALL_OPS` is the union of three), `VERB_RUNGS`, `PARAMS`, `_DEFAULT_PROJECTION`, `base.py`, `session.py`, `README.md`; `SupportsRun` is absent from `protocol.py`, `_FAMILY_OPS`, `storage/__init__.py`; `uv run python -c "from vfs.ops import EXEC_OPS"` raises `ImportError`; the drift tests pass.
2. A bytes-sourced row renders `[binary <path> <mime> <size>B v<version>]` byte-for-byte in `_render_read`, `_render_block` and a table cell; no `to_str()` output contains base64 or a bytes `repr` (a test greps the rendering of a 10,000-row result of bytes rows: 0 matches).
3. `to_payload()` carries no bytes and no `"data"` in any populated mask; `to_payload(include_bytes=True)` round-trips through `from_payload` with equality.
4. `to_str(budget=32_768)` cuts at a line boundary, prints exactly one marker naming characters removed and rows remaining, and never cuts the errors section; `to_str()` is unbounded.
5. `scripts/ci.sh` green at 100%; README verb table has no `Execute` row.

### S2 — The parser (spec 167 slice B). **M.** Depends on: nothing (parallel with S1).
*Why.* ADR 081's static parse is what makes the execution policy and a future interrupt summary sound: nothing runs on a refused line.
*Acceptance.*
1. The weighted 100-command corpus of study 01 parses 86 of 100; each of the 14 refusals is `vfs.unsupported.construct` with `line`, `column`, `construct` and, for slice-2 constructs, the slice named in the hint.
2. Each malformed case (unclosed quote, unclosed here-document, trailing `|`, `&& &&`, stray `)`) is `vfs.invalid.syntax` with `line`, `column`, `offset`, `construct`, `expected`, `incomplete`; exactly one error per call; the display shows the source line and a caret under `column`.
3. The four parser budgets each classify `vfs.budget_exhausted` on a counted input (1 MiB + 1 byte; 100,001 tokens; depth 201; the brace expansion that would exceed `ITERATION_BUDGET`) and never hang (the test asserts the error, not time).
4. `&` is refused with a hint saying the call returns when the list has run; `time -p` parses as a builtin before a pipeline.
5. Parse-level spec tests exist for `quoting expansion redirect heredoc pipeline lists errors refused`, asserting the AST or the refusal, never stdout.

### S3 — The pipe, the ABI and `cli` with the minimal programs (spec 167 slice C). **XL.** Depends on: S1, S2.
*Why.* This is the shell. After it an agent types `grep -rn mfa /enterprise | head -20` through `VirtualFileSystem.cli` or `Session.cli` and every verb passes the gate.
*Acceptance.*
1. `ls /nope | wc -l` prints `0` with `statuses == [[1, 0]]`, `exit_code == 0`, `success is False`, one `not_found` in `errors`; `grep zzz f` and `false` succeed with `exit_code == 1`; `cat /nope` fails.
2. A 10,000-file `ls | wc -l` prints `10000` in 10 chunks at a maximum queue depth of 2 (counted); `head -3` on a 10,000-row producer closes after 1 chunk and the producer reports `vfs.cancelled` at info severity.
3. Every `Fs` call reaches a public router method with the admitted authority (spied: N calls, N matches); `vfs.shell` imports nothing from `vfs.storage` (import-graph test); two sessions with different authorities see different `ls /` through `cli`.
4. `cli` under `Authority.system()` explicitly, and on a default-system router with no authority, is `invalid`; a relative path reaching `Fs` is `vfs.internal`; a 65-stage line is `invalid`; `sweep` and `posture` are `unrecognized` 127; `curl` is `unsupported` 126 with the network hint.
5. `cat img.png | wc -c` prints `size_bytes`; `cat a.png > b.png` leaves equal `content_hash`es; `cat img.png` alone displays exactly one placeholder line; `write x; for …` runs zero `write` calls (spied).
6. The display caps at 32,768 characters with the marker and keeps stderr whole to 4,096; `cat big.log | tail -1` prints the last line (the pipe is uncapped).
7. `Session.cli` keeps `cwd` across calls; a second `VirtualFileSystem.cli` starts at `/`; `history` holds at most 1,000 entries of at most 256 surfaced paths.
8. `scripts/ci.sh` green at 100%; the four engine legs green.

### S4 — The program forms, `copy/move(replace=)`, `glob(case_mode=)`, `set -e`, the never table (spec 167 slice D). **L.** Depends on: S3; ADR 087 pin 17 answered (which identity survives a replace).
*Why.* Slice C is the minimal set; D is what makes `ls -la`, `find`, `rm -rf`, `cp -r`, `sed -i`, `stat -c`, `tree`, `glean`, `graph` and `set -e` real, and lands the two verb changes the WASI provider also needs.
*Acceptance.*
1. Every row of 167 §4.1 has a test against a committed GNU fixture; `ls -l` prints `kind size_bytes updated_at owner_id version` in that order and never mode bits.
2. `move(src, dest, replace=True)` onto a file keeps the destination's `entry_id`, versions the replaced body, tombstones the source; a directory over a directory is `exists`; on all five engine legs.
3. `glob(case_mode="insensitive")` returns the same set as a case-folded Python filter on all five legs, in one statement per mount (counted), with a scale review recorded.
4. `set -e` stops at the first failing statement and every POSIX exemption in `tests/shell/spec/set-e` holds; `set_e_tripped` names the pipeline and stage.
5. Each never-class name returns its kind, exit code and hint (`git` → `stat`/trash/`restore`; `perl -pi` → `sed -i`; `python3` → the install hint until S15).
6. `rm -rf /` at a bind site is `busy`; elsewhere it tombstones (counted `delete` calls = 1 with `cascade=True`).

### S5 — The coverage harness and `docs/reference/shell.md` (spec 167 slice E). **M.** Depends on: S4.
*Why.* bashkit's method — fixtures from real bash, a replayed corpus, four counted rates — is the only honest answer to "how bash-like is it", and the reference page is what an agent's host reads.
*Acceptance.*
1. The harness reports parse, resolve, flag and run rates in total and in scope on the synthesized corpus; the in-scope run rate is at least 85%.
2. Fixtures are produced by one pinned-image script and committed; tests never run bash (a test asserts no `subprocess` call in the shell test module).
3. `docs/reference/shell.md` lists the grammar, every program with its forms, the exit-code table and the refusal table; the docs fences in `scripts/ci.sh` pass; `docs/how-to/expose-over-mcp.md` is either written (S10) or removed from the nav.

### S6 — `/.vfs` views, the index, union resolution, install rules, `/.agents` retired (spec 169a). **L.** Depends on: S3 (`shell/status.py`, `Session`), S4 (`replace=` for `cp`/`mv` into an index directory).
*Why.* This is "everything is a file": the catalogue views and the gated resolution (`read` on the entry) that every tool kind shares.
*Acceptance.*
1. On a fresh node `ls /.vfs` lists `bin skills trash`; `ls /data/.vfs` at a mount lists `trash`; `stat /.vfs` is a directory at both.
2. `write`, `mkdir`, `move`, `copy` into `/.vfs/bin/x`, `/.vfs/sessions/x`, `/data/.vfs/bin/x` are each `invalid` carrying the caller's path and the index detail; `sweep /.vfs/trash` passes; `posture /.vfs/bin` lands in the root binding's grants table.
3. An unscoped `glob **` and `grep -r /` make zero calls into any view (spied); `mounts()` lists no view.
4. The first resolution mints `/opt/bin` once as the system actor at posture `read` (one `mkdir`, one `posture`; a second resolution adds none); an agent's `write /opt/bin/upper.wasm` is `permission_denied` without an `add` grant and `created` with one.
5. Resolving a name over a 10,000-file program directory is one `stat` dispatch per mount and zero `ls`; a caller holding `list` only sees the union row bare; a name in `masked` is `unsupported` 126; `write /opt/bin/sed.wasm` is `invalid` unless `sed` is in `prefer_stored`.
6. `/.agents` names are gone from `src/`; `Skill.to_entries(at=container)` writes `<container>/<name>/SKILL.md`; the drift tests pass; four engine legs green.

### S7 — The `/.vfs/run` record (spec 169c). **S.** Depends on: S6.
*Why.* Program output and MCP tool results need an address (`/.vfs/run/<call-id>/stdout`, `/<i>`) before the adapter can mint links for them.
*Acceptance.*
1. After `cat /data/a.txt | upper`, `read /.vfs/run/<id>/stdout` returns the output and `read …/status` names the program path and `content_hash`.
2. Another authority's `read` of the record is `not_found`; the 65th call evicts the first for that authority (counted); the byte budget evicts across authorities (counted).

### S8 — Host tools as files: `ToolView`, the schema-to-flags table, `_invoke`, `rungs_at` (spec 170 §1, §2, §5). **L.** Depends on: S6, S7; S10 §2.6 only for the MCP half (not needed here).
*Why.* Theme 4(a) and theme 7 together: a LangChain-shaped function becomes `/.vfs/tools/<name>`, callable as `<name> --arg value`, gated by `read` on its entry.
*Acceptance.*
1. A registered function (plain, async, and a LangChain `BaseTool` by shape) appears at `/.vfs/tools/<name>` and in `/.vfs/bin` with `callable_kind=tool`; `<name> --x 1` calls it once (spied); a `str` return is one `text/plain` row, a `dict` one `application/json` row, `None` no row, a `Result` passes through.
2. Each row of the flag table has one passing call and one `vfs.invalid` exit 2 with zero tool calls (spied); an unknown flag and an unknown property are refused client-side; `--json` mixed with a property flag is `vfs.invalid`; `cat f | upload` binds `body`.
3. `cat`, `stat`, `ls -l`, `grep -r . /.vfs/tools` issue zero tool calls (spied); `type <name>` prints "runs on the host, with the host's authority (network: yes|no)".
4. A caller without `read` on the entry gets 126; without `list` the name is absent from `/.vfs/bin` and resolves 127; `posture("/.vfs/tools", "list")` makes every tool 126 for everyone until a `grant` of `read`; `rungs_at` issues one chunked statement per `membership_budget` slice over 10,000 entries (counted) on all four engine legs.
5. `ToolError` → exit 1 with the message on stderr; a plain exception → exit 1 with the generic line and no detail in the `Result`; a sync tool past its deadline → `vfs.timeout` 124.
6. A tool declaring a parameter typed `Fs` receives the caller's `Fs` and nothing wider: a `write` through it to a path the caller cannot write is `permission_denied` (spied: the authority on the router call is the caller's, not the host's).

### S9 — MCP servers as views: `McpView`, the inbound table, the supervisor (spec 170 §3, §4, §7 + its three study pieces). **L.** Depends on: S8, S10's `from_call_tool_result` (171 §2.6) — or land that function with this story.
*Why.* Theme 4(b)'s first half: a mounted server appears under `/.vfs/mcp/<server>/{tools,resources,prompts}` and its tools are callable like any program, with the host's configured credential.
*Acceptance.*
1. A connected in-process server appears under `/.vfs/mcp/<name>/`; one call yields a text row, a media row, a `[link …]` row, an embedded text row and an `[unknown block …]` row at `/.vfs/run/<call-id>/<i>` with `structured` as an extra; `isError` is exit 1 with its text on stderr and no rows and no minted kind.
2. Every row of the failure map produces its kind and exit: `-32602` → `invalid` 2; `-32601` → `not_found` 127; `-32000`/transport → `unavailable.backend` 1; wall → `timeout` 124; `-32021` → `unsupported` 126 (until S11 changes elicitation).
3. `ls /.vfs/bin` twice in one `cli` call issues one `tools/list` per server; inside `MCP_LIST_FLOOR_MS`, zero (counted); a tool missing from a refreshed listing is 127.
4. A stdio server killed mid-session: the call is `unavailable.backend` 1; the next call respawns exactly once (counted); a call cancelled by the wall budget is issued exactly once, never retried.
5. `VirtualFileSystem.close()` closes every McpView with no cross-task error on Python 3.11 and 3.13; `import vfs` works without the `mcp` extra; `add_mcp` without it raises with the install hint.
6. Credentials passed to `add_mcp(credentials=)` never appear in `os.environ` of a spawned stdio server (the test spawns a server that prints its environment).

### S10 — The MCP adapter, `serve()` and the token edge (spec 171 + spec 149). **XL** (171 L + 149 M). Depends on: S1 (placeholder, cap, `to_payload`), S3 (`cli`); S7 for links to program output (degrades to placeholder without it).
*Why.* Theme 6. Every verb as a tool plus one `cli` tool, five blocks only, bounded on all three channels, an `Authority` per request, the system actor and open mounts refused at the edge.
*Acceptance.*
1. `tools/list` names exactly the `AGENT_OPS` verbs in `fs.capabilities()` plus `cli`: 21 on the default router, 19 on an unknown dialect, 1 with `tools={"cli"}`; no input schema names `authority`, `observations` or `provenance` (counted over the listing); no served tool and no kernel program names a mount-admin verb.
2. A spy on the router sees zero calls with `authority=None` across the MCP test module; `serve(fs, transport="stdio", authority=Authority.system())` raises before binding a transport, as does a router whose `default_authority` is the system actor; `serve()` refuses an `open` mount unless `allow_open=True` and names it.
3. Over HTTP: no token reads a `shared` mount and is `unauthenticated` on a `private` one; an invalid token is 401; `authority_from_token` refuses a `sub` equal to the reserved system name; audience, signature, issuer and expiry are checked by the verifier (one failing test per check).
4. Over the `ls` tool on 10,000 files: the text block is at most 32,768 characters plus the marker; `structuredContent` holds exactly the rows the text showed plus one `vfs.budget_exhausted.truncated` warning with `vfs.elided.rows == 10,000 - shown`; a `Result` of 10,000 image rows yields at most 8 typed blocks, 4 MiB raw, 64 links (counted); `structuredContent` carries no bytes and validates against `ResultPayload`.
5. `isError == not structuredContent["success"]` on every wire test; `cli('grep nomatch f')` and `cli('false')` are `isError: false` with `exit_code == 1`; `cli('for x in a; do :; done')` is `isError: true`; `cli('cd /notes')` then `cli('pwd')` prints `/`; `timeout_ms` above 10,000 leaves the deadline at 10 s (spied on the clock seam).
6. `resources/read` returns a blob with `mimeType` for a bytes row and the exact text for a text row; hidden, missing and directory are `-32602`; a row over 12 MiB is `-32603` with zero bytes fetched (spied); `vfs:///` URIs round-trip for a space, `#`, `?`, `%` and a non-ASCII letter.
7. The wire validates in the four session modes against the vendored 2025-06-18, 2025-11-25 and 2026-07-28 schemas; the 2025-03-26 session carries no link, no audio and no `structuredContent`; the core install imports nothing from `mcp`.

### S11 — Interrupts: the `pending` kind, the ask ledger, and resume for every tool kind (new; amends ADR 084 pin 4, spec 148 rule 5, spec 149 rule 5, spec 170 §4, spec 171 scope). **L.** Depends on: S3, S8, S9, S10; ADR 087's replay contract (spec 177) for safe re-runs.
*Why.* Themes 1 and 4 require a tool call to stop, ask a human, and continue. The kernel keeps its law — it never blocks and never decides — by carrying the question as a classified, resumable `Result` whose answer lives in a ledger written through the grant channel. Without this story, 170 and 171 ship with elicitation refused and complete-only tools, and the host must build its own interrupt layer around vfs, against theme 1.
*Acceptance.*
1. A host tool that raises `Interrupt(payload)` ends its stage with exactly one `vfs.pending` error carrying `data = {digest, ttl, payload, stage, program}`, exit code 75, `success is False`, `isError: true` on the wire; the tool function was entered exactly once (spied); zero verbs ran after the interrupt.
2. Writing a one-shot allowance for that digest and re-issuing the same `cli` line runs the tool once more with the answer as its resume value; a second re-issue with the spent allowance is `pending` again (allowance count 1 → 0, counted); a foreign digest admits nothing; a grant row admits every later run.
3. A mounted 2026-07-28 server answering `input_required` yields `vfs.pending` with `inputRequests` and the opaque `requestState` in `data`; the resume re-sends `tools/call` with `inputResponses` and the same `requestState` exactly once (spied on the wire); the interim result is never cached.
4. A pipeline `producer | interrupting_tool | consumer` ends with the consumer having received 0 chunks, the producer cancelled with `vfs.cancelled` at info, stdout emitted before the stop kept, `statuses` marking the pending stage; a verb the ladder refuses under a `none` posture that a principal could allow answers `pending` with a digest of verb, canonical arguments, authority shape and grant revision.
5. On the wire, `serve()` surfaces `pending` as MRTR `input_required` with an integrity-protected `requestState` (principal, TTL, digest inside); a tampered `requestState` is refused `invalid` with zero handler calls (spied); a client that cannot speak MRTR gets the `pending` text and payload as a `complete` error result.
6. `pending` has a `KindContract` with `retry_class=refresh`; `WASI_ERRNO[pending]` exists (drift test); ADR 084 pin 9's kind list and `shell/status.py` carry the new row; the ledger write path is a grant-channel call (a test asserts no `Session` method writes it).

### S12 — MCP servers that authenticate as the user (new ADR + spec; extends 170 and 149). **L.** Depends on: S9, S10, S11 (an OAuth authorization-code round trip is itself an interrupt).
*Why.* Theme 4(b)'s second half. Spec 170 decided one credential per server at v1. A per-caller identity means per-caller connections (or per-caller headers on streamable HTTP), a credential record keyed by principal, the MCP client-side OAuth 2.1 flow when a server demands it, and a refusal to forward the served bearer token upstream (149 rule 4's spirit, RFC 8707 audience).
*Acceptance.*
1. `add_mcp(name, server=, identity="caller")` opens one connection per distinct `(issuer, sub)` principal, lazily, capped by `MCP_CALLER_CONNECTION_BUDGET` (counted); `identity="host"` keeps today's one connection.
2. Two callers see two `tools/list` results when the server lists per identity (an in-process server that varies its catalogue by bearer), and the `/.vfs/mcp/<server>` view differs per caller with zero cross-caller cache hits (counted).
3. A caller with no stored credential for a server that returns 401 gets `vfs.pending` carrying the authorization URL and a digest; completing the ledger entry with the callback's code mints the token record for that principal; the re-run calls the tool once (spied).
4. The inbound HTTP bearer token never appears in any outbound request to a mounted server (a relay asserts zero occurrences across the test module).
5. `remove_mcp` and principal revocation drop every connection and credential for that principal (counted to zero); credentials are never written to `os.environ` or to a vfs row the agent can `read`.

### S13 — A one-line serve entry point (`python -m vfs.mcp` / `vfs serve`). **S-M.** Depends on: S10; a router-from-URL constructor (another domain: storage/host config; spec 157's Postgres provisioning is adjacent).
*Why.* Theme 6 says "easy". `await serve(fs, …)` in a Python file is not a one-liner a Claude Desktop or Codex config can name.
*Acceptance.*
1. `uv run python -m vfs.mcp --url sqlite+aiosqlite:///x.db --transport stdio --as me` starts a server whose `tools/list` equals S10's; `[project.scripts] vfs = "vfs.cli:main"` provides `vfs serve` with the same flags.
2. Starting against a mount whose posture is `open` exits non-zero naming the mount unless `--allow-open`; `--as system` exits non-zero before binding.
3. The command imports nothing from `mcp` until `serve` is chosen (`vfs --help` works without the extra; a test asserts the import graph).
4. `docs/how-to/expose-over-mcp.md` has the steps and a Claude Desktop / Codex config block, and the docs fences pass.

### S14 — Text kernels in Rust (spec 168 a → b → c). **L** (a M, b M, c S). Depends on: S4; the Rust seam (`PROTOCOL_VERSION` 10 → 11).
*Why.* Moves six names off Python and adds `sort uniq tr tee xargs diff cmp`; `xargs` is the one explicit rows-to-verb form and what makes `find -exec` run. Honest gain about 1% of measured calls beyond 167, so a is worth 0.1.0, b is needed for `find -exec`, c can slip.
*Acceptance.*
1. Parity tests pass for `head tail wc cut nl sed` against the slice-D Python transforms as oracles under `tests/support/oracles/shell/`; a refused form calls `feed` 0 times (spied).
2. Every new kernel passes its GNU fixtures and the split law (whole, one byte at a time, seeded random boundaries); `KNOWN_DELTAS` lists `cut -c` characters, BSD `sed -i ''`, no `sort -R`.
3. `cat f | sort | uniq -c | sort -rn | head -5` over 10,000 lines feeds 10 chunks, each `sort` materializes once, queue depth ≤ 2 at every seam, `head` drains 1 chunk, the second `sort` reports `vfs.cancelled` (counted).
4. `find . -name '*.py' | xargs -n 10 grep -l TODO` over 25 files calls the `grep` verb 3 times (spied); `xargs` returns 123 when one child exits 1; the `Call` a program receives has no execution capability (type test).
5. `awk '{print $1}'` and `jq .` are `unrecognized` 127 with their hints until S16; `cargo test -p vfs-core` green; the wheel budget holds.

### S15 — The Python guest over wasi-python (spec 172 rewritten per memo 2026-10-23; ADR 086 amended). **M.** Depends on: S3 (the ABI and `cli`), S4 (`replace=`), S6 (resolution of `python3`); Clay's answers to memo Q1-Q5 and ADR 086 pins 5/8.
*Why.* Theme 4(c), the installed-interpreter half. The mechanism is proven twice; what remains is a thin adapter (`VfsProvider`, `verb_tools`, budgets, exit codes) behind `vfs-py[python]`, and a rewrite of the stale spec.
*Acceptance.*
1. `python3 -c "import numpy, pandas; print(numpy.__version__)"` runs with zero host preopens beyond the stdlib zip the runner preopens itself and zero vfs `Grant`s (the runner's `done` record is asserted).
2. The pandas CSV job (`read_csv` from a row, `groupby`, `to_csv`, read back) completes with exit 0 in at most 21 verbs (17 `stat`, 2 `read`, 2 `write` as measured; a per-run stat cache lowers the bound and the test pins the new number).
3. A guest `open("/ro/x", "w")` on a read-only mount raises `EROFS` 69 in the guest, lands in `files.refused`, and the stage reports status 1 with one `read_only` error although the guest exited 0; `open("/.vfs/trash")` is `ENOENT` 44 with zero verbs.
4. The same script run as Alice (no grant) and Bob (`read` on `/secret`) gives `FileNotFoundError` 44 and the body respectively, through one provider class; `tools.write` to a forbidden path returns `success: False` with `vfs.read_only` and no exception.
5. `trapped == "deadline"` → exit 124; "out of fuel"/"out of file calls" → 137; any other trap → 134; `python3 -m pip install x` and `import scipy`-style misses report `unsupported` naming the set from the wheel's MANIFEST.
6. `WASI_ERRNO` has one entry per `ErrorKind` (drift test); `import vfs` works without the `python` extra; the guest tests are `slow`.

### S16 — The generic wasm host, `/opt/bin` programs, `awk`/`jq`/uutils (spec 169b + its post-171 section). **XL.** Depends on: S6, S7, S14 (kernel names), S10 (`vfs install`). **Recommend post-0.1.0 unless Q6 is answered "yes, our own host".**
*Why.* It is the only road to `awk` (the largest measured hole) and to installing arbitrary programs as files, but it duplicates a preview1 host that wasi-python's runner already owns, and the memo asks whether vfs still wants it.
*Acceptance (if taken).* 169b's fourteen counted criteria as written (verb counts `{stat 2, read 3, write 1}` on a first run and `{stat 2, read 2, write 1}` on a cached one; `ACCES` on a refused close with stage status 1; `NOTCAPABLE` on `../../etc/passwd` with zero verbs; fuel kill 137 after exactly the budget; `WASI_ERRNO` drift test; `prog | head -1` issues no host verb after the cancel), plus `cat users.json | jq '.users[].name'` through installed jaq with zero guest verbs.

### Dependency-ordered landing list with sizes

| # | Story | Spec | Size | Needs |
|---|---|---|---|---|
| 1 | S1 renderer gaps + `run` out | 167 A | M | — |
| 2 | S2 parser | 167 B | M | — (parallel with 1) |
| 3 | S3 pipe, ABI, `cli` | 167 C | XL | 1, 2 |
| 4 | S4 forms, `replace=`, `case_mode`, `set -e` | 167 D | L | 3; ADR 087 pin 17 |
| 5 | S10 adapter + `serve()` + token edge | 171 + 149 | XL | 1, 3 (7 for links) |
| 6 | S5 harness + docs | 167 E | M | 4 |
| 7 | S6 views, index, resolution | 169a | L | 3, 4 |
| 8 | S7 `/.vfs/run` | 169c | S | 7 |
| 9 | S8 host tools (`ToolView`, `_invoke`, `rungs_at`) | 170 §1-2, §5 | L | 7, 8 |
| 10 | S9 MCP servers (`McpView`) + the three study pieces | 170 §3-4, §7 | L | 9, 5 (§2.6) |
| 11 | S11 interrupts: `pending`, ledger, resume | new; amends 084/148/149/170/171 | L | 3, 9, 10, 5; spec 177 |
| 12 | S14a-b text kernels + `xargs` | 168 a, b | M + M | 4 |
| 13 | S15 Python guest over wasi-python | 172 (rewritten) | M | 3, 4, 7; ADR 086 amended |
| 14 | S13 one-line serve | new | S-M | 5; a router-from-URL story |
| 15 | S12 MCP as the user | new | L | 10, 11, 5 |
| 16 | S14c `diff`/`cmp` | 168 c | S | 12 |
| 17 | S16 generic wasm host, `awk`, `jq`, uutils | 169b + post-171 | XL | 7, 8, 12, 5; Q6 |

Critical path for themes 4/6/7/8 at 0.1.0 (INFERRED): 1+2 → 3 → 4 → 7 → 8 → 9 → 10 → 11, with 5 in parallel after 3, and 13 in parallel after 7. Roughly five L/XL items in series.

---

## 6. Open questions Clay must decide

1. **Interrupts versus "no `ask` inside vfs".** Amend ADR 084 pin 4 to "vfs never asks, but carries a `pending` outcome a host answers through the ledger"? If yes, S11 must land before 170/171 are built as drafted (their elicitation-refusal and complete-only rows change). If no, interrupts live entirely in the host's layer and themes 1/4's "interrupt capability" means only the static parse summary and the classified refusal.
2. **The shape of `pending`:** a child kind `vfs.permission_denied.pending` (Mirage §4.3, degrades for old consumers) or a top-level `vfs.pending` (spec 148's wording, which also covers a tool's own question, not only a refusal)? Which exit code: 75 (`EX_TEMPFAIL`), or another row? Where does the ask ledger live — storage per mount (survives restarts, visible to the grant verbs) or the router (one per process, lost with it)? TTL?
3. **Can a suspended pipeline resume in process?** Accept "end the `cli` call with a resumable `pending`; re-issue re-runs the line" as the only model at 0.1.0 (the pipe cannot checkpoint), with an in-process `Session` hold-and-resume as a later option? Or push `/.vfs/jobs` + the MCP tasks extension (`input_required`) into 0.1.0 so a suspended line is a task?
4. **MCP servers as the user.** Keep spec 170 §3.1 (one credential per server, host's identity) for 0.1.0 and schedule S12 after, or require per-caller identity now (which changes the supervisor and the listing cache before McpView is built)? If per-caller: per-caller connections, header injection on streamable HTTP, or OAuth-on-demand through an interrupt? Never forwarding the served bearer upstream (149 rule 4's spirit) — confirm.
5. **Default posture for the catalogue views.** Keep 170 §5.1 (fresh node: everyone, anonymous included, can call every host tool with the host's authority; the host locks it with two lines) or mint `/.vfs/tools` and `/.vfs/mcp` at posture `list` so a tool needs an explicit `read` grant before anyone calls it?
6. **The generic wasm host (169b) and `awk`.** Memo 2026-10-23 Q2: does vfs still want its own preview1 host for stored `.wasm` programs now that the Python guest runs on wasi-python's runner? `awk` (371 measured uses) is the largest coverage hole and is only reachable through it (or a second runner, or a Rust awk subset that 168 decision 2 refused). Options: (a) build 169b in Python as drafted (XL); (b) ask wasi_python whether its runner can host a generic wasip1 module over the same mount protocol (unknown; INFERRED); (c) ship 0.1.0 without `awk`/`jq`, refusing with hints as 168 says.
7. **A one-line serve.** Reverse 171 decision 7 for 0.1.0 (`python -m vfs.mcp --url … --transport stdio` and `vfs serve`)? It needs a router-from-URL constructor owned by the storage/host-config domain; name that dependency.
8. **Order against the kernel specs.** Land 167 C/D before 174/176/178/181 (shipping the racy `>>`, `stat`-then-`write` `touch`, no paging, no `owner_id`, then changing them), or after? And the flag's name: `overwrite=` (167/169) or `replace=` (ADR 087/181), with pin 17's identity rule.
9. **The 0.1.0 program table cut.** Confirm: all of 167 (A-E), 168a and 168b in; 168c, `awk`, `jq`, uutils out unless Q6 is (a) or (b). Also: should `grant`, `revoke`, `grants`, `edit`, `mkedge`, `rmedge` get shell spellings (today `unrecognized` with a hint naming the verb tool), given theme 8 says "fully functional" and theme 7 says tools share the permission structure the shell cannot set?
10. **ADR 086 amendments and the Python guest at 0.1.0.** Confirm pins 1, 2, 4, 6, 7 are rewritten from memo 2026-10-23 (package set from the wheel's MANIFEST; 3.15/SDK 33 resolved; no rows under `/opt`; wasi-python's runner is the host; the door is the tool protocol), accept two versions per guest-created file (F9) at v1, decide the guest's writable `HOME` (F11) and whether to ask wasi_python for read-only-mount `import_path` so `import vfs` can ship (memo Q1). Is the Python guest in 0.1.0 (S15, M) or after?
11. **Spec 170's remaining study.** Treat the supervisor spike on 3.11/3.13, the real-server schema census and the legacy-server probe as the first three tasks of S9 (an afternoon each per review 15) rather than a separate research memo?
12. **Docs housekeeping now or at landing:** README's `run`/`/.agents`/"MCP-native" sections and the empty `expose-over-mcp.md` stub are published facts that are false today; fix in S1/S10 or earlier?
