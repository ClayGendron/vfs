# Slice 9 implementation guide — `topology.py`: move / copy / delete

Written 2026-07-23 after a full orientation pass, for whoever executes
task 12. Spec 079 (statement-attributed guarded updates) is landed and
all four Docker engine legs are green, so the write path you are
extending is verified on real engines. No slice-9 code exists yet —
this records the settled design so the next session starts at
implementation, not re-derivation.

## Read these first (contract sources, in order)

1. **`src/vfs/storage/backends/memory.py`** — `delete` (~line 346) and
   `_transfer` (~line 619). This is *the* semantic reference: the
   refusal ladder, batch-shape rules, covered/seen delete semantics,
   and observation timing must match it row for row. The conformance
   suite was written against it.
2. **`tests/storage_conformance.py`** — the ~40 topology rows (grep
   `move`/`copy`/`delete` in test names). They flip from skipped to
   enforced the moment `capabilities()` declares the verbs; no test
   edits needed. Notable rows that constrain the design:
   - `test_delete_covered_miss_classifies_the_requested_target` —
     forces miss classification against the **pre-batch committed
     snapshot**, not in-transaction state (see Delete below).
   - `test_batch_move_observations_match_the_committed_state` — pair 2
     creates under pair 1's destination, so per-pair reads must see
     earlier pairs' in-transaction effects, and observations must be
     re-read after the whole batch.
   - `test_move_cycle_classifies_before_the_occupied_destination` and
     `test_move_no_replace_occupied_destination_is_exists_before_kind`
     — pin the exact ladder order below.
   - `test_transfer_classifies_a_row_that_overflows_at_the_destination`
     — destination overflow is `unaddressable`, refusing the pair.
3. **Spec 072 §9–§10** (`spec.md` ~530–720) — trash shape, move
   contract, serialization-point pins. **ADR 014** + **spec 075** —
   trash is normal-fs parity now: one meta scope, no trash filters, no
   write gate; delete hides originals via the path rewrite alone.

## Files to touch

1. **`dialects.py`** — `MYSQL` gains `topology_isolation="READ
   COMMITTED"` (MARIADB inherits via `replace`). Reason: mirrors the
   Postgres pin — under the serialization point the load-bearing
   property is per-statement visibility of post-rival state; MySQL's
   REPEATABLE READ pins a snapshot at the first consistent read and its
   UPDATEs current-read anyway. Add
   `topology_execution_options(profile)` beside `op_execution_options`:
   `{"vfs_writer": True}` plus `isolation_level` from
   `topology_isolation` when declared (never `op_isolation` — topology
   verbs trade the op snapshot for the lock, deliberately).
2. **`engine.py`** — make `_advisory_key` public (`advisory_key`) and
   add an `EngineHost.topology_key` property:
   `advisory_key(self.mount_identity)` once adopted, falling back to
   the table-name key pre-touch. Spec pin: topology locks key on the
   durable mount identity, never the mount path.
3. **`topology.py`** (new) — the whole slice; layout below.
4. **`backend.py`** — `delete`/`move`/`copy` route through a
   `_execute_topology` runner (clone of `_execute_write` but stamping
   `topology_execution_options`); extract the shared body if it reads
   cleanly. `_LANDED_OPS` gains `"delete", "move", "copy"`.
   `targets_of(path, observations)` feeds delete, `operations` feeds
   move/copy directly.

## The serialization point (first statement of every topology verb)

Every parent-pointer mutation runs under it (spec 072 §10 — two
individually-safe moves compose a committed cycle without it, observed
in the spike at both RC and RR).

| engine     | mechanism                                                    |
|------------|--------------------------------------------------------------|
| sqlite     | nothing extra — `vfs_writer` already opens BEGIN IMMEDIATE   |
| postgresql | `SELECT pg_advisory_xact_lock(host.topology_key)` at READ COMMITTED (declared `topology_isolation`) — RC is load-bearing: an RR snapshot would be fixed at the lock call itself, so post-lock re-checks would read pre-rival topology |
| everything else (mysql, mssql, oracle, generic) | `UPDATE <meta> SET schema_format_version = schema_format_version WHERE id = 1` — a row X-lock on the single meta row, held to commit; portable, auto-released, serializes rival topology verbs and first touch |

All reads happen **after** the point is taken, inside the same
transaction, so every refusal check judges post-rival state and later
pairs see earlier pairs' effects (read-own-writes).

