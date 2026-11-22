# Research: ready-made approval modes for interrupts

## The question

The interrupt design gives vfs one hook: a host hands vfs a policy function, vfs shows it every call before the call runs, and the policy returns allow, deny or interrupt. An interrupted call changes nothing and returns an `Interrupt` with an id, a reason and a preview. The host asks a person, records the answer with `fs.answer(id, allow=...)`, and the same call made again runs once.

The question here is the next layer up. A host should be able to pick a named mode instead of writing a function, the way Claude Code runs in a manual-review mode or an auto-accept mode. This memo studies how agent tools and frameworks split manual review from automatic acceptance, and recommends which built-in policies vfs should ship and how they are expressed.

Terms used throughout. A **mode** is a named preset that decides which actions run without asking. A **rule** is one allow, ask or deny entry matched against an action. **Review before** means the action waits for a person. **Review after** means the action lands at once and a person inspects it later, with a way to undo it. **Blast radius** is how much one action can touch. **Approval fatigue** is the habit of approving prompts without reading them.

Each claim carries its basis. READ means it was read in the named file or at the named URL. EXECUTED means a command was run in this study. INFERRED means it is reasoning from what was read.

## Sources

Every local clone was refreshed on 2026-11-21 with `git fetch origin` and a detached checkout of the branch `origin/HEAD` names; the license was checked after the refresh. [EXECUTED]

| Clone | Commit | Commit date | Default branch | License |
|---|---|---|---|---|
| codex | 140815f19c05 | 2026-11-21 | main | Apache-2.0 |
| opencode | 4d4a95a3239c | 2026-11-21 | dev | MIT |
| claude-agent-sdk-python | 3184360393a9 | 2026-11-20 | main | MIT |
| langchain | 8ff3cd30eebf | 2026-11-20 | master | MIT |
| langgraph | c6335a4255dc | 2026-11-20 | main | MIT |
| deepagents | 65d33b2c114d | 2026-11-21 | main | MIT |
| deepagentsjs | cc136b0ef58f | 2026-11-20 | main | MIT |
| openai-agents-python | 6c4e4a29cd08 | 2026-11-20 | main | MIT |
| adk-python | 2b90353cd2f1 | 2026-11-20 | main | Apache-2.0 |
| letta | 8816d3a85168 | 2026-10-18 | main | Apache-2.0 |
| eve | 5c52fbff40d9 | 2026-11-21 | main | Apache-2.0 |
| A2A | 5f931b8a25fe | 2026-11-18 | main | Apache-2.0 |
| modelcontextprotocol | b7e13978aa0b | 2026-11-21 | main | mid-transition from MIT to Apache-2.0, as its LICENSE file states |
| python-sdk | 77001c96f950 | 2026-11-05 | main | MIT |
| sandbox-runtime | 0bbebed0aa9a | 2026-11-12 | main | Apache-2.0 |

Clone notes. `gemini-cli` was skipped: `git status` reported 597 changed paths at d42e3f1e7fbd (2025-08-01), so it was not refreshed or studied; its current docs were read from GitHub instead. The `langchain` fetch reported a refname conflict on two unrelated branches; `master` fetched cleanly. `letta` now holds only a README that says its source moved to `letta-ai/letta-code`, which is not cloned, so Letta is not studied. `deepagentsjs` and `python-sdk` were refreshed and not cited. [EXECUTED; READ letta/README.md:5]

Web pages were fetched on 2026-11-21. Two figures that shape the recommendation, the 97% and 93% approval rates, were fetched a second time to confirm their wording. Pages that could not be reached are named under "What was not checked". [EXECUTED]

- Claude Code: https://code.claude.com/docs/en/permissions, https://code.claude.com/docs/en/permission-modes (read in part), https://code.claude.com/docs/en/settings, https://code.claude.com/docs/en/security, https://code.claude.com/docs/en/hooks (PreToolUse part), https://code.claude.com/docs/en/checkpointing, https://www.anthropic.com/engineering/claude-code-auto-mode, https://claude.com/blog/auto-mode-default-in-claude-code, https://claude.com/blog/auto-mode-in-production, https://www.anthropic.com/engineering/claude-code-sandboxing.
- Codex: https://developers.openai.com/codex/agent-approvals-security.md, https://developers.openai.com/codex/config-reference.md, https://developers.openai.com/codex/noninteractive.md, https://developers.openai.com/codex/concepts/sandboxing/auto-review.md.
- Gemini CLI, from https://raw.githubusercontent.com/google-gemini/gemini-cli/main/docs/: cli/cli-reference.md, reference/configuration.md, cli/plan-mode.md, reference/policy-engine.md, cli/trusted-folders.md, cli/checkpointing.md.
- Cursor: https://cursor.com/help/ai-features/terminal, https://cursor.com/docs/agent/security, https://cursor.com/docs/agent/security/run-modes, https://cursor.com/docs/reference/permissions, https://cursor.com/docs/enterprise/llm-safety-and-controls, https://cursor.com/help/ai-features/agent, https://cursor.com/docs/agent/chat/checkpoints, https://www.backslash.security/blog/cursor-ai-security-flaw-autorun-denylist.
- Cline: https://docs.cline.bot/features/auto-approve, https://cline.bot/blog/cline-v3-35, https://docs.cline.bot/features/yolo-mode, https://docs.cline.bot/features/plan-and-act, https://docs.cline.bot/features/checkpoints.
- GitHub Copilot in VS Code: https://code.visualstudio.com/docs/agents/run/approvals, https://code.visualstudio.com/docs/agents/reference/ai-settings, https://code.visualstudio.com/docs/agents/run/security.md, https://code.visualstudio.com/docs/agents/run/review-code-edits.
- Windsurf, now Devin Desktop: https://docs.devin.ai/windsurf/plugins/cascade/cascade-overview, https://docs.devin.ai/desktop/controls.md, https://docs.devin.ai/desktop/terminal.
- Zed: https://zed.dev/docs/ai/agent-profiles, https://zed.dev/docs/ai/tool-permissions, https://zed.dev/docs/ai/agent-panel, https://zed.dev/releases/stable.
- Aider: https://aider.chat/docs/git.html, https://aider.chat/docs/config/options.html, https://aider.chat/docs/usage.html, https://aider.chat/docs/faq.html.
- Non-AI precedent: https://developer.hashicorp.com/terraform/cli/commands/apply, https://developer.hashicorp.com/terraform/cli/commands/plan, https://developer.hashicorp.com/terraform/tutorials/automation/automate-terraform, https://discuss.hashicorp.com/t/question-on-error-saved-plan-is-stale/52912, https://www.sudo.ws/docs/man/sudoers.man/, https://www.freedesktop.org/software/polkit/docs/latest/polkit.8.html, GitHub's protected-branch and ruleset pages under https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/.
- Approval fatigue and incidents: https://www2.eecs.berkeley.edu/Pubs/TechRpts/2012/EECS-2012-26.html, https://scholarsarchive.byu.edu/facpub/1955, https://www.usenix.org/conference/soups2014/proceedings/presentation/bravo-lillo, https://www.uber.com/newsroom/security-update/, https://www.infoq.com/news/2022/09/Uber-breach-mfa-fatigue, https://simonwillison.net/2025/Oct/22/living-dangerously-with-claude/, https://www.theregister.com/2025/07/21/replit_saastr_vibe_coding_incident, https://forum.cursor.com/t/cursor-ai-agent-used-rm-rf-to-delete-files-from-a-parallel-subdirectory/44742, https://forum.cursor.com/t/cursor-yolo-deleted-everything-in-my-computer/103131.
- vfs, in the worktree on branch `a-call-is-interrupted-and-the-host-asks` at f15a2fd9: `documentation/how-to/interrupt-a-call-and-ask-a-person.md`, `documentation/reference/access-levels.md`, `src/vfs/ops.py`, `src/vfs/permissions.py`, `src/vfs/base.py`, `context/standards/roadmap.md` section 5, `documentation/tutorials/control-who-can-access-files.md`, and the reference deployment table in `AGENTS.md`.

