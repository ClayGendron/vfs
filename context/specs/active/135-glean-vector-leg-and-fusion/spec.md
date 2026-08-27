# 135 — the vector leg and fusion: dialect distance, exact-first tiers, the vector-leg client floor, and the client-side `Fusion` seam

- **Status:** ready — drafted 2026-08-26 from ADR 051 (pins 1, 2, 5,
  8, 9) and ADR 052 (pins 1, 3); **amended the same day under ADR
  055**: fusion is client-side on every engine (`Fusion.fuse` only —
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
