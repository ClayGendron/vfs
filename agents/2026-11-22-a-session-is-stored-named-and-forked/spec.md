# A session is stored under its owner and its id

A draft, written on 2026-11-22. It is not reviewed and nothing is built. It is spec 2 of the nine that `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md` maps, and it rests on that overview, on the guide `documentation/how-to/keep-a-session-for-each-conversation.md`, on the seven studies under `research/` in this directory, and on the code as read at commit `6dae6a1d`. Four probes were run that day against that tree, `spec2_probe1.py` to `spec2_probe4.py` under the session scratchpad's `specs/` directory. What each showed is written beside the claim it supports, because a scratchpad does not last. It was then revised, the same day, against the other eight drafts and the rulings of the round that reconciled them. A name another spec owns is written as that spec has it and cited by its number and heading.

## The outcome wanted

A host asks for a session with `fs.session(authority, id)`, in any process, and gets a handle to the same stored session whether or not that id was ever used. The id is a name the host chooses, or one VFS makes. The session is stored under its owner and its id together, so a caller with another authority who says the same id reaches a session of its own and never this one. Nothing is opened and nothing is closed. A session can be listed, asked whether it exists, and removed, and it expires 30 days after its last use. Specs 3, 4, 5 and 7 hang their records on the row this spec stores.

## Builds on

- **The overview, the two guides under `documentation/how-to/`, and the seven studies under `research/`: written.** The guides describe an API that is not built.
- **Spec 0, `2026-11-22-the-kernel-keeps-records-of-its-own`: drafted.** It owns the kernel store, `KernelStore`, whose whole interface is its decision 22 ("The interface is private, and this is all of it"). This spec follows that decision's eight rules, and uses these parts.
  - The table `vfs_sessions` is added to `build_kernel_tables` in `src/vfs/models/kernel_rows.py`, and the landing adds one to `KERNEL_FORMAT_VERSION` (its decision 8, "The tables are made at the store's first use, and a store of another format is refused").
  - `query` for a read and `commit` for a write, with `KernelStoreUnavailable` as the one failure (its decision 9, "The store is used through `query` and `commit`, and a failure is one exception"). A `commit` begins as a writer on SQLite. On Postgres the store runs at READ COMMITTED (its decision 5, "On Postgres the place is the mount's database and schema, on a pool of the store's own").
  - `upsert_rows`, `key_chunks`, `membership_budget` and `parameter_budget` for a statement over many rows (its decision 12, "A batch of rows is written in chunked statements through four helpers").
  - `register_behind`, `put_behind` with a `scope`, and `drain` (its decisions 13 and 16). There is no call that drops one scope's rows, so a removal drains first (decision 22 here).
  - `register_sweeper` and `sweep` (its decision 17, "Expired records are removed by a counted sweep in bounded chunks, and a record past its expiry reads as absent before it is swept").
  - `store.now()` for every time, and `store.clock` for a test (its decision 18).
  - `store.engine` for a test's statement listener.
  - On SQLite the store is a file of its own in WAL (its decision 4), so a `query` does not wait on the store's writer.
- **Spec 3, the stamps: drafted.** It makes the row through `resolve` (decision 14 here). Its bare line is a session that is never stored (its decision 16, "A bare line is a strict session of its own, and it is never stored"), which is what a caller that owns no session gets. One need of this spec is not met yet, and is listed under "Needs no other spec meets yet".
- **Spec 4, turns, rewind and fork: drafted.** Taken: `turn_counter`, which its `start_turn` adds to (its decision 4, "`start_turn` stores the turn at once, takes its number from the session's counter, and returns the turn id"); `remove_turns` (its decision 2, "`vfs_session_turns` holds one row per turn"); a fork that copies its rows and reads nothing through its parent (its decisions 17 and 19); `fork(id)` refused with `vfs.exists` when the owner has the id (its decision 16); a record that names a turn with no row is dead (its decision 8, "A removed turn's number is never used again, and a record that names it is dead"); and the `turn` and `parent` properties it adds to the handle (its decisions 6 and 19). Decision 27 here gives it the function its fork needs.
- **Spec 5, the change records: drafted.** Taken: `remove_changes(session, session_key, limit) -> int` (its decision 16, "A rewind of the memory alone removes no change row, and a fork copies none"), which joins `SESSION_CHILDREN`.
- **Spec 6, policies: drafted.** Taken: `Policy`, `PolicySet` and `decisions.with_policies` (its decision 17, "A session's policies are asked after the file system's and can only add"), and the `TypeError` for an item that is no policy (its decision 9).
- **Spec 7, jobs: drafted.** Taken: `vfs_jobs.session_key` (its decision 4); `cancel_session_jobs(store, session_key, *, from_turn=None, reason)` (its decision 35, "A session's delete, its expiry and a rewind cancel its waiting jobs through one call, and a fork takes none"); and `Principal.name` (its decision 28), which the owner key does not read. It uses `owner_key` for every caller, the anonymous one included (its decision 7).
- **Specs 1 and 8: drafted.** Nothing is taken from either, and neither asks anything of this spec.
- **`context/specifications/archive/070-principal-scoped-sessions/spec.md`: landed 2026-09-06.** Its decision 4 stands. Its decision 5 is reversed in part (see "Earlier decisions this reverses").
- **The retired record `context/decisions/063-a-session-never-widens-itself.md`,** read with `git show 3667fec2^:context/decisions/063-a-session-never-widens-itself.md`. Its rules 1, 2 and 4 bind and are kept by decisions 4 and 5.
- **`documentation/maintainers/how-we-name.md`: published.** Decision 25 amends it.

## Terms

- **Session.** VFS's side of one conversation: who the agent is, what it has been shown, and where its shell is. It is a stored record.
- **Handle.** The Python object `fs.session(...)` returns. It names a session and holds nothing the store does not.
- **Owner.** The actor and the subjects of the authority a session is asked for with.
- **Owner key.** 64 hexadecimal characters derived from the owner. It is the first half of a session's stored name.
- **Id.** The second half of the name. The host chooses it or VFS makes it.
- **Session key.** The integer the kernel store hands out for a session row, the column `session_key`. Every other table names a session by it. It is never handed out twice.
- **Kernel store.** Where the kernel keeps its own records: spec 0's `KernelStore`.
- **Written behind.** Put in the store's buffer by `put_behind` and written a moment after the call returns, never during it.
- **Scope.** The value a session's rows are put behind under, so that `drain` can wait for them alone. It is the pair of the owner key and the id.
- **Resolve.** To find a session's row by its owner key and id, and to make it when the caller has something to store.
- **Use.** One call made through a handle. It is what keeps a session from expiring.
- **Removal.** The end of a session: by `fs.remove_session`, or by expiry.
- **Marker.** A removed session's row after its name is cleared, kept until the rows that hang on it are gone.
- **Host.** The application code that holds the file system object. An agent never holds it.

## What the code does today

Read at `6dae6a1d`. "Run" means one of the four probes.

