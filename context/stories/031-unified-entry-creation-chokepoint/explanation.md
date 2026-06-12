# How filesystems create things

*A learning doc on the abstractions behind a single, invariant-enforcing
entry-creation path — drawn from the reference implementations checked out
under `~/Git/Repos` (Linux, FreeBSD, Plan 9 / 9P, FUSE, SQLite), and mapped
back onto VFS.*

---

## 0. Orientation — how to read this, and the one idea

This document is organised along **Diátaxis**, which separates four kinds of
documentation by what the reader is trying to do. They are deliberately *not*
blended here; jump to the mode that matches your need:

| Part | Diátaxis mode | You are trying to… | Read when |
|------|---------------|--------------------|-----------|
| **1** | **Explanation** | *understand* the abstractions and why they exist | building a mental model |
| **2** | **Reference** | *look up* exactly what each system does, with `file:line` | checking a precise fact |
| **3** | **Tutorial** | *follow* one create operation through a real kernel, step by step | you learn by tracing |
| **4** | **How-to** | *apply* the abstractions to VFS's code | you're about to build it |
| **5** | — | the design decision + open questions | deciding the rework |

Every reference citation below was grep-verified against the local checkout.
Line numbers drift across versions; the **routine names** are the durable part.

**The one idea.** In a mature filesystem there is exactly *one* path through
which any object comes into existence, and that path enforces every invariant
*before* the object is actually written. There is no second door. Bugs,
security holes, and corruption come from second doors — code that writes an
object without passing the gate. VFS currently has second doors (chunk
creation, version creation). The whole design exercise is: **collapse them into
one.**

---

## 1. Explanation — the seven abstractions

These build on each other. Read them in order the first time.

### 1.1 Everything is a file (the uniform object model)

Unix's foundational move: files, directories, devices, pipes, sockets — all are
manipulated through *one* set of operations (`open`/`read`/`write`/`close`).
Plan 9 took it to the limit: not only is everything a file, but the *only*
interface between programs and resources is a file protocol (9P). A process, a
network connection, the window system — all are file trees served over 9P.

**Why it matters.** A uniform object model means you write the hard machinery —
naming, permissions, lifecycle, transactions — *once*, and every kind of thing
inherits it. The cost of adding a new kind of object is near zero, because it's
"just a file." The danger is the inverse: if some kinds quietly opt out of the
uniform machinery, you've lost the entire benefit and added confusion on top.

**VFS already lives here.** Every object is a row in one table (`VFSEntry`),
discriminated by `kind ∈ {file, chunk, edge, directory}`. Versions are entries.
Connections (edges) are entries. This is the "everything is a file" doctrine
made literal — *which is exactly why every kind must share one creation path.*

### 1.2 The single creation choke-point

In Linux you cannot create a file. You can only call `vfs_create()`, which
*then* — and only if a battery of checks passes — calls into the concrete
filesystem to do the actual mint. The same is true of `vfs_mkdir()`,
`vfs_mknod()`, `vfs_link()`, `vfs_symlink()`. Each is a narrow funnel: generic
preconditions on top, one dispatch to the on-disk layer at the bottom.

**Why it matters.** Invariants enforced *inside the funnel* cannot be
forgotten, because there is no way to reach the mint except through the funnel.
Contrast a codebase where "create a directory if missing" and "check
permissions" are open-coded at each call site: the third time someone needs to
create an object, they copy the happy path and forget the checks. That third
site is a second door.

**The litmus test for a choke-point:** *can any code in the system bring an
object into existence without calling this function?* If yes, it is not a
choke-point yet — it is merely a popular helper.

### 1.3 The generic/specific split (and op-vectors)

The funnel has two layers, and the boundary between them is the single most
important structural idea in filesystem design:

- **Generic layer** (the VFS): enforces invariants that are true of *all*
  filesystems — permission, parent-must-exist, name rules, reference counting.
