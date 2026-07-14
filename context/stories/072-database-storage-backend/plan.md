# 072 — Plan: `DatabaseStorage` on the composed seam

Implements the spec's resolved shape (§§1–12) as **one prerequisite,
one pre-backend stage, and the three delivery passes**, each pass cut
into session-sized slices that land green independently. The spec's
passes are the landing units; the slices below are the working units.

**Prerequisite:** ADR 059 — the identity decision record binding
option (c) — must land before any Stage-1 code. Recommended home:
`context/decisions/004-stable-node-identity.md` (decisions live in
`context/decisions/`), with the reserved story-059 slot recording a
pointer; the ADR pins ULID-as-logical-identity + integer surrogate
key, `parent_id` as the one structural pointer, and path as
regenerable cache, citing `research.md` §1.

## Sequencing rationale

Roughly half of Pass A's surface never touches a database: the
revision/mask model ripple, the protocol ripples, the `code_grams.py`
bug fixes, the conformance-harness extraction, and the `rows.py`
schema rewrite are all independently-green chunks with their own
tests. Landing them first (Stage 1) means `DatabaseStorage` arrives
into a tree where its schema, its seam, and its test suite are
already settled — each backend slice then just implements verbs and
flips conformance rows green.

## Decisions pinned here (the spec delegated these to plan.md)

1. **Capability-traits shape (049 ripple).** A new optional protocol
   in `storage/protocol.py`:

   ```python
   @runtime_checkable
   class SupportsTraits(Protocol):
       def traits(self) -> Mapping[str, str]: ...
   ```

   Key vocabulary as a module-level `Literal` + frozenset
   (`TRAIT_KEYS`): `grep_tier` (`indexed` / `scan`), `grep_staleness`
   (`none` / `watermark`), `revision_encoding` (`counter64`),
   `durability` (`full` / `relaxed`), `arbitration` (`upsert` /
   `catch_retry`). `InMemoryStorage` declares its honest values
   (`scan`, `none`, `counter64`, n/a-omitted keys allowed — absent
   key = trait not declared). The router does not consume traits yet;
   surfacing via `mounts()`/`MountInfo` is a recorded follow-up.
2. **Capabilities per pass.** `storage_ops(self)` cannot be honest
   mid-story (Pass A ships glob-without-grep, and the mutation family
   without `mkedge` — family derivation would over-declare).
   Mechanism: `DatabaseStorage.capabilities()` returns a
   hand-declared frozenset per pass; unlanded verbs simply do not
   exist as methods. When Pass C completes the surface, the body
   becomes `storage_ops(self)` and the §1 claim comes true.
3. **Module layout.** A package, not a god-file (`memory.py` is 678
   lines; this backend is several times that):

   ```
   src/vfs/storage/backends/database/
     __init__.py   — re-export DatabaseStorage
     dialects.py   — per-dialect declared data: parameter budget, key
                     byte budget, retryable-error classifier
                     (SQLSTATE/errcode), per-session settings,
                     isolation pins, collation names
     engine.py     — construction XOR, first-touch (create_all +
                     schema-version row under the topology
                     serialization point), close(), retry-with-
                     backoff wrapper
     descent.py    — the shared descent ladder / classification
                     chokepoint (R8) + the liveness prefix filter
     backend.py    — the DatabaseStorage class: protocol verbs, admin
                     verbs, capabilities/traits
     reads.py      — read-family + glob statement builders
     writes.py     — write/edit/mkdir batch planning, revision
                     stamping, parameter-budget chunking
     topology.py   — move/copy/delete/trash statement builders +
                     under-lock re-checks
     versions.py   — version rows, reconstruction, pack (Pass B/C)
     grep.py       — gram planner integration, posting intersection,
                     dirty overlay, scan/verify tier (Pass C)
   ```

   Transaction ownership maps onto the split (spec W5): only
   `backend.py`'s protocol/admin methods open and commit; every
   helper module takes an `AsyncConnection` and builds/executes
   statements, never begins or commits.
