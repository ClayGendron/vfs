# 073. The Everyone Level Lives on the Row, and a Caller's Rights Are Caller-Sized

- **Status:** accepted 2026-10-02 (Clay: "I'll take your recommendation
  based on the research for the four forks. please get going on this
  work"; the forks are spec 150 §4, §5, §8 and §9). Amends ADR 067 rules 1 and 2 (the
  compile model), ADR 071 rule 6 (every deeper `*` row as a hole) and
  ADR 072's input (the pieces a caller sends). Does not change what
  any caller may see: every rule below is a representation change,
  held to the same pointwise answers.
- **Date:** 2026-10-02
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, 2026-10-02). Drafted by Claude from
  `../research/2026-10-02-grants-at-100k-users-measured.md` and
  `../research/2026-10-02-row-labelled-acls-and-the-list-problem-prior-art.md`,
  on Clay's direction ("we need to scale to 100,000+ users each with
  their own private folder, and grants to dozens of shared ones";
  "draft or update the spec with your recommendations").

## Context

ADR 067 compiles a caller's rights in app code and sends them to SQL
as a literal predicate. ADR 068 made the mount open by default, with
a posture per directory. ADR 071 rule 6 then said how the two meet: an
open prefix is an arm, and **every** deeper `*` row that lowers the
level is a hole cut from it. ADR 072 turned arms minus holes into
sorted path pieces, one bound value, joined to the path index.

That representation has one input the caller does not own. Under an
open root with one private home per user, every caller's root arm
carries every other user's home as a hole. The 2026-10-01 review
found it failing at about 1,000 homes. The 2026-10-02 baseline study
measured it to the end, on SQLite at 1,000, 10,000 and 100,000 users:

| | 1,000 | 10,000 | 100,000 |
|---|---|---|---|
| holes per caller | 1,000 | 10,000 | 100,000 |
| `pieces()` | 119 ms | 18.4 s | about 75 min (stopped at 60 s) |
| bind per query | 92 KB | 920 KB | 9.2 MB |
| `admits` per row | 21 µs | 200 µs | 4.3 ms |
| `tree /`, ordinary caller | 0.2 s | 21 s | past 60 s |
| cached `Rights` per caller | 427 KB | 4.2 MB | 42 MB |

The clause fan (ADR 071 rule 1), which the vector leg and Oracle
still use, fails at exactly 1,000 holes on SQLite and wedges the
Postgres backend at 5,000. One grant write invalidates every cached
caller; at 100,000 users that is 59 CPU-hours of recompute if each
user reads once.