- **Specific layer** (ext4, tmpfs, btrfs…): knows how to actually lay bytes on
  *this* medium. Reached only through a **table of function pointers** —
  `inode_operations` in Linux, the *vnode op vector* (`VOP_CREATE`) in BSD, the
  op table in FUSE, the four verbs in 9P.

`vfs_create()` does the generic checks, then calls `dir->i_op->create(...)`.
The `->create` slot is different for each filesystem; the checks above it are
identical for all. ext4 and tmpfs mint *completely differently* (journaled disk
extents vs. a kernel radix tree) yet both sit behind the one `vfs_create`.

**Why it matters — and the subtle lesson for VFS.** The kernels unify the
**gate**, not the **mint**. They never try to force ext4 and tmpfs to write
bytes the same way; they only force them through the same checks. This is the
answer to "won't a single creation path wreck my bulk-insert performance?" — no,
because the *mint* is allowed to stay polymorphic (ORM `session.add` for the
interactive path, bulk Core `INSERT` for the ETL path). What's unified is the
gate above it.

In VFS terms: the per-kind differences (a new file spawns a v1 version row; a
chunk carries forward grams on re-chunk; an edge validates its source exists)
are the *specific* layer — your `i_op->create` per kind. The *generic* layer —
parent reconciliation, permission, validation, metadata-root — is what the
choke-point owns.

### 1.4 Name resolution to the parent (namei / walk-to-parent)

You never create an object "at a path." You **walk** the path to its **parent
directory**, and create the object *inside that parent*. Linux resolves
`/a/b/c` down to the parent dentry `b` plus the final name `c` (`namei`), then
creates `c` within `b`. BSD's `vn_open_cred` resolves to `ni_dvp` (the parent
*directory vnode*) and calls `VOP_CREATE(ni_dvp, ...)`. 9P models creation as
`Twalk` (to the parent fid) followed by `Tcreate(name)`. FUSE's create ops are
literally typed `(parent_inode, name, mode)`.

**Why it matters.** Creation-by-parent is what makes "does the parent exist?
are you allowed to write *into* it?" the natural, unavoidable questions. The
parent is the unit of authorization and of existence. A system that creates
"at a full path" with no notion of the parent has nowhere to hang those
questions — so it tends to skip them.

**VFS's analogue.** A new entry's "parent" is its ancestor *directory* chain.
`_resolve_parent_dirs` is VFS's `namei`: it walks ancestors, materialises the
missing directories, revives the deleted ones, and **rejects an ancestor that
exists as a non-directory** (the equivalent of `ENOTDIR`). This is precisely
the walk-to-parent step — today it lives inside the write path only.

### 1.5 The permission gate on the parent (`may_create`)

Before the mint, Linux calls `may_create_dentry()`. It checks, in order: the
child must not already exist (`-EEXIST`), the parent must be a live directory
(`-ENOENT`), the caller's uid/gid must be representable, and — the crux — the
caller must hold **write + execute on the parent**. 9P's `screate` checks
`hasperm(parent, uid, AWRITE)`. BSD runs the MAC hook
`mac_vnode_check_create` before `VOP_CREATE`.

**Why it matters.** The permission decision is made on the **parent**, **before
the object exists**, **upstream of the only dispatch.** You cannot create then
check, or check in some-but-not-all call sites. The gate is structurally
upstream, so it cannot be skipped.

**The VFS nuance you already encode.** `_write_phase_resolve_parent_dirs`
permission-checks *revived* directories but deliberately lets brand-new
ancestors through unchecked (a writable carve-out inside a read-only mount needs
reachable ancestors). That's a real policy, and it belongs *in the gate* so it
applies uniformly — not re-decided per creation site.

### 1.6 The single commit primitive (one writer for user *and* system data)

