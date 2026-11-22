# A row carries an etag, and a change can require it

A draft, written on 2026-11-22. It is not reviewed, and nothing is built. It is spec 1 of the nine that `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md` maps. It lifts decisions 1 and 2 out of the spec merged from pull request 42, `agents/2026-11-22-the-session-remembers-what-it-read/spec.md`, and makes them a kernel spec of their own that needs no session. It rests on the landed spec `agents/2026-11-20-write-takes-preconditions-and-an-append/spec.md`, whose preconditions it extends, and on the verification record `agents/2026-11-22-shell-review/reviews/verification.md`, whose four cases it ran again. Every fact about the code was read on the branch `a-job-is-interrupted-and-resumed` at `6dae6a1d`, whose kernel and storage files are those of `dev` at `5a823ea`, and the facts a decision rests on were run that day. The probes sit outside the repository.

## The outcome wanted

Every row a call returns about a file or a directory that the caller may read carries an `etag`: a short opaque value that names one entry at one version. A caller that reads a file and later writes, edits, deletes or moves it passes that value back as `if_match=`. The change lands only when the row at the path is still that entry at that version. When it is another version, or another file that came to stand at the path, nothing changes and the call is refused with `vfs.conflict`.

```python
row = (await fs.read("/notes.md", authority=who)).observations[0]
changed = await fs.write(path="/notes.md", content=new_body, if_match=row.etag, authority=who)
# changed.success is False, and changed.errors[0].kind == "vfs.conflict", when /notes.md moved on
```

The check costs no statement, and a read pays no statement for the etag.

## Builds on

- `agents/2026-11-20-write-takes-preconditions-and-an-append/`: landed on 2026-11-20. It gives `write(if_version=, if_versions=, if_absent=, append=)`, the snapshot, the plan, the guard and `conflict` with `data["version"]`. This spec keeps its plan and its guard, and replaces its two version arguments.
- `agents/2026-11-22-the-session-remembers-what-it-read/spec.md` as merged from pull request 42: drafted. Its decisions 1 and 2 are the source of this spec. It is being rewritten as spec 3 to hold the session half only.
- `agents/2026-11-22-shell-review/reviews/verification.md`: the record that a version alone does not name a file. Its four cases were run again here.
- `agents/2026-11-22-a-session-is-stored-named-and-forked/research/history.md`, lineage 4: the entity tag and `If-Match` of HTTP, and the lost update they were made for. Its lesson is that the record of what was read is a validator checked at write time, safe to copy, safe to lose and safe to send with the request.
- It needs nothing from specs 0 and 2 to 8. It keeps no record, so it needs no kernel store.
- Specs 3, 5 and 7 build on it. They were being written the same day and none was seen.

## Terms

- **Entry id.** The permanent identity of one stored row, a ULID kept as 16 bytes in `vfs_entries.entry_id`. It never leaves the storage.
- **Version.** The per-entry counter in `vfs_entries.version`. Creation sets 1, and each change of the row adds one.
- **Mount identity.** One ULID kept in `vfs_meta.mount_identity`, made when a database is provisioned. It names the database, and not the path it is mounted at.
- **Etag.** Twenty characters that name one entry at one version in one mount. Two etags are equal when, and only when, they name the same entry at the same version of the same mount. An etag grants nothing: rights are judged on every call as before.
- **Mint.** To compute the etag of a row.
- **Precondition.** A condition a caller attaches to a change. When it is false, nothing changes and the call is refused.
- **Snapshot.** The read a change takes of its targets before it decides anything.
- **Guard.** The terms on a mutation statement that prove the row is still the one the snapshot read.
- **Window.** The time between the snapshot and the guarded statement.
- **Mutation statement.** An `INSERT`, `UPDATE` or `DELETE`.
- **Tombstone.** A deleted row that stays at its path with `deleted_at` set. It is absent to every read.
- **Bare row.** A row that shows only `path` and `kind`, given to a caller who may list a row and may not read it.
- **Seam.** The storage protocol, `SupportsMutation` in `src/vfs/storage/protocol.py`.
- **Trait.** A quality a storage declares through `traits()`, read by the kernel without calling a verb.
- **Key.** One path of an `if_matches` mapping.

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
| The row a delete returns reports the version the row had before the delete (`trash.py:660-668`). | Read and run. |
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

### 1. Every row that carries a version carries an etag, and the storage mints it

`Observation` gains one field, `etag: Etag | None`, placed after `version`. A storage fills it on every row it fills `version` on, from that row's own entry id and the version the row reports. The two fields share a mask: `"etag"` is in `populated` exactly when `"version"` is. `ALWAYS_ON_FIELDS` in `reads.py` gains it, so no `columns=` projection drops it. A bare row carries neither.

The field is listed in `OBSERVATION_QUERY_FIELDS`, the fields no model field owns: it is worked out when a row is produced and is stored nowhere. `Entry.to_observation` leaves it unpopulated, as it leaves `version`.

The etag is part of the public result and crosses the wire as any other field does.

The storage mints, and not the router. The merged spec had the router mint.

Nothing is stored. No table gains a column, the schema format number stays, and no row is backfilled.

Reason: an etag is made from the entry id, and the entry id is the one fact about a row that never leaves the storage. A router that minted would have to be handed the id on every row, which is the leak the models forbid.

### 2. An etag is twenty hexadecimal characters: a keyed digest of the mount, the entry and the version

```python
# src/vfs/etag.py, a leaf module: the standard library alone
ETAG_LENGTH: Final = 20
Etag = Annotated[str, "20 lowercase hex characters that name one entry at one version; compared, never parsed"]

def is_etag(value: object) -> bool: ...          # a str of exactly ETAG_LENGTH characters from 0-9 and a-f

class EtagMint:
    def __init__(self, mount_identity: str) -> None: ...
    def mint(self, entry_key: bytes, version: int) -> Etag: ...
```

`mint` returns `hashlib.blake2b(entry_key + version.to_bytes(8, "big"), digest_size=10, key=mount_identity.encode("ascii"), person=b"vfs.etag.1").hexdigest()`. `entry_key` is the entry id's 16 bytes, so the hashed input is always 24 bytes and no two rows share one. The key is the mount identity's 26 characters. `person` names the form.

