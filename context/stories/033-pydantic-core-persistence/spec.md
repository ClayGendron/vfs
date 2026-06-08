# 033 — Pydantic Domain Model over SQLAlchemy Core (with stable id references)

- **Status:** draft
- **Date:** 2026-06-08
- **Owner:** Clay Gendron
- **Kind:** migration + architecture
- **Depends on:** 031 (unified entry chokepoint), 032 (`VFSPath` typed path
  handle), 010 (align primitives — `VFSEntry`/`Candidate`), 008 (plan9 object
  model), 025 (modularized write pipeline)
- **Enables:** an unambiguous attached/detached boundary; a rename-stable graph
  and directory tree; per-mount schema minting without metaclass magic; the
  `path: VFSPath` typing that SQLModel made unsafe on the read path

## Intent

Replace **SQLModel** as the entry persistence layer with two purpose-built
pieces:

1. a **pure Pydantic `VFSEntry`** — the internal domain/value model, holding
   human-readable paths, validated on construction, never bound to a session;
2. **SQLAlchemy 2.0 Core** `Table`s minted per mount — owning schema (DDL) and
   all database I/O — fronted by a thin **repository/mapper** that is the only
   code allowed to touch a `Session`.

Riding on that boundary, change four columns from **path strings to stable id
references** — `parent_dir`, `parent_file`, `source_path`, `target_path` become
`parent_dir_id`, `parent_file_id`, `source_id`, `target_id` in the database —
while the Pydantic `VFSEntry` continues to expose all four as human-readable
paths. Paths stay the human projection; ids become the stable relational
backbone.

This story is the migration plan; the architecture is in
[`design.md`](./design.md).

## Why — the friction

The team's stated pain is **not** typing noise or upstream risk. It is that a
single `VFSEntry` is *sometimes a plain Python value and sometimes a live,
session-attached ORM row*, and nothing in the type tells you which. Keeping
track of which instances are detached vs. bound to a session — and keeping
internal Python data separate from db-bound session state — has been a recurring
source of bugs.

That is an ORM unit-of-work problem, and SQLModel causes it by fusing "Pydantic
value" and "SQLAlchemy ORM entity" into one class. Two facts make the split the
right call:

- **Read-path validation is not required** ("write-only is fine"). The one
  reason to keep value and entity fused — validate-on-load — does not apply, so
  fusing them buys nothing and costs the lifecycle ambiguity.
- **The ORM dependence is shallow and partly already-Core.** An audit of
  `backends/database.py` found **no** `relationship()`, lazy/eager loading, ORM
  `cascade=`, `.merge()`, or identity-map reliance; `expire_on_commit=False` is
  set (opting *out* of ORM lifecycle). The only ORM usage is `session.add` /
  `flush` / `session.delete` and `.scalars().all()` returning attached entities —
  and the gram index already runs on pure Core `insert`/`update`/`delete`. The
  `.scalars()` attached-entity read is the direct cause of the confusion.

Making attachment a property of the *type* removes the ambiguity by
construction: hold a `VFSEntry` → it is detached internal data, always; the
session-bound representation is a database row that never escapes the repository.

The id-reference change is motivated separately (and detailed in
`design.md §4`): path strings are a fragile foreign key. A move of `/a` → `/b`
today must rewrite every descendant's `parent_dir`/`parent_file` and every edge
`source_path`/`target_path` that embeds the moved prefix, found by fragile
`LIKE` matching. Stable ids make the *relationships* survive renames untouched,
and make the rows a move *does* still have to rewrite (the materialized `path`
strings) findable by exact id lookup instead of prefix scans.

## Current state

- `VFSEntry(SQLModel)` is `table=False`; each mount mints a `table=True`
  subclass at runtime via `SQLModelMetaclass` in `_build_vfs_tables`
  (`models.py`), alongside two hand-built Core `Table`s for the gram index.
- The entry carries path-string relationship columns: `path` (unique),
  `parent_dir: str`, `parent_file: str | None`, `source_path: str | None`,
  `target_path: str | None`, plus `name`, `kind`, content/metric/version/edge/
  embedding columns (`models.py:95`–`148`).
- Backends read with `session.execute(select(...)).scalars().all()` (attached
  entities) and write with `session.add(...)` + `session.flush()` /
  `session.delete(...)`, with app-level (not ORM) cascade
  (`backends/database.py`).
- Validation + path derivation run in the `@model_validator(mode="before")`
  `_normalize_and_derive`, which now routes through `resolve_path` and derives
  `name`/`parent_dir`/`parent_file`/`source_path`/`target_path` from the
  canonical path (story 032 work).

## Target state

- **`VFSEntry` is a pure `pydantic.BaseModel`.** Same public field shape
  (path-named relationship fields), same pure methods (`chunk`,
  `plan_file_write`, `set_version`, `to_candidate`, version reconstruction), same
  construction-time validation. No SQLAlchemy base, no `table=True` subclassing,
  no `_sa_instance_state`. `clone()` becomes `model_copy()`.
- **A Core table factory** (`build_entry_table(...)`) returns a SQLAlchemy 2.0
  `Table` (entry) plus the two gram `Table`s on one `MetaData`, replacing
  `_build_vfs_tables`'s `SQLModelMetaclass` path. Per-mount minting stays;
  it is just Core, which is built for runtime construction.
- **A repository/mapper** is the sole `Session` holder. It maps domain ⇄ row,
  resolves path↔id at the seam, runs Core statements, and returns **detached
  Pydantic** `VFSEntry`/`Candidate` objects. No session-attached object crosses
  into business logic.
