# The unified path-resolution chokepoint

*The concrete design for collapsing all path handling behind one gate — the
sibling of [`031-unified-entry-creation-chokepoint`](../031-unified-entry-creation-chokepoint/design.md).
Story 031 puts one door in front of every `VFSEntry` **row**; this story puts one
door in front of every **path string** that enters or leaves the system. Both
borrow the same lesson from mature filesystems — `vfs_create` gates row creation,
`namei` / `walk` gates path resolution. Every `file:line` was read against the tree
(`src/vfs/paths.py`, `src/vfs/base2.py`, `src/vfs/backends/database.py`,
`src/vfs/routing.py`).*

> **Superseded in part (2026-06).** Two later decisions override this document; see
> **`HANDOFF.md`** for the current task and **`vfspath-typed-handle.md`** for the type
> design. (1) **User-scoping is dropped** — tenant isolation moves to a permission
> layer over one global namespace, so the scoping tier (`§3`), the scoping invariant
> (`§5`), and open-question 1 (`§7`, `scope_like_prefix`) no longer apply, and
> `scope_path`/`unscope_path`/`validate_user_id` are deleted. (2) The gate's result is
> branded by a **`VFSPath`** type. The rest of this design — the gate, validate/
> normalize separation, `check_mutable_path`, the mount gate — still stands.

---

## 1. The problem

A path is the one thing a caller hands VFS on every operation, and before it can
touch storage it must be made **canonical**: NFC-normalized, absolute,
`posixpath.normpath`-collapsed, validated for length/control-characters/reserved
space, and — for a multi-tenant backend — **scoped** under `/{user_id}`. On the
way back out the scoping must be stripped so the caller never sees it.

The pure machinery for all of this **already exists and is good**: `src/vfs/paths.py`
is a clean library of pure functions — `normalize_path` (`:166`), `validate_path`
(`:187`), `validate_mutation_path` (`:281`), `parse_kind` (`:316`), the constructors
(`chunk_path:414`, `version_path:425`, `edge_out_path:434`, `api_path:450`), the
decomposers (`decompose_edge:469`, `endpoint_root:240`), and the scoping pair
(`scope_path:513` / `unscope_path:525`).

The problem is the same one story 031 found for rows: **the library is not enforced
as a door.** It is a *popular helper*, not a *chokepoint* (the litmus test from
031/explanation §1.2). Code reaches around it and hand-assembles or hand-inspects
paths in many places. Each is a **second door** — a place where a path can enter
storage un-normalized, un-validated, or wrongly-scoped:

- **User-scoping is a per-call-site convention, not a funnel.** `_scope_path(path,
  user_id)` (`database.py:544`) is called manually at the top of ~15 backend methods
  (`_read_impl:1643`, `_write_impl:1811`, `_copy_impl:2618`, `_move_impl:3040`,
  `_mkedge_impl:2880`, stat/ls/grep…). Omit the call in a new method and scoping
  silently does not happen. Worse, several sites bypass even that helper and
  hand-encode the `/{user_id}` layout directly: LIKE patterns `f"/{user_id}/%"`
  (`:1221`, `:1262`, `:1292`, `:3271`, `:3502`), prefix scoping
  `f"/{user_id}/{prefix.lstrip('/')}"` (`:3175`), and
  `scope_path(...) if ... else f"/{user_id}/{pattern}"` (`:3348`, mirrored in
  `backends/mssql.py:1103` and `backends/postgres.py:1367`).
- **Metadata-namespace detection is hand-coded** with raw `startswith` instead of
  `is_meta_root_path` / `parse_kind`: `row.parent_dir.startswith("/.vfs")`
  (`:2681`), `path.startswith("/.vfs")` (`:3813`), `pattern.startswith("/.vfs")`
  (`:3369`).
- **Meta paths are hand-assembled** with f-strings rather than the constructors:
  `f"{meta_root(f.path)}/__meta__/chunks"` (`:717`, `:2155`).
