# Portable vector search across SQL engines: the GENERIC floor for glean

- **Study for**: brief question 9 of
  [2026-07-25-multimodal-storage-and-search-brief.md](../../2026-07-25-multimodal-storage-and-search-brief.md)
- **Date**: 2026-07-25
- **Sources**: engine documentation (URLs), local `~/Git/Repos/sqlalchemy`
  (MIT, verified at `LICENSE`; checkout `abfe6cc`, version 2.1.0b3), and the
  vfs live tree. No copyleft repos were opened.

## Question

Every engine vfs targets shipped a vector type recently. What does each one
actually offer in 2026 — and when a mount lands on an engine with no native
vector support (or an unknown dialect), what is the conservative `GENERIC`
floor for `glean`'s vector leg, stated honestly with its scale ceiling?

---

## 1. Engine ground truth, 2026

### 1.1 PostgreSQL + pgvector — the reference implementation

pgvector 0.8.5 (PostgreSQL license) is the most complete story and the one
vfs already integrates (`src/vfs/models/vector.py:184-199` lazily imports
`pgvector.sqlalchemy.Vector` when `postgres_native=True`).

- **Types**: `vector` (float32, ≤16,000 dims), `halfvec` (float16, ≤16,000),
  `bit` (≤64,000), `sparsevec` (≤16,000 non-zero elements).
- **Indexes**: HNSW and IVFFlat. Indexing caps are tighter than storage:
  `vector`/`halfvec` index at **≤2,000 dims** (`bit` up to 64,000). A
  3,072-dim embedding column can be *stored* but not HNSW-indexed as
  `vector` — a real constraint on embedding-model choice.
