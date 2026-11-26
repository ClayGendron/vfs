# Every write-gated verb sent twice answers as its row of a replay table in `ops.py` says, and a refused replay names what it found

A draft, written on 2026-11-25. It is not reviewed, and nothing is built. Every fact about the code was read on `dev` at `27f3d24d`, and every answer a decision rests on was run that day against a SQLite file store, from scratch scripts in the session scratchpad; those runs are cited as "the probe". It serves roadmap story K5 at gate b, its criteria 1 and 2 ([the roadmap](../../context/standards/roadmap.md), lines 179 and 180). It is unit 177-1 of [the unit map](../2026-11-25-the-backlog-converted/units.md), converted from [spec 177](../../context/specifications/archive/177-replay-the-contract-and-the-request-key/spec.md), sections 0 and 1, with tasks 1, 4 and 9 of [its tasks](../../context/specifications/archive/177-replay-the-contract-and-the-request-key/tasks.md), read with [the study of that spec](../2026-11-25-the-backlog-converted/studies/165-181/177-replay-the-contract-and-the-request-key.md) and [the reassessment against dev](../2026-11-25-the-backlog-converted/reassessment/writes-and-replay.md). It rests on the landed preconditions spec and on roadmap decisions D7, D11 and D55, and it waits for nothing. On 2026-11-25 it was checked against every spec of this conversion that it names or that names it, as each stood that day, and the answers of the table were run again on a SQLite file store; decisions 1 to 4, 6, 7, 10, 11, 14 and 15 were amended in place by that check, under their own numbers, and decisions 18 to 21 were added by it. Decision 21, on who is given a record, rests on a second run of that day, over every rung of the ladder.

## The outcome wanted

A client that lost the reply to a mutation sends the same call again. After this work, what that second call answers when it carries no request key is written down, for each of the fifteen write-gated verbs and each form of them, as data in `src/vfs/ops.py`, and a conformance family sends every form twice to one storage on the memory, SQLite and Postgres legs and checks the answer and the state against its row.

Every replay that is refused now says what it found. A replayed `move` is `not_found` at the source with `vfs.target` naming the destination and `data["dest"]` naming the file that stands there. A replayed `copy`, `restore` and strict `mkdir`, and the landed create-only `write`, are `exists` with one record of the row that stands at the path: its `kind`, `version` and, for a file, `content_hash`. No record names the entry's database id, and a record is given only to a caller that may read the row it describes. A replayed `edit` whose text is gone says whether its new text is there.

```python
first = await fs.move("/y.md", "/z.md")              # created, version 2
again = await fs.move("/y.md", "/z.md")              # the reply to the first was lost
(error,) = again.errors
# error.kind == "vfs.not_found", error.path == "/y.md"
# error.data["vfs.target"] == "/z.md"
# error.data["dest"] == {"kind": "file", "version": 2, "content_hash": "…"}
```

The caller compares the record with the row its first call would have left, here a file at version 2 with the body's hash at `/z.md`, and learns what stands there without a second read. The record states what is at the path and never whose call put it there; that proof is the request key's, in unit 177-3. Nothing else changes: a call that is not a replay answers as it does today, and no verb issues a statement more on its success path.

## Builds on

- `agents/2026-11-20-write-takes-preconditions-and-an-append/spec.md`, landed on `dev`. Its decision 5 makes an identical write `unchanged`, its decision 7 refuses a create-only write over a live row `exists` with the occupant's version and hash (`src/vfs/storage/backends/database/staging.py:531-541`), its decision 8 is the append, and its decisions 2 and 6 the expected version. The `write` rows of the table pin what it built, and the `exists` record it gave is the one this spec widens.
- The kernel rulings, `context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md`, landed. Decided 2026-11-15 (D55, its decision 6): a move keeps the moved file's identity, so a replayed `move` finds at the destination the `entry_id` the source had. Decided 2026-11-15 (D7, its decision 7): `overwrite=` leaves `write`, so the create-only row is `write(if_absent=True)`. Decided 2026-11-15 (D11, its decision 10): a tool whose verb has any form that applies twice withholds `idempotentHint`, which is why a verb's shape here is set by its worst form.
- `agents/2026-11-22-a-row-carries-a-vid-and-a-change-can-require-it/spec.md`, specified on `dev` and not built, carried by the open branches `origin/every-row-carries-a-vid`, `origin/write-requires-a-vid`, `origin/edit-requires-a-vid` and `origin/delete-move-and-restore-require-a-vid`, whose reviews stand at lands. Its decision 16, landing 1, puts `vid` beside `version` in the data of `exists`, through `occupant_exists`, which on `origin/delete-move-and-restore-require-a-vid` reads `occupant_exists(path, version, content_hash, vid)`. Its decision 7 removes `if_version`, and its decision 12 answers a stale `if_vid` `conflict` with the version and vid at the path. Its Terms say of the entry id, "It never leaves the storage", which decision 6 here keeps. Neither this spec nor that series needs the other. Whichever lands second rebases onto the other: if the vid series lands first, the four sites this spec routes through `occupant_exists` pass the vid it mints; if this lands first, the vid series adds `vid` to the one record, and every site here carries it with no edit of its own, and its second landing replaces the `if_version` form of the `write` row.
- `agents/2026-11-24-a-deleted-row-gives-up-its-path/spec.md`, on the open branch `origin/a-deleted-row-gives-up-its-path` at `d8c1d55d`, reviewed fit to build, not built. Its decision 9, step 1, answers a `restore` over a live row `exists` "with the occupant's version and hash as `occupant_exists` gives them"; this spec builds that answer first, and the deletes spec finds it done. Its decisions 11 and 12 rename `sweep` to `destroy` and confine it to trash paths, and its decisions 4 and 5 make a write at a deleted path a new file. Its landing rewrites the `sweep` row as a `destroy` row and adds whatever forms it changes; the conformance family of decision 15 fails that landing until it does. Either order builds.
- `agents/2026-11-25-a-readable-row-reports-its-owner-and-no-row-reports-the-entrys-id/spec.md`, unit 181-2 of this conversion, written, not reviewed, not built; its directory keeps an earlier title. Its decision 1 reads "No row carries `entry_id`, and the identity half of K9 criterion 3 is the vid", and its Left as it is says of the `data["dest"]["entry_id"]` that K5 criterion 1 names: "Each unit restates its row without a public id: a storage-level test can read the column, and a public row has the vid." Decision 6 here follows it: the occupant record names no id, and the tests read the id from the entries table. Its choice 1 names the other side; a ruling there that shows the id on rows adds the key to the one constructor here. It is not needed first.
- Beside this unit, each written, not reviewed and not built, and none needed first: [177-2](../2026-11-25-a-commit-whose-connection-drops-answers-in-doubt/spec.md), the in-doubt commit, whose Scope leaves to this unit what a caller with no key checks afterwards (decision 18); [177-3](../2026-11-25-a-keyed-call-stores-its-answer-with-its-change-and-a-resend-gets-it-back/spec.md) and [177-4](../2026-11-25-request-key-is-an-argument-of-every-keyed-verb-at-the-router/spec.md), the stored answer and the request key, which add no row here and share two test files with this unit (decisions 15 and 19); [160-1](../2026-11-25-a-cross-mount-file-copy-is-a-read-on-one-mount-and-a-write-on-the-other/spec.md), the cross-mount copy, whose replay is a `write` row and no `copy` row (decision 20); [167-7](../2026-11-25-move-and-copy-take-replace-and-a-move-keeps-the-moved-file/spec.md), whose two `replace` forms decision 14 places; [171-1](../2026-11-25-the-wire-adapter-projects-a-result-to-mcp-blocks-within-budget/spec.md), which reads `REPLAY` and `IDEMPOTENT_OPS` for the tool descriptions and the hint; and [179-1](../2026-11-25-the-conformance-battery-is-split-by-kernel-operation-with-no-test-lost/spec.md), the battery split, which decides where the conformance family sits (decision 15).
- The rights gate as it stands: a caller who reaches a ladder's `exists` or a move's source miss was admitted at the destination's create rung or the occupant's primary rung, every one of them `add` or above. Precedent: `test_add_hears_exists_from_a_create_only_write_over_anothers_row` and `test_a_create_only_write_over_a_row_tells_a_list_holder_nothing` (`tests/storage/database/test_ladder.py:207`, `:241`), and the probe, in which a caller holding nothing or `list` at a move's destination is refused by the gate at the destination before the ladder runs.

## Terms

- **Replay.** The same call, with the same arguments, sent again because the sender got no reply.
- **Form.** One way of calling a verb whose replay answers differently from the others: `write` plain, with `if_version`, with `if_absent=True`, with `append=True`.
- **Shape.** What a verb's replay is: `idempotent` (it succeeds and leaves the state the first call left), `recognisable` (it is refused, leaves that state, and its refusal's data names what it found), or `applies_twice` (some form changes the state again).
- **Occupant.** The live row a verb found at a path it needed free, or, for a replayed `move`, the live row at the destination.
- **Occupant record.** The flat mapping `{"kind", "version", "content_hash"}` that describes an occupant; `content_hash` is left out for a directory. It holds no `entry_id`.
- **Keyless.** A call that carries no `request_key`. Every call on `dev` is keyless, and every row of the table is a keyless call's answer.
- **Keyed.** A call that carries a `request_key`, once units 177-3 and 177-4 are built. Its resend is answered from the stored answer and is no row of the table (decision 19).
- **Bare.** An `exists` that carries no occupant record, as `WritePlan.occupied` names a row the same batch staged (`staging.py:317-326`).

## What the code does today

