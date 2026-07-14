# 072 research — nine reference repos reviewed against the spec

- **Date:** 2026-07-12
- **Method:** nine parallel reviewers (one per repo, shallow clones under
  `~/Git/Repos/`), each reading `spec.md` and then the repo's actual
  implementation, grading each spec section **supports / contradicts /
  nuanced / no-precedent** with file:line evidence. Reviewers were
  instructed to be adversarial — contradictions valued over agreement.
- **Repos:** juicefs, seaweedfs, libsqlfs, apache/opendal,
  fsspec (filesystem_spec), pyfilesystem2, pjdfstest,
  tursodatabase/agentfs, sourcegraph/zoekt.
- **Bottom line:** the spec's spine survives review intact — and the two
  biggest open questions in it are now answerable with shipped
  precedent: **identity option (c) is unanimously confirmed** (§1 below)
  and **§6 resolves to LIKE-tier grep in v1, grams deferred whole**
  (§2 below). The review also surfaced five genuine gaps the spec does
  not currently cover (§4).

> **Superseded (2026-07-12, same day):** the §2 recommendation
> ("LIKE-tier in v1, grams deferred whole") was overruled by a hard
> 0.1.0 scale requirement — grep must stay fast at millions of docs, so
> the gram index ships with grep, write+read together. §2's *evidence*
> stands (scan tier permanent, staging/fold dropped, batch rebuild) and
> feeds the successor design. See `research-grep-index.md` (deep-dive:
> refusal predicate, execution policy, freshness, scale) and
> `spike-results.md` (measured at ~1M docs). Deltas #3 in §5 is
> superseded the same way; spec.md §6 records the final resolution.

## Verdict matrix

S = supports · C = contradicts · N = nuanced · — = no precedent / not assessed

| Spec section | juicefs | seaweedfs | libsqlfs | opendal | fsspec | pyfs2 | pjdfstest | agentfs | zoekt |
|---|---|---|---|---|---|---|---|---|---|
| §1 class family / capabilities | N | S | — | N | S | N | — | — | — |
| §2 construction / lifecycle | **C** | — | S | N | S | S | — | S | — |
| §3 Core-only, txn-per-method | N | N | S | S | S | S | S | — | — |
| §4 identity model (option c) | S | **C**→c | S | S | S(–) | — | S | S | — |
| §5 revision stamps | — | — | — | S | — | — | — | S | — |
| §6 search ladder | — | N | — | S | S | S | — | — | S/N |
| §7 graph via recursive CTE | N | — | — | — | — | — | — | — | — |
| §8 DDL ownership | S | S | S | N | — | — | — | N | S |
| §9 meta namespace / soft delete | N | N | S | — | S | — | S | — | S |
| §10 concurrency | N | N | N | N | S | S | — | N | — |
| §12 conformance testing | S | N | S | S | S | S/N | S/N | S | — |
| Pass C (gram maintenance) | — | — | — | — | — | — | — | — | **C** |

(SeaweedFS's §4 "C" contradicts *path-keying* — i.e. it is the
production-scale scar that argues **for** option (c). Same reading for
JuiceFS's §2 "C": it contradicts *lazy-only* init, not first-touch
init itself.)

## 1. The identity fork (§4) is settled: option (c), unanimously

Six repos speak to the fork and every one lands on the same side:

- **JuiceFS** (supports): inode-keyed nodes + `edge(parent, name →
  inode)` with `UNIQUE(parent, name)`; **no path column anywhere**
  (`pkg/meta/sql.go:65-93`). Subtree rename updates one edge row
  regardless of subtree size (`sql.go:2292-2560`); paths are
  regenerated on demand for diagnostics only (`base.go:2329-2378`).
  Production on MySQL/Postgres/SQLite.
- **AgentFS** (supports): `fs_dentry(id, name, parent_ino, ino,
  UNIQUE(parent_ino, name))` with stable `ino` identity
  (`SPEC.md:229-238`); rename is a single-row `UPDATE fs_dentry SET
  parent_ino=?, name=?` (`agentfs.rs:2376-2387`). Their `fs_origin`
  table exists purely because stable IDs proved load-bearing across
  overlay copy-up.
