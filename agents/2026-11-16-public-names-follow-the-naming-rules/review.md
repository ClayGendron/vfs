# Review: who may change a mount, after the first review

The branch `public-names-follow-the-naming-rules` was reviewed once at commit `55a29ffa`. Commit `31adfbd2` came after and was reviewed on 2026-11-18, by two independent readings of the diff. Neither was given a summary of the work. One reading was made with a second model. Both ran throwaway scripts against the code.

Both verdicts were "does not land yet". The fixes are commit `51f0cf3f`.

## Found and fixed

| Found | Fix |
|---|---|
| `update_mount` and `remove_mount` acted on rights judged for a mount point that had since changed. A caller changed a mount that the storage above it had never judged them for. Both readings found it, and one reproduced it. | What was judged is captured before the rights check and checked again under the mount lock, in all three mount changes. It is `MountJudgement` in `vfs.mounts`. The change is refused with a `ValueError` that asks for a retry. |
| `add_mount` compared only the storage that judged, so a storage detached and attached again at another path passed. | The path of the mount that holds the mount point is compared as well. |
| The root's exemption in `update_mount`, the `mkdir` half of its gate, and the authority of the `restore` in `add_mount` could each be wrong with every test passing. | A test for each, and each was seen to fail under its mutant. |
| A test of `normalize_mount_path` asserted nothing about the path returned. | It asserts the exact value. |
| The docs said `update_mount` is refused wherever a remove and an add would be. It asks the gate for `delete` and `mkdir` and nothing more. | The docstring, the mounts page and the access-levels page say what the gate asks. |
| The docs said `read_write` at an existing mount-point directory is enough to mount there. It is not for a caller with no name when a directory between the root and the mount point is closed. | The access-levels page says so. |
| The docs export told a type variable by a prefix of its text. | It tells one by what the value is. |

## Found and left, each a task in `agents/tasks.md`

- `remove_mount` deletes the mount-point directory after the mount lock is released. An `add_mount` at the same path that runs between the two can end with a live mount on a deleted directory. Executed.
- `add_mount` restores a deleted file, or a deleted directory that is not empty, and then refuses the mount. The restored rows stay. Executed.
- When `close()` lands during the cleanup of `remove_mount`, the detached storage is neither returned nor closed. Executed.
- The rights check is made once, before the change. A grant revoked after the check and before the commit does not stop that change. The mounts page now says so.
- `grants` can be masked with `deny_ops`, though it only reads.
- `add_mount(storage, path="")` falls back to the storage's name.
- `require_storage` accepts a storage whose members are not callable.
- The judgement compares the path and the storage object. The same storage attached again at the same path passes it. The mounts page now says what is compared.
- The docs export does not follow an alias of a type variable.