| Fact | How it is known |
|---|---|
| `WRITE_GATED_OPS` is the ten mutations and the five grant writes, fifteen verbs (`src/vfs/ops.py:68-70`, `:92-98`). No replay table, shape or idempotent set exists under `src/vfs`. | Read; a search of `src/vfs` for `REPLAY`, `replay` and `IDEMPOTENT_OPS` finds none. |
| Sent twice: `write` answers `unchanged`; `write(if_version=1)` answers `unchanged`; `write(if_absent=True)` is `exists` with `{version, content_hash}`; `write(append=True)` is `updated` and appends again; `edit("world" → "there")` is `invalid` with no data; `edit("foo" → "foo!")` is `updated` and leaves `foo!!`; strict `mkdir` is `exists` with no data; `mkdir(exist_ok=True)` is `unchanged`; `delete` is `not_found` with `vfs.trashed` and `vfs.deleted_at`; `restore` is `exists` with no data; `copy` is `exists` with only `vfs.target`; `move` is `not_found` with no data. | The probe. |
| Sent twice: `mkedge` is `updated`; `rmedge` succeeds with a `not_found` warning carrying `edge_type` and `vfs.target`; `grant`, `set_posture` and `add_member` succeed; `revoke` succeeds with a `not_found` warning carrying `principal_id`; `remove_member` with one carrying `group_id` and `principal_id`; `sweep` of the trash view succeeds; `sweep` of a live path is `not_found` with no data. | The probe. |
| Every replay that does not apply twice leaves the entries (path, entry id, kind, version, hash, deleted time, owner, label), the count of version rows, the edges, the grants, the memberships and the pending relabels as the first call left them. | The probe, comparing those tables after each call, and run again on a SQLite file store in the check of 2026-11-25, read through a second connection. |
| Each of two `set_posture("/", "read")` calls over a four-row tree reports `relabel` as 4 rows, 2 statements and 1 transaction, and the second leaves every label as the first left it. The count is known only after the posture row's own transaction (`src/vfs/storage/backends/database/backend.py:1317-1344`). An `edit` to empty text sent twice is `invalid` with no data. | The check of 2026-11-25, on a SQLite file store. |
| The ladder is `none < list < read < add < contribute < read_write`, "Each rung includes every one below it" (`src/vfs/ops.py:125-130`), and grant rows only widen: "there is no deny row" (`src/vfs/storage/grants.py:3-6`). `stat` shows a `list` holder the path and the kind, and shows `version` and `content_hash` from `read` up (`src/vfs/storage/backends/database/reads.py:114`, `:280-284`). | Read, and run: the table of decision 21. |
| With every label settled, no refusal to a caller below `add` on the occupant carries a key of the occupant, for a named caller with a grant at each rung, a named caller under a posture at each rung, and the anonymous caller under a posture at each rung. Below `add` the answers are `not_found` at the parent, `permission_denied` or `unauthenticated`, each with no key of the row. | Run on a SQLite file store on 2026-11-25, twelve calls at each of six rungs for each of the three callers; the table of decision 21. |
| A posture change plants its mark with the posture row, and a pending mark is compiled into every caller's rights as a cover or a hole, "so a reader sees the new posture before the labels do" (`grants.py:18-20`). With the mark standing and no label yet rewritten: after `none` to `add`, `stat` shows the row whole and the create-only write is `exists` with `version` and `content_hash`; after `add` to `none`, `stat` is `not_found` and the write is `not_found` at the parent; after `add` to `list`, `stat` shows a bare row and the write is `permission_denied`. | Run, with the posture verb's relabel loop held back by replacing `_settled` on the instance, for a named caller and for anonymous. |
| A `move` and a `copy` across two postures, and a `restore` after a posture change, leave each row's stored label equal to the posture at its path, with no mark pending; a posture change rewrites the labels of deleted rows as well. | Run. |
| With one stored label set to `none` by a statement on the entries table, beneath an `add` posture and with no mark, the caller's `stat` is `not_found` and its create-only write is `exists` with the row's `version` and `content_hash`; over two bodies at the path the two refusals differ in the hash and in nothing else. `copy`, `move` and both forms of `mkdir` there are `exists` with nothing of the row. With the label set to `list` or `read` every one of them is `permission_denied`. `Rights.admits` at `read`, called on the row's stored columns, is false in that state and agrees with `stat` in every state above. | Run, for a named caller and for anonymous; the last sentence is a prototype that calls `dev`'s own `Rights.admits` (`grants.py:485-498`) and builds nothing. |
| `judging(session, rung)` returns the attempt gate's rights at a rung, and `None` for the system actor; `admit` judges rows in memory by `rights.admits(row["path"], row["owner_id"], row["everyone_level"])` (`src/vfs/storage/backends/database/authorized.py:263-276`). `topology.py:43` and `trash.py:64` import `judging` already. The fence that proves a caller's rights at the commit runs for a successful body alone (`authorized.py:231`). | Read. |
| `DEVELOPER_OPS` is `sweep`, `set_posture`, `add_member` and `remove_member` (`src/vfs/ops.py:101`), so the write-gated verbs outside it are eleven. No verb takes a request key, and `KEYED_OPS` does not exist. `run` is in `EXEC_OPS` (`ops.py:89`) and is not write-gated. | Read. |
| A move reads its sources' committed rows once, after the serialization point (`src/vfs/storage/backends/database/topology.py:148`, `:154`), then reads each source again by `point_row` and classifies a miss by `classify_misses`, one call a missed pair (`:170-172`). An occupied destination is read by `point_row` and refused by `_occupied` (`:188-190`, `:276-281`). | Read. |
| `point_row` selects `SNAPSHOT_COLUMNS`, which hold `entry_id`, `parent_id`, `path`, `name`, `kind`, `version`, `size_bytes` and `deleted_at`, and no `content_hash` (`src/vfs/storage/backends/database/serialized.py:72-81`, `:245-248`). | Read. |
| `restore` fetches `_TOMBSTONE_COLUMNS`, the snapshot's columns plus `trash_root_id`, `owner_id` and `everyone_level`, and no `content_hash` (`src/vfs/storage/backends/database/trash.py:108`, `:306`); its ladder refuses a live row `already_exists(target)` (`:251`), and a row revived earlier in the batch reads live through `_RestoreLadder.row` (`:240-244`). | Read. |
| Strict `mkdir` refuses a live occupant `already_exists(path)` (`src/vfs/storage/backends/database/writes.py:266`) with the occupant's committed row, `content_hash` and the rights columns included, in hand (`writes.py:427-440`). | Read. |
| A transfer's `own` set holds the ids its earlier pairs moved or minted (`topology.py:160`, `:215`, `:446`, `:524`). | Read. |
| `edited_entry` turns a failed `apply_edits` into `invalid` with no data (`src/vfs/storage/editing.py:41-43`); `apply_edits` returns the first failing `replace` result as it is (`src/vfs/storage/replace.py:288-301`), whose miss reads "old_string not found in file content." (`:282-285`). | Read. |
| On SQLite, statements issued by a replayed call, transaction control and statistics left out, system actor then a named caller under a `read_write` posture: `copy` 4 and 13, strict `mkdir` 1 and 6, `restore` 2 and 5, `move` 4 and 8, `edit` 1 and 6, `delete` 2 and 7, `write(if_absent=True)` 1 and 6. A replayed batch of n moves issues 2n + 2 (102 at 50 pairs, 402 at 200, 2,002 at 1,000). A landed one-pair `move` issues 16 and 24, a landed one-pair `copy` 15 as the system actor. `membership_budget` is 32,668 on SQLite. | The probe. |
| `writes.py` holds 1,415 lines and `base.py` 3,090, each at its exact entry in `MODULE_LINE_BASELINE` (`tests/lint/allowlist.py:26-33`), so neither may grow. | Read. |

## The problem

A client that lost a reply cannot tell, from a refused second call, whether its first call landed. A replayed `move` answers a bare `not_found`, which is also the answer for a path that never existed. A replayed `restore` and strict `mkdir` answer a bare `exists`, which is also the answer when a rival made the row. A replayed `edit` either refuses with no data or, when its new text contains its old, applies a second time. The constitution's Article 2 fails a pattern that "forces an agent to guess, retry blindly, or parse prose to learn state"; each of these does.

Nothing pins what a replay answers. Five landings since 2026-11-20 changed a replay answer (the `unchanged` write, the create-only record, the append, and on open branches the vid and the deletes spec), and no test would have said so. The roadmap's MCP story derives `idempotentHint` from "K5's replay table" (roadmap line 874), which does not exist.

At the reference deployment the agent population issues about 150,000 verb calls a day, about one in four a write or edit, and a lost reply is the ordinary failure of a long-lived connection. A replay that cannot be recognised costs the agent a read before every retry, or, for `edit` and an append, a duplicated change. The nightly batch moves and copies 10,000-file batches; a replayed batch must say, pair by pair, what stands at each destination, in a bounded number of statements.

## Decisions

### 1. The replay table is data in `src/vfs/ops.py`, one row for each write-gated verb, one answer for each form

```python
# ---------------------------------------------------------------------------
# The replay table — what each write-gated verb answers when it is sent twice
# ---------------------------------------------------------------------------

ReplayShape = Literal["idempotent", "recognisable", "applies_twice"]


class ReplayAnswer(NamedTuple):
    """What the second of two identical calls answers, in one form of a verb."""

    form: str
    status: Literal["created", "updated", "unchanged", "deleted"] | None = None
    kind: str | None = None
    severity: Literal["error", "warning"] | None = None
    data: frozenset[str] = frozenset()
    applies_twice: bool = False


class Replay(NamedTuple):
    """One verb's replay answers, its default form first."""

    answers: tuple[ReplayAnswer, ...]

    @property
    def shape(self) -> ReplayShape: ...


REPLAY: Final[dict[Op, Replay]] = {...}          # the rows of decision 3
IDEMPOTENT_OPS: Final[frozenset[Op]] = frozenset(op for op, row in REPLAY.items() if row.shape == "idempotent")
```

`status` is the status every row the second call returns carries, and `None` when it returns no row. `kind` is the value of the one error or warning it carries, as a string, and `severity` that entry's severity; both are `None` when it carries none. `data` is the exact set of keys of that entry's `data`. The group sits after the ladder group in `ops.py`, so it reads `Op` and nothing above it.

