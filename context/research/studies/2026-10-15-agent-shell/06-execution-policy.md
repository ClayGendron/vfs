# S6 — Execution policy: how a command is allowed or denied in the vfs shell

- **Date:** 2026-10-15
- **Researcher:** S6
- **Question:** How is a command allowed or denied in the vfs shell, by whom, and where does that bind to the permission ladder vfs already has?
- **Clones read** (all read-only; commits from `refresh.log`): `codex` 16e578d (Apache-2.0; shallow clone, one commit), `claude-agent-sdk-python` aada024 (MIT), `gemini-cli` d42e3f1e7 (MIT; **DIRTY, not refreshed, and `packages/` is deleted from the working tree — read via `git show HEAD:`**), `opencode` 13263f30ed (MIT; code now under `packages/core/src`), `deepagents` 0bf167654 (MIT), `deepagentsjs` 9f3bfd5 (MIT), `eve` 5666d2f0d (Apache-2.0), `sandbox-runtime` 9a277e5 (Apache-2.0), `sandbox-sdk` a080a65 (Apache-2.0), `just-bash` 9ab0e0d (Apache-2.0), `bashkit` b7904a4 (MIT), `amla-sandbox` 169384f (Python MIT; bundled wasm runtime AGPL/BUSL, study only), `plan9port` b6564bd9 (MIT), `9front` a0806493 (**DIRTY, not refreshed; no top-level licence file**), `pjdfstest` 85a8aea (one citation).
- **Web:** Claude Code permissions and sandboxing docs, fetched 2026-10-15 (URLs in Sources).
- **Evidence labels:** `[EXECUTED]` I ran it and show the output; `[READ]` I (or a subagent I briefed, marked `[READ/sub]`) read it in a checkout or a doc; `[INFERRED]` my reasoning from the above. The vfs-side facts are `[READ]` from the live tree unless marked `[EXECUTED]`.

---

## Summary

The vfs shell does not need a command policy. It needs the gate it already has, fired on every verb a command resolves to. Every peer that judges a command *string* (Codex, Claude Code, gemini-cli, opencode, the deepagents CLI) does so because its runtime is an OS shell that can run anything, and every one of them says in its own docs or code that the string match is not a security boundary; the real boundary is an OS sandbox over paths and hosts, enforced while the command runs. vfs is in the other position. Its shell can only reach storage through the 25 verbs, each verb is gated per principal per path at dispatch, and a program runs as the caller with the caller's authority value. So the pinned order in `_gate_entry` — capability, grammar, permission — is the execution policy, and the only pre-flight work left is resolving the program name, refusing over-shape input, and setting budgets. `run`'s rung stays `read`: a program is a row, and running it reads it, exactly as Plan 9's `OEXEC` is "read, plus the x bit", and vfs has no x bit by ADR 080's choice of a total order over bits. That one rule dissolves both halves of the parked "per-path / per-principal execute" question: who may run a program is who holds `read` on its row in `/.agents/bin`; a path nobody may run is a bin row postured at `list`; a program nobody should see is not bound in. Installing a program is a `write` under the ladder (`add` mints, `contribute` overwrites, the owner floor rides). The budget set mirrors grep: shape caps refuse `invalid` before anything runs, the fan-out and output caps truncate with a warning, and fuel and wall time trip at runtime as `budget_exhausted` and `timeout`. The one new lever worth adding is small: a host may mask a *program* name the way `deny_ops` masks a verb, and the refusal classifies `unsupported`, the same as a masked verb today.

---

## Findings

### 1. What vfs has today `[READ]`, with one executed check

1. **`run` is an `EXEC_OPS` verb at rung `read`** (`src/vfs/ops.py:85`, `:156`). The table's docstring says "`run` waits for its own axis" (`ops.py:169-171`) and ADR 080 pin 9 says "`run` on its own axis". No storage implements `SupportsRun` (`src/vfs/storage/protocol.py:346-355`; the brief confirms "no shipped storage implements it"), so **no gate reads `run`'s rung today**. The router's own gate runs capability and grammar only: `_gate_entry` applies the permission layers only to `write_rels` of a `WRITE_GATED_OPS` verb, and `run` is not one (`src/vfs/base.py:2829-2873`; the `run` docstring: "Not a namespace mutation, so it takes no write-authorization gate", `base.py:1555-1560`). The tests pin that a mount declaring `run` executes with no rights check at all (`tests/base/test_gates.py:182-190`, the `RunnerStorage` spy) and that a mount not declaring it answers `unsupported` (`:172-180`, `:193-200`).
2. **The gate order is a contract:** capability → grammar → permission; "an incapable entry reads as `unsupported`, never as a policy denial" (`base.py:2836-2841`). `_gate_entry` refuses `op not in binding.meta.caps` as `ErrorKind.unsupported` with `"operation {op!r} is not declared by the storage mounted here"` (`:2857-2862`), then `check_reserved_path` for mutations (`invalid`), then `check_writable_composed` (`read_only`).
3. **`deny_ops` is a per-mount verb mask, mutating and exec verbs only.** `MountMeta.caps = declared_caps - deny_ops` (`base.py:147-160`); `_validate_deny_ops` rejects any read-family op: "mount policy is principal-blind, and read denial lives in the permission plane, where a principal is in scope" (`base.py:846-862`). A masked verb is indistinguishable from an undeclared one: both are `unsupported`.
4. **`DEVELOPER_OPS` is a documented rule with no enforcement site yet.** `grep -rn DEVELOPER_OPS src/vfs` finds it only in `ops.py:97` `[EXECUTED]`; there is no MCP serve module in `src/vfs/` today (listing of `src/vfs/` `[EXECUTED]`). The rule binds the future `cli` and serve surfaces.
5. **The ladder and the one table.** `none < list < read < add < contribute < read_write` (`ops.py:118-124`); `VERB_RUNGS` holds `primary`/`create`/`traverse` per verb (`ops.py:134-160`). ADR 080 pin 6: "A verb's rung is the rung of the field it reads." Pin 4: the blind drop box "joins `run` on the second-axis list" — the ADR parked `run`, it did not decide it. Grants only widen; there is no deny row (`src/vfs/storage/grants.py:3-5`; `base.py:1583-1584`). The owner floor: a named caller alters and trashes its own rows at any rung from `add` up; anonymous holds none (ADR 080 pin 3, pin 12).
6. **Identity is a value on the call.** `Authority` is frozen, hashable, re-derived on every call, never cached (`src/vfs/authority.py:118-126`). It carries a `Narrowing` enum "what a session has given up", whose only value today is `NONE` (`authority.py:65-69`). That is the seam for attenuation and it is already in the type.
7. **Spec 039 (archived)** decided "execute defaults to granted: both string forms include `execute`" and that per-user execution is "out by doctrine" for the user-blind permission map (`context/specs/archive/039-execute-permission-tier/spec.md`, "Decided policy", "Open questions"). It was superseded by `deny_ops`, and denied execution classifies `unsupported`, not `permission_denied` (same file, status block). The open question splits the demand: per-path → reopen 039; per-principal → an `execute` level "beyond `read_write`" in the grant ladder (`context/open-questions.md:73-80`).
8. **The existing budget discipline** (`src/vfs/storage/backends/database/grep.py:113-126`): `CANDIDATE_BUDGET = 25_000`, `POSTING_BYTE_BUDGET = 4 MiB`, `WALL_TIME_BUDGET = 10.0`, `CONTENT_BYTE_BUDGET = 32 MiB`; glean has `SCOPE_ID_BUDGET = 5_000`, `OVERLAY_BUDGET = 500`, `WALL_TIME_BUDGET = 10.0` (`glean.py:137-146`). "A tripped budget truncates with a warning" naming the budget by name (`grep.py:41-53`, `:254-307`), and the warning is `truncated = "vfs.budget_exhausted.truncated"` — "a runtime budget cut the result; refine, do not retry" (`src/vfs/results/kinds.py:82`). The wider kind vocabulary that execution will use: `unauthenticated`, `permission_denied`, `read_only`, `unsupported`, `unrecognized`, `invalid`, `budget_exhausted`, `timeout`, `cancelled` (`kinds.py:63-93`). Producer exclusivity: "only capability gates emit `unsupported`; only dispatch emits `unrecognized`" (`kinds.py:43-44`).
9. **The July memo's capability rule:** the guest-visible capability set *is* the security surface; "the capability set must be curated vfs verbs bound to the session principal, never raw internals"; "the guest gets capabilities, never config" (`context/research/2026-07-24-hermetic-runtime-and-wasm-cli.md:169-173`, `:366-368`). ADR 069: "There is no shell, no side door … the check runs on the storage call, for every caller" and "The shell is the enforcement gap, by the peers' own admission" (`context/decisions/069-*.md:116-120`, `:298-301`).

