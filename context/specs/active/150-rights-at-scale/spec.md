# 150 — Rights at scale: the everyone level on the row, caller-sized ranges, and the linear range algebra

- **Status:** **built 2026-10-03, awaiting Clay's review; `scripts/ci.sh`
  not run.** Drafted 2026-10-02 with Claude's recommendations; Clay
  took all four recommendations the same day ("I'll take your
  recommendation based on the research for the four forks. please get
  going on this work"), so every former `[NEEDS CLARIFICATION]` below
  reads as decided. Born from ADR 073, accepted the same day. Every
  slice landed green on the next day, each leaving the tree passing:
  A made every range operation a sorted merge and `Rights` a set of
  pieces; D measured the three-seek shape and the relabel on all five
  engines; B put the everyone level on the row and made every caller's
  rights caller-sized; C made the posture relabel a bounded, resumable,
  in-flight-compiled walk and the admin verbs lock before they decide;
  F judged the trash by its origin and folded the restore refusal; E
  keyed the rights cache on per-principal stamps and the relabel marks,
  bounded it in bytes, and ran the 100k gate (SQLite N=100,000 and
  Postgres N=10,000; all criteria met but two: the miss-path compile is
  2.98 ms against 1 ms, and `ls /home` is 2.5× the system actor, the
  road probe over 100,000 hidden homes). Three of its slices are the bug
  fixes the 058 review ordered.
- **Date:** 2026-10-02
- **Owner:** Clay Gendron
- **Kind:** feature and refactor (the grants compile model, one schema
  column, the posture relabel, per-principal revisions, the grant
  verbs' lock order, the trash label)
- **Depends on:** 058 as built (the rows, verbs, gates, tests and the
  oracle it reshapes), 070 (`Authority`), ADR 072 (the range join it
  keeps as the explicit-grant leg), the dialect budgets
- **Decisions it implements:** ADR 073 (all eight rules), ADR 072 rule
  1 as completed by 073 rule 5, ADR 065 (unchanged: hidden rows are
  absent, statistics over the visible set), ADR 064 rule 2 (the
  mount-wide revision still stamps version rows)
- **Supersedes in 058:** §0 "Compilation", §3 step 4 (everyone arms
  with holes), §4 (the unit shape for everyone arms), and the
  `grant_revision` memo key in §1. Everything else in 058 stands: the
  rows, the ladder, the floor, the verbs, reads filter, writes check,
  statistics, the gates.
- **Research it stands on:**
  `../../../research/2026-10-02-grants-at-100k-users-measured.md` (the
  numbers) and
  `../../../research/2026-10-02-row-labelled-acls-and-the-list-problem-prior-art.md`
  (the principles); studies
  `../../../research/studies/2026-10-02-grants-at-100k-users-baseline/`,
  `../../../research/studies/2026-10-02-row-label-grants-spike/`,
  `../../../research/studies/2026-10-02-sorted-merge-range-algebra/`.
- **Review it answers:** the 2026-10-01 code review of commits
  `3e5e9cf^..4759bc6`: findings 2 (the NUL bound), 4 (one clause per
  arm with every hole), 5 (grant verbs decide before they lock), 6
  (`pieces()` quadratic), 7 (`meet` quadratic), and 1 (a deleted
  private row becomes world-readable), plus the two the baseline
  study added (`admits` scans the holes per row; 42 MB per cached
  caller).

## Intent

**Nothing a caller may see changes. What changes is whose grants are
in the caller's hands.** Today every caller carries every other
user's private home as a hole, so the cost of one user's read grows
with the number of users. After this spec a caller carries only its
own prefixes, the everyone level is a column on the row, and every
operation on ranges is one pass over sorted input. The target this
spec is sized against: 100,000 or more users, one private home each,
dozens of shared folders each, on every engine vfs serves.

In one line: the everyone level moves onto the row; the caller's
rights become its own ranges; the algebra becomes a merge; a posture
change pays its subtree and nothing else; a grant invalidates one
caller.

## Decided semantics

### 0. Terms

- **Everyone level**: the level of the deepest covering `*` row at a
  path (058 §0). Unchanged in meaning; changed in where it lives.
- **Piece**: ADR 072's unit, an exact path or an open range
  `lo < path < hi`.
- **Caller-sized**: grows with the caller's own grants and groups.
  **World-sized**: grows with the number of other principals.
- **Relabel**: the `UPDATE` that rewrites `everyone_level` beneath a
  path after a `*` row changes.
- **In flight**: a `*` row whose relabel has started and not settled.

### 1. The column

- **`entries.everyone_level`**, a small integer, `NOT NULL`:
  `0 = none`, `1 = read`, `2 = read_write`, the same ladder 058 §2
  names. Its value at a row is the everyone level at the row's path.
- **Written with the row.** Every minting site (`write`, `mkdir`,
  `copy`, `restore`, the edge and derived-row writers) computes the
  label from the `*` rows covering the new path: one lookup of the
  ancestor chain against the posture rows, the same ancestors the
  write gate already reads. A batch of 10,000 rows computes its labels
  from one chunked read of the distinct ancestor prefixes.
- **Rewritten on a move.** `move` rewrites `path` and
  `everyone_level` in the same statement, from the destination's `*`
  rows. A moved subtree that contains its own `*` rows keeps those
  rows' effect beneath them: the relabel is "destination level, minus
  the moved subtree's own boundaries", computed with the same pieces
  a posture relabel uses (§4).
- **Rewritten on a posture change** (§4).
- **Derived, never authoritative.** The `*` rows stay the truth. A
  maintenance verb rebuilds every label from them (the migration uses
  it; a crash mid-relabel can fall back to it). Any read that finds a
  label disagreeing with the `*` rows is a bug, and the random-world
  parity test asserts they agree after every write and every posture
  change.
- **Index `(everyone_level, path)`.** Serves the scoped read ("rows
  under `/p` everyone may see") as one seek. The single-column index
  is not built; the composite's leading column covers it. `path`
  (unique) and `owner_id` remain.
- **Schema format 15.** The migration adds the column with a default
  of `read_write` (the default open posture), then runs the rebuild
  once from the `*` rows, in chunks (§4's rule), before the format
  stamp is written.

### 2. The resolver: caller-sized

For an `Authority` and a verb's required level, replacing 058 §3:

1. Walk each subject's group closure per subject (ADR 071 rule 3,
   unchanged). Read the rows of every subject and every closure group
   in one chunked `IN`. **Do not read the `*` rows.** Memoised per
   `(subjects, revision)` with §6's revision.
2. Per subject, the covering set at the required level, kept in tree
   order (segments split on `/`) so that a subtree is one contiguous
   run; `minimise` is one pass.
3. For a set, the meet as a sorted-merge intersection of the members'
   covering sets. One pass per member.
4. Emit `Rights(level, pieces, owner_pieces, whole)`: the meet's
   prefixes as sorted disjoint pieces (points plus open ranges), and
   per member the owner floor as that member's id plus the pieces of
   the other members' meet, trimmed of what `pieces` covers. `whole`
   is set when the pieces cover the root. There is no `Arm`, no
   `holes`, no everyone arm.
5. `Rights.admits(path, owner_id, everyone_level)` is the Python
   authority every row passes: `everyone_level >= level`, or a bisect
   of the sorted pieces finds a covering piece, or `owner_id` is a
   member whose owner pieces cover the path. O(log n) per row.

`MAX_SUBJECTS` and `MAX_GROUP_DEPTH` are unchanged.

### 3. The algebra: one pass, every operation

- Range sets are sorted tuples of half-open spans over path strings
  with the `\x00` sentinel as the internal "just past" marker. `union`,
  `intersect`, `subtract`, `normalise`, `contains` are each one pass
  over sorted input. Prefix sets are kept in tree order; `minimise`,
  `meet`, the owner-floor trim and `covers_subtree` are each one pass.
- **The split into pieces, both edges.** A span `[lo, hi)`:
  - `hi == lo + "\x00"` is the exact point `lo`.
  - otherwise, `lo` ending in `"\x00"` means the open range starts just
    past the path before it, and that path is already its own point.
  - **`hi` ending in `"\x00"` means the span runs through the path
    before it**: emit the open range up to `hi[:-1]` and the exact
    point `hi[:-1]`. This is the sibling fix (`/v1` beside `/v10`).
  Every emitted bound is `/`, `0`, `p`, `p/` or `p0` for an input
  prefix `p`. The well-formedness test asserts it, and the sentinel
  never reaches SQL (ADR 072 rule 1).
- **Stated edge cases** (from the algebra study): an empty subject
  set resolves to the whole mount, and the resolver refuses it
  instead — `Authority` already forbids it, so this is a narrowing
  assert, never a validation. `whole` and `covers_subtree` are
  semantic (the pieces cover the root; the pieces cover the subtree),
  which takes the fast path more often than today's syntactic test
  and is equally sound. Duplicate `(principal_id, path_prefix)` rows
  cannot exist (unique index), so the resolver takes no position.
- **Fuzz is part of the suite.** The sibling generator (`p` beside
  `p0`, `p-x`, `p/x`, segments sorting around `/`, non-ASCII) joins
  the random-world generator, so the 400-world parity test covers the
  shapes the review found missing.

### 4. The posture relabel

`posture(path, level, *, authority)`, replacing nothing in 058 §0's
verb contract and adding its write-side cost:

1. Take the admin lock (`bump_revision`), then resolve the caller's
   rights, then gate (§7).
2. Write the `*` row and mark it **in flight** (a `relabel_pending`
   column on the grants row, or a row in a small `relabels` table —
   whichever the schema slice finds cleaner; the marker must survive
   a crash).
3. Compute the relabel's pieces: the subtree under *path*, minus the
   subtrees of every deeper `*` row. This is the one place the hole
   algebra still runs, local to one write, linear (§3), and sized by
   the deeper `*` rows under *path*, not by the mount.
4. Relabel in chunks. **Count first, then batch**: pieces are grouped
   so that one statement carries at most `in_list_budget` pieces and
   touches at most `RELABEL_ROWS` rows (a dialect fact beside
   `in_list_budget`, default 50,000); a single open range larger than
   that is walked by keyset. Each chunk is its own transaction. On
   Postgres the statement is `UPDATE … FROM unnest(…)` so each range
   is an index seek; on other dialects the same join through their
   `range_source`.
5. Clear the in-flight marker in the last chunk's transaction and
   bump the posture's revision (§6).

**The relabel statement per dialect, measured in slice D** (every
range an index seek; `id IN (SELECT …)` never, it stalled past 15
minutes on MariaDB and SQL Server): SQLite `UPDATE … FROM
json_each(…)` (root relabel across 1,102 postures: 35 ms); Postgres
`UPDATE … FROM unnest(…)` (290 ms); MariaDB `UPDATE e STRAIGHT_JOIN
JSON_TABLE(…) … SET` (158 ms); SQL Server `UPDATE e … FROM OPENJSON(…)
r INNER LOOP JOIN e` (956 ms); Oracle the literal `OR` of ranges with
`/*+ USE_CONCAT */`, a concatenation of index range scans (394 ms;
`MERGE` merge-joins a full scan at 500 ranges). Per-row rates: 1.3 µs
SQLite, 4.5 MariaDB, 9 Postgres, 15–25 Oracle, 17–38 SQL Server.
`RELABEL_ROWS = 50,000` with one transaction per statement was safe
on every engine.

**While in flight**, the resolver compiles that one `*` row the old
way: at the caller's level it is an arm (if it widens) or a hole on
the caller's pieces (if it narrows), so every reader sees the new
posture from step 2 onward, and the rows' stale labels do not matter.
The in-flight set is read with the caller's rows (one small table or
one filtered read of the `*` rows) and is normally empty. A relabel
that dies leaves its marker set, the compile covers it, and the next
`posture` call on any path, or the maintenance verb, resumes it.

- **Decided (Clay, 2026-10-02): the posture verb waits for the
  relabel.** The fork was: wait, or return with it in flight. Measured: 2 s per million rows on
  SQLite, 17 s on Postgres; a ten-million-row subtree is minutes.
  **Recommendation: the verb waits.** The chunks are separate
  transactions, so the wait never holds a long lock; the in-flight
  compile makes correctness independent of the wait; and a verb that
  returns before its work is done needs a task runner vfs does not
  have. A background relabel can be added later without changing any
  contract, because the in-flight rule already covers it. The verb
  reports rows relabelled and chunks run in its result payload.

### 5. The predicate: three seeks

`Visibility.entries()` returns the visible entry ids as the union of
three branches, each an index seek:

1. `everyone_level >= :level` — the everyone leg, through
   `(everyone_level, path)`, with the verb's scope prefix as a range
   when it has one.
2. the range join on the caller's pieces (ADR 072, unchanged) —
   `AND everyone_level < :level`, so branches 1 and 2 are disjoint.
3. `owner_id = :sub` per member, joined to that member's owner pieces
   — `AND everyone_level < :level`.

Branches 1 and 2 never overlap; 2 and 3 may, and are merged by
`UNION`. Statements that read chunk-side tables join the result as a
derived table (ADR 072 rule 4, unchanged). `whole` skips the
predicate (unchanged). The in-flight `*` rows (§4) are added to
branch 2 as pieces or holes before it is sent.

- **The clause fan survives only where it must**: dialects without a
  `range_source` (Oracle, generic) and the vector leg until its count
  gate ADR. It now fans the caller's own pieces, which are dozens, so
  it is bounded by the caller. `_units` loses its holes: one unit is
  one piece. ADR 071 rule 1's budget still applies.
- **`Visibility.admits(mapping)`** reads `everyone_level` from the row
  mapping; every read builder's row select includes the column.
- **Decided (Clay, 2026-10-02): a per-dialect fence.** The fork was
  the statement shape on Postgres. The
  three-branch `UNION` is misestimated 1,300× on the range branch
  (default inequality selectivity × ranges), which plans a
  disk-spilling hash aggregate and turns JIT on; the measured cost at
  100,000 users was 253 ms for an unscoped fetch where 2 ms was
  possible. **Recommendation: a per-dialect fence**, as ADR 072
  already chooses spellings per dialect: on Postgres, branch 2 is
  wrapped as a materialised subquery (`OFFSET 0`) so the planner
  stops multiplying, and `SET LOCAL jit = off` is issued with the
  statement; the `UNION ALL` of branches 1 and 2 (disjoint by rule)
  with a `UNION` only onto branch 3. Slice D measures this on all
  five engines and records the chosen shape per dialect in
  `DialectProfile` only if the spelling needs a fact SQLAlchemy does
  not model.
- **Measured, slice D (2026-10-02,
  `../../../research/studies/2026-10-02-three-seek-shape-five-engines/`):
  the fence does not work; the disjoint shape does.** With `OFFSET 0`
  and JIT off, Postgres still estimated the range branch at 8.4 M
  rows (actual 20) and spilled the aggregate (268 → 163 ms, the JIT
  share only). Shape (e), **branches made disjoint and joined by
  `UNION ALL`** — branch 2 carries `everyone_level < :r`, branch 3
  carries `everyone_level < :r AND NOT EXISTS (the caller's ranges
  over this row)` — plans no aggregate at all: 85 ms at 100,000
  users. Keep `SET LOCAL jit = off`. Recall exact on every engine,
  every shape, every N; the sibling traps never leaked. The extra
  `everyone_level` term misleads four of the five planners, each in
  its own way, so **the range branch's join keyword is a
  `DialectProfile` fact** (SQLAlchemy does not model it): SQLite
  `json_each(…) CROSS JOIN entries`; MariaDB `STRAIGHT_JOIN` with
  `FORCE INDEX (path)`; SQL Server `OPENJSON(…) INNER LOOP JOIN
  entries`; Oracle `JSON_TABLE` with `/*+ CARDINALITY(src n) */` per
  range branch, `INDEX(e (everyone_level path))` on branch 1, and
  `NO_MERGE LEADING USE_NL INDEX(entry_id)` on derived statements, so
  **Oracle gains a `range_source` in slice B**; Postgres a plain
  `JOIN`. Shape (e) is never worse than (b) on any engine, so it is
  the one shape everywhere. On SQL Server the literal form still wins
  for small rights (44 ms entries, 6.7 ms top-10), as ADR 072 rule 5
  allows.

### 6. Revisions

- **`principal_revisions(principal_id, revision)`**: one row per
  principal or group that has ever been granted or made a member,
  bumped by every grants or memberships write that names it. A
  caller's memo key is `(subjects, max over its subjects' and their
  closure groups' revisions)`, read in the same statement as the
  closures.
- **Posture revision**: the `*` rows carry their own `revision`
  (already a column) and bump on write; it keys nothing in the compile
  (the posture is on the rows) and gates only the in-flight set.
- **`meta.grant_revision` stays**: it is the admin lock and the stamp
  on version rows (ADR 064 rule 2). It no longer keys the rights
  cache.
- **The cache is bounded in bytes, not entries.** 256 entries of
  caller-sized `Rights` is a few megabytes; the limit becomes a byte
  budget with the entry count as a ceiling, and the measured size of
  one `Rights` is asserted at the 100k gate (§Acceptance).

### 7. The grant verbs lock before they decide

`grant_rows`, `revoke_rows`, `set_posture`, `add_member_rows` and
`remove_member_rows`: `bump_revision` first (the `UPDATE` that
serialises admin writes), then the caller's resolution inside the
same transaction, then the gate, then the write. `add_member_rows`
already does this; the others move to it. The order is the docstring's
promise ("the revision bumps first") made true. This is the review's
finding 5; the race was executed on Oracle and SQL Server.

### 8. The trash keeps its label

Today a deleted row is reparented under `/.vfs/trash/<bucket>/` and
judged by that path, which the root posture covers; a private row
becomes world-readable on delete (review finding 1, critical). With
the label:

- **The trash move does not relabel.** A row keeps the
  `everyone_level` it had at its original path, so a row hidden from
  everyone stays hidden from everyone in the trash.
- **Explicit grants reach trash rows through the origin.** The trash
  row already carries `original_parent_id` and `original_name`; the
  visibility predicate for rows under `TRASH_ROOT` joins the caller's
  pieces to the origin path (the parent's path plus the name) instead
  of the trash path. Concretely: branch 2 of §5 has a second form for
  trash rows, used by `tree`/`ls`/`glob` under `TRASH_ROOT`, by
  `restore`, and by `sweep`.
- **The owner floor is unchanged**: the owner sees their trashed rows.
- **Refusals echo only the caller's input** (ADR 065 rule 2):
  `restore`'s "No trashed entry for" and "Not found: <trash path>"
  payloads (review finding 14) are folded into the one `not_found`
  that names the path the caller sent.
- **Decided (Clay, 2026-10-02): a trashed row is judged by its
  origin.** The fork was whether that is the rule Clay wants. The alternative is a posture of `none` on the
  trash bucket, which hides every trashed row from everyone but
  owners and whole-mount callers, and makes a system-written row
  (no owner) in a private home unrestorable by that home's holder.
  **Recommendation: judge by origin.** It is the only rule under
  which "delete then restore" is invisible to permissions, which is
  what a user expects of a trash.

### 9. The owner floor on a move

A subtree moved into another user's private home stays visible to
its former owner through the mount-wide owner floor (the spike's §4;
the shipped code agrees). The mover had `read_write` on the
destination at the time, or the move was refused.

- **Decided (Clay, 2026-10-02): the owner floor stays mount-wide.**
  The fork was mount-wide (today) or bounded by the row's current area. **Recommendation: keep it mount-wide**, as
  058 §2 and ADR 064 rule 4 state and the docs promise ("so that a
  person can never be locked out"). The bounded form (`owner_id = me
  AND everyone_level >= read`) is one term away if Clay prefers it,
  and the review's finding 33 (owner restamped on edit, so a revoked
  writer keeps rows it rewrote) is the same policy question seen from
  the write side; both should be decided together, and this spec
  does not change the restamp.

### 10. What does not change

Hidden rows are absent (ADR 065). Statistics are over the visible set
(058 §7; the visible-corpus count joins the three-seek derived table).
Writes check points (058 §6); the write gate reads `everyone_level`
on the target rows and the caller's pieces, never a hole. Road
directories (ADR 070). Groups resolve per member (ADR 071 rule 3).
The six grant verbs' contracts (058 §8). The pointwise oracle stays
the authority, and gains `everyone_level` as an input it computes
from the `*` rows itself.

## Non-goals

- The vector leg's count gate and path-ordered chunk numbers (their
  own ADRs, as ADR 072 ruled).
- A background relabel runner (§4's marker covers it; not built).
- Changing the owner restamp on edit (review finding 33; decided with
  §9).
- Native row security (ADR 067).
- The other review findings (tree `max_depth` road, `mounts()`
  posture, doc drift, the test pins) — a separate fix list after the
  058 review; slice F below takes the test pins that this spec's
  changes touch.

## Acceptance criteria

- **Parity.** The random-world test (400 worlds plus the sibling
  generator) asserts the new `Rights.admits` equals the pointwise
  oracle and, for one landing only, equals the shipped `admits` on
  every probe; the pieces are well-formed (every bound ends in `/`,
  `0` or a path byte; no sentinel); the label on every row equals the
  oracle's everyone level after every write, move, copy, restore and
  posture change in the world.
- **The 100k gate** (SQLite and Postgres, the baseline study's world
  at N=100,000, run by `bench.py` in the baseline study against the
  shipped code): ordinary caller compile under 1 ms and under 20 KB;
  `tree /`, `ls /home` and `glob /shared/*/*.md` within 1.5× of the
  system actor's time for the same call (restated 2026-10-03 after
  slice B: the predicate is no longer the cost — `tree /` went from
  past 60 s to 4.5 s for 402,000 visible rows, against 5.8 s for the
  system actor's 501,000 with no predicate at all; what remains is
  row-object construction, which is the observation layer's budget,
  not this spec's); `admits` under 10 µs per row; one
  cached `Rights` under 100 KB; a posture change on a 1,000-row
  subtree under 100 ms and on a 1,000,000-row subtree under 30 s with
  no statement touching more than `RELABEL_ROWS` rows; a grant to one
  user invalidates one cached caller.
- **Five engines.** Slice D's study runs the three-seek shape and the
  relabel on SQL Server, MariaDB and Oracle before slice B lands;
  recall exact on each; the chosen shape per dialect recorded in the
  study and in `ranges.py`'s docstring. The GrantsContract mixin
  green on all five.
- **The race.** The review's `race.py` shape (a revoke committed
  between gate and write) refuses on Oracle and SQL Server after
  slice C.
- **The trash.** A row deleted from a private home is `not_found` to
  every caller but its owner and whole-mount callers, on every verb
  including `grep`, `glean`, `tree /.vfs/trash` and `sweep`; its
  holder restores it; the refusal payload names only the caller's
  path.
- **No clause holds more than `membership_budget // 2` binds** on any
  path, asserted by the starved-budget test, now including the vector
  leg's fan over a caller with 500 grants.
- **Coverage, lint, types** at the house bar; `scripts/ci.sh 3.13`
  before the landing commit unless Clay says otherwise.

## Slices

| Slice | Content | Lands green? |
|---|---|---|
| A | The algebra: sorted range sets and tree-ordered prefix sets in `grants.py`; `Rights` as pieces; `admits` by bisect; the both-edges split (the sibling fix); the sibling generator in the tests; parity against the oracle and the shipped `admits`. Behaviour-identical; the holes still exist in this slice. Fixes review findings 2, 6, 7. | yes |
| B | The column: `everyone_level`, the index, format 15, the labeller at every minting site and on move/copy/restore, the rebuild verb and the migration; the resolver stops reading `*` rows; `Visibility.entries()` as three seeks; `_units` without holes; `Visibility.admits` reads the label; the oracle computes the label. Fixes findings 4 and the two baseline walls. Gated on slice D's five-engine study. | yes |
| C | The posture relabel: in-flight marker, count-then-batch chunking, `RELABEL_ROWS`, the `UPDATE … FROM` form, the in-flight compile, resume; lock-before-decide in all five admin verbs (finding 5). | yes |
| D | The five-engine study (SQL Server, MariaDB, Oracle join the SQLite and Postgres spikes): the three-seek shape, the Postgres fence, the relabel statement per dialect; the per-dialect choice recorded. A study, not code; precedes B. | n/a |
| E | Revisions: `principal_revisions`, the memo key, the byte-bounded cache; the 100k gate run and recorded. | yes |
| F | The trash: label kept, origin-judged branch, `restore`/`sweep` through it, the folded refusal payload (findings 1 and 14); the test pins the review ordered that touch these paths (copy and move gates, overlay and grep view checks, posture and `add_member` bumps). | yes |

Order: A, D, B, C, E, F. A and D can run in parallel.

## Open questions

- None. The four forks (§4 wait or return, §5 the Postgres shape, §8
  the trash by origin, §9 the floor's scope) were decided 2026-10-02
  as recommended. The edit restamp (review finding 33) stays with the
  mount-wide floor and is not changed here.

## Implementation progress — slice A

**2026-10-02.** The algebra landed in `src/vfs/storage/grants.py` and its
consumer `src/vfs/storage/backends/database/rights.py`. Behaviour is
identical to the shipped code on every pointwise answer; the holes still
enter the compile (slice B removes them).

Function by function, `grants.py`:

- `tree_key` (new): the tree-order sort key (segments split on `/`), so
  a subtree is one contiguous run. `minimise` sorts by it and keeps a
  prefix when the last kept one does not cover it — one pass. `meet` is
  a two-pointer merge over two minimised, tree-ordered sets; `meet_all`
  folds from the root identity.
- Range sets (new, public): `Span`, `RangeSet`, `FULL`, `cover`,
  `cover_all`, `normalise`, `union`, `subtract` (two-pointer), `contains`
  (one bisect). The `\x00` sentinel is module-private and never reaches a
  bound.
- `pieces(spans)` replaces `pieces(arms)` and carries the both-edges
  split: an upper bound ending in the sentinel becomes the open range up
  to `hi[:-1]` plus the point `hi[:-1]` (the `/v1` + `/v10` fix). Every
  bound is `/`, `0`, `p`, `p/` or `p0`.
- `Arm(prefix, holes)` is gone. `Rights(level, spans, owner_arms, roots)`:
  `spans` is the covered range set; `owner_arms` keep
  `OwnerArm(owner, prefixes)` (the trimmed meet of the other members) and
  their cover is memoised per owner; `roots` are the covered prefixes
  whose parent is not covered (every hidden directory with a visible row
  beneath it is a proper ancestor of one), computed with one bisect per
  candidate and consumed by the road. `whole` is now a property,
  semantic (`spans == FULL`); `covers` is a bisect; `covers_subtree` is
  two bisects (the point span and the subtree span); `admits` is at most
  two bisects.
- `_everyone_region` replaces `_everyone_arms` + `_already`: posture rows
  in tree order, nearest posture parent by a stack, each qualifying row
  owns its cover minus its posture children's covers, union of the parts.
- `_meet_all_but_each` (prefix and suffix meets, three meets per member)
  and `_uncovered` (two-pointer trim) replace the per-member re-meet and
  the G×G trim in `resolve`.
- `resolve` refuses an empty subject set with a narrowing assert
  (`Authority` already forbids it); duplicate `(principal, prefix)` rows
  are declared keyed input.

`rights.py`: `cover_clause`, its LIKE escaping and `_cover_binds` are
removed. `_units(entry, rights, bind_cap)` builds one unit per piece
(`path = :p`, one bind; `lo < path < hi`, two binds — bound through the
path column's type, so the mysql family compares bytes and SQL Server
keeps the UTF-8 collation); owner units are `owner_id = :o AND (pieces)`
sliced to the clause's bind cap, at most 50 pieces. `_owned_beneath`
takes the owner's pieces; `Visibility.road` iterates `ranges().owners`;
`_existing_roots` reads `Rights.roots`.

Tests: `tests/support/grant_worlds.py` gained `Layout`, the `SIBLINGS`
layout (`p` beside `p0`, `p-x`, `p/x`; segments ending in `0`, `-`, `.`,
`!`, space, `~`, `é`; `/v1` beside `/v10`) and `random_world(rng, layout)`;
`tests/storage/test_grants.py` runs the 400-world parity over both
layouts and every owner variant, asserts every bound is in
`{/, 0, p, p/, p0}` with no sentinel, pins the roots invariant, and unit
tests each operation on the shapes the study's mutants break (the
sentinel-free split, the subtract bounds, both directions of the meet);
`tests/storage/database/test_rights.py` replays the sibling layout
through the clause fan and the range join and pins per-piece units and
bind counts; `tests/support/grants_contract.py` runs the touching
sibling pair on every engine.

Numbers (M-series laptop, pure Python, through the shipped `resolve` +
`ranges()`): 10,000 holes 23 ms (was 16.3 s); two members over 10,000
grants 59 ms (was 26.0 s); 100,000 holes 339 ms; 10,000 shared homes
each with a private sub 62 ms. Three-way parity (oracle, the backed-up
shipped module, the new module) over 2,000 worlds: 2,650,000 `admits`
checks, 0 disagreements; pieces byte-identical in all 19,952 cases where
the shipped pieces were well-formed; the 48 shipped NUL-bound cases now
clean. The study's `parity.py` re-run against the new module:
3,762,840 checks, 0 failures, pieces identical in all 40,050 cases,
0 NUL bounds, and `whole`/`covers_subtree` agree with the study's
semantic form in every case. The study's `fuzz.py` (adapted only for the
empty-subject refusal, which is now I12's expected answer): 100,000
cases, 1,389,026 probes, twelve invariants, 0 breaks, 0 NUL bounds.

Gates: `ruff check`, `ruff format --check` and `ty` at zero; the suite
3,609 passed with `grants.py` and `rights.py` at 100% coverage; `pytest
docs` 23 passed; the full conformance class (the storage contract plus
every `GrantsContract` test, including the touching sibling pair) 276
passed on each of Postgres, MariaDB, SQL Server and Oracle.

Deferred to later slices: the holes themselves and the `*` rows in the
compile (B); the owner floor is still not trimmed by the everyone region
(kept for parity; a free improvement once B lands); `Rights.admits` keeps
its `(path, owner_id)` signature until B adds `everyone_level`.

## Implementation progress — slice B

**2026-10-03.** The everyone level is a column on the row, every caller's
rights are caller-sized, and visibility is the three-seek statement on
every tuned dialect — Oracle included. Landed as two green checkpoints:
B1 (the column, written at every mint and rewritten on move, copy,
restore and posture change; visibility unchanged) and B2 (the resolver
stops reading `*` rows; `Visibility.entries()` is shape (e)).

File by file:

- `models/rows.py`: `entries.everyone_level`, `SmallInteger NOT NULL`
  with **no default** — a mint site that forgets it fails loudly, like
  `edges.provenance`; index `ix_<t>_everyone_path (everyone_level,
  path)` and no single-column index; `SCHEMA_FORMAT_VERSION = 15`
  (the repo's practice refuses a mismatched mount, as 13→14 did; no
  in-place migration is written, the rebuild below is the maintenance
  seam). `ENTRY_ROW_ONLY_COLUMNS` names the column so the drift test
  passes.
- `storage/grants.py`: `level_at(star, path)` (the deepest covering
  posture row's level) and `posture_regions(star)` (each level's region,
  the stack walk slice A's `_everyone_region` used); `resolve` reads no
  `*` row — `spans = cover_all(shared)`, `whole` iff the grants cover
  the root, `roots` from the shared prefixes alone; `Rights.need` (the
  rank), `Rights.reaches(path, everyone_level)` (what a creation is
  judged by) and `Rights.admits(path, owner_id, everyone_level)` (the
  label first, then a bisect of the spans, then the owner floor);
  `_owned` is each owner arm's cover **minus the spans**, so the owner
  branch never names a row the range branch does and no `NOT EXISTS` is
  needed for disjointness. `_everyone_region` is gone.
- `storage/backends/database/labels.py` (new): `posture_rows` (one
  chunked read of the `*` rows among a set of prefixes), `labels_for`
  (a batch's labels from the distinct ancestors of its paths — one read
  per batch), `posture_beneath` (the posture in force at a transfer
  destination plus every `*` row beneath it), `label_of`, `relabel`
  (the posture change: `subtract(cover(path), cover_all(deeper))` →
  points by membership, open ranges in chunks of `in_list_budget`
  pairs), `relabel_spans`, `rebuild_labels` (every row from the `*`
  rows: each level's region, then the uncovered remainder to `none`,
  all as chunked range statements). The relabel `UPDATE` per dialect,
  the measured forms: SQLite and Postgres `UPDATE … FROM` through the
  range source (Core); MariaDB `UPDATE e JOIN JSON_TABLE(…) r ON … SET`
  (the study's plain-join form — its planner reads the ranges first and
  range-checks the path index per row; `STRAIGHT_JOIN` here would force
  the entry table first, the opposite of what the SELECT needs); SQL
  Server `UPDATE e SET … FROM OPENJSON(…) r INNER LOOP JOIN e`; Oracle
  and the generic floor the literal `OR` under `/*+ USE_CONCAT */`.
- `writes.py`: `_apply` reads the batch's labels once (`labels_for`
  over the created paths) and `_entry_values` stamps them; one more
  `SELECT` per batch, pinned in `test_write_statement_counts_are_pinned`.
  The write gate reads the posture rows separately (its targets'
  ancestors); sharing the read would thread the gate into the plan, so
  both reads stay one chunked statement each.
- `topology.py`: the trash chain mints its links labelled; `copy`
  labels every fresh row from `posture_beneath(dest)`; `move` and
  `restore` rewrite `everyone_level` **in the same statement** as the
  path — the root claim carries the destination's label and the
  descendant executemany carries one per row (`label_of` over the
  destination's posture map; a transfer onto a place that still holds
  stale deeper `*` rows takes those rows' levels beneath them, exactly
  as the oracle computes). The trash move passes no posture: a trashed
  subtree keeps the labels it had, the cheap half of §8 (the
  origin-judged branch, `restore`/`sweep` through it and the folded
  refusal are slice F).
- `rights.py`: `resolve_authority` reads the subjects' and groups'
  rows plus the root `*` row alone (`_root_level`, one row, for the
  anonymous refusal); `RIGHTS_FIELDS = {owner_id, everyone_level}` is
  what every judged row select carries (reads, glob, grep's and glean's
  `FETCH_RIDE`, the gate's and the restore permit's selects);
  `Visibility.admits` reads the label; `entries(scope)` is shape (e) and
  answers `None` for a caller with no pieces of its own (the everyone
  level alone decides, so the clause path serves it with one term);
  `narrow(stmt, scope)`; `prepare(session)` issues the profile's
  `range_settings` (Postgres `SET LOCAL jit = off`) from `_viewed`,
  once per partial read; `road` gains a third source, `_open_beneath` —
  a hidden directory holding a row everyone may see at the level is on
  the road to it (one `EXISTS` seek of the composite index per
  candidate, chunked); `WriteGate.subtrees` pages only the rows beneath
  the root with `everyone_level < need` (an open subtree is one empty
  seek, never a walk); `_decide` judges a creation by `reaches` with the
  label from the posture rows, and a missing ancestor the batch itself
  supplies is judged as its own target (a pre-existing gap the open
  mount's `whole` fast path had masked: `write([child, parent])`
  without `parents=True`); `_units` opens with the everyone unit
  (`everyone_level >= :r`, one bind) and carries no hole;
  `list_grants` and the grant verbs' shared refusal read the level at
  the path from the `*` rows on its chain. The rights cache key stays
  `(subjects, grant_revision)`.
- `ranges.py`: `visible_entries(entry, ranges, need, profile, scope)`
  renders branch 1 (`everyone_level >= :r`, scoped to the subtree's
  path range when the verb has one), the range branches and the owner
  branches each with `everyone_level < :r`, all `UNION ALL`; the join
  keyword is the profile's through a `_RangeJoin` element (its keyword
  is part of the cache key); MariaDB's `FORCE INDEX` and Oracle's
  `CARDINALITY`, branch-1 `INDEX` and derived-table hints come from the
  profile as templates; Oracle's range source `json_table_clob` binds
  the JSON as a CLOB. `derived_hint` is applied by glean's visible
  corpus count. **One finding beyond the study**: joined to a consuming
  statement as a plain derived table, SQLite pushes the outer table
  into every branch of the union and drives each branch from it,
  scanning the unpacked ranges once per outer row — `tree /` for the
  ordinary caller took 3.9 s at 10,000 users where the union alone
  takes a millisecond. The study measured the union standing alone, so
  it never saw this. On SQLite the visible set is therefore a
  `WITH visible AS MATERIALIZED (…)` common table expression
  (`DialectProfile.range_fence`), computed once and probed by the outer
  statement: 35 ms for the same tree. The other engines keep the plain
  derived table the study measured.
- `dialects.py`: `range_join` (SQLite `CROSS JOIN`, MariaDB
  `STRAIGHT_JOIN`, SQL Server `INNER LOOP JOIN`, Postgres and Oracle
  `JOIN`), `range_entry_hint` (MariaDB `FORCE INDEX ({index})`),
  `range_hints: RangeHints` (Oracle's four templates), `range_settings`
  (Postgres), `range_fence` (SQLite `MATERIALIZED`), `RangeSource`
  gains `json_table_clob` and Oracle declares it. Each field's docstring
  names the measured reason per engine.
- `engine.py`: the provisioned root row carries the mount's posture as
  its label. `backend.py`: `_viewed` prepares the view; the restore
  permit judges the trashed row by its kept label and the destination
  by the posture rows; `grant`/`revoke`/`posture` pass the profile and
  budget. `reads.py`, `scope.py`, `glean.py`: the rights fields ride
  every judged select; `tree` scopes the join to its subtree.
- Tests: `tests/support/oracles/grants.py` (the oracle's
  `everyone_rank` is the label's truth; the docstring says so);
  `test_rights.py` gains the random-world label parity (after every
  write, copy, move, mkdir, three posture changes, delete and restore,
  every live row's label equals the oracle's — a trashed subtree is
  excluded, by design) and judges rows by `(path, owner_id,
  everyone_level)`; `test_labels.py` (new) pins the labeller, the
  relabel's rendering on every dialect, the posture verb's `relabel`
  payload and the rebuild; `test_ranges.py` pins shape (e) per dialect
  (keyword, pins, hints, five disjoint branches, no `UNION`, no `NOT
  EXISTS`); `test_grants.py` pins `level_at`, `posture_regions`, the
  caller-sized `resolve` and the subtracted owner arms; the
  `GrantsContract` mixin gains the label on every engine, the road to an
  everyone-visible row under a hidden directory, and the open mount
  served through the label; `test_dialects.py` pins the new profile
  fields; `test_rows.py` the column and its one index.

Numbers (the baseline study's world through the shipped `DatabaseStorage`,
2 files per home, plus a 1,000-row `/mid` and a 200,000-row `/big`;
`bench100k.py` in the slice's scratch; M-series laptop, the engine legs
running beside it):

| | SQLite, N=100,000 (702,203 rows) | Postgres 17, N=10,000 (101,303 rows, `/big` 50,000; server shared with the leg) |
|---|---|---|
| ordinary caller's `resolve_authority`, cold (closures, rows, two resolves) | 4.3 ms (was: 75 min projected, stopped at 60 s) | 10.5 ms |
| one cached `Rights` pair (read + write), deep size | 36 KB, 78 pieces, 2.1 KB bind (was 42 MB) | 31 KB, 66 pieces |
| `tree /`, cold / warm, rows | 4.5 s / 6.6 s, 402,205 (was past 60 s; the system actor's 501,202-row tree took 5.8 s in the baseline — the floor is now the row objects, not the predicate) | 1.1 s / 1.3 s, 71,305 |
| `ls /home` | 1.6 s, 101 rows (100,000 hidden homes probed for the road, one seek each; the baseline's system `ls /home` took 1.4 s) | 0.6 s / 0.5 s |
| `glob /shared/*/*.md` | 2.2 s / 3.2 s, 200,000 rows (system: 2.8 s in the baseline) | 0.19 s / 0.35 s, 20,000 |
| posture change, 1,000-row subtree | 74 ms cold, 9 ms warm; 2 statements | 125 / 47 ms |
| posture change, 200,000-row subtree (50,000 on Postgres) | 376 / 423 ms; 2 statements | 1.5 / 2.8 s |
| `tree /` recall against `Rights.admits` over every row | exact (402,205 of 402,206; the one short is the root, which `tree` never lists) | exact |

The spec's 100k gate asks for `tree /` under a second; the predicate is
no longer what costs it — 402,205 observations are built per call —
and the `ls /home` time is the road probe over 100,000 hidden
directories, one indexed `EXISTS` each. Both are the next thing to
measure in slice E's gate run, not a wall.

Gates: `ruff check`, `ruff format --check` and `ty` at zero on `src/` and
`tests/`; the suite 3,640 passed with 100% coverage; `pytest docs` 23
passed; the full conformance class (the storage contract plus every
`GrantsContract` test, now including the label on every row, the road
to an everyone-visible row under a hidden directory, and the open mount
served through the label) passed on each engine at both checkpoints —
B2: Postgres 315, MariaDB 307, SQL Server 317, Oracle 312. Oracle runs
the range join for the first time, through `json_table_clob`.

Deferred: the in-flight marker, count-then-batch row chunking,
`RELABEL_ROWS`, resume and lock-before-decide (C); per-principal
revisions and the byte-bounded cache (E); the trash's origin-judged
branch, `restore`/`sweep` through it and the folded refusal payload
(F). The relabel today runs whole in the posture verb's transaction,
chunked by pieces only; a subtree of millions of rows holds that
transaction for its duration until C lands.

## Implementation progress — slice C

**2026-10-03.** The posture relabel is now a bounded, chunked,
resumable walk under a durable in-flight marker; while it runs every
reader sees the new posture through the compile; and the five admin
verbs lock before they decide. Nothing a caller may see depends on
whether a relabel has finished.

The in-flight rule as implemented. A posture change writes its `*` row
and a marker row, both committed together, then rewrites the labels
beneath in separate transactions. **While the marker stands, the
resolver compiles that one `*` row the old way.** The region it is
rewriting — the row's cover minus every deeper `*` row's — joins the
caller's spans as a *cover* when the new level reaches the caller's
need, and is cut from the everyone leg as a *hole* when it does not. A
row in a hole is judged by the spans and the owner floor alone, never
by its stored label, because the label may not have caught up.
`Rights.admits` applies the two rules in Python (the label decides
unless the path is in a hole); the SQL predicate fences the hole out of
the everyone branch with a `NOT EXISTS` over its unpacked pieces and
rides the spans' and owner arms' parts inside the hole as extra
disjoint branches. The compile stays bounded by the number of rows in
flight (normally zero), never by the mount. The cache is keyed on the
grant revision, which bumps when a row goes in flight (the posture
write) and again when the last chunk settles, so no compile outlives
its window.

File by file:

- `models/rows.py`: a `relabels(path_prefix, cursor)` table — the
  durable marker, one row per posture change under way, its cursor the
  last path a chunk rewrote; `SCHEMA_FORMAT_VERSION = 16`.
- `storage/backends/database/revision.py` (new): `read_revision`,
  `bump_revision` (the admin lock that advances), and `hold_revision`
  (the admin lock that does not — a relabel chunk takes it to serialise
  behind rival admin writes without retiring any compile). Lifted here
  so `rights.py` and `labels.py` share it with no import cycle.
- `storage/grants.py`: `intersect`, `above`, `through`, `end` (the
  range-set cursor algebra); `inflight_regions` (each pending row's
  region split into cover and hole by its new level); `Rights.holes`
  and the hole-aware `admits`/`ranges`; `resolve(pending=…)` folds the
  in-flight `*` rows in.
- `storage/backends/database/labels.py`: `mark_relabel`,
  `inflight_postures`, and `Relabeller` — the count-then-batch driver.
  Each `step` is one transaction: hold the admin lock, read the mark,
  rewrite the next chunk (at most `in_list_budget` pieces and
  `relabel_rows` rows), move the cursor or clear the mark and bump the
  revision. A range larger than a chunk is walked by keyset (`ORDER BY
  path LIMIT 1 OFFSET relabel_rows-2`); the plan is counted once
  (`ranges.range_counts`) and remade if the revision or cursor drifts.
  `rebuild_labels` and the posture verb no longer relabel inline.
- `storage/backends/database/ranges.py`: `hole_free` (the `NOT EXISTS`
  fence, literal negation on the generic floor) and `range_counts`; the
  holed-arm and holed-owner branches in `visible_entries`.
- `storage/backends/database/rights.py`: the admin verbs take the
  revision from the caller (bumped first) rather than bumping
  themselves; `resolve_authority(cache=None)` resolves uncached for an
  admin write and reads `inflight_postures`; `set_posture` marks the row
  and returns, no inline relabel; `subtrees` and `_open_beneath` and
  `_units` honour holes; `bump_revision`/`read_revision` moved to
  `revision.py`.
- `storage/backends/database/backend.py`: `_grant_write` is
  lock-then-gate-then-body (`bump_revision` first, gate resolved
  uncached under it, seams `grants:before-lock` and `grants:before-write`
  for the race pins); `posture` writes the row then `_settled` drives
  the `Relabeller` to completion, one chunk per writer transaction, and
  reports `{rows, statements, transactions}`.

Numbers (SQLite, slice scratch `scale.py`): a posture change to
`private` over a 200,000-row `/big` subtree relabelled 200,001 rows in
**10 update statements across 6 transactions, 0.53 s wall, no statement
over 49,998 rows** (the `relabel_rows` cap of 50,000 held). Reads during
an in-flight window are exact against the oracle — pinned in the suite
by `test_reads_match_the_oracle_while_a_posture_relabel_is_held_midway`
(every random world, every subject set) and the `GrantsContract`
in-flight test on every engine.

The race (review finding 5), executed on all four servers with the
adapted `race.py` (a rival `revoke` committed in the `grants:before-lock`
gap, then ann's own `grant`/`posture`): **every engine refuses the
stale write** — Postgres, MariaDB, SQL Server and Oracle, for both
`grant` and `posture`; the rival's revoke commits, ann's write is
`not_found`, and no row ann could not authorise is written. The
in-suite SQLite pin stages the revoke on the verb's own writer session
(SQLite admits no second concurrent writer), the repo's coherence
idiom. Resume is pinned by
`test_a_dead_relabel_resumes_and_reads_stay_exact_meanwhile` (kill after
chunk one, reads stay exact, a fresh driver clears the mark and the
labels equal the oracle).

Gates: `ruff check`, `ruff format --check` and `ty` at zero on `src/`
and `tests/`; the full suite passed at 100% coverage; `pytest docs` 23
passed; the full conformance class green on every engine — Postgres
316, MariaDB 308, SQL Server 318, Oracle 313.

Deferred to later slices: per-principal revisions and the byte-bounded
cache, and the 100k gate run (E); the trash's origin-judged branch,
`restore`/`sweep` through it and the folded refusal payload (F). A
background relabel runner is still a non-goal — the in-flight rule
already covers it, so the posture verb waits (decided §4).

## Implementation progress — slice F

**2026-10-03.** A trashed row is judged by its origin, on every verb;
restore's refusals echo only the path the caller sent; and the six
test pins the 058 review ordered on these paths are in the
`GrantsContract` mixin, each proven to kill the mutant it names.
Review findings 1 (critical) and 14 are closed, with 8 to 13.

**The storage form chosen for the origin: materialised, not derived.**
`entries.origin_path` is a nullable `BytewiseString(MAX_PATH_LENGTH)`
with its own index, schema format 17. Delete writes it in the same
statement that rewrites the row's path — the root claim as
`COALESCE(origin_path, path)`, each descendant from the rewrite list —
so every row of a trashed subtree records the path *it* held (a child
deleted as part of a subtree gets its own old path, not the root's),
and a row deleted from inside the trash keeps the origin it already
had. Every transfer out (restore, a move) clears it in its claim and
its descendant rewrite, so a row carries an origin exactly while it
sits under the trash root. The derived form (follow
`original_parent_id` to the parent's *current* path at query time) was
rejected: the parent may itself be trashed, moved or gone by the time
the row is judged, so it answers a moving target, while the grants the
deleter held at delete time named where the row *was*; and it would put
a self-join under every judged read. The rule it implements, in one
line: **a row's judged path is its origin when it has one, else its
path** (`judged_path`), with the label it kept and the owner it had.

File by file:

- `models/rows.py`: the column and `ix_<t>_origin_path`; format 17;
  `ENTRY_ROW_ONLY_COLUMNS` names it.
- `paths.py`: `is_trash_path` (the trash root or beneath it, the one
  home for the test `edges.py` had privately) and `on_trash_chain`
  (the trash root, an ancestor of it, or a path under it — the only
  places a row with an origin can lie, so every scoped read elsewhere
  is untouched).
- `storage/backends/database/rights.py`: `RIGHTS_FIELDS` gains
  `origin_path`, so every judged select carries it; `judged_path` and
  `judged_columns`; `Visibility.admits` judges the origin. Every piece
  predicate goes through `_judged_units`: the live form on `path`
  carries `origin_path IS NULL` (no bind) and the trashed form seeks
  `origin_path`, so the clause fan and the vector leg spend twice the
  binds per piece and a grant on the trash subtree reaches no trashed
  row. `Visibility.road` gains a fourth source, `_origin_beneath`: a
  trash-chain directory holding a trashed row whose origin the caller's
  pieces cover is on the road to it; `_owned_beneath` and
  `_open_beneath` judge the origin, and the three share `_beneath`.
  `WriteGate.subtrees` never takes the cover fast path on the trash
  chain (cover of the root's paths proves nothing about rows judged
  elsewhere) and judges each paged row at its origin; `WriteGate.row`
  takes the path to judge and the path to name apart; `WriteGate.missing`
  is the one refusal for a target the call cannot act on — the descent
  ladder over what the view shows, so a hidden ancestor reads as a
  missing one and the payload names a prefix of the sent path only;
  `denied` is public.
- `storage/backends/database/ranges.py`: `visible_entries` sends every
  piece branch in two forms — live on `path` with `origin_path IS
  NULL`, trashed on `origin_path` through its index, each dialect's
  index hint naming the right column — unless the scope lies off the
  trash chain, where only the live forms go; `judged_hole_free` fences
  an in-flight hole on the judged path. The five-branch statement the
  study measured becomes nine for an unscoped read and stays five for
  a subtree read outside the trash.
- `storage/backends/database/labels.py`: every relabel statement runs
  twice, over `path` for the live rows and over `origin_path` for the
  trashed ones, so a posture change after a delete reaches the trash
  row at its origin and the rebuild agrees — a trashed row's label is
  always the level at its origin. The trashed form is sized by the
  trashed rows whose origin lies in the chunk's pieces, which the
  chunk's row count does not bound; a keyset walk over `origin_path`
  is the direction if a mount ever trashes more rows than one chunk.
- `storage/backends/database/topology.py`: delete records the origin;
  `_apply_rewrites` records it on the descendants of a trash move and
  clears it on every other transfer; `_execute_move` clears it on the
  root. Restore is split into `_lookup_restore` (the trash row and the
  destination's parent, no wording) and `_restore_site` (the ladder's
  verdict); `RestoreLookup` and `RestoreSource` are public, and the
  backend's `permit` sees both before any refusal is chosen.
- `storage/backends/database/backend.py`: the restore permit — a row
  the caller cannot see is answered as the gate answers any target it
  cannot act on (`missing`, or `permission_denied` when it is a
  directory on the road, so both addresses of one trashed directory
  get one verdict); a trash-side address whose original parent the
  caller cannot see is answered as absent, folding "original parent no
  longer exists", "restore `<parent>` first" and "Not a directory:
  `<parent>`" away from a caller they would inform; the ladder's own
  refusals stand only once the caller may see everything they name;
  the destination is judged under the posture rows and named by the
  sent path when its parent is hidden.
- `reads.py`, `glean.py`: the explicit judged selects carry
  `RIGHTS_FIELDS`. `edges.py`: uses `is_trash_path`.
- Tests: `tests/support/oracles/grants.py` gains `origins` and
  `judged` — the oracle judges a trash path at its origin with the
  owner it had; `test_rights.py` includes trashed rows in the label
  parity (a posture change while `/m1` sits in the trash) and adds
  `test_the_trash_is_judged_by_its_origin_against_the_oracle`: for
  every random world and subject set, a deleted directory's trash
  listing equals the oracle's admitted rows plus the road, and restore
  and sweep succeed exactly when the oracle writes every row — denied
  when the trashed root is seen or on the road, absent otherwise;
  `GrantsContract` gains the trash section (the open mount with one
  private home, a group holder restoring what it does not own by both
  addresses, the refusal wording, the hidden original parent) and the
  six review pins; `test_ranges.py`, `test_labels.py`, `test_rows.py`
  and `test_trash.py` pin the shapes and the column.

**The repros, after** (SQLite and Postgres, the review's scripts
adapted to the tree; before, on Postgres under an open root: dave read
the trashed diary, anonymous read it, dave swept it, and ann's restore
then failed). Under open, shared and private roots alike: dave and
anonymous `not_found` on the trashed diary; dave's sweep of it
`not_found` and of `/.vfs/trash` `permission_denied` — with a
`read_write` grant on `/.vfs` too; ann lists the bucket and restores.
zed, holding nothing on a private mount: `/hr/fired.md`, `/hr/other.md`
→ `Not found: /hr`; `/nodir/x.md` → `Not found: /nodir`; the trash
address → `Not found: /.vfs` — the same message `read` gives each path,
no trash path and no "No trashed entry for" (before: three
distinguishable answers, one naming the trash row).

**The mutants** (a source-rewrite import hook in the slice's scratch,
`VFS_MUTANT=<name>`, the memory leg; the tree passes every pin):

| mutant | pin that kills it |
|---|---|
| M8 — the admin lock reads the revision instead of bumping it, and the relabel's settle does not bump | `test_a_posture_change_is_seen_by_a_caller_already_resolved` (anonymous's cached root posture keeps answering `not_found` where `unauthenticated` is owed) |
| M9 — `add_member_rows` without its bump | `test_a_membership_change_is_seen_by_a_caller_already_resolved` |
| M10 — glean's overlay admits without the view | `test_a_hidden_row_written_after_the_index_never_reaches_the_overlay` |
| M11 — grep's index-side candidates skip the view | `test_grep_never_matches_inside_a_hidden_row_through_the_index` |
| M12a — copy's source gate dropped (N17) | `test_a_copy_needs_read_at_its_source_and_write_at_its_destination` |
| M12b — copy's destination gate dropped (N18) | the same pin |
| M13 — a moved source gated at read (N16) | `test_a_move_of_a_visible_read_only_source_is_denied` (and `test_a_move_needs_write_at_both_ends` now asserts the kind) |

Gates: `ruff check`, `ruff format --check` and `ty` at zero on `src/`
and `tests/`; the suite 3,697 passed with 100% coverage; `pytest docs` 23
passed; the full conformance class on each engine — Postgres 326,
MariaDB 318, SQL Server 328, Oracle 323, plus the hidden-destination
restore pin run once more on each engine after it was added (6 legs
passed). The MariaDB leg found one engine fact on the way: the mysql
family applies ``SET`` left to right, so an origin computed in the
statement as ``COALESCE(origin_path, path)`` read the rewritten path;
the origin is bound from the snapshot row instead.

Record corrected: the `context/open-questions.md` entry "Trash under a
non-open posture" stated that a trash row is owner-only under a shared
posture; the review showed it world-readable. The entry moved to
`open-questions-archive.md` with the correction and the decided rule.

Deferred: slice E (per-principal revisions, the byte-bounded cache, the
100k gate run); a keyset walk of the relabel's trashed form.

## Implementation progress — slice E

**2026-10-03.** The rights cache is keyed on what can change a caller's
rights and nothing else: a stamp per principal and group, and the
relabel marks. A grant retires its grantee's compile, a membership
write its member's, a posture change nobody's — the labels decide —
except for the span of its relabel, which every reader compiles once
as a cover or a hole and then drops. The cache is bounded in bytes as
well as entries. The 100k gate ran on SQLite and Postgres and its
numbers are in
`../../../research/studies/2026-10-02-grants-at-100k-users-baseline/runs/gate-2026-10-03.md`.

**The table and the key.** `principal_revisions(principal_id,
revision)` — one row per principal or group ever named by a grants or
memberships write, stamped with the grant revision of the write that
last named it (`stamp_principals`, under the admin lock, after
`bump_revision` and after the gate). Absent means never named: stamp
0. A new row takes the mount revision rather than 1, so a never-named
principal's first stamp is above every stamp before it and the
caller's maximum moves. The key is `RightsKey(subjects, stamp, marks)`:
the subject set, the greatest stamp over the subjects and their
closure groups (`principal_revision`, one chunked `MAX … WHERE
principal_id IN (…)`, bounded by the closure size), and the relabel
marks in flight as `(path, revision)` pairs. `relabels` gains a
`revision` column — the mount revision the mark was planted under — so
a mark is a value, not just a presence: clearing it retires every
compile made while it stood (their key names a mark that no longer
exists and can never recur), and a second posture change on the same
path replants it under a new revision and retires the first's compiles
too. Schema format 18.

**Who is stamped, and why the member alone.** `grant_rows` and
`revoke_rows` stamp the grantee (a group's stamp retires every member,
because every member's closure holds the group and its key reads the
group's row). `add_member_rows` and `remove_member_rows` stamp the
*member* only. The brief suggested stamping the group too; thinking
it through, the member is the one row that is both sufficient and
necessary: a membership write changes the *member's* closure, every
caller whose closure holds the member (the member itself, or, for a
nested group, every member of it) reads the member's stamp, and no
other caller's closure changed. Stamping the group would retire every
fellow member for nothing (500 recomputes per membership change at
100k); stamping the group *instead* of the member would miss the
nested case, since a caller whose closure gains the group through the
member does not read the group's row until after the write. Pinned:
`test_a_membership_change_retires_the_member_and_not_its_fellow_members`
and the contract triple below. `set_posture` stamps the everyone
principal `*` alone: the one caller whose rights are the posture and
nothing else is anonymous, whose key reads `*`'s stamp beside its own,
so the root posture it carries for the `unauthenticated` refusal
follows every posture write while no named caller is retired.

**The read, hit and miss.** On a hit the resolver reads two things:
the stamps of the ids the entry was made for (the cache remembers the
closure's ids beside the compile, so no walk is needed to know whose
stamps to read) and the marks. Equal stamp and equal marks mean no
write that could change the compile has committed — every such write
stamps one of those ids — so the entry is served; the stamps are read
before the marks, so a write landing between the two reads is one the
next call sees whole. On a miss: the mount revision is read, the
closures walked, the ids' stamps read, the marks read, the rows read,
the pending postures compiled in, and the mount revision read again; a
compile the two reads disagree over is answered but not remembered,
because an admin write landed between its statements and the compile
may be torn (closures from before, stamps from after — which, cached,
would be stale until the next write). On every engine but SQLite each
statement sees its own snapshot, so the guard is what makes the miss
path safe under READ COMMITTED; it costs one single-row read on misses
only. `meta.grant_revision` still bumps on every admin write — it is
the lock and the stamp source — but keys nothing. `Resolution` loses
its `revision` field.

**The cache.** `RightsCache(entries=RIGHTS_CACHE, budget=RIGHTS_CACHE_BYTES)`,
one entry per subject set, LRU past either bound, the newest entry
always kept. `RIGHTS_CACHE` is 1,024 entries and `RIGHTS_CACHE_BYTES`
64 MiB; `weight(resolution)` is `sys.getsizeof` over the spans, roots,
holes, owner arms and pieces of both rights, strings counted per
occurrence (an overestimate, so the bound is conservative), with the
pieces computed at put time so the estimate counts what a view holds.
One ordinary caller at 100k weighs 55.6 KB (57 KB held per caller in
the running cache), so the entry ceiling binds first for ordinary
callers and the byte budget for heavy ones.

File by file: `models/rows.py` (the table, the column, format 18);
`revision.py` (`principal_revision`, `stamp_principals`, the docstring
now the whole story of the two revisions); `labels.py` (`Mark`,
`mark_relabel(path, revision)`, `inflight_marks` split from
`inflight_postures(marks)`); `rights.py` (`RightsKey`, the cache, `weight`,
`resolve_authority`, the five verbs' stamps); `backend.py` (the cache
comment). Tests: `test_rights.py` — a user grant retires that user and
nobody else (three cached callers, `resolve` counted per miss), a
group grant its members only, a membership write its member and not a
fellow member, a settled posture change nobody but the in-flight
window everybody once and the settle once more, a posture change the
anonymous compile, the hit path's statement shape (stamps, marks, the
row read — never the memberships), the torn-compile guard, entry and
byte eviction, `weight`; `GrantsContract` gains
`test_an_admin_write_retires_only_the_compiles_it_reaches` (the
triples on every engine); `test_labels.py` and `test_rows.py` pin the
mark's revision and the table.

**The gate** (the full table in the run file): on SQLite at N=100,000
the ordinary caller's compile is 2.98 ms on a miss and **0.41 ms on a
hit**, 2.1 KB of binds, 55.6 KB cached; `tree /` 1.16× the system
actor cold and 1.49× warm (402,205 rows against 702,202); `glob
/shared/*/*.md` 0.79× / 1.01×; `admits` 0.17–0.42 µs per row; a posture
change on 1,000 rows 106 ms cold and 15 ms warm, on 200,000 rows 0.46 s
in 20 statements over 6 transactions with no statement over 49,998
rows, on 1,000,000 rows 2.29 s in 84 statements over 22 transactions;
one user grant retires 1 of 200 cached callers, one group grant exactly
the 3 cached members, a posture change 0. Postgres at N=10,000 agrees
on every shape (miss 11.4 ms, hit 2.3 ms, `tree /` 0.58× / 0.71×, one
user grant 1 of 200, a group grant exactly its 26 cached members).
**Two criteria are not met**: the compile under 1 ms holds on the hit
path only (the miss path, paid once per caller and again only when a
write names it, is 2.98 ms); and `ls /home` is 2.5× the system actor
(1.79 s against 0.72 s) on SQLite and 2.5–4.8× on Postgres — the road
probe over 100,000 hidden homes, one indexed `EXISTS` each in chunks
of 1,000, which is the whole of the ordinary caller's time there. The
direction for the road is one range statement per chunk over the
`(everyone_level, path)` index (the hidden candidates sorted, the
first row at the level above each candidate's `/`-bound found by a
single ordered seek per candidate inside one statement) rather than
one correlated `EXISTS` per candidate; it is the observation layer's
next measurement, not a wall. The 1,000-row posture change misses the
100 ms line by 6 ms on the first call of a cold run only.

Gates: `ruff check`, `ruff format --check` and `ty` at zero on `src/`
and `tests/`; the suite passed at 100% coverage; `pytest docs` passed;
the full conformance class on each engine — Postgres 328, MariaDB 320 (8 skipped), SQL Server 330, Oracle 325; the suite 3,709 passed.