Reason: the source puts the table beside the op classes it describes, so the conformance family, the drift tests and later the MCP adapter read one source. Facts a test can compare, in place of the source's prose columns, are what makes the table pinned: a landing that changes an answer fails until its row says so. The kind is a string because `vfs.results` imports `vfs.ops` (`src/vfs/results/projection.py`), so `ops.py` may not import `ErrorKind`; a peer's op names are plain strings in the same module for the same reason. The source's "first call" and "verify without a key" columns are left out: the first is what the verb's docstring says, and the second is given as a rule over the rows by decision 18, since the in-doubt unit, [177-2](../2026-11-25-a-commit-whose-connection-drops-answers-in-doubt/spec.md), leaves it to this one.

### 2. A verb's shape follows from its answers, its worst form deciding

`Replay.shape` is `applies_twice` when any answer has `applies_twice`; otherwise `idempotent` when the default answer's `severity` is not `error`; otherwise `recognisable`.

Reason: D11 withholds the hint from a verb with any form that applies twice, so a host never resends an append or an edit on its own. A form that only refuses on replay, such as `if_absent=True`, which the caller chose in order to be refused, does not lower the verb. So `write` and `edit` are `applies_twice`, and `IDEMPOTENT_OPS` is `mkedge`, `rmedge`, `grant`, `revoke`, `set_posture`, `add_member`, `remove_member` and `sweep`. The consequence decision 10 of the rulings accepted, that the `write` tool loses the hint once `append=` lands, holds now, since `append=` has landed. A request key changes no shape (decision 19): 171-1's decision 3 emits `idempotentHint` for `IDEMPOTENT_OPS` and omits it elsewhere "even when this call supplies a key".

### 3. The rows

| Verb | Form | The second call answers | `data` keys | Applies twice | Shape |
|---|---|---|---|---|---|
| `write` | `plain` | success, its row `unchanged` | none | no | `applies_twice` |
| | `if_version` | success, `unchanged` | none | no | |
| | `if_absent` | `vfs.exists`, error | `kind`, `version`, `content_hash` | no | |
| | `append` | success, `updated` | none | yes | |
| `edit` | `old_gone` | `vfs.invalid`, error | `new_present` | no | `applies_twice` |
| | `new_holds_old` | success, `updated` | none | yes | |
| `mkdir` | `plain` | `vfs.exists`, error | `kind`, `version` | no | `recognisable` |
| | `exist_ok` | success, `unchanged` | none | no | |
| `delete` | `plain` | `vfs.not_found`, error | `vfs.trashed`, `vfs.deleted_at` | no | `recognisable` |
| `restore` | `plain` | `vfs.exists`, error | `kind`, `version`, `content_hash` | no | `recognisable` |
| `copy` | `plain` | `vfs.exists`, error | `vfs.target`, `kind`, `version`, `content_hash` | no | `recognisable` |
| `move` | `plain` | `vfs.not_found`, error | `vfs.target`, `dest` | no | `recognisable` |
| `mkedge` | `plain` | success, `updated` | none | no | `idempotent` |
| `rmedge` | `plain` | success, no row; `vfs.not_found`, warning | `edge_type`, `vfs.target` | no | `idempotent` |
| `grant` | `plain` | success, no row | none | no | `idempotent` |
| `revoke` | `plain` | success, no row; `vfs.not_found`, warning | `principal_id` | no | `idempotent` |
| `set_posture` | `plain` | success, no row | none | no | `idempotent` |
| `add_member` | `plain` | success, no row | none | no | `idempotent` |
| `remove_member` | `plain` | success, no row; `vfs.not_found`, warning | `group_id`, `principal_id` | no | `idempotent` |
| `sweep` | `trash_view` | success, no row | none | no | `idempotent` |
| | `path` | `vfs.not_found`, error | none | no | |

The forms are these calls. `write`'s `plain` writes the body the path already holds; `if_version` names the version the first call found and writes a new body; `if_absent` and `append` are those flags. `edit`'s `old_gone` replaces text the first call removed and that its new text does not contain (`"world"` to `"there"`); `new_holds_old` replaces text with text that contains it (`"foo"` to `"foo!"`). `mkdir`'s `plain` is the strict form of a directory. `copy` and `move` are one pair of files in one mount. `sweep`'s `trash_view` is its default path, and `path` names a live directory. Each verb's other forms on `dev`, such as a batch, a directory transfer, `cascade=False` or `replace_all=True`, answer as its default form does, and the table names a form only where the answer differs. The one exception is an `edit` to empty text, which is `invalid` with no data and is named under Left as it is.

Every row is the answer of a call with no request key, sent twice to one storage. No row is a keyed call's (decision 19), no row waits for the ruling on whether `set_posture` takes a key (decision 19), and no row is what the router answers across two mounts (decision 20).

Reason: each row is the answer at `dev` as the probe ran it, with the four refusals this spec adds a record to (decisions 6 and 11) and the edit refusal of decision 12. The `write` rows are the landed spec's. Only the `sweep` row's `path` form is a refusal that names nothing; nothing is there to name, since a swept row leaves no trace, and the deletes spec's landing replaces both `sweep` forms.

### 4. "The state the first call left" is the namespace and the rights, and leaves the counters out

The conformance family compares, after the first call and after the second: each entries row's `path`, `entry_id`, `kind`, `version`, `content_hash`, `deleted_at`, `owner_id` and `everyone_level`; the count of `vfs_versions` rows; each edge's `source_id`, `target_id`, `edge_type`, `weight`, `distance` and `provenance`; each grant's `principal_id`, `path_prefix` and `level`; each membership's `principal_id` and `group_id`; and the count of `vfs_relabels` rows. An answer with `applies_twice` must leave a different state; every other answer the same one.

Left out, because no reader keys on them and a replay of a rights verb moves them: `vfs_meta.grant_revision`, `vfs_principal_revisions`, the grants' `granted_by`, `granted_at` and `revision`, the memberships' `granted_by` and `granted_at`, the index marks in `vfs_index_state`, and every derived search table. Left out as well, where 177-3 is built: its `vfs_replays` and `vfs_replay_pages`, which no keyless call writes and which a `destroy` of the trash head reclaims by its decision 10. The `entry_id` column is compared here, in the storage's own table, and is in no answer. Precedent: the source's rule that "same state" ignores counters no reader keys on, a grant replay's rights being unchanged while the caches revalidate.

### 5. A removal of what is already gone keeps today's two answers

An edge, a grant or a membership is a row of a set: removing one that is not there leaves the same set, so `rmedge`, `revoke` and `remove_member` succeed with one `not_found` warning. A path is a name a caller typed: `delete` of one that is not live is refused, as `rm` is, and the tombstone's hint makes it recognisable. The rule is stated in `REPLAY`'s docstring, and the table pins both halves.

Reason: it is what the tree does, POSIX `unlink` answers ENOENT, and the `not_found` kind maps ENOENT (`src/vfs/results/kinds.py:67`). The alternative, `delete` answering an absent path with success and a warning as `rm -f` does, would change a landed contract and gain nothing the hint does not give.

### 6. One occupant record, built by `occupant_exists`, describes every live occupant an `exists` names

`occupant_exists` stays in `staging.py` and takes the row and the caller's rights at `read`: `occupant_exists(path: Path, row: Mapping[str, Any], rights: Rights | None, *, target: Path | None = None) -> ResultError`. Where the rights admit the row, by the rule of decision 21, it returns `classified(ErrorKind.exists, path, target=target, data=occupant_record(row))`; where they do not, it returns the same `exists` with no record. Beside it, `occupant_record(row: Mapping[str, Any]) -> dict[str, object]` returns `kind` and `version`, and `content_hash` where the row has one. It returns no `entry_id`: the row it is handed holds one, and the record leaves it in the storage. Six sites call it:

- `WritePlan.occupied`, the create-only write over a committed row (`staging.py:317-326`);
- the two rival probes of a create, which already select `entry_id`, `kind`, `path`, `version` and `content_hash` (`writes.py:690`, `:779`, `:693-696`);
- strict `mkdir` and `mkdir(exist_ok=True)` over a file, from the plan's committed row (`writes.py:266`);
- `_occupied`, for a move or a copy onto a live occupant, with `target` the source (`topology.py:276-281`);
- `_RestoreLadder.verdict`, for a restore over a live row (`trash.py:251`).

The keys are flat and unprefixed. The record is the data of `exists` and the value of a moved file's `dest`, nothing else.

Reason: a caller learns what stands at the path by comparing the record with the row its first call would have left: its kind, the version one application gives, and the hash of the body. The record names no id because no row does. The vid spec's Terms hold that the entry id "never leaves the storage", the deletes spec rests on the same rule, and 181-2's decision 1 gives no row an `entry_id` and has each unit that named one restate its record without it. A caller therefore holds no id to compare one with, and the key would leave the storage and prove nothing. D55 still holds, a move and a restore keep the entry's id, and the tests pin it from the entries table. The identity a caller is given is the vid: the vid series adds `vid` to this one constructor (its decision 16), and a caller passes it as `if_vid` on its next change without a read. `kind` lets a strict `mkdir` over a file say so; it means what `wrong_kind`'s `data["kind"]` already means, the occupant's kind (`src/vfs/results/envelope.py:297-299`). The kinds docstring's producer rule, "producer keys are unprefixed" (`kinds.py:60`), and the landed record set the spelling. One constructor keeps the six sites alike, and is the one place the vid series adds its key. Widening the landed create-only record by `kind` is additive; it and the absent id are choices 1 and 4. `writes.py` keeps its 1,415 lines: each changed call stays one line.

### 7. The gate admits the caller to the site, and decision 21 judges the occupant once more before the record is given

A caller reaches each of the six sites, and the move's source miss of decision 11, only after the gate admitted it at the destination's create rung or the occupant's primary rung. Every such rung is `add` or above (`ops.py:151-177`, `:190`), and each rung includes `read` (`ops.py:125-130`). The gate decides who reaches a site. It does not decide alone who is given the record: decision 21 does, by one judgment in memory at `read`.

