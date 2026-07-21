# Prior art for the 077 review's three open design questions

- **Date:** 2026-07-21
- **Question:** The five-lens review of the 077 landing left three design
  notes open (no present defect, direction undecided): (1) catch-retry's
  conflicted-layer replay is O(layer), not O(conflicts) — what granularity
  does prior art retry at? (2) `SCHEMA_FORMAT_VERSION` stayed 1 across an
  incompatible re-key — when do storage engines start bumping their format
  number? (3) the schema declares no foreign keys and the entries-content
  join predicate was written out twice — do production metadata-on-SQL
  stores use FKs, and who owns the canonical join?
- **Evidence gathered:** three parallel sweeps of the read-only reference
  checkouts under `~/Git/Repos/` (postgres, sqlite, sqlalchemy, turso,
  jackrabbit-oak, juicefs, seaweedfs, libsqlfs, agentfs, gel, age, kuzu).

## 1. Batch-insert conflict resolution granularity

**Closest precedent: Jackrabbit Oak `RDBDocumentStore`** — same
constraints as our catch-retry arm (no `ON CONFLICT`, client-minted keys,
batched JDBC inserts). Its bulk `createOrUpdate` partitions operations
into `CHUNKSIZE` chunks (default 64), learns the conflicted subset from
the per-row batch result, bulk-retries only that shrinking subset for up
to 3 rounds, and applies just the persistent residue sequentially — with
inline comments stating the rationale ("operations that conflicted in 3
consecutive bulk updates should be applied sequentially"). Its pure-create
path commits/rolls back per chunk, not per batch
(`RDBDocumentStore.java` `internalCreateOrUpdate`/`internalCreate`,
`RDBDocumentStoreJDBC.java` `insert`/`update` with
`BatchUpdateException.getUpdateCounts`).

**Supporting:** SQLAlchemy `insertmanyvalues` and `postgres_fdw` both
chunk strictly by bind-parameter budget and punt conflict recovery to the
caller — validating budget-chunking, silent on retry. SeaweedFS's SQL
filer is inherently row-at-a-time (insert, on duplicate fall back to
update). Nobody bisects (pgloader-style split-in-half was found nowhere);
Oak's learn-the-conflicted-subset is strictly better where the driver
reports per-row status.

**Dissent:** JuiceFS retries the *whole transaction* on duplicate-key
(50 tries, quadratic backoff, `shouldRetry` classifies duplicate-key as
transient). That fits its model — conflicts are rare races that vanish on
re-read — and does not fit ours, where a conflict is a real pre-existing
`(parent_id, name)` occupant that re-running wholesale would hit again.

**Implication adopted:** savepoint per budget-sized chunk; on conflict
re-drive only the conflicted chunk row-at-a-time. Python DBAPI
executemany does not reliably surface per-row failure status through the
abort, so chunk granularity is our floor (Oak's per-row refinement needs
JDBC-style update counts). Landed same day in `_catch_retry_layer`.

## 2. Schema format version bump policy

**The user-facing format number moves only for shipped formats.**
SQLite's file formats 1–4 each map 1:1 to a released version (3.0.0,
3.1.3, 3.1.4, 3.3.0 — history inline in `prepare.c`), and new databases
are written at the *lowest* format supporting the features used. Oak's
segment store went 1→2 across shipped formats and validates a
min/max window. JuiceFS runs production today still at
`MetaVersion` = `MaxVersion` = 1, deferring finer compatibility to a
separate client-semver range. None burn numbers on pre-release churn.

**The counter-model is a second, internal number, not an eager public
one.** Postgres bumps `CATALOG_VERSION_NO` on *every* initdb-requiring
commit — but that constant exists precisely so the user-facing
`PG_VERSION` does not move during development ("during development cycles
we usually make quite a few incompatible changes... we don't want to bump
the major version number for each one", `catversion.h`).

**Mismatch UX is universal: refuse, never migrate silently, classify
precisely.** Postgres aborts FATAL before touching data, with found and
expected values plus a hint ("It looks like you need to initdb"). JuiceFS
refuses with "please upgrade the client". Oak throws directional errors
("too old" vs "too recent" client) and — the sharpest detail — classifies
an *impossible* version value (`<= 0`) as unrecoverable corruption,
distinct from a legitimate window miss. SQLite alone degrades gracefully:
a too-new *write* version mounts read-only; a too-new *read* version
refuses.

**Implication adopted:** decision record 020 — stay at 1 until first
release; bump per incompatible change after; refine the guard's error
taxonomy when bumping starts.

## 3. Foreign keys and join-predicate ownership

**FK-free is the unanimous production posture.** JuiceFS (xorm structs:
`pk`/`index`/`unique` tags only, zero FK tags across node/edge/chunk/
xattr), libsqlfs (two tables, no FK), agentfs (`fs_dentry.parent_ino`
indexed, never FK), Oak's RDBDocumentStore (one PK-only documents table
per dialect). Even engines selling typed references avoid storage FKs:
gel compiles link integrity to triggers that raise
`foreign_key_violation` (`delta.py`), emitting FK *metadata* only in its
SQL-introspection emulation; Apache AGE uses real FKs solely on static
catalog tables, never vertex/edge data. Our write path (delete+reinsert
content, rival-identity adoption, parents-then-children bulk inserts) is
exactly the workload FK checks tax.

**The canonical join lives with the schema owner.** JuiceFS authors
`edge.inode=node.inode` exactly once in `initStatement()` and every call
site references it by key through `sqlConv` (`sql.go`). SQLAlchemy
blesses the same shape (`primaryjoin` relationships "that don't involve
any schema-level foreign keys", `join_conditions.rst`) — and notes SQLite
doesn't even enforce FKs without an explicit pragma.

**Implication adopted:** stay FK-free (now a confirmed position, not an
omission); `VFSTables.content_joined()` owns the entries-content join.
Landed same day.
