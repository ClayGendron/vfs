# Write takes preconditions and an append

This spec is not built and has had no review. It replaces the draft at `context/specifications/active/174-write-preconditions-and-the-guarded-append/spec.md`, which was cut on 2026-10-24 against commit `ba77449`. The design is the draft's. Every fact in it was checked against `dev` at `93f3d297` on 2026-11-20, and its probes were run again that day. What moved since the draft is listed under "What changed since the draft".

## The outcome wanted

A caller that reads a file, changes it and writes it back can say which version it read, and the write is refused when the file has moved on. A caller can create a file only if nothing is there. A caller can append to a file in one call, and concurrent appends all land. A write of the body a file already holds writes nothing.

## Terms

- **Precondition.** A condition a caller attaches to a write. When it is false, nothing is written and the call is refused.
- **Snapshot.** The one bounded read every write batch takes before it decides anything, `_fetch_committed` in `writes.py`. It holds each target's row, its ancestors and any tombstone.
- **Plan.** The pure Python pass that judges every entry against the snapshot, `WritePlan` in `staging.py`. It runs no SQL. A plan with any error runs no mutation statement.
- **Guard.** The terms `version = base AND path = ...` on the material `UPDATE`. `base` is the version the snapshot saw. A rival that committed after the snapshot makes the guard match no row.
- **Window.** The time between the snapshot and the guarded `UPDATE`.
- **Mutation statement.** An `INSERT`, `UPDATE` or `DELETE`.
- **Tombstone.** A deleted row that stays at its path with `deleted_at` set. It is absent to every read, and a `write` at its path revives it.
- **Unchanged.** The status a write reports when the body it carries is the body the row already holds.
- **Rung.** A step of the access ladder `none < list < read < add < contribute < read_write`.
- **Seam.** The storage protocol, `SupportsMutation.write` in `storage/protocol.py`.

## What the code does today

Run on 2026-11-20 on a SQLite file, at `dev` `93f3d297`. Statement counts leave out `BEGIN`, `COMMIT`, `PRAGMA`, `SAVEPOINT`, `RELEASE` and `ROLLBACK`.

| Fact | How it is known |
|---|---|
| Two callers read `/log.txt`, and each writes it back with one more line. Both report success. One line survives. | Run. |
| 20 concurrent read-then-write appends: 20 report success and 1 line survives. The same 20 through `edit` keep 20. | Run. |
| A rewrite of a file with its own body reports `updated`, adds one to the version, and mints no version row. At the seam, as the system actor, it issues 7 statements: the snapshot, the guarded `UPDATE`, the revision read, the body read for the mint, two body `DELETE`s and the content `INSERT`. Through the kernel as the default caller it issues 13. | Run. |
| A rewrite with a new body issues 8 statements at the seam and 15 through the kernel. | Run. |
| An identical rewrite of 1,000 files updates 1,000 entry rows, deletes and inserts 1,000 content rows, and moves every version from 1 to 2. | Run. |
| The update of a row clears its `chunked`, `encoded` and `indexable` marks and sets `updated_at`, so an identical rewrite sends the file through the index again. | Read, `_material_values` in `writes.py`. |
| An `edit` whose steps cancel out reports `updated` and adds one to the version. | Run. |
| An `edit` with `old == new` is refused `invalid` before any storage is called. | Run. |
| `write` takes no precondition. Its arguments are `entries`, `path`, `content`, `data`, `overwrite`, `parents` and `authority`. | Read, `AsyncVirtualFileSystem.write` in `base.py`. |
| `overwrite=False` refuses a live file with `exists`. The refusal carries no `data`. It does not refuse a tombstone, which it revives. | Run, and read in `WritePlan.put_file`. |
| The snapshot does not fetch `content_hash`. | Read, `_fetch_committed`. |
| `conflict` is documented to carry `version` in its `data`. No producer sets it. | Read, `results/kinds.py` and `_conflict` in `writes.py`. |
| A guard that matches no row is a retryable `conflict` on SQLite, Postgres, SQL Server and Oracle. On MariaDB and the generic floor the whole call runs again from a new snapshot. | Read, `_classify_guard_misses` and the `guard_miss` field in `dialects.py`. |
| A write runs at REPEATABLE READ on Postgres and MariaDB. The topology verbs run at READ COMMITTED there, so that their checks read what a rival committed. | Read, `op_execution_options` and `topology_execution_options`. |
| Every writer transaction runs inside the label fence, and each staged row is admitted against the caller's rights. | Read, `fenced`, `admit_staged` and `admit_landed` in `authorized.py`. |

