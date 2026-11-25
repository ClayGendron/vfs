# The trash retention pass reclaims in short slices, one transaction each

A draft, written on 2026-11-25 and checked against `dev` at `27f3d24d`. It is not reviewed, and nothing is built. It is unit 180-4 of [the backlog's conversion](../2026-11-25-the-backlog-converted/units.md), at gate 0.2: the roadmap lists "`pack`, the bounded `sweep`, the garbage gauge (spec 180's rest)" among what is deliberately left out of 0.1.0 (`context/standards/roadmap.md:1181`), and no story names it. It is converted from [numbered spec 180](../../context/specifications/archive/180-history-pack-on-reindex-and-the-bounded-sweep/spec.md), sections 5.1 to 5.3 and 5.5, read through [the study of that source](../2026-11-25-the-backlog-converted/studies/165-181/180-history-pack-on-reindex-and-the-bounded-sweep.md) and [the reassessment against dev](../2026-11-25-the-backlog-converted/reassessment/history-and-surface.md), and it replaces the draft of this directory written against `main` at `0ed462f`. It rests on the deletes spec, reviewed fit to build on the branch `a-deleted-row-gives-up-its-path` and not built, which renames the verb `destroy` and gives it the two arms this spec works within, and it is built after that spec's third landing.

## The outcome wanted

A deployment job, the system actor or a developer calls `destroy("/.vfs/trash")` and gets the end state the retention pass gives today: every deleted root older than `trash_days` is gone with its set, and every body and version row whose entry is gone, older than a day, is reclaimed with a warning. What changes is the shape of the work. The pass is a loop of short transactions, each of at most one membership budget of roots or keys. A delete, restore, move, copy or destroy on the same mount waits for one slice at most, where today it waits for the whole pass. No statement of the pass reads a whole table. A pass stopped by a refusal, a failure or a cancellation keeps every slice it committed and says so in its answer, and the next call continues from what remains. Version rows whose file is gone, which nothing reclaims today, leave with the other orphans.

## Builds on

