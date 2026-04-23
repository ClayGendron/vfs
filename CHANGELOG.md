# Changelog

All notable changes to vfs will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Breaking

- **Storage primitive rename `VFSObject` → `VFSEntry`** (story 010) — `VFSObject` and `VFSObjectBase` collapse into a single `VFSEntry(SQLModel, table=False)`. `VFSEntry` is the durable record (Constitution Article 1.2); there is no base/concrete split. See [`context/stories/010-align-primitives-vfsentry-and-candidate/spec.md`](context/stories/010-align-primitives-vfsentry-and-candidate/spec.md).
- **Per-mount `table=True` class** — `DatabaseFileSystem.__init__` mints a private `table=True` subclass of `VFSEntry` scoped to `(table_name, schema, native_embedding)`. The minted class is never exposed on the public surface.
- **`model=` kwarg removed** from `DatabaseFileSystem`, `MSSQLFileSystem`, `PostgresFileSystem`, `VFSClient*`, and `RustworkxGraph`. Storage shape is no longer a deployment knob. Callers passing `model=...` now get `TypeError`.
- **`table_name: str = "vfs_entries"` and `native_embedding: NativeEmbeddingConfig | None = None`** added to `DatabaseFileSystem.__init__`. The default `__tablename__` is now `vfs_entries` and the default index is `ix_vfs_entries_ext_kind`. Callers preserving an existing `vfs_objects` table pass `table_name="vfs_objects"` explicitly.
- **Result-row rename `Entry` → `Candidate`** — the query-time partial view is `Candidate` (Constitution Article 1.5). `VFSResult.entries` becomes `VFSResult.candidates`, `ENTRY_FIELDS` becomes `CANDIDATE_FIELDS`, and `VFSEntry.to_entry()` becomes `VFSEntry.to_candidate()`. The storage-write kwarg `entries=` on `write()` / `_write_impl()` / `_mkedge_impl()` still takes a `Sequence[VFSEntry]` and stays named `entries=`.
- **Envelope field rename in JSON output** — `result.to_json()` emits `"candidates"`; the `"entries"` key no longer appears.

### Changed

- **`MSSQLFileSystem._lexical_search_impl`** (story 012) — rewritten as a single `FREETEXTTABLE` query that projects `path`, `kind`, `content`, and `ct.[RANK] AS score` in one round-trip, ordered by `ct.[RANK] DESC, o.id` for deterministic ranking across calls. Tokenization, stemming, stoplist handling, and thesaurus expansion now run server-side; the Python `tokenize_query` + OR-of-literal-terms CONTAINS expression is gone. `_grep_impl` still uses `CONTAINSTABLE` and `_quote_contains_term` for its literal-AND pre-filter and is unchanged.
- **MSSQL `Candidate.score` scale change** — lexical-search scores are now `FREETEXTTABLE` BM25-derived ranks (unbounded positive, integer on the wire, returned as `float`), not the previous `CONTAINSTABLE` rank formula. Still `float`, different magnitude, still not comparable to Postgres `ts_rank_cd`. Callers thresholding on the old value must re-tune.

## [0.0.22] — 2026-04-22

### Added

- **`PostgresFileSystem`** (story 003) — native Postgres backend with pgvector-backed embeddings, native lexical (`tsvector` + `CONTAINSTABLE`-equivalent `plainto_tsquery`) and semantic search, regex pushdown, and explicit schema verification. Respects the model-declared pgvector operator class (`vector_cosine_ops`, `vector_ip_ops`, `vector_l2_ops`) for both distance operator selection (`<=>`, `<#>`, `<->`) and score normalization.
- **Native Postgres pattern-search contract** — partial trigram GIN + B-tree `text_pattern_ops` indexes on `vfs_objects.path` and `.content`; `verify_native_search_schema` fails fast if the required artifacts are missing.
- **Native Postgres `meeting_subgraph`** (story 004) — server-side PL/pgSQL Steiner-tree traversal installed via `install_native_graph_schema()` and verified at startup.
- **Native MSSQL `meeting_subgraph`** — T-SQL stored procedure with a TVP (`GroverSeedList`) seed-list input; override routes through a raw `aioodbc` cursor since SQLAlchemy `bindparam` can't plumb TVPs.
- **Native MSSQL pushdown for `predecessors`, `successors`, `ancestors`, `descendants`, `neighborhood`** — previously delegated to the in-memory rustworkx path. Seed/exclusion sets bind as JSON strings unpacked via `OPENJSON` with an explicit `NVARCHAR(450)` schema; multi-hop traversals drive a Python BFS loop over single-hop SQL queries to avoid MSSQL's recursive-CTE `UNION ALL` cycle hazard.
- **`/.vfs` sidecar namespace** (story 002) — canonical `/.vfs/<path>/__meta__/...` layout for edge storage and metadata. Replaces the prior child-of-file metadata namespace; `mkconn` is removed.

### Changed

