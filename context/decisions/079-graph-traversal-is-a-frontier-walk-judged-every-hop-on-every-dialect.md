# 079. Graph traversal is a frontier walk — one chunked statement per hop, rights judged on every row, served on every dialect

- **Status:** proposed (2026-10-14; revised the same day after Clay's
  review of the first cut — the names, the `minimal` flag, the hierarchy
  mirror off by default, the traversal-rights rule on the permission
  ladder, `limit` 128, induced edges rendered with `tree`'s glyphs
  and no diagram arrangement, and the ladder spec 165 sequenced
  before the build). On acceptance:
  amends ADR 059 pin 4 (the graph half of the withholding rule is
  void; `glean` alone is withheld from a dialect with no distance
  function), amends ADR 016 pin 4 (the deferred `edges(path,
  direction, type)` read verb is a depth-one walk's edge rows, not a
  separate verb), and retires the seven-method vocabulary spec 067
  recorded in `ops.py`. **Pin 2 amended by ADR 080 (accepted 2026-10-14, spec 165 landed):** the walk's rung is `list` to pass a node and `read` to return its contents, read from `VERB_RUNGS["graph"]`.
- **Date:** 2026-10-14
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay set the four directions on 2026-10-13:
  SQL native as much as possible, rights enforced through the
  traversal, direction plus depth in place of four methods, every
  dialect serves graph; the assistant led six research studies and
  proposes the shape and the vocabulary below for his decision)

## Context

The `graph` verb has a router, a parameter gate, a closed vocabulary
of seven methods and no backend. ADR 018 put the hierarchy into the
edges table as reserved `fs` rows so that one query over one table
answers every edge question. ADR 065 says a hidden row is absent from
edge traversals. ADR 059 withheld `graph` from unknown dialects on the
grounds that the floor cannot declare the engine fact it needs — a
rule written before anyone knew what fact a traversal needs.

The memo `research/2026-10-14-graph-traversal-prior-art-and-experiments.md`
studied thirty-two reference systems and ran the two candidate shapes
on the live vfs schema. The facts that force the decision:

- A recursive CTE has no visited set. With a depth column it
  enumerates paths. SQL Server and Oracle allow only `UNION ALL` in
  the recursive member, where a 200-node cycle costs 7.9 million rows
  at depth 3 and 1.58 billion at depth 4. Postgres, SQLite and
  MariaDB allow `UNION`, which bounds the rows polynomially but still
  re-expands every node on every level.
- Rights applied after a walk leak: a visible node behind a hidden
  one is reached (executed). The predicate must run on every hop.
  Inside a recursion the Python authority `Rights.admits` cannot
  judge rows and the generic floor's clause fan cannot ride at all;
  in a per-hop loop both work as they do for `tree`.
- The meeting subgraph must stop when the seeds are joined, which no
  recursive CTE can express; the per-hop loop stopped at hop 2 where
  the CTE ran to its bound at thirty times the work.
- No shipping system compiles hops into recursive SQL. SpiceDB,
  OpenFGA, cayley and the old vfs backend all walk hop by hop in the
  application with one flat query per hop.
- `in_degree` and `out_degree` are counts in every library and are
  already count fields on `Observation`.
- The archived directed pruning rule for the meeting subgraph deletes
  the shared dependency in `a → x ← b`.

## Options considered

- **One recursive CTE per seed chunk** — one statement per chunk of
  `membership_budget` seeds, visibility as a materialized sibling set,
  depth bound in the recursive member, `GROUP BY node, MIN(depth)`
  outside. Pros: the fewest round trips (1 / 5 / 10 statements for
  10,000 seeds on SQLite-Postgres-MariaDB / SQL Server / Oracle,
  independent of depth); one snapshot per chunk. Cons: exponential on
  the two engines that refuse `UNION`; polynomial but node × level
  work on the other three; rows returned grow with the chunk count;
  SQL Server needs a `#temp` table for the visible set (DDL on a
  read); Oracle needs a `CYCLE` clause and MariaDB a session cap; the
  Python authority is not the referee; the clause fan cannot ride;
  three new `DialectProfile` fields; "stop when connected" is
  impossible.
- **A frontier walk, one chunked statement per hop (chosen)** — the
  application holds the frontier, the visited set and the stop
  condition; each hop issues one statement per frontier chunk over
  `vfs_edges` joined to the entries table, narrowed by the caller's
  view exactly as `tree` is, and every returned row passes
  `Rights.admits` before it joins the frontier. Pros: bounded by the
  nodes reached on every engine (399 rows in two statements on the
  cycle bomb); the rights law holds as it does for every read; early
  stop; no DDL; no engine fact, so the generic floor serves it. Cons:
  round trips grow with the depth reached (Σ over hops of the
  frontier's chunks: 2–3 / 6–7 / 12–13 statements at depth 2–4 for
  10,000 seeds); the snapshot may move between hops under a rival
  writer, as it does for `tree` followed by `read`.
