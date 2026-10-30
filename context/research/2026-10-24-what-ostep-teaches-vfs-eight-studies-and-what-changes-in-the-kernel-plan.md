# What OSTEP teaches vfs: eight studies, and what changes in the kernel plan

- **Status:** research memo with a recommendation (commits us to nothing). It feeds the kernel ADR that yesterday's memo proposed and reorders that memo's spec series.
- **Date:** 2026-10-24
- **Owner:** Clay Gendron
- **Question:** Clay, 2026-10-24: take *Operating Systems: Three Easy Pieces* (OSTEP) section by section and write up the principles, verbs and nouns vfs should adopt and build around.
- **Method:** the PDF was converted to text and split by chapter into eight sections. Eight Opus agents each read one section in full and the vfs code at HEAD `ac5c515`, then wrote a study with the same five parts: what the chapters say, principles vfs should adopt, nouns and verbs, what does not transfer, one lesson. Thirteen probe scripts ran under `uv run` against the SQLite backend (S02's was scratch and is not kept); the scripts, and the outputs where they were captured, are kept beside the studies. The book is paraphrased throughout and never quoted (Clay's rule, 2026-10-24).
- **Sources:** `context/research/studies/2026-10-24-ostep-principles-for-vfs/`: `00-brief.md`; `01-principles-intro-and-the-device-stack.md` (ch. 2, 35–38); `02-files-and-directories-the-api.md` (ch. 39); `03-file-system-implementation-vsfs.md` (ch. 40); `04-locality-and-log-structure-ffs-lfs-ssd.md` (ch. 41, 43, 44); `05-crash-consistency-and-data-integrity.md` (ch. 42, 45, 46); `06-distribution-nfs-afs.md` (ch. 48–51); `07-concurrency-locks-structures-events.md` (ch. 26, 28–30, 32, 33); `08-virtualization-abstraction-gate-allocation-caching.md` (ch. 4, 6, 13, 17–19); `experiments/s01/`, `s03/`–`s08/`. Cited below as S01–S08.
- **Relation to yesterday's memo:** `2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md` (the kernel memo). This memo confirms its shape, corrects two of its claims (§2.2 and §2.9 below), and reorders its spec series (§5).

## 0. The recommendation in one paragraph

The book confirms the kernel memo's shape: vfs already has a real kernel in the textbook sense, with a fixed table of operations, one gate every call passes, arguments checked before anything acts, and rights judged on every access (S08). What the book adds is a list of promises vfs keeps but has never written down, and three places where vfs is quietly wrong. The unwritten promises: one call on one mount commits whole or not at all, a batch across two mounts can tear, the search indexes catch up after the write rather than with it, the wire is stateless, and protection is a wall only at a process edge (S01, S05, S06, S08). The three wrongs, each shown by an executed probe: a read followed by a write loses a rival's update and reports success (S07, 20 appends became 1 line); a body changed or deleted underneath vfs is served as success because the stored checksum is never compared (S05); and a replayed `move` cannot be told apart from a move that never happened (S06). So the kernel ADR should state the atomic unit, the fault model and the trust tiers in plain words, and the spec series should put `write(if_version=)` first, add an integrity pass, add a replay contract, and give version rows the cleaner they lack (S04).

## 1. What the book confirms vfs already does right

Each item is a textbook principle vfs follows today. These need no change, only a sentence in the kernel ADR so they stay true.

| Principle | Where vfs does it | Study |
|---|---|---|
| One fixed trap table; callers name a service, never an entry point | `_call_storage`'s `match op:` ending in `assert_never`; `_gate_params` first in every verb | S08 p1–3 |
| Metadata apart from data, so a stat never touches a body | `vfs_entries` never holds a body; `stat` of a 4 MiB file fetched 273 bytes (EXECUTED) | S03 p3 |
| Path lookup costs rows, not round trips | `stat` at depth 20 is 1 statement, 21 rows (EXECUTED) | S03 p5, S08 p10 |
| No shared allocator or counter on the write path | ULID ids; per-entry versions; ADR 013 removed the mount counter | S03 p6, S07 p4, S08 p16 |
| A read never writes; no access time | read builders are SELECT-only; no `atime` column | S03 p4, S08 §4 |
| Commit before reply | `_mutate` commits, then returns the `Result` | S06 p5 |
| Stateless wire: every request carries its authority and names by path | every public verb takes `authority`; `Session` holds one value | S06 p2 |
| Detect and recover for deadlocks and serialization races | retryable kinds per dialect; `with_retry`; `test_races.py` | S07 p10 |
| Derived indexes as checkpoint plus tail | gram epoch is the checkpoint; `encoded = false` rows are the tail grep scans | S04 p7, S05 §2.3 |
| Identities are never reused | ULIDs, skipped epochs, tombstones instead of frees | S05 §2.6, S08 §4 |
| Event loop kept free of I/O | async drivers throughout; the offload pool takes CPU work; no sync I/O found (EXECUTED grep) | S07 p3 |
| Rights checked on every access, cache hit included | ADR 084 pin 2; `Authority` never caches a decision | S08 p13 |

