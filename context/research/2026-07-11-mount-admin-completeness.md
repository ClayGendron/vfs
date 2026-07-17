# 068 — Research record: mount administration completeness

- **Date:** 2026-07-10
- **Purpose:** the evidence behind spec.md's revision from seed to draft —
  reference-system findings (Linux/Unix, Plan 9), consumer findings (MCP
  wire posture), the three fork resolutions with decision/rationale/dissent,
  and the code-grounding drift audit whose corrections are now folded into
  the spec. This file is why the spec says what it says.

## 1. Reference systems — Linux/Unix

### remount (`MS_REMOUNT`, `mount_setattr(2)`)

Two planes: plain `MS_REMOUNT` reconfigures the **superblock** (fs-wide
options) and must target the filesystem root [local:
linux/fs/namespace.c:3363-3380]; `MS_REMOUNT|MS_BIND` changes only the
**per-mount (vfsmount) flags** (`ro,nosuid,nodev,noexec,atime*`), touching
no superblock state [local: namespace.c:3326-3361]. The path is never
unmounted — remount edits flags in place under `lock_mount_hash()`; no
window exists where lookups miss the mount. Read→write transitions of `ro`
are guarded by a writer count and return **EBUSY with active writers**
[local: namespace.c:589-692]; toggling `noexec`/`nosuid`/`nodev` runs no
busy check at all — those flags are consulted per subsequent operation.
Children beneath the remounted mount are neither consulted nor rejected;
per-mount flags do not propagate down. `mount_setattr(2)` added
`AT_RECURSIVE`: two-phase validate-then-commit, all-or-nothing across a
subtree under one lock [local: namespace.c:4846-4974] — the kernel's
precedent for atomic tree-wide policy change.

### Locked mounts (the `no_overlay` analogue)

Locks are stamped when a tree is copied into a less-privileged namespace
(`lock_mnt_tree`, `MNT_LOCKED`) [local: namespace.c:2412-2437]. Refused on
a locked mount: `umount(2)` including lazy detach → EINVAL [local:
namespace.c:1941]; being a `move_mount` source → EINVAL [local:
namespace.c:3646]; `open_tree` of a subtree with locked children → EINVAL
[local: namespace.c:2399, 2984]. Clearing a locked flag → EPERM; *adding*
restrictions stays allowed — tightening yes, loosening no [local:
namespace.c:3242-3273]. **Key precedent for F2:** Linux never rejects a
tightening because children exist — when it tightens a live tree (namespace
copy), existing children are absorbed by the lock; EINVAL is reserved for
later operations that would circumvent it.

### noexec / nosuid / nodev

Enforced in the generic VFS at point of use, per-vfsmount, filesystem never
involved: `noexec` at `execve`/`may_open(MAY_EXEC)` [local:
fs/exec.c:115-122, 785; fs/namei.c:4269]; `nosuid` **silently ignored**,
not an error [local: fs/exec.c:1538; namespace.c:6421]; `nodev` at
device-node open → EACCES [local: fs/namei.c:4232-4251]. Toggling them has
no busy check; the flag gates future opens/execs only. Mounting `noexec`
over a filesystem with nothing executable is legal — no content check
exists [memory: mount(8), fstab(5)]. **Reads are never masked**: a `noexec`
binary can still be read and copied; a `nodev` node can be stat'ed and
listed. No Linux mount flag suppresses the read family — read denial is the
province of permission bits/ACLs/MAC, planes where a principal is in scope
[local: the three check sites above are exec/open-dev only; memory:
mount(2)]. There is **no Unix precedent** for `deny_ops={"read"}`.

### `/proc/self/mountinfo`

Fields: mount ID, parent ID, major:minor, root-within-fs, mount point,
per-mount options, extensible optional tags, fs type, source, super options
[local: linux/Documentation/filesystems/proc.rst:1960-1997]. Mount point +
root + type + source + both option fields + propagation tags suffice to
**reconstruct the namespace** — this is why mountinfo superseded
`/proc/mounts`, which could not distinguish subtree bind mounts. The Unix
lineage ran summary → full text → structured full data (mtab →
/proc/mounts → mountinfo → listmount/statmount); rows carry actual option
flags, never counts. Rows carry both per-mount and per-sb options —
precedent for `MountInfo` reporting effective (post-mask) caps *and*
entry-local policy.

### `move_mount(2)`

