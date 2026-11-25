# `move` and `copy` take `replace=`: a replacing move keeps the moved file and leaves the replaced one restorable, a replacing copy keeps the destination's identity, and a directory on either side is `vfs.exists`

A draft, written on 2026-11-25. It is not reviewed, and nothing is built. Every fact about the code was read on `dev` at `27f3d24d`, and the statement counts cited were run that day on the in-memory store. It serves criterion 2 of roadmap story F4, gate b, and roadmap decisions D7 and D55 (`context/standards/roadmap.md:707`, `:1218`, `:1266`). It is unit 167-7 of [the backlog's map](../2026-11-25-the-backlog-converted/units.md), converted from the numbered spec `context/specifications/archive/167-the-shell-pipeline-core/spec.md` (its decision 7 and its "`overwrite=` on `copy` and `move`" section) with the amendments of [its study](../2026-11-25-the-backlog-converted/studies/165-181/167-the-shell-pipeline-core.md) and of [the reassessment's section for 167-7](../2026-11-25-the-backlog-converted/reassessment/shell.md). It rests on [the kernel rulings of 2026-11-15](../../context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md), on the deletes spec on the branch `origin/a-deleted-row-gives-up-its-path`, reviewed fit to build and not built, and on the vid series, whose fourth landing is the branch `origin/delete-move-and-restore-require-a-vid`, not on `dev`.

## The outcome wanted

An agent or a pipeline can move a file onto a file that is already there, and can copy a file over one, by asking for it. A move that replaces keeps the moved file: its `entry_id`, its edges and its history go with it to the destination. The file it replaced is not lost: it becomes a deleted row at the destination's path, shown by the trash view and brought back by `restore` once the path is free. A copy that replaces writes the source's body onto the destination's row, which keeps its identity and keeps its old body as a version, as `cp` does. Without `replace=True` both verbs refuse an occupied destination with `exists`, as today.

```python
await fs.move("/proj/draft.md", "/proj/final.md", replace=True, authority=who)
# the row at /proj/final.md has draft.md's entry_id; /proj/draft.md is not_found
await fs.stat("/.vfs/trash/proj/final.md", authority=who)    # the replaced final.md, deleted_at set
await fs.copy("/proj/template.md", "/proj/notes.md", replace=True, authority=who)
# notes.md keeps its entry_id and owner, its version rises by one, its old body is a version
await fs.move("/proj/dir_a", "/proj/dir_b", replace=True, authority=who)   # vfs.exists: replace never applies to a directory
```

Once the vid series has landed, a caller that read the destination can require it: `moves=[(src, dest)], replace=True, if_vids={dest: row.vid}` replaces only the file it read, and is `conflict` where that file has moved on.

## Builds on

- [The kernel rulings](../../context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md), landed. Decision 6: "A move keeps the moved file's identity, a replacing move included, and the replaced file stays undoable", and "A replacing `copy` ... stays a write of the source's body onto the destination's row, which keeps the destination's identity and keeps the replaced body as a version". Decision 7: "The flag that lets `move` or `copy` land on an existing file is `replace=`, default refuse". Its Scope: a directory over a directory is refused `vfs.exists` until a spec rules otherwise. Roadmap rows D7 and D55 record both as decided on 2026-11-15.
- The deletes spec, `origin/a-deleted-row-gives-up-its-path:agents/2026-11-24-a-deleted-row-gives-up-its-path/spec.md`, reviewed fit to build on 2026-11-24 and not built. This spec relies on four of its decisions. Decision 1: "`path` and `(parent_id, name)` are unique among live rows, and among them only." Decision 4: "A `move` or a `copy` lands there. Its destination check reads the live side." Decision 14, the rule this spec builds the argument on: "In the move's own transaction, before its claim, the occupant is stamped as a deleted row and its own root, by the statement a delete uses", "The moved row keeps its entry id and takes the name", "The mover needs delete's rung on the occupant", and "A directory at the destination is `exists`". Decision 17: a row from the trash view reports `/.vfs/trash/<its own path>`. Its decision 16 orders three landings; this spec's first landing comes after the deletes spec's second, "The name is free", and does not need its third, `destroy`.
- The vid series: [the vid spec](../2026-11-22-a-row-carries-a-vid-and-a-change-can-require-it/spec.md) on `dev`, built on the branches `origin/every-row-carries-a-vid`, `origin/write-requires-a-vid`, `origin/edit-requires-a-vid` and `origin/delete-move-and-restore-require-a-vid`, each ahead of `dev` and none merged. This spec relies on its decision 6 ("`if_vids` is the precondition of the batch form ... It maps a path to the vid required there", and "The kernel turns `if_vid=E` into a mapping of one key ... A storage sees one shape"), decision 11 ("A move requires its source, and its destination takes no precondition", with the reason "a precondition protects what a call would replace"), decision 12 (the answers of a mismatch), decision 13 (a trait gates a precondition), decision 18 (the mark `ABSENT`) and decision 19 (`stale_vid`). On the branch, `move` says "The destination takes no vid: a move never replaces what is there" (`origin/delete-move-and-restore-require-a-vid:src/vfs/base.py:1316`). This spec's second landing comes after the series' fourth.
- [Write takes preconditions and an append](../2026-11-20-write-takes-preconditions-and-an-append/spec.md), landed: `overwrite=` has left `write` (`src/vfs/base.py:925-938`), which is decision 7's condition, and a write over a file keeps its replaced body as a version row (`src/vfs/storage/backends/database/writes.py:543-550`).
- [Every mutating verb sent twice answers as a pinned replay table says](../2026-11-25-every-mutating-verb-sent-twice-answers-as-a-pinned-replay-table-says/spec.md), unit 177-1 of this conversion, a draft written on 2026-11-25, not reviewed and not built. Its decision 1 makes the replay table data in `src/vfs/ops.py`, `REPLAY`, a row of `ReplayAnswer`s for each write-gated verb, one for each form; its decision 11 makes a replayed `move` a `not_found` at the source carrying `vfs.target` and `data["dest"]`, the record of the live file at the destination; its decision 14 says a landing that changes a replay answer changes its row in the same change; and its Scope says unit 167-7 adds the `replace=True` forms of `move` and `copy`. Decision 11 here states those two forms. Neither spec waits for the other.
- [A cross-mount file copy is a read on one mount and a write on the other](../2026-11-25-a-cross-mount-file-copy-is-a-read-on-one-mount-and-a-write-on-the-other/spec.md), unit 160-1, a draft. Its Left as it is says that when this unit adds `replace=`, a replacing cross-mount copy writes without `if_absent`. Decision 12 states the same from this side.

