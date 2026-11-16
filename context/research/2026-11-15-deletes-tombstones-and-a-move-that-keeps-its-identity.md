# A tombstone hides a row and brings the same row back, but it keeps hold of its path: a deleted folder's name is dead, a new file at a deleted file's path becomes the old file, no move can replace anything, and the one verb that frees a name destroys live data without a warning

This memo was a placeholder and is now completed in place. Clay raised it on 2026-11-15 while ruling on roadmap story K1. Asked whose identity survives when `move(replace=True)` lands on an existing file, Clay answered: "I think we should keep POSIX, so we may need to design this and tombstoning a bit better. If you move a file, you are keeping the same id but changing the path. Please do some seperate research on deletes and let me know if tombstones are designed correctly today." Three researchers worked the same day to [the brief](studies/2026-11-15-deletes-tombstones-and-a-move-that-keeps-its-identity/00-brief.md), for about twenty, eleven and nine minutes: one ran every delete, restore, revive, move and sweep sequence on the in-memory store, one read seventeen reference clones, and one read the public documentation of twelve products. No intention: the question came from one ruling. The spec that will use the answer is the deletes spec, which is not yet written; [the kernel rulings spec](../specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md) records the two rulings that lean on it, its decisions 3 and 6.

Labels: EXECUTED means a command ran on 2026-11-15 and the claim reports its output; READ means read in the file, clone or page cited; INFERRED means reasoning from the two. Each claim below is from one of the three studies, which give the file and line, the clone and commit, or the page and date: [study 01, what vfs does today](studies/2026-11-15-deletes-tombstones-and-a-move-that-keeps-its-identity/01-what-vfs-does-today.md), [study 02, the reference clones](studies/2026-11-15-deletes-tombstones-and-a-move-that-keeps-its-identity/02-how-file-systems-and-stores-keep-identity-across-delete-and-rename.md) and [study 03, products with a trash](studies/2026-11-15-deletes-tombstones-and-a-move-that-keeps-its-identity/03-how-products-with-a-trash-name-and-shape-it.md).

## Sources

vfs at `08c372af`: under `src/vfs/storage/backends/database/` the files `trash.py`, `staging.py`, `topology.py`, `writes.py`, `versions.py`, `rights.py` and `backend.py`; `src/vfs/models/rows.py`, `src/vfs/ops.py` and `src/vfs/base.py`. The retired records 027 and 074, read in git before commit `3667fec2`, and the numbered spec 162. Ten probe scripts and their outputs under the studies folder's `experiments/`, run on the in-memory store, which is the database backend on an in-process SQLite. Seventeen clones, each with its commit in `refresh.log` and its licence in `licenses.log`: `linux` and `plan9` were dirty and were read as they stood, not refreshed; `agentfs` carries no licence file and is MIT by its README and its package file; `linux`, `minio` and `libsqlfs` are copyleft and `afs` is source-available, all studied only. The product documentation of Google Drive, Dropbox, OneDrive and SharePoint, the freedesktop.org trash specification, macOS, Windows, Amazon S3, Azure Blob, Google Cloud Storage, HashiCorp Vault, IMAP and Git, each page by URL in study 03, read on 2026-11-15 through a fetch tool and not compared by eye with the rendered page.

## The answer

Tombstones are designed correctly for one job and wrongly for another. As a way to hide a row and bring the same row back, the design holds: a restored file has its id, owner, history, edges and rights, and nothing a caller could not read before can be read through a delete, a restore or a write at a deleted path (EXECUTED). As a way to free a path, it fails, because a deleted row goes on holding its path and its name under both unique keys. Four things follow, each executed. A deleted folder's name cannot be used again. A new file written at a deleted file's path is not new: it becomes the deleted file. No move can replace anything, and the workaround the code documents is refused. And `sweep`, the only way left to free a name, destroys live data at once, with no warning, at the same rung as `delete`. Clay's ruling that a move keeps its identity through a replace cannot be built on today's schema. It can be built once a deleted row stops counting in the unique keys, and of the ways to do that, a generation number in the key is the one that is a single plain declaration on all five engines and also makes a listing stop paying for the deleted rows beside it (EXECUTED on SQLite only).

## 1. What holds today

EXECUTED, study 01's sections 3 to 5. A deleted file answers `not_found` to every read verb and is left out of every listing and search; the trash view shows it to the callers who could read it. A restore brings back the same row: same id, owner, label, version rows and edges, for a file and for a tree. A caller who could not see a live file learns nothing from its tombstone, at the live path or through the trash view. A write at a deleted path needs `read_write` on the row or ownership of it, the rung a restore needs, so no caller comes to read another's deleted file by writing over it. A move keeps every id, for a file and for trees up to 2,000 rows.

