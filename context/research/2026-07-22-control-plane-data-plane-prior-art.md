# Control plane and data plane: prior art for vfs's MCP surface

- **Status**: research memo (commits us to nothing; feeds a family of ADRs)
- **Date**: 2026-07-22
- **Owner**: Clay Gendron
- **Question**: What is the control plane / data plane split, in the terms
  the prior art actually uses; where does vfs sit against it today; and what
  should the MCP verb surface look like as a consequence? Secondarily: is
  `docs/plans/everything_is_a_file.md` §10.3 — which treats `.api/` as *the*
  control plane — the right framing?
- **Evidence gathered**: seven parallel surveys of read-only sibling
  checkouts under `~/Git/Repos/`, each paired with a line-level audit of
  `src/vfs/`. Sources: `plan9` (kernel namespace, devmnt, devip, devsrv,
  devproc, devcons, parse.c, libauth) and `plan9port` (lib9p, 9pserve) plus
  the normative 9P man pages; `freebsd-src`, `linux`, `libfuse`, `pjdfstest`;
  `juicefs`, `seaweedfs`, `minio`, `opendal`; `filesystem_spec`,
  `pyfilesystem2`, `libsqlfs`, `agentfs`, `jackrabbit-oak`;
  `modelcontextprotocol`, `python-sdk`, `fastmcp`; `spicedb`, `openfga`,
  `casbin`, `oso`. Citations are repo-relative to those checkouts; our own
  code is cited from `src/vfs/`.

---

## 1. The framing, and why §10.3 is too narrow

**The prior art does not define the control plane by what a node points
at. It defines it by what an operation's *subject* is.** FreeBSD states
the test structurally: `struct vfsops` holds exactly the operations whose
subject is the mounted instance — mount, unmount, root, statfs, sync,
quotactl, vget — every one taking `struct mount *mp` and none taking a
vnode; `struct vop_vector` holds the ~75 operations whose subject is one
object (freebsd-src:sys/sys/mount.h:800-850,
freebsd-src:sys/kern/vnode_if.src:54-881). The two are joined by exactly
two bridge ops. Linux draws the same line under different names
(linux:Documentation/filesystems/vfs.rst:174-215).

That test cuts across "where do the bytes live". `quotactl` takes a path,
resolves it with `namei`, then immediately throws the vnode away and uses
only `nd.ni_vp->v_mount` — the path was a *selector for the mount*, not the
operand (freebsd-src:sys/kern/vfs_syscalls.c:189-230). Taking a path does
not make an operation data plane.

§10.3 conflates two orthogonal axes. Its table contrasts "Data plane
(synced files)" against "Control plane (`.api/`)" on rows that are all
about **storage provenance** — local DB vs pass-through, searchable vs not,
versioned vs not, fast vs slow, offline vs not. Those rows are real and
worth keeping, but they describe a **mount kind** (stored vs pass-through),
not a plane. The plane question is orthogonal: `bind`, `remount`,
`mounts()`, `first_touch`, session establishment, and capability
negotiation are all control plane, all operate on locally stored mounts,
and none of them appear anywhere in §10.3.

**So the sharpest thing this memo can say: `.api/` is one control-plane
surface, not the control plane.** Seven buckets are in play, and vfs has
built exactly two of them well:

| | Concern | vfs today |
| --- | --- | --- |
| C1 | Session establishment, version and capability negotiation | partial — backend↔store handshake only |
| C2 | Namespace construction (mount, bind, unbind, remount) | **implemented, strongest surface in the tree** |
| C3 | Handle / instance lifecycle, cancellation, leases | absent |
| C4 | Control verbs (`ctl` files, admin ops) | specified-only, in §10.3 |
| C5 | Metadata mutation (attributes, ownership, quota) | partial — no attribute-write verb at all |
| C6 | Authorization | partial — path-only, principal-blind |
| C7 | Introspection and telemetry | data exists, no surface serves it |

