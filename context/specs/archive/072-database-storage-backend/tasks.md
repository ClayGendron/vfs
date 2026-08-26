# 072 — Tasks

> **Citation map (2026-07-16 reorg):** this spec's research memos moved to
> `context/research/` under dated names. Bare citations below resolve as:
> `research.md` → `2026-07-13-database-storage-backend.md` ·
> `research-grep-index.md` → `2026-07-13-database-storage-grep-index.md` ·
> `research-pipelines-brief.md` → `2026-07-13-database-storage-pipelines-brief.md` ·
> `research-read-pipeline.md` → `2026-07-13-database-storage-read-pipeline.md` ·
> `research-write-pipeline.md` → `2026-07-13-database-storage-write-pipeline.md` ·
> `research-posting-storage.md` → `2026-07-14-database-storage-posting-storage.md`


Ordered; every task leaves the suite green (`uv run pytest tests/ -q`,
`ruff`, `ty`). Slice numbers refer to plan.md sections.

## Prerequisite

- [x] 1. ADR 059: `context/decisions/004-stable-node-identity.md` —
      ULID logical identity + integer surrogate, `parent_id`
      structural pointer, path as regenerable cache; pointer in the
      story-059 slot; spec status line updated.

## Stage 1 — seam ripples (no DB code)

- [x] 2. `models/entry.py`: `revision` on `Entry`/`Observation`;
      `populated: frozenset[str]` mask on `Observation`;
      `results/projection.py` mask-driven; render excludes the mask.
- [x] 3. `backends/memory.py`: stamp `revision` (monotone counter,
      unconditional parent bump) and `populated` on every
      observation.
- [x] 4. `storage/protocol.py`: `allow_scan` on grep +
      `SupportsTraits` + `TRAIT_KEYS`; `params.py` ingress row;
      memory backend `allow_scan` no-op + `traits()`.
- [x] 5. `results/envelope.py`: orthogonal `retryable` flag (057
      ripple), default False, tests pin it never renders.
- [x] 6. `models/code_grams.py`: per-codepoint-NFC fold fix +
      always-plan-folded guard; tests pin both false-negative cases.
- [x] 7. Extract `tests/storage_conformance.py` (backend-factory
      fixture, per-family capability opt-in, R8 error-ordering
      matrix, mask assertions); `test_storage_conformance.py` runs
      it over memory only; `test_backends_memory.py` shrinks to
      memory-specific tests.
- [x] 8. `models/rows.py` → target schema: narrow `entries`
      (`node_id` ULID + surrogate PK + `parent_id` + path cache +
      `revision` + restore-metadata columns, UNIQUE(parent_id,
      name)), `content`, `versions`, `chunks` (ID-keyed, embedding
      moves here), `edges` (ID-keyed), single-row
      `meta` (`SCHEMA_FORMAT_VERSION`, `mount_identity`),
      `posting_list` (varint default, epoch); delete `gram_staging`
      + `GramStagingRow`; binary collation per dialect; drift test +
      `ENTRY_ROW_ONLY_COLUMNS` updated. `uv add python-ulid`.
- [x] 8a. Stage-1 pressure test remediated and ruled
      (pressure-findings-stage1.md): findings 1.1–1.4 implemented;
      rulings 2.1–2.6 landed — mask-driven merge with revision
      agree-or-null, rename refusal order, raw folded gram stream +
      Turkic-i fold, MSSQL UTF-8 collation (2019+ floor),
      order-independent batch semantics + per-target `error.data`,
      `MAX_TABLE_NAME_LENGTH` bound. Posting persistence research in
      research-posting-storage.md with §6/§8 pins (CAS epoch flip,
      byte-capped sorted bulk insert, pre-fetch `byte_size` guard).

## Pass A — files and directories

- [x] 9. Slice 6 — `backends/database/` skeleton: `dialects.py`
      (policy only — retryable classifier, settings, isolation, key
      byte budgets; facts SQLAlchemy models are read off the dialect:
      `insertmanyvalues_max_parameters`, `is_disconnect`; unknown
      dialects serve on a generic floor, never refused),
      `engine.py` (construction XOR, first-touch with schema-version
      row under the serialization point, per-session settings, retry
      + backoff, `close()`), `backend.py` stub. Tests: restart
      rebind, cross-loop first touch, version-mismatch refusal,
      concurrent first touch, borrowed-pool close. New kind
      `vfs.unavailable.schema` for the mismatch refusal. Slice-6
      pressure test: 2 confirmed findings remediated — half-provisioned
      database (rows but no meta) now a classified refusal, not a raw
      `NoResultFound`; SQLite session settings stamp every pool checkout
      so pre-borrow pooled connections are covered. ADR-002 conformance
      restored post-landing: the borrowed handle is an injected session
      factory (the bare `engine=` kwarg the ADR removed had crept back);
      dialect policy resolves from the session bind at first use, all IO
      flows through sessions, and a borrowed host never holds an engine
      (pinned by tests).
