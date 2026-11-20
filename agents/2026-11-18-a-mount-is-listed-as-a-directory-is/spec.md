# A mount is listed as a directory is

This spec is built, on the branch `a-mount-is-listed-as-a-directory-is`, which sits on top of the branch `public-names-follow-the-naming-rules`. It is the third draft. The second was reviewed twice on 2026-11-18 and found not sound, and this draft answers those reviews. The third draft was built without a review of its own. Decisions 4, 6, 7 and 8 were changed while it was built, decision 11 was added, and each now says what the code does. Three reviews of the built code then found eleven defects, and the fixes changed the words of decisions 2 to 8 and 11, the cost and the scope to match. A review of those fixes found nine more, and their fixes changed the words of decisions 2, 3, 4, 6, 8 and 11 and the cost again. A third review found seven more. Their fixes put a rule in place of each special case and changed the words of decisions 2, 4, 5, 6, 8 and 11 and the cost. A review of those fixes found four more, which changed the words of decisions 4, 6, 8 and 11. What is left is in `agents/tasks.md`.

## The outcome wanted

At a mount point, VFS behaves as Plan 9, Unix and Linux do. Where VFS has something those systems lack, which is rights on each row, it applies its own rule for a plain directory, so that a mount and a directory with the same contents look the same.

## Terms

- **Mount point.** The path a mount is attached at, such as `/data`.
- **Covered directory.** The empty directory stored at the mount point. It is an ordinary entry in the storage of the mount above.
- **Mounted root.** The root of the storage attached at the mount point. Its own path is `/`, and callers see it as `/data`.
- **Parent.** The storage that holds the covered directory.
- **Child.** The storage attached at the mount point.
- **Listing.** A call that returns the entries inside a directory: `ls`, `tree` and `glob`.
- **Bare row.** A row with only its path and its kind filled in.
- **Road.** In a storage, a directory the caller holds nothing on still shows, as a bare row, when a row the caller may see lies beneath it. The caller can then walk down to what they were given. A storage's own root is on the road for every named caller.

## What the precedent is

Read in local clones on 2026-11-18. 9front at a0806493, MIT. Linux at faeab166, GPL-2.0. libfuse at 6a484ac6, LGPL-2.1 and GPL-2. FreeBSD at 3ccfcdac, BSD-3-Clause by its file headers. The 9front and Linux clones were dirty and were read as they stood.

| Question | Plan 9 | Linux |
|---|---|---|
| What is the entry at a mount point when the parent is read? | The mounted root. Every directory read replaces the entry with a `stat` of what is mounted there, and keeps the name. `sys/src/9/port/sysfile.c:550-610`, `695-705`. | The covered entry from `getdents`. A `stat` of the name crosses into the mounted root, so `ls -l` shows the mounted root. `fs/readdir.c:341-372`, `fs/namei.c:1569`. |
| Who decides whether the name shows? | The parent. Reading the directory is checked on the directory. No entry has visibility of its own. `sysfile.c:573-579`. | The parent. Read permission is checked on the directory. The mounted root's mode never hides the name. |
| Is the covered directory reachable while mounted? | No, after a replacing mount. `chan.c:1516-1522`. | No, by ordinary lookup. |
| What does a caller get who may not read the parent? | No listing. With walk permission they still reach the mount by its path. | No listing. With search permission they still reach the mount by its path. |
| What does a permission change at the mount path change? | The mounted root. | The mounted root. |
| Who may mount and unmount? | Any process, in its own namespace. | A process with `CAP_SYS_ADMIN`. `fs/namespace.c:2002`. FUSE lets a user mount on a directory they may write, `util/fuser_conf.c:401`. FreeBSD lets a user mount on a directory they own, `sys/kern/vfs_mount.c:1163`. |

Three things follow for VFS.

- **The row at a mount point is the mounted root.** Plan 9 does exactly this. Linux reaches the same result for any listing that shows attributes.
- **The mounted storage's rights never hide a mount's name.** On both systems the name belongs to the parent.
- **The rights of the covered directory cannot be reached while the mount is on.** A grant at the mount path goes to the mounted root. This is how VFS behaves today, and it is not a defect.

