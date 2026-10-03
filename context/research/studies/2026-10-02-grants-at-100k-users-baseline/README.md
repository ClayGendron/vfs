# Study: the shipped grants design at 100,000 users — the baseline

Status: executed 2026-10-02. Engines: SQLite and Postgres 17 (asyncpg).
Owner: Clay. Scope: measurement only; no `src/` change.

## The question

How does the shipped grants design (spec 058, ADR 072) behave at the
target scale — 100,000 users, each with a private home, each holding
dozens of shared folders through groups — and exactly where and why does
it break? The 2026-10-01 code review found three failures by reading
and small repros (one clause holds every posture hole; `pieces()` is
quadratic; `meet` is a cross product). This study builds the world,
runs the shipped code paths at N = 1,000, 10,000 and 100,000 on both
engines, and puts a number on every wall. A parallel prototype builds
the same world from `world.py`, so the two can be compared row for row.

## What is here

| file | what it does |
|---|---|
| `world.py` | The seeded world: N users, `/home/uNNNNNN` at posture `none` with a `read_write` self-grant, root `open`, N/100 shared folders, N/200 groups, 5 groups per user, 3 read + 1 read_write group grants and 10 user grants per shared folder, 20 files per home, 200 per shared folder, 100 sibling traps `/home/uNNNNNN-x`. Importable; one RNG, draw order documented in the module docstring. |
| `bench.py` | Writes the world into a real `DatabaseStorage` mount's own tables with the shipped `bulk_insert`, then measures the shipped code: `resolve_authority`, `Rights.ranges()`/`pieces()`, the range join (`visible_entries`), the clause fan (`visibility_clauses`), `tree`/`glob`/`ls` end to end (one subprocess per verb so a runaway call dies at the cap), cache churn, cached-rights memory, and `Rights.admits` per row. Checks recall against `Rights.admits`. `--results` assembles `results.md` from the JSON run files. |
| `runs/<engine>-<N>.md` / `.json` | One result file per engine and N, with the Postgres `EXPLAIN (ANALYZE, BUFFERS)` / SQLite `EXPLAIN QUERY PLAN` of the ordinary caller's range join. `runs/postgres-ladder.json` holds the Postgres hole ladder. |
| `results.md` | Every number, with its engine and N, one table per measurement. |

## Rerun

Postgres up at the URL below (ephemeral data; the bench namespaces its
tables `bl_<hex>_` and drops them). From this directory:

    uv run --no-sync python bench.py --engine sqlite --n 1000 --sweep
    uv run --no-sync python bench.py --engine sqlite --n 10000
    uv run --no-sync python bench.py --engine sqlite --n 100000 --files-per-home 2 --e2e-cap 60 --e2e-callers ordinary,system
    uv run --no-sync python bench.py --engine postgres --url postgresql+asyncpg://vfs:vfs@localhost:54320/vfs --n 1000
    ...
    uv run --no-sync python bench.py --results

`--sweep` adds the hole ladder and the out-of-world `meet` ladder. The
Postgres hole ladder runs as `--ladder-only` (it sets a server-side
`statement_timeout`; see the caveats — do not run it past 2,000 holes
on a server you share). Wall time: SQLite 45 s / 220 s / 460 s for the
three sizes; Postgres 26 s / ~5 min at 1k / 10k with the fan guard.
`runs/` holds SQLite 1k/10k/100k, Postgres 1k/10k and the Postgres
ladder.

## The world at each N

| N | groups | shared folders | grant rows | memberships | entries | grants an ordinary user holds |
|---|---|---|---|---|---|---|
| 1,000 | 5 | 10 | 2,141 | 5,000 | 23,213 | 42 |
| 10,000 | 50 | 100 | 21,401 | 50,000 | 230,303 | 36 |
| 100,000 | 500 | 1,000 | 214,001 | 500,000 | 501,203 (2 files per home) | 41 |

The 100k world was built with 2 files per home instead of 20, to keep
the load under a minute per engine (the full world is 2,301,203 rows).
Every number that depends on row count at 100k (the range join's fetch,
`tree('/')`, `ls('/home')`) is therefore an underestimate for the full
world; nothing that depends on hole count is affected, and the walls
below are all hole-count walls.

An ordinary user's read rights at every N are: one root arm with N
holes (every home, its own included), one arm on its own home, dozens
of shared-folder prefixes that the open root already covers (so they
add nothing to the read arms), and one owner arm at `/`. The **hole
count equals N**, and every wall below is a function of it.

