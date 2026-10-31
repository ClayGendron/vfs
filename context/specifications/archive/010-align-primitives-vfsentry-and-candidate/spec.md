# 010 — Align storage and result primitives: `VFSEntry` and `Candidate`

- **Status:** draft (revised 2026-04-23 — scope expanded)
- **Date:** 2026-04-23
- **Owner:** Clay Gendron
- **Kind:** migration (primitive alignment; storage-model closure; result-type rename)
- **Depends on:** Constitution Article 1 (Primitives), Article 4 (backend-agnostic contract), story 001 (unified `VFSResult`), story 008 (object model for metadata entries)
- **Amends:** Constitution Article 1 — promotes `Candidate` to a fifth primitive; restates Article 1.2 as the full persisted record.
- **Backwards compatibility:** none. Breaking rename across code, docs, MCP output keys, and constitutional primitives. No aliases, no shims, no re-exports, no deprecation warnings.

## Scope note — what changed from the original draft

The original draft of this story covered the rename `VFSObject` → `VFSEntry`, the deletion of `VFSObjectBase`, and the removal of the `model=` constructor argument. Two decisions made during spec review required expanding scope:

1. **Per-mount storage class.** Instead of a single module-level `VFSEntry(table=True)`, `VFSEntry` is a `SQLModel` with `table=False`, and each filesystem mount mints a private `table=True` subclass at construction time. This dissolves the shared-SQLAlchemy-registry problem and removes the need for a `(table_name, schema, native_vector_config)` cache.
2. **Entry vs. Candidate.** The current result-row type `Entry` (in `src/vfs/results.py`) is actually a *partial view produced at query time*, not the full namespace record. It becomes `Candidate`. `VFSEntry` is the full record — everything needed to compose and query an entry in the namespace. `Candidate` is a narrow projection carrying only what a search or traversal surfaces. Both are first-class; they occupy different roles.

This story now covers all three renames (`VFSObject` → `VFSEntry`, `Entry`-result → `Candidate`, storage-class split) as one coherent change, because splitting them would require two back-to-back breaking releases in the same area.

## Intent

After this story:

1. There is **one** storage-shape SQLModel class: `VFSEntry` with `table=False`. It carries every field a persisted namespace row needs. No `VFSEntryBase`. No dev-side subclassing for the public API.
2. Each `DatabaseFileSystem` / `MSSQLFileSystem` / Postgres-variant filesystem mints its own `table=True` subclass of `VFSEntry` at construction time, scoped to that instance's `table_name`, `schema`, and (for Postgres) `NativeEmbeddingConfig`. These generated classes are private — developers never see them, import them, or type against them.
3. The `model=` constructor argument is removed from every filesystem (`DatabaseFileSystem`, `MSSQLFileSystem`, any Postgres-specific filesystem, `RustworkxGraph`, `VFSClient*`). Developers do not supply a model class.
4. `table_name: str = "vfs_entries"` and `schema: str | None = None` are the two storage-shape knobs on `DatabaseFileSystem`. Native pgvector configuration is a separate constructor argument on the Postgres filesystem (`native_embedding: NativeEmbeddingConfig | None`).
5. The result-row type is renamed `Entry` → `Candidate`. `VFSResult.entries` → `VFSResult.candidates`. `ENTRY_FIELDS` → `CANDIDATE_FIELDS`. Every consumer (renderer, projection validator, MCP tool, docs example) is updated.
6. The constitution is amended in the same PR: Article 1.2 is restated to describe `Entry` as the full persisted record, and a new Article 1.5 defines `Candidate` as the query-time partial view. The primitive count goes from four to five.
7. All call sites, imports, docstrings, tests, fixtures, and external-facing documentation use the new names. `vfs_objects` → `vfs_entries`; `VFSObject` → `VFSEntry`; `Entry` (result) → `Candidate`; `VFSObjectBase` → deleted.

## Why

### 1. Primitive alignment with the constitution

Article 1 names the primitives of VFS. Two names in the codebase drifted from the primitive they were supposed to represent:

- **`VFSObject` / `VFSObjectBase`** is an artifact of the earlier providers/mixins era. The row on disk is the persisted form of the namespace primitive the constitution calls `Entry` — it is not a separate concept. Keeping two names for one concept means every doc, every type annotation, and every code review has to translate between them, and translation is where bugs hide.
- **`Entry` (the result-row type in `results.py`)** is misnamed for what it actually is. A query does not return "entries"; it returns *candidates* — partial observations that match the query, carrying only the fields the query populated. The constitution's original Article 1.2 even admitted this: "It is not the object — it is what an operation returned about it, at the moment it returned." That is the definition of a candidate, not a record.

