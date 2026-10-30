# 180 — History: `pack` on `reindex`, the bounded `sweep`, the garbage gauge, and the history read

- **Status:** draft — cut 2026-10-24 from ADR 087 (proposed the same day) and the two memos it stands on. Not started. 8 open `[NEEDS CLARIFICATION]` markers, each carrying a lean.
- **Date:** 2026-10-24
- **Owner:** Clay Gendron
- **Kind:** feature. A new `reindex` phase, `pack`, in a new module `src/vfs/storage/backends/database/pack.py`, with its pure planner in `src/vfs/models/versioning.py`. Two columns and one index on `vfs_versions`. `sweep(limit=, after=)` run in slices, each its own transaction. A storage-level `garbage()` gauge. A new read verb, `versions(path)`, and `read(path, version=N)`. One new `Observation` field, `actor`.
- **Depends on:** spec 176 (the resumption-key field on `Result` and the `after=` / `limit=` grammar; the sweep key and the `versions` key ride that field). Spec 175 (the integrity kind a hash mismatch classifies as, and the `scrub` that covers version rows). Pack, the gauge and the sliced sweep internals land before 176; the two cursor-bearing surfaces land after it (see `tasks.md`).
- **Decisions it implements:** ADR 087 pin 11 (the whole of it), pin 1 (history operations are kernel operations), pin 7 (`sweep` moves to the resumable model), pin 9 (a served version body is verified), pin 14 (counted access paths); ADR 017 pins 3–4 (forward diffs, cadence counted in stored rows) with the amendment below; ADR 027 pins 3–4 (sweep is the only destroyer, on the developer plane); ADR 064 (attribution survives pack untouched); ADR 065 pins 1, 2 and 5 (hidden rows are absent; statistics are visible-set); ADR 074 item 8 (sweep by retention); ADR 016 (versions are addressed by owning file plus key, never by path).
- **Research it stands on:** `../../../research/2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md` §2.6, §5 step 9, §6 Q3 (Clay's answer: keep the full history, convert cold versions to deltas during `reindex`, name the step `pack`); `../../../research/2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md` §4.3 (the history read belongs in the kernel); `../../../research/studies/2026-10-24-ostep-principles-for-vfs/04-locality-and-log-structure-ffs-lfs-ssd.md` P1–P7 and Appendix A (`experiments/s04/lfs_probe.py`); `05-crash-consistency-and-data-integrity.md` §2.5, §2.7, §2.9; `02-files-and-directories-the-api.md` principle 11. Five probes run for this spec on 2026-10-24 at HEAD `ba77449`, `uv run` against `InMemoryStorage` (in-process SQLite), counting rows, bytes and statements and never timing anything. Their numbers are recorded below and labelled EXECUTED.

## Intent

vfs keeps every body a write replaces, as a whole copy in `vfs_versions`. Three rewrites of a corpus leave three times the corpus in history, and nothing ever shrinks it. After this spec, `reindex` runs a phase called `pack`. Pack rewrites cold version rows into one snapshot plus forward diffs, using the diff law vfs already has. No version is ever deleted. Every version still reconstructs byte for byte, and pack proves it by hash before it lands anything.

The same spec makes the cleaners bounded and visible. `sweep` takes a `limit` and hands back a resumption key, so a deployment job reclaims tombstones and orphan bodies in slices, one short transaction each. A two-statement gauge tells that job how much garbage a mount holds. And the history becomes readable: `versions(path)` lists a file's version rows a page at a time, and `read(path, version=N)` returns any one of them, verified by its hash.

## Terms

| Term | Meaning here |
|---|---|
| version row | One row of `vfs_versions`: a body a write replaced, labelled with the version number it had (ADR 017). |
| snapshot | A version row that stores the whole body (`is_snapshot` true; text in `content`, bytes in `data`). |
| diff | A version row that stores only a unified diff (`version_diff`) from the previous stored row's text to its own. |
| chain | One file's version rows in label order. A diff is read by walking forward from the nearest snapshot below it. |
| hot / cold | A hot row is one of the newest `PACK_HOT_ROWS` rows of a file. Every older row is cold. Only cold rows are packed. |
| judged | A row pack has decided on (new column `packed` true). The decision is "diff" or "keep whole". |
| tombstone | A deleted row: still in `vfs_entries`, with `deleted_at` set (ADR 074). |
| orphan | A body or version row whose `entry_id` names no row in `vfs_entries`. |
| slice | One bounded unit of cleaning work, run in its own transaction. |
| resumption key | An opaque string a call returns so the next call continues where it stopped (spec 176's shape). |
| gauge | A cheap read that counts garbage, so a scheduler can decide when to clean. |

## What the code does today

| Fact | Where | Label |
|---|---|---|
| The mint writes one whole snapshot per replaced body, `is_snapshot` true, never a diff. | `versions.py` `mint_versions`, `_version_row` (line 158) | READ |
| The mint compares the pre-image's hash with the *new body's* hash (`version["content_hash"] == staged.content_hash`, line 145). It never reads `vfs_versions`. | `versions.py` `_mint_rows` | READ |
| No code writes `version_diff`, and no code reads `vfs_versions` except `_purge`, which deletes a purged entry's rows. | `trash.py` line 581; repo-wide grep | READ |
| The diff law exists and is tested: `compute_diff` (difflib unified diff, 3 lines of context), `apply_diff` (unidiff), `reconstruct_version`, `Version.reconstruct` (order-based, verifies `content_hash`). | `models/versioning.py`, `models/version.py` lines 191–222, `tests/models/test_versioning.py` | READ |
| `create_version` picks snapshots by label arithmetic (`version_number % SNAPSHOT_INTERVAL`), which ADR 017 pin 4 rules out over gapped labels. It has no caller in `src/` except `Version.create`, which has none. | `models/versioning.py` lines 163–165 | READ |
| The diff law round-trips byte for byte on 18 hand-picked hard cases (CRLF, lone CR, U+2028, form feed, `\x1c`, `\x85`, lines that look like diff headers or the no-newline marker, no trailing newline, empty to text and back) and on a seeded fuzz of 5,000 random edits over those characters: 0 mismatches, 0 errors. | probe `diff_law_probe.py`, `diff_fuzz.py` | EXECUTED |
| A context-0 diff (no context lines) fails through today's `apply_diff` in 476 of 3,000 seeded trials: pure-insertion hunks land one line early. So the law keeps its 3 lines of context. | probe `pack_probe_big.py` | EXECUTED |
| One retention `sweep` is one transaction over every expired root, plus an orphan anti-join over all of `vfs_content` and `vfs_blobs`, under the serialization point. On SQLite it issued 17 statements at 100, 1,000 and 5,000 expired roots (`BEGIN` 1, `SELECT` 6, `DELETE` 9, `UPDATE` 1; membership budget 32,668). On Oracle's 1,000-key budget the delete count grows by 9 per 1,000 roots, and the transaction always grows with the garbage. | `trash.py` `sweep_rows` (line 342), `_reclaim_orphan_content` (line 592); probe `sweep_gauge_probe.py` | READ, EXECUTED |
| `reindex` holds a single-runner lease, runs phases each in its own writer transaction, checks a `lost` flag between them, and runs its render stage as keyset pages that read with no transaction open, compute on the offload pool, and land in one short write. | `indexing.py` lines 151–235; `backend.py` `_reindex_phases` (line 1187), `_render_step` | READ |

## 1. Pack: which rows are cold

**The rule.** A version row is cold when at least `PACK_HOT_ROWS` newer version rows of the same file exist. Coldness is a distance in stored rows from the newest row, counted the way ADR 017 pin 4 counts the snapshot cadence: rows, never label arithmetic.

```python
# models/versioning.py
PACK_HOT_ROWS: Final = 1
"""The newest version rows of a file that pack leaves whole: the undo a reader reaches in one row."""
```

Why distance, and not the other two candidates:

| Rule | What it needs | Verdict |
|---|---|---|
| **Distance from the newest row (chosen)** | Nothing new. A row turns cold only when the mint writes a newer row, so pack's work list is the set of rows minted since its last run. | Proportional to new work. Per-file churn is built in: a file rewritten nightly accumulates cold rows and packs; a file written once never has a cold row. That is study 04's P5 (hot/cold) without a policy knob. |
| By age (`created_at` older than T) | An index on `vfs_versions.created_at`, and a re-scan every run, because rows turn cold by the clock, with no write to mark them. | Rejected: work is proportional to all history, not to new history. |
| By per-file churn (rewrites per day) | A rate per file, stored or computed. | Rejected as a separate rule: the distance rule already packs exactly the files that churn. |

**The lean on the window.** The brief for this spec asked that the newest version row stay a snapshot. The code shows the mint never compares against any version row (see *What the code does today*), so nothing in the write path needs it whole. What it buys is a one-row read of the most recent undo. What it costs is measured:

| Corpus (EXECUTED, `pack_probe.py`, `pack_probe_big.py`) | `PACK_HOT_ROWS = 1` | `PACK_HOT_ROWS = 0` |
|---|---|---|
| study 04's literal corpus: 1,000 files, 3 rewrites, every line changes | 3,000 snapshots, 0 diffs, ratio 1.000 | same, 1.000 |
| one or two lines changed per rewrite, 20-line bodies, 1,000 files × 3 rewrites | 2,000 snapshots, 1,000 diffs, ratio 0.791 | 1,000 snapshots, 2,000 diffs, ratio 0.616 |
| one or two lines changed per rewrite, 200-line bodies, 1,000 files × 3 rewrites | 2,000 snapshots, 1,000 diffs, ratio 0.681 | 1,000 snapshots, 2,000 diffs, ratio 0.376 |
| one or two lines changed per rewrite, 20-line bodies, 100 files × 25 rewrites | 400 snapshots, 2,100 diffs, ratio 0.620 | 300 snapshots, 2,200 diffs, ratio 0.604 |

"Ratio" is stored version bytes after pack over stored version bytes before it. Reading the table: on short histories the hot row holds a third of the history whole; on long histories it hardly matters.

[NEEDS CLARIFICATION: keep the newest version row whole (`PACK_HOT_ROWS = 1`, the lean, as the brief asked), or pack every version row (`0`), which halves the bytes on three-rewrite histories and costs a walk of up to nine diffs for the most recent undo?]

A note on the diff direction, for the record. Reverse diffs (the newest row whole, older rows as diffs backwards, as RCS stores a trunk) measured the same as `PACK_HOT_ROWS = 0` with forward diffs (ratios 0.616 and 0.605 on the second and fourth rows above). ADR 017 pin 3 fixes forward diffs and the code is built for them; this spec keeps them.

## 2. Pack: the chain law

Pack walks one file's rows in label order and decides each cold, unjudged row by this table. The first row that matches wins.

| # | The row | Decision | Chain state after |
|---|---|---|---|
| 1 | is a bytes row (`data` set) | keep whole; bytes are never diffed | no text predecessor; chain length 0 |
| 2 | has no verified text predecessor (the first row, the row after a bytes row, the row after a rotten row) | keep whole | chain length 0 |
| 3 | would make the chain since the last snapshot reach `SNAPSHOT_INTERVAL` stored rows | keep whole | chain length 0 |
| 4 | is larger than `PACK_MAX_BODY_BYTES` | keep whole | chain length 0 |
| 5 | does not hash to its own `content_hash` | keep whole, report rot (§8) | no text predecessor; chain length 0 |
| 6 | its diff from the predecessor's text, applied back, does not hash to `content_hash`, or the diff is not smaller in UTF-8 bytes than the body | keep whole | chain length 0 |
| 7 | otherwise | store the diff | chain length + 1 |

So a chain is at most one snapshot and nine diffs, with `SNAPSHOT_INTERVAL = 10` (the existing constant, now counted in stored rows as ADR 017 pin 4 says). A read walks at most nine diffs. Row 6 is why pack can never grow history: a diff lands only when it is smaller and only when it has already reconstructed the exact body. On study 04's literal corpus every diff is larger than its body, so every row stays whole (EXECUTED, ratio 1.000 above).

The planner is pure Python over plain values, so it is unit-testable and runs on the offload pool:

```python
# models/versioning.py
class PackRow(NamedTuple):
    """One version row as pack reads it: its label, its stored form, and its full text when it has one."""

    number: int
    is_bytes: bool
    is_snapshot: bool
    judged: bool
    content_hash: str
    size_bytes: int
    text: str | None


class PackDecision(NamedTuple):
    """What pack lands for one cold row: a diff with its stored size, or keep whole."""

    number: int
    content_hash: str
    diff: str | None
    stored_bytes: int


class PackPlan(NamedTuple):
    decisions: list[PackDecision]
    rot: list[int]


def plan_pack(chain: Sequence[PackRow], *, hot: int = PACK_HOT_ROWS) -> PackPlan:
    """Decide every cold, unjudged row of one file's *chain*, oldest first, by the chain law."""
```

`chain` is the file's rows from its last judged snapshot onward (§3). The planner first rebuilds the text of the judged rows it was given (snapshot text, then each diff applied, each step hash-verified), so the first unjudged row has a verified predecessor and a correct chain length. A judged row is never re-decided.

`PACK_MAX_BODY_BYTES` is an eligibility gate, the same kind as `MAX_INDEXABLE_BYTES` in `indexing.py`: a body above it keeps its whole history, it is never refused and never lost. It exists because `difflib` is quadratic in the worst case and pack runs the Python law.

```python
# models/versioning.py
PACK_MAX_BODY_BYTES: Final = 2 * 1024 * 1024
"""Bodies above this stay whole in history: an eligibility gate on the diff law's cost, never on what is kept."""
```

[NEEDS CLARIFICATION: land pack on the existing Python diff law (`difflib` plus `unidiff`, already a dependency and already tested) behind the 2 MiB gate, with a Rust diff kernel in `crates/vfs-core` as the follow-on and the Python law as its parity oracle (the lean); or build the Rust kernel first, as CLAUDE.md's performance rule asks of engine hot paths? Pack runs off the request path, on the offload pool, so the Python law costs reindex time, not agent latency.]

`create_version` and `VersionRecord` decide by label arithmetic and have no caller in `src/`. Task 1 retires them; `Version.create` builds the snapshot form only, which is the only form the write path makes (ADR 017 pin 4: the write path always snapshots).

## 3. Pack: the phase

### 3.1 Where it runs

`DatabaseStorage._reindex_phases` (`backend.py` line 1187) gains a last step, `_pack_step(tables, lost)`, after `_signal_phase`. It runs last because search freshness serves agents and pack only reclaims space. Every earlier rule of the reindex lease holds: one runner, the `lost` flag checked before every landing, a crashed run freeing the lease by heartbeat expiry.

```python
# storage/backends/database/backend.py
async def _pack_step(self, tables: VFSTables, lost: asyncio.Event) -> tuple[Result | None, PackReport]:
    """Pack every file whose history grew since the last run, one page per short write under the held lease."""
```

The report rides out as a `pack` extra on `reindex`'s `Result`, the way `rendering` does today: `files`, `judged`, `diffs`, `kept`, `bytes_before`, `bytes_after`, `rot`. Rot is also a warning record (§8). Pack never fails the run for a row: a row it cannot pack stays whole.

### 3.2 The durable mark

Pack's mark is the row itself. A new column, `vfs_versions.packed`, is false when the mint writes the row and true once pack has judged it. Each landed page flips its rows in the same transaction that rewrites them. So:

- A crash loses at most the page in flight. Nothing landed is judged twice.
- The next run's work list starts exactly where the last landed page stopped, because the work list is "rows not yet judged".
- No journal row and no cursor in `vfs_meta` are needed. This is the relabel journal's guarantee (study 05 §2.5: recovery in proportion to the work in flight) with the rows as their own journal, the same shape as the render stage's dirty predicate.

Hot rows are never judged, so they stay `packed = false` until they turn cold.

### 3.3 The work list

```sql
SELECT entry_id FROM vfs_versions
WHERE packed = :false AND entry_id > :after
GROUP BY entry_id HAVING count(*) > :hot
ORDER BY entry_id LIMIT :page
```

- A new index `ix_vfs_versions_packed (packed, entry_id)` serves it as an index-only range scan in `entry_id` order.
- `:page` is the dialect's `membership_budget` (1,000 on Oracle), so every later `IN` list of the page fits one chunk.
- `:after` is an in-memory keyset for this run only, so a page that lands nothing cannot repeat within a run.
- Honest profile: with `PACK_HOT_ROWS = 1` the scan visits one index entry per file that has history, every run, plus the new rows. With `0` it visits only new rows. The docstring says so. The direction if that ever matters is a pack-dirty flag set by the mint's own transaction.

### 3.4 One page

1. **Metadata read**, one statement per page, no transaction held open:

   ```sql
   SELECT v.entry_id, v.version_number, v.is_snapshot, v.packed,
          v.content_hash, v.size_bytes,
          CASE WHEN v.data IS NULL THEN 0 ELSE 1 END AS is_bytes
   FROM vfs_versions v
   WHERE v.entry_id IN (:page)
     AND v.version_number >= coalesce(
         (SELECT max(s.version_number) FROM vfs_versions s
          WHERE s.entry_id = v.entry_id AND s.packed = :true AND s.is_snapshot = :true), 0)
   ORDER BY v.entry_id, v.version_number
   ```

   The correlated subquery finds each file's last judged snapshot. Rows read per file are the unjudged rows plus at most `SNAPSHOT_INTERVAL - 1` judged rows of context. EXECUTED on SQLite for the same subquery shape in the history read (§7.2): the plan is two searches of the primary key, `(entry_id=? AND version_number>? AND version_number<?)` and a correlated scalar search, no scan.
2. **Slices.** The page's files are cut into slices of at most `BLOB_PAGE_BYTES` (8 MiB) of text rows' `size_bytes` (a bytes row weighs nothing, because its body is never read), whole files together, with `byte_chunked`. A single file whose run exceeds the budget gets a slice of its own, cut at a row boundary with an upper label bound (`version_number <= :hi`); its remaining rows stay unjudged and the next page picks them up from the new anchor.
3. **Body read**, one statement per slice: the same predicate as step 1, selecting `content` and `version_diff`. It never selects `data`: a bytes row is kept whole, and `is_bytes` from step 1 is all pack needs to know about it.
4. **Plan**, on the offload pool, no transaction open: `call_offloaded(executor, partial(plan_all, slice))`, which runs `plan_pack` per file.
5. **Land**, one short write transaction per slice, after checking `lost`:

   ```python
   to_diff = (
       update(versions)
       .where(versions.c.entry_id == bindparam("b_id"),
              versions.c.version_number == bindparam("b_num"),
              versions.c.packed.is_(False),
              versions.c.content_hash == bindparam("b_hash"))
       .values(is_snapshot=False, content=None, version_diff=bindparam("b_diff"),
               stored_bytes=bindparam("b_stored"), packed=True)
   )
   ```

   executemany, chunked by `byte_chunked(..., BLOB_PAGE_BYTES)` and the parameter budget. The kept rows flip `packed` alone through the set-based triad `_flip_flags` uses today (a `VALUES` join where the profile proves it, a row-value `IN` where `profile.tuple_in`, verified executemany otherwise), generalized to take a table and its key columns and moved to `dialects.py` beside `statement_budget`.

Every statement is bounded at a 10,000-file batch: each `IN` list is one `membership_budget` chunk, each payload is at most one blob page. Statements per page are constant in the size of the mount's history.

### 3.5 Rivals

| Rival | What happens | Why it is safe |
|---|---|---|
| The mint, writing a new version | Inserts a higher label with `packed = false`. Pack never updates an unjudged row it did not read, and labels only grow. | A diff is defined on its predecessor's *text*, which no rival changes. |
| `sweep` purging the file | Deletes all of the file's version rows in one transaction. Pack's guarded update then matches zero rows. | Pack never inserts, so it cannot resurrect a purged row. |
| A second pack after a lease loss | Both guard on `packed = false`; the second landing on a row misses. | Any mix of the two runs' landings reconstructs the same text, because every landed diff was verified against text. At worst a chain runs longer than nine diffs, which costs read work only. |
| A history read mid-landing | See §7.2: one re-read when a chain does not start at a snapshot. | Pack only turns snapshots into diffs, so the re-read finds an earlier snapshot. |

A shortfall in a landing's row count is counted in the report, never an error.

## 4. Pack: what it never does

- It never deletes a version row, and never deletes information: every row's full text is what `content_hash` says, before and after.
- It never touches `vfs_content` or `vfs_blobs` (a statement-table pin in the criteria). The live body is not history.
- It never rewrites attribution: `actor`, `provenance`, `source_identity`, `grant_revision`, `created_at`, `vfs_version_subjects` and the metrics columns (`content_hash`, `size_bytes`, `lines`) are untouched. ADR 064 holds.
- It never diffs a bytes row and never diffs across one.
- It never builds on rotten text (§8).
- It never re-decides a judged row.

## 5. The bounded sweep

### 5.1 The shape

```python
# base.py
async def sweep(
    self,
    path: str = "/.vfs/trash",
    *,
    limit: int | None = None,
    after: str | None = None,
    authority: Authority | None = None,
) -> Result:
```

- **Slices.** The retention arm always runs in slices. A slice is at most `membership_budget` units, in its own transaction, which takes the serialization point as its first statement (`serialize`), runs the gate, does its work and commits. Other serialized verbs (`delete`, `restore`, `move`, `copy`) get the lock between slices.
- **`limit`** caps the units one call processes. A unit is one tombstoned root (the roots phase) or one body key examined (the orphan phase). Without `limit`, one call runs slices until done: the same end state as today, in bounded transactions instead of one.
- **`after`** is the resumption key the previous call returned, in the field spec 176 adds to `Result`. A call that finishes returns no key. A malformed key, or a key minted for another mount, is `invalid`.
- **The purge arm** (any address other than the trash view) is unchanged: one wholesale transaction. `limit` or `after` at such an address is `invalid` with a detail naming the trash view.

[NEEDS CLARIFICATION: keep the purge arm whole-batch (the lean: the caller chose the subtree, and its delete was one transaction of the same size), or slice it too, leaves first by `path` descending so every commit leaves a consistent tree?]

### 5.2 Phase one: expired roots

```sql
SELECT <snapshot columns> FROM vfs_entries
WHERE deleted_at < :cutoff AND trash_root_id = entry_id
ORDER BY deleted_at
LIMIT :slice
```

- EXECUTED on SQLite: the plan is `SEARCH vfs_entries USING INDEX ix_vfs_entries_deleted_at (deleted_at<?)`. Ordering by `deleted_at` alone matters: adding `entry_id` as a tie-break made SQLite sort every row of the oldest delete batch (`USE TEMP B-TREE FOR LAST TERM OF ORDER BY`).
- No position is needed in this phase. A purged root is gone, so the next slice's select starts at the oldest root that remains. A root a rival revived is no longer expired. Each slice therefore removes at least one root or ends the phase.
- Each slice purges its roots through `_purge` with the `still_tombstoned` proof, exactly as today, then `bump_many` on their parents. The unit of a slice is a whole root set: a set's delete was one transaction (ADR 087 pin 7, whole-batch), and its purge is one too, so a `restore` between slices never revives half a set.
- Observations are each purged root, in `deleted_at` order across calls and `path` order within a slice.

### 5.3 Phase two: orphans, in key ranges

The orphan pass covers `vfs_content`, `vfs_blobs` and, new here, `vfs_versions` with `vfs_version_subjects` (keyed by the same `entry_id`). Each family is walked by its own key, `entry_id`, in windows, so no statement scans a whole table (study 04 P2):

1. **Window**: `SELECT entry_id FROM <family> WHERE entry_id > :after ORDER BY entry_id LIMIT :slice`. EXECUTED on SQLite for `vfs_content`: `SEARCH ... USING COVERING INDEX sqlite_autoindex_vfs_content_1 (entry_id>?)`. For `vfs_versions` the select is `DISTINCT entry_id` over its primary key prefix; rows visited are the window's files' version rows, and the docstring says so.
2. **Anti-join inside the window**: `SELECT entry_id FROM vfs_entries WHERE entry_id IN (:window)` (one membership chunk), and the difference in Python names the candidates.
3. **Delete with re-proof**: `DELETE FROM <family> WHERE entry_id IN (:candidates) AND created_at < :fence AND NOT EXISTS (SELECT 1 FROM vfs_entries e WHERE e.entry_id = <family>.entry_id)`. The 24-hour `_ORPHAN_AGE_FENCE` is unchanged; each reclaim is the same `internal` warning as today.

At most three statements per family per slice. When a window returns fewer keys than `:slice`, the family is done and the next one starts at the beginning.

### 5.4 The key

The key is an opaque, URL-safe string. Only the backend that minted it reads it. Inside, it names the mount (`vfs_meta.mount_identity`), the phase (`roots`, `content`, `blobs`, `versions`) and, for an orphan phase, the last `entry_id` examined. Its envelope (prefix, encoding, the `Result` field it rides) is spec 176's; this spec adds only the payload.

```python
# storage/backends/database/trash.py
class SweepMark(NamedTuple):
    """Where a sliced retention sweep stands: the mount, the phase, and the last key an orphan window examined."""

    mount: str
    phase: Literal["roots", "content", "blobs", "versions"]
    after: str | None
```

### 5.5 Statements per call

With `limit = L` and budget `B = membership_budget`, a call runs at most `ceil(L / B)` slices. A roots slice issues a constant number of statements plus `ceil(set rows / B)` per family delete inside `_purge`; an orphan slice issues at most three per family. None of these numbers depends on how many expired roots or orphans the mount holds. The criterion pins the count at landing by equality across garbage sizes, never by a number guessed here.

## 6. The garbage gauge

```python
# storage/protocol.py
@runtime_checkable
class SupportsGarbage(Protocol):
    """Optional: a cheap count of what a mount's cleaners would find, for the job that schedules them."""

    async def garbage(self) -> Result: ...
```

`DatabaseStorage.garbage()` issues exactly two statements in one read transaction and returns `Result(ops=("garbage",), garbage={...})`:

| Statement | Fields | Access path |
|---|---|---|
| 1. `SELECT count(*), sum(CASE WHEN trash_root_id = entry_id ...), sum(CASE WHEN deleted_at < :cutoff ...), min(deleted_at) FROM vfs_entries WHERE deleted_at > :floor` | `tombstoned_rows`, `tombstoned_roots`, `expired_rows`, `oldest_tombstone` | The `deleted_at` index. EXECUTED on SQLite: `deleted_at IS NOT NULL` with the extra columns planned as `SCAN vfs_entries`; the range spelling `deleted_at > :floor` planned as `SEARCH ... USING INDEX ix_vfs_entries_deleted_at`. Rows visited: the tombstones. |
| 2. `SELECT count(*), sum(CASE WHEN is_snapshot ...), sum(CASE WHEN packed ...), sum(size_bytes), sum(stored_bytes) FROM vfs_versions` | `version_rows`, `version_snapshots`, `version_unjudged`, `version_logical_bytes`, `version_stored_bytes` | A scan of `vfs_versions` (EXECUTED: `SCAN vfs_versions`). Rows visited: all version rows. The docstring says so; engine statistics are the future direction. |

- `:cutoff` is the mount's retention cutoff (`trash_days`), so `expired_rows` is what one full retention sweep would reclaim now. `:floor` is the Unix epoch; no tombstone predates it, and every engine's timestamp type holds it.
- `version_unjudged` counts rows pack has not judged; with `PACK_HOT_ROWS = 1` it is at least one per file with history, by design.
- `version_stored_bytes` is why `stored_bytes` exists (§9): it is the one number that shows pack working. Summing `length()` of text and binary columns is not portable (`LEN` on SQL Server counts characters and trims trailing spaces; Oracle needs LOB functions).
- Orphans are not counted. Counting them is the anti-join the sliced sweep exists to bound.

**Where the gauge lives.** It is a storage-level maintenance read, beside `reindex()`, outside the router and outside the gate. Reasons: its counts are mount-wide, and ADR 065 pin 5 rules that statistics are computed over the caller's visible set, so a routed, authority-scoped gauge would have to refuse every caller who cannot see the whole mount; the deployment job that runs `reindex()` and `sweep()` already holds the storage object; and a storage method can never reach an agent surface, by construction.

[NEEDS CLARIFICATION: the gauge as a storage-level method beside `reindex()` (the lean), or a routed developer-plane verb (`DEVELOPER_OPS`, gated at `read_write` over the whole mount, like sweep's retention arm), or a row in a `/.vfs` view per ADR 082 (spec 169's territory)?]

## 7. The history read

### 7.1 `versions(path)`

```python
# base.py
async def versions(
    self,
    path: str,
    *,
    after: str | None = None,
    limit: int | None = None,
    authority: Authority | None = None,
) -> Result:
    """The version rows of the file at *path*, newest first, a page at a time."""
```

- **Name.** `versions`, a plural noun like `grants`. It avoids `history`, which is a bash builtin the shell's program table (spec 167) would otherwise shadow, and a field of spec 148's session.
- **Op class.** `"versions"` joins `Op`, `READ_OPS` (it must work on a read-only mount) and `VERB_RUNGS` as `Needs("read")`. It is not in `DEVELOPER_OPS`: agents may read history.
- **Protocol.** A new optional family, `SupportsHistory`, with `versions(*, path, after, limit, authority)`, added to `_FAMILY_OPS` as `{"versions"}`.
- **Rows.** One `Observation` per version row: `path` (the file's current path), `kind="file"`, `version` (the label), `content_hash`, `size_bytes`, `source` (`"bytes"` when `data` is set, else `"text"`), `created_at`, and the new `actor` (§9). The `populated` mask names exactly these. `is_snapshot`, `packed` and `stored_bytes` are storage facts and never project.
- **The current body is not a row.** `versions` lists what writes replaced. The current state is `stat`'s row, and its `version` is the label `read(path, version=N)` accepts for the live body.
- **Order and key.** Newest first, keyset on `version_number` descending. The key carries the file's `entry_id` and the last label returned. A key whose `entry_id` is not the file now at `path` (it was deleted and a new file took the name) is `invalid`, with a detail that says to start again. The default page is `HISTORY_PAGE_ROWS = 100` rows, or spec 176's default page size if it sets one; the same maximum as 176's `ls`.
- **One page, two statements** past the gate: resolve the entry under the caller's view, then

  ```sql
  SELECT version_number, content_hash, size_bytes, created_at, actor,
         CASE WHEN data IS NULL THEN 0 ELSE 1 END
  FROM vfs_versions
  WHERE entry_id = :e AND version_number < :after
  ORDER BY version_number DESC LIMIT :limit
  ```

  EXECUTED on SQLite: `SEARCH vfs_versions USING INDEX sqlite_autoindex_vfs_versions_1 (entry_id=? AND version_number<?)`. Rows visited per page are bounded by `limit`, whatever the file's history.

[NEEDS CLARIFICATION: the history verb's name. `versions` is the lean (it keeps the bash `history` builtin free for the shell); `history` is the name the kernel memo used.]

### 7.2 `read(path, version=N)`

- `read` gains `version: int | None = None`, single-path form only (`OnlyWith("version", "path")` in `params.py`; with `observations=` it is `invalid`, because an observation's `version` field means something else today).
- The router refuses `read(version=)` as `unsupported` on a mount whose `capabilities()` lack `"versions"`, before dispatch.
- `N` equal to the entry's current `version`: the live body, exactly as `read(path)`.
- Otherwise one statement fetches the chain from the nearest snapshot at or below `N`:

  ```sql
  SELECT version_number, is_snapshot, content, version_diff, data, content_hash
  FROM vfs_versions v
  WHERE v.entry_id = :e AND v.version_number <= :n
    AND v.version_number >= (SELECT coalesce(max(s.version_number), 0) FROM vfs_versions s
                             WHERE s.entry_id = v.entry_id AND s.is_snapshot = :true
                               AND s.version_number <= :n)
  ORDER BY v.version_number
  ```

  EXECUTED on SQLite: two primary-key searches, no scan. At most ten rows.
- `Version.reconstruct` rebuilds the text and checks `content_hash`. A bytes row returns its `data`, hashed the same way. Bodies at or above the write path's offload threshold are reconstructed and hashed through `call_offloaded`, as spec 175 does for `read`.
- If the chain does not start at a snapshot (a pack landing raced the statement on an engine without statement-level snapshots), the read runs the statement once more. Pack only turns snapshots into diffs, so the second read finds an earlier snapshot. A second miss, a failed diff, or a hash mismatch classifies with spec 175's integrity kind, never as success.
- No row labelled `N`: `not_found`, with detail "no version N". Gaps in labels are expected (ADR 017 pin 2) and are not errors of their own.
- The row returned carries `version=N`, the body, and the same fields `versions` returns.

### 7.3 Rights

- Both reads judge the file's **current path** at the `read` rung, through the same `_viewed` gate `read` uses. History is served under today's grants, never the grants in force when a version was written. That is ADR 064 pin 6's rule for revert (Plan 9's dump is served under the same permissions), applied to reading.
- A path the caller cannot see answers `not_found`, the same answer an unknown path gets (ADR 065 pin 1). A path the caller can list but not read is a classified refusal (ADR 065 pin 2).
- A tombstoned file answers as `read` does: `not_found` with `data["vfs.trashed"] = true`, so the caller knows `restore` applies (ADR 074 item 2).

[NEEDS CLARIFICATION: should a tombstoned file's history be readable without a restore (for audit), or answer `not_found` with the trashed hint as `read` does (the lean)?]

### 7.4 What the minimal shape leaves out

- `actor` is the one attribution column shown. `subjects`, `provenance`, `source_identity` and `grant_revision` stay in storage.
- No bodies in the `versions` listing; a body is one `read(path, version=N)`.
- No `lines` column: `Observation` has no `lines` field today, and adding it is a change to `stat` as much as to history.
- No diff-between-two-versions verb.

[NEEDS CLARIFICATION: is `actor` visible at the `read` rung (the lean, as `git log` shows authors to any reader), and do `subjects`, `provenance`, `source_identity` and `grant_revision` join the row, and at which rung?]

[NEEDS CLARIFICATION: the rest of the shape. Bodies inline in a `versions` page (`columns={"content"}`), a `lines` field on `Observation`, and a `diff` view between two versions are all left out here. Which, if any, belong in this spec rather than a later one?]

**A known limit of the row type.** `Result`'s set algebra keys rows by path (`envelope.py`, `_as_dict`, `__or__`). Every row of a `versions` page has the same path, so `|` or `-` over two such pages fuses them. A single `versions` call is unaffected (one mount, one `Result`, no merge). The docstring of `versions` says so; changing the algebra's key is out of scope.

## 8. Integrity (with spec 175)

- **Verify on read.** `read(path, version=N)` is a read, so ADR 087 pin 9 binds it: the reconstructed body is hashed and compared, and a mismatch is an error with spec 175's integrity kind. The hash is `hashlib`, as pin 9 rules.
- **Pack is a partial scrub.** Pack hashes every cold row it reads. A snapshot that does not match its `content_hash`, or a judged chain that does not reconstruct, is reported as a warning with spec 175's integrity kind and `data={"entry_id": ..., "version": N}`. Pack marks a rotten row judged and keeps it whole, so it is reported once; the row after it stays whole too (rule 5), so no diff is ever built on rotten text. Pack never repairs.
- **The scrub covers version rows** (study 05 §2.9). A diff row is verified by reconstructing it. Rebase note for spec 175: scrub each file's chain in label order, carrying the text forward, so a chain of ten rows costs ten applications, not fifty-five.
- **Caches.** A version's text is immutable under pack: pack changes how a row is stored, never what it reads as. A cache keyed by `(entry_id, version)` stays valid across a pack.

## 9. Schema and model changes

| Change | Where | Notes |
|---|---|---|
| `vfs_versions.packed` `Boolean NOT NULL DEFAULT false` | `models/rows.py` | Pack's durable mark. |
| `vfs_versions.stored_bytes` `Integer NOT NULL DEFAULT 0` | `models/rows.py` | UTF-8 bytes of the stored payload: the body for a snapshot, the diff for a diff row. Same type as `size_bytes`. |
| Index `ix_vfs_versions_packed (packed, entry_id)` | `models/rows.py` | The work list (§3.3). |
| `SCHEMA_FORMAT_VERSION` to the next value at landing (176 and 177 bump it first) | `models/rows.py` line 139 | First touch refuses a format-23 mount (`engine.py` line 568); greenfield, no migration. |
| `VERSION_ROW_ONLY_COLUMNS` gains `packed`, `stored_bytes` | `models/rows.py` line 102 | Storage bookkeeping the `Version` model never holds, like `entry_id`. |
| The `vfs_versions` comment names the pack phase and the chain law | `models/rows.py` lines 528–534 | Replaces "the batch pack verb". |
| The mint sets `packed=False`, `stored_bytes=size_bytes` | `versions.py` `_version_row` | No new statement. |
| `Observation.actor: str \| None` | `models/entry.py` | A mirror of `Version.actor` in `OBSERVATION_MIRROR_OWNERS`. Rendered only when populated. |
| `PACK_HOT_ROWS`, `PACK_MAX_BODY_BYTES`, `PackRow`, `PackDecision`, `PackPlan`, `plan_pack` | `models/versioning.py` | `create_version` and `VersionRecord` retire. |
| `"versions"` in `Op`, `READ_OPS`, `VERB_RUNGS`, `PARAMS`, the default projection | `ops.py`, `params.py`, `results/projection.py` | Drift tests follow. |
| `version` on `read`; `limit`, `after` on `sweep` | `params.py`, `base.py`, `storage/protocol.py` | `limit` is an `int` with minimum 1 and maximum `INT_CEILING`. |
| `SupportsHistory`, `SupportsGarbage` | `storage/protocol.py` | `SupportsHistory` joins `_FAMILY_OPS`. |

## Scope

**In:** everything above.

**Out:**

- A retention window that deletes old versions. Clay's decision is to keep the full history; a window stays a possible future setting, never a default.
- A Rust diff kernel (follow-on, per the marker in §2).
- Changing the diff law's context size (EXECUTED: context 0 breaks today's `apply_diff`).
- Content-addressed dedup of identical bodies across versions or files.
- Orphan chunk, segment and edge rows; `reindex`'s re-convergence passes own derived state.
- `restore` of an old version as a verb. Revert stays `read(path, version=N)` then `write`, under current grants (ADR 064 pin 6), and with spec 174 the write carries `if_version=`.
- A ranged read of an old version (spec 178 composes later).
- Exposing `versions` on the MCP tool or the CLI (spec 171 and spec 167 decide their own projections; see the rebase notes).

## Acceptance criteria

Counts and states, never clocks. Every criterion runs on the SQLite leg and on every real-engine leg (Postgres, MariaDB, SQL Server, Oracle) through `tests/support/storage_contract.py` or a database test marked for the engines. The heavy corpora are marked `slow`.

**Pack**

1. **Compression on the probe's corpus, edited.** Study 04's 1,000 files, with bodies of 20 lines, `"".join(f"row {i} line {k} gen {g if k == g % 20 else 0}\n" for k in range(20))` for file `i` at generation `g` (so each rewrite changes one or two lines), written at `g = 0` and rewritten at `g = 1, 2, 3`, then `reindex`: 3,000 version rows, of which exactly 2,000 are snapshots and 1,000 are diffs. `sum(stored_bytes)` after pack is at most 0.80 of the sum before it (EXECUTED in simulation: 1,014,940 of 1,283,400 bytes, 0.791).
2. **Byte-for-byte.** After criterion 1, all 3,000 versions are read back with `read(path, version=N)`. Every body's sha256 equals the row's `content_hash`, and equals the body that write replaced (kept by the test before pack ran): 3,000 matches, 0 mismatches.
3. **Pack never grows history.** Study 04's literal corpus (every line changes each rewrite): 3,000 rows, 3,000 snapshots, 0 diffs, stored bytes 833,400 before and after.
4. **The cadence.** 100 files of criterion 1's bodies rewritten 25 times (`g = 1 … 25`): exactly 400 snapshots and 2,100 diffs after one `reindex`. Reading any version applies at most 9 diffs (spied `apply_diff` calls per read: maximum 9).
5. **Incremental equals whole.** The criterion 4 corpus packed after every rewrite (25 `reindex` runs) ends with the same form for every row as one `reindex` at the end.
6. **Idempotent.** A second `reindex` with no write between judges 0 rows and issues 1 pack statement (the empty work list).
7. **Bytes.** A file whose versions alternate text, bytes, text, text: the bytes row stays a `data` snapshot, the text row after it stays a snapshot, the next text row may be a diff, and all four read back byte for byte.
8. **Rot.** One cold snapshot's `content` changed by direct SQL: pack leaves that row and the next one whole, lands no diff that uses them, and reports exactly 1 warning with spec 175's integrity kind naming the entry and version. `read(path, version=N)` of that row is an error, never success.
9. **Resumable.** A failure injected at the seam `pack:before-land` on the second slice: the next `reindex` finishes, the final forms equal an uninterrupted run's, and no row is landed twice (count of landed updates equals the count of judged rows).
10. **Lease.** With `lost` set before a landing, pack lands nothing after it (spied: 0 landing statements).
11. **Bounded.** 10,000 files, two rewrites each, on every engine leg: every pack statement's `IN` list is at most one `membership_budget` chunk and every landing payload at most `BLOB_PAGE_BYTES` (spied); the pack step's statement count equals the count predicted from its pages and slices.
12. **Hands off.** During the pack step, 0 statements name `vfs_content` or `vfs_blobs` (statement table inspected), and no column other than `is_snapshot`, `content`, `version_diff`, `stored_bytes` and `packed` changes on any version row (row snapshot diff before and after).
13. **The mint after pack.** A write after pack mints one snapshot row with `packed = false` and `stored_bytes = size_bytes`, and the statement count of a 1,000-file overwrite is unchanged from today.

**Sweep**

14. **Bounded and flat.** With 1,000 and with 5,000 expired single-file roots, `sweep(limit=100)` returns 100 observations and a key, and issues the same statement count per call at both sizes (counted, equal).
15. **One transaction per slice.** With the profile narrowed to `in_list_budget=100` (the way `tests/storage/database/test_graph.py` narrows it), 300 expired roots and `limit=300`: the roots phase opens exactly 3 transactions (counted `BEGIN`s), each taking the serialization point as its first statement.
16. **Converges.** Calling `sweep(limit=100, after=key)` until no key returns reclaims every expired root in exactly `ceil(N / 100)` roots-phase calls, then walks the orphan phases; afterwards 0 tombstones past retention remain.
17. **Orphans, windowed.** Three orphan content rows, one orphan blob row and two orphan version rows (entries deleted by direct SQL, `created_at` aged past the fence) are reclaimed with exactly 6 warnings across the calls. No orphan-phase statement returns more than `limit` keys, and an orphan slice issues at most 3 statements per family.
18. **Unlimited keeps today's contract.** `sweep()` with no `limit` reaches the end state today's retention tests pin (`test_trash.py`, `storage_contract.py`) in one call; those tests stay green unchanged except for the order of observations across slices.
19. **Rivals between slices.** A root restored between two slices survives whole; a root revived by `write` between slices survives.
20. **Bad keys.** A malformed key, a key from another mount, and `limit` or `after` at a non-trash address are each `invalid`.
21. **Developer plane.** `sweep` stays in `DEVELOPER_OPS`; the new parameters change nothing on any agent surface (the drift test of the op classes passes unchanged).

**Gauge**

22. `garbage()` issues exactly 2 statements (counted) and its fields equal direct SQL counts on the criterion 1 corpus with 50 tombstones: before pack, after pack (`version_stored_bytes` falls, `version_logical_bytes` does not), and after a full sweep.
23. `garbage()` is not an `Op`, is not routed, and has no `authority` parameter.

**History read**

24. **Paged.** A file with 25 version rows: `versions(path, limit=10)` returns 10, 10 and 5 rows newest first over three calls, the last with no key. Statements per page past the gate are 2, equal for a file with 25 rows and one with 2,500 (counted).
25. **Exact rows.** Each row's `populated` mask is exactly `path`, `kind`, `version`, `content_hash`, `size_bytes`, `source`, `created_at`, `actor`, and `actor` equals the writer's `authority.actor.sub` (`None` under the system actor).
26. **Hidden is absent.** For a caller who cannot see the path, `versions` and `read(version=)` answer the same kind and message as for a path that does not exist. For a caller holding only `list`, both are a classified refusal.
27. **Every label.** `read(path, version=N)` for every label in criterion 24's file returns the right body; `N` equal to the current version returns the live body; `N` in a label gap is `not_found`; `version=` with `observations=` is `invalid`.
28. **Tombstoned.** Both reads of a tombstoned file are `not_found` with `vfs.trashed` set.
29. **Race.** A pack landing injected between the anchor and the chain fetch (seam `versions:after-anchor`) yields the right body after exactly one re-read.
30. **Capability.** `read(path, version=1)` on a backend whose `capabilities()` lacks `"versions"` is `unsupported` with 0 storage calls (spied).

**Always**

31. `scripts/ci.sh` is green at 100% coverage after every task. The four engine legs are green before tasks 3, 5 and 6 land.

## ADR amendments this spec needs

- **ADR 017 pin 4:** "the pack verb" becomes the `pack` phase of `reindex` (ADR 087 already says so). Pin 4 gains the chain law of §2: a diff lands only when it is smaller than the body and has reconstructed it by hash; bytes rows and the row after a bytes row stay whole; the newest `PACK_HOT_ROWS` rows stay whole; a body above `PACK_MAX_BODY_BYTES` stays whole. The interval stays 10, counted in stored rows. `create_version`'s label arithmetic, which contradicted the pin, is retired.
- **ADR 017, "Committed to":** "the pack verb consumes and preserves gapped labels" holds; add that pack never deletes a row and never changes a row's metrics or attribution.
- **ADR 027 pin 3 and ADR 074 item 8:** the retention arm runs in slices, each its own transaction under the serialization point, and takes `limit=` and `after=`. Without `limit`, one call still reclaims everything, in bounded transactions. The orphan reclaim runs in `entry_id` windows and covers version rows. Observations come in `deleted_at` order across slices.
- **ADR 087 pin 7:** `sweep` is a resumable verb from this spec on; its purge arm stays whole-batch (pending the §5.1 marker).
- **ADR 087 pin 11:** the history read is named `versions(path)` with `read(path, version=N)` (pending the §7.1 marker); the gauge is a storage-level maintenance read beside `reindex()` (pending the §6 marker).
- **ADR 064:** version rows gain two storage columns, `packed` and `stored_bytes`; no attribution column changes, and pack rewrites none.
- **ADR 015 / 034 (the mirror table):** `Observation.actor` mirrors `Version.actor`.

## Rebase notes for specs 167/171/172 (and 175/176)

- **167 (the shell):** the history verb is named `versions` so that bash's `history` builtin keeps its meaning in the program table. If 167's catalog maps a program to the verb, it is `versions`. `sweep` stays `unrecognized` on `cli`, as 167 criterion 12 pins; its new arguments change nothing there.
- **171 (MCP adapter):** `versions` is a read op: it projects as a tool with `readOnlyHint` and `idempotentHint`, and `read`'s tool gains an optional `version` argument. `sweep` stays off the wire (`DEVELOPER_OPS`). `garbage()` is not an op and never reaches the wire.
- **172 (WASI runtime):** a version's text is immutable under pack, so a guest cache keyed by `(entry_id, version)` stays valid across a pack; ADR 087's warning about `(path, version)` after a rename or a sweep stands.
- **175 (integrity):** the scrub walks each file's version chain in label order carrying the text forward (§8). Pack's rot warning and `read(version=)`'s mismatch use 175's integrity kind.
- **176 (cursor):** the sweep key and the `versions` key ride 176's `Result` field and its `after=` / `limit=` grammar; this spec adds only their payloads (§5.4, §7.1).

## Landing notes

(Filled in on landing, per task.)
