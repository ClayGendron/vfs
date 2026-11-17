# Public names follow the naming rules: handoff

## Goal

The public API of `vfs` follows `documentation/maintainers/how-we-name.md`. The names in that page's last table are changed in `src/`, `tests/` and `documentation/`, and the table is deleted.

Nothing in this directory is built. The decisions below were made on 2026-11-16 during the glossary work, on the branch `glossary-rules`. This work gets its own branch off `dev`.

## Decisions, each with its reason

1. One public class, `Mount`, replaces `Binding`, `MountMeta` and `MountInfo`. Reason: one concept has one noun. Plan 9 (`struct Mount` in `9front/sys/src/9/port/portdat.h`, made by `cmount` for both the bind and the mount call) and Linux (`struct mount` in `fs/mount.h`, `struct vfsmount`, `struct statmount`) name every layer for the mount, and neither has a noun "binding". Four agent file systems checked on disk (agentfs, afs, agentvfs, branchfs) define `Mount` types and no `Binding` type; those clones were not refreshed before the search.
2. `Mount` is a frozen dataclass with slots, not a `NamedTuple`. Reason: `caps` is computed once at construction as `declared_caps - deny_ops`, every permission gate reads it, and a `NamedTuple` cannot compute a field when it is built.
3. `Mount` has the fields `path`, `storage`, `permissions`, `deny_ops`, `no_overlay`, `owned`, `declared_caps` and the computed `caps`. Reason: these are the fields of `Binding` and `MountMeta` today, flattened. `MountMeta` is already replaced whole and never field-mutated.
4. `Mount.to_payload()` returns the JSON-native fields `MountInfo` has today. Reason: `MountInfo` promises that `json.dumps` always succeeds on a row, a `Mount` holding a live storage object cannot, and `PermissionMap.to_payload()` is the existing name for the same job.
5. `mounts()` returns a tuple of `Mount`. Reason: a plural noun returns that noun.
6. `bind()` and `unbind()` leave the public API. `add_mount()` and `remove_mount()` are the public pair. Reason: "bind" means aliasing in Plan 9 and Linux, vfs refuses aliasing, and the word is kept free. `add_member()` and `remove_member()` already use the same pattern.
7. `remount()` becomes `update_mount()`, `session()` becomes `open_session()`, `posture()` becomes `set_posture()`. Reason: a noun is never a method name by itself, and the verb comes from the fixed list: add and remove, set, update, open and close.
8. `StorageBackend` and `ObjectKind` become public. Reason: public signatures name them (6 and 7 times in the export of 2026-11-16), and `Mount.storage` names `StorageBackend`.
9. A test requires every type named in a public signature to be exported. Reason: the rule is checkable from the docs export, which holds every public signature.
10. A test requires that a session has no way to reach a `Mount`. Reason: `Mount` carries the storage object, a session is what an agent holds, and reaching the storage would go around permissions. Today only the file-system object has mount methods; the test keeps it so.

## Details left to settle when the code is open

- `bind()` requires the directory to exist and be empty; `add_mount()` creates it when absent. `unbind()` leaves the directory; `remove_mount()` deletes it. Removing the strict pair from the public API needs an option on each remaining method, or a decision that the strict behaviour is not offered.
- The private name of the operation that puts a `Mount` in the table. "Bind" as a private verb is consistent with the precedent; a noun "binding" is not.
- Why both `add_mount` and `bind` were public: the commit `d02b3ad3` of 2026-07-07 made `bind` the primitive and `add_mount` the convenience that fuses a mkdir in front.
- `unbind()` returns the live record today. `remove_mount()` returns `None`. Whether `remove_mount()` returns the removed `Mount`.
- The sync facade in `src/vfs/sync.py` mirrors every method named above.
- `MountError`'s docstring names `add_mount` and `remove_mount`; it stays correct after the change.
- The glossary term Mount is rewritten for the one class.

## Size, counted in `src/` on 2026-11-16

`Binding` 26 occurrences, `bind(` 17, `unbind(` 3, `add_mount` 11, `MountInfo` 7, `MountMeta` 5. `tests/base/test_mount_admin.py` uses `MountInfo` or `mounts()` 33 times and `tests/test_sync.py` 7 times.
