# Tasks

The work that is outstanding, in one list. A task is removed from this file when it is done. Last updated on 2026-11-21.

## One branch waits to land

Pull requests 10 to 18 landed on `dev` on 2026-11-20, and their branches are deleted.

`a-cancelled-call-leaves-its-storage-intact`, called branch 8 below, has a pull request to `dev`, opened on 2026-11-21. It holds the fix that leaves a SQLite storage whole after a cancelled call, in memory and in a file, the removal of the `session_factory=` constructor, so that a storage always builds and owns its engine, and the glossary term Storage. It was read three times with no summary of the work, and `review-a-cancelled-call-leaves-its-storage-intact.md` beside its spec holds what each reading found. The third reading's verdict is that it lands.

- [ ] **Read the listing rule once in full.** It landed as pull request 13. It has not had a full reading since its fourth round of fixes, only a check that the last two findings were closed.
- [ ] **Run the SQL Server leg.** It could not run on the machine used on 2026-11-19. Every test failed before any statement was sent, because the ODBC driver could not load OpenSSL: `openssl@3` is installed by Homebrew and is not linked, so `/opt/homebrew/lib/libssl.3.dylib` does not exist. `brew link openssl@3` is the usual cure. It changes the machine, so it was not run.
- [ ] **Run the engine legs once on fresh containers.** The procedure recreates the containers before each run. On 2026-11-19 the legs ran against containers that had been up for three days, because taking them down was not permitted in that session.

## Decisions waiting

- [ ] **Whether the three choices of `add_mount(..., posture=...)` stand.** The default is `None`, which keeps the storage's posture, so a call that names no posture still leaves a new mount open. A given posture replaces the posture stored at the storage's root. No failure puts the earlier posture back. The spec in `agents/2026-11-18-add-mount-takes-a-posture/` gives the cost of each alternative.
- [ ] **The four choices of the time limit.** The spec is `spec.md` in `agents/2026-11-18-a-call-that-reaches-several-mounts-bounds-each-mount/`. It was read three times and found fit to build, and it is not built. Its first landing, the cancellation fix, is built on branch 8. The choices, each with its recommendation: a default of 30 seconds, yes; a late call cancelled at its timeout, yes; the addressed storage timed too, no; a late mount marked and probed once in each timeout, yes, as a later landing.
- [ ] **Whether a fault in a mounted storage should raise out of a listing of its parent.** A storage that raises an ordinary exception, and not a transport error, now raises out of `ls`, `tree` and `glob` of the directory its mount is in. That is the kernel's rule for a fault. Before the listing rule, `ls` of the parent did not ask the mounted storage. The other choice is a bare row and a warning, as for a storage that cannot be reached.
- [ ] **Whether `glob` may ask the mounted roots after the storages have answered.** It does since the third round of fixes, which costs one more round trip when a pattern matches a mount point. It is what lets a limit be spent only on rows that are shown, and what keeps a storage from being called after `close()`.
- [ ] **Which feature is next.** Write preconditions, spec 174, is the recommendation. The ranged read and the listing cursor are the others considered.

## Defects found and not fixed

Each was shown by a script that ran, unless it says "read". The review records name the reading that found each one.

### A cancelled call

Branch 8 fixes the two defects that were here, for every SQLite storage. These are what it leaves.