And on the data side: D1 transfer unit (partial — statement-level only),
D2 consistency tokens (**implemented, and stronger than 9P's**), D3 walk
and listing (partial — no pagination anywhere), D4 bulk and backpressure
(partial — batch-native, unbounded), D5 content addressing (hashing yes,
addressing no), D6 index and search (built as libraries, unwired), D7
transactions and durability (transaction discipline good, versioning and GC
unwired).

Two smaller corrections to §10.3 while we are here. Its data-plane examples
still write `/.vfs/jira/PROJ-4521/__meta__/chunks/...`, a grammar ADR 016
retired; and it promises that after a write "the `BackgroundWorker` runs
the appropriate analyzer", which the resolved ancestor-propagation question
forecloses — storage owns no background work
(`context/research/2026-07-17-write-path-prior-art-and-scaling.md` §4.3).
§10.3 must be read as a pre-refactor sketch, and rewritten before it is
cited as a spec.

---

## 2. Plan 9 and 9P, in depth

Plan 9 is the acknowledged ancestor, and the useful reading is not "every
control surface is a file" — it is *which* control surfaces are files, and
what 9P refuses to provide at all.

### 2.1 The session is thinner than it sounds

A 9P session is three things and no more: a connection epoch, a fid space,
and a per-attach (identity, tree) pair.

- **Epoch.** `Tversion(msize, version)` must be the first message, and the
  client may send nothing else until `Rversion` arrives. The server may
  only *lower* `msize`, never raise it; the negotiated value is stored once
  on the mount and every downstream buffer derives from it
  (plan9:sys/man/5/version:17-48; plan9:sys/src/9/port/devmnt.c:98-240,
  with `m->msize = f.msize` at :221 and a second version attempt refused
  rather than renegotiated at :129-146). Critically, a successful version
  request *initializes* the connection: all outstanding I/O is aborted and
  every active fid is clunked. The set of messages between two version
  requests is literally the definition of a session
  (plan9:sys/man/5/version:83-90).
- **Identity, captured once.** `Tattach(fid, afid, uname, aname)` binds a
  fid to the root of a named tree. lib9p stamps `fid->uid` from `uname` at
  attach and `swalk` copies it down the fid tree; *no later message carries
  a user field at all* (plan9port:src/lib9p/srv.c:211-242, :324;
  plan9:sys/man/5/0intro:543-546). That is a security property, not an
  efficiency one — the per-call surface is structurally incapable of
  expressing privilege escalation.
- **Scope selection is separate from authentication.** `aname` picks which
  of the server's several trees this attach sees; `afid` proves who you
  are. One validated afid may back many differently-scoped attaches
  (plan9:sys/man/5/attach:76-119). 9pserve's `-A` flag rewrites every
  attach to a fixed aname/afid — a ready-made sandbox pattern
  (plan9port:man/man4/9pserve.4:70-78).

**Refusal is a success reply, not an error.** If the server does not
understand the version string it must answer `Rversion` with the literal
seven characters `unknown` — explicitly *not* `Rerror`
(plan9:sys/man/5/version:50-78; plan9port:src/lib9p/srv.c:165-178). This is
the single cheapest rule in the whole protocol and the one with the most
leverage for an LLM client, which reads a tool error as an outage.

### 2.2 Namespace construction is the control plane Plan 9 is famous for

`cmount` hashes the mounted-on channel's qid into the process group's mount
hash, finds or creates an `Mhead`, and splices a `Mount` in front
(MBEFORE/MREPL) or at the tail (MAFTER) of an ordered chain, returning a
globally increasing `mountid` (plan9:sys/src/9/port/chan.c:646-763). Type
must match. `cunmount` is two-arity — remove one specific binding, or
everything at a path — with distinct errors for "nothing mounted here"
(`Eunmount`) and "that thing is not in this union" (`Eunion`)
(chan.c:764-836). `rfork(RFNAMEG)` deep-copies the table into a fresh
process group, and `pgrpcpy` carries a comment that it **MUST** preserve
the parent's mountid allocation order (plan9:sys/src/9/port/pgrp.c:104-165).

Two things fall out that vfs does not have. `/proc/n/ns` renders the mount
table in *namespace(6) syntax* — `bind <flags> <to> <from>` — the same
language that constructs it, paged by an ordered cursor over mountids
(plan9:sys/src/9/port/devproc.c:928-975). "Show me this namespace" and
"reproduce this namespace" are one output. And `RFNOMNT` sets an
irrevocable, inherited `pgrp->noattach`: `bindmount` refuses before
touching any state, `namec` refuses `#`-attach outside a whitelist and
refuses `#M` unconditionally for everyone, and there is no way to clear the
flag (plan9:sys/src/9/port/chan.c:1359-1377,
plan9:sys/src/9/port/sysfile.c:1009-1010). A revocable seal is not a
sandbox.

### 2.3 The clone/ctl idiom, mechanically

§10.3 cites `/net/tcp/clone`. The mechanism is what makes it race-free.
`ipopen`'s `Qclone` case reserves a conversation under the protocol qlock
and then **rewrites the channel being opened** to point at the new
instance's ctl file — so the fd `open()` returns *is already* the
per-instance ctl, with no window in which the client holds "clone" unbound
to an instance (plan9:sys/src/9/ip/devip.c:407-422). Reading that ctl
returns the decimal instance number and nothing else (devip.c:650-655).
Teardown is refcount-by-open-handle with a reset to a well-defined idle
state that the allocator tests before reuse
(devip.c:553-583 `closeconv`). Registry lifetime is handle-scoped: lib9p's
`postfd` creates `/srv/name` with `ORCLOSE` and deliberately never closes
the fd, so `srvclose` unpublishes when the poster dies
(plan9port:src/lib9p/srv.c:829-853, plan9:sys/src/9/port/devsrv.c:284-297).
No TTL, no reaper, no orphan sweeper.

Two properties to reject rather than copy: `Fsprotoclone` rescans a fixed
array and hands back a *reused* slot index (devip.c:1281-1345), and there
is no idle timeout anywhere — safe only because the kernel guarantees fd
closure at process exit, which an MCP disconnect does not.

### 2.4 The verb-dispatch machinery

Every ctl write in the kernel goes through the same three functions.
`parsecmd` copies into a `Cmdbuf` and tokenizes; `lookupcmd` matches
`cb->f[0]` against a static `Cmdtab` and **enforces exact arity before any
side effect**, raising `Ecmdargs`; `cmderror` reconstructs the offending
message with `%q` quoting so the diagnostic echoes back what the client
wrote (plan9:sys/src/9/port/parse.c:10-114). `devproc` and `devcons` use it
verbatim (devproc.c:1299-1322, devcons.c:1055-1078). The atomicity unit is
the write: one message, one lock acquisition, all-or-nothing, byte count
returned (plan9:sys/src/9/ip/devip.c:1123-1186).

### 2.5 What 9P deliberately refuses to provide

This is the part a designer of an MCP verb surface most needs.

- **No schema on read.** Reading `/net/tcp/n/ctl` returns the conversation
  number; `/dev/consctl` is mode 0220 and cannot be read at all
  (plan9:sys/src/9/port/devcons.c:604-627); `/proc/n/ctl` has no read
  implementation. The verb tables exist and are never rendered. The only
  discovery mechanism in the system is writing a wrong verb and reading the
  error. **`read = schema` is an improvement Plan 9 does not have, and
  nothing in Plan 9 constrains how to do it.**
- **No transactions, no compound, no multi-object atomicity.** "Transaction"
  in 9P means one T/R pair (plan9:sys/man/5/0intro:61-65). The only
  atomicity guarantees in the entire protocol are that `wstat` is
  all-or-nothing over one file's metadata
  (plan9:sys/man/5/stat:227-232) and that `iounit` bytes transfer without
  splitting (plan9:sys/man/5/open:196-206). `newns` continues past failed
  binds and only reports under a debug flag
  (plan9:sys/src/libauth/newns.c:138-200) — a half-built namespace is a
  normal outcome.
- **No compare-and-swap.** `qid.vers` is advisory; no message accepts an
  expected-version argument, and lib9p bumps `vers` *after* a successful
  write (plan9port:src/lib9p/srv.c:544-551). Two clients editing one file
  silently last-writer-wins.
- **No batching.** Every message names one fid. `Twalk` is the sole
  exception and batches *steps along one path*, capped at 16 elements
  purely so `Fcall` can hold fixed arrays
  (plan9port:include/fcall.h:12,:35,:37).
- **No server-initiated messages.** Strictly request/reply; a client learns
  something changed only by asking again
  (plan9:sys/man/5/0intro:53-65). MCP inherits this constraint honestly.
- **No flow control.** `msize` bounds one message; nothing bounds the number
  of outstanding requests. 9pserve's only defense is to stop reading its
  own input (plan9port:src/cmd/9pserve.c:518-522).
- **Check-then-act races, admitted.** lib9p carries two literal
  `/* BUG RACE */` comments at `sopen`'s ORCLOSE parent check and
  `sremove`'s parent check (plan9port:src/lib9p/srv.c:405, :575). vfs can
  fold the authz predicate into the mutating statement; this is a place the
  prior art is known-broken rather than merely silent.
- **Cross-fid coherence after remove is explicitly implementation-defined**,
  with two blessed incompatible behaviours (plan9:sys/man/5/remove:33-46).

Three 9P rules are worth adopting verbatim. **Directory reads may seek only
to 0 or to the exact previous offset** (plan9:sys/man/5/read:56-78) — which
looks like byte-offset paging and is in fact the opposite: the restriction
is what licenses lib9p to hold a linked-list pointer and call it an offset
(plan9port:src/lib9p/file.c:334-373, with the fields marked
"implementation-specific; don't use" at include/9p.h:49-53). **Clunk is
terminal**: even if the clunk returns an error the fid is no longer valid
(plan9:sys/man/5/clunk:14-34), and lib9p removes the fid *before* any
handler runs (srv.c:553-560, :568-584). **Tflush can never be answered with
Rerror**, and a flushed request may still have taken effect — the client
must honor a reply that beats the Rflush, because a completed `Tcreate`
created a file (plan9:sys/man/5/flush:14-99).

---

## 3. Supporting evidence by area

### 3.1 Unix VFS, FUSE, POSIX conformance

**Confirms** the subject-of-the-operation test (§1) and confirms that
metadata mutation is a sparse, atomic patch: `wstat` applies all changes or
none, with per-field authority — name needs write on the parent, length
needs write on the file, mode needs ownership.

**Adds** four things. (a) **Typed, declared option schemas.** Linux replaced
the string blob with `struct fs_parameter_spec` — a name plus a value type
from a closed set, with `fs_parse()` validating and coercing before the
filesystem sees it, and one `fs_context` serving both mount and remount
(linux:Documentation/filesystems/mount_api.rst:596-685, :186). This is what
makes `read = schema` a *projection of the declaration* rather than a
hand-written manifest. (b) **A declared live-mutable subset**:
`MNT_UPDATEMASK` names exactly which flags a running mount may change
(freebsd-src:sys/sys/mount.h:442-450), and `vfs_domount_update` accepts a
caller-supplied `fsid` and returns ENOENT if it does not match the live
mount — a compare-and-swap on the control plane, costing one field
(freebsd-src:sys/kern/vfs_mount.c:1313-1450). (c) **Doomed handles.**
Forced unmount sets `MNTK_UNMOUNTF`, purges, and waits for `mnt_lockref` to
drain; `vgonel` marks each vnode `VIRF_DOOMED` so every later operation
fails with a stable error rather than touching freed state
(vfs_mount.c:2156-2340, vfs_subr.c:4170-4260, sys/vnode.h:252). `vflush`
distinguishes WRITECLOSE (flush, then reclaim) from FORCECLOSE (reclaim
regardless) — graceful and forced drain are different verbs. (d)
**Three-set capability negotiation.** FUSE's INIT computes `capable` (what
the server can do), `want` (what it asks for), and echoes back what is in
force; `want & ~capable` is a hard EPROTO that terminates the session, never
a silent downgrade (libfuse:lib/fuse_lowlevel.c:2592-2602, :2679-3028). It
also negotiates *numbers*, not just booleans — `max_readahead` by mutual
minimum, `max_write` clamped to the buffer, and `time_gran`, the server's
declared timestamp resolution (libfuse:include/fuse_kernel.h:914-930).

