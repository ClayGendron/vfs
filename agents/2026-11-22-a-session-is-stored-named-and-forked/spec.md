# A session is stored under its owner and its id

A draft, written on 2026-11-22. It is not reviewed and nothing is built. It is spec 2 of the nine that `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md` maps, and it rests on that overview, on the guide `documentation/how-to/keep-a-session-for-each-conversation.md`, on the seven studies under `research/` in this directory, and on the code as read at commit `6dae6a1d`. Three probes were run that day against that tree, `spec2_probe1.py`, `spec2_probe2.py` and `spec2_probe3.py` under the session scratchpad's `specs/` directory. What each showed is written beside the claim it supports, because a scratchpad does not last.

## The outcome wanted

A host asks for a session with `fs.session(authority, id)`, in any process, and gets a handle to the same stored session whether or not that id was ever used. The id is a name the host chooses, or one VFS makes. The session is stored under its owner and its id together, so a caller with another authority who says the same id reaches a session of its own and never this one. Nothing is opened and nothing is closed. A session can be listed, asked whether it exists, and deleted, and it expires 30 days after its last use. Specs 3, 4, 5 and 7 hang their records on the row this spec stores.

## Builds on

- **The overview, the two guides under `documentation/how-to/`, and the seven studies under `research/`: written.** The guides describe an API that is not built.
- **Spec 0, `2026-11-22-the-kernel-keeps-records-of-its-own`: not written when this was drafted.** It owns the kernel store. This spec needs seven things from it.
  1. A kernel store for every root storage, and the table `vfs_sessions` made in it from the SQLAlchemy `Table` this spec declares.
  2. A synchronous path that runs this spec's statements in one transaction. On SQLite a transaction that writes begins as a writer. On Postgres it runs at READ COMMITTED. A store that cannot be reached raises one documented exception. The path also hands over the two budgets a statement is sliced by, the membership budget and the insert's parameter budget, because no module outside the database adapter may import from it (`tests/lint/test_code_shape.py:37-42`).
  3. A write-behind writer that takes one *use* per call (decision 17), keeps at most one per session, and at each flush calls `resolve` (decision 14) once for every session the flush names, inside the flush's transaction and before any other spec's rows are written.
  4. Two controls on that writer for one session: `settle`, which writes what this process has queued for the session and waits, and `discard`, which drops it.
  5. A sweep that calls this spec's two passes (decision 22) on its schedule, and can be interrupted between two chunks.
  6. On SQLite, a kernel store whose plain reads do not wait on its writer.
  7. A way for a test to count the statements issued on the kernel store's engine.
- **Spec 3, the stamps: drafted, and being rewritten.** Needs: a function that deletes at most 5,000 stamp rows of one `session_key` and returns the count; and a guard of its own for a shell line run by a caller that owns no session (decision 7).
- **Spec 4, turns, rewind and fork: not written.** Needs: it maintains `last_turn`, `turn_count`, `parent_key`, `parent_id` and `fork_turn`; a function that deletes at most 5,000 turn rows of one `session_key`; a fork holds rows of its own and reads nothing through its parent, so that removing a parent changes no fork; it decides what `fork(id)` does when the id exists; and it decides what a call does when a handle's current turn is no longer stored.
- **Spec 5, the change records: drafted.** Need: a function that deletes at most 5,000 change rows of one `session_key`.
- **Spec 6, policies: not written.** Need: what a policy is, and the check of a handle's `policies`.
- **Spec 7, jobs: not written.** Needs: a job names its session by `session_key`; a function that cancels the waiting jobs of up to 100 session keys inside the transaction it is handed, taking the authority that removed them and a reason; and it takes `owner_key` from `vfs.authority`. The guides construct `Principal(..., name=...)`, and `Principal` has no `name` today (`src/vfs/authority.py:87-89`). Ruling 8 is spec 7's, so the field is taken to be that spec's, and the owner key does not read it.
- **`context/specifications/archive/070-principal-scoped-sessions/spec.md`: landed 2026-09-06.** Its decision 4 stands. Its decision 5 is reversed in part (see "Earlier decisions this reverses").
- **The retired record `context/decisions/063-a-session-never-widens-itself.md`,** read with `git show 3667fec2^:context/decisions/063-a-session-never-widens-itself.md`. Its rules 1, 2 and 4 bind and are kept by decisions 4 and 5.
- **`documentation/maintainers/how-we-name.md`: published.** Decision 25 amends it.

## Terms

- **Session.** VFS's side of one conversation: who the agent is, what it has been shown, and where its shell is. It is a stored record.
- **Handle.** The Python object `fs.session(...)` returns. It names a session and holds nothing the store does not.
- **Owner.** The actor and the subjects of the authority a session is asked for with.
- **Owner key.** 64 hexadecimal characters derived from the owner. It is the first half of a session's stored name.
- **Id.** The second half of the name. The host chooses it or VFS makes it.
- **Session key.** The integer the kernel store hands out for a session row. Every other table names a session by it. It is never handed out twice.
- **Kernel store.** Where the kernel keeps its own records, as spec 0 defines it.
- **Write-behind.** Written a moment after the call returns, by spec 0's writer, and never during the call.
- **Resolve.** To find a session's row by its owner key and id, and to make it when the caller has something to store.
- **Use.** One call made through a handle. It is what keeps a session from expiring.
- **Removal.** The end of a session: by `delete`, or by expiry.
- **Marker.** A removed session's row after its name is cleared, kept until the rows that hang on it are gone.
- **Host.** The application code that holds the file system object. An agent never holds it.

## What the code does today

Read at `6dae6a1d`. "Run" means one of the three probes.

| Fact | How it is known |
|---|---|
| A session is made by `open_session(authority)`, which builds a new object each time and takes no id. | Read, `src/vfs/base.py:655-663`, `src/vfs/sync.py:256-258`. |
| The object holds three values: the file system, the authority and a closed flag. | Read, `src/vfs/session.py:61-66`. Run: `__slots__` is `('_authority', '_closed', '_fs')`. |
| Two `open_session` calls issue 0 statements and return two objects. Nothing about a session is stored anywhere. | Run. |
| A warm `read` through a session issues the 3 statements the direct call issues. | Run. |
| A session is an `async` context manager. `close()` sets the flag, and a closed session never reopens. Entering a closed one raises `ValueError`. | Read, `src/vfs/session.py:76-93`, `:462-464`. |
| Each of the 26 public methods of a session, the 25 ops and `cli`, begins with a check of the flag, and a closed session answers `vfs.invalid` with "the session is closed and cannot reopen; open a new one". | Read, `src/vfs/session.py:42-49`, `:466-468`; 26 call sites counted. Run. |
| The synchronous `Session` wraps an `AsyncSession` and repeats the lifecycle: `closed`, `close`, `__enter__`, `__exit__`, and the flag checked before each hop. | Read, `src/vfs/sync_session.py:45-74`, `:364-366`, `:395-399`. |
| An open session on a closed file system answers `vfs.unavailable.backend`, "the filesystem is closed", on both faces. | Run. Read, `src/vfs/base.py:3069-3071`, `src/vfs/sync.py:691-698`. |
| The public names of a session are the 25 ops and `authority`, `cli`, `close`, `closed`. A test pins exactly that set and the return annotations. | Run. Read, `tests/base/test_authority.py:311-320`. |
| A session verb has the kernel verb's signature without `authority`, pinned per op. | Read, `tests/base/test_authority.py:274-284`. |
| `session.delete()` with no argument is the file verb, and is refused `vfs.invalid`: "Exactly one of path or observations must be provided". `fs.delete()` answers the same. | Run. |
| `str(Result(ops=("delete",)))` is "No changes". | Run. |
| A verb returns a `Result` and never raises for a refusal. A management method returns a typed value and raises: `mounts()` returns a tuple of `Mount`; `locate` raises `ValueError` on a closed kernel; the synchronous face raises `RuntimeError` after `close()`. | Read, `src/vfs/ops.py:110-113`, `src/vfs/base.py:581`, `:778`, `:2675`, `src/vfs/sync.py:72`, `:709-714`. |
| `grant`, `grants` and `set_posture` are ops, routed to a storage, and return a `Result`. | Read, `src/vfs/base.py:1741-1765`. |
| A call that names no authority runs as `default_authority`, or else as the anonymous caller. | Read, `src/vfs/authority.py:227-251`, `src/vfs/base.py:299`, `:314`. |
| An `Authority` has five fields: `subjects`, `actor`, `provenance`, `narrowing`, `source_identity`. A `Principal` has three: `sub`, `kind`, `scopes`. A subject set holds at most 64. `Narrowing` has one value. | Read, `src/vfs/authority.py:63-71`, `:80-89`, `:119-131`. |
| `subject_names` is every subject's `sub`, sorted. Two principals with one `sub` and different scopes may sit in one set, and the name then appears twice. | Read, `src/vfs/authority.py:200-203`. Run: `('ada', 'ada')`. |
| `owner_subject` is `None` for the anonymous authority, "else every anonymous caller would own every anonymous row". | Read, `src/vfs/authority.py:205-216`. |
| The anonymous authority's names are `('anon',)` and `anon`. The system authority's are `()` and `system`. | Run. |
| The refusal `vfs.unauthenticated` hints "open a session with an authority, or configure a default". | Read, `src/vfs/results/kinds.py:189`. |
| The naming page forbids a noun as a method and gives `session()` as its example, and lists `open_session()` under the verbs `open` and `close`. | Read, `documentation/maintainers/how-we-name.md:12`, `:34`. |
| `open_session` is named in 10 tracked files outside `src/`, `context/` and `agents/`: `tests/base/test_authority.py` (4 lines), `tests/test_sync.py` (8), `tests/shell/test_host.py` (4), `tests/base/test_listing_cursor.py` (1), `documentation/tutorials/control-who-can-access-files.md` (3), `documentation/maintainers/how-we-name.md` (1), and `docs/how-to/run-calls-as-a-principal.md`, `docs/reference/api.md`, `docs/reference/session.md` and `docs/reference/sync.md` (9 between them). | Run, `git grep -n open_session`. |
| The fences under `docs/` are run by the gate. | Read, `scripts/ci.sh:79-80`. |
| `src/vfs/base.py` is 3,090 lines and is held at that count. | Read, `tests/lint/allowlist.py:27`. |