### 2. Codex judges an argv before spawn, with Starlark prefix rules; the OS sandbox is the boundary `[READ/sub]`

- **The brief's premises were partly stale.** There is one crate, `codex-rs/execpolicy`; `execpolicy2` does not exist. No default policy ships: `core/src/exec_policy.rs:563-567` loads `*.rules` from the config folders and the policy is empty without them. The only `.rules` file is `execpolicy/examples/example.codexpolicy` (78 lines: `git reset --hard` forbidden; `ls`, `cat`, `head`, `printenv` allow; `cp` prompt) and it says it is not for real use. `is_known_safe_command` does not exist.
- **The language:** Starlark. `prefix_rule(pattern, decision, match, not_match, justification)` where `pattern` is an ordered token list, each token a literal or a list of alternatives (`execpolicy/src/parser.rs:349-410`, `:171-217`). `match`/`not_match` are example argvs checked when the policy loads (`rule.rs:245-306`). `network_rule(host, protocol, decision)` and `host_executable(name, paths)` are the other two builtins (`parser.rs:412-472`).
- **The verdicts:** `Decision` is `Allow < Prompt < Forbidden`; the evaluation takes the maximum across matches, so the strictest wins (`decision.rs:9-16`, `policy.rs:386-412`). An unmatched command gets a heuristics verdict: `rm` with `-f`/`-rf`/`--force` (also through `sudo`, `env`, `trap`, nested `sh -c`) is dangerous (`shell-command/src/command_safety/is_dangerous_command.rs:38-160`).
- **The parse:** input is always an argv. Only `[shell, "-c"|"-lc", script]` is split, by tree-sitter-bash, and only when every node is a plain word/command/list/pipeline and the only operators are `&&`, `||`, `;`, `|` (`shell-command/src/bash.rs:29-98`). Redirections, `$(...)`, variables, control flow, heredocs: the whole argv is judged as one unit. A non-shell argv[0] is judged as `[argv0]` alone; inner commands "can add restrictions, but cannot grant the executable trust" (`core/src/exec_policy/executable_identity.rs:15-101`).
- **Composition with approval and sandbox:** `AskForApproval` is `untrusted | on-request (alias on-failure) | granular | never`; under `never` every `Prompt` becomes `Forbidden` (`core/src/exec_policy.rs:218-240`). `SandboxPolicy` is `danger-full-access | read-only | external-sandbox | workspace-write{writable_roots, network_access}` (`protocol/src/protocol.rs:1183-1230`). `bypass_sandbox` is true only when every segment matched an explicit `Allow` rule, never from a heuristic (`exec_policy.rs:442-456`). Enforcement at run time is Seatbelt on macOS and bwrap+seccomp+landlock on Linux (`sandboxing/src/manager.rs:50-64`).
- **The lesson:** the string judgement exists to decide whether to *ask a human* and whether to *lift the sandbox*; it is not what keeps the command inside the workspace. The sandbox does that, per path and host, while the process runs.

### 3. Claude Code: deny → ask → allow on whole-command text, per subcommand; "isn't a security boundary"; the sandbox is `[READ]` (docs, 2026-10-15)

- Rule shapes: `Bash(npm run build)` exact, `Bash(git log *)` prefix (everything before the first `*` matches as written), `Bash(ls:*)` equals `Bash(ls *)`, `Read(./.env)`, `Edit(/src/**/*.ts)`, `WebFetch(domain:example.com)`, `mcp__server__tool`. Path rules follow gitignore semantics with `//abs`, `~/`, `/settings-relative`, and plain `cwd`-relative anchors.
- Order: "Rules are evaluated in order: deny, then ask, then allow. The first match in that order determines the outcome, and rule specificity doesn't change the order." An allow "can't carve an exception out of a deny rule." A bare tool name in deny removes the tool from the model's context entirely.
- Compound commands: the recognized separators are `&&`, `||`, `;`, `|`, `|&`, `&`, newlines; "a rule must match each subcommand independently." Deny and ask rules also apply inside subshells, `$(...)` and loop bodies. `npm test &&` (nothing after) is unparseable and no allow rule approves it. Wrappers `timeout`, `time`, `nice`, `nohup`, `stdbuf`, `command`, `builtin`, `noglob` are stripped first; a leading assignment of a known-safe env var is stripped for allow, any assignment is seen through for deny.
- The admission: "A Bash rule matches the command text Claude writes … It doesn't match the same program invoked in a different form, so a deny or ask rule covers the invocation Claude usually produces and isn't a security boundary around the program." `Bash(git push *)` in deny does not stop `git -C . push origin main`. `Bash(command:rm *)` is ignored because it "would be bypassable by a compound command."
- A built-in read-only set (`ls`, `cat`, `echo`, `pwd`, `head`, `tail`, `grep`, `find`, `wc`, `which`, `diff`, `stat`, `du`, `cd`, read-only `git`) runs without a prompt in every mode and is not configurable; `Read`/`Edit` deny rules are also applied to the file arguments of `cat`, `head`, `tail`, `sed`, `tee` and to redirection targets, but "don't apply to a command that reads files without naming them."
- The sandbox: "a boundary that the operating system enforces around the shell commands"; Seatbelt on macOS, bubblewrap+socat on Linux; `filesystem.allowWrite/denyWrite/allowRead/denyRead`, `network.allowedDomains/deniedDomains`, `allowUnixSockets`, `allowLocalBinding`, `excludedCommands`, `allowUnsandboxedCommands`, `failIfUnavailable`, `autoAllowBashIfSandboxed` (default true: sandboxed commands run with no prompt). "The sandbox covers shell commands only. Claude's file tools, MCP servers, and hooks run outside it." Protected configuration paths "stay write-denied" and "there is no way to exempt one of these paths." Read overlap: the narrower path wins; a deny holds inside a wider allow.
- The SDK mirrors the vocabulary: `PermissionMode = default | acceptEdits | plan | bypassPermissions | dontAsk | auto`, `PermissionBehavior = allow | deny | ask`, `PermissionRuleValue(tool_name, rule_content)`, `PermissionUpdate(type ∈ addRules | replaceRules | removeRules | setMode | addDirectories | removeDirectories)`, and a `can_use_tool` callback returning `PermissionResultAllow | PermissionResultDeny` (`claude-agent-sdk-python:src/claude_agent_sdk/types.py:25-27`, `:134-161`, `:259-276`). A warning fires when an `allowed_tools` entry shadows the callback (`:2218-2250`).

