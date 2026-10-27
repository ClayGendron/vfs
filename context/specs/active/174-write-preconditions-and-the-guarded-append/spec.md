# 174 — Write preconditions and the guarded append: `if_version`, `if_absent`, `append`, and `unchanged`

- **Status:** draft — cut 2026-10-24 from ADR 087 (proposed the same
  day) and the two memos it stands on. Not started. One open
  `[NEEDS CLARIFICATION]` (§9, the content-hash precondition).
- **Date:** 2026-10-24
- **Owner:** Clay Gendron
- **Kind:** feature (three new arguments on `write` across the router,
  the session, the params table and the storage seam; `overwrite=`
  leaves `write`; a pure-Python judgment pass in `staging.py`; a
  locked read-modify-write path in `writes.py`; one companion rung
  constant in `ops.py`; conformance rows on every engine leg).
- **Depends on:** ADR 087 pins 3, 6 and 10 (and pin 15's axis table);
  ADR 080 pin 3 (append maps to `add`) and pin 8 (one rung table);
  ADR 074 rule 5 (a write revives a tombstone); ADR 013 pin 1 (every
  material write adds exactly one to the version); ADR 025 (the
  conflict redrive); ADR 085 pin 12 (a row keeps its source when the
  body allows it). Nothing in flight blocks it. It lands before specs
  167's slice C, 169b and 171, which use it.
- **Decisions it implements:** ADR 087 pin 3 (`write` takes
  `if_version=` and `if_absent=`; `append=True` is a guarded form of
  `write` at the `add` rung), pin 6 (the consistency check sits at
  write time), pin 10's first clause (an identical body reports
  `unchanged` and leaves the version alone). The first memo's §7
  step 3 and the second memo's §5 step 2.
