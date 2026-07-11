# Story status — cross-story review snapshot

A periodic true-up of story specs against the code. **This is a
snapshot, not a live index** — trust the per-story `spec.md` status
lines first; regenerate this file when the picture shifts (review the
open/seed/draft specs against `src/vfs/` and update both).

- **Last reviewed:** 2026-07-10, against `main` at `fee073d`
  (story 071 landed).
- **Method:** every spec's status line collected, then the
  draft/seed/in-progress stories verified against the actual code
  (`base.py`, `permissions.py`, `ops.py`, `params.py`, `results/`).

## Outstanding work that touches `base.py`

Ordered by a suggested sequence (068 → 039 → 051, with 070 first or
last depending on whether the `Principal` rename should ripple through
068's new surface or land on top of it).

- **068 — mount admin completeness** (seed, but well-decided; closest
  to implementable). New router surface: `mounts()` reading the
  `_bindings` snapshot, async `remount()` doing atomic `Binding`
  replacement under the mount lock, `deny_ops` mask on
  `bind`/`add_mount`/`remount`. Three localized clarification forks
  remain.
- **039 — execute permission tier** (draft; premise fully intact).
  Not started: `permissions.py` still has the two-value `Permission`,
  no `Rights` type, and `run` on a read-only mount still executes
  ungated (`ops.py` `EXEC_OPS` — "routed, no write gate"). Unblocks
  the 044 re-triage.
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
- **044 — mount rights mask** (draft). Chain-intersection semantics
  already partially exist via `_permission_layers` /
  `check_writable_composed`; the per-edge `rights=` mask depends on
  039, and the spec's "router reaches into the child's private map"
  premise looks obsolete post-056. Re-triage before implementing.
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