- **Result schema unified** — the `Candidate` / `Detail` chain is collapsed into a flat `Entry` row with operation metadata hoisted onto the envelope. Backends and the query executor now reason in terms of column projection instead of shape dispatch.
- **Constitution rewritten** around four primitives (Namespace, Entry, Revision, Operation) with RFC 2119 precedence language.
- **`in_degree` / `out_degree` dropped** from `VFSObjectBase`, `Entry` projection, and result defaults — graph degrees are no longer part of the entry payload.
- **`path` / `parent_path` max length restored to 4096** so `SQLModel.metadata.create_all` targets SQL Server's `VARCHAR(8000)` ceiling; deepest sidecar paths (`/.vfs/<path>/__meta__/versions`) now have headroom.
- **`MSSQLFileSystem._grep_impl`** — WHERE body extracted so the two FROM / ORDER BY branches no longer duplicate the filter body.
- **`context/` workspace** — research/ migrated into `context/standards/`, `context/stories/`, `context/learnings/`; legacy docs and demo DB fixtures pruned.

### Fixed

- **`VectorType.process_result_value`** — reject `str` / `bytes` before the iterable fallback so the expected `ValueError("expected iterable pgvector value")` is raised instead of a downstream per-character float parse error.
- **CI coverage** restored above the 99% gate with focused tests for Postgres inverse-edge projections, path/vector helper error handling, model/result rendering, and routing/parser/base/permission edge cases.
- **CI lint / format / type-check regressions** from the native search backend work — touched files now pass `ruff check`, `ruff format --check`, and `ty check src/`.

## [0.0.21] — 2026-04-18

### Changed

- **Python package renamed from `grover` to `vfs`** — imports change from `from grover import ...` to `from vfs import ...`. Matches the `vfs-py` PyPI distribution name. This is a breaking change with no compatibility shim.
- **Class identifiers renamed to a `VFS*` / `VirtualFileSystem` scheme**:
  - `GroverFileSystem` → `VirtualFileSystem` (in `vfs.base`)
  - `Grover` → `VFSClient` (sync facade)
  - `GroverAsync` → `VFSClientAsync` (async router)
  - `GroverResult` → `VFSResult`
  - `GroverObject` / `GroverObjectBase` → `VFSObject` / `VFSObjectBase`
  - `GroverError` → `VFSError`
- **DB table renamed `grover_objects` → `vfs_objects`** (and the `ix_grover_objects_ext_kind` index → `ix_vfs_objects_ext_kind`). No migration script is shipped — existing databases need their tables recreated by the consumer.
- **`scripts/bump_version.py`** — updated to point at `src/vfs/__init__.py`.
- **`README.md`** — examples, install commands, badges, and class names updated for the new package and identifiers.

## [0.0.20] — 2026-04-17

### Changed

- **PyPI package renamed from `grover` to `vfs-py`** — install with `pip install vfs-py`. Python imports are unchanged (`import grover`). Versions 0.0.18 and earlier remain available on PyPI under the `grover` name; new releases publish to `vfs-py`.

## [0.0.18] — 2026-04-10

### Changed

- **DB read paths now hydrate `Candidate.content`** — `ls`, `glob`, `delete`, `move`, `tree`, and `lexical_search` always populate `content` on the candidates they emit. The underlying `select(self._model)` was already pulling the column over the wire; the `include_content=False` default on `to_candidate` was discarding it during projection. Removed the parameter entirely so every read-path projection returns content, eliminating the redundant follow-up `read(...)` round trip when a downstream stage needs the content.
- **MSSQL `_grep_impl`, `_glob_impl`, and `_lexical_search_impl` delegate to the base class when `candidates` is supplied** — Once the candidate set has been transferred to Python (and now carries content), there is nothing left for SQL Server to do. The base class runs the regex via `_collect_line_matches` and BM25 via `BM25Scorer` over the in-memory content with zero round trips. Full-tree pushdowns (`CONTAINSTABLE`, `REGEXP_LIKE`) are unchanged for the no-candidates path.
- **MSSQL `_glob_impl` no-candidates branch** — `SELECT path, kind, content` instead of `SELECT path, kind`, so glob results carry content directly out of the pushdown.
- **MSSQL `_lexical_search_impl` no-candidates branch** — Follows the `CONTAINSTABLE` pushdown with one small batched `SELECT path, content WHERE path IN (top_k)` so the top-k results return hydrated. `k` is bounded (default 15), so the second round trip is tiny.
- **Base `_lexical_search_impl`** — Threads content through `_LexicalDoc` into the result candidates (previously dropped during result construction).
- **Base `_glob_impl` upstream-candidates branch** — Preserves prior content and metrics via `Candidate.model_copy(...)` instead of constructing a fresh `Candidate` that drops them.
- **`_read_impl`** — Skips the `SELECT` for already-hydrated candidates and only fetches the gaps. Makes `read(candidates=...)` cheap when content is already on the candidates from a prior stage.

### Removed

- **`include_content` parameter on `GroverObjectBase.to_candidate`** — Always populates content now. The 5 callers that explicitly passed `include_content=True` (`_write_impl`, `_read_impl`, bulk write) drop the redundant kwarg.
- **MSSQL `_grep_with_candidate_chunks` helper** — Dead after the candidates path delegates to the base class.

