# /context/standards

What every stage of [the pipeline](../README.md) obeys. These pages change rarely, by a spec that says so, and the other folders must agree with them.

| Page | What it holds |
|---|---|
| [constitution.md](constitution.md) | The policies that, if broken, stop vfs from being vfs: the five primitives, the agent-first contract, the error taxonomy, the capability model, operational discipline. |
| [mission.md](mission.md) | What we are building, who it is for, and why it should exist. |
| [roadmap.md](roadmap.md) | What "0.1.0 is done" means, domain by domain, as stories with acceptance criteria. |
| [how-we-code.md](how-we-code.md) | The reusable patterns the repository follows, written so a code review can check a diff against them line by line: test first, gate then act, parse at the boundary, classify failures, bounded storage, the engine seam, the shape of a module, the tests. |
| [landing.md](landing.md) | How a change lands: the commit format and its trailers, the landing checklist, the gate, the changelog line, and the licence of the installed review skills. |
| [python-style.md](python-style.md) | What `ruff` enforces and the conventions it cannot. |
| [testing.md](testing.md) | The test tiers, pins with their mutant, never mocking the database, the engine legs. |
| [tooling.md](tooling.md) | uv, ruff, ty, the Rust extension, `scripts/ci.sh`. |
| [release.md](release.md) | How a release is cut from `main` and how the changelog is assembled from the landed specs. |
| [quality-rubric.md](quality-rubric.md) | How the repository's quality is scored, and the [grades/](grades/) time series. |
| [mutant-ledger.md](mutant-ledger.md) | The replayable one-line mutations each pinned law is proven by. |

A convention that matters enough to write down matters enough to have its own page. Spec-specific design belongs in the spec; historical decisions live in the spec that carried them.
