# 2026-10-29 — The development process: seven studies, one per stage

This folder is the study set for [the research memo](../../2026-10-29-the-development-process-seven-studies-and-what-they-recommend.md), owned by Clay Gendron and read-only against `main` at `1198d92`. The method was seven parallel studies, one per stage of the pipeline intent → research → spec → review → code → review → commit, each a fresh general-purpose agent given the brief below and a 30-minute box; every claim labelled; nothing copied from any other project; wasi-python read at `1431ba6f` (Apache-2.0). Three rulings from Clay arrived while the studies ran and were relayed to every agent: no numbers in document file names (every intention, spec and review is `YYYY-MM-DD-descriptive-slug.md`); the intention document has no header lines; the code stage is tests first, then code. It is a study set and not a memo because each stage has its own prior art (Anthropic's SDLC material, user-story templates, RFC and design-doc processes, review practice, coding-pattern pages, commit conventions) and its own corner of the two repositories to read; one agent per stage keeps each study self-contained and auditable, and the memo is the synthesis.

## Labels

EXECUTED means a command was run here and the claim reports its output. READ means read in a file or page cited by path or URL. INFERRED means the researcher's reasoning from the two.

## The brief every researcher received

> You are one of seven research agents studying the seven stages of vfs's new development process: intent → research → spec → review → code → review → commit. Your stage is **<stage>**.
>
> Repo: /Users/claygendron/Git/Repos/vfs. Read first: CLAUDE.md, context/README.md, and the intention context/intentions/2026-10-29-the-development-process.md. Decided already by Clay: [the rulings listed per stage: one file per spec; no ADRs, decisions live in the spec; every spec carries an architecture diagram; no open questions; every change needs a spec; reviews are files in context/reviews/, one before build and one before landing, by a fresh reviewer given the spec and the diff; no pull requests, a change lands by a commit to main when Clay asks; Cloudflare's security-audit skill installed unchanged and cited].
>
> Your question: <one question per stage, recorded in each study's Question line>.
>
> Method: study the sibling project wasi-python (~/Git/Repos/wasi_python, read-only; never modify, never copy; record its commit); study vfs's own practice; read online prior art with WebSearch and WebFetch, recording URLs and read dates. Describe, never copy at length.
>
> Write your study to context/research/studies/2026-10-29-the-development-process/0N-<stage>.md with header lines Status, Date, Owner, Question, Method, Sources; then sections: What the sources say (each claim labelled READ, EXECUTED or INFERRED); What vfs does today; The recommended format (a complete Markdown skeleton in a fenced code block); the rules; a lint rule that could hold the shape; One line.
>
> Rules: short sentences, one idea each, define each term of art on first use, say the key idea more than once. Never copy code or long passages from any other project. Do not edit any other file in the repo. Do not run git commands that change state. Time box 30 minutes; at the box, stop and record where you stood.

The stage-specific additions: the intent study read Anthropic's published AI-SDLC material; the code study read the live `src/` and `tests/` tree for the patterns it already follows; the code-review study read the Cloudflare security-audit skill as installed in wasi-python and found its licence and install command; the commit study read sixty commits of vfs's own history.

## Files

| # | File | Question | Executed findings worth knowing |
|---|---|---|---|
| 01 | `01-intent.md` | What format does an intention take, when is one written, how does it link forward? | Anthropic's playbook has an `intent.md` stage before `spec.md`, read by plan mode "if one exists"; the four user-story templates agree on person, value, check. |
| 02 | `02-research.md` | What shape do a memo, a placeholder memo and a study take, and what holds them? | Of 154 vfs memos, 131 carry no evidence label and 95 have no Method line; no test reads `context/`; the kernel memo was revised in place twice against the append-only rule. |
| 03 | `03-spec.md` | What is the required shape of a spec, its Kind vocabulary, its lifecycle, its lint? | 31 active spec folders, 23 with markers (72 marker lines), 4 with a plan or task file; ten ADRs still "proposed"; the architecture pages use five Mermaid kinds with `planned` and `retiring` classes. |
| 04 | `04-spec-review.md` | What format does a spec review take and what does a reviewer check? | Spec 164's pre-build review lives in a lost scratchpad; only its amendments survived in the spec. |
| 05 | `05-code.md` | Which coding patterns does the repo follow, and how are they written as one standard? | 24 named patterns, each with `file:line`; `contributing.md` names `VFSResult` and `DatabaseFileSystem`, zero hits in `src/`; 68 test files name their mutant, 0 of 842 commits say "seen failing". |
| 06 | `06-code-review.md` | What format does a code review take, how do the seven skills fold in, how is the Cloudflare skill installed? | The skill is MIT (Cloudflare, 2025-2026); `npx skills add … -a claude-code` writes `.claude/skills/security-audit/` and `skills-lock.json`; guidance mode writes no artifacts. |
| 07 | `07-commit.md` | What is the commit format, the landing order, the gate, and the changelog answer? | Every one of the last sixty subjects is `type(scope): words`, many past 72 characters, 21 with a `(spec …)` suffix; `test.yml` skips `context/`-only commits. |
