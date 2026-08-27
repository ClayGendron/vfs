# SQLite cosine top-10 over a BLOB column: sqlite-vec, vectorlite, the Rust kernel

- **Study for**: ADR 059 (every supported dialect has a distance function) — which
  loadable extension gives SQLite its cosine, and whether the choice is clear.
- **Date**: 2026-08-27
- **Method**: `bench_sqlite_vectors.py` (beside this file; run with
  `uv run --with vectorlite-py python bench_sqlite_vectors.py <out dir>`). One table
  `(id INTEGER PRIMARY KEY, v BLOB)` of N unit vectors of D float32 packed
  little-endian — vfs's stored format — on an Apple M1 Pro, CPython 3.13.11,
  SQLite 3.50.4. Each arm answers the ten nearest ids by cosine to one query,
  best of three after a warm-up; the three answers are checked equal.
- **Arms**: sqlite-vec 0.1.9 `ORDER BY vec_distance_cosine(v, ?) LIMIT 10`;
  vectorlite-py 0.2.0 `ORDER BY vector_distance(v, ?, 'cosine') LIMIT 10` (its
  scalar; its HNSW virtual table is in-memory per connection with manual
  save/load and no source-table sync, so it was not a candidate); the Rust
  `cosine_topk` kernel over every row fetched (`SELECT id, v`).
- **Sources**: sqlite-vec clone `~/Git/Repos/sqlite-vec` @ 04d28bd
  (v0.1.10-alpha.4, 2026-05-17, MIT / Apache-2.0); PyPI `sqlite-vec` 0.1.9
  (2026-03-31; wheels: macOS arm64 + x86_64, manylinux x86_64 + aarch64, Windows
  x64; no musl, no sdist); vectorlite README (wheels: Windows x64, Linux x64,
  macOS x64 + arm64 — **no Linux aarch64**); Turso "native vector search"
  post and `libsql-sqlalchemy` (requires the libSQL fork of the library and its
  own driver; Linux/macOS only; vector feature in beta).

| N rows | dims | sqlite-vec | vectorlite scalar | fetch + Rust kernel | agree |
|---|---|---|---|---|---|
| 10,000 | 64 | 3.4 ms | 2.5 ms | 5.5 ms | yes |
| 10,000 | 256 | 6.7 ms | 5.0 ms | 7.6 ms | yes |
| 10,000 | 1536 | 34.3 ms | 26.2 ms | 30.3 ms | yes |
| 100,000 | 64 | 26.2 ms | 19.7 ms | 44.7 ms | yes |
| 100,000 | 256 | 72.5 ms | 53.9 ms | 79.7 ms | yes |
| 100,000 | 1536 | 338.0 ms | 251.3 ms | 279.2 ms | yes |

Reading: every arm is brute force and linear in the scope; vectorlite's
scalar is ~25 % faster than sqlite-vec's and the Rust path sits in the same
band (the fetch dominates it). The 25 % buys no different algorithm, and
vectorlite ships no Linux aarch64 wheel — disqualifying for a core dependency
that must install wherever vfs's own wheel does. **sqlite-vec is the choice**;
SQLite's honest vector profile is tens of milliseconds per 100k-chunk scope at
common widths and ~0.3 s at 1536 dimensions, with no ANN tier.
