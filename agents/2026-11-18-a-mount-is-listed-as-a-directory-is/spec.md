# A mount is listed as a directory is

This spec is drafted and not yet fit to build. It is built on its own branch, after the branch `public-names-follow-the-naming-rules` has landed. It replaces an earlier draft that aimed the grant verbs at a mount point. That idea is deferred, and the last section says why.

## Terms

- **Mount point.** The path a mount is attached at, such as `/data`.
- **Covered directory.** The empty directory stored at the mount point. It is an ordinary entry in the storage of the mount above. For a mount at `/data` on the root, it is the entry `/data` in the root's storage.
- **Mounted root.** The root of the storage attached at the mount point. Its own path is `/`, and callers see it as `/data`.
- **Parent.** The storage that holds the covered directory.
- **Child.** The storage attached at the mount point.
- **Listing.** A call that returns the entries inside a directory: `ls`, `tree`, and `glob`.

## Who owns a mount point

The parent owns the place. The child owns what is there.

- The parent decides whether a mount may sit at the path. That covers `add_mount`, `remove_mount` and `update_mount`.
- The child decides everything a reader sees at the path and beneath it.

Today the second line has one exception, and it is the defect this spec removes. In a listing of the parent directory, the row at the mount point is the covered directory, so the parent's rights decide whether a reader sees the mount's name.

## The problem

A mount does not look like a directory to a caller it is shared with.

Executed on 2026-11-18. The root is closed, with posture `none`. A file is at `/data/report.md`. The caller ada is granted `read` at `/data`. The same setup was run twice, once with `/data` a plain directory and once with `/data` a mount whose storage is also closed.

| Call as ada | Plain directory | Mount |
|---|---|---|
| `ls("/")` | `/data` | nothing |
| `tree("/")` | `/data`, `/data/report.md` | `/data/report.md` |
| `tree("/", max_depth=1)` | not run | nothing |
| `glob("/*")` | not run | nothing |
| `stat("/data")` | `/data` | `/data` |
| `ls("/data")` | `/data/report.md` | `/data/report.md` |
| `glob("/**/*.md")` | `/data/report.md` | `/data/report.md` |

With the mount, `ls("/")` hides the folder that was shared, and `tree("/")` returns a file whose parent directory is missing. No error and no warning is returned.

The cause is that a grant made after the mount exists lands in the child. The covered directory in the parent has no row for ada, so the parent does not list it for her.

Two more facts, both executed.

- For the system actor, the row that `ls("/")` returns at `/data` is not equal to the row that `stat("/data")` returns. The first is the covered directory and the second is the mounted root. One path shows two different entries.
- Before the mount exists there is one entry at the path, and a grant there is enough. The defect appears only once the mount is on.

## Decisions

### 1. In a listing, the row at a mount point is the mounted root

`ls`, `tree` and `glob` take the row at a mount point from the child. The row is the one `stat` of the mount point returns, with the mount's path as its path.

Reason: a reader then sees one entry at one path, whichever verb they use. A mount is listed as a directory is.

### 2. The covered directory is never listed

The parent's own row at a mount point is dropped from every listing, for every caller, the system actor included. The parent's rights on the covered directory no longer decide what a reader sees. They decide only who may change the mount.

Reason: one path must not show two entries. This also makes the ownership rule have no exception.

### 3. The child says whether the caller sees its root, through `holds`

For each mount point in a listing, the kernel asks the child `holds(path="/", level="list", authority=caller)`. The row is shown when the answer is yes.

Reason: `stat` cannot be the test. Executed: `stat` of a closed mounted root succeeds for a caller who holds nothing in it, and for a caller who is granted only deeper in it. `holds` tells them apart. It answered yes for a caller granted `read` at the root, and `not_found` for the other two.

This matches a plain directory. A caller granted at `/data` sees `/data` in `ls("/")`. A caller granted only at `/a/b` does not see `/a` in `ls("/")`, which was also executed. The kernel adds no visibility rule of its own. It asks the child the question the parent used to answer.

- The system actor is not asked. It sees every mount.
- A child that declares no grant verb keeps no rights, so its name shows to every caller.
- A child that keeps grants and cannot answer `holds` does not show its name to a named caller, and a record of severity `info` says so.

### 4. A refusal from the parent stands

When the parent refuses the listing itself, the call is refused as it is today. The kernel does not add rows to a listing the parent refused.

Executed: on a closed root, `ls("/")` by the anonymous caller is refused with `unauthenticated`, while a named caller who holds nothing gets an empty, successful listing. So a named caller will see the mounts shared with them in `ls("/")`, and the anonymous caller will still be refused.

Reason: the kernel never turns a storage's refusal into a success.

### 5. A child that cannot be reached is left out, with a warning

When the child fails to answer, its row is not shown, and a record of severity `warning` names the mount at its mount path. The rest of the listing is returned.

Reason: `tree` already treats a mount that fails among mounts that answer this way.

### 6. The row keeps its place

The row is put where the covered directory's row would have been, in path order. In `tree`, a mount point that sits exactly at `max_depth` still shows its row, though the mount is not descended.

