# Grants at 100,000 users: what the shipped design costs, and what a row label and a sorted-merge algebra buy

- **Status:** research memo. Commits us to nothing. Input to the ADR
  that will amend the grants compile model (ADR 067 and 072) and to
  the fix for review findings 2, 4, 6 and 7 of 2026-10-01. Companion
  to the prior-art memo of the same day,
  [`2026-10-02-row-labelled-acls-and-the-list-problem-prior-art.md`](2026-10-02-row-labelled-acls-and-the-list-problem-prior-art.md).
- **Date:** 2026-10-02
- **Owner:** Clay Gendron
- **Question:** vfs must serve 100,000 or more users, each with a
  private home folder, each granted dozens of shared folders. The
  shipped design compiles each caller's rights from the grant rows,
  and the mount's open posture becomes one root *arm* with every
  private home cut out of it as a *hole*. The 2026-10-01 review
  measured that shape failing at about 1,000 homes. Three questions:
  (1) exactly what does the shipped design cost on the way to 100,000
  users, and where does it stop working; (2) does putting the
  everyone level on the row, as the prior art suggests, make the
  caller's rights independent of the user count; (3) can the range
  algebra in `grants.py` become linear with the same answers.
- **Method:** three executed studies, run in parallel on 2026-10-02,
  on SQLite 3.50 and Postgres 17 only (the other three engines are
  deferred, see §7). Two of them build the same seeded world so their
  numbers compare: users `u000000..`, root posture open, one private
  home per user with a `read_write` self-grant, N/100 shared folders,
  N/200 groups, five groups per user, each shared folder granting
  `read` to three groups, `read_write` to one, and `read` to ten
  users; 20 files per home (2 at N=100,000 in the baseline), 200 per
  shared folder, 100 sibling traps. N ∈ {1,000, 10,000, 100,000}.
  1. **Baseline**: the shipped `resolve`, `pieces`, range join,
     clause fan and `DatabaseStorage` verbs at each N.
     `studies/2026-10-02-grants-at-100k-users-baseline/`.
  2. **Row-label prototype**: a standalone schema with a per-row
     `public_level`, explicit grants as ADR 072 path ranges built by a
     linear merge, the owner floor as `owner_id = me`; the same
     statements, plus relabel, move and invalidation costs. A
     `domain_id` variant beside it.
     `studies/2026-10-02-row-label-grants-spike/`.
  3. **Sorted-merge algebra**: a pure-Python range algebra that
     replaces every pairwise loop in `grants.py`, held against the
     oracle and the shipped code on 4,000 worlds and 100,000 fuzz
     cases. `studies/2026-10-02-sorted-merge-range-algebra/`.
- **Sources:** the three study directories above (each with `README.md`,
  `results.md` and `runs/`), the review report of 2026-10-01 (session
  scratch, findings 2, 4, 5, 6, 7), `src/vfs/storage/grants.py` and
  `src/vfs/storage/backends/database/{rights,ranges}.py` at `4759bc6`.
- **Caveat on Postgres numbers:** the two database studies shared one
  Postgres container for the whole hour. It went into crash recovery
  twice under the prototype's million-row relabels, and once the
  baseline's table cleanup terminated one of the prototype's backends
  by mistake (its name filter matched the `public_level` column). The
  baseline lost two attempts at N=100,000 to the recoveries and was
  stopped on the third, so its Postgres series ends at 10,000. All
  Postgres timings carry contention noise; SQLite's do not. The
  baseline's 100,000-user world used 2 files per home instead of 20,
  which lowers only the row-count-bound numbers; every wall it found
  is a hole-count wall, and holes equal N.

## Terms used here

- **Arm**: one prefix a caller may read, with the holes cut from it.
- **Hole**: a lower posture row inside an everyone arm; the shipped
  compiler subtracts it.
- **Piece**: ADR 072's unit — an exact path, or an open range
  `lo < path < hi` — sent to SQL as one bound value.
