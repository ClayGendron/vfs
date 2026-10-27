# Study 03 — File System Implementation (vsfs), laid against vfs's tables

- **Date:** 2026-10-24
- **Book section:** OSTEP v1.10, chapter 40, *File System
  Implementation* (PDF pages 535–552). Page numbers below are the
  chapter's own page numbers (p. 1–18). PDF page = chapter page + 534.
- **vfs commit:** `ac5c515` (`main`, with the uncommitted ADR 081–086
  and spec 166–173 drafts in the tree).
- **Prior work cited, not redone:** study 05 of the 2026-10-23 set,
  `context/research/studies/2026-10-23-filesystem-shaped-api/05-vfs-surface-audit.md`,
  and its scripts under `experiments/s05/` (statement counts per verb
  per authority, the 10,000-child `ls`, object allocations).
- **New scripts (EXECUTED, in the session scratchpad, outputs beside
  them):** `ostep/experiments/s03/access_paths.py` → `access_paths.out`
  (ordered statement list per verb with rows returned, bytes bound and
  bytes fetched; path depth 2 vs 20; a 4 MiB body; 10,000 overwrites in
  one call vs 200 one-file calls; create-then-delete residue) and
  `ostep/experiments/s03/edit_probe.py` (the SQL text of an edit's
  first statements). Both run on `InMemoryStorage` (SQLite through
  aiosqlite), system actor unless named. Every number is a count:
  statements, rows, bytes. Nothing is timed.
- **Engine references (READ, not refreshed for this study):**
  `~/Git/Repos/postgres` at `b128e75e` (2026-10-14), PostgreSQL
  licence; `~/Git/Repos/sqlite` at `3d17c3f9e` (2026-08-04), public
  domain. Cited for how each engine stores one large value.
- **Labels:** READ = the book (chapter and page) or a file at this
  commit; EXECUTED = ran here with `uv run`; INFERRED = my reasoning
  across sources.
- **Book text:** paraphrased only, never quoted, per the brief.

Terms used below, defined once:

- **Access path**: the ordered list of storage reads and writes one
  call performs. The chapter draws these as timelines.
- **Statement**: one SQL round trip the driver executes. An
  `executemany` over 10,000 parameter rows counts as one statement in
  SQLAlchemy's `before_cursor_execute` hook.
- **Bytes sent / fetched**: the sizes of the string and bytes values
  bound as parameters, and of those returned in result rows.
- **Body**: a file's content. Text lives in `vfs_content`, bytes in
  `vfs_blobs`.
- **Pre-image**: the body a write is about to replace. vfs keeps it as
  a version row.

## 1. What the chapter says

The chapter builds a toy Unix-like file system, vsfs, to teach one
habit of mind. To understand any file system, learn two things: the
structures it keeps on disk, and the access paths that each call walks
through those structures (ch. 40 p. 1–2). The disk is cut into
fixed-size blocks. Most blocks hold user data. A few hold the
superblock (what this file system is and where its parts start), two
bitmaps (which inodes and which data blocks are free), and the inode
table (p. 2–4). An inode is a small fixed-size record of a file's
metadata and of where its data blocks sit. Its number alone tells you
where it lives on disk (p. 4–5). To reach big files, the inode uses a
lopsided tree of pointers: a few direct pointers, then indirect blocks
of pointers, then doubly and triply indirect ones. The tree is lopsided
on purpose, because measured file systems hold mostly small files and a
few huge ones (p. 6–8). Extents (a start plus a length) and linked
allocation (FAT) are the alternatives (p. 7, 9). A directory is just a
file whose data is a list of name-to-inode-number pairs, with tricks
for deleted entries; XFS keeps directories as B-trees so that a create
can check name uniqueness fast (p. 8–9). Free space is tracked in the
bitmaps; ext2 also pre-allocates runs of blocks for locality (p. 10).
The heart of the chapter is two timelines that count every disk read
and write. Opening a file walks the path from the root, two reads per
level. Each read of a block also writes the inode to record the access
time. Each allocating write costs five I/Os. Creating one file costs
about ten (p. 10–14). The chapter then asks how to make all this
cheaper. The answer is memory: a cache for reads, sized dynamically in
a unified page cache, and buffering for writes. Delaying writes lets
the system batch them, schedule them, and sometimes skip them. The
price is durability: a crash loses what was buffered. Applications that
cannot accept that loss force writes out with `fsync` (p. 14–16).