The engine host builds one `EtagMint` at first touch, where it reads the mount identity, and every site that builds a row from a stored row is handed it.

An etag is compared for equality and nothing else. No code takes one apart, and none can: the digest does not give back the id or the version.

| Form | Verdict |
|---|---|
| The entry id and the version in clear, encoded | Rejected. It is 40 characters against 20, it puts a database identifier on a model that carries none by rule, and a caller that can parse it will. |
| A digest in two halves, one of the entry and one of the entry at its version | Rejected. Its one use is to compare the entry alone, which decision 10 does not need, and it costs every row a second hash. |
| The version and the body's hash, the pair the shell's host keeps | Rejected. It tells two files apart only while their bodies differ. Another file with the same body at the same version passes, and a delete or a move of it then changes a file the caller never saw. A directory has no hash at all. |
| A digest in base64url, 16 characters | Rejected. 318 of 20,000 minted ones began with `-`, which reads as an option on a command line, and the alphabet is case-sensitive. Hex costs 4 more characters and is the faster to make. |
| One keyed digest in hex, 20 characters | Chosen. |

Reason for the digest: it keeps the etag opaque by construction, so its form can change without breaking a caller. Reason for the key: an etag of one mount equals an etag of another only when two digests collide, which is one chance in 2^80 for each comparison, so an etag cannot be mistaken for another mount's. Reason for 80 bits: an etag is compared against one row, never searched for, and it grants nothing, so nobody gains by forging one.

### 3. An etag follows the entry and its version, and nothing else

| Event | The etag |
|---|---|
| A write of a new body, an edit, an append | A new one. The version moved. |
| A write of the body the file holds | The same. Nothing moved. |
| A delete of the row, then a restore | A new one. The version moved twice. The body is the same, and a holder of the old etag reads again. |
| A delete, then a write at the path | A new one. The row keeps its id and the version moved. |
| A move of the row | A new one, at the new path. |
| A move of a directory above the row | The same, at the row's new path. It is the same entry at the same version. Required at the old path, it meets nothing or another entry. |
| A delete and a restore of a directory above the row | The same. While the row is deleted, a change that requires it is `not_found`. |
| A copy | The copy is another entry at version 1, with an etag of its own. |
| `update_mount` | The same. It changes policy and never the storage. |
| The same storage mounted at another path, in another kernel or in another process | The same. A path is no part of an etag, and the mount identity is the database's. |
| Another storage mounted at a path | No etag held for that path matches, and a change that requires one is `conflict`. |
| A move or a copy between mounts | Refused `cross_mount`, as today. A caller that copies and deletes makes a new entry in the other mount. |
| A grant, a posture, an index pass, a rendering | The same, wherever the version stays. An etag names what a change replaces. It says nothing of rights or of derived state. |
| A later form of the etag | Every old etag stops matching. That is only ever a refusal, and a read mends it. |

Reason: these are the properties of the two columns the etag is made from, run in "What the code does today". None is added by this spec, so no statement is added to keep one true.

### 4. Each verb fills the etag on the rows it already returns

| Verb | Rows | The etag names |
|---|---|---|
| `read`, `stat` | Each row the caller may read | The row as read |
| `ls`, `tree`, `glob` | Each whole row. A bare row, a directory shown only as the road to a mount, and the trash view's own head carry none | The row as listed |
| `grep`, `search` | Each file row | The file as searched |
| `traverse` | Each whole node row. An edge row and a bare node carry none | The node as walked |
| `write`, `edit`, `mkdir` | Each row of the result, a `created`, an `updated` and an `unchanged` one alike | The row after the call |
| `move`, `copy`, `restore` | Each row of the result | The row after the call, at its new path |
| `delete`, `sweep` | Each row of the result | The row as it was before the call, since the row reports that version |
| `mkedge`, `rmedge`, the grant verbs | None. Their rows carry no version | |

A row in the trash view carries the etag of the tombstone. A mount's root, shown where the mount is listed, carries the etag its own storage mints.

`observations=` never implies a precondition. A row handed back to `edit`, `delete`, `read` or any other verb is used for its path, and its etag is ignored. A caller that wants each row required says so: `if_matches={row.path: row.etag for row in rows}`.

A merge of two rows of one path, by `Result.merge` or by `&`, `|` and `-`, keeps an etag both rows agree on and nulls one they disagree on, as it does a version. When it nulls the version it nulls the etag.

The default text projections stay as they are. They show no version today and show no etag. A caller names `etag` in a projection to see it in text.

The shell's host answers a line with public verbs (`src/vfs/shell/host.py:377`, `421`, `476-490`), so the rows it is handed carry etags as any caller's do. It passes none to the module, no program prints one, and it sends no `if_match`.

Reason for every listing row: a caller cannot know which listed row it will change, and a session stamps what it is shown, so a listing that left the etag out would force a second read of every row before a change. The cost of carrying it is under "Cost".

### 5. A read takes the entry id as its stored bytes and mints once for each row

`src/vfs/models/rows.py` gains a sibling of `ULIDKey`, `ULIDBytes`: the same column read as its 16 stored bytes with no conversion to text. A read that does not already select the id selects it through `ULIDBytes` under the label `entry_key`. On SQLite the driver returns the bytes. On Postgres it returns a UUID, whose `bytes` the type hands on. A read that already holds the id as text, and every change, turns the text into the 16 bytes with a new pure function beside it, `entry_key_of(text)`, which is `int(text.translate(table), 32).to_bytes(16, "big")`.

`etag` is no column. Where a set of fields becomes a select list (`entry_columns` in `reads.py`), a new constant `DERIVED_FIELDS = frozenset({"etag"})` is left out, and the id is selected for it.

| Step | Cost for each row |
|---|---|
| Select the id as text through `ULIDKey` | 2.1 µs |
| Select the id as bytes through `ULIDBytes` | 0.2 µs |
| Mint from bytes | 0.9 µs |
| Mint from text, through `entry_key_of` | 1.2 µs |

Reason: a listing does not select the id today, and selecting it as text would cost twice what the mint costs. As bytes, a read row pays about 1.1 µs in all.

