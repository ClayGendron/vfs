# 076 — plan

Approach: paths first (the grammar is the deepest dependency), then the
model split, then the minimal consumer edits, then tests. Each step
compiles against the previous one; the tree is green only at the end of
the pass, but every edit is committed as one landing.

## Resolutions the spec defers to plan.md

- **Chunk drops `name` and `version_number`.** Pin 4's field list names
  both, but the acceptance criteria pin "no `path`/`name` field" and a
  per-model column drift check, and the `chunks` table has neither
  column. Both fields were namespace-projection artifacts: the
  `<start>_<end>@<offset>` name existed to keep directory leaves unique
  (identity is now `(owner, chunk_index)` — uniqueness is free), and the
  version segment existed only in the retired path grammar. The naming/
  disambiguation logic retires with them; `split_content` moves whole.
- **Edge keeps `revision` as a declared model-only field.** ADR 013
  names revision an `Entry`/`Edge` concern, but the `edges` table has no
  revision column and this spec makes no schema change. The drift test
  carries an explicit model-only exemption set; `Edge.revision` sits in
  it with the wiring spec named as the resolver.
- **Edge endpoint fields are `source`/`target`** (pin 5 says
  `source_file`/`target_file` — the old computed-field names). The
  models mirror their tables; `source_id`/`target_id` argue for the
  short names, as does pin 8's own identity triple `(source, target,
  edge_type)`.
- **`check_mutable_path` reduces to root + `/.vfs` root.** Its
  chunk/version/edge arms, the inverse-edge refusal, and the
  reserved-skeleton allowance are all metadata-family validation (pin
  9). What remains: `/` and `/.vfs` are not write targets; everything
  else is grammar-mutable (ADR 014 pin 2: ingress admits trash paths
  under the ordinary grammar). The `kind` parameter goes.
- **`parse_kind` special cases after the collapse:** `/.vfs` itself and
  the `/.agents` skeleton (root, family roots, unit directories)
  classify `directory` — their dotted/extensionless names must not fall
  into the name lottery; everything else, including everything deeper
  under `/.vfs`, takes the ordinary file/directory rules.
  `AGENT_FAMILY_TO_KIND` is replaced by a family-name set (the "tool"/
  "skill" strings stop being kinds); the full tool/skill helper
  relocation stays deferred per Out of scope.
- **Structural-directory refusal survives in `Entry`.** The old rule
  "content under a reserved path raises instead of reclassifying to
  file" keyed off `_CONTENT_FREE_KINDS` and `is_meta_path`. It becomes a
  path predicate: a new `paths.is_reserved_directory` (root, `/.vfs`
  root, `/.agents` skeleton) guards the reclassify-to-file arm. Content
  elsewhere under `/.vfs` (trash-side paths) reclassifies like any
  ordinary path — the 075 parity posture.
- **`base.py` `mkedge` validates through the Edge model.** Endpoint
  eligibility and edge-type lawfulness live on `Edge` (pin 5); base
  constructs `Edge(source=..., target=..., edge_type=...)` and maps
  `ValidationError` to `invalid`. Permission gating moves from the two
  retired projection paths to the two endpoint paths (an edge write
  mutates both endpoints' metadata sets).
- **Memory `mkedge` stores edges off-namespace**: an internal
  `dict[(source, target, edge_type), revision]`. The observation row is
  the *source* path with `edge_type` populated and created/updated
  status — no derived path, no `kind="edge"`. Endpoint liveness checks
  stay; delete/move do not yet cascade into the edge dict (dormant
  machinery, deferred with the rest of the wiring).

## 1. `paths.py`

- Retire: `META_SEGMENT`, `EDGE_DIRECTIONS`/`EDGE_DIRECTION_SET`,
  `chunk_path`, `version_path`, `edge_out_path`/`edge_in_path`,
  `validate_edge_endpoint`, `decompose_edge`, `EdgeParts`,
  `compute_parent_file`, and the internal grammar layer
  (`_meta_grammar_reason`, `_split_edge_path`, `_EdgePathParts`,
  `_split_nested_endpoint`, `_canonical_endpoint_path`,
  `_is_reserved_metadata_directory`, `_meta_family_tail`,
  `_is_projected_edge_path`, `_reject_embedded_meta_segment`,
  `_validate_file_base`, `_validate_version`).
- `ObjectKind = Literal["file", "directory"]`.
- `Path` loses `parent_file`/`source_file`/`target_file`; `ext` stops
  kind-gating (`extract_extension` for every path).
- `validate_path` drops the nested-`__meta__` and meta-grammar checks.
- `_validate_name` promotes to public `validate_segment` (used by the
  tool/skill builders and the `Edge` model).
- New `is_reserved_directory(path)` predicate; `_agent_namespace_kind`
  returns `directory` for skeleton spots.
- Module docstring/examples rewritten (no `__meta__` grammar).

## 2. Models

- **`models/chunk.py`** — `Chunk(owner: Path, chunk_index, line_start,
  line_end, content, content_hash, encoded=False, embedding=None)`;
  null-byte + hash-measure validators; `Chunk.split(owner, content,
  ext) -> list[Chunk]` absorbs `split_content` dispatch and index
  enumeration.
- **`models/version.py`** — `Version(owner: Path, version_number,
  is_snapshot, content, version_diff, content_hash, lines, size_bytes,
  created_by, created_at)`; not-both-payloads and null-byte validators;
  metrics always explicit (of the full content), never re-measured.
  `Version.create(...)` absorbs `create_version_row`;
  `stored_payload()` and `Version.reconstruct(rows, target)` absorb the
  payload/reconstruction pair over `versioning.py`, hash check included.
- **`models/edge.py`** — `Edge(source: Path, target: Path, edge_type,
  weight=None, distance=None, revision=1)`; validators: endpoints
  distinct from root/`/.vfs` space, `edge_type` a lawful segment.
- **`entry.py`** — `Entry` narrows per pin 1; validators shed the
  kind-dispatch arms; `ext` derives for every kind from the path;
  factories `chunk() -> list[Chunk]` and `create_version(previous:
  Entry | None, *, version_number, created_by, force_snapshot=False) ->
  Version` delegate. `with_version`, `create_version_row`,
  `_stored_version_payload`, `_reconstruct_file_version`,
  `split_content`, and the old `chunk()` body leave. `to_observation`
  populates only Entry-owned mirrors.
- **Mirror ownership** — `OBSERVATION_MIRROR_OWNERS: dict[field,
  (model, field)]` beside `Observation` (`version_number` → `Version`;
  `edge_type`/`edge_weight` → `Edge.edge_type`/`.weight`;
  `edge_distance` → `Edge.distance`; the rest → `Entry`), with
  `ENTRY_OWNED_MIRRORS` derived. `models/__init__` exports `Chunk`,
  `Version`, `Edge`, and the maps.

## 3. `rows.py`

- `ENTRY_FIELD_HOMES` dissolves. Per-table constants replace it:
  row-only column sets (`entry`: + `version_number`; `chunks`: `id`,
  `entry_id`; `versions`: `entry_id`; `edges`: `id`, `source_id`,
  `target_id`), an owner-reference map (model owner field → id column),
  and the model-only exemption (`Edge.revision`).
- Module docstring updates (model-per-table, no homes map).

## 4. Consumers

- `skills.py`: unit directory becomes `kind="directory"`; docstrings.
- `memory.py`: `_Row` loses `edge_type`; `mkedge` per the resolution
  above; the meta-ancestor minting note goes.
- `base.py` `mkedge`: Edge-model validation + endpoint-path gating.
- `render.py`: `_WRITE_SUMMARY_KINDS = ("file", "directory")`;
  docstrings drop chunk/edge/version language.
- `reads.py`/`writes.py`: `CONTENT_KINDS` unchanged (stored-kind
  strings at the row layer) — confirmed, not widened.

## 5. Tests

- `test_paths.py`: delete the `__meta__` grammar families (builders,
  decompose, parse_kind meta branches, meta mutability arms, edge
  splitting); rewrite `check_mutable_path` and kind-inference pins to
  the collapsed contract; add `is_reserved_directory` and
  directory-`ext` pins.
- `test_models.py`: version/chunk families move to `Version`/`Chunk`
  with the call surface changed and behavior pins kept (snapshot-vs-
  diff, no re-measure, reconstruction + hash check, split dispatch);
  new `Edge` validation family; Entry narrowing pins (dropped fields
  refused, directory `ext`, factories delegate).
- `test_rows.py`: drift test walks the four per-model maps.
- `test_skills.py`: unit directory expectation `kind="directory"`.
- `storage_conformance.py` + `test_backends_memory.py`: mkedge family
  rewritten to the off-namespace contract; edge-path tests deleted.
- `test_backends_database.py`: seeds/writes using `kind="version"` and
  `__meta__` paths move to plain files under `/.vfs`.
- `test_render.py`: write-summary vocabulary; `test_projection.py`
  unaffected (Observation fields unchanged).
- Full suite green; `ruff`/`ty` zero.
