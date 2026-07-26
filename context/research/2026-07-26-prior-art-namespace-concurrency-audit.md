# Prior-art audit: is the storage architecture on the right track?

- **Date:** 2026-07-26
- **Trigger:** recurring verified defects across review campaigns (086/087
  landing review found two new criticals) prompted a step-back question:
  are the bugs implementation slips, or the predicted output of a design
  choice? Three read-only research agents surveyed the prior-art
  checkouts; this memo consolidates their findings and the synthesis.
- **Sources surveyed** (all `~/Git/Repos/`, read-only): `linux`,
  `freebsd-src`, `plan9`/`plan9port`, `pjdfstest`; `juicefs`,
  `seaweedfs`, `jackrabbit-oak`, `agentfs` (`libsqlfs` README only —
  LGPL, code not read); `sqlalchemy`, `postgres`, `sqlite`.

## Synthesis: three pillars, two validated, one at an unoccupied point

vfs's storage design rests on three pillars. Prior art validates two of
them outright and shows the third is the sole source of the recurring
bug class — and that it is one structural rule away from the shape every
surviving system converged on.

**Pillar 1 — the schema hybrid (stable id + parent pointer + materialized
path cache): validated for this workload.** The census splits cleanly:
materialized-path systems (seaweedfs filer, oak DocumentNodeStore,
libsqlfs) get sargable subtree scans and pay O(subtree) rename;
inode+edge systems (juicefs, agentfs) get O(1) rename and pay
per-component resolution with no single-scan subtree query. Nobody gets
both from one structure. vfs's hybrid is unique but coherent: identity
survives rename (better than every path-keyed system) and subtree
grep/glob/tree is one indexed `LIKE` scan (better than every edge
system) — and subtree enumeration is vfs's primary read pattern. Oak's
depth-prefixed path keys exist for exactly this sargability reason. The
accepted cost, per oak's precedent, is that very large subtree moves are
expensive and eventually operationally bounded — oak *refuses* oversized
commits rather than weakening atomicity.

**Pillar 2 — the redrive doctrine (guarded statements, in-band stale
signal, whole-method retry, bounded backoff): validated; it is the
consensus design.** Postgres doctrine mandates whole-transaction retry
including the logic that decided which SQL to issue
(`doc/src/sgml/mvcc.sgml:1778-1841`) and deliberately offers no
automatic retry; SQLAlchemy's FAQ says the same and its `version_id_col`
machinery is a strict subset of vfs's guard ladder (rowcount-only
verification, warn-and-proceed on insane rowcounts where vfs refuses
`unsupported`; `lib/sqlalchemy/orm/persistence.py:833-963`); oak
implements exactly the loop shape (12 jittered attempts, then a merge
lock; `DocumentNodeStoreBranch.java:119-229`); juicefs sizes the same
loop at 50 attempts (`pkg/meta/sql.go:1198-1267`). vfs's SQLite writer
discipline (`BEGIN IMMEDIATE`; BUSY retryable, BUSY_SNAPSHOT a loud
bug) matches upstream doctrine precisely (`sqlite/src/wal.c:3696-3733`,
`doc/wal-lock.md:47-82`).

**Pillar 3 — plain writes unserialized against topology verbs, coherence
by optimistic per-row version guards assembled per method: the outlier.**
The kernel census is unanimous: no kernel commits a child-attach without
holding the parent's lock exclusively at commit time
(`linux/Documentation/filesystems/locking.rst:100-112` — only *lookup*
is shared; single choke point `__start_dirop`, `fs/namei.c:2901-2920`).
Kernel optimism exists only on the read/probe side (RCU-walk seqcounts,
FreeBSD `vn_seqc`, ERELOOKUP), always with a locked-commit fallback, and
always bumped at a single structural choke point (`__d_move` under
`rename_lock`). The DB-backed census is equally unanimous: every
surviving system makes parent liveness a property the database enforces
atomically at commit — juicefs re-affirms the parent with an in-txn
UPDATE whose affected-rows must be 1 (`pkg/meta/sql.go:1925-1938`); oak
makes every child-add write the parent document so the engine's own
conflict detection catches a deleted parent
(`Commit.java:524-545,609-617` — a comment states the parent-touch
exists "to enable hierarchy conflict detection"); juicefs-redis puts the
parent key in the WATCH set. The two systems that neither serialize nor
structurally check are the cautionary tales: seaweedfs's rename is
unlocked and non-atomic on most backends (torn subtrees are permanent
and undocumented; `weed/server/filer_grpc_server_rename.go:134-302`),
and lib9p's `createfile` never checks the parent is still attached — it
is safe only because the default srv loop is single-threaded
(`plan9port/src/lib9p/file.c:137-198`, `srv.c:721-742`).

**The determination.** vfs's recurring bug class — a missed bump, a
missed guard, a missed re-collection producing a torn namespace — is the
predicted steady-state of pillar 3 as currently formulated: proof
obligations discharged by per-callsite discipline at N sites, where
every prior-art survivor discharges them by structure at one site. The
fix is not serializing writes (juicefs and oak both let creates run
fully concurrent) and not a rebuild: it is relocating the guard into the
one builder that attaches children, so a create *cannot commit* unless
its parent's row survives the same atomic commit. vfs's "create bumps
the parent version" is already most of this mechanism; what is missing
is the structural guarantee that no child-attaching mutation can be
built without the affirmed parent write.

