# 085 — Delete never destroys; sweep is the only destroyer

- **Status:** open — born 2026-07-25 from ADR 027 (pins 1–4, 6).
- **Evidence:**
  `context/decisions/027-delete-never-destroys-sweep-only-destruction.md`;
  `context/decisions/014-trash-normal-fs-parity.md` (pins 3–5);
  `context/decisions/026-self-describing-trash-names-and-restore-contract.md`;
  spec 083 (landed sweep semantics this spec extends);
  `context/open-questions.md` — the amended overflow-fallback entry
  and the new overwrite-occupant entry.
- **Depends on:** spec 084 (either arm) — the contract flip must land
  against a tree whose every backend holds the trash arc.

## Problem

Permanent destruction is agent-reachable three ways: the
`permanent=True` flag on delete, and the silent hard-delete upgrade
when a delete target holds the active bucket chain. ADR 027 pins the
repair: delete always trashes and refuses what it cannot trash;
sweep — a developer-plane verb agents can never call — becomes the
only destroyer, gaining arbitrary addresses; internal callers hold
the same line.

## Decisions this spec owns

1. **`permanent` is removed everywhere.** `VFS.delete` (`base.py`),
   the delete entry in the params gate, the storage protocol's
   `delete`, and `delete_rows` (`topology.py`) all lose the
   parameter. A successful delete observation always carries
   `trash_path`; the `trash_path=None`-means-purged signal retires.
   `_subsumed_trash_path` loses its `permanent` arm; its
   chain-inside arm becomes unreachable (the covering root refuses,
   failing the batch) and goes with it.
2. **The chain-inside arm flips to refusal.** A target whose subtree
   holds the active bucket chain (`/.vfs`, `/.vfs/trash`, the
   current hour-bucket) classifies `invalid` with a message naming
   the reclamation verb — shape:
   `Cannot delete {target}: contains the active trash chain — sweep reclaims trash`.
   Older buckets keep trashing normally (nested trash stays lawful).
3. **Sweep grows the purge arm.** The address decides the arm:
   - *Trash root of the mount* — the landed retention arm, unchanged
     (canonical bucket parse, `trash_days` floor, warning skips,
     idempotent no-op on a missing root).
   - *Any other address* — immediate wholesale purge of that
     subtree: root refuses `invalid`, a miss classifies through the
     shared descent ladder (`not_found`/`wrong_kind` at the failing
     component), the router's EBUSY guard applies as it does for
     delete, and the subtree purges via the shared
     `_purge_subtree` regardless of retention age. Observations
     report `status="deleted"` with no `trash_path`. A bucket
     address is just this arm — per-bucket reclamation regardless
     of age, re-homed from `delete(permanent=True)`.
   - The `path` default stays the trash root, so the bare
     `fs.sweep()` gesture keeps meaning "retention cleanup". The
     purge arm is wholesale-only — no cascade flag; a caller who
     wants a guarded, childless-only removal has delete, which is
     recoverable and refuses `not_empty`.
4. **Sweep joins a developer-plane op classification.** `ops.py`
   grows a declared set (shape: `DEVELOPER_OPS: Final = frozenset({"sweep"})`)
   with a docstring pinning the rule: ops in this set are never
   registered on any agent-facing tool surface (MCP serve, CLI).
   The serve layer, when it lands (spec 054's line), consumes this
   set; a test pins that the agent-facing registry and
   `DEVELOPER_OPS` stay disjoint. Sweep remains on the Python API
   unchanged.
5. **The router's unmount trashes the mount directory.**
   `base.py:403` drops `permanent=True` and keeps `cascade=False` —
   the must-not-destroy-unseen-rows guarantee is the non-cascade
   `not_empty` refusal, unchanged; a refused delete leaves the
   unbind standing and raises, as today. The empty mount-directory
   row parks in trash as accepted clutter; retention reclaims it.
   Unmount deliberately does **not** call sweep: mount admin is
   headed for the agent surface, and keeping sweep free of
   agent-reachable internal callers keeps the plane rule a
   structural invariant (a test pins this — see acceptance).
6. **Contracts and records are re-said.** `topology.py`'s module
   docstring drops the permanent arm and states the refusal;
   `base.py` delete/sweep docstrings restate the one-sentence
   contract (*delete is reversible; sweep is not; agents only get
   the first*); the open-questions overflow entry's
   `permanent=True` fallback wording carries its 2026-07-25
   amendment (developer sweep or piecewise deletes).

## Acceptance criteria

- No `permanent` parameter survives on any public surface;
  `grep -rn "permanent" src/` returns only prose describing the
  sweep contract.
- Delete of `/.vfs`, `/.vfs/trash`, and the current bucket refuses
  `invalid` naming sweep, nothing purged, on the in-memory leg,
  sqlite-file, and all four engine legs; an older bucket still
  trashes (nested), and restore brings it back.
- Every successful delete observation carries a `trash_path` that
  restore round-trips.
- Sweep purge arm: an arbitrary directory and a single file purge
  wholesale on every leg; sweep of `/` refuses; a missing address
  classifies `not_found`; a bind site inside the target refuses
  `busy` at the router. Retention arm: spec 083's acceptance rows
  all still pass unchanged.
- Unmount leaves the mount directory as a trash row (restorable);
  a mount directory that gained rows the router never saw refuses
  `not_empty`, the unbind stands, and the rows survive; a
  `trash_days=0` sweep reclaims the trashed mount-dir row.
- No agent-reachable code path calls sweep: beside the
  `DEVELOPER_OPS`-disjointness test, a test pins that routing any
  agent-surface op (unmount included) never dispatches the sweep
  verb on storage.
- The `DEVELOPER_OPS`-disjointness test pins sweep off the
  agent-facing surface.
- Full suite, `ruff`, `ty` at zero, coverage held, four engine legs
  green.

## Non-goals

- Trashing move/copy overwrite occupants — the last agent-reachable
  destruction, deliberately left open (`open-questions.md`); this
  spec neither closes nor widens it.
- A trash size bound or oversized-delete bypass (demand-gated,
  `open-questions.md`).
- Background or scheduled sweeping (ADR 013 pin 5 stands; the
  deployment schedules the trash-root sweep).
- Permission-tier gating of sweep (the plane split makes it moot on
  the agent surface).
