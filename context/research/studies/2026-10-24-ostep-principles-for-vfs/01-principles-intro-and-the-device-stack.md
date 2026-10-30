# Study 01: the design goals, the device stack, the atomic unit, and the evaluation axes

- **Date:** 2026-10-24
- **Brief:** `00-brief.md` in this folder.
- **Book section:** OSTEP v1.10, chapter 2 (Introduction to Operating Systems), chapter 35 (A Dialogue on Persistence), chapter 36 (I/O Devices), chapter 37 (Hard Disk Drives), chapter 38 (RAID). Read in full from the `pdftotext -layout` split.
- **Page citations** use the page number printed at the top of each chapter page (each chapter restarts at 1). To find the PDF page, add 28 for chapter 2, 455 for chapter 35, 457 for chapter 36, 471 for chapter 37 and 487 for chapter 38.
- **No book text is quoted.** Every idea from the book is paraphrased and cited by chapter and page.
- **vfs state:** HEAD `ac5c515` on `main`.
- **Labels:** **READ** (the book, or a vfs file at `ac5c515`), **EXECUTED** (ran here with `uv run`), **INFERRED** (my reasoning).

## The angle, in one line

Chapter 2 gives a checklist of design goals. Chapter 36 gives a layered stack. Chapter 37 gives an interface with one honest atomic unit. Chapter 38 gives a method: judge a design on named axes. This study lays each of the four against vfs.

---

## 1. What the chapters say

**Chapter 2, Introduction.** An operating system does three jobs. It **virtualizes** a physical resource (CPU, memory, disk) into an easier, more general form of itself. It handles **concurrency**. It keeps data **persistent**. (READ, ch. 2 pp. 1–2, 7–9.) The OS is also a standard library of system calls and a resource manager (READ, ch. 2 p. 2). Questions about which job goes next are answered by a **policy**; the ability to do the thing at all is a **mechanism** (READ, ch. 2 p. 4). The disk is the one resource the OS does *not* virtualize per program, because files are meant to be shared between programs (READ, ch. 2 p. 9). The chapter then names the design goals: abstraction for ease of use, high performance meaning low overhead in time and space, protection and isolation between programs, reliability, and then energy, security and mobility (READ, ch. 2 pp. 11–12). The history section explains why a file system cannot be a library: a library cannot stop one program from reading another's files; the system call, a trap that raises the hardware privilege level, can (READ, ch. 2 pp. 12–13).

**Chapter 35, Dialogue on persistence.** Keeping information takes real extra work, like preserving fruit for winter. The work is making data survive crashes, disk failures and power loss (READ, ch. 35 p. 3).

**Chapter 36, I/O devices.** Every device has two parts: an interface the rest of the system talks to, and internals that implement it (READ, ch. 36 p. 3). The simple protocol is poll the status, write the data, write the command, poll again (READ, ch. 36 p. 4). Interrupts let the CPU do other work while a slow device runs; polling is still better for a fast device or under a flood of events (READ, ch. 36 pp. 5–6). DMA moves bulk data without the CPU hand-carrying each word (READ, ch. 36 pp. 6–7). The device driver holds every device-specific detail, so the file system above can stay device-neutral; the Linux stack runs application, POSIX API, file system, generic block layer, driver, device, with a raw block interface on the side for tools like a file-system checker (READ, ch. 36 pp. 8–9). Two warnings close it. A generic layer can throw away a rich device's error detail, so the file system only sees a generic I/O error. And drivers are most of the kernel's code and a leading source of its crashes (READ, ch. 36 p. 9).

**Chapter 37, Hard disk drives.** The interface is an array of sectors numbered 0 to n−1; that numbering is the drive's address space (READ, ch. 37 p. 1). Multi-sector writes are allowed, but the maker promises atomicity for one sector only. A larger write can be torn by a power loss (READ, ch. 37 p. 1). Clients also rely on an unstated contract: nearby blocks are faster than far ones, and sequential access is fastest (READ, ch. 37 pp. 1–2). The drive may acknowledge a write when it reaches its cache (write-back) or when it reaches the platter (write-through); write-back looks faster and can break ordering guarantees (READ, ch. 37 p. 5). The cost of one I/O is a fixed positioning cost (seek plus rotation) plus a transfer cost; small random I/O is two orders of magnitude slower than sequential, so use the disk sequentially or in big chunks (READ, ch. 37 pp. 6–8). Scheduling picks the next request; the best scheduler needs geometry only the drive knows, so modern systems hand the drive a small window and let it order them, while the OS merges adjacent requests (READ, ch. 37 pp. 10–13).