### 7. Nothing is added to the storage protocol

`holds` and `stat` exist. No new verb, no new argument and no new public name is added.

## Cost

The kernel's mount table is in memory, so finding the mounts inside a listed directory costs no storage call. A directory that holds no mount point costs nothing more than today.

For each mount point in the listing, the kernel makes one `holds` call and one `stat` call on the child. For the system actor it makes the `stat` only. Both are point reads. They run at the same time as the parent's own listing. No lock is taken and nothing is written.

At the reference deployment a listing is one of about 150,000 verb calls a day. The cost rides on the number of mounts directly inside one directory. The worst case is `ls("/")` on a deployment that attaches every mount at the root. With 20 mounts there, each `ls("/")` adds up to 40 point reads. The number of mounts in a deployment is an assumption. No measurement exists.

`tree` already asks each mount beneath the target. It gains the same two calls for each mount within its depth.

## Not yet decided

- **Whether one call can do the work of two.** `holds` returns no row and `stat` returns no verdict. A storage could return its root row from one call that also judges the caller. That would change the protocol, which decision 7 avoids.
- **How `glob` reaches the rule.** `glob` plans its own fan-out and gives each mount a pattern of its own. Whether the row at the mount point comes from that plan or from the same step `ls` uses has not been read in the code.
- **Whether a child's answer may be cached within one call.** A `tree` over many mounts asks each child twice.
- **What `ls` with `observations` does.** Each listed directory would follow the rule. This has not been checked against how a batch of rows is grouped by mount.
- **The listing cursor.** Paging for `ls`, `tree` and `glob` is not built yet. Its resume key is a path. A row that comes from another storage must sort and resume correctly under it.

## Tests, written before the code

In a new `tests/base/test_mount_listing.py`. Counts are of calls recorded by a storage double, never of time.

- A caller granted `read` in the child sees the mount's name in `ls` of the parent, with no grant in the parent.
- The same caller sees the mount point and the file beneath it in `tree` of the parent.
- The same holds for `glob("/*")`.
- A caller who holds nothing in the child does not see the mount's name. A caller granted only deeper in the child does not see it either.
- For every caller and each of the three verbs, a plain directory and a mount with the same grants give the same set of paths.
- The row at a mount point in `ls` of the parent equals the row `stat` of the mount point returns.
- No listing returns two rows at one path.
- The system actor sees every mount, and the child is not asked `holds` for it.
- A child that declares no grant verb shows its name to every caller.
- A child that keeps grants and has no `holds` is left out for a named caller, with one `info` record.
- A child that raises a transport error is left out, with one `warning` record that names the mount path, and the other rows are returned.
- When the parent refuses the listing, the result is that refusal and no child is asked.
- A mount point exactly at `max_depth` shows its row and is not descended.
- Listing a directory that holds no mount point makes one storage call, as today.
- Listing a directory with `k` mount points makes at most `2k` more calls for a named caller and `k` more for the system actor.
- A nested mount is listed by the mount that holds its covered directory.

## Scope

In: `ls`, `tree` and `glob` at a directory that holds a mount point, the row filter that drops entries hidden by a deeper mount, their tests, and the docs.

Out: `grep` and `search`, which return files. The mount methods and who may call them. Any change to the grant verbs.

## What the docs must say

- A mount shows in the listing of its parent to every caller who holds `list` at the root of the mounted storage.
- A grant at the mount point after the mount is added is a grant in the mounted storage, and it is enough to share the mount.
- The rights on the directory beneath a mount decide only who may add, remove or change that mount.

Pages: `documentation/reference/access-levels.md`, `documentation/maintainers/mounts.md`, the Mount term in the glossary, and the docstrings of `ls`, `tree` and `glob`.

## Deferred: aiming a grant at a mount point

An earlier draft gave `grant`, `revoke`, `grants` and `set_posture` a keyword, `mount_point=True`, that sent the call to the parent's covered directory.

It is deferred, for two reasons.

- It would have fixed the listing by making every share need two grants, one in the child and one on the mount point. Forgetting the second gives the broken listing above with no error.
- With the listing fixed by rule, the keyword serves one job only: giving or taking the right to change one mount after the mount exists. That right can be given before the mount is added, or on a directory above it. The system actor passes every check, and a session has no mount methods.

If it is built later, these decisions of 2026-11-17 apply: a session takes the keyword, and `remove_mount` deletes the rights rows on the mount point.

Prior art read for that draft still holds. Plan 9, Linux, FUSE and FreeBSD each judge a mount change on the covered directory and send ordinary access to the mounted root. On Linux a listing of the parent shows a mount point with the attributes of the mounted root, which is what decision 1 does.

## Not checked

- The server engines. Every probe ran on the in-memory storage.
- A child that wraps a remote kernel.
- Whether `ls("/data")` by a caller granted `read` at `/data` lists a directory that was made by writing a file deeper beneath it. One probe returned no rows there, and it was not followed up.

## One line

In a listing, the row at a mount point comes from the mounted storage and is shown to whoever holds `list` at its root, so sharing a mount takes one grant and a mount is listed as a directory is.
