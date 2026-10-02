# Study: spec 058's performance gate — the shipped predicate against S1's literal form

Spec 058's acceptance criteria end with a performance gate: *S1's probe
run against the shipped resolver and compiler on Postgres stays within
1.5x of the study's literal form for the grep pass and the 1,000-id
join-back.* This study is that run.

## What is here

| file | what it does |
|---|---|
| `gate.py` | Loads S1's deterministic corpus into S1's lean entry table (reusing `corpus.py` and `common.py` from `../2026-09-05-permissions-predicate-at-scale/`). Picks S1's typical principal. Builds its rights with the shipped `vfs.storage.grants.resolve` and compiles them with the shipped `visibility_clauses`. Times the grep pass and the 1,000-id join-back against S1's `literal_like`, and asserts both forms return the same rows. Also times the same principal's rights reached through S1's groups form, for the record (S1 has no literal form for groups). Writes `runs/<engine>-<rows>.md`. |
| `runs/` | One result file per engine and size. |

## Rerun

Containers up (`docker/compose.test.yml`), then from this directory:

    VFS_TEST_POSTGRES_URL="postgresql+asyncpg://vfs:vfs@localhost:54320/vfs" \
      uv run --no-sync python gate.py --engine postgres --files 75000 --reps 5
    VFS_TEST_POSTGRES_URL="postgresql+asyncpg://vfs:vfs@localhost:54320/vfs" \
      uv run --no-sync python gate.py --engine postgres --files 800000 --reps 5
    uv run --no-sync python gate.py --engine sqlite --files 75000 --reps 5

`--files 75000` is about 100k entry rows; `--files 800000` is about 1M.

## Results

See `runs/`. The verdict line of each run reads `PASS` or `FAIL`
against the 1.5x gate.
