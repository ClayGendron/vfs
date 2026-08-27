# 025. Whole-Batch Conflict Re-Drive Stands; One Batch Writer per Subtree

- **Status:** accepted 2026-07-23 — raised by the multi-agent review
  of the spec 079 landing (scale lens filed the re-drive cost as a
  finding; verification downgraded it to a design question); decided
  by Clay in session.
- **Date:** 2026-07-23
- **Deciders:** Clay Gendron
- **Context source:** spec 079's aggregate rung: on
  `rowcount != N` the savepoint rolls back and the whole guarded set
  re-drives row-by-row for exact blame — one rival increment in a 10k
  batch costs O(batch) per-row statements on the engines that ride
  the aggregate arm (sqlite, mysql family, oracle).

## Decisions

### 1. The whole-batch re-drive is the chosen design, not a defect

The conflict path exists for correctness, not throughput: it runs
only on batches that actually contain a conflict, it produces exact
per-row blame (the stale rows classify `conflict`; every fresh row
lands exactly once), and its costs were measured and accepted in
spec 079's plan. No chunked-savepoint or bisecting optimization lands
without production evidence that conflict-carrying large batches are
common — complexity spent on a hypothesis is the wrong trade.

### 2. The operating doctrine: one batch writer per subtree

Bulk ETL against a vfs mount is expected to run as **one batch
writer per mount, or one batch writer per disjoint subtree of the
file tree**. Concurrent agents doing small guarded writes are the
designed-for case; two bulk pipelines racing over the *same* rows are
a pipeline-management problem, not a vfs tuning problem. Under this
doctrine the re-drive is rare correctness machinery — a batch that
triggers it frequently is mispartitioned.

### 3. The doctrine is a documentation obligation

Every future operations/integration document that describes bulk
writes (ETL guides, deployment docs, backend README material) must
state the one-batch-writer-per-subtree expectation and what happens
when it is violated: correctness is preserved, cost degrades to
per-row on the conflicted batch.

## Revisit trigger

Production telemetry showing frequent conflicts *inside large
batches* despite partitioned writers reopens decision 1; the cheaper
design (chunked savepoints bounding the re-drive to conflicted
chunks, per `_catch_retry_layer`'s pattern) is sketched in the
2026-07-23 review record.
