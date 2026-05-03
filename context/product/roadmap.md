# Roadmap

**Status:** active — Plan 9 wave (2026-Q2 / Q3)
**Purpose:** Ordered direction — what's next, next-next, and later. Not a commitment.

The wave below is a coherent sequence: each story unlocks the
next. The sequencing is dependency-driven, not priority-ordered.
Earlier stories tend to be smaller and ship faster; later
stories are more ambitious and depend on the foundation.

```
       ┌──────────────────── 015 router calls public API ────────────────────┐
       │                                                                      │
       ▼                                                                      ▼
┌──────────────┐    ┌──────────────────┐    ┌─────────────────────────────────┐
│ 016 cleanup  │ →  │ 017 topology +   │ →  │ 018 bind   │ 019 unions+shadow  │
│ (foundation) │    │     /.mounts/    │    └─────────────────────────────────┘
└──────────────┘    └──────────────────┘                  │
                                                          ▼
                                          ┌────────────────────────────────────┐
                                          │ 020 remote backends (FSP transport)│
                                          └────────────────────────────────────┘
                                                          │
                            ┌─────────────────────────────┼────────────────────┐
                            ▼                             ▼                    ▼
                  ┌─────────────────┐    ┌────────────────────┐   ┌─────────────────────┐
                  │ 021 cross-svr   │    │ 022 hybrid search  │   │ 023 per-session     │
                  │     edges       │    │     across mounts  │   │     namespaces      │
                  └─────────────────┘    └────────────────────┘   └─────────────────────┘
                            │                                                 │
                            └────────────────┬────────────────────────────────┘
                                             ▼
                                ┌─────────────────────────────┐
                                │ 024 graph workspace sessions│
                                └─────────────────────────────┘
```

## Now (Wave 1 — namespace foundation)

- **015 routers-call-public-api-not-impl** — the architectural
  prerequisite for everything that follows. Router stops
  calling `_*_impl`; backends own their own session/transaction.
  Decouples engine lifecycle from mount membership for free.
- **016 namespace-primitives-cleanup** — small, independent,
  unblocks the rest. Allow nested mount paths; structured
  `MountError` reasons; bind-cycle guard at resolution time;
  push the "exclude mounted paths" filter into SQL.
- **017 topology-resource-and-mount-ctl** — `list_mounts()` and
  `/.mounts/` synthesized read tree, plus `/.mounts/ctl` writable
  surface. `add_mount` / `remove_mount` route through ctl. MCP
  `fs.mount.*` tools become one-line proxies.

## Next (Wave 2 — namespace ergonomics)

- **018 bind-aliases** — `bind(source, target, *, flags)`.
  Tiny `BindFS` forwarding filesystem. Aliases compose with
  unions and per-session namespaces.
- **019 union-mounts-and-shadow-resolution** — `MountFlag`
  activates beyond `REPL`: `BEFORE`, `AFTER`, `CREATE`. Union
  member walking. Critical: shadow filtering across union
  members so search/graph results match what the agent can
  actually read.

## Next (Wave 3 — distribution layer)

- **020 remote-backends-as-mount-targets** — `VFSTransport`
  protocol; `RemoteFS(VirtualFileSystem)`; `mcp+stdio://`,
  `mcp+http://`, `mcp+ws://` schemes. In-process backends keep
  their direct-method-call path (no JSON cost on the hot path).
  Capability negotiation at `initialize`. The wire format = the
  public method signatures.

## Later (Wave 4 — multi-backend correctness and federation)

- **021 cross-server-graph-edges** — `NodeId = (mount_uri,
  qid_path, version)`. Edge placement (source / target /
  registry). Federated traversal merging across mounts. The
  "knowledge graph that spans corpora" payoff.
- **022 hybrid-search-across-mounts** — per-backend score
  normalization, router-level merge with diversity,
  shadow-aware result filtering, capability-pruned fanout.
  Per-mount IDF preserved; vector model mismatch warned.
