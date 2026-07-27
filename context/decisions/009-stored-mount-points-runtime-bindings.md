# 009. Mount Points Are Stored Plain Directories; Bindings Are Runtime Table State

- **Status:** accepted
- **Date:** 2026-07-16
- **Deciders:** Clay Gendron
- **Decided by:** human (055 review 2026-07-07; corrected by the 056
  research review 2026-07-07 before landing; this record captures the
  landed shape)

## Context

Before story 055, a bare `VirtualFileSystem()` was a storageless router
whose namespace shape was *synthesized* from the mount table — the
"spine" (story 041) — and `add_mount(fs, "/a/b/c")` conjured
arbitrarily deep phantom ancestors. The spine special-cased reads at
every chokepoint and produced story 050's grouped-vs-single
classification divergence. Meanwhile the POSIX ground truth (verified
against `mount(8)`/udisks during the 055 review) is the opposite split:
the mount point is an *ordinary directory* created by `mkdir` on the
parent filesystem, while the binding lives only in the kernel's runtime
mount table — nothing about the mount is ever written to disk.

## Options considered

- **A stored `mount` kind, or a read-time `kind="mount"` projection** —
  rejected (055 decision 4): binding metadata in storage is drift by
  construction — a crash leaves a stored "mount" with no binding, and a
  shared database lies cross-process. POSIX shows a directory when you
  `ls` a mount point; mount-ness belongs to the mount table, not the
  kind vocabulary.
- **055's drafted fused shape** — `add_mount` always mkdirs, `remove_mount`
  always deletes, mounting onto an existing directory rejected —
  **superseded before landing** (056 decisions 4/5): on a persistent
  backend every process restart fails `exists` at rebind, and once the
  parent path's storage can be shared or remote, the "provably empty"
  claim behind the unconditional delete is false — a data-loss bug.
- **Bind onto an existing empty directory as the primitive** (chosen,
  056 decisions 4/5): `add_mount` becomes mkdir-if-absent + bind sugar;
  `remove_mount` becomes unbind + strict non-recursive rmdir. Linux,
  Plan 9, and FUSE never create mount points; the mkdir half is owned
  as udisks-style convenience, not claimed as POSIX.

## Decision

Recorded is the **landed** shape (056 Pass A, commit `d02b3ad`), not
055's drafted fused-mkdir shape:

1. **The mount-point directory is stored; the binding never is.** A
   mount point is a plain stored directory. There is no `mount` kind,
   stored or projected — `ObjectKind` is untouched
   (`src/vfs/paths.py:34`). The binding is runtime-only, per-process
   mount-table state: `Binding(path, storage, meta)` with the node's
   own storage as the identity entry at `/`
   (`src/vfs/base.py:230`). Mount identity stays live by reading
   the bound storage's `description` as an attribute at listing time
   (`src/vfs/base.py:551`), never by storing it.
2. **`bind` is the primitive; the site must be an existing empty
   directory** — the `graft_tree` rule: exists, is a directory, has no
   children (`bind`, `src/vfs/base.py:238`). This is what makes
   rebinding after a restart work on persistent backends and turns
   crash-orphaned mount-point directories into valid future sites
   instead of poison. `add_mount` fuses mkdir-if-absent in front
   (`parents=` per ADR 003); a failed bind leaves the directory behind
   — a valid future mount site, not damage to roll back
   (`src/vfs/base.py:358`).
3. **`remove_mount` = unbind + strict non-recursive rmdir**
   (`src/vfs/base.py:382`). Unbind is pure table surgery under the
   mount lock — no storage I/O, so it succeeds against a wedged
   backend. The rmdir is never a cascade: on shared or persistent
   storage the directory may have gained rows this router never saw. A
   failed rmdir leaves the unbind standing and a plain directory in the
   namespace — loud, honest, recoverable.
4. **The router's synthesized spine is deleted.** Namespace shape is
   stored, never synthesized; stored directories answer `ls`/`stat`/
   `tree` from storage. No spine code remains in `src/vfs/` (verified
   by search, 2026-07-16). Story 050's divergence closed with it.
5. **`VirtualFileSystem()` defaults to a real `InMemoryStorage`** —
   `storage=None` means `InMemoryStorage()`, not "no storage"
   (`src/vfs/base.py:211-212`); every node has a backend and the
   storageless gate branches died. Divergence from the 055 draft, on
   record: 055 drafted the router default as directories-only
   (`allow_files=False`), but the landed constructor passes no flag and
   `allow_files` defaults `True` (`src/vfs/storage/backends/memory.py:84`)
   — the bare node is a full in-memory store. Directories-only remains
   the explicit `InMemoryStorage(allow_files=False)` opt-in; its
   refusals classify `unsupported`, and `capabilities()` declares the
   full op set regardless (capabilities speak ops, not per-kind
   guarantees).

## Consequences

- **Easier:** rebind-after-restart on persistent backends; a mount
  point is honest in every state, bound or not; remount at the same
  path is clean by construction; one storage-backed read path with no
  spine special cases; the database backend mounts with the same
  semantics as memory.
- **Harder:** unmount can fail loudly (strict rmdir against a directory
  that gained foreign rows) and leave a plain directory to clean up;
  an empty directory is indistinguishable from an unbound mount site
  except through the mount table — by design.
- **Committed to:** no `mount` kind ever enters `ObjectKind`; no
  binding metadata is ever stored; the mount lock is per-process, so
  shared-storage mount admin is unsynchronized and races surface as
  ordinary classified storage results (056 decision 22).

Executed through story 055 (`context/specs/archive/055-posix-mounts-inmemory-default/`)
and 056 Pass A (`context/specs/active/056-storage-mounts/`, commit `d02b3ad`).