### Fixed

- **`glob | grep` on MSSQL drops from three round trips to one** — Previously the executor pre-hydrated content via `read(...)`, then MSSQL `_grep_impl` ignored the hydrated content and re-queried with `REGEXP_LIKE` against the same paths. Now glob returns hydrated content directly and grep runs the regex in Python on the in-memory candidates.

## [0.0.17] — 2026-04-10

### Fixed

- **`glob` and `grep` mount-prefix routing** — Absolute patterns and literal `paths` filters are now stripped of the mount prefix before dispatch to each mount. Previously the non-candidate fanout in `_route_fanout` forwarded the full pattern to every mount, but mounts store paths mount-relative — so `glob('/data/**/*.py')` and `grep` with `paths=('/data/src',)` silently returned empty while `read` on the same path worked. New dedicated `_route_glob_fanout` / `_route_grep_fanout` use exact-rewrite when provable (literal-prefix or single-segment glob consumption against the mount name) and fall back to a `/**` superset query plus router-side authoritative re-filter when the pattern's leading segment is `**`. `globs_not` is never silently dropped — exclusions that cannot be exactly pushed are enforced at the router after rebase. `max_count` is deferred to the router whenever any mount uses the post-filter fallback so it cannot truncate pre-filter candidates. Wildcard mount selectors (`/*/`, `/d?ta/`, `/d[ae]ta/`) and multi-hop chains (`GroverAsync → router → router → leaf`) work correctly. The candidate-input path (`glob`/`grep` with `candidates=`) had the same mismatch and is fixed by filtering at the router with the original absolute pattern before grouping by terminal.

### Added

- **`grover.routing` module** — Pure helpers (`rewrite_glob_for_mount`, `rewrite_path_for_mount`, `first_segment`, `glob_segment_matches`) and plan dataclasses (`GlobMountPlan`, `GrepMountPlan`) backing the new fanout strategy.

### Changed

- **`MSSQLFileSystem` glob pushdown** — `_glob_impl` now structurally decomposes glob patterns via the new `decompose_glob()` helper into a literal path prefix and a trailing `**/*.<ext>` tail, then pushes both into SQL: the prefix becomes a sargable `LIKE` predicate and the ext narrows the `(ext, kind)` composite index seek. When the pattern is fully expressible as `prefix + **/*.<ext>` the authoritative `REGEXP_LIKE` residual is dropped entirely and `kind` is narrowed to `'file'` so the planner picks `ix_grover_objects_ext_kind` instead of relying on `ext IS NULL` for directory exclusion. Caller-supplied `ext` and `paths` remain authoritative (intersected with the decomposed values) so explicit narrowing is never broadened by the optimization. Patterns the decomposer doesn't recognize fall through to the existing regex path with no behavior change.

## [0.0.16] — 2026-04-10

### Added

- **Ripgrep-compatible filter surface on `grep` and `glob`** — Structural filters (`ext`, positional `paths`, `globs`, output modes `files`/`lines`/`count`, context windows `-A`/`-B`/`-C`, `case_mode`, `max_count`) now push into SQL through a composable clause builder instead of forcing every search through a full-content scan. `DatabaseFileSystem` still issues a single query per grep/glob call; `MSSQLFileSystem` picks between four SQL templates (CONTAINSTABLE/Direct × lines/files) and skips content transfer entirely for `-l` (files-only) mode.
- **Indexed `ext` column on `grover_objects`** — Derived from `path` and indexed so `-t py` on a million-row corpus becomes an index seek rather than a table scan. Maintained automatically on write.
- **`docs/ai_agent_glob_grep_patterns.md`** — Reference for agents on rg-equivalent query patterns against Grover.

### Changed

- **`grep` / `glob` kwargs aligned with ripgrep** — `case_sensitive` → `case_mode` (`smart`/`insensitive`/`sensitive`), `max_results` → `max_count`. This is a breaking change for callers of the old kwargs.

## [0.0.15] — 2026-04-10

### Fixed

- **`MSSQLFileSystem` schema resolution for raw `text()` SQL** — Raw `text()` queries in `verify_fulltext_schema`, `_lexical_search_impl`, `_grep_impl`, `_grep_with_candidate_chunks`, and `_glob_impl` used `self._model.__tablename__` directly, bypassing SQLAlchemy's `schema_translate_map` (which only applies when compiling `Table` references). Mounts pointing at a non-default schema hit `Invalid object name 'grover_objects'` on every search call. Fixed by adding a `schema` kwarg to `GroverFileSystem` that stores `self._schema` and applies `schema_translate_map={None: schema}` to every session via `_use_session()` so ORM queries continue to resolve correctly, plus a `_resolve_table()` helper on `MSSQLFileSystem` that qualifies the bare `__tablename__` with `self._schema` for raw SQL. Works uniformly across `engine=` and `session_factory=` construction and supports multiple filesystems sharing one factory with different schemas (per-session connection options). Closes #3.
- **`verify_fulltext_schema` DDL hint key column** — The suggested `CREATE UNIQUE NONCLUSTERED INDEX` referenced `(path)`, but `path` is `max_length=4096` and exceeds SQL Server's 900-byte index key limit, so the DDL would always fail. The Full-Text `KEY INDEX` now targets `(id)`, the 36-character UUID primary key.

