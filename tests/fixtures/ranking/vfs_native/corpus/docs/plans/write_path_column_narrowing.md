# Write-path column-narrowed ORM loads

Flip the `DatabaseFileSystem` write path from full-row `select(self._model)`
to explicit allowlists declared in `vfs.columns.DEFAULT_COLUMNS`. The plan
unifies write-path column narrowing through the existing `_resolve_columns`
infrastructure, mirroring the read path.

This document supersedes the originally-drafted plan. Changes from the draft
are explained in the **Critique notes** section near the end; the column
sets here are the verified-minimal ones, not the draft's over-inclusive
sets.

## Context

There are 12 (not 13, per actual count) `select(self._model)` call sites in
[src/vfs/backends/database.py](../../src/vfs/backends/database.py). The three
heavy columns — `content`, `version_diff`, `embedding` — dominate the wire
cost on write-path queries, especially for batches where most entries are
unchanged.

Prior work in this area:

- `_write_phase_fetch_existing` ([database.py:1568](../../src/vfs/backends/database.py))
  uses `defer(content, embedding)` — blocklist style.
- `_write_phase_load_deferred_for_changed` ([database.py:1667](../../src/vfs/backends/database.py))
  was added to re-hydrate `content` for paths that actually need it.

This work flips blocklist → allowlist semantics via SQLAlchemy 2.0's
`load_only`, declares the allowlists in `vfs/columns.py`, and rolls the
pattern out to all write-path ORM-row queries.

Read-path queries already use the tuple-projection form
(`select(*_select_columns(cols))` returning rows that flow into `Candidate`)
and are out of scope.

## Goals

1. No write-path query issues `select(self._model)` without an explicit
   column allowlist, except the five explicitly out-of-scope call sites listed
   in step 4. This includes `_write_phase_load_deferred_for_changed`,
   which today is a latent full-row SELECT despite its `undefer(content)`
   intent.
2. Adding a new heavy column to `VFSEntry` is automatically excluded from
   write-path SELECTs — the caller has to opt in.
3. Mutation tracking (SQLAlchemy unit of work) still works on the loaded
   ORM rows.
4. Column sets are declared once, in `vfs/columns.py`, alongside the
   existing `DEFAULT_COLUMNS` map.

## Background reading (in this order)

1. [docs/internals/write_pipeline.md](../internals/write_pipeline.md) — the phase model.
2. [src/vfs/columns.py](../../src/vfs/columns.py) — `DEFAULT_COLUMNS` and the
   public column-resolution surface.
3. [src/vfs/backends/database.py:380–454](../../src/vfs/backends/database.py) —
   `_resolve_columns`, `_select_columns`, `_row_to_candidate` (the read-path
   triple this work mirrors for ORM-row loads).
4. [src/vfs/backends/database.py:1568–1704](../../src/vfs/backends/database.py) —
   the two phases already using `defer`/`undefer`.

## Step 1 — Add `_load_only_columns` helper

Add a sibling to `_select_columns` in `src/vfs/backends/database.py`, right
after the existing helper (around line 421). Update the import line near the
top of the file to include only `load_only`:

```python
from sqlalchemy.orm import load_only
```

Add the helper:

```python
def _load_only_columns(self, cols: frozenset[str]) -> Any:
    """Sibling of :meth:`_select_columns` for queries that need ORM rows.

    Returns a ``load_only()`` option that restricts the SELECT to the
    listed columns while keeping ORM instances — preserving mutation
    tracking and identity-map semantics. ``path`` is force-included to
    match the :meth:`_select_columns` convention.

    Note the return type differs from ``_select_columns``: this returns a
    single ``Load`` option to pass to ``.options(...)``, not a list of
    column expressions to splat into ``select(*...)``. Read-path queries
    that flow back to ``Candidate`` should use ``_select_columns``; this
    helper is for write-path queries that need ORM rows (revival,
    soft-delete, path rewrite, ``existing.to_candidate()``).
    """
    ordered = ["path", *sorted(c for c in cols if c != "path")]
    return load_only(*(getattr(self._model, c) for c in ordered))
```

