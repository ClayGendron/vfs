# `add_mount` takes a posture

This spec is built, on the branch `add-mount-takes-a-posture`, in commit `4b01c9eb`. Two reviews of that build found five things, and each is fixed. The text below is brought in line with the fixes, in decisions 3, 7, 8, 9 and 10, the cost, the tests and the docs. First, a file written into the mount-point directory while the posture was written was hidden by the mount when it committed, and a mount could be committed where its mount-point directory no longer existed. When a posture is given, the table and the mount point are now checked again once the storage has been asked, whether or not anything was written, because a slow read of a posture already held opened the same gap. Second, a posture write could start after `close()` had returned, because the table was not checked between the read of the grants and the write. It is now checked just before the write. Third, `mount_table_refusal` sorted the mount paths on every call, under the mount lock, and it now reads them in the order the kernel keeps. Fourth, `validate_posture` accepted a value that compared equal to a level and was not a `str`, and it now refuses one with a message that names its type. Fifth, the docstring of `add_mount`, `documentation/maintainers/mounts.md` and the glossary said more than the code does, about when the storage is written, which refusals leave the posture alone and where the posture is set. The reviews also found seven changes to the code that no test caught, and each now has a test. The fixes add two functions to `mounts.py`, `require_mount_site` and `require_posture_kept`, which raise what `mount_site_refusal` and `posture_refusal` return, so that `base.py` stays within its entry. Last, `src/vfs/mounts.py` was over the ceiling of 1,000 lines, at 1,109 lines before the fixes and 1,137 after them, so it is split in two with no change in behaviour. `vfs.mounts` keeps the mount, its payload, the checks a mount change passes, `AskStorage` and where a path lives, in 485 lines. A new module, `vfs.listing`, of 693 lines, takes `MountListing`, `PathFilters`, `gather_settled`, `skip_record`, `bare_directory` and the helpers only they use. It sits on a rung of its own in `LAYERS`, between `vfs.mounts` and `vfs.base`, and `vfs.mounts` does not import it. `base.py` ends at 3040 lines and `sync.py` at 1075, and their entries are set to those counts. The whole suite passed the same tests before the split and after it. The first build differed from the text below in five things. The code had moved since the line counts were taken, so the build fits the spec to the code as it now stands. `_gate_mount_change` moved to `mounts.py` as the function `require_gate_allows`, the named fallback, because the three named moves left `base.py` 11 lines over its entry. `base.py` went from 3073 lines to 3065 and `sync.py` from 1078 to 1075, and their entries are set to those counts. `mount_table_refusal` takes a fourth argument, the name of the kernel's class, because the refusal for a sealed root names it, and it returns the words of the refusal for `_check_mount_table` to raise. `mount_site_refusal` takes the mount that holds the path, as `_match_mount` gives it, or `None` for a closed kernel, so that the check for a closed kernel moved with it. Test 12 makes `/data` before it writes the file there, because a write does not make missing parents. The spec as first written follows. It was drafted on 2026-11-18 against commit `0d05c606` on the branch `a-mount-is-listed-as-a-directory-is`. Every statement about today's behaviour was executed on the in-memory storage, and the design was run once as a throwaway subclass of the kernel before it was written down. A fresh reader reviewed it the same day and found two things that stopped it. The first draft set the posture as the system actor, which let a caller open a stored storage they hold no rights in. Decision 4 now sets it as the caller. The draft also named nothing it builds on, and "Builds on" now does. The smaller findings are answered in the text, and the reader signed it fit to build after two more rounds. Three of its decisions could reasonably go the other way, and they are listed under "Choices to confirm".

## The outcome wanted

A mount can be added closed. When `add_mount` is given a posture, no caller reaches the mount's root under any other root posture. There is no moment between two calls in which the mount is live and open. Deeper postures that a stored storage holds stay, as decision 6 says.

## Builds on

This spec is built on the branch `a-mount-is-listed-as-a-directory-is`, which sits on `public-names-follow-the-naming-rules` and `glossary-rules`. None has landed. Two fixes from the review of those branches are part of what it builds on. `update_mount` and `remove_mount` refuse with a retry when the mount point's holder changed while rights were checked, and `ls` and `stat` take a hop from the call's budget. `_check_mount_table` is extracted after those fixes, and `update_mount` and `remove_mount` keep their own checks.

Two other drafts change `src/vfs/base.py` and share its fixed line baseline in `tests/lint/allowlist.py`. They are `agents/2026-11-17-search-applies-its-file-filters-to-rows-in-hand` and `agents/2026-11-18-a-call-that-reaches-several-mounts-bounds-each-mount`. The second also adds a keyword to `add_mount`, `timeout`, and rewrites the same docstring and pages. Whichever is built second places its keyword after the other's, in the order `permissions`, `posture`, `timeout`, `deny_ops`, and sets the baseline again from the file as it then stands.

Two files this spec changes are held at an exact line count by `MODULE_LINE_BASELINE`, and neither may grow. An entry is only ever lowered, never raised.

- **`src/vfs/sync.py`** gains two lines, one in the signature of `add_mount` and one in its call. They are paid by writing the signature of `sweep` in that file on one line, as the signature of `remove_mount` is written. It fits in the line length, and it frees five lines.
- **`src/vfs/base.py`** gains the argument, about 13 lines of docstring on `add_mount`, the steps of decision 3 and the set of decision 10. Three things keep it from growing.
  - The posture write is the function `set_mount_posture` in `mounts.py`, as decision 7 says. The kernel hands it `_call_storage`.
  - The table checks are the function `mount_table_refusal` in `mounts.py`, as decision 3 says.
  - `_probe_mount_site` moves to `mounts.py` as the function `mount_site_refusal`, with the same body. It takes the kernel's `_call_storage`, the mount that holds the mount point and the mount path. It is 32 lines.

Before any other code is written, the docstring drafts below are applied and the two files are counted. If `base.py` is still over its entry after the three moves, `_gate_mount_change` moves to `mounts.py` in the same way, as a function that takes the mount table and the permission layers. The landing ends with each entry in `MODULE_LINE_BASELINE` set to its file's new count, since the lint refuses a file below its entry as it refuses one above it.

## Terms

- **Level.** One of `none`, `list`, `read`, `add`, `contribute` and `read_write`, in that order. Each includes the ones before it.
- **Posture.** The level everyone holds at a path and below. A storage keeps it as a grant row for the principal `*`.
- **Root posture.** The posture at the root of one storage. A mount at `/data` shows it at `/data`.
- **New storage.** A storage no call has touched. Its first call plants one grant row, `*` at `/` with `read_write`.
- **Stored posture.** A posture a storage already holds when it is mounted, as a database storage does after a restart.
- **Mount point.** The path a mount is attached at, such as `/data`.
- **Parent.** The storage that holds the mount-point directory.
- **Child.** The storage that `add_mount` attaches.
- **Mount table.** The kernel's record of its mounts, kept in memory. A call reaches a storage only through it.
- **Mount lock.** The lock a mount change takes while it changes the table. No verb takes it.
- **System actor.** The caller `Authority.system()`, which passes every rights check. It stands for the application's own code.
- **Relabel.** The rewrite a database storage does after a posture changes. Each row beneath the posture carries the level everyone holds on it, and the relabel sets it again.
- **Mask.** The `deny_ops` of a mount, the operations its mounter took out of its capabilities.

## The problem