## The problem

A mount does not look like a directory to a caller it is shared with.

Executed on 2026-11-18, and reproduced by two reviewers. The root is closed, with posture `none`. A file is at `/data/report.md`. The caller ada is granted `read` at `/data`. The setup was run once with `/data` a plain directory and once with `/data` a mount whose storage is also closed.

| Call as ada | Plain directory | Mount |
|---|---|---|
| `ls("/")` | `/data` | nothing |
| `tree("/")` | `/data`, `/data/report.md` | `/data/report.md` |
| `tree("/", max_depth=1)` | `/data` | nothing |
| `glob("/*")` | `/data` | nothing |
| `stat("/data")` | `/data` | `/data` |
| `ls("/data")` | `/data/report.md` | `/data/report.md` |

With the mount, `ls("/")` hides the folder that was shared, and `tree("/")` returns a file whose parent is missing. No error and no warning is returned.

The cause is that the row at `/data` in a listing of `/` is the covered directory. The parent has no row for ada there, so the parent does not list it.

More facts, all executed.

- For the system actor, the row `ls("/")` returns at `/data` is not the row `stat("/data")` returns. Their `version`, `created_at` and `updated_at` differ. One path shows two entries.
- A caller who holds nothing anywhere gets a bare row from `stat("/data")`, an empty success from `ls("/data")`, and `exists=True` from `locate("/data", exists=True)`. So every named caller can already learn that a mount exists and what it is called. Only the listing of the parent hides it.
- With a mount at `/a/b` shared with ada and a closed root, `ls("/")` is empty and `ls("/a")` is `not_found`. With plain directories, `ls("/")` shows `/a` and `ls("/a")` shows `/a/b`.
- A new mount is open. Its storage starts at posture `read_write`, so every caller reads its files until its posture is set, even under a closed root. A posture does not cross a mount.

## Decisions

### 1. In a listing, the row at a mount point is the mounted root

`ls`, `tree` and `glob` take the row at a mount point from the child. It is the row `stat` of the mount point returns to that caller, with the mount's path as its path. The caller's `columns` are passed to that `stat`, and the row keeps the mask of fields the child filled.

A caller with rights at the mounted root gets the full row. A caller with none gets the bare row, because a storage's root is on the road for every named caller.

Reason: Plan 9 does this on every directory read. A reader then sees one entry at one path, whichever verb they use.

### 2. The mounted storage's rights never hide a mount's name

A mount's name shows in every listing of its parent that succeeds. No rights question is asked of the child. The child decides only how much of the row a caller sees.

`glob` asks every storage at once and merges what answers, so it decides for each mount point on its own whether the listing of its parent succeeded. The parent is the deepest mount whose path lies strictly above the mount point. A failure removes only the mount points in the region it describes, in the parent that holds them, and each is left out with the record of its `stat`. A failure of the parent's `glob` is the region at the path it was raised for, which is its `data["vfs.target"]` or its own path, and that path is in the region. A failure of a root's probe is the region strictly beneath that root, in the mount that was probed. The root's own row is not beneath itself, so it is kept. A failure that cannot be tied to a path, or a probe failure that names none of the roots it probed, is the whole of the mount that failed. A warning removes nothing. A parent that was not asked refused nothing, and its mount points are kept. A directory above a mount point is judged the same way.

Reason: on Plan 9 and on Linux the mounted root's permissions never hide the name. It also makes the listing agree with `stat` and `locate`, which show every mount to every named caller today.

Consequence to state in the docs: a mount's path is not a secret. A caller who holds nothing in a mount can see that it exists.

### 3. The covered directory is never listed

The parent's own row at a mount point is dropped from every listing, for every caller, the system actor included. It is dropped before any rows are merged, so none of its fields reach the result. A listing that fails and is returned with the rows it has drops it too. Its rights decide only who may change the mount.

