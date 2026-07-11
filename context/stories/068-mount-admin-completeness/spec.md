# 068 — Mount administration completeness: introspection, remount, op masks, move, automount

- **Status:** implemented 2026-07-11 — features 1–3 landed
  (`mounts()`, `remount`, `deny_ops`) with all acceptance criteria
  pinned in `tests/test_base_mount_admin.py`; features 4–5 stay
  demand-gated, to be split into their own stories if picked up.
- **Date:** 2026-07-09 (seed); revised 2026-07-10
- **Owner:** Clay Gendron
- **Kind:** feature (mount administration — control-plane surface on the
  router; no dispatched-verb changes)
- **Depends on:** 056 storage mounts (one table, one funnel), 057 result
  envelope (classified errors, `MountError`)
- **Interactions:** 070 Principal renames `user_id` on every dispatched
  verb and storage method; this surface carries no identity parameter, so
  the rename brushes it only through `add_mount`/`remove_mount`'s internal
  `mkdir`/`delete` calls — 068-before-or-after-070 is the sequencing call
  STATUS.md leaves open. 054: when `serve()` lands, `remount` joins the
  locked control-plane set and is never a wire tool; `mounts()` may
  surface remotely only as a read-only topology view.
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
    masks are visible, intersection along the chain, **no dark mounts**)
    carry over; its mechanism does not.
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
   *replayable* bind/mount commands. Our table lives only in `_bindings`
   (plus its derived `_sorted_mount_paths` index) — an MCP client, ops
   tool, or test cannot ask "what is mounted where, under what policy."
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
class PermissionsPayload(TypedDict):
    default: Permission          # "read" | "read_write"
    overrides: list[list[str]]   # [[prefix, perm], ...], normalized order

class MountInfo(NamedTuple):
    path: str                    # bind path, router coordinates
    storage_name: str            # storage.name (protocol-required, never None)
    storage_type: str            # type(storage).__name__
    description: str             # storage.description (live attribute read; protocol-required, never None)
    caps: tuple[str, ...]        # effective caps, sorted — post-mask (feature 3)
    deny_ops: tuple[str, ...]    # the stored mask, sorted; () = no mask (feature 3)
    permissions: PermissionsPayload | None  # serialized local map; None = none stored
    no_overlay: bool
    owned: bool

