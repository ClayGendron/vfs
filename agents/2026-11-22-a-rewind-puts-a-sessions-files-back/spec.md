# A rewind puts a session's files back as they were before a turn

A draft, written on 2026-11-22. It is not reviewed, and nothing is built. It replaces the short draft that stood at this path, whose eight decisions were leanings. It rests on the map in `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md`, on the two guides under `documentation/how-to/`, on three studies under `agents/2026-11-22-a-session-is-stored-named-and-forked/research/` (`coding-agent-sessions.md`, `forking-files.md`, `framework-session-stores.md`), and on the tree read at `af8ee869`. Every fact under "What the code does today" marked "Run" was run that day on a SQLite file. Specs 0, 1, 2, 3, 4, 6 and 7 were read as drafts of the same day, none of them reviewed, and spec 3 only in part. Spec 8 was not read. The feature is wanted for 0.1.0.

## The outcome wanted

A session works through turns `msg_4`, `msg_5` and `msg_6`, and changes files in each. A rewind to before `msg_5` that asks for the files puts every file the session changed in `msg_5` and `msg_6` back as it was when `msg_4` ended. A file somebody else changed in the meantime is left as it is and reported, never overwritten. Nothing is destroyed: a body put back is a new version, a file taken away goes to the trash, and the rollback's own changes are recorded.

```python
scout.rewind(before="msg_5")                                    # the memory only: spec 4
plan = scout.rewind(before="msg_5", files=True, preview=True)   # what would be put back; nothing changes
done = scout.rewind(before="msg_5", files=True)                 # the files, then the memory

done.files.observations     # one row for each entry put back
done.files.warnings         # one fact for each entry left as it is, with the reason
```

## Builds on

Each entry gives its state, then what this spec takes from it and what it needs. A need is stated and not designed here.

- **Spec 0, the kernel keeps records of its own.** Drafted, and read.
  - Taken: `KernelStore.record_after`, `query`, `commit` and `insert_rows`; the rule that a record beside a change names its form; the eight rules for a spec that keeps a record.
  - Its decision 10 names the record of what a session changed as a case for its claim-before form. Decision 4 here takes record-after and says why.
- **Spec 1, a row carries an etag and a change can require it.** Drafted, and read.
  - Taken: `Etag`, `ETAG_LENGTH`, `EtagMint`; an etag is minted by the storage and compared, never parsed; `if_match` and `if_matches` on `write`, `edit`, `delete` and `move`; every row a change returns carries the etag after it; a directory is matched by its entry and its version.
  - Need: `restore` takes `if_match` and `if_matches`. Spec 1 leaves `restore` with no precondition. Decision 7 says what goes wrong without it, and landing 4 carries it if spec 1's landings do not.
- **Spec 2, a session is stored, named and forked.** Drafted, and read.
  - Taken: `session_key`, never used twice; an anonymous authority owns no session; `SESSION_CHILDREN` and `SESSION_RECLAIM_CHUNK`.
  - Its need of this spec, a function that deletes at most 5,000 change rows of one `session_key`, is decision 16's `remove_changes`.
- **Spec 3, the session remembers what it read.** Drafted, and read in part: its decisions 8, 13 and 17.
  - Taken: the guarded router, through which every change of a session passes; step 7 of its decision 8, where the stamps a change leaves are stored after the change, and where it says this spec's record belongs; its decision 17, which sends every effect of a shell line through the guarded router.
  - Need: one function that moves the stamp a session holds for a path from one etag to another, only when it holds the first. Decision 14 uses it.
- **Spec 4, a session works in turns and rewinds or forks at one.** Drafted, and read.
  - Taken: `rewind(*, before) -> Rewind`, to which this spec adds `files=`, `preview=` and a field, as its decision 12 says; the hook of its decision 13, after the read that finds the session key and the turn's number `n` and before the transaction that removes the turns; a removed turn's number is never used again; a handle with no turn files a record under the session's latest turn, with `make_first_turn` for an empty session; a fork copies no change row; these methods raise a refusal.
  - Its step R4 asks for this spec's rule for the change rows of removed turns. Decision 16 gives it.
- **Spec 6, a policy judges each step.** Drafted, and read.
  - Need: a step class that is no verb's, called `RewindStep` here, beside its 25. It is a `Mutation`. Its `verb` is `"rewind"`, its `paths` are every path the plan would change, and it carries the turn id.
  - Need: a way to dispatch a verb as part of a step already judged, so that the policies are not asked about it again.
- **Spec 7, a job is interrupted and resumed.** Drafted, and read.
  - Need: a job for a call that is no verb. Its saved step holds the session key, the turn's number and one integer.
  - Need: the interrupt before a `RewindStep` carries decision 12's report as its preview, an eighth beside its seven verbs.
  - Need: `resume` of that job returns the report of decision 11, a `Result`.
  - Taken: a resumed job stays in its turn and what it writes passes through its session; a rewind cancels the waiting jobs of the removed turns.
- **`agents/2026-11-20-write-takes-preconditions-and-an-append/`.** Landed. A write of the body a row holds is `unchanged` and writes nothing. A batch write fails whole on each mount and names every stale row.
- **Trash and restore.** Landed. A delete is a tombstone, and only `sweep` destroys.
- **Roadmap story K8, the history read side.** Not built, gate `f` (`context/standards/roadmap.md:203`). Decision 5 builds the part of its criterion 2 a rollback needs, as a storage method with no public verb.
- **Roadmap story H2, a plan of a change.** Not built (`roadmap.md:325`). The preview in decision 12 does not wait on it and shows no diff.
- **Roadmap story H0, the action log.** Not built (`roadmap.md:300`). The record here is a table of its own.
- **`agents/2026-11-21-an-append-keeps-only-what-it-added/`.** Drafted. It would store a version that is not a whole body. Whichever spec first writes such a row extends decision 5's method.

## Terms

- **Kernel store.** Where the kernel keeps its own records, apart from any mount's tables. Spec 0 owns it.
- **Etag.** Twenty hexadecimal characters that name one entry at one version. Spec 1 owns it.
- **Tombstone.** A deleted row that stays at its path with `deleted_at` set. It reads as absent and holds its path.
- **Change.** One entry's own row changed by one call: it was made, its body was written, it was moved, deleted, restored, or brought back by a write. A row whose path changed because a directory above it moved is not a change of that row.
- **Change row.** One row of `vfs_session_changes`: one change a session made.
- **Log.** A session's change rows in the order of their `id`.
- **Rollback.** The file half of `rewind(before=, files=True)`.
- **Step.** One thing a rollback does to one entry: a write, a move, a delete or a restore.
- **Plan.** The steps a rollback would take and the entries it would leave, worked out from the rows and one read of the files.
- **Segment.** Rows of one entry that an earlier rollback already undid, together with that rollback's own rows for the entry. It needs nothing done.
- **Link.** A row that is in no segment, or a segment.
- **Chain.** One entry's links among the rows a rewind selects, oldest first.
- **Run.** The longest tail of a chain in which each link starts where the one before it ended. It is what the session did to the entry with nobody else in between.
- **Buried.** A link of a chain that is before the run. Somebody else's change lies on top of it.
- **Guard.** The check that an entry is still as the session's last change left it.
- **Holding name.** A name beside a made entry that a rollback moves it to before deleting it, so that its tombstone does not hold a path another step needs.
- **Version row.** A row of `vfs_versions`: a body an entry held, kept when it was replaced.

## What the code does today

Read at `af8ee869`. "Run" means run on 2026-11-22 on a SQLite file, through the public verbs as a named caller. Statement counts leave out `BEGIN`, `COMMIT`, `PRAGMA`, `SAVEPOINT`, `RELEASE` and `ROLLBACK`.

