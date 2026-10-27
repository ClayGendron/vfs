# Study 04: locality and log structure (FFS, LFS, flash SSDs) laid against vfs

- **Date:** 2026-10-24
- **Brief:** `00-brief.md` in this folder.
- **Book section:** OSTEP v1.10, chapter 41 (Locality and the Fast File
  System, PDF pages 553–566), chapter 43 (Log-structured File Systems,
  PDF pages 588–603), chapter 44 (Flash-based SSDs, PDF pages 604–627).
  Page numbers below are the book's own page numbers inside each
  chapter (each chapter restarts at page 1), written `ch43 p.10`.
  Everything from the book is paraphrased; nothing is quoted.
- **vfs:** read at HEAD `ac5c515`. The files read are named where they
  are cited. The main ones: `src/vfs/storage/backends/database/`
  (`versions.py`, `trash.py`, `writes.py`, `staging.py`, `reads.py`,
  `serialized.py`, `topology.py`, `dialects.py`), `src/vfs/models/rows.py`,
  `src/vfs/base.py`, `src/vfs/storage/protocol.py`, ADRs 004, 013, 017,
  027, 074, and yesterday's memo
  `context/research/2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md`
  (cited as *the kernel memo*).
- **Experiment:** one probe script, run here with `uv run` on the
  in-process SQLite backend. It counts rows and statements; it never
  times anything. The script and its full output are in Appendix A.
- **Labels:** every claim is **READ** (book or vfs file), **EXECUTED**
  (the probe), or **INFERRED** (my reasoning).

## Why this section matters to vfs

vfs already behaves a lot like a log-structured store. A write that
replaces a body keeps the old body as a version row. A delete does not
erase; it sets a tombstone, a mark on the row that says it was deleted. Only `sweep`
destroys anything. LFS (the log-structured file system) is the
textbook for exactly that kind of store: one that never overwrites in
place, keeps old copies around, and needs a cleaner to reclaim them.
FFS (the Fast File System) is the textbook for *locality*: putting
things that are read together next to each other. Flash SSDs repeat
the LFS story one layer lower, inside the drive, and add the cost of
keeping the name-to-location map in memory.

So this study asks three questions:

1. Does vfs have a cleaner for everything that piles up, or only for
   some of it? (LFS)
2. Where do a directory's children sit, and what does a listing touch?
   (FFS)
3. What does vfs's name-to-row map cost, and who keeps it? (SSD FTL)

---

## 1. What the chapters say

**Chapter 41, FFS.** The first Unix file system treated the disk as if
any block were as cheap to reach as any other. It was not: a disk pays
a large positioning cost (seek and rotation) before every transfer.
So the old file system spread a file's blocks far from its inode,
fragmented free space, and reached only a tiny share of the disk's
bandwidth (ch41 p.1–2). FFS kept the same system-call interface and
changed only the layout (ch41 p.3). It cut the disk into groups, each
with its own inodes, data blocks and free-space bitmaps (ch41 p.3–4).
Its one rule: put related things in the same group and unrelated
things in different groups. A file's data goes in its inode's group,
and the files of one directory go in that directory's group (ch41
p.5–6). Traces show the rule fits real use: a large share of opens hit
the same file or a sibling of the last one (ch41 p.7–8). Large files
are the exception. FFS spreads them over several groups in big chunks,
so one file cannot fill a group, and it sizes the chunks so that the
seek between chunks is paid back by the transfer. The book calls this
amortization (ch41 p.8–10). FFS also measured each disk's parameters
instead of assuming them, and added long names, symbolic links and an
atomic rename, because a usable system wins adoption (ch41 p.10–12).

**Chapter 43, LFS.** Memory grew, so reads were mostly served from
cache and disk traffic became mostly writes. Sequential writes were
far cheaper than random ones (ch43 p.1). LFS therefore buffers every
update, data and metadata alike, into a large in-memory segment and
writes the segment in one sequential transfer to free space. It never
overwrites anything in place (ch43 p.2–4). The buffer size follows from
the same amortization math as FFS (ch43 p.4–5). Because inodes now move
on every write, LFS adds a level of indirection: the inode map (imap)
takes an inode number to the address of that inode's newest copy
(ch43 p.5–6). A fixed checkpoint region points at the pieces of the
imap and is rewritten only every so often (ch43 p.7). The imap also
stops the recursive update problem: without it, moving an inode would
force a rewrite of its directory, that directory's parent, and so on
to the root (ch43 p.8). The price of never overwriting is garbage: old
copies of data and inodes left behind (ch43 p.9). A cleaner reads a
few partly-dead segments, copies their live blocks into fewer new
segments, and frees the old ones whole (ch43 p.9–10). To know which
blocks are live, each segment carries a summary that says, for every
block, which file and which offset it belongs to. A block is live only
if that file's current inode still points at it. A per-file version
number makes the check cheaper (ch43 p.10–11). Policy is the hard part:
clean when idle, on a schedule, or when full; and clean cold segments
sooner than hot ones (ch43 p.11). Crash recovery uses two checkpoint
regions written alternately with timestamps, then rolls forward
through the log written after the last checkpoint (ch43 p.12). The
chapter's closing tip: NetApp's WAFL turned the garbage into a feature
by exposing old versions as snapshots, which also means it has to
clean less often; it still deletes them eventually (ch43 p.13).