def mounts(self) -> tuple[MountInfo, ...]: ...
```

- **Values out, JSON-serializable, no storage I/O** — table facts and
  bind-time snapshots only. `description` is the one live read (attribute
  access, not a call) — a read **new with this story**: nothing in the
  router reads `storage.description` today.
- **Every field is a JSON fixed point** — str, bool, None, or dict/list/
  tuple of these. Hence `caps` crosses as a sorted `tuple[str, ...]`, not
  the `frozenset[str]` stored in `MountMeta` (a frozenset does not survive
  `json.dumps`).
- **Replayable, per `ns(1)`:** the rows carry enough to reconstruct the
  namespace given the storages — the property that makes Plan 9's version
  useful rather than merely informative. Mounter-imposed policy is
  therefore echoed verbatim on the row — `permissions`, `deny_ops`,
  `no_overlay`, `owned` — never left to be derived: post-mask `caps`
  cannot recover a mask (deriving `declared − caps` re-calls
  `capabilities()` at replay time and is wrong whenever the declared set
  drifted after bind, and inert masks of undeclared ops vanish entirely).
- Ordered by bind path; a closed filesystem returns `()`.
- Synchronous: it reads one dict snapshot; taking the mount lock would
  buy nothing (the table can change the instant the lock drops anyway).

**Decided — `permissions` is the fully serialized map, not a summary**
(resolved 2026-07-10; full rationale and dissent in research.md):

- **Replayability forces this.** A summary string carries a rule *count*;
  the prefixes and per-prefix permissions are unrecoverable. The dict
  feeds `PermissionMap(default=..., overrides=...)` verbatim; emitted in
  the map's normalized order, it is deterministic and round-trips exactly.
  One typing note: the round-trip is verbatim at *runtime*
  (`__post_init__` normalizes arbitrary pair iterables), but the payload's
  `overrides: list[list[str]]` is not statically assignable to
  `PermissionMap`'s declared `tuple[tuple[str, Permission], ...]`
  (permissions.py:169), so typed replay code converts the pairs
  explicitly — see the replay criterion's `payload_to_map` helper — rather
  than splatting `PermissionMap(**payload)`; no live-code annotation
  change is made.
- `None` means the entry stores no local map — possible only on child
  binds where `permissions` was omitted. **The root row is never `None`:**
  the constructor always installs a map (`coerce_permissions`, default
  `"read_write"`). Replaying `None` as an omitted argument reproduces the
  table exactly.
- **No summary string ships, alone or alongside the map.** Prose in a
  machine-readable table becomes regex-parsed wire grammar (057 D14); a
  derived digest beside its source is the disagreement-by-redundancy 057
  D1 exists to prevent. The human one-liner is a renderer's job — as
  `ns(1)` is a renderer over `/proc/pid/ns`.

**Acceptance criteria**

- `mounts()` on a fresh router returns one row: the root entry, caps
  equal to the storage's declared set (sorted), `permissions` the
  serialized constructor map — never `None`.
- After `add_mount`, the new row appears with its bind path, meta flags,
  and snapshot caps; after `remove_mount`/`unbind`, it is gone; after
  `close()`, `mounts()` returns `()`.
- `json.dumps(row._asdict())` succeeds for every row and `json.loads`
  reproduces the values (tuples reading back as lists);
  `row.permissions` survives the round-trip unchanged.
- Replay round-trip: bind storages under maps carrying overrides (the
  `read_only(write=[...])` / `read_write(read=[...])` factories),
  including at least one entry bound with a `deny_ops` mask, then rebuild
  a second router from the rows. The root row feeds the constructor —
  `VirtualFileSystem(storage=..., permissions=payload_to_map(row.permissions),
  deny_ops=row.deny_ops, no_overlay=row.no_overlay)` — since `bind`
  rejects `/` (`_normalize_mount_path`); every other row replays via
  `bind(storage_by_name[row.storage_name], row.path,
  permissions=payload_to_map(row.permissions), deny_ops=row.deny_ops,
  no_overlay=row.no_overlay, owned=row.owned)` — omitting `permissions`
  where the row says `None`. `payload_to_map` is a small typed tests-side
  helper (`PermissionMap(default=payload["default"],
  overrides=tuple((p, validate_permission(perm)) for p, perm in
  payload["overrides"]))`) — needed because the payload's
  `list[list[str]]` is runtime-valid for `PermissionMap` but not
  statically assignable to its declared overrides type, and the tree
  stays at ty zero. The same friction applies to `deny_ops`: the row's
  `tuple[str, ...]` is not statically assignable to the intakes'
  `Iterable[Op]`, so typed replay widens it explicitly (the tests'
  `replay_ops` cast) — stored masks are replay-safe at runtime either
  way. The second router's `mounts()` equals the first's — post-mask
  `caps` and `deny_ops` included. *(Amended post-implementation:)* rows
  carrying `no_overlay=True` replay **seal-last** — bind unsealed, then
  `remount(row.path, no_overlay=True)` — because a sealed entry refuses
  the child binds beneath it, and a subtree grandfathered by feature 2's
  `remount(no_overlay=True)` is otherwise unreachable (pinned in tests);
  replay keyed by `storage_name` assumes the mounter keeps storage names
  unique, which the table itself never enforces.
- A child bind with `permissions` omitted reports `permissions=None`.
- No storage I/O: no op is dispatched (`RecorderStorage.calls` stays
  empty) and `capabilities()` is not re-called after bind — `.calls`
  records op dispatches only, so pin the latter with a small subclass
  spying `capabilities()` invocations.
- The `description` live read is real: mutating `storage.description`
  after bind is reflected in the next `mounts()` row — an attribute read,
  not a call, so the no-I/O criterion above is unaffected.

## Feature 2 — `remount(path, ...)`: entry policy changes in place

```python
async def remount(
    self,
    path: str,
    *,
    permissions: Permission | PermissionMap | None = None,
    deny_ops: Iterable[Op] | None = None,   # feature 3
    no_overlay: bool | None = None,
    refresh_caps: bool = False,
) -> None: ...
```

- `None` means "leave unchanged" — `deny_ops=()` (clear the mask) is
  distinct from `deny_ops=None` (keep it). Passing no changes at all is a
  no-op, not an error.
- **Atomic under the mount lock:** the `Binding` is replaced with one
  carrying a new `MountMeta`; no moment exists where the path is unbound.
  No storage I/O, no site probe. The dict key is unchanged, so
  `_sorted_mount_paths` needs no rebuild.
- `refresh_caps=True` re-snapshots `storage.capabilities()` — the one
  storage call, taken *outside* the lock like the bind probe (056 D11),
  committed under it: the remedy for a reconnected wire backend whose
  tool set changed.
- Applies to the root identity entry too (`remount("/")` is how you
  tighten the whole namespace) — root is an ordinary entry. Note:
  `remount` cannot reuse `_normalize_mount_path`, which rejects root by
  design; it needs its own normalization admitting `/`.
- Unknown path raises `ValueError`, as `unbind` does — `remount` performs
  no storage mutation, so `bind`/`unbind`'s plain-`ValueError` temperament
  applies; typed `MountError` (057 D15) stays reserved for
  `add_mount`/`remove_mount`'s storage-step failures.

Loosening is permitted, as on Linux: composition already bounds it — a
parent layer's map still gates every path beneath (most restrictive wins,
`_permission_layers`), so `remount` can never grant more than the chain
above allows.

**Decided — `no_overlay=True` over existing deeper bindings commits, with
future-only effect** (resolved 2026-07-10; rationale and dissent in
research.md): existing children stay bound and dispatching; only
subsequent binds beneath the entry are refused — by existing machinery,
with its existing messages: non-root sealed entries refuse with "does not
allow binds beneath it"; the sealed root refuses via `bind`'s separate
root branch with "`<class>` does not allow child mounts". Not a
softening: `no_overlay` is a bind-time gate (its only reads are `bind`'s
under-lock commit checks), so there is no existing state to validate, and
Linux agrees on both halves (no content/busy check on `noexec`-family
remounts; `MNT_LOCKED` absorbs existing children, never rejects).
Rejection would make the flagship move — `remount("/", no_overlay=True)`
on any namespace with children — unreachable with no remediation, since
children beneath a sealed parent cannot be re-bound. Two consequences are
contract, and the docstring and `MountInfo` field docs must say so:
`no_overlay=True` means "no *new* binds beneath," not "nothing beneath" —
a sealed entry may show child rows in `mounts()` — and because `unbind`
never consults the flag, the sealed subtree is a one-way ratchet: it can
shrink but never grow. A third consequence for feature 1: such a table
replays seal-last (see the amended replay criterion) — passing the
sealed row's flag at bind/construction time would refuse the
grandfathered children.

**Acceptance criteria**

- Remounting `permissions="read"` makes a previously succeeding `write`
  classify as a permission denial, with no unbound window. `remount` does
  no storage I/O and never awaits while the entry is absent, so there is
  no seam for a suspending race double; pin atomicity by contrast: the
  unbind+bind sequence has a schedulable moment between the two awaits
  where a read resolves to the parent entry (and sees the orphan site
  directory), while a read interleaved with `remount` via
  `asyncio.gather` resolves at the bound path under the old or new meta —
  never to the parent entry.
- `refresh_caps=True` picks up a capability gained after bind
  (`RecorderStorage`'s `caps` knob is read live, so the test widens it
  post-bind); `refresh_caps=False` (default) leaves the snapshot alone.
- Field-by-field: unchanged arguments preserve the prior meta exactly.
- `remount` on an unbound path raises `ValueError`; on a closed table
  raises.
- `remount(p, no_overlay=True)` with an existing deeper binding beneath
  `p` succeeds; the child still answers dispatched ops; a subsequent
  `bind` beneath `p` raises the existing "does not allow binds beneath
  it" message. The ratchet is pinned: `unbind` of the grandfathered child
  succeeds; re-`bind` at the vacated path is refused.
- `remount("/", no_overlay=True)` on a table with child mounts succeeds;
  subsequent child binds anywhere raise; `mounts()` shows the root row
  `no_overlay=True` with child rows still beneath it.

## Feature 3 — `deny_ops`: the noexec family (044 re-anchored)

```python
async def bind(self, storage, path, *, deny_ops: Iterable[Op] = (), ...) -> None
async def add_mount(self, storage, path=None, *, deny_ops: Iterable[Op] = (), ...) -> None
# and on the constructor for the root entry, and on remount() (feature 2)
```

One mechanism buys the whole mount-flag family:

- **Effective caps are an intersection** (044's signed-off rule):
  `meta.caps = frozenset(storage.capabilities()) - frozenset(deny_ops)`.
  `_gate_entry`, `capabilities()`, fan-out skip classification, and tree
  descents all read `meta.caps`, so those seams pick the mask up
  unchanged. Two seams do not, and both are accounted for: bind-site
  probes reach storage without the entry gate — moot, since probes issue
  only `stat`/`ls` and the mask excludes read-family ops (below) — and
  `add_mount` creates its site through the public, gated `mkdir`, so a
  parent-entry mask containing `mkdir` refuses new mount sites beneath it
  (`unsupported` → `MountError`): the mask doing its job, pinned in tests.
- **Both the mask and the unmasked snapshot are stored.** `MountMeta`
  gains `deny_ops` (the validated mask) and keeps the bind-time
  capability snapshot *unmasked* alongside it; `meta.caps` remains the
  post-mask intersection the gates read (whether stored or derived is a
  plan.md detail). Post-mask caps alone cannot implement `remount`:
  clearing or replacing a mask must restore previously masked ops with
  no storage I/O, and `refresh_caps=True` with `deny_ops=None` must
  re-subtract the *existing* mask from the fresh snapshot — both need
  the two stored facts. `MountInfo.caps` stays the post-mask projection;
  the row's `deny_ops` echoes the stored mask.
- A masked op classifies exactly as an incapable entry does today:
  `unsupported` at the gate, naming the bind path. No new error kind —
  whether "does not answer" is the storage's nature or the mounter's
  policy is deliberately not distinguished on the data plane.
- **Masks are visible** (044's visibility decision): `mounts()` reports
  post-mask caps *and* echoes the stored mask as the row's `deny_ops`
  (sorted tuple); `capabilities()` unions post-mask sets. What the
  namespace advertises is what it answers.
- `remount(..., deny_ops=...)` operates over the two stored facts:
  `deny_ops=X` replaces the stored mask and recomputes effective caps
  from the stored unmasked snapshot (no storage I/O); `deny_ops=()`
  clears the mask, restoring the snapshot exactly; `deny_ops=None` keeps
  the stored mask. `refresh_caps=True` re-snapshots the declared set,
  then subtracts whichever mask applies (kept, replaced, or cleared).
- Denying an op the storage never declared is legal and inert on caps —
  fstab carries `noexec` for filesystems with nothing executable. The
  inert mask is still stored and echoed in the row's `deny_ops`, so it
  survives replay and starts biting if `refresh_caps` later picks the op
  up.
- **The mask is principal-blind.** Per 070's resolved `system()` fork,
  structural configuration binds every principal, system included — no
  identity bypasses a mask.

This supersedes 044's mechanism (a `Rights` mask checked in the terminal
gate) while keeping its decisions. 039's execute-permission tier is *not*
revived: `run` stays outside the permission-map vocabulary; `deny_ops` is
the execution lever. Two deliberate supersessions to record when 039/044
statuses are trued up: denied execution classifies `unsupported` (040's
capability slot), not their `permission_denied`; and 039's per-path
execute carve-outs stay unexpressed — `deny_ops` is per-entry.

**Decided — the mask is restricted to `MUTATING_OPS | EXEC_OPS`;
read-family ops cannot be masked** (resolved 2026-07-10; rationale and
dissent in research.md). A `deny_ops` containing any `READ_OPS` member
raises `ValueError` at every intake — constructor, `bind`, `add_mount`,
`remount` — before any table change. This *is* 044 carried over, not
narrowed: its signed-off no-dark-mounts decision ("every mask includes
`read`, by construction") and its enabled use case — "discoverable, not
writable, not runnable" — are exactly the restricted mask. The reference
systems are unanimous: no Unix mount flag has ever masked the read family
(a `noexec` binary still reads and copies). Read denial lives in the
permission plane, where a principal is in scope; mount policy is
principal-blind, and so is `deny_ops`.

Restriction buys two invariants an unrestricted mask would destroy:
**advertised means answered, fully** — post-mask caps only ever shed
mutating/exec ops, so every read-family op an entry advertises genuinely
answers and `ls` never returns rows no verb can open — and **masks never
touch fan-out**: every fan-out verb is read-family, so a mask can never
cause a fan-out skip.

If "names public, content gated" ever becomes real, it belongs where the
reference systems put it: storage-side (a backend declaring `ls`/`stat`
but not `read` is legal today) or in the permission vocabulary. Loosening
this mask later deletes a `ValueError` no client can have depended on;
tightening after shipping breaks live namespaces. The check is closed
over the known `READ_OPS` names — if `deny_ops` is ever widened to raw
strings for peer ops, unknown names stay maskable.

**Acceptance criteria**

- `bind(storage, "/tools", deny_ops={"run"})` on a run-capable storage
  (`RunnerStorage`): `run("/tools/x")` classifies `unsupported` naming the
  bind path; `read("/tools/x")` still answers; `capabilities()` excludes
  `run` if no other entry declares it.
- Masks never alter fan-out: unscoped fan-out over a `deny_ops={"run"}`
  entry returns results identical to the unmasked entry, with no skip
  minted on the mask's account.
- `deny_ops` containing any read-family op raises `ValueError` at each of
  the four intakes — constructor, `bind`, `add_mount`, `remount` — and the
  table and the entry's meta are unchanged after the raise.
- A `remount` that combines a read-family `deny_ops` with
  `refresh_caps=True` raises without re-snapshotting: the prior caps
  snapshot is preserved exactly.
- `deny_ops={"mkdir"}` on a parent entry: `add_mount` beneath it raises
  `MountError` (the composed `mkdir` classifies `unsupported`), while a
  direct `bind` at an existing empty directory beneath it still succeeds
  (the probe is ungated).
- `mounts()` shows post-mask caps and the stored mask in `deny_ops`;
  masking an undeclared op is legal — caps unchanged, mask still echoed
  in the row; constructor-level `deny_ops` masks the root identity entry.
- Mask replace/clear round-trip with no storage I/O: after
  `bind(..., deny_ops={"edit"})`, `remount(p, deny_ops={"run"})` restores
  `edit` to effective caps and masks `run` from the bind-time snapshot;
  `remount(p, deny_ops=())` restores the full unmasked snapshot — neither
  call re-invokes `capabilities()`.

## Feature 4 — `move_mount(src, dest)` (stretch; may split out)

`mount --move` for the table: relocate a binding and its stored
mount-point directory in one administrative step. Unlike Linux — where a
mount point is just a dirent — our mount-point directory is a stored row
in the parent entry's storage, so the move is two-plane:

- Table surgery is atomic under the lock (and, unlike `remount`, changes
  a key — it must rebuild `_sorted_mount_paths`); the storage steps
  (rmdir old site, mkdir new site) sequence around it exactly as
  `remove_mount` and `add_mount` do today, with the same
  loud-and-recoverable failure states (a failed step leaves plain empty
  directories, never a dangling binding).
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
