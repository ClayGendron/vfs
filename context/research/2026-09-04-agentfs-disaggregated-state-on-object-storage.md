# AgentFS and "disaggregated agent state on object storage", mapped onto vfs

- **Status**: research memo (commits us to nothing; feeds the Turso
  re-attempt named in ADR 028 pin 3, roadmap 019 (union mounts) and 023
  (per-session namespaces), spec 054 (`serve()`), spec 070
  (principal-scoped sessions), and the audit story ADR 058 names for
  the Catalog plane)
- **Date**: 2026-09-04
- **Owner**: Clay Gendron
- **Question**: Pekka Enberg argues that an agent's state must survive
  ephemeral compute, move between machines, and scale without
  provisioned volumes. His design keeps SQLite-speed local operations,
  captures mutations in the write-ahead log, pushes them incrementally
  to object storage as the source of truth, and lazy-loads state on
  another machine. What exactly is the design? What has `agentfs`
  actually implemented — schema, key-value store, tool-call audit,
  snapshot and fork, sync? What are the consistency claims and their
  limits? And what should vfs take for (a) the Turso backend, (b)
  per-agent ephemeral workspaces, (c) the audit and read-side record?
- **Method**: four fetches of the blog post (2026-01-11) covering every
  section; a line-level read of `tursodatabase/agentfs` at the
  refreshed default branch — `SPEC.md`, `MANUAL.md`, `README.md`,
  `CHANGELOG.md`, the Rust SDK (`lib.rs`, `filesystem/agentfs.rs`,
  `filesystem/overlayfs.rs`, `toolcalls.rs`, `kvstore.rs`,
  `schema.rs`, `connection_pool.rs`), the CLI's `cmd/sync.rs`,
  `cmd/init.rs`, `opts.rs`, the TypeScript entry points and the
  Cloudflare / serverless adapters, the Python SDK, the Go SDK's
  driver line, and `sandbox/src/vfs/`; keyword greps for `sync`,
  `WAL`, `S3`, `checkpoint`, `branch`, `fork`, `snapshot`. Then a read
  of the sync engine the blog leans on, in the sibling `turso` clone
  (`sync/engine/src/*`, `cli/sync_server.rs`, the Python binding's
  sync surface). Then the vfs seams each idea maps onto: ADRs 013,
  017, 025, 027, 028, 058; spec 084's gate report; `roadmap.md`;
  `models/rows.py`, `models/version.py`,
  `storage/backends/database/dialects.py`, `storage/backends/memory.py`;
  the Mirage memo §3.21 / §3.24; the positioning memo §3. Cites and
  describes only — every line of vfs code stays ours.
- **Licenses**: `agentfs` — **MIT**, declared in `sdk/rust/Cargo.toml:6`,
  `sdk/typescript/package.json:47`, `sdk/python/pyproject.toml:11`,
  and `README.md:209-211`. The README badge links a root `LICENSE.md`
  that is *absent* from the checkout; the `licenses/` directory holds
  only third-party notices for two vendored crates — `fuser` (MIT,
  `licenses/LICENSE-fuser.md`) and `nfsserve` (BSD-3-Clause,
  `licenses/LICENSE-nfsserve.md`). Study freely; copy nothing.
  `turso` — **MIT** (`LICENSE.md`, "Copyright 2024 the Turso authors"),
  re-confirmed after refreshing. The blog post is copyrighted prose;
  it is quoted in short fragments only.