## The problem

A write is last writer wins, and it says so to nobody. Two agents that edit one file by reading and writing lose one agent's work with two reports of success. A log that several callers append to keeps one caller's lines. Nothing in the result lets either caller find out.

A second cost sits beside it. A pipeline that ingests a folder again, where most files did not change, pays for every file as if it had: a row update, a body delete and insert, and a second trip through the index.

## Decisions

### 1. `write` takes `if_version`, `if_versions`, `if_absent` and `append`, and `overwrite` leaves

```python
async def write(
    self,
    entries: Iterable[Entry] | None = None,
    *,
    path: str | None = None,
    content: str | None = None,
    data: bytes | None = None,
    if_version: int | None = None,
    if_versions: Mapping[str, int] | None = None,
    if_absent: bool = False,
    append: bool = False,
    parents: bool = False,
    authority: Authority | None = None,
) -> Result: ...
```

Four public methods take this shape: `AsyncVirtualFileSystem.write`, `AsyncSession.write`, and the two in `sync.py`, `VirtualFileSystem.write` and `Session.write`. The two session methods take no `authority`.

- `if_version` is the precondition of the single form. `if_versions` is the precondition of the batch form, a mapping from path to expected version. A path with no key has no precondition.
- `if_absent=True` is today's `overwrite=False` under one name for one fact. The default replaces an occupant, as `overwrite=True` does today. No alias is kept, because the design is not released.
- `append` and `if_absent` apply to every entry of the call.

The seam takes one shape for both forms.

```python
async def write(
    self,
    *,
    entries: list[Entry],
    if_versions: Mapping[Path, int] | None = None,
    if_absent: bool = False,
    append: bool = False,
    parents: bool = False,
    authority: Authority | None = None,
) -> Result: ...
```

The kernel turns `if_version=N` into `if_versions={path: N}`. A storage never sees the single form. Inside `writes.py` the word `overwrite` stays where it means "a create may land on an occupant", which `edit` and `mkdir` pass too.

Reason: a version is the one coordinate every reader already holds, since every row a read returns carries it. A model can copy a version number from a result. It cannot work out a hash.

### 2. The batch precondition is a mapping keyed by path

| Shape | Verdict |
|---|---|
| A field on `Entry` | Rejected. An `Entry` is the stored file, and a caller cannot author its version. A copy between mounts passes rows read from another mount, and a version carried on them would refuse the copy. |
| A list beside `entries` | Rejected. Position would carry the meaning. The kernel sorts a batch by depth and splits it by mount, and `entries` is an iterable read once. |
| A mapping from path to version | Chosen. It is keyed by the one identity an entry has, it survives the sort and the split, and the plan reads it from a dictionary at no statement. |

One call cannot mix appended rows with plain rows, or create-only rows with plain rows. Each is its own call, and so its own transaction on each mount.

### 3. The rules at the gate

Each is refused with `invalid`, names the argument, and is judged before any storage is called.

| Rule | Where |
|---|---|
| `if_version` is an integer from 1 to `INT_CEILING` | a `ParamSpec` in `params.py` |
| `if_versions` is a mapping of text to integers from 1 to `INT_CEILING` | a new `ParamKind`, checked key by key |
| `if_version` goes with the single form only, and `if_versions` with `entries` only | two shape rules |
| `if_absent=True` with `if_version` or `if_versions` | a rule: an absent row has no version |
| `if_absent=True` with `append=True` | a rule: an append to an absent path already creates |
| every key of `if_versions` names a file entry of the batch, once it is resolved as the entry paths are | `_route_entry_batch` in `base.py` |
| under `append=True` every entry is a file | `_route_entry_batch` |

The kernel resolves each key as it resolves each entry path, matches keys to entries, and hands each mount the keys of its own entries with the mount prefix taken off. A batch over two mounts stays whole on each mount and not across them, which is today's rule for any refusal.

### 4. The plan judges each entry in one order

The first step that fails gives the answer. No step issues SQL. The rights gate runs before the plan, as today, so a caller who may not touch a row never reaches a judgment that describes it.