- **`routing.py` rolls its own normalization** — `lstrip`/`rstrip`/`startswith("/")`
  (`:63`, `:103`, `:106`, `:124`, `:138`, `:140`) — a parallel implementation of
  what `normalize_path` already does.
- **The router does not validate at the public boundary at all.** In `base2.py`,
  `read`/`stat`/`ls` (`:471`–`:499`) pass the raw path into `_route_single` →
  `_resolve_terminal` (`:230`), which calls `normalize_path` but **never**
  `validate_path`. Only *mount* paths are validated (`_normalize_mount_path:186`).
  So `read("/\x00bad")` is normalized and routed without ever being rejected.

The resolution is the same shape as 031: **unify the gate; keep the pieces pure.**
`paths.py` stays the pure library. One runtime funnel — `_resolve_path` — becomes
the only way a caller-supplied path becomes a canonical internal path, and the
scattered scoping/detection/assembly second doors are routed through the library
they were reaching around.

## 2. The model: canonical path is the internal form; raw and scoped are boundary forms

This mirrors 031 §2 (`id` is identity, `path` is correlation). A path exists in
three forms, and the chokepoint's whole job is to keep the conversions in one place:

| form | who sees it | produced by |
|---|---|---|
| **raw** | the caller hands it in | the public method's `path=` argument |
| **canonical** | everything internal (routing, the entry gate, queries) | `_resolve_path` — validate → normalize |
| **scoped** | the storage rows / SQL | `scope_path(canonical, user_id)` at the storage seam |

Two rules fall out, and they are the whole design:

1. **Exactly one canonicalization, at entry.** Every public method funnels its
   incoming path(s) through `_resolve_path` *once*, at the boundary, before routing
   or storage. Downstream code may assume any path it holds is already canonical and
   never re-normalizes defensively.
2. **Exactly one scoping, at the storage seam, and one unscoping, at the result
   seam.** `scope_path` is applied where canonical paths cross into physical storage
   (the backend), and `unscope_path` where stored paths cross back out into a
   `VFSResult` (`results.py:415`). Nothing in between re-encodes the `/{user_id}`
   convention by hand.

## 3. The two tiers: generic resolve (router) vs. specific scope (backend)

Story 031/explanation §1.3 names the single most important structural idea: the
kernels unify the **gate**, not the **mint** — `vfs_create` runs identical generic
checks, then dispatches to a per-filesystem `->create`. Path handling has the same
split, and getting the split right is what keeps this change small:

- **Generic tier — the router (`base2.py`).** Validation and normalization are true
  of *every* filesystem, storage or not, and they are storage-layout-agnostic. They
  belong in the router, upstream of routing, so a path is canonical before any mount
  decision or storage call. This is VFS's `namei`: raw path in, canonical path out,
  invariants enforced before dispatch.
- **Specific tier — the storage backend (`database.py`).** Scoping is *physical
  layout policy*: it depends on how a particular backend lays tenants into its
  table, and a pure router has no rows to scope. So `scope_path` / `unscope_path`
  stay at the storage seam, owned by the backend — the analogue of `->create` being
  per-filesystem. A union or remote mount may scope differently or not at all; the
  router must not bake one tenant layout into the routing layer.

This is why the chokepoint is **not** a single function that also scopes: scoping at
the router would force one storage layout onto every mount and would double-scope
with the backend. The router gate canonicalizes; the backend gate scopes. Each tier
has exactly one door.

> **The boundary that makes this safe** (parallels 031 §3 step 3). The backend's
> scoping skip is keyed on the principal: `user_id=None` means system/admin (ETL,
> internal) and the application-level scoping is intentionally waived, with the
> deployment's database grants governing. The public surface must inject an
> authenticated principal so `None` can only originate internally — the same
> discipline 031 requires for its permission carve-out.

## 4. The chokepoint: `resolve_path`

