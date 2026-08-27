# 132 — glean, lexical-only: `SupportsGlean` on the database backend with the block-posting BM25 leg, scope as candidate ids, the ladder, MaxP, and the freshness overlay

- **Status:** **landed 2026-08-27** — drafted 2026-08-26 from ADR 051 (pins 6, 7) and
  ADR 052 (pins 2, 5, 7 minus previews); **rewritten the same day
  under ADR 055**: the lexical leg is no longer an in-engine statement
  but two key-fetch rounds and the Rust scorer, with scope resolved to ids and
  a cost ladder in grep's shape. Third of the glean arc: the first
  working `glean`, lexical-only, so the verb exists and is measured
  before vectors arrive.
- **Born from:** ADRs 051, 052; memos
  `../../../research/2026-08-26-glean-in-the-engine.md` §1, §5, §6 and
  `../../../research/2026-08-26-glean-fusion-and-cross-mount-merge.md`
  §3.
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Re-read under ADR 057 decision 4 (2026-08-27):** the scorer's
  "numpy fallback" clause is void — the Rust scorer is the only
  scorer; `competing_blocks` and the summary decode become crate
  kernels (spec 142); the scope intersect is spec 141's
  `candidate_ids` kernel. No numpy enters this spec.
- **Inherits from spec 131 (landed 2026-08-27):** the harness's BM25
  driver (`tests/ranking/driver.py`) is the referee this leg must equal;
  its two laws carry over — the score is rounded to nine decimals
  before the order-by, and the tie-break is `path ASC`, not `entry_id`
  (entry ids are ULIDs minted per write; a cross-engine pin must
  survive a rebuild). The engine-leg pin rows already exist
  (`TestPostgresRankingPin` and siblings); this spec points them at
  `glean`.
- **Kind:** new verb implementation in `DatabaseStorage` (a new
  `glean.py` beside `grep.py`, in grep's shape: id resolution, posting
  fetch, engine scoring, a ladder); result-shape change on
  `Observation` usage (entries with top-K chunk `Match` rows);
  conformance rows.
- **Depends on:** spec 130 as rewritten (the block tables, the scorer,
  the stats export with ceilings), spec 131 (the harness and pins), ADR
  040's segment pushdown (`pathterms.py`, `segments.py`), grep's scan
  partition (`_entries_for_scan`), its ladder constants and
  truncation-record discipline.
- **Relates to:** spec 133 (previews on these rows), spec 135 (adds the
  vector leg and fusion to this statement), spec 137 (consumes the
  term-stats export).

## Intent

Ship `glean` with one leg so the statement shape, scope pushdown,
entry aggregation, freshness posture, envelope records and conformance
pins all exist and are exercised on every engine before the vector leg
and fusion land. A lexical-only glean is a capable `SupportsGlean`
backend (traits say so), and it is the state a mount with no embedding
provider stays in.

## Decided semantics