## The problem

A chat application handles each message in a new request, often in another process. Today's session lives in one object in one process, so whatever it comes to hold is lost between two messages. The stamps of spec 3 would be lost on every turn, and under strict every edit would be refused as unread. Two studied projects kept such a record in memory and both failed in this way (`research/coding-agent-sessions.md`, section 7; `research/wire-protocol-sessions.md`, lesson 1).

The fix is to store the session and let any process ask for it by name. A name the caller supplies is the hazard the studies return to most often. A server that makes a session for any id it is shown, keyed by the id alone, lets one caller prepare or guess the id another will use (`research/history.md`, lineage 2). One studied project adopts any existing id with no owner check (`research/coding-agent-sessions.md`, section 1). One joins a supplied id into a path unchecked (`research/forking-files.md`, section 1). One mints its ids in the browser with a generator its own docstring calls not secure (`research/chat-protocols.md`, section 1). One has no create step, no owner and no bound on growth (`research/langgraph-threads.md`, sections 1 and 2).

Today's lifecycle also has nothing left to do. `close()` releases nothing, since a session holds no resource, and the closed flag costs 26 checks, two context managers and one refusal that protects no state.

## Decisions

### 1. A session is a record the kernel keeps, and it is not a sixth first-class thing

Article 1 of the constitution allows five first-class things and requires each to have a path. A session has no path and is none of them. It is a record the kernel keeps about calls, as a grant and a posture are records about rights. It is reached through methods of the file system and of the handle, and through nothing in the namespace. It adds no entry kind and no primitive. A view of sessions in the namespace is left out, as the overview rules.

Reason: a session describes callers, not the tree. Forcing it into the namespace would make a file of something that is not one, which article 3 warns against.

### 2. `fs.session(authority=None, id=None, *, strict=True, policies=())` returns a handle and does no I/O

```python
def session(
    self,
    authority: Authority | None = None,
    id: str | None = None,
    *,
    strict: bool = True,
    policies: Iterable[object] = (),
) -> AsyncSession: ...
```

It is a plain method on both faces, never a coroutine, as `mounts()` is. `VirtualFileSystem.session` has the same parameters and returns a `Session`, with no hop to the loop thread. It issues no statement, awaits nothing, and stores nothing.

- `authority=None` is resolved once, here, by `caller_for(authority, default_authority, op="session")`: the kernel's `default_authority`, or else the anonymous authority, which decision 7 refuses.
- `id=None` makes an id here, by decision 11.
- A value that is not an `Authority` raises `TypeError`: "authority must be an Authority, got <type>".
- An id that is not a `str` raises `TypeError`, and an unlawful one raises `ValueError`, by decision 10.
- A `strict` that is not a `bool` raises `TypeError`: "strict must be a bool, got <type>".

A refusal here is raised, not returned, because the call returns a handle and has no `Result` to carry one. Every one of these is a mistake in the host's code, as a bad `Principal` is.

Reason: ruling 10 of the overview. A handle that costs nothing can be asked for at the top of every request.

### 3. The handle holds seven values, and only its current turn ever changes

| Slot | Public as | What it is |
|---|---|---|
| `_fs` | nothing | the kernel |
| `_authority` | `authority` | the authority every call is made as |
| `_id` | `id` | the id, as given or as made |
| `_ref` | nothing | the owner key, the id, and the actor and subject names, worked out once |
| `_strict` | `strict` | decision 4 |
| `_policies` | `policies` | decision 4, as a tuple |
| `_turn` | `turn` | the current turn, which spec 4 adds and `start_turn` sets |

- The classes keep their names: `AsyncSession` on the kernel and `Session` on the synchronous face, exported from `vfs`. The guides already use both.
- No method replaces `authority`, `id`, `strict` or `policies`. A host that wants other values asks for another handle.
- Two handles for one session are two objects. A handle compares and hashes by identity, because its turn can change.
- A handle cannot be pickled or sent to another process. What crosses a process boundary is the authority and the id.
- Several calls may run at once through one handle. The handle is read by them and written by none.
- The handle carries every op and `cli`, and nothing that reaches a mount or the kernel. The test that pins this stays, with the new set of names.

Reason: a handle that holds nothing the store does not can be dropped at any moment, and two processes can never disagree about a session because of what one of them remembers.

### 4. `strict` and `policies` belong to the handle and are never stored

`strict` is read by spec 3 and `policies` by spec 6. This spec carries them. Each call is judged by the values of the handle it came through.

- Nothing about either is written to `vfs_sessions`. A policy is a function and cannot be stored, by ruling 2. A stored `strict` would make two handles with different values a conflict that some rule must settle, and there is no such conflict when each handle answers for itself.
- A session's policies are added to the file system's and can only ask for more review, as the guide says. The handle offers no way to take one away.
- Until spec 6 lands, a non-empty `policies` raises `ValueError`: "policies are not served yet". Spec 6 removes that line. A host that asked for review must never be given silence.
- Until spec 3 lands, nothing reads `strict`.

Reason: the session is a serializable record, and these two are code and a caller's wish.

### 5. A session stores no right, and every call is judged on the handle's authority at the time of the call

The row holds no grant, no level and no decision. A call through a handle is the kernel's verb with the handle's authority, and the kernel derives the caller's rights again on that call. A right taken away takes effect on the next call through every handle.

A handle never widens: its authority is fixed when it is made. A wider authority is a new handle, from a new proof, made by the host.

Reason: rules 1, 2 and 4 of the retired record on sessions, and decision 4 of the archived spec. A stored right would be a stale right.

### 6. The owner is the actor and the subjects, and the owner key is a SHA-256 over them

```python
OWNER_KEY_DOMAIN: Final = "vfs.owner.v1"

def owner_key(authority: Authority) -> str:
    names = sorted(set(authority.subject_names))
    payload = json.dumps([OWNER_KEY_DOMAIN, authority.actor.sub, names], ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("ascii")).hexdigest()
```

It lives in `src/vfs/authority.py`, beside `owner_for`, and spec 7 uses the same function for jobs. It raises `ValueError` for the anonymous authority (decision 7).