- **Operator classes**: `vector_l2_ops`, `vector_ip_ops`,
  `vector_cosine_ops`, `vector_l1_ops`, `halfvec_*`, `bit_hamming_ops`,
  `bit_jaccard_ops`, `sparsevec_*`; operators `<->`, `<#>`, `<=>`, `<+>`,
  `<~>`, `<%>`. (https://github.com/pgvector/pgvector)
- **Iterative index scans** (0.8.0+): the ANN+WHERE-filter interaction fix —
  keep scanning the index until enough post-filter results exist
  (`hnsw.iterative_scan`). Its existence is evidence that *filtered* ANN is
  genuinely hard; note for §3 that the exact-scan floor gets this for free.
- **Exact search works with no index at all** — `ORDER BY embedding <=> $1
  LIMIT k` is a legal sequential scan.
- **SQLAlchemy**: not in core; via `pgvector-python` (MIT — safe dependency),
  which provides the SQLAlchemy type plus `l2_distance` /
  `cosine_distance` / `max_inner_product` / `l1_distance` /
  `hamming_distance` / `jaccard_distance` comparators.
  (https://github.com/pgvector/pgvector-python)

### 1.2 SQL Server 2025 (17.x) — native VECTOR, exact GA, ANN in preview

- **Type**: `VECTOR(n)`, float32 base, **max 1,998 dims**, GA. `float16`
  base is preview-gated (`PREVIEW_FEATURES = ON`).
- **Search**: `VECTOR_DISTANCE` (cosine/euclidean/dot) is **GA** — exact
  KNN via `ORDER BY VECTOR_DISTANCE(...)` works today. `VECTOR_SEARCH` +
  `CREATE VECTOR INDEX` (DiskANN, SSD-resident graph, ~0.95 recall) are
  **preview-gated** in SQL Server 2025; the type/functions went GA in Azure
  SQL first.
  (https://learn.microsoft.com/en-us/sql/t-sql/data-types/vector-data-type?view=sql-server-ver17,
  https://devblogs.microsoft.com/azure-sql/announcing-general-availability-of-native-vector-type-functions-in-azure-sql/)
- **Wire format — the key fact for vfs**: vectors are stored binary but
  *exposed as JSON arrays*. Only new TDS-aware drivers
  (Microsoft.Data.SqlClient 6.1+, JDBC 13.1+) get binary transport; for
  everyone else — **including pyodbc, which has no native vector support** —
  the server presents `varchar(max)` JSON and implicitly converts on
  insert. vfs's JSON-text serialization
  (`src/vfs/models/vector.py:226`) is therefore *literally the documented
  client protocol* for SQL Server vectors, not merely a fallback.
- **Restrictions**: no B-tree/columnstore on vector columns, no equality or
  key constraints, no vector math operators outside the built-ins.

### 1.3 Oracle 23ai/26ai — the most complete native story, modeled by SQLAlchemy

- **Type**: `VECTOR(n, format)` — formats FLOAT32/FLOAT64/INT8 (23.4+) and
  BINARY (23.5+, packed sign bits, dims multiple of 8); DENSE and SPARSE;
  **max 65,535 dims** (65,528 for BINARY).
  (https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/create-tables-using-vector-data-type.html)
- **Indexes**: HNSW (in-memory Vector Pool) and IVF (partition-based,
  RAC-capable). Exact search is the default; ANN is opt-in per query:
  `FETCH APPROX FIRST k ROWS ONLY WITH TARGET ACCURACY 90` — accuracy is a
  *query-time contract*, a design worth remembering for glean's Result
  honesty. (https://blogs.oracle.com/database/using-hnsw-vector-indexes-in-ai-vector-search)
- **SQLAlchemy**: **native in-tree support since 2.0.41** —
  `sqlalchemy/lib/sqlalchemy/dialects/oracle/vector.py:235-366` defines
  `VECTOR` with `l2_distance`/`inner_product`/`cosine_distance` comparators
  (`<->`, `<#>`, `<=>` — deliberately pgvector-compatible operator
  spellings), `VectorIndexConfig` for HNSW/IVF DDL
  (`vector.py:121-199`), `VectorStorageFormat`, and `SparseVector`
  (2.0.43+). Binding is `array.array`, not JSON — so a future
  `oracle_native=True` in `VectorType` would follow the exact
  `postgres_native` pattern with zero new dependencies.

### 1.4 MySQL 9.x — a type without a search function (community edition)

The sharpest finding of the survey, and it lands on an engine vfs's
conformance suite actually runs:

- **Type**: `VECTOR(n)` exists in community MySQL 9.0+ (little-endian
  float32 binary; default 2,048 dims, max 16,383).
- **Functions in community**: `STRING_TO_VECTOR`/`TO_VECTOR`,
  `VECTOR_TO_STRING`/`FROM_VECTOR`, `VECTOR_DIM` — conversion and
  inspection only. **`DISTANCE()`/`VECTOR_DISTANCE()` is available only on
  MySQL HeatWave on OCI and MySQL AI; it is not in Commercial or Community
  distributions**, and community has no ANN index of any kind.
  (https://dev.mysql.com/doc/refman/9.7/en/vector-functions.html)
- Consequence: on stock MySQL there is **no server-side way to compute a
  vector distance at all**. The native `VECTOR` type buys nothing for
  search — every distance runs client-side. The GENERIC floor is not a
  hypothetical for unknown dialects; it is the *only* MySQL story.
- **SQLAlchemy**: no MySQL vector type in 2.1.0b3 (grep of
  `lib/sqlalchemy/dialects/mysql/` finds nothing), consistent with there
  being nothing to model.

### 1.5 SQLite — no built-in; sqlite-vec is permissive but is an extension

- `sqlite-vec` (dual **MIT OR Apache-2.0** — license-safe) provides the
  `vec0` virtual table: float/int8/bit vectors, metadata and partition-key
  columns, KNN via `MATCH ... ORDER BY distance`. Search is **brute force**
  ("fast enough" by its own description; DiskANN/IVF appear only as
  in-progress source references). (https://github.com/asg017/sqlite-vec,
  https://alexgarcia.xyz/blog/2024/sqlite-vec-stable-release/index.html)
- Benchmarked (vectorlite's comparison): 100k vectors, average KNN query —
  float 1,536-dim ≈ 105 ms, 3,072-dim ≈ 214 ms, ≤1,024-dim < 75 ms; **bit
  vectors: 3,072-dim in ≈ 11 ms**. A C-speed measurement of what exact scan
  costs at 100k when serialization is binary, and a preview of the
  sign-bit trick in §3.3.
  (https://1yefuwang1.github.io/vectorlite/markdown/news.html)
- It is a *loadable extension*: the GENERIC floor cannot assume it, but a
  `sqlite_native`-style opt-in (mirroring `postgres_native`) is
  license-clean if ever wanted.

### 1.6 SQLAlchemy support matrix (2.1.0b3, local checkout)

| Engine | Native type in SQLAlchemy | Distance comparators | Index DDL |
|---|---|---|---|
| Oracle | yes, in-tree (2.0.41+) — `dialects/oracle/vector.py` | yes (`vector.py:358-366`) | yes (`VectorIndexConfig`) |
| Postgres | via `pgvector-python` (MIT) | yes | via extension |
| SQL Server | **none** | none | none |
| MySQL | none (nothing to model in community) | n/a | n/a |
| SQLite | none (extension territory) | n/a | n/a |

The `TypeDecorator.load_dialect_impl` pattern vfs already uses
(`src/vfs/models/vector.py:184-187`) extends cleanly: Postgres and Oracle
can each get a native branch; SQL Server's "native" branch *is* the JSON
path plus a server-side `CAST(? AS VECTOR(n))` and `VECTOR_DISTANCE` in
queries; MySQL and GENERIC stay on the floor.

---

## 2. When does brute force stop being honest? Published numbers

The literature's numbers are for **in-memory SIMD scans** — the best case:

- FAISS Flat, 10M × 768-dim, single query: **p95 ≈ 44.7 ms** (vs HNSW
  0.42 ms). (https://markaicode.com/benchmarks/faiss-production-benchmark-latency/)
- Rule-of-thumb estimates: 1M × 768 ≈ 768M multiply-adds ≈ **15–75 ms** with
  SIMD; at 10M × 768, real-world brute force lands **0.5–2 s**.
  (https://endee.io/blog/what-is-hnsw-and-why-is-it-so-fast,
  https://mbrenndoerfer.com/writing/vector-similarity-search-metrics-ann-faiss)
- Practitioner consensus: flat/exact is "usable" up to **~1M vectors**,
  and past ~5M you are in ANN territory regardless of hardware.
  (https://bigdataboutique.com/blog/scaling-vector-search-performance-from-millions-to-billions-8d50a1)
- sqlite-vec (C, binary storage, no SQL wire cost): 100k × 1,536 ≈ 105 ms
  (§1.5).

**The vfs floor is not that machine.** `VectorType`'s portable path stores
JSON text in a `Text` column (`src/vfs/models/vector.py:226`); a floor scan
pays, per query: (a) SQL fetch of every candidate row's vector, (b)
`json.loads` per row, (c) scoring. The arithmetic (stated assumptions:
768-dim, ~12 bytes per serialized float, `json.loads` of a 9 KB array
≈ 30–60 µs, driver throughput on the order of 100 MB/s):

| Corpus in scope | JSON wire size | Parse cost | Realistic total |
|---|---|---|---|
| 1,000 | ~9 MB | ~0.05 s | well under 0.5 s |
| 10,000 | ~92 MB | ~0.3–0.6 s | **~1–2 s** |
| 100,000 | ~920 MB | ~3–6 s | tens of seconds; memory pressure |

Data motion, not arithmetic, is the binding cost — the distance math on 10k
parsed vectors is single-digit milliseconds in numpy. Three consequences:

1. **The JSON-text floor is honest to ~10k vectors per query scope**
   (interactive, ~1–2 s), tolerable for batch to ~100k, and dishonest
   beyond.
2. **Serialization is the cheapest 3–4× win.** Packed little-endian float32
   (`array("f").tobytes()` in a `LargeBinary` column) is 3 KB vs ~9 KB per
   768-dim vector, parses in ~1–2 µs vs 30–60 µs, and is what MySQL's own
   `VECTOR` and SQL Server's internal format already are. Fully portable;
   endianness declared once. This moves the interactive ceiling to
   **~30–50k** without any cleverness.
3. **Caching changes the regime.** If the score matrix stays in process
   memory (keyed by mount + embedding space + a version watermark), repeat
   queries cost FAISS-flat-like milliseconds up to ~1M vectors; the fetch
   cost is paid on first touch and invalidation. That is a design decision
   about memory ownership, not a storage-schema question — flagged, not
   settled, here.

---

## 3. Candidate narrowing without native ANN

Patterns that keep a floor scan honest at larger scales, ordered by how
much they preserve the repo's existing candidate doctrine.

### 3.1 Scope prefilter (lossless — do this first, always)

vfs is a filesystem: `glean(paths=...)` already scopes queries
(`src/vfs/storage/protocol.py:198-206`). Path-subtree, mime, and mount
predicates are exact B-tree work that shrinks the scanned set *before* any
vector is fetched. This turns the corpus-size ceiling into a
**scope-size ceiling** — a 10M-file mount whose query scopes stay under
~30k vectors never leaves the honest regime. Note the inversion versus
native ANN: pgvector needed iterative scans (§1.1) and SQL Server's
DiskANN documents filter interactions precisely because *filter-then-ANN*
is hard; *filter-then-exact* at the floor has zero recall loss and simpler
semantics. The floor's weakness is scale, never correctness.

### 3.2 IVF in plain SQL (lossy, portable, operationally heavy)

Prior art: Davide Mauri's Azure SQL KMeans pattern, built when Azure SQL
had no vector type — an external k-means job writes centroids and a
`cluster_id` int column back to SQL; queries find the nearest few
centroids in the client, then scan only those clusters via an ordinary
B-tree index (`WHERE cluster_id IN (...)` — which composes with vfs's
`membership_budget` chunking,
`src/vfs/storage/backends/database/dialects.py:229-237`).
(https://devblogs.microsoft.com/azure-sql/vector-search-optimization-via-kmeans-voronoi-cells-and-inverted-file-index-aka-cell-probing/,
https://github.com/Azure-Samples/azure-sql-db-vectors-kmeans)
Oracle's IVF index is this exact shape done natively. It works on every
engine, cuts scanned rows by 10–100×, but brings recall loss (governed by
probe count), an offline clustering job, and centroid drift as the corpus
mutates — real lifecycle machinery. Verdict: a documented *upgrade path*
above the floor, not the floor.

### 3.3 Binary sign quantization + exact rescore (lossy-but-bounded, cheap)

Store one extra sidecar per vector: the packed sign bits (768 dims =
96 bytes — ~100× smaller than the JSON). Floor query: fetch only the bit
column for the scope, Hamming-rank in Python (`int.bit_count()` on 96-byte
ints is fast; sqlite-vec's C version does 100k × 3,072-dim in 11 ms, §1.5),
keep an oversampled top (k × 20–50), fetch full floats for only those, and
rescore exactly. Both pgvector (`bit` + `bit_hamming_ops` + rerank) and
Oracle (BINARY format) ship this as a first-class pattern, which is decent
evidence for its recall behavior at modern embedding dimensions. This
raises the honest interactive ceiling to the **~500k–1M** range while
staying pure-portable SQL (one `LargeBinary` column, equality-free
predicates, all ranking client-side).

### 3.4 The gram-planner analogy — and where it breaks

The repo's candidate doctrine is `code_grams`: candidates "may admit false
positives but must never introduce false negatives — the authoritative
match is always run in Python afterward"
(`src/vfs/models/code_grams.py:8-10`). The vector floor *matches* the
second half (exact Python rescore is the authoritative match) but can only
match the first half for §3.1: every other narrowing (IVF probes, Hamming
prefilter, dimension truncation) **can drop true neighbors** — recall < 1
is intrinsic, not a bug. Grep-style grams have no vector analogue because
substring containment is decomposable and cosine proximity is not. Any
floor design that narrows beyond exact predicates must therefore *declare*
its recall posture rather than inherit grep's "no false negatives"
promise. (LSH banding is the honest name for gram-style vector candidates;
it needs many hash tables for good recall and is strictly worse than §3.3
at these dimensions — noted and rejected.)

---

## 4. The GENERIC floor, stated

Following the dialect doctrine (unknown engines are served at a
conservative floor, never refused — `dialects.py:155-182`), the vector
floor that survives this survey:

> **GENERIC floor**: vectors stored in a portable column (today JSON text;
> packed float32 bytes recommended), scoped by exact predicates first
> (§3.1), then **exhaustively scanned and exactly scored client-side**.
> Recall is 1.0 by construction. The honest ceiling is a *per-query-scope*
> vector count: **~10k interactive today (JSON), ~30–50k with binary
> packing**; beyond that the floor still serves, degrading in latency,
> never in correctness — and the Result should be able to say so
> (Oracle's `TARGET ACCURACY` and the brief's degradation posture both
> point at surfacing search quality/cost in the result, not hiding it).

Above the floor, three upgrade tiers, each opt-in per dialect and none
required for correctness: (1) **server-side exact KNN** where a distance
function exists with no index needed — pgvector unindexed, Oracle
`VECTOR_DISTANCE` exact, SQL Server `VECTOR_DISTANCE` GA via plain pyodbc
JSON binding; (2) **native ANN** where indexes exist — pgvector
HNSW/IVFFlat (shipped in `NativeEmbeddingConfig`,
`src/vfs/models/vector.py:48-62`), Oracle HNSW/IVF via SQLAlchemy's
in-tree `VectorIndexConfig`, SQL Server DiskANN once out of preview;
(3) **portable narrowing** (§3.3, then §3.2) for engines stuck at the
floor at scale — with MySQL community as the permanent, named resident of
that tier.

Two engine-cap facts should become declared knowledge wherever vector
config lives (the `DialectProfile` precedent: declare only what the
library doesn't model, `dialects.py:38-69`): the **dimension caps**
(pgvector index 2,000 / SQL Server 1,998 / MySQL 16,383 / Oracle 65,535)
and the **distance-function availability** per engine — both are facts
SQLAlchemy takes no position on for three of the five engines.