A new storage gives everyone `read_write`. A posture does not cross a mount. So a storage mounted under a closed root is open to every caller until `set_posture` is called on the mount's path. Between the two calls the mount is live and open.

Executed on 2026-11-18. The root is closed with `set_posture("/", "none")`. Then `add_mount(InMemoryStorage(), "/data")` runs as the system actor, and the system actor writes `/data/report.md`.

| Call | Before `set_posture("/data", "none")` | After |
|---|---|---|
| `read("/data/report.md")` with no authority | Succeeds and returns the content | `unauthenticated` |
| `read("/data/report.md")` as ada, who holds no grant | Succeeds | `not_found` |
| `write("/data/x.md")` with no authority | Succeeds | not run |
| `set_posture("/data", "none")` with no authority | Succeeds, and the row says `granted_by: anon` | `unauthenticated` |

The anonymous caller can read the mount, write to it, and set its posture. The second column lasts until the application's second call returns.

More facts, all executed.

- A new `InMemoryStorage` holds exactly one grant row, `*` at `/` with `read_write`, granted by `system`.
- On a new storage every caller may set the posture, the anonymous caller included. Once the posture is `none`, ada's `set_posture` is refused with `not_found`, even when she asks for `none` again.
- `DatabaseStorage` already takes `posture=` in its constructor. It is planted once, at the first call on a new database, and a stored posture is kept. `InMemoryStorage` does not pass it on, and `InMemoryStorage(posture="none")` raises `TypeError`. A child built as `DatabaseStorage(url=..., posture="none")` is closed from its first call, with no window.
- A stored posture survives a restart. A file database was given `none` at its root and `read` at `/pub`, then closed. A second storage object on the same file showed both rows, and refused the anonymous caller.
- `set_posture` at a root leaves a deeper posture row as it was. The row at `/pub` was still `read` after the root was set again.
- `set_posture` rewrites every row beneath it even when the level does not change. On a storage of 500 files in 10 directories, setting `read_write` over `read_write` reported 511 rows rewritten.
- On a mount whose storage declares no grant verb, `set_posture` is refused with `unsupported`, in the words "operation 'set_posture' is not declared by the storage mounted here". A storage that has the method and does not declare it is refused the same way and is never called.
- A caller who may change a mount can already set its storage's posture. Ada held `read_write` at the mount point and nothing in the mounted storage. She removed the mount, took the storage from the `Mount` that `remove_mount` returned, set its posture directly as the system actor, and added the mount again.

## What the precedent is

This table is general knowledge of Linux and its manual pages. It was not read in source, and no clone was opened for it.

| System | Option | What it sets | When it applies | Where it is kept | When it is omitted |
|---|---|---|---|---|---|
| tmpfs | `mode=`, `uid=`, `gid=` | The mode and the owner of the root directory of the new instance | When the instance is made, before it is attached to the tree | In the instance. `chmod` and `chown` change it later, and a remount does not | Mode 1777, which is open to every user |
| FAT | `uid=`, `gid=`, `umask=`, `dmask=`, `fmask=` | The owner and the mode shown for every file, because the format stores none | At mount, for the life of the mount | On the mount. Nothing is stored | The mounting process's own uid, gid and umask |
| NFS client | None for mode or owner | Nothing. Permissions are the server's stored state | Never | On the server | The server's permissions stand |
| ext4 and other disk formats | None | Nothing. The root directory's mode is stored in the file system | Never | In the file system | The stored mode stands, and a `chmod` of the mount path after mounting changes the mounted root |
| Linux `fsopen`, `fsconfig`, `fsmount`, `move_mount` | Every option | Whatever the file system takes | The file system is configured first and mounted detached. `move_mount` attaches it last | Not applicable | Not applicable |

Four things follow for VFS.

- **An access option is in force before the mount can be reached.** The file system is configured while nothing points at it, and it is attached last.
- **Where permissions are stored, an omitted option leaves them alone.** The stored state stands on ext4 and on NFS. A new tmpfs is open to everyone, as a new VFS storage is.
- **tmpfs `mode=` is the closest case.** It sets stored state on the root once, at mount. A remount does not take it, and `chmod` changes it later. For VFS that is `add_mount` with a posture, `update_mount` without one, and `set_posture`.
- **One case has no close precedent.** A tmpfs mount always makes a new instance. VFS can mount a storage that already holds a posture. Decision 6 settles that case, and FAT is the nearest model, since its options apply on every mount.

## Decisions

### 1. `add_mount` takes `posture`, a keyword of type `Posture | None`

The name is `posture`. It is keyword-only and sits after `permissions`, so the two arguments that say who may do what are side by side. The whole signature is below.

```python
async def add_mount(
    self,
    storage: StorageBackend,
    path: str | None = None,
    *,
    parents: bool = False,
    permissions: Permission | PermissionMap | None = None,
    posture: Posture | None = None,
    deny_ops: Iterable[Op] = (),
    no_overlay: bool = False,
    owned: bool = True,
    authority: Authority | None = None,
) -> None:
```

The value is one of the six levels, as `set_posture` takes. A `str` that is not a level raises `ValueError` with the message `posture must be one of none, list, read, add, contribute, read_write, or None, got <repr>`. A value that is not a `str` and not `None` raises `ValueError` with the message `posture must be a string, got <type name>`, as `set_posture` words its own refusal, even when the value compares equal to a level. It is raised beside the check of `deny_ops`, before the rights check and before any storage is asked.

The mount methods are not in the argument table of `vfs.params`, which holds the verbs only. So the check is a new function, `validate_posture(posture: object) -> Posture | None`, in `vfs/mounts.py` beside `validate_deny_ops`. It reads the levels from `vfs.ops.RUNGS`.

Reason: `posture` is the word `set_posture`, `DatabaseStorage` and the access-levels page already use, and one concept has one noun. A wrong value is a wrong argument, and the mount methods raise `ValueError` for those.

### 2. The default is `None`, and `None` leaves the storage's posture alone

With `posture=None` the kernel asks the child nothing and writes nothing to it. The child keeps the posture it holds. A new storage holds `read_write`. A `DatabaseStorage` built with its own `posture=` holds that. A stored posture stays as it was stored.

So a call that omits the argument behaves as it does today. The problem above remains for such a call, and the docs must say so in the sentence that names the argument.

The safer default, `posture="none"`, is not chosen. It is listed first under "Choices to confirm".

Reason: a default that is not `None` is a write that happens because an argument was left out. It would change the 330 lines that call `add_mount` in 18 Python test files and the three in `README.md`. It would set a stored posture back to `none` on every restart of a process whose code did not name one. It would close every mount of a table rebuilt from `mounts()`, which says to add each mount bare. And the root would still start open, so a mount and the root would differ. The precedent agrees: an omitted option leaves stored permissions alone.

### 3. A posture that is given is in force before the mount is in the table

`add_mount` runs these steps in this order. Steps 4, 5, 9, 10 and 11 are new. The rest are today's, in today's order.