1. The address gates, as today: the trash view, the key budget, the engine's value cap, the parent rule.
2. `if_absent`: any live occupant, file or directory, is `exists`. This comes before the kind check, as `O_EXCL` answers `EEXIST` over a directory.
3. The occupant's kind, as today: a directory at a file's target is `wrong_kind`.
4. An expected version against no live row is `not_found`. A tombstone is `not_found` with the trashed hint. A precondition never revives.
5. Stage. An append composes its body first.
6. Settle, once, after every entry is staged. A staged update whose final body is the committed body is dropped and reports `unchanged`. Each update that is left and whose expected version is not the committed one is refused `conflict`.

| Target at the snapshot | no precondition | `if_version=N` | `if_absent=True` | `append=True` |
|---|---|---|---|---|
| absent | create | `not_found` | create | create, the tail is the body |
| tombstoned file | revive | `not_found`, trashed hint | revive | revive, the tail is the body |
| live file, same body | `unchanged` | `unchanged`, whatever `N` is | `exists` | `unchanged` only when the tail is empty |
| live file at version `N`, new body | update to `N+1` | update to `N+1` | `exists` | update: old body and tail |
| live file at another version, new body | update | `conflict`, with the version | `exists` | update |
| live directory | `wrong_kind` | `wrong_kind` | `exists` | `wrong_kind` |

### 5. A write of the body a row already holds is `unchanged`

A staged update of a live row whose final material equals the committed material is dropped from the plan. Its entry reports `status="unchanged"` with the committed version. Material is four columns: `kind`, `source`, `content_hash` and `mime_type`.

- The snapshot gains `content_hash`. It is one more column on a read that already runs.
- `WritePlan.settle()` is new. It runs in `_finish`, after the staged rows are admitted against the caller's rights and before the errors are looked at. The order matters: `unchanged` tells a caller that its body equals the stored one, so only a caller who may change the row hears it.
- Settle sees the final staged state. A batch that writes `/a` as B and then back to its stored A is `unchanged`.
- A revive is never `unchanged`, since it clears a tombstone. A create is never `unchanged`.
- `edit` runs through `_finish` too. An edit whose steps cancel out is `unchanged`.
- With every row dropped the plan is empty and `_apply` returns at its first line. A batch that is all unchanged issues no mutation statement at any size.

Reason for `mime_type`: a text write with no declared type stores none, so a caller who declares one on the same body is changing the row. Reason for `source`: the text `"hi"` and the bytes `b"hi"` hash the same, and a text row rewritten as bytes is a different row.

Reason for the rule: it is what makes `if_version` safe to send twice. A caller that lost the reply to its own write and sends it again meets its own body and hears `unchanged`, not `conflict`.

### 6. An expected version is judged at the snapshot and carried by the guard

- **When it holds.** `StagedEntry` gains `expected_version`. When it equals the snapshot's version, the staged update's `base_version` already equals it, and the guard that is already on the `UPDATE` compares the row with the caller's version. No statement is added at any batch size.
- **When it is stale.** Settle refuses `conflict` before `_apply` runs, with `data={"version": current}` and `retryable=False`. An identical retry would carry the same stale version, so the instruction is to read again.
- **When the row is missing.** `not_found`, judged from the snapshot. The parent rule is applied as if `parents=False`, so a missing ancestor answers at that ancestor.
- **When the row is a tombstone.** `not_found` with the trashed hint, even where the numbers match. A row beneath a deleted directory keeps its version through the delete, so a number alone cannot tell a tombstone from a live row.
- Every stale row of a batch is listed, and the batch fails whole.

A rival inside the window:

- Where a miss is probed, the probe in `_classify_guard_misses` also selects `version` and `content_hash`. A missed row whose current hash is the staged hash raises `StaleSnapshot`, and the rerun settles `unchanged`: the rival wrote the same body. Every other miss is a `conflict` that carries the current version. It is not retryable for a row with an expected version, and stays retryable for a row without one.
- Where a miss reruns the call, the new snapshot holds the rival's version and settle gives the same two answers.

A replay of one's own write: body X with `if_version=1` lands as version 2, the reply is lost, and the call is sent again. Settle checks `unchanged` before the version, so the answer is `unchanged` at version 2. This is safe. The harm a precondition prevents is erasing a rival's change, and an `unchanged` answer writes nothing.

### 7. `if_absent` creates and never replaces