## Findings

### 1. The taxonomy: what each mode allows without asking

The table lists the end-user products first, then the frameworks. "Yes" means it runs without asking. "Ask" means a person is asked. "No" means it is refused. A cell with a condition gives the condition. The default mode of each tool is marked (default).

| Tool | Mode | Reads | Edits in workspace | Edits outside | Shell | Network | Destructive ops |
|---|---|---|---|---|---|---|---|
| Claude Code | `default`, "Manual" | Yes, inside working dirs | Ask | Ask | Ask, except a fixed read-only set (`ls`, `cat`, `grep`, read-only `git` and others) | Ask; WebFetch to built-in docs domains is yes | Ask |
| Claude Code | `acceptEdits` | Yes | Yes, plus `mkdir`, `touch`, `rm`, `rmdir`, `mv`, `cp`, `sed` in scope | Ask | Ask for other commands | Ask | `rm` in scope yes; protected paths and critical-path removals ask |
| Claude Code | `plan` | Yes | No | No | Read-only commands | Not stated | No |
| Claude Code | `auto` (default for terminal and VS Code since v2.1.283) | Yes | Yes, no classifier call | Classifier | Classifier | Classifier; read-only HTTP allowed | Classifier blocks irreversible destruction of files that existed before the session, `git reset --hard`, force push |
| Claude Code | `dontAsk` | Yes | Only if pre-approved, else no | Same | Same | Same | Same |
| Claude Code | `bypassPermissions` | Yes | Yes | Yes | Yes | Yes | Yes, except explicit ask rules, deny rules and critical-path `rm` |
| Codex | Read Only preset | Yes | Ask | Ask | In a read-only sandbox | Ask | Not in sandbox |
| Codex | Auto, labelled "Default" (default for a version-controlled folder) | Yes | Yes | Ask | Yes, in a workspace-write sandbox | Ask | Yes inside the workspace; `.git`, `.codex`, `.agents`, `.aws` stay read-only |
| Codex | Full Access | Yes | Yes | Yes | Yes, no sandbox | Yes | Yes |
| Gemini CLI | `default` (default) | Yes, read-only tools allowed | Ask | Ask | Ask | Ask | Ask |
| Gemini CLI | `auto_edit` | Yes | Yes | Not stated | Ask | Ask | Not stated |
| Gemini CLI | `plan` | Yes | No | No | No | Not stated | No |
| Gemini CLI | `yolo` (command line only) | Yes | Yes | Yes | Yes | Yes | Yes |
| opencode | `build` agent (default) | Yes; `.env` reads ask | Yes | Yes, `external_directory` is allowed by default | Yes | Yes | Yes |
| opencode | `plan` agent | Yes | No, except its plan folder | No | Yes | Yes | No |
| Cursor | Auto-review (default) | Yes, system-wide by default | Yes, saved to disk at once; config files ask | Ask (External-File Protection) | Allowlisted run; others run sandboxed; what cannot be sandboxed goes to a classifier | Restricted by default | File-Deletion Protection blocks automatic deletion |
| Cursor | Allowlist | Yes | Yes | Ask | Allowlist only | Allowlist only | Ask |
| Cursor | Run Everything | Yes | Yes | Yes | Yes | Yes | Yes |
| Cline | Auto-approve toggles | Toggle: project, or all files | Toggle: project | Toggle: all files | Toggle: "safe" commands, which the model flags, or all | Toggle: browser | Model-flagged commands ask |
| Cline | YOLO | Yes | Yes | Yes | Yes | Yes | Yes |
| Cline | Plan | Yes | No | No | No | Not stated | No |
| Copilot in VS Code | Manual (default) | Yes | Edits land, then Keep or Undo; sensitive files confirm | Confirm | Ask, except read-only and rule-allowed; `rm`, `curl`, `chmod` and others default to ask | URL fetch asks per host | Ask |
| Copilot in VS Code | Assisted | Yes | Model reviewer | Model reviewer | Model reviewer | Model reviewer | Model reviewer |
| Copilot in VS Code | Allow all | Yes | Yes | Yes | Yes | Yes | Yes |
| Windsurf (JetBrains Cascade) | Off / Auto / Turbo | Not stated | Not stated | Not stated | Off: allowlist only; Auto: model decides; Turbo: all except denylist | Not stated | Turbo: denylist asks |
| Zed | Profile Write, `tool_permissions` default `confirm` (default) | Confirm unless allowed | Confirm, then hunk accept or reject | Confirm | Confirm, per chained part | Confirm | Built-in rules forbid recursive forced deletion of `/`, `~`, `.` |
| Aider | Only one mode | Files the user adds | Yes, then auto-commit to git | Not applicable | Asks before adding command output to the chat | Not applicable | `/undo` reverts the last commit |
| LangChain HITL middleware | `interrupt_on` per tool | Only tools listed are interrupted; default none | Same | Same | Same | Same | Same |
| deepagents library | `FilesystemPermission` | Allow by default; rules give allow, deny or interrupt per path | Same | Same | Not applicable | Not applicable | Same |
| deepagents-code CLI | `manual` (default) / `auto` / `yolo` | Manual asks per configured tool; auto uses a classifier; yolo runs all | Same | Same | Same | Same | Same |
| OpenAI Agents SDK | `needs_approval` per tool | Default `False`: nothing asks | Same | Same | Same | Same | Same |
| Google ADK | `require_confirmation` per tool | Default `False` | Same | Same | Same | Same | Same |
| eve | `approval` per tool or agent-wide: `never()` (default), `once()`, `always()`, `auto()` | Never asks by default | Same | Same | Same | Same | Same |

