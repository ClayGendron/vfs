# 004. Stable Node Identity: ULID Logical ID, Integer Surrogate Key, Path as Regenerable Cache

- **Status:** accepted
- **Date:** 2026-07-14
- **Deciders:** Clay Gendron
- **Decided by:** human (option (c) confirmed 2026-07-13 during story 072
  research review; this record makes it binding)

This is the identity decision the stable-ID series reserved story 059
for. Story 072 (database storage backend) executes it directly; the
story-059 slot records a pointer here.

## Context

Entry identity in the pre-refactor schema — and in `rows.py` as it
stands today — is the **path**. Edges encode their endpoints as
`source_path`/`target_path` strings, so a rename must rewrite every
edge row under the moved subtree or lineage silently severs. The
2026-07-08 stable-ID evaluation
(`context/research/2026-07-08-stable-id-namespace-proposal.md`)
judged this a live defect and sketched a remediation series (stories
059–066); story 072 then had to choose whether to port the database
backend onto the defective schema, sequence the series first, or land
directly on the target schema.

The nine-repo reference review (story 072's research memo, now `context/research/2026-07-13-database-storage-backend.md`, §1) settled
the substance unanimously — six repos speak to the fork and all land
on stable identity with a parent pointer:

- **JuiceFS**: inode-keyed nodes + `edge(parent, name → inode)`,
  no path column anywhere; subtree rename updates one row.
- **AgentFS**: `fs_dentry(id, name, parent_ino, ino)` with stable
  `ino`; rename is a single-row UPDATE.
- **SeaweedFS** (the scar): path-keyed rows force a recursive
  enumerate/insert/delete over every descendant per rename, then
  stable identity had to be grafted back on anyway.
- **libsqlfs** (the purest demonstration): renaming one file rewrites
  the key on every content-block row; an `inode` column *exists in its
  schema* but keys nothing — a stable-ID column changes nothing unless
  dependent tables key on it.
- **OpenDAL**: its path-keyed SQL services simply declare
  `rename: false` — an exit a VFS with mandatory move/lineage verbs
  cannot take.
- **pjdfstest**: POSIX filesystems are literally parent-pointer
  systems (`rename/24.t`: after a directory move, `..` resolves to the
  new parent).

## Options considered

- **(a) Port the backend on the current path-keyed schema, migrate
  later** — cheapest now; fossilizes the rename/sever defect ADR 001
  warned every landed implementation would fossilize, and buys a real
  data migration later that greenfield avoids entirely.
- **(b) Execute the stable-ID series (059–066) as schema-only stories
  first, then port** — cleanest layering; serializes two large
  efforts, and 060–063 have no consumer until the backend exists.
- **(c) Land the backend directly on the target schema** (chosen) —
  the port and the pivot are the same work done once; there is no live
  database to migrate. The schema deltas of 060–063 fold into story
  072's Stage 1 and Pass A.
- **Rejected identity encodings** (from the 2026-07-08 evaluation):
  *path-as-identity* — the live rename/sever defect; *exposed bigint*
  — per-mount scope, no application-side minting, renumbers on
  dump/restore; *pure pathless storage* — inverts the rename/glob
  trade the wrong way (glob and ls are the hottest agent operations);
  *content-hash IDs* — mutable rows under permanent identity are
  inode/qid-shaped, not OID-shaped; hashing content severs edges on
  every update.

## Decision

Entry identity moves from path to a permanent stable node identity.
Three pins:

1. **`node_id` (ULID) is the logical identity.** Globally unique
   across mounts, mintable application-side without a database round
   trip (no `RETURNING` dependency), permanent across dump/restore,
   non-enumerable, time-ordered so batch inserts append to the index's
   right edge. Never reused: overwrite at an existing path keeps the
   `node_id` and bumps revision; delete-then-recreate at the same path
   mints a fresh ULID — the old ID named a different object that
   reused a name.
2. **Tables keep an integer surrogate primary key** for compact row
   references. Every dependent table — edges (`source_id`/`target_id`),
   posting lists (`doc_id`), content, versions, chunks — keys on the
   integer, never the ULID and never the path. `parent_id` (integer,
   nullable for root) is the one structural pointer; `UNIQUE(parent_id,
   name)` arbitrates creates. The internal integer is never a public
   name.
3. **Path survives as a regenerable cache, not identity.** The unique,
   binary-collated `path` column stays because glob's sargable LIKE
   and batch path→ID translation need it — agents glob a thousand
   times per rename. The invariant that keeps it honest: **nothing
   references path**; dropping and rebuilding the column from
   `parent_id` + `name` loses zero information, and a rebuild routine
   that proves byte-equality ships with the backend (the JuiceFS
   `doRepair` precedent — every denormalized cache is budgeted a
   verify/repair path).

Amendments absorbed from the reference review while confirming (c):

- **The read-path win is part of the claim**, not just the rename win:
  `parent_id` makes ls and parent checks one indexed integer equality
  instead of a subtree scan or per-ancestor query ladder (libsqlfs
  pays the scan on every directory listing).
- **The acceptance criterion is strengthened**: rename of a subtree
  with lineage rewrites **zero** edge, version, chunk, or content rows
  — only the path-cache column.
- **The new hazard is named**: under `parent_id`,
  move-into-own-descendant becomes a committable parent-pointer
  *cycle* that breaks CTE traversal and path regeneration. It must be
  refused at arbitrary depth under the story-072 §10 topology
  serialization point, and the harness tests it at ≥2 depths plus
  post-move descendant path checks.

## Consequences

- **Easier:** rename is O(subtree path-cache rewrite) with zero
  edge/lineage churn; ls is an integer equality; edge rows shrink to
  narrow ID triples with forward and reverse composite indexes;
  concurrent create arbitration gets one honest home
  (`UNIQUE(parent_id, name)`); dump/restore and cross-mount references
  survive because the public name is the ULID, not a row number.
- **Harder:** the path cache is denormalized state that must be
  rewritten in-transaction on every reparent (move, trash, restore)
  and guarded by the rebuild-and-prove routine; parent-pointer cycles
  become a real hazard requiring the topology serialization point;
  `python-ulid` becomes a core dependency.
- **Committed to:** story 072 lands `DatabaseStorage` directly on this
  schema (its Stage-1 `rows.py` rewrite and Pass A absorb the schema
  deltas of reserved stories 060–063); the path-pair edge encoding
  descending from story 011 is superseded; any future backend that
  keys dependent rows on path — or exposes the integer surrogate as a
  public name — is out of spec.

Executes through story 072 (`context/specs/072-database-storage-backend/`).
Evidence: `context/research/2026-07-13-database-storage-backend.md` §1;
`context/research/2026-07-08-stable-id-namespace-proposal.md` §§2–3.
