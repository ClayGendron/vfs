# 179 — The storage seam as the kernel: declared capabilities, the atomic unit as a trait, the crash-point and access-path families

- **Status:** draft — cut 2026-10-24 from ADR 087 (proposed the same
  day) and the two memos it stands on. Not started. Two open
  `[NEEDS CLARIFICATION]` markers (§1.2 and §5.4).
- **Date:** 2026-10-24
- **Owner:** Clay Gendron
- **Kind:** refactor, feature and test families. The `Supports*`
  protocols regrouped by kernel group (`storage/protocol.py`,
  `storage/__init__.py`, `ops.py`); a finer declaration (`features()`,
  two new traits, the atomicity map); the fault model written once in
  `protocol.py`; the engine's error code as a structured field
  (`engine.py`, `dialects.py`); derived operations for a backend that
  lacks them (`base.py`, a new `src/vfs/derived.py`, `src/vfs/chain.py`);
  two counters (retries, the rights cache) and a test meter for native
  calls; the rights revalidation fold (`rights.py`); the conformance battery split into a
  package by kernel operation, plus three new families (the mixed
  batch, the crash points, the access paths).
- **Depends on:** ADR 087. The landed fixes `25f6da4` to `ba77449`
  (lock order, jitter, the three hidden statements, the offloaded
  write hash). Specs 174 (`if_versions`, `if_absent`, `append`), 176
  (the listing cursor), 178 (`read(range=)`), 177 (the request key),
  180 (`sweep` with a limit; `versions`), 175 (`scrub`): their
  arguments ride the regrouped protocols, and this spec names the
  feature each one declares. Spec 167 slice A (`run` and `SupportsRun`
  removed) and task 13 (the replace flag on `move` and `copy`). None of
  them blocks slices A, C, D or E; slice B's feature gate fills in as
  each lands.
- **Decisions it implements:** ADR 087 pins 1 (the kernel groups at the
  seam), 2 (a backend with no index is still served `grep`), 5 (the two
  halves of the gate, written at the seam), 7 (the atomic unit and the
  two models), 8 (the fault model, the engine code as a field), 13 (the
  retry counter), 14 (the access-path tables, three units, three
  authorities, depth). The kernel memo's §7 step 6 and the OSTEP memo's
  §5 step 8.
- **Research it stands on:**
  `../../../research/2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md`
  §2, §4.4, §4.5; `../../../research/2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md`
  §2.2, §2.7, §2.8, §2.10, §5, §6; the studies
  `studies/2026-10-24-ostep-principles-for-vfs/01-principles-intro-and-the-device-stack.md`
  (principles 6, 7, 10, 11, 16, 17; `experiments/s01/atomic_unit.py`),
  `05-crash-consistency-and-data-integrity.md` (§2.1, §2.2, §2.7,
  §2.10, §2.11; `experiments/s05/crash_points.py`),
  `03-file-system-implementation-vsfs.md` (§2.2, principles 1, 2, 14;
  `experiments/s03/access_paths.py`),
  `07-concurrency-locks-structures-events.md` (principles 2, 3, 5, 6),
  `08-virtualization-abstraction-gate-allocation-caching.md`
  (principles 1, 2, 11, 12, 14); and
  `studies/2026-10-23-filesystem-shaped-api/05-vfs-surface-audit.md`
  (§3, §6, §7). Seven new probes ran for this spec (below).

## Intent

The storage seam is the bottom half of vfs's kernel. Today it is
grouped by accident of history, it declares which verbs a backend
serves but not which arguments or indexes, and it keeps its strongest
promises unwritten. After this spec the seam is grouped the way ADR 087
draws the kernel. A backend says, in one place, what it serves, how,
and what its atomic unit is. A backend that lacks a derivable piece is
still served by the kernel, more slowly. The fault model and the two
atomicity models are written once, in `protocol.py`.

The promises then become tests. One family proves that a batch with
one bad row writes nothing to any table, on every engine. One family
crashes each verb at every mutating statement and at every named seam,
and proves the store is whole afterwards. One family pins each kernel
verb's access path: its ordered statements, rows and bytes, at three
authorities. A new statement then appears as a reviewed diff, never as
a surprise. The conformance battery is reorganised by kernel operation
so these families have a home. The Rust engine does not change.

## Terms

Defined once here. The sections below use them without redefining.

| Term | Meaning |
|---|---|
| **Seam** | The storage protocol in `storage/protocol.py`: the methods the router's one funnel calls. |
| **Kernel group** | One of the four kinds of kernel operation ADR 087 pin 1 names: filesystem core, query, history, rights. Spec 181 adds `derived` for `tree` and `edit`. |
| **Capability** | An op a backend declares in `capabilities()`. "Which verbs." Exists today. |
| **Feature** | New. An argument family or an index a backend serves itself, declared in `features()`. "Which arguments." |
| **Trait** | A quality of how a backend serves, declared in `traits()`. "How." Exists today. |
| **Derive** | The kernel serves something the backend lacks from simpler calls the backend has. Correct, slower. |
| **Atomic unit** | The largest piece of work that commits whole or not at all. |
| **Whole-batch** | An atomicity model: the whole call on one mount is one transaction. |
| **Resumable** | An atomicity model: the call commits in bounded chunks behind a durable mark, and the next call finishes the work. |
| **Access path** | The ordered list of statements one call issues, with the table each touches. Study 03's term. |
| **Golden table** | A reviewed fixture file that pins an access path. A test fails when the run differs. |
| **Crash point** | A place where a call can stop: before a mutating statement, or at a named seam in `seams.py`. |
| **Before-image** | Every row of every table of the mount, read before the call. |
| **Logical image** | The before-image with volatile columns dropped (surrogate ids, ULIDs, timestamps, epoch numbers) and every `entry_id` replaced by its entry's path. Two runs of the same work compare equal on it. |
| **Payload bytes** | The bytes of every `str` and `bytes` value bound as a parameter (sent) or returned in a row (fetched). Study 03's unit. Bodies dominate it. |

## Facts this spec stands on

EXECUTED at `ba77449` with `uv run python -I`, scripts and outputs in
the session scratchpad `179/` (copied into the landing commit's
research note only if Clay asks). Counts only. Nothing timed.

| # | Probe | Finding |
|---|---|---|
| F1 | `crash_points.py` | 11 whole-batch scenarios on a SQLite file: write batch (overwrite, create, minted parent) 10 mutating statements; the same as a named principal 10 (adds `vfs_version_subjects`); `edit` 5; `mkdir -p` three deep 6; `move` of a directory 6; `copy` of a directory 5; cascade `delete` 3; `restore` 3; `mkedge` 1; `rmedge` 1; `grant` 5. A fault at each of the 55 points left all 22 tables equal to the before-image. Zero torn. |
| F2 | `which_raise.py` | SQLAlchemy 2.0.52 runs `before_cursor_execute` outside its own wrapping `try`. A raw driver exception raised from the hook escapes the verb raw, even the dialect's own `OperationalError` class. This is why study 05's probe saw a raw raise. |
| F3 | `wrapped_raise.py` | A fault raised as `sqlalchemy.exc.OperationalError` wrapping a `sqlite3.OperationalError` with `sqlite_errorcode = 10` classifies `vfs.unavailable`, retryable, with `data = None`. The engine's code is gone; only the prose `detail` holds anything. The same wrap with code 5 (`SQLITE_BUSY`) fired once is redriven by `with_retry`, and the write succeeds. |
| F4 | `access_paths.py` | Rows counted at SQLAlchemy's `CursorResult` fetch layer equal study 03's driver-cursor counts (`read` 3 rows, 330 B; `stat` at depth 20, 21 rows, 2,122 B). That layer is the same for every dialect. |
| F5 | `access_paths.py` | System actor, non-control statements: `stat` 1, `read` 1, `ls` 2, `tree` 2, `glob` 1, `grep` (dirty side) 4, `write` create at depth 1 **6**, create at depth 2 7, overwrite **8**, `edit` **7**, `mkdir` 5, `move` 14, `copy` 13, `delete` 4, `restore` 6, `mkedge` 3, `rmedge` 3, `grants` 1. A named principal with a warm cache adds exactly 2 to each (`vfs_principal_revisions`, `vfs_relabels`); cold `read` is 7. |
| F6 | `access_paths_partial.py` | Posture `read` at `/`, alice `read_write` on `/docs`: alice's create in `/docs` is 11 statements, overwrite 13, `edit` 12. The gate's read of the target and its ancestors and of the posture rows is then repeated by the write plan's snapshot and owner label (statements 3–6 of the create path). Anonymous `read` is 4. |
| F7 | `access_paths.py` | A one-byte `edit` of a 4 MiB body now fetches 4,194,369 B (one pre-image). Study 03 measured 8,388,752 B before `99884aa`. `stat` and `read` of the same file fetch 198 B and 4,194,502 B. |
| F8 | `mixed_batch.py` | One bad row in a batch of `write` (three kinds), `write` as alice, `edit`, `delete`, `move`, `copy`, `mkedge`, `restore`: success false, the bad row's kind only, 0 commits, all 22 tables unchanged. `rmedge` differs by design: a missing triple is a warning and the rest commit. |
| F9 | `native_calls.py` | Native calls by thread: `write`, `read`, `glob` none. `grep` on the dirty side builds `ContentMatcher` on the loop and runs `hit_lines` on a worker (1 hop). Indexed `grep` adds `candidate_ids` on the loop. `glean` runs 6 native calls on the loop (`tokenize` 1, `decode_summary` 2, `lexical_score` 2, `select_blocks` 1) and 0 hops. `reindex` builds its two builders on the loop and runs every other native call on workers (10 hops). |
| F10 | grep of `seam("…")` in `src/` and of handler installs in `tests/` | 21 seams. **Five** have no test handler: `grants:before-lock`, `grants:before-write`, `reindex:before-render`, `relabel:after-chunk`, `transfer:post-snapshot`. Study 05 §2.11 counted four; it missed `transfer:post-snapshot`. |

