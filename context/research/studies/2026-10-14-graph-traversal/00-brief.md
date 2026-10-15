# Shared brief for every researcher on the vfs graph-traversal study (2026-10-13)

## The project
vfs (`/Users/claygendron/Git/Repos/vfs`) is a virtual filesystem for AI agents over a SQL
database (SQLite dev default; Postgres, MariaDB, SQL Server 2025, Oracle 23ai in production).
Live code is `src/vfs` and `tests/`; `src2/` and `tests2/` are an ARCHIVED pre-refactor quarry:
you may read them for semantics but never run, lint or port them.
Run Python only through `uv run python ...` from the vfs repo root. Write any script or output
in the scratchpad dir `./`
(subdirs `research/` for reports, `experiments/` for scripts). NEVER modify files under
`/Users/claygendron/Git/Repos/vfs`. NEVER create git worktrees or branches.

## The question we are answering
Design the `graph` verb: read-side graph traversal (NOT centrality — centrality is index-time
data already, out of scope) over the `vfs_edges` table, SQL-native on every supported dialect,
with the caller's rights enforced inside the traversal (a node the caller may not see is absent,
and nothing is reached through it), correct and bounded at 10,000+ seeds per call.
Clay's four directions: (1) SQL native as much as possible; (2) rights enforced through the
traversal; (3) collapse predecessors/successors/ancestors/descendants into a direction plus a
`depth` argument, with names that make direction unmistakable; (4) every supported dialect
serves graph (the old rule withholding it from unknown dialects is to be revisited).

## What is already law in vfs (read these first, they bind the design)
- `src/vfs/ops.py` (GRAPH_METHODS, the closed vocabulary today: predecessors, successors,
  ancestors, descendants, neighborhood, meeting_subgraph, min_meeting_subgraph).
- `src/vfs/params.py` lines ~286-292 (the gate: method, path, observations, depth>=1, authority).
- `src/vfs/base.py` `graph()` (~line 1493) and the `_route_single` dispatch.
- `src/vfs/storage/protocol.py` `SupportsGraph`.
- `src/vfs/models/rows.py` lines ~595-625: `vfs_edges` (id, source_id, target_id, edge_type,
  weight, distance, provenance, context; unique (source,target,type); indexes fwd (source_id,
  edge_type) and rev (target_id, edge_type); NO path columns — addressing and liveness come from
  joining the entries table). Also read the entries table definition in the same file.
- `src/vfs/storage/backends/database/edges.py` module docstring: the hierarchy is mirrored as
  reserved `fs` edges (parent -> child), one per non-root entry; authored edges have other types.
  Edges whose endpoint is tombstoned (deleted_at set) are hidden by the liveness term every edge
  reader carries.
- `src/vfs/storage/backends/database/descent.py` (`liveness_filters`, `subtree_filter`),
  `rights.py` and `ranges.py` module docstrings (the visibility predicate: `Visibility`,
  `visible_entries` three-seek UNION ALL join, or a literal OR of path terms; `Rights.admits` in
  Python is the authority and SQL is a pushdown), `reads.py` (how `tree` and `ls` are served).
- `src/vfs/storage/backends/database/dialects.py` (`DialectProfile`, `membership_budget`,
  `chunked`, `in_list_budget`): no statement may grow with batch size; IN lists chunk by the
  tighter of Oracle's 1,000-element cap and the bind budget.
- `context/decisions/018-*.md` (edges), `065-*.md` (hidden rows are absent, names edge
  traversals), `067-*.md` (the predicate function), `059-*.md` pin 4 (the withholding rule).
- `context/research/2026-03-03-graph-memory-and-meeting-subgraph.md` and
  `2026-04-22-mssql-native-meeting-subgraph.md` (pre-refactor meeting-subgraph work).
- `context/specs/archive/004-postgres-native-meeting-subgraph/spec.md` "Method-Specific
  Semantics" (the pre-refactor semantics of each method).

## Rules of evidence
- Reference repos live in `~/Git/Repos/<name>` and are READ-ONLY. They were refreshed to their
  upstream default branch on 2026-10-13. Cite `repo:path:line`. Describe, never copy code.
  Licences were checked (Apache/MIT/BSD/PostgreSQL; neo4j is GPL and afs is BSL: study only).
- Separate what you EXECUTED from what you READ from what you INFERRED. Label each.
- An experiment is worth more than a claim. Where you can run something (compile a statement,
  run a query on SQLite, write a Python reference), do it and report the output.
- Mark anything you could not verify as `[NOT VERIFIED: why]`.
- Use WebSearch (standard mode; extended for engine docs) for engine documentation facts
  (MariaDB, SQL Server, Oracle, PostgreSQL, SQLite) and cite the URL.

## Deliverable
Write your report as Markdown to the file named in your task prompt. Lead with a one-paragraph
summary and a findings table; then the evidence per source; then open questions. Use short
sentences. Your final chat reply is just the path and a five-line summary.