- **Encoding.** A JSON array of three items: the domain string, the actor's `sub`, and the subjects' distinct `sub` values in sorted order. JSON quotes and escapes each name, so no two different owners produce the same text. A separator character joined between names would not have that property, and one studied project has an open bug from exactly that (`research/framework-session-stores.md`, section 1). Run: actor `a:b` for subject `c` and actor `a` for subject `b:c` give different keys.
- **`ensure_ascii=True`.** The text is ASCII whatever the names hold, so a name with a lone surrogate still encodes. Run.
- **Length.** 64 lowercase hexadecimal characters, always. Run. A subject set may hold 64 names of any length, and a hash is what keeps the key inside an index.
- **Not secret.** Anyone who knows the names can work the key out. It is never accepted from a caller. It is only ever computed from an `Authority`.
- **What is in it.** The actor's `sub` and each subject's `sub`, and nothing else.
- **What is not.** A principal's `kind` and `scopes`: rights are granted to a `sub`, and a token renewed with other scopes is the same caller. Run: both are ignored. A principal's display name, when spec 7 adds one. `provenance` and `source_identity`: the same caller proven at the edge or built in process is one owner. `narrowing`: it limits what a call may do, which decision 5 judges on each call, and does not change whose session it is.

Narrowing has one value today. When it gains a second, a narrowed authority keeps its owner key. The session's shell state can then pass from a wider handle to a narrower one of the same owner, so a host that narrows an authority for a part of its work gives that part an id of its own.

| Authority | Owner |
|---|---|
| a person acting as itself | its own, apart from every agent's |
| an agent acting for one person | that pair |
| the same agent acting for another person | another owner |
| an agent acting for a set | that agent and that exact set, in any order |
| the system authority | one owner, decision 8 |
| the anonymous authority | none, decision 7 |

Reason: the overview's ownership rule. One studied server adds a digest of the user to an id its clients make, and that is what makes a client-made id safe (`research/history.md`, lineage 3). Another puts the user in the key beside the id (`research/framework-session-stores.md`, section 1).

### 7. An anonymous authority owns no session

`fs.session(Authority.anonymous(), ...)` raises `ValueError`: "an anonymous caller owns no session; pass an authority that names the caller". So does `fs.session()` on a kernel with no `default_authority`. `fs.sessions` called as the anonymous authority returns an empty page and issues no statement.

Every anonymous caller is one principal, `anon`. If it owned sessions, every anonymous caller would be one owner, and the id would be the only thing between two of them. The id would then be a credential, which the overview rules it never is. One caller could read another's shell variables, cancel its waiting jobs, or prepare an id for it to walk into.

A host with callers it cannot name gives each a principal of its own, or works without a session, which the guide allows. A guard for one shell line run by an anonymous caller stores nothing and is spec 3's own.

Reason: it is the rule `owner_subject` already applies to rows, for the same reason, applied to sessions.

### 8. The system authority owns sessions as one owner, and lists every owner's

`fs.session(Authority.system(), id)` is lawful. Every caller that holds the system authority is one owner. That is not the hazard of decision 7, because the system authority cannot be derived from anything on a wire. Whoever holds it is the host itself.

The system authority has no way to open another owner's session by its id, and needs none. A row that `fs.sessions` returns names its actor and its subjects, and a host that can build any authority can build that one. The host is trusted inside the process, as the archived spec's trust model states.

Reason: one rule for every named authority, and no impersonation call to guard.

### 9. A subject set that changes is another owner, so the conversation gets a new and empty session

An agent acts for two people in a group chat. A third joins. The authority of the next request has three subjects, its owner key differs, and `fs.session(authority, "conv_123")` is a session that has never been used.

What follows, plainly:

- The session has seen nothing. Under strict the next change to a file is refused as not read, and one read clears it.
- The shell starts at `/` with no variables.
- The turns of the old session cannot be rewound to through the new one.
- A job the old session left waiting is not listed by the new session. It is still answered through `fs.resume(job_id, ...)`.
- The old session stays, reachable only with the old authority, and expires 30 days after its last use.

Why this is right, and not only tolerable: the rights of a set are the least of its members' rights. When a subject joins, the set may see less than it did. The old session holds what was shown under the old rights, in its stamps and in its shell variables. Carrying it over would put that in front of a conversation that now includes someone who may not see it. The same rule the other way costs only a few reads.

What to do instead, where a host wants one memory across the change: nothing in these nine specs copies a session to another owner. It is named under "Left as it is" with the facts a later spec needs.

Reason: the owner is the whole authority, by the overview and by the guide's own example of one agent working for two people.

### 10. An id is 1 to 255 visible ASCII characters, kept exactly as given

- **Characters.** Each is in the range `0x21` to `0x7E`. No space, no control character, nothing outside ASCII. This is the rule one wire protocol set for its own session ids (`research/wire-protocol-sessions.md`, section 1), and it holds every id form the guide's table names.
- **Length.** 1 to 255, the overview's default, as `SESSION_ID_MAX: Final = 255`. A character is one byte, so 255 characters is 255 bytes on both engines.
- **No normalisation.** The id is stored and compared byte for byte. `Conv_1` and `conv_1` are two sessions. Nothing is trimmed, folded or coerced.
- **A `str` only.** An integer, a `UUID` object or `bytes` raises `TypeError`: "a session id is a str, got <type>". Coercing with `str()` would make `123` and `"123"` one session without the host having said so.
- **The refusal.** `ValueError`: "a session id is 1 to 255 visible ASCII characters", followed by the length, or by the first character outside the range as `repr` prints it.
- **An id is only ever a bind parameter.** It is never joined into a path, a table name or the text of a statement.

Run: `conv_123`, a UUID and `user:42/conv:7` pass; the empty string, 256 characters, a space, a newline and `café` are refused.

Reason: a name the host's browser may have made must be safe to carry anywhere, and one byte order on both engines keeps a listing in one order.

### 11. A generated id is `ses_` and 26 characters from 128 random bits

```python
def new_session_id() -> str:
    return "ses_" + base64.b32encode(secrets.token_bytes(16)).decode("ascii").rstrip("=").lower()
```

30 characters, from the operating system's secure generator. Run: 100,000 made, 100,000 distinct, all lawful under decision 10. Its uniqueness rests on the 128 bits and on no clock, so two processes that make ids in the same microsecond do not meet. A collision would name a session of the same owner and never another's, because the owner key is the other half of the name.

The prefix reserves nothing. A host may supply an id that begins `ses_`.

Reason: three studied projects had defects from a time inside an id or a name (`research/framework-session-stores.md`, lesson 3). The id is unguessable because it costs nothing to make it so, and not because anything rests on its being secret.

### 12. The same call returns the same session whether or not it exists, and no call asks to create one

There is no create and no open. `fs.session(authority, id)` is both, by ruling 10. A host that must know asks `exists()`.

The studies advise two separate verbs with a conflict rule (`research/langgraph-threads.md`, lesson 1; `research/history.md`, lineage 6). That advice answers two problems, and neither is left here. The first is another caller's id, which decision 6 closes: a session made for an id it is shown is made inside the caller's own owner, and no one else can reach it. The second is a mismatch between the parameters of the first call and a later one. A session has no such parameters, because decision 4 stores none.

Reason: with an owner in the key and nothing to compare, the two verbs would differ only in an error a host would have to handle on every request.

### 13. `vfs_sessions` holds one row per session, under a key that is never used twice

| Column | Type | Holds |
|---|---|---|
| `session_key` | 64-bit integer, primary key | Handed out by the engine and never reused: `AUTOINCREMENT` on SQLite, an identity column on Postgres, as `vfs_entries` does (`src/vfs/models/rows.py:370`, `:451`) |
| `owner_key` | `BytewiseString(64)`, not null | decision 6 |
| `id` | `BytewiseString(255)`, null | decision 10; `NULL` once the session is removed |
| `actor` | text, not null | the actor's `sub`, for a listing |
| `subjects` | text, not null | the subjects' distinct `sub` values, sorted, as a JSON array |
| `parent_key` | 64-bit integer, null | the session this one was forked from; spec 4 |
| `parent_id` | `BytewiseString(255)`, null | that session's id when the fork was made, for display; spec 4 |
| `fork_turn` | 64-bit integer, null | the number of the last turn the fork took from its parent; spec 4 |
| `last_turn` | 64-bit integer, not null, default 0 | the last turn number handed out; spec 4 |
| `turn_count` | integer, not null, default 0 | the turns the session holds now; spec 4 |
| `created_at` | timestamp with zone, not null | for display |
| `last_used_at` | timestamp with zone, not null | decision 17 |
| `expires_at` | timestamp with zone, not null | decision 18 |
| `removed_at` | timestamp with zone, null | set when the session is removed; decision 22 |

Indexes: a unique constraint `uq_vfs_sessions_name` on `(owner_key, id)`; `ix_vfs_sessions_expires_at` on `expires_at`; and `ix_vfs_sessions_removed_at` on `removed_at`, partial where it is not null.