- **Row label**: a column on the entry row that records a fact about
  the row's position. Here, `public_level`: the `*` posture level
  that reaches the row.
- **Relabel**: the `UPDATE` that rewrites labels under a path when a
  posture changes.
- **Caller-sized**: grows with the caller's own grants and groups.
  **World-sized**: grows with the number of other users.

## Bottom line

1. **The shipped design is world-sized, and it stops working between
   1,000 and 10,000 users.** At 100,000 users on SQLite, an ordinary
   caller's rights are one arm with 100,000 holes: 1.8 s to resolve,
   `pieces()` does not finish in 60 s (about 75 minutes by its
   ladder), the pieces are 300,000 long and 9.2 MB as a bind, `tree`,
   `glob` and `ls` all time out at 60 s, `Rights.admits` costs 4 ms
   per row, and one cached `Rights` is 42 MB (the 256-entry cache
   would be 10.9 GB). The clause fan fails at exactly 1,000 holes on
   SQLite and wedges the Postgres backend at 5,000. §1.
2. **The row label makes the caller's rights caller-sized, and the
   numbers prove it.** With `public_level` on the row, an ordinary
   caller compiles to 11 to 44 pieces, about 2 KB, in 22 to 31 µs at
   every N. Reads follow the visible set, not N: a scoped read is
   2.5 ms on both engines at 100,000 users. Recall was exact in every
   cell. A posture change relabels its subtree in 2 s per million
   rows on SQLite and 17 s on Postgres, chunkable, and invalidates no
   compiled rights. §2.
3. **The algebra becomes linear with identical answers, and the
   sibling bug goes away.** 3.76 million three-way `admits` checks
   with zero disagreements; 100,000 fuzz worlds with zero invariant
   breaks. 100,000 holes: 287 ms instead of a projected 27 minutes.
   Two members over 10,000 grants: 57 ms instead of 26 s. §3.
4. **Both changes are needed.** The algebra alone leaves the holes in
   the compile (287 ms per caller at 100,000 users, and a 9 MB bind
   per query). The label alone leaves the meet across members
   quadratic. Together: the everyone level is a column compare, the
   caller's own grants are a few dozen ranges, and every operation on
   them is one pass. §4.
5. **Five choices are open**, listed in §6 with the evidence each
   needs: level or handle; owner-floor scope on a move into a private
   home; what label a trashed row carries; synchronous relabel or a
   gated stale window; and the Postgres statement shape.

## 1. Baseline: the shipped design on the way to 100,000 users

The numbers below are the ordinary caller (one home, five groups) on
SQLite, from `baseline/runs/sqlite-{1000,10000,100000}.md`. Postgres
agrees in shape at 1,000 and 10,000 (`runs/postgres-*.md`).

| N | holes | `resolve` cold | shipped `pieces` | linear pieces | pieces | bind bytes | range-join count | `admits` per row | `tree /` cold |
|---|---|---|---|---|---|---|---|---|---|
| 1,000 | 1,000 | 10 ms | 119 ms | 1.3 ms | 3,000 | 92 KB | 9 ms | 21 µs | 0.2 s |
| 10,000 | 10,000 | 118 ms | 18.4 s | 17 ms | 30,000 | 920 KB | 31 ms | 200 µs | 21.2 s |
| 100,000 | 100,000 | 1.8 s | > 60 s (stopped) | 264 ms | 300,000 | 9.2 MB | 284 ms | 4.3 ms | > 60 s (stopped) |

What each column shows.

- **Every cost is world-sized.** The ordinary caller holds 41 grants
  of its own. Nothing in the row above moves with 41; everything
  moves with N. The holes come from `_everyone_arms`
  (`grants.py:309-324`), which folds every lower posture row in the
  mount into the root arm of every caller.
