# Mounts

This page says how a [mount](../reference/glossary.md#mount) is built in the code, and why. It is for people who change VFS.

## The word

- **The class is `Mount`, and there is no "binding".** Plan 9 and Linux each keep a private live record of a mount and publish a separate description of it. Every layer is named for the mount: Plan 9's kernel record is `Mount` whether the `bind` call or the `mount` call made it, and Linux has `mount`, `vfsmount`, `statmount` and `mountinfo`. Neither uses "binding" as a noun.
- **"Bind" is kept free.** In Plan 9 and in Linux, to bind is to make something already in the file tree appear at a second path. VFS does not do that today, and the word is reserved for it.

## The class

- **`Mount` is a frozen dataclass with slots, not a `NamedTuple`.** Its `caps` field is computed once, when the mount is built, as `declared_caps - deny_ops`. Every permission check reads it. A `NamedTuple` cannot compute a field when it is built.
- **Its fields are `path`, `storage`, `permissions`, `deny_ops`, `no_overlay`, `owned`, `declared_caps` and the computed `caps`.** There is no second class for the policy and no third for the public view.
- **`Mount.to_payload()` returns the JSON-native form, a `MountPayload`.** A `Mount` holds a live storage object, so `json.dumps` cannot take it whole. `PermissionMap.to_payload()` uses the same name for the same job.
- **`remove_mount()` returns the `Mount` it removed,** so the caller can close the storage.

## Who may change a mount

- **A mount change is a write at its mount point.** Adding a mount needs what `mkdir` at the mount point needs, and removing one needs what `delete` there needs. Changing one in place with `update_mount()` asks the gate for a `delete` and a `mkdir` at the mount point, and for nothing more. That is less than a remove followed by an add. A mount beneath a `no_overlay` mount, a mount with mounts beneath it, and a mount whose `restore` is masked above can each be changed in place, and none of them can be removed and added again. A read-only parent takes no new mount, loses none, and lets none beneath it change. The root has no mount above it, so nothing above can refuse a change to the root. The two private methods `_attach_mount()` and `_detach_mount()` ask the gate themselves, so no caller goes around it.
- **A mask refuses a mount change only on the mount that holds the mount point. A read-only permission map refuses it from any mount above.** The gate reads the capabilities of the one mount that stores the mount-point directory, which are what its storage declared less its `deny_ops`. It reads the permission map of every mount above the mount point. So when `/a` is a mount, a root that masks `mkdir` does not stop a mount at `/a/b`, and a root that is read-only does.
- **A mount change needs `read_write` at the mount point.** `add_mount()`, `remove_mount()` and `update_mount()` take an `authority`, and a call that names none is treated as any verb is. The check runs before anything changes.
- **The rights are checked once, before the change.** A grant revoked after the check and before the commit does not stop that change.
- **Whoever holds `read_write` at a mount point can change that mount's policy.** `update_mount()` changes its mask, its permissions and its `no_overlay` in place, wherever the gate allows a `delete` and a `mkdir` at the mount point. An operator who wants a mount's policy kept does not give `read_write` at its mount point.
- **The storage that holds the mount point answers.** It answers through `holds()`, a question that reads the rights and changes nothing. `holds()` is not a verb, so a session cannot ask it. A storage that keeps grants and cannot answer refuses.
- **`add_mount()` makes the mount-point directory as the caller.** It is the caller's own `mkdir`, with the caller's own `parents`. A caller who may not make the directory may not mount there, and `read_write` at the mount point alone does not let a caller make a directory in a parent they cannot see. The check of the mount point, and the delete of its directory when the mount is removed, are the kernel's own work and run as the system actor.
- **If a mount at or above the mount point is added or removed while the caller's rights are checked, the call refuses and asks for a retry.** All three mount changes keep what was judged and check it again under the mount lock, with no await between that check and the commit. The mount that holds the mount point must be the same storage at the same path. For `update_mount()` and `remove_mount()`, the mount at the path must be the one that was there. Otherwise the rights were judged for a place that has changed.
- **Once a mount exists, no verb reaches the rights of its mount point.** `/data` then names two entries, the directory in the storage above and the root of the mounted storage, and `grant()`, `revoke()`, `grants()` and `set_posture()` reach the second. The right to change the mount is on the first, so that right is given before the mount is added or on a directory above it.
- **A session has no way to reach a `Mount`.** A `Mount` carries the storage object, and a session is what an agent holds. Reaching the storage would go around permissions. Only the file-system object has mount methods, and a test keeps it so.

## Rebuilding a mount table

`mounts()` returns enough to build the same table again. Add every mount bare, then set each mount's policy with `update_mount()`. A mount that is read-only, that masks `mkdir` or that is sealed with `no_overlay` refuses new mounts beneath it, so the policy goes on last. Set the policy of the deepest mount first and the root's last, because a read-only mount also refuses a change to the mounts beneath it.
