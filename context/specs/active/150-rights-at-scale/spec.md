# 150 — Rights at scale: the everyone level on the row, caller-sized ranges, and the linear range algebra

- **Status:** **drafted 2026-10-02 with Claude's recommendations, awaiting
  Clay's read.** Born from ADR 073 (proposed the same day). Every
  `[NEEDS CLARIFICATION]` below is a fork Clay decides; each carries
  the recommendation and the evidence for it. Not scheduled; it is the
  next grants work after the 058 review, and three of its slices are
  the bug fixes that review ordered.
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

**While in flight**, the resolver compiles that one `*` row the old
way: at the caller's level it is an arm (if it widens) or a hole on
the caller's pieces (if it narrows), so every reader sees the new
posture from step 2 onward, and the rows' stale labels do not matter.
The in-flight set is read with the caller's rows (one small table or
one filtered read of the `*` rows) and is normally empty. A relabel
that dies leaves its marker set, the compile covers it, and the next
`posture` call on any path, or the maintenance verb, resumes it.

- [NEEDS CLARIFICATION: **does the posture verb wait for the relabel,
  or return with it in flight?** Measured: 2 s per million rows on
  SQLite, 17 s on Postgres; a ten-million-row subtree is minutes.
  **Recommendation: the verb waits.** The chunks are separate
  transactions, so the wait never holds a long lock; the in-flight
  compile makes correctness independent of the wait; and a verb that
  returns before its work is done needs a task runner vfs does not
  have. A background relabel can be added later without changing any
  contract, because the in-flight rule already covers it. The verb
  reports rows relabelled and chunks run in its result payload.]

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
- [NEEDS CLARIFICATION: **the statement shape on Postgres.** The
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
  not model.]

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
- [NEEDS CLARIFICATION: **is judging a trashed row by its origin the
  rule Clay wants?** The alternative is a posture of `none` on the
  trash bucket, which hides every trashed row from everyone but
  owners and whole-mount callers, and makes a system-written row
  (no owner) in a private home unrestorable by that home's holder.
  **Recommendation: judge by origin.** It is the only rule under
  which "delete then restore" is invisible to permissions, which is
  what a user expects of a trash.]

### 9. The owner floor on a move

A subtree moved into another user's private home stays visible to
its former owner through the mount-wide owner floor (the spike's §4;
the shipped code agrees). The mover had `read_write` on the
destination at the time, or the move was refused.

- [NEEDS CLARIFICATION: **mount-wide floor (today), or bounded by the
  row's current area?** **Recommendation: keep it mount-wide**, as
  058 §2 and ADR 064 rule 4 state and the docs promise ("so that a
  person can never be locked out"). The bounded form (`owner_id = me
  AND everyone_level >= read`) is one term away if Clay prefers it,
  and the review's finding 33 (owner restamped on edit, so a revoked
  writer keeps rows it rewrote) is the same policy question seen from
  the write side; both should be decided together, and this spec
  does not change the restamp.]

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
  `tree /` under 1 s warm (it was past 60 s); `ls /home` and
  `glob /shared/*/*.md` under 1 s; `admits` under 10 µs per row; one
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

The four `[NEEDS CLARIFICATION]` markers above: §4 (wait or return),
§5 (the Postgres shape), §8 (the trash by origin), §9 (the floor's
scope, with the edit restamp). Each has a recommendation; the spec is
buildable as recommended.
