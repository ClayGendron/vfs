# 022. The serve() Topology Lock Binds the Wire, Not the Host

- **Status:** proposed (2026-07-22) — drafted from an evidence review
  commissioned in session; **awaiting Clay's ratification.** Note that
  it decides *against* the lean recorded in spec 054.
- **Date:** 2026-07-22
- **Deciders:** Clay Gendron
- **Decided by:** pending — drafted by Claude from first-hand prior-art
  research.
- **Supersedes:** spec 054's `allow_child_mounts` mechanism, which is
  not merely stale but unimplementable as written — the identifier has
  zero occurrences in live `src/` (verified 2026-07-22).

## Context

Spec 054 decided that `serve()` locks mount topology, then went stale
when specs 056 and 068 reshaped mount administration. Two things needed
re-deriving: what enforces the lock now, and — the fork 054 left open —
whether the lock also freezes the **host process's own handle**, or only
the view reachable over the wire. 054's recorded lean was "conservative
default wins ties — flipping the flag freezes both."

The prior art is not a tie, so the tie-breaker does not apply.

## Decisions

### 1. Topology mutation is absent from the served surface by construction

The MCP server registers verb tools explicitly; nothing unregistered
exists on the wire. An `add_mount` tool that is never registered is
structurally unreachable, not merely denied.

**Grounding.** Tools reach the wire only via explicit registration —
`fastmcp/fastmcp_slim/fastmcp/server/server.py:1634` (`def add_tool`),
decorators at `:1649-1690`. There is no ambient export. This is what
spec 054's own 2026-07-07 re-read already observed about 056's shape.

### 2. A served node additionally refuses topology mutation via any indirect wire path, for the serve lifetime

Construction handles the direct surface; this covers anything that could
reach topology through a registered verb. The refusal is serve-lifetime
session state, not persistent node state, and lifts on un-serving —
054's un-serving criterion stands.

### 3. The lock binds wire-originated calls only; the host handle keeps mount admin

This resolves 054's open fork **against** its recorded lean.

**Grounding — two independent lineages agree, and both are precise
about *whose* rights are curtailed.** Plan 9's `RFNOMNT` is the direct
precedent for "serving locks mounts": `sys/man/2/fork:71-74` — "If set,
subsequent mounts into the new name space and dereferencing of pathnames
starting with # are disallowed." Enforcement is a one-way bit set on the
**newly derived** process group (`sys/src/9/port/sysproc.c:142-143`:
`if(flag & RFNOMNT) p->pgrp->noattach = 1;`), checked at attach time
(`sys/src/9/port/chan.c:1361,1375-1377` — "noattach is sandboxing"). The
parent's namespace rights are untouched.

Linux says the same with locked mounts: mounts propagated into a
less-privileged mount namespace are stamped `MNT_LOCKED` and the stamp
is inherited by the clone, never applied to the owner
(`fs/namespace.c:2208-2209`:
`if (src_mnt->mnt.mnt_flags & MNT_LOCKED) dst_mnt->mnt.mnt_flags |= MNT_LOCKED;`;
umount of a locked mount refused at `:1941`). The privileged owner
retains full control of the original.

**The lock travels with the untrusted view, not with the resource.**

**Consequence.** The host may legitimately reshape topology under a live
server. That is exactly what Linux permits the owning namespace and what
a Plan 9 parent retains, and vfs already classifies mount races as
ordinary results — ADR 009 commits to a per-process mount lock with
shared-storage mount admin unsynchronized. Freezing the host too would
buy little: the host is in-process and can stop the server anyway.

### 4. No persistent `topology_locked` state

The lock is session state for the serve lifetime. The opt-in
(`allow_topology_mutation=True`) stays loud in advertised capabilities
as 054 drafted it.

## Options considered

- **Freeze both host and wire** (054's recorded lean). Rejected: both
  precedents curtail the derived view specifically, and the host can
  stop the server regardless, so the freeze costs flexibility for
  little safety.
- **Re-derive `allow_child_mounts` against post-068 mount admin.**
  Rejected: the identifier does not exist in live code; the mechanism
  should be deleted from 054, not revived.
- **Defer entirely to the serve() spec.** Rejected for the policy core
  — the fork has been open since 2026-07-10 and the evidence is now in
  hand. The *mechanics* still belong to the serve() spec.

## Consequences

- Spec 054's mechanism language should be deleted; its policy is
  restated here.
- The serve() spec (056 Pass C is the named vehicle) implements the
  mechanics against this policy.
- **Sequencing note:** 054 defers "who may opt in" to the auth layer, so
  the serve() spec should land after spec 070 lets the opt-in be
  principal-gated rather than a bare boolean.
- **Re-derive if** serve() ever gains a multi-process host story (host
  handle and server in separate processes over shared storage) — "the
  host keeps admin" stops being enforceable and the conservative freeze
  becomes honest again. Likewise if spec 070 produces a principal-gated
  admin surface, this may become a rights question rather than a
  topology flag.