Keeping the misnaming costs us on every axis the constitution measures:

- **Agent legibility.** An agent reading the MCP surface sees a field called `entries`; an agent reading the Python API sees a row class called `Entry`; the durable shape behind both has been called `VFSObject`. Three names for two concepts means the contract leaks implementation history into every interaction.
- **Plan 9 / Unix lineage (Article 3).** The tradition separates the durable record (`inode` / `dirent`) from the transient observation (`stat` struct, `readdir` entry). Using one name for the durable record and a different name for the query-time observation is exactly the discipline this article imports.
- **Backend-agnostic contract (Article 4).** When every backend speaks in terms of `VFSEntry` (persisted) and `Candidate` (returned), the contract is uniform. When one backend has `VFSObject` and another has `VFSEntry`, or when the result row is also called `Entry`, the public surface leaks history.

### 2. Close the model, per-mount, to eliminate a configuration axis

`VFSObjectBase` exists today so that `postgres_native_vfs_object_model()` can build a dynamic subclass with a native pgvector column. The dynamic subclass is cached at module level by embedding parameters. This creates two problems:

- The `type[VFSObjectBase]` annotation threads through every filesystem, every helper, and every call site. It exists to support one legitimate use case (pgvector column swap) plus a hypothetical "user brings their own model" extension the project has decided it does not want.
- A second mount with a different table name wants a different `table=True` class, which wants different SQLAlchemy metadata, which today means either threading another dynamic subclass through the constructor or sharing a global registry that does not model per-mount isolation.

Making `VFSEntry` a `table=False` SQLModel and letting each filesystem mint its own `table=True` subclass at construction time solves both:

- Developers never see a base vs. concrete split. `VFSEntry` is the only class they import, annotate against, or mention in a docstring.
- The `table=True` class is an implementation detail of the filesystem. It is keyed on the filesystem's own construction arguments — not a module-level cache — so two filesystems with different `table_name` or different `NativeEmbeddingConfig` do not share state.
- The `model=` argument disappears from public constructors entirely. Shape is not a deployment knob.

### 3. Entry vs. Candidate — distinct primitives with distinct jobs

The constitution's original description of Entry bundles two different things:

> An **Entry** is one row describing one observation of an object in the namespace. It is not the object — it is what an operation returned about it, at the moment it returned.

That is the definition of the *observation* primitive. But the constitution uses "Entry" elsewhere to mean the durable shape that makes a row addressable in the namespace. The codebase inherited the conflation. Splitting them gives each its own coherent definition:

- **`VFSEntry`** — the full record. Carries every field needed to compose the row in the namespace, including the ones that do not travel in query results (for example, persisted content bytes, edge endpoints, embedding vectors). Used for writes, reads of a known path, and as the persistence shape.
- **`Candidate`** — the query-time partial view. Carries only the fields the query populated: always `path`, `kind`, `revision`; optionally `score`, `content`, `lines`, `size_bytes`, `in_degree`, `out_degree`, `updated_at`. A null field on a Candidate means "not populated by this call," never "absent on the record." A Candidate can always be hydrated into a `VFSEntry` by path; a `VFSEntry` can always be projected to a `Candidate` by dropping fields.

This mapping also maps cleanly onto agent mental models: an agent searches and gets back *candidates* that match; it acts on the full *entry* when it decides to read, write, or edit.

### 4. Table name as the one allowed knob

Multi-tenant deployments and environments that run more than one VFS instance against the same database need to separate tables. `schema` already gives them one axis; `table_name` gives them the orthogonal axis. Concretely:

- Two VFS instances against one Postgres database, same schema, different corpora: `vfs_entries_snhu` and `vfs_entries_research`.
- A hosted deployment where the customer picks their own table name by policy.
- Tests that spin up an isolated table without isolating the schema.

`table_name` is **not** a place where semantics change. The row shape is `VFSEntry` regardless of table name. It is pure routing metadata, at the same level as `schema`.

## Constitution amendment (ships in this PR)

Article 1 is updated in this story. Exact text lives in `context/constitution.md`; the diff is bounded to:

### New Article 1.2 — Entry (restatement)