- [ ] **A caller that is cancelled while its attempt waits for a connection is not back until the wait ends.** On a SQLite storage in a file whose pool has no connection free, the attempt is refused when it gets a connection, and its caller is back then. That is the pool's timeout at the latest, 30 seconds unless `pool_timeout` is set in `engine_arguments`. Before branch 8 such a caller was back at once. The same holds for a wait for a turn on an in-memory storage, where it held before as well. A wait in the pool's queue touches no connection, so it could be made to end at the cancellation. A checkout that has begun cannot be.
- [ ] **A cancelled caller under an anyio cancel scope keeps the event loop turning until its attempt ends.** The scope cancels its task again on every turn of the loop, and the wait takes each cancellation and goes on. One statement held for a second took 135,379 cancellations, where a plain asyncio caller sent two. The loop serves other tasks between them. SQLite only.
- [ ] **Cancellation is not run on a server engine.** What a cancelled write has done on Postgres, MariaDB, SQL Server and Oracle is read in driver source. Whether a connection thrown away there can hold a lock, as on a SQLite file, is not known.
- [ ] **What the statistics pass's interrupt does at `close()` is not run against the fix.**
- [ ] **A `tree` that is cancelled can raise a new `CancelledError` with no message.** The kernel's `tree` raises `CancelledError()` of its own where its caller was cancelled, so a canceller that knows its cancellation by its message, as an anyio cancel scope does, does not know this one. Seen in the second reading of branch 8 and not in the third, on three mounts, so it depends on the arrangement of the mounts. Before branch 8.
- [ ] **A rebuild that is cancelled as it claims or releases the index lease leaves the lease held.** The next rebuild is refused as a rival until the lease's five minutes have passed. One cut in 125 on each SQLite host. Before branch 8.
- [ ] **A rebuild's beat is awaited under a `suppress` of `CancelledError`.** `maintenance.py` suppresses it around `await beat`, so a second cancellation of the rebuild's caller that lands there would be swallowed. Read, and before branch 8.
- [ ] **A connection that an application opens on `storage.engine` beside a call costs an in-memory storage its database.** The checkout stamps its settings on the one connection inside the call's transaction, the stamp fails, and SQLAlchemy throws the connection away. The docstring of the property says the engine is for listeners and that no connection is to be opened on it. Nothing prevents it.
- [ ] **A creator on SQLite gives up the closing of a failed statement's cursor.** SQLAlchemy ignores `connect_args` when `engine_arguments` holds `creator` or `async_creator`, so the connections are not `ClosingConnection`. On Python 3.11 that is the open cursor `drivers.py` describes. It is said in the docstring and not refused, and not run on Python 3.11.
- [ ] **One `pool=` given to two storages is not refused.** The two would share connections, and each would put its checkout listener on the pool. Read, and not run.
- [ ] **A wrong engine argument that is found at first touch is answered `unavailable` and retryable.** A synchronous `creator` and `connect_args={"autocommit": True}` were run. A caller that retries on `retryable` never stops. The classifier's default for a failure it does not know is the same before branch 8, and `engine_arguments` makes it reachable.
- [ ] **The synchronous `VirtualFileSystem` and uvloop are not run under cancellation.**
- [ ] **`engine_arguments` is not run on a server engine.** A pool class, `async_creator` and a `do_connect` hook behind a connection pooler are the uses the constructor is for. Only the merge of the arguments is tested, with a SQL Server URL and no server.
- [ ] **A How-to page on putting a time limit on a call.** What a caller may count on after a cancelled call belongs on a page for users, beside the time limit that is its common cause. It is written with the landing of the time limit. `documentation/maintainers/cancellation.md` is the page for people who change VFS.

### Changing a mount

- [ ] **`remove_mount` deletes the mount-point directory after the mount lock is released.** An `add_mount` at the same path that runs between the two can end with a live mount on a deleted directory.
- [ ] **`add_mount` restores a deleted file, or a deleted directory that is not empty, and then refuses the mount.** The restored rows stay.
- [ ] **When `close()` lands during the cleanup of `remove_mount`, the detached storage is neither returned nor closed.**
- [ ] **A mount change asks `holds` outside the one place storage calls go through.** A `close()` that lands between the entry check and that call still calls a closed storage. Read.
- [ ] **Three small ones.** `grants` can be masked with `deny_ops`, though it only reads. `add_mount(storage, path="")` falls back to the storage's name. `require_storage` accepts a storage whose members are not callable.

### Listing at a mount point