| Fact | How it is known |
|---|---|
| A version row holds the body that was replaced, numbered with the version it was replaced at. | Read, `versions.py:145`. Run: a file written, edited, appended, moved and written again stands at version 6 with version rows 1, 2, 3 and 5. |
| So the body an entry held at version `V` is in the version row with the smallest number at or above `V`, or is the body it holds now. | Run: row 5 holds the body of versions 4 and 5, because the move from 4 to 5 changed no body. |
| A create mints no version row. A body replaced by the same bytes mints none. | Read, `versions.py:11-15`, `:147`. |
| Nothing in `src/` reads a version row. `mint_versions` writes them and the purge deletes them. `Version.reconstruct` is pure and no storage calls it. | Read: `writes.py:88`, `trash.py:606`, `models/version.py:205`. |
| No public verb reads an old body. | Read, the verbs of `base.py:802-1291`. |
| A delete adds one to the named row's version. The rows beneath a deleted directory are tombstoned and keep their versions. A restore adds one to the named row and clears the rest. | Read, `trash.py:459-464`, `:492-496`, `:525-526`, `:543-547`. Run. |
| A delete's result reports the version before the delete. | Read, `trash.py:660-668`. Run: reported 6, stored 7. |
| A move adds one to the moved row's version. The rows beneath a moved directory change path and keep their versions. | Read, `topology.py:326-338`, `:399-403`. Run. |
| A directory's version moves when a child is made, deleted, restored or moved in or out. It does not move when a child's body is written. | Run: 1 to 2 on a child's create, still 2 after the child's update. |
| A move onto a path that a tombstone holds is refused `exists`, with the trashed hint. So is a move onto a live row. | Read, `topology.py:188-191`, `:276-281`. Run. |
| A file moved away, a new file written at its old path and deleted, and the first file cannot be moved back: `exists`. Restoring the new file, moving it aside, deleting it there and moving the first back works, and the first file's body is intact. | Run. |
| A `write` over a tombstone brings the row back with the new body, keeps its entry, and reports `updated`. The replaced body is kept as a version. | Read, `staging.py:81`. Run: tombstone at version 7, live at 8, version row 7 minted, status `updated`. |
| `write(parents=True)` makes the missing directories and reports only the file. `mkdir(parents=True)` reports every directory it made. | Run. |
| A copy mints new entries at version 1 for the whole tree and reports one row for each pair. | Read, `topology.py:486-507`, `:241`. |
| A delete with `cascade=False` of a directory that holds only tombstones succeeds. | Run. |
| `stat` of `/.vfs/trash/<path>` returns the tombstoned row with its version. `stat` of the path itself is `not_found` with the trashed hint. | Run. |
| `delete`, `restore`, `move` and `sweep` are judged at `read_write` or the owner floor; `write` and `edit` at `contribute`. | Read, `ops.py:160-174`. |
| Every change a shell line makes is a public verb called with the line's authority: `write`, `mkdir`, `delete`, `copy` and `move` from the host, and `edit`, `grant`, `revoke`, `mkedge` and `rmedge` from the programs. | Read, `shell/host.py:471-493`, `shell/programs.py:704`, `:715`, `:746`. |
| A session's `cli` hands the router and the authority to the host, so no session sees a line's changes. | Read, `session.py:414-417`, `base.py:1668-1677`. |
| A storage opens and commits its own transaction inside each method. The kernel never holds one. | Read, `base.py:2852-2880`. |
| Through the kernel as a named caller: a one-file `write` issues 15 statements, a `move` 24, a `delete` 10, a `restore` 10, a `stat` 5 and a `read` 3. | Run. |
| The trash sweep destroys a tombstone and its version rows `trash_days` after the delete, 90 by default, or at once when a path is swept by name. Nothing else removes a version row. | Read, `trash.py:388`, `:606`, `backend.py:143`. |

## The problem

- **Nothing records what a session changed.** A version row names the actor who replaced a body, not the session, the turn, or the call. A move, a delete and a create leave no version row at all.
- **A result does not say what a row was before.** A write over a tombstone and a write over a live file both report `updated`. A delete reports the version before it. A write that made three directories reports none of them. A rollback built on results alone would bring a deleted file back to life.
- **An old body cannot be read.** Story K8 is not built.
- **A tombstone holds its path.** "Delete what the session made, then move the old file back" fails for the commonest case there is: a file moved aside and a new one written in its place.
- **The two studied systems that restored files from snapshots lost other callers' work.** opencode took a whole-tree diff as a step's changes and discarded what other sessions wrote; its snapshot store grew to 15 GB in 11.5 hours. Codex removed file undo. Claude's file checkpointing does not undo a change made through the shell, a move, a delete or a made directory (`coding-agent-sessions.md`, sections 5 and 7; `forking-files.md`, the survey).

## Decisions

### 1. A change row is a record the kernel keeps, and it adds no primitive

A change row has no path in the namespace and is not first-class. It is a record the kernel keeps about calls, reached through `rewind` as a grant is reached through `grants`. A rollback composes three things the constitution has: the entry, its revision, and the version-history capability of article 1.5.

Reason: article 1 allows five first-class things, and the overview rules that a session, a turn and a job add none.

### 2. A storage reports every entry row a mutation changed, and what the row was before

`src/vfs/models/change.py` is new.

```python
class Change(NamedTuple):
    what: Literal["made", "written", "moved", "deleted", "restored", "revived"]
    kind: Literal["file", "directory"]
    entry: str                  # names the entry alone
    path: Path                  # where the row is after the call, as the storage sees it
    path_before: Path | None    # set for "moved" alone
    etag: Etag                  # the row after the call
    etag_before: Etag | None    # the row before; None for "made"
    version_before: int | None  # None for "made"
    mime_before: str | None     # the declared type before, for "written" and "revived"
```

| `what` | The row before | The row after | Where the storage knows it |
|---|---|---|---|
| `made` | absent | live | a staged insert: a file, a directory, a parent made by `parents=True`, every row a copy mints |
| `written` | live | live, another body or declared type | a staged update: `write`, `edit`, an append, an arbitration that landed on a rival's row |
| `revived` | a tombstone | live, another body | a staged update with `revive` set |
| `moved` | live at another path | live | the named row of a move |
| `deleted` | live | a tombstone | each row a delete named |
| `restored` | a tombstone | live | each row a restore named |

- `entry` is `EtagMint.mint(entry_key, 0)`: spec 1's mint at version 0, which no row holds. It is twenty hexadecimal characters, the same for two changes exactly when they are of one entry of one mount, and it is no row's etag. The entry id itself never leaves the storage.
- `etag` and `etag_before` are minted by the storage from the versions its transaction holds. A delete's `etag` is the tombstone's, one version above the one its observation reports.
- `Result` gains a private attribute, `_changes: tuple[Change, ...]`, empty by default. It is a pydantic `PrivateAttr`: it is not a field, it is not serialized, it does not render, and it is on no exported page.
- Each mutating method of the storage sets it on a result that succeeded. The facts are the ones its transaction already holds: `StagedEntry` has the entry, the base version, the new version and `revive` (`staging.py:55-82`), and the trash and topology verbs hold each claimed row. No statement is added.
- A row that came back `unchanged` reports nothing. A row beneath a deleted, restored or moved directory reports nothing: its own version did not move. A parent whose version was bumped reports nothing. `sweep` reports nothing.
- The router carries `_changes` through every merge and every path rewrite as it carries observations, and puts the mount's path in front of each path.
- No storage is reached over a wire in the tree. One that is must carry these facts in its own framing.

Reason: the storage is the only place that knows the state before a change for certain, and it knows it inside the transaction that made the change. Three of the six kinds cannot be told from a public result today.

### 3. `vfs_session_changes` holds one row per change, and no row is ever updated

```python
changes = Table(
    "vfs_session_changes",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True),
    Column("session_key", <the type of the surrogate key of vfs_sessions>, nullable=False),
    Column("turn_number", BigInteger, nullable=False),
    Column("what", String(16), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("entry", String(ETAG_LENGTH), nullable=False),
    Column("path_before", BytewiseString(MAX_PATH_LENGTH)),
    Column("path_after", BytewiseString(MAX_PATH_LENGTH), nullable=False),
    Column("etag_before", String(ETAG_LENGTH)),
    Column("etag_after", String(ETAG_LENGTH), nullable=False),
    Column("version_before", BigInteger),
    Column("mime_before", String(MAX_SEGMENT_LENGTH)),
    Column("rewind", String(ULID_LENGTH)),
    Column("undoes", BigInteger),
    Index("ix_vfs_session_changes_turn", "session_key", "turn_number", "id"),
    sqlite_autoincrement=True,
)
```

- The table joins `build_kernel_tables`, and the landing adds one to `KERNEL_FORMAT_VERSION`. Its statements are in a new module, `src/vfs/kernel_store/changes.py`.
- `id` is the order of the log. It is a counter the store hands out, never a clock, and never used again.
- The columns from `what` to `mime_before` are decision 2's. A rollback writes one more value of `what`, `settled`, which decision 15 gives. Paths are the caller's paths, with the mount's path in front. `path_before` is null unless the row was moved. `etag_before` and `version_before` are null for `made`.
- `rewind` is null for an ordinary change. For a row a rollback wrote it is that rollback's id. `undoes` is decision 15's.
- A row is inserted and never updated. The table has no expiry of its own and so no sweeper: rows go with their session, by decision 16.
- There is no foreign key. No table in the tree has one.

