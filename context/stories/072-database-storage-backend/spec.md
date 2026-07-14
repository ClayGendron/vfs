# 072 — Database Storage Backend: `DatabaseStorage` on the Composed Seam

- **Status:** researched — drafted 2026-07-12; §6 resolved 2026-07-12
  (`research-grep-index.md`); §§4-5, 8-10, 12 resolved 2026-07-13
  (`research-write-pipeline.md`, `research-read-pipeline.md`,
  `spike-results-pipelines.md`); versioning inverted to
  store-full-on-write + batch pack 2026-07-13 (owner decision);
  red-team scrutiny gate applied 2026-07-13 (22 confirmed findings
  folded — counter scope, move-verb isolation carve-out, topology
  serialization scope, verb surfaces, trash semantics, copy). No open
  markers. **in progress** — plan.md + tasks.md drafted 2026-07-13;
  ADR 059 landed 2026-07-14 as
  `context/decisions/004-stable-node-identity.md`; Stage 1 (seam
  ripples, tasks 2–8) complete 2026-07-14; adversarial pressure test
  same day — 11 confirmed + 3 contested findings written up in
  `pressure-findings-stage1.md` (four ready-to-implement, six
  decision-gated) — resolve before Pass A slice 6
  (`backends/database/` skeleton, tasks.md task 9)
- **Date:** 2026-07-12
- **Owner:** Clay Gendron
- **Kind:** feature (the database backend port that ADR 001 and ADR 002
  committed to)
- **Depends on:** 049 (`StorageBackend` protocol), 056 Pass A (storage
  mounts), 057 (result envelope), 071 (ingress gates — what the backend may
  assume about inputs), ADR 001 (composition), ADR 002 (engine ownership),
  ADR 003 (parent rule)
- **Relates to:** stable-ID namespace proposal (learnings 2026-07-08; story
  numbers 059–066 are reserved for that series), 058 (row-level grants), 070
  (principal-scoped sessions), 014/030/013 (auto-chunk / incremental index /
  trigram index — quarry), 003/006/007/011/012 (dialect-native search and
  traversal — quarry)
- **Enables:** persistent mounts, Postgres/MSSQL providers, `glean`/`graph`
  over durable state, the vfs MCP server backed by a real database

## Intent

Land the first persistent `StorageBackend`: `DatabaseStorage`, a SQL-backed
implementation of the composed protocol from 049/056, built from the schema
half that already exists (`models/rows.py`, `models/vector.py`,
`models/versioning.py`, `models/chunking.py`, `models/code_grams.py`) and
shaped like the reference backend (`storage/backends/memory.py`) rather than
like the archived `src2` god-class. The old `DatabaseFileSystem` is a quarry
for semantics (write planning, version chains, meta-path handling), not a
template for structure — its structural defects (no checked contract,
router/storage fusion, per-mount minted ORM classes, ~99 typing
suppressions, a write-only trigram index, three duplicate graph engines,
catalog-introspection DDL verification) are exactly what ADR 001/002 and the
live seam were designed to retire.

One sentence: **a repository behind the protocol — Core tables in, `Entry`
domain objects through, classified `Result`s out, one session per op, owned
by nobody but itself.**

## Shape

### 1. Class family (ADR 001 §"provider inheritance")

- `DatabaseStorage` — the portable base. Runs on any SQLAlchemy async
  engine (SQLite/aiosqlite is the dev/CI default; Postgres and MSSQL work
  unaccelerated). Implements `SupportsRead`, `SupportsPatternSearch`,
  `SupportsMutation`, `SupportsGraph`, `SupportsClose`; declares
  capabilities from its own method surface (`storage_ops(self)` is honest
  here — the method surface is the truth, per `protocol.py` doctrine).
- `PostgresStorage`, `MSSQLStorage` — provider subclasses that override
  only the verbs a native engine accelerates. **Their specs are separate
  stories** mined from 003/006/007/011/012; this story ships the portable
  base and proves the seam.
- User-facing wiring classes (`PostgresFileSystem` style) are thin
  constructors composing a `VirtualFileSystem` over a `DatabaseStorage` —
  no behavior.

### 2. Construction and lifecycle (ADR 002, verbatim)

- Exactly two constructions, loud XOR: **built** (connection config in,
  backend creates its own engine + sessionmaker, implements `close()` →
  dispose) or **borrowed** (injected session factory yielding fresh
  independent sessions; `close()` never touches the pool).
- No `setup()`. First-touch initialization is idempotent and lazy: dialect
  sniff, parameter budget, `create_all` on the mount's minted `MetaData`,
  metadata-root row. First touch happens at the first routed op (056
  consequence note), on the caller's loop by construction.
- One `DatabaseStorage` instance = one mount's tables (fresh `MetaData`
  from `build_vfs_tables`). Aliasing one instance at two paths is already
  refused at bind (056 decision 9).
- First touch writes a **schema-version row** at creation and verifies
  it on every subsequent first touch: empty database → provision;
  version mismatch → loud classified refusal — never PRAGMA/catalog
  sniffing (the AgentFS retrofit scar). Benign declared staleness
  (e.g. a stale index epoch) serves; unknown/incompatible state
  refuses (research.md §3 "§2"; write-pipeline W8). Shape: a per-mount
  single-row meta table minted by `build_vfs_tables`, holding an
  integer schema-format version compared against a module constant
  (plus the mount's durable identity, which keys the §10 advisory
  lock; index staleness lives in the §6 epoch fingerprint, not here).
  First touch runs under the §10 topology serialization point (the
  per-mount advisory lock on Postgres; `BEGIN IMMEDIATE` wrapping
  check-and-provision on SQLite); the version row is upserted, and a
  unique violation means another instance provisioned first — re-read
  and verify, never fail the op.
- Per-connection settings (`busy_timeout`, `synchronous=FULL`,
  `case_sensitive_like=ON` on SQLite; on Postgres the §10 isolation
  choice — REPEATABLE READ for op sessions, READ COMMITTED for
  topology verbs) are applied at the start of every op session — they are
  connection state, not database state, and a borrowed pool cannot be
  assumed pre-configured. Database-file state (`journal_mode=WAL`,
  `page_size=16384`) is first-touch.

