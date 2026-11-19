# Mature systems wait without limit by default, bound a member only for reads, and never promise that the member stopped

This memo answers one question, asked on 2026-11-18: how do mature systems bound a slow or dead member when one call reaches several, and what should VFS take from them. It was written in one sitting on 2026-11-18. Source was read in eight local clones and five installed driver packages, public documentation was read on the web, and five experiments were run on SQLite. The specs that stand on it are `spec.md` and `spec-a-cancelled-call-leaves-its-storage-intact.md` in this directory. A memo decides nothing; a spec decides. The memo was corrected the same day after two reviews, and five more experiments were run. Section 8 lists what changed.

Every claim carries a label. EXECUTED means a command ran here and the claim reports its output. READ means the claim was seen in a file or page that is cited. INFERRED means reasoning from the two.

## The answer in one paragraph

Almost every mature system waits for a member without limit unless it is told otherwise. Where a bound exists, it is a setting on the member, made when the member is attached. It applies to reads, and its documented cost falls on writes. A read that loses a member returns the other members' rows with a record that names what is missing. A write is never cut that way. No system treats the bound as proof that the member stopped: the bound is the waiter's decision, and the member may run on or may already have finished. Almost every system that bounds a member also tells it to stop, and NFS `soft` is the one that does not. In Python on SQLAlchemy, a cancelled call is not stopped cleanly. On SQLite the statement runs to its end and the connection is thrown away. A database that lives inside that one connection, which is the in-memory storage, is lost with it. A database in a file keeps its data. A caller that awaits the cancelled call waits for the statement, and a caller that cancels and does not wait is back at once.

## Sources

VFS at `0d05c606` on branch `a-mount-is-listed-as-a-directory-is`, read on 2026-11-18.

| Clone | Commit | Date | Licence | State |
|---|---|---|---|---|
| `linux` | `faeab1661` | 2026-04-18 | GPL-2.0 | Not refreshed: the working tree is dirty in 13 files. Read as it stood. |
| `9front` | `a0806493` | 2026-10-15 | MIT | Not refreshed: dirty in 5 files. Read as it stood. |
| `plan9` | `ed1a9c21e` | 2025-10-28 | MIT | Not refreshed: dirty in 5 files. Read as it stood. |
| `freebsd-src` | `d1e14cba4a` | 2026-11-18 | BSD, by file headers | Refreshed to `origin/main`. Sparse: only `sys/` and `share/`. |
| `libfuse` | `6a484ac67f` | 2026-11-18 | LGPL-2.1 and GPL-2 | Refreshed to `origin/master`. |
| `postgres` | `ba11c48390` | 2026-11-19 | PostgreSQL licence | Refreshed to `origin/master`. |
| `grpc-go` | `70d9d2ff79` | 2026-11-18 | Apache-2.0 | Refreshed to `origin/master`. |
| `cpython` | `6c9f2b691a` | 2026-11-19 | PSF-2.0 | Refreshed to `origin/main`. |
| `sqlalchemy` | `6f924b05d7` | 2026-11-16 | MIT | Refreshed to `origin/main`. Not cited: the installed 2.0.52 is what runs. |

Installed packages, read in the project's environment: sqlalchemy 2.0.52, aiosqlite 0.22.1, asyncpg 0.31.0, aiomysql 0.3.2, aioodbc 0.5.0 with pyodbc 5.3.0, oracledb 4.0.2 (compiled, so its upstream source was read on the web). Python 3.13.11, SQLite 3.50.4. A package path below is relative to the package, such as `engine/base.py` in sqlalchemy.

Web pages were read on 2026-11-18. Each is cited where it is used.

No code was copied from any clone or package. The experiment scripts are kept in the session scratch directory, outside the repository, and are not durable. Each experiment is described closely enough to be written again.

## 1. Kernels with mounts

### 1.1 Linux NFS

- READ. `hard` is the default and has no bound: "NFS requests are retried indefinitely." <https://man7.org/linux/man-pages/man5/nfs.5.html>
- READ. `soft` and `softerr` are mount options. They become flags on every RPC task. `linux/fs/nfs/fs_context.c:616-628`, `linux/fs/nfs/client.c:651-655`, `linux/net/sunrpc/clnt.c:1184-1187`.
- READ. At a major timeout a soft task fails with `EIO`, a `softerr` task fails with `ETIMEDOUT`, and a hard task logs "not responding, still trying" and goes on. `linux/net/sunrpc/clnt.c:2519-2568` (`rpc_check_timeout`).
- READ. The defaults on TCP are `timeo` 600 tenths of a second and `retrans` 2. `linux/include/uapi/linux/nfs_fs.h:16-19`.
- INFERRED. The default time to a major timeout on TCP is 60 s plus 2 more of 60 s, which is 180 s. `linux/net/sunrpc/xprt.c:654-666`.
- READ. `intr` is ignored. `linux/fs/nfs/fs_context.c:179-180`, and nfs(5): "It is ignored after kernel 2.6.25."
- READ. A waiting process sleeps killable. Only a fatal signal ends the wait. `linux/net/sunrpc/sched.c:277-283`, `985-988`.
- READ. The cost of `soft` is stated for writes: "A so-called 'soft' timeout can cause silent data corruption in certain cases. As such, use the soft or softerr option only when client responsiveness is more important than data integrity." nfs(5), same page.
- READ. With `softreval`, an attribute check that times out falls back to the cached attributes and returns no error. `linux/fs/nfs/inode.c:1411-1415`.
- READ. On NFSv4 a soft request that has been sent is not cut by time at all. It times out "only if the transport connection gets terminally broken". `linux/net/sunrpc/clnt.c:2536-2545`. The socket is given keepalive and a user timeout taken from `timeo`. `linux/net/sunrpc/xprtsock.c:2280-2307`.
- INFERRED. NFSv4 judges a server dead by its connection, not by how long one request has run. A fixed time cannot tell a slow request from a dead server.

### 1.2 Linux: a listing, a `stat` and `df` at a dead mount

