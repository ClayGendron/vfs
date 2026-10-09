# 074. Trash Is a Tombstone on the Row: Delete Flags, Restore Clears, a Write Revives

- **Status:** accepted 2026-10-08 (Clay: "those all sounds good …
  accept the ADR and cut the spec"). Supersedes ADR 026's rejection of
  its option (e), "flag, don't move", and amends ADR 014 (the trash is
  a view over tombstoned rows, not an ordinary subtree). It retires
  spec 150 §8's trashed predicate forms (judge trashed rows by origin
  — true by construction here, so the built second forms go),
  dissolves spec 156 rule 2 (a restore-only trash prefix), binds spec
  161 (the version a revive mints), and supersedes in part the
  archived 081 (self-describing trash names), 082 (the trash-side
  restore address) and 083 (the bucket sweep). Spec 162 builds it.
- **Date:** 2026-10-08
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, 2026-10-08). Drafted by Claude from the
  2026-10-08 memo at Clay's request; Clay's framing: "deleting
  something just turns the visibility off … if you write back to that
  location, it turns it back on and creates a new version … this
  solves the permission problems when entries 'move' to the trash."

## Context

Today `delete` moves the row: its `path` is rewritten to
`/.vfs/trash/<hour>/<ulid>-<name>`, every descendant's path with it,
and the path-segment postings that mirror the path column follow.
The row keeps `origin_path`, `original_parent_id`, `original_name`
and `deleted_at`. ADR 014 chose the move so that the trash is an
ordinary browsable subtree; ADR 026 considered "flag, don't move" and
rejected it because a flag "threads `deleted_at IS NULL` through
every live query and the `(parent_id, name)` unique index", recording
the rejection "so it is not re-litigated".

Two later decisions changed the ground. ADR 072 made explicit grants
into sorted path ranges joined to the path index, so a moved row
leaves every range and lands under the root posture: a private row
became world-readable on delete (spec 150 review finding 1,
critical). Spec 150 §8 closed that leak, and the fix landed with
ADR 073 (`f823436`, 2026-10-03): every rights statement judges a
trashed row by `origin_path`, which means every piece branch of
every visibility statement is built twice (a live form on `path`, a
trashed form on `origin_path`), the hole test is an `OR` of two
forms, the origin columns ride in the rights field set with their
own index and per-dialect join hints, and 46 sites carry them. ADR 073
also put a row-level predicate, `everyone_level`, on every partial
read, so the read path already carries a per-row term.

