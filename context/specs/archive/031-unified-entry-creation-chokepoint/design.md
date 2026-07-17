# The unified entry-creation chokepoint

*The concrete design for collapsing all `VFSEntry` creation behind one gate. Its
rationale — how mature filesystems (Linux `vfs_create`, BSD `VOP_CREATE`, 9P
`screate`, SQLite `sqlite3BtreeInsert`) put exactly one door in front of object
creation — lives in [`explanation.md`](./explanation.md). This document says what
VFS builds. Every `file:line` was read against the tree
(`src/vfs/backends/database.py`, `src/vfs/models.py`).*

---

## 1. The problem

VFS stores every object as a row in one table, `VFSEntry`, discriminated by
`kind ∈ {file, directory, chunk, version, edge}`. Today those rows come into
existence through **several** code paths with **different** guarantees:

- **Interactive writes** (`write()` → `_write_impl`, `database.py:1730`) mint files,
  directories, and edges through a parent-reconcile + permission gate.
- **ETL / batch indexing** (`index()` → `_chunk_pending`, `:2242`) mints **chunks**
  via a bulk insert that **skips that gate entirely**.
- **Version rows** are minted ad-hoc *inside* the persist helpers (`_insert_new:1609`,
  `_update_existing:1561`) rather than through the gate.

Every path that can bring a row into existence without passing the checks is a
**second door** — the source of the bugs and inconsistencies the gate exists to
prevent. The design collapses them into **one**: a single internal primitive,
`_mint_entries`, that enforces every invariant *before* any row is written.

Two performance constraints shape the design:

1. **Fast single-file operations** — an agent's `read`/`write` of one file must stay
   low-overhead.
2. **Fast batch uploads** — ingesting a whole knowledgebase (ETL) must keep bulk
   throughput.

The resolution, borrowed from the kernels: **unify the gate; keep the mint a small,
bulk lay-down.** The checks are shared; the row-write is a handful of bulk inserts in
one atomic transaction, the same shape for a one-row write and a ten-thousand-row
batch.

## 2. The identity model: `id` is the identity, `path` is the correlation key

Every entry has two keys, doing two different jobs.

- **`id`** (autoincrement integer primary key) is the **identity**. It is immutable
  for the life of the row, never reused, and survives rename, move, and
  soft-delete/revive — the *path* changes, the `id` does not. It is the posting-list
  `doc_id`, and it is the value every cross-reference stores. This is the one stable
  handle on "which entry."
- **`path`** (unique at the database level) is the **correlation key**: the one thing
  about a new row that is **known before insert**, client-side. It is also the
  mutable, user-facing name. The database enforces uniqueness, so by-path id recovery
  is unambiguous without a partial/live-only uniqueness scheme.

`id` is server-issued — it exists only *after* insert. That is the single awkward
fact about it, and `path` is exactly what bridges it. Because every incoming entry's
path is known up front, the gate can insert rows, recover their freshly-issued `id`s
**by path** (a `SELECT id, path WHERE path IN (...)`, or `RETURNING` where the backend
supports it portably), and wire dependents' foreign keys from those ids — **all in
one transaction, so the whole thing is atomic.** No client-minted UUID is needed:
`path` already is the before-insert correlation key, and a bulk insert does not have
to hand its ids back.

**Cross-references store `id`, never path.** `path` is a *mutable handle* — it
changes on rename and on soft-delete/revive — so it must not be the link between
entries. The reference columns are integer FKs onto `id`:

| reference | column | (was, as a path) |
|---|---|---|
| a chunk / version → its file | `parent_file_id` | `parent_file` |
| any entry → its directory | `parent_dir_id` | `parent_dir` |
| an edge → its endpoints | `source_id`, `target_id` | `source_path`, `target_path` |

