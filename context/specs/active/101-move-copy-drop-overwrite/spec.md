# 101 — Move/copy drop `overwrite`: no agent surface destroys, ever

- **Status: draft 2026-08-14** — born from the open-questions entry
  "Move/copy overwrite destroys the occupant permanently — the last
  agent-reachable destruction", resolved by Clay in session
  2026-08-14: **the flag is removed entirely**, not softened. No open
  forks.
- **Date:** 2026-08-14
- **Owner:** Clay Gendron
- **Kind:** verb-surface contraction — a signature change on `move`
  and `copy` (router, protocol, backend), the deletion of both
  overwrite fences, and the closure of ADR 027's one remaining
  exception.
- **Depends on:** ADR 027 (delete never destroys; sweep is the only
  destroyer — this spec makes its contract sentence unconditional),
  the 081–083 trash arc (the displacement path callers use instead).
- **Relates to:** specs 084/085 (where delete lost `permanent=True` —
  the same law arriving at the transfer verbs), spec 086 (the purge
  machinery the move fence invokes today).

## Intent

After ADR 027, `move`/`copy` with `overwrite=True` (the **default**)
is the only way an agent can permanently destroy data: the move arm
hard-purges the destination occupant (`_execute_move` →
`_purge_subtree`) and the copy arm deletes the occupant's content
row. The refusal ladder bounds the blast radius (only a file or an
*empty* directory can be overwritten), but a file's content is
exactly what the trash arc exists to protect.

The resolution refuses to guard an overwrite arm at all: **no agent
surface may permanently destroy data, so the surface itself goes.**
An occupied destination always refuses `exists`; a caller that means
to displace an occupant does it honestly in two calls — `delete` the
occupant (which trashes it, restorably) and re-issue the transfer.
POSIX rename-unlink parity is knowingly declined, the same divergence
`delete` already made when it lost `permanent=True`.

## Shape

- **§1 Router.** `overwrite` leaves the `move`/`copy` signatures and
  their `ParamSpec` tables (`params.py`); `_route_pairs`/
  `_route_two_path` stop threading it. An unknown-parameter caller
  refuses at the gate like any other stale kwarg.
- **§2 Seam.** `SupportsMutation.move`/`.copy` lose the parameter;
  the backend methods and `topology.py`'s `_execute_move`/
  `_execute_copy` drop their fences — the occupant check refuses
  `exists` unconditionally. The purge call disappears from the move
  arm; `_purge_subtree`'s remaining callers are audited (sweep keeps
  it — sweep is the destroyer by design).
- **§3 Restore audit (same law).** `restore` keeps its own
  `overwrite` (default `False`); this spec audits its occupant arm:
  if a `restore(overwrite=True)` onto an occupied original site
  destroys the occupant rather than trashing it, the arm gets the
  same treatment — the flag goes and the site refuses `exists` until
  the caller deletes the occupant. If the arm already trashes, it is
  documented and pinned. (`write`'s `overwrite` is out of scope:
  content replacement is versioned by the per-entry revision arc,
  never destruction.)
- **§4 Docs.** ADR 027's contract sentence loses its exception (the
  amendment recorded in place); the open-questions entry links here.

## Verification obligations

- Conformance rows flip: `move`/`copy` onto an occupied destination
  refuse `exists` on every backend and engine leg (the existing
  `overwrite=False` rows become the only behavior; the
  `overwrite=True` rows are deleted, not skipped).
- A displacement round-trip row: delete occupant → move onto the
  freed address → restore the occupant fails `exists` at its
  original site (the incoming row holds it) — pinning that the trash
  arc, not an overwrite arm, owns displacement.
- A grep over `src/` proves no permanent content deletion is
  reachable from any agent verb (sweep and trash-bucket reclamation
  are the only `DELETE`s against content rows outside guard misses).
- Suite, `ruff`/`ty`, and the four Docker legs green.

## Touch points

- `src/vfs/base.py` (`move`, `copy`, `_route_pairs`,
  `_route_two_path`), `src/vfs/params.py` (two `ParamSpec` rows;
  restore's row per §3).
- `src/vfs/storage/protocol.py` (`SupportsMutation.move`/`.copy`).
- `src/vfs/storage/backends/database/backend.py`, `topology.py`
  (both fences, the move-arm purge).
- `tests/support/storage_contract.py` (the overwrite rows),
  `tests/base/`, `tests/storage/`.

## Slices

- **A** — seam + backend: fences out, occupant refusals
  unconditional, conformance rows flipped.
- **B** — router + params + restore audit (§3) + ADR 027 amendment +
  docs true-up.

## Open questions

None — the decision is recorded in `../../open-questions-archive.md`
(resolved 2026-08-14); §3's audit outcome is a finding to record, not
a fork.