Detach and attach happen inside one `namespace_lock`/`lock_mount_hash`
region; no lookup observes the subtree absent or half-moved; no busy check
— open files keep working [local: namespace.c:3625-3697]. Rejections (all
EINVAL unless noted): source not a mount root, source is namespace root,
source `MNT_LOCKED`, source's parent shared, dir/non-dir mismatch,
destination outside namespace, unbindable-into-shared; destination inside
source → ELOOP. EXDEV never appears — a move is pure table surgery, no data
movement, matching the spec's "the binding moves, no stored data crosses."

### autofs

The kernel provides only **mount traps** (`d_automount` fires on access
beyond a stat, blocks the accessor, writes a request packet to the daemon's
pipe); the daemon consults the map and performs the real `mount(2)` [local:
Documentation/filesystems/autofs.rst:36-101]. Idle expiry is daemon-driven,
kernel-arbitrated; the autofs binding itself never changes [local:
autofs.rst:250-300]. The map **declares** up front; the mount **proves** at
first access — a wayward entry is discovered at use, not at map load
[local: autofs.rst:45-78; memory: auto.master(5)]. Layering lesson:
automount lives outside the mount-table core, composed on top — one-to-one
with "`LazyStorage` adapter in `storage/backends/`, router untouched."

## 2. Reference systems — Plan 9

### `ns(1)` and replayability

`ns` prints the namespace as an rc script that could recreate it, one line
per mount-table entry in table order: `mount <flags> <servename>
<mountpoint> <spec>` / `bind <flags> <src> <mountpoint>` / trailing `cd`
[local: plan9/sys/man/1/ns; plan9/sys/src/9/port/devproc.c:930-963].
Replayable because (a) every line *is* a `bind(1)`/`mount(1)` command —
the same syntax `namespace(6)` files feed `newns` [local:
plan9/sys/man/6/namespace]; (b) sources are recorded as **names, not
descriptors**; (c) per-binding flags are stored verbatim in `Mount.mflag`
and printed verbatim — policy round-trips; (d) table order is preserved.
Omitted: mount id, auth facts, liveness, capabilities. Names are bind-time
snapshots ("may be inaccessible if the files have been subsequently
renamed") [local: man/1/ns BUGS]. Lesson for `MountInfo`: replayability
comes from storing mounter-imposed policy *on the row* and echoing it
exactly — for us: `permissions`, `deny_ops` (echoed verbatim as its own
field; post-mask caps alone cannot recover a mask), `no_overlay`,
`owned`.

### Remount analogue

**No flag-mutation call exists** — the surface is exactly `bind`, `mount`,
`unmount`, `rfork(RFCNAMEG)`. Closest analogue: a fresh `MREPL` bind at an
already-bound point atomically replaces the mount list there under
`wlock(&m->lock)` — no unbound window [local:
plan9/sys/src/9/port/chan.c:715-742]. Our `remount` is that minus source
re-evaluation and re-probe. No precedent for partial flag updates —
supports `None`-means-unchanged with a whole new `MountMeta` over field
mutation.

### Dead servers; unmount

Plan 9 never reaps or annotates a dead mount; failure reports per-operation
at dispatch (`Ehungup`, `Emountrpc`) and the table row persists [local:
plan9/sys/src/9/port/error.h:6,24; devmnt.c:750-820]. No refresh operation
exists — none is needed because Plan 9 snapshots nothing; the
reconnected-backend problem `refresh_caps` addresses is a consequence of
*our* capability snapshotting. `unmount(2)`'s two-argument selector exists
only because a mount point holds a union stack; with no unions, one
argument is total — `unbind(path)` needs no selector. `Eunmount` "not
mounted" is an error, not a no-op [local: man/2/bind:196-213;
chan.c:764-833] — supports `ValueError` on unknown path for
`unbind`/`remount`.

## 3. Consumers — MCP wire posture

Config/topology reaches MCP clients as **resources** (JSON via
`resources/read`; fastmcp auto-serializes dicts) or **tool results with
`structuredContent`** — a JSON *object* with named keys; bare
tuples/NamedTuples serialize positionally and render as opaque arrays
[local: modelcontextprotocol/docs/specification/2025-11-25/server/{tools,resources}.mdx;
python-sdk func_metadata.py; fastmcp docs/servers/resources.mdx]. Per 056,
admin verbs are not wire protocol; `mounts()` rows reach clients via a
read-only resource/diagnostic on the future MCP server (017's revivable
half) or in-process JSON dumps — either way each row must become a JSON
object (`_asdict()`), never a positional array. `frozenset` fails
`json.dumps` outright. 057's freeze discipline makes the first shipped
field names/shapes permanent, and 057 D14's Plan 9 lesson means any summary
string *will* be regex-parsed into de-facto wire grammar. Precedent is
uniform: fsspec `to_json()` serializes full constructor arguments,
reconstructible [local: filesystem_spec/fsspec/spec.py:1438-1537]; minio
`ListTargets` returns full remote config, never counts [local:
minio/cmd/bucket-targets.go:246]. No surveyed system summarizes policy in
its mount/remote listing.

