# 055 — POSIX Mounts Over a Storage-Backed Namespace: `InMemoryStorage` as the Default

- **Status:** closed 2026-07-10 — core landed via 056 Pass A
  (`d02b3ad`): `InMemoryStorage` with `allow_files`, spine removed,
  `add_mount`/`remove_mount` with `parents` threading all verified in
  code. Caveat: the fused mkdir→bind `add_mount` shape in "Decisions
  settled" 1–2 was **superseded, not landed** — 056 decisions 4/5
  replaced it with bind-onto-existing-empty-directory and strict
  non-recursive rmdir. tasks.md items 1–7 folded into 056 Pass A.
- **Date:** 2026-07-07
- **Owner:** Clay Gendron
- **Kind:** feature (new backend) + refactor (mount semantics, spine removal)
- **Depends on:** ADR 003 (POSIX parent rule), 049 (`StorageBackend`
  protocol), 041 (mount spine — the mechanism this retires), 042/048
  (mount lock — unchanged, still load-bearing)
- **Enables:** the database backend port mounting with clean semantics;
  closes story 050 (the spine divergence dissolves with the spine)

## Intent

Give every node a real storage backend and make mounting POSIX-shaped.
Today a bare `VirtualFileSystem()` is a storageless router whose
namespace shape is *synthesized* from the mount table (the spine), and
`add_mount(fs, "/a/b/c")` conjures arbitrarily deep phantom ancestors.
After this story:

- `VirtualFileSystem()` defaults to a new `InMemoryStorage` in its
  directories-only mode — the namespace shape is *stored*, not
  synthesized.
- `add_mount` follows POSIX's split, fused the way an automounter
  (udisks) fuses it: the mount-point **directory** is a real stored
  entry (`mkdir`), the mount **binding** is runtime state on the node
  (the kernel mount-table model).  Parents must already exist (ADR
  003); `parents=True` is the explicit opt-in that mkdirs the chain.

## Decisions settled (review 2026-07-07)

1. **The mount-point directory is stored; the binding never is.**
   POSIX ground truth (verified against `mount(8)`/udisks behavior):
   the mount point is an ordinary directory on the parent filesystem,
   created by `mkdir`, while the binding lives only in the kernel's
   runtime table — nothing about the *mount* is written to disk.  We
   mirror both halves.  A stored `mount_point` flag was considered and
   rejected: binding metadata in storage is drift by construction
   (crash phantoms, cross-process lies through a shared database).  A
   plain empty directory has none of those failure modes — it is
   honest in every state, bound or not.
2. **`add_mount` always creates the directory; `remove_mount` always
   removes it.**  Because mounting onto an *existing* directory stays
   rejected (no shadowing), every mount-point directory is
   add_mount-created by construction — so unmount can delete it with
   no provenance tracking, and it is provably empty (routing sends
   everything beneath it to the child, so parent storage never gains
   rows under it).  This is udisks' mkdir → mount → umount → rmdir
   cycle, fused into the two public calls.
3. **The default node stores directories only.**  `InMemoryStorage` is
   a full `StorageBackend`, with a construction switch that refuses
   file content; `VirtualFileSystem()` defaults to that mode, so a
   bare router carries namespace shape (directories, mount points)
   without becoming an accidental RAM file store.  Constructing
   `InMemoryStorage` directly in full mode is the explicit opt-in to a
   tmpfs-like node.
4. **Mount points read as plain directories — no `mount` kind,
   stored or projected.**  Storing a `mount` kind would re-create the
   stale-copy problem (a crash leaves a stored "mount" with no binding
   — a lie).  A read-time `kind="mount"` projection was considered and
   dropped too (review 2026-07-07): POSIX shows a directory when you
   `ls` a mount point, and mount-ness belongs to the mount table, not
   the kind vocabulary.  `ObjectKind` is untouched.  The one read-time
   composition that survives: a bound mount row carries the child's
   live ``description``, so a parent reading a mount point still sees
   the child's constructor metadata; unbound, the row is the bare
   stored directory it is.

## Scope

### 1. `InMemoryStorage` (new, `vfs/backends/memory.py`)

- Implements the full protocol surface: read family, pattern search,
  mutation family — the *reference backend*, and the executable home
  for the site-check semantics deleted from the router in the 049
  follow-up (absence reads as free; a non-directory ancestor is
  `wrong_kind`).  There is no standalone site probe: `mkdir` and the
  other mutation verbs check and act in one call, and dropping the
  probe dropped `is_path_writable` from the protocol entirely (review
  2026-07-07).
- `allow_files: bool = True` at construction (settled — a kwarg, not a
  named constructor).  With `allow_files=False`, `write`/`edit` of file
  content classify
  `unsupported` with a "directories only" message; `mkdir`, directory
  `delete`/`move`, and all reads work.  The family stays whole — the
  mutation family is all-or-nothing, and capabilities speak ops, not
  per-kind guarantees.
