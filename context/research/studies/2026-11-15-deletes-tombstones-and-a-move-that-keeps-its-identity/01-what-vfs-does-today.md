# Study 01: what vfs does today with a delete, a restore, a revive, a move and a sweep

The developer asked on 2026-11-15 whether tombstones are designed correctly today, after ruling that a move keeps the moved file's identity as POSIX rename does, and that the verb which destroys for good should be called `destroy`. This study answers for the tree as it stands at commit `08c372affd1730739c27aec84b8e94e0d6ef1e87`. It read the trash, staging, topology, write, version, label and rights code and the two retired decision records, and it ran eleven probe scripts, one of them a smoke test, on the in-memory store (`InMemoryStorage`, an in-process SQLite 3.50.4 under SQLAlchemy 2.0.52 and Python 3.13). No pytest, no Docker and no database server ran. Every script and its output is in the `experiments/` folder beside this file, on top of [one shared helper](experiments/probe_common.py); each section links the output it reports. The work took well under the one-hour box and nothing was cut short.

EXECUTED means a command ran here and the claim reports its output. READ means read in a file cited by path and line. INFERRED means this researcher's reasoning from the two.

A term used throughout: a *tombstone* is a row of `vfs_entries` whose `deleted_at` is set. The row stays at its own path. A tombstoned *root* is the row a delete named; its `trash_root_id` is its own id. A *member* is a row tombstoned beneath a root by the same delete; its `trash_root_id` is the root's id. The *trash view* is the address `/.vfs/trash/<path>`, which reads tombstoned rows and stores nothing. A *revive* is a file `write` that lands on a tombstoned file's path.

## 1. The finding in one paragraph

INFERRED from everything below: the tombstone is sound as a way to hide a row and bring the same row back, and it is unsound as a way to free a path. Restore works and returns the same file with its id, owner, history, edges and rights (EXECUTED). Rights are not widened by a delete, a restore or a write at a deleted path in anything probed (EXECUTED). But a tombstone holds its path under both unique keys, and today's design pays for that in four places. A deleted directory's name cannot be used again until it is restored or destroyed. A new file written at a deleted file's path is not new: it takes over the deleted row's id, owner, links and history, and the deleted file can no longer be restored. A move can never replace anything, and the workaround the code documents, delete then move, is refused. And `sweep`, the only way left to free a name, destroys live rows at once with no warning at the same rung as `delete`. The ruling that a move keeps its identity through a replace cannot be built on today's schema; three ways to change the schema are costed in section 13.

## 2. How a deleted row is stored

READ: the entry table declares `entry_id` unique and `path` unique as single columns (`src/vfs/models/rows.py:429` and `:432`) and one named constraint, `UNIQUE (parent_id, name)` (`rows.py:486`). None of the three carries a liveness term. The tombstone is two nullable columns, `deleted_at` and `trash_root_id` (`rows.py:482` to `:485`), each with a plain single-column index (`rows.py:499` and `:500`). The comment above the table says the `(parent_id, name)` key "arbitrates concurrent creates and serves keyset pagination" (`rows.py:419` to `:422`).

EXECUTED ([p07](experiments/p07_listing_cost_and_keys.out), section 1): SQLite reports three unique indexes on `vfs_entries`, `ix_vfs_entries_entry_id`, `ix_vfs_entries_path` and the automatic index for `uq_vfs_entries_parent_name`, and `PRAGMA index_list` reports `partial=0` for every index on the table. So one row holds a path whether it is live or deleted, and one row holds a name under a parent whether it is live or deleted.

READ: this was a deliberate choice. The retired decision record `context/decisions/074-trash-is-a-tombstone-on-the-row.md` (in git at `3667fec2^`) rejected "a tombstone with a partial unique index" as "five schemas for one invariant" and chose "one row per path and revive-on-write". Its consequences section says: "Committed to. One row per path, always: no design may later admit a second row at a tombstoned path without reopening the partial-index question." The same record says what came before: until 2026-10-08 a delete moved the row to `/.vfs/trash/<hour>/<ulid>-<name>`, at about six row writes per file, and a moved private row became world-readable because grants are path ranges, which is why the move was retired. Spec 162 (`context/specifications/active/162-trash-as-a-tombstone-on-the-row/spec.md`, "Decided semantics") built the record item by item. The record and the spec both call the destroying verb `destroy` in their prose; the verb in the code is `sweep`.

READ: `delete` stamps `deleted_at`, `trash_root_id` and `version + 1` on each named row, guarded on the version it read, then stamps every live descendant with one `UPDATE … WHERE path LIKE …` per chunk of directories; a descendant already tombstoned keeps its own root and time (`src/vfs/storage/backends/database/trash.py:120` to `:211`, `:433` to `:499`). It also sets `encoded` false on every content row it stamps, which sends the row back to the index pass when it returns (`trash.py:450` to `:456`, `:502` to `:508`). Path, parent, name, owner, label, postings, edges and version rows are untouched.

## 3. Delete, and what each read verb then returns