## The meta-defect, named

Every verified critical/major across the campaigns reduces to one
shape: **a proof obligation held at a different site from the evidence
that discharges it.**

1. *Parent liveness* — proved by a version bump each code path must
   remember to register (the adopt arm forgot; earlier, delete's rewrite
   list and the overwrite destroy had the same shape). Kernels make this
   unforgettable via lock acquisition; juicefs/oak via a mandatory
   parent write inside the commit.
2. *Plan-derived state* — `WritePlan.bumps` is derived at staging time,
   then execution-time arbitration rewrites staged rows (absorb/adopt)
   and the derived set silently goes stale. Derived sets must be
   re-derived from final staged state at execution.
3. *Retry classification* — the predicate in `with_retry` knows an
   exception is a retryable conflict, but exhaustion lets a different
   classifier (`classify_failure`, no memory of that decision) emit
   `unavailable` + raw driver text for Postgres 40001 while
   `StaleSnapshot` exhaustion emits clean retryable `conflict`. Oak
   normalizes both channels into one classification *before* the loop
   and exhaustion preserves it; pgbench counts an exhausted
   serialization failure as a serialization failure
   (`src/bin/pgbench/pgbench.c:386-427`).
4. *Bind budgets* — chunk sizes predicted by hand arithmetic at each
   callsite drift from compiled reality (the 1,049-row MSSQL overflow:
   `2n+1` binds vs a `//2` budget). SQLAlchemy's insertmanyvalues counts
   binds on the compiled statement and derives fixed overhead as
   `total - per_row` (`lib/sqlalchemy/sql/compiler.py:5859-5877`) at one
   chokepoint.

## Hardening program suggested by the audit

In priority order; items 1 and 4 subsume the open critical findings
rather than patching them:

1. **Structural parent affirmation.** Every mutation that attaches a
   child emits, from the one insert/write builder, a verified write
   against the parent row in the same transaction (bump or no-op touch,
   affected-rows/RETURNING-verified). Per-method bump registration goes
   away as an obligation; a concurrently trashed or moved parent fails
   the child's own commit and the redrive recovers. (Kernel `IS_DEADDIR`
   under the lock; juicefs affected-rows==1; oak parent-touch.)
2. **Derive execution-time sets from final staged state.** `bumps` (and
   any future derived set) computed after arbitration, from the staged
   rows' final persistence states — never frozen at staging.
3. **One retry-exhaustion channel.** `with_retry` converts an exhausted
   retryable outcome (native or in-band) into the single semantic
   signal (StaleSnapshot or a RetryExhausted carrying the cause and
   attempt count); `classify_failure` shrinks to genuinely
   non-retryable failures.
4. **Measured bind budgets.** One shared chunk-size helper that compiles
   a probe statement on the live dialect, counts `bind_names`, and
   derives per-row width and fixed overhead — SQLAlchemy's formula
   generalized — plus an execution-time assert that any compiled
   statement fits the budget.
5. **A declared subtree-move ceiling** (or documented cost model) for
   very large moves, per oak's refuse-oversized-commits precedent; the
   fan-out stays inside one chunk-budgeted transaction always.

## Full agent memos

The three source memos (kernel namespace locking; DB-backed filesystem
metadata census; OCC/retry/bind-budget doctrine) contain the complete
citation trails backing every claim above. Key anchors:

- Kernels: `linux/fs/namei.c:1796-1799` (dead-dir check after lock),
  `:2901-2920` (`__start_dirop`), `:5339-5381` (`vfs_rmdir` sets
  `S_DEAD`), `:5895-6018` (rename doctrine + global mutex);
  `Documentation/filesystems/directory-locking.rst:130-248` (the lock
  proof); `freebsd-src/sys/kern/vfs_syscalls.c:3866` (`mnt_renamelock`),
  `sys/ufs/ufs/ufs_vnops.c:1304-1395` (relock-and-reverify);
  `pjdfstest` pins postconditions only, nothing concurrent.
- DB filesystems: `juicefs/pkg/meta/sql.go:65-93` (node+edge schema),
  `:1795-1809,1925-1938` (parent liveness in-txn), `:2292+` (O(1)
  rename); `seaweedfs/weed/filer/abstract_sql/abstract_sql_store.go:171-284`
  (path-keyed), `weed/server/filer_grpc_server_rename.go:134-302`
  (unlocked O(subtree) rename); `jackrabbit-oak` `Commit.java:524-545`
  (parent-touch), `NodeDocument.java:1174-1221` (conflict unit),
  `Utils.java:352-380` (depth-prefixed path keys);
  `agentfs/sdk/rust/src/connection_pool.rs:14` (global single writer).
- OCC/retry: `sqlalchemy/lib/sqlalchemy/orm/persistence.py:746-963`
  (version_id_col), `lib/sqlalchemy/sql/compiler.py:5859-5877`
  (insertmanyvalues bind accounting);
  `postgres/doc/src/sgml/mvcc.sgml:1778-1841` (retry doctrine),
  `src/backend/utils/errcodes.txt:328-334` (40001 is semantic, not
  transport); `sqlite/src/wal.c:3696-3733` (BUSY_SNAPSHOT vs BEGIN
  IMMEDIATE).