Build order: the deletes spec's first and second landings, then this spec's first landing; the vid series' fourth landing, then this spec's second landing.

## Terms

- **Occupant.** The live row standing at a pair's destination when the pair is judged.
- **Replacing pair.** A pair of a `move` or a `copy` called with `replace=True` whose occupant is a live file and whose source is a file.
- **Replaced file.** The occupant of a replacing pair. A replacing move deletes it; a replacing copy writes over it.
- **Replaced rung.** The rung a caller must hold on the replaced file: the rung of the verb the replacement performs on it, `delete` for a move and `write` for a copy.

## What the code does today

| Fact | How it is known |
|---|---|
| `move` and `copy` take `src`, `dest`, `moves` or `copies`, and `authority`. Neither takes `replace=`. | Read, `src/vfs/base.py:1247-1295`, `src/vfs/params.py:262-273`, `src/vfs/storage/protocol.py:246-258`. |
| The transfer ladder refuses any occupant with `exists`, a deleted one included, with the trashed hint where it is deleted. "no transfer replaces an occupant" is written in its docstring. | Read, `src/vfs/storage/backends/database/topology.py:136-146`, `:186-191`, `:276-281`. |
| The ladder runs pair by pair inside one serialized transaction, and later pairs see earlier pairs' effects. The ids an earlier pair moved or made are kept in `own`. | Read, `topology.py:118-160`. |
| A move to a free path is 16 statements as the system actor and 24 as a named caller; a copy 16 and 23; a delete 4 and 10; a write over a file 8 and 15; a move refused `exists` 5 and 15. A batch of 100 file moves is 1,105 statements as the system actor. | Run, a probe on the in-memory store, `BEGIN`, `COMMIT`, `PRAGMA`, `SAVEPOINT`, `RELEASE`, `ROLLBACK` and statistics left out. |
| A move reports its row `created` at the destination at the source's version plus one, and bumps the directory twice when source and destination share it; a copy reports `created` at version 1 and bumps once; a write over a file reports `updated` and bumps no directory. | Run, the same probe. |
| A delete stamps each root by one guarded claim, `_tombstone_roots`, which assigns `deleted_at`, `trash_root_id`, the demoted `encoded` and `version + 1`. | Read, `src/vfs/storage/backends/database/trash.py:433-469`. |
| The gate judges a transfer's destination as a creation (`"create"` mode). A creation at an occupied target the caller may see is judged at the create rung, and one it may not see is judged as a creation at its path; where either passes, the ladder answers `exists`. | Read, `src/vfs/storage/backends/database/backend.py:1410-1444`, `src/vfs/storage/backends/database/rights.py:173`, `:871-948`. |
| `VERB_RUNGS` gives `move` `Needs("read_write", create="add")`, `copy` `Needs("read_write", create="add", passing="read")`, `delete` `read_write` and `write` `contribute`. Two sites already read another verb's rung from the table: restore's at a revive and write's at a landed row. | Read, `src/vfs/ops.py:136-177`, `rights.py:941`, `src/vfs/storage/backends/database/authorized.py:343`. |
| `TraitKey` holds eight keys, and `DatabaseStorage` declares seven of them on every dialect and `durability` on the tuned ones. | Read, `protocol.py:78-99`, `backend.py:240-253`. |
| `base.py` holds 3,090 lines and `rights.py` 1,539, each exactly its entry in `MODULE_LINE_BASELINE`; a module over 1,000 lines that grows fails the lint. | Read, `tests/lint/allowlist.py:26-33`, `tests/lint/test_code_shape.py:76`. |
| `base.py` imports `dataclasses.replace` and calls it once, in `update_mount`. | Read, `base.py:51`, `:530`. |

## The problem

An agent that writes a file under a working name and renames it into place, and a pipeline that stages a file and swaps it in, both meet `exists` today. The way around is a `delete` and then the `move`: two calls, two transactions, and a window in which the destination holds nothing. The shell holds the same refusal for `mv` and `cp` onto an occupied file, by decision 3 of [the shell file operations spec](../2026-11-22-shell-file-operations/spec.md), because the kernel has no argument to map `-f` onto.

The argument could not be built before the deletes spec, because a deleted row holds its path, so a replaced file had nowhere to go but out of existence, which the roadmap's promise that every delete is reversible forbids. The deletes spec frees the name. What is left is the argument, its rights, its answers, and one gap the vid series leaves: once a move can replace, the destination is something a call would replace, and the vid series' own reason for giving the destination no precondition no longer holds.

At the reference deployment, transfers are a share of the 1,050,000 file writes a day, and the nightly batch moves 10,000 files a call. A replacement that cost more than a bounded statement a pair, or that left an unbounded trail, would be paid there.

## Decisions

### 1. `move` and `copy` take `replace: bool = False`, keyword-only, on every face

```python
async def move(self, src=None, dest=None, moves=None, *, replace: bool = False, authority=None) -> Result: ...
async def copy(self, src=None, dest=None, copies=None, *, replace: bool = False, authority=None) -> Result: ...
```