Sources for the table. Claude Code: https://code.claude.com/docs/en/permissions, https://code.claude.com/docs/en/permission-modes, https://code.claude.com/docs/en/settings [READ]. The mode names also appear in the SDK at claude-agent-sdk-python/src/claude_agent_sdk/types.py:25-27, whose docstring says `dontAsk` denies anything not pre-approved and `auto` is a model classifier (types.py:2484-2492) [READ]. Codex: codex/codex-rs/utils/approval-presets/src/lib.rs:28-60 for the three presets and their descriptions, and https://developers.openai.com/codex/agent-approvals-security.md for the defaults and the read-only paths [READ]. Gemini CLI: cli/cli-reference.md, reference/configuration.md, cli/plan-mode.md [READ]. opencode: opencode/services/site/src/docs/content/permissions.mdx:213-241 [READ]. Cursor: https://cursor.com/docs/agent/security/run-modes and https://cursor.com/docs/agent/security [READ]. Cline: https://docs.cline.bot/features/auto-approve, yolo-mode, plan-and-act [READ]. Copilot: https://code.visualstudio.com/docs/agents/run/approvals, https://code.visualstudio.com/docs/agents/reference/ai-settings, review-code-edits [READ]. Windsurf: https://docs.devin.ai/windsurf/plugins/cascade/cascade-overview [READ]. Zed: https://zed.dev/docs/ai/agent-profiles, tool-permissions [READ]. Aider: https://aider.chat/docs/git.html and options.html [READ]. LangChain: langchain/libs/langchain_v1/langchain/agents/middleware/human_in_the_loop.py:586-591 [READ]. deepagents: deepagents/libs/deepagents/deepagents/middleware/filesystem.py:376-391 and 417-427; deepagents/libs/code/deepagents_code/approval_mode.py:48-53 [READ]. OpenAI Agents: openai-agents-python/src/agents/tool.py:500-511 [READ]. ADK: adk-python/src/google/adk/tools/function_tool.py:188-199 [READ]. eve: eve/docs/tools/human-in-the-loop.md:33-38 and 44 [READ].

Three patterns stand out.

**Products and libraries default differently.** Every end-user product asks before at least shell commands by default. Every library defaults to asking about nothing: LangChain, OpenAI Agents, ADK, eve and the deepagents library all run every tool unless the developer marks it. vfs is a library, so a default of no policy matches its peers. [INFERRED from the table]

**Workspace edits have moved to "land, then review".** Codex's default preset, Cursor's default, Copilot's Manual mode, Aider and Claude Code's new `auto` default all let in-workspace edits through without asking. What they still ask about is shell, network, paths outside the workspace and destructive commands. [INFERRED from the table]

**The ladder of modes is nearly universal.** Almost every product has the same four rungs: a read-only planning mode, an ask mode, an accept-edits mode, and an everything mode. Claude Code is `plan`, `default`, `acceptEdits`, `bypassPermissions`. Gemini is `plan`, `default`, `auto_edit`, `yolo`. Codex is Read Only, Auto, Full Access. Cline is Plan, toggles, YOLO. A fifth rung, a model classifier, has appeared in the last year in Claude Code (`auto`), Codex (`auto_review`), Cursor (Auto-review), Copilot (Assisted), Windsurf (Auto), deepagents-code (`auto`) and eve (`auto()`). [INFERRED from the table]

### 2. The axes underneath

The modes vary along seven axes. The table says which ones products show to their users and which ones they hide.