| One row for each | Verdict |
|---|---|
| Entry a session changed in a turn, as the overview's table says | Rejected. The second change of a turn would update the first row, which is a read and a write on the synchronous path. Two calls of one turn that end out of order would leave a row whose last etag is not the entry's. A change by somebody else between two of the session's would vanish inside the row. |
| Change | Chosen. An insert alone. Rows of one entry chain by their etags whatever order they arrived in, and a gap in the chain is somebody else's change, in plain sight. |

The record is a table of its own and not rows of the action log. Story H0 is not built, and a rollback wanted for 0.1.0 cannot wait on it.

Reason: an insert that depends on nothing is the one write that is safe when a process dies, when two calls race and when a row is lost. The cost is rows in proportion to changes, and each change already kept a whole body as a version.

### 4. A session writes its change rows after the change commits, by spec 0's record-after form, before the verb returns

A change through a stored session follows the order of spec 3's decision 8. This spec adds to two of its steps.

1. At its step 5 the kernel dispatches the verb. The storage commits it and returns the result with `_changes`.
2. At its step 7 the guarded router calls `store.record_after(fn)`. Inside it, `fn` builds one row for each `Change` and writes them with `insert_rows`. The stamps the change leaves are stored in the same call, so a change costs the kernel store one transaction for both.
3. The verb returns.

- **The turn.** `turn_number` is the number of the handle's turn. For a handle with no turn, `fn` reads the session's latest turn number first, in the same transaction, and calls spec 4's `make_first_turn` when the session has none.
- **A kernel store that fails.** The change stands. `record_after` returns spec 0's warning, of kind `vfs.unavailable`, and the result carries it. The rows are not written, and a rewind will not put that change back.
- **A cancel.** Spec 0's rule holds. A caller cancelled inside `record_after` is raised its cancellation after the rows are committed. A caller cancelled while the storage method runs gets its cancellation by the storage's rule, the kernel does not learn whether the change landed, and no row is written.
- **The system authority.** Its stored session records as any other. An anonymous authority owns no session, by spec 2.
- **No session.** A call on the file system with `authority=`, and a line run with `fs.cli`, write no row. A rewind has nothing of theirs to put back.

What each crash point leaves:

| The process stops | The mount | The log | What a later rollback does |
|---|---|---|---|
| before the storage commits | unchanged | no row | nothing; there is nothing to undo |
| after the commit, before the rows | changed | no row | with no other row for the entry: leaves the file and reports nothing. With earlier rows: the entry's etag is not the one the last row left, so it is left and reported `changed`. With later rows: the run starts after the gap, the file goes back to what the unrecorded change left, and it is reported `partly` |
| after the rows | changed | the rows | undoes them |

In none of the three is a file put into a state it never had, and in none is another caller's change removed. A missing row can only leave a file as it is.

What the verbs record:

| Call | Rows |
|---|---|
| a `write` or `edit` of one file | 1 |
| a `write` of 10,000 entries | 10,000, in 4 statements: 13 values a row against a budget of 32,700 |
| a `write` that changed nothing | 0 |
| an append | 1, `written`; each of 1,000 appends is a row |
| `write(parents=True)` that made three directories | 4 |
| a delete of a directory with a million entries beneath | 1, for the directory |
| a move of that directory | 1 |
| a copy of a tree of 10,000 entries | 10,000, each `made` |
| a shell line | the rows of each verb it called, in the order they returned |
| a resumed job | the rows of its verbs, under the turn the job started in |
| a tool's write through its session | the session's rows; tools are not built |
| `sweep`, `mkedge`, `rmedge`, `grant`, `revoke`, `set_posture`, a membership | 0; decision 18 |

| The form | Verdict |
|---|---|
| Inside the mount's transaction | Not offered. Spec 0 rules that no record is written there, on either engine. |
| Claim before, completed after | Rejected, though spec 0 names this record as its case. It is two transactions for every change, where the log cost study measured an effect's two at +151 ms a write under 32 writers on Postgres. The etag after, the parents made and an arbitration's outcome are not known before the change. A claim with no completion is in doubt, and a file in doubt cannot be put back: the store cannot say whose change moved its etag. So the form would add a warning for such a file and no restore. |
| Record after | Chosen. One transaction. A caller that has its result has its rows, so two calls made one after the other are recorded in order. |

Reason: the direction of every failure is the same. The log may lack a change the files hold. It never holds a change the files lack. A rollback checks the file, not the log, before it touches anything, so a lost row loses a restore and never does harm.

### 5. A rollback reads the files through two storage methods, `find_entries` and `read_versions`, and no public verb is added

`src/vfs/storage/protocol.py` gains a protocol, `SupportsRollback`, with two methods. Neither is an `Op`, neither is routed by name, and no caller outside the kernel reaches them. The database storage has both. Through a storage that lacks the protocol, every entry of that mount is left, each with a `vfs.unsupported` warning.

```python
class EntryTarget(NamedTuple):
    path: Path          # where the entry is expected
    entry: str          # decision 2's name for it

class VersionTarget(NamedTuple):
    path: Path          # where the entry is now
    entry: str
    version: int        # the version whose body is wanted
    holding: str | None # the content hash the entry holds now

async def find_entries(self, *, targets: list[EntryTarget], authority: Authority | None = None) -> Result: ...
async def read_versions(self, *, targets: list[VersionTarget], authority: Authority | None = None) -> Result: ...
```

**`find_entries`** answers where an entry is and what it is now.

- It reads the row at each `path` on either side of the tombstone. When that row is the entry named, it answers one observation: `path`, `kind`, `version`, `etag`, `content_hash`, and `deleted_at` when the row is a tombstone.
- When the path holds no row, or a row of another entry, it answers `not_found` for that path, and the rest are served.
- A row is judged at `list`, as `stat` judges a live row and the trash view a deleted one. A row the caller may not see is `not_found`.
- It issues one statement for each chunk of the membership budget and reads no body.

**`read_versions`** answers the body an entry held at a version.

- For each target the storage finds the version row of that entry with the smallest number at or above `version`. Each lookup is a seek on the primary key `(entry_id, version_number)`.
- A target whose entry has no such row, or whose row's hash is `holding`, answers one observation with status `unchanged` and no body. The entry already holds that body.
- Any other target answers one observation with the body as `content` or `data`, its `source`, its `content_hash`, its `size_bytes` and the version row's number as `version`. The body's hash is checked against the row's before it is returned, and a mismatch is that target's `vfs.internal` error.
- Targets are served in the order given while the bodies in the result stay within `BLOB_PAGE_BYTES`, 8 MiB (`dialects.py:81`), and at least one is served. The caller asks again from the first target that has no observation. Sizes are read from the version rows first, so no body is fetched that will not be returned.
- Each target is judged at `read` on the live row at `path`, which must be the entry named. A miss is that target's `not_found` or `permission_denied`, as a batch `read` gives, and the rest are served.
- A version row that is not a whole body, `is_snapshot` false, answers `not_found` with the detail `this version is not stored whole`. Nothing writes such a row today.
- Statements are chunked by the membership budget: one for the lookups of a chunk, one for the bodies of a page.

Reason for `read_versions`: story K8 gives callers `versions(path)` and `read(version=)`, with a verb name, a page key and creator rows that are not ruled. A rollback needs one thing of K8: the body an entry held at a version, for a caller who may read it. Built as a seam method, K8 can later stand its public read on it. Reason for `find_entries`: an etag cannot be taken apart, so no public row says whether a directory at a path is the directory the session moved. The storage can say, and the entry id stays inside it.

### 6. A rewind with files walks the session's change rows newest first and undoes each one

```python
async def rewind(self, *, before: str, files: bool = False, preview: bool = False) -> Rewind: ...
```

The rollback is given the session key and the number `n` of the turn, at the place spec 4 fixes.

**Select.** Read the session's rows with `turn_number >= n`, in pages of `CHANGE_PAGE_ROWS`, 10,000, by `id`. The newest `id` read is the rollback's `through`. A turn that an earlier rewind of the memory removed still has its rows, and they are selected when its number is at or above `n`. A removed number is never used again, so they can belong to no other turn.

**Group.** Rows with one `entry` are grouped, oldest first.

**Fold.** Walking a group from its newest row: a row with `undoes = j`, and every row of the group with an `id` from `j` to its own, become one segment. A segment starts at the `etag_before` and the path of its oldest row and ends at the `etag_after` and the path of its newest. It needs nothing done. What is left is the entry's chain.

**Find the run.** The run is the longest tail of the chain in which each link starts where the one before ended. For a file that is `etag_before` equal to the earlier `etag_after`. For a directory it is the same path and the same liveness, because a directory's version moves with its children. Links before the run are buried and are not undone.

