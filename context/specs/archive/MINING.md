# Archive mining catalog — 2026-07-16

Verdicts from the four-agent mining pass over all 55 archived stories
(each spec read and cross-checked against `src/vfs/`, the four existing
ADRs, and the `research/` corpus). Execution order: write the promoted
ADRs and memos, run the two pre-deletion checks, then delete every
folder here — residue flows backward first (see `../README.md`).

## PROMOTE-DECISION — 8 ADRs to write

| Story | Decision to record |
|---|---|
| 002 | Metadata sidecar: chunks/versions/edges live in a hidden parallel tree (`/.vfs/<path>/__meta__/`), never as children of the file — a file can't be both file and directory on POSIX/FUSE backends. Governs `paths.py` (`METADATA_ROOT`, `META_SEGMENT`). |
| 032 | No path-prefix tenant scoping: `/{user_id}` prefixes dropped; tenant isolation is a permission layer over one global namespace (Unix model). Confirmed live — no `scope_path`/`user_id` in `paths.py`. (Correction 2026-07-16: its `VFSPath` typed-handle half DID land — `7d8d86f`, later renamed to the live `Path` class — it's a separate concern scoped out of ADR 006, not a rejected design.) |
| 036 | Search surface: one fused `glean(query, limit)` — the caller never selects a retrieval strategy (backends fuse vector/lexical/graph opaquely); deliberately asymmetric with `graph(method, …)`; centrality dropped. |
| 037 | Result is the only failure channel inside the mount tree; raising is an outermost-boundary opt-in (`raise_if_failed`), never a node flag — root is a role, not a type. |
| 055 | Mount points are stored plain directories; the binding is runtime-only table state (no `mount` kind); router spine deleted; `VirtualFileSystem()` defaults to directories-only `InMemoryStorage`. Record the **landed** shape (056's bind-onto-existing-empty-directory), not 055's drafted fused-mkdir. |
| 057 | Result envelope: `success` derived not stored, severity/source provenance, value-identity dedup, hierarchical dotted kinds with longest-prefix dispatch + tombstoned aliases, derived retry classes, lenient per-item parsing, zero-progress fan-out demotion. |
| 069 | No-union routing rule: a function returns one type (`X | None` the only union); value-producers are total, policy checks partial; no function both produces and refuses. Binding constraints: router-side table-fact checks only (backends check-and-act); holds only while resolution is I/O-free. |
| 071 | Router owns ingress: every public verb strictly validates non-path parameter types/domains before any state or dispatch (`vfs.invalid`, dispatch nothing) — validates, never repairs; structural decode belongs to the wire adapter. Governs `params.py`. |

## PROMOTE-RESEARCH — 2 memos to write

| Story | Memo |
|---|---|
| 009 | Cloud permission-model invariants (Drive/SharePoint/Dropbox synthesis, six cross-cutting invariants) — the spec cites `research/2026-04-22-cloud-permission-models.md`, which was never written. Extract from the spec before deletion. |
| 031 | Single-creation-chokepoint survey (`explanation.md`: Linux `vfs_create`, BSD `VOP_CREATE`, 9P `screate`, SQLite btree insert, FTS5 shadow tables) → dated memo on one-door entry creation. |

## Pre-deletion checks

- **013**: ~~confirm the `analysis-*.md` evidence files are reflected in the
  existing grep-index memos~~ **done 2026-07-16** — one gap found and
  extracted to `research/2026-07-16-fts5-trigram-tokenizer-divergence.md`
  (FTS5 gram-alphabet divergence + zoekt DocChecker limits); everything
  else re-covered by the 2026-07-13/14 memos. 013 is now safe to delete.
- **069**: fold its three-lens `namei` review (Linux/Plan 9/BSD) into the
  ADR's context section rather than a separate memo; same for 071's
  openat2/9P/MCP validate-posture inputs.

## DELETE — 45 folders, nothing durable beyond code/ADRs/research

001, 003, 004, 005, 006, 007, 008, 010, 011, 012, 013*, 014, 015, 016,
017, 018, 019, 020, 021, 022, 023, 024, 025, 026, 027, 028, 029, 030,
033, 034, 035, 038, 040, 041, 042, 043, 044, 046, 047, 048, 049, 050,
052, 059, 068. (*013 after its pre-deletion check.)

Dominant reasons: unbuilt namespace-wave features (018–024, 027, 034);
explicit supersession (017→068, 026→057, 028→029, 030/013/014→072 §6,
041/042/044/048/050→056/068); residue already promoted (046→ADR 001,
059→ADR 004, 068→2026-07-11 memo, 057-research→2026-07-08 memo).

The 10 promote-source folders (002, 009, 031, 032, 036, 037, 055, 057,
069, 071) are deleted too once their ADR/memo lands.
