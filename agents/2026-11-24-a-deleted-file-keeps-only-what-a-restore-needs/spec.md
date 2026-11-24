# A deleted file keeps only what a restore needs

A draft, written on 2026-11-24 from the work on `agents/2026-11-24-a-deleted-row-gives-up-its-path/spec.md`, which leaves it out. It is not reviewed, and nothing is built.

## The outcome wanted

It is decided, and stated in the docs, what a deleted file goes on holding until it is destroyed: its body alone, or its body with everything derived from it.

## The problem

Read on `dev` at `27f3d24`.

- A delete marks the entry row and removes nothing. The body, the version rows, the chunk rows, the path postings and the edges stay until the row is destroyed (`src/vfs/storage/backends/database/trash.py:596-614` lists what a purge then removes).
- A delete lowers the row's `encoded` flag, so the next index build leaves the file out, and a restore sends the file through the index pass again (`trash.py:450-456`). The derived rows that are kept are therefore not what makes a restore cheap.
- They are what serves the trash view: a `grep` and a `search` scoped to `/.vfs/trash` find a deleted file after a rebuild (`tests/support/storage_contract.py:1951`, `:2128`).
- The reference deployment holds about ten chunks a file. At the deletes spec's assumed 450,000 standing deleted rows that is about 4,500,000 chunk rows kept for the trash view's search. A pipeline that deletes and rewrites a million files a night would keep 90 nights of them.
- A deleted file's body is readable through the trash view by whoever could read the file, for the whole retention window. A secret written by mistake and deleted is still there. The only removal is `destroy`, which is the system actor's wherever everyone does not hold `read_write`.

## Choices

1. **What a delete keeps.** Everything, as today, so that the trash view is searchable; or the body and the version rows alone, with the derived rows dropped at the delete and rebuilt at the restore, which already rebuilds.
2. **Whether the trash view is searched at all.** If derived rows go, `grep` in the trash view falls back to a scan of bodies, and `search` there is withheld.
3. **A way to remove one deleted body early without the system actor.** None today, by the ruling on who may destroy. The choice is whether the docs say so, or a narrower act is added.

## Tests

The count of chunk rows whose entry is deleted, after a delete and an index pass, is the number the first choice fixes: unchanged, or 0.

## One line

A deleted file keeps its search index for a trash view few will search, and nobody has decided that it should.