## 2. Principles vfs should adopt

Each item gives the principle, where the book teaches it, where vfs
stands, and the one change it implies.

### 2.1 vfs's own on-disk layout, drawn the chapter's way

First the picture the chapter would draw for vfs. READ,
`src/vfs/models/rows.py`, unless marked.

| vsfs region (ch. 40 p. 2–4) | vfs's stand-in | What it holds |
|---|---|---|
| Superblock | `vfs_meta`, one row (`id = 1`) | `schema_format_version` (checked at first touch, currently 23), `mount_identity`, `current_gram_epoch`, the reindex lease, `embedding_model`, `grant_revision` |
| Inode bitmap, data bitmap | **none** | Identity is a ULID minted by vfs (ADR 019); surrogate integer keys come from the engine's `Identity()`; free space is the engine's own business |
| Inode table | `vfs_entries` | One narrow row per file or directory: identity, `parent_id`, `name`, `path`, `kind`, `version`, size, hash, timestamps, tombstone, `owner_id`, `everyone_level`, index dirty flags. **Never a body.** |
| Data region | `vfs_content` (text) and `vfs_blobs` (bytes) | One whole body per entry, keyed by `entry_id`, body column last |
| Directory data blocks | **no separate blocks** | A directory is an `entries` row. Its listing is the `UNIQUE(parent_id, name)` index over child rows. `vfs_edges` mirrors each parent link as an `fs` edge (ADR 018). `vfs_segments` posts each ancestor name for glob |
| Indirect blocks | **none in vfs**; the engine's large-value storage | See principle 8 |
| (no vsfs analogue) | `vfs_versions`, `vfs_version_subjects` | Every replaced body, whole, with who replaced it |
| (no vsfs analogue) | `vfs_chunks`, `vfs_grams_posting_list`, `vfs_lex_*`, `vfs_signals`, `vfs_gram_epochs`, `vfs_signal_epochs` | Derived search indexes, rebuilt by `reindex`, epoch-scoped |
| (no vsfs analogue) | `vfs_grants`, `vfs_memberships`, `vfs_relabels`, `vfs_principal_revisions` | Rights |
| (no vsfs analogue) | `vfs_lock`, one row | The serialization point for move, copy and delete (ADR 078) |

Twenty-three tables in one mount (`VFSTables`). vsfs has five regions.
The extra eighteen are history, search and rights: the three things
vfs exists to add on top of a file system.

### 2.2 vfs's access paths, drawn the chapter's way

The chapter's timelines (ch. 40 p. 11, p. 13) list every block touched
per call. Here is the same thing for vfs: every statement, in order,
with the table it touches. EXECUTED, `access_paths.out`, section A.
System actor, file `/docs/a.md` (depth 2, 60-byte body). R = read,
W = write, D = delete.

**read(/docs/a.md)** — 1 statement, 3 rows back, 330 B fetched.

| # | Statement | Rows back | Why |
|---|---|---|---|
| 1 | R `vfs_entries` LEFT JOIN `vfs_content`, `path IN ('/', '/docs', '/docs/a.md')` | 3 | target and every ancestor in one go; the ancestors classify a miss and carry rights |

**stat(/docs/a.md)** — the same select without the body join. 1
statement, 3 rows, 270 B.

**ls(/docs)** — 2 statements, 318 B.

| # | Statement | Rows back |
|---|---|---|
| 1 | R `vfs_entries`, `path IN ('/', '/docs')` | 2 |
| 2 | R `vfs_entries`, `parent_id IN (…)`, ordered by `(parent_id, name)` | 1 per child |

**write, create (/docs/b.md)** — 9 statements plus control.