The path columns (`parent_dir`, `parent_file`, `source_path`, `target_path`) remain as
the **materialized name layer** — fast for path queries, human-readable — but they are
derived, not authoritative. On a move or rename you walk the `*_id` graph to find the
affected entries and **rewrite their path columns** in one transaction; the `id` links
never change. This is what makes move correct and cheap. Because `path` is DB-unique,
a soft-deleted row still occupies its path: a later write to that path either revives
the same row or must first move/rename the tombstoned row to a reserved historical
path before minting a new row. In both cases version history remains bound to `id`, not
to whatever name currently points at that row.

> **Why `id` and not a client-minted UUID.** Earlier drafts carried an `entry_id`
> UUID so identity would be known before insert. With cross-mount graphs off the
> table, `id` is sufficient: it is stable and immutable within the database — which is
> exactly why the posting list already trusts it — and `path` covers the one thing
> `id` cannot, being a *before-insert* correlation key. So `entry_id` is dropped and
> `id` is the single identity. The cost is that creation inserts in dependency stages
> (§3 step 5) instead of one pass; the gain is one fewer column, one identity, and a
> simpler index (the trigram staging records real `doc_id`s, removing the
> `entry_id → id` JOIN from compile — §6).

## 3. The chokepoint: `_mint_entries`

One internal method is the only way a `VFSEntry` row comes into existence. It runs the
generic gate, then inserts the new rows in dependency stages. It executes **inside the
caller's transaction and never commits** — the caller owns the commit/rollback
boundary (the `sqlite3BtreeInsert` discipline: participate in the active write
transaction, do not start one). Staged or not, the whole call is atomic: all of it
commits, or the caller rolls it back.

```python
class _KindPolicy(NamedTuple):
    user_perm: bool   # does creating this kind represent a user-authored write?

# The gate auto-creates ancestor dirs for every kind (so an `auto_parents` flag
# would always be True — omitted), and it does not author dependents. The per-kind
# policy is a single meaningful bit: is the kind user-authored? It governs the
# revived-dir permission check (step 3).
_KIND_POLICY = {
    "file":      _KindPolicy(user_perm=True),
    "directory": _KindPolicy(user_perm=True),
    "edge":      _KindPolicy(user_perm=True),
    "chunk":     _KindPolicy(user_perm=False),   # machine-authored
    "version":   _KindPolicy(user_perm=False),   # machine-authored
}

class _MintResult(NamedTuple):
    minted: list[VFSEntry]              # rows as written, with server-issued `id`s
    candidates: dict[str, Candidate]

async def _mint_entries(
    self,
    entries: Sequence[VFSEntry],        # leaf entries + caller-planned dependents;
                                        # never parent dirs (the gate resolves those)
    *,
    session: AsyncSession,              # the caller's txn — the gate never commits
    op: str = "write",
    user_id: str | None = None,
) -> _MintResult:
    ...
```

The gate is a strict "mint the entries you're given, plus their ancestor dirs"
primitive. It does **not** author dependents and does **not** decide file/version
semantics — the caller plans those and passes them in (§6). The funnel, in order:

**1 — Validate, and enforce the creation preconditions.** Reuse the per-entry checks
from `_build_write_context` (`:1848-1861`): `validate_mutation_path`, reject root,
restrict `kind`, reject duplicate paths in the batch. Extract that loop into a shared
`_validate_entry_paths(entries)` so this gate and the write context call the same
code. Two structural preconditions live here so they cannot be skipped:

- **A `file` carries its `version`.** Every `kind="file"` in `entries` must be
  accompanied by its planned `version` row in the same batch; reject otherwise. This
  makes "no file mints unversioned" a gate invariant rather than a caller convention —
  a file physically cannot reach the mint without its version.
- **Dependency layering is well-formed.** Every entry's parent is either already in the
  database or present *earlier in this batch's stage order* (dirs by depth → files →
  versions/chunks/edges). Assert it. This is the manual guard for the shallow, acyclic
  dependency shape staged inserts assume; it fails loudly the day that shape breaks.
  Edges are stricter: their source and target files must already exist in the database
  before the edge is minted. The gate resolves `source_id` / `target_id` from those
  existing rows and rejects an edge whose endpoint is only being created in the same
  batch.