### 6. `write`, `edit`, `delete` and `move` take `if_match`, and their batch forms take `if_matches`

```python
async def write(self, entries=None, *, path=None, content=None, data=None,
                if_match: Etag | None = None, if_matches: Mapping[str, Etag] | None = None,
                if_absent: bool = False, append: bool = False, parents: bool = False,
                authority: Authority | None = None) -> Result: ...

async def edit(self, path=None, old=None, new=None, edits=None, observations=None, replace_all=False, *,
               if_match: Etag | None = None, if_matches: Mapping[str, Etag] | None = None,
               authority: Authority | None = None) -> Result: ...

async def delete(self, path=None, observations=None, *, cascade: bool = True,
                 if_match: Etag | None = None, if_matches: Mapping[str, Etag] | None = None,
                 authority: Authority | None = None) -> Result: ...

async def move(self, src=None, dest=None, moves=None, *,
               if_match: Etag | None = None, if_matches: Mapping[str, Etag] | None = None,
               authority: Authority | None = None) -> Result: ...
```

- `if_match` is the precondition of the single form: `path` for `write`, `edit` and `delete`, and `src` with `dest` for `move`, where it names the source.
- `if_matches` is the precondition of the batch form: `entries`, `observations` or `moves`. It maps a path to the etag required there. A path with no key has no precondition.
- The precondition holds when the live row at the path has the etag given. Nothing else is compared.

The kernel turns `if_match=E` into a mapping of one key, as it turns `if_version` today. A storage sees one shape:

```python
async def write(self, *, entries, if_matches: Mapping[Path, Etag] | None = None, if_absent=False, append=False, parents=False, authority=None) -> Result: ...
async def edit(self, *, edits, path=None, observations=None, if_matches: Mapping[Path, Etag] | None = None, authority=None) -> Result: ...
async def delete(self, *, path=None, observations=None, cascade=True, if_matches: Mapping[Path, Etag] | None = None, authority=None) -> Result: ...
async def move(self, *, operations, if_matches: Mapping[Path, Etag] | None = None, authority=None) -> Result: ...
```

The kernel passes `if_matches` only when the call requires something, so a storage that cannot honour it never sees the argument.

The merged spec gave `if_matches` to a batch write alone. The batch forms of `edit`, `delete` and `move` take it here too.

Reason: a precondition that only one form of a verb can state leaves the other form to be split into one transaction a row, which loses the rule that a batch fails whole. The mapping costs no statement, since the comparison is made in Python against rows the snapshot already holds.

### 7. `if_version` and `if_versions` leave

They leave the four public signatures, the parameter table with its `versions` kind and its four rules, and the seam. Inside the plan, `StagedEntry.expected_version` becomes `expected`, an etag, and `stale_version` becomes `stale_etag`. No alias is kept.

`version` stays on every row. It is the readable counter, the label of a version row and the number a `conflict` reports.

A caller that wants "the file is at version N" reads the row, compares `row.version` itself and passes `row.etag`. That is one read, and it is sound.

Reason: the four cases of "The problem" report success and replace a file the caller never saw. A precondition that is known to be unsound beside a sound one is a trap, and the design is not released, so there is no caller to move. The earlier reason for the version was that every reader already holds it and a model can copy it. Both are now true of the etag, which arrives in the same row.

### 8. The rules at the gate

Each is refused before any storage is called. Rows 1 to 5 are in `params.py` and are judged first, even on a closed kernel.

| Rule | Refusal |
|---|---|
| `if_match` is an etag: `is_etag` holds | `invalid`: `"{op} if_match must be an etag, the 20 characters a result carries, got {shown}"`. `shown` is the type's name for a value that is not text, and the first 32 characters in quotes for one that is. A new `ParamKind`, `etag`. |
| `if_matches` is a mapping of text to etags | `invalid`: `"{op} if_matches must be a mapping of paths to etags, got {type}"`, `"{op} if_matches keys must be strings, got {type}"`, or `"{op} if_matches values must be etags, the 20 characters a result carries, got {shown}"`. A new `ParamKind`, `etags`, checked key by key. |
| `if_match` goes with the single form, and `if_matches` with the batch form | `invalid`: `"write takes if_match with path, and if_matches with entries"`, `"edit takes if_match with path, and if_matches with observations"`, `"delete takes if_match with path, and if_matches with observations"`, `"move takes if_match with src and dest, and if_matches with moves"`. Two shape rules for each verb. |
| `if_absent=True` with `if_match` or `if_matches` | `invalid`: `"write if_absent=True takes no if_match or if_matches: an absent file has no etag"`. |
| `append=True` with `entries` | `invalid`, as today. `append=True` with `if_match` is lawful: it is the append that lands at most once. |
| Each key of `if_matches` names a target of the call, once it is resolved as the targets are: a file of `entries`, a row of `observations`, a source of `moves` | `invalid`: `"each key of if_matches must be the path of a file in entries"`, `"... of a row in observations"` or `"... of a source in moves"`, with `data={"raw": key}`. In `base.py`. |
| No two keys name one path | `invalid`: `"if_matches names one path twice"`, with `data={"raw": key}`. |
| The storage of each mount that receives a key declares the `etag` trait | `unsupported` at the mount's path: `"the storage mounted here issues no etag, so a change there cannot require one"`. Decision 13. |

The kernel resolves each key, matches it to a target, and hands each mount the keys of its own targets with the mount's prefix taken off. A batch over two mounts stays whole on each mount and not across them, which is today's rule for any refusal.

An empty `if_matches` requires nothing. Beside the single form it is refused by the form rule, as an empty `if_versions` is today.

A value that has the shape of an etag and was minted by another mount, or by nobody, passes the gate. Decision 12 says what answers it.

Reason: a wrong argument is the caller's to fix and is named before anything runs. The shape is all the gate can know, since an etag cannot be taken apart.

### 9. The precondition is judged at the snapshot, and the guard each statement already carries holds it

Each verb mints the etag of the live row its snapshot read and compares it with the one required. When they are equal, the id and the version the snapshot holds are the ones the etag names, and the mutation statement already compares both. No term and no statement is added.