| Fact | How it is known |
|---|---|
| A session is made by `open_session(authority)`, which builds a new object each time and takes no id. | Read, `src/vfs/base.py:655-663`, `src/vfs/sync.py:256-258`. |
| The object holds three values: the file system, the authority and a closed flag. | Read, `src/vfs/session.py:61-66`. Run: `__slots__` is `('_authority', '_closed', '_fs')`. |
| Two `open_session` calls issue 0 statements and return two objects. Nothing about a session is stored anywhere. | Run. |
| A warm `read` through a session issues the 3 statements the direct call issues. | Run. |
| A session is an `async` context manager. `close()` sets the flag, and a closed session never reopens. Entering a closed one raises `ValueError`. | Read, `src/vfs/session.py:76-93`, `:462-464`. |
| Each of the 26 public methods of a session, the 25 ops and `cli`, begins with a check of the flag, and a closed session answers `vfs.invalid` with "the session is closed and cannot reopen; open a new one". | Read, `src/vfs/session.py:42-49`, `:466-468`; 26 call sites counted. Run. |
| The synchronous `Session` wraps an `AsyncSession` and repeats the lifecycle: `closed`, `close`, `__enter__`, `__exit__`, and the flag checked before each hop. | Read, `src/vfs/sync_session.py:45-74`, `:364-366`, `:395-399`. |
| A verb through an open session on a closed file system answers `vfs.unavailable.backend`, "the filesystem is closed", on both faces. | Run. Read, `src/vfs/base.py:3069-3071`, `src/vfs/sync.py:691-698`. |
| A line through a session runs: `echo $((6 * 7))` prints `42`. After the kernel is closed, `echo hi` through the same session still succeeds on the kernel, since the line calls no verb. On the synchronous face it is refused `vfs.unavailable.backend` with exit status 2. | Run. |
| The public names of a session are the 25 ops and `authority`, `cli`, `close`, `closed`. A test pins exactly that set and the return annotations. | Run. Read, `tests/base/test_authority.py:311-320`. |
| A session verb has the kernel verb's signature without `authority`, pinned per op. | Read, `tests/base/test_authority.py:274-284`. |
| `session.delete()` with no argument is the file verb, and is refused `vfs.invalid`: "Exactly one of path or observations must be provided". `fs.delete()` answers the same. | Run. |
| A verb returns a `Result` and never raises for a refusal. A management method returns a typed value and raises: `mounts()` returns a tuple of `Mount`; `add_mount` raises `MountError`, which carries a `Result`; `locate` raises `ValueError` on a closed kernel; the synchronous face raises `RuntimeError` after `close()`. | Read, `src/vfs/ops.py:110-113`, `src/vfs/base.py:581`, `:778`, `:2675`, `src/vfs/exceptions.py:36-46`, `src/vfs/sync.py:72`, `:709-714`. |
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
| Ruff's rule `A` is on, and no ignore list for builtins is set. | Read, `pyproject.toml:106-116`. Spec 4 ran `def start_turn(id: ...)` under it and it failed `A002`. |

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
    policies: Iterable[Policy] = (),
) -> AsyncSession: ...
```

It is a plain method on both faces, never a coroutine, as `mounts()` is. `VirtualFileSystem.session` has the same parameters and returns a `Session`, with no hop to the loop thread. It issues no statement, awaits nothing, and stores nothing.

- `authority=None` is resolved once, here, by `caller_for(authority, default_authority, op="session")`: the kernel's `default_authority`, or else the anonymous authority, which decision 7 refuses.
- `id=None` makes an id here, by decision 11.
- A value of the wrong type raises `TypeError`: "authority must be an Authority, got <type>", "a session id is a str, got <type>", "strict must be a bool, got <type>". An item of `policies` that is no policy raises spec 6's `TypeError` (its decision 9).
- An unlawful id (decision 10) and an anonymous authority (decision 7) raise `ValidationError`, which carries a `Result` with one fact of the kind `vfs.invalid`, as `MountError` carries one.

A refusal here is raised, not returned, because the call returns a handle and has no `Result` to give back. Every one of these is a mistake in the host's code, as a bad `Principal` is.

Reason: ruling 10 of the overview. A handle that costs nothing can be asked for at the top of every request.

### 3. The handle holds seven values, and only its current turn ever changes

| Slot | Public as | What it is |
|---|---|---|
| `_fs` | nothing | the kernel |
| `_authority` | `authority` | the authority every call is made as |
| `_id` | `id` | the id, as given or as made |
| `_ref` | nothing | the owner key, the id, and the actor and subject names, worked out once |
| `_strict` | `strict` | decision 4 |
| `_policies` | `policies` | decision 4 |
| `_turn` | `turn` | the current turn, which spec 4 adds and its `start_turn` sets (its decision 6, "The turn is on the handle, and the store holds no current turn") |

- The classes keep their names: `AsyncSession` on the kernel and `Session` on the synchronous face, exported from `vfs`. The guides already use both.
- No method replaces `authority`, `id`, `strict` or `policies`. A host that wants other values asks for another handle.
- Two handles for one session are two objects. A handle compares and hashes by identity, because its turn can change.
- A handle cannot be pickled or sent to another process. What crosses a process boundary is the authority and the id.
- Several calls may run at once through one handle. The handle is read by them and written by none.
- The handle carries every op and `cli`, and nothing that reaches a mount, the kernel or the kernel store. The test that pins this stays, with the new set of names.
- On a handle, `delete` is the file verb and nothing else (decision 21).

Reason: a handle that holds nothing the store does not can be dropped at any moment, and two processes can never disagree about a session because of what one of them remembers.

### 4. `strict` and `policies` belong to the handle and are never stored

`strict` is read by spec 3 and `policies` by spec 6. This spec carries them. Each call is judged by the values of the handle it came through.

- Nothing about either is written to `vfs_sessions`. A policy is a function and cannot be stored, by ruling 2 of the overview. A stored `strict` would make two handles with different values a conflict that some rule must settle, and there is no such conflict when each handle answers for itself.
- The handle builds a `PolicySet` from what it was given, once, through spec 6's constructor, and keeps it. That constructor raises the `TypeError` and the `ValueError` of spec 6's decisions 9 and 17. Each verb the handle forwards runs inside `decisions.with_policies(that_set)`. A handle given none enters nothing. The one line in each verb lands with whichever of the two specs is built second.
- `session.policies` returns the set's policies as a tuple, in order, as `fs.policies()` does for the file system's.
- A session's policies are added to the file system's and can only ask for more review. The handle offers no way to take one away.
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

It lives in `src/vfs/authority.py`, beside `owner_for`. It answers for every authority, the anonymous one included, because spec 7 keys a job by it whoever made the call (its decision 7, "The owner of a job is the authority that made the call, and a job made through a session records its session and its turn"). That an anonymous caller owns no session is `fs.session`'s refusal, in decision 7 here, and not this function's. The column type of an owner key, in any table, is `BytewiseString(64)`.

- **Encoding.** A JSON array of three items: the domain string, the actor's `sub`, and the subjects' distinct `sub` values in sorted order. JSON quotes and escapes each name, so no two different owners produce the same text. A separator character joined between names would not have that property, and one studied project has an open bug from exactly that (`research/framework-session-stores.md`, section 1). Run: actor `a:b` for subject `c` and actor `a` for subject `b:c` give different keys.
- **`ensure_ascii=True`.** The text is ASCII whatever the names hold, so a name with a lone surrogate still encodes. Run.
- **Length.** 64 lowercase hexadecimal characters, always. Run. A subject set may hold 64 names of any length, and a hash is what keeps the key inside an index.
- **Not secret.** Anyone who knows the names can work the key out. It is never accepted from a caller. It is only ever computed from an `Authority`.
- **What is in it.** The actor's `sub` and each subject's `sub`, and nothing else.
- **What is not.** A principal's `kind` and `scopes`: rights are granted to a `sub`, and a token renewed with other scopes is the same caller. Run: both are ignored. A principal's `name`, which spec 7 adds for display (its decision 28). `provenance` and `source_identity`: the same caller proven at the edge or built in process is one owner. `narrowing`: it limits what a call may do, which decision 5 judges on each call, and does not change whose session it is.

Narrowing has one value today. When it gains a second, a narrowed authority keeps its owner key. The session's shell state can then pass from a wider handle to a narrower one of the same owner, so a host that narrows an authority for a part of its work gives that part an id of its own.

| Authority | Owner |
|---|---|
| a person acting as itself | its own, apart from every agent's |
| an agent acting for one person | that pair |
| the same agent acting for another person | another owner |
| an agent acting for a set | that agent and that exact set, in any order |
| the system authority | one owner, decision 8 |
| the anonymous authority | one key, which names jobs and never a session, decision 7 |

Reason: the overview's ownership rule. One studied server adds a digest of the user to an id its clients make, and that is what makes a client-made id safe (`research/history.md`, lineage 3). Another puts the user in the key beside the id (`research/framework-session-stores.md`, section 1).

### 7. An anonymous authority owns no session

`fs.session(Authority.anonymous(), ...)` raises `ValidationError` with the kind `vfs.invalid` and the detail "an anonymous caller owns no session; pass an authority that names the caller". So does `fs.session()` on a kernel with no `default_authority`. `fs.sessions` called as the anonymous authority returns an empty page, and `fs.remove_session` returns `False`, and neither issues a statement.

Every anonymous caller is one principal, `anon`. If it owned sessions, every anonymous caller would be one owner, and the id would be the only thing between two of them. The id would then be a credential, which the overview rules it never is. One caller could read another's shell variables, cancel its waiting jobs, or prepare an id for it to walk into.

A host with callers it cannot name gives each a principal of its own, or works without a session, which the guide allows. A shell line run by an anonymous caller is still guarded for its own length: spec 3's bare line is a session that is never stored (its decision 16), and it asks nothing of this spec.

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
- A job the old session left waiting is not listed by the new session. It is still answered through spec 7's `fs.resume(job_id, ...)`.
- The old session stays, reachable only with the old authority, and expires 30 days after its last use.

Why this is right, and not only tolerable: the rights of a set are the least of its members' rights. When a subject joins, the set may see less than it did. The old session holds what was shown under the old rights, in its stamps and in its shell variables. Carrying it over would put that in front of a conversation that now includes someone who may not see it. The same rule the other way costs only a few reads.

What to do instead, where a host wants one memory across the change: nothing in these nine specs copies a session to another owner. Spec 4's fork keeps the owner of its source (its decision 16). The copy is named under "Left as it is" with the facts a later spec needs.

Reason: the owner is the whole authority, by the overview and by the guide's own example of one agent working for two people.

### 10. An id is 1 to 255 visible ASCII characters, kept exactly as given

- **Characters.** Each is in the range `0x21` to `0x7E`. No space, no control character, nothing outside ASCII. This is the rule one wire protocol set for its own session ids (`research/wire-protocol-sessions.md`, section 1), and it holds every id form the guide's table names.
- **Length.** 1 to 255, the overview's default, as `SESSION_ID_MAX: Final = 255`. A character is one byte, so 255 characters is 255 bytes on both engines.
- **No normalisation.** The id is stored and compared byte for byte. `Conv_1` and `conv_1` are two sessions. Nothing is trimmed, folded or coerced.
- **A `str` only.** An integer, a `UUID` object or `bytes` raises `TypeError`. Coercing with `str()` would make `123` and `"123"` one session without the host having said so.
- **The refusal.** `check_session_id(id)` raises `ValidationError` with the kind `vfs.invalid` and the detail "a session id is 1 to 255 visible ASCII characters", followed by the length, or by the first character outside the range as `repr` prints it. `fs.session`, `fs.remove_session` and spec 4's `fork` all refuse through it.
- **An id is only ever a bind parameter.** It is never joined into a path, a table name or the text of a statement.

Run: `conv_123`, a UUID and `user:42/conv:7` pass; the empty string, 256 characters, a space, a newline and `café` are refused.

Reason: a name the host's browser may have made must be safe to carry anywhere, and one byte order on both engines keeps a listing in one order.

### 11. A generated id is `ses_` and 26 characters from 128 random bits

```python
def new_session_id() -> str:
    return "ses_" + base64.b32encode(secrets.token_bytes(16)).decode("ascii").rstrip("=").lower()