> An **Entry** is the full record of one object in the namespace. It is everything needed to compose that object in the namespace and to query against it. (`src/vfs/models.py:<line>`.)
>
> An Entry is fully described by:
>
> - `path` — absolute, normalized, canonical identity. MUST be unique within its terminal filesystem.
> - `kind` — closed enum: `file | directory | chunk | version | edge | tool | api` (`src/vfs/paths.py:30`).
> - `revision` — the coherence stamp for this Entry (see §1.4). MUST be populated on every Entry.
> - The remaining persisted fields that make the Entry queryable: content or content pointer, size, timestamps, embedding, edge endpoints (when `kind=edge`), and any other field required to reconstruct or query the row.
>
> Entries MUST live in the namespace at a single, normalized path. New object kinds extend the `kind` enum; they MUST NOT live outside it. Storage representations of an Entry (SQL rows, object storage keys, graph nodes) are implementation details; the Entry is the logical primitive.

### New Article 1.5 — Candidate

> A **Candidate** is one row describing one observation of an Entry, as returned by an operation on the namespace. It is not the Entry — it is what an operation returned about it, at the moment it returned. (`src/vfs/results.py:<line>`.)
>
> A Candidate is fully described by:
>
> - `path` — absolute, normalized. MUST reference a location in the caller's namespace.
> - `kind` — the same closed enum as Entry.
> - `revision` — the coherence stamp at the moment the Candidate was produced. MUST be populated on every Candidate.
> - Zero or more populated query-time fields (`content`, `lines`, `size_bytes`, `score`, `in_degree`, `out_degree`, `updated_at`).
>
> **A null field means "not populated by this call," never "absent on the Entry."** A consumer MUST NOT infer the truth of an attribute from a null. Candidates are frozen; enrichment returns a new Candidate. Hydrating a Candidate into its full Entry MUST be a path lookup in the terminal filesystem — never a hidden handle or opaque id.

### Article 1.1 update

Preamble in Article 1: "VFS has **five** first-class primitives." Reorder list to: Namespace, Entry, Candidate, Mount, Revision. (Candidate sits between Entry and Mount because it is the read-side counterpart of Entry; Mount and Revision remain where they are.)

### Article 2 update

§1 (One envelope): `VFSResult` carries `candidates`, not `entries`. Example code and citation (`src/vfs/results.py:<line>`) updated.

§4 (Composable results): set-algebra description unchanged in spirit; "entries" → "candidates" throughout.

### Article 1.3 and 1.4 updates

Cross-references to "Entry" that actually meant "the result row" are changed to "Candidate." The revision stamp still lives on both Entry (persisted) and Candidate (as carried on the returned row).

## Research — what the constitution already tells us

- Article 1 says every first-class primitive must be addressable inside the one canonical namespace. `VFSEntry` is clearly namespace-addressable (by path). `Candidate` is addressable too — via the Entry it observes — so promoting it is consistent with the primitive definition.
- Article 4 says "extensions MUST be exposed as new named operations, never as overloads of existing ones." The same discipline applies to types: a backend that wants a specialized column shape does not get to ship a specialized model class; it declares a capability, and the capability adds a field to `VFSEntry` or configures the Postgres-specific column type via `NativeEmbeddingConfig`.
- Article 2 §1 says every public operation returns `VFSResult`. After this story the MCP and Python surfaces still return `VFSResult`; the only change on the envelope is the row field name (`entries` → `candidates`).

## Scope

### In