**Dissent.** FreeBSD has no runtime capability negotiation at all —
`vfsops` is a compile-time table and a caller discovers unsupported
behaviour by receiving EOPNOTSUPP from an operation it already issued
(freebsd-src:sys/sys/mount.h:1089-1100). FUSE's 41 accumulated INIT flags
(libfuse:include/fuse_kernel.h:452-495) are precisely the retrofit that
absence forces. Also: FUSE's lookup-count/forget protocol makes the
*client* responsible for reference accounting and concedes the count is
abandoned wholesale at unmount (libfuse:include/fuse_lowlevel.h:253-289) —
that is a kernel-trust assumption an MCP client does not earn.

**Note on conformance.** pjdfstest's ~8,700 assertions pin *only* the data
plane and metadata mutation — exact errno per precondition, inode stability
across rename, timestamp update rules including negatives, all gated by a
`supported()` check keyed to the filesystem type
(pjdfstest:tests/rename/00.t:1-60, pjdfstest:tests/misc.sh:171-196). Nothing
in the industry-standard conformance suite tests mount options, remount,
forced unmount, or capability negotiation. vfs gets no free validation for
its control plane and must write those tests itself.

### 3.2 Distributed metadata engines

**Confirms** vfs's `DialectProfile` direction from an independent angle,
and confirms that keyset cursors are the only correct listing shape.
JuiceFS's `DirHandler` pages by `name > cursor` on the `(parent,name)`
index and lowers its batch to 4096 when the driver is sqlite3, citing
`SQLITE_MAX_VARIABLE_NUMBER` (juicefs:pkg/meta/sql.go:6064-6149, :482-484).
SeaweedFS requests `limit+1` to derive has-more without a COUNT
(seaweedfs:weed/filer/abstract_sql/abstract_sql_store.go).

**Adds** five mechanisms. (a) **Session rows with expiry + heartbeat +
CAS-elected reaping.** JuiceFS inserts a `session2` row, refreshes
`expire = now + 5*heartbeat` with jitter, re-inserts if the update affects
zero rows, and elects a single sweeper via `setIfSmall` — a compare-and-set
on a counter row acting as a distributed lease, in portable SQL with no
advisory locks (juicefs:pkg/meta/sql.go:3146-3262,
juicefs:pkg/meta/base.go:883-948). (b) **`.control` as a real production
ctl file**, with reserved inodes above `minInternalNode`, per-node
permission bits, framed writes, **progress frames on the same handle every
300 ms**, and cancel-by-flush (juicefs:pkg/vfs/internal.go:38-82, :186-210;
juicefs:pkg/vfs/vfs.go:817-836, :1003-1006). (c) **The admin plane as a
reserved, separately-versioned prefix with its own authorization
vocabulary** — MinIO's `/minio/admin/<version>/…` under a reserved bucket,
every handler wrapped by middleware that always emits an audit log and
checks a distinct `policy.AdminAction`, so S3 data permissions never grant
admin verbs (minio:cmd/admin-router.go:30-131,
minio:cmd/auth-handler.go:188-206). (d) **Token-and-poll for long
operations**, with a generated client token, status fetched by token, and a
keep-alive byte every 10s (minio:cmd/admin-handlers.go:1340-1461). (e)
**Deferred deletion**: tombstone tables plus refcounts, swept by
lease-elected, timeout-bounded jobs on de-synchronized intervals —
SeaweedFS's poll interval is the prime 1123 ms, chosen explicitly to avoid
aligning with other periodic tasks
(juicefs:pkg/meta/base.go:1037-1066, seaweedfs:weed/filer/filer_deletion.go:23-41).

**Dissent, and it is sharp.** MinIO caps every batch at the protocol
boundary — `maxDeleteList = 1000`, and `DeleteObjectsHandler` *rejects*
rather than truncates (minio:cmd/api-response.go:43-46,
minio:cmd/bucket-handlers.go:473). vfs takes the opposite position by
design. The two are reconcilable only if vfs states a resource ceiling
(memory, transaction duration, lock hold time) that is *named and enforced*
even while the product limit stays generous; "we chunk internally" bounds
statement size and nothing else. Second dissent: **all three systems
deliberately refuse all-or-nothing semantics across a large batch** —
JuiceFS's `BatchUnlink` is scoped to one directory, MinIO returns a
per-object error slice, SeaweedFS responds per request. vfs currently
commits a write batch iff the *whole* batch succeeded
(`src/vfs/storage/backends/database/backend.py` `_execute_write`), which is
an implementation artifact no decision records. Third: JuiceFS packs all
slices of a chunk into one BLOB rather than a row per slice
(juicefs:pkg/meta/sql.go:167-172) — the right call for its hot path, and
flatly incompatible with vfs's addressable-chunks premise. Worth knowing
*why* it packs (bounded rows per mutation) without copying *what* it does.