- READ. `getdents` reads only the directory that was opened. `linux/fs/readdir.c:87-115`, `384-398`. The file holds no mount lookup.
- INFERRED. A listing of names in the parent never waits on the mounted file system. This is why `ls /mnt` returns while `ls -l /mnt` hangs.
- READ. A path walk that ends on a mount point moves to the mounted root, and `stat` calls that file system. `linux/fs/namei.c:1590-1606`, `linux/fs/stat.c:210-213`, `254-262`.
- READ. On NFS that call sends a request when the cached attributes have expired. `linux/fs/nfs/inode.c:1040-1065`.
- READ. One flag skips the wait for a single call. With `AT_STATX_DONT_SYNC`, NFS answers from its cache and sends nothing. `linux/fs/nfs/inode.c:1004-1008`. statx(2): "on a network filesystem, it may not involve a round trip to the server". <https://man7.org/linux/man-pages/man2/statx.2.html>
- READ. `statfs`, which `df` calls, always sends a request on NFS. `linux/fs/nfs/super.c:246-259`.
- INFERRED. On a dead hard mount, `stat` after the cache expires and `df` both block without limit. On a soft mount they return `EIO` or `ETIMEDOUT`.

### 1.3 autofs

- READ. The kernel has no time limit on a mount request. The process sleeps killable until the daemon answers. `linux/fs/autofs/waitq.c:440`.
- READ. A dead daemon is noticed only when a write to its pipe fails. The mount then goes "catatonic" and every later waiter gets `ENOENT` at once. `linux/fs/autofs/waitq.c:15-35`, `164-175`.
- READ. The kernel's `timeout` is idle expiry, not a bound on a request. `linux/fs/autofs/expire.c:22`.
- READ. `stat` does not trigger a mount, so a listing does not mount everything. `linux/fs/namei.c:1548-1551`, `linux/fs/stat.c:373`. statx(2) gives the reason: "to prevent mass-automounting".

### 1.4 FUSE

- READ. The default is no bound. The two sysctls default to 0. `linux/Documentation/admin-guide/sysctl/fs.rst:351-369`, `linux/fs/fuse/inode.c:1322-1325`.
- READ. A bound, when set, is for the whole connection and is at least 15 s. When the oldest request expires, the connection is aborted. `linux/fs/fuse/dev.c:73-127`, `linux/fs/fuse/inode.c:1337`. libfuse says the same: "the connection will be aborted by the kernel." `libfuse/include/fuse_common.h:782-787`.
- READ. An abort ends every waiting request with `ECONNABORTED`, and later requests get `ENOTCONN`. `linux/fs/fuse/dev.c:217-219`, `2411-2422`, `2457-2529`.
- READ. A signal does not end the wait. It sends an interrupt message, and the server "may ignore the INTERRUPT requests entirely". `linux/fs/fuse/dev.c:544-591`, `linux/Documentation/filesystems/fuse/fuse.rst:148-171`.

### 1.5 FreeBSD NFS

- READ. Hard is the default. `soft` and `intr` are opt-in. `freebsd-src/sys/fs/nfsclient/nfs_clvfsops.c:1017-1028`.
- READ. `soft` becomes a retry count, and without it the count is `INT_MAX`. `freebsd-src/sys/fs/nfs/nfs_commonkrpc.c:398-410`. A timeout returns `ETIMEDOUT`. `nfs_commonkrpc.c:1071-1114`.
- READ. The way out of a dead server is a forced unmount, which cancels every request. umount(8) says it "may throw away data not yet written". `nfs_clvfsops.c:1994-2003`, <https://man.freebsd.org/cgi/man.cgi?query=umount&sektion=8>

### 1.6 Plan 9 and 9P

- READ. The mount driver has no timeout. It writes the request and sleeps until a reply. `9front/sys/src/9/port/devmnt.c:1099-1178`. The file's one timed sleep is a read-ahead worker, `devmnt.c:867`.
- READ. A note sends a `Tflush` and the process goes back to waiting. `devmnt.c:1104-1120`.
- READ. `Tflush` does not promise the work stopped. "The server may respond to the pending request before responding to the Tflush." The client "must wait to receive the corresponding Rflush". A reply that arrives first must be honoured "since the completed request may signify a state change in the server." `9front/sys/man/5/flush:49-51`, `74-83`.
- READ. A directory read calls `stat` on what is mounted at each entry. `9front/sys/src/9/port/sysfile.c:557-650`, the call at `:600`.
- READ. When that `stat` fails, the covered entry is kept. `sysfile.c:593-594`.
- INFERRED. That `stat` has no bound. So a hung file server blocks the listing of the directory above it. This is the case VFS has today, and Plan 9 has no answer to it. A server that fails or hangs up costs nothing.
- READ. A union directory skips a member that fails: "Error causes component of union to be skipped". `sysfile.c:360-369`.

## 2. Systems that fan one query out and merge

### 2.1 Elasticsearch

- READ. There is no default bound: "By default, search requests don't time out." <https://www.elastic.co/guide/en/elasticsearch/reference/8.18/search-your-data.html>
- READ. The request `timeout` is for each shard. At the bound "Elasticsearch uses only the hits accumulated up to that point", and the response says `timed_out: true`. Same page.
- READ. `allow_partial_search_results` defaults to true and covers "shard request timeouts or shard failures". With false, the search fails. <https://www.elastic.co/guide/en/elasticsearch/reference/8.18/search-search.html>
- READ. The response names what is missing: `_shards.failed`, and a `failures` list that names each shard. For remote clusters, `_clusters.details` gives a status for each. <https://www.elastic.co/guide/en/elasticsearch/reference/8.18/modules-cross-cluster-search.html>
- READ. `skip_unavailable` is set for each remote cluster. Its default became true in 8.15. A search fails only when a cluster marked false is unavailable. Same page.
- READ. A cancelled task "may continue to run for some time after it has been cancelled". <https://www.elastic.co/guide/en/elasticsearch/reference/8.18/tasks.html>
- READ. Writes have no such mode. The `timeout` of a write waits for shards to be ready, and a bulk request reports each item. <https://www.elastic.co/guide/en/elasticsearch/reference/8.18/docs-bulk.html>
- READ. The pages disagree on one point. The API page says a search past its `timeout` "fails and returns an error". The guide says partial hits. The guide is followed here.

