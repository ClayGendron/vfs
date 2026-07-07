# 055 — Plan

Approach for landing the spec in one pass: new backend first (it has no
dependents), then the protocol/ADR-003 wiring it implements, then the
router rebuild on top of it, tests last.  Everything lands on `main` per
repo workflow; verification (pytest/ruff/ty) runs once at the end of the
session per the working agreement.

## 1. Vocabulary

No kind changes.  Mount points are plain directories everywhere —
stored and read (settled 2026-07-07: no `mount` kind, stored *or*
projected; mount-ness lives in the mount table).  The only vocabulary
edit is `ops.py`: delete `SPINE_READ_OPS` and its docstring-table row
(the spine dies with this story; `TwoPathOperation` and the rest stay).

## 2. ADR 003 wiring on the mutation surface

The new backend is the reference implementation of ADR 003, so the
flags must exist before it can honor them:

- `SupportsMutation.mkdir` gains `parents: bool = False,
  exist_ok: bool = False`.
- `SupportsMutation.write` gains `parents: bool = False` (per-call, not
  per-entry — ADR 003's working assumption).
- Router publics `mkdir` / `write` grow the same keywords and thread
  them through `_route_single` / `_route_entry_batch` kwargs.
- Test doubles absorb via `**kwargs` already; no double changes needed
  for signatures.

## 3. `InMemoryStorage` (`src/vfs/backends/memory.py`)

Families implemented: read, pattern search, mutation.  Not
glean/graph/run — no retrieval index, no
subgraph, no tools.

- **State:** `dict[Path, _Row]` where `_Row` is a small dataclass
  (`kind: ObjectKind`, `content: str | None`,
  `description: str | None`).  Root `/` always exists as a directory
  and is neither deletable nor writable-over.  Deliberately not
  `Entry`-backed: `Entry`'s validators derive kind/metrics from the
  path, which would fight explicit kinds; observations are built thin,
  null meaning "not populated."
- **POSIX rules (ADR 003), enforced in one shared gate used by every
  minting op:** missing ancestor → `not_found` naming the first missing
  one; ancestor exists as non-directory → `wrong_kind`
  (unconditional); `parents=True` mints the chain; `mkdir` on an
  occupied site → `exists` unless `exist_ok=True` and the occupant is a
  directory; writing onto a directory → `wrong_kind`; file overwrite
  governed by `overwrite`/`exists`.
- **Reads:** `stat` (row or `not_found`), `ls` (children of a
  directory; a file lists itself, POSIX-style), `tree` (subtree with
  `max_depth`), `read` (file content; directory → `wrong_kind`).
- **Mutations:** `write` (path/content or entries batch), `edit`
  (sequential `EditOperation`s via `vfs.replace.replace`, atomic — one
  failed match applies nothing), `delete` (cascade default; root
  protected), `mkdir`, `move`/`copy` (`ResolvedPair` batches, subtree
  moves, dest parent must exist), `mkedge` (stores an edge row at
  `edge_out_path`, parents auto-minted — internal machinery is exempt
  from ADR 003 by its own terms).
- **Pattern search:** `glob` (fnmatch over stored paths, `ext` and
  `max_count` honored), `grep` (regex over file content honoring
  `case_mode`, `fixed_strings`, `word_regexp`, `invert_match`,
  `output_mode` lines/files/count, `max_count`, ext/glob filters;
  context args accepted, minimal rendering).  Scope `paths` filter by
  prefix; empty means unscoped.
- **`allow_files: bool = True`.**  With `False` (the router's default
  node): any op that would store non-directory content — `write`/`edit`
  of file content, file entries, `mkedge` — classifies `unsupported`
  with a "directories only" message; `mkdir`, directory `delete`/
  `move`/`copy`, all reads, and pattern search over names still work
  (`grep` finds nothing, honestly).  Families stay whole.

## 4. Router rebuild (`src/vfs/base2.py`)

- **Constructor:** `storage=None` resolves to
  `InMemoryStorage(allow_files=False)`; `self._storage` is now always a
  `StorageBackend`.  Storageless branches die: the `_gate_terminal`
  no-storage `not_found` arm, `_call_local_impl`'s `None` check,
  `capabilities()`' hardcoded `{"ls","stat","tree"}` seed (the derived
  set now starts from `self._storage_ops`).
- **Spine removal:** delete `_spine_children`, `_is_spine_path`,
  `_spine_row`, `_spine_read`, `_spine_ls`, `_spine_tree`,
  `_absorb_not_found`, the `SPINE_READ_OPS` peels in `_route_single`
  and `_dispatch_grouped_observations`, and `_gate_terminal`'s
  `spine_check` parameter (mutations against a stored directory get
  `wrong_kind` from storage truth now).