Only `ls`, `tree` and `glob` drop it, where the rows are known to be live. Every verb drops the rows strictly beneath a deeper mount, as before. A deleted row at a mount path in a trash view is not the covered directory, and it is kept, and so is a graph node at a mount path in `traverse`. A `glob` keeps a row at a mount path that carries `deleted_at`.

Reason: the covered directory is unreachable while mounted on both systems, and one path must not show two entries.

### 4. A directory that leads to a mount point is on the road

A directory in the parent that lies above a mount point is listed as a bare row in its own parent. `ls`, `stat`, `tree`, `glob` and `locate` of it answer as they do for a road directory, even where the parent's storage answered `not_found`. The kernel knows these directories from its mount table, which it keeps as a set in memory.

The rule is that a bare row stands in for a `not_found`, and for nothing else, and each target is judged on its own errors. An error is raised for its `data["vfs.target"]`, or for its own path when it has no target, and when the call names one path every error is raised for that path. A failure that is not a `not_found`, such as a refusal, withholds the bare row of the target it was raised for, and that target's answer stands as the storage gave it. A failure that cannot be tied to any target, because it names no path, or names the storage's own root with no target as a transport failure does, is a failure of the whole answer, and then no target gets a bare row. Otherwise each `not_found` raised for the directory is dropped, whatever part of the path it names, and the storage's other rows and records are kept. A covered directory is always dropped. Where the storage returns its own row for the directory, that row is shown and no bare row is added. Where it returns no row, the directory shows bare. `locate` says the directory exists and is a directory, unless the storage refused with something other than `not_found`, and then it reports that refusal in `note`. One function decides this for `stat` and for `locate`, and both read the error with the mount's path put back.

The directory shows to every caller whose listing succeeds, the caller who holds nothing in the mount included. Decision 2 already shows that caller the mount's full path.

`tree` shows the directories above a mount only when the mount itself lies within `max_depth`. A storage does the same for a plain directory, which shows only above a row that is within the depth.

One thing is left as it was. `stat` of a path beneath such a directory, where the path itself is missing, still names the directory as the first missing part of the path.

Reason: on both systems a caller reaches a mount by its path through parents they cannot read, given walk or search permission. VFS has no such permission. The road is what serves that purpose in a plain tree, and decision 2 already makes the full path of every mount visible.

This is the one place where the precedent cannot be copied as it is. VFS applies its own rule for a plain directory here.

### 5. A refusal of the listed directory stands

When the parent refuses `ls` or `tree` of the addressed directory with anything other than `not_found`, the call is refused as it is today. The anonymous caller on a closed root is refused with `unauthenticated` and learns no mount names. `glob` keeps the rules it has today for a region where one branch fails and others answer. A mount point whose parent failed the `glob` is left out, as decision 2 says, so the anonymous caller on a closed root learns no mount name from `glob` either.

In `ls` and `tree`, the parent and the children are asked at the same time. When the parent refuses, the children's answers are discarded. A `glob` asks the children after the storages answer, and only for the mount points it keeps, as decision 11 says.

Reason: on both systems a caller who may not read a directory gets no listing of it.

### 6. A child that gives no row still shows, as a bare row

A mount shows a bare row when its storage gives none that is a directory. There are five cases.

| The child | The row | A record |
|---|---|---|
| Refuses the caller, with `not_found`, `permission_denied` or `unauthenticated` | Bare | None |
| Cannot answer `stat`, by its capabilities | Bare, and the child is not asked | None |
| Answers and returns no row for its root | Bare | The child's own records, if it gave any |
| Answers with a row for its root that is not a directory | Bare | The child's own records, if it gave any |
| Fails in any other way, such as a transport error, with or without a row | Bare | One of severity `warning` for each failure, which names the mount at its mount path, also when the failure names no path |

This table is for the child. A parent that fails is decision 4's case: its failure stands, and no bare row is made up for a directory above a mount. In `tree`, each mounted storage's own answer is judged by decision 4's rule before any directory it holds is added, so a mounted storage that failed adds no directory and no mount point beneath it.