- **SeaweedFS** (the scar): rows keyed `PRIMARY KEY (dirhash, name)` —
  path-keyed — so directory rename is a recursive
  enumerate/insert/delete over every descendant inside one caller-held
  transaction (`weed/server/filer_grpc_server_rename.go:134-327`), and
  that in turn forced a caller-owned cross-op transaction seam smuggled
  through an untyped context key that most backends silently no-op
  (`filerstore.go:36-38`). It then had to graft stable identity back on
  anyway: derived inode hashes and a refcounted hardlink KV side-table.
- **libsqlfs** (the purest demonstration): renaming one file rewrites
  the key on **every 8K content-block row** (`sqlfs.c:788-847`); a
  subtree rename is O(descendants × their blocks). The kicker: an
  `inode` column *exists in its schema* but is never used as a key —
  a stable-ID column changes nothing unless dependent tables key on it.
  Also: without `parent_id`, listing one directory scans the whole
  subtree with app-side filtering (`sqlfs.c:853-911`).
- **OpenDAL** (negative precedent): its path-keyed SQL services simply
  **declare `rename: false, copy: false`** rather than rewrite rows
  (`services/postgresql/src/backend.rs:159-167`). A VFS where move and
  lineage are mandatory verbs cannot take that exit.
- **pjdfstest** (semantics): POSIX filesystems are literally
  parent-pointer systems — `rename/24.t` pins that after a directory
  move, `..` resolves to the new parent's inode.

**Amendments to absorb while confirming (c):**

- **Keep a materialized path column** (the spec already says this; the
  review hardens it). AgentFS has no path column and pays a
  per-component SELECT walk per op, patched with a hand-invalidated
  in-process dentry cache — exactly the in-process state §10 forbids.
  The path cache is also what §6's sargable LIKE requires.
- **Strengthen the acceptance criterion** (libsqlfs): rename of a
  subtree rewrites zero edge rows **and zero version/chunk/content
  rows** — only the path-cache column.
- **Claim the read-path win in 059**, not just the rename win
  (libsqlfs): `parent_id` makes ls/tree/parent-checks one indexed
  equality instead of a subtree scan or per-ancestor query ladder.
- **Budget a verify/repair path for any denormalized cache** (JuiceFS
  `doRepair`): if path or parent is cached, ship the rebuild routine
  the stable-ID proposal already specs (062's rebuild-and-prove-
  byte-equality).
- **New hazard under parent_id** (pjdfstest): move-into-own-descendant
  becomes a parent-pointer **cycle** that breaks the §7 CTE and path
  regeneration — it must be refused at arbitrary depth and the harness
  must test it at ≥2 depths, plus post-move descendant path checks.

## 2. ~~The §6 fork is settled: v1 grep is LIKE-tier; grams deferred whole~~ (superseded — see banner above; evidence below still load-bearing)

- **Zoekt** (the production trigram engine) shows the scan path is a
  **permanent component, never a placeholder**: any regex without a
  ≥3-char literal atom routes to a brute-force tree
  (`index/eval.go:616-693`), sub-3-rune patterns bypass the index
  entirely (`matchtree.go:1296-1318`), and every candidate is
  re-verified authoritatively (`matchtree.go:810-845`). So the LIKE
  tier is the permanent skeleton the gram tier later narrows — build
  it as keepable code.
- **Zoekt contradicts the rows.py staging/fold/compact pipeline**: its
  default build **deletes and rewrites shards wholesale** with atomic
  publication; the incremental delta path is fenced with hard
  unsupported-case errors (`builder.go:688-775`). A mature engine
  treats incremental index maintenance as the hazardous half. Combined
  with the src2 scar (write-only staging machinery), the conclusion:
  when Pass C lands, prefer **transactional batch recompute of an
  entry's gram set in the write transaction** (or wholesale posting
  rebuild) over the staging-log/fold machinery; admit staging only
  when write volume proves the need.