**2 — Walk to the parent.** Reuse `_resolve_parent_dirs(paths, session)` (`:1333`)
unchanged: it de-dups ancestors into a set, batches the lookup, **rejects a
non-directory ancestor** (the `ENOTDIR` analogue, `:1380`), and returns the missing
ancestor dirs, distinguishing brand-new from soft-deleted (revived) by `deleted_at`.
Creation is always *into a resolved parent*; callers never pass parent dirs — the gate
owns ancestry end to end.

**3 — Permission on revivals, conditioned on a principal.** For each *revived* ancestor
dir, run `check_writable(self, op, d.path)` — but only when `user_id is not None`.
`user_id` answers "who are we acting on behalf of": `user_id=None` means **system /
admin** (ETL, internal operations), where the application-level path check is
intentionally waived and the deployment's **database grants** govern. Brand-new
ancestors always pass unchecked (the writable carve-out that lets a writable subtree
exist inside a read-only mount, `:1909`).

> **The boundary that makes this safe.** The skip is sound only if `user_id=None` can
> never originate from an untrusted request. Therefore the **public, user-facing
> surface must require an authenticated principal and inject it** — it may never let
> `None` fall through — and **only internal / ETL / system entry points may pass
> `user_id=None`**. With that boundary the carve-out cannot be reached by a caller
> merely *forgetting* to thread a user. (The database layer does not replicate the VFS
> path check — it knows nothing of read-only mounts or carve-outs — so DB grants do
> not *substitute* for the check; they govern *because* the caller is trusted.) Making
> "system" an explicit, greppable principal rather than a bare `None` is the cleaner
> spelling, and it yields `created_by` provenance for machine-authored kinds for free.

**4 — Ensure the metadata root.** Call `_ensure_metadata_root(session)` (`:1395`):
idempotent, memoized (`:1402`), and race-tolerant via a `begin_nested()` savepoint
(`:1412`, a subtransaction, not a commit — safe inside the caller's txn). The savepoint
stays special (its race-tolerance is load-bearing and the root has no ancestors to
walk), but its **row-mint goes through `_mint_entry_rows`**, not an inline
`session.add` — so there is no sanctioned exception to the one-door rule.

**5 — Resolve and mint, in dependency stages.** Identity is server-issued, so creation
runs in stages — all in the caller's transaction, so still atomic:

- **Stage A — ancestors and files.** Resolve existing ancestors by path first. Insert
  missing ancestor dirs **by depth** (e.g. `/a`, then `/a/b`, then `/a/b/c`), recovering
  each depth's freshly-issued `id`s before wiring the next depth's `parent_dir_id`.
  Then insert the new files and recover their `id`s **by path**. Parents that already
  exist are resolved to their `id` by the same path lookup (and revived in place if
  soft-deleted — a mutation, §6).
- **Stage B — dependents.** Set each dependent's FK (`parent_dir_id`, `parent_file_id`,
  `source_id`, `target_id`) from the ids resolved in Stage A, then insert the versions,
  chunks, and edges.

Each stage's row-write is `_mint_entry_rows` (§4). Parents-before-children is now
literal: a child cannot be wired until its parent's `id` exists. After every staged
insert, the gate writes the recovered server-issued `id` back onto the corresponding
in-flight `VFSEntry` objects before returning `_MintResult`; downstream encode and
candidate rendering must see real ids, not merely an internal path→id map.

**What the gate reuses:** `_resolve_parent_dirs`, `_ensure_metadata_root`,
`check_writable`, `_row`. **What it owns:** the `user_perm` policy lookup, the
preconditions, the stage ordering + id recovery, and the mint dispatch.

## 4. The mint: `_mint_entry_rows`

The row-write is one bulk insert over `model_dump()` dicts. No `session.add`, no
identity map, no per-row entities. The gate calls it once per stage and recovers the
server-issued ids between stages.