1. `require_storage`. `TypeError` for a storage that cannot be read.
2. The mount path is worked out and checked.
3. `validate_deny_ops`.
4. `validate_posture`.
5. If a posture is given, the child is checked for a posture it can keep, as decision 8 says.
6. `_require_mount_rights`. The parent says whether the caller holds `read_write` at the mount point.
7. The caller's own `mkdir` of the mount point, or `restore` of a deleted one.
8. `_attach_mount` checks that the mount point is an empty directory, as the system actor, and builds the `Mount`.
9. If a posture is given, `_attach_mount` checks the child again as decision 8 says, runs the table checks once with no lock, and reserves the storage object, as decision 10 says.
10. If a posture is given, `_attach_mount` sets it on the child, as decisions 4, 6 and 7 say. This is storage I/O, and the mount lock is not held. The read of the grants is an `await`, so the table checks run again after it and before the write, with no `await` between them and the write. They do not count this call's own reservation against it. A refusal there is raised as at step 9, and the child is not written.
11. If a posture is given, once the child has been asked, whether it was read, written or both, the table checks run again, and then the mount point is checked again with the same check as at step 8, `mount_site_refusal`. A refusal is raised as at step 9 or step 8. A posture write can take as long as a relabel, and a slow read opens the same gap. While either runs, the mount-point directory can gain a row, be deleted, or come to be held by another mount. Without this step the mount would commit over a directory that is no longer empty, and hide its rows, or where no directory is. With it, the window between the check of the mount point and the commit is what it is with no posture. The step runs whether or not anything was written. A call with no posture asks the child nothing and makes no second check.
12. The mount lock is taken. The table checks run again. The mount is put in the table. No `await` lies between the re-check and the commit.

The posture is set inside `_attach_mount`, so `_attach_mount` takes `posture: Posture | None = None` as a keyword after `permissions`, and `add_mount` passes it through. `_attach_mount` also takes `authority: Authority | None = None` as its last keyword, and `add_mount` passes its own, because decision 4 sets the posture as the caller. `_attach_mount` runs `validate_posture` itself, as it runs `validate_deny_ops` itself.

The table checks are the ones `_attach_mount` runs under the lock today, the check of what the caller's rights were judged for among them. They move, unchanged and in the same order, to one private method of the kernel, `_check_mount_table(self, mount: Mount, judged: MountJudgement | None, *, reserved_here: bool = False) -> None`. It raises what the checks raise today. The method runs the check for a closed kernel and the check of what was judged, and then asks the gate. It then calls a function in `vfs/mounts.py`, `mount_table_refusal`, which holds the checks that follow the gate today. It takes the mount table, the mount paths in the order the kernel keeps them, deepest first, and the storage objects reserved under decision 10. It reads the paths in that order and does not sort them again. `reserved_here` says that this call holds the reservation of the storage object, which then does not count against it. So the order is today's, and a call that breaks two rules gets the error it gets today. Steps 9, 10, 11 and 12 all call the method. With `posture=None` step 12 is the only call, as today.

The checks of step 8 and of step 11 raise through `require_mount_site` in `vfs/mounts.py`, which raises `ValueError` with the reason `mount_site_refusal` gives. The checks of decision 8 raise through `require_posture_kept`, which raises `MountError` with the refusal `posture_refusal` gives. Each replaces a block of four lines that `base.py` held twice.

There is no window. The child is in no table entry while its posture is written, so no call through the kernel reaches it. It enters the table only after the write has returned a success. `DatabaseStorage.set_posture` returns only after the posture row is committed and the relabel has finished.

The posture is set last before the lock for a reason. Every refusal that needs no write to the child has had its turn by then, so a refusal before the write leaves the child's posture untouched. The exceptions are the refusals after the write, at step 11 and step 12, when the table or the mount point changed during the write. Decision 9 covers them.

Holding the mount lock across the write was rejected. A posture write on a large stored storage is a relabel, and `close()` and every other mount change would wait for it.

Reason: an access option must be in force before the mount can be reached, as on tmpfs and in the Linux mount API. The mount lock stays a lock held for a commit, never for storage I/O.

### 4. The kernel sets the posture as the caller

The read and the write of decision 7 are made with the caller's admitted authority, through `_call_storage`, at the root path of the child. It is the authority `_admitted` gives: the call's own, else the kernel's default, else the anonymous caller. The child judges the write as it judges `set_posture`. The caller must hold `read_write` at its root.

- On a new storage everyone holds `read_write`. So every caller who may add the mount may set its posture, the anonymous caller included.
- On a stored storage that gives the caller less, the child's refusal is raised as decision 9 says, before the mount is in the table. The system actor sets the posture there instead.
- The grant row names the caller in `granted_by`.

A named caller who holds nothing in a stored closed storage is therefore refused even when asking for the level it already holds. The read of decision 7 fails for them, so the write is tried, and it is refused with `not_found`. Such a caller adds the mount with no posture, and the stored posture stands.

A caller who can read the grants at the child's root, and who asks for the level already stored, is not written for and is not refused, since nothing changes. A caller who holds `read` in a storage closed with `none` is one.

The read is made as the caller, and never as the system actor. A read made as the system actor would let a caller who holds nothing learn a hidden posture, because the call would succeed exactly when their guess matched it.

Reason: a posture is state in the child, and each storage keeps its own access. The right to change a mount is judged in the parent and says nothing about the child. A write made as the system actor for a named caller would widen a stored posture that `set_posture` refuses them. Executed: a shared database was mounted closed in one kernel. In a second kernel a caller held `read_write` only at a scratch directory. A posture write made for her as the system actor let the anonymous caller of the first kernel read the shared files, and the row named `system`. The same write made as the caller is refused with `not_found`.

### 5. The caller gets no grant in the child

A caller who may add the mount holds `read_write` at the mount point in the parent. That says nothing about the child. In the child the caller holds what its posture gives everyone and what its own grants give them, and nothing more. No grant row is written for the caller.

Executed on the prototype: ada added a new storage with `posture="none"`. Her `write` into it was refused with `permission_denied`, and the child held one grant row, the `*` row.

The system actor grants in the child after the mount is added, as it does today.

Reason: each storage keeps its own access, and a grant at a mount's path is a grant in the mounted storage. A mount change that wrote a grant would be a second way to grant.

A consequence the docs must state: whoever may change a mount may set the posture of a new storage, because everyone holds `read_write` in it. A stored storage's posture is set only by a caller who holds `read_write` at its root.

### 6. A posture that is given replaces the root posture the child holds, and nothing else

The argument sets the `*` row at the root of the child, as `set_posture` at the mount's path does once the mount exists. A stored root posture is replaced. Posture rows deeper in the child, and every grant, stay as they are. So `posture="none"` on a stored storage does not close a subtree that a deeper posture row opens.

A process that passes the same posture on every start is stating configuration. A process that wants the stored posture to win passes nothing.

Reason: the argument then means one thing on a new storage and on a stored one, which is the level everyone holds at the mount's root when the call returns. A rule that applied only to a new storage would need the kernel to tell a new storage from a stored one, and the storage protocol has no such question.

### 7. The child is written unless a read shows that everyone already holds the posture at its root

Before it writes, the kernel asks the child for `grants` at its root, as the caller. If the answer succeeds and holds a row whose `principal_id` is `*`, whose `path_prefix` is `/` and whose `level` equals the posture asked for, nothing is written. In every other case the kernel calls `set_posture` at the root. That covers a failed read, an answer with no such row, a row with another level, and a row with that level for a principal that is not `*`.

The read is made only when the child declares `grants`. A child that declares `set_posture` and not `grants` is written without a read. So the child is written in three cases: it holds another level at its root, it does not declare `grants`, or the read failed.

