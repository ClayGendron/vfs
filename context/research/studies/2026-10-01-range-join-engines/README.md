# Study: ADR 072's range join on all five engines, with a recall check

ADR 072 says rights should reach SQL as one bound list of path ranges,
unpacked by the engine and joined to the `path` index, with entries
filtered before any chunk-side table is touched. Its Consequences ask
for this prototype on all five engines, with a recall column, before
any `src/` change. This study is that prototype.

## What is here

| file | what it does |
|---|---|
| `bench.py` | Builds a lean entry table (`path` with vfs's own `BytewiseString`, unique index; `owner_id`, indexed) and a chunk table (`entry_id`, an integer `score` standing in for vector distance). Resolves six callers with the shipped `vfs.storage.grants.resolve`. Times three statements (visible entries, visible chunk count, top 10 chunks by score) in four shapes: `arms` (the shipped `visibility_clauses`), `literal` (the pieces inline, small rights only), `join IN` (chunks by `entry_id IN (visible)`) and `join derived` (chunks joined to the visible entries as a derived table). Checks every answer against `Rights.admits` run in Python over every row. Writes `runs/<engine>.md`. |
| `runs/` | One result file per engine, with the plan of the join's count statement. |

The corpus has a sibling trap in every top folder: `/tNN/f000-x` sorts
between `/tNN/f000` and `/tNN/f000/`, so a range that skipped the
two-piece rule would leak it, and the recall column would show it.

## Rerun

Containers up (`docker/compose.test.yml`), URLs as in
`.github/workflows/test-dialects.yml`, then from this directory:

    uv run --no-sync python bench.py --engine sqlite --files 40
    VFS_TEST_POSTGRES_URL=... uv run --no-sync python bench.py --engine postgres --files 40

Engines are `sqlite`, `postgres`, `mariadb`, `mssql`, `oracle`. All five
run in parallel in about the time of the slowest.

## A finding from the smoke run: no bound may end in a low byte

The first version expressed an exact path `p` as the range
`[p, p + "\x01")`. SQL Server returned the hole folders it should have
cut. SQL Server pads the shorter string with spaces before comparing,
so `p` compares as `p ` and sorts *above* `p + "\x01"`. The fix, which
is ADR 072 rule 1 as written: exact paths stay `path = p`, and ranges
are open at both ends (`lo < path < hi`). A lower bound that is itself
a lawful path becomes an exact point beside the open range.

## Results

Every shape returned exactly the right rows on every engine (the recall
column is 1.00 throughout). Wall time for all five engines in parallel:
about 3 minutes, Oracle the slowest.

- **Visible entries flatten on four engines.** At 100 grants: SQLite
  176 → 5 ms, Postgres 10 → 4.6, MariaDB 206 → 11, SQL Server
  1,299 → 15. Oracle 230 → 196, and at 500 grants the join lost
  (960 against 721).
- **Chunk-side statements need the derived table.** `entry_id IN
  (visible)` took 0.6 to 22 s on MariaDB and 3.7 to 55 s on Oracle;
  the derived table stayed under 52 ms on the four engines that gain,
  and was never much worse than `IN` where `IN` was fine.
- **Top 10 by an indexed score can favour today's arms.** A caller who
  sees much of the mount lets the engine walk the score index and
  stop at ten visible rows (open root with holes: 1 to 2 ms with arms,
  14 to 26 ms through the visible set). This is the choice the
  vector-leg count gate must make; the integer score here stands in
  for an index-ordered distance and does not model an exact scan.
- **Caveat:** the `arms` count fetches chunk ids and counts them in
  Python (its clauses may overlap), so it overstates today's count
  somewhat. The entries rows compare like with like.
