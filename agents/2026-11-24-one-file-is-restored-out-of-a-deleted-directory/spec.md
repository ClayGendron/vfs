# One file is restored out of a deleted directory, and a file is restored to another place

A draft, written on 2026-11-24 from the work on `agents/2026-11-24-a-deleted-row-gives-up-its-path/spec.md`, which leaves both out. It is not reviewed, and nothing is built.

## The outcome wanted

A caller who deleted a directory of 10,000 files and wants one of them back gets that one. A caller whose deleted file's place is taken, or whose directory has been renamed, restores the file to a path it names.

## The problem

Run on `dev` at `27f3d24`, `agents/2026-11-24-a-deleted-row-gives-up-its-path/probes/p01_what_a_deleted_row_does_to_its_name_today.py`, part 6.

- A `restore` of a file inside a deleted directory is `not_found`, "inside a deleted tree; restore its root". The whole directory must be restored and deleted again. Every restored file goes back through the index pass, and the second delete starts the retention clock again for all of them.
- The trash view reads the file, and a `copy` out of the view is refused as a change to the view. So the one way to take a file out is to read it and write it elsewhere, which makes a new entry with no history.
- After the deletes spec, a deleted row stays at the path it was deleted at. A file deleted from a directory that is then renamed restores only once a directory is made again at the old path. `restore` makes no directory and takes no destination.
- A `restore` onto a path that holds a live row is `exists`. The remedy is to move the occupant aside, restore, and move both back: four calls where one would say what is meant.

## Choices

1. **A member is restored alone.** The restored row leaves its set and becomes live under the directory at its parent path; the rest of the set stays deleted. The other choice keeps "only a root restores" and allows a `copy` out of the trash view, which gives a new entry.
2. **`restore(path, to=)`.** The row comes back at the path named. Microsoft Graph's restore takes a new parent and a new name. The other choice leaves the destination out and relies on a move after the restore.
3. **`restore(parents=True)`.** It makes the missing directories, as `write` and `mkdir` do. The Windows Recycle Bin and the freedesktop trash make them without being asked.

## Tests

One file restored out of a deleted directory of 3 leaves 1 live file and 2 deleted rows in the set. A restore to another path leaves the entry's history rows attached to the row at that path.

## One line

Restore takes a root back to where it was and nothing else, and two ordinary wishes need more.
