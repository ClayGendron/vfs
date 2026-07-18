# 076 — Entry model split: Entry + Chunk + Version + Edge

- **Status:** shaped — drafted 2026-07-18 from accepted ADRs 015 and 016;
  no open markers. Ready for plan.md.
- **Date:** 2026-07-18
- **Owner:** Clay Gendron
- **Kind:** domain-model refactor (split one kinded `Entry` into four
  models; narrow `ObjectKind` to `file | directory`; retire `tool`/`skill`
  kinds; take chunks/versions/edges off the namespace — no `path`, retire the
  `__meta__` grammar; reshape the model↔table drift test). No schema change —
  the table family already keys on owner + discriminator.
- **Depends on:** ADR 015 (the model split, binding); ADR 016 (chunks/
  versions/edges leave the namespace — entry-scoped metadata, binding); ADR
  004 (stable identity — every dependent table keys on the integer surrogate,
  preserved); ADR 013 / spec 074 (per-entry revisions — the revision stays an
  `Entry`/`Edge` concern)
- **Relates to:** ADR 014 (trash keeps `/.vfs` as its scope — untouched
  here); the future interface spec that adds the `versions`/`chunks`/`edges`
  verbs (this spec removes the path grammar but does not add the verbs); the
  future write/read wiring that persists `Chunk`/`Version`/`Edge` (dormant
  here); the storage conformance suite (both backends must observe identically)

## Intent

`models/entry.py` carries one `Entry` whose `kind` ranges over seven values
and whose fields are the union of every kind's needs — ~20 nullable columns
gated by runtime `kind`-dispatch. Meanwhile persistence is already a table
family (`entry`, `content`, `versions`, `chunks`, `edges`), and
`rows.py:ENTRY_FIELD_HOMES` hand-maps each off-`entry` field to its home
table. ADR 015 resolves the divergence: make the domain models mirror the
tables one-to-one.

This spec executes ADRs 015 and 016 against the **domain-model and path
layers**. `Entry` narrows to file-or-directory; `Chunk`, `Version`, `Edge`
become standalone models owning the construction logic that was dormant on
`Entry`, and — per ADR 016 — carry **no `path`**: they are addressed by owner
entry + discriminator, so the `__meta__` per-file metadata grammar retires
from `paths.py`. `tool`/`skill` stop being kinds; `Observation` stays one
masked type with a per-owner drift check. The write/read/memory/render
*wiring* to the new models is deliberately out of scope — the chunk/version/
edge machinery has no live caller today and stays that way here; the tree
stays green by the smallest consumer edits the narrowed vocabulary and the
retired grammar force. The `versions`/`chunks`/`edges` *verbs* that will
expose this metadata (ADR 016 pin 4) are a future interface spec, not this one.

One sentence: **each model is the single door for one table's rows — `Entry`
for file/directory (path is identity), `Chunk`/`Version`/`Edge` for their own
tables (owner + discriminator is identity, no namespace path) — and an
`Entry` can still mint the `Chunk`s and `Version` that relate to it through
thin factories that delegate, never a second door.**

## Shape (pinned)

1. **`Entry` covers `file` and `directory` only.** It keeps: identity
   (`path`, `name`, `kind`, `external_id`), shared body/metrics (`content`,
   `content_hash`, `mime_type`, `ext`, `lines`, `size_bytes`), index flags
   (`chunked`, `encoded`), `revision`, `owner_id`, and timestamps
   (`created_at`, `updated_at`, `deleted_at`), plus the `parent_dir`
   computed field. It **loses** `version_diff`, `version_number`,
   `is_snapshot`, `created_by`, `line_start`, `line_end`, `edge_type`,
   `edge_weight`, `edge_distance`, `embedding`, and the
   `parent_file`/`source_file`/`target_file` computed fields. Its validators
   shed the edge-type derivation and the version-metrics carve-out;
   `_reject_null_bytes` guards `content` only (`version_diff` is gone from
   the model).

2. **`ext` is derived for directories too.** Derivation keys off the path,
   not `kind == "file"`: `foo.bar/` carries `ext = "bar"` (POSIX parity,
   ADR 015 pin 5). Content invariants otherwise unchanged — a directory
   carries no content; a file defaults to `""`.