**Chapter 44, flash SSDs.** A flash chip reads a page fast, but can
only write a page that was erased first, and erases whole blocks of
many pages at a time. Erase is slow, and each block survives a limited
number of erase cycles before it wears out (ch44 p.2–5). The flash
translation layer (FTL) hides this and offers a plain block device
(ch44 p.6). A direct map (logical page N always lives at physical page
N) is terrible: every small write rewrites a whole block (ch44 p.7).
So nearly every FTL is log-structured: it appends each write to the
next free page and records the new location in a mapping table (ch44
p.8–9). That brings back LFS's two costs. First, garbage: overwrites
leave dead pages, a collector must copy the live pages out and erase
the block, and that copying inflates write amplification, the ratio of
bytes the device writes to bytes the client asked to write (ch44
p.6–7, 10–11). Second, the mapping table is big: one entry per page
costs memory in proportion to the device (ch44 p.12). Fixes: map whole
blocks (small table, terrible small writes), a hybrid with a small
per-page log table in front of a per-block data table, or keep the
full page map on flash and cache only the hot part (ch44 p.12–16). The
device can rebuild the map after power loss by scanning per-page
out-of-band records, or faster with checkpoints (ch44 p.10). A trim
command lets the file system tell the device a range is dead (ch44
p.12). Spare capacity lets the collector work in the background (ch44
p.12). Wear leveling moves long-lived data so all blocks age evenly
(ch44 p.17).

---

## 2. Principles vfs should adopt

Status words: **follows**, **half follows**, **does not**. The change
is the one concrete change the principle implies, if any. It is a
pointer for the synthesis, not a recommendation for vfs as a whole.

### From LFS: the cleaner

**P1. Every kind of garbage a no-overwrite store makes needs a named
cleaner.**
- Source: ch43 p.9–10 (old versions are garbage; a cleaner reclaims
  them); ch43 p.13 (WAFL keeps old versions as a feature but still
  deletes them eventually).
