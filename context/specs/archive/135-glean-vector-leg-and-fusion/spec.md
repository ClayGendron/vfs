# 135 — the vector leg and fusion: dialect distance, exact-first tiers, the vector-leg client floor, and the client-side `Fusion` seam

- **Status:** landed 2026-08-27 (landing note below; **amended under
  ADR 059 while landing**: there is no client floor — every supported
  dialect has cosine in the engine, SQLite through sqlite-vec, MySQL
  community is dropped, unknown dialects withhold `glean`) — drafted
  2026-08-26 from ADR 051 (pins 1, 2, 5, 8, 9) and ADR 052 (pins 1,
  3); **amended the same day under ADR 055**: fusion is client-side on every engine (`Fusion.fuse` only —
  `to_sql` is dropped), the vector leg keeps its in-engine statement
  and tiers, and the "client floor" is no longer a MySQL/`GENERIC`
  special case for the lexical side but the one path. Sixth of the
  glean arc: turns spec 132's lexical glean into the fused verb.
- **Born from:** ADRs 051, 052; memos
  `../../../research/2026-08-26-glean-in-the-engine.md` §1, §2, §4, §7,
  §8 and `../../../research/2026-08-26-glean-fusion-and-cross-mount-merge.md`
  §2; study `engine-matrix.md` (the verified statement, the tier plans,
  the floor benchmark).
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Re-read under ADR 057 decision 4 (2026-08-27):** `Fusion.fuse`
  over two short arrays is plain Python, not numpy; the MySQL /
  `GENERIC` client-floor cosine over `membership_budget` batches is a
  measured-scale kernel candidate — its own slice in `crates/vfs-core`,
  `bytes in, top-K out`, with its own measurement. No numpy enters
  this spec.
- **Kind:** statement extension, a `Fusion` protocol with `Convex` and
  `RRF` built-ins, a dialect distance factory, two `UserDefinedType`s,
  declared `DialectProfile` facts, Docker-leg image bumps.
- **Depends on:** spec 132 (the statement), spec 134 (vectors and the
  query embedder), `dialects.py` (`DialectProfile`), `VectorType`.
- **Relates to:** spec 136 (adds the `signals` join to the same
  statement), spec 137 (uses `Fusion.fuse` at the router).

## Intent

Fuse the vector and lexical legs inside the engine on Postgres,
MariaDB, SQL Server, Oracle and SQLite — verified to produce identical
rankings — and fall to a client floor on MySQL community and `GENERIC`,
with the same `Fusion` object doing both. Scope-first exact is the
default; ANN is an accelerator the planner may or may not use, and the
answer says which tier served.

## Decided semantics

