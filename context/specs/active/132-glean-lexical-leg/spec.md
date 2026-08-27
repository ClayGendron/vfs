# 132 — glean, lexical-only: `SupportsGlean` on the database backend with the block-posting BM25 leg, scope as candidate ids, the ladder, MaxP, and the freshness overlay

- **Status:** ready — drafted 2026-08-26 from ADR 051 (pins 6, 7) and
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