The test of the answer is a new function in `vfs/mounts.py`, `everyone_holds(answer: Result, posture: Posture) -> bool`. The read and the write are one new function in `vfs/mounts.py`, `set_mount_posture(ask, mount: Mount, posture: Posture, authority: Authority | None, check: Callable[[], None]) -> None`, which raises `MountError` as decision 9 says. `ask` is the kernel's `_call_storage`, which gives a call with no authority the kernel's default or the anonymous caller. It makes both calls through `ask`, with the `Mount` that step 8 built and that is in no table yet. `check` is the table checks of step 10, and it is called with no `await` before the write.

Reason: a posture write is never free. Measured, a `set_posture` to the level already held rewrote all 511 rows of a 500-file storage. A process that names its posture at every start would relabel the whole storage at every start, in every worker. At ten million files that is a pass over the corpus for each process start. One read avoids it.

### 8. A child that keeps no posture refuses the argument before anything is made

A posture can be set on a child only when its declared capabilities hold `set_posture` and it has the grant methods, which is `isinstance(storage, SupportsGrants)`. Otherwise `add_mount` raises `MountError`. That covers a child that declares no `set_posture` and one that declares it and lacks the methods. The error carries one `unsupported` refusal at the mount path, with the detail `the storage keeps no posture, so add_mount cannot set one`. The message is `Cannot mount at <path>: <the refusal's message>`.

It is raised at step 5, before the rights check and before the directory is made. `_attach_mount` checks it again from the `Mount` it builds, because it is the method that writes. The check is a new function in `vfs/mounts.py`, `posture_refusal(storage: StorageBackend, declared_caps: frozenset[str], mount_path: Path) -> Result | None`, beside `rights_refusal`. With a posture, `storage.capabilities()` is therefore read twice.

With `posture=None`, such a child mounts as it does today.

The child's declared capabilities decide, and the mask does not. `add_mount(storage, "/data", posture="read", deny_ops={"set_posture"})` sets the posture and then refuses every later `set_posture` on the mount. Executed on the prototype. Nor does the mount's own `permissions` decide. `add_mount(storage, "/ro", permissions="read", posture="none")` sets the posture, and a later `set_posture` at `/ro` is refused by the map.

Reason: a storage that keeps no grants serves every row to every caller. Ignoring `posture="none"` there would return a mount that looks closed and is open. `unsupported` is what `set_posture` on such a mount answers today, and `MountError` is how a mount method carries a refusal.

### 9. A failed posture write raises `MountError` and adds no mount, and no failure puts a posture back

| What fails | Raised | Mount-point directory | Child's posture | Mount |
|---|---|---|---|---|
| `posture` is not a level | `ValueError` | Not made | Not asked | None |
| The child keeps no posture | `MountError`, `unsupported` | Not made | Not asked | None |
| Rights, the gate, or the `mkdir` | As today | As today | Not asked | None |
| The mount point is not an empty directory, or the table refuses at step 9 | `ValueError`, or `MountError` when the gate refuses, as at step 12 | Stays | Not asked | None |
| The table refuses at step 10, after the read and before the write | As at step 9 | Stays | Read, not written | None |
| The child refuses `set_posture` | `MountError` that carries the child's refusal | Stays | Whatever the child did | None |
| The child cannot be reached | `MountError`, `backend_unavailable` | Stays | Unknown | None |
| The table or the mount point refuses at step 11, after the child was asked | As at step 9, or `ValueError` as at step 8 | Stays | The posture asked for, written or already held | None |
| The table refuses at step 12 | `ValueError` or `MountError`, as today | Stays | The posture asked for | None |