```

30 characters, from the operating system's secure generator. Run: 100,000 made, 100,000 distinct, all lawful under decision 10. Its uniqueness rests on the 128 bits and on no clock, so two processes that make ids in the same microsecond do not meet. A collision would name a session of the same owner and never another's, because the owner key is the other half of the name.

The prefix reserves nothing. A host may supply an id that begins `ses_`. Spec 4's `fork` with no id takes its id from this function.

Reason: three studied projects had defects from a time inside an id or a name (`research/framework-session-stores.md`, lesson 3). The id is unguessable because it costs nothing to make it so, and not because anything rests on its being secret.

### 12. The same call returns the same session whether or not it exists, and no call asks to create one

There is no create and no open. `fs.session(authority, id)` is both, by ruling 10. A host that must know asks `exists()`.

The studies advise two separate verbs with a conflict rule (`research/langgraph-threads.md`, lesson 1; `research/history.md`, lineage 6). That advice answers two problems, and neither is left here. The first is another caller's id, which decision 6 closes: a session made for an id it is shown is made inside the caller's own owner, and no one else can reach it. The second is a mismatch between the parameters of the first call and a later one. A session has no such parameters, because decision 4 stores none.

One call does refuse an id that exists: a fork, which copies a history into the id (spec 4, decision 16). Decision 27 gives it the insert that refuses.

Reason: with an owner in the key and nothing to compare, the two verbs would differ only in an error a host would have to handle on every request.

### 13. `vfs_sessions` holds one row per session, under a key that is never used twice

| Column | Type | Holds |
|---|---|---|
| `session_key` | `BigInteger`, `Integer` on SQLite; identity; primary key | Handed out by the engine and never reused: `AUTOINCREMENT` on SQLite, an identity column on Postgres, as `vfs_entries` does (`src/vfs/models/rows.py:370`, `:451`) |
| `owner_key` | `BytewiseString(64)`, not null | decision 6 |
| `id` | `BytewiseString(255)`, null | decision 10; `NULL` once the session is removed |
| `actor` | text, not null | the actor's `sub`, for a listing |
| `subjects` | text, not null | the subjects' distinct `sub` values, sorted, as a JSON array |
| `parent_id` | `BytewiseString(255)`, null | the id of the session this one was forked from; spec 4, decision 19 |
| `fork_before` | `BytewiseString(1020)`, null | the turn id the fork was given as `before`; 1,020 is spec 4's `MAX_TURN_ID_BYTES` |
| `fork_number` | `BigInteger`, null | the fork point, a turn number; null for a session that is no fork |
| `turn_counter` | `BigInteger`, not null, default 0 | the last turn number handed out; spec 4's `start_turn` adds to it |
| `created_at` | timestamp with zone, not null | for display |
| `last_used_at` | timestamp with zone, not null | decision 17 |
| `expires_at` | timestamp with zone, not null | decision 18 |
| `removed_at` | timestamp with zone, null | set when the session is removed; decision 22 |

Indexes: a unique constraint `uq_vfs_sessions_name` on `(owner_key, id)`; `ix_vfs_sessions_expires_at` on `expires_at`; and `ix_vfs_sessions_removed_at` on `removed_at`, partial where it is not null. The table is declared in `build_kernel_tables`. It has no foreign key, as no table in the tree has one.

- **The key is never reused.** A row written behind for a removed session must never land on another session. Run on SQLite 3.50.4: the row with the highest key was deleted, and the next row took a higher key.
- **Both engines treat `NULL` ids as distinct** in the unique constraint, so any number of markers share an owner. Run on SQLite. On Postgres it is the documented default and was not run.
- **The three lineage columns are spec 4's to fill,** through decision 27. They are a record of where a session came from, and nothing reads through them. `parent_id` may name an id that has since been used for a new session, as spec 4's decision 19 says.
- **A turn number is the fork point,** because a turn's id can be used again after a rewind and its number cannot.
- **`turn_counter` is a counter in spec 0's sense** (its decision 11, "A counter is a column that one statement adds to and returns"). It is not the number of turns: a rewind removes turns and never lowers it.
- **`actor` and `subjects` are unindexed text,** so a long name fails no length check.
- The table holds four columns the overview's row for it does not list: `actor`, `subjects`, `fork_before` and `removed_at`.

Reason: an order is a counter and never a clock, by the overview, and a name that can be freed needs an identity that cannot.

### 14. The row is first written by the first record that needs it, through one function, `resolve`

Asking for a handle stores nothing. The row is made when some spec has a record to store for the session: a stamp, a turn, a change record, a job. Each of them calls one function, inside the `commit` that writes its own rows.

```python
class SessionRef(NamedTuple):
    owner_key: str
    id: str
    actor: str
    subjects: tuple[str, ...]

    @property
    def scope(self) -> tuple[str, str]: ...        # (owner_key, id), the scope of decision 17

async def resolve(
    store: KernelStore, session: AsyncSession, refs: Sequence[SessionRef], *, create: bool, lifetime: timedelta
) -> dict[tuple[str, str], int]: ...

