# Pydantic domain model over SQLAlchemy Core — and the id-reference backbone

*The concrete design for replacing SQLModel with a pure-Pydantic `VFSEntry` plus
SQLAlchemy 2.0 Core tables, and for moving the four relationship columns from
fragile path strings to stable id references. The sibling of
[`031`](../031-unified-entry-creation-chokepoint/design.md) (one door in front of
every row) and [`032`](../032-unified-path-resolution-chokepoint/design.md) (one
door in front of every path): this story decides **what a row physically is** and
**how identity is stored**, so those gates have a clean substrate. Read after the
spec; `VFSPath` (story 032) is assumed.*

---

## 1. The problem: one class, two lifecycles

`VFSEntry` is asked to be two incompatible things at once. As a **value** it is
internal Python data — the thing `chunk()`, `plan_file_write()`, and the write
pipeline pass around, copy, and mutate freely. As an **entity** it is a live
SQLAlchemy row, attached to a `Session`, governed by the unit of work (identity
map, autoflush, expire-on-commit, detached-instance errors). SQLModel fuses the
two into a single class, and instances drift between the states with nothing in
the *type* to say which you hold.

That drift is the team's actual pain: *"confusion between VFSEntries tied to a
session and those that are not."* A `.scalars().all()` read hands back attached
rows; a freshly constructed entry is detached; a `model_dump()`-and-rebuild is
detached again; `clone()` has to hand-wire `_sa_instance_state` to fake the
attached shape. Every boundary is a place to get it wrong.

Two facts decide the fix (see spec *Why*): read-path validation is **not**
required, and the ORM dependence is **shallow** — no relationships, no lazy
loading, no `cascade=`, no identity-map reliance, `expire_on_commit=False`, and
the gram index already on pure Core. So the value/entity fusion buys nothing and
costs the ambiguity. We unfuse them.

## 2. The model: three roles, separated by type

After this story there is no single object that is both value and entity. There
are three things, and the type you are holding tells you exactly what it is and
what lifecycle rules apply:

| role | what it is | lifecycle | who holds it |
|---|---|---|---|
| **`VFSEntry`** | pure `pydantic.BaseModel` (domain value) | detached, always; never sees a `Session` | all business logic |
| **entry `Table`** | SQLAlchemy 2.0 Core `Table` (schema + I/O) | the database; minted per mount | DDL + the repository only |
| **repository / mapper** | the one `Session`-holding seam | converts domain ⇄ row, resolves path↔id, runs statements | the backend internals |

The invariant that kills the pain: **a `VFSEntry` is, by construction, detached
internal data.** There is no attached `VFSEntry` to confuse it with, because the
session-bound representation is a *row* (a `dict`/`Row`), not a `VFSEntry`. The
repository is the membrane; nothing session-aware crosses it.

This mirrors the kernels' own split (story 031/032 surveys): the generic value
and the storage entity are different artifacts, joined at one gate. Here the gate
is the repository, and the join is path↔id (§5–§6).

`VFSEntry` keeps everything that is *pure*: the fields (path-named, §3), the
construction-time validator (`resolve_path` + derive, story 032), and the
data methods (`chunk`, `plan_file_write`, `set_version`, version reconstruction,
`to_candidate`). It loses only the SQLAlchemy base, the `table=True` subclassing,
and the `_sa_instance_state` wiring; `clone()` becomes `model_copy()`.

## 3. Path is the projection; id is the identity

The central idea of the id-reference change is a separation the current schema
conflates: **a path is how a human (and the namespace) addresses a node; an id is
how the database refers to it.** Today the relationship columns store paths, so
the database refers to nodes the way a human does — by a string that *changes
when the node moves*. That is the fragility.

The decisive observation that makes the split cheap: **all four relationship
paths are derivable from the entry's own `path`.**

| field (on the Pydantic model) | derived from `path` by |
|---|---|
| `parent_dir` | `compute_parent_dir(path)` |
| `parent_file` | `compute_parent_file(path)` |
| `source_path` (edge) | `decompose_edge(path).source` |
| `target_path` (edge) | `decompose_edge(path).target` |

These are exactly the derivations the story-032 validator already runs. On the
model they are `@computed_field` properties — derived from `path` on access,
never stored, so they are **not columns** (§7); the table carries the `*_id`
columns instead. So:

- **Hydration needs no join.** To present a `VFSEntry`, the mapper reconstructs
  the four paths from the row's `path` with pure `paths.py` functions. The `*_id`
  columns are never read to build the human-readable model.
- **The id columns are the relational backbone, not the display.** They exist for
  *queries that must be stable and fast across renames* — child enumeration,
  metadata-of-file, and graph edges — not to reconstruct paths.

So `path` is the materialized human projection (and the unique natural key); the
`*_id` columns are the stable machine identity. The two agree by construction (an
id points to the row whose `path` equals the derived path), and stay consistent
under moves because a move re-points only what physically moved (§6).

## 4. The id-reference backbone

Four columns change from path string to id, on the **table only** — the Pydantic
model keeps the path-named fields (§3):

| model field (path, kept) | table column (today) | table column (target) | indexed | meaning |
|---|---|---|---|---|
| `parent_dir` | `parent_dir: str` | `parent_dir_id: int \| None` | yes | the node's directory |
| `parent_file` | `parent_file: str \| None` | `parent_file_id: int \| None` | yes | owning file of a chunk/version/edge |
| `source_path` | `source_path: str \| None` | `source_id: int \| None` | yes | edge tail endpoint |
| `target_path` | `target_path: str \| None` | `target_id: int \| None` | yes | edge head endpoint |

`path` stays the unique key; `name` and `kind` stay strings. The columns are
self-referential to the entry table's own `id` (`BigInteger`/sqlite-`Integer`
PK), `NULL` where the relationship is absent (root has no `parent_dir_id`; files
have no `parent_file_id`; non-edges have no `source_id`/`target_id`).

**Why this is the payoff — rename stability.** Consider moving `/a` → `/b` with a
deep subtree and graph edges into it:

- *Path-string columns (today):* every descendant's `parent_dir`/`parent_file`
  must be rewritten, and every edge whose `source_path`/`target_path` embeds `/a`
  must be found by `LIKE '/a%'` (fragile, slow, false-positive-prone) and
  rewritten.
- *Id columns (target):* the `parent_dir_id`/`parent_file_id`/`source_id`/
  `target_id` values **do not change at all** — they point to the same rows,
  which kept their ids. The relationship graph is rename-invariant.

