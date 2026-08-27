# Research — The single creation chokepoint: how filesystems create things

> **Note (extracted 2026-07-16):** this memo was extracted from story 031's
> `explanation.md`
> (`specs/archive/031-unified-entry-creation-chokepoint/explanation.md`,
> last committed 2026-06-12, `4be7c24`) during the archive mining pass, and
> is dated to the original work. It preserves the precedent survey — one-door
> entry creation across Linux, FreeBSD, Plan 9 / 9P, FUSE, and SQLite — that
> grounded the story's `_mint_entries` design. The story-specific how-to
> recipes and the resolved design decision stayed with the story's
> `design.md`; VFS code citations below reference the pre-rebuild tree (now
> archived under `src2/`).

- **Date:** 2026-06-12
- **Status:** extracted record (preservation, not new research)
- **Scope:** the abstractions behind a single, invariant-enforcing
  entry-creation path, drawn from the reference implementations checked out
  under `~/Git/Repos` (Linux, FreeBSD, Plan 9 / 9P, FUSE, SQLite), and mapped
  back onto VFS. Every citation was grep-verified against the local
  checkouts; line numbers drift across versions — the **routine names** are
  the durable part.

**The one idea.** In a mature filesystem there is exactly *one* path through
which any object comes into existence, and that path enforces every invariant
*before* the object is actually written. There is no second door. Bugs,
security holes, and corruption come from second doors — code that writes an
object without passing the gate. VFS at the time of this survey had second
doors (chunk creation, version creation); the design exercise was to collapse
them into one.

## 1. The seven abstractions

These build on each other; read them in order the first time.

### 1.1 Everything is a file (the uniform object model)

Unix's foundational move: files, directories, devices, pipes, sockets — all
are manipulated through *one* set of operations (`open`/`read`/`write`/
`close`). Plan 9 took it to the limit: not only is everything a file, but the
*only* interface between programs and resources is a file protocol (9P). A
process, a network connection, the window system — all are file trees served
over 9P.

**Why it matters.** A uniform object model means you write the hard
machinery — naming, permissions, lifecycle, transactions — *once*, and every
kind of thing inherits it. The cost of adding a new kind of object is near
zero, because it's "just a file." The danger is the inverse: if some kinds
quietly opt out of the uniform machinery, you've lost the entire benefit and
added confusion on top.

**VFS already lives here.** Every object is a row in one table,
discriminated by `kind ∈ {file, chunk, edge, directory}`. Versions are
entries. Connections (edges) are entries. This is the "everything is a file"
doctrine made literal — *which is exactly why every kind must share one
creation path.*

### 1.2 The single creation choke-point

In Linux you cannot create a file. You can only call `vfs_create()`, which
*then* — and only if a battery of checks passes — calls into the concrete
filesystem to do the actual mint. The same is true of `vfs_mkdir()`,
`vfs_mknod()`, `vfs_link()`, `vfs_symlink()`. Each is a narrow funnel:
generic preconditions on top, one dispatch to the on-disk layer at the
bottom.

**Why it matters.** Invariants enforced *inside the funnel* cannot be
forgotten, because there is no way to reach the mint except through the
funnel. Contrast a codebase where "create a directory if missing" and "check
permissions" are open-coded at each call site: the third time someone needs
to create an object, they copy the happy path and forget the checks. That
third site is a second door.

**The litmus test for a choke-point:** *can any code in the system bring an
object into existence without calling this function?* If yes, it is not a
choke-point yet — it is merely a popular helper.

### 1.3 The generic/specific split (and op-vectors)

The funnel has two layers, and the boundary between them is the single most
important structural idea in filesystem design:

- **Generic layer** (the VFS): enforces invariants that are true of *all*
  filesystems — permission, parent-must-exist, name rules, reference
  counting.
- **Specific layer** (ext4, tmpfs, btrfs…): knows how to actually lay bytes
  on *this* medium. Reached only through a **table of function pointers** —
  `inode_operations` in Linux, the *vnode op vector* (`VOP_CREATE`) in BSD,
  the op table in FUSE, the four verbs in 9P.