### 4. gemini-cli and opencode: the same shape, with the parse getting stricter over time `[READ/sub]`

- **gemini-cli** (d42e3f1e7, dirty, gutted): `splitCommands` is a quote-aware scanner splitting on `&&`, `||`, `;`, `&`, `|` — not newlines, not inside `$(...)` (`packages/core/src/utils/shell-utils.ts:15-63`); `getCommandRoot` keeps the last path component of the first word (`:73-95`). Patterns are `ShellTool(<prefix>)` with word-boundary prefix matching (`:226-248`); the blocklist is checked first and a hit is a hard denial (`:250-269`); `coreTools` entries turn the list into a strict allowlist (`:309-329`). `$(`, backticks and `<(` outside single quotes are hard-denied before anything else (`:130-179`, `:215-224`). "Always allow" is an in-process `Set` of root commands (`tools/shell.ts:45,153-174`). Approval modes: `default | autoEdit | yolo` (`config/config.ts:55-58`). **No trusted-folders code exists at this commit** (grep empty).
- **opencode** (13263f30ed): `permission` maps a tool key to an action or an ordered `{pattern: action}` map; `ask | allow | deny`; **key order is the policy because evaluation is last-match-wins** (`packages/core/src/v1/config/permission.ts:5-35`, `permission.ts:87-97`). Saved "always" approvals are added after the configured-deny check, so they cannot override a configured deny (`:173-189`). The shell tool parses with tree-sitter and makes every `command` node a resource — pipelines, `&&` lists and commands inside `$(...)` are each checked; the resource is the node's full text (`tool/plugin/shell.ts:117-146`, `shell/parse.ts:175-207`). An opt-in "portable" scanner refuses opaque input by reason: `command-substitution`, `compound-command`, `dynamic-command-name`, `dynamic-execution`, `heredoc`, `unterminated-quote`, … (`shell/scan.ts:3-12`). `cd` targets feed an `external_directory` check instead (`shell/parse.ts:192-195`). `Wildcard.match` anchors the whole string, `*` matches anything including `/` and spaces (`util/wildcard.ts:3-14`). `ask` blocks the tool call on a deferred; replies are `once | always | reject` (`permission.ts:204-322`). `doom_loop` is in the schema and docs only; no enforcement was found.

### 5. deepagents and eve: the libraries gate nothing by name; the harness does `[READ/sub]`

- **deepagents** core: the fs tools are `ls read_file write_file edit_file delete glob grep execute` (`libs/deepagents/deepagents/middleware/filesystem.py:1607-1611`); `execute` and `delete` are dropped when the backend cannot support them (`:3029-3051`). `interrupt_on` defaults to `None` and HITL is added only when non-empty (`graph.py:288`, `:950-955`). The current config keys are `allowed_decisions` (approve/edit/reject/respond), `description`, `when` (a per-call predicate); `allow_accept`/`allow_edit`/`allow_respond` no longer exist. **The core has no command-level policy**; "Execution not available" is the only refusal (`filesystem.py:3172-3183`). **Path permissions plus an execution-capable backend are rejected at construction** "because shell commands bypass path rules" (`filesystem.py:1976-1983`; JS `fs.ts:2245-2260`) — the enforcement gap of ADR 069, stated as a `NotImplementedError`. The CLI's `ShellAllowListMiddleware` allowlists the first token after a regex blocklist of `$(`, backticks, redirects, heredocs, `${`, `$VAR`, lone `&` (`libs/code/deepagents_code/agent.py:860-975`, `config.py:4204-4310`). Per-call `timeout` is capped by `max_execute_timeout = 3600` (`filesystem.py:3150-3168`); `LocalShellBackend` defaults to 120 s and runs `subprocess(shell=True)` unsandboxed (`backends/local_shell.py:113-116`).
- **eve:** `byPrincipal` scopes **memory and schedules**, not tools or files; it builds a key from `[principalType, authenticator, issuer, principalId]` and returns `null` (memory off) for anonymous or runtime principals (`packages/eve/src/shared/principal-scope.ts:3-15`). The principal is read at the route edge and projected as `session.auth` (`context/keys.ts:60-63`). Tools have an `approval` policy (`never | once | always | auto | custom(session.auth, toolInput)`), not a per-principal table. `bash` has no command policy; it yields after 30 s and backgrounds the process (`execution/sandbox/bash.ts:10`); output is capped at 50 KiB (`truncate-output.ts:20`). File tools check only that a path is absolute — there is no check that it is under `/workspace` (`execution/sandbox/require-sandbox.ts:8-21`). Budgets are per session in tokens and dollars (`docs/agent-config.md:241-300`); no step cap.

### 6. The OS sandboxes have no command policy at all; they police resources `[READ/sub]`