Stable ids do not make `path` itself free to rewrite — `path` is a materialized
string stored per row, so a move still rewrites the `path`/`name` of the moved
subtree, and rewrites the *projected* `path` of edges that embed a moved endpoint
(an edge's path encodes its endpoints). But the id backbone makes those rows
**findable by exact id lookup** (`WHERE source_id IN (...) OR target_id IN (...)`)
instead of prefix scanning — the rewrite set is precise and cheap to gather
(§6). The relationships survive; only the human-facing strings are refreshed.

**Physical form:** plain indexed `BigInteger`, **app-managed** integrity — no
database `ON DELETE`. Three reasons settle this over an FK with `ON DELETE
CASCADE`:

1. **Soft-delete is the common path and is an `UPDATE`.** `deleted_at` is set;
   no row is `DELETE`d, so a DB cascade would never fire on the path that runs
   most. Cascade only matters on *hard*-delete.
2. **Postings cannot be FK-cascaded.** The posting list is a *packed* per-gram
   structure (one row per gram holding many `doc_id`s), not one row per
   `(gram, doc)`. Removing a doc means editing packed blobs — application logic,
   not a foreign key.
3. **One place for cascade beats two.** Since postings already force app-managed
   cleanup, splitting the rest onto DB cascade would scatter the policy. Keep it
   whole.

### Hard-delete cascade (by id)

Soft-delete sets `deleted_at` and touches nothing else. **Hard-delete** removes a
node *and the closure of rows that depend on it*, gathered by exact id lookup
rather than path `LIKE`:

- hard-deleting a **file** `F` removes every row with `parent_file_id = F` (its
  chunks, versions, owned edges) **and** every incident edge with `source_id = F`
  or `target_id = F` (inbound/outbound graph edges that would otherwise dangle):
  `DELETE ... WHERE parent_file_id = F OR source_id = F OR target_id = F`;
- for each removed **chunk**, its `doc_id` (= the chunk's `id`) is purged from the
  packed posting lists (application logic);
- this is the same win as rename (§6): the id columns turn what was a fragile
  `/.vfs/<path>/__meta__/%` + endpoint-`LIKE` sweep into an exact, indexed
  closure. The work the cascade still has to do (purging packed postings) is
  inherently app-managed, which is why the whole cascade is.

## 5. Write: resolving path → id (the two-pass insert)

A write batch may reference rows that do not exist yet *in the same batch* (a
file written together with its first version, its chunks, and its edges). So id
resolution is a two-pass operation inside one transaction — the same shape as the
existing "fetch existing, then persist" pipeline (story 025), now with an id
backfill:

1. **Insert rows, then learn their ids.** `INSERT` the batch with `*_id` columns
   left `NULL`. Build the `path → id` map (see *id-return* below), merged with a
   lookup of any pre-existing referents fetched by `path` (parents, edge
   endpoints already in the tree).
2. **Backfill the id columns.** For each inserted row, derive its referent paths
   (pure string ops, §3), resolve them through the `path → id` map, and bulk
   `UPDATE entry SET parent_dir_id=?, parent_file_id=?, source_id=?, target_id=?
   WHERE id=?` via executemany.

This resolves intra-batch references and yields the stable `id` that the
posting-list `doc_id` depends on. Topological parent-before-child insertion is
rejected: more round-trips, and awkward for edges, which cross-reference.

**The id-return mechanism — dialect-agnostic by the unique `path`.** Rather than
depend on `RETURNING`/`OUTPUT` semantics that differ across SQLite, Postgres, and
MSSQL (and that MSSQL `OUTPUT` complicates when the native-search backends add
triggers), the **primary, universal** mechanism leans on the one thing every
dialect agrees on — `path` is `UNIQUE` and the batch's paths are known:

```text
INSERT the batch (ids autoassigned, *_id NULL)
SELECT id, path FROM entry WHERE path IN (:batch_paths)   -- build path -> id
UPDATE ... SET *_id = ... WHERE id = ...                  -- backfill
```

The `SELECT … WHERE path IN (...)` is correct on every backend and sees the
transaction's own inserts. `insert().returning(id, path)` is layered in as an
*optimization* only where it is proven to fold the SELECT into the INSERT
(Postgres, modern SQLite via SQLAlchemy 2.0 `insertmanyvalues`) — never a
correctness dependency, so a dialect that misbehaves silently falls back to the
SELECT. The mechanism (and the fallback) is confirmed by tests on all three
backends (spec acceptance §8). Isolate it behind one small repository method
(`_insert_returning_ids(rows) -> dict[path, id]`) so the per-dialect choice lives
in exactly one place.

Writes are pure Core: `session.execute(insert(entry), [m.model_dump() ...])`,
`update(...).where(...).values(...)`, `delete(...).where(...)` — the pattern the
gram index already uses. `session.add`/`flush`/`session.delete` and `.scalars()`
disappear.

## 6. Read: hydrate from `path`; move via id

**Read / hydrate.** `session.execute(select(entry)...).mappings().all()` returns
row dicts; the mapper builds detached `VFSEntry`s via `model_construct` (no
revalidation — write-only validation, spec) and reconstructs the four
relationship paths from `path` (§3). `path` is re-branded to `VFSPath` via
`VFSPath.from_storage` (cheap, no re-gate), and `parent_dir`/`parent_file`/
`source_path`/`target_path` come back as `VFSPath` (`VFSPath | None`) straight
from the `paths.py` derivations — so every path field on a hydrated `VFSEntry` is
a real `VFSPath`. Column-projected reads (the existing `load_only` sites) become
Core column selects.

**Move / rename.** The operation splits cleanly along the projection/identity
line:

- *Identity (ids):* unchanged. `parent_dir_id`/`parent_file_id`/`source_id`/
  `target_id` keep pointing at the same rows. No write.
- *Projection (paths):* rewrite `path`/`name` for the moved subtree (still
  required — `path` is materialized), and rewrite the projected `path` of edges
  that embed a moved endpoint. The affected edges are gathered by exact id —
  `WHERE source_id IN (moved_ids) OR target_id IN (moved_ids)` — not by `LIKE`.

So the id backbone turns the worst part of rename (finding and re-pointing the
graph) into an exact, indexed lookup, and shrinks what must be rewritten to the
materialized strings alone.

## 7. The table factory: Core replaces `SQLModelMetaclass`

`_build_vfs_tables` mints a `table=True` subclass per mount via
`SQLModelMetaclass` and hangs two Core gram `Table`s off its `MetaData`. The
target `build_entry_table(...)` returns three Core `Table`s on one `MetaData` —
entry + the two gram tables — keeping the per-mount minting (unique table names,
`schema`, sqlite-autoincrement, the native-embedding `VectorType` column) but as
plain Core, which is *built* for runtime construction. This also drops the
`# ty: ignore[invalid-argument-type]` noise on `sa_type=` Fields: a Core `Column`
takes its type directly. `VectorType` is already a SQLAlchemy type and carries
over unchanged.

### 7.1 The model is the domain object; the table is its persisted projection

`VFSEntry` holds everything the business logic wants — and **not every attribute
is a column.** The model is the single source of truth; `build_entry_table(model)`
generates the table from the *persisted subset*. Three categories of attribute,
only the first of which becomes a column:

| category | mechanism | column? | examples |
|---|---|---|---|
| **persisted** | `Annotated[T, Col(...)]` field | yes | `path`, `content`, `content_hash`, `ext`, `embedding` |
| **derived** | `@computed_field` property | no — derived on access | `parent_dir`, `parent_file`, `source_path`, `target_path` (from `path`, §3) |
| **transient** | `PrivateAttr` / `Col(persist=False)` | no — per-process only | `_explicit_fields`, a search `score`, dirty flags |

The rule is **opt-in**: a field becomes a column *only* if it carries a `Col(...)`
annotation. Nothing is persisted by accident — a `@computed_field` or a bare
field with no `Col` is simply not stored. This keeps "what is in the database"
legible from the model itself, which is the whole point of leaving SQLModel.

```python
def build_entry_table(model: type[BaseModel], name: str, md: MetaData) -> Table:
    cols = [Column("id", BigInteger().with_variant(Integer, "sqlite"),
                    primary_key=True)]
    for field, info in model.model_fields.items():
        col = _col_meta(info)                 # the Col(...) in Annotated, or None
        if col is not None:                   # opt-in: only annotated fields persist
            cols.append(_to_column(field, info, col))
    cols += _RELATIONSHIP_ID_COLUMNS          # parent_dir_id / parent_file_id /
    return Table(name, md, *cols)             #   source_id / target_id (table-only)
```

Divergence runs **both ways, by design**: the model has attributes the table does
not (derived paths, transient state), and the table has columns the model does not
store as fields (the `*_id` relationship columns, §4). That is the separation
SQLModel's one-class-does-both fused away. `Col(...)` is a tiny dataclass you
define — `index`/`unique`/`length`/`sa_type` — read by the generator, ignored by
Pydantic; `VectorType` (already a SQLAlchemy type) rides through it unchanged. The
function is one-directional and testable, not a metaclass — single-source columns
without the lifecycle ambiguity. The fallback (two hand-maintained definitions +
a CI drift test) stays available if the generator ever gets too clever to read at
a glance, but a ~40-column hand-mirror is the drift risk we are avoiding.

## 8. What we keep, what we drop

**Keep:** the `VFSEntry` public field shape (path-named); the story-032 validator
(`resolve_path` + derive); all pure methods; `Candidate` projection; the gram
Core tables; `VectorType` / native pgvector; per-mount table minting; app-level
cascade and soft-delete; write-only validation.

**Drop:** the SQLModel base and `table=True` subclassing; `_sa_instance_state`
wiring in `clone()` (→ `model_copy()`); `session.add`/`flush`/`session.delete`
and `.scalars()` attached-entity reads; the path-string relationship columns on
the table; `# ty: ignore` on `sa_type=`.

**Newly safe:** `path: VFSPath` on the model. Under SQLModel, `table=True` rows
skip Pydantic validation on load, so a `VFSPath` annotation lied for DB-loaded
rows (`entry.path.parent_dir` → `AttributeError`); making it safe needed a
`TypeDecorator`. A pure-Pydantic model has no load-bypass, and the repository
brands `path` via `from_storage` on hydration — so the annotation holds
everywhere with no column-type gymnastics.

## 9. Resolved questions / roads not taken

Settled across the spec and §4–§6: `parent_file` (not `parent_path`); plain
indexed `BigInteger`, app-managed cascade; `name` stays stored; dialect-agnostic
id-return by unique `path`; `VFSPath` everywhere; id change stays in this story.
The three design-level questions, now resolved:

1. **Pure-inode (id-only) is the *write*-optimized model — rejected; VFS is
   read-optimized.** Storing only `name` + `parent_dir_id` and *computing* `path`
   makes a move O(1), but it taxes every read. Path resolution — the hottest
   operation (`read`/`stat`/`open`/write-target) — becomes a root-to-leaf
   `namei` walk (N lookups or a recursive CTE) instead of one O(1) hit on the
   `path` unique index; and recursive `glob`/subtree `grep` become recursive CTEs
   instead of a single `path` prefix range scan. That is backwards for our
   workload. So `path` stays materialized (the "path enumeration" pattern), and
   the hybrid gives the planner **three** indexed read access paths — more than
   either extreme:

   | read | index |
   |---|---|
   | exact lookup (`read`/`stat`/write-target) | `path` unique, O(1) |
   | `ls` / single-level glob `*` | `(parent_dir_id, name)` |
   | recursive glob `**` / subtree `grep` | `path` prefix range scan |

   The id columns do not serve path reads; they make relationships rename-stable
   and cascade exact (§4, §6). The sole cost is a *write* one — a move rewrites
   the moved subtree's `path` strings — which is the correct side to pay on, and
   the id backbone makes even that rewrite's target set exact to find. Revisit
   only if move throughput ever dominates reads (it should not).

2. **Column source — derive the `Table` from the model (§7.1).** One source of
   truth without a metaclass: `build_entry_table(model)` reads `model_fields` and
   emits a `Column` per **opt-in** `Col(...)`-annotated field, appending the
   table-only `*_id` columns. Derived (`@computed_field`) and transient
   (`PrivateAttr` / `Col(persist=False)`) attributes are not columns, so the model
   can hold more than the table stores — and the table can hold what the model
   does not (the `*_id` columns). Hand-maintained pair + drift test is the
   fallback.

3. **`EdgeParts` carries `VFSPath`.** `decompose_edge` will return `EdgeParts`
   with `VFSPath` `source`/`target` (today `str`) so edge `source_path`/
   `target_path` hydrate typed without re-gating — a small `paths.py` follow-up
   folded in when edge hydration is wired.

## 10. Rollout

Each step is independently testable; Phase 1 (persistence) and Phase 2 (ids) stay
in separate diffs.

**Phase 1 — ORM → Pydantic + Core (resolves the stated pain):**

- **Step 1 — pure-Pydantic `VFSEntry`.** Drop the SQLModel base; keep fields,
  validator, and pure methods; `clone()` → `model_copy()`. Relationship columns
  still conceptually path strings. Test against ported model tests.
- **Step 2 — `build_entry_table` (Core).** Replace `_build_vfs_tables`'s
  `SQLModelMetaclass` with a Core `Table` factory (entry + gram tables, one
  `MetaData`), columns unchanged (path-string relationship columns) to isolate
  the ORM→Core change. Test DDL/`create_all` per backend.
- **Step 3 — repository/mapper.** Introduce the `Session`-holding seam: domain ⇄
  row mapping, `mappings()` reads + `model_construct`, Core `insert`/`update`/
  `delete` writes. Convert `database.py` (and Postgres/MSSQL) off
  `add`/`flush`/`scalars`/`delete`. **This is the step that removes
  session-attachment.** Test the database backend suite.

**Phase 2 — stable id references (rename-stable graph):**

- **Step 4 — id-return + id columns + backfill.** Land
  `_insert_returning_ids` (the dialect-agnostic SELECT-by-`path` mechanism, §5)
  and **test it on SQLite, Postgres, and MSSQL first** — it underpins everything
  after. Then add `parent_dir_id`/`parent_file_id`/`source_id`/`target_id`,
  backfill from the path→id map, and implement the two-pass insert + path↔id
  resolution in the mapper; keep the path-string columns temporarily for parity.
- **Step 5 — flip queries, cascade, drop path columns.** Move child enumeration
  and graph traversal to the id columns; implement the app-managed hard-delete
  cascade by id including posting purge (§4); rework move/rename to gather
  affected edge paths by id (§6); drop the path-string relationship columns. Test
  child listing, graph traversal, a deep move with edges, and a hard-delete
  cascade (file → chunks/versions/edges/postings).

Phase 1 ships first and on its own; Phase 2 lands behind it once the seam is
trusted, in its own diffs.