## 2. The findings that change the kernel plan

Ranked by harm today. Each names the study, the evidence label, and the change.

### 2.1 Guard the gap between calls (correctness; silent data loss)

- The book's oldest lesson: a read then a write is a critical section (S07 p1, ch. 26). Inside one vfs call every check sits inside the write statement, so vfs is correct. Across two calls nothing guards the gap.
- EXECUTED (S07): 20 concurrent read-append-write tasks on one file. All 20 reported success. One line survived. The same 20 appends through `edit` kept all 20, because `edit` checks its `old` string inside the transaction.
- S06 adds the distributed view: this is "last writer wins", the AFS model, and vfs's main client cache is a model's context window that no server can invalidate. So the check has to sit at write time, not at open time (S06 §2.3).
- S02 adds the security view: this is TOCTTOU, the check-then-use gap, reopened above the kernel by spec 167's `>>` and the WASI write-at-close (S02 p10).
- **Change:** `write(if_version=)` and `write(if_absent=)` move to the front of the spec series (§5). `>>` and the WASI close-time write use them. An append verb, if added, must carry a precondition from day one because it is the first vfs write that is not a store of a value (S06 §4).

### 2.2 State the atomic unit, and correct what commits with the body

- A disk promises exactly one thing about failure, the single sector write, and every layer above is built on that promise (S01 p10). vfs keeps a strong promise and never states it.
- EXECUTED (S01, S05): one call on one mount commits whole or not at all, at any size. A 10,000-entry batch made 1 commit. The same batch plus one bad entry wrote 0 rows. A fault injected at each of the 10 mutating statements of a 3-file write left the store untouched all 10 times.
- EXECUTED (S01): a batch spanning two mounts tears. The good entry on `/` landed while the bad one on `/b` refused. This is the book's consistent-update problem, and vfs has no log across mounts.
- READ (S03, S05): what the write transaction covers is the entry row, the path segments, the fs edge mirror, the version row, the body and the parent bumps. The trigram, lexical and vector indexes are **not** in it. The write stamps `encoded = false`; `reindex` builds the index later (ADR 033 §6). grep stays correct by scanning the dirty side. **The kernel memo said the indexes commit with the body. That was wrong and is now corrected in that memo.**
- vfs has two atomicity models without names (S05 §2.7): whole-batch verbs (`write`, `edit`, `mkdir`, `move`, `copy`, `delete`, `restore`) and resumable verbs that commit in bounded chunks with a durable mark (`posture` relabel, `reindex`, render, embed).
- **Change:** the storage seam's docstring states the atomic unit in one sentence; the kernel ADR names both models and says which verbs use which; the conformance battery gains a mixed good-and-bad `write` batch that checks every table, and a crash-at-each-statement family on every engine leg (S05 §2.11).

### 2.3 Check the checksum you already store (integrity)

- The book's rule: a checksum that is never compared protects nothing (S05 §2.8, ch. 45). vfs stores sha256 as `content_hash` on the entry row, which is the parent-row placement ZFS uses to catch lost writes.
- EXECUTED (S05): a body rewritten underneath vfs with direct SQL was served by `read` as success with the wrong text. A body row deleted underneath vfs was served as success with `content=None` while the entry still said 11 bytes and kept its hash. A full `reindex` reported nothing. grep, by contrast, verified every candidate against the body and returned no false hit.
- The fault that matters here is not bit rot. It is the out-of-band writer: an ETL job or migration with SQL credentials, or a vfs bug that writes a body under the wrong id. Engine page checksums cannot see faults above the engine. Only `content_hash` can (S05 §2.10).
- **Change:** verify on read, with the hash computed in the Rust engine fused into the decode the read already does, and classify a mismatch or a missing body as an error, not success. Add a report-only, paced `scrub` for the cold data nobody reads, such as version rows (S05 §2.9). Return `content_hash` on each written row so a client can check end to end without a second `stat` (S06 p13).

