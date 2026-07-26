# 029. Proof Obligations Are Structural, Not Disciplinary

- **Status:** accepted
- **Date:** 2026-07-26
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, in session — pre-accepted on the
  prior-art audit's recommendation after the 2026-07-26 landing review
  surfaced two new critical findings of the same recurring shape)
- **Context source:**
  `context/research/2026-07-26-prior-art-namespace-concurrency-audit.md`
  (the three-agent survey of linux/freebsd/plan9, juicefs/seaweedfs/
  jackrabbit-oak/agentfs, sqlalchemy/postgres/sqlite);
  `context/research/2026-07-26-writes-topology-review-verification.md`
  (the defect ledger the audit explains).

## Context

Successive review campaigns kept finding verified defects in the
storage backend — each individually small, all of one shape: **a proof
obligation held at a different site from the evidence that discharges
it.** The adopt arm forgot to re-register its parent bump (torn
namespace on Oracle); the staging-time `bumps` set went stale when
execution-time arbitration rewrote the plan; an exhausted Postgres
40001 classified differently from an exhausted `StaleSnapshot` because
a second classifier re-derived what the retry loop already knew; a
hand-predicted bind budget drifted from the compiled statement's
actual bind count (the MSSQL 1,049-row overflow).

The prior-art audit established three facts:

1. **The schema hybrid** (stable id + parent pointer + materialized
   path cache) is well-precedented for vfs's subtree-scan-dominated
   workload; every alternative trades away either rename-stable
   identity or sargable subtree queries.
2. **The redrive doctrine** (guarded statements, in-band stale signal,
   whole-method retry) is the consensus design — Postgres doctrine,
   SQLAlchemy's own machinery, Oak's and JuiceFS's retry loops all
   match it, and vfs is stricter than SQLAlchemy at every fork.
3. **No surviving system distributes namespace-coherence proofs across
   call sites.** Kernels take the parent lock at one choke point and
   check deadness under it; JuiceFS re-affirms the parent with an
   in-transaction affected-rows-verified UPDATE; Oak makes every
   child-add write the parent document so the engine's conflict
   detection catches a dead parent by construction. The systems
   without a structural guarantee (seaweedfs's unlocked rename,
   lib9p's unchecked createfile) exhibit exactly vfs's torn-namespace
   anomaly class.

## Decision

**The architecture stands; the enforcement moves.** The schema hybrid
and the redrive doctrine are ratified as-is. The concurrency model
keeps writes unserialized against topology — but every coherence proof
becomes structural: emitted by one builder or verified against one
authority, so that no future code path can omit it. Concretely:

### 1. Child-attaching mutations affirm their parent structurally

The one execution path that attaches children to a directory emits,
inside the same transaction, a verified write against the parent's row
(version bump or verified no-op touch). A parent that a rival trashed
or moved fails the child's own commit; the landed redrive recovers.
Per-method bump registration ceases to be an obligation anyone can
forget. This is the kernel `IS_DEADDIR`-under-the-lock pattern, the
JuiceFS affected-rows re-affirmation, and the Oak parent-touch,
translated to vfs's optimistic protocol.

### 2. Derived plan state is computed from final staged state

Any set derived from a `WritePlan` (today: `bumps`) is derived at
execution time from the staged rows' post-arbitration states — never
frozen at staging where arbitration can silently invalidate it.

### 3. Retry exhaustion has one classification channel

`with_retry` itself owns the exhausted-retryable outcome: whatever the
carrier (native serialization error or in-band `StaleSnapshot`), the
retry predicate's judgment survives to exhaustion as the single
semantic signal, classified once at the backend seam as a retryable
`conflict`. `classify_failure` handles only genuinely non-retryable
failures. This is Oak's normalize-before-the-loop shape and pgbench's
taxonomy (an exhausted serialization failure is still a serialization
failure).

### 4. Bind budgets are measured, not predicted

Chunk sizes for multi-row statements derive from the compiled
statement's actual bind registry (SQLAlchemy's insertmanyvalues
formula: fixed overhead = total binds − per-row width), through one
shared helper, with an execution-time budget assert so residual drift
fails loudly in development rather than at row 1,049 in production.

### 5. The path cache's fan-out cost is a documented contract

Large subtree moves are O(descendants) by design. The cost model is a
documentation obligation (ETL/operations docs state it, per ADR 025's
pattern); a hard refusal ceiling is deliberately **not** adopted now —
Oak's refuse-oversized-commits precedent is recorded as the shape to
adopt if production evidence demands one.

## Options considered

- **Serialize writes with topology** (take the per-mount lock for
  every write). Rejected: JuiceFS and Oak prove creates can run fully
  concurrent when the parent proof is structural; serializing would
  cost the agent-facing concurrency story for no correctness gain
  beyond decision 1.
- **Row-lock the parent on every create** (`SELECT … FOR UPDATE`, the
  literal kernel translation). Rejected for now: portable only as
  exclusive locks (no `FOR SHARE` on Oracle), so sibling creates in a
  hot directory would serialize; decision 1 buys the same guarantee
  optimistically at no hot-path cost. Revisit if guard-miss redrives
  become a measured contention problem.
- **Abandon the materialized path for inode+edge.** Rejected: forfeits
  the single-scan subtree read that vfs's primary workload depends on;
  the audit shows no surveyed system gets both, and vfs's hybrid
  already holds the better half for this workload.
- **Keep discipline, add review vigilance.** Rejected: three campaigns
  of empirical evidence show per-callsite discipline decays at exactly
  the rate new code paths appear; the audit's unanimous census is that
  survivors make the proof unforgettable, not the authors more
  careful.

## Consequences

- Spec 090 implements decisions 1–4 (and subsumes the open critical
  and major findings from the 2026-07-26 review rather than patching
  them).
- The write-builder layer becomes the single home of the parent
  affirmation; future persistence states (like `adopt`) inherit
  coherence by construction.
- `classify_failure` narrows; raw driver text can no longer reach a
  public result for a retryable race on any engine.
- A new statement-budget helper becomes the only lawful way to chunk
  multi-row statements; hand arithmetic at call sites is a review
  refusal.
- Documentation owes the fan-out cost model wherever bulk moves are
  described.

## Revisit trigger

Production telemetry showing sustained guard-miss redrive storms on
hot directories reopens the row-lock option; production evidence of
pathological giant moves reopens the hard ceiling (decision 5).
