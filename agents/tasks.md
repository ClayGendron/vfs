# Tasks

The work that is outstanding, in one list. A task is removed from this file when it is done. Last updated on 2026-11-18.

## Three branches wait to land

None is pushed and none has a pull request. Each sits on the one before it, so they reach `dev` in this order.

1. `glossary-rules`
2. `public-names-follow-the-naming-rules`
3. `a-mount-is-listed-as-a-directory-is`

These tasks stand between the branches and `dev`.

- [ ] **Fix `tests/lint/test_context_shape.py::test_links_resolve`, which fails on `dev`.** The archived spec `2026-11-14-a-row-minted-across-a-posture-change-carries-the-label-the-standing-posture-gives.md` links to three specs that are in `active/`. The gate fails on every pull request until the links are fixed. No branch above caused it.
- [ ] **Review the later code on `public-names-follow-the-naming-rules`.** The branch was reviewed at commit `55a29ffa`. Commit `31adfbd2` came after and has had no fresh reader. It holds the gate on `update_mount`, the mount-point directory made as the caller, the refusal that asks for a retry, and the move of the mount checks to `vfs.mounts`.
- [ ] **Review `a-mount-is-listed-as-a-directory-is`.** Neither the code in commit `2b6b7e40` nor the third draft of `agents/2026-11-18-a-mount-is-listed-as-a-directory-is/spec.md` has had a fresh reader. Decisions 4, 6, 7, 8 and 11 of the spec changed while it was built.
- [ ] **Run the server engine legs on both branches.** `holds` and the listing rule have run on SQLite only.
- [ ] **Run `scripts/ci.sh` to its end.** It stops at the failing link test, so its docs-examples and wheel-size steps have not run inside it. The docs examples pass when run alone.
- [ ] **Push each branch and open its pull request to `dev`.** Each push needs approval of its own.

## Follow-up work

Each is a piece of work of its own, on its own branch.

- [ ] **`search` applies its file filters to rows in hand.** With `observations`, `search` ignores `ext`, `ext_not`, `globs` and `globs_not`. The spec is `agents/2026-11-17-search-applies-its-file-filters-to-rows-in-hand/spec.md`.
- [ ] **The docstrings of 16 source files follow the docstring rules.** About 265 of 311 break a rule in `documentation/maintainers/how-we-write-docstrings.md`, and about 170 public members have none. The largest files are `rights.py`, `paths.py`, `backend.py`, `labels.py`, `ranking.py` and `sync.py`. The words "router", "bind path", "bind point" and "bind site" remain in them, and in `fanout.py` and `pattern_matching/glob.py`.
- [ ] **Seven words used in docstrings get a glossary entry.** They are gate, capability, permission map, posture, authority, trash view and mount point.
- [ ] **Test names say "mount again" and not "remount".**
- [ ] **The docs export tells a type variable by its type.** Today it matches a prefix of the value's text. It would misread `typing.TypeVar(...)` and a value built by the package's own `ParamSpec`. No source hits either case today.
- [ ] **`stat` of a missing path names the right missing part.** Beneath a hidden directory that leads to a mount, `stat` names that directory as missing. `stat` of the directory itself returns a bare row. The two answers disagree.
- [ ] **`read` of a directory that leads to a mount says `wrong_kind`.** A caller who holds nothing on it gets `not_found` today, though `stat` now shows it.
- [ ] **The cost of a listing over mounts is measured on a server engine.** It is counted in calls and not measured. `ls` of a directory with `k` mount points makes `1 + k` storage calls, and each `stat` of a mounted root is 3 `SELECT` for a named caller with warm rights.
- [ ] **The Playwright test "a button that returns to the top shows once the reader scrolls back up" is watched.** It failed once in three runs on an unchanged build and has passed in every run since.

## Waiting on a decision

- [ ] **Whether `remove_mount` keeps the mount-point directory.** It deletes it, and `umount` on Unix leaves it. It also deletes it as the system actor, where `add_mount` makes it as the caller.
- [ ] **Whether `add_mount` takes a posture.** A new mount gives everyone `read_write` until its posture is set, even under a closed root. The docs say so.
- [ ] **Whether a call that reaches several mounts gets a time budget for each mount.** `ls`, `tree` and the searches wait for every mounted storage with none. One stuck storage holds every listing of the directory above it.
- [ ] **How headless Codex runs are set up.** The proposal is a wrapper at `scripts/codex-run.sh`, a Maintainers page, and one sentence in `AGENTS.md`. The facts found: a run is started detached and with no timeout, `project_doc_max_bytes=262144` is needed for the whole of `AGENTS.md` to be read, and an exit code of 0 is the only proof that a run finished. The wrapper was written and tested and is in no repository.
- [ ] **Whether a guided session still ends with a handoff note.** `AGENTS.md` and `documentation/maintainers/how-we-work.md` say it does. The two notes written on 2026-11-18 were deleted, and this file took their lists.
- [ ] **Which feature is next.** Write preconditions, spec 174, is the recommendation. The ranged read and the listing cursor are the others considered.
