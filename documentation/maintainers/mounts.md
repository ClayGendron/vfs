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

- **A mount change is a write at its mount point.** Adding a mount needs what `mkdir` at the mount point needs, and removing one needs what `delete` there needs. Changing one in place with `update_mount()` needs both, because it does what a remove followed by an add would do. A read-only parent takes no new mount, loses none, and lets none beneath it change. The root has no mount above it, so nothing above can refuse a change to the root. The two private methods `_attach_mount()` and `_detach_mount()` ask the gate themselves, so no caller goes around it.
- **A mount change needs `read_write` at the mount point.** `add_mount()`, `remove_mount()` and `update_mount()` take an `authority`, and a call that names none is treated as any verb is. The check runs before anything changes.
- **Whoever holds `read_write` at a mount point owns that mount's policy.** They can remove the mount and add it again, so they can also change its mask and its permissions in place. An operator who wants a mount's policy kept does not give `read_write` at its mount point.
- **The storage that holds the mount point answers.** It answers through `holds()`, a question that reads and writes nothing. `holds()` is not a verb, so a session cannot ask it. A storage that keeps grants and cannot answer refuses.
- **`add_mount()` makes the mount-point directory as the caller.** It is the caller's own `mkdir`, with the caller's own `parents`. A caller who may not make the directory may not mount there, and `read_write` at the mount point alone does not let a caller make a directory in a parent they cannot see. The check of the mount point, and the delete of its directory when the mount is removed, are the kernel's own work and run as the system actor.
- **If a mount is added above the mount point while the caller's rights are checked, the call refuses and asks for a retry.** The rights were judged by a storage that no longer holds the mount point.
- **Once a mount exists, no verb reaches the rights of its mount point.** `/data` then names two entries, the directory in the storage above and the root of the mounted storage, and `grant()`, `revoke()`, `grants()` and `set_posture()` reach the second. The right to change the mount is on the first, so that right is given before the mount is added or on a directory above it.
- **A session has no way to reach a `Mount`.** A `Mount` carries the storage object, and a session is what an agent holds. Reaching the storage would go around permissions. Only the file-system object has mount methods, and a test keeps it so.

## What a listing shows at a mount point

A mount point names two entries. The **covered directory** is the empty directory stored in the storage above. The **mounted root** is the root of the storage attached there. `MountListing` in `vfs/mounts.py` holds the rules, and the kernel's `ls`, `stat`, `tree` and `glob` call it.

- **The row at a mount point is the mounted root.** It is the row `stat` of the mount point returns to the same caller, so one path shows one entry whichever verb reads it. Plan 9 does this on every directory read, where `mountfix` replaces the entry with a `stat` of what is mounted. On Linux `getdents` returns the covered entry and `stat` crosses into the mount, so `ls -l` shows the mounted root too.
- **The covered directory is never listed.** The filter that drops rows hidden by a deeper mount also drops the row at the mount's own path, before any rows are merged. On both systems the covered directory cannot be reached while the mount is on.
- **The mounted storage never hides a mount's name.** No rights question is asked of it. It decides only how much of the row a caller sees, and a caller who holds nothing gets a bare row with only `path` and `kind`. On both systems the name belongs to the directory above, and the mounted root's permissions never hide it. `stat` and `locate` already showed every mount to every named caller.
- **A mount that gives no row still shows, as a bare row.** That is a mount that refuses the caller, one that cannot answer `stat`, and one whose storage fails. Only a failure adds a record, a warning that names the mount. A dead network mount on Linux still shows its name in the directory above.
- **A directory that leads to a mount point always shows.** `ls`, `stat`, `tree`, `glob` and `locate` answer for it from the mount table when its storage says `not_found`, and any other refusal stands. Plan 9 and Linux let a caller walk to a mount through a parent they cannot read, given walk or search permission. VFS has no such permission, and this rule serves in its place. It is the one rule here that the two systems do not have.
- **A refusal of the listed directory stands.** The anonymous caller on a closed root is refused and learns no mount name. The storage above and the mounted storages are asked at the same time. When the storage above refuses, the answers of the mounted storages are dropped.
- **Each mount point costs one `stat` of the mounted root.** `ls` of a directory with `k` mount points makes `1 + k` storage calls. `tree` over `m` mounts makes `1 + 2m`. `glob` makes one more for each mount point its pattern matches. A directory that holds and leads to no mount point costs what it did, because the kernel keeps the set of directories above a mount in memory.
- **`glob` judges a mount point itself.** No storage returns that row, since the storage above holds a directory that is never shown and the mounted storage does not list its own root. The kernel tests each mount point against the pattern, the exclusions, the extension filters and `kind`, with the same matcher a storage uses on its own rows.
- **In a batch, a directory that holds or leads to a mount point is listed on its own.** `ls` and `stat` with `observations` send the other rows in one call, as before. The rows of those directories come after the others.
- **Nothing was added to the storage protocol.** A storage does not know it is mounted.

Two things still differ from Plan 9 and Linux. `remove_mount()` deletes the mount-point directory, where `umount` leaves it. And a listing waits for every mounted storage with no time limit, as `tree` and a search of several mounts already did.

## Rebuilding a mount table

`mounts()` returns enough to build the same table again. Add every mount bare, then set each mount's policy with `update_mount()`. A mount that is read-only, that masks `mkdir` or that is sealed with `no_overlay` refuses new mounts beneath it, so the policy goes on last. Set the policy of the deepest mount first and the root's last, because a read-only mount also refuses a change to the mounts beneath it.
