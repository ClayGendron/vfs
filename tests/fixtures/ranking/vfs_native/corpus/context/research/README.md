# /context/research

The RESEARCH stage of the pipeline (research → decide → specify → code).
Raw study of precedent that informs decisions: literature reviews, reference
repo deep-dives, benchmarks, landscape and competitive analyses,
post-mortems.

## What belongs here

- Study of prior art before a decision gets made (Plan 9, fsspec, pgvector,
  turbopuffer, …)
- Benchmarks and spike write-ups whose numbers outlive the spec that
  ordered them
- Post-mortems on incidents or failed experiments
- Generalized patterns extracted from multiple specs

## What does not belong here

- Decisions we're committed to (→ `../decisions/`)
- Actionable work packages (→ `../specs/`)
- Unknowns (→ `../open-questions.md`)

## Naming

```
YYYY-MM-DD-short-slug.md
```

Date-prefixed so time-order is visible. Research authored inside a spec
moves here under a dated name when it's worth keeping — specs link to
research, they don't contain it.

## Rules

- **Append-mostly.** A memo is a record of what we learned when we learned
  it. Don't edit it after the fact — supersede it with a newer memo and
  cross-link.
- A memo should be re-readable by a future reader who has forgotten the
  original context.
- Decisions cite memos here; a memo on its own commits us to nothing.
- Memos written before 2026-07-16 lived in `context/learnings/` and may
  reference `stories/` paths; those now resolve under `../specs/` or
  `../specs/archive/`. Historical text stays as written.