- **The key is never reused.** A row written behind for a removed session must never land on another session. Run on SQLite 3.50.4: the row with the highest key was deleted, and the next row took a higher key.
- **Both engines treat `NULL` ids as distinct** in the unique constraint, so any number of markers share an owner. Run on SQLite. On Postgres it is the documented default and was not run.
- **`parent_key` is the truth and `parent_id` is for display.** After a parent is removed and its id used again, the id would point at the wrong session and the key points at none.
- **A turn number is the fork point,** not a turn id, because a turn's id can be used again after a rewind and its number cannot.
- **`actor` and `subjects` are unindexed text,** so a long name fails no length check.
- This table adds five columns to what the overview's row for it lists: `actor`, `subjects`, `parent_id`, `turn_count` and `removed_at`. The reasons are in decisions 8, 20 and 22 and in the two items above.

Reason: an order is a counter and never a clock, by the overview, and a name that can be freed needs an identity that cannot.

### 14. The row is first written by the first record that needs it, through one function, `resolve`

Asking for a handle stores nothing. The row is made when some spec has a record to store for the session: a stamp, a turn, a change record, a job, a fork. Each of them calls one function, inside the transaction that writes its own rows.

```python
class SessionRef(NamedTuple):
    owner_key: str
    id: str
    actor: str
    subjects: tuple[str, ...]

async def resolve(
    connection, refs: Sequence[SessionRef], *, create: bool, now: datetime, lifetime: timedelta
) -> dict[tuple[str, str], int]: ...
```

It returns each session's key by `(owner_key, id)`. A session with no row is left out of the answer when `create` is false, and gets a row when it is true. `now` is passed in and never read inside.

The steps, with `refs` made distinct first:

1. **Read.** One `SELECT session_key, last_used_at, expires_at` by membership of the pair `(owner_key, id)`. The pairs are sliced at half of the membership budget, since a pair is two binds. That budget is `membership_budget(profile, parameter_budget)` (`src/vfs/storage/backends/database/dialects.py:541`), handed over by the kernel store.
2. **Replace what expired.** A row whose `expires_at` is before `now` is removed by decision 22's first step when `create` is true, and is then absent. When `create` is false it is treated as absent and left for the sweep.
3. **Create.** With `create` true, one multi-row `INSERT ... ON CONFLICT (owner_key, id) DO NOTHING RETURNING session_key, owner_key, id` for the absent, sliced by the insert's parameter budget at seven binds a row.
4. **Read again** the pairs that step 3 did not return, which another transaction created first (decision 15).
5. **Touch.** One `UPDATE` of `last_used_at` and `expires_at` for the rows decision 17 finds due, by `session_key`, sliced by `membership_budget`.

| Case | Statements |
|---|---|
| the row is there and was used in the last five minutes | 1 |
| the row is there and a touch is due | 2 |
| the row is absent and `create` is false | 1 |
| the first write | 2 |
| the first write, lost to a rival | 3 |
| the row has expired and `create` is true | 3, and spec 7's cancel once it lands |

The read comes first because the common case is a row that is there. It also spends no key: an insert that does nothing still takes a number from the engine. Run on SQLite: seven inserts that did nothing moved the next key from 3 to 10.

Reason: one seam for five kinds of record means one place where a session comes to exist, and one statement in the common case.

### 15. Two first writes at the same moment end as one row, on both engines

Two processes resolve one new session at once. Both read and find nothing. Both insert.

- **Postgres, at READ COMMITTED.** The second insert meets the first's uncommitted entry in the unique index and waits for that transaction. When it commits, the second inserts nothing and returns no row, and its read in step 4 is a new statement with a new snapshot, which sees the committed row. When the first rolls back, the second inserts. Either way one row exists and both hold its key. Neither sees an integrity error. This rests on the engine's documented behaviour and was not run.
- **SQLite.** The kernel store has one writer. The second transaction begins after the first commits, its insert does nothing, and step 4 reads the row. Run: 8 threads on 8 connections resolved one new session at once, and the table held 1 row and every thread held key 1.
- **A kernel store in memory.** It belongs to one process. Two tasks meet as two SQLite transactions do.

A transaction that ran at a snapshot level on Postgres would not see the rival's row in step 4. That is why this spec needs READ COMMITTED of spec 0. If step 4 ever finds no row, `resolve` raises, and it never guesses a key.

Reason: the unique constraint is the arbiter, as it is for two creates of one path, and a check in Python alone is the race the studies found most often (`research/framework-session-stores.md`, lesson 2).

### 16. A handle keeps no copy of the row, so every record names its session by owner and id

A handle does not remember its `session_key`. Each transaction that stores something resolves the key again.

The other design was costed. A handle that kept the key would save one statement on a write. But a session can be removed by another process. The handle would then go on writing under a key whose row is gone, and reading its own orphans back, as a second session under the same id that no other handle can see. With no copy, the next record after a removal resolves, finds no row, and makes the new session that every handle then shares.

Reason: the overview's rule that the handle holds no state the store does not, taken literally, at the price of one read by a unique index.

### 17. Every call through a handle reports one use, written behind, and a row is touched at most once in five minutes

When a call through a handle returns, the handle hands spec 0's writer one use: its `SessionRef` and the time. This is a write to memory. It issues no statement and awaits nothing. The writer keeps one use per session, the latest.

At a flush, every session the flush names is resolved once. A session that has rows to write is resolved with `create` true, and one named only by a use with `create` false, so **a use alone never makes a row**. A session that has stored nothing has nothing to expire.

A touch is due when the stored `last_used_at` is more than `SESSION_TOUCH_SLACK: Final = timedelta(minutes=5)` before `now`. The age is read from the row in step 1 of `resolve`, so no process keeps a table of what it touched. The touch sets `last_used_at = now` and `expires_at = now + lifetime + SESSION_TOUCH_SLACK`.

- A synchronous `resolve`, such as a turn being started, touches by the same rule.
- `exists()`, `fs.sessions` and the sweep are not uses. Asking whether a session exists does not keep it alive.
- `last_used_at` may be up to five minutes behind the true last use. It is for display and for expiry, and is never an order.

Reason: the overview's bar that a read adds no synchronous statement. The slack bounds the updates of one row to 12 an hour however many calls a session makes.

### 18. A session expires 30 days after its last use, and is gone from that moment

`AsyncVirtualFileSystem(session_lifetime=timedelta(days=30))`, and the same on `VirtualFileSystem`. The value is a `timedelta` greater than zero. Anything else raises `ValueError` from the constructor: "session_lifetime must be a timedelta greater than zero". There is no value that means never.

- **Never early.** The stored `expires_at` carries the slack of decision 17, so it is never before the true last use plus the lifetime. A new row is given the `expires_at` a touch would give it.
- **Exact in effect.** Every read of the table treats a row whose `expires_at` has passed as absent: `exists()` is false, a listing leaves it out, and `resolve` replaces it. A session used on day 31 is a new and empty one whether or not the sweep has run.
- **The sweep only reclaims.** It removes what has expired, by decision 22.
- **The lifetime in force is the one of the process that last touched the row.** A host that changes it sees the new value on each session's next touch.
- **One clock read per call,** at the kernel, passed down as `now`. Two processes whose clocks differ by seconds differ by seconds in a 30-day lifetime.

Reason: every mature system the studies read has a retention rule, and the one that went two years without one had to add it (`research/langgraph-threads.md`, section 7). An idle lifetime with no absolute one is enough, because the id grants nothing.

### 19. `session.exists()` reads one row and is not a use

```python
async def exists(self) -> bool: ...
```

It first asks the writer to `settle` what this process has queued for the session, then issues one `SELECT` by `(owner_key, id)` for a row that has not expired. It returns `True` when the session has stored anything.

- It follows the management convention: a typed value, and a raise where it cannot answer. On a closed kernel it raises `ValueError`: "Cannot read sessions: filesystem is closed". On the synchronous face it goes through the management hop, which raises `RuntimeError` after `close()`. A kernel store that cannot be reached raises spec 0's exception.
- Within one process the answer is exact, because of the settle. A read made in another process a moment ago may not be stored yet.
- At this spec's landing nothing public stores a record, so `exists()` is `False` until spec 3 or spec 4 lands.

Reason: the guide's sentence for it, and a question that must not change its own answer.

### 20. `fs.sessions(authority=None, *, after=None, limit=None)` returns one bounded page

```python
async def sessions(
    self, authority: Authority | None = None, *, after: str | None = None, limit: int | None = None
) -> SessionPage: ...

@dataclass(frozen=True, slots=True)
class SessionInfo:
    id: str
    parent: str | None
    turns: int
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    actor: str
    subjects: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class SessionPage:
    rows: tuple[SessionInfo, ...]
    next_after: str | None
```