| Axis | Exposed to users | Where it shows |
|---|---|---|
| Class of action (read, edit, shell, network, MCP) | Yes, everywhere | Claude Code tool names; opencode `action`; Cline toggles; Zed per tool |
| Location (workspace or outside) | Yes | Claude Code `additionalDirectories`; Codex writable roots; opencode `external_directory`; Cline "project" and "all files"; Cursor External-File Protection |
| Command or path pattern | Yes | Claude Code `Bash(npm run *)`; Codex `prefix_rule`; opencode glob resources; Copilot regex keys |
| Trust of the workspace | Yes, as one switch | Claude Code's trust dialog gates project allow rules; Gemini trusted folders; Codex `trust_level` |
| Reversibility | Hidden, or only inside a classifier | Claude Code `auto` blocks "irreversibly destroying files that existed before the session"; deepagents-code classifier category `destructive_action`; MCP `destructiveHint`; Cursor File-Deletion Protection is a proxy for it |
| Who is calling | Hidden in single-user products; exposed in eve | eve's `response` policy decides who may answer; approval runs as the requester, never the approver |
| Blast radius (one file or 10,000) | Hidden | No product found has a count threshold; Claude Code's critical-path `rm` and Zed's forbidden recursive deletes of `/` and `~` are fixed proxies |

Sources: https://code.claude.com/docs/en/permission-modes and https://code.claude.com/docs/en/permissions; codex/codex-rs/execpolicy/README.md:5-8; opencode permissions.mdx:105-127 and 142-156; https://docs.cline.bot/features/auto-approve; https://cursor.com/docs/agent/security/run-modes; https://code.claude.com/docs/en/settings; Gemini cli/trusted-folders.md; deepagents/libs/code/deepagents_code/auto_mode.py:287-298; modelcontextprotocol/schema/draft/schema.ts:1927-1957; eve/docs/tools/human-in-the-loop.md:47 and the `response` policy section; https://zed.dev/docs/ai/tool-permissions. [READ]

Reversibility and blast radius are hidden for a reason. A coding agent's shell can do anything the user account can do, so the tool cannot know whether an action can be undone or how far it reaches. Claude Code says a Bash command a user approves "can still write anywhere your user account can" (https://code.claude.com/docs/en/security). Copilot says restoring a checkpoint does not reverse "completed terminal commands, network requests, deployments" (https://code.visualstudio.com/docs/agents/run/review-code-edits). [READ]

vfs can expose both axes honestly. Every vfs call names its verb and its paths, and every verb is classified in one table (`src/vfs/ops.py:66-105`). Every verb also has a rung on the access ladder (`ops.py:145-171`), and the ladder already orders verbs by how much they can destroy: `add` only creates or appends, `contribute` overwrites, and `read_write` trashes, moves and changes rights (`ops.py:119-124`). A shell line in vfs is not an opaque process: `cli` parses the line into these same verbs and re-enters through their public methods, so every gate fires on the real verb (`ops.py:15-17`). [READ] So a vfs policy can judge reversibility and blast radius exactly where a coding tool can only guess. [INFERRED]

### 3. How rules are written, and what goes wrong

Every rule system found has the same three effects: allow, ask and deny. They differ in how a conflict is settled.

| System | Precedence | Source |
|---|---|---|
| Claude Code | Deny, then ask, then allow; first match wins and "rule specificity doesn't change the order"; a deny at any settings level cannot be allowed by another | https://code.claude.com/docs/en/permissions |
| Claude Code hooks | Among several hooks, deny beats defer beats ask beats allow; deny and ask rules are still evaluated after a hook says allow | https://code.claude.com/docs/en/hooks, https://code.claude.com/docs/en/permissions |
| Codex execpolicy | The strictest decision across all matching rules: `forbidden` over `prompt` over `allow` | codex/codex-rs/execpolicy/README.md:95 |
| opencode | Last matching rule wins, in load order; for one action over several resources, any deny denies, else any ask asks | opencode permissions.mdx:25, 88-103 |
| Gemini CLI | Highest priority wins, with priorities computed from tiers plus a fraction | Gemini reference/policy-engine.md |
| Zed | Built-in rules, then always_deny, always_confirm, always_allow, then tool default, then global default | https://zed.dev/docs/ai/tool-permissions |
| eve | The agent-wide policy and the tool's policy combine to the stricter: denied, then user approval, then approved; a policy "can add a gate but never remove one" | eve/docs/tools/human-in-the-loop.md:168 |
| deepagents | First matching rule wins; no match allows | deepagents/libs/deepagents/deepagents/middleware/filesystem.py:417-427 |
| sandbox-runtime | For reads, `allowRead` beats `denyRead`; for writes, `denyWrite` beats `allowWrite` | sandbox-runtime/README.md:119 |
| GitHub rulesets | "A ruleset does not have a priority"; where rulesets overlap, the most restrictive rule applies | GitHub's about-rulesets page |

[READ, each from its source column]

