# 019. ULID as the Referential Identity for Durable State

- **Status:** accepted (2026-07-21, confirmed by Clay in session)
- **Date:** 2026-07-21
- **Deciders:** Clay Gendron
- **Decided by:** human (fork raised and argued by Clay during the
  2026-07-21 writes.py review session; evidence commissioned and
  reviewed in-session)
- **Amends:** ADR 004 pin 2. Pins 1 and 3 of ADR 004 (ULID minting
  rules; path as regenerable cache) are unchanged and restated below
  only where they interact.

## Context

ADR 004 established `node_id` (ULID) as the permanent logical identity
"so nothing needs to change" across dump/restore — then pin 2 routed
every actual relationship (parent pointer, content, versions, chunks,
edges) through the engine-minted integer surrogate. The tension: **if
nothing internal references the ULID, it is a public handle, not a
stable reference between tables.** The integer never changes inside one
living database, but it re-mints at exactly the boundaries this project
treats as first-class workload — cross-engine ETL, logical-replication
failover (sequence state is not replicated), database merges, partial
re-imports. If that mapping is ever lost, content is expensively
re-derivable by hash; **version and edge rows reference identity alone
and are unrecoverable** — the same severed-lineage defect class ADR 004
was written to kill, one level up.

The evidence (research memo `2026-07-21-ulid-referential-identity.md`):
a local Postgres 18 spike (cost is storage-shaped, not latency-shaped:
ls +5%, joins equal, edge fanout +22% at ~62 µs, footprint +29% in the
worst-case text encoding); a 19-repo precedent review (~15 of 19 key
durable tables on system-minted identity; JuiceFS ships the exact target
shape with inert bigserial columns; SpiceDB migrated to *delete* its
bigserial keys); and the literature (time-ordered 16-byte ids match
bigint insert throughput; the catastrophic numbers belong to random v4
and to text encodings).

## Options considered

- **(a) Keep pin 2** (integer FKs) — smallest indexes and no churn; but
  the durability promise stays hollow for internal relationships, and
  the underivable rows (versions, edges) stay keyed to the one identity
  that does not survive boundaries.
- **(b) ULID as the referential identity for durable state** (chosen) —
  references survive every boundary; measured cost ~25% on key-heavy
  indexes in binary form, ~0–13% on joins, insert parity; write pipeline
  simplifies (client-side wiring, no id read-backs).
- **(c) Drop the integer entirely** (ULID primary key) — rejected: the
  integer still earns its keep as a compact local locator (SQLite rowid
  alignment; narrow derived-table references), and once nothing durable
  references it, its remaining costs are zero.

## Decision

1. **`entry_id` (ULID) is the referential identity for durable state.**
   The entries column formerly `node_id` is renamed `entry_id`; the
   minting rules of ADR 004 pin 1 are unchanged (minted
   application-side at create only; overwrite keeps it; delete-then-
   recreate mints fresh). Durable dependent references key on it:
   `parent_id`, `original_parent_id`, `content.entry_id`,
   `versions.entry_id`, `chunks.entry_id`, `edges.source_id`/
   `target_id`. The `UNIQUE(parent_id, name)` arbitration index moves
   with the new type. FK columns keep their role names; joins read
   `entries.entry_id = content.entry_id` (the JuiceFS `inode ↔ inode`
   shape).
2. **The integer `id` is demoted to local row locator.** It remains the
   primary key (SQLite rowid alignment, compact heap addressing) and is
   referenced by nothing durable, exposed to nothing public. Derived,
   regenerable stores — posting lists' doc ids, future search
   structures — may key on the integer under the regenerable-cache
   doctrine that governs `path`: if a rebuild renumbers, rebuild the
   cache.
3. **Storage form is binary-16, never text.** The ULID's 128 bits are
   stored via SQLAlchemy's `Uuid` type (native `uuid` on Postgres),
   with a SQL Server variant of `BINARY(16)` because `UNIQUEIDENTIFIER`
   sorts by its own byte grouping and would forfeit time-ordered index
   locality. Text ULID columns in an indexed role are out of spec (the
   one encoding every benchmark condemns). The domain and API surface
   keeps the 26-character ULID string; conversion happens once, at the
   storage boundary.
4. **The write pipeline wires identity client-side.** Children reference
   parents by minted ULID before any statement runs; RETURNING no
   longer harvests ids for wiring. Depth-layered insert order and
   per-layer fail-fast are retained — arbitration-loss detection still
   requires learning each layer's winners before wiring deeper layers.

## Consequences

- **Easier:** references survive re-keyed ETL, logical-replication
  failover, merges, and cross-engine moves — for exactly the rows that
  are underivable if severed; dependent rows are reconcilable across
  copies/backups by stable id; the write pipeline drops its id
  read-backs (`_parent_id` two-source resolution, catch-retry id
  read-back, learned-id content wiring); a mount's tables can be copied
  row-wise into a fresh schema with the integer re-minting freely.
- **Harder:** key-heavy indexes grow (~+25% binary; edges worst at
  ~1.4×); joins on some engines pay 0–13%; a per-dialect storage-type
  seam (Postgres native uuid / SQL Server BINARY(16)) joins the
  DialectProfile family of declared decisions; ULID↔binary conversion
  discipline at the storage boundary.
- **Committed to:** spec 077 lands the schema and pipeline together;
  any future durable table keys on `entry_id`; any future derived table
  documents which side of the locator/identity line it sits on.

Executes through story 077
(`context/specs/archive/077-ulid-referential-identity/`). Evidence:
`context/research/2026-07-21-ulid-referential-identity.md`.

## Amendments (2026-07-21, from the post-landing five-lens review)

- **Decision 4 caveat — adoption, not minting, on clobbers.** "RETURNING
  no longer harvests ids for wiring" holds for rows the batch itself
  creates. On an overwrite conflict the rival row survives and keeps its
  `entry_id`, and the staged entry *adopts* it — from RETURNING on the
  upsert arm, from the occupant probe on catch-retry — so content rows
  wire to the row that exists. Client-side minting governs created rows;
  adoption governs clobbered ones. (The suite pins this:
  `test_upsert_layer_adopts_identity_or_classifies_per_rival`.)
- **Decision 3 stated the election incompletely.** "Via SQLAlchemy's
  `Uuid` type" read literally would store CHAR(32) hex *text* on SQLite,
  MySQL, and Oracle — outlawed by this decision's own headline. The
  landed election is three-armed: the engine's native uuid only where
  its sort preserves ULID time-order (Postgres); `RAW(16)` on Oracle;
  fixed-width `BINARY(16)` everywhere else. The gate is an allow-list,
  not `supports_native_uuid` — that flag means driver uuid-object
  handling and says nothing about sort order (MSSQL's
  `UNIQUEIDENTIFIER` and MariaDB's byte-swapped native uuid both report
  support while mis-sorting).
- **Where the seam lives.** The consequences said the storage-type seam
  "joins the DialectProfile family of declared decisions"; it is
  deliberately homed as SQLAlchemy type variants beside the schema in
  `rows.py` instead — the profile records only decisions SQLAlchemy
  takes no position on, and column storage form is not one of them.