- **What survives, re-anchored on the mount table (routing, not
  visibility):**
  - `_mounts_beneath(rel)` — the mounts strictly under a self-owned
    path.  Used by fan-out scope expansion: a self-owned scope
    dispatches to own storage *and* expands to capable mounts beneath
    it (root scope → all mounts, storage unscoped); the silent-skip
    rule for incapable storage on a *region* scope (root, or a path
    with mounts beneath) is preserved.
  - `tree` local wrapper: own-storage `tree` + parallel descents into
    mounts beneath the path with the same depth-budget arithmetic as
    today (`tree("/", max_depth - distance)`, skip at budget ≤ 0,
    silent skip of incapable mounts) — minus the skeleton synthesis,
    since stored rows are real now.
  - **Mount projection** `_project_mounts(result)`: applied to every
    *local* read result (`_route_single`, grouped dispatch, fan-out,
    tree) — a row whose path is a bound mount path keeps its stored
    `kind="directory"` and gains the child's live `description`
    (`model_copy(update=...)`; `Observation` is frozen).  A node's own
    root row picks up `self.description`, preserving today's
    metadata composition when a parent reads a mount point.  Child
    results need nothing: the child projects its own rows before
    rebasing (recursion).
- **`add_mount(filesystem, path=None, *, parents=False)`** — the fused
  mkdir+bind, ordered validate → mkdir → commit-gate bind under the
  lock:
  1. Existing checks (delegation, self/cycle/duplicate, deeper-mount).
  2. `storage.mkdir(path=mount_path, parents=parents)` — the one site
     authority: stores the mount-point directory; a failed `Result`
     raises `ValueError` carrying its message (missing parent names the
     first missing ancestor — the parent rule and site rule both live
     here).  No standalone probe: `is_path_writable` was dropped from
     the protocol when mkdir became check-and-act.
  3. `_commit_mount` (unchanged).  A commit-gate failure deletes the
     directory just created (udisks-style cleanup of the fused op's own
     side effect); minted parents persist.
  - Consequence, named in the docstring: a backend without the
    mutation family cannot host new mounts (it cannot store the
    directory) — the read-only-filesystem analogue.
  - Delegation passes `parents` through.
- **`remove_mount`:** pop the binding (as today), then
  `storage.delete(path=mount_path)` — the directory is add_mount-owned
  and provably empty.  A failed delete raises after the unbind; the
  namespace is left in the loud-but-recoverable orphan-directory state
  the spec accepts.
- `mkedge`'s gate loses its `spine_check=False` special case along
  with the parameter.

## 5. Tests

- **New `tests/test_backends_memory.py`:** the backend contract —
  POSIX parent/site rules per verb (both flag modes), `exist_ok`,
  move/copy subtrees, edit atomicity, glob/grep modes,
  `allow_files=False` refusals pinned as `unsupported`, root
  protection.
- **`tests/test_base_mounts.py`:** add the parent rule
  (`/x/y` fails naming `/x`; `parents=True` mints `/x`), the stored
  mkdir/rmdir lifecycle (dir present in storage after add, gone after
  remove, re-mount clean), projection (`ls` shows a directory row
  carrying the child's description), read-only-backend refusal.
  Sparse-mount tests
  invert into failures without the flag.
- **`tests/test_base_spine.py` retires.**  Surviving semantics (mount
  rows in `ls`, tree depth budgets across mounts, fan-out region
  expansion, grouped-read equivalence — story 050's acceptance) move
  into `test_base_mounts.py` / `test_base_dispatch.py` rewritten
  against stored directories.
- **Ripples:** bare-node tests that assumed a pure router
  (`not_found` with no storage, capabilities == `{ls,stat,tree}`) now
  see a real directories-only backend; doubles that host mounts must
  carry the mutation family (`RecorderStorage` already does).

## Trade-offs accepted

- No standalone site probe.  `mkdir` is the single site authority
  (check and act in one call, no TOCTOU window), so `is_path_writable`
  came off the protocol; a side-effect-free "can I write here?" probe
  can return later if MCP serving or a UI needs one.
- `grep` in the reference backend is honest but minimal — full flag
  semantics, minimal match rendering.  The database backend remains the
  serious implementation.
- A mutation-incapable backend cannot host mounts.  POSIX-faithful and
  a direct consequence of storing the mount-point directory.