`vfs_create()` does the generic checks, then calls `dir->i_op->create(...)`.
The `->create` slot is different for each filesystem; the checks above it are
identical for all. ext4 and tmpfs mint *completely differently* (journaled
disk extents vs. a kernel radix tree) yet both sit behind the one
`vfs_create`.

**Why it matters — and the subtle lesson for VFS.** The kernels unify the
**gate**, not the **mint**. They never try to force ext4 and tmpfs to write
bytes the same way; they only force them through the same checks. This is
the answer to "won't a single creation path wreck my bulk-insert
performance?" — no, because the *mint* is allowed to stay polymorphic. What's
unified is the gate above it.

### 1.4 Name resolution to the parent (namei / walk-to-parent)

You never create an object "at a path." You **walk** the path to its
**parent directory**, and create the object *inside that parent*. Linux
resolves `/a/b/c` down to the parent dentry `b` plus the final name `c`
(`namei`), then creates `c` within `b`. BSD's `vn_open_cred` resolves to
`ni_dvp` (the parent *directory vnode*) and calls `VOP_CREATE(ni_dvp, ...)`.
9P models creation as `Twalk` (to the parent fid) followed by
`Tcreate(name)`. FUSE's create ops are literally typed
`(parent_inode, name, mode)`.

**Why it matters.** Creation-by-parent is what makes "does the parent exist?
are you allowed to write *into* it?" the natural, unavoidable questions. The
parent is the unit of authorization and of existence. A system that creates
"at a full path" with no notion of the parent has nowhere to hang those
questions — so it tends to skip them.

### 1.5 The permission gate on the parent (`may_create`)

Before the mint, Linux calls `may_create_dentry()`. It checks, in order: the
child must not already exist (`-EEXIST`), the parent must be a live directory
(`-ENOENT`), the caller's uid/gid must be representable, and — the crux — the
caller must hold **write + execute on the parent**. 9P's `screate` checks
`hasperm(parent, uid, AWRITE)`. BSD runs the MAC hook
`mac_vnode_check_create` before `VOP_CREATE`.

**Why it matters.** The permission decision is made on the **parent**,
**before the object exists**, **upstream of the only dispatch.** You cannot
create then check, or check in some-but-not-all call sites. The gate is
structurally upstream, so it cannot be skipped.

### 1.6 The single commit primitive (one writer for user *and* system data)

Drop below the filesystem into the storage engine and the pattern repeats.
Every row SQLite ever writes — your tables, its own `sqlite_master` catalog,
the b-tree pages of every index — goes through **one** function:
`sqlite3BtreeInsert()`. The bytecode op `OP_Insert` is just a thin marshaller
in front of it. There is no "fast path for internal rows." Cross-cutting
concerns (update hooks, the change counter, `lastRowid`) live *at* that
choke-point, precisely because it is the only door.

**Why it matters.** This is abstraction 1.2 one layer down, and it carries
the same lesson: *internal/derived data goes through the same writer as user
data.* SQLite does not give its own catalog a privileged side-channel. If it
did, every invariant maintained at the insert boundary (and every future
one) would have to be duplicated and kept in sync — the classic source of
"the index disagrees with the table" corruption.

### 1.7 Derived vs. authored data — and the choice to refuse the distinction

There is a deep tradition of treating *derived* or *internal* data
differently from *user-authored* data:

- **SQLite FTS5** stores its inverted index in **shadow tables**
  (`%_content`, `%_data`, `%_idx`, …): real tables, same database, same
  transaction, but *outside the user's logical namespace*. The engine
  recognises them by name (`fts5ShadowName`) and protects them from direct
  writes.
- **procfs / sysfs** present files that have **no backing store at all** —
  synthetic inodes materialised on demand from kernel state
  (`proc_register` builds an in-memory tree). They have a *different
  lifecycle*: no `unlink`, no user creation, regenerated from live state.