`SessionPage` has `Result`'s sequence protocol over `rows`: `len`, iteration and indexing. `str(page)` is a table of `id`, `parent`, `turns` and `last_used_at`, with a last line `more: after=<key>` when `next_after` is set, the words a listing already uses (`src/vfs/results/render.py:72`).

| Caller | Sees | Order | `next_after` |
|---|---|---|---|
| a named authority | the sessions under its own owner key | by `id`, in byte order | the last id of the page |
| the system authority | every session of every owner | by `session_key` | the last key, in decimal |
| the anonymous authority | nothing, with no statement issued | | `None` |

- `authority=None` is the `default_authority`, or else anonymous.
- `limit=None` is `SESSIONS_PAGE_DEFAULT: Final = 100`. A `limit` is an integer from 1 to `INT_CEILING`, as a listing's is (`src/vfs/params.py:145-147`).
- One statement a page, with `LIMIT limit + 1`. The extra row says whether there is more and is not returned.
- `after` is a value a page returned. One that is not a lawful id, or for the system authority not a decimal integer, raises `ValueError`.
- A listing leaves out markers and expired rows.
- It is a management method: it joins `MANAGEMENT_METHODS`, returns a typed value, and raises as `exists()` does.
- Another owner's sessions are never in a named caller's page, in any order, by any `after`.

The order by `id` is the unique index's own, so a page is a range read and stays stable while sessions are touched. An order by last use would need an index every touch rewrites, and rows would move between two pages.

Reason: article 2 of the constitution requires every listing to be bounded with a cursor. `turn_count` is on the row so that a page needs no second statement over spec 4's table.

### 21. `session.delete()` with no argument removes the session

This is the overview's name, and the handle already has a file verb called `delete`. The decision keeps the name and makes the one call that can be told apart mean removal. "Where this spec disagrees with the overview or the guides" proposes another name, with the evidence.

```python
NOT_GIVEN: Final[Any] = _NotGiven()   # in src/vfs/session.py; its repr is "NOT_GIVEN"

async def delete(
    self, path: str | None = NOT_GIVEN, observations: list[Observation] | None = None, *, cascade: bool = True
) -> Result: ...
```

- **The call that removes the session passes no argument at all.** That is: `path` is `NOT_GIVEN`, `observations` is `None` and `cascade` is `True`.
- **Every other call is the file verb,** unchanged. A `path` that is `NOT_GIVEN` is passed to it as `None`.
- **An explicit `None` stays the file verb's refusal.** `session.delete(path=None)` and `session.delete(None)` answer `vfs.invalid`, as today. A wrapper that passes on a missing argument as `None` therefore never removes a session.
- **It returns a `Result`,** because one method has one return type and the file verb's is `Result`. A removal returns `Result(ops=("delete",))`, with no row and no error, and it never raises. A kernel store that cannot be reached is `backend_unavailable`, and a closed file system is the kernel's closed refusal.
- **It is the same answer when there was no session.** Removing a session that never stored anything, or was already removed, succeeds and writes nothing.
- **It is not a step.** No policy of spec 6 is shown it.
- The synchronous `Session.delete` has the same default and goes through the verb hop.
- The test that pins a session verb's signature to the kernel's admits this one default by name.

Reason: the overview's public names, kept. The sentinel is what lets the name be kept without turning a refused mistake into a removal.

### 22. Removal frees the id in one commit and reclaims the rest in bounded chunks

A removal is `delete`, or an expiry met by `resolve` or by the sweep. It has two steps.

**Step 1, one transaction.** Find the row. `UPDATE vfs_sessions SET id = NULL, removed_at = :now WHERE session_key = :k AND removed_at IS NULL`. Call spec 7's function to cancel the session's waiting jobs, in the same transaction, as the authority that removed it: the handle's for `delete`, the system authority for an expiry. Commit.

From that commit the name is free. `exists()` is false, the session is in no listing, and the next record for that owner and id makes a new row with a new key. The old row is a marker.

**Step 2, bounded chunks.** For the marker's key, each of specs 3, 4 and 5 deletes its rows, at most `SESSION_RECLAIM_CHUNK: Final = 5_000` to a transaction, until none is left. The kernel holds their three functions in one tuple, `SESSION_CHILDREN`, which is empty at this spec's landing and which each of them joins in its own. Then the marker itself is deleted.

- **`delete` runs both steps.** Before step 1 it tells the writer to `discard` what this process has queued for the session. If step 2 fails or the call is cancelled, the removal has still happened, the result is still a success, one `WARNING` is logged on `vfs.session`, and the sweep finishes the work.
- **`resolve` runs step 1 only,** for a row it finds expired, and leaves step 2 to the sweep. A call that happens to arrive on day 31 does not pay for the reclaim.
- **The sweep has two passes.** The first reads up to `SESSION_SWEEP_BATCH: Final = 100` keys whose `expires_at` has passed, by the index, and runs step 1 for them in one transaction. The second reads up to 100 markers by their index and runs step 2 for each. Each pass repeats until it finds nothing, and can stop between two chunks.
- **A crash between the steps loses nothing.** The marker is in the store, and its index is how the sweep finds it. No pass scans the table.

What goes with a session, and what does not:

| Thing | On removal |
|---|---|
| its turns, its stamps, its change records | deleted, in step 2 |
| its waiting jobs | cancelled, in step 1, by spec 7; a later `resume` of one answers that it was cancelled |
| its finished jobs | left to spec 7's own lifetime |
| its forks | not deleted and not changed; `parent_key` then points at no row, and `parent_id` still shows the name |
| the files it changed | untouched |
| its id | free at once; used again, it is a new and empty session with a new key and a new `created_at` |

No name is kept reserved after a removal. One studied project reserves every branch name for ever (`research/framework-session-stores.md`, section 4). There the name was the only identity. Here the key is, and the owner who removed a session is the only caller who can ever say its name again.

**A late record.** A read in another process may have a stamp queued when the session is removed. Its flush resolves, finds no row, and makes the session again, holding that one read. This is the id being used again, which it was. It authorizes nothing: a stamp is checked against the file when a change is made. Within one process the discard makes `delete` exact.

Reason: a removal that waits for every row holds a writer for as long as the session was long. Freeing the name in one commit is what the caller asked for, and the chunk size is the one the log cost study measured at 21 ms on SQLite and 67 ms on Postgres at the median.

### 23. `open_session`, `close`, the context manager and the closed refusals are removed, and nothing replaces them

Removed from `AsyncSession`: `closed`, `close`, `__aenter__`, `__aexit__`, `_close_now`, `_refuse_closed`, its 26 call sites, `CLOSED_SESSION_DETAIL` and `closed_refusal`. Removed from `Session`: `closed`, `close`, `__enter__`, `__exit__` and the three checks of the flag. Removed from both file systems: `open_session`.

No alias is kept, by ruling 15. `fs.session(authority)` with no id is what `fs.open_session(authority)` was: a handle whose verbs carry the authority.

Reason: a session holds no resource of the process, so there was nothing to close. Two wire protocols learned that a session tied to an object's or a connection's life ends whenever a stateless handler returns (`research/wire-protocol-sessions.md`, lesson 1).

### 24. After its file system is closed, a handle answers as the file system does

| Call | On a closed file system |
|---|---|
| `fs.session(...)` | returns a handle; it reads no state |
| a verb or `cli` through a handle | the kernel's own refusal, `backend_unavailable`, "the filesystem is closed" |
| `session.delete()` | the same refusal |
| `session.exists()`, `fs.sessions(...)` | raises: `ValueError` on the kernel, `RuntimeError` on the synchronous face |

The handle has no closed state of its own. Closing the file system removes no session. A session in a database is there for the next process. A session of an in-memory root is gone with the store that held it.

Reason: one closed fact, the kernel's, in place of two.

### 25. `documentation/maintainers/how-we-name.md` gains one exception, for `session()`

The page forbade `session()` because the name hid that the thing had to be closed. Nothing is made by the call any more and nothing has to be closed. The amendment, exactly:

Under "Nouns", the second item becomes:

> - **A noun is never a method name by itself, with one exception.** A method called `posture()` does not say whether it reads the posture or sets it. The exception is a method that takes the key of one thing and returns a handle to it, and does nothing else: it stores nothing, reads nothing, and returns nothing that must be closed. `session(authority, id)` is that method. It is the singular of `sessions()`.