- **The deletes spec**, `origin/a-deleted-row-gives-up-its-path:agents/2026-11-24-a-deleted-row-gives-up-its-path/spec.md`: reviewed fit to build on 2026-11-24, not built. Relied on, by decision number. Decision 11: "`destroy` takes `sweep`'s place on the four faces, in `Op`, in `VERB_RUNGS`, in `DEVELOPER_OPS` and on the seam, with its default path `/.vfs/trash`. `sweep` is removed in the same landing." Decision 12: "At the trash view's head, `/.vfs/trash`, it is the retention pass, as today"; "At a trash path beneath the head, `/.vfs/trash/<path>`, it removes the newest deleted root at that path, with its set"; "Any other path is `invalid`"; "Each row a `destroy` returns has status `destroyed`" and "carries its trash path and its `deleted_at`"; "No parent is bumped." Decision 13: "Each row of a set is judged, and one row that fails refuses the call whole. The retention pass is judged the same way, row by row." Decision 2 keeps `ix_vfs_entries_deleted_at`, the index of deleted rows by `deleted_at`, and adds two indexes of its own. Its "Left as it is" leaves "The bounded retention of numbered spec 180, `destroy(limit=, after=)` once renamed" to this unit and the next. Its decision 16 lands `destroy` third, after the key and the free name.
- **The kernel rulings**, [decision 3](../../context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md), built as a ruling: the verb is named `destroy`. Roadmap rows D56 and D57 (`context/standards/roadmap.md:1267-1268`) are the rulings on the name and on who may call it. No verification of D56 or D57 exists under the conversion's `decisions/` directory; both rows read "Decided" in the roadmap, which is the record cited.
- **Who calls the pass**, `origin/a-deleted-row-gives-up-its-path:agents/2026-11-24-the-trash-is-emptied-without-being-asked/spec.md`: a draft, not reviewed. Its choice 1 (the daily rebuild, a job, or the deployment's owner) is open, and this spec serves each answer, because the pass is the same loop whoever calls it. Its choice 2 (the whole backlog, or a bounded slice with a cursor) is decided here for the transaction and left to unit 180-5 for the call. Its choice 3 (whether the orphan scan rides the pass) is choice 4 below.
- **The kernel store's own pass**, `origin/the-kernel-writes-records-behind-and-sweeps-them`, whose reviews stand at lands and which is not on `dev`. Relied on: decision 17 of `agents/2026-11-22-the-kernel-keeps-records-of-its-own/spec.md` on that branch, "The pass runs only when the storage's retention succeeded", and its code, which runs `self._kernel_store.sweep()` after the root's retention only when `result.success` (`src/vfs/base.py:1198-1232` on that branch), in transactions of `SWEEP_CHUNK` = 5,000 rows each (`src/vfs/kernel_store/sweep.py:41` on that branch). That pass is the precedent for a reclaim cut into commits of its own.
- **The topology-lock draft**, [`agents/2026-11-21-the-topology-lock-is-held-for-a-commit/spec.md`](../2026-11-21-the-topology-lock-is-held-for-a-commit/spec.md), on `dev`, not reviewed and not built. Its decision 1: "The lock row is taken as the verb's last statement before its commit, and the verb's reads before it are checked again under the lock." Decision 4 says how the two land in either order.
- **The relabel's chunk loop**, built: `DatabaseStorage._settled` runs one writer transaction per chunk, stops at the first chunk that fails, and awaits the seam `relabel:after-chunk` between chunks (`src/vfs/storage/backends/database/backend.py:1317-1345`). The pass follows its shape.
- Built on by unit 180-5, `../2026-11-25-a-retention-pass-resumes-from-where-the-last-call-stopped/spec.md`, which adds `limit=` and `after=` and serialises this spec's mark, and unit 180-6, `../2026-11-25-a-gauge-reports-how-much-garbage-a-mount-holds/spec.md`. Neither is written.

Build order: the deletes spec's three landings, then this unit, then units 180-5 and 180-6. The topology-lock draft may land before or after this unit.

## Terms

- **Retention pass.** One call of `destroy` at the trash view's head, from its first slice to its last.
- **Slice.** One bounded piece of a pass, in a writer transaction of its own that takes the serialization point and commits before the next slice begins.
- **Budget, B.** `membership_budget(profile, parameter_budget)` read from the engine host (`src/vfs/storage/backends/database/engine.py:255-257`): the keys one `IN` list may carry. It is 32,668 on SQLite and on Postgres, and 1,000 on the generic floor (EXECUTED, `membership_budget` over each profile and SQLAlchemy's `insertmanyvalues_max_parameters` of 32,700).
- **Phase.** One kind of work a pass does, run as slices until it has no more: `roots`, `content`, `blobs`, `versions`.
- **Root, set.** A root is a deleted row a delete named; its `trash_root_id` is its own `entry_id` (`src/vfs/storage/backends/database/descent.py:215-217`). Its set is every row sharing that `trash_root_id`.
- **Orphan.** A row of `vfs_content`, `vfs_blobs` or `vfs_versions` whose `entry_id` names no row of `vfs_entries`, live or deleted.
- **Window.** The next keys of one table after a position, in key order, at most B of them.
- **Fence.** The age an orphan must reach before it is reclaimed: `_ORPHAN_AGE_FENCE`, 24 hours (`src/vfs/storage/backends/database/trash.py:112`).
- **Mark.** Where a pass stands: its phase and, in an orphan phase, the last `entry_id` a window examined. It lives in memory for one call.

## What the code does today

At `27f3d24d`. A file named without a directory is under `src/vfs/storage/backends/database/`. EXECUTED means a scratch script ran on 2026-11-25 against a file-backed SQLite storage of 300 files, 200 of them deleted and 50 overwritten once; it counted statements with the engine's `before_cursor_execute` event and read plans with `EXPLAIN QUERY PLAN`, and timed nothing.

1. **One pass is one transaction.** READ, `trash.py:346-404`: `sweep_rows` takes the serialization point (`:377`), runs the gate, selects the expired roots (`:388-394`), purges them by chunk (`:397-400`), bumps their parents (`:401`), runs the orphan reclaim (`:403`) and returns one `Result`. READ, `backend.py:879-910` and `:1454-1463`: `DatabaseStorage.sweep` runs it through `_execute_topology`, one fenced session under `_mutate`, committed once. EXECUTED: the pass over 200 roots opened one `BEGIN IMMEDIATE` and issued 16 statements besides the statistics step: the lock read, the roots select, two purge collections, nine deletes, one parent bump and two anti-joins.
2. **The roots select has no limit and sorts every expired root.** READ, `trash.py:389-394`: `WHERE deleted_at < :cutoff AND trash_root_id = entry_id ORDER BY path`, read whole with `.mappings().all()`. EXECUTED: `SEARCH vfs_entries USING INDEX ix_vfs_entries_deleted_at (deleted_at<?)` then `USE TEMP B-TREE FOR ORDER BY`, a seek of every expired root and an in-memory sort of all of them. The index is partial on the deleted side (`src/vfs/models/rows.py:441`).
3. **The orphan reclaim reads two whole tables.** READ, `trash.py:617-657`: for `vfs_content` and then `vfs_blobs`, one `SELECT entry_id ... WHERE NOT EXISTS (an entry with that id) AND created_at < :fence`, sorted in memory, then deleted by chunk. EXECUTED: the plan is `SCAN b` with a correlated seek of `ix_vfs_entries_entry_id` for each row. Its docstring says the scan runs "end to end, inside the serialized transaction" and is "the sweep's dominant cost" on many millions of bodies (`trash.py:630-637`).
4. **Version rows are never reclaimed as orphans.** READ, `trash.py:642`: the loop is `for body in (tables.content, tables.blobs)`. `vfs_versions` and `vfs_version_subjects` leave only with a purged entry (`trash.py:606-608`).
5. **The serialization point is held from the first statement to the commit.** READ, `serialized.py:112-122`: one locking read of the mount's single lock row, "held to the end of the transaction"; rival serialized verbs queue on it and nothing else reads it. On SQLite the writer transaction is the lock (`serialized.py:119-121`). The serialized verbs are delete, restore, sweep, move and copy (`serialized.py:1`).
6. **Statements are chunked; the transaction is not.** READ, `trash.py:397-400` and `:551-614`: the purge runs per `membership_budget` chunk of roots and deletes each family per chunk of collected rows, re-proving `deleted_at IS NOT NULL` in the entry delete and raising `StaleSnapshot` on a short count (`:599-603`). Each collected round is judged against the caller's rights before any of it is deleted (`:588`, and `admit` at `authorized.py:271-276`).
7. **The keys the windows need exist.** READ, `rows.py:460`, `:473`, `:490-491`, `:516-518`: `entry_id` is the primary key of `vfs_content` and `vfs_blobs` and the leading column of the keys of `vfs_versions` and `vfs_version_subjects`. `vfs_entries.entry_id` has a unique index (`rows.py:371`). EXECUTED: `entry_id > ? ORDER BY entry_id LIMIT ?` on each of the three families is `SEARCH ... USING COVERING INDEX sqlite_autoindex_<table>_1 (entry_id>?)`, `DISTINCT` included for `vfs_versions`, and `entry_id IN (...)` on `vfs_entries` is `SEARCH ... USING COVERING INDEX ix_vfs_entries_entry_id (entry_id=?)`.
8. **Every body and version row records when it was written.** READ, `writes.py:1149`, `:1151`, `:1354` and `versions.py:187`. `vfs_version_subjects` has no `created_at` (`rows.py:514-521`).
9. **`backend.py` is at its size limit.** READ, `tests/lint/allowlist.py:28`: `MODULE_LINE_BASELINE` holds it at 1,509 lines, its count; a module on that list that grows fails the lint. `trash.py` is 668 lines, under the ceiling of 1,000 (`tests/lint/test_code_shape.py:76`).

## The problem

At the reference deployment of `AGENTS.md` a mount holds 10,000,000 files. Fact 3 reads about 10,000,000 body rows and seeks `vfs_entries` once for each, and fact 2 sorts every expired root in memory, inside one transaction that holds the point every delete, restore, move, copy and destroy on the mount needs. `AGENTS.md` rules that a lock other callers need is never held for a batch's body, and that a whole-table operation is affordable only once a day, bounded in memory and interruptible. Today's pass is none of these: its hold grows with the corpus, its memory grows with the backlog, and a failure at its end rolls back all of its work. On SQLite, fact 5 makes that hold a stall of every writer on the file. And fact 4 leaves an orphaned version row forever, a body no verb can reach, which grows with the history the roadmap keeps whole.

## Decisions

### 1. The arm sliced is `destroy` at the trash view's head, and this spec adds no public name

The deletes spec's retention arm, `destroy("/.vfs/trash")`, runs as a pass of slices. Its other arm, `destroy("/.vfs/trash/<path>")`, removes one deleted set and stays one transaction, as the deletes spec builds it. No argument, field, error kind, op or trait is added. Every name this spec adds is private, and says `retention`, never `sweep` or `destroy`.

Reason: ruled, D56 and the kernel rulings' decision 3, and the deletes spec's decisions 11 and 12. The single-set arm destroys what one delete marked, and that delete was one transaction of the same size. The source's open question, whether a live-path purge arm is sliced, has no arm left to ask about: decision 12 of the deletes spec removes it.

### 2. Each slice judges its rows as the deletes spec judges a pass, inside its own transaction, and commits under the fence

Each slice runs the verb's gate after its serialization point and judges every row of its roots' sets by the deletes spec's decision 13 before it deletes any of them. Each slice commits through `fenced` (`authorized.py:218-236`), which proves the caller's rights and the postures again before the commit. Who may call is unchanged: by D57, the system actor anywhere, and another caller only on rows whose `everyone_level` is `read_write`. The op stays in `DEVELOPER_OPS`.

Reason: a pass is many transactions, and a right can change between two of them. A transaction that destroys rows must judge its caller in its own snapshot, so a posture change committed between slices stops the pass at the next slice. Judging once, at the first slice, would let a pass go on destroying for a caller who no longer may. For the system actor the gate and the fence issue no statement (fact 1 counts none). Precedent: today's purge judges each collected round before deleting it (fact 6).

### 3. A pass is always a loop of slices, and a slice works on at most one budget of units

A unit is one root in the `roots` phase, and one key examined in an orphan phase. There is no unsliced mode and no switch: a pass over three roots is one slice for each phase. Between two slices no transaction is open, so a serialized verb that arrived meanwhile runs before the pass goes on. The slice size is B and nothing else, so every membership predicate of a slice is one chunk and no size is written in the code.

Reason: the source, section 5.1, and the unit's statement. B is the bound every statement of the backend already obeys, read from the engine (fact 6). A smaller declared size is choice 1.

### 4. A slice takes the serialization point where the tree's topology verbs take it, and its checks hold in either place

Each slice calls `serialize` exactly where the other serialized verbs call it when the slice is built. On `dev` that is the first statement, and the hold is the slice's body. If the topology-lock draft lands first, the slice takes the point last before its commit, as that draft's decision 1 moves every topology verb, and the hold is a commit. If it lands after, its build moves the slice with the other verbs and counts it among them, as its outcome names `sweep` among the five verbs it moves. The slice adds no re-check for the move, because its statements already prove again, at the moment they act, what they read: the purge's entry delete re-proves `deleted_at IS NOT NULL` and counts its rows (fact 6), and the orphan delete re-proves the entry's absence and counts its rows (decision 10).

Reason: two drafts that move one lock in two ways would collide, and the topology-lock draft is the one whose subject the lock is. A slice whose statements re-prove their reads is sound whichever statement takes the point, so neither draft waits for the other.

### 5. A pass walks a fixed sequence of phases: `roots`, `content`, `blobs`, then `versions`

`RETENTION_PHASES` is a tuple of the four names, walked from first to last. Roots come first, as today, and the body families follow in today's order with `versions` added last, so the warnings of a pass keep their order (`tests/storage/database/test_coherence.py:420-422` asserts content before blobs). A later reclaim of a mount's own table joins as one more name and one more slice function.

Reason: the source, sections 5.2 and 5.3. Destroying roots first lets the orphan phases of the same pass see the bodies the roots left, none of which a purge leaves behind (fact 6).

### 6. A roots slice seeks the oldest expired roots by `deleted_at`, with no tie-break and no position

The select is `WHERE deleted_at < :cutoff AND trash_root_id = entry_id ORDER BY deleted_at LIMIT :B+1`, served by `ix_vfs_entries_deleted_at`. No `entry_id` tie-break is added: EXECUTED, `ORDER BY deleted_at, entry_id` adds `USE TEMP B-TREE FOR LAST TERM OF ORDER BY`, a sort of every root sharing the oldest timestamp, and one delete batch stamps one time on all its roots. The phase keeps no position: a destroyed root is gone, and a root a rival restored is no longer deleted, so the next slice starts at the oldest root that remains. The deletes spec's `n` deleted rows at one name are `n` roots with `n` sets, each expired by its own `deleted_at`; the seek reads no path, so they are destroyed oldest first with every other root.

Reason: the source, section 5.2, and the plans re-read at `27f3d24d` (EXECUTED; fact 2). A select that orders by path must sort every expired root to return the first B.

### 7. Every phase select asks for one row more than a slice works on, and that row is what continues the phase

A roots select and an orphan window each carry a limit of B + 1. The slice works on the first B; if row B + 1 came back, the phase has another slice, else it is over. A phase of N units therefore takes `max(1, ceil(N / B))` slices, and a phase with nothing to do costs one slice of two statements.

Reason: the look-ahead row is the tree's idiom for a bounded read that must know whether more remains (`keyset.py:87`). The source ends a family when "a window returns fewer keys than `:slice`", which opens one more empty transaction whenever N is a multiple of B; this departs from that wording.

### 8. A root is destroyed with its whole set in one slice, so a slice is counted in roots

A slice hands its roots' ids to the purge as one chunk with the deletes spec's proof and judgment, as the retention arm does today, and bumps no parent, by the deletes spec's decision 12. A set is never cut across two slices. The honest profile goes in the docstring: a slice's row count is the sum of its roots' sets, a deleted directory of any size is one unit, and the purge still reads that set's ids into memory and deletes them B at a time inside one transaction (`trash.py:589-614`).

Reason: the source, section 5.2: a set's delete was one transaction, so its destroy is one too, and a set is never half destroyed. The direction, if one large deleted directory shows in a profile, is a purge of that set leaves first behind a durable mark; it is not built here.

### 9. The cutoff and the fence are each read from one clock reading per pass

The pass reads `datetime.now(UTC)` once. Every slice derives its cutoff (`trash_days` before that instant) and its fence (24 hours before it) from that reading, and a redriven slice uses the same reading. A root deleted while the pass runs is younger than the cutoff and waits for the next pass, so the set of expired roots only shrinks during a pass and the `roots` phase ends after at most `ceil(N / B)` slices however fast rivals delete.

Reason: a loop whose bound moves with the clock has no countable end. Precedent: the kernel store's pass, which is handed "the pass's one reading of the clock" (decision 17 on its branch).

### 10. The orphan phases walk `vfs_content`, `vfs_blobs` and `vfs_versions` by `entry_id` in windows, and no statement reads a whole table

An orphan slice issues, after its serialization point, in this order and only as far as each step finds work:

- **The window.** `SELECT entry_id FROM <family> WHERE entry_id > :after ORDER BY entry_id LIMIT :B+1`; for `vfs_versions`, `SELECT DISTINCT entry_id`. The first window of a phase has no `after`.
- **The entries read.** `SELECT entry_id FROM vfs_entries WHERE entry_id IN (:window)`, one chunk through `membership`. It has no liveness term, so a deleted file's body is never a candidate. The keys of the window it does not return are the candidates, taken in memory.
- **The age probe.** `SELECT DISTINCT entry_id FROM <family> WHERE entry_id IN (:candidates) AND created_at >= :fence`. The candidates it does not return are aged.
- **The guarded delete.** `DELETE FROM <family> WHERE entry_id IN (:aged) AND NOT EXISTS (SELECT 1 FROM vfs_entries e WHERE e.entry_id = <family>.entry_id)`. The proof binds nothing, as the purge's does. Where the driver reports a row count, it must equal the aged keys for `vfs_content` and `vfs_blobs` and be at least that for `vfs_versions`; a shortfall raises `StaleSnapshot` and the slice redrives from a fresh window.
- **The subjects delete.** For `vfs_versions` only, the same guarded delete on `vfs_version_subjects` for the same aged keys.

A slice therefore issues, with the lock read, 2 statements when its window is empty, 3 when the window holds no candidate, 4 when every candidate is young, 5 when it reclaims from `vfs_content` or `vfs_blobs`, and 6 when it reclaims from `vfs_versions`. The orphan phases run on every pass, as the reclaim does today. The honest profile goes in the docstring: a pass reads every key of the three families once, so its work is in proportion to the corpus and, for `vfs_versions`, to the whole kept history, one index entry for each version row; the directions are unit 180-5's key, which spreads one walk over many calls, and choice 4.

Reason: the source, section 5.3, re-planned at `27f3d24d` (fact 7). The source folds the age test into the delete for "at most three statements per family per slice"; this departs from it, because a delete that filters by age cannot say which keys it took, and each reclaimed key is reported (decision 12). The count check follows the tree's rule for a set-based destroy (`trash.py:599-603`). Orphans are residue, so the common slice is the three-statement one.

### 11. An orphaned file's version rows go together, once none of them is younger than the fence

The age probe is by `entry_id`, so a file with one young version row keeps every version row until a later pass. A version row with a null `created_at`, which the mint never writes (fact 8), counts as aged. A subject row whose file has no version row is not walked: both tables lose a file's rows in the same purge chunk (`trash.py:606-608`), so that residue needs a hand-written statement to exist.

Reason: the fence keeps an in-flight write's rows out of reach (`trash.py:110-112`), and a file with a young row may be in flight. A fourth walk for residue no verb makes is not worth a pass over its table.

### 12. The fence, the warning's kind and its shape stay as they are

`_ORPHAN_AGE_FENCE` stays 24 hours. Each reclaimed key is one record of kind `vfs.internal`, severity `warning`, with `data={"entry_id": ...}` and a message naming the table, built as today (`trash.py:648-656`); a version reclaim names `vfs_versions`, and the verb named in the message is the one the deletes spec leaves. One warning stands for a file and a family, never for a version row, so a file with ten thousand orphaned versions is one line. A pass that reclaims orphans is still a success.

Reason: the source, section 5.3, and `tests/storage/database/test_coherence.py:401-422`, which pins today's warnings.

### 13. The answer lists the destroyed roots slice by slice, by trash path within a slice, then the warnings in phase order

A slice sorts its own roots by trash path, then by `deleted_at`, and the pass appends each slice's rows to the answer. Slices run oldest delete first, so across slices the order is by `deleted_at`. Each row is the deletes spec's: status `destroyed`, its trash path, its `deleted_at`. A pass of one slice returns the answer the deletes spec's arm returns. The answer carries no new field.

Reason: the source, section 5.2, "in `deleted_at` order across calls and `path` order within a slice", with the deletes spec's row. The second key orders the `n` rows one name can hold, which the deletes spec makes possible.

### 14. A slice that is refused, fails or is cancelled ends the pass, and committed slices stay

A slice ends in one of four ways: it commits; its judgment refuses it; its transaction fails (a redrive exhausted, an engine error); or the call is cancelled. On a refusal or a failure the pass runs no further slice and returns the rows and warnings of every committed slice with the failing slice's errors; `success` is false. On a cancellation the slice in flight rolls back and the cancellation propagates. Committed slices stay committed, and the next call continues from what remains, because a destroyed root is gone and an orphan phase starts again at its first key. Because `success` is false, the kernel store's pass, which runs "only when the storage's retention succeeded", does not run after a partial pass; it runs after the next pass that ends whole. Warnings leave `success` true (`src/vfs/results/envelope.py:388-390`), so a pass that only reclaims orphans still lets it run.

Reason: the tree's one multi-transaction verb does the same, "a chunk that fails leaves its mark for the next call" (`backend.py:1320-1322`), as does the kernel store's pass, "a pass that is cancelled or fails has removed whole chunks and nothing else" (decision 17 on its branch). An irreversible act that hid what it had already done would leave no record of it. For a pass of more than one slice this departs from the deletes spec's "refuses the call whole"; choice 2 holds the departure.

### 15. The pass and the orphan slices live in a new module, and the roots slice in `trash.py`

- `src/vfs/storage/backends/database/retention.py`, new: `RetentionPhase`, `RETENTION_PHASES`, `RetentionMark`, the orphan slice `reclaim_orphans`, the slice dispatcher, and the loop `run_retention`. Its module docstring states what a slice is and carries the two honest profiles of decisions 8 and 10.
- `src/vfs/storage/backends/database/trash.py`: the roots slice, `destroy_expired_roots`, under the verb's banner beside the deletes spec's `destroy_rows`, so the purge stays private to its module. `_reclaim_orphan_content` is deleted, and the head branch leaves `destroy_rows`.
- The mark is `class RetentionMark(NamedTuple)` with `phase: RetentionPhase` and `after: str | None = None`; a slice returns its rows, its warnings and the mark to go on from, or no mark when the pass is done. A private mapping of phase to table sits beside the tuple, so no position in a sequence stands for a table.

Reason: `backend.py` may not grow (fact 9) and `trash.py` gains the deletes spec's code too, so the new code goes to a module of its own, as the listing work put its pages in `listings.py` and `keyset.py`. Function names are verb first and types are nouns, as `documentation/maintainers/how-we-name.md` asks.

### 16. Each slice commits through the topology verbs' own parts, and the held advisories are taken once

`DatabaseStorage.destroy` gains no method. Its head branch calls `run_retention` with a commit function built of the three parts `_execute_topology` composes, `_mutate`, `fenced` and `topology_execution_options` (`backend.py:1454-1463`), and takes the host's held advisories once, on the pass's answer. A redrive after a stale snapshot repeats one slice, never the pass. `backend.py` stays at the baseline the deletes spec leaves it; if the branch cannot be paid for inside the method, the pull request sets the baseline to the count reached and says so, as the deletes spec's Scope does.

Reason: the advisories belong to "the public verb that returns next" (`backend.py:1397-1401`) and a pass is one public call. A second runner that copied the fence and the execution options would be the duplication `AGENTS.md` names as a smell.

### 17. Between two slices the pass awaits the seam `retention:after-slice`

The seam fires after each slice commits and before the next begins, and never after the last. With no handler it is an inert await. It is the window the race and rights tests stage their rivals in.

Reason: precedent `relabel:after-chunk` (`backend.py:1343`) and the seams' own rule that a race window the public surface cannot reach declares a named seam (`seams.py:3-10`).

### 18. The mark stays in memory, and this spec adds no resumption key, schema change or error kind

`RetentionMark` is a value the loop holds between slices. It is not returned, stored or accepted from a caller. A call runs slices until every phase is done, which is the end state of today's one transaction. `limit=`, `after=`, the key's encoding and the field it rides are unit 180-5's, which serialises this mark; the kernel rulings' decision 5 makes `next_after` a path, which a retention key is not.

Reason: the unit map splits the slices (this unit) from the resumable call (180-5), so that each is one pull request.

### 19. Two passes at once destroy each row once

Two passes on one mount, from one process or two, take turns slice by slice on the point. A roots slice of the second sees no root the first destroyed, because its select runs under the point after the first's commit. Should the point move last (decision 4), the purge's proof and count, and the orphan delete's proof and count, make the later slice redrive and find the rows gone.

Reason: a deployment may run the pass from a job and a developer may run it by hand; the kernel store's pass makes the same promise of two passes at once (decision 17 on its branch).

### 20. The branch runs `scripts/ci.sh`, `scripts/docs.sh check` and the Postgres leg

It touches `src/`, `tests/` and docstrings under `src/vfs/`, and it changes statements of the database backend.

Reason: `AGENTS.md`, Tooling, names both gates for a branch that touches those trees; the storage contract and the race tests run on Postgres only through its leg.

## Cost

Costed per corpus: a retention pass is a whole-mount maintenance act, costed at one a day. Nothing here runs per verb call, per file write or per index visit; if the trash-is-emptied draft makes the daily rebuild the caller, the pass rides the rebuild once, which is still once per corpus. B is 32,668 on SQLite and Postgres and 1,000 on the floor; the figures below give Postgres first and the floor second.

| Addition | Grows with | At the reference deployment | Declared bound |
|---|---|---|---|
| Roots select, one per roots slice | nothing: a seek of B + 1 index entries | expired roots a day are an assumption: the deletes spec's decision 15 sets 5,000 deletes a working day, so about 5,000 roots expire a day, 1 slice on Postgres and 5 on the floor; at the write ceiling of 1,100,000 a day as an upper bound, 34 and 1,100 | limit `membership_budget + 1` |
| The purge of a slice's roots | the rows of those roots' sets | for single-file roots, one chunk: 2 collections and 9 deletes (EXECUTED, fact 1, less the parent bump the deletes spec drops) | every `IN` list one chunk through `chunked` and `membership`; the set itself is unbounded (decision 8) |
| Orphan window, one per orphan slice | nothing: B + 1 index entries, or the version index entries of B + 1 files | about 10,000,000 body keys over `vfs_content` and `vfs_blobs`: about 307 slices on Postgres, 10,000 on the floor; `vfs_versions` holds at most one key per file, 10,000,000, read through one index entry per version row, a number that grows by at most about 1,050,000 a day with the writes | limit `membership_budget + 1` |
| Entries read, one per non-empty window | nothing | at most B seeks of `ix_vfs_entries_entry_id` | one chunk through `membership` |
| Age probe and guarded deletes | the candidates of one window | zero on a mount with no residue; at most B keys | one chunk through `membership`; the proof binds nothing |
| A slice's keys in memory | nothing | at most B + 1 keys, about 1 MB of ULID strings at 32,668 | `membership_budget + 1` |
| The pass's answer in memory | destroyed roots plus reclaimed keys | one row or one warning each, as today | none here; unit 180-5's `limit=` bounds a call |
| The loop of slices | units over B | about 620 short transactions for a full pass on Postgres, about 20,000 on the floor | `max(1, ceil(N / membership_budget))` a phase (decisions 7 and 9) |

The total work is of the order today's pass does for bodies, since today's anti-join also reads every body row and seeks an entry for each, plus the new walk of `vfs_versions`. What changes is that it is cut into transactions of bounded size, each interruptible, with at most B + 1 keys in memory.

**Per lock.** Who waits on the point: the mount's other serialized verbs, delete, restore, move, copy and destroy, and nothing else, so no read, plain write or rights compile waits behind a slice on Postgres (`serialized.py:115-118`). A read never waits on a pass, before or after. Today the hold is the pass and grows with the corpus. After this spec it is one slice: an orphan slice is at most 6 statements over at most B keys; a roots slice of single-file roots is 13 statements, and 9 more for each further chunk of a larger set. The hold is a slice's body until the topology-lock draft makes it a commit (decision 4). At the daytime peak of about 20 verb calls a second, the share that are serialized verbs is not measured; deletes alone are about 5,000 a working day, about one every six seconds, so a hold of a second stalls well under one call. On SQLite the writer transaction is the lock, so every writer on the file waits for one slice where it waited for the pass.

## Left as it is

- **The single-set arm,** `destroy("/.vfs/trash/<path>")`: one transaction, by decision 1.
- **A writer beside a long pass on SQLite.** Slices follow each other with no pause, and a writer waiting on SQLite's busy budget may give up after about twenty seconds beside a long pass, as beside any long writer (`agents/2026-11-21-a-sqlite-writer-beside-a-batch-waits-for-its-commit/spec.md`). The kernel store's pass states the same profile: "A long pass on SQLite is run when the root is quiet" (decision 17 on its branch). SQLite is the development default; the docstring says so.
- **A large deleted directory** is destroyed in one slice (decision 8).
- **Orphaned chunk, segment and edge rows,** which the source also leaves out, and subject rows with no version row (decision 11).
- **Who calls the pass,** and a count of expired rows where a deployment looks: the trash-is-emptied draft and unit 180-6.
- **The kernel store's pass,** its chunk of 5,000 and its order after retention: the kernel-records branch.
- **A replay store's reclaim.** Roadmap K5's criterion 5 hangs one on this arm (`context/standards/roadmap.md:183`); unit 177-3, which would add it, is not written and its store's home is contested by the kernel-records spec, so no phase is reserved for it. It joins by decision 5 if it lands as a table of the mount.
- **Two rows at one trash path in one answer,** when `n` deleted rows at a name expire together: the deletes spec's row shape, which this spec orders (decision 13) and does not change.

## Tests

Each is written and seen failing before the code, except the pins marked unedited. Counts and states, never clocks. "At budget 100" means the host's profile narrowed with `monkeypatch.setattr(host, "_profile", replace(host.profile, in_list_budget=100))`, as `tests/storage/database/test_dialects.py:217` narrows a profile. Statements are counted with the `_spy` listener of `tests/storage/database/test_trash.py:1045-1051`, which leaves out control and statistics statements; transactions are counted as the `BEGIN IMMEDIATE` statements the SQLite engine sends, recorded beside `_spy`, with the statistics step's own transaction left out as `is_statistics_statement` leaves out its statements. Unless a test names a caller, the caller is the system actor, and test names below are written after the deletes spec's rename.

`tests/storage/database/test_trash.py`, a new class `TestRetentionSlices`, on a file-backed SQLite storage:

- `test_a_pass_opens_one_transaction_per_slice`: at budget 100, 300 expired single-file roots and no orphan: exactly 3 transactions delete from `vfs_entries`, the pass opens 6 transactions in all (3 for roots, 1 for each orphan family), and the first statement recorded in each is the `vfs_lock` read.
- `test_every_statement_of_a_pass_stays_within_one_budget`: in that pass every roots select and window binds a limit of 101, and no statement binds more than 100 keys besides its fixed binds.
- `test_a_slice_costs_the_same_statements_at_any_garbage_size`: at budget 100, every roots transaction issues the same number of statements at 300 roots and at 1,000, and the pass opens `ceil(N / 100) + 3` transactions at each.
- `test_a_root_set_larger_than_the_budget_is_destroyed_in_one_slice`: at budget 100, one deleted directory of 250 files is destroyed by exactly 1 transaction, in 3 deletes from `vfs_entries`, and 0 rows of its set remain in any family table.
- `test_a_root_deleted_during_a_pass_waits_for_the_next_pass`: `trash_days=0`, budget 100, 150 expired roots; a file deleted at the first firing of `retention:after-slice` is still deleted after the pass, and the answer holds exactly 150 rows.
- `test_a_pass_answers_slice_by_slice_and_by_trash_path_within_a_slice`: at budget 100, 100 roots under `/z` deleted before 100 under `/a`; the answer's first 100 rows are the `/z` trash paths in path order and the next 100 the `/a` ones.
- `test_a_pass_cancelled_between_slices_keeps_whole_slices`: at budget 100 with 300 expired roots, the task running the pass is cancelled at the first firing of `retention:after-slice`; exactly 200 expired roots remain, no body, version or posting row is left without its entry, and a second pass destroys the 200.
- `test_no_statement_the_pass_adds_scans_a_table_on_sqlite`: the `EXPLAIN QUERY PLAN` of the roots select, the three windows, the entries read, the age probe and the guarded deletes, as the pass issued them, holds 0 `SCAN` lines.
- `test_the_windows_read_no_table_by_a_sequential_scan_on_postgres`, parametrized over `ENGINE_LEGS` and marked `slow`: over 200,000 body rows made by one statement, the plans of the three windows and of the entries read hold 0 `Seq Scan` nodes, read as `tests/support/plan_store.py` reads a Postgres plan.
- Unedited: `TestScale::test_a_retention_sweep_issues_a_flat_number_of_statements_in_roots` under its renamed name, and the retention tests the deletes spec keeps in this file.

`tests/storage/database/test_coherence.py`, a new class `TestOrphanWindows`:

- `test_a_pass_reclaims_aged_orphan_version_rows_with_their_subjects`: three version rows of two entry ids that name no entry, aged 25 hours, with two subject rows, are gone after a pass; a one-hour-old orphan version row and a live file's version rows remain; the answer carries exactly 2 warnings of kind `vfs.internal`, each naming one entry id and `vfs_versions`.
- `test_the_orphan_phases_walk_three_families_in_windows`: at budget 100, 250 live files, three aged orphan content rows, one aged orphan blob row and two aged orphan version entries; the answer carries exactly 6 warnings in the order content, blobs, versions; the content phase opens `ceil(K / 100)` transactions for the K content keys the test counts; and an orphan transaction issues exactly 2, 3, 5 and 6 statements in the cases decision 10 names, each case met in the run.
- `test_a_file_with_one_young_version_row_keeps_all_its_rows`: an orphaned file with two aged version rows and one an hour old keeps 3 rows and gets 0 warnings.
- `test_aged_orphans_of_three_families_are_reclaimed_on_every_server_engine`, parametrized over `ENGINE_LEGS`: one aged orphan in each of the three families is reclaimed with exactly 3 warnings, and a young one in each remains.
- Unedited: `TestWriteVsTopologyCoherence::test_sweep_reclaims_only_aged_orphan_bodies` under its renamed name.

`tests/storage/database/test_races.py`, class `TestPurgeWindows`, each parametrized over `ENGINE_LEGS` and run at budget 100:

- `test_a_restore_between_retention_slices_survives_whole`: a deleted directory of 3 files restored at the first firing of `retention:after-slice`, before the slice that would destroy it, is live with its 3 files after the pass, and the answer holds the 100 rows of the first slice only.
- `test_a_create_at_an_expired_name_between_slices_survives`: a `write` at an expired root's path at the first firing, before the slice that destroys that root, leaves a live file with the new body and a version of 1, and the deleted root is destroyed.
- `test_a_rival_delete_lands_between_two_retention_slices`: with 150 expired roots, a `delete` of a live file driven at the first firing and awaited under the test's own deadline returns success while 50 roots remain to destroy.
- `test_two_passes_at_once_destroy_each_root_once`: two passes over 300 expired roots, started together, both succeed, their answers hold 300 rows between them with no path twice, and 0 expired roots remain.

`tests/storage/database/test_rights.py`, module-level, as the file is laid out, on the in-memory storage:

- `test_a_refused_retention_pass_names_no_row_and_destroys_nothing`, the leak test: a named caller on a mount at `read_write` with one expired root under a region below `read_write` that the caller may not list; the answer holds 0 rows and 0 warnings, no `DELETE` is issued, and its errors equal, in kind, path, message and data, the errors of the same call on a mount whose only such root lies at another path.
- `test_a_posture_change_between_slices_ends_the_pass_with_what_committed`: at budget 100, a named caller and 300 expired roots under `/open` at `read_write`; the system actor sets `/open` to `read` at the first firing of `retention:after-slice`; the answer is not a success, holds exactly 100 rows and 1 `permission_denied`, 200 expired roots remain, and no `DELETE` is issued after the refusal.

Unedited elsewhere: the storage contract's retention rows under the deletes spec's names, on the memory, SQLite and Postgres conformance classes of `tests/storage/test_conformance.py`; the deletes spec's `test_a_retention_pass_that_meets_one_closed_row_destroys_nothing` in `tests/support/grants_contract.py`, whose rows fit one slice; and the op-plane pins of `tests/test_ops.py` as the deletes spec renames them.

Whichever of this unit and the kernel-records branch lands second writes `tests/kernel_store/test_sweep.py::test_a_retention_pass_that_fails_a_slice_runs_no_store_pass`: with an expired kernel record and a pass whose second slice is made to fail, the record remains and the answer is not a success.

## Scope

In:

- `src/vfs/storage/backends/database/retention.py`, new (decision 15).
- `src/vfs/storage/backends/database/trash.py`: `destroy_expired_roots`, the head branch's removal from `destroy_rows`, the deletion of `_reclaim_orphan_content`, the module docstring.
- `src/vfs/storage/backends/database/backend.py`: the head branch of `destroy` (decision 16).
- The tests above.

Out:

- `limit=`, `after=` and the resumption key: unit 180-5.
- The garbage gauge: unit 180-6. It counts no orphans, which only these windows find.
- The verb's name, its arms, its rights rule and its rows: the deletes spec.
- Who calls the pass: the trash-is-emptied draft.
- Moving the serialization point: the topology-lock draft (decision 4).
- `pack` and any rewrite of a version row: unit 180-3. A retention of old versions of a live file is ruled out: the full history is kept (`context/standards/roadmap.md:1181`).
- A 10,000-entry statement pin of the verb on the Postgres leg: roadmap story D4.

## What the docs must say

- The docstring of `AsyncVirtualFileSystem.destroy`, which the deletes spec writes, gains: at `/.vfs/trash` the pass runs in short transactions; one that fails part way has destroyed what its committed slices destroyed, says so in its answer and is not a success; calling again continues; a delete, restore, move or copy on the mount waits for one slice at most.
- The module docstring of `trash.py`, on the verb, and that of `retention.py`, with the profiles of decisions 8 and 10 and the SQLite note under "Left as it is".
- No page under `documentation/` describes the pass (EXECUTED, `grep -rln sweep documentation/` names `reference/access-levels.md`, which states who may call the verb, and three pages that use the word in other senses), so none changes here.

## Earlier decisions this reverses

- The deletes spec's decision 13, "one row that fails refuses the call whole", for a retention pass of more than one slice: the slice is refused whole and the slices before it stay (decision 14; choice 2).
- Numbered spec 180, section 5.3: the end of a family on a short window, and three statements per family per slice (decisions 7 and 10).

## Not checked

- Nothing was run on Postgres: no server was available. Every plan and count above is SQLite's, on a mount of 300 files, which shows which index a statement can use and not what a planner picks at ten million rows. The Postgres tests above are the check.
- How long a slice holds the point on either engine. The kernel store measured 67 ms for a chunk of 5,000 on Postgres (decision 17 on its branch); a roots slice at B = 32,668 deletes from nine tables and was not timed.
- The deletes spec is not built, so the statement counts of a roots slice under its judgment, its gate and its rows were inferred from today's arm; decision 8's 13 statements assume the deletes spec drops the parent bump and adds no statement for the system actor.
- Whether the deletes spec's third landing leaves `_purge`'s per-round `admit` or replaces it; decision 2 relies only on rows being judged before they are deleted.
- The kernel-records branch was read at its tip on 2026-11-25 and not run.
- Whether `tests/storage/test_cancelled_call.py` should add `destroy` to its table of verbs; it holds none of the topology verbs' maintenance arms today.

## Choices to confirm

1. **The slice size.** Options: one membership budget, 32,668 on both served engines; or a declared, smaller retention budget, such as the kernel store's measured 5,000. Taken: the membership budget, because the unit states it, every `IN` list of a slice is then one chunk, and no new constant is declared; narrowing it later is one value in one place.
2. **A refusal part way through a pass.** Options: refuse the slice whole and keep the slices before it; or judge every expired root's set in a read-only walk before the first slice, so that a refused pass destroys nothing. Taken: the slice, because a walk first costs a second read of the backlog and a right can still change between the walk and the destroy; the walk can be added later without changing what a single-slice pass does.
3. **The serialization point in an orphan slice.** Options: take it, as every slice does; or run orphan slices without it, since no topology verb reads a body row by key and each orphan delete proves its own reads. Taken: take it, as the unit states; dropping it later is the removal of one call.
4. **The orphan phases on every pass.** Options: every pass, as today; or a separate, rarer act, as the tree's docstring and the trash-is-emptied draft's choice 3 suggest. Taken: every pass, because that keeps today's behaviour and the windows already bound each transaction; making them rarer later is an additive flag.

## One line

`destroy("/.vfs/trash")` becomes a loop of short serialized transactions, one budget of roots or keys each, so that no rival waits for more than a slice, no statement reads a whole table, a stopped pass keeps what it committed, and orphaned version rows leave with the bodies.