### 2.2 Thanos

- READ. `--store.response-timeout` is off by default. When set, "a Store will be ignored and partial data will be returned". <https://thanos.io/tip/components/query.md/>
- READ. Partial response is on by default and can be set for each request. A missing store "will not cause query to fail, but instead return warning". The caller gets a `warnings` list with HTTP 200. Same page.
- READ. The whole query has its own bound, `--query.timeout`, 2 minutes. The store bound is meant to be set tighter than it. Same page.

### 2.3 Vitess, Citus, Trino and `postgres_fdw`

- READ. Vitess fails a scatter query when any shard fails. `SCATTER_ERRORS_AS_WARNINGS` opts one query into "returning the partial results from the healthy shards". <https://vitess.io/docs/23.0/user-guides/configuration-advanced/comment-directives/>
- READ. Vitess kills a query at the tablet after 30 s by default. `QUERY_TIMEOUT_MS` "Only works for SELECT (read) queries." Same page and <https://vitess.io/docs/24.0/reference/programs/vttablet/>
- READ. Citus bounds only the connect, at 30 s. A worker that cannot be reached fails the query. <https://docs.citusdata.com/en/stable/develop/api_guc.html>
- READ. Trino has no partial answer. Its only bounds are for the whole query, and they default to 100 days. <https://trino.io/docs/current/admin/properties-query-management.html>
- READ. `postgres_fdw` has no timeout of its own for a remote statement. `postgres/src/include/libpq/libpq-be-fe-helpers.h:415-450`. A local `statement_timeout` bounds it, and that is off by default. `postgres/doc/src/sgml/config.sgml:10845-10850`.
- READ. `postgres_fdw` bounds the cancel, not the query. It sends a cancel, sends it again after 1 s, and waits at most 30 s. `postgres/contrib/postgres_fdw/connection.c:106`, `113`, `1623-1645`, `1821-1916`.
- READ. A connection that did not confirm the cancel is thrown away. `connection.c:1571-1607`, `1926-1989`.
- READ. Remote writes commit one server at a time, with no two-phase commit. `connection.c:1255-1276`, `postgres/doc/src/sgml/postgres-fdw.sgml:1166-1169`.

### 2.4 gRPC

- READ. A deadline is "a point in time past which a client is unwilling to wait". There is none by default. <https://grpc.io/docs/guides/deadlines/>
- READ. It crosses a hop as the time that is left: "gRPC converts the deadline to a timeout from which the already elapsed time is already deducted". Same page. In source, the client sends `grpc-timeout` computed from the absolute deadline, `grpc-go/internal/transport/http2_client.go:633-640`, and the server rebuilds a deadline from it, `grpc-go/internal/transport/http2_server.go:452-457`, `535-536`.
- READ. A call whose deadline has already passed is refused before it is sent. `http2_client.go:633-640`.
- READ. Both sides signal the handler to stop at the deadline. The client resets the stream with a cancel code. `grpc-go/internal/transport/client_stream.go:99-110`. The server sets a timer of its own from the deadline and closes the stream with a cancel code when it fires, which cancels the handler's context. `grpc-go/internal/transport/http2_server.go:600-609`.
- READ. The signal is not a stop. "The server application is responsible for stopping any activity it has spawned". <https://grpc.io/docs/guides/deadlines/> The two sides "make independent and local determinations of the success of the call, and their conclusions may not match", and "Changes made before a cancellation are not rolled back." <https://grpc.io/docs/what-is-grpc/core-concepts/>
- READ. A call is refused at once when the channel's connection is known to be down: "without Wait-for-Ready it will immediately return a failure." <https://grpc.io/docs/guides/wait-for-ready/> In source the refusal comes from the picker, which follows the connectivity state, and it is answered with `Unavailable`. `grpc-go/picker_wrapper.go:156-176`.
- READ. A call that ran out its deadline does not make later calls fail fast. Nothing in the picker reads a deadline. Same lines.
- READ. A connection is judged dead by a small exchange, not by a real call. A keepalive ping that gets no acknowledgement within its timeout closes the connection. `grpc-go/internal/transport/http2_client.go:1812-1843`. The ping is off by default and its timeout is 20 s. `grpc-go/internal/transport/defaults.go:31-33`. Reconnection is tried again after a delay that starts at 1 s and grows to 120 s. `grpc-go/backoff/backoff.go:47-52`.

## 3. Cancellation in Python

### 3.1 What asyncio does

- READ. `asyncio.wait_for` cancels the call at the timeout and raises `TimeoutError`. It is `asyncio.timeout` around an `await`. `cpython/Lib/asyncio/tasks.py:452-500`, `cpython/Lib/asyncio/timeouts.py:96-118`.
- INFERRED. The caller gets `TimeoutError` only after the cancelled call has finished unwinding. A call that cannot be interrupted holds the caller past the timeout. This is true of a caller that awaits the cancelled call, as `wait_for` does. A caller that cancels a task and does not await it is not held.
- READ. A cancelled `gather` cancels its children and finishes when all of them have. `cpython/Lib/asyncio/tasks.py:773-798`, `879-906`.
- READ. The event loop keeps only weak references to tasks. A task that is left running must be held somewhere. `cpython/Doc/library/asyncio-task.rst:276`.

### 3.2 What SQLAlchemy does with a cancellation

- READ. SQLAlchemy counts `CancelledError` and `asyncio.TimeoutError` as exit exceptions. sqlalchemy `util/_concurrency_py3k.py:61-66`.
- READ. An exit exception inside a statement marks the connection as disconnected and invalidates it. sqlalchemy `engine/base.py:2246-2259`, `2369-2378`.
- READ. Invalidating first tries a graceful close, shielded from the cancellation. sqlalchemy `connectors/asyncio.py:397-414`.
- READ. Closing a session is shielded, so a cancellation that lands there does not interrupt it. sqlalchemy `ext/asyncio/session.py:1068-1070`.

### 3.3 Each driver

