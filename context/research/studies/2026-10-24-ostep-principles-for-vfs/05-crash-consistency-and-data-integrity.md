# Study 05: crash consistency and data integrity (OSTEP chapters 42, 45, 46)

- **Date:** 2026-10-24
- **Brief:** `00-brief.md` in this folder.
- **Book:** Arpaci-Dusseau and Arpaci-Dusseau, *Operating Systems: Three Easy Pieces*, version 1.10. Chapter 42 (PDF pages 567 to 587), chapter 45 (PDF 628 to 641), chapter 46 (PDF 642 to 643). Page numbers below are the chapter's own page numbers, with the PDF page in brackets. Every idea from the book is paraphrased; nothing is quoted.
- **vfs:** read at HEAD `ac5c515` on `main`. Two experiments were run with `uv run` against a SQLite file (see the appendix). Their scripts lived in the session scratchpad and are not committed.
- **Labels:** **READ** (the book, or a vfs file at `ac5c515`), **EXECUTED** (ran here), **INFERRED** (my reasoning).

**The angle.** vfs gets atomicity from the SQL engine's transaction. So the book's journaling machinery is the engine's job, not vfs's. Three things remain vfs's own job:

1. Saying what one vfs call is atomic across.
2. Keeping the book's ordering rule wherever vfs spans more than one transaction.
3. Data integrity: noticing when a stored body is wrong.

This study also asks whether the conformance suite enumerates crash points the way chapter 42 does.

---

## 1. What the chapters say

**Chapter 42, crash consistency.** One logical update often needs several separate writes to disk. A crash can land between any two of them. The chapter takes a single file append, which needs three writes (the inode, the free-space bitmap, the new data block). It then walks every combination of which writes landed and which did not (ch. 42, pp. 3 to 4 [569 to 570]). Some leftovers are harmless. Some leave the inode pointing at junk. Some leak space. The goal is to move the disk from one consistent state to the next as one indivisible step (p. 5 [571]). The first fix was a checker, `fsck`, that scans the whole disk after a crash and repairs what disagrees. It works, but its cost grows with the size of the disk, not with the size of the failed update (pp. 5 to 7 [571 to 573]). The fix that won is journaling, also called write-ahead logging: write a description of the update to a log first, mark it committed, and only then write the real locations. After a crash, replay the committed log entries and skip the rest (pp. 7 to 11 [573 to 577]). Refinements follow. A checksum in the commit record lets the log be written in one go (p. 10 [576]). Many updates are grouped into one commit to save work (pp. 11 to 12 [577 to 578]). The log is circular and is freed after checkpointing (pp. 12 to 13 [578 to 579]). Ordered (metadata-only) journaling skips logging the data itself, but must write the data block before the metadata that points to it. The chapter names that ordering rule as the core of crash consistency (pp. 13 to 15 [579 to 581]). Deleting and then reusing a block is the hard case; ext3 adds revoke records so replay does not overwrite a reused block (pp. 15 to 16 [581 to 582]). Other approaches close the chapter: soft updates (careful ordering of every write), copy-on-write (never overwrite; flip a root pointer at the end), back-pointer consistency (check on read that the pointed-to block points back) and optimistic crash consistency (pp. 17 to 18 [583 to 584]).

**Chapter 45, data integrity.** Disks do not only fail whole. They also fail one block at a time (ch. 45, pp. 1 to 3 [628 to 630]). A latent sector error is a block the disk cannot read; the disk says so, and redundancy recovers it (pp. 3 to 4 [630 to 631]). Corruption is worse, because it is silent: the disk returns wrong bytes and reports success. In the study the chapter cites, roughly one cheap drive in ten saw an unreadable sector over about three years, and silent corruption was about ten times rarer (p. 2 [629]). The tool for silent corruption is the checksum: a small summary computed when data is written, stored, and compared when the data is read back (pp. 4 to 8 [631 to 635]). Checksum functions trade strength for speed (XOR, addition, Fletcher, CRC; pp. 5 to 6 [632 to 633]). Where the checksum lives matters (pp. 6 to 7 [633 to 634]). A checksum that also records the block's address catches a misdirected write, meaning good data written to the wrong place (pp. 8 to 9 [635 to 636]). A checksum kept in the parent, as ZFS keeps one in the inode, catches a lost write, meaning a write the device acknowledged but never stored (p. 9 [636]). Data that is never read is never checked, so systems scrub: they read everything on a schedule and verify it (pp. 9 to 10 [636 to 637]). The space cost of checksums is tiny. The time cost is real: CPU to compute the checksum on every write and read, plus the I/O of scrubbing. Fusing the checksum with a copy that happens anyway hides most of the CPU cost (p. 10 [637]).