| # | Statement | Rows | What it is |
|---|---|---|---|
| 1 | R `vfs_entries`, `path IN` target + ancestors | 2 | the snapshot the plan is staged against |
| 2 | R `vfs_grants` | 1 | the posture rows that set the new row's `everyone_level` label |
| 3 | W `vfs_entries` INSERT (inside a SAVEPOINT) | 1 | the new entry row (the inode, in vsfs terms); the savepoint arbitrates a racing create |
| 4 | W `vfs_segments` INSERT | — | one row per ancestor directory name, for glob |
| 5 | W `vfs_edges` INSERT | — | the `fs` mirror edge parent → child |
| 6 | D `vfs_content` | — | clears a body that cannot exist yet (see principle 14) |
| 7 | D `vfs_blobs` | — | same |
| 8 | W `vfs_content` INSERT | — | the body |
| 9 | W `vfs_entries` UPDATE | — | the parent bump: `version + 1` on `/docs`, guarded by its path and liveness |

**write, update (/docs/b.md, new body)** — 8 statements plus control.

| # | Statement | Rows | What it is |
|---|---|---|---|
| 1 | R `vfs_entries`, target + ancestors | 3 | snapshot |
| 2 | W `vfs_entries` guarded UPDATE (inside a SAVEPOINT) | — | `WHERE version = base AND path = … AND deleted_at IS NULL` |
| 3 | R `vfs_meta` | 1 | the grant revision, stamped on the version row |
| 4 | R `vfs_entries` JOIN `vfs_content` | 1 | the pre-image body |
| 5 | W `vfs_versions` INSERT | — | the pre-image, whole |
| 6–7 | D `vfs_content`, D `vfs_blobs` | — | delete-then-insert of the body |
| 8 | W `vfs_content` INSERT | — | the new body |

**edit (/docs/b.md, `y` → `z`)** — 9 statements: the write-update list
above, except the snapshot joins the body (it needs the old text to
edit), and one extra select of the root row appears (principle 14).

Named principal (section B): add 2 reads at the front,
`vfs_principal_revisions` and `vfs_relabels`. These are the rights
stamps that validate the cached rights. A write by a named principal
also writes one `vfs_version_subjects` row. Anonymous adds a
`vfs_grants` read (study 05 §7). Delete (study 05): R `vfs_entries`,
R `vfs_lock`, two W `vfs_entries` (stamp the root, stamp the
descendants).

The summary grid, one row per verb, one column per table (system
actor):

| Verb | entries | content | blobs | versions | meta | grants | segments | edges | lock |
|---|---|---|---|---|---|---|---|---|---|
| read | R | R (join) | | | | | | | |
| stat | R | | | | | | | | |
| ls | R R | | | | | | | | |
| write create | R W W | D W | D | | | R | W | W | |
| write update | R W R | R D W | D | W | R | | | | |
| edit | R R W R | R R D W | D | W | R | | | | |
| delete | R W W | | | | | | | | R |

### 2.3 The principles

1. **Understand a file system by two things: what it stores, and the
   path each call takes through what it stores.**
   - Book: ch. 40 p. 1–2 (the two aspects, and the mental-model aside).
   - vfs: **half follows.** The storage half is well documented:
     `rows.py` explains every table and index (READ). The access-path
     half exists only in pieces. `tests/storage/database/test_writes.py:111`
     pins the create and overwrite counts at 8 non-control statements
     each, and `tests/storage/database/test_reads.py:294` pins that the
     read family issues SELECTs only (READ). No test or doc shows the
     ordered path per verb, as §2.2 does.
   - Change: keep an **access-path table per verb** as a golden test:
     the ordered list of (statement kind, first table) for read, stat,
     ls, write-create, write-update, edit, delete, at three authorities.
     A new statement then shows up as a reviewed diff, not a surprise
     (INFERRED).

2. **Count the I/Os per step on a timeline, and count the unit that
   actually costs.**
   - Book: ch. 40 p. 11–14 (both timelines; five I/Os per allocating
     write, about ten per create, open cost grows with path length).
   - vfs: **half follows.** CLAUDE.md already says count operations,
     never wall-clock, and the tests count statements (READ). But a
     statement is not vfs's only cost. EXECUTED, section D: a one-byte
     edit of a 4 MiB text file issues the same 9 statements as a
     one-byte edit of a 2-byte file. It fetches **8,388,752 bytes** and
     sends **8,388,980 bytes**. The small edit fetched 130 bytes and sent 355. The statement count
     hides a difference of tens of thousands of times in bytes moved. In the other direction, section E: 10,000
     overwrites in one call issue 15 statements but send 3.7 MB, because
     `executemany` counts once.
   - Change: count **three units** in the access-path test: statements,
     rows, and body bytes moved (bound plus fetched). The book's unit
     was a block; vfs's honest unit is a round trip *and* its payload
     (INFERRED).

