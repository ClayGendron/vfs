# 177 — Replay: the per-verb contract, recognisable replays, the request key, and the in-doubt commit

- **Status:** draft — cut 2026-10-24 from ADR 087 (proposed the same day) and the two memos it stands on. Not started. Two open `[NEEDS CLARIFICATION]` markers (§3.6 the time to live; §6 the hint on a tool whose verb has a non-idempotent form).
- **Date:** 2026-10-24
- **Owner:** Clay Gendron
- **Kind:** feature. A replay table as data in `ops.py`; two new error kinds in `results/kinds.py`; one new `ParamKind` and a `request_key` row on twelve verbs in `params.py`; the argument on the router, the session and the storage seam; a new module `storage/backends/database/replays.py`; two new tables and a schema format bump in `models/rows.py`; a replay arm in `sweep`; occupant facts on four refusals; an in-doubt classification in the mutation runner; a conformance family run on all six engine legs.
- **Depends on:** ADR 087 pins 7, 8, 10 and 15. Spec 174 for the `write` row (`unchanged` on an identical body; `if_absent`; `append` as a non-idempotent form). Spec 180 by reference (its sliced `sweep` absorbs this spec's replay arm as one more phase). Spec 181 by reference (`entry_id` on mutation rows, which lets a client compare the id this spec puts in refusal data). Spec 171 consumes §6. Nothing in flight blocks this spec; the `write` row of the conformance table waits for 174 (tasks.md task 9).
- **Decisions it implements:** ADR 087 pin 10, all of it except the first clause (the `unchanged` status on `write`, which spec 174 owns); pin 8's fault model for the one fault it leaves open (a connection lost during `COMMIT`); pin 7's atomic unit, which the request key's stored answer shares; pin 15's axis table for the store (§3.8). It answers the idempotency half of the open question "MCP 2026-07-28: long-batch execution model and serving-stack choice for serve()" (§8).
- **Research it stands on:** `../../../research/studies/2026-10-24-ostep-principles-for-vfs/06-distribution-nfs-afs.md` (§2.1 the replay table, EXECUTED; principles 1, 3, 4, 5 and 15; the experiments `experiments/s06/replay.py`, `transfer.py`, `details.py` and their `.out` files); `05-crash-consistency-and-data-integrity.md` §2.6 (identities are never reused); the memo `../../../research/2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md` §2.4 and §6 Q2 (Clay: the stored answer is a row in the mount with a short time to live, swept with the trash); `../../../research/2026-09-15-eve-vercel-agent-framework.md` §8 items 1 and 2 (eve hands every remote call a replay-stable `callId`); spec 171 §0, §1.3 and criterion 15; spec 174 §10 (the write rows). Five probes run for this spec at `ba77449` (EXECUTED; outputs in the appendix).

## Intent

A client that loses a reply sends the call again. It cannot know whether the first call ran. After this spec every mutating verb has a pinned answer to that second send. Most verbs are safe (same state, a success) or recognisable (same state, a refusal whose data says what it found). Two are neither: an `edit` whose new text contains its old text applies twice, and so will an append. The table that says which is data in `ops.py`, a test sends every row twice on every engine, and spec 171's tools quote it.

A caller that needs more passes `request_key`. The first call's `Result` is stored in the mount, in the same transaction as the change, so the answer exists if and only if the change landed. A repeat within the time to live gets the stored answer back and runs nothing. That one argument makes `edit`, `move`, an append and a 10,000-row batch safe to send twice, and it turns a connection lost during `COMMIT` from a guess into a question the server can answer.

## Terms

| Term | Meaning here |
|---|---|
| **replay** | The same call sent again, because the sender got no reply. |
| **idempotent** | A replay leaves the same state as one call and answers success. Safe to resend blindly. |
| **recognisable** | A replay leaves the same state as one call, but answers a refusal. The refusal's `data` names what the server found, so the client can tell "my first call landed" from "something else happened". |
| **key-only** | A replay without a key can change state again. Only `request_key` makes the verb safe. |
| **request key** | An optional string the caller chooses, once per logical call, and sends again unchanged on a resend. |
| **replay store** | Two tables in the mount's schema that hold, per request key, the first call's `Result`. |
| **fingerprint** | A sha256 of the call's verb and arguments. It tells "the same call again" from "a different call that reused a key". |
| **time to live (TTL)** | How long a stored answer is served. After it, the key is free again. |
| **in doubt** | The outcome of a commit whose connection dropped while it was committing. It may have landed or not. |
| **occupant** | The row found at an address a verb wanted empty (or, for a replayed `move`, the row found at the destination). |

## What the code does today (at `ba77449`)

| Fact | Evidence |
|---|---|
| Sent twice, 10 of 18 calls answer success and 8 refuse: `write(overwrite=False)`, two `edit`s, strict `mkdir`, `delete`, `restore`, `copy`, `move`. A replayed `move` refuses `not_found` with **no data**. A replayed identical `write` answers `updated` and bumps the version | EXECUTED (`replay_head.out`, appendix A; study 06 §2.1) |
| An `edit` whose `new` contains its `old` **applies twice** on replay: `foo` → `foo!` sent twice leaves `foo!!` | EXECUTED (`payload_sizes.out`, appendix B). Study 06's table recorded only the refusing case. |
| `rmedge`, `revoke` and `remove_member` answer an already-gone row with success and a `not_found` warning; `delete` answers an already-trashed path with a `not_found` failure carrying `vfs.trashed` and `vfs.deleted_at` | EXECUTED (appendix A) |
| No verb accepts a request id; MCP 2026-07-28 ships none | READ (`base.py` verb signatures; `open-questions.md`, the long-batch entry) |
| `_mutate` commits iff the `Result` succeeded, then returns it | READ (`backend.py` L1718–L1747) |
| A driver error escaping `session.commit()` is classified like any other: a disconnect becomes `vfs.unavailable.backend`, `retryable=True` | READ (`engine.py` `classify_failure`, L329–L356); EXECUTED on aiosqlite (appendix C): the commit raised `OperationalError` with `connection_invalidated=True` and classified `vfs.unavailable.backend`, retryable |
| `with_retry` redrives only retryable codes and `StaleSnapshot`; no profile lists a disconnect, so a commit disconnect is never redriven server-side | READ (`engine.py` L298–L327, the catch at L318; `dialects.py` L349, L411, L507, L535) |
| `Result.merge` drops `model_extra`; the router merges every routed write | READ (`envelope.py` L557–L587; `base.py` `_route_entry_batch`) |
| A 10,000-row `write` `Result` serializes to 1,480,046 bytes of JSON (148 B a row); `delete` by rows 204 B a row; stdlib `zlib` level 1 packs the write's to 31,791 bytes | EXECUTED (appendix B, D) |
| `BLOB_PAGE_BYTES` is 8 MiB | READ (`dialects.py` L102) |

## 0. The replay table is a pinned contract

### 0.1 The table

One row per verb that the write gate covers (`WRITE_GATED_OPS`, `ops.py`). "Replay answers" is the state after this spec and spec 174. The last column is what a caller does when a call came back in doubt (§5) and it sent no key.

| Verb | First call | Replay answers | Shape | Verify an in-doubt outcome without a key |
|---|---|---|---|---|
| `write` (a store) | `created` v1, or `updated` vN+1 | success, `unchanged`, same version, no version row (174 §3; today `updated` vN+1, EXECUTED) | idempotent | `stat`: `content_hash` equals the sha256 of the body sent |
| `write(if_absent=True)` | `created` v1 | `exists` with `version`, `content_hash` of the occupant (174 §8) | recognisable | as above |
| `write(append=True)` | `updated` | appends again (174 §10) | key-only | `read` the tail |
| `edit` | `updated` vN+1 | refusal `invalid` ("old_string not found"), now with `data.new_present` (§1.4); **or applies again** when `new` contains `old` (EXECUTED) | key-only | `read` and compare |
| `mkdir` (strict) | `created` v1 | `exists` with occupant facts (§1.2) | recognisable | `stat`: a directory |
| `mkdir(exist_ok=True)` | `created` v1 | success, `unchanged` | idempotent | — |
| `delete` | `deleted` | `not_found` with `vfs.trashed`, `vfs.deleted_at` (as today) | recognisable | `stat`: `not_found` with `vfs.trashed` |
| `restore` | `created` vN+1 | `exists` with occupant facts: the same `entry_id` (§1.2) | recognisable | `stat`: live |
| `copy` | `created` v1 | `exists`, `vfs.target` the source, occupant facts, `matches_source` (§1.2) | recognisable | `stat` the destination; compare `content_hash` with the source's |
| `move` | `created` vN+1 at the destination | `not_found` at the source, `vfs.target` the destination, `data.dest` with the occupant's `entry_id` (§1.3) | recognisable | `stat` both: source absent, destination present |
| `mkedge` | `created` | success, `updated` | idempotent | `graph(source, method="outbound", edge_types=[t], depth=1)` |
| `rmedge` | `deleted` | success; warning `not_found` with `edge_type`, `vfs.target` | idempotent | the same `graph` call shows no edge |
| `grant` | success, `grants=` | success, `grants=` | idempotent | `grants(path)` |
| `revoke` | success, `grants=` | success; warning `not_found` with `principal_id` | idempotent | `grants(path)` |
| `posture` | success, `grants=`, `relabel=` | success; the labels beneath are rewritten to the same value again (EXECUTED: 6 rows, then 6 again) | idempotent | `grants(path)`: the everyone row |
| `sweep` | the purged rows | success, nothing to purge | idempotent | — |
| `add_member` | `members=` | success, `members=` | idempotent | — |
| `remove_member` | `members=` | success; warning `not_found` | idempotent | — |

Rules the table follows:

- The table shows some forms on their own lines, for reading. `REPLAY` (§0.2) holds one row per verb; its `replay` text names each form.
- A verb's **shape** is its default form's shape, with one override: if any form it accepts can change state twice, the verb is key-only. A form that only refuses on replay (`if_absent=True`, which the caller chose so as to be refused) does not lower it; a form that applies twice does, because an automatic resend must never apply twice. So `mkdir` is recognisable (its default form refuses), and `write` is idempotent until 174's `append=True` becomes one of its forms, when it becomes key-only. The other forms are named in the row text.
- "Same state" ignores counters that no reader keys on. A `grant` replay bumps `vfs_meta.grant_revision` and re-stamps `vfs_principal_revisions` (READ, `backend.py` `_grant_write`): the rights are unchanged, the caches revalidate. The replay contract says so and does not pin the counter.
- The edge, grant and membership rows the table cites as warnings are today's behaviour, kept (§1.5).

### 0.2 Where it lives

The table is data in `src/vfs/ops.py`, beside the op classes it describes, so the MCP descriptions, the annotations and the conformance test all read one source:

```python
ReplayShape = Literal["idempotent", "recognisable", "key_only"]


class Replay(NamedTuple):
    """What one verb answers when the same call is sent twice."""

    first: str
    replay: str
    shape: ReplayShape
    verify: str


REPLAY: Final[dict[Op, Replay]] = {...}  # one row per WRITE_GATED_OPS verb, text as §0.1

KEYED_OPS: Final[frozenset[Op]] = frozenset(
    {"write", "edit", "mkdir", "delete", "restore", "copy", "move", "mkedge", "rmedge", "grant", "revoke", "posture"},
)
"""Verbs that accept ``request_key``: every write-gated verb an agent or an operator replays."""

IDEMPOTENT_OPS: Final[frozenset[Op]] = frozenset(op for op, row in REPLAY.items() if row.shape == "idempotent")
```

- `sweep`, `add_member` and `remove_member` take no key. They are idempotent by shape, developer-plane, and `sweep`'s answer can be large and is worthless to store.
- A drift test pins `REPLAY.keys() == WRITE_GATED_OPS` and `KEYED_OPS <= WRITE_GATED_OPS`. A verb added to `ops.py` without a replay row fails the test.

### 0.3 The test

A new conformance family, `tests/support/replay_contract.py` (`ReplayContract`), mixed into the six storage legs in `tests/storage/test_conformance.py` (memory, SQLite file, Postgres, MariaDB, SQL Server, Oracle). It sends each row's call twice to the storage seam and asserts, per row: the second answer's verdict, kind, severity and the `data` keys the row names; the state after (the row, its version, the count of its version rows, the edge or grant row) equals the state after the first call. The membership rows run in `GrantsContract`'s fixture world. Each row names its verb, so a failure reads as "the `move` row broke on Oracle".

## 1. Recognisable replays

### 1.1 The occupant facts

A refusal that found a row where it wanted none now says which row. One helper in `storage/backends/database/descent.py`:

```python
OCCUPANT_FIELDS: Final = ("entry_id", "kind", "version", "content_hash")


def occupant_facts(row: Mapping[str, Any], shown: frozenset[str]) -> dict[str, object]:
    """The facts a refusal may state about *row*: those of OCCUPANT_FIELDS the caller's view shows."""
```

- The keys are flat and unprefixed, matching the kinds docstring ("producer keys are unprefixed") and spec 174's `if_absent` record (`{"version", "content_hash"}`), which this helper also serves.
- **The mask.** `shown` is what `stat` would show this caller on that row. The system actor (`WriteGate.whole`) sees all four. A caller whose `Visibility.reads(row)` holds sees all four (spec 181 §3.4 puts `entry_id` at the `read` rung). A caller who only lists the row sees `kind` alone. The backend builds the mask once per call from the `WriteGate` it already resolved and hands it to the ladder as a `shown: Callable[[Mapping[str, Any]], frozenset[str]]` beside the existing `gate` callable. So the facts never widen what a caller sees (pin 15's protection axis).
- The rows the ladders read must carry the columns the mask judges by. `SNAPSHOT_COLUMNS` (`serialized.py` L72), restore's `_TOMBSTONE_COLUMNS` and the row `mkdir_rows`' plan holds each gain whichever of `content_hash`, `owner_id` and `everyone_level` they lack. That widens a row read by under 100 bytes and adds no statement.

### 1.2 `copy`, `restore` and strict `mkdir`: `exists` names its occupant

| Site | Today | After |
|---|---|---|
| `copy` onto an occupied destination (`topology.py` `_occupied`, L258) | `exists`, `vfs.target` = source | plus `occupant_facts(occupant)`, plus `matches_source: bool` when both rows are files and the mask shows `content_hash` on both |
| `restore` onto a live row (`trash.py` `_RestoreLadder.verdict`, L247) | `exists`, no data | plus `occupant_facts(row)`: on a replay this is the row the first restore revived, same `entry_id` |
| strict `mkdir` onto a live row (`writes.py` `mkdir_rows`, L212) | `exists`, no data | plus `occupant_facts(row)` from the plan's row |

Every site already holds the occupant's row when it refuses. No statement is added.

### 1.3 `move`: a missed source names what sits at the destination

Today a pair whose source is absent refuses `not_found` at the source with no data (`topology.py` L162–L163). After this spec:

- The pair loop records each missed pair. After the loop, and only when some pair missed, one probe reads the destinations of the missed pairs: `SELECT entry_id, path, kind, version, content_hash, owner_id, everyone_level, deleted_at FROM vfs_entries WHERE path IN (...)`, chunked by `membership_budget` through `chunked()` and the `membership()` helper. A 10,000-pair replay costs at most `ceil(10,000 / membership_budget)` probe statements (11 on Oracle's floor), never one per pair. The success path issues none.
- When the destination holds a live row, the source's `not_found` gains `vfs.target` (the destination) and `dest: occupant_facts(row)`. When it holds a tombstone or nothing, the refusal is unchanged.
- The error's locus stays the source, because the source is what is missing. `dest` is a nested record so no key in `data` is mistaken for a fact about the locus.
- A move keeps the row's `entry_id` (READ, `topology.py` `_execute_move` updates the row in place; study 05 §2.6: ids are never reused). So a replay finds the same `entry_id` at the destination that the first call moved there. A client compares it with the id it holds: from the first call's row once spec 181 puts `entry_id` on mutation rows, or from a `stat` before the move.
- The server states facts, never the inference "already moved". A rival could have deleted the source and created the destination. The id comparison is the client's proof; the request key (§2) is the server's.

### 1.4 `edit`: the refusal says whether the new text is there

- `apply_edits` (`storage/replace.py`) reports the index of the edit that failed.
- When that edit failed as "old_string not found", its `new` is not empty, and `new` occurs in the body that edit saw, the `invalid` refusal gains `data.new_present = True`. The body is already in hand; the check is one `str.find`.
- This makes the common replay recognisable. It cannot catch the case where `new` contains `old`: there the replay matches and applies again (EXECUTED, `foo!!`). That is why `edit` is key-only.

### 1.5 One rule for removals of what is already gone

The inconsistency study 06 found (principle 3): `rmedge` and `revoke` answer "already gone" with success and a warning; `delete` answers it with a failure. The rule this spec states, which changes no landed contract:

> **A removal of a relation row is a set operation; a removal of a
> namespace row is a POSIX operation.** Edges, grants and memberships
> are rows of a set: removing an absent member leaves the same set, so
> it succeeds with a `not_found` warning. A path is a name a caller
> typed: removing one that is not there is a refusal, as `rm` is, and
> the tombstone makes the replay recognisable (`vfs.trashed`,
> `vfs.deleted_at`).

The alternative, `delete` of an already-trashed path answering success with a warning (`rm -f`), was considered and not taken. It would change a landed contract (ADR 074's refusal at a tombstone), make spec 167's `rm` map a warning back to exit 1 by hand, and buy nothing the trashed hint does not already give.

## 2. `request_key`: the argument

### 2.1 Its type

A new `ParamKind` in `params.py`, `"token"`: an opaque, caller-chosen string of 1 to 255 characters, each in printable ASCII without space (`!` to `~`, 0x21–0x7E).

- Why ASCII: a key is compared byte for byte after a digest. Unicode would let two keys that look the same (NFC and NFD forms) differ. UUIDs, ULIDs, eve's `callId` and an idempotency header all fit.
- `_check_value` gains the `token` branch; a violation is `invalid` naming `request_key`, like every other parameter.
- `MAX_REQUEST_KEY_LENGTH: Final = 255` in `params.py`.

```python
_REQUEST_KEY: Final = ParamSpec(
    "request_key",
    "token",
    doc="the caller's id for this call; a resend with the same key gets the first call's answer back",
)
```

`_REQUEST_KEY` joins `PARAMS` for every verb in `KEYED_OPS`, before `_AUTHORITY`.

### 2.2 The router and the session

- Each of the twelve verbs in `base.py` gains `request_key: str | None = None`, keyword-only, and passes it to `_gate_params`. The signature drift test (`test_params.py`) holds the table and the signatures together.
- The routing helpers carry it in `kwargs` to `_dispatch_entry`: `_route_single`, `_dispatch_grouped_observations`, `_route_entry_batch`, `_route_two_path`, `_route_edge_batch`, `_route_grant`. They pass it **only when it is not `None`**, so a keyless call reaches storage exactly as today.
- `session.py`'s twelve methods forward it.
- A batch that spans mounts dispatches the same key to each mount. Each mount stores its own slice of the answer under its own fingerprint (§3.3). A replay re-routes the same way, and each mount answers its own slice. This matches pin 7: a cross-mount batch is atomic per mount, so a replay where one mount landed and one did not gets the stored slice from the first and runs the second.

### 2.3 Which mounts honour it

- A new trait key `replay` with one value, `keyed`, in `protocol.py`'s `TraitKey` and `TRAIT_VALUES`. `DatabaseStorage` declares it.
- `MountMeta` gains `keyed: bool`, snapshotted at bind from `storage.traits().get("replay") == "keyed"` (a storage without `SupportsTraits` is not keyed). It is replaced whole with the meta, like `declared_caps`.
- `_gate_entry` gains `keyed: bool = False`. A keyed call to a mount whose meta is not keyed refuses `unsupported` at the capability step, with the detail "this storage keeps no replay store; resend without request_key". The capability gate is the only producer of `unsupported` (the kinds docstring's producer-exclusivity rule), and this is a capability.
- The storage protocol's mutation methods and `grant`, `revoke`, `posture` gain `request_key: str | None = None`. A storage that does not declare the trait never receives the argument, so its methods need not change.

## 3. The replay store

### 3.1 The tables (`models/rows.py`)

```python
# One row per request key answered: whose key, which call, and when it lapses.
# The answer itself lives in pages below, so this row stays narrow.
replays = Table(
    "vfs_replays",
    metadata,
    Column("request_id", String(64), primary_key=True),
    Column("op", String(16), nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("actor_id", _string(MAX_PRINCIPAL_ID_LENGTH), nullable=False),
    Column("created_at", _timestamp(), nullable=False),
    Column("expires_at", _timestamp(), nullable=False),
    Index("ix_vfs_replays_expires_at", "expires_at"),
    schema=schema,
)

# The stored answer: a zlib-packed Result, cut into pages of at most one blob page.
replay_pages = Table(
    "vfs_replay_pages",
    metadata,
    Column("request_id", String(64), primary_key=True),
    Column("page", Integer, primary_key=True, autoincrement=False),
    Column("expires_at", _timestamp(), nullable=False),
    Column("payload", _body_bytes(), nullable=False),
    Index("ix_vfs_replay_pages_expires_at", "expires_at"),
    schema=schema,
)
```

- `request_id` is a sha256 hex digest (§3.2), the same width as every `content_hash` column. It fits every engine's key cap.
- `expires_at` sits on both tables so `sweep` deletes each by its own index, with no subquery and no join (§4).
- `actor_id` is the actor's `sub`, for an operator who looks at the table. Nothing reads it to decide anything.
- `payload` uses `_body_bytes()`: LONGBLOB on the mysql family, VARBINARY(max) on SQL Server, BLOB on Oracle and SQLite, BYTEA on Postgres.
- `VFSTables` gains `replays` and `replay_pages`. The rows drift test gains both tables; no domain model mirrors them.
- **The schema format version bumps by one.** First touch creates tables only on a fresh mount (`engine.py` `_verify_or_provision`), so an existing mount would lack the new tables; the bump makes first touch refuse it loudly as `vfs.unavailable.schema` (ADR 020 pin 3). Specs 176 and 180 bump it too. Each of 176, 177 and 180 takes the next value at landing, read from `rows.py` then, not a number fixed here.

### 3.2 Whose key: the request id

A key is scoped to the caller who sent it. Otherwise caller B, by guessing or by accident, could be answered with caller A's stored `Result`.

```python
request_id = sha256(frame(
    b"vfs.replay.1",
    actor.kind, actor.sub,
    *[f"{p.kind}:{p.sub}" for p in sorted(subjects, key=lambda p: (p.kind, p.sub))],
    narrowing.value,
    request_key,
)).hexdigest()
```

- `frame` writes each field as its UTF-8 length (4 bytes, big-endian) then its bytes, so no two field lists hash alike.
- Provenance and `source_identity` are left out: the same caller proven two ways is the same caller.
- **The anonymous caller may not use a key.** Every anonymous caller is the same principal, so their keys would share one space. A keyed call under `Authority.anonymous()` refuses `invalid` ("a request key needs a named caller"). The system actor may: it is one trust tier (in process, ADR 068), and an ETL job that reuses its own keys is replaying its own calls. A direct storage call that names no authority acts as the system actor (`backend.py` `_named`), so it may use a key too.

### 3.3 Which call: the fingerprint

```python
fingerprint = sha256(frame(b"vfs.call.1", op, *canonical(arguments))).hexdigest()
```

`canonical` walks the storage call's keyword arguments sorted by name, `authority` and `request_key` excluded, and frames each value by type:

| Value | Framed as |
|---|---|
| `Path`, `str`, `bool`, `int`, `None` | a type tag, then the text |
| `Entry` | path, kind, source (`content` or `data`), `content_hash` — the body is represented by its hash, which `_authored_entry` already computed |
| `EditOperation` | `old`, `new`, `replace_all` |
| `ResolvedPair` | `src`, `dest` |
| `Edge` | source, target, edge type, weight, distance |
| `Observation` (an address) | its path only |
| a list | its length, then each item |

- It is computed in the storage method, over the arguments that storage received. So each mount of a cross-mount batch fingerprints its own slice.
- For a 10,000-entry write it frames 10,000 paths and hashes: about 1 MB through one `hashlib.sha256` object, on the loop, no thread hop.
- A golden test pins the fingerprint of one fixed call to a fixed hex string, so the encoding cannot drift between processes or versions without a test failing.

### 3.4 The flow, inside the mutation runner

`_mutate` (`backend.py` L1718) gains `request: ReplayRequest | None`. Every mutating method builds it with `replay_request(op, authority, request_key, arguments)` and passes it through `_execute_write`, `_execute_topology` and `_grant_write`. Inside `attempt()`, on the writer session, **before** `fn`:

1. **Look up.** One statement: `SELECT h.op, h.fingerprint, h.created_at, h.expires_at, p.page, p.payload FROM vfs_replays h LEFT JOIN vfs_replay_pages p ON p.request_id = h.request_id WHERE h.request_id = :id ORDER BY p.page`.
2. **A live row answers.** If the row exists and `expires_at > now`:
   - a different `op` or `fingerprint` refuses `invalid` ("this request key already answered a different call"), with no other data. The stored call is never described.
   - otherwise the pages are joined, unpacked (§3.5) and returned with one added entry (§3.6). `fn` never runs. Nothing is written. The session rolls back on exit.
3. **An expired row is replaced.** Two statements, `DELETE FROM vfs_replay_pages WHERE request_id = :id` and `DELETE FROM vfs_replays WHERE request_id = :id`; then go on as a miss.
4. **Claim.** One `INSERT` of the head row (`op`, `fingerprint`, `actor_id`, `created_at = now`, `expires_at = now + ttl`). A unique violation here means a rival with the same key committed, or is committing, the same call: the `IntegrityError` is raised as `StaleSnapshot`, so `with_retry` redrives from step 1, which then finds the rival's answer.
5. **Run** `fn(session)`.
6. **Record** only if the `Result` succeeded: pack it, cut it into pages, insert the pages, then commit with the change. A failed `Result` is not stored: the session rolls back, the claim with it, and a resend runs again, which is right because nothing landed.

Why the claim comes first:

- **Rivals.** Two sends of one key can overlap (a client times out while the first is still running: study 06 principle 15). On Postgres, SQL Server, Oracle and MariaDB an `INSERT` of a key held by an uncommitted row waits for that transaction, then fails if it committed. So the second send waits and then gets the stored answer. It never runs the call a second time. On SQLite `BEGIN IMMEDIATE` already serializes writers, so the second send's look-up sees the first's commit. A claim at the end instead would let a failing duplicate (a second `move`, refused `not_found`) return its refusal without ever reaching the conflict.
- **Isolation.** Postgres and MariaDB run op writes at `REPEATABLE READ` (`dialects.py` L436, L500). A claim that meets a row committed after the snapshot raises a unique violation or a serialization failure; the first becomes `StaleSnapshot`, the second is already retryable. Both redrive into a fresh snapshot.
- **Lock order.** The claim locks one key in `vfs_replays` before `fn` takes the serialization point or any entry row. Two different keys never conflict on it. Two sends of one key: the second waits on the claim alone and holds nothing `fn` needs, so no cycle forms.
- **The look-up comes before the gate.** `fn` starts with the rights gate, and for the grant verbs with `bump_revision`, a write. A hit must issue no mutation statement, so the look-up precedes them. The stored answer was judged under the rights in force when it ran, and only the same caller (§3.2) gets it. A resend answers what happened, not what would happen now. The router's own gates (permission maps, a read-only mount, a busy bind site) still run on the resend, before storage.

Statement cost (non-control statements, counted in criteria 7–9):

| Call | Added statements |
|---|---|
| no key | 0 |
| keyed, miss, answer fits one page | 3: look-up, claim, one page |
| each further page | +1 |
| keyed, expired row | +2 deletes before the claim |
| keyed, hit | 1: the look-up; `fn` runs nothing |

### 3.5 The stored answer: whole, packed, paged

- **What is stored:** the whole `Result`, as `result.model_dump_json(exclude_none=True)`, the same JSON `to_payload` builds (`envelope.py` L723), extras included (`grants`, `relabel`, `members`). It never carries bytes: no mutation row populates `data`.
- **Packed** with stdlib `zlib` at level 1. EXECUTED: a 10,000-row write answer, 1,480,046 bytes, packs to 31,791 (47×) on synthetic paths. Real paths and spec 175's per-row `content_hash` will pack less well, perhaps to a third of raw for the hashes alone; one 8 MiB page still holds a 10,000-row answer many times over.
- **Paged:** the packed bytes are cut with `byte_chunked` into pages of at most `min(BLOB_PAGE_BYTES, value_cap)` bytes, as the body writes are (`writes.py` L405–L407), and each page is one `INSERT`. No statement grows with the batch; no ceiling is declared on the answer's size; a larger answer is more pages.
- **Off the loop:** when the JSON is at least `REPLAY_OFFLOAD_BYTES = 100_000` bytes (the break-even ADR 087 pin 9 measured for the hash hop), the dump and the compression run through `call_offloaded` on the backend's pool, as do the decompression and the parse on a hit. A test counts offload calls, never time.
- **Unpacked** with `Result.model_validate_json(..., strict=False)` after `zlib.decompress`. A page set that does not decode is an out-of-band edit (pin 8's fault model): the call refuses `vfs.internal` ("the stored answer for this request key is unreadable"). It is never treated as a miss, because running the call again could apply it twice.
- **Rejected: a digest plus the rows' identities.** It is smaller, but it cannot reproduce the answer. The hit would have to re-read rows, under rights that may have changed, and the client would get a different `Result` from the first. Clay's answer (memo §6 Q2) stores "the first Result".

### 3.6 What the caller sees

- A hit returns the stored `Result` exactly, plus **one** entry of a new kind at `info` severity:

  ```python
  replayed = "vfs.replayed"  # the stored answer of the first call with this request key; nothing ran again
  ```

  `KindContract("Replayed", RetryClass.never, "This is the stored answer of the first call with this request_key; nothing ran again.", "None — source carries the mount")`, with `data = {"vfs.first_at": <created_at ISO>, "vfs.expires_at": <ISO>}`.
- Why an error entry and not a `Result` field: `Result.merge` keeps errors and drops extras, and every routed write passes through a merge. An `info` entry never fails the envelope (`Severity` docstring), so `isError` stays false on the wire. It is the vocabulary's first kind used only at `info`; the `KIND_CONTRACTS` row and the docstring say so, and that only the replay store produces it.
- A miss returns the `Result` the call produced, unmarked.
- **`posture`.** Its first transaction (the posture row) carries the claim and the record; `_settled` then runs the relabel chunks in their own transactions (`backend.py` L1603). On a hit, `posture` still calls `_settled`, so a resend also drives any relabel the first call left pending to its end, which is what a resumable verb should do. `_settled` keeps the stored answer's `errors` (today it drops them), so the `vfs.replayed` entry survives.
- **The time to live.** `DatabaseStorage` and `InMemoryStorage` gain `replay_hours: int = 24`, validated `>= 0`. Zero stores answers that lapse at once: the claim still makes overlapping sends wait for each other, and tests use it to reach expiry without a clock.

  `[NEEDS CLARIFICATION: ADR 087 leaves the TTL pending. Lean: 24 hours. A client retry after a lost reply comes within seconds; a host restart within minutes; a durable workflow (eve's step replay) may resume hours later, after a crash. A day covers all three, and it is the window the common payment-API idempotency keys use (general knowledge, not studied here). Cost: an ETL job keying 100 batches of 10,000 rows an hour holds about 2,400 answers, under 100 MB packed at the measured ratio before content hashes. Alternatives: 1 hour (the retry window only) or 7 days (a long durable resume).]`

### 3.7 The module

`src/vfs/storage/backends/database/replays.py`, laid out per the house order:

- `ReplayRequest(NamedTuple)`: `request_id`, `op`, `fingerprint`, `actor_id`, `ttl`.
- `replay_request(op, authority, request_key, arguments) -> ReplayRequest | ResultError | None`: `None` without a key; the `invalid` refusal for the anonymous caller.
- `answered(session, tables, request, now) -> Result | ResultError | None`: steps 1–3.
- `claim(session, tables, request, now) -> None`: step 4, raising `StaleSnapshot` on a unique violation.
- `record(session, tables, request, result, *, page_budget, executor) -> None`: step 6.
- `reclaim_expired(session, tables, now) -> int`: §4.
- Internal helpers last: `_frame`, `_canonical`, `_pack`, `_unpack`.

### 3.8 The options, on the standing axes (pin 15)

| Axis | **A. Row in the mount, claim first, whole answer packed in pages (chosen)** | B. Row in the mount, digest plus row identities | C. Memory of the serve process | D. One store for the whole router |
|---|---|---|---|---|
| agent latency | +3 statements on a keyed miss, 1 on a hit, 0 without a key | the same on a miss; a hit must re-read rows | 0 | +3, but in a second transaction |
| ETL throughput | +3 statements for a 10,000-row batch (one page) | the same | 0 | the same |
| boundedness | every statement one key or one page | the same | unbounded memory, no sweep | the same as A |
| correctness under rivals | the claim makes the second send wait, then answer | the same | two processes do not see each other | the same as A |
| atomic unit | the answer commits with the change: it exists iff the change landed | the same | not atomic with the commit | atomic with one mount only; a cross-mount batch tears the answer from the change |
| dialect reach | plain tables and one `LEFT JOIN`, every engine | the same | n/a | the same |
| protection | scoped to the caller; served only to the same caller | the same | the same | the same |
| overhead above the engine | one JSON dump and one `zlib` pass per keyed miss | smaller | none | the same as A |
| survives a restart | yes | yes | **no** (Clay's answer rules it out) | yes |

## 4. `sweep` reclaims the replay store

- The retention arm (`sweep` at the trash view, `trash.py` `sweep_rows`, L384 onward) gains one step after the orphan reclaim: `reclaim_expired(session, tables, now)`, which issues `DELETE FROM vfs_replay_pages WHERE expires_at < :now` and `DELETE FROM vfs_replays WHERE expires_at < :now`. Two statements, one bind each, whatever the number of rows.
- The answer gains an extra, `replays_swept: int`, the head rows deleted (the second statement's `rowcount`). `sweep` routes through `_route_single` and `_dispatch_entry`, which keep extras (`Result.with_mount`); no merge drops it.
- The purge arm (a `sweep` at any other address) does not touch the replay store. A stored answer names paths, but it is an answer, not a row of the tree.
- ADR 027's "only sweep destroys" governs namespace rows. A replay row is a cached answer. Step 3 of §3.4 replaces an expired one in place, which is the only destruction outside `sweep`, and it touches only the caller's own lapsed key.
- **With spec 180.** 180 slices the retention arm into phases (`roots`, `content`, `blobs`, `versions`) behind a `SweepMark`. The replay arm becomes a fifth phase, `replays`: a window `SELECT request_id FROM vfs_replays WHERE expires_at < :now ORDER BY expires_at LIMIT :slice`, then the two deletes by `request_id IN (:window)` chunked by `membership_budget`. The phase needs no position: a deleted row is gone, so each window starts at the oldest that remains. 180's garbage gauge gains the replay rows and their page bytes. Until 180 lands, the arm is the two whole statements above, the same unsliced shape the retention arm has today.

## 5. The in-doubt commit

### 5.1 Detection

In `_mutate`'s `attempt()`, the commit moves inside a guard:

```python
if result.success:
    try:
        await seam("mutate:before-commit")
        await session.commit()
        await seam("mutate:after-commit")
    except DBAPIError as exc:
        if self._host.is_disconnect(exc):
            raise CommitInDoubt(op) from exc
        raise
```

- `EngineHost.is_disconnect(exc) -> bool` is extracted from `classify_failure` (`engine.py` L338–L347) so one owner holds the test: `exc.connection_invalidated`, or `dialect.is_disconnect` on the driver origin. `classify_failure` calls it too.
- `CommitInDoubt(Exception)` lives in `dialects.py` beside `StaleSnapshot`. `with_retry` catches only `DBAPIError` and `StaleSnapshot` (L318), so it never redrives an in-doubt commit. That is required: a redrive of a commit that landed is the double apply this spec exists to prevent.
- A disconnect raised **before** the commit call (inside `fn`) is unchanged: nothing was sent to commit, so the transaction is gone, and `vfs.unavailable.backend` with `retryable=True` is the truth.
- A non-disconnect error at commit (a deferred constraint, a serialization failure at `COMMIT` on Postgres) is unchanged: the engine answered, so the outcome is known.
- The two seams are the fault-injection points the tests use: a handler that raises `DBAPIError(None, None, Exception("lost"), connection_invalidated=True)` after the real commit simulates "landed, reply lost"; before it, "never landed". Seams are no-ops in production (`seams.py`).
- EXECUTED (appendix C): on aiosqlite a connection closed before `COMMIT` raises `OperationalError` with `connection_invalidated = True`. The detection rule sees it. That case did not land (0 rows), and the rule still answers in doubt: the server cannot tell, so it says so.

### 5.2 Classification

A new child kind under `unavailable`:

```python
in_doubt = "vfs.unavailable.in_doubt"  # the connection dropped during COMMIT; the change may or may not have landed
```

`KindContract("Outcome unknown", RetryClass.refresh, "The connection dropped while the change was committing, so it may or may not have landed. Check with stat before retrying, or resend with the same request_key, which returns the stored answer if it landed.", "None — source carries the mount")`.

- `RetryClass.refresh` ("re-read state first, then retry") is the class that says verify first. A client that predates the kind degrades it to `vfs.unavailable` by `kind_family`, which is today's behaviour, never worse.
- `retryable` is `True` only when the call carried a request key. With a key a blind resend is safe: §3's claim and record committed with the change, so the resend finds the stored answer if it landed and runs the call if it did not. Without a key, `retryable` is `False`, and the replay table's last column says what to `stat`.
- `_mutate` catches `CommitInDoubt` beside `StaleSnapshot` and returns `Result(ops=(op,), errors=[classified(ErrorKind.in_doubt, detail=..., retryable=request is not None)])`.
- `posture`'s relabel chunks pass through the same runner. A chunk in doubt is harmless (its durable mark resumes it), and `posture` is idempotent, so the same answer serves.

### 5.3 What the server does not do

It does not reconnect and resolve a keyed in-doubt call by itself. After a drop, the first transaction may still be open on the engine: its claim row stays locked until the engine notices the dead connection, which on Postgres with default settings can take as long as the TCP keepalive. A server-side probe would hide that wait inside the call. The client, told `in_doubt` and `retryable`, chooses when to resend; the resend's claim then waits on the engine's own resolution, which is the honest answer. The wire backend's `TransportError` mid mutation (`base.py` `_call_storage`) has the same doubt; it waits for the wire backend's own spec.

## 6. `idempotentHint` and the MCP surface (for spec 171)

- **The rule.** A tool earns `idempotentHint: true` iff its verb's replay shape is `idempotent`: `op in IDEMPOTENT_OPS`. Derived, never hand-set, like `readOnlyHint` (171 §1.3).
- **Why the stricter reading.** MCP defines the hint as "no additional effect on its environment". By that text a refused replay (`move`, `copy`, `delete`) also earns it. But a host reads the hint to decide whether to resend on its own, and an automatic resend that comes back refused, for work that landed, misleads the model. So the hint means here: resend blindly, and the answer is still a success.
- **What it gives, by the table:** `write`, `mkedge`, `rmedge`, `grant`, `revoke` among the agent tools (`posture`, `sweep` and the membership verbs are not served). `mkdir` does not, because its default form refuses on replay. `write` keeps it until a form that applies twice joins it: 174's `append=True` is an increment.

  `[NEEDS CLARIFICATION: the hint is per tool, not per call. For a tool whose verb has a non-idempotent form (strict mkdir; write once 174's append is on its input schema), withhold the hint (lean: the shape rule of §0.1, so a host never auto-resends an append), or set it on MCP's effects-only reading, under which strict mkdir's replay changes nothing? If withheld from write, 171 could serve append as its own tool so write keeps the hint.]`
- **`request_key` on the wire.** 171 projects input schemas from `PARAMS` (§1.1). The `token` kind projects as `{"type": "string", "minLength": 1, "maxLength": 255, "pattern": "^[!-~]+$"}`. The key appears on the eleven agent tools in `KEYED_OPS` (all but `posture`).
- **Descriptions.** Each mutating tool's replay line (171 §1.3) is `REPLAY[op].replay` plus, for a recognisable or key-only verb, one sentence: "To make a resend safe, pass request_key and send it again unchanged."
- **Reading a host's call id.** A host with a replay-stable id (eve's `callId`) passes it as `request_key`. Reading it from MCP `_meta` automatically is a later adapter rule, out of scope here.

## 7. Boundedness at 10,000 rows on the tightest engine

| Statement | Binds | Grows with N? | Chunked by |
|---|---|---|---|
| look-up (head `LEFT JOIN` pages, one key) | 1 | no | — |
| expired replace (2 deletes by key) | 1 each | no | — |
| claim (one head row) | 6 | no | — |
| page insert | 3 per page | pages grow with the packed answer, one statement each | `byte_chunked` at `min(BLOB_PAGE_BYTES, value_cap)` |
| `move` destination probe (failure path) | ≤ budget | no | `chunked(..., membership_budget)` and `membership()` |
| sweep's replay arm (2 deletes by `expires_at`) | 1 each | rows per statement, not binds; 180 slices it | 180's `LIMIT :slice` window, then `membership_budget` |
| fingerprint | none (CPU) | O(N) hashing, about 1 MB for 10,000 entries | — |

The existing per-pair miss probe in `transfer_rows` (one `classify_misses` per missed pair) is unchanged here; its cost belongs to spec 179's access-path family.

## 8. The open question this spec answers

`context/open-questions.md`, "MCP 2026-07-28: long-batch execution model and serving-stack choice for serve()". The revision makes a broken stream a cancellation, the client re-issues fresh, and MCP has no idempotency mechanism. This spec is the idempotency half of the answer:

- Every verb's resend is pinned and quoted on the wire (§0, §6).
- A resent 10,000-file `write` with its key is a no-op that returns the first answer (criterion 9).
- A resend that arrives while the first is still running waits and gets the first answer (criterion 11).
- A commit whose connection dropped is reported as in doubt, and the key resolves it (§5).

The tasks half (a pollable handle for a batch that outlives a client timeout, study 06 principle 15) stays open. On landing, the entry's status line records that the idempotency half is resolved by this spec.

## Scope

In: §0–§7. The replay table and its drift test; the conformance family on six legs; the occupant facts on four refusals; `edit`'s `new_present`; the removal rule; `request_key` on twelve verbs; the trait and the capability gate; the replay store, its tables and the format bump; the `vfs.replayed` and `vfs.unavailable.in_doubt` kinds; the in-doubt detection; the `sweep` arm; the `replay_hours` setting.

Out: the `unchanged` status and `if_absent` / `append` (174); the sliced sweep and the garbage gauge (180, which absorbs §4's arm); `entry_id` on observations (181); spec 171's code (it takes §6 as a rebase); a key for a whole `cli` line (a later design: the line runs many verbs); reading a host's call id from `_meta`; server-side resolution of an in-doubt commit (§5.3); a wire backend's in-doubt `TransportError`; the MCP tasks extension (the other half of the open question, §8).

## Acceptance criteria

Counts and states, never clocks. "Mutation statements" means `INSERT`, `UPDATE`, `DELETE` and `MERGE`, counted with a `before_cursor_execute` listener as `tests/storage/database/test_writes.py` does.

1. **The table is complete.** `REPLAY.keys() == WRITE_GATED_OPS`; `KEYED_OPS <= WRITE_GATED_OPS`; `IDEMPOTENT_OPS` equals the rows whose shape is `idempotent`. Adding an op without a row fails.
2. **The replay table test passes on every engine.** Each row of `REPLAY` (with 174's `write` rows once 174 has landed) is sent twice on the memory, SQLite-file, Postgres, MariaDB, SQL Server and Oracle legs. Each second answer matches its row's verdict, kind, severity and named `data` keys, and the state after equals the state after the first call (row, version, version-row count, edge or grant row).
3. **A replayed `move` names its destination.** After `move(/y, /z)`, the replay refuses `not_found` at `/y` with `data["vfs.target"] == "/z"` and `data["dest"]["entry_id"]` equal to the `entry_id` the row had at `/y` before the first move (read from `stat` once 181 lands, else from the entries table). A move whose destination is empty carries no `dest`. A 10,000-pair replay issues at most `ceil(10,000 / membership_budget)` destination-probe statements; a successful move issues none (counted).
4. **The other occupants.** A replayed `restore` refuses `exists` with the same `entry_id` the first restore revived; a replayed strict `mkdir` refuses `exists` with `kind == "directory"`; a replayed file `copy` refuses `exists` with `matches_source is True`, and a copy onto a different file has `matches_source is False`. A caller who only lists the occupant gets `data` with `kind` and none of `entry_id`, `version`, `content_hash` (counted keys). None of these sites adds a statement (counted against the same call before the change).
5. **`edit` says what it found.** `edit(f, "world", "there")` sent twice: the second refuses `invalid` with `data["new_present"] is True`. An edit whose `new` is absent has no `new_present`.
6. **The removal rule.** An already-gone edge, grant and membership answer success with one `not_found` warning each; an already-trashed path answers a `not_found` failure with `vfs.trashed`. One test names the rule.
7. **A repeated key runs nothing.** For each verb in `KEYED_OPS`, a second call with the same key within the TTL returns a `Result` whose observations equal the first's and whose errors equal the first's plus exactly one `vfs.replayed` `info` entry, with **zero** mutation statements on every leg. On the SQLite leg it issues exactly one non-control statement, the look-up. For `posture`, zero mutation statements when no relabel is pending.
8. **A keyless call costs what it cost.** The non-control statement counts pinned in `test_writes.py` (6 for a one-file create, 7 for a one-edit `edit`) hold unchanged for a keyless call. A keyed miss of the one-file create counts exactly 9: the 6, plus look-up, claim and one page.
9. **A 10,000-row batch replayed by key is a no-op.** A keyed write of 10,000 entries, sent again with the same key: zero mutation statements, every version unchanged, the version-row count unchanged, and the 10,000 returned observations equal the first call's. The stored answer is one page (counted rows in `vfs_replay_pages`). Marked `slow`.
10. **Keys do not cross.** The same key with different arguments, and the same key on a different verb, refuse `invalid` and change nothing. Two principals sending the same key each run their own call and each get their own answer. A keyed call as anonymous refuses `invalid`. The system actor's keyed call stores.
11. **Overlapping sends run once.** Two sends of one key overlap: a seam inside the first call's transaction starts the second as a task, and the test awaits it after the first returns. The change happens once (version +1 once, one version row), and both callers get the same observations, the second with `vfs.replayed`. On the four server legs the second waits on the claim; on the SQLite legs it queues behind `BEGIN IMMEDIATE` and then finds the answer.
12. **Expiry.** With `replay_hours=0`, a second keyed call runs again and its head row's `created_at` is the second call's (the expired row was replaced, two deletes counted).
13. **The replay row is reclaimed by `sweep`.** 3 live answers from real keyed calls, plus 10,000 expired head rows and their pages bulk-inserted by the test: `sweep()` at the trash view leaves the 3 and their pages, reports `replays_swept == 10_000`, and spends exactly 2 statements on the arm whatever the count (counted with 3 expired rows and with 10,000). A `sweep` at a path leaves the replay store untouched.
14. **Large answers page.** With the page budget lowered in the test to 1,024 bytes, an answer whose packed size is P bytes is stored in `ceil(P / 1024)` pages, each at most 1,024 bytes, and a hit returns it intact. An answer of at least 100,000 JSON bytes packs and unpacks through `call_offloaded` (counted calls: 1 each way).
15. **A corrupt page refuses.** A page overwritten with junk by direct SQL makes the hit refuse `vfs.internal` and run nothing.
16. **The in-doubt commit.** A disconnect raised at `mutate:after-commit` answers `vfs.unavailable.in_doubt`, `retry_class == refresh`, `retryable is False` without a key and `True` with one; the change is in the store (stat). The keyed resend returns the stored answer with zero mutation statements. A disconnect at `mutate:before-commit` answers the same kind, the change is absent, and the keyed resend runs it once. A disconnect inside `fn` still answers `vfs.unavailable.backend`. `with_retry` ran one attempt in every case (counted).
17. **The parameter.** `request_key` is in `PARAMS` for exactly the twelve `KEYED_OPS` verbs; `""`, a 256-character key, and a key holding a space or a control character refuse `invalid`; the signature drift test and `session.py` forwarding pass; a keyless call passes no `request_key` to storage (spied).
18. **The trait.** `DatabaseStorage.traits()["replay"] == "keyed"`. A keyed call to a mount whose storage does not declare it refuses `unsupported` at the router and reaches no storage method (spied); the same call without the key is served.
19. **The fingerprint is stable.** One fixed `write` call fingerprints to a pinned hex string.
20. `scripts/ci.sh` is green at 100% coverage after every task; the four server legs are green before tasks 3, 4, 5, 6 and 9 land (`tasks.md`).

## ADR amendments this spec needs

- **ADR 087 pin 10.** Its first sentence ("every mutating verb is safe to send twice or recognisable on the second send") holds for every verb but two forms: an `edit` whose `new` contains its `old` (EXECUTED, `foo!!`) and 174's append. Neither can be made recognisable without history, so the table names them key-only and the request key is their remedy. Add: the replay table lives in `ops.py` with three shapes (idempotent, recognisable, key-only) and a verb's shape is its default form's, lowered to key-only by any form that can apply twice; the request key is scoped to the caller's identity (actor, subjects, narrowing), refused for the anonymous caller, and its answer commits with the change in the same transaction; a mismatched reuse is `invalid`; the in-doubt kind is `vfs.unavailable.in_doubt` with retry class `refresh`. Record the TTL once §3.6's marker is answered, and drop it from *Pending Clay*.
- **ADR 087 pin 8.** The fault model gains the in-doubt commit as a named fault: detected at the commit call, never redriven, classified apart, and resolved by the request key.
- **ADR 010** (the envelope and its kinds). Two kinds: `vfs.replayed` (the first kind used only at `info`; produced only by the replay store) and `vfs.unavailable.in_doubt`. Two per-kind `data` records: `exists` may carry the occupant facts (`entry_id`, `kind`, `version`, `content_hash`, and on `copy` `matches_source`); `not_found` from `move` may carry `dest`; `invalid` from `edit` may carry `new_present`.
- **ADR 027.** A replay row is a cached answer, not data: `sweep` reclaims it by age, and a caller's own expired key is replaced in place.
- **ADR 020.** The format bump of §3.1 (pre-release: re-provision, no migration).
- **ADR 074 / ADR 018** (the removal semantics). Record §1.5's rule: relation rows are sets, namespace rows are POSIX.

## Rebase notes for specs 167/171/172 (and 174, 179, 180, 181)

- **171.**
  - §0 "Synchronous, complete-only, and re-issue": replace the "Today (`experiments/r171/p4`)" sentence with "each verb's replay answer is `REPLAY[op]` (spec 177)"; add that a resend with the same `request_key` returns the stored answer.
  - §1.1: the projection table gains the `token` kind (§6 here). The drift test's `WITHHELD` set is unchanged; `request_key` is projected.
  - §1.3: "`idempotentHint` is not set" becomes `idempotentHint = op in IDEMPOTENT_OPS`, pending §6's marker. The replay line is drawn from `REPLAY`.
  - §1.2: no new extra in `ResultPayload`; the replay marker is an `info` error entry. A `vfs.replayed` entry leaves `isError` false.
  - Criterion 15 is met by this spec's conformance family; 171's own test checks that each mutating tool's description quotes `REPLAY[op].replay` and that the annotation is derived.
  - The appendix's `cli` description gains one sentence under "State": "A re-sent line runs again; each command in it answers as its tool does when sent twice."
- **167.** The shell passes no key, so `vfs.replayed` never reaches it. `vfs.unavailable.in_doubt` degrades to the `unavailable` family in the status table (exit 1). Slice D's `copy`/`move` `replace=` (pin 17) adds replay rows: `move(replace=True)` replays like `move`; `copy(replace=True)` re-copies, which is idempotent only if an identical body leaves the version alone (174's rule applied to the copied body), else key-only. That task updates `REPLAY`.
- **172.** No change. The close-time write-back is one `write`, a store; a guest that resends it after a lost reply gets `unchanged` (174).
- **174.** Its §10 rows are §0.1's `write` rows. Its `if_absent` `exists` record should come from `occupant_facts` (§1.1) so the mask applies there too. If `append=True` lands on `write`, `REPLAY["write"]` becomes key-only (§6's marker).
- **179.** The crash-point family can absorb §5's two commit seams; the access-path family should pin the keyed miss and hit counts of criteria 7–8.
- **180.** Add the `replays` phase to `SweepMark` and to the gauge (§4). The format bump is shared (§3.1).
- **181.** Its §3.1 bullet citing 177 holds: the move replay's `dest.entry_id` comes from the probe row, at the `read` rung. When 181 lands, criterion 3 reads the id from `stat`.

## Appendix: the probes (EXECUTED at `ba77449`)

Scripts and outputs in the session scratchpad, `/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/5d8df80f-e1a8-4b32-8c5d-fd4fe65a3cc5/scratchpad/177/`. All against `VirtualFileSystem(storage=InMemoryStorage())` as the system actor unless named. The results that matter are copied here.

**A. `replay_head.py`**: every mutating verb sent twice.

```text
write /a.md 'one' #2               ok=True  rows=[('/a.md', 'updated', 2)]
write overwrite=False /b.md #2     ok=False errs=[('vfs.exists', 'error', None)]
edit x->xx (new contains old) #2   ok=False errs=[('vfs.invalid', 'error', None)]   # two matches: ambiguous
edit world->there #2               ok=False errs=[('vfs.invalid', 'error', None)]
mkdir /d #2                        ok=False errs=[('vfs.exists', 'error', None)]
mkdir /d2 exist_ok #2              ok=True  rows=[('/d2', 'unchanged', 1)]
delete /x.md #2                    ok=False errs=[('vfs.not_found', 'error', {'vfs.trashed': True, 'vfs.deleted_at': '…'})]
restore /x.md #2                   ok=False errs=[('vfs.exists', 'error', None)]
copy /x.md /y.md #2                ok=False errs=[('vfs.exists', 'error', {'vfs.target': '/x.md'})]
move /y.md /z.md #2                ok=False errs=[('vfs.not_found', 'error', None)]
mkedge a->x #2                     ok=True  rows=[('/a.md', 'updated', None)]
rmedge a->x #2                     ok=True  errs=[('vfs.not_found', 'warning', {'edge_type': 'cites', 'vfs.target': '/x.md'})]
grant /d alice read #2             ok=True  extra=['grants']
revoke /d alice #2                 ok=True  errs=[('vfs.not_found', 'warning', {'principal_id': 'alice'})]
posture /d read #2                 ok=True  extra=['grants', 'relabel']
add_member g alice #2              ok=True  extra=['members']
remove_member g alice #2           ok=True  errs=[('vfs.not_found', 'warning', {'group_id': 'group:g', 'principal_id': 'alice'})]
sweep /.vfs/trash #2               ok=True  rows=[]
```

**B. `payload_sizes.py`**: the stored answer's size, and an edit that applies twice.

```text
write 10k created            rows= 10000 payload_bytes=  1480046 bytes_per_row=148
copy 10k                     rows= 10000 payload_bytes=  1480045 bytes_per_row=148
move 10k                     rows= 10000 payload_bytes=  1480045 bytes_per_row=148
move 10k replay (failure)    errors=10000 payload_bytes= 1230045 bytes_per_row=123
mkedge 10k                   rows= 10000 payload_bytes=  1560047 bytes_per_row=156
delete 10k by rows           rows= 10000 payload_bytes=  2040047 bytes_per_row=204
edit foo->foo! twice leaves: 'foo!!'
```

**C. `commit_disconnect.py`**: the driver connection of a write session closed, then `commit()` called (aiosqlite, a file database).

```text
raised: OperationalError | orig: OperationalError | connection_invalidated: True
classified today: vfs.unavailable.backend retryable: True
rows after: 0
```

**D. `payload_compress.py`**: the 10,000-row write answer under stdlib `zlib` (bytes only).

```text
zlib level 1: raw=1480046 packed=31791 ratio=46.6x
zlib level 6: raw=1480046 packed=29933 ratio=49.4x
```

**E. `posture_twice.py`**: a posture sent twice over five files.

```text
posture #1: ok=True relabel={'rows': 6, 'statements': 2, 'transactions': 1}
posture #2: ok=True relabel={'rows': 6, 'statements': 2, 'transactions': 1}
```

## Landing notes

(Filled in on landing.)
