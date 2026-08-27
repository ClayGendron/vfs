# ULID vs integer surrogate as the referential identity for durable state

- **Date:** 2026-07-21
- **Question:** ADR 004 pin 2 keys every dependent table (parent pointer,
  content, versions, chunks, edges) on the engine-minted integer surrogate
  `id`, with the ULID `node_id` referenced by nothing. Should durable
  references key on the ULID instead — making the stable identity the one
  that tables actually join on?
- **Trigger:** writes.py review session. The observation: if nothing
  internal references `node_id`, it is a public handle, not "the stable
  reference between tables" — and versions/edges are underivable if the
  integer mapping is ever lost (content could be rematched by hash;
  version and edge rows reference identity and nothing else).
- **Evidence gathered:** a local Postgres 18 spike, a 19-repo precedent
  review of the reference checkouts, and an internet literature review.

## 1. Spike: local Postgres 18, both schemas side by side

Two identical table families (`entries`/`content`/`edges`), differing only
in what dependent rows reference: the bigint `id` (children learn parent
ids via read-back before wiring — the current pipeline shape) vs a
client-minted `VARCHAR(26)` ULID (everything wired upfront). Load: 1,000
directories x 100 files, 100k content rows, 100k edges. Script:
session scratchpad `spike_identity_fk.py`.

| Dimension | int FK | ULID FK (text) | Delta |
| --- | --- | --- | --- |
| insert 100k files | 2,307 ms | 2,326 ms | ~equal |
| id read-backs (int flow only) | 337 ms | — | ULID saves |
| insert 100k edges | 1,406 ms | 2,072 ms | +47% |
| load total | 5,524 ms | 5,924 ms | +7% |
| ls x2,000 (parent equality) | 1,846 ms | 1,932 ms | +4.7% |
| content join, 5k rows | 68 ms | 66 ms | equal |
| edge fanout x2,000 (join to entries) | 101 ms | 124 ms | +22% (~62 µs/query) |
| `(parent_id, name)` index | 6.9 MB | 10.2 MB | +48% |
| content PK index | 2.2 MB | 4.8 MB | +118% |
| edges table + indexes | 12.3 MB | 24.1 MB | ~2x |
| whole footprint | ~70 MB | ~91 MB | +29% |

Readings: the cost is **storage-shaped, not latency-shaped** (ls within
5%, joins equal, edge fanout +22% at trivial absolute cost). The
client-wiring insert win is **neutralized** by wider edge-index
maintenance (net load +7%). And these numbers are the pessimistic
ceiling: the spike used text ULIDs, the one encoding the literature
uniformly condemns (§2) — binary-16 reclaims roughly half the overhead.

## 2. Literature (key results, with sources)

- **Time-ordered ids match bigint on insert throughput.** Ardent
  Performance's benchmark (1M inserts under concurrent reads): UUIDv7
  3,420 tps vs bigint 3,480 tps — indistinguishable; UUIDv4 ~28% slower;
  storage bigint 1.97 GB / v7 2.47 GB / v4 2.65 GB / **text-uuid 4.31 GB**
  (ardentperf.com/2024/02/03/uuid-benchmark-war).
- **Join deltas are small.** CYBERTEC 5M-row joins: uuid ~+13% over int4;
  "int4 vs int8 is a bigger difference than int8 vs uuid"
  (cybertec-postgresql.com, int4-vs-int8-vs-uuid-vs-numeric).
- **Text form is the mistake.** uuid-as-text: +63% total storage, ~10%
  slower inserts (Ardent); PK index +85% at 10M rows
  (maciejwalkowiak.com/blog/postgres-uuid-primary-key). ULID's 128 bits
  repack losslessly into a native 16-byte uuid/bytea column.
- **Random v4 is where the horror stories live** (up to ~7x index bloat
  at 100M rows; whole-index working sets). Time-ordering restores
  right-edge inserts (tvondra/sequential-uuids; michal-drozd.com).
