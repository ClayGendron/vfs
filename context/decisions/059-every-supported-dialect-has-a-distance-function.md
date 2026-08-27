# 059. Every Supported Dialect Has a Distance Function: sqlite-vec Loaded by vfs, MySQL Community Dropped, Unknown Dialects Serve the Core Verbs Only

- **Status:** accepted 2026-08-27 — decided by Clay in session while
  spec 135 (the vector leg) was being built: "I no longer want to
  support dialects through vfs that do not have a distance function
  built in or available through an extension that we can ensure is
  installed … unknown dialects can do read/write/topology/glob/grep but
  not graph or glean. drop MySQL." **Amends ADR 051 pin 2 and ADR 055
  decision 6** (the "client floor" for MySQL and `GENERIC` is
  withdrawn), **amends ADR 040's unknown-dialect posture** and the
  CLAUDE.md line "unknown dialects are served, not refused" (they are
  served the core verbs, never the ranked ones), and refines ADR 057
  (the Rust cosine kernel built for the floor becomes the vector leg's
  referee).
- **Date:** 2026-08-27
- **Deciders:** Clay Gendron
- **Decided by:** human
- **Context source:** `context/research/studies/2026-08-26-glean/engine-matrix.md`
  §2–§4 (the per-engine distance facts and the floor benchmark); the
  sqlite-vec probe run in session (v0.1.9 loads under uv's CPython 3.13
  through `sqlite3.Connection.enable_load_extension`, and
  `vec_distance_cosine` scores the packed float32 blobs vfs stores).

## Context

Spec 135 was designed with two tiers for the vector leg: an in-engine
`ORDER BY distance LIMIT k` where the engine has a cosine function, and
a "client floor" — the scoped vectors fetched in pages and scored beside
the database — for MySQL community (a `VECTOR` type with no distance
function in the community edition and no installable extension: the
only path is a compiled server-side UDF plugin vfs cannot install),
SQLite (no vector type in core), and unknown dialects. The floor is
exact and its cost is linear in the scope; a Rust kernel was built for
it.

Clay's requirement is a different line: **a supported dialect supports
all of vfs**. A dialect without a distance function that vfs can
guarantee — native, or an extension vfs itself installs and loads — is
not a supported dialect for ranked search. Two consequences follow for
the engines at hand, and one for the doctrine.

## Options considered

- **SQLite**: keep the client floor (exact, in Rust, no dependency) vs
  **load sqlite-vec** — a loadable extension shipped as a PyPI wheel
  (MIT / Apache-2.0), adding `vec_distance_cosine` over plain BLOB
  columns holding packed float32 — vfs's stored format exactly — so the
  SQLite leg takes the same statement shape as the native engines.
  Chosen: vfs can ensure it is installed (a core dependency) and loaded
  (the connection hook that already stamps SQLite's settings), and
  first touch refuses loudly on an interpreter whose `sqlite3` cannot
  load extensions. It is brute force like the floor, but it keeps one
  code path.
- **MySQL community**: keep it on the floor vs **drop it**. Dropped:
  nothing vfs can install gives it a distance function. MariaDB 11.7+
  (native `VEC_DISTANCE_COSINE`, an MHNSW index) takes the family's
  seat: its tuned profile, the Docker leg, the driver extra (still
  aiomysql), the CI matrix entry. A `mysql://` URL still connects — as
  an unknown dialect.
- **Unknown dialects**: refuse at first touch vs serve on the floor vs
  **serve the core verbs and withhold the ranked ones**. Chosen: the
  `GENERIC` profile still serves read, write, the topology verbs, glob
  and grep exactly as before; `glean` (and `graph`, when it lands) are
  not in an unknown dialect's declared capabilities, because the floor
  cannot declare the one engine fact they need.

## Decision

1. **Every supported dialect has cosine in the engine**: pgvector's
   `<=>` on PostgreSQL, `VEC_DISTANCE_COSINE` on MariaDB,
   `VECTOR_DISTANCE('cosine', …)` on SQL Server 2025, `VECTOR_DISTANCE(…,
   COSINE)` on Oracle 23ai+, and `vec_distance_cosine` on SQLite through
   sqlite-vec. The `DialectProfile` declares it (`vector_distance ∈
   {exact, ann}` on every tuned profile; `none` only on `GENERIC`).
2. **sqlite-vec is a core dependency**, loaded on every SQLite
   connection by the engine host's connection hook beside the settings
   it already stamps, and probed at first touch (`vec_version()`); an
   interpreter that cannot load extensions refuses the mount as
   `unavailable` naming the fix. The SQLite vector leg is the in-engine
   statement over the packed BLOB column — no virtual table.
3. **MySQL community is not a supported dialect.** Its profile, Docker
   service, driver extra name and CI entry go; MariaDB carries the
   family's tuned policy under its own name and leg (`mariadb` marker,
   `VFS_TEST_MARIADB_URL`, host port 33062). The mysql-family type
   variants in `rows.py` stay: a MySQL URL is served as an unknown
   dialect and its keys and blobs still need them.
4. **Unknown dialects serve the core verbs and withhold `glean`** (and
   `graph`): `DatabaseStorage.capabilities()` subtracts the ranked verbs
   when the resolved profile declares no distance function. The router
   never routes to an undeclared verb, so an agent on such a mount is
   told so by the capability gate, never by a failing statement.
5. **There is no client floor.** The vector leg has one shape — an
   in-engine `ORDER BY <distance> LIMIT k` with the scope predicate
   inside — and only the distance expression varies per dialect. The
   Rust `cosine_topk` kernel built for the floor stays as the **referee**:
   the conformance suite fetches the scoped vectors, ranks them exactly
   in the engine, and pins every dialect's in-SQL order against it — the
   vector leg's twin of the lexical leg's pure-BM25 referee.

## Consequences

- **Easier:** one vector statement to reason about; identical rankings
  across dialects are pinned against one referee; no per-page scoring
  path to keep correct at 10⁵-row scopes; the MariaDB leg replaces the
  MySQL leg one-for-one (same driver, same family policy).
- **Harder:** a new core dependency (sqlite-vec, ~1 MB) and a
  connection hook with a first-touch probe; interpreters whose `sqlite3`
  lacks extension loading (some system Pythons) cannot mount SQLite —
  the refusal names it. MySQL community users lose a tuned profile: they
  are served the core verbs on the generic floor.
- **Committed to:** the capability set is dialect-aware and declared,
  never discovered by a failing statement; ranked search is never
  "approximately available".

Evidence: `context/research/studies/2026-08-27-sqlite-vectors/README.md`
(the executed sqlite-vec / vectorlite / Rust-kernel benchmark and the
platform-wheel survey that decided the extension: vectorlite's scalar is
~25 % faster but ships no Linux aarch64 wheel; Turso's vector search
needs the libSQL fork and its own driver); `engine-matrix.md` §2.3 (MySQL 9.7.2: `DISTANCE()` "available
only for users of MySQL HeatWave … not included in MySQL Commercial or
Community"; no index; the driver cannot decode the wire type), §2.6
(SQLite + sqlite-vec 0.1.9: `vec_distance_cosine` over a BLOB column,
`rowid IN` prefilter honoured), §4 (the floor's linear cost).