4. **Dependencies.** `python-ulid>=2` and `numpy` become core
   dependencies (owner-approved 2026-07-13) — node identity, and the
   vectorized delta+varint decode the spike priced (~125M values/s).
   ulid arrives with the Stage-1 schema chunk, numpy with the Pass C
   codec. Postgres tests ride the existing `postgres` extra (asyncpg).
5. **Posting codec home.** New `src/vfs/models/postings.py`:
   `encode_postings` / `decode_postings` (delta+varint), doc-count
   and byte-size helpers, encoding-tag dispatch. Schema constants
   stay in `rows.py`.
6. **Conformance suite layout.** `tests/storage_conformance.py` — a
   backend-agnostic suite module (like `base_doubles.py`, importable
   via the tests pythonpath) holding the contract tests, parametrized
   by a backend-factory fixture with per-family opt-in from declared
   capabilities. `tests/test_storage_conformance.py` instantiates it
   over `memory`, `sqlite`, and marker-gated `postgres`.
   `test_backends_memory.py` shrinks to memory-specific behavior;
   `tests/test_backends_database.py` holds DB-specific tests
   (lifecycle, locks, WAL, budgets, concurrency).
7. **Observation mask shape.** `Observation` gains
   `populated: frozenset[str]` (excluded from rendering) plus
   `revision: int | None`; `Entry` gains `revision` (backend-owned —
   stamped on the way out, never trusted on ingress). Harness
   assertion: `populated == requested ∪ {"path", "kind", "revision"}`.

## Stage 1 — seam ripples, no DB code (five chunks)

### 1. Revision + Observation mask (live-model ripple)

- `models/entry.py`: `revision` on `Entry` and `Observation`;
  `populated` mask on `Observation` (decision 7).
- `results/projection.py`: the `all` sentinel and column narrowing
  become mask-driven (union of `populated`) instead of
  getattr-is-not-None; identity fields always-on.
- `backends/memory.py`: stamps `revision` (per-instance monotone
  counter, parent bump on namespace mutations, unconditional parent
  increment) and `populated` on every observation — the shared
  harness must hold for both backends.
- Render: `populated` never renders; existing snapshots unchanged.

### 2. Protocol ripples

- `storage/protocol.py`: `allow_scan: bool = False` on
  `SupportsPatternSearch.grep`; `SupportsTraits` (decision 1).