### 2.4 Make every mutating verb safe to replay, or recognisable on replay

- NFS stays simple because each request stands alone and most can be sent twice (S06 §5). vfs has the first property. It has the second for half its verbs.
- EXECUTED (S06 replay table): safe to send twice: `write`, `mkedge`, `rmedge`, `grant`, `revoke`, `mkdir(exist_ok=True)`. Not safe: `edit`, strict `mkdir`, `delete`, `restore`, `copy`, `move`. A replayed `delete` at least carries `vfs.trashed` in its error data. A replayed `move` returns bare `not_found`, so a client cannot tell "already moved" from "never existed".
- EXECUTED (S06): a replayed identical `write` mints no version row but still bumps the version counter, and reports `updated` though the vocabulary has `unchanged`. Every cache keyed on version then throws away a good copy, and with `if_version` a client's replay of its own write would be refused.
- A disconnect during `COMMIT` is classified as retryable `backend_unavailable`, though the commit may have landed (READ, S06 p5; not reproduced on a real engine).
- **Change:** pin the replay table as a contract, one row per mutating verb, and set `idempotentHint` where earned (spec 171). An identical-body write reports `unchanged` and leaves the version alone. A `move` replay names the destination it finds occupied by the same `entry_id`. An optional request key on mutating verbs, answered from the stored first `Result`, is the one tool that makes `move`, `edit` and a 10,000-row batch replay-safe at once (S06 p4).

### 2.5 Take row locks in one order on the hot write path

- The four deadlock conditions are all present in a vfs write batch, and circular wait is possible when two batches touch the same files in opposite caller orders (S07 p2). The doctrine says callers sort their keys; parent bumps, `bump_many` and edge endpoints do.
- EXECUTED (S07): an overwrite batch given `c, a, b, z, y` issued its UPDATE rows in exactly that order. `segments.py` drift repair locks unsorted too, against its own module's docstring.
- The retry channel catches the deadlock on Postgres, SQL Server, Oracle and MariaDB. SQLite cannot deadlock because one writer lock covers the database.
- **Change:** sort staged rows by `entry_id` or path before the insert layers and the guarded-update pass. Add jitter to `with_retry`, which today backs off 50, 100, 200 ms with no random part, the book's livelock rhythm. Name fairness as an axis in the next arbitration ADR (S07 p5).

### 2.6 Give version rows a cleaner, and bound the sweep

