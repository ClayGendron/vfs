# 2026-10-28 — The 0.1.0 roadmap audits

- **Status:** study set, read-only against `main` at `90f5883`. Feeds `../../../standards/roadmap.md` (the 0.1.0 definition of done).
- **Owner:** Clay Gendron
- **Method:** eight parallel read-only audits, one per domain, each a fresh subagent with the same brief; every claim labelled READ (a file or record was read), EXECUTED (a command or probe was run) or INFERRED (the auditor's synthesis). Two review passes on the roadmap draft followed (files 09 and 10); a third, the fact-check (file 11), is folded into the roadmap's second revision; a fourth, of the durable-run design (file 12), into the third. Nothing in the tree was edited by an auditor; no git state changed.
- **Why a study set and not a memo:** each file is new investigation (executed probes against `InMemoryStorage`, a real ipykernel, the statement counter, `gh run list`, PyPI, the web), not a transcription of in-session reasoning. The synthesis lives in the roadmap, which is a standard, not a research memo.

## The brief every auditor received

> Read `CLAUDE.md` first. `src/` and `tests/` are live; `src2/` and
> `tests2/` are archived. READ-ONLY: edit nothing, change no git state,
> no worktrees. Label every claim READ, EXECUTED or INFERRED. Report:
> (1) built today, with `file:line`; (2) in flight, with each spec's
> status line; (3) gaps against the 0.1.0 goal; (4) risks — wrong,
> stale or contradictory; (5) proposed stories, each with a why,
> dependencies and 3–8 testable acceptance criteria in the repo's style
> (count operations, never clocks; name engines; name classified
> kinds); (6) open questions Clay must decide.

The eight themes Clay named for 0.1.0 were given to every auditor: a public kernel API with human-in-the-loop interrupts; storage for SQLite, Postgres, SQL Server and Oracle; an embedding provider so `glean` fuses BM25 and vector at query time; three tool kinds, all interruptible; sync calls for Jupyter and ETL; serving vfs as an MCP server; everything is a file including tools under one permission structure; a bash-like CLI composing through the public APIs.

## Files

| # | File | Domain | Executed findings worth knowing |
|---|---|---|---|
| 01 | `01-kernel-api-and-interrupts.md` | the gate, the 25 verbs, ADR 087's arguments, interrupts | all three ADR 087 probes still reproduce on `InMemoryStorage`; no producer of `cancelled` or `timeout`; no sync facade |
| 02 | `02-storage-engines-and-dialects.md` | five profiles, the floor, CI legs, schema lifecycle | MSSQL leg red on `main` at the `apt` step (run 40689014566); every `IN` list chunked; no migration story |
| 03 | `03-search-glean-and-embeddings.md` | glean's legs, fusion, providers, renderers, graph | query-time embedding built; ADR 060's fastembed default never built; slow providers never converge |
| 04 | `04-shell-tools-mcp-and-wasi.md` | specs 167–173, the three tool kinds, `serve()` | nothing built; "MCP servers as the user" undecided; the pipe cannot checkpoint |
| 05 | `05-identity-rights-and-the-trust-edge.md` | `Authority`, the ladder, grants, spec 149 | no edge factory exists though the docstring names one; 100k-user numbers are a memo, not a pin |
| 06 | `06-developer-experience-sync-jupyter-etl.md` | sync, notebooks, ETL, docs, examples | `asyncio.run` fails in a real ipykernel; a 25-line thread-loop facade works; 10k write = 49 statements; 5 of 9 examples import dead names |
| 07 | `07-release-ci-and-repo-hygiene.md` | workflows, PyPI, the bump script, strays, the context pipeline | the publish matrix has never run; nothing yanked; 31 active specs, 10 proposed ADRs |
| 08 | `08-industry-needs-and-positioning.md` | 2026 needs, the eight themes classified, forgotten themes, copy risks | web sources cited inline; three truthful announcement sentences |
| 09 | `09-review-scope-gates-and-capacity.md` | PM review of the roadmap draft | the draft's own sizes sum to 26–48 weeks against a landing rate of 7 specs a month |
| 10 | `10-review-acceptance-criteria.md` | engineering review of every criterion | 9 blocking, 40 should-fix, 35 nits, each with a rewrite |
| 11 | `11-review-fact-check.md` | fact-check of every checkable claim in the draft | ten corrections (24 error kinds; 6 of 9 examples; `awk` 331 uses; 35–49 statements for the 10k write; four names that are spec proposals, not live code); every cited ADR pin and spec status confirmed |
| 12 | `12-review-the-durable-run.md` | engineering review of the third revision's durable-run design (domain B, F3 c10, T2, T5, M3, D40–D44) | nine contradictions with specs 167/169/170/172/177 and ADRs 063/081/084 by `file:line`; resume authority unspecified; no crash semantics; reads are inputs to the walk; the arithmetic recount |

Paths inside the files that begin with `/tmp/…/scratchpad/` were the auditors' working directory; the files now live here.
