# A row carries a vid, and a change can require it

A draft, written on 2026-11-22. It is not reviewed, and nothing is built. It is spec 1 of the nine that `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md` maps. It lifts decisions 1 and 2 out of the spec merged from pull request 42, `agents/2026-11-22-the-session-remembers-what-it-read/spec.md`, and makes them a kernel spec of their own that needs no session. It rests on the landed spec `agents/2026-11-20-write-takes-preconditions-and-an-append/spec.md`, whose preconditions it extends, and on the verification record `agents/2026-11-22-shell-review/reviews/verification.md`, whose four cases it ran again. Every fact about the code was read on the branch `a-job-is-interrupted-and-resumed` at `6dae6a1d`, whose kernel and storage files are those of `dev` at `5a823ea`, and the facts a decision rests on were run that day. The probes sit outside the repository. It was reconciled the same day with the other eight specs as they stood on disk: decisions 17 to 19 are that round's, and so are the changes to decisions 2, 6, 8, 9, 12, 14 and 16 that each says it carries. A third round, against the other eight at `7c383f32` and after, renamed nothing here and closed every need another spec had stated on this one.

## The outcome wanted

Every row a call returns about a file or a directory that the caller may read carries a `vid`: a short opaque value that names one entry at one version. A caller that reads a file and later writes, edits, deletes or moves it passes that value back as `if_vid=`. The change lands only when the row at the path is still that entry at that version. When it is another version, or another file that came to stand at the path, nothing changes and the call is refused with `vfs.conflict`.

```python
row = (await fs.read("/notes.md", authority=who)).observations[0]
changed = await fs.write(path="/notes.md", content=new_body, if_vid=row.vid, authority=who)
# changed.success is False, and changed.errors[0].kind == "vfs.conflict", when /notes.md moved on
```

The check costs no statement, and a read pays no statement for the vid.

## Builds on