- **`pieces()` is worse than quadratic.** 119 ms, 18.4 s, then not
  finishing. The study's pure ladder (1k, 2k, 5k, 10k, 20k holes:
  0.11, 0.47, 4.1, 20.0, 101.8 s) fits an exponent of about 2.3,
  which puts 100,000 holes near 75 minutes. The study's linear
  re-implementation of the same function gives identical pieces
  (checked equal at 1,000 and 10,000) in 1.3, 17 and 264 ms. That is
  review finding 6, measured to its end.
- **`admits` is the wall that would survive the other fixes.**
  `_holed` (`grants.py:306`) tests `ancestor in arm.holes` on a tuple,
  so one admit under the root arm costs 21 µs, 200 µs, then 4.3 ms as
  the holes grow. Every row-check loop (`reads.py:555`,
  `_children_by_parent` at 647 and 652, glob, grep, glean) multiplies
  that by its rows: minutes at 100,000 users. The review did not name
  this one; the study found it to be the dominant cost at 100,000.
- **`meet` is not reached at "dozens of grants".** The two-subject
  pair resolves in 36 ms at 10,000 users and 271 ms at 100,000,
  because each member holds 41 to 71 prefixes. The cross product
  shows only when a group carries thousands of grants (25.4 s for a
  pair over a 10,000-grant group, against 19 ms single). It is a
  real wall, but a different layout triggers it.
- **The bind is the next wall.** Even with linear pieces, the range
  join sends 9.2 MB per statement at 100,000 users, and the engine
  unpacks 300,000 rows from it before the first index seek. The
  count still answers in 284 ms on SQLite, which says the join itself
  is sound; it is the input that is wrong-sized.