Under "Methods", one row is added after "Plural noun":

> | Singular noun, with a key | The method returns a handle to the one thing the key names, and does no work | `session()` |

Under "The verbs", the last row becomes:

> | `open`, `close` | The thing holds resources of this process and must be closed | `close()` |

The page's first sentence says a word has one meaning. `delete` on a handle has two under decision 21, and the amendment does not hide it: the disagreement is listed below.

Reason: the rule exists so that a name does not hide work or a duty. This name hides neither. `use_session` is the alternative, under "Choices for the owner".

### 26. Two landings, each green

1. **The handle.** `fs.session` in place of `open_session`; decisions 2 to 12 as far as they need no store; decision 23; decision 24's first two rows; decision 25; `owner_key`; every caller rewritten; the docs. It needs nothing from spec 0. `exists`, `sessions`, the removal form of `delete` and `session_lifetime` are not yet there.
2. **The row.** `vfs_sessions`, `resolve`, the use, `exists`, `fs.sessions`, removal, expiry and `session_lifetime`. It needs spec 0.

Reason: the first is of use alone, since it removes a lifecycle that did nothing, and it lets specs 3 and 6 name the handle before the store exists.

## Cost

Costed against the reference deployment in the working agreement. Its callers start 2 to 5 agent sessions a person a day, so about 3,500 new sessions a day, and with a 30-day lifetime about 105,000 rows at the centre and 150,000 at five a day. That count is an estimate from those figures.

**Per verb call, about 150,000 a day.** Asking for a handle issues no statement. A call through a handle adds no synchronous statement from this spec: it writes one use to memory. Behind the call, each flush issues one `SELECT` for all the sessions it names, however many calls they made. A flush of 256 records names at most 256 sessions, 512 binds. A touch is at most one `UPDATE` a flush, and at most 12 an hour for any one row. The bound over a day is the number of calls, 150,000, reached only if every call is more than five minutes after the last on its session.

**Per file write, about 1,050,000 a day.** A write through a session resolves the session once a call, not once a file, so that specs 3 and 5 can write their rows: one read by a unique index. The 50,000 single-file writes a day add at most 50,000 such reads. The nightly batch is 100 calls and adds 100.

**Per index visit.** Nothing.

**Per batch.** One `resolve` for a 10,000-entry call. Its statement does not grow with the entries. The removal of a session that made such a call reclaims its 10,000 change records in 2 chunks.

**Per corpus, once a day.** The sweep reads expired rows and markers by their indexes, never the table. At a steady state about 3,500 sessions expire a day: 35 transactions of step 1, and step 2 in chunks of 5,000 rows.

**Per lock.**

| What is locked | For how long | Who waits |
|---|---|---|
| nothing, by `resolve`'s read, `exists` and a listing | | no one |
| the unique index entry of one new session | one commit | a rival creating the same session |
| one session row, by a touch or by step 1 | one commit | another touch, turn or removal of that session |
| the rows of one chunk of step 2 | one commit | no one who is served, since the marker's rows are reachable by no handle |
| on SQLite, the kernel store's one writer | one commit, and for a chunk about 20 ms at the median and 200 ms at most, as the log cost study measured | a stamp flush, a job being stored, another chunk |

No table lock is taken. No read of a file waits on any of this, because on SQLite the kernel store is a file of its own. No lock is held across a batch's body, a person's pause, or the whole of a removal.

**Size.** A row is 14 columns and three indexes, and holds the 64-character key twice. It was not measured. By the log study's 572 to 620 bytes for a 15-column row with two indexes, about 450 bytes is the estimate, and 150,000 rows about 70 MB.

**Memory.** The writer holds one use per session it has not flushed. A handle holds seven references.

## Left as it is

- **A copy of a session to another owner.** Decision 9 gives the case. A later spec would need: which authority may ask, since the host holds both; that the stamps copied were seen under other rights, so each must be dropped or checked against the new set's rights; and that shell variables may hold what the new set may not read.
- **An absolute lifetime.** A session lives as long as it is used.
- **A `SessionInfo.to_payload()` and sessions over MCP.** The overview leaves serving out.
- **A view of sessions in the namespace.**
- **Sessions across a storage that wraps another kernel.** The far kernel has sessions of its own, and a handle is not forwarded.
- **What a session a tool is handed may call.** The handle gains `resume` and `jobs` in spec 7, and whether a tool's handle carries them is that spec's rule.
- **Two whole turns at once on one session.** The guide leaves it to the host.
- **The scripts under `agents/2026-11-21-what-a-log-row-per-call-costs/scripts/`,** which call `open_session`. They belong to a finished study and no gate runs them.
- **`documentation/maintainers/mounts.md`,** whose two sentences about a session still hold.

## Tests

Each is written and seen failing before the code. A count is of statements recorded by a `before_cursor_execute` listener, leaving out `BEGIN`, `COMMIT`, `PRAGMA`, `SAVEPOINT`, `RELEASE` and `ROLLBACK`, on the engine named. Never of time. A time a test needs is passed as `now`, or set on the row by SQL.

The handle, first landing, in `tests/test_sessions.py` unless a file is named:

- `test_asking_for_a_session_issues_no_statement`: two calls of `fs.session`, with an id and without, issue 0 statements on the root mount's engine, and return two objects with equal `id` when the id was given.
- `test_a_made_id_is_thirty_lawful_characters`: 1,000 handles with no id have 1,000 distinct ids, each 30 characters, each beginning `ses_`, each lawful.
- `test_an_unlawful_id_is_refused`, one case each for: the empty string, 256 characters, a space, a newline, a character outside ASCII, an integer, `bytes`. The first five raise `ValueError` and the last two `TypeError`, and each message names the rule.
- `test_an_id_is_kept_byte_for_byte`: `Conv_1` and `conv_1` give handles whose refs differ.
- `test_an_anonymous_authority_owns_no_session`: `fs.session(Authority.anonymous())` and `fs.session()` on a kernel with no default each raise `ValueError`; with `default_authority` set, `fs.session().authority` is the default.
- `test_a_non_empty_policies_is_refused_until_policies_exist`: raises `ValueError`. Spec 6 deletes this test.
- `test_a_handle_offers_no_way_to_change_itself`: assigning `authority`, `id`, `strict` or `policies` raises `AttributeError`, on both faces.
- `tests/test_authority.py::test_the_owner_key_is_64_hex_characters`, `::test_the_owner_key_ignores_order_kind_scopes_and_repeats`, `::test_a_joined_subject_is_another_owner`, `::test_names_that_join_alike_do_not_collide` (actor `a:b` for `c` against actor `a` for `b:c`), `::test_the_owner_key_takes_any_name` (a lone surrogate), `::test_the_anonymous_authority_has_no_owner_key`, and `::test_the_owner_key_is_pinned`, which holds one known authority to one literal key, so a change of encoding fails by name.
- `tests/base/test_authority.py::test_a_session_verb_is_the_direct_call_with_the_authority_filled_in`, per op, through `fs.session(ALICE)`: equal results and equal calls recorded.
- `tests/base/test_authority.py::test_session_verbs_take_no_identity_argument`, per op, unchanged in the first landing.
- `tests/base/test_authority.py::test_a_session_cannot_reach_a_mount`: the public names of both faces are the 25 ops and `authority`, `cli`, `id`, `strict`, `policies`, and neither face has `close`, `closed`, `__enter__`, `__exit__`, `__aenter__` or `__aexit__`.
- `tests/base/test_authority.py::test_a_handle_on_a_closed_file_system_answers_as_the_file_system`, per op: `backend_unavailable`, and 0 calls recorded by the storage. It replaces `test_a_closed_session_refuses_and_dispatches_nothing` and `test_closed_is_final`, which are deleted.
- `tests/test_sync.py::test_the_constructors_and_the_context_managers_are_twins`: `session` is a twin on both faces as `mounts` is, and the count of a session's coroutines is the ops and `cli`.
- `tests/test_package.py::test_the_session_lifecycle_is_gone`: neither file system has the attribute `open_session`, and `vfs.session` has neither `CLOSED_SESSION_DETAIL` nor `closed_refusal`. 4 names looked for, 0 found.
- `test_a_wrong_type_is_refused`: `fs.session("someone")` and `fs.session(ALICE, strict=1)` each raise `TypeError`.
- `test_a_right_taken_away_binds_the_next_call_through_a_handle`: one handle reads a file, the grant is revoked, and the same handle's next read is refused. 1 success, then 1 refusal, with no new handle made.
- `test_the_naming_page_names_session_as_the_one_exception`: `documentation/maintainers/how-we-name.md` holds "with one exception" once, the row "Singular noun, with a key" once, and `open_session` 0 times.