async def find(store: KernelStore, session: AsyncSession, ref: SessionRef) -> int | None: ...
```

Here `session` is the SQLAlchemy session that `store.commit` or `store.query` hands its function. `resolve` returns each session's key by `(owner_key, id)`. A session with no row is left out of the answer when `create` is false, and gets a row when it is true. `resolve` may write, so it runs inside a `commit`. `find` is one `SELECT` that writes nothing, for a `query`: it returns the key of a row that has not expired, or `None`.

The steps of `resolve`, with `refs` made distinct first and `now` read once from `store.now()`:

1. **Read.** One `SELECT session_key, last_used_at, expires_at` by membership of the pair `(owner_key, id)`. The refs are cut at half of `store.membership_budget`, since a pair is two binds.
2. **Replace what expired.** A row whose `expires_at` is at or before `now` is removed by decision 22's first step when `create` is true, and is then absent. When `create` is false it is treated as absent and left for the sweep.
3. **Create.** With `create` true, `store.upsert_rows(session, sessions, rows, key=("owner_key", "id"), update=())` for the absent. An empty `update` makes it `ON CONFLICT DO NOTHING`, and the helper cuts the rows under the parameter budget at seven values a row.
4. **Read again** the refs step 3 was given, which holds the rows it made and the rows a rival made first (decision 15).
5. **Touch.** One `UPDATE` of `last_used_at` and `expires_at` for the rows decision 17 finds due, by `session_key`, cut by `store.key_chunks`.

| Case | Statements |
|---|---|
| the row is there and was used in the last five minutes | 1 |
| the row is there and a touch is due | 2 |
| the row is absent and `create` is false | 1 |
| the first write, won or lost to a rival | 3 |
| the row has expired and `create` is true | 5: the read, the mark, spec 7's cancel, the insert and the second read |

The read comes first because the common case is a row that is there. It also spends no key: an insert that does nothing still takes a number from the engine. Run on SQLite: seven inserts that did nothing moved the next key from 3 to 10.

Who calls it:

| Spec | For | Call |
|---|---|---|
| 3 | a stamp written behind, in its kind's `write`; the stamps a change leaves, at step 7 of its decision 8 ("A read writes its stamps behind, and a change writes them with the change") | `resolve(create=True)` |
| 3 | the stamps it reads before a change, at step 2 of that decision | `find`; no row means no stamp |
| 4 | `start_turn`, at S2 of its decision 4, and `make_first_turn` | `resolve(create=True)` |
| 4 | `rewind` and `turns` | `find` |
| 4 | `fork` | `find` for the source, and decision 27's `make_fork` for the new row |
| 5 | its change rows, inside `store.record_after` (its decision 4, "A session writes its change rows after the change commits, by spec 0's record-after form, before the verb returns") | `resolve(create=True)` |
| 7 | a job stored for a call made through a handle (its decision 7) | `resolve(create=True)` |
| 7 | `session.jobs` and `session.resume` (its decision 32) | `find`; no row means no job |
| this spec | a use, in its kind's `write` (decision 17) | `resolve(create=False)` |

Reason: one seam for four kinds of record means one place where a session comes to exist, and one statement in the common case.

### 15. Two first writes at the same moment end as one row, on both engines

Two processes resolve one new session at once. Both read and find nothing. Both insert.

- **Postgres, at READ COMMITTED.** The second insert meets the first's uncommitted entry in the unique index and waits for that transaction. When it commits, the second inserts nothing, and its read in step 4 is a new statement with a new snapshot, which sees the committed row. When the first rolls back, the second inserts. Either way one row exists and both hold its key. Neither sees an integrity error. This rests on the engine's documented behaviour and was not run.
- **SQLite.** The kernel store has one writer, and a `commit` begins as one. The second transaction begins after the first commits, its insert does nothing, and step 4 reads the row. Run: 8 threads on 8 connections resolved one new session at once, and the table held 1 row and every thread held key 1.
- **A kernel store in memory.** It belongs to one process. Two tasks meet as two SQLite transactions do.

A transaction at a snapshot level on Postgres would not see the rival's row in step 4. Spec 0's store runs at READ COMMITTED with no pin, for the same reason its counter needs. If step 4 ever finds no row, `resolve` raises, and it never guesses a key.

Reason: the unique constraint is the arbiter, as it is for two creates of one path, and a check in Python alone is the race the studies found most often (`research/framework-session-stores.md`, lesson 2).

### 16. A handle keeps no copy of the row, so every record names its session by owner and id

A handle does not remember its `session_key`. Each `commit` that stores something resolves the key again, and each `query` finds it again.

The other design was costed. A handle that kept the key would save one statement on a write. But a session can be removed by another process. The handle would then go on writing under a key whose row is gone, and reading its own orphans back, as a second session under the same id that no other handle can see. With no copy, the next record after a removal resolves, finds no row, and makes the new session that every handle then shares.

Reason: the overview's rule that the handle holds no state the store does not, taken literally, at the price of one read by a unique index.

### 17. Every call through a handle reports one use, written behind, and a row is touched at most once in five minutes

```python
SESSION_USE: Final = BehindKind(name="session_use", write=write_uses, key=("owner_key", "id"))