**Undo.** The rows of every run that are in no segment, taken together, are walked from the newest `id` to the oldest. Each row's undo is:

| `what` | Undo |
|---|---|
| `written` | nothing of its own; the body is put back once, below |
| `moved` | move from `path_after` to `path_before` |
| `deleted` | `restore` at `path_after` |
| `restored` | delete at `path_after` |
| `revived` | delete at `path_after` |
| `made` | delete at `path_after`; `cascade=False` for a directory; decision 8 when the path is needed |

**The body.** A file's body is put back once. Take the oldest row of its run that is in no segment. The body wanted is the one the file held at that row's `version_before`, read by `read_versions`, and it is written with that row's `mime_before` declared. The write comes after that row's undo. When that row is `revived` or `restored`, the write comes just before its undo, so that the file goes back to the trash holding its old body. When that row is `made` there is no write. A body that `read_versions` answers `unchanged` needs no write.

Kind by kind:

| In the removed turns the session | The rollback |
|---|---|
| wrote, edited or appended to a file | writes its earlier body, as a new version |
| made a file | deletes it, to the trash |
| deleted a file | restores it |
| moved a file | moves it back |
| made a directory | deletes it with `cascade=False`, after everything the session made in it |
| deleted a directory | restores it, and everything deleted with it comes back |
| moved a directory | moves it back, with everything beneath it |
| changed one entry several times | undoes each move, delete and restore, newest first, and writes the body once: the entry is as it was before the first change |

- A file changed 1,000 times in the removed turns is put back by one write.
- A file written in `msg_5`, deleted in `msg_6`: the restore, then the write. It ends live with the body of `msg_4`.
- A directory moved after its files were edited: the move back first, since it is newer, and then each file is at the path its row names.
- A file moved from `a` to `t`, another from `b` to `a`, the first from `t` to `b`: three moves back, in reverse, through the session's own `t`. No cycle has to be broken.

| How to order | Verdict |
|---|---|
| Work out each entry's net change and sort the entries | Rejected. A row's paths are true only at the moment of its change. A directory moved later makes every earlier path beneath it false, and a swap of two files is a cycle. |
| Undo every row, newest first | Rejected for bodies: 1,000 appends would be 1,000 writes, each keeping a whole body. |
| Undo every row that moved, made or removed something, newest first, and put each body back once | Chosen. At each row the namespace is as that change left it, so its paths are true. |

Reason: the session's changes happened in an order in which each was possible. Their reverse is an order in which each undo is possible, as far as the session's own entries go.

### 7. An entry is put back only while it is as the session's last change left it

The plan reads the files once before any step, as the session's authority, through the router and not the session:

- `find_entries`, for each entry where it is now;
- one batch `stat` of each path a step would move an entry to, which must hold nothing.

An entry's path now is the `path_after` of its newest row, carried through every newer `moved` row of a directory above it, oldest first.

| The entry | The guard |
|---|---|
| A file, live or deleted | `find_entries` finds it at its path with the `etag_after` of the run's newest link. |
| A deleted directory | The same. A tombstone's version does not move. |
| A live directory | `find_entries` finds it at its path. Its etag is not compared, because a child made by anyone moves its version. |

Each step then carries the check into its own transaction:

- The first step on a file carries `if_match`: the `etag_after`. Each later step on that entry carries the etag the step before returned.
- A `restore` carries the tombstone's etag.
- A live directory is looked up again by `find_entries` just before its step, because the rollback's own steps inside it move its version. A move carries the etag that lookup returned.
- A made directory is deleted with `cascade=False` and no `if_match`, as spec 1's decision 10 says an emptied directory is. `not_empty` is its guard.

Every way another caller can have touched an entry, and what the report says:

| Since the session's last change, somebody | What is seen | The entry is | Reason |
|---|---|---|---|
| wrote, edited or appended to the file | the entry, another etag | left | `changed` |
| changed it and changed it back to the same body | the entry, another etag | left | `changed`; the guard is the version, never the body |
| deleted it and wrote it again at the path | the entry, another etag | left | `changed` |
| deleted it | the entry, a tombstone, another etag | left, in the trash | `changed` |
| moved it, or moved a directory above it | no row, or another entry, at the path | left where it now is | `not_there` |
| moved it away and put another file at the path | another entry | left; the other file is not touched | `not_there` |
| restored a file the session deleted, or wrote over its tombstone | the entry, live, another etag | left | `changed` |
| swept a file the session deleted | no row | lost | `gone` |
| made a file inside a directory the session made | the delete answers `not_empty` | left, with what it holds | `not_empty` |
| made a file inside a directory the session moved | nothing; the directory is the same entry | moved back, and the file rides with it | none |
| put something at the path a moved entry came from | the `stat`, or the move's `exists` | left where it is | `path_taken` |
| took a right from the session's authority | the step answers `permission_denied` | left | the verb's own refusal |
| changed the entry between the plan and its step | the step's `if_match` fails | left | `changed` |
| removed the mount, or made it read-only | `not_found`, or `read_only` | left | `not_there`, or the verb's own refusal |

The session's own later change counts as somebody else's when it is not in the selected rows: a change whose row was lost, or one a resumed job made under a kept turn. The words of `changed` say "after this session's last change in these turns" and name no one.

**`restore` must take `if_match`.** Without it: the session deletes a file, another caller restores it, edits it and deletes it again, and an unguarded restore brings back the other caller's edit as if it were the session's file. The precondition holds when the tombstone at the path has the etag given. It is judged in the restore ladder, and the claim that follows already compares the entry and the version (`trash.py:525-531`), so no statement is added. A mismatch is spec 1's `conflict`.

**Two windows are left open, and both are the ones spec 1 leaves.** A made directory replaced by another empty directory between the plan and its delete is deleted: it held nothing, and the delete can be undone. A change deep inside a moved directory does not move the directory's version and is not seen: the directory still goes back, with that change in it.

Reason: an etag names one entry at one version, versions only go up, and so an etag never comes back. A match means nobody has changed the entry since. Nothing else is known to mean that.

### 8. A made entry that stands on a path an older step needs is moved to a holding name and deleted there

A tombstone holds its path, and a move onto it is refused. So when the undo of a `made` row would leave a tombstone at `p`, and an older row of the plan is a `moved` row whose `path_before` is `p`, the undo is two steps:

1. Move the made entry from `p` to its holding name, `<name>.vfs-rewound-<id>` in the same directory, where `<id>` is the `id` of the `made` row.
2. Delete it there.

- The holding name is taken only then. Every other made entry is deleted where it stands, and the trash shows it at its own path.
- A made directory is moved with the tombstones beneath it, and deleted there with `cascade=False`.
- A holding name longer than `MAX_SEGMENT_LENGTH`, a holding path longer than `MAX_PATH_LENGTH`, or a holding path that holds anything: the made entry is left, with reason `path_taken`, and so is the entry that needed the path.
- A path held by an entry the session did not make is never cleared. The entry that needed it is left, `path_taken`.

Run on 2026-11-22: move `/a` to `/a.bak`, write a new `/a`, then move the new one aside, delete it, and move `/a.bak` back. `/a` holds its first body and its first entry.

| When the path is held by what the session made | Verdict |
|---|---|
| Delete it and report that the older entry cannot come back | Rejected. "Move a file aside and write a new one in its place" is how a backup is kept, and how a refactor leaves a shim at the old path. |
| Sweep it | Rejected. A sweep destroys, takes no `if_match`, and would make the rollback the one thing in this spec that cannot be undone. |
| Move it to a holding name, then delete it | Chosen. Two guarded steps, both reversible, both recorded. |

Reason: nothing a rollback does may destroy, and the trash does not give a path back.

### 9. Steps run in batches through the router's verbs, as the session's authority, below the session and below the policies