1. **`Fusion` protocol** (`src/vfs/storage/ranking.py`):
   `fuse(legs, signals) -> RankedList` over per-leg ranked lists —
   the vector leg's top-K from its in-engine statement, the lexical
   leg's top-K from the scorer (spec 132). `Convex(weights={"vector":
   0.5, "lexical": 0.5})` is the reference: cosine normalised by
   `(cos + 1)/2`, BM25 by min-max over the leg's candidate union, fused
   as one arithmetic expression in Python (numpy over two short
   arrays; a Rust `fuse` is not warranted). `RRF(k=10)` is the
   rank-only floor with per-leg k and weights. There is no `to_sql`:
   ADR 055 amended ADR 051 pin 1 to the vector leg alone. Declared on
   the Storage (`ranker=`; the full `Ranker` object arrives in spec 136
   — here it carries `fusion` and `aggregate` only).
2. **The vector leg**: a statement `ORDER BY <DIST(c.embedding, :q)>
   LIMIT :kv` with the scope predicate and `embedding IS NOT NULL`
   inside, ranked above the limited leg (never a window inside it,
   which defeats an index scan), aggregated to entries inside the leg
   (MaxP in SQL — the vector leg is the one leg that still scores in
   the engine). Per-leg depth `max(10 × limit, 100)`. The scope
   predicate is the same id-resolving statement spec 132 compiles for
   the lexical leg, spelled as a semi-join here.
3. **Dialect distance factory** keyed by dialect: pgvector `<=>` via
   pgvector-python; Oracle in-tree `VECTOR` comparators; `func.vector_distance('cosine', a, b)`
   on SQL Server; `func.vec_distance_cosine(a, func.vec_fromtext(q))` on
   MariaDB; `func.vec_distance_cosine` on SQLite with sqlite-vec loaded
   on `connect` behind a `sqlite_native`-style opt-in, else the client
   floor; **no expression** for MySQL and `GENERIC`.
4. **Native types**: two `UserDefinedType`s selected from
   `VectorType.load_dialect_impl` — SQL Server `VECTOR(n)` (JSON text
   over pyodbc) and MariaDB `VECTOR(n)` (`VEC_FromText`/`VEC_ToText`) —
   on the `postgres_native` pattern; MySQL stays on the packed
   `LargeBinary` column.
5. **Tiers and honesty**: native exact/ANN where a distance function
   exists; ANN only where the planner will use it — unscoped on MariaDB
   and Oracle, Postgres with `SET LOCAL hnsw.iterative_scan =
   relaxed_order` where pgvector ≥ 0.8; SQL Server's `VECTOR_SEARCH` /
   DiskANN never used (read-only table). The **client floor for the
   vector leg** (MySQL, `GENERIC`, opted-out SQLite): `SELECT id,
   entry_id, embedding FROM chunks WHERE <scope> AND embedding IS NOT
   NULL` fetched in `membership_budget` batches, scored in numpy with a
   running top-K. Fusion is `Fusion.fuse` on every engine (ADR 055), so
   the floor differs from the native tiers only in how the vector list
   is produced.
   Every answer records the tier per leg (`native_ann | native_exact |
   client_floor`), inferred from configuration (index present + no
   scope) — fork E6's cheaper choice; plan-reading is a later refinement.
6. **Declared `DialectProfile` facts**: `vector_distance ∈ {none, exact,
   ann}` (Postgres after a first-touch extension probe),
   `vector_dimension_cap`, `ann_honours_scope`. Over-cap spaces store
   but refuse the native tier with a classified first-touch error.
7. **Unembedded rows** are simply absent from the vector leg; the
   lexical-only count from spec 132's overlay record now also covers
   them; a mount with no provider or a `conflict`ed identity serves
   `Convex` over the lexical leg alone (a one-leg convex is the leg
   itself).
8. **Docker legs**: `pgvector/pgvector:pg17`, `mariadb:11.8`, `mysql:9`,
   `mcr.microsoft.com/mssql/server:2025-latest` with a small Dockerfile
   installing `mssql-server-fts` and creating a user database, and the
   regular `gvenzl/oracle-free:23` image for the Oracle leg (with
   `vector_memory_size` set at the CDB root); `docker/README.md` and the
   `db_test` skill updated.

## Scope

In: the protocol and two fusions, the vector CTE, the distance factory,
the two native types, tiers and the floor, the dialect facts, the
records, the image bumps, harness arms. Out: signals (136), the
router merge (137), ANN index DDL beyond what `NativeEmbeddingConfig`
already scaffolds (a later spec if a scope ever exceeds the floor),
lossy narrowing (unbuilt by decision).

## Slices

- **A — `Fusion`, `Convex`, `RRF`**: the protocol and `fuse`, unit pins
  on fixtures (the convex reference against a hand-computed fusion;
  RRF against its definition; determinism with the rounding-before-order
  law).
- **B — the vector leg and dialect factory**: the statement, distance
  expressions, native types, `DialectProfile` facts, the sqlite-vec
  opt-in; the ordered-top-10 pin becomes the *fused* pin on all five
  engines (identical rankings now follow from one client fusion over
  legs whose own rankings are pinned).
- **C — the floor and tier records**: MySQL/`GENERIC` path, numpy
  scoring in batches, tier records, unembedded handling; the compose
  bumps and skill/doc updates; harness arms (vector-only, fused) with
  the sweep numbers in the landing note.

## Landing criteria

- `scripts/ci.sh 3.13` green; engine legs green on the bumped images
  with the fused ordered-top-10 pin identical across Postgres, MariaDB,
  SQL Server, Oracle, SQLite, and the floor pin on MySQL matching them.
- Harness: fused ≥ lexical-only on all three corpora; α = 0.5 recorded;
  the 0.005 gate holds.
- Ledger rows: a scoped call on MariaDB/Oracle never reads the ANN
  index (tier record `native_exact`); a MySQL floor call never issues a
  distance expression; over-cap dimension refuses at first touch.

## Landing note (2026-08-27)

`glean` is hybrid. Landed together with spec 134 and ADR 059 (decided
mid-landing by Clay: a supported dialect supports all of vfs).

**Landed**

- **`vfs.storage.ranking`** (new): the `Fusion` protocol (`fuse(legs)`),
  `Convex(weights)` — the reference, weights renormalised over the legs
  present so a one-leg mount ranks exactly as that leg — `RRF(k=10,
  weights)` as the rank-only floor, `MaxP(chunks_per_entry=3)`, and
  `Ranker(fusion=, aggregate=)` declared on the Storage (`ranker=`).
  `unit_cosine` and `min_max` are the one definition of each leg's
  normalisation. All value-identity, hashable, plain Python.
- **The vector leg** (`glean._vector_leg`): one statement shape on
  every supported dialect — the chunk table joined to its entry,
  `embedding IS NOT NULL`, `chunked`, liveness, kind and the scope
  pushdown inside, `ORDER BY <cosine distance>, chunk id LIMIT
  max(10 × limit, 100)` — with only the distance spelling varying
  (`distance.cosine_distance`: pgvector `<=>`, MariaDB
  `VEC_DISTANCE_COSINE`, SQL Server `VECTOR_DISTANCE('cosine', …,
  CAST(:q AS VECTOR(n)))`, Oracle `VECTOR_DISTANCE(…, COSINE)`, SQLite
  `vec_distance_cosine` through sqlite-vec). The query binds through
  the column's own `VectorType`, so the type does the per-dialect wire
  conversion. The ladder is the lexical leg's: an allow-list ≤ 5,000
  entries runs the statement per id chunk and merges the lists
  client-side; a wide scope fetches, gates with `passes_gates`, and
  deepens once by `PROBE_DEEPEN`. MaxP to entries; the top chunks of
  either leg ride as `Match` rows.
- **Fusion** (`glean._fuse`): each leg aggregated to entries and
  normalised by its own law (cosine `(cos + 1)/2`; BM25 min-max over
  the lexical union, chunks on the entries' range), the mount's fusion
  over entries and, keyed `(entry, chunk)`, over chunks; the fused
  scores min-max scaled to the unit interval, rounded to nine
  decimals, ordered `score DESC, path ASC` — a lexical-only mount ranks
  byte-identically to spec 132.
- **Native columns everywhere they exist** (`VectorType(native=True)`
  now follows the embedder's width automatically): pgvector's
  `vector(n)` (+ HNSW within 2,000 dims), Oracle's in-tree `VECTOR(n,
  FLOAT32)` (`array('f')` on the wire), and two column-spec
  `UserDefinedType`s in `vector_native.py` — SQL Server `VECTOR(n)`
  (JSON text) and MariaDB `VECTOR(n)` (the packed float32 bytes
  MariaDB stores natively). SQLite keeps the packed BLOB.
- **sqlite-vec** (ADR 059): a core dependency, located by path (its
  Python package imports numpy when present, so vfs never imports it),
  loaded at every pool checkout through the aiosqlite worker's own
  coroutines (`await_only`, the adapter's `create_function` pattern; a
  `vec_version()` probe skips connections that already carry it, so
  borrowed pools work), and probed at first touch — an interpreter
  without `enable_load_extension` refuses the mount as `unavailable`
  naming the fix.
- **Declared dialect facts**: `vector_distance ∈ {exact, ann}` on
  every tuned profile (`none` only on `GENERIC`), `vector_dimension_cap`,
  `ann_dimension_cap` (pgvector 2,000), `ann_honours_scope` (pgvector
  only). `DatabaseStorage.capabilities()` withholds `glean` when the
  profile declares no distance; **MySQL community is dropped** — the
  `MARIADB` profile carries the family's policy, the Docker leg, the
  `mariadb` extra/marker/`VFS_TEST_MARIADB_URL` and the CI entry
  replace MySQL's, and a `mysql://` URL is served as an unknown dialect.
