# Story status — cross-story review snapshot

A periodic true-up of story specs against the code. **This is a
snapshot, not a live index** — trust the per-story `spec.md` status
lines first; regenerate this file when the picture shifts (review the
`active/` specs against `src/vfs/` and update both).

- **Last reviewed:** 2026-08-16, at spec 100's mining pass. That arc,
  all in two days: slice A's expansion-caps research memo and
  rerunnable study landed and the §6 cap fork resolved by Clay
  (both caps, small values); slices B–D landed as one planner
  rewrite (bounded variants, `MAX_CLASS_MEMBERS = 8` /
  `MAX_VARIANT_WIDTH = 64`, degrade-never-refuse) with executed cap
  mutants, the battery planner edition (181 case-checks), and the
  ladder planner rows; spec 100 mined and archived (decision set →
  ADR 038) and ADR 033's deferred item discharged. Suite re-verified
  green same day (2,301 passed / 838 skipped, coverage 100%,
  `ruff`/`ty` zero, full 3.11–3.14 matrix). Entries older than this
  arc carry forward from the 2026-08-14 review unverified.
- **Previous review:** 2026-08-14, at the 095–099 mining pass. That
  pass: all five campaign specs mined and archived (residue verified
  downstream — ADR amendments, `open-questions-archive.md`
  resolutions, battery editions); specs 100 (gram-planner upgrades),
  101 (move/copy drop `overwrite` — Clay's 2026-08-14 resolution of
  the last agent-reachable destruction), and 102 (set-based scattered
  delete, research-first) drafted into `active/`; `open-questions.md`
  split live-only with resolved entries moved to
  `open-questions-archive.md`; the Grover-era references purged from
  live surfaces (src, standards, CONTRIBUTING, docs) and the two
  top-level relics deleted; suite re-verified green same day (2,276
  passed / 838 skipped, `ruff`/`ty` zero). Router-era entries (039,
  045, 051, 053, 054, 070) carry forward from the 2026-07-10/11
  review — not re-verified, and no commits since have claimed router
  work.
- **Earlier review:** 2026-07-26, the specs-reorg session (tree at
  `d616d75`): verified the 084–090 line directly (code spot-checks
  against each spec's decisions, full suite at 1873 passed / 744
  skipped; four Docker legs green at each 07-26 landing) and moved
  every landed spec into `archive/`.
- **Layout (since 2026-07-26; deletion rescinded 2026-08-05):** open
  specs live in `active/`; landed specs move to `archive/`, get their
  backward-flow mining pass, and stay there permanently as the
  historical record. See `README.md`.

## The active line: finishing the database backend's verb surface

- **072 — database storage backend** (in progress; the umbrella
  story). Live surface: read/stat/ls/tree/glob/grep +
  write/edit/mkdir + delete/move/copy + restore/sweep + the
  `reindex()` admin verb, hardened by the 086–090 coherence
  campaign. **mkedge is the only remaining classified stub**
  (`backend.py`; capabilities now derive via `storage_ops(self)`
  minus mkedge). Pass C (grep, tasks 19–22) discharged by 093's
  2026-08-05 landing. The real-engine harness (four Docker legs +
  the `db_test` skill) supersedes task 13's original CI-leg framing.
  Task 17 (edges slice) is reshaped by ADR 018 and waits on its
  wiring spec.
- **073 — glob segment semantics** — **landed 2026-08-01** (all four
  slices in one session: LIKE fusion, `glob_patterns.py` chokepoint,
  ext pushdowns with the stored-column agreement made structural,
  py3.13 floor (later lowered — floor 3.11, target 3.13, ADR 035,
  with an in-house translator replacing the stdlib wrap),
  conformance true-up; four Docker legs green; spike
  re-pointed at the landed code, claims 2–5 pass). **Mined and
  archived 2026-08-05**: decision set → ADR 032; spike →
  `../research/studies/2026-07-14-glob-like-superset/`.
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
  probe-carried assertions; **spec 092 (landed 2026-08-05)** owned
  implementation, and the interim dispatch shape is deleted.
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
  **Mined and archived 2026-08-05**: all residue was already
  downstream (ADR 030 as amended by ADR 031, the 2026-07-31 memo,
  the residuation study).
