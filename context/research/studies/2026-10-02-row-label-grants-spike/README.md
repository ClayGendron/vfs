# Study: row-label grants — `public_level` on every row, grants as the caller's own ranges

- **Date:** 2026-10-02
- **Status:** executed study; nothing here is imported by vfs
- **Engines:** SQLite 3.50 (vfs's own pragmas) and Postgres 17, the two
  the brief allowed
- **Question:** the shipped grants design (spec 058, ADR 072) compiles
  one root arm with every private home subtracted as a hole, so a
  caller's rights grow with the number of *other* users and break near
  1,000 homes (review findings 4, 6, 7). Does putting the everyone
  level on the row — `public_level`, materialized at write and
  relabelled on a posture change — keep compile, bind size and read
  cost flat at 100,000 users, and what does the relabel cost?

See `results.md` for the result tables and "what held and what did
not". This file says what is here and how to rerun it.

## The shape under test

Every entry row carries two labels:

- `public_level` — the level the nearest covering posture row gives
  everyone (0 none, 1 read, 2 read_write). Stamped when the row is
  written; relabelled for a subtree when a posture changes.
- `domain_id` — the id of the nearest covering *boundary* (a posture
  or a grant prefix). Rows in one domain have identical coverage, so
  one domain id stands for every row's rights at once. This is the
  comparison variant.

Visible at level L:

| variant | predicate |
|---|---|
| `public_level` | `public_level >= L` OR `path` in the caller's ranges OR `owner_id = me` |
| `domain_id` | `domain_id IN (domains the caller may see)` OR `owner_id = me` |

The caller's ranges are ADR 072's pieces (exact points and open
ranges) built from the caller's **own** grants only — the rows naming
the subject or one of its groups. No posture row enters them and no
hole is cut, so they number dozens, not thousands. `prototype.py`
builds them with a linear sorted merge; a subject set takes the
sorted-merge intersection of its members' spans, and each member's
owner floor is the intersection of the *other* members' spans (the
plain `owner_id = me` when there is one member). The shipped quadratic
`_subtract` / `meet` are not reused.

The semantics the brief asked to preserve, and how the shape gives them:

- a private home's `none` posture blocks `*` but not an explicit grant
  that covers it: the home's rows carry `public_level = 0`, and the
  owner's grant on the home is in the owner's ranges, so the ranges
  branch admits them;
- a nested `shared` / `open` posture inside a private subtree reopens
  it: its rows are labelled from the nearest posture, which is the
  nested one;
- sibling traps (`/home/u000001-x` beside `/home/u000001`): the
  prefix's pieces are the exact point plus the open range
  `('/home/u000001/', '/home/u0000010')`, and the trap row is its own
  `none` posture, so neither branch admits it;
- a row moved across a posture boundary takes the destination's label
  in the same `UPDATE` that rewrites its path.

Every answer is checked against `truth()` in `prototype.py`, a plain
Python reading of spec 058's rules, and on a sample against the
shipped `Rights.admits` for the same world.

## What is here

| file | what it does |
|---|---|
| `world.py` | Builds the synthetic world at N users (the brief's parameters; see its docstring for the one choice made inside them: `g0000` is the grant-heavy group) and names the five callers. |
| `prototype.py` | The span algebra (cover, merge, intersect, subtract, split), the labeller (nearest posture, nearest boundary), the Python truth function, the compiler, the DDL and index set, the per-dialect statement text for both variants and five statement shapes, and the relabel span computation. |
| `bench.py` | Read mode (`--n`): load, index, truth, shipped-resolver check, compile timings, domain lists, statement timings cold and warm with recall, invalidation table, plans, index sizes. Writes mode (`--writes`): posture relabel over 1,000 and 1,000,000 rows (whole and keyset-chunked), the root relabel across every home, the domain-variant relabel, a new grant boundary, a 10,000-row move across a posture boundary, and the per-write label lookup. |
| `runs/` | `<engine>-<N>.md` for N in 1,000 / 10,000 / 100,000 per engine; `sqlite-writes.md` and `postgres-writes.md`; `postgres-<N>-jitoff.md` (the JIT-off probe, `RL_PG_JIT_OFF=1`); `sqlite-semantics.md` (the executed traps, `--semantics`). |
| `results.md` | The result tables across N and engines, and what held and what did not. |

## Rerun

Postgres up at `postgresql+asyncpg://vfs:vfs@localhost:54320/vfs` (or
set `RL_PG_URL`); SQLite needs nothing. Scratch defaults to the study's
job scratch directory (`RL_SCRATCH` overrides it). From this directory:

    uv run --no-sync python bench.py --engine sqlite --n 10000
    uv run --no-sync python bench.py --engine postgres --n 10000
    uv run --no-sync python bench.py --engine sqlite --n 100000 --chunks 1 --sample 500
    uv run --no-sync python bench.py --engine sqlite --writes
    uv run --no-sync python bench.py --engine sqlite --semantics
    RL_PG_JIT_OFF=1 uv run --no-sync python bench.py --engine postgres --n 10000

`--chunks` is chunks per file (3 by default; the 100,000-user runs
used 1 to stay inside the time budget). `--sample` is how many rows
the shipped `Rights.admits` is compared on (its hole tuple makes each
check O(homes)). `--reps` is the warm repeat count (3). Every table is
prefixed `rl_<hex>_` and dropped at the end; the SQLite file is
removed.

Wall time: N=1,000 a few seconds; N=10,000 about one to two minutes
per engine; N=100,000 about ten minutes per engine; writes about two
to four minutes per engine. Both engines can run at once.
