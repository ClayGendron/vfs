# 024 — Graph Workspace Sessions (clone + ctl + view)

- **Status:** draft
- **Date:** 2026-05-02
- **Owner:** Clay Gendron
- **Kind:** feature · graph · stateful sessions
- **Depends on:** 015, 017, 020, 021, 023
- **Enables:** agentic graph exploration through dialogue;
  refinement queries without re-shipping full parameter sets

## Intent

Make graph queries **dialogue-shaped** rather than one-shot.
Today the only way for an agent to refine a graph query (extend
scope, change algorithm, swap edge filter, drop irrelevant
nodes) is to send a fresh single-request query with the full
cumulative parameters every time.

This story introduces a Plan 9-shaped graph **workspace**: a
short-lived server-side state, allocated via the clone idiom,
configured by writes to ctl files, read by reads on view files,
released on close.

```text
open  /.graph/clone                                → "0042"
write /.graph/0042/scope     "/tenants/acme/code/auth.py depth=2"
write /.graph/0042/scope     "+ /tenants/acme/code/db.py"   # extend
write /.graph/0042/filter    "edge.kind=imports"
read  /.graph/0042/nodes                            → current view
write /.graph/0042/algorithm "pagerank damping=0.85"
read  /.graph/0042/ranking                          → ranked view
write /.graph/0042/algorithm "betweenness"
read  /.graph/0042/ranking                          → re-ranked, same scope
close                                              # clunk releases
```

This is more powerful than one-shot but introduces server-side
state. The story commits to the smallest model that supports
the user's real refinement pattern.

## Why

- **The user's stated pattern (rec/03 conversation):** "sessions
  are a good idea, will want to search and follow up on a query."
  Single round-trip would force them to either re-send the full
  cumulative state or live with stateless queries that can't
  refine.
- **Pagination (the other forcing function) is not needed.** The
  user said "results fit." So workspaces are not a paging
  cursor — they're a **conversation cursor**. The held state is
  the cumulative query, not a slice.
- **The session has a natural cleanup signal.** Per-session
  namespaces (story 023) already bind state to the MCP session.
  Workspaces piggy-back on that lifecycle, so the "who
  cleans up" question has a clean answer.
- **Plan 9's pattern is the canonical one.** `/net/tcp/clone`
  and `/proc/N/...` together cover both halves: clone for
  allocation, view-files for reading current state, ctl-files
  for narrowing.

## Scope

### In

1. **`/.graph/` synthesized resource on the router.**
   Read-only top-level dir. `/.graph/clone` is the one writable
   entry there.

2. **Clone allocation.**
   Open `/.graph/clone` returns a fid; the first read on it
   yields `"NNNN"` (a numeric workspace id). Construct the
   workspace dir path as `/.graph/NNNN/`. Closing all fids
   into the workspace releases it; explicit
   `write("/.graph/NNNN/ctl", "close")` does the same eagerly.

3. **Workspace files.**
   Each workspace is a directory with these files:
   ```
   /.graph/NNNN/
     ctl          # writable; verbs: scope, filter, algorithm, reset, close
     scope        # readable; the current scope spec
     filter       # readable; the current edge/node filters
     algorithm    # readable; current algorithm + params
     nodes        # readable; current node set rendered as JSON Candidates
     edges        # readable; current edge set
     ranking      # readable; ranking under the current algorithm (if set)
     subgraph     # readable; full subgraph projection (nodes + edges)
     status       # readable; "ok | computing | error: ..."
   ```

4. **Ctl verb table.**
   ```text
   scope     <path-spec>          # set scope (replaces previous)
   scope     + <path-spec>        # extend scope
   scope     - <path-spec>        # subtract scope
   filter    <expr>               # set filter (replaces); empty resets
   filter    + <expr>             # add filter clause
   algorithm <name> [params...]   # set algorithm + params
   reset                          # clear all configuration
   close                          # release this workspace
   ```
   Same `Cmdtab` shape as `/.mounts/ctl` from story 017.
   `respondcmderror`-style echo of bad input.

5. **Lazy materialization.**
   Reading `nodes` / `edges` / `ranking` triggers computation.
   Cached until configuration changes — re-reading after no ctl
   write is free. Status is `computing` while in flight; reader
   blocks until ready.

6. **Bound to per-session namespace (story 023).**
   Each session has its own `/.graph/`. Workspaces opened in one
   session are invisible to another. Lifetime is tied to the
   session: when the session closes, its workspaces are
   released.

7. **Workspace TTL fallback.**
   Even within a session, an idle workspace times out after 10
   minutes of no ctl writes and no reads. Configurable per
   `VFSClient`. Re-clone is cheap.

8. **Federated computation across mounts (story 021 hookup).**
   When the scope spans multiple mounts, the workspace's node
   resolution and edge fetching uses the federated traversal
   from 021. Algorithm computation happens at the router on
   the assembled subgraph; no per-mount algorithm dispatch
   (because algorithms are subgraph-scoped, and the router is
   the only place that holds the subgraph).