- **Production migrations in both directions exist**: Shopify measured a
  50% insert-duration drop switching an idempotency table v4→ULID
  (shopify.engineering/building-resilient-payment-systems); Buildkite cut
  primary-DB WAL ~50% moving to UUIDv7 (buildkite.com,
  goodbye-integers-hello-uuids). PlanetScale is the counter-pole:
  bigint PKs inside + NanoID public ids, warning against random string
  PKs on MySQL (planetscale.com). Postgres 18 ships native `uuidv7()`.
- **Identity-survival facts**: pg_dump restores serial values and
  sequence state; physical/WAL replication preserves everything. But
  **logical replication does not carry sequence state**
  (postgresql.org, logical-replication-restrictions) — the classic
  post-failover duplicate-key incident; ETL re-import and shard merges
  re-key as an expected conflict class (TiDB shard-merge best
  practices); SQLite `VACUUM` may renumber implicit rowids
  (sqlite.org/lang_vacuum.html).
- **SQL Server caveat**: `UNIQUEIDENTIFIER` sorts by its own byte
  grouping, so naive time-ordered ids lose index locality there;
  `BINARY(16)` (or byte-shuffled storage) preserves it
  (learn.microsoft.com, newsequentialid).

## 3. Reference-repo precedent (19 systems)

Full per-system findings with file citations are in the session record;
the decisive rows:

| System | Durable join key | Engine autoincrement referenced? |
| --- | --- | --- |
| JuiceFS | app-minted inode (counter) | **No** — bigserial cols exist, unreferenced |
| SeaweedFS | dirhash(path) + name | No — none exists |
| libsqlfs | path text | No |
| Jackrabbit Oak | `depth:path` string; content hash | No |
| SpiceDB (pg) | natural key + xid8 | No — **shipped bigserial, then migrated to delete it** |
| OpenFGA | natural key; app ULID (changelog) | No |
| Gel/EdgeDB | UUID (time-ordered v1mc), native type | No |
| Graphiti / Cognee / Letta / mem0 | app UUID strings | No |
| TerminusDB | IRI (durable); layer-local u64s remapped on squash | No |
| Cayley | content hash (BYTEA) | No (SERIAL exists, unreferenced) |
| AgentFS | SQLite rowid `ino` | **Yes** — portable only by physical file copy |
| memori | autoincrement int | **Yes** — plus parallel UNIQUE uuid because the int is DB-local |
| basic-memory | autoincrement int | **Yes** — DB explicitly disposable, rebuilt from files |
| Apache AGE | graphid (label + sequence) | **Yes** — locally unique only |
| Neo4j / Kuzu | record offsets (internal) | Offsets reused/remapped on export; users told to own a UUID |

Score: ~15 of 19 key durable dependent tables on a system-minted stable
identifier. The systems that reference engine surrogates are the
disposable-database bucket (rebuilt from canonical files), the
no-logical-export bucket (physical copy only), or engines whose internal
ids are openly positions, not identity. JuiceFS is the exact target
shape: inert bigserial + app-minted referential id, dump/load preserving
inodes verbatim. SpiceDB is the strongest single datum: it paid a
five-migration sequence to remove its bigserial keys.

## 4. Synthesis

1. With binary-16 storage, ULID-keyed durable references cost roughly
   +25% on key-heavy indexes (edges worst), 0–13% on joins, and nothing
   on insert throughput.
2. The autoincrement never changes inside one living database; it
   changes at exactly the boundaries this project sells as first-class —
   cross-engine ETL, logical-replication failover, merges, partial
   re-imports.
3. The asymmetry is decisive: content is expensively re-derivable by
   hash; **version and edge rows reference identity alone and are
   unrecoverable if the mapping is lost**.
4. Precedent contract (from the repo review): anything the engine mints
   is re-mintable and must never be the only name for a row; the
   identity that survives dump/restore is the one the application
   minted.
5. Recommendation: amend ADR 004 pin 2 — ULID as the referential
   identity for durable state, integer demoted to local locator, derived
   stores exempt, binary-16 storage. Decision record: ADR 019.