**Chapter 38, RAID.** Many disks can be made to look like one bigger, faster, more reliable disk, and because it looks like a disk, nothing above it has to change: transparency is what got RAID deployed (READ, ch. 38 pp. 1–2). One logical I/O becomes one or more physical I/Os (READ, ch. 38 p. 2). Before comparing designs, the chapter fixes a **fault model** (fail-stop: a disk works or is wholly and detectably dead) and three **evaluation axes**: capacity, reliability and performance, with performance split by workload (sequential or random, read or write) and by measure (single-request latency or steady-state throughput) (READ, ch. 38 pp. 3–4, 6). A write that must update two disks can be left half-done by a crash; the cure is a write-ahead log (READ, ch. 38 p. 9). In parity RAID every small write must touch the one parity disk, so that disk serializes all writes no matter how many disks are added; rotating parity across disks removes the hot spot (READ, ch. 38 pp. 13–14). The chapter ends with one table scoring each level on every axis, and says the right level depends on what the user values (READ, ch. 38 pp. 15–16).

---

## 2. Principles vfs should adopt

Each item: the principle; where the book says it; whether vfs follows it; the one change it implies.

### 2.1 The design-goal checklist (chapter 2 laid on vfs)

The brief asked for chapter 2's goals as a checklist. Here it is first, because several numbered principles below expand one row.

| Book goal (ch. 2 pp. 11–12) | What it means for vfs | Status | Evidence |
|---|---|---|---|
| Abstraction, ease of use | A small path-keyed set of verbs; the database is hidden | Follows | `base.py` docstring: paths cross as `str`, storage is behind the funnel (READ) |
| Performance = low overhead in time and space | The cost vfs adds above the engine: statements per verb and per-row construction | Half | S05 in the 2026-10-23 memo §2: nine statements for a one-row create; about 27 allocated blocks per returned row (READ, memo) |
| Protection between programs | One caller cannot see or change what its rights do not cover | Follows at the wire, not in-process | Principle 4 below |
| Isolation | A caller's view is its own visible set, never another's | Follows | ADR 065 (hidden rows are absent); ADR 063 (a session never widens itself) (READ, titles and memo) |
| Reliability | One failing mount or engine must not take the router down | Follows | ADR 008: every dispatch gather settles; ADR 010: errors carry their source mount (READ) |
| Security | Protection extended to hostile callers | Half | ADR 068 pt 7: `serve()` refuses an open posture without an explicit flag (READ) |
| Energy, mobility | Not vfs goals | Does not apply | INFERRED |

### 2.2 The numbered principles

1. **A file system is a shared resource, protected by rights, not split into private copies.**
   - Book: the OS gives each program a private CPU and memory but deliberately not a private disk, because files exist to be shared (READ, ch. 2 p. 9).
   - vfs: **follows.** One namespace per router (`base.py` docstring, READ); rights are a view over shared rows (ADR 006, ADR 065).
   - Change: none.

2. **Keep mechanism and policy apart.**
   - Book: mechanisms are the abilities; policies decide which and when (READ, ch. 2 p. 4).
   - vfs: **follows.** `DialectProfile` is declared policy and the statement builders are mechanism (`dialects.py:150`, READ). `MountMeta` says policy lives on the entry and state on the storage (`base.py:137`, READ). Posture is data, not a mode knob (ADR 068 pt 1, READ). ADR 084 makes the gate order the execution policy.
   - Change: none.

3. **Name the design goals and trade against them on purpose.**
   - Book: goals focus a design and justify trade-offs (READ, ch. 2 p. 11).
   - vfs: **half follows.** The goals exist, but spread out: CLAUDE.md (two audiences, never assume SQLite, no designed caps), ADRs 069 and 075 (positioning). No single list is checked per design.
   - Change: the table in §2.1 (or its successor) becomes a standing checklist each kernel ADR answers row by row. (INFERRED)