```python
async def _mint_entry_rows(self, rows, session):
    if not rows:
        return
    # insert(self._model) is the ORM-enabled bulk insert: it takes dicts (no entities
    # held) but routes through the column layer, so type coercion (datetime / JSON /
    # Vector) and Python-side defaults apply. It compiles to the same insertmanyvalues
    # executemany as a raw Core insert, at the same speed.
    await session.execute(
        insert(self._model),
        [r.model_dump(exclude={"id"}) for r in rows],
    )

async def _ids_by_path(self, paths, session):
    # Recover server-issued ids after a bulk insert. Portable across backends; the
    # database-level uniqueness of `path` values makes the mapping unambiguous.
    rows = await session.execute(
        select(self._model.id, self._model.path).where(
            self._model.path.in_(paths),
        )
    )
    return {p: i for i, p in rows}
```

This is the same insert statement the ETL chunk path already runs (`:2333`), now used
for **every** creation. **The cost** of dropping the client-minted id is a small,
bounded number of round-trips per call — insert missing dirs by depth with id recovery
between depths, insert files, recover ids, then insert dependents. The number of stages
is bounded by namespace depth plus the fixed file/dependent phases, never by row count.
A single-file write is still a small handful of statements; an ETL batch is bulk
statements plus batched id lookups. **The gain** is that the trigram index now stages
real `doc_id`s (§6), so the `entry_id → id` JOIN disappears from compile.

**Bulk discipline.** Always pass a parameter *list* and let SQLAlchemy batch it —
`insertmanyvalues` splits a large list into batched statements (page size tunable via
`insertmanyvalues_page_size`), and plain executemany falls to the driver. **Never
hand-assemble a single multi-row `INSERT ... VALUES (…),(…)`**: that is the one pattern
that hits a backend's bind-parameter ceiling (Postgres caps at 65535 ≈ 4300 rows at ~15
columns). With a parameter list there are no hard-coded limits in VFS and the mint
stays portable across every SQLAlchemy backend. A backend-specific fast path (`COPY` on
Postgres) is a possible future optimization for extreme-scale ETL — not the default,
because it is not portable.

## 5. Persistence model: Pydantic + SQLAlchemy, split by DDL vs DML

The mint is "Core-shaped" but does **not** drop the mapped class. The split:

- **`VFSEntry` (Pydantic, `table=False`)** is the domain/validation model. Its
  `model_validator` derives the fields that come from the row's *own* path and content
  — `parent_dir`, `parent_file`, `content_hash`, `size_bytes`, `lexical_tokens`. (The
  `*_id` reference FKs are **not** validator-derived; they are the parent's
  server-issued `id`, set by the gate in Stage B once Stage A has run.) The derived
  fields are ordinary columns, so they appear in `model_dump()`.
- **The `table=True` subclass** (minted per mount via `SQLModelMetaclass`,
  `models.py:862`) is the **single source of truth for the schema** — `Field()` →
  `Column` carries `max_length`, `unique`, `index`, and the `BigInteger`/`Integer`
  variant. It is used for **DDL** (`metadata.create_all`) and to provide `__table__`
  for `insert(self._model)`. It is **never used to hold a row** as a mapped instance.

So: *keep the ORM model for DDL; never carry data through it.* Data is either a
`VFSEntry` (in flight) or a dict/row (in the database). One source of truth for the
column definitions — important because the tables are minted *per mount* — with the ORM
identity map off the write path entirely.

**One correctness rule this imposes:** the dicts fed to `_mint_entry_rows` must come
from **`table=False`-validated `VFSEntry` instances**, dumped `mode="python"` — never
from a re-classed `table=True` instance. SQLModel skips validators when constructing a
`table=True` object (`sqlmodel_table_construct`), so a row built that way would carry
empty/zeroed derived fields. The existing code already validates-then-reclasses for
this reason (`models.py:618-636`); the mint must build its list from the validated base
objects.

**Mutation is still on the ORM, transitionally.** Creation is Core-shaped now;
existing-row *mutation* (`apply_write_plan`, `update_content`, dir revival, the path
rewrites a move drives) still uses ORM dirty-tracking. Converting those to Core — pure
planning functions returning update dicts, then `update(table).where(...)` executemany
(the shape the ETL path already uses, `:2308-2317`) — is a separate, optional
follow-up, not a prerequisite for the gate. While both coexist in one session, the only
rule is to keep create and mutate on **disjoint rows** within a batch and to not
`get()`/relationship-load a just-inserted path later in the same transaction (a Core
insert does not register in the identity map). Routing creation through
`insert(self._model)` keeps it on the same Session abstraction as the mutations, which
keeps the coexistence clean.

