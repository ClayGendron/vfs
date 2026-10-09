# 153 — Docs tell the truth about v2: every README claim matches the live tree

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** docs (README, `docs/`, two module docstrings); no code
  behaviour changes
- **Depends on:** nothing lands first. 161 (version rows on every
  mutation) decides whether the versioning sentence comes back.
- **Research it stands on:**
  `../../../research/2026-10-08-smartowl-workspace-integration-issues.md`
  items 1–5, 16, 22 and 23.

## Intent

The README is the first thing a host developer reads, and today its
first code block does not import, its permission string raises, and
its verb table promises an undo that no write path provides. A host
copying the README fails at mount time. Make every sentence in the
README and `docs/` true of the live tree at the commit it ships with,
and say plainly what is designed but not built.

One line: the README describes the code that exists, not the code we
want.

## What is wrong today (verified 2026-10-08)

1. **Versioning.** `README.md` L52–55 calls mutations "versioned,
   reversible" and says "a mutation is always versioned so it can be
   undone". No write path mints a version row; `write` and `edit`
   replace the body in place. Only delete is reversible, through trash
   and `restore`.
2. **Permission string.** L110 says `"read_only"`. `validate_permission`
   accepts `"read"` and `"read_write"` and raises `ValueError` on
   anything else.
3. **Backend classes.** L31–35 import `DatabaseFileSystem` and
   `PostgresFileSystem` from `vfs.backends`. There is no such package;
   the class is `vfs.storage.backends.DatabaseStorage`, constructed
   with `url=` or `session_factory=`.
4. **Deepagents doc.** `docs/deepagents-integration.md` imports
   `VFSClientAsync` and `vfs.exceptions` from the previous generation;
   a `deepagents` extra still exists in `pyproject.toml`.
5. **Tools at paths.** The banner says tools at paths are "designed,
   not built" while `VirtualFileSystem.run` exists. True, but a reader
   cannot tell what `run` does today.
6. **Permissions per instance.** `src/vfs/permissions.py` L57–81
   documents that a permission map lives on the node, not the data,
   and two nodes on one schema do not see each other's maps. The
   docstring still names `DatabaseFileSystem`, and the README never
   mentions the limitation.
7. **Default posture.** A `DatabaseStorage` provisions `open`
   (ADR 068); anonymous read, write and delete all succeed. The
   README does not say so.
8. **Cross-mount copy and move.** Refused `cross_mount` by design;
   the README does not say so.
9. **Binary edit.** `edit` refuses a bytes body by design (152 §1); the
   README does not say so.

## Scope

- Rewrite the README's first code block against the live API: one
  `VirtualFileSystem`, two `DatabaseStorage` mounts (`url=` for one,
  `session_factory=` for the other), `permissions="read"` on one
  `add_mount`. The block is executed by a doc test or a `tests/` check
  that imports every name it uses.
- Replace `"read_only"` with `"read"` and name the three forms a
  permission map takes (`"read"`, `"read_write"`, a per-prefix map).
- Soften the verb table: "Mutate" answers *changes; delete is
  reversible through trash and `restore`*. The sentence "a mutation is
  always versioned so it can be undone" leaves until 161 lands, and
  161's landing note restores it.
- Add a short **Known limits** section to the README with four bullets:
  permissions are per node, not per row (link spec 058 and ADR 073 for
  the row-level answer); a fresh storage is `open` and anonymous
  callers may write until the posture changes (link ADR 068); copy and
  move do not cross a mount boundary (link 160); `edit` does not touch
  a binary body, use `write`.
- `run`: one sentence under the banner saying the verb exists and
  routes to a storage that declares it, and no shipped storage does.
- `docs/deepagents-integration.md`: either delete it or replace it
  with a stub that says the v2 adapter is not written and points at the
  `BackendProtocol` study in the 2026-09-15 landscape memo. Remove the
  `deepagents` extra from `pyproject.toml` if nothing imports it.
  `[NEEDS CLARIFICATION: delete the doc and the extra, or keep a stub?
  Leaning delete both; the memo is the design record.]`
- `permissions.py` docstring: `DatabaseFileSystem` → `VirtualFileSystem`.
- Out of scope: the version verb (161), the release (158), any code
  behaviour.

## Acceptance criteria

- Every `import` and every class name in `README.md` and `docs/*.md`
  resolves in the live tree; a test under `tests/docs/` extracts the
  README's fenced Python blocks and imports every `from vfs...` name
  they use.
- `grep -rn "read_only\|DatabaseFileSystem\|PostgresFileSystem\|vfs.backends" README.md docs/ src/` returns nothing except
  `VFSErrorKind.read_only`.
- The README has a **Known limits** section naming the four limits
  above with links.
- `scripts/ci.sh 3.13` green.