The gate is a **pure function in `paths.py`** — `resolve_path` — not a router method.
`paths.py` is the library; `resolve_path` is the one door that *composes* the
library's pure pieces in the right order so none can be skipped. The router (and any
other caller) invokes it at the boundary and maps its result onto the caller's error
channel. It returns either the canonical path or a structured rejection reason — it
**never raises** (so a router can turn the reason into a `VFSResult`, and a
mount-time caller can turn it into a `ValueError`).

```python
class ResolvedPath(NamedTuple):
    path: str | None          # canonical path, or None on failure
    error: str | None         # rejection reason, or None on success

def resolve_path(path: str, *, mutation: bool = False) -> ResolvedPath:
    """Canonicalize a caller-supplied path: validate, normalize, (authorize).

    The single door through which a caller-supplied path becomes a canonical
    internal path. Storage backends scope the result separately (Tier 2, §3).
    Never raises.
    """
    canonical = normalize_path(path)                       # normalize EXACTLY once
    valid, reason = validate_path(path, normalized=canonical)
    if not valid:
        return ResolvedPath(None, reason)
    if mutation:
        ok, reason = check_namespace_writable(canonical)   # the authorization gate
        if not ok:
            return ResolvedPath(None, reason)
    return ResolvedPath(canonical, None)
```

The funnel, in order — every step is a pure function in `paths.py`; the gate only
**sequences and enforces** them (§6 explains why this ordering, drawn from the
reference systems):

1. **raw rejects + `normalize_path`** — `validate_path` rejects null bytes, control
   characters, and over-length input on the *raw* string (before `normpath` can
   mangle hostile input); `normalize_path` runs exactly once and the canonical form
   is threaded into `validate_path` (via `normalized=`) for the segment-length check,
   so the path is never normalized twice. `normalize_path` is a pure transform that
   never raises; `validate_path` is the rejecter.
2. **`check_namespace_writable`** (mutating ops only) — the authorization gate
   (renamed from `validate_mutation_path`, §6 D2): rejects writes to `/` and to
   reserved metadata space, allowing only the machine-authored endpoints and reserved
   directory skeleton. Read-family ops (`read`/`stat`/`ls`/`grep`) skip it;
   write-family ops (`write`/`edit`/`move`/`copy`/`mkedge`/`rm`) pass `mutation=True`.

**Where it is called.** Every public method funnels its incoming path through it
first; `_route_single` (`base2.py:397`) is the shared funnel for single-path ops, so
the cleanest placement is *there*, with the candidate path-set funneled in
`_group_candidates_by_terminal` (`base2.py:303`, already the one place candidate
paths are walked). After this lands, `_resolve_terminal` may trust its input is
canonical.

### 4.1 The mount gate is the same gate plus mount rules

`_normalize_mount_path` (`base2.py:186`) is a *specialization* of the gate, not a
parallel implementation: a mount path is a canonical path with extra constraints (not
root, no reserved `.vfs` segment, no stray-whitespace segments). It calls
`resolve_path` for the shared validate+normalize, keeps the normalized-form-equality
check (mounts *reject* non-canonical input like `/a/../b` rather than silently
collapsing it — so the raw-vs-canonical comparison must run on the un-collapsed form),
and then adds only the mount-specific rules — so mounting and operations canonicalize
through the same code, and the rule "every path is validated the same way" has no
exception.

## 5. The invariant, and how it is checked

The whole point, as in 031 §8, is that there is no second door. After the change,
**every** caller-supplied path is canonical before routing, and **every**
re-encoding of the scoping / metadata / meta-construction conventions lives in
`paths.py` or the one resolve gate. A CI grep enforces it:

```
# raw scoping convention, hand-built meta paths, hand-coded reserved detection,
# ad-hoc normalization — every hit must be inside paths.py or _resolve_path.
grep -nE 'f"/\{user_id\}|/__meta__/|startswith\("/\.vfs|\.lstrip\("/"\)|\.rstrip\("/"\)' \
  src/vfs/base2.py src/vfs/routing.py src/vfs/backends/database.py
```