The gate admits a creation over a live row in two ways (`src/vfs/storage/backends/database/rights.py:931-948`). Where the caller's view names the row, the caller must hold the create rung on that row (`:935-937`), and a caller that holds it holds `read`. Where the view does not name the row, the gate asks whether the caller may mint at the path under the posture rows (`:943-948`), and never looks at the row. The second way is reached with a live row only where the row's stored label is below the posture at its path and no relabel is pending for it. No verb leaves that state (What the code does today), and it was made for the check by one statement on the entries table. In it the caller's `stat` of the row is `not_found` and the landed create-only `write` is `exists` with the row's `version` and `content_hash`.

Reason: an earlier text of this decision made no second judgment, on the ground that a second judgment "would be a branch no caller can reach". The check of 2026-11-25 reached it, and what is reached there is a body's hash given to a caller that may not read the body. The ladder tests pin the first way (`test_ladder.py:207`, `:241`); nothing on `dev` holds the second. Unit 167-7's step 3 judges the occupant at `list` for a call with `replace=True` and names it bare; with decision 21 the call without `replace=` names it bare as well, which is what its decision 5 says of that call. The earlier text also called the second way "the window in which a posture was raised and its relabel has not reached the row". That was wrong: a pending relabel is compiled into the caller's rights, so in the real window the caller reads the row (What the code does today).

### 8. A row the same call made, moved or revived is named bare

A copy or move pair whose destination holds a row whose `entry_id` is in the transfer's `own` set refuses `exists` as today, with `vfs.target` and no record. A restore target that a row revived earlier in the same batch occupies, which `_RestoreLadder.row` reports live, refuses `exists` as today, with no data.

Reason: the call fails whole, so that row will not be stored, and a record of it would describe a file the caller will never find. Precedent: `WritePlan.occupied` names a row the batch staged bare, and `test_a_create_only_batch_that_names_a_path_twice_is_refused_whole` pins it (`tests/support/storage_contract.py:421-430`).

### 9. A deleted occupant keeps today's answer

A transfer onto a tombstoned occupant stays `exists` with `vfs.target` and the trashed hint, and no record (`topology.py:278-281`; `test_a_transfer_onto_a_tombstoned_occupant_is_exists_with_the_hint`, `tests/storage/database/test_trash.py:215`). A move whose destination holds only a tombstone, or nothing, gains no `dest`.

Reason: the record describes a live row a caller can read, act on or compare. A deleted row is reached through `restore` and the trash view, and once the deletes spec lands, a deleted row holds no name at all.

### 10. The rows each site reads gain the columns the record needs, and no site gains a statement

`serialized.py` gains `OCCUPANT_COLUMNS = (*SNAPSHOT_COLUMNS, "content_hash", "owner_id", "everyone_level")`, and `point_row` gains `names: Sequence[str] = SNAPSHOT_COLUMNS`. The destination read in `transfer_rows` passes `OCCUPANT_COLUMNS`; every other `point_row` call is unchanged. `_TOMBSTONE_COLUMNS` gains `content_hash`; it holds `owner_id` and `everyone_level` already (`trash.py:108`). `mkdir` and the create-only write read the plan's committed row, which holds every column already (`writes.py:427-440`). The rival probe's select gains `owner_id` and `everyone_level` (`writes.py:693-696`): `staging.py` gains `RIVAL_COLUMNS`, the five names the probe selects today and those two, and `_occupant_query` builds its columns from it in the one line it has. `WritePlan.occupied` takes the rights as its second argument. `writes.py` reads `judging` and `RIVAL_COLUMNS` on the two import lines it already has (`writes.py:65`, `:87`), each within the 120-character line, so the file keeps its 1,415 lines.

Reason: the replayed `copy`, `restore` and `mkdir` cost what they cost today, the counts of What the code does today, and a successful verb pays only a 64-character column, an owner name and one integer on a row it already reads. The two rights columns are what decision 21's judgment reads, `RIGHTS_FIELDS` (`rights.py:152`), "The entry columns every row a view judges must carry beside its path". This is the widening the source spec's section 1.1 named.

### 11. A replayed `move` probes the destinations of its absent sources once, and names the live file at each

In `transfer_rows`, for `op == "move"`, right after the committed snapshot (`topology.py:154`): the pairs whose source has no live row in that snapshot are collected, and when there is at least one, their destinations are read by one call of `rows_by_path` with `OCCUPANT_COLUMNS`, imported into `topology.py` by that name. A move whose every source is live issues nothing more. In the pair loop, when a pair's source misses and `classify_misses` places the `not_found` at the source itself, and the probe found a live row at the destination that the caller's rights at `read` admit (decision 21), the error becomes `classified(ErrorKind.not_found, src, target=dest, data={**(miss.data or {}), "dest": occupant_record(row)})`. A miss placed at an ancestor, a destination that holds a tombstone or nothing, and a destination row the caller may not read keep today's error, with no `vfs.target` and no `dest`.

- The locus stays the source, because the source is what is missing. `dest` is a nested record with no path in it, so the rebase across mounts touches only `vfs.target`, which `with_mount` already rebases (`envelope.py`, `ResultError.with_mount`).
- The probe reads committed state, after the serialization point and before any pair runs, so it describes what stands at the destination once the failed call rolls back. A row an earlier pair of the same batch would move there is never in it.
- The server states facts, never the inference "already moved". A rival could have deleted the source and made the destination, and where it wrote the same body at the same version it leaves the same record. A client compares the record with the row its first call would have left; proof of whose call made the row is the request key's, which is 177-3's opening case.

Reason: roadmap K5 criterion 1, and the source's section 1.3 with its probe moved from after the loop to before it, which makes the facts exact without tracking which rows the loop touched. A probe in the loop, one point read a missed pair, would add 10,000 statements to a replayed 10,000-pair batch; one chunked call adds one. Precedent: the committed snapshot it sits beside, and `rows_by_path`, the bounded membership fetch every verb uses.

### 12. A missed edit says whether its new text is there

`ReplaceResult` gains `new_present: bool = False`. `apply_edits` sets it on the result it returns when an edit's `replace` failed because `old` was not found, that edit's `new` is not empty, and `new`, with its line endings normalised as `replace` normalises them, occurs in the text that edit saw. `edited_entry` then refuses `invalid` with `data={"new_present": True}`; in every other case the refusal carries no data, as today. A failure of another cause (an empty `old`, `old == new`, several matches, the fuzzy budget, `replace_all` over a fuzzy match) never sets it.

Reason: this makes the common edit replay recognisable at the cost of one substring search over a body already in hand, on a refusal only. It cannot catch the replay whose new text contains its old, which matches again and applies twice, and that is why `edit` is `applies_twice`. A `False` is not written, because the kinds docstring reads an absent key as "not known" (`kinds.py:52`). The miss is told apart by a field `replace` sets at its final return, never by its message, which is prose.

### 13. A replayed `copy` names the copy and the source, and no derived flag

The `exists` of a copy carries `vfs.target`, the source, and the record of the copy at the destination: `version` 1 and the body's `content_hash` on a replay. The source spec's `matches_source` flag is not added.

Reason: the client holds the source's path and can compare the record's hash with the source's by `stat`. The flag would need the source's hash, which the snapshot does not read. Adding a key later is additive, so leaving it out is the cheaper side; it is listed under Choices to confirm.

### 14. A landing that changes a replay answer changes its row in the same change

The table holds the forms `dev` serves on the day this unit is built. The vid series' second and fourth landings replace the `if_version` form with `if_vid` and add the `if_vid` forms of `edit`, `delete`, `move` and `restore`. The deletes spec's landing replaces the `sweep` row with a `destroy` row and adds any form it changes. Unit [167-7](../2026-11-25-move-and-copy-take-replace-and-a-move-keeps-the-moved-file/spec.md) adds the `replace=True` forms of `move` and `copy`, as its decision 11 states them: `replace` on `move`, with the plain form's answer, and `replace` on `copy`, `ReplayAnswer("replace", status="unchanged")`, each with a driver. Where 167-7 has landed first, the two forms are served on `dev`, so this unit's table and `DRIVERS` hold them from the start.

Three units of this conversion add no form. [177-3](../2026-11-25-a-keyed-call-stores-its-answer-with-its-change-and-a-resend-gets-it-back/spec.md) and [177-4](../2026-11-25-request-key-is-an-argument-of-every-keyed-verb-at-the-router/spec.md) leave the keyless table to this unit in their Scope, and a keyed resend is no form (decision 19). [160-1](../2026-11-25-a-cross-mount-file-copy-is-a-read-on-one-mount-and-a-write-on-the-other/spec.md) adds none to `copy` (decision 20). 177-3's decision 10 hangs the reclaim of expired replay rows on a `destroy` of the trash head and returns `replays_reclaimed`; that is a count on the result, which no `ReplayAnswer` field holds, so the `destroy` row stays a success with no row.

Reason: the conformance family drives every form the table names and checks each answer, so a landing that changes an answer without its row is red, and one that adds a verb without a row fails the drift test of decision 15. This is the pin roadmap K5 criterion 2 asks for. Precedent: tasks.md task 1 of the source, which let the `write` row move with spec 174.

### 15. The conformance family is a mixin, driven by the table, on three legs

`tests/support/replay_contract.py` holds `ReplayContract` and `DRIVERS: dict[tuple[Op, str], ReplayDriver]`, one driver for each verb and form of `REPLAY`. A driver seeds the world its form needs and returns the call to send twice. `ReplayContract` is mixed into `TestMemoryConformance`, `TestSqliteConformance` and `TestPostgresConformance` in `tests/storage/test_conformance.py`, beside `CursorContract`. It calls the storage seam with the system actor, as the membership verbs require.

Two files are shared with 177-3. Its keyed conformance nodes run from `tests/support/replay_contract.py::ReplayContract` on the same three legs, and its storage tests sit in `tests/storage/database/test_replays.py`, the file the Tests section here opens. The first of the two units to land creates each file and the class, and the second adds to them; no test name is in both specs. `DRIVERS` holds keyless drivers alone: a keyed test may seed its world with a driver and adds no entry, so `test_every_replay_form_has_a_driver` reads the same before and after 177-3.