4. **Protection needs a privilege transition; a library cannot protect.**
   - Book: a file system as a plain library would let any program read any file; the system call exists to cross into a privileged mode (READ, ch. 2 pp. 12–13). Only the OS may issue device instructions (READ, ch. 36 p. 8).
   - vfs: **follows at the edges, by design.** In-process, any caller can construct `Authority.system()` (`authority.py:178`, READ), so the Python API is a library and trusts its host. The privilege line is the process edge: the system actor never crosses a wire (ADR 062 pt 4, READ); the topology lock binds wire calls only, and the host keeps admin (ADR 022 §3, READ); rights never cross into a WASI guest (memo §4.3, citing ADR 082 pin 2, READ).
   - Change: the kernel ADR should say in one sentence that vfs's protection boundary is the process edge (wire, guest), and that the in-process API is the trusted side. Today that fact is spread over three ADRs. (INFERRED)

5. **Layer the stack so everything above the driver is device-neutral.**
   - Book: the driver holds every device detail; the file system issues generic block requests and never knows the disk type (READ, ch. 36 pp. 8–9).
   - vfs: **follows.** The stack lines up like this (READ for the vfs column from `base.py`, `protocol.py`, `backend.py`, `dialects.py`; the mapping is INFERRED):

     | Book layer (ch. 36 p. 9) | vfs layer | Where |
     |---|---|---|
     | Application | Front: MCP tool, CLI, WASI provider, Python caller | specs 167, 169, 171 |
     | POSIX API | Public verbs on `VirtualFileSystem` | `base.py` |
     | (Linux VFS switch, not drawn in the figure) | The router: resolve, gate, dispatch, rebase | `base.py` |
     | File system | `DatabaseStorage`: namespace rules, versions, tombstones, indexes | `backend.py`, `staging.py`, `writes.py` |
     | Generic block layer | SQLAlchemy Core: dialect-neutral statements | `writes.py`, `reads.py` |
     | Driver | SQLAlchemy dialect, DBAPI driver, `DialectProfile` | `dialects.py` |
     | Device | The SQL engine | Postgres, SQL Server, Oracle, MariaDB, SQLite |
     | Raw interface | The tables themselves | `models/rows.py` |

     One observation from the mapping. vfs's storage protocol is **not**
     at the book's block line. It sits above the file system, where
     Linux's VFS switch sits, and each backend is a whole file system.
     So the promises the seam makes are file-system promises (whole
     operations), not block promises. (INFERRED)
   - Change: none to the layering. Principle 10 uses the observation.

6. **A generic layer must not flatten a rich device error into a generic one.**
   - Book: Linux SCSI reports rich errors, but the block layer passes up a generic I/O error, so the file system loses the detail (READ, ch. 36 p. 9).
   - vfs: **half follows.** The kind vocabulary is hierarchical and extensible: dotted kinds, longest-prefix fallback, an `x.<vendor>.*` namespace for backend kinds (`kinds.py` docstring, READ). But `classify_failure` maps every escaped driver error to one of four kinds (`backend_unavailable`, `unsupported`, `internal`, `unavailable`), and the engine's own error text survives only inside the prose `detail` (`engine.py:323–349`, READ). ADR 076 says no consumer may parse prose (READ). So the engine's code (a SQLSTATE, an ORA number) is, structurally, lost. This is the book's generic-error case. (INFERRED)
   - Change: carry the engine's error code as a structured field on the error's `data` (or as a child kind), so a caller or operator can act on it without parsing a message. (INFERRED)

7. **Keep a raw interface for the tools that need it, and keep normal callers off it.**
   - Book: a raw block interface lets a checker or defragmenter bypass the file abstraction (READ, ch. 36 p. 9).
   - vfs: **half follows.** The managed raw doors exist: the `/.vfs` meta subtree is hidden from default enumeration (`protocol.py` docstring, READ); the system actor serves batch loaders and backups (ADR 062 pt 4, READ). The *real* raw interface is direct SQL on the tables. The only stance on it is a consequence line: a row edited behind vfs's back can carry a bad path into results, accepted because the write path remains the gate (ADR 041, Consequences, READ).
   - Change: state in the storage seam's fault model (principle 16) that the tables are vfs-private, and that any out-of-band edit is outside the contract. (INFERRED)