**Postgres at N = 100,000 did not complete.** Two attempts were lost
when the shared server recovered from another agent's crash, and the
third was stopped on the coordinator's instruction inside the
quadratic `pieces()` step, after the load (501,202 entries in 15 s)
and step 1: `resolve_authority` cold 1,344 ms for the ordinary user
(pure `resolve` 814 ms; `_everyone_arms` 151 ms), in line with
SQLite's 1,832 ms. SQLite's 100k row is the 100k baseline; the Python
walls (pieces, admits, memory, churn) are engine-independent.

**All Postgres timings here are noisy**: the server was shared with
another agent's bulk-write spike during the same hour. The same
caller shape measured 8 ms to 600 ms on the range join across runs.
Read the Postgres rows as order-of-magnitude; the SQLite rows were
taken on a private file.

## Results in one table (SQLite; Postgres in `results.md`)

| measurement | N = 1,000 | N = 10,000 | N = 100,000 |
|---|---|---|---|
| `resolve_authority` cold, ordinary user | 10 ms | 118 ms | 1,832 ms |
| pure `resolve(read)` | 2.8 ms | 67 ms | 994 ms |
| `_everyone_arms` (minimise N holes) | 0.9 ms | 12 ms | 231 ms |
| `Rights.ranges()` — shipped `pieces()` | 119 ms | 18,355 ms | timed out at 60 s (fit: ~75 min) |
| the same pieces by a linear sweep (study code) | 1.3 ms | 17 ms | 264 ms |
| pieces (points + opens) / JSON bind bytes | 2,999 / 92 KB | 29,999 / 920 KB | 299,999 / 9.2 MB |
| range join: visible count, warm | 9 ms | 31 ms | 284 ms |
| range join: visible rows fetched, warm | 18 ms (2,234 rows) | 83 ms (20,324) | 746 ms (201,206) |
| recall of the join vs `Rights.admits` | 1.00, 0 extra | 1.00, 0 extra | 1.00, 0 extra |
| clause fan (`visibility_clauses`) | **fails**: expression depth 1000 | fails | fails |
| `Rights.admits`, one row under the root arm | 21 µs | 200 µs | 4,347 µs |
| `tree('/')` ordinary, cold / warm | 203 / 69 ms | 21,184 / 4,170 ms | timed out at 60 s |
| `glob('/shared/*/*.md')` ordinary, warm | 60 ms | 4,094 ms | timed out at 60 s |
| `ls('/home')` ordinary, warm | 25 ms | 825 ms | timed out at 60 s |
| `tree('/')` system actor, warm | 251 ms (23,212 rows) | 3,094 ms (230,302) | 8,346 ms (501,202) |
| one cached `Resolution` (both levels) | 72 KB | 702 KB | 7.0 MB |
| the same plus the read ranges memo | 427 KB | 4.2 MB | 42.4 MB |
| a full 256-entry rights cache | 109 MB | 1.1 GB | 10.9 GB |
| callers discarded by one grant write | 20 of 20 cached | 20 of 20 | 20 of 20 |
| recompute per caller after a grant (resolution only) | 18 ms | 136 ms | 2,129 ms |
| ...if every user reads once after one grant | 18 s CPU | 23 min CPU | 59 h CPU |

Postgres differs in two places: the range join is slower and plans
badly (8 to 600 ms, see below), and the clause fan runs instead of
failing — at 1.3 s per statement at N = 1,000 — until the driver's
bind cap stops it. The resolver, pieces, admits, memory and churn
numbers are pure Python and match SQLite's.

## Where it breaks and why

Each wall names the line responsible. Line numbers are at commit
`4759bc6`.

### Wall 1 — the clause fan cannot split an arm's holes (fails at exactly 1,000 holes on SQLite; 1.3 s at 1,000 on Postgres, unsendable past 16,383)

`src/vfs/storage/backends/database/rights.py:731-735` (`_units`)
compiles one arm as `and_(cover, not_(hole_1), ..., not_(hole_H))` —
one unit, 2H+2 binds, 2H+1 terms. `visibility_clauses` (lines 226-233)
only splits *between* units, so the root arm with N holes always lands
in one clause whatever `bind_cap` says.

- SQLite: the ladder passes at 990 holes (607 ms) and fails at 1,000
  with `Expression tree is too large (maximum depth 1000)`. The N =
  1,000 world already fails for every partial caller. SQLite's parser
  depth tracks the AND chain's term count, not the bind count.