Where [179-1](../2026-11-25-the-conformance-battery-is-split-by-kernel-operation-with-no-test-lost/spec.md), the battery split, has landed first, the family is `ReplayRows` in `tests/support/contract/replay.py`, composed into `StorageContract`, as its decisions 3 and 4 place a law over verbs of several groups, and the legs name no third class. Where this unit lands first, the split moves the module whole, as it moves `cursor_contract.py`, and the row this unit changes at `tests/support/storage_contract.py:394` goes with the `write` rows under its own name. Either way every id stays `tests/storage/test_conformance.py::<leg>::<method>`, and by its decision 11 a row added after the split need not join its record.

Reason: `CursorContract` is the precedent for a family mixed into each database leg (`tests/support/cursor_contract.py`). Roadmap K5 criterion 2 names the memory and SQLite legs; the Postgres leg is added because decisions 10 and 11 change what the move and the restore read, and Postgres plans and binds those reads its own way. The drift between the table and its drivers is a test, so a form cannot be named and left undriven. 179-1's decision 15 says of two units that touch one contract module that "whichever lands second rebases", which is the rule taken here for both shared files.

### 16. `REPLAY` is not exported from `vfs` and has no reference page at this unit

`REPLAY`, `Replay`, `ReplayAnswer`, `ReplayShape` and `IDEMPOTENT_OPS` live in `vfs.ops`, as `WRITE_GATED_OPS` does, and are added to no `__all__` of `vfs`. The records a caller reads are documented where a caller meets them, in the docstring of `ErrorKind`, which the Results reference page renders (`documentation/reference/python-api/results.md:31`).

Reason: their readers at this unit are the kernel's own tests, and at M1 the MCP adapter. A public name is frozen at the beta, and nothing outside the package needs these yet. `base.py`'s verb docstrings are left as they are, since the file is at its line baseline and the kind's docstring is the one place a refusal's data is listed today.

### 17. No convention of Unix is departed from

`rename` of a missing source answers ENOENT, and a create over a name answers EEXIST; the kinds stay `not_found` and `exists`. The data is an addition that an errno cannot carry, and it changes no kind, no locus and no retry class. Article 3 of the constitution asks for a numbered deviation only where a convention is left, and none is.

### 18. After an in-doubt answer a keyless caller checks by the form's row, and the table carries no `verify` column

177-2 answers a commit whose outcome is unknown `vfs.unavailable.in_doubt`, retry class `refresh`, with `retryable=False` for a keyless call, and its hint reads "Read the affected entries (stat, read) to see which before sending the call again." (its decisions 7 and 8). Its Scope leaves to this unit what that caller checks for each verb. No field is added to `Replay` or `ReplayAnswer` for it. The rule is read from the rows:

- **A form whose answer does not have `applies_twice`.** Sending it again leaves the state one send leaves, and the second answer says which happened: the verb's ordinary answer where the first send did not land, and the row's answer where it did. A refusal's data is the read 177-2 asks for, already made: the occupant record, a move's `dest`, a delete's `vfs.trashed`. The conformance family pins the second case; the first is a first send to an unchanged world.
- **A form whose answer has `applies_twice`.** On `dev` these are `write` with `append=True` and an `edit` whose new text contains its old. It is never sent again unread: the caller reads the file and compares its body with the body one application leaves.
- **A refusal that names nothing.** An `edit` to empty text and a `sweep` of a path are refused on replay with no data (Left as it is), so the refusal settles nothing. Their callers read as well: the file for the edit, `stat` of the path for the sweep.

A resend is an ordinary second call and acts on the state it finds. Where another writer may have acted on the same paths between the two sends, as a rival that made a new file at a path the first send deleted, the caller reads first, which is what 177-2's hint asks of every caller and what `retryable=False` tells a host.

Reason: an earlier text of 177-2's Scope named "the replay table's last column" for this, and decision 1 had named 177-2, so neither spec carried it; 177-2's Scope now cites this decision. The source's column was prose a test cannot compare, and each of its entries is one of two things: the form's own replay answer, or a read of the body. A rule over `applies_twice` is pinned by the table's tests; a `verify` field added later is additive, so leaving it out is the cheaper side, and it is choice 5. Precedent: D11 lets a host resend on its own only what `IDEMPOTENT_OPS` names, and 177-2's decision 8 sets the flag a host reads to `False` because "the study's probe applied an `edit` twice".

### 19. The table holds what a call with no request key answers, and no row waits for the ruling on `set_posture`

`REPLAY` describes a keyless call. 177-3's decision 2 says "The absence of a key bypasses key validation, hashing, answer storage and lookup", so every row holds before and after 177-3 and 177-4 are built, and neither unit adds, changes or removes a row or a form. A keyed resend is answered in one of two ways, and neither is a form of this table:

- **A live stored answer.** Within its window, at the same storage, by the same authority, with the same effective arguments, the resend returns the stored first answer and one `vfs.replayed` information record (177-3's decisions 6 and 9), for every verb of `KEYED_OPS` (177-4's decision 1).
- **No live stored answer.** The window of 177-3's decision 10 has lapsed, or the first send was refused or rolled back and so stored nothing (its decision 7). The verb runs, and it answers as its keyless row here says.

A key changes no shape. `Replay.shape` and `IDEMPOTENT_OPS` are computed from keyless answers alone.

| Rows of the table | Takes a request key |
|---|---|
| `write`, `edit`, `mkdir`, `delete`, `restore`, `copy`, `move`, `mkedge`, `rmedge`, `grant`, `revoke` | yes: 177-3's decision 2 and 177-4's decision 1, eleven verbs |
| `set_posture` | waits for the ruling that 177-3 and 177-4 each list as "The twelfth verb" |
| `sweep` (`destroy`, after the deletes spec), `add_member`, `remove_member` | never |

No row waits. The `set_posture` row is the keyless answer, a success with no row. Run on `dev`, two sends each report the same `relabel` counts and leave every label as the first left it; the counts are an extra on the result, which no `ReplayAnswer` field holds. A resend after a crash between the posture row's commit and its relabel chunks finishes those chunks (`backend.py:1317-1344`), which moves the state to the one a completed first send leaves. That is why 177-3's decision 11 cannot store a posture answer in one transaction, and it changes nothing here. The row stands under a ruling for eleven keyed verbs and under a ruling for twelve: the ruling settles whether `set_posture` joins `KEYED_OPS`, and `KEYED_OPS` is no part of this table.

The four verbs outside the eleven are `DEVELOPER_OPS`, and each is `idempotent`. So under either ruling `WRITE_GATED_OPS - IDEMPOTENT_OPS <= KEYED_OPS`: every verb whose shape is `recognisable` or `applies_twice` takes a key. The second of this unit and 177-4 to land pins that with `test_every_verb_outside_the_keyed_set_is_idempotent`, and the second of this unit and 177-3 to land adds `test_a_keyed_resend_with_no_live_answer_answers_as_its_keyless_row`.

Reason: 177-3's Scope puts "the keyless replay table" in this unit and 177-4's reads "Keyless replay classifications belong to 177-1", and 171-1's decision 3 reads the hint from `IDEMPOTENT_OPS` whether or not a call carries a key. A table that mixed keyed forms in would change with the ruling; one that holds keyless answers alone does not. Precedent: the source's section 0.2, whose drift test pins `KEYED_OPS <= WRITE_GATED_OPS` and which says of `sweep`, `add_member` and `remove_member` that they "take no key" and "are idempotent by shape". Pinning the relation is choice 6.

### 20. A row is what one storage answers, and a cross-mount `copy` sent twice answers the create-only `write` row

The conformance family calls the storage seam, and `REPLAY` is that seam's table. What the router answers before any storage is asked is no row, and is the same on every send: a read-only mount's refusal of a write-gated verb, `cross_mount` for a `move` pair across mounts, 177-4's `unsupported` for a keyed call at a mount without the `replay` trait (its decision 5), and 160-1's `cross_mount` for a cross-mount pair of a keyed `copy` (its decision 19, "The same call sent again with the same key is the same refusal").

Where 160-1 is built, a keyless `copy` pair across mounts is a read of one mount and a create-only write of the other (its decisions 1 and 10). Sent twice, it is answered by the destination storage's `write`, in the `if_absent` form of the `write` row: `exists` at the destination with the record of decision 6 and no `vfs.target`, the group stopping at its first page (its decision 12) and adding no `cross_mount` information record, since no pair landed (its decision 13). 160-1's decision 19 says the same: it is "no row of `copy`, since the storage saw a write". The `copy` row here is an in-mount pair's, and no `cross_mount` form joins `REPLAY["copy"]`, because no storage can be driven to it. The second of this unit and 160-1 to land adds `test_a_cross_mount_copy_sent_twice_answers_as_a_create_only_write` to 160-1's `tests/base/test_copy_across_mounts.py`.

Reason: a storage sees its own slice of a call and nothing of the other mount, so a table driven at the seam can pin only what one storage answers; the two public answers of `copy` differ by one key, `vfs.target`, and each is pinned where it is produced. Precedent on `dev`: the router refuses a cross-mount pair before any storage is called (`src/vfs/base.py:2339-2341`), and `Result.with_mount` rebases what a storage answered and adds no fact to it.

### 21. The occupant record goes only to a caller whose rights at `read` admit the occupant, judged once in memory

Decided 2026-11-25: every site of decision 6, and the `dest` of decision 11, gives the record only to a caller that holds `read` on the row it describes. Each site passes `judging(session, "read")` to `occupant_exists`, and the move's probe asks the same of each destination row. The record is given where those rights are `None`, which is the system actor and a call with no gate, or where `rights.admits(row["path"], row["owner_id"], row["everyone_level"])` holds. Otherwise the refusal carries no key of the row: an `exists` keeps its `vfs.target` where the site has one, which is the caller's own source path, and a move's source miss is today's error with no `vfs.target` and no `dest`.

The three keys are given or withheld together, and each has its own ground:

- **`content_hash`.** A SHA-256 of a body is an equality test on the body. A caller that holds it confirms a guess of a short or low-entropy file by hashing candidates, and sees every change of the file. It is given at `read` and never below.
- **`version`.** It counts the changes of a row a caller may not see, and `stat` shows it from `read` up. It is given at `read` and never below.
- **`kind`.** `stat` shows it to a `list` holder, so giving it at `list` would leak nothing. It is withheld below `read` all the same: no state reaches a site with `list` and without `read` on the occupant (the table below), so a second tier would be a branch nothing runs, and one judgment keeps one constructor.
- **`vid`.** The vid series adds it to this constructor, and its own opening rule is "Every row a call returns about a file or a directory that the caller may read carries a `vid`". It rides the same judgment.

What `dev` answers today, run on a SQLite file store with every label settled, for a named caller holding the column's rung on the occupant by a grant. The cell is the refusal's kind and the keys of its `data`:

| The call, over a live occupant | `none` | `list` | `read` | `add` | `contribute` | `read_write` |
|---|---|---|---|---|---|---|
| `stat`, for comparison | `not_found` at the parent | row: `kind` | row: `kind`, `version`, `content_hash` | the same | the same | the same |
| `write(if_absent=True)` | `not_found` at the parent | `permission_denied`, none | `permission_denied`, none | `exists`: `version`, `content_hash` | the same | the same |
| `copy` and `move` onto it | `not_found` at the parent | `permission_denied`, none | `permission_denied`, none | `exists`: `vfs.target` | the same | the same |
| `mkdir`, strict or `exist_ok=True` | `not_found` at the parent | `permission_denied`, none | `permission_denied`, none | `exists`, none | the same | the same |
| `restore` | `not_found` at the parent | `permission_denied`, none | `permission_denied`, none | `permission_denied`, none | `permission_denied`, none | `exists`, none |
| `write` with a stale `if_version` | `not_found` at the parent | `permission_denied`, none | `permission_denied`, none | `permission_denied`, none | `conflict`: `version` | the same |
| `edit` whose old text is absent | `not_found` at the parent | `permission_denied`, none | `permission_denied`, none | `permission_denied`, none | `invalid`, none | the same |
| `delete` of a deleted path | `not_found` at the parent | `permission_denied`, none | `permission_denied`, none | `permission_denied`, none | `permission_denied`, none | `not_found`: `vfs.trashed`, `vfs.deleted_at` |
| `copy` onto a deleted path | `not_found` at the parent | `not_found`, none | `exists`: `vfs.target`, `vfs.trashed`, `vfs.deleted_at` | the same | the same | the same |

The `not_found` at the parent carries `vfs.target`, the path the caller sent. A named caller with no grant under a posture at the column's rung answers cell for cell the same. The anonymous caller under a posture at the column's rung is `unauthenticated` with no data wherever the rung is below the verb's own: its create-only write is `exists` with `version` and `content_hash` from `add` up, its stale `if_version` is `conflict` with `version` and its `mkdir` and `edit` answer from `contribute` up, and its `copy`, `move`, `restore` and `delete` answer at `read_write` alone. So with settled labels nothing of an occupant reaches a caller below `add`, `add` includes `read`, and every caller that is given `version` and `content_hash` is shown both by `stat`. With a relabel pending the same holds, since the pending posture is in the caller's rights. The one state in which `dev` gives a hash to a caller that may not read the row is the stored label below its posture with no mark, which no verb leaves, and there only the create-only write gives it.

Reason: the landed write spec's decision 9 gave the rule this decision takes: "`add` sits above `read` on the ladder, so the `content_hash` in that refusal goes only to a caller who may read the row." On `dev` that rule holds because two facts agree, the order of the rungs and every stored label matching the posture at its path, and no line of code holds it: the gate's last arm admits a creation by the posture rows without looking at the row (`rights.py:943-948`). This unit takes the record from one site to six and a `dest`, and adds `kind`, so it stops relying on the agreement and judges the row. The judgment is the one every ladder already makes of a row it finds after its gate, `admit(judging(session, rung), rows)` (`authorized.py:263-276`), by `Rights.admits`, whose docstring calls it "the one authority" (`grants.py:485-498`); it agreed with `stat` in every state run. It issues no statement and takes no lock, so no read waits on it. A refusal is not fenced, as no refusal is today (`authorized.py:231`), so a caller whose rights were withdrawn inside the call's window is judged by the rights its gate opened with. The other side, the record to whoever the gate admitted, is choice 7.

## Cost

Costed against [the reference deployment](../../AGENTS.md#the-reference-deployment-the-scale-every-idea-is-filtered-through) on SQLite and Postgres, the engines `dev` serves, and on the generic floor.

- **Per verb call**, about 150,000 a day. A successful verb issues no statement more: the probe of decision 11 runs only when a move's snapshot holds an absent source. The restore fetch selects one more column, `content_hash`, 64 characters a row read, and the destination read of a copy or move pair and the rival probe of a create select that and the two rights columns, an owner name of at most 255 characters and an integer; at the daytime peak of about 20 calls a second that is under 7 KB a second across the mount. A replayed `move` issues one statement more than today (4 to 5 for the system actor, 8 to 9 for a named caller); a replayed `copy`, `restore`, `mkdir`, `edit`, `delete` and create-only `write` issue what they issue today. A missed edit pays one substring search over the body it already holds.
- **Per batch**, 100 a night. A replayed 10,000-pair move issues `ceil(10,000 / membership_budget)` probe statements: one on SQLite, whose `membership_budget` is 32,668 (the probe), one on Postgres, where both caps sit above 10,000 (its `in_list_budget` is 65,535, `src/vfs/storage/backends/database/dialects.py:416`, and its driver binds at most 32,767 parameters), and ten on the floor's 1,000. That is one statement on top of the 20,002 the per-pair ladder issues today (2n + 2, the probe). The probe's map holds at most 10,000 rows of eleven columns while the call runs.
- **Per file write**, **per index visit** and **per corpus**: nothing. No write statement, index pass or rebuild step changes.
- **Per lock**: none is added or held longer. The probe is one read inside the transaction that already holds the mount's serialization point for the move, on a refusal path, and a read never waits on it. No statement is added to any success path, so no lock other callers need is held a statement longer than today.
- **Decision 21**, the judgment at `read`: no statement on any path, on any engine. The rights are the ones the call's gate already resolved, read from the attempt in memory, and `Rights.admits` is one comparison of the label and a bisect over the caller's own spans, which grow with the caller's grants and never with the mount. It runs once for each occupant a refusal would describe, so a replayed 10,000-pair move makes at most 10,000 judgments in memory beside the one chunked probe, and a successful call makes none. It reads no row and takes no lock, so no read and no writer waits on it.
- **Decisions 18 to 20** add no statement, no column and no lock: they say which answers the table holds. A cross-mount `copy` sent twice costs what 160-1's decisions 6, 7 and 12 give a group that stops at its first page: the group's sizing read, that page's body reads and one refused create-only write, with no page after it read or written.

## Left as it is

- A transfer reads each pair's source by its own `point_row`, and classifies each miss by its own `classify_misses`, so a replayed batch of n pairs costs 2n + 2 statements and a landed one about 12n (the probe: 12,005 at 1,000 pairs). Each statement is bounded, the count grows with the batch, and the batch holds the serialization point throughout. This is the landed topology ladder; a chunked ladder is a change of its own for a scale review, and decision 11 adds one statement, not one a pair.
- An `edit` whose new text is empty, and one whose new text contains its old, stay unrecognisable on replay, and an append applies again. Only a request key cures them, which is [177-3](../2026-11-25-a-keyed-call-stores-its-answer-with-its-change-and-a-resend-gets-it-back/spec.md); `write` and `edit` are among its eleven keyed verbs under either ruling on the twelfth. Until then decision 18 has their callers read first.
- No record says whose call made the row it describes. A rival that wrote the same body at the same version leaves the same record, and telling the two apart is the request key's work, not the table's.
- `set_posture` sent twice writes each label beneath the path again, to the value it holds. The answer and the state are the first send's; the second rewrite is the posture verb's cost, not this unit's to remove.
- `sweep` of a live path stays a bare `not_found` on replay; the deletes spec retires that form.
- A move whose source is missing at an ancestor keeps its ancestor `not_found` with no `dest`; the replay the table pins misses at the source.

## Tests

Written first and seen failing, at the layer each behaviour lives. Counts and states, never clocks.

The table, `tests/test_ops.py`:

- `test_the_replay_table_has_one_row_for_each_write_gated_verb`: `REPLAY.keys() == WRITE_GATED_OPS`, fifteen rows.
- `test_each_verb_names_its_forms_once`: every row has at least one answer, and its forms are distinct.
- `test_an_answer_names_a_kind_exactly_when_it_names_a_severity`: `kind is None` iff `severity is None`, and an answer with `applies_twice` succeeds.
- `test_a_shape_follows_from_its_answers`: the rule of decision 2 on three synthetic rows, one of each shape, and on `REPLAY`: `write` and `edit` are `applies_twice`; `mkdir`, `delete`, `restore`, `copy` and `move` are `recognisable`.
- `test_idempotent_ops_are_the_rows_whose_shape_is_idempotent`: `IDEMPOTENT_OPS` equals the literal set of decision 2.
- `test_every_replay_form_has_a_driver`: `set(DRIVERS) == {(op, answer.form) for op, row in REPLAY.items() for answer in row.answers}`.
- `test_no_replay_answer_names_an_entry_id`: no `ReplayAnswer.data` of `REPLAY` holds `entry_id` (decision 6).
- `test_the_forms_that_apply_twice_are_an_append_and_an_edit_whose_new_text_holds_its_old`: the set of `(op, form)` whose answer has `applies_twice` is exactly `{("write", "append"), ("edit", "new_holds_old")}`, the two forms decision 18 has a caller read before sending again. A landing that adds a third fails here until the list and `REPLAY`'s docstring name it.
- `test_every_verb_outside_the_keyed_set_is_idempotent`, added by the second of this unit and 177-4 to land: `WRITE_GATED_OPS - IDEMPOTENT_OPS <= KEYED_OPS` and `KEYED_OPS <= WRITE_GATED_OPS`. It holds with eleven keyed verbs and with twelve, and names neither count.

The contract, `tests/support/replay_contract.py`, each method run as `tests/storage/test_conformance.py::<Class>::<method>` for `TestSqliteConformance`, `TestPostgresConformance` and `TestMemoryConformance`:

- `test_each_form_sent_twice_answers_as_its_row_says[<op>-<form>]`, parametrised over every form of `REPLAY`: the second answer's success, its rows' statuses, its one error's kind and severity, and the exact key set of that error's data equal the row's; the state of decision 4 after the second call equals the state after the first, and differs where the answer has `applies_twice` (one more version, one more version row).
- `test_a_replayed_move_names_the_file_at_its_destination`: after `move(/y, /z)` the replay is `not_found` at `/y` with `data["vfs.target"] == "/z"` and `data["dest"]` equal to exactly `{"kind": "file", "version": v, "content_hash": h}`, where `v` is the first move's returned version and `h` the stored hash, so it holds no `entry_id`. Read from the entries table, the row at `/z` holds the id the table held for `/y` before the first move.
- `test_a_move_whose_destination_holds_nothing_live_names_no_destination`: a move of a path that never existed, and a replay after the moved file was deleted, carry neither `vfs.target` nor `dest`.
- `test_a_replayed_restore_names_the_row_the_first_restore_revived`: the record's `version` is the first restore's returned version and its `content_hash` the body's. Read from the entries table, the row holds the id it had before the delete.
- `test_a_replayed_copy_names_the_copy_and_its_source`: `vfs.target` is the source, the record's `version` is 1, and its `content_hash` equals the source's.
- `test_a_strict_mkdir_over_a_file_names_a_file`: `exists` with `kind == "file"` and a `content_hash`; over a directory, `kind == "directory"` and no `content_hash`.
- `test_a_replayed_edit_says_its_new_text_is_there`: `edit(f, "world", "there")` sent twice refuses `invalid` with `data == {"new_present": True}`; an edit whose old text was never there and whose new text is absent refuses with no data; and `edit(f, "world", "")` sent twice refuses with no data.
- `test_a_keyed_resend_with_no_live_answer_answers_as_its_keyless_row`, added by the second of this unit and 177-3 to land: a keyed `move` lands; 177-3's replaceable clock is put past the answer's expiry; the same keyed call answers `not_found` with `vfs.target` and `dest`, exactly the `move` row's keys, carries no `vfs.replayed` record and leaves the state of decision 4 as it was, and the refusal stores no answer (177-3's decision 7). A keyed `write(append=True)` resent the same way appends once more, as its row says.