8. **Drivers are most of the code and most of the bugs; keep the device-specific part small, declared, and tested on the real device.**
   - Book: over 70% of Linux is drivers, and they cause many crashes (READ, ch. 36 p. 9). Simulator results are suspect until a real system agrees (READ, ch. 2 p. 19).
   - vfs: **follows.** Dialect facts are declared fields, read from SQLAlchemy where it models them (CLAUDE.md, `dialects.py:150`, READ). SQLite is the dev default, never the target, and every engine has a real test leg (CLAUDE.md, READ). `InMemoryStorage` is SQLite, so it is the simulator here (`memory.py` docstring, READ).
   - Change: none.

9. **Overlap slow I/O with other work, and move bulk data through the bulk path.**
   - Book: interrupts let the CPU run other work during I/O; DMA stops the CPU from copying each word by hand (READ, ch. 36 pp. 5–7).
   - vfs: **follows.** Every verb is async; per-mount groups dispatch concurrently and settle together (ADR 008, `base.py` `_gather_settled`, READ). Bulk inserts go through the driver's own executemany or Postgres `COPY` (ADR 056; `bulk_insert` field in `dialects.py`, READ). Pool exhaustion classifies as an operating condition, not a raise (`backend.py` `_execute`, READ), which is the polite cousin of the book's livelock warning.
   - Change: none.

10. **The interface states its atomic unit. Anything larger is built on top, and is declared as such.**
    - Book: a disk is an array of sectors and promises one thing about failure: a single sector write is all or nothing. A bigger write can tear (READ, ch. 37 p. 1). Everything in the crash-consistency chapters is built on knowing exactly that unit.
    - vfs: **half follows.** What vfs actually does today:

      | Unit | Atomic? | Evidence |
      |---|---|---|
      | One verb call on one mount (the whole batch) | Yes: commit only if the whole batch succeeded | `backend.py` `_mutate`: commit iff success (READ). Probe: a batch with one bad entry wrote nothing (EXECUTED, case 1) |
      | A 10,000-entry batch on one mount | Yes, one transaction | Probe: one commit for 10,000 rows; 10,000 good plus 1 bad wrote 0 rows (EXECUTED, cases 3–4) |
      | `edit` with several edits | Yes, and documented | `base.py:1001`: one failed match applies nothing (READ) |
      | One batch that spans two mounts | **No.** Each mount commits on its own | Probe: the good entry on `/` landed while the bad one on `/b` refused (EXECUTED, case 2). The router merges settled per-mount results (`base.py` `_route_entry_batch`, READ) |
      | Maintenance passes (relabel, render, embed) | No, by design: many short transactions with a resumable mark | `labels.py:216`, `render.py`, `embed.py` docstrings (READ) |
      | Reads across a batch | No, by design: per-target results | `protocol.py` docstring: partial results, per-target errors (READ) |

      The behaviour is good. What is missing is the declaration. The
      storage protocol says transactions are backend-internal, but it
      never states that one mutation call is all-or-nothing
      (`protocol.py` docstring, READ). The router's `write` docstring
      does not say that a cross-mount batch can land partially (READ,
      `base.py:935`). ADR 008 mentions batch partial successes in
      passing (READ). ADR 001 says cross-verb atomicity would need a
      designed entry point (READ).
    - Change: write the atomic unit into the seam's contract in one
      sentence, the way a disk spec states its sector: **one mutation
      call, on one mount, commits whole or not at all.** Say beside it
      that a batch spanning mounts is per-mount atomic only, and that
      maintenance passes are resumable, not atomic. A declared trait
      (say, the atomic unit) would let a wire backend or adapter that
      cannot keep this promise say so. (INFERRED)

