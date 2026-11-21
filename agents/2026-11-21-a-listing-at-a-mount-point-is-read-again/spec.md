# A listing at a mount point is read again

A draft, written on 2026-11-21 from the defects the readings of the listing rule left. It is not reviewed, and nothing is built.

## The outcome wanted

Every verb gives the same answer at a mount point and at the directories above one, whatever order the storages answer in and whatever fails. The rule of `agents/2026-11-18-a-mount-is-listed-as-a-directory-is/spec.md`, which landed as pull request 13, holds for `glob`'s named roots, for `tree`, for `stat`, for `read` and for the trash view, as it holds for `ls`.

## Builds on

The listing rule, pull request 13, and the module `vfs.listing` it added. `MountListing.beneath` and `MountListing.governing` walk the mount table by a path's prefixes since pull request 23.

## The problem

Each defect below was shown by a script that ran during a reading of the listing rule's branch, unless it says "read". Where it says "before the listing rule", the defect is older than pull request 13. None has been run again on `dev`.

### `glob`

- **An error record can name a mount the caller may not list.** When the caller's listing was refused, a record for a mount that cannot `glob`, and a mounted storage's own refusal, both carry the mount's path. Before the listing rule.
- **A named root that is a mount point is not treated as other mount points are.** Its probe returns the row as the storage gave it, even from a failed answer, or with a kind that is not a directory. It is asked twice when one of its ancestors is named too, and two answers that differ merge to a row with no version. The limit does not count a row a probe already supplied.
- **After a region fails, a row in it can come back.** A stored row for a directory above a mount comes back through the merge, and a named root's probe can put its row back.
- **A storage applies `max_count` before the kernel drops the rows hidden beneath a mount.** A stray row in the parent storage beneath a mount path can cost the caller a visible row. Before the listing rule.
- **A storage builds every candidate before it applies the limit.** Before the listing rule.
- **A call can reach a storage that `remove_mount` handed back and whose owner closed it.** The call in flight holds the storage.
- **Over rows in hand, `glob` and `grep` look a missing fact up on the mount table as it is when they ask.** A mount replaced while they wait changes the answer. Before the listing rule.

### `tree`, `stat`, `read` and `locate`

- **In `tree`, a mount whose holder failed loses its own row, and the rows beneath it are still listed.** A mounted storage whose own `tree` returns its root row gives two rows at the mount point.
- **`stat` of a missing path beneath a hidden directory above a mount names that directory as the missing part.** `stat` of the directory itself returns a bare row.
- **`read` of a directory above a mount says `not_found` to a caller who holds nothing on it,** where `stat` shows it and a visible directory gives `wrong_kind`.
- **`locate` and `stat` report a file when a second kernel on the same storage replaced a directory above a mount with a file.** Before the listing rule.
- **`read`, the mutating verbs and `locate` take no hop.** A storage that wraps its own kernel recurses without end on them. `ls` and `stat` take one. Before the listing rule.

### The trash view

- **The parent's trash listing loses the deleted rows that lie beneath a mount path.** Before the listing rule.

### Cost

- **Every mounted root in a listing is asked at once.** With 200 database mounts, one `ls` opens 200 transactions together. Read.
- **The cost of a listing over mounts is counted in calls, and not measured on a server engine.**

### Where the code lives

- **`gather_settled` and `PathFilters` live in `vfs.listing`.** Three readings said they belong in a module that is not about listings, since writes and searches use them too.

## Decisions

1. **Before any fix, one fresh reading of the listing rule in full,** given `src/vfs/listing.py`, the listing paths of `src/vfs/base.py` and the spec, and none of the defects above. The rule has not had a full reading since its fourth round of fixes, only a check that the last two findings were closed. The reading's findings join this list, and each item above is run again on `dev` and dropped if it no longer holds.
2. **A named root of `glob` that is a mount point goes through the same path as any other mount point.** Its probe answers only from a successful answer with a directory kind, it is asked once per call, and the limit counts its row. This one change answers the second and third `glob` items.
3. **The kernel drops the hidden rows before the limit is spent.** The storage is asked for the limit plus the number of mount paths beneath the root, or the kernel asks again while it is short. Which of the two is a choice below.
4. **Every verb that resolves a path takes one hop,** as `ls` and `stat` do.
5. **The mounted roots of one listing are asked with a bound on how many at once.** The bound is a kernel setting with a default, and the time limit's spec gives each its time.
6. **`gather_settled` and `PathFilters` move to a module named for what they do,** with no change to either.

## Tests

Each defect gets its reproducing test first, at the kernel layer, with storage doubles where an order of answers must be forced. A counted test pins decision 5: an `ls` over 200 mounts never has more mounted calls in flight than the bound.

## Scope

In: the listing paths of the kernel, `vfs.listing`, and the hop of the path-resolving verbs. Out: the time limit, which has its own spec, and the search defects, which are `agents/2026-11-21-search-and-grep-agree-over-rows-in-hand/spec.md`.

## Not checked

- Whether each defect still holds on `dev` at `48486e6c`. Pull requests 21, 23 and 24 changed the code around several of them.
- What 200 transactions at once cost on Postgres.

## Choices to confirm

1. **Does a fault in a mounted storage raise out of a listing of its parent?** Today a storage that raises an ordinary exception, and not a transport error, raises out of `ls`, `tree` and `glob` of the directory its mount is in. That is the kernel's rule for a fault. Before the listing rule, `ls` of the parent did not ask the mounted storage. Recommended: keep it, since a fault is a bug and a listing that hides it hides the bug. Alternative: a bare row and a warning, as for a storage that cannot be reached.
2. **May `glob` ask the mounted roots after the storages have answered?** It does since the third round of fixes. It costs one more round trip when a pattern matches a mount point, and it lets the limit be spent only on rows that are shown and keeps a storage from being called after `close()`. Recommended: yes.
3. **Decision 3: ask for more, or ask again?** Recommended: ask for more, since it is one round trip and the mount paths beneath a root are known. Its cost: a storage may build up to that many extra rows.

## One line

The listing rule is read once more in full, and then `glob`, `tree`, `stat`, `read`, `locate` and the trash view are brought to the answer `ls` gives at a mount point.