- **The entry table stores id references, not relationship paths:**
  `parent_dir_id`, `parent_file_id`, `source_id`, `target_id` (indexed,
  self-referential to `id`). `path` remains the unique materialized key; `name`
  and `kind` remain. The path-string relationship columns are dropped from the
  table.
- **`VFSEntry` still exposes paths, typed `VFSPath`.** `path`, `parent_dir`,
  `parent_file`, `source_path`, `target_path` are all `VFSPath`
  (`VFSPath | None` where nullable); the relationship paths are reconstructed
  from the entry's own `path` (pure `paths.py` functions — no join). The id
  columns serve queries, cascade, and rename-stability, not hydration.

## Scope

### In

1. Pure-Pydantic `VFSEntry` (drop the SQLModel base; preserve fields, validators,
   and pure methods).
2. Core `Table` factory replacing `_build_vfs_tables` (entry + gram tables, one
   `MetaData`, per-mount), **keeping path-string relationship columns first** to
   isolate the ORM→Core change from the id-reference change.
3. Repository/mapper layer owning the `Session`; convert `backends/database.py`
   (and the Postgres/MSSQL subclasses) reads/writes/deletes to go through it.
   This is the step that removes session-attachment.
4. The id-reference change: add `*_id` columns, backfill from paths, resolve
   path↔id in the mapper, flip child-enumeration and graph traversal to id-based,
   drop the path-string relationship columns.
5. A **dialect-agnostic id-return mechanism** (SELECT-by-unique-`path` primary,
   `RETURNING` optimization where proven), confirmed by code and tests on SQLite,
   Postgres, and MSSQL.
6. **App-managed hard-delete cascade by id**: removing a node removes its
   id-referenced dependents (chunks/versions/edges via `parent_file_id`, incident
   edges via `source_id`/`target_id`) and purges affected `doc_id`s from the
   packed posting lists; soft-delete is unchanged.
7. Move/rename reworked to use `source_id`/`target_id` to find affected edge
   `path`s for rewrite (replacing `LIKE`-prefix edge discovery).
8. Port the relevant `tests2/` suites into `tests/` against the new model (see
   `CLAUDE.md` — `tests2/` is stale reference only).

### Out

- **No change to the `VFSEntry` public field shape** above the repository:
  callers keep reading/writing `path`, `parent_dir`, `parent_file`,
  `source_path`, `target_path` as `VFSPath` (`VFSPath | None` where nullable).
  The whole point is that the domain surface is insulated from the storage
  change.
- No read-path revalidation (write-only validation stands; reads use
  `model_construct`).
- No new ORM (we are removing it, not swapping it).
- No change to chunking, versioning, BM25/trigram, embedding, or permission
  semantics beyond what the persistence seam requires.
- No move to a pure-inode (id-only, `path` computed) model — `path` stays
  materialized for prefix queries; the pure-inode option is recorded as a road
  not taken in `design.md §9`.

## Reversal plan

The migration is **reversible by construction** because path and id are mutually
derivable: a row's relationship paths are computable from its `path`, and the
ids are the rows whose `path` equals those derived paths. So:

- **Code:** the domain model's public shape is unchanged, so reverting is
  swapping the repository/table implementation back; callers above the seam are
  untouched. The repo is mid-refactor (tree not green, per `CLAUDE.md`), and
  per-mount tables are minted fresh — reversal is reverting the commits, not a
  schema downgrade dance.
- **Data:** to roll the schema back, rebuild the path-string relationship
  columns from each row's `path` (pure derivation); to roll forward again,
  rebuild the `*_id` columns from the path→id map. Both directions are lossless.

## Acceptance criteria

1. `VFSEntry` is a `pydantic.BaseModel` with no SQLAlchemy base and no
   `table=True` subclass; constructing one never touches a `Session`.
2. No code path returns a session-attached object into business logic; every
   `VFSEntry`/`Candidate` handed to a caller is a detached Pydantic instance.
3. The entry table is a SQLAlchemy 2.0 Core `Table` minted per mount; DDL for
   entry + both gram tables is provisioned by one `create_all`.
4. The entry table stores `parent_dir_id`, `parent_file_id`, `source_id`,
   `target_id` (indexed) and **not** the path-string relationship columns; `path`
   remains unique.
5. `entry.path` and `entry.parent_dir`/`parent_file`/`source_path`/`target_path`
   are `VFSPath` (`VFSPath | None` where nullable), derived from `path` with no
   database join.
6. Child enumeration and graph traversal use id columns; a move/rename rewrites
   only the moved subtree's `path`/`name` (+ affected edge `path`s found via id),
   never unrelated relationship columns.
7. Write batches resolve referent ids correctly within one transaction
   (including a file written together with its version/chunks/edges), with stable
   `id` returned for posting-list `doc_id`.
8. The id-return mechanism is verified by tests on **SQLite, Postgres, and
   MSSQL**, with the SELECT-by-`path` path correct on all three.
9. Hard-delete of a file removes its chunks, versions, and incident edges (by
   id) and purges their `doc_id`s from the posting lists; soft-delete leaves
   references intact.
10. Ported `tests/` suites pass for models and the database backend; Postgres and
    MSSQL backends inherit the shared repository without copy-paste.

## Rollout (summary; sequenced in `design.md §10`)

- **Phase 1 — persistence migration (ORM → Pydantic + Core):** steps In-1
  through In-3, with relationship columns still path strings. Removes
  session-attachment; no schema-semantics change. Independently shippable.
- **Phase 2 — stable id references:** steps In-4 and In-5. Adds the id backbone,
  flips queries, drops path-string relationship columns, reworks move/rename.

Phase 1 is the one that resolves the stated pain; Phase 2 delivers the
rename-stable graph. Keep them separate so two large changes are never entangled
in one diff.