A refusal from the child is carried with the mount's path in front of its paths, which `Result.with_mount` does. The message is `Cannot mount at <path>: <the refusal's message>`, and a refusal with no message reads `the storage refused the posture`. A `TransportError` becomes `backend_unavailable` in `_call_storage`, as for any verb. Any other exception is a fault in the storage and is raised as it is.

`DatabaseStorage` commits the posture row before it relabels. A failure during the relabel leaves the new posture in force and the relabel pending. A retried `add_mount` with the same posture finds the row in force and writes nothing, so it does not finish the relabel. Readers are judged correctly while the relabel is pending, at a cost to each read. `set_posture` at the mount's path finishes it. Executed: a relabel was stopped before its first chunk, the anonymous caller was still refused, and a later `set_posture` rewrote the rows and cleared the mark.

No failure puts the earlier posture back.

Reason: the child is in no table entry when the call fails, so the posture left behind opens nothing through this kernel. Putting it back would be a second write and a second relabel. It could fail too. On a shared database it could overwrite a posture that another process set in between. The caller holds the storage and the next `add_mount` sets the posture again. The directory already stays after a failed mount, for the same reason.

### 10. While a posture is being set, no other call can mount that storage object

The table checks at step 9 refuse a storage object that is already mounted. Without them, `add_mount(storage, "/b", posture="none")` on a storage that is live at `/a` would close the live mount before the call was refused.

Step 9 also reserves the object. The kernel keeps `self._posture_writes: set[int]`, the `id` of each storage whose posture an `add_mount` in flight is writing. It is made empty in the constructor.

- `_check_mount_table` gains one check, after the others. A storage whose `id` is in the set raises `ValueError` with the message `Cannot mount at <path>: another call is mounting that storage object, so retry`.
- At step 9 the call runs `_check_mount_table` and then adds the `id`, with no `await` between the two.
- At steps 10 and 11, and at step 12 under the lock, the call runs `_check_mount_table` with `reserved_here=True`, which leaves its own `id` out of the set the checks read. At step 12 it then commits, with no `await` between the check and the commit. With `posture=None` step 12 passes `reserved_here=False`, so a call with no posture is refused while another call holds the reservation.
- A `finally` around steps 10 to 12 removes the `id` with `set.discard`, whether the call commits, fails, is cancelled, or meets a fault raised by the storage.

A second call for the same object is refused whether or not it names a posture. So a posture is written only to a storage that is in no table entry and that no other call can put in one.

Reason: without the reservation, two calls that mount one object at two paths with two postures could both write. The one that commits could then hold the posture the other asked for. The reservation costs a set lookup and takes no lock across storage I/O.

The reservation is by object, in one kernel. Two storage objects on one database, or one object in two kernels, are not seen. Each write there is an ordinary `set_posture` on shared state.

### 11. `update_mount` and the constructor take no posture

`update_mount` is unchanged. Once a mount exists, `set_posture` at its path reaches the root of the mounted storage, under that storage's own rights check. There is no window to close, since the mount is already live under the posture it has.

The kernel's constructor is unchanged. The root storage keeps the posture it holds.

Reason: `update_mount` changes policy, which lives on the mount, and a posture is state in the storage. tmpfs does not take `mode=` on a remount. The constructor is not a coroutine, so it cannot call a storage. It also has no window, because no caller holds the kernel until the constructor returns, and the code that built it can set the root's posture before it hands the kernel on. A root built as `DatabaseStorage(posture=...)` starts with that posture.

### 12. A posture is not a field of `Mount` or `MountPayload`

`Mount`, `MountPayload`, `Mount.to_payload()` and `mounts()` are unchanged. The posture is read with `grants` at the mount's path.

Reason: policy lives on the mount and state lives on the storage. A posture changes through `set_posture` while the mount stays the same object, so a field would be out of date after the first change. `mounts()` promises that no storage is asked and that what it returns is what the gate reads. Rebuilding a table from `mounts()` needs no posture either, because each `Mount` carries its storage and the storage carries its posture.

### 13. The sync facade takes the same argument, and nothing else mirrors the signature

`VirtualFileSystem.add_mount` in `src/vfs/sync.py` takes `posture: Posture | None = None` at the same place and passes it on. `Posture` is already imported there and in `base.py`, and `vfs` already exports it.

`tests/test_sync.py::test_every_router_coroutine_has_a_sync_twin` compares the two signatures by name, kind, default and annotation. It fails for `add_mount` until the facade follows, and it needs no change. No other test compares the mount methods' signatures. `AsyncSession` and `Session` have no mount methods, and the tests that hold that stay as they are. `vfs.params` is untouched.

### 14. Nothing is added to the storage protocol, and no storage changes

The kernel uses `grants` and `set_posture`, which `SupportsGrants` already has. `DatabaseStorage` and `InMemoryStorage` are not edited.

## Cost

Storage calls made by one `add_mount`. The parent's calls are today's, and a posture that is given adds two more, the `stat` and the `ls` of step 11, whether or not the child is written.

| Case | Calls on the parent | Calls on the child |
|---|---|---|
| No posture, system actor | `mkdir`, `stat`, `ls` | None |
| No posture, named caller | `holds`, `mkdir`, `stat`, `ls` | None |
| Posture the child already holds | As above, then `stat`, `ls` | `grants` |
| Posture the child does not hold | As above, then `stat`, `ls` | `grants`, `set_posture` |
| Posture, and the child does not declare `grants` | As above, then `stat`, `ls` | `set_posture` |

The table checks of steps 10 and 11 read the table in memory and ask no storage. `mount_table_refusal` reads the mount paths in the order the kernel keeps, so no check sorts the table.

Counted on SQLite, on a storage that had been touched once. The table leaves out SQLite's `SAVEPOINT`, `RELEASE`, `PRAGMA` and `ANALYZE` statements.

| Call on the child | Statements | Rows rewritten |
|---|---|---|
| `grants` at the root, counted as the system actor | 1 transaction, 1 `SELECT`, which returns every grant row at the root. A named caller adds the reads that resolve their rights | 0 |
| `set_posture` at the root of an empty storage | 4 transactions, 15 `SELECT`, 9 `UPDATE`, 1 `INSERT`, 1 `DELETE` | 1 |
| `set_posture` at the root of 500 files in 10 directories | The same statement counts | 511 |

Against the reference deployment.

- **A mount change is a rights change.** It is made a few times a day, and once for each mount at each process start. It rides on no per-call, per-write or per-index multiplier.
- **A process start that names the posture its storage holds costs one `SELECT` for each mount.** Nothing is written and no lock is taken. The mount point is checked again, with the two parent calls below.
- **A posture that is given costs two more calls on the parent, written or not.** They are the `stat` and the `ls` of the mount point, each a bounded read of one directory, and they ride on no multiplier but the mount change itself.
- **A posture that differs costs what `set_posture` costs today.** The relabel visits every row beneath the root, down to the next deeper posture row, in bounded chunks. At ten million files and a million directories that is about 220 transactions of at most 50,000 rows each, the storage's `RELABEL_ROWS`, and `add_mount` returns after the last. The count is worked out and was not run. The storage's own rule applies: a call that creates a row waits for each posture transaction, so a stored posture is changed outside the ingest window. This is the cost of the two-call sequence used today, moved to before the mount is live.
- **No read waits.** No verb takes the mount lock. The mount lock is not held during any storage call, so `close()` and other mount changes do not wait for a relabel.

The time `add_mount` takes with a posture is the time `set_posture` takes. No time budget is added.

## Tests

In a new file, `tests/base/test_mount_posture.py`, written and seen failing before the code. Counts are of calls recorded by a storage double, never of time.

The file defines `SYSTEM`, `ADA`, `closed()` and `paths(fs)` as `tests/base/test_mount_authority.py` does. It adds `posture_at(fs, path)`, which calls `fs.grants(path, authority=SYSTEM)` and returns the `level` of the row whose `principal_id` is `*` and whose `path_prefix` is `path`. The doubles come from `tests/support/base_doubles.py`.

No existing test pins behaviour that changes, because the default keeps today's behaviour.

Where a test names no root, the file system is `AsyncVirtualFileSystem()`, whose root is a new `InMemoryStorage`. Where a test names no authority, the call names none, so the caller is anonymous. A test that sets a posture on a storage that is not new passes `authority=SYSTEM`, because decision 4 sets the posture as the caller.

1. `test_add_mount_takes_a_posture_that_defaults_to_none`. For `AsyncVirtualFileSystem` and `VirtualFileSystem`, the `posture` parameter of `add_mount` is keyword-only and its default is `None`.
2. `test_update_mount_and_the_mount_take_no_posture`. `posture` is no parameter of `update_mount` on either face, no field of `Mount`, and no key of `MountPayload.__annotations__`.
3. `test_a_mount_added_closed_is_closed_from_its_first_call`. On `closed()`, `add_mount(InMemoryStorage(), "/data", posture="none", authority=SYSTEM)`, then a write of `/data/report.md` as `SYSTEM`. `read` with no authority is `unauthenticated`, `read` as `ADA` is `not_found`, and `posture_at(fs, "/data")` is `"none"`.
4. `test_a_mount_added_with_no_posture_keeps_what_its_storage_holds`. On `closed()`, `add_mount(InMemoryStorage(), "/data", authority=SYSTEM)` leaves `posture_at` at `"read_write"`, and a write with no authority succeeds. A `DatabaseStorage(url="sqlite+aiosqlite:///:memory:", posture="list")` added at `/kept` as `SYSTEM` with no posture leaves `posture_at(fs, "/kept")` at `"list"`.
5. `test_each_level_can_be_the_posture_of_a_new_mount`, parametrised over `vfs.ops.RUNGS`. `add_mount(InMemoryStorage(), "/data", posture=level)` leaves `posture_at(fs, "/data") == level`.
6. `test_no_posture_asks_the_new_storage_nothing`. Root `BindableStorage`, child `RecorderStorage`. After `add_mount(child, "/m", authority=SYSTEM)`, `child.calls == []`.
7. `test_a_posture_is_set_at_the_root_as_the_caller`. Root `BindableStorage`, child `RecorderStorage`. After `add_mount(child, "/m", posture="list", authority=ADA)`, `child.calls` is `[("grants", {"path": Path("/")}), ("set_posture", {"path": Path("/"), "posture": "list"})]` and `child.authorities == [ADA, ADA]`.
8. `test_a_storage_that_does_not_declare_grants_is_written_without_a_read`. Child `RecorderStorage(caps=...)` with every capability but `grants`. After `add_mount(child, "/m", posture="list")`, the recorded ops are `["set_posture"]`.
9. `test_the_posture_is_set_before_the_mount_is_in_the_table`. The child is a `RecorderStorage` subclass whose `set_posture` appends `paths(fs)` to a list, sets an event and waits on a second event. `add_mount(child, "/data", posture="none")` runs as a task. Once the first event is set, `paths(fs) == ["/"]`. After the release and the await, `paths(fs) == ["/", "/data"]` and the list is `[["/"]]`.
10. `test_the_posture_is_set_after_the_mount_point_is_made_and_checked`. Root `BindableStorage`. The child is a `RecorderStorage` subclass whose `set_posture` copies the ops the root has recorded so far. After `add_mount(child, "/m", posture="none", authority=SYSTEM)`, the copy is `["mkdir", "stat", "ls"]`.
11. `test_a_caller_who_may_not_mount_changes_no_posture`. On `closed()`, `/data` is made as `SYSTEM` and ada is granted `contribute` there. `add_mount(RecorderStorage(), "/data", posture="none", authority=ADA)` raises `MountError` with `permission_denied`, and the child's `calls == []`.
12. `test_a_mount_point_that_cannot_hold_a_mount_changes_no_posture`. The root holds a file at `/data/x.md`. `add_mount(RecorderStorage(), "/data", posture="none")` raises `ValueError` that matches `not empty`, and the child's `calls == []`.
13. `test_a_storage_that_is_already_mounted_keeps_its_posture`. One `InMemoryStorage` is mounted at `/a`. `add_mount` of the same object at `/b` with `posture="none"` raises `ValueError` that matches `already mounted`, and `posture_at(fs, "/a")` is still `"read_write"`.
14. `test_a_storage_that_keeps_no_posture_refuses_one_before_anything_is_made`, parametrised over `ReadFamilyStorage()` and `RecorderStorage(caps=frozenset({"read", "stat", "ls", "tree"}))`. `add_mount(child, "/m", posture="none")` raises `MountError` that matches `keeps no posture`. `errors[0].kind` is `unsupported` and its path is `/m`. `paths(fs) == ["/"]`, and `stat("/m")` as `SYSTEM` is `not_found`. The same child then mounts at `/m` with no posture.
15. `test_a_storage_that_declares_the_grant_verbs_and_lacks_them_refuses_a_posture`. The child is a `ReadFamilyStorage` subclass whose `capabilities()` adds `GRANT_OPS`. `add_mount(child, "/m", posture="none")` raises `MountError` with `unsupported`. Nothing was made: `paths(fs) == ["/"]`, and `stat("/m")` as `SYSTEM` is `not_found`.
16. `test_an_unknown_posture_is_refused_before_anything_is_made`. On `closed()`, `add_mount(InMemoryStorage(), "/m", posture="open", authority=ADA)`, where ada holds nothing, raises an exception whose type is exactly `ValueError` and that matches `posture must be one of`. So the check comes before the rights check. `paths(fs) == ["/"]`, and `stat("/m")` as `SYSTEM` is `not_found`.
17. `test_a_storage_that_refuses_the_posture_is_not_mounted`. The child is a `RecorderStorage` subclass whose `set_posture` returns a failed `Result` with one `permission_denied` error at `Path("/")`. `add_mount(child, "/m", posture="none")` raises `MountError` that matches `Cannot mount at /m`. `errors[0].kind` is `permission_denied` and its path is `/m`. `paths(fs) == ["/"]`, and `stat("/m")` as `SYSTEM` succeeds, so the directory stays. A second child whose `set_posture` returns a failed `Result` with one error that has an empty message raises `MountError` that matches `the storage refused the posture`.
18. `test_a_storage_that_cannot_be_reached_is_not_mounted`. Child `TransportFailStorage`. `add_mount(child, "/m", posture="none")` raises `MountError` whose `errors[0].kind` is `backend_unavailable` and whose path is `/m`. `paths(fs) == ["/"]`.
19. `test_a_storage_that_already_holds_the_posture_is_not_written`. The child is an `InMemoryStorage` subclass that counts its `set_posture` calls. It is given `list` directly, with `child.set_posture(path=Path("/"), posture="list", authority=SYSTEM)`, so the count is 1. `add_mount(child, "/data", posture="list", authority=SYSTEM)` leaves the count at 1 and `posture_at` at `"list"`. After `remove_mount("/data", authority=SYSTEM)`, `add_mount(child, "/data", posture="read", authority=SYSTEM)` makes the count 2 and `posture_at` `"read"`.
20. `test_a_posture_replaces_a_stored_one_and_keeps_the_deeper_ones`. With `tmp_path`, a `DatabaseStorage` on a SQLite file is mounted at `/data`, given `none` at `/data` and `read` at `/data/pub`, with `ada` granted `read` at `/data`, all as `SYSTEM`, and its file system is closed. A second `DatabaseStorage` on the same file, added to a new file system with no posture, shows `none` at `/data`. After `remove_mount`, the same object added with `posture="list", authority=SYSTEM` shows `list` at `/data`, still `read` at `/data/pub`, and still the row that grants `ada` `read` at `/data`.
21. `test_the_mask_does_not_stop_the_posture_of_a_new_mount`. After `add_mount(InMemoryStorage(), "/frozen", posture="read", deny_ops={"set_posture"})`, `posture_at(fs, "/frozen")` is `"read"` and `set_posture("/frozen", "none", authority=SYSTEM)` is `unsupported`.
22. `test_no_second_call_mounts_a_storage_while_its_posture_is_being_set`. The child waits in `set_posture` as in test 9. While the first `add_mount(child, "/a", posture="none")` waits, `add_mount(child, "/b")` and `add_mount(child, "/b", posture="read")` each raise `ValueError` that matches `another call is mounting`. After the release, `paths(fs) == ["/", "/a"]` and the child recorded one `set_posture`.
23. `test_a_failed_posture_write_frees_the_storage_for_the_next_call`. The child's `set_posture` fails on its first call and succeeds on its second. The first `add_mount(child, "/m", posture="none")` raises `MountError`. The second returns, and `paths(fs) == ["/", "/m"]`.
24. `test_the_posture_stays_when_the_table_refuses_the_mount_after_it_was_set`. Root `BindableStorage`. The child waits in `set_posture` during `add_mount(child, "/data", posture="none")`. While it waits, a second `RecorderStorage` is mounted at `/data`, by an `add_mount` that is started as a task and awaited before the first is released. A mount lock held across the posture write would make that await never return. After the release the first call raises `ValueError` that matches `Mount already exists`. The first child recorded exactly one `set_posture` and no call after it.
25. `test_a_named_caller_who_adds_a_closed_mount_holds_nothing_in_it`. On `closed()`, `/data` is made as `SYSTEM` and ada is granted `read_write` there. `add_mount(InMemoryStorage(), "/data", posture="none", authority=ADA)` returns. Ada's `write` of `/data/a.md` is `permission_denied`, and `grants("/data", authority=SYSTEM)` holds one row, whose `principal_id` is `*` and whose `granted_by` is `ada`.
26. `test_the_attach_step_sets_the_posture_itself`. The root is an `InMemoryStorage` with an empty directory at `/data`. `_attach_mount(ReadFamilyStorage(), "/data", posture="none")` raises `MountError` with `unsupported`. So does `_attach_mount` of a `RecorderStorage` whose capabilities leave out `set_posture`, which has the grant methods, and that child records no call. `_attach_mount(InMemoryStorage(), "/data", posture="open")` raises an exception whose type is exactly `ValueError`. `_attach_mount(RecorderStorage(), "/data", posture="none")` records `set_posture` on the child.
27. `test_the_plain_face_passes_the_posture_on`. In `with VirtualFileSystem() as fs`, after `fs.add_mount(InMemoryStorage(), "/data", posture="none")`, `fs.read("/data/a.md")` with no authority is `unauthenticated`.
28. `test_validate_posture_and_everyone_holds`. `validate_posture` returns `None` and each level unchanged and raises `ValueError` for `"open"`, which matches `posture must be one of`, and for `3` and `UserString("read")`, which read `posture must be a string, got int` and `posture must be a string, got UserString`. `everyone_holds` is false for a failed `Result`, for a `Result` with no `grants`, for a row for `ada` at `/` with the same level, for a `*` row at `/pub` and for a `*` row at `/` with another level, and true for a `*` row at `/` with the same level.
29. `test_a_named_caller_cannot_widen_a_stored_posture`. With `tmp_path`, a `DatabaseStorage` on a SQLite file is closed at its root as `SYSTEM`, with `set_posture(path=Path("/"), posture="none", authority=SYSTEM)` on the storage. On `closed()`, `/data` is made as `SYSTEM` and ada is granted `read_write` there. `add_mount(storage, "/data", posture="read_write", authority=ADA)` raises `MountError` whose `errors[0].kind` is `not_found`. `paths(fs) == ["/"]`. A second `DatabaseStorage` on the same file still shows `none` for the `*` row at its root.
30. `test_a_named_caller_cannot_add_a_stored_closed_storage_with_the_posture_it_holds`. The same setup. `add_mount(storage, "/data", posture="none", authority=ADA)` raises `MountError` with `not_found`. `add_mount(storage, "/data", authority=ADA)` then returns, and `posture_at(fs, "/data")` is `"none"`.
31. `test_a_cancelled_posture_write_frees_the_storage`. The child waits in `set_posture` as in test 9. The task that runs `add_mount(child, "/a", posture="none")` is cancelled while it waits, and awaiting it raises `CancelledError`. Then `add_mount(child, "/a")` returns and `paths(fs) == ["/", "/a"]`.
32. `test_a_storage_that_raises_in_set_posture_is_freed`. The child's `set_posture` raises `RuntimeError`. `add_mount(child, "/m", posture="none")` raises `RuntimeError`. Then `add_mount(child, "/m")` returns.
33. `test_the_mount_s_own_permissions_do_not_stop_its_posture`. After `add_mount(InMemoryStorage(), "/ro", permissions="read", posture="none")`, `posture_at(fs, "/ro")` is `"none"`, and `set_posture("/ro", "read", authority=SYSTEM)` fails with `read_only`.
34. `test_a_caller_who_can_read_the_stored_posture_and_asks_for_it_is_not_refused`. With `tmp_path`, a `DatabaseStorage` on a SQLite file is closed with `none` at its root and grants ada `read` at its root, both as `SYSTEM` on the storage. The storage object mounted is a subclass that counts its `set_posture` calls from then on. On a file system where ada holds `read_write` at `/data`, `add_mount(storage, "/data", posture="none", authority=ADA)` returns, and the count is 0.

The tests below were added after the reviews of the build. Each was seen failing, before its fix or under the change to the code that no earlier test caught. Every wait in the file, on an event or on a task, is bounded by one constant, `RETURNS_WITHIN`, of five seconds, so a wrong build fails a test and does not hang the suite. Tests 9, 22, 24 and 31 had awaited with no deadline. Nothing asserts on elapsed time.

35. `test_a_call_with_no_authority_sets_the_posture_as_the_kernel_s_default`. On a kernel built with `default_authority=ADA`, `add_mount(child, "/m", posture="list")` with no authority leaves `child.authorities == [ADA, ADA]`.
36. `test_a_posture_checks_the_mount_point_again_whether_or_not_it_is_written`. Root `BindableStorage`. A posture that is written leaves the root's ops at `["mkdir", "stat", "ls", "stat", "ls"]`. A child whose `grants` shows `list` already held, given `posture="list"`, records only `grants`, and the root's ops are the same five.
37. `test_a_storage_that_keeps_no_posture_is_refused_before_the_rights_are_checked`. On `closed()`, ada, who holds nothing, adds a `ReadFamilyStorage` with `posture="none"` and gets `MountError` with `unsupported`, not a rights refusal.
38. `test_a_gate_tightened_while_the_mount_point_is_checked_changes_no_posture`. The root's `ls` waits during the check of the mount point, and the root is made read-only meanwhile. The call raises `MountError` with `read_only`, and the child records no call.
39. `test_a_mount_point_that_gains_a_row_during_the_posture_write_is_not_covered`. While the child waits in `set_posture`, a file is written into the mount-point directory. The call raises `ValueError` that matches `not empty`, no mount is added, the file is still read, and the child recorded `grants` and `set_posture`.
40. `test_a_mount_point_removed_during_the_posture_write_is_not_mounted`. While the child waits in `set_posture`, the mount-point directory is deleted. The call raises `ValueError` that matches `no directory stored at the mount point`.
41. `test_a_mount_point_whose_holder_changed_during_the_posture_write_is_not_mounted`. A mount at `/work` waits in the root's `ls` of `/work` while `add_mount(child, "/work/sub", posture="read")` starts and waits in `set_posture`. The mount at `/work` then commits. The second call raises `ValueError` that matches `no directory stored at the mount point`, and the table is `["/", "/work"]`.
42. `test_a_mount_point_whose_holder_was_removed_while_the_posture_is_read_is_not_mounted`. While the child waits in `grants` for `/work/sub`, the mount at `/work` is removed. The call raises `ValueError` that matches `no directory stored at the mount point`.
43. `test_a_kernel_closed_during_the_posture_write_adds_no_mount`. While the child waits in `set_posture`, the kernel is closed. The call raises `ValueError` that matches `filesystem is closed`.
44. `test_a_kernel_closed_while_the_posture_is_read_writes_no_posture`. While the child waits in `grants`, the kernel is closed. The call raises `ValueError` that matches `filesystem is closed`, and the child recorded only `grants`.
45. `test_a_gate_tightened_while_the_posture_is_read_writes_no_posture`. While the child waits in `grants`, the root is made read-only. The call raises `MountError` with `read_only`, and the child recorded only `grants`.
46. `test_a_mount_point_taken_while_the_posture_is_read_writes_no_posture`. While the child waits in `grants`, another storage is mounted at the same path. The call raises `ValueError` that matches `Mount already exists`, and the child recorded only `grants`.
47. `test_a_named_caller_s_grant_at_the_root_does_not_stand_for_everyone`. A new `InMemoryStorage` grants ada `read` at its root. After `add_mount(child, "/data", posture="read", authority=SYSTEM)`, `posture_at(fs, "/data")` is `"read"` and a write with no authority fails.
48. `test_the_table_checks_follow_the_order_the_kernel_keeps`. `mount_table_refusal` given mounts at `/m/a` and `/m/b`, for a mount at `/m`, names whichever of the two comes first in the order it is given.
49. `test_a_mount_point_that_gains_a_row_while_a_held_posture_is_read_is_not_covered`. A new `InMemoryStorage` subclass waits in `grants`, and `posture="read_write"` is the posture it holds. While it waits, a file is written into the mount-point directory. The call raises `ValueError` that matches `not empty`, no mount is added, the file is still read, and `set_posture` was never called.

No test is added for the line counts. `tests/lint/test_code_shape.py` already fails when `base.py` or `sync.py` grows.

## Scope

In:

- `AsyncVirtualFileSystem.add_mount` and `_attach_mount`, the new private method `_check_mount_table`, and the set `_posture_writes`, in `src/vfs/base.py`.
- `validate_posture`, `posture_refusal`, `require_posture_kept`, `everyone_holds`, `set_mount_posture`, `mount_table_refusal`, `mount_site_refusal` and `require_mount_site` in `src/vfs/mounts.py`, under the banner of the checks a mount change passes. `mount_site_refusal` is `_probe_mount_site` moved.
- `VirtualFileSystem.add_mount` in `src/vfs/sync.py`, and the signature of `sweep` there written on one line.
- The entries of `base.py` and `sync.py` in `tests/lint/allowlist.py`, lowered if the files end shorter.
- The tests above, and the docs below.
- The line "Whether `add_mount` takes a posture" in `agents/tasks.md`, which is removed when this is built.

Out:

- `update_mount`, `remove_mount`, the constructor, `Mount`, `MountPayload` and `mounts()`.
- The storage protocol, `DatabaseStorage` and `InMemoryStorage`. `InMemoryStorage` still takes no `posture` of its own. The class docstring of `DatabaseStorage` names the levels "open, shared or private", which are not levels, and it is left for the docstring task in `agents/tasks.md`.
- A storage that starts closed. A new storage still gives everyone `read_write`.
- A grant for the caller in the child, and any other grant made by a mount change.
- A time budget for the posture write.
- The existing tests that call `add_mount` and then `set_posture`. They stay as they are.

## What the docs must say

- `add_mount` takes `posture`, the level everyone holds at the root of the mounted storage. With it, the mount is never live under another posture.
- With no posture the storage keeps what it holds, and a new storage gives everyone `read_write`. Under a closed root, a mount added with no posture is open to everyone.
- A posture that is given replaces the posture stored at the storage's root. Deeper postures and grants stay.
- The kernel sets it as the caller, who must hold `read_write` at the root of the storage. On a new storage everyone does. The caller gets no grant in the mounted storage.
- A stored storage refuses a posture from a caller who may not set it. A caller who can read nothing in it is refused even the posture it holds. Such a caller adds the mount with no posture, or the system actor adds it.
- If a posture write fails part-way, a retried `add_mount` does not finish it. `set_posture` at the mount's path does.
- A storage that keeps no posture refuses the argument.
- A posture is state in the storage. It is not on `Mount`, and `update_mount` does not take it. `set_posture` at the mount's path changes it later.

Pages and docstrings.

- `documentation/reference/access-levels.md`. In "Mounts", the bullet "A level does not cross a mount" ends by naming the argument, in the form `fs.add_mount(storage, "/data", posture="none")`, in place of the sentence that says a new mount is open until `set_posture` is called. In "Who Holds a Level", the table gains a row for everyone at a new mount. In "Who May Change Access", the row for `add_mount` says that a posture is set under the mounted storage's own rule for `set_posture`.
- `documentation/maintainers/mounts.md`. A new section, "The posture of a new mount", after "Who may change a mount". It holds one bullet for each of decisions 3, 4, 7, 8, 9, 10 and 12, with its reason, and two more from decision 3: which refusals leave the posture alone, and why the table is checked again before the write and the mount point after it.
- `documentation/reference/glossary.md`, the Mount term. One sentence that `fs.add_mount(..., posture=...)` sets what everyone holds at the root of the mounted storage, and one that a posture set deeper in it stays.
- `README.md`, "Known limits". The bullet on a fresh storage's posture gains one sentence that names the argument. No fenced example is added, because the gate runs the fences of `README.md`.
- The docstring of `add_mount`. One paragraph after the paragraph on `permissions` and `deny_ops`, and two lines in the failure list. The draft is below.
- The docstring of `_attach_mount`. It says the posture is set after the check of the mount point and before the lock, that the table checks run before the read, just before the write and under the lock, and that once the storage has been asked, written or not, the table and the mount point are checked again.
- The docstring of `_gate_mount_change`. "The caller holds the mount lock" becomes a sentence that is true for both calls: the caller holds the mount lock, or runs no `await` between this check and the reservation of the storage object.
- The docstring of `set_posture`. The sentence "A fresh mount starts at `read_write`" gains "unless `add_mount` set another".
- The docstring of `Mount`. After "Policy lives on the mount and state lives on the storage", one sentence that a posture is state and is not a field.
- The docstrings of the five new functions and methods.

"Posture" has no glossary entry yet. A docstring must not mark it with `:term:`, which would stop `scripts/docs.sh check`. It is defined in the sentence that first uses it.

The draft for `add_mount`:

```
``posture`` is the level that everyone holds at the root of ``storage`` and below, as
:meth:`set_posture` sets it. If ``posture`` is ``None``, the storage is asked nothing and keeps the
posture it holds, and a new storage gives everyone ``read_write``. If ``posture`` is given, it is in
force before the mount can be reached, so no caller meets the mount under another posture. The
kernel sets it as the caller, who must hold ``read_write`` at the root of the storage, as everyone
does in a new storage. It first reads the grants at the root, and writes nothing when everyone
holds ``posture`` there. It writes when the storage holds another level, when it does not declare
``grants``, and when the read fails. The postures set deeper in the storage are kept, and so are
its grants. The mask in ``deny_ops`` and the mount's own ``permissions`` do not stop it. The
caller gets no grant in the storage. After the storage is asked the mount point is checked again.
```

The two lines for the list of `MountError` cases:

```
- ``posture`` is given and ``storage`` declares no ``set_posture`` or lacks the grant methods.
  Nothing has been made.
