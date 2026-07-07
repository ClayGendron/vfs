# 056 — Tasks

## Pass A — protocol + router core

1. [x] `results2.py`/`ops.py`: add `backend_unavailable`, `busy`,
   `budget_exhausted` error kinds (+ docstring-table rows).
2. [x] `storage.py`: `StorageBackend` gains required `name`,
   `description`, `capabilities()`; delete `storage_ops()`; add
   `TransportError` family; `SupportsClose` idempotent/dead-peer
   contract; path-form contract for returned paths.
3. [x] `backends/memory.py`: `name`/`description` kwargs;
   `capabilities()` full set regardless of `allow_files`.
4. [x] `tests/base_doubles.py`: all doubles implement the three new
   members; partial doubles declare exactly what they implement.
5. [x] `permissions.py`: `check_writable` takes `(PermissionMap,
   context)`; ancestor-composition helper (mount-relative
   coordinates, most restrictive wins).
6. [x] `base2.py` types: `MountMeta`; `Binding(path, storage, meta)`;
   identity entry at `/`.
7. [x] `base2.py` deletions: `_call_remote_op`, `_parent`, `_root`,
   `_reachable_ids`, cross-instance commit gate, add_mount
   delegation, `allow_child_mounts`, recursive close, resolve
   nesting loop, fs-is-self branches.
8. [x] `base2.py` funnel + gates: single longest-prefix resolve; one
   funnel with `TransportError` → `backend_unavailable` and
   decoration at the rebase seam; snapshot capabilities; ancestor
   permission composition; `no_overlay`.
9. [x] `base2.py` entry-keyed dispatch at all five sites
   (grouped-observations, two-path → `cross_mount`, entry-batch,
   mkedge, fanout grouping/dedupe).
10. [x] `base2.py` shadowing: merge-seam filtering, `tree` region
    subtraction, `ls` union of storage rows + table entries;
    correct `_merge_results` docstring.
11. [x] `base2.py` busy guard on data-plane mutations at bind sites
    (including resolved-to-mount-root).
12. [x] `base2.py` hop budget: constructor default 16, threaded
    through fan-out/tree → `budget_exhausted`.
13. [x] `base2.py` lifecycle: `bind`/`unbind` primitives
    (onto-existing-empty); `add_mount`/`remove_mount` as sugar
    (mkdir-if-absent / strict rmdir); aliasing refusal; no storage
    I/O under `_mount_lock`; close = snapshot-clear, dedupe, `owned`,
    timeouts, gather.
14. [x] Tests rework: `test_base_mounts.py`, `test_base_dispatch.py`,
    `test_base_gates.py`, `test_storage.py`,
    `test_backends_memory.py` (absorbs 055 task 8).
15. [x] Tests new: shadow filtering, `cross_mount`, `busy`,
    `backend_unavailable`, close ordering/dedupe/cancellation, hop
    budget, per-row grouped reads (closes 050).
16. [x] Retire `test_base_spine.py`; port survivors (055 task 10).
17. [x] Story/ADR ripples: 015 superseded-in-shape; 041/048/050
    closed; 054 re-read; ADR 002 consequence note.
18. [ ] End of session: `uv run pytest tests/`, `uv run ruff check`,
    `uv run ty check` on touched files.

## Pass B — adapter

19. [ ] `adapter.py`: `VFSStorageAdapter` per-verb class — arg/result/
    error rebasing, root clamp, live name/description/caps
    forwarding, wrapped-identity exposure; `ClosingAdapter` opt-in;
    move/copy + edit signature bridges.
20. [ ] `tests/test_adapter.py`: rebasing, clamp, capability
    forwarding, nested bind over adapter, mutual-adapter loop →
    `budget_exhausted`, closing semantics.
21. [ ] End of session: pytest/ruff/ty.

## Pass C — MCP trio

22. [ ] `uv add mcp`; shared client core (exit stack, timeouts,
    `TransportError` mapping, dead-peer teardown).
23. [ ] `backends/mcp.py`: `MCPStorage` (generic — tools/list rows,
    `run` → `call_tool`, honest capabilities).
24. [ ] `backends/mcp.py`: `VFSStorage` (dialect — verb → tool,
    composite lowering, TTL wire field, caps/name/description
    refresh, HTTP auto-reconnect, stdio never respawned).
25. [ ] `mcp_server.py`: versioned tools, no admin surface,
    `listChanged` on mount changes, session-pinned identity.
26. [ ] Tests over in-memory transport: dialect round-trip, caps
    invalidation, dead-session → reconnect, generic tool mount,
    admin refusal, identity pinning.
27. [ ] End of session: pytest/ruff/ty.
