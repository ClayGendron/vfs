# 083 — The trash sweep verb and the retention policy

- **Status:** landed 2026-07-24 — executes ADR 014 pin 5 and
  ADR 026 pin 5; the retention numbers were decided here (Clay,
  in session), closing the open-questions entry they were parked in.
  Awaiting its residue-mining pass and deletion.
- **Evidence:**
  `context/decisions/014-trash-normal-fs-parity.md` (pin 5);
  `context/decisions/026-self-describing-trash-names-and-restore-contract.md`
  (pin 5); `context/open-questions.md` — "Trash retention policy".
- **Depends on:** specs 081/082 (the trash arc's naming and restore
  contracts; sweep completes the arc).

## Problem

Trash accumulates without bound: ADR 014 pins reclamation as an
explicit idempotent verb (storage owns no background work) and ADR 026
pins its mechanism (parse `<YYYY-MM-DD-HH>` bucket names, drop expired
buckets wholesale), but no verb exists and no retention length was
ever declared. For the ETL audience a single bulk delete parks an
entire dataset in one bucket — capacity risk with no reclamation
story.

## Decisions this spec owns

1. **Retention is 90 days by default, configured per backend.**
   `DatabaseStorage(trash_days=90)` — the JuiceFS shape (a
   deployment-posture knob, not a per-call argument). Generous next to
   the field's 30-day convention, deliberately so: the sweep is
   explicitly invoked, so retention is a floor on what a sweep may
   destroy, not a promise of timely reclamation. `trash_days=0` is
   lawful (everything expires); negative refuses at construction.
   **The size bound and oversized-delete bypass stay demand-gated** —
   recorded in `open-questions.md`, not built here.
2. **`sweep` is a routed op addressed at the trash root.** It joins
   `MUTATING_OPS`; its `path` defaults to `/.vfs/trash` and routes
   like any single-path mutation (so `fs.sweep("/m/.vfs/trash")`
   sweeps that mount's trash). The storage side refuses any other
   address as `invalid` — per-bucket reclamation is already
   `delete(permanent=True)`. The delete-style EBUSY guard applies to
   the addressed subtree, so a bind site inside the trash region
   refuses `busy` before dispatch.
3. **Expiry keys off canonical bucket names only.** A child of the
   trash root is a bucket iff it is a directory whose name round-trips
   `strptime`/`strftime` of `%Y-%m-%d-%H` exactly (the strict-parse
   lesson: the closed world is gone, so near-miss names are foreign
   state, not buckets). A bucket expires when its hour has fully aged
   out: `bucket_hour + 1h <= now - trash_days`. Expired buckets drop
   wholesale via the shared purge — including user-authored rows
   inside them, the documented macOS-purge contract.
4. **Skips are surfaced as warnings.** Every non-bucket row directly
   under the trash root — files, misnamed directories, a squatter at
   the trash root itself — is skipped and reported as a
   warning-severity `wrong_kind` entry (the row in bucket position is
   not the kind the sweep reclaims); warnings leave `success` true.
   Young buckets are simply retained, unreported. Dropped buckets are
   the observations (`status="deleted"`).
5. **Memory backend refuses.** No trash (deletes are permanent), so
   `sweep` classifies `unsupported` and is carved out of
   `capabilities()` beside `restore`; the conformance sweep family
   gates on `@needs("sweep")`.

## Acceptance criteria

- An aged bucket (creatable through public verbs — trash is an
  ordinary subtree) drops wholesale, foreign rows inside included; a
  fresh delete's bucket survives; the boundary
  (`hour + 1h` vs `now - trash_days`) is pinned with `trash_days=0`.
- Non-canonical names (`2020-1-1-0`), files under the trash root, and
  a trash-root squatter are skipped, surfaced as warnings, and
  survive; `success` stays true.
- Sweep of a never-used trash is a successful no-op, twice
  (idempotence).
- Any non-trash-root address refuses `invalid`; a bind site inside
  the trash region refuses `busy` at the router.
- Conformance sweep family enforced on sqlite and all four engine
  legs, skipped on memory; full suite, `ruff`, `ty`, 100 % coverage.

## Non-goals

- A size bound / oversized-delete bypass (demand-gated, stays in
  `open-questions.md`).
- A per-call retention override (config-only, the JuiceFS shape).
- Background or scheduled sweeping (ADR 013 pin 5: storage owns no
  background work — scheduling belongs to the deployment).