3. **Keep per-file metadata small and apart from the data, so metadata
   calls never touch data.**
   - Book: ch. 40 p. 4–6 (the inode is small, fixed, and points at the
     data).
   - vfs: **follows.** `rows.py` keeps bodies out of `vfs_entries` so a
     metadata write never rewrites a body (READ, the `ENTRY_BODY_HOMES`
     comment). EXECUTED: `stat` of the 4 MiB file fetched 273 bytes;
     `ls /docs` with that file as a child fetched 453 bytes.
   - Change: none to the design. Pin it: `stat` and `ls` fetch zero body
     bytes, whatever the body size.

4. **A read never writes, and never touches the structures only writes
   need.**
   - Book: ch. 40 p. 12 (reads do not consult the allocation bitmaps).
     The same timeline shows the cost of breaking the rule: vsfs writes
     the inode's access time on every block read (p. 11–12).
   - vfs: **follows, more strictly than vsfs.** Read builders execute
     SELECTs only (`reads.py` docstring; `test_reads.py:294`) (READ).
     There is no access time (`Observation` carries `created_at`,
     `updated_at`, `deleted_at`; study 05 §4e) (READ). EXECUTED: a read
     touches `vfs_entries` and `vfs_content` only; it never touches
     `vfs_meta`, `vfs_lock` or `vfs_grants` as the system actor.
   - Change: none. Record the absence of an access time as deliberate wherever the
     stat fields are listed, so a future front (FUSE, WASI) does not add
     one as a write-on-read (INFERRED).

5. **Path lookup must not cost one round trip per path level.**
   - Book: ch. 40 p. 12 and p. 14 (open cost grows with the number of
     directories in the path; a hundred-level path means hundreds of
     reads without a cache).
   - vfs: **follows.** One `path IN` select fetches the target, every
     ancestor, and the root together (`descent.py`
     `targets_with_ancestors`, `reads.py` `_mappings_by_path`) (READ).
     EXECUTED, section C: `stat` at depth 20 is **1 statement, 21 rows,
     2,122 bytes**; at depth 2 it is 1 statement, 3 rows. vsfs would do
     about 40 block reads for the same walk. The cost that still grows
     with depth is rows, not round trips. One write cost also grows with
     depth: a create at depth 20 inserts 19 `vfs_segments` rows, one per
     ancestor name (EXECUTED, 352 bytes; READ, `rows.py` segments
     comment).
   - Change: none to the design. Add depth as a dimension of the
     access-path test (statements constant, rows linear).

6. **A create must not read and write a structure every create shares.**
   - Book: ch. 40 p. 10 and p. 13 (a create reads and writes the inode
     bitmap; an allocating write reads and writes the data bitmap). The
     book's own fix comes later: buffer the bitmap and batch it (p. 15).
   - vfs: **follows, by decision.** ADR 013 dropped the per-mount
     revision counter because every write held its lock. Versions are
     per-entry values on their own rows (`writes.py` docstring: no
     per-mount counter) (READ). Identity is a ULID minted by vfs, not
     allocated from a table (ADR 019, `ULIDKey` in `rows.py`) (READ).
     EXECUTED: a create touches no `vfs_meta` and no `vfs_lock` row. An
     update *reads* `vfs_meta` once for the grant revision. That is a
     read of a shared row, not a write.
   - Change: none. Pin the rule in the access-path test: no create or
     update path *writes* a mount-wide row (`vfs_meta`, `vfs_lock`).

7. **Name uniqueness in a directory should be checked by an index, not
   a scan.**
   - Book: ch. 40 p. 9 (XFS keeps directories as B-trees so a create
     can check a name fast; a plain list must be scanned).
   - vfs: **follows.** `UNIQUE(parent_id, name)` arbitrates concurrent
     creates and orders listings (`rows.py`, `uq_vfs_entries_parent_name`)
     (READ).
   - Change: the same index carries the listing cursor. Keyset on
     `(parent_id, name)`, as yesterday's memo §4.2 recommends; study 05
     §4b measured `ls` of 10,000 children returning all 10,000 rows in 3
     statements, with no cursor.