**Chapter 46, summary dialogue.** Keeping data for a long time is much harder than keeping it in memory. Every update must be planned around what a crash would leave behind, so recovery becomes a first-class design concern (ch. 46, p. 1 [642]). The ideas outlive the hardware they were built for. Flash translation layers still log-structure their writes (p. 2 [643]).

---

## 2. Principles vfs should adopt

Each item gives the principle, the source, where vfs stands, and the one change it implies.

### 2.1 Name the unit of atomicity, and say it at the seam

- **Principle.** Every operation should take the store from one consistent state to the next as one indivisible step, and the system must know what that step covers. (ch. 42, p. 5 [571]; READ)
- **Where vfs stands: half follows.**
  - The behavior is right. Every mutation runs as one engine transaction and commits only if the result has no fatal error. The code: `_mutate` in `src/vfs/storage/backends/database/backend.py` (lines 1718 to 1747), with `_execute_write` and `_execute_topology` on top. A 10,000-entry write batch is one transaction. Its plan is staged first, and a plan with any error runs no mutation at all (`writes.py` module docstring). READ.
  - EXECUTED: a fault was injected at each of the 10 mutating statements of a three-file write batch. All 10 runs left the store exactly as it was before the call. Zero runs left it torn (appendix, experiment A).
  - The seam does not say any of this. `protocol.py` says only that transactions are internal to the backend (module docstring). Its traits name `durability` (`full` or `relaxed`) but no atomicity scope (`TraitKey` and `TRAIT_KEYS`, lines 73 to 76). The one batch rule the seam does state is about reads: a missing target gets a per-target error beside the good rows, never all-or-nothing. A reader could easily assume writes behave the same way. They do not: writes are whole-batch. READ.
  - The cross-backend contract pins whole-batch atomicity for `edit` (`test_edit_batch_is_atomic_on_a_failed_match`), `move` (`test_move_batch_is_staged_atomic`) and `delete` (`test_failed_batch_leaves_revisions_untouched`), all in `tests/support/storage_contract.py`. It does not pin it for `write`. Only the SQLite-specific `tests/storage/database/test_writes.py::test_failed_batch_commits_nothing` pins it there, and that test counts entry and content rows only, not versions, edges or segments. READ.
- **Change.** Write the atomicity scope into `SupportsMutation`'s docstring: one call, one batch, all of it or none of it, reads aside. Then add a mixed good-and-bad `write` batch to `StorageContract` that checks every table the write touches.

### 2.2 Know exactly what is inside the step, and record lag atomically