- `AsyncVirtualFileSystem`, `VirtualFileSystem`, `AsyncSession` and `Session` carry it, before `authority`, and the parity tests hold the four alike.
- `PARAMS` gains one row on each verb: `ParamSpec("replace", "bool", nullable=False, default=False, doc="land on an occupied file: a move deletes it, restorably; a copy writes over it")`. A value that is not a bool is `invalid` before any storage is called.
- The seam gains it: `StorageBackend.move(*, operations, replace: bool = False, authority=None)` and the same on `copy`. The kernel passes `replace=True` to a storage only when the call asks for it, so a storage that never declared the trait of decision 9 never receives the argument.
- `replace` applies to every pair of a batch. No pair has a flag of its own.
- The parameter shadows the `dataclasses.replace` import inside `move`, `copy` and the routing helpers they call; none of them calls it, and the import stays.

Reason: decision 7 of the rulings, default refuse. A per-pair flag would add a pair shape the parameter table does not have. Precedent: `if_absent` and `parents` on `write`, which apply to the whole call (`src/vfs/params.py:199-201`).

### 2. `replace=True` replaces a file with a file, and nothing else

A pair whose occupant is a live file and whose source is a file is a replacing pair. Every other occupied pair answers exactly what it answers without `replace=True`: `exists` at the destination, with no statement run for the pair. That covers a directory over a directory, a file over a directory and a directory over a file. A destination that holds only deleted rows is free by the deletes spec's decision 4, and the pair is a plain transfer. A pair whose destination is its source is unchanged, as today (`topology.py:178-180`).

Reason: the rulings' Scope refuses a directory over a directory until a spec rules otherwise, and the deletes spec's decision 14 refuses a directory at the destination. A directory source over a file is the third case, and one rule ("replace applies to files") is the simplest to state and to test. It departs from the source spec, which answered a file over a directory and a directory over a file with `wrong_kind`; `exists` is the answer each of those pairs already gets, so no answer changes. Choice 2.

### 3. A replacing move deletes the occupant where it stands, and the moved file keeps its identity

For a replacing pair of a `move`, after the ladder of decision 6 has passed and before the move's root claim (`topology.py:299-358`):

- The occupant is stamped by trash.py's root stamp, `_tombstone_roots`, renamed `tombstone_roots` and called from `topology.py`, with the one claim `(occupant entry_id, occupant version)`. It becomes a deleted row, its own root, at its own path, at its version plus one, with the generation of the deletes spec's decision 3.
- The move's root claim and descendant rewrite then run as for a free destination. The moved row keeps its `entry_id`, its edges, its version history and its owner, takes the destination's path and the destination's label, and stands at its version plus one.
- The replaced file keeps its edges, its version rows, its postings and its body. It is the newest deleted row at the path, shown at `/.vfs/trash/<dest>` and restored by `restore(dest)` once the path is free, by the deletes spec's decisions 9 and 10.
- The row the call returns for the pair is the moved row at the destination, status `created`, as a move to a free path returns. The replaced file is not reported in the result. Choice 3.

Reason: the rulings' decision 6 and the deletes spec's decision 14, which this applies without change. A guard miss on the stamp, a rival write to the occupant inside the window, raises `StaleSnapshot` and the verb redrives from a fresh snapshot, as every claim of a serialized verb does (`trash.py:444-448`). The result row follows POSIX `rename(2)`, which reports nothing of what it replaced, and the rule that a `Result` pairs rows by path alone (`src/vfs/results/envelope.py:524-548`), under which a second row at the destination's path would be merged into the first.

### 4. A replacing copy writes the source's file onto the occupant's row

For a replacing pair of a `copy`, the occupant's row is updated in place, inside the copy's transaction:

- **What stays.** `entry_id`, `owner_id`, `created_at`, `path`, `parent_id`, `everyone_level`, edges and postings.
- **What is written.** The source's material: the columns a plain copy carries (`_COPIED_COLUMNS`, `topology.py:92-108`) less `ext`, which stays the destination's, and `size_bytes`, so the source's rendering is carried and not redone, as a plain copy carries it. The index flags are reset as a write resets them: `chunked` false, `encoded` by `encoded_at_creation`, `indexable` false (`writes.py:1308-1341`). `version` rises by one and `updated_at` is the call's time.
- **The guard.** The update is one claim guarded on the occupant's `entry_id`, its version and `deleted_at IS NULL`, through `serialized.claim` (`src/vfs/storage/backends/database/serialized.py:125-152`); a miss redrives.
- **The old body.** It is kept as one version row by `versions.mint_versions`, the call a write over a file makes (`writes.py:543-550`), given the occupant's id and the version it replaced.
- **The new body.** The occupant's rows in both body tables are deleted and the source's body inserted under the occupant's id, in the copy's bytes-bounded body pass, `_copy_bodies` (`topology.py:527-562`), whose read of the source stays guarded on the source's version and hash.
- **The same body.** A pair whose occupant already holds the source's body (equal `content_hash`, `source` and `mime_type`, the test a write's settle makes, `staging.py:549`) is reported `unchanged` at the occupant's version, and no write is issued for it.
- The pair's row is the occupant at its path, status `updated`, at its new version.

Reason: the rulings' decision 6. A write over a file keeps its owner (`writes.py:1308-1316`), keeps the replaced body as a version and reports `updated`, so a replacing copy does the same. Carrying the rendering follows the plain copy, which never re-renders a body it copied. Reporting `unchanged` for the same body is what makes a replacing copy sent twice a no-op, decision 11.

### 5. The replaced file is judged at the replaced rung, and a hidden occupant answers as it does without `replace=`

