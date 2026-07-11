# 054 — `serve()` Defaults to a Locked Mount Topology at the MCP Boundary

- **Status:** draft — decision recorded ahead of the `serve()` story;
  binds whichever story lands the server.  Re-read against 056
  (2026-07-07): the locked surface is now the router's control plane
  (bind/unbind/add_mount/remove_mount/close), which 056 keeps off the
  wire structurally — the server wrapper exposes no admin tools, so
  this story's default is enforced by construction.
  Re-read 2026-07-10: the "Why" section's `allow_child_mounts` claim is
  stale — that flag no longer exists anywhere in `src/vfs` (it was
  deleted with 056's mount-table rework), so the client-half symmetry
  argument needs restating when `serve()` is specced.
- **Date:** 2026-07-07
- **Owner:** Clay Gendron
- **Kind:** policy decision (security default for the future MCP server)
- **Depends on:** 034 (MCP-native mounts — the client half this
  mirrors), 042/048 (mount-table lock — the invariants a remote caller
  must not reach), 039 (execute tier — the sibling "explicit rights at
  the boundary" decision)
- **Enables:** exposing a namespace over MCP without handing every
  wire caller root over its topology

## Intent

When `vfs.serve()` (or whatever shape the MCP server story takes)
exposes a `VirtualFileSystem` over the wire, **topology mutation is
not part of the served surface by default**. A wire caller gets the
verb surface — reads, searches, gated mutations, `run` — never
`add_mount` / `remove_mount`. Serving defaults the served node to
`allow_child_mounts=False` semantics, and an operator who wants remote
mount control must opt in explicitly.

## Why

- Mount topology is *namespace shape*, not namespace content. The op
  vocabulary already draws this line: `add_mount`/`remove_mount` are
  deliberately not in `ops.py` — they are host-process API, invisible
  to routing, gating, and the wire contract. Serving must not blur a
  line the vocabulary kept sharp.
- A caller who can mount can alias, shadow, or detach anything: mount
  a hostile filesystem under a trusted prefix, unmount a sibling
  mid-flight, or graft the namespace into loops the commit gate exists
  to prevent. That is administrative power, and MCP callers are
  agents, not administrators.
- The client half already made this call: a mount proxying a remote
  namespace is constructed `allow_child_mounts=False` so a *parent*
  cannot mutate the remote's table without opt-in (see
  `add_mount`'s docstring). This story is the same principle viewed
  from the server side — the two defaults should land as one symmetric
  rule: **nobody edits a namespace's topology from across a boundary
  unless the owner said so.**

## Scope

- `serve()` (when it lands) takes the node it serves and, by default:
  - exposes no mount-control tool/resource over MCP — no `add_mount`,
    no `remove_mount`, no writable topology resource (if a topology
    *view* ships à la old story 017, it is read-only);
  - flips the served node to `allow_child_mounts=False` for the serve
    lifetime, so even an indirect path to `add_mount` (a delegated add
    arriving through some future wire verb) is refused by the node
    itself, not just unrouted by the server.
- `remove_mount` today has no flag gating it at all —
  `allow_child_mounts` only guards adds. The serve default must cover
  both directions; if that means the flag grows a sibling or is
  generalized to a `topology_locked` notion, decide it here rather
  than overloading the add-only flag silently.
- Opt-in shape: an explicit `serve(..., allow_topology_mutation=True)`
  (name TBD) that also requires the node itself to allow child mounts
  — both the server and the node must agree before wire callers can
  reshape the tree.
- Out of scope: auth/identity for *who* may opt in (that is the
  share/ReBAC layer), and the serve() transport/tool-mapping design
  itself.

## Acceptance criteria

- A namespace served with defaults refuses topology mutation from any
  wire path: no mount tools advertised, and a smuggled/delegated
  `add_mount` reaching the served node raises exactly as
  `allow_child_mounts=False` does today; `remove_mount` from the wire
  is equally unreachable.
- The local host process's own handle: `[NEEDS CLARIFICATION]` does
  the lock apply only to wire-originated calls, or does serving freeze
  the node for the host too? Flipping the flag freezes both (simple,
  conservative — the user-suggested default); wire-only requires the
  server to withhold the tools while the host keeps its Python API.
  Decide before implementation; conservative default wins ties.
- Un-serving (server shutdown) restores the node's constructed
  `allow_child_mounts` value — serving must not permanently rewrite
  the node's identity.
- The opt-in is loud: enabling remote topology mutation appears in the
  server's advertised capabilities, never silently.