1. Rename the Python identifier `VFSObject` → `VFSEntry` everywhere. No alias, no re-export.
2. Delete `VFSObjectBase`. The field set folds into `VFSEntry`. `VFSEntry` is a `SQLModel` with `table=False` — it carries fields, validators, and pure-data methods, and is **not** itself directly writeable.
3. Delete the module-level `VFSObject(..., table=True)` class. No `table=True` class exists at module scope.
4. Inside `DatabaseFileSystem.__init__`, mint a private `table=True` subclass of `VFSEntry` bound to `(table_name, schema)` for that instance. The subclass MUST be invisible on the public surface — not exported, not returned from public methods, not surfaced in error messages except as `__tablename__`.
5. Rename the default `__tablename__` from `vfs_objects` → `vfs_entries`. Rename the index `ix_vfs_objects_ext_kind` → `ix_vfs_entries_ext_kind`. Rename module-private symbols (`_POSTGRES_NATIVE_MODEL_CACHE`, `postgres_native_vfs_object_model`, `resolve_embedding_vector_type`, `postgres_vector_column_spec`) to use `entry` instead of `object`.
6. Remove the `model=` constructor parameter from `DatabaseFileSystem`, `MSSQLFileSystem`, `VFSClient*`, and `RustworkxGraph`. Callers MUST NOT supply a model class. Removing this parameter is a breaking API change; the release notes call it out.
7. Add a `table_name: str = "vfs_entries"` constructor parameter to `DatabaseFileSystem` (and by inheritance to `MSSQLFileSystem`, any Postgres-specific filesystem). It sits alongside `schema`.
8. Replace `postgres_native_vfs_object_model()` with a `native_embedding: NativeEmbeddingConfig | None = None` constructor argument on the Postgres-specific filesystem. When present, the filesystem's minted `table=True` subclass declares `embedding` with a native `Vector(dimension)` column and the configured index method. `NativeEmbeddingConfig` lives in `src/vfs/vector.py`.
9. Rename the result-row type `Entry` → `Candidate` in `src/vfs/results.py`. Rename `ENTRY_FIELDS` → `CANDIDATE_FIELDS`. Rename `VFSResult.entries` → `VFSResult.candidates`. Update `.entries` properties in chaining methods (`sort`, `top`, `filter`, `kinds`, set algebra) to use the new field name.
10. Update every import, type annotation, docstring, and comment: `type[VFSObjectBase]`, `Sequence[VFSObjectBase]`, `list[Entry]`, `Entry(...)`, `result.entries`, `ENTRY_FIELDS`, etc.
11. Update the entire test suite and every fixture. Rename fixtures that use the old names; tests that constructed a filesystem with `model=` now pass `table_name=` (or omit it for the default).
12. Update `src/vfs/columns.py` documentation and any column-mapping comments that reference `VFSObjectBase`.
13. Update the constitution: Article 1 preamble ("five first-class primitives"), rewritten Article 1.2 (Entry = full record), new Article 1.5 (Candidate), Article 2 §1 row-field rename, and every cross-reference between the two.
14. Update `docs/`, `README.md`, `Grover_The_Agentic_File_System.md`, `examples/`, and every architecture memo. Update the MCP tool docs (if any) for the `candidates` output field.
15. Update memory pointers in `/Users/claygendron/.claude/projects/-Users-claygendron-Git-Repos-grover/memory/MEMORY.md` that reference `vfs_objects` or Entry-as-result-row (notably `project_everything_is_a_file.md` and `project_architecture_v2.md`).
16. `CHANGELOG.md`: record this as a `### Breaking` change, link to this spec, and enumerate the three renames and the constitution amendment.
17. Add a migration note (no script) describing the one-time rename a user must run if they have an existing `vfs_objects` table they want to preserve. One short paragraph; lives in the story folder.

### Out

1. **No data migration script.** Per the project's standing rule (`feedback_no_migration_scripts.md`), the dev is responsible for their data lifecycle. We document the rename they must run; we do not ship it.
2. **No backward-compatibility layer.** No `VFSObject = VFSEntry` alias, no `Entry = Candidate` alias, no `from vfs.models import VFSObject` shim, no `DeprecationWarning`, no `entries` property on `VFSResult` that mirrors `candidates`, no `table_name="vfs_objects"` default as a compatibility mode.
3. **No changes to the `kind` enum.** Kinds remain `file | directory | chunk | version | edge | tool | api`. This story is about the envelope and the primitive names, not the contents.
4. **No new capability declarations.** `SupportsNativeVector` is not introduced here; if the Postgres filesystem needs to declare the capability explicitly, that is a follow-on.
5. **No cross-filesystem rename.** Mounting an existing mount with a custom table name at runtime is not supported by this story beyond what `table_name` already offers at construction time.
6. **No configuration discovery.** There is no auto-detection of an existing `vfs_objects` table. If the developer wants the old name, they pass `table_name="vfs_objects"` explicitly.
7. **No `Candidate` → `Entry` hydration helper in this story.** Callers that need the full record call `vfs.stat(path)` or `vfs.read(path)`. Whether to ship a `candidate.hydrate()` convenience is a separate design decision.
8. **No renaming of `VFSResult`.** Envelope name stays. Only the row-field name and row-type name change.
9. **No projection-semantics change on `Candidate`.** `default`, `all`, and function-specific defaults behave as they do today — they operate on the new `CANDIDATE_FIELDS` set.

## Core types

### `VFSEntry` — full record, not-directly-persisted

```python
from sqlmodel import SQLModel

class VFSEntry(SQLModel, table=False):
    """The full record of one object in the namespace (Article 1.2).

    VFSEntry carries every field required to compose and query a row. It is
    table=False so that each filesystem mount can mint its own table=True
    subclass scoped to its own (table_name, schema) — see DatabaseFileSystem.
    """

    # Identity, kind discriminator, content fields, metrics, timestamps,
    # edge fields, embedding — every field that lives on VFSObjectBase today
    # folds directly into VFSEntry.
```