- **Tiers and records**: the tier is inferred from configuration —
  `native_ann` where the profile declares `ann`, the mount provisions
  an index (pgvector within its cap) and the scope does not defeat it
  (`ann_honours_scope`), with `SET LOCAL hnsw.iterative_scan =
  relaxed_order` as the statement's prelude when pgvector ≥ 0.8 (the
  version read at first touch); `native_exact` otherwise. The answer's
  `legs` extra names the lexical hits and terms, the vector tier, model,
  depth and hits, and the fusion. A mount with no embedder: an `info`
  `unavailable` record; a stale space: a `conflict` warning; a provider
  failing to embed the query (under `glean_wall_seconds`): a retryable
  warning — the lexical leg alone answers in every case. The query
  vector is memoised per space (`QUERY_VECTOR_CACHE = 256`). Traits:
  `glean_signals = "hybrid"` with an embedder.
- **The referee**: the Rust `cosine_topk` kernel (bit-reproducible
  float32 dot products, `score DESC, id ASC`, rayon above 4,096 rows;
  protocol 7 → 8; pure-Python oracle in `tests/support/oracles/vectors.py`)
  pins the engine's order: `tests/storage/database/test_vector_leg.py::TestReferee`
  on sqlite-vec, and the hybrid ordered-top-10 pin
  (`tests/fixtures/ranking/vfs_native/top10_hybrid.json`, recorded on
  sqlite with the 64-d hashing embedder) asserted through the verb on
  memory, sqlite and every server leg.
