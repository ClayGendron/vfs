# 101 — Move/copy drop `overwrite`: no agent surface destroys, ever

- **Status: landed 2026-08-25.**
  Both slices in one landing: ``overwrite`` leaves ``move``, ``copy``,
  **and ``restore``** — §3's audit found restore's occupant arm purged
  through the same ``_execute_move`` fence, so it took the same law
  (a finding, as the spec asked, not a fork). Router signatures and
  ``ParamSpec`` rows, the seam, the backend, and both ``topology.py``
  arms drop the flag; an occupied destination refuses ``exists``
  unconditionally, which deletes the occupant-kind and emptiness
  sub-ladder, the move fence and its purge, and copy's in-place
  clobber. One consequence the spec did not foresee: a move onto an
  ancestor is always an occupied destination (ancestors exist by
  definition), so the ancestor direction of the cycle check became
  unreachable and was deleted — the ladder is now exists → into-itself
  cycle → byte overflow. Conformance rows flipped (no ``overwrite=True``
  row survives as a skip), the displacement round-trip row landed,
  and the grep proved sweep's ``_purge_subtree`` / orphan reclaim are
  the only content-row DELETEs outside a write's own body replacement.
  ADR 027 amended in place; the open-questions-archive entry closed.
  Details in the landing note below.
- **Status (original): draft 2026-08-14** — born from the open-questions entry
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

## Landing note (2026-08-25)

- **§3 audit outcome: restore's flag goes too.** `restore_rows` with
  `overwrite=True` handed the occupant to `_execute_move`, whose
  fence-and-purge arm hard-deleted it — the same destruction, one
  verb over. Three verbs now share one sentence: an occupied site
  refuses `exists`; displacement is `delete` (which trashes) then the
  verb again. `restore` by exact trash-side path is how a caller
  reaches a specific trashed row once the newest one is the squatter
  (pinned in `test_trash.py`).
- **The ancestor cycle branch died.** `src.startswith(dest + "/")`
  could only fire when `dest` was an ancestor of `src` — a row that
  always exists — and the exists check now precedes it, so the branch
  was unreachable (the 100 % coverage gate would have said so). The
  order is the Linux one: `do_renameat2`'s `RENAME_NOREPLACE` EEXIST
  precedes `vfs_rename`'s trap check. Two conformance rows re-shaped:
  into-itself with an unoccupied destination stays `invalid`; onto an
  occupied descendant and onto an ancestor are `exists`.
- **Rows deleted, not skipped:** the two overwrite-fence race rows in
  `test_races.py` (the fence no longer exists; the class is now
  `TestTransferCollision` around the surviving copy-collision row),
  `test_overwrite_fence_redrives_when_the_occupant_was_bumped` and the
  fence probe in the shared-executor row of `test_coherence.py`, and
  the two `wrong_kind`-on-occupant rows that the exists-before-kind
  row already covers.
- **The DELETE grep.** Content-row DELETEs in `src/`: sweep's
  `_purge_subtree` and `_reclaim_orphan_content` (developer plane),
  and the write path's own body replacement (a content write, in
  scope for the revision arc, not this spec). Chunk-row DELETEs are
  derived-index maintenance. No agent-reachable verb destroys.
- **Observation status:** transfers and restores now only report
  `created` (or `unchanged` for rename-to-self); `_PendingTransfer`'s
  status type narrowed to match.
- **Engine-leg finding:** `test_copy_child_collision_redrives_to_the_
  honest_refusal` (real engines only) pre-created `/dest` and expected
  `not_empty` after the redrive — under the new law the copy refused
  `exists` before the seam ever fired. Re-shaped to keep its intent:
  `/dest` absent, the rival mints it and a child with `parents=True`
  mid-window, the unique violation redrives, and the fresh ladder
  refuses `exists` at the root the rival took, with no driver text
  leaking. Green on all four engines.
- **Gates:** `ci.sh 3.13` at 100 % coverage (2,685 passed / 863
  skipped; pure leg 2,671); Postgres 209, MySQL 211, MSSQL 211,
  Oracle 208 (capability skips only).