- **Principle.** A crash-consistent update must cover every structure that refers to the new data. Anything left outside must be safe to find stale. (ch. 42, pp. 3 to 5 [569 to 571]; READ)
- **Where vfs stands: follows, but the kernel memo misdescribes it.**
  - EXECUTED (experiment A, the statement trace). One write batch touches these tables, in this order, inside one transaction:
    1. `vfs_entries`: create inserts, layered parents first.
    2. `vfs_segments`: the path-segment postings for fresh creates.
    3. `vfs_edges`: the fs mirror edge for fresh creates.
    4. `vfs_entries`: the guarded material update for overwrites.
    5. `vfs_versions`: the replaced body kept as a version.
    6. `vfs_content` and `vfs_blobs`: the bodies, delete then insert.
    7. `vfs_entries`: the parent version bumps.
  - Outside the step, rebuilt later by `reindex` in transactions of their own: chunk rows, gram postings, the BM25 lexical tables, embeddings, renderings, signals and extracted link edges (`indexing.py` module docstring; `_reindex_phases` in `backend.py`). ADR 051 accepts this lag and serves the stale index between a write and the next reindex. READ.
  - What makes the lag safe is that the write resets the dirty flags (`chunked`, `encoded`) in the same transaction. The invariant is that `encoded = True` implies the entry's grams are in the current epoch, and grep always scans the `NOT encoded` side (`indexing.py`, `grep.py` docstrings). READ.
  - The 2026-10-23 kernel memo (§0 and §4.3) says the query indexes are written in the same transaction as the body. At HEAD, that is true only of the path segments and the fs edge mirror. The trigram, lexical and vector indexes are not written there. What the write transaction carries is the *flag* that says those indexes no longer cover the row. READ, with the trace EXECUTED.
- **Change.** When the kernel ADR is written, state the rule this way: the body and its dirty flag commit together, and the derived indexes catch up later. Do not say the indexes commit with the body.

### 2.3 Write the pointed-to thing before the pointer, wherever more than one commit is involved

- **Principle.** Never let a committed pointer name something that is not yet durable. Write the target first and the pointer last. This rule underlies ordered journaling, soft updates and copy-on-write alike. (ch. 42, p. 14 [580] and p. 17 [583]; READ)
- **Where vfs stands: follows, in the place where it matters.**
  - *Inside one transaction*, order cannot cause a crash inconsistency, because the engine commits all of it or none of it. vfs in fact writes the pointer first. The entry row (with its new `content_hash`) is updated before the body is replaced. That way the version mint can read the old body under the same row lock (`versions.py` docstring; `_apply` in `writes.py`). This is correct. Under a transaction, order serves locking, not crash safety. READ, then INFERRED.
  - *Across transactions*, vfs keeps the rule every time:
    - The gram index is built under a fresh epoch that nobody can see. Publishing flips `vfs_meta.current_gram_epoch` and the `encoded` flags together, with a compare-and-set (`indexing.py`). This is the book's copy-on-write root flip.
    - A crashed build leaves only unpublished rows. Nothing points at them, and a later reindex reclaims them (`test_a_crashed_build_never_poisons_the_number_line`, `tests/storage/database/test_indexing.py`).
    - A posture change commits its intent mark (`vfs_relabels`) in the same transaction as the posture row. Readers honor the mark before the labels catch up (`labels.py` docstring).
    - READ throughout.
- **Change.** None today. Carry the rule into the kernel ADR for any future verb that spans commits. The memo's §4.5 names chunked blobs as a possible future. A chunked blob must have its chunks written before the entry row points at them, or else be written in one transaction.

### 2.4 Treat an index as a hint and verify against the data

- **Principle.** A pointer you cannot trust should be checked when you follow it. Back-pointer consistency does this: on access, confirm the target agrees with the pointer, and report an error if it does not. (ch. 42, p. 18 [584]; READ)
- **Where vfs stands: follows.**
  - Grep's postings only *nominate* candidates. Every candidate is then verified against the stored body by the shared matcher, and the unindexed side is always scanned (`grep.py` docstring). READ.
  - EXECUTED (experiment B). A body was changed underneath vfs from "needle in a haystack" to "neeXle in a haystacK". The stale postings still nominated the file, verification dropped it, and grep returned no false hit.
- **Change.** None for grep. See 2.8: the same discipline is missing for `read` itself.

### 2.5 Recover in proportion to the work in flight, not the size of the store