- **Authority.** Every step is dispatched with the session's authority, and is judged against that authority's rights as they stand when the step runs. A session stores no rights.
- **Below the session.** A step does not pass through the guarded router. The strict rule does not apply to it, and it makes no stamp of its own; decision 14 says what the stamps become.
- **Below the policies.** The rollback is judged once, as decision 13 says. Its steps are dispatched by spec 6's way of running a verb inside a step already judged.
- **Recorded.** Each step's `Change` facts become rows by `record_after`, as decision 4's do, with `turn_number = n`, `rewind` set, and `undoes` as decision 15 says.
- **Versioned.** A body put back is a `write`. The body it replaces is kept as a version row, attributed to the session's authority. Nothing is removed from history.
- **Guarded.** In article 5's words, every write a rollback makes is revision-guarded, and none is last writer wins. The one step with no `if_match` is the delete of a made directory, which `not_empty` guards.
- **Batches.** Steps that are next to each other in the walk, use the same verb with the same arguments, and touch different entries, go in one batch call: `write(entries=)`, `delete(observations=)`, `restore(observations=)`, `move(moves=)`, each with `if_matches`. A batch is cut at `REWIND_BATCH_ROWS`, 10,000 entries. A batch of writes is also cut where the bodies `read_versions` returned for one page end, so at most 8 MiB of old bodies are in hand, or one body when it is larger. The two steps of decision 8, and a step on a live directory, are single calls.
- **A refused batch.** A batch fails whole on each mount. Each error names a path. Those entries are left, with the reason their error gives, and the batch is sent again without them, at most `REWIND_BATCH_RESENDS`, 3, times. If an error names no entry of the batch, or the last resend is refused, every entry still in the batch has failed.
- **An entry that is left.** Its later steps are dropped. A step of another entry that depended on it meets its own refusal and is left too.
- **Timestamps.** `updated_at` is the time of the step. No time is put back.

Reason: a step is an ordinary change in everything but who asked for it. Rights, the version mint, the index's dirty marks and the chunked builders come with the verbs and are not built twice. One call for each of 10,000 files would be 150,000 statements, where a batch is tens.

### 10. A rollback puts back what it can and reports the rest, and only a failure stops the memory from being rewound

- **Some, not all.** An entry that cannot be put back is left, and the others are put back. This holds within one mount and across mounts. Each step is its own transaction on its own mount.
- **Left.** An entry left for a reason in decision 7's table, or because its earlier body is no longer kept. A second try would leave it again.
- **Failed.** A step that ended in `vfs.unavailable`, `vfs.timeout` or `vfs.cancelled`, or a batch that failed as decision 9 says. A second try may put it back.
- **The order.** The rollback runs first. If nothing failed, spec 4's transaction then removes the turns. If anything failed, the memory is not touched, and `rewind` raises with the report.
- **The retry is the same call.** The turn is still there. The rows of the steps already done are in the log, each finished entry closed with `undoes`, so the next plan folds them into segments and does nothing for them.
- **A step done but not recorded.** A crash between a step and its row leaves the entry at an etag the log does not have. The retry reports it `changed` and leaves it where that step left it.
- **A process that stops between the rollback and the memory.** The same call again finds every run folded, does no step, and rewinds the memory.
- **Two rollbacks of one session at once.** Each file is put back once, by whichever step's guard holds. The other reports it `changed`. A host runs one rewind of a conversation at a time, as it runs one turn.
- **A session still working.** A change made after the plan fails the guard of its entry, which is left. Rows newer than `through` are not read.

| | Verdict |
|---|---|
| Put back nothing unless every entry can be put back | Rejected. One file that somebody else touched would keep every other file of the turn as the session left it. No transaction spans two mounts, so the promise could hold on one mount at most. |
| Put back what can be, report the rest | Chosen. |

Reason: the guard exists so that another caller's file is left alone. A rule that made the whole rollback fail on that file would turn the guard against the user.

### 11. The report is a `Result` on a new field of `Rewind`

```python
class Rewind(NamedTuple):
    before: str
    turns: int
    jobs: int
    files: Result | None = None   # None when files=False
```

`files.ops` is `("rewind",)`. It has one observation for each entry put back, in the order of the walk, with `path`, `kind`, `status`, `version` and `etag` as they are after the rollback.

| The entry ends | `status` |
|---|---|
| in the trash | `deleted` |
| live at a path it was not live at before the rollback: brought back, or moved back | `created` |
| live where it was, with its earlier body | `updated` |
| as it already was | `unchanged` |

It has one warning for each entry left. The `path` is where the entry is, or was last known to be. `data["vfs.rewind"]` holds `reason` and the `what` of the run's rows.

| `reason` | Kind | Words |
|---|---|---|
| `changed` | `vfs.conflict` | `It changed after this session's last change in these turns, so it was left as it is.` |
| `not_there` | `vfs.not_found` | `Nothing is at the path this session left it at, so nothing was put back.` |
| `gone` | `vfs.not_found` | `It was deleted for good, so it cannot be brought back.` |
| `path_taken` | `vfs.exists` | `Its earlier path holds something this session did not put there, so it was left where it is.` |
| `not_empty` | `vfs.not_empty` | `This session made the directory, and it now holds entries the session did not make, so it was left.` |
| `no_version` | `vfs.not_found` | `The body it held before is no longer kept, so it was left as it is.` |
| `partly` | `vfs.conflict` | `An earlier change this session made to it lies under a change the session did not make. It was put back as far as that change.` |
| a verb's own refusal | as the verb gave it | as the verb gave it |

- `partly` is a warning on an entry that also has an observation.
- No kind is new. Every warning has `retryable` false.
- A warning carries no diff between the file as it is and the file as it was. The path and the reason are what is reported.
- The report is not paged. It has one row or one warning for each entry of the plan, as a batch write's result has one row for each entry.
- A failed entry is an error of the kind its step gave. `rewind` then raises `exception_for_kind` of the first failure (`exceptions.py:88`) with the report as its `result`, as spec 4's refusals carry theirs.
- The synchronous `Session.rewind` takes the same arguments, returns the same value and raises the same.

Reason: spec 4 ruled that `rewind` returns a plain value and raises, so that a rewind that did nothing is never read as one that did. A list of rows and facts already has a type, and a host already knows how to read it.

### 12. A preview returns the same report and changes nothing

`rewind(before=, files=True, preview=True)` runs decision 6 up to the plan and decision 7's reads, and returns `Rewind(before, 0, 0, files=report)`.

- Each observation has the status the entry would have and the path it would be at. Its `version` and `etag` are the ones it has now.
- It foresees `changed`, `not_there`, `gone`, `path_taken` and `partly`. It does not foresee `not_empty`, `no_version`, a missing right or a read-only mount: those are judged when a step runs. It reads no version row.
- It issues no `INSERT`, `UPDATE` or `DELETE` on any mount or on the kernel store. No turn is removed, no job is cancelled and no stamp is moved.
- It is not shown to the policies. It changes nothing, and it is the host's read of its own session's record.
- It shows what would be done to each entry and not the text that would change. A diff is story H2's.
- `preview=True` with `files=False` is refused `vfs.invalid` and raises `ValidationError`: `preview=True shows what files=True would put back; pass both.`

Reason: a person who is asked to approve a rollback must be shown its plan, and a host must be able to ask what a rollback would do before it does it.

### 13. A rewind with files is one step to the policies and one job to an interrupt

`rewind` is for the host's code, as `resume` is. It is not a shell command and is never offered to an agent as a tool.

- When the plan has at least one step, the policies are asked about one `RewindStep`. Its `paths` are every path a step would change: the path an entry is at and the path it goes back to. A policy typed `Mutation` sees it, and `step.touches("/contracts")` is true when any file put back is under `/contracts`.
- **Allowed.** The steps run.
- **Denied.** Nothing is put back, the memory is not rewound, and `rewind` raises with spec 6's denial, `vfs.permission_denied.policy`. The host may then rewind the memory alone.
- **Interrupted.** Nothing is put back and the memory is not rewound. The job is saved with the session key, `n` and `through`. `rewind` returns `Rewind(before, 0, 0, files=<the interrupted result>)`, whose `interrupted` is true and whose interrupt carries decision 12's report as its preview. It does not raise.
- **Resumed.** The plan is made again from rows with `id <= through`, and every guard is checked again. An entry that changed while the job waited is left. A change the session made while the job waited is not in the plan, and its entry is left. So the resumed rollback can do less than the person saw and never more. The memory is then rewound, and `resume` returns the report.
- **The system authority.** No policy is asked about its rollback, and it is never interrupted.
- **A rewind of the memory while the job waits.** Spec 4 cancels the waiting jobs of the removed turns. The rollback's job is one of them: it is stored under turn `n`.
- A policy typed for one verb, such as `DeleteStep`, is not asked about a `RewindStep`. A host that wants a rollback judged types its policy `Mutation` or names `RewindStep`.

| | Verdict |
|---|---|
| Each step is shown to the policies as its own write, delete or move | Rejected. Under a review policy a rollback of 300 files is 300 interrupts, one waiting at a time, with the files half put back between each for as long as a person takes. The rollback would need a journal as a shell line does, and the memory could not be rewound until the last answer, while spec 4 cancels the waiting jobs of the turns it removes. |
| The rollback is one step | Chosen. One question, with the whole plan as its preview. |

Reason: a policy guards what an agent does. A rollback is the host's act, made on a user's word. It is still a change to files, so the policies see it, once.