## 4. Fork resolutions

### F1 — `permissions` field format

**Decision.** The field carries the fully serialized `PermissionMap` as a
JSON-native dict — `{"default": "read"|"read_write", "overrides":
[[prefix, perm], ...]}` in the map's normalized (duplicate-rejected at
construction, length-sorted) order — typed via a small TypedDict (`PermissionsPayload | None`), `None`
meaning the entry stores no local map (possible only on child binds; the
root row always carries a map). No summary string ships, alone or
alongside. The JSON-fixed-point rule is pinned for every `MountInfo` field,
which also converts `caps` from `frozenset[str]` to a sorted
`tuple[str, ...]`.

**Rationale.** The fork is forced, not preferential: the spec's replay
constraint requires rows sufficient to reconstruct the namespace, and a
summary string carries a rule *count* — prefixes and per-prefix permissions
are unrecoverable, so option (a) fails categorically outside the
default-only case. Option (c) puts a derived digest beside its evidence
(the disagreement-by-redundancy smell 057 D1 made unrepresentable) and
ships a second frozen wire grammar clients will regex-parse (057 D14).
Option (b) is essentially free in the live code: `PermissionMap` is two
JSON-adjacent fields (permissions.py:126, 168-169), `__post_init__`
re-normalizes generic pair iterables (permissions.py:171-186), and
`coerce_permissions` passes maps through (permissions.py:206-207) — replay
is `PermissionMap(default=..., overrides=...)` verbatim at runtime,
round-trip exact. (Typed replay code converts the pairs explicitly — see
the spec's `payload_to_map` note — since `list[list[str]]` is not
statically assignable to the declared `overrides` tuple type; only
`__post_init__`'s runtime normalization accepts the payload verbatim.)
Precedent unanimous (mountinfo, `ns(1)`, fsspec, minio). `None` semantics
fall out of the table: `bind` stores `permission_map=None` when omitted
(base.py:237); the constructor always installs a root map (base.py:184-189).

**Dissent.** The dict is the weakest-typed, least glanceable field on the
row: ty cannot fully check its shape, rows become unhashable, wide override
lists render poorly in compact tables, and the `{default, overrides}` key
names plus positional pair-arrays freeze as wire contract on first ship —
future permission-vocabulary growth must be strictly additive, and every
human-facing consumer reimplements the one-line summary.

### F2 — `no_overlay=True` over existing deeper bindings

**Decision.** Commits, with **future-only effect**: meta replaced
atomically under the mount lock; existing children stay bound and
dispatching; only subsequent binds beneath the entry are refused — by the
existing bind-commit checks with the existing error message. No deeper-scan
or rejection branch in `remount`. The docstring/field docs must say "no
*new* binds beneath," and the one-way ratchet (a grandfathered child can be
unbound but its vacated path cannot be re-bound) is pinned as intended.

**Rationale.** (1) `no_overlay` is a pure bind-time gate — its only two
reads in all of `src/vfs` are `bind`'s under-lock ancestor and root checks
(base.py:255-264); dispatch, unbind, `capabilities()`, fan-out never
consult it — so future-only is the flag's existing semantics applied at a
later set-time, costing zero new enforcement code. (2) Linux never rejects
a tightening because children exist: noexec-family remounts run no
content/busy check, and `MNT_LOCKED` absorbs existing children; EINVAL is
reserved for circumvention. (3) Rejection makes the flagship move —
`remount("/", no_overlay=True)` — unreachable on any table with children,
with no remediation: unbind-seal-rebind is impossible because the sealed
parent refuses rebinds; the state {sealed parent, retained children} could
never exist, forcing the non-atomic gap this feature eliminates. (4) The
stricter-than-Unix temperament targets *shadowing*; sealing above visible
children hides nothing, and since `unbind` ignores the flag the subtree
monotonically converges toward fully sealed. Aligned with Linux, so no
constitution Art 3 deviation record is needed.