- **The clause fan is already dead at 1,000.** One unit carries 2
  binds per hole (`rights.py:731-735`, review finding 4). SQLite
  fails at exactly 1,000 holes ("Expression tree is too large,
  maximum depth 1000"; 990 passes), so the N=1,000 world already
  fails for every partial caller on this path. The Postgres ladder on
  the 1,000-user table: 1,000 holes 1.4 s, 2,000 holes 2.9 s, 5,000
  holes past 45 s, and the backend then ignored `statement_timeout`
  and `pg_terminate_backend` for over five minutes. asyncpg refuses
  32,768 arguments, so a unit of 16,384 holes can never be sent. At
  100,000 the fan is 200,000 binds and 400,000 terms, takes 3 to 5 s
  to build, and is rejected. This is the path the vector leg and
  Oracle take today.
- **The cache does not help.** One cached `Resolution` is 72 KB,
  702 KB, then 7.0 MB; with its read ranges, 42 MB at 100,000 users,
  so the 256-entry LRU (`rights.py:78`) would hold 10.9 GB. One grant
  write bumps the global revision (`rights.py:162`) and discards every
  entry; recompute is 18 ms, 136 ms, then 2.1 s per caller, so if
  every user reads once after one grant the bill is 18 s, 23 minutes,
  then 59 CPU-hours.
- **The verbs stop.** For the ordinary caller, `tree /` goes 0.2 s,
  21.2 s, then past the 60 s cap; `glob /shared/*/*.md` 60 ms, 4.1 s,
  then past the cap; `ls /home` 25 ms, 0.8 s, then past the cap. The
  system caller, with no predicate, answers the same three at 100,000
  users in 8.3, 2.8 and 1.4 s, so the engine is not the limit.

Recall was 1.0 with zero extra rows wherever the shipped path
finished, so the shipped design is correct up to the point where it
cannot run.

## 2. The row label, measured

From `row-label-grants-spike/results.md`. Same world, standalone
schema: `entries(path, owner_id, public_level)` with indexes `path`,
`(public_level, path)`, `owner_id`; a `postures` table; the caller's
explicit grants as ADR 072 pieces built by a linear merge; the
predicate `public_level >= :read OR path in pieces OR owner_id = :me`.

### 2.1 Compile is caller-sized

| N | caller | grants held | pieces | bind bytes | compile | shipped `resolve` on the same world |
|---|---|---|---|---|---|---|
| 1,000 | ordinary | 41 | 11 | 630 B | 23 µs | 3–4 ms |
| 10,000 | ordinary | 49 | 44 | 2.4 KB | 31 µs | 139–204 ms |
| 100,000 | ordinary | 36 | 36 | 2.0 KB | 22 µs | 1.9–2.1 s |
| 100,000 | heavy group | 244 | 232 | 12.8 KB | 146 µs | 9.9–10.3 s |
| 100,000 | two subjects | 76 | 13 + 152 owner | 4.9 KB | 77 µs | 0.9–1.2 s |

The ordinary caller's pieces follow its own grants and nothing else:
the count moves with the seeded group draw (36 to 44), not with N.
The heavy-group member holds `8 + S/5` grants by construction, so its
bind grows with the number of shared folders, which is a caller-sized
quantity. No posture row enters the compile. No hole is cut.

### 2.2 Reads follow the visible set

Ordinary caller, warm, `public_level` variant:

| N | visible rows | all visible ids | scoped read (one folder) | chunk count via derived table | top-10 via derived table | top-10 inline predicate |
|---|---|---|---|---|---|---|
| 1,000 | 2,034 | 1.8 / 3.6 ms | 1.3 / 1.9 | 1.1 / 6.7 | 1.5 / 7.9 | 1.2 / 3.1 |
| 10,000 | 20,124 | 28 / 78 ms | 7.7 / 5.6 | 14 / 99 | 18 / 60 | 12 / 2.4 |
| 100,000 | 201,024 | 311 / 757 ms | 2.5 / 2.5 | 57 / 504 | 65 / 765 | 1.3 / 2.0 |

(SQLite / Postgres.) Recall exact in every cell, every caller, both
engines, including the sibling traps, a nested `shared` folder inside
a private home, and a subtree moved across a boundary.

- "All visible ids" at 100,000 is the cost of fetching 201,024 ids;
  the system caller takes 1.9 to 2.3 s to fetch all 2.3 million.
  Nothing in the predicate scales with the user count.
- The scoped read is served by `(public_level, path)` in 2.5 ms. The
  `domain_id` variant has no index that combines "domain in list"
  with "path in range" and takes 15.7 ms, growing with the list.
- The inline-predicate top-10 lets both engines walk the score index
  and stop early: 1.3 and 2.0 ms at 100,000. SQLite does not take
  that plan for the anonymous caller (whose predicate is the single
  term `public_level >= 1`) and sorts 200,000 chunks instead, 43 ms.
  The vector-leg count gate ADR will have to choose the shape per
  dialect, as ADR 072 already expects.

### 2.3 Postgres needs one planner fix for the `UNION` shape

At 100,000 the range-join branch is estimated at 9.2 million rows
(the default inequality selectivity, one ninth of the table, times 36
ranges) against 7,020 actual. The `UNION`'s hash aggregate plans 128
partitions, spills 8 MB to disk and turns JIT on (68 of 253 ms). The
same misestimate hits ADR 072's shipped range join today. The inline
predicate estimates fine. Two known fixes, neither built: fence the
range branch (`OFFSET 0` or a `MATERIALIZED` CTE), or make the
branches disjoint and use `UNION ALL` so no aggregate is planned. The
`domain_id` variant does not suffer, because `= ANY(array)`
estimates well.

### 2.4 Writes: the relabel is bounded

| operation | SQLite | Postgres |
|---|---|---|
| posture change, 1,000-row subtree | 3 ms | 27 ms |
| posture change, 1,000,000-row subtree, one statement | 1.96 s | 16.8 s |
| the same in keyset chunks of 50,000 | 1.43 s (43 statements) | 16.0 s |
| root posture change across 1,102 deeper postures (3,308 pieces) | 70 ms (8 statements) | 305 ms |
| move 10,001 rows across a boundary, label in the same `UPDATE` | 34 ms | 87 ms |
| a grant at a new prefix | 0 (no row write) | 0 |
| label lookup for one new row | 0.24 ms | 1.3 ms |

Every label was checked against a Python labeller after every change.

- The relabel is bounded two ways: binds, because the ranges travel
  as ADR 072 pieces at most 500 per statement; rows, because an open
  range can be walked by keyset so no statement touches more than k
  rows. What chunking does not bound is the transaction. A
  million-row relabel in one transaction is what put the shared test
  container into crash recovery twice. The chunks need their own
  transactions, and the posture row needs a revision that gates the
  subtree while the labels catch up (§6).
- Postgres relabels at 10 to 16 µs per row, eight times SQLite: each
  updated tuple is a new version with five indexes to maintain, and
  an indexed `public_level` rules out HOT updates. The relabel must be
  written as `UPDATE … FROM unnest(…)`; the `id IN (SELECT …)` form
  plans a full-table semi-join on Postgres.
- Per-range keyset chunking explodes on many small ranges (4,413
  statements for the root). The rule to build is: count first, batch
  small ranges through the range join, keyset only the big ones.
- A grant never writes a row in the `public_level` variant. In the
  `domain_id` variant every new boundary relabels its subtree (758 ms
  per million rows). That, with §2.2, is why `domain_id` loses.

### 2.5 Invalidation

Callers invalidated by one write:

| write | global revision (today) | per-principal + per-group + posture revisions |
|---|---|---|
| grant to one user | N | 1 |
| grant to a group | N | the group's members (about 1,000 here) |
| posture change | N | 0 — the posture is on the rows |

Recompute per caller is 0.3 ms on SQLite and 0.3 ms on Postgres with
the two-branch fetch shape (§7 of the study). Granularity still
matters, by a factor of N for user grants; and the posture write,
which invalidated everyone under the shipped design, leaves the
compile entirely.

### 2.6 One semantic finding

A subtree moved into another user's private home stays visible to its
former owner through the owner floor. The Python truth, both
variants and the shipped single-subject owner arm all agree, because
`owner_id = me` is mount-wide in the spec's rules. It is a spec
question, not a prototype bug. §6.

## 3. The sorted-merge algebra, verified

From `sorted-merge-range-algebra/results.md`. Range sets as sorted
half-open spans with the `\x00` sentinel; prefix sets kept in *tree
order* (split on `/`) so a subtree is one contiguous run, which is
what makes `minimise`, `meet` and the owner-floor trim linear; the
everyone region by a stack walk.

- **Parity:** 2,000 worlds from the suite's generator plus 2,000 from
  a sibling generator, every subject set, both levels, every probe,
  every owner variant: 3,762,840 three-way `admits` checks (oracle =
  shipped = new), 0 disagreements. Pieces byte-identical to the
  shipped pieces in 39,814 of 40,050 cases; the other 236 are exactly
  the cases where the shipped pieces carry a NUL bound. The suite's
  own generator never produces a `p`/`p0` sibling pair, so the
  shipped 400-world test cannot see review finding 2.
- **Fuzz:** 100,000 worlds over segments that sort around `/` (`0`,
  `-`, `.`, `!`, space, `~`, `é`, `日本`), derived siblings, nested
  holes, hole equals grant, hole on root, many members, empty groups.
  Twelve invariants, 0 breaks. The shipped pieces carried a NUL bound
  in 6,295 cases. Three deliberate mutants are each caught.
- **Timing**, shipped vs new:

| shape | 1k | 10k | 100k |
|---|---|---|---|
| open root, H private homes | 98 ms / 3 ms | 16.3 s / 37 ms | ~1,600 s projected / 287 ms |
| H shared homes each with a private sub | 216 ms / 4 ms | 21.6 s / 47 ms | ~2,200 s / 619 ms |
| G grants to one group, 1 member | 3 / 2 ms | 31 / 20 ms | 366 / 282 ms |
| G grants, 2 members | 301 ms / 5 ms | 26.0 s / 57 ms | ~2,600 s / 719 ms |
| G grants, 5 members | 3.4 s / 16 ms | ~340 s / 171 ms | ~34,000 s / 1.9 s |

- **The sibling fix.** `/v1`'s subtree ends exactly where the point
  `/v10` begins (`0` is the byte after `/`), so the merge yields
  `[/v1/, /v10\x00)`, and the shipped `_split` only recognises a
  sentinel-ended span when it is a lone point. The rule: a span whose
  upper bound ends in the sentinel runs through the path before it,
  so it becomes the open range up to that path plus the exact point.
  Every emitted bound is `/`, `0`, `p`, `p/` or `p0` for an input
  prefix `p`, so none can end in NUL or a control byte. Numbered
  homes (`/home/u1`, `/home/u10`) hit this bug on the exact layout we
  are designing for: 99 pairs per 1,000 homes.
- **Subtleties the ADR or spec should state:** an empty subject set
  resolves to the whole mount; `whole` and `covers_subtree` are
  syntactic today and semantic in range form (both sound; the
  semantic one takes the fast path more often); duplicate
  `(principal, prefix)` rows are undefined input; the owner floor is
  not trimmed by the everyone region, and could be; the sentinel can
  be an upper bound after a merge, so the two-piece rule and the
  sentinel discipline belong in one sentence.

The study's README lists, function by function, what would change in
`grants.py`: keep the public names, replace each pairwise loop with a
tree-ordered or byte-ordered merge, give `Rights` a range set per arm
set instead of `Arm(prefix, holes)`, and add the upper-bound rule to
`_split`.

## 4. What the three results mean together

The shipped design has one world-sized input, the holes, and three
quadratic operations on caller-sized inputs. The two studies fix
different halves, and neither is enough alone.

| | holes in the compile | meet across members | bind size per query | posture write cost | grant write cost |
|---|---|---|---|---|---|
| shipped | 100,000 at N=100,000 | O(G²) | 9.2 MB | one row | one row, invalidates everyone |
| algebra only | still 100,000, now linear (287 ms) | O(G log G) | still 9.2 MB | one row | one row |
| label only | 0 | still O(G²) | 2 KB | subtree relabel | one row |
| both | 0 | O(G log G) | 2 KB | subtree relabel | one row, invalidates one caller |

The shape that follows, stated as the design the ADR would have to
decide:

- The entry row carries `public_level`, written when the row is
  written (inherit from the nearest posture above), rewritten for the
  subtree when a posture changes, and rewritten on a move.
- A caller's compiled rights hold only the caller's own prefixes:
  explicit grants as ADR 072 pieces, the meet across a subject set as
  a sorted-merge intersection, the owner floor as `owner_id = me`.
  The word "hole" leaves the compiler.
- The visibility predicate is three index seeks:
  `public_level >= :read`, the range join on the caller's pieces, and
  `owner_id = :me`, as disjoint `UNION ALL` branches or one inline
  predicate, chosen per dialect.
- Revisions are per principal, per group and per posture, not one
  global counter.
- The relabel is chunked by the count-then-batch rule, each chunk its
  own transaction, with the posture row's revision gating reads of
  the subtree until the labels are consistent.

## 5. Principles the numbers confirm

The prior-art memo distilled seven principles (§10 there). Each now
has a measured witness.

| principle | witness |
|---|---|
| Compile only the caller's own principals | §2.1: 22 µs and 2 KB at every N, against 1.8 s and 9.2 MB |
| A deny-by-subtraction belongs on the row | §1 vs §2.2: the holes are the only world-sized input, and a column compare removes them |
| A row label is a small position fact, never a principal list | §2.4: `public_level` costs no write on a grant; `domain_id` relabels per boundary |
| Propagation is a chunked range update with a declared bound | §2.4: 500 pieces or k rows per statement; the transaction is the remaining bound |
| LIST is a seek on a row fact or a sorted range | §2.2: scoped read 2.5 ms at 100,000 users |
| Sorted sets merge; they are never cross-multiplied | §3: 26 s to 57 ms with identical answers |
| Invalidate per caller | §2.5: N recomputes per grant write becomes 1 |

## 6. Open choices

- [NEEDS CLARIFICATION: **level or handle on the row?** The spike
  measured a three-valued `public_level` and a `domain_id` handle,
  and the level won on every axis measured (constant bind, write-free
  grants, scoped reads through `(public_level, path)`). The prior art
  favours a handle for richer labels. Recommendation: the level, and
  drop `domain_id`. Decide.]
- [NEEDS CLARIFICATION: **owner-floor scope on a move.** A subtree
  moved into another user's private home stays visible to the mover
  through the mount-wide owner floor (§2.6). The shipped code agrees.
  Either state it, or bound the floor by the row's current
  `public_level` (a row in a private area is owner-visible only if
  the owner is still granted there), which the range form can express
  as `owner_id = me AND public_level >= read`.]
- [NEEDS CLARIFICATION: **what label does a trashed row carry?**
  Review finding 1 (critical): a deleted private row becomes
  world-readable because every verb judges it by its trash path. With
  a row label the fix is natural — the trash move keeps the row's
  label instead of inheriting the trash bucket's — but that is a
  decision about what "deleted" means, not a measurement.]
- [NEEDS CLARIFICATION: **synchronous relabel, or a gated stale
  window?** A million-row relabel is 2 s on SQLite and 17 s on
  Postgres; a ten-million-row one is minutes. Either the posture verb
  owns the whole relabel (simple, slow, and a long transaction
  crashed the test container), or it writes the posture row and a
  relabel task, with the posture row's revision gating reads of the
  subtree until the labels catch up (fast verb, a stale window to
  design). The brief's "never design toward a cap" rule points at the
  second.]
- [NEEDS CLARIFICATION: **the Postgres statement shape.** `UNION` of
  seeks with a fence, disjoint `UNION ALL`, or the inline predicate,
  per dialect (§2.3). The vector-leg count gate needs the same
  decision.]

## 7. What is not measured yet

- SQL Server, MariaDB and Oracle: the `public_level` spelling, the
  relabel `UPDATE … FROM` form, and whether their planners take the
  three-seek shape. The ADR 072 study showed each engine has its own
  planner trap; this design needs the same five-engine pass before
  it is built.
- A moved subtree that contains its own posture boundaries.
- `(public_level, path)` under concurrent relabel and read.
- The relabel task design: the stale window, the per-posture
  revision, and recovery after a crash mid-relabel.
- A 64-subject authority with deep group closures at scale.
- The Postgres 100,000-user baseline, lost to the shared server; its
  SQLite twin and its 10,000 run are enough to show the shape.

## What this means for vfs

The shipped grants design is correct and it is world-sized. At 1,000
users it is slow; at 10,000 it is unusable; at 100,000 it cannot run.
The cause is one representation choice: every other user's private
home is a hole in every caller's rights.

Two changes, both measured on SQLite and Postgres with exact recall,
remove the world from the caller's rights. The everyone level moves
onto the row as a three-valued column, written with the posture row
and the move, rebuilt by a chunked range update. The range algebra
becomes a sorted merge, which also fixes the sibling NUL bound that
numbered homes trigger today.

After both, an ordinary caller's rights are two kilobytes, a scoped
read is a few milliseconds at 100,000 users, a posture change costs
its subtree and nothing else, and a grant invalidates one caller. The
five open choices in §6 are what an ADR must settle; §7 is what the
other three engines must confirm before it is built.