## 2. Where it fails, most serious first

EXECUTED unless a line says otherwise, study 01's sections 5 to 12.

- `sweep` at a live path destroys the live rows there, with their bodies, history and edges, in one call. Nothing warns: there is no confirmation, no dry run and no refusal for a live target, and the row it returns says `deleted`, the word `delete` uses. It is judged at `delete`'s rung, so an owner holding only `add` can run it on their own file, and on a fresh mount, where everyone holds `read_write`, anonymous can. Its one guard is that no agent-facing tool offers it (READ, `src/vfs/ops.py:97-101`).
- A deleted folder's name is dead. `mkdir` there answers `not_found`, a write beneath it `not_found`, a `move` or `copy` onto it `exists`. Only `restore` or `sweep` frees it, so the ordinary way to reuse a name runs through the irreversible verb.
- A write at a deleted file's path revives the deleted row. The new file keeps the old id, owner, creation time, external id, edges in both directions and history, ignores `overwrite=False`, and reports `updated`. The delete can then no longer be undone, and the deleted body survives only as a version row that no verb reads.
- After such a revive by a second caller, the first caller is still the row's owner. With every grant of theirs removed, the first caller still read, edited and deleted the file the second caller believed they had created. No right was widened at the moment of the write; the drift comes after it.
- No move replaces an occupant, a tombstoned one included. The code's own instruction, delete the occupant and move again (`topology.py:139-142`), is refused with `exists`. Only sweep and then move works, and it destroys the replaced file.
- A listing visits every deleted child in the folder: 355 SQLite steps for ten live files, and 20,362 with 4,000 tombstones beside them. The trash view's head walks the whole table and returns every root with no limit. Tombstones stand for 90 days by default and only an explicit `sweep` removes them.
- Smaller surprises: a caller at `contribute` may overwrite a live file and is denied at the same path once it is deleted; a tombstone restores only at its new path after an ancestor is moved; a delete and a restore each raise the version with no version row; a restore sends every restored file back through the index pass.

## 3. What other systems do

READ, studies 02 and 03.

No system read keeps a stable file id, a unique path, and a deleted item that goes on holding the path. Where a system has both an id and a unique path, the deleted item gives the path up and is found by a second handle: an inode number in the trash entry's name (JuiceFS), a deletion id (Azure), a restore token (Google Cloud Storage), an item id (Google Drive, OneDrive). The one precedent for today's shape is a caution: Jackrabbit Oak keeps the deleted mark on the path's own record and needs a second flag, revive-aware readers and a collector that re-checks.

Two systems do what Clay ruled. JuiceFS: a rename onto an existing file moves the replaced file into the trash with its inode intact, so both files keep their identity and the replaced one can be restored. Azure Blob with a hierarchical namespace: "The existing destination blob or empty directory is soft-deleted and the source replaces it." POSIX itself gives only half: the moved file keeps its inode, and the replaced file is gone.

Every system that keeps identity through a rename stores the name apart from the file, so a rename is one name record at any tree size. Every system that keys a file by its path loses identity on a move or rewrites every descendant. vfs keeps the id and also stores the path on every row, so it keeps identity and still rewrites every descendant (EXECUTED, section 5 below).

A new file at a freed path inherits nothing in every system where the file has an id of its own. It joins the old history only where the path is the identity (S3, Vault), and there on purpose.

A restore onto a path taken since has five documented answers: refuse until the occupant is gone (Azure, JuiceFS), append a number (SharePoint), overwrite and soft-delete the occupant (Google Cloud Storage), let the caller name a new place (Microsoft Graph), or no collision because versions stack (S3, Vault).

The irreversible act is never called "sweep". It is "permanently delete" (Dropbox, Microsoft Graph, S3, JuiceFS, MinIO), "destroy" (Vault), "erase" (freedesktop) or EXPUNGE (IMAP). Vault's delete, undelete and destroy, each granted separately, is the closest match to Clay's ruling. Delete, restore and the permanent act are separately granted nearly everywhere. Azure and Google Cloud Storage have no early irreversible verb at all: a soft-deleted object cannot be destroyed before its clock runs out. Every hosted trash has a clock, from 7 to 365 days.

No trash read widens access. One lesson not to copy: JuiceFS lets every user list the names of everything deleted.

## 4. Where a deleted or replaced row could live

INFERRED from the studies, with the SQLite parts EXECUTED in study 01's section 13.