| Driver | What a cancelled `await` does | Does the statement run on? | The connection |
|---|---|---|---|
| aiosqlite 0.22.1 | READ. Only the waiting future is cancelled. The function is already queued to the connection's worker thread, which runs it to its end. `core.py:48-76`, `150-160`. | EXECUTED. Yes, always. | EXECUTED. Invalidated and closed. The close queues behind the statement, so the caller waits for the statement anyway. |
| asyncpg 0.31.0 | READ. A cancelled waiter makes the driver send a cancel request on a side connection. `protocol/protocol.pyx:642-684`, `connection.py:1681-1682`. | INFERRED. It stops if the request reaches the server in time. Not executed. | READ. Invalidated: a graceful close with a 2 s limit, then a hard close. sqlalchemy `dialects/postgresql/asyncpg.py:910-917`. |
| aiomysql 0.3.2 | READ. A cancellation while a packet is read closes the socket. No `KILL` is sent. `connection.py:336-341`, `610-612`, `636-638`, `1116-1118`. | INFERRED. Yes, until the server next writes to the closed socket. Not executed. | READ. Closed by the driver. |
| aioodbc 0.5.0 | READ. Each call runs on a thread pool. `connection.py:65-69`. | INFERRED. Yes. A thread cannot be cancelled. Not executed. | READ. The dialect declares no hard close, so the close goes through the same thread pool. Whether it waits behind the statement was not checked. |
| oracledb 4.0.2 | READ, in the upstream source, through a fetch that summarises: any exception during a message, a cancellation included, sends a break marker and waits for the server's reset, with no time limit of its own. <https://raw.githubusercontent.com/oracle/python-oracledb/main/src/oracledb/impl/thin/protocol.pyx> | INFERRED. It stops if the server answers the break. Not executed. | INFERRED. SQLAlchemy still invalidates it. |

### 3.4 The experiments on SQLite

The method is the same in each. One driver round trip is one function queued to aiosqlite's worker thread. The experiment patches aiosqlite's queueing function so that one chosen round trip sleeps 0.30 s on the worker thread before it runs. That stands in for a slow server. The caller gives up after 0.08 s. The storage holds one file, `/a.txt`, with the content `old`. The calls run as the system actor. A laptop on macOS ran them, and no time below is a measure of anything but order.

**Experiment 1: cancel a read on the in-memory storage.** `asyncio.wait_for(fs.stat("/"), 0.08)`, with the `SELECT` slowed.

- EXECUTED. The caller got `TimeoutError` after 0.31 s, not 0.08 s. It waited for the statement.
- EXECUTED. One connection was invalidated and one new connection was opened.
- EXECUTED. The next `read("/a.txt")` failed with `vfs.unavailable: read failed: no such table: vfs_entries`.
- EXECUTED. The next `write` succeeded, on a new empty database. `read("/a.txt")` then returned `not_found`, and `ls("/")` listed only the new file.
- INFERRED. An in-memory SQLite database lives inside its one connection. `src/vfs/storage/backends/database/engine.py:1145-1151` says so. SQLAlchemy throws that connection away when a call is cancelled inside a statement. The database goes with it.

**Experiment 2: cancel at every round trip.** The same cut was made at each driver round trip of `stat("/")`, `read` and `write` on the in-memory storage.

- EXECUTED. `stat` and `read` are 34 round trips each. A cut at 32 of the 34 lost the database. The two safe cuts are the rollbacks at session close, which SQLAlchemy shields.
- EXECUTED. `write` is 81 round trips. A cut at any of the 81 lost the database, the commit included.

**Experiment 3: cancel a write on a file database.** The cut was made at each of the 17 statements from `BEGIN IMMEDIATE` to the end of `write(path="/a.txt", content="new")`.

- EXECUTED. A cut at any of the 15 statements before the commit left `old`. The transaction was rolled back.
- EXECUTED. A cut at the commit, or at the statement after it, left `new`. The caller was told the call was cancelled, and the write had landed.
- EXECUTED. In every case the caller waited 0.30 to 0.34 s for a 0.08 s limit, and one connection was invalidated.
- EXECUTED. No data was lost at any cut. The file database lost one connection and kept every row. The loss in experiments 1 and 2 belongs to a database that lives in one connection.

**Experiment 4: leave the call running.** The same cuts, with `asyncio.wait` and no cancellation. The call was left to finish.

- EXECUTED. The caller was back after 0.08 s in every case.
- EXECUTED. The late call ended with success. No connection was invalidated. The in-memory database was intact.
- EXECUTED. A late `write` landed: the content was `new` at every cut. A late `stat` changed nothing.

**Experiment 5: the pool under calls that were left running.** A file database, with every `stat` slowed to 2.0 s inside its statement.

- EXECUTED. The pool is `AsyncAdaptedQueuePool` with 5 connections, 10 more on overflow, and a 30 s wait for a connection.
- EXECUTED. With 5 calls left running, 5 connections were out and the next `stat` waited 0.00 s.
- EXECUTED. With 15 calls left running, 15 connections were out and the next `stat` waited 1.84 s, until one of the 15 ended.
- INFERRED. Calls that are left running on a storage that never answers use up its pool. The sixteenth call then waits 30 s for a connection it will not get.

### 3.5 Why the in-memory database is lost, and two spikes of a fix

These were run after the review, on the kernel as it is at `0d05c606`.

**Experiment 6: who throws the connection away.** A listener on the pool's `invalidate` event recorded the exception and the SQLAlchemy functions on the stack. The cut was made at four places.

| Cut at | Invalidated through | Database |
|---|---|---|
| A session setting stamped at checkout | `_checkout`, `_checkin_failed`, `invalidate` | Lost |
| The transaction's `SELECT` | `_exec_single_context`, `_handle_dbapi_exception`, `invalidate` | Lost |
| The commit of a write | `_commit_impl`, `_handle_dbapi_exception`, `invalidate` | Lost |
| The pool's rollback as a write's connection is returned | `_checkin`, `_finalize_fairy`, `invalidate` | Lost |
| The rollback at the close of a read's session, which SQLAlchemy shields | Not invalidated | Kept |

