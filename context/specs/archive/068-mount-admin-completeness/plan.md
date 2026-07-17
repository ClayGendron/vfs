# 068 — Plan: mount administration completeness

Implements features 1–3 (`mounts()`, `remount`, `deny_ops`) against the
resolved spec. Features 4 (`move_mount`) and 5 (`LazyStorage`) stay
demand-gated per the spec's order of work — if picked up they leave as
their own stories; nothing here builds toward them.

## Build order vs. spec order

The spec lands 1 → 2 → 3, but all three features share one substrate:
`MountMeta` must carry the mask and the unmasked snapshot before
`MountInfo` can echo them, before `remount` can replace metas wholesale,
and before the intakes go live. So the plan front-loads that reshape as
a behavior-neutral groundwork step, then lands the features in spec
order — each landing green.

## Approach

1. **Groundwork — `MountMeta` reshape (no behavior change).** Fields
   become `permission_map`, `no_overlay`, `owned`, `declared_caps`
   (the unmasked bind-time snapshot), `deny_ops` (validated mask,
   default `frozenset()`); `caps` becomes `field(init=False)` computed
   in `__post_init__` as `declared_caps - deny_ops`. The spec's
   stored-vs-derived question resolves as *stored, derived at
   construction*: the invariant is unforgeable (no call site can
   hand-assemble a meta whose `caps` disagrees with its parts) and the
   dispatch hot path keeps O(1) attribute reads — `_gate_entry`,
   `capabilities()`, fan-out skips, and tree descents need no edits,
   ever. Three construction sites switch to `declared_caps=`: the
   constructor (base.py:184), `bind` (base.py:236), and the direct
   `MountMeta(caps=...)` in tests/test_base_mounts.py:445 — miss the
   third and task 1 goes red. Imports: base.py needs `field` (only
   `dataclass` is imported today) and a runtime `READ_OPS`.
   Alongside: `_validate_deny_ops(deny_ops) -> frozenset[Op]` in
   base.py's internal helpers — materialize the iterable, raise
   `ValueError` naming any `READ_OPS` members, deliberately **no**
   `ALL_OPS` membership check (unknown names stay maskable per the
   spec's forward-compatibility note).

2. **Serialization — `permissions.py`.** `PermissionsPayload` TypedDict
   in the module's shared-types section and `PermissionMap.to_payload()
   -> PermissionsPayload` emitting `{"default": ..., "overrides":
   [[prefix, perm], ...]}` in the map's already-normalized order. The
   method lives on the map because normalized order is the map's
   knowledge; base.py just calls it. No live-code annotation change for
   the reverse direction — replay's `payload_to_map` is a tests-side
   helper per the spec.

3. **Feature 1 — `MountInfo` + `mounts()`.** `PermissionsPayload` is
   re-exported where needed; `MountInfo` (NamedTuple, spec's exact
   shape) sits in base.py's shared-types section beside `Binding`.
   `mounts()` goes in the mount-administration group: synchronous, no
   lock (one dict snapshot — sync methods can't be interleaved on the
   loop), rows built in **ascending** bind-path order via a fresh
   `sorted(self._bindings)` — `_sorted_mount_paths` is reverse-sorted
   for longest-prefix matching and must not be reused here.
   Per row: `path=str(...)`, `storage_name=storage.name`,
   `storage_type=type(storage).__name__`, `description` as a live
   attribute read, `caps=tuple(sorted(meta.caps))`,
   `deny_ops=tuple(sorted(meta.deny_ops))`, `permissions=None` when
   `meta.permission_map is None` else `to_payload()`, plus the two
   flags. Export `MountInfo` and `PermissionsPayload` from
   `vfs/__init__.py`.

4. **Feature 2 — `remount`.** Spec signature verbatim — including
   `deny_ops`, whose replace/clear/keep semantics ship complete here
   (the two stored facts and the validator exist from groundwork);
   feature 3 is then intakes only, and adds no remount code.
   - *Normalization:* `_normalize_mount_path` gains
     `allow_root: bool = False`; `remount` passes `True`. One helper,
     one flag — no second normalizer to drift.
   - *Sequencing:* validate `deny_ops` first (before any storage call —
     the combined read-family-mask + `refresh_caps=True` criterion
     requires raising without re-snapshotting). Then, if
     `refresh_caps`, read the current binding (sync dict get; unknown →
     `ValueError`) and call `binding.storage.capabilities()` — the
     protocol method is synchronous, so "outside the lock" (056 D11)
     means "before acquiring". Then `async with self._mount_lock:`
     re-fetch the binding: it must exist and hold **the same storage
     object** as the pre-lock read, else `ValueError` — the table
     changed while awaiting the lock and the snapshot is stale
     (`bind`'s re-check temperament). Under the lock, build the new
     `MountMeta` from the current meta with non-`None` deltas applied
     (`deny_ops=()` clears, `None` keeps; fresh snapshot replaces
     `declared_caps` only when `refresh_caps`), then
     `self._bindings[p] = binding._replace(meta=new_meta)`. Keys
     unchanged — no `_rebuild_sorted_mounts`. No await between re-check
     and commit.
   - *`no_overlay` future-only:* zero enforcement code — `bind`'s
     existing under-lock checks are the whole mechanism. The docstring
     and the `MountInfo`/`MountMeta` field docs state "no *new* binds
     beneath" and the one-way ratchet, per the resolved fork.
   - *Closed table:* the dict is empty, the get returns `None`, the
     same unknown-path `ValueError` fires — no separate branch.

5. **Feature 3 — `deny_ops` intakes.** Constructor, `bind`, and
   `add_mount` gain `deny_ops: Iterable[Op] = ()`, each validating via
   `_validate_deny_ops` **before** any side effect — in `add_mount`
   that means before the `mkdir`, or a rejected mask would still mint
   the site directory. `add_mount` then passes the validated mask
   through to `bind`. No gate changes anywhere: `meta.caps` is already
   post-mask from groundwork, so `_gate_entry` (`unsupported`, bind
   path), `capabilities()` unions, and fan-out skip classification pick
   the mask up by construction. The parent-mask-refuses-`add_mount`
   seam (`mkdir` masked → `unsupported` → `MountError`) and the
   ungated bind-site probe are existing behavior to pin in tests, not
   code to write.

6. **Tests — new `tests/test_base_mount_admin.py`** (the new admin
   surface; `test_base_mounts.py` at 826 lines stays the
   lifecycle/bind/unbind file). Doubles: add a small
   `CapCountingStorage(RecorderStorage)` to `base_doubles.py` spying
   `capabilities()` invocations (`.calls` records op dispatches only);
   reuse `RecorderStorage`'s live `caps` knob for `refresh_caps`,
   `RunnerStorage` for the noexec double, `BindableStorage` for probe
   sites. Test groups mirror the spec's acceptance blocks one-to-one:
   - `mounts()`: fresh-router root row; add/remove/unbind/close row
     lifecycle; an explicit ascending-bind-path-order pin;
     `json.dumps(row._asdict())` round-trip; the replay round-trip with
     `payload_to_map` (typed tests-side helper, spec's exact shape) —
     shipped mask-free here and **extended in the feature 3 task** with
     a masked entry and a constructor-level `deny_ops`, since the
     intakes don't exist yet; child-bind `permissions=None`;
     no-storage-I/O (`.calls` snapshotted/cleared *after* setup — the
     bind probe and `add_mount`'s mkdir legitimately record on the
     parent — plus zero `capabilities()` re-calls); live `description`
     mutation.
   - `remount`: read→write flip; the atomicity contrast against
     unbind+bind driven through a **suspending parent double**
     (`SuspendingStorage`-style `stat`/`ls`, base_doubles.py:255) —
     every listed double's methods run without yielding, so a bare
     `asyncio.gather` never interleaves and the contrast would pass
     vacuously; the suspension opens bind's probe window so the read
     deterministically lands in the unbound gap (parent entry) on the
     unbind+bind branch and never does across `remount`; `refresh_caps`
     both ways; field-by-field preservation; unknown-path and
     closed-table `ValueError`; the `no_overlay` grandfather + ratchet
     pins, non-root and root.
   - `deny_ops`: `RunnerStorage` noexec (`unsupported` at bind path,
     reads answer, `capabilities()` shrinks); fan-out invariance;
     read-family `ValueError` at all four intakes with table/meta
     unchanged; the no-resnapshot criterion; parent `mkdir` mask →
     `add_mount` `MountError` while direct `bind` succeeds; inert-mask
     echo; constructor-level root mask; replace/clear round-trip with
     zero `capabilities()` calls.

## Plan-level decisions

- **`caps` stored-but-construction-derived** (rationale in step 1).
- **`remount` cannot clear a child's local map back to `None`** —
  `permissions=None` means "keep", and no `UNSET` sentinel ships. In
  effect `permissions="read_write"` is equivalent: under
  most-restrictive-wins layering a default-only `read_write` map never
  tightens anything the chain above allows (verified: `None` skips the
  layer, base.py:1591; `read_write` resolves to no denial for every
  op). The residue is representational only — the row shows a payload
  instead of `None`, and replay reproduces a map. Accepted asymmetry;
  a sentinel is a purely additive change if a real need appears.
- **Concurrent storage swap during `remount`'s lock wait raises
  `ValueError`** rather than silently re-snapshotting (which would be
  storage I/O under the lock) — loud and retryable.
- **Constitution Art 2.3 (bounded listings):** `mounts()` is unbounded
  by design — a control-plane accessor over an admin-bounded table
  (rows = binds an administrator made), not a data-plane listing; no
  cap, no pagination.

## Outcome (post-implementation)

Landed as planned; the full pre-change suite passed unmodified except
two touch-ups the plan missed: `tests/test_ops.py`'s
`MANAGEMENT_METHODS` allowlist gains `"remount"` (the router-surface
drift test correctly flagged the new public coroutine), and the
`_validate_deny_ops` return type is `frozenset[Op]`, not
`frozenset[str]`, so `add_mount` can hand the validated mask to `bind`
under ty. The atomicity contrast worked as designed: with the
suspending parent double, the gathered read deterministically lands on
the parent entry during unbind+bind and never during `remount`. 26 new
tests; no re-pins of existing behavior were needed.

A six-dimension adversarial pressure sweep (30 agents: contract
honesty, concurrency/lifecycle, gate seams, adversarial inputs, type
guarantees, behavioral parity; every claim double-refuted) confirmed
the concurrency and gate mechanics outright and surfaced three
contract-honesty gaps, all fixed: (1) the replay recipe was dishonest
for tables where `remount(no_overlay=True)` grandfathered children —
now documented and pinned as **seal-last** (bind unsealed, seal via
`remount`); (2) name-keyed replay silently assumed unique storage
names — now stated on `mounts()`; (3) the spec's verbatim
`deny_ops=row.deny_ops` replay line failed ty — the `replay_ops`
widening is now recorded beside `payload_to_map`. One contested
finding was fixed as cheap hardening: a bare-string `deny_ops`
(`deny_ops="run"`) would have frozenset-splattered into an inert char
mask — silently failing open, bypassing the read-family guard, and
able to clear a working mask via `remount`; `_validate_deny_ops` now
raises `TypeError` on str/bytes, matching `_as_list`'s temperament.

## Risks and checks

- **`MountMeta` churn:** three construction sites (one in tests, which
  ty alone won't flag as loudly — run the suite, not just ty).
  `slots=True` + `field(init=False)` + `__post_init__` is the one
  slightly novel dataclass shape — pin with a direct unit test that
  hand-built metas always satisfy `caps == declared_caps - deny_ops`.
- **ty on the payload boundary:** `overrides: list[list[str]]` is
  intentionally not assignable to `PermissionMap.overrides`; only the
  tests-side `payload_to_map` converts. Tree stays at ty zero with no
  live-code annotation change.
- **Hot path:** no per-dispatch set arithmetic is introduced anywhere.
- **070 sequencing:** this surface carries no identity parameter; if
  070 lands first, only `add_mount`/`remove_mount`'s internal
  `mkdir`/`delete` calls are brushed — no plan change either way.
- Suite: `uv run pytest tests/ -q` green, `ruff` and `ty` at zero after
  every task.