### 3. Data access discipline — Core only, no ORM

The backend holds no SQLModel and no ORM unit-of-work. The three-lifecycle
rule from learnings 2026-05-26/2026-06-02 becomes structure:

- **Read**: column selects (`.mappings()`) narrowed by the `columns`
  projection push-down; reconstruct detached `Entry` objects via
  `model_construct` only where domain methods are needed. Nothing tracked,
  nothing dirty, thread-safe to hand to CPU work.
- **Write**: accumulate plain dicts, emit few large Core
  `insert()`/`update()`/`delete()` statements. The 50×-SQLite / 4×-Postgres
  bulk-insert lesson is the default idiom, not an optimization pass.
- **Transactions are backend-internal** (ADR 001 §D5): each protocol
  method opens one session, commits on success, rolls back on any
  DB-level error. A batch (`entries`, `operations`, `edits`) is one
  transaction — the durable analogue of the memory backend's
  stage-against-a-copy-and-commit. DB errors are transaction-fatal by
  default; `begin_nested()` savepoints only where partial tolerance is a
  designed behavior (the metadata-root race, the §9 lazy trash-bucket
  creation race, the §2 schema-version upsert — the designed cases
  where a unique violation is a benign already-created outcome, not an
  exists-classification).

Amendments from the pipelines research (write-pipeline W1/W5,
read-pipeline R2):

- **Statement order inside a transaction is pinned** — parents before
  children, entries before versions/edges. It carries no
  crash-consistency weight (one commit frame) but constraint
  arbitration fires per statement, so order is load-bearing for
  identical conflict behavior across dialects.
- **Internal helpers never open or commit transactions**; the protocol
  method owns its one transaction (the libsqlfs
  transaction-per-helper scar).
- **A batch is ONE transaction even when statements chunk by parameter
  budget**, and every entry gets a classified per-entry outcome, never
  a silent skip (the JuiceFS `doBatchUnlink` anti-pattern). The budget
  is a declared per-dialect datum on the base class.
- **Overlapping batch targets are order-independent** (resolved
  2026-07-14, pressure finding 2.6.1): a cascade delete subsumes
  requested descendants and repeats — judged against committed state,
  the S3-DeleteObjects/fsspec norm; no surveyed batch API validates
  against accumulating staged state — while move refuses duplicate
  sources and a source inside another moved source as a batch-shape
  conflict (`invalid`, named for the requested target; copy fan-out
  from one source stays legal, since copy never consumes its source).
  Per-target errors stamp the requested target into ``error.data`` so
  value-identical failures from distinct targets survive merge dedup
  (2.6.2 — per-requested-key attribution is the wild norm; nothing
  attributes a failure to a cascade root).
- The one-commit guarantee holds only while content lives in the
  transactional store — moving content out is a design fork that
  re-acquires the metadata/data ordering problem, not an optimization.
- **Every Observation carries an explicit populated-field mask** (the
  `statx` `stx_mask` precedent): projection is pinned strict —
  populated == requested ∪ always-on identity fields (path, kind,
  revision) — and the harness asserts by mask, never by value. This is
  a live-model ripple this story owns in Pass A: `Entry`/`Observation`
  gain `revision` and the mask, `results/projection.py` becomes
  mask-driven, and `InMemoryStorage` stamps revision so the shared
  harness holds for both backends.