| Verb | Where it is judged | The statement that carries it, unchanged |
|---|---|---|
| `write` | In the plan. Order: the address gates, `if_absent`, the occupant's kind, a required etag against no live row, stage, settle. Settle drops a row whose body is the stored body first, and then refuses each row whose etag is not the one required. | The material `UPDATE`. SQLite: `entry_id = ? AND version = ? AND path = ? AND deleted_at IS NULL`. Postgres: the same four terms over a `VALUES` join. |
| `write(append=True)` | As a write, after the row lock and the second read. | The same `UPDATE`. |
| `edit` | After the miss and before every other judgment of the row: a target whose etag is not the one required is refused, its kind of body is not looked at and its edits are not run. | The same `UPDATE`. |
| `delete` | In the ladder, after the miss and before `not_empty`. A target covered by another target's cascade is judged too, where it has a key. | The claim `UPDATE`: `entry_id = ? AND version = ? AND deleted_at IS NULL`, as an executemany on SQLite and over a `VALUES` join on Postgres. |
| `move` | In the pair's ladder, after the source is found live and the root is refused, and before the rename onto itself. | The root claim `UPDATE`: `entry_id = ? AND version = ?`, on both engines. |

What a `write` answers, by what is at the path when the snapshot is read:

| Target | `if_match=E` |
|---|---|
| absent | `not_found`. A precondition never creates. A missing parent answers at that parent, with `parents=True` too. |
| tombstoned file | `not_found` with the trashed hint. A precondition never revives. |
| live file, same body | `unchanged`, whatever `E` is |
| live file whose etag is `E`, new body | updated to the next version |
| live file whose etag is not `E`, new body | `conflict` |
| live directory | `wrong_kind` |

`unchanged` comes before the comparison for a `write` and after it for an `edit`. A write of the body a row holds is recognisably a call sent twice, and it writes nothing. An edit is no stored value, so its second sending cannot be told from a stale one, and it is `conflict`.

A rival inside the window:

- **SQLite.** A writer holds the database's one writer lock from before its snapshot, so no rival commits inside the window. The in-memory storage has one connection, and calls on it queue.
- **Postgres, `write` and `edit`.** The call runs at REPEATABLE READ. A rival's commit inside the window ends the guarded `UPDATE` with a serialization failure or with no row matched. The first runs the call again from a new snapshot, where the etag no longer matches. The second is probed and refused. Either way the answer is `conflict`, unless the rival wrote the very body the call carries, which is `unchanged`.
- **Postgres, `delete` and `move`.** The call runs at READ COMMITTED behind the serialization point. A rival's write inside the window moves the version, the claim matches no row, and the verb runs again from a new snapshot, where the etag no longer matches.
- **An append.** A rival appender waits on the row lock. When it gets the lock it reads the new version, and with `if_match` it is refused `conflict` and does not run again.

Two calls that require one etag of one file: one lands and moves the version, and the other meets the new one. Exactly one lands on every engine.

Two processes mint the same etag for one row, since every input is a stored value.

A crash between two statements leaves nothing: the snapshot, the comparison and the mutation are one transaction. A call cancelled before its commit changed nothing, and one cancelled after it landed whole. The caller cannot tell which, so it sends the call again with the same etag: a `write` that landed answers `unchanged`, an `edit` that landed answers `conflict`, and a `delete` or a `move` that landed answers `not_found`.

In a batch, a key is judged against the state before the call. A `write` that names one path twice judges its key once. A `move` reads each pair's source live, so a key on a source that an earlier pair of the same call moved into place never matches.

Reason: the comparison belongs where the row is already in hand, and the proof belongs on the statement that changes it. Both existed. Adding a term or a read would cost the million writes a day something for a guarantee they already have.

### 10. A directory is matched as a file is, by its entry and its version

One rule serves every kind of row on every verb. For a directory:

- A cascading delete, and a move, with `if_match` require the directory to be the same entry with the same direct children it had when it was read: a child made in it, deleted from it, moved into or out of it, or renamed in it since refuses the call. A change deeper down, and a change of a child's body, do not move the directory's version and are not seen.
- A delete without cascade requires the same. A caller that emptied the directory itself moved its version by doing so, and passes no `if_match`: `not_empty` is the guard an empty directory needs.
- `write` and `edit` refuse a directory `wrong_kind`, as today.

The merged spec compared the entry alone on a delete without cascade.

Reason: comparing the entry alone needs an etag that can be taken apart, which costs every row a second hash or its opacity (decision 2). It would buy one refusal: of a delete of an empty directory that is not the one the caller saw. An empty directory holds nothing to lose, and the delete can be undone.

### 11. A move requires its source, and its destination takes no precondition

`if_match` on a `move` names the row at `src`. The destination must be free, as today: any occupant, a tombstone included, is `exists`, whether or not a precondition is given.

Reason: a precondition protects what a call would replace. A move replaces nothing at its destination, so there is nothing there to require.

### 12. A mismatch is `conflict` with the version and the etag of the row at the path, and an etag from another mount is a mismatch like any other

| Refusal | Kind | `data` | `retryable` |
|---|---|---|---|
| The etag required is not the etag of the live row, at the snapshot | `conflict` | `{"version": v, "etag": e}` of the row at the path | no |
| The same, found by a call that ran again after a rival | `conflict` | the same | no |
| A write with a required etag lost its guard, and the row probed is still at the path | `conflict` | `{"version": v, "etag": e}` of that row | no |
| The same, and the row probed has moved away | `conflict` | none: the row now at the path was not read | no |
| A plain write lost its guard | `conflict` | `{"version": v, "etag": e}` where the row is still at the path, and none where it moved | yes, as today |
| A required etag against no live row | `not_found` | the trashed hint on a tombstone | no |
| `if_absent` over a live row | `exists` | `{"version": v, "content_hash": h, "etag": e}` | no |
| A value that is no etag | `invalid` | none | no |
| A mount whose storage issues no etag | `unsupported` | none | no |

The detail of the first four is `"the etag required is not the etag of what is stored"`. Every stale row of a batch is listed, and the batch fails whole.

The contract row of `conflict` in `KIND_CONTRACTS` reads: phrase `Conflict`, retry class `refresh`, hint `"Read the entry again, then retry; a change that requires an etag takes the one that read returns."`, and `path` means `"the entry whose state is not the one the call expected"`.