- **sandbox-runtime** (Anthropic): the config has `filesystem{denyRead, allowRead, allowWrite, denyWrite}` and `network{allowedDomains, deniedDomains, strictAllowlist, allowUnixSockets, allowLocalBinding, …}` (`src/sandbox/sandbox-config.ts:929-963`, `:677-918`). Reads are allowed by default with a narrower `denyRead` winning inside an `allowRead`; writes are denied by default with `denyWrite` beating `allowWrite` (`README.md:119-120`). Mandatory write denies (`.gitconfig`, rc files, `.claude/agents`, `.git/hooks`, …) cannot be exempted (`sandbox-utils.ts:13-42`). Enforcement is a generated Seatbelt profile with default deny (`macos-sandbox-utils.ts:1049-1085`) or bubblewrap with `--unshare-net/pid/user` and socat bridges to a host proxy (`linux-sandbox-utils.ts:3469-3761`). Violations are a 100-entry ring; on Linux they are "diagnostic hints" that must never gate a decision (`linux-violation-monitor.ts:71-74`). "It has no command-level allow/deny. The policy is purely about resources."
- **sandbox-sdk** (Cloudflare): `exec(cmd: string[], {cwd, env, user, signal, pty, stdin, stdout, stderr})` — an argv, no shell string, **no timeout option** (timeouts are the application's job, `docs/architecture.md:57`). Restrictions are container-level: `enableInternet:false` plus `interceptOutbound*` to a Worker, instance presets, `hardTimeout`, inbound only via `getTcpPort`. No path policy; S3 mounts carry `read-only | read-write`. "This Worker runs any command" (`examples/outbound-workspace/README.md:66`).

### 7. The in-process bash interpreters: limits tables, allow-lists, revocable leases, allow-only capabilities `[READ/sub]`

- **just-bash**: the threat model's primary adversary is the untrusted script author, "an AI agent or user" (`THREAT_MODEL.md:11-27`); host-provided `fs`, `fetch`, `customCommands` are trusted and "can bypass all sandboxing by design" (`:31-38`). `ExecutionLimits` has ~45 fields in two profiles (`src/limits.ts:163-261`): `maxCommandCount` 100 000 → 10 000, `maxLoopIterations` 100 000 → 10 000, `maxExecutionTimeMs` 1 h → 30 s, `maxOutputSize` 256 MiB → 10 MiB, `maxLiveBytes` 512 MiB → 64 MiB, `maxFileDescriptors` 4096 → 1024; `maxCallDepth` 100 and `maxExecDepth` 64 in both. `trusted: false` keeps the global-blocking defence active for a host command (`interpreter/builtin-dispatch.ts:1020-1023`); every host command gets its own budget and a revocable membrane over `fs`/`env`/`exec` (`:110-140`). Network is off unless `network`/`fetch` is passed; `allowedUrlPrefixes` is exact-origin plus segment-safe path prefix, no globs; `allowedMethods` defaults to `GET, HEAD` (`src/network/types.ts:56-133`, `fetch.ts:35`). **Commands are removed by omission from an allow-list** (`commands?: CommandName[]`, `Bash.ts:191-196`); there is no deny-list.
- **bashkit**: profiles `Hardened | Standard | Interactive` (`crates/bashkit/src/profile.rs:14-24`). `ExecutionLimits`: `max_commands` 10 000 → 2 500 (called the "fuel model"), `timeout` 30 s → 10 s, `max_stdout_bytes` 1 MiB → 256 KiB, `max_work_units` 100 M → 25 M, `max_function_depth` 16 hard (`limits.rs:53-175`, `profile.rs:136-161`); `SessionLimits` persist across calls (`max_exec_calls` 1 000). Every exec gets one budget and one capability lease, `ACTIVE → REVOKING → REVOKED`; retained handles fail with "execution capability revoked" (`execution_capability.rs:11-32`); `insert_trusted` is the explicit escape hatch (`builtins/mod.rs:446-476`). A `builtin_filter` predicate drops builtins; a `before_exec` hook can cancel (`lib.rs:2133-2139`, `hooks.rs:12-23`). Network is default-deny, exact scheme+host+port.
- **amla-sandbox**: method patterns are `/`-segment globs (`*` one segment, `**` zero or more) with a subset relation for attenuation (`capabilities/patterns.py:34-214`); parameter constraints are `lt le gt ge eq ne in not_in starts_with ends_with contains exists` with AND/OR nesting (`constraints.py:70-123`); capabilities compose by OR, **there is no deny** (`runtime/wasm.py:1153-1207`); each `ToolCallCap` has `max_calls`; the check runs host-side before every tool call and returns `permission_denied` to the guest (`:1312-1350`). Limits: `max_steps` 10 000 host-loop steps, `max_tool_result_size` 10 MB; **no fuel, memory cap or wall clock in the Python layer** (default `wasmtime.Engine()`; grep for `fuel|epoch|set_limits` empty).

### 8. Plan 9: the namespace is the policy; exec is read plus a bit; sealing is a device mask `[READ/sub]`

- `sysexec` resolves its argument with `namec(file, Aopen, OEXEC, 0)` — no path search in the kernel (`9front:sys/src/9/port/sysproc.c:297-346`). `/bin` is a union assembled by the namespace file: `bind /$cputype/bin /bin; bind -a /rc/bin /bin` (`9front:lib/namespace:25-27`). `OEXEC` is "execute, == read but check execute permission" (`sys/include/libc.h:649`); after the check `openmode` turns it into `OREAD` (`sysfile.c:180-188`). **The file server enforces the bit**, not the kernel: `devpermcheck` (`dev.c:335-352`), lib9p `hasperm` (`lib9p/srv.c:420-431`), hjfs, gefs. A walk needs search on each directory (`hjfs/fs2.c:63`; pjdfstest `tests/open/05.t:4`: EACCES "when search permission is denied for a component of the path prefix").
- `RFNOMNT` is a device mask: `nomntdevs = "|decp"` (pipe, dup, env, cons, proc); everything else, `#M` included, is masked, so no new mounts (`sysproc.c:30-34`, `pgrp.c:150-156`). The mask survives `RFCNAMEG` and only ever grows (`pgrp.c:107-111`, `:164-186`). `bind` still works under the mask but only rearranges names already reachable.
- Policy files: `namespace(6)` has `mount`, `bind`, `cd`, `unmount`, `clear`, `.`, `chdev` (`sys/man/6/namespace:32-85`). A restricted service gets a file that binds in exactly what it needs and then `chdev -r Ms` seals it (`rc/bin/service/!tcp80.namespace:1-24`); `auth/box` builds a view holding only the named paths (`sys/src/cmd/auth/box.c:62-107`, `:194-237`). `exportfs -r root -P patterns -R` exports a subtree, filtered, read-only (`sys/man/4/exportfs:46-80`).
- Who writes `/$cputype/bin`: the proto file gives `amd64/bin` mode `d775` with `uid=sys gid=sys` (`sys/lib/sysconfig/proto/distproto:1-4`, `:139-145`). Everyone else gets `r-x`.
- Synthesis: there is no exec allow-list and no setuid. Deciding what may run means deciding what names exist; deciding who may run means the x bit on the file, checked by the server that owns it. `plan9port` has no kernel namespaces at all (`src/lib9/getns.c:31-58`).

### 9. The reference evaluator `[EXECUTED]`

`experiments/s6/policy_eval.py` is a 330-line table-driven evaluator. Inputs: a parsed command (program, argv, the verbs it will need with their paths and facts), the caller's rung per prefix, the host's mount facts (effective caps, read-only mounts, a program mask, the bin table, the builtins), and a `Budgets` record. It runs the pinned order — resolve program, capability, grammar, permission, budgets — and answers with the classified kind. Output over 33 cases (`experiments/s6/policy_eval.out`):

```
case                                                                                   caller     verdict
1  list at list                                                                        bob        ALLOW
2  cat at list                                                                         bob        DENY  vfs.permission_denied — read needs read on /x.md; bob holds list
3  cat at read                                                                         alice      ALLOW
4  rm -rf at read_write (trash, reversible)                                            alice      ALLOW
5  rm -rf at contribute, not own                                                       bob        DENY  vfs.permission_denied — delete needs read_write on /notes; bob holds contribute
6  rm own row at add (owner floor)                                                     bob        ALLOW
7  cat 10k files (batch contract) — bytes over the stdout budget                       alice      ALLOW — [warning: vfs.budget_exhausted.truncated: stdout would be 209715200 bytes; cut at 4194304, rows served are whole]
8  cat 25k files — over the fan-out budget                                             alice      ALLOW — [warning: vfs.budget_exhausted.truncated: 25000 paths exceed the fan-out budget of 10000; the first 10000 are served, refine the scope]
9  a program that loops forever                                                        alice      ALLOW — [runtime: vfs.timeout after 10.0s (epoch deadline); rows already emitted are kept]
10 a program that burns fuel                                                           alice      ALLOW — [runtime: vfs.budget_exhausted after 2000000000 instructions (fuel trap); not retryable as-is]
11 install into bin at add (fresh name)                                                installer  ALLOW
12 install into bin at list                                                            bob        DENY  vfs.permission_denied — write needs add on /.agents/bin/yq.wasm; bob holds list
13 overwrite another's program at add                                                  installer  DENY  vfs.permission_denied — write needs contribute on /.agents/bin/jq.wasm; installer holds add
14 sweep (developer plane)                                                             alice      DENY  vfs.unrecognized — 'sweep' is a developer-plane verb; the shell has no such word
15 posture (developer plane)                                                           alice      DENY  vfs.unrecognized — 'posture' is a developer-plane verb; the shell has no such word
16 git (no such program)                                                               alice      DENY  vfs.unrecognized — no builtin or installed program named 'git'
17 jq at read on bin and on the data                                                   alice      ALLOW
18 jq at list on bin (can name, not read)                                              bob        DENY  vfs.permission_denied — run needs read on /.agents/bin/jq.wasm; bob holds list
19 curl wants the network                                                              alice      DENY  vfs.unsupported — 'curl' wants capability 'net'; the kernel has none
20 pipeline grep | wc                                                                  alice      ALLOW
21 write into a deny_ops-masked mount                                                  alice      DENY  vfs.unsupported — operation 'write' is not declared by the storage mounted at /archive
22 write into a permissions='read' mount                                               alice      DENY  vfs.read_only — the mount at /vendor is read-only
23 rm when the host masks rm                                                           alice      DENY  vfs.unsupported — program 'rm' is masked by the host (deny_ops on programs)
24 read the trash view                                                                 alice      ALLOW
25 write into the trash view                                                           alice      DENY  vfs.invalid — write may not address the reserved tree /.vfs/trash/notes/x
26 anonymous cat under a none posture                                                  anon       DENY  vfs.unauthenticated — /secret.md is 'none' to everyone; a named authority is needed
27 anonymous write under an add posture                                                anon       ALLOW
28 cp: read on the source, add at the target                                           alice      ALLOW
29 mv: read_write on the source                                                        alice      DENY  vfs.permission_denied — move needs read_write on /x.md; alice holds read
30 a program writing into bin as a caller holding read on bin (no more than its caller) alice      DENY  vfs.permission_denied — write needs add on /.agents/bin/evil.wasm; alice holds read
31 a hidden path in a glob (never revealed)                                            alice      ALLOW
32 cat a hidden path                                                                   alice      DENY  vfs.not_found — /secret/k.md is not visible to alice
33 a 200-stage pipeline                                                                alice      DENY  vfs.invalid — 200 stages exceed the stage budget of 64
```

What the run shows: every verdict a command can get is one of the kinds the envelope already has. No case needed a new kind, a new rung, or a judgement of the command text. The two warnings and the two runtime outcomes are the only things the string-judging peers call "policy" that the gate does not already give.

---

## What this means for vfs

### A. The taxonomy: what a policy can be about

Each row names the dimension, what vfs has today, the gap, and the recommendation.

| # | Dimension | vfs mechanism today | Gap | Recommendation |
|---|---|---|---|---|
| (a) | Which programs may run (an allow-list of names) | None. `deny_ops` masks verbs per mount, never names. Builtins do not exist yet. | A host cannot say "no `jq` here". | **Two existing levers before any new one.** A program nobody may run is a bin row at posture `list` (visible, not readable, so not runnable). A program nobody should see is not bound into `/.agents/bin` at all (Plan 9: policy is what you can see). **One small new lever:** `deny_ops` gains program names on the shell's mount meta, refusing `unsupported`, exactly as a masked verb. No allow-list: vfs's catalogue of builtins is closed by construction, and `just-bash`'s allow-list-by-omission is the same thing as "not bound in". |
| (b) | Which verbs a program may call (the fs capability narrowed per program) | The program gets the vfs verbs as its capability, closed over the caller's `Authority`. `Narrowing` exists with one value, `NONE`. | No attenuation per program. | **v1: the capability is the full verb set under the caller's authority; attenuation is the ABI's job later.** amla's "child pattern ⊆ parent" and bashkit's revocable lease are the precedent: a program *manifest* may declare the verbs it needs, and the kernel may hand it only those. That is a program-ABI fact (S2's study), not an execution-policy fact. `Narrowing` is the seam when it lands. |
| (c) | Which paths (per principal) | The ladder, per prefix, per principal, at every verb (`VERB_RUNGS`, the owner floor, postures, grants). | None. | **A program runs AS the caller and holds exactly the caller's rungs.** It can never hold more (argued in B). It may hold less (b). |
| (d) | Resource budgets | `grep`/`glean` budgets per call; warning-severity `truncated`; `budget_exhausted`, `timeout`, `cancelled` kinds. | No per-command, per-program or per-session budgets. | **The budget set in D.** Shape caps refuse `invalid`; fan-out and output caps truncate with a warning; fuel and wall time trip at runtime. Session-wide counters (bashkit `SessionLimits`) are a fork. |
| (e) | Network | None, by design. The kernel has no network capability to hand out. | — | **A program asking for the network is `unsupported`** (the capability is undeclared, same as a storage not declaring a verb; case 19). If the kernel ever networks, it is a kernel capability with its own allow-list, never a program's own socket. |
| (f) | Who installs programs | `/.agents` is an ordinary reserved tree; a `tools`/`skills` unit is installed by `write` under the ladder. No `bin` family yet. | `bin` is not a family. | **Add `bin` to `AGENT_FAMILIES`; install is `write` under the ladder** (rule E). |
| (g) | Who may run which (per-path vs per-principal) | `run` at `read` in the table; nothing reads it; the open question splits the demand into 039 (per-path rights set) and 058 (an `execute` level above `read_write`). | The question is parked because nobody asked. | **Both halves are already the ladder once `run`'s rung is `read` on the program row** (rule C). Per-principal = a grant of `read` on the bin row. Per-path = a posture of `list` on the bin prefix. The open question closes; 039 stays archived; no `execute` level. |