## 6. How it fits the interactive write path

`_write_impl` keeps owning the **index pipeline** (chunk → encode → compile) and
**change detection**; the gate absorbs **parent resolution, permission, and the
staged mint**. Version *planning* and existing-row *mutation* stay in the caller.

**The one pipeline reordering.** Today `encode` stages trigram deltas *before* the
rows are persisted, keyed on a pre-insert identity. With `id` as the only identity, a
gram's `doc_id` is the chunk's `id`, which exists only *after* insert — so **encode
moves to after the gate's mint**. The order becomes **chunk → mint (gate) → encode →
compile**. This is a deliberate change to the pipeline sequence (the rest of it is
untouched), and it pays for itself: the staging delta-log now records real `doc_id`s,
so the `entry_id → id` resolution JOIN drops out of compile, and the staging table
loses its `entry_id` column.

**Stays in the pipeline / write context (otherwise unchanged):** `_build_write_entries`
(`:1794`), `_build_write_context` (`:1832`, minus the extracted validation loop),
`chunk(ctx)` (`:2202`), `_write_phase_validate_chunk_parents` (`:1875`),
`_stamp_chunk_versions` (`:2036`), `_classify_chunks` (`:2126`),
`_write_phase_fetch_existing` (`:1939`, including the `unchanged` short-circuit
`:2019`), `encode(ctx)` (`:2375`, now after the mint), `compile` (`:811`, minus the
JOIN).

**Moves into the gate:** parent-dir resolution + the conditional revival permission
(the old `_write_phase_resolve_parent_dirs` phase, `:1902`, disappears — the gate
resolves ancestry internally), and the `session.add` of new files, non-file entries,
and dirs (`:1610`, `:2549`, `:2586`) becomes the gate's staged bulk mint.

**Stays in the caller:**

- **Version planning** — `plan_file_write` / `apply_write_plan` / `create_version_row`
  (`models.py:401-539`). The persist phase already holds the fetched existing state the
  planner needs; it computes the v1 row (new file) or delta row (existing file) and
  hands the resulting version **rows** to the gate, with the leaves. The gate gates and
  mints; it does not author. (This is the `sqlite3BtreeInsert` shape: the primitive
  writes what it is handed; it does not decide what rows the system needs.)
- **Existing-row mutation** — revive `deleted_at`, `apply_write_plan`, `update_content`,
  the move-driven path rewrites, stale deletes. The gate is creation-only.

So the persist phase becomes: run change detection and existing-row mutations as today,
**plan** version rows as today, then hand *new leaf entries* + *planned version rows* to
one `_mint_entries(...)` call. It passes no parent dirs (the gate resolves them) and the
gate plans no versions (persist does).

## 7. How it fits the ETL path

`_chunk_pending` (`:2242`) splits cleanly along create-vs-mutate. The gate is about
creation; updates and deletes stay where they are.

- **Direct DML (mutation / deletion), unchanged:** the `chunked=True` flip (`:2308`),
  stale-chunk delete (`:2314`), carry-rename update (`:2317`), and the whole
  `_match_chunks` reconciliation (`:2303`).
- **Through the gate:** the insert of genuinely-new chunks (`:2332`) becomes
  `_mint_entries(plan.new_chunks, session=session, op="write", user_id=None)`. The gate
  inserts them, recovers their `id`s, and (encode, now downstream) stages their grams
  with those real `doc_id`s.