Two READ facts complete the picture. Postgres's bulk insert streams a
binary `COPY` through the raw asyncpg connection (`dialects.py`
`bulk_insert`, L869–882). SQLAlchemy never sees the `COPY`, so neither
does any `before_cursor_execute` hook; the hook sees only the
`SELECT 1` prologue (`_COPY_PROLOGUE`, L826) that opens the driver
transaction first. And `pyodbc` exposes SQL Server's SQLSTATE in
`args[0]` but its native error number only inside the message text.

## 1. The seam regrouped by kernel group

### 1.1 The groups, declared once in `ops.py`

Spec 181 §2.1 defines `OpGroup`, `OP_GROUPS` and `GROUP_OF`. This spec
lands first, so it adds them **exactly as 181 writes them**, and 181
then only reorders the surfaces (rebase note below). The seam reads
them; it defines no group list of its own.

Ops that sibling specs add join a group here, so the drift test stays
total: `versions` (180) and `scrub` (175) join `history`.

### 1.2 The protocols

Each protocol is one family. A backend implements a family whole or
not at all (the existing `test_families_are_all_or_nothing`). Families
follow the kernel groups, not the write gate. `MUTATING_OPS` stays the
write gate's set in `ops.py`; it is a different axis (181 §2.1 says
so for the public surface).

```python
# storage/protocol.py — the families, by kernel group

# Filesystem core
class SupportsFileRead(Protocol):          # stat, ls, read — the verb minimum
class SupportsFileWrite(Protocol):         # write, mkdir, delete, move
class SupportsCopy(Protocol):              # copy — optional; derived when absent (§4)

# Derived verbs a backend may answer natively
class SupportsTree(Protocol):              # tree — optional; derived from ls
class SupportsEdit(Protocol):              # edit — optional; derived from read + guarded write

# Query
class SupportsPatternSearch(Protocol):     # glob, grep — optional; derived as a scan
class SupportsGlean(Protocol):             # glean
class SupportsGraph(Protocol):             # graph
class SupportsEdges(Protocol):             # mkedge, rmedge

# History
class SupportsTrash(Protocol):             # restore, sweep
# spec 180's SupportsHistory (versions) and SupportsGarbage, spec 175's SupportsScrub

# Rights
class SupportsRights(Protocol):            # grant, revoke, grants, posture, add_member, remove_member

# Maintenance — never routed
class SupportsTraits(Protocol):            # traits()
class SupportsFeatures(Protocol):          # features() — new, §2
class SupportsReindex(Protocol):           # reindex()
class SupportsClose(Protocol):             # close()

class StorageBackend(SupportsFileRead, Protocol):
    name: str
    description: str
    def capabilities(self) -> frozenset[Op]: ...
```

- `SupportsRead`, `SupportsMutation`, `SupportsGrants` and
  `SupportsRun` are deleted, not aliased. There is no legacy to keep.
  If spec 167 slice A has not landed, this task deletes `SupportsRun`
  and `run` as 167 task 1 lists them.
- The minimum shrinks from four methods to three. `tree` leaves it
  because the kernel derives it (ADR 087 pin 1 calls `tree` a derived
  verb).
- `_FAMILY_OPS` (L508) is rewritten to these families and
  `storage_ops` keeps its contract.
- `vfs.storage.__init__` exports the new names.
- The method names `delete` and `move` follow ADR 087 pin 3's lean.
  [NEEDS CLARIFICATION: pin 3 is pending Clay. If he picks `remove`
  and `rename`, the seam methods rename with the public verbs in the
  same commit, and `SupportsFileWrite`'s signature changes; nothing
  else in this spec does.]

### 1.3 The per-call arguments, owned elsewhere

The regrouped protocols carry every kernel argument. This spec does
not define any of them. It names the feature each one declares (§2).

| Method | Argument | Owning spec | Feature | Without the feature |
|---|---|---|---|---|
| `ls`, `tree`, `glob` | `after`, `limit`; the resumption key on `Result` | 176 | `ls_cursor` | derive: the router pages the full answer (§2.3) |
| `read` | `range` | 178 | `read_range` | derive: the router slices (178 §6) |
| `write` | `if_versions`, `if_absent`, `append` | 174 | `write_preconditions` | refuse |
| `move`, `copy` | the replace flag | 167 task 13 (ADR 087 pin 3) | `transfer_replace` | refuse |
| every mutating method | the request key | 177 | `request_key` | refuse |
| `sweep` | `limit`, `after` | 180 | `sweep_cursor` | refuse |
| `read` | `version` | 180 | (an op, `versions`) | `unsupported`, as 180 says |

The table is the one vocabulary. The sibling specs use these names
(notes below).

## 2. A finer declaration: ops, features, traits

### 2.1 The rule

Three declarations, three questions, never mixed:

| Declaration | Question | Type | Absent means |
|---|---|---|---|
| `capabilities()` | Which verbs? | `frozenset[Op]` | the verb is refused, or derived (§4) |
| `features()` | Which arguments and indexes does it serve itself? | `frozenset[Feature]` | derived or refused, per feature (table above and §2.2) |
| `traits()` | How does it serve? | `Mapping[str, str]` | not declared; a caller assumes nothing |

A trait with exactly one possible value is a feature in disguise.
Spec 178 drafts `read_range` as a one-valued trait (`"engine"`); this
spec makes it a feature (rebase note).

### 2.2 The feature vocabulary (`ops.py`)

```python
Feature = Literal[
    "ls_cursor", "read_range", "write_preconditions", "transfer_replace",
    "request_key", "sweep_cursor",
    "segment_index", "trigram_index", "lexical_index", "vector_index",
]
FEATURES: Final[frozenset[str]] = frozenset(get_args(Feature))

FEATURE_ARGUMENTS: Final[dict[Op, dict[str, Feature]]]
"""Each argument that needs a feature, by op; an argument at its default needs none."""

FEATURE_FALLBACK: Final[dict[Feature, Literal["derive", "refuse"]]]
"""What the router does for a call that needs a feature its mount lacks."""
```

- `Feature` lives in `ops.py` beside `Op`, because `protocol.py`
  imports `ops.py` and never the reverse.
- `FEATURE_ARGUMENTS` starts empty and gains one row as each owning
  spec lands. A drift test pins: every key of every inner dict is a
  parameter of that op in `PARAMS`.
- The four index features are not argument-bound. Each one says the
  backend keeps that index:

| Index feature | What it serves | Without it | Trait it must agree with |
|---|---|---|---|
| `segment_index` | `glob` by path segments (`vfs_segments`) | the backend scans names, or the kernel derives `glob` | — |
| `trigram_index` | `grep`'s candidate set (`vfs_grams_posting_list`) | the scan tier | `grep_tier == "indexed"` iff present |
| `lexical_index` | `glean`'s BM25 leg (`vfs_lex_*`) | no `glean` | `glean_signals` in `{"lexical", "hybrid"}` iff present |
| `vector_index` | `glean`'s vector leg (`vfs_chunks.embedding`) | lexical only | `glean_signals == "hybrid"` iff present |

A consistency test reads both declarations of every backend in the
conformance legs and fails on any disagreement.

`DatabaseStorage.features()` (new, beside `capabilities()` at
`backend.py:276`) answers the argument features whose specs have
landed, plus `segment_index`, `trigram_index` and `lexical_index`
always, and `vector_index` when an embedder is configured and
`profile.vector_distance != "none"`. On the generic floor (an unknown
dialect) `glean` is already withheld (`backend.py:282`), so
`lexical_index` and `vector_index` are withheld with it.

### 2.3 How the router uses features

- `MountMeta` (`base.py:141`) gains `declared_features`, a snapshot
  of `storage.features()` taken at bind, beside `declared_caps`, and
  refreshed by `remount(refresh_caps=True)`. A backend without
  `SupportsFeatures` snapshots the empty set. `MountInfo` gains
  `features`.