### Added

- **`schema` kwarg on `GroverFileSystem`** — Optional, forwarded through `DatabaseFileSystem.__init__` and `MSSQLFileSystem.__init__`. When set, `_use_session()` applies `schema_translate_map={None: schema}` per session so ORM queries resolve unqualified tables, and `MSSQLFileSystem` raw queries qualify the table name with it.

## [0.0.14] — 2026-04-09

### Added

- **`MSSQLFileSystem` (alpha)** — SQL Server / Azure SQL backend with full-text search and native regex pushdown. Subclass of `DatabaseFileSystem` that overrides `_lexical_search_impl`, `_grep_impl`, and `_glob_impl` to push work into SQL Server 2025+ via `CONTAINSTABLE` and `REGEXP_LIKE`. CRUD, versions, chunks, connections, graph, and vector search are inherited unchanged. Includes `verify_fulltext_schema()` startup check, a dialect parameter budget of 2000, and a Docker dev environment (SQL Server 2025 + Full-Text Search + ODBC Driver 18) with `mssql_up.sh` / `mssql_down.sh` / `mssql_test.sh` helpers. Install via `grover[mssql]` (requires `aioodbc>=0.5` and `pyodbc>=5.0`). Operators must provision the Full-Text catalog and index outside the application. Integration tests gated on `pytest --mssql`; helpers run unconditionally in CI. `src/grover/backends/mssql.py` is excluded from the coverage gate until a SQL Server 2025 service container is wired into CI.
- **Mount-level permissions** — `read` / `read_write` flag on `add_mount()` for coarse-grained access control. Read-only mounts reject all write operations at the facade boundary.
- **Directory-level permissions via `PermissionMap`** — fine-grained per-directory permission rules layered on top of mount permissions. Routing checks both mount and directory permissions before dispatching to the backend.

## [0.0.13] — 2026-04-07

### Added

- **`GroverObjectBase.clone()`** — Fast (~1.7µs) method to create a detached copy of a model instance with independent SQLAlchemy state. Uses shallow copy + fresh `InstanceState` so clones can be safely added to any session.

### Fixed

- **`write(objects=...)` no longer mutates input objects** — `_group_objects_by_terminal` now clones objects before stripping mount prefixes, preserving the caller's original list.
- **`add_prefix` path normalization** — Prefixes are now normalized via `normalize_path()` before concatenation, ensuring paths always have a leading `/` regardless of prefix format.
- **`strip_prefix` safety** — Now validates the prefix matches the start of the path and raises `ValueError` on mismatch instead of blindly slicing. Prefixes are normalized before comparison.
- **`_rederive_path_fields` normalization** — Calls `normalize_path()` as a safety net, guaranteeing all post-mutation paths are valid before reaching the database.

## [0.0.12] — 2026-04-03

### Changed

- **Unified client API** — All `Grover` sync methods now return `GroverResult`, matching `GroverFileSystem` exactly. Single-path CRUD methods (`read`, `write`, `edit`, `delete`, `stat`, `mkdir`, `mkconn`) no longer unwrap to `Candidate`.
- **`add_mount` simplified** — Accepts both `"data"` and `"/data"`, rejects nested paths. No more factory kwargs (`engine_url`, `session_factory`, etc.) — construct `DatabaseFileSystem` explicitly and pass it in.
- **No overrides in facades** — Mount normalization, engine disposal, and `close()` live on `GroverFileSystem`. `GroverAsync` is now a one-liner subclass. `Grover` sync wrapper is a pure delegation layer.
- **Batch parameters added to sync `Grover`** — `candidates` param on `read`, `stat`, `edit`, `delete`, `ls`; `edits` list on `edit`; `moves`/`copies` batch lists on `move`/`copy`; `objects` on `write`.

### Fixed

- **Path length limit test** — Account for `/.versions/1` suffix when testing max path length against the 4096-char column limit.

## [0.0.11] — 2026-04-02

### Added

