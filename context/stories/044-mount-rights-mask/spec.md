# 044 — Mount-Time Rights Mask: Effective Rights Are an Intersection Along the Chain

- **Status:** draft — design decisions signed off 2026-07-03 (ownership
  rule, read-required masks, mask visibility); ready for plan.md
- **Date:** 2026-07-03
- **Owner:** Clay Gendron
- **Kind:** feature (permission model) + fix (a gate that is fictional for
  remote mounts)
- **Depends on:** 039 (`Rights` sets — the mask is a `Rights`; land 039
  first), 040 (one terminal gate — the mask check slots into
  `_gate_terminal`, not five sites)
- **Enables:** 034 (mounting an untrusted MCP catalog with "discoverable,
  not writable, not runnable" declared *by the mounter*), safe namespace
  composition generally — today whoever hands you a filesystem decides
  your policy

## Intent

Two problems, one design.

**A parent cannot impose policy on a mount.** `add_mount(fs, path)` takes
no permission argument: mount a writable filesystem and it is writable,
full stop. The only lever is the child's own `_permission_map` — which
belongs to whoever constructed the child, not to the namespace composing
it in. "Mount this read-write thing read-only here" — the single most
common containment need, and the obvious posture for an untrusted 034
catalog — is not expressible.

**The gate we do run at the boundary is fictional for remote mounts.**
When the terminal is a child, every chokepoint calls
`check_writable(child_fs, ...)` — reaching into the *child's* private
`_permission_map` from outside (`base2.py:565`, `:502-505`, `:628-634`,
`:797-799`; the reach itself is `permissions.py:279-285`). For a local
child this is pure redundancy: the child's own public method re-runs the
identical check on the identical map one frame later. For the 034
end-state — a child that proxies a remote namespace — the child's local
map is a placebo; the real policy lives on the remote, and no parent-side
inspection can see it. The current code only means something because
every child happens to be in-process.

The design that fixes both: **every node gates with what it owns.** A
node's own permission map governs paths it stores; a **rights mask on
each mount edge** governs what crosses that edge. Effective rights at a
path are the intersection of the masks along the mount chain with the
terminal's own resolved rights — and no node ever needs to see another
node's map, because each hop enforces its own mask as dispatch recurses
through public methods. The composition falls out of the existing
recursion for free.

## Why

- **This is the union-mount lineage.** Plan 9 binds carry flags the
  *binder* chooses; POSIX mounts take `ro`. The mounter states policy at
  the edge because the mounter is the one making a foreign tree reachable
  — the tree's own opinion of itself cannot be the last word.
- **Intersection is the only sound composition.** A mask can only remove
  rights, never add them: a read-only child under a writable mask stays
  read-only (the child still refuses at its own gate); a writable child
  under a read-only mask is read-only *here* without touching the child —
  the same instance's policy elsewhere is unaffected because the mask
  lives on the edge, not the node.
- **It makes local and remote uniform.** After this story the router
  never consults a child's map — masks are the parent's own state, and
  the terminal (local impl or remote server) is authoritative for its own
  policy. A remote mount then behaves *identically* to a local one at the
  permission layer, which is the 034 wire contract working as designed
  ("values in, `Result` out" — policy included).
- **The docstring already warns about half of this.** The Limitations
  section of `permissions.py` (lines 58-75) documents that two instances
  sharing an engine dodge the per-instance map. Edge masks don't fix
  shared engines, but they give the composing namespace its own
  enforcement point that no instance-swap can bypass.

## Design

### D1 — the ownership rule (signed off 2026-07-03)

> A node enforces (a) its own `PermissionMap` when it is the terminal,
> and (b) the mask on each of its own mount edges when routing across
> one. No node reads another node's policy state, ever.

Consequence: the parent-side `check_writable(child_fs, ...)` calls are
**deleted**, not relocated. Denial for a path inside a child comes from
the child (or from this node's edge mask) — one authority per fact.

Trade-off, accepted with the sign-off: for in-process children, a denial
that today fails fast at the parent's chokepoint now surfaces one
call-frame later, from inside the child, and the *message* prose names
the child-local path. This is already the router's stated philosophy —
mkedge delegates exactly this way today ("the child re-derives … and
gates it against its own permission map", `base2.py:1193-1195`) — and
040's D2 makes the structured `error.path` router-side everywhere, which
is the field consumers are supposed to read. Message-prose rebasing was
considered and rejected: rewriting prose is how messages start lying.
Accepting local coordinates in child-originated prose is the cost of a
model that is truthful for remote mounts.

### D2 — the mask on the mount table

```python
async def add_mount(
    self,
    filesystem: VirtualFileSystem,
    path: str | None = None,
    *,
    rights: Rights | str = "read_write",   # coerce_rights; default = full, today's behavior
) -> None: ...
```

The table becomes `dict[Path, MountEntry]` where `MountEntry` carries
`(filesystem, mask)`. Delegated adds pass `rights` through unchanged —
the mask lands on the edge that *owns* the mount, so a nested delegation
chain holds each delegator's mask on its own hop. Default is the full
rights set: every existing construction keeps its behavior, and the
diff at existing call sites is zero.

No per-path granularity on the mask (that is what the terminal's own
`PermissionMap` is for); a mask is one `Rights` for the whole edge.
Carve-outs across an edge boundary compose naturally: mask says what may
cross at all, the terminal's map refines within.

### D3 — enforcement inside the one gate

In `_gate_terminal` (040), after capability, before the terminal-local
permission check:

- Resolve which mount edge (if any) the dispatch crosses — `_resolve_
  terminal` already walks the chain; it accumulates the **intersection
  of masks** along the walk (this node's own hops only; deeper hops are
  enforced by deeper nodes as dispatch recurses).
- If the op's `required_right` (039) is absent from the accumulated
  mask: denied at this node, with the router-side path, `kind=read_only`
  for write, `permission_denied` for execute — same kind mapping as 039.
- When the terminal is `self`: no edge crossed, only the local map runs
  (unchanged).

Fan-out honors masks the same way: an unscoped `glob` still reaches a
read-masked mount — reads pass every mask, because **every mask includes
`read`, by construction (decided 2026-07-03)**: `add_mount` rejects a
mask without it. A mounted-but-unreadable subtree is a foot-gun (an
invisible mount that still occupies paths); the staging/quarantine need
is served by `read`-only masks and 039's `no_execute()`, not by dark
mounts.

### D4 — the mask is visible metadata (decided 2026-07-03)

Policy is readable, not probe-discovered: `stat`/`ls` on a mount point
report the edge's rights — the same no-probe courtesy `capabilities()`
extends for ops, applied to policy. An agent deciding whether to attempt
a write reads the answer instead of collecting a denial. Mechanically
this rides on 041's spine rows (mount points become visible observations
there); whether rights surface as a dedicated `Observation` column or in
`description` is 041-integration detail decided in plan.md — the
decision here is only that they surface.

### D5 — what happens to `check_writable`'s `fs` parameter

With parent-side child gating gone, `check_writable`/`check_allowed`
(039) is only ever called with `fs=self` — the friend-module reach into
`fs._permission_map` (`permissions.py:279`) disappears as a side effect,
which completes 039's D4 cleanup for free.

## Out of scope

- Per-user rights on an edge — ReBAC/share layer, per the existing
  doctrine.
- Message-prose rebasing across mounts (D1's noted trade-off; revisit
  only if agent transcripts show the local-coordinate prose misleading
  in practice).
- Shared-engine isolation (the documented Limitation stands — masks add
  an enforcement point, they do not virtualize storage).
- Changing mkedge's delegation shape — it already conforms to D1.

## Test plan

1. **Containment:** writable child mounted `rights="read"` — every
   mutating verb through the parent denies with `read_only` and the
   router-side path; the same child instance mutated *directly* (its own
   public API) still writes. The mask is on the edge, not the node.
2. **Intersection, not override:** read-only child under a full mask —
   still denies (child's own gate, child-originated error). Full child
   under full mask — writes. The 2×2 pins intersection semantics.
3. **Execution mask (with 039):** catalog mounted
   `rights=frozenset({"read"})` — `ls`/`read` succeed, `run` denies
   `permission_denied` before any dispatch (no-probe holds for policy,
   not just capability).
4. **Chain intersection:** grandparent masks `read`, parent masks
   `read_write` — a write through the grandparent denies at the
   grandparent's edge; through the parent, succeeds. Each node enforces
   its own hop.
5. **No foreign reads (the D1 pin):** a child whose `_permission_map`
   raises on access (guard object) routes reads/writes correctly through
   the parent — proving the router never touches it. This is the
   regression test that keeps the fictional gate from creeping back.
6. **No dark mounts:** `add_mount` with a mask lacking `read` raises at
   construction, with a message naming the rule.
7. **Visible policy:** `stat` on a mount point reports the edge's rights
   (shape per 041 integration); the reported value reflects the mask,
   not the child's internal map.
8. **Default is identity:** the full existing suite passes with zero
   edits except sites that asserted parent-side denial messages.

## Open questions

None — the three decision points (ownership rule D1, read-required masks
D3, mask visibility D4) were signed off 2026-07-03 and are folded into
the design above.