1. **The leg** (`glean.py`, one session, SELECTs only, the backend
   owns the transaction, `StaleSnapshot` redrive as grep) is two
   rounds in grep's shape, a third only for overflowing terms (ADR 055
   pin 4): **round one** — the `lex_df` probe for the query terms'
   summary rows `(df, idf, max_weight, blocks)` with the `lex_stats`
   row (spec 130's export), and the **head fetch** `SELECT block rows
   FROM lex_postings WHERE epoch = :e AND term IN (:terms) AND
   block_no < HEAD_BLOCKS` (`HEAD_BLOCKS = 8`, declared here; the
   `IN`-list under `membership_budget`) — two statements that need
   nothing from each other; **scoring in the engine** — `vfs.native`'s
   scorer over the fetched blocks (numpy fallback), `score DESC,
   chunk_id` order; **round two**, for each term with blocks past the
   head — spec 130's `competing_blocks` over the summary, the round-one
   candidates and θ names the blocks that can still change the top-k,
   fetched by key as `(epoch = :e AND term = :t1 AND block_no IN (…))
   OR (epoch = :e AND term = :t2 AND block_no IN (…))` — the epoch
   equality inside every arm so each is a full key prefix (factored
   outside the OR, sqlite scans the epoch: 470 ms vs 0.03 ms measured,
   ADR 055 pin 4; never a row-value `(term, block_no) IN`, which SQL
   Server refuses), each list under `membership_budget`; the plan on
   every engine leg is a landing measurement (*Landing criteria*); the
   scorer runs again over the union. Then **MaxP client-side**:
   `lex_docs` rows for the top chunks (one `IN` probe on chunk ids)
   give `entry_id`; `MAX(score)` per entry with the top-K chunks
   carried; `LIMIT n` on entries. No scoring SQL is issued on any
   dialect; the only statements are key fetches every engine plans as
   index seeks. Round-two bytes are bounded by round-one candidates ×
   one block per overflowing term (each candidate lies in one block),
   independent of a common term's df, while θ exceeds the overflowing
   terms' summed maxima; the leg records when it does not (a K = 1,000
   fusion request, an all-common query) and fetches the lists.
2. **Scope is resolved to candidate ids, then intersected**: `paths=`
   takes the globs `grep` takes, compiled through `pathterms`/
   `segments` into an id-returning statement (`SELECT entry_id …` with
   the segments join, liveness, `encoded`, `user_id`); piped
   `observations` are already ids. The candidate set maps to chunk ids
   through `lex_docs (epoch, entry_id)` — its existing index — and the
   scorer intersects it with the decoded postings (`candidates=`).
   **The ladder** decides the order by grep's cost model — estimated
   posting bytes (from `lex_df`'s `df` × bytes/posting) against the
   candidate set's size and fetch cost: a narrow scope resolves ids
   first and filters postings; a wide scope scores first and probes
   the top candidates' liveness/scope in one semi-join round (≤ 2
   probes, as measured in the prototype). A scope of tens of
   thousands of ids is never fetched client-side per query without the
   ladder choosing it.
3. **Query terms** go through spec 130's tokenizer; no term is dropped
   — a flooding term's blocks stay in the engine unless a candidate in
   their id range can still compete (ADR 055 pins 2, 4); an empty
   post-fold query classifies `invalid`; a query with more distinct
   terms than one membership chunk fetches in chunks and merges.
4. **Freshness**: the index side is the `encoded` partition; the `NOT
   encoded` set (grep's scan partition) is tokenized and scored
   client-side from live text with the epoch's `idf`/`avg_dl` by the
   same scorer, on the same scale, merged into the lexical list before
   MaxP, bounded by grep's candidate budget and deadline; one warning
   record names scanned / unconsulted / lexical-only counts.
5. **Entries out**: one `Observation` per entry — `path`, `score` (the
   entry's leg score, bounded [0, 1] by min-max over the candidate
   union so the router's contract holds from day one), `matches` = the
   top-K (default 3) chunk `Match` rows (`start`/`end` the chunk's line
   bounds, `match=None`, `content` the chunk text, `score` the chunk
   score); `populated` stamped like every read; projection default
   stays `("path", "score")`. No preview yet (spec 133).
6. **Term statistics ride the answer**: per query term `(df, N,
   avg_dl)` from spec 130's export, carried in the `Result` for the
   router (spec 137) — the `SupportsGlean` requirement of ADR 052 pin 5
   is met by the first implementation.
7. **Traits**: `glean_signals="lexical"`, `glean_staleness="overlay"`;
   `SupportsGlean` becomes a declared capability of `DatabaseStorage`
   (`storage_ops` grows `glean`).
8. **Records**: `truncated` (warning) for the df ceiling, the overlay
   budget and the entry limit when the statement's candidate window was
   full; `invalid` for an empty query; the envelope never trims
   warnings.

## Scope

In: the verb, the statement, scope, overlay, entries/top-K, stats
export on the result, traits, conformance rows, engine legs, harness
pins. Out: previews (133), vectors and fusion (135), signals (136), the
cross-mount merge (137 — the router's `Result.top` stays as is until
then; single-mount is the supported case).

## Slices

- **A — the leg and scope**: `glean.py`, the two rounds and the
  overflow round, `HEAD_BLOCKS`, MaxP/top-K, the id-resolving scope
  statement, the ladder with declared and measured constants
  (referees as grep's);
  unit tests on sqlite plus the ordered-top-10 pin on every engine leg
  (identical by construction — the same scorer — but pinned).
- **B — overlay and records**: the `NOT encoded` client-side scoring,
  budgets, the three warning records, the empty-query refusal.
- **C — surface**: `SupportsGlean` on `DatabaseStorage`, traits,
  conformance rows in `storage_contract.py` (scoped, piped, dirty-set,
  trashed-row exclusion, `user_id` scoping, entries-not-chunks), harness
  arm "lexical-only glean" with its numbers in the landing note.

## Landing criteria

- `scripts/ci.sh 3.13` green; 100 % coverage; engine legs green on all
  five real engines with the ordered-top-10 pin identical across them.
- The round-two statement plans as key seeks on every engine leg
  (`EXPLAIN` recorded per dialect in the landing note) — sqlite scans
  the epoch when the epoch equality sits outside the OR
  (`research/studies/2026-08-26-bm25-storage/landing-comparison.md`),
  so the shape is measured on each engine, not assumed.
- Harness: lexical-only glean ≥ the BM25 baseline of spec 131 on all
  three corpora (it *is* that baseline through the statement — any gap
  is a bug).
- Ledger rows: scope is exact (a scoped call never returns an
  out-of-scope entry whichever rung the ladder took); overlay coverage
  (a written-but-unreindexed file is found); the ladder's constants
  are refereed both ways (a voided constant changes a rung choice).

## Landing note (2026-08-27)

The first working `glean`: lexical-only, on every backend, measured
equal to spec 131's referee. The verb lives in `glean.py` beside
`grep.py`; the scope machinery both verbs share moved to one owner,
`scope.py`; the selection kernel became a per-query call. Nothing is
committed by this note — see the commit shape at the end.

**Landed**

- **Slice 0 — `select_blocks`** (`crates/vfs-core`, protocol 6 → 7):
  block selection is one seam call per query, not one per term; the
  summaries, the round-one candidates and their scores cross as packed
  bytes and are viewed in place on the Rust side. The six-term shape
  spec 142 left at 0.43 ms per term is **0.144 ms per query** on the
  full linux store (the memo's 0.15 ms target). Oracle, parity and
  hand tests, the fidelity referee and the harness driver all use it.
- **`glean.py`** — the two rounds (`HEAD_BLOCKS = 8`, the head fetch
  and the `lex_df` probe; `select_blocks`; the round-two key fetch
  with the epoch equality inside every arm, arms packed under the
  bind budget by `_packed_arms`); the scorer at `FUSION_K = 1,000`;
  MaxP with `TOP_CHUNKS = 3` chunk `Match` rows (line bounds, text,
  score); min-max normalisation over the candidate union, rounded to
  `SCORE_DECIMALS = 9`, ordered `score DESC, path ASC`; the
  `lexical_stats` extra on the envelope (`n_docs`, `avg_dl`, per-term
  `df`/`idf`); `invalid` for a term-less query; `truncated` warnings
  with structured `data` for the candidate window, the scope probe,
  the overlay budget and the wall clock.
- **The ladder** — two rungs priced by grep's segment allow-list:
  `≤ SCOPE_ID_BUDGET = 5,000` nominated entries → their chunk ids are
  the scorer's candidate set (filter, then fetch — exact); wider or
  unprunable → score first, gate the top chunks' rows as they are
  fetched, one deeper probe at `PROBE_DEEPEN = 4 ×`, then the record.
  `passes_gates` is the authority on every answering row on either
  rung; the constants are refereed both ways in `test_glean.py`.
- **The overlay** — the `NOT encoded` rows the gates admit (grep's
  scan partition, `OVERLAY_BUDGET = 500` in path order) have their
  bodies tokenized and encoded as blocks at query time (`encode_block`)
  and scored by the same engine with the epoch's `idf`/`avg_dl`; a
  term the epoch never saw takes a local idf. ADR 044's two-read
  protocol verbatim under the `glean:after-pointer-read` seam; a moved
  pointer raises `StaleSnapshot` for the backend's redrive.
- **`scope.py`** (new) — `passes_gates`, `pushdown_terms`,
  `channel_facts`, `static_binds`, `entries_for_scan`, `ScanNominees`,
  `Pushdown`, `CHANNEL_ARM_BINDS`, `FETCH_RIDE`, extracted verbatim
  from `grep.py`; `pointer_with_overlay` and `content_for_entries`
  promoted to `reads.py`. grep imports them (96/96 green).
- **Surface** — `SupportsGlean.glean` in `protocol.py`,
  `DatabaseStorage.glean` (`InMemoryStorage` inherits), the ctor's
  `glean_wall_seconds`, traits `glean_signals="lexical"` /
  `glean_staleness="overlay"` with both keys in `TraitKey` /
  `TRAIT_VALUES`; `VirtualFileSystem.glean` routes through the same
  dispatch builder grep uses (`_grep_dispatches` takes `op`), so
  `paths=` composes into the `globs` channel per scope root and piped
  `observations` admit their own paths as literal globs; the four
  channels declared for `"glean"` in `params.py`.
- **Tests** — `tests/storage/database/test_glean.py` (31 rows: refusals,
  ranking laws, the mask, both rungs refereed, the round-two arms on a
  140-document two-block term, multi-chunk entries, the overlay in
  every world, the budget, the two-read protocol's three shapes, the
  records' `data`); ten conformance rows in `storage_contract.py`
  (`SupportsGlean` on `ConformanceBackend`; entries-not-chunks, the
  unit scale and the path tie, scope exact in both worlds, piped rows,
  the dirty set found before reindex and the index partitioned after a
  rewrite, the meta subtree hidden unless addressed, a trashed root
  served only under its trash glob, `user_id` accepted and not applied,
  the empty query, the trait row) plus glean in the identity-mask row;
  the ordered-top-10 pin now asserts **through the verb as well as the
  driver** (`pins.py`) on all six backends; the harness arm `glean`
  (`driver.glean_run`) recorded in `baselines.json`.

**Deviations from the spec, all deliberate**

- *Scope crosses the seam as grep's channels, not as `paths`* (pin 2):
  `SupportsGlean.glean` takes `ext / ext_not / globs / globs_not /
  observations`; the router composes `paths=` into globs per scope
  root through the builder grep already owns. One owner for scope
  text on both verbs; the id-resolving statement is the same
  allow-list grep prunes with.
- *The ladder prices scope by the allow-list's size*, not by estimated
  posting bytes — the count is known before any posting is fetched and
  the budget is a declared entry count, not a cost model with two
  unmeasured constants.
- *`user_id` is accepted and not applied.* Every read on this backend
  ignores it today; row-level grants are spec 058's and are not
  half-built here. The conformance row pins the current behaviour so
  the day it changes, the row changes with it.
- *The overlay answers whole entries*: one `Match(start=1, end=1,
  content=None)` per fresh row. Chunk text for unindexed rows is spec
  133's preview work.
- *No record when round two fetches whole lists* (pin 1's last
  sentence — θ at or below the overflowing terms' summed maxima, the
  all-common query at K = 1,000). The fetch is still bounded by the
  lists and the answer is exact; the record needs a classification
  that is neither `truncated` nor `invalid`, which is a results
  vocabulary decision. Residue below.

**Harness** — the `glean` arm equals the BM25 baseline to the fourth
decimal on every corpus (`assert_arms_agree` pins them to 1e-9): the
verb *is* the driver through the product path.

| corpus | arm | nDCG@10 | MRR@10 | recall@10 | recall@50 |
|---|---|---|---|---|---|
| vfs-native | bm25 = **glean** | 0.7589 | 0.9833 | 0.4134 | 0.7852 |
| SciFact | bm25 = **glean** | 0.6580 | 0.6235 | 0.7890 | 0.8737 |
| NFCorpus | bm25 = **glean** | 0.3052 | 0.5152 | 0.1459 | 0.2045 |

**The round-two statement on every engine** (`EXPLAIN` of the product
shape — bound parameters, two arms, `block_no IN (…)` in each — on a
1,500-document spanning corpus whose common terms span twelve blocks;
the scratch script is the session's, not the repo's):

| engine | plan | note |
|---|---|---|
| sqlite 3.50.4 | `MULTI-INDEX OR` → two `SEARCH … USING PRIMARY KEY (epoch=? AND term=? AND block_no=?)` | 0.58 ms cold. **Only with bound parameters**: the same SQL rendered with literals plans `PRIMARY KEY (epoch=?)` — the epoch scan — until `ANALYZE` runs. Debug scripts that render literals mislead. |
| Postgres 17.10 | `BitmapOr` of two `Bitmap Index Scan` on the pkey, full `(epoch, term, block_no = ANY(…))` in each `Index Cond` | 1.5–1.9 ms. **After `ANALYZE`**: a never-analysed table plans `Index Cond: (epoch = 1)` with term/block_no as a heap filter (estimated 2 rows, so the planner is right at that size). Autovacuum's analyse is what production sees; residue below. |
| MySQL 8.4.10 | `Index range scan … using PRIMARY over (epoch = 1 AND term = … AND block_no = 10) OR (epoch = 1 AND term = … AND block_no = 8) OR (2 more)` | 1.1 ms; the `IN` lists are unrolled into key tuples. |
| SQL Server 2022 | two `Clustered Index Seek` on the PK, each fed by a `Constant Scan` of its `IN` list, concatenated (`Merge Join / Concatenation`) | 17–33 ms first execution under Rosetta (prepare included). `SET SHOWPLAN_TEXT` returns nothing through the parameterised path; captured with `SET STATISTICS XML`. |
| Oracle 23 Free | `CONCATENATION` of `INDEX UNIQUE SCAN` (the one-block arm, full key access) and `INDEX RANGE SCAN` (access `epoch = :b AND term = :b`, filter on the three `block_no`) | dynamic sampling at this size; not timed. |

No engine plans the amended shape as an epoch scan with statistics in
place; sqlite needs the binds, Postgres needs the analyse.

**Gates.** `scripts/ci.sh 3.13`: 2,868 passed, 922 skipped, coverage
100.00 % (BEIR present locally). Full matrix 3.11–3.14 green
(2,865 / 2,865 / 2,868 / 2,867 passed; wheel under budget). Engine legs (Docker, concurrent): Postgres **225**, MySQL
**225**, SQL Server **225**, Oracle **222** — spec 131's 215/215/215/212
plus the ten glean rows on each, the ordered top-10 identical on all
six backends through the driver and through the verb.

**Residue.**

- The whole-list round-two case is not recorded (above); when the
  results vocabulary gains an informational kind, `_chunk_ranking`
  knows the condition (θ against the overflowing terms' summed
  maxima) and can emit it.
- Postgres plans the round-two statement as key seeks only once the
  postings table has statistics. A lexical build inserts a whole new
  epoch's rows; until autovacuum analyses them the planner may scan
  the epoch prefix. Direction: the build issues `ANALYZE` on the
  postings and summary tables after the swap, per dialect (Postgres
  and Oracle have the verb; MySQL's InnoDB stats are automatic;
  sqlite's `ANALYZE` would also rescue the literal-rendered shape).
  Not done here — a build-side change with its own measurement.
- The overlay scores whole entries, without chunk text (spec 133);
  min-max over the union makes scores comparable across mounts and
  meaningless in absolute terms (ADR 052's contract).
- `SCOPE_ID_BUDGET = 5,000` and `OVERLAY_BUDGET = 500` are declared,
  refereed constants, not measured optima; the ranking harness has no
  scoped queries yet to tune them against.
- `HANDOFF.md` (the in-session handoff) is deleted at archive; this
  note supersedes it.

**Commit shape.** Slice 0 stands alone (`select_blocks`, protocol 7:
the crate, the binding, the stub, `native.py`, `models/lexical.py`,
the oracle and its tests, the referee and the driver). The verb, the
surface and `scope.py` are one commit; conformance, the pin through
the verb, the harness arm and this note a third — or the last two
squashed.