- The feature gate runs in `_gate_entry` (`base.py:2852`) right after
  the capability check, so its order is: capability, feature, grammar,
  permission. For each argument of the call named in
  `FEATURE_ARGUMENTS[op]` at a non-default value, when the binding
  lacks the feature:
  - **derive**: the router calls the backend without the argument and
    shapes the answer itself. `read_range` slices each body (178's
    `slice_rows`). `ls_cursor` takes the full listing and cuts the
    page at the keyset `(parent path, name)` the native path uses, and
    mints the same resumption key. The answer is the same rows; the
    cost is the full listing, and the docstring says so (never a cap).
  - **refuse**: `vfs.unsupported`, with `data["vfs.feature"]` naming
    the feature, before any storage call. A precondition checked
    outside the write's transaction is the check-then-use gap the
    precondition exists to close, so the kernel never fakes one.

### 2.4 The `atomic_unit` trait

`TraitKey` (`protocol.py:73`) gains `"atomic_unit"`. `TRAIT_VALUES`
gains:

| Value | Promise | Who declares it |
|---|---|---|
| `"call"` | One mutation call commits whole or not at all, at any batch size. | `DatabaseStorage` |
| `"mount"` | Whole per mount inside the call; a call that spans mounts can land in part. | an adapter that presents a router as a backend |
| `"row"` | Each row commits on its own. | a wire backend whose peer has no batch transaction |

Absent means not declared. A caller then assumes `"row"`, the weakest
promise. The router itself never declares a trait; its `write`
docstring says the cross-mount case once (§3.2).

### 2.5 The `durability` trait, from the live connection

OSTEP memo §2.10: `InMemoryStorage` is SQLite `:memory:` and declares
`durability: "full"` (`backend.py:296–300`), and nothing reads
Postgres's `synchronous_commit`. The declaration should come from the
engine.

- `TRAIT_VALUES["durability"]` gains `"none"`: nothing survives the
  process.
- `DialectProfile` gains one field, `durability_probe: str | None`, a
  query whose single answer decides. SQLAlchemy takes no position on
  durability, so the field is justified by CLAUDE.md's rule.
- `EngineHost` reads it once at first touch and keeps
  `self.durability`. `traits()` reports it.