`data` lets a caller that already holds the state the etag names go on without a read. A caller that does not hold it reads first. Sending the etag from the refusal back without reading replaces the very change the refusal reported, and the reference page says so.

An etag minted by another mount is answered here, as a mismatch, and not at the gate. The merged spec refused it `invalid` before any storage was called.

Reason for one answer: a digest cannot say who minted it, and nothing needs it to. The case that happens is a path whose mount was replaced while a caller, or a session's memory, still held etags from the old one. That caller did nothing wrong, and the true answer is that what is at the path is not what was seen, which is `conflict` and is mended by a read. Reason for carrying the etag: the kind's contract is to say what is there now, and the version alone is half of that. It goes only to a caller who passed the rights check for the change, and every rung that changes a row sits above `read`.

### 13. A storage declares the `etag` trait, and a mount without it refuses a change that requires one

`TRAIT_KEYS` gains `etag`, with one value, `entry_version`. A storage that declares it promises four things:

1. Every row it returns with a version carries an etag of the public shape.
2. Two of its rows carry equal etags when, and only when, they are the same entry at the same version.
3. No etag of another storage equals one of its own, short of a collision.
4. It honours `if_matches` inside the transaction that changes the row, with the answers of decisions 9 and 12.

`DatabaseStorage` declares it on every dialect. `SQLiteStorage`, `PostgresStorage` and `InMemoryStorage` are that class. The in-memory storage has a mount identity of its own for each object, so its etags end with it. A dialect on the generic floor mints and honours as the two engines do, since nothing here is engine-specific. No engine leg tests the floor.

A storage that does not declare the trait fills no etag, and its rows carry a version alone. A call that sends `if_match` or `if_matches` to its mount is refused `unsupported` by the kernel before the storage is called. A storage that wants the trait may use `EtagMint` with any identity that is its own.

Reason: a precondition that a storage silently dropped would be a write the caller believes is guarded and is not. The constitution forbids a silent clobber and requires a capability to be declared, and the listing cursor already works this way.

### 14. The four public faces, the parameter table and the seam carry the same names

- `AsyncVirtualFileSystem`, `VirtualFileSystem`, `AsyncSession` and `Session` each carry `if_match` and `if_matches` on `write`, `edit`, `delete` and `move`, keyword-only. The session faces take no `authority`, and pass both through unchanged, as they pass every argument today. What a session fills in is spec 3's.
- `PARAMS` gains the two names on the four verbs and loses the two version names on `write`. The signature drift test and the count of integer channels follow: 11, where 12 were.
- `Etag` and `EtagMint` are exported from `vfs`. `Etag` sits on the Entry reference page beside `ContentHash`, and `EtagMint` on the Storage page under "Writing a Storage Backend".
- The glossary gains **Etag**: "A short value on a row that names one entry at one version. A change can require it."

Reason: a name that differs between two faces is found by the caller who crosses from one to the other. The parity tests exist to make that impossible.

### 15. The etag adds no primitive, and Article 1.5 names it in place of `if_version`

This spec manipulates one primitive, the Candidate, which gains a field. An etag is a value on a Candidate, composed of two things the constitution already has: the Entry's identity and its revision, within one Mount. It has no path and needs none. Nothing is found by it: hydrating a Candidate stays a path lookup, and a caller that never passes an etag uses the file system as before.

The third bullet of Article 1.5 becomes: "**Usable for optimistic concurrency.** Every Candidate that carries a revision carries an *etag*, an opaque value composed of the Entry's identity and its revision. A caller MAY pass `if_match=etag` on a change; a mismatch MUST surface as `Conflict` in the error taxonomy (Article 2). A revision alone is not a precondition: two Entries can stand at one path, one after the other, at the same revision."

Article 1.3's list gains: "`etag` — present wherever `revision` is; see §1.5."

Article 2 holds: the refusals are four kinds of the closed taxonomy. Article 4 holds: the capability is declared by a trait and read without running a verb. Article 5 holds: a change with `if_match` is revision-guarded, and one without is last writer wins, as each docstring says.

Reason: Article 1 allows five first-class things. A sixth would be the most expensive mistake this spec could make, and it is avoided by making the etag a fact about a row and never a name for one.

### 16. Four landings, in this order

1. The etag on every row: `etag.py`, `ULIDBytes`, the mint at each site, the trait, the merge rule, the exports, and `etag` beside `version` in the `data` of `conflict` and `exists`. No argument changes.
2. `write` takes `if_match` and `if_matches`, and `if_version` and `if_versions` leave, in one landing.
3. `edit` takes them.
4. `delete` and `move` take them, and the constitution, the roadmap rows and the guide's sentence change.

Reason: each leaves the tree green and is of use alone. The first lets a caller see what it would require. The second swaps the precondition in one step, so at no commit does `write` have two or none.

## Cost

Costed against the reference deployment in the working agreement.

**Per verb call, about 150,000 a day.** No read issues a statement for the etag. A read that did not select the entry id selects 16 more bytes from a row it already reads. Each row costs about 1.1 µs to fetch the id and mint, on rows that cost 7.3 to 18.0 µs today: 12 to 15% for `ls`, `tree` and `glob`, and 6% for `grep` and a batch `stat`. Each row is 30 bytes longer in compact JSON, on 185, and holds 69 bytes more in memory. A 10,000-row listing pays about 11 ms, 300 KB on the wire and 690 KB in memory. About three calls in four are reads. At an assumed 50 rows a read, that is 5.6 million rows and about 6 seconds of processor a day. The 50 is an assumption. No measurement of rows per call exists.

**Per file write, about 1,050,000 a day.** No statement, no bind and no stored byte. One mint for the result row, and one more where the change requires an etag, at 1.2 µs each: under 3 seconds of processor a day.

**Per index visit, about 11,000,000 a day.** Nothing. The index path builds no row with a version, and a `rebuild` returned none.

**Per batch, 100 a night.** A 10,000-entry write with a key for every row mints 20,000 etags, about 25 ms of a call measured at 1.3 s. The keys never enter a statement, so the statement count is the count without keys and no chunk changes size. The mapping holds 10,000 paths and 10,000 twenty-character values. A batch with one stale key writes nothing.