- The storage refuses the posture, or cannot be reached. The directory stays and the mount is not added.
```

The sentence on `ValueError` gains "when ``posture`` is not a level" and "when another call is mounting the same storage object". The last paragraph gains "If the call fails after the posture was set, the posture stays."

The gates for this change are `scripts/ci.sh` and `scripts/docs.sh check`, since a docstring changes.

## Not checked

- The server engines. Every probe ran on SQLite, in memory or in a file.
- Two processes that add a mount on one new database at the same time. By the storage's design each posture write is serialised and is in force from its commit. It was not run.
- A storage that wraps a remote kernel. None exists in `src/`.
- What posture a storage holds after a call is cancelled while the posture is being written. Test 31 holds that the storage object is freed.
- The design was run as a subclass in a scratch script, with the steps of decision 3 written out. The build is not that code.
- The statement counts are from SQLite. No server engine was counted, and the `UPDATE` count did not grow from 1 row to 511 because one chunk held them all. A storage larger than one chunk was not counted.
- The Unix precedent. It is general knowledge and was not read in source.

## Choices to confirm

Each is a choice this spec made that could reasonably go the other way.

1. **The default is `None`, which keeps today's behaviour.** Alternative: the default is `"none"`, so a mount is closed unless the call says otherwise. Cost: every existing call changes behaviour, on 330 lines in 18 Python test files and three in `README.md`. A stored posture is set back to `none` at every start that does not name one. The rebuild rule of `mounts()` must change. The root still starts open. A second alternative is a default that copies the posture in force at the mount point in the parent. Cost: one more read of the parent for each mount, a write on every existing call, and the same reset of a stored posture.
2. **A posture that is given replaces a stored root posture.** Alternative: it is planted only on a new storage, as the constructor argument of `DatabaseStorage` is. Cost: a new question in the storage protocol, since the kernel cannot tell a new storage from a stored one, and an argument that means two things.
3. **No failure puts a posture back.** Alternative: the earlier posture is read first and written back when the mount is refused. Cost: a second write and a second relabel that can fail too, and on a shared database it can overwrite a posture another process set in between.

## One line

`add_mount(storage, path, posture=...)` sets what everyone holds in the storage, as the caller and under the storage's own rule, after every other check and before the mount enters the table, and with no posture the call does what it does today.