- vfs today: **half follows.**
  - vfs makes three kinds of garbage. (a) Tombstoned rows. (b) Version
    rows: every overwrite keeps the replaced body whole
    (`versions.py`, READ). (c) Orphaned body rows: a content or blob row
    whose entry is gone (`trash.py` `_reclaim_orphan_content`, READ).
  - Kinds (a) and (c) have a cleaner: the retention arm of `sweep`
    (`trash.py` `sweep_rows`, ADR 074 item 8, READ).
  - Kind (b) has **no cleaner while the file is live**. The only code
    that deletes version rows is `_purge`, which runs when the entry
    itself is destroyed (`trash.py` line 581; a repo-wide search finds
    no other reader or deleter of `tables.versions`, READ).
  - EXECUTED (Appendix A): 1,000 files written, then overwritten three
    times with new bodies. Result: 3,000 version rows holding 833,400
    bytes, beside 277,800 live bytes. History is three times the live
    data after three rewrites, and grows by one full copy per rewrite.
    A `sweep` of the trash view with retention 0 then left all 3,000
    rows in place.
  - The schema already names a compaction step: a batch `pack` verb
    that rewrites cold ranges into periodic snapshots plus forward
    diffs (`rows.py` comment on `vfs_versions`; ADR 017 pins 3–4,
    READ). No code writes `version_diff` today (READ: the only hits
    are the model's validators).
- The change: give version rows a cleaner of their own, with a
  retention policy (by count, by age, or both) and the pack step, and
  decide whether `sweep` or a separate verb runs it. INFERRED. This is
  a policy knob, not a scale cap: keep-everything stays a valid
  setting, it just has to be a setting.

**P2. Which copy is live should be answerable without a whole-table
scan.**
- Source: ch43 p.10–11 (segment summary block plus imap; the version
  number shortcut); ch44 p.11 (the FTL stores which logical page each
  physical page holds, then checks the map).
- vfs today: **mostly follows, one gap.**
  - vfs separates live bodies from dead ones *by table*. The current
    body sits in `vfs_content` or `vfs_blobs`, keyed by `entry_id`.
    Old bodies sit in `vfs_versions`. Nothing in `vfs_versions` is
    ever current (`versions.py` docstring; `rows.py`, READ). So vfs
    never has to ask LFS's question for versions: the table answers
    it. INFERRED from READ.
  - Each body row carries a back-pointer, its `entry_id`, exactly the
    role of LFS's segment summary (`rows.py`, READ).
  - Derived rows use LFS's version-number shortcut. Chunks and links
    record the body hash they were built from (`chunk_source_hash`,
    `link_source_hash`), and every write guards on `version`
    (ADR 013 pin 1; `rows.py`, READ).
  - The gap: an orphaned body is found by an anti-join over the whole
    body table, inside the serialized sweep transaction. The
    docstring says so and names the direction: run it rarely as its
    own maintenance verb, or reclaim at purge time and retire the scan
    (`trash.py` `_reclaim_orphan_content`, READ).
- The change: run the orphan check in bounded key ranges of
  `entry_id` per call, the way the LFS cleaner takes a few segments at
  a time (ch43 p.10). INFERRED.

**P3. Clean in bounded units, not in one pass over everything.**
- Source: ch43 p.10 (the cleaner reads M segments and writes N);
  ch43 references p.14 (Mogul: holding writes back too long and then
  flushing in a burst can hurt reads).
- vfs today: **half follows.**
  - Every sweep statement is chunked by the dialect budget, and the
    statement count is flat in batch size. EXECUTED: sweeping 900
    tombstoned roots took 17 statements; sweeping an empty trash took 5.
  - But one sweep call is one transaction over *all* expired roots,
    plus the orphan scan, while holding the per-mount serialization
    point (`trash.py` `sweep_rows`; `serialized.py` docstring, READ).
    The serialization point does not block reads or writes, only the
    other serialized verbs (delete, restore, move, copy) (READ). On a
    corpus with millions of expired rows, that one transaction is long.
    INFERRED.
- The change: let `sweep` take a limit and return a resumption key, so
  a deployment job cleans in slices. This is the same cursor shape the
  kernel memo proposes for `ls` (kernel memo §4.2). INFERRED.

**P4. When to clean is a policy the cleaner needs inputs for.**
- Source: ch43 p.11 (clean on a schedule, when idle, or when full).
- vfs today: **follows on who cleans, not on what the cleaner can look at.**
  - vfs decided that storage owns no background work. The deployment
    schedules `sweep`; there is no daemon (ADR 013 pin 5; ADR 027
    pin 4, READ). `sweep` is a developer-plane verb that agents never
    see (`base.py` `sweep` docstring, READ). This is a deliberate and
    good choice: a database-backed library should not run its own
    threads.
  - vfs cannot clean on a full disk, because it does not know the
    database's free space. INFERRED.
  - What a scheduler has today: nothing cheap that says how much
    garbage exists. There is an index on `deleted_at`, so a tombstone
    count is one seek (`rows.py`, READ). There is no equivalent for
    version bytes. INFERRED.
- The change: a cheap garbage gauge per mount (tombstoned rows, version
  rows and bytes) that a deployment job can read before it decides to
  clean. INFERRED.

**P5. Separate hot data from cold data so the cleaner does less
copying.**
- Source: ch43 p.11 (hot segments are being overwritten and should be
  left to die further; cold segments should be cleaned sooner); ch44
  references p.21 (the unwritten-contract paper lists grouping by death
  time among its rules).
- vfs today: **half follows.**
  - vfs groups by death time already, in two places. Live bodies and
    history live in different tables (P2). Tombstones are found by
    their own `deleted_at` index and purged as a set by
    `trash_root_id` (`rows.py`; ADR 074 item 8, READ).
  - The planned pack step targets cold version ranges and leaves the
    recent ones as full snapshots (`rows.py` comment, READ). That is the
    LFS hot/cold rule. It is not built yet.
  - A gap the book makes visible: a hot file (one rewritten by every
    nightly ETL run) makes almost all of the version garbage. A cold
    file makes almost none. A retention rule that is per mount, not per
    file, treats them the same. INFERRED.
- The change: when the version cleaner (P1) is designed, let its policy
  see per-file churn, not only age. INFERRED.

**P6. Turn the garbage into a feature, but still clean it.**
- Source: ch43 p.13 (WAFL's snapshots).
- vfs today: **half follows.**
  - vfs did exactly the WAFL move. Its garbage is a feature: every
    version row names who wrote it, how the authority was proven, the
    subjects it acted for, and the grant revision in force
    (`versions.py`; ADR 064, READ). A write at a tombstoned path revives
    the row and mints a version of the body it replaced (ADR 074 item 5,
    READ).
  - But today the feature has no reader. No verb returns a version
    row; the kernel memo lists a future `history(path)` read
    (kernel memo §4.3; READ: no code selects from `vfs_versions`).
  - WAFL's second half, deleting old versions in the background, is P1.
- The change: none beyond P1 and the planned history read. INFERRED.

**P7. Let the store's own log do crash recovery; keep vfs's derived
state on a checkpoint-plus-tail model.**
- Source: ch43 p.12 (two checkpoint regions, then roll forward over the
  log tail); ch44 p.10 (rebuild the map from per-page records, or use
  checkpoints to go faster); ch44 p.14–16 (hybrid FTL: a small log
  table consulted first, then the big data table).
- vfs today: **follows.**
  - vfs has no checkpoint region and needs none. Each verb runs in one
    SQL transaction that the backend method owns (`reads.py`,
    `writes.py` docstrings, READ). The engine's own write-ahead log does
    what LFS's checkpoint and roll forward do. INFERRED.
  - vfs's *derived* indexes already work the LFS way. Each entry has
    dirty flags (`chunked`, `encoded`) that every content write
    resets. grep reads the index for rows with `encoded` true and scans
    the rest (ADR 013 pin 3, READ). The gram epoch is the checkpoint;
    the unencoded rows are the log tail; grep's scan side is the roll
    forward. It is also the FTL's hybrid map: a small scanned part in
    front of a large indexed part. INFERRED from READ.
- The change: none. Name the pattern so later indexes copy it.
  INFERRED.

### From FFS: locality

**P8. Keep the interface; change the layout underneath.**
- Source: ch41 p.3 (FFS kept open, read, write and close and changed
  only the on-disk structures); ch44 p.6 (the SSD keeps the block
  interface and hides flash behind it).
- vfs today: **follows, and the kernel memo builds on it.** The
  `Supports*` protocols are the interface (`protocol.py`, READ). The
  kernel memo's whole recommendation is a stable kernel interface with
  facets over it (kernel memo §0, §4.1, READ).
- The change: none from this section.

**P9. Put the rows a common query reads together in the order it reads
them.**
- Source: ch41 p.5–6 (place a directory's files in the directory's
  group); ch41 p.7–8 (traces: siblings are often opened one after
  another); ch44 references p.21 (locality still matters on SSDs).
- What locality means in a SQL store (INFERRED): there are no
  cylinders. There are index pages and table pages. Two rows are
  near each other if they share an index page, and a query is cheap if it walks
  one contiguous key range and does not jump to scattered table pages.
- vfs today: **half follows.**
  - The listing index is right. `ls` selects children by `parent_id`
    and orders by `(parent_id, name)` (`reads.py`
    `_children_by_parent`, READ). The unique constraint
    `uq_vfs_entries_parent_name` is exactly that key (`rows.py`, READ).
    So in the index, a directory's children are one contiguous run, in
    name order. That is FFS's directory-group rule, applied to an
    index. EXECUTED: SQLite's plan for the children select is a search
    of that index on `parent_id`.
  - The table rows are not. The `vfs_entries` table is keyed by an
    integer surrogate `id` in insert order (`rows.py`, READ). EXECUTED:
    eight single-file writes alternating between `/a` and `/b` gave
    `/a`'s children ids 2005, 2008, 2010, 2012 and `/b`'s 2007, 2009,
    2011, 2013. That is the spread-out layout ch41 p.6 shows as the bad
    case. A listing finds the children in one index run, then fetches
    each row from wherever it landed. INFERRED: on SQLite, MariaDB and
    SQL Server the table is clustered on `id`; on Postgres it is a heap
    in insert order; in all of them siblings written at different times
    land on different table pages.
  - Tombstones sit inside the listing's key range. A tombstoned row
    keeps its `(parent_id, name)` (ADR 074 item 1, READ). The index
    does not hold `deleted_at`, so the liveness filter runs after the
    table lookup. EXECUTED: after deleting 900 of 1,000 children,
    `ls` returned 100 rows, but the `parent_id` key range still held
    1,000 rows until `sweep` ran. INFERRED from the EXECUTED plan: the
    listing looked up all 1,000 to return 100. This is LFS's lesson in
    a new place: garbage interleaved with live data costs *read* work,
    not only space.
- The change: when the `ls` cursor lands (kernel memo §4.2), page
  through an access path whose key keeps the live children
  contiguous, or covers the listed columns, and pin the result as a
  count of rows visited per page on each engine. INFERRED. Candidate
  shapes, each to be checked per engine: a covering index for the
  narrow projection; a listing index that leads with
  `(parent_id, deleted_at)`; or simply bounding tombstone density with
  the sweep schedule. The cursor already has the right key:
  `(parent_id, name)`, which `reads.py` orders by.

**P10. Keep big bodies out of the narrow row that metadata queries
read.**
- Source: ch41 p.8–10 (the large-file exception: big files must not
  crowd out their neighbours).
- vfs today: **follows.** The entries row holds identity and metadata,
  never bodies, so a metadata write never rewrites content. Bodies live
  in `vfs_content` and `vfs_blobs`, with the body column physically
  last. On Postgres the bytes column is set to `EXTERNAL` storage, so a
  substring read is a ranged fetch (`rows.py`; `_attach_blob_storage_ddl`,
  READ).
- The change: none.

**P11. Size each unit of work so the fixed cost per unit is paid
back.**
- Source: ch41 p.9–10 and ch43 p.4–5 (amortization: the bigger the
  transfer per positioning cost, the closer to peak bandwidth).
- vfs today: **follows, by a different rule.**
  - The fixed cost in vfs is a statement round trip, not a seek.
    INFERRED.
  - vfs batches by declared engine budgets: bind parameters,
    `IN`-list length, and 8 MiB of body per bulk blob statement
    (`dialects.py` `BLOB_PAGE_BYTES`; CLAUDE.md, READ).
  - EXECUTED: overwriting 1,000 files took 17 statements, version mint
    included. The kernel memo's probe wrote 10,000 files in 40
    statements (kernel memo §2, READ).
  - The budgets come from correctness caps, not from an amortization
    calculation. At these counts that does not matter: the fixed cost
    is already a rounding error. INFERRED.
- The change: none.

**P12. Read the device's parameters; do not assume them.**
- Source: ch41 p.11 (FFS measured each disk's timing and laid blocks
  out to match).
- vfs today: **follows.** CLAUDE.md requires reading facts off the live
  SQLAlchemy dialect, and `dialects.py` reads single-value caps from the
  live server (`ValueCap`, READ).
- The change: none. The book's own footnote also applies: once disks
  hid their geometry, file systems stopped modelling it (ch41
  p.11–12). vfs should likewise not model an engine's page layout
  beyond choosing keys and indexes. INFERRED.

### From LFS and the FTL: indirection and the map

**P13. Use a stable identity as the indirection, so moving a thing
does not rewrite everything that points at it.**
- Source: ch43 p.5–6 (the imap; indirection lets structures move
  without updating every reference, at some cost); ch43 p.8 (the imap
  stops the recursive update up the tree).
- vfs today: **follows for references, deliberately not for the path
  cache.**
  - Every durable dependent (content, versions, chunks, edges) keys on
    `entry_id`, a ULID. `parent_id` is the one structural pointer. A
    rename rewrites zero chunk rows (ADR 004, ADR 019; `rows.py`, READ).
    That is the imap's job, done.
  - The path is stored on every row as a cache (ADR 004, READ). So a
    `move` rewrites the path of every descendant, and the glob segment
    postings with it (`topology.py` docstring, READ). That is the
    recursive update problem, going down the tree instead of up. vfs
    pays it on purpose: rights travel as sorted path ranges joined to
    the path index (ADR 072, READ), and subtree reads use one sargable
    `LIKE` on the path (`reads.py`, READ).
  - A create bumps its parent's version one level up, and only when the
    directory's membership changes (`staging.py` `derive_bumps`, READ).
    ADR 013 pin 5 already names this as contention to remove later by
    deriving directory change state at read time (READ). That is also
    LFS's fix: let the indirection absorb the change instead of the
    parent.
- The change: none from this section. The path-cache trade is an
  existing decision.

**P14. Know what your name-to-location map costs, and who keeps it.**
- Source: ch44 p.12 (a page-level map costs memory in proportion to
  the device); ch44 p.16 (keep the full map on flash and cache the hot
  part).
- vfs today: **follows, by handing the map to the database.**
  - vfs keeps no in-process map from path to row. Every resolution is a
    lookup in a database index (`reads.py` point reads are `path IN`
    selects, READ). The engine's buffer pool caches the hot index pages.
    That is the FTL's page map plus caching, for free. INFERRED.
  - The cost moves into index size. `vfs_entries` carries three name
    maps: the unique `path` index, the unique `(parent_id, name)`
    index, and `(everyone_level, path)` (`rows.py`, READ). The path is
    long, so two of the three have long keys. The glob segment postings
    mirror the path again (`topology.py`, READ). EXECUTED: SQLite shows
    13 indexes on `vfs_entries`.
  - Each index is also write amplification (P15). INFERRED.
- The change: none now. When an index is added to `vfs_entries`, count
  it as a map the database must keep warm. INFERRED.

**P15. Measure write amplification, and count it, not time it.**
- Source: ch44 p.6–7 (write amplification defined); ch44 p.10–11 and
  p.17 (garbage collection and wear leveling raise it).
- vfs today: **half follows.**
  - The kernel memo measured that a one-row create issues nine
    statements, four of them the verb's own (kernel memo §2, READ).
  - A content overwrite writes: the entry row, a delete and an insert
    of the body row, a full-snapshot version row, and later the chunk
    and posting rows (`writes.py`, `versions.py` docstrings, READ).
  - INFERRED (not measured here): on Postgres an UPDATE writes a new
    row version, and it can skip new index entries only when no
    indexed column changed. A content write changes `content_hash`,
    `encoded` and `render_status`, all indexed, so each overwrite
    likely adds an entry to every index on the table. This is general
    knowledge of Postgres MVCC, not studied from the Postgres source
    for this memo.
  - CLAUDE.md already requires performance pins to count operations
    (READ). There is no pin today for rows or bytes written per file
    overwritten. INFERRED from not finding one; not exhaustively
    checked.
- The change: a counted pin of rows written per overwritten file,
  version and index rows included, so the ratio cannot drift
  silently. INFERRED.

---

## 3. Nouns and verbs

Adopt name means use the book's word in vfs. Concept means keep
the idea under vfs's own name. Not have means vfs should deliberately
not have it.

### Nouns

| Book term (chapter, page) | What it is | vfs today | Call | Why |
|---|---|---|---|---|
| inode (ch41, ch43 p.5) | per-file metadata record | entry row in `vfs_entries`, identity `entry_id` | concept | vfs's row is richer (rights, render, index state); the word inode would mislead |
| inode number | stable file identity | `entry_id` (ULID) | concept | ADR 004 and ADR 019 settled it |
| superblock (ch41 p.1, p.4) | whole-volume facts | `vfs_meta` row plus the mount binding | concept | already split between storage and the router (`base.py`) |
| cylinder group / block group (ch41 p.3–4) | a region where related data is placed | none | not have | the engine owns placement; vfs chooses keys, not pages |
| placement policy (ch41 p.5) | which group a new file goes to | index key choice, e.g. `(parent_id, name)` | concept | in SQL, locality is a key order (P9) |
| sub-block / small-file fragment (ch41 p.10) | small allocation for small files | none | not have | a small body is just a short value in a row |
| large-file chunk (ch41 p.8) | a big file's spread-out piece | none for bodies; bodies are whole rows | not have yet | the kernel memo names chunked blobs only if a front needs ranged writes (§4.5) |
| symbolic link (ch41 p.12) | an alias path | none | not have | parked by ADRs 011 and 021 (one path per entry for rights) |
| segment (ch43 p.3) | a large buffered unit of writes | a batch, sliced by `chunked()` and `BLOB_PAGE_BYTES` | concept | the batch contract is vfs's segment |
| inode map, imap (ch43 p.5) | inode number to newest copy | the unique `path` index plus `entry_id` | concept | the database keeps it (P14) |
| checkpoint region (ch43 p.7) | fixed root of the map | the engine's own log; for derived indexes, the gram epoch | not have (storage) / concept (indexes) | P7 |
| segment summary block (ch43 p.10) | per-block back-pointer to file and offset | `entry_id` on every body, version and chunk row | concept | P2 |
| version number (ch43 p.11) | per-file counter for cheap liveness | `version` column; version rows numbered by it | concept | ADR 013, ADR 017 |
| garbage (ch43 p.9, ch44 p.10) | dead copies | tombstoned rows, version rows, orphan bodies | adopt name (in docs) | naming the three kinds makes the missing cleaner visible (P1) |
| cleaner / garbage collector (ch43 p.9, ch44 p.11) | reclaims dead copies | `sweep` (tombstones, orphans only) | concept | `sweep` is a good name; it needs a version arm (P1) |
| hot / cold segment (ch43 p.11) | churning vs stable data | none | concept | P5; useful vocabulary for the version policy |
| liveness (ch43 p.10) | is this copy current? | `liveness_filters`, `tombstone_side` (`descent.py`) | already adopted | vfs uses the word |
| log, roll forward (ch43 p.12) | writes since the checkpoint, replayed | grep's scan side over `encoded = false` rows | concept | P7 |
| versioning file system, snapshot (ch43 p.9, p.13) | keeping old versions on purpose | version rows, `is_snapshot` | concept | P6 |
| copy-on-write / shadow paging (ch43 p.12) | write new, never overwrite | partly: bodies are replaced in place, history copied out first | concept | see section 4: vfs is closer to an undo log |
| flash page, erase block (ch44 p.2) | write unit vs erase unit | none | not have | below the database |
| FTL, mapping table (ch44 p.6, p.8) | logical to physical map | path index in the engine | concept | P14 |
| log table / data table, hybrid map (ch44 p.14) | small fine map in front of a big coarse one | grep's overlay: scan side plus index side | concept | P7 |
| out-of-band area (ch44 p.10) | per-page record used to rebuild the map | `parent_id` + `name`, from which `path` is regenerable | concept | ADR 004 calls path a regenerable cache |
| write amplification (ch44 p.6) | device bytes per client byte | none | adopt name | P15; it is a metric word, useful in pins and memos |
| wear leveling (ch44 p.17) | spread erases evenly | none | not have | the engine and the drive handle it |
| overprovisioning (ch44 p.12) | spare space so cleaning can wait | the `trash_days` retention window, loosely | not have | the analogy is weak; vfs does not manage space |

### Verbs

| Book verb | vfs today | Call | Why |
|---|---|---|---|
| allocate / place (ch41 p.5) | insert with a key | not have | the engine places rows |
| rename, atomic (ch41 p.12) | `move` (one transaction; refuses `exists`) | concept | `replace=` is in flight (spec 167; kernel memo §4.2) |
| defragment (ch41 p.2) | the planned pack step | concept | ADR 017 pin 4 names it; unbuilt (P1) |
| buffer then write (ch43 p.3) | the batch call | concept | already the 10,000-row contract |
| clean (ch43 p.9) | `sweep` | concept | keep `sweep`; add the version arm (P1) |
| checkpoint (ch43 p.7) | reindex advancing the epoch | concept | P7 |
| roll forward (ch43 p.12) | grep's scan side | concept | P7 |
| trim (ch44 p.12) | `delete` (tombstone) tells `sweep` what is dead | concept | the tombstone is vfs's trim |
| merge: switch, partial, full (ch44 p.15–16) | none | not have | device-level |
| erase / program (ch44 p.3) | none | not have | device-level |

---

## 4. What does not transfer

**A row store is not a disk.** FFS and LFS exist because a disk pays a
large positioning cost and a sequential transfer is nearly free (ch41
p.1–2; ch43 p.1). vfs never sees a seek. Its fixed cost is a statement
round trip, and its unit of placement is an index key, not a block
address. So the book's arithmetic (how many megabytes per seek) does
not carry over. The *shape* of the argument does: pay a fixed cost
rarely and move a lot per payment (P11). INFERRED.

**vfs is not log-structured at the body level.** This is the most
important break in the analogy. LFS writes the new copy somewhere new
and leaves the old copy where it was (ch43 p.2). vfs does the
opposite for the live body. It copies the old body out into a version
row, then replaces the body row at the same key (`versions.py`:
the mint reads the pre-image and runs before the bodies are replaced;
`writes.py`: content delete-then-insert, READ). The entry row is
updated in place under a version guard (ADR 013 pin 1, READ). That is
closer to a database undo log than to LFS. The consequence is good:
vfs never needs an imap to find the current copy, because the current
copy is always at its key. INFERRED from READ.

**The layers below vfs are already log-structured.** Postgres keeps
old row versions until vacuum reclaims them (general knowledge,
INFERRED). The SSD under it runs a log-structured FTL with its own
garbage collector (ch44 p.8–11). So a vfs overwrite on Postgres on
flash can be cleaned three times: by a future vfs version cleaner, by
vacuum, and by the drive. The book's own references point at this
problem of redundant maps across layers (ch43 and ch44 references, the
nameless-writes paper). vfs cannot remove the lower two. It should not
add a fourth physical log of its own. Its history should stay a
*semantic* feature (who wrote what), and physical cleaning should stay
with the engine. INFERRED.

**Crash recovery is the engine's job.** Two alternating checkpoint
regions with timestamps (ch43 p.12) and out-of-band scans (ch44 p.10)
solve a problem SQL transactions already solve. vfs commits each verb
as one transaction. The only place vfs needs the checkpoint idea is its
derived indexes, and it already has it (P7). INFERRED.

**Wear, erase blocks and disturbance do not exist at vfs's layer.**
Wear leveling (ch44 p.17) and program disturbance (ch44 p.7) belong to
the drive. Nothing in vfs should model them. INFERRED.

**Placement groups do not exist.** FFS chooses a group for each new
directory (ch41 p.5). vfs cannot choose a page. What it can choose is
the key of each index and which index a query walks. That is the whole
of locality in a SQL store (P9). Clustering a table by a key is
possible on some engines and not others; vfs should not depend on it.
INFERRED.

**Free space is not visible.** LFS can clean when the disk is full
(ch43 p.11). vfs does not know how full the database is, and the
policy that storage owns no background work means it would not act on
it anyway (ADR 013 pin 5, READ). The scheduler lives in the
deployment (P4).

**Small-file tricks do not apply.** FFS's sub-blocks (ch41 p.10) save
space inside fixed-size blocks. A row stores a short value at its own
length. INFERRED.

---

## 5. The one design lesson

A store that never throws a write away needs a cleaner for every kind
of leftover it makes, and vfs today cleans deleted files and orphan
bodies but not the version rows that every overwrite of a live file
leaves behind (EXECUTED: three rewrites of 1,000 files left three times
the live bytes in history, untouched by `sweep`). The same lesson
shows up in listings: tombstones sit in the `(parent_id, name)` key
range beside live children, so garbage costs read work until it is
swept, which the coming `ls` cursor must page around or bound. Locality
in a SQL store is key order, and vfs already has the right key for
siblings; what it lacks is a version cleaner, bounded cleaning slices,
and a gauge that tells a scheduler how much garbage there is.

One-line version: vfs is a versioning store with a cleaner for deletes
only; it needs one for history, run in slices, and its listing cursor
must account for tombstones in the key range.

---

## Appendix A. The probe (EXECUTED)

Run from the repo root on 2026-10-24 at HEAD `ac5c515`:
`uv run python <scratchpad>/s04exp/lfs_probe.py`. The script lived in
the session scratchpad, not in the repo; it is reproduced here in full.
It uses `InMemoryStorage` (the database backend over in-process
SQLite) with `trash_days=0`, so a retention sweep reclaims every
tombstone. The statement counts exclude the probe's own counting
queries.

Output:

```text
etl gen 0: ok=True statements=21 versions=0 version_bytes=0 live_bytes=277800
etl gen 1: ok=True statements=17 versions=1000 version_bytes=277800 live_bytes=277800
etl gen 2: ok=True statements=17 versions=2000 version_bytes=555600 live_bytes=277800
etl gen 3: ok=True statements=17 versions=3000 version_bytes=833400 live_bytes=277800
identical rewrite: versions=3000
sweep(trash, days=0) with no tombstones: ok=True observed=0 versions_after=3000 statements=5 [BEGIN=1, SELECT=4]
delete 900 children: ok=True statements=5 [BEGIN=1, SELECT=2, UPDATE=2]
ls(/d) after delete: rows=100 statements=3 rows_in_(parent_id,name)_range=1000
  children select: SELECT vfs_entries.parent_id, vfs_entries.content_hash, vfs_entries.created_at, vfs_entries.deleted_at, vfs_entries.kind, vfs_entries.mime_type, vfs_entries.path, vfs_entries.render_status, vfs_entries.size_bytes, vfs_entries.source, vfs_entries.updated_at, vfs_entries.version FROM vfs_entries WHERE vfs_entries.parent_id IN (?) AND vfs_entries.deleted_at IS NULL AND vfs_entries.path != ? AND vfs_e
  plan of children select: SEARCH vfs_entries USING INDEX sqlite_autoindex_vfs_entries_1 (parent_id=?)
sweep(trash, days=0) after delete: observed=900 statements=17 [BEGIN=1, DELETE=9, SELECT=6, UPDATE=1] rows_in_range_after=100
versions still held (live /etl history): 3000
surrogate ids of /a children: [2005, 2008, 2010, 2012]; of /b children: [2007, 2009, 2011, 2013]
entries indexes: ['ix_vfs_entries_content_hash', 'ix_vfs_entries_deleted_at', 'ix_vfs_entries_encoded_kind', 'ix_vfs_entries_entry_id', 'ix_vfs_entries_everyone_path', 'ix_vfs_entries_ext', 'ix_vfs_entries_ext_kind', 'ix_vfs_entries_kind', 'ix_vfs_entries_owner_id', 'ix_vfs_entries_path', 'ix_vfs_entries_render_status', 'ix_vfs_entries_trash_root', 'sqlite_autoindex_vfs_entries_1']
```

A separate check (EXECUTED) confirmed that `sqlite_autoindex_vfs_entries_1`
is the unique `(parent_id, name)` constraint.

How to read it:

- **Rows 1–4.** Each overwrite generation mints one full-snapshot
  version per file. History grows by one live-corpus copy per rewrite.
- **Row 5.** Rewriting identical bodies mints nothing, as `versions.py`
  promises.
- **Row 6.** A retention sweep with no tombstones touches no version
  row.
- **Rows 7–10.** After 900 deletes, the listing returns 100 rows, but
  the index range it searches still holds 1,000 rows. The plan
  searches on `parent_id` only, so the `deleted_at IS NULL` test runs
  per row after the lookup (INFERRED from the plan).
- **Row 11.** Sweeping 900 roots takes 17 statements; the key range
  drops back to 100.
- **Row 13.** Siblings written at different times get interleaved
  surrogate ids, so they land apart in the table's own order.

Limits: SQLite only, 1,000 rows, no real engine. Rows visited are
inferred from the plan, not counted by the engine. The Postgres and SQL
Server behaviour in P9 and P15 is INFERRED and should be measured on
the engine legs before any decision rests on it.

<details>
<summary>The probe script</summary>

```python
"""Study 04 probe: version growth, sweep reach, tombstones in a listing, sibling locality.

Counts rows and statements; never times. SQLite in-process (InMemoryStorage).
"""

from __future__ import annotations

import asyncio
from collections import Counter

from sqlalchemy import event, text

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.models import Entry, Observation
from vfs.storage.backends.memory import InMemoryStorage

N = 1_000


async def count(storage, sql: str) -> int:
    async with storage._host.engine.connect() as conn:
        return int((await conn.execute(text(sql))).scalar_one())


async def rows(storage, sql: str):
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(text(sql))).all()


async def main() -> None:
    storage = InMemoryStorage(trash_days=0)
    fs = VirtualFileSystem(storage=storage)
    sysa = Authority.system()
    await storage.first_touch()
    stmts: list[str] = []

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def rec(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        stmts.append(statement)

    def heads() -> str:
        return ", ".join(f"{k}={v}" for k, v in sorted(Counter(s.split(None, 1)[0] for s in stmts).items()))

    out: list[str] = []
    # 1. ETL rewrite: N files written, then overwritten three times with new bodies.
    for gen in range(4):
        stmts.clear()
        r = await fs.write([Entry(path=f"/etl/f{i:04}.txt", content=f"gen {gen} row {i}\n" * 20) for i in range(N)],
                           parents=True, overwrite=True, authority=sysa)
        v = await count(storage, "select count(*) from vfs_versions")
        vb = await count(storage, "select coalesce(sum(length(content)),0) from vfs_versions")
        cb = await count(storage, "select coalesce(sum(length(content)),0) from vfs_content")
        out.append(f"etl gen {gen}: ok={r.success} statements={len(stmts)} versions={v} version_bytes={vb} live_bytes={cb}")
    # Identical rewrite mints nothing.
    await fs.write([Entry(path=f"/etl/f{i:04}.txt", content=f"gen 3 row {i}\n" * 20) for i in range(N)],
                   overwrite=True, authority=sysa)
    out.append(f"identical rewrite: versions={await count(storage, 'select count(*) from vfs_versions')}")
    # Sweep at the trash head with retention 0: no tombstones, so live history is untouched.
    stmts.clear()
    s = await fs.sweep(authority=sysa)
    n, h = len(stmts), heads()
    out.append(f"sweep(trash, days=0) with no tombstones: ok={s.success} observed={len(s.observations)} "
               f"versions_after={await count(storage, 'select count(*) from vfs_versions')} statements={n} [{h}]")

    # 2. Tombstones inside a listing: 1000 children, delete 900, ls the parent.
    await fs.write([Entry(path=f"/d/c{i:04}.txt", content=f"{i}\n") for i in range(N)], parents=True, authority=sysa)
    stmts.clear()
    d = await fs.delete(observations=[Observation(path=f"/d/c{i:04}.txt", kind="file") for i in range(900)], authority=sysa)
    out.append(f"delete 900 children: ok={d.success} statements={len(stmts)} [{heads()}]")
    pid = (await rows(storage, "select entry_id from vfs_entries where path='/d'"))[0][0]
    stmts.clear()
    ls = await fs.ls("/d", authority=sysa)
    ls_stmts = list(stmts)
    in_range = await count(storage, f"select count(*) from vfs_entries where parent_id = x'{pid.hex()}'")
    out.append(f"ls(/d) after delete: rows={len(ls.observations)} statements={len(ls_stmts)} "
               f"rows_in_(parent_id,name)_range={in_range}")
    sel = [s for s in ls_stmts if "parent_id IN" in s or "parent_id =" in s]
    if sel:
        out.append("  children select: " + " ".join(sel[-1].split())[:400])
        plan = await rows(storage, "explain query plan " + sel[-1].replace("?", "NULL"))
        out.append("  plan of children select: " + " | ".join(str(p[-1]) for p in plan))
    stmts.clear()
    s = await fs.sweep(authority=sysa)
    n, h = len(stmts), heads()
    in_range2 = await count(storage, f"select count(*) from vfs_entries where parent_id = x'{pid.hex()}'")
    out.append(f"sweep(trash, days=0) after delete: observed={len(s.observations)} statements={n} [{h}] "
               f"rows_in_range_after={in_range2}")
    vers = await count(storage, "select count(*) from vfs_versions")
    out.append(f"versions still held (live /etl history): {vers}")

    # 3. Sibling locality: alternate single-file writes between two directories.
    for i in range(8):
        await fs.write([Entry(path=f"/{'ab'[i % 2]}/x{i}.txt", content="x\n")], parents=True, authority=sysa)
    a = await rows(storage, "select id, path from vfs_entries where path like '/a/%' order by name")
    b = await rows(storage, "select id, path from vfs_entries where path like '/b/%' order by name")
    out.append(f"surrogate ids of /a children: {[r[0] for r in a]}; of /b children: {[r[0] for r in b]}")
    idx = await rows(storage, "select name from pragma_index_list('vfs_entries')")
    out.append(f"entries indexes: {sorted(r[0] for r in idx)}")
    await fs.close()
    print("\n".join(out))


asyncio.run(main())
```

</details>
