# Story status — cross-story review snapshot

A periodic true-up of story specs against the code. **This is a
snapshot, not a live index** — trust the per-story `spec.md` status
lines first; regenerate this file when the picture shifts (review the
open/seed/draft specs against `src/vfs/` and update both).

- **Last reviewed:** 2026-07-10, against `main` at `fee073d`
  (story 071 landed); 068/039/044/017 entries trued up 2026-07-11
  when 068 landed.
- **Method:** every spec's status line collected, then the
  draft/seed/in-progress stories verified against the actual code
  (`base.py`, `permissions.py`, `ops.py`, `params.py`, `results/`).

## Outstanding work that touches `base.py`

Ordered by a suggested sequence (051 next, with 070 whenever — 068
landed before it, so the `Principal` rename now ripples through
`add_mount`/`remove_mount`'s internal calls only).

- **068 — mount admin completeness**: **landed 2026-07-11** (features
  1–3: `mounts()`/`MountInfo`, atomic `remount`, `deny_ops` mask on
  constructor/`bind`/`add_mount`/`remount`; `MountMeta` now stores
  `declared_caps` + `deny_ops` with derived post-mask `caps`).
  Features 4 (`move_mount`) and 5 (`LazyStorage`) stay demand-gated —
  split into new stories if picked up.
- **039 — execute permission tier** (draft; superseded in practice by
  068's `deny_ops` — see its status line). `run` stays outside the
  permission-map vocabulary; denied execution classifies
  `unsupported`. Reopen only for per-path/per-principal execute
  policy.
- **051 — fanout deadline** (draft; premise intact). No time budget
  anywhere in fan-out — `_gather_settled` gathers with no deadline;
  the `timeout` error kind exists in `results/kinds.py` but is unused.
  Do not confuse with the hop *budget* (`_hop_budget`/`_HopGrant`),
  which is mount-loop prevention, not a deadline.
- **070 — principal-scoped sessions** (draft; decisions 1–4 recorded
  2026-07-10). The largest pending change: `user_id: str | None` →
  verified `Principal` on every public verb, every `_route_*` helper,
  and the storage funnel (~87 `user_id` references in `base.py`).
  Supersedes 058's `user_id` phrasing and delivers the `Principal`
  that 058's grants consume.
- **053 — router review cleanups** (draft; mostly stale after 069/071
  — see its status line). Only the bare-assert item clearly survives.

## Outstanding work that does NOT touch `base.py`

- **056 Pass B and Pass C** — the `VFSStorageAdapter` (`adapter.py`)
  and the MCP trio (`backends/mcp.py`, `mcp_server.py`, `mcp` dep) are
  unlanded (tasks 19–27, acceptance criteria unmet). All new-file
  work; Pass A already carried every `base.py` change. Also carries
  057 decision 13's inbound half (`VFSStorage` treating a parseable
  vfs payload as authoritative), which waits on Pass C.
- **044 — mount rights mask**: **superseded by 068 feature 3**
  (landed 2026-07-11). Its signed-off decisions carried over onto
  `MountMeta.caps`/`_gate_entry`; its `Rights`-in-terminal-gate
  mechanism is retired with it.
- **045 — verb wire contract** (draft; doc/contract artifact). No
  schema artifact exists yet; post-071 `params.py` `ParamSpec` tables
  are a better drift-test substrate than the raw signatures the spec
  assumed.
- **054 — serve() locks topology** (policy decision). Waits on
  `serve()` existing; its `allow_child_mounts` premise is stale (see
  its status line).
- **058 — row-level grants** (seed; eleven clarification forks; needs
  070's `Principal`). Enforcement lands in `permissions.py`/query
  construction, not the router.
- **067 — graph traversal-only** (seed). Work is in the future graph
  subsystem and `results/` rendering; `base.py` dispatch unaffected.

## Closed or trued-up in this review (2026-07-10)

- **069** — status corrected: landed in `22a3f33` (was "pending
  commit").
- **047** — closed: both findings fixed as side effects of 069 + 071.
- **055** — closed: core landed via 056 Pass A; the fused
  mkdir→bind `add_mount` shape was superseded by 056 decisions 4/5.
- **053** — re-triage note added (items 2–4 stale/obsolete).
- **054** — stale `allow_child_mounts` premise flagged.

## Fully landed and verified in code (recent line)

049 → 055 → 056 Pass A → 057 (Passes A+B, complete — no Pass C
exists) → 069 → 071. `base.py` has no TODO/FIXME markers and no
unmerged branches carry router work.