Drop below the filesystem into the storage engine and the pattern repeats.
Every row SQLite ever writes — your tables, its own `sqlite_master` catalog, the
b-tree pages of every index — goes through **one** function:
`sqlite3BtreeInsert()`. The bytecode op `OP_Insert` is just a thin marshaller in
front of it. There is no "fast path for internal rows." Cross-cutting concerns
(update hooks, the change counter, `lastRowid`) live *at* that choke-point,
precisely because it is the only door.

**Why it matters.** This is abstraction 1.2 one layer down, and it carries the
same lesson: *internal/derived data goes through the same writer as user data.*
SQLite does not give its own catalog a privileged side-channel. If it did, every
invariant maintained at the insert boundary (and every future one) would have to
be duplicated and kept in sync — the classic source of "the index disagrees with
the table" corruption.

**The VFS echo.** VFS's "commit primitive" is the moment a `VFSEntry` row hits
the session (`session.add` / `session.execute(insert(...))`). Today user-driven
files and ETL-driven chunks reach it through different code with different
guarantees. The SQLite lesson says: one writer, for entries *and* their derived
kin (chunks, versions, grams).

### 1.7 Derived vs. authored data — and the choice to refuse the distinction

There is a deep tradition of treating *derived* or *internal* data differently
from *user-authored* data:

- **SQLite FTS5** stores its inverted index in **shadow tables** (`%_content`,
  `%_data`, `%_idx`, …): real tables, same database, same transaction, but
  *outside the user's logical namespace*. The engine recognises them by name
  (`fts5ShadowName`) and protects them from direct writes.
- **procfs / sysfs** present files that have **no backing store at all** —
  synthetic inodes materialised on demand from kernel state
  (`proc_register` builds an in-memory tree). They have a *different lifecycle*:
  no `unlink`, no user creation, regenerated from live state.
- **Extended attributes** (`__vfs_setxattr`) attach metadata *to* an inode
  rather than as a *child* of it — a side-channel, not a namespace entry.

The common doctrine: *derived data lives in the same transaction but a separate
region, with a minimal, non-user lifecycle.* By that doctrine, VFS chunks — which
are regenerable from their parent file, content-addressed, versioned as slaves
of the file, and hidden from `ls` — look exactly like FTS shadow rows, and
"should" escape the user lifecycle entirely.

**The design decision (yours) is to refuse this split.** Under "everything is an
entry," a chunk is not a shadow row; it is a first-class entry that happens to
be machine-authored. The price is that the *choke-point* must be expressive
enough to say "this kind is machine-authored: auto-create its parents, don't
permission-check it as user data" — i.e. the per-kind *policy* of 1.3 — rather
than letting chunks slip out a side door. The benefit is that you keep one
object model, one query surface, one lifecycle to reason about, and the
content-addressed version/carry-forward machinery (story 030) keeps working.
Section 5 weighs this; the point here is that it is a genuine fork in the road
that every reference system resolves the *other* way, so it is worth holding
consciously.

---

## 2. Reference — the systems, precisely

Dry facts. Each row: the choke-point routine, what it enforces, where the
generic layer dispatches to the specific layer. Verified against the local
checkout (`~/Git/Repos`).

### 2.1 The creation choke-points

| System | Choke-point | Permission gate | Dispatch to specific layer | Location |
|--------|-------------|-----------------|----------------------------|----------|
| **Linux VFS** | `vfs_create()` / `vfs_mkdir()` | `may_create_dentry()` (write+exec on parent, `-EEXIST`, dead-dir) | `dir->i_op->create(...)` / `->mkdir(...)` | `linux/fs/namei.c:4184`, `:5232`; gate `:3733`; dispatch `:4204`, `:5261` |
| **FreeBSD VFS** | `vn_open_cred()` → `VOP_CREATE` | `mac_vnode_check_create()` before the op | `VOP_CREATE(ni_dvp, ...)` — addressed by **parent** vnode | `freebsd-src/sys/kern/vfs_vnops.c:253`, create at `:320` |
| **Plan 9 / 9P** | `screate()` (`Tcreate`) | `hasperm(parent, uid, AWRITE)`; parent must be a dir (`Ecreatenondir`) | `srv->create(...)` | `plan9port/src/lib9p/srv.c:441`; perm `:407`/`:449`; dispatch `:451` |
| **FUSE (lowlevel)** | op table slots | request carries caller creds | `(req, parent, name, mode)` — create *cannot be expressed* except by parent+name | `libfuse/include/fuse_lowlevel.h:378` (mknod), `:393` (mkdir), `:982` (create) |

