# Results: group permissions, max within each subject, min across the set

One full run of `model.py` on 2026-09-28 (Python 3.13.11, SQLite
3.50.4, seed 20260928, `uv run --no-sync python model.py`). The output
is reproduced verbatim below, section by section, each followed by how
to read it. The memo that draws on it is
`../../2026-09-28-group-permissions-max-within-min-across.md`.

## 1. Worked example: Ann, John, and the Ann + John session

| path | Ann | John | Ann + John (min) | groups pooled (wrong) | owner floor only for one (wrong) |
|---|---|---|---|---|---|
| `/design/mock.png` | read_write | read | **read** | read_write (LEAK) | read |
| `/eng/specs/api.md` | read_write | read_write | **read_write** | read_write | read_write |
| `/home/ann/diary.md` | read_write | invisible | **invisible** | invisible | invisible |
| `/home/ann/shared/plan.md` | read_write | read | **read** | read | invisible (over-hidden) |
| `/ops/runbook.md` | read | invisible | **invisible** | read (LEAK) | invisible |
| `/public/readme.md` | read | read | **read** | read | read |
| `/sales/deals.csv` | read | read_write | **read** | read_write (LEAK) | read |
| `/vault/keys.md` | read | invisible | **invisible** | read (LEAK) | invisible |

Ann + John at `read`: arms /public, /design, /eng, /sales; owner arms owner=ann AND under /home/ann/shared; owner=john AND under /ops, /vault; 16 binds.

Ann + John at `read_write`: arms /eng; owner arms owner=ann AND under /sales; owner=john AND under /design; 8 binds.

**Reading.** "Ann" and "John" are each person's maximum over their own
rows, their groups' rows (Ann reaches `eng` through `platform`), the
everyone row and the owner floor. "Ann + John" is the minimum of the
two. The script asserts that the resolver's arms reproduce that column
exactly. Pooling groups across the pair leaks four rows in both
directions. Dropping the owner floor for sets hides Ann's shared plan,
which both may read. Owner arms are trimmed of what the shared arms
already cover, so `john` carries arms for `/ops` and `/vault` even
though he owns nothing there: they would admit a row John owns that
Ann can read.

## 2. Algebra and SQL: 3000 random worlds, nested groups, posture rows, sets of 1 to 5

- checks: 454796
- correct_wrong: 0
- pooled_leaks: 16746
- pooled_hides: 0
- single_only_hides: 369
- nearest_holes_leaks: 30
- sql_mismatch: 0
- literal_root_hides: 220865

**Reading.** `checks` counts (world, set, path, level) cases.
`correct_wrong` and `sql_mismatch` are the resolver and its compiled
SQLite `WHERE` against the per-row oracle: both zero. The four wrong
variants: pooling groups across the set leaks (16,746); the owner floor
only for a set of one over-hides (369, no leaks); posture holes attached
only to the nearest `*` row leak (30); compiling `/` as `LIKE '//%'`
over-hides almost everything under a root grant (220,865).

## 3. Budgets: S1-shaped grants, 2,000 users, 300 team groups (270 nested one level), 20 random sets per cell, level read

