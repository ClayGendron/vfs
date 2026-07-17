# Spec-Driven Development: Research and Recommendations

- **Date:** 2026-04-18
- **Author:** Human + AI (research synthesis)
- **Status:** Informs the initial structure of `/context/`
- **Audience:** Future contributors (human or AI) re-grounding on why this tree looks the way it does

## TL;DR

1. Every serious spec-driven development (SDD) framework in 2026 converges on the same seven building blocks: **immutable principles, product context, story specs (split into WHAT/HOW/DO), conventions, decisions, learnings, and explicit unknowns**. `/context/` maps one folder to each. (Frameworks call these "feature specs"; we use "story" to cover work beyond software features — analyses, experiments, migrations.)
2. The load-bearing patterns are: **separation of WHAT from HOW**, **`[NEEDS CLARIFICATION]` markers instead of guessing**, **templates that constrain LLM output**, and **gates between stages**.
3. The dominant failure mode is **spec drift** — the markdown and the code diverge, and the gap widens each iteration. Design for refresh, not for freeze.
4. Karpathy's LLM Wiki pattern argues knowledge should **compound**, not be rediscovered per query. `/context/` is the "wiki"; the LLM is its librarian.

## Why context-driven development

Traditional docs serve code. As code moves forward, docs don't — because code is the artifact and docs are the commentary. The SDD inversion: **specifications are the artifact; code is the build output**. When code and spec disagree, you fix the code.

This is only viable now because AI agents can faithfully translate a sufficiently-precise natural-language spec into working code. The raw capability has been present for ~two years; the missing piece was structure. Every framework surveyed is a different answer to "what structure?"

## Framework landscape

| Framework | Key contribution | Canonical artifact |
|---|---|---|
| **GitHub Spec Kit** | `/specify` → `/plan` → `/tasks` CLI + templates; `constitution.md` of immutable articles read before every task | `specs/NNN-slug/{spec,plan,tasks,research}.md`, `memory/constitution.md` |
| **AWS Kiro** | Spec as source of truth; Agent Hooks fire on save/PR to cascade changes; Claude Sonnet powered | Per-spec packages with event-driven maintenance |
| **Agent OS (Builder Methods)** | Three-layer context: Standards (how) / Product (what+why) / Specs (next) | `agent-os/product/{mission,roadmap,tech-stack}.md` + standards profiles |
| **BMAD** | Role-based specialized agents (Analyst, PM, Architect, Dev, QA) with quality gates at handoffs | Every agent emits a versioned artifact, not a chat response |
| **Tessl** | "Vibe specs" → reviewed spec → agent implements; spec registry of 10k+ library specs to reduce API hallucinations | Specs live in-repo as "long-term memory" |
| **Red Hat's Four Pillars** | Vibes / Specs / Skills / Agents as a complete mental model | `specs/what-*.md` + `specs/how-*.md` + `.claude/skills/*/SKILL.md` |
| **AGENTS.md** | Single root file convention, nearest-file-wins; Linux Foundation-stewarded, 20k+ repos | `AGENTS.md` at project root |
| **Karpathy LLM Wiki** | LLM-maintained markdown knowledge base; compounds instead of re-retrieving | `index.md` catalog + `log.md` append-only + entity/concept pages |

### Notable takeaways from canonical sources

**Spec Kit's template discipline.** The templates themselves are prompts that constrain LLMs: they *forbid* tech-stack details in spec.md ("Focus on WHAT users need and WHY / Avoid HOW to implement"), *mandate* `[NEEDS CLARIFICATION: specific question]` instead of plausible guesses, *enforce* checklists ("No `[NEEDS CLARIFICATION]` markers remain", "Requirements are testable and unambiguous"), and *gate* implementation behind simplicity/anti-abstraction checks. This is the most important pattern in the entire research: **structure beats exhortation.** "Don't over-engineer" as a constitution line fails; a checkbox that forces you to justify any 4th project succeeds.

**Karpathy's compounding insight.** RAG retrieves and forgets. A wiki accumulates and compounds. The LLM is a "full-time research librarian" that lints, cross-references, and files answers back as new pages. The `/context/` tree should be treated the same way: when a user question produces a durable answer, that answer becomes a file. When a drift is detected, the LLM fixes the index. Human curates; agent maintains.

**AGENTS.md convention.** The root-level, nearest-wins convention is now the de facto standard (20k+ repos, Linux Foundation stewardship). `/context/` should be *referenced* from an `AGENTS.md` at the repo root, not replace it.