9. **Algorithms.**
   v1 ships:
   - `neighborhood` (default: scope itself)
   - `successors`, `predecessors`, `ancestors`, `descendants`
   - `pagerank`
   - `betweenness_centrality`, `closeness_centrality`,
     `degree_centrality`
   - `meeting_subgraph`, `min_meeting_subgraph`

   These map onto the existing single-backend algorithms but run
   against the workspace's federated subgraph.

10. **MCP-side helper.**
    A small MCP tool `vfs.graph.workspace` that wraps the clone
    + ctl + read pattern in one call shape, for agents that
    want a one-shot interface without losing the refinement
    capability:
    ```python
    tools/call vfs.graph.workspace {
       scope: "/code/auth.py depth=2",
       filter: "edge.kind=imports",
       algorithm: "pagerank damping=0.85"
    }
    → returns ranking + workspace_id
    ```
    The agent can refine by calling again with the same
    `workspace_id` and incremental edits. Underneath, this
    boils down to the file-shape ops.

### Out

- Persisting workspaces across MCP sessions. v1 is in-memory
  and tied to session lifetime.
- Cross-session workspace sharing. A workspace is private.
- Streaming partial results. v1 fully materializes; the
  algorithms aren't slow enough to need streaming.
- Algorithm plug-ins from outside the codebase. v1 ships the
  fixed list above.
- A "diff" file showing what changed between two algorithm
  configurations. Useful but secondary.

## Acceptance Criteria

1. **Clone allocates.** Open `/.graph/clone` and the fid yields
   a fresh numeric workspace id, distinct across calls.

2. **Ctl scope set + read.** Write `scope /a/b depth=2` to ctl;
   read `scope` returns the same expression normalized.

3. **Read nodes triggers materialization.** A workspace with
   no algorithm configured returns the scope's nodes via
   `nodes` and edges via `edges`.

4. **Algorithm change re-ranks without re-scoping.** Same scope,
   pagerank → betweenness yields different rankings; no
   re-fetch of nodes/edges (cached).

5. **Scope extension is incremental.** `scope + /c/d` adds
   without dropping previous scope; `scope - /a/b` subtracts.

6. **Federated scope works.** A scope spanning two mounts
   populates the workspace from both; algorithms run on the
   merged subgraph.

7. **Close releases.** `close` ctl write or last-fid-clunk
   removes the workspace from `/.graph/`. Subsequent
   reads of the path return `NotFoundError`.

8. **TTL eviction.** A workspace with no activity for 10
   minutes is removed; documented.

9. **Per-session isolation.** Two sessions cloning workspaces
   independently see only their own.

10. **Status during compute.** A long algorithm reports
    `computing` in `status` until ready; readers of `ranking`
    wait until `ok`.

11. **Bad ctl echoes back.** `algorithm frobenius` returns
    `unknown algorithm: "frobenius"` with a list of valid
    names.

12. **MCP wrapper tool works.** `tools/call vfs.graph.workspace`
    returns ranking + workspace id; subsequent calls with the
    same id refine.

## Risks

- **Server-side state cost.** N concurrent agents × M
  workspaces each × subgraph size. Mitigation: TTL eviction,
  cap on concurrent workspaces per session (default 10),
  workspaces are subgraphs not full graphs.
- **Algorithm cost.** Centrality algorithms on large subgraphs
  can be slow. Mitigation: scope-driven materialization keeps
  subgraphs small by construction; document expected complexity
  per algorithm.
- **Correctness across federated edges.** A pagerank computed on
  a federated subgraph treats every node as equal; missing
  edges to mounts not in scope are absent from the
  computation. Documented; agents can `scope +` to bring more
  in.
- **Race between reads and ctl writes.** A read while a write
  is in flight sees `computing`; reader blocks. Standard
  workspace lock.
- **Workspace leaks.** Untracked fids that linger past the TTL.
  Mitigation: TTL is the safety net; docs encourage explicit
  close.

## Open Questions

1. **Should `scope` accept queries (e.g., `scope ?
   kind=file ext=py`)?** Default: yes, eventually. v1 accepts
   path specs only; query support is a follow-up.

2. **Should rankings be sortable / paginated through the file
   interface?** Default: no — results fit per the user's
   answer. Reading `ranking` returns the full ordered list.

3. **Should there be a `subgraph.dot` view file** that emits
   Graphviz output? Default: low-priority but cheap to add.
   Stub it if requested.

4. **Should TTL be visible to the agent?** Default: yes —
   `read("/.graph/NNNN/status")` reports remaining TTL when
   idle.

5. **Do workspaces survive `bind` topology changes?** Default:
   yes — node identity is `NodeId` (story 021), which is mount-
   uri based and unaffected by bind paths.

## References

- Plan 9 networks paper — the clone idiom, `/net/tcp/N/...`
- Plan 9 names paper — `/proc/N/...` view files
- `lib9p/parse.c` — `Cmdtab` shape for ctl verb dispatch
- Story 011 — MSSQL multi-hop traversal (single-backend)
- Story 021 — federated traversal infrastructure this builds on
- Story 023 — per-session namespaces (workspace lifecycle root)
- `docs/plan9-mount-namespace-recommendations.html` — Rec 04
  (textual ctl) and the discussion thread on session-shaped
  graph state