| n | groups each | distinct ids fetched | fetch stmts Oracle / SQL Server | walk stmts | cover per member (median) | meet arms | owner arms | literal binds (median / max) | literal over SQL Server budget | fallback binds, per-member group lists (median / max) | fallback over SQL Server budget | largest one-member id list |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0 | 3 | 1 / 1 | 2 | 7 | 7 | 1 | 25 / 25 | 0/20 | 4 / 4 | 0/20 | 2 |
| 2 | 0 | 4 | 1 / 1 | 2 | 7 | 2 | 2 | 36 / 36 | 0/20 | 8 / 8 | 0/20 | 2 |
| 5 | 0 | 7 | 1 / 1 | 2 | 7 | 2 | 0 | 14 / 14 | 0/20 | 20 / 20 | 0/20 | 2 |
| 20 | 0 | 22 | 1 / 1 | 2 | 7 | 2 | 0 | 14 / 14 | 0/20 | 80 / 80 | 0/20 | 2 |
| 64 | 0 | 66 | 1 / 1 | 2 | 7 | 2 | 0 | 14 / 14 | 0/20 | 256 / 256 | 0/20 | 2 |
| 1 | 3 | 9 | 1 / 1 | 3 | 26 | 26 | 1 | 64 / 73 | 0/20 | 10 / 10 | 0/20 | 8 |
| 2 | 3 | 15 | 1 / 1 | 3 | 27 | 10 | 2 | 109 / 122 | 0/20 | 20 / 20 | 0/20 | 8 |
| 5 | 3 | 31 | 1 / 1 | 3 | 26 | 4 | 3 | 32 / 48 | 0/20 | 48 / 50 | 0/20 | 8 |
| 20 | 3 | 97 | 1 / 1 | 3 | 26 | 2 | 0 | 14 / 32 | 0/20 | 193 / 198 | 0/20 | 8 |
| 64 | 3 | 223 | 1 / 1 | 3 | 26 | 2 | 0 | 14 / 14 | 0/20 | 617 / 623 | 0/20 | 8 |
| 1 | 10 | 21 | 1 / 1 | 3 | 56 | 56 | 1 | 123 / 139 | 0/20 | 22 / 24 | 0/20 | 22 |
| 2 | 10 | 37 | 1 / 1 | 3 | 52 | 22 | 2 | 195 / 232 | 0/20 | 44 / 47 | 0/20 | 22 |
| 5 | 10 | 74 | 1 / 1 | 3 | 54 | 12 | 5 | 70 / 101 | 0/20 | 109 / 112 | 0/20 | 22 |
| 20 | 10 | 183 | 1 / 1 | 3 | 54 | 6 | 4 | 40 / 64 | 0/20 | 429 / 443 | 0/20 | 22 |
| 64 | 10 | 335 | 1 / 1 | 3 | 54 | 3 | 1 | 20 / 45 | 0/20 | 1387 / 1405 | 0/20 | 22 |
| 1 | 50 | 72 | 1 / 1 | 3 | 128 | 128 | 1 | 268 / 287 | 0/20 | 73 / 78 | 0/20 | 76 |
| 2 | 50 | 116 | 1 / 1 | 3 | 126 | 88 | 2 | 394 / 458 | 0/20 | 147 / 153 | 0/20 | 76 |
| 5 | 50 | 197 | 1 / 1 | 3 | 128 | 60 | 5 | 217 / 269 | 0/20 | 367 / 376 | 0/20 | 78 |
| 20 | 50 | 315 | 1 / 1 | 3 | 127 | 32 | 11 | 128 / 146 | 0/20 | 1467 / 1484 | 0/20 | 78 |
| 64 | 50 | 366 | 1 / 1 | 2 | 127 | 24 | 10 | 103 / 122 | 0/20 | 4697 / 4750 | 20/20 | 80 |

SQL Server arm cap by binds alone: (2099 - 32) // 2 = 1033 arms.

**Reading.** Columns: distinct principal ids the grant fetch reads
(subjects, closure groups, `*`) and the `IN` statements that takes on
Oracle and SQL Server; statements the membership walk takes (one per
nesting level, plus the final empty frontier); the median covering-set
size per member; arms in the meet; owner arms emitted after trimming;
binds of the literal predicate; binds of an `EXISTS` fallback that
lists each member's ids (`owner_id = :s OR EXISTS (… principal_id IN
(:s, :g1, …) AND level >= :l …)`, three fixed binds plus the closure
per member); and the largest single member's id list (Oracle's `IN`
cap is 1,000). Groups grow each member's covering set (7 to 128); the
meet shrinks the set's predicate as it grows (at 50 groups: 128 arms
for one person, 24 for 64 people). The literal never exceeds 458
binds. The fallback grows with members times groups and exceeds SQL
Server's budget in every sample at 64 members with 50 groups each.

## 4. SQLite 3.50.4: the literal predicate parses up to 998 arms (1996 binds), one more fails

- spec 058's bind-only cap on SQLite would be (32,700 - 32) // 2 = 16334 arms

**Reading.** Bisection on SQLite: 998 arms of `(path = ? OR path LIKE ?
ESCAPE '\')` parse; 999 do not (a direct try at 1,000 arms fails with "Expression
tree is too large (maximum depth 1000)"). The limit is `SQLITE_MAX_EXPR_DEPTH`, not the
bind budget, so a bind-only cap is sixteen times too high on SQLite.

## 5. Nesting: a 13-deep chain and a cycle

- cap 4: refused (group walk from ann deeper than 4)
- cap 8: refused (group walk from ann deeper than 8)
- cap 16: walk finished at depth 13, 13 groups
- cycle a -> b -> a: walk terminates at depth 2 with ['group:a', 'group:b'] (visited set)

**Reading.** The walk refuses a chain deeper than its cap rather than
truncating it, and a cycle terminates because the walk keeps a visited
set. Refusing cycles at write is still recommended (Postgres and Oak
both do), since a cycle is always a mistake.