The 2026-10-08 memo
(`../research/2026-10-08-trash-as-a-tombstone-on-the-row.md`)
measured the move at about six row writes per file on delete and six
on restore (one entry update, four posting inserts, one posting
delete), verified by a run that the origin-judged rights hold (bob
cannot see alice's private row in the trash), found the trash
exclusion already owned by one function
(`liveness_filters`, five call sites), studied MinIO's delete markers
and JuiceFS's enforced move, and established per engine that a
partial unique index is not portable (SQL Server's `UNIQUE` admits one
NULL; Oracle and MariaDB have no partial indexes) — while Clay's
revive-on-write rule makes that index unnecessary, because one row
per path is preserved.

## Options considered

- **Keep the move, judge trashed rows by origin (the status quo,
  spec 150 §8 as built).** Correct: the leak is closed. Keeps the
  browsable subtree and the archived trash specs intact. Costs: the
  six-writes-per-file move stays; every visibility statement carries
  two predicate forms and an `OR`'d hole test, which is where
  JuiceFS's gaps sit (xattrs, open handles, hard links — the seams
  between its two trash predicates); and the trash remains a place a
  mutation can reach (the SmartOwl memo's item 15). Rejected: it pays
  for a path rewrite whose only remaining purpose is to be undone by a
  second predicate.
- **A tombstone with a partial unique index (the ORM `deleted_at`
  school).** Live and tombstoned rows may share a path; restore picks
  the newest. Costs the per-engine DDL the memo's §4 lays out
  (`postgresql_where` / `sqlite_where` / `mssql_where`, a
  function-based index on Oracle, a generated column on MariaDB) and
  a second unique constraint on `(parent_id, name)` with the same
  problem. Rejected: five schemas for one invariant, and the codebase
  already notes a partial index over the restore columns "is not
  portable".
- **A tombstone with one row per path and revive-on-write (chosen).**
  Delete sets a flag; nothing moves; a `write` at a tombstoned path
  revives the same row and mints a version of the body it replaced;
  `restore` clears the flag. The unique index on `path` and the
  constraint on `(parent_id, name)` stay plain on every engine. MinIO
  implements both restore forms (delete the marker; PUT on top) and
  keys authorization on the unchanged key; the agent-audience peers
  all clear their delete mask on a write at the path.
- **Snapshots instead of trash (Plan 9 / ZFS).** Rejected in ADR 026
  and unchanged here: trash is cheap delete-undo, not time travel;
  spec 161's version rows are the per-row history.

## Decision

A deleted row stays where it is and is marked. Concretely:

1. **The flag.** `delete` sets `deleted_at` and a new
   `trash_root_id` (the entry id of the row the caller named; a root
   points at itself) on the target and, for a directory, on every
   live descendant, chunked by the dialect budget. `path`,
   `parent_id`, `name`, `everyone_level`, `owner_id`, the postings
   and the fs edge row are untouched. A descendant that was already
   tombstoned keeps its earlier `deleted_at` and `trash_root_id`.
   The `origin_path`, `original_parent_id` and `original_name`
   columns and their indexes are dropped, and with them the trashed
   forms in `ranges.py`, `rights.py` and `labels.py`; the path is the
   origin.
2. **Liveness.** `liveness_filters` gains `deleted_at IS NULL`; every
   enumerating and searching verb inherits it through that one
   function, and a test per verb pins it. A point read at a
   tombstoned path classifies `not_found`, as a deleted path does
   today and as pjdfstest requires; when the caller's rights admit the
   row, the refusal carries `data["vfs.trashed"] = true` so an agent
   knows `restore` applies (MinIO's `x-amz-delete-marker`).
3. **Permissions do not notice a delete.** The row is judged at its
   own path by the label and ranges it already has. There is no
   trash-side predicate form. `restore` requires write rights at the
   path, as the delete did; `destroy` stays on the developer plane.
4. **Restore clears the flag** on the row and on every row sharing
   its `trash_root_id`, version-guarded as today. It is addressed by
   the row's path; there is no trash-side address. With one row per
   path there is at most one tombstone per path; older generations
   are version rows.
5. **A write revives.** A `write` whose path holds a tombstoned row
   clears the flag, mints a version row of the replaced body (spec
   161's law), lands the new body, and keeps the entry id. If the
   incoming kind differs from the row's (a file where a directory
   was deleted, or the reverse), the row changes kind and its
   tombstoned descendants keep their flags; a later `restore` of the
   directory refuses `exists` because the site is occupied, the rule
   the July memo found unanimous across the field, and the
   descendants restore individually once the site is a directory
   again.
6. **Edges survive.** Nothing moves, so the fs mirror row needs no
   repoint and authored edges need no cascade; an edge whose endpoint
   is tombstoned is hidden with it by the same liveness term and
   returns with `restore` or a revive. This reverses the edges
   module's "restore brings entries back with authored edges gone"
   rule, which existed because the row moved.
7. **The trash is a view.** `/.vfs/trash` remains the address an
   agent and `destroy` use, but it enumerates tombstoned roots at
   their own paths with `deleted_at` projected, under the same rights
   as a live listing. There are no hourly buckets and no in-trash
   names; ADR 026's naming rules have no referent.
8. **Sweep** destroys rows with `deleted_at` older than the mount's
   retention, chunked by id, each root with its cascade. No bucket
   name is parsed and no closed-world assumption is needed. The purge
   arm's content, blob, chunk, posting and edge cleanup is unchanged.
9. **No mutation reaches a tombstoned row** except the three above:
   `restore`, `destroy`, and a `write` at its path. `edit`, `move`,
   `copy`-from, `mkdir`, `mkedge` classify `not_found`. The "writable
   trash" hole (SmartOwl memo item 15; spec 156 rule 2) has nothing
   to write into.
10. **Scale.** The cascade is one column wide and chunked; statement
    counts stay flat in batch size as the rewrite's do today. The
    liveness term sits on a column the liveness index can carry. No
    engine-specific DDL is added.

## Consequences

- **Easier.** Delete and restore are invisible to permissions by
  construction; spec 150 §8's second predicate forms, the `OR`'d hole
  test and the origin index are removed.
  Delete writes one row per file instead of six, restore the same,
  and the postings never move. Restore has one address form. The
  sweeper is a `WHERE`. The trash cannot be written into. The unique
  index needs nothing per engine. Trash and versions become one
  story: a revive mints the version the README promises.
- **Harder.** Every future nominator must go through
  `liveness_filters` or carry the term itself; the test per verb is
  the guard. The trash view is new code where the subtree was free,
  and `ls /.vfs/trash` no longer looks like a directory of directories.
  `topology.py`'s delete, restore and sweep arms are rewritten; the
  archived 081, 082 and 083 are superseded in part and their status
  lines say so on acceptance. The kind-change-on-revive rule (item 5)
  is a fork Clay may re-decide; the alternative is to refuse the write.
- **Committed to.** One row per path, always: no design may later
  admit a second row at a tombstoned path without reopening the
  partial-index question. A delete never changes who can see a row; a
  restore never reveals one (mirage's invariant, stated for data).
  ADR 014's parity goal survives as inspectability through the view,
  not as a physical subtree.