- **v2 rewrite** — Complete rewrite of Grover around the "everything is a file" philosophy. New unified `grover_objects` table replaces the four separate tables (files, chunks, versions, connections). All entities are path-addressable with dot-prefixed metadata directories (`.chunks/`, `.versions/`, `.connections/`).
- **`GroverFileSystem` base class** — Concrete async base class with mount routing, session management, and path rebasing. Subclasses override `_*_impl` methods for storage.
- **`DatabaseFileSystem`** — Full SQL-backed implementation with CRUD, glob, grep, tree, versioning (snapshot + forward diffs), soft-delete, cascading operations, and LIKE wildcard escaping for path safety.
- **CLI query engine** — Hand-rolled tokenizer, parser, AST, executor, and renderer. Unix-like pipeline syntax with `|`, `&`, `intersect()`, `except()`. Commands: `read`, `write`, `edit`, `rm`, `mv`, `cp`, `mkdir`, `mkconn`, `ls`, `tree`, `glob`, `grep`, `search`, `lsearch`, `vsearch`, graph traversal, and ranking.
- **Graph algorithms** — All 10 graph algorithms implemented on `RustworkxGraph`: ancestors, descendants, neighborhood, meeting subgraph, min meeting subgraph, PageRank, betweenness/closeness/degree centrality, and HITS. Cross-validated against NetworkX at 10K nodes.
- **BM25 lexical search** — Hand-rolled BM25 scorer with SQL-hybrid pipeline for `lexical_search`. No external dependencies.
- **`EmbeddingProvider` and `VectorStore` protocols** — Pluggable embedding and vector search with `DatabricksVectorStore` and `LangChainEmbeddingProvider` implementations.
- **User-scoped filesystem** — Per-user path-prefix isolation via `user_scoped=True` on `DatabaseFileSystem`. Strict scope/unscope at DB boundary.
- **`GroverAsync` and `Grover` facades** — Async facade for app servers, sync wrapper for scripts and notebooks. `raise_on_error` flag with classified exception hierarchy (`NotFoundError`, `MountError`, `WriteConflictError`, `ValidationError`, `GraphError`).
- **Composable result types** — `GroverResult` with `Candidate` and `Detail` objects. Set algebra (`&`, `|`, `-`), enrichment chains (`sort`, `top`, `filter`, `kinds`).

### Changed

- **README rewritten** — New README focused on the v2 direction with code-first examples, design principles, API table, and namespace diagram.
- **Type checker upgraded** — Migrated from ty 0.0.16 to 0.0.27 with `# ty: ignore` inline comments replacing `# type: ignore`.
- **BM25 comparison tests moved to scripts** — `test_bm25_comparison.py` (requires `rank_bm25`) moved to `scripts/bm25_comparison.py`. Replaced with standalone `test_bm25.py`.

## [0.0.10] — 2026-03-19

### Added

- **Unified `GroverResult` type** — All facade operations (`write_files`, `read`, `edit`, `delete`, `move_files`, `copy_files`, `read_files`, `write_chunks`, `reconcile`) now return `GroverResult` with typed `Detail` objects providing per-file success/failure tracking, messages, and metadata.
- **Batch `move_files()`, `copy_files()`, `read_files()`** — New facade methods for bulk operations with per-file result tracking.
- **`ValidatedSQLModel` base class** — Runtime Pydantic validation for SQLModel instances constructed from non-database sources (DataFrames, dicts). DB models opt in via `ValidatedSQLModel` inheritance; `model_from_mount()` on `GroverContext` resolves the correct model class per mount.
- **`move --follow` support** — `move_files()` gains a `follow` parameter to update graph connections after moves.
- **`list_dir` returns candidates** — Directory listing now returns typed result objects.
- **`ReconcileDetail`** — New detail type for per-file reconcile tracking (added/updated/deleted).

### Changed

- **Version/trash facade methods removed** — `versions()`, `rollback()`, `trash()`, `restore()`, `empty_trash()` removed from facade, backends, and protocols. Deletions now cascade automatically through the database.
- **`read()` simplified** — `offset` and `limit` parameters removed from `read()` across facade, backends, and utilities. Content slicing is no longer a backend concern.
- **`write_chunks` refactored** — Follows the same thin-facade pattern as `write_files`, with chunking logic pushed into `ChunkProvider`.
- **`Ref` internals unified** — Internal ref parsing consolidated into `models/internal/ref.py` with enhanced decomposition.
- **Mount naming and DB model base classes simplified** — Cleaner mount initialization, streamlined dialect helpers.

### Fixed

- **ty 0.0.23 compatibility** — Protocol mismatches and or-pattern union errors resolved for latest type checker.
- **`GroverResult` migration alignment** — Backend return types, batch type exports, and test expectations aligned with unified result model.

## [0.0.9] — 2026-03-17

### Changed

- **`vector` field renamed to `embedding`** — `FileModel.embedding`, `FileChunkModel.embedding`, and `FileVersionModel.embedding` replace the old `vector` field. Pydantic's `Vector` type still handles serialization under the hood.
- **`created_at`/`updated_at` default to `None`** — File models no longer eagerly timestamp at construction time. The backend fills timestamps on write if not set. This makes DataFrame-sourced bulk writes cleaner.
- **Mount `path` → `name`** — `add_mount("project", ...)` replaces `add_mount("/project", ...)`. Mount names are simple identifiers (no `/` allowed). `mount.path` is derived internally as `f"/{name}"`.

### Added

