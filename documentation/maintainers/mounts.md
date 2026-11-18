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

- **A mount change is a write at its mount point.** Adding a mount needs what `mkdir` at the mount point needs, and removing one needs what `delete` there needs. A read-only parent takes no new mount and loses none. The two private methods `_attach_mount()` and `_detach_mount()` ask the gate themselves, so no caller goes around it.
- **A mount change needs `read_write` at the mount point.** `add_mount()`, `remove_mount()` and `update_mount()` take an `authority`, and a call that names none is treated as any verb is. The check runs before anything changes.
- **The storage that holds the mount point answers.** It answers through `holds()`, a question that reads and writes nothing. `holds()` is not a verb, so a session cannot ask it. A storage that keeps grants and cannot answer refuses.
- **A session has no way to reach a `Mount`.** A `Mount` carries the storage object, and a session is what an agent holds. Reaching the storage would go around permissions. Only the file-system object has mount methods, and a test keeps it so.

## Rebuilding a mount table

`mounts()` returns enough to build the same table again. Add every mount bare, then set each mount's policy with `update_mount()`. A mount that is read-only, that masks `mkdir` or that is sealed with `no_overlay` refuses new mounts beneath it, so the policy goes on last.