No `VFSEntryBase`. No separate `VFSEntry` base class. No module-level `table=True` variant.

### Per-mount `table=True` subclass

`DatabaseFileSystem.__init__` builds its own concrete class:

```python
fs = DatabaseFileSystem(engine=engine, schema="public", table_name="vfs_entries")
# Internally:
#   self._entry_model = _build_entry_table_class(
#       base=VFSEntry,
#       table_name=self._table_name,
#       schema=self._schema,
#       native_embedding=None,   # set by Postgres subclass
#   )
```

Invariants:

- The generated class is assigned to a private attribute (for example `self._entry_model`) and used for every SQL operation that needs a table-bound class.
- Same fields as `VFSEntry`. Same indexes (renamed to match `table_name`). Same validators.
- Two filesystems with the same `(table_name, schema, native_embedding)` against the same engine MUST NOT produce colliding SQLAlchemy metadata. Implementation MAY cache by a private per-filesystem-class key; MUST NOT share a module-level global that other filesystems can observe.
- The generated class is never returned from a public method, never assigned to a public attribute, never accepted as an argument.

### `NativeEmbeddingConfig` — Postgres pgvector knob

```python
@dataclass(frozen=True)
class NativeEmbeddingConfig:
    dimension: int
    index_method: Literal["hnsw", "ivfflat"] = "hnsw"
    operator_class: str = "vector_cosine_ops"
```

Lives in `src/vfs/vector.py`. The Postgres filesystem accepts it and uses it to shape the generated `table=True` class's `embedding` column.

### `Candidate` — query-time partial view

```python
from pydantic import BaseModel, ConfigDict

class Candidate(BaseModel):
    """One observation of an Entry, as returned by an operation (Article 1.5).

    A null field means 'not populated by this call,' never 'absent on the Entry.'
    Candidates are frozen; enrichment returns a new Candidate.
    """

    model_config = ConfigDict(frozen=True)

    path: str
    kind: str | None = None
    revision: str | None = None        # Article 1.4 — MUST be populated on returned rows
    lines: list[LineMatch] | None = None
    content: str | None = None
    size_bytes: int | None = None
    score: float | None = None
    in_degree: int | None = None
    out_degree: int | None = None
    updated_at: datetime | None = None

    @property
    def name(self) -> str: ...
```

`VFSResult.candidates: list[Candidate]`. `CANDIDATE_FIELDS = frozenset(Candidate.model_fields.keys())`.

## What this change MUST get right

These are the invariants. Violating any of them fails review.