- **`tokens` field** — `FileModel` and `FileChunkModel` gain a `tokens: int = 0` field for storing token counts.
- **`FileModelBase.create()` factory** — `FileModel.create("a.py", "code", mount="project", embedding=[0.1, ...], tokens=150)` builds a fully-populated model with computed hash, size, mime type, line count, and timestamps.
- **`write_files()` model flow-through** — Facade preserves all user-set fields (embedding, tokens, owner_id) through to the backend instead of stripping models down to `{path, content}`.

### Fixed

- **Variable shadowing in `_create_engine_mount`** — A `for name in table_names` loop variable overwrote the `name` parameter, causing engine-config mounts to get the wrong name when tables were created.

## [0.0.8] — 2026-03-17

### Added

- **Schema-aware table creation** — When `EngineConfig` provides a `schema`, `add_mount()` now creates the schema if it doesn't exist (PostgreSQL, MSSQL) and creates tables within that schema using `schema_translate_map`. Logs `Schema created: "name"` and `Tables created: ...` when new objects are created.
- **`ensure_schema()`** — Dialect-aware helper in `grover.util.dialect` that creates a database schema if missing. Supports PostgreSQL (`CREATE SCHEMA IF NOT EXISTS`), MSSQL (conditional `CREATE SCHEMA`), and no-ops on SQLite.
- **`check_tables_exist()`** — Helper that returns which table names already exist in a given schema, used to determine whether to log table creation messages.

## [0.0.7] — 2026-03-16

### Added

- **`EngineConfig`** — Frozen dataclass for engine-managed mounts. Accepts `url` (simple) or `engine_factory` (advanced, e.g. custom pool/connect_args via `create_async_engine_factory`). Supports `schema`, `create_tables`, and custom model overrides. Engine is created at mount time and disposed on unmount/close.
- **`SessionConfig`** — Frozen dataclass for app-managed mounts. Wraps an existing session factory; Grover does not dispose the engine. Dialect inferred from the factory's bind or set explicitly.
- **`create_async_engine_factory()`** — Helper that captures `create_async_engine` args and returns a zero-arg callable for deferred engine creation.
- **Engine lifecycle on `Mount`** — `Mount.engine` field tracks Grover-owned engines. `unmount()` and `close()` dispose them automatically.

### Changed

- **`add_mount()` API redesigned** — `engine=`, `session_factory=`, `dialect=`, `file_model=`, `file_version_model=`, `file_chunk_model=`, `db_schema=` parameters replaced by `engine_config=` and `session_config=`. `filesystem` and `mount` are now keyword-only. `path` remains positional.
- **`DatabaseFileSystem` constructor simplified** — Config parameters (dialect, schema, model classes) removed. Only provider kwargs remain. New `_configure()` method applies settings from `EngineConfig`/`SessionConfig` at mount time.
- **`LocalFileSystem` constructor simplified** — Model and schema parameters removed. Accepts only `workspace_dir`, `data_dir`, and provider kwargs.
- **`UserScopedFileSystem` constructor simplified** — Config parameters removed. Accepts only `share_model` and provider kwargs.
- **deepagents integration** — `from_database()` and `from_database_async()` now accept `EngineConfig` instead of raw engine/session_factory.

### Fixed

- **Sync `Grover` in Jupyter** — Pre-created `AsyncEngine` bound to the wrong event loop no longer causes failures. `EngineConfig` defers engine creation to mount time, ensuring it runs on the correct loop.

## [0.0.6] — 2026-03-16

### Changed

- **`max_length=1024` on all indexed string columns** — All `id`, `path`, `file_path`, `source_path`, `target_path`, `owner_id`, and `grantee_id` fields across all five DB models (`grover_files`, `grover_file_chunks`, `grover_file_connections`, `grover_file_shares`, `grover_file_versions`) now have explicit `max_length=1024` for compatibility with databases that require bounded index columns.

## [0.0.5] — 2026-03-16

### Added

- **`FileSearchSet` candidate container** — unordered set with set algebra (`&`, `|`, `-`, `>>`), path transforms (`rebase`, `remap_paths`), and iteration. Used as input filter for search methods.
- **`BatchResult`** — batch operation result type with `succeeded`/`failed` counts.
- **Candidates filtering** — `glob`, `grep`, `vector_search`, `lexical_search`, `hybrid_search` all accept `candidates: FileSearchSet` for pipeline-style filtering.
- **`diff_versions`** — compare two file versions, exposed on `Grover`/`GroverAsync`.
- **`write_file`, `write_files`, `write_chunk`, `write_chunks`** — public API methods for model-based writes.
- **Self-managing graph** — `RustworkxGraph` lazy-loads from DB, TTL-based refresh, `configure_refresh()`.
- **`IndexConfig`** — frozen dataclass for vector index creation, defined in `providers/search/protocol.py`.
- **`parent_path_from_id`** — utility to extract parent file path from chunk IDs (`/a.py#login` → `/a.py`).

### Changed