- **Principle.** A whole-store checker costs time in proportion to the store. A log costs time in proportion to the work that was in flight. Prefer the log for recovery, and keep the checker for rare maintenance. (ch. 42, pp. 6 to 7 [572 to 573] and p. 18 [584]; READ)
- **Where vfs stands: half follows.**
  - Recovery is proportional to the work in flight:
    - Engine recovery is the engine's log. INFERRED.
    - A crashed reindex frees its lease by heartbeat timeout and leaves nothing to clean (`indexing.py`; `test_an_expired_lease_is_claimed_through_and_released`).
    - A dead relabel leaves a mark and a cursor, and a fresh driver resumes from the cursor (`test_a_dead_relabel_resumes_and_reads_stay_exact_meanwhile`, `tests/storage/database/test_labels.py`).
    - `vfs_relabels` is a small redo journal: an intent record (`path_prefix`, `revision`) and a progress cursor, with the last chunk freeing the record (`rows.py`, `labels.py`).
    - READ throughout.
  - vfs also has two checkers shaped like `fsck`, both inside `reindex`. `collect_edge_drift` streams every entry and every edge to rebuild the fs mirror from `parent_id`. The segment pass does the same for path segments (`edges.py`; `_reindex_phases` in `backend.py`). Correctness never depends on them, because the write keeps the mirror in its own transaction (2.2). They surface drift as warnings. Their cost grows with the corpus. READ, then INFERRED.
  - The redo journal has one gap: who replays it. A stranded relabel mark is finished only by the next `posture` call (the `labels.py` docstring and `_settled` in `backend.py`). Until then, every reader compiles the in-flight mark into its predicate. Rights stay correct throughout, but reads pay for the mark. INFERRED.
- **Change.** Give the redo journal a standing recovery point. For example, `reindex` (or first touch) could drain any stranded relabel mark. Then finishing the work does not depend on an admin happening to call `posture` again.

### 2.6 Never reuse an identity that an old record might still name

- **Principle.** Delete followed by reuse is the hardest case for crash recovery. Replay can write stale contents over the new owner of a reused block. Either never reuse until the old record is gone, or log a revoke record. (ch. 42, pp. 15 to 16 [581 to 582]; READ)
- **Where vfs stands: follows, by construction.**
  - Entry identity is a ULID that never returns. The edge-drift collector relies on exactly this fact (`edges.py`, `collect_edge_drift` docstring; ADR 019). Bodies, versions, chunks and edges all key on `entry_id`, never on path (`rows.py` docstring).
  - A crashed build's epoch number is skipped, never reused (`test_a_crashed_build_never_poisons_the_number_line`).
  - Delete never destroys (ADR 027). It sets a tombstone on the row (ADR 074), so the classic delete-then-reuse sequence cannot arise.
  - READ throughout.
- **Change.** None. Name it as a kernel rule: identities are never reused, and only `sweep` destroys.

### 2.7 Batch commits for throughput, but know what the log must hold

- **Principle.** Grouping many updates into one commit saves work, but the log is finite. A full log stops the system, and a long log slows recovery. (ch. 42, pp. 11 to 13 [577 to 579]; READ)
- **Where vfs stands: half follows. vfs has two atomicity models and has not named them.**
  - *Whole-batch*: `write`, `edit`, `mkdir`, `move`, `copy`, `delete`, `restore`. One transaction for the whole batch, however large it is. The number of statements is bounded by the dialect budgets (CLAUDE.md; `writes.py`). But the engine's own log (Postgres WAL, SQL Server transaction log, Oracle undo) must hold the whole batch until it commits. On SQLite the write lock is held from the plan's first read to the commit (`BEGIN IMMEDIATE`, `_execute_write` docstring). READ, then INFERRED for the engine logs.
  - *Resumable*: posture relabel and reindex. Each is one bounded chunk per transaction, with a durable mark or epoch to resume from. The stated reason is so that no single transaction holds a whole subtree's locks (`_settled` docstring in `backend.py`). READ.
- **Change.** Name both models at the seam, and give each mutating verb its model. Per CLAUDE.md, do not cap batch size. Instead, say in the docstring that a whole-batch call's log and lock footprint grows with its bytes. Name the resumable model as the direction if a real engine's log ever refuses a batch.

### 2.8 Store a checksum apart from the data, in the parent, and check it