- EXECUTED. In every lost case the exception was `CancelledError`, one new connection was opened, and the `sqlite3` connection afterwards was a different object.
- READ. The three paths are SQLAlchemy's own. A cancellation inside a statement or a commit is an exit exception and invalidates: sqlalchemy `engine/base.py:2246-2259`, `2369-2378`. Any exception while a connection is checked out, a listener's included, invalidates: sqlalchemy `pool/base.py:743-749`, `1369-1376`. Any exception while a returned connection is reset invalidates: sqlalchemy `pool/base.py:1007-1012`.
- READ. VFS stamps its session settings in a `checkout` listener, on every checkout. `src/vfs/storage/backends/database/engine.py:1021-1031`. That is 26 of the 34 driver round trips of a `stat`.
- EXECUTED. The host's ready latch was true before the next call and false after it. The new connection drops the latch when it connects, `engine.py:1145-1160`. The call in hand has already passed the latch, so it runs on an empty database and fails with `no such table`. The call after it provisions an empty schema.
- READ. The engine knows the hazard for its own work. It does not replace a stale connection of an in-memory database, because "replacing the last connection to any in-memory database drops it". `engine.py:747-752`, `834`. Nothing guards a verb against SQLAlchemy doing the same.
- INFERRED. The cause is established. SQLAlchemy treats a connection that was cancelled in mid-use as unusable and replaces it, which is sound for a pooled connection to a server. VFS lets a caller's cancellation reach a connection that is the database.

**Experiment 7: a statement that runs long for real.** A recursive count that takes 6.7 s was run on the worker thread at one round trip, and the caller gave up after 0.2 s. Two spikes patched `EngineHost.with_retry` in the experiment so that the unit of work ran in a task of its own, shielded from the caller's cancellation. One waited for the unit to end. One called `sqlite3`'s interrupt every millisecond until it ended.

| | Caller back after | `stat` cut at its `SELECT` | `write` cut at its `UPDATE` |
|---|---|---|---|
| Today | 6.73 s | Database lost | Database lost |
| Shielded, waited out | 6.77 s | Intact | Intact, and the write landed |
| Shielded, interrupted | 0.20 s | Intact | Intact, and the write was rolled back |

**Experiment 8: the two spikes at every round trip.** The cut of experiment 2 was repeated under each spike.

- EXECUTED. Waited out: 34 of 34 cuts of `stat` and 81 of 81 cuts of `write` kept the database. No connection was invalidated. Every cancelled write had landed.
- EXECUTED. Interrupted: 8 of 81 cuts of `write` lost the database. All 8 were cuts in the session settings stamped at checkout. The interrupt made a setting fail with an ordinary error, and the pool invalidates on any error there. The sweep of `stat` lost the database at its first cut and then stopped answering, which was not diagnosed.
- INFERRED. An interrupt is safe only while the transaction's own statements run. In the checkout and in the reset it loses the database by the same door the cancellation uses.

**Experiment 9: a second connection that keeps the database alive.** Run after the second review, which proposed it and showed with plain `sqlite3` that a named in-memory database outlives its working connection while another connection holds it. `InMemoryStorage` was built as VFS builds it, except that the engine's URL named a shared in-memory database and one plain `sqlite3` connection to the same name was opened beside it and never used. The pool was kept as the `StaticPool`. In both forms the session factory was `_SerializedSessions` and the host read `in_memory` as true, as today, and the calls were 34 and 81 round trips, as today. Two forms were run: SQLite's shared cache, `file:NAME?mode=memory&cache=shared`, and SQLite's `memdb` file system, `file:/NAME?vfs=memdb`.

| | Shared cache | `memdb` |
|---|---|---|
| `stat`, 34 cuts | 34 kept every row. 32 cost one connection, 2 cost none. | The same. |
| `write`, 81 cuts | 81 kept every row. 73 cuts before the commit left `old`, and 2 at or after it left `new`, with the next calls working. After the other 6 cuts before the commit, the next read and write were refused: `database table is locked: vfs_entries`. | No answer in 20 s to the read after the cut at round trip 29, the first inside the transaction. The sweep stopped there. |
| The cuts between `BEGIN` and the commit, run again | 4 of 53 were refused. All 4 were cuts in a statement that returns rows. Each answered again, with `old`, after `gc.collect()`. | Not run. |
| A call cancelled and not awaited, then a read, a write and an `ls` at once | After a `stat`: the write was refused, `database table is locked`. After a `write`: all answered. | After a `stat`: the write was refused, `first touch kept losing to concurrent changes`, four more connections were invalidated at checkout, and `ls` returned no rows. After a `write`: all answered. |
| The 6.7 s statement | Caller back when the statement ended. Database kept, and the write rolled back. | The same. |

- EXECUTED. No row was lost at any cut in either form.
- INFERRED. The refusals come from the old connection. SQLite keeps a connection open while a statement of it is still referenced, and the cancelled call's cursor is referenced until Python collects it. Until then the old connection holds its transaction and its locks, and an in-memory database has no write-ahead log, so a reader and a writer on two connections block each other. That the refusals ended at `gc.collect()` fits this. It was not traced in SQLite.

**Experiment 10: the shield, with a mark.** The patch of experiment 8 was changed in three ways. The caller waits on the unit's task and catches each cancellation, marking the unit. A `before_commit` listener on the session refuses the commit of a marked unit. And a unit that is already marked when it gets the host's lock gives the lock back and ends.

- EXECUTED. `stat`, 34 cuts: 34 kept the database, with no connection invalidated.
- EXECUTED. `write`, 81 cuts: 81 kept the database, with no connection invalidated. The 79 cuts before the commit left `old`. The 2 cuts at the commit or after left `new`. That is the split a file database gave in experiment 3.
- EXECUTED. The listener fired at the release of a savepoint as well as at the commit, so a marked write stopped at whichever came first.
- EXECUTED. A `write` cancelled while it waited behind a slow `stat` sent no statement. The `stat` ended with success, and the content was `old`.
- EXECUTED. A caller cancelled twice, 10 ms apart, was still waiting after each, and raised one `CancelledError` when the unit ended.
- EXECUTED. A `stat` and a `write` cancelled and not awaited were each followed at once by a read, a write and an `ls`. All answered.
- EXECUTED. With the 6.7 s statement the caller was back when the statement ended, the database was kept, and the write was rolled back.