8. **Build for the measured common case: most files are small, and a
   few large files hold most of the bytes.**
   - Book: ch. 40 p. 7–8 (the lopsided multi-level index exists because
     of this; the measurement summary on p. 8; and the advice to
     revisit the design when workloads change, p. 8).
   - vfs: **half follows.** One whole body per row is the small-file
     fast path. It is the vfs version of the inode's direct pointers: a
     small file is one row and one probe. But vfs has no indirect
     tier of its own. A large body pays its whole size on every change.
     EXECUTED, section D, one-byte change to a 4 MiB body:

     | Call | Statements | Bytes fetched | Bytes sent |
     |---|---|---|---|
     | `write`, 4 MiB create | 9 | 104 | 4,194,693 |
     | `read` | 1 | 4,194,584 | 19 |
     | `stat` | 1 | 273 | 19 |
     | `write`, update, one byte differs | 8 | 4,194,431 | 8,388,979 |
     | `edit`, one byte | 9 | 8,388,752 | 8,388,980 |

     The update fetches the pre-image once and sends the body twice
     (the version snapshot, then the new body). The edit fetches it
     twice: once for the edit, once again for the version mint.

     Underneath, the engine already keeps a multi-level index for big
     values. READ, PostgreSQL: a large value is cut into chunk rows
     numbered by `chunk_seq` in a TOAST table
     (`src/backend/access/common/toast_internals.c:198, 316, 350`), and
     a slice fetch exists (`src/backend/access/common/detoast.c:27,
     241`). READ, SQLite: a large row spills to overflow pages that form
     a **linked list** (`src/btreeInt.h:197-204`), and the cursor keeps a
     cache of overflow page locations (`btreeInt.h:539`). That is the
     chapter's linked-allocation aside (p. 9) and its in-memory table fix,
     inside SQLite. So vfs does have an indirect tier: the engine's.
     vfs's update path defeats it by replacing the whole value
     (INFERRED).
   - Change: measure vfs's own file-size distribution before choosing a
     chunked body (the chapter's p. 8 table, for vfs's corpora: agent
     workspaces, code, ETL loads). Name the direction in the
     `versions.py` and `writes.py` docstrings, never as a cap: ranged
     read through the engine's `substr` (memo §4.5), and diff-form
     versions for large text (the `version_diff` column already exists
     in `rows.py`; the write path stores snapshots only).

9. **Buffering writes trades durability for fewer I/Os, so decide per
   kind of data which side it sits on.**
   - Book: ch. 40 p. 15–16 (batching, scheduling and avoidance; the
     5–30 second window; the durability/performance tip; databases
     force writes with `fsync`).
   - vfs: **follows, with a split the chapter does not draw.** Primary
     data is never buffered: each call is one transaction, committed
     before the `Result` returns (`backend.py` `_mutate`) (READ). Derived
     index data *is* deferred. A write only resets the `chunked` and
     `encoded` flags; trigram, BM25, chunk and embedding rows wait for
     `reindex` (ADR 033 §6: no per-write index maintenance;
     `indexing.py` docstring) (READ). Correctness survives the delay:
     the scan side serves every `NOT encoded` row (ADR 033 §5, ADR 051
     decision 7) (READ). Only two derived facts are written in the same
     transaction: path segments and the `fs` edge (EXECUTED, §2.2).
     This is write buffering done safely. The buffered data is
     rebuildable, and readers have a correct path while it is stale.
   - Change: none to vfs. **One correction for the synthesis**:
     yesterday's memo (§0 and §4.3) says the trigram, lexical and vector
     indexes are written in the same transaction as the body. At this
     commit they are not; only `vfs_segments` and the `fs` edge are
     (READ + EXECUTED). The kernel ADR should state the real split.

