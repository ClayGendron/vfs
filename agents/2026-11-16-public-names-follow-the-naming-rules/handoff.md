# Handoff: public names follow the naming rules

Written on 2026-11-18 for the autonomous pass. The branch is `public-names-follow-the-naming-rules`. It sits on top of the unmerged branch `glossary-rules`. Neither branch is pushed.

## The goal

The code follows the naming rules in `documentation/maintainers/how-we-name.md`. A noun is a type or a glossary term. A method is a verb then a noun. A type that a public signature names can be imported. A family of specialist types is a public module.

The goal grew during the work to cover three more things: every mount change passes the gate and needs an authority, a standard for docstrings, and the docstrings of `src/vfs/base.py` and `src/vfs/mounts.py` rewritten to that standard.

## Decisions, with reasons

- **One public `Mount` class in `src/vfs/mounts.py`.** It replaced three shapes of the same facts. `Mount.to_payload()` gives the JSON form.
- **The mount methods are `add_mount`, `remove_mount` and `update_mount`.** `remove_mount` returns the `Mount`, so the caller can close the storage. The steps that only change the table are private, `_attach_mount` and `_detach_mount`, because a public step went around permissions.
- **A mount change is a write at its mount point and passes the gate.** Adding needs what `mkdir` there needs, removing what `delete` there needs, and `update_mount` needs both, because it does what a remove then an add would do. The root has no mount above it, so the gate is not asked for the root.
- **A mount change takes an authority, and the caller must hold `read_write` at the mount point.** The storage that holds the mount point judges, through `holds`, a question that is not a routed verb. A call with no authority is treated as every verb treats one.
- **`add_mount` makes the mount-point directory as the caller.** It works as the caller's own `mkdir` does. Consequence: `read_write` at the mount point alone does not let a caller mount where the directory is absent and the parent is hidden from them.
- **Whoever holds `read_write` at a mount point owns that mount's policy.** They can remove the mount and add it again, so changing its mask or its map in place gives them nothing more.
- **A mount added above the mount point while rights are checked refuses the change.** The call raises `ValueError` and asks for a retry.
- **The op that sets a posture is `set_posture` at every layer.** A `deny_ops` mask that names `"posture"` no longer masks anything.
- **`open_session` replaced `session`.**
- **Fifty-three names are exported from `vfs`.** `ranking`, `rerank`, `rendering`, `embedding` and `permissions` are public modules, and each lists what it offers. The docs export refuses to build when a public signature names a type that no exported name reaches.
- **The pure mount checks live in `vfs.mounts`.** `normalize_mount_path`, `validate_deny_ops`, `require_storage` and `rights_refusal` moved there, which also keeps `base.py` under its line count.
- **Docstrings follow `documentation/maintainers/how-we-write-docstrings.md`.** `base.py` and `mounts.py` follow it in full.
- **"Kernel" is a glossary term** and is the word for `AsyncVirtualFileSystem` in docstrings.

## Checked

- `ruff check`, `ruff format --check` and `ty` are at zero on `src/` and `tests/`.
- The whole suite: 5,412 passed and 1 failed on 2026-11-17. The failure is `tests/lint/test_context_shape.py::test_links_resolve`.
- `pytest docs README.md`: 44 passed.
- `scripts/docs.sh check`: exit 0.
- The branch was reviewed at commit `55a29ffa` by a reader that did not write it. The findings are fixed in commit `31adfbd2`, except those listed below.

## Unfinished

- **`test_links_resolve` is red on `dev`.** The archived spec `2026-11-14-a-row-minted-across-a-posture-change-carries-the-label-the-standing-posture-gives.md` links to three specs that are in `active/`. The gate fails on any pull request until the links are fixed. The fault is not from this branch.
- **The code written after the review has not been reviewed.** It is commit `31adfbd2` and what follows it: the gate on `update_mount`, the directory made as the caller, the retry refusal, and the move of the mount checks to `vfs.mounts`.
- **The docstrings of 16 other source files do not follow the rules.** About 265 of 311 break a rule, and about 170 public members have none. The largest are `rights.py`, `paths.py`, `backend.py`, `labels.py`, `ranking.py` and `sync.py`. The words "router", "bind path" and "bind site" remain in those files.
- **`holds` has run on SQLite only.** The server engine legs have not been run on this branch.
- **A mount shared with a caller does not show in the listing of its parent.** The spec is `agents/2026-11-18-a-mount-is-listed-as-a-directory-is/spec.md`. It is built on its own branch. Aiming the grant verbs at a mount point is deferred there.
- **`search` ignores its file filters when it is given `observations`.** The placeholder spec is `agents/2026-11-17-search-applies-its-file-filters-to-rows-in-hand/spec.md`.
- **`remove_mount` deletes the mount-point directory as the system actor.** `add_mount` now makes it as the caller. Whether the two should match was not decided.
- **A new mount starts open even under a closed root.** Each storage starts at posture `read_write`. This is existing behaviour and was not changed.
- **The export's test for a type variable is a prefix match on the text of a value.** It would misread `typing.TypeVar(...)` and a value built by the package's own `ParamSpec`. No source hits either case today.
- **Terms used in docstrings with no glossary entry:** gate, capability, permission map, posture, authority, trash view, mount point.
- **"remount" remains in some test names.**
- **The Playwright test "a button that returns to the top shows once the reader scrolls back up" failed once in three runs** on an unchanged build earlier in the work. It has passed in every run since.

## Order of landing

`glossary-rules` lands first, then this branch. Each needs a push, which needs approval each time, and a pull request to `dev`.