As with 031, the check is about *where the convention is encoded*, not about banning
the substrings outright: a hit inside `paths.py` (the library) or inside
`resolve_path` / a single `scope_like_prefix` helper (§7, open) is sanctioned; a hit
anywhere else is a second door. The invariant is precisely: **every path is
canonicalized in `resolve_path`, and every `/{user_id}` / `/.vfs` / `/__meta__/`
encoding lives in `paths.py`.**

## 6. What the reference systems teach

Before fixing the gate's shape, the local reference checkouts (Linux, FreeBSD, Plan 9,
SQLite, fsspec, libfuse) were surveyed for how each separates the three concerns. The
survey grounds the decisions below — every `file:line` was read against the checkout.

| System | Lexical normalization | Structural validation | Authorization | Structure |
|---|---|---|---|---|
| **Plan 9** | `cleanname()` — pure, never validates (`plan9port/src/lib9/cleanname.c:9`) | delegated to servers; not in `cleanname` | `hasperm()` — pure, post-lookup (`src/lib9p/uid.c:12`) | 3 separate concerns |
| **Linux** | resolved *during* the walk by inode deref, no whole-string normpath (`fs/namei.c:2574`) | `lookup_noperm_common` — empty/dot-dotdot/charset (`:3086`) | `may_lookup` / `may_create_dentry` (`:1951`, `:3733`) | 3 separate fns, interleaved in one walk |
| **FreeBSD** | component walk (`sys/kern/vfs_lookup.c:1187`) | `NAME_MAX` check, distinct (`:1195`) | `mac_vnode_check_lookup` / `VOP_ACCESS` (`:1311`) | 3 distinct phases in one walk |
| **SQLite** | `unixFullPathname` (`src/os_unix.c:7023`) | fused into normalize (buffer checks, `:6955`) | `unixAccess` / OS `open()`, separate (`:6896`) | normalize+validate fused, auth separate |
| **fsspec** | `_strip_protocol` / `make_path_posix`, pure, **never raises** (`fsspec/spec.py:193`) | none — delegates rejection to backend | n/a (delegated to OS) | normalize-only, generic gate + per-backend override |

**Two patterns are near-universal:**

1. **Authorization is always a separate concern from name handling** — `hasperm`,
   `may_create_dentry`, `mac_vnode_check_create`, `unixAccess`. Not one system folds
   "may you write here" into "is this a clean, legal name."
2. **Normalization is a pure transform that never raises; validation is the
   rejecter.** fsspec states this as an explicit rule; Plan 9 enforces it by keeping
   `cleanname` validation-free.

**The kernels interleave; we don't — and shouldn't.** Linux and FreeBSD fold the
three concerns into one per-component walk *because they resolve against a live tree*
(symlinks, races, per-directory `MAY_EXEC`). VFS canonicalizes a path string and then
routes — there is no live walk — so our lineage is the **lexical / library** one:
Plan 9's `cleanname` (the ancestor of Go's `path.Clean`) and fsspec's pure
`_strip_protocol` / `make_path_posix`. Whole-string lexical canonicalization is the
correct model for us; we deliberately do **not** adopt the per-component walk.

**What every kernel has that we lacked** is the single door that *sequences* the
concerns so none is skipped — Linux's one walk, FreeBSD's one `lookup`. `resolve_path`
is that door: three pure functions, composed once, in a fixed order.

**Decisions the survey drove:**

- **D1 — keep the three pure functions separate; `resolve_path` composes them.**
  Confirmed by Plan 9 and fsspec: lexical normalization, structural validation, and
  authorization are distinct concerns. The split is not over-engineering — it is the
  universal shape. The chokepoint is the *composition*, not a merge.