10. **Batching is how you amortize the fixed cost of an I/O.**
    - Book: ch. 40 p. 15 (delaying the bitmap write lets two creates
      share one I/O).
    - vfs: **follows, with the caller doing the batching.** EXECUTED,
      section E: 10,000 overwrites in one `write(entries=…)` cost **15
      statements**; 200 overwrites in 200 calls cost **2,200
      statements** (11 each). That is about 0.0015 statements per file
      against 11. This is the ETL contract in CLAUDE.md (READ). An agent
      loop that writes one file per call gets no batching. vfs holds no
      dirty state between calls, so it cannot merge two calls into one
      commit.
    - Change: none in the kernel. If a front ever coalesces small writes
      across calls, it moves the durability point, and it must say so
      in its contract (INFERRED; principle 9).

11. **Laziness can skip work entirely: a file created and then deleted
    before the flush never reaches disk.**
    - Book: ch. 40 p. 15.
    - vfs: **does not, on purpose.** EXECUTED, section F: create then
      delete leaves 1 `entries` row (tombstoned), 1 `content` row, 1
      `segments` row and 1 `edges` row. Delete never destroys; `sweep`
      is the only destroyer (ADR 027); trash is a tombstone on the row
      (ADR 074) (READ).
    - Change: none. Keep it as a deliberate non-adoption. Undo and audit
      need the row.

12. **Cache in one shared, dynamically sized pool rather than in fixed
    private slices.**
    - Book: ch. 40 p. 14–15 (the unified page cache; the static vs
      dynamic partitioning tip).
    - vfs: **follows, by having almost no cache of its own.** Rows and
      bodies are cached by the engine's buffer pool, shared by every
      process that talks to the database (INFERRED from the code: no
      row or body cache exists in `src/vfs`). The caches vfs does keep
      are small and statically bounded: `RightsCache`, bounded by
      entries and bytes (`rights.py:250`), and the table-family LRU of
      64 (`rows.py` `TABLE_FAMILY_CACHE`) (READ).
    - Change: if a body cache arrives (the WASI provider's staged
      buffers keyed by `(path, version)`, spec 172 per study 05 §4f),
      key it by `version`. Versions only ever rise per entry (ADR 013),
      so a cached body is valid exactly when a `stat` shows the same
      version. That `stat` costs 1 statement and no body bytes
      (principle 3).

13. **The superblock is read once, at mount, and names the file
    system's format.**
    - Book: ch. 40 p. 4 (mount reads the superblock first; it carries a
      magic number and the layout).
    - vfs: **follows.** `vfs_meta` holds `schema_format_version`, and
      first touch compares it and refuses loudly on mismatch (`rows.py`
      `SCHEMA_FORMAT_VERSION` comment) (READ). First touch costs 100
      statements, once (study 05 §7, EXECUTED there). ADR 078 moved the
      serialization lock out of this row into `vfs_lock`, so the
      meta row is not every writer's choke point (READ).
    - Change: none.

14. **Look for the hidden I/Os, the ones the obvious model does not
    predict.**
    - Book: ch. 40 p. 14, footnote 2 (creating an inode costs a read,
      because the inode shares a block with others and the update is a
      read-modify-write).
    - vfs: **has three of its own.** EXECUTED:
      - Every create issues `DELETE vfs_content` and `DELETE vfs_blobs`
        for a row minted in this same batch, whose body cannot exist
        yet. That is 2 of the 9 create statements. Cause:
        `_replace_bodies` is one delete-then-insert path for every
        write (`writes.py:961`) (READ).
      - Every edit issues a select of the root row alone
        (`path IN ('/')`), even when no target missed (`edit_probe.py`).
        Cause: `miss_errors` calls `classify_misses` with an empty miss
        list, and `targets_with_ancestors` always adds `/`
        (`descent.py:135`, `:183`) (READ).
      - Every edit fetches the whole pre-image twice: once in the
        snapshot, once again in the version mint (8.4 MB for a 4 MiB
        file). The guarded update proves the version did not change
        since the snapshot (`writes.py` `_update_materials`), so the
        snapshot's body already is the pre-image (INFERRED).
    - Change: skip the body pre-clear for freshly minted rows (the code
      already separates them as `minted`); return early from
      `miss_errors` when nothing missed; let the mint reuse an edit's
      snapshot body for rows whose guard matched. Each is small. The
      bigger lesson is that only an access-path table (principle 1)
      shows them.

