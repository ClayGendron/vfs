# Review: `add_mount` takes a posture

Five readings on 2026-11-18 and 2026-11-19. None was given a summary of the work.

| What was read | By | Verdict |
|---|---|---|
| The spec, first draft | A fresh reader | Not yet. The draft set the posture as the system actor, which let a caller open a stored storage they hold no rights in. It also named nothing it builds on. |
| The spec, second draft | The same reader | Not yet: the plan for the line counts of `base.py` and `sync.py` did not add up. |
| The spec, third draft | The same reader | Fit to build. |
| The build, commit `4b01c9eb` | A fresh reader, with mutants and a security lens | Lands. Four mutants that should have been caught survived, and one of them reopened a mount the caller asked to close. |
| The build | A second model | Does not land yet: a mount could cover a directory that gained a file during the posture write, and a posture write could start after `close()` returned. |

## The security finding in the spec

Executed in review. A shared database was mounted closed in one kernel. In a second kernel a caller held `read_write` only at a scratch directory. With the first draft's design, an `add_mount` of that storage with `posture="read_write"` wrote the posture as the system actor, and the anonymous caller of the first kernel could then read the shared files. The grant row named `system`.

Decided: the posture is set as the caller, under the storage's own rule for `set_posture`. The read that comes first is made as the caller too, so a caller who holds nothing cannot learn a hidden posture by guessing it.

Both readings of the build checked this again and found it closed, for a call with an authority, with none, with the kernel's default authority, through the sync face, through `_attach_mount` directly, and across two kernels on one file.

## Found in the build and fixed

Commit `ccd7aeba`.

| Found | Fix |
|---|---|
| The mount point was checked for an empty directory before the posture write and not after. A file written into it during a long write was hidden by the mount. Executed. | When a posture is given, the table and the mount point are checked again after the storage has been asked, whether or not anything was written. |
| The table was not checked between the read of the grants and the write. A `close()` during the read was followed by a posture write. Executed. | The table is checked again immediately before the write. |
| The check of `everyone_holds` for the principal `*` could be removed with every test passing. With it removed, a named caller's grant row at the root stood in for the everyone row, the write was skipped, and a mount asked to be `read` stayed open. | A test for the function and one end to end. |
| The checks before the write, the refusal of a storage that keeps no posture before anything is made, the order of that refusal and the rights check, and `_attach_mount`'s own checks could each be weakened with every test passing. | A test for each, and each was seen to fail under its mutant. |
| Four tests waited on an event with no deadline, so a wrong build hung the suite. | Every wait has a deadline. |
| `validate_posture` took a value equal to a level that was not a `str`. The table check sorted the mount paths again under the lock. | Both fixed. |
| The docstring and two pages said more than the code does about when the storage is written and when a refusal leaves the posture alone. | The words say the three cases that write. |

The build put `src/vfs/mounts.py` over the module ceiling of 1,000 lines once the listing fixes were merged in. `MountListing` and what it needs moved to a new module, `src/vfs/listing.py`, with no change in behaviour. The moved code was checked to be the same text.

## Choices that are not yet confirmed

They are a task in `agents/tasks.md`. The default is `None`, which keeps today's behaviour, so a call that names no posture still leaves a new mount open. A posture that is given replaces the posture stored at the storage's root. No failure puts a posture back.