Settings live in layers. Claude Code reads managed settings, then the command line, then the local project file, then the shared project file, then the user file; list keys merge, and a deny anywhere wins (https://code.claude.com/docs/en/settings). opencode appends global rules after defaults and agent rules after global ones, and a managed policy can only turn allow or ask into deny (permissions.mdx:88-90, 297-309). Cursor's team dashboard wins over per-user and per-repo files (https://cursor.com/docs/reference/permissions). [READ]

What users and vendors report as confusing or dangerous:

- **Pattern rules over shell text are not a boundary.** Claude Code: "Bash permission patterns that try to constrain command arguments are fragile", and a deny on `Bash(rm *)` does not stop `/bin/rm` (https://code.claude.com/docs/en/permissions). Cursor deprecated its denylist after four published bypasses (base64, subshells, a script file, quote tricks), and now says its allowlist is "best-effort, not a security boundary" (https://www.backslash.security/blog/cursor-ai-security-flaw-autorun-denylist, https://cursor.com/docs/enterprise/llm-safety-and-controls). Copilot: "Command matching is best effort" (https://code.visualstudio.com/docs/agents/run/approvals). [READ]
- **Order and priority schemes confuse their own authors.** Gemini's policy-engine page gives a tier table of 1 to 5, while its own worked examples compute with an older numbering, and it says the Workspace tier is "currently non-functional" (Gemini reference/policy-engine.md). sandbox-runtime's read and write lists have opposite precedence (README.md:119). [READ]
- **One setting silently disables another.** The Claude Agent SDK added a runtime warning because `allowed_tools` or `bypassPermissions` silently stops a `can_use_tool` callback from ever firing (claude-agent-sdk-python/CHANGELOG.md:512; types.py:2321-2331). The same SDK once shipped a `dontAsk` docstring that said the opposite of what the mode does (CHANGELOG.md:893). [READ]
- **A predicate that changes its mind on resume skips the answer.** LangChain's `when` predicate runs again when the run resumes; if it returns `False` then, "the reviewer's answer is skipped and the tool runs, even if they rejected it" (langchain/libs/langchain_v1/langchain/agents/middleware/human_in_the_loop.py:378-385). [READ] The vfs how-to avoids this: an answered call skips the policy, because the answer is on record (interrupt-a-call-and-ask-a-person.md:166). [READ]
- **Unanchored path patterns over-fire.** deepagents warns that a pattern like `/**/secrets` "collapses to `/` and conservatively over-fires for any bulk call" (deepagents/libs/deepagents/deepagents/middleware/filesystem.py:396-399). Claude Code path rules need four different anchors (`//`, `~/`, `/`, `./`) to say what they mean (https://code.claude.com/docs/en/permissions). [READ]
- **Hints from a server are not facts.** MCP says tool annotations "are not guaranteed to provide a faithful description of tool behavior" and clients "should never make tool use decisions based on `ToolAnnotations` received from untrusted servers" (modelcontextprotocol/schema/draft/schema.ts:1907-1912). [READ]

The lesson for vfs: an order-free rule ("the strictest wins") is the one no source reported as confusing. Every confusion found came from order, priority, or text patterns over shell commands. vfs has no shell text to match, because `cli` hands the policy real verbs. [INFERRED]

### 4. Review after instead of ask before

Many tools let changes land and rely on undo. Their undo has a consistent hole.

| Tool | What lands first | Undo | What undo does not cover |
|---|---|---|---|
| Aider | Every edit, committed to git | `/undo` drops the last commit | Anything outside git |
| Claude Code | Edits in `acceptEdits` and `auto` | Checkpoints with `/rewind`, kept for the 100 most recent | "A file that only Bash commands changed isn't tracked"; subagent edits; external edits |
| Cursor | Edits, "saved to disk immediately" | Diff reject; checkpoints of modified files | Not stated for terminal changes |
| Copilot | Edits, "already saved to disk" | Keep or Undo per change, file or all; checkpoints | "completed terminal commands, network requests, deployments" |
| Cline | Edits under auto-approve | Shadow git checkpoint after each tool use | Not stated |
| Gemini CLI | Approved edits | Shadow git checkpoint and `/restore`, off by default | Not stated |
| Zed | Edits | Hunk accept or reject; checkpoints were removed in 1.27.0 | "use Git" |
| Windsurf | Edits | Revert a step | "Reverts are currently irreversible" |

Sources: https://aider.chat/docs/git.html; https://code.claude.com/docs/en/checkpointing; https://cursor.com/docs/agent/security, https://cursor.com/docs/agent/chat/checkpoints; https://code.visualstudio.com/docs/agents/run/review-code-edits; https://docs.cline.bot/features/checkpoints; Gemini cli/checkpointing.md; https://zed.dev/docs/ai/agent-panel, https://zed.dev/releases/stable; https://docs.devin.ai/windsurf/plugins/cascade/cascade-overview. [READ]

The record of the pattern. Undo works for the agent's own edit-tool changes and fails for everything the shell did. The incidents found are all shell or database deletions that no checkpoint covered. A Cursor agent ran `rm -rf` on a sibling directory with no prompt and no backup (forum thread 44742). A user in YOLO mode reported the agent deleted "everything on my computer" (forum thread 103131). Replit's agent deleted a production database during a code freeze and then said rollback could not restore it, which proved false (The Register, 2025-07-21). [READ]

What vfs makes possible that these tools cannot do:

- **The shell's changes are undoable too.** In vfs a shell line is parsed into vfs verbs (`ops.py:15-17`). So `rm` in a `cli` line is a vfs `delete`, which moves the file to the trash (access-levels.md:39), and a redirect that overwrites a file is a `write`, which keeps the old body as a version (access-levels.md:41). The hole every coding tool has, "Bash changes are not tracked", does not exist for files inside vfs. [READ; INFERRED for the conclusion]
- **Undo is per file, not per session.** A checkpoint rolls back everything since a point. vfs versions are per file, so one bad edit can be reverted while later good edits stay. [INFERRED from access-levels.md:41]
- **Who did what is attributable.** The planned action log (roadmap H0) records actor, verb and paths for every call (roadmap.md:278). With it, "show every change Scout made since 09:00" is one query. [READ]
- **An approval binds to the version the person saw.** Terraform treats passing a saved plan as the approval, and refuses a saved plan whose state serial moved ("Saved plan is stale"; https://developer.hashicorp.com/terraform/cli/commands/apply, https://discuss.hashicorp.com/t/question-on-error-saved-plan-is-stale/52912). The vfs how-to already does the same: a file that changed between preview and re-run is a conflict (interrupt-a-call-and-ask-a-person.md:172; roadmap.md:249). GitHub's "dismiss stale pull request approvals when new commits are pushed" is the same idea. [READ]

Three gaps limit review-after in vfs today. First, versions are kept, but the router has no public verb that reads or reverts an earlier version: `read` takes no version argument (`src/vfs/base.py:824-831`), and the router's verbs are listed at `base.py:824-1768` with no such verb among them. Second, the action log that would list what changed is planned, not built (roadmap.md:259). Third, the trash is not forever: `sweep` destroys for good (access-levels.md:39), though it is a developer-plane verb no agent is offered (`ops.py:99-103`). [READ] Calls that leave vfs, the `run` verb, host tools and mounted MCP servers, cannot be undone by vfs at all. [INFERRED from roadmap.md:249, "vfs cannot preview code that runs elsewhere"]

### 5. What an approver can do

| Choice | Where it exists | What it needs from the system |
|---|---|---|
| Approve once | Every tool studied | An id for the pending action |
| Reject with a reason the agent reads | Codex `Denied { rejection }` (protocol.rs:4665); LangChain `reject` with `message` and `respond` (human_in_the_loop.py:87); Claude SDK `PermissionResultDeny.message` (types.py:308-313); Claude Code "No" with a comment; opencode reject with feedback | A text channel back to the caller |
| Reject and stop the whole turn | Codex `Abort` (protocol.rs:4672); Claude SDK `interrupt=True` (types.py:313); Claude Code "No" without a comment; opencode reject, which rejects every pending request in the session (permissions.mdx:280) | A notion of a run or turn to cancel |
| Edit the proposed change, then approve | LangChain `edit` (human_in_the_loop.py:124-134); Claude SDK `updated_input` (types.py:300); Claude Code hook `updatedInput` | The approved action is no longer the action the caller made |
| Approve for the rest of the session | Codex `ApprovedForSession` (protocol.rs:4651); Copilot "In this Session"; eve `once()` (human-in-the-loop.md:191); Claude Code file edits ("until the session ends") | A session object and a rule for what "the same" means |
| Approve and remember for good | Codex `ApprovedExecpolicyAmendment` (protocol.rs:4644); opencode "Allow always", saved as a project rule (permissions.mdx:279-292); Claude Code "don't ask again", saved to `.claude/settings.local.json`; Copilot "Always Allow"; Zed "Always for <pattern>"; OpenAI Agents `always_approve` (run_state.py:1381-1384) | A durable rule store and a way to propose a pattern from one action |
| Let a reviewer model answer | Codex `approvals_reviewer = "auto_review"` (config_types.rs:183); Claude Code `auto`; Cursor Auto-review; Copilot Assisted; eve `auto()` | A model, and a fallback to a person |

[READ, each from its cited source; codex paths are under codex/codex-rs/protocol/src/, the SDK paths under claude-agent-sdk-python/src/claude_agent_sdk/, and the opencode and eve paths are their docs files named above]

Three observations shape the vfs answer.

- **"Remember" is everywhere, and every product proposes the pattern itself.** opencode: "Tools choose the proposed saved pattern: some propose `*`, shell proposes command prefixes" (permissions.mdx:290-291). Claude Code saves up to five per-subcommand rules for a compound command (https://code.claude.com/docs/en/permissions). The pattern is a product decision about what "the same action" means. [READ]
- **A remembered approval is consent, not a right.** eve says so in those words: "A remembered approval is consent, not authorization. Authorize the current caller on every call" (human-in-the-loop.md:199), and "The approved call ... run[s] with the requesting user's identity ... never the approver's" (human-in-the-loop.md:47). opencode: saved approvals "never override a configured `deny`" (permissions.mdx:289-290). The vfs how-to rules the same: an approval "does not lend Scout any of Ada's access" (interrupt-a-call-and-ask-a-person.md:174). [READ]
- **Editing before approval conflicts with the exact-call rule.** The vfs answer covers "this exact call", and a changed argument is a different call (interrupt-a-call-and-ask-a-person.md:171). An approver edit would admit a call nobody made. A reject with a reason ("use 60 days, not 120") reaches the agent, which then makes the call the person wants, and that call is checked like any other. [READ; INFERRED for the conclusion]

### 6. Approval fatigue and safety

The evidence that people stop reading prompts is strong and recent.

- Claude Code users "accept 93% of them anyway" (https://www.anthropic.com/engineering/claude-code-auto-mode, 2026-03-25). A later post says "users approve 97% of permission prompts in Claude Code" (https://claude.com/blog/auto-mode-default-in-claude-code, 2026-08-07). Both were fetched twice to confirm the wording. [READ]
- In a controlled test with 1,053 paid professional testers, "human review caught just 13.6% of dangerous commands, while auto mode caught 89%" (same post). [READ]
- The auto-mode classifier's own errors: a 0.4% false positive rate on 10,000 real actions, and a 17% false negative rate on 52 real overeager actions, which the post calls "the honest number" (https://www.anthropic.com/engineering/claude-code-auto-mode). [READ]
- Anthropic's sandboxing "safely reduces permission prompts by 84%", and names "approval fatigue, where users might not pay close attention to what they're approving" (https://www.anthropic.com/engineering/claude-code-sandboxing). [READ]
- Older work says the same of warnings in general. Only 17% of Android users paid attention to permissions at install, and 3% answered all comprehension questions correctly (Felt et al., https://www2.eecs.berkeley.edu/Pubs/TechRpts/2012/EECS-2012-26.html). Habituation was seen directly in fMRI, and varied warnings resisted it (Anderson, Vance et al., https://scholarsarchive.byu.edu/facpub/1955). Push-approval fatigue was the way into Uber in 2022: the contractor "eventually ... accepted one" (https://www.uber.com/newsroom/security-update/). [READ]

How tools reduce prompt volume:

| Technique | Examples |
|---|---|
| Never ask about reads | Every product in the taxonomy |
| Let in-workspace edits land, rely on undo | Codex Auto, Cursor, Copilot, Aider, Claude Code `auto` |
| Contain instead of ask (a sandbox) | Codex sandbox modes; Cursor sandboxed commands; Claude Code sandboxing, 84% fewer prompts |
| Remember answers | Every product's "always" or "session" choice |
| A model answers the low-risk ones | Claude Code `auto`, Codex `auto_review`, Cursor Auto-review, Copilot Assisted, eve `auto()`, deepagents-code `auto` |
| Credential caching for a short time | sudo `timestamp_timeout`, default 5 minutes (https://www.sudo.ws/docs/man/sudoers.man/); polkit `auth_admin_keep` (https://www.freedesktop.org/software/polkit/docs/latest/polkit.8.html) |

[READ, each from sources already cited]

Every classifier found fails closed to a person or to a refusal. Claude Code's auto mode goes back to prompting after 3 blocks in a row or 20 in total (https://code.claude.com/docs/en/permission-modes). Codex stops the turn after 3 consecutive denials or 10 in the last 50 (https://developers.openai.com/codex/concepts/sandboxing/auto-review.md). deepagents-code says "an unusable one fails closed" (deepagents/libs/code/deepagents_code/auto_mode.py:248-255). eve asks a person "when the model errors, times out, or the input is over 64 KB" (human-in-the-loop.md:180). [READ]

What review-everything would cost at the reference deployment. The deployment has about 150,000 agent verb calls a day, with about three reads, lists, globs and greps per write or edit (AGENTS.md, the reference deployment table). [READ] So about one call in four changes something: about 37,000 mutating calls a day, or about 37 a day for each of the 1,000 users. A mode that interrupts every change would ask each person about 37 times a day. At the measured 93 to 97% approval rate, most of those answers would be reflexes. [INFERRED]

### 7. The recommendation for vfs

The recommendation is a small set of named policies, built as ordinary policy functions, plus two helpers that make them compose. Every built-in is a pure function of the call: it reads the verb, the paths and the arguments, and touches no storage.

**The named policies.**

| Name | Allows | Interrupts | Denies |
|---|---|---|---|
| `review` | `read`, `ls`, `tree`, `glob`, `grep`, `search`, `stat`, `grants`, `traverse` | `write`, `edit`, `mkdir`, `copy`, `move`, `delete`, `restore`, `mkedge`, `rmedge`, `grant`, `revoke`, `set_posture`, `run` | Nothing |
| `review_irreversible` | Every read, and every change vfs can undo: `write` and `edit` (the old body is kept as a version), `mkdir`, `copy` to a new path, `delete` (to the trash), `restore`, `move` without `replace`, `mkedge`, `rmedge` | `grant`, `revoke`, `set_posture` (what was read under a grant cannot be unread); `run` (its effects leave vfs); `move` or `copy` with `replace=True`; any change on a mount whose storage keeps no versions or no trash; any call naming more than `max_paths` paths | Nothing |

How each name reads to a host, in one line each. `review` means "a person sees every change before it lands". `review_irreversible` means "changes land, because vfs can undo them, and a person sees only what vfs cannot undo". [INFERRED]

Notes that apply to both:

- **`cli` is not judged as a line.** It is not an op; it re-enters each verb's public method (`ops.py:15-17`), so the policy judges each verb the line makes. This is how a shell line stops at the one command that needs a person, as the how-to's Step 7 shows. [READ; the design consequence is INFERRED]
- **The system authority is never judged**, as already ruled (interrupt-a-call-and-ask-a-person.md:63). So an ETL load of 10,000 files run as the system is never interrupted, and a 10,000-file write by a named caller is one interrupt with one preview, because the policy sees one call. [READ; INFERRED for the batch case]
- **`sweep`, `add_member` and `remove_member` are not listed.** They are developer-plane verbs that no agent is offered (`ops.py:99-103`). Under a built-in they are allowed, since only host code reaches them. [READ; INFERRED for the choice]
- **The access gate still runs first.** A built-in can only narrow (interrupt-a-call-and-ask-a-person.md:39), so neither name ever lets a caller do what its grants forbid. [READ]

**How a host picks one.** The string is shorthand for the factory with no arguments. A factory takes a path scope and, for `review_irreversible`, the blast-radius threshold. An unknown string is refused when the file system is made, never treated as "no policy".

```python
from vfs import VirtualFileSystem, policies

fs = VirtualFileSystem(policy="review")
fs = VirtualFileSystem(policy=policies.review(paths=["/contracts", "/finance"]))
fs = VirtualFileSystem(policy=policies.review_irreversible(max_paths=100))
fs = VirtualFileSystem(policy=policies.strictest(
    policies.review_irreversible(),
    policies.review(paths=["/contracts"]),
    my_policy,
))
```

**Path scope is a prefix, not a glob.** `paths=["/contracts"]` covers `/contracts` and everything below it, which is how a grant already reads ("A level covers a path and everything below it", access-levels.md:70). A call outside every listed prefix is allowed by that policy. A call naming several paths, such as a `move` or a batch `write`, is in scope when any of its paths is, as opencode does for a patch over several files (permissions.mdx:101-103). Prefixes avoid the unanchored-glob over-firing deepagents warns about and the four-anchor syntax of Claude Code's path rules. [READ for the precedents; INFERRED for the choice]

**Composition is strictest-wins and order-free.** `policies.strictest(a, b, ...)` asks each policy and returns deny if any denies, else interrupt if any interrupts, else allow. The interrupt reasons of every policy that interrupted are joined. This is the rule Codex execpolicy, eve, GitHub rulesets, Zed and Claude Code all use in some form, and it is the one rule no source reported as confusing. Last-match and priority schemes (opencode, Gemini) are not offered. [READ for the precedents; INFERRED for the choice]

**Where the mode belongs.**

- **The file system holds the floor.** `VirtualFileSystem(policy=...)` applies to every session, as the how-to already shows.
- **A session may add, never loosen.** `fs.open_session(authority, policy=...)` gives that session `strictest(fs_policy, session_policy)`. This matches eve, where a subagent's policy "adds to it and can't loosen it", and the roadmap's H3, which already names `Session(policy=hook)` (roadmap.md:311). A host that wants a planning agent and a working agent opens two sessions with different policies. [READ for the precedents; INFERRED for the choice]
- **Not the mount.** A path scope already says "only under `/contracts`", and a mount already carries a `PermissionMap` for the structural read-only case, where "the most restrictive layer wins" (`src/vfs/permissions.py:1-10`). A third place to set a policy would add a precedence question for no new power. [READ; INFERRED for the choice]
- **Never the call.** The caller, often an agent, writes the call's arguments. A mode chosen per call would let the caller choose its own review. [INFERRED]

**Modes that are deliberately not built in.**

- **No "bypass" or "yolo" name.** No policy at all is that mode, and it stays the default, as in every library studied. [INFERRED from finding 1]
- **No "read_only" or "plan" policy.** A policy's distinct job is to interrupt. Refusing every change is a rights question, and vfs already answers it: a mount with `permissions="read"` (`permissions.py:221-235`), a posture, or a grant of `read`. A built-in that only denies would be a second way to say the same thing. If a session-scoped read-only is wanted, it belongs in authority narrowing, which the roadmap already lists (roadmap.md:324), not in the policy. [READ; INFERRED for the choice]
- **No classifier.** vfs ships no model. A host that wants Claude Code's `auto` writes a policy that calls its own model and returns allow or interrupt, and the docs show it falling back to interrupt on any error, as every classifier studied does. [INFERRED from finding 6]

**"Remember this answer" belongs to the host for now.** vfs answers one exact call once, as ruled. "For the rest of the session" and "always" stay in the host, for three reasons. Each product picks its own meaning of "the same action" (finding 5), and that is a UI decision. A remembered approval is consent, not a right, so it must never become a second grant table inside vfs (eve, human-in-the-loop.md:199). And the host already holds the policy function, so a closure over its own set of remembered answers is a few lines. If vfs takes this on later, the one piece only vfs can do well is durability and attribution: `fs.answer(id, allow=True, remember=...)` writing an attributed rule beside the interrupts in the root binding's storage. That is a later option, not a 0.1 need. [INFERRED]

**Edit-before-approve is not offered.** The reason carried by a rejection is the channel for "do it differently" (interrupt-a-call-and-ask-a-person.md:210-220). [READ; INFERRED for the choice]

**What must ship first, and what can wait.**

| Rank | Piece | Why it ranks here |
|---|---|---|
| 1 | `policies.review(paths=...)` and `policy="review"` | The mode every product has; needs nothing vfs does not already plan for interrupts; scoped by path it is the `/contracts` case in the how-to, with no function to write |
| 1 | `policies.strictest(...)` and session policies that only add | Without them a host cannot combine a built-in with its own rule, and the precedence question gets answered ad hoc |
| 2 | `policies.review_irreversible(max_paths=...)` | The mode that answers approval fatigue, but it promises undo; it ships once vfs has a public verb that lists and reverts a file's versions, and once the action log (H0) can list what a session changed |
| 3 | `fs.answer(..., remember=...)` | Only if hosts show they need durable, attributed remembered approvals |
| Not planned | `read_only`, `bypass`, a built-in classifier, edit-before-approve | Covered by rights, by no policy, by the host's own function, and by the rejection reason |

**The strongest argument against this recommendation.** vfs cannot know which files matter, and a named mode invites a host to pick `review` for the whole tree. At the reference deployment that is about 37 interrupts a person a day, and the measured result of asking that often is approval of 93 to 97% of prompts and a catch rate of 13.6% for dangerous ones. A named `review` could make a deployment less safe than grants plus undo, while looking safer. `review_irreversible` has a different weakness: it rests on an undo the API cannot yet perform, and undo does not reach what happened downstream, such as another agent that read the bad edit and acted on it. The alternative is to ship no named modes at all, only small predicates (`mutates`, `under(path)`, `op_in(...)`) and the `strictest` helper, and let each host write its six lines. The recommendation keeps the names because the path-scoped `review` is the common case the how-to itself teaches, and because a name a host can read is easier to audit than a function. It answers the fatigue risk by documenting `review` with a path scope, never as a whole-tree default, and by ranking `review_irreversible` as the mode for broad use once undo is a public verb. [INFERRED]

## What was not checked

- The Claude Code permission-modes page was read only in part, cut off in its "Critical paths" section, and only the PreToolUse part of the hooks page was read.
- The Windsurf "Disabled, Allowlist Only, Auto, Turbo" levels could be seen only in a search-result snippet of a page that now redirects; the table uses the JetBrains Cascade page's three levels instead. No Windsurf default was stated on any page fetched.
- Cline's default toggle settings are not stated on its auto-approve page; the v3.35 post says only that auto-approve is always on.
- Cursor's per-hunk review controls and whether its checkpoints revert terminal changes are not described on the official pages fetched.
- Codex docs say `approval_policy = "untrusted"` is no longer supported, while the source at 140815f19c05 still declares the variant (codex/codex-rs/protocol/src/protocol.rs:1207-1211). Which one a current build honours was not run.
- Letta's current source (`letta-ai/letta-code`) and the dirty `gemini-cli` clone were not studied; Gemini was studied from its docs only.
- ADK was checked only for `require_confirmation` and `ToolConfirmation`; no ADK policy engine was found by the searches run.
- The Replit follow-up article, the Bravo-Lillo 2013 paper (its PDF came back unreadable) and the further Cursor forum reports named in search results were not read.
- In vfs: whether `InMemoryStorage` keeps versions and a trash, and whether a `move` or `copy` with `replace=True` keeps the replaced occupant as a version, were not checked. Both decide exactly which calls `review_irreversible` may let through, and its spec must settle them first.
- No code was run against vfs; every vfs statement is from reading the worktree at f15a2fd9.

## One line

Ship `review` with a path scope and a strictest-wins `strictest()` first, add `review_irreversible` once vfs can revert a version through its public API, and leave read-only, bypass, classifiers and remembered answers to rights, to no policy, and to the host.