store.put_behind(SESSION_USE, [{"owner_key": ..., "id": ..., "actor": ..., "subjects": ...}], scope=ref.scope)
```

When a call through a handle returns, the handle puts one row of this kind behind. `put_behind` is a plain function that sends nothing and waits for nothing. The kind is keyed by the session's name, so the buffer holds one use per session however many calls it made.

- **The kind's `write`** is `resolve(create=False)` over the rows of one flush. So **a use alone never makes a row**. A session that has stored nothing has nothing to expire.
- **The kernel registers the kind when it is built,** with its `session_lifetime` bound into `write`, and before any kind of another spec, since kinds are written in the order they were registered.
- **The scope** is `ref.scope`. Spec 3 puts a session's stamps behind under the same scope, so one `drain(ref.scope)` waits for everything of one session.
- **This kind is only ever written behind.** A use that is dropped errs toward an earlier expiry of a session nobody then used, which is spec 0's test for a record that may be dropped (its decision 14).

A touch is due when the stored `last_used_at` is more than `SESSION_TOUCH_SLACK: Final = timedelta(minutes=5)` before `now`. The age is read from the row in step 1 of `resolve`, so no process keeps a table of what it touched. The touch sets `last_used_at = now` and `expires_at = now + lifetime + SESSION_TOUCH_SLACK`.

- A `resolve` with `create` true, such as a turn being started, touches by the same rule.
- `exists()`, `fs.sessions`, `find` and the sweep are not uses. Asking whether a session exists does not keep it alive.
- `last_used_at` may be up to five minutes behind the true last use. It is for display and for expiry, and is never an order.

Reason: the overview's bar that a read adds no synchronous statement, which spec 0 holds by making `put_behind` a read verb's whole dealing with the store. The slack bounds the updates of one row to 12 an hour however many calls a session makes.

### 18. A session expires 30 days after its last use, and is gone from that moment

`AsyncVirtualFileSystem(session_lifetime=timedelta(days=30))`, and the same on `VirtualFileSystem`. The value is a `timedelta` greater than zero. Anything else raises `ValueError` from the constructor, as a bad `deny_ops` does: "session_lifetime must be a timedelta greater than zero". There is no value that means never.

- **Never early.** The stored `expires_at` carries the slack of decision 17, so it is never before the true last use plus the lifetime. A new row is given the `expires_at` a touch would give it.
- **Exact in effect.** Every read of the table treats a row whose `expires_at` has passed as absent, as spec 0 requires of every table that expires: `exists()` is false, a listing leaves it out, `find` returns `None`, and `resolve` replaces it. A session used on day 31 is a new and empty one whether or not the sweep has run.
- **The sweep only reclaims.** It removes what has expired, by decision 22.
- **The lifetime in force is the one of the process that last touched the row.** A host that changes it sees the new value on each session's next touch.
- **Every time is `store.now()`.** Two processes whose clocks differ by seconds differ by seconds in a 30-day lifetime.

Reason: every mature system the studies read has a retention rule, and the one that went two years without one had to add it (`research/langgraph-threads.md`, section 7). An idle lifetime with no absolute one is enough, because the id grants nothing.

### 19. `session.exists()` reads one row and is not a use

```python
async def exists(self) -> bool: ...
```

It first awaits `store.drain(ref.scope)`, so that what this process has put behind for the session is written. Then it runs `find` in one `store.query`. It returns `True` when the session has stored anything.

- Within one process the answer is exact, because of the drain. A read made in another process a moment ago may not be stored yet.
- It raises as decision 28 says.
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
    parent: str | None          # parent_id
    fork_before: str | None
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
- One statement a page, in one `store.query`, with `LIMIT limit + 1`. The extra row says whether there is more and is not returned.
- `after` is a value a page returned. One that is not a lawful id, or for the system authority not a decimal integer, is refused with `vfs.invalid`.
- A listing leaves out markers and expired rows.
- **`turns` counts the rows of `vfs_session_turns`,** as spec 4 asks, by one scalar subquery in the same statement: `(SELECT count(*) FROM vfs_session_turns t WHERE t.session_key = s.session_key)`. It is a range of that table's primary key for each row of the page. Until that table exists `turns` is 0, and the subquery joins the statement in the landing that makes the table.
- It is a management method: it joins `MANAGEMENT_METHODS`, and returns and raises as decision 28 says.
- Another owner's sessions are never in a named caller's page, in any order, by any `after`.

The order by `id` is the unique index's own, so a page is a range read and stays stable while sessions are touched. An order by last use would need an index every touch rewrites, and rows would move between two pages.

Reason: article 2 of the constitution requires every listing to be bounded with a cursor. Spec 7's `jobs` pages the same way (its decision 31).

### 21. `fs.remove_session(authority, id)` removes a session, and `delete` on a handle is the file verb and nothing else

The first draft of this decision kept the overview's `session.delete()` and made the bare call mean removal. The reconciling round ruled otherwise, and this is what the decision now says.

```python
async def remove_session(self, authority: Authority | None, id: str) -> bool: ...
```

- It returns `True` when a session was there and is now removed, and `False` when there was none. Removing a session that never stored anything, or was already removed, is `False` and no error.
- `authority=None` is the `default_authority`, or else anonymous. The anonymous authority owns no session, so the answer is `False` with no statement.
- `id` is required and is checked by decision 10.
- It is a management method on both faces: it joins `MANAGEMENT_METHODS`, and returns and raises as decision 28 says. It is not a step, and no policy is asked about it. It is host code's call.
- A handle has no way to remove its session. An agent's tool holds a handle and never the file system, so no tool can remove a session or cancel the jobs that wait in it.
- `AsyncSession.delete` and `Session.delete` keep the kernel verb's signature and meaning, unchanged. `session.delete()` with no argument stays the verb's refusal, `vfs.invalid`. Run.
- What it does is decision 22.

Reason: on a handle that carries every file verb, a second meaning for `delete` would turn a refused mistake into the loss of a session and the cancelling of its waiting jobs. `remove` is the naming page's verb for a thing that leaves a collection the file system keeps, and `fs.sessions()` is that collection.

### 22. Removal frees the id in one commit and reclaims the rest in bounded chunks

A removal is `fs.remove_session`, or an expiry met by `resolve` or by the sweep. It has two steps.

**Step 1, one `commit`.** Find the row. `UPDATE vfs_sessions SET id = NULL, removed_at = :now WHERE session_key = :k AND removed_at IS NULL`. Then, in the same transaction, spec 7's `cancel_session_jobs(session, session_key, reason=...)`, with the reason "the session was deleted" or "the session expired", the two its decision 35 lists.

From that commit the name is free. `exists()` is false, the session is in no listing, and the next record for that owner and id makes a new row with a new key. The old row is a marker.

**Step 2, bounded chunks.** For the marker's key, each function in `SESSION_CHILDREN` deletes its rows, at most `SESSION_RECLAIM_CHUNK: Final = 5_000` to a `commit`, until it returns fewer than it was asked for. Then spec 4's `remove_turns(session, [session_key])` removes the session's turns in one ranged statement, last, because a stamp and a change row name a turn. Then the marker itself is deleted.

What each spec's records end by:

| Spec | Rows | Call | Step |
|---|---|---|---|
| 7 | the session's waiting jobs in `vfs_jobs` | `cancel_session_jobs(session, session_key, reason=...)`, its decision 35 | 1 |
| 3 | `vfs_session_stamps` | a function of the shape `(session, session_key, limit) -> int`, which it has not named yet; see "Needs no other spec meets yet" | 2, in `SESSION_CHILDREN` |
| 5 | `vfs_session_changes` | `remove_changes(session, session_key, limit) -> int`, its decision 16 | 2, in `SESSION_CHILDREN` |
| 4 | `vfs_session_turns` | `remove_turns(session, [session_key])`, its decision 2 | 2, after the children |
| 8 | `vfs_job_replies` | none of this spec's; a journal goes with its job | |

`SESSION_CHILDREN` is one tuple the kernel holds. It is empty at this spec's landing, and each of specs 3 and 5 adds its function in its own landing.

- **`fs.remove_session` runs both steps.** Before step 1 it awaits `store.drain(ref.scope)`, so that what this process has put behind for the session is written and then removed with the rest. If step 2 fails or the call is cancelled, the removal has still happened, the answer is still `True`, one `WARNING` is logged on `vfs.kernel_store`, and the sweep finishes the work.
- **`resolve` runs step 1 only,** for a row it finds expired, and leaves step 2 to the sweep. A call that happens to arrive on day 31 does not pay for the reclaim.
- **The sweep** is one sweeper, `store.register_sweeper("sessions", sweep_sessions)`, of spec 0's shape: it is handed the store, a session, the pass's `now` and a `limit`, and it works in the one `commit` it is given. It first reads up to `SESSION_SWEEP_BATCH: Final = 100` keys whose `expires_at` has passed, by the index, and runs step 1 for them. It then reads markers by their index, oldest key first, and runs step 2 for each until it has removed `limit` rows. It returns the rows it removed, child rows and markers together. A marker is deleted only when its dependents are gone, which is spec 0's rule for a parent.
- **A crash between the steps loses nothing.** The marker is in the store, and its index is how the sweep finds it. No pass scans the table.

What goes with a session, and what does not:

| Thing | On removal |
|---|---|
| its turns, its stamps, its change records | deleted, in step 2 |
| its waiting jobs | cancelled, in step 1; a later `resume` of one returns "Cancelled by the system", with the reason, as spec 7 has it |
| a job being carried out at that moment | finishes; what it would have had the session remember stores nothing (spec 7, decision 34) |
| its finished jobs | left to spec 7's own lifetime |
| its forks | not deleted and not changed; each has rows of its own, and its `parent_id` still shows the name |
| the files it changed | untouched |
| its id | free at once; used again, it is a new and empty session with a new key and a new `created_at` |

No name is kept reserved after a removal. One studied project reserves every branch name for ever (`research/framework-session-stores.md`, section 4). There the name was the only identity. Here the key is, and the owner who removed a session is the only caller who can ever say its name again.

**A late record.** A read in another process may have a stamp in that process's buffer when the session is removed. Its flush resolves by owner and id, finds no row, and makes the row again. This is the ruling spec 3 asks for. Whether the stamp is then stored is spec 3's and spec 4's rule: a stamp whose turn has no row stores nothing (spec 4, decision 8), and a stamp from a handle with no turn is filed under a first turn made for it. Either way the new session holds at most what that one read saw, and it authorizes nothing: a stamp is checked against the file when a change is made. Within one process the drain makes a removal exact.

Reason: a removal that waits for every row holds a writer for as long as the session was long. Freeing the name in one commit is what the caller asked for, and the chunk size is spec 0's `SWEEP_CHUNK`, which the log cost study measured at 21 ms on SQLite and 67 ms on Postgres at the median.

### 23. `open_session`, `close`, the context manager and the closed refusals are removed, and nothing replaces them

Removed from `AsyncSession`: `closed`, `close`, `__aenter__`, `__aexit__`, `_close_now`, `_refuse_closed`, its 26 call sites, `CLOSED_SESSION_DETAIL` and `closed_refusal`. Removed from `Session`: `closed`, `close`, `__enter__`, `__exit__` and the three checks of the flag. Removed from both file systems: `open_session`.

No alias is kept, by ruling 15. `fs.session(authority)` with no id is what `fs.open_session(authority)` was: a handle whose verbs carry the authority.

Reason: a session holds no resource of the process, so there was nothing to close. Two wire protocols learned that a session tied to an object's or a connection's life ends whenever a stateless handler returns (`research/wire-protocol-sessions.md`, lesson 1).

### 24. After its file system is closed, a handle answers as the file system does

| Call | On a closed file system |
|---|---|
| `fs.session(...)` | returns a handle; it reads no state |
| a verb through a handle | the kernel's own refusal, `vfs.unavailable.backend`, "the filesystem is closed" |
| `cli` through a handle | whatever `fs.cli` answers on that face. Run: on the kernel a line that calls no verb still runs, and on the synchronous face the line is refused `vfs.unavailable.backend` |
| `session.exists()`, `fs.sessions(...)`, `fs.remove_session(...)` | raises `VFSError` with spec 0's fact for a closed store, `vfs.unavailable.backend`, "the filesystem is closed"; on the synchronous face the management hop raises `RuntimeError` first, as it does today |

The handle has no closed state of its own. Closing the file system removes no session. A session in a durable store is there for the next process. A session of an in-memory store is gone with it, as spec 0's decision 19 says.

Reason: one closed fact, the kernel's, in place of two.

### 25. `documentation/maintainers/how-we-name.md` gains one exception, for `session()`

The page forbade `session()` because the name hid that the thing had to be closed. Nothing is made by the call any more and nothing has to be closed. The amendment, exactly:

Under "Nouns", the second item becomes:

> - **A noun is never a method name by itself, with one exception.** A method called `posture()` does not say whether it reads the posture or sets it. The exception is a method that takes the key of one thing and returns a handle to it, and does nothing else: it stores nothing, reads nothing, and returns nothing that must be closed. `session(authority, id)` is that method. It is the singular of `sessions()`.

Under "Methods", one row is added after "Plural noun":

> | Singular noun, with a key | The method returns a handle to the one thing the key names, and does no work | `session()` |

Under "The verbs", the first row and the last row become:

> | `add`, `remove` | The thing joins or leaves a collection the file system keeps | `add_mount()`, `remove_member()`, `remove_session()` |
>
> | `open`, `close` | The thing holds resources of this process and must be closed | `close()` |

Spec 4 adds `start` to the same table, and spec 6 uses `add` and `remove` for policies. Each carries its own line.

Reason: the rule exists so that a name does not hide work or a duty. This name hides neither. `use_session` is the alternative, under "Choices for the owner".

### 26. Two landings, each green

1. **The handle.** `fs.session` in place of `open_session`; decisions 2 to 12 as far as they need no store; decision 23; decision 24's first three rows; decision 25; `owner_key`; `builtins-ignorelist = ["id"]` under `[tool.ruff.lint.flake8-builtins]` in `pyproject.toml`, which the argument `id` needs; every caller rewritten; the docs. It needs nothing from spec 0. `exists`, `sessions`, `remove_session` and `session_lifetime` are not yet there.
2. **The row.** `vfs_sessions`, `resolve`, `find`, `make_fork`, the use, `exists`, `fs.sessions`, `fs.remove_session`, expiry and `session_lifetime`. It needs spec 0's third and fourth landings.

Reason: the first is of use alone, since it removes a lifecycle that did nothing, and it lets specs 3, 4 and 6 name the handle before the store exists.

### 27. A fork's row is made by one function, which refuses an id the owner already has

```python
async def make_fork(
    store: KernelStore, session: AsyncSession, ref: SessionRef, *,
    parent_id: str, fork_before: str | None, fork_number: int, turn_counter: int, lifetime: timedelta,
) -> int | None: ...