- LFS is the textbook for a store that never overwrites and keeps old copies until a cleaner reclaims them (S04). vfs did the WAFL move: its garbage is a feature, every version row names who wrote it.
- EXECUTED (S04): 1,000 files rewritten three times left 3,000 version rows holding 833,400 bytes beside 277,800 live bytes. A retention-0 sweep left all of them. Version rows are deleted only when their entry is purged. The `pack` step named in the schema comment and ADR 017 has no code.
- EXECUTED (S04): after deleting 900 of 1,000 children, `ls` returned 100 rows but the `(parent_id, name)` range still held 1,000 until sweep ran, so the listing looked up all 1,000 to return 100. Garbage interleaved with live data costs read work, not only space.
- One `sweep` call is one transaction over every expired root plus an orphan scan of the whole body table, under the serialization point (S04 P3).
- **Change:** the `pack` step, run as a `reindex` phase, shrinking cold versions into snapshot-plus-diff form so the full history is kept at a fraction of the bytes (Clay's decision, §6 Q3; a retention window stays a possible setting, never the default), and a `sweep` that takes a limit and returns a resumption key, the same cursor shape as `ls`. A cheap garbage gauge per mount (tombstoned rows, version rows and bytes) so a deployment job can decide when to clean (S04 P4). The `ls` cursor should page around tombstones or the sweep schedule should bound their density (S04 P9).

### 2.7 Count statements, rows and bytes, and pin the access path per verb

- The vsfs chapter teaches a file system by drawing the path each call takes and counting every block touched (S03). S03 drew the same tables for vfs and found three hidden I/Os.
- EXECUTED (S03): a one-byte `edit` of a 4 MiB file issues the same 9 statements as a one-byte edit of a 2-byte file, but fetches 8.4 MB and sends 8.4 MB. The body moves four times. Statement counts hide a difference of tens of thousands of times in bytes.
- EXECUTED (S03): every create deletes from both body tables for a row minted in the same batch; every edit selects the root row alone even when nothing missed; every edit fetches the whole pre-image twice. Each has a small fix.
- EXECUTED (S03): 10,000 overwrites in one call cost 15 statements; 200 one-file calls cost 2,200. Batching is the caller's job and it works. An agent loop writing one file per call gets none of it.
- **Change:** a golden test per verb holding the ordered access path (statement kind, first table) at three authorities, counting three units: statements, rows and body bytes moved. The three hidden I/Os are fixed. The whole-body rewrite is the next cost to cut, and the engine's own chunked storage (TOAST on Postgres, overflow pages on SQLite) is where to look before vfs chunks bodies itself (S03 p8).

### 2.8 Make the rights-cache hit nearly free

- The TLB chapter's rule: a translation cache helps only if a hit is cheap and the working set fits (S08 p12, p14). vfs's TLB is the `RightsCache`, keyed by subject set and revalidated by stamps instead of flushed, which is the right design for many processes sharing one database with no invalidation channel.
- EXECUTED (S08): a `read` as the system actor is 1 statement. As a named principal with a warm cache it is 3, two of them only to recheck the cache (`vfs_principal_revisions`, `vfs_relabels`). Cold it is 7. On a remote Postgres each is a round trip.
- The cache has no hit, miss or eviction counter. Its 1,024-entry limit could thrash on a group-chat MCP server where every distinct set of people is its own key (INFERRED, S08 p14).
- **Change:** fold the two revalidation reads into one statement, or into the data statement, and pin it by count. Count hits, misses and evictions.

### 2.9 Name the trust tiers and both halves of the gate

- A kernel earns the name only when the program cannot reach the hardware except through its trap (S08 §5). Python has no hardware mode bit.
- EXECUTED (S08): a write through a read-only router was refused. The same write made straight to the storage object with a self-constructed `Authority.system()` succeeded. This is by design (ADR 068): in-process code is trusted.
- The gate has two halves (S08 p11): the router judges capability, grammar and the structural permission maps; storage judges grants inside the SQL statement. A front that bypassed either would bypass the gate.
- **Change:** the kernel ADR names three tiers in plain words: in process the gate is a convention; on the wire it is a wall; in the wasm guest it is a wall. It names both halves as the one gate. It states one more rule from S02 p8: a front's handle carries a path and an offset, never a right, because a descriptor is checked once at open and vfs checks on every call.

### 2.10 Smaller changes the studies agree on

| Change | Why | Study |
|---|---|---|
| Expose `entry_id` as a read-only `stat` column; no verb takes it as an address | lets a tool tell "same file moved" from "new file, same name"; `(path, version)` is not a safe cache key after a rename or sweep (EXECUTED) | S02 p1, S06 p6 |
| `move(replace=)` must decide whose identity survives and what happens to edges on the loser | POSIX keeps the source inode; spec 167 keeps the target's history; the write-temp-then-rename idiom fails today (EXECUTED) | S02 p6 |
| Derive the `durability` trait from the live connection | `InMemoryStorage` is SQLite `:memory:` and declares `durability: full` (EXECUTED); nothing reads Postgres `synchronous_commit` | S02 p7 |
| Carry the engine's error code as a structured field | `classify_failure` flattens every driver error to four kinds; the SQLSTATE survives only in prose, which ADR 076 forbids parsing | S01 p6 |
| A standing axis table for kernel ADRs | RAID's method: score every option on fixed axes per workload (agent latency, ETL throughput, boundedness, correctness under rivals, atomic unit, dialect reach, protection, overhead) | S01 p19 |
| One written fault model for the storage seam | which faults are detected, how they classify, what is retried, what is out of scope (engine corruption, out-of-band edits) | S01 p16, S05 §2.10 |
| A per-dialect statement timeout from the call's remaining deadline | the wasm epoch deadline does not cover time inside a verb; no engine-side timeout exists (EXECUTED grep) | S08 p5 |
| A per-front table of when an update becomes visible and what two writers get | WASI is AFS (last closer wins); CLI `>>` is read-then-write; MCP caches are off | S06 p8 |
| Let `reindex` drain a stranded relabel mark | today only the next `posture` call finishes it; readers pay for the mark meanwhile | S05 §2.5 |
| A counted pin of loop-thread native calls per verb; offload glean's lexicon union past a threshold | CPU residue on the event loop is the book's implicit blocking | S07 p3 |
| A retry counter per verb | ADR 025's revisit trigger needs it; "rare" is an assumption until counted | S07 p6 |

## 3. Nouns and verbs, consolidated

The eight studies' tables agree. This is the merged verdict.

**Adopt the book's word** (vfs lacks a word, or the book's is sharper):