The row, second landing, in `tests/test_sessions.py`, on a SQLite file and on the Postgres leg unless one engine is named:

- `test_a_first_write_is_two_statements_and_the_next_is_one`: `resolve(create=True)` for a new session issues 2 statements on the kernel store and leaves 1 row; the same call again issues 1 and leaves 1 row.
- `test_a_use_alone_makes_no_row`: a `read` through a handle, then `settle`: 1 statement on the kernel store, 0 rows.
- `test_a_call_through_a_session_issues_no_statement_on_the_kernel_store`, for `read`, `ls` and `grep`: 0 statements between the call and its return.
- `test_a_10_000_entry_write_through_a_session_reports_one_use`: after `settle`, 1 statement on the kernel store. Marked `slow`.
- `test_eight_first_writes_at_once_leave_one_row`: 8 concurrent `resolve` calls on 8 connections leave 1 row and return 1 distinct key.
- `test_a_use_inside_five_minutes_updates_nothing`: with `last_used_at` set 4 minutes before `now`, 0 `UPDATE` statements; set 6 minutes before, 1, and `expires_at` is `now` plus the lifetime plus five minutes.
- `test_resolve_of_10_000_sessions_stays_inside_the_budget`: with the membership budget narrowed to 1,000 and the insert's parameter budget to 3,500, 10,000 new refs issue 20 `SELECT` statements of 500 pairs and 20 `INSERT` statements of 500 rows, leave 10,000 rows, and no statement carries more than 3,500 binds. Marked `slow`.
- `test_exists_is_false_then_true_then_false`: false on a new handle with 1 statement; true after a `resolve(create=True)`; false after `delete()`; and the row's `last_used_at` is unchanged by the three calls.
- `test_another_owner_sees_nothing`: two authorities resolve the same id. 2 rows. Each one's `exists()` is true, each one's `fs.sessions` holds 1 row, and `delete()` by one leaves the other's row.
- `test_a_listing_is_a_page`: 250 sessions of one owner; `fs.sessions(a)` returns 100 rows in id order with `next_after` set, and three calls return 250 distinct ids and end with `next_after` `None`. Each call issues 1 statement.
- `test_the_system_authority_lists_every_owner`: 3 owners with 2 sessions each give 6 rows in key order; a named owner's page holds 2; the anonymous authority's holds 0 with 0 statements.
- `test_a_bad_cursor_is_refused`: `after="a b"` raises `ValueError`, and for the system authority `after="x"` does.
- `test_a_bare_delete_removes_the_session`: 3 statements with no child rows; the row is gone; a second `delete()` issues 1 statement and succeeds.
- `test_a_delete_with_none_is_the_file_verb`: `session.delete(None)`, `session.delete(path=None)` and `session.delete(cascade=False)` each answer `vfs.invalid` and issue 0 statements on the kernel store, and the row is still there.
- `test_a_removed_id_is_a_new_session`: after `delete()`, a `resolve(create=True)` returns a key greater than the old one, and `created_at` is the new `now`.
- `test_removal_reclaims_in_chunks`: with one child function over a test table of 12,000 rows for the session, step 2 issues 3 deletes of that table, none of more than 5,000 rows, then 1 of the marker.
- `test_a_crash_between_the_steps_is_finished_by_the_sweep`: step 1 alone leaves 1 marker; the sweep's second pass leaves 0 rows.
- `test_an_expired_session_is_gone_at_once`: with `expires_at` set before `now`, `exists()` is false, the listing holds 0 rows, and `resolve(create=True)` returns a new key and leaves 1 marker.
- `test_the_sweep_reads_no_more_than_a_batch`: 250 expired rows are marked in 3 transactions.
- `test_a_fork_outlives_its_parent`: a row whose `parent_key` names a removed session is unchanged by both steps, and its `parent_id` still reads the name.
- `test_session_lifetime_is_a_positive_timedelta`: `timedelta(0)`, a negative one, `30` and `None` each raise `ValueError`.
- `tests/test_sync.py`: `sessions` is in `MANAGEMENT_METHODS` and has a twin; `Session.exists` is the twin of `AsyncSession.exists`; both raise `RuntimeError` on a closed facade.
- `test_a_closed_kernel_refuses_the_two_questions`: after `close()`, `await session.exists()` and `await fs.sessions(ALICE)` each raise `ValueError`, `fs.session(ALICE)` still returns a handle, and `await session.delete()` answers `backend_unavailable`. 0 statements on the kernel store.
- `tests/base/test_authority.py::test_session_verbs_take_no_identity_argument` admits one difference by name, the default of `delete`'s `path`.

## Scope

In, first landing: `src/vfs/session.py`, `src/vfs/sync_session.py`, `src/vfs/base.py`, `src/vfs/sync.py`, `src/vfs/authority.py` (`owner_key`), and a new module `src/vfs/session_records.py` holding `SessionRef`, the id rule and `new_session_id`. The hint at `src/vfs/results/kinds.py:189` becomes "This mount's posture needs a name: pass an authority, or configure a default." On the layer ladder (`tests/lint/test_code_shape.py:46-68`) the new module sits on the rung of `vfs.listing`, below `vfs.base`, and imports `vfs.authority` alone. The upward import of `vfs.session` by `vfs.base` stays allowed. Then the tests named above, and each caller, file by file:

| File | What it becomes |
|---|---|
| `tests/base/test_authority.py:266`, `:291`, `:303`, `:326` | `fs.session(ALICE)` with no `async with`; the two closed-session tests are replaced as "Tests" says; `:316` holds the new names |
| `tests/test_sync.py:257`, `:260-261` | the twin of `session`; the two context-manager lines go; `:254` counts the ops and `cli` |
| `tests/test_sync.py:627`, `:667`, `:761`, `:769` | `fs.session(ALICE)`, with no `with` |
| `tests/test_sync.py:634-656`, `:670-676` | the closed-session test is replaced by the closed-facade one, per op, and `test_sync_closed_is_final` is deleted |
| `tests/test_sync.py:717-718`, `:819-829` | unchanged: the two rewritten pages under `docs/reference/` keep their first headings and the words these lines look for |
| `tests/shell/test_host.py:910-911`, `:917-921` | the closed session's line leaves the list, which then holds four results and four expectations |
| `tests/shell/test_host.py:952-957` | renamed `test_a_session_runs_a_line_as_its_authority`; the two lines after the close go |
| `tests/shell/test_host.py:963`, `:969-975` | `fs.session(ADA)`; the closed-session assertion at `:975` goes and the closed-facade one stays |
| `tests/base/test_listing_cursor.py:348` | `fs.session(SYSTEM)` |
| `documentation/tutorials/control-who-can-access-files.md:71`, `:78-87`, `:203` | the new hint; "Ask for a session for each of two people"; `fs.session(...)` twice; the summary line names `fs.session` |
| `documentation/reference/python-api/sessions.md`, `index.md:12-13` | "What the docs must say" |
| `documentation/maintainers/how-we-name.md` | decision 25 |
| `documentation/reference/glossary.md`, `glossary.json` | the term Session |
| `docs/how-to/run-calls-as-a-principal.md:31-48` | "Or ask for a session", `s = fs.session(alice)` with two awaited calls, and the paragraph and fence about a closed session deleted |
| `docs/reference/session.md` | rewritten: construction by `fs.session`, the attributes of decision 3, no lifecycle section, no closed refusal |
| `docs/reference/sync.md:87-103` | the same for `Session` |
| `docs/reference/api.md:16`, `:24` | `session(authority=None, id=None, *, strict=True, policies=())`; the new hint |
| `docs/reference/glossary.md:51` | the new entry, without "Closed is final" |
| `docs/how-to/share-a-folder-with-grants.md:131` | the new hint |

In, second landing: `src/vfs/session_records.py` gains `SessionInfo`, `SessionPage`, the `Table` for `vfs_sessions`, `resolve`, the listing and the two steps of removal, and then also imports the kernel store's module, which must sit on a lower rung wherever spec 0 puts it; `session_lifetime` on both constructors; `sessions` on both file systems and in `MANAGEMENT_METHODS` (`src/vfs/ops.py:110`), whose docstring gains "or the kernel's own records"; `exists` and the removal form of `delete` on both handles; `SessionInfo` and `SessionPage` exported from `vfs`.