- [ ] **A `glob` result can name a mount in its error records when the caller's listing was refused.** A record for a mount that cannot `glob`, and a mounted storage's own refusal, both carry the mount's path. Before the listing rule.
- [ ] **A named root of `glob` that is a mount point is not treated as other mount points are.** Its probe returns the row as the storage gave it, even from a failed answer or with a kind that is not a directory. It is asked twice when one of its ancestors is named too, and two answers that differ merge to a row with no version. The limit does not count a row a probe already supplied.
- [ ] **After a region of a `glob` fails, a row in it can come back.** A stored row for a directory above a mount comes back through the merge, and a named root's probe can put its row back.
- [ ] **A storage applies `max_count` before the kernel drops rows hidden beneath a mount.** A stray row in the parent storage beneath a mount path can cost the caller a visible row. Before the listing rule.
- [ ] **The parent's trash listing loses deleted rows that lie beneath a mount path.** Before the listing rule.
- [ ] **A `glob` can call a storage that `remove_mount` has handed back and whose owner has closed it.** The call in flight holds the storage.
- [ ] **`glob` and `grep` over rows in hand look up a missing fact on the mount table as it is when they ask.** A mount replaced while they wait changes the answer. Before the listing rule.
- [ ] **`locate` and `stat` report a file when a second kernel on the same storage replaced a directory above a mount with a file.** Before the listing rule.
- [ ] **In `tree`, a mount whose holder failed loses its own row, and the rows beneath it are still listed.** A mounted storage whose own `tree` returns its root row gives two rows at the mount point.
- [ ] **`stat` of a missing path beneath a hidden directory above a mount names that directory as the missing part.** `stat` of the directory itself returns a bare row.
- [ ] **`read` of a directory above a mount says `not_found` to a caller who holds nothing on it,** where `stat` shows it and a visible directory gives `wrong_kind`.
- [ ] **`read`, the mutating verbs and `locate` take no hop.** A storage that wraps its own kernel recurses without end on them. `ls` and `stat` now take one. Before the listing rule.

### Search over rows in hand

- [ ] **A row at a storage's own root makes the call fail.** A row at a mount point, the row of `/`, and the row of the trash view's head each reach the storage as a path it turns into a glob, and the call fails with `invalid`. `glob("/*")` on any kernel with a mount returns such a row. `grep` given the same row succeeds.
- [ ] **`search` without `observations` does not expand a brace pattern in the kernel, as `grep` does.** `*.{md,rst}` matches nothing there, and a glob that cannot be parsed is refused once by each mount.
- [ ] **`grep` over a held row in the trash view matches nothing and reports nothing.**

## Cost and structure

- [ ] **Two scans of the mount table grow with a batch.** `_permission_layers` scans it once for each row, 2,000,000 visits for 10,000 rows and 200 mounts, and `MountListing.beneath` once for each named root. Before the listing rule.
- [ ] **`Result.merge` removes repeated errors by searching a growing list.** 200 distinct errors cost 19,900 comparisons, so 10,000 would cost about 50,000,000. Before the listing rule.
- [ ] **A storage searches 10,000 rows in hand close to its time budget.** 8 to 9 seconds against 10, on SQLite in memory, measured once by the clock.
- [ ] **A storage builds every `glob` candidate before it applies the limit.** Before the listing rule.
- [ ] **Every mounted root in a listing is asked at once.** With 200 database mounts, one `ls` opens 200 transactions together. Read.
- [ ] **The cost of a listing over mounts is measured on a server engine.** It is counted in calls and not measured.
- [ ] **A SQLite storage stamps its session settings at every checkout.** A probe for the vector function and six `PRAGMA` statements are sent each time a connection leaves the pool, which is 7 of the 9 statements of a `stat` on an in-memory storage. Settings that last for the life of a connection could be sent once, when it is made.
- [ ] **Several storages on one database each build an engine and a pool.** One mount for each schema of one database is a supported shape, and each such mount holds its own pool. An engine that VFS builds once and several storages share would hold one. `agents/2026-11-21-a-storage-always-owns-its-sessions/research.md` names it as the later step.
- [ ] **The engine host's attribute `session_factory` keeps the name of the removed constructor argument, and `EngineHost.engine` can be assigned to.** About 270 uses in the tests read the first. `DatabaseStorage.engine` is a read-only property, and the host's is a plain attribute.
- [ ] **`gather_settled` and `PathFilters` live in `vfs.listing`.** Three readings said they belong in a module that is not about listings, since writes and searches use them too.
- [ ] **The tests of `vfs.listing` are in `tests/base/test_mount_listing.py`.** The new module has no test file of its own name.

## Words and names