### 3.3 Python abstraction layers and embedded SQL filesystems

**Confirms** the chunking discipline and the declared-capability idea:
PyFilesystem2's `getmeta()` returns a cacheable, namespaced table of
implementation facts, and — the load-bearing detail — the *base class
consumes what it publishes*: `validatepath` reads `invalid_path_chars`,
`move` reads `supports_rename`, `match` reads `case_insensitive`
(pyfilesystem2:fs/base.py:727-779, :1595-1614, :1183-1199). A declared
capability that no generic code reads is documentation that will rot.

**Adds** the two strongest single artifacts in this whole survey.

**Oak's `RDBDocumentStore`** is the same problem as vfs — a content tree on
an arbitrary SQL vendor — solved in production.
`RDBJDBCTools.appendInCondition` emits, for N placeholders,
`(field in (?…1000) or field in (?…1000) or …)`, splitting a large
membership test into OR'd groups of at most 1000 with the comment "maximum
'in' statement in Oracle takes 1000 values"; a separate `MAX_IN_CLAUSE =
2048` is the statement-level ceiling above which callers pre-partition
(jackrabbit-oak:oak-store-document/src/main/java/org/apache/jackrabbit/oak/plugins/document/rdb/RDBJDBCTools.java:345-404).
That single technique decouples the IN-list cap from the round-trip count.
It also carries `MODCOUNT` per row, batches `update … where ID = ? and
MODCOUNT = ?`, and walks the per-row batch result codes into a
`successfulUpdates` set so only the losers retry
(RDBDocumentStoreJDBC.java:328-410) — and it calls `sortDocuments()` before
every batch insert and update, plus `assertNoDuplicatedIds()`
(RDBDocumentStoreJDBC.java:1118-1122, :430-434).

**agentfs's SPEC** is the design libsqlfs should have had: an
inode/dentry/data split where listing is an index range scan on
`(parent_ino, name)`, hard links fall out for free, chunk size lives in a
config table and is **immutable after initialization** so
`chunk_index = offset // chunk_size` is a pure function, and every chunk
except the last is exactly `chunk_size` bytes
(agentfs:SPEC.md:159-284, :130-158, :361-390). Its whiteout table stores
`parent_path` as a column, justified in the spec text as "enabling O(1)
lookups of whiteouts within a directory, avoiding expensive LIKE pattern
matching" (agentfs:SPEC.md:495-520) — exactly the reasoning vfs applies
everywhere.