1. **No symbol named `VFSObject` or `VFSObjectBase` exists after the change.** `grep -Rn 'VFSObject'` on `src/`, `tests/`, `docs/`, `examples/`, `context/`, and `README.md` returns zero matches. CI enforces this with a grep gate.
2. **No table named `vfs_objects` is referenced in code.** `grep -Rn 'vfs_objects'` returns zero matches (including raw SQL, index names, and error messages). Developers who want the old name pass it explicitly via `table_name="vfs_objects"`.
3. **`VFSEntry` is never `table=True` at module scope.** A static check — either a test assertion or a grep rule — ensures no module under `src/vfs/` defines a `table=True` `VFSEntry` class at import time.
4. **No module-level `_POSTGRES_NATIVE_MODEL_CACHE` (or renamed equivalent).** The old module-level cache of dynamic subclasses is removed. Any caching of generated `table=True` classes is a private instance-level concern of the owning filesystem.
5. **No `model=` parameter exists on any public filesystem constructor.** `DatabaseFileSystem.__init__`, `MSSQLFileSystem.__init__`, any Postgres-specific filesystem constructor, `RustworkxGraph.__init__`, and `VFSClient*` constructors do not accept `model`. Calling with `model=...` raises `TypeError` (unexpected keyword argument).
6. **`VFSEntry` is the only public storage class.** Generated per-mount siblings are private, and never returned from a public function or appear in a public annotation.
7. **`table_name` is the only storage-shape knob exposed to developers** (alongside `schema` for routing and, on Postgres, `native_embedding` for column specialization). Field additions, column types outside the native-embedding config, indexes, and validators are not configurable at construction time. A developer who needs a different shape is asking for a contributor amendment to `VFSEntry`.
8. **`schema` and `table_name` compose orthogonally.** Any combination of `(schema, table_name)` is valid.
9. **No symbol named `Entry` exists as a result-row type.** `grep -Rn '\bEntry\b'` on `src/vfs/results.py`, `src/vfs/base.py`, `src/vfs/client.py`, and the rest of `src/` returns zero matches *when referring to the query-result row type*. (Matches on the word "Entry" inside `VFSEntry` identifiers, docstrings describing the primitive, or the constitution are expected and fine.)
10. **`VFSResult.entries` no longer exists.** The field is `candidates`. JSON output from `result.to_json()` uses key `"candidates"`. A caller reading `result.entries` raises `AttributeError`.
11. **`ENTRY_FIELDS` no longer exists.** Renamed to `CANDIDATE_FIELDS`. Projection validator messages reference "Candidate field" wording.
12. **No aliasing.** `VFSObject = VFSEntry`, `Entry = Candidate`, `result.entries = result.candidates` are all forbidden at any level (module, package `__init__.py`, docs examples).
13. **No deprecation shim.** No `warnings.warn(...)` branch triggered by old-name usage. Old names simply do not exist.
14. **No silent default flip.** `table_name` defaults to `"vfs_entries"`. There is no environment-variable fallback to the old name, no auto-detection of an existing `vfs_objects` table.
15. **Native pgvector support is preserved.** A Postgres filesystem with a `NativeEmbeddingConfig` still produces the same pgvector index shape and the same query plans it did before.
16. **User scoping still works.** `DatabaseFileSystem(user_scoped=True, table_name="...")` behaves identically to the current `user_scoped=True` path, against the renamed and possibly renamed-by-instance table.
17. **Constitution citations are updated.** Every `src/vfs/*.py:<line>` citation in `context/constitution.md` resolves to a valid line after the rename. Specifically: Article 1.2's reference to the Entry implementation now points at `src/vfs/models.py:<line>`; Article 1.5's reference to Candidate points at `src/vfs/results.py:<line>`; Article 2 §1's reference to `VFSResult` is re-verified.
18. **Revision stamp is represented on both types.** `VFSEntry` and `Candidate` both carry `revision` (Article 1.4). If the current codebase stores revision on `VFSObject` under a different name, rename to `revision` as part of this change.
19. **Tests are renamed at the same depth.** Test files, fixtures, and helpers that name the old model, the old result type, or the old row-field are renamed. No `test_vfs_object_*` lingering, no `entries=[...]` fixtures asserting the old shape, no `@pytest.fixture` named `entry_*` that returns a result row (those become `candidate_*`).
20. **Docs and examples are updated in the same PR.** `examples/`, `docs/`, `README.md`, `Grover_The_Agentic_File_System.md`, `mkdocs.yml`-configured pages, and the constitution all name `VFSEntry` and `Candidate`. A reader browsing docs never sees the old names.

## Developer-facing surface after this change

```python
from vfs.models import VFSEntry                           # the full record
from vfs.results import Candidate, VFSResult              # the query observation + envelope
from vfs.backends.database import DatabaseFileSystem
from vfs.backends.postgres import PostgresFileSystem
from vfs.vector import NativeEmbeddingConfig

fs = DatabaseFileSystem(
    engine=engine,
    schema="public",
    table_name="vfs_entries",            # the one storage-shape knob
    user_scoped=False,
    permissions="read_write",
)

pg = PostgresFileSystem(
    engine=engine,
    schema="public",
    table_name="vfs_entries",
    native_embedding=NativeEmbeddingConfig(
        dimension=1536,
        index_method="hnsw",
        operator_class="vector_cosine_ops",
    ),
)

result: VFSResult = await fs.vector_search("auth", k=5)
for candidate in result.candidates:
    assert isinstance(candidate, Candidate)
    print(candidate.path, candidate.score)
```

There is no `model=`, no `VFSEntryBase`, no imported helper for constructing models, no `result.entries`. If a deployment needs a different table name or schema, it passes it to the filesystem constructor. If it needs native pgvector, it passes a `NativeEmbeddingConfig`. Everything else is an in-tree amendment.

## Acceptance criteria