EXECUTED ([p01](experiments/p01_delete_and_reads.out)). The setup is an open region (`/d` and `/t`, where a fresh mount's default gives everyone `read_write`) and a closed region (`/p`, everyone `none`, alice granted `read_write`). Alice, bob and the system actor wrote the files; anonymous wrote nothing.

**A file.** `delete /d/a.txt` returned one row, `status=deleted` with `deleted_at` set. Afterwards the row held the same id, path, parent, name, owner (alice) and label, with `deleted=yes`, `trash_root` equal to its own id and its version raised from 1 to 2. The delete's own observation reported version 1, the version before the delete. The parent directory's version rose by one. Both authored edges to and from the file were still in `vfs_edges`. No version row was written.

| Verb at the deleted file | System, alice, bob and anonymous (open region) |
|---|---|
| `read /d/a.txt`, `stat /d/a.txt` | `not_found`, with `vfs.trashed: true` and `vfs.deleted_at` in the error's data |
| `ls /d`, `tree /d`, `glob /d/**` | the live sibling only |
| `grep`, `search` for a word in the file | the other files that hold the word; never the deleted one |
| `traverse outbound` from the live file that links to it | the seed only; the edge is hidden |
| `edit`, a second `delete` | `not_found` with the trashed hint |
| `ls /.vfs/trash`, `tree /.vfs/trash`, `glob /.vfs/trash/**` | the deleted row, at its own path `/d/a.txt`, with `deleted_at` and version 2 |
| `stat` and `read` at `/.vfs/trash/d/a.txt` | the row and its body |
| `grep` or `search` with `paths=("/.vfs/trash",)` | `invalid`: "the view's head is a directory, not a pattern; scope beneath it with '/.vfs/trash/**'" |

All four callers got the same answers in the open region, because everyone holds `read_write` there. The trash view reports each row at its live path, not at a path under `/.vfs/trash`.

**A tree.** `delete /t` with `cascade=False` refused `not_empty`. With one file deleted first on its own, `delete /t` returned one row for `/t`. Afterwards all five rows under `/t` were tombstoned; four carried `trash_root` equal to `/t`'s id, and the file deleted earlier kept its own id as its root. Only `/t` had its version raised; the members' versions did not move. `read /t/x.txt` answered `not_found` at `/t` with the trashed hint and `vfs.target` naming the file. `stat`, `ls` and `tree` at `/t` answered `not_found` with the hint; `glob /t/**` and `grep` returned nothing with no error. `ls /.vfs/trash` listed the two roots; `ls /.vfs/trash/t` listed `/t`'s two direct children; `tree /.vfs/trash` listed every tombstoned row.

**The closed region.** Bob, who holds nothing at `/p`, was refused the delete with `not_found` at `/p`. After alice deleted `/p/secret.txt`, the system actor and alice saw `not_found` with the trashed hint at the live path and read the body through the trash view. Bob saw `not_found` at `/p` with no hint at the live path and at the trash-view path alike. Anonymous saw `unauthenticated` at both. So a caller who could not see the live file learns nothing from its tombstone.

## 4. Restore

EXECUTED ([p02](experiments/p02_restore.out)).

**A file.** After two writes, two edges and a delete, `restore /d/a.txt` returned `status=created` at version 4. The row had the same id, the same owner, the same label, the same body and its one earlier version row; both edges were still there and `traverse` followed them again. The version counter had moved by two, one for the delete and one for the restore, with no version row for either. A second restore answered `exists`. A restore of a path that never existed answered `not_found`. A restore addressed through the trash view answered `invalid`: "Cannot mutate the trash view beneath '/.vfs/trash'".

**A tree.** With `/t` deleted and one file beneath it deleted earlier on its own: a restore of a member file and of a member directory each answered `not_found` with "inside a deleted tree; restore its root" and the root's id in `vfs.trash_root`. A restore of the earlier-deleted file, a root in its own right, answered `not_found` at `/t`, because its parent was still deleted. `restore /t` brought back `/t` and its three members in one call; the earlier-deleted file stayed deleted and still listed in the trash view, and then restored on its own. Anonymous was able to run that tree restore, because everyone holds `read_write` in the open region.

**Onto a path occupied since.** READ: restore refuses `exists` when a live row sits at the path (`trash.py:250` to `:251`). EXECUTED: that case can only arise one way today. With `/d/a.txt` deleted, a `move` onto the path answered `exists` with the trashed hint, a `copy` onto it answered the same, and `mkdir` at it answered `not_found` with the trashed hint. The one thing that could occupy the path was a file `write`, and that write does not create a second row: it revives the deleted row (section 5). The restore that followed answered `exists`, and the path then held the new body. So "the path has been occupied since" always means "the deleted row itself was revived", and a restore can never collide with a different row.

**Who.** In the closed region, with alice holding only `add` and owning the file: bob (nothing) was answered `not_found` at `/p`, anonymous `unauthenticated`, and alice restored her own file. READ: the restore is judged at `read_write` or by ownership, and a directory restore also needs `read_write` on every row beneath it (`src/vfs/storage/backends/database/backend.py:794` to `:828`).

## 5. Revive: a write at a deleted file's path

READ: a file write whose target holds a tombstoned file stages an update on that row, not a create (`src/vfs/storage/backends/database/staging.py:287` to `:326`). The update's column set clears `deleted_at` and `trash_root_id` and replaces the body, and it never writes the owner: "never the owner, which a row keeps from its creation" (`src/vfs/storage/backends/database/writes.py:1194` to `:1227`). `overwrite=False` does not refuse it, "since no live row occupies the path" (`staging.py:287` to `:290`). The replaced body is kept as one version row (`src/vfs/storage/backends/database/versions.py:1` to `:15`).

EXECUTED ([p03](experiments/p03_revive.out)). Alice wrote `/d/a.txt` twice, linked it both ways to another file, was given an `external_id` on the row, and carol was granted `read` at the exact path.

**Same caller.** Alice deleted the file and wrote "a new file" at the path. The write returned `status=updated` at version 4, not `created`. The row kept its id. A second version row appeared holding the deleted body. The edges were untouched. A restore then answered `exists` and the trash view was empty.

**A different caller, open region.** Alice deleted the file; bob wrote at the path with `overwrite=False`. The write succeeded with `status=updated`. What bob's new file carries:

| Field | What the new file has | Whose |
|---|---|---|
| `entry_id` | unchanged | the deleted file's |
| `owner_id` | `alice` | the deleted file's owner, not the writer |
| `created_at` | unchanged (READ: the update's column set leaves it out, `writes.py:1206` to `:1227`) | the deleted file's |
| `external_id` | `ext-alice-001` | the deleted file's |
| Edges | both, in and out; `traverse inbound` and `outbound` as bob follow them | the deleted file's |
| Version rows | three: alice's two earlier bodies, and the body bob replaced, with `actor=bob` | the deleted file's history, with the reviver named on the last |
| Grant at the exact path | carol's `read` still applies | path-based, so it follows the path |
| Label | unchanged | the path's posture |

Alice's restore then answered `exists`, and her read at the path returned bob's body. Her deleted body now exists only as a version row. EXECUTED: `git grep` over `src/` finds `tables.versions` only in the mint (`versions.py`) and in the purge (`trash.py:606`); no verb reads a version row today. So after a revive the deleted body is kept in the database and reachable by no verb.

**What happens next.** The region was then closed: everyone `none` at `/d`, bob granted `read_write`, alice granted nothing. Alice could still read `/d/a.txt`, the file bob believes he created. She could edit it and delete it. She could not read `/d/bob-own.txt`, a file bob really created (`not_found`). The difference is the owner column: the revived row is still hers, and ownership is a floor under every rung.

**A different caller, closed region.** With alice's file deleted under `/p` (everyone `none`):

| Bob holds at `/p` | Read at the live path | Read through the trash view | Write at the deleted path | Write at a fresh name |
|---|---|---|---|---|
| nothing | `not_found` at `/p` | `not_found` at `/.vfs/trash/p` | `not_found` at `/p` | `not_found` at `/p` |
| `list` | `not_found`, no hint | `permission_denied` (`stat` shows the name and kind only) | `permission_denied` | `permission_denied` |
| `read` | `not_found` with the hint | the body | `permission_denied` | `permission_denied` |
| `add` | `not_found` with the hint | the body | `permission_denied` | created, owned by bob |
| `contribute` | `not_found` with the hint | the body | `permission_denied` | created, owned by bob |
| `read_write` | `not_found` with the hint | the body | revived: same id, owner still alice, alice's body kept as a version row with `actor=bob` | created, owned by bob |

READ: the gate judges a mutation at a tombstoned row "as a restore of the row — `read_write` or own" (`src/vfs/storage/backends/database/rights.py:907` to `:909`, and the code at `:938` to `:942`).

**The plain answer.** Can a second caller come to *read* anything of the first caller's deleted file this way: no (EXECUTED). A revive needs `read_write` on the row or ownership of it, and a caller at `read` or above already reads the tombstone through the trash view. A caller below `read` gets the same answer at the deleted path as at a fresh name. Can a second caller come to *hold* it: yes, and in an unexpected direction (EXECUTED). The second caller's content lands in the first caller's row. The second caller takes over the id, the inbound links, the external id and the history. The first caller stays the owner, so the first caller keeps a right to read, edit and delete what the second caller wrote, even after every grant the first caller had is gone. And the first caller's delete can no longer be undone.

EXECUTED ([p10](experiments/p10_plans_and_contribute.out), section 2), one more consequence of judging a revive as a restore: bob at `contribute` overwrote and edited alice's live file, as that rung allows. Once alice deleted it, bob's write at the same path answered `permission_denied`. A caller who may overwrite a live file may not write at its path once it is deleted.

## 6. `mkdir` at a deleted directory's path, and a write beneath it

READ: `put_dir` treats a tombstone at the site as absent and refuses `not_found`, "only `restore` brings it back" (`staging.py:328` to `:346`); the parent gate refuses a tombstoned ancestor "whatever the flag says" (`staging.py:246` to `:267`).

EXECUTED ([p04](experiments/p04_mkdir_and_write_beneath.out)). With `/proj/src` (a directory holding one file) and `/proj/notes` (a file) deleted:

| Call | Answer |
|---|---|
| `mkdir /proj/src`, also with `exist_ok=True`, with `parents=True`, and as the system actor | `not_found` at `/proj/src`, with the trashed hint |
| `write /proj/src/new.py`, also with `parents=True` | `not_found` at `/proj/src`, with the trashed hint |
| `write /proj/src/main.py`, the deleted member's own path | `not_found` at `/proj/src` |
| `write /proj/src` as a file | `wrong_kind: directory`, with the trashed hint |
| `mkdir /proj/notes`, where a deleted file sits | `not_found`, with the trashed hint |
| `write /proj/notes/child.txt` with `parents=True` | `not_found` at `/proj/notes` |
| `move /proj/other /proj/src`, `copy /proj/other /proj/src` | `exists`, with the trashed hint |
| `move /proj/other /proj/src/inside` | `not_found` at `/proj/src` |

So the same path answers "not found" to `mkdir` and "already exists" to `move`. The name came back two ways only: `restore /proj/src`, which brings the old directory back, and `sweep /proj/src`, which destroyed the tombstoned tree, after which `mkdir /proj/src` created a fresh directory with a new id. A deleted file's path can never become a directory and a deleted directory's path can never become a file, short of a sweep.

## 7. Move

READ: `move` takes `src`, `dest` and `moves`; it has no `replace` parameter (`src/vfs/base.py:1235` to `:1246`). "No transfer replaces an occupant, a tombstoned one included — displacement is the caller's delete, then the transfer again" (`src/vfs/storage/backends/database/topology.py:139` to `:142`). The occupant probe reads the destination path with no liveness term, and any row there refuses `exists` (`topology.py:188` to `:191`, `:276` to `:281`). A move updates the root row's `parent_id`, `name`, `path`, `ext`, label and version, then rewrites `path` and label on every descendant by id, tombstoned descendants included, then rewrites the path-segment postings (`topology.py:299` to `:359`, `:362` to `:447`).

EXECUTED ([p05](experiments/p05_move.out)).

**The id stays.** `move /d/a.txt /e/b.md`, run by bob on alice's file, returned `status=created` at version 3. The row kept its id and its owner (alice); `parent_id`, `name` and `path` changed; the version row and both edges stayed with the id. The old path answered a plain `not_found` and the trash view was empty: a move leaves nothing behind. A moved tree kept every id as well.

**Onto an occupant.** A file onto a live file: `exists`. A file onto a tombstoned file: `exists` with the trashed hint. A directory onto an empty live directory: `exists`. A file onto itself: `status=unchanged`. A tombstoned source: `not_found` with the hint.

**The documented workaround does not work.** With a live file at the destination, the caller deleted it and moved again, as `topology.py:139` to `:142` tells it to. The move still answered `exists`, now with the trashed hint. The tombstone holds the address. Only `sweep` of the destination freed it, and the move then succeeded; the replaced file was destroyed, with no undo.

**A tree that holds a tombstone.** With `/t/sub/z.txt` deleted, `move /t /u` carried the tombstone along: the trash view then listed it at `/u/sub/z.txt`. `restore /t/sub/z.txt`, the path the delete reported, answered `not_found`; `restore /u/sub/z.txt` worked. The old path `/t/sub/z.txt` was then free for an unrelated new file with a new id.

**How much a move rewrites.** Counted with a `before_cursor_execute` listener; a parameter set is one row's worth of an `executemany`.

| Tree | `move` statements | `move` parameter sets | `delete` | `restore` | `sweep` (live) |
|---|---|---|---|---|---|
| 100 rows | 32 | 130 | 18 | 16 | 19 |
| 1,000 rows | 32 | 1,030 | 18 | 16 | 19 |
| 2,000 rows | 32 | 2,030 | 18 | 16 | 19 |

The 1,000-row move's statements are listed in the output. Twenty are reads, among them two that fetch the whole subtree. One `UPDATE` moves the root. One `executemany` of `UPDATE vfs_entries SET path=?, everyone_level=? WHERE entry_id = ?` carries 999 parameter sets, one per descendant. One `UPDATE vfs_segments` rewrites the renamed segment for every row in the tree. One `UPDATE vfs_edges` repoints the root's hierarchy edge and two bump the parents. So a move of an N-row tree issues a flat number of statements and rewrites N entry rows and N posting rows. INFERRED: every id survives at any size, and the cost of that is the stored `path` column, not identity; the 999 single-row updates are one round trip each on a driver that does not batch `executemany`.

EXECUTED ([p09](experiments/p09_index_state_across_delete_and_restore.out)): a move leaves the index state alone (200 of 200 files still `encoded`), while a delete followed by a restore of the same tree left 200 of 200 files `encoded=False`, waiting for the next index pass. `grep` still found them, served by scan.

## 8. Sweep

READ: `sweep` defaults its path to `/.vfs/trash` (`base.py:1119` to `:1141`). At that address it destroys every tombstoned root older than the mount's `trash_days` (90 by default) with its members, then scans the body tables for orphans. At any other address it "purges that subtree wholesale, immediately, regardless of retention age, live and tombstoned rows alike" (`trash.py:346` to `:404`). The purge deletes from the entry, content, blob, version, version-subject, chunk, segment and edge tables (`trash.py:551` to `:614`).

EXECUTED ([p06](experiments/p06_sweep.out)).

**At the trash view.** With the default 90 days and one file just deleted, `sweep()` and `sweep("/.vfs/trash")` returned no rows and changed nothing. With `trash_days=0`, `sweep("/.vfs/trash")`, run by alice, returned two rows, `status=deleted`, and took the table counts from 6 entries, 3 bodies, 1 version row, 4 postings and 7 edges to 3, 1, 0, 0 and 2. `sweep("/.vfs/trash/work/a.txt")` answered `invalid`; a single tombstone is destroyed by its own path instead, `sweep("/work/a.txt")`, after which restore answered `not_found`.

**At a live path.** `sweep("/work")` on a live directory holding a live file with history and a live subdirectory with another caller's file returned exactly one row, `/work kind=directory status=deleted`, and no error, warning or note. Afterwards four entry rows, two bodies, the version row, all four postings and six of seven edges were gone, including the authored edge from a surviving file into the swept tree. The trash view was empty and `restore /work` answered `not_found`. Nothing warned first: there is no confirmation flag, no dry run, and no refusal for a live target. The status word on the observation is `deleted`, the same word `delete` uses; the only difference is that `deleted_at` is absent. `sweep("/")` answered `invalid` and a missing path `not_found`.

**Who.** On the open region anonymous swept a live file, and bob swept alice's live file with its history. In the closed region, alice as owner holding only `add` swept her own file. Bob holding `add` or `contribute` and not owning the file was denied. The retention arm at `/.vfs/trash` was denied to alice until she held `read_write`.

## 9. Who may delete, restore and sweep, by rung

READ: the one table of rungs is `VERB_RUNGS` in `src/vfs/ops.py:142` to `:168`. The ladder, lowest first, is `none`, `list`, `read`, `add`, `contribute`, `read_write`; each rung includes those below it; `add` "creates beneath a prefix and alters only one's own rows", `contribute` "also overwrites and edits anyone's", `read_write` "trashes, moves and grants" (`ops.py:117` to `:121`).

| Verb | Rung on the target | What else the gate asks | Where |
|---|---|---|---|
| `delete` | `read_write`, or ownership of the row | with `cascade`, `read_write` on every row beneath | `ops.py:154`; `backend.py:756` to `:762` |
| `restore` | `read_write`, or ownership of the row | for a directory, `read_write` on every row beneath; a row the caller cannot see answers as absent | `ops.py:155`; `backend.py:797` to `:828` |
| a `write` that revives | `restore`'s rung, not `write`'s | the live parent chain | `rights.py:938` to `:942`; `src/vfs/storage/backends/database/authorized.py:303` to `:313` |
| `move` | `read_write` on the source and every row beneath; `add` at the destination | the destination must be empty | `ops.py:156`; `topology.py:410` to `:447` |
| `sweep` at a path | `read_write`, or ownership of the row | `read_write` on every row beneath; each purged row is judged again | `ops.py:165`; `backend.py:850` to `:861`; `trash.py:588` to `:591` |
| `sweep` at `/.vfs/trash` | `read_write` over the whole mount | none | `backend.py:857` to `:858` |

EXECUTED (sections 4, 5 and 8 above): the owner floor is real for all three verbs. An owner holding only `add` deleted, restored and swept its own file.

READ: `sweep` is in `DEVELOPER_OPS`, "never registered on any agent-facing tool surface (MCP serve, CLI) — Python-API only" (`ops.py:97` to `:101`). INFERRED: that is its only guard. It is a property of adapters, not of the verb: any Python caller who may `delete` a row may `sweep` it, at the same rung, and on a fresh mount, where everyone holds `read_write`, that includes anonymous.

## 10. Keys, indexes, and the cost of tombstones in a listing

EXECUTED ([p07](experiments/p07_listing_cost_and_keys.out), [p10](experiments/p10_plans_and_contribute.out)). Work is counted in SQLite virtual-machine steps through the progress handler, never in time.

| Directory holds | `ls` steps | `stat` of one live child | `glob dir/live*` | `delete` one child, `cascade=False` | `restore` one child |
|---|---|---|---|---|---|
| 10 live, 0 tombstoned | 355 | 117 | 341 | 805 | 643 |
| 10 live, 1,000 tombstoned | 5,362 | 117 | 345 | 5,819 | 643 |
| 10 live, 2,000 tombstoned | 10,362 | 117 | 345 | 10,830 | 643 |
| 10 live, 4,000 tombstoned | 20,362 | 117 | 345 | 20,841 | 643 |

Each call returned the same ten rows in three statements. The listing costs five more steps for every tombstone in the directory. The real statement is `… WHERE parent_id IN (?) AND deleted_at IS NULL … ORDER BY parent_id, name`, and SQLite's plan for it is `SEARCH vfs_entries USING INDEX sqlite_autoindex_vfs_entries_1 (parent_id=?)`: it seeks the parent in the `(parent_id, name)` key, then visits every child, live or deleted, and tests `deleted_at` on each. The occupancy count that `delete` with `cascade=False` runs has the same shape and the same cost. A point read and a pattern match on the path did not grow.

The trash view's head, `ls /.vfs/trash`, runs `… WHERE trash_root_id = entry_id AND deleted_at IS NOT NULL … ORDER BY path`. With statistics gathered, SQLite's plan is `SCAN vfs_entries USING INDEX ix_vfs_entries_path`: a walk of the whole table in path order. Over 7,000 tombstoned roots it returned all 7,000 rows in one result, with no limit. INFERRED: the test `trash_root_id = entry_id` compares two columns of the same row, so no index on either column can seek it; how each server engine plans it was not measured.

READ: the retention arm fetches every expired root into memory, purges them in one transaction that holds the mount's serialization point from its first statement, and then "scans `vfs_content` and `vfs_blobs` end to end, inside the serialized transaction"; the docstring names that scan as the sweep's dominant cost at scale and names the direction (`trash.py:388` to `:404`, `:617` to `:657`).

## 11. Today's design against the properties, one by one

**A delete can be undone.** Holds, until someone writes at the path. EXECUTED: restore worked for a file and a tree. EXECUTED: after any revive the restore answers `exists` and the deleted body is a version row no verb reads. The write that forecloses the undo reports `updated` and nothing else.

**An undone delete brings back the same file: id, history, edges, owner, rights.** Holds. EXECUTED: all five came back unchanged. Two side effects: the version counter moves by two, and every file in the restored set goes back through the index pass.

**A path freed by a delete can be used again, and what a new file inherits is a deliberate choice.** Fails. EXECUTED: a deleted directory's path cannot be used by `mkdir`, `write`, `move` or `copy`. A deleted file's path can be used only by a file `write`, and the new file inherits everything: id, owner, creation time, external id, links in both directions and history. The caller is given no choice and no sign beyond `updated`.

**A move keeps the moved file's id, at any size, and a replacing move leaves the replaced file undoable.** Half holds. EXECUTED: the id stays for a file and for a tree of 2,000 rows. EXECUTED: there is no replacing move; an occupied destination refuses, a tombstoned one included, and delete-then-move is refused too. INFERRED: with one row per path a replaced file has nowhere to go, so the ruling cannot be built without a schema change. INFERRED: "at any size" holds for correctness and not yet for cost, since a move rewrites every row of the tree in one transaction (section 13).

**The irreversible verb is named so nobody runs it by mistake.** Fails. EXECUTED: `sweep` with no argument is a harmless retention pass, and `sweep` with a path destroys a live tree at once, returns one row whose status reads `deleted`, and warns of nothing. INFERRED: one word covers a routine cleanup and the most dangerous call in the library, and the address alone picks which.

**Every verb stays bounded at the reference deployment.** Mostly holds for statements, fails in three places for work. EXECUTED: delete, restore, sweep and move issue a flat number of statements at 100, 1,000 and 2,000 rows. EXECUTED: a listing costs in proportion to live and deleted children together. EXECUTED: the trash view's head scans the table and returns every root. READ: the retention sweep is one whole-batch transaction with a full scan of the body tables.

**Rights are never widened.** Holds in everything probed, with one drift over time. EXECUTED: a caller who could not read a file learned nothing from its tombstone, its trash-view address, a restore or a write at its path. EXECUTED: after a revive by another caller, the first owner keeps the owner floor over content it did not write. READ, not probed: a move judges every row it carries at `read_write` and every new path as a creation (`topology.py:410` to `:447`), and relabels each moved row, tombstones included, to the destination's posture.

## 12. Where today's design fails or surprises, most serious first

1. EXECUTED: `sweep` at a live path destroys live rows, bodies, history and edges at once, with no warning, at `delete`'s rung, reachable through the owner floor and, on a fresh mount, by anonymous. Its observation says `deleted`.
2. EXECUTED: a deleted directory's name is dead. `mkdir` says `not_found`, `move` says `exists`, and only `restore` or `sweep` changes that. INFERRED: so the ordinary way to reuse a name runs through the irreversible verb, which is the opposite of what "delete is reversible; sweep is not; agents only get the first" (`base.py:1071`) intends.
3. EXECUTED: the code's own instruction for replacing a file by a move, "the caller's delete, then the transfer again" (`topology.py:139` to `:142`), is refused with `exists`. Only sweep-then-move works, and it destroys the replaced file.
4. EXECUTED: a write at a deleted file's path silently becomes the deleted file. It keeps the old id, owner, links, external id and history, ignores `overwrite=False`, forecloses the restore, and leaves the first owner with a standing right over the second caller's content.
5. READ and INFERRED: there is no replacing move and no room for one. The developer's ruling needs a second row at a path, which the retired record 074 names as the one thing that reopens the schema question.
6. EXECUTED: a listing visits every tombstone in the directory, and the trash view's head walks the table. Tombstones live for 90 days by default and nothing but an explicit `sweep` removes them (`base.py:1135`: "storage owns no background work").
7. EXECUTED: a caller at `contribute` may overwrite a live file and is denied at the same path once the file is deleted.
8. EXECUTED: a restore is addressed by "the path the delete reported" (`base.py:1105`), and that path stops working when an ancestor is moved; the tombstone then restores only at its new path.
9. EXECUTED: a delete and a restore each raise the version with no version row, the delete's observation reports the version before its own bump, and a restore sends every file in the set back through the index pass. INFERRED: at about 11,000,000 index visits a day, an accidental delete and restore of a 100,000-file directory adds about 1% to that day's index work.
10. EXECUTED: "the body it replaced is kept as a version" is true in the table and not yet in the interface, since no verb reads a version row.

## 13. Redesign options: where a deleted or replaced row lives

INFERRED throughout, from the code read and the probes run; the SQLite parts are EXECUTED in [p08](experiments/p08_live_only_key_on_sqlite.out) and [p10](experiments/p10_plans_and_contribute.out), section 3. The three options are the ones the brief names. Each is judged on the same questions: what the schema declares, what each verb does, and what it costs at the reference deployment in `AGENTS.md` (10,000,000 files, 10,000-file batches, about 150,000 verb calls a day, about three reads or listings for each write).

| | Option 1: tombstones leave the unique keys | Option 2: tombstones move to a path under the trash view | Option 3: the unique keys gain a generation |
|---|---|---|---|
| Schema | `path` and `(parent_id, name)` are unique over live rows only | no key changes; the row's `path`, `parent_id` and `name` are rewritten on delete, and the origin is kept in new columns | a `generation` column, 0 on a live row and unique per tombstone; keys become `(path, generation)` and `(parent_id, generation, name)` |
| Rows at one path | one live, any number deleted | one | one live, any number deleted |
| `delete` | stamps the tombstone, as today; the row drops out of two unique indexes | a move: every row of the tree and its postings are rewritten | stamps the tombstone and the generation; two unique index entries are re-keyed |
| `write` or `mkdir` at a deleted path | a fresh row: new id, the writer as owner, no links, no history | a fresh row | a fresh row |
| `restore` | clears the tombstone; the key refuses it if a live row holds the path | a move back; `exists` if the path is taken | sets generation to 0; the key refuses it if a live row holds the path |
| `move` with replace | the occupant is tombstoned where it is; the source keeps its id | the occupant is moved to the trash; the source keeps its id | as option 1 |
| Trash-view address | `/.vfs/trash/<path>` can name several rows; needs a second part | unique by construction | as option 1; the generation can be that second part |
| Rights | unchanged: the row is judged at its own path | must be judged by origin again, in a second form of every rights statement | unchanged |
| Listing a directory full of tombstones | never visits them | never visits them | never visits them, with the key order above |
| Dialects | three spellings across five engines | one | one |

**Option 1, a key over live rows only.** EXECUTED on SQLite: `CREATE UNIQUE INDEX … WHERE deleted_at IS NULL` on `path` and on `(parent_id, name)` admitted two tombstones and one live row at one path, refused a second live row, and refused a restore while a live row held the path. A live listing over 4,000 tombstones cost 63 steps. A lookup by path with no liveness term fell to `SCAN e`, so a second, plain index on `path` is needed for the trashed hint and the trash view. Whether each dialect can declare it: SQLite yes (EXECUTED). Postgres and SQL Server yes, as a partial and a filtered index; READ: SQLAlchemy 2.0.52 models `postgresql_where`, `sqlite_where` and `mssql_where`, and this repository already declares one such index on the edge table for exactly those three dialects (`rows.py:635` to `:647`). MariaDB and Oracle have no partial index; READ in the retired record 074: the spellings are "a function-based index on Oracle, a generated column on MariaDB", and SQLAlchemy has no `where` option for either. The edge-table precedent leaves those two engines with no index at all, which is not acceptable for the key that arbitrates concurrent creates. A nullable column that vfs sets to NULL on delete works under a plain `UNIQUE` on SQLite (EXECUTED) and READ in record 074 fails on SQL Server, whose `UNIQUE` admits one NULL. So option 1 is declarable on all five, in three spellings, four of them not executed here. What changes in the verbs: the insert arbitration on SQLite and Postgres names `index_elements=["parent_id", "name"]` (`writes.py:523` to `:529`) and must name the index predicate too; every lookup by path must say which row it wants, where today 11 call sites of `rows_by_path`, 3 of `point_row` and 2 of `fetch_snapshot` fetch with no liveness term and sort live from deleted in Python; the revive path goes (71 lines in 9 files of `src/` mention it); `restore` and the trash view need a way to name one of several tombstones at a path. Cost at the reference deployment: a delete is still one row write per file; a listing no longer pays for tombstones; a point read adds a liveness term to a seek. The new cost is rows: a name that is created and deleted over and over keeps one row and one body per cycle until retention destroys them, where today it keeps one row and one version row per cycle.

**Option 2, tombstones move under the trash view.** READ: this is the design vfs had until 2026-10-08, and record 074 gives the reasons it was retired. The move cost "about six row writes per file on delete and six on restore". Grants are sorted path ranges, so a moved private row left its ranges and became world-readable; closing that took a second form of every rights statement, judged by an origin path, at 46 sites. And the trash became a place a mutation could reach. EXECUTED here, for the cost: a move of a 1,000-row tree rewrites 1,000 entry rows and 1,000 posting rows (section 7), and a delete would cost the same. At the reference deployment a 10,000-file delete batch becomes about 60,000 row writes instead of 10,000, and a deleted 1,000,000-row directory becomes a 1,000,000-row path rewrite in one transaction, done twice if it is restored. What it gets right: the unique keys do not change, every tombstone has its own address, a replaced file has a place to go, and no dialect work is needed. INFERRED: it buys the property the developer asked for by paying again for the two problems the tombstone was built to remove.

**Option 3, a generation in the key.** EXECUTED on SQLite: with `generation` 0 on live rows and the row's own integer `id` on a tombstone, plain `UNIQUE (path, generation)` and `UNIQUE (parent_id, name, generation)` admitted two tombstones and a live row at one path and refused the same two things option 1 refused. The key order decides the listing cost: with `(parent_id, name, generation)` a live listing over 4,000 tombstones cost 16,073 steps, and with `(parent_id, generation, name)` it cost 54. Whether each dialect can declare it: it is two ordinary composite unique constraints over NOT NULL columns, so all five can, in one spelling; none but SQLite was executed. The keys grow by eight bytes, against a path of at most 1,024 bytes and the tightest key budget of 1,700 (`src/vfs/storage/backends/database/dialects.py:543`), so no path budget moves. Using the row's own `id` as the generation needs no counter and no shared row to contend on. What changes in the verbs: the same list as option 1, with `generation = 0` as the liveness term in a seek, `generation` stamped by `delete` and zeroed by `restore`, and the insert arbitration naming the three-column key. One index on `(path, generation)` serves both the live seek and the lookup of every tombstone at a path, where option 1 needs two. Cost at the reference deployment: as option 1, plus two index entries re-keyed on each delete and each restore; the same accumulation of rows at a name that churns.

**What options 1 and 3 share, and must decide.** Both make a delete free the path at once, so a new file there is new: a deliberate choice of "inherits nothing". Both keep "permissions never notice a delete", since a tombstone is still judged at its own path by its own owner and label. Both turn a replacing move into "tombstone the occupant in place, then move". Both must settle three things the one-row rule settled for free: how `restore` and the trash view name one of several tombstones at a path; what `restore` does when a live row holds the path (refuse `exists`, which now has a real remedy, since deleting or moving the occupant frees the path; or restore under another name, which is a move of the set); and whether `write` at a deleted path may still revive when the caller asks for it.

**A fourth shape, for completeness.** INFERRED: tombstones stay in place as today, and only a tombstone that is in the way, under a replacing move or a new file, is relocated to a trash-side path at that moment. The common delete stays one row write. The cost is that a relocated row needs the origin-judged rights form of option 2, for those rows only, and the design has two kinds of tombstone.

**The move's own cost is separate from all four.** EXECUTED: a move rewrites every descendant's stored path. INFERRED: no option above changes that, because it comes from `path` being a stored column on every row. At the reference deployment a move of a 1,000,000-row directory is 1,000,000 entry updates and 1,000,000 posting updates in one transaction that took the mount's serialization point as its first statement, so every other move, delete, restore and sweep on the mount waits for it; reads and plain writes do not take that point (`trash.py:444` to `:448`). That fits the reference deployment's rule for a lock only if such a move is rare, and it is the place "at any size" is not yet true.

## 14. What a rename of `sweep` to `destroy` touches

EXECUTED, with the search the eight rulings study used for verb calls, `git grep -o -h -E "[A-Za-z_][A-Za-z0-9_]*\.sweep\("` over `src tests docs documentation docs-app README.md examples`: 67 call sites, 65 in `tests/` and 2 in `src/`, none in the docs trees and none in `tests/fixtures`. By receiver: 50 on `storage`, 7 on `fs`, 5 on `root`, 3 on `s`, and 1 each on `impatient` and `_fs`.

| What | Count | Where |
|---|---|---|
| Call sites `.sweep(` | 67 | 65 in `tests/` across 18 files, 2 in `src/` |
| Definitions `def sweep` | 6 in `src/`, 3 test doubles | `base.py:1119`, `session.py:199`, `backend.py:844`, `storage/protocol.py:207`, `sync.py:380`, `sync.py:866`; `tests/storage/test_protocol.py:82` and `:173`, `tests/support/base_doubles.py:98` |
| The op name as a string, `"sweep"` | 23 in 8 files of `src/`, 32 in 16 files of `tests/` | `ops.py`, `params.py`, `permissions.py`, `results/render.py` and others |
| The builder `sweep_rows` | 3 lines in `src/`, 3 in `tests/` | `trash.py`, `backend.py` |
| Test functions with `sweep` in the name | 35 in 14 files | `tests/` |
| Lines holding the word | 60 in 17 files of `src/`, 239 in 69 files of `tests/` | includes docstrings and comments |
| Prose in the docs | 6 lines in 5 files | `README.md`, three files under `docs/`, one under `documentation/` |
| Documents under `context/` | 1,633 lines in 329 files | history; append-mostly, so not rewritten |

EXECUTED: `git grep -n "destroy" -- src` finds prose only, no function, method or op of that name, so the name is free. Some uses of the word in `src/` are not the verb and should stay: `sweep_undeclared_signals` (`signals.py:167`) and the prose "sweeps" in the index, edge and signal modules. READ: the retired record 074 and spec 162 already write `destroy` for this verb.

INFERRED: the rename is small beside the 424 and 1,679 call sites the eight rulings study counted for its two questions. It fixes the name and not the shape. The verb has two arms: a retention pass over expired tombstones, which is routine, and an immediate purge of whatever sits at a path, live rows included, which is the dangerous one. A rename is the moment to decide whether both arms keep one name, whether the path arm should refuse a live target unless told otherwise, and whether its observation should say something other than `deleted`.

## What this study did not reach

- Concurrency. Every probe ran one caller at a time on one in-process connection. A rival revive against a restore, a write beneath a directory being deleted, and a sweep against a write were read in the code and not run. The experiment is the existing real-engine conformance legs with two sessions.
- The other four engines. The listing cost, the trash view's plan and the three key spellings in section 13 were executed on SQLite only. The experiment is the same DDL and the same counted listing on Postgres, MariaDB, SQL Server and Oracle, with each engine's own plan output.
- A 10,000-file batch. Statement counts were taken at 100, 1,000 and 2,000 rows for one tree, not for a batch of 10,000 separate targets. The experiment is p05's counter over a 10,000-target `delete`, `restore` and `move`.
- A move's rights. The move probes ran in a region where everyone holds `read_write`; a move by a caller who cannot see part of the tree, and a move of a tombstone from a closed region into an open one, were read and not run. The experiment is p05's tree under p03's closed region.
- Bytes-bodied files, a posture change while tombstones stand, a cross-mount move, and `copy` over a tree holding tombstones were not probed.
- The number of tombstones a real deployment carries. No figure exists for how often a name is deleted and created again; the reference deployment table has no row for deletes. The cost of options 1 and 3 at a name that churns rests on that figure.
- The prior art. Studies 02 and 03 hold it; this study read neither.

## One line

Today a tombstone hides a row well and brings the same row back, but it keeps hold of its path, so a deleted directory's name is dead, a new file at a deleted file's path silently becomes the old file, a move can never replace anything, and the only way to free a name is `sweep`, which destroys live data without a warning; a move that keeps its identity through a replace needs the unique keys to stop counting tombstones, by a key over live rows (three spellings across five engines) or by a generation in the key (one spelling).