async def read_session(store: KernelStore, session: AsyncSession, ref: SessionRef) -> SessionInfo | None: ...
```

`make_fork` is the statement F2 of spec 4's decision 17 ("A fork copies the turns below the fork point, their stamps and their shell state, in statements with a fixed number of binds"). It runs inside spec 4's `commit`.

1. A row under the ref that has expired is removed by decision 22's first step.
2. One `INSERT ... ON CONFLICT (owner_key, id) DO NOTHING RETURNING session_key`, of one row and so of a fixed number of binds, with the three lineage columns and `turn_counter` as given. Spec 4 passes the fork point less one.
3. It returns the new key. When the insert returned no row the owner has the id, and it returns `None`. It never adopts the row that is there.

Spec 4 turns `None` into its refusal `vfs.exists`, and reads the lineage that refusal carries with `read_session`, one `SELECT` that returns the row as a `SessionInfo`.

Two forks to one new id at one moment: one insert wins the unique index, and the other returns `None`. A fork and a first write to one id at one moment: whichever commits first has the row, and a fork that lost is refused.

Reason: `resolve` answers the same for a row it made and a row it found, which is right for a session and wrong for a fork. Spec 4's decision 16 gives the case: adopting a session under the id would hand back one that may have gone its own way.

### 28. The calls over the row return plain values and raise a classified error

| Call | Returns | Raises |
|---|---|---|
| `fs.session(...)` | a handle | `TypeError` for a wrong type; `ValidationError`, `vfs.invalid`, for an unlawful id or an anonymous authority |
| `session.exists()` | `bool` | `VFSError` with the store's fact |
| `fs.sessions(...)` | `SessionPage` | `ValidationError`, `vfs.invalid`, for a bad `after` or `limit`; `VFSError` with the store's fact |
| `fs.remove_session(...)` | `bool` | `ValidationError`, `vfs.invalid`, for an unlawful id; `VFSError` with the store's fact |

- Each exception carries a `Result` with the one classified fact, as `MountError` does, and as spec 4's `start_turn`, `rewind`, `fork` and `turns` do (its decision 21).
- **The store's fact** is `KernelStoreUnavailable.error`, raised on as `exception_for_kind` maps its kind, which is `VFSError` for the family `vfs.unavailable`. A drain whose flush failed raises the same way.
- No kind is added. A session that does not exist is not an error of any of these four: `exists()` is `False`, `remove_session` is `False`, and `fs.session` makes no claim. Another owner's session is answered exactly as one that does not exist.
- On the synchronous face each coroutine goes through the management hop, which raises `RuntimeError` on a closed facade (`src/vfs/sync.py:709-714`).

Checked against today's code: `add_mount` returns nothing and raises `MountError`; `mounts()` returns a value; `grants` and `set_posture` return a `Result` because they are ops routed to a storage. These four manage the kernel's own records and reach no storage, so they are of the first kind, and nothing here departs from it.

Reason: the reconciling round's rule for what a call returns. A `Result` from `remove_session` that nobody reads would be a removal that silently did not happen.

## Cost

Costed against the reference deployment in the working agreement. Its callers start 2 to 5 agent sessions a person a day, so about 3,500 new sessions a day, and with a 30-day lifetime about 105,000 rows at the centre and 150,000 at five a day. That count is an estimate from those figures.

**Per verb call, about 150,000 a day.** Asking for a handle issues no statement. A call through a handle adds no synchronous statement from this spec: it calls `put_behind` once. Behind the call, the use kind issues one `SELECT` a flush for all the sessions the flush names, however many calls they made. A flush takes at most 1,024 rows, so at most 1,024 sessions and 2,048 binds. A touch is at most one `UPDATE` a flush, and at most 12 an hour for any one row. The bound over a day is the number of calls, 150,000, reached only if every call is more than five minutes after the last on its session.

**Per file write, about 1,050,000 a day.** A write through a session resolves the session once a call, not once a file, so that specs 3 and 5 can write their rows: one read by a unique index, inside the `commit` they already open. The 50,000 single-file writes a day add at most 50,000 such reads. The nightly batch is 100 calls and adds 100.

**Per index visit.** Nothing.

**Per batch.** One `resolve` for a 10,000-entry call. Its statement does not grow with the entries. The removal of a session that made such a call reclaims its 10,000 change records in 3 calls of `remove_changes`: two chunks, and one that finds none.

**Per corpus.** The sweep reads expired rows and markers by their indexes, never the table. At a steady state about 3,500 sessions expire a day. One call of the sweeper marks at most 100, and a pass is due every 1,024 writes of a process, so a deployment that makes 150,000 calls a day runs well over the 35 calls a day that needs. An expired row that no pass has reached yet reads as absent anyway.

**Per lock.**

| What is locked | For how long | Who waits |
|---|---|---|
| nothing, by `find`, `exists` and a listing, which are `query` calls | | no one |
| the unique index entry of one new session | one commit | a rival creating the same session |
| one session row, by a touch, by step 1, or by spec 4's counter | one commit | another touch, turn or removal of that session |
| the rows of one chunk of step 2 | one commit | no one who is served, since the marker's rows are reachable by no handle |
| on SQLite, the kernel store's one writer | one commit, and for a chunk about 20 ms at the median and 200 ms at most, as the log cost study measured | a stamp flush, a job being stored, another chunk |

No table lock is taken. No read of a file waits on any of this, because on SQLite the kernel store is a file of its own. No lock is held across a batch's body, a person's pause, or the whole of a removal.

**Size.** A row is 13 columns and three indexes, and holds the 64-character key twice. It was not measured. By the log study's 572 to 620 bytes for a 15-column row with two indexes, about 450 bytes is the estimate, and 150,000 rows about 70 MB.

**Memory.** The store's buffer holds one use per session it has not flushed. A handle holds seven references.

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

Each is written and seen failing before the code. A count is of statements recorded by a `before_cursor_execute` listener, leaving out `BEGIN`, `COMMIT`, `PRAGMA`, `SAVEPOINT`, `RELEASE` and `ROLLBACK`, on the engine named; for the kernel store that is `store.engine`. Never of time. A time a test needs comes from the clock of `tests/support/kernel_store.py`, which the test steps forward.

The handle, first landing, in `tests/test_sessions.py` unless a file is named:

- `test_asking_for_a_session_issues_no_statement`: two calls of `fs.session`, with an id and without, issue 0 statements on the root mount's engine, and return two objects with equal `id` when the id was given.
- `test_a_made_id_is_thirty_lawful_characters`: 1,000 handles with no id have 1,000 distinct ids, each 30 characters, each beginning `ses_`, each lawful.
- `test_an_unlawful_id_is_refused`, one case each for: the empty string, 256 characters, a space, a newline, a character outside ASCII, an integer, `bytes`. The first five raise `ValidationError` whose result holds 1 error of the kind `vfs.invalid`, and the last two raise `TypeError`.
- `test_an_id_is_kept_byte_for_byte`: `Conv_1` and `conv_1` give handles whose refs differ.
- `test_an_anonymous_authority_owns_no_session`: `fs.session(Authority.anonymous())` and `fs.session()` on a kernel with no default each raise `ValidationError`; with `default_authority` set, `fs.session().authority` is the default.
- `test_a_wrong_type_is_refused`: `fs.session("someone")` and `fs.session(ALICE, strict=1)` each raise `TypeError`.
- `test_a_non_empty_policies_is_refused_until_policies_exist`: raises `ValueError`. Spec 6 deletes this test.
- `test_a_handle_offers_no_way_to_change_itself`: assigning `authority`, `id`, `strict` or `policies` raises `AttributeError`, on both faces.
- `test_a_right_taken_away_binds_the_next_call_through_a_handle`: one handle reads a file, the grant is revoked, and the same handle's next read is refused. 1 success, then 1 refusal, with no new handle made.
- `test_delete_on_a_handle_is_the_file_verb`: `session.delete()`, `session.delete(None)` and `session.delete(path=None)` each answer `vfs.invalid`, and the session's `delete` has the kernel's parameters without `authority`. 3 refusals.
- `tests/test_authority.py::test_the_owner_key_is_64_hex_characters`, `::test_the_owner_key_ignores_order_kind_scopes_and_repeats`, `::test_a_joined_subject_is_another_owner`, `::test_names_that_join_alike_do_not_collide` (actor `a:b` for `c` against actor `a` for `b:c`), `::test_the_owner_key_takes_any_name` (a lone surrogate), `::test_every_authority_has_an_owner_key` (the anonymous and the system authority each give 64 characters, and the two differ), and `::test_the_owner_key_is_pinned`, which holds one known authority to one literal key, so a change of encoding fails by name.
- `tests/base/test_authority.py::test_a_session_verb_is_the_direct_call_with_the_authority_filled_in`, per op, through `fs.session(ALICE)`: the result equals the direct call's, and the storage records the same calls.
- `tests/base/test_authority.py::test_session_verbs_take_no_identity_argument`, per op, unchanged.
- `tests/base/test_authority.py::test_a_session_cannot_reach_a_mount`: the public names of both faces are the 25 ops and `authority`, `cli`, `id`, `strict`, `policies`, and neither face has `close`, `closed`, `__enter__`, `__exit__`, `__aenter__` or `__aexit__`.
- `tests/base/test_authority.py::test_a_handle_on_a_closed_file_system_answers_as_the_file_system`, per op: `backend_unavailable`, and 0 calls recorded by the storage. It replaces `test_a_closed_session_refuses_and_dispatches_nothing` and `test_closed_is_final`, which are deleted.
- `tests/test_sync.py::test_the_constructors_and_the_context_managers_are_twins`: `session` is a twin on both faces as `mounts` is, and the count of a session's coroutines is the ops and `cli`.
- `tests/test_package.py::test_the_session_lifecycle_is_gone`: neither file system has the attribute `open_session`, and `vfs.session` has neither `CLOSED_SESSION_DETAIL` nor `closed_refusal`. 4 names looked for, 0 found.
- `test_the_naming_page_names_session_as_the_one_exception`: `documentation/maintainers/how-we-name.md` holds "with one exception" once, the row "Singular noun, with a key" once, `remove_session()` once, and `open_session` 0 times.
- The gate's `ruff check src/ tests/` exits 0 with an argument named `id` in `src/vfs/base.py`.

The row, second landing, in `tests/test_sessions.py`, on a SQLite file and on the Postgres leg unless one engine is named:

- `test_a_first_write_is_three_statements_and_the_next_is_one`: `resolve(create=True)` for a new session issues 3 statements on the kernel store and leaves 1 row; the same call again issues 1 and leaves 1 row.
- `test_a_use_alone_makes_no_row`: a `read` through a handle, then `store.drain(scope)`: 1 statement on the kernel store, 0 rows.
- `test_a_call_through_a_session_issues_no_statement_on_the_kernel_store`, for `read`, `ls` and `grep`: 0 statements between the call and its return.
- `test_a_10_000_entry_write_through_a_session_reports_one_use`: after the drain, 1 statement on the kernel store. Marked `slow`.
- `test_a_hundred_calls_are_one_use`: 100 reads through one handle with the store's task held, then one flush: 1 statement.
- `test_eight_first_writes_at_once_leave_one_row`: 8 concurrent `commit` calls of `resolve` leave 1 row and return 1 distinct key.
- `test_a_use_inside_five_minutes_updates_nothing`: with the clock stepped 4 minutes past the row's `last_used_at`, 0 `UPDATE` statements; stepped 6 minutes, 1, and `expires_at` is `now` plus the lifetime plus five minutes.
- `test_resolve_of_10_000_sessions_stays_inside_the_budget`: with `membership_budget` narrowed to 1,000 and `parameter_budget` to 3,500, 10,000 new refs issue 20 reads of 500 pairs, 20 inserts of 500 rows and 20 second reads, 60 statements, leave 10,000 rows, and no statement carries more than 3,500 binds. Marked `slow`.
- `test_find_writes_nothing`: `find` inside a `query` issues 1 `SELECT`, and the row's `last_used_at` is unchanged with the clock an hour on.
- `test_exists_is_false_then_true_then_false`: false on a new handle with 1 statement; true after a `resolve(create=True)`; false after `fs.remove_session`; and no call of `exists` changed `last_used_at`.
- `test_another_owner_sees_nothing`: two authorities resolve the same id. 2 rows. Each one's `exists()` is true, each one's `fs.sessions` holds 1 row, and `fs.remove_session` by one returns `True` and leaves the other's row.
- `test_a_listing_is_a_page`: 250 sessions of one owner; `fs.sessions(a)` returns 100 rows in id order with `next_after` set, and three calls return 250 distinct ids and end with `next_after` `None`. Each call issues 1 statement.
- `test_the_system_authority_lists_every_owner`: 3 owners with 2 sessions each give 6 rows in key order; a named owner's page holds 2; the anonymous authority's holds 0 with 0 statements.
- `test_a_bad_cursor_is_refused`: `after="a b"` raises `ValidationError`, and for the system authority `after="x"` does.
- `test_remove_session_says_whether_one_was_there`: `True` with 3 statements when the session has no child rows, and the row is gone; `False` with 1 statement the second time; `False` with 0 statements for the anonymous authority.
- `test_a_removed_id_is_a_new_session`: after a removal, a `resolve(create=True)` returns a key greater than the old one, and `created_at` is the new `now`.
- `test_removal_reclaims_in_chunks`: with one child function over a test table of 12,000 rows for the session, step 2 calls it 3 times, no call deletes more than 5,000 rows, and then 1 statement deletes the marker.
- `test_a_crash_between_the_steps_is_finished_by_the_sweep`: step 1 alone leaves 1 marker; `store.sweep()` leaves 0 rows and returns 1.
- `test_an_expired_session_is_gone_at_once`: with the clock stepped past `expires_at`, `exists()` is false, the listing holds 0 rows, `find` returns `None`, and `resolve(create=True)` returns a new key and leaves 1 marker.
- `test_the_sweeper_marks_no_more_than_a_batch`: with 250 expired rows, one call of the sweeper leaves 100 markers and 150 expired rows.
- `test_a_fork_row_refuses_an_id_the_owner_has`: `make_fork` returns a key and stores the three lineage columns and the counter it was given; a second `make_fork` to the same ref returns `None` and changes 0 rows; a `make_fork` over an expired row returns a key and leaves 1 marker. `read_session` returns the lineage.
- `test_a_fork_outlives_its_parent`: a row whose `parent_id` names a removed session is unchanged by both steps.
- `test_session_lifetime_is_a_positive_timedelta`: `timedelta(0)`, a negative one, `30` and `None` each raise `ValueError`.
- `test_a_store_that_cannot_answer_raises_its_fact`: with the store closed, `await session.exists()`, `await fs.sessions(ALICE)` and `await fs.remove_session(ALICE, "c")` each raise `VFSError` whose result holds 1 error of the kind `vfs.unavailable.backend`, and `fs.session(ALICE)` still returns a handle. 0 statements on the kernel store.
- `tests/test_sync.py`: `sessions` and `remove_session` are in `MANAGEMENT_METHODS` and have twins; `Session.exists` is the twin of `AsyncSession.exists`; each raises `RuntimeError` on a closed facade.
- `tests/test_sessions.py::test_no_handle_reaches_the_store`: no public name of either handle returns the kernel store, beside spec 0's own test that no public method does.

## Scope

In, first landing: `src/vfs/session.py`, `src/vfs/sync_session.py`, `src/vfs/base.py`, `src/vfs/sync.py`, `src/vfs/authority.py` (`owner_key`), `pyproject.toml` (the ignore list for `id`), and a new module `src/vfs/session_records.py` holding `SessionRef`, `check_session_id` and `new_session_id`. The hint at `src/vfs/results/kinds.py:189` becomes "This mount's posture needs a name: pass an authority, or configure a default." On the layer ladder (`tests/lint/test_code_shape.py:46-68`) the new module sits on the rung of `vfs.params` and `vfs.exceptions`, and imports `vfs.authority` alone, so that `vfs.kernel_store`, on the rung above, can import it. The upward import of `vfs.session` by `vfs.base` stays allowed. Then the tests named above, and each caller, file by file:

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

In, second landing: `vfs_sessions` in `src/vfs/models/kernel_rows.py`, with `KERNEL_FORMAT_VERSION` raised by one; a new module `src/vfs/kernel_store/sessions.py` holding every statement of this spec, as spec 0's second rule requires: `resolve`, `find`, `make_fork`, `read_session`, the listing, the two steps of removal, the use kind and the sweeper; `SessionInfo` and `SessionPage` in `src/vfs/session_records.py`, exported from `vfs`; `session_lifetime` on both constructors; `sessions` and `remove_session` on both file systems and in `MANAGEMENT_METHODS` (`src/vfs/ops.py:110`), whose docstring gains "or the kernel's own records"; `exists` on both handles; the registration of the kind and the sweeper where the kernel builds its store.

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
- **`fs.remove_session(authority, id)` removes a session at once.** It is a call on the file system, for the host's code. On a session, `delete` deletes a file.
- **A new member of a group conversation starts a new session.**

Pages, each changed: the docstrings of `AsyncVirtualFileSystem.session`, `.sessions`, `.remove_session`, `AsyncSession`, `AsyncSession.exists`, `SessionInfo` and `SessionPage`, which are the reference page's content; the class docstring of `AsyncVirtualFileSystem` for `session_lifetime`; and the pages in the table under "Scope".

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
> A session stores no right. Every call made through it is judged on its authority at the time of the call. A session is not an [entry](#entry) and has no path. It expires 30 days after its last use, and `fs.remove_session(authority, id)` removes it at once.
>
> In code the handle is `AsyncSession`, with calls you `await`, and `Session`, with plain calls.

and in `glossary.json`: `{"term": "Session", "summary": "VFS's side of one conversation, stored under its owner and its id.", "types": ["AsyncSession", "Session"]}`.

The guide `keep-a-session-for-each-conversation.md` changes in five places. Four are the items under "Where this spec disagrees with the overview or the guides". The fifth is the reconciling round's ruling: in "Find, Expire and Delete Sessions", the sentence "`scout.delete()` does the same at once." becomes "`fs.remove_session(scout_is, "conv_123")` does the same at once."

## Earlier decisions this reverses

- **Decision 5 of the archived spec on principal-scoped sessions:** a session is opened as a context manager, and closed is final. Reversed by decision 23. The same decision's rule that a session is sugar over the funnel, with no second dispatch path, stands at this spec's landing, and spec 3 amends it.
- **The same spec's landing note** that a closed session refuses as `invalid`. The refusal is gone.
- **The naming page's rule** that `session()` is not a method name, and the naming work of 2026-11-16 that renamed it `open_session`. Reversed by decision 25, for the reason that the page's own reason no longer holds.
- **Rule 1 of the retired record on sessions** speaks of a change to a session's narrowing as a subset test. It stands. A handle offers no such change at all, so the test has nothing to refuse.
- **`MANAGEMENT_METHODS` as "the router's public coroutines that manage the mount tree".** It now also names two methods over the kernel's records.
- **This spec's own first draft of decision 21,** which kept `session.delete()` as the removal. The reconciling round's ruling replaced it.

## Choices for the owner

1. **The name `fs.session`.** Taken: `session(authority, id)`, with the amendment of decision 25. The alternative is `use_session(authority, id)`, which needs `use` added to the page's verbs as "the method returns a handle to a named thing and makes nothing".
2. **Anonymous callers.** Taken: an anonymous authority owns no session, and asking raises. The alternative is one owner shared by every anonymous caller, with the id as the only separation.
3. **A changed subject set.** Taken: a new owner and a new, empty session. The alternative needs a copy of a session to another owner, which is not designed.
4. **The id's alphabet.** Taken: visible ASCII. The alternative is any text without control characters, which makes a character more than one byte and brings Unicode look-alikes into a name. Spec 4 takes that alternative for a turn id (its decision 3), so the two ids have two alphabets.
5. **No lifetime that means never.** Taken: `session_lifetime` is always a positive `timedelta`. The alternative is `None` for no expiry.
6. **What the system authority's listing shows.** Taken: each row's actor and subjects in clear. The alternative is the owner key alone.

## Where this spec disagrees with the overview or the guides

1. **`fs.sessions(authority=None)` takes `after=` and `limit=` and returns a page.** The overview's signature has neither. Article 2 of the constitution requires them. The guide's sentence should read: "`fs.sessions(scout_is)` lists the sessions Scout owns, a page of 100 at a time, with each one's id, parent, number of turns and time of last use."
2. **The guide says an id is "a string of 1 to 255 characters".** It should say "1 to 255 visible ASCII characters, kept exactly as given".
3. **The guide does not say that an anonymous caller owns no session.** Its section "Who Owns a Session" should gain: "A caller with no name owns no session, and asking for one is an error. Give each caller a principal of its own."
4. **The guide's section on a chat framework does not say what a new member does.** It should gain the first two sentences of decision 9.
5. **The interrupt guide says "a session opened on it"** in its last section. Nothing is opened: "a session asked for from it".
6. **`vfs_sessions` has four columns the overview's row does not list:** `actor`, `subjects`, `fork_before` and `removed_at`. The table's owner fixes its columns, so this is stated and is not a departure.

The first draft's disagreement over `session.delete()` is settled by the reconciling round, and is decision 21.

## Needs no other spec meets yet

1. **Spec 3: a function that ends a session's stamps.** Its Builds on asks that a removal and an expiry remove its rows, and names no call. The text its spec would need, as an item of its decision 15 or a decision of its own: "`remove_stamps(session, session_key, limit) -> int` deletes at most `limit` rows of `vfs_session_stamps` for one `session_key`, in one statement of a fixed shape, and returns the count. It joins spec 2's `SESSION_CHILDREN`." Until it does, a removed session's stamps stay under a key nothing can reach.
2. **Spec 3: no copy of the session key.** Its decision 8 has a handle keep its address, and its Terms add the surrogate key "once known". The text it would need: "A handle keeps the owner key and the id and never the session key. Each store and each lookup of a stamp gets the key from spec 2's `resolve` or `find`, in the transaction that uses it." Its cost line "a handle's first change also runs spec 2's statement once" then reads "every change".
3. **Spec 4: an expired row reads as absent.** S1 of its decision 4 and F1 of its decision 17 find a session by `owner_key` and `id` in statements of their own, with no test of `expires_at`. The text it would need in each: "The session is found through spec 2's `resolve` or `find`, or the statement carries `AND s.expires_at > :now`, so that an expired session is never given a turn or forked."
4. **Spec 4: the count of turns in the listing.** The text it would need under its decision 2: "The landing that makes `vfs_session_turns` adds the count of a session's turns to the listing statement of spec 2's decision 20."
5. **Spec 7: the first argument of `cancel_session_jobs`.** Its decision 35 takes "the kernel store, or a transaction of it that the caller has open". Decision 22 here calls it inside a `commit` already open. The text it would need: "Called with the SQLAlchemy session of an open `commit`, it issues its one update in that transaction and opens none."

## Not checked

- **Postgres.** No statement here was run on it, and no server was to be had. To run on the Postgres leg: `test_eight_first_writes_at_once_leave_one_row`, for decision 15's account of two first writes; two inserts of one `owner_key` with a `NULL` id, for the default that `NULL` ids are distinct in a unique constraint; and `test_a_fork_row_refuses_an_id_the_owner_has` with two forks at once.
- **How SQLAlchemy renders the membership test over a pair** on each dialect. On SQLite the form `(owner_key, id) IN (VALUES (?, ?), ...)` was run by hand and returned the two rows that were there.
- **The size of a row.** It is an estimate by comparison.
- **The count of live sessions.** It is worked from the reference deployment's sessions a day, and nothing measures how many conversations keep one id.
- **The other eight specs as they are now.** Each was read once in this round, while its writer was revising it. Every name taken from them is as it stood then.
- **Whether `exception_for_kind` maps every kind `KernelStoreUnavailable` can carry to `VFSError`.** Its table and its fallback were read for the family `vfs.unavailable` (`src/vfs/exceptions.py:68-100`), not run.

## One line

A session is a row under its owner's key and an id the host may choose, a handle to it costs nothing and is never closed, and no caller can reach a session by knowing its name.