`src/vfs/base.py` changes length in both landings, and its entry in `MODULE_LINE_BASELINE` is set to the new count each time.

Out: everything under "Left as it is", and every table but `vfs_sessions`.

## What the docs must say

- **A session is VFS's side of one conversation, stored under its owner and its id.** The object is a handle. Asking for one costs nothing and stores nothing.
- **There is nothing to close.** No `with`, no `close()`.
- **The id is a name, never a key.** 1 to 255 visible ASCII characters, kept exactly as given. With no id, VFS makes one.
- **The owner is the whole authority.** Build the authority from the caller the host verified. A host that runs every caller as one principal has one owner, and then the id is all that separates two callers' sessions.
- **An anonymous caller owns no session.**
- **A session stores no right.** Every call is judged at the time of the call.
- **A session expires 30 days after its last use,** and the time shown for its last use may be five minutes behind.
- **A new member of a group conversation starts a new session.**

Pages, each changed: the docstrings of `AsyncVirtualFileSystem.session`, `.sessions`, `AsyncSession`, `AsyncSession.exists`, `AsyncSession.delete`, `SessionInfo` and `SessionPage`, which are the reference page's content; the class docstring of `AsyncVirtualFileSystem` for `session_lifetime`; and the pages in the table under "Scope".

The reference page `documentation/reference/python-api/sessions.md` opens:

> A session is VFS's side of one conversation. `fs.session(authority, id)` returns a handle to it, new or not, and the handle has every call the file system has, made as that authority. `AsyncSession` has calls you `await`, and `Session` has the same calls as plain ones. A session is stored by the file system, so there is nothing to open and nothing to close.

and then documents `vfs.AsyncSession`, `vfs.Session`, `vfs.SessionInfo` and `vfs.SessionPage`.

The glossary term, in `documentation/reference/glossary.md`, after Mount:

> ## Session
>
> A session is VFS's side of one conversation: who the agent is, what it has been shown, and where its shell is. **A session is stored by the [kernel](#kernel) under its owner and its id, and the object in code is a handle that holds nothing the store does not.** `fs.session(authority, id)` returns the handle, and it is the same call the first time an id is used and every time after.
>
> The owner is the whole authority: the actor, and everyone it acts for. The id is a name inside that owner and never a key that opens anything. A caller with another authority who passes the same id gets a session of its own.
>
> A session stores no right. Every call made through it is judged on its authority at the time of the call. A session is not an [entry](#entry) and has no path. It expires 30 days after its last use.
>
> In code the handle is `AsyncSession`, with calls you `await`, and `Session`, with plain calls.

and in `glossary.json`: `{"term": "Session", "summary": "VFS's side of one conversation, stored under its owner and its id.", "types": ["AsyncSession", "Session"]}`.

The guide `keep-a-session-for-each-conversation.md` changes as items 2 to 5 under "Where this spec disagrees with the overview or the guides" say, and the interrupt guide as item 6 says.

## Earlier decisions this reverses

- **Decision 5 of the archived spec on principal-scoped sessions:** a session is opened as a context manager, and closed is final. Reversed by decision 23. The same decision's rule that a session is sugar over the funnel, with no second dispatch path, stands at this spec's landing, and spec 3 amends it.
- **The same spec's landing note** that a closed session refuses as `invalid`. The refusal is gone.
- **The naming page's rule** that `session()` is not a method name, and the naming work of 2026-11-16 that renamed it `open_session`. Reversed by decision 25, for the reason that the page's own reason no longer holds.
- **Rule 1 of the retired record on sessions** speaks of a change to a session's narrowing as a subset test. It stands. A handle offers no such change at all, so the test has nothing to refuse.
- **`MANAGEMENT_METHODS` as "the router's public coroutines that manage the mount tree".** It now also names a method over the kernel's records.

## Choices for the owner

1. **The name `fs.session`.** Taken: `session(authority, id)`, with the amendment of decision 25. The alternative is `use_session(authority, id)`, which needs `use` added to the page's verbs as "the method returns a handle to a named thing and makes nothing".
2. **The name of the removal.** Taken: `session.delete()` with no argument, as the overview has it. Proposed: `fs.remove_session(authority, id)`, a management method that returns whether a session was there. The evidence is under the next heading.
3. **Anonymous callers.** Taken: an anonymous authority owns no session, and asking raises. The alternative is one owner shared by every anonymous caller, with the id as the only separation.
4. **A changed subject set.** Taken: a new owner and a new, empty session. The alternative needs a copy of a session to another owner, which is not designed.
5. **The id's alphabet.** Taken: visible ASCII. The alternative is any text without control characters, which makes a character more than one byte and brings Unicode look-alikes into a name.
6. **No lifetime that means never.** Taken: `session_lifetime` is always a positive `timedelta`. The alternative is `None` for no expiry.
7. **What the system authority's listing shows.** Taken: each row's actor and subjects in clear. The alternative is the owner key alone.

## Where this spec disagrees with the overview or the guides

1. **`session.delete()` is already the file verb.** The spec keeps the overview's name, in decision 21, and proposes `fs.remove_session(authority, id)` in its place. The evidence:
   - Run: `session.delete()` with no argument is today the file verb's refusal, `vfs.invalid`. The overview's name turns a refused mistake into the removal of a session and the cancelling of its waiting jobs.
   - Without the `NOT_GIVEN` default, `session.delete(path=None)` would remove the session too. With it, one session verb no longer has the kernel verb's signature, which a test pins per op (`tests/base/test_authority.py:274-284`).
   - The overview says each new name returns as the management methods do. `exists()` can and does. `delete()` cannot, because one method has one return type, so the two session-life methods on one handle follow two conventions.
   - Run: the removal's result prints "No changes".
   - No policy is shown the removal, though it is spelled as the verb a policy most often guards.
   - The guide uses both meanings on one object, `scout.delete("/notes/budget.md")` and `scout.delete()`.
   - A session a tool is handed could remove its caller's session, and so cancel jobs that wait for a person. A method on the file system is out of a tool's reach.
   With the proposed name, decision 21 becomes four lines, the sentinel and its test exception go, and the guide's sentence reads "`fs.remove_session(scout_is, "conv_123")` does the same at once."
2. **`fs.sessions(authority=None)` takes `after=` and `limit=` and returns a page.** The overview's signature has neither. Article 2 of the constitution requires them. The guide's sentence should read: "`fs.sessions(scout_is)` lists the sessions Scout owns, a page of 100 at a time, with each one's id, parent, number of turns and time of last use."
3. **The guide says an id is "a string of 1 to 255 characters".** It should say "1 to 255 visible ASCII characters, kept exactly as given".
4. **The guide does not say that an anonymous caller owns no session.** Its section "Who Owns a Session" should gain: "A caller with no name owns no session, and asking for one is an error. Give each caller a principal of its own."
5. **The guide's section on a chat framework does not say what a new member does.** It should gain the first two sentences of decision 9.
6. **The interrupt guide says "a session opened on it"** in its last section. Nothing is opened: "a session asked for from it".
7. **`vfs_sessions` has five columns the overview's row does not list:** `actor`, `subjects`, `parent_id`, `turn_count` and `removed_at`. The table's owner fixes its columns, so this is stated and is not a departure.

## Not checked

- **Postgres.** No statement here was run on it. Decision 15's account of two first writes, and the default that `NULL` ids are distinct in a unique constraint, rest on the engine's documented behaviour. The Postgres leg of the tests is where they are shown.
- **Spec 0.** It was not written when this was drafted. Every need under "Builds on" is stated without knowing its interfaces, its module or the cadence of its flush.
- **How SQLAlchemy renders the membership test over a pair** on each dialect. On SQLite the form `(owner_key, id) IN (VALUES (?, ?), ...)` was run by hand and returned the two rows that were there.
- **The size of a row.** It is an estimate by comparison.
- **The count of live sessions.** It is worked from the reference deployment's sessions a day, and nothing measures how many conversations keep one id.
- **How the docs export draws the default `NOT_GIVEN`** in a signature.
- **`cli` through a handle.** The probe could not run a shell line: the installed extension was older than the source and refused `host_programs`. The claims about `cli` are read from `src/vfs/session.py:414-417` and `src/vfs/sync_session.py:364-367`.
- **The other eight specs.** None was read, since they were drafted at the same moment. Each need on them is a need and not a report.

## One line

A session is a row under its owner's key and an id the host may choose, a handle to it costs nothing and is never closed, and no caller can reach a session by knowing its name.