- **A per-dialect stored procedure** — the archived PL/pgSQL and
  T-SQL. Pros: one call. Cons: five bodies to maintain; the archived
  ones copied the whole edge table per call; DDL at provisioning.
  Rejected.
- **Whole graph in memory plus a Rust kernel** (AGE, DuckPGQ). Pros:
  fastest. Cons: the whole-corpus profile on every call; rights
  filtered at load; not SQL native. Rejected for the verb; a kernel
  for the small post-walk phase of the meeting subgraph stays open.

## Decision

Ten pins.

**The shape:**

1. **`graph` is a frontier walk.** The backend resolves the seeds
   (one chunked statement, hidden and tombstoned seeds absent), then
   walks: each hop is one statement per chunk of the frontier under
   `membership_budget`, selecting the frontier's edges in the chosen
   direction from `vfs_edges`, joined to the entries table on the far
   endpoint with the liveness term, narrowed by the caller's view, and
   using the dialect's join pin. The application removes visited
   nodes, judges every row with `Rights.admits`, and makes the rest
   the next frontier. No statement grows with the batch; the per-call
   statement count is the sum over hops of the frontier's chunks.
2. **Rights are judged on every hop, by the same authority every read
   uses.** `Visibility.narrow` narrows each hop statement (the
   three-seek join or the clause fan merged per hop); `admits` judges
   each returned row. The rule is: **to traverse an edge the caller
   must hold the walk's rung on both endpoints.** A node below that
   rung never enters the frontier, so nothing is reached through it.
   The rung is one declared entry in the verb-to-rung table, today
   `read` (the only visibility rung the ladder has). The expanded
   ladder (spec 165: `none < list < read < add < contribute <
   read_write`, `manage` parked) is where "you may pass a directory you may not read" is
   decided — a `list` rung on an intermediate node, with the road of
   ADR 070 counting as `list` — and when it lands the graph verb's rung
   flips in that one table entry. Until then a road-only directory is
   absent in a walk, exactly as every other edge-shaped verb already
   treats it (memo 2026-09-28 §5.2), and the hierarchy mirror is not
   followed by default (pin 6), so the case arises only when a caller
   names `fs`.
3. **Every dialect serves `graph`.** The walk needs no engine fact,
   so `DatabaseStorage.capabilities()` withholds only `glean` from a
   profile with no distance function. ADR 059 pin 4 is amended to
   that effect.
4. **The recursive CTE per chunk is the recorded acceleration, not the
   shape.** It is correct and cheaper in round trips on engines that
   deduplicate `UNION`; it arrives as a dialect-declared arm in its
   own spec only if a measured profile shows round trips dominating,
   never on SQL Server or Oracle.

**The vocabulary:**

5. **Four methods: `inbound`, `outbound`, `neighborhood`, `meet`.**
   `outbound` follows each edge from its `source` to its `target` —
   what this node points to, the direction `mkedge` was given;
   `inbound` follows edges from `target` back to `source` — what
   points at this node; `neighborhood` follows both; `meet` returns
   the subgraph that joins the seeds (the meeting subgraph), and
   `meet` with `minimal=True` prunes it to the nodes needed to keep the
   seeds connected. `predecessors`, `successors`, `ancestors`,
   `descendants`, `meeting_subgraph` and `min_meeting_subgraph`
   retire. `forward` / `reverse` were considered and rejected (Clay:
   a reference points at an older document, so "forward" reads as
   going back in time); `in` / `out` because `in` is a Python keyword;
   `both` / `around` because they do not say what the walk does.
   `in_degree` and `out_degree` stay what they are, count fields.
6. **Parameters:** `depth` (int ≥ 1, default 1; `None` walks until
   the frontier empties, lawful because the visited set bounds it by
   the nodes reached), `edge_types` and `edge_types_not` (sequences of
   type names; empty follows every **authored** type), `minimal`
   (bool, default false; lawful only with `meet`, `invalid`
   elsewhere), `limit`, `columns`, `authority`. Seeds come as a path or
   as observations, as today. For `meet`, `depth` is the search radius
   per seed. **The hierarchy mirror is not followed by default:** `fs`
   edges are followed only when `edge_types` names `fs`, so a walk is
   over the relations callers and extractors authored unless the
   caller asks for the tree. (ADR 018 keeps `fs` an ordinary type
   name; this pin sets the default, not the law.)
7. **Seeds are included at depth 0 in every method.** A seed the
   caller cannot see, or that is tombstoned, yields no row and starts
   no hop.