**Dissent.** Future-only permanently forfeits the invariant "`no_overlay`
entry has an empty subtree" — no future code (fan-out descent skips, naive
`mounts()` replay, `move_mount` destination shortcuts) can ever rely on it,
and tightening to rejection later would be a breaking change; it is the one
spot where the table tolerates a flag whose strongest reading is weaker
than its actual state.

### F3 — `deny_ops` scope

**Decision.** Restrict the mask to `MUTATING_OPS | EXEC_OPS`. Any
read-family op (`READ_OPS`: read, stat, ls, tree, glob, grep, glean, graph)
in `deny_ops` raises `ValueError` at every intake — constructor, `bind`,
`add_mount`, `remount` — before any table mutation. The validation is
closed over the known `READ_OPS` names, so if `deny_ops` is ever widened to
raw strings for peer ops, unknown names stay maskable. "Discoverable, not
readable" remains expressible storage-side (a backend declaring `ls`/`stat`
but not `read`, or a read-stripping wrapper adapter); loosening later is a
backward-compatible deletion of a check.

**Rationale.** (1) The fork's premise about 044 was wrong: 044's D3
(signed off 2026-07-03) rules *against* read masking — "every mask includes
`read`, by construction… a mounted-but-unreadable subtree is a foot-gun,"
with an explicit no-dark-mounts acceptance criterion; its enabled use case
is "discoverable, not writable, not runnable." Restriction *is* the 044
carry-over 068 promises; allowance would silently reverse a sign-off.
(2) Reference systems unanimous across 50 years: no Unix mount flag masks
the read family; read denial lives in the permission plane where a
principal is in scope — mount flags are principal-blind, exactly as
`deny_ops` is (no admin method takes an identity, and 070's principal
sessions make a principal-blind read mask almost never the real policy).
The live code encodes the same layering: `READ_OPS` is docstring-pinned
"routed, no write gate," and the composed check returns `None` for every
non-mutating op. (3) Restriction buys invariants: advertised read ops
genuinely answer; `ls` never returns rows no verb can open; since every
fan-out verb is read-family, masks can never cause a fan-out skip, so
policy never masquerades as backend incapacity. Unrestricted read masking
would also be inconsistently enforced by construction — `_probe_bind_site`
reaches storage via `_call_storage` without the entry gate — and
`deny_ops={"read"}` is a false-containment trap (grep/glean/tree still
surface content; closing the leak means masking `ls`, precisely 044's
rejected dark mount). (4) Regret asymmetry is decisive on its own:
loosening later deletes a check no client depended on; restricting after
shipping breaks live namespaces under 057's freeze discipline.

**Dissent.** The permission vocabulary cannot express read denial
(`Permission` is only `"read"`/`"read_write"`), so `deny_ops` was the only
mounter-side lever for "names public, content gated" — and a
lists-but-won't-read citizen remains legal via native backend declaration,
so the restriction stops only the mounter from minting a state the
architecture tolerates elsewhere. If 034's untrusted-MCP direction produces
a real catalog of that shape, this story must be reopened.

## 5. Code-grounding drift audit (all corrected in spec.md, 2026-07-10)

1. **`_decorate` does not exist.** The funnel is rebase + shadow-filter
   only (`_dispatch_entry`, base.py:1626-1636); nothing in the router reads
   `storage.description` today — it is only a required identity attribute
   (protocol.py:299). The live-attribute read is **new with this story**,
   not "matching" anything. (Stale mentions: base.py:26 docstring phrase;
   protocol.py:289-290 doc promise.)
