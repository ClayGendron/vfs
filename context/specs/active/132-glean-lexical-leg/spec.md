# 132 — glean, lexical-only: `SupportsGlean` on the database backend with the BM25 leg, predicate scope, MaxP, and the freshness overlay

- **Status:** ready — drafted 2026-08-26 from ADR 051 (pins 1, 6, 7)
  and ADR 052 (pins 2, 5, 7 minus previews). Third of the glean arc:
  the first working `glean`, lexical-only, so the verb exists and is
  measured before vectors arrive.
- **Born from:** ADRs 051, 052; memos
  `../../../research/2026-08-26-glean-in-the-engine.md` §1, §5, §6 and
  `../../../research/2026-08-26-glean-fusion-and-cross-mount-merge.md`
  §3.
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Kind:** new verb implementation in `DatabaseStorage` (a new
  `glean.py` beside `grep.py`); result-shape change on `Observation`
  usage (entries with top-K chunk `Match` rows); conformance rows.
- **Depends on:** spec 130 (the tables and stats export), spec 131 (the
  harness and pins), ADR 040's segment pushdown (`pathterms.py`,
  `segments.py`), grep's scan partition (`_entries_for_scan`) and
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

1. **The statement** (`glean.py`, one session, SELECTs only, the
   backend owns the transaction, `StaleSnapshot` redrive as grep): a
   chunk-scoring CTE over `lex_terms` — `SUM(weight) … WHERE epoch =
   :e AND term IN (:terms) GROUP BY chunk_id` — joined to `lex_docs`
   and `entries` for liveness (`deleted_at IS NULL`), `encoded`,
   `user_id` scoping and the **scope predicate**, aggregated **inside
   the leg** to entries (`MAX(score)` with `ROW_NUMBER() OVER
   (PARTITION BY entry_id ORDER BY score DESC, chunk_id) <= K` carrying
   the top-K chunks), ordered `score DESC, entry_id`, `LIMIT :n` on
   entries. Built with Core; the limit spelling is the dialect's.
2. **Scope is a predicate**: `paths=` takes the globs `grep` takes;
   the scope compiles through `pathterms`/`segments` as the segments
   join inside the leg — zero id binds. Piped `observations` compile
   as a **semi-join subquery** on entry ids (never a JOIN), chunked under
   `membership_budget` with a client-side merge of per-chunk leg top-k
   when the list exceeds one chunk.
3. **Query terms** go through spec 130's tokenizer; a **df ceiling**
   drops flooding terms with a warning-severity record naming them; an
   empty post-fold query classifies `invalid`; the term `IN`-list is
   bounded by the membership budget (a query has tens of terms).
4. **Freshness**: the index side joins `encoded`; the `NOT encoded` set
   (grep's scan partition) is scored client-side from live text with
   the epoch's `idf`/`avg_dl` (one `lex_df` probe), on the same scale,
   merged into the leg before aggregation, bounded by grep's candidate
   budget and deadline; one warning record names scanned / unconsulted
   / lexical-only counts.
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

- **A — the statement and scope**: `glean.py`, the leg CTE, MaxP/top-K,
  segments-join scope, observation semi-join, limit spelling; unit
  tests on sqlite plus the ordered-top-10 pin on every engine leg.
- **B — overlay and records**: the `NOT encoded` client-side scoring,
  budgets, the three warning records, the empty-query refusal.
- **C — surface**: `SupportsGlean` on `DatabaseStorage`, traits,
  conformance rows in `storage_contract.py` (scoped, piped, dirty-set,
  trashed-row exclusion, `user_id` scoping, entries-not-chunks), harness
  arm "lexical-only glean" with its numbers in the landing note.

## Landing criteria

- `scripts/ci.sh 3.13` green; 100 % coverage; engine legs green on all
  five real engines with the ordered-top-10 pin identical across them.
- Harness: lexical-only glean ≥ the BM25 baseline of spec 131 on all
  three corpora (it *is* that baseline through the statement — any gap
  is a bug).
- Ledger rows: scope inside the leg (a scoped call never returns an
  out-of-scope entry even when the candidate window truncates);
  overlay coverage (a written-but-unreindexed file is found).