3. **`Version` is a standalone model over `versions`.** Fields track the
   table: owner file path, `version_number`, `is_snapshot`,
   `content`/`version_diff`, `content_hash`, `lines`, `size_bytes`,
   `created_by`, `created_at`. It absorbs from `Entry`:
   `create_version_row` → `Version.create(...)`; `_stored_version_payload`
   and `_reconstruct_file_version` → `Version` methods over `versioning.py`
   (snapshot-vs-diff, forward-diff replay, the write- and read-side hash
   checks). The version-metrics carve-out (a diff row must not re-measure its
   stored payload) lives inside `Version` now, not `Entry`.

4. **`Chunk` is a standalone model over `chunks`.** Fields: owner file path,
   `chunk_index`, `name`, `line_start`, `line_end`, `content`,
   `content_hash`, `version_number`, `embedding`, `encoded`. It absorbs
   `split_content` and the naming/`@<offset>` disambiguation from `Entry.chunk`.

5. **`Edge` is a standalone model over `edges`.** Fields: `source_file`,
   `target_file`, `edge_type`, `weight`, `distance`, `revision`. It absorbs
   `edge_type` derivation from the path grammar and the source/target
   endpoint resolution (the retired `source_file`/`target_file` computed
   fields).

6. **Ergonomic factories stay on `Entry`, delegating.**
   `Entry.chunk() -> list[Chunk]` and `Entry.create_version(previous: Entry,
   ...) -> Version` remain, so a caller holding one entry mints its related
   rows in one call. They marshal the entry's content/derived state and hand
   off to `Chunk`/`Version` construction — no invariant is re-implemented on
   `Entry` (ADR 015 pins 3–4). `create_version` sources `prev_content` from
   `previous.content`; how the next `version_number` is chosen is a
   plan-level detail (a parameter for now, not a lookup — `Entry` holds no
   session).

7. **`tool`/`skill` stop being kinds.** `ObjectKind` narrows to
   `Literal["file", "directory"]`. `_CONTENT_FREE_KINDS` collapses to
   `{"directory"}`. `skills.py` keeps its builders (a skill's unit directory
   becomes `kind="directory"`, its `SKILL.md` a `file`) and its discovery
   moves to path predicates under `/.agents`, never a `kind` check.

8. **`Chunk`/`Version`/`Edge` carry no namespace path (ADR 016).** Their
   identity is owner + discriminator, exactly the row PKs: a `Chunk` is
   `(owner, chunk_index)`, a `Version` is `(owner, version_number)`, an `Edge`
   is `(source, target, edge_type)`. The domain model references its owner
   file by that owner's `Path` (a reference, not the metadata's own address);
   it has no `path`/`name` field and is never placed in the namespace.

9. **The `__meta__` per-file metadata grammar retires from `paths.py`
   (ADR 016).** `META_SEGMENT`, `chunk_path`, `version_path`,
   `edge_out_path`/`edge_in_path`, `decompose_edge`, `compute_parent_file`,
   the chunk/version/edge branches of `parse_kind`, and the metadata-family
   validation (`validate_edge_endpoint`, nested-`__meta__` refusal,
   family-tail parsing) leave the module. `ObjectKind` and the path-role
   vocabulary collapse to `Literal["file", "directory"]` — no five-value
   role enum is needed once the metadata families are off the namespace.
   `METADATA_ROOT` (`/.vfs`) **stays**: it remains the meta scope hosting
   `/.vfs/trash` (ADR 014) and mount metadata — untouched. Extent is bounded
   by the green-tree rule: a helper still called by a live consumer (memory
   backend edges, `skills.py`) is retired only as that consumer moves to
   owner + discriminator; any helper that would strand a live feature is
   resolved in plan.md (retire-now vs immediate follow-up), never left as
   dead-but-referenced.

10. **`Observation` stays one masked model; drift pins per owner.**
   `Observation` remains the single partial return row for every read. Its
   mirror fields now mirror whichever model owns each field —
   `version_number` → `Version`, `edge_*` → `Edge`, the rest → `Entry` — and
   the drift test pins each mirror to its owning model rather than to `Entry`
   alone. `ENTRY_FIELD_HOMES` dissolves: each model maps to exactly one
   table, so the cross-table homes map becomes four per-model column checks.