**The rows:**

8. **Node rows and edge rows in one answer.** A node row carries
   `path`, `kind` and a new query field `depth` (distance from the
   nearest seed). An edge row is the shape `mkedge` already returns:
   `path` = source, `edge_target`, `edge_type`, `edge_weight`,
   `edge_distance`. The edge rows are **every edge among the returned
   nodes** — the induced subgraph — for walks and for `meet` alike
   (Clay, 2026-10-14: present the connections with their edge types
   in a form that conveys complicated graphs), so an agent sees
   cross-links and cycles, not only the tree of discovery. Order:
   nodes by depth then path, then edges by source, type, target.
   `limit` (int ≥ 1, **default 128**; `None` returns every row) cuts
   node rows in that order; edge rows follow the nodes — an edge
   touching a cut node is cut too, so the answer is always a
   consistent subgraph — and the cut is reported with the existing
   `ErrorKind.truncated` warning. `graph` gets its own renderer
   arrangement: **the tree glyphs `tree` already prints**, one line
   per reached node indented under the node that discovered it with
   the edge type on the line and the depth in brackets, every further
   edge among the returned nodes printed where its source sits and
   marked as a cross-link or a cycle, the meeting point marked for
   `meet`, and a closing count line. No Mermaid or other diagram
   arrangement is planned (Clay, 2026-10-14): the rows carry every
   edge and type, so a caller who wants a drawing makes its own.
9. **ADR 016's `edges(path, direction, type)` is a depth-one walk.**
   `graph("outbound" | "inbound", path, edge_types=(type,))` read
   through its edge rows is that verb; no separate name.

**The meeting subgraph:**

10. **`meet` is a multi-source undirected frontier walk with
    declared tie-breaks.** Discovery follows every selected edge type
    in both directions; each node is owned by the nearest seed, ties
    by seed input order; a meeting is an edge between differently
    owned nodes; union-find merges components; the walk stops when
    every resolved seed shares a component, the frontier empties, or
    the radius is spent. Bridges are accepted in the order (meeting
    depth, owners' seed order, source path, target path). The kept set
    is the bridge paths traced back to their seeds through the parent
    map, pruned by **undirected** degree-one stripping of non-seed
    nodes; `minimal=True` then repeatedly removes the lowest-path
    non-seed node that is not an articulation point of the undirected
    kept subgraph, re-stripping after each removal. No resolved seed
    answers an empty result; one resolved seed answers that node
    alone; seeds in different components each survive with no edges
    between them, and the answer says how many components remain.

## Consequences

- **Easier:** one shape on every engine, built from helpers the
  backend already has (`membership`, `chunked`, `liveness_filters`,
  `Visibility.narrow`, `admits`, the dialect join pin); the rights law
  is unchanged; the memory backend serves `graph` for free because it
  is `DatabaseStorage`; the public claim ADR 069 reserves can be made
  once the spec lands; the vocabulary explains itself in one sentence.
- **Harder:** round trips grow with the depth reached, so a deep
  unbounded walk pays one statement per level; the snapshot can move
  between hops; the walk's statement must carry the dialect join pin
  or SQLite plans a full scan (measured: 8.2 s for 1,000 seeds without
  it); every method's semantics change for anyone who read the
  archived specs.
- **Committed to:** spec 164 implements pins 1–10 against
  `DatabaseStorage`; `ops.py`'s `GRAPH_METHODS` becomes the four
  names and the verb-to-rung table gains `graph`; `Observation` gains `depth`; the capability pins in
  `tests/storage/database/test_reads.py` and `tests/storage/test_memory.py`
  flip; the README and `docs/reference/api.md` name `graph` once a
  backend answers it; conformance tests pin the hidden-node cut, the
  tombstone cut, seed chunking at 10,000, the cycle bomb's statement
  count, and the `a → x ← b` meeting; ADR 059's status line records
  the amendment on acceptance.
- **Not decided here** (pointers in `../open-questions.md`): the
  expanded permission ladder and the `list` rung the walk will
  traverse on (spec 165, its own research and ADR, **sequenced
  first** — Clay, 2026-10-14); the CTE acceleration's trigger; a Rust
  kernel for the post-walk phase of `meet`.

Evidence: `research/2026-10-14-graph-traversal-prior-art-and-experiments.md`
and its six studies under `research/studies/2026-10-14-graph-traversal/`
(the engine table, the field survey, the leak experiment, the 200-trial
meeting-subgraph comparison, the naming survey, the cycle bomb and the
10,000-seed statement counts); ADR 018 (one table, `fs` ordinary);
ADR 065 rule 1 (hidden rows absent from edge traversals); ADR 067 (one
predicate function); ADR 070 (the road); spec 067 (traversal only).
