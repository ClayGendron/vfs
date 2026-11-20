# A mount is listed as a directory is

This spec is drafted and not yet fit to build. It is the third draft. The second was reviewed twice on 2026-11-18 and found not sound, and this draft answers those reviews. It is built on its own branch, after the branch `public-names-follow-the-naming-rules` has landed.

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

Reason: on Plan 9 and on Linux the mounted root's permissions never hide the name. It also makes the listing agree with `stat` and `locate`, which show every mount to every named caller today.

Consequence to state in the docs: a mount's path is not a secret. A caller who holds nothing in a mount can see that it exists.

### 3. The covered directory is never listed

The parent's own row at a mount point is dropped from every listing, for every caller, the system actor included. It is dropped before any rows are merged, so none of its fields reach the result. Its rights decide only who may change the mount.

Reason: the covered directory is unreachable while mounted on both systems, and one path must not show two entries.

### 4. A directory that leads to a mount point is on the road

A directory in the parent that lies above a mount point is listed as a bare row in its own parent. `ls`, `stat` and `tree` of it answer as they do for a road directory, even where the parent's storage answered `not_found`. The kernel knows these directories from its mount table, so no storage is asked.

Only a `not_found` is replaced. A refusal of any other kind stands.

Reason: on both systems a caller reaches a mount by its path through parents they cannot read, given walk or search permission. VFS has no such permission. The road is what serves that purpose in a plain tree, and decision 2 already makes the full path of every mount visible.

This is the one place where the precedent cannot be copied as it is. VFS applies its own rule for a plain directory here.

### 5. A refusal of the listed directory stands

When the parent refuses `ls` or `tree` of the addressed directory with anything other than `not_found`, the call is refused as it is today. The anonymous caller on a closed root is refused with `unauthenticated` and learns no mount names. `glob` keeps the rules it has today for a region where one branch fails and others answer.

The parent and the children are asked at the same time. When the parent refuses, the children's answers are discarded.

Reason: on both systems a caller who may not read a directory gets no listing of it.

### 6. A child that cannot answer is left out, with a warning

When a child fails, or does not answer within the listing's time budget, its row is not shown. A record of severity `warning` names the mount at its mount path, and the rest of the listing is returned.

Reason: `tree` already treats a failing mount among answering mounts this way. A mount's name is not a secret, so the record may name it. Without a time budget, one stuck child would hold every `ls` of the directory above it.

### 7. Each verb keeps its own order

- `ls` puts the row in place of the covered row, in name order within the listed directory.
- `tree` and `glob` keep the order in which they merge answers today.
- A covered row is removed before it can count against `max_count`.
- In `tree`, a mount point exactly at `max_depth` shows its row and is not descended.

### 8. The rule covers every route to a listing

- An explicit root of `glob` that is a mount point already answers from the child, and stays so.
- `ls` with `observations` applies the rule to each directory it lists, keeps one answer for each input row, and keeps each row's own error.
- `glob` over rows in hand returns the rows it was given, unchanged.
- A trash view lists the deleted rows of the storage it addresses, unchanged.

### 9. Nothing is added to the storage protocol

One `stat` of the child's root supplies each row. No new storage call, no new argument and no new public name is added.

### 10. The grant verbs are not aimed at the covered directory

An earlier draft gave the grant verbs a keyword, `mount_point=True`, to reach the rights of the covered directory. It is dropped.

Reason: on Unix a permission change at a mount path changes the mounted root, and the covered directory's permissions cannot be reached until the mount is removed. VFS behaves that way today. The right to change a mount is given before the mount is added, or on a directory above it.

A decision taken for that draft, that `remove_mount` deletes the rights rows on the mount point, goes with it. On Unix the covered directory keeps its permissions through a mount and an unmount.

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

The risk that is not priced is latency. A listing is as slow as its slowest child, which decision 6 bounds.

## Not yet decided

- **The step that gives `glob` its mount-point rows.** `glob` gives each mount a pattern of its own, and a child's own `glob` leaves its root out. A step beside the root probes must test each mount path against every arm, the exclusions, the extension filters and the kind.
- **The time budget in decision 6.** Whether it is the deadline listings already carry, or its own.
- **Whether a road directory under decision 4 is listed when the caller is refused at the mount itself.** Decision 2 says the mount's name shows to every named caller, so the directories above it would show too.
- **The listing cursor.** Paging is not built yet. `ls` sorts by name within a directory, so a row replaced in place fits a path key. `tree` and `glob` have no path order today.

## Tests, written before the code

In a new `tests/base/test_mount_listing.py`. Counts are of calls recorded by a storage double, never of time.

Three tests pin today's behaviour and are rewritten: `test_bind_point_row_is_served_by_the_parent` in `tests/base/test_glob_namespace.py`, and `test_tree_budgets_depth_from_a_non_root_target` and `test_shadow_filter_drops_ls_rows_beneath_a_deeper_mount` in `tests/base/test_mounts.py`.

Each fixture states what was shared: the grants, the owner, the group, the posture, which rows exist, and which storage received each grant.

- A caller granted `read` in the child sees the mount in `ls`, `tree` and `glob("/*")` of the parent, with no grant in the parent.
- A caller granted only deeper in the child, a caller who owns a row in the child, and a caller who holds nothing in it each see the mount as a bare row.
- For each of those callers and each verb, a mount and a plain directory with the same contents give the same paths, except that the caller who holds nothing sees the mount's bare row.
- The row at a mount point in `ls` of the parent equals the row `stat` of the mount point returns, for a named caller and for the system actor.
- `ls` and `tree` return one row at a mount point, and it carries no field of the covered directory.
- `columns` reaches the child, and the row keeps the child's field mask.
- With a mount at `/a/b` and a closed root, `ls("/")` shows `/a` bare, `ls("/a")` shows `/a/b`, and `stat("/a")` is a bare row.
- The anonymous caller on a closed root is refused `ls("/")` with `unauthenticated`.
- A child that raises a transport error is left out with one `warning` record that names the mount path, and the other rows are returned.
- A mount point exactly at `max_depth` shows its row and is not descended.
- `glob("/*", max_count=1)` returns a row the caller may see, and does not spend its one slot on a covered row.
- `ls` with `observations` that names a directory twice returns its listing twice, and a missing directory in the same batch keeps its own `not_found`.
- Listing a directory with no mount point makes one storage call.
- Listing a directory with `k` mount points makes `k` more calls, and no `holds` call.
- A nested mount is listed by the mount that holds its covered directory.

## Scope

In: `ls`, `tree` and `glob` at a directory that holds or leads to a mount point, `stat` of a directory that leads to one, the row filter that drops entries hidden by a deeper mount, their tests, and the docs.

Out: `grep` and `search`, which return files. The mount methods and who may call them. The grant verbs. The storage protocol.

## What the docs must say

- A mount shows in the listing of its parent to every named caller. Its path is not a secret.
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