| Word | Meaning in vfs | Study |
|---|---|---|
| trap, trap table | the one door into the kernel; `_call_storage`'s `match op:` | S08 |
| atomic unit, torn write | one call on one mount commits whole; a cross-mount batch can tear | S01 |
| fault model, fail-partial | which faults each layer catches; engines fail partly, not fail-stop | S01, S05 |
| access path | the ordered statements a verb issues; the per-verb golden test | S03 |
| write amplification | rows and bytes written per file overwritten; a metric word for pins | S04 |
| garbage, cleaner | tombstones, version rows, orphan bodies; `sweep` and the missing version arm | S04 |
| scrub | scheduled read-and-verify of everything, report-only | S05 |
| idempotent, at-most-once, stateless | per-verb replay behaviour; the wire's property | S06 |
| last writer wins | the honest name for today's whole-body `write` | S06 |
| lock order, livelock, fairness | the hot path's missing sort; backoff without jitter; the unnamed axis | S07 |
| atomicity violation, order violation | review-checklist words for the two non-deadlock bug classes | S07 |
| TOCTTOU | the check-then-use gap `>>` and WASI write-back reopen | S02 |
| mechanism / policy, transparency / efficiency / protection | design words vfs already practices | S01, S08 |
| logical vs physical I/O | one verb vs its N statements | S01 |

**Keep the concept under vfs's own name:** inode is `Entry` (the row is richer than an inode and has a path); i-number is `entry_id`; superblock is the meta row; dirent is the `(parent_id, name)` key on the child; generation is `version`; compare-and-swap is the guarded update; fetch-and-add is the bump; checkpoint is the gram publish; roll-forward is grep's scan side; fsck is the drift pass; redo log is the relabel mark; capability is `Authority`; ACL is grant rows; superuser is the system actor; TLB is `RightsCache`; ASID is the subject set; big kernel lock is the serialization point; detect and recover is the retry channel; DMA is the bulk insert path; RAID's "looks like one disk" is the router over mounts.

**Deliberately not have** (each with the recorded reason):

| Not in vfs | Reason | Study |
|---|---|---|
| file descriptor, open file table, offset, `lseek`, `close` | per-process state; a descriptor is checked once and vfs checks every call; fronts own handles | S02, S08 |
| `fsync` as a verb | every verb commits before it returns; `durability` is a trait | S02, S03 |
| hard links, symlinks, link count | one path per entry is the grant coordinate; `..` resolves by text; edges key on `entry_id` and survive moves; delete never frees | S02 |
| mode bits, `chmod` | rights are per caller on the row and in grant rows; no file execute bit | S02 |
| access time | a read must never write | S03, S08 |
| journal, checkpoint region, revoke record | the engine's log does this; identities are never reused | S05 |
| callbacks, server-pushed invalidation | server state; a model cannot be called back; storage owns no background work | S06 |
| allocator, free list, bitmap | the engine owns space; vfs must never reuse an id | S03, S08 |
| spin lock, ticket lock, condition variable across processes | locks come from the engine; waits are engine queues | S07 |
| attribute cache with a nonzero TTL | what made NFS hard to reason about; spec 171 sets it to 0 | S06 |

## 4. What does not transfer

- **The atomic unit is big and free, not small and scarce.** A disk gives one sector; a SQL engine gives a transaction of any size. vfs needs none of the crash-consistency machinery inside a mount. Its hard problems move to statement budgets, lock time, and spanning two engines (S01, S05).
- **vfs is not log-structured at the body level.** It copies the old body out to a version row, then replaces the body at the same key. That is an undo log, not LFS, and it means vfs never needs an inode map to find the current copy (S04).
- **The layers below are already log-structured.** Postgres keeps old tuples until vacuum; the SSD runs its own cleaner. vfs should not add a third physical log. Its history stays a semantic feature (S04).
- **There is no hardware privilege bit in Python**, so protection holds only at a process edge (S01, S08).
- **The path is stored, so the lookup trade flips.** An inode file system pays per level at lookup and nothing at rename; vfs pays one statement at any depth and rewrites descendants on a directory move. For agents, who look up far more than they rename, this is the right way round (S03).
- **The biggest client cache cannot be invalidated.** It is the model's context window. Validate at write time (S06).
- **Isolation levels have no chapter.** The same vfs code waits on SQL Server's locking read committed and does not wait on Postgres MVCC (S07).
- **The file system knows what is in the file, and every caller sees a different tree.** The deepest break from the book, and vfs's reason to exist (S02).