### B. A program never holds more than its caller — and why that is a theorem, not a policy

- The capability a program receives is the verb set *bound to the caller's `Authority`* (July memo §4, `:169-173`). The gate re-derives rights from that value on every call (`authority.py:118-126`). There is no second identity in scope. So the only way a program could gain a right is if the kernel minted a different `Authority` for it — and the four construction doors are closed to anything but vfs's own code (`authority.py:17-22`). `[INFERRED]` from `[READ]`.
- Every peer agrees on the direction. Codex: inner commands "can add restrictions, but cannot grant the executable trust". Plan 9 has no setuid; `auth/box` only removes names. amla's attenuation is subset-only; bashkit's `insert_trusted` is the named exception and it is for the *host*, not the script. eve: the sandbox has no secrets. Nobody has a mechanism by which a program raises its caller.
- The consequence for the bin directory: a program at `/.agents/bin/evil.wasm` that tries to write into `/.agents/bin` writes with the caller's rung there (case 30). A caller holding `read` on bin can run everything and install nothing. That is exactly Plan 9's `r-x` on `/amd64/bin` for everyone but `sys`.
- The one thing that *looks* like "more" is the `system` actor. A batch job or the router's own control plane runs as `Authority.system()` (`base.py:124-126`). A program must never be dispatched under it. Rule: **the `cli` meta-verb and `run` refuse an authority whose actor is the system principal at the params gate** — classify `invalid`, because only vfs's own code can construct one. `[INFERRED]`.

### C. `run`'s rung: keep `read`

The rule in ADR 080 pin 6 is "a verb's rung is the rung of the field it reads." Apply it:

1. **What does `run` read?** The program row's body — the wasm bytes, the tool definition, the manifest. A `list` holder sees the name and kind and nothing else (pin 2). You cannot execute bytes you cannot read. So `run` needs `read` on the program row. That is the entry already in the table (`ops.py:156`).
2. **Plan 9 says the same thing in one line.** `OEXEC` is "execute, == read but check execute permission" (`libc.h:649`). Exec *is* read plus one extra bit. vfs chose a total order over bits (ADR 080, "Independent bits … Rejected"), so the extra bit has nowhere to live — and it does not need to. Its two jobs are covered: "readable but not runnable" is a bin row you may `read` but that is not bound into the shell's program table (the namespace, not a bit); "runnable but not readable" is the blind-execute case Plan 9 also cannot express cleanly (its `--x` on a binary still lets the loader read it), and vfs has no use for it.
3. **An `execute` level above `read_write` is backwards.** The open question's per-principal half proposes it (`open-questions.md:60`, `:78`). But execution is not more dangerous than any verb the program can call, because the program holds no more than the caller (B). `execute > read_write` would say "you may trash everyone's rows and grant rights, but you may not run `wc`". Spec 039's own signed-off policy — "`read` implies execute" — is `run = read` in the ladder's words. `[INFERRED]`.
4. **The per-path half is a posture.** "Runnable except these paths" (039's `execute_not=["/deploy"]`) is `posture("/.agents/bin/deploy", "list")`: everyone sees the names, nobody reads the bodies, nobody runs them; a grant of `read` to one principal re-opens it for that principal. That is strictly more expressive than 039's user-blind carve-out. `[INFERRED]`.
5. **Where the gate fires.** Today no gate reads `run`'s rung because no storage implements it (finding 1). When the shell lands, the program table is a directory, resolving a program name is a `read` of the row, and that read is the gate. No new code path: the `cli` meta-verb reads `/.agents/bin/<name>` through the public `read` and gets `permission_denied` or `not_found` by the rules every other row follows (ADR 065 rule 2: a `list` row answers `permission_denied`, a `none` row `not_found`). Case 18 and case 32 show both.
6. **Recommendation:** amend the docstrings that say `run` "waits for its own axis" (`ops.py:169-171`; ADR 080 pin 9's "`run` on its own axis") to "`run` is `read` on the program row." Close the open question with pointers here. Leave 039 archived.

### D. The budget set

Names mirror grep's: a `_BUDGET` constant per bound, a tripped budget truncates with a warning that names the budget and the refine move, and nothing is ever a declared scale cap (CLAUDE.md: "never design toward a hard scale cap"). Numbers are starting points chosen against the peers' hardened profiles and vfs's own batch contract; the 10 000-file batch is a *floor*, not a ceiling.

| Budget | Default | When it fires | Classification | Peers' value for calibration |
|---|---|---|---|---|
| `STAGE_BUDGET` | 64 | pre-flight, on the parsed line | `invalid` (refuse whole) | just-bash `maxExecDepth` 64; bashkit `max_subshell_depth` 32 |
| `ARGV_BYTE_BUDGET` | 128 KiB | pre-flight, after expansion | `invalid` | Linux `MAX_ARG_STRLEN` is 128 KiB per argument; bashkit `max_input_bytes` 10 MiB / 1 MiB |
| `FANOUT_BUDGET` | 10 000 paths per stage per call | at dispatch, per stage | serve the first N, `truncated` warning | the batch contract itself; grep `CANDIDATE_BUDGET` 25 000 |
| `STDOUT_BYTE_BUDGET` | 4 MiB per stage | runtime, on the pipe and on the final render | `truncated` warning, rows served whole | bashkit 1 MiB / 256 KiB; eve 50 KiB; just-bash 256 MiB / 10 MiB; grep `POSTING_BYTE_BUDGET` 4 MiB |
| `WALL_TIME_BUDGET` | 10.0 s per command line | runtime, epoch deadline across every stage | `timeout`; rows already emitted kept | grep and glean 10.0 s; bashkit 30 s / 10 s; just-bash 30 s hardened |
| `FUEL_BUDGET` | 2 × 10⁹ instructions per program | runtime, wasmtime fuel | `budget_exhausted`, not retryable as-is | no peer meters fuel (amla and llm-wasm-sandbox differ; the July memo names wasmtime fuel) |
| `MEMORY_BYTE_BUDGET` | 256 MiB linear memory per program | instantiation, `Store.set_limits` | `budget_exhausted` | just-bash `maxLiveBytes` 512 MiB / 64 MiB |
| `VERB_CALL_BUDGET` | 10 000 dispatches per program run | runtime, counted at the capability | `budget_exhausted` | bashkit `max_commands` 10 000 ("fuel model"); amla `max_calls` per capability; just-bash `maxCommandCount` |

Rules that bind the set:

- **Count operations, never time, in tests** (CLAUDE.md). `WALL_TIME_BUDGET` is the one clock, and it is a runtime kill switch with a classified outcome, never an assertion.
- **A fan-out over the budget is not a refusal.** `cat` over 25 000 files serves the first 10 000 and warns (case 8). Refusing it would turn the batch contract into a cap.
- **A truncation never drops a row it has started.** Rows are whole or absent (grep's rule, `grep.py:41-43`).
- **Fuel and wall time are both needed.** Wall time stops a program stuck in a host call; fuel stops a hot loop deterministically and is what makes a run reproducible in a test oracle. wasmtime exposes both (`wasmtime-py:tests/test_store.py:32-59` per the July memo).
- **No session-wide counter at v1.** bashkit's `SessionLimits` (`max_exec_calls` 1 000) is the only peer with one, and it exists because bashkit sessions are long-lived shells. vfs sessions are an `Authority` plus a lifecycle (`session.py:1-14`), and the host loop already counts turns. Fork F3.

### E. The bin-directory install rule

- **`bin` is the third `AGENT_FAMILIES` entry**, beside `tools` and `skills` (`paths.py:52`). `/.agents/bin/<name>` is a file row whose body is the program (wasm bytes or a text program); like a skill, "its location … is what makes it a" program — discovery is by path, never by kind (`skills.py:13-17`). A program file is data until run (July memo §5 risk 5).
- **Installing is `write`, under the table.** A fresh name mints at `add`; an occupied name overwrites at `contribute` or own; `delete` at `read_write` or own; a tombstoned name is a restore at `read_write` or own (ADR 080 pin 3, pin 9). Every overwrite mints a version, so a bad install is reversible by `restore`. Cases 11–13.
- **The posture of `/.agents/bin` defaults to `read`.** Everyone may name and run every installed program; installing needs a grant. This is Plan 9's `sys:sys d775` — `r-x` for the world — and the rule that a program never holds more than its caller makes it safe: a malicious install cannot escalate, it can only spend the budget and trash what its *caller* could already trash. An operator who wants a locked catalogue sets the posture to `list` and grants `read` per principal.
- **An agent that installs its own tools holds `add`.** It can install, re-install its own (the owner floor), and cannot overwrite another's. A name collision answers `exists` (a `write` without overwrite at an occupied name) — the agent picks another name or asks for `contribute`.
- **Shadowing is not a feature at v1.** Plan 9's union bind lets `/rc/bin` shadow `/amd64/bin` per process. vfs has one directory and one namespace per mount; a per-agent `PATH` of several bin directories is fork F6.
- **A builtin name cannot be installed over.** `tee /.agents/bin/ls` must refuse `invalid`: the kernel's words are reserved, and a program shadowing `grep` would reopen the side door ADR 069 closed ("`grep` in this shell can only resolve to `storage.grep()`"). `[INFERRED]`.

### F. The classified refusals

One table, from the evaluator's output and the envelope's kinds:

| Situation | Kind | Severity | Who emits it |
|---|---|---|---|
| no builtin or installed program by that name; a developer-plane word | `unrecognized` | error | the shell's dispatch (the only producer of `unrecognized`) |
| the verb is not declared by the mount, or `deny_ops` masks it; the program name is masked by the host; the program wants a capability the kernel has none of (network) | `unsupported` | error | the capability gate (the only producer of `unsupported`) |
| a mutation addresses `/.vfs`; a program would shadow a builtin; the authority's actor is the system principal; stages or argv over budget | `invalid` | error | the params/grammar gate |
| the mount or prefix is `permissions="read"` | `read_only` | error | the permission map |
| the caller holds a rung below the verb's need on a visible row | `permission_denied` | error | the storage gate |
| the row is `none` to the caller | `not_found` | error | the storage gate (never reveals) |
| anonymous at a posture below the need | `unauthenticated` | error | the storage gate |
| a mutation hits a live bind site (`rm -rf /` at the root) | `busy` | error | the router's busy guard (`_BUSY_GUARDED_OPS = {delete, restore, sweep}`, `base.py:122`) |
| fan-out or output over budget, rows served whole | `budget_exhausted.truncated` | **warning** | the shell, naming the budget and the refine move |
| wall time spent | `timeout` | error (rows already emitted ride) | the runtime |
| fuel, memory or verb-call budget spent | `budget_exhausted` | error | the runtime |
| the host cancelled the run | `cancelled` | error | the runtime |

No new kind is needed. Two kinds get a new producer: `truncated` from the shell (today only grep/glean emit it) and `budget_exhausted` from the runtime (today only the hop/TTL and authority budgets).

### G. Pre-flight versus dispatch-only: the cases

The question: does the shell need to judge the command string before running it, or is "every gate fires on the real verb" enough?

| Case | What the string-judging peers do | What the vfs gate does without judging the string |
|---|---|---|
| `rm -rf /` | Codex heuristic: `-rf` is dangerous → Prompt; Claude Code: prompts unless `Bash(rm *)` is allowed; deepagents CLI: not on the read-only allow-list. | `delete` on `/` is a live bind site → `busy`; `delete` on `/notes` at `read_write` → trash, reversible, `restore` undoes it (case 4). Nothing is destroyed; `sweep` is the destroyer and the shell has no such word (case 14). No pre-flight needed. |
| a 10k-file `cat` | just-bash/bashkit cap output bytes; eve caps at 50 KiB. | Served under `FANOUT_BUDGET` and `STDOUT_BYTE_BUDGET` with a `truncated` warning (cases 7–8). The budget is a pre-flight *parameter*, not a judgement. |
| a program that loops forever | bashkit `timeout` + cancellation token; just-bash `maxExecutionTimeMs`; eve yields after 30 s. | `WALL_TIME_BUDGET` epoch deadline → `timeout`; `FUEL_BUDGET` → `budget_exhausted` (cases 9–10). Runtime, not pre-flight. |
| a program that writes to `/.agents/bin` | Claude Code and sandbox-runtime: protected paths, mandatory write denies. | The ladder on that prefix: `write` needs `add`/`contribute` there, and the program holds its caller's rung (cases 11–13, 30). No protected-path list: the prefix is already a posture. |
| `sweep` | — | Developer plane; `unrecognized` (case 14). The word never parses. |
| `curl` | Codex `network_rule`; sandbox proxies. | `unsupported`: the kernel declares no network capability (case 19). |
| `$(...)`, backticks, heredocs | gemini-cli and the deepagents CLI hard-deny; opencode's scanner refuses as opaque; Codex judges the whole argv as one unit. | Irrelevant: whatever the grammar expands to is a program name and verbs, each gated. The grammar question (what the shell accepts) is S1's; the policy question is answered the same way for every expansion. |

Conclusion `[INFERRED]`: the peers judge strings because their shell can run *anything* and their only runtime boundary is an OS sandbox over paths and hosts; the string judgement decides whether to ask a human and whether to lift that sandbox. vfs has no human to ask (it allows or classifies; the host harness's own `can_use_tool` is where `ask` lives), and nothing to lift. The three pre-flight jobs that remain are the ones the evaluator does before the permission step: **resolve the program** (which is itself a gated `read`), **refuse over-shape input** (`STAGE_BUDGET`, `ARGV_BYTE_BUDGET`), and **set the budgets**. Everything else fires on the real verb.

### H. What to adopt and what to reject

Adopt:
- The pinned gate order as the policy, with `run = read` on the program row (C).
- A program's authority is the caller's `Authority`, unchanged at v1; `Narrowing` is the attenuation seam (B, (b)).
- `bin` as an `AGENT_FAMILIES` entry with posture `read` by default; install as `write` (E).
- The budget set in D, with grep's warning discipline.
- `deny_ops` extended to program names on the shell's mount, classified `unsupported` ((a)).
- The classified-refusal table in F; no new kinds.
- bashkit's revocable lease as the shape of the capability handed to a program: it dies with the run, and a retained handle fails closed. This is an ABI fact to carry into S2's design.

Reject:
- An `execute` rung or level anywhere on the ladder (C.3).
- A command-string policy language (Starlark prefix rules, `Bash(git *)` patterns): it judges invocation text, and every peer says it is not a boundary around the program (findings 2–4).
- An `ask` verdict inside vfs: there is no human on the call; `ask` is the harness's job via its own tool-permission layer.
- A program allow-list on the mount as the primary lever: namespace binding and bin-row postures already express it; the allow-list would be a second source of truth.
- A protected-path list for the bin directory: it is a posture on a prefix, like every other prefix.
- Session-wide counters at v1 (F3).

---

## Forks for the ADRs

**F1. Per-path execute rung vs per-principal grant vs program allow-list on the mount.**
- (i) A rights set with `execute` (039's shape) — user-blind, per prefix.
- (ii) An `execute` level above `read_write` in the grant ladder (the open question's 058 half).
- (iii) **`run = read` on the program row; per-principal is a `read` grant on the bin row, per-path is a `list` posture on the bin prefix; a program nobody should see is not bound in.**
- (iv) A `programs` allow-list on the shell's mount meta.
- Lean: **(iii)**, with `deny_ops` extended to program names as the one host-side mask (a deny, not an allow-list). (i) and (ii) each add a dimension the total order cannot hold; (iv) duplicates the namespace.

**F2. Pre-flight judgement vs dispatch-only.**
- (i) A pre-flight verdict on the parsed line (Codex/Claude Code shape).
- (ii) **Dispatch-only: resolve the program (a gated read), refuse over-shape input, set budgets; every other gate fires on the real verb.**
- (iii) Dispatch-only plus a manifest-declared verb set per program, attenuating the capability before the run (amla's subset rule).
- Lean: **(ii) at v1, (iii) as the ABI matures** — (iii) is not policy, it is the program's declared shape, and it belongs to the ABI ADR.

**F3. Are limits a mount property or a session property?**
- (i) Per mount, on `MountMeta` beside `deny_ops` — a host tunes the budgets where it binds the shell.
- (ii) Per session, on `Session` — a host tunes per principal (bashkit's `SessionLimits`).
- (iii) **Per call with declared module defaults, as grep does; the mount may tighten, never loosen** (the `MNT_READONLY` composition rule already in `permissions.py`).
- Lean: **(iii)**. Budgets are kernel constants with a tightening knob at the mount; a session-wide counter is a later addition if a host asks, and it composes as a second tightening layer.

**F4. May a host deny a builtin by name (`deny_ops` extended to programs)?**
- (i) No: a builtin is a verb, and `deny_ops` on the verb already masks it (`rm` is `delete`; masking `delete` masks `rm` — case 21's shape).
- (ii) **Yes for installed programs (names in `/.agents/bin`), no for builtins: a builtin is reachable only through its verb, so masking the name and not the verb would be a lie about capability** — and read-family builtins cannot be masked for the same reason `deny_ops` refuses read-family verbs (`base.py:849-852`).
- (iii) Yes for both, with the read-family exception lifted for the shell.
- Lean: **(ii)**. The refusal stays `unsupported`, so a masked program and an undeclared verb look the same to the agent, as today.

**F5. The default posture of `/.agents/bin`.**
- (i) **`read` for everyone** (Plan 9's `r-x`; a program never holds more than its caller, so running is safe by construction).
- (ii) `list` for everyone, `read` by grant (a locked catalogue).
- (iii) `none` (the bin directory is invisible until granted).
- Lean: **(i)**, because an agent "shouldn't feel limited" (Clay, 2026-10-15) and the ladder makes a bad program harmless beyond its budget; (ii) is a one-line posture change for an operator who wants it.

**F6. One bin directory vs a per-agent `PATH` of several.**
- (i) **One `/.agents/bin` per mount; no shadowing; a builtin name may not be installed.**
- (ii) A `PATH` list of bin directories per session, Plan 9's union bind, later program shadows earlier.
- Lean: **(i) at v1**. (ii) is where "where does an agent's bundle live" (`open-questions.md:273-279`) meets the shell, and it should be decided with that question, not here.

**F7. The system actor and the shell.**
- (i) A `cli`/`run` call under `Authority.system()` is refused `invalid` at the params gate.
- (ii) It is allowed and the program runs with no gate (a batch loader's convenience).
- Lean: **(i)**. The one way a program could hold more than a caller is to be handed the system actor; close it at the door.

---

## Sources

- vfs live tree (read 2026-10-15): `src/vfs/ops.py`, `src/vfs/base.py` (`MountMeta` 130-160, `_validate_deny_ops` 846-862, `run` 1548-1564, `_route_single` 1686-1722, `_gate_entry` 2829-2873, `_BUSY_GUARDED_OPS` 122), `src/vfs/authority.py`, `src/vfs/permissions.py`, `src/vfs/session.py`, `src/vfs/params.py:357-361`, `src/vfs/paths.py:51-52`, `src/vfs/skills.py:1-20`, `src/vfs/storage/protocol.py:346-355`, `src/vfs/storage/grants.py:1-40,72-91`, `src/vfs/storage/backends/database/grep.py:1-60,113-126,318-330`, `src/vfs/storage/backends/database/glean.py:137-146`, `src/vfs/results/kinds.py:24-115`, `tests/base/test_gates.py:165-200`; `context/decisions/080-*.md`, `context/decisions/069-*.md:108-125,292-306`, `context/specs/archive/039-execute-permission-tier/spec.md`, `context/open-questions.md:55-80,273-279`, `context/research/2026-07-24-hermetic-runtime-and-wasm-cli.md:160-180,260-280,350-372`.
- `codex` @ 16e578d (Apache-2.0): `codex-rs/execpolicy/{README.md,src/parser.rs,src/rule.rs,src/decision.rs,src/policy.rs,src/amend.rs,examples/example.codexpolicy}`, `codex-rs/core/src/exec_policy.rs`, `codex-rs/core/src/exec_policy/executable_identity.rs`, `codex-rs/shell-command/src/bash.rs`, `codex-rs/shell-command/src/command_safety/is_dangerous_command.rs`, `codex-rs/protocol/src/protocol.rs:1097-1249`, `codex-rs/core/src/tools/{sandboxing.rs,orchestrator.rs}`, `codex-rs/sandboxing/src/manager.rs`.
- Claude Code docs, fetched 2026-10-15: https://code.claude.com/docs/en/permissions (redirect target of https://docs.claude.com/en/docs/claude-code/permissions), https://code.claude.com/docs/en/sandboxing.
- `claude-agent-sdk-python` @ aada024 (MIT): `src/claude_agent_sdk/types.py:25-27,134-161,259-276,2218-2290`.
- `gemini-cli` @ d42e3f1e7 (MIT; dirty, read via `git show HEAD:`): `packages/core/src/utils/shell-utils.ts`, `packages/core/src/tools/shell.ts`, `packages/core/src/config/config.ts:55-58,638-671`, `packages/cli/src/utils/sandbox.ts:37-44,194-202`, `packages/cli/src/config/sandboxConfig.ts:31-104`.
- `opencode` @ 13263f30ed (MIT): `packages/core/src/v1/config/permission.ts`, `packages/core/src/permission/{permission.ts,saved.ts}`, `packages/core/src/util/wildcard.ts`, `packages/core/src/tool/plugin/shell.ts`, `packages/core/src/shell/{parse.ts,scan.ts}`, `packages/core/src/file-access.ts`, `packages/schema/src/permission.ts`.
- `deepagents` @ 0bf167654 (MIT): `libs/deepagents/deepagents/middleware/{filesystem.py,_fs_interrupt.py,subagents.py}`, `libs/deepagents/deepagents/graph.py`, `libs/deepagents/deepagents/backends/{filesystem.py,local_shell.py,protocol.py,utils.py}`, `libs/code/deepagents_code/{agent.py,config.py}`. `deepagentsjs` @ 9f3bfd5 (MIT): `libs/deepagents/src/middleware/fs.ts`, `backends/{protocol.ts,filesystem.ts,local-shell.ts}`, `permissions/{types.ts,enforce.ts}`.
- `eve` @ 5666d2f0d (Apache-2.0): `packages/eve/src/shared/{principal-scope.ts,sandbox-network-policy.ts}`, `packages/eve/src/public/memory/{scope.ts,index.ts}`, `packages/eve/src/context/keys.ts`, `packages/eve/src/execution/sandbox/{bash.ts,require-sandbox.ts,truncate-output.ts}`, `packages/eve/src/tools/provided/bash.ts`, `docs/{concepts/security-model.md,tools/human-in-the-loop.md,agent-config.md,sandbox/index.mdx,patterns/multi-tenant-memory.md}`.
- `sandbox-runtime` @ 9a277e5 (Apache-2.0): `README.md`, `src/sandbox/{sandbox-config.ts,sandbox-manager.ts,sandbox-utils.ts,macos-sandbox-utils.ts,linux-sandbox-utils.ts,linux-violation-monitor.ts,sandbox-violation-store.ts,domain-pattern.ts}`. `sandbox-sdk` @ a080a65 (Apache-2.0): `README.md`, `docs/architecture.md`, `templates/openai-agents-api/worker-configuration.d.ts:3475-3576`, `examples/outbound-workspace/`, `packages/sandbox/src/s3-mount/{contracts.ts,gateway-policy.ts}`.
- `just-bash` @ 9ab0e0d (Apache-2.0, `packages/just-bash/LICENSE`): `THREAT_MODEL.md`, `packages/just-bash/README.md`, `packages/just-bash/src/{limits.ts,Bash.ts,types.ts,custom-commands.ts,interpreter/builtin-dispatch.ts,network/types.ts,network/fetch.ts,fs/overlay-fs/overlay-fs.ts,fs/real-fs-utils.ts}`.
- `bashkit` @ b7904a4 (MIT): `crates/bashkit/src/{profile.rs,limits.rs,execution_capability.rs,lib.rs,hooks.rs,builtins/mod.rs,network/allowlist.rs}`, `knowledge/security/request-lifecycle.md`, `docs/{security.md,networking.md,configuration.md,snapshotting.md}`.
- `amla-sandbox` @ 169384f (Python MIT; wasm runtime AGPL-3.0/BUSL-1.1, study only): `src/amla_sandbox/capabilities/{patterns.py,constraints.py,tool_call.py}`, `src/amla_sandbox/runtime/wasm.py`, `src/amla_sandbox/{sandbox.py,auth.py}`.
- `9front` @ a0806493 (dirty; no top-level licence): `sys/src/9/port/{sysproc.c,chan.c,dev.c,pgrp.c,sysfile.c,devcons.c,portdat.h}`, `sys/include/libc.h`, `lib/namespace`, `lib/namespace.ftp`, `rc/bin/service/!tcp80.namespace`, `rc/lib/rcmain`, `sys/src/libauth/newns.c`, `sys/src/cmd/auth/{none.c,box.c}`, `sys/src/cmd/aux/listen.c`, `sys/src/cmd/exportfs/`, `sys/src/cmd/hjfs/{auth.c,fs2.c}`, `sys/src/cmd/gefs/fs.c`, `sys/src/lib9p/srv.c`, `sys/lib/sysconfig/proto/distproto`, `sys/man/{2/fork,3/cons,4/exportfs,6/namespace}`. `plan9port` @ b6564bd9 (MIT): `src/lib9/getns.c`, `man/man3/auth.3`, `man/man1/namespace.1`. `pjdfstest` @ 85a8aea: `tests/open/05.t`.
- Experiment: `experiments/s6/policy_eval.py` and its output `experiments/s6/policy_eval.out` (run 2026-10-15 with `uv run python`).
