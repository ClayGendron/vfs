# 010 — Implementation progress

Tracks the three-commit split of story 010 (`spec.md`) against the
work landed. One section per commit; each section records what
shipped, what's different from the spec, and what still needs doing.

- **Status:** C1 landed · C2 pending · C3 pending
- **Branch:** `main` (local, uncommitted)
- **Spec:** `spec.md` in this folder
- **Tests:** 2360 passing · 0 failing · 108 skipped (pre-existing `--postgres`/`--mssql` gated tests)
- **Lint/type:** `uvx ruff check src/ tests/` and `uvx ty check src/` pass

## Commit plan

Three commits inside one PR, each green at the boundary:

1. **C1** — Storage-model rename (`VFSObject` → `VFSEntry`, per-mount
   `table=True` minting, `model=` out, `table_name=` in,
   `NativeEmbeddingConfig` added, `postgres_native_vfs_object_model`
   deleted). **Done.**
2. **C2** — Result-row rename (`Entry` → `Candidate`, `ENTRY_FIELDS`
   → `CANDIDATE_FIELDS`, `VFSResult.entries` → `.candidates`, every
   backend's result construction and every test assertion). **Pending.**
3. **C3** — Docs sweep (`docs/`, `README.md`,
   `Grover_The_Agentic_File_System.md`, `examples/`), memory files at
   `~/.claude/.../grover/memory/`, `CHANGELOG.md` `### Breaking`
   entry, and the migration note. **Pending.**

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

## C2 — Result-row rename · **PENDING**

Expected file set:
- `src/vfs/results.py` — `Entry` class → `Candidate`; `ENTRY_FIELDS`
  → `CANDIDATE_FIELDS`; `VFSResult.entries` → `.candidates`; all
  `.entries` property references in `sort`, `top`, `filter`,
  `kinds`, `__and__`, `__or__`, `__sub__`, `_merge_entry` →
  `_merge_candidate`, `add_prefix`, `strip_user_scope`,
  `to_json`, `to_str`.
- `src/vfs/columns.py` — `ENTRY_FIELD_TO_MODEL_COLUMNS` →
  `CANDIDATE_FIELD_TO_MODEL_COLUMNS`; `ENTRY_BACKED_MODEL_COLUMNS`
  → `CANDIDATE_BACKED_MODEL_COLUMNS`; `entry_field_columns` →
  `candidate_field_columns`; docstring vocabulary sweep.
- `src/vfs/models.py` — `VFSEntry.to_entry(...)` method returning an
  `Entry` row → rename to `VFSEntry.to_candidate(...)` returning a
  `Candidate`.
- `src/vfs/base.py`, `src/vfs/backends/database.py`,
  `src/vfs/backends/postgres.py`, `src/vfs/backends/mssql.py`,
  `src/vfs/graph/rustworkx.py`, `src/vfs/query/executor.py`,
  `src/vfs/query/parser.py`, `src/vfs/query/render.py`,
  `src/vfs/versioning.py`, `src/vfs/replace.py` — every
  `result.entries`, `VFSResult(entries=...)`, `.to_entry()`,
  `list[Entry]`, `Entry(...)` construction, `ENTRY_FIELDS` import.
- Every test file — `result.entries` assertions → `.candidates`,
  `entries=[...]` kwargs in `VFSResult(...)` construction → either
  `candidates=[...]` or use the positional / field-name the fixture
  expects, `Entry(...)` row construction → `Candidate(...)`.
- Projection validator messages — "Entry field" → "Candidate field".

Grep gate targets for C2 sign-off:
- `grep -rn '\bEntry\b' src/ tests/` returns only `VFSEntry`
  references (Entry-as-row is gone).
- `grep -rn 'ENTRY_FIELDS\|ENTRY_BACKED_MODEL_COLUMNS' src/ tests/`
  returns zero.
- `grep -rn '\.entries\b' src/ tests/` returns zero in
  `VFSResult`-context (pytest method names like `test_entries_*`
  are allowed but shouldn't exist — rename them too).

## C3 — Docs + memory + CHANGELOG · **PENDING**

- `CHANGELOG.md` — add `### Breaking` entry under `Unreleased`
  linking to `spec.md`, enumerating the three renames plus the
  storage-shape constructor change and the result envelope field
  rename.
- Migration note — short `migration.md` or appended section in
  `implementation.md` describing the one-shot SQL rename users run if
  they want to preserve an existing `vfs_objects` table:
  ```sql
  ALTER TABLE vfs_objects RENAME TO vfs_entries;
  ALTER INDEX ix_vfs_objects_ext_kind RENAME TO ix_vfs_entries_ext_kind;
  -- ... any pgvector / tsvector / trigram indexes named ix_vfs_objects_*
  ```
- `docs/architecture.md`, `docs/index.md`, `README.md`,
  `Grover_The_Agentic_File_System.md`, any example notebooks under
  `examples/` — replace `VFSObject`, `vfs_objects`, `model=`, `Entry`
  (as result row), `entries=` (as write kwarg docs), `result.entries`
  (as docs snippet).
- `context/stories/*/` cross-references — check story 009's
  references to `Entry.capabilities` now point at `VFSEntry`.
- `/Users/claygendron/.claude/projects/-Users-claygendron-Git-Repos-grover/memory/`
  — update `project_everything_is_a_file.md` and
  `project_architecture_v2.md` to use `vfs_entries` / `VFSEntry` /
  `Candidate` vocabulary. `MEMORY.md` index line-items unchanged.

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