### 14. After a rollback the session remembers a put-back file as the state it saw

A file put back has a new etag: the same entry, a later version. A stamp from a kept turn names the old one, so the session would refuse its next change as changed, though the file holds exactly what was read.

- After spec 4's transaction, for each entry whose run ends undone, by this call or by an earlier try of it, the rollback asks spec 3's function to move the session's stamp for the entry's path from the `etag_before` of the run's oldest link to the etag the entry has now.
- The stamp moves only if the session holds exactly that etag. A session that last saw an older state keeps its stamp, and its next change is refused until it reads the file.
- An entry that was left has its stamp untouched.
- A process that stops before the stamps are moved leaves them as they were. The cost is one refusal and one read for each file.

Reason: a stamp means this content was shown. After a rollback that is true of the put-back state exactly when the kept memory holds the state that was put back.

### 15. A rollback's own changes are rows of the log, marked with its id, and no call undoes a rollback yet

- Each `rewind` with `files=True` that reaches its steps makes an id, a ULID of 26 characters. Every row a step leaves carries it in `rewind`.
- When every step on an entry has succeeded, the rollback closes the entry with `undoes`: the `id` of the oldest row it undid. The row of the entry's last step carries it. When that step changed nothing, or the entry needed no step, the rollback writes one row for it with `what = "settled"`, the entry's etag as both `etag_before` and `etag_after`, its path, and `undoes`.
- That is what lets a later plan fold the undone rows and the rollback's own into a segment. An entry that was left, or whose steps did not all succeed, is not closed.
- A later rewind to an earlier turn selects the rollback's rows with the rest, since they carry `turn_number = n`. A file edited in `msg_3`, edited in `msg_5`, put back by a rewind to `msg_5`, and then rewound to `msg_3`: its chain is the row of `msg_3` and one segment, the run is both, and one write puts back the body before `msg_3`.
- A turn started after the rollback has a higher number. A rewind to it does not select the rollback's rows.
- **A rollback can be undone by hand today.** Each body it replaced is a version row, and each entry it took away is in the trash.
- **No call undoes it.** The rows marked with one id are exactly what such a call would walk, newest first, by decision 6. The overview's public names have none for it, and this spec adds none.

Reason: an append-only log needs no second table to remember a rollback. The rollback is in the log as every other change is, and the two markers cost two null columns.

### 16. A rewind of the memory alone removes no change row, and a fork copies none

- **Spec 4's step R4 issues no statement.** The files still hold what the removed turns did, and the rows say so.
- A later `rewind(before=, files=True)` to a turn before those puts their changes back with the rest.
- There is no call that puts the files back and leaves the memory. Files go back only with the memory.
- **A fork.** `fork` changes no file and copies no change row. A fork's own rewind selects rows of the fork's key alone, so it puts back what the fork changed and never what its parent did.
- **The end of a session.** `remove_changes(session, session_key, limit) -> int` deletes at most `limit` rows of one key and returns the count. It is one statement of a fixed shape: `DELETE FROM vfs_session_changes WHERE id IN (SELECT id FROM vfs_session_changes WHERE session_key = :k ORDER BY id LIMIT :limit)`. It joins spec 2's `SESSION_CHILDREN`. No file is touched.
- A live session's rows are never pruned.

Reason: a row is the fact that a file still carries a session's change. A rewind of the memory does not make that false. A fork that held its parent's rows could undo its parent's work.

### 17. No version a rollback needs is held back from a sweep, and what a sweep destroyed is reported

- **Live entries.** Nothing removes a version row of a live entry. Every body a rollback needs for a live file is there for as long as the file is.
- **Deleted entries.** A file the session deleted is swept `trash_days` after the delete, 90 by default, or when its path is swept by name. A rollback then reports it `gone`.
- A session expires 30 days after its last use, and a session in use does not expire. So a session used for longer than `trash_days` can outlive a file it deleted.
- A rollback places no hold on the trash, and `sweep` reads no session.
- A spec that removes or rewrites version rows of live entries must say what it does to a rollback. None is built. The roadmap's `pack` and the draft that keeps only what an append added are the two that would.

Reason: a hold would make every sweep read every session's log, to protect a rollback that is offered and may never be asked for. Reporting what is gone costs nothing until it happens.

### 18. Edges, rights, sweeps and anything outside VFS are not put back

- **Edges.** `mkedge` and `rmedge` are not recorded. An edge has no version and no etag, so there is nothing to guard it with.
- **Rights.** A grant, a revoke, a posture and a membership are not recorded.
- **A sweep.** What it destroyed is gone.
- **Mounts** added or removed, **jobs** cancelled by the rewind, and other sessions' stamps.
- **Outside VFS.** A request a tool sent, a message, a process. Zheng et al. show that a restore cannot unsend one (`forking-files.md`, the survey).

Reason: the rule of this spec is that a thing is put back only when nobody else has changed it, and that rule needs an etag. The guide lists what is not put back, as ADK's does.

### 19. The work is five landings, each green

1. The storage reports its changes: `Change`, `_changes`, every mutating method, the router's carry. After spec 1's first landing, for the mint.
2. `find_entries` and `read_versions`. After the same.
3. The table and the rows a session writes. After specs 0, 2 and 3, and spec 4's first landing.
4. `rewind(files=, preview=)`: the plan, the steps, the report, the stamps, and `if_match` on `restore` where spec 1's landings have not carried it. After spec 4's third landing.
5. The `RewindStep` and the interrupted rollback. After specs 6 and 7. If spec 6 is built when landing 4 is cut, the two land as one, so that no tree has policies a rollback does not meet.

Reason: the first two are of use to stories H0, H2 and K8 with no session at all, and each later landing adds one thing that can be tested alone.

## Cost

Costed against the reference deployment in the working agreement.

**Per verb call, about 150,000 a day.** A read adds no statement, synchronous or written behind, and no row. `_changes` is an empty tuple on its result.

**Per file write, about 1,050,000 a day.** One `record_after` on the kernel store for each mutating call through a stored session, and one row for each entry it changed. Nothing is added to the mount's transaction, and no lock is taken on any mount. Each `Change` costs three mints, at 1.2 µs each by spec 1's figure. A write with no session adds nothing: the nightly batch of 1,000,000 files is a pipeline's and writes no row. The organic 50,000 writes a day, 100,000 at the ceiling, are the most that can pass through sessions. A row is three twenty-character values, one path and a few short columns, about 250 bytes with its index entry; that figure is an estimate and not measured. 100,000 rows a day is about 25 MB a day, kept for the life of each session.

**The insert.** It is into a table that only grows, keyed by a counter. No row is shared between sessions, and no row is updated, so there is no hot row. A read never touches the table.

**Per batch.** A 10,000-entry write through a session is 10,000 rows in 4 statements.

**Per index visit.** Nothing is added to a partial pass or to the rebuild. A file put back is one more changed file for the next partial pass, as any write is.

**Per rollback.** Work in proportion to the entries the session changed in the removed turns, never to the corpus.

| Part | Statements |
|---|---|
| Reading the rows | one for each 10,000 rows |
| Reading the files as they stand | `find_entries` and one batch `stat` for each mount, each chunked by the membership budget; one more `find_entries` for each live directory with a step |
| Old bodies | one lookup statement for each chunk of targets and one body statement for each 8 MiB page |
| Steps | those of the batch verbs: a turn that wrote 10,000 files of 4 KB is about 5 pages, each one batch `write` |
| The rollback's own rows | one `record_after` for each batch; 4 statements for a batch of 10,000 |

**Memory.** The plan holds every selected row, about half a kilobyte each in Python: 5 MB for a turn of 10,000 changes, 500 MB for a million. No cap is declared. The direction is a plan that reads one entry's rows at a time, by an index on `entry`. One page of old bodies is in hand at a time. One body larger than the page is held whole, as an `edit` of that file holds it today.

**Per lock.** A rollback holds no lock between steps and none while a person is asked: an interrupt comes before the first step. Each step takes what its verb takes and holds it for that verb's commit. No read waits on a rollback beyond what it waits on a batch write, delete or move today.

**A rollback across an earlier one.** Bodies cost nothing more: a segment needs nothing done. A step that was left half done by a crash is undone and done again by the next plan.

## Left as it is