- **Extended attributes** (`__vfs_setxattr`) attach metadata *to* an inode
  rather than as a *child* of it — a side-channel, not a namespace entry.

The common doctrine: *derived data lives in the same transaction but a
separate region, with a minimal, non-user lifecycle.* By that doctrine, VFS
chunks — regenerable from their parent file, content-addressed, versioned as
slaves of the file, and hidden from `ls` — look exactly like FTS shadow
rows, and "should" escape the user lifecycle entirely.

**The design decision (VFS's) was to refuse this split.** Under "everything
is an entry," a chunk is not a shadow row; it is a first-class entry that
happens to be machine-authored. The price is that the choke-point must be
expressive enough to say "this kind is machine-authored: auto-create its
parents, don't permission-check it as user data" — a per-kind *policy* —
rather than letting chunks slip out a side door. The benefit is one object
model, one query surface, one lifecycle to reason about. This is a genuine
fork in the road that every reference system resolves the *other* way, so it
is worth holding consciously.

## 2. Reference — the systems, precisely

Dry facts. Each row: the choke-point routine, what it enforces, where the
generic layer dispatches to the specific layer. Verified against the local
checkouts (`~/Git/Repos`).

### 2.1 The creation choke-points

| System | Choke-point | Permission gate | Dispatch to specific layer | Location |
|--------|-------------|-----------------|----------------------------|----------|
| **Linux VFS** | `vfs_create()` / `vfs_mkdir()` | `may_create_dentry()` (write+exec on parent, `-EEXIST`, dead-dir) | `dir->i_op->create(...)` / `->mkdir(...)` | `linux/fs/namei.c:4184`, `:5232`; gate `:3733`; dispatch `:4204`, `:5261` |
| **FreeBSD VFS** | `vn_open_cred()` → `VOP_CREATE` | `mac_vnode_check_create()` before the op | `VOP_CREATE(ni_dvp, ...)` — addressed by **parent** vnode | `freebsd-src/sys/kern/vfs_vnops.c:253`, create at `:320` |
| **Plan 9 / 9P** | `screate()` (`Tcreate`) | `hasperm(parent, uid, AWRITE)`; parent must be a dir (`Ecreatenondir`) | `srv->create(...)` | `plan9port/src/lib9p/srv.c:441`; perm `:407`/`:449`; dispatch `:451` |
| **FUSE (lowlevel)** | op table slots | request carries caller creds | `(req, parent, name, mode)` — create *cannot be expressed* except by parent+name | `libfuse/include/fuse_lowlevel.h:378` (mknod), `:393` (mkdir), `:982` (create) |

The structural invariant across all four: **gate first, single dispatch
second, no other door.** FUSE enforces it at the *type level* — you literally
cannot phrase a create without a parent inode.

### 2.2 The storage-engine commit primitive

| System | Single writer | What it proves |
|--------|---------------|----------------|
| **SQLite** | `sqlite3BtreeInsert()` (`sqlite/src/btree.c:9412`), fronted by `OP_Insert` (`src/vdbe.c`) | User tables, the `sqlite_master` catalog, and every index page insert through the *same* primitive — no privileged path for internal rows |

### 2.3 Derived / internal data

| System | Mechanism | Lifecycle | Location |
|--------|-----------|-----------|----------|
| **SQLite FTS5** | shadow tables (`%_content`, `%_data`, `%_idx`, …) | same DB + txn, outside user namespace, recognised by name, write-protected | `fts5ShadowName()` `sqlite/ext/fts5/fts5_main.c:3709`; registered as `xShadowName` `:3784` |
| **Linux procfs** | synthetic inodes, in-memory tree | no backing store; no user create/unlink; regenerated from kernel state | `proc_register()` `linux/fs/proc/generic.c:390` |
| **Linux xattr** | metadata attached *to* an inode | side-channel on an object, not a child entry | `__vfs_setxattr()` `linux/fs/xattr.c:202` |

## 3. Tutorial — trace one create through the Linux kernel

Follow along in `linux/fs/namei.c`. Goal: see how `mkdir("/a/b/c", 0755)`
becomes one gated, single-dispatch creation.

1. **Resolve to the parent.** The syscall path resolves `/a/b` to a parent
   dentry and isolates the final component `c`. This is `namei` / `walk`
   (abstraction 1.4). Result: a *parent directory inode* `dir` and a
   *negative dentry* for `c` (a name with no inode yet).

2. **Enter the choke-point.** Control reaches `vfs_mkdir()`
   (`fs/namei.c:5232`). Everything from here is generic — true for ext4,
   tmpfs, NFS alike.

3. **The gate runs first.** `vfs_mkdir` calls `may_create_dentry()`
   (`fs/namei.c:3733`). Watch the order of checks (abstraction 1.5):
   - child already exists? → `-EEXIST`
   - parent is a dead directory? → `-ENOENT`
   - uid/gid representable in this idmap?
   - **`inode_permission(dir, MAY_WRITE | MAY_EXEC)`** — may the caller
     write *into the parent*?

   If any fail, we return *before anything is created*. No half-made object.

4. **The single dispatch.** Only now (`fs/namei.c:5245`) does it check
   `dir->i_op->mkdir` exists, and call it (`:5261`):

   ```c
   de = dir->i_op->mkdir(idmap, dir, dentry, mode);
   ```

   For ext4 this journals a new on-disk inode and directory block; for tmpfs
   it allocates a kernel inode. **The generic gate has no idea which** —
   that's abstraction 1.3. The polymorphism is in this one slot; the checks
   above are shared.

5. **There is no step 5.** There is no other way to make a directory. A
   driver author implements `->mkdir`; they never re-implement the
   permission check, because they are never *reached* without it having run.

**What to take away from the trace:** the kernel did not "create then
validate." It walked to the parent, ran every invariant on the parent, and
*then* made one polymorphic call to lay bytes. The ordering — *gate, then
mint, through one door* — is the whole game.

## 4. How the story consumed this

Story 031 mapped the survey onto VFS as a single internal primitive,
`_mint_entries`, called by every entry-minting site: a generic gate
(path/kind validation, walk-to-parent directory reconciliation,
revival-permission checks, metadata root) above a single staged mint (bulk
`INSERT` over dicts, server-issued integer `id` as identity, `path` as the
before-insert correlation key), running in the caller's transaction and
never committing. The per-kind policy collapsed to one bit — is the kind
user-authored? (`file`/`directory`/`edge`: yes; `chunk`/`version`: no) —
keyed on the principal, so machine-authored kinds pass *through* the same
gate rather than escaping it (the deliberate refusal of the shadow-table
tradition, §1.7). The kernels' gate/mint split answers the ETL-performance
worry: unify the gate, keep the mint a single bulk `executemany` for both
interactive and batch writes. The full resolved design lived in the story's
`design.md`.

## Appendix — where to read each idea in the source

- **Choke-point + gate:** `linux/fs/namei.c` → `vfs_create:4184`,
  `vfs_mkdir:5232`, `may_create_dentry:3733`, dispatch `:4204`/`:5261`.
- **Op-vector / parent-addressed create:** `freebsd-src/sys/kern/vfs_vnops.c`
  → `vn_open_cred:253`, `VOP_CREATE:320`; `libfuse/include/fuse_lowlevel.h:378`.
- **Walk-to-parent + perm-on-parent:** `plan9port/src/lib9p/srv.c` →
  `screate:441`, `hasperm:407`.
- **Single commit primitive:** `sqlite/src/btree.c:9412` `sqlite3BtreeInsert`.
- **Derived-data lifecycles:** `sqlite/ext/fts5/fts5_main.c:3709`
  `fts5ShadowName`; `linux/fs/proc/generic.c:390` `proc_register`;
  `linux/fs/xattr.c:202` `__vfs_setxattr`.