In `tree`, a mount whose own `tree` fails is reported once, by the warning of that `tree`, and the failure of its `stat` is not reported as well. A child whose `stat` raises an ordinary exception, and not a transport error, has a fault. The exception is raised out of the listing, as the kernel raises a fault in a storage out of any verb.

The earlier text of this decision left a failing child out of the listing. It was changed while the spec was built.

Reason: decision 2 says the name always shows, and leaving a failing mount out would make the set of paths in a listing depend on the health of a backend. Plan 9 keeps the entry when the `stat` of what is mounted fails, and a dead network mount on Linux still shows its name in the directory above.

No time budget is added. A listing waits for each child, as `tree` and a search over several mounts already wait for each mount.

### 7. Each verb keeps its own order

- `ls` puts the row of a mount, and the bare row of a directory that leads to one, in path order among the storage's own rows. The storage's rows keep the order the storage gave them.
- `tree` returns the rows of the addressed storage first, and then each mount in table order. A mount's own row comes first among its rows. A directory between a mount and the target comes among the rows of the mount that stores it, whether or not that mount was asked for its `tree`.
- `glob` returns the rows of the named roots first, then the mount points and the directories above them that match, in path order, then the rows of the mounts as before. The order never depends on the order of a set or on the order the mounts were added in, so the rows kept under `max_count` do not either.
- A covered row cannot cost the caller a row under `max_count`. The mount's own row is merged ahead of the parent's rows, so it takes the place the covered row took.
- In `tree`, a mount point exactly at `max_depth` shows its row and is not descended. A mount point deeper than `max_depth` is not asked at all.

### 8. The rule covers every route to a listing

- An explicit root of `glob` that is a mount point already answers from the child, and stays so. A root that is a directory above a mount point is no longer an error for a caller who holds nothing on it.
- `stat` with `observations` is one storage call for the whole batch, as before. It follows decision 4's rule, so each target is judged on its own errors. Each failure counts against the path it was raised for, which is its `data["vfs.target"]`, or its own path when the storage set no target. A `not_found` names the first part of the path that is missing, so two targets can name the same directory, and the target is what tells them apart. A failure that is not a `not_found` withholds the bare row of its target only, and one that cannot be tied to a target withholds every bare row. A batch that names one path is judged as that one path is, and gives the same rows and records. Every other `not_found` raised for a directory above a mount point is dropped. That directory gets one bare row for each time the batch names it beyond the rows the storage gave for it, so a directory named twice gives two rows. A `not_found` raised for any other target, or for none, stands. The failures are matched in one pass, so a batch costs its length.
- `ls` with `observations` answers each directory that holds or leads to a mount point on its own, once however often the batch names it. The other rows go to the storage in one call, as before. `ls` returns the listing of such a directory once for each time the batch names it, after the rows of the other targets of the same mount. A batch that spans several mounts returns each mount's rows together, so the order holds within one mount only. An error is recorded once for a directory, however often the batch names it.
- `glob` over rows in hand returns the rows it was given, unchanged.
- A trash view lists the deleted rows of the storage it addresses, unchanged.

### 9. Nothing is added to the storage protocol

One `stat` of the child's root supplies each row. No new storage call, no new argument and no new public name is added.

### 10. The grant verbs are not aimed at the covered directory

An earlier draft gave the grant verbs a keyword, `mount_point=True`, to reach the rights of the covered directory. It is dropped.

Reason: on Unix a permission change at a mount path changes the mounted root, and the covered directory's permissions cannot be reached until the mount is removed. VFS behaves that way today. The right to change a mount is given before the mount is added, or on a directory above it.

A decision taken for that draft, that `remove_mount` deletes the rights rows on the mount point, goes with it. On Unix the covered directory keeps its permissions through a mount and an unmount.

### 11. `glob` judges a mount point itself

