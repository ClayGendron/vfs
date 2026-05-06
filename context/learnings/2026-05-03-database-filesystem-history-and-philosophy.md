# Database Filesystems — History, Patterns, Philosophy

- **Date:** 2026-05-03
- **Owner:** research
- **Status:** snapshot — chronological survey and synthesis. Extended 2026-05-03 with relations/edges deep-dive. Complements the 2026-02-17 modern landscape doc.

## Why this doc exists

The existing [2026-02-17 database VFS patterns](2026-02-17-database-vfs-patterns.md) doc covers the modern landscape — TOAST, SQLite VFS, FILESTREAM, lakeFS, Dolt, Perkeep, AgentFS, RLS — at the level needed to make implementation choices today. It does not say where any of this came from, why it keeps repeating, or which threads VFS should explicitly trace itself back to. This doc fills that gap. It walks the chronology from the first "DB-as-FS" experiments in the 1960s through the table-format era of 2024, surfaces the design tensions that persist across decades, distills the patterns that survived, and ends with the philosophy and the rules VFS contributors are expected to internalize.

VFS is not the first system to claim that the filesystem and the database should be the same primitive. It is the first one we know of that makes that claim *for agents specifically*, on the grounds that agents interact with state through reading, writing, and grepping rather than through SQL. That position has a long lineage on both sides — the systems that fused FS and DB and the systems that deliberately kept them apart — and the constitution's choices are best understood as deliberate selections from that lineage.

## The chronology

### 1960s — the first fusion (and its rebuttal)

#### Multics segments and single-level store (1965–)