- A live occupant is `exists`. The refusal carries the occupant's `version` and `content_hash` in `data`, so a caller that lost the reply to its own create can recognise it.
- The same body from another caller is still refused. Otherwise two agents that create one lock file would both hold the lock.
- A tombstone is absent, so `if_absent=True` revives it. Every read already treats the path as empty. The revive is still judged as a restore by the rights gate.
- A directory entry under `if_absent` is `exists` over any occupant, as `mkdir` is without `exist_ok`.
- Two concurrent creates of one absent path both pass the snapshot and both insert. One wins the `(parent_id, name)` index. The loser is classified `exists` by the arbitration code that serves `overwrite=False` today, and its probe gains `content_hash`.

### 8. `append=True` is one read and one write inside one transaction, under a row lock

| Way to append | Verdict |
|---|---|
| The caller loops `read` and `write(if_version=)` | Works with decision 6 alone, and stays the fallback. Each loser pays a whole round trip, and the body crosses the wire twice. |
| The storage appends inside one transaction, under a row lock | Chosen. One call. Rivals queue on the lock. It is how `edit` already keeps 20 of 20. |
| SQL concatenation, `content = content || :tail` | Rejected. A sha256 cannot be extended from a stored digest, and the version mint keeps the old body. Both need the body in hand. |

The transaction, in order:

1. **Lock the targets that exist.** The target paths are sorted and locked with `locked_lookup`, in chunks of the membership budget. An absent target locks nothing. Sorted paths are the lock order every write pass already uses, so an append and a plain write cannot deadlock.
2. **Read the snapshot with bodies, as a second statement.** On Postgres a locking read that waited checks the locked row again and not the joined body row, so one statement could hand back the body a rival just replaced.
3. **Compose each body**, in entry order, through the staged overlay. A path appended twice in one batch appends to its own staged body, as `edit` does.
4. **Stage, settle and apply** as a plain write. The guard still rides the `UPDATE`.

The transaction runs under the topology verbs' isolation pin, READ COMMITTED where a profile declares one, because step 2 must read what was committed after step 1 waited. It takes the writer marker and the label fence, as every write does. It takes no serialization point.

Composing is a pure function beside `edited_entry` in `storage/editing.py`. No stored body leaves the tail as the whole body. Otherwise the two join as bytes. A text row stays text when the joined bytes are UTF-8 with no NUL, and becomes a bytes row when they are not. A bytes row stays bytes. The row keeps its stored `mime_type`.

The composed body is measured as a write's body is: inline below `MEASURE_OFFLOAD_BYTES`, in one offloaded hop at or above it. The mint reuses the body the snapshot read. `StagedEntry` gains `base_data` beside `base_content`, so no old body is read twice.

When a rival beats an append, the append recomputes. It carries the kernel's own precondition and not the caller's.

- Two appends to one absent path both insert. The loser raises `StaleSnapshot`, and the rerun locks the winner's row and appends to it. It is never `exists`, and it never absorbs the winner's row, which would erase the winner's line.
- A guard miss under the lock is not expected. If one happens it raises `StaleSnapshot` on every dialect.
- With `if_version=N` as well, the caller's precondition wins and a mismatch is `conflict`. That is an append that lands at most once.

An append sent twice appends twice. It is the one write that is not the storing of a value.

### 9. A write that removes no stored byte is judged at `add`

`ops.py` gains one constant beside `VERB_RUNGS`.

```python
ADDITIVE_WRITE: Final[Needs] = Needs("add", create="add")
```

The storage passes it to the gate when `append` or `if_absent` is set. A tombstoned target is still judged as a restore.

Reason: an append adds after the last byte and keeps the old body as a version. A create-only write never lands on an occupant. Neither widens what a caller can destroy. An `add` holder who creates over a file hears `exists`, which is the true answer, and not `permission_denied`. `add` sits above `read` on the ladder, so the `content_hash` in that refusal goes only to a caller who may read the row.

### 10. No new error kind, and two kinds carry data

| Refusal | Kind | `data` | `retryable` |
|---|---|---|---|
| expected version stale at the snapshot | `conflict` | `{"version": current}` | no |
| a row with an expected version lost the guard | `conflict` | `{"version": current}` | no |
| a plain write lost the guard | `conflict` | `{"version": current}`, new | yes, as today |
| expected version on no live row | `not_found` | the trashed hint on a tombstone | no |
| `if_absent` over a live row, at the snapshot or at arbitration | `exists` | `{"version": v, "content_hash": h}`, new | no |

