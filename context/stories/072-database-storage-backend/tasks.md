# 072 — Tasks

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
- [ ] 10. Slice 7 — `descent.py` (ladder chokepoint + two-scope
      liveness prefix filter) + `reads.py` (read family, `parent_id`
      ls, prefix-LIKE tree, binary-collated order) + glob (escaped
      sargable LIKE); mask stamping; hand-declared capabilities;
      conformance suite gains the sqlite parametrization —
      read/glob families green.
- [ ] 11. Slice 8 — `writes.py`: write/edit/mkdir; dict-accumulate →
      bulk Core statements in pinned order; one transaction per
      batch, budget chunking, per-entry outcomes; revision stamp +
      WHERE guard + parent bump; upsert arbitration (MSSQL
      savepoint arm); key-byte-budget classification; designed-race
      savepoints. Mutation conformance rows green.
- [ ] 12. Slice 9 — `topology.py`: move/copy/delete under the
      serialization point (BEGIN IMMEDIATE / advisory lock at READ
      COMMITTED with root-walk ancestry re-check); trash-reparent
      with lazy buckets, ULID in-bucket names, restore-metadata
      columns, `/.vfs/trash/` path-cache prefix; `permanent=True`
      hard delete; move refusal order; copy = fresh ids/chains, zero
      edges.
- [ ] 13. Postgres CI leg (with slice 9): `postgres` marker + env
      URL + service wiring; conformance + topology/concurrency tests
      run under it; coverage posture for Postgres-only branches kept
      narrow.
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
- [ ] 18. Pack verb (`versions.py`, unblocked after task 15): batch
      rewrite to snapshot-interval + forward diffs, one transaction
      per chain, idempotent-cheap on unchanged watermark;
      byte-identical reconstruction before/after; corrupted-diff-row
      probe (blast radius ≤ interval).

## Pass C — grep + gram index

- [ ] 19. `models/postings.py`: delta+varint codec with
      numpy-vectorized decode (`uv add numpy`), property tests.
- [ ] 20. Slice 13 — `grep.py`: compile-first classification,
      folded-always planning, `unindexable_pattern` refusal naming
      `allow_scan`, scan/verify tier, rarest-first k=4 intersection,
      liveness/metadata join before content, unconditional `re`
      verification, runtime budgets + truncation flags, dirty
      overlay (`revision > watermark`, capped, visible); posting
      build path; capabilities + traits updated.
- [ ] 21. Slice 14 — reindex admin verb: new-epoch build, one-
      transaction compare-and-set pointer flip (expected-epoch guard;
      old-or-new harness row), three-part fingerprint, drop-and-rebuild on mismatch, idempotent-cheap
      watermark check, old-epoch reclamation step.
- [ ] 22. Endgame: `capabilities()` → `storage_ops(self)`; full
      acceptance-criteria audit (zero new suppressions); spec status
      → landed; STATUS.md true-up; 013/014/030/059–066 supersede
      notes verified. Session end: pytest/ruff/ty.