11. **Write the unwritten contract down.**
    - Book: disk clients rely on performance facts the interface never states (near is fast, sequential is fastest) (READ, ch. 37 pp. 1–2).
    - vfs: **half follows.** `traits()` already writes several down: grep tier, staleness window, durability, arbitration mode (`protocol.py:66–85`, `backend.py:287–300`, READ). Still unwritten: what each verb costs as a function of batch size and result size. For example `ls` of 10,000 children returns all 10,000 rows with no cursor (memo §2, S05, READ).
    - Change: each kernel verb's docstring states its statement count as a function of N, pinned by a count test (CLAUDE.md already requires counting operations, never clocks). (INFERRED)

12. **Acknowledge only what is durable, or declare that you don't.**
    - Book: write-back caching reports done before the data is safe; write-through waits. The first is faster and can break ordering (READ, ch. 37 p. 5).
    - vfs: **follows.** `durability` is a declared trait with values `full` and `relaxed`. Only tuned, measured profiles claim `full`; an unknown dialect claims nothing (`backend.py:296–300`, READ).
    - Change: none.

13. **Cost is a fixed positioning part plus a per-unit transfer part; amortize the fixed part.**
    - Book: one I/O costs seek plus rotation plus transfer; small random I/O wastes almost all its time positioning, so batch and go sequential (READ, ch. 37 pp. 6–8).
    - vfs: **follows for ETL, by contract.** The vfs analogue of positioning is the per-statement round trip; the transfer is rows. A one-row create costs nine statements (memo §2, S05, READ); a 10,000-row batch costs one transaction (EXECUTED, case
      3) and chunked multi-row statements (`writes.py` docstring, READ). An agent's single call pays the full fixed cost every time, which is the book's random workload. (INFERRED)
    - Change: none beyond principle 11.

14. **Let the layer that knows the geometry do the scheduling.**
    - Book: only the drive knows head position and track layout, so the OS hands it a window of requests and lets it order them; the OS merges adjacent requests first (READ, ch. 37 pp. 12–13).
    - vfs: **follows.** vfs pushes predicates, rights and ranking into the engine, which knows its indexes and pages: pushdown doctrine (ADRs 032, 045), rights compiled into the query (ADR 067), the distance function in the engine (ADR 059). vfs merges requests into chunked `IN` lists sized by the dialect (`dialects.py`, CLAUDE.md, READ).
    - Change: none.

15. **Transparency gets a design deployed.**
    - Book: RAID succeeded because it looked exactly like a disk, so no software had to change (READ, ch. 38 p. 2).
    - vfs: **follows.** A mount binds anything that satisfies `StorageBackend`; a router can be wrapped as a backend, and MCP clients are wire backends (`base.py` docstring, READ). An unknown SQL dialect still serves the core verbs (ADR 059 pt 4, READ).
    - Change: none.

16. **Fix the fault model before you design.**
    - Book: RAID designs are compared only after the chapter states which faults are expected and how they are detected (READ, ch. 38 p. 3).
    - vfs: **half follows.** The pieces exist but are scattered: a wire peer's death is a `TransportError`, an in-process exception is a bug (`protocol.py`, READ); retry classes per kind (`kinds.py`, READ); driver failures classified (`engine.py:323`, READ); a lost race is a retryable `conflict` (`backend.py` `_mutate`, READ); out-of-band edits are accepted risk (ADR 041, READ). A SQL engine rarely fails in the book's clean fail-stop way: it times out, deadlocks, loses a serialization race, or drops a connection. (INFERRED)
    - Change: one written fault model for the storage seam, in one place: which failures are detected and how they classify, which are retried, and which are out of scope (silent engine corruption, out-of-band table edits). (INFERRED)