- **A minimal correct gram query path needs four pieces** (Zoekt):
  sub-3-byte fallback to scan; empty-posting short-circuit;
  frequency-aware gram selection (intersect only the rarest few grams —
  `posting_list.byte_size` in rows.py is the ready cardinality proxy);
  unconditional authoritative re-match. Less is incorrect; more is
  optimization.
- **Case folding**: vfs's single folded gram stream is the valid dual
  of Zoekt's 8-variant query-time expansion — pin that case-sensitive
  grep queries the *same* folded index (fold pattern, verify
  case-sensitively), and keep verification `str.casefold`-correct,
  never ASCII lowering (`matchiter.go:57-63`'s Kelvin-sign warning).
- **fsspec corroborates the two-tier shape**: its only glob engine is
  literal-prefix push-down + authoritative compiled regex
  (`spec.py:596-663`) and it held for a decade of ecosystem use.
- **glob-to-LIKE translation must escape LIKE metacharacters**
  (`%`, `_`, escape char) in path-derived prefixes — OpenDAL ships a
  dedicated `escape_like` helper (`services/mysql/src/core.rs:124-155`).
- **Competitive footnote** (AgentFS): the most prominent agent-FS peer
  ships no search at all — even LIKE-tier grep in Pass A is
  differentiation; the gram tier can wait without losing ground.

## 3. Section-by-section: what the review confirms or amends

### §1 class family — confirmed, with two refinements

One portable SQL base serving SQLite/Postgres/MySQL is shipped reality
in both JuiceFS (`dbMeta`, ~6k lines; dialect files are 37–93 lines of
driver registration) and SeaweedFS (`AbstractSqlStore` + a 9-method
SQL-string generator per engine). Both found the same three things
actually force dialect code: **upsert syntax, identifier
quoting/collation, retry classification** — none of which justify a
subclass. Refinements:

- Keep provider subclasses **strictly for whole-verb native
  accelerations**; express upsert/retry/budget deltas as per-dialect
  *data* in the base, or the subclasses become empty shells (JuiceFS).
- Capability declaration needs room for **per-verb variants and
  numeric limits** (OpenDAL's `write_can_empty`, `delete_max_size`;
  two RFCs on native-vs-simulated capability). Decide up front whether
  a LIKE-tier and a gram-tier grep are distinguishable to callers, and
  define `capabilities()` as the *effective* set.
- Conformance also needs declared **semantic traits** that aren't
  verbs — revision encoding, arbitration mode, case sensitivity — with
  `unknown` legal (pyfilesystem2's `_meta` flags).

### §2 construction/lifecycle — confirmed, one amendment to adopt

Zero-I/O construction + idempotent lazy first-touch is OpenDAL's shipped
shape (`OnceCell` pool, `get_or_try_init` at first op) and AgentFS's
(`new()` delegates to `from_pool()` so built/borrowed never diverge —
worth mirroring). fsspec is the cautionary tale of the alternative:
its pid+thread-keyed instance caches, fork-detection, and "not
fork-safe" errors all compensate for loop-binding at construction —
the exact failure ADR 002 designs away. fsspec's own docs also
converged on built-XOR-borrowed for its event loop.

**The JuiceFS contradiction to absorb:** it refuses to serve an
unformatted database (`base.go:710-714`) — provisioning (`format`) is
an explicit admin act, and a format/version document is verified on
every load. Adopt the compatible half: **write a schema-version row at
first-touch creation and verify it on every subsequent first touch**,
so "rebind onto existing directory" distinguishes *empty DB →
provision* from *incompatible schema → refuse loudly*. AgentFS learned
this the hard way — no version row at creation, so version detection
decayed into PRAGMA introspection plus a retrofitted `migrate` command.

### §3 Core-only, transactions backend-internal — strongly confirmed

- JuiceFS holds an ORM (xorm) and still ended with every load-bearing
  statement as raw dialect-branched SQL; the ORM's conveniences
  generated their own plumbing tax (`sql.go:319-411`). SQLite's
  bind-variable ceiling is real in production (`DirBatchNum = 4096`).
- libsqlfs is the counterexample proving one-transaction-per-method:
  transaction-per-helper forced hand-rolled nesting emulation
  (`transaction_level` counters) with dozens of manual
  cleanup-before-return sites — and it *commits* on error paths.
  **Add to the spec: internal helpers MUST NOT open/commit
  transactions.**
- fsspec's `Transaction` is the ambient-mode cautionary tale:
  transaction state on a globally-cached instance silently changes
  unrelated callers' `open()` semantics and achieves only
  "semi-atomicity" (`transaction.py:5-46`).
- pyfilesystem2's `Info` namespaces validate the `columns` projection
  push-down, with one upgrade: a **loud not-loaded signal**
  (`MissingInfoNamespace`) — a projected-out field must be
  distinguishable from a null value at the Observation layer (vfs's
  "null means not populated" rule already says this; the harness
  should prove it).

### §5 revision — genuinely novel; land it before first persistence

No filesystem precedent exists: JuiceFS has no revision (safe only
because FUSE read-modify-write never crosses a transaction — vfs's
agent read→edit→write cycle does); AgentFS has none and its
second-precision mtimes **failed as a change stamp** in production
(NFS cache invalidation broke; they retrofitted nanosecond columns).
Treat `updated_at`-based encodings with suspicion — prefer a counter
or counter‖hash. OpenDAL validates the sequencing: universal stamp
now, `if_revision`-guarded writes later as a capability-gated feature
with a dedicated conflict kind (`ConditionNotMatch`), noting guard
failures may warrant the retryable flag (§10 below). JuiceFS's
additive schema-sync also warns: a revision column backfilled later is
semantically empty for existing rows — another reason it ships in
Pass A.

### §7 graph — one engine confirmed; placement noted

JuiceFS has exactly one traversal implementation (never per-engine —
the opposite of the src2 three-engine defect), but placed *above* the
storage seam because Redis/TiKV must run it too. The CTE-in-backend
choice is right for a SQL-only family; record that a future non-SQL
backend re-opens placement, hedged by keeping graph behind
`SupportsGraph`. AgentFS has no graph facility at all — no precedent
pressure to over-build.

### §8 DDL ownership — resolved: app-owned, with a version row

- JuiceFS: entire schema via idempotent struct-tag sync; **no
  migration tool across years of releases**; format flags gate
  destructive transitions.
- SeaweedFS's own evolution is the answer in miniature: v1 postgres
  store required operator-run DDL; the v2 store moved to app-owned
  `CREATE TABLE IF NOT EXISTS` with a config escape hatch for custom
  DDL.
- Zoekt sharpens scope: **index-tier tables are versioned regenerable
  caches** — stamp a format version; on mismatch drop-and-rebuild,
  never migrate. The alembic question then applies only to the durable
  entry/edge/version tables.
- OpenDAL confirms the negative rule: never verify external schema by
  catalog introspection — capability-gate, trust config, let the first
  query fail classified.
- SeaweedFS adds one DDL detail: **pin binary collation on path/name
  columns up front** (`postgres_collation.go` retrofits COLLATE "C"
  detection because locale-aware collation silently broke cursor
  ordering; MySQL DDL pins `utf8mb4_bin`).

### §9 meta namespace / soft delete — two viable models, one new duty

- The single select-builder chokepoint is validated by Zoekt: tombstones
  checked at exactly one place in the eval loop, physical removal
  deferred to compaction (`eval.go:218-238`, `merge.go:104-111`).
- JuiceFS offers the stronger alternative for the open question:
  **delete = reparent into a time-bucketed trash directory** — liveness
  encoded in the namespace, no predicate to forget anywhere, free
  list/restore of deleted entries, and it fits the parent_id model
  natively.
- Either way, the review adds a duty the spec lacks: **soft delete is
  half a design without a reclamation story** (expiry sweep, orphaned
  gram/version rows, cross-writer coordination — JuiceFS runs a fleet
  of background cleaners). Spec the GC story even if v1 defers it.
- pjdfstest pins the visibility contract: the name must vanish from
  **every** lookup instantly even while data persists — the harness
  should probe a deleted path through every read verb expecting
  `not_found` (catches any read path that bypassed the chokepoint).
- SeaweedFS (hard-delete world) shows what soft delete buys: they
  hand-sequence chunk cleanup after commit because mid-rename failure
  would leave metadata pointing at deleted chunks; reversible-until-
  vacuum collapses that hazard. libsqlfs calibrates the schema floor: a
  complete FS in 2 tables — resist splitting content out of the
  transactional store in v1.

### §10 concurrency — the section needing the most amendment

The unique-index-arbitrates / pre-checks-are-optimizations model is
validated (JuiceFS `doMknod`: pre-check + mustInsert with the unique
edge index as the real arbiter). Six amendments from shipped scars:

1. **Per-dialect retryable-error classifier as a first-class
   component** (JuiceFS `shouldRetry`, `sql.go:1198-1228`): the
   whole-transaction retry loop (50 attempts, quadratic backoff) is the
   backbone of correctness, not an edge case.
2. **Retryability is an orthogonal axis on the error envelope**
   (OpenDAL `ErrorStatus` {Permanent, Temporary, Persistent}): the
   backend alone knows SQLITE_BUSY vs a constraint violation; retry
   policy lives at the router/layer seam and needs the flag, not
   kind-sniffing. This is a **057 Result-envelope ripple**.
3. **Soften the FOR UPDATE and in-process-lock bans to defaults**
   (JuiceFS): REPEATABLE READ does not make read-modify-write safe on
   MySQL (31 `ForUpdate()` call sites), and inode-sharded in-process
   locks tame retry storms (throughput, not correctness). SQLite's
   single-writer reality makes an in-process write throttle nearly
   mandatory (AgentFS caps its pool at ONE connection).
4. **A SQLite lock-discipline paragraph** (libsqlfs's corruption-bought
   evolution, AgentFS concurring): write transactions `BEGIN
   IMMEDIATE` (aiosqlite defaults to deferred), `busy_timeout` at
   connect, WAL + `journal_size_limit` at first touch, no app-side
   busy-retry loops; define which Result kind SQLITE_BUSY classifies to.
5. **Classify constraint violations by SQLSTATE/driver error type,
   never message text** (SeaweedFS's `err.Error()` string-match is the
   anti-pattern; its MySQL-only wording breaks on other engines).
6. **The MSSQL catch-and-retry must run in its own transaction or
   savepoint** (SeaweedFS postgres store: a duplicate-key failure
   inside an open Postgres transaction poisons it — 23505 → 25P02 —
   which is why they default Postgres to upsert).

Also: libsqlfs's `static int max_inode` (in-process ID minting,
multi-writer collision) is the direct precedent for ULID client-side
minting; add a two-instances-one-database concurrent-create test.

### §12 conformance testing — validated everywhere; seven upgrades

The parametrized harness is the single most cross-validated decision
(JuiceFS runs one suite byte-identically over Redis/SQLite/MySQL/
Postgres/TiKV/memory; OpenDAL's env-selected behavior suite doubles as
the capability honesty check; AgentFS runs pjdfstest/xfstests against
its FUSE mount). Upgrades to adopt:

1. **An error-ordering matrix** (pjdfstest's top finding): for
   co-occurring conditions (wrong_kind ancestor + missing leaf,
   exists + wrong_kind at target, not_found vs not_empty), pin ONE
   deterministic winning kind, asserted identically across backends.
   pjdfstest's `"EEXIST|ENOTEMPTY"` alternations are the documented
   cost of leaving this unpinned; vfs controls both sides and can do
   better. Corollary: **zero per-engine conditional assertions** — an
   engine-specific `todo` is a classification bug, not a suite
   annotation.
2. **Verb × error-kind × node-kind cross-products** (pjdfstest's
   structure): parametrize each error case over node kinds at the
   offending site; enumerate move/copy target-exists cases explicitly
   (libsqlfs ships a decade-old rename-onto-empty-dir ENOTEMPTY bug
   exactly where its home-grown tests have no case).
3. **Pair every error assertion with a post-condition state probe**
   (pjdfstest): the kind can be right while a half-committed
   transaction leaves wrong state — this is what proves §3 rollback.
4. **Capability/trait-parametrized opt-in, never subclass overrides**
   (pyfilesystem2's FTP backend copy-pastes whole test methods to fudge
   timestamps; fsspec's `supports_empty_directories` is branched 43
   times *inside* test bodies — treat any semantic-divergence fixture
   as a contract fork to reject). Skip-as-pass for honestly-absent
   families (pjdfstest `supported()`/`quick_exit`).
5. **Ship the harness as an importable module** with one small
   fixtures class per backend (fsspec `tests/abstract/` +
   pyfilesystem2 `FSTestCases` shape); fresh isolated backend per test.
   Build it in Pass A — fsspec retrofitted after a decade and its suite
   can only encode the intersection of already-diverged backends.
6. **Run the suite through a router mount at a non-root path** too
   (pyfilesystem2 runs FSTestCases through MountFS at `/foo`), and
   **construct/serialize every kind in the closed taxonomy** (their
   unexercised `PatternError` shipped broken for years).
7. **Stable contract-clause IDs in test names** (AgentFS's
   `TestSpec_FS24_...` scheme) so failures name the violated clause and
   coverage is auditable. Steal fsspec's `GLOB_EDGE_CASES_TESTS` table
   (~18 distilled glob divergence cases) for the glob family.
   Concurrency gets **dedicated targeted tests outside the conformance
   suite** — pjdfstest proves races never fall out of semantics suites.

CI posture (answers the §12 open question): memory + SQLite in every
run; Postgres behind an env/marker gate; MSSQL on demand — JuiceFS's
exact shipped posture (`sql_test.go:154-158` SKIP_NON_CORE).

## 4. Gaps the spec does not currently cover

1. **Path/name length limits** (pjdfstest, contradicts): every POSIX op
   has NAME_MAX/PATH_MAX cases; the DB makes them real — unique-index
   key caps (MSSQL ~1700 bytes, Postgres btree ~2704) would surface as
   unclassified driver errors, violating the no-raw-exceptions
   criterion. `MAX_PATH_LENGTH = 1024` exists at the paths layer;
   the spec must state the byte-vs-char budget per engine, the
   classification for overlong names, and at/over-limit tests per
   mutating verb.
2. **Cursor pagination in the storage protocol** (SeaweedFS): its store
   contract bakes in (startName, limit, lastName) and its own recursive
   move/delete consume it internally. The vfs protocol returns
   materialized lists; fine for v1, but recursive verbs over a large
   mount will hit the cliff — record it as the known scaling seam and
   a candidate protocol extension.
3. **Ordering semantics pinned per dialect** (SeaweedFS): declare
   binary collation in DDL and assert identical list order across
   engines in the harness.
4. **A reclamation/GC story for soft delete and index tiers**
   (JuiceFS, Zoekt): tombstones/deleted rows and orphaned gram/version
   rows need an owner, even if v1 defers implementation.
5. **Error-path re-anchoring at one router-owned chokepoint**
   (pyfilesystem2's MountFS leaks backend-relative paths in errors;
   WrapFS's `unwrap_errors` does it right at one seam). vfs's
   `with_mount` rebase seam already is this chokepoint — add a harness
   assertion that error paths in Results surfaced through a non-root
   mount are facade-rebased, so the invariant is pinned, not assumed.

## 5. Recommended spec deltas (actionable)

1. §4: confirm option (c); strengthen the rename acceptance criterion
   to zero edge/version/chunk/content rows; add descendant-cycle
   refusal + post-move path-regeneration tests; note the read-path win
   for 059.
2. §5: commit revision to Pass A (pre-first-persistence); prefer
   counter-based encoding over `updated_at`-derived; keep `if_revision`
   as a later capability-gated feature.
3. ~~§6: resolve the open question — v1 grep LIKE-tier; grams deferred
   whole to Pass C~~ (superseded — grep ships *with* the gram index;
   see banner). Still adopted from this delta: Zoekt-shaped execution
   (permanent scan fallback, frequency-aware selection, batch recompute
   instead of the staging/fold pipeline) and LIKE-metacharacter
   escaping in the glob translation.
4. §2/§8: keep lazy first-touch, add a schema-version row written at
   creation and verified at every first touch (empty → provision;
   mismatch → loud classified refusal); index tables versioned
   drop-and-rebuild; binary collation pinned in DDL.
5. §10: add the per-dialect retryable-error classifier and the
   SQLite lock-discipline paragraph; soften FOR-UPDATE/in-process-lock
   bans to defaults-with-justification; SQLSTATE-based classification;
   MSSQL retry in its own transaction/savepoint. Propose the
   retryable/temporary flag on `ResultError` to 057 as a ripple.
6. §9: decide deleted_at-chokepoint vs trash-reparent (JuiceFS model
   fits parent_id naturally and kills the predicate hazard); either
   way spec the reclamation story.
7. §12: adopt the seven harness upgrades (error-ordering matrix,
   kind cross-products, state probes, trait parametrization,
   importable module, mounted-suite run + error-path rebase assertion,
   contract-clause IDs); CI = SQLite always, Postgres gated.
8. New: path/name length budget per engine with classified overflow;
   record cursor pagination as the known protocol-scaling seam.

## 6. Full per-repo findings

The complete reviewer outputs (per-section verdicts with file:line
evidence and lessons) are preserved verbatim below the summaries above
in the workflow journal
(`~/.claude/projects/-Users-claygendron-Git-Repos-vfs/.../subagents/workflows/wf_c1822bcc-e3a/journal.jsonl`)
and are summarized per repo here:

- **juicefs** — inode+edge schema, closed retried transactions,
  app-owned Sync2 DDL, trash-reparent deletes, one suite over six
  engines. Top: confirm (c); add the retryable-error classifier;
  soften the lock bans.
- **seaweedfs** — the path-keyed scar at production scale; cursor
  pagination in the store contract; collation retrofit; v1→v2 DDL
  ownership migration. Top: confirm (c).
- **libsqlfs** — path-keyed rename rewrites content blocks; unused
  inode column; SQLite lock discipline bought with corruption bugs;
  2-table completeness calibration. Top: confirm (c); absorb the
  SQLite pragmas paragraph.
- **opendal** — static capability declaration + correctness layer;
  12-kind taxonomy + orthogonal retryability status; layers at the
  seam; built-only lifecycle; LIKE escaping. Top: add the retryability
  flag to the Result envelope.
- **filesystem_spec (fsspec)** — undeclared capabilities decay into
  bare-except probing; retrofitted conformance suite encodes only the
  intersection; ambient transactions couple strangers; loop-binding
  compensation layer. Top: ship the harness in Pass A,
  capability-gated at family granularity.
- **pyfilesystem2** — FSTestCases as the importable-suite precedent;
  closed FSError taxonomy via per-backend translation tables;
  Info-namespace projection; WrapFS/MountFS delegation drift. Top:
  trait-parametrized harness; exercise every error kind; run the suite
  through a mount.
- **pjdfstest** — verb × errno × node-kind matrices; capability-gated
  skip-as-pass; error-ordering left unpinned is permanent scar tissue;
  zero concurrency coverage in 20+ years of POSIX tooling. Top: pin an
  explicit error-ordering matrix.
- **agentfs** — shipped (c)-model schema; BEGIN IMMEDIATE + pool-of-one
  on SQLite; closed errno taxonomy carrying verb+path; schema-version
  retrofit scar; no search/graph/versioning (competitive claims
  confirmed at source level). Top: confirm (c); mandate the
  materialized path column.
- **zoekt** — scan tier permanent; four-piece minimal gram query path;
  folded-index case strategy; delta+varint postings byte-compatible
  with rows.py; wholesale rebuild over incremental staging; tombstone
  chokepoint + compaction. Top: v1 grep LIKE-tier, grams deferred
  whole.
