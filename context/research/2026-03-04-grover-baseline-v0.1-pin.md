# VFS Baseline: v0.1 Alpha API Pin

- **Date:** 2026-03-04 (research conducted)
- **Source:** migrated from `research/grover-baseline.md` on 2026-04-18
- **Status:** snapshot — landscape findings remain current; any VFS API surface references reflect the v0.1 alpha and have been superseded by the v2 architecture

## Purpose

This file is a pin. The original `research/grover-baseline.md` was a complete inventory of VFS's (currently `Grover` in code) v0.1 alpha public API captured on 2026-02-17 (file later touched 2026-03-04). The full method-by-method breakdown is no longer useful because the API surface has been entirely replaced by v2.

## What v0.1 looked like

- Two facades: sync `Grover` (RLock + daemon thread event loop) and async `GroverAsync`, both exposing identical methods.
- A mount-based filesystem: `mount(path, backend, ...)` / `unmount(path)`, with longest-prefix path routing across `LocalFileSystem`, `DatabaseFileSystem`, and `UserScopedFileSystem` backends.
- A broad surface of CRUD + search + versioning + trash + sharing + reconciliation operations, plus a separate graph API (`successors`, `predecessors`, `path_between`, `contains`) and a semantic `search(query, k)`.

## What replaced it

Replaced as of v0.0.15 by the v2 architecture:

- A single `grover_objects` table unifies files, versions, edges, chunks, embeddings, and shares under one "everything is an object" schema.
- A concrete `GroverFileSystem` base class with the `_*_impl` terminal pattern — callers hit the base methods, which delegate to backend-specific `_*_impl` terminals.
- Mount routing and `GroverResult` structured returns are still present; the dual sync/async facade has collapsed behind the base class.

## Where to look now

- Live code: `src/grover/` (module will rename to `vfs`; PyPI package is `vfs-py`).
- Current architectural shape: `docs/architecture.md`.
- For how the v2 pieces fit together, see the `grover-v2-architecture` and `user-scoped-filesystem` notes in project memory.
