# 055 — Tasks

1. [ ] `ops.py`: delete `SPINE_READ_OPS` + docstring row.  (No kind
   changes — mount points are plain directories everywhere.)
3. [ ] `storage.py`: `mkdir` gains `parents`/`exist_ok`; `write` gains
   `parents`.
4. [ ] `src/vfs/backends/memory.py`: `InMemoryStorage` (read, pattern
   search, mutation, `allow_files`).
5. [ ] `base2.py`: constructor default → `InMemoryStorage(allow_files=False)`;
   kill storageless branches; `capabilities()` seed from storage ops.
6. [ ] `base2.py`: spine removal; `_mounts_beneath` region helper;
   tree local wrapper with mount descents; `_project_mounts` on local
   reads.
7. [ ] `base2.py`: `add_mount` fused shape (+`parents`), `remove_mount`
   unbind+rmdir; router `mkdir`/`write` thread the new flags.
8. [-] `tests/test_backends_memory.py`: backend contract suite.
9. [-] `tests/test_base_mounts.py`: parent rule, lifecycle, projection,
   read-only refusal; invert sparse-mount tests.
10. [-] Retire `tests/test_base_spine.py`; port survivors into mounts /
    dispatch suites (incl. story 050 equivalence).
11. [-] Sweep remaining suites for bare-node assumptions.
12. [-] End-of-session: `uv run pytest tests/`, `uv run ruff check`,
    `uv run ty check` on touched files.

Tasks 8-12 folded into story 056 (2026-07-07): the suites they
targeted are reshaped by the storage-mount rebuild, so the port
happened once, there.  See 056 tasks 14-18.