- **A call that undoes a rollback.** Decision 15 keeps what it would need.
- **A rewind of the files alone.** Decision 16.
- **A diff in the preview.** Story H2.
- **`versions(path)` and `read(version=)`.** Story K8.
- **The made parents in a write's result.** They are in `_changes` and not in the observations.
- **A delete and a write that cancel out.** A file deleted and written again in the removed turns is put back by a delete, a restore and a write, where one write would do. It is correct, and it costs two steps.
- **A directory's guard.** Somebody else's file in a directory the session moved goes back with it. Its body and its etag do not change.
- **A file's executable bit.** The draft that adds it must say whether a version row keeps it and whether a write keeps it.
- **A session's rows over a long life.** They are not pruned.
- **A change made without a session.** A host that writes through the file system for a conversation leaves no row.

## Tests

Each is written and seen failing before the code. Counts are of statements recorded by a `before_cursor_execute` listener on the mount's engine and on the kernel store's `engine`, as `tests/storage/database/test_writes.py` does, on a SQLite file. Never of time. A row of the storage contract runs on every engine leg.

`tests/storage/database/test_changes.py`, at the seam:

- `test_each_mutation_reports_what_it_changed`, one case for each row of decision 2's table: the `what`, the `version_before`, and that `etag` is the etag a `stat` then returns. A write over a tombstone reports `revived`. A delete reports the tombstone's etag, not the one its observation shows.
- `test_two_changes_of_one_entry_share_its_name`: a write, a move and a delete of one file report one `entry`; a copy of it reports another.
- `test_parents_made_by_a_write_are_reported`: `write(parents=True)` under three missing directories reports 4 changes and 1 observation.
- `test_a_directory_delete_and_move_report_one_row`: a directory with 100 entries beneath reports 1 change for a delete, 1 for a restore and 1 for a move.
- `test_a_copy_reports_every_row_it_mints`: a tree of 100 entries reports 100 `made`.
- `test_an_unchanged_write_reports_nothing`.
- `test_reporting_adds_no_statement`: the counts of a `write`, an `edit`, a `delete`, a `restore`, a `move` and a `copy` are the counts before the landing.
- `test_changes_are_not_serialized`: `Result.model_dump()` and the payload hold no change.

`tests/storage/database/test_rollback_reads.py`:

- `test_an_entry_is_found_on_either_side_of_the_tombstone`: a live file, a deleted one and a directory each answer one row with its etag; a path that holds another entry, and one that holds nothing, answer `not_found`. One statement for the five targets.
- `test_a_row_the_caller_may_not_see_is_not_found`.
- `test_the_body_at_a_version_is_the_next_version_row`: after a write, a move and a write, the body at the version after the first write is read from the row numbered one above it.
- `test_a_body_still_held_is_unchanged`: a target whose `holding` is the row's hash, and one with no row at or above its version, answer `unchanged` with no body, and no body statement runs.
- `test_bodies_stop_at_the_page`: ten targets of 1 MiB each are served 8, then 2, in two calls.
- `test_a_target_the_caller_may_not_read_is_refused_alone`: one `permission_denied`, the rest served.
- `test_10000_targets_issue_a_bounded_number_of_statements`, with the membership budget narrowed to 1,000: 10 statements for `find_entries`, and 10 lookup statements for `read_versions`. Marked `slow`.
- A contract row: a bytes body and a text body read back equal on every engine leg.

`tests/session/test_changes.py`, on memory, SQLite and the Postgres leg:

- `test_a_change_is_one_insert_on_the_kernel_store`: a session's `write` issues 1 `INSERT` into `vfs_session_changes`, and the mount's count is the count without a session.
- `test_a_read_writes_nothing`: `read`, `stat`, `ls`, `tree`, `glob`, `grep` and `search` through a session issue no statement naming `vfs_session_changes`, during the call and after `drain`.
- `test_a_10000_entry_write_is_4_statements`: 10,000 rows, 4 statements. Marked `slow`.
- `test_a_recursive_delete_and_a_directory_move_are_one_row_each`.
- `test_a_line_records_each_change_it_made`: `scout.cli("mkdir d && echo x > d/f && mv d/f d/g")` leaves 3 rows in that order.
- `test_a_call_with_no_session_writes_no_row`: `fs.write(..., authority=)` and `fs.cli` leave the table empty.
- `test_a_handle_with_no_turn_files_the_row_under_the_latest_turn`.
- `test_a_failed_record_leaves_the_change_and_warns`: with the kernel store made to fail, the write succeeds, the file holds the body, the result has one `vfs.unavailable` warning, and the table gains no row.
- `test_a_cancel_inside_the_record_still_writes_the_row`: 1 row, and the caller is raised `CancelledError`.
- `test_a_fork_copies_no_row` and `test_deleting_a_session_removes_its_rows`, the second in chunks of `SESSION_RECLAIM_CHUNK`.

`tests/session/test_rewind_files.py`, on memory, SQLite and the Postgres leg:

- `test_each_kind_of_change_is_put_back`, one case each: a file written, edited, appended to, made, deleted, moved; a directory made, deleted with files beneath, moved with files beneath; a file brought back by a write over its tombstone. Each compares the entry's path, liveness and body with those before the turn.
- `test_many_changes_to_one_file_are_one_write`: 50 edits across two removed turns are put back by 1 batch `write`, and the file gains 1 version.
- `test_a_file_written_then_deleted_comes_back_with_its_first_body`.
- `test_a_moved_file_whose_path_was_taken_by_a_new_one`: the new file is in the trash under its holding name, and the first file is at its path with its entry and its body.
- `test_a_swap_of_two_files_is_three_moves_back`.
- `test_a_directory_moved_after_its_files_were_edited`.
- `test_a_moved_directory_the_session_then_filled_goes_back`: a directory moved and a file made in it; the file is deleted, the directory is looked up again and moved, and neither is reported left.
- `test_a_file_another_caller_changed_is_left`, one case for each row of decision 7's table: the reason, and the other caller's body, path or tombstone unchanged. Zero mutation statements name that entry.
- `test_a_change_between_the_plan_and_the_step_is_left`: a rival write at a seam before the step makes the step's `if_match` fail, and the rival's body survives.
- `test_a_restore_is_guarded`: delete by the session, then restore, edit and delete by another caller; the rollback reports `changed` and the file stays deleted.
- `test_a_buried_change_is_put_back_as_far_as_the_other_callers`: the file holds the other caller's body, and the report has `partly`.
- `test_nothing_is_removed_from_history`: the count of version rows after a rollback is the count before plus the bodies it replaced, and no tombstone was swept.
- `test_a_rollback_as_a_caller_who_lost_a_right_leaves_that_file`: one `permission_denied` warning, the rest put back.
- `test_two_mounts`: with one mount made read-only, its entries are left and the other mount's are put back.
- `test_a_failed_step_keeps_the_memory`: with one batch made to fail `unavailable`, `rewind` raises, `turns()` still shows the turn, and the same call again puts back the rest and issues no mutation statement for the entries already done.
- `test_a_rollback_run_twice_does_nothing_the_second_time`: zero mutation statements on the mount.
- `test_an_entry_already_as_it_was_is_closed_by_a_settled_row`: a file written and written back in one turn gains 1 `settled` row, and the next plan does not ask `read_versions` about it.
- `test_a_10000_file_turn_rolls_back_in_batches`: with 10,000 files of 1 KiB edited in one turn, the rollback makes at most 2 batch `write` calls, counted by a spy on the router's dispatch, and writes its 10,000 rows in at most 5 statements, one `record_after` for each batch. Marked `slow`.
- `test_a_preview_changes_nothing`: zero `INSERT`, `UPDATE` and `DELETE` on the mount and on the kernel store; the rows of `vfs_session_turns`, `vfs_session_stamps` and `vfs_session_changes` are counted equal before and after; the report equals the report of the real call that follows in paths and statuses.
- `test_preview_without_files_is_invalid`.
- `test_a_rewind_without_files_changes_no_file_and_removes_no_row`: zero statements on any mount.
- `test_a_later_rewind_to_an_earlier_turn_crosses_a_rollback`: decision 15's example, 1 write.
- `test_a_rewind_of_the_memory_then_of_the_files`: a memory-only rewind to `msg_5`, then a rewind with files to `msg_4`, puts back the changes of the removed `msg_5`.
- `test_a_put_back_file_can_be_changed_without_reading_it`: the session's next `edit` succeeds. With an older stamp it is refused as changed.
- `test_a_fork_rewinds_only_what_it_changed`.
- `test_a_swept_file_is_reported_gone`.

`tests/session/test_rewind_policies.py`, with landing 5:

- `test_a_rollback_is_one_step`: a policy typed `Mutation` is called once for a rollback of 20 files, with 20 paths.
- `test_a_denied_rollback_changes_nothing`: zero mutation statements, the turn still stored.
- `test_an_interrupted_rollback_waits_and_resumes`: zero mutation statements before the answer; after `resume`, the files are back and the turn is gone.
- `test_a_resumed_rollback_leaves_what_changed_while_it_waited`.
- `test_the_system_authority_is_not_judged`.