No storage returns the row at a mount point. The parent holds the covered directory, which is never shown, and the child's own `glob` leaves its root out. So the kernel tests each mount point, and each directory above one, against the call. A path is kept when it lies beneath a root and an arm matches it. It is dropped when an exclusion, an extension filter or `kind` rules it out.

The test is run by the matcher a storage uses on its own rows, in one hop to the thread pool, within the time budget each matching stage has. A stage that reaches the budget leaves those rows out and adds one `truncated` warning. A call whose roots hold no mount point beneath them makes no hop. The mounted roots are asked for their `stat` after the storages answer, and only for the mount points that decision 2 keeps, or for the first `max_count` of them. So no mounted root is asked for a path the caller does not get, and a limit is never spent on a mount point that is then left out. No storage is called once the kernel is closed. Every call on a storage goes through one seam in the kernel, and it answers the closed refusal, `backend_unavailable`, when the mount table is empty. A mounted root refused this way shows bare with a warning, as any mounted root that cannot answer does.

Reason: the same matcher gives the same answer a plain directory at that path would get. A pattern that ends in `**` does not match the directory it names, for example, and a second matcher could disagree on that.

## Cost

The mount table is in memory, so finding the mounts in a listed directory costs no storage call. A directory that holds no mount point costs what it costs today.

Counted on the in-memory storage, which is the database storage on SQLite, with the rights cache warm.

| Call on the child | Named caller | System actor |
|---|---|---|
| `stat("/")` | 1 transaction, 3 `SELECT` | 1 transaction, 1 `SELECT` |

| Listing | Storage calls today | Under this design |
|---|---|---|
| `ls` of a directory with `k` mount points | 1 | 1 + `k` |
| `tree` over `m` mounts within its depth | 1 + `m` | 1 + 2`m` |
| `glob` whose pattern matches `M` mount points | as planned today | `M` more |

Every call is a read. Nothing is written and no lock is taken. The cost grows with the number of mounts and never with the size of the corpus.

At the reference deployment a listing is one of about 150,000 verb calls a day. With 20 mounts at the root, one `ls("/")` adds 20 calls and about 60 statements. The number of mounts in a deployment is an assumption. No measurement exists.

The risk that is not priced is latency. A listing is as slow as its slowest child, and decision 6 adds no time budget. A `glob` that matches mount points waits for the storages and then for the mounted roots, which is one round trip more than asking them at the same time.

`ls` and `stat` of a path first look the path up in the set of directories above a mount, which the kernel works out when the mount table changes. A kernel with one mount has an empty set. A batch of 10,000 rows costs one set lookup for each row. The directories each mount stores, and the mounts in each directory, are worked out at the same time. The filter that drops a row beneath a deeper mount looks up the prefixes of the row's own path in the set of mount paths, so a row costs the depth of its path and never the number of mounts.

`ls`, `stat` and `tree` take one hop of the call's budget, as the searches do. A listing of a parent asks each mount in it for the row of its root, so a storage that wraps the kernel it is mounted in would loop. With the hop, the loop ends in `budget_exhausted`, and the mount shows bare with that warning. `read` and the verbs that change something take no hop. Only a verb's own entry into the kernel takes a hop. The probe of a search's roots runs inside the hop the search holds and takes none, so a budget of one serves a search with roots.

Each listing reads one copy of the mount table, made when the table changes. A mount added or removed while a listing waits on a storage changes the next listing and never that one. `glob`, `grep` and `search` take the copy when they start, and it serves the plan, the resolution of each root, the probes, the calls on the storages, the filter and the merge. The kernel finds the mount of any path with the same function. It cuts the path at each `/` and looks each prefix up in the table as plain text, because a prefix of a checked path is never checked again. A table that holds only the root answers at once. Finding the mount of a 1,024-byte path makes no call to the path check, and a batch of 10,000 rows costs the depth of each row's path and not the number of mounts. The permission maps of each row are still found by a scan of the table.

## Left as it is

