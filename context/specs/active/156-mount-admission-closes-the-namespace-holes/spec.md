# 156 — Mount admission closes the namespace holes: a sealed root, a protected trash, a `..` gate test, no bare node as a mount

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** fix (router policy in `base.py`; one gate rule; tests)
- **Depends on:** the terminal gate and `MUTATING_OPS` as built
  (`ops.py`, `base.py`), `remount` and `deny_ops`, the trash chain
  (archived 075, 081, 082, 083), `restore` as built.
- **Research it stands on:**
  `../../../research/2026-10-08-smartowl-workspace-integration-issues.md`
  items 14, 15, 17 and the verification addendum's missed crash.

## Intent

A host puts an agent on a namespace with a read-only mount and a
read-write mount and expects the agent to be confined to those two
subtrees. Today it is not: `write /x` lands on the default in-memory
root, invisible to any viewer that lists the mounts and gone on close;
`write` into `/mine/.vfs/trash/...` overwrites the only copy that
`restore` could bring back; and a `VirtualFileSystem` handed to
`add_mount` is accepted and then crashes `glob`. Each is a router
admission decision, and each closes in `base.py`.

One line: once a namespace has mounts, the root holds nothing, the
trash is restore-only, and a mount is a storage.

## Decided semantics

1. **The default root seals on first mount.** A `VirtualFileSystem()`
   built with no `storage` gets its `InMemoryStorage` root as today,
   but the first successful `add_mount` sets the root entry's
   `deny_ops` to `MUTATING_OPS`. A later mutation at a root-only path
   refuses `read_only` with the root as its `source`. A node built with
   an explicit `storage=` is the owner's choice and keeps its policy.
   `remount("/", deny_ops=())` reopens it for a host that wants the
   root writable.
   `[NEEDS CLARIFICATION: seal on first mount (quiet, automatic) or
   refuse at construction unless `permissions="read"` is passed with
   no storage (loud, explicit)? Leaning seal on first mount with an
   info record on the `add_mount` result.]`
2. **The trash is restore-only.** *(2026-10-08: dissolved by ADR 074,
   accepted — a tombstoned row has no trash-side path to write into. Spec
   162 owns it; this spec builds rules 1, 3 and 4 only.)* Under every mount's `/.vfs/trash`
   prefix the gate admits `read`, `stat`, `ls`, `tree`, `glob`, `grep`,
   `glean`, `restore` and `destroy` at the trash root (retention). It
   refuses `write`, `edit`, `move`, `copy`-as-destination, `mkdir`,
   `mkedge` with `invalid`, and `delete` with `invalid` (today a delete
   re-trashes the row under a second ULID prefix, which is a hole of a
   different shape). This is a gate rule on the reserved prefix, not a
   permission-map rule, so it needs no per-verb prefix allowance and
   `restore` keeps working.
3. **A `..` into a sibling mount meets the sibling's gate.** Already
   true by canonicalization (`paths.py`); this spec pins it with a
   router-level test: `write /mine/../course/x.md` on a `read` mount at
   `/course` refuses `read_only` at `/course/x.md`.
4. **`add_mount` refuses a bare node.** A `VirtualFileSystem` is not a
   `StorageBackend` even though it has the read family; passing one
   raises `TypeError` naming the adapter to use. Nesting stays what it
   is today: deeper bindings in one table.
   `[NEEDS CLARIFICATION: refuse, or ship the adapter that forwards a
   node's verbs under the storage protocol's names (`patterns=` for
   `pattern`, …)? The README's "mounts nest" sentence reads as the
   adapter. Leaning refuse now, adapter as its own spec.]`

## Scope

- Root seal in `add_mount` under the mount lock; an info record on
  the result.
- The trash rule in the gate beside the existing "meta root is not a
  write target" rule (`tests/base/test_gates.py` L247–254 pins the
  current admission; that test flips).
- The `..` test in `tests/base/test_gates.py`.
- The node refusal in `add_mount`'s `isinstance` check and in
  `__init__`'s `storage=` check.
- Out of scope: row-level grants (058, 150), the trash's retention
  policy, nested-node adapters.

## Acceptance criteria

- After one `add_mount`, `write /x` and `mkdir /evil` on a default
  root refuse `read_only`; `ls /` lists only the mounts.
- `write`, `edit`, `move`, `mkdir` and `delete` on a trashed path refuse
  `invalid`; `restore` of that path succeeds; `destroy /m/.vfs/trash`
  still runs retention.
- `write /mine/../course/x.md` with `/course` mounted `read` refuses
  `read_only` with `path == "/course/x.md"`.
- `add_mount(VirtualFileSystem(), "/n")` raises `TypeError`.
- `scripts/ci.sh 3.13` green.