- Postgres: 1,444 ms at 1,000 holes (ordinary; 312 ms for anonymous,
  whose clause has no owner-arm OR and keeps the index), 2,861 ms at
  2,000, past 45 s at 5,000. Worse than slow: from about 5,000 holes
  the backend **wedges** — the 5,000- and 10,000-hole statements ran
  for more than five minutes server-side, ignored `statement_timeout`,
  ignored `pg_terminate_backend` (it answered true; the backend kept
  running), and were still running when the shared server went
  through crash recovery (cause not established; see the caveats).
  The time goes to the planner (the 1k→2k→5k curve is
  super-linear and the executor's work is linear), where
  `CHECK_FOR_INTERRUPTS` is not reached. After that, the bench no
  longer sends a Postgres clause of more than 2,000 holes that the
  driver would accept. Past 16,383 holes asyncpg refuses the statement
  before Postgres sees it: `the number of query arguments cannot exceed
  32767`. At N = 100,000 the fan builds a 200,000-bind clause in 3 to
  4.6 s of Python and the driver rejects it.

This path is what `glean`'s vector leg runs on every engine and what
Oracle and the generic floor run for every narrowed read. So `glean` is
broken for every partial caller from N = 1,000 on SQLite, and over a
second per statement from N = 1,000 on Postgres.

### Wall 2 — `pieces()` is super-quadratic in holes (18 s at 10,000; ~75 min at 100,000)

`src/vfs/storage/grants.py:360-371` (`_subtract`) rebuilds the whole
`out` list once per cut span, and `out` grows to ~2H spans. Measured
on the shipped function: 0.11 s (1k), 0.47 (2k), 4.07 (5k), 19.97
(10k), 101.8 (20k) — 5.1× per doubling, an exponent of about 2.3 (the
sort in `_merged` and list rebuilds add to the H²). At 100,000 holes
it did not finish in 60 s; the fit says about 75 minutes of event-loop
CPU for one caller. A two-pointer sweep over the sorted keep and cut
lists (`fast_pieces` in `bench.py`) produces the identical `Ranges`
(checked equal at every N where the shipped one finished) in 1.3 ms /
17 ms / 264 ms.

Every partial caller pays this on its first read per grant revision,
synchronously, inside `Visibility.entries()`: at N = 10,000 a cold
`tree('/')` is 21.2 s on SQLite and the warm one 4.2 s — the 17 s
difference is `pieces()`.

### Wall 3 — `meet` is a cross product (not reached by this world; 25 s for a 10,000-grant group)

`src/vfs/storage/grants.py:98` is `{... for a in left for b in right}`.
In this world a user's covering set is 41 to 71 prefixes, so the pair
authority's meet is a 50×50 product and costs nothing: the pair's pure
`resolve` is 36 ms at N = 10,000 and 271 ms at 100,000, both dominated
by the holes, not the meet. The wall is real but needs a different
shape — one group holding thousands of grants. Out of world (the
review's shape): a single-subject resolve over a 10,000-grant group is
19 ms; the pair is 25.4 s (1k: 0.25 s; 3k: 2.3 s), ~9× per tripling.

### Wall 4 (new) — `Rights.admits` scans the hole tuple on every row (4.3 ms per row at 100,000)

`src/vfs/storage/grants.py:306` (`_holed`) tests `ancestor in
arm.holes` with `holes` a tuple (`Arm.holes: tuple[str, ...]`, line
117). Membership in a tuple is a linear scan, so one `admits` on a row
that falls to the root arm — every shared file, every road directory,
every trap — costs O(depth × N): 21 µs at 1,000 holes, 200 µs at
10,000, 4.3 ms at 100,000. A row under a hole (another user's home)
costs half that; a row under the caller's own arm costs 1 µs.

Every row-check loop pays it: `_visible_rows`
(`reads.py:555`), `_children_by_parent` (`reads.py:647,652`), the glob
and grep candidate checks, glean's overlay. This is the wall that stays
after the first three are fixed, and it is why the shipped verbs time
out at 100,000 even though the SQL side answers in under a second:

- `tree('/')` returns ~20,000 rows at N = 10,000: 4.2 s warm (20,000 ×
  200 µs). At 100,000 it returns 201,206 rows × 4.3 ms ≈ 15 minutes;
  killed at 60 s.
- `ls('/home')` fetches all N home directories and asks `admits` for
  each hidden one (then `view.road`): 0.8 s at 10,000; 100,000 × 2.3
  ms ≈ 4 minutes at 100,000; killed at 60 s.
- `glob('/shared/*/*.md')`: 4.1 s at 10,000 (20,000 rows); killed at
  60 s at 100,000.

The system actor, which skips the view, returns 501,202 rows from
`tree('/')` in 8.3 s and 100,100 from `ls('/home')` in 2.6 s at
100,000 — so the engine and the row materialisation are not the limit.

### Wall 5 (new) — the cached rights weigh 42 MB per user at 100,000; a full cache is 10.9 GB

`Resolution` holds two `Rights` (read and write), each with the root
arm's N hole strings in a tuple, and `Rights.ranges()` memoises the
pieces — 300,000 strings and 200,000 tuples more. Deep size for the
ordinary user: 72 KB / 702 KB / 7.0 MB per `Resolution`; 427 KB / 4.2
MB / 42.4 MB once the read ranges are computed. `RIGHTS_CACHE = 256`
(`rights.py:78`) makes a warm cache 109 MB / 1.1 GB / 10.9 GB. The
JSON bind for the range join is 9.2 MB per statement at 100,000 — sent
on every narrowed read.

### Wall 6 — one global revision discards every cached caller (59 CPU-hours per grant write at 100,000)

The cache key is `(subjects, revision)` (`rights.py:162`) and every
grant, revoke, posture or membership write bumps the one
`meta.grant_revision` (`bump_revision`, `rights.py:646`). Measured:
20 cached callers, one `grant` by the system actor, 20 of 20 miss.
Recompute per caller (rows read + two `resolve` calls, before pieces):
18 ms / 136 ms / 2.1 s. If every user reads once after one grant:
18 s / 23 min / 59 h of CPU at the three sizes — and each caller then
pays `pieces()` again on top (Wall 2).

### What held

- The range join itself (`ranges.py`, `visible_entries`) is sound and
  fast on SQLite at every N: count 9 / 31 / 284 ms, fetch of 201,206
  rows 746 ms, recall 1.00 with 0 extra rows every time, traps
  included. Statement text never changed; only the one JSON bind grew.
- On Postgres the join is correct (recall 1.00) but the planner
  misestimates the `unnest` join at 5.2 million rows against 2,254
  actual (see the plan in `runs/postgres-1000.md`), so it hash-joins
  the whole entry table and hash-aggregates with 128 planned
  partitions. Warm times swing between 8 ms and 600 ms for callers
  with identical shapes — consistent with asyncpg's prepared
  statement flipping between a custom and a generic plan after five
  executions. The statement never changing with the grants is exactly
  what blinds the generic plan to the array's size. 110 to 600 ms at
  N = 10,000.
- `resolve()` is linear in the rows it reads, but it reads all N
  everyone rows on every cold resolution (`_grant_rows`, every row
  naming `*`): 10 ms / 118 ms / 1.8 s cold.
- Bulk load through the shipped `bulk_insert`: 501,202 entries in 11 s
  on SQLite, 214,000 grants + 500,000 memberships in 4 s.

## Caveats and what surprised me

- The 100k world has 2 files per home (501k entries, not 2.3M). Said
  above; it only lowers row-count-bound numbers.
- The Postgres runs had to be restarted twice. The hole ladder's big
  statements, cancelled client-side at the cap, kept running
  server-side (leader in `BgworkerShutdown`, workers busy), blocked
  the table drop, and survived `pg_terminate_backend`. The shared
  server then went through crash recovery, dropping every connection
  (mine mid-load). The coordinator reports the server crashed twice
  during the other agent's 1M-row writes, so the wedged backends may
  only have been bystanders; which it was is not established. The bench now
  sets a server-side `statement_timeout` before every timed statement
  (it did not help against the wedge) and refuses to send a Postgres
  clause of more than 2,000 holes. The Postgres 10k numbers are from
  the third run, after the server recovered; 100k never completed
  (above). A cancelled
  asyncpg statement can outlive its client — worth knowing for vfs's
  own retry layer and for ADR 071's "each clause inside the budget"
  promise: on Postgres the budget that matters is not binds but
  planner time, and it is not interruptible.
- While cleaning that up, a `pg_terminate_backend` filtered on `query
  like '%bl_%'` also matched the other agent's `public_level` column
  and terminated one of its backends (pid 3471111). That agent may have
  seen one connection failure around then.
- The parallel agent reused this `bench.py` for its own SQLite 100k run
  at the same time as mine, so the SQLite 100k numbers were taken with
  one more CPU-bound process on the box (10 cores; no step here is
  multi-threaded).
- Surprise 1: the biggest wall at 100,000 is not any of the three the
  review named — it is the tuple scan in `_holed`, which turns every
  verb that checks rows in Python into minutes of CPU.
- Surprise 2: on Postgres the clause fan already costs more than a
  second at the smallest N, and the range join's plan is unstable
  across identical callers.
- Surprise 3: `meet` never shows up in this world. Dozens of grants per
  user is far below where a 50×50 product matters.
- Surprise 4: `pieces()` is worse than quadratic in practice (5× per
  doubling), so the review's "17 s at 10,000" is 100 s at 20,000 and
  about an hour and a quarter at 100,000.