2. **`caps: frozenset[str]` contradicted the `json.dumps` criterion** —
   `json.dumps` raises `TypeError` on a frozenset. Now a sorted
   `tuple[str, ...]` (folded into F1's JSON-fixed-point rule).
3. **Root row `permissions` is never `None`** — the constructor always
   installs a `PermissionMap` via `coerce_permissions` (base.py:167,
   184-189; permissions.py:200-211); only non-root binds store `None` when
   omitted (base.py:237). "None if no local rules" scoped to child binds.
4. **`remount("/")` vs "matching `unbind`" conflicted in mechanism** —
   `_normalize_mount_path` rejects root (base.py:460-463) and is used by
   bind/unbind/add_mount/remove_mount; `remount` needs its own
   normalization that admits root. Spec now says so. (057 D15 tension also
   resolved: `remount` performs no storage mutation, so plain `ValueError`
   like `unbind` — `MountError` stays reserved for `add_mount`/
   `remove_mount` storage-step failures, and is itself a `ValueError`
   subclass, exceptions.py:34.)
5. **"Mask propagates through every existing seam for free" was false at
   two seams:** (a) `_probe_bind_site` calls `_call_storage` directly for
   `stat`/`ls` with no capability gate (base.py:430, 441) — moot once the
   mask excludes read-family ops; (b) `add_mount` creates its site through
   the public gated `mkdir` (base.py:325), so a parent mask containing
   `mkdir` refuses new mount sites beneath it (`unsupported` →
   `MountError`) — now stated as intended and pinned in acceptance;
   (c) `_call_storage`'s isinstance family checks (base.py:1678-1724)
   remain an independent `unsupported` source for over-claims.
6. **`storage_name: str | None` over-permissive** — the protocol requires
   `name: str` (protocol.py:298); now plain `str`.
7. **"Table lives only in `_bindings`"** — plus the derived
   `_sorted_mount_paths` index (base.py:191, 470-478). `remount` replaces
   a `Binding` value in place (keys unchanged, no rebuild); `move_mount`
   changes keys and must call `_rebuild_sorted_mounts`.

Verified sound: unbind's `ValueError` on unknown path (base.py:283-285);
frozen caps snapshot (base.py:188, 240, never refreshed); the non-atomic
unbind+bind gap (orphan dir resolves to parent; probe requires an existing
empty dir, base.py:415-446); `run` outside the write gate (ops.py:71;
permissions.py:294); `TransportError` → `backend_unavailable`
(base.py:1727-1733); `_gate_entry` reads `meta.caps`, never live
capabilities, and reports the bind path with `unsupported`
(base.py:1545-1578); fan-out skips mint info-severity `unsupported` at the
bind path (base.py:1797-1819); `capabilities()` unions snapshots, no lock,
synchronous (base.py:401-413); test doubles cover every criterion
(tests/base_doubles.py — `RecorderStorage` with a live-read `caps` knob,
`RunnerStorage` as the noexec double, `BindableStorage` for probe sites;
caveat: `.calls` records op dispatches only, so the no-storage-I/O
criterion needs a small subclass spying `capabilities()` invocations; the
`description` live read is pinned by mutating the attribute post-bind,
not by a spy).

## 6. Prior-art constraints honored

- **044**: mounter-imposes-policy, masks-visible, intersection-along-chain
  carried over; no-dark-mounts *re-affirmed* by F3 (not silently reversed).
- **056**: control plane off the wire; D2's dropped tightening override
  sanctioned feature 3's return in advance; D11 no-storage-I/O-under-lock
  binds `refresh_caps` sequencing; D6 root-as-ordinary-entry grounds
  `mounts()` root row and `remount("/")`; D19's in-flight-race contract
  covers remount's concurrent-read window.
- **057**: no new error kind (D5 tombstones); D10/D12 classification and
  bind-path reporting reused; D15 `ValueError`-vs-`MountError` resolved
  (drift 4).
- **040**: mask lands in the *capability* slot of the pinned gate order —
  masked reads as `unsupported`, never a policy denial.
- **070**: no signature impact (admin surface carries no identity
  parameter); `deny_ops` is principal-blind per 070's resolved `system()`
  fork; sequencing 068-vs-070 stays a STATUS.md call.
- **054**: when `serve()` lands, `remount` joins the locked control-plane
  set, never a wire tool; `mounts()` may surface only as a read-only view.
- **039**: non-revival holds with two recorded residues — kind mapping
  supersession (`permission_denied` → `unsupported` for denied execution)
  and per-path execute carve-outs left unexpressed (`deny_ops` is
  per-entry); 039/044 statuses to be trued up when 068 lands.
- **017**: feature 1 supersedes exactly the programmatic half
  (`MountInfo` + accessor); everything else stays parked.
- **Constitution**: §1.4 (mounts may change capabilities, not taxonomy) —
  the caps-intersection with no new kind is the clean shape; Art 2.3
  bounded-listings note (`mounts()` is unbounded, defensible as
  control-plane accessor — one line for plan.md); Art 3 deviation records
  not triggered (F2 aligns with Linux); Art 5 snapshot-reads satisfied by
  construction.

Sources: `src/vfs/{base,permissions,ops,exceptions}.py`,
`src/vfs/storage/protocol.py`, `tests/base_doubles.py`;
`context/constitution.md`, `context/decisions/002`,
`context/stories/{017,039,040,044,054,056,057,070,071}/spec.md`,
`context/stories/{README,STATUS}.md`; Linux and Plan 9 sources as tagged
`[local: ...]` above; MCP/fastmcp/python-sdk/fsspec/minio sources as tagged
in §3.