- [x] 10. Slice 7 — `descent.py` (ladder chokepoint + two-scope
      liveness prefix filter) + `reads.py` (read family, `parent_id`
      ls, prefix-LIKE tree, binary-collated order) + glob (escaped
      sargable LIKE); mask stamping; hand-declared capabilities;
      conformance suite gains the sqlite parametrization. Note: the
      read-family conformance rows stay capability-skipped until
      slice 8 supplies write/mkdir fixtures — slice 7's verification
      is the seeded-Core read tests in `test_backends_database.py`.
      Pressure-tested (12 dimensions, adversarially verified): two
      confirmed findings fixed and pinned — descent through a trashed
      row leaked its kind (`classify_misses` now carries the trash
      scope; trash misses classify uniformly), and pool exhaustion
      leaked a raw `sqlalchemy.exc.TimeoutError` (catch widened to
      `SQLAlchemyError`). Precedent review (four-agent reference
      sweep) confirmed the ladder, listing shapes, mask contract, and
      prefilter/verify structure against Linux/FreeBSD/JuiceFS/
      statx/zoekt; the one contract-level deviation found (fnmatch
      glob semantics) is story 073's charter, decided 2026-07-14.
- [x] 11. Slice 8 — `writes.py`: write/edit/mkdir; dict-accumulate →
      bulk Core statements in pinned order; one transaction per
      batch, budget chunking, per-entry outcomes; revision stamp +
      WHERE guard + parent bump; upsert arbitration (MSSQL
      savepoint arm); key-byte-budget classification; designed-race
      savepoints. Mutation conformance rows green. Landed 2026-07-16
      (`b488e25`); membership predicates budget-bounded same window
      (`d9ca522`). Subsequently rewritten in place by specs 074
      (per-entry revisions replace the ordered counter, `7f152af`),
      075 (trash scope retired for meta-scope parity, `44aa439`),
      and 076 (entry model split; version rows minted in the write
      transaction, `40408da`).
