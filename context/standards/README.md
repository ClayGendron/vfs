# /context/standards

How-we-build. Conventions, patterns, and procedural skills that shape code without constraining what the code *is*.

## What belongs here

- Naming conventions and style rules
- Non-functional requirements (performance budgets, accessibility, etc.)
- Recurring patterns the team has converged on
- Procedural skills: "how to add a new migration", "how to author a new CLI command"

## What does not belong here

- Immutable rules (→ `constitution.md`)
- Story-specific design (→ `stories/`)
- Historical decisions (→ `decisions/`)

## Organizing

Prefer one topic per file. Good names:

```
standards/
  python-style.md
  testing-approach.md
  error-handling.md
  naming-conventions.md
  commit-and-pr.md
```

A convention that matters enough to write down matters enough to have its own file.