1. `grep -Rn 'VFSObject' src/ tests/ docs/ examples/ context/ README.md` returns zero matches.
2. `grep -Rn 'VFSObjectBase' src/ tests/ docs/ examples/ context/ README.md` returns zero matches.
3. `grep -Rn 'vfs_objects' src/ tests/ docs/ examples/ context/ README.md` returns zero matches.
4. `grep -Rn 'postgres_native_vfs_object_model' src/ tests/ docs/ examples/ context/ README.md` returns zero matches.
5. `grep -Rn '_POSTGRES_NATIVE_MODEL_CACHE' src/ tests/` returns zero matches.
6. `grep -Rn 'ix_vfs_objects_ext_kind' src/ tests/ docs/ examples/ context/` returns zero matches.
7. `from vfs.models import VFSEntry` succeeds. `from vfs.models import VFSObject` raises `ImportError`. `from vfs.models import VFSObjectBase` raises `ImportError`.
8. `from vfs.results import Candidate` succeeds. `from vfs.results import Entry` raises `ImportError`.
9. `DatabaseFileSystem(model=...)` raises `TypeError` (unexpected keyword argument).
10. `DatabaseFileSystem(engine=engine)` constructs successfully and persists rows into a table literally named `vfs_entries`.
11. `DatabaseFileSystem(engine=engine, table_name="acme_entries")` persists rows into a table literally named `acme_entries`, with the same field set as `vfs_entries`. All public operations produce the same results against either instance.
12. `DatabaseFileSystem(engine=engine, schema="tenant_a", table_name="acme_entries")` addresses `tenant_a.acme_entries` on Postgres, `[tenant_a].[acme_entries]` on MSSQL, and errors clearly on SQLite (where schemas are not supported).
13. A Postgres filesystem constructed with `native_embedding=NativeEmbeddingConfig(dimension=1536, index_method="hnsw")` creates a table (named `vfs_entries` or the configured `table_name`) whose `embedding` column is a native `vector(1536)` with an HNSW index. Query plans are unchanged from the pre-rename equivalent.
14. `VFSResult().candidates` exists as a `list[Candidate]`. `VFSResult().entries` raises `AttributeError`.
15. `result.to_json()` produces an object with a `"candidates"` key. `"entries"` does not appear.
16. `isinstance(result.candidates[0], Candidate)` is True for every non-empty result.
17. Every `VFSResult` returned from a public operation carries `revision` on every candidate (Article 1.4). An integration test asserts this across grep, glob, vector_search, and stat.
18. The existing integration-test suite passes with no `@pytest.skip` additions and no new warnings. No test references the old names.
19. `uv run pytest` passes. `uvx ruff check` passes. `uvx ty check` passes.
20. `CHANGELOG.md` records this as a breaking change with the header `### Breaking` and links to this spec.
21. `context/constitution.md` has Article 1 preamble updated to "five first-class primitives," a rewritten Article 1.2, a new Article 1.5 (Candidate), and Article 2 §1 updated to cite `candidates`. All internal cross-references are consistent.
22. `MEMORY.md` (user auto-memory) and its referenced project notes no longer refer to `vfs_objects` or Entry-as-result-row; they refer to `vfs_entries` and `Candidate`.

## Rejected alternatives

- **Keep `VFSObject` as an alias for `VFSEntry`, or `Entry` as an alias for `Candidate`.** Rejected. Two names per primitive is what this story exists to eliminate. Shipping an alias reintroduces the problem.
- **Deprecation warnings on old import paths / field access.** Rejected. No backward compatibility is a first-class policy on this change.
- **Ship an Alembic migration that renames `vfs_objects` → `vfs_entries`.** Rejected per `feedback_no_migration_scripts.md`. Document the rename; the developer runs it.
- **Keep `VFSObjectBase` because some hypothetical user will want to subclass.** Rejected. Subclassing is the axis this story closes.
- **Keep the module-level `VFSEntry(table=True)` class and generate per-mount siblings only when `table_name` differs from the default.** Rejected. A module-level `table=True` class is a shared SQLAlchemy metadata node; two mounts that want the same `table_name` on different engines, or the same engine with different `native_embedding`, would still collide. Consistent per-instance minting is simpler to reason about than a mixed module-level + per-instance model.
- **Put `table_name` at mount time rather than at `DatabaseFileSystem` construction.** Rejected. Mounts compose filesystems; they don't configure their storage. The filesystem owns its table the same way it owns its engine.
- **Make `table_name` a class attribute on a subclass the developer defines.** Rejected — this is the `model=` problem in a different disguise.
- **Auto-detect `vfs_objects` and use it when present.** Rejected. Silent environment-sensitive defaults are the category of behavior Article 2 §2 was written to forbid.
- **Rename `Entry` in `results.py` to something other than `Candidate` (for example `Observation`, `Row`, `Match`).** Rejected. `Candidate` fits the query-time semantics (a match that *might* be what the caller wanted) and keeps the constitutional vocabulary agent-legible. `Observation` is too generic; `Row` overloads SQL terminology; `Match` is specific to search and does not cover read/stat results.
- **Keep `VFSEntry` as `table=True` at module scope and only mint per-mount siblings when `table_name != default`.** Rejected (see above); the mixed model is harder to audit than the uniform one.
- **Add `Entry` (the constitution primitive name) as the persisted class name, drop the `VFS` prefix.** Rejected. The `VFS` prefix signals "this is the VFS primitive, not some other framework's Entry." Consistent with `VFSResult`, `VFSClient`, `VirtualFileSystem`.
- **Split the story into three PRs (storage rename, per-mount split, Candidate rename).** Rejected. Each touches the same files; splitting produces three back-to-back breaking releases in the same area with no semantic benefit. One PR, one `### Breaking` entry, one constitution amendment.

