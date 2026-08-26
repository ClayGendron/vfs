# 102 — Set-based scattered delete: shrink the topology-lock hold

- **Status: researched 2026-08-25** — slice A delivered as
  `../../../research/2026-08-25-set-based-scattered-delete.md`: the five research questions answered on all five engines — the per-target bumps are the measured cost, a set-based prototype holds the lock 24–40× shorter on four engines (7.6× on MSSQL, whose residual is the snapshot IN-list fetch) with byte-for-byte parity, the range predicate proven sargable where LIKE is not, cross-transaction chunking not needed. Design (slice B) waits on
  Clay's review of the memo.
- **Status: draft 2026-08-14, research-first** — born from the
  open-questions entry "Scattered 10k-target delete holds the
  topology lock for minutes", scheduled by Clay in session
  2026-08-14 ("research this soon and create a spec"). No
  implementation until the research questions below are answered on
  real engines.
- **Date:** 2026-08-14
- **Owner:** Clay Gendron
- **Kind:** latency work under the topology lock — batch-shape
  change to the trash-everything delete arm, correctness contract
  unchanged.
- **Depends on:** the 081–083 trash arc (the arm being reshaped),
  spec 086 (two-sided guards — any reshaped statement keeps its
  guard discipline), ADR 025 (single-batch-writer doctrine and the
  redrive posture the lock hold interacts with).
- **Relates to:** spec 080 (the MySQL per-row executemany cost —
  any set-based reshape here must not regress into that trap);
  spec 101 (removes the move-arm purge; delete's trash arm is
  untouched by it).

## Problem

Trash-everything delete runs ~4 statements per target inside one
serialized topology transaction: a scattered 10k-target batch
measured 52.9 s on Postgres while blocking a rival move for 51.9 s,
and ~2 minutes on MSSQL (b16c38b review, scale lens). Not a
correctness defect — batches stayed atomic and the set-based bulk
escape (cascade delete of one holding directory) is documented — but
minutes-long topology-lock holds starve every rival topology verb,
and 10k-target batches are a supported contract, not an edge case.

The recorded direction: **set-based scattered execution** — group
targets per trash bucket, then one reparent executemany plus one
path-rewrite pass per bucket, replacing the per-target statement
quartet. Cross-transaction chunking (weaker batch atomicity) is the
fallback shape if set-based execution cannot hold the contract.

## Research questions (answer before designing)

1. **Where do the 4-statements-per-target actually go?** Profile the
   current arm on Postgres and MSSQL at 1k/10k scattered targets —
   per-statement timing, so the reshape targets the measured cost,
   not the assumed one.
2. **Can the reparent go set-based on every declared engine?** The
   move is per-target (each target gets its own trash-bucket
   address); a VALUES-join UPDATE serves Postgres/MSSQL
   (`values_join`), but the MySQL family loops executemany UPDATEs
   per row (spec 080's finding) and Oracle needs its own
   verification. What does each engine's best set-based spelling
   look like, and what does it measure?
3. **Does the path-rewrite pass fuse?** Descendant path rewrites
   currently ride per-target; a per-bucket rewrite keyed on the old
   prefix set may fuse into one statement per chunk — does it stay
   sargable, guard-disciplined, and inside bind budgets at 10k?
4. **What does the lock-hold curve look like after?** Re-run the
   b16c38b rival-blocking measurement on the reshaped arm — the
   acceptance number is the rival's blocked time, not the batch's
   elapsed time.
5. **Is cross-transaction chunking needed at all?** Only if
   set-based execution cannot get the hold under an acceptable
   bound; chunking weakens batch atomicity and needs its own
   redrive/partial-result story, so it enters only with numbers
   proving the need.

## Acceptance criteria

- The scattered 10k-target delete's topology-lock hold drops by an
  order of magnitude on Postgres and MSSQL (measured, recorded in
  the research memo), with MySQL/Oracle at parity or better than
  today.
- Batch atomicity, two-sided guard discipline, trash restorability,
  and result attribution are byte-for-byte contract-identical —
  pinned by the existing trash conformance rows plus a
  scattered-scale row.
- No statement grows unboundedly with batch size (chunked by the
  declared budgets); the four Docker legs run the scale row green.

## Slices

- **A** — research memo: the profile, per-engine set-based
  spellings, measured curves (questions 1–4); Clay reviews before
  any design lands.
- **B** — design + implementation per the memo's findings; spec
  updated from draft to shaped at that point.
