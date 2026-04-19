# /context/stories

Per-story packages. Each story is a discrete unit of intentional work — a feature, an analysis, an experiment, a migration, a research thread. Not bound to agile ceremony; no requirement that a story be "user-facing" or estimable.

## Naming

```
NNN-kebab-case-slug/
```

- `NNN` is a zero-padded number (`001`, `002`, `042`, `1000`)
- Number is sequential across all stories, never reused
- Slug is git-branch-friendly
- The feature branch (when one exists) should be named `NNN-slug` as well

## Contents

Every story folder has at minimum:

```
NNN-slug/
  spec.md      # WHAT & WHY — intent, scope, acceptance criteria
  plan.md      # HOW — approach, trade-offs
  tasks.md     # DO — ordered executable task list
```

`spec.md` reads differently depending on the kind of work:

- **Feature:** user-visible behavior and acceptance criteria
- **Analysis:** the question being answered and what "answered" means
- **Experiment:** hypothesis, success/failure criteria
- **Migration:** current state, target state, reversal plan

Optional:

```
  research.md       # exploration notes, library comparisons, literature review
  contracts/        # API shapes, data models, schemas
  data/             # sample inputs, fixtures, reference outputs
  notes.md          # scratch space; delete on ship
```

## The three-file rule

- **spec.md** is stable: if the spec changes, the story has changed
- **plan.md** is regenerable: can be rewritten if a better approach emerges without touching spec
- **tasks.md** is disposable: it exists to guide execution; once shipped, it's history

## Lifecycle

1. Create folder with `spec.md` — leave `[NEEDS CLARIFICATION]` markers liberally
2. Review the spec until markers are resolved and acceptance criteria are testable
3. Write `plan.md` against the spec; cite `constitution.md` where it applies
4. Generate `tasks.md` from the plan
5. Execute against tasks; update plan/spec if reality disagrees
6. On ship: archive or prune `tasks.md`; keep spec and plan as the record

## Small stories

Not every story needs all three files. A one-hour fix can live as `spec.md` alone. The folder exists to *group* artifacts, not to *require* them. Err toward less ceremony when the work is small.
