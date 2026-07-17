# 068 — Tasks

Ordered; every task leaves the suite green (`uv run pytest tests/ -q`,
`ruff`, `ty` at zero).

- [x] 1. Groundwork: `MountMeta` → `declared_caps` + `deny_ops` with
      `caps` derived in `__post_init__` (`init=False`); update the
      three construction sites (constructor, `bind`, and
      tests/test_base_mounts.py:445); base.py imports gain `field` and
      runtime `READ_OPS`; add `_validate_deny_ops` to base.py internal
      helpers. No behavior change; direct unit test for the caps
      invariant.
- [x] 2. `permissions.py`: `PermissionsPayload` TypedDict +
      `PermissionMap.to_payload()` in normalized order.
- [x] 3. Feature 1: `MountInfo` beside `Binding`; `mounts()` in the
      mount-administration group (sync, no lock, ascending path order,
      live `description` read); export `MountInfo` and
      `PermissionsPayload` from `vfs/__init__.py`.
- [x] 4. Feature 1 tests in new `tests/test_base_mount_admin.py`:
      root row, row lifecycle, ascending-bind-path-order pin, JSON
      round-trip, replay round-trip via `payload_to_map` (mask-free
      for now — task 8 extends it), child `permissions=None`,
      no-storage-I/O with `.calls` snapshotted after setup (add
      `CapCountingStorage` to `base_doubles.py`), live `description`.
- [x] 5. Feature 2: `_normalize_mount_path(allow_root=...)`; `remount`
      per plan sequencing (validate → optional pre-lock sync
      `capabilities()` → lock → same-storage re-check → meta replace),
      `deny_ops` replace/clear/keep semantics complete here;
      docstrings state future-only `no_overlay` + ratchet.
- [x] 6. Feature 2 tests: atomicity-by-contrast via a suspending
      parent double (`SuspendingStorage`-style `stat`/`ls` — a bare
      gather never interleaves, see plan), `refresh_caps` both ways,
      field preservation, unknown-path and closed-table `ValueError`,
      `no_overlay` grandfather + ratchet (non-root and root).
- [x] 7. Feature 3: `deny_ops` intake on constructor, `bind`,
      `add_mount` (validate before `mkdir`). No gate edits, no remount
      edits (task 5 shipped its mask semantics).
- [x] 8. Feature 3 tests: noexec via `RunnerStorage`, fan-out
      invariance, read-family `ValueError` at all four intakes
      (table/meta unchanged, no re-snapshot), parent `mkdir` mask →
      `add_mount` `MountError` vs direct `bind` OK, inert mask echo,
      constructor root mask, replace/clear with zero `capabilities()`
      calls; extend task 4's replay round-trip with a masked entry and
      a constructor-level `deny_ops`.
- [x] 9. Close-out: full suite + `ruff` + `ty`; spec status →
      implemented; true up 039/044 statuses (kind-mapping supersession,
      per-path execute carve-outs unexpressed) and the 017 half
      superseded by feature 1; STATUS.md row for 068; note any re-pins
      actually needed in plan.md.