- **Principle.** Silent corruption can only be caught by a checksum stored separately from the data. Keeping it in the parent (as ZFS keeps one in the inode) also catches a write that was lost. A checksum that is never compared protects nothing. (ch. 45, pp. 4 and 7 to 9 [631, 634 to 636]; READ)
- **Where vfs stands: half follows. It stores the checksum and never checks it on read.**
  - vfs already puts the checksum where ZFS does. `vfs_entries` carries `content_hash`, the sha256 of the body, on the entry row, which is the pointer. The body itself lives in `vfs_content` or `vfs_blobs`, keyed by `entry_id` (`rows.py`; `measure_text` and `measure_bytes` in `src/vfs/models/version.py`). READ.
  - Version rows carry their own `content_hash`. The mint measures it from the body it actually reads, never by copying the entry's column (`versions.py` docstring). READ.
  - `Version.reconstruct` does verify the hash after rebuilding a version (`version.py`, lines 191 to 220). It has no caller in `src/`; only `tests/models/test_models.py` calls it. READ (grep).
  - Nothing on the live read path compares a body with its hash. EXECUTED (experiment B):
    - A body rewritten underneath vfs is served by `read` as `success=True` with the wrong text. `stat` still reports the old hash, and the two disagree.
    - A body row deleted underneath vfs is served by `read` as `success=True` with `content=None`. The entry still says 11 bytes and still carries a hash. This is chapter 42's case of an inode pointing at nothing, served as success.
    - A full `reindex` afterwards reports nothing wrong.
- **Change.** Verify on read. Compare sha256 of the served body with `content_hash`, and classify a mismatch, or a missing body behind a hashed entry, as an error rather than a success. `unavailable` (EIO) is the nearest existing `ErrorKind`; whether integrity deserves a kind of its own is a decision for the ADR. Per ADR 057 the hashing belongs in the Rust engine, fused with the decode the read already does. That is the book's trick of folding the checksum into a copy that happens anyway (ch. 45, p. 10 [637]). INFERRED.

### 2.9 Check what is never read: a scrub, report-only and paced

- **Principle.** Rarely read data goes unchecked until it is needed, and by then every copy may be bad. A scheduled scrub reads everything and verifies it. Its I/O cost should be paced and placed off-peak. (ch. 45, pp. 9 to 10 [636 to 637]; READ)
- **Where vfs stands: does not follow.**
  - There is no scrub verb. The op vocabulary (`src/vfs/ops.py`) has none, and `reindex` does not hash bodies. READ.
  - Version history is exactly the cold data the book warns about. Agents rarely read old versions, and no live verb reads them at all. READ, then INFERRED.
- **Change.** Add a scrub as a maintenance verb, or as a `reindex` phase:
  - Stream `vfs_content`, `vfs_blobs` and `vfs_versions` one blob page at a time (`BLOB_PAGE_BYTES`). Recompute sha256 in the Rust engine. Compare against `content_hash`. Also flag hashed entries with no body row.
  - Report mismatches as warnings, the way the drift passes do. Never repair: vfs has no second copy to repair from, and the book says detection without redundancy can only report (ch. 45, p. 8 [635]).
  - Cost: O(total stored bytes) of reads across the wire, plus CPU. It has the same shape as `fsck`. That is acceptable for a scheduled job, but not acceptable as recovery. INFERRED.

### 2.10 Write down the fault model: which layer catches which fault

- **Principle.** Devices fail partially: a block can be unreadable, or silently wrong, or written to the wrong place, or lost. Each kind of fault needs its own detector, and a reliable system says which detector covers which fault. (ch. 45, pp. 1 to 3 and 8 to 9 [628 to 630, 635 to 636]; READ)
- **Where vfs stands: does not follow (no stated model).**
  - The engines guard their own pages against media faults. General knowledge, not verified here: SQL Server verifies page checksums by default, Oracle has block checksums, Postgres data checksums are an `initdb` option, and SQLite has no page checksum by default. INFERRED.
  - vfs's SQLite profile does choose the book's journaling mode directly. It sets `journal_mode = WAL` and `synchronous = FULL` (`dialects.py`, lines 399 and 407). Tuned profiles declare `durability: full` (`backend.py`, line 298). READ.
  - Engine checksums cannot see faults that happen *above* the engine. Each of the book's device faults has an analog at that layer:
    - a vfs bug writes body A under `entry_id` B (the misdirected write);
    - a vfs bug drops a body insert (the lost write);
    - an ETL job or a migration writes the tables directly with SQL credentials. Only vfs's own `content_hash` can detect these. The `entry_id` key is the physical-ID field the book adds to a checksum. INFERRED.
  - The durability claim rests on the engine's fsync being honest (ch. 42, p. 9 [575]). vfs cannot check that, and should say so. INFERRED.