Throughput is unchanged — the mint is the same `insertmanyvalues` statement the path
runs today, plus one bulk `id`-by-path lookup per batch. What the new chunks *gain* by
passing the gate: parent-dir reconciliation (the `/__meta__/chunks/<version>/` dir is
materialized if missing, where today `_chunk_pending` assumes it exists) and the
`kind=chunk` policy (machine-authored: no user-permission check). The added
`_resolve_parent_dirs` SELECT de-dups and batches over the *distinct* chunk-version dirs
(`:1353`, `:1369`), so it is one batched query, not one per chunk. `user_id=None` is
correct: ETL is machine-authored.

## 8. The invariant, and how it is checked

The whole point is that there is no second door. After the change, **every**
`session.add` / `session.add_all` / `insert(<entry table>)` in `database.py` must be
lexically inside `_mint_entries` / `_mint_entry_rows`. A CI check enforces it:

```
grep -nE "session\.add(_all)?\(|insert\(self\._model|insert\(table\)" src/vfs/backends/database.py
```

| Current mint site | line | Becomes |
|---|---|---|
| version mint (file update) | `:1561` | planned in caller, **minted** through the gate |
| v1 version mint (new file) | `:1609` | planned in caller, **minted** through the gate |
| new file mint | `:1610` | gate mint |
| chunk bulk insert (ETL) | `:2333` | gate mint |
| new non-file entry (edge) | `:2549` | gate mint |
| new parent-dir mint | `:2586` | gate mint |
| metadata-root mint | `:1413` | gate mint (via `_ensure_metadata_root`) |

The check is about *where rows are minted*, not where they are planned — a version row
planned in the caller still passes, because its insert happens in the gate. **Not**
entry mints, and excluded: `insert(self._gram_table)` (`:2410`, `:2477`, the trigram
delta-log — which now carries the real `doc_id`), the posting-list writes in compile,
and every `session.execute(update(...))` / `session.delete(...)` (mutation/deletion,
which the gate deliberately does not own). The invariant is precisely "every `VFSEntry`
row is born in the gate."

## 9. Rollout

Each step is independently testable.

- **Step 0 — fix the prerequisite bug.** `_classify_chunks` (`:2168`) calls
  `_match_chunks(new_chunks, ctx.existing_chunks)` with the wrong arity (missing the
  `now` arg required at `:2073`) and the wrong unpack (the NamedTuple order is
  `(new_chunks, carry_updates, stale_ids)`, `:111`). Deeper: `_match_chunks` returns
  carries as **param dicts** keyed `_id` (`:2112`, for the ETL executemany) but the
  inline caller needs **`(existing_row, new_chunk)` pairs** (`:2171`). Match carry
  `_id`s back to `ctx.existing_chunks`. Add a regression test for inline re-chunk (a
  file whose chunk count changes across two writes; currently untested). Ships
  independently of the gate.
- **Step 1 — the identity migration.** Drop `entry_id`; add the `*_id` reference
  columns (`parent_dir_id`, `parent_file_id`, `source_id`, `target_id`), backfilled
  from the existing path columns by path lookup. Keep `path` DB-unique; do not introduce
  a live-only partial uniqueness scheme. Switch the trigram staging delta-log to carry
  the real `doc_id` (remove its
  `entry_id` column and the compile JOIN). This is the schema change the rest depends
  on; land it first, with its own tests.
- **Step 2 — extract shared validation** out of `_build_write_context` (`:1848`) into
  `_validate_entry_paths`. Pure refactor.
- **Step 3 — introduce `_mint_entries` + `_mint_entry_rows` + `_ids_by_path` + the
  policy table; wire the interactive path** with the staged mint and the
  chunk → mint → encode → compile reordering. New files, caller-planned versions, dirs,
  and non-file entries mint through the gate; version planning and existing-row
  mutations stay in the caller. `_chunk_pending` untouched. Test: write/edit/copy/mkedge
  suites.
- **Step 4 — route the ETL chunk door through the gate.** Swap `_chunk_pending`'s
  `insert(table)` (`:2333`) for `_mint_entries(plan.new_chunks)`. Benchmark the added
  `_resolve_parent_dirs` + `_ids_by_path` SELECTs. Test: `index()` suite + large-batch
  ETL.
- **Step 5 — fold the metadata-root mint through `_mint_entry_rows`** so the litmus grep
  is zero-exception.