A `conflict` is retryable only where the caller stated no precondition, because only there does an identical retry judge afresh and succeed.

### 11. No content-hash precondition is added

An adapter that speaks a protocol with a hash precondition does `stat`, compares the hash, and writes with `if_version`. If the write lands, the row was still at the version whose hash matched, so the pair is correct at the cost of one round trip. Decision 5 already gives the one extra power a hash has, which is that a replay meeting its own body succeeds. An `if_hash` argument can be added later without changing anything here.

### 12. Four landings, in this order

1. `unchanged`. No argument changes.
2. `if_version` and `if_versions`.
3. `if_absent` in place of `overwrite`, with `ADDITIVE_WRITE`.
4. `append`.

Reason: each leaves the tree green and is of use alone. The first makes the second safe to retry. The fourth adds a locking read and an isolation path, so it waits for the engine legs.

## Cost

Costed against the reference deployment in the working agreement.

**Per file write, about 1,050,000 a day.** A plain write, a write with an expected version and a create-only write issue the statements a write issues today. The snapshot reads one more column. The precondition is read from a dictionary.

**An unchanged file.** At the seam an identical rewrite falls from 7 statements to 1 and from two rows written to none. It is also no longer sent through the index, because its `chunked` and `encoded` marks are not cleared. The nightly batch is 1,000,000 files. Each file in it that did not change costs a snapshot row and nothing else, where today it costs an entry update, a body delete and insert, a version bump, and a visit in the next index pass. The share of a nightly batch that is unchanged is an assumption. No measurement exists.

**A stale precondition.** One read and no mutation statement, at any batch size. A 10,000-row batch with one stale key writes nothing.

**An append.** One more statement for each chunk of targets, the locking read. A 10,000-row append at a budget of 1,000 issues ten of them. The snapshot joins the bodies, as an `edit` snapshot does.

**Memory.** An append batch holds every target's old body and composed body in memory, as `edit` does today. Nothing pages them but the membership chunk. The direction, if a measured append workload needs it, is to page the body join by bytes as the mint pages. No cap is declared.

**The lock an append takes.**

| Question | Answer |
|---|---|
| What is locked | The rows the call appends to. No table, no parent row, no other row. |
| When | Before the body is read, after the rights gate. |
| Until | The commit of the call. For one file that is one write. For a batch it is the batch's body. |
| Who waits | Another writer of the same row: a write, an edit, an append, a delete or a move of it. |
| Who does not wait | Every read, list, glob, grep and search. A plain read takes no row lock on Postgres, MariaDB and Oracle. On SQL Server the hint is `UPDLOCK`, which a reader's shared lock passes. On SQLite the writer lock is the database's, taken by every write at its `BEGIN`. |

The working agreement says a lock other callers need is held for the length of a commit and never for a batch's body. An append batch holds its row locks for its body. A plain write batch holds the same locks from its guarded `UPDATE` to its commit, which is most of its body. The append takes them one read and one compose earlier. The callers who wait are writers of the rows the batch is itself rewriting, and nobody else.

## Left as it is

- **`edit`, `delete`, `move` and the rest take no expected version.** An edit's `old` text is its precondition.
- **A request key and an append that lands exactly once.** An append with `if_version` lands at most once, and that is what this gives.
- **`content_hash` on every written row of a result.** It is carried only in the `exists` refusal.
- **A repair of a body that rotted under a hash that still matches.** Today a rewrite of the right body repairs it. After decision 5 that rewrite is `unchanged` and repairs nothing. A check of the hash on read, and a repair that does not go through `write`, are a change of their own.
- **A capability name on the seam for append.** The database storage is the only storage, and the in-memory storage is the same class.
- **Mixing appended, create-only and plain rows in one call.**

## Tests

Each is written and seen failing before the code. Counts are of statements recorded by the `before_cursor_execute` listener `tests/storage/database/test_writes.py` already uses, on a SQLite file, at the seam, as the system actor. Never of time. A row of the storage contract runs on every engine leg.

`unchanged`:

- A rewrite of a text file with its own body is `unchanged`, the version stays, no version row is minted, and one statement runs, the snapshot. The same for a bytes row. Contract row for the state.
- A 10,000-entry identical rewrite reports 10,000 `unchanged` rows and writes no entry row and no content row. Marked `slow`.
- A batch of 3 changed and 3 identical rows updates 3 entry rows, and the 3 identical rows are `unchanged` at their old versions.
- A batch that writes `/a` as B and back to its stored A is `unchanged`.
- The same body with a new declared `mime_type` is `updated`. A text body rewritten as the same bytes is `updated` with `source == "bytes"`.
- An edit whose steps cancel out is `unchanged` and mints nothing. An edit that changes the body keeps its pinned count of 7.
- A revive with the body the tombstoned row held is `updated`, and the row is live after.
- An unchanged row keeps its `chunked` and `encoded` marks and its `updated_at`.

`if_version`:

- With `/a` at version 2, `write("/a", content="x", if_version=1)` fails with one `conflict` at `/a`, `data == {"version": 2}` and `retryable is False`. No mutation statement runs and one statement runs in all. `stat` still shows version 2.
- A passing `if_version=N` is `updated` at `N+1`, and the guard's base parameter is `N`.
- Body X with `if_version=1` lands as version 2. The same call again is `unchanged` at version 2. A different body with `if_version=1` is `conflict` with version 2.
- A rival committed at the `write:before-apply` seam makes a write with an expected version fail `conflict` with the rival's version, and the rival's body survives. A rival that wrote the same body gives `unchanged`. On a leg that probes a miss and on the MariaDB leg that reruns.
- `if_version` on an absent path is `not_found` at the target. Under a missing parent it is `not_found` at the parent, with `parents=True` too. On a tombstoned file it is `not_found` with the trashed hint, and the row stays deleted.
- A 10,000-entry batch with a key for every row issues the same number of statements as the batch without keys, with the membership budget narrowed to 1,000. With one stale key it fails whole with one `conflict` and no mutation statement. Marked `slow`.
- Each rule of decision 3 is refused `invalid` and names its argument: `if_version=0`, `if_version` with `entries`, `if_versions` with `path`, `if_absent` with `if_version`, `if_absent` with `append`, a key that names no entry, a key that names a directory entry, `append` with a directory entry.
- A batch over two mounts with a stale key on one refuses that mount's rows and lands the other's.
- A plain write that lost the guard carries the current version in its `conflict`.

`if_absent`:

- On an absent path it is `created`. On a live file it is `exists` with the occupant's `version` and `content_hash`, and no mutation statement runs. On a tombstoned file it revives the row and keeps its `entry_id`. On a live directory it is `exists`.
- 20 concurrent creates of one absent path: 1 success and 19 `exists`. Contract row.
- A caller who holds `add` on `/drop`, where another owns `/drop/x`: `write("/drop/x", if_absent=True)` is `exists`, and a plain overwrite is `permission_denied`. A caller who holds only `list` gets `permission_denied` for the create-only write, and no `data`.
- `overwrite` is in no `write` signature, not on the seam and not in `PARAMS["write"]`, and the drift tests pass.

`append`:

- On a file that holds `line0\n`, 20 concurrent appends all succeed, the body has 21 lines, and each line appears once. From an absent path the body has 20 lines, at least one rerun is counted on the arbitration path, and none is `exists`. Contract row.
- An append to a bytes row leaves the old bytes and the tail. A text tail on a bytes row appends its UTF-8 bytes. A tail that is not UTF-8 turns a text row into a bytes row. A UTF-8 bytes tail leaves a text row text.
- An append to a directory is `wrong_kind`. An append of an empty tail is `unchanged`.
- A single text append issues 8 statements: the locking read, the snapshot, the guarded update, the revision read, the version insert, two body deletes and the content insert. No second read of the old body.
- A caller who holds `add` appends to another's row. The same caller's overwrite of that row is `permission_denied`, and so is its append to another's tombstoned row.
- A 10,000-entry append with the membership budget at 1,000 issues ten locking reads and one `COMMIT`, holds no `IN` list longer than the budget, and every row ends as its old body and its tail. Marked `slow`.
- A composed body at or above `MEASURE_OFFLOAD_BYTES` is measured in one offloaded hop, and a smaller one in none.
- An append with `if_version=N` on a row at another version is `conflict`.
- While an append holds its row lock, a read of that row, a search, and an edit of another file each return, as the system actor, a named caller and anonymous. On every server engine.

