# 015. Split the Unified Entry into Entry + Chunk + Version + Edge

- **Status:** accepted
- **Date:** 2026-07-18
- **Deciders:** Clay Gendron
- **Decided by:** human (direction set by Clay in the 2026-07-18 model
  session — drop `tool`/`skill` as kinds, extract chunk/version/edge into
  their own models, single `Entry` over `File`/`Directory`; single-`Entry`
  shape recommended by the assistant and adopted; accepted same session)

## Context

`models/entry.py` carries one `Entry` model whose `kind` field ranges over
seven values — `file`, `directory`, `chunk`, `version`, `edge`, `tool`,
`skill` — and whose fields are a union of every kind's needs. A file never
sets `line_start`/`line_end`; a chunk never sets `mime_type`; an edge sets
only `edge_type`/`edge_weight`/`edge_distance`; a version alone uses
`version_diff`/`is_snapshot`/`created_by`. The result is ~20 nullable fields
gated by `kind`-dispatch in the validators (`_derive_identity`,
`_derive_and_measure`), the computed relationship paths, and every consumer.
To the type checker a chunk `Entry` and a file `Entry` are the same type, so
the "type gating" is runtime `if self.kind == ...` branching, not structure.

The persistence layer has already moved the other way. `build_vfs_tables`
mints a *family* — `entry`, `content`, `versions`, `chunks`, `edges` — and
`rows.py:ENTRY_FIELD_HOMES` already maps each non-entries-table field to its
home table (`version_diff`/`is_snapshot`/`created_by` → versions;
`line_start`/`line_end`/`embedding` → chunks; `edge_type`/`edge_weight`/
`edge_distance` → edges). The domain model and the schema have diverged: one
kinded model on one side, a table-per-concern family on the other, held in
sync only by a drift test walking a hand-written homes map.

This reopens the design from story 031 (research
`2026-06-12-single-creation-chokepoint.md`): the *unified* `Entry` was chosen
so there was exactly one door through which any object comes into existence,
closing the pre-rebuild "second doors" for chunk and version creation. That
property is worth preserving — but it argues for *one door per type*, not
*one type*. The chunk/version/edge machinery on `Entry`
(`chunk()`, `create_version_row`, `with_version`, `_reconstruct_file_version`)
is dormant in the live tree — no live caller invokes it; the only live
cross-kind uses are `memory.py` edge staging and `skills.py` skill/tool
construction — so the extraction is model-layer surgery, not a call-site
migration (greenfield: no data, no migration).

Two side facts force smaller pins. `tool` and `skill` are content-free
directory-like units under `/.agents` that live in the `entry` table beside
plain directories; nothing about their *row* differs from a directory.
And today `ext` is derived only when `kind == "file"` (`entry.py:275`),
which contradicts POSIX — a directory may legitimately carry a `.ext`
(`foo.bar/`).

## Options considered

- **(a) Status quo — one kinded `Entry`.** One construction door, one drift
  target. But the nullable-field wall grows with every new concern, kind
  dispatch leaks into every consumer, the model no longer mirrors the table
  family it persists to, and static typing cannot tell a chunk from a file.
- **(b) `File`/`Directory` subclasses (+ `Chunk`/`Version`/`Edge`).**
  Strongest static typing per node kind. But once a directory may carry
  `ext` (POSIX, below), file and directory share nearly every field — the
  base holds ~90% and the leaves are thin — so the split is churn without
  coherence, and polymorphic construction (`Entry(path=...)` dispatching to a
  subclass) fights the single-door chokepoint.
- **(c) One `Entry` (`kind: file | directory`) + standalone `Chunk`,
  `Version`, `Edge` models (chosen).** Model-per-table: `Entry` ↔ `entry`,
  `Version` ↔ `versions`, `Chunk` ↔ `chunks`, `Edge` ↔ `edges`. The
  genuinely-different things (their own tables, their own identity and
  invariants) become their own types with only their own fields; file and
  directory — which really do share one row shape — stay one simple model.
  Ergonomic derivation is preserved by thin factory methods on `Entry` that
  delegate to the owning model. Costs three new modules and a drift-test
  reshape.
- **(d) Keep unified `Entry`, add typed views/adapters over it.** No model
  split. But it leaves the model/schema mismatch in place and adds a parallel
  type layer to paper over it — two representations of the same rows.

## Decision

We choose (c). Seven pins:

1. **`Entry` covers `file` and `directory` only.** `ObjectKind` narrows to
   `Literal["file", "directory"]`. `Entry` keeps identity (path, name, kind,
   external_id), the shared body/metrics (content, content_hash, mime_type,
   ext, lines, size_bytes), the index flags (chunked, encoded), revision,
   ownership, and timestamps. It sheds `version_diff`, `version_number`,
   `is_snapshot`, `created_by`, `line_start`, `line_end`, `edge_type`,
   `edge_weight`, `edge_distance`, `embedding`, and the
   `parent_file`/`source_file`/`target_file` computed fields.