## 5. What this does to yesterday's order of work

The kernel memo §7 listed eight steps. The studies reorder them and add four. The rule stays: what is incorrect today comes before what is unbounded, and both come before what is merely unstated.

1. **ADR: the kernel and the facets.** Unchanged in shape. It gains: the atomic unit and the two atomicity models (§2.2); the fault model and the trust tiers, with both halves of the gate (§2.9); the corrected statement that the body and its dirty flag commit together and the indexes catch up (§2.2); the rule that a handle carries a path and an offset, never a right; the standing axis table (§2.10).
2. **Spec: write preconditions and append** (`if_version`, `if_absent`, append as a guarded operation). Moved up from third to second, because it is the only silent data-loss bug (§2.1). Rewrites spec 167's `>>` and the WASI close-time write.
3. **Spec: integrity.** New. Verify on read in the Rust engine, classify a mismatch or a missing body, return `content_hash` on write, add a report-only `scrub` (§2.3).
4. **Spec: the listing cursor.** Unchanged, now with the tombstone finding: the cursor pages around tombstones or the sweep schedule bounds them (§2.6).
5. **Spec: replay.** New. The replay table as a contract, `unchanged` for an identical write, a recognisable `move` replay, `idempotentHint` where earned, and the optional request key (§2.4).
6. **Spec: ranged read.** Unchanged.
7. **Spec: rename and copy with `replace=`.** Unchanged, plus the identity question (§2.10).
8. **Spec: the storage seam as the kernel.** Unchanged, plus the mixed-batch and crash-at-each-statement conformance families (§2.2), the lock-order sort (§2.5), the hidden-I/O fixes and the access-path golden tests (§2.7), the rights-cache fold (§2.8), and the `durability` trait from the live connection (§2.10).
9. **Spec: history.** New. The `pack` step on `reindex` (full history kept, cold versions as deltas), a bounded `sweep` with a resumption key, and a garbage gauge (§2.6, §6 Q3). Also the `history(path)` read the kernel memo already names.
10. **Spec: the public surface regrouped.** Unchanged, plus `entry_id` as a `stat` column (§2.10).
11. **Later, independent:** chunked `data` bodies, with the note that the engine's own chunked storage is the first place to look (§2.7); a FUSE or NFS front.

## 6. Open questions, and Clay's answers (2026-10-24)

Clay answered the five questions the same day, in session. The answers are decisions for the ADR and specs to carry; this memo only records them.