The structural invariant across all four: **gate first, single dispatch second,
no other door.** FUSE enforces it at the *type level* — you literally cannot
phrase a create without a parent inode.

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

### 2.4 VFS today — the current creation sites

| Site | Mints | Goes through the gate? |
|------|-------|------------------------|
| `_write_impl` → `_write_phase_resolve_parent_dirs` (`database.py:1730`, `:1902`) | files, dirs, **edges** (via `_mkedge_impl:2854`), copy/move | **Yes** — parent reconcile + permission |
| `_insert_new` (`database.py:1589`) | a new file's **v1 version** row (`session.add` `:1609`) | Partly — inside the write txn, but the version row isn't itself gated |
| `_update_existing` (`database.py:1559`) | **version** rows on each file update (`session.add` `:1561`) | Partly — same as above |
| `_chunk_pending` (`database.py:2242`) | **chunks** via bulk `insert(table)` (`:2333`) | **No** — the ETL second door |
| `_ensure_metadata_root` (`database.py:1395`) | the `/__meta__` root dir | special-cased |

**Reading of the table:** edges already share the file lifecycle (they route
through `_write_impl`). The genuine outliers are **chunks** (a fully separate
ETL path) and **versions** (minted ad-hoc *inside* the persist helpers rather
than through the parent/permission gate). Those are the second doors to close.

---

## 3. Tutorial — trace one create through the Linux kernel

Follow along in `linux/fs/namei.c`. Goal: see how `mkdir("/a/b/c", 0755)`
becomes one gated, single-dispatch creation. (Open the file and jump to the
line numbers as you read.)

1. **Resolve to the parent.** The syscall path resolves `/a/b` to a parent
   dentry and isolates the final component `c`. This is `namei` / `walk`
   (abstraction 1.4). Result: a *parent directory inode* `dir` and a *negative
   dentry* for `c` (a name with no inode yet).

2. **Enter the choke-point.** Control reaches `vfs_mkdir()`
   (`fs/namei.c:5232`). Everything from here is generic — true for ext4, tmpfs,
   NFS alike.

3. **The gate runs first.** `vfs_mkdir` calls `may_create_dentry()`
   (`fs/namei.c:3733`). Watch the order of checks (abstraction 1.5):
   - child already exists? → `-EEXIST`
   - parent is a dead directory? → `-ENOENT`
   - uid/gid representable in this idmap?
   - **`inode_permission(dir, MAY_WRITE | MAY_EXEC)`** — may the caller write
     *into the parent*?
   If any fail, we return *before anything is created*. No half-made object.

4. **The single dispatch.** Only now (`fs/namei.c:5245`) does it check
   `dir->i_op->mkdir` exists, and call it (`:5261`):
   ```c
   de = dir->i_op->mkdir(idmap, dir, dentry, mode);
   ```
   For ext4 this journals a new on-disk inode and directory block; for tmpfs it
   allocates a kernel inode. **The generic gate has no idea which** — that's
   abstraction 1.3. The polymorphism is in this one slot; the checks above are
   shared.

5. **There is no step 5.** There is no other way to make a directory. A driver
   author implements `->mkdir`; they never re-implement the permission check,
   because they are never *reached* without it having run.

**What to take away from the trace:** the kernel did not "create then validate."
It walked to the parent, ran every invariant on the parent, and *then* made one
polymorphic call to lay bytes. The ordering — *gate, then mint, through one
door* — is the whole game.