2. **`tool` and `skill` stop being kinds.** They are plain files and
   directories. Well-formedness is enforced by dedicated *creation helpers*
   (the `skills.py` builders keep formatting their unit directory and
   `SKILL.md`), and tool/skill *discovery* is by path semantics under
   `/.agents`, never a `kind` on the row. `_CONTENT_FREE_KINDS` collapses to
   `{"directory"}`.

3. **`Chunk`, `Version`, `Edge` are standalone models**, one per table — not
   `Entry` subclasses. Each owns its own fields, validators, metrics, and the
   invariant-enforcing construction that used to live on `Entry`:
   - `Version` absorbs `create_version_row`, `_stored_version_payload`, and
     `_reconstruct_file_version`, over the `versioning.py` provider
     (snapshot-vs-diff, forward-diff reconstruction, hash verification).
   - `Chunk` absorbs `split_content` and the naming/disambiguation logic from
     `chunk()`, over the `chunking.py` splitters.
   - `Edge` absorbs `edge_type` derivation and the source/target endpoint
     resolution.
   Each type is the single construction door for its kind — the story-031
   chokepoint, now held per type instead of per model.

4. **Ergonomic factories stay on `Entry`, delegating to the owning model.**
   `Entry.chunk() -> list[Chunk]` and `Entry.create_version(previous:
   Entry, ...) -> Version` remain so a caller can hold one entry and mint the
   rows that relate to it. These are thin factories: they marshal the entry's
   content and derived state and hand off to `Chunk`/`Version` construction —
   they never re-implement the invariants (no second door). The exact
   signatures (how the next `version_number` and `prev_content` are sourced)
   are a code/spec detail, not pinned here.

5. **`ext` is derived for directories too.** POSIX parity: `ext` derivation
   keys off the path, not `kind == "file"`, so `foo.bar/` carries `ext =
   "bar"`. Content invariants are unchanged — a directory carries no content;
   a file defaults to `""`.

6. **Path-role detection is a concern separate from `Entry.kind`.**
   `paths.py` still classifies a path's grammar (chunk/version/edge under
   `/.vfs`; file/directory otherwise) to route it to the right model and
   table — but that routing role is no longer the same type as `Entry.kind`,
   and `tool`/`skill` roles disappear. This ADR pins the direction; the full
   `paths.py` rework (renaming/splitting the role enum, retiring the
   tool/skill branches) lands in a follow-up, not the domain-models pass.

7. **`Observation` stays one masked model; its drift test pins per owner.**
   `Observation` remains the single, possibly-partial return row for every
   read (including grep hits on chunks and edge listings). But its mirror
   fields now mirror whichever model owns each field — `version_number` →
   `Version`, `edge_*` → `Edge`, the rest → `Entry` — so the drift test pins
   each mirror to its owning model, not to `Entry` alone.

## Consequences

- **Easier:** each model carries only its own fields, so static typing tells
  a chunk from a file and validators lose their kind-dispatch arms; the model
  layer mirrors the table family one-to-one, so `ENTRY_FIELD_HOMES` and its
  cross-model drift check shrink toward per-model column maps; `Entry` becomes
  a small, legible file-or-directory record; adding a future concern (a new
  indexed unit) is a new model + table, not another nullable column on
  everything.
- **Harder:** three new model modules and their construction/validation move
  out of `entry.py`; `Observation`'s drift test must resolve mirrors across
  four owners; `paths.py` grows a role-vs-kind distinction (staged now,
  finished later); the memory backend's edge staging and any future database
  write path for chunks/versions/edges must construct the new models rather
  than a kinded `Entry`; render's `_WRITE_SUMMARY_KINDS` and other kind-literal
  consumers need the narrowed vocabulary.
- **Committed to:** `Entry` = file|directory; `Chunk`/`Version`/`Edge` as the
  owning models and single doors for their kinds; `tool`/`skill` as
  path-semantic conventions over plain files/directories, never kinds;
  delegating factories on `Entry` for ergonomic derivation; POSIX `ext` on
  directories; `Observation` unified with per-owner drift. Deferred by design:
  the full `paths.py` role/kind split and the write/read/memory/render wiring
  to the new models (this ADR scopes the domain-models pass only).

Evidence: `research/2026-06-12-single-creation-chokepoint.md` (the reopened
one-door design); `research/2026-07-13-database-storage-write-pipeline.md` §W4
(content/per-concern table layout); `models/rows.py:ENTRY_FIELD_HOMES` (the
existing model↔table seam). Refines the story-031 unified-Entry design
(one door per type, not one type); does not supersede any numbered ADR.
Neighbors ADR 004 (stable identity — every dependent table keys on the
integer surrogate, unchanged here) and ADR 013 (per-entry revisions — the
revision stays an `Entry`/`Edge` concern).