| Engine | Probe | `full` when | otherwise |
|---|---|---|---|
| SQLite | none; the URL and the profile | a file database (`synchronous = FULL` and WAL are the profile's own settings) | `"none"` for `:memory:` |
| PostgreSQL | `SHOW synchronous_commit` | not `off` | `"relaxed"` |
| MariaDB | `SELECT @@innodb_flush_log_at_trx_commit` | `1` | `"relaxed"` |
| SQL Server | `SELECT delayed_durability_desc FROM sys.databases WHERE database_id = DB_ID()` | `DISABLED` or `ALLOWED` (vfs never asks for delayed commit) | `"relaxed"` for `FORCED` |
| Oracle | `SELECT value FROM v$parameter WHERE name = 'commit_wait'` | empty or `WAIT` | `"relaxed"`; not declared when the role may not read `v$parameter` |
| generic floor | none | — | not declared (as today) |

One statement at first touch, never per call.

## 3. The atomicity models and the fault model, written at the seam

### 3.1 Every mutating method names its model

```python
# storage/protocol.py
Atomicity = Literal["whole_batch", "resumable"]

METHOD_ATOMICITY: Final[dict[str, Atomicity]] = { ... }
"""Each mutating seam method's atomicity model; the conformance families drive both."""
```

| Method | Model | Why (code) |
|---|---|---|
| `write`, `edit`, `mkdir` | whole_batch | `_execute_write`: one writer transaction, commit iff success (`backend.py:1666`, `_mutate` L1718) |
| `delete`, `restore`, `move`, `copy` | whole_batch | `_execute_topology`: one serialized transaction (L1709) |
| `sweep` | whole_batch today; resumable when spec 180's limit lands | `sweep_rows` in one topology transaction |
| `mkedge`, `rmedge` | whole_batch | `_execute_write`. `rmedge`'s missing triple is a warning by design, so its other rows commit (F8) |
| `grant`, `revoke`, `add_member`, `remove_member` | whole_batch | `_grant_write`: the revision bump, the gate and the body in one transaction (L1577) |
| `posture` | resumable | the posture row commits whole; the relabel then runs one bounded chunk per transaction behind the `vfs_relabels` mark (`_settled`, L1603) |
| `reindex` | resumable | the lease, then render, chunk, build, publish, reclaim, segment and edge passes, signals, embed, each in its own transactions (`_reindex_phases`, L1187); the dirty flags and the epoch are the marks |

A drift test pins: the keys are exactly `WRITE_GATED_OPS | {"reindex"}`
plus the mutating ops sibling specs add.

### 3.2 The docstring, written once

`protocol.py`'s module docstring (L1–49) gains three sections after its
current text. The text is the contract; ADR numbers stay out of it.

> **The atomic unit.** One mutation call on one mount commits whole or
> not at all, at any batch size: the entry rows, the path segments,
> the fs edge mirror, the version rows, the bodies and the parent
> bumps, with the dirty flag that says the search indexes no longer
> cover a row. The indexes catch up later in `reindex`'s own
> transactions, and the search verbs scan the dirty side meanwhile. A
> whole-batch call's log and lock footprint grows with its bytes; vfs
> declares no batch cap. A resumable call commits in bounded chunks
> behind a durable mark, and the next call finishes what one left.
> `METHOD_ATOMICITY` names each method's model. The `atomic_unit`
> trait lets a backend that cannot keep the promise say so. A batch
> that spans two mounts is atomic per mount only.
>
> **The fault model.** The engine owns media faults and the atomic
> commit; the `durability` trait says what a commit means on this
> mount. vfs owns the logical faults above the engine: a body written
> under the wrong entry, a lost body insert, and the out-of-band writer,
> an ETL job or migration holding SQL credentials. `content_hash` on
> the entry row is vfs's detector. Engines fail partly, not cleanly: a
> timeout, a deadlock, a lost serialization race, a dropped connection.
> Each classifies and never raises: a retryable outcome restarts the
> whole method from a fresh snapshot, an exhausted restart is a
> retryable `conflict`, a dropped connection is `backend_unavailable`,
> and the engine's own code rides `data["vfs.engine_error"]`. The
> tables are private to vfs; a row edited outside these methods is
> outside the contract. Identities are never reused: entry ids are
> ULIDs, epochs are skipped, a delete is a tombstone.
>
> **The gate.** The gate has two halves. The router's half judges
> parameters, capability, features, the reserved grammar and the mount
> permission maps. This seam's half judges grants inside the statement
> that reads or writes the rows. A front that bypassed either half
> would bypass the gate. In process the gate is a convention: trusted
> code may hold the system authority and this object. On the wire and
> in a WebAssembly guest the gate is a wall: a token in, an `Authority`
> out, and no other door.

`base.py`'s module docstring gains one sentence pointing at these
sections, and `VirtualFileSystem.write`'s docstring gains the
cross-mount sentence. Spec 181 §5 restates the trust tiers on the
public surface; it cites this text rather than writing a second copy
(rebase note).

### 3.3 The engine's code as a structured field

ADR 076: no consumer parses `message`. F3 shows the engine's code
survives only there today.

```python
# storage/protocol.py — the one key, part of the fault model
ENGINE_ERROR_KEY: Final = "vfs.engine_error"

# storage/backends/database/dialects.py
class EngineCode(NamedTuple):
    dialect: str
    sqlstate: str | None
    code: int | None
    name: str | None

    def as_data(self) -> dict[str, str | int]: ...   # the present fields only, JSON-native

def engine_code(dialect: str, exc: BaseException) -> EngineCode | None:
    """The engine's own code behind *exc*, read off driver attributes, never message text."""
```

`engine_code` walks `driver_origin` (L905) and reuses `_sqlstate_of`
(L1019) and `_driver_code_of` (L1034). It returns `None` when the
driver carries nothing structured.

| Engine (driver) | `sqlstate` | `code` | `name` |
|---|---|---|---|
| SQLite (`sqlite3` via aiosqlite) | — | `sqlite_errorcode` (extended) | `sqlite_errorname` |
| PostgreSQL (asyncpg) | `sqlstate` | — | — |
| SQL Server (pyodbc via aioodbc) | `args[0]` | — (pyodbc puts the native number only in prose) | — |
| MariaDB (aiomysql) | — | `args[0]` | — |
| Oracle (python-oracledb) | — | `args[0].code` | `args[0].full_code` (`ORA-00060`) |

- `EngineHost.classify_failure` (`engine.py:329–355`) passes
  `data={ENGINE_ERROR_KEY: code.as_data()}` to `classified` on every
  branch when `engine_code` returns one. The kinds do not change.
- The exhausted-retry `conflict` in `_execute` and `_mutate`
  (`backend.py:1640–1643`, L1741–1745) carries the same field read off
  `exc.__cause__`, which `with_retry` sets (`engine.py:324`).
- The key is `vfs.`-prefixed, so the envelope's rule holds: producers
  of `vfs.*` errors write only `vfs.` keys.
- The message keeps its `detail`. It stops being the only carrier.

## 4. Derived operations for a backend that lacks them

ADR 087 pin 2: a backend with no index is still served `grep` through
the kernel. Pin 1: `tree` and `edit` are derived verbs. The kernel memo
§4.4: a backend may declare a native `tree` or `copy` and the kernel
uses it. `DatabaseStorage` declares everything natively, so nothing
changes for it. A partial third-party backend, a snapshot or a wire
peer gains these verbs.

### 4.1 Where it lives

- `src/vfs/derived.py` (new): one async function per derived op,
  taking the binding's storage, the call's arguments and its
  authority, and returning a `Result`. It imports nothing from
  `vfs.storage.backends`.
- `src/vfs/chain.py` (new): the rows-in-hand filters lifted out of
  `base.py` (`_glob_rows_in_hand` L1817, `_grep_rows_in_hand` L1858)
  as two plain functions. The router's chained path and the derived
  scans call the same function. Spec 181 §4 builds its public
  `vfs.chain.glob`/`grep` on them (rebase note).
- `MountMeta.caps` becomes `(declared_caps | derivable) - deny_ops`,
  where `derivable` comes from one table, `DERIVED_FROM` in `ops.py`.
  `MountMeta` keeps `native_caps = declared_caps - deny_ops`.
  `MountInfo` gains `derived`, the ops served by derivation.
- `_call_storage` (`base.py:2956`): the arms for `tree`, `copy`,
  `edit`, `glob` and `grep` call the backend when the op is in
  `native_caps`, else `derived.<op>(...)`. The match still ends in
  `assert_never`. A mask that denies `ls` also removes the derived
  `tree`, because derivation reads the masked set.

### 4.2 The table

| Op | Built from | Bound at a 10,000-row tree | Atomicity | Waits on |
|---|---|---|---|---|
| `tree` | `ls(observations=frontier)` per depth level, breadth first, path order | one `ls` call per level; each `ls` chunks its `IN` list by `membership_budget`; with `ls_cursor`, pages | read | — |
| `copy` | `tree` (or `stat`) of each source, `read` of its files in batches, then one `write(entries=…, if_absent=True, parents=True)` and `mkdir` for empty directories | reads batched by `DERIVED_READ_ROWS` (256 observations a call); the write is one call, chunked by storage | the write is whole-batch on the destination mount; the source is a read snapshot, not locked (the docstring says so) | — |
| `edit` | `read` of each target, the replace engine (`storage/replace.py`) in memory, then one `write(if_versions={path: version})` | one read call, one write call | whole-batch write; a rival between the read and the write classifies 174's precondition kind | 174 (`write_preconditions`); refused without it |
| `glob` | `tree` from each pattern's literal prefix, then `chain.filter_glob` | the walk is the bound; `max_count` stops it early | read | — |
| `grep` | `tree` from each scope root, `read` in batches of `DERIVED_READ_ROWS`, then `chain.filter_grep` | batches by rows and by `DERIVED_READ_BYTES` (32 MiB, the offload batcher's budget); the grep wall budget (`WALL_TIME_BUDGET`) applies and a cut answers as native grep's does | read | — |

- The derived `grep` serves the scan tier only. It declares no index,
  so a pattern the indexed tier would refuse is served.
- Match batches at or above `MEASURE_OFFLOAD_BYTES` (`base.py:137`)
  run on the loop's default executor, the same hop the router already
  uses to measure a large write body. Below it they run inline.
- Spec 181 §5's `edit` oracle is this derivation; its parity test is
  181's (rebase note).

## 5. Counters: retries, the rights cache, and the fold

### 5.1 A retry counter per verb (ADR 087 pin 13)

ADR 025's revisit trigger needs a count of redrives. `with_retry`
keeps none (study 07 principle 6).

- `EngineHost.with_retry(fn, *, op: str)` (`engine.py:298`). The two
  callers already know the op (`_rows` L1650, `_mutate` L1718);
  first touch passes `"first_touch"`.
- `EngineHost.retries: dict[str, RetryTally]`, where
  `RetryTally(redrives: int, exhausted: int)`. A redrive is an
  attempt after the first. Exhausted counts calls that left as
  `StaleSnapshot` after the last attempt. Plain integers on the loop
  thread; the borrowed path is single-loop by intent (`engine.py`
  docstring), so no lock.

### 5.2 Hits, misses, stale entries and evictions on `RightsCache`

Study 08 principle 14: a cache helps only while the working set fits,
and nothing measures it.

- `RightsCache` (`rights.py:250`) gains `counts() ->
  RightsCacheCounts(hits, misses, stale, evicted)`.
- `ids()` returning `None` is a miss. `get()` under a different key
  drops the entry: stale, and a miss. `get()` under the same key is a
  hit. Each pop in `put()`'s bound loop (L295) is an eviction.
- The system authority never reaches the cache
  (`resolve_authority` L350) and is never counted.

### 5.3 Fold the two revalidation reads into one statement

F5: a warm named `read` is 3 statements, two of them only to recheck
the cache: `principal_revision` (`revision.py:79`) and `inflight_marks`
(`labels.py:186`). On a remote engine each is a round trip.

```sql
SELECT NULL AS path_prefix, MAX(revision) AS revision
  FROM vfs_principal_revisions WHERE principal_id IN (:ids)
UNION ALL
SELECT path_prefix, revision FROM vfs_relabels
```

- One new function, `stamps_and_marks(session, tables, profile,
  membership_budget, ids) -> tuple[int, tuple[Mark, ...]]`, in
  `rights.py`. The first arm's `NULL` is a typed `null()` cast to the
  `path_prefix` column's type, so every engine unifies the arms. The
  stamp row is the one with a `NULL` prefix; the marks sort by prefix
  in Python, as `inflight_marks` orders them today.
- Arm order is the current read order: stamps first, marks second.
  Postgres's `Append` and SQL Server's `Concatenation` run their
  inputs in order (INFERRED from the engines' plan operators, not
  executed here; the engine-leg coherence tests in
  `tests/storage/database/test_coherence.py` are the check). On the MVCC engines the statement reads one
  snapshot, which is stronger than two statements. On SQL Server's
  locking read committed it is the same as two statements in that
  order. So the fold never weakens the revalidation.
- Bound: the stamp arm's `IN` list is one `membership(...)` chunk. The
  fold runs only when `len(ids) <= membership_budget`, which is every
  real caller (a caller's subjects and their groups are dozens). Past
  it, the current two-step path runs, chunked by `chunked` as today.
- `resolve_authority` uses it on the hit path (L354–358) and on the
  miss path (L369–370).
- Result on SQLite: warm named `read` 3 → 2; warm anonymous `read`
  4 → 3; cold named `read` 7 → 6. Every named and anonymous row of
  every golden table drops by one statement, reviewed as one diff.
- Not chosen: folding the stamps into the data statement. The data
  statement is built from the resolution the stamps validate, so the
  two cannot be one statement without compiling the view twice.

### 5.4 Where the counters are read

`DatabaseStorage.counters() -> StorageCounters`, a `NamedTuple` of
`retries` (a copy of §5.1's dict) and `rights` (§5.2). It is a
backend method, not routed, like `first_touch` and
`install_extensions`. Tests and an operator's exporter read it.
[NEEDS CLARIFICATION: should `serve()` deployments read the counters
through the router (an admin method on `VirtualFileSystem` that walks
the bindings), or does a backend method suffice until spec 171 asks
for a metrics endpoint?]

The native-call count of ADR 087's study 07 principle 3 is a test
meter, not a production counter (§9.6): it needs no code in `src/`.

## 6. The conformance battery, reorganised by kernel operation

### 6.1 The package

`tests/support/storage_contract.py` (2,784 lines, 220 tests) and
`tests/support/grants_contract.py` (1,247 lines, 75 tests) become one
package. Each file is a mixin of test methods. `StorageContract` and
`GrantsContract` are composed in `__init__.py` from the mixins, so
`tests/storage/test_conformance.py` changes only its import line, and
every pytest node id (`TestSqliteConformance::test_…`) stays the same.

| New file | Kernel group | Rows it takes (current line ranges) | Tests |
|---|---|---|---|
| `contract/_base.py` | shared | L1–207: the module docstring, `ConformanceBackend`, `needs`, the helpers, the graph and meet worlds, the `storage` and `_capability_gate` fixtures; plus the new `faults`, `reopen` and `meter` fixtures (each skips by default) | 0 |
| `contract/fs_shapes.py` | filesystem: `stat`, `ls`, `read`, `tree` | ls/read/tree/stat shapes L319–425 (13); per-row classification of batched reads L2042–2150 (9); meta-scope `ls`/`tree` L1319, L1327 (2); `tree` under a metacharacter name L1243 (1); bytes listings L2748 (1) | 26 |
| `contract/fs_write.py` | filesystem: `write`, `mkdir`, `edit` | POSIX parent/site L208–318 (13); the descent ladder L426–461 (3); `edit` L642–679 (4); version stamping L2151–2276 (9); committed-state observations L2277–2366 (6); metacharacter write/read L1236 (1); bytes L2668, L2686, L2700, L2715 (4) | 40 |
| `contract/fs_transfer.py` | filesystem: `move`, `copy`, `delete` | move/copy L462–641 (17); the delete leaf table L680–775 (8); overlapping batch targets L2367–2481 (8); occupant identity and unicode L2482–2569 (7); metacharacter delete and move L1275, L1289, L1303 (3); extension re-derived on move/copy L1080–1117 (4); bytes copy L2725 (1) | 48 |
| `contract/history.py` | history | `restore` L776–905 (12); `sweep` L906–976 (7); bytes delete/restore L2737 (1) | 20 |
| `contract/query_glob.py` | query: `glob` | the glob rows L977–1229 without L1080–1117 (23); metacharacter prefix and literal L1252, L1265 (2) | 25 |
| `contract/query_grep.py` | query: `grep` | meta scope L1341 (1); grep modes L1355–1434 (11); the pattern-class taxonomy L1435–1492 (4); reindex serving L1493–1629 (9); bytes rendered and grepped L2758 (1) | 26 |
| `contract/query_glean.py` | query: `glean` | glean L1630–1783 (11); the embed step L2591–2631 (3) | 14 |
| `contract/query_graph.py` | query: `graph`, `mkedge`, `rmedge` | mkedge L1784–1881 (7); graph L1882–2041 (10) | 17 |
| `contract/maintenance.py` | maintenance | declared traits L2632–2662 (3); lifecycle L2571–2590 (1); the new feature/trait consistency rows (§2.2) | 4 + new |
| `contract/rights_view.py` | rights: what a caller sees | `grants_contract.py`: hidden rows L148–283 (15); owner floor L284–302 (2); posture L303–358 (5); everyone level L712–801 (4); ranked search L1072– (4) | 30 |
| `contract/rights_gate.py` | rights: what a caller may change | `grants_contract.py`: the write gate L359–560 (20); the trash L561–711 (5); the grant verbs L802–860 (6); groups L861–961 (9); the ladder L962–1071 (5) | 45 |
| `contract/atomicity.py` | new family (a) | §7 | new |
| `contract/crash.py` | new family (b) | §8 | new |
| `contract/access_paths.py` | new family (c) | §9 | new |

The 220 and the 75 add up exactly (26 + 40 + 48 + 20 + 25 + 26 + 14 +
17 + 4 = 220; 30 + 45 = 75). Version stamping stays whole in
`fs_write.py` though some of its rows drive `move` and `copy`: it is
one law, the stamp law, and splitting it would scatter it.

Two things the split fixes on the way. The `sweep` banner today
covers 27 glob tests (L977–1229 have no banner of their own); they get
one. And the split is a pure move: no assertion changes in the same
commit.

### 6.2 No test lost

- Before the split, `pytest --collect-only -q
  tests/storage/test_conformance.py` is saved. After it, the same
  command's output equals it, line for line. Two mixins that defined
  the same method name would shadow one test silently; this
  comparison is what catches it.
- `storage_contract.py` and `grants_contract.py` are deleted in the
  same commit.
- New families add node ids; they never rename one.

### 6.3 Fixtures the new families need

The families stay engine-blind in their assertions (the contract's
rule: zero per-engine conditional assertions). What is engine-shaped
is supplied by each leg in `test_conformance.py`:

| Fixture | What it is | Memory | SQLite file | Server legs |
|---|---|---|---|---|
| `faults` | an `EngineFaults` for the leg (§8.1) | provided | provided | provided |
| `reopen` | a callable returning a fresh handle on the same store | the same object (an in-memory database dies with its handle, so this leg proves rollback, not durability) | a new `DatabaseStorage` on the same file URL | `server_schemas.sibling` |
| `meter` | an `AccessMeter` bound to the leg's engine (§9.1) | skipped (same engine as SQLite) | provided | provided |

A backend whose leg provides none of them skips the three families
with a reason, like a missing capability.

## 7. Family (a): the mixed good-and-bad batch

Study 05 §2.1: the contract pins whole-batch atomicity for `edit`,
`move` and `delete`, never for `write`, and the one SQLite test that
does counts only entry and content rows.

- **Scenarios**, every one on every leg (F8 is the SQLite run):

| Verb | Good rows | The bad row | Expected error |
|---|---|---|---|
| `write(parents=True)` | an overwrite, a create, a create that mints a parent, a bytes create | a file under a file | `wrong_kind` |
| `write(if_absent=True)` | a create | an occupied path | `exists` |
| `write` | an overwrite | a path that is a directory | `wrong_kind` |
| `write` as alice | an overwrite (mints `vfs_version_subjects`) | a file under a file | `wrong_kind` |
| `edit(observations=…)` | a match | a row with no match | `invalid` |
| `delete(observations=…)` | a file | a missing path | `not_found` |
| `move` | a file | a missing source | `not_found` |
| `copy` | a file | an occupied destination | `exists` |
| `mkedge` | an edge | a missing endpoint | `not_found` |
| `rmedge` as alice | an edge she may change | an edge whose source she may not modify | `permission_denied` |
| `restore` | — | a live row | `exists` |

- **Assertions**: `success is False`; the errors are exactly the bad
  rows' kinds at their paths; the commit count is 0, counted by
  SQLAlchemy's `commit` connection event (portable, no driver
  knowledge); and the before-image equals the after-image on all 22
  tables of `VFSTables`.
- **The 10,000-row variant** (`slow`): 10,000 good creates plus one
  bad row at the end. 0 commits, 0 rows under the target directory in
  every table. Study 01's case 4 is the SQLite precedent.
- **The tear, declared**: one router-level test mounts two
  `InMemoryStorage` and writes one good row to each with the bad row on
  the second. The first mount's row lands, the second's does not, and
  `traits()["atomic_unit"] == "call"` on both. The test's name says
  this is the declared behaviour (study 01 case 2).
- `rmedge`'s missing triple stays a warning. A separate row pins that
  the rest of its batch commits (F8), so "whole-batch" never reads as
  "any non-error aborts".

## 8. Family (b): crash at each mutating statement, and at each seam

### 8.1 The statement injector

```python
# tests/support/faults.py
class EngineFaults:
    """Fails the Nth mutating statement of the next call, once, with an engine-shaped fault."""

    def __init__(self, storage: DatabaseStorage, *, fatal: Fault, retryable: Fault) -> None: ...
    def at(self, n: int, *, retryable: bool = False, times: int = 1) -> ContextManager[FaultRecord]: ...

class Crash(BaseException):
    """The process died here: nothing below a seam may catch it."""
```

- The hook is `before_cursor_execute` on `storage._host.engine.sync_engine`.
  A statement is mutating when its first word is `INSERT`, `UPDATE`,
  `DELETE` or `MERGE`. On the Postgres leg the `COPY` prologue
  (`SELECT 1`, issued only by `bulk_insert`'s copy mode) also counts:
  it is the last point SQLAlchemy sees before each `COPY`, so failing
  it is failing at that `COPY`'s start, and failing the statement
  after a `COPY` covers its end.
- Because the hook runs outside SQLAlchemy's wrapping (F2), the hook
  raises the wrapper itself: `sqlalchemy.exc.OperationalError(statement,
  params, orig)`, where `orig` is the leg's fault object. That is the
  shape a real driver failure has when it reaches vfs.
- `FaultRecord` keeps the ordered list of mutating statements
  (verb and first table) and how many times the fault fired. `times`
  re-arms the fault at the same N on each retry attempt, which is how
  criterion 12 exhausts the retries.

The fault objects mimic each driver's attributes exactly as
`engine_code` and `is_retryable` read them, and nothing else:

| Leg | Fatal fault (classifies `unavailable`) | Retryable fault (redriven) |
|---|---|---|
| SQLite | `sqlite3.OperationalError` with `sqlite_errorcode = 10`, `sqlite_errorname = "SQLITE_IOERR"` | `sqlite_errorcode = 5` (`SQLITE_BUSY`) |
| PostgreSQL | an exception with `sqlstate = "58030"` (I/O error) | `sqlstate = "40P01"` |
| SQL Server | `args = ("HY000", …)` | `args = ("40001", …)` |
| MariaDB | `args = (1030, …)` | `args = (1213, …)` |
| Oracle | `args = (error,)` with `error.code = 1114`, `error.full_code = "ORA-01114"` | `error.code = 60` |

None of the fatal codes is a disconnect to `dialect.is_disconnect`, so
each classifies `vfs.unavailable`, retryable, and the family can also
assert `data["vfs.engine_error"]` (§3.3).

### 8.2 The images

`tests/support/images.py`:

- `full_image(storage)`: `SELECT *` of each of the 22 tables, every
  row as a tuple of `repr` values, sorted in Python. Exact.
- `logical_image(storage)`: the same, through `LOGICAL_COLUMNS`, a
  per-table declaration of which columns are kept, which are dropped
  as volatile, and which `entry_id` columns are replaced by the entry's
  path. A drift test fails when a table gains a column that is in
  neither list, so a new column forces a decision.

### 8.3 Whole-batch verbs: crash at every N

For each scenario of F1, on every leg:

1. Seed the world. Take the before-image.
2. Run the verb once with no fault (`faults.at(∞)`) **on a sibling
   store** seeded the same way: this is the reference, and its
   `FaultRecord` gives M, the number of mutating statements on this
   leg. M is read, never hardcoded, because it differs by engine.
3. For N = 1 … M: run the verb with the fatal fault at N; assert the
   Result is `vfs.unavailable`, retryable, with the engine code; close
   the handle; `reopen`; assert the full image equals the before-image.
   Because it does, the next N reuses the same store. One seed per
   scenario, M + 1 runs.
4. For N = 1 … M again with the retryable fault: assert success, the
   logical image equals the reference's logical image, and
   `counters().retries[op].redrives == 1`.

The scenarios are F1's eleven, plus `sweep` of one expired root and
`revoke`, `add_member`, `remove_member` (every whole-batch method in
§3.1). The SQLite counts of F1 (10, 10, 5, 6, 6, 5, 3, 3, 1, 1, 5)
are the baseline the SQLite leg must reproduce.

### 8.4 What differs per engine

| Leg | What the hook sees | Locking while it fails | Reopen |
|---|---|---|---|
| SQLite | every statement, including the driver bulk path, which goes through `exec_driver_sql` | one writer lock from the plan's first read (`BEGIN IMMEDIATE`); no rival can interleave | a new `DatabaseStorage` on the same file |
| PostgreSQL | Core statements; each `COPY` only as its `SELECT 1` prologue (§8.1) | the op snapshot at `REPEATABLE READ`; topology at `READ COMMITTED` under the advisory lock; identity sequences advance on rollback, which no image compares | `sibling` on the same schema |
| SQL Server | Core statements; creates arbitrate by catch-and-retry under a savepoint, so the create path and M differ from the upsert engines | `UPDLOCK, FORCESEEK` key locks; the fault releases them on rollback | `sibling` |
| MariaDB | Core statements and the driver executemany through `exec_driver_sql` | InnoDB rolls the whole transaction back on a failure, the same as vfs's own rollback here | `sibling` |
| Oracle | Core array DML | a failed statement rolls back only itself; vfs then never commits, and the session close rolls back the rest | `sibling` |

### 8.5 Every seam

`seams.py` holds 21 named points (F10). Each gets a row in one table,
`SEAM_CLASSES`, in `contract/crash.py`. A drift test parses `src/` for
`seam("…")` calls and fails when a name has no row, so a seam added
later must declare its class and gain its test.

| Class | Seams | Handler | Assertion |
|---|---|---|---|
| inside a whole-batch transaction | `write:before-apply`, `delete:post-snapshot`, `delete:post-collect`, `restore:post-resolve`, `transfer:post-snapshot`, `transfer:post-collect`, `purge:post-collect`, `purge:pre-entry-delete`, `mkedge:before-insert`, `grants:before-lock`, `grants:before-write` | raises `Crash` | the call raises `Crash`; after `reopen` the full image equals the before-image |
| inside a read | `grep:after-pointer-read`, `glean:after-pointer-read` | raises `Crash` | the full image is unchanged |
| resumable: `reindex` | `reindex:before-render`, `reindex:before-render-land`, `reindex:before-chunk-split`, `reindex:before-chunk-flip`, `reindex:before-publish`, `reindex:before-reclaim`, `reindex:before-embed` | raises `Crash` | readers stay exact; the next `reindex` converges (below) |
| resumable: `posture` | `relabel:after-chunk` | raises `Crash` | readers stay exact; the next `posture` call converges |
| resumable: bounded `sweep` (spec 180) | the slice seam 180 adds | raises `Crash` | the row is reserved; 180 fills it |

`Crash` derives from `BaseException` so no `except Exception` and no
retry loop below the seam can swallow it: it is the process dying at
that line. `finally` blocks still run, which a real death skips. The
one that matters is the reindex lease release
(`_held_reindex_lease`), so every `reindex` seam runs twice: once as
raised, and once with the lease then rewritten as held by a dead
token whose expiry has passed (the state a killed process leaves).

**Readers stay exact**, checked between the crash and the next call,
as the system actor, alice and anonymous:

- `grep` on the indexed tier, for a fixed set of patterns, returns
  exactly the rows the fault-free reference returns. The index may be
  stale; the dirty-side scan keeps the answer exact.
- `glean` returns no row the caller cannot read.
- `read`, `ls` and `tree` return the reference's rows.
- After a `relabel:after-chunk` crash, alice and anonymous see exactly
  the rows the new posture allows: the pending mark compiles as covers
  and holes (`rights.py` `resolve_authority` docstring).

**The next call converges**: the next `reindex` (or `posture` with the
same arguments) succeeds; afterwards `reindex` again finds nothing
dirty (`NOT chunked` and `NOT encoded` counts are 0); the logical
image of the primary tables (entries, content, blobs, versions,
version subjects, edges, segments, grants, memberships) equals the
reference; and every reader answer above equals the reference.

### 8.6 What the families do not do

They inject at statements and seams, never inside the engine. A
crash in the middle of a `COMMIT` is the replay spec's case (177; ADR
087 pin 10), not this one.

## 9. Family (c): the access-path golden tables

### 9.1 The meter

`tests/support/access.py` (spec 178 §9 starts it with a body-window
counter; this spec absorbs that counter into the meter):

- **Statements**: `before_cursor_execute`. Each record keeps the
  statement kind (first word), the first `vfs_` table named, whether
  it is control (`BEGIN`, `COMMIT`, `PRAGMA`, `SAVEPOINT`, `RELEASE`,
  `ROLLBACK`, `SET`), the parameter sets bound (1, or the executemany
  length) and the payload bytes sent.
- **Rows and bytes fetched**: a wrapper on `CursorResult`'s four fetch
  implementations (`_fetchone_impl`, `_fetchmany_impl`,
  `_fetchall_impl`, `_fetchiter_impl`). Every dialect's rows pass
  through them (F4).
- **Postgres `COPY`**: a wrapper on asyncpg's `copy_records_to_table`
  records one statement `COPY <table>`, its record count as rows bound
  and its payload bytes as sent. No other driver call bypasses
  SQLAlchemy.
- Installed by a context manager on the leg's engine, uninstalled on
  exit. Test support only; nothing in `src/` changes for it.

### 9.2 The world and the cases

One seeded world per leg, the same on every leg:

- posture `read` at `/`; alice holds `read_write` on `/docs` only; so
  the system actor is whole, alice's writes in `/docs` pass the gate,
  and anonymous may read but not write. F6 is this world on SQLite.
- `/docs/a.md` (60 B), `/pin.txt` at depth 1, a file at depth 20, a
  4 MiB body, one authored edge, one tombstoned file, a reindex run,
  then one more write, so the indexed tier and the dirty side both
  hold rows.

The cases, each at three authorities (system, alice with a warm cache,
anonymous) unless marked:

| Group | Cases |
|---|---|
| filesystem | `stat`, `read`, `ls`, `tree` at depth 2 and depth 20; `write` create at depth 1, 2 and 20; overwrite; `mkdir`; `delete`; `move` of a file and of a directory; `copy` of a file |
| derived | `edit` |
| query | `glob`; `grep` on the dirty side and on the indexed tier; `glean`; `graph` outbound one hop; `mkedge`; `rmedge` |
| history | `restore`; `sweep` of one file |
| rights | `grants`; `grant`, `revoke`, `posture` (system and alice); `add_member`, `remove_member` (system) |
| body (system) | `stat`, `ls`, `read`, overwrite and `edit` of the 4 MiB body |
| cache (alice) | `read` cold |
| batch (system, `slow`) | `write` create and overwrite of 10,000 rows; `ls` of 10,000 children |

Refusals are cases too: anonymous writes are refused, and their paths
are pinned like any other.

### 9.3 The fixture

- One file per engine family under `tests/storage/access_paths/`:
  `sqlite.json`, `postgresql.json`, `mssql.json`, `mariadb.json`,
  `oracle.json`. Key: `"<case>@<authority>"`. Value:

```json
{"path": [["SELECT", "vfs_entries"], ["INSERT", "vfs_entries"], ...],
 "statements": 6, "control": 3, "rows_fetched": 4, "rows_bound": 6,
 "bytes_sent": 342, "bytes_fetched": 102, "success": true}
```

- The test compares the whole record. Any difference fails, including
  a statement that moved. That is the "reviewed diff" ADR 087 pin 14
  asks for.
- Repin: `VFS_ACCESS_PATHS_REPIN=1 uv run pytest -n 0
  tests/storage/test_conformance.py -k access_path`, with the engine
  URLs set for the server files. It uses `tests/ranking/pins.py`'s
  `rewriting()` rule, which refuses under xdist.
- SQLite's file is exact in every field. The server files pin every
  field too, because the meter sees every value on every driver once
  `COPY` is wrapped. If a driver ever hands back a value the meter
  cannot size (an unconverted LOB), the record carries
  `"bytes_exposed": false` and the bytes fields are left out of that
  row's comparison, never guessed.

### 9.4 The baseline the SQLite file must reproduce

The first SQLite fixture is taken at the commit before §5.3's fold. It
must reproduce what the live tests already pin
(`tests/storage/database/test_writes.py:111–160`) and what F5 measured:

| Case | System | Alice (warm) | Anonymous |
|---|---|---|---|
| `write` create, depth 1 | **6** | — | refused |
| `write` overwrite | **8** | per F6 | refused |
| `edit` | **7** | per F6 | refused |
| `read`, `stat` | 1 | 3 | 4 |
| `ls`, `tree` | 2 | 4 | 5 |

The fold (§5.3) then lands as a fixture diff in its own commit: every
alice and anonymous row loses exactly one statement, and no system row
changes.

### 9.5 The dimensions, as assertions on the fixture

These are checked by code over the recorded rows on every leg, so they
hold when a repin changes the numbers:

- **Depth.** `stat`, `read` and `ls` issue the same statements at depth
  2 and depth 20. `stat`'s rows fetched differ by exactly 18 (one row
  per extra ancestor). A create at depth 20 binds 18 more segment rows
  than at depth 2.
- **Body.** `stat` and `ls` of the 4 MiB file fetch no body
  (`bytes_fetched` under 1,024). `read` fetches the body once. The
  overwrite sends at most two bodies and fetches at most one; `edit`
  fetches at most one (the `99884aa` pin, F7).
- **No mount-wide write.** No create, overwrite or `edit` path writes
  `vfs_meta` or `vfs_lock` (study 03 principle 6).
- **The router adds nothing.** A single-mount `read` and `write`
  through `VirtualFileSystem` issue the same statement list as the
  same calls on the storage object.

### 9.6 Native calls on the loop thread

`tests/support/access.py` also holds `NativeMeter`. It wraps every
callable of `vfs._native` (the call sites reach it through
`extension()` at call time, so the wrapper sees every call) and wraps
the two builder classes and `ContentMatcher` in proxies that wrap their
methods. Each call is counted under its name and "loop" or "worker",
by comparing the calling thread with the loop's thread.

- One fixture, `tests/storage/access_paths/native.json`, pinned on the
  SQLite leg only: the native calls do not depend on the dialect,
  except `glean`'s vector leg, which runs in the engine on Postgres.
- The baseline is F9. A new native call on the loop shows as a diff.
  Study 07's change (offload `glean`'s lexicon union past a threshold)
  is its own follow-up; this pin is what will show it worked.

### 9.7 What the first tables already show

F6 exposes one more hidden pair, the kind the landed fixes removed: a
caller whose rights are partial pays the target-and-ancestors read and
the posture read twice on every write (once in the gate's `targets`,
`rights.py:672`, once in the write plan's snapshot and owner label).
And `move` as the system actor issues six `vfs_entries` selects. Both
are follow-up fixes in the style of `4459271`: one commit each, pinned
by the golden diff. They are not in this spec.

## 10. What the Rust engine does not change

Nothing. The engine takes bytes, ids and packed arrays and returns
ids, spans and scores; no kernel takes a `Path`, an `Authority`, a
`Result` or an `Observation` (audit §6; `crates/vfs-core/src/lib.rs`
docstring). Regrouping the seam, adding features and traits, deriving
ops in the router and counting calls touch none of its inputs. The
native-call meter wraps the extension from the outside. No file under
`crates/` changes, and `PROTOCOL_VERSION` stays 10.

## Boundedness at 10,000 rows on the tightest engine

| New statement or call | Bound | Helper |
|---|---|---|
| the stamps-and-marks fold | one `IN` list of at most `membership_budget` ids; past it the chunked two-step path | `membership`, `chunked`, `membership_budget` |
| the durability probe | one statement at first touch | — |
| derived `tree` | one `ls` per depth level; each chunks its frontier | `ls`'s own `chunked(…, membership_budget)` |
| derived `copy`, `grep` | reads of at most `DERIVED_READ_ROWS` observations and `DERIVED_READ_BYTES` per call; one `write` call that storage chunks | storage's own `chunked` and `rows_per_statement` |
| derived `edit` | one `read` call and one `write` call; `if_versions` rides 174's chunking | 174 §7 |
| the derived cursor (`ls_cursor` absent) | the backend's full listing, cut by the router | none needed: no new statement |
| test images and meters | test support only | — |

No new statement grows with N past the dialect budget.

## Scope

**In:** the protocol regroup and its exports; `OP_GROUPS` (181's
shape); `Feature`, `FEATURE_ARGUMENTS`, `FEATURE_FALLBACK`, `DERIVED_FROM`;
`SupportsFeatures` and `DatabaseStorage.features()`; the `atomic_unit`
trait and `"none"` durability; the durability probe; `METHOD_ATOMICITY`;
the three docstring sections; `ENGINE_ERROR_KEY` and `engine_code`;
the feature gate and its derive arms; derived `tree`, `copy`, `glob`,
`grep`, and `edit` once 174 lands; `chain.py`'s two filters; the retry
counter; the rights-cache counts and the fold; `counters()`; the
conformance package; the three families; the native meter; the docs
lines in §Landing.

**Out:** the per-call arguments themselves (174, 176, 177, 178, 180);
integrity and `scrub` (175); the public surface regroup, `entry_id`
and `vfs.chain`'s public functions (181); the two hidden I/Os of §9.7;
offloading `glean`'s lexicon union; `reindex` draining a stranded
relabel mark (OSTEP memo §2.10); a per-dialect statement timeout; a
crash inside `COMMIT` (177); any change under `crates/`.

## Acceptance criteria

Counts and states, never clocks. Each is tagged with its slice
(tasks.md).

1. **(A)** `vfs.storage` exports `SupportsFileRead`,
   `SupportsFileWrite`, `SupportsCopy`, `SupportsTree`,
   `SupportsEdit`, `SupportsPatternSearch`, `SupportsGlean`,
   `SupportsGraph`, `SupportsEdges`, `SupportsTrash`, `SupportsRights`,
   `SupportsTraits`, `SupportsFeatures`, `SupportsReindex`,
   `SupportsClose`. `SupportsRead`, `SupportsMutation`,
   `SupportsGrants` and `SupportsRun` do not exist anywhere in `src/`
   or `tests/`.
2. **(A)** `_FAMILY_OPS` maps every op in `ALL_OPS` to exactly one
   family, and `OP_GROUPS` puts every op in exactly one group (the
   drift tests of 181 §2.2, landed here).
3. **(A)** A backend with `stat`, `ls`, `read`, `name`, `description`
   and `capabilities` is a `StorageBackend`; one missing any of the
   six is not; `tree` is not required.
4. **(A)** `DatabaseStorage.features()` on each of the five legs
   equals the expected set for that leg (with and without an
   embedder), every member is in `FEATURES`, and the index features
   agree with `grep_tier` and `glean_signals` on every leg.
5. **(A)** `traits()["atomic_unit"] == "call"` on every leg.
   `TRAIT_VALUES["atomic_unit"] == {"call", "mount", "row"}`.
6. **(A)** `InMemoryStorage` declares durability `"none"`; a SQLite
   file declares `"full"`; each server leg declares the value its
   server's setting implies (the Docker defaults give `"full"`), read
   by exactly one statement at first touch.
7. **(A)** `METHOD_ATOMICITY`'s keys equal `WRITE_GATED_OPS |
   {"reindex"}` (plus sibling ops as they land), and its whole-batch
   keys equal the set family (b) drives in §8.3.
8. **(A)** `protocol.__doc__` holds the three sections, "The atomic
   unit", "The fault model" and "The gate", and the sentence
   "One mutation call on one mount commits whole or not at all"
   appears exactly once in `src/`.
9. **(A)** On every leg, the fatal fault of §8.1 classifies
   `vfs.unavailable`, retryable, with `data["vfs.engine_error"]` equal
   to the leg's row of §3.3 (SQLite `{"dialect": "sqlite", "code": 10,
   "name": "SQLITE_IOERR"}`; Postgres `sqlstate` `"58030"`; SQL Server
   `sqlstate` `"HY000"`; MariaDB `code` 1030; Oracle `code` 1114,
   `name` `"ORA-01114"`). Four retryable faults in a row exhaust the
   retries and the `conflict` carries the retryable code. No test or
   source line reads `message` to get it.
10. **(B)** Over a partial backend double (`SupportsFileRead`,
    `SupportsFileWrite` only), `tree`, `copy`, `glob` and `grep`
    through the router return the same rows, in the same order, with
    the same error kinds, as the same router over a full
    `InMemoryStorage` on the same world: at least 30 differential
    cases. `mounts()` lists them under `derived`. After 174 lands,
    `edit` joins with its rival case classifying 174's kind.
11. **(B)** A call with a feature argument on a mount that lacks the
    feature: for `read_range` and `ls_cursor`, the same rows and the
    same resumption key as the native path; for `write_preconditions`,
    `transfer_replace`, `request_key` and `sweep_cursor`,
    `vfs.unsupported` with `data["vfs.feature"]` and 0 storage calls
    (spied). Each row lands with its owning spec.
12. **(E)** One retryable fault on any whole-batch verb: success and
    `counters().retries[op] == RetryTally(1, 0)`. Four: `conflict` and
    `RetryTally(3, 1)`. No fault: no entry for the op.
13. **(C)** `RightsCache` counts exactly: cold named `read` 1 miss;
    warm 1 hit; after a grant to alice, the next call 1 stale; with
    `entries=2`, a third subject set 1 eviction. The system actor
    leaves every count at 0.
14. **(C)** On SQLite, warm named `read` is 2 statements, warm
    anonymous `read` 3, cold named `read` 6. With `ids` one past the
    membership budget (a forced small budget), the stamp read issues
    `ceil(ids / budget)` statements plus one for the marks. On every
    server leg, every alice and anonymous golden row drops by exactly
    one statement in the fold's commit, and no system row changes.
15. **(D)** The `--collect-only` node-id list of
    `tests/storage/test_conformance.py` after the split equals the
    list before it, line for line. `storage_contract.py` and
    `grants_contract.py` are gone; the package holds 220 + 75 moved
    tests.
16. **(E)** Family (a): every scenario of §7 on every leg gives
    `success is False`, exactly the bad rows' errors, 0 commits and an
    unchanged full image across all 22 tables. The 10,000 + 1 variant
    gives 0 commits and 0 rows under its directory in every table. The
    two-mount tear test lands one row and not the other.
17. **(E)** Family (b), statements: on every leg, for every scenario
    of §8.3 and every N from 1 to its M, the reopened full image
    equals the before-image (0 torn). The SQLite leg's M values equal
    F1's (10, 10, 5, 6, 6, 5, 3, 3, 1, 1, 5) for the shared scenarios.
    The retryable pass gives success, a logical image equal to the
    reference, and 1 redrive, for every N.
18. **(E)** Family (b), seams: every one of the 21 seams has a row in
    `SEAM_CLASSES` and a passing test on every leg, including the five
    with no handler today. The parse-based drift test fails for a
    seam name with no row. Each `reindex` seam passes in both lease
    variants.
19. **(E)** Family (c): one fixture per engine family with every case
    of §9.2 at its authorities; each run equals its fixture in every
    field. The SQLite fixture reproduces §9.4. The repin refuses under
    xdist.
20. **(E)** The §9.5 dimensions hold on every leg: statements equal
    across depth, 18 more rows for `stat` at depth 20, no body bytes
    for `stat` and `ls`, at most one body fetched by `edit`, no write
    to `vfs_meta` or `vfs_lock` on the write paths, and the router
    adding zero statements.
21. **(E)** `native.json` holds F9's counts for `write`, `read`,
    `glob`, `grep` (both tiers), `glean` and `reindex`, by name and
    thread, and the run equals it.
22. **(all)** No file under `crates/` changes in this spec's commits;
    `cargo test -p vfs-core` stays green.
23. **(all)** `scripts/ci.sh` is green at 100% coverage after every
    task. The four engine legs (the db_test skill) are green before
    tasks 4, 5, 8, 9, 10, 11 and 13 land.

## ADR amendments this spec needs

- **ADR 087 pin 7.** The whole-batch list adds `sweep` (until spec
  180 makes it resumable), `mkedge`, `rmedge`, `grant`, `revoke`,
  `add_member` and `remove_member`. `posture` is split: its row is
  whole, its relabel resumable. `rmedge`'s missing triple is a warning
  that lets the rest of the batch commit.
- **ADR 087 pin 8.** Name the field: `data["vfs.engine_error"]`, with
  `dialect` and whichever of `sqlstate`, `code` and `name` the driver
  carries. SQL Server's native number is not structured in pyodbc, so
  only its SQLSTATE travels.
- **ADR 087 pin 14.** "Body bytes moved" is measured as payload bytes:
  every `str` and `bytes` value bound or fetched. Bodies dominate it;
  the 4 MiB dimension shows them alone.
- **ADR 087 pin 1** gains one sentence: the seam's protocol families
  follow the kernel groups, so `mkedge` and `rmedge` leave the
  mutation family for `SupportsEdges`; the write gate stays its own
  axis (`MUTATING_OPS`).
- **A new pin, or a line under pin 2:** "presence is a feature, a
  quality is a trait": a declaration with one possible value is a
  feature, and every feature names whether the kernel derives or
  refuses it.
- **Study 05 §2.11's count** is four untested seams; it is five
  (`transfer:post-snapshot`). Research memos are not edited; the ADR's
  consequences line can cite F10.

## Rebase notes for specs 167, 171 and 172

- **167.** Task 1 deletes `SupportsRun`; whichever of 167 and 179
  lands first does it, and the other skips. Task 13's replace flag
  declares `transfer_replace` in `DatabaseStorage.features()`. The
  shell's `tree` and `cp` call the router, so derived ops are
  invisible to it. The regex `sed -i` (181's note) uses
  `write(if_version=)`; on a mount without `write_preconditions` it
  is refused, never run unguarded.
- **171.** The tool list comes from the mount's effective `caps`,
  derived ops included, so a partial backend's mount still offers
  `tree`, `glob` and `grep`. A refused feature argument arrives as
  `vfs.unsupported` with `data["vfs.feature"]`; the adapter maps it to
  a tool error naming the argument. `serve()` is the wall tier of
  §3.2's gate section. If Clay answers §5.4 "through the router",
  171's metrics endpoint reads `counters()` that way.
- **172.** The WASI provider reads the mount's `features` (from
  `mounts()`): with `read_range` it maps `fd_read` to a ranged read;
  without it the kernel slices, which is correct and whole-body. Its
  close-time write-back needs `write_preconditions`; on a mount
  without it the provider refuses the write at close rather than
  write unguarded, and says why.

## Notes for the sibling specs of ADR 087

- **174** uses the feature name `write_preconditions` (its §6.8 defers
  the name here) and adds the `FEATURE_ARGUMENTS["write"]` row.
- **176** declares `ls_cursor` and adds its rows; the router's derived
  page (§2.3) mints the same resumption key its native path does.
- **177** declares `request_key`.
- **178** drops the one-valued trait `read_range: "engine"` and
  `MountMeta.declared_traits` in favour of the feature `read_range`
  and `MountMeta.declared_features`; its router fallback and
  `slice_rows` stay as written. Its `tests/support/access.py` counter
  becomes part of §9.1's meter.
- **180** keeps `SupportsHistory` (`versions`) and `SupportsGarbage`
  as history-group families beside this spec's `SupportsTrash`
  (`restore`, `sweep`), declares `sweep_cursor`, adds its slice seam
  to `SEAM_CLASSES`, and moves `sweep` to resumable in
  `METHOD_ATOMICITY`.
- **175** puts `scrub` in the history group and `SupportsScrub` among
  the history families.
- **181** finds `OP_GROUPS`, `GROUP_OF` and the group drift tests
  already landed in its §2.1 shape, and `src/vfs/chain.py` holding the
  two row filters; it adds `vfs.chain.glob`/`grep` over them and the
  surface reordering. Its trust-tier text cites §3.2's docstring. Its
  `edit` oracle is §4.2's derivation, and its conformance rows go in
  `contract/fs_shapes.py` (`stat`) and `contract/fs_write.py`.

## Landing notes

(Filled in on landing, per task.) Docs to touch on landing:
`docs/explanation/write-pipeline.md` (the atomic unit, the two models,
the cross-mount tear, already half said there), `docs/contributing.md`
(the protocol line and the contract package), `docs/reference/glossary.md`
(feature, trait, atomic unit, access path), and the README banner's
`SupportsRun` sentence if 167 has not removed it.
