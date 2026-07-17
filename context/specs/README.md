# /context/specs

The SPECIFY stage of the pipeline (research → decide → specify → code).
A spec is a detailed work package with a small scope — small enough to hand
to a single developer (human or agent) to complete, and self-contained
enough to leave the repo as a handoff artifact.

## Naming

```
NNN-kebab-case-slug/
```

- `NNN` is a zero-padded number, sequential across all specs, never reused
  (the sequence continues from the pre-reorg stories)
- Slug is git-branch-friendly; the feature branch (when one exists) should
  be named `NNN-slug` as well

## Contents

Every spec folder has at minimum:

```
NNN-slug/
  spec.md      # WHAT & WHY — intent, scope, acceptance criteria
  plan.md      # HOW — approach, trade-offs
  tasks.md     # DO — ordered executable task list
```

- **spec.md** is stable: if the spec changes, the work has changed
- **plan.md** is regenerable: can be rewritten if a better approach emerges
- **tasks.md** is disposable: it guides execution, nothing more

Optional: `contracts/` (API shapes, schemas), `data/` (fixtures),
`spike/` (throwaway scripts and their result write-ups), `notes.md`
(scratch; delete on ship). Substantive research does **not** live here —
it goes to `../research/` as a dated memo, and the spec links to it.

A small fix can live as `spec.md` alone. The folder groups artifacts, it
doesn't require them.

## Lifecycle — specs are ephemeral

1. A spec is born from a decision (or directly from the roadmap for small
   work); it cites the decisions and research it stands on
2. Draft `spec.md` with `[NEEDS CLARIFICATION]` markers; review until
   markers are resolved and acceptance criteria are testable; pointer each
   open marker in `../open-questions.md`
3. Write `plan.md` against the spec, citing `../standards/constitution.md`
   where it applies; generate `tasks.md` from the plan
4. Execute; update plan/spec if reality disagrees
5. **On landing, durable residue flows backward**: decisions made during
   implementation → `../decisions/`, research and benchmark results →
   `../research/` — then delete the folder. Git history is the archive.

## Status tracking

`STATUS.md` is the periodic cross-spec true-up: every spec's status line
verified against the live code. Trust per-spec `spec.md` status lines
first; regenerate STATUS.md when the picture shifts.

## archive/

Pre-reorg landed stories (2026-07-16) that haven't had their mining pass
yet — their inline decisions and research haven't flowed backward. Mine
opportunistically; delete each folder once mined. Nothing in `archive/`
governs current work.