- `Needs` gains a fourth field, `replaced: Rung | None = None`. `VERB_RUNGS["move"]` becomes `Needs("read_write", create="add", replaced="read_write")` and `VERB_RUNGS["copy"]` `Needs("read_write", create="add", passing="read", replaced="contribute")`. A test holds each equal to `VERB_RUNGS["delete"].primary` and `VERB_RUNGS["write"].primary`.
- `GateMode` gains `"replace"`. Under `replace=True` the transfer gate judges every destination in that mode in place of `"create"` (`backend.py:1424-1426`). In `_decide`, an occupied target the caller may see is judged at `needs.replaced`, with the owner floor riding, where it is a file, and at `needs.create`, as today, where it is a directory. A target that holds no live row is judged as a creation. `_lowest` gives anonymous the replaced rung at an occupied file.
- An occupant the caller may not see is judged as a creation at its path, as today: where the caller may not create there, the gate's refusal is the one a call without `replace=True` gets; where it may, the ladder answers `exists` with no data, again that call's answer, and replaces nothing, since step 3 of decision 6 asks the caller's rights at `list` on the occupant before anything else.
- The ladder admits the occupant at `needs.replaced` again, through `admit(judging(session, ...))`, so a rights change committed inside the window redrives, as for every row a transfer finds (`authorized.py:271-276`).
- An owner may replace its own file at any level, through the owner floor, as it may delete or overwrite it.

Reason: the replaced file undergoes a delete or a write, so it is judged at that verb's rung, as the deletes spec's decision 14 says for a move and the source spec said for a copy ("judged as `write` judges an occupied target"). A field of `Needs` keeps the one verb-to-rung table the only place a rung is written (`src/vfs/ops.py:178-188`). A hidden occupant must not be told apart from what the call without `replace=` reveals, which is `exists` and no more.

### 6. The ladder of a replacing pair, in order

After the source is found live, the root and rename-to-self arms and the destination's parent, as today (`topology.py:166-186`), the occupant step reads:

- **Step 1.** No live occupant: a plain transfer.
- **Step 2.** The occupant or the source is a directory: `exists`, decision 2.
- **Step 3.** The caller may not `list` the occupant: `exists`, with no data, decision 5.
- **Step 4.** The occupant's `entry_id` is in `own`: `invalid` at the destination, "the destination holds a file this call already moved or made there", decision 7.
- **Step 5.** A key of `if_vids` names the destination: decision 10, from the second landing.
- **Step 6.** The replacement, decision 3 or 4.

Without `replace=True` the step is today's single arm: any occupant is `exists`.

Reason: kind and visibility come first, so that no answer to a replacing pair says more than the same pair without the flag. The `own` rule comes before the precondition because it is a fault of the call's shape, which no vid can mend.

### 7. A pair never replaces a file the same call moved or made

A replacing pair whose occupant is a row an earlier pair of the same call moved, minted or wrote over is `invalid`, and the batch fails whole, as any per-pair refusal makes it fail. A replacing copy adds the occupant's id to `own`, as a plain copy adds the ids it mints. Otherwise pairs run in order, and a later pair sees what an earlier one did: `moves=[("/a", "/b"), ("/b", "/c")]` with `/b` and `/c` occupied replaces `/b` with `/a`, then moves that file on to `/c`, replacing `/c`.

Reason: `moves=[("/a", "/b"), ("/c", "/b")]` would otherwise delete the file the call put at `/b` a pair earlier, a loss no caller asks for in one call. `own` already holds exactly those ids (`topology.py:159-160`), so the rule costs no statement. Pair order is the ladder's rule today, and two calls in sequence give the same end state as the batch.

### 8. A replacing pair bumps the parents a plain transfer of its kind bumps, and no more

A replacing move bumps the source's parent and the destination's parent, as a move does (`topology.py:355-358`); the occupant's stamp adds no bump. A replacing copy bumps no directory, as a write over a file bumps none; an `unchanged` pair bumps nothing.

Reason: a directory's version moves when its listing changes. A replacing move changes the destination directory's listing once, and the move's bump already records it. A replacing copy changes no listing.

### 9. A storage declares the `transfer_replace` trait, and a mount without it refuses `replace=True`

- `TraitKey` gains `transfer_replace`, with one value, `undoable`: the storage replaces a file at a transfer's destination as decisions 2 to 8 say, and a replaced file stays restorable.
- `DatabaseStorage` declares it on every dialect, the generic floor included, since nothing here is engine-specific. `SQLiteStorage`, `PostgresStorage` and `InMemoryStorage` are that class.
- A call with `replace=True` to a mount whose storage does not declare it is refused `unsupported` at the mount's path, "the storage mounted here cannot replace a file at a transfer's destination", before that mount's storage is called. The check runs per mount in `_route_two_path` (`base.py:2322-2383`), after the cross-mount and `busy` checks.

Reason: Article 2 and Article 4 of the constitution require a capability to be declared and readable without running the verb, and a storage that silently ignored the flag would answer `exists` to a caller who asked for a replacement. Precedent: the vid trait of the vid spec's decision 13 and the `listing_cursor` trait (`protocol.py:98`).

### 10. A replacing pair's destination may be required by its vid, through `if_vids` keyed by the destination

This is the second landing, after the vid series' fourth.

- **`move`.** Under `replace=True`, a key of `if_vids` may name the destination of a pair in `moves`, beside the keys that name sources. `if_vid` names the source, as the series has it; the single form states no destination. A caller that must require the destination of one pair passes `moves=[(src, dest)]`.
- **`copy`.** `copy` gains `if_vids: Mapping[str, Vid | Literal["absent"]] | None = None` on the two file system faces and the seam, and a `PARAMS` row of kind `vids`, and no `if_vid`. Its keys name destinations of pairs in `copies`. `AsyncSession` and `Session` carry neither, by the series' decision 14.
- **At the gate,** each refused `invalid` before any storage is called. A destination key without `replace=True`: on `move` the series' words, "each key of if_vids must be the path of a source in moves"; on `copy`, "copy takes if_vids only with replace=True: a copy without it lands only on a free path". A key that names a path that is both a source and a destination of the call: "if_vids names a path that is both a source and a destination". `copy` with `if_vids` beside `src` and `dest`: "copy takes if_vids with copies". Keys are resolved and routed by the series' `routed_vids` (`origin/delete-move-and-restore-require-a-vid:src/vfs/preconditions.py:87`), and a mount without the `vid` trait is `unsupported`, as the series refuses it.
- **In the ladder,** at step 5 of decision 6, the answers:

| What stands at the keyed destination | Key is a vid | Key is `ABSENT` |
|---|---|---|
| A live file whose vid is the key, the caller admitted | the replacement runs | `exists`, with the occupant's version, `content_hash` and vid |
| A live file with another vid, the caller admitted | `conflict` by `stale_vid`, with the occupant's version and vid; nothing changes | `exists`, as above |
| No live row | `not_found` at the destination, with the trashed hint where a deleted row the caller may list lies there | a plain transfer |

- A directory, and an occupant the caller may not see, answer at steps 2 and 3, before the key is read: `exists`, and for a hidden occupant with no data.
- A pair whose destination has no key is replaced whatever its version, last writer wins, and the docstring says so.

Reason: the vid spec's decision 11 gave the destination no precondition because "a precondition protects what a call would replace" and a move replaced nothing there; under `replace=True` it does, so the same reason gives the destination one. A key in `if_vids` adds no argument name and reaches the storage in the shape it already takes, a mapping of paths to vids (the series' decision 6). `ABSENT` at a destination asks that nothing be there, which is the create-only answer of a write, `exists` (the series' decision 18). Article 5 of the constitution asks each write to declare its conflict mode, and the docstring does. The spelling is choice 1.

### 11. A replacing transfer sent twice changes nothing the second time

- `move(src, dest, replace=True)` sent twice: the second call finds no live source and answers `not_found` at `src`, as the plain form does, with the same `data` the plain form's row names. Its ladder stops at the source, so no second occupant is read or deleted. The moved file stands at `dest` with the same `entry_id`, which is the replay rule the rulings' decision 6 keeps, and which unit 177-1's decision 11 reports as `data["dest"]` once it is built.
- `copy(src, dest, replace=True)` sent twice: the second call finds the source's body at the destination and answers `unchanged`, decision 4, at the version the first call left.

Where unit 177-1 has landed first, this spec's first landing adds the form `replace` to `REPLAY["move"]`, with the plain form's answer, and to `REPLAY["copy"]`, as `ReplayAnswer("replace", status="unchanged")`, and adds a driver for each to `DRIVERS` in `tests/support/replay_contract.py`, by that spec's decision 14. Where this spec lands first, the two forms are served on `dev` when unit 177-1 is built, and that spec's table holds them.

Reason: a caller that lost a reply resends, and a resend must not delete a second file or mint a second version.

### 12. A replacing cross-mount copy is a write without `if_absent`

Where unit 160-1 is built, a `copy` across mounts with `replace=True` writes the source's body at the destination without `if_absent`, which keeps the destination's identity and its old body as a version, and a destination key of `if_vids` is passed to that write as its key. A `move` across mounts stays `cross_mount`, with or without the flag. Until unit 160-1 is built, every cross-mount pair is `cross_mount`, as today (`base.py:2367-2369`).

Reason: the rulings' decision 6 gives a replacing copy the meaning of a write, so the same call gives the same answer on one mount and across two. Unit 160-1's Left as it is says the same.

### 13. Where this spec leaves Plan 9 and Unix it says so

| The principle | What vfs does | The constraint | Ends |
|---|---|---|---|
| Plan 9's `wstat` refuses a new name that exists; Unix `rename(2)` replaces a file. | A transfer refuses by default, as Plan 9 does, and replaces a file under `replace=True`, as `rename(2)` does. | The rulings' decision 7: no verb removes a file unless asked to. | Followed, not departed from. |
| `rename(2)` unlinks the file it replaces. | The replaced file is kept as a deleted row, restorable, until it is destroyed. | The roadmap's promise that every delete is reversible. Inherited, by the rulings' decision 6. | Never. |
| `rename(2)` replaces an empty directory with a directory. | `exists`, decision 2. | The rulings' Scope and the deletes spec's decision 14. | When a spec rules on replacing a directory. |
| `rename(2)` answers `ENOTDIR` or `EISDIR` for a directory over a file and a file over a directory. | `exists`, decision 2. | One answer for every pair `replace` does not apply to, the answer each already gets. | Choice 2. |
| `cp` over a file truncates and writes into the same inode. | The same: the destination keeps its `entry_id`, decision 4. | | Followed. |

Reason: Article 3 of the constitution asks that each departure be a numbered decision naming the principle, the deviation, the constraint and when it ends.

### 14. Two landings, in this order

- **Landing 1, `replace=`.** Decisions 1 to 9 and 11 to 13: the argument on the four faces, the parameter table and the seam; the two ladders; `Needs.replaced` and the gate mode; the trait; the docstrings. It lands after the deletes spec's second landing.
- **Landing 2, the destination's vid.** Decision 10. It lands after the vid series' fourth landing and after this spec's first.

Each is green under `scripts/ci.sh` and under `scripts/docs.sh check`, since each changes a docstring. The Postgres leg runs before the pull request of each.

Reason: the first landing needs only the free name, and the vid series is on open branches whose merge order is its own. Splitting keeps the argument from waiting on the series, and the series from waiting on the argument.

### 15. The code goes where there is room, and two baselines are set to the count the build reaches

The ladder, the occupant arms and the `own` rule go in `topology.py` (565 lines), the stamp's rename in `trash.py` (668), `replaced` in `ops.py` (220), and the parameter rows in `params.py` (739). `base.py` gains two signature lines, the per-mount trait check and two docstring sentences on each verb, and `rights.py` the mode in `_slot`, `_lowest` and `_decide`; each baseline in `tests/lint/allowlist.py` is set to the count the build reaches, and the pull request names both counts.

Reason: neither change can be moved out of its module without moving the verb or the gate it extends. Precedent: the vid series set five baselines the same way (`origin/delete-move-and-restore-require-a-vid:tests/lint/allowlist.py`, `base.py` from 3,090 to 3,181).

## Cost

Costed against the reference deployment in `AGENTS.md`, on SQLite and Postgres.

**Per pair.** A replacing move pair issues the statements of the same move to a free path, plus one: the occupant's stamp, one guarded `UPDATE` by primary key through `claim_rows`, which chunks by the parameter budget and the membership budget as every claim does (`serialized.py:155-215`). The gate reads no new row: the occupant is among the rows `targets` already fetches for the destination (`rights.py:740-743`). A replacing copy pair trades the plain copy's row insert, posting insert, edge insert and parent bump for one guarded `UPDATE`, the version mint and the deletes of the occupant's body rows; its budget is two statements more than the same copy to a free path, and the test of decision 4 pins it. An `unchanged` copy pair issues none.

**Per batch, 100 a night.** A 10,000-pair move issues about 110,500 statements today, about 11 a pair (1,105 for 100 pairs, measured), because the transfer ladder reads each pair live. Replacing every pair adds 10,000, about 9%. No statement's size grows with the batch: the stamp names one row, and every body page stays under `BLOB_PAGE_BYTES`.

**Per file write, about 1,050,000 a day.** A transfer is one kind of write. A replacing pair adds one bounded statement on a row by primary key, uncontended but for a rival write to the same occupant, which redrives.

**Per verb call and per index visit.** Nothing is added to a read, and the index passes see a replaced file as they see a deleted one.

**Per lock.** A transfer holds the mount's serialization point from its first statement to its commit (`topology.py:148`), as delete, restore and sweep do; no read and no write takes it (`tests/storage/database/test_topology.py:163-186`). A replacing pair adds one statement to that body. Holding the point for the commit alone is [the topology lock spec](../2026-11-21-the-topology-lock-is-held-for-a-commit/spec.md)'s work and is not changed here.

**What grows with use.** Each replacing move leaves one deleted row, with its body and derived rows, until it is destroyed, as a delete does. A pipeline that swaps 1,000,000 files a night by `move(replace=True)` would stand 90,000,000 deleted rows at a 90-day retention. A write over a file leaves one version row instead and keeps the file's identity, so the docstring of `move` says that a pipeline replacing a file's body writes over it, or copies over it, and moves over it only when the moved file's identity is the point. No cap is set.

## Left as it is

- **The shell.** `mv -f` and `cp -f` onto an occupied file keep the refusal until unit 167-8 maps them onto `replace=True`.
- **Replacing a directory.** Refused `exists`, decision 2, until a spec rules on it.
- **The transfer ladder's statement per pair.** It reads each pair live today. A set-based ladder would bound a batch by its chunks and is a spec of its own; decision 7 and the rule that later pairs see earlier ones would carry over.
- **A session's destination key.** How a session fills the key of decision 10 for a destination it read is the session spec's, [the session remembers what it read](../2026-11-22-the-session-remembers-what-it-read/spec.md).
- **`destroy`.** The deletes spec's third landing. A replaced file is destroyed as any deleted row is.
- **The replay table.** Unit 177-1's; decision 11 says what it holds for the two forms, and who writes them.

## Tests

Each is written and seen failing before the code. Counts are of rows, errors, statements recorded by a `before_cursor_execute` listener, or calls to a spied function; never time. A test of `tests/support/storage_contract.py` or `tests/support/grants_contract.py` runs on the in-memory store, on SQLite and on the Postgres leg, through `TestMemoryConformance`, `TestSqliteConformance` and `TestPostgresConformance` in `tests/storage/test_conformance.py`.

**Landing 1.** `tests/support/storage_contract.py`, `StorageContract`:

- `test_a_replacing_move_keeps_the_moved_entry_at_the_destination`: `/a.txt` and `/b.txt` written; `move(/a.txt, /b.txt, replace=True)` returns 1 row, status `created`, whose `entry_id` is `/a.txt`'s and whose version is its version plus 1; `/a.txt` is `not_found`; `/b.txt` reads `/a.txt`'s body; `/.vfs/trash/b.txt` stats 1 row carrying the old `/b.txt`'s `entry_id` and `deleted_at`.
- `test_a_replaced_file_is_restored_once_its_path_is_free`: after that move, `restore(/b.txt)` is 1 `exists`; after `/b.txt` is moved to `/c.txt`, `restore(/b.txt)` returns 1 row with the old `entry_id` and body.
- `test_replace_onto_a_free_destination_is_a_plain_transfer`: for `move` and `copy`, the row returned equals the one the same call without the flag returns, and 0 deleted rows exist.
- `test_replace_refuses_every_pair_with_a_directory_on_either_side`: 6 cases, directory over directory, file over directory and directory over file, for `move` and `copy`; each is 1 `exists`; the versions of both rows are unchanged and 0 deleted rows exist. The existing `test_move_dir_over_empty_dir_is_exists` and its neighbours stay as they are, without the flag.
- `test_a_replacing_move_onto_itself_is_unchanged`: 1 row, status `unchanged`, 0 deleted rows.
- `test_a_replacing_copy_keeps_the_destinations_identity`: `/b.txt` keeps its `entry_id`, `owner_id` and `created_at`, rises by 1 version, reads `/a.txt`'s body, and is reported `updated`; `/a.txt` is unchanged.
- `test_a_replacing_copy_of_the_same_body_is_unchanged`: 1 row `unchanged`, the version is the same before and after.
- `test_a_batch_never_replaces_a_file_it_moved_or_made`: `moves=[(a, b), (c, b)]` and `copies=[(a, b), (c, b)]`, each with `replace=True`, are each 1 `invalid` at `b`, and 0 rows change.
- `test_a_replacing_batch_runs_in_pair_order`: `moves=[(a, b), (b, c)]` with `b` and `c` occupied leaves `a`'s `entry_id` at `c`, 0 live rows at `a` and `b`, and 2 deleted rows, the old `b` and the old `c`.
- `test_a_replacing_move_sent_twice_deletes_one_file`: the second call is 1 `not_found` at the source; 1 deleted row stands at the destination.
- `test_a_replacing_copy_sent_twice_is_unchanged`: the second row is `unchanged` at the version the first left.
- Where unit 177-1 has landed first: `tests/support/replay_contract.py::ReplayContract::test_each_form_sent_twice_answers_as_its_row_says[move-replace]` and `[copy-replace]`, and that spec's `test_every_replay_form_has_a_driver` holds the two new drivers.
- `test_a_replacing_move_bumps_the_parents_a_move_bumps`: across two directories, each parent rises by exactly 1; within one, by exactly 2; a replacing copy leaves its parent's version unchanged.
- `test_a_replacing_file_move_costs_one_statement_more_than_a_move_to_a_free_path`: as the system actor and as a named caller, the difference is exactly 1.
- `test_a_replacing_file_copy_costs_at_most_two_statements_more_than_a_copy_to_a_free_path`: as the system actor and as a named caller.
- `test_the_replace_trait_is_declared`: `traits()["transfer_replace"] == "undoable"`. The existing `test_declared_traits_stay_within_the_vocabulary` holds the value in the vocabulary.

`tests/support/grants_contract.py`, `GrantsContract`, the leak tests among them:

- `test_a_replacing_move_needs_delete_rights_on_the_file_it_replaces`: a caller holding `read_write` on the source and `add` where another caller's file is the occupant is 1 `permission_denied` at the destination, and 0 rows change; the occupant's owner, at `add`, replaces it.
- `test_a_replacing_copy_needs_write_rights_on_the_file_it_replaces`: at `add` over another's file, 1 `permission_denied`; at `contribute`, 1 row `updated`.
- `test_a_hidden_occupant_answers_as_it_does_without_replace`: a caller that may not list the occupant gets, with and without the flag, 1 refusal of equal kind, detail and data, carrying none of the occupant's version, hash or vid; the occupant's version is unchanged and 0 deleted rows exist; for `move` and `copy`, under a posture that hides the occupant and under another caller's ownership with no grant.
- `test_anonymous_is_judged_at_the_replaced_rung`: under a posture where anonymous may create and not delete, a replacing move by anonymous is 1 `unauthenticated` at the destination, and a move to a free path succeeds.

`tests/storage/database/test_topology.py`, a new class `TestReplacingTransfers`:

- `test_a_replacing_copy_keeps_the_replaced_body_as_one_version_row`: `vfs_versions` holds 1 row for the occupant, at its old version number, with its old body and hash.
- `test_a_replacing_copy_clears_both_body_tables_of_the_occupant`: a bytes occupant replaced by a text source leaves 0 rows in `vfs_blobs` and 1 in `vfs_content` for its id.
- `test_the_replaced_file_and_the_moved_file_keep_their_own_edges`: an authored edge to each; after a replacing move, 2 edge rows, each still on its own `entry_id`.
- `test_a_thousand_replacing_pairs_cost_a_thousand_statements_more`, marked `slow`: 1,000 file pairs onto 1,000 occupants against the same pairs onto free paths, a difference of exactly 1,000 statements.

`tests/storage/database/test_races.py`:

- `test_a_write_to_the_occupant_inside_a_replacing_moves_window_redrives`: a rival write to the occupant committed at the seam `transfer:post-collect`; 2 attempts; the moved file stands at the destination, and the newest deleted row there holds the rival's body.
- `test_a_rival_create_at_a_free_destination_is_replaced_and_kept`: a rival create at the seam `transfer:post-snapshot`; 2 attempts; 1 live row, the moved file, and 1 deleted row holding the rival's body.
- The same two on Postgres: `tests/storage/test_conformance.py::TestPostgresTopologyRivals`, under the same names.

`tests/base/test_dispatch.py`:

- `test_replace_reaches_the_storage_only_when_true`: a recording double receives no `replace` keyword for a call without the flag and `replace=True` for one with it.
- `test_a_storage_without_the_replace_trait_is_unsupported_and_never_called`: 1 `unsupported` at the mount's path, 0 storage calls.
- `test_a_replacing_move_across_mounts_is_cross_mount`: 1 `cross_mount`, 0 storage calls.

`tests/test_params.py`: `test_every_verb_signature_matches_the_table` holds the two new rows, and `test_garbage_classifies_invalid_with_zero_dispatch` gains `move` and `copy` with `replace="yes"`, each 1 `invalid` and 0 dispatches.

`tests/test_ops.py`: `test_the_replaced_rung_is_the_rung_of_the_verb_the_replacement_performs`: `VERB_RUNGS["move"].replaced == VERB_RUNGS["delete"].primary`, `VERB_RUNGS["copy"].replaced == VERB_RUNGS["write"].primary`, and every other verb's `replaced` is `None`.

`tests/test_sync.py`: `test_every_router_coroutine_has_a_sync_twin` and `test_every_session_coroutine_has_a_sync_twin` hold the four faces alike, unchanged.

**Landing 2.** In the vid series' contract module, `tests/support/vid_contract.py` (added by the series, not on `dev`):

- `test_a_replacing_pair_requires_its_destination_by_key`: for `move` and `copy`, each of the six cells of decision 10's table, with its answer and the count of rows changed (1 where the replacement runs, 0 elsewhere).
- `test_a_destination_key_over_a_directory_is_exists_before_the_key`: 1 `exists`, 0 rows changed.

`tests/support/grants_contract.py`: `test_a_destination_key_over_a_hidden_occupant_answers_exists_without_data`: with a vid key and with `ABSENT`, 1 `exists` whose `data` is empty, for `move` and `copy`.

`tests/base/test_dispatch.py`: `test_a_destination_key_is_refused_without_replace`, `test_a_key_that_names_a_source_and_a_destination_is_invalid` and `test_copy_takes_if_vids_with_copies_only`: each 1 `invalid` with decision 10's words and 0 storage calls.

`tests/test_params.py`: `test_every_verb_signature_matches_the_table` holds copy's `if_vids` row of kind `vids`.

## Scope

In:

- `src/vfs/base.py`: `replace` on `move` and `copy`, carried through `_route_pairs` and `_route_two_path`, the per-mount trait check, and, in landing 2, `if_vids` on `copy` and the destination keys. `src/vfs/session.py`, `src/vfs/sync.py`, `src/vfs/sync_session.py`: the argument on the other three faces.
- `src/vfs/params.py`: the `replace` rows, and in landing 2 copy's `if_vids` row and form rule. `src/vfs/ops.py`: `Needs.replaced` and its two values, and the two `replace` forms of `REPLAY` where unit 177-1 has landed first.
- `src/vfs/storage/protocol.py`: the argument on the seam, `transfer_replace` in `TraitKey` and `TRAIT_VALUES`, and in landing 2 `if_vids` on `copy`.
- `src/vfs/storage/backends/database/`: `backend.py` (the trait, the argument, the gate mode in `_execute_transfer`), `topology.py` (the ladder, the two arms, the `own` rule, the docstrings that say no transfer replaces), `trash.py` (`tombstone_roots`), `rights.py` (the `"replace"` mode), `versions.py` (called as it is).
- The tests above. `tests/lint/allowlist.py`: the two baselines of decision 15.
- The docs below.

Out: the shell's `mv -f` and `cp -f` (unit 167-8); the cross-mount copy (unit 160-1); the replay table (unit 177-1); replacing a directory; `destroy` and the trash design (the deletes spec); the vid series itself; the topology lock's hold; a set-based transfer ladder; `crates/`.

## What the docs must say

- `move` and `copy` refuse an occupied destination unless `replace=True` is passed. `replace=True` replaces a file with a file; a directory on either side is `exists`.
- A replacing move keeps the moved file, its id, its edges and its history. The replaced file is deleted, not destroyed: it is in the trash at the destination's path, and `restore` brings it back once the path is free.
- A replacing copy writes the source's body over the destination, which keeps its id and owner and keeps its old body as a version. A copy of a body the destination already holds is `unchanged`.
- Replacing needs the rights of the act on the replaced file: what a `delete` of it needs for a move, and what a `write` over it needs for a copy.
- A replacement with no key for the destination replaces whatever version is there, last writer wins; from landing 2, `if_vids={dest: vid}` replaces only the file that was read, and is `conflict` where it moved on.
- A pipeline that replaces a file's body writes over it or copies over it; each `move(replace=True)` leaves the replaced file in the trash until it is destroyed.

Pages, each changed: the docstrings of `move` and `copy` on `AsyncVirtualFileSystem`, which are the reference pages of the four faces; `documentation/reference/access-levels.md`, two rows, "`move` with `replace=True` onto the file" (Permission denied at each level below `read_write`, Yes at `read_write`) and "`copy` with `replace=True` over the file" (the row of "`write` over the file"); `documentation/reference/planned-api/vids-and-preconditions.md`, the sentence "The destination takes no precondition", where the page still stands when landing 2 lands; `context/standards/roadmap.md`, the *State* line of story F4 once each landing is built.

## Earlier decisions this reverses

- Numbered spec 167, `context/specifications/archive/167-the-shell-pipeline-core/spec.md`: "A file over a directory, or a directory over a file, is `wrong_kind`" becomes `exists` (decision 2), and "An occupied destination under `overwrite=True` is judged as `write` judges an occupied target" holds for `copy` alone; a move's occupant is judged at delete's rung (decision 5). Its flag name and identity rule were already replaced by the rulings' decisions 6 and 7.
- The vid spec, decision 11: "its destination takes no precondition" holds without `replace=True`; under it, the destination takes a key of `if_vids` (decision 10). Its gate rule that each key of `if_vids` names "a source in moves" gains the destinations of a replacing call.
- The transfer ladder's docstrings, `topology.py:12-21` and `:136-146`, and the comments of the contract's exists tests, which say no transfer replaces an occupant: they hold without `replace=True`.

## Not checked

- Nothing was run on Postgres. The engine leg of each landing is the check.
- The deletes spec and the vid series are not built on `dev`, so the stamp beside the generation key, the moved row's claim at a path that holds a deleted row, and the destination key were read from those specs and branches, not run. The branch code cited was read at `origin/delete-move-and-restore-require-a-vid`, last commit `b00ab57b`.
- The statement budgets of the replacing pairs (one more for a move, at most two more for a copy) are derived from the code, not measured: the arms are not built.
- Today's answer to a transfer onto an occupant the caller may not list was read in the code (`rights.py:943-948`, `topology.py:186-191`), not run.
- The generic floor. No engine runs it; the trait is declared there on the reading that nothing in the two arms is engine-specific.
- Whether the in-memory store's statement counts match a SQLite file's and Postgres's for the transfer verbs. The counts under "What the code does today" are the in-memory store's.
- How a session fills the destination key, and whether a strict session refuses a replacement of a file it never read: the session spec's.

## Choices to confirm

1. **Where the destination's vid is spelled** (decision 10). Taken: a key of `if_vids` alone, on `move` and on `copy`, with no single-form spelling, because it adds no argument name and the storage already takes that mapping. The other options: an `if_dest_vid` keyword on both single forms, which adds a name; or no destination requirement at all, which leaves every replacement last writer wins against the vid spec's own reason. A single-form spelling can be added later without changing a caller.
2. **A directory over a file is `exists`** (decision 2). Taken: `exists`, one answer for every pair `replace` does not apply to, which is the answer each such pair gets today. The other: `wrong_kind` for a directory over a file and a file over a directory, as the source spec had it and as `ENOTDIR` and `EISDIR` read.
3. **The replaced file is not in the result** (decision 3). Taken: one row a pair, the moved file, as `rename(2)` reports nothing of what it replaced and as a `Result` pairs rows by path. The other: a second row for the replaced file at its trash path, status `deleted`, so a caller can hand it to `restore` without a listing. Appending that row later leaves the first row as it is.

## One line

`move` and `copy` take `replace=True`, which lets a file land on a file: a move keeps the moved file and leaves the replaced one restorable in the trash, a copy writes over the destination and keeps its identity, a directory on either side stays `exists`, the replaced file is judged at the rung of the act done to it, and once the vid series lands the destination can be required by its vid.
