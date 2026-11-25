# 156 — Mount admission: a `..` gate test, and no bare node as a mount

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo; revised 2026-10-08 after a review against `0760fe9` that executed the bare-node mount (the structural check admits a node today). Rule 1 (seal the default root) dropped the same day (Clay): the default root is a `DatabaseStorage` on in-process SQLite, so a write that lands there is the owner's choice, not a hole; spec 153 has the README say what the default root is. Rule 2 dissolved by ADR 074.
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** fix (router admission in `base.py`; one nominal type check; tests)
- **Depends on:** `add_mount` and `__init__`'s structural `isinstance(storage, StorageBackend)` checks (`base.py` L337, L399; `StorageBackend` is `@runtime_checkable`, `protocol.py` L414), `normalize_path` (`paths.py`).
- **Research it stands on:** `../../../research/2026-10-08-smartowl-workspace-integration-issues.md` item 17 and the verification addendum's missed crash.

## Intent

A `VirtualFileSystem` handed to `add_mount` passes the structural `StorageBackend` check, is bound, routes `read` and `write`, and then crashes `glob` with `TypeError: got an unexpected keyword argument 'patterns'` (executed 2026-10-08). A router is not a storage; the admission check should say so before anything routes.

One line: a mount is a storage.

## Decided semantics

1. **The default root stays as it is.** *Dropped 2026-10-08 (Clay). `VirtualFileSystem()` with no `storage` gets an `InMemoryStorage`, a full `DatabaseStorage` on a private in-process SQLite database. Writes outside every mount land there, as the owner chose; the README says so (spec 153).*
2. **The trash is restore-only.** *Dissolved 2026-10-08 by ADR 074 (accepted): a tombstoned row has no trash-side path to write into, and a mutation at a tombstoned path classifies `not_found`. Spec 162 owns the `/.vfs/trash` write-target rule and the flip of `tests/base/test_gates.py` L247–254.*
3. **A `..` into a sibling mount meets the sibling's gate.** Already true by canonicalization (`normalize_path`; executed 2026-10-08: `write /mine/../course/x.md` refuses `read_only` at `/course/x.md`). The existing pins are unit-level (`tests/test_paths.py` L82–101, `locate` in `test_mount_admin.py` L539); this spec adds the router-level gate test.
4. **`add_mount` refuses a bare node.** `add_mount` and `__init__(storage=)` gain a nominal refusal ahead of the structural check: `isinstance(storage, VirtualFileSystem)` raises `TypeError("a VirtualFileSystem is a router, not a storage; wrap it in the node adapter")`. Nesting stays what it is today: deeper bindings in one table. The README's "mounts nest" sentence is softened by 153. `[NEEDS CLARIFICATION: refuse, or ship the adapter that forwards a node's verbs under the storage protocol's names (`patterns=` for `pattern`, …)? Leaning refuse now, adapter as its own spec.]`

## Scope

- The `..` gate test in `tests/base/test_gates.py`.
- The nominal refusal in `add_mount` and `__init__`; `tests/base/test_mount_admin.py` gains the case.
- Out of scope: the default root's policy, row-level grants (058, 150), the trash (162), nested-node adapters.

## Acceptance criteria

- `write /mine/../course/x.md` with `/course` mounted `read` refuses `read_only` with `path == "/course/x.md"`.
- `add_mount(VirtualFileSystem(), "/n")` and `VirtualFileSystem(storage=VirtualFileSystem())` raise `TypeError`.
- `scripts/ci.sh 3.13` green.
