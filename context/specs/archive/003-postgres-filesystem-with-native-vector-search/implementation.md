# 003 - Implementation Notes

This document maps the current implementation for story 003 to [spec.md](./spec.md).

It also records the follow-up decisions that were resolved during implementation review:

- `PostgresFileSystem` does **not** define a custom `__init__`; it uses the inherited `DatabaseFileSystem` constructor.
- Native vector dimension is owned entirely by the model declaration (`VectorType(..., postgres_native=True, dimension=<N>)`), not by a backend constructor argument.
- The probe update landed in [`scripts/postgres_repo_cli_probe.py`](../../../scripts/postgres_repo_cli_probe.py); the shell wrapper did not need a behavioral change.

## High-level result

Story 003 landed in five layers:

1. a PostgreSQL-native backend, `PostgresFileSystem`, exported alongside the portable and MSSQL backends
2. a model/type contract for native pgvector on the shared `embedding` column
3. native Postgres implementations for lexical search, grep, glob, vector search, and semantic search
4. a shared write-path fix so explicit embedding updates persist without clobbering omitted values
5. test/provisioning/doc updates plus a runnable playground notebook

The current implementation matches the updated [spec.md](./spec.md), including the clarified constructor direction.

## 1. Explicit backend surface

Spec coverage:

- [spec.md](./spec.md) "In" items 1, 2, and 3
- [spec.md](./spec.md) "Acceptance criteria / Backend surface"

Key code:

- [`src/vfs/backends/postgres.py#L67-L739`](../../../src/vfs/backends/postgres.py#L67-L739) defines `PostgresFileSystem`
- [`src/vfs/backends/database.py#L191-L211`](../../../src/vfs/backends/database.py#L191-L211) provides the inherited constructor used by `PostgresFileSystem`
- [`src/vfs/backends/__init__.py#L1-L7`](../../../src/vfs/backends/__init__.py#L1-L7) exports the backend

`PostgresFileSystem` is an explicit subclass, not a flag on `DatabaseFileSystem`. The public VFS surface is unchanged; callers opt in by instantiating the subclass directly.

The important design point is what is **not** in the class: there is no Postgres-specific constructor state for native vector dimensions. The subclass starts at the backend behavior layer (`_resolve_table`, schema verification, and search overrides), while instance construction remains the shared `DatabaseFileSystem` path.

## 2. Native Postgres vector contract lives on the model

Spec coverage:

- [spec.md](./spec.md) "In" items 4, 5, and 13
- [spec.md](./spec.md) "Acceptance criteria / Native vector column / migration"

Key code:

- [`src/vfs/vector.py#L126-L221`](../../../src/vfs/vector.py#L126-L221) adds `postgres_native`, ANN metadata, lazy pgvector loading, and native bind/result handling to `VectorType`
- [`src/vfs/models.py#L95-L103`](../../../src/vfs/models.py#L95-L103) defines `PostgresVectorColumnSpec`
- [`src/vfs/models.py#L627-L660`](../../../src/vfs/models.py#L627-L660) derives the vector index contract from the model declaration
- [`src/vfs/models.py#L663-L699`](../../../src/vfs/models.py#L663-L699) provides `postgres_native_vfs_object_model(...)`

The delivered contract is model-declared, not constructor-declared:

- `VectorType(postgres_native=True)` requires a fixed `dimension` and fails immediately if one is missing
- Postgres-native provisioning and verification discover the vector column, dimension, index method, operator class, and index name from the model/type metadata
- callers that want native pgvector either pass an explicit native model or build one via `postgres_native_vfs_object_model(...)`

This is locked in by targeted model/type tests:

- [`tests/test_vector.py#L252-L268`](../../../tests/test_vector.py#L252-L268)
- [`tests/test_models.py#L626-L637`](../../../tests/test_models.py#L626-L637)

## 3. Native schema verification

Spec coverage:

- [spec.md](./spec.md) "In" items 4 and 5
- [spec.md](./spec.md) "Acceptance criteria / Schema verification"

Key code:

- [`src/vfs/backends/postgres.py#L78-L83`](../../../src/vfs/backends/postgres.py#L78-L83) exposes `verify_native_search_schema()`
- [`src/vfs/backends/postgres.py#L85-L151`](../../../src/vfs/backends/postgres.py#L85-L151) verifies the FTS prerequisites
- [`src/vfs/backends/postgres.py#L153-L247`](../../../src/vfs/backends/postgres.py#L153-L247) verifies the pgvector/native-vector prerequisites

The verification path is fail-fast and deployment-managed:

- resolves the schema-qualified table name
- checks for `content`
- accepts a GIN expression index or generated `tsvector` column for full-text search
- skips vector checks entirely when `vector_store=` is explicitly supplied
- otherwise requires the `vector` extension, a native `vector(<N>)` column on `embedding`, a dimension match against the resolved model, and an ANN index using one of the supported pgvector index methods

Legacy serialized `embedding` columns are not rewritten in place. Verification raises with an explicit migration message instead.

Integration coverage lives in [`tests/test_postgres_backend.py#L119-L171`](../../../tests/test_postgres_backend.py#L119-L171).

## 4. Native search implementations

Spec coverage:

- [spec.md](./spec.md) "In" items 6 through 12
- [spec.md](./spec.md) "Native behavior contract"
- [spec.md](./spec.md) "Acceptance criteria / Lexical / grep / glob"
- [spec.md](./spec.md) "Acceptance criteria / Vector / semantic search"

Key code:

- [`src/vfs/backends/postgres.py#L322-L406`](../../../src/vfs/backends/postgres.py#L322-L406) implements native lexical search with Postgres FTS ranking, then hydrates only the ranked top-`k` rows
- [`src/vfs/backends/postgres.py#L408-L540`](../../../src/vfs/backends/postgres.py#L408-L540) implements grep regex pushdown while keeping line grouping/context reconstruction in Python
- [`src/vfs/backends/postgres.py#L542-L635`](../../../src/vfs/backends/postgres.py#L542-L635) implements case-sensitive Postgres glob pushdown
- [`src/vfs/backends/postgres.py#L637-L705`](../../../src/vfs/backends/postgres.py#L637-L705) implements native pgvector search over `vfs_objects.embedding`
- [`src/vfs/backends/postgres.py#L707-L739`](../../../src/vfs/backends/postgres.py#L707-L739) implements semantic search as `embedding_provider` + native vector search

Important behavioral details that shipped:

- `FULLTEXT_CONFIG` is fixed to `simple`
- `glob` remains case-sensitive through the `~` regex operator
- `grep(invert_match=True)` stays Python-authoritative and does not become a lossy row-level SQL negation
- candidate filtering for native vector search uses `ANY(:candidate_paths)` rather than exploding scalar placeholders
- explicit `vector_store=` still wins for `vector_search` and `semantic_search`, while lexical/grep/glob remain Postgres-native

Coverage:

- lexical / grep / glob tests in [`tests/test_postgres_backend.py#L174-L236`](../../../tests/test_postgres_backend.py#L174-L236)
- vector / semantic tests in [`tests/test_postgres_backend.py#L239-L316`](../../../tests/test_postgres_backend.py#L239-L316)
- override precedence in [`tests/test_vector_store.py#L215-L242`](../../../tests/test_vector_store.py#L215-L242)

## 5. Shared write-path support for native embeddings

Spec coverage:

- [spec.md](./spec.md) "In" items 14, 15, and 16
- [spec.md](./spec.md) "Acceptance criteria / Native vector column / migration"

Key code:

- [`src/vfs/models.py#L47-L74`](../../../src/vfs/models.py#L47-L74) tracks explicitly provided fields on validated SQLModel instances
- [`src/vfs/backends/database.py#L340-L355`](../../../src/vfs/backends/database.py#L340-L355) distinguishes omitted embedding from explicitly provided embedding
- [`src/vfs/backends/database.py#L792-L840`](../../../src/vfs/backends/database.py#L792-L840) applies explicit embedding updates on existing rows during writes

This is the shared behavior that keeps native pgvector honest:

- explicit `embedding=...` on insert/update persists to the row
- explicit `embedding=None` clears the row value
- omission preserves the stored value
- plain `write(path, content)` and `edit()` calls do not auto-generate embeddings

That behavior is covered by:

- [`tests/test_postgres_backend.py#L319-L374`](../../../tests/test_postgres_backend.py#L319-L374)

The explicit legacy migration path is exercised in:

- [`tests/test_postgres_backend.py#L377-L417`](../../../tests/test_postgres_backend.py#L377-L417)

## 6. Test provisioning, tooling, and docs

Spec coverage:

- [spec.md](./spec.md) "In" item 17
- [spec.md](./spec.md) "Acceptance criteria / Tooling / docs"
- [spec.md](./spec.md) "Test plan"

Key code and docs:

- [`tests/conftest.py#L136-L175`](../../../tests/conftest.py#L136-L175) provisions Postgres FTS and native pgvector indexes for integration tests
- [`tests/conftest.py#L223-L242`](../../../tests/conftest.py#L223-L242) exposes `postgres_native_db` and `postgres_legacy_db` fixtures
- [`scripts/postgres_repo_cli_probe.py#L1-L260`](../../../scripts/postgres_repo_cli_probe.py#L1-L260) probes a Postgres-backed repo snapshot through the public client/CLI surface
- [`pyproject.toml#L42-L60`](../../../pyproject.toml#L42-L60) adds `pgvector` to the `postgres` extra
- [`README.md#L15-L18`](../../../README.md#L15-L18), [`README.md#L43-L43`](../../../README.md#L43-L43), [`docs/index.md#L145-L146`](../../../docs/index.md#L145-L146), [`docs/architecture.md#L42-L42`](../../../docs/architecture.md#L42-L42), and [`docs/api.md#L622-L628`](../../../docs/api.md#L622-L628) document the backend and precedence rules
- [examples/postgres_backend_playground.ipynb](../../../examples/postgres_backend_playground.ipynb) provides a hands-on playground for the backend

Verification that was run during implementation:

- `uv run pytest tests/test_vector_store.py tests/test_postgres_backend.py tests/test_models.py -q`
- `uv run ruff check src/vfs/backends/postgres.py tests/test_vector_store.py docs/api.md`

Earlier full-story verification also included:

- `uv run --extra postgres pytest --postgres tests/test_postgres_backend.py -q`
- `uv run --extra postgres pytest --postgres -q`

## Summary

Story 003 shipped as an explicit native backend, not as special casing inside the portable backend. The durable architectural boundary is:

- `VectorType` + the model declaration define the native Postgres vector schema
- `PostgresFileSystem` executes native Postgres search against that schema
- shared write-path logic preserves embeddings correctly
- explicit external `vector_store=` remains a first-class override

The only meaningful post-spec adjustment was removing the optional constructor shortcut and making the model declaration the sole native-vector source of truth. The current [spec.md](./spec.md) has been updated to reflect that.
