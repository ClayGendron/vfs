# 068 — Mount administration completeness: introspection, remount, op masks, move, automount

- **Status:** seed — drafted from a mount-concepts survey of Linux, Plan 9,
  and classic Unix against `base.py`'s admin section (design discussion,
  2026-07-09). `[NEEDS CLARIFICATION]` markers are unresolved design forks,
  not omissions.
- **Date:** 2026-07-09
- **Owner:** Clay Gendron
- **Kind:** feature (mount administration — control-plane surface on the
  router; no dispatched-verb changes)
- **Depends on:** 056 storage mounts (one table, one funnel), 057 result
  envelope (classified errors, `MountError`)
- **Prior art:**
  - `017-topology-resource-and-mount-ctl` (May draft, pre-056): its
    `list_mounts()` half is **superseded by feature 1 here**; its synthetic
    `/.mounts/` file tree and ctl-file write surface stay parked — the
    admin surface is deliberately *not* part of the namespace today
    (`base.py` module docstring: "no dispatched verb can mutate a mount
    table"), and this story does not reopen that.
  - `044-mount-rights-mask` (design signed off 2026-07-03, anchored to
    039 `Rights` sets and 040's `_gate_terminal` — both pre-056 shapes):
    **feature 3 here is 044 re-anchored** on `MountMeta.caps` and
    `_gate_entry`. 044's signed-off decisions (mounter imposes policy,
    masks are visible, intersection along the chain) carry over; its
    mechanism does not.
  - `018-bind-aliases`, `019-union-mounts-and-shadow-resolution` (May
    drafts): stay rejected — see Non-goals.

## Intent

The admin section (`bind`/`unbind`/`add_mount`/`remove_mount`/`close`)
already mirrors most of the classic surface: `mount(2)`/`umount(2)`, the
EBUSY busy-guard, `umount -l`'s no-I/O table surgery, locked mounts
(`no_overlay`), loop-device-style lifecycle (`owned`) — and the graft-tree
rule is *stricter* than Unix, which mounts over non-empty directories and
shadows their contents.

Four gaps remain where every reference system has an answer and the router
has none, plus one pattern that must be pinned as a storage-side concern
before someone designs it into the router:

1. **The table is unreadable.** Unix has exposed its mount table since v1
   (`mount` with no arguments; `/etc/mtab` → `/proc/mounts` →
   `/proc/self/mountinfo`); Plan 9's `ns(1)` prints the namespace as
   *replayable* bind/mount commands. Our table lives only in `_bindings` —
   an MCP client, ops tool, or test cannot ask "what is mounted where,
   under what policy."
2. **Entry policy is frozen at bind.** `mount -o remount,ro` is ancient
   and constantly used; our only path to tightening a live mount is
   `unbind` + `bind` — not atomic (requests in the gap resolve to the
   parent entry and see the orphan directory) and it re-runs the site
   probe pointlessly. The capability snapshot is likewise frozen: a wire
   backend that reconnects with more tools has no way to refresh its
   entry.
3. **The mounter cannot narrow ops.** `noexec`/`nosuid`/`nodev` exist
   because *where* a filesystem is mounted deserves narrower rights than
   what it supports. Read-only is already expressible
   (`Permission = "read" | "read_write"`), but `run` is `EXEC_OPS` —
   outside the write gate entirely — so "mount this tool-bearing MCP
   catalog, but noexec" has no expression. This is 044's problem
   statement, still true after 056.
4. **Relocating a binding is three non-atomic steps.** Linux grew
   `move_mount(2)` / `mount --move` for exactly this; we force
   unbind → move directory → bind, with three chances to fail halfway.
5. **Automount wants a home.** autofs mounts on first access and expires
   idle mounts; the MCP analogue (dial a wire backend on first dispatch,
   drop the session when idle) is real — but the right seam is a lazy
   `StorageBackend` adapter, not the mount table. Pin that now.

Features 1–3 are the deliverable core; 4 and 5 are demand-gated and may be
split out at plan time.

## Feature 1 — `mounts()`: the table is readable

A read-only accessor on `VirtualFileSystem` returning one row per binding,
root identity entry included (it is an ordinary entry — presenting it
otherwise would misreport the table):

```python
class MountInfo(NamedTuple):
    path: str                    # bind path, router coordinates
    storage_name: str | None     # storage.name
    storage_type: str            # type(storage).__name__
    description: str | None      # storage.description (live, not snapshot)
    caps: frozenset[str]         # effective caps — post-mask (feature 3)
    permissions: str | None      # summary of the entry's map, None if no local rules
    no_overlay: bool
    owned: bool

def mounts(self) -> tuple[MountInfo, ...]: ...
```

- **Values out, JSON-serializable, no storage I/O** — table facts and
  bind-time snapshots only. `description` is the one live read
  (attribute access, not a call), matching `_decorate`'s behavior.
- **Replayable, per `ns(1)`:** the rows carry enough to reconstruct the
  namespace (`bind(storage_by_name, path, permissions=..., ...)`) given
  the storages. This is the property that makes Plan 9's version useful
  rather than merely informative.
- Ordered by bind path; a closed filesystem returns `()`.
- Synchronous: it reads one dict snapshot; taking the mount lock would
  buy nothing (the table can change the instant the lock drops anyway).

`[NEEDS CLARIFICATION]` — the `permissions` summary format: the full
`PermissionMap` is a rule list; a wire-friendly summary could be the
default plus rule count (`"read_write (3 rules)"`), or the serialized map.
Decide against what MCP clients actually need to display.

**Acceptance criteria**

- `mounts()` on a fresh router returns one row: the root entry, its caps
  equal to the storage's declared set, `permissions` reflecting the
  constructor argument.
- After `add_mount`, the new row appears with its bind path, meta flags,
  and snapshot caps; after `remove_mount`/`unbind`, it is gone.
- After `close()`, `mounts()` returns `()`.
- Every field of every row round-trips through `json.dumps`.
- No method on any bound storage is called (pinned with a double that
  counts calls).

## Feature 2 — `remount(path, ...)`: entry policy changes in place

```python
async def remount(
    self,
    path: str,
    *,
    permissions: Permission | PermissionMap | None = None,
    no_overlay: bool | None = None,
    refresh_caps: bool = False,
) -> None: ...
```

- `None` means "leave unchanged" — `remount(p, no_overlay=True)` touches
  nothing else. Passing no changes at all is a no-op, not an error.
- **Atomic under the mount lock:** the `Binding` is replaced with one
  carrying the new `MountMeta`; no moment exists where the path is
  unbound. No storage I/O, no site probe.
- `refresh_caps=True` re-snapshots `storage.capabilities()` — the one
  storage call, taken *outside* the lock like the bind probe, committed
  under it. This is the remedy for a reconnected wire backend whose tool
  set changed.
- Applies to the root identity entry too (`remount("/")` is how you
  tighten the whole namespace) — root is an ordinary entry.
- Unknown path raises `ValueError`, matching `unbind`.

Loosening is permitted, as on Linux: composition already bounds it — a
parent layer's map still gates every path beneath (most restrictive wins,
`_permission_layers`), so `remount` can never grant more than the chain
above allows.