- **092 — pattern-only glob seam** — **landed 2026-08-05** (all four
  slices in one session on Clay's go-ahead). The storage glob
  contract is now `patterns: tuple[str, ...]` — scoping crosses the
  seam only as pattern text (`composed_pattern` in
  `glob_patterns.py`: name arm `root/**/pattern`, path arm via
  `effective_pattern`, canonicalization downstream of composition),
  one batched call per entry in one transaction/snapshot; the
  backend executor renders one self-contained OR-arm per pattern
  (all ext and liveness facts inside the arm — the multi-index OR
  plan is pinned surviving them; a contradicted arm is dead before
  SQL), chunked at ~200 arms by `arm_budget` (bind, IN-list, and
  expression-depth caps); root assertions ride a concurrent
  router-side `stat` probe per owning entry (three-way outcomes —
  Clay resolved the stat-incapable corner 2026-08-05 as honest
  "undeterminable" warnings; root rows served on a pattern hit, the
  find-operand rule). Interim scaffolding (per-residual dispatches,
  session bound, subsumption carve-out) deleted; storage-side
  "anchor" vocabulary retired. Proof: differential find/rg battery
  green (52 case-checks), scale
  rows pinned (10k roots → one glob + one probe call; 10k patterns
  → 50 statements, one session), `verify_residuation.py` identical
  statistics, four Docker legs green (postgres 173 / mysql 173 /
  mssql 174 / oracle 172), MSSQL benchmark gate passed (batched fan
  3.8× ahead at K=100, 1.4× at K=1,000). Suite 2010 passed, coverage
  100%, `ruff`/`ty` zero. **Mined and archived 2026-08-05**:
  decisions were already ADR 031; the differential battery and the
  MSSQL benchmark moved to `../research/studies/` (dated 2026-08-05)
  as the permanent harness and the recorded result.
- **093 — grep content search** — **landed 2026-08-05** (all four
  slices in one arc; owns 072 Pass C / tasks 19–22, discharged). The
  last read-family stub is live: the byte-trigram index (refusal
  gate + `allow_scan`, k=4 rarest-first under a posting-byte budget,
  batch-only epoch lifecycle with CAS flip), the ADR 013
  flag-partitioned overlay superseding 072 §6's watermark, and grep
  born on the pattern-only seam + probe (ADR 031 D4/D6, ADR 032
  §5/§6 discharged). All three shaping forks resolved by Clay same
  day (staleness trait `"overlay"`; truncation flag with
  refine-guidance now, cursor deferred to the MCP pass; planner
  upgrades deferred whole). Slice D's flip: capabilities derive via
  `storage_ops(self)` minus mkedge, traits declare
  `grep_tier="indexed"` / `grep_staleness="overlay"`, every grep
  conformance row (incl. the pattern-class taxonomy and
  fold-shortening edge) live on every leg. Proof: epoch-atomicity
  seam row, scale rows (10k roots → one call + one probe; budgeted
  reindex statements), the grep differential battery (109
  case-checks vs `grep -E`/`rg -uu` over four worlds) and the
  rerunnable query-ladder benchmark, both under
  `../research/studies/` (dated 2026-08-05). Suite 2126 passed,
  coverage 100%, `ruff`/`ty` zero; four Docker legs green with grep
  live (Postgres 191 / MySQL 191 / MSSQL 192 / Oracle 190).
  **Mined and archived 2026-08-05**: decision set → ADR 033
  (refusal gate + `allow_scan`, budgets and the deferred cursor,
  folded planning, chunk-grain corpus, batch epoch lifecycle,
  seam inheritance, capability derivation and trait vocabulary);
  the two studies were already downstream; fork resolutions rest
  in `../open-questions.md`.
- **094 — glob language field parity** — **landed 2026-08-07** (three
  slices, same session as its shaping review; five forks resolved by
  Clay same day). Brace alternation expansion-first at the chokepoint
  (`expand_pattern`, twice-gated defects, `MAX_PATTERN_ARMS` 64,
  nesting refused), `globs_not`/`ext_not`/`kind` on glob (the one
  `SupportsPatternSearch.glob` signature change; exclusions
  authority-side per the false-negative doctrine; `kind` inside every
  arm), chained `kind=` fetch-to-populate. Proof: brace edition of
  the differential battery (121 case-checks vs `rg -g`), the
  cap-×-1k-roots scale row, four Docker legs green. **Mined and
  archived 2026-08-13**: decision set → ADR 037; the ADR 030/034
  annotations, docs flips, and battery were already downstream at
  landing.
- **The 095–099 review-campaign arc — all landed and committed
  2026-08-13; all five mined and archived 2026-08-14** (residue was
  already downstream at each landing; per-spec status lines carry the
  mining notes). A 73-agent five-lens review of the 092/093/094 arc
  (`f1ab5b3^..0359c8d`) produced the 2026-08-13 campaign memo (30
  verified findings, 8-question decision pass resolved by Clay) and
  five specs, each implemented same day:
  - **095 — reindex integrity and engine parity** (`4de5878`):
    flag-algebra closure (restore-after-rebuild blindness), the MSSQL
    reindex break (`_pending_probe` reshaped legal-everywhere), and
    the engine-marked reindex→indexed-grep conformance rows the four
    legs were missing.
  - **096 — gram coverage and chunk boundaries** (`1567619`, decision
    record ADR 036): chunks are semantic-only, the gram index reads
    whole entries — the boundary-straddle false negative closed at
    the grain, pinned by the boundary battery and codec pin.
  - **097 — grep runtime bounds and isolation** (`db23271`):
    epoch-consistent reads, bounded runtime, the reindex lease.
  - **098 — literal text and line semantics** (`a577c28`):
    `escape_glob` quoting root text at every composition seam (the
    ADR 030 rationale-3 regression repaired), the dialect-conditioned
    `escape_like` bracket class (MSSQL), the `\n`-only line law
    (`split_lines`), the bang-class arm; four legs green, control-
    character differential battery 157 case-checks.
  - **099 — ownership and vocabulary cleanup** (`810ff3d`): the
    decision pass landed — `passes_filters` home, `ext_membership`
    pair, `normalize_ext_channel`, `GLOB_CHANNEL_LABELS`,
    `meta_scoped` delegation, posting row cap deleted, floor facts
    trued. Behavior byte-identical (38,880-case differential).
- **100 — gram-planner upgrades** — **landed 2026-08-16** (slice A
  research 2026-08-16 morning, slices B–D the same day as one
  planner rewrite). The ADR 033 successor story: the planner
  compiles bounded guaranteed-literal variants — small classes fork
  per post-fold member, alternations fork at any depth through
  transparent groups, anchors are zero-width transparent — under two
  declared caps (`MAX_CLASS_MEMBERS = 8`, `MAX_VARIANT_WIDTH = 64`,
  the glob arm cap's value), over-cap nodes degrading to the flush.
  Field-corpus refusal delta 28% → 22%; the collapse law and the
  refusal gate unchanged. Proof: pinned rows (`min|max`,
  `^(#|Using)`, the starvation guard, `[fF]oo`), executed cap
  mutants, upgrade fuzz, battery planner edition (181 case-checks vs
  `grep -E`/`rg -uu`, four worlds), ladder planner rows (rescued
  classes 21–28 ms vs 272–318 ms scans). Suite 2,301 passed,
  coverage 100%, `ruff`/`ty` zero, full 3.11–3.14 matrix. **Mined
  and archived 2026-08-16**: decision set → ADR 038; the memo,
  studies, and ADR 033 true-up were already downstream.
- **080 — mysql batch UPDATE statements** (draft 2026-07-23,
  research-first; owns the per-row executemany cost question in
  `../open-questions.md`). No implementation until its preconditions
  are verified on real engines.
- **101 — move/copy drop `overwrite`** (draft 2026-08-14) — Clay's
  resolution of the last agent-reachable destruction: the flag is
  removed entirely, occupied destinations refuse `exists`,
  displacement is delete-then-transfer; ADR 027's contract sentence
  loses its exception. No open forks.
- **102 — set-based scattered delete** (draft 2026-08-14,
  research-first) — owns the 10k-scattered-target topology-lock-hold
  question; research memo before any design.
- **103 — grep pipeline Rust core** (draft 2026-08-16; slice A done
  same day) — Clay's resolution at the linux-benchmark readout: the
  measured-slow grep loops move to Rust behind unchanged contracts;
  acceptance bar = beat rg on every row of the recorded 25-query
  bench. Slice A's three memos landed 2026-08-16 (read-path profile:
  verify is 82–99.7% of every query and the floor is the 366 MB
  unindexable overlay tail; verify-stage prior art: lines are
  presentation, not matching; accelerator packaging: two-package
  psycopg shape recommendation, `abi3-py311`); the posture fork
  resolved in two steps — pure-Python fallback stays, and the shape
  is one package on the pendulum model (maturin mixed layout,
  fallback inside every wheel), with the Rust workspace's
  binding-free core crates shaped to seed the vfs-js / vfs-rs
  roadmap. Slices B–D unblocked.

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
- ~~Open decision worth making soon: move/copy `overwrite=True`~~ —
  **resolved 2026-08-14** (Clay): the flag is removed entirely; spec
  101 owns the landing (see the active line above).

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
→ 089 → 090 → 073 → 091 → 092 → 093 → 094 → 095 → 096 → 097 → 098 →
099 → 100. ADRs 001–038 accepted (005 superseded by 016; 021/022
proposed, awaiting ratification; 018 awaiting its wiring spec; 032,
033, 037, and 038 are the retroactive records of 073's, 093's, 094's,
and 100's decision sets, written at their mining passes; 036 amends
033's chunk-grain clause). The 073/091/092 glob arc, 093, 094, the
095–099 campaign arc, and 100 are all mined and archived (095–099 on
2026-08-14; 100 on 2026-08-16). Tree green at 2,301 passed / 838
skipped, coverage 100%, `ruff`/`ty` at zero (2026-08-16, full
3.11–3.14 matrix), all four Docker engine legs green as of the 098
landing (2026-08-13).
