# /context/decisions

Architecture Decision Records (ADRs) — and, increasingly, Agent Decision Records (AgDRs) for choices the AI made with user approval.

## What belongs here

- A choice that was non-obvious at the time it was made
- A trade-off that a future reader would otherwise re-litigate
- A decision that overrides or refines the constitution

## What does not belong here

- "We decided to use Python" (scaffolding, not a decision)
- Implementation details (→ story plans)
- Preferences that can evolve freely (→ `standards/`)

## Naming

```
NNN-short-slug.md
```

Numbered sequentially. Never renumbered.

## Template

```markdown
# NNN. <Title>

- **Status:** proposed | accepted | superseded by NNN | deprecated
- **Date:** YYYY-MM-DD
- **Deciders:** names
- **Decided by:** human | AI-with-approval

## Context
What forced the decision? What constraints were in play?

## Options considered
- Option A — pros, cons
- Option B — pros, cons
- Option C — pros, cons

## Decision
We chose <option> because <reason>.

## Consequences
- What becomes easier
- What becomes harder
- What we are now committed to
```

## Supersession

Never edit an accepted decision. If we change our mind, write a new ADR that supersedes the old one and update the old one's status to `superseded by NNN`.