- `params.py`: `allow_scan` ingress row for grep (071's table).
- `backends/memory.py`: accepts `allow_scan` as a no-op (already
  scan-tier); implements `traits()`.
- `results/envelope.py` (057 ripple): orthogonal `retryable: bool`
  flag on the error side of the envelope, default False, set by
  backends whose classifier says the condition is retryable.

### 3. `code_grams.py` prerequisite fixes

The two confirmed §6 prerequisites, independent of everything else:
the per-codepoint-NFC fold false-negative fix, and the guard that
planning always runs folded regardless of case mode
(`research-grep-index.md` §5). Tests pin both.

### 4. Conformance harness extraction

- Extract the behavior contract from `test_backends_memory.py` into
  `tests/storage_conformance.py` (decision 6), run against **memory
  only** in this chunk — proves the extraction changed nothing
  before a second backend exists.
- Adopt the R8 error-ordering matrix verbatim: shared descent ladder
  rows (positional precedence, wrong-kind beats permission on a
  node, deleted/trashed ancestor → `not_found`, per-component length
  at the offending component) + the per-verb leaf table (create:
  exists > permission; delete: permission > wrong_kind). Zero
  per-engine conditional assertions; per-family opt-in from
  declared capabilities.
- Mask assertions from Stage-1 chunk 1 move into the shared suite
  (projected-out ≠ null, assert-by-mask).

### 5. `rows.py` → target schema

The rewrite to option (c); pure schema objects, no consumer yet,
`test_rows.py` and the Entry drift test keep it green:

- **entries** (narrow): integer surrogate PK (`sqlite_autoincrement`
  stays), `node_id` ULID unique, `parent_id` FK-shaped integer
  (nullable for root), `name`, `kind`, `path` (regenerable cache,
  unique, binary collation), `revision` BigInteger, metrics,
  timestamps, `owner_id`, restore-metadata columns
  (`original_parent_id`, `original_name`, `deleted_at` — null unless
  trashed), **no content column**, `UNIQUE(parent_id, name)` — the
  create-arbitration index that also serves keyset pagination.
- **content**: `node_id`-keyed, one blob per row, blob column
  physically last.
- **versions**: (`node_id`, `version_number`) key, `is_snapshot`,
  body (full snapshot at write; diff form only post-pack),
  `content_hash`, `created_by`, `created_at`. Identical-hash write
  short-circuit is the dedup hook.
- **chunks**: ID-keyed — (`node_id`, `chunk_index`) unique, line
  span, chunk text, `content_hash`, embedding column (the
  `VectorType` moves here off the entry table — chunks are the
  embedded unit). Never path-keyed (the zero-chunk-rows rename
  criterion). Read side lands in Pass B; population belongs to the
  follow-up chunk/encode story.
- **edges**: ID-keyed and narrow — `source_id`, `target_id`,
  `edge_type`, `weight`, `distance`, `UNIQUE(source_id, target_id,
  edge_type)`, indexes both directions. `source_path`/`target_path`
  columns die.
- **meta**: single-row — `schema_format_version` (module constant
  `SCHEMA_FORMAT_VERSION = 1`), `mount_identity` ULID (keys the §10
  advisory lock), `created_at`.
- **posting_list**: keeps its shape; default encoding flips to
  `ENCODING_DELTA_VARINT`; **`gram_staging` and `GramStagingRow` are
  deleted** (batch-only lifecycle); posting rows gain the epoch
  column (three-part fingerprint lives in one epoch row or meta —
  final shape with the table).
- Binary collation pinned per dialect via `with_variant` (SQLite
  BINARY is default; Postgres `COLLATE "C"`; MSSQL
  `Latin1_General_BIN2`) on `path`/`name`.
- `ENTRY_ROW_ONLY_COLUMNS` and the drift test updated; encoding
  constants' docstrings trued up (delta+varint is v1, gamma dropped).

## Pass A — files and directories (four slices)

### 6. Package skeleton + lifecycle

`dialects.py`, `engine.py`, `backend.py` with the read surface
stubbed to classified `unsupported` until slice 7:

- Construction XOR (built vs borrowed), loud on both-or-neither.
- First-touch: idempotent, lazy, on the caller's loop; dialect
  sniff; database-file settings (WAL, `page_size=16384`) before any
  table; `create_all`; schema-version row upserted under the
  topology serialization point (advisory lock / `BEGIN IMMEDIATE`);
  unique violation → re-read and verify; mismatch → loud classified
  refusal; metadata-root row.
- Per-op session start applies connection state every time
  (`busy_timeout`, `synchronous=FULL`, `case_sensitive_like=ON`;
  Postgres isolation per §10).
- Retry wrapper: per-dialect retryable classifier (SQLSTATE /
  extended errcode), whole-method restart from first read, backoff;
  23505 never blind-retried. `BEGIN IMMEDIATE` for writes.
- `close()`: dispose iff built; idempotent.
- Tests (`test_backends_database.py`): restart/rebind shape (056
  criterion), construct-on-one-loop/first-touch-on-another,
  version-mismatch refusal, two-instance concurrent first touch,
  borrowed-pool close never disposes.

### 7. Read family + glob

- `descent.py`: one descent-ladder chokepoint returning either the
  resolved row or the R8 classification; liveness prefix filter with
  its two scopes (trash always excluded; `__meta__` excluded from
  enumeration, direct-address bypasses).
- `reads.py`: point reads via `.mappings()` column selects narrowed
  by projection; `ls` = `parent_id` equality only; `tree` = sargable
  path-prefix LIKE with escaping + depth budget; binary-collated
  name ordering (harness-asserted byte-identical across engines).
- glob: sargable LIKE on the path cache with metacharacter escaping
  (`patterns.py` quarry).
- Mask stamping per decision 7. Capabilities: read family + glob
  (hand-declared, decision 2).
- Conformance suite gains its `sqlite` parametrization here — the
  read/glob families go green; mutation rows remain family-gated off
  until slice 8.

### 8. Mutation core (write / edit / mkdir)

- `writes.py`: accumulate dicts → few large Core statements;
  statement order pinned (parents before children, entries before
  versions/edges); one transaction per batch with parameter-budget
  chunking (budget from `dialects.py`) and classified per-entry
  outcomes; O(tables-touched) statements per chunk
  (acceptance criterion).
- Revision: per-mount monotone counter stamped in-transaction;
  guard in every material write's WHERE clause (rowcount 0 →
  `conflict`); unconditional parent bump on namespace mutations;
  metadata-only writes are material.