Five tests used a rewrite of the same body to make a row pending again without changing its hash, and were rewritten at the first landing to write the body away and back: `test_a_refresh_of_kept_entries_flips_and_bumps_only`, `test_a_write_during_a_publish_keeps_one_posting`, `test_a_missed_flip_is_stamped_all_the_same`, and `test_same_body_overwrite_skips_the_resplit`, which is now `test_a_body_written_away_and_back_skips_the_resplit`. The fifth, `test_a_same_bytes_overwrite_renders_once_more_and_settles`, is now two: the same bytes keep their rendering, and bytes written away and back render once more. The index's paths for a pending row whose body did not change stay reachable that way, and by a delete and a restore.

Still to be rewritten, at the third landing: the 66 uses of `overwrite=` in 15 files under `tests/`.

## Scope

In: the four arguments on the four public signatures, the params table and the seam; `overwrite` off `write`; `WritePlan.settle` and the `unchanged` rule for `write` and `edit`; the locked append path; `ADDITIVE_WRITE`; the `data` of `conflict` and `exists`; the probe of a guard miss carrying `version`; the tests; the docs.

Out: everything under "Left as it is".

## What the docs must say

- A write of the same body changes nothing and says `unchanged`. The version does not move.
- `if_version` is how a caller that reads, changes and writes back avoids erasing another caller's change. A `conflict` names the version that is there now.
- `if_absent=True` creates a file only where no live file is. A deleted file counts as absent.
- An append is one call, concurrent appends all land, and an append sent twice appends twice.
- `add` lets a caller create files and append to files, and never replace or remove what is stored.

Pages: the docstrings of the four `write` methods, which are the reference page; the `ErrorKind` docstring for the two `data` records; the `Rung` docstring and `documentation/reference/access-levels.md` for `add`; `documentation/how-to/load-a-folder-of-files.md` for a second load of the same folder; the write docstring in `exceptions.py`. Six pages under `documentation/` use the word "overwrite" and are read at the third landing.

## Earlier decisions this reverses

- A decision record on versions says every material write adds exactly one to the version. It stands as written: an unchanged write is not a material write. What changes is that a rewrite of the same body no longer counts as one.
- A decision record on the trash says `overwrite=False` does not refuse a revive. It now reads `if_absent=True`. Added to it: an expected version never revives.
- A decision record on the conflict rerun says a guard miss is classified. An append's guard miss and arbitration loss rerun.
- A decision record on the access ladder gives `add` the creation of new names. `add` now also appends to a row.

## What changed since the draft

- The kernel class is `AsyncVirtualFileSystem`. A synchronous facade exists in `sync.py`, so four methods take the arguments and not two.
- `entries` is an iterable read once. A list beside it was already rejected, and this is one more reason.
- Every writer transaction runs inside the label fence. The append's runner takes it too.
- Bodies are measured in the storage, by `measured_entries`, and `MEASURE_OFFLOAD_BYTES` already lives in `models/version.py`. The draft's move of that constant is done.
- `edit` with `old == new` is refused `invalid`. The draft's test of an unchanged edit used it. The test now uses steps that cancel out.
- The statement counts were run again and are the draft's at the seam: 7 and 8. Through the kernel as the default caller they are 13 and 15, since the rights gate reads first.
- The working agreement's rule for locks is newer than the draft. The append's lock is costed against it under "Cost", and a test that readers do not wait is added.
- The reference pages are generated from docstrings under `documentation/`. The draft named pages under `docs/` that no longer exist.
- The draft's notes for the shell, the WASI host and the adapter specs are not carried. Those specs are unbuilt and under `context/`. What they can use is the surface in decision 1.

## Not checked

- The server engines. Every probe ran on a SQLite file.
- On Postgres at REPEATABLE READ, a rival's commit inside the window can end the guarded `UPDATE` with a serialization failure and a rerun, and not with a guard that matches no row. Both roads are read to end at the same answer. Neither was run.
- Lock escalation on SQL Server under a 10,000-row append. The locking reads are chunked at the `IN` list budget of 2,000, under the 5,000 locks at which one statement escalates.
- SQL Server with `READ_COMMITTED_SNAPSHOT` off. No code under `src/vfs` reads that setting.
- The count of 8 statements for one append is worked out and not run.
- How many existing tests rewrite a body with itself.
- The share of a nightly batch that is unchanged.

## One line

A write can say what it expects to find, an append is one call that loses no line, and a write of the same body writes nothing.