### 3.6 What a timeout does to the promise of `gather_settled`

- READ. `gather_settled` waits for every call before it raises a fault. Its docstring gives the reason: "A batch can then never go on changing things behind a caller who has already seen a failure". `src/vfs/mounts.py:244-264`.
- INFERRED. A timeout that cancels keeps the letter of the promise on the client: `wait_for` returns only when the call has unwound. It does not keep it on the server. Experiment 3 shows a write that landed after the caller was told it was cancelled, and section 3.3 shows two drivers, aiomysql and aioodbc, that do not tell the server to stop.
- INFERRED. A timeout that leaves the call running breaks the promise outright for a write. Experiment 4 shows the write landing after the caller has returned.
- INFERRED. The promise is about changes. A read changes nothing, so a read that is cancelled or left running breaks nothing. A bound on reads is compatible with the promise. A bound on writes is not, whichever way it is built.
- READ. A read that is left running is not free. A read runs at `REPEATABLE READ` on Postgres and MariaDB, `src/vfs/storage/backends/database/dialects.py:534`, `605`, so it holds a snapshot as well as a connection for as long as it runs.
- READ. `tree` has no stage budget. `tree_rows`, `src/vfs/storage/backends/database/reads.py:241-316`, takes no `Deadline`. Its time grows with the subtree. `glob`, `grep` and `search` each take one.

## 4. What VFS has today

### 4.1 Every bound on time or hops

| Bound | Where | What it bounds | What the caller sees |
|---|---|---|---|
| `Deadline`, `WALL_TIME_BUDGET` 10 s | `src/vfs/deadline.py:36`, `46-89` | Each row-matching stage: the kernel's own at `src/vfs/base.py:1290`, `2110`, `2169`, `2251`, `src/vfs/chain.py:141`, `228`, `src/vfs/mounts.py:431`, and a storage's `grep`, `glob` and `search` at `src/vfs/storage/backends/database/grep.py:225`, `reads.py:385`, `search.py:307`, `backend.py:1253`. | A `truncated` warning. The rows found so far are returned. |
| Hop budget, 16 | `src/vfs/base.py:139`, `304`, `2538-2562` | How many kernels one call may enter. It is carried in a context variable, taken at `:1818` and `:1903`. | `budget_exhausted`. |
| `close_timeout` 10 s | `src/vfs/base.py:305`, `544-548` | The close of each storage, with `asyncio.wait_for`. | An exception from `close()`. |
| Query embedding | `backend.py:671` | The embedding of a `search` query, with `asyncio.wait_for` at the search budget. | Not traced. |
| Embedding of documents, 120 s | `embed.py:72`, `499`, `532` | One request to the embedding provider during a rebuild. | Not a verb call. |
| SQLite `busy_timeout` 5 s | `dialects.py:486` | The wait for SQLite's write lock. | The engine's own error. |
| Retry, 4 attempts | `engine.py:182-183`, `369-376` | Retries of a stale or serialization failure. | The failure, after the last attempt. |

- EXECUTED. A search of `src/vfs` for `statement_timeout`, `lock_timeout`, `command_timeout`, `pool_timeout`, `max_statement_time`, `call_timeout`, `query_timeout`, `connect_timeout`, `pool_pre_ping` and `pool_recycle` finds nothing. VFS sets no statement timeout on any engine.
- READ. The engine already knows that a cancellation does not stop a statement. Its analysis pass runs the SQL in an inner task, shields the wait, and interrupts the driver by hand. `engine.py:480-498`, `863-900`. No verb has that protection.
- READ. `_call_storage` awaits the storage with no bound. A `TransportError` becomes `backend_unavailable`. `src/vfs/base.py:2816-2940`.
- READ. No storage in `src/vfs` wraps a kernel. The hop budget is carried for one that would. `src/vfs/base.py:2541-2544`.

### 4.2 Every call that reaches more than one storage

| Route | Verbs | Kind | How failures merge |
|---|---|---|---|
| `MountListing.heads`, `src/vfs/mounts.py:438-468` | `ls`, `tree`, `glob`: one `stat` of each mounted root | Read | A failing mount shows bare, with a `warning`. |
| `MountListing._directory`, `:470-506` | `ls` of a directory that holds mount points | Read | A refusal of the directory stands, other than `not_found`. |
| `MountListing.tree`, `:346-402`, from `_tree_region` | `tree` over a region | Read | A failing mount becomes a `warning` among mounts that answer. |
| `MountListing.matched`, `:404-436` | `glob`, the mount points it matches | Read | As `heads`. |
| `MountListing.listed`, `:307-344` | `ls`, `stat` with a batch that names such directories | Read | Plain: each failure stands. |
| `_route_fanout`, `src/vfs/base.py:1854-1943` | `glob`, `grep`, `search` | Read | A mount asked whole becomes a `warning`. A mount the caller named fails the call. |
| `_dispatch_grouped_observations`, `:1736-1790` | Any verb given `observations` across mounts | Read or write | Plain. |
| `_route_entry_batch`, `:2393-2446` | `write` | Write | Plain. |
| `_route_two_path`, from `_route_pairs`, `:2337-2341` | `move`, `copy` | Write | Plain. |
| `_route_edge_batch`, `:2448-2532` | `mkedge`, `rmedge` | Write | Plain. |

Every one of them waits through `gather_settled`, with no bound.

### 4.3 The hang, executed

A kernel with a root, a mount at `/data` and a mount at `/slow`. One file in each. The storage at `/slow` was made to wait for ever in `stat`, `tree`, `glob`, `grep` and `read`. The harness gave each call 1.0 s.

| Call | `/slow` healthy | `/slow` stuck |
|---|---|---|
| `ls("/")` | `/data`, `/root.md`, `/slow` | No answer |
| `tree("/")` | Five rows | No answer |
| `glob("/*")` | `/data`, `/root.md`, `/slow` | No answer |
| `glob("**/*.md")` | Three files | No answer |
| `grep("needle")` | Three files | No answer |
| `stat("/slow")` | `/slow` | No answer |
| `ls("/data")` | `/data/report.md` | `/data/report.md`, at once |