**Per corpus.** Nothing. There is no column, no backfill and no pass.

**Per lock.** None is taken and none is held longer. The comparison is made in Python between two statements the call already issues, inside the transaction it already holds. No reader waits on anything new.

**A refused change.** A stale `write` or `edit` costs the snapshot and no mutation statement. A stale `delete` or `move` costs its reads and no mutation statement.

**What grows with input.** The mapping grows with the batch, as `entries` does, and never enters SQL. The etags of a result grow with its rows, and a page bounds both. No statement, bind list or chunk grows, and no dialect profile gains a field.

**The mint, if it ever shows in a profile.** The direction is one call into `crates/vfs-core` that mints a whole listing's etags. It is not built, and nothing here is capped for want of it.

## Left as it is

- **`copy`, `mkdir`, `restore`, `sweep`, `mkedge` and `rmedge` take no precondition.** A copy changes no source and replaces no destination. `mkdir` and `restore` land only on a free path. `sweep` runs retention or destroys a subtree named whole, and no caller is known that reads before it.
- **A read that returns nothing when an etag still holds.** The etag is what such a read would take. No caller for it is known.
- **`entry_id` on `stat`.** The kernel plan lists it as not built. No precondition needs it now.
- **A precondition on the body's hash.** The earlier decision stands.
- **A request key, and a change that lands exactly once.**
- **The parent's new etag on the result of a change.** A change that adds or removes a child moves its parent's version and reports the child alone. A caller that holds the parent's etag from before its own change reads the parent again before it requires it.
- **`etag` in the default text of a listing.** It is in the row and not in the default projection, as `version` is.
- **The shell's host.** It keeps its pair of version and hash. An etag is that pair in one value, and the host can hold it when it is next changed.
- **A copy of a database.** A file copy or a dump restored elsewhere carries the mount identity and every entry id with it. Etags minted against one are honoured by the other wherever their versions line up. Telling two copies apart is a change to provisioning.
- **Version rows.** No verb serves them yet. When one does, a version row's etag by the rule of decision 1 is the etag the entry had at that version.
- **The kinds a session answers with, `vfs.conflict.unread` and `vfs.conflict.changed`.** They are spec 3's.
- **Create-only rows and required rows in one call.** `if_absent` applies to every entry of its call, as landed.

## Tests

Each is written and seen failing before the code. Counts are of statements recorded by the `before_cursor_execute` listener the write tests use, of rows, of errors, or of calls to a spied function. Never of time. A row of the storage contract runs on memory, on SQLite and on the Postgres leg.

`tests/test_etag.py`, new:

- `test_an_etag_is_twenty_lowercase_hex_characters`: 1,000 mints, 1,000 that pass `is_etag`.
- `test_one_entry_at_one_version_has_one_etag_and_no_other_row_shares_it`: 10,000 pairs of id and version give 10,000 distinct etags; each pair minted twice gives 0 differences; a mint with another mount identity gives 0 equal of 10,000.
- `test_is_etag_refuses_each_malformed_value`, parametrized over 9 values: 19 characters, 21 characters, an upper-case letter, a `g`, a quoted etag, an empty string, an integer, bytes, `None`. Each is false.

`tests/models/test_rows.py`:

- `test_the_id_reads_as_bytes_and_as_text_alike`: for 1,000 stored rows, `ULIDBytes` and `entry_key_of(text)` give 0 differences.

`tests/models/test_models.py`:

- `test_etag_is_a_field_no_model_owns`: `"etag"` is in `OBSERVATION_QUERY_FIELDS`, and `Entry.to_observation()` leaves it out of the mask.

`tests/results/test_result_laws.py`:

- `test_a_merged_etag_agrees_or_is_null`: equal etags are kept, differing ones are null and still masked, a nulled version nulls the etag, and the law holds in both orders and applied twice. 4 cases.

`tests/test_params.py`:

- The drift test passes with the new names. `test_every_int_channel_enforces_the_shared_ceiling` counts 11.
- `test_garbage_classifies_invalid_with_zero_dispatch` gains one case for each rule of rows 1 to 5 of decision 8, on each of the four verbs where the rule applies: 0 storage calls each.
- `if_version` and `if_versions` are in no signature of the four faces and not in `PARAMS`.

`tests/base/test_dispatch.py`:

- `test_if_match_reaches_the_storage_keyed_by_its_own_path`, one case for each of the four verbs: the recorder storage receives one key, with the mount's prefix off.
- `test_if_matches_go_to_the_mount_of_each_key`, for `write`, `edit`, `delete` and `move`.
- `test_a_key_that_names_no_target_of_the_call_is_invalid` and `test_if_matches_that_names_one_path_twice_is_invalid`: 0 storage calls.
- `test_a_mount_whose_storage_issues_no_etag_refuses_a_required_change`: `unsupported` at the mount's path, 0 storage calls, and the same call without `if_match` reaches the storage once.
- `test_a_call_that_requires_nothing_passes_no_if_matches`: the recorder receives no such argument.

`tests/support/storage_contract.py`, a new class `TestEtag`:

- `test_every_row_with_a_version_carries_an_etag`, parametrized over 17 calls: `read`, `stat`, `ls`, `tree`, `glob`, `grep`, `search`, `traverse`, a `write` that creates, one that updates, one that is unchanged, `edit`, `mkdir`, `move`, `copy`, `delete`, `restore`. For each row, the count of rows where `version` and `etag` are not both set or both unset is 0, and so is the count where their masks differ.
- `test_a_bare_row_carries_no_etag`: under an everyone level of `list`, `stat` and `ls` return 0 etags.
- `test_one_row_has_one_etag_from_every_verb`: `stat`, `read`, `ls` and `glob` of one file give 1 distinct etag.
- `test_what_moves_an_etag_and_what_keeps_it`, 10 cases from decision 3: a new body, the same body, an edit, an append, a delete and a restore, a delete and a write, a move, a parent moved, a parent deleted and restored, a copy.
- `test_a_matching_etag_updates`, and `test_a_stale_etag_is_conflict_and_writes_nothing`: one `conflict`, `data` equal to the version and the etag a `stat` then returns, `retryable` false, and the body unchanged.
- `test_a_path_freed_by_a_move_is_refused`, parametrized over the 4 rows of "The problem": each is `conflict`, and the file now at the path keeps its body. All four pass with `if_version` today.
- `test_a_write_with_an_etag_sent_twice_is_unchanged`, and `test_an_etag_on_no_live_row_is_not_found` for an absent path, a missing parent with `parents=True` and a tombstone with the trashed hint.
- `test_an_etag_minted_by_another_storage_is_conflict`: an etag from a second storage of the same class, for a file at the same path and version, is refused.
- `test_stale_keys_refuse_the_whole_batch_and_each_is_named`, and `test_an_append_with_an_etag_lands_at_most_once`.
- `test_twenty_writers_that_require_one_etag_land_once`: twenty writes at once, each with a body of its own and the same etag, give 1 success and 19 `conflict`.
- `test_an_edit_with_a_stale_etag_is_conflict_before_any_text_is_matched`: an edit whose `old` is not in the file and whose etag is stale answers 1 error, `conflict`. An edit sent twice with one etag answers `conflict` the second time.
- `test_a_delete_requires_what_it_was_shown`: a stale file is `conflict` and stays live; a matching one is deleted; a tombstone is `not_found`; a directory with a child made since is `conflict` and the count of live rows beneath it is unchanged; a directory with a grandchild made since is deleted; an empty directory with a child removed since is `conflict` without cascade, and is deleted with no `if_match`.
- `test_a_batch_delete_with_one_stale_key_deletes_nothing`: 0 rows tombstoned.
- `test_a_move_requires_its_source`: a stale source is `conflict`, the source is still at its path and the destination is empty; a matching one moves, and the result's etag differs from the one required; an occupied destination is `exists` with or without `if_match`.
- `test_an_exists_names_the_etag_of_what_is_there`.
- `test_the_storage_declares_the_etag_trait`.

`tests/storage/database/test_writes.py`, class `TestRequiredEtag` in place of `TestExpectedVersion`, on a SQLite file at the seam as the system actor:

- `test_a_stale_etag_runs_the_snapshot_and_no_write`: 1 statement, a `SELECT`.
- `test_a_key_for_every_row_adds_no_statement`, for 100 files and, marked `slow`, 10,000, with the membership budget narrowed to 1,000: the list of statement verbs equals the list of the same write without keys. With one stale key the batch fails whole with 0 mutation statements.
- `test_a_required_etag_mints_twice_for_each_row`: a 10,000-entry write with a key for every row calls `EtagMint.mint` 20,000 times. Marked `slow`.
- `test_a_row_that_lost_its_guard_names_what_is_at_its_path`: a rival committed at the `write:before-apply` seam gives `conflict` with the rival's version and etag; a rival that moved the row away gives `conflict` with no `data`.
- `test_a_required_etag_adds_no_statement_to_an_edit`: the list of statement verbs with `if_matches` equals the list without, on twin files, and counts 7. A stale one issues 1 statement, the snapshot.

`tests/storage/database/test_trash.py` and `tests/storage/database/test_topology.py`, at the seam as the system actor:

- `test_a_required_etag_adds_no_statement`, in `test_trash.py` over a delete of a file, a cascading delete of a directory and a delete of an empty directory without cascade, and in `test_topology.py` over a move of a file within one directory: the list of statement verbs with `if_matches` equals the list without, on twin fixtures. The counts are 4, 5, 6 and 16.
- `test_a_stale_etag_issues_no_mutation_statement`, over the same four: 0 statements that begin `INSERT`, `UPDATE` or `DELETE`.
- `test_a_ten_thousand_target_delete_with_a_key_for_every_row_adds_no_statement`. Marked `slow`.

`tests/storage/database/test_reads.py`:

- `test_a_read_issues_the_statements_it_issued_before_the_etag`: on the fixture of "What the code does today", through the kernel as the system authority, the eight read verbs issue 1, 1, 2, 2, 1, 7, 8 and 3 statements.
- `test_a_listing_mints_once_for_each_row`: a `glob` of 10,000 rows calls `EtagMint.mint` 10,000 times, and one whose rows are all bare calls it 0 times. Marked `slow`.

`tests/storage/database/test_races.py`, on the Postgres leg:

- `test_a_rival_inside_the_window_refuses_a_required_change`, for `write`, `edit`, `delete` and `move`: a rival committed inside the window leaves the rival's state, and the call answers `conflict`.

`tests/storage/database/test_engine.py`:

- `test_two_storage_objects_over_one_database_mint_one_etag`: two storages opened on one SQLite file return 1 distinct etag for one row, and a storage on another file returns another for a file at the same path and version.

`tests/test_sync.py`: the twin tests pass with the new arguments on both synchronous faces.

Every test that passes `if_version` or `if_versions` is rewritten to read the row and pass its etag: 66 uses in `tests/test_params.py`, `tests/base/test_dispatch.py`, `tests/support/storage_contract.py`, `tests/storage/database/test_writes.py` and `tests/storage/database/test_races.py`. The recorder storage in `tests/support/base_doubles.py` declares the trait. A test that compares a whole row gains the field.

## Scope

In:

- New: `src/vfs/etag.py`.
- `src/vfs/__init__.py`, `src/vfs/models/__init__.py`, `src/vfs/models/entry.py` (`Observation.etag`, the field partition), `src/vfs/models/rows.py` (`ULIDBytes`, `entry_key_of`).
- `src/vfs/params.py`, `src/vfs/base.py`, `src/vfs/session.py`, `src/vfs/sync.py`, `src/vfs/sync_session.py`.
- `src/vfs/storage/protocol.py` (the seam, the trait vocabulary).
- `src/vfs/storage/backends/database/`: `engine.py` (the mint, built at first touch), `backend.py` (the trait, the arguments), `reads.py`, `listings.py`, `grep.py`, `search.py`, `traverse.py` (the id and the mint on each row), `staging.py`, `writes.py` (the plan's comparison, the rows of a result, the `data` of two refusals), `serialized.py`, `trash.py`, `topology.py` (the comparison in each ladder, the rows of a result).
- `src/vfs/results/envelope.py` (the merge rule), `src/vfs/results/kinds.py` (the words of `conflict`).
- The tests above, and the entries of `tests/lint/allowlist.py` for each module that grows.
- The docs below.

Out: everything under "Left as it is", the schema, `crates/`, the shell, and every session rule.

The landings are decision 16's four. Each is green under `scripts/ci.sh` and `scripts/docs.sh check` alone. The Postgres leg runs before the pull request of the second, the third and the fourth.

## What the docs must say

- A row carries an etag wherever it carries a version. An etag names one file or directory at one version. It is compared and never taken apart.
- `if_match` is how a caller that reads, changes and writes back avoids replacing a change, or a file, it never saw. It works on `write`, `edit`, `delete` and `move`. `if_matches` is the same for a batch.
- A `conflict` names the version and the etag that are there now. Read the file again before sending them back.
- An etag changes when the row changes, and stays the same when a directory above it is moved, deleted or restored.
- A directory's etag changes when something is added to it, removed from it or renamed in it, and not when something deeper changes.
- A storage that issues no etag refuses a change that requires one.

Pages, each changed: the docstrings of `write`, `edit`, `delete` and `move` on `AsyncVirtualFileSystem`, which are the reference pages of the four faces; the `Observation` docstring, with `Etag` on `documentation/reference/python-api/entry.md` and a line on `index.md`; the `ErrorKind` docstring for the `data` of `conflict` and `exists`; `documentation/reference/python-api/storage.md` for the trait, its four promises and `EtagMint`; `documentation/reference/glossary.json` and `glossary.md` for the term; `context/standards/constitution.md`, Articles 1.3 and 1.5; `context/standards/roadmap.md`, the rows of stories K2 and K10 that name `if_version`; `documentation/how-to/keep-a-session-for-each-conversation.md`, the one sentence named below.

## Earlier decisions this reverses

- `agents/2026-11-20-write-takes-preconditions-and-an-append/`, decision 1: `if_version` and `if_versions` leave. Its reason, that a version is the one coordinate every reader holds, now holds of the etag. Its decisions 4 to 6 stand with the etag in the version's place. Its decision 10 gains `etag` in the `data` of `conflict` and `exists`. Its line under "Left as it is" that `edit`, `delete` and `move` take no expected version no longer holds. Its decision 11, no hash precondition, stands.
- The same spec's rule that a write which lost its guard reports the version of the row it probed: where that row has moved away, the refusal now carries no `data`.
- The spec merged from pull request 42, decision 2, in four places. The storage mints, where the router did. An etag from another mount is `conflict` from the storage, where it was `invalid` before any storage was called. A delete of a directory without cascade compares the entry and the version, where it compared the entry alone. The batch forms of `edit`, `delete` and `move` take `if_matches`, where only `write` did. Its sentence that `if_match` is exclusive with `if_version`, and its decision 4's sentence that an explicit `if_version` reaches storage unchanged, have nothing left to speak of.
- `context/standards/constitution.md`, Article 1.5, third bullet: reworded as decision 15 gives it.
- `context/standards/roadmap.md`, story K10: it stamped the `entry_id`, the version and the hash, and filled in `if_version`. The etag is the stamp, and `if_match` is what is filled in.

## Choices for the owner

Each is decided above. The decision stands until it is ruled on.

1. **`if_version` and `if_versions` leave** (decision 7). The other choice keeps them beside `if_match`, exclusive with it, with the four unsound cases written into the docstring.
2. **A delete of a directory without cascade compares the entry and the version** (decision 10). The other choice is the merged spec's, the entry alone, at the price of an etag in two halves and a second hash on every row.
3. **An etag from another mount is `conflict`, answered by the storage** (decision 12). The other choice puts a mount tag in clear at the front of the etag and refuses a foreign one `invalid` at the mount.
4. **Every listing row carries the etag** (decision 4), at 1.1 µs and 30 bytes a row. The other choice carries it only where `columns=` names it, and a session then reads each row again before a change.
5. **The batch forms of `edit`, `delete` and `move` take `if_matches`** (decision 6). The other choice refuses a precondition on them.
6. **The etag is a digest that cannot be taken apart** (decision 2). The other choice is a token that holds the id and the version, 40 characters, which another spec could read a version from.
7. **A `conflict` carries the etag that is there now** (decision 12). The other choice carries the version alone, so that no caller can send the etag back unread.

## Where this spec disagrees with the overview or the guides

- The overview: nothing.
- `documentation/how-to/keep-a-session-for-each-conversation.md`, line 258, says a call made on the file system guards a write only when the expected version is passed. Proposed: it guards a change only when the expected etag is passed, as `if_match=`. The evidence is "The problem": a version passed that way guards nothing in four cases, and decision 7 removes the argument.
- `documentation/how-to/interrupt-a-job-and-ask-a-person.md`: nothing. Its refusal of a step whose file changed is the `conflict` of decision 12.

## Not checked

- Postgres. No server was run. The Postgres guards were compiled from the builders, and the rival cases of decision 9 are read from the code and the landed spec. `ULIDBytes` was run on SQLite alone; on Postgres the driver hands back a UUID object whose `bytes` are taken, which is read and not run.
- The generic floor.
- The costs. They are a bench on one machine against in-memory SQLite. The share of a call they are on Postgres, where a row costs more to fetch, was not measured.
- The mean number of rows a read returns at the reference deployment. The 50 is an assumption.
- How many existing tests compare a whole row or a rendered table of every field, and so gain the new field.
- That the list of sites that build a row with a version is complete. It was made by a search for the constructors. The contract row of 17 calls is what catches a site that was missed.
- Whether a rendering pass moves a version. Decision 3 says only that an etag stays where the version does.
- The other eight specs. None was seen. Spec 3 may still pass `if_match` on a delete of a directory without cascade, or name `if_version`, and spec 5 may want a version read from an etag. Decisions 7 and 10 and choice 6 are where those meet this spec.
- A database copied by file or by dump, mounted beside its original.

## One line

Every row a caller may read says which entry it is and at what version in twenty characters, and a write, an edit, a delete or a move that passes them back changes that row or nothing.