- **A time budget for a child.** None is added. `tree` and a search over several mounts wait for each mount with no budget of their own, and a listing now waits in the same way. A budget for every call that reaches several mounts is a change of its own.
- **The listing cursor.** Paging is not built yet. `ls` returns its rows in path order within a directory, so a row put in at its place fits a path key. `tree` and `glob` have no single path order.

## Tests

In `tests/base/test_mount_listing.py`, written and seen failing before the code. Counts are of calls recorded by a storage double, never of time.

Four tests pinned the earlier behaviour and were rewritten. One is `test_bind_point_row_is_served_by_the_parent` in `tests/base/test_glob_namespace.py`, which is now `test_a_pattern_that_ends_at_a_mount_point_returns_the_mounted_root`. Three are in `tests/base/test_mounts.py`: `test_tree_budgets_depth_across_mounted_regions`, `test_tree_skips_incapable_mount_with_info_record` and `test_tree_budgets_depth_from_a_non_root_target`. The comment of `test_shadow_filter_drops_ls_rows_beneath_a_deeper_mount` changed and its assertion was made exact.

Each fixture states what was shared: the grants, the owner, the posture, which rows exist, and which storage received each grant.

- A caller granted `read` in the child sees the mount in `ls`, `tree` and `glob("/*")` of the parent, with no grant in the parent.
- A caller granted only deeper in the child, a caller who owns a row in the child, and a caller who holds nothing in it each see the mount as a bare row.
- For a caller granted at the top, a caller granted deeper and a caller who owns a row, a mount and a plain directory with the same contents give the same paths in `ls`, `tree` and `glob`. The mount's own row is the one path a mount may add, and it adds it in `tree` to depth 1, where a plain directory shows nothing for a caller whose rows lie deeper.
- A caller who holds nothing sees the mount and does not see the plain directory.
- The row at a mount point in `ls`, `tree` and `glob` equals the row `stat` of the mount point returns, for a named caller and for the system actor.
- Each listing returns one row at a mount point, and it carries no field of the covered directory.
- `columns` reaches the child, and the row keeps the child's field mask.
- `ls` puts a mount in name order among files.
- With a mount at `/a/b` and a closed root, `ls("/")` shows `/a` bare, `ls("/a")` shows `/a/b`, `stat("/a")` is a bare row, `glob("/*")` returns `/a`, and `locate` says `/a` exists. This holds for a caller granted in the mount and for one who holds nothing.
- `tree` shows the directories above a mount it reaches, and none above a mount deeper than `max_depth`.
- A directory above a mount that the caller may see keeps its own stored row.
- A batch of `stat` or `ls` answers for a directory above a mount and keeps the `not_found` of a missing path.
- A `not_found` beneath a directory above a mount is a miss like any other: `ls`, `tree` and `stat` of the directory answer for it.
- A `glob` beneath a directory above a mount does not fail on that directory.
- The anonymous caller on a closed root is refused `ls("/")` and `tree("/")` with `unauthenticated`, and gets no rows.
- A mount that refuses the caller shows bare with no record. A mount that returns no row for its root shows bare. A mount that cannot `stat` shows bare and is not asked.
- A child that raises a transport error shows bare with one `warning` record that names the mount path, in `ls`, `tree` and `glob`, and the other rows are returned.
- A mount point exactly at `max_depth` shows its row and is asked for no `tree`.
- `glob("/*", max_count=1)` returns one row, and `max_count=2` returns the mount and the file beside it.
- The filters of `glob` apply to the row at a mount point: `kind`, `globs_not`, `ext`, a pattern that ends in `**`, and a name arm that does not match.
- `glob` beneath a root returns the mount points beneath it, by a name arm and by a path arm, and a root is never beneath itself.
- Mount points that were not judged within the time budget are left out with one `truncated` warning.
- `ls` with `observations` that names a directory twice returns its listing twice, and a missing directory in the same batch keeps its own `not_found`.
- Listing a directory that holds no mount point makes one storage call, and so does `stat` of it.
- Listing a directory with three mount points makes one `stat` call on each, and one `ls` call on the parent.
- A nested mount is listed by the mount that holds its covered directory.
- A batch of `stat` keeps the miss of the path that is missing beside directories above mounts, returns a directory named twice twice with no error, keeps each miss beneath such a directory, keeps a miss that names no path, and matches its misses in a count of checks linear in the batch.
- A failed `ls` or `tree` never returns the covered directory.
- A root that fails its probe hides no mount point beneath another root, a probe failure that names no root hides only the mount points of the mount probed, and a parent that fails one root keeps the mount points beneath its other roots.
- Under `max_count`, a mount point that is left out costs no `stat` and no place.
- `glob`, `grep` and `search` with roots pass on a budget of one hop. A hop is given back when the storage raises and when the call is cancelled.
- A row that comes with a failure is not shown at a mount point.
- `locate` says a directory above a mount exists, and `stat` shows it, when its storage answers with a miss beneath it or one too deep to name. Both report a refusal of any other kind.
- A storage that cannot answer gets no row made up for a directory above a mount, in `stat` of a path, `stat` of a batch, `ls`, `tree` and the probe of a `glob` root.
- A batch that names a directory above a mount twice, where the storage gave one row and one miss for it, returns two rows and no error.
- A failed probe of a root keeps the root's own row and hides what lies beneath it, and a failed `glob` at the same path hides the path too.
- A `glob` that finds the kernel closed after its storages answer asks no mounted root, with a limit and without, and the mount shows bare with a warning.
- A `close()` that lands beside `ls`, `tree`, a batch of `stat` or `glob`, or while the mounted roots are asked, is followed by no call on any storage.
- Each target of a batch is judged on its own errors, a failure no target can claim withholds every bare row, and one path and a batch of that path give the same answer.
- `tree` adds no directory for a mounted storage whose own `tree` failed, and treats its miss as a miss.
- A table that holds only the root finds the mount of a path without one step up it.
- A `glob` under a limit passes the caller's `columns` to the mounted storage.
- Finding the mount that holds a 1,024-byte path makes no call to the path check.
- A mount replaced while `glob`, `grep` or `search` plans its scope leaves that call as it began, and the new storage is not asked.