- **D2 — rename `validate_mutation_path` → `check_namespace_writable`.** It is an
  authorization gate (a `may_create` analogue), not structural validation; the name
  should say so, and it parallels `permissions.check_writable`. The return shape stays
  `(ok, reason)`.
- **D3 — normalize exactly once, in a fixed order.** Cheap raw rejects (null bytes,
  control chars, total length) run on the *raw* input first — so a hostile string is
  rejected before `normpath` can mangle it (the FreeBSD order: validate, then
  authorize). Then normalize once; the segment-length check runs against the canonical
  form. `validate_path` gains an optional `normalized=` parameter so the gate passes
  the canonical form it already computed, eliminating the double-normalize where
  `validate_path` previously re-normalized after the gate had.

## 7. Open questions

1. **LIKE patterns are not paths.** The scattered `f"/{user_id}/%"` are SQL `LIKE`
   *prefix patterns*, not stored paths — a normalized path and a `LIKE` pattern are
   different artifacts (the pattern carries `%` and escaping concerns). The gate
   needs a companion `scope_like_prefix(user_id, prefix="")` helper in `paths.py` so
   these route through the library too, rather than being declared out of scope. Lean
   toward adding it.
2. **Does the router scope at all, ever?** This design keeps scoping entirely in the
   backend (§3). An alternative is a router-level scope step for storage mounts only.
   Rejected here because it couples the routing layer to one tenant layout, but worth
   recording as the road not taken.
3. **`routing.py` normalization.** Routing's own `lstrip`/`rstrip` predates this gate.
   Folding it onto `normalize_path` is in scope, but routing operates on *mount
   patterns* (which may legitimately differ from entry paths); confirm the semantics
   match before collapsing them.
4. **Interaction with 031.** The entry gate (`_mint_entries`) assumes the paths it
   receives are already canonical. Once `_resolve_path` lands at the public boundary,
   `_mint_entries` can drop any defensive re-normalization and treat its input paths
   as canonical — a small simplification to fold in when both land.

## 8. Rollout

Each step is independently testable.

- **Step 1 — `resolve_path` + `ResolvedPath` in `paths.py`** (landed). The gate that
  composes the pure functions; no caller wired yet.
- **Step 2 — the refactor the survey drove (§6 D2/D3):** rename
  `validate_mutation_path` → `check_namespace_writable`; give `validate_path` the
  optional `normalized=` parameter and have `resolve_path` normalize exactly once;
  add the "never raises" contract to `normalize_path` and `validate_path`. Pure
  refactor; update the existing `paths` callers and tests.
- **Step 3 — wire the router's public methods.** Call `resolve_path` at the top of
  `_route_single` for single-path ops and in `_group_candidates_by_terminal` for
  candidate paths; on error return `self._error(reason)`. Read-family ops pass
  `mutation=False`; write-family `mutation=True`. Test: invalid paths now rejected at
  the boundary; valid paths unchanged.
- **Step 4 — fold the mount gate onto `resolve_path`** (`_normalize_mount_path` calls
  it for validate+normalize, keeps the normalized-equality and mount-specific rules).
  Test: existing mount suite.
- **Step 5 — add `scope_like_prefix` to `paths.py`** (open question 1) and route the
  `f"/{user_id}/%"` / `_scope_filter_prefix` sites through it. Test: per-user
  filtering across read/ls/grep.
- **Step 6 — close the detection/assembly second doors in `database.py`**: replace
  `startswith("/.vfs")` with `is_meta_root_path`, and the hand-built
  `f"{meta_root(...)}/__meta__/chunks"` with the `chunk_path`/meta constructors.
- **Step 7 — fold `routing.py` onto `normalize_path`** (open question 3), then add the
  litmus grep (§5) to CI.

Steps 1–4 are the "mounting and initial public methods" slice and ship first; 5–7
close the backend second doors and can land incrementally behind the same invariant.