- **Sources line**: blog "Towards a Disaggregated Agent Filesystem on
  Object Storage", Pekka Enberg, 2026-01-11
  (`https://penberg.org/blog/disaggregated-agentfs.html`).
  `tursodatabase/agentfs` @ `0a014eb` (2026-06-03, "Make clippy happy
  (#337)"), refreshed today to upstream default; the checkout is a
  **shallow clone of one commit**, so commit counts and authorship
  cannot be reported from it. Latest `CHANGELOG.md` entry is 0.6.4
  (2026-03-25); `SPEC.md` is version 0.4. `tursodatabase/turso`
  refreshed today from `5fc727df1` (2026-08-26, 205 commits behind)
  to `origin/main` @ `6c7252267` (2026-09-04); working tree was clean
  before the refresh.

---

## 1. Bottom line

Enberg's post is a *direction*, and he says so. The disaggregated
design — local SQLite speed, the write-ahead log as the change feed,
object storage as the source of truth, the working set pulled on
demand — is described in prose and one figure. What `agentfs` has
built is narrower and honest about it: a SQLite schema (inodes,
directory entries, 4 KiB content chunks, symlinks, a key-value table,
a tool-call table), an overlay layer for copy-on-write sandboxing, and
four CLI verbs (`pull`, `push`, `stats`, `checkpoint`) that hand the
whole database file to Turso's sync engine. There is no time-travel
verb, no branch verb, no snapshot verb; "snapshot" is `cp agent.db
snapshot.db` and "fork" is the overlay's `--base` directory. Time
travel from the WAL is a README sentence, not code (§3.5).

The sync engine that would make the design real lives in `turso`, not
`agentfs`, and it is real: a change-data-capture tape, a page-level
pull protocol with lazy per-page loading, a logical push protocol, and
a transform hook. But the object-storage half is **Turso Cloud** — the
in-repo sync server is a TCP dev server over a local file. So "S3 as
the source of truth" is a hosted product's property, not something the
open code does on its own (§3.6, §4).

Three findings matter for vfs:

1. **The premise about vfs's own Turso backend is stale.** ADR 028
   chose Turso, but spec 084's gate hit three upstream blockers in
   pyturso's SQLAlchemy adapter and landed the fallback arm. The
   in-memory backend today runs on `sqlite+aiosqlite:///:memory:`
   (`memory.py:1-18`; gate report). Nothing in the live tree touches
   Turso. The re-attempt ADR 028 pin 3 promises is where any of this
   memo's "Turso backend" ideas would land (§5.1).
2. **"SQLite as the unit of state" conflicts with vfs's production
   posture for the shared corpus and does not conflict for a
   per-agent scratch mount.** The shared corpus is multi-process,
   10,000-row batches, five engines; ADR 013 removed the one
   manufactured single-writer lock vfs had. A per-agent scratch mount
   is single-process by nature (ADR 028 pin 4), already SQLite-shaped
   (`InMemoryStorage`), and could become a portable file that Turso
   sync moves between machines — as a *dialect choice*, not a vfs
   feature (§5.2).
3. **The tool-call ledger is the one piece to adopt in shape** — at
   the `serve()` tier, keyed by principal and session, and genuinely
   insert-only (agentfs's own implementation updates rows and so
   breaks its own spec, §3.3). Together with Mirage's op records
   (§3.24 there) it is the read-side audit the Catalog plane needs;
   vfs has the write-side half already in per-entry versions (§5.4).

What not to take: object storage as the source of truth for the shared
corpus (the engine is the source of truth; that is the whole point of
running on the customer's database), last-push-wins merging (vfs's
version guard makes merge unnecessary on one engine), physical
page-level history (vfs's history is logical and already built), the
FUSE/NFS/ptrace sandbox, and fixed 4 KiB content chunks (§6).

One-line version: *Enberg's design is a good sketch of a portable
per-agent scratch file; agentfs has built the schema and an overlay
but not the time-travel or the sync internals; vfs should keep its
engine as the source of truth, treat a Turso-synced SQLite file as one
possible scratch mount, and lift only the tool-call ledger.*

---

## 2. Enberg's argument and design

Terms used below, defined once:

- **WAL (write-ahead log)**: SQLite writes each change as a *frame*
  appended to a separate log file before folding it into the main
  database file. The main file is committed state; the WAL is
  in-flight change. Folding the WAL back into the main file is a
  **checkpoint**.
- **Page**: SQLite's unit of storage, 4 KiB by default. A WAL frame
  carries one whole page even if one byte changed.
- **Disaggregated**: compute and storage on different machines, so
  the machine doing the work can vanish without the state vanishing.
- **Object storage**: S3-style buckets — durable, cheap, no volume to
  provision, high latency per request.
- **Lazy load**: fetch only the pages a query touches, on demand,
  rather than the whole database up front.

### 2.1 The problem he states

Three needs. Agents work best with a filesystem because "foundation
models have internalized decades of Unix tools" — give an agent
`grep`, `sed`, `git`, and it is capable without custom tools. But a
real filesystem costs a container or VM, serverless and browser
agents have no filesystem at all, and "operating persistent volumes at
scale to host them is just hard." Agents also need to be "snapshotted
and resumed" — for debugging, reproducibility, compliance, recovery —
and today that is spread across a database, a log system, local disk
and git. And state must be portable: compute is interrupted by
timeouts and scaling, serverless compute is gone when the run ends,
and "if the agent state lives on a local filesystem or in memory, it
disappears too." His one-sentence statement: "State needs to survive
ephemeral compute, move between machines, and scale without requiring
persistent volumes to be provisioned."

### 2.2 AgentFS as the local answer

Everything an agent touches goes into one SQLite file: files and
directories (an inode/dentry design — the *dentry* table maps a name
in a parent to an *inode*; the inode table holds size, mode, times;
content is chunked), a key-value store (JSON values), and "an
append-only audit log of every tool invocation, capturing inputs,
outputs, and timing." The payoff he claims: "a single file contains
the complete agent runtime, which you can copy to another machine,
check into version control, or attach to a bug report," and because
the data is structured you can ask it questions with SQL. For native
tools, FUSE on Linux and NFS on macOS mount the file as a POSIX
filesystem (Figure 1: agent → bash → kernel VFS → FUSE → AgentFS
daemon → SQLite; the kernel page cache absorbs repeated reads). For
serverless and the browser, a TypeScript reimplementation of common
shell commands runs directly on the schema.

### 2.3 The disaggregated design

One local file "becomes limiting as workloads scale with multiple
agents, extended execution times, or collaborative scenarios." His
move: rather than separating metadata from data the way JuiceFS or
HopsFS do, disaggregate at the *database* layer, using the WAL. The
main file is committed state; the WAL is the stream of mutations.
"With Turso's sync protocol, local changes are pushed to a remote as
logical mutations, while remote changes are pulled as physical pages."
"The object store acts as the source of truth." Checkpoints persist to
object storage; WAL frames stream through a coordination layer; state
is reconstructed on any machine, and "only the working set is fetched
on demand, minimizing cold start latency."

Figure 2 is a timeline: during operation, WAL frames batch and sync to
a coordinator, which persists them to S3 immediately; when compute
migrates, the new instance pulls pages and WAL from the coordinator's
cache. "The compute remains ephemeral; the state persists."

Four capabilities follow, in his words or close to them:

- *Ephemeral compute, persistent state*: a serverless agent pulls
  state from S3, works, pushes, and exits — no volume, no storage
  cost while dormant.
- *Time-travel and branching*: "the WAL captures every mutation,"
  so a state can be rolled back or forked "without storing complete
  state snapshots."
- *Multi-agent collaboration*: agents share a filesystem through the
  coordinator, with conflicts resolved "last-push-wins by default, or
  custom merge logic via transform hooks."
- *Offline execution*: pull a checkpoint, work disconnected, sync
  later.

### 2.4 What he says is not done

"The disaggregated architecture represents a direction rather than a
complete implementation." Four open problems:

- **Write concurrency**: SQLite is single-writer. "The multi-version
  concurrency control implementation in Turso allows multiple
  writers, which mitigates this problem, but needs to be enabled in
  AgentFS."
- **Checkpointing overhead**: folding the WAL into the main file
  costs latency the filesystem feels; an incremental checkpoint may
  be needed.
- **Write amplification**: 4 KiB pages mean a one-byte edit ships a
  whole page. He names *physiological logging* — logical operations
  with physical page references — as the way to ship only what
  changed.
- **Large files**: videos, datasets, model weights do not fit the
  chunk model well; a hybrid that stores large blobs directly in S3
  and keeps only metadata in SQLite "might be required."

No numbers, latencies or benchmarks appear anywhere in the post. The
references it leans on are Turso's own: "Turso Cloud Goes Diskless"
(the S3-based server architecture) and "Introducing Databases Anywhere
with Turso Sync" (the client sync engine).

---

## 3. What agentfs implements today

All paths under `~/Git/Repos/agentfs` @ `0a014eb`. The repo is four
SDKs (TypeScript, Python, Rust, Go), a Rust CLI, and a Rust sandbox
crate. Only the Rust SDK and the CLI know about sync. The TypeScript
and Python SDKs open a plain local Turso database (`index_node.ts:26-59`,
`agentfs_sdk/agentfs.py:48-93`); the Go SDK does not use Turso at all
— it opens `modernc.org/sqlite` and sets `PRAGMA journal_mode=WAL`
itself (`sdk/go/agentfs.go:14, 85-88`).

### 3.1 The filesystem schema

`SPEC.md` v0.4 is the contract; `sdk/rust/src/filesystem/agentfs.rs:470-613`
(`initialize_schema`) is what the Rust SDK actually creates.

| Table | Purpose | Spec lines | Notes |
| --- | --- | --- | --- |
| `fs_config` | `chunk_size` (default 4096), `schema_version` | 130-157 | "immutable after initialization" |
| `fs_inode` | `ino` (AUTOINCREMENT), `mode`, `nlink`, `uid`, `gid`, `size`, `atime`/`mtime`/`ctime` + `_nsec`, `rdev` | 159-222 | inode 1 is root; nanoseconds added in 0.4 for NFS cache invalidation |
| `fs_dentry` | `(parent_ino, name) → ino`, `UNIQUE(parent_ino, name)` | 224-255 | hard links = several dentries, one inode |
| `fs_data` | `(ino, chunk_index) → data BLOB` | 257-283 | fixed-size chunks; last may be short |
| `fs_symlink` | `ino → target` | 285-299 | resolution is "implementation-defined" |

Path resolution walks one `SELECT ino FROM fs_dentry WHERE parent_ino
= ? AND name = ?` per component (spec 303-313); the Rust SDK fronts it
with a 10,000-entry LRU dentry cache (`agentfs.rs:20-65`). Every
mutating verb opens `Transaction::new_unchecked(&conn,
TransactionBehavior::Immediate)` — eight sites, e.g. `pwrite` at
`agentfs.rs:1410` — so each write takes SQLite's write lock up front.
The connection "pool" is one connection: `MAX_CONNECTIONS: usize = 1`
(`connection_pool.rs:14`), with callers queueing on a semaphore. The
SDK is therefore single-writer by construction, independent of the
engine underneath. Schema evolution is by column introspection:
`schema.rs:52-89` sniffs `fs_inode`'s columns to decide 0.0 / 0.2 /
0.4, and `agentfs migrate` adds columns (`MANUAL.md:182-233`).

The spec's "Extension Points" list "Version history and snapshots,"
"Content deduplication," and "File checksums/hashes" as things an
implementation *may* add (`SPEC.md:475-485`). None is implemented.
There is no version table, no hash column, and no dedup.

### 3.2 The key-value store

`kv_store(key TEXT PRIMARY KEY, value TEXT NOT NULL, created_at,
updated_at)` with one index on `created_at` (`SPEC.md:622-635`;
`kvstore.rs:33-48`). Set is an upsert; get, delete, keys are one
statement each. Values are JSON strings. The spec's own extension
list — "namespaced keys with hierarchy support," "value versioning" —
describes a filesystem.

### 3.3 The tool-call audit log

The spec (`SPEC.md:21-39`) declares `tool_calls(id, name, parameters,
result, error, started_at, completed_at, duration_ms)` and states rule
5 plainly: "Records MUST NOT be updated or deleted (insert-only audit
log)" (line 99). `completed_at` and `duration_ms` are `NOT NULL`;
"insert once when the tool call completes."

The Rust implementation departs from that. Its DDL adds a `status TEXT
NOT NULL DEFAULT 'pending'` column and makes `completed_at` and
`duration_ms` nullable (`toolcalls.rs:95-105`). `start()` inserts a
pending row and returns its id (`:129-150`); `success()` and `error()`
then **`UPDATE`** that row with the result, status, completion time
and duration (`:153-188`, `:236-262`). Only `record()` (`:193-233`) is
"the spec-compliant insert-only method." The Python SDK mirrors the
pending/success/error shape (`toolcalls.py:11-35`). So the audit log
as shipped is mutable: the same row is written at least twice, and a
crash between `start()` and `success()` leaves a permanent `pending`.
The `agentfs timeline` CLI reads this table (`MANUAL.md:275-287`),
which is how the README's sample shows a `pending` row (`README.md:86-91`).

Two observations for §5.4: the spec's *intent* (record on completion,
immutable) is the right one for an audit record; the implementation
chose ergonomics (a start/finish pair) and lost the property. And the
schema carries no session id, no principal, no parent call — the spec
lists all three as extensions "in separate tables" (`SPEC.md:113-122`).

### 3.4 Overlay: the only fork

An `OverlayFS` composes a read-only `base: Arc<dyn FileSystem>` (a host
directory in practice — `agentfs init --base <PATH>`, `MANUAL.md:28`)
with a writable `delta: AgentFS` (`overlayfs.rs:39-61`). Lookup order
is delta → whiteout → base → not found (`SPEC.md:557-562`). Deleting
a base file records a **whiteout** row so the lookup does not fall
through (`fs_whiteout`, `SPEC.md:495-520`); copying a base file into
the delta before modifying it (**copy-up**) records `fs_origin(delta_ino
→ base_ino)` so FUSE keeps reporting the inode number the kernel
cached (`SPEC.md:564-605`, "similar to Linux overlayfs's
`trusted.overlay.origin`"). Whiteouts and origins are loaded into
in-memory sets at open (`overlayfs.rs:137-191`). Note a second
spec/code split: the spec's `fs_whiteout` carries an indexed
`parent_path` column "for O(1) child lookups"; the Rust DDL creates
`fs_whiteout(path, created_at)` with no such column
(`overlayfs.rs:95-103`).

This is what "fork" and "sandbox" mean in agentfs: `agentfs run
--session <ID>` mounts an overlay over the host tree (Linux: FUSE +
user namespaces; macOS: NFS + Apple's sandbox — `MANUAL.md:90-111`),
`agentfs diff` lists the delta (`:267-273`), and the FAQ contrasts it
with git worktrees: isolation "enforced" rather than "conventional"
(`README.md:187`). The sandbox crate adds a mount table with
longest-prefix routing (`sandbox/src/vfs/mount.rs:9-40`) and an
`SqliteVfs` over the SDK (`sandbox/src/vfs/sqlite.rs:11-43`), for the
experimental ptrace backend.

### 3.5 Snapshot, time travel, branching

The keyword grep for `snapshot`, `branch`, `fork`, `checkpoint`,
`WAL`, `S3` over every source file finds: `libc::fork` in the daemon
and sandbox, FD-table cloning "for fork/clone syscalls," the Go SDK's
WAL pragma, and the sync command. Nothing else. Snapshot is a file
copy — "cp agent.db snapshot.db" (`README.md:41`). The README FAQ's
claim that "SQLite's write-ahead log enables snapshotting and
time-travel forking by capturing every filesystem change"
(`README.md:191`) describes a property of the storage format, not a
feature of the code. There is no verb that rolls a filesystem back to
a point, and no verb that branches one.

### 3.6 Sync: four verbs over Turso's engine

The Rust SDK depends on `turso = { version = "0.4.4", features =
["sync"] }` (`sdk/rust/Cargo.toml:9`; same in `cli/Cargo.toml:30`).
`SyncOptions { remote_url, auth_token, partial_sync }`
(`lib.rs:84-91`) rides on `AgentFSOptions` (`:104-118`). `open()`
decides the mode in three arms (`:312-336`): a `remote_url` builds a
new synced database through `turso::sync::Builder::new_remote`; an
existing `{path}-info` sidecar re-opens one; otherwise it is a local
database, optionally encrypted — and encryption and sync are
mutually exclusive (`:302-306`; `cmd/init.rs:135-138`;
`MANUAL.md:37`). The four public methods are one-liners onto the sync
database: `pull()` (`:429`), `push()` (`:436`), `checkpoint()` (`:443`),
`sync_stats()` (`:450`). The CLI exposes exactly those as `agentfs
sync <id> pull|push|stats|checkpoint` (`opts.rs:362-371`;
`cmd/sync.rs:1-46`), with `TURSO_DB_AUTH_TOKEN` from the environment
(`cmd/init.rs:21-26`). Partial sync — the lazy-load leg — is
configured at `init` with a 128 KiB prefix bootstrap and 128 KiB
segments by default (`cmd/init.rs:37-42`; flags at `opts.rs:52-63`).
The CHANGELOG dates this: "Basic sync support to the agentfs CLI" in
0.5.0, 2026-01-08 (`CHANGELOG.md:152`), three days before the blog.

No agentfs code batches WAL frames, talks to a coordinator, or names
S3. All of that is either inside `turso`'s sync engine or inside
Turso Cloud. Reading the engine (refreshed `turso` @ `6c7252267`,
`sync/engine/src/`):

- **Change capture** is a CDC table, not raw WAL frames: `DatabaseTape`
  turns on `PRAGMA capture_data_changes_conn('full,turso_cdc')`
  (`database_tape.rs:22-33, 154-156`) and reads row-level before/after
  images from `turso_cdc`.
- **Push** replays those as logical row operations to the remote over
  HTTP; `push_changes_to_remote` "will **not** block writes for the
  period of sync" (`database_sync_engine.rs:3163-3164`). An optional
  `push_operations_threshold` splits a push into batches, never
  mid-transaction (`:67-73`).
- **Pull** receives either physical pages (`PullUpdatesStreamKind::Pages`,
  selected by a Roaring bitmap of wanted pages —
  `server_proto.rs:16-45, 61-64`) or, on MVCC remotes, a logical log
  of `LogicalOp { UpsertRow | DeleteRow | Schema | UpdateHeader }`
  keyed by `table_name`/`stable_table_id` and **rowid**
  (`client_proto.rs:6-16, 54-92`). Applying a pull "will block writes
  for the period of pull" (`:1879-1880`), and `sync()` is push then
  pull (`:3199-3206`).
- **Lazy load** is `LazyDatabaseStorage`: a page store that fetches a
  page on first read and deduplicates concurrent loads of the same
  page (`database_sync_lazy_storage.rs:19-52, 222`).
- **Transform hooks** are `use_transform` (`:49`) →
  `apply_transformation`, which hands batches of DML row mutations to
  a user callback, split at DDL boundaries, and expects the same
  number of results back (`database_sync_operations.rs:3176-3210`).
- **Checkpoint** compacts the local WAL and resets the
  `revert_since_wal_watermark` the engine keeps so it can revert
  unpushed local changes (`types.rs:146-178`; `:1460`).
- **The Python binding exposes all of it**: `turso.sync.connect(":memory:",
  remote_url=...)` with `pull()`, `push()`, `stats()`, `checkpoint()`,
  and an asyncio twin (`bindings/python/README.md:85-140`;
  `bindings/python/src/turso_sync.rs:576-597`).
- **The server side in the repo is a dev server**: `cli/sync_server.rs`
  (1,289 lines) is a blocking TCP listener that answers
  `/pull-updates` by scanning WAL frames of one local file, and refuses
  logical pulls for in-memory paths (`:165, :554-593, :900-907`). The
  "coordination layer" and the S3 persistence in Figure 2 are Turso
  Cloud's — the "Turso Cloud Goes Diskless" reference — and are not in
  either repository. The turso CHANGELOG never mentions agentfs.

So: the *client* half of Enberg's design exists and works
(CDC-tape push, page or logical pull, partial bootstrap, transform
hook); agentfs uses it as a black box through four verbs; the *object
storage* half is a hosted service.

### 3.7 Everywhere the schema runs

The same tables run on Node (`@tursodatabase/database`), in the
browser (WASM, `index_browser.ts`), on Cloudflare Durable Objects'
SQLite (`integrations/cloudflare/agentfs.ts:1-8` — the "Cloudflare
Durable Objects integration prototype," 0.4.1), and over HTTP against
Turso serverless (`integrations/serverless/adapter.ts:1-17`). This is
the real source of agentfs's "runs anywhere" reach: the unit is a
schema simple enough to re-implement on any SQLite-shaped store, not
a binary that ports.

---

## 4. Consistency claims and their limits

Each claim below is stated, then bounded by what the code does.

**"Reads and writes occur at local-disk speed."** True for the
single-writer, single-process case the SDK enforces (one pooled
connection, `BEGIN IMMEDIATE` per verb). It is also the ceiling:
two agents in two processes sharing one file serialize on SQLite's
lock, and two agents on two machines are not sharing a file at all —
they are sharing a remote through push/pull.

**"Since remote state is authoritative, automatic conflict resolution
occurs."** The mechanism is *last-push-wins on rowid*. A push replays
`UpsertRow`/`DeleteRow` by `(table, rowid)`; `fs_inode.ino` and
`fs_dentry.id` are `AUTOINCREMENT` integers minted locally. Two
agents that each create a file offline will both mint the next `ino`;
whichever pushes second overwrites the first's inode row, while both
dentries may survive and point at one inode. The spec's consistency
rules ("every dentry MUST reference a valid inode," "file size MUST
match total size of all data chunks," `SPEC.md:456-463`) are not
enforced by the sync layer; they hold only if the transform hook
re-establishes them. The post's "custom merge logic via transform
hooks" is where that burden lands, and nothing in agentfs supplies
such a hook. In plain terms: the merge is correct for one writer at a
time, and undefined for two.

**"Time-travel and branching" from the WAL.** Turso's engine keeps a
revert watermark so *unpushed* local changes can be rolled back
(`revert_since_wal_watermark`), and MVCC remotes keep a logical log
per generation. That is an engine-level undo, not a filesystem
history: nothing maps "the file `/a` as of tool call 7" to a WAL
offset, and a checkpoint (`agentfs sync checkpoint`) discards the
local watermark. The claim is architectural potential; the feature
does not exist (§3.5).

**"Only the working set is fetched on demand."** True at *page*
granularity, which is not *file* granularity. A `readdir` walks
`fs_dentry` by index; a `read` fetches `fs_data` chunks by
`(ino, chunk_index)`. Both are B-tree lookups, so the pages touched
are roughly proportional to the files touched — good. But an
`ORDER BY name` listing of a large directory, or the tool-call table's
`ORDER BY started_at DESC`, touches every page of the relevant index,
and the 128 KiB prefix bootstrap (`cmd/init.rs:39`) is a fixed guess
at what the first pages will be.

**"Append-only audit log."** Spec yes, implementation no (§3.3).

**Offline execution.** Genuine: `push()` and `pull()` are explicit
verbs, nothing runs in the background, and the engine records
`last_pull_unix_time` / `last_push_unix_time` so the CLI's `stats`
can say how stale a replica is (`types.rs:155-158`). This is also
where agentfs agrees with vfs's "storage owns no background work" pin
(ADR 013 pin 5): sync is a verb.

**Encryption at rest and sync are exclusive** (`lib.rs:302-306`).
A portable file that must also be encrypted cannot be synced today.

**Write amplification and checkpoint cost** are acknowledged as open
(§2.4) and are inherent to a page-granular physical log. Turso's
logical MVCC pull path (`PullUpdatesStreamKind::MvccLogicalLog`) is
the engine's answer on the *pull* side; the push side is already
logical (CDC rows). The post's "physiological logging" is therefore
partly landed in the engine, but only for MVCC-mode remotes, which
agentfs does not enable (§2.4's own admission).

---

## 5. Mapping onto vfs

Legend: **adopt** — take the concept now, in vfs's own shape;
**adapt** — take it when the roadmap reaches the consumer;
**parity** — vfs already has it, sometimes better; **skip** — a
consequence of a bet vfs did not make.

| # | agentfs / Enberg idea | What vfs has | Verdict |
| --- | --- | --- | --- |
| A | one SQLite file is the unit of an agent's state (§2.2) | `InMemoryStorage` = `DatabaseStorage` over `sqlite+aiosqlite:///:memory:`, single-process by declaration (ADR 028 pin 4); shared corpus on server engines | **adapt** for scratch mounts; **skip** as the unit (§5.1, §5.2) |
| B | WAL/CDC capture, push to a remote, object storage as source of truth (§2.3, §3.6) | the engine *is* the source of truth; Postgres/MSSQL/Oracle bring their own replication; `updated_at` is the coarse change cursor (ADR 013 pin 4); no change-log table by decision (ADR 017) | **skip** for the corpus; **adapt** for a Turso-file scratch mount via `turso.sync` — a dialect, not a feature (§5.1) |
| C | lazy-load the working set by page (§3.6) | server-engine mounts fetch rows on demand over the wire by construction; nothing to build | parity by architecture |
| D | time travel from the WAL (§3.5, §4) | per-entry `version`, versions table minted per content write with a content hash (ADR 013/017); trash arc, delete never destroys (ADR 027) — a *logical* history that exists today | parity, stronger; skip physical history (§5.3) |
| E | overlay fork: base + delta, whiteouts, copy-up, `agentfs diff` (§3.4) | roadmap 019 union mounts (`BEFORE`/`AFTER`/`CREATE`) and 023 per-session namespaces with `fork()`; neither built | **adapt** — the whiteout rule set is design input for 019 (§5.2) |
| F | multi-agent via last-push-wins + transform hooks (§4) | one shared engine; every material `UPDATE` is guarded by `WHERE version = :seen` and a stale write classifies `conflict` (ADR 013 pin 1); one batch writer per subtree (ADR 025) | **skip** — no merge is needed when writers share the engine |
| G | tool-call audit table (§3.3) | write-side audit only (versions); no ledger of what an agent *called*; ADR 058 names the audit story for the Catalog; Mirage §3.24 op records | **adopt** in shape at the `serve()` tier, insert-only for real (§5.4) |
| H | key-value store (§3.2) | files at paths; entry `metadata`; the KV spec's own extensions describe a filesystem | skip |
| I | fixed 4 KiB content chunks in `fs_data` (§3.1) | `content` row per entry; semantic chunks for the index only (ADR 036/048); bytes path (ADR 043) | skip — different job |
| J | sync is an explicit verb, no daemon (§4) | ADR 013 pin 5: storage owns no background work | parity |
| K | schema version by column sniffing + `migrate` (§3.1) | greenfield, no migrations; drift tests pin schema to models | parity (different stage) |
| L | large files: blobs in S3, metadata in SQLite (§2.4) | content lives on the engine; no blob offload; no roadmap entry | note as a later-wave open question (§5.5) |
| M | the same schema re-implemented on Node, browser, Durable Objects, serverless HTTP (§3.7) | one Python implementation; the JS/Rust "full implementation" question is open (open-questions, 2026-08-16) | positioning fact (§5.5) |
| N | FUSE/NFS mounts, ptrace sandbox, `agentfs run` (§3.4) | `run` verb on the hermetic-runtime direction (monty / WASI); FUSE explicitly out of scope | skip |
| O | encryption XOR sync (§4) | none of either | note only |

### 5.1 (a) The Turso backend: the premise, corrected, and what is one step away

The question assumes vfs runs on Turso. It does not. ADR 028 chose
`sqlite+aioturso:///:memory:`, but spec 084's gate found three
blockers in pyturso 0.7.1's SQLAlchemy adapter — engine construction
fails on a missing `has_stop`, the writer-listener recipe cannot set
`isolation_level` on the generic async adapter, and `memoryview` bind
parameters (vfs's `ULIDKey` → `BINARY(16)`) are refused — and landed
the fallback arm (`context/specs/archive/084-turso-in-memory-backend/gate-report.md`).
The in-memory backend is `DatabaseStorage` over
`sqlite+aiosqlite:///:memory:` with a `StaticPool` (`memory.py:1-18`).
pyturso was removed after the probe. ADR 028 pin 3 keeps the
re-attempt open "as it matures."

Two things this memo adds to that re-attempt:

- **A Turso *file* mount with sync is a dialect choice.** pyturso now
  ships `turso.sync.connect(path, remote_url=...)` with `pull`, `push`,
  `checkpoint`, `stats`, sync and async (§3.6). If the SQLAlchemy
  adapter blockers clear, a `DatabaseStorage` pointed at a synced
  Turso file would inherit push/pull *outside* vfs's verb surface —
  the operator runs `push()` on the connection, the way agentfs's CLI
  does. vfs would declare a turso-stamped `DialectProfile` only where
  divergence demands it (ADR 028 pin 2 already says so;
  `dialects.py` docstring: "a `DialectProfile` field is justified only
  for a decision SQLAlchemy takes no position on"). Nothing in the
  `VirtualFileSystem` API needs to know.
- **What the sync engine would do to vfs's tables.** Push replays
  row images by rowid; pull installs pages or logical ops. vfs's
  identities are ULIDs, so two scratch files never collide on
  `entry_id` — but each table also has an integer surrogate primary
  key "that nothing durable references" (`rows.py` docstring), and
  that surrogate *is* the rowid the sync engine keys on. Two offline
  replicas of one vfs mount would collide exactly as agentfs's inodes
  do (§4). The consequence is a rule, not a feature: **a synced Turso
  file is a single-writer replica that moves between machines; it is
  never a merge target.** That is the same posture as ADR 028 pin 4
  (single-process) and ADR 025 (one batch writer per subtree), so it
  costs nothing to state.

### 5.2 (b) Per-agent ephemeral workspaces: where SQLite-as-unit is fine

Where the conflict is real: the shared corpus. "Never assume SQLite"
is not a preference; it is the batch contract (10,000+ rows in one
call, chunked to Oracle's 1,000-element `IN` cap and SQL Server's
~2,100 binds), the multi-process deployment, and the write-parallelism
ADR 013 bought by removing the last manufactured global lock. Enberg's
own future-work list names SQLite's single writer as the problem and
Turso's MVCC as the mitigation "which needs to be enabled." vfs
already runs on engines whose MVCC is not experimental. The source of
truth for the corpus is the engine the customer already backs up and
governs; that is the positioning ADR 058 rides on ("the namespace
lives in the database you already run").

Where there is no conflict: a per-agent scratch mount. It is
single-process by nature. Its lifetime is one run or one session. It
wants zero infrastructure. `InMemoryStorage` is that mount today, and
it is already SQLite-shaped, on the same code path as production (the
conformance suite is the contract, not "memory parity"). Enberg's
contribution to this mount is *portability*: make it a file, and let
Turso sync move the file. Concretely, the shape vfs would want, when
roadmap 023 lands per-session namespaces:

- The agent's namespace is a union: the shared corpus mounted
  read-only *below*, a scratch mount *above* that takes creates
  (`MountFlag.CREATE`), so `read → edit → write` loops land in the
  scratch and never touch the corpus without an explicit promote.
  This is agentfs's overlay in vfs's vocabulary — base and delta —
  and roadmap 019 already names the hard part: "shadow filtering
  across union members so search/graph results match what the agent
  can actually read."
- The rules to carry from `SPEC.md:557-614` into 019's design: lookup
  order top → whiteout → base; a whiteout is written when a base
  entry is deleted through the union and removed when a new entry is
  created at that path; a directory listing subtracts the whiteouts
  under it (the spec's `parent_path` index is the right access path —
  the Rust code dropped it and pays a set-membership scan instead,
  §3.4). Skip `fs_origin`: it exists to keep the kernel's inode cache
  happy through FUSE, which vfs does not serve.
- `agentfs diff` is `tree` on the top member plus the whiteout list.
  vfs can answer it today from `updated_at` and the versions table on
  the scratch mount; nothing new.
- The scratch mount can be in-memory (today), or a Turso file that
  `push()`es to a remote so a resumed session on another machine
  `pull()`s it (§5.1, when the gate clears). Either way the shared
  corpus never becomes a SQLite file.

One roadmap line is worth revisiting in that light. "Explicitly not
doing: Persistent (cross-process) sessions — sessions are in-memory
v1; agents reconnect with a fresh session." Enberg's post is the case
for the *v2*: the session's private namespace *and its scratch data*
are what "resume on another machine hours later" means. The 023 story
can keep the session object ephemeral while making the scratch mount
the durable part; that is a smaller change than durable sessions and
buys most of the value.

### 5.3 Time travel: vfs's is logical and already built

agentfs's time travel would be physical — a WAL offset, a page image.
vfs's is logical: every content write mints a version row labeled by
the entry's own monotone `version` with a content hash, reconstruction
walks stored rows in label order, and a numbering gap is itself the
record that a non-content change happened (`version.py` docstring;
ADR 017 pins 1-3). Delete moves to a self-describing trash name and
only `sweep` destroys (ADR 027). This answers "what did `/a` look like
at version 7" by a row lookup, on every engine, with no WAL access. It
does not answer "the whole mount as of 14:02" — ADR 013 pin 4 makes
`updated_at` the only mount-wide cursor and declares it coarse. That
is a deliberate trade (no change-log table; no ordered allocation),
and Enberg's post does not change the calculus: a physical
whole-database rewind is what you get when you have no per-entry
history, and vfs has one. Keep it. Note for the scratch mount: a
"discard this session's scratch" is a mount unbind, and a "keep it" is
a promote — neither needs a rewind.

### 5.4 (c) The audit and read-side record: adopt the ledger, at the right tier

vfs's audit today is write-side: every content write is a version
row, so "what changed, when, to what" is a query. What vfs lacks —
and what agentfs, the Mirage memo (§3.21 snapshot/pin and §3.24 op
records), and the positioning memo's "systems generate evidence" line
all point at — is the **read-side** and **call-side** record: what did
this agent *call*, with what arguments, what did it *read*, at which
version, and what did each call cost. ADR 058 names this as the
Catalog plane's audit story. Three design inputs from agentfs, in
vfs's shape:

1. **One insert per completed call, and mean it.** The spec's rule 5
   ("MUST NOT be updated or deleted") is the property an audit record
   needs; the implementation lost it with a `start()`/`success()` pair
   (§3.3). vfs's `Result` envelope is minted at completion and already
   carries kind, `source` provenance per hop, and `data`; a ledger row
   written *from the envelope*, once, at the `serve()` boundary
   (spec 054) gets insert-only for free. If a `pending` view is
   wanted for a running call, that is a separate, disposable table —
   never an `UPDATE` on the audit row. (This is the same "one record
   type, one store" lesson the Mirage memo drew for the decision
   ledger, §3.9 there, applied in reverse: the audit row is settled
   by construction.)
2. **Key it by principal and session, and record `(path, version)`
   per read.** agentfs's table has neither and lists both as
   extensions. Spec 070 delivers `Principal` and a session facade;
   spec 054 is the boundary that sees every tool call. Every vfs
   `Observation` already carries `version`, so a read's ledger row
   can record the exact versions handed to the agent at zero extra
   cost — which is Mirage's "fingerprint the reads" (§3.21 there)
   with vfs's stronger pin (a content hash exists for every version).
   "Would replaying this session see the same files" becomes a join.
3. **Keep the ledger out of storage.** ADR 013 pin 5 (no background
   work) and ADR 017 (no change-log table) both argue for the ledger
   living beside the server, not inside `DatabaseStorage`. It is
   evidence *about* the namespace, not part of it. Where it is stored
   is open — a dedicated table in the same engine is the obvious
   default, and it is the one place where an append-only, time-keyed
   table on the production engine is exactly right.

The audit row shape agentfs converged on — `name`, `parameters`,
`result | error`, `started_at`, `completed_at`, `duration_ms`, indexed
by name and start time — is a sensible minimum and matches what the
`Result` envelope already knows. Add `principal`, `session`, and the
observations' `(path, version)` list, and vfs has a stronger record
than agentfs's with less machinery.

### 5.5 Two smaller notes

- **Large blobs.** Enberg's "hybrid: big files in S3, metadata in
  SQLite" is the one future-work item that is also a plausible vfs
  item: vfs stores content on the engine, and a multi-gigabyte
  artifact is the case where an engine-resident BLOB is the wrong
  home on every dialect. It is not on the roadmap and should be an
  explicit later-wave line or an explicit non-goal, per the same rule
  the Mirage memo applied to foreign-schema mounts (§4.7 there).
- **Reach.** agentfs runs "anywhere" because its unit is a
  re-implementable schema, and it re-implemented it four times
  (Node, browser, Durable Objects, serverless HTTP) plus a Go SDK on
  a different engine. vfs's reach is SQLAlchemy dialects. The
  open question of 2026-08-16 (full JavaScript and Rust
  implementations) is the same question in vfs's terms, and agentfs
  is evidence for its cost: four ports of one small schema, with
  spec/code drift already visible in two places (§3.3, §3.4).

---

## 6. What not to take

- **Object storage as the source of truth for the shared corpus.**
  The engine is the source of truth; that is what "the namespace lives
  in the database you already run" sells. Postgres, SQL Server and
  Oracle bring replication, backups and point-in-time recovery vfs
  does not need to rebuild on S3.
- **SQLite as the unit of the corpus.** The batch contract and the
  multi-process posture forbid it; ADR 013 spent real work removing
  the one single-writer lock vfs had. The scratch mount is the only
  place the unit fits (§5.2).
- **Last-push-wins merging and transform hooks.** vfs's writers share
  one engine and a version guard; there is nothing to merge. If a
  synced scratch file ever needs to land on the corpus, that is a
  `copy`/`move` through the verb surface, gated and versioned like
  any write — not a row-level replay.
- **Physical, page-level history.** vfs's per-entry versions answer
  the questions agents ask; a WAL rewind answers a question about the
  whole file that ADR 013 chose not to ask (§5.3).
- **Fixed 4 KiB content chunks.** agentfs chunks for random access
  through FUSE; vfs stores content whole and chunks semantically for
  the index. Different job (ADR 036/048).
- **FUSE, NFS, the ptrace sandbox, `agentfs run`.** Out of scope, as
  the Mirage memo already recorded; vfs's `run` is the hermetic
  runtime direction (monty / WASI), where the agent's code comes to
  the data rather than a kernel coming to the file.
- **A KV table.** Its own spec's extension list rebuilds a
  filesystem. Files at paths, with metadata, are the KV.
- **`fs_origin` inode-stability tracking.** A FUSE artifact.
- **The start/finish audit pair.** The one agentfs mechanism that
  contradicts its own spec; take the spec's rule instead (§5.4).

---

## 7. Next steps

1. **Record the corrected premise where it will be read**: a one-line
   note on ADR 028 that spec 084 landed the fallback arm and the live
   in-memory backend is aiosqlite, with this memo's §5.1 as the
   input to the Turso re-attempt (the sync driver is now in pyturso;
   the three adapter blockers are the gate).
2. **Fold §5.2's whiteout rules into roadmap 019** as design input for
   union mounts, and add to 023 the framing that the *scratch mount*
   is the durable part of a session, with the session object staying
   ephemeral — a revision of the "persistent sessions" non-goal that
   keeps its spirit.
3. **Open the audit-ledger design under specs 054/070** with §5.4's
   three rules: one insert per completed call from the `Result`
   envelope; keyed by principal and session, carrying `(path,
   version)` per read; stored beside the server, not inside storage.
   This is the read-side half of the Catalog's audit story and the
   Mirage memo's §4.8 item, now with a concrete row shape.
4. **State the single-writer-replica rule** (§5.1) wherever a Turso
   file mount is first documented: a synced scratch file moves
   between machines; it is never a merge target; two replicas of one
   mount are a pipeline error, the same doctrine as ADR 025.
5. **Add a roadmap line for large-blob offload** (§5.5) as either a
   later wave or an explicit non-goal, not silence.
6. **Cite this memo from the JS/Rust-implementation open question** as
   evidence of what four ports of one schema cost, and of the
   spec/code drift they produce.

---

## Sources

All `agentfs` paths under `~/Git/Repos/agentfs` @ `0a014eb`; all
`turso` paths under `~/Git/Repos/turso` @ `6c7252267`.

- Blog: Pekka Enberg, "Towards a Disaggregated Agent Filesystem on
  Object Storage," 2026-01-11,
  `https://penberg.org/blog/disaggregated-agentfs.html` — sections
  "Problem," "The Agent Filesystem," "Towards a Disaggregated Agent
  Filesystem," "Future Work," "Summary"; Figures 1 and 2. Its
  references used here: Glauber Costa, "Turso Cloud Goes Diskless"
  (2025); Nikita Sivukhin, "Introducing Databases Anywhere with Turso
  Sync" (2025); Enberg and Costa, "The Missing Abstraction for AI
  Agents: The Agent Filesystem" (2025); Enberg, "AgentFS with
  copy-on-write overlay filesystem" (2025).
- agentfs specification and docs: `SPEC.md` (v0.4; tool calls 15-122,
  filesystem 124-485, overlay 487-614, key-value 616-697, revision
  history 699-736), `MANUAL.md` (init/sync flags 15-37, run 90-111,
  sync 168-180, migrate 182-233, timeline 275-287, env 301-317),
  `README.md` (why 37-45, FAQ 180-192, license 209-211),
  `CHANGELOG.md` (0.5.0 sync 144-166; 0.6.0 beta 46-98).
- agentfs Rust SDK: `sdk/rust/src/lib.rs` (`SyncOptions` 84-91,
  `AgentFSOptions` 104-118, `open` 291-368, `pull`/`push`/`checkpoint`/
  `sync_stats` 429-455), `sdk/rust/src/filesystem/agentfs.rs`
  (`DEFAULT_CHUNK_SIZE` 19, `DentryCache` 22-65, `initialize_schema`
  470-613, `pwrite` 1388-1470, `TransactionBehavior::Immediate` sites
  192/246/1249/1410/1615/2309/3096/3611),
  `sdk/rust/src/filesystem/overlayfs.rs` (39-61, 95-127, 137-232),
  `sdk/rust/src/toolcalls.rs` (95-125, 127-262), `sdk/rust/src/kvstore.rs`
  (33-48), `sdk/rust/src/schema.rs` (7-18, 52-104),
  `sdk/rust/src/connection_pool.rs` (14, 19-23), `sdk/rust/Cargo.toml:9`.
- agentfs CLI: `cli/src/opts.rs` (52-63, 106-114, 362-371),
  `cli/src/cmd/sync.rs` (1-46), `cli/src/cmd/init.rs` (19-70, 129-160),
  `cli/src/cmd/mcp_server.rs` (tools listed in `MANUAL.md:145-149`),
  `cli/Cargo.toml:30`.
- agentfs other SDKs and sandbox: `sdk/typescript/src/index_node.ts`
  (26-69), `index_browser.ts`, `agentfs.ts` (9-54),
  `integrations/cloudflare/agentfs.ts` (1-55), `integrations/cloudflare/index.ts`,
  `integrations/serverless/adapter.ts` (1-17);
  `sdk/python/agentfs_sdk/agentfs.py` (15-93), `toolcalls.py` (11-80);
  `sdk/go/agentfs.go` (14, 85-88); `sandbox/src/vfs/mod.rs` (48-60),
  `sandbox/src/vfs/mount.rs` (9-40), `sandbox/src/vfs/sqlite.rs` (11-43).
- turso sync engine: `sync/engine/src/lib.rs` (1-16),
  `types.rs` (`PartialSyncOpts` 40-62, `DatabaseMetadata` 146-178,
  `DatabasePullRevision` 188-197, `DatabaseChange` 297-320),
  `server_proto.rs` (16-45, 61-73, 125-143), `client_proto.rs`
  (6-16, 54-112), `database_sync_engine.rs` (`DatabaseSyncEngineOpts`
  45-91, `checkpoint` 1460, `apply_changes_from_remote` 1879-1880,
  `push_changes_to_remote` 3163-3164, `sync` 3199-3206,
  `pull_changes_from_remote` 3208), `database_sync_operations.rs`
  (`apply_transformation` 3176-3210), `database_tape.rs` (22-40,
  154-156), `database_sync_lazy_storage.rs` (19-52, 222),
  `wal_session.rs` (7-53); `cli/sync_server.rs` (1-80, 165, 554-593,
  900-907); `bindings/python/README.md` (85-140),
  `bindings/python/src/turso_sync.rs` (576-597);
  `docs/manual.md` (167-227, MVCC and `BEGIN CONCURRENT`);
  `CHANGELOG.md` (sync-engine entries; no agentfs mention).
- vfs seams read for the mapping:
  `context/decisions/028-turso-in-memory-backend.md`,
  `013-per-entry-revisions.md`, `017-version-numbers-are-revision-values.md`,
  `025-conflict-redrive-and-single-batch-writer-doctrine.md`,
  `027-delete-never-destroys-sweep-only-destruction.md`,
  `058-the-access-layer-for-agents-positioning.md`;
  `context/specs/archive/084-turso-in-memory-backend/{spec,gate-report}.md`;
  `context/specs/active/054-mcp-serve-locks-topology/spec.md`,
  `070-principal-scoped-sessions/spec.md`; `context/standards/roadmap.md`
  (Waves 3-5, "Explicitly not doing"); `context/open-questions.md`
  (MCP tasks/idempotency; JS/Rust implementations; hermetic runtime);
  `src/vfs/models/rows.py`, `src/vfs/models/version.py`,
  `src/vfs/storage/backends/database/dialects.py`,
  `src/vfs/storage/backends/memory.py` (module docstrings);
  `context/research/2026-09-04-mirage-design-patterns.md` §3.9, §3.21,
  §3.24, §4.7, §4.8; `context/research/2026-08-27-agent-access-layer-positioning.md`
  §3.