- EXECUTED. Every call that reaches `/slow` gave no answer. Only the call that names another mount returned.

### 4.4 A spike of the bound, executed

A subclass of the kernel was written for the experiment. It waits 0.3 s for each storage call that is not the root's. Past that, it leaves the call running and returns a failed result with one `timeout` error at the mount's path. Nothing else was changed.

| Call, `/slow` stuck | Result |
|---|---|
| `ls("/")` | Success. `/data`, `/root.md`, `/slow`. One record: `warning`, `timeout`, at `/slow`. |
| `tree("/")` | Success. `/data`, `/data/report.md`, `/root.md`, `/slow`. The same record. |
| `glob("/*")` | Success. `/data`, `/root.md`, `/slow`. The same record. |
| `glob("**/*.md")`, `grep("needle")` | Success. The two files outside `/slow`. The same record. |
| `stat("/slow")` | Failure. One `error`, `timeout`, at `/slow`. |

- EXECUTED. Each answer came after 0.30 s.
- EXECUTED. The mount point still showed as a row in every listing, and the record became a `warning` among mounts that answered. No line of `src/vfs/mounts.py` was changed for that. The rules that report a failing mount today report a late one in the same way.
- EXECUTED. Seven calls were left running at the end, one for each call made on the stuck storage. With no guard, every call adds one more.

### 4.5 Seen in passing

- EXECUTED. One `stat("/")` on the in-memory storage is 34 driver round trips. 26 of them stamp the session settings before the transaction begins. One is the `SELECT`.

## 5. What the precedent says

| System | What bounds a member | What the caller sees for a slow member | What happens to writes |
|---|---|---|---|
| Linux NFS, `hard`, the default | Nothing. A fatal signal ends the wait. | A hang in `stat` and `df`. A listing of names in the parent is not held. | Retried without limit. |
| Linux NFS, `soft` or `softerr` | `timeo` and `retrans`, set for each mount. About 180 s on TCP by default. | `EIO` or `ETIMEDOUT`. With `softreval`, the cached attributes and no error. | An error, and a documented risk of "silent data corruption". |
| Linux `statx` with `AT_STATX_DONT_SYNC` | The caller, for one call. | Cached attributes, perhaps stale. No wait. | None. |
| autofs | No kernel bound on a mount request. | A hang while the daemon lives. `ENOENT` at once after the daemon is found dead. | None. |
| FUSE | Nothing by default. An optional bound for the whole connection, at least 15 s. | A hang. At the bound, the whole mount is aborted: `ECONNABORTED`, then `ENOTCONN`. | Aborted with the rest. |
| FreeBSD NFS | Nothing by default. `soft` sets a retry count for each mount. | A hang, or `ETIMEDOUT`. | Retried. A forced unmount "may throw away data not yet written". |
| Plan 9, 9P | Nothing. `Tflush` asks, and the client still waits. | A directory read blocks on a hung server. A server that fails keeps the covered entry. A union skips a member that fails. | A flushed request may already have been applied. |
| Elasticsearch | A `timeout` for each shard, on the request. None by default. `skip_unavailable` for each remote cluster. | HTTP 200, `timed_out: true`, partial hits, and a list that names the failed shards. | No partial mode. Each item of a bulk request is reported. |
| Thanos | `--store.response-timeout` for each store. Off by default. | HTTP 200 with a `warnings` list. | None. Reads only. |
| Vitess | A 30 s limit at each tablet. A lower one for each query, for `SELECT` only. | An error. With `SCATTER_ERRORS_AS_WARNINGS`, partial rows and warnings. | Best effort across shards by default. Two-phase commit by choice. |
| Trino, Citus | Bounds on the whole query only. | The whole query fails. | All or nothing. |
| `postgres_fdw` | Nothing of its own. A fixed 30 s for the cancel. | An error. The connection is thrown away if the cancel is not confirmed. | Each remote commits in turn. No two-phase commit. |
| gRPC | A deadline for each call, set by the client. None by default. Both sides cancel the handler when it passes. | `DEADLINE_EXCEEDED`. A channel whose connection is down answers `Unavailable` at once. | "Changes made before a cancellation are not rolled back." |

## 6. The findings that bind the design

1. **A member that runs out its bound is told to stop, and that is never proof that it did.** gRPC cancels the handler from both sides. 9P sends `Tflush`. `postgres_fdw` sends a cancel and gives the cancel 30 s. FUSE aborts the connection. Vitess kills the query. NFS `soft` is the one that only stops retrying. None of them takes the signal as proof: `Tflush` allows the reply to arrive anyway, gRPC says the two sides may disagree, Elasticsearch says a cancelled task may run on, and `postgres_fdw` throws the connection away when it cannot be sure. A design must send the signal, and must say what it does with a call that is still running, because one always can be.

2. **Reads degrade to a partial answer that names what is missing. Writes never do.** Elasticsearch, Thanos and Vitess return the healthy members' rows with a named failure. No system studied gives a write that treatment. NFS documents data corruption as the price of a soft write. Experiment 3 and experiment 4 show both ways of bounding a write leaving a change behind a caller who was told it failed, which is what `gather_settled` forbids.

3. **In Python, cancelling is not a clean stop, and one storage must be made safe before anything cancels.** On SQLite a cancelled call runs its statement to the end and costs a connection. A caller that awaits the cancellation is held for that long, and one that does not is not. A database in a file loses nothing. A database that lives in one connection is destroyed, and experiments 6 to 8 give the cause and a fix that held at every cut. Two of the four server drivers do not tell the server to stop, and the other two only ask. A call that is left running holds a connection and a snapshot, and experiment 5 shows fifteen of them empty the pool. The systems that stop asking a member do so on a sign that its connection is down: gRPC answers `Unavailable` from the connectivity state, Elasticsearch skips an unavailable cluster, and autofs answers at once after a write to its daemon fails. None of them stops asking because one call was slow.

