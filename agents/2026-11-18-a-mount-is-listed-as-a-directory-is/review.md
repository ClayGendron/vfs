# Review: a mount is listed as a directory is

The build was read eight times on 2026-11-18 and 2026-11-19, and fixed four times. The last reading was a narrow one: it checked only that the two findings of the reading before it were closed. The feature has not had a full reading since its fourth round of fixes. No reading was given a summary of the work. Three readings were made of the first build, two by fresh readers and one by a second model. The second model then read each round of fixes. Every finding below was shown by a script that ran.

| What was read | Verdict | Fixes |
|---|---|---|
| The build, commit `2b6b7e40`, three readings | Does not land yet, all three | `39f4d894` |
| The first fixes | Does not land yet | `fa7775ec` |
| The second fixes | Does not land yet | `cae3dbdf` |
| The third fixes | Does not land yet: two findings, both from the third fixes | `e9eb88f2` |
| The fourth fixes, the two findings only | Both closed, and nothing that worked was broken | None |

## What the readings say about the design

Each round closed what it was given and opened something beside it. The first two rounds added a mechanism for each finding. The third and fourth replaced mechanisms with rules, and the code grew shorter. Most of the findings were in `glob`, where four things meet: the mount points a pattern matches, the roots a caller names, a limit, and a mount table that can change while the call waits. `ls`, `stat` and `tree` settled after the first round.

## Found and fixed

| Found | Rule now |
|---|---|
| `glob` returned a mount's name to a caller whose listing of its parent was refused. | A mount point is shown only when the storage that holds its parent directory answered that `glob`. A failed probe of a named root removes what lies strictly beneath that root. |
| A mount that loops back on its kernel crashed `ls`, `tree` and `glob` of its parent with `RecursionError`. | `ls` and `stat` take a hop from the call's budget, as `tree` does. The probe of a named root, inside a search that holds a hop, takes none. |
| One listing read the mount table twice and saw two versions of it. A mount added during `ls` dropped out of the listing. A `glob` returned a row from a new storage beside a row from the old one. | A `MountListing` is a copy of the table, made when the table changes. One call uses one copy from its first step to its last, in every verb. |
| The filter that drops the directory beneath a mount also dropped deleted rows from the trash view and a node from a graph walk. | Only `ls`, `tree` and `glob` drop that row, and `glob` keeps a row that is known to be deleted. |
| A `stat` batch named the wrong path as missing, and a directory named twice came back once with an error. | Each miss is matched to the path it was raised for. A directory above a mount gets a bare row for each time the batch names it and the storage gave none. |
| A storage that could not answer still had a bare row made up for a directory it holds. | A bare row stands in for a `not_found`, and for nothing else. Each path is judged on its own errors, and a failure that names no path is a failure of the whole answer. |
| A failed `ls` or `tree` could return the directory beneath a mount, with its fields. | That row is dropped before any answer is returned. |
| A mounted root's row was shown from a failed answer, or with a kind that is not a directory. | The row is taken only from an answer with no fatal error, and only when it is a directory. Otherwise it is bare. |
| Under `max_count`, the limit was spent on a mount point that was then left out, and a storage was asked after `close()`. | The mounted roots are asked after the storages have answered, for the mount points that are shown, and no storage is called once the kernel is closed. |
| `locate` said a directory above a mount was not there. | One function decides for `stat` and `locate`. Such a directory is there unless its storage refused with something other than `not_found`. |
| A `stat` batch, and the probe of named roots, made one storage call for each directory above a mount. The row filter compared every row with every mount. Finding the mount that holds a path checked every prefix of the path again. | A `stat` batch is one call. The filter walks up a row's own path. A prefix is looked up as text and checked once. |
| The order of `glob`'s rows came from a set, and changed from run to run. | Mount points and the directories above them come back in path order. |

Sixty-one tests were added across the four rounds, each seen failing before its fix.

## Found and left, each a task in `agents/tasks.md`

Some were there before the feature. Each is marked.

- A `glob` result can name a mount in its error records when the caller's listing was refused. Before the feature.
- A storage that raises an ordinary exception, not a transport error, raises out of the listing of its parent. That is the kernel's rule for a fault, and a test now pins it. Before the feature, `ls` of the parent did not ask the mounted storage, so it was not affected.
- A named root that is a mount point is returned by its probe as the storage gave it, and is asked twice when one of its ancestors is named too. The limit does not count a row a probe already supplied.
- After a region of a `glob` fails, a stored row for a directory in it, or the row of a named root, can come back through the merge.
- A storage applies `max_count` before the kernel drops rows hidden beneath a mount. Before the feature.
- Rows strictly beneath a mount path are dropped from the parent's trash listing. Before the feature.
- A `glob` with no limit can call a storage that `remove_mount` has handed back and whose owner has closed it. The call in flight holds the storage.
- `glob` and `grep` over rows in hand look up a missing fact on the mount table as it is when they ask. Before the feature.
- `locate` and `stat` report a file when a second kernel on the same storage replaced a directory above a mount with a file. Before the feature.
- A mounted storage whose own `tree` returns its root row gives two rows at the mount point.
- `read` and the mutating verbs take no hop, and neither does `locate`. Before the feature.
- Every mounted root in a listing is asked at once, with no limit on how many at a time.
- `_permission_layers` scans the mount table once for each row of a batch, and `MountListing.beneath` once for each named root. `Result.merge` removes repeated errors by searching a growing list. Before the feature.
