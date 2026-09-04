# The delete-vs-mkedge race — staged on five engines, prior art on four fates

- **Status:** research memo (commits us to nothing)
- **Date:** 2026-09-04
- **Owner:** Clay Gendron
- **Method:** an executed experiment (the race staged deterministically
  through the `mkedge:before-insert` seam with a genuine rival delete
  on a second `DatabaseStorage`, run on Postgres 17, MariaDB 11.8,
  SQL Server 2025, Oracle 23ai Free, and sqlite; a Postgres row-lock
  probe; a read-path audit of the live tree), plus five parallel
  researchers over refreshed read-only `~/Git/Repos` checkouts —
  spicedb (Apache-2.0, `origin/main` 9b5cdc1, 2026-09-03), openfga
  (Apache-2.0, `origin/main` 450b68c, 2026-09-04), jackrabbit-oak
  (Apache-2.0, `origin/trunk` f26e243, 2026-09-04), gel (Apache-2.0,
  `origin/master` 8519106, 2025-12-23), juicefs (Apache-2.0,
  `origin/main` c9a67b2, 2026-09-04), postgres (PostgreSQL licence,
  `origin/master` 74c7705, 2026-09-04). All clones refreshed to their
  upstream defaults and license-checked 2026-09-04.
- **Question under evaluation:** spec 143's landing review found a
  race: `mkedge` resolves its endpoint ids, a rival `delete` then
  trashes an endpoint, cascades the authored edges it can see (the new
  edge is not inserted yet), and commits; `mkedge`'s insert then
  commits an authored edge naming a trashed entry. Is the race real on
  our engines, who can observe the stray, and which of the candidate
  fates — accept, prevent by locking, heal at restore, heal at
  reindex — does the field support?

## Bottom line

1. **The race is real on every client/server engine.** Staged
   deterministically, the stray edge lands on Postgres, MariaDB,
   SQL Server, and Oracle alike — no isolation pin prevents it, no
   engine aborts either transaction, and `mkedge` reports `created`
   for an edge whose target is already in trash. Only sqlite is
   immune, by its single-writer architecture: the rival delete cannot
   commit inside the window (it classifies as a retryable conflict and
   loses), so the edge lands against a live entry.
2. **Nothing heals it today, and restore resurrects it.** Reindex
   re-convergence reports zero warnings and leaves the stray in place
   (`collect_edge_drift` reclaims only rows whose endpoint *entry row*
   is gone; a trashed entry still has its row). After `restore`, the
   stray is a fully live authored edge — silently violating "restore
   never re-mints" — and `rmedge` can then remove it normally.
3. **No reader can see it yet.** The live tree's only consumers of the
   edges table are the edge verbs themselves, the mirror mint sites,
   and reindex. The first genuine readers arrive with spec 136
   (in-degree signals — a stray would inflate a score) and spec 067
   (traversal). The observable damage today is confined to the
   restore resurrection and the conformance invariant.
4. **The cheap lock works on Postgres.** A probe confirmed that both
   `FOR KEY SHARE` and `FOR UPDATE` on the endpoint entry row block
   the rival delete: trash rewrites `path`, a unique-indexed column,
   which counts as a key update and conflicts even with the weakest
   share lock. Portably, the house shape is the plain
   `with_for_update()` guard `repair_edge_drift` and the segment
   repair already use.
5. **The field's verdict is unusually clean.** Every surveyed system
   that enforces only the *delete* side of the reference — Oak's
   commit-hook check, gel's delete triggers — leaves this exact
   insert-vs-delete window open (Oak demonstrably, gel with no
   comment acknowledging it). The two systems that actually close it
   both do it the same way: an **insert-side lock on the referenced
   row** — juicefs's `SELECT … FOR UPDATE` on the target inode
   inside the link transaction, and Postgres's own FK machinery
   (`FOR KEY SHARE` at insert). The dangle-by-design camp
   (SpiceDB/OpenFGA) holds that position because their architecture
   forces it — they have no resource table to check — where vfs
   holds both sides of the reference in one store and one
   transaction scope. vfs's delete cascade is already the
   delete-side enforcement; the insert side is the missing half.

## The staged race — what actually happens

The experiment (rerunnable:
`studies/2026-09-04-delete-vs-mkedge-race/`): two `DatabaseStorage`
instances on one minted table namespace; storage A runs
`mkedge(/src.py → /dst.py, "imports")` with a handler installed on the
`mkedge:before-insert` seam; the handler drives
`storage_b.delete(path=/dst.py)` to completion and commit, then A's
insert proceeds.

| Engine | rival delete | mkedge | stray after commit | after reindex | after restore |
| --- | --- | --- | --- | --- | --- |
| Postgres 17 | succeeds | `created` | present | present, 0 warnings | present, live |
| MariaDB 11.8 | succeeds | `created` | present | present, 0 warnings | present, live |
| SQL Server 2025 | succeeds | `created` | present | present, 0 warnings | present, live |
| Oracle 23ai | succeeds | `created` | present | present, 0 warnings | present, live |
| sqlite | loses (`conflict`, retry exhausted) | `created` (target still live) | none — no race | — | — |