## Delete (`delete_rows`)

Signature mirrors the write builders plus `targets`, `permanent`,
`cascade`, `user_id`, `lock_key`. Flow:

1. Serialize. Fetch the **pre-batch snapshot** once: all targets +
   their ancestors + `"/"` → `dict[str, RowMapping]` (columns:
   entry_id, parent_id, path, name, kind, version, size_bytes). Derive
   a `path → kind` map for miss classification. This snapshot-first
   order is what makes `test_delete_covered_miss` pass: after `/a` is
   trashed in-transaction, classifying `/a/ghost` against live state
   would blame `/a` instead of the requested target.
2. Per target, in request order (mirror memory's `delete` exactly):
   - root → `invalid` "Cannot delete the root directory".
   - `covered` (cascade AND inside another *unique* target's subtree)
     or repeat (`seen`): judge against the snapshot — present →
     observe `deleted`; missing → classify from the snapshot kinds.
   - miss → classify from the snapshot kinds.
   - `not cascade` and live children exist (`EXISTS` on
     `parent_id == row.entry_id`) → `not_empty`. (Live, not snapshot:
     memory's staged dict gives the same order-dependence.)
   - **permanent arm**: collect subtree ids in one statement
     (`path == target OR path LIKE escape_like(target) + '/%'`), then
     chunked deletes across every family table — content, versions,
     chunks, edges (both `source_id` and `target_id`), entry.
   - **trash arm** (the default): see below.
   - Bump the original parent (`version = version + 1`, unguarded,
     matching `_bump_parents`).
   - Observation: the **pre-delete** snapshot row (`status="deleted"`,
     snapshot version/kind/size) — memory parity; there is no
     post-commit row to stat.
3. Any error fails the batch whole (runner never commits).

### Trash reparent details

- Bucket path: `f"{TRASH_ROOT}/{now:%Y-%m-%d-%H}"` (hourly UTC;
  `TRASH_ROOT` is in `vfs.paths`). Ensure the chain `/.vfs`,
  `/.vfs/trash`, bucket lazily, once per batch: select each; missing →
  INSERT under `begin_nested()`, catching `IntegrityError` →
  re-select (a rival *write op* can mint these concurrently — writes
  are not serialized with topology; this is the designed benign race).
  A non-directory occupant anywhere in the chain classifies
  `wrong_kind` (075 made trash writable — a user file at
  `/.vfs/trash` is possible). Bump each minted dir's parent.
- Reparent the target row in one UPDATE: `parent_id = bucket_id`,
  `name = row.entry_id` (the ULID-as-in-bucket-name pin — two
  same-named deletes can never collide on UNIQUE(parent_id, name)),
  `path = f"{bucket_path}/{entry_id}"`, `original_parent_id`,
  `original_name`, `deleted_at = now`, `version = version + 1`
  SQL-side. **Deliberately unguarded** — a deviation from 072 §5's
  "reparent is guarded" sentence, with this rationale: under the
  serialization point the row cannot vanish (permanent deletes are
  topology verbs too), and a concurrent *edit* composes — the reparent
  touches no material column and both bump SQL-side off the current
  row; on Postgres RR the second committer gets 40001 and retries.
  Record the deviation in the slice's plan notes.
- Rewrite descendant path caches: select `(entry_id, path)` where
  `path LIKE escape_like(old) + '/%'`, compute
  `new_prefix + path[len(old_prefix):]` **in Python on raw `str`** and
  executemany-update. Two traps: (a) **never mint `Path` objects for
  trash-side paths** — a deep row's trash path may exceed
  `MAX_PATH_LENGTH` (1024 bytes) and `Path` validation now rejects on
  bytes; that is fine, backend-authored trash paths only need to fit
  the key budgets, and they always do (1024 + ~53-byte prefix < 1700,
  the tightest `key_byte_budget`); (b) descendant rewrites bump no
  versions and take no guard (072 §5 exemption — else one directory
  move floods the dirty overlay).
- Bump the bucket too (it gained a member).

## Move / copy (one shared `transfer_rows(op, ...)`)

Serialize, then for move only: fetch the **committed** snapshot of all
sources + their ancestors (batch-shape refusals are judged against
committed state — order-independence pin). Then per pair, mirroring
memory's `_transfer` ladder **exactly in this order**:

1. Overlap arm (move only, src ≠ root): duplicate source or source
   inside another moved source → judged against the committed
   snapshot; a missing duplicated source classifies the miss instead
   (`test_move_duplicate_missing_source...`). Messages verbatim from
   memory.
2. `src_row` — **live** point select by path (later pairs must see
   earlier pairs' effects). Miss → `classify_misses` (live probe).
3. src or dest is root → `invalid`.
4. `dest == src` → pending `unchanged`, no statements (POSIX
   rename-to-self).
5. Dest parent gate — live fetch of dest's ancestors + `"/"`; missing
   ancestor → `not_found` at that component (the test asserts
   `error.path == "/ghost"`), non-directory → `wrong_kind`. Yields
   `dest_parent_id` (root row's id when parent is `/`). Trashed
   ancestors miss naturally — their paths were rewritten, which *is*
   the destination-ancestry liveness re-check under this design (all
   reads are post-lock).
6. Occupant (live select of dest). Occupant and `not overwrite` →
   `exists` — **before** the cycle checks (RENAME_NOREPLACE order).
7. Cycle, both directions, one kind (`invalid`):
   `dest.startswith(src + "/")` then `src.startswith(dest + "/")`.
   Fires before occupied-target kind translation (Linux rename-trap
   ordering — the pinned reachability argument).
8. Occupant kind mismatch (dir↔file) → `wrong_kind`; occupant
   directory with live children → `not_empty`.
9. Subtree fetch (`path == src OR LIKE prefix`) and destination path
   minting on raw strings; any new path over `MAX_PATH_LENGTH`
   **bytes** → `unaddressable`, refuse the pair, no statements run.
10. Execute (move) — all statements only after every check passed:
    - occupant present → hard-delete it (entry + content + family
      rows; it is an empty dir or a file — POSIX rename unlinks the
      target, no trash hop).
    - update the moved node: `parent_id`, `name = dest.name`,
      `path = str(dest)`, `version = version + 1` SQL-side (same
      unguarded rationale as the reparent), `updated_at = now`, and
      **clear `original_parent_id`/`original_name`/`deleted_at`** — a
      move out of trash is the restore gesture (ADR 014 pin 4) and a
      live row must not carry trash metadata.
    - rewrite descendant paths (same helper as delete).
    - bump `src_row.parent_id` and `dest_parent_id` (both, even when
      identical — memory applies two increments).
11. Execute (copy):
    - fetch subtree rows with material columns; mint
      `id_map = {old: str(ULID())}`.
    - occupant present → the copy **root** keeps the occupant's
      identity: update its material columns from the source root,
      `version = version + 1` (memory: "an overwritten occupant is a
      material update"), and its content is delete-then-insert.
      Descendants' `parent_id` map through the occupant's id.
    - otherwise all rows are fresh inserts: `version = 1`,
      `created_at = updated_at = now`, `owner_id = user_id`, restore
      columns NULL, `external_id` not copied, **no edge rows copied**
      (spec §9 copy pin). Chunk by `rows_per_statement`.
    - content: select bodies for content-bearing source ids (chunked
      `IN`), insert under mapped ids (driver executemany). A
      Python round-trip is acceptable for v1; note it as the
      optimization seam (INSERT…SELECT with a VALUES join would need
      the `values_join` gate — see the 079 plan for why SQLite can't).
    - bump `dest_parent_id` only when there was no occupant (memory
      parity).
12. Observations: capture `(dest, status, fallback version/kind/size)`
    per pending pair at execution time (`created` when no occupant,
    `updated` otherwise, move root version = old + 1, copy fresh = 1,
    copy-onto-occupant = occupant + 1). After the loop, re-select all
    pending dest paths in one chunked pass and prefer the final values
    — a later pair may have bumped an earlier dest; a dest a later
    pair moved away falls back to the captured values (memory's
    comment documents the same fallback).

## Known traps (learned the hard way this session)

- SQLAlchemy's `values()` construct does not execute on SQLite
  (rejects `AS name (cols)`) — hence the `DialectProfile.values_join`
  gate. Don't reach for VALUES joins in topology without it.
- Always `escape_like()` path prefixes (`%`/`_` are legal in names)
  with `escape=LIKE_ESCAPE`.
- Oracle folds `''` to NULL — never store an empty string in a NOT
  NULL column (this bit provisioning; root name is now `"/"`).
- Paths are byte-denominated: overflow checks use
  `len(s.encode())`/`byte_length`, never `len(s)`.
- `uv sync --extra X` evicts other extras' drivers — sync every
  engine's extra at once (see the db_test skill).

## The open race to file alongside the slice

Once move/delete exist, a **create under a concurrently-moved (or
trashed) directory** can commit a child row whose path carries the
old prefix while its `parent_id` points at the relocated parent — a
torn path cache. Reachability per engine: SQLite safe (single
writer); Postgres safe (op sessions at REPEATABLE READ — the parent
bump on the rival-updated row raises 40001 and the method restarts);
**MySQL, MSSQL, Oracle, and the generic floor are exposed** (their
bumps current-read past the rival's commit). Fix sketch, deliberately
not bolted into slice 9: make `_bump_parents` guard on
`(entry_id, path-at-snapshot)` with 079-style statement attribution —
a guard miss means the parent's path changed mid-op and classifies a
retryable conflict; sibling writes never disturb the path, so the
hot-directory throughput rationale for unguarded bumps survives. File
an open-questions entry when the slice lands (it is unreachable until
then) and give the fix its own story.

## Decide before implementing: the concurrency-pin seam

**A decision is required before `topology.py` work starts — do not
begin the implementation with this open.** The torn-row regression
pin (`tests/test_storage_conformance.py:108`) stages its race by
hand-assembling the backend's write orchestration from private
`writes.py` parts, because the race window is unreachable through the
public surface. That mirror is faithful today, but it omits
`with_retry` and the classification arm, and nothing detects drift:
if the real orchestration changes and the mirror does not, the pin
silently guards a machine that no longer exists. Slice 9 multiplies
the pattern — every topology verb needs rival-injection tests at its
serialization point.

Decide one of:

1. **The code under test owns the seam** — an injectable hook (or
   shared helper) between snapshot and finish that tests use to
   insert a rival mid-window; pins stop mirroring privates entirely.
2. **The mirror is ratified** — a drift test pins the mirror to the
   real orchestration (the lockstep-by-test pattern rows.py uses for
   the model/row split), and the `with_retry`/classification omissions
   are made explicit and deliberate.

Record the choice as a decision (or in this slice's plan) before the
first topology verb lands; the existing pin is refactored to match in
the same slice.

**Decided 2026-07-23 (Clay, in session): option 1 — the code owns the
seam.** Ratified after a prior-art verification pass over the reference
repos: every project that stages deterministic mid-window races owns
the seam in production code or a production-owned boundary — Postgres
`INJECTION_POINT` markers (added in PG17 precisely because the
isolation tester could only pause at statement boundaries or
heavyweight-lock waits, `src/test/isolation/README:147-149`), SQLite
`sqlite3FaultSim` call sites (inert without an installed callback,
compiled out under `SQLITE_UNTESTABLE`), and Oak's injectable
`DocumentStore` SPI with semaphore-breakpoint wrappers
(`PausableDocumentStore`). The two that don't — juicefs (brute-force
goroutines asserting only outcome-set invariants) and seaweedfs (a
test double behind the production `FilerStore` interface) — never
assert a specific interleaving's classification, which our pins do,
and neither mirrors orchestration in tests. Shape: a named, default-off
async hook invoked at the declared window (post-serialization-point /
post-snapshot, pre-execution) in the write and topology runners'
builders; tests install a rival via fixture and drive the real public
verb, so `with_retry` and the classification arm are exercised, not
mirrored. The `test_storage_conformance.py` torn-row pin is refactored
onto the hook in this slice; the hand-assembled mirror is deleted.

**Sequencing (same session): two landings.** Landing 1 — serialization
infrastructure (dialects/engine/runner + seam) and `delete` (trash
reparent, descendant rewrite). Landing 2 — `move`/`copy`. Conformance
rows flip per verb as `capabilities()` declares them, so each landing
is green and fully enforced for what it ships.

## Verification workflow

Land with the sqlite suite + coverage first, then run the full
`db_test` cycle (skill: start Docker Desktop → `up -d --wait` for all
four → four marker legs → profiled teardown → quit). Expected: the
~40 topology conformance rows flip from skipped to passing on every
leg; sqlite leg pass count rises accordingly; coverage stays at 100%
(`_execute_topology`'s options and the postgres/meta-lock arms need
either the marked legs or unit doubles — the serialization helper's
non-sqlite arms are two statements each and unit-testable against a
captured-statement double like `_ReturningSession` in
`test_backends_database.py`). Update `tasks.md` task 12 and
`STATUS.md` when green.
