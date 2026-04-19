# /context

The durable memory of this project. Everything an AI agent or a new human contributor needs to understand **what** we're building, **why**, and **how we build it** — separated from the code itself.

Code is a build artifact of this context. When code and context disagree, fix the code (unless the context is demonstrably wrong, in which case fix the context first).

## Structure

```
context/
  constitution.md       # immutable principles — read before every task
  open-questions.md     # unknowns, undecided, parked items
  product/
    mission.md          # what we're building and for whom
    roadmap.md          # ordered direction, not a commitment
  standards/            # how-we-build: conventions, patterns, skills
  stories/              # per-story packages (001-foo, 002-bar) — features,
                        #   analyses, experiments, migrations
    NNN-slug/
      spec.md           # WHAT & WHY — intent, scope, acceptance criteria
      plan.md           # HOW — approach, trade-offs
      tasks.md          # DO — ordered executable task list
      research.md       # optional — captured exploration
  decisions/            # ADRs: point-in-time choices with rationale
  learnings/            # research, post-mortems, shared insights
```

## The three-file rule for stories

Every story is a folder with at least `spec.md` (WHAT), `plan.md` (HOW), `tasks.md` (DO). A story can be a feature, an analysis, an experiment, a migration — any discrete unit of intentional work. This separation is load-bearing:

- **spec.md** stays stable as tech choices change
- **plan.md** can be regenerated when the spec is solid
- **tasks.md** is ephemeral — shipped stories can archive or delete it

## Clarification over guessing

When authoring any document here, mark uncertainty explicitly:

```
[NEEDS CLARIFICATION: which auth method — OAuth, SSO, email/password?]
```

Never silently guess. The marker is a first-class citizen and should be surfaced in reviews.

## Conventions

- Plain Markdown, no proprietary formats
- Each document has a frontmatter-free header: title, status, date, owner
- Cross-reference liberally with relative links
- Prefer small, focused documents over monoliths
- `learnings/` is append-mostly; `decisions/` is append-only (supersede, don't rewrite)