`tests/storage/database/test_trash.py`: `test_a_restore_that_requires_an_etag`: the tombstone's etag restores; another is `conflict` and the row stays deleted; the count of statements is the count without the argument.

`tests/shell/test_host.py`: `test_a_change_made_by_a_line_is_put_back`: `sed -i`, `mv`, `rm -r` and `>` through `scout.cli`, then a rewind with files.

`tests/test_sync.py`: the parity test covers `files=` and `preview=` on `Session.rewind` and the `files` field.

## Scope

In:

- `src/vfs/models/change.py`, new. `src/vfs/results/envelope.py`: the private attribute.
- `src/vfs/storage/backends/database/`: `writes.py`, `staging.py`, `trash.py`, `topology.py` and `backend.py` report changes; a new `rollback_reads.py` and the two methods on the backend; `if_matches` on `restore`. `src/vfs/storage/protocol.py`: `SupportsRollback`.
- `src/vfs/base.py`: the carry of `_changes` through merges and path rewrites; `if_match` and `if_matches` on `restore`, on the four public faces and in the parameter table.
- `src/vfs/kernel_store/changes.py`, new: the table's statements. `build_kernel_tables` and `KERNEL_FORMAT_VERSION`.
- `src/vfs/session.py` and `src/vfs/sync_session.py`: the rows, `rewind`'s two arguments. A new `src/vfs/rewind.py`: the plan, the walk, the batches and the report.
- `Rewind.files`, and the constants `CHANGE_PAGE_ROWS`, `REWIND_BATCH_ROWS` and `REWIND_BATCH_RESENDS`.
- The tests above, and the docs below.

Out: everything under "Left as it is"; spec 3's stamp function; spec 6's step class; spec 7's job.

Files other specs also change: `src/vfs/session.py` and `src/vfs/sync_session.py`, by specs 2, 3, 4 and 7. `src/vfs/results/envelope.py`, by spec 7. `src/vfs/storage/protocol.py`, `trash.py`, `base.py` and the parameter table, by spec 1. `build_kernel_tables`, by every spec that keeps a record.

The landings are decision 19's. Each runs `scripts/ci.sh`, and landings 1 to 4 run the Postgres leg.

## What the docs must say

- A rewind with `files=True` puts back the files the session changed in the removed turns, each one only if nobody has changed it since.
- A file somebody else changed is left, and the report says which and why.
- A body put back is a new version. A file the session made goes to the trash. Nothing is destroyed.
- A rewind with files covers what a shell line changed, a move, a delete and a made directory.
- What is not put back: edges, rights, anything swept, anything outside VFS, and a change made without a session.
- `preview=True` shows the plan and changes nothing.
- A policy sees a rollback as one step, and a person approves the whole plan.
- A fork never puts back its parent's files.
- `restore` takes `if_match`.

Pages, each changed: the docstrings of `AsyncSession.rewind` and `Session.rewind`, which are the reference; the docstring of `restore`; `documentation/how-to/keep-a-session-for-each-conversation.md`, as the disagreements below say; `documentation/how-to/interrupt-a-job-and-ask-a-person.md`, one line. The `Result` docstring is not changed, since `_changes` is private.

## Earlier decisions this reverses

- **The draft that stood at this path.** Its decision 1 wrote the record "with the change"; the row is written after it, in another transaction. Its decision 3 deleted a made file where it stood; decision 8 moves it first when its path is needed. Its decision 5 made each restore a call of a public verb; a step is dispatched below the policies, as part of one step.
- **Spec 3's decision 13**, a draft of the same day: a session's own change refreshes its stamps. A rollback's steps do not pass through the guarded router and refresh none. Decision 14 says what the stamps become.
- **A decision record on the trash** says no transfer replaces an occupant, a tombstoned one included. It stands. Decision 8 works around it and does not change it.
- **Roadmap story K8** gave the read of an old body to a public verb at gate `f`. The storage half is built here, earlier, with no verb.
- **Three drafts of the same day, where they meet this one.** Spec 0's decision 10 names this record for its claim-before form; decision 4 takes record-after. Spec 1 leaves `restore` with no precondition; decision 7 gives it one. Spec 4's decision 8 says a dead record is removed by the next rewind whose range covers its number; a change row is not removed, by decision 16.

## Choices for the owner

Each is decided above and stands until it is ruled on.

1. **A rollback is one step to the policies.** Decision 13. The other choice shows each restore to the policies and interrupts file by file.
2. **A rollback puts back what it can.** Decision 10. The other choice puts back nothing unless every entry can be.
3. **Files go back only with the memory.** Decision 16. The other choice is a call that puts back the files and keeps the session's memory, as Claude's rewind offers.
4. **No call undoes a rollback in 0.1.0.** Decision 15. The rows that would serve one are kept.
5. **A made file in the way goes to the trash under a holding name.** Decision 8. The other choice leaves both files and reports them.
6. **Another caller's file inside a directory the session moved goes back with the directory.** Decision 7. The other choice leaves the directory where it is.
7. **Edges and rights are not put back.** Decision 18.
8. **The trash is not held for a session.** Decision 17. The other choice keeps a deleted file from the sweep while a session that deleted it lives.
9. **The record is written after the change, not claimed before it.** Decision 4. The other choice is spec 0's claim-before form, at two transactions a change.

## Where this spec disagrees with the overview or the guides

1. **The overview's table says `vfs_session_changes` holds one row per entry a session changed in a turn.** Change proposed: "one row per change a session made to an entry". Evidence: decision 3's table. A row per entry and turn must be updated on the synchronous path and loses a change made between two of the session's.
2. **The overview gives spec 1 `if_match=` on `write`, `edit`, `delete` and `move`.** Change proposed: add `restore`. Evidence: decision 7's case of a file restored, edited and deleted again by another caller.
3. **The overview's table has spec 5 build on 1, 3 and 4.** Change proposed: add 0 and 2, and 6 and 7 for its last landing. Evidence: decisions 4 and 13.
4. **The overview says a step is one verb about to run.** Change proposed: "one verb, or one rewind that puts files back". Evidence: decision 13. A rollback under a review policy is otherwise one interrupt for each file.
5. **The session guide says "A rewind and a fork change what a session remembers. They never change a file", twice, and calls putting files back "a separate feature, planned for the same release".** Change proposed: Step 5 gains `scout.rewind(before="msg_5", files=True)` with its report, the sentence "A rewind changes a file only when it is asked to, with `files=True`", and a third column in its table: with `files=True` the plan is "put back as it was read in `msg_4`, so Scout can change it without reading it again". Evidence: ruling 14 and decision 14.
6. **The interrupt guide lists what a `Mutation` is and ends at "a restore".** Change proposed: add "and a rewind that puts files back". Evidence: decision 13.

## Not checked

- Nothing was run on Postgres. The holding-name sequence, the delete of a directory that holds only tombstones, and the version numbering were run on SQLite alone.
- The seven other drafts were read once, while they were being written, and may have changed since. Every name taken from them, `record_after`, `insert_rows`, `EtagMint`, `session_key`, `SESSION_CHILDREN`, `Rewind` and the place of its hook, is as it stood then. Spec 8 was not read. Spec 3 was read in part, after it was rewritten: the stamp function of decision 14 is a need it has not answered, and whether its step 7 can share one `record_after` with the change rows was not checked against its statement.
- That specs 6 and 7 can carry a step that is no verb. Neither draft has one: spec 6 gives each of 25 verbs a class, and spec 7 computes a preview for seven verbs and returns a `Result` from `resume`.
- The size of a row, and what a `record_after` costs a write in round trips.
- Two calls of one turn that overlap and touch each other's paths, such as a move away from a path and a create at it sent at once. Their rows can be inserted in the other order. The steps then meet a refusal and both entries are left and reported. It was reasoned and not run.
- The rights a session needs for the holding move. It made the entry, so the owner floor should serve; read, not run.
- The plan's memory and time at a million rows.
- Whether a batch `delete`, `move` or `restore` names every refused path in its errors once each carries `if_matches`. `delete_rows`, `restore_rows` and `transfer_rows` collect an error for each target today (`trash.py:173-199`, `:312-327`, `topology.py:165-243`).
- How often a turn changes a file through a session, and how often a user asks for the files back. One study measured up to 87% of turns changing no file (`forking-files.md`, Crab).

## One line

A session records each change it makes, and a rewind can walk those changes backwards and put each file back, only if nobody else has changed it since, destroying nothing.