## Consensus patterns that work

1. **WHAT before HOW.** Specs describe user-visible behavior and acceptance criteria. Plans describe technical approach. Keeping these in separate files keeps specs stable as technology changes.
2. **Clarification markers over guesses.** `[NEEDS CLARIFICATION: ...]` is a first-class token. The single highest-leverage anti-hallucination tool in the research.
3. **Constitution read before every task.** Immutable principles aren't a README; they're a pre-prompt the agent re-reads each time.
4. **Gates at stage transitions.** Spec → plan requires spec to have no open markers. Plan → tasks requires plan to cite the constitution. Tasks → code requires tests first (in Spec Kit's constitution).
5. **Templates constrain quality.** Don't ask an LLM to "write a good spec." Give it a template with required sections and self-review checklists. The difference is dramatic.
6. **Per-feature packages, not monoliths.** Every framework treats a feature as a folder, not a document. Spec + plan + tasks + optional research + contracts.
7. **Plain Markdown.** No proprietary formats, no locked databases, no export friction. `grep`-able, `git`-able, `diff`-able.
8. **Index + log.** (Karpathy) An `index.md` that stays current and a `log.md` that grows append-only. Agent maintains both.
9. **Decisions are append-only.** ADRs supersede; they never rewrite. The audit trail is the product.

## Failure modes to design against

- **Spec drift.** The dominant failure. Gaps widen each cycle because AI generation is non-deterministic. Mitigation: specs live in repo, reviewed with code; periodic "lint" passes; consider file-save hooks later.
- **Doc explosion.** "Many frameworks are overkill… makes it harder to keep track of spec state, not easier." Mitigation: one topic per file, ruthless pruning, README-driven folders.
- **Static specs.** Specs can't capture all implicit context and decay as code evolves. Mitigation: treat spec as the source of truth but update it when reality diverges — don't let it fossilize.
- **Silent guessing.** The "plausible but wrong" class of error. Mitigation: hard rule on `[NEEDS CLARIFICATION]` markers.
- **Over-specification before commitment.** Writing a 12-file feature package for a one-hour fix. Mitigation: feature folders are proportional; `spec.md` alone is a valid feature for small work.
- **Bag-of-agents compounding errors.** Multi-agent orchestration without structure accumulates ~17x error rate. Mitigation: for now, single-agent with good context; don't spawn role-based subagents prematurely.

## Community tooling worth evaluating (deferred until `/context/` proves itself)

- [`github/spec-kit`](https://github.com/github/spec-kit) — reference CLI + templates; v0.5 as of early 2026
- [`SpillwaveSolutions/sdd-skill`](https://github.com/SpillwaveSolutions/sdd-skill) — Claude skill wrapping Spec Kit
- [`Pimzino/claude-code-spec-workflow`](https://github.com/Pimzino/claude-code-spec-workflow) — slash commands for Requirements → Design → Tasks → Implementation
- [`gotalab/cc-sdd`](https://github.com/gotalab/cc-sdd) — Kiro-style commands, multi-agent support
- [`buildermethods/agent-os`](https://github.com/buildermethods/agent-os) — 3-layer context installer
- [`me2resh/agent-decision-record`](https://github.com/me2resh/agent-decision-record) — AgDR format (ADRs for AI-made choices)
- [`bmad-code-org/BMAD-METHOD`](https://github.com/bmad-code-org/BMAD-METHOD) — role-based agent orchestration

Explicit non-decision: don't adopt any of these yet. Build `/context/` by hand first; let real friction tell us which tool to import.

## Decisions encoded in the current `/context/` structure

1. **Root is `/context/`, not `/spec/`.** "Specification" is too narrow — the tree holds principles, learnings, open questions, and research, not only specs. "Context" describes the whole, and generalizes beyond software (analyses, experiments, research).
2. **Stories, not features.** The per-work-unit folder is `stories/`, not `features/`. "Feature" is software-specific; "story" covers features, analyses, experiments, migrations, and research threads. The three-file internal structure (`spec.md` + `plan.md` + `tasks.md`) is unchanged.
3. **Stories are Spec-Kit-numbered (`NNN-slug`).** Sequential, never reused, git-branch-friendly. Leaves the door open to adopting Spec Kit tooling later without a rename.
4. **Three-file story rule.** Directly borrowed from Spec Kit's feature-package convention. Load-bearing: spec is stable, plan is regenerable, tasks are disposable.
5. **Constitution is a single root file, not a folder.** Agent OS splits standards by specialty; Spec Kit keeps a single constitution. For most projects, one file wins on readability.
6. **`decisions/` uses ADR numbering, append-only, supersede-don't-rewrite.** Standard ADR discipline, extended to cover AgDRs (decisions made by AI with human approval).
7. **`learnings/` is date-prefixed, free-form.** Karpathy-influenced — compounding knowledge, not structured records.
8. **`open-questions.md` is a single file, not a folder.** Open questions are few and cross-cutting; a folder would create premature categorization.
9. **`product/` separates `mission.md`, `roadmap.md`, and `brand.md`.** They change at different cadences (mission ~immutable, roadmap quarterly, brand occasionally) and serve different readers.
10. **No tooling built alongside.** Slash commands, skills, and hooks are deferred until the structure has absorbed real work.

## Applying this to a project

A rough order of operations for any project adopting this tree:

1. **Seed the constitution.** Pull from existing conventions already implicit in the codebase — test discipline, language/tooling choices, non-negotiable boundaries. Cap at ~7 articles; expand only when real friction demands it.
2. **Write a one-page mission.** If you can't say what you're building and for whom in a paragraph, the rest will drift.
3. **Migrate the first real story.** Pick an in-flight piece of work and decompose it into `spec.md` + `plan.md` + `tasks.md`. The first story will expose which conventions are missing.
4. **Extract conventions to `standards/` only after they recur.** Resist writing abstract standards before you have two or three concrete stories that would cite them.
5. **Capture decisions retroactively.** Any past choice that a contributor is likely to re-litigate deserves an ADR, even if the decision is old.
6. **Let `learnings/` accumulate naturally.** Don't seed it; write memos as you hit something worth remembering.

## Open questions this structure leaves open

1. **Constitution seeding.** Hand-authored vs. agent-drafted-then-edited.
2. **Drift prevention.** Validation slash commands, pre-commit hooks, file-save agents, or pure review discipline.
3. **Overlap with agent memory systems.** If an agent harness already maintains user/project memory, what belongs in `/context/` vs. in that memory layer?

## Sources

### Canonical
- [GitHub Spec Kit repo](https://github.com/github/spec-kit) — [`spec-driven.md`](https://github.com/github/spec-kit/blob/main/spec-driven.md)
- [AWS Kiro](https://kiro.dev/) — [Kiro GitHub](https://github.com/kirodotdev/Kiro)
- [Agent OS v2](https://buildermethods.com/agent-os/v2) — [3-Layer Context](https://buildermethods.com/agent-os/v2/3-layer-context)
- [BMAD Method](https://docs.bmad-method.org/) — [BMAD-METHOD repo](https://github.com/bmad-code-org/BMAD-METHOD)
- [Tessl](https://tessl.io/) — [Spec-Driven Development docs](https://docs.tessl.io/use/spec-driven-development-with-tessl)
- [AGENTS.md](https://agents.md/) — [agentsmd/agents.md repo](https://github.com/agentsmd/agents.md)
- [Karpathy LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

### Commentary and analysis
- [GitHub Blog: Spec-driven development with AI](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)
- [Microsoft Developer: Diving into SDD with Spec Kit](https://developer.microsoft.com/blog/spec-driven-development-spec-kit)
- [Red Hat: Vibes, specs, skills, and agents — four pillars](https://developers.redhat.com/articles/2026/03/30/vibes-specs-skills-agents-ai-coding)
- [Addy Osmani: How to write a good spec for AI agents](https://addyosmani.com/blog/good-spec/)
- [O'Reilly: How to write a good spec for AI agents](https://www.oreilly.com/radar/how-to-write-a-good-spec-for-ai-agents/)
- [VentureBeat: Agentic coding at enterprise scale demands SDD](https://venturebeat.com/orchestration/agentic-coding-at-enterprise-scale-demands-spec-driven-development)
- [Augment Code: Living specs for AI agent development](https://www.augmentcode.com/guides/living-specs-for-ai-agent-development)
- [Chris Swan: ADRs with AI coding assistants](https://blog.thestateofme.com/2025/07/10/using-architecture-decision-records-adrs-with-ai-coding-assistants/)
- [agent-decision-record (AgDR)](https://github.com/me2resh/agent-decision-record)
- [jamesm.blog: Spec Kit 2026 update](https://jamesm.blog/ai/github-spec-kit-2026-update/)
- [Wade Woolwine: Building an AI development constitution](https://wadewoolwine.com/blog/building-your-ai-development-constitution-the-essential-framework)
