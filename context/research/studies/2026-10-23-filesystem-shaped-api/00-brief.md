# Brief: should vfs's public API become filesystem-shaped?

- **Date:** 2026-10-23
- **Asked by:** Clay Gendron. His words: "vfs was designed around tools for an AI, and then it was designed that we'll build a CLI that calls those public APIs, and then we decided to also add Python, and I'm sure we'll add more later. But the core vfs design has stayed the same, around AI-tool-like signatures. What would a refactor look like to make vfs more of a 'real' file system? We still have the database persistence constraint and still need the indexes we have for search. I do not care about time and cost to rebuild or refactor; I only care about what design makes vfs better positioned to grow and maintain or improve its performance."
- **The question each study answers, in its own corner:** what is the right *kernel* API for a filesystem whose rows live in a SQL database and whose bodies are indexed for search, when that kernel must serve at least four front ends: MCP tools for a model, a bash-shaped CLI, a WASI guest's POSIX file calls (through wasi-python's eight-method mount provider), and bulk ETL (10,000-row batches)?

## What vfs is today (read `src/vfs/base.py`, `session.py`, `ops.py`)

Every verb is one async method on `VirtualFileSystem` taking a path (or a list of `Observation` rows), keyword options, and an `authority=`, returning one `Result` envelope of `Observation` rows plus classified errors. Bodies are whole (`content` text column XOR `data` blob); there are no handles, no offsets, no directory cursors, no streaming. Writes mint versions; deletes are tombstones; the permission ladder gates every verb at one chokepoint. The search verbs (`glob`, `grep`, `glean`, `graph`) share the same envelope as `read`/`ls`. This shape was chosen for MCP tools first (ADR 010, spec 171) and is being adapted to a CLI (spec 167) and a WASI Python guest (spec 172; memo `2026-10-23-wasi-python-0-1-0-over-vfs-the-mount-and-the-tool-door.md`).

## Rules for every study

- Read-only over `~/Git/Repos/<repo>`; every clone was refreshed to its upstream default branch today (`refresh.log` has commit, date and licence). **Never copy code.** Cite file and line; describe designs.
- Label every claim **READ** (a file at the commit), **EXECUTED** (ran here), or **INFERRED**.
- Answer the study's numbered questions in order; keep each answer short; put the one design lesson for vfs at the end of each answer.
- Do not recommend for vfs as a whole; that is the synthesis's job. Report what the studied project does and why, with evidence.
- Write the report to `context/research/studies/2026-10-23-filesystem-shaped-api/<NN>-<slug>.md`. Never touch `src/`, `tests/`, `pyproject.toml`, any ADR or spec. No worktrees, no branches, no commits.
- `uv run` for any Python; never `pip`.