17. **One logical update over several devices needs a log, or it can tear.**
    - Book: a mirrored write that reaches one disk and not the other leaves the copies inconsistent; a write-ahead log fixes it (READ, ch. 38 p. 9).
    - vfs: **does not, across mounts, and does not claim to.** Inside a mount the engine's transaction covers every table the verb touches (`writes.py` docstring: one transaction, READ). Across mounts there is no log; the cross-mount batch tears in the book's sense (EXECUTED, case 2).
    - Change: none to the mechanism today. The declaration in principle 10 is the change. If cross-mount atomicity is ever wanted, it is a designed entry point (ADR 001's words, READ), not a router tweak. (INFERRED)

18. **One spot that every write must touch caps write throughput; spread the hot spot.**
    - Book: parity RAID's single parity disk serializes all small writes however many disks there are; rotating parity fixes most of it (READ, ch. 38 pp. 13–14).
    - vfs: **half follows.** vfs has two such spots. First, the serialized verbs (delete, restore, sweep, move, copy) run one at a time per mount on the `vfs_lock` row (ADR 078, READ). ADR 078 already moved the hot *reads* off that point onto a separate row, which is the book's fix in spirit. Second, every child create bumps its parent's row (ADR 029 §1; `writes.py` docstring, READ), so concurrent creates into one directory meet on one row. (INFERRED) ADR 025 tells bulk writers to partition by subtree, which spreads load the way rotating parity does (READ).
    - Change: none now. Measure contention by counting waits or redrives before changing anything, as ADR 025's revisit trigger already says. (INFERRED)

19. **Judge every design on fixed, named axes, per workload.**
    - Book: RAID levels are scored on capacity, reliability and performance; performance is split by workload and by latency versus throughput; one summary table ends the chapter, and the verdict depends on what the user values (READ, ch. 38 pp. 3–4, 6, 15–16).
    - vfs: **half follows.** The review skills already split by lens (scale, contract, test). ADRs record measurements (ADR 047). But no ADR scores its options on one fixed set of axes.
    - Change: a standing axis table for kernel-level ADRs. A proposal for the rows, in vfs's own terms (INFERRED):

      | Axis | Question |
      |---|---|
      | Agent latency | Statements and round trips for one small call |
      | ETL throughput | Statements and transactions for a 10,000-entry batch |
      | Boundedness | Does any statement grow with N past the dialect budget? |
      | Correctness under rivals | What does a concurrent writer see; what redrives |
      | Atomic unit | What commits together; what can tear |
      | Dialect reach | Which engines serve it; what the generic floor gets |
      | Protection | Can the change widen what a caller sees |
      | Overhead | Per-row construction and allocation above the engine |

---

## 3. Nouns and verbs

**Adopt name** means use the book's word. **Concept, own name** means keep vfs's word for the same idea. **Do not have** means vfs should deliberately lack it.

| Book term (where) | vfs today | Decision | Reason |
|---|---|---|---|
| Operating system / kernel (ch. 2 p. 2) | The kernel in the 2026-10-23 memo (router core plus storage seam) | Adopt name | The memo already uses it; it means the part under the one gate |
| Virtualization (ch. 2 p. 2) | none as a word | Concept, own name | vfs turns a SQL engine into a file tree; the name vfs already says it |
| System call (ch. 2 p. 13) | A public verb; an MCP tool call | Concept, own name | Verb is the established term in vfs |
| Trap / privilege level (ch. 2 p. 13) | The wire edge: token in, `Authority` out (ADR 062) | Concept, own name | The privilege change is a process edge, not a CPU mode |
| User mode / kernel mode (ch. 2 p. 13) | Wire caller or guest / in-process host | Concept, own name | See principle 4 |
| Mechanism / policy (ch. 2 p. 4) | Builders / `DialectProfile`, posture, `MountMeta` | Adopt name | Useful words for review; vfs already practices the split |
| Resource manager (ch. 2 p. 2) | none | Do not have | vfs does not allocate the engine's resources; the engine does |
| Batch processing (ch. 2 p. 13) | ETL batches (`entries=`) | Concept, own name | The 10,000-entry contract |
| Interactive / time-sharing (ch. 2 p. 14) | Agent loops | Concept, own name | The second audience |
| Device (ch. 36 p. 3) | The SQL engine | Concept, own name | Engine is the vfs word |
| Interface vs internals (ch. 36 p. 3) | Protocol vs backend (ADR 001) | Concept, own name | Already the seam's shape |
| Status register (ch. 36 p. 4) | `capabilities()`, `traits()` | Concept, own name | Declared, read before use |
| Device driver (ch. 36 p. 8) | SQLAlchemy dialect + DBAPI driver + `DialectProfile` | Concept, own name | Dialect is the vfs word |
| Generic block layer (ch. 36 p. 9) | SQLAlchemy Core | Concept, own name | Dialect-neutral statements |
| Raw interface (ch. 36 p. 9) | `/.vfs` meta, system actor, and the tables | Concept, own name | Principle 7 |
| Generic I/O error, EIO (ch. 36 p. 9) | `vfs.unavailable` with prose detail | Concept, own name | Principle 6: add the engine code as data |
| Polling / interrupt (ch. 36 pp. 4–5) | `await` on the driver | Do not have | asyncio replaces both; there is nothing to poll |
| Interrupt coalescing (ch. 36 p. 6) | Batching per mount | Concept, own name | Fewer, larger statements |
| DMA (ch. 36 p. 6) | Driver executemany, `COPY` (ADR 056) | Concept, own name | Bulk path that skips per-row Python |
| Programmed I/O (ch. 36 p. 4) | A per-row Python loop issuing statements | Do not have | The thing ADR 056 removed |
| Sector / block (ch. 37 p. 1) | Entry row | Concept, own name | The unit a verb names |
| Address space 0..n−1 (ch. 37 p. 1) | The path namespace | Concept, own name | Hierarchical and sparse, not dense integers; see §4 |
| Atomic sector write (ch. 37 p. 1) | One mutation call on one mount | **Adopt the concept, name it** | Principle 10: it exists but is unnamed at the seam |
| Torn write (ch. 37 p. 1) | Cross-mount batch landing in part | **Adopt name** | A short, exact word for the case vfs should declare |
| Unwritten contract (ch. 37 p. 2) | Traits, plus undeclared costs | Adopt name | Good review word for what is still unstated |
| Write-back / write-through (ch. 37 p. 5) | `durability`: `relaxed` / `full` | Concept, own name | Already declared |
| Seek + rotation, transfer (ch. 37 p. 6) | Per-statement round trip, rows | Concept, own name | The vfs cost model, principle 13 |
| Random vs sequential workload (ch. 37 p. 7) | Agent calls vs ETL batches | Concept, own name | The two audiences |
| Disk scheduler (ch. 37 p. 10) | The engine's planner | Do not have in vfs | The engine knows the geometry, principle 14 |
| I/O merging (ch. 37 p. 13) | Chunked `IN` lists, per-mount grouping | Concept, own name | Already done |
| Starvation (ch. 37 p. 11) | none named | Concept, own name | Relevant to serialized verbs queuing on one lock row |
| RAID, looks like one disk (ch. 38 p. 1) | The router over mounts, one namespace | Concept, own name | Many backends, one tree |
| Logical vs physical I/O (ch. 38 p. 2) | One verb vs its N statements | Adopt the pair | Clear words for cost reviews |
| Mapping problem (ch. 38 p. 5) | Longest-prefix mount resolution | Concept, own name | `base.py` resolve |
| Fault model, fail-stop (ch. 38 p. 3) | Scattered: `TransportError`, retry classes | **Adopt name** | Principle 16 |
| Latent sector error (ch. 38 p. 3) | Silent engine corruption | Do not have | Out of scope; the engine's job |
| Consistent-update problem (ch. 38 p. 9) | Cross-mount batch | Adopt name | Principle 17 |
| Write-ahead log (ch. 38 p. 9) | The engine's own; none across mounts | Do not have, today | Only if cross-mount atomicity is ever designed |
| Parity disk bottleneck, small-write problem (ch. 38 p. 13) | `vfs_lock` row, parent bumps | Concept, own name: hot spot | Principle 18 |
| Mirroring, parity, hot spare (ch. 38) | none | Do not have | Redundancy is the engine's and the operator's job |
| Capacity / reliability / performance axes (ch. 38 p. 3) | none standing | **Adopt the method** | Principle 19, with vfs's own axes |
| open, close (ch. 2 p. 10) | none | Do not have | The memo §4.2: handles belong to fronts |
| read, write (ch. 2 p. 10) | `read`, `write` | Adopt name | Already |
| fsync | none | Do not have | Every mutation commits before it returns; `durability` declares the rest |

---

## 4. What does not transfer

1. **The atomic unit is big and free, not small and scarce.** A disk gives one 512-byte sector. Everything larger must be built with a journal. A SQL engine gives a transaction of any size, and vfs inherits it: a 10,000-row batch commits once (EXECUTED, case 3). So vfs does not need the book's crash-consistency machinery inside a mount. Its hard problems move elsewhere: keeping each statement inside the dialect's budget, keeping lock time short, and spanning two engines. (INFERRED)
2. **The address space is not a dense array.** A disk address is an integer, and near integers are near on the platter. A vfs address is a path. Locality comes from index order, such as the `(parent_id, name)` order the children read already uses (memo §4.2, READ), not from geometry. (INFERRED)
3. **There is no geometry for vfs to schedule against.** Seek and rotation have no direct analogue. The fixed cost per call is a network round trip plus planning, and the engine schedules its own pages. vfs's only scheduling lever is how many statements it sends. (INFERRED)
4. **Hardware mechanisms do not transfer.** Registers, interrupts, DMA engines, memory-mapped I/O and buses are hardware. Their lessons transfer (overlap, offload, declare status); their machinery does not. Python's `await` replaces both polling and interrupts. (INFERRED)
5. **Redundancy is not vfs's job.** RAID builds reliability by copying or parity across disks. vfs leaves replication and backup to the engine and the operator. RAID's transparency rule and its evaluation method transfer; its levels do not. (INFERRED)
6. **There is no hardware privilege bit in-process.** The book's protection rests on a CPU mode. A Python caller in the same process can construct the system authority (`authority.py:178`, READ). So vfs's protection holds only where a process edge exists: the wire and the WASI guest. (READ, ADRs 022, 062; INFERRED conclusion)
7. **Fail-stop is too clean for a database.** The book's first fault model has a disk either working or obviously dead. An engine fails partly and transiently: timeouts, deadlocks, lost serialization races, dropped connections. vfs's retry classes and `conflict` redrive are richer than fail-stop, and must be. (INFERRED)
8. **Some of the stack is upside down.** In the book, the device-neutral line sits *below* the file system. In vfs, the storage seam sits *above* the file system: each backend is a whole file system, like a Linux VFS switch entry. The block-layer analogue (SQLAlchemy Core) is inside the backend. So the seam's promises are about whole operations, never about rows or statements. (INFERRED)

---

## 5. The one design lesson

A disk tells its users exactly one thing about failure, which sector write is atomic, and every layer above is built on that one honest promise. vfs already keeps a strong promise, one mutation call on one mount commits whole or not at all, but it never states it at the seam, and it never says that a batch spanning mounts can tear. State the atomic unit and the fault model in the storage contract, and judge every kernel design on one fixed table of named axes, as the RAID chapter does.

---

## Appendix: the executed probe

Run from the repo root on 2026-10-24 with `uv run python -I <scratchpad>/s01/atomic_unit.py`, vfs at `ac5c515`, `InMemoryStorage` (SQLite). The script counts `AsyncSession.commit` calls by wrapping the method. It writes nothing to the repo.

What it does, in four cases:

1. One mount. A batch of `/a.txt` (good) and `/missing/b.txt` (parent absent, `parents=False`).
2. Two mounts (`/` and `/b`). A batch of `/a.txt` (good, on `/`) and `/b/missing/x.txt` (bad, on `/b`).
3. One mount. 10,000 entries under `/etl`.
4. One mount. The same 10,000 entries plus one bad entry at the end.

Output (EXECUTED):

```
1 single-mount batch with one bad entry: success= False errors= [(vfs.not_found, '/missing')] | /a.txt landed? False
2 cross-mount batch, bad entry on /b only: success= False errors= [(vfs.not_found, '/b/missing')] | /a.txt landed? True
3 10,000-entry batch: success= True rows= 10000 commits= 1
4 10,000 good + 1 bad: success= False errors= 1 commits= 0 | rows now under /etl: 0
```

Reading it: on one mount, the whole call is the atomic unit at any size (cases 1, 3, 4). Across mounts, each mount is its own unit, and the batch as a whole can land in part (case 2).