## Scope

In: `ls`, `tree` and `glob` at a directory that holds or leads to a mount point, `stat` and `locate` of a directory that leads to one, the row filter that drops entries hidden by a deeper mount, their tests, and the docs.

Out: `grep` and `search`, which return files. They share the root probe of `glob`, so a root that is a directory above a mount point is no longer an error for them either. The mount methods and who may call them. The grant verbs. The storage protocol.

## What the docs must say

- A mount shows in the listing of its parent to every caller who can list that parent. Its path is not a secret.
- What a caller sees of the mount, and of everything in it, is decided by the mounted storage.
- A grant at a mount path is a grant in the mounted storage. One grant shares a mount.
- The rights on the directory beneath a mount decide only who may add, remove or change that mount. They cannot be changed while the mount is on.
- A posture does not cross a mount. A new mount is open to everyone until its own posture is set.

Pages: `documentation/reference/access-levels.md`, `documentation/maintainers/mounts.md`, the Mount term in the glossary, and the docstrings of `ls`, `tree` and `glob`.

## Earlier decisions this reverses

- An archived spec on mount visibility ruled that a row at a mount point is made by the kernel with no call to the mounted storage, for cost. This design makes one `stat` call for each such row.
- An archived spec on stored mount points ruled that the row is the stored directory. This design replaces it with the mounted root.

## Not checked

- The server engines. Every probe ran on the in-memory storage.
- A child that wraps a remote kernel.
- The trash view of a parent after a mount is added over a path that held deleted rows.
- Whether the mount table is public on Plan 9 and Linux was not read in the clones. It is assumed from general knowledge that a process can read its own mount table on both.

## One line

In a listing, the row at a mount point comes from the mounted storage and its name is never hidden, as on Plan 9 and Linux, and the directories above a mount show bare so that a caller can walk to it.