11. **Green tree by minimal consumer edits, not by wiring.** The narrowed
    vocabulary breaks a few live consumers; each gets the smallest change to
    compile and pass, with real re-modeling deferred: `skills.py` (pin 7),
    the memory backend's internal edge row (`memory.py` — its `_Row` edge
    representation adjusts to the narrowed `ObjectKind`; full `Edge`-model
    adoption in memory is deferred), `results/render.py`
    (`_WRITE_SUMMARY_KINDS` drops `chunk`/`edge` or moves to the new
    vocabulary), and `reads.py`/`writes.py` `CONTENT_KINDS` (still
    `{"file", "chunk", "version"}` as *stored-kind strings* at the row layer,
    unaffected by the domain `ObjectKind` narrowing — confirm, don't widen).

## Acceptance criteria

- `models/entry.py` defines `Entry` with `kind: Literal["file",
  "directory"]` and none of the ten dropped fields or three dropped computed
  fields; `Chunk`, `Version`, `Edge` exist as standalone models in their own
  modules and are exported from `models/__init__`.
- `Entry.chunk()` returns `list[Chunk]`; `Entry.create_version(previous)`
  returns a `Version`; both delegate — the chunk-naming and snapshot-vs-diff
  logic lives on `Chunk`/`Version`, and grepping `entry.py` finds no
  `split_notebook`/`compute_diff`/`reconstruct_version` call except through
  the new models.
- Version round-trips match today: a diff row's stored payload is its diff
  (not re-measured), and reconstruct-from-snapshot+diffs reproduces content
  with the hash check — the tests that covered `Entry`'s version methods pass
  against `Version` with only the call surface changed.
- A directory whose path carries an extension observes `ext` set
  (`Entry(path="/a/foo.bar", kind="directory").ext == "bar"`); a file is
  unchanged.
- `ObjectKind == Literal["file", "directory"]`; the strings `"tool"` and
  `"skill"` appear in `src/` only as path-semantic conventions
  (path segments, discovery predicates), never as a `kind` value or an
  `ObjectKind` member; `skills.py` constructs directories/files.
- The `rows.py` drift test pins `Entry`↔`entry`, `Version`↔`versions`,
  `Chunk`↔`chunks`, `Edge`↔`edges` columns per model; `Observation` mirrors
  resolve to the owning model. No test references `ENTRY_FIELD_HOMES` as a
  single cross-table map.
- `Chunk`/`Version`/`Edge` have no `path`/`name` field; they are constructed
  from an owner `Path` + discriminator. `META_SEGMENT`, `chunk_path`,
  `version_path`, `edge_out_path`/`edge_in_path`, `decompose_edge`, and
  `compute_parent_file` no longer exist in `paths.py`; `parse_kind` returns
  only `file`/`directory`. `METADATA_ROOT` and the `/.vfs/trash` scope are
  unchanged — the trash tests (ADR 014) pass untouched.
- Full suite green; `ruff` and `ty` at zero across `src/` and `tests/`.

## Out of scope

- **Persisting `Chunk`/`Version`/`Edge` through the write/read pipeline.**
  `writes.py`/`reads.py`/`staging.py` still write and read `entry`+`content`
  only; the version/chunk/edge tables stay dormant exactly as today. Wiring
  them is a future spec.
- **The `versions`/`chunks`/`edges` verbs** that expose the now-namespaceless
  metadata to callers (ADR 016 pin 4) — a future interface spec. This spec
  removes the path grammar; it does not add the retrieval verbs.
- **Residual `paths.py` cleanup beyond the `__meta__` removal** — retiring
  `AGENT_FAMILY_TO_KIND` and relocating tool/skill helpers to a discovery
  module (ADR 015 pin 6). The metadata-family grammar goes here (pin 9); the
  tool/skill helper reshuffle can trail.
- **Modeling edges in the memory backend as `Edge`.** The memory backend's
  internal representation gets the minimal green-tree edit to drop edge paths;
  adopting the `Edge` model there is deferred with the rest of the wiring.
- **Unifying `versions.version_number` with `revision`** — noted in spec 074
  as a possible future alignment, untouched here.
- **`File`/`Directory` subclasses** — considered and rejected in ADR 015
  (option b); revisiting is a new ADR, not this spec.

Evidence: `decisions/015-entry-chunk-version-edge-split.md` and
`decisions/016-metadata-off-the-namespace.md` (both binding);
`research/2026-07-18-metadata-namespace-vs-verbs.md` (the five-facet survey
behind ADR 016); `research/2026-06-12-single-creation-chokepoint.md` (the
one-door design this refines);
`research/2026-07-13-database-storage-write-pipeline.md` §W4 (the per-concern
table layout the models now mirror); `models/rows.py` (`ENTRY_FIELD_HOMES`,
the seam being dissolved into per-model maps).