## 3. Nouns and verbs

| Book term (ch. 40) | What it is in the book | vfs today | Adopt the name, adopt the concept, or not? |
|---|---|---|---|
| block | fixed unit of disk I/O (p. 2) | none; the engine's page | **Not.** vfs never addresses storage; the engine does. |
| superblock | per-volume facts, read at mount (p. 4) | `vfs_meta` row | **Concept, own name.** *Meta row* already says it. |
| inode | small per-file metadata record (p. 4–6) | `vfs_entries` row; `Observation` on the wire | **Concept, own name.** *Entry* is right; an inode has no path and an entry does. |
| i-number | low-level name; computes the inode's address (p. 5) | `entry_id` (ULID) plus surrogate `id` | **Concept, own name.** The address is found by index probe, not computed. |
| inode table | array of inodes (p. 3) | `vfs_entries` | **Concept.** |
| inode bitmap, data bitmap | free/used tracking (p. 3–4, 10) | none | **Not, deliberately.** ULIDs need no allocator; ADR 013 removed the last shared counter. |
| data region / data block | where file bytes live (p. 2–3) | `vfs_content`, `vfs_blobs` | **Concept, own name**: *body*. |
| direct / indirect pointer, multi-level index | map from file offset to blocks (p. 6–7) | none in vfs; the engine's TOAST, LOB or overflow chain | **Not as a name.** The concept enters only if vfs chunks bodies itself (principle 8). |
| extent | start plus length (p. 7) | none | **Concept, later**, as `read(range=…)` (memo §4.2). |
| linked allocation / FAT | next-pointer chain (p. 9) | none in vfs; SQLite's overflow pages are one | **Not.** Worth knowing: it is what SQLite does under a big body. |
| directory | file of name → inode-number pairs (p. 8–9) | a `directory` entry; its children by `parent_id` | **Name kept** (`kind="directory"`). Storage is an index, not a file. |
| directory entry (dirent) | one name/number pair (p. 8) | `(parent_id, name)` on the child row | **Concept, own place.** The name lives on the child, not in the parent. |
| `.` and `..` | self and parent entries (p. 8) | `parent_id`; no stored `.` | **Not.** Paths are canonical; no relative entries are stored. |
| freed dirent / record length | holes left by unlink (p. 8–9) | tombstone (`deleted_at`) on the row | **Concept, different meaning.** A tombstone keeps the name taken and the row whole. |
| metadata | everything that is not user data (p. 6) | the `entries` columns | **Name kept.** |
| mode, uid, gid, ACL | protection fields (p. 6) | `owner_id`, `everyone_level`, `vfs_grants` | **Concept, own names.** No mode bits (study 05 §4e). |
| atime | last-access time (p. 6, 12) | none | **Not, deliberately.** It turns every read into a write (principle 4). |
| mtime, ctime, dtime | modify, change, delete times (p. 6) | `updated_at`, `created_at`, `deleted_at` | **Concept, own names.** |
| links count | hard links (p. 6) | none | **Not.** One path per entry (ADR 011, 021; study 05 §4g). |
| generation | file version for NFS (p. 6) | `version` | **Concept, own name.** Per-entry, monotone (ADR 013). |
| access path | which structures a call touches (p. 10) | none | **Adopt the name**, for the per-verb table and its test (principle 1). |
| page cache / buffer cache | memory holding hot blocks (p. 14–15) | the engine's buffer pool; `RightsCache` | **Not in vfs.** The engine owns it; vfs caches only rights. |
| write buffering, delayed write | hold writes in memory before disk (p. 15) | caller batches; `reindex` defers derived indexes | **Concept, own names**: *batch*, *dirty flag*, *reindex*. |
| pre-allocation | reserve contiguous blocks for locality (p. 10) | ULID time order keeps index locality (`rows.py` `_uuid_native`) | **Concept, implicit.** No name needed. |
| file descriptor, open-file table, offset | per-process open state (p. 12) | none | **Not.** No handles in the kernel (memo §4.2; ADR 074 names handles as a trash-leak seam). |
| open | walk the path, check rights, hand back an fd (p. 11–12) | none; `stat` / the descent ladder does the walk | **Not as a verb.** A front with handles owns it. |
| read, write | the data calls (p. 12–13) | `read`, `write` (whole body, batchable) | **Names kept.** |
| create | allocate inode, link name (p. 13) | `write` on an absent path; `mkdir` | **Concept, inside `write`.** |
| unlink | remove a name (p. 8) | `delete` (a tombstone) | **Concept, own name.** |
| close | free the fd; no disk I/O (p. 12) | none | **Not.** |
| `fsync` | force buffered writes to disk (p. 16) | none; every call commits | **Not needed.** A committed call is as durable as the database makes it. |
| mount | read superblock, attach the volume (p. 4) | `bind`, `add_mount`, first touch | **Concept, own names.** |
| allocate | find a free inode or block (p. 10) | mint a ULID | **Concept, own name**: *mint*. |
| lookup / traverse | path walk from the root (p. 11) | `targets_with_ancestors`, the descent ladder | **Concept, own name.** Already one statement. |