The storage, a new `tests/storage/database/test_replays.py`:

- `test_a_replayed_refusal_issues_the_statements_it_issued_before[<verb>-<caller>]`, on a SQLite file store, which is also the pin that decision 21's judgment issues no statement, since the named caller's refusals are judged: the counts of What the code does today, unchanged for `copy`, `restore`, `mkdir`, `edit`, `delete` and create-only `write`, for the system actor and for a named caller under a `read_write` posture; the replayed one-pair `move` issues 5 and 9.
- `test_a_landed_move_issues_no_probe[sqlite|postgres]`: with `topology.rows_by_path` wrapped by a counter, a landed one-pair move calls it zero times, and on SQLite issues 16 statements as the system actor and 24 as a named caller.
- `test_a_replayed_move_probes_its_destinations_once[sqlite|postgres]`: a replayed 3-pair move calls `topology.rows_by_path` once, with the three destinations.
- `test_a_replayed_batch_of_ten_thousand_moves_names_each_destination`, marked `slow`, on SQLite: 10,000 errors, each with `dest`; the probe's statements are `ceil(10,000 / storage._host.membership_budget)`, and the replay issues 2 × 10,000 + 2 + that many. Run again as a named caller holding `read_write`, it carries 10,000 `dest` records and issues the same number of probe statements.
- `test_a_batch_names_bare_an_occupant_it_made_itself`: `copy` of `[(a, c), (a, c)]` refuses the second pair `exists` with `data == {"vfs.target": "/a"}`; `move` of `[(a, b), (c, b)]` where `c` is live refuses the second pair with no record.
- `test_a_restore_batch_names_bare_a_row_it_revived_itself`: `restore` of `[p, p]` refuses the second `exists` with `data is None`.
- `test_a_move_onto_a_live_occupant_names_it`: a first-time move onto a live file is `exists` with `vfs.target` the source and the occupant's record.

The rule and the leak, `tests/storage/test_replace.py`, `tests/storage/test_editing.py` and `tests/storage/database/test_ladder.py`:

- `tests/storage/test_replace.py::test_a_missed_edit_says_whether_its_new_text_is_there`: `apply_edits` sets `new_present` when the second of two edits misses and its new text is in the text the first left; not when the new text is absent, is empty, or when the failure is several matches.
- `tests/storage/test_editing.py::test_an_invalid_edit_carries_new_present_only_when_it_is_true`.
- `tests/storage/database/test_ladder.py::test_no_caller_the_gate_refused_hears_an_occupant_record[<verb>]`, the leak test, for `copy`, `move`, strict `mkdir`, `restore` and create-only `write`: a caller holding nothing at the occupant's path and one holding `list` there are refused by the gate, and no error of either result carries `entry_id`, `kind` (outside `wrong_kind`), `version`, `content_hash` or `dest`; the replayed move of such a caller names its source miss with no `dest`. The same test holds that an admitted caller's record, on each of the five verbs, has no `entry_id`.
- `tests/storage/database/test_ladder.py::test_no_refusal_below_read_differs_by_the_occupants_body[<call>-<caller>]`, the leak test of decision 21. The calls are create-only `write`, `copy`, `move`, strict `mkdir`, `mkdir(exist_ok=True)` over a file, `restore`, a `move` whose source is absent onto the path, and an `edit` whose old text is absent. The callers are every one below `read` on the occupant: a named caller with no grant; a named caller with `list`; anonymous under a posture of `none` and of `list`; and a named caller and anonymous beneath an `add` posture with the occupant's stored label set to `none` by one statement on the entries table, the one state in which a caller below `read` reaches a site. Each pair runs in three worlds that differ only at the path: nothing there; body A at version 1; body B, written twice, at version 2, and holding the edit's new text. The whole result is compared, its success, its rows and every field of every error, `data` included. The body-A and body-B results are equal for every pair. For a caller that does not hold `list` on the path, by grant or posture, the result over nothing equals them as well. The exception is the four creating calls of the label-edited callers, which the posture admits: over nothing they create, and over a row they are `exists` with `data` equal to `None` or to `{"vfs.target": src}` exactly. No error of any of these results holds `kind`, `version`, `content_hash`, `vid`, `dest` or `new_present`.
- `tests/storage/database/test_ladder.py::test_a_reader_is_given_the_record_and_a_pending_posture_counts[<call>]`, the other side of the same rule: a caller holding `add` by grant, one holding it by posture, and one for whom a posture raised from `none` to `add` has its mark planted and no label rewritten, the relabel loop held back, each hear the record, and each is shown the same `version` and `content_hash` by `stat`; with a posture lowered from `add` to `none` and its relabel held back, the caller hears no record. The system actor hears the record with no gate.
- `tests/storage/database/test_ladder.py::test_add_hears_exists_from_a_create_only_write_over_anothers_row`, changed: its exact data gains `kind` and no other key, and a `copy` onto and a strict `mkdir` over another's row hear the same record.

The tests that pin the landed record exactly change with it, each gaining `kind` alone: `tests/support/storage_contract.py:394` (`test_a_create_only_write_over_a_live_file_is_exists_and_names_what_is_there`) and the key list at `tests/storage/database/test_writes.py:676`.

The router, where 160-1 is built, in its `tests/base/test_copy_across_mounts.py`:

- `test_a_cross_mount_copy_sent_twice_answers_as_a_create_only_write`, added by the second of this unit and 160-1 to land: on two mounts, `copy("/a/t.md", "/b/t.md")` lands and the same call sent again answers one `exists` at `/b/t.md`, whose data keys are exactly those of the `if_absent` answer of `REPLAY["write"]`, with no `vfs.target`; the result carries no `cross_mount` information record; and the state of decision 4 in both mounts is as the first call left it.

The Postgres leg runs through the `db_test` skill before the pull request, since decisions 10 and 11 change what the move and the restore read.

## Scope

In: decisions 1 to 21. `src/vfs/ops.py`; `src/vfs/storage/backends/database/staging.py`, `writes.py`, `topology.py`, `trash.py` and `serialized.py`; `src/vfs/storage/replace.py` and `src/vfs/storage/editing.py`; the docstring of `ErrorKind` in `src/vfs/results/kinds.py`; `tests/test_ops.py`, `tests/support/replay_contract.py`, `tests/storage/test_conformance.py`, `tests/storage/database/test_replays.py`, `tests/storage/test_replace.py`, `tests/storage/test_editing.py`, `tests/storage/database/test_ladder.py`, `tests/storage/database/test_writes.py` and `tests/support/storage_contract.py`; criterion 1 and the state line of story K5 in `context/standards/roadmap.md`. Where the named sibling has landed first, the three tests that decisions 19 and 20 give to the second of two units to land are in as well.

Out, each with where it belongs:

- The in-doubt commit, its kind, its hint and its `retryable` flag: [177-2](../2026-11-25-a-commit-whose-connection-drops-answers-in-doubt/spec.md). What a keyless caller checks after that answer is decision 18 here.
- The stored answer, the `vfs.replayed` record, the request key, `KEYED_OPS` and whether `set_posture` joins it: [177-3](../2026-11-25-a-keyed-call-stores-its-answer-with-its-change-and-a-resend-gets-it-back/spec.md) and [177-4](../2026-11-25-request-key-is-an-argument-of-every-keyed-verb-at-the-router/spec.md). Until they are built every call is keyless and answers as its row says.
- The cross-mount `copy`, and what the router answers for a pair that crosses: [160-1](../2026-11-25-a-cross-mount-file-copy-is-a-read-on-one-mount-and-a-write-on-the-other/spec.md). Today such a pair is refused `cross_mount` on every send, before any storage is asked.
- Where the conformance family's file sits once the battery is split: [179-1](../2026-11-25-the-conformance-battery-is-split-by-kernel-operation-with-no-test-lost/spec.md), by decision 15 here.
- A `set_posture` that skips a subtree whose labels already hold the posture. Today each send rewrites every label beneath the path in bounded chunks, one transaction a chunk, and reports the count: 4 rows, 2 statements and 1 transaction on each of two sends over a four-row tree. A replay therefore costs what the first send cost. It owes a spec of its own, and none of this conversion carries it.
- A stored label that disagrees with the posture at its path while no relabel is pending. No verb was found to leave one, and nothing on `dev` detects or repairs one. Today a caller the posture admits at `add` creates beside such a row, is told `exists` at it, with the row's `version` and `content_hash` from a create-only write, and gets `conflict` with no path and no data from a write with a stale `if_version` (run). After this unit the `exists` names nothing of the row. Whether the gate should refuse that creation outright, and a pass that finds and repairs such labels, owe a spec of their own.
- `idempotentHint` and the tool descriptions that read `REPLAY` and `IDEMPOTENT_OPS`: [171-1](../2026-11-25-the-wire-adapter-projects-a-result-to-mcp-blocks-within-budget/spec.md).
- `vid` in the record and the `if_vid` forms: the vid series on its four branches.
- The `destroy` row, and what a write at a deleted path answers: the deletes spec on `origin/a-deleted-row-gives-up-its-path`.
- The `replace=True` forms: [167-7](../2026-11-25-move-and-copy-take-replace-and-a-move-keeps-the-moved-file/spec.md).
- Whether any row shows `entry_id`: [181-2](../2026-11-25-a-readable-row-reports-its-owner-and-no-row-reports-the-entrys-id/spec.md), whose decision 1 shows it on none. No record of this unit shows it either.
- A chunked transfer ladder: no unit; Left as it is.

## What the docs must say

- `ErrorKind`'s docstring, under "Per-kind `data` records": `exists` from a create, a copy, a move, a restore or a strict `mkdir` may carry the `kind`, `version` and, for a file, `content_hash` of the live row there; `not_found` from a move whose source is gone may carry `dest`, the same record for the live row at the destination `vfs.target` names; `invalid` from an edit may carry `new_present`, when the edit's new text is in the file it found. It says that the record states what stands at the path and not whose call made it, and that it is given only to a caller that may read the row: any other caller the gate admitted hears the same kind with no key of the row. `scripts/docs.sh check` runs, since this is a docstring the Results page renders.
- `REPLAY`'s docstring: what a replay is, the three shapes and the rule of decision 2, the removal rule of decision 5, and that a landing which changes an answer changes its row. It says three more things: every row is a call with no request key sent twice to one storage (decisions 19 and 20); a form that applies twice is read before it is sent again, and every other form's second answer says what happened (decision 18); and a record names no entry id (decision 6).
- Story K5 in `context/standards/roadmap.md`: criterion 1 reads "A replayed `move` returns `not_found` at the source with `vfs.target` the destination and `data["dest"]` the record of the live file there, its kind, version and content hash; a move of a path that never existed carries neither.", and the story gains a state line: criteria 1 and 2 built, with this spec named.

## Earlier decisions this reverses

- Roadmap story K5, criterion 1, "`data["dest"]["entry_id"]` the occupant's id": the record names no id, by decision 6, and the criterion is reworded as under What the docs must say.
- Sections 1.1 and 1.2 of [spec 177](../../context/specifications/archive/177-replay-the-contract-and-the-request-key/spec.md): the occupant facts held `entry_id` on the ground that "spec 181 §3.4 puts `entry_id` at the `read` rung", which unit 181-2's decision 1 does not carry, and a copy carried `matches_source`. Decisions 6 and 13 carry neither.
- Section 0.1 of the same spec, its last column, "Verify an in-doubt outcome without a key", and section 0.2's `verify` field: decision 18 gives a rule over the rows and no field.
- Decision 7 of [the landed write spec](../2026-11-20-write-takes-preconditions-and-an-append/spec.md), "A live occupant is `exists`. The refusal carries the occupant's `version` and `content_hash` in `data`": it stands for a caller that may read the occupant, which is every caller its decision 9 had in mind. Where the caller's rights at `read` do not admit the row, the refusal is now bare, by decision 21. On `dev` that departs from the landed answer in one state, a stored label below its posture with no relabel pending, which no verb leaves.
- An earlier text of decision 7 here, "no second judgment is made": decision 21 makes one.
- An earlier draft of this spec put `entry_id` in the occupant record, on the reading that unit 181-2 showed the id on every row. 181-2 as it stands shows it on none, and decision 6 was corrected on 2026-11-25.

## Not checked

- The Postgres leg was not run, and no Postgres server was at hand for the check of 2026-11-25. The plan Postgres takes for the probe of decision 11 was not read, and the statement counts of the Tests section are SQLite's alone.
- The replayed 10,000-pair move was not run; its 20,002 statements today are 2n + 2 measured at 50, 200 and 1,000 pairs.
- The vid branches and the deletes spec were read, not merged or run against this design; the rebase each needs is reasoned from their texts and from `occupant_exists` on `origin/delete-move-and-restore-require-a-vid`.
- How the renderer and the shell print an `exists` or `not_found` with the new keys was not run. The shell reads `data["kind"]` only for `wrong_kind` (`src/vfs/shell/host.py:502-504`, `src/vfs/shell/programs.py:951-952`), which was read.
- Nothing of units 160-1, 167-7, 171-1, 177-2, 177-3, 177-4, 179-1 and 181-2 is built: each is written and not reviewed. So the three tests that decisions 19 and 20 give to the second of two units to land were not run, and neither were the shared files of decision 15 or the two placements of the conformance family. What was compared is each spec's text as it stood on 2026-11-25.
- No keyed call was run, since no verb on `dev` takes a request key. That a keyed resend with no live answer answers as its keyless row is read from 177-3's decisions 6, 7 and 10, not run.
- A `set_posture` interrupted between its posture row and its relabel chunks was not run; that a resend finishes the chunks is read from `backend.py:1317-1344`.
- Decision 21's judgment is not built. That `Rights.admits` at `read` separates the one leaking state from every other was run as a prototype over `dev`'s own function, for a named caller and for anonymous, in seven states each and an eighth for the named caller; `occupant_exists` was not changed and no site was wired. That the two import lines of `writes.py` stay within 120 characters was counted by hand, not formatted.
- The stored label below its posture was made by one statement on the entries table. No way was found for a verb to leave it: a move and a copy across postures, a restore after a posture change, and a posture change held before its first relabel chunk were run and none does. A crash inside a relabel chunk, and two posture changes racing on one path, were not run.
- The table of decision 21 was run on SQLite alone, for a caller of one subject. A set of two subjects, a group grant and the owner floor were not run; `Rights.admits` is the judgment for all of them, by its docstring.

## Choices to confirm

1. **Does the landed create-only `exists` gain `kind`?** The rulings and the landed spec do not say. Options: one record at all six sites, or the landed `{version, content_hash}` at the create-only write and the wider record at the four new sites. Side taken: one record, because one constructor keeps every `exists` alike, the vid series then adds its key once, and the change only adds a key. Reversing it removes one key from one site.
2. **What is the third shape called?** The source writes `key_only`, after the remedy. Side taken: `applies_twice`, after the fact, because it is true before and after the request key exists, and a host reading the table learns why the hint is withheld. Reversing it is a rename of one literal before the freeze.
3. **Does a replayed `copy` carry `matches_source`?** The source adds it. Side taken: not at this unit, because the record already holds the copy's hash, the client holds the source's path, and the source's hash is not read today. Adding it later is additive.
4. **Does the occupant record name `entry_id`?** Roadmap K5 criterion 1 and the source name it. The other side is unit 181-2's choice 1: its side taken shows the id on no row, and the vid spec keeps it in the storage. Side taken: no id in the record, because a caller is shown no id to compare one with, and a key left out can be added while a key shown cannot be withdrawn after the freeze. A ruling for 181-2's other side adds `entry_id` to `occupant_record`, one line, and to four rows of the table.
5. **Does the table carry a `verify` column?** The source has one, and an earlier text of unit 177-2's Scope named it as this unit's; that Scope now cites decision 18. Side taken: no field, and decision 18's rule over `applies_twice` in its place, because the column was prose no test can compare and every entry of it was the form's own replay answer or a read of the body. Adding a field later is additive.
6. **Is it pinned that every verb outside the keyed set is idempotent?** The other side is unit 177-4, which owns `KEYED_OPS` and derives "no membership from idempotence or write access". Side taken: one test of the relation, `WRITE_GATED_OPS - IDEMPOTENT_OPS <= KEYED_OPS`, added by the second of the two units to land. It derives no membership; it fails a landing that leaves a verb whose shape is `recognisable` or `applies_twice` without a key. It holds under eleven keyed verbs and under twelve. Reversing it deletes one test.
7. **Is the occupant judged again before the record is given?** The other side is the landed write spec, whose decision 7 gives the record to whoever the gate admitted, and an earlier text of decision 7 here, which kept that. Options: one judgment in memory at `read`, the record only where it passes; or no second judgment. Side taken: the judgment, decision 21. The earlier side does not survive: its ground was that the branch could not be reached, the check reached it, and what it gives there is a body's hash to a caller whose `stat` of the row is `not_found`. The judgment is the narrower side and the cheaper to reverse: it costs no statement, it withholds keys in one state that no verb leaves, and dropping it later adds keys where taking it later would remove them. A second tier that gives `kind` at `list` is the other open side, and is additive.

## One line

Each of the fifteen write-gated verbs gets a row in a replay table in `ops.py` saying what a call with no request key answers when one storage is sent it twice, a conformance family sends every form twice on three legs, and every refused replay names the live row it found, by one occupant record that holds no entry id and goes only to a caller that may read the row, a move's `dest` and an edit's `new_present`, with no statement added to any success path and no row that waits for the ruling on a keyed `set_posture`.