- **Docker legs**: `pgvector/pgvector:pg17`, `mariadb:11.8`,
  `mcr.microsoft.com/mssql/server:2025-latest`, `gvenzl/oracle-free:23-slim`;
  `docker/README.md`, the `db_test` skill and the CI matrix updated.
- **Harness**: `TestHybridArms` records `vector/{hash,potion}` and
  `fused/{hash,potion}` on vfs-native (potion when cached):

  | arm | nDCG@10 | MRR@10 | recall@10 | recall@50 |
  |---|---|---|---|---|
  | bm25 / glean (lexical) | 0.7589 | 0.9833 | 0.4134 | 0.7852 |
  | vector/hash | 0.3150 | 0.6540 | 0.1394 | 0.4907 |
  | **fused/hash** (α = 0.5) | **0.7692** | 0.9833 | 0.4159 | 0.7668 |
  | vector/potion | 0.5765 | 0.8757 | 0.2576 | 0.6601 |
  | **fused/potion** (α = 0.5) | **0.7809** | 0.9833 | 0.4220 | 0.8003 |

  Fused ≥ lexical-only on the golden set for both embedders at the
  untuned α = 0.5 (+0.010 and +0.022 nDCG@10); the BEIR pair's hybrid
  arms are not recorded (the pair is fetched outside the repo and the
  `slow` arms were not run in this landing).

**Deviations from the spec, all deliberate**

- *No client floor, no sqlite-vec opt-in, no MySQL*: ADR 059.
- *MaxP runs client-side, not in SQL*: the chunk list is needed for
  the `Match` rows either way; fetching top-k chunks and folding them
  to entries beside the lexical leg keeps one aggregation code path.
- *Over-cap widths*: pgvector's index cap is honoured by skipping the
  index (an exact scan), never by refusing; the storage caps are
  declared facts not yet enforced at first touch (no provider ships a
  width past 16,000).
- *The tier is inferred, never read from a plan* (fork E6, as the spec
  allowed); MariaDB and Oracle provision no ANN index yet, so they
  answer `native_exact`.

**Measurements**

- Embed-step throughput (spec 134's landing criterion), a 3,975-file
  linux sample of `.c`/`.h` files → 18,350 chunks, sqlite, Apple M1
  Pro, after a lexical-only reindex (4.1 s): the hashing provider
  **3,425 chunks/s** (5.4 s, 9 requests of 2,048 inputs, 72 cached by
  hash), potion-base-8M **3,301 chunks/s** (5.6 s). The two are within
  4 % of each other while the providers themselves run at 9,777 and
  5,212 chunks/s in the study, so on sqlite the step is bound by the
  per-row write-back (aiosqlite's executemany is a statement per row
  on the worker thread), not by the embedder — a recorded
  suboptimality; a multi-row `VALUES`-join update where the profile
  proves it is the future direction, never a cap.
- SQLite's vector leg: sqlite-vec `ORDER BY vec_distance_cosine LIMIT
  10` over 100k rows — 26 ms at 64 dims, 73 ms at 256, 338 ms at 1536
  (`context/research/studies/2026-08-27-sqlite-vectors/`).

**Gates** — `scripts/ci.sh 3.13`: lint, format, types, the wheel
budget and the suite at 100 % coverage (3,035 passed, 938 skipped);
the engine legs on the bumped images, every one carrying the hashing
embedder and the hybrid ordered-top-10 pin: Postgres 229, MariaDB
221, SQL Server 2025 229, Oracle 226 passed. Two engine truths surfaced
on the legs and are fixed: asyncpg's binary `COPY` has no codec for a
`vector` column (carried vectors now land by `UPDATE`, never through
the bulk insert), and MariaDB 11.8's snapshot isolation raises errno
1020 ("record has changed since last read") and rolls the transaction
back — now a retryable driver code, with an unwinding error (the
savepoint's 1305) classified by the transient cause behind it.