**Dissent.** libsqlfs makes the full path the primary key and pays for it
openly: hard links are unconditionally `-EACCES` ("hard link not supported,
not allowed"), directory rename re-keys every descendant row individually,
and `readdir` globs the whole subtree then filters for an embedded `/` in C
(libsqlfs:sqlfs.c:2417-2421, :2246-2320, :1989-2050). That is the clearest
statement available of what "one path tree, path is identity" costs. Second
dissent: fsspec's `AbstractFileSystem.ls` docstring still concedes, fifteen
years in, that the return contract is "TBD, but must be consistent across
implementations" (filesystem_spec:fsspec/spec.py:337-340) — the strongest
argument for vfs's declared column projection over a bag-of-fields dict.
Third: Oak's `NodeStore.merge(builder, commitHook, info)` lets a hook
**reject or rewrite** a commit, naming "update an in-content index" as an
intended use
(jackrabbit-oak:oak-store-spi/src/main/java/org/apache/jackrabbit/oak/spi/commit/CommitHook.java:38-54)
— which is the only prior art here for maintaining derived state
transactionally, and it is in tension with nothing in vfs except the
absence of a place to put it.

### 3.4 MCP as the outer control plane

**Confirms** that MCP already owns C1 and part of C3, and vfs must not
rebuild them in-namespace. `initialize` negotiates protocol version and
nested capability objects, with the python-sdk deriving the capability
object mechanically from which handlers are registered
(modelcontextprotocol:docs/specification/2025-11-25/basic/lifecycle.mdx:40-211,
python-sdk:src/mcp/server/lowlevel/server.py:283-328).
`notifications/cancelled` is Tflush, implemented over an anyio cancel scope
per in-flight request
(python-sdk:src/mcp/shared/session.py:95-200). Pagination is an opaque
cursor with a server-chosen page size that clients MUST NOT parse or
persist across sessions
(modelcontextprotocol:docs/specification/2025-11-25/server/utilities/pagination.mdx:15-97)
— the same restriction 9P imposes, licensing the same keyset freedom.

**Adds** three things vfs needs. **`tools/list` with a JSON Schema 2020-12
`inputSchema`, an `outputSchema` servers MUST conform to, and behaviour
annotations** (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
`openWorldHint`) *is* read=schema/write=act, machine-readable
(modelcontextprotocol:docs/specification/2025-11-25/server/tools.mdx:56-215,
modelcontextprotocol:schema/2025-11-25/schema.ts:1182-1224). **Tasks** —
`task: {ttl}` on a request returns a `taskId` immediately, status walks
`working → completed|failed|cancelled`, and per-tool
`execution.taskSupport` is `forbidden` / `optional` / `required` — are the
only long-lived, pollable, cancellable handle MCP offers, and the per-tool
gate maps exactly onto vfs's two audiences
(modelcontextprotocol:docs/specification/2025-11-25/basic/utilities/tasks.mdx:113-200,
:386-470). **Resource templates** (`vfs:///{+path}`) plus
`completion/complete` let an unbounded SQL tree be addressable without ever
being enumerated
(modelcontextprotocol:docs/specification/2025-11-25/server/resources.mdx:166-207).

**Dissent, and it is the most consequential in the memo.** The two
reference implementations disagree about how to page. The python-sdk's task
store uses a keyset cursor (`next_cursor = page_task_ids[-1]`, resumed via
`index(cursor) + 1`,
python-sdk:src/mcp/shared/experimental/tasks/in_memory_task_store.py:156-181),
while fastmcp base64-encodes a numeric **offset** and slices
`items[offset:end]`
(fastmcp:fastmcp_slim/fastmcp/utilities/pagination.py:15-80). Offset paging
degrades linearly and, under the concurrent inserts an ETL batch produces,
silently skips or repeats rows. Meanwhile the *official high-level* server
ignores cursors entirely — every `_handle_list_*` accepts
`PaginatedRequestParams` and returns no `next_cursor`
(python-sdk:src/mcp/server/mcpserver/server.py:302-382). Neither reference
is safe to copy; the contract is, the implementations are not.

Second dissent: MCP declines D1 outright. `ReadResourceRequestParams` adds
nothing to `uri` — no offset, no length, no range, no negotiated message
size (modelcontextprotocol:schema/2025-11-25/schema.ts:700-730), and the
python-sdk base64s whole payloads in one shot
(python-sdk:src/mcp/server/mcpserver/server.py:340-366). Third: JSON-RPC
batching was **deliberately removed** in the 2025-06-18 revision
(modelcontextprotocol:docs/specification/2025-06-18/changelog.mdx:12), so
vfs's 10,000-file contract must be one tool call taking an array —
per-file `tools/call` is not an option. Fourth: `notifications/resources/updated`
carries the URI and **no version, no hash, no payload**
(modelcontextprotocol:schema/2025-11-25/schema.ts:745-802); `_meta` is the
only extension point, and its namespacing rules are specified.

### 3.5 Dedicated authorization systems

**Confirms** that a consistency token belongs in the caller's hands.
SpiceDB's `Consistency` oneof is resolved by a gRPC interceptor into
exactly one revision before any handler runs —
`minimize_latency` / `at_least_as_fresh` / `fully_consistent` /
`at_exact_snapshot` (spicedb:pkg/middleware/consistency/consistency.go:111-264).
The ZedToken carrying that revision also carries the first 8 characters of
the datastore's unique ID, so a token minted against a different store is
classified `MismatchedDatastoreID` and handled by declared policy rather
than silently trusted (spicedb:pkg/zedtoken/zedtoken.go:82-215).

**Adds** the single most important architectural idea for C6. Oso runs the
policy with the resource left as an unbound variable and compiles the
residual constraints into a host-agnostic `Filter`: a root type, a set of
declared `Relation(from, field, to)` joins, and conditions in **disjunctive
normal form** — an OR of ANDs of `(Datum, Comparison, Datum)` where a Datum
is a `Projection(type, field)` or an immediate, over a closed comparison set
(oso:polar-core/src/filter.rs:24-79). The adapter that renders it into
SQLAlchemy is ~60 lines and returns the query **unexecuted**
(oso:languages/python/oso/polar/data/adapter/sqlalchemy_adapter.py:15-40,
oso:languages/python/oso/polar/data/adapter/adapter.py:1-5). That boundary
is what lets a policy stay expressive while enforcement stays a WHERE
clause — and, decisively, the IR's size is a function of the policy, not of
the batch, so one compiled predicate serves a 1-file read and a 10,000-file
scan identically.

Also adds: **preconditions as data**. SpiceDB's mutating RPCs take a list
of `(filter, MUST_MATCH | MUST_NOT_MATCH)` evaluated *inside* the write
transaction, each as one bounded `LIMIT 1` existence probe
(spicedb:internal/services/v1/preconditions.go:15-53). And **batch
collapse by decision shape**: bulk check hashes items to a cache key,
groups by hash-without-resource-id so all checks sharing
permission+subject collapse into one dispatch, and reports
`DuplicateCheckCount` back to the caller
(spicedb:internal/services/v1/bulkcheck.go:44-105,
spicedb:internal/services/v1/grouping.go:27-52,
openfga:pkg/server/commands/batch_check_command.go:116-205). OpenFGA
additionally requires caller-supplied **correlation IDs** and rejects
duplicates, removing positional coupling from the batch contract
(batch_check_command.go:211-227).

**Dissent.** Casbin is the negative case and it is instructive: its
model/policy separation is right, but because the matcher is an opaque
expression string, enforcement is a linear scan over every loaded rule per
decision (casbin:enforcer.go:806-830), and the only mitigation —
`LoadFilteredPolicy` — is dangerous enough that the enforcer refuses
`SavePolicy` while filtered (casbin:enforcer.go:508-544). Do not adopt an
authorization language that cannot be compiled into a predicate. Second
dissent: OpenFGA's contextual tuples are request-scoped facts overlaid by
in-memory iterator concatenation — and are **deliberately excluded from
`ReadPage`** (openfga:pkg/storage/storagewrappers/combinedtuplereader.go:14-85).
Request-scoped facts and pagination were never reconciled; that is a seam
vfs must not inherit. Third: neither SpiceDB nor OpenFGA found a durable
server-side session necessary at all — every RPC carries store, model
version, consistency token and contextual tuples and is otherwise
stateless. Spec 070 owes an explicit justification for any state it keeps
beyond the request.

---

## 4. Ranked candidate recommendations

Ranked across all areas, deduplicated. "Converged" marks a recommendation
that three or more independent surveys arrived at; those are the strongest
signals here. None of this is decided — each row is a candidate for an ADR.

| # | Bucket | Gap today | Proposal (one line) | Effort | Anchor |
| --- | --- | --- | --- | --- | --- |
| 1 | D3 | **No pagination anywhere.** `ls_rows`/`tree_rows` emit no LIMIT; `_cap_rows` (`base.py:2025`) trims *after* full materialization. `rows.py:276` claims `UNIQUE(parent_id,name)` "serves keyset pagination" — no code redeems it. | Opaque, self-describing keyset cursor on ls/tree/glob/grep/glean; page bound pushed into SQL; composite cursor for cross-mount fan-out; a cursor that does not decode classifies invalid. **Converged — all six areas.** | large | plan9:sys/src/9/port/devproc.c mntscan; plan9:sys/man/5/read:56-78; juicefs:pkg/meta/sql.go:6064-6149; libfuse:include/fuse_lowlevel.h:760-784; MCP pagination.mdx:15-97; spicedb:pkg/cursor/cursor.go:53-120 |
| 2 | D2 | CAS exists but is **internal**: `staging.py` fills `base_version` from the write path's own read; no verb takes a precondition. `VFSErrorKind.conflict` + `RetryClass.refresh` are unreachable. | Optional per-entry `base_version` / `if_version` on write and edit, feeding the existing guarded UPDATE; zero-row guard → `conflict` carrying the observed version. **Converged — 5 areas.** | small | jackrabbit-oak RDBDocumentStoreJDBC.java:328-410; plan9:sys/src/9/port/devproc.c:446-455; spicedb:internal/services/v1/preconditions.go:15-53 |
| 3 | C6 | Authorization is router-side and path-only (`permissions.py:279-340`, `base.py:1747-1800`); nothing principal-aware reaches SQL. Spec 058 declares the target and has no IR. | Compile `(principal, session grants, verb, mount layers)` into a small DNF predicate IR; render into `liveness_filters` — the existing enumeration chokepoint — as unexecuted `Select` contributions. Never post-filter. | large | oso:polar-core/src/filter.rs:24-79; oso adapter.py:1-5; casbin:enforcer.go:806-830 (negative) |
| 4 | C1 | `capabilities()`/`traits()`/`membership_budget` are computed and never leave the process. A caller cannot size a batch or learn a verb is a stub. | One establishment call publishing per-mount dialect, effective budgets, traits, derived capabilities, `mount_identity`, path limits; three-set negotiation (capable/want/in-force); mismatch is a **structured downgrade in the success envelope, never an error**. **Converged — 5 areas.** | medium | libfuse:lib/fuse_lowlevel.c:2592-2602, :2679-3028; plan9:sys/man/5/version:50-78; opendal capability.rs:23-180; pyfilesystem2:fs/base.py:727-779 |
| 5 | D4 | Batch is unbounded in memory and all-or-nothing; no in-batch duplicate rule outside ADR 018; results are positional. | Declared+enforced resource ceiling (reject, never truncate); per-item outcomes keyed by caller-supplied identity; in-batch duplicate detection; deterministic key sort before every statement. **Converged — 4 areas.** | medium | minio:cmd/bucket-handlers.go:473; jackrabbit-oak RDBDocumentStoreJDBC.java:1118-1122, :430-434; fsspec/asyn.py:204-282; openfga batch_check_command.go:211-227 |
| 6 | C4 | `grep -rn '\.api' src/` returns nothing; §10.3 is the only artifact and is pre-refactor. Administration is Python methods unreachable over MCP. | Declare control nodes as a table (name, type, doc, readable, writable, live-mutable) shaped like `PARAMS`; render it as schema on read, validate against it on write; reserved prefix; **separate action vocabulary**; mandatory audit on control writes; control reads pinned to current state. **Converged — 5 areas.** | large | plan9:sys/src/9/port/parse.c:35-114; freebsd-src:sys/kern/kern_sysctl.c:2333-2420; linux mount_api.rst:596-685; minio:cmd/admin-router.go:30-131; spicedb:internal/services/v1/schema.go:86-189 |
| 7 | C3 | No cancellation of any kind; `cancelled` and `timeout` kinds exist unproduced; `with_retry` cannot tell that a caller left. | Cancel never fails and is idempotent; a cancelled op reports a distinguished outcome; declare per verb whether cancel is a rollback (for writes it is, because the batch is one transaction); plumb the MCP cancel scope to the chunk boundary and suppress retry. **Converged — 3 areas.** | medium | plan9:sys/man/5/flush:14-99; plan9port:src/cmd/9pserve.c:526-598; MCP cancellation.mdx:13-67 |
| 8 | C7/C3 | Every verb is one synchronous call; a 10k ingest or reindex exceeds any call timeout with no receipt. | Long ops as readable job nodes: write returns a job id, read returns progress, expiry reaps; per-tool `taskSupport` **required** for bulk arms and **forbidden** for the agent loop; progress emitted from the existing `chunked()` loop. **Converged — 3 areas.** | large | minio:cmd/admin-handlers.go:1340-1461; juicefs:pkg/vfs/internal.go:186-210; MCP tasks.mdx:113-200 |
| 9 | D1 | `read` has no offset/length; every bound is a row count. A 200 MB body and a 4 KB config read identically. | Ranged reads with explicit offsets (pread shape — stateless, retryable); an advertised per-entry transfer unit; error-rather-than-truncate when one indivisible item exceeds the ceiling. **Converged — 4 areas.** | medium | plan9:sys/man/5/read:100-122; plan9:sys/man/5/0intro:493-507; agentfs:SPEC.md:257-284, :361-383; fsspec/caching.py:331-457 |
| 10 | C3 | `close()`/`unbind` clear the table then dispose the engine without waiting for in-flight ops. | Per-binding refcount + doomed flag: mark, refuse new dispatch with the existing classified error, drain under a bounded timeout, then dispose; offer graceful and forced variants. | medium | freebsd-src:sys/kern/vfs_mount.c:2156-2340; vfs_subr.c:4170-4260 |
| 11 | C6/D7 | Nothing coordinates two processes beyond a Postgres-only first-touch advisory lock; reclamation of versions/chunks/epochs has no mechanism. | One `leases(name, holder, token, expires_at, last_message)` table with CAS acquire/renew/release — no `FOR UPDATE`, no advisory locks; tombstone tables plus a caller-invoked, lease-elected, bounded sweep verb. **Converged — 2 areas, and it is one mechanism serving both.** | medium | juicefs:pkg/meta/base.go:883-948, :1037-1066; seaweedfs:weed/server/master_grpc_server_admin.go:62-90 |
| 12 | C4/C6 | The composed policy has no identity — bindings are runtime-only, so nothing names "the policy that answered this". | A `PolicyFingerprint` hashed over the ordered composed layers, stamped on every Result and every cursor, assertable by an ETL run; unknown values are named bypass sentinels that disable caching, never empty strings. | medium | openfga write_authzmodel.go:54-96; spicedb:pkg/datalayer/schemahash.go:1-56 |
| 13 | D4 | `membership_budget` makes the IN-list cap govern the round-trip count: 10,000 keys on the GENERIC floor is 10 sequential statements. | Add an OR-of-bounded-IN-groups builder beside `chunked()`, capped so total binds stay under the parameter budget, with a declared hard statement ceiling above which callers pre-partition. | small | jackrabbit-oak RDBJDBCTools.java:345-404 |
| 14 | D7 | `DialectProfile` says nothing about string ordering; MSSQL and Oracle default to case- and accent-insensitive collations. | Declare `name_collation` as a profile fact and emit it on both the ORDER BY and the cursor comparison — **a precondition for #1, not a polish item**: a mismatch silently skips or repeats rows. | small | seaweedfs:weed/filer/mysql/mysql_sql_gen.go:22-60 |
| 15 | D2 | `updated_at` is the ratified change cursor and nothing declares its resolution across four engines. | A `time_gran` trait declared per profile, so "query with slack" becomes a computable window rather than folklore. | small | libfuse:include/fuse_kernel.h:914-930 |
| 16 | C2 | `no_overlay` is a per-entry ratchet but `remount(no_overlay=False)` clears it; there is no session-wide shape freeze. | An irrevocable, inherited `frozen` flag refused before any state change, deny-by-default with an enumerated allowance list. | small | plan9:sys/src/9/port/chan.c:1359-1377; sysproc.c:61-66, :135-143 |
| 17 | C2 | `mounts()`'s replay recipe is a docstring paragraph; `bind`/`add_mount` commit one at a time, so a failed fifth mount leaves four standing. | Namespace profiles as data (mounts() output *is* a valid profile), applied all-or-nothing under one lock with seal-last encoded in the builder — deliberately inverting Plan 9's best-effort policy. | medium | plan9:sys/src/libauth/newns.c:34-200; plan9:sys/man/6/namespace |
| 18 | C7 | `mounts()` returns the table; nothing answers "why is this path read-only". | A resolution-introspection read (which binding, which composed layers, which deeper bindings shadow) and a namespace render that emits the calls rebuilding it, paged by a monotonic mount id. | small | plan9:sys/src/9/port/devproc.c:928-975; pyfilesystem2:fs/multifs.py:172-186 |
| 19 | C5 | No attribute-write verb exists; `owner_id` is a stored column no policy reads, and changing it requires rewriting content. | Batch-native sparse attribute patch — absent means untouched, explicit null means clear (generalizing `remount`'s own convention), atomic per entry, with a declared immutable-field list rejected loudly rather than silently ignored. | medium | plan9:sys/man/5/stat:227-250; plan9:sys/src/9/port/devsrv.c:226-282 |
| 20 | C6 | Spec 070's session shape is open; spec 058 is blocked on it. | Principal and scope fixed at establishment and **not overridable per call**; session grants compiled into the predicate (#3) as extra disjuncts, capped, and hashed into the fingerprint and the cursor. | medium | plan9port:src/lib9p/srv.c:211-242, :324; openfga combinedtuplereader.go:14-85 |
| 21 | D6 | Splitters, encoder, gram planner and DDL all exist; `_apply`'s statement sequence is entries, content, parent bumps, nothing else. | An ordered, composable derived-state stage inside the write transaction that may add rows or reject the commit; control writes declared to bypass the chain. | large | jackrabbit-oak CommitHook.java:38-54 |
| 22 | D1/D7 | A body is one unbounded Text column; every edit is a whole-body delete-then-insert. | Fixed-size storage blocks with the size stored once and **immutable**, only the last block short; ranged read/write and truncate become index range operations. Distinct from the semantic chunks table. | large | agentfs:SPEC.md:130-158, :257-284; libsqlfs:sqlfs.c:1375-1640 |
| 23 | D3/C6 | `_cap_rows` truncates **silently**; there is no time, fan-out, or byte axis. | Four-axis bounding with truncation-as-marked-success: a warning-severity marker naming the axis plus a continuation cursor. "500 matches, truncated, resume here" is actionable; a short list is a wrong answer. | small | openfga:pkg/server/commands/list_objects.go:60-152, :479-482 |
| 24 | C7 | `KIND_CONTRACTS` has retry classes and agent hints; nothing says which side of MCP's error line each kind falls on. | Declare the kind → channel mapping: most kinds are `isError: true` execution results carrying the hint (so the model self-corrects); reserve JSON-RPC errors for malformed input and internal faults. | small | MCP tools.mdx:440-495 |
| 25 | C1 | The meta row answers "does the schema match" but not "may this build serve this store". | Add `min_client_version` / `max_client_version` to the existing single row, checked in `_adopt`, refused not migrated. | small | juicefs:pkg/meta/config.go:170-200 |
| 26 | C5/D3 | `move`/`copy` are stubs, so subtree rename's cost is undecided — while the read path already depends on a materialized `path` column. | Pin the descendant rewrite as one set-based UPDATE per membership chunk before `topology.py` is written; shape it to raise rather than truncate on over-length. | medium | libsqlfs:sqlfs.c:2246-2320 (the cost); jackrabbit-oak RDBDocumentStoreDB.java:518-534, :655-678 |
| 27 | C7 | No telemetry of any kind in `src/`. | A branching accounting object with a no-op singleton default, feeding the bulk response and client-tunable structured logging (statements per operation, rows fetched vs served, arbitration arm, retries). | small | fsspec/callbacks.py:4-190; MCP logging.mdx:17-140 |
| 28 | C3 | The handle question is structurally open and no ADR closes it in either direction. | **Record the negative decision**: the data plane stays stateless and path/observation-addressed; the only cross-call continuation is the stateless cursor of #1; anything handle-shaped is a distinct named, expiring object (#8), never an implicit pinned resource. | small | plan9port:src/lib9p/srv.c:304-337 ("cannot clone open fid"); MCP has no fid model at all |

---

## 5. What vfs should deliberately not take

- **Union directories and the ordered mount chain.** Plan 9's first-hit
  walk (chan.c:965-1130) and concatenating `unionread` (sysfile.c:323-364)
  cost vfs specifically: `_route_entry_batch` groups a 10,000-entry batch
  by the single terminal binding a path resolves to, and unions turn that
  into per-element statements in exactly the fan-out that must stay
  bounded on Oracle. Worse, `unionread` *silently skips* an element that
  fails to enumerate — for an ETL audience a mount vanishing from a listing
  is a data-integrity bug. Take only the residue: write destination is
  declared, never inferred (Plan 9's MCREATE / `Enocreate`,
  chan.c:1140-1162), and every sibling in a fan-out settles rather than
  being dropped. **Correction worth recording:** ADR 011 is not the union
  decision — it governs return types and its own scope clause restricts it
  to router-side table-fact checks. The real constraint is the
  single-terminal-binding invariant in `Binding` and `_shadow_filter`,
  which is load-bearing and written down nowhere.
- **Fids for the data plane.** lib9p enforces "cannot clone open fid"
  because an open handle owns backing resources
  (plan9port:src/lib9p/srv.c:304-337). In vfs those resources would be a
  session from a bounded pool, pinned by an agent that may never return —
  and MCP is request/response with no server-initiated reclaim. See #28.
- **Client-side reference counting.** FUSE's lookup-count/forget protocol
  concedes counts are abandoned wholesale at unmount
  (libfuse:include/fuse_lowlevel.h:253-289). Take `generation` (vfs already
  has it as ULID identity, ADR 019); reject count-based reclamation.
- **`ioctl`.** An opaque numeric command plus an opaque blob, with no
  discovery — an agent can `ls .api/` and can never enumerate ioctls. Note
  that FUSE itself refuses unrestricted ioctl for regular mounts
  (libfuse:example/ioctl_ll.c:14-30). Keep only the kind-mismatch error
  discipline, which vfs already has as unconditional `wrong_kind`.
- **Path as sole identity.** libsqlfs's `-EACCES` on hard links and its
  row-by-row directory rename are the direct price
  (libsqlfs:sqlfs.c:2417-2421, :2246-2320). vfs already keeps entry_id ULIDs
  as durable identity (ADR 004/019) — do not let a materialized `path`
  column quietly become the key.
- **Opaque blob payloads.** SeaweedFS packs all attributes and the chunk
  list into one `meta` LONGBLOB and JuiceFS packs slices per chunk
  (juicefs:pkg/meta/sql.go:167-172). Both are right for their hot paths and
  both make per-chunk addressability, edges, and search impossible — which
  is the whole project.
- **Background workers, accumulators, and async invalidation.** Oak's
  `UnsavedModifications` flusher, JuiceFS's quota ticker, OpenFGA's
  spawn-on-miss cache invalidation. All conflict with the resolved decision
  that storage owns no background work
  (`context/research/2026-07-17-write-path-prior-art-and-scaling.md` §4.3).
  Maintenance runs as caller- or operator-invoked verbs, which is also what
  makes it testable. §10.3's "the `BackgroundWorker` runs the appropriate
  analyzer" needs deleting.
- **Casbin-style matcher strings.** Expressive and structurally
  un-pushdownable; O(rules) in memory per decision
  (casbin:enforcer.go:806-830). Keep only its refuse-to-write-back-a-partial-view
  guard (enforcer.go:508-544).
- **Offset pagination.** fastmcp's base64 offset cursor
  (fastmcp:fastmcp_slim/fastmcp/utilities/pagination.py:68-80) violates
  boundedness at 10k entries and is incorrect under concurrent insert.
- **A small product batch cap.** MinIO's `maxDeleteList = 1000` is the
  opposite of vfs's stated contract. Take the *discipline* (a named,
  enforced ceiling; reject rather than truncate), not the number.
- **fsspec's global strong-ref instance cache.** Its own docstrings admit
  it defeats GC and needs manual clearing
  (filesystem_spec:fsspec/spec.py:1599-1611); ADR 002 already settled engine
  ownership as a loud built-XOR-borrowed.
- **Reused instance ids and untimed leases.** `Fsprotoclone` hands back a
  free slot index and `closeconv` has no timeout
  (plan9:sys/src/9/ip/devip.c:1281-1345, :553-583). Safe under kernel
  process-exit guarantees; not under MCP disconnect.

**Recommendations that would reopen a landed ADR**, flagged so nobody
adopts them by accident:

- A mount-wide ordered revision or a change-log table (SpiceDB's
  quantized head revision, any snapshot cursor) reopens **ADR 013**. The
  cursor in #1 must therefore be keyset position plus the ratified
  `updated_at` watermark, never a global sequence.
- A router-owned transaction or a unit of work spanning mounts reopens
  **ADR 001**. Counted-nesting *inside one backend* (libsqlfs's
  `transaction_level`, sqlfs.c:209-295) keeps the letter of ADR 001 — the
  router still never sees a session — but does reopen its implied scope
  that a transaction cannot outlive one op call. Anything cross-mount is
  simply foreclosed.
- Per-tenant path prefixes, or honouring MCP `roots` as a path rewrite,
  reopens **ADR 006**. Roots must be a visibility filter over mounts;
  `aname`-style scoping maps to which bindings and permission layers a
  session gets, not to a rewritten root.
- `search(strategy=...)` reopens **ADR 007**.
- Exception-based control flow inside the tree reopens **ADR 008**.
- Persisting the mount table reopens **ADR 009**.
- Reintroducing metadata as namespace entries — including making `.api/`
  nodes stored rows or a new `ObjectKind` — reopens **ADR 015/016**.
  Control nodes must be router-synthesized ordinary files.
- A migration framework before first release reopens **ADR 020**.

---

## 6. Candidate follow-ups

**Ripe for an ADR now** (the evidence is convergent and the design space is
closed enough to decide):

1. **Pagination and the cursor contract** (#1, #14, #23) — the single
   foundational gap, and it changes every read signature, so it must
   precede the wire contract (spec 045) and the MCP boundary (spec 056).
   The collation fact is part of the same decision, not a follow-on.
2. **Caller-supplied write preconditions** (#2, and #19's atomicity rule) —
   small, reuses the SQL that already exists, and closes the lost-update
   hole in the project's primary workload. Should land together with a
   resolution of the recorded ABA question, since a caller-supplied base
   makes rows-affected the right win signal and retires the read-back
   inference.
3. **The negative handle decision** (#28) — cheap to write, expensive to
   relitigate, and every subsequent conversation about sessions, cursors,
   and cancellation depends on it being settled.
4. **Establishment and published budgets** (#4, #25) — the numbers exist
   and are already correct per dialect; this is publication, not
   computation.
5. **Batch contract: ceiling, per-item outcomes, ordering, duplicates**
   (#5, #13) — note that per-item outcomes make the current
   commit-iff-whole-batch-succeeded behaviour a *decision* rather than an
   artifact, which is worth recording either way.
6. **The `.api/` framing correction** (§1) — at minimum, rewrite §10.3
   against the current grammar, retire the `BackgroundWorker` sentence, and
   state the seven-bucket split. This is nearly free and it is what stops
   the next survey from treating vfs's control plane as absent.
7. **The single-terminal-binding invariant** (§5) — currently an unwritten
   load-bearing rule that reviewers keep misattributing to ADR 011.

**Needs more research or a prior decision first:**

- **The authorization IR** (#3, #12, #20). The shape is clear; the hard
  part is that vfs's grouping key is longest-prefix-shaped where SpiceDB's
  is exact equality, so batch collapse needs a covering-prefix resolution
  pass this memo does not design. Blocked behind spec 070 in any case.
  [NEEDS CLARIFICATION: does a row-level grant attach to an entry_id, a
  path prefix, or both — and is a grant on a directory inherited by
  descendants created after it?]
- **Fixed-size storage blocks** (#22). Large, and it interacts with the
  semantic chunks table, versioning, and content hashing.
  [NEEDS CLARIFICATION: block size — a single global constant in the meta
  row, or per-mount? And is a stored body's block size allowed to differ
  from a version row's, given ADR 017 ties version rows to material
  content writes?]
- **The derived-state commit stage** (#21). Structurally decisive for
  whether search can ever be transactionally consistent with content, and
  in tension with nothing except the absence of a place to put it.
  [NEEDS CLARIFICATION: does the chunk/embedding stage run inline in the
  write transaction for a 10,000-file batch, or does it mark rows dirty and
  defer to a caller-invoked verb — and if the latter, what does `grep`
  report about coverage in between?]
- **Long-running jobs and MCP tasks** (#8). The token-and-poll shape is
  clear; what is not is durability. MCP's TTL explicitly permits deleting a
  task *and its result*, so the task record cannot be the receipt.
  [NEEDS CLARIFICATION: what is the durable record of what a bulk ingest
  landed, and does it survive the task's TTL?]
- **Cancellation semantics for partially-committed work** (#7). The write
  case is answerable today (one batch, one transaction). The read and
  fan-out cases are not.
  [NEEDS CLARIFICATION: if a paged read is cancelled mid-fan-out, do pages
  already returned stand, and is the cursor still valid?]
- **Lease-elected sweeps and tombstones** (#11) — needs the `delete` /
  `move` / `copy` shape settled first (spec 072 task 12), because the
  tombstone form should inform those builders rather than be retrofitted.
- **Per-principal fairness limiting.** Strictly downstream of spec 070 and
  a `serve()` that does not exist; recorded so it is in scope from the
  start rather than discovered after the first shared deployment.
  [NEEDS CLARIFICATION: is the fairness budget process-local, or must it be
  shared across several MCP servers pointed at one database?]
- **Multi-engine conformance** (§3.1). The suite runs on SQLite while the
  production target is four engines, and the invariants most likely to
  diverge — rename identity preservation, in-transaction timestamp
  ordering, collation — are exactly the untested ones. The Postgres CI leg
  (spec 072 task 13) is the prerequisite, not the deliverable.
