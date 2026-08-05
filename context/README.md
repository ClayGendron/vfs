# /context

The durable memory of this project. Everything an AI agent or a new human
contributor needs to understand **what** we're building, **why**, and **how
we build it** — separated from the code itself.

Code is a build artifact of this context. When code and context disagree,
fix the code (unless the context is demonstrably wrong, in which case fix
the context first).

## The pipeline

We work **research → decide → specify → code**, all while following
standards. Each directory is one stage:

```
context/
  README.md             # this map
  open-questions.md     # intake: unknowns, undecided calls, parked ideas
  research/             # RESEARCH — dated memos: raw study of precedent
  decisions/            # DECIDE — ADRs: point-in-time choices, append-only
  specs/                # SPECIFY — open work packages, single-dev scope
  standards/            # FOLLOW — rarely-changing governing docs + grades/
```

## Lifecycle rules

The directory names matter less than the flow contract between them:

- **`research/`** — append-mostly, date-prefixed (`YYYY-MM-DD-slug.md`),
  never edited after the fact (supersede with a newer memo). Raw study of
  precedent, benchmarks, landscape. A research memo commits us to nothing.
  Prior-art study never copies code: studied projects inform the design of
  our own original implementation — memos cite and describe, nothing more.
- **`decisions/`** — append-only ADRs. Each cites the research it stands on
  and names what it supersedes. Where "we studied X" becomes "we will do Y."
- **`specs/`** — **retired on landing, never authoritative afterward.**
  Born from decisions, small enough for one developer, self-contained
  enough to leave the repo. Open specs live in `specs/active/`; on
  landing a spec moves to `specs/archive/`, and its durable residue
  flows *backward* — decisions made during implementation →
  `decisions/`, research done along the way → `research/`. The mined
  folder stays in `archive/` as a historical record (policy since
  2026-08-05 — archived specs were previously slated for deletion);
  nothing there governs current work.
- **`standards/`** — versioned, rarely changed, and the only directory the
  other three must obey. Holds the constitution, mission, roadmap, the
  how-we-build standards, the quality rubric, and the `grades/` time series.

The backward-flow rule is the key design point: it is what lets a
landed spec safely go stale and keeps `decisions/` and `research/` as
the permanent memory a reader can trust without opening the archive.

## Clarification over guessing

When authoring any document here, mark uncertainty explicitly:

```
[NEEDS CLARIFICATION: which auth method — OAuth, SSO, email/password?]
```

Never silently guess. The marker is a first-class citizen, should be
surfaced in reviews, and gets a pointer in `open-questions.md`.

## Conventions

- Plain Markdown, no proprietary formats
- Each document has a frontmatter-free header: title, status, date, owner
- Cross-reference liberally with relative links
- Prefer small, focused documents over monoliths
- `research/` is append-mostly; `decisions/` is append-only (supersede,
  don't rewrite)