- **SearchProvider protocol stripped to MVP** — 6 methods: `connect`, `close`, `create_index`, `upsert(files=)`, `delete(files=)`, `vector_search(candidates=)`. Uses domain types (`File`, `BatchResult`, `FileSearchResult`) instead of search-specific types. `lexical_search` moved to filesystem backend (DB-native FTS).
- **`types.py` deleted** — `VectorEntry`, `UpsertResult`, `DeleteResult`, `VectorHit`, `SparseVector`, `TextEntry`, `IndexConfig` (old), `IndexInfo`, `SearchResult` all removed.
- **Opt-in search protocols removed** — `SupportsNamespaces`, `SupportsMetadataFilter`, `SupportsIndexLifecycle`, `SupportsHybridSearch`, `SupportsReranking` deleted from `protocol.py`. Pinecone/Databricks keep these as concrete methods.
- **DatabricksVectorStore rewritten** — stripped to protocol surface only (`connect`, `close`, `create_index`, `upsert`, `delete`, `vector_search`).
- **Internal result types overhauled** — `FileSearchResult` extends `FileSearchSet`, typed `Evidence` subclasses on `File` objects replace 30+ result subclasses. `GraphProvider` returns `FileSearchResult` directly.
- **RustworkxGraph refactored** — adjacency dicts, `_snapshot()` for thread-safe algorithm execution, `.graph` property exposes `PyDiGraph`, public attributes replace getters.
- **Async graph operations** — all query/algorithm methods on `RustworkxGraph` are `async def`. Heavy algorithms use `asyncio.to_thread()`.
- **Graph facade simplified** — `GraphOpsMixin` is pure delegation to `GraphProvider`. `GraphStore` alias removed.
- **`GroverAsync` mixins consolidated** — 8 → 6 mixins (ConnectionMixin absorbed into GraphOpsMixin, VersionTrashMixin into FileOpsMixin).
- **Search method signatures corrected** — `list_dir`, `tree`, `list_versions` reverted to path-based; `vector_search` rebase bug fixed.

### Fixed

- **CI workflow** — `uvx ruff`/`uvx ty` instead of pip-installed tools; trigger on workflow file changes.
- **ty type errors** — evidence lists annotated as `list[Evidence]`, `Any` replaced with concrete types.

## [0.0.4] — 2026-03-04

### Added

- **Background worker** — `BackgroundWorker` with per-path debounced task scheduling, `flush()`/`drain()` lifecycle, and `IndexingMode` (background vs manual). Replaces `EventBus`.
- **Version chain verification** — `verify_chain()`, `verify_versions()`, and `verify_all_versions()` for proactive integrity checking across backends, facade, and sync wrapper.
- **Composable search pipeline** — `vector_search()`, `lexical_search()`, `hybrid_search()` with `SearchProvider` protocol. BM25 full-text search via `FullTextStore` with SQLite/PostgreSQL/MSSQL backends.
- **Connection service** — `ConnectionService` in `DatabaseFileSystem` for filesystem-owned persistent edges. Graph is now a pure in-memory projection loaded from DB via `from_sql()`.
- **Result type algebra** — `FileOperationResult` and `FileSearchResult` base types with set operations (`&`, `|`, `-`, `>>`). Candidates-based search results. `GraphResult` for graph method returns.
- **`Ref` identity type** — Thin frozen wrapper with lazy path decomposition. Factories for chunk, version, and connection refs. Replaces `file_ref()` and `fs/paths.py`.
- **`GroverContext` dataclass** — Shared state for the facade, accessed via `self._ctx`. `GroverAsync` decomposed into 8 mixins (mount, file ops, search ops, graph ops, version/trash, share, connection, index).
- **Native async integrations** — deepagents and LangChain integrations accept `Grover | GroverAsync`.

### Changed

- **Package restructure** — `fs/` → `backends/`, `facade/` → `api/`, `types/` → `results/`, `graph/` and `search/` → `providers/graph/` and `providers/search/`, analyzers promoted to top-level `analyzers/`.
- **Protocol consolidation** — `SupportsVersions`, `SupportsTrash`, `SupportsSearch`, `SupportsConnections`, `SupportsFileChunks` merged into `GroverFileSystem`. Only `SupportsReBAC` and `SupportsReconcile` remain as opt-in. Graph protocols collapsed from 8 → 1, search from 9 → 6, storage from 3 → 1.
- **Filesystem-centric providers** — `DatabaseFileSystem` owns all providers directly. Provider protocols co-located in `providers/<family>/protocol.py`. `Mount` stripped to minimal dataclass (no graph/search).
- **`LocalFileSystem`** simplified to thin `DatabaseFileSystem` subclass (~330 lines).
- **`SharingService`** inlined into `UserScopedFileSystem`.
- **`DatabaseFileSystem`** flattened — internal mixins and services inlined.
- **Graph terminology** — `dependents`/`dependencies` renamed to `predecessors`/`successors`. `impacts`, `ancestors`, `descendants` removed.
- **Type safety** — `Any` replaced with concrete types across the codebase. `FilterValue` type alias added. `ty check src/` passes clean.
- **Backward compat aliases removed** — `mount()` → `add_mount()`, `SentenceTransformerProvider` alias deleted, `GroverEdge` removed, `query_types.py` deleted.
- **Dead code deleted** — `SearchEngine`, `FullTextStore`, `EventBus`, `Embedding` model, `VectorStore` protocol, mount dispatch protocols, `vfs.py`.