- Content layout: entries row never carries content; content table
  written separately (WAL-amplification criterion).
- `begin_nested()` only at the designed benign races (metadata root,
  schema-version upsert; trash bucket arrives in slice 9).
- Create arbitration: upsert on the unique index
  (SQLite/Postgres), catch-and-retry in its own savepoint on MSSQL
  (code path present, exercised when MSSQL testing arrives).
- Key-budget classification: over-byte-budget path/name classifies
  at the backend, per-verb harness rows.

### 9. Topology verbs: move / copy / delete + trash

- `topology.py`: every parent-pointer mutation under the
  serialization point — SQLite single-writer via `BEGIN IMMEDIATE`;
  Postgres `pg_advisory_xact_lock(hash(mount_identity))` at READ
  COMMITTED (the declared §10 exception), under-lock re-check
  walking destination ancestry to the root (liveness + acyclicity,
  both cycle directions → one refusal kind).
- move: subtree reparent = guarded material write of the moved node
  + unconditional both-parent bumps; descendants' path-cache rewrite
  bumps nothing; refusal order source-missing > target-exists >
  cycle > permission.
- copy: fresh node_ids, fresh chains (version 1 = copied content),
  zero edge rows, content-hash dedup allowed.
- delete: same-transaction trash-reparent into lazily-created hourly
  UTC bucket (the third designed savepoint race); in-bucket name =
  node ULID; restore metadata into columns; path caches rewritten
  under the internal `/.vfs/trash/` prefix; `permanent=True` =
  hard-delete of every row family.
- Postgres CI leg lands **in this slice**, not at the end — the
  advisory-lock code is Postgres-only and SQLite cannot exercise it.
  Marker-gated (`postgres`), URL via env, service container wiring
  per the existing integration-marker posture.
- Tests: move contract (no observable intermediate states),
  two-instance concurrent cycle composition (refusal or abort,
  never a committed cycle), two same-named deletes into one bucket,
  trashed path `not_found` through every read verb, crash-simulated
  rollback consistency, permanent delete leaves zero rows.
- Pass A close-out: capabilities declaration trued up, acceptance
  criteria audited, STATUS.md and spec status updated.

## Pass B — meta namespace and graph (three slices)

### 10. Versions + content hash + meta paths

- Store-full on write in the same transaction (no read of prior
  content — acceptance criterion); identical-hash short-circuit.
- Reads through `reconstruct_version` (a full row is a chain of
  length one); hash verified on write and reconstruction; mismatch →
  the dedicated corruption kind naming version and chain position.
- Meta-path mapping: `__meta__` version/chunk endpoints resolve to
  rows via `paths.py` decomposition (no ad-hoc re-parsing); chunk
  rows read side.

### 11. Trash admin verbs: restore + sweep

- Admin methods beside `close()`, outside the sixteen-verb surface.
- restore: move-shaped; target-exists → `conflict`; original parent
  re-verified live (trashed/swept → `not_found`); parent followed by
  identity.
- sweep: retention + grace parameters; idempotent, crash-resumable;
  liveness check + delete in one transaction; deletes version /
  chunk / gram / edge rows both directions (no dangling edges —
  harness row).

