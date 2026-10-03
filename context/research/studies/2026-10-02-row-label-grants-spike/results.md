# Results: row-label grants at 1,000, 10,000 and 100,000 users

Short version. Putting the everyone level on the row works. The
caller's compiled rights stop depending on how many other users exist:
the ordinary caller's bind is about 2 KB and 22 µs at every N, while
the shipped resolver takes 2 seconds and 5 ms per `admits` call at
100,000 homes. Every statement returned exactly the right rows on both
engines at every N, including the sibling traps, the nested re-opened
folder and the moved subtree. A posture change costs a bounded relabel
`UPDATE` — 2 s per million rows on SQLite, 17 s on Postgres — and it
can be chunked by path range so no statement is unbounded. The
`public_level` variant is the one to take; the `domain_id` variant's
bind grows with the number of boundaries the posture reaches (1,002 ids
at N=100,000) and loses the scoped read. Postgres needs one planner fix
for the `UNION` shape (a default range selectivity inflates the range
branch's estimate 1,300×), which the inline-predicate shape avoids.

All runs: median of 3 warm runs on one connection; cold is the first
run on a fresh connection (the OS cache and Postgres shared buffers
were not purged). Postgres was shared with another agent's jobs for
the whole study (200-second counts ran beside mine), so Postgres
numbers carry noise; SQLite numbers do not. Full tables with plans are
in `runs/`.

## 1. Compile: the caller's own grants → sorted pieces

The pieces are exact points plus open ranges built from the rows that
name the subject or one of its groups. No posture row enters, no hole
is cut. `points` = `opens` because every prefix gives one of each.

| N | caller | grants held | points | bind bytes | compile µs | shipped `resolve` ms | shipped holes | shipped `admits` µs/row |
|---|---|---|---|---|---|---|---|---|
| 1,000 | ordinary | 41 | 11 | 630 | 23 | 3–4 | 1,100 | 11 |
| 10,000 | ordinary | 49 | 44 | 2,445 | 31 | 139–204 | 10,100 | 115 |
| 100,000 | ordinary | 36 | 36 | 2,005 | 22 | 1,855–2,084 | 100,100 | 4,859–6,031 |
| 1,000 | heavy group | 41 | 11 | 630 | 22 | 3 | 1,100 | 11 |
| 10,000 | heavy group | 46 | 44 | 2,445 | 27 | 115–132 | 10,100 | 106–114 |
| 100,000 | heavy group | 244 | 232 | 12,785 | 146 | 9,930–10,294 | 100,100 | 4,783–5,436 |
| 1,000 | two subjects | 82 | 10 (+44 owner) | 1,804 | 56 | 4 | 1,100 | 11 |
| 10,000 | two subjects | 104 | 21 (+178 owner) | 6,094 | 96 | 70–87 | 10,100 | 102–121 |
| 100,000 | two subjects | 76 | 13 (+152 owner) | 4,939 | 77 | 858–1,161 | 100,100 | 5,147–5,564 |

What this shows. The ordinary caller's pieces follow its own grants
(one home plus five groups' folders): 11 at N=1,000 only because there
are 10 shared folders in total there, 36 to 44 above that, and the
number moves with the seeded group draw, not with N. The heavy group
member holds `8 + S/5` grants by construction (S = N/100 shared
folders), so its bind grows with N as a *caller-sized* quantity: 232
pieces and 12.8 KB at 100,000 users. The shipped resolver carries every
other user's home as a hole on the root arm: 100,100 holes, 2 to 10
seconds to resolve, and 5 ms per `admits` call (a tuple scan of the
holes per ancestor). Compile time here is 22 to 146 µs.

The two-subject authority's owner floor is the intersection of the
*other* member's spans, which is why it carries 150 to 180 owner
pieces: the partner's five groups cover that many folders. It is
still caller-sized.

The SQL that feeds the compile (grant rows by principal and by the
subject's groups, one statement) is 0.2 to 1.0 ms warm on SQLite.
On Postgres it measured 7 to 22 ms because my statement's shape — an
`OR` between an array match and an `IN (subquery)` — defeats the
index; see §7 for the two-branch shape that fixes it.

## 2. Reads: the ordinary caller, warm ms

Statements: `entries` = every visible entry id (a `UNION` of index
seeks: the `public_level` index, the point and range joins, the owner
index); `scoped` = the same under `/shared/s0001`; `count` = visible
chunks through a derived table; `top10` = ten chunks by score through
the derived table; `top10 probe` = the same with the visibility as one
inline predicate on the entry row, so the engine may walk the score
index and stop early.

| N | visible entries | statement | SQLite public | SQLite domain | Postgres public | Postgres domain |
|---|---|---|---|---|---|---|
| 1,000 | 2,034 | entries | 1.8 | 2.0 | 3.6 | 2.9 |
| | | scoped | 1.3 | 0.3 | 1.9 | 1.4 |
| | | count | 1.1 | 1.0 | 6.7 | 7.6 |
| | | top10 | 1.5 | 1.7 | 7.9 | 5.9 |
| | | top10 probe | 1.2 | 1.9 | 3.1 | 1.8 |
| 10,000 | 20,124 | entries | 28.0 | 23.6 | 77.7 | 27.5 |
| | | scoped | 7.7 | 4.9 | 5.6 | 6.0 |
| | | count | 13.9 | 14.3 | 98.8 | 46.7 |
| | | top10 | 18.0 | 16.7 | 59.9 | 28.0 |
| | | top10 probe | 12.4 | 9.1 | 2.4 | 1.9 |
| 100,000 | 201,024 | entries | 311 | 331 | 757 | 462 |
| | | scoped | 2.5 | 15.7 | 2.5 | 2.8 |
| | | count | 56.7 | 57.8 | 504 | 310 |
| | | top10 | 64.8 | 66.0 | 765 | 285 |
| | | top10 probe | 1.3 | 61.4 | 2.0 | 2.6 |

Recall was exact in every cell, for every caller, at every N, on both
engines (the `runs/` files print it per cell).

What this shows.

- **Read cost follows what the caller can see, not N.** Nothing in
  the predicate scales with the user count. `entries` at 100,000 is
  dominated by fetching 201,024 ids (the system caller, with no
  predicate at all, takes 1.9 s on SQLite and 2.3 s on Postgres to
  fetch 2.3 M). `count` and `top10` through the derived table are
  the cost of touching 200,000 chunk rows.
- **The scoped read is where `(public_level, path)` earns its place.**
  SQLite serves it from that index (`ANY(public_level) AND path>? AND
  path<?`, 2.5 ms at 100,000). The domain variant has no index that
  combines "domain in list" with "path in range", so it seeks 1,002
  domains and filters: 15.7 ms, and growing with the list.
- **The probe shape is a planner choice, not a guarantee.** With the
  `public_level` predicate, both engines walk the score index for the
  ordinary caller and stop after a handful of rows (1.3 to 2 ms at
  100,000). SQLite does *not* do it for the anonymous caller, whose
  predicate is the single term `public_level >= 1`: it starts from
  the public index and sorts 200,000 chunks (43 ms). For the domain
  variant SQLite picks a multi-index OR and sorts (61 ms). The
  vector-leg count gate ADR will have to choose the shape per
  dialect, as ADR 072 already expects.
- **Postgres's `UNION` shape needs a planner fix.** At 100,000 the
  range-join branch is estimated at 9.2 M rows (255,678 per range —
  the default inequality selectivity, 1/9 of the table — times 36
  ranges) against 7,020 actual. That makes the `UNION`'s hash
  aggregate plan 128 partitions and spill 8 MB to disk, and turns on
  JIT (68 ms of compilation per statement). The same misestimate hits
  ADR 072's shipped range join. The domain variant does not suffer
  because `domain_id = ANY(array)` estimates well. The JIT-off probe
  (§6) separates the two effects. The inline predicate (`top10
  probe`) estimates fine and is 2 ms.

## 3. Writes: the relabel cost

SQLite, a 1,000-user world plus `/mid` (1,000 rows), `/mv` (10,000)
and `/big` (1,000,000), median of 3; every row's label checked against
the Python labeller after each change.

| operation | shape | statements | rows touched | ms |
|---|---|---|---|---|
| posture `/mid` → shared | range join, one statement per ≤500 pieces | 2 | 1,001 | 3 |
| posture `/mid` → shared | keyset chunks of 500 rows | 7 | 1,001 | 5 |
| posture `/big` → shared | range join | 2 | 1,000,001 | 1,962 |
| posture `/big` → shared | keyset chunks of 50,000 | 43 | 1,000,001 | 1,433 |
| posture `/big` → shared | keyset chunks of 200,000 | 13 | 1,000,001 | 1,829 |
| posture `/` → shared, 1,102 deeper postures cut | range join (1,103 points + 2,205 ranges) | 8 | 12,014 | 70 |
| posture `/` → shared | keyset per range | 4,413 | 12,014 | 810 |
| domain variant: posture `/mid` | `domain_id = :d` | 1 | 1,001 | 3 |
| domain variant: posture `/big` | `domain_id = :d` | 1 | 1,000,001 | 1,736 |
| grant at a new prefix over `/big`, `public_level` variant | nothing to write | 0 | 0 | 0 |
| grant at a new prefix over `/big`, domain variant | relabel `domain_id` by path range | 1 | 1,000,000 | 758 |
| move `/mv` → `/home/u000000/mv` (open → private) | one `UPDATE`: path rewrite + destination labels | 1 | 10,001 | 34 |
| label lookup for one new row (6-deep path) | `path IN (ancestors)` on the domain table | 1 | 1 | 0.24 |

Postgres, same world. Three attempts: with a 1,000,000-row `/big`
the server fell over twice right after the three 1M-row relabels
(attempt 1: "connection was closed in the middle of operation";
attempt 2: the next connection found the server in crash recovery —
a backend crash in a 128 MB-shared-buffers container that had just
taken nine million dead tuples, beside the other agent's jobs). The
third attempt used a 200,000-row `/big` and completed every step;
its root relabel ran the very statement the earlier attempts died
on, in 305 ms. The 1M-row rows below are attempt 1's; the rest are
attempt 3's (`runs/postgres-writes.md`).

| operation | shape | statements | rows touched | ms |
|---|---|---|---|---|
| posture `/mid` → shared | range join | 2 | 1,001 | 27 (180 on the first-ever statement) |
| posture `/mid` → shared | keyset chunks of 500 | 7 | 1,001 | 16 |
| posture `/big` (1M) → shared | range join | 2 | 1,000,001 | 16,766 |
| posture `/big` (1M) → shared | keyset chunks of 50,000 | 43 | 1,000,001 | 16,006 |
| posture `/big` (1M) → shared | keyset chunks of 200,000 | 13 | 1,000,001 | 16,062 |
| posture `/big` (200k) → shared | range join | 2 | 200,001 | 1,895 |
| posture `/big` (200k) → shared | keyset chunks of 50,000 | 11 | 200,001 | 1,865 |
| posture `/` → shared, 1,102 deeper postures cut | range join (3,308 pieces) | 8 | 12,014 | 305 |
| posture `/` → shared | keyset per range | 4,413 | 12,014 | 2,832 |
| domain variant: posture `/mid` | `domain_id = :d` | 1 | 1,001 | 39 |
| domain variant: posture `/big` (200k) | `domain_id = :d` | 1 | 200,001 | 2,151 |
| grant at a new prefix over `/big` (200k), domain variant | relabel `domain_id` by path range | 1 | 200,000 | 2,271 |
| move `/mv` → `/home/u000000/mv` | one `UPDATE` | 1 | 10,001 | 87 |
| label lookup for one new row | `path IN (ancestors)` | 1 | 1 | 1.3 |

A plain `EXPLAIN` of the root relabel on Postgres (scratch diagnostic,
1,000-user world) shows the statement shape matters there: the
`UPDATE … WHERE id IN (SELECT e.id FROM unnest(…) r JOIN e ON path >
lo AND path < hi)` form plans a sequential scan of the whole entries
table with a nested-loop semi-join testing every row against all 500
ranges (rows × ranges); the `UPDATE e SET … FROM unnest(…) r WHERE
e.path > r.lo AND e.path < r.hi` form seeks the path index once per
range. On the 23k-row world both take about 30 ms in batches of 500
(50 to 60 ms in batches of 100), so the timing hides it; on a
million-row table the `IN` form is the wrong plan. The relabel
should be written in the `FROM` form on Postgres.

Postgres relabels at about 10 to 16 µs per row, eight times SQLite's
2 µs: every updated tuple is a new tuple version with five indexes to
maintain (an indexed `public_level` rules out HOT updates), and a
million-row relabel leaves a million dead tuples for vacuum. Chunking
does not change the total on Postgres; it bounds each statement.

What this shows.

- **The relabel is bounded two ways.** Binds: the ranges travel as
  ADR 072 pieces, at most 500 per statement. Rows: an open range can
  be walked by keyset (`ORDER BY path LIMIT 1 OFFSET k` for the
  boundary, then `path > cur AND path <= boundary`), so no single
  statement touches more than k rows. On SQLite the chunked walk is
  *faster* than the whole-range statement; on Postgres it costs the
  same. What chunking does not bound is the transaction: a
  million-row relabel in one transaction is what put the test
  container into crash recovery twice, so the chunks need their own
  transactions and the posture row needs a revision that gates the
  subtree while the labels catch up (see the decisions below). The root relabel across every home is the hole algebra again,
  but local to one write and linear: 3,308 pieces in 8 statements.
- **The per-range keyset is the wrong chunking for many small
  ranges** (4,413 statements for the root). The right rule is: count
  first, batch small ranges through the range join, keyset only the
  ranges bigger than the chunk. Not built here.
- **A grant costs no row write** in the `public_level` variant; in
  the domain variant every new boundary relabels its subtree (758 ms
  per million rows). That is the second reason to prefer
  `public_level`.
- **A move takes the destination's label in the same statement** as
  the path rewrite. A moved subtree that *contains* boundaries would
  need the "range minus deeper boundaries" computation at the
  destination; this run's subtree had none.

## 4. Semantics, executed

`runs/sqlite-semantics.md`: a 1,000-user world, then `shared` set on
`/home/u000001/pub` (a nested re-open inside a private home) and
`/mv` moved from under the open root into `/home/u000002`. Five
callers through both variants, every answer equal to the truth
function:

- the nested shared folder is visible to everyone; the rest of the
  home stays hidden; the owner sees the whole home through its grant;
- the sibling trap `/home/u000001-x` is visible to nobody;
- the moved rows are visible to the destination's owner (grant) and
  hidden from bystanders and from anonymous;
- **the moved rows stay visible to their former owner `u000005`
  through the owner floor.** The truth function, both variants and
  the shipped single-subject owner arm all agree, because
  `owner_id = me` is mount-wide in the spec's rules. Whether a move
  into another user's private home should keep the mover's floor is
  a question for the spec, not a bug in the shape.

Across the main runs the shipped `Rights.admits` agreed with the
truth function on every sampled row (5,000 rows per caller at 1,000
and 10,000 users, 500 at 100,000 where each check costs 5 ms).

## 5. Cache invalidation

Per-caller recompute = fetch the caller's grant rows + merge: 0.25 to
0.3 ms warm on SQLite, 2 to 22 ms on Postgres with the slow fetch
shape (§7). Callers invalidated by one write:

| write | global revision | per-principal + per-group + posture revisions |
|---|---|---|
| grant to one user | N | 1 |
| grant to a group | N | the group's members (~1,000 at every N here: 5 groups per user, N/200 groups) |
| posture change | N | **0** — the posture is on the rows, not in any caller's pieces |

At N=100,000 a global revision means 100,000 recomputes per grant
write: 25 s of SQLite work or 37 minutes of Postgres work with the
slow fetch, spread over the next request of every active caller.
Granular revisions make a user grant cost one recompute and a group
grant about 1,000. So granularity still matters, by a factor of N for
user grants and N/1,000 for group grants — but the *posture* row
disappears from the compile entirely, which is the write that
invalidated everyone under the shipped design. A principal's
revision can be `max(own, groups')`, read in the same statement as the
closures.

## 6. Postgres with JIT off

`runs/postgres-10000-jitoff.md` and `runs/postgres-100000-jitoff.md`
repeat the Postgres runs with `SET jit = off` on every connection.
They did not separate the effects cleanly: the server was shared, and
the warm numbers moved both ways between the two runs (ordinary
`entries` 757 → 724 ms, `count` 504 → 632, anonymous `entries` 312 →
667), which is contention, not JIT. The `EXPLAIN ANALYZE` in the
JIT-on run is the better witness: of 253 ms for the ordinary
`entries` statement at 100,000, JIT accounted for 68 ms and the
128-partition, disk-spilling hash aggregate for the rest. So turning
JIT off is worth a quarter of the cost; the estimate is the real
problem. Two fixes are known to work on Postgres and neither was
built here: fence the range branch so the planner stops multiplying
(`OFFSET 0` on the subquery, or a `MATERIALIZED` CTE), or make the
branches disjoint and use `UNION ALL` so no aggregate is planned at
all (the ranges branch gains `AND public_level < :level`; the owner
branch overlaps the ranges only where the caller is granted its own
rows, which the owner-floor decision in the last section touches).

## 7. The grants fetch statement

The bench fetched a caller's grant rows as `principal_id = ANY(:subs)
OR principal_id IN (SELECT group_id FROM memberships WHERE
principal_id = ANY(:subs))`. On Postgres at 100,000 users (214,101
grant rows) that is a sequential scan: 21.5 ms. The same rows as a
`UNION ALL` of two index seeks (the subject's own rows; the groups'
rows through a nested loop over the membership index) take 0.26 ms.
The Postgres "grants fetch" and "recompute" numbers in §1 and §5
should be read with the 0.26 ms shape in mind; vfs's own
`_grant_rows` already reads by a chunked `IN` list of ids, which is
the fast shape.

## 8. Indexes

| index | SQLite 10k | Postgres 10k | SQLite 100k | Postgres 100k |
|---|---|---|---|---|
| `path` (unique) | 6.8 MB | 9.3 MB | 68.3 MB | 92.6 MB |
| `owner_id` | 3.6 | 1.8 | 36.1 | 18.0 |
| `public_level` | 2.1 | 1.6 | 20.9 | 16.0 |
| `(public_level, path)` | 7.1 | 9.3 | 70.9 | 92.6 |
| `domain_id` | 2.5 | 1.8 | 27.0 | 17.8 |
| entries table (230k / 2.3M rows) | 9.6 | 18.0 | 97.4 | 174.7 |

`public_level` alone is small (a three-valued column). The composite
`(public_level, path)` costs as much as the path index itself and is
the one that serves scoped reads; with it, the single-column
`public_level` index is redundant on both engines (every plan that
used it could use the composite's leading column). The right set for
the `public_level` variant is `path`, `(public_level, path)`,
`owner_id`. Index build time was under 2 s each at 2.3 M rows.

## What held and what did not

Held:

- Compile and bind size are independent of N: caller-sized at 1,000,
  10,000 and 100,000 users, 22 to 146 µs, 0.6 to 12.8 KB.
- Exact recall everywhere, including the three traps the brief named
  and a moved subtree.
- Read cost follows the visible set; the `public_level` predicate is
  one index compare with no holes.
- A posture change is a bounded relabel: ~2 s per million rows on
  SQLite, 17 s on Postgres, chunkable by path range; a posture change
  invalidates no compiled rights.
- The `public_level` variant beats the `domain_id` variant: constant
  bind, grants are write-free, scoped reads use the composite index.

Did not hold, or needs a decision:

- Postgres's `UNION`-of-branches shape is misestimated 1,300× on the
  range branch and pays for it (disk-spilling aggregate, JIT). The
  inline predicate does not. The fix is a statement-shape question
  for the spec (see §6 for what JIT alone accounts for).
- The owner floor follows a row into another user's private home.
- The per-range keyset chunking explodes on many small ranges; the
  batching rule above is needed before the relabel is written.
- Postgres relabel is 8× SQLite's per row; a 10 M-row subtree would
  take minutes and should run outside the posture verb's transaction
  (the rows are mislabelled until it finishes, so the posture row's
  own revision must gate reads of the subtree meanwhile — not
  designed here). A 1M-row `/big` relabelled nine times in one run
  crashed the shared test Postgres twice; the 200k-row run was clean.
- Not measured: a moved subtree containing its own boundaries; the
  `(public_level, path)` index under concurrent relabel and read;
  SQL Server, MariaDB and Oracle spellings (out of scope by the
  brief).

## What I would want decided before this became a spec

1. **Owner floor scope.** Is `owner_id = me` mount-wide (today), or
   bounded by the row's current domain? The move case makes this
   visible.
2. **Relabel transaction boundary.** Does the posture verb own the
   relabel, or does it write the posture row and a relabel task, with
   the subtree's reads gated on a per-posture revision until the
   labels catch up?
3. **The statement shape on Postgres.** `UNION` of index seeks with a
   planner hint (`SET LOCAL jit = off`, or an `OFFSET 0` fence on the
   range branch), or the inline predicate everywhere, or per-dialect.
4. **Chunking rule for the relabel**: count-then-batch, with the chunk
   size as a dialect fact beside `in_list_budget`; and the relabel
   statement in the `UPDATE … FROM` form on Postgres, so each range is
   an index seek rather than a table scan.
5. **Whether `domain_id` is kept at all.** It buys nothing the
   measurements reward; dropping it removes one index and the
   boundary table.