- `agents/2026-11-20-write-takes-preconditions-and-an-append/`: landed on 2026-11-20. It gives `write(if_version=, if_versions=, if_absent=, append=)`, the snapshot, the plan, the guard and `conflict` with `data["version"]`. This spec keeps its plan and its guard, and replaces its two version arguments.
- `agents/2026-11-22-the-session-remembers-what-it-read/spec.md` as merged from pull request 42: drafted. Its decisions 1 and 2 are the source of this spec. It is being rewritten as spec 3 to hold the session half only.
- `agents/2026-11-22-shell-review/reviews/verification.md`: the record that a version alone does not name a file. Its four cases were run again here.
- `agents/2026-11-22-a-session-is-stored-named-and-forked/research/history.md`, lineage 4: the entity tag and `If-Match` of HTTP, and the lost update they were made for. Its lesson is that the record of what was read is a validator checked at write time, safe to copy, safe to lose and safe to send with the request.
- It needs nothing from specs 0 and 2 to 8. It keeps no record, so it uses none of the forms of spec 0, decision 22 (The interface is private, and this is all of it). It adds no error kind.
- Built on by, each drafted and read on 2026-11-22:
  - Spec 3, decision 9 (A session fills in the precondition and, when strict, refuses a change to what it was not shown), which passes `if_vid`, `if_vids` and the mark of decision 18; decision 11 (A directory is held to its vid, and a session's own change carries that vid forward), which since the ruling of 2026-11-23 sends the vid decision 10 here matches; decision 12 (The two refusals are `vfs.conflict.changed` and `vfs.conflict.unread`, and neither carries a version), which answers in place of this spec's `conflict` only where the session filled the precondition in; decision 18 (A writer that spans chunks carries the vid its last chunk left), which states `if_vid` on an append; and decision 23 (A mount that issues no vid is outside the guard), which rests on decision 13 here.
  - Spec 5, decision 2 (A storage reports every entry row a mutation changed, and what the row was before), which uses `VidMint`, and decision 7 (An entry is put back only while it is as the session's last change left it), which needs decision 17 here.
  - Spec 6, decision 2 (Each verb has one step class, and that class is the one description of the verb's arguments), whose classes are written from the parameter table as this spec leaves it.
  - Spec 7, decision 13 (The preview is computed once, as the caller, for seven verbs, and every part of it is bounded), which needs decision 19 here, and decision 22 (The saved step is carried out as its caller, with rights judged again, and with the vids the preview saw as `if_vid`), which needs decisions 6 and 18.
  - Spec 8, decision 7 (A read is journaled as a reference to the body it saw, and the body is read again on replay), which keeps a row's vid.

## Terms

- **Entry id.** The permanent identity of one stored row, a ULID kept as 16 bytes in `vfs_entries.entry_id`. It never leaves the storage.
- **Version.** The per-entry counter in `vfs_entries.version`. Creation sets 1, and each change of the row adds one.
- **Mount identity.** One ULID kept in `vfs_meta.mount_identity`, made when a database is provisioned. It names the database, and not the path it is mounted at.
- **Vid.** Twenty characters that name one entry at one version in one mount. Two vids are equal when, and only when, they name the same entry at the same version of the same mount. A vid grants nothing: rights are judged on every call as before.
- **Mint.** To compute the vid of a row.
- **Precondition.** A condition a caller attaches to a change. When it is false, nothing changes and the call is refused.
- **Snapshot.** The read a change takes of its targets before it decides anything.
- **Guard.** The terms on a mutation statement that prove the row is still the one the snapshot read.
- **Window.** The time between the snapshot and the guarded statement.
- **Mutation statement.** An `INSERT`, `UPDATE` or `DELETE`.
- **Tombstone.** A deleted row that stays at its path with `deleted_at` set. It is absent to every read.
- **Bare row.** A row that shows only `path` and `kind`, given to a caller who may list a row and may not read it.
- **Seam.** The storage protocol, `SupportsMutation` in `src/vfs/storage/protocol.py`.
- **Trait.** A quality a storage declares through `traits()`, read by the kernel without calling a verb.
- **Key.** One path of an `if_vids` mapping.
- **Mark.** The value `ABSENT`, given where a vid is given. It requires that the path holds no live row.

## What the code does today

Run on 2026-11-22. A file named without a directory is under `src/vfs/storage/backends/database/`, but for `base.py`, `mounts.py` and `cursor.py`, which are under `src/vfs/`, and `entry.py` and `rows.py`, which are under `src/vfs/models/`. Statement counts leave out `BEGIN`, `COMMIT`, `PRAGMA`, `SAVEPOINT`, `RELEASE`, `ROLLBACK` and the statistics statements. Times are from a bench on one machine, Python 3.13, in-memory SQLite. They size a cost and pin nothing.

| Fact | How it is known |
|---|---|
| `Observation` carries `version` and `content_hash` and nothing that names the entry (`src/vfs/models/entry.py:457-460`). The models carry no database identifier, by rule (`entry.py:23-26`, `82-86`), and rows never leave the storage (`rows.py:20-23`). | Read. |
| The entry id is a ULID stored as 16 bytes and handed to Python as 26 characters (`rows.py:241-268`, `371`). The version is a 64-bit column (`rows.py:377`). | Read. |
| The mount identity is minted at provisioning (`engine.py:671`) and read at first touch (`engine.py:945`). Every verb awaits first touch before its first statement (`backend.py:1352`, `1482`). Two storage objects over one database file read one identity, and another database has another. | Read and run. |
| `write` takes `if_version`, `if_versions`, `if_absent` and `append` (`base.py:925-938`). The single form becomes a mapping of one key (`base.py:1020`), and the keys are routed to the mount of each file (`base.py:2491-2501`). | Read. |
| `edit`, `delete` and `move` take no precondition (`base.py:1025-1035`, `1072-1079`, `1247-1254`). | Read and run. |
| A row a caller may read always carries `version` (`reads.py:110`). A caller who holds `list` alone gets a bare row (`reads.py:114`, `280-284`). Under an everyone level of `list`, `stat` and `ls` return rows whose mask is `kind` and `path`. | Read and run. |
| What moves the id and the version of one file, in order: created (id A, 1), rewritten (A, 2), written with the same body (A, 2), deleted (A, 3), written again (A, 4), deleted and restored (A, 6), moved (A, 7), its parent moved (A, 7 at the new path), copied (a new id, 1), its parent deleted (A, 7, tombstoned), its parent restored (A, 7), edited (A, 8), appended to (A, 9). | Run. |
| A directory's version moves when a direct child is made, deleted or renamed, and not when a child's body changes or a grandchild is made: 2, child made 3, child rewritten 3, subdirectory made 4, grandchild made 4, child deleted 5, child renamed inside 7. | Run. |
| The guard of a write or an edit already names the entry and the version. On SQLite it is `entry_id = ? AND version = ? AND path = ? AND deleted_at IS NULL` as an executemany proven by its row count (`writes.py:1086-1097`). On Postgres it is a `VALUES` join with `RETURNING`: `entry_id = incoming.v_id AND path = incoming.v_path AND deleted_at IS NULL AND version = incoming.v_base` (`writes.py:953-981`). | Run on SQLite. Compiled from the builder for Postgres. |
| The claim of a delete already names both: `entry_id = ? AND version = ? AND deleted_at IS NULL` on SQLite (`serialized.py:201-205`) and the same three terms over a `VALUES` join on Postgres (`serialized.py:314-328`), from the snapshot's id and version (`trash.py:458`). | Run on SQLite. Compiled for Postgres. |
| The claim of a move already names both, on both engines: `entry_id = ? AND version = ?`, from the source row read for the pair (`topology.py:170`, `326-338`). A move never replaces what is at its destination: an occupant, a tombstone included, is `exists` (`topology.py:188-191`). | Read and run. |
| A delete adds one to the version of the row it names and stamps the rows beneath with no change of version (`trash.py:459-464`, `492-496`). A restore adds one to the root and none beneath (`trash.py:526`, `543-547`). A move adds one to the moved row and none beneath (`topology.py:335`, `387-407`). | Read and run. |
| The row a delete returns reports the version the row had before the delete (`trash.py:660-668`). A file deleted at version 1 is a tombstone at 2 in the trash view and is live at 3 after a restore. | Read and run. |
| A restore judges the row at the path, then the parents (`trash.py:246-258`), and its claim names the entry and the version of the tombstone: `entry_id = ? AND version = ? AND deleted_at IS NOT NULL` (`trash.py:525-531`). At the seam, as the system actor, a restore of a file issues 6 statements. | Read and run. |
| A batch that creates three files in one directory and replaces a fourth issues 1 insert on `vfs_entries`. The files of one depth are arbitrated as one group, under one flag for the whole call (`writes.py:622-625`). | Read and run. |
| A `write` whose target is a directory is `wrong_kind`, with or without an expected version (`staging.py:288-290`). | Read and run. |
| At the seam, as the system actor, on a SQLite file: an update by `write` issues 8 statements, an `edit` 7, a delete of a file 4, a cascading delete of a directory 5, a delete of an empty directory without cascade 6, a move of a file 16. A write with a stale `if_version` issues 1, the snapshot. | Run. |
| Through the kernel, as the system authority, on a SQLite file that holds five files in `/d`, one in `/d/sub` and one edge, after a `rebuild`: `stat` issues 1 statement, `read` 1, `ls` 2, `tree` 2, `glob` 1, `grep` 7, `search` 8, `traverse` 3. | Run. |
| A stale `if_version` is `conflict` with `data == {"version": n}` and `retryable` false (`staging.py:521-528`). An `if_absent` over a live row is `exists` with `version` and `content_hash` (`staging.py:531-541`). | Run. |
| A write that loses its guard probes the row by its entry id (`writes.py:1069-1082`). The version it reports is that entry's, wherever the entry now sits. | Read. |
| A merge of two rows of one path keeps a version both agree on and nulls one they disagree on (`src/vfs/results/envelope.py:497-498`). | Read and run. |
| A storage declares traits (`src/vfs/storage/protocol.py:78-99`, `backend.py:240-253`), and the kernel passes `after` and `limit` only to a storage that declares `listing_cursor` (`cursor.py:128-131`). | Read. |
| `InMemoryStorage` is `SQLiteStorage` over a private in-memory database (`src/vfs/storage/backends/memory.py:41`). | Read. |
| `update_mount` changes a mount's policy and never its storage (`base.py:529-535`). One storage object is mounted once in a table (`mounts.py:482`). A move or a copy between two mounts is refused `cross_mount` (`base.py:2368-2369`). | Read. |
| Postgres runs a write at REPEATABLE READ and a delete or a move at READ COMMITTED behind the serialization point, and both engines probe a lost guard (`dialects.py:360-365`, `413-422`). SQLite takes its writer lock before a write's first read (`backend.py:1383-1385`). | Read. |
| A row of a 10,000-row listing costs 9.4 µs for `ls`, 7.3 µs for `tree`, 8.2 µs for `glob`, 18.0 µs for `grep` in files mode and 17.5 µs for a `stat` of 10,000 rows, end to end. Its compact JSON is 185 bytes. | Run, a bench. |
| The shell's host keeps `(path, version, content_hash)` for each open, because a version alone does not tell two files apart (`src/vfs/shell/host.py:300-306`), and asks every read for the hash for that reason (`host.py:91-93`). | Read. |

## The problem

A version alone does not name a file. A move that frees a path lets another file come to stand there at the version a caller saw, and `write(if_version=...)` then replaces a file the caller never read and reports success. Each case was run on an in-memory file system. The caller reads `/x/p` at version N, another caller acts, and the first caller writes with `if_version=N`.

| What the other caller did | `/x/p` afterwards | `write(path="/x/p", if_version=N)` |
|---|---|---|
| Moved `/x/p` away and wrote a new file at `/x/p` | another entry at version 1 | success with N = 1. The new file is replaced. |
| Moved `/x/p` away and moved another file, then at version 1, to `/x/p` | another entry at version 2 | success with N = 2. The moved file is replaced. |
| Moved `/x/p` away and copied another file to `/x/p` | another entry at version 1 | success with N = 1. The copy is replaced. |
| Moved `/x` to `/y`, made `/x` again and wrote `/x/p` | another entry at version 1 | success with N = 1. The file the caller read sits untouched at `/y/p`. |

Two cases the version does catch were run beside them. A delete and a write at the same path leave version 3 against a caller at 1, and the write is refused `conflict`. A move onto a deleted path is refused `exists`.

An entry id alone does not name a state of a file either. A delete and a later write at the same path revive the row with its old id, and every rewrite keeps the id.

`edit`, `delete` and `move` take no precondition at all. A caller that lists a directory and deletes it cannot say what it saw.

The kernel has both halves of the answer and shows neither whole. The id stays inside the storage by rule. The version is shown, and it is half a name.

## Decisions

### 1. Every row that carries a version carries a vid, and the storage mints it

`Observation` gains one field, `vid: Vid | None`, placed after `version`. A storage fills it on every row it fills `version` on, from that row's own entry id and the version the row reports. The two fields share a mask: `"vid"` is in `populated` exactly when `"version"` is. `ALWAYS_ON_FIELDS` in `reads.py` gains it, so no `columns=` projection drops it. A bare row carries neither.

The field is listed in `OBSERVATION_QUERY_FIELDS`, the fields no model field owns: it is worked out when a row is produced and is stored nowhere. `Entry.to_observation` leaves it unpopulated, as it leaves `version`.

The vid is part of the public result and crosses the wire as any other field does.

The storage mints, and not the router. The merged spec had the router mint.

Nothing is stored. No table gains a column, the schema format number stays, and no row is backfilled.

Reason: a vid is made from the entry id, and the entry id is the one fact about a row that never leaves the storage. A router that minted would have to be handed the id on every row, which is the leak the models forbid.

### 2. A vid is twenty hexadecimal characters: a keyed digest of the mount, the entry and the version

```python
# src/vfs/vid.py, a leaf module: the standard library alone
VID_LENGTH: Final = 20
Vid = Annotated[str, "20 lowercase hex characters that name one entry at one version; compared, never parsed"]

def is_vid(value: object) -> bool: ...          # a str of exactly VID_LENGTH characters from 0-9 and a-f

class VidMint:
    def __init__(self, mount_identity: str) -> None: ...
    def mint(self, entry_key: bytes, version: int) -> Vid: ...
```

`mint` returns `hashlib.blake2b(entry_key + version.to_bytes(8, "big"), digest_size=10, key=mount_identity.encode("ascii"), person=b"vfs.vid.1").hexdigest()`. `entry_key` is the entry id's 16 bytes, so the hashed input is always 24 bytes and no two rows share one. The key is the mount identity's 26 characters. `person` names the form.

The engine host builds one `VidMint` at first touch, where it reads the mount identity, and every site that builds a row from a stored row is handed it.

A vid is compared for equality and nothing else. No code takes one apart, and none can: the digest does not give back the id or the version. The reconciliation rules the same for all nine specs: a record that needs a version keeps it beside the vid, from the same row.

`mint(entry_key, 0)` is lawful. No row is at version 0, since creation sets 1, so the value is no row's vid, is on no row, and never satisfies a precondition. A storage may keep it inside a record of its own to name an entry alone, as spec 5, decision 2 (A storage reports every entry row a mutation changed, and what the row was before) does.

| Form | Verdict |
|---|---|
| The entry id and the version in clear, encoded | Rejected. It is 40 characters against 20, it puts a database identifier on a model that carries none by rule, and a caller that can parse it will. |
| A digest in two halves, one of the entry and one of the entry at its version | Rejected. Its one use is to compare the entry alone, which decision 10 does not need, and it costs every row a second hash. |
| The version and the body's hash, the pair the shell's host keeps | Rejected. It tells two files apart only while their bodies differ. Another file with the same body at the same version passes, and a delete or a move of it then changes a file the caller never saw. A directory has no hash at all. |
| A digest in base64url, 16 characters | Rejected. 318 of 20,000 minted ones began with `-`, which reads as an option on a command line, and the alphabet is case-sensitive. Hex costs 4 more characters and is the faster to make. |
| One keyed digest in hex, 20 characters | Chosen. One value in about 4,300 is all digits, or digits around one `e`, and a reader that guesses types takes it for a number (`probes/p09_how_often_an_etag_reads_as_a_number.py`: 101 of 400,000). JSON keeps it text. The gate's refusal names the type it was handed, and the reference page says a vid is always text. |

Reason for the digest: it keeps the vid opaque by construction, so its form can change without breaking a caller. Reason for the key: a vid of one mount equals a vid of another only when two digests collide, which is one chance in 2^80 for each comparison, so a vid cannot be mistaken for another mount's. Reason for 80 bits: a vid is compared against one row, never searched for, and it grants nothing, so nobody gains by forging one.

### 3. A vid follows the entry and its version, and nothing else

| Event | The vid |
|---|---|
| A write of a new body, an edit, an append | A new one. The version moved. |
| A write of the body the file holds | The same. Nothing moved. |
| A delete of the row, then a restore | A new one. The version moved twice. The body is the same, and a holder of the old vid reads again. |
| A delete, then a write at the path | A new one. The row keeps its id and the version moved. |
| A move of the row | A new one, at the new path. |
| A move of a directory above the row | The same, at the row's new path. It is the same entry at the same version. Required at the old path, it meets nothing or another entry. |
| A delete and a restore of a directory above the row | The same. While the row is deleted, a change that requires it is `not_found`. |
| A copy | The copy is another entry at version 1, with a vid of its own. |
| `update_mount` | The same. It changes policy and never the storage. |
| The same storage mounted at another path, in another kernel or in another process | The same. A path is no part of a vid, and the mount identity is the database's. |
| Another storage mounted at a path | No vid held for that path matches, and a change that requires one is `conflict`. |
| A move or a copy between mounts | Refused `cross_mount`, as today. A caller that copies and deletes makes a new entry in the other mount. |
| A grant, a posture, an index pass, a rendering | The same, wherever the version stays. A vid names what a change replaces. It says nothing of rights or of derived state. |
| A later form of the vid | Every old vid stops matching. That is only ever a refusal, and a read mends it. |

Reason: these are the properties of the two columns the vid is made from, run in "What the code does today". None is added by this spec, so no statement is added to keep one true.

### 4. Each verb fills the vid on the rows it already returns

| Verb | Rows | The vid names |
|---|---|---|
| `read`, `stat` | Each row the caller may read | The row as read |
| `ls`, `tree`, `glob` | Each whole row. A bare row, a directory shown only as the road to a mount, and the trash view's own head carry none | The row as listed |
| `grep`, `search` | Each file row | The file as searched |
| `traverse` | Each whole node row. An edge row and a bare node carry none | The node as walked |
| `write`, `edit`, `mkdir` | Each row of the result, a `created`, an `updated` and an `unchanged` one alike | The row after the call |
| `move`, `copy`, `restore` | Each row of the result | The row after the call, at its new path |
| `delete`, `sweep` | Each row of the result | The row as it was before the call, since the row reports that version |
| `mkedge`, `rmedge`, the grant verbs | None. Their rows carry no version | |

A row in the trash view carries the vid of the tombstone. A mount's root, shown where the mount is listed, carries the vid its own storage mints.

`observations=` never implies a precondition. A row handed back to `edit`, `delete`, `read` or any other verb is used for its path, and its vid is ignored. A caller that wants each row required says so: `if_vids={row.path: row.vid for row in rows}`.

A merge of two rows of one path, by `Result.merge` or by `&`, `|` and `-`, keeps a vid both rows agree on and nulls one they disagree on, as it does a version. When it nulls the version it nulls the vid. When two rows disagree on the vid the version is nulled with it, whether or not the two versions are equal: two rows of one path at one version with two vids are two entries, and the version names neither.

The default text projections stay as they are. They show no version today and show no vid. A caller names `vid` in a projection to see it in text.

The shell's host answers a line with public verbs (`src/vfs/shell/host.py:377`, `421`, `476-490`), so the rows it is handed carry vids as any caller's do. It passes none to the module, no program prints one, and it sends no `if_vid`.

Reason for every listing row: a caller cannot know which listed row it will change, and a session stamps what it is shown, so a listing that left the vid out would force a second read of every row before a change. The cost of carrying it is under "Cost".

### 5. A read takes the entry id as its stored bytes and mints once for each row

`src/vfs/models/rows.py` gains a sibling of `ULIDKey`, `ULIDBytes`: the same column read as its 16 stored bytes with no conversion to text. A read that does not already select the id selects it through `ULIDBytes` under the label `entry_key`. On SQLite the driver returns the bytes. On Postgres it returns a UUID, whose `bytes` the type hands on. A read that already holds the id as text, and every change, turns the text into the 16 bytes with a new pure function beside it, `entry_key_of(text)`, which is `int(text.translate(table), 32).to_bytes(16, "big")`.

`vid` is no column. Where a set of fields becomes a select list (`entry_columns` in `reads.py`), a new constant `DERIVED_FIELDS = frozenset({"vid"})` is left out, and the id is selected for it.

| Step | Cost for each row |
|---|---|
| Select the id as text through `ULIDKey` | 2.1 µs |
| Select the id as bytes through `ULIDBytes` | 0.2 µs |
| Mint from bytes | 0.9 µs |
| Mint from text, through `entry_key_of` | 1.2 µs |

Reason: a listing does not select the id today, and selecting it as text would cost twice what the mint costs. As bytes, a read row pays about 1.1 µs in all.

### 6. `write`, `edit`, `delete` and `move` take `if_vid`, and their batch forms take `if_vids`

```python
async def write(self, entries=None, *, path=None, content=None, data=None,
                if_vid: Vid | None = None, if_vids: Mapping[str, Vid] | None = None,
                if_absent: bool = False, append: bool = False, parents: bool = False,
                authority: Authority | None = None) -> Result: ...

async def edit(self, path=None, old=None, new=None, edits=None, observations=None, replace_all=False, *,
               if_vid: Vid | None = None, if_vids: Mapping[str, Vid] | None = None,
               authority: Authority | None = None) -> Result: ...

async def delete(self, path=None, observations=None, *, cascade: bool = True,
                 if_vid: Vid | None = None, if_vids: Mapping[str, Vid] | None = None,
                 authority: Authority | None = None) -> Result: ...

async def move(self, src=None, dest=None, moves=None, *,
               if_vid: Vid | None = None, if_vids: Mapping[str, Vid] | None = None,
               authority: Authority | None = None) -> Result: ...
```

- `if_vid` is the precondition of the single form: `path` for `write`, `edit` and `delete`, and `src` with `dest` for `move`, where it names the source.
- `if_vids` is the precondition of the batch form: `entries`, `observations` or `moves`. It maps a path to the vid required there. A path with no key has no precondition.
- The precondition holds when the live row at the path has the vid given. Nothing else is compared.
- A value may be the mark, `ABSENT`, in place of a vid. Decision 18.
- `restore` takes both arguments too. Decision 17.

The kernel turns `if_vid=E` into a mapping of one key, as it turns `if_version` today. A storage sees one shape:

```python
async def write(self, *, entries, if_vids: Mapping[Path, Vid] | None = None, if_absent=False, append=False, parents=False, authority=None) -> Result: ...
async def edit(self, *, edits, path=None, observations=None, if_vids: Mapping[Path, Vid] | None = None, authority=None) -> Result: ...
async def delete(self, *, path=None, observations=None, cascade=True, if_vids: Mapping[Path, Vid] | None = None, authority=None) -> Result: ...
async def move(self, *, operations, if_vids: Mapping[Path, Vid] | None = None, authority=None) -> Result: ...
```

The kernel passes `if_vids` only when the call requires something, so a storage that cannot honour it never sees the argument.

The merged spec gave `if_vids` to a batch write alone. The batch forms of `edit`, `delete` and `move` take it here too.

Reason: a precondition that only one form of a verb can state leaves the other form to be split into one transaction a row, which loses the rule that a batch fails whole. The mapping costs no statement, since the comparison is made in Python against rows the snapshot already holds.

### 7. `if_version` and `if_versions` leave

They leave the four public signatures, the parameter table with its `versions` kind and its four rules, and the seam. Inside the plan, `StagedEntry.expected_version` becomes `expected`, a vid, and `stale_version` becomes `stale_vid`. No alias is kept.

`version` stays on every row. It is the readable counter, the label of a version row and the number a `conflict` reports.

A caller that wants "the file is at version N" reads the row, compares `row.version` itself and passes `row.vid`. That is one read, and it is sound.

Reason: the four cases of "The problem" report success and replace a file the caller never saw. A precondition that is known to be unsound beside a sound one is a trap, and the design is not released, so there is no caller to move. The earlier reason for the version was that every reader already holds it and a model can copy it. Both are now true of the vid, which arrives in the same row.

### 8. The rules at the gate

Each is refused before any storage is called. Rows 1 to 5 are in `params.py` and are judged first, even on a closed kernel.

| Rule | Refusal |
|---|---|
| `if_vid` is a vid or the mark: `is_vid` holds, or the value is `ABSENT` | `invalid`: `"{op} if_vid must be a vid, the 20 characters a result carries, got {shown}"`. `shown` is the type's name for a value that is not text, and the first 32 characters in quotes for one that is. A new `ParamKind`, `vid`. |
| `if_vids` is a mapping of text to vids or the mark | `invalid`: `"{op} if_vids must be a mapping of paths to vids, got {type}"`, `"{op} if_vids keys must be strings, got {type}"`, or `"{op} if_vids values must be vids, the 20 characters a result carries, got {shown}"`. A new `ParamKind`, `vids`, checked key by key. |
| `if_vid` goes with the single form, and `if_vids` with the batch form | `invalid`: `"write takes if_vid with path, and if_vids with entries"`, `"edit takes if_vid with path, and if_vids with observations"`, `"delete takes if_vid with path, and if_vids with observations"`, `"move takes if_vid with src and dest, and if_vids with moves"`, `"restore takes if_vid with path, and if_vids with observations"`. Two shape rules for each verb. |
| `if_absent=True` with `if_vid` or `if_vids` | `invalid`: `"write if_absent=True takes no if_vid or if_vids: an absent file has no vid"`. |
| `append=True` with `entries` | `invalid`, as today. `append=True` with a vid as `if_vid` is lawful: it is the append that lands at most once. `append=True` with the mark is `invalid`, with the words `if_absent` has today: `"write takes append or if_absent, not both: an append to an absent path already creates it"`. |
| Each key of `if_vids` names a target of the call, once it is resolved as the targets are: a file of `entries`, a row of `observations`, a source of `moves` | `invalid`: `"each key of if_vids must be the path of a file in entries"`, `"... of a row in observations"` or `"... of a source in moves"`, with `data={"raw": key}`. In `base.py`. |
| No two keys name one path | `invalid`: `"if_vids names one path twice"`, with `data={"raw": key}`. |
| The storage of each mount that receives a key declares the `vid` trait | `unsupported` at the mount's path: `"the storage mounted here issues no vid, so a change there cannot require one"`. Decision 13. |

The kernel resolves each key, matches it to a target, and hands each mount the keys of its own targets with the mount's prefix taken off. A batch over two mounts stays whole on each mount and not across them, which is today's rule for any refusal.

An empty `if_vids` requires nothing. Beside the single form it is refused by the form rule, as an empty `if_versions` is today.

A value that has the shape of a vid and was minted by another mount, or by nobody, passes the gate. Decision 12 says what answers it.

Reason: a wrong argument is the caller's to fix and is named before anything runs. The shape is all the gate can know, since a vid cannot be taken apart.

### 9. The precondition is judged at the snapshot, and the guard each statement already carries holds it

Each verb mints the vid of the live row its snapshot read and compares it with the one required. When they are equal, the id and the version the snapshot holds are the ones the vid names, and the mutation statement already compares both. No term and no statement is added.

| Verb | Where it is judged | The statement that carries it, unchanged |
|---|---|---|
| `write` | In the plan. Order: the address gates, `if_absent` or the mark, a required vid against a live directory, the occupant's kind, a required vid against no live row, stage, settle. Settle drops a row whose body is the stored body first, and then refuses each row whose vid is not the one required. | The material `UPDATE`. SQLite: `entry_id = ? AND version = ? AND path = ? AND deleted_at IS NULL`. Postgres: the same four terms over a `VALUES` join. |
| `write(append=True)` | As a write, after the row lock and the second read. | The same `UPDATE`. |
| `edit` | After the miss and before every other judgment of the row: a target whose vid is not the one required is refused, its kind of body is not looked at and its edits are not run. | The same `UPDATE`. |
| `delete` | In the ladder, after the miss and before `not_empty`. A target covered by another target's cascade is judged too, where it has a key. | The claim `UPDATE`: `entry_id = ? AND version = ? AND deleted_at IS NULL`, as an executemany on SQLite and over a `VALUES` join on Postgres. |
| `move` | In the pair's ladder, after the source is found live and the root is refused, and before the rename onto itself. | The root claim `UPDATE`: `entry_id = ? AND version = ?`, on both engines. |
| `restore` | Decision 17: after the ladder and the permit, before the claim. | The claim `UPDATE`: `entry_id = ? AND version = ? AND deleted_at IS NOT NULL`. |

What a `write` answers, by what is at the path when the snapshot is read:

| Target | `if_vid=E` |
|---|---|
| absent | `not_found`. A precondition never creates. A missing parent answers at that parent, with `parents=True` too. |
| tombstoned file | `not_found` with the trashed hint. A precondition never revives. |
| live file, same body | `unchanged`, whatever `E` is |
| live file whose vid is `E`, new body | updated to the next version |
| live file whose vid is not `E`, new body | `conflict` |
| live directory | `conflict`. With no vid required it is `wrong_kind`, as today. |
| tombstoned directory | `not_found` with the trashed hint. With no vid required it is `wrong_kind` with the hint, as today. |

A live row whose vid is not the one required is `conflict` whatever its kind. This is round two's change: spec 3, decision 11 (A directory is held to its vid, and a session's own change carries that vid forward) reads a file's vid met by a directory as a file that changed, and `wrong_kind` would tell a caller that required a file nothing about what became of it.

`unchanged` comes before the comparison for a `write` and after it for an `edit`. A write of the body a row holds is recognisably a call sent twice, and it writes nothing. An edit is no stored value, so its second sending cannot be told from a stale one, and it is `conflict`.

A rival inside the window:

- **SQLite.** A writer holds the database's one writer lock from before its snapshot, so no rival commits inside the window. The in-memory storage has one connection, and calls on it queue.
- **Postgres, `write` and `edit`.** The call runs at REPEATABLE READ. A rival's commit inside the window ends the guarded `UPDATE` with a serialization failure, and the call runs again from a new snapshot. The answer is the one that snapshot gives: `conflict` where the row is still at the path with another vid, `not_found` where the rival moved or deleted it, and `unchanged` where the rival wrote the very body the call carries. Run on Postgres 19.0 on 2026-11-23 (`probes/p03_a_rival_inside_the_window.py`, `probes/p04_the_quoted_statements_at_each_isolation_level.py`). A guard that matches no row is answered by a probe on a profile that declares it, and both supported engines do (`dialects.py:365`, `418`). Neither reaches it from a rival inside the window: SQLite admits no rival, and Postgres raises the serialization failure first. The generic floor declares no probe and runs the call again (`dialects.py:318`). The probe is reached by a rival staged on the attempt's own session, which is how its tests stage it.
- **Postgres, `delete` and `move`.** The call runs at READ COMMITTED behind the serialization point. A rival's write inside the window moves the version, the claim matches no row, and the verb runs again from a new snapshot, where the vid no longer matches.
- **An append.** A rival appender waits on the row lock. When it gets the lock it reads the new version, and with `if_vid` it is refused `conflict` and does not run again.

Two calls that require one vid of one file: one lands and moves the version, and the other meets the new one. Exactly one lands on every engine.

Two processes mint the same vid for one row, since every input is a stored value.

A crash between two statements leaves nothing: the snapshot, the comparison and the mutation are one transaction. A call cancelled before its commit changed nothing, and one cancelled after it landed whole. The caller cannot tell which, so it sends the call again with the same vid: a `write` that landed answers `unchanged`, an `edit` that landed answers `conflict`, a `delete` or a `move` that landed answers `not_found`, and a `restore` that landed answers `exists`.

In a batch, a key is judged against the state before the call. A `write` that names one path twice judges its key once. A `move` reads each pair's source live, so a key on a source that an earlier pair of the same call moved into place never matches.

Reason: the comparison belongs where the row is already in hand, and the proof belongs on the statement that changes it. Both existed. Adding a term or a read would cost the million writes a day something for a guarantee they already have.

### 10. A directory is matched as a file is, by its entry and its version

One rule serves every kind of row on every verb. For a directory:

- A cascading delete, and a move, with `if_vid` require the directory to be the same entry with the same direct children it had when it was read: a child made in it, deleted from it, moved into or out of it, or renamed in it since refuses the call. A change deeper down, and a change of a child's body, do not move the directory's version and are not seen.
- A delete without cascade requires the same. A caller that emptied the directory itself moved its version by doing so, and passes no `if_vid`: `not_empty` is the guard an empty directory needs. A caller that names the children and the directory in one call may require the directory's vid: the key is judged against the state before the call.
- `write` and `edit` refuse a directory `wrong_kind`, as today.

The merged spec compared the entry alone on a delete without cascade.

Reason: comparing the entry alone needs a vid that can be taken apart, which costs every row a second hash or its opacity (decision 2). It would buy one refusal: of a delete of an empty directory that is not the one the caller saw. An empty directory holds nothing to lose, and the delete can be undone.

### 11. A move requires its source, and its destination takes no precondition

`if_vid` on a `move` names the row at `src`. The destination must be free, as today: any occupant, a tombstone included, is `exists`, whether or not a precondition is given.

Reason: a precondition protects what a call would replace. A move replaces nothing at its destination, so there is nothing there to require.

### 12. A mismatch is `conflict` with the version and the vid of the row at the path, and a vid from another mount is a mismatch like any other

| Refusal | Kind | `data` | `retryable` |
|---|---|---|---|
| The vid required is not the vid of the live row, at the snapshot | `conflict` | `{"version": v, "vid": e}` of the row at the path | no |
| The same, found by a call that ran again after a rival | `conflict` | the same | no |
| Where a guard matched no row and the profile probes, which a rival inside the window causes on neither supported engine: a write with a required vid lost its guard, and the row probed is still at the path | `conflict` | `{"version": v, "vid": e}` of that row | no |
| The same case: the row probed has moved away | `conflict` | none: the row now at the path was not read | no |
| The same case: a plain write lost its guard | `conflict` | `{"version": v, "vid": e}` where the row is still at the path, and none where it moved | yes, as today |
| A required vid against no live row | `not_found` | the trashed hint on a tombstone | no |
| The mark, on a `write`, over a live row | `exists` | `{"version": v, "content_hash": h, "vid": e}` | no |
| The mark, on `edit`, `delete` or `move`, over a live row | `conflict` | `{"version": v, "vid": e}` | no |
| A `restore` whose tombstone has another vid | `conflict` | `{"version": v, "vid": e}` of the tombstone | no |
| `if_absent` over a live row | `exists` | `{"version": v, "content_hash": h, "vid": e}` | no |
| A value that is no vid | `invalid` | none | no |
| A mount whose storage issues no vid | `unsupported` | none | no |

The detail of the first four is `"the vid required is not the vid of what is stored"`. Every stale row of a batch is listed, and the batch fails whole. Decision 19 gives the one constructor.

This spec adds no error kind. A session answers with its own two in place of this `conflict` only where it filled the precondition in, and those carry no version: spec 3, decision 12 (The two refusals are `vfs.conflict.changed` and `vfs.conflict.unread`, and neither carries a version). A precondition the caller stated is answered here, with the version and the vid.

The contract row of `conflict` in `KIND_CONTRACTS` reads: phrase `Conflict`, retry class `refresh`, hint `"Read the entry again, then retry."`, and `path` means `"the entry whose state is not the one the call expected"`.

`data` lets a caller that already holds the state the vid names go on without a read. A caller that does not hold it reads first. Sending the vid from the refusal back without reading replaces the very change the refusal reported, and the reference page says so.

A vid minted by another mount is answered here, as a mismatch, and not at the gate. The merged spec refused it `invalid` before any storage was called.

Reason for one answer: a digest cannot say who minted it, and nothing needs it to. The case that happens is a path whose mount was replaced while a caller, or a session's memory, still held vids from the old one. That caller did nothing wrong, and the true answer is that what is at the path is not what was seen, which is `conflict` and is mended by a read. Reason for carrying the vid: the kind's contract is to say what is there now, and the version alone is half of that. It goes only to a caller who passed the rights check for the change, and every rung that changes a row sits above `read`.

### 13. A storage declares the `vid` trait, and a mount without it refuses a change that requires one

`TRAIT_KEYS` gains `vid`, with one value, `entry_version`. A storage that declares it promises four things:

1. Every row it returns with a version carries a vid of the public shape.
2. Two of its rows carry equal vids when, and only when, they are the same entry at the same version.
3. No vid of another storage equals one of its own, short of a collision.
4. It honours `if_vids`, the mark included, inside the transaction that changes the row, with the answers of decisions 9, 12, 17 and 18.

`DatabaseStorage` declares it on every dialect. `SQLiteStorage`, `PostgresStorage` and `InMemoryStorage` are that class. The in-memory storage has a mount identity of its own for each object, so its vids end with it. A dialect on the generic floor mints and honours as the two engines do, since nothing here is engine-specific. No engine leg tests the floor.

A storage that does not declare the trait fills no vid, and its rows carry a version alone. A call that sends `if_vid` or `if_vids` to its mount is refused `unsupported` by the kernel before the storage is called. A storage that wants the trait may use `VidMint` with any identity that is its own.

Reason: a precondition that a storage silently dropped would be a write the caller believes is guarded and is not. The constitution forbids a silent clobber and requires a capability to be declared, and the listing cursor already works this way.

### 14. The four public faces, the parameter table and the seam carry the same names

- `AsyncVirtualFileSystem` and `VirtualFileSystem` carry `if_vid` and `if_vids` on `write`, `edit`, `delete`, `move` and `restore`, keyword-only. `AsyncSession` and `Session` carry neither, by the ruling of 2026-11-23: a session's verb is the file system's verb without `authority`, `if_vid` and `if_vids`, and the parity test names those three. What a session fills in is spec 3, decision 9 (A session fills in the precondition and, when strict, refuses a change to what it was not shown). Code inside VFS that must state a vid within a session, such as the line's host and a resumed job, states it to spec 3's guarded router and never through a handle. `if_absent` stays on a session's `write`, since it is no vid.
- `PARAMS` gains the two names on the five verbs and loses the two version names on `write`: ten rows join and two leave, so a table of 142 rows holds 150. The signature drift test and the count of integer channels follow: 11, where 12 were.
- `Vid`, `VidMint` and `ABSENT` are exported from `vfs`. `Vid` sits on the Entry reference page beside `ContentHash`, and `VidMint` on the Storage page under "Writing a Storage Backend".
- The glossary gains **Vid**: "A short value on a row that names one entry at one version, which a change can require."

Reason: a name that differs between two faces is found by the caller who crosses from one to the other. The parity tests exist to make that impossible.

### 15. The vid adds no primitive, and Article 1.5 names it in place of `if_version`

This spec manipulates one primitive, the Candidate, which gains a field. A vid is a value on a Candidate, composed of two things the constitution already has: the Entry's identity and its revision, within one Mount. It has no path and needs none. Nothing is found by it: hydrating a Candidate stays a path lookup, and a caller that never passes a vid uses the file system as before.

The third bullet of Article 1.5 becomes: "**Usable for optimistic concurrency.** Every Candidate that carries a revision carries a *vid*, an opaque value composed of the Entry's identity and its revision. A caller MAY pass `if_vid=vid` on a change; a mismatch MUST surface as `Conflict` in the error taxonomy (Article 2). A revision alone is not a precondition: two Entries can stand at one path, one after the other, at the same revision."

Article 1.3's list gains: "`vid` — present wherever `revision` is; see §1.5."

Article 3 holds by decision 20. Article 2 holds: the refusals are four kinds of the closed taxonomy. Article 4 holds: the capability is declared by a trait and read without running a verb. Article 5 holds: a change with `if_vid` is revision-guarded, and one without is last writer wins, as each docstring says.

Reason: Article 1 allows five first-class things. A sixth would be the most expensive mistake this spec could make, and it is avoided by making the vid a fact about a row and never a name for one.

### 16. Four landings, in this order

1. The vid on every row: `vid.py`, `ULIDBytes`, the mint at each site, the trait, the merge rule, the exports of `Vid` and `VidMint`, and `vid` beside `version` in the `data` of `conflict` and `exists`. No argument changes.
2. `write` takes `if_vid` and `if_vids` with the mark of decision 18, `ABSENT` is exported, `stale_vid` of decision 19 takes the place of `stale_version`, and `if_version` and `if_versions` leave, in one landing.
3. `edit` takes them.
4. `delete`, `move` and `restore` take them, and the planned page `documentation/reference/planned-api/vids-and-preconditions.md` is removed, with its row in `planned-api/index.md`, once the reference pages say what it says.

Three things are placed by the review of 2026-11-23. The constitution and the roadmap rows change in the second landing, with the argument they name, so that at no commit does Article 1.5 offer an argument the code has lost. `ABSENT` is exported in the second landing, when something first accepts it. In the first landing `stale_version` stays and gains `vid` in its `data`; `stale_vid` takes its place in the second.

Spec 5's first landing needs the first of these, for the mint. Spec 5's fourth carried `if_vid` on `restore` only if no landing here did, and the fourth here does.

Reason: each leaves the tree green and is of use alone. The first lets a caller see what it would require. The second swaps the precondition in one step, so at no commit does `write` have two or none.

### 17. `restore` takes `if_vid` and `if_vids`, and they name the tombstone

```python
async def restore(self, path=None, observations=None, *,
                  if_vid: Vid | None = None, if_vids: Mapping[str, Vid] | None = None,
                  authority: Authority | None = None) -> Result: ...
```

The seam's `restore` takes `if_vids: Mapping[Path, Vid] | None`, under the rules of decisions 6, 8 and 13.

- The precondition holds when the tombstone the restore would clear has the vid given. It is judged after the ladder has found a deleted root with live parents and after the caller's permit, and before the row is claimed.
- Every earlier answer of the ladder stands, with or without a precondition: no row is `not_found`, a live row is `exists`, a row inside a deleted tree is `not_found` naming its root, and a deleted parent is `not_found` there.
- A mismatch is `conflict` with the tombstone's version and vid, and nothing is restored. A batch with one stale key restores nothing.
- The claim that follows already compares both: `entry_id = ? AND version = ? AND deleted_at IS NOT NULL` on SQLite, and the same three terms over a `VALUES` join on Postgres. No term and no statement is added.
- A rival that revives the row inside the window moves its version. The claim matches no row, the verb runs again, and the answer is `exists`.

A tombstone's vid is the one its row carries in the trash view. The row a `delete` returns carries the vid of the row before the delete (decision 4), which is the tombstone's only for a row deleted beneath a directory. A storage that reports its changes gives the tombstone's own, as spec 5, decision 2 does.

This reverses the line of round one that left `restore` with no precondition.

Reason: spec 5, decision 7 (An entry is put back only while it is as the session's last change left it) shows the case. A session deletes a file, another caller restores it, edits it and deletes it again, and a restore with no precondition brings back the other caller's edit as the session's file. The tombstone's version tells the two deletes apart, and the claim already carries it.

### 18. The mark `ABSENT`, in place of a vid, requires that the path holds no live row

```python
# src/vfs/vid.py
ABSENT: Final = "absent"      # no vid has this shape, and it is plain JSON
```

`if_vid` is typed `Vid | Literal["absent"] | None`, and a value of `if_vids` `Vid | Literal["absent"]`.

- **On `write`,** the entry at a marked path only creates. A live occupant, a file or a directory, is `exists` with the occupant's version, hash and vid. A tombstone counts as absent and is revived. This is `if_absent` for one entry, so one batch can require a vid at some paths, nothing at others, and leave the rest plain.
- **On the single form of `write`,** `if_vid=ABSENT` is `if_absent=True` under another spelling. It exists so that a saved precondition has one shape for every path.
- **On `edit`, `delete` and `move`,** a live row at a marked path is `conflict` with its version and vid. With no live row there the verb goes on and answers what it answers for such a path, which is `not_found`.
- **On `restore`,** the mark is lawful and adds nothing: the ladder already answers a live row `exists`. It is admitted so that one mapping serves every verb.
- **`if_absent=True`** stays, applies to every entry, and is still refused beside `if_vid` and `if_vids`.
- **A tombstoned directory at a marked path** is `wrong_kind` with the trashed hint, as `if_absent` answers today: a file write revives a file and never a directory.
- **Rights.** A call is judged at `add` when `if_absent=True`, when it is an append, or when every file entry carries the mark. Any other call is judged at the verb's own rungs, and the rung is the call's and never the entry's: in a mixed call a marked entry over a row the caller may not change answers `permission_denied`, as a plain one does.
- **A create that loses its name to a rival.** A marked entry answers `exists` and never lands on the rival's row. An unmarked one lands on it, as today. `StagedEntry` gains `exclusive: bool`, read where the call-wide flag is read today.
- **Statements.** The files of one depth are inserted in at most two groups, marked and unmarked, where they are one group today. A batch that mixes the two issues at most one more insert for each depth it creates at. A batch of one kind issues what it issues today.

Reason: two specs need it and neither can do without soundly. Spec 3, decision 9 writes a strict session's batch of read and unread paths, and without the mark it is two calls, the second of which can fail after the first has landed. Spec 7, decision 22 carries out a saved batch in which the preview found some paths empty, and without the mark those paths are not guarded at all. Reason for a word and not `*`: a `*` reads as anything at all, and to a caller who knows HTTP's `If-Match: *` it reads as something is there, which is the opposite.

### 19. One constructor makes the refusal of a failed precondition, for a storage and for the kernel alike

```python
# src/vfs/results/envelope.py, beside already_exists and wrong_kind; exported from vfs.results
def stale_vid(path: Path, version: int, vid: Vid) -> ResultError: ...
```

It returns `classified(ErrorKind.conflict, path, detail="the vid required is not the vid of what is stored", data={"version": version, "vid": vid})`, which is not retryable. The plan, the three ladders and the lost-guard probe call it. It replaces `stale_version` of `staging.py`, and decision 7's sentence that `stale_version` becomes `stale_vid` there now reads: it moves here.

Reason: spec 7, decision 13 (The preview is computed once, as the caller, for seven verbs, and every part of it is bounded) refuses a step whose own `if_vid` is already stale before it stores a job, from rows a `stat` returned. That refusal must be the one a storage would give, word for word and key for key, and one function is how two places stay the same.

### 20. Where this spec leaves Plan 9 and Unix it says so, with the constraint that moved it

Article 3 of the constitution has VFS follow a convention of Plan 9 or Unix wherever one exists, and requires a deviation to be a numbered decision that names the principle, the deviation, the motivating constraint and the expected expiry. This is that decision. The section "Prior art, and where this spec departs" lists each point where a convention exists, what this spec does, and for each departure the four things the Article asks for. The points where the behaviour is older than this spec are listed too, marked as inherited, because this spec builds a guarantee on them.

Reason: a caller who knows `O_EXCL`, `rename` and `ESTALE` should be able to predict this API, and where it cannot, the place to learn why is the spec that decided it.

## Cost

Costed against the reference deployment in the working agreement.

**Per verb call, about 150,000 a day.** No read issues a statement for the vid. A read that did not select the entry id selects 16 more bytes from a row it already reads. Each row costs about 1.1 µs to fetch the id and mint, on rows that cost 7.3 to 18.0 µs today: 12 to 15% for `ls`, `tree` and `glob`, and 6% for `grep` and a batch `stat`. Each row is 30 bytes longer in compact JSON, on 185, and holds 69 bytes more in memory. A 10,000-row listing pays about 11 ms, 300 KB on the wire and 690 KB in memory. About three calls in four are reads. At an assumed 50 rows a read, that is 5.6 million rows and about 6 seconds of processor a day. The 50 is an assumption. No measurement of rows per call exists.

**Per file write, about 1,050,000 a day.** No statement, no bind and no stored byte. One mint for the result row, and one more where the change requires a vid, at 1.2 µs each: under 3 seconds of processor a day.

**Per index visit, about 11,000,000 a day.** Nothing. The index path builds no row with a version, and a `rebuild` returned none.

**Per batch, 100 a night.** A 10,000-entry write with a key for every row mints 20,000 vids, about 25 ms of a call measured at 1.3 s. The keys never enter a statement, so the statement count is the count without keys and no chunk changes size. The mapping holds 10,000 paths and 10,000 twenty-character values. A batch with one stale key writes nothing.

**The mark.** A batch that mixes marked and unmarked creates issues at most one more insert for each depth it creates at, bounded by the depth of its deepest path and not by its size. No other batch changes.

**A restore.** No statement, as a delete: 6 at the seam with and without the precondition.

**Per corpus.** Nothing. There is no column, no backfill and no pass.

**Per lock.** None is taken and none is held longer. The comparison is made in Python between two statements the call already issues, inside the transaction it already holds. No reader waits on anything new.

**A refused change.** A stale `write` or `edit` costs the snapshot and no mutation statement. A stale `delete` or `move` costs its reads and no mutation statement.

**What grows with input.** The mapping grows with the batch, as `entries` does, and never enters SQL. The vids of a result grow with its rows, and a page bounds both. No statement, bind list or chunk grows, and no dialect profile gains a field.

**The mint, if it ever shows in a profile.** The direction is one call into `crates/vfs-core` that mints a whole listing's vids. It is not built, and nothing here is capped for want of it.

## Left as it is

- **`copy`, `mkdir`, `sweep`, `mkedge` and `rmedge` take no precondition.** A copy changes no source and replaces no destination. `mkdir` lands only on a free path. `sweep` runs retention or destroys a subtree named whole, and no caller is known that reads before it. Specs 3 and 7 pass none on `copy` and `mkdir` either (spec 3, decision 9; spec 7, decision 22).
- **A read that returns nothing when a vid still holds.** The vid is what such a read would take. No caller for it is known.
- **`entry_id` on `stat`.** The kernel plan lists it as not built. No precondition needs it now.
- **A precondition on the body's hash.** The earlier decision stands.
- **A request key, and a change that lands exactly once.**
- **The parent's new vid on the result of a change.** A change that adds or removes a child moves its parent's version and reports the child alone. A caller that holds the parent's vid from before its own change reads the parent again before it requires it. A session does not have to: it learns the parent's new vid from spec 5's `bumped` change, which is private to a result, and carries its stamp forward (spec 3, decision 11).
- **A value on a row that names its entry alone.** No row says which entry it is apart from its version. Two rows are known to be one entry only when their vids are equal. No spec asks for more: spec 3, decision 5 (One stamp per path is current, and the stamp that arrives last is the current one) orders stamps by arrival, and its decision 10 (An append is never held to a stamp, and moves one only when it landed directly on it) compares a stamp with the vid before a change, which spec 5, decision 2 reports.
- **`vid` in the default text of a listing.** It is in the row and not in the default projection, as `version` is.
- **The shell's host.** It keeps its pair of version and hash. A vid is that pair in one value, and the host can hold it when it is next changed.
- **A copy of a database.** A file copy or a dump restored elsewhere carries the mount identity and every entry id with it. Vids minted against one are honoured by the other wherever their versions line up. Telling two copies apart is a change to provisioning.
- **Version rows.** No verb serves them. The one seam that reads an old body is spec 5, decision 5 (A rollback reads the files through two storage methods, `find_entries` and `read_versions`, and no public verb is added). It takes a version number, kept beside the vid by whoever asks.
- **The kinds a session answers with, `vfs.conflict.unread` and `vfs.conflict.changed`.** They are spec 3, decision 12's.
- **A directory entry of a batch under the mark.** A key names a file of `entries`, so a directory entry is made or left as a plain write leaves it. `mkdir` without `exist_ok` is the create-only form for a directory.

## Tests

Each is written and seen failing before the code. Counts are of statements recorded by the `before_cursor_execute` listener the write tests use, of rows, of errors, or of calls to a spied function. Never of time. A row of the storage contract runs on memory, on SQLite and on the Postgres leg.

`tests/test_vid.py`, new:

- `test_a_vid_is_twenty_lowercase_hex_characters`: 1,000 mints, 1,000 that pass `is_vid`.
- `test_one_entry_at_one_version_has_one_vid_and_no_other_row_shares_it`: 10,000 pairs of id and version give 10,000 distinct vids; each pair minted twice gives 0 differences; a mint with another mount identity gives 0 equal of 10,000.
- `test_is_vid_refuses_each_malformed_value`, parametrized over 9 values: 19 characters, 21 characters, an upper-case letter, a `g`, a quoted vid, an empty string, an integer, bytes, `None`. Each is false.

`tests/models/test_rows.py`:

- `test_the_id_reads_as_bytes_and_as_text_alike`: for 1,000 stored rows, `ULIDBytes` and `entry_key_of(text)` give 0 differences.

`tests/models/test_models.py`:

- `test_vid_is_a_field_no_model_owns`: `"vid"` is in `OBSERVATION_QUERY_FIELDS`, and `Entry.to_observation()` leaves it out of the mask.

`tests/results/test_result_laws.py`:

- `test_a_merged_vid_agrees_or_is_null`: equal vids are kept, differing ones are null and still masked, a nulled version nulls the vid, equal versions under differing vids are nulled too, and the law holds in both orders and applied twice. 5 cases.

`tests/test_params.py`:

- The drift test passes with the new names. `test_every_int_channel_enforces_the_shared_ceiling` counts 11.
- `test_garbage_classifies_invalid_with_zero_dispatch` gains one case for each rule of rows 1 to 5 of decision 8, on each of the five verbs where the rule applies: 0 storage calls each.
- `if_version` and `if_versions` are in no signature of the four faces and not in `PARAMS`.

`tests/base/test_dispatch.py`:

- `test_if_vid_reaches_the_storage_keyed_by_its_own_path`, one case for each of the five verbs: the recorder storage receives one key, with the mount's prefix off.
- `test_if_vids_go_to_the_mount_of_each_key`, for `write`, `edit`, `delete`, `move` and `restore`.
- `test_a_key_that_names_no_target_of_the_call_is_invalid` and `test_if_vids_that_names_one_path_twice_is_invalid`: 0 storage calls.
- `test_a_mount_whose_storage_issues_no_vid_refuses_a_required_change`: `unsupported` at the mount's path, 0 storage calls, and the same call without `if_vid` reaches the storage once.
- `test_a_call_that_requires_nothing_passes_no_if_vids`: the recorder receives no such argument.

`tests/support/storage_contract.py`, a new class `TestVid`:

- `test_every_row_with_a_version_carries_a_vid`, parametrized over 19 calls: `read`, `stat`, `ls`, `tree`, `glob`, `grep`, `search`, `traverse`, a `write` that creates, one that updates, one that is unchanged, `edit`, `mkdir`, `move`, `copy`, `delete`, `restore`, a `sweep` of a subtree, and an `ls` of the trash view. For each row, the count of rows where `version` and `vid` are not both set or both unset is 0, and so is the count where their masks differ.
- `test_a_bare_row_carries_no_vid`: under an everyone level of `list`, `stat` and `ls` return 0 vids.
- `test_one_row_has_one_vid_from_every_verb`: `stat`, `read`, `ls` and `glob` of one file give 1 distinct vid.
- `test_what_moves_a_vid_and_what_keeps_it`, 10 cases from decision 3: a new body, the same body, an edit, an append, a delete and a restore, a delete and a write, a move, a parent moved, a parent deleted and restored, a copy.
- `test_a_matching_vid_updates`, and `test_a_stale_vid_is_conflict_and_writes_nothing`: one `conflict`, `data` equal to the version and the vid a `stat` then returns, `retryable` false, and the body unchanged.
- `test_a_path_freed_by_a_move_is_refused`, parametrized over the 4 rows of "The problem": each is `conflict`, and the file now at the path keeps its body. All four pass with `if_version` today.
- `test_a_write_with_a_vid_sent_twice_is_unchanged`, and `test_a_vid_on_no_live_row_is_not_found` for an absent path, a missing parent with `parents=True` and a tombstone with the trashed hint.
- `test_a_vid_minted_by_another_storage_is_conflict`: a vid from a second storage of the same class, for a file at the same path and version, is refused.
- `test_stale_keys_refuse_the_whole_batch_and_each_is_named`, and `test_an_append_with_a_vid_lands_at_most_once`.
- `test_twenty_writers_that_require_one_vid_land_once`: twenty writes at once, each with a body of its own and the same vid, give 1 success and 19 `conflict`.
- `test_an_edit_with_a_stale_vid_is_conflict_before_any_text_is_matched`: an edit whose `old` is not in the file and whose vid is stale answers 1 error, `conflict`. An edit sent twice with one vid answers `conflict` the second time.
- `test_a_delete_requires_what_it_was_shown`: a stale file is `conflict` and stays live; a matching one is deleted; a tombstone is `not_found`; a directory with a child made since is `conflict` and the count of live rows beneath it is unchanged; a directory with a grandchild made since is deleted; an empty directory with a child removed since is `conflict` without cascade, and is deleted with no `if_vid`.
- `test_a_batch_delete_with_one_stale_key_deletes_nothing`: 0 rows tombstoned.
- `test_a_move_requires_its_source`: a stale source is `conflict`, the source is still at its path and the destination is empty; a matching one moves, and the result's vid differs from the one required; an occupied destination is `exists` with or without `if_vid`.
- `test_an_exists_names_the_vid_of_what_is_there`.
- `test_the_storage_declares_the_vid_trait`.
- `test_a_required_vid_over_a_directory_is_conflict`: a `write` and an `edit` that require a file's vid at a path a directory now holds each answer 1 `conflict`; the same `write` with no vid answers `wrong_kind`.
- `test_a_restore_requires_its_tombstone`: the vid the trash view shows restores the file; the vid the delete's row carried is `conflict` with the tombstone's version and vid, and the row stays deleted; a file deleted, restored, edited and deleted again by another caller is `conflict` for the vid of the first tombstone; a live row is `exists` and a missing one `not_found`, with or without the argument; a batch with one stale key restores 0 rows.
- `test_the_mark_creates_and_never_replaces`: in one batch of three files, one with a vid, one with the mark and one plain, all three land when the first matches and the second path is empty; with the second path occupied the batch writes 0 rows and answers 1 `exists` with the occupant's version, hash and vid; a tombstone at the marked path is revived.
- `test_the_mark_on_a_change_of_what_is_there`: `edit`, `delete` and `move` with the mark over a live row each answer `conflict` with its version and vid, and over an empty path each answer `not_found`.
- `test_twenty_marked_creates_of_one_path_land_once`: 1 success and 19 `exists`, in batches that each also replace a file of their own.
- `test_a_call_of_marked_entries_alone_is_judged_at_add`: a caller who holds `add` creates through the mark, hears `exists` over another's file, and is `permission_denied` when one entry of the call is unmarked and lands on another's file.

`tests/storage/database/test_writes.py`, class `TestRequiredVid` in place of `TestExpectedVersion`, on a SQLite file at the seam as the system actor:

- `test_a_stale_vid_runs_the_snapshot_and_no_write`: 1 statement, a `SELECT`.
- `test_a_key_for_every_row_adds_no_statement`, for 100 files and, marked `slow`, 10,000, with the membership budget narrowed to 1,000: the list of statement verbs equals the list of the same write without keys. With one stale key the batch fails whole with 0 mutation statements.
- `test_a_required_vid_mints_twice_for_each_row`: a 10,000-entry write with a key for every row calls `VidMint.mint` 20,000 times. Marked `slow`.
- `test_a_row_that_lost_its_guard_names_what_is_at_its_path`: a rival staged on the attempt's own session at the `write:before-apply` seam, as today's test of the probe stages it (`tests/storage/database/test_writes.py:1990`), gives `conflict` with the rival's version and vid; a rival that moved the row away gives `conflict` with no `data`. It tests the probe, which both engines declare and neither reaches from a second connection. The generic floor runs the call again.
- `test_a_required_vid_adds_no_statement_to_an_edit`: the list of statement verbs with `if_vids` equals the list without, on twin files, and counts 7. A stale one issues 1 statement, the snapshot.

`tests/storage/database/test_trash.py` and `tests/storage/database/test_topology.py`, at the seam as the system actor:

- `test_a_required_vid_adds_no_statement`, in `test_trash.py` over a delete of a file, a cascading delete of a directory and a delete of an empty directory without cascade, and in `test_topology.py` over a move of a file within one directory: the list of statement verbs with `if_vids` equals the list without, on twin fixtures. The counts are 4, 5, 6 and 16.
- `test_a_stale_vid_issues_no_mutation_statement`, over the same four: 0 statements that begin `INSERT`, `UPDATE` or `DELETE`.
- `test_a_ten_thousand_target_delete_with_a_key_for_every_row_adds_no_statement`. Marked `slow`. The same for an `edit` of 10,000 rows, in `test_writes.py`. These are the sizes spec 7, decision 22 carries.
- `test_a_restore_that_requires_a_vid_adds_no_statement`, in `test_trash.py`: the list of statement verbs equals the list without, and counts 6; a stale one issues 0 mutation statements.
- `test_a_batch_that_mixes_marked_and_plain_creates_issues_one_more_insert`, in `test_writes.py`: a batch of 100 marked and 100 unmarked new files in one directory issues 2 inserts on `vfs_entries`, where 200 of one kind issue 1.

`tests/storage/database/test_reads.py`:

- `test_a_read_issues_the_statements_it_issued_before_the_vid`: on the fixture of "What the code does today", through the kernel as the system authority, the eight read verbs issue 1, 1, 2, 2, 1, 7, 8 and 3 statements.
- `test_a_listing_mints_once_for_each_row`: a `glob` of 10,000 rows calls `VidMint.mint` 10,000 times, and one whose rows are all bare calls it 0 times. Marked `slow`.

`tests/storage/database/test_races.py`, on the Postgres leg:

- `test_a_rival_inside_the_window_refuses_a_required_change`, for `write`, `edit`, `delete` and `move`: a rival that wrote inside the window leaves the rival's state, and the call answers `conflict`. For `write`, a rival that moved the row away, and one that deleted it, answer `not_found`, the second with the trashed hint.

`tests/storage/database/test_engine.py`:

- `test_two_storage_objects_over_one_database_mint_one_vid`: two storages opened on one SQLite file return 1 distinct vid for one row, and a storage on another file returns another for a file at the same path and version.

`tests/results/test_results.py`:

- `test_stale_vid_is_the_refusal_a_storage_gives`: the error `stale_vid` builds equals, field for field, the one a stale `write` returns from the database storage.

`tests/test_sync.py`: the twin tests pass with the new arguments on the synchronous file system. The synchronous session carries none.

`tests/base/test_authority.py`:

- `test_session_verbs_take_no_identity_argument`, which removes `authority` alone today: for each of the 25 verbs, the file system's parameters without `authority`, `if_vid` and `if_vids` are the session's, name for name.

Every test that passes `if_version` or `if_versions` is rewritten to read the row and pass its vid: 66 uses in `tests/test_params.py`, `tests/base/test_dispatch.py`, `tests/support/storage_contract.py`, `tests/storage/database/test_writes.py` and `tests/storage/database/test_races.py`. The recorder storage in `tests/support/base_doubles.py` declares the trait. A test that compares a whole row gains the field.

## Scope

In:

- New: `src/vfs/vid.py`.
- `src/vfs/__init__.py`, `src/vfs/models/__init__.py`, `src/vfs/models/entry.py` (`Observation.vid`, the field partition), `src/vfs/models/rows.py` (`ULIDBytes`, `entry_key_of`).
- `src/vfs/params.py`, `src/vfs/base.py`, `src/vfs/session.py`, `src/vfs/sync.py`, `src/vfs/sync_session.py`.
- `src/vfs/storage/protocol.py` (the seam, the trait vocabulary).
- `src/vfs/storage/backends/database/`: `engine.py` (the mint, built at first touch), `backend.py` (the trait, the arguments), `reads.py`, `listings.py`, `grep.py`, `search.py`, `traverse.py` (the id and the mint on each row), `staging.py`, `writes.py` (the plan's comparison, the rows of a result, the `data` of two refusals), `serialized.py`, `trash.py`, `topology.py` (the comparison in each ladder, the rows of a result).
- `src/vfs/results/envelope.py` (the merge rule, `stale_vid`), `src/vfs/results/__init__.py`, `src/vfs/results/kinds.py` (the words of `conflict`).
- The tests above.
- `tests/lint/test_code_shape.py`: `LAYERS` gains `vfs.vid` on the rung of `vfs.paths`, since it imports the standard library alone and the models import it, and `vfs.preconditions` on the rung of `vfs.cursor`, below `vfs.base`. `vfs.vid` joins `IMPORTS_NO_VFS_MODULE`. No rung is loosened and no upward import is admitted.
- The size gate. `MODULE_LINE_BASELINE` holds each module over 1,000 lines at its exact count and fails one that grows (`tests/lint/allowlist.py:11-12`, `26-33`). Five of its six modules are in this scope, and two more sit just under the ceiling. Where the new code goes is decided here, so that a baseline is raised by this spec and not in the build. Each figure is an estimate made before the code is written; the build sets each baseline to the count it reaches and says in its pull request where that differs.
  - **A new module, `src/vfs/preconditions.py`, beside `cursor.py`,** takes the routing of `if_vids` keys to mounts, the two rules that need resolved paths (a key names a target, and no two keys name one path) and the check of the trait. It takes the routing `base.py` does for `if_versions` today, a loop at `base.py:2491-2501`, so that loop leaves `base.py`.
  - **`base.py`, 3,090:** two arguments on five verbs, a paragraph in each of five docstrings, and one call a verb into the new module. About 60 lines more.
  - **`backend.py`, 1,509:** `if_vids` passed through five methods, the trait, and the mint handed to each builder of a row. About 15 lines more where the mint rides on an object the builders are already passed, and about 45 where it is one more argument at each of the 29 calls that pass `host.tables`. The first is the one to build.
  - **`writes.py`, 1,415:** the comparison at settle, `exclusive`, and the second insert group of the mark. About 40 lines more. `staging.py` takes `expected` in place of `expected_version` and is under the ceiling.
  - **`reads.py`, 1,164:** `DERIVED_FIELDS`, the id in the select list, and the mint where a row is built. About 20 lines more.
  - **`engine.py`, 1,008:** one `VidMint` built at first touch. About 5 lines more. Spec 0's first landing splits this module and lowers its count; whichever lands second takes the other's number.
  - **`results/envelope.py`, 948,** gains the merge rule and `stale_vid`, about 25 lines, and **`search.py`, 979,** gains the id and the mint, about 6. Both stay under 1,000 and neither joins the list. If either would pass it, the new code moves to a module of its own first.
- The docs below.

Out: everything under "Left as it is", the schema, `crates/`, the shell, and every session rule.

The landings are decision 16's four. Each is green under `scripts/ci.sh` and `scripts/docs.sh check` alone. The Postgres leg runs before the pull request of each of the four: the first changes `models/rows.py` and every read path of the database backend.

## What the docs must say

- A row carries a vid wherever it carries a version. A vid names one file or directory at one version. It is compared and never taken apart.
- `if_vid` is how a caller that reads, changes and writes back avoids replacing a change, or a file, it never saw. It works on `write`, `edit`, `delete`, `move` and `restore`. `if_vids` is the same for a batch.
- `ABSENT` in place of a vid requires that nothing is at the path. In a batch write it makes one entry create-only.
- A restore that requires a vid requires the deleted row's, which the trash view shows.
- A `conflict` names the version and the vid that are there now. Read the file again before sending them back.
- A vid changes when the row changes, and stays the same when a directory above it is moved, deleted or restored.
- A directory's vid changes when something is added to it, removed from it or renamed in it, and not when something deeper changes.
- A storage that issues no vid refuses a change that requires one.

Pages, each changed: the docstrings of `write`, `edit`, `delete`, `move` and `restore` on `AsyncVirtualFileSystem`, which are the reference pages of the four faces; the `Observation` docstring, with `Vid` on `documentation/reference/python-api/entry.md` and a line on `index.md`; the `ErrorKind` docstring for the `data` of `conflict` and `exists`; `documentation/reference/python-api/storage.md` for the trait, its four promises and `VidMint`; `documentation/reference/glossary.json` and `glossary.md` for the term; `context/standards/constitution.md`, Articles 1.3 and 1.5; `context/standards/roadmap.md`, the rows of stories K2 and K10 that name `if_version`. `documentation/reference/planned-api/vids-and-preconditions.md` is removed in the fourth landing, with its row in `planned-api/index.md`, once the reference pages say what it says.

## Earlier decisions this reverses

- `agents/2026-11-20-write-takes-preconditions-and-an-append/`, decision 1: `if_version` and `if_versions` leave. Its reason, that a version is the one coordinate every reader holds, now holds of the vid. Its decisions 4 to 6 stand with the vid in the version's place. Its decision 10 gains `vid` in the `data` of `conflict` and `exists`. Its line under "Left as it is" that `edit`, `delete` and `move` take no expected version no longer holds. Its decision 11, no hash precondition, stands.
- The same spec's rule that a write which lost its guard reports the version of the row it probed: where that row has moved away, the refusal now carries no `data`.
- The same spec's decision 2, that one call cannot mix create-only rows with plain rows: the mark of decision 18 lets it. And its table's row for a live directory under an expected version, `wrong_kind`: under a required vid it is `conflict`.
- The spec merged from pull request 42, decision 2, in four places. The storage mints, where the router did. A vid from another mount is `conflict` from the storage, where it was `invalid` before any storage was called. A delete of a directory without cascade compares the entry and the version, where it compared the entry alone. The batch forms of `edit`, `delete` and `move` take `if_vids`, where only `write` did. Its sentence that `if_vid` is exclusive with `if_version`, and its decision 4's sentence that an explicit `if_version` reaches storage unchanged, have nothing left to speak of.
- `context/standards/constitution.md`, Article 1.5, third bullet: reworded as decision 15 gives it.
- `context/standards/roadmap.md`, story K10: it stamped the `entry_id`, the version and the hash, and filled in `if_version`. The vid is the stamp, and `if_vid` is what is filled in.

## Prior art, and where this spec departs

Read on 2026-11-23 in the clones and at the lines the research memo `research/2026-11-23-how-unix-plan-9-and-linux-name-a-file-in-a-state.md` records. The memo was written before the ruling that named the value `vid`, and uses the first name.

Where this spec agrees:

- **The name of a file in a state is an identity and a counter.** Plan 9's qid is a path that is never reused and a version that moves when the file is modified. Unix has the inode number with a generation, and Linux adds a change counter. The vid is made of the same two things, the entry id and the version.
- **Two names are the same file in the same state when the two values are equal.** That is Plan 9's rule for two qids, and it is the one thing a vid is for.
- **What moves a directory's counter.** In fossil, cwfs, ext4, FFS and V7 a directory changes when a direct child is made, removed or renamed, and not when a child's body changes. The version of a directory here moves the same way, which is all decision 10 claims for it.
- **A stale name is `ESTALE`.** A file handle whose generation is wrong is refused `ESTALE`, and so is a handle from another file system. A stale vid and a vid from another mount are both `conflict`, the kind the code maps to `ESTALE`.
- **A change with no precondition lands, and the last writer wins.** No change requires a state. `write` replaces as `creat` and the shell's `>` do, and refusing to replace is opted into, as `noclobber` is.
- **Create-only is `O_EXCL`.** An occupant of any kind, a directory too, is `exists`, as `O_CREAT|O_EXCL` answers `EEXIST`. An append is outside the rule, as `>>` is.
- **The validator is opaque, as Unix has it.** An NFS file handle is opaque to its client, and Linux does not let user space read its change counter. The vid is a digest for the same reason: a caller that can take a validator apart will.
- **Removing a directory, a mount point, and crossing a mount** answer `not_empty`, `busy` and `cross_mount`, which are `ENOTEMPTY`, `EBUSY` and `EXDEV`.

Where this spec departs. Each row is a deviation under Article 3.

| The convention | What this spec does | The constraint that moved it | Expiry |
|---|---|---|---|
| No write, remove or rename in 9P or POSIX can carry the state it was read in. | The plain call is kept as it is. `write`, `edit`, `delete`, `move` and `restore` may also carry `if_vid`, and a session carries it for its caller. | The callers this system is built for read a file and change it later, with other callers between, and the lost update is the commonest harm of that loop. It is an addition and never a demand. The nearest relatives are NFSv3's guarded `SETATTR`, git's `update-ref` with an old value, and HTTP's `If-Match`. | None. |
| Plan 9 shows the whole qid: its path, its version and its type. Unix shows the inode number. | A row shows the version and the kind, which are the qid's version and type. The entry id, which is the qid's path, never leaves the storage, and the vid cannot be taken apart. | Article 3 already rejects raw inode exposure, and the models carry no database identifier by rule. | When a caller is found that must tell the same entry at another version from another entry; "Left as it is" names the field that would serve it. |
| The word is qid. | The word is `vid`, for version and id: Plan 9's style, and not Plan 9's word. | A qid shows its parts and a vid does not, so the same word would promise what is not there. | None. |
| Create-only is a flag of its own, `O_EXCL`. | `if_absent=True` is that flag. The mark `ABSENT` is also given where a vid is given. | One mapping must be able to require a vid at some paths and absence at others, so that a batch fails whole (decision 18). git's `update-ref` does the same with an all-zero old value. | None. |
| A file expected where a directory stands is `EISDIR`. | Under a required vid it is `conflict`. Without one it is `wrong_kind`, as before. | The caller named a file it had read; that a directory took its place is the file changing, and one read mends it (decision 9). | None. |
| A write always moves the file's counter, in Unix and in Plan 9. | A write of the body the file holds moves nothing and answers `unchanged`. | A call sent twice must be recognisable. Article 1.5 lets a write that changes nothing keep its revision. Inherited from the write-preconditions spec, decision 5. | None. |
| A name removed and made again is another file: a new qid path, a new inode or generation. | A write at a deleted path revives the row, which keeps its entry id and takes a later version. | The trash keeps a deleted row at its address so that it can be restored. Inherited. The version moves, so no vid from before the delete matches. | When the trash design changes. |
| A removed file occupies nothing. | A tombstone holds its address: a move onto it is `exists`, a restore requires its vid, and the mark counts it as absent. | The same. Inherited. | When the trash design changes. |
| POSIX `rename` replaces what is at its destination, atomically. | A move never replaces. This is Plan 9's rule for a rename and Linux's `RENAME_NOREPLACE`. | No verb destroys but `sweep`. Inherited. Decision 11 rests on it: a destination that is never replaced needs no precondition. | None. |
| A rename of a file onto itself succeeds and does nothing. | With a stale vid required it is `conflict`. | The precondition is judged before any other fact about the source, so that a refusal never depends on the destination. | None. |
| Two names are one file when their device and inode, or their qid paths, are equal. | No row says which entry it is apart from its version. | No caller needs it yet, and the field that would say it is the identifier the models keep out. | When a caller needs it. |

One difference is neither agreement nor a decision: a rename inside one directory moves that directory's version by two, where Unix changes the directory once. It makes no vid match that should not.

## Choices for the owner

Each is decided above. The decision stands until it is ruled on. One choice of round one is ruled and is gone from the list: a vid cannot be taken apart, for all nine specs. One of round two is gone because nobody asks for it now: a field on every row that names its entry alone.

Stated on 2026-11-23: no change requires a state. A change with no precondition lands as it does in Unix, and the last writer wins. A precondition is a convenience that a caller or a session chooses, never something the kernel demands, and a caller may leave it off.

Ruled on 2026-11-23: the value is named `vid`, for version and id, and the arguments are `if_vid` and `if_vids`. The first names in this spec were HTTP's, `etag`, `if_match` and `if_matches`, and every spec, guide and planned page was renamed in one pass on that day, with this work directory. The name is in Plan 9's style, beside `qid`, `fid` and `uid`, and is not `qid` itself: a qid shows its parts, and a vid is compared and never taken apart. A vid is not an id that stays with a file: it names one entry at one version, and changes when the version does.

Ruled on 2026-11-23, with choice 1: the vid is the session's to carry. A session keeps the vid of each file it was shown and fills in the precondition on each change (spec 3, decision 9). A caller that states `if_vid` by hand is the rare case, and keeps the vid itself. A model is never asked to copy a vid. A session's verbs therefore take no `if_vid` and no `if_vids`: only the file system's do (decision 14). Reason: a rule held by the signature cannot be missed by a tool schema built from a session.

1. **Ruled on 2026-11-23: `if_version` and `if_versions` leave** (decision 7). The other choice kept them beside `if_vid`, exclusive with it, with the four unsound cases written into the docstring. Specs 3 and 6 had taken the decision: spec 3's Builds on, and spec 6, decision 2, whose step classes carry `if_vid` and `if_vids` once this spec has landed.
2. **Ruled on 2026-11-23: a directory is matched by its entry and its version on every verb** (decision 10). The other choice was the merged spec's, the entry alone on a delete without cascade, at the price of a vid in two halves. The caller that emptied a directory itself, the one case this rule handles awkwardly, is designed around for a session: spec 3's decision 11 sends a directory's vid and carries it forward through the session's own changes, from spec 5's `bumped` change.
3. **Ruled on 2026-11-23: a vid from another mount is `conflict`, answered by the storage** (decision 12). The other choice put a mount tag in clear at the front of the vid and refuses a foreign one `invalid` at the mount.
4. **Ruled on 2026-11-23: every listing row carries the vid** (decision 4), at 1.1 µs and 30 bytes a row. A row with a version and no vid would be a guard that fails with no sign. The other choice carried it only where `columns=` names it, and a session then reads each row again before a change.
5. **Settled by the ruling above: the batch forms of `edit`, `delete`, `move` and `restore` take `if_vids`** (decisions 6 and 17). A session fills in the precondition of a batch (spec 3, decision 9), so the batch forms must take one, or a session's batch would be split and would no longer fail whole.
6. **A `conflict` carries the vid that is there now** (decision 12), in its `data` and never in its words. By the ruling above the kind's hint names no vid, since a model is never asked to handle one. The other choice carries the version alone, so that no caller can send the vid back unread. Only a caller that states a vid by hand, with no session, meets this refusal. A session's own two refusals carry neither.
7. **Settled by the ruling above: a required vid met by a directory is `conflict`** (decision 9). The vid comes from a session's memory of a file, and a directory now at the path is a file that changed, which one read mends. `wrong_kind`, as an expected version has it today, would say nothing of what became of the file.
8. **Settled by the ruling above: `if_absent=True` stays, and `ABSENT` is its second spelling on a single write** (decision 18). A session's `write` has no `if_vid`, so `if_absent` is the only way a caller of a session says "create only". The other choice removed `if_absent` and left the mark as the one spelling, which changes the shell's host and spec 3, decision 9.

## Where this spec disagrees with the overview or the guides

- The overview: nothing.
- `documentation/how-to/keep-a-session-for-each-conversation.md`: nothing. The sentence under "Work Without a Session" already names the vid and `if_vid=`.
- `documentation/how-to/interrupt-a-job-and-ask-a-person.md`: nothing. Its refusal of a step whose file changed is the `conflict` of decision 12.
- What a call returns: nothing. Every call this spec changes is a verb, and returns a `Result` as it does today.

## Needs no other spec meets yet

Nothing. This spec needs nothing of another spec, and no item of another spec's list is addressed to it.

What the other specs take from this one, read at their text after round two, and where each is decided:

- Spec 3, Builds on: the vid on every row, decisions 1 and 4; the form, decision 2; `if_vid` and `if_vids`, decision 6; `if_version` gone, decision 7; the answers, decisions 9 and 12; the trait, decision 13; the mark, decision 18; a directory, decision 10. Its own list says of this spec that nothing is asked.
- Spec 5, Builds on: `restore` with `if_vid` and `if_vids`, decision 17; `VidMint.mint(entry_key, 0)`, decision 2.
- Spec 6, decision 2: the parameter table as decisions 6, 7, 14 and 17 leave it.
- Spec 7, decisions 13 and 22: `stale_vid`, decision 19; `if_vid`, `if_vids` and `ABSENT`, decisions 6 and 18; what a directory's vid guards, decision 10; a mount with no vid, decision 13.
- Spec 8, decision 7: `vid` beside `version` on a `read` row, decisions 1 and 4.

Two needs of round two are closed by their askers. Specs 3 and 8 no longer ask for a function that takes a vid apart: each keeps the version beside the vid. Spec 3 no longer compares entries: its decision 5 lets the stamp that arrives last be the current one, and its decision 10 takes the vid before a change from spec 5, decision 2.

One count in another spec follows from decision 17 here and was written before it. Spec 6, decision 2 has the parameter table at 148 rows once this spec has landed, from eight rows joining four verbs. `restore` gains two more, so the table holds 150.

## Not checked

- Postgres 19.0 was run on 2026-11-23, by probes of today's code and of the quoted statements (`probes/`, `reviews/2026-11-23-spec-review.md`). Held: the guards and claims as quoted, the statement counts, the bytes of the native `uuid` column, a rival inside the window of each verb, twenty writers and twenty creates landing once, and a cost of 0.66 microseconds a row for the id and the mint. Not run, because it is not built: the mark beside a vid in one batch with its two insert groups, and `if_vid` on `edit`, `delete`, `move` and `restore`. For those the probes show the guard, the arbitration and the second run they will ride on, and their answers are inferred. Postgres 15 to 18 were not run.
- The generic floor. No leg runs it.
- The costs under "Cost" are a bench on one machine against in-memory SQLite. Sized again on 2026-11-23 on Postgres 19.0 and on a SQLite file: the id as bytes and the mint add 0.66 and 0.69 microseconds a row to a 10,000-row listing, 8 to 11% of a row (`probes/p07_what_the_etag_costs_a_listing_row.py`). The 1.1 above is not understated. No other machine was measured.
- The mean number of rows a read returns at the reference deployment. The 50 is an assumption.
- How many existing tests compare a whole row or a rendered table of every field, and so gain the new field.
- That the list of sites that build a row with a version is complete. It was made by a search for the constructors. The contract row of 19 calls is what catches a site that was missed.
- Whether a rendering pass moves a version. Decision 3 says only that a vid stays where the version does.
- The mark's second insert group was read from the arbitration code and not run. The count of 2 inserts is the test's to show.
- The other eight specs were read at `7c383f32` and as they stood on disk in round three, while their writers were revising them. Every decision cited here was found under the number and the heading given. A later change of a heading is not seen.
- A database copied by file or by dump, mounted beside its original.

## One line

Every row a caller may read says which entry it is and at what version in twenty characters, and a write, an edit, a delete, a move or a restore that passes them back changes that row or nothing.