- **023 per-session-namespaces** — `VFSSession` with private
  mount overlay; `async with vfs.session() as s`; `fork()` for
  `rfork(RFNAMEG)` semantics; MCP-session ↔ VFS-session
  binding; the answer to "how do agents adapt to per-tenant
  topology?".

## Later (Wave 5 — agentic exploration)

- **024 graph-workspace-sessions** — clone-shaped graph
  workspaces. `/.graph/clone` allocates; `ctl` configures;
  `nodes` / `edges` / `ranking` view files render. Refinement
  in-place rather than re-shipping cumulative parameters.
  Session-scoped lifecycle from 023; TTL fallback.

## Explicitly not doing

- **Streams (kernel module pipelines).** Plan 9 itself regrets
  them; our async/await + `VFSResult` covers the same ground
  with less complexity. Networks paper §"Reflections" is
  explicit about this.
- **Per-arch binaries / `$cputype`.** Python doesn't have this
  problem.
- **Global cross-corpus BM25 IDF.** Requires shared corpus
  statistics across heterogeneous backends. Open research; not
  a practical deliverable. Per-corpus IDF + diversity rules at
  the router are the principled answer.
- **Cross-mount distributed transactions / 2PC.** Story 014
  established that vfs does not provide cross-mount atomicity
  across heterogeneous backends. That stance carries through
  the wave; per-mount atomicity is the ceiling.
- **In-protocol caching messages.** 9P has none and we follow
  suit. Caching is a layer (a `VirtualFileSystem` decorator),
  not a protocol feature. `Entry.version` + `content_hash` are
  the validation primitives.
- **A non-Python FSP server reference impl.** Out of scope for
  this wave. The protocol is JSON-RPC; polyglot impls are
  feasible but not on the critical path.
- **Persistent (cross-process) sessions.** Sessions are
  in-memory v1; agents reconnect with a fresh session. Wave 5
  may revisit if MCP gains durable session semantics.
- **A query optimizer for federated graph traversal.** v1
  fanout is "all eligible mounts in parallel." Optimization is
  its own future story once we have data on what the slow
  paths actually are.
- **Edge inference / auto-detected cross-corpus relationships.**
  Edges are written explicitly through `mkedge` (or the
  registry). Inference is a separate pipeline, not part of the
  namespace layer.

## Foundation already shipped

The wave above presupposes the following stories on `main`:

- **008** Plan 9 object model for metadata entries
- **010** Aligned primitives (VFSEntry / Candidate)
- **011** MSSQL native multi-hop traversal (single-backend
  graph baseline)
- **013** Database-agnostic code-trigram index
- **014** Auto-chunk and auto-index on write (the write
  pipeline; per-mount atomicity stance)

## Notes on sequencing

- 015 must land before any of 016–024. It is the architectural
  foundation; everything downstream assumes the router/backend
  boundary is clean.
- 020 (remote backends) can be paused after Wave 2 if the
  product needs to show value in single-process before going
  distributed. 021/022/023 each depend on 020 to deliver their
  full scope but each has a "single-process subset" if needed
  (cross-router-but-same-process edges; hybrid search across
  in-process mounts only; per-session overlays without remote
  mounts).
- 024 is the most speculative. The user's "results fit, no
  pagination" answer means workspaces are conversation-shaped,
  not stream-shaped. If usage doesn't bear that out, this
  story is the easiest one to drop or replace with a stateless
  query API.

## Source documents

- `docs/plan9-mount-namespace-recommendations.html` — the
  10-recommendation audit that seeded most of these stories
- `~/.claude/projects/-Users-claygendron-Git-Repos-grover/memory/`
  — Plan 9 study memos (`plan9_namespaces.md`, `plan9_overview.md`,
  `plan9_9p_protocol.md`, `plan9_security.md`, `plan9_networks.md`,
  `plan9_lib9p_patterns.md`, `plan9_to_vfs_guidance.md`)
- `context/learnings/2026-04-19-fsp-vfs-synthesis.md` — the
  pre-existing synthesis memo this wave operationalizes
- `context/stories/015-024/spec.md` — full per-story specs