- [ ] **The docstrings of 16 source files follow the docstring rules.** About 265 of 311 break a rule in `documentation/maintainers/how-we-write-docstrings.md`, and about 170 public members have none. The largest files are `rights.py`, `paths.py`, `backend.py`, `labels.py`, `ranking.py` and `sync.py`. The words "router", "bind path", "bind point" and "bind site" remain in them, and in `fanout.py` and `pattern_matching/glob.py`.
- [ ] **"Storage backend" gives way to the term Storage.** Storage is a glossary term since 2026-11-20, with `StorageBackend` as its type. Eleven places in four pages under `documentation/` still say "storage backend" and link nothing, and nine docstrings under `src/vfs/` say it with no `:term:` marker. The example line in `how-we-document.md` is one of the eleven.
- [ ] **Seven words used in docstrings get a glossary entry.** They are gate, capability, permission map, posture, authority, trash view and mount point.
- [ ] **`documentation/maintainers/mounts.md` is bullet points for the greater part.** 36 of its 48 lines are list items. `how-we-document.md` says a page is written as prose, with a list only for things that are a list.
- [ ] **"Attempt" may be a glossary term.** It has a specific meaning in VFS, one try of one call's transaction, and `documentation/maintainers/cancellation.md` and the docstrings of `attempts.py` use it in that sense.
- [ ] **Comment blocks in `dialects.py` and `engine.py` run to more than two lines.** The working agreement allows two. Before branch 8.
- [ ] **Two test names overclaim or use an old word.** `test_update_mount_is_refused_where_removing_and_adding_the_mount_would_be` claims more than `update_mount` does. `test_unmount_and_remount_pass_under_a_rule_beneath_the_site` keeps "remount", because documents under `context/` cite it by name.
- [ ] **A refusal in `update_mount` has an em dash in its message.** "Mount at … changed while it was being updated — retry".
- [ ] **The docs export follows an alias of a type variable.** It now tells a type variable by what the value is, and it does not follow `T = U` or a renamed constructor.

## Tests that fail now and then

- [ ] **Four database storage tests fail under load and pass alone.** `test_two_writers_crossing_together_analyze_once` in `test_statistics.py`, `test_every_scope_statement_fits_the_budget` and `test_contract_scale_pattern_batch_chunks_within_budget[10k]` in `test_reads.py`, and `test_scope_channel_searches_as_composition[composed]` in the storage contract. Seen three times on 2026-11-19 and once on 2026-11-20, each time while other work shared the machine. On 2026-11-20 the load was 34 on 10 cores and the suite took ten minutes in place of four. The two-writers test needs a write of 30,000 files to end inside the 20 seconds its rival waits for the lock, over four attempts of five seconds. The two in `test_reads.py` returned no row where one was expected, which is what a `glob` gives when its stage reaches its time budget. The cause of the fourth was not found. A test that can fail on a slow machine is a test of the clock, which the working agreement forbids. `scripts/ci.sh` passes when it runs alone.
- [ ] **The test of the lease's beat gives up after 100,000 turns of the loop.** `test_the_beat_keeps_ticking_through_a_slow_batch` in `test_embed.py` waits for five beats of a timer by yielding to the loop, at most 100,000 times. Under load it ran out of turns in 2 of 38 runs before branch 8 and in 1 of 38 on it. It is a test of the clock.
- [ ] **No test pins `expire_on_commit=False` on a storage's sessions.** A build without it passed the six test files of the cancellation branch.
- [ ] **A test of the trash failed once under the slower tracer.** `test_a_create_whose_snapshot_predates_the_parents_delete_refuses` in `test_trash.py` failed once in a run with branch coverage on, which forces the slower tracer on Python 3.13, and passed in two plain runs of the suite and three times alone.
- [ ] **A worker thread of aiosqlite was seen to end after its event loop had closed.** One `PytestUnhandledThreadExceptionWarning`, seen in two of the runs of the suite under coverage on branch 8 and in no plain run. It was reported during a test that opens no connection, so an earlier test in the same worker left the thread.
- [ ] **The ranking pin failed once on Postgres in CI.** `TestPostgresRankingPin::test_ordered_top10_matches_the_pin` failed on pull request 18 on 2026-11-20 with a bare `AssertionError`, and passed when that one job was run again. It passed on the Postgres leg of pull requests 11 to 17 the same day and on a laptop. The assertion compares two lists and prints neither, so the difference was not seen. The cause is not known.
- [ ] **Other tests of the docs site may act before the page's scripts have started.** The back-to-top test did, and now waits for the theme toggle to say it is ready. The drawer test on a phone and the test that the menu for scripts off is gone both need scripts and do not wait. Neither has been seen to fail.
- [ ] **`scripts/docs.sh check` fails to start when port 4173 is in use.** Seen once.
