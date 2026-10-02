# Study: listing what a caller may see as grants grow

Feeds `../../2026-09-30-authz-list-filtering-prior-art.md` (§8).

vfs compiles a caller's rights to OR'd path-prefix arms, so a scan
tests every row against every arm. This study asks which predicate
shape keeps the per-query cost flat as the arm count grows. Every
script builds a lean copy of the two tables glean scans (an entry
table with vfs's `BytewiseString` path and its unique index, and a
chunk table), 50,000 entries in the glean bench's layout (10 tops ×
100 folders × 50 files), in a fresh `az*_<hex>` namespace dropped on
exit. Every shape is asserted to return the same rows.

## What is here

| file | what it does |
|---|---|
| `probe.py` | Six shapes (`like`, `range`, `tree`, `stab`, `drive`, `values`) × six callers (1, 10, 100, 500 folders; one top folder; 5,000 single files) × two statements (`count`, glean's statistics scan; `top10`, the vector leg's shape). SQLite runs with vfs's `case_sensitive_like` pragma. Writes `runs/<engine>-50000.md`. |
| `plans.py` | The engine's plan for the `count` statement in four shapes at 500 folders. `--no-jit` turns Postgres JIT off. Writes `runs/plans-<engine>[-nojit].md` (the per-arm index-scan lines of the `like` plan are elided). |
| `unnest.py` | Postgres only: the range join with all ranges bound as two arrays and `unnest`ed (one statement, two binds), against `values` and `drive`. Writes `runs/postgres-unnest.md`. |
| `jsonbind.py` | SQLite only: the range join with all ranges in one JSON bind read by `json_each`, against `values`. Writes `runs/sqlite-jsonbind.md`. |

## Rerun

From this directory:

    uv run --no-sync python probe.py --engine sqlite
    uv run --no-sync python plans.py --engine sqlite
    uv run --no-sync python jsonbind.py

With the test containers up (`docker/compose.test.yml`):

    export VFS_TEST_POSTGRES_URL="postgresql+asyncpg://vfs:vfs@localhost:54320/vfs"
    uv run --no-sync python probe.py --engine postgres
    uv run --no-sync python plans.py --engine postgres
    uv run --no-sync python plans.py --engine postgres --no-jit
    uv run --no-sync python unnest.py

Each run takes under 10 minutes. The SQLite `like` and `range` rows at
5,000 grants dominate (about 10 s per statement).

Study code only: nothing here is imported by vfs.
