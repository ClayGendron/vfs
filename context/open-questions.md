# Open Questions

**Status:** live — first populated 2026-07-16 (from the specs/STATUS.md picture)
**Purpose:** A single list of unknowns, undecided calls, and parked ideas. Anything tagged `[NEEDS CLARIFICATION]` anywhere in `/context` should have a pointer here.

## Format

```
## <short title>
- **Asked:** YYYY-MM-DD by <who>
- **Context:** 1-2 sentences of what prompted the question
- **Blocking:** list of specs/plans/decisions that are waiting on this
- **Options considered:** bullet list
- **Status:** open | parked | resolved (→ link to decision or story that closed it)
```

## Lifecycle

- **open** — actively unresolved; blocks work
- **parked** — deliberately deferred; not blocking but not forgotten
- **resolved** — closed by a decision or story; keep the entry and link to what closed it

Resolved questions stay in this file as a record; they are not deleted. If the list grows long, split resolved ones into `open-questions-archive.md`.

---

## Create under a concurrently-trashed (or moved) directory can commit a torn path cache

- **Asked:** 2026-07-23 (filed with slice 9 landing 1, as the slice-9 topology guide directs — the window became reachable when `delete` landed)
- **Context:** Writes are deliberately not serialized with topology verbs. A write op that creates a child under a directory a rival topology verb is concurrently trashing (or, once landing 2 ships, moving) can commit a child row whose `path` carries the old prefix while its `parent_id` points at the relocated parent — a torn path cache. Reachability per engine: SQLite safe (single writer); Postgres safe (op sessions at REPEATABLE READ — the parent bump on the rival-updated row raises 40001 and the method restarts); **MySQL, MSSQL, Oracle, and the generic floor are exposed** (their bumps current-read past the rival's commit).
- **Blocking:** nothing lands broken — the window needs a rival interleaving on an exposed engine; the seam infrastructure from landing 1 can stage it for a repro when the fix story starts.
- **Fix sketch (from the slice-9 guide, deliberately not bolted into slice 9):** make `_bump_parents` guard on `(entry_id, path-at-snapshot)` with 079-style statement attribution — a guard miss means the parent's path changed mid-op and classifies a retryable conflict; sibling writes never disturb the path, so the hot-directory throughput rationale for unguarded bumps survives.
- **Scope widened 2026-07-23 (adversarial pressure test + multi-agent review of the slice-9 landing):** the family has a second flavor this entry's per-engine table did not cover. A rival write racing `_purge_subtree` (permanent delete, or move overwriting a directory occupant) committed between the purge's id-collection and its deletes — leaving a **permanent orphan row on all four real engines, Postgres included** (the REPEATABLE READ defense above never covered the purge's stale id list; topology runs at READ COMMITTED). Executed repro: `scratchpad/pressure/orphan_repro.py`, first-attempt reproduction on every engine. **That flavor is closed** (same day): `_purge_subtree` now re-collects and deletes until the subtree reads empty, so a mid-purge rival's child is swept with the subtree — winner-take-all, matching the observed race semantics elsewhere. The original torn-path-cache flavor (create under a concurrently *trashed/moved* directory) remains open and still wants the guarded-bump story; that fix must also cover the residual purge window (a rival committing after the purge's final sweep but before the topology transaction commits).
- **Options considered:** guarded parent bumps with statement attribution (the sketch); serialize writes with topology (rejected — defeats the single-batch-writer throughput doctrine); isolation pins on the exposed engines (partial, engine-by-engine)
- **Kernel precedent (2026-07-23 prior-art pass):** Linux closes exactly this race with locks — creates take the parent directory's `i_rwsem` and cross-directory renames hold both parents' plus the per-superblock `s_vfs_rename_mutex` (`linux/fs/namei.c:3784-3792`, `:5895-5914`: "everybody except rename does 'lock parent, lookup, lock child'"). vfs deliberately declines that lock for writes (single-batch-writer throughput doctrine), so the guarded bump is the optimistic substitute for the lock the kernels take — detect-and-retry instead of exclude.
- **Status:** open — the guarded-bump story was taken in-session 2026-07-23 (purge flavor already closed in-tree the same day); this entry tracks the torn-path-cache flavor and the residual commit-window until that story lands

## Trash rewrites can exceed the path column — refuse, widen, or store-and-classify?

- **Asked:** 2026-07-23 by Clay + Claude (adversarial pressure test of the slice-9 landing, defect 2; multi-agent review findings 9 and 20 hit the same contradiction from the read side)
- **Context:** Slice 9 landed declaring trash-side paths may lawfully exceed the 1,024-byte public budget, but the `path` column is `BytewiseString(MAX_PATH_LENGTH)` — byte-exact DDL on every real engine by ADR 024's own design. The bucket prefix (`/.vfs/trash/<hour>/<ULID>`) is 52 bytes, so the worst-case rewrite is 1,074 bytes: a lawful delete of a shallow directory with a deep descendant failed on **all four** engines (Postgres truncation error, MySQL 1406, MSSQL 42000, Oracle ORA-12899), classified `unavailable`/`retryable=True` on the wrong channel — and such trees could only be deleted with `permanent=True`. Adjacent: reads over stored over-budget state would raise raw `ValueError` out of public verbs, since `Path` minting enforces the budget.
- **Prior art (verified in-session):** no kernel refuses a mutation for descendant path depth — deep trees are representable-but-unaddressable, failing only at render time (`getcwd` → ENAMETOOLONG, `linux/fs/d_path.c:430-439`) — but only because kernels store one name per edge and never materialize paths (`__d_move` relinks a single edge, `linux/fs/dcache.c:2928`). No kernel has trash at all; userspace trash (the only trash precedent) refuses the move and offers permanent delete as the fallback. vfs materializes a path cache by design, which makes the budget a write-time constraint.
- **Options considered:** refuse on overflow (`unaddressable`, permanent delete remains available — matches the landed move-verb and memory-backend refusals; no DDL change; the budget becomes a true end-to-end invariant); widen the column with declared trash headroom (≥1,074 → 1,088 — the kernel-analog "unaddressable at read", but reopens the `Path` never-observes-over-budget invariant and adds read-path surface); keep the contradiction filed
- **Status:** resolved 2026-07-23 (Clay, in session; confirmed against the prior-art pass) — **refuse on overflow.** The trash arm computes every descendant rewrite first and refuses the target `unaddressable` (`Cannot delete <target>: Path too long`) before any statement applies; over-budget paths are never stored, so the read-side ValueError exposure is unreachable. The slice-9 "trash paths lawfully exceed the budget" line was the invention the DDL contradicted, and it is reversed in `topology.py`'s module contract.

## Trash retention policy: TTL, size bound, and eviction observability

- **Asked:** 2026-07-23 by Clay + Claude (trash prior-art pass; ADR 026 pin 5 deliberately left the numbers open)
- **Context:** ADR 014 pin 5 makes reclamation an explicit idempotent sweep verb and ADR 026 pin 5 keys expiry off parsing `<YYYY-MM-DD-HH>` bucket names — but no retention length is declared anywhere. The field's postures: JuiceFS `--trash-days N` (configurable, default on); iCloud/Photos and Drive/Dropbox fixed 30-day TTL; Purdue entomb ≤24 h backed by real backups; Windows adds a per-volume **size quota** with observable oldest-first eviction plus an oversized-item bypass (items bigger than the bin hard-delete after a prompt). Given the ETL audience's 10,000+-file batches, an unbounded trash is a real capacity risk — a single bulk delete can park an entire dataset in one bucket.
- **Blocking:** the sweep-verb story (it needs a default retention to sweep against); capacity planning for bulk-delete workloads
- **Options considered:** mount-level `trash_days`-style config (JuiceFS shape) with a sensible default; fixed TTL (cloud shape); TTL + declared size bound with oldest-bucket-first eviction (Windows shape — likeliest fit for the ETL audience); an oversized-delete bypass (batch bigger than the bound goes straight to permanent, loudly)
- **Status:** resolved 2026-07-24 (Clay, in session; spec 083 landed same day) — **90-day TTL, configured per backend** (`DatabaseStorage(trash_days=90)`, the JuiceFS shape; `trash_days=0` lawful, negative refuses at construction). Deliberately generous next to the field's 30-day convention: the sweep verb is explicitly invoked, so retention is a floor on what a sweep may destroy, not a promise of timely reclamation. Eviction observability: dropped buckets are the sweep result's observations; skipped foreign rows surface as warning-severity entries. **The size bound and oversized-delete bypass stay demand-gated** — unbuilt until a deployment hits the capacity wall; reopening them is a new entry, not this one.

## MSSQL silently mangles non-Latin1 path and name characters to `?`

- **Asked:** 2026-07-23 by Clay + Claude (adversarial pressure test of the slice-9 landing, defect 4 — surfaced attacking topology; the defect is on the write path, pre-existing)
- **Context:** On MSSQL, `write` of a path containing non-Latin1 characters reports success but stores literal `?` bytes (`/u/🚀.txt` → `/u/??.txt`, verified by raw hex dump); the written path is then unaddressable — silent data corruption. The column design is correct (`VARCHAR` + `Latin1_General_100_BIN2_UTF8`, byte-exact per ADR 024); the loss is bind-side: SQLAlchemy's mssql dialect binds plain `String` params as ANSI `SQL_VARCHAR`, which the server decodes via the *database's* default collation codepage (the harness runs in `master`, CP-1252) before the value reaches the UTF-8 column. Postgres, MySQL, and Oracle round-trip emoji/Devanagari/Japanese names cleanly. The conformance suite never wrote a non-ASCII name on the mssql leg, which is why four green legs coexisted with this.
- **Blocking:** any real MSSQL deployment storing non-Latin1 names; honest per-engine unicode conformance
- **Options considered:** make path/name binds go over the wire as Unicode (`SQL_WVARCHAR` — NVARCHAR→UTF-8-VARCHAR server conversion is lossless); UTF-8 ANSI binds paired with a UTF-8 database collation requirement; NVARCHAR columns — rejected, UTF-16 doubles key bytes past MSSQL's 1,700-byte index cap at 1,024
- **Status:** resolved 2026-07-23 (Clay + Claude, in session; probe-verified both halves on the live engine) — **two-sided fix.** Bind side: built mssql engines pass `use_setinputsizes=False` (`engine.py:_engine_kwargs`), restoring pyodbc's `SQL_WVARCHAR` default — probe showed default MANGLED, disabled LOSSLESS, byte-for-byte. Column side: the probe also proved `Text` bodies mangle *server-side* under the database codepage even with Unicode binds, so `_body_text()` and every caller-supplied `String` column (`external_id`, `mime_type`, `ext`, `owner_id`, `created_by`, `edge_type`) gained the `Latin1_General_100_BIN2_UTF8` variant (`rows.py:_string`). Pinned by a non-Latin1 round-trip conformance row (write/stat/read/move/copy/ls/delete) enforced on every backend and engine leg; the original raw-hex repro now stores exact UTF-8 bytes. Borrowed session factories carry their builder's engine and must apply the bind-side setting themselves — documented on `_engine_kwargs`.

## MySQL-family batch UPDATEs are per-row driver round trips

- **Asked:** 2026-07-23 (multi-agent review of the spec 079 landing; scale lens, CONFIRMED 3/3)
- **Context:** pymysql/aiomysql `executemany` batches only INSERT/REPLACE (`RE_INSERT_VALUES`) and loops per-row for UPDATE, so on mysql/mariadb the guarded aggregate arm and the unguarded absorb executemany each cost one driver round trip per row — a 10k overwrite batch is ~10k sequential UPDATEs inside one REPEATABLE READ transaction. Results stay correct and statements stay bounded; the cost defeats plan.md's "one executemany regardless of N" and widens the 1205/1213 lock window. Postgres/mssql (VALUES-join arm) and oracledb (real array DML) are unaffected.
- **Blocking:** nothing lands broken; a fix is a capability-ladder change (a set-based join-UPDATE for the mysql family, verified by aggregate rowcount == N, no RETURNING needed).
- **Preconditions to verify before designing:** (1) rowcount semantics — SQLAlchemy's mysql dialect defaults to `found_rows` (rows *matched*); the guard always bumps `version`, so matched == changed today, but the fix must not silently depend on that; (2) validate on the real mysql/mariadb legs via the db_test cycle.
- **Options considered:** multi-table UPDATE with a derived-table join (mysql-native); leave as-is and document the cost; raise the driver's executemany capability upstream.
- **Status:** open — owned by `specs/080-mysql-batch-update-statements/` (research questions and acceptance criteria live there); do not fix inline

## Row-level grant semantics (spec 058's clarification forks)

- **Asked:** 2026-07-10 (spec 058 seeded with `[NEEDS CLARIFICATION]` forks — nine in the spec as it stands; this entry long said eleven)
- **Context:** Row-level permission grants need a verified `Principal` before enforcement semantics can be pinned; the forks cover grant shape, inheritance, and query-construction enforcement.
- **Blocking:** `specs/058-row-level-permission-grants/`
- **Coupled to:** the parked full-dirent question below. 058 attaches grants to **path prefixes** and computes coverage from the path string; ADR 018's parked end-state gives one entry many paths via hard links, which makes prefix coverage ambiguous and dissolves `Entry.path` as sole domain identity — the classic POSIX hard-link permission problem. Ratifying a prefix-attached grant model entrenches against that end-state; unparking it forces 058 to re-derive around ids.
- **Also lands here:** the *per-principal* half of the execute-policy question below — an `execute` level in this grant ladder, not a reopening of 039.
- **Stale premise:** 058's depends-on line cites `src/vfs/models.py` / `VFSEntry`, neither of which survived spec 076's model split (now `src/vfs/models/entry.py`, `Entry`), and its "identity threaded as `user_id` through `_call_storage`" language is superseded by spec 070. True these up before the full spec is written.
- **Options considered:** see the forks inline in 058's spec
- **Status:** open — waits on spec 070 (`Principal`) landing first

## serve() topology-lock policy premise

- **Asked:** 2026-07-10 (flagged in the STATUS true-up)
- **Context:** Spec 054 decides that `serve()` locks mount topology, but its `allow_child_mounts` premise went stale after 056/068 reshaped mount admin. **Verified 2026-07-22:** `allow_child_mounts` has zero occurrences in live `src/` — the spec's mechanism language is not merely stale but unimplementable as written, and should be deleted rather than re-derived.
- **Blocking:** `specs/054-mcp-serve-locks-topology/` — itself waiting on `serve()` existing
- **Options considered:** re-derive the policy against the post-068 mount admin surface, or fold it into the MCP serve spec when that work starts
- **Status:** parked

## Per-path / per-principal execute policy

- **Asked:** 2026-07-11 (068 landing superseded spec 039's mechanism)
- **Context:** `run` stays outside the permission-map vocabulary; denied execution classifies `unsupported`. 068's `deny_ops` covers the mount-level need.
- **Blocking:** nothing today
- **The two halves have different owners** — route incoming demand accordingly: **per-path** execute (uniform across principals) reopens `specs/039-execute-permission-tier/`, whose rights-set is already drafted and whose implicit-grant fork is signed off, so nothing needs re-deciding first. **Per-principal** execute is a grant-ladder extension in spec 058 (an `execute` level beyond `read_write`), not a 039 question. Treating them as one thing sends the demand to the wrong spec.
- **Options considered:** permission-map tier (039's original shape) vs. mount-level `deny_ops` (landed)
- **Status:** parked — unblocked only by a real consumer asking for "runnable except these paths" (→ 039) or "runnable by these principals" (→ 058)

## Bare-node default: full store or directories-only?

- **Asked:** 2026-07-16 (surfaced writing ADR 009 during the archive mining pass)
- **Context:** Story 055 decided `VirtualFileSystem()` defaults to directories-only `InMemoryStorage(allow_files=False)`; the landed code passes no flag and `allow_files` defaults `True` (`base.py:213-214`, `memory.py:93` — both anchors had drifted from the numbers this entry was filed with), so a bare node is a full in-memory store. `git log -L` shows it never shipped as directories-only.
- **Options considered:** keep full-store default (ratify the divergence) vs. restore 055's directories-only intent
- **Status:** resolved 2026-07-22 (Clay, in session) — **ratify the landed full-store default.** No follow-up note to ADR 009 is needed: decision 5 already records the divergence as deliberate and on record, which is all a note would say. The canon is unanimous and has no counter-example — fsspec's `MemoryFileSystem` is "a filesystem based on a dict of BytesIO objects" (`filesystem_spec/fsspec/implementations/memory.py:17-24`), pyfilesystem2's `MemoryFS` "constructor takes no arguments" and is not read-only (`pyfilesystem2/fs/memoryfs.py:319-350`), and no in-memory filesystem in the reference set defaults to directories-only. That mode is vfs's own scaffolding invention and is correctly an explicit `InMemoryStorage(allow_files=False)` opt-in. 055's directories-only intent is dead, not latent; no defect exists. Checked for a safety property that might have made it load-bearing (a router node that must never hold content a mount could shadow) — none: shadowing is governed by `no_overlay`, not by the root store's file capability.

## Mount-wide change cursor: does anything need one after revisions go per-entry?

- **Asked:** 2026-07-17 by Clay + Claude (write-path prior-art memo §3)
- **Context:** The plan to drop the per-mount ordered revision counter (per-entry versions + index-status flags) removes the only mount-wide total order of changes. Nothing live depends on "everything changed since T" today, but sync/replication/audit features would.
- **Blocking:** the revision-split ADR (to be written from `research/2026-07-17-write-path-prior-art-and-scaling.md` §4.1–4.2) — it should state the answer either way
- **Options considered:** no cursor needed (updated_at + per-entry versions cover near-term); append-only change-log table written in the same txn; revive ordered allocation only for the feature that needs it
- **Status:** resolved 2026-07-17 (Clay, in session) — `updated_at` is the change cursor; no change-log table, no ordered allocation. It is coarse (wall-clock, tie- and skew-prone): consumers query with slack and dedupe by per-entry version. Recorded in `research/2026-07-17-write-path-prior-art-and-scaling.md` §3; the revision-split ADR ratifies it.

## Full dirent model: name-on-edge, parent_id dropped, hard links?

- **Asked:** 2026-07-19 by Clay + Claude (edge-authoring session, while deciding ADR 018)
- **Context:** ADR 018 materializes fs edges but keeps `parent_id` as the write-side arbiter because `UNIQUE(parent_id, name)` is portable where a shared-edges-table unique constraint is not (SQL Server single-NULL, Oracle composite-NULL, no clean GENERIC floor). The POSIX-pure end-state — names live on the edge (juicefs `edge(parent, name, inode, type)`), entries hold no parent, hard links become possible — would make the edges table the sole hierarchy store.
- **Blocking:** nothing — ADR 018 works without it; revisiting means rethinking `Entry.path` as sole domain identity and per-dialect unique strategies
- **Coupled to:** the row-level grant question above — 058's path-prefix grants assume one path per entry, which hard links break. Every year of path-attached features raises the cost of unparking this, so the two must be decided with each other in view.
- **Why juicefs's shape does not port directly:** its dirent table is portable precisely because it is *dedicated* — `edge{Parent, Name}` are both NOT NULL in a table nothing else shares (`juicefs/pkg/meta/sql.go:65-71`), so the shared-table NULL-semantics problem never arises. That is ADR 018's rejected option two, and it resurrects the two-table traversal the one-query-one-table requirement forecloses.
- **Options considered:** keep ADR 018's mirror (landed); full dirent model via a dedicated fs-edge/dirent table (resurrects two-table traversal); name-on-edge in the shared table with per-dialect functional/filtered unique indexes
- **Status:** parked — unlocked only by a ratified requirement for hard links, or for rename of giant subtrees where path-cache regeneration dominates, or by dropping the one-table traversal requirement. Unparking means a full research → ADR cycle, not an amendment.

## Ancestor propagation: is a background task acceptable in the deployment model?

- **Asked:** 2026-07-17 by Clay + Claude (write-path prior-art memo §4.3)
- **Context:** Parent-directory revision bumps are the remaining shared-row write; Oak and JuiceFS both move ancestor updates to an in-memory accumulator with a batched background flush. Whether we can do the same depends on whether the backend may own background work or must stay purely request-scoped.
- **Blocking:** memo §4.3's (a) background flusher vs (b) derive-at-read choice; the hot-parent fix in the scaling ADR
- **Options considered:** background accumulator + flush (Oak/JuiceFS pattern); derive directory change from `MAX(updated_at)` over children at read time and drop stored bumps; keep synchronous bumps and accept same-directory fan-in contention
- **Status:** resolved 2026-07-17 (Clay, in session) — storage owns no background work, so the Oak/JuiceFS accumulator is out. At-scale path: derive directory change from children at read time; stored parent bumps leave the write path (synchronous bumps acceptable until then). Recorded in `research/2026-07-17-write-path-prior-art-and-scaling.md` §4.3.

## The declared key-byte budget never reaches the DDL — MySQL refuses first touch

- **Asked:** 2026-07-23 by Clay + Claude (first run of the real-engine conformance harness, `docker/compose.test.yml`)
- **Context:** The MySQL conformance leg fails at `create_all` with error 1071 (`max key length is 3072 bytes`): `entries.path` is `_binary_string(MAX_PATH_LENGTH)` — VARCHAR(1024), `unique=True, index=True` (`models/rows.py:284`) — and utf8mb4's 4 bytes/char makes that a 4,096-byte key. `DialectProfile.key_byte_budget` exists and is enforced **at write time** (`writes.py:101,147,193` via `WritePlan`), but no DDL consumes it, so an engine whose cap is tighter than the column's worst case refuses the schema outright — first touch classifies `unavailable` and every mutating verb fails. This contradicts "unknown dialects are served, not refused" on the most common unknown dialect there is.
- **Blocking:** the MySQL leg of `.github/workflows/test-dialects.yml` (was marked `continue-on-error`); any real MySQL/MariaDB deployment
- **Options considered:** size indexed key columns from a byte budget rather than a char count (touches every profile; the honest fix); a MySQL `with_variant` using a binary type or per-column charset so 1,024 chars fit the key cap; a prefix index (`mysql_length`) — rejected on its face for the *unique* path index, since prefix uniqueness is stricter than path uniqueness; declare MySQL unsupported — contradicts the GENERIC-floor contract
- **Status:** resolved 2026-07-23 (Clay, in session) — **ADR 024**: path limits became byte-denominated (1024/255 UTF-8 bytes, the BSD/macOS `PATH_MAX`/`NAME_MAX` — Clay's proposed angle, confirmed against fs heritage, juicefs, and Oak), key columns compile to `VARBINARY` on the mysql family, and the budget↔DDL gap closes by construction (`MAX_PATH_LENGTH <= min(key_byte_budget)`, pinned in tests). MySQL/MariaDB gained tuned profiles (catch-retry, REPEATABLE READ, errno-based deadlock retry). Research: `research/2026-07-23-mysql-support-byte-denominated-path-limits.md`. The MySQL conformance leg runs green and enforcing.

## Hermetic-runtime guest bet: Monty, CPython-on-WASI, or both behind one capability contract

- **Asked:** 2026-07-24 by Clay + Claude (hermetic-runtime research memo §7)
- **Context:** The CLI-as-hermetic-runtime direction needs a sandboxed guest interpreter for agent-written code. Monty (pydantic, 0.0.19) is purpose-built — dict-based host functions, async coroutine externals, pause/resume snapshots — but self-labeled experimental with a real language subset (no inheritance, no generators, nine-module stdlib) and no security audit. CPython-on-WASI under wasmtime is the full language behind the same capability idea, at higher startup/memory cost. The research memo's mitigation: define the guest-visible capability contract once and treat the interpreter as swappable.
- **Blocking:** the Monty phase of the runtime work — not the wasm-CLI spike, which needs no guest interpreter
- **Options considered:** Monty first, WASI-CPython later behind the same contract (memo's lean); both from day one; wasm-only until Monty matures
- **Status:** open — decide when the code-execution phase is specced; the wasm spike proceeds regardless

## Shell pipe payload: Result envelopes with a canonical wire serialization, or bytes at v1?

- **Asked:** 2026-07-24 by Clay + Claude (hermetic-runtime research memo §2, from nushell's documented wart)
- **Context:** nushell pipes structured values but serializes structured→external-stdin via its *human table renderer* (run_external.rs:502-518) — the display format became the wire format and cannot be fixed post-ship. If vfs shell pipes carry Result envelopes, the structured→wasm-stdin boundary needs a canonical serialization declared before the first shell ships (JSON lines is the obvious candidate — it is what jq eats); the alternative is bytes-only pipes at v1 with structure layered later.
- **Blocking:** the shell-surface ADR; the wasm spike only touches it at the stdin boundary and can hardcode JSON lines without prejudice
- **Options considered:** envelopes in the pipe + declared JSON-lines wire format at the external boundary (memo's lean); bytes-only v1; per-command negotiated formats (rejected on its face — nushell's warts show format decisions must be global)
- **Status:** open

## Guarded-update read-back infers success from the post-image — a reachable torn row on READ COMMITTED

- **Asked:** 2026-07-22 by Clay + Claude (reviewing `_update_materials` while designing spec 078); severity corrected the same day by an independent review
- **Context:** `_update_materials` deliberately does not trust per-driver executemany rowcounts; it re-reads the batch's versions and infers success from `observed == staged.version` (`writes.py:531`). Version numbers are per-entry counters, so the post-image cannot distinguish "our write landed" from "a rival's did." Statement order on an engine at READ COMMITTED: (1) `_fetch_committed` reads version N, staging `base=N, version=N+1`; (2) a rival commits from the same base, leaving the row at N+1 with *its* material; (3) our guarded `WHERE version = N` matches zero rows and raises nothing; (4) the read-back sees N+1 `== staged.version` and concludes success; (5) `_replace_content` then deletes the rival's content row and inserts ours, and the batch commits with a success `Observation`. **This needs no precise interleave** — it needs one rival committing anywhere in the window the guard exists to police, and a single rival advancing the version by exactly one is the *common* conflict, not the edge; the check catches only the rarer two-plus-increment and deletion cases, so its detection is inverted from likelihood. **The consequence is worse than a lost update: it is a torn row** — the entry keeps the rival's `content_hash`/`size_bytes`/`mime_type`/`owner_id`/`updated_at` while the content table holds our body, so `content_hash` no longer hashes the content.
- **Exposure:** the engines that reach it are those whose op sessions run at READ COMMITTED — the MSSQL profile and the GENERIC floor (engine default), i.e. exactly where `_update_materials`' docstring says the guard is load-bearing. **Not** Postgres (op sessions pinned REPEATABLE READ, rivals surface as 40001) and **not** SQLite (single writer; `BEGIN IMMEDIATE` precedes the snapshot read).
- **Blocking:** nothing mechanically — spec 078 explicitly leaves the check untouched and stays a pure rename. But this should not sit parked: it is a data-integrity defect on shipped dialect profiles and wants its own fix story.
- **Options considered:** **(1) return the matched keys from the guarded UPDATE itself** (`RETURNING entry_id` on PG/SQLite, `OUTPUT inserted.entry_id` on MSSQL) — you learn which rows *your* statement touched, with no inference and no pre-image; likely the natural fix; (2) return the pre-image instead of inferring from the post-image; (3) carry a per-write token (writer id or ULID stamp) compared alongside the version; (4) pin isolation on the exposed engines, mirroring the Postgres REPEATABLE READ pin; (5) lock the update targets in the snapshot read (`FOR UPDATE` / `UPDLOCK`); (6) drive the guarded arm row-at-a-time where rowcount is trustworthy — **collides with the 10,000-entry batch contract** and should carry that caveat. "Prove it unreachable" was considered and is expected to fail: the statement-order argument above already establishes reachability.
- **Status:** resolved 2026-07-23 (Clay, in session) — **spec 079 landed**: the read-back is deleted and guarded updates attribute from their own statements, via a capability ladder — a set-based VALUES-join UPDATE with RETURNING (postgres/mssql, gated by the new `DialectProfile.values_join` bit since SQLite rejects SQLAlchemy's column-aliased VALUES rendering), an executemany savepoint fast path whose sane aggregate rowcount proves every guard matched (sqlite/mysql/oracle), a per-row rowcount floor, and a classified refusal where nothing is verifiable. The regression pin (one-increment rival at READ COMMITTED) ran red on real MSSQL against the old code — `success=True` with a torn row — and green after; all four Docker legs pass. Details in `specs/079-guarded-update-statement-attribution/plan.md`.
