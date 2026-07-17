# 011. The No-Union Routing Rule: Total Producers, Partial Refusal Checks

- **Status:** accepted
- **Date:** 2026-07-16
- **Deciders:** Clay Gendron
- **Decided by:** human (research review 2026-07-10, three
  primary-source lenses, no fatal objections; fusion fork declined with
  owner same day)

## Context

The router's three routing methods had grown past the point where their
phases read as phases, and the file mixed two return conventions: the
better half returned products (`ResolvedPath`) or refusal checks
(`_gate_entry` → `Result | None`), while newer code returned
`Result | Token` and a decomposition sketch proposed `Path | Result`
helpers — the two-headed shape the cleanup would have reintroduced.

Story 069's review ran three namei lenses against fetched primary
source, and all three converged against the union:

- **Linux (v6.12 `namei.c`/`pnode.c`):** `ERR_PTR` is C economics —
  one register, no product types — and still breeds a known bug class
  (forgotten `IS_ERR`). Where semantics beat registers, Linux itself
  separates check from produce: the `may_*` family returns 0-or-errno
  (≅ `Result | None`), kept apart from the dentry pipeline;
  `vfs_rmdir` sequences `may_delete_dentry` (entry policy,
  `fs/namei.c`) then the busy check (`fs/namespace.c`) at the call
  site — two named checks, two files, never fused.
- **Plan 9 (4th-edition `chan.c`/`devmnt.c`):** never adopted the union
  even in C — `walk()` returns status plus out-params, `waserror()` is
  confined behind seams, and the wire carries only Rerror values and
  graded Rwalk (partial progress is success-with-less; only zero
  progress is loud).
- **V7 → 4.4BSD:** a fifteen-year migration off overloaded returns. V7
  `namei` returned `inode | NULL` where NULL meant three things
  disambiguated by five globals; 4.3BSD ran two error channels at once
  (`ni_error`/`u.u_error`); 4.4BSD ended it — the refusal is the sole
  `int` return, values live in the `nameidata` product.

The rule adopts what all three systems converged on and discards only
what C forced.

## Options considered

- **Union-returning helpers** (`Path | Result`, `Plan | Result`) —
  rejected: violates the rule and defeats `ty` narrowing at every call
  site.
- **An async context manager for the hop budget** — rejected: cannot
  early-return the caller's refusal, so every site keeps the check and
  pays an indent level for it.
- **Fusing the busy guard and the entry gate** (`_refuse_target`) —
  declined with owner: the halves co-fire at only one call site, their
  subjects differ (mount table vs entry policy), and the verified Linux
  precedent keeps exactly that split, sequenced by the caller.
- **Callback-parameterized batch/dispatch engines** — declined:
  indirection of the kind the file refuses; every abstraction in
  `base.py` is a named contract, not a hook.

## Decision

In the router, **a function returns one type, and the only union is
`X | None`.** Value-producing steps are *total* — they always return
their value. Policy checks are *partial* — they return `Result | None`,
where the `Result` is a classified refusal and `None` means proceed.
**No function both produces a value and refuses.** A step that needs
both returns a product carrying its own refusal field — `_FanoutPlan`
and `_HopGrant` (`src/vfs/base.py:178,167`), each field total or
`X | None`, the `refusal` field the *sole* failure carrier.

Binding constraints, adopted as review amendments:

- **Plans are output-only, forever.** `_FanoutPlan` never grows input
  fields — BSD's `nameidata` accreted I/O state that 4.4 had to cut
  back out — and a refusal never rides beside a returned value as a
  second channel (4.3BSD's dual error channels are the recorded
  failure mode).
- **The rule's scope is router-side table-fact checks only.** Backends
  check-and-act in one call by design (`mkdir` has no site probe)
  because a separated check would race. This ADR must never be cited
  to split a backend into a check-then-produce pair.
- **One-flag budget on fused checks.** V7's `flag 0/1/2` and 4.3BSD's
  `LOCKPARENT`/`NOCACHE`/`FOLLOW` soup show flag accretion is how
  fused checks decay.
- **The split rides on I/O-free resolution.** The total/refusal seams
  exist because `_resolve_terminal` is a synchronous table match. Plan
  9 shows what happens otherwise: when resolution requires storage I/O
  (`walk()` is device I/O with per-step mount checks), resolve and
  dispatch must interleave and these seams collapse. If symlink-alikes
  or per-component gates ever arrive, this shape is **re-litigated,
  not patched**.

## Consequences

- **Easier:** `ty` narrows every call site; the file's subtlest
  invariants — subsumption pinning and the capability-skip rule —
  became directly unit-testable (`_merge_fanout` is a pure static
  method taking hand-built `Result`s; `_classify_fanout_scopes` is
  synchronous with zero awaits).
- **Harder:** product types and refusal fields are real ceremony next
  to one clever union return; check *order* becomes a suite-pinned
  contract (`invalid` beats `busy` on a batch pairing a bind-site src
  with an invalid dest), because sequencing at call sites is what
  keeps checks separate.
- **Committed to:** no function in `base.py` returns a union other
  than `X | None` (acceptance-pinned); the busy guard and entry gate
  stay separate named checks; the re-litigation trigger above is the
  rule's honest boundary, recorded so I/O-bearing resolution is a
  redesign, not an erosion.

Executed by story 069
(`context/specs/archive/069-routing-decomposition/`, landing commit
`22a3f33`); the review's full precedent table lives in that spec.
