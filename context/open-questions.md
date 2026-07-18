# Open Questions

**Status:** live — first populated 2026-07-16 (from the specs/STATUS.md picture)
**Purpose:** A single list of unknowns, undecided calls, and parked ideas. Anything tagged `[NEEDS CLARIFICATION]` anywhere in `/context` should have a pointer here.

## Format

```
## <short title>
- **Asked:** YYYY-MM-DD by <who>
- **Context:** 1-2 sentences of what prompted the question
- **Blocking:** list of specs/plans/decisions that are waiting on this
- **Options considered:** bullet list
- **Status:** open | parked | resolved (→ link to decision or story that closed it)
```

## Lifecycle

- **open** — actively unresolved; blocks work
- **parked** — deliberately deferred; not blocking but not forgotten
- **resolved** — closed by a decision or story; keep the entry and link to what closed it

Resolved questions stay in this file as a record; they are not deleted. If the list grows long, split resolved ones into `open-questions-archive.md`.

---

## Row-level grant semantics (spec 058's clarification forks)

- **Asked:** 2026-07-10 (spec 058 seeded with eleven `[NEEDS CLARIFICATION]` forks)
- **Context:** Row-level permission grants need a verified `Principal` before enforcement semantics can be pinned; the forks cover grant shape, inheritance, and query-construction enforcement.
- **Blocking:** `specs/058-row-level-permission-grants/`
- **Options considered:** see the forks inline in 058's spec
- **Status:** open — waits on spec 070 (`Principal`) landing first

## serve() topology-lock policy premise

- **Asked:** 2026-07-10 (flagged in the STATUS true-up)
- **Context:** Spec 054 decides that `serve()` locks mount topology, but its `allow_child_mounts` premise went stale after 056/068 reshaped mount admin.
- **Blocking:** `specs/054-mcp-serve-locks-topology/` — itself waiting on `serve()` existing
- **Options considered:** re-derive the policy against the post-068 mount admin surface, or fold it into the MCP serve spec when that work starts
- **Status:** parked

## Per-path / per-principal execute policy

- **Asked:** 2026-07-11 (068 landing superseded spec 039's mechanism)
- **Context:** `run` stays outside the permission-map vocabulary; denied execution classifies `unsupported`. 068's `deny_ops` covers the mount-level need.
- **Blocking:** nothing today; reopen `specs/039-execute-permission-tier/` only if per-path or per-principal execute policy becomes real
- **Options considered:** permission-map tier (039's original shape) vs. mount-level `deny_ops` (landed)
- **Status:** parked

## Bare-node default: full store or directories-only?

- **Asked:** 2026-07-16 (surfaced writing ADR 009 during the archive mining pass)
- **Context:** Story 055 decided `VirtualFileSystem()` defaults to directories-only `InMemoryStorage(allow_files=False)`; the landed code passes no flag and `allow_files` defaults `True` (`base.py:211`, `memory.py:84`), so a bare node is a full in-memory store. `git log -L` shows it never shipped as directories-only.
- **Blocking:** nothing — but ADR 009 records the landed shape, so if directories-only was the real intent this is a latent defect to fix and ADR 009 needs a follow-up note
- **Options considered:** keep full-store default (ratify the divergence) vs. restore 055's directories-only intent
- **Status:** open

## Mount-wide change cursor: does anything need one after revisions go per-entry?

- **Asked:** 2026-07-17 by Clay + Claude (write-path prior-art memo §3)
- **Context:** The plan to drop the per-mount ordered revision counter (per-entry versions + index-status flags) removes the only mount-wide total order of changes. Nothing live depends on "everything changed since T" today, but sync/replication/audit features would.
- **Blocking:** the revision-split ADR (to be written from `research/2026-07-17-write-path-prior-art-and-scaling.md` §4.1–4.2) — it should state the answer either way
- **Options considered:** no cursor needed (updated_at + per-entry versions cover near-term); append-only change-log table written in the same txn; revive ordered allocation only for the feature that needs it
- **Status:** resolved 2026-07-17 (Clay, in session) — `updated_at` is the change cursor; no change-log table, no ordered allocation. It is coarse (wall-clock, tie- and skew-prone): consumers query with slack and dedupe by per-entry version. Recorded in `research/2026-07-17-write-path-prior-art-and-scaling.md` §3; the revision-split ADR ratifies it.

## Ancestor propagation: is a background task acceptable in the deployment model?

- **Asked:** 2026-07-17 by Clay + Claude (write-path prior-art memo §4.3)
- **Context:** Parent-directory revision bumps are the remaining shared-row write; Oak and JuiceFS both move ancestor updates to an in-memory accumulator with a batched background flush. Whether we can do the same depends on whether the backend may own background work or must stay purely request-scoped.
- **Blocking:** memo §4.3's (a) background flusher vs (b) derive-at-read choice; the hot-parent fix in the scaling ADR
- **Options considered:** background accumulator + flush (Oak/JuiceFS pattern); derive directory change from `MAX(updated_at)` over children at read time and drop stored bumps; keep synchronous bumps and accept same-directory fan-in contention
- **Status:** resolved 2026-07-17 (Clay, in session) — storage owns no background work, so the Oak/JuiceFS accumulator is out. At-scale path: derive directory change from children at read time; stored parent bumps leave the write path (synchronous bumps acceptable until then). Recorded in `research/2026-07-17-write-path-prior-art-and-scaling.md` §4.3.