`[NEEDS CLARIFICATION]` — should `no_overlay=True` be rejected when
deeper bindings already exist beneath the entry, or take effect for
*future* binds only? (Linux's locked-mount semantics suggest
future-only; rejecting is the stricter graft-tree temperament.)

**Acceptance criteria**

- Remounting `permissions="read"` makes a previously succeeding `write`
  classify as a permission denial, with no unbound window (a concurrent
  read during remount never resolves to the parent entry).
- `refresh_caps=True` picks up a capability the double added after bind;
  `refresh_caps=False` (default) leaves the snapshot untouched.
- Field-by-field: unchanged arguments preserve the prior meta exactly.
- `remount` on an unbound path raises; on a closed table raises.

## Feature 3 — `deny_ops`: the noexec family (044 re-anchored)

```python
async def bind(self, storage, path, *, deny_ops: Iterable[Op] = (), ...) -> None
async def add_mount(self, storage, path=None, *, deny_ops: Iterable[Op] = (), ...) -> None
# and on the constructor for the root entry, and on remount()
```

One mechanism buys the whole mount-flag family:

- **Effective caps are an intersection** (044's signed-off rule):
  `meta.caps = frozenset(storage.capabilities()) - frozenset(deny_ops)`.
  Nothing else changes — `_gate_entry`, `capabilities()`, fan-out
  skip/`unsupported` classification, and tree descents all already read
  `meta.caps`, so the mask propagates through every existing seam for
  free.
- A masked op classifies exactly as an incapable entry does today:
  `unsupported` at the gate, info-severity skip in unscoped fan-outs.
  No new error kind — the caller-visible fact is "this entry does not
  answer that op here," and whether that is the storage's nature or the
  mounter's policy is deliberately not distinguished on the data plane.
- **Masks are visible** (044's visibility decision): `mounts()` reports
  post-mask caps; `capabilities()` unions post-mask sets. What the
  namespace advertises is what it answers.
- `remount(..., deny_ops=...)` replaces the mask (combined with
  `refresh_caps` it recomputes from a fresh snapshot).
- Denying an op the storage never declared is legal and inert —
  fstab carries `noexec` for filesystems with nothing executable.

This supersedes 044's mechanism (a `Rights` mask checked in the terminal
gate) while keeping its decisions. 039's execute-permission tier is *not*
revived: `run` stays outside the permission-map vocabulary; `deny_ops`
is the execution lever.

`[NEEDS CLARIFICATION]` — 044 also wanted the mask to cover *reads*
("discoverable, not readable" for catalog mounts). `deny_ops={"read"}`
expresses that structurally, but a mount that answers `ls` and not
`read` is an unusual namespace citizen — decide whether to allow masking
read-family ops or restrict the mask to `MUTATING_OPS | EXEC_OPS`.

**Acceptance criteria**

- `bind(storage, "/tools", deny_ops={"run"})` on a run-capable storage:
  `run("/tools/x")` classifies `unsupported` naming the bind path;
  `read("/tools/x")` still answers; `capabilities()` excludes `run` if
  no other entry declares it.
- Unscoped fan-out over a masked entry records the info-severity skip,
  identical to a natively incapable entry.
- `mounts()` shows post-mask caps.
- Masking an undeclared op is a no-op, not an error.
- Constructor-level `deny_ops` masks the root identity entry.

## Feature 4 — `move_mount(src, dest)` (stretch; may split out)

`mount --move` for the table: relocate a binding and its stored
mount-point directory in one administrative step. Unlike Linux — where a
mount point is just a dirent — our mount-point directory is a stored row
in the parent entry's storage, so the move is two-plane:

- Table surgery is atomic under the lock; the storage steps (rmdir old
  site, mkdir new site) sequence around it exactly as `remove_mount` and
  `add_mount` do today, with the same loud-and-recoverable failure
  states (a failed step leaves plain empty directories, never a dangling
  binding).
- Old and new site in different entries is legal — the *binding* moves;
  no stored data crosses a storage boundary, so this is not EXDEV.
- Same rejection table as `bind` at the destination (occupied site,
  beneath `no_overlay`, above a deeper binding) and as `unbind` at the
  source (deeper bindings beneath it).

Demand-gated: defer unless namespace reshaping shows up as a real
workflow. The three-step manual sequence remains correct in the interim.

## Feature 5 — Automount is a storage adapter (design note + reference impl)

Pinned decision: **the router gets no automount machinery.** The autofs
analogue is a `LazyStorage` adapter in `storage/backends/` that wraps a
connect callable, dials on first dispatched op, and surfaces dial
failures as `TransportError` (which the funnel already classifies
`backend_unavailable`). Idle expiry, if wanted, is the adapter closing
its own session — the binding and the namespace never change.

The one genuine wrinkle is bind time: `bind` snapshots
`storage.capabilities()`, but the lazy adapter has not dialed yet. The
adapter therefore takes its declared caps as configuration (the autofs
map file move — the map declares, the mount proves later), and a
post-dial mismatch is an over-claim classifying `unsupported` at
dispatch, exactly like any backend whose declaration over-claims.
`remount(refresh_caps=True)` (feature 2) trues it up after first dial.

Deliverable: the adapter with tests, plus a short section in the storage
protocol docs naming the pattern so it is findable.

## Non-goals — considered against the reference systems, staying rejected

- **Bind-mount aliasing / subtree binds** (Plan 9 `bind`, Linux
  `--bind`; story 018). The table keeps "one object, one path"
  (`base.py`'s aliasing rejection). The sanctioned route is composition:
  an exportfs-style adapter presenting a subtree of a router as a
  `StorageBackend`, bound elsewhere — aliasing without the table ever
  holding one object twice. 018 stays parked; if aliasing returns, it
  returns as that adapter.
- **Union directories / overlays** (Plan 9 `MBEFORE`/`MAFTER`/`MCREATE`,
  overlayfs; story 019). Contradicts the full-shadow rule
  (`_shadow_filter`); Plan 9 needed unions for its search path, a
  pressure we don't have. 019 stays parked.
- **Mount stacking at one path** (Linux mount-over-mount). "Already
  bound" stays a rejection; stacking buys little without unions.
- **Propagation groups / per-process namespaces** (shared/slave/private,
  `CLONE_NEWNS`). Multiple views are multiple routers over shared
  storages — one `VirtualFileSystem` = one namespace is the cleaner
  statement.
- **`pivot_root` / rebinding `/`.** The root identity entry is fixed at
  construction; a container-runtime need, not an MCP one.
- **A writable ctl surface inside the namespace** (017's second half).
  The admin surface stays control-plane-only; no dispatched verb mutates
  the table.

## Order of work

1 (`mounts()`) → 2 (`remount`) → 3 (`deny_ops`); each lands
independently green. 4 and 5 are demand-gated and should be pulled into
their own stories if picked up.