Three facts worth stating twice. The stray survives reindex: the
re-convergence pass is blind to it by design, because the trashed
entry's row still exists. The stray survives until purge: sweep's
purge arm deletes every edge touching a destroyed id, so the damage
self-limits at the trash horizon (90 days by default). And restore
turns the stray into a live authored edge with no record that
anything went wrong.

The Postgres lock probe: holding `SELECT … FOR KEY SHARE` on the
target's entry row, the rival delete blocked until release; same with
`FOR UPDATE`. The reason the weak lock suffices is that delete's
trash rewrite updates `path`, and `path` carries a unique index — a
key update, which conflicts with `KEY SHARE` (see the Postgres
section below for the FK mechanics this mirrors).

## Who can observe the stray (read-path audit)

`grep` over the live `src/` tree: the edges table is touched by
exactly four modules — `edges.py` (the verbs and re-convergence),
`writes.py` and `topology.py` (the mirror mint sites and cascade),
and `backend.py` (routing, reindex). No read verb joins it. While the
target is trashed the stray is unaddressable even by `rmedge` (trash
paths are unresolvable as endpoints). So today the stray is
observable in exactly two ways: the conformance invariant ("zero edge
rows touching trashed ids") and the post-restore resurrection.
Spec 136's in-degree signal is the first reader that would silently
consume it.

## Prior art — the four positions

### juicefs — lock in the transaction, repair the rest later

The closest analogue vfs has: a POSIX filesystem whose metadata lives
in SQL (read at c9a67b2). Its `doLink` (hardlink creation — insert a
row referencing an inode) re-reads the target inode's row **inside
the same transaction with `SELECT … FOR UPDATE`** (`pkg/meta/
sql.go:2700`) and refuses `ENOENT` if the row is gone; `doUnlink` and
`doRmdir` take the same lock on the same row (`sql.go:2003`, `:2187`),
so the engine serializes the two sides and the loser re-reads
committed truth. There is **no foreign key** from edge to node
(`sql.go:69`) — the lock does the FK's job, exactly the shape of our
candidate fix. Around it: duplicate names are left to a unique
constraint plus a 50-attempt quadratic-backoff retry loop
(`sql.go:1230–1267`), and anything not guarded inline (orphaned
attribute rows, leaked slices) is deliberately a background-repair
problem — `juicefs fsck --repair` reconstructs missing node rows
(`base.go:2474+`, `sql.go:4176`), hourly GC goroutines reap the rest.
Position: **lock the referenced row for the hot-path race; never
block the live path for anything else; repair-later as the backstop.**

### SpiceDB / OpenFGA — dangle by design, structurally

Read at 9b5cdc1 / 450b68c. Neither system *can* check endpoint
existence: their storage schemas hold only tuple and changelog/
transaction tables — there is no resource table to check against
(spicedb `internal/datastore/postgres/schema/schema.go:10-14`;
openfga `pkg/storage/postgres/postgres.go:469,551`). Write-time
validation is schema-shape only (namespace, relation, type
restrictions — spicedb `internal/relationships/validation.go:145`;
openfga `internal/validation/validation.go:37`). The row locks and
strong isolation they do use (SpiceDB Serializable on Postgres,
`postgres.go:293`; OpenFGA `SELECT … FOR UPDATE` over the tuple rows,
`postgres.go:1399-1410`) guard tuple-vs-tuple write races, never
resource existence. Cleanup of dangling tuples is entirely the
calling application's job, via filtered `DeleteRelationships`
(spicedb `internal/services/v1/relationships.go:494`) — plus an
opt-in per-tuple TTL in SpiceDB; OpenFGA offers nothing. Position:
**dangle by design — but note the position is forced by their
architecture (no resource table), where vfs holds both sides of the
reference in one store and one transaction scope.**

### Jackrabbit Oak — commit-time enforcement, delete side only

Read at f26e243. Oak's `ReferenceEditor` runs synchronously inside
the commit's own critical section (a commit-hook `IndexEditor`,
`oak-core/.../reference/ReferenceEditor.java`) and rejects the whole
commit (`CommitFailedException(INTEGRITY)` →
`ReferentialIntegrityException`) when a commit deletes a node that
the persisted `:references` back-reference index still names —
a bounded index probe, paid only by commits that delete a
referenceable node. `WEAKREFERENCE` dangles by design (the JCR
spec's position). The load-bearing nuance: **the check guards only
the delete direction.** The add side is a literal no-op
(`ReferenceConstraint.test` returns `true` unimplemented,
`.../constraint/ReferenceConstraint.java:31-35`), and the three-way
rebase machinery sees add-ref-to-Y vs delete-X as disjoint paths —
so a session adding a reference to a just-deleted node's UUID
commits cleanly, and Oak mints exactly the dangling strong reference
vfs's race mints. Oak's design proves the general lesson twice over:
delete-side enforcement alone — which vfs's cascade already is —
cannot close the insert-vs-delete window.

### gel — deletion policies as triggers, and the same race unclosed

Read at 8519106. Gel's links offer the full declared-fate vocabulary
(`on target delete`: restrict / delete source / allow / deferred
restrict; `on source delete`: allow / delete target / delete target
if orphan — `edb/edgeql/qltypes.py:309-341`). But the enforcement is
**not** Postgres foreign keys: link tables carry no FK at all (a
`UNIQUE (source, target)` and a target index only,
`edb/pgsql/delta.py:5012-5098`); every policy compiles to a
hand-written `AFTER DELETE` constraint trigger scanning the link
table (`delta.py:6096-6330`), with "deferred restrict" riding real
`DEFERRABLE INITIALLY DEFERRED`. Crucially, the link-*insert* path
takes no lock on the target row — no `FOR KEY SHARE` anywhere in the
DML compiler — so Gel enforces only the delete side of the FK
protocol and leaves the insert-vs-delete TOCTOU window open, with no
comment acknowledging it. Two lessons: the *declared-fate vocabulary*
is good API prior art; and even a system with hard deletes did not
get the race closed by accident — closing it requires the
insert-side lock, deliberately.

### Postgres FK mechanics — the insert-side lock, precisely

Read at 74c7705. A real FK check on insert is exactly
`SELECT … FOR KEY SHARE` on the referenced row
(`src/backend/utils/adt/ri_triggers.c:624`, fast path
`ri_LockPKTuple` taking `LockTupleKeyShare` at `:3399-3402`). The
conflict rule (`src/backend/access/heap/README.tuplock`,
`heapam.c:3457-3489`): an UPDATE that modifies any column of a
non-partial, non-expression unique index is a "key update" and takes
`LockTupleExclusive`, which conflicts with `KEY SHARE`; an update
leaving key columns alone takes only `LockTupleNoKeyExclusive`,
which does not. This is exactly why our probe blocked: vfs's trash
rewrite updates `path`, which carries a full unique index, so the
rival delete is a key update and even the weakest share lock
serializes it. Under READ COMMITTED a genuinely gone referenced row
is a clean FK violation (SQLSTATE 23503, `ri_triggers.c:3831-3841`),
not a serialization error. The caveat that does not bite us: a rival
update touching only non-key columns slips past `KEY SHARE` — but
every path that de-lives an entry in vfs rewrites `path`. Postgres's
own answer to our exact question is: the insert-side lock is the
mechanism, and the weak shared flavor of it suffices when the rival
is a key update.

## The candidate fates, priced by the evidence

- **(a) Accept and document.** The tuple-store position. Costs
  nothing now; leaves the restore resurrection and poisons spec 136's
  in-degree signal the day it lands. The invariant battery's claim
  ("zero edge rows touching trashed ids") would need an honesty
  asterisk.
- **(b) Lock the endpoint entry rows in `mkedge_rows`.** The juicefs
  position, and what Postgres FKs do natively. One
  `with_for_update()` on the endpoint resolve — the guard shape
  `repair_edge_drift` already uses portably. Closes the race
  entirely. Open design questions for a spec: lock order (sorted
  entry ids, to avoid deadlock against delete's own claim order) and
  lock breadth at the 10k contract (up to 20k rows locked in one
  transaction; SQL Server lock escalation at ~5k locks needs a
  measurement).
- **(c) Sweep authored edges at restore.** One bounded delete inside
  the restore transaction (the ids are already in hand). Does not
  close the race — it makes the stray unobservable: while trashed it
  is invisible to every reader and dies at purge; at restore it is
  reaped. Cheap, but spec 136's signal pass would still count strays
  that sit in trash, unless it joins liveness (it should anyway).
- **(d) Teach reindex re-convergence to reclaim authored edges
  touching trashed entries.** The house doctrine ("drift is repaired
  at reindex, loudly") extended one clause: the collect pass already
  streams every entry; carrying the trash-scope fact per id and
  reclaiming authored rows that touch it is one more predicate.
  Heals within one reindex cycle rather than never; does not close
  the window itself.

(b) prevents; (c) and (d) heal; (a) documents. They compose: (b)
alone is complete; (d) is also independently justified as
defense-in-depth for any future mint-site bug, which is the same
argument the segment re-convergence already won.

## Sources

- The staged-race experiment and lock probe: this session,
  2026-09-04, against the `docker/compose.test.yml` engines
  (Postgres 17/pgvector, MariaDB 11.8, SQL Server 2025, Oracle 23ai
  Free) and sqlite+aiosqlite, on the tree at `65646e5`.
- Reference checkouts as listed in **Method**, each refreshed to its
  upstream default branch and license-checked 2026-09-04.