## Open questions (resolve in plan phase)

1. **How exactly is the per-mount `table=True` subclass built?** `SQLModelMetaclass` direct call (as `postgres_native_vfs_object_model()` does today), or a lower-level SQLAlchemy registry construction, or `type(...)` with a populated `__table__`? Lean: keep the `SQLModelMetaclass` path; it already works and fits how SQLModel models its registry.
2. **Where does the per-mount class live in relation to SQLAlchemy's `registry`?** If two filesystems share an engine, do they share a registry instance? Lean: each filesystem owns its own registry; this is the most isolated, and the cost of registry duplication at runtime is negligible. Plan phase must confirm there are no cross-registry reference issues (for example, relationship() cascades, shared metadata bind).
3. **What does `revision` look like on `VFSEntry` today?** If the existing `VFSObjectBase` stores this under a different field name (`updated_at`, `version`, etc.), the plan includes a field rename. Grep and confirm before the plan is final.
4. **Does `VFSResult.set_algebra` need a `_merge_candidate` replacing `_merge_entry`?** Yes — it's just a rename, but the shape change on `.entries` → `.candidates` propagates through every method on `VFSResult`. Plan phase enumerates the 10-ish methods that need the rename.
5. **Does the CLI / MCP output contract carry `"entries"` as a documented key?** If yes, the MCP tool descriptions and any published schema need the `"candidates"` update, and the story must confirm nothing external depends on the old key.
6. **Rename the story folder?** `010-rename-vfsobject-to-vfsentry/` no longer matches scope. Optional; folder is untracked, so a rename is cheap. Lean: rename to `010-align-primitives-vfsentry-and-candidate/`.
7. **Do we ship a `Candidate.hydrate()` helper that returns the full `VFSEntry`?** Out of scope for this story; file a follow-on if demand materializes.
8. **Does `RustworkxGraph` need `VFSEntry` awareness at all after the rename?** It operated on `VFSObject` today to read edge rows. Plan confirms whether the graph still needs a row type reference or whether it can operate purely on paths.

## Dependency and sequencing notes

- This story lands **before** story 009 (sharing and access control). 009's spec references `Entry.capabilities`; after this rename that becomes `VFSEntry.capabilities` (the capability field lives on the full record, not the query view). The storage-side rename reduces 009's diff surface.
- This story **does not conflict** with story 008; 008 defines the object ontology on top of the namespace, and 008's names (`file`, `version`, `chunk`, `edge`) are kinds within `VFSEntry`.
- This story **replaces** every `type[VFSObjectBase]` annotation in the codebase — roughly 60 call sites across `base.py`, `backends/database.py`, `backends/mssql.py`, `client.py`, `graph/rustworkx.py`, and `models.py`. It additionally replaces every `Entry` (result-row type) reference, which touches `results.py`, `base.py`, `client.py`, and every test under `tests/` that asserts result rows.
- `CHANGELOG.md` version bump is a **minor or major** version — this is the kind of breaking change that justifies one. Release mechanics live in `context/standards/release.md` and are not in scope here beyond the ask that the entry be tagged `### Breaking`.

## Summary

Three renames, one coherent change:

- `VFSObject` → `VFSEntry`. The full persisted record. One class, `table=False`, minted into a private `table=True` subclass by each filesystem at construction. No `VFSObjectBase`, no `model=`, no module-level `table=True`.
- `Entry` (result row) → `Candidate`. The query-time partial view. Separate primitive, separate job, no collision with the storage name.
- Constitution Article 1 gets a fifth primitive (`Candidate`), and Article 1.2 is restated to describe the full record rather than the observation.

No aliases, no shims, no warnings, no migration script. One class per role, one name per primitive, one knob for storage shape.
