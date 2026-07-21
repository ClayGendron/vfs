# Story status — cross-story review snapshot

A periodic true-up of story specs against the code. **This is a
snapshot, not a live index** — trust the per-story `spec.md` status
lines first; regenerate this file when the picture shifts (review the
open/seed/draft specs against `src/vfs/` and update both).

- **Last reviewed:** 2026-07-20, against `main` at `2cf80b7`
  (ADR 018 docs landed). This pass trued up the 072–076 storage arc
  (specs 074/075/076 landed; 072 slices 6–8 landed and rewritten in
  place; tasks.md 11/13/17 annotated). Router-story entries (051,
  053, 056, 070, etc.) carry forward from the 2026-07-10/11 review —
  not re-verified this pass, and no commits since have claimed router
  work.
- **Method (this pass):** recent spec status lines read, then verified
  against the live backend surface
  (`storage/backends/database/backend.py` — which verbs delegate vs
  stub), 072's task checklist, and `git log` hashes.

## The active line: 072 database backend and its rewrites

- **072 — database storage backend** (in progress). Landed: slice 6
  skeleton (`5238324`), slice 7 read family + glob (`f69824a`),
  slice 8 mutation core (`b488e25`), membership-predicate budget
  bounding (`d9ca522`). Live surface: read/stat/ls/tree/glob +
  write/edit/mkdir; **grep, delete, move, copy, mkedge are classified
  stubs.** Next in sequence: task 12 (slice 9, `topology.py`
  move/copy/delete), then the Postgres CI leg (task 13 — its
  revision-allocation half is dead per ADR 013, see tasks.md note).
  Task 17 (edges slice) is reshaped by ADR 018 and waits on its
  wiring spec.
- **074 — per-entry revisions**: **landed 2026-07-17** (`7f152af`).
  Ordered per-mount counter gone; revisions are per-entry monotone
  values; ADR 013 executed in full.
- **075 — trash normal-fs parity**: **landed 2026-07-18** (`44aa439`).
  `/.vfs/trash` is an ordinary subtree under the meta scope; the
  reserved-scope filters and gates of 072 §9 are retired (ADR 014).
- **076 — entry model split**: **landed 2026-07-19** (`40408da`).
  `Entry` + `Chunk` + `Version` + `Edge`; chunks/versions/edges off
  the namespace; version numbers are revision values (ADR 017);
  version history pinned content-only.
- **073 — glob segment semantics** (shaped, ready for plan.md).
  Owner decision and open questions resolved 2026-07-14; soundness
  machine-verified. Land before or with Pass C grep (shared pattern
  language).

## Decided but unspecified — the next spec to write

- **ADR 018 — edge authoring** (accepted 2026-07-19, `2cf80b7`; docs
  only). Batch-native `mkedge`/`rmedge`, touch/upsert, materialized
  reserved-type `"fs"` hierarchy edges minted storage-side,
  `parent_id` retained as write-side arbiter. **No spec exists yet**;
  pin 9 (user-edge fate on entry delete) and pin 8's conformance
  invariant (fs edges mirror `parent_id` after every mutating verb)
  are explicitly the wiring spec's to own. The live `mkedge`
  (`base.py`; stubbed in the database backend) predates the ADR.
  Feeds 067 (graph traversal-only).

## Outstanding work that touches `base.py`

Carried forward from the 2026-07-10/11 review (not re-verified this
pass):

- **068 — mount admin completeness**: landed 2026-07-11 (features
  1–3). Features 4 (`move_mount`) and 5 (`LazyStorage`) stay
  demand-gated — split into new stories if picked up.
- **039 — execute permission tier** (draft; superseded in practice by
  068's `deny_ops`). Reopen only for per-path/per-principal execute
  policy.
- **051 — fanout deadline** (draft; premise intact). No time budget
  anywhere in fan-out; the `timeout` error kind exists in
  `results/kinds.py` but is unused.
- **070 — principal-scoped sessions** (draft; decisions 1–4 recorded
  2026-07-10). The largest pending `base.py` change: `user_id` →
  verified `Principal` everywhere. Supersedes 058's `user_id`
  phrasing.
- **053 — router review cleanups** (draft; mostly stale — only the
  bare-assert item clearly survives).

## Outstanding work that does NOT touch `base.py`

- **056 Pass B and Pass C** — `VFSStorageAdapter` and the MCP trio
  (`backends/mcp.py`, `mcp_server.py`, `mcp` dep) unlanded (tasks
  19–27). All new-file work; carries 057 decision 13's inbound half.
- **045 — verb wire contract** (draft; doc/contract artifact). No
  schema artifact yet; post-071 `ParamSpec` tables are the better
  drift-test substrate.
- **054 — serve() locks topology** (policy decision; waits on
  `serve()` existing; `allow_child_mounts` premise stale).
- **058 — row-level grants** (seed; needs 070's `Principal`).
- **067 — graph traversal-only** (seed; now downstream of ADR 018's
  wiring spec — traversal reads the one edges table).

## Fully landed and verified in code (recent line)

049 → 055 → 056 Pass A → 057 → 069 → 071 → 072 slices 6–8 → 074 →
075 → 076. ADRs 001–018 accepted (005 superseded by 016);
013/014/015/016/017 executed in code, 018 awaiting its spec. Tree green at 1461 passed, `ruff`/`ty`
at zero (076's landing verification).