### 12. Edges, `mkedge`, graph

- `mkedge` completes the mutation family; edges join endpoints to
  live entries for liveness (never surface a trashed endpoint).
- `graph`: one bounded-depth recursive CTE over edges, parameterized
  by direction/edge-type/hop-limit, dialect differences confined to
  CTE syntax; runtime budgets + truncation flags.
- The **pack verb** (`versions.py`) depends only on slice 10 and may
  land any time after it — kept adjacent to reindex in Pass C by the
  spec's grouping, but it is unblocked from here on; take it early
  if a session has room. Corrupted-diff-row probe rides with pack.

## Pass C — grep + gram index (two slices, plus pack if not landed)

### 13. Grep: index write+read together

- `models/postings.py` codec (decision 5) with property tests
  (round-trip, monotone deltas, tag dispatch).
- `grep.py`: compile-first (failure → invalid-pattern); plan folded
  unconditionally for every case mode; `GramAny` →
  `unindexable_pattern` naming `allow_scan=True`; scan/verify tier
  as the opt-out engine; rarest-first k=4 intersection by
  `doc_count` with early exit and empty-posting short-circuit;
  metadata/liveness join before content fetch; unconditional Python
  `re` verification; runtime budgets (candidate / posting-byte /
  wall-time) with truncation flags.
- Dirty overlay: `revision > watermark` scan-tier union, mutually
  exclusive sides, capped with visible response.
- Posting build path (shared with 14): fold, gram, encode, bulk
  insert under an epoch.
- Capabilities gain grep; `traits()` reports `indexed` /
  `watermark`.

### 14. Reindex verb: epoch flip + reclamation

- Admin verb; builds posting rows under a new epoch, flips the
  current-epoch pointer in one transaction (readers see old or new,
  never a mix — acceptance criterion); old-epoch reclamation as the
  separate slower step; three-part fingerprint (format version,
  options hash, max-revision watermark); idempotent-cheap on
  unchanged watermark; format/options mismatch → drop-and-rebuild.
- Full acceptance-criteria audit; `capabilities()` becomes
  `storage_ops(self)` (decision 2 endgame); spec status → landed.

## Ripples

- **Stories**: 013/014/030 already carry supersede notes (verify
  final wording when Pass C lands); 067's graph direction consumed
  by slice 12 — leave 067 open for the analytics decision; the
  059–066 series: 059 becomes the ADR, 060–063's schema deltas are
  absorbed by Stage-1 chunk 5 + Pass A (record that in their
  slots/STATUS.md when landing).
- **070 sequencing**: every backend verb and conformance signature
  written before 070 adds `user_id` surface the `Principal` rename
  must later touch. If 070 is imminent, land it before Stage 1;
  otherwise proceed — the ripple stays mechanical either way.
- **056 Pass B/C** (adapter + MCP trio) remain independent; nothing
  here blocks or is blocked by them.
- **Docs**: `docs/home.md` backend list when Pass A lands;
  CLAUDE.md needs no change.

## Risks and checks

- **The rows.py drift test and `ENTRY_ROW_ONLY_COLUMNS`** are the
  guard that the schema rewrite and the Entry ripple stay in
  lockstep — update both sides in the same chunk, never separately.
- **Coverage gate (99%)**: Postgres-only branches (advisory lock,
  isolation pins, 23505 upsert arm) are exercised only under the
  marker — mirror the existing integration-backend posture in
  `[tool.coverage.run] omit`/pragma policy *narrowly* (per-branch
  pragmas beat omitting the module; the SQLite paths must count).
- **MSSQL catch-and-retry arm** ships untested-by-CI (on-demand
  engine) — keep it a thin, obviously-correct savepoint wrapper.
- **`sqlite_autoincrement` + posting doc_ids**: deleted-top-rowid
  reuse stays forbidden; the constraint survives the schema rewrite.
- **Session-end discipline per slice**: `uv run pytest tests/ -q`,
  `uv run ruff check`, `uv run ty check` — green tree is the
  invariant, including mid-pass.