- **Change.** State the fault model in the kernel ADR. The engine owns media faults and atomic commit. vfs owns logical faults, and `content_hash` is its detector (2.8, 2.9).

### 2.11 Enumerate the crash points, and test each one

- **Principle.** Reason about crash safety by listing every point where a crash can land and saying what the store looks like after each. Do not reason about the happy path alone. (ch. 42, pp. 3 to 5 [569 to 571], and the timelines on pp. 16 to 17 [582 to 583]; READ)
- **Where vfs stands: half follows.**
  - The conformance battery is `StorageContract` in `tests/support/storage_contract.py` (2,784 lines). It is instantiated per backend in `tests/storage/test_conformance.py`. It has no crash-at-each-point family. Its atomicity tests use *logical* failures (a missing source, a failed edit match). Those fail at planning time, before any mutation statement runs, so they never exercise a rollback after mutations have run. READ.
  - vfs does have the right tool. `seams.py` declares named injection points modeled on Postgres `INJECTION_POINT` and SQLite's fault simulator. There are 21 seams in `src/`. Tests install handlers on 17 of them, mostly to commit a rival writer mid-window (concurrency). `relabel:after-chunk`, `reindex:before-render`, `grants:before-lock` and `grants:before-write` have no test handler. READ (grep).
  - Crash scenarios are tested one at a time, outside the contract:
    - a crashed build (`test_indexing.py`);
    - an expired lease (`test_indexing.py`);
    - a lost publish (`test_indexing.py`);
    - a relabel that dies after its first chunk (`test_labels.py`). These are the right cases. Each covers one crash point by hand, on SQLite only. READ.
  - EXECUTED (experiment A). A statement-level fault at each of a write's 10 mutation points is cheap to run. It confirmed the whole-batch promise on SQLite.
- **Change.** Add a crash-point family to the contract, so it runs on every engine leg:
  - *Single-transaction verbs.* Use a `before_cursor_execute` hook that fails the Nth mutating statement, for every N. Then reopen and assert the store equals the before-image, across all tables. Count statements, never time.
  - *Multi-transaction verbs* (reindex, relabel, the render and embed landings). For every seam the verb passes, install a handler that raises. Assert the store is in an allowed state: readers stay exact, and nothing points at unpublished rows. Then assert that the next call converges.

---

## 3. Nouns and verbs