---

## 4. How-to — map each abstraction onto VFS

Recipes for the rework. Each maps a Part-1 abstraction to concrete VFS code. The
authoritative, current spec is [`design.md`](./design.md); this section is the
teaching view of how the abstractions land.

### How-to: build the single choke-point

Introduce one internal primitive — `_mint_entries` — that **every** entry-minting
site calls. Sketch:

```python
async def _mint_entries(
    self,
    entries: Sequence[VFSEntry],    # leaf entries + caller-planned dependents
    *,
    session: AsyncSession,          # caller's txn — the primitive never commits
    op: str = "write",              # permission verb (write | mkedge | …)
    user_id: str | None = None,     # None = system/admin (ETL, internal)
) -> _MintResult:
    # ---- generic gate (shared by all kinds: 1.1 / 1.4 / 1.5) -------
    self._validate_entry_paths(entries)             # name/kind gate + preconditions
    dirs = await self._resolve_parent_dirs(...)     # walk-to-parent
    self._enforce_revival_perms(dirs, op, user_id)  # may_create on revivals (if a principal)
    await self._ensure_metadata_root(session)
    # ---- staged mint: identity is server-issued (1.6) -------------
    ids = await self._mint_parents(dirs, files, session)  # insert, recover ids BY PATH
    await self._mint_dependents(deps, ids, session)       # wire *_id FKs, insert
```

Two things differ from the earliest draft:

- **The gate does not author dependents.** A file's version row is *planned by the
  caller* and passed in `entries`; the gate gates and mints what it is handed (the
  `sqlite3BtreeInsert` shape, 1.6). A gate **precondition** enforces the pairing — a
  `file` in the batch must carry its `version` — so no file can mint unversioned.
- **The mint is staged, not single-pass.** Identity is the server-issued integer
  `id`, so the gate inserts parents, recovers their `id`s **by path**, then wires the
  dependents' `parent_*_id` / `source_id` / `target_id` FKs and inserts them — all in
  one transaction, so it stays atomic. `path` is the before-insert correlation key
  that makes this work; there is no client-minted UUID (design.md §2–4).

The litmus test (1.2): after this lands, grep for `session.add(` and `insert(` in
`database.py`. *Every* survivor must be inside `_mint_entries` / `_mint_entry_rows`.
Any other is a second door.

### How-to: one mint, not two (don't fear ETL perf)

Per 1.3 the kernels unify the *gate*, not the *mint* — but VFS goes one step further
and uses a **single** lay-down for both paths: one bulk `insert(self._model)` over
`model_dump()` dicts (the ORM-enabled bulk insert — dicts in, no entities held). The
interactive write and `_chunk_pending`'s ETL batch run the *same* mint; a one-row
write and a ten-thousand-row batch are the same `executemany`. The mapped class is
kept only as the **schema / DDL** source (`metadata.create_all`, per-mount
`__table__`), never to hold a row. The ext4-vs-tmpfs lesson holds at the *gate*; the
mint itself doesn't need to vary.

### How-to: bring versions and connections through the gate

- **Versions** (`_insert_new:1609`, `_update_existing:1561`): stop calling
  `session.add(version_row)` inline. The caller still **plans** the version
  (`plan_file_write`) but hands the resulting rows to `_mint_entries` alongside the
  file, so they mint through the same gate, in the same txn, under the `version`
  policy. The file-carries-its-version precondition makes this structural.
