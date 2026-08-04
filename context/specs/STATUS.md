# Story status — cross-story review snapshot

A periodic true-up of story specs against the code. **This is a
snapshot, not a live index** — trust the per-story `spec.md` status
lines first; regenerate this file when the picture shifts (review the
`active/` specs against `src/vfs/` and update both).

- **Last reviewed:** 2026-07-26, in the specs-reorg session (tree at
  `d616d75`). This pass verified the 084–090 line directly (code
  spot-checks against each spec's decisions, full suite at 1873
  passed / 744 skipped, `ruff`/`ty` at zero; the four Docker engine
  legs were run green at each 07-26 landing and not re-run here) and
  moved every landed spec into `archive/`. Router-era entries (039,
  045, 051, 053, 054, 070) carry forward from the 2026-07-10/11
  review — not re-verified, and no commits since have claimed router
  work.
- **Layout (since 2026-07-26):** open specs live in `active/`; landed
  specs move to `archive/` until their backward-flow mining pass, then
  are deleted. See `README.md`.

## The active line: finishing the database backend's verb surface

- **072 — database storage backend** (in progress; the umbrella
  story). Live surface: read/stat/ls/tree/glob + write/edit/mkdir +
  delete/move/copy + restore/sweep, hardened by the 086–090
  coherence campaign. **grep and mkedge are the only remaining
  classified stubs** (`backend.py`). The real-engine harness (four
  Docker legs + the `db_test` skill) supersedes task 13's original
  CI-leg framing. Task 17 (edges slice) is reshaped by ADR 018 and
  waits on its wiring spec.
- **073 — glob segment semantics** — **landed 2026-08-01** (all four
  slices in one session: LIKE fusion, `glob_patterns.py` chokepoint,
  ext pushdowns with the stored-column agreement made structural,
  py3.13 floor, conformance true-up; four Docker legs green; spike
  re-pointed at the landed code, claims 2–5 pass). Awaiting its
  backward-flow mining pass, then archive.
- **091 — glob namespace routing** — **landed 2026-08-01**, same
  session, test-first throughout (ADR 030: namespace-coordinate
  patterns, residual routing at the seam, roots + root-anchored
  filters). `effective_pattern`/`residuals` in `glob_patterns.py`,
  the residual dispatch step in `base.py`, the placement-invariance
  battery in `tests/base/test_glob_namespace.py`; residuation spike
  re-pointed at the landed functions stays the permanent acceptance
  harness. Four Docker legs green. **Review remediation same day**
  (five-lens verified review): adjacent-`**` canonicalization, empty
  components refuse `invalid`, ext binds charged against the anchor
  fan, per-anchor dispatch session-bounded + anchors deduped, linear
  fan-out merge, and the review's test-coverage gaps pinned. The
  dispatch-shape decision is **ADR 031, accepted 2026-08-04** after
  its confirm pass — pattern-only glob seam, `patterns` tuple batch,
  probe-carried assertions; **spec 092 (draft)** owns implementation.
  **Walkthrough remediation 2026-08-04**: the executable routing
  walkthrough (notebook study, same-named dir under
  `../research/studies/`) exposed name-arm subsumption silently
  dropping a covered root's find-operand assertion — fixed (name arm
  now dispatches both arms, pinned in the namespace battery), and
  ADR 031 sharpened from its confirm pass: ext arity committed
  (call-level `ext`, per-arm derived), probe concurrent-and-separate
  with skew accepted, probe stated as the general fan-out assertion
  law scoped to glob, MSSQL benchmark gate and two battery cases
  added as spec obligations.
  Awaiting its backward-flow mining pass, then archive.