## 4. What does not transfer

- **The unit of cost is different.** A vsfs I/O moves one 4 KB block.
  A vfs statement can move one row or ten thousand, and one byte or
  four megabytes (EXECUTED, §2.3 items 2 and 8). Counting statements
  alone, the way the book counts blocks, undercounts both batches and
  big bodies. vfs needs statements, rows and bytes (INFERRED).
- **An address is not computed.** vsfs finds inode 32 by arithmetic
  (ch. 40 p. 5). vfs finds a row by a B-tree probe on `path` or
  `entry_id`. There is no layout to place, so the chapter's placement
  questions (where to put a new file, p. 16) belong to the engine
  (INFERRED).
- **The path is stored, so the trade-off flips.** An inode file system
  pays per level at lookup and almost nothing at rename. vfs stores the
  full path on every row as a cache (`rows.py`), so lookup is one
  statement at any depth, and moving a directory rewrites every
  descendant's path. Study 05 §7 measured a one-file `move` at 14
  non-control statements as the system actor. The chapter's cost model
  would call vfs's choice backwards; for agents, who look up far more
  than they rename, it is the right way round (INFERRED).
- **There is no in-memory dirty state to lose.** vsfs's durability
  trade-off is about memory the kernel holds (p. 15–16). vfs holds
  nothing between calls; durability is the database's commit, WAL and
  configuration. The knob the chapter describes exists, but it belongs
  to the database operator, not to vfs (INFERRED).
- **Many processes share one store.** The chapter's cache is one
  machine's memory. Several vfs processes can serve one database, so a
  process-local cache must prove itself fresh against the row. That is
  why principle 12 keys any future cache by `version` (INFERRED).
- **Concurrency is not in this chapter.** vsfs has one caller. vfs's
  guarded updates, savepoint arbitration, whole-batch redrive (ADR 025)
  and the lock row (ADR 078) have no counterpart here (READ, ch. 40;
  READ, the ADRs).
- **The extra tables have no counterpart.** Versions, search indexes and
  rights are about eighteen of vfs's twenty-three tables (§2.1). The
  chapter's I/O arithmetic covers the five regions vsfs has. The rest
  is cost vfs chose for history, search and governance (study 05 §7:
  the per-call SQL count is set by what the mount stores) (READ).
- **Rights are checked on every call, not once at open.** vsfs checks
  permission when `open` runs (p. 12). vfs judges rights on every
  statement path (§2.2: two stamp reads per named call). No fd exists
  to carry an earlier check (READ).

## 5. The one design lesson

Draw vfs's access paths the way the chapter draws vsfs's: one table per
verb, every statement in order, with rows and body bytes counted. Then
pin those tables as tests, because that table is the mental model the
chapter asks for. vfs has already collapsed the costly parts of the
vsfs timeline (the walk per path level, the shared bitmap, the
access-time write) into one bounded step each; what it has not
collapsed is the whole-body cost, where a one-byte edit moves the body
four times, and the engine's own chunked storage underneath is the
place to look first.

One line: count statements, rows and bytes per verb, pin the table,
and the next cost to cut is the whole-body rewrite.