- **Step 6 — add the litmus grep to CI.**

A later, optional track moves existing-row *mutation* off ORM dirty-tracking onto Core
update DML, and converts reads that hand back mapped instances to return row mappings /
detached `VFSEntry`s. The mapped class is **kept** as the schema/DDL source throughout
(§5).

## 10. Edge cases and risks

- **`_move_impl` (`:3016`) is mutation, not creation** — it rewrites the path columns of
  existing rows and (now) the path columns of everything hanging off them, walking the
  `*_id` graph; it mints nothing (move requires an empty destination, `:3056`). It stays
  out of the gate. `_copy_impl` (`:2959`) and `_edit_impl` / `_mkedge_impl` *do* create,
  but via `_write_impl` (`:3000`), so they inherit the gate.
- **Move is now a name rewrite over a stable graph.** Because cross-references are `id`
  FKs, a move/rename changes only the path columns of the affected subtree (found by
  walking `parent_dir_id` / `parent_file_id`); no link is re-pointed. Versions and
  chunks keep their `parent_file_id` and need their path columns rewritten in the same
  transaction. (A future option: store chunk/version *paths* under an `id`-derived
  location so a move touches only the file's own row — out of scope here.)
- **`path` is DB-unique.** A soft-deleted row still owns its path. A write to that path
  revives the same row unless the system first moves the tombstoned row to a reserved
  historical path and then mints a new row. `_ids_by_path` can therefore resolve by path
  unambiguously using the database uniqueness guarantee; it does not depend on
  backend-specific partial unique indexes.
- **Stage ordering** — parents must be inserted before children, because a child's FK
  is the parent's server-issued `id`. The gate enforces this with Stage A before Stage
  B; the in-batch layering precondition (§3 step 1) rejects a batch whose dependencies
  aren't well-formed.
- **Metadata-root special case** — keep `_ensure_metadata_root` special (its savepoint
  race-tolerance is load-bearing); do not route the root through the generic
  `_resolve_parent_dirs` walk, but do route its row through the one mint.
- **Permission carve-out** — preserve exactly: new ancestors unchecked, revived
  ancestors checked, leaf chunk/version entries never user-checked. Do not add a
  per-leaf permission step the codebase doesn't have.
- **`_match_chunks` dual return shape** (Step 0) is the part of the plan the real code
  makes hardest; it must be fixed before the gate is layered on the inline re-chunk path.
- **`_explicit_fields`** distinguishes "clear this field" from "leave it" via ORM
  attribute history today (`database.py:537`). When mutation moves to Core update dicts,
  that signal must be carried explicitly — it is not present in a plain `model_dump()`.

## 11. Open questions

1. **`version` as a public kind.** Should `version` be an accepted `kind` at the public
   `write()` boundary, or remain gate-internal only (minted as a dependent, never
   accepted as user input)? Leaning gate-internal.
2. **Identity-anchored metadata paths.** Storing chunk/version *paths* under an
   `id`-derived location (rather than the file's path) would make a move touch only the
   file's own row instead of rewriting every chunk/version path beneath it. Attractive,
   but a larger change; defer until move cost is a measured problem.
3. **Index staleness (future, when search consumes the posting list).** Today no query
   path reads the trigram posting list: `_grep_impl` (`:3402`) scans file `content`
   directly, and lexical/vector search read content / the vector store — so the
   staging→compile lag is not query-visible, and the only staleness is the intended one
   (chunk-derived search waits for chunk/encode). When a gram-gated grep *does* read the
   posting list, the deferred fold will need: a guarantee that a deferred `compile`
   eventually runs and is crash-re-runnable, single-writer folding, and either inline
   folding on the interactive path or a query-time merge of un-compiled staging. (An
   existing learning note claims grep already merges staging — that does not match the
   current grep and should be reconciled.)
4. **ETL affordances (future).** A whole-knowledgebase ingest will want progress
   reporting, bounded concurrency, and partial-failure handling (one poison document not
   aborting the batch) on top of the staged bulk insert. Out of scope here.