| Book term | What it means in the book | vfs's name today | Adopt the name, the concept, or neither | Why |
|---|---|---|---|---|
| crash-consistency problem | a multi-write update torn by a crash (ch. 42, p. 5) | none (solved by the engine) | concept only | vfs inherits the solution; it should still name the scope (2.1) |
| atomic update / transaction | all-or-nothing state change | "one batch = one writer transaction" (`_execute_write`) | concept, own name ("batch") | "batch" is already the user-facing word for the ETL contract |
| journal / write-ahead log | redo log written before the real locations (pp. 7 to 11) | the engine's WAL; SQLite `journal_mode = WAL` | neither | engine-owned; vfs must not build a second log for row writes |
| TxB / TxE, commit block | begin and end markers of a logged transaction (pp. 8 to 11) | the engine's `BEGIN` / `COMMIT` | neither | engine-owned |
| checkpoint | copy committed log contents to their final places (p. 8) | none at row level; the gram **publish** is the nearest | concept, own name ("publish") | the epoch flip is vfs's checkpoint for derived state |
| free (journal superblock) | reclaim log space after checkpoint (p. 13) | **reclaim** (dead epochs), last relabel chunk clears the mark | concept, own name | already named in `indexing.py` and `labels.py` |
| redo logging / replay | redo committed entries after a crash (p. 11) | `vfs_relabels` mark + cursor; Relabeller resumes | concept, own name ("mark", "resume") | small, durable intent records for multi-commit verbs (2.5) |
| revoke record | stop replay from writing over a reused block (p. 16) | none needed | deliberately not | identities never return (ULID, epoch skip), so there is nothing to revoke (2.6) |
| data vs ordered (metadata) journaling | log data too, or only metadata with data written first (pp. 13 to 15) | none | neither | the engine logs whole rows; bodies cannot tear |
| fsck / checker | whole-store scan that repairs inconsistencies (pp. 5 to 7) | edge and segment **drift** passes inside `reindex` | concept, own name ("drift") | maintenance, never recovery; cost grows with the corpus (2.5) |
| lost+found | where orphaned inodes go | none | deliberately not | an orphan body has no owner to show; report it as drift instead |
| soft updates | ordered writes so disk is always consistent (p. 17) | none | neither | needs no transaction; vfs has one |
| copy-on-write, root flip | write new copies, flip one root pointer (p. 17) | gram **epoch** + `current_gram_epoch` CAS | concept, own name ("epoch", "publish") | already the reindex design (ADR 033) |
| back-pointer consistency | check on access that the target points back (p. 18) | grep **verify**; `chunk_source_hash`, `render_source_hash`, `link_source_hash` stamps | concept, own name ("verify", "stamp") | index nominates, body decides (2.4) |
| write barrier / flush | force ordering to stable storage (p. 9) | engine commit; `synchronous = FULL` | neither | engine-owned; vfs states the `durability` trait |
| checksum | small summary to detect corruption (ch. 45, p. 4) | `content_hash` (sha256) on entries, versions, chunks | adopt the concept; keep the name `content_hash` | already stored; needs checking (2.8) |
| stored vs computed checksum | compare on read (p. 7) | none on the read path | adopt the concept | the missing half of 2.8 |
| physical ID | address recorded with the checksum (p. 8) | `entry_id` primary key on the body row | concept, already present | body row keyed by identity; a hash mismatch catches a body under the wrong id |
| misdirected write | right data, wrong place (p. 8) | none | adopt the concept in the fault model | a vfs bug can do it above the engine (2.10) |
| lost write | acknowledged, never stored (p. 9) | none; seen as "entry with hash, no body" | adopt the concept in the fault model | experiment B shows it is served as success today |
| latent sector error | unreadable block (p. 3) | engine error, classified `unavailable` | neither | engine-owned; vfs already classifies driver failures (`classify_failure`) |
| scrub | scheduled read-and-verify of everything (pp. 9 to 10) | none | adopt the name `scrub` | standard word; report-only, paced, maintenance-plane (2.9) |
| fail-stop vs fail-partial | whole-device vs per-block failure (p. 2) | none | concept, in the fault model | vfs must assume fail-partial above the engine too |

---

## 4. What does not transfer