- Obeys ADR 003 natively: no implicit parents; `parents=` honored on
  the ops that take it.

### 2. Constructor default (`vfs/base2.py`)

- `storage=None` now means `InMemoryStorage(allow_files=False)`, not
  "no storage."  The gate's storageless branches (`not_found` for a
  pure router, the `_call_local_impl` no-backend arm) die — every node
  has a backend.
- Derived capabilities of a bare node become the backend's real set.

### 3. `add_mount` / `remove_mount` — the fused POSIX shape

- **Parent rule:** every ancestor of the mount path must exist as a
  stored directory on the owning node (`mkdir` checks as it acts);
  missing → `ValueError` naming the first missing ancestor.  `add_mount(..., parents=True)` mkdirs the chain first —
  ADR 003's flag, symmetric with the mutation verbs.
- **Site rule:** the mount path itself must be free — absent from
  storage and unbound in the table.  `add_mount` then stores the empty
  mount-point directory and binds over it.  Mounting onto an existing
  directory or file stays rejected (`exists` in the reason).
- **Unbind rule:** `remove_mount` detaches the child and deletes the
  empty mount-point directory it created.  Re-mounting at the same
  path is then clean by construction.
- Ordering under the lock: mkdir → commit-gate bind.  A bind that
  fails at the commit gate removes the directory it just created
  (udisks-style — the fused model cleans up its own side effect, and a
  corrected retry finds a clean site); parents minted by
  `parents=True` persist, as after `mkdir -p` and a failed `mount`.
  On a *persistent* backend, a crash between mkdir
  and a later unmount leaves an empty directory that blocks re-mounting
  with `exists` until the caller deletes it — loud, honest, and
  recoverable with one `delete`.
- Delegation into an existing mount, the lock, and the commit gate are
  otherwise untouched.

### 4. Spine removal (`vfs/base2.py`)

- Delete `_spine_children`, `_is_spine_path`, `_spine_row`,
  `_spine_read`, `_spine_ls`, `_spine_tree`, `_absorb_not_found`, and
  `SPINE_READ_OPS`' special-casing at the chokepoints.  Stored
  directories answer `ls`/`stat`/`tree` from storage; the `wrong_kind`
  classification for mutations against a directory comes from the
  ordinary path (storage truth), not a spine check.
- The one remaining read-time step is *decoration*: rows for bound
  mount points keep `kind="directory"` and gain the child's live
  description projected from the binding table.  Namespace shape
  itself is never synthesized.
- Scoped fan-out expansion (a scope covering mounts beneath it)
  remains — it reads the binding table, which is routing, not
  visibility.
- Story 050's grouped-vs-single divergence closes with the spine;
  verify both input shapes classify identically once storage answers.

### 5. Ripples

- `tests/test_base_spine.py` retires; surviving semantics (mount rows
  in `ls`, tree depth budgets across mounts, fan-out expansion) move
  to storage-backed equivalents.  Mount tests gain the parent rule,
  `parents=True`, and the mkdir/rmdir lifecycle; the sparse-mount
  tests (`/a/b/c` over nothing) invert into failures without the flag.
- 053 item 3 (spine rows ignore `columns`) dissolves; item 2's
  overlap analysis simplifies once scopes resolve against storage.

## Acceptance criteria

- `VirtualFileSystem()` answers `ls("/")` as an empty success from
  storage; `mkdir("/data")` then `add_mount(child, "/data/a")` works;
  `add_mount(child, "/x/y")` without `parents=True` fails naming
  `/x`; with it, `/x` exists as a stored directory afterwards.
- After `add_mount(child, "/data/a")`, the mount-point directory is a
  stored entry (`kind="directory"` in storage) and `ls("/data")` shows
  the row as a directory carrying the child's live description.
  After `remove_mount("/data/a")`, the directory is gone
  from storage and re-mounting at the same path succeeds.
- `write(path="/f.txt", content=...)` on a bare node classifies
  `unsupported` (directories-only default); the same call on a node
  built with a full `InMemoryStorage` succeeds and reads back.
- All 050 shapes (path and observation input) classify identically
  against directories and absent paths.

## Open questions

All resolved (review 2026-07-07):

- Directories-only switch: `allow_files: bool = True` kwarg on
  `InMemoryStorage`; the router default is
  `InMemoryStorage(allow_files=False)`.
- Error kind for file writes into directories-only storage:
  `unsupported` — a capability statement about the backend, not a kind
  mismatch at a site that may not even exist.  Pinned in the backend
  tests.
- Module home: `vfs/backends/memory.py`, beside the future database
  backends.