4. **A bound belongs to the member, and it crosses a hop as one instant.** NFS, FreeBSD, FUSE, Thanos and Elasticsearch set the bound for each mount, store or remote cluster, because the latency is the member's own. gRPC carries one absolute deadline across hops as the time that is left, and never lengthens it. Thanos sets the member's bound tighter than the whole call's. The default almost everywhere is no bound at all. A default bound is VFS's own choice, and it must sit above the 10 s that VFS already gives its own matching stages, or the kernel cuts a storage before the storage can return its own truncated answer.

## 7. Not checked

- **The server engines.** Nothing was executed on Postgres, MariaDB, SQL Server or Oracle. Section 3.3 is read from driver source and labelled so. What a cancelled or a late call leaves on those engines, and whether a hard close of an ODBC connection waits behind its statement, need the engine legs.
- **oracledb.** The installed package is compiled. The upstream source on its main branch was read through a fetch that summarises, not line by line, and not at version 4.0.2.
- **A dead peer.** Every experiment used a slow statement that ends. A connection whose peer has gone silent, with no reply at all, was not simulated. How long each driver holds a call in that state was not measured.
- **The citations of sections 1 and 2.** They come from two separate readings of the clones and pages. A sample was opened again and matched: `clnt.c:2519-2568`, `nfs_fs.h:16-19`, `fuse/dev.c:544` and `73`, `inode.c:1004-1008`, `waitq.c:440`, `sysfile.c:593-600`, `devmnt.c:867` and `1099`, `flush:49-51` and `74-83`, `connection.c:106` and `113`, `http2_client.go:633-640`. The rest were not opened a second time.
- **FreeBSD.** The clone is sparse and has no `sys/rpc/`. How the retry count and the call timeout combine into a total time was not established. The mount_nfs(8) wording was read through a fetch that summarises.
- **Linux NFS writes.** Only the sentence in nfs(5) is established. The path of a write after a soft timeout was not traced.
- **Elasticsearch, Vitess and Citus** were read in documentation only. Whether `SCATTER_ERRORS_AS_WARNINGS` turns a shard timeout into a warning, and what Citus does when a worker hangs and does not refuse, were not established.
- **The linux, 9front and plan9 clones** were dirty and were not refreshed. The linux clone is seven months old.
- **A storage that wraps a kernel.** None exists in `src/vfs`, so no hop was crossed in any experiment.
- **The interrupt spike.** Its sweep of `stat` stopped answering after the first cut and was not diagnosed. Only its 81 cuts of `write` and the two long statements of experiment 7 are reported.
- **A cancellation during first touch.** Every cut was made on a storage that had already been provisioned.
- **Whether a Thanos store call is cancelled at its timeout.** Not read.

## 8. Corrections after review

A fresh reader reviewed the spec and this memo on 2026-11-18 and checked nine of its claims in the clones. Seven stood. Each change below was checked again in the clone or by experiment before it was made. The memo was edited in place, and this section lists what changed.

- **gRPC cancels the handler on the server too.** Section 2.4 said only that the deadline does not stop the server. The server sets a timer from the deadline and cancels the handler's context when it fires, `grpc-go/internal/transport/http2_server.go:600-609`, and the client resets the stream, `client_stream.go:99-110`. Both were read. The memo now says the handler is signalled from both sides and that the signal is not a stop.
- **gRPC's fail-fast follows the connection, not slow calls.** Section 2.4, the table in section 5 and finding 3 said a channel "known to be failing" refuses at once, and the first spec read that as precedent for skipping a storage whose call was slow. The refusal comes from the picker and the connectivity state, `grpc-go/picker_wrapper.go:156-176`, and it is answered with `Unavailable`. A call that ran out its deadline changes nothing for later calls. The keepalive ping and the reconnection delay were read and added, because they are the precedent that does apply: `http2_client.go:1812-1843`, `defaults.go:31-33`, `backoff/backoff.go:47-52`.
- **The data loss belongs to a database that lives in one connection.** The opening answer and finding 3 said cancelling "destroys an in-memory database" beside sentences about SQLite in general. Experiment 3 had already shown a file database keeps every row, and the review ran it again. The answer, experiment 3 and finding 3 now say so in words.
- **A cancelled call holds only a caller that awaits it.** Section 3.1 and finding 3 said cancelling does not return in time. That is true of `asyncio.wait_for`, which awaits the cancelled call. A task that is cancelled and not awaited returns its canceller at once, as the review executed.
- **Finding 1 was half of the precedent.** It said a bound is never proof that the member stopped, and the first spec concluded that the member need not be told. Almost every system studied tells it: the finding now leads with that.
- **NFSv4 `soft` was left out.** A sent request is cut only when the connection breaks, `linux/net/sunrpc/clnt.c:2536-2545`. It is added to section 1.1, because it is the kernel precedent for not putting a fixed time on work that may honestly run long.
- **What a call left running holds, and that `tree` has no budget.** Both were read in `dialects.py` and `reads.py` after the review raised them, and are added to section 3.6.
- **The cause of the loss, and two spikes of a fix.** Section 3.5 is new: experiments 6, 7 and 8.

A second review, the same day, confirmed the cause and asked for one more experiment. Two were run and added to section 3.5.

- **Experiment 9, a second connection that keeps the database alive.** It never lost a row, and it left the storage refusing calls after 6 of 81 cuts of a write in one form and gave no answer in the other.
- **Experiment 10, the shield with a mark.** A marked unit refuses its commit. 115 of 115 cuts kept the database and the next call, and a cancelled write was rolled back at 79 of 79 cuts before its commit.
- **Line numbers.** Every `src/vfs` citation in this memo is at `0d05c606`. The checkout has since moved to `a64dd18c` and then `e97ca9a9`. `src/vfs/storage/backends/database/` did not change in either move. In `base.py` and `mounts.py` names have moved: `MountListing.heads` is `_heads`, `_tree_region` is gone, and `_dispatch_entry` now goes through `MountListing.called`. The specs carry the current names.

## One line

Mature systems wait without limit unless told otherwise, bound a member for reads by a setting on the member, return the other members' rows with the missing one named, tell the late member to stop without assuming it did, and never do any of this to a write; and on SQLAlchemy a cancelled call costs a connection, which is the whole database when the database lives in one.