1. **The disk writes one block at a time. The engine does not.** The whole of chapter 42 exists because a disk commits one write at a time. An engine transaction commits many rows as one. So for any single vfs call, statement order inside the transaction is not a crash-safety question. vfs writes the pointer (entry row) before the data (body) on purpose, and that is fine (2.3). READ, then INFERRED.
2. **There is no mount-time recovery for vfs to run.** The engine replays its own log before vfs connects. vfs's own first touch checks the schema version, not consistency. The only vfs-level recovery is resuming its own multi-commit verbs, and those resume lazily, on the next call. INFERRED.
3. **Data vs metadata journaling is not a choice vfs gets.** The engine logs whole rows, bodies included. So vfs pays for writing every body byte twice (once to the log, once to the table), which the book counts as the price of data journaling (ch. 42, p. 13 [579]). vfs gets the matching benefit: a body is never torn. For a 10,000-file ETL batch of large bodies, that doubled write is the engine's cost, and vfs cannot opt out of it. INFERRED.
4. **Checksum layout and sector size do not apply.** There are no 520-byte sectors and no checksum blocks to pack. A hash is just a column. Its only placement choice is which row carries it, and vfs already chose the parent row (2.8). INFERRED.
5. **The book's checksums are cheap and short. vfs's is a cryptographic hash.** sha256 is much slower per byte than CRC or Fletcher. But it already does three other jobs: twin lookups by index, the fingerprint-skip stamps, and the version mint's identical-body check. A second, cheaper checksum would duplicate the body-measurement law in `measure_text`. Keep one hash and pay for it in Rust. INFERRED.
6. **Redundancy for repair is not vfs's.** RAID mirrors and parity let the book's systems repair a bad block. vfs has no second copy of a current body. Engine replicas are the engine's business. An older version row is a different body, not a copy. So vfs's integrity work is detection and reporting only. INFERRED.
7. **Block reuse does not happen.** Row identities are minted fresh and never return. Surrogate keys are autoincrement. Deletes are tombstones. The revoke-record machinery has nothing to protect against (2.6). READ.
8. **The crash model gains a new actor: the out-of-band writer.** A disk has one writer, the file system. A SQL database shared with ETL pipelines has many: other clients of shared storage (which `base.py` already names in `_shadow_filter`), migrations, and people with credentials. That fault does not exist in the book. For vfs it is more likely than bit rot, and only an end-to-end hash check catches it. INFERRED.

---

## 5. The one design lesson

The engine makes every vfs call atomic. But vfs has never said how far that atomicity reaches, and the answer is narrower than the kernel memo assumes: the body, its row, its version, its path segments and its edge mirror, plus a dirty flag in place of the search indexes. Where vfs spans more than one commit, it already follows the book's rules (write the target before the pointer, and keep a small redo mark instead of running a whole-store check). Where it fails the book is integrity: it stores the right checksum in the right place, the parent row, and then never compares it, so a rotten or missing body reads as success.

---

## Appendix: the two experiments (EXECUTED)

Both ran with `uv run python` against a fresh SQLite file per run, through `DatabaseStorage` at HEAD `ac5c515`.

**Experiment A: crash at each statement of one write batch.**

- *Seed.* `/d/a.txt` with body "old a".
- *Batch.* One `write(parents=True)` of three entries: overwrite `/d/a.txt`, create `/d/b.txt`, create `/e/c.txt` (this also mints `/e`).
- *Fault.* A `before_cursor_execute` hook on the sync engine counted the INSERT, UPDATE and DELETE statements and raised a driver-style `sqlite3.OperationalError` at statement N, once, for N = 1 to 10.
- *Reboot.* After each run the storage was closed and the file was reopened by a fresh `DatabaseStorage`.
- *Check.* Row counts of entries, content, versions, edges and segments, plus every entry's (path, version, content_hash) and every body, compared with the before-image and with a fault-free reference run.
- *Result.* 10 mutating statements, in the order listed in 2.2. All 10 crash points left the store equal to the before-image. None was torn.
- *Caveat.* The injected exception is not a SQLAlchemy `DBAPIError`. So it escaped `write` raw instead of being classified. That is an artifact of the hook, not a vfs defect: real driver failures arrive wrapped and are classified by `classify_failure`.

**Experiment B: silent rot and a lost body.**

- *Setup.* Wrote `/a.txt` ("needle in a haystack") and `/b.txt` ("second file"), then ran `reindex`. Then, with a direct SQL connection, rewrote `/a.txt`'s `vfs_content` row to "neeXle in a haystacK" and deleted `/b.txt`'s `vfs_content` row.
- *Result for `/a.txt`.* `read` returned `success=True` with the rotten text. sha256 of the served body did not equal `stat`'s `content_hash`. `grep needle` returned no rows and no errors: the postings nominated the file, and verification dropped it.
- *Result for `/b.txt`.* `read` returned `success=True`, `content=None`, `size_bytes=11`, with `content_hash` still set and no errors.
- *Result for `reindex`.* It succeeded with no warnings.