- **Connections / edges** (`_mkedge_impl:2854`): already route through `_write_impl`,
  so they already pass the gate — *keep it that way.* The source-exists validation
  stays edge-specific (the specific layer), exactly like 9P's create dispatching to
  `srv->create` after the generic `hasperm`. Edges store their endpoints as
  `source_id` / `target_id` (the endpoints' `id`s, resolved from the DB), not as
  path strings.

### How-to: encode "machine-authored" as policy, not as a side door

This is the resolution of 1.7 under "everything is an entry." The per-kind policy
collapses to a **single bit** — is the kind user-authored? Auto-parenting is true for
every kind, and dependents are caller-planned (not gate-authored), so the only thing
the gate reads per kind is whether to run the user-permission check on a revived
parent:

| kind | `user_perm` (revival permission check) |
|------|----------------------------------------|
| `file`, `directory`, `edge` | yes |
| `chunk`, `version` | **no** (machine-authored) |

Chunks don't *escape* the lifecycle (the FTS-shadow answer); they *pass through it
with a policy that says "machine-authored."* And "machine-authored" is keyed on the
principal: `user_id=None` (ETL/system) skips the user-level path check, while the
database's own grants govern. The public surface must inject an authenticated
principal so `None` can only originate internally (design.md §3 step 3).

### How-to: respect the transaction boundary

Per 1.6, the gate **must not open its own session or commit.** It runs in the
caller's transaction so that `index()` (`database.py:2335`) and `_write_impl`
keep owning the commit/rollback boundary — chunks-under-a-missing-dir can never
be a half-committed state, because parent dirs and chunks land in the same txn.
This mirrors SQLite: `sqlite3BtreeInsert` participates in the active write
transaction; it does not start one.

---

## 5. The design decision, and what's resolved

**The decision.** Everything is an entry; one choke-point — `_mint_entries` —
enforces every invariant we've designed, for files, directories, chunks,
**versions**, and **connections** alike. This rejects the shadow-table /
synthetic-inode tradition (1.7) that every reference system follows for derived data.
The justification is coherence: a single object model, query surface, and lifecycle.
The obligation it creates is that the choke-point carries a **per-kind policy** (now a
single `user_perm` bit) so machine-authored kinds skip user-permission without a side
door.

**Resolved since the first draft** (full spec in [`design.md`](./design.md)):

- **A method, not a `WriteTxn` object** — the smallest delta; it runs in the caller's
  txn and never commits. (fsspec's `transaction` models the layer *above* a commit
  primitive; `_mint_entries` *is* the primitive.)
- **One Core-shaped mint**, not an orm/core split — `insert(self._model)` over dicts,
  the same statement for interactive and ETL. SQLModel is kept for **DDL only**.
- **`id` is the identity; `path` is the correlation key.** The integer PK is the
  stable identity (and the posting `doc_id`); cross-references are `*_id` FKs; the path
  columns are the materialized, mutable name layer. `entry_id` is dropped.
- **Dependents are caller-planned and flattened** — the gate mints what it's handed; a
  precondition enforces "a file carries its version." (No recursive re-entry.)
- **Provenance** — an explicit system principal (`user_id`) yields `created_by` for
  machine-authored kinds for free.
- **Per-kind policy is a static table** — and it turned out to be one bit.

**Still open** (design.md §11): whether `version` is a public `kind`; whether to
anchor chunk/version *paths* on `id` so a move touches only the file's own row; index
staleness once search consumes the posting list; and ETL affordances (progress,
concurrency, partial-failure).

**Prerequisite — must land first.** `_classify_chunks` (`database.py:2159`/`:2168`)
calls the old `_match_chunks` contract (wrong arity, tuple-unpacks a `NamedTuple`) —
the inline re-chunk path is broken and untested. Fix and cover it *before* layering
the gate on top, so the new gate isn't built against a half-migrated callee.

---

### Appendix — where to read each idea in the source

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
- **VFS today:** `src/vfs/backends/database.py` → `_write_impl:1730`,
  `_resolve_parent_dirs:1333`, `_write_phase_resolve_parent_dirs:1902`,
  `_insert_new:1589`, `_update_existing:1559`, `_chunk_pending:2242`,
  `_mkedge_impl:2854`, `_ensure_metadata_root:1395`.