- **Result merge under the mask** (resolved 2026-07-14, pressure
  finding 2.1): overlap fill in the result algebra is mask-driven —
  the right row fills only fields absent from the left mask, masks
  union, fetched-and-null is never overwritten — and revision merges
  agree-or-null: when both sides carry differing revisions the merged
  row's revision stamps null (still masked), so a composite of two
  snapshots never claims a single one (the NFS same-change_attr
  discipline, adapted so bind-path decoration keeps working across
  mounts' unrelated counters).

This retires the `src2` typing pain at the root: no minted ORM classes, no
`_unchecked_select`, target of **zero** `ty: ignore` in the new module.

### 4. Identity model — the fork this spec must not dodge

`rows.py` today is path-keyed with edge identity in
`source_path`/`target_path` columns — the exact encoding the 2026-07-08
stable-ID evaluation judged a live defect (rename must rewrite every edge
row or lineage severs). Three options:

- (a) Port on the current schema; migrate to stable IDs later. Cheapest
  now; fossilizes the defect ADR 001 warned every landed impl would
  fossilize, and buys a real data migration later.
- (b) Execute the stable-ID series (059–063) as schema-only stories first,
  then port. Cleanest layering; serializes two large efforts and 060–063
  have no consumer until this backend exists.
- (c) **Land this backend directly on the target schema** — `node_id`
  ULID, `parent_id`, narrow ID-keyed `edges` table, path as regenerable
  cache — folding the schema deltas of 060–063 into this story, with 059
  (the identity ADR) landing first as the binding decision. There is no
  live database to migrate; greenfield means the port and the pivot are
  the same work done once.

Resolved 2026-07-13: **(c) confirmed** by owner (evidence: the unanimous
six-repo verdict in `research.md` §1). 059 (the identity ADR) still lands
before plan.md as the binding decision record. One 059 detail this spec
depends on: `node_id` (ULID) is the *logical* identity; tables keep an
integer surrogate key for compact row references — §6 posting lists
encode the integer, never the ULID.

### 5. Revision — resolved: 64-bit counter, stamped in Pass A

Constitution §1.5 requires a monotone `revision` on every Entry and every
Candidate. Resolved 2026-07-13 (write-pipeline W2): revision lands **in
this story, Pass A** — the protocol layer supplies the precedent
research.md thought missing (Linux `i_version`, 9P `qid.vers`, the NFSv4
mandatory change attribute, whose `change_attr_type` taxonomy ranks the
counter encoding at the top of the value hierarchy).

- **Encoding: 64-bit integer counter**, backend-owned, never
  caller-writable, incremented unconditionally per material write in
  the same transaction as the write it stamps. No lazy-increment
  complexity (vfs lacks the journaling pressure that motivated Linux's);
  64-bit because fossil's 32-bit `mcount` is documented "can wrap!".
- **Scope: one per-mount global monotone sequence** — every material
  write stamps the touched entry with the next value. This
  deliberately diverges from the per-inode precedents (i_version,
  qid.vers, mcount): the §6 watermark and dirty-overlay predicate
  (`revision > watermark`) require globally comparable values, and a
  per-entry counter would leave every post-build entry (revision 1 <
  watermark) in neither the index nor the overlay — the silent
  false-negative class §6 forbids. Per-path monotonicity
  (Constitution §1.5) follows a fortiori from the global sequence.
- **"Material write" includes metadata-only mutations** (RFC 7862 §10,
  the stronger precedent over fossil's narrower scoping) —
  `if_revision` guards must catch metadata races too. One exemption,
  pinned: the path-cache column is derived state keyed off node
  identity, so a subtree reparent (move, trash, restore) is a
  material write of the moved node (guarded) plus an unconditional
  bump of both parents — descendants' path-cache rewrites bump no
  revisions and bypass the revision guard (else one directory move
  floods the §6 dirty overlay with unchanged-content entries).
- **Namespace mutations bump the parent directory's revision** (the
  iversion contract; ext4 and fossil both do). Without it, future list
  caching and the §6 watermark cannot see membership changes that
  touch no child row. The parent bump is an unconditional increment,
  never revision-guarded — it is not lost-update-bearing state, and
  guarding it would make every same-directory write pair conflict.
- The ordering half of the contract, stated: a revision value is never
  observable before the state it stamps — free here because both
  commit together (fossil, which stamps early and never rolls back, is
  the cautionary tale).
- The encoding is a **declared capability trait** (`change_attr_type`
  precedent), and revision is surfaced on every Observation
  unconditionally — the same-transaction stamp removes the
  write-amplification concern that gates it in Linux.
- The §6 index epoch's content watermark is the max revision at build
  time, and the dirty-overlay predicate is `revision > watermark` — a
  second independent reason the stamp ships in Pass A.
- `if_revision` guarded writes remain a follow-up capability-gated
  story, with one exception already in scope (W7): **the revision
  guard appears in the WHERE clause of every material write to the
  op's target entries** (rowcount 0 → `conflict`; the parent bump
  above is deliberately unguarded) — at READ COMMITTED (the §10 topology-verb
  exception) EvalPlanQual otherwise makes a write-write conflict
  silently last-writer-wins; at the §10 REPEATABLE READ pin the rival
  surfaces as 40001, the retry discipline re-runs the op against
  fresh state, and the guard then reports `conflict` honestly instead
  of retrying forever.

### 6. Search ladder (portable tier only)

Resolved 2026-07-12 — full evidence and numbers in
`research-grep-index.md`; scale claims validated empirically in
`spike-results.md` (SQLite portable tier at ~1M docs: selective grep
0.3–80 ms, full index rebuild ~3.5 min single-threaded; pg_trgm
comparison run at 100K/495K). Hard requirement: grep stays fast at
millions of documents, so the gram index is a core deliverable, not an
optimization tier; a LIKE-prefilter scan is never the default public
behavior.

- `glob` — sargable `LIKE` on the indexed path column (the `patterns.py`
  quarry; proven shape), with LIKE-metacharacter escaping (`%`, `_`,
  escape char) on every path-derived prefix.
- `grep` — ships **with** the byte-trigram index (`code_grams.py`
  planner + posting tables in `rows.py`), write side and read side in
  the same pass — never one without the other (the `src2` write-only
  scar stands).
  - **Index-required by default.** Compile the pattern first (failure
    classifies as invalid-pattern, never unindexable); plan with the
    gram planner **folded unconditionally, for every case mode** (raw
    planning against a folded-only index is a silent false negative);
    refuse `GramAny` patterns with a classified kind
    (`unindexable_pattern`) whose message names the per-call opt-out
    (`allow_scan=True`), which runs the scan/verify tier instead. No
    weak-selectivity refusal tier — selectivity is a runtime budget
    (candidate/posting-byte/wall-time caps, truncation-flagged
    results), not a plan-time prediction.
  - **The gram stream is raw folded codepoints — no Unicode
    normalization** (resolved 2026-07-14, pressure finding 2.4). The
    authoritative matcher is Python `re` over raw content, which is
    codepoint-exact and never unifies canonical-equivalent forms,
    while NFC is not substring-stable — so NFC in the pipeline created
    real false negatives to defend matches the verifier cannot make
    (zoekt, codesearch, and pg_trgm all index un-normalized streams).
    The one shared fold is newline-normalize + Turkic-i pre-fold
    (U+0131 and U+0130 → `i`; sre's simple-case orbit unifies them
    with `i` where `casefold` does not — U+0130 was a second breaker
    the original finding missed) + `casefold`, satisfying the
    invariant *candidate fold ⊇ verifier case orbit* (pinned by an
    exhaustive orbit-scan test). Normalization-insensitive grep
    (matching U+00E9 in either composed form) is explicitly out of
    contract — the raw-content verifier never provided it; offering it
    would be a product decision requiring normalized-verify semantics.
    The three-part epoch fingerprint's index format version (below)
    covers the fold definition: any future fold change forces reindex.
  - **Execution:** rarest-first intersection ordered by
    `posting_list.doc_count` — default **k=4** grams with early exit
    (spike-validated: k=2, zoekt's positional-only number, is up to 5×
    worse on doc-level postings; k=all wastes decode on rare
    patterns), empty-posting short-circuit, **the posting-byte budget
    enforced before fetch via `posting_list.byte_size`** — a blob the
    budget won't cover is never pulled; Postgres detoast of a
    compressed blob is all-or-nothing, so an accidental hot-gram fetch
    is expensive and unmitigable after the fact (resolved 2026-07-14,
    research-posting-storage.md) — metadata/soft-delete join
    before any content fetch, unconditional authoritative Python `re`
    verification of every candidate. The scan/verify machinery is
    permanent keepable code — it is the verification layer, the
    opt-out engine, and the dirty overlay.
  - **Posting encoding:** v1 default is `delta+varint` (numpy-decodable
    at ~125M values/s; also smaller than gamma for the sparse blobs the
    k-rarest policy actually fetches — spike §2). Delta+gamma is
    dropped; `ENCODING_ROARING` stays reserved for a density-tier
    upgrade if ever needed.
  - **Storage granularity (resolved 2026-07-14,
    research-posting-storage.md): one row per `(epoch, gram_key)`
    holds the gram's full doclist blob.** FTS5 and GIN split posting
    lists only to serve intra-list seek and in-place update — both
    absent here (whole-blob fetch of k-rarest grams; epoch-immutable
    rows), and the shipped tier has no blob-capacity cliff. Doc-id-range
    chunking stays reserved, never built speculatively: posting tables
    are regenerable caches, so a future chunked format is a
    format-version bump and drop-and-rebuild, not a migration.
  - **Index lifecycle: batch only.** No per-write index maintenance —
    the staging/fold/compact pipeline is dropped and `gram_staging`
    leaves the schema. An explicit reindex verb builds posting rows
    under a new epoch and flips the current-epoch pointer in one
    transaction — **the flip is a compare-and-set on the expected old
    epoch, rows-affected checked, so concurrent reindexers cannot
    publish over each other** (Oak's checkpoint CAS; resolved
    2026-07-14, research-posting-storage.md); old-epoch reclamation is
    a separate slower step. Posting rows bulk-insert **sorted by
    `(epoch, gram_key)` in size-partitioned batches** — SQLAlchemy's
    insert paging is parameter-count-only with no byte limiter (and
    MSSQL's 2,100-param cap yields 349 rows/statement at six columns),
    so the verb caps batch bytes itself: large pages for the tiny-blob
    majority, small pages for heavy grams. The
    epoch stamp is a three-part fingerprint (index format version,
    index-options hash, max-revision watermark); any format/options
    mismatch → drop-and-rebuild, never migrate. The verb is
    idempotent-cheap when the watermark says nothing changed.
  - **Freshness: dirty overlay.** The index tier serves entries at or
    below the watermark; entries above it are scan-grepped and
    unioned, the two sides mutually exclusive so modified entries
    never double-hit. The dirty set is capped with a visible response
    (forced reindex or surfaced degradation). Grep's tier and
    staleness window are declared capability traits (§10's
    declared-eventual-consistency rule).
  - **Prerequisites:** the confirmed per-codepoint-NFC false-negative
    fix in `code_grams.py`, and a guard that grep always plans folded
    (both in `research-grep-index.md` §5).
- `glean` — **not in this story's portable tier.** It needs the
  chunk/encode pipeline; partial backends are first-class under 049, so
  capabilities simply omit `glean` until the indexing story lands.

Surface decisions (the 049/056/071 ripple, named — scrutiny gate
2026-07-13): **`allow_scan` is a real parameter on the grep protocol
signature** — added to `SupportsPatternSearch.grep`, given an ingress
row in 071's table, and accepted by `InMemoryStorage.grep` as a no-op
(the memory backend is already scan-tier). **Capability traits**
(grep tier and staleness window, revision encoding, durability tier,
arbitration mode) live in one declared mapping on the backend,
surfaced beside `capabilities()`; its exact protocol shape is pinned
in plan.md as a 049 ripple. **Maintenance verbs — §6 reindex, §9 pack
and sweep, and v1 restore — are backend admin methods, not routed
protocol verbs**: they sit beside `close()` outside the sixteen-verb
surface, invisible to capabilities and 071's ingress table; a routed
maintenance/trash surface is a recorded follow-up story.

### 7. Graph — one engine, not three

`src2` implemented traversal three times (plpgsql function, T-SQL proc +
TVP, in-process rustworkx). Here: **one** implementation — bounded-depth
recursive CTE over the edges table (the 067 direction), parameterized by
direction/edge-type/hop-limit, portable across SQLite/Postgres/MSSQL with
dialect differences confined to CTE syntax. No in-memory graph cache, no
stored procedures, no per-dialect reimplementation. Analytics that
genuinely need an in-memory engine are out of scope (067 decides those).

The CTE is the **graph engine only** (R7, spike-measured — no
crossover at any size or depth): subtree enumeration for read verbs
uses sargable path-prefix LIKE on the materialized path column (2.7×
on full-row enumeration, 12× on counts, at 84K descendants —
SQLite-measured; the same range-scan-vs-per-row-probe structure holds
on Postgres, constants unmeasured), and shallow listing is
`parent_id` equality only, never prefix-scan-and-filter (795× — the
libsqlfs scar quantified). Deep enumeration runs under §6-style
runtime budgets with truncation flags.

### 8. DDL ownership

The backend owns every schema object it requires: `create_all` at first
touch provisions the portable tables and indexes. The `src2` pattern —
externally provisioned extensions/generated-columns/ANN indexes verified by
regex-matching `pg_get_indexdef` output — dies. Native accelerations
(pgvector indexes, FTS columns, FREETEXT catalogs) belong to the provider
stories and must arrive there as **explicitly provisioned or explicitly
declared-external with a capability gate**, never as brittle catalog
introspection.

Resolved 2026-07-13 (research.md §3 "§8"; write-pipeline W8):
**app-owned idempotent `create_all` + the §2 schema-version row** is
the shipped posture (JuiceFS: years of releases, no migration tool;
SeaweedFS's v2 store moved *to* app-owned DDL). Index-tier tables are
versioned regenerable caches — format-version stamped,
drop-and-rebuild on mismatch, never migrated. **Binary collation is
pinned in DDL on path/name columns** — a pagination-correctness and
LIKE-sargability prerequisite, not an ordering nicety. On MSSQL that
collation is `Latin1_General_100_BIN2_UTF8` (resolved 2026-07-14,
pressure finding 2.5): a Unicode-safe VARCHAR whose byte order equals
UTF-8/code-point order on every engine, with a **SQL Server 2019+
floor**. Plain `_BIN2` VARCHAR was a code-page column silently
corrupting non-Latin paths; NVARCHAR+`_BIN2` is rejected twice over —
UTF-16 code-unit order diverges from the other engines on
supplementary-plane characters, and 2 bytes/char busts the 1,700-byte
index-key cap even for ASCII paths at the full 1024-char budget,
where UTF-8 VARCHAR keeps every all-ASCII path indexable (non-ASCII
paths past 1,700 UTF-8 bytes classify at the byte budget below). The
MSSQL provider story must validate the ODBC UTF-8 parameter path
end-to-end before claiming the capability; Oak's
varbinary-of-UTF-8-bytes key is the documented fallback. A migration
tool remains a future option for the durable entry/edge/version
tables only, if deployment policy demands it; that changes how DDL
runs, not who defines it.

Path/name key columns carry an explicit **per-engine byte budget** —
a declared per-dialect datum beside the parameter budget (MSSQL
unique keys cap near 1,700 bytes, Postgres btree near 2,704;
`MAX_PATH_LENGTH = 1024` counts characters, i.e. up to 4,096 UTF-8
bytes). A path lawful at ingress but over the engine's key budget
classifies at the backend — never an unclassified driver error — with
at/over-limit harness rows per mutating verb (research.md gap #1,
closed). `table_name` carries the same discipline (resolved
2026-07-14, pressure finding 2.6.3): `build_vfs_tables` refuses a
prefix over `MAX_TABLE_NAME_LENGTH = 41` — derived constraint names
must fit Postgres's 63-char identifier cap on every engine (SQLite
would accept them; SQLAlchemy's compile-time `IdentifierError` fires
only on the first engine that enforces the cap) — with a tightness
test pinning the 63 − 22 arithmetic to the longest derived suffix.

Blob columns are correct as generic `LargeBinary` on the shipped tier
(SQLite `BLOB`, Postgres `bytea`, MSSQL `VARBINARY(max)` on 2012+ via
`deprecate_large_types`). A future MySQL tier must pin `LONGBLOB` via
`with_variant` — bare `LargeBinary` renders MySQL's plain `BLOB`, a
64 KB silent-truncation cap (resolved 2026-07-14,
research-posting-storage.md).

### 9. Meta namespace, versions, content layout, and delete — resolved

- Chunks, versions, and edge projections are rows in the same store,
  addressed under `/.vfs/.../__meta__/...` exactly as `paths.py` defines;
  the backend maps meta paths to rows (quarry: `src2` meta-path handling,
  minus the ad-hoc re-parsing — `paths.py` now owns decomposition).
  Precedent for version addressing through the normal verb vocabulary:
  fossil's `/snapshot/yyyy/mmdd` namespace.
- **Versions — store-full on write, pack in batch** (owner decision
  2026-07-13, promoting the git-shaped alternative W3 recorded as the
  fallback: the write path is the common case and carries no diff
  work). The write transaction stores the version as a **full
  snapshot** — no diff computed, no read of the previous version's
  content inside the write transaction (the read amplification the
  spike found dominant: the write-side diff costs 2× the worst read
  replay at 256 KB — spike §1). The version row still commits in the
  same transaction as the entry update. `content_hash` is computed at
  write and doubles as the dedup/idempotence hook (identical-content
  versions store one body — git's hash-then-skip).
- **The pack verb** — a batch maintenance verb beside §6's reindex,
  same doctrine (explicit, idempotent, caller-scheduled, cheap when
  the watermark says nothing changed) — rewrites cold version ranges
  into the compact form `versioning.py` already implements: a full
  snapshot every `SNAPSHOT_INTERVAL` (10) + forward diffs between
  (spike-validated read cost: worst-case replay 0.25–5.2 ms across
  1 KB–256 KB docs; the ~10 ms/version diff cost at 256 KB now runs
  off the write path, in batch). Each chain's rewrite commits in one
  transaction, so readers see the old form or the new form, never a
  mix (the §6 epoch-flip shape). Unpacked history is fatter, never
  wrong — packing is compaction, not correctness.
- Reads reconstruct through `reconstruct_version` regardless of form
  (a full row is a chain of length one). Content hash is verified
  **on write and on reconstruction**; a mismatch classifies as a
  dedicated **corruption kind** — never `not_found`, never `conflict`
  — naming the failing version and chain position. Packed snapshots
  double as corruption firewalls (blast radius ≤ 9 versions); a
  corrupt row in unpacked form poisons only itself.
- **Content layout** (W4): content lives in its own node_id-keyed
  table, one blob per row, blob column physically last; the entries row
  stays narrow so metadata writes never rewrite content — measured:
  259× WAL amplification for a width-changing metadata bump beside an
  inline 1 MB blob (spike §2). `page_size=16384` for the mount's
  SQLite database file, set at first touch before any table exists —
  a whole-file setting, not per-table (1.6–2.5× on large blobs for
  +2% WAL; entries rows are narrow enough not to care). Id-keyed
  chunk rows are the recorded fallback; `sqlite3_blob_*` is recorded
  as a future streaming escape hatch only (structurally incompatible
  with one-session-per-op).
- **Delete — resolved: trash-reparent; the `deleted_at` predicate is
  retired.** No reviewed system ships a hand-threaded liveness
  predicate; JuiceFS's namespace-encoded liveness is the shipped
  model, and it presupposes exactly the stable-ID substrate option (c)
  provides (write-pipeline W6a):
  - Delete = **same-transaction reparent** into a time-bucketed trash
    node (hourly-or-coarser UTC buckets, lazily created — the one
    designed benign creation race, §3). **Trash is backend-internal
    state in v1**: trash nodes are rows reachable by `parent_id`, not
    addressable paths — `paths.py`'s grammar gains no trash shape,
    and a routed list-the-trash/restore namespace is a recorded
    follow-up story. Trashed rows' path caches are rewritten under a
    reserved internal `/.vfs/trash/...` prefix that ingress never
    admits: the value exists so the chokepoint's prefix filter has
    something to filter on, not for addressing. The name vanishes from every lookup inside the
    delete transaction — the pjdfstest visibility contract by
    construction.
  - **The trashed entry's in-bucket name is its node ULID**; the
    original identity (original parent_id, original name, deleted_at)
    lives in restore-metadata **row columns, never encoded into entry
    names** (the JuiceFS MaxName-truncation scar). Two same-named
    deletes into one bucket can never collide on the
    UNIQUE(parent_id, name) arbitration index.
  - **Restore** is a backend admin method in v1 (§6 surface
    decisions), move-shaped: target-exists classifies `conflict`, and
    the restore transaction **re-verifies the original parent is
    live** — a trashed or swept parent classifies `not_found`, never
    a silent restore into the excluded namespace; a parent that
    merely moved is followed by identity (parent_id, not path).
  - The read-path exclusion is a **liveness filter with two scopes at
    one chokepoint**: default-scope enumeration and search (ls, tree,
    glob, grep) exclude trash and meta subtrees by prefix; a
    directly-addressed read of a lawful `__meta__` endpoint bypasses
    the meta exclusion but never the trash exclusion; **graph and
    edge projections join endpoints to live entries** — an edge is
    invisible whenever either endpoint is trashed (edges carry no
    path column; they inherit liveness by joining to entries, where
    the prefix filter applies — the same entries-join grep's
    candidate stage already performs before content fetch).
  - **`permanent=True`** (the flag the protocol's delete already
    carries) = same-transaction hard delete of the entry subtree plus
    its version/chunk/gram/edge rows — no trash hop, zero rows
    remaining in any family.
  - **Reclamation**: an explicit, idempotent sweep verb with a
    retention parameter and grace window deletes expired bucket
    subtrees plus their version/chunk/gram/**edge** rows (both
    directions — no dangling edges survive a sweep); scheduling is the
    caller's problem (the §6 reindex-verb doctrine). The trash rows
    are the durable work queue (the ext4 orphan-list shape); the sweep
    is safe to re-run after a crash at any point, and its liveness
    check + delete run in one transaction — closing the concurrent
    -mutation race git-gc documents as unsolved.
- **Copy** (the protocol verb no section owned — scrutiny gate): copy
  mints fresh node_ids for every copied node, starts a fresh version
  chain (version 1 = the copied content), copies **no** edge rows, and
  may share content bodies via the `content_hash` dedup hook. The
  mirror of rename's criterion: copying a subtree with lineage creates
  entry/content/version-1 rows only.
- **Listing order**: `ls`/`tree` results are ordered by the
  binary-collated name column, byte-identical across engines
  (harness-asserted). The recorded pagination extension (research.md
  gap #2) is a keyset cursor — (last name, limit) over that collation,
  served by the same UNIQUE(parent_id, name) index that arbitrates
  creates — never OFFSET, never opaque positional tokens.

### 10. Concurrency, consistency, and durability — resolved

- **One session per op; no cross-op state.** Never hold sessions, open
  cursors, or unconsumed result iterators across ops — an open read
  transaction pins the SQLite WAL reader mark and blocks checkpoint
  backfill (R4). No in-process locks guarding correctness (the `src2`
  compile `asyncio.Lock` protected nothing across processes) —
  cross-writer arbitration is the database's job. Any future cache
  must meet the R6 admission criteria: a store-owned stamp (revision),
  a validation event (revalidate-per-hit for one-shot ops),
  whole-entry invalidation, named excluded classes; staleness may only
  ever cost latency, never wrongness; not-found results are never
  cached in-process.
- **Read-consistency contract:** each protocol method observes a
  single committed snapshot fixed at its first database read —
  topology verbs on Postgres excepted, by design: they trade the
  op-level snapshot for the serialization point below, where
  per-statement visibility is the load-bearing property;
  sequential methods on one backend read their own prior writes; no
  consistency is promised across methods beyond that. SQLite:
  substrate-guaranteed (WAL snapshot at first read; writes snapshot at
  `BEGIN IMMEDIATE`). Postgres: **op sessions pin REPEATABLE READ** —
  default READ COMMITTED silently downgrades to per-statement
  snapshots (R4, the one real read-side contradiction). Void for
  replica reads unless remote-apply semantics are declared.
- **SQLite lock discipline (W7):** writes open `BEGIN IMMEDIATE` —
  the busy handler is only consulted with no open transaction, so a
  DEFERRED read→write upgrade fails instantly with BUSY_SNAPSHOT that
  no timeout absorbs (measured: IMMEDIATE ran 600 contended two-writer
  ops with zero errors; spike §4). `busy_timeout`, `synchronous=FULL`,
  and `case_sensitive_like=ON` applied **per connection** — at every
  op-session start, since they are connection state a pool cannot be
  assumed to carry (§2); WAL and `page_size` at first touch
  (database-file state). BUSY_SNAPSHOT under the discipline is a bug
  classified loudly, never silently retried; COMMIT itself can never
  return BUSY in WAL mode. `case_sensitive_like=ON` is load-bearing
  twice: default LIKE is case-insensitive AND unsargable on the path
  index — both §6 glob and §7 enumeration silently degrade without it.
- **Retry discipline (W7):** a per-dialect retryable-error classifier
  (SQLSTATE/extended errcode, never message text) wraps read AND
  write transactions. A retryable outcome (SQLITE_BUSY at op start,
  Postgres 40001) restarts the **whole protocol method from its first
  read** (the FreeBSD ERELOOKUP shape), **with backoff** — bare
  spin-retry measurably starves against a busy rival (spike §4).
  Unique violations (23505) are definite exists-outcomes after
  arbitration, never blind-retried; the MSSQL catch-and-retry runs in
  its own transaction or savepoint. Retryability is an orthogonal
  flag on the Result envelope (057 ripple).
- **Arbitration:** concurrent create arbitrated by the unique path
  index (upsert on Postgres/SQLite; catch-and-retry on MSSQL);
  pre-checks are optimizations. The §5 revision guard in every
  material write's WHERE clause is the lost-update defense; no
  `SELECT ... FOR UPDATE` in v1 (a default-with-justification, not a
  ban — JuiceFS's 31 call sites earn theirs).
- **Move contract (W6b):** at no point does any reader observe the
  destination absent during replace, both names live, or a partially
  moved subtree — one SQL transaction delivers what the FFS lineage
  never had; say so. **Every parent-pointer mutation — move,
  trash-reparent delete, restore, the sweep, and first-touch
  provisioning — executes under the serialization point that freezes
  tree topology**: two individually-safe moves compose a committed
  parent-pointer cycle at READ COMMITTED *and* REPEATABLE READ
  (observed — spike §4; the 4.4BSD bug, MVCC edition), and an
  unserialized delete can trash a move's destination between its
  re-check and its commit. SQLite's single writer suffices as-is.
  **Postgres topology verbs take a per-mount advisory lock**
  (`pg_advisory_xact_lock`; key = a stable 64-bit hash of the mount's
  durable identity from the §2 schema-version row, never the mount
  path) **and run at READ COMMITTED — a declared, deliberate
  exception to the per-op REPEATABLE READ pin**: an RR snapshot is
  fixed at the transaction's first statement, which is the lock call
  itself, so the post-lock re-check would read pre-rival topology and
  recommit the observed cycle; READ COMMITTED's per-statement
  snapshot is the load-bearing property the refusal depends on (the
  spike validated the refusing shape at READ COMMITTED only). The
  under-lock re-check verifies **destination-ancestry liveness** (no
  trashed or swept ancestor), not just acyclicity; it walks to the
  root, never fixed-depth; both cycle directions collapse to one
  classified refusal kind (Linux's EINVAL/ENOTEMPTY split recorded as
  deliberately not copied). **Cycle classification runs before
  occupied-target classification** (resolved 2026-07-14, pressure
  finding 2.3 — the Linux ladder: the rename trap checks fire in the
  lookup phase, before vfs_rename's kind checks ever run), which is
  what makes the one-kind pin reachable in the target-ancestor
  direction: an ancestor destination is by construction an occupied
  non-empty directory, so any occupied-first order would misclassify
  that direction as wrong_kind/not_empty.
- **Durability — "committed" defined per engine (W8):** committed =
  atomic (recovery truncates at the last valid commit frame),
  immediately visible, durable per the declared tier.
  `synchronous=FULL` / `synchronous_commit=on` are the defaults
  (measured price: 2× per-commit p50, ~6,500 single-op commits/s
  ceiling — spike §5, whose macOS-fsync caveat is disclosed there;
  re-price on target deployment hardware before publishing throughput
  claims); the NORMAL-mode unsynced-commit window is
  available as *declared* deployment tuning, never the silent
  default. The durability tier is a capability trait; conformance
  tests that assert durability-after-crash pin the tier explicitly.
- **Window inventory (W8):** within one transaction — zero windows
  (the substrate closes ext4's four machinery-windows by
  construction). Between transactions, every window vfs creates is
  classified **stale-declared** (the §6 watermark + dirty overlay) or
  **leak-with-a-named-sweeper** (orphaned non-current epoch rows →
  reindex reclamation; expired trash → the §9 sweep; unpacked version
  ranges → the §9 pack verb, a pure compaction — both forms
  reconstruct identically, so it is not a consistency window); the
  **corrupt**
  class must be empty — that assertion makes "no split-brain surface
  beyond declared windows" checkable instead of asserted. Sweeps are
  idempotent and resumable at any crash point: durable rows are the
  queue, and derived state that outran its authority row is
  discarded, never trusted.

### 11. Identity and principals

- `user_id: str | None` passes through to `owner_id` scoping as today;
  the 070 `Principal` rename ripples through mechanically when it lands.
- `user_scoped=True` path-rewriting mode and 058 row-level grants are
  out of scope; RLS is a deployment-hardening story.

### 12. Conformance testing — promote the contract to a harness

`test_backends_memory.py` pins one backend by name. This story extracts
the behavior contract into a **parametrized conformance suite** run against
both `InMemoryStorage` and `DatabaseStorage(sqlite)` — same POSIX
parent/site rules, batch classification, edit atomicity, move/copy
semantics, error kinds — with per-family opt-in matching declared
capabilities. Precedent: fsspec's `AbstractFixtures`/generic suite,
PyFilesystem2's `FSTestCases` base class, pjdfstest for POSIX semantics.
**The error-ordering matrix is adopted verbatim from
`research-read-pipeline.md` R8** (shared descent ladder + per-verb
leaf table, grounded independently in Linux and FreeBSD namei):
precedence is positional (leftmost path boundary wins, no lookahead);
wrong-kind on a node beats permission on that same node (the V7
access-clobbers-ENOTDIR bug is the rationale for a single early-return
classification chokepoint); leaf order is verb-class-dependent
(create: exists > permission, hand-engineered; delete: permission >
wrong_kind); deleted/trashed ancestors classify `not_found`;
per-component length classifies at the offending component, whole-path
budget at ingress (071). Per-verb translation is asserted at the
router seam; **zero per-engine conditional assertions**.

Harness rows added by the pipelines research: a trashed path
classifies `not_found` through every read verb; an op under a deleted
ancestor classifies `not_found`; a crash-simulated (rolled-back)
delete leaves all row families consistent; move/copy refusal order
(source-missing > exists-under-no-replace > cycle > wrong_kind >
not_empty > permission; resolved 2026-07-14, pressure findings
2.2/2.3) with both cycle directions one kind, dir-over-empty-dir a
successful POSIX replace, and dir-over-non-empty-dir `not_empty`
(POSIX latitude allows EEXIST or ENOTEMPTY; FreeBSD/JuiceFS/SeaweedFS
all emit ENOTEMPTY); the concurrent two-move cycle test on two
instances of one database; the corrupted-diff-row probe — post-pack
only, Pass C, since the write path is diff-free (corruption kind
asserted and post-snapshot versions still reconstruct);
create-after-failed-lookup from a second instance succeeds (no
negative caching); projected-out ≠ null asserted via the Observation
mask; WAL size returns to baseline after an op storm.

From the scrutiny gate: two same-named deletes into one trash bucket
both succeed; graph/edge projections never surface a trashed
endpoint, and a sweep leaves no dangling edge rows; restore with a
trashed/swept original parent classifies `not_found`; a
directly-addressed `__meta__` read succeeds while the same subtree is
excluded from enumeration; glob/enumeration case-sensitivity is
byte-identical across memory/SQLite/Postgres; at/over the per-engine
key byte budget classifies identically per mutating verb; permanent
delete leaves zero rows in any family.

Engine matrix, resolved 2026-07-13: memory + SQLite in every CI run;
Postgres behind a marker/service gate; MSSQL on demand (JuiceFS's
shipped posture, research.md §3 "§12").

## Delivery passes (each lands green, capabilities honest per pass)

- **Pass A — files and directories.** Construction modes, first-touch
  init + schema-version row, read family (with the Observation mask),
  mutation family, glob, trash-reparent delete + the namespace-prefix
  read chokepoint, revision stamping (with parent bump), conformance
  harness, 056 restart shape (rebind onto existing empty directory).
  No grep — capabilities honestly omit it until Pass C lands the index
  it requires.
- **Pass B — meta namespace and graph.** Version rows on write +
  reconstruction reads, chunk rows (read side), the trash reclamation
  sweep and restore admin methods, edges + `mkedge`, recursive-CTE
  `graph`.
- **Pass C — grep + gram index, write and read together.** Refusal
  gate, posting build, reindex verb with epoch flip, dirty overlay,
  runtime budgets (§6; shapes in `research-grep-index.md`), plus the
  version **pack verb** (§9 — the second batch-maintenance verb, same
  doctrine). The chunk/encode/glean pipeline follows as its own story.
- **Provider stories** (separate specs): Postgres-native search/vector,
  MSSQL-native search, each overriding verbs on the base.

## Out of scope

- `SupportsRun` — nothing durable to execute yet.
- The MCP trio and `VFSStorageAdapter` (056 Pass B/C).
- External vector stores (Databricks et al.) and the `VectorStore`
  protocol revival.
- Dialect-native accelerations (provider stories).
- Branching/snapshots beyond the version chain (future; lakeFS/Iceberg
  references on file in learnings 2026-05-03).

## Acceptance criteria (seed)

- Conformance suite passes identically for `InMemoryStorage` and
  `DatabaseStorage(sqlite)` across the families both declare.
- A built backend constructed on one loop and first-touched on another
  works (the ADR 002 notebook/sync-client shape) — no loop poisoning.
- Restart shape: new process, same database file → `add_mount` at the
  same path rebinds onto the existing directory (056 criterion).
- Rename of a subtree with lineage rewrites **zero** edge, version,
  chunk, or content rows — only the path-cache column (identity option
  (c), confirmed; strengthened per `research.md` §1).
- An N-entry batch executes in O(tables touched) statements per
  parameter-budget chunk (the budget a declared per-dialect datum), as
  ONE transaction with classified per-entry outcomes — the constant-
  statement criterion restated for wire dialects (spike §3: in-process
  SQLite is statement-count-indifferent; Postgres pays 2× per-row).
- Two concurrent cross-directory moves on two instances of one
  database can never commit a parent-pointer cycle — refusal or abort,
  never a committed cycle (spike §4 composes one without the §10
  mechanism).
- A metadata-only write beside 1 MB of content writes O(row) WAL
  bytes, not O(content) — the §9 layout criterion (spike §2: 259×
  the other way).
- A trashed path classifies `not_found` through every read verb;
  restore is move-shaped and `conflict`-classified on collision.
- A version-creating write performs no read of prior version content
  (the write path is diff-free); a chain's pack rewrite is atomic to
  readers (old form or new, never a mix), and every version
  reconstructs byte-identical before and after packing.
- Copy of a subtree with lineage creates entry, content, and
  version-1 rows only — fresh node_ids, fresh chains, zero edge rows
  carried.
- Grep refuses unindexable patterns with a classified kind by default;
  `allow_scan=True` runs the scan tier instead; capped queries surface
  a truncation flag, never silent partial results.
- An epoch rebuild is atomic to readers: grep sees the old index until
  the pointer flip, the new index after, and never a mix.
- No raw exception escapes a protocol method for any operating condition;
  every failure is a classified `Result`.
- `ruff` and `ty` at zero with **no new suppressions** in the backend
  module.

## Open questions

- ~~Identity model option (c) confirmation and 059 sequencing — §4.~~
  Resolved 2026-07-13: (c) confirmed; 059 remains the prerequisite ADR
  before plan.md.
- ~~Revision: prerequisite story or in-scope — §5.~~ Resolved
  2026-07-13: in scope, Pass A; 64-bit counter with the parent bump
  (`research-write-pipeline.md` W2).
- ~~Gram index in v1 grep or deferred whole — §6.~~ Resolved
  2026-07-12: grep ships with the index, write+read together, in
  Pass C; index-required by default with classified refusal and
  `allow_scan` opt-out; batch-only reindex (`research-grep-index.md`).
- ~~DDL: app-owned `create_all` vs migration-tool ownership — §8.~~
  Resolved 2026-07-13: app-owned + schema-version row
  (research.md §3; `research-write-pipeline.md` W8).
- ~~Soft-delete model — §9.~~ Resolved 2026-07-13: trash-reparent +
  reclamation sweep verb (`research-write-pipeline.md` W6).
- ~~CI engine matrix — §12.~~ Resolved 2026-07-13: SQLite always,
  Postgres gated, MSSQL on demand (research.md §3).

None remain. Prerequisite before plan.md: ADR 059 (the identity
decision record binding option (c)).