The first system to seriously argue that "files" and "memory" and "the database" should not be separate primitives was [Multics](https://multicians.org/history.html). Daley and Neumann's 1965 FJCC paper [*A General Purpose File System for Secondary Storage*](https://multicians.org/fjcc4.html) defines the segment as the unit of both addressable memory and persistent storage; programs access files by issuing memory references, and the OS pages segments to and from disk. The [single-level store](https://en.wikipedia.org/wiki/Single_level_store) explicitly discards the file/memory distinction.

Novel: hierarchical pathnames as the primary handle to structured persistent state; symbolic naming as a level of indirection above physical addresses.
Aged well: the hierarchical namespace; pathname normalization; access-control lists at every node.
Aged badly: the conflation of memory addressing and storage addressing — modern systems separate them so that crash recovery, replication, and tiered storage can each be reasoned about independently.
For VFS: the namespace-as-world-model thesis is older than Unix. The constitution's Article 1 inherits it.

#### IBM IMS (1968)

[IMS](https://www.ibm.com/history/information-management-system) shipped in August 1968 to manage the bill of materials for the Saturn V. It is a hierarchical DBMS — segments arranged in parent-child trees — and it ran (still runs) atop OS/360 as a layer above the filesystem, not as a replacement for it. IMS picked the same shape Multics picked (a tree of named records) and applied it to transactional business data.

Novel: the hierarchical data model formalized for OLTP, before Codd's relational paper.
Aged well: hierarchical models survived as a niche (XML, JSON, document stores). IMS itself remained in production at >95% of Fortune 1000s [[twobithistory](https://twobithistory.org/2017/10/07/the-most-important-database.html)].
Aged badly: child-segment access requires walking from the parent; ad-hoc queries that cross hierarchies are awkward. The relational model won the general case for a reason.
For VFS: hierarchies are good defaults for navigation; they are bad defaults for arbitrary querying. VFS's `find`, `grep`, and graph edges exist precisely because pure tree traversal is insufficient.

#### Pick (1965) and MUMPS (1966)

Two contemporaneous systems took "the DB *is* the OS" further. [Pick](https://en.wikipedia.org/wiki/Pick_operating_system) (originally GIRLS, 1965, Don Nelson and Dick Pick at TRW) ran on the IBM System/360 as a database operating system: accounts, dictionaries, files, items, attributes, values, sub-values — a hash-organized hierarchical store with a built-in query language. [MUMPS](https://en.wikipedia.org/wiki/MUMPS) (1966, Massachusetts General Hospital) exposed persistent state as *globals* — sparse hierarchical arrays addressed by subscript paths like `^Patient("12345","Name")` — that programs read and write as ordinary variables. Both systems pre-date the relational model and outlived most relational competitors in their niches (Pick in inventory and ERP; MUMPS in healthcare via Epic, Meditech, and the VA's VistA).

Novel: persistent state addressable as a hierarchical name without a separate API; no "open the database" step.
Aged well: the addressing convention. Healthcare backends are still MUMPS globals.
Aged badly: every system grew a bespoke query dialect that did not generalize; integration with the surrounding ecosystem was a perennial problem.
For VFS: hierarchical addressing as the default *read* path is a winning shape. But pinning *all* operations to that shape (as Pick and MUMPS did) means every cross-cutting operation reinvents indexing. VFS keeps the path as the primary handle while accepting that search, graph traversal, and revision queries are first-class operations beside it (Article 1, Article 2 §3).

### 1970s–80s — the integrated mainframe era and the Unix rebuttal

#### IBM System/38 → AS/400 → IBM i (1978–)

The [IBM System/38](https://en.wikipedia.org/wiki/IBM_System/38) (announced 1978) is the canonical "DB is the OS" production system. The Single-Level Store (SLS) presents one virtual address space across RAM and disk; every persistent thing is an *object* with a typed system-managed identity, not a file with bytes. DB2/400 is part of the OS, not a layer over it: tables, views, programs, users, queues, libraries — all are SLS objects, all participate in the same locking and authorization model. [IBM i](https://en.wikipedia.org/wiki/IBM_i) carries this forward today, advertising "everything is an object" as the explicit counter-thesis to "everything is a file."

Novel: hardware-independent Machine Interface that survived two CPU transitions (CISC → PowerPC → Power); object-based addressing on top of SLS; the database as a peer of the OS, not a guest.
Aged well: SLS's single namespace; the discipline of typed objects with declared capabilities (essentially a strongly-typed namespace).
Aged badly: portability outside the IBM i ecosystem is essentially zero; the model is too dependent on platform-specific microcode and hardware.
For VFS: the constitution rejects the "everything is an object" framing because object-based addressing requires every caller to learn the type taxonomy first. But the *typed namespace* idea returns, narrowed: VFS's `kind` enum (`file | directory | chunk | version | edge | tool | api`) is a closed type set declared in the path itself rather than discovered through metadata calls.

#### Ken Thompson, Dennis Ritchie, and "everything is a file" (1971–)

The Unix branch took the contrary axiom: the *filesystem* is the right unifier, *not* the database. Devices, pipes, tty lines — all addressed as files. The relational DB stays out. This was a deliberate discipline: Unix was small precisely because it refused to absorb the DB. The Multics-via-mainframe lineage absorbed it; Unix kept it separate; the field has been arguing about which choice was right for fifty years.

For VFS: the constitution sides with Unix on the framing (Article 1: file is the unifier) and with the integrated-DB systems on the storage (the terminal filesystem is allowed to *be* a database). It is a synthesis position, not a partisan one.

#### Sun VFS / vnodes (1985, Kleiman)

[Vnodes: An Architecture for Multiple File System Types in Sun UNIX](https://cgi.cse.unsw.edu.au/~cs3231/15s1/assignments/asst2/kleiman86vnodes.pdf) (Kleiman, USENIX 1986) is the first portable abstraction layer that lets multiple filesystem implementations coexist behind one POSIX-shaped interface. The split: `vfs` is the per-mount object; `vnode` is the per-file object. Each defines a vtable of operations. NFS, FFS, MS-DOS, RFS — different on disk, identical at the API.

Novel: capability-bearing function tables behind a stable client interface; mount as the composition primitive.
Aged well: every Unix-derived OS still uses some descendant of this design; FreeBSD's VFS is direct lineage [[2026-04-19 freebsd-vfs](2026-04-19-freebsd-vfs.md)].
Aged badly: vnodes leak state; the locking discipline is hard for new backends to get right; cross-mount operations remain a known weak point.
For VFS: this is the most direct ancestor of `VirtualFileSystem` and the `_*_impl` terminal pattern. The constitution's mount routing (Article 1 §1.4) is a deliberate Kleiman descendant. The decision to make capabilities explicit (Article 2 §2) is a *correction* of vnodes' weakness — vnodes leak unsupported-op surprises through `ENOTSUP` at call time rather than declaring capabilities up front.

### 1990s — Plan 9 and the file-shaped extensions

#### Plan 9 (Pike, Thompson, Presotto et al., 1990s)

[The Use of Name Spaces in Plan 9](https://9p.io/sys/doc/names.pdf) (Pike, Presotto, Thompson, Trickey, Winterbottom, SIGOPS 1992) is the load-bearing paper for VFS's worldview. Three claims: (1) every resource — devices, processes, network endpoints, synthetic services — should appear in a name space addressed by hierarchical paths; (2) name spaces are per-process, composed by `bind` and `mount`; (3) a single small protocol, [9P](http://doc.cat-v.org/plan_9/4th_edition/papers/), suffices for everything. Plan 9 declined to absorb concerns that would require *lying* about file shape — process creation and shared memory stayed as system calls — and that discipline is what VFS inherits as Article 3.

Novel: the *protocol* and the *kernel API* converge into one shape; composition through namespace manipulation rather than API plumbing.
Aged well: 9P is a clean protocol; the namespace ideas show up everywhere now (FUSE, /proc, /sys, container mount namespaces).
Aged badly: per-process namespaces never landed in mainstream Unix as a user feature; the wstat (omnibus metadata update) and msize negotiation became known anti-patterns.
For VFS: Plan 9 is the explicit ancestor (constitution Article 3). Read this paper before adding any mount-routing rule.

#### BeFS (Giampaolo, 1996)

The [Be File System](https://en.wikipedia.org/wiki/Be_File_System) is the most successful "filesystem with database features" that ever shipped. Journaled, 64-bit, B+tree indexing per extended attribute, *live queries* that update as files change, query expressions parsed in-kernel. Giampaolo's [Practical File System Design](http://www.nobius.org/dbg/practical-file-system-design.pdf) book documents the implementation in unusual detail.

Novel: extended attributes promoted to first-class queryable state; live queries (the query result is a directory whose contents update); a working demo that "FS + DB features" is feasible without inventing a relational schema.
Aged well: the *extended-attributes-as-metadata* pattern shows up in macOS HFS+ xattrs and Linux user.* xattrs.
Aged badly: BeOS itself died, taking BeFS with it on the desktop; Haiku keeps it alive. The kernel-side query parser is a complexity sink later systems avoided.
For VFS: BeFS is the proof that the metadata-as-queryable-FS thread *can* work. The constitution's `Candidate` shape — query-time fields populated optionally on a path-keyed result — is BeFS's live-query pattern with the kernel parser cut out.

#### ReiserFS / Reiser4 (Hans Reiser, 1996–)

[Reiser4](https://en.wikipedia.org/wiki/Reiser4) attempted the most ambitious "FS subsumes the DB" position of the era: atomic operations on small files, tail-packing, plugins for arbitrary content schemas, and an explicit [future vision](https://reiser4.wiki.kernel.org/index.php/Future_Vision) of obviating the relational DB by making the FS itself transactional and queryable. The Dancing B*-tree was novel; the project never made mainline Linux.

Novel: small-file performance via tail-packing; transactional commit semantics inside the FS.
Aged well: small-file performance arguments were vindicated by later workloads (lots of tiny config files, lots of source files, lots of agent-written notes).
Aged badly: ambition outran the kernel community's tolerance; Hans Reiser's incarceration killed momentum; the "FS replaces DB" framing scared developers off.
For VFS: a cautionary case. The right framing is not "VFS replaces the DB" — it is "VFS is a discipline on top of the DB."

### Early 2000s — the relational-FS dream and its grand failure

#### WinFS (2003–2006, canceled)

[WinFS](https://en.wikipedia.org/wiki/WinFS) was Microsoft's bet that the Windows file system should *be* a relational database. Schema-up-front type system: every kind of data (`Person`, `Document`, `Photo`) is a typed Item with declared properties and relationships. Stored on top of SQL Server. Demoed in 2003, decoupled from Vista in 2004, fully canceled in 2006.

Novel: typed items + declared relationships; the idea that relationships across "files" are first-class; integrated full-text and structured search.
Aged well: pieces survived. The Item/Type model influenced ADO.NET Entity Framework; the metadata-and-relationships idea reappears in Spotlight, OneDrive, Google Drive, and (arguably) every modern note-graph tool.
Aged badly: schema-up-front died on contact with reality. Every app wanted its own types; cross-app schemas required vendor coordination that never came; performance on the hardware of 2004 was unworkable. WinFS is the canonical "schema rigidity killed the project" cautionary tale.
For VFS: any proposal to extend VFS with a typed-item schema layer MUST be argued against this failure mode. The constitution's response is a small, closed `kind` enum rather than an open user-defined type system; closing the set is the discipline that keeps VFS shippable.

#### Apple Spotlight + Core Data (2004–) — the survivors

[Spotlight](https://en.wikipedia.org/wiki/Spotlight_(software)) shipped in 10.4 (2005) as the practical residue of the WinFS dream: a metadata index alongside a conventional FS, populated by per-format extractors, queried with a structured language. [Core Data](https://developer.apple.com/documentation/coredata) gave apps a managed object graph with SQLite as the default store. Together they delivered the user-visible parts of WinFS without the schema-up-front fight: the FS stays POSIX, the *index* gets the structure. Apple's [Core Spotlight semantic search](https://developer.apple.com/videos/play/wwdc2024/10131/) (WWDC 2024) extends this with embeddings.

Novel: structure-as-side-channel rather than structure-in-FS. Apps donate; the index aggregates.
Aged well: this is the dominant architecture for desktop search and increasingly for cloud drives.
Aged badly: indexes go stale, deny inspection, and have their own failure modes; metadata richness depends on ad-hoc extractor coverage.
For VFS: a direct precedent for VFS's pattern of layering search and graph indices over a path-keyed Entry table. Spotlight is the answer to "do we put structure in the namespace or in a side index?" — both, with the namespace as the source of truth.

#### Venti (Quinlan and Dorward, 2002)

[Venti: A New Approach to Archival Storage](https://www.cs.princeton.edu/courses/archive/spr05/cos598E/bib/venti-fast.pdf) (Quinlan and Dorward, FAST 2002, Bell Labs) is the often-overlooked progenitor of every CAS system. A network block store that addresses blocks by SHA-1 of their contents; writes are write-once and idempotent; deduplication is automatic; the block address *is* the integrity check. Plan 9's [Fossil](https://en.wikipedia.org/wiki/Fossil_(file_system)) (Quinlan, McKie, Cox, 2002) is the live filesystem that snapshots into Venti, organized as `/active`, `/snapshot/yyyy/mmdd/hhmm`, and `/archive/yyyy/mmdd<seq>`. This pair is the architectural template for everything that came after.

Novel: content-addressed block storage validated on a decade of real Plan 9 usage data; the explicit separation of the live mutable filesystem (Fossil) from the immutable archival store (Venti).
Aged well: Git (2005), IPFS (2014), Perkeep (2010s), DVC (2017), lakeFS (2020), Dolt (2019) are all variations on this theme.
Aged badly: SHA-1 is now considered weak; the on-disk format and block sizes assumed disk economics that have changed.
For VFS: Venti is the right reference for any future content-addressed storage in VFS. Read it before drafting a spec; the live/immutable two-tier design is the part that ages best, not the specific hash function or block format.

### Mid-2000s through 2010s — content addressing escapes the lab

#### Git (2005)

Git is Venti for source code with a different vocabulary (blob, tree, commit, tag) and a SHA-1 Merkle DAG. The covering [2026-02-17 doc](2026-02-17-database-vfs-patterns.md) covers the object model. The historical point: Git mainstreamed CAS. After 2005, CAS is a lingua franca; before 2005, it was niche.

#### ZFS and Btrfs (2005–)

[ZFS](https://en.wikipedia.org/wiki/ZFS) (Bonwick, Moore, Ahrens at Sun, 2005) and Btrfs (Mason at Oracle, 2007) brought *transactional copy-on-write* into general-purpose filesystems. [Bonwick's *The Zettabyte File System*](https://www.semanticscholar.org/paper/The-Zettabyte-File-System-Bonwick-Ahrens/27f81148ecbcd04dd97cebd717c8921e5f2a4373) describes the pooled-storage model, end-to-end checksums, and the snapshot mechanism: a snapshot is a preserved root pointer; modified blocks go to new locations; the old pointer keeps the old tree alive. Snapshots cost O(1) at creation and grow only with divergence.

Novel: snapshots as preserved pointers, not as data copies; pooled storage decoupled from filesystem boundaries; checksum every block.
Aged well: every modern filesystem stole the snapshot-as-pointer idea; cloud block stores all do CoW now.
Aged badly: CoW filesystems hosting databases produce write amplification — databases do their own CoW, and the layered CoW collides [[2026-02-17 doc](2026-02-17-database-vfs-patterns.md)].
For VFS: the snapshot-as-pointer pattern is the right shape for branching when VFS gets there. The two-CoW collision is the warning against running ZFS underneath PostgreSQL underneath VFS.

#### Perkeep / Camlistore (Brad Fitzpatrick, ~2010–)

[Perkeep](https://perkeep.org/) is a personal-scale CAS with a deliberate split: blobs are content-addressed and immutable; *permanodes* are stable identity blobs; *claims* are signed, timestamped mutations against permanodes; the current state of a permanode is the fold of all valid claims. The covering [2026-02-17 doc](2026-02-17-database-vfs-patterns.md) maps this to VFS's File + FileVersion split.

Novel: explicit reconciliation of mutable identity with immutable content via signed claims; offline-friendly and cryptographically attributable.
Aged well: the permanode/claims pattern reappears in CRDT-flavored systems, in ATProto/Bluesky lexicons, and arguably in event-sourced architectures generally.
Aged badly: GPG-signing every claim is operationally heavy; the user interface never crossed from prosumer to mainstream.
For VFS: the permanode/claims model is the right reference for VFS's `path → revision → content` shape. Path is the permanode (mutable identity); revision is the claim ordering; content is the immutable blob.

### 2017–2024 — the table-format era

This is where the industry now sits. Iceberg, Delta Lake, and Hudi are not databases that wrap files — they are *file layouts* that *act as* databases over object storage. They invert the historical relationship: instead of putting a DB on top of an FS, they put a DB-shaped *manifest* over a file pile and call the result a table.

#### Apache Iceberg (Netflix, 2017)

[Iceberg's spec](https://iceberg.apache.org/spec/) defines four metadata layers: a catalog pointer; a `metadata.json` table file; manifest lists per snapshot; manifest files listing data files with column-level statistics. Every write produces a new snapshot — an immutable list of data files at that instant. Time-travel queries are pointer reads; rollbacks are pointer writes.

Novel: metadata files are the database; the data files are content-addressable Parquet blobs; snapshots are immutable manifests.
Aged well: Iceberg is winning the format war as of 2026; major engines (Snowflake, BigQuery, Trino, Spark, Flink) all read it.
Aged badly: the metadata layer has its own scaling problems; small-file proliferation requires periodic compaction; catalog choice (REST, Glue, Nessie) is non-trivial.
For VFS: Iceberg is the reference for "manifest separates committed-immutable from staged-mutable." VFS's revision stamps per Entry are the per-file analog of Iceberg's per-snapshot pointer.

#### Delta Lake (Databricks, 2017)

[Delta Lake](https://www.databricks.com/blog/2019/08/21/diving-into-delta-lake-unpacking-the-transaction-log.html) made a different trade: a `_delta_log` directory of numbered JSON files records every transaction as a sequence of actions (`Add`, `Remove`, `Update metadata`, `Change protocol`, `Commit info`). Optimistic concurrency control resolves writes; readers reconstruct table state by replaying the log forward to a checkpoint and then reading the trailing JSONs.

Novel: the log *is* the schema-of-record; checkpoints are an optimization, not the truth.
Aged well: append-only log + periodic checkpoint is now the table-format default shape.
Aged badly: log replay cost grows with history; checkpoint discipline is required for performance.
For VFS: append-only commit log is the right shape for any future write-history feature in VFS. Don't store deltas in a way that requires reconstruction order to read.

#### Apache Hudi (Uber, 2016–)

[Hudi](https://hudi.apache.org/docs/overview/) leaned into upserts: record-level indexes (bloom filters, column statistics), Copy-on-Write tables for read-heavy workloads, Merge-on-Read tables for write-heavy ones, and a `.hoodie` timeline. It is the most database-like of the three, designed for CDC.

Novel: per-record indexes maintained inside the table format.
For VFS: when VFS adds chunk-level write paths (already underway in story 014), Hudi's MoR pattern is the relevant precedent — write fast to small log files, compact later.

#### Project Nessie and lakeFS (2020–)

[Nessie](https://projectnessie.org/) versions the *catalog* — branches and tags of Iceberg metadata pointers, Git-shaped. [lakeFS](https://lakefs.io/) versions the *whole object-store layer* with two-layer Merkle metaranges. Both ship the missing "branching for data" piece. Covered in detail in the [2026-02-17 doc](2026-02-17-database-vfs-patterns.md).
For VFS: when branching arrives in VFS, the right reference is lakeFS's two-layer Merkle, not bespoke design.

### 2019–2026 — DB-native versioning and the agent-era inflection

#### Dolt and Prolly Trees (2019–)

[Dolt](https://docs.dolthub.com/) embeds Git semantics into a MySQL-compatible engine. The novel data structure is the [Prolly Tree](https://www.dolthub.com/blog/2024-03-03-prolly-trees/): a content-addressed B-tree where chunk boundaries are determined by a hash function applied to keys, giving history-independent structural sharing and O(diff-size) diffs. Detailed in the [2026-02-17 doc](2026-02-17-database-vfs-patterns.md).
For VFS: Prolly Trees are the most interesting structure on the horizon; implementation cost is high; the cheaper takeaway is exposing version control through the query interface (system tables, stored procedures), which agents can navigate as paths in VFS.

#### SQLite as application file format and DuckDB (~2020)

[SQLite as Application File Format](https://sqlite.org/appfileformat.html) is Hipp's argument that "your enemy is complexity" — bespoke binary formats are vastly more code than reusing SQLite, and the SQLite file format is itself a stable specification. The same logic produced DuckDB's storage format. The pattern: a single-file embedded DB *is* the application's filesystem.
For VFS: this is the architectural justification for VFS's `DatabaseFileSystem` even when "database" sounds heavyweight. A SQLite file is a portable, self-describing, transactional substrate — it is both the DB and the FS; the only question is what shape the namespace takes on top.

#### Turso AgentFS (2025) and the agent-era inflection

[AgentFS](https://turso.tech/blog/agentfs) is an agent-focused SQLite filesystem with three interfaces: POSIX-like dentry/inode, key-value, append-only audit log. Letta (formerly MemGPT) [[2026-04-23 letta](2026-04-23-letta.md)] models agent state as multi-tier memory atop SQL with checkpointing. LlamaIndex's "Files Are All You Need" [[2026-02-17 ai-agent-filesystems](2026-02-17-ai-agent-filesystems.md)] argues files are the primary agent interface. Across all of these the file metaphor is *reasserting* for agents specifically — not because POSIX is right but because agents read, write, and grep, and the file is the right shape for "thing I can read, write, and grep."
For VFS: this is the project's home era. The constitution's Article 2 (agent-first contract) is the statement that this inflection is load-bearing for VFS, not incidental.

## The recurring tensions

Six tensions show up in every era and never resolve cleanly. Naming them explicitly is the first step to making conscious choices instead of accidentally re-fighting decided battles.

**Hierarchy vs. relations vs. graphs.** Multics, IMS, IBM i, Unix, BeFS, ReiserFS, Iceberg all chose hierarchies as the primary navigation. The relational model (Codd 1970, WinFS 2003) tried to replace hierarchies with relations and lost the user-experience battle even where it won the data-model battle. Knowledge-graph systems re-introduce graph as a first-class navigation. VFS's resolution: hierarchy is the default navigation; relations are exposed as queries (`grep`, `find`); graph edges are first-class but addressed *through* the namespace as `kind=edge` paths.

**Schema-up-front vs. schema-on-read.** WinFS demanded schemas; Iceberg, BeFS attributes, JSON in S3, MUMPS globals, and POSIX xattrs deferred or skipped them. Schema-up-front systems lost the deployment race because every app wants its own schema and cross-app coordination is impossible. VFS's resolution: a small, closed schema for the *namespace primitives* (Entry kind, revision shape, capability set); arbitrary schema-on-read for content.

**Content-addressed vs. mutable-path.** Venti, Git, IPFS, Perkeep, Iceberg data files all use content-addressed identity. POSIX, NTFS, IBM i objects use mutable-path identity. Each fails at what the other does well: content-addressed needs an indirection layer for human-meaningful names (refs, permanodes, manifests); mutable-path has no built-in deduplication or integrity. VFS's resolution: path is the public identity (Article 1); content addressing is permitted as a backend implementation detail.

**Files-as-bytes vs. files-as-queryable-records.** BeFS, WinFS, IBM i argued that the FS should expose structured records. Unix, Plan 9 argued the FS should expose bytes and let tools impose structure. The byte-stream camp produced more interoperable systems; the queryable-record camp produced more powerful per-system tooling and worse interop. VFS's resolution: bytes at the read interface; structure via separate operations (search, traversal) that return Candidates. A `Candidate` is the queryable-record shape with the discipline that *paths address Entries, not Candidates*.

**Single-machine integrity vs. distributed eventual consistency.** ZFS, Btrfs, IBM i, SQLite assume single-machine atomicity. NFS, IPFS, Perkeep, Iceberg, Delta Lake, lakeFS assume distributed eventual consistency with explicit reconciliation. The two camps look identical at the API and diverge at failure handling. VFS's resolution: declare which (Article 4 capability declaration); revision stamps are the reconciliation primitive (Article 1 §1.5).

**In-band metadata vs. side-channel metadata.** Spotlight, Lucene, Whoosh, Elasticsearch put metadata in a side index; HFS+/NTFS xattrs, BeFS, IBM i objects put it in-band. Side-channel goes stale; in-band is hard to query without inventing a query language. VFS's resolution: *the namespace is the source of truth*; indices (search, embeddings, graph) are caches that the system MAY rebuild from the namespace. Article 1 forbids parallel public naming systems precisely to keep this guarantee.

## Deeper dive — relations and edges

The "hierarchy vs. relations vs. graphs" tension above is the one most likely to be re-litigated by future contributors. This section sharpens it. The position of the constitution does not change; what changes is the depth of the argument behind it.

### What hierarchy filesystems should steal from the relational ones

The agreed framing is that hierarchy is the right primary navigation. The standard mistake when accepting that framing is to ignore the relational lineage entirely and re-derive its lessons accidentally a decade later. The interesting question is the inverse: *what did the systems that put relations in primary position actually get right that hierarchy-first systems do not usually borrow?* Five answers, each with a system that proved it.

**1. Path-as-conjunctive-query (Gifford et al., SOSP 1991).** *Semantic File Systems* (Gifford, Jouvelot, Sheldon, O'Toole) is the foundational paper here, and it is older than every hierarchy-first system VFS cites except Multics, Unix, and Plan 9. The trick: a path component of the form `field:value` is a query predicate, and successive components compose by conjunction; `cd /sfs/owner:dgifford/ext:c/` is `WHERE owner='dgifford' AND ext='c'`. Crucially, SFS layered this *over* an unmodified hierarchical FS exposed via NFS — the relational view was an additional reading of the same byte-store, not a replacement. Tagsistant carries the design forward (`tags/t1/t2/+/t1/t4/@/`) with explicit conjunction and union operators and an `@/` terminator that re-enters POSIX semantics. The non-obvious lesson: **path syntax is rich enough to encode conjunctive queries; hierarchy-first systems leave this affordance on the floor**. VFS already gestures at this with `/.vfs/.../__meta__/...` projections; the unused move is to also accept `field:value` *components* in synthetic query subtrees (e.g. a `/.vfs/q/ext:py/kind:file/` virtual directory) without breaking Article 1 — every component is still a path segment, and the result is still a `Candidate` listing.

**2. Bidirectional relations as a property of the relation, not the endpoints (WinFS).** WinFS defined Relationship as a first-class typed object with Source, Target, kind (Holding | Reference | Embedding), and lifetime semantics ([WinFS spec, MSDN archive]). The thing WinFS *got right* is independent of the schema-up-front mistake: **a relation is a thing in its own right, with its own identity, lifecycle, and rules — not an attribute of either endpoint**. Holding relationships propagate delete; Reference relationships do not. Embedding adds order. Hierarchy-first systems usually represent edges either as attributes on one side (loses bidirectionality) or as symlinks (loses typed semantics, loses delete propagation). VFS already follows WinFS on this point — `kind=edge` with `source_path`, `target_path`, `edge_type` is a Relationship in the WinFS sense — but the two unborrowed pieces are *typed lifecycle rules* (does deleting the source delete the edge? the target? neither?) and *cardinality* (is this edge unique on `(source, type)`?). Both are decisions VFS will eventually need.

**3. Indexed attributes as queryable peers of bytes (BeFS).** Giampaolo's [Practical File System Design](http://www.nobius.org/dbg/practical-file-system-design.pdf) describes BeFS extended attributes as B+tree-indexed first-class metadata. The non-obvious move is not the indexing — every modern FS has indices — but the *contract*: each indexed attribute behaves like a relational column with full predicate support (`=`, `<`, `LIKE`), available *without* cracking the file open, and queries are open-able as if they were directories. Hierarchy-first systems usually put attributes in xattrs and treat them as opaque payload; BeFS treated them as queryable first-class state. VFS's `Candidate` field set is the spiritual descendant — `score`, `in_degree`, `updated_at`, `lines` are queryable peers of `path` — but the unborrowed move is exposing *user-defined* attribute predicates in the namespace, not just system-chosen ones. A hierarchy-first system MAY decline this; what it MUST NOT do is decline it without realizing BeFS already proved the cost of inclusion is bounded.

**4. Files-as-records with composable readers (Reiser4 plugins, Pick attributes).** Reiser4's [Future Vision](https://archive.kernel.org/oldwiki/reiser4.wiki.kernel.org/index.php/Future_Vision.html) and Pick's items-with-multivalued-attributes both argue that a file is sometimes the wrong granularity — the *record inside* the file is. Reiser proposed pruners (predicate functions like `_is-a-shellscript`) and per-content-type plugins; Pick let you address `account.dictionary.attribute` as a path. Hierarchy-first systems usually stop at the file boundary and force the application to crack the bytes. VFS's `kind=chunk` is a partial answer — sub-file addressing through `/.vfs/.../__meta__/chunks/<name>` — but it is *system-chosen* (line ranges from a chunker), not user-chosen (the regex `def \w+` against a Python file). The unborrowed move is BeFS-style queryable transducers exposing *programmable* sub-file slices as paths. Whether VFS wants this is open; that the relational lineage already paid the cost of inventing it is not.

**5. The query as a persisted, sharable object (BeFS live queries, Spotlight smart folders).** A relational system that stops at "you ran a query and got a result set" loses; one that names the query and lets it be re-opened, subscribed to, or composed wins. BeFS live queries returned a directory whose contents updated as files matched or stopped matching. Spotlight smart folders are saved query objects in the FS. The pattern: **the query is itself a path**. Article 5 §1 forbids live handles, which forbids the BeFS *update* semantics directly — but the persisted-query-as-path shape is compatible with snapshot reads (each `read` re-evaluates against the current revision), and it is the right shape for agent workflows that want to refer to "all imports of this file" by name rather than re-pose the query each call. The relational systems proved this is worth doing; hierarchy-first systems usually rebuild it as a per-tool feature instead of an FS feature.

The honest summary: hierarchy is the right primary navigation, *and* the relational lineage spent thirty years working out affordances that compose with hierarchy rather than replacing it. Path-as-query, typed relations, attribute predicates, sub-file records, and persisted queries are all of that shape. The constitution does not need to bend to host any of them; what is required is the discipline to recognize them as relational-lineage debt when they show up and to import them deliberately rather than re-discovering them under new names.

### Edge representation — is `kind=edge` the right shape?

The current shape, grounded in the actual code (`src/vfs/paths.py`, `src/vfs/models.py`):

- An edge is a first-class `VFSEntry` row with `kind="edge"` and three identity columns: `source_path`, `target_path`, `edge_type`.
- The canonical *writeable* address is `/.vfs/<source>/__meta__/edges/out/<edge_type>/<target>` (`edge_out_path`).
- The inverse *readable* projection is `/.vfs/<target>/__meta__/edges/in/<edge_type>/<source>` (`edge_in_path`); writes to it are rejected by `validate_mutation_path`.
- `decompose_edge` recovers `(source, target, type, direction)` from any edge path; `parse_kind` returns `"edge"` for either projection.

This is *not* "an edge is a path"; it is "an edge is a row whose canonical name is a path that embeds both endpoints, projected bidirectionally so each endpoint can list its own edges with `ls`." The user's intuition that edges are *between* paths is correct; the existing design's response is to embed the "between" *into* one of the endpoints' synthetic subtrees and project it from the other.

Eight alternatives, evaluated under Articles 1–3.

**(1) Edge-as-path (current).** Articles 1–3 are honored: every edge is addressable, the kind is path-derivable (`parse_kind`), the projection avoids parallel naming systems by living under `__meta__`. Plan 9 corroboration: this is the `/proc/N/status` shape — synthetic paths whose existence is implied by the parent. Cost: long paths (the target is embedded literally), and the bidirectional projection is two paths for one logical fact, requiring `validate_mutation_path` to reject inverse writes. Survives at scale because the canonical write side is unique and the inverse is enumerable from one B+tree-index lookup on `target_path`.

**(2) Edge-as-extended-attribute.** BeFS shape: `xattr -w refs.imports /path/to/util.py /path/to/foo.py`. Honors Article 3 in spirit (xattrs are file-shaped). Fails Article 1: the edge is not addressable as a first-class object — it is a value buried inside the source file's attribute namespace, requiring callers to open the source file to enumerate edges. Also fails Article 2 §3 (bounded enumeration): an edge query becomes a scan of every file's xattrs.

**(3) Edge-as-symlink-with-metadata.** Article 3 *explicitly* rejects symlinks. Plan 9's bind/mount obviated symlinks because their static, untyped, mostly-undebuggable nature is a known anti-pattern ([9P/bind documentation](https://9p.io/sys/doc/lexnames.html)). Disqualified at the article level.

**(4) Edge-as-special-directory-content.** Git's `refs/`, Iceberg's manifest list. A reserved directory (`/.vfs/edges/`) holds all edges as files. Honors Articles 1–3, but loses the *locality* property — an agent that wants "what does foo.py import?" must scan a global edges directory rather than read foo.py's metadata subtree. Iceberg succeeds with this shape because edges are between *table snapshots*, which are coarse and few; VFS edges are between files, which are fine and many. The locality cost is real.

**(5) Edge-as-content-of-a-file.** Edges live in markdown frontmatter or a sidecar `.edges.json`. This is what most note-taking tools do. Fails Article 1: the edge is not first-class addressable — it is a substring of a file's content. Fails Article 4: every backend would need to know how to parse every content format to expose graph queries. Disqualified.

**(6) Edge-as-9P-control-file.** Plan 9 ctl idiom: `echo "link imports /src/util.py" > /src/foo.py/ctl`. The [`plan9_to_vfs_guidance.md`](../../../.claude/projects/-Users-claygendron-Git-Repos-grover/memory/plan9_to_vfs_guidance.md) memo specifically endorses ctl for backend-specific knobs. But edges *are* first-class state, not configuration; ctl is the right shape for *operations*, not for *enumerable persistent objects*. Use ctl for "compact this graph" or "rebuild edge index from scratch," not for the edges themselves.

**(7) Edge-as-mount.** Mount a graph database under `/graph/`; queries become reads. Article 1 §1.4 permits this — composition through mounts is the whole point — and Iceberg-catalog backends use exactly this shape. But it conflates *terminal filesystem boundaries* with *kind boundaries*. An edge from a DB-backed file to a Slack-backed message is a single logical fact whose two endpoints live in different mounts; if edges live in their own mount, that mount must know how to address every other mount, which is the side-channel routing Article 1 forbids.

**(8) Edge-as-virtual-directory-result (BeFS / Spotlight).** `ls /.vfs/src/foo.py/__meta__/edges/out/imports/` returns the targets, computed at read time from a graph index. This is *also what the current design does* on the read side — `_split_edge_path` makes the inverse projection a virtual view whose contents are computed by querying `target_path`. The current design is therefore a hybrid of (1) and (8): canonical writes go to (1), reads of the inverse projection are (8).

**Recommendation.** Stay with (1) — `kind=edge` paths under `/.vfs/<endpoint>/__meta__/edges/<direction>/<type>/<other>` — and lean *harder* into the (8) hybrid the code already implements, by treating the inverse projection as a fully synthesized view and never letting an edge row be addressable by two real keys. Concretely: keep `source_path` as the only canonical primary-key component of an edge row, and treat `edge_in_path` strictly as a query rendering, never as an alternate insert target (this is already what `validate_mutation_path` enforces; the recommendation is to keep that invariant load-bearing and document it). The constitution does not need to bend to support this — Articles 1–3 already permit it — but two follow-ons should be written down: an edge is *owned* by its source endpoint for lifetime purposes (delete-source cascades to outgoing edges; delete-target tombstones inbound edges as broken without removing them), and edge cardinality on `(source, type, target)` is unique. WinFS got the typed lifecycle rules right; that is the unborrowed piece worth importing.

## Best practices distilled

The patterns that survived three or more eras:

- **Append-only commit log + periodic checkpoint.** Delta Lake, IMS, Iceberg, Git, Perkeep claims, ZFS uberblock, lakeFS. Universal shape for "give me history without paying for full snapshots." VFS's revision stream is the same idea narrowed to per-path.
- **Copy-on-write with snapshot-as-pointer.** ZFS, Btrfs, Iceberg, lakeFS, Fossil. Snapshots are O(1); divergence costs are paid only on writes. Any future VFS branching MUST use this shape and not snapshot-by-copy.
- **Manifest separates committed-immutable from staged-mutable.** Iceberg, Delta Lake, lakeFS, Fossil/Venti pair, Git index/HEAD. Mutable working state is cheap; committed state is immutable and shared. The two layers MUST be distinguishable in any future VFS write pipeline.
- **Capability declaration ahead of execution.** A failure of vnodes (capability discovered at call time) and a success of MCP, Iceberg (catalog declares what it supports). Article 2 §2 in the constitution.
- **Bounded enumeration with cursors.** Every system that didn't get this right (early FUSE wrappers, naive ORMs) eventually rebuilt it. Article 2 §3.
- **Revision stamps for cache coherence.** 9P's qid.vers, ETag in HTTP, MVCC version columns, Iceberg snapshot IDs, Git object hashes. Article 1 §1.5.
- **Content before commit ordering.** The blob exists at its hash before the manifest names it; the file content is on disk before the directory entry points to it. Universal across CAS systems. Reversed once in VFS in commit `f7e039a` and reverted; see [feedback_fs_write_ordering](../../../.claude/projects/-Users-claygendron-Git-Repos-grover/memory/feedback_fs_write_ordering.md).
- **FUSE has a syscall round-trip tax.** ~4 context switches per operation, ~60% slower for metadata-heavy workloads, up to 3× slower in the worst case [[FAST 2017 *To FUSE or Not to FUSE*](https://www.usenix.org/system/files/conference/fast17/fast17-vangoor.pdf)]. VFS's choice to expose a Python API rather than a FUSE driver is informed by this; FUSE is acceptable for human-driven workflows where the latency budget is large.
- **Don't run CoW filesystems under databases.** Established in the [2026-02-17 doc](2026-02-17-database-vfs-patterns.md) — write amplification compounds. Operationally relevant if VFS ever recommends a deployment topology.
- **Single-file portability is a feature.** SQLite as application file format, AgentFS, DuckDB. A whole filesystem in one file is good for backup, replication, and inspection.

## What VFS should learn from — reading list

Ranked by load-bearing relevance to current VFS work. Each item is read-before-design, not read-eventually.

1. [Pike, Presotto, Thompson, Trickey, Winterbottom — *The Use of Name Spaces in Plan 9*](https://9p.io/sys/doc/names.pdf) (1992). The constitution's primary ancestor. Read before adding any mount-routing rule.
2. [Kleiman — *Vnodes: An Architecture for Multiple File System Types in Sun UNIX*](https://cgi.cse.unsw.edu.au/~cs3231/15s1/assignments/asst2/kleiman86vnodes.pdf) (USENIX 1986). The mount/dispatch ancestor of `VirtualFileSystem`.
3. [Quinlan and Dorward — *Venti: A New Approach to Archival Data Storage*](https://www.cs.princeton.edu/courses/archive/spr05/cos598E/bib/venti-fast.pdf) (FAST 2002). The CAS ancestor; required reading before any content-addressed work in VFS.
4. [Daley and Neumann — *A General Purpose File System for Secondary Storage*](https://multicians.org/fjcc4.html) (FJCC 1965). The hierarchical-namespace-as-world-model thesis at its origin.
5. [Apache Iceberg specification](https://iceberg.apache.org/spec/). The current SOTA for "manifest separates committed-immutable from staged-mutable." Read before any history/branching work.
6. [Delta Lake transaction log protocol](https://github.com/delta-io/delta/blob/master/PROTOCOL.md). Sister reference to Iceberg; the append-only-commit-log shape.
7. [Giampaolo — *Practical File System Design with the Be File System*](http://www.nobius.org/dbg/practical-file-system-design.pdf) (1999). The most accessible book-length treatment of FS internals; the live-query pattern that informs `Candidate`.
8. [DoltHub — Prolly Trees explainer](https://www.dolthub.com/blog/2024-03-03-prolly-trees/). The structure to read about before re-inventing diff-shaped versioning.
9. [Bonwick and Ahrens — *The Zettabyte File System*](https://www.semanticscholar.org/paper/The-Zettabyte-File-System-Bonwick-Ahrens/27f81148ecbcd04dd97cebd717c8921e5f2a4373). Snapshot-as-pointer canon.
10. [Vangoor, Tarasov, Zadok — *To FUSE or Not to FUSE: Performance of User-Space File Systems*](https://www.usenix.org/system/files/conference/fast17/fast17-vangoor.pdf) (FAST 2017). The empirical answer to "should VFS ship a FUSE driver?"
11. [SQLite as Application File Format](https://sqlite.org/appfileformat.html). The architectural justification for embedding a DB as the FS.
12. [WinFS — Wikipedia summary and Frank's World retrospective](https://en.wikipedia.org/wiki/WinFS). The schema-up-front cautionary tale.
13. [Perkeep documentation — permanodes and claims](https://perkeep.org/doc/). The mutable-identity-over-immutable-content reference.
14. [Lakefs versioning internals](https://docs.lakefs.io/v1.60/understand/how/versioning-internals/). The two-layer Merkle for branching at scale.
15. The [2026-02-17 database VFS patterns](2026-02-17-database-vfs-patterns.md) doc in this repo. Modern landscape coverage; read alongside this one.

## Concepts every VFS dev should know

**Namespace.** The single rooted tree of all addressable objects. Plan 9's name space, Multics' segment hierarchy, Unix's `/`. In VFS this is the world model; Article 1 forbids parallel naming systems. Lives in `src/vfs/base.py` (mount routing) and `src/vfs/paths.py` (path normalization).

**Mount.** A named attachment of one filesystem inside another at a single-segment path. Plan 9's `bind`/`mount`, Unix's `mount`, Iceberg's catalog binding. In VFS, `_mounts: dict[str, VirtualFileSystem]`; resolution is longest-prefix.

**Inode vs. dentry vs. vnode.** Three nouns describing different things. Inode = the on-disk record of a file's metadata and block pointers. Dentry = the in-memory cached lookup result of a path component. Vnode = the OS-level abstract handle to an open file across filesystem types. VFS's `Entry` is closest to "inode" semantically; VFS deliberately does not expose vnodes (no live handles, Article 5).

**Fid (9P).** A per-connection channel ID for a file or directory walk in progress. Not a file descriptor — server-managed, per-protocol-conversation. The Plan 9 lineage of VFS's session/transaction scoping.

**Qid (9P).** A 13-byte tuple of (type, version, path) that uniquely identifies a file at a moment. The version field is the cache-invalidation stamp. VFS's revision (Article 1 §1.5) is the qid.vers idea generalized to a backend-chosen monotone encoding.

**TOAST (PostgreSQL).** Transparent overflow of large attribute values into a side table, with optional compression. The reason `DatabaseFileSystem` can store multi-MB content in a column without operational pain. Covered in detail in the [2026-02-17 doc](2026-02-17-database-vfs-patterns.md).

**LOB (Large Object).** Database-managed handle to a multi-GB binary value. PostgreSQL `pg_largeobject`, MSSQL FILESTREAM. Operationally heavier than TOAST; rarely the right choice for VFS.

**Content-addressed storage (CAS).** Identity is the hash of content; same content always has the same address. Venti, Git blobs, IPFS CIDs, Iceberg data files. Properties: dedup, immutability, integrity, history-independence. Cost: a separate indirection layer for human-meaningful names.

**Merkle DAG.** A directed acyclic graph in which every node is identified by a hash that includes the hashes of its children. Git's commit graph, IPFS, the Iceberg manifest tree. Enables structural sharing and verifiable history.

**Prolly Tree.** A content-addressed B-tree where chunk boundaries are determined by hashing keys. History-independent (insertion order doesn't change tree shape), key-based chunking (value updates don't shift boundaries), O(diff-size) diffs. Dolt's core structure.

**Write-ahead log (WAL).** Append-only journal of intended changes, written before the change is applied to the main store. Crash recovery replays the log. Universal in transactional databases; the ancestor of Delta Lake's `_delta_log`.

**Copy-on-write (CoW).** Modifications produce new blocks; old blocks remain reachable from old root pointers. Snapshots are old root pointers preserved. ZFS, Btrfs, Iceberg, Fossil.

**Snapshot pointer.** A persisted root reference that captures the entire visible state at the moment of the snapshot. O(1) to take; divergence-proportional to keep. The right shape for branching in VFS.

**MVCC (multi-version concurrency control).** Reads see a consistent snapshot of state without blocking writers; writers create new versions without overwriting. PostgreSQL's tuple visibility, all serious databases, Iceberg snapshot semantics. The shape Article 5 §1 (reads are snapshots) inherits.

**Optimistic concurrency.** Writers read a version stamp, compute their change, and commit only if the stamp hasn't changed. The Delta Lake commit protocol; HTTP `If-Match`. Article 1 §1.5's `if_revision=X` is exactly this.

**Capability declaration.** A backend states which operations it supports on which paths *before* being asked. Iceberg catalog capabilities, MCP server tool list, Article 2 §2. The fix for vnodes' "discover at call time" failure mode.

**Manifest / metarange.** The structural metadata that names the data files comprising a snapshot. Iceberg manifest list, lakeFS metaranges, Git tree objects. Separates the "what is in the table" question from the "what bytes are in each file" question.

**Snapshot (Iceberg-flavor).** An immutable list of data files representing the table's state at a commit. New writes produce new snapshots; old snapshots remain readable. Time-travel queries are pointer reads.

**Branch (as ref).** A mutable name pointing to a snapshot/commit. Git, lakeFS, Nessie, Dolt. Branching is naming, not copying.

**Revision (VFS).** The constitutional primitive (Article 1 §1.5). Per-path monotone stamp; the unit of cache invalidation; the MVCC handle. Implementations are backend-chosen — counter, ULID, timestamp+hash — as long as ordering is total and stable.

**Candidate (VFS).** The query-time observation of an Entry (`src/vfs/results.py`). Carries path, kind, revision, and zero or more populated query-time fields. Frozen; enrichment returns a new Candidate. The resolution of the BeFS live-query and the Spotlight side-index patterns: the namespace owns truth, the Candidate is the per-call view.

## The motivating philosophy

Sixty years of work has produced two coherent positions and one workable synthesis. The first position is "the database absorbs the operating system" — Multics, Pick, MUMPS, IBM i, WinFS, Reiser4. It produces powerful, queryable, integrated systems that are also platform islands; portability and interop are perennial pain. The second position is "the filesystem absorbs everything" — Unix, Plan 9. It produces small, composable, interoperable systems that pay for that flexibility by leaving the database concerns to the application. The synthesis position — Iceberg, Delta Lake, lakeFS, Dolt, AgentFS, and now VFS — is "the filesystem is the *interface*; the database is the *implementation*; agents see paths and bytes; engines see manifests, transactions, and indices." This is the position the constitution takes.

"Everything is a file" is the right unifier *given* this synthesis. The DB and the FS have been converging for sixty years; the convergence point is not a new primitive but a *discipline* on the old one. Plan 9's discipline — don't lie about what a file is; if a concern would require a dishonest file shape, keep it out — is the safety rail. The constitution's Article 3 makes this explicit, and the closed `kind` enum (file, directory, chunk, version, edge, tool, api) is the operationalization: every first-class object in VFS is a file in the rigorous sense, not a metaphor that breaks under load.

Agent-first matters now in particular because agents are the first class of users for whom the file metaphor is *re-validating itself*. Humans wrote SQL; agents grep. Humans clicked "Open"; agents `ls /context/`. Humans built schemas; agents create files and read what's there. The file is the right shape for "thing I can read, write, and grep" — and that is exactly the shape an agent's interaction with state has. The agent-era inflection (AgentFS, Letta, the LangChain Deep Agents pluggable backend) is not a fashion; it is a return to the Unix shape because that shape happens to be the right one for a population of users that didn't exist when the choice was made.

VFS exists because nothing else in 2026 holds all three threads at once: the DB-as-storage thread (so we can run on a real database with real transactions), the FS-as-interface thread (so agents and humans can use it without learning a query dialect), and the Plan 9 discipline (so the abstractions don't lie). This is the position. Everything else — backends, capabilities, mounts, candidates, revisions — is in service of holding the position without compromise.

## Instructions for VFS devs

These are derived from the history above. They are RFC 2119 rules; deviations require a written decision in `context/decisions/` per the constitution preamble.

1. **Contributors MUST read the Plan 9 namespaces paper before introducing or modifying mount-routing logic.** Mount routing is not "a path-prefix dictionary"; it is a position in a 35-year design conversation, and the constraints (composition, no side worlds, longest-prefix) come from that conversation.
2. **Versioning work MUST be evaluated against Venti's content-addressed model and lakeFS's two-layer Merkle approach before any new design is drafted.** "Just store diffs" is the answer that has been re-invented and abandoned across a decade of systems.
3. **Schema-up-front extensions MUST be justified against WinFS's failure mode in writing.** A new typed-item layer, a new property graph, a new declared-relationship system — each one MUST cite WinFS, name the difference, and explain why this time will not fail the same way.
4. **Snapshots MUST be implemented as preserved pointers, never as full copies.** ZFS, Iceberg, Fossil, Git all converged on this; an alternative requires a written decision.
5. **Append-only commit logs MUST be preferred over in-place mutation for any history-bearing surface.** Delta Lake, IMS, Iceberg, all major databases. The reason is recovery, not performance.
6. **Content-before-commit ordering MUST be preserved in all write paths.** The blob is on disk at its address before the manifest names it; the file content is durable before its path is published. See [feedback_fs_write_ordering](../../../.claude/projects/-Users-claygendron-Git-Repos-grover/memory/feedback_fs_write_ordering.md). This was reversed once in `f7e039a` and immediately reverted; the reversal MUST NOT recur.
7. **Capability declaration MUST be possible without executing the operation.** Article 2 §2 in the constitution. The fix for vnodes' historical weakness; surprise `UnsupportedCapability` at call time is forbidden.
8. **FUSE drivers SHOULD NOT be the primary delivery surface for VFS.** The FAST 2017 measurements show 60%+ slowdown on metadata-heavy workloads; agent workloads are metadata-heavy. A FUSE wrapper is acceptable for human ergonomics; the contract surface stays Python (and FSP over MCP for remote).
9. **Revision stamps MUST be carried on every Entry and every Candidate.** No exceptions, no nulls, no "we'll backfill later." Article 1 §1.5. This is the primitive that makes optimistic concurrency, cache invalidation, and reads-as-snapshots work; missing stamps silently corrupt all three.
10. **The namespace MUST be the source of truth; indices are caches.** Search indices (BM25, embeddings), graph indices, and full-text indices are derived state that the system MAY rebuild from the namespace. They MUST NOT be the only authoritative copy of any user-visible fact.
11. **Cross-mount operations MUST declare their non-atomicity or raise `CrossMount`.** Article 1 §1.4. Silent best-effort moves and copies across mounts are the bug class that ate three decades of NFS.
12. **New `kind` values MUST extend the closed enum, not bypass it.** Article 1 §1.2. The closed set is the discipline that keeps VFS shippable; an open type system is what killed WinFS.
13. **Backends MUST NOT accept backend-specific path grammar in public arguments.** No URL chains, no `?backend=foo` query strings, no per-backend escape sequences in paths. Composition is through mounts, not through path grammar; this is Article 1 §1.4 and Article 4.
14. **Migration scripts SHOULD NOT be written.** External data lifecycle is the deployer's concern; see [feedback_no_migration_scripts](../../../.claude/projects/-Users-claygendron-Git-Repos-grover/memory/feedback_no_migration_scripts.md). The historical evidence: every system that shipped its own migration tooling spent the next five years maintaining it.
15. **When in doubt, the answer is "look at how Plan 9 did it, then look at how Iceberg does it, then choose."** This is not deference; it is recognition that the two systems jointly cover the design space VFS occupies.

## Open questions

1. Does VFS commit to content-addressed storage as a backend capability, and if so on what schedule? The 2026-02-17 doc marks CAS as a v0.2/v0.3 candidate; the historical evidence (Venti through Iceberg) suggests it should be a non-optional backend feature for any future remote-store implementation.
2. What is the right reference structure for branching in VFS — lakeFS's two-layer Merkle, Dolt's Prolly Trees, or Git's tree-of-trees? Each implies a different cost model. Decision required before any branching story is opened.
3. How does VFS expose history to agents — virtual paths under `/.vfs/path/.../__meta__/versions/N` (per Article 1 §1.5), as system tables (Dolt-shaped), or both? The constitution names the former; the latter is a separable enhancement.
4. Is the `kind` enum truly closed for the project's lifetime, or does the agent-era invite a `memory` kind, an `inbox` kind, a `tool-call` kind? The WinFS lesson argues for keeping the set small; the AgentFS three-interfaces design argues there are at least two more useful classes.
5. Does VFS ship a wire protocol (FSP) that is recognizably 9P-shaped, or a JSON-shaped descendant inheriting only the semantics? Plan 9's wire format is small and old; MCP-over-HTTP is what agents already speak. The right answer is probably the latter; the cost is losing 9P tooling. [NEEDS VERIFICATION — there may be active discussion in `context/stories/` not surveyed here.]
6. Where is the right boundary between the `Candidate` query-time view and a "live query" in the BeFS sense — a result set that updates as the namespace changes? The constitution forbids live handles (Article 5 §1: reads are snapshots), which forbids the BeFS shape directly. The agent equivalent — a poll loop with revision-guarded reads — works but is not the same shape.

## Sources

- [Multics History](https://multicians.org/history.html)
- [Multics — Wikipedia](https://en.wikipedia.org/wiki/Multics)
- [Daley and Neumann — *A General Purpose File System for Secondary Storage* (1965)](https://multicians.org/fjcc4.html)
- [Daley and Dennis — *Virtual Memory, Processes, and Sharing in Multics*](https://www.cs.virginia.edu/~evans/greatworks/MULTICS.pdf)
- [Single-level store — Wikipedia](https://en.wikipedia.org/wiki/Single_level_store)
- [IBM Information Management System — Wikipedia](https://en.wikipedia.org/wiki/IBM_Information_Management_System)
- [IMS at IBM History](https://www.ibm.com/history/information-management-system)
- [The Most Important Database You've Never Heard Of — twobithistory](https://twobithistory.org/2017/10/07/the-most-important-database.html)
- [Pick operating system — Wikipedia](https://en.wikipedia.org/wiki/Pick_operating_system)
- [MUMPS — Wikipedia](https://en.wikipedia.org/wiki/MUMPS)
- [MultiValue database — Wikipedia](https://en.wikipedia.org/wiki/MultiValue_database)
- [IBM System/38 — Wikipedia](https://en.wikipedia.org/wiki/IBM_System/38)
- [IBM i — Wikipedia](https://en.wikipedia.org/wiki/IBM_i)
- [Kleiman — *Vnodes: An Architecture for Multiple File System Types in Sun UNIX* (USENIX 1986)](https://cgi.cse.unsw.edu.au/~cs3231/15s1/assignments/asst2/kleiman86vnodes.pdf)
- [Sandberg, Goldberg, Kleiman, Walsh, Lyon — *Design and Implementation of the Sun Network Filesystem*](https://www.cs.ucf.edu/~eurip/papers/sandbergnfs.pdf)
- [Pike, Presotto, Thompson, Trickey, Winterbottom — *The Use of Name Spaces in Plan 9* (SIGOPS 1992)](https://9p.io/sys/doc/names.pdf)
- [Plan 9 documents](https://9p.io/sys/doc/)
- [Everything is a file — Wikipedia](https://en.wikipedia.org/wiki/Everything_is_a_file)
- [Be File System — Wikipedia](https://en.wikipedia.org/wiki/Be_File_System)
- [Giampaolo — *Practical File System Design with the Be File System*](http://www.nobius.org/dbg/practical-file-system-design.pdf)
- [Reiser4 — Wikipedia](https://en.wikipedia.org/wiki/Reiser4)
- [Reiser4 Future Vision](https://reiser4.wiki.kernel.org/index.php/Future_Vision)
- [WinFS — Wikipedia](https://en.wikipedia.org/wiki/WinFS)
- [WinFS Cancellation Q&A — OSnews](https://www.osnews.com/story/15022/winfs-cancellation-questions-and-answers/)
- [Apple Spotlight — Wikipedia](https://en.wikipedia.org/wiki/Spotlight_(software))
- [Core Spotlight semantic search — WWDC24](https://developer.apple.com/videos/play/wwdc2024/10131/)
- [Quinlan and Dorward — *Venti: A New Approach to Archival Storage* (FAST 2002)](https://www.cs.princeton.edu/courses/archive/spr05/cos598E/bib/venti-fast.pdf)
- [Venti documents on cat-v](http://doc.cat-v.org/plan_9/4th_edition/papers/venti/)
- [Fossil (file system) — Wikipedia](https://en.wikipedia.org/wiki/Fossil_(file_system))
- [Quinlan, McKie, Cox — Fossil: An Archival File Server](http://www.scs.stanford.edu/06wi-cs240d/lab/fossil.pdf)
- [Bonwick and Ahrens — *The Zettabyte File System*](https://www.semanticscholar.org/paper/The-Zettabyte-File-System-Bonwick-Ahrens/27f81148ecbcd04dd97cebd717c8921e5f2a4373)
- [Bonwick and Moore — ZFS: The Last Word in File Systems](https://www.racf.bnl.gov/Facility/TechnologyMeeting/Archive/Apr-09-2007/zfs.pdf)
- [Apache Iceberg specification](https://iceberg.apache.org/spec/)
- [Iceberg format spec on GitHub](https://github.com/apache/iceberg/blob/main/format/spec.md)
- [Delta Lake transaction log overview — Databricks](https://www.databricks.com/blog/2019/08/21/diving-into-delta-lake-unpacking-the-transaction-log.html)
- [Delta Lake transaction log protocol](https://delta.io/blog/2023-07-07-delta-lake-transaction-log-protocol/)
- [Apache Hudi overview](https://hudi.apache.org/docs/overview/)
- [Project Nessie](https://projectnessie.org/)
- [lakeFS](https://lakefs.io/)
- [lakeFS versioning internals](https://docs.lakefs.io/v1.60/understand/how/versioning-internals/)
- [DoltHub — Prolly Trees](https://www.dolthub.com/blog/2024-03-03-prolly-trees/)
- [SQLite as Application File Format](https://sqlite.org/appfileformat.html)
- [Hipp on SQLite — CoRecursive Podcast](https://corecursive.com/066-sqlite-with-richard-hipp/)
- [Perkeep](https://perkeep.org/)
- [Perkeep — Wikipedia](https://en.wikipedia.org/wiki/Perkeep)
- [Vangoor, Tarasov, Zadok — *To FUSE or Not to FUSE: Performance of User-Space File Systems* (FAST 2017)](https://www.usenix.org/system/files/conference/fast17/fast17-vangoor.pdf)
- [Performance and Resource Utilization of FUSE User-Space File Systems (ACM Transactions)](https://dl.acm.org/doi/fullHtml/10.1145/3310148)
- [Turso AgentFS](https://turso.tech/blog/agentfs)
- [Gifford, Jouvelot, Sheldon, O'Toole — *Semantic File Systems* (SOSP 1991)](https://www.cs.cornell.edu/people/egs/615/sfs.pdf) — virtual directories, transducers, path-as-conjunctive-query
- [MIT 6.826 lecture notes — Semantic File Systems handout](https://web.mit.edu/6.826/www/notes/HO13.pdf)
- [Semantic file system — Wikipedia](https://en.wikipedia.org/wiki/Semantic_file_system)
- [Tagsistant — semantic FUSE filesystem](https://tagsistant.org/)
- [Tagsistant — Wikipedia](https://en.wikipedia.org/wiki/Tagsistant)
- [Reiser4 Future Vision (archived)](https://archive.kernel.org/oldwiki/reiser4.wiki.kernel.org/index.php/Future_Vision.html)
- [Datomic data model overview](https://docs.datomic.com/datomic-overview.html) — entity-attribute-value-tx (EAVT) and references-as-attributes
- [Microsoft Cairo — BetaArchive Wiki](https://www.betaarchive.com/wiki/index.php/Microsoft_Cairo) — Object File System (OFS), 1993–1996, WinFS predecessor [NEEDS VERIFICATION — primary Microsoft sources for OFS are not online]
- [WinFS lessons — Kellblog (2005)](https://kellblog.com/2005/08/30/lessons-from-winfs/)
- [Frank's World — WinFS retrospective (2025)](https://www.franksworld.com/2025/05/14/winfs-windows-future-storage-canceled-what-you-need-to-know-from-a-retired-microsoft-engineer/)
- [Lexical File Names in Plan 9 (Pike)](https://9p.io/sys/doc/lexnames.html) — bind vs. symlinks
- [Plan 9 bind(1) man page](http://man.cat-v.org/plan_9/1/bind)
- Cross-references in this repo: [2026-02-17 database VFS patterns](2026-02-17-database-vfs-patterns.md), [2026-02-17 AI agent filesystems](2026-02-17-ai-agent-filesystems.md), [2026-04-19 plan9 and plan9port](2026-04-19-plan9-and-plan9port.md), [2026-04-19 freebsd VFS](2026-04-19-freebsd-vfs.md), [2026-04-23 letta](2026-04-23-letta.md), [constitution](../constitution.md)