Naming nit: I considered `_load_only_option` to reflect that this returns a
`Load` option rather than a list. Keeping `_load_only_columns` for parity
with `_select_columns` is fine but the docstring should make the shape
difference explicit (above).

## Step 2 — Declare write-path internal column sets

Edit [src/vfs/columns.py](../../src/vfs/columns.py). Add internal entries
to `DEFAULT_COLUMNS` keyed by leading underscore, signaling private use.
Place them in a clearly-commented block at the bottom of the dict.

Column sets below are the **verified-minimal** sets from auditing every
attribute access on rows from these phases. The draft plan had wider,
defensively-padded sets; tightening preserves the goal stated above
("adding a new heavy column is automatically excluded — caller has to opt
in"). A wider set weakens that property.

```python
DEFAULT_COLUMNS: dict[str, frozenset[str]] = {
    # ... existing entries unchanged ...

    # ──────────────────────────────────────────────────────────────────
    # Internal — load_only column sets for DatabaseFileSystem write-path
    # queries. These restrict the SELECT on ORM-row fetches to only the
    # cheap metadata columns the write pipeline needs. The three heavy
    # columns (content, version_diff, embedding) are intentionally
    # absent from broad write-path fetches; callers that need them must
    # extend the set explicitly or use a targeted load_only refresh (see
    # _write_phase_load_deferred_for_changed).
    # ──────────────────────────────────────────────────────────────────
    "_fetch_existing": frozenset({
        "path",
        "kind", "content_hash", "deleted_at", "version_number",
        "index_content", "updated_at", "size_bytes",
    }),
    "_resolve_parent_dirs": frozenset({"path", "kind", "deleted_at"}),
    "_fetch_children": frozenset({
        "path", "kind", "deleted_at", "parent_path",
        "size_bytes", "updated_at",
    }),
    "_delete_targets": frozenset({
        "path", "kind", "deleted_at", "updated_at", "size_bytes",
    }),
    "_move_edges": frozenset({
        "path", "kind", "source_path", "target_path", "edge_type",
    }),
    # Phase 4: re-hydrate ``content`` for changed paths. ``embedding`` and
    # ``version_diff`` are write-only on existing rows, so they stay
    # excluded — see _write_phase_load_deferred_for_changed for the read
    # audit.
    "_load_changed_content": frozenset({"path", "content"}),
}
```

Including ``"path"`` in each set is required by the
``test_columns.py::TestDefaultColumns::test_path_always_in_default``
invariant (which loops every value in ``DEFAULT_COLUMNS``).
``_resolve_columns`` would re-add it anyway via ``cols | {"path"}``, but
keeping it in each set is cheaper than carving out the underscore keys
in the test.

Why each set looks the way it does (audited reads/writes per phase, against
the current code at [database.py](../../src/vfs/backends/database.py):

- **`_fetch_existing`** — phases 3–9 read `kind`, `deleted_at`,
  `content_hash`, `version_number`, `index_content` directly, plus
  `to_candidate()` reads `size_bytes` and `updated_at`. `content` is
  refreshed in phase 4 via `_load_changed_content` on changed paths.
  `embedding` and `version_diff` are write-only on existing rows — never read.
- **`_resolve_parent_dirs`** — function reads `obj.kind` (line 1015) and
  `existing[p].deleted_at` (line 1022). Persist phase writes `deleted_at =
  None` and `updated_at = now` to returned dirs — writes don't require the
  column to be loaded.
- **`_fetch_children`** — sole caller is `_delete_impl`, which calls
  `child.to_candidate()` (lines 2144, 2152). `to_candidate()` reads `kind`,
  `size_bytes`, `updated_at`. The function itself doesn't read
  `parent_path` directly but it's a stable filter column the caller can
  inspect cheaply.
- **`_delete_targets`** — reads `obj.kind` (via passthrough to
  `_fetch_children_batched`) and `obj.to_candidate()`. No reads of
  `parent_path` or `version_number` on delete targets in current code.
- **`_move_edges`** — incoming-edges loop reads `conn.source_path`,
  `conn.target_path`, `conn.edge_type`, `conn.kind` (via
  `_rederive_path_fields`). `deleted_at` is in the SQL WHERE clause only,
  which compiles independently of `load_only`; no Python-level access.

Validation note: `_resolve_columns` only validates against
`CANDIDATE_BACKED_MODEL_COLUMNS` when the caller passes an explicit
`columns` arg. Default-column lookups (passing `None`) skip validation, so
internal column names like `parent_path`, `source_path`, `target_path`,
and `edge_type` are fine here.

## Step 3 — Migrate `_write_phase_fetch_existing`

This is the test case. If it passes the test suite, the same pattern rolls
out to the rest.

Current code at [database.py:1568](../../src/vfs/backends/database.py)
uses `defer(content, embedding)`. Replace the SELECT-and-options block
with `load_only`:

```python
async def _write_phase_fetch_existing(
    self,
    ctx: _WriteContext,
    session: AsyncSession,
) -> None:
    """Batch-fetch existing rows and the latest version hash per file.

    Heavy columns (``content``, ``embedding``, ``version_diff``) are
    excluded from the SELECT — they are large and the write pipeline
    only needs them on rows that actually change.
    ``_write_phase_load_deferred_for_changed`` re-hydrates ``content``
    for paths in ``ctx.changed_paths`` after phase 4 decides which rows
    need real work. ``embedding`` and ``version_diff`` are write-only on
    existing rows so they stay deferred for the lifetime of the phase.
    """
    cols = self._resolve_columns("_fetch_existing", None)
    all_paths = list(ctx.write_map.keys())
    existing_map: dict[str, VFSEntry] = {}
    for batch in self._chunk_paths(session, all_paths, binds_per_item=1):
        stmt = (
            select(self._model)
            .where(self._model.path.in_(batch))  # ty: ignore[unresolved-attribute]
            .options(self._load_only_columns(cols))
        )
        result = await session.execute(stmt)
        for row in result.scalars().all():
            existing_map[row.path] = row
    ctx.existing_map = existing_map

    # ... version-hash fetch below unchanged ...
```

Leave the version-hash fetch in the lower half of the function alone — it
already uses tuple projection (`select(self._model.path,
self._model.content_hash)`).

**Stop here and run the test suite.** If `tests/test_write_pipeline.py`,
`tests/test_write_pressure.py`, and `tests/test_database.py` pass, the
pattern works. If any test fails with an `AttributeError` on a column
access — or a query counter shows an N+1 of follow-up `SELECT col FROM
...` — the column needs to be added to the `_fetch_existing` set. That
diagnostic is itself a useful signal.

SQLAlchemy 2.0.46 interop note — phase 4 needs its own migration.
`undefer(content)` only un-defers a column that was already deferred at
the statement level. The current phase 4 statement is
`select(self._model).options(undefer(content)).execution_options(populate_existing=True)`,
which compiles to a full-row SELECT — *every* column is rendered,
including `embedding` and `version_diff`, because nothing on the statement
defers them. The reason phase 4 works today is `populate_existing=True`
refreshes whatever the SELECT returned; the SELECT just happens to return
everything. That is the column-narrowing bug this work is trying to fix,
not preserve.

Migrate phase 4 the same way as phase 3, using the new
`_load_changed_content` set:

```python
async def _write_phase_load_deferred_for_changed(
    self,
    ctx: _WriteContext,
    session: AsyncSession,
) -> None:
    cols = self._resolve_columns("_load_changed_content", None)
    paths = [p for p in ctx.changed_paths if p in ctx.existing_map]
    if not paths:
        return
    for batch in self._chunk_paths(session, paths, binds_per_item=1):
        stmt = (
            select(self._model)
            .where(self._model.path.in_(batch))  # ty: ignore[unresolved-attribute]
            .options(self._load_only_columns(cols))
            .execution_options(populate_existing=True)
        )
        await session.execute(stmt)
```

The function's docstring is unchanged in spirit — `content` is the only
column we refresh — but now the SELECT actually says so. `embedding` and
`version_diff` stay deferred on the identity-map instance and are still
write-only on the row, just as documented.

## Step 4 — Roll out to the remaining call sites

Apply the same pattern. Each is a self-contained edit: replace the bare
`select(self._model)` with
`.options(self._load_only_columns(self._resolve_columns(...)))`.

### 4a. `_resolve_parent_dirs` ([database.py:973](../../src/vfs/backends/database.py))

```python
cols = self._resolve_columns("_resolve_parent_dirs", None)
for batch in self._chunk_paths(session, sorted(all_ancestors), binds_per_item=1):
    stmt = (
        select(self._model)
        .where(self._model.path.in_(batch))  # ty: ignore[unresolved-attribute]
        .options(self._load_only_columns(cols))
    )
    result = await session.execute(stmt)
    existing.update({obj.path: obj for obj in result.scalars().all()})
```

### 4b. `_fetch_children_batched` ([database.py:1054](../../src/vfs/backends/database.py))

Two queries (lines 1088 and 1122). Hoist `cols = self._resolve_columns(
"_fetch_children", None)` to the top of the method so it's computed once,
then apply `.options(self._load_only_columns(cols))` on both `select`s.

### 4c. `_delete_impl` ([database.py:2080](../../src/vfs/backends/database.py))

Use `_delete_targets` cols. Result rows are mutated (soft-delete) or
removed (hard-delete) — ORM rows are required.

### 4d. Move/copy incoming edges ([database.py:2468](../../src/vfs/backends/database.py))

Use `_move_edges` cols. The result rows have their `target_path` rewritten
— ORM rows are required.

### Explicitly out of scope (do not touch in this work)

- **`_get_object` ([database.py:565](../../src/vfs/backends/database.py))** —
  generic single-row helper used across many callers with varying column
  needs. Convert in a follow-up if needed (probably add an optional `cols`
  parameter).
- **`_fetch_version_chain` ([database.py:1193](../../src/vfs/backends/database.py))** —
  needs `content` and `version_diff` for chain reconstruction. The right
  fix here is tuple projection (`select(self._model.path,
  self._model.content, ...)`) since the result is read-only and flows
  through pure-data methods. Separate ticket.
- **Move/copy descendants ([database.py:2407, 2415, 2425](../../src/vfs/backends/database.py))** —
  need to preserve `content` and `embedding` end-to-end. Full row is
  correct here. Could add a `_load_only_columns` call with the full
  candidate-backed col set later, but the SQL would match
  `select(self._model)` so it would be cosmetic.

## Step 5 — Remove the obsolete `defer` / `undefer` imports

After step 3 (phase 3 migration), `defer` is no longer referenced.
After step 3b (phase 4 migration), `undefer` is also no longer needed:
`load_only(path, content)` with `populate_existing=True` refreshes
`content` on identity-map instances directly — there is no deferred
column to *un*-defer because columns aren't deferred at the mapper
level.

Confirm with:

```bash
grep -n "\bdefer\b\|\bundefer\b" src/vfs/backends/database.py
```

If both only appear in the import line, drop them. Keep `load_only`.
The final import should read:

```python
from sqlalchemy.orm import load_only
```

If the test suite reveals a code path that broke (e.g. a deferred
column is later read explicitly), the diagnostic is clear and the fix
is to widen the relevant column set, not to bring `undefer` back.

## Step 6 — Add at least one write-path projection regression test

Audited gap: `test_backend_projection.py` covers read-path narrowing only
(glob, stat, ls, tree, read, grep). Without a write-path test, regressions
in this work won't be caught — a future edit can silently add `content` to
`_fetch_existing` and tests stay green.

**Isolate the SELECT, do not use the global helper.** A global
`sql_capture.assert_no_column("content")` would fail on a changed write
because phase 4 legitimately re-fetches `content` for changed paths
(now narrowed to `{path, content}` per the phase-4 migration above, but
still projecting `content`). The test must target the specific
`_write_phase_fetch_existing` statement.

Both phase-3 and phase-4 SELECTs are batched `WHERE path IN (...)`
shapes. The reliable disambiguator is the column list: phase 3's set
includes both `content_hash` and `version_number`; phase 4's set has
neither (only `path` and `content`). So filter on those two columns to
land on phase 3 specifically:

```python
import re

from vfs.models import VFSEntry

async def test_write_phase_fetch_existing_omits_heavy_columns(self, db, sql_capture):
    # Seed so the second write hits the existing-row branch.
    await db.write([VFSEntry(path="/seed.txt", kind="file", content="seed")])
    sql_capture.reset()

    # Identical-content rewrite — exercises _write_phase_fetch_existing and
    # skips phase 4 (no changed paths), so the only SELECT we capture from
    # the write-path is the phase-3 fetch.
    await db.write([VFSEntry(path="/seed.txt", kind="file", content="seed")])

    fetch_existing = [
        s for s in sql_capture.reads_against_entries()
        if "vfs_entries.content_hash" in s and "vfs_entries.version_number" in s
    ]
    assert fetch_existing, "expected to capture the _write_phase_fetch_existing SELECT"

    word = lambda col: re.compile(rf"\bvfs_entries\.{col}\b")
    for stmt in fetch_existing:
        assert not word("content").search(stmt), stmt
        assert not word("embedding").search(stmt), stmt
        assert not word("version_diff").search(stmt), stmt
        assert word("kind").search(stmt)
        assert word("content_hash").search(stmt)
        assert word("deleted_at").search(stmt)
```

The `\b` boundaries in the regex distinguish `content` from
`content_hash` (since `_` is a word character, `\b` will not match
between `content` and `_hash`). That's the same logic
`SQLCapture.assert_no_column` already uses; the test just re-applies it
per-isolated-statement instead of across every captured read.

## Test plan

Run after step 3 (smoke test), then again after step 4 (full rollout),
then once more after step 6 (new test):

```bash
uv run pytest tests/test_write_pipeline.py tests/test_write_pressure.py tests/test_database.py tests/test_backend_projection.py -x
```

Pay particular attention to:

- **`test_backend_projection.py`** — exercises the existing read-path
  column-narrowing. Should remain unaffected; if it breaks, the change
  accidentally touched something shared.
- **N+1 detection** — if a test logs queries and one suddenly shows many
  `SELECT content FROM vfs_entries WHERE id = ?` follow-ups, a code path
  is accessing an unloaded column and triggering a lazy-load. Add the
  missing column to the relevant `DEFAULT_COLUMNS["_*"]` entry.
- **The new write-path projection test** from step 6.

The `.venv` in the repo may be stale from the `grover` → `vfs` rename; if
tests fail to launch, `uv sync --group dev` rebuilds it.

## Risk and rollback

**Primary risk:** an unaudited code path accesses a column not in the new
allowlist, triggering a lazy-load. This is *not* a correctness bug — it
just degrades performance silently. Tests with query counters will surface
it; production won't crash.

**Identity-map gotcha:** if two phases issue independent fetches for
overlapping paths with different allowlists, SQLAlchemy's identity map
returns the first-loaded instance for the second fetch — set B's columns
won't appear unless `populate_existing=True` is set. This doesn't happen
in the current write pipeline (phases 3 and 4 are the only repeat-fetch
pair, and phase 4 already uses `populate_existing=True`), but is worth a
comment near the helper.

**Hardening option (recommended local-only check before merge):**
SQLAlchemy 2.0 supports `load_only(*attrs, raiseload=True)` — a deferred
column then raises on access instead of lazy-loading. Worth running the
test suite once with `raiseload=True` flipped on locally to flush out any
missed columns (loud failure beats silent slowness), then back off to
`raiseload=False` (the default) for the merge. Could promote to
`raiseload=True` permanently in a follow-up once the rollout is stable.

**Rollback:** each step is a single commit.

- Step 3 alone is one method; reverting it preserves the helper in
  `database.py` and the column entries in `columns.py` as inert
  additions.
- Step 4 commits are one-per-call-site; revert any single one without
  affecting the others.
- Step 6 (new test) is a single file edit.

## Acceptance criteria

- All seven target call sites use
  `select(self._model).options(self._load_only_columns(...))`:
  `_write_phase_fetch_existing` (step 3),
  `_write_phase_load_deferred_for_changed` (step 3b),
  `_resolve_parent_dirs`, the two queries in `_fetch_children_batched`,
  `_delete_impl`, and the incoming-edges SELECT in `_move_impl` (step 4).
- No `select(self._model)` without `.options(...)` in `database.py`
  *except* the five explicitly-out-of-scope call sites listed in step 4.
- `defer` is removed from the SQLAlchemy import; `undefer` is also
  removed (phase 4 no longer needs it once it uses `load_only`); only
  `load_only` remains in the import.
- `tests/test_write_pipeline.py`, `tests/test_write_pressure.py`,
  `tests/test_database.py`, `tests/test_backend_projection.py`,
  `tests/test_columns.py` all pass.
- A new write-path projection test exists in
  `tests/test_backend_projection.py` asserting that the
  `_write_phase_fetch_existing` SELECT (identified by projecting both
  `content_hash` and `version_number`) does not project `content`,
  `embedding`, or `version_diff`.
- The PR description quotes before/after SQL snippets for **both**
  `_write_phase_fetch_existing` and
  `_write_phase_load_deferred_for_changed` showing the column lists
  narrowing from `*` to the explicit sets. (Phase 4's snippet is the
  one that demonstrates this work fixed a pre-existing latent bug, not
  just refactored phase 3.)

## Estimated effort

- Step 1 + 2: ~15 minutes (helper + dict entries, mechanical).
- Step 3 + 3b: ~25 minutes (phases 3 and 4) including test run.
- Step 4: ~30 minutes for the five remaining edits + test runs.
- Step 5: ~5 minutes.
- Step 6: ~20 minutes (new test using existing fixture, plus optional
  `raiseload=True` sweep).
- **Total: ~95 minutes of focused work** assuming the test suite
  cooperates.

## Critique notes — changes from the originally-drafted plan

This section explains what changed from the draft and why. Future-you (or
a reviewer) can use this to judge whether the changes still make sense if
the code has drifted by the time the work happens.

### 1. Tightened column sets

The draft's sets had defensive padding that wasn't justified by actual
attribute access. The verified-minimal sets above were derived by
auditing every `.attr` read on rows returned from each phase.

| Set | Draft | Tightened | Reason |
| --- | --- | --- | --- |
| `_fetch_existing` | adds `owner_id` | drop `owner_id` | No `existing.owner_id` read found anywhere in the write path. |
| `_resolve_parent_dirs` | `{kind, deleted_at, updated_at, size_bytes}` | `{kind, deleted_at}` | Function only reads `kind` and `deleted_at`. `updated_at` is written but writes don't need loaded columns. `size_bytes` is never accessed. |
| `_fetch_children` | `{kind, deleted_at, parent_path}` | adds `size_bytes`, `updated_at` | **This was a bug.** Sole caller is `_delete_impl` which calls `child.to_candidate()` — needs `size_bytes` and `updated_at`. The draft would have caused lazy loads. |
| `_delete_targets` | adds `parent_path`, `version_number` | drop both | Neither is read in `_delete_impl`. Defensive padding without justification. |
| `_move_edges` | adds `deleted_at`, `updated_at` | drop both | `deleted_at` is WHERE-clause only (doesn't need to be loaded). `updated_at` is never accessed in the move/copy code. |

The principle here: wider allowlists weaken the goal stated in step 2
("adding a new heavy column is automatically excluded"). A future
`features_blob: bytes` column added to `VFSEntry` should be excluded by
default; a wider allowlist makes that promise less reliable.

### 2. Added step 6: write-path projection regression test

The draft's test plan referenced `test_backend_projection.py` as a
"nothing else broke" smoke check. But that file only covers read-path
narrowing — there is no test that pins the column list for the
`_write_phase_fetch_existing` SELECT. Without one, a future edit can
silently re-add `content` to the allowlist with no failing test. Step 6
closes this gap with a single test using the existing `sql_capture`
fixture.

### 3. Helper-shape clarification

The draft described `_load_only_columns` as a "sibling" of
`_select_columns`. They share the cols-input convention but return
different shapes: `_select_columns` returns a list to splat into
`select(*...)`; `_load_only_columns` returns a single `Load` option to
pass to `.options(...)`. The docstring above is explicit about this so a
future reader doesn't try to splat one or wrap the other.

### 4. Identity-map gotcha called out

The draft didn't flag the SQLAlchemy identity-map quirk: re-fetching an
already-loaded row with a different allowlist returns the cached instance
unless `populate_existing=True` is set. This doesn't bite in the current
pipeline (phase 4 already uses `populate_existing=True`) but is worth a
note for future phases.

### 5. `raiseload=True` upgraded from "deferred follow-up" to
"recommended local-only check before merge"

The draft suggested `raiseload=True` as a follow-up once rollout was
stable. But running it once locally during this work — to flush out
missed columns by failing loud instead of degrading silently — costs
~5 minutes and catches the exact class of regression we're worried
about. Worth doing now, even if it's not turned on for the merge.

### 6. Call-site count corrected

The draft cited "~13 call sites." Actual count of `select(self._model)`
in the file is 12. Off-by-one; inconsequential, but corrected here.

### 7. Line numbers refreshed

Draft was off by ~5 lines throughout (probably written against an earlier
revision). Line numbers in this doc reflect the file at the time of
writing — if the file has drifted, search by function name.

### 8. Phase 4 corrected — was a latent full-row SELECT

An earlier revision claimed "no code change needed in phase 4" because
`undefer(content) + populate_existing=True` would still refresh
deferred content on identity-map instances. That description was
literally true (the refresh works) but missed the column-narrowing
question entirely. The current phase 4 statement —
`select(self._model).options(undefer(content)).execution_options(populate_existing=True)` —
compiles to a full-row SELECT: every column is rendered because
nothing on the statement defers them. `undefer` is a no-op when
columns aren't already deferred at the statement level. So
today's phase 4 ships `embedding` and `version_diff` over the wire on
every changed-path refresh — exactly the cost this work claims to
remove.

The fix is the same pattern phase 3 uses:
`load_only(*_load_changed_content)` on the statement, with
`populate_existing=True` preserved. After this change, the phase-4
SELECT projects only `path` and `content`, and `undefer` is no longer
needed anywhere in the file (removed from the import in step 5).

### 9. `path` included in each private DEFAULT_COLUMNS entry

`_resolve_columns` re-adds `"path"` via `cols | {"path"}` regardless,
but `tests/test_columns.py::TestDefaultColumns::test_path_always_in_default`
asserts `"path" in cols` for every dict entry. Including `path`
explicitly in each underscore-keyed set preserves the invariant
without altering the test.

### 10. Step 6 test isolated to the phase-3 SELECT

The draft of step 6 said "assert `_write_phase_fetch_existing` doesn't
project `content`" using the global `sql_capture.assert_no_column`
helper. That would fail on any changed-path write because phase 4
legitimately projects `content` (narrowed to `{path, content}` after
this work, but still). The test must locate the phase-3 statement
specifically — the disambiguator is "projects both `content_hash` and
`version_number`" — and assert against that one statement.
