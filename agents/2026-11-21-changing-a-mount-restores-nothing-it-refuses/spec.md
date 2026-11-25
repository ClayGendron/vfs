# Changing a mount restores nothing it refuses

A draft, written on 2026-11-21 from what pull request 24 left. It is not reviewed, and nothing is built.

## The outcome wanted

An `add_mount` that is refused leaves the parent storage as it found it. A mount change calls no storage that `close()` has closed.

## Builds on

Pull request 24, which made a removal in flight refuse a mount at its path, and made `close()` close what it removes.

## The problem

### A refused mount leaves restored rows behind

`add_mount` at a path that holds a deleted file, or a deleted directory that is not empty, restores the site and then refuses the mount. The restored rows stay. Shown by a script that ran.

A fix was tried on 2026-11-21 and withdrawn. It judged the site through its trash view before restoring. The trash view of a deleted directory lists every deleted row beneath it, those an earlier delete removed among them, and `restore` brings back only the rows of the directory's own delete. So the probe refused sites that `restore` would leave empty, and that broke an ordinary cycle of unmount and remount.

### A mount change asks `holds` outside the one place storage calls go through

A `close()` that lands between the entry check and the `holds` call still calls a closed storage. Read. On 2026-11-21 no `await` was found between the closed check in `_require_mount_rights` and the `holds` call, so on one event loop `close()` cannot land there today. Any `await` added between them later opens it.

## Decisions

1. **The trash view says which delete each row belongs to.** Each deleted row carries the identity of the delete that removed it, and the view exposes it. `add_mount` then asks the view for the rows of the site's own delete alone, and refuses before it restores anything when one of them would stay. This changes what the trash view exposes.
2. **`holds` stays a direct call, and a test pins that no `await` comes between the closed check and it.** Routing `holds` through `_call_storage` would make it a dispatched op, which is a larger change than the risk it removes.

## Tests

A reproducing test first: `add_mount` at a deleted directory with a live child is refused, and the trash view afterwards lists the same rows as before. For decision 2, a test that fails when the closed check and `holds` are separated by a yield.

## Scope

In: the site check of `add_mount`, the trash view's row shape, and the one test of decision 2. Out: every other mount change.

## Not checked

- Whether the storage protocol's trash view can carry a delete's identity on every storage, or only on the database storage.
- What the identity costs per deleted row at the reference deployment's 10,000,000 files.

## Choices to confirm

1. **Does the trash view expose a delete's identity?** Recommended: yes, as decision 1. Alternative: `add_mount` refuses any site that holds a deleted row. Its cost: an ordinary remount at a path that was deleted once is refused.
2. **Decision 2: pin it, or route `holds` through `_call_storage`?** Recommended: pin it.

## One line

A refused `add_mount` restores nothing, because the trash view says which delete each row belongs to, and the `holds` call of a mount change stays next to its closed check.