- [x] 12. Slice 9 — `topology.py`: move/copy/delete under the
      serialization point (BEGIN IMMEDIATE / advisory lock at READ
      COMMITTED with root-walk ancestry re-check); trash-reparent
      with lazy buckets, ULID in-bucket names, restore-metadata
      columns, `/.vfs/trash/` path-cache prefix; `permanent=True`
      hard delete; move refusal order; copy = fresh ids/chains, zero
      edges. **Design settled 2026-07-23** — full orientation and
      per-engine serialization design recorded in
      `slice-9-topology-guide.md`; start there. Prerequisite spec
      079 (statement-attributed guarded updates) landed the same
      day with all four Docker engine legs green. **Gate (owner
      decision 2026-07-23): the concurrency-pin seam decision in the
      guide ("Decide before implementing") must be made before
      implementation starts — resolved the same day: code owns the
      seam (see the guide's decision note).**
      **Landing 1 of 2 built 2026-07-23**: serialization
      infrastructure (`topology_execution_options`, MySQL topology
      pin, public `advisory_key` + `EngineHost.topology_key`), the
      concurrency-seam module (`seams.py`; write-path and delete
      seams live; torn-row pin refactored off the private mirror
      onto the public verb), and `delete` (trash reparent, hourly
      buckets, descendant rewrite, permanent purge). Ten delete
      conformance rows enforced; all four Docker legs green (an
      MSSQL `SELECT EXISTS` refusal was caught live and fixed to a
      one-row probe); coverage 100%.
      **Landing 2 built 2026-07-23, completing the slice**:
      `transfer_rows` (one shared move/copy pair ladder mirroring
      `memory._transfer` row for row — overlap refusals against the
      committed snapshot, live per-pair reads, exists-before-cycle,
      cycle-before-kind, byte-overflow refusal), move as reparent +
      descendant rewrite + restore gesture, copy as fresh-ULID mint
      (no edges, no `external_id`, occupant keeps identity). All ~36
      topology conformance rows enforced; four Docker legs green
      (101/101/101/100); coverage 100%. The
      create-under-trashed-directory race is filed in
      `open-questions.md` per the guide.
- [ ] 13. Postgres CI leg (with slice 9): `postgres` marker + env
      URL + service wiring; conformance + topology/concurrency tests
      run under it; coverage posture for Postgres-only branches kept
      narrow. Revision allocation (owner decision 2026-07-16, driven
      by the many-writers-per-mount deployment): slice 8's portable
      meta-row counter serializes writers per mount on Postgres/MSSQL
      (lock held allocation→commit, defeating group commit) — this
      slice replaces it there with native sequences (`nextval` range /
      `sp_sequence_get_range`) behind the slice-8 allocation seam.
      Sequences break allocation-order = commit-order, which only the
      Pass C index watermark consumes: reindex must then capture its
      watermark under a brief per-mount shared/exclusive fence
      (writers shared, reindexer momentarily exclusive) instead of
      assuming ordered commits. **Superseded note (2026-07-20):** the
      revision-allocation half of this task is dead — ADR 013 / spec
      074 removed ordered allocation and the counter row entirely
      (`7f152af`); no sequence replacement is needed, and the index
      watermark premise it served is gone (the flags are the grep
      overlay's dirty set). The CI-leg half (Postgres marker, env
      URL, service wiring, conformance under Postgres) stands.
- [ ] 14. Pass A close-out: two-instance cycle test, crash-rollback
      consistency, WAL-baseline and metadata-write-amplification
      checks; acceptance-criteria audit; STATUS.md + spec status;
      `docs/home.md` backend note. Session end: pytest/ruff/ty.

## Pass B — meta namespace and graph

- [ ] 15. Slice 10 — `versions.py`: store-full on write (diff-free
      path), identical-hash short-circuit, `reconstruct_version`
      reads, hash verify on write + reconstruction → corruption
      kind; `__meta__` version/chunk endpoint mapping via `paths.py`;
      direct-address-vs-enumeration harness row.
- [ ] 16. Slice 11 — restore + sweep admin verbs: move-shaped
      restore (conflict on collision, `not_found` on dead parent);
      idempotent resumable sweep deleting all row families, edges
      both directions; harness rows.
- [ ] 17. Slice 12 — edges + `mkedge` (completes the mutation
      family) + recursive-CTE `graph` with budgets/truncation;
      liveness joins (trashed endpoint invisible; sweep leaves no
      dangling edge). Session end: pytest/ruff/ty; STATUS.md.
      **Reshaped note (2026-07-20):** ADR 018 (accepted 2026-07-19)
      redesigned this surface — batch-native `mkedge`/`rmedge`,
      touch/upsert semantics, materialized reserved-type fs edges
      minted in the namespace-mutating transactions, `parent_id`
      kept as write-side arbiter. This slice waits on ADR 018's
      wiring spec (which also owns user-edge fate on delete, pin 9)
      rather than the shape sketched here.
- [ ] 18. Pack verb (`versions.py`, unblocked after task 15): batch
      rewrite to snapshot-interval + forward diffs, one transaction
      per chain, idempotent-cheap on unchanged watermark;
      byte-identical reconstruction before/after; corrupted-diff-row
      probe (blast radius ≤ interval).

## Pass C — grep + gram index

Discharged by spec 093 (all four slices landed 2026-08-05; the
watermark framing below was superseded by ADR 013's flag-partitioned
overlay — see 093's *Corrections*).

- [x] 19. `models/postings.py`: delta+varint codec with
      numpy-vectorized decode (`uv add numpy`), property tests.
- [x] 20. Slice 13 — `grep.py`: compile-first classification,
      folded-always planning, `unindexable_pattern` refusal naming
      `allow_scan`, scan/verify tier, rarest-first k=4 intersection,
      liveness/metadata join before content, unconditional `re`
      verification, runtime budgets + truncation flags, dirty
      overlay (`revision > watermark`, capped, visible); posting
      build path; capabilities + traits updated.
- [x] 21. Slice 14 — reindex admin verb: new-epoch build, one-
      transaction compare-and-set pointer flip (expected-epoch guard;
      old-or-new harness row), three-part fingerprint, drop-and-rebuild on mismatch, idempotent-cheap
      watermark check, old-epoch reclamation step.
- [x] 22. Endgame: `capabilities()` → `storage_ops(self)`; full
      acceptance-criteria audit (zero new suppressions); spec status
      → landed; STATUS.md true-up; 013/014/030/059–066 supersede
      notes verified. Session end: pytest/ruff/ty.