### Fixed

- **Path traversal vulnerability** in `UserScopedFileSystem._resolve_path`.
- **Read-only permission enforcement** across all mutation paths.

## [0.0.3] — 2026-02-19

### Added

- **Graph protocol hierarchy** — `GraphStore` core protocol + 7 capability protocols (`SupportsCentrality`, `SupportsConnectivity`, `SupportsTraversal`, `SupportsSubgraph`, `SupportsFiltering`, `SupportsNodeSimilarity`, `SupportsPersistence`), following the same `@runtime_checkable` pattern as the filesystem layer.
- **Graph algorithms** — Centrality (PageRank, betweenness, closeness, katz, degree), connectivity (weakly/strongly connected components), and traversal (ancestors, descendants, topological sort, shortest paths, all simple paths) on `RustworkxGraph`.
- **Subgraph extraction** — `subgraph()`, `neighborhood()` (BFS with direction/edge-type filters), `meeting_subgraph()` (pairwise shortest paths + PageRank scoring + pruning), and `common_reachable()`.
- **Graph filtering** — `find_nodes()` with callable predicates or equality matching, `find_edges()` by type/source/target, `edges_of()` with direction filtering.
- **Node similarity** — Jaccard coefficient via `node_similarity()` and `similar_nodes()` (top-k).
- **`SubgraphResult` type** — Frozen dataclass with deep immutability (`tuple` fields, `MappingProxyType` scores).
- **Public API surface** — `GraphStore` and `SubgraphResult` exported from `grover`. Convenience wrappers on `Grover`/`GroverAsync` for `pagerank`, `ancestors`, `descendants`, `meeting_subgraph`, `neighborhood`, `find_nodes` with `isinstance`-based capability checking.

### Changed

- **`Graph` → `RustworkxGraph`** — Renamed with no backward-compatible alias. All imports migrated.
- **`GroverAsync.graph` is now a public attribute** typed as `GraphStore` (was `self._graph`).
- Removed `SentenceTransformerProvider` backward-compat alias — use `SentenceTransformerEmbedding`.

## [0.0.2] — 2026-02-17

### Added

- **User-scoped file systems** — `UserScopedFileSystem` backend with per-user path namespacing, owner-scoped trash, and `@shared` virtual directory for cross-user access.
- **Sharing service** — Path-based share/unshare with permission resolution (read-only, read-write), expiration support, and directory inheritance.
- **External edit detection** — Synthetic version insertion to preserve version chain integrity when files change outside Grover.
- **Move with `follow` semantics** — `follow=True` renames in place; `follow=False` creates a clean break.
- **deepagents integration** — `GroverBackend` (BackendProtocol) and `GroverMiddleware` (10 tools for version, search, graph, and trash operations).
- **LangChain/LangGraph integration** — `GroverRetriever`, `GroverLoader`, and `GroverStore` for RAG pipelines and persistent agent memory.
- **Public API additions** — `user_id`, `share`, `unshare`, `list_shares`, `list_shared_with_me`, `move`, `copy`, `overwrite`, `replace_all`, `offset`/`limit` parameters threaded through the full stack.
- **Authorization hardening** — Fixed 6 bypass vulnerabilities in `UserScopedFileSystem`.

### Changed

- Bumped minimum Python requirement from 3.10 to 3.12.
- Scoped CI triggers: tests run on `src/`/`tests/` changes, docs build on `docs/` changes.

### Fixed

- `_list_shared_dir` now supports file-level shares via filtered fallback.
- SQL `LIKE` wildcards properly escaped in `update_share_paths`.
- Loader non-recursive `size_bytes` calculation and binary file skip behavior.

## [0.0.1] — 2026-02-11

Initial alpha release.

### Added

- **Two storage backends** — `LocalFileSystem` (disk + SQLite) for local dev, `DatabaseFileSystem` (pure SQL) for web apps and shared knowledge bases.
- **Mount-based VFS** — Routes operations to the right backend by path prefix; mount multiple backends side by side.
- **Automatic versioning** — Diff-based storage (snapshots + forward diffs) with SHA-256 integrity checks.
- **Soft-delete trash** — Restore or permanently delete.
- **File operations** — read, write, edit, delete, move, copy, mkdir, list_dir, exists.
- **Search operations** — glob (pattern matching), grep (regex search with context lines), tree (directory listing with depth limits).
- **Capability protocols** — Backends declare support via `SupportsVersions`, `SupportsTrash`, `SupportsReconcile`, checked at runtime.
- **Dialect-aware SQL** — SQLite, PostgreSQL, and MSSQL.
- **Reconciliation** — Sync disk state with database for `LocalFileSystem`.
- **Sync and async APIs** — `Grover` (sync facade) and `GroverAsync` (async core).
- **Event-driven architecture** — EventBus for internal consistency.
- **Result types** — Structured return types for all operations.
