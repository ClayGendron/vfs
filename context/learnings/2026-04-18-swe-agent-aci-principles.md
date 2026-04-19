# SWE-agent and Agent-Computer Interface (ACI) Design

- **Date:** 2026-04-18
- **Primary source:** Yang, Jimenez, Wettig, Lieret, Yao, Narasimhan, Press. *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering* (arXiv:2405.15793v3, NeurIPS 2024). Princeton Language and Intelligence.
- **Why it matters to Grover:** Grover *is* an ACI. It's the interface between an LM agent and a file-shaped persistence layer. The SWE-agent paper is the clearest published argument for why that layer should be shaped around the agent rather than around a human user, and it enumerates design principles we should test our tool surface against.

## The core claim

LM agents are a new category of end user — not humans, not traditional API consumers. Human UIs (shell, IDE, search engines) are tuned for people who can visually scan, flexibly ignore noise, and click through many micro-steps cheaply. LMs can't: every token has a fixed cost, distracting context hurts performance, and verbose navigation patterns burn budget. So the interface itself — the commands available and how feedback is returned — is a performance lever that's *independent of the underlying model*.

SWE-agent demonstrated this on SWE-bench: same GPT-4 Turbo model went from **2.67% → 18.00%** resolved on SWE-bench Lite purely by swapping the shell for a tailored ACI. No weight changes. The ablation table (§5.1) is the money table — every ACI component they removed cost 2–8 percentage points.

## The four ACI design principles

These are the principles the authors extract. I'm restating them with Grover-relevant framing:

1. **Actions should be simple and easy to understand.** Bash commands with 40 flags confuse agents. A small command with 2–3 args and a concise docstring is easier to call correctly without demonstrations or fine-tuning. → *For Grover: resist the urge to add flags. Each MCP/CLI tool should do one thing with obvious arguments.*

2. **Actions should be compact and efficient.** Important high-order operations (navigate, edit) should land in one call, not be composed across many turns. A "minimal primitives" API that forces the agent to chain 5 actions to do one edit is worse than one `edit` command that takes `start_line, end_line, new_text`. → *For Grover: the "everything is a file" strategic direction (see `project_everything_is_a_file`) already leans this way. Resist splitting unified ops into micro-ops.*

3. **Environment feedback should be informative but concise.** After an edit, show the agent the updated region of the file automatically — don't make them issue another command to see what happened. But don't dump the whole file either. → *For Grover: write/edit responses should echo the affected region with line context, not the full object and not nothing. The `GroverResult` shape is the natural place for this.*

4. **Guardrails mitigate error propagation and hasten recovery.** Integrate checks (linter, syntax) inline with actions. Reject operations that produce invalid state and return a specific error + before/after snippet so the model can self-correct. Silent success of a bad edit is the worst outcome. → *For Grover: this maps directly to the `content-before-commit` rule we already enforce (see `feedback_fs_write_ordering`). The linter analogue is validation at the object boundary — reject and explain, don't half-write.*

## Concrete mechanisms worth stealing

- **File viewer with a fixed window + line numbers.** 100 lines was the sweet spot in their sweep; 30 lines (too little) and the full file (too much) both *hurt* performance by 3.7–5.3 pts. Prepending line numbers makes edit commands cheap to generate — no arithmetic.
- **Unified `edit <start>:<end>\n<text>` command.** Replaces `sed` / heredoc redirection patterns. Multi-line edits become one action. The file viewer auto-re-renders the affected region after the edit applies.
- **Linting guardrail on edit.** They run `flake8 --select=F821,F822,F831,E111,E112,E113,E999,E902` after every edit. If errors, edit is *reverted* and the agent gets `{error_codes, proposed_diff_snippet, original_snippet, retry_instruction}`. Lifts resolve rate from 15% → 18% on Lite (§5.1, Table 3). Recovery rate decays fast — 90.5% chance of eventual success with 0 prior failures, drops to 57.2% after one failed edit — which argues for getting the guardrail *right* rather than relying on multi-turn recovery.
- **Search result caps.** Search commands return at most 50 results; more triggers "refine your query" rather than flooding context. Relevant to the `feedback_mssql_fts_word_tokens` learning: predictable, bounded search output is more important than maximal recall.
- **Context collapsing.** Observations older than the last 5 turns are replaced with `Old output omitted (N lines)`. Structure of history preserved, content dropped. Keeps token budget for later turns without losing the trajectory shape.
- **"No output" handling.** Silent commands (`rm`, `touch`) return `Your command ran successfully and did not produce any output.` rather than empty string. Prevents the agent from issuing redundant "did it work?" probes.

## Empirical findings about agent behavior

Useful as reality-checks on how an agent will actually use Grover:

- **Trajectories are bimodal.** Agents either reproduce-then-localize (start with `create → edit → python`) or localize-then-edit (start with `search_dir → open`). From turn 5+, the loop is almost exclusively `edit → execute → edit → execute`. Design for this — it's the hot path.
- **Agents succeed quickly and fail slowly.** Median successful run: 12 turns / $1.21. Median unsuccessful: 21 turns / $2.52. 93% of resolved trajectories finished before budget exhaustion. Increasing budget doesn't help — if the first 15 turns don't converge, neither will the next 25.
- **Most failures are bad implementations, not bad tool use.** 52% of unresolved trajectories were categorized as "incorrect" or "overly specific" implementation; 23% were cascading failed edits; only ~10% were localization failures. Implication: once the interface is decent, model reasoning is the bottleneck — further ACI work has diminishing returns on the same benchmark.
- **Demonstrations help formatting, not strategy.** Removing the in-context demo drops performance 1.7 pts. The demo teaches the response shape, not domain expertise.

## Follow-up work (2024–2026)

The ACI framing stuck. What's happened since:

- **SWE-bench saturation.** Original SWE-bench full: 12.47% (SWE-agent + GPT-4 Turbo, 2024). SWE-bench Verified (500 hand-filtered instances, now the standard split) is near-saturated — Claude-family models report ~94% as of early 2026, Gemini 3 Pro + Live-SWE-agent ~77% on the public leaderboard. Harder splits (SWE-bench Pro, SWE-bench Live, SWE-bench M for multimodal) have taken over as the frontier — SOTA on Pro sits around 23%.
- **Mini-SWE-agent** ([github.com/SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)). ~100 lines of Python. No custom ACI — the model just gets `bash` and is prompted to use it. Scores >74% on SWE-bench Verified with a strong frontier model. **This is the interesting update:** frontier models in 2026 are capable enough that a bespoke ACI matters *less* than it did for GPT-4 Turbo. The ACI principles still hold, but the bar for "worth building" has risen. Don't over-engineer Grover's tool surface for Claude 4/Gemini 3–class models — they can cope with more primitive interfaces than GPT-4 Turbo could.
- **SWE-agent Multimodal / OpenHands-Versa.** Adds browser + multimodal file handling. Confirms the ACI framing extends beyond code — the principles are about LM ergonomics, not software engineering specifically.
- **Live-SWE-agent** (arXiv:2511.13646, Nov 2025). Agent that rewrites its own tools/prompts at runtime based on task feedback. An auto-ACI-design approach — addresses the paper's own "limitations" section item about automating the ACI development loop.
- **Agentless / Agentless-Lite.** RAG-based localization + single-shot patch generation, no iterative agent loop. Competitive on SWE-bench with much lower cost. Reminder that "agent loop" isn't the only shape of a software engineering system — for some task classes, retrieve-once-and-generate beats iterate.

## Applicability to Grover

Where SWE-agent validates what Grover is already doing:

- **Unified write/edit with validation before commit.** Matches `feedback_fs_write_ordering`. The paper's linting-revert-with-explanation pattern is exactly the behavior we want from Grover's write path when constraints fail.
- **Single unified tool (the "everything is a file" direction).** Matches principle 2 — consolidate high-order ops.
- **Search that returns bounded, predictable output.** `grep`/`glob` in Grover should cap and guide rather than flood. The MSSQL FTS word-tokenization behavior makes this doubly important: users need to understand *why* something didn't match, not just get zero results silently.

Where SWE-agent suggests things to add or verify:

- **Echo affected region after writes.** Does `GroverResult` currently include enough post-write context for the agent to confirm the change without issuing a follow-up read? If not, that's a cheap win.
- **Error messages should include before/after + what-went-wrong + retry guidance.** Principle 4 isn't just "reject bad writes" — it's reject *with enough context that the agent can fix it in one turn*. Worth auditing current error shapes.
- **Context collapsing is an LM-client concern, not a Grover concern.** Mentioned for completeness — Grover shouldn't try to manage the agent's history. But tools should return compact payloads so the client has less to collapse.

Where the follow-up work tempers the original paper:

- The mini-swe-agent result (bash-only, 74%+ on Verified) suggests we should be skeptical of elaborate custom tool surfaces. Grover earns its place if it provides something `bash + ripgrep + sed` genuinely can't — persistence semantics, structured objects, user-scoped views, hydrated content — not just "a nicer `edit` command."

## Sources

- [SWE-agent paper (arXiv:2405.15793)](https://arxiv.org/abs/2405.15793) — Yang et al., NeurIPS 2024
- [SWE-agent ACI documentation](https://swe-agent.com/0.7/background/aci/)
- [SWE-bench leaderboards](http://www.swebench.com/)
- [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) — simpler 2025 follow-up
- [Live-SWE-agent (arXiv:2511.13646)](https://arxiv.org/pdf/2511.13646) — self-evolving agent, Nov 2025
- [OpenHands-Versa / multimodal coding agents (arXiv:2506.03011)](https://arxiv.org/pdf/2506.03011)