- **Research it stands on:**
  `../../../research/2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md`
  §2.1, §2.4, §5;
  `../../../research/2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md`
  §4.2 (the `write` row of the kernel table) and §7 step 3;
  studies `07-concurrency-locks-structures-events.md` (principle 1, the
  20-append probe, `experiments/s07/lost_update.py`),
  `06-distribution-nfs-afs.md` (§2.1 the replay table, §2.3 what
  `if_version` is, principles 7 and 9) and
  `02-files-and-directories-the-api.md` (principle 10, TOCTTOU), all
  under `../../../research/studies/2026-10-24-ostep-principles-for-vfs/`;
  `../../../research/2026-09-15-filesystem-over-database-landscape-and-vfs-differentiation.md`
  §4.3 (the peers' content-hash preconditions).

## Intent

Today two agents that each read a file, change it, and write it back
both hear "success", and one of them has silently erased the other.
Twenty concurrent appends to one log keep one line. After this spec a
caller can say "replace only the version I read" (`if_version=`) or
"create only if nothing is there" (`if_absent=`), and the refusal
names the version that is there now. An append is one call that reads
and writes inside one transaction, so twenty appends keep twenty
lines on every engine.

The same spec makes a write of the body a file already holds a
no-op. It reports `unchanged`, mints no version, and leaves the
version number where it was. That is what makes `if_version=` safe to
retry: a client that lost the reply to its own write and sends it
again meets its own body and hears `unchanged`, not `conflict`. It is
also what makes an ETL re-ingest of 10,000 unchanged files write
nothing.

## Terms

Each term is used in this sense everywhere below.

| Term | Meaning |
|---|---|
| **precondition** | A condition the caller attaches to a write. If it is false, nothing is written and the call is refused. |
| **snapshot** | The one bounded read (`_fetch_committed` in `writes.py`) that every write batch takes before it decides anything. It holds each target's row, its ancestors and any tombstone. |
| **plan** | The pure-Python pass (`WritePlan` in `staging.py`) that judges every entry against the snapshot. It runs no SQL. A plan with any error runs no mutation statement. |
| **guard** | The `WHERE version = base AND path = … AND deleted_at IS NULL` terms on the material `UPDATE` (`_guarded_stmt`, `_values_update_stmt` in `writes.py`). `base` is the version the snapshot saw. A rival that committed after the snapshot makes the guard match zero rows. |
| **mutation statement** | An `INSERT`, `UPDATE` or `DELETE`. Counts below exclude `BEGIN`, `COMMIT`, `PRAGMA`, `SAVEPOINT`, `RELEASE` and `ROLLBACK`, as `tests/storage/database/test_writes.py` already does. |
| **tombstone** | A deleted row that stays at its path with `deleted_at` set (ADR 074). It is absent to every read. A `write` at its path revives it. |
| **unchanged** | The status a write reports when the body it carries is the body the row already holds. Nothing is written. |
| **rung** | A step of the permission ladder `none < list < read < add < contribute < read_write` (ADR 080). |

## 0. What the code does today (at `ba77449`)

| Fact | Evidence |
|---|---|
| 20 concurrent read-then-write appends: 20 report success, 1 line survives. The same 20 through `edit` keep 20. | EXECUTED again at `ba77449` (`experiments/s07/lost_update.py`, study 07 principle 1). |
| `write` takes no precondition: `path`, `content`, `data`, `overwrite`, `parents`, `authority`. | READ, `base.py` `VirtualFileSystem.write`. |
| `overwrite=False` already is create-exclusive on a live occupant (`exists`), and does not refuse a revive. | READ, `staging.py` `WritePlan.put_file`; ADR 074 rule 5. |
| An identical rewrite reports `updated`, bumps the version, mints no version row, and issues 7 statements: snapshot, guarded `UPDATE`, revision read, body read for the mint, two body `DELETE`s, content `INSERT`. | EXECUTED, `scratchpad/174/baseline.py` (SQLite file, system actor). |
| A 10,000-entry identical rewrite updates 10,000 entry rows and inserts 10,000 content rows; 0 version rows. | EXECUTED, `scratchpad/174/rows.py`. |
| The snapshot does not fetch `content_hash`. | READ, `writes.py` `_fetch_committed`. |
| `vfs.conflict` exists. Its contract: retry class `refresh`, hint "re-read the entry and retry with its current version", `path` is "the entry whose version is stale", and `data` may carry `version`. No producer sets `version` today. | READ, `results/kinds.py` `ErrorKind`, `KIND_CONTRACTS`; `writes.py` `_conflict`. |
| A guard miss on a `reprobe` dialect (SQLite, Postgres, SQL Server, Oracle) returns `conflict`, retryable. On a `redrive` dialect (MariaDB, the generic floor) it raises `StaleSnapshot` and the whole method reruns from a fresh snapshot. | READ, `writes.py` `_classify_guard_misses`; `dialects.py` `guard_miss`. |
| Writes run at `op_isolation` (REPEATABLE READ on Postgres and MariaDB). Topology verbs run at `topology_isolation` (READ COMMITTED) so their checks read post-rival state. | READ, `dialects.py` `op_execution_options`, `topology_execution_options`. |
| `delete` bumps the root row's version; covered descendants keep theirs. | READ, `trash.py` `assign`. So a version number alone cannot tell a tombstone from a live row. |
| `Entry` carries no `version`: "a caller cannot author one". | READ, `models/entry.py` `Entry` docstring. |

## 1. The surface

### 1.1 Signatures

```python
# vfs/base.py — VirtualFileSystem
async def write(
    self,
    entries: Sequence[Entry] | None = None,
    *,
    path: str | None = None,
    content: str | None = None,
    data: bytes | None = None,
    if_version: int | None = None,
    if_versions: Mapping[str, int] | None = None,
    if_absent: bool = False,
    append: bool = False,
    parents: bool = False,
    authority: Authority | None = None,
) -> Result: ...
```

- `Session.write` (`session.py`) mirrors it, minus `authority`.
- **`overwrite=` leaves `write`.** `if_absent=True` is today's
  `overwrite=False`, with one name for one fact. The default
  (`if_absent=False`) replaces an occupant, as `overwrite=True` does
  today. No alias: there are no users to migrate (greenfield). The
  ~45 test call sites and `exceptions.py`'s write docstring move with
  it. Internals that pass `overwrite` between `write_rows`, `_finish`
  and the arbitration helpers keep that word; it means "a create may
  land on an occupant", which `edit` and `mkdir` also pass.
- **`if_version`** is the single form's precondition. **`if_versions`**
  is the batch form's: a mapping from path to expected version. It is
  the plural of `if_version` the way `entries` is the plural of
  `path` (ADR 087 pin 3: the plural forms stay).
- `append` and `if_absent` apply to every entry of the call.

The storage seam takes one shape for both forms:

```python
# vfs/storage/protocol.py — SupportsMutation
async def write(
    self,
    *,
    entries: list[Entry],
    if_versions: Mapping[Path, int] | None = None,
    if_absent: bool = False,
    append: bool = False,
    parents: bool = False,
    authority: Authority | None = None,
) -> Result: ...
```

The router turns `if_version=N` on the single form into
`if_versions={path: N}`. Storage never sees the single form.

### 1.2 Why the batch precondition is a path-keyed mapping

Three shapes were weighed for "a precondition per row of a 10,000-row
batch".

| Shape | Verdict |
|---|---|
| A field on `Entry` | Rejected. `Entry` is the stored file; its docstring forbids a caller-authored version. A cross-mount copy passes `Entry` rows read from another mount, and an implicit precondition would refuse them. |
| A list parallel to `entries` | Rejected. Position silently carries meaning (the smell CLAUDE.md names). A reorder breaks it, and the router reorders by depth. |
| **A mapping from path to version (chosen)** | Keyed by the one identity an entry has. Survives the router's depth sort and the per-mount split. Costs no statement: the plan reads it from a dict. On the wire (spec 171) it is a JSON object. |

Mixing `append` and plain rows, or `if_absent` and plain rows, in one
call is out of scope. Each is one call, which is one transaction per
mount. A caller that needs both in one transaction is the request a
per-row options type would answer; none exists today.

### 1.3 The ingress rules (`vfs/params.py`)

| Rule | Where | Refusal |
|---|---|---|
| `if_version` is an int in `[1, INT_CEILING]` | `ParamSpec("if_version", "int", minimum=1, maximum=INT_CEILING)` | `invalid` |
| `if_versions` is a mapping of str to int in `[1, INT_CEILING]` | new `ParamKind` `"versions"`, checked item by item in `_check_value` | `invalid` |
| `if_version` only with the single form; `if_versions` only with `entries` | two `ShapeRule`s, `exactly_one=False` | `invalid` |
| `if_absent=True` with `if_version` or `if_versions` | `OnlyWith` rules | `invalid` ("an absent row has no version") |
| `if_absent=True` with `append=True` | `OnlyWith` rule | `invalid` (it is one spelling of an `if_absent` write) |
| every key of `if_versions` names a file entry of the batch, after `resolve_path(key, mutation=True)` | `_route_entry_batch` | `invalid` naming the key |
| under `append=True`, every entry is a file | `_route_entry_batch` | `invalid` naming the path |

`overwrite` leaves `PARAMS["write"]`; the signature drift test in
`tests/test_params.py` moves with it.

### 1.4 Routing (`_route_entry_batch` in `base.py`)

- The router resolves each `if_versions` key with the same
  `resolve_path(..., mutation=True)` it applies to each entry path. It
  matches keys to resolved entry paths, then rebases each matched key
  with its entry (`Entry.without_mount`). Each per-mount group carries
  its own `if_versions` slice to `_dispatch_entry`.
- A batch that spans two mounts stays per-mount atomic (ADR 087
  pin 7). A stale key on mount `/a` refuses `/a`'s group whole; `/b`'s
  group may land. That is today's rule for any refusal, unchanged.

## 2. The judgments, in order

The plan judges every entry in this order. The first failing step
answers. Nothing here issues SQL.

1. **Today's address gates, unchanged:** the trash view, the
   key-byte budget, the engine's value cap, the POSIX parent rule.
2. **`if_absent`:** any live occupant, file or directory, refuses
   `exists` (§5). This comes before the kind check, as POSIX's
   `O_EXCL` answers `EEXIST` over a directory too.
3. **The occupant's kind, unchanged:** a directory at a file entry's
   target is `wrong_kind`.
4. **`if_version` against a missing row:** no live row at the target
   refuses `not_found` (§4.2). A tombstone refuses `not_found` with the
   trashed hint. A precondition never revives.
5. **Stage:** compose the body for an append (§6), then stage a
   create, an update or a revive as today.
6. **Settle, once, after every entry is staged** (`WritePlan.settle`,
   §3): drop each staged update whose final body equals the committed
   one (`unchanged`), then refuse each remaining update whose expected
   version is not the committed one (`conflict`).

The rights gate (`gate.targets` in `backend.py`) runs before the
plan, as today. So a caller who may not touch a row never reaches a
judgment that would describe it.

| Target at the snapshot | no precondition | `if_version=N` | `if_absent=True` | `append=True` |
|---|---|---|---|---|
| absent | create | `not_found` | create | create with the tail as the body |
| tombstoned file | revive | `not_found` + trashed hint | revive (ADR 074 rule 5) | revive with the tail as the body |
| live file, same body | `unchanged` | `unchanged` (whatever N is) | `exists` | `unchanged` only if the tail is empty |
| live file at version N, new body | update to N+1 | update to N+1 | `exists` | update: old body + tail |
| live file at version V ≠ N, new body | update | `conflict`, `data={"version": V}` | `exists` | update (with `if_version=N`: `conflict`) |
| live directory | `wrong_kind` | `wrong_kind` | `exists` | `wrong_kind` |

## 3. The `unchanged` rule (ADR 087 pin 10, first clause)

**The rule.** A staged update on a live row whose final material
equals the committed material is dropped from the plan. Its entries
report `status="unchanged"` with the committed version. "Material" is
four columns: `kind`, `source`, `content_hash` and `mime_type`. Every
other column a write sets (`size_bytes`, `lines`, `ext`) is derived
from those, or is a stamp (`render_*`, `encoded`, `updated_at`) that
stays true when the body does not change.

**Why `mime_type` is in the set.** A text write with no declared type
stores `NULL` (EXECUTED: the probe's stat shows `mime_type None`). A
caller who declares a new type on the same body is changing the row.
That is an update, not a no-op.

**Why `source` is in the set.** `measure_text` hashes the UTF-8 bytes,
so the text `"hi"` and the bytes `b"hi"` hash equal. A text row
rewritten as bytes changes its source and must be an update.

**Code.**

- `_fetch_committed` adds `entry.c.content_hash` to its columns. One
  more column on a select that already runs. No new statement.
- `WritePlan.settle()` (new, `staging.py`) runs at the top of
  `_finish`, before `if plan.errors`. It walks `self.staged`; for each
  row with `persistence == "update"` and `revive is False`:

  ```python
  row = self.committed[str(path)]
  if _same_material(staged, row):
      del self.staged[path]
      self._mark(path, "unchanged")
  elif staged.expected_version not in (None, row["version"]):
      self.errors.append(stale_version(path, row["version"]))
  ```

  `_mark` rewrites every `pending` tuple for that path. `_finish`
  already builds a pending row with no staged entry from the committed
  row (kind and version), so the observation equals a post-commit
  `stat`.
- Because settle sees the **final** staged state, a batch that writes
  `/a` twice (B, then back to A) also settles `unchanged`. Today that
  case bumps the version and mints nothing.
- A revive is never `unchanged`: it clears a tombstone, which is a
  change. A create is never `unchanged`.
- `edit` runs through `_finish` too, so an edit whose result equals
  the body (`old == new`, or a sequence that cancels out) reports
  `unchanged` and mints nothing. That is the same rule; no other
  change to `edit`.
- With every row dropped, `plan.staged` is empty and `_apply` returns
  at its first line. **An all-unchanged batch issues zero mutation
  statements** at any size.

**What it saves (EXECUTED baseline, INFERRED after).**

| Call | Today | After |
|---|---|---|
| One identical rewrite | 7 statements; reports `updated`, version +1 | 1 statement (the snapshot); `unchanged`, version stays |
| 10,000 identical rewrites | 10,000 entry rows updated; 10,000 content rows inserted; every pre-image read by the mint | 0 rows written; 0 bodies read beyond the snapshot |

**One consequence for integrity (spec 175).** The rule trusts the
entry row's `content_hash`. If an out-of-band writer changed a body
without its hash, a rewrite of the correct body now reports
`unchanged` and repairs nothing. Today's rewrite would repair it.
Spec 175's verify-on-read detects the rot; its repair path cannot be
"write the same body again". See the rebase notes.

## 4. `if_version`: judged at the snapshot, carried by the guard

### 4.1 The happy path costs nothing new

- `StagedEntry` gains `expected_version: int | None`. `put_file` sets
  it from `if_versions.get(target)`.
- When the expected version equals the snapshot's, the staged
  update's `base_version` already equals it. The existing guard
  (`version = :b_base` in `_guarded_stmt`, `version = v_base` in
  `_values_update_stmt`) then compares the row against the caller's
  version, inside the `UPDATE`. **The precondition rides the guard
  that is already there.** No statement is added, at any batch size.

### 4.2 A stale or missing precondition runs no mutation statement

- **Stale.** `settle` refuses `conflict` before `_apply` runs. The
  refusal is `stale_version(path, current)` (new, in `staging.py`
  beside the plan that raises it; `writes.py` imports `staging.py`,
  never the reverse):

  ```python
  classified(ErrorKind.conflict, path, data={"version": current})
  ```

  `retryable` stays `False`. An identical retry carries the same stale
  version and fails again; the contract's retry class `refresh` ("re-
  read, then retry") is the right instruction, and the `version` in
  `data` is what to retry with.
- **Missing.** No live row at the target refuses `not_found`, judged
  from the snapshot the plan already holds: the parent rule is applied
  as if `parents=False` (a row expected to exist implies its parents
  exist), so a missing ancestor answers at that ancestor; a missing
  target answers at the target. `edit` answers the same way. `not_found`
  rather than `conflict`, because "the row is gone" and "the row moved
  on" call for different next steps, and the existing guard-miss
  reprobe already splits them that way.
- **Tombstoned.** Refuses `tombstone_miss(target, deleted_at)`:
  `not_found` with the trashed hint. A precondition never revives,
  even when the numbers happen to match (a covered descendant keeps
  its version through a delete; §0).
- Any refusal fails the whole batch (the plan rule). Every stale row
  is listed, not only the first: the plan accumulates.

### 4.3 A rival inside the window

The window is the time between the snapshot read and the `UPDATE`
(the `write:before-apply` seam in `_finish`).

- **`reprobe` dialects.** The guard matches zero rows. The reprobe in
  `_classify_guard_misses` already selects by `entry_id`; it adds
  `entry.c.version` and `entry.c.content_hash` to that select. A missed
  row whose current hash equals its staged hash raises `StaleSnapshot`:
  the rival wrote our body, and the redrive's `settle` answers
  `unchanged`. Every other miss is a `conflict` that now carries
  `data={"version": current}`. A row with an expected version gets
  `retryable=False`; a row without one keeps `retryable=True`, as
  today (an identical retry of a plain write succeeds).
- **`redrive` dialects.** `StaleSnapshot` reruns the method. For a row
  with an expected version, the fresh snapshot holds the rival's
  version, and `settle` answers: `unchanged` if the rival wrote our
  body, else `conflict` with the version. The same answers as
  `reprobe`, by a different road. A plain row re-plans over the
  rival's body and lands, last writer wins, as today.
- **Retry exhaustion** (`_mutate`'s `except StaleSnapshot`) is
  unchanged: a pathless, retryable `conflict`.

### 4.4 The replay of one's own write (study 06 §2.3)

A client writes body X with `if_version=1`. The write lands (version
2). The reply is lost. The client sends the same call again. The
replay meets version 2, and the committed body is X. `settle` checks
`unchanged` **before** the version, so the answer is `unchanged` at
version 2, not `conflict`.

Is answering `unchanged` when V ≠ N ever unsafe? The danger
`if_version` exists to stop is erasing a rival's change. An
`unchanged` answer writes nothing, so it erases nothing. The file
holds exactly what the caller asked for. The only thing the caller
does not learn is that the file passed through other bodies in
between; `version` in the observation tells it the counter moved.

## 5. `if_absent`: create-exclusive

- **A live occupant refuses `exists`.** The kind already says exactly
  this: "EEXIST: the site is occupied and this verb never replaces an
  occupant". No child kind is needed. POSIX's `O_EXCL` answers
  `EEXIST`, and spec 169 §b7 maps `exists` to errno 20.
- **The refusal carries the occupant's `version` and `content_hash`**
  in `data` (new helper `occupied(path, row)` in `staging.py`, used by
  `put_file` and by the arbitration probes in `writes.py`). That
  makes a lost-reply replay recognisable: a client that sees its own
  hash at version 1 knows its create landed. It does **not** turn the
  replay into success. An identical body from another caller must
  still refuse, or two agents creating the same lock file would both
  hold the lock.
- **A tombstone is absent, so `if_absent=True` revives it** (ADR 074
  rule 5: "`overwrite=False` does not refuse a revive, since no live
  row occupies the path"). Every read already treats the path as
  empty; create-exclusive judges what a caller can see. The revive is
  still judged as a restore (`read_write` or own; ADR 080 pin 3), so
  nobody revives another's deleted row at a lower rung. It reports
  what a revive reports today, `updated`.
- **A directory entry under `if_absent`** refuses `exists` on any
  occupant (`put_dir` gains `exclusive: bool`), matching `mkdir`
  without `exist_ok`.
- **Arbitration.** Two concurrent `if_absent` creates of one absent
  path both pass the snapshot. Both insert. One wins the
  `(parent_id, name)` index; the loser, created with `clobber=False`,
  is classified by `_classify_arbitration_loss` / `_resolve_rows` as
  `exists`. That is today's `overwrite=False` path. The occupant probe
  there adds `content_hash` to its select so the late `exists` carries
  the same `data`.
- **The rung.** An `if_absent` write never replaces an occupant's
  bytes, so an occupied target is judged at `add`, not `contribute`
  (§6.6). An `add` holder who tries to create over a file hears
  `exists`, the true answer, rather than `permission_denied`.

## 6. `append=True`: one read-modify-write inside one transaction

### 6.1 Why in the kernel, and why this shape

ADR 087 pin 15 asks every kernel-level choice to be scored on one
table. Three ways to append were weighed.

| Axis | (a) The front loops `read` + `write(if_version=)` | (b) **Storage appends inside one transaction, under a row lock (chosen)** | (c) SQL concatenation (`content = content \|\| :tail`) |
|---|---|---|---|
| Agent latency | 2 calls per try, more under contention | 1 call | 1 call |
| ETL throughput | 2N statements' worth of round trips | the batch's bounded chunks | bounded |
| Boundedness | bounded | bounded (§7) | bounded |
| Correctness under rivals | correct, but each loser retries the whole round trip | correct; rivals queue on the lock | cannot compute `content_hash` or mint the pre-image without reading the body |
| Atomic unit | per try | one call | one call |
| Dialect reach | all | all (`lock_rows` spells every engine) | per-dialect concat and blob concat; fails the hash law |
| Protection | as `write` | judged at `add` (§6.6) | — |
| Overhead | the body crosses the wire twice | the body is read once, inside the engine connection | none, but breaks integrity |

(c) is out: sha256 cannot be extended from a stored digest, so the
whole new body must be hashed, and the version mint must keep the
pre-image. Both need the body in hand. (a) is what a front can do
today with `if_version` alone, and is the fallback for a backend that
declares no append (§6.8). (b) is `edit`'s model, which the probe
already showed keeps all 20 lines.

### 6.2 The transaction

`DatabaseStorage.write(append=True)` runs through a new runner,
`_execute_append`, which is `_mutate(op, fn,
topology_execution_options(profile))`. It borrows the topology
verbs' isolation pin (READ COMMITTED where a profile declares
`topology_isolation`; the engine default elsewhere) for the same
reason they use it: the check must read state committed **after** the
lock was taken. It takes **no** serialization point. The profile field
(`topology_isolation`) and the function keep their names; their
docstrings name the append as their second user. Inside it,
`write_rows(..., append=True)`:

1. **Locks the targets that exist.** `_lock_targets` sorts the batch's
   target paths and issues `locked_lookup(entry, entry.c.path, chunk,
   [entry.c.entry_id], profile)` per `chunked(paths, membership_budget)`.
   Absent targets lock nothing. The sort is the lock order every write
   pass already uses (commit `25f6da4`), so an append batch and a plain
   batch cannot deadlock on each other.
2. **Reads the snapshot with bodies, in a new statement.**
   `_fetch_committed(..., bodies=True)` selects from
   `tables.bodies_joined(content=True, data=True)` and adds
   `content` and `data` to its columns. It must be a second statement:
   on Postgres a `FOR UPDATE` that waited re-checks the locked row but
   not the joined body row, so a one-statement lock-and-read could
   hand back the predecessor's stale body. At READ COMMITTED the next
   statement sees the predecessor's commit.
3. **Composes each body** (§6.3), in entry order, through the staged
   overlay: a path appended twice in one batch appends to its own
   staged output, as `edit` does.
4. **Stages, settles and applies** exactly as a plain write. The guard
   still rides the `UPDATE`.

On SQLite the lock read renders as a plain `SELECT` (EXECUTED:
SQLAlchemy's SQLite compiler renders no `FOR UPDATE`) and costs one
statement; the
writer lock that `BEGIN IMMEDIATE` takes at the first read already
serializes appenders. On SQL Server `lock_rows` spells
`WITH (UPDLOCK, FORCESEEK)`; `in_list_budget` doubles as the lock
budget there, under the 5,000-lock escalation trigger.

### 6.3 Composing the body (`vfs/storage/editing.py`)

A new pure function beside `edited_entry`, so every backend appends
alike:

```python
def appended(source: Source | None, body: str | bytes | None, tail: Entry) -> tuple[Source, str | bytes]:
    """The body an append leaves: the stored body, then the tail, under the keep-the-source rule.

    No stored body (an absent or tombstoned target) leaves the tail as the
    whole body. Otherwise the two join as bytes. A text row stays text when
    the joined bytes are UTF-8 without NUL; a bytes row stays bytes.
    """
```

- This is ADR 085 pin 12's write-back rule, applied once in the kernel
  so no front repeats it. Spec 167's `>>` passes its stage's plain
  bytes; spec 169b's `O_APPEND` flush passes bytes; both land on a
  text log as text.
- A text row whose joined bytes are not UTF-8 (or hold a NUL) becomes
  a bytes row, as pin 12 says for any write-back. It is an update like
  any source change: the render stamp resets to `pending`.
- The composed row keeps the stored `mime_type`. An append to an
  absent path takes the tail entry's.

### 6.4 Measuring the composed body

The composed body needs a new sha256, size and line count. A body of
`MEASURE_OFFLOAD_BYTES` or more is measured through
`call_offloaded(host executor, …)` (`offload.py`); a smaller one
inline, by `measure_text` or `measure_bytes`. This is ADR 087 pin 9's
threshold rule, already applied to the router's write path in
`ba77449`. `MEASURE_OFFLOAD_BYTES` moves from `base.py` to
`models/version.py`, beside the measure functions, so `base.py` and
`writes.py` import one constant. Pinned by counting offload calls,
never by time.

### 6.5 The version mint reads nothing twice

The mint already reuses a text pre-image the snapshot joined
(`StagedEntry.base_content`). `StagedEntry` gains `base_data` for a
bytes pre-image, and `mint_versions` (`versions.py`) uses either. An
append therefore reads each pre-image once, in the snapshot.

### 6.6 The rung: `add` (ADR 080 pin 3)

- `ops.py` gains, beside `VERB_RUNGS`:

  ```python
  ADDITIVE_WRITE: Final[Needs] = Needs("add", create="add")
  """The rungs of a write that removes no stored byte: create-exclusive and append."""
  ```

- `DatabaseStorage.write` passes `ADDITIVE_WRITE` to `self._gate`
  when `append` or `if_absent` is set, else `VERB_RUNGS["write"]`.
  The gate mode stays `"upsert"`. A tombstoned target is still judged
  as a restore (the gate's own tombstone branch reads
  `VERB_RUNGS["restore"]`).
- Why this is safe. An append cannot remove or alter a stored byte;
  it only adds after the last one, and the pre-image is kept as a
  version. An `if_absent` write never lands on an occupant at all.
  Neither can widen what a caller can destroy. This is NFSv4's
  `APPEND_DATA` beside `ADD_FILE` and Plan 9's `DMAPPEND`, the
  precedent ADR 080 cites.

### 6.7 Arbitration and guard misses redrive an append

An append carries the kernel's own precondition, not the caller's.
So when a rival beats it, the right move is to recompute, not to
refuse.

- **Create race.** Two appends to one absent path both insert. The
  loser (inserted with `clobber=False`, `StagedEntry.append = True`)
  raises `StaleSnapshot` in `_classify_arbitration_loss` and
  `_resolve_rows`, never `exists` and never an absorb (an absorb would
  clobber the winner's line). The redrive locks the winner's row and
  appends to it.
- **Guard miss.** Under the row lock this should not happen. If it
  does, a missed row with `append = True` raises `StaleSnapshot` in
  `_classify_guard_misses` on every dialect, rather than returning
  `conflict`.
- **With `if_version=N` as well**, the caller's precondition wins: a
  version mismatch at the snapshot refuses `conflict` (§4.2). That is
  the at-most-once append (§10).
- The retry budget is `with_retry`'s four attempts. With rivals
  queued on the lock, an append redrives at most once (the create
  race), so twenty appenders do not exhaust it.

### 6.8 A backend that declares no append

The kernel serves `append` only through a backend's `write`. A
backend that cannot hold a row lock across a read and a write must
not claim it. The seam declares nothing new in this spec; spec 179
(the storage seam as the kernel) owns the capability names
(`write_preconditions` in the kernel memo §4.5). Until then the only
backend is `DatabaseStorage`, and `InMemoryStorage` is the same class
over SQLite.

## 7. Batches and boundedness (10,000 rows, the tightest engine)

`B` is `membership_budget(profile, parameter_budget)`: 1,000 on
Oracle's `IN` cap, 2,000 on SQL Server's declared `in_list_budget`. `N` is the
batch size.

| Step | Statements | Helper that chunks it | Added by this spec |
|---|---|---|---|
| the lock read (append only) | `ceil(N / B)` | `chunked` + `locked_lookup` | yes, append only |
| the snapshot (targets, ancestors, tombstones; bodies for append) | `ceil(paths / B)` | `rows_by_path` | no (one more column; two joins for append) |
| precondition and `unchanged` judgments | 0 | pure Python | yes, zero statements |
| the guarded material `UPDATE` | one per chunk | `statement_budget` + `chunked` in `_values_update`; per-row floor as today | no |
| the version mint | as today, minus the body read for append | `byte_chunked` + `chunked` in `mint_versions` | no |
| body `DELETE` + `INSERT` | as today | `chunked`, `bulk_insert`, `byte_chunked` | no |
| the reprobe on a guard miss | `ceil(missed / B)` | `chunked` | two more columns |

- A 10,000-row `if_versions` batch issues **the same statements** as
  the same batch without preconditions. The mapping is read in Python.
- One stale key in that batch refuses the whole batch at `settle`:
  **zero mutation statements**, one `conflict` per stale key.
- One call is one transaction per mount at any `N` (ADR 087 pin 7).
- **Memory, stated honestly.** An append batch holds every target's
  whole pre-image and composed body in memory, as `edit` does today.
  The bodies are paged by nothing but the membership chunk. The named
  direction, if a measured ETL append workload needs it, is to page
  the snapshot's body join by bytes the way the mint pages
  (`byte_chunked` over `base_size_bytes`). No cap is declared.

## 8. Error kinds and their `data`

No new kind. Two `data` records are added to the per-kind list in the
`ErrorKind` docstring (`results/kinds.py`).

| Refusal | Kind | `path` | `data` | `retryable` |
|---|---|---|---|---|
| `if_version` stale at the snapshot | `conflict` | the target | `{"version": current}` | `False` |
| `if_version` row lost the guard (reprobe) | `conflict` | the target | `{"version": current}` | `False` |
| plain write lost the guard (reprobe) | `conflict` | the target | `{"version": current}` (new) | `True` (unchanged) |
| `if_version` on no live row | `not_found` | the first missing component | the trashed hint on a tombstone | `False` |
| `if_absent` over a live row | `exists` | the target | `{"version": v, "content_hash": h}` (new) | `False` |
| `if_absent` lost arbitration | `exists` | the target | `{"version": v, "content_hash": h}` (new) | `False` |

The rule for `retryable` on `conflict`, stated once: it is `True` only
where the caller stated no precondition, because only there does an
identical retry adjudicate afresh and succeed.

## 9. The open question this spec closes

`open-questions.md`, "Write preconditions on the wire: expected
version, content hash, or both?" The answer here:

- **The kernel takes an expected version** (option a). It is vfs's own
  coordinate. Every row a read returns already carries it. It has no
  ABA hole: a body that goes A → B → A has moved from version 1 to 3.
  It is what every vfs front holds after its read: the shell's `sed -i`
  and the WASI open (spec 169 §b4 reads `version`), and a model, which
  can copy a version number from a read result but cannot compute a
  sha256 in its head.
- **A mismatch is `vfs.conflict`** (ESTALE), not a child of `invalid`.
  The caller's input is not wrong; the world moved.
- **A content-hash precondition composes over it without a gap.** An
  adapter speaking a peer's protocol (Anthropic's `content_sha256`,
  memgres's `base_hash`) does `stat` → compare the hash → `write(
  if_version=V)`. If the write succeeds, the row was still at version
  V, whose hash matched. The window between the `stat` and the
  `write` is closed by the version, so this is correct, at the cost of
  one more round trip.
- **The `unchanged` rule already gives the hash's one extra power**:
  a replay that meets its own body succeeds whatever the version.

[NEEDS CLARIFICATION: accept a content-hash precondition (`if_hash=`)
beside `if_version=` now, or not until an adapter needs it? Accepting
it costs no statement (the snapshot now fetches `content_hash`, and
the precondition would ride the same version guard) but adds a second
precondition argument and its batch twin to every surface. The
2026-09-15 landscape memo recommended adopting the peers' hash idiom
on the served surface. This spec recommends waiting: the version is
sufficient and correct for every in-flight front, and a hash form is
additive later.]

On landing, the entry moves to `open-questions-archive.md` as resolved
by this spec, with the marker's answer recorded.

## 10. The replay rows this spec fixes (feeds spec 177)

| Call, sent twice | Before | After |
|---|---|---|
| `write` same body | `updated`, version +1 | `unchanged`, version stays |
| `write(if_version=N)` whose first send landed | (no such argument) | `unchanged` at N+1 |
| `write(if_absent=True)` whose first send landed | `exists`, no data | `exists` with the occupant's `version` and `content_hash`: recognisable |
| `write(append=True)` | (no such argument) | appends twice: **not** idempotent. An append is an increment, the first vfs write that is not a store of a value (study 06 §4) |
| `write(append=True, if_version=N)` | — | the replay meets N+1 and a different body: `conflict`, `data.version = N+1`. At most once, recognisable by the version |

Exactly-once append needs the request key of ADR 087 pin 10, which is
spec 177's. `idempotentHint` for the `write` tool is spec 171's and
177's call; the facts it rests on are these rows.

## Scope

**In:** the three arguments and `if_versions` on the router, the
session, the params table and the seam; `overwrite=` retired from
`write`; `WritePlan.settle` and the `unchanged` rule for `write` and
`edit`; the locked append path; `ADDITIVE_WRITE`; the two new `data`
records; the guard-miss reprobe carrying `version`; the measure
threshold constant's move; conformance rows; docs.

**Out:** a content-hash precondition (§9); per-row `append` or
`if_absent` inside one batch; `if_version` on `edit`, `delete`,
`move` and the rest (edit's content match is its precondition, pin 6);
the request key and exactly-once append (177); `move`/`copy`
`replace=` (spec 167's task with pin 17); returning `content_hash` on
every written row (175); capability names on the seam (179); paging
an append batch's bodies by bytes (§7).

## Acceptance criteria

Counts and states, never clocks. "Every engine leg" means a
`StorageContract` row, so it runs on the memory, SQLite-file,
Postgres, MariaDB, SQL Server and Oracle legs. Statement counts are
pinned on the SQLite file leg in `tests/storage/database/test_writes.py`
with the `before_cursor_execute` listener already used there.

**The three the brief requires**

1. **The 20-task append probe keeps 20 lines** (every engine leg). On
   a file holding `line0\n`, 20 concurrent tasks each call
   `write(path, content=f"{i}\n", append=True)`. All 20 report
   success, the body has 21 lines, and each `i` appears exactly once.
   The same run starting from an absent path keeps 20 lines, and at
   least one `StaleSnapshot` redrive is counted (spied) on the
   arbitration path, never an `exists`.
2. **A stale `write(if_version=)` runs zero mutation statements.**
   Write `/a` as `"one"` (v1), then as `"two"` (v2), then
   `write("/a", content="x", if_version=1)`: the result fails with one
   `conflict` at `/a`, `data == {"version": 2}`, `retryable is False`;
   the listener records **zero** `INSERT`, `UPDATE` or `DELETE`
   statements and exactly one non-control statement (the snapshot);
   `stat` still says v2 with the v2 hash; the version-row count is
   unchanged (every engine leg for the state; SQLite for the count).
3. **An identical-body write mints nothing and reports `unchanged`.**
   Rewriting `/a` with its own body: status `unchanged`, version
   unchanged, **zero** `INSERT INTO vfs_versions`, zero mutation
   statements, one non-control statement in all (was 7). The same for
   a bytes row (every engine leg; SQLite for the count).

**`unchanged`**

4. A 10,000-entry identical rewrite reports 10,000 `unchanged` rows
   and writes 0 entry rows and 0 content rows (was 10,000 and 10,000,
   EXECUTED baseline), counted by the listener.
5. A batch of 3 changed and 3 identical rows updates exactly 3 entry
   rows and mints at most 3 version rows; the 3 identical rows report
   `unchanged` at their old versions.
6. A batch that writes `/a` as B then back to its stored A reports
   `unchanged` and leaves the version alone.
7. A same-body write with a new declared `mime_type` is `updated`; a
   text body rewritten as the same bytes is `updated` with
   `source == "bytes"`.
8. An `edit` whose result equals the body reports `unchanged` and
   mints nothing; a real edit keeps its pinned count (7).
9. A revive with the body the tombstoned row held is `updated`, never
   `unchanged`, and the row is live after.

**`if_version`**

10. A passing `write(if_version=N)` reports `updated` at N+1, and the
    guarded statement's base parameter is N (spied on the statement's
    parameters).
11. A replay of one's own write: `write(X, if_version=1)` → v2; the
    same call again → `unchanged` at v2, success. A different body
    with `if_version=1` → `conflict`, `data.version == 2`.
12. A rival committed at the `write:before-apply` seam makes an
    `if_version` write fail `conflict` with `data.version` equal to
    the rival's version, on a `reprobe` leg and on the MariaDB
    `redrive` leg; the rival's body survives. If the rival wrote the
    same body, the answer is `unchanged` on both.
13. `if_version` on an absent path is `not_found` at the target; under
    a missing parent, `not_found` at the parent even with
    `parents=True`; on a tombstoned file, `not_found` carrying
    `vfs.trashed`, and the row stays tombstoned.
14. A 10,000-entry batch with `if_versions` for every row issues the
    same number of statements as without (counted, with
    `in_list_budget` narrowed to 1,000 as `test_graph.py` does). With
    one stale key it fails whole with exactly one `conflict`, zero
    mutation statements, and every row at its old version.
15. The ingress rules of §1.3 each refuse `invalid` naming the
    parameter: `if_version=0`, `if_version` with `entries`,
    `if_versions` with `path`, `if_absent` with `if_version`,
    `if_absent` with `append`, a key naming no entry, a key naming a
    directory entry, `append` with a directory entry.

**`if_absent`**

16. `if_absent=True` on an absent path is `created`; on a live file it
    is `exists` with `data["version"]` and `data["content_hash"]` of
    the occupant and zero mutation statements; on a tombstoned file it
    revives the row and keeps its `entry_id`.
17. 20 concurrent `write(if_absent=True)` calls to one absent path:
    exactly 1 success and 19 `exists` (every engine leg).
18. A caller holding `add` on `/drop` (and not owning `/drop/x`, which
    another owns): `write(/drop/x, if_absent=True)` is `exists`, not
    `permission_denied`; a plain overwrite is `permission_denied`. A
    caller holding only `list` on `/drop` gets `permission_denied` from
    the gate for the same `if_absent` write, never `exists` or its
    `data`.

**`append`**

19. An append to a bytes row leaves `data == old + tail`; a text tail
    on a bytes row appends its UTF-8 bytes; a non-UTF-8 tail on a text
    row turns the row into a bytes row holding `old.encode() + tail`;
    a UTF-8 bytes tail on a text row keeps it text.
20. An append to a directory is `wrong_kind`; `append` with an empty
    tail is `unchanged`.
21. A single-file text append on SQLite issues 8 non-control
    statements: the lock read, the snapshot, the guarded update, the
    revision read, the version insert, two body deletes, the content
    insert. No second `SELECT` of the pre-image (the mint reuses it).
22. A caller holding `add` appends to another's row with success; the
    same caller's plain overwrite of that row is `permission_denied`.
    An `add` holder's append to another's **tombstoned** row is
    `permission_denied` (judged as a restore).
23. A 10,000-entry append batch with `in_list_budget` narrowed to
    1,000 issues `ceil(10,000 / B)` lock reads, one `COMMIT`, no
    `IN` list longer than `B` (counted by the listener), and every row
    ends `old + tail`.
24. A composed body of `MEASURE_OFFLOAD_BYTES` or more is measured
    through exactly one `call_offloaded` hop; a smaller one through
    none (spied).

**The tree**

25. `overwrite` is absent from `write`, `Session.write`, the seam and
    `PARAMS["write"]`; the drift tests pass. `ADDITIVE_WRITE` has its
    invariant test (no rung below `add`, `create` not above
    `primary`).
26. `scripts/ci.sh` is green at 100% coverage after every task, and
    the four real-engine legs are green before the append task lands.

## ADR amendments this spec needs

- **ADR 087 pin 3:** `overwrite=` leaves `write`; `if_absent=` replaces
  it. The batch form of `if_version` is `if_versions=`, a mapping from
  path to version. `append` and `if_absent` judge an occupied row at
  `add`.
- **ADR 087 pin 10:** the `unchanged` rule also covers `edit` (a
  result equal to the body), and "material" is `kind`, `source`,
  `content_hash` and `mime_type`. A replay of an `if_version` write
  that meets its own body answers `unchanged` whatever the version.
- **ADR 080 pin 3 and pin 8:** the append rung is landed as
  `ADDITIVE_WRITE = Needs("add", create="add")` in `ops.py`, a
  companion to `VERB_RUNGS`, and it serves `if_absent` too. The
  docstring of `Rung` and the glossary's ladder line gain "and appends
  to any row it may read".
- **ADR 074 rule 5:** "`overwrite=False` does not refuse a revive"
  reads "`if_absent=True` does not refuse a revive". Add: a
  precondition (`if_version`) never revives; a tombstone fails it as
  `not_found` with the trashed hint.
- **ADR 025:** an append's guard miss and arbitration loss redrive
  instead of classifying; the whole-batch redrive doctrine is
  otherwise unchanged.
- **ADR 013 pin 1:** no change. An `unchanged` write is not a material
  write, so it adds nothing; the sentence stands as written.
- **`results/kinds.py` data records** (no ADR owns the list; ADR 076
  governs words, not data): `conflict` carries `version` from every
  producer; `exists` may carry `version` and `content_hash`.

## Rebase notes for specs 167, 169, 171 and 172 (and 175, 177)

- **167 (the shell).** §5 *Redirections*: `>>` becomes one call,
  `write(path, data=<stage bytes>, append=True)`. No `read`. Delete
  "with no version precondition, so concurrent appends can lose data;
  the docstring says so". The kernel applies the keep-the-source rule
  (§6.3), so the shell need not decode. §4.1: `touch P` becomes one
  call, `write(P, content="", if_absent=True)`, where `exists` is
  success with exit 0 and no output. That removes the `stat`-then-
  `write` gap, in which a rival's new file could be truncated to empty.
  `sed -i 's/a/b/'` (the read-then-write form) passes `if_version=`
  from its `read`; a `conflict` prints `sed: <path>: Conflict` on
  stderr and exits 1, with no automatic retry. Criterion 15's `>>` on
  an absent file still holds (an append creates). Add a criterion:
  20 concurrent `cli("echo i >> /log")` calls keep 20 lines.
- **169 §b4–§b5 (the WASI host; spec 172 inherits it).** Every
  close-time write-back carries a precondition from its open:
  `if_version=` the version the open's `read` or `stat` returned, or
  `if_absent=True` when the open found no row (`O_CREAT` on a miss,
  `O_CREAT | O_EXCL`). A `conflict` at close is errno 72 `STALE`
  (§b7 already maps it); an `exists` at close is 20 `EXIST`. Note the
  one deviation from POSIX this leaves: a rival create between an
  `O_EXCL` open and the close fails at close, not at open. An
  `O_APPEND` descriptor whose writes all landed at the end flushes as
  `write(append=True)` of the bytes past the open-time size, with no
  version, so two guests appending to one log both keep their lines;
  one that seeked flushes as an `if_version` write. Criterion 8
  ("a same-bytes reinstall advances the version") becomes "reports
  `unchanged`, keeps the version, and hits the cache".
- **171 (the MCP adapter).** The `write` tool's schema gains
  `if_version` (integer), `if_absent` (boolean) and `append`
  (boolean), and `if_versions` (object) on the batch form if the tool
  exposes one; `overwrite` leaves. The tool description's replay
  line: a same-body write answers `unchanged`; an append is not
  idempotent. The read tool's rendered rows should show `version`, so
  a model can copy it into `if_version`.
- **172 (the Python runtime).** Its write-back is 169b's; the note
  above applies. The kernel memo's "one `write(if_absent=True, b"")`
  is still a version" for the WASI create path now reads: the
  create-then-write pair is two versions (1, then 2), and the second
  write carries `if_version=1`.
- **175 (integrity).** A same-body write no longer rewrites the body
  (§3). Its repair path for a body rotted under an intact hash must
  be something else (a scrub-driven rewrite that bypasses `unchanged`,
  or a delete and revive). Name it there.
- **177 (replay).** Take §10's rows into the replay table.

## Landing notes

(Filled in on landing, per task.)