The prior-art memo found no system that compiles other principals'
grants into a caller's rights. Those that store a label on the row
(SharePoint's scope id, juicefs's ACL id, NTFS's inherited ACEs) pay a
bounded subtree write when the label changes and keep the label a
position fact, never a principal list. Unix pays nothing per caller
at all: the inode's mode is the label.

Two executed studies on SQLite and Postgres at the same scale:

- **The row label.** A three-valued `everyone_level` on each entry
  row, written with the row and rewritten for a subtree on a posture
  change; explicit grants as ADR 072 pieces built from the caller's
  own rows; the owner floor as a column. An ordinary caller compiles
  to about 2 KB in 22 to 31 µs at every N. A scoped read is 2.5 ms on
  both engines at 100,000 users. Recall exact everywhere. A posture
  change relabels its subtree at 2 s per million rows on SQLite and
  17 s on Postgres, chunkable by path range, and invalidates no
  compiled rights.
- **The sorted-merge algebra.** Every pairwise loop in `grants.py`
  replaced by one pass over sorted ranges: 3.76 million three-way
  checks against the oracle and the shipped code, zero
  disagreements; 100,000 fuzz worlds, zero invariant breaks; 100,000
  holes in 287 ms instead of a projected 27 minutes; two members over
  10,000 grants in 57 ms instead of 26 s. The same pass fixes the
  sibling bound bug (`/v1` beside `/v10` shipped a NUL-terminated
  bound that Postgres rejects; numbered homes trigger it 99 times per
  1,000).

Neither change alone is enough. The algebra leaves the holes in the
compile and a 9 MB bind per query. The label leaves the meet across
members quadratic.

## Options considered

- **Keep the compile, make it linear.** The algebra alone. Rejected
  as the whole answer: 287 ms per caller per revision and 9.2 MB per
  query at 100,000 users is still world-sized, and `admits` still
  scans the holes per row.
- **A per-row ACL handle (`domain_id`): the nearest grant-or-posture
  boundary.** Measured beside the level. Rejected: a grant at a new
  prefix relabels its subtree (758 ms per million rows), the caller's
  bind grows with the boundaries the posture reaches (1,002 ids at
  100,000 users), and no index combines "handle in list" with "path
  in range", so the scoped read loses (16 ms against 2.5).
- **Engine-native row security.** Rejected in ADR 067; Postgres RLS
  cannot make the hole predicate cheap either (a `NOT EXISTS` over
  homes is a per-row subplan), so it would not have helped here.
- **The everyone level on the row, explicit grants as the caller's
  own ranges, the algebra linear.** Chosen.

## Decision

1. **The everyone level is a column on the entry row.**
   `entries.everyone_level ∈ {none, read, read_write}` is the level of
   the deepest covering `*` row at the row's path. It is written when
   the row is written, rewritten for the subtree when a `*` row
   changes, and rewritten on a move. It is derived, never
   authoritative: the `*` rows remain the truth, and the column is
   rebuildable from them.
2. **A caller's compiled rights hold only the caller's own prefixes.**
   `Rights` is built from the rows that name the caller's subjects
   and their groups, as sorted disjoint path pieces (ADR 072's
   points and open ranges). No `*` row enters the compile. The word
   "hole" leaves the compiler: ADR 071 rule 6 is withdrawn.
3. **Visibility is three index seeks**, one per source of a right:
   `everyone_level >= :level`, the range join on the caller's pieces
   (ADR 072), and `owner_id = :sub` per member. Their union is the
   visible set. The predicate's shape and size no longer depend on
   how many other principals the mount holds.
4. **Every operation on ranges is one pass over sorted input.** Union
   within a member, the meet across members, the owner-floor trim,
   `minimise`, `covers`, `admits` and the split into pieces are
   sorted merges or binary searches. No cross product, no rebuild
   per element. `admits` reads the row's `everyone_level` and
   bisects the caller's pieces.
5. **A span whose upper bound ends in the sentinel is the open range
   up to the path before it plus that exact point.** This completes
   ADR 072 rule 1: no bound a caller sends ever ends in a byte below
   `/`.
6. **A posture change is a bounded, chunked relabel.** The `*` row is
   written and the subtree's `everyone_level` rewritten in chunks,
   each chunk bounded by the dialect's bind budget in pieces and by a
   declared row count, each chunk its own transaction. While a
   posture's relabel is in flight, that one `*` row compiles the old
   way, as an arm or a hole on every affected caller, so readers see
   the new posture at once; when the relabel settles, it leaves the
   compile. A relabel that dies is resumed, never left half-done
   without the in-flight compile covering it.
7. **Revisions are per principal and per group, not one counter.**
   A caller's cache key is the maximum revision over its subjects and
   their groups' closures. A grant to a user invalidates that user; a
   grant to a group invalidates its members; a posture change
   invalidates nobody's compiled rights. The mount-wide
   `grant_revision` stays for version rows (ADR 064 rule 2) and the
   admin lock.
8. **Admin verbs lock before they decide.** `grant`, `revoke`,
   `posture`, `add_member` and `remove_member` take the revision lock
   first, then resolve the caller's rights, then write.

## Consequences

- The schema gains one column and one composite index,
  `(everyone_level, path)`; schema format 15. A migration relabels
  every row from the `*` rows once.
- `grants.py` keeps its public names; `Arm(prefix, holes)` goes;
  `Rights` carries range sets. The 400-world parity test and the
  pointwise oracle remain the authority, extended with sibling pairs
  (`p` beside `p0`) that the generator never produced.
- `rights.py` loses `_units`' hole fan. The clause fan (ADR 071 rule
  1) survives only for dialects without a `range_source` and for the
  vector leg, now over the caller's own pieces, which are dozens.
- Spec 058 §0 "Compilation", §3 step 4 and §4 are superseded by spec
  150, which carries this decision into code.
- Open choices the spec must settle, each with a marker: the
  owner-floor scope when a row moves into another user's private
  area; what label a trashed row carries (ties to review finding 1);
  whether the posture verb waits for the relabel or returns with it
  in flight; the per-dialect statement shape (Postgres misestimates
  the `UNION` by 1,300× and needs a fence or disjoint branches).
- SQL Server, MariaDB and Oracle have not run this design. The
  five-engine pass that ADR 072 required before building is required
  again before slice B of spec 150 lands.
