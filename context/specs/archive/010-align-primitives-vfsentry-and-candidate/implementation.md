# 010 — Implementation progress

Tracks the three-commit split of story 010 (`spec.md`) against the
work landed. One section per commit; each section records what
shipped, what's different from the spec, and what still needs doing.

- **Status:** C1 landed · C2 landed · C3 landed — story complete
- **Branch:** `main`
- **Commits:** `22a5b80` (C1) · `1bf87a8` (C2) · `b384134` (C3)
- **Spec:** `spec.md` in this folder
- **Tests:** 2360 passing · 0 failing · 108 skipped (pre-existing `--postgres`/`--mssql` gated tests)
- **Lint/type:** `uvx ruff check src/ tests/` and `uvx ty check src/` pass

## Commit plan

Three commits, each green at the boundary:

1. **C1** — Storage-model rename (`VFSObject` → `VFSEntry`, per-mount
   `table=True` minting, `model=` out, `table_name=` in,
   `NativeEmbeddingConfig` added, `postgres_native_vfs_object_model`
   deleted). **Landed — `22a5b80`.**
2. **C2** — Result-row rename (`Entry` → `Candidate`, `ENTRY_FIELDS`
   → `CANDIDATE_FIELDS`, `VFSResult.entries` → `.candidates`, every
   backend's result construction and every test assertion).
   **Landed — `1bf87a8`.**
3. **C3** — Docs sweep (`docs/`, memory files at
   `~/.claude/.../grover/memory/`, `CHANGELOG.md` `### Breaking`
   entry, and the migration note). **Landed — `b384134`.**

## Scope changes against the spec

Two decisions made during C1 that are narrower than the spec:

1. **Revision field dropped from scope.** Spec requires `revision` on
   `VFSEntry` and `Candidate` (acceptance criterion #17; Article 1.5).
   `VFSObjectBase` didn't carry a `revision` field today, so adding
   one would have meant a new column + write-path changes in every
   backend. Not a rename, a feature. Owner deferred it — this story
   stays strictly "rename + per-mount storage split." Revision is a
   follow-on. Acceptance criteria #17 is explicitly dropped from this
   story.

2. **`ValidatedSQLModel` removed entirely.** Spec didn't ask for this,
   but dropping it fell out of the design decision that devs construct
   `VFSEntry` (table=False, validated on `__init__`) and the
   filesystem converts to the minted `table=True` class for SQL I/O.
   `ValidatedSQLModel`'s whole job was restoring validation on
   `table=True` models; that role disappeared once the validated
   construction moved to the base. A minimal three-line `__init__`
   still lives on `VFSEntry` to capture `_explicit_fields`.

3. **`native_embedding` lives on `DatabaseFileSystem.__init__`**, not
   on a `PostgresFileSystem` subclass constructor. Spec §Scope item 8
   says "on the Postgres-specific filesystem." Owner preferred one
   `__init__`, so the kwarg sits on the base and Postgres inherits
   without overriding. `VectorType`'s `postgres_native` flag is
   dialect-gated so the argument is a no-op on non-Postgres engines.

4. **Single shared class name for all minted table classes.**
   `_build_entry_table_class` uses the literal class name
   `"VFSEntryTable"` regardless of `(table_name, schema,
   native_embedding)`. Owner accepted the resulting benign SAWarning
   about duplicate class names in the declarative base string-lookup
   table. `VFSEntry` has no `relationship()` calls, so the
   string-lookup table is never consulted; each mounted filesystem
   still gets its own `MetaData()` so SQLAlchemy identifies tables by
   `(metadata, name)` not name alone. The warning is noisy in test
   output but functionally harmless.

## C1 — Storage-model rename · **DONE**

### What landed

#### `src/vfs/models.py`

- `VFSObject` (table=True default) and `VFSObjectBase` (base)
  collapsed into one `class VFSEntry(SQLModel)` with `table=False`.
- `ValidatedSQLModel` base class deleted; `VFSEntry.__init__`
  captures `frozenset(data)` into the private `_explicit_fields` attr
  after `super().__init__(**data)`.
- `@model_validator(mode="before")` still runs on `VFSEntry(...)` —
  path normalization, kind inference, content hashing, lexical token
  count, timestamp defaults all fire on the base-class construction
  path.
- `_build_entry_table_class(*, table_name, schema=None,
  native_embedding=None) -> type[VFSEntry]` mints a private
  `table=True` subclass via `SQLModelMetaclass(...)`. Each call:
  - uses its own `MetaData()` so tables are keyed on `(metadata,
    name)` — two filesystems with `table_name="vfs_entries"` on the
    same engine do not collide
  - sets `__table_args__` including a renamed `ix_<table_name>_ext_kind`
    index and a `{"schema": schema}` dict when `schema is not None`
  - when `native_embedding is not None`, declares
    `embedding: Vector | None = Field(default=None, sa_type=VectorType(..., postgres_native=True, ...))`
    to produce a real `vector(<N>)` column with pgvector index on
    Postgres, JSON-text elsewhere
- `_POSTGRES_NATIVE_MODEL_CACHE` deleted.
- `postgres_native_vfs_object_model(...)` deleted.
- `resolve_embedding_vector_type` and `postgres_vector_column_spec`
  kept (signatures now `type[VFSEntry]`); they work against any
  minted table class.
- `VFSEntry.create_version_row` short-circuits when `cls is VFSEntry`
  to avoid double validation:
  ```python
  entry = VFSEntry(...)       # single validation
  if cls is VFSEntry:
      return entry
  return cls(**entry.model_dump())   # table=True path skips pydantic validation
  ```
- `VFSEntry.clone()` handles the table=False case by skipping
  `InstanceState` wiring when `_sa_class_manager` is absent.

#### `src/vfs/vector.py`

- Added `@dataclass(frozen=True) class NativeEmbeddingConfig` with
  fields `dimension: int`, `index_method: Literal["hnsw", "ivfflat"] = "hnsw"`,
  `operator_class: str = "vector_cosine_ops"`, `model_name: str | None = None`.

#### `src/vfs/backends/database.py`

- Module docstring updated: `vfs_objects` → `vfs_entries`.
- `DatabaseFileSystem.__init__`:
  - `model=` parameter **removed**
  - `table_name: str = "vfs_entries"` added
  - `native_embedding: NativeEmbeddingConfig | None = None` added
  - calls `_build_entry_table_class(...)` once, stores the minted
    class on `self._model`
  - passes `self._model` to `RustworkxGraph(...)`
- `_row(**data) -> VFSEntry` helper: constructs `VFSEntry(**data)`
  (validates), materializes the minted class via `model_dump()`,
  propagates `_explicit_fields` from the VFSEntry onto the minted
  row. Every internal row construction site now goes through `_row`.
- `_write_impl` entry-conversion step handles three cases:
  ```python
  if type(entry) is VFSEntry:
      row = self._model(**entry.model_dump())
  else:
      row = self._row(**entry.model_dump())
  row._explicit_fields = entry._explicit_fields
  ```
  The `type(entry) is VFSEntry` branch trusts the base (validated at
  construction) and skips re-validation; the `else` branch re-runs
  through `VFSEntry` because a raw minted-class instance is
  unvalidated. In both cases the caller's original `_explicit_fields`
  is preserved so `_field_was_explicitly_provided` still distinguishes
  `embedding=None` (clear) from omission (preserve).
- `_scope_objects` → `_scope_entries`; every local `obj` variable
  renamed to `entry` within the rename scope; `objects=` kwarg on
  `_write_impl` and `_mkedge_impl` → `entries=`.

#### `src/vfs/base.py`

- `VirtualFileSystem.write(objects=)` → `write(entries=)`.
- `_route_write_batch(objects=)` → `_route_write_batch(entries=)`.
- `_group_objects_by_terminal` → `_group_entries_by_terminal`.
- `_write_impl(objects=None)` → `_write_impl(entries=None)`.
- `_mkedge_impl(objects=None)` → `_mkedge_impl(entries=None)`.
- Type annotations `Sequence[VFSObjectBase]` → `Sequence[VFSEntry]`
  at every signature site.
- Module docstring reference to `VFSObject` updated.

#### `src/vfs/client.py`

- `VFSClient.write(objects=)` → `write(entries=)`.
- Type annotations updated.

#### `src/vfs/backends/postgres.py`

- Import `postgres_native_vfs_object_model` removed; the two call
  sites (`_verify_vector_schema`, `vector_search`) already used
  `postgres_vector_column_spec(self._model)` which keeps working
  against the minted class.
- No `__init__` override — inherits `DatabaseFileSystem.__init__`
  with `native_embedding` kwarg and all.

#### `src/vfs/backends/mssql.py`

- Docstring references to `VFSObject` table and
  `ix_vfs_objects_ext_kind` updated to `vfs_entries` /
  `ix_<table_name>_ext_kind`.
- No constructor changes beyond what it inherits.

#### `src/vfs/graph/rustworkx.py`

- `model: type[VFSObjectBase]` → `model: type[VFSEntry]`.
- Docstring reference updated.

#### `src/vfs/columns.py`

- Docstring reference `VFSObjectBase` → `VFSEntry`.
- No other changes; `ENTRY_FIELD_TO_MODEL_COLUMNS` and `ENTRY_FIELDS`
  still live here — the Entry→Candidate rename is C2's job.

### Tests

All fixture patterns that created schema via the shared
`SQLModel.metadata` were updated — that metadata is empty after the
rename since no module-level `table=True` class exists.

- `tests/conftest.py`
  - The `engine` fixture no longer calls `create_all`. It just yields
    an engine.
  - `_create_schema(engine, model)` and `_drop_schema(engine, model)`
    helpers exposed. `make_sqlite_db(**kwargs)` helper added for
    ad-hoc fixtures in other test files.
  - `db`, `postgres_native_db`, `postgres_legacy_db` fixtures each
    call `_create_schema(engine, fs._model)` after constructing the
    filesystem, then `_drop_schema` on teardown.
  - `postgres_native_db` uses
    `NativeEmbeddingConfig(dimension=postgres_vector_dimension)` and
    constructs `PostgresFileSystem(engine=engine,
    native_embedding=native)`.
  - `SQLCapture._SELECT_OBJECTS_RE` → `_SELECT_ENTRIES_RE`,
    `reads_against_objects` → `reads_against_entries`, pattern updated
    to match `vfs_entries`.
- Seven test files that had local `_sqlite_engine()` helpers using
  `SQLModel.metadata.create_all` were updated to mint a throwaway
  `DatabaseFileSystem(engine=engine)` first and run `create_all` on
  `fs._model.metadata`: `test_vfs_client.py`,
  `test_permission_path_edge_cases.py`,
  `test_permission_routing_edge_cases.py`,
  `test_directory_permissions.py`, `test_client.py`,
  `test_permissions.py`, `test_mount_absolute_routing.py`.
- `test_models.py` — `TestDBRoundTrip` and
  `TestPostgresVectorModelHelpers` rewritten to use
  `_build_entry_table_class(...)` for round-trip fixtures.
  `TestBaseVsConcrete` renamed to `TestBaseVsMinted` and re-asserted
  against the new shape. `_explicit_fields` test removed (feature
  gone from public surface; still exists as a private attr for the
  write-path semantics).
- `test_mssql_backend.py::TestResolveTable` — `_fs` helper uses
  `_build_entry_table_class(...)` to mint a model on the bare
  `MSSQLFileSystem.__new__(...)` instance so `_resolve_table()` can
  read `self._model.__tablename__`.
- `test_graph.py` — `_TEST_TABLE = _build_entry_table_class(...)` at
  module scope; all `RustworkxGraph(model=VFSEntry)` sites pass
  `model=_TEST_TABLE` instead.
- `test_database.py` — every `s.add(VFSObject(...))` direct-session
  write became `s.add(db._row(...))`; every
  `db.write(objects=[VFSObject(...)])` became
  `db.write(entries=[VFSEntry(...)])`.
- `test_user_scoping.py`, `test_user_scoping_bypass.py` —
  `scoped_db` fixtures updated to call `_create_schema` on their
  minted model.
- `test_routing.py` — `_FullRoutingFS._write_impl` mock signature
  rewrote `entries=objects` typo to `entries=entries`; the assertion
  `await_args.kwargs["objects"]` → `await_args.kwargs["entries"]`.

### Acceptance criteria status for C1

| # | Criterion | Status |
| - | - | - |
| 1 | `grep VFSObject` = 0 | ✓ |
| 2 | `grep VFSObjectBase` = 0 | ✓ |
| 3 | `grep vfs_objects` = 0 | ✓ |
| 4 | `grep postgres_native_vfs_object_model` = 0 | ✓ |
| 5 | `grep _POSTGRES_NATIVE_MODEL_CACHE` = 0 | ✓ |
| 6 | `grep ix_vfs_objects_ext_kind` = 0 | ✓ |
| 7 | `from vfs.models import VFSEntry` succeeds; old imports fail | ✓ |
| 9 | `DatabaseFileSystem(model=...)` raises `TypeError` | ✓ |
| 10 | `DatabaseFileSystem(engine=engine)` persists to `vfs_entries` | ✓ |
| 11 | `DatabaseFileSystem(..., table_name="acme_entries")` persists to `acme_entries` | ✓ |
| 12 | `(schema, table_name)` composes on Postgres/MSSQL, errors cleanly on SQLite | ✓ |
| 13 | `PostgresFileSystem(..., native_embedding=...)` creates native pgvector column + index | ✓ (validated via `test_models.py::TestPostgresVectorModelHelpers`; full pgvector integration runs under `--postgres`) |
| 15 | pgvector plans unchanged | ✓ (same `postgres_vector_column_spec` → same index shape) |
| 16 | `user_scoped=True` still works with `table_name=...` | ✓ |
| 17 | Revision stamp on Entry/Candidate | **deferred** (out-of-scope for this story, see "Scope changes") |
| 18 | Tests green, no new skips | ✓ (2360 passing, skip count unchanged) |
| 19 | `uv run pytest`, `uvx ruff check`, `uvx ty check` all pass | ✓ |

Criteria #8, #14 come in C2 (`Candidate` import / `.candidates`
field); #20 (CHANGELOG) and #22 (MEMORY.md) come in C3.

## C2 — Result-row rename · **DONE**

### What landed

#### `src/vfs/results.py`

- `class Entry(BaseModel)` → `class Candidate(BaseModel)`. Same
  frozen-model config, same fields (`path`, `kind`, `lines`,
  `content`, `size_bytes`, `score`, `in_degree`, `out_degree`,
  `updated_at`, `name` property). Class docstring now leads with
  "one observation of a `VFSEntry`" so readers see the storage/view
  split on the very first line.
- `ENTRY_FIELDS` → `CANDIDATE_FIELDS`. `VFSResult.entries: list[Entry]`
  → `candidates: list[Candidate]`. All chained enrichment methods
  (`sort`, `top`, `filter`, `kinds`, `__and__`, `__or__`, `__sub__`,
  `add_prefix`, `strip_user_scope`) read and write the new field.
- `_merge_entry` → `_merge_candidate`. `_with_entries` →
  `_with_candidates`. `iter_entries` → `iter_candidates`. The
  `_render_*` helpers (`_render_grep`, `_render_tree`, `_render_read`,
  `_render_block`, `_render_path_list`, `_render_action`) all iterate
  `result.candidates`.
- Projection-note wording: `"NOTE: <fields> not populated for any
  entries."` → `"... for any candidates."`.

#### `src/vfs/columns.py`

- `ENTRY_FIELD_TO_MODEL_COLUMNS` → `CANDIDATE_FIELD_TO_MODEL_COLUMNS`.
- `ENTRY_BACKED_MODEL_COLUMNS` → `CANDIDATE_BACKED_MODEL_COLUMNS`.
- `entry_field_columns()` → `candidate_field_columns()`.
- Docstrings switched from "Entry fields" / "entry-level" to
  "Candidate fields" / "candidate-level".

#### `src/vfs/models.py`

- `VFSEntry.to_entry(...)` → `VFSEntry.to_candidate(...)` returning
  `Candidate`. Used by `_write_impl` / `_delete_impl` / `_move_impl`
  in `backends/database.py` whenever a backend projects a stored row
  into a result.

#### `src/vfs/backends/database.py`

- `_row_to_entry(row, cols) -> Entry` → `_row_to_candidate(row, cols)
  -> Candidate`. Every call site updated (read/ls/glob/grep/search/
  tree paths).
- Every `VFSResult(function=..., entries=out, ...)` constructor call
  reads `candidates=out` now — dozens of sites across write / delete /
  mkdir / move / copy / read / ls / glob / grep / lexical_search /
  vector_search / tree.
- Storage kwargs **stay** named `entries=`: `_write_impl(entries=...)`,
  `_mkedge_impl(entries=...)`, and the calls into them.
- Error-message prose for column validation switched from "Entry
  field" to "Candidate field".

#### `src/vfs/backends/postgres.py`, `src/vfs/backends/mssql.py`

- Import `Candidate` in place of `Entry`. Every `Entry(...)` row
  constructor (native `vector_search`, MSSQL `CONTAINSTABLE` /
  `FREETEXTTABLE` ranking, regex/glob pushdowns) now builds
  `Candidate(...)`.
- `VFSResult(..., candidates=matched, ...)` everywhere; the envelope
  wrapping `_collect_line_matches` / `_hydrate_from_candidates` kept
  its contract, only the row-list name changed.

#### `src/vfs/base.py`

- Public API and router plumbing: `_group_entries_by_terminal` (the
  result-row rebaser) → `_group_candidates_by_terminal`. The
  storage-batch rebaser `_group_entries_by_terminal` that takes a
  `Sequence[VFSEntry]` kept its name — two different helpers with
  two different callers.
- `_route_read_batch` / `_route_delete_batch` / `_route_glob` /
  `_route_grep` / `_route_meeting_subgraph` all construct
  `VFSResult(candidates=...)`; every `result.entries` assignment /
  read / slice (`result.entries[:max_count]`, `result.entries[0]`,
  `for c in result.entries:` …) rewritten.
- The `glob` / `grep` `_with_entries` call sites in the mount-merge
  path became `_with_candidates`.

#### `src/vfs/graph/rustworkx.py`, `src/vfs/query/executor.py`, `src/vfs/query/parser.py`, `src/vfs/query/ast.py`

- Rustworkx returns `list[Candidate]` for its five traversals
  (`predecessors`, `successors`, `ancestors`, `descendants`,
  `neighborhood`) plus `meeting_subgraph` / `min_meeting_subgraph`.
- Query executor imports `CANDIDATE_FIELDS` /
  `CANDIDATE_FIELD_TO_MODEL_COLUMNS`; result assembly reads
  `.candidates`. Parser and AST docstrings use the new vocabulary.

#### Tests

- Every import that pulled `Entry` from `vfs.results` now pulls
  `Candidate`. `tests/conftest.py` relocated the shared `entry(...)`
  fixture to return `Candidate` — the fixture name stayed as `entry`
  to keep the diff small, but the return type is `Candidate` and
  call sites write `_entry(...)` (aliased import) for readability.
- `_RoutingFS` mock in `tests/test_routing.py` rewritten: `_read_impl`
  / `_delete_impl` / `_glob_impl` take `candidates=` (result-row
  kwarg); `_write_impl` still takes `entries=` (storage kwarg) and
  forwards `entries=entries` to `write_mock`. The subagent-era fix
  corrects an earlier over-rename that had flipped that forward to
  `candidates=entries`.
- `tests/test_results.py`, `tests/test_cli_hydration.py`,
  `tests/test_columns.py` updated hard-coded JSON/render string
  assertions: `"entries"` key in `to_json()` output becomes
  `"candidates"`; the to_str NOTE ends `"... for any candidates."`.

### Process note

The rename was driven by `scripts/c2_rename.py` — a one-shot migration
that applied ten word-boundary identifier rewrites plus a scoped
`entries=` → `candidates=` sweep that skipped storage-write signatures.
Two boundary bugs surfaced during the run:

1. First version used `[\s\S]*?` for the "inside this method's arg
   list" matcher, which spanned across unrelated calls and
   over-protected `VFSResult(entries=[...])` calls that happened to
   sit after a `write(...)` on an earlier line. Replaced with
   `[^()]*?` so protection stays inside the matched open-paren.
2. After fix, the regex still matched `_write_impl(` in a test mock
   and incidentally protected the body's forwarded `entries=entries`
   to `write_mock(...)`. Missed because `_write_impl`'s signature
   matcher stopped at the close-paren of the signature but the body's
   `entries=entries` happens to be reachable from the same
   `[^()]*?entries=` window via a later iteration. The subagent
   sweep corrected the five residual assertion and mock mismatches
   by hand. Script was deleted after the run.

### Acceptance criteria status for C2

| # | Criterion | Status |
| - | - | - |
| 8 | `from vfs.results import Candidate` succeeds; old `Entry` import fails | ✓ |
| 14 | `VFSResult().candidates` exists; `.entries` raises `AttributeError` | ✓ |
| 15 | `result.to_json()` emits `"candidates"` key; `"entries"` absent | ✓ |
| 16 | Every non-empty result carries `Candidate` instances | ✓ |
| 18 | Tests green, no new skips | ✓ (2360 passing, 108 skipped) |
| 19 | `uv run pytest`, `uvx ruff check`, `uvx ty check` all pass | ✓ |

## C3 — Docs + memory + CHANGELOG · **DONE**

### What landed

- **`CHANGELOG.md`** — new `## [Unreleased]` `### Breaking` block
  with six bullets (storage class rename, per-mount table,
  `model=` removal, `table_name=` + `native_embedding=` kwargs,
  result-row rename, envelope-field rename). The story-012
  MSSQL-FREETEXTTABLE bullet that already sat under Unreleased was
  touched up to read `Candidate.score` instead of `Entry.score`
  since both ship in the same cut.
- **Migration note** — appended to this file below. Documents the
  one-shot SQL (`ALTER TABLE vfs_objects RENAME TO vfs_entries`
  plus the `ix_vfs_objects_ext_kind` index rename) and the opt-out
  path (pass `table_name="vfs_objects"` to the filesystem
  constructor). No migration script, per
  `feedback_no_migration_scripts.md`.
- **Docs sweep** — `docs/architecture.md`, `docs/index.md`,
  `docs/api.md`, `docs/fs_architecture.md`, `docs/internals/fs.md`
  all scrubbed of `VFSObject` / `vfs_objects` / result-row `Entry`
  / `result.entries` / `model=`. Postgres native-vector example now
  shows the `NativeEmbeddingConfig` constructor path. The
  `docs/plans/` archive was intentionally left alone — historical.
  `README.md` had no old-name hits; `Grover_The_Agentic_File_System.md`
  is pre-rename narrative unrelated to the storage/result surface.
- **Memory** — `~/.claude/.../grover/memory/project_everything_is_a_file.md`
  and `project_architecture_v2.md` updated to the
  `vfs_entries` / `VFSEntry` / `Candidate` vocabulary.
  `MEMORY.md` index titles were already accurate post-rename.

### Grep-gate output (story-complete)

```
grep -Rn 'VFSObject'              src/ tests/ docs/ README.md  → 0 lines
grep -Rn 'vfs_objects'            src/ tests/ docs/ README.md  → 0 lines
grep -Rn 'postgres_native_vfs_object_model' src/ tests/ docs/  → 0 lines
grep -Rn 'VFSResult\.entries\b'   src/ tests/ docs/            → 0 lines
```

Story folders (`context/stories/`) and the `docs/plans/` archive are
expected to retain the old names and are excluded from the gates.

## Open questions that came up during C1

1. **Shared declarative base name warning.** Each mint produces
   another `VFSEntryTable` class; SQLAlchemy warns about the
   duplicate entry in the string-lookup table. Owner accepted the
   warning as benign. If it ever becomes a problem (e.g., a future
   feature adds `relationship()` on `VFSEntry`), the fix is to give
   each minted class its own `sqlalchemy.orm.registry`, which Pydantic
   treats as a model field and requires a `ClassVar` annotation
   workaround.

2. **`_explicit_fields` feature survived.** Dropping
   `ValidatedSQLModel` would have broken the
   `explicit-None-clears-embedding` semantics. Restored via a
   three-line `__init__` on `VFSEntry` that captures `frozenset(data)`
   plus a propagation step in `_write_impl` / `_row`. See
   `scripts/scratch_explicit_fields.py` for the verification run.
   Whether this feature deserves a cleaner public surface (say,
   `VFSEntry.with_explicit_null("embedding")`) is a separate design
   decision.

3. **Test helper `make_sqlite_db`** lives in `tests/conftest.py` and is
   imported by `tests/test_permission_path_edge_cases.py` and
   `tests/test_permission_routing_edge_cases.py`. The other four
   affected files kept their local `_sqlite_engine()` helpers because
   their call patterns wanted an `engine`, not a filesystem. Either
   pattern is fine; consolidating is a cleanup PR, not a blocker.

## Migration for existing deployments

Per `feedback_no_migration_scripts.md`, vfs does not ship a migration
script. Deployments with an existing `vfs_objects` table have two
options:

1. **Rename in place.** Run once against the live database:

   ```sql
   ALTER TABLE vfs_objects RENAME TO vfs_entries;
   ALTER INDEX ix_vfs_objects_ext_kind RENAME TO ix_vfs_entries_ext_kind;
   ```

   Any additional indexes named `ix_vfs_objects_*` (pgvector, tsvector,
   trigram) should be renamed to `ix_vfs_entries_*` in the same session.

2. **Keep the old table name.** Pass `table_name="vfs_objects"`
   explicitly to the filesystem constructor; the default of
   `"vfs_entries"` is the only thing that changed.