| | A key over live rows only | Deleted rows move under the trash view | A generation in the key |
|---|---|---|---|
| Schema | `path` and `(parent_id, name)` unique where the row is live | no key changes; path, parent and name rewritten on delete | a `generation` column, 0 on a live row and the row's own number on a deleted one; keys `(path, generation)` and `(parent_id, generation, name)` |
| Declared on the five engines | three spellings: a partial index, a filtered index, and a generated column or function index on MariaDB and Oracle | one | one, two ordinary unique constraints |
| `delete` | one row write a file, as today | a move: every row of the tree and its postings rewritten, about six row writes a file | one row write a file, two index entries re-keyed |
| A new file at a deleted path | a new row that inherits nothing | the same | the same |
| A replacing move | the occupant is tombstoned where it stands; the moved file keeps its id | the occupant moves to the trash; the moved file keeps its id | as the first column |
| A listing beside 4,000 tombstones | 63 steps (EXECUTED, SQLite) | not run; it would not visit them | 54 steps with the key ordered `(parent_id, generation, name)`; 16,073 with the generation last (EXECUTED, SQLite) |
| Rights | unchanged: a tombstone is judged at its own path | a second form of every rights statement, judged by where the row came from | unchanged |
| Precedent | Azure, Drive, OneDrive | JuiceFS, freedesktop, macOS, Windows | S3's version id, the generation in ext4 and UFS |
| What it cost before | rejected by the retired record 074 as "five schemas for one invariant" | vfs had it until 2026-10-08 and retired it: the row writes, and a moved private row became world-readable because grants are path ranges | not tried |

The generation is the one that is a single declaration everywhere, keeps a delete at one row write, leaves the rights statements alone and makes a listing stop paying for tombstones. JuiceFS can move a deleted name cheaply because its names are separate rows; vfs stores the path on every row, which is why the same move cost six writes a file here. With a generation, a replacing move is "tombstone the occupant where it stands, then move", which is Azure's shape.

A generation, like a key over live rows, makes three choices necessary that the one-row rule made for free. How `restore` and the trash view name one of several deleted rows at one path: the precedents use the item's own id. What `restore` does when a live row holds the path: refusing `exists` now has a real remedy, since deleting or moving the occupant frees the path. And whether a write at a deleted path may still revive when the caller asks for it.

## 5. Two things beside the schema

The verb. `sweep` has two arms under one name: a retention pass at the trash view, which is routine, and an immediate purge of whatever sits at a path, live rows included (READ, `trash.py:346-404`; EXECUTED). EXECUTED: renaming it to `destroy` touches 67 call sites, 6 definitions and 3 test doubles, 55 string literals and 35 test names, and no `destroy` symbol exists in `src/` today. The rename fixes the name and not the shape. The precedents suggest three changes to the shape: the irreversible act applies only to what is already deleted, so destroying live data takes a delete first; it is granted apart from `delete`; and its result says something other than `deleted`.

The move's cost. EXECUTED: a move issues a flat 32 statements at 100, 1,000 and 2,000 rows, and rewrites one entry row and one posting row for every row of the tree, in one transaction that takes the mount's serialization point as its first statement. So a move of a 1,000,000-row folder is about 2,000,000 row writes during which every other move, delete, restore and sweep on the mount waits; reads and plain writes do not take that point (READ, `trash.py:444-448`). None of the three schema choices changes that, because it comes from the path being stored on every row. "A move keeps its id at any size" holds today for correctness and not for cost.

## What this memo does not settle

- Whether a generation in the key behaves on Postgres, MariaDB, SQL Server and Oracle as it did on SQLite: the declaration, the listing's plan, and the insert that arbitrates two concurrent creates. The experiment: study 01's probes p08 and p10 with the same DDL and a counted listing on the four engine legs, each engine's plan recorded.
- Concurrency. Every probe ran one caller at a time. The experiment: a rival create against a restore at one path, a write beneath a folder being deleted, and a replacing move against a write to its occupant, staged at seams on the four engine legs.
- How many deleted rows a real deployment carries. The reference deployment has no row for deletes, and the cost of rows gathering at a name that is created and deleted over and over rests on that figure. The experiment: none can measure it; it is an assumption Clay sets, as the nightly batch was.
- A move's rights where the mover cannot see part of the tree, and a move of a tombstone from a closed region into an open one. The experiment: study 01's probe p05 under probe p03's closed region.
- Whether a large move should run in bounded chunks behind a durable mark, as a posture's relabel does, or whether names should be stored apart from files so a move is one row. The experiment: the statement and row counts of a chunked move of 100,000 rows on the four engine legs, beside a read of how the grant ranges and the path-segment postings would be kept if the path were not a stored column.
- Who may destroy. The experiment: none; it is a ruling, informed by section 3's finding that the permanent act is granted apart from delete nearly everywhere.

## One line

Tombstones are right for undo and wrong for freeing a path; putting a generation in the unique keys lets a deleted row step aside, which is what a move that keeps its identity through a replace needs, and `destroy` should act only on what is already deleted.