- **092 — pattern-only glob seam** (draft 2026-08-04, born from ADR
  031's ratification; not started). The batched `patterns` storage
  contract, backend OR-arm executor under the bind budgets, the
  router root probe, interim-scaffolding deletion, differential
  find/rg battery, MSSQL benchmark gate. Supersedes the 091 interim
  dispatch shape at landing. The five-agent research pass completed
  same day —
  `../research/2026-08-04-batched-glob-seam-field-study.md` — and
  is folded in: both ADR 031 precedent claims confirmed (zoekt's
  set-atom rewrite is the batch shape in production; no studied
  system fans per root), the sqlite benchmark puts the fan ~1.4-2×
  ahead at every scale (sweet spot ~200 arms/statement, hard
  expression-depth wall at 997 arms), and two rendering rules were
  learned the hard way: ext facts must render inside arms (a
  call-level AND beside the fan measured ~350×), and LIKE-prefix
  seeks have collation preconditions the `DialectProfile` must
  declare. Awaiting shaping review.
- **080 — mysql batch UPDATE statements** (draft 2026-07-23,
  research-first; owns the per-row executemany cost question in
  `../open-questions.md`). No implementation until its preconditions
  are verified on real engines.

## Decided but unspecified — the next specs to write

- **ADR 018 — edge authoring** (accepted 2026-07-19, `2cf80b7`; docs
  only). Batch-native `mkedge`/`rmedge`, touch/upsert, materialized
  reserved-type `"fs"` hierarchy edges minted storage-side,
  `parent_id` retained as write-side arbiter. **No spec exists yet**;
  pin 9 (user-edge fate on entry delete) and pin 8's conformance
  invariant (fs edges mirror `parent_id` after every mutating verb)
  are explicitly the wiring spec's to own. The live `mkedge`
  (`base.py`; stubbed in the database backend) predates the ADR.
  Feeds 067 (graph traversal-only).
- **The multimodal ADR chain** — two research memos drafted
  2026-07-25 and awaiting review
  (`../research/2026-07-25-multimodal-storage-and-search.md`,
  `../research/2026-07-25-multimodal-result-content.md`): the
  storage-bytes ADR gates the content-channel ADR. Entries in
  `../open-questions.md`.
- **Open decision worth making soon:** move/copy `overwrite=True`
  still permanently destroys the occupant — after ADR 027 it is the
  only agent-reachable destruction left. Filed in
  `../open-questions.md`; decides whether ADR 027's contract sentence
  gains a footnote or loses the exception.

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
  The project's stated destination (MCP design).
- **045 — verb wire contract** (draft; doc/contract artifact). No
  schema artifact yet; post-071 `ParamSpec` tables are the better
  drift-test substrate.
- **054 — serve() locks topology** (policy decision; waits on
  `serve()` existing; `allow_child_mounts` premise verified dead in
  live `src/` 2026-07-22).
- **058 — row-level grants** (seed; needs 070's `Principal`).
- **067 — graph traversal-only** (seed; downstream of ADR 018's
  wiring spec — traversal reads the one edges table).

## Landed and archived (the 074–090 line)

All in `archive/`, each awaiting its backward-flow mining pass:

- **074–079** — per-entry revisions (`7f152af`), trash normal-fs
  parity (`44aa439`), entry model split (`40408da`), ULID referential
  identity (`9b426f0`), persistence-state discriminator (`3c17e8f`),
  guarded-update statement attribution (`d19d97b`).
- **081–083 — the trash arc** (landed 2026-07-24): delete reports
  where rows went, restore brings them back, sweep reclaims them
  (90-day default via `DatabaseStorage(trash_days=90)`).
- **084/085** — one landing (`b16c38b`, minors `8fcd590`,
  2026-07-25): the bespoke in-memory backend retired for
  `DatabaseStorage` over `:memory:` (ADR 028), then delete lost
  `permanent=True` — delete always trashes, sweep is the only
  destroyer (ADR 027).
- **086–088 — the write-vs-topology coherence campaign** — one
  landing (`67aa7bd`, 2026-07-26): two-sided guards on the parent
  row, `StaleSnapshot` redrive-over-probe doctrine, the adopt/absorb
  arbitration arms, guard-every-destroy, error-attribution helpers.
- **089** — descent shared idioms (`5e311be`).
- **090** — structural proof obligations (round 1 `0c200b4`, round 2
  `82f9754`): derived parent bumps, one retry-exhaustion channel,
  measured bind budgets (`statement_budget`), HY000 errno
  fall-through. ADR 029 is the ratified doctrine.

## Fully landed and verified in code (recent line)

049 → 055 → 056 Pass A → 057 → 069 → 071 → 072 slices 6–9 → 074 →
075 → 076 → 077 → 078 → 079 → 081 → 082 → 083 → 084/085 → 086/087/088
→ 089 → 090 → 073 → 091. ADRs 001–030 accepted (005 superseded by
016; 021/022 proposed, awaiting ratification; 018 awaiting its wiring
spec). Tree green at 1972 passed / 780 skipped, `ruff`/`ty` at zero,
all four Docker engine legs green as of the 073+091 landing
(2026-08-01).