- **Q1. Where does the checksum check run?** Verify on **every read**, always. Clay asked for the latency it adds. EXECUTED (`experiments/synthesis/hash_latency.py`, hashlib sha256 against a system-actor `read` on in-memory SQLite, 20 reps each):

  | Body bytes | read µs | sha256 µs | added |
  |---|---|---|---|
  | 1,000 | 1,257 | 1 | 0.1% |
  | 10,000 | 1,272 | 5 | 0.4% |
  | 100,000 | 1,261 | 41 | 3.2% |
  | 1,000,000 | 1,761 | 404 | 23% |
  | 4,000,000 | 2,166 | 1,640 | 76% |
  | 16,000,000 | 3,935 | 6,506 | 165% |

  Reading it: sha256 runs at about 2.5 GB/s here, so a file under 100 KB pays under 4%, and that is the agent workload. A 4 MiB body pays as much again as the read itself. Two caveats. The read side is the fastest vfs can be (in-process SQLite, no network); on a remote Postgres the read is slower and every percentage falls. And the percentages are wall-clock from one laptop, which belongs in a memo and never in a test. Clay then asked whether hashing should run in Rust. EXECUTED (`experiments/synthesis/hashbench/`, a standalone release build of the `sha2` crate, same sizes, same laptop, arm64):

  | Body bytes | Python `hashlib` µs | Rust `sha2` default µs | Rust `sha2` + `asm` µs |
  |---|---|---|---|
  | 10,000 | 5 | 29 | 5 |
  | 100,000 | 41 | 347 | 47 |
  | 1,000,000 | 407 | 2,974 | 814 |
  | 4,000,000 | 1,625 | 11,255 | 1,854 |
  | 16,000,000 | 6,562 | 45,134 | 7,356 |
  | throughput | 2.46 GB/s | 0.35 GB/s | 2.1 GB/s |

  Reading it: `hashlib` is OpenSSL's C code using the ARM SHA instructions, and it is the fastest of the three. The `sha2` crate's default build is 7× slower because it does not use those instructions; `-C target-cpu=native` did not help. With the crate's `asm` backend it reaches 2.1 GB/s, about 12% behind OpenSSL. A fused pass (UTF-8 validate, count lines and hash in one sweep) was no faster than two passes at any size, because the hash dominates and memory bandwidth is not the limit here. So the design note changes: **keep the hash in Python's `hashlib` for now.** Rust earns its place only if the read already decodes the body in Rust and the hash can ride that call for free, or to take a large body off the event loop, and `hashlib` already releases the GIL for inputs over 2 KB. The integrity spec should measure before moving it. Caveat: wall-clock from one laptop, and the `sha2` 0.10 `asm` feature is the older backend; the 0.11 line has hardware intrinsics of its own that were not measured.

  Clay then asked whether large bodies should be hashed off the event loop, given many users at once. EXECUTED (`experiments/synthesis/offload_threshold.py`, vfs's own `call_offloaded` seam with an 8-thread pool, 32 concurrent requests):

  | Body bytes | hash inline µs | hash offloaded µs | 32 users inline ms | 32 users offloaded ms | loop stall inline ms |
  |---|---|---|---|---|---|
  | 10,000 | 5 | 36 | 0.3 | 1.2 | 0.1 |
  | 100,000 | 43 | 79 | 1.5 | 1.1 | 0.4 |
  | 256,000 | 106 | 160 | 3.5 | 1.5 | 2.5 |
  | 1,000,000 | 404 | 451 | 13.1 | 2.5 | 12.0 |
  | 4,000,000 | 1,612 | 1,667 | 52.2 | 7.7 | 51.1 |
  | 16,000,000 | 6,542 | 6,560 | 207.2 | 28.2 | 206.2 |

  Reading it: one hand-off through the seam costs 32 µs. Below about 100 KB that is more than the hash, so small bodies stay inline. Above it, offloading wins, and the win grows with concurrency: 32 users each reading a 1 MB file wait 13 ms inline and 2.5 ms offloaded, because `hashlib` releases the GIL and the eight workers hash in parallel while the loop keeps serving everyone else. The loop-stall column is the point: inline, every other coroutine in the process freezes for the whole hash (206 ms for the 16 MB case). **Rule for the integrity spec: hash inline under a size threshold near 100 KB, offload above it, and pin the threshold by counting offload calls, never by time.** The same rule applies to the write path, which already hashes every body on the loop today (`measure_text`, `models/version.py`; S07 p3).
- **Q2. Where does the request key's stored `Result` live?** **A row in the mount's schema with a short TTL**, swept with trash. It survives a serve restart and works on every dialect.
- **Q3. Version retention?** Clay wants the **full history kept**, with versions **converted to deltas during `reindex`**. The schema already has `version_diff` and ADR 017 calls the step **`pack`**; Clay keeps that name. So the history spec (§5 step 9) is pack-on-reindex, not a retention window: no version is ever deleted by default, and the cleaner's job is to shrink cold versions into snapshot-plus-diff form. The bounded `sweep` and the garbage gauge stand.
- **Q4. Expose `entry_id`?** **Yes, as a read-only `stat` and `ls` column.** No verb accepts it as an address. Rights and routing stay path-keyed, and the ADR states the read-only line.
- **Q5. Land the small fixes now?** **Yes.** The three hidden I/Os and the lock-order sort land as green-tree fixes with count-pinned tests, through `scripts/ci.sh`, ahead of the kernel ADR, because no contract changes. Follow-up decisions, same day: the lock-order sort keys by **path**, matching the parent bumps and edge endpoints; two ride-alongs join the set, **jitter in `with_retry`** (S07 p5) and **offloading write-path hashing above the 100 KB threshold** (Q1); the fixes land as **one commit per fix**; and the **real-engine legs run** after the lock-order change, since SQLite cannot deadlock.
