# Handoff: a mount is listed as a directory is

Written on 2026-11-18, at the end of the guided session that built the spec beside this file.

## The goal

At a mount point, VFS behaves as Plan 9, Unix and Linux do. A mount shows in the listing of the directory it is in, as the root of the mounted storage, and its name is never hidden.

## The branch

The work is on `a-mount-is-listed-as-a-directory-is`. That branch sits on top of `public-names-follow-the-naming-rules`, which sits on top of `glossary-rules`. None of the three is pushed, and none has a pull request. The three reach `dev` in that order.

## What was built

- `src/vfs/mounts.py` holds a new class, `MountListing`. It holds the kernel's mount table and the set of directories that lie above a mount point. It has five methods.
  - `without_hidden` drops the rows a deeper mount hides. It now drops the row at the mount's own path too.
  - `listed` answers `ls` and `stat` for one path or one batch.
  - `tree` lists a subtree and every mount within the depth.
  - `matched` returns the mount points, and the directories above them, that a `glob` matches.
  - `heads` returns the row at each mount point, from one `stat` of each mounted root.
- `src/vfs/base.py` calls it from `_dispatch_read`, `_tree_region`, `_glob_dispatches`, `_root_probe`, `_dispatch_entry` and `_probe_location`.
- Four things moved from `base.py` to `mounts.py` with no change in what they do: `gather_settled`, `skip_record`, `PathFilters`, and the row filter. `base.py` went from 3,148 lines to 3,080, and its entry in `tests/lint/allowlist.py` went down with it.
- Nothing changed in any storage, in the storage protocol, in the session or in the sync facade.

## Decisions taken while building, with reasons

The spec has each in full. These four differ from the third draft as it was approved.

- **A mount whose storage fails shows a bare row and a warning.** The draft left it out of the listing. Decision 2 says a mount's name always shows, and both Plan 9 and Linux keep the name when the mounted side cannot answer.
- **A mount that refuses the caller shows a bare row and no record.** The anonymous caller on an open root, with a closed mount beneath it, sees the mount's name and nothing else.
- **No time budget was added.** `tree` and a search over several mounts already wait for each mount with none.
- **`glob` judges mount points with the matcher a storage uses.** A second matcher in the planner, `residuals`, treats a pattern that ends in `**` as matching the directory it names, and the storage's matcher does not.

Two more follow from the code.

- **A covered row needs no extra room under `max_count`.** The mount's own row is merged ahead of the parent's rows, so it takes the place the covered row took.
- **In a batch, a directory that holds or leads to a mount point is listed after the other rows.** Before, every row of a batch came back in the order the batch named it, within one mount.

## What was checked

All on 2026-11-18, on the in-memory storage, which is the database storage on SQLite.

- `uv run pytest --cov`: 5,445 passed, 1 failed, coverage 100%. The failure is `tests/lint/test_context_shape.py::test_links_resolve`, which fails on `dev` already. An archived spec links to three specs under `active/`.
- `ruff check`, `ruff format --check` and `ty check` on `src/` and `tests/`: clean.
- `uv run pytest docs README.md -p no:cov -n 0`: 44 passed.
- `scripts/docs.sh check`: passed.

## What is unfinished

- **No fresh reader has reviewed this code or the third draft of the spec.** Nothing reaches `dev` unreviewed. The review is given the diff and this note.
- **The server engines were not run.** The change is in the kernel and reads storages only through `stat`, `ls`, `tree` and `glob`, so the engine legs are expected to pass. That is not checked.
- **`scripts/ci.sh` was not run to its end.** It stops at the failing link test, so its wheel-size step did not run.
- **`test_links_resolve` fails on `dev`.** It fails the gate of any pull request until the three links are fixed.
- **`stat` of a missing path beneath a hidden directory that leads to a mount names that directory as the missing part.** `stat` of the directory itself now returns a bare row. The two answers disagree.
- **`read` of a directory that leads to a mount still answers as its storage does.** A caller who holds nothing on it gets `not_found`, where a visible directory gives `wrong_kind`.
- **`remove_mount` deletes the mount-point directory, and `umount` leaves it.** This was so before the work and was left alone.
- **A new mount is open to everyone until its posture is set, even under a closed root.** The docs now say so. Whether `add_mount` should take a posture is not decided.
- **The cost at scale is counted in calls, not measured.** `ls` of a directory with `k` mount points makes `1 + k` storage calls, and each `stat` of a mounted root is 3 `SELECT` for a named caller with warm rights.
- **A listing has no time budget for a mounted storage.** One stuck storage holds every `ls` of the directory above it. `tree` had this already.
