# branchfs and "Fork, Explore, Commit": the branch model, and how it maps onto vfs as an overlay over the versions table

- **Status**: research memo (commits us to nothing; feeds roadmap 023
  (per-session namespaces, `fork()`), roadmap 024 (graph workspace
  sessions), spec 054 (`serve()`), and a possible ADR on "a branch is a
  session-scoped content overlay")
- **Date**: 2026-09-04
- **Owner**: Clay Gendron
- **Question**: branchfs gives every agent an isolated copy-on-write
  branch of a filesystem, reachable at `/@branch-name/`, with an
  advertised O(1) create, atomic commit to the parent, cheap abort, and
  automatic sibling invalidation, all without root. The companion paper
  argues that fork / explore / commit should be operating-system
  primitives for agents. What is the branch / commit / abort model
  precisely, what are its semantics and failure modes, and how would a
  branch map onto vfs as a **namespace overlay on top of the versions
  table** rather than a filesystem-level copy-on-write?
- **Method**: a line-level read of the whole branchfs Rust tree at
  `~/Git/Repos/branchfs` (`src/branch.rs`, `fs.rs`, `fs_ctl.rs`,
  `fs_path.rs`, `fs_helpers.rs`, `daemon.rs`, `main.rs`, `storage.rs`,
  `inode.rs`, `error.rs`, `platform/linux.rs`), its `README.md`,
  `bench/README.md`, the shell and Rust test suites, and the git
  history (every commit message; three commits diffed). The paper was
  fetched from `arxiv.org/html/2602.08199v1` in three passes
  (abstract and introduction; design; evaluation, related work,
  limitations). Then a read of the vfs seams the mapping lands on:
  `models/version.py`, `models/entry.py`, `results/kinds.py`,
  `storage/protocol.py`, `storage/backends/database/{writes,staging,
  topology,dialects}.py`, `base.py` (`write`, `edit`), ADRs 013 / 017 /
  025 / 027, the roadmap, the archived specs 023 and 024, and the
  Mirage memo §3.21–3.22. Cites and describes only; every line of vfs
  code stays ours.
- **License**: MIT (`LICENSE`, "Copyright (c) 2026 Multikernel
  Technologies, Inc."). Study freely; copy nothing.
- **Sources line**: `multikernel/branchfs` @ `a4b6592` (2026-05-22),
  78 commits since 2026-02-01, 77 of them by one author (Cong Wang),
  Rust, 4,994 source lines + 1,366 test lines, 740 KB checkout. Paper:
  arXiv 2602.08199v1, "Fork, Explore, Commit: OS Primitives for Agentic
  Exploration", Cong Wang (Multikernel Technologies) and Yusheng Zheng
  (UC Santa Cruz), submitted 2026-02-09.

---

## 1. Bottom line

branchfs is small, honest, and worth reading. It is a FUSE filesystem
(FUSE: a kernel facility that lets an ordinary user process answer
filesystem calls). Each branch is a directory of changed files (the
**delta**), a list of deleted paths (**tombstones**, also called
whiteouts), and — since May 2026 — a full copy of the parent's visible
tree taken at fork time (the **inherited snapshot**). Commit copies the
delta into the parent and bumps a counter. Abort deletes the branch's
directory. That is the whole model. It is about 1,300 lines of Rust.

Four findings matter for vfs:

1. **The paper's O(1) fork is no longer what the code does.** The
   February paper measured a lazy design: an unmodified file was found
   by walking up the branch chain to the base, so creating a branch
   cost one `mkdir`. On 2026-05-19 the author replaced that with an
   eager copy of the parent's whole visible tree into `inherited/`
   (commit `62dd895`, "Fix branch snapshot isolation"). The README's
   "O(1) branch creation" row became "Snapshot Isolation", and the
   bench README's expectation went from "~300 µs constant" to "scales
   with visible parent tree size" (§4.2). The reason is instructive:
   the lazy design leaked later parent writes into an already-forked
   child. A frozen view of the *whole* tree cannot be had for free in
   a system that has no snapshot coordinate. vfs has no mount-wide
   snapshot coordinate either, by decision (ADR 013 pin 4), so it
   should not promise one. It should promise something cheaper and
   more exact instead: a **pin per touched entry** (§5.1).
2. **"Sibling invalidation" is a counter compare at commit time, not a
   merge rule.** A branch records the parent's `commit_count` at fork.
   Commit refuses with `ESTALE` if the parent's count has moved
   (`branch.rs:805-815`). That is the paper's "first-commit-wins": the
   loser is refused even when it touched disjoint files, and the code
   never looks at which files changed (§4.4). vfs's per-entry version
   guard (`writes.py:827`) is strictly finer: siblings with disjoint
   write sets both commit, and an overlapping sibling gets exact
   per-row `conflict` blame (ADR 025). The paper lists "file-level
   union of non-overlapping changes" as future work; vfs has it by
   construction (§5.4).
3. **Commit is atomic per file, not per branch, and branches do not
   survive a restart.** Commit stages copies beside their destinations
   and publishes them with a loop of renames (`branch.rs:185-194`); a
   crash mid-loop leaves some files published and some not. The daemon
   deletes every branch directory on start (`daemon.rs:98-105`). vfs's
   write batch is one transaction per mount and either lands whole or
   runs no mutation (`writes.py:1-19`), so a vfs commit is strictly
   more atomic within a mount, and the "branches are session-scoped
   and in-memory" stance already on the roadmap is parity, not a gap
   (§5.2, §5.3).
4. **The paper is a position paper with microbenchmarks.** It evaluates
   only branchfs, against no baseline, on no agent workload: sub-350 µs
   create (on the old lazy design), 317 µs–2.1 ms commit, 315–890 µs
   abort. The proposed `branch()` syscall — process groups, memory
   copy-on-write, kernel-enforced sibling isolation — is unimplemented.
   Its strongest argument, atomic composition of fs + process + memory
   isolation, is about the OS, not about a storage layer, and does not
   transfer (§3, §6).

What vfs should take is the **shape**, not the mechanism: a branch is a
session-scoped overlay of `path → (base pin, new content | tombstone)`
above the shared, immutable versions table; **fork** is allocating an
empty overlay (truly O(1)); **commit** is one guarded write batch — the
verbs, the `conflict` kind, and the redrive doctrine already exist;
**abort** is dropping the overlay, which minted nothing and so needs no
sweep. The one real gap is that vfs's guard today compares against the
row the write transaction itself just read, not against a version the
caller read earlier — there is no caller-supplied precondition on
`write`/`edit`/`delete`. That parameter is the whole schema-free
enabler (§5.2). No new table is needed; at 10,000 entries the commit is
exactly today's chunked batch (§5.5).

One line: **take branchfs's fork / commit / abort vocabulary and its
tombstone-and-delta overlay shape, put the overlay in the session above
the versions table with per-entry pins instead of a tree copy, and let
the existing version guard be the commit — nothing to copy at fork,
nothing to sweep at abort, and a finer conflict rule than the paper
proposes.**

---

## 2. What branchfs is

**Shape.** One daemon process per storage directory (`daemon.rs`),
holding one shared `BranchManager` (`branch.rs:375-391`) for every
mount it serves. A mount is a FUSE session at a mountpoint; a mount is
"on" one branch at a time (`mount_branches`, `branch.rs:388`). The base
directory is any existing directory on any filesystem — ext4, xfs, NFS
— which is the project's portability claim (README, "Why not btrfs /
dm-snapshot").

**Terms.** *Copy-on-write* (CoW): a file is shared with the parent
until the first write, when a private copy is made. *Whiteout* or
*tombstone*: a marker saying "this path is deleted here, even though a
lower layer still has it". *Overlay*: a view built by stacking a
changed layer over an unchanged one, resolving each name in the top
layer first.

**On disk.** Under `<storage>/branches/<name>/` (`branch.rs:246-249`):
`files/` (the delta — full copies of every file this branch wrote),
`inherited/` (the frozen snapshot of the parent's visible tree at fork),
and `tombstones` (an append-only text file, one deleted path per line,
loaded into a set at open — `branch.rs:272-296`). `main` is a branch
too, with an empty `inherited/`; its "inherited" source is the live
base directory (`branch.rs:648-654`).

**In memory.** `Branch` (`branch.rs:223-237`): name, parent name, the
three paths, the tombstone set, a `commit_count` (how many children
have been merged into this branch), and `parent_version_at_fork` (the
parent's `commit_count` when this branch was created). `BranchManager`
adds one global `epoch` counter (`branch.rs:380`), FUSE notifiers per
(branch, mount) for kernel cache invalidation, and a quota counting
delta bytes only (`branch.rs:16-87`).

**The agent surface.** Every non-main branch is a virtual directory
`/@name/` at the mount root, so one mount serves many agents without
switching (`fs_path.rs:18-41`). Each branch has its own control file
`/@name/.branchfs_ctl`; the root has `/.branchfs_ctl`. Writing
`create[:name]`, `commit`, or `abort` to a control file drives the
lifecycle (`fs_ctl.rs:40-162`); three `ioctl`s do the same for programs
(`platform/linux.rs:7-9`, `fs.rs:1559-1642`). The README's suggested
multi-agent pattern is one mount, one `@branch` per agent, each agent
bind-mounting its own `@branch` path as its workspace root.

**History in one paragraph.** Initial commit 2026-02-01. Per-mount
isolation (02-02) was replaced by one shared manager (02-06).
Commit-to-root became commit-to-immediate-parent (02-07). First-wins
conflict detection arrived 02-09. Nested `/@parent/@child/` paths were
removed for a flat namespace (02-10) — the README still shows the
nested form, which is stale. Rename, symlinks, a quota, tombstone
compaction, and a macOS port followed through March. Then two
correctness fixes in May: the eager inherited snapshot (05-19) and the
staged, rollback-able commit (05-22, "prevent silent data loss on merge
failure"). The paper predates both May fixes.

---

## 3. The paper's argument

**The abstraction.** A *branch context* is a filesystem view with a
copy-on-write delta layer plus a process group, with a three-phase
lifecycle: **fork** (N contexts created atomically from a frozen
origin), **explore** (each runs in isolation), **commit / abort** (one
wins, the rest are discarded). Four stated semantics (§3.3): *frozen
origin* — the parent becomes read-only while children exist,
"eliminating merge conflicts by construction"; *parallel isolated
execution* — no context can observe another; *first-commit-wins* —
the first committer's state replaces the parent and all siblings are
invalidated; *nested contexts* — a branch may fork sub-branches, each
committing to its immediate parent only.

**Two implementations.** branchfs (the FUSE one, this memo's subject)
and a proposed Linux syscall
`branch(int op, union branch_attr *attr, size_t size)` with
`BR_CREATE` / `BR_COMMIT` / `BR_ABORT` and flags `BR_FS` (a mount
namespace with a branched filesystem), `BR_MEMORY` (page-table
copy-on-write; the parent's pages go read-only), `BR_ISOLATE`
(kernel-enforced signal and ptrace barriers between siblings),
`BR_CLOSE_FDS`. `BR_CREATE` returns 0 to the parent and 1..N to
children, like `fork()`. Siblings of a committer receive `-ESTALE` and
are terminated. The syscall is not implemented; the authors target
Linux 6.19 with `BR_FS` and `BR_ISOLATE` first.

**Why the OS.** The paper's case is about *composition*: setting up
cgroups, PID and mount namespaces, a filesystem branch, and signal
barriers from user space is "a multi-step process with race windows
between steps" and "error-prone cleanup on partial failure"; a syscall
composes them atomically with kernel-side cleanup, "following the same
rationale that motivated `clone()` over manual `fork()` + `unshare()`
sequences". Three things it says user space cannot do at all: memory
copy-on-write, stopping a process escaping its group via `setsid()`,
and preventing cross-branch signal / ptrace interference. Its critique
of current practice: git stashing and container clones are heavy and
cannot capture shell side effects like `npm install`; per-file
snapshots (it names Claude Code) miss shell-command changes and have no
parallel branching; overlayfs, btrfs, and dm-snapshot lack
commit-to-parent, nesting, or unprivileged operation.

**Evaluation.** branchfs only. No baseline. No agent task, no
SWE-bench-style workload. Hardware: a Ryzen 5 5500U laptop, 8 GB, NVMe,
Linux 6.17. Numbers: branch creation under 350 µs, flat from 100 to
10,000 base files (the lazy design — see §4.2); commit 317 µs at 1 KB of
change to 2.1 ms at 1 MB; abort 315–890 µs over the same range;
sequential read 1,655 MB/s through FUSE and 7,236 MB/s with FUSE
passthrough (a kernel feature that lets reads bypass the daemon);
write 631–719 MB/s. The claims are "O(1) creation" and "modification-
proportional commit".

**Conflicts and merge.** There is no merge. "Any context may commit;
the first to do so wins, and all siblings are invalidated." Future work
lists three rungs: file-level union of non-overlapping changes,
conflict detection for overlapping files, semantic merge.

**Positioning.** overlayfs / UnionFS: no commit-to-parent, no sibling
invalidation, needs root. btrfs / ZFS: nested subvolumes but tied to
one filesystem type, no commit-to-parent. dm-snapshot: block device
required, O(depth) reads. DAXFS: branching with commit and sibling
invalidation, but memory-backed and not portable. Containers and VMs:
whole-VM overhead. TxOS: deep kernel changes, flat short transactions.
Speculator and OS speculation: sequential, owner-decided acceptance,
where branch contexts are parallel and competitive. Git worktrees are
not in the related-work section; git appears only in §2.1 as an ad hoc
workaround. **agentfs is not cited** in the version fetched.

**Stated limitations.** Symlinks with absolute targets resolve outside
the branch; hard links lose their link on copy; FIFOs, sockets, and
device nodes are unsupported in the delta; disk exhaustion is
`-ENOSPC`. And the one that matters most for agents: "external side
effects (network, IPC, device I/O) are not rolled back on abort"; the
proposed fix is *effect gating* — buffer external actions until commit.

---

## 4. The branch model in detail

### 4.1 Resolution: how a path is found

`resolve_path_locked` (`branch.rs:684-708`) is the whole read model.
For a branch and a relative path: if the path is in the branch's
tombstone set, it does not exist. Else if the delta has it, the delta
file is the answer. Else the inherited source is consulted — the
`inherited/` snapshot for a real branch, the live base directory for
`main` (`branch.rs:648-654`). There is no chain walk any more: a
branch's view is exactly *its delta over its frozen snapshot*. A
grandchild never looks at its grandparent, because the grandparent's
view was copied into the child's snapshot, and the child's view into
the grandchild's.

Directory listing is the union of the delta directory's names and the
inherited directory's names (`branch.rs:656-682`), then each name is
re-resolved so tombstones drop out and the file type is read from the
winning layer (`fs_helpers.rs:156-210`). The kernel's name cache is
given a TTL of zero so every lookup revalidates (`fs.rs:26`).

### 4.2 Fork: what is snapshotted, and when

`create_branch` (`branch.rs:466-497`): validate the name (no `/`, no
leading `@`, at most 255 bytes — `branch.rs:347-373`), take the
manager's **write lock**, refuse a duplicate, read the parent's
`commit_count` into `parent_version_at_fork`, make the three
directories, then `snapshot_visible_tree` (`branch.rs:710-759`) walks
the parent's visible tree — resolving every name through §4.1, so the
parent's own tombstones and deltas are honored — and **copies every
regular file and symlink** into `inherited/` with `fs::copy`
(`storage.rs:22-34`). Only then is the branch inserted into the map. On
any error the half-built directory is removed.

So the snapshot instant is "under the write lock, at create". Because
the lock is held for the entire copy, **every path resolution on every
mount blocks while a branch is being created**, and the create is
O(bytes in the parent's visible tree). The bench README now says so
(`bench/README.md`, "includes materializing the inherited snapshot ...
Expected: scales with visible parent tree size"). Before `62dd895` the
code walked the chain lazily and the README promised O(1); the diff of
that commit rewrites both the README feature row and the bench
expectation. The motivating bug is visible in the tests that landed
with it: a child must not see a file the parent wrote *after* the fork
(`tests/test_branch_dirs.sh:185-194`).

Note what is *not* frozen: the paper's "frozen origin" (parent
read-only while children exist) is **not enforced**. A write on `main`
while branches exist goes into `main`'s own delta (`fs.rs:743-749`,
which calls `ensure_cow` with no check for live children), and the
test above writes to a parent branch after forking a child. Isolation
comes from the child's copy, not from freezing the parent.

### 4.3 Write, delete, rename inside a branch

*Write* (`fs.rs:653-800`): on the first write to a path,
`ensure_cow_for_branch` (`fs_helpers.rs:46-73`) copies the resolved
source file into the delta (charging the quota) and the write lands on
the copy; later writes hit a cached descriptor. File-level, not block-
level: a one-byte change copies the whole file, which the paper calls
"coarser than block-level but simpler to implement correctly".

*Delete* (`fs.rs:1041-1131`): append the path to the tombstone file,
and remove any delta copy. `rmdir` is the same code. Tombstones
compact when stale lines outnumber live ones (`branch.rs:298-310`).

*Rename* (`fs.rs:1138-1310`): refused across branches (`EXDEV`,
`fs.rs:1210-1213`). Within a branch: copy the source into the delta if
it is not there yet, rename inside the delta directory, tombstone the
source, tombstone the old destination if one existed, and remove any
tombstone on the new destination (`fs.rs:1272-1282`). **A rename is
therefore recorded as a delete plus a new file**; at commit the
destination is copied whole and the source is deleted. No rename
identity survives.

### 4.4 Commit

`commit` (`branch.rs:782-949`) in order:

1. Refuse `main` (`CannotOperateOnMain`).
2. Take the manager's write lock — held until the branch map is
   updated (`branch.rs:871`, `:935`), so all resolution on all mounts
   blocks for the whole merge, copies included.
3. Refuse a branch that has children (`NotALeaf`,
   `branch.rs:776-778`, `:794`). **Only leaves commit or abort.**
4. **First-wins check** (`branch.rs:805-815`): if the parent's
   `commit_count` is not the value recorded at fork, refuse with
   `Conflict`, which both control interfaces report as `ESTALE`
   (`fs_ctl.rs:198-201`, `fs.rs:1611-1614`). This is the entire
   conflict rule. It does not look at paths. Two siblings that changed
   different files still conflict; the second one to commit loses and
   its delta is kept for the agent to retry or abort.
5. If the parent is `main`, merge into the **base directory**
   (`branch.rs:820-883`); otherwise merge into the **parent's delta**
   (`branch.rs:884-946`). Both go through `StagedMerge`
   (`branch.rs:100-211`): deletions are renamed aside to a
   `.branchfs-trash.<name>` sibling, copies are written to a
   `.branchfs-tmp.<name>` sibling, and only when every copy succeeded
   are the temps renamed into place and the trash removed
   (`branch.rs:185-194`). If staging fails, `Drop` puts everything
   back (`branch.rs:197-211`). This is the 2026-05-22 fix; before it a
   failed copy could be reported as success.
6. Nested-parent bookkeeping: child tombstones are added to the parent's
   set (so a child delete shadows a parent delta), and any path the
   child wrote is removed from the parent's tombstones (a child write
   revives a parent delete) — `branch.rs:900-920`. Main-parent
   bookkeeping: `main`'s own delta copies of committed or tombstoned
   paths are removed so the fresh base wins (`branch.rs:846-855`).
7. Bump the parent's `commit_count`, remove the branch and its
   directory, bump the global `epoch` (`branch.rs:858-869`,
   `:923-932`).
8. Drop the lock and invalidate the kernel's cache: every mount for a
   commit to `main` (`invalidate_all_mounts`, `branch.rs:560-604`), or
   just the child and parent for a nested commit (`branch.rs:934-936`).
9. If the mount that issued the commit was on the committed branch, it
   switches to the parent (`fs_ctl.rs:178-181`); the `ioctl` path never
   switches (`fs.rs:1600-1615`).

Atomicity, stated honestly: each rename is atomic; the publish loop is
not. A crash inside step 5's publish leaves a mix of old and new files
plus stray side files; the next commit clears a stale trash sibling
before reusing the name (`branch.rs:148-150`) but nothing reconciles
the mix. And the whole staged merge holds the global lock, so the cost
of commit is paid by every reader.

### 4.5 Abort

`abort` (`branch.rs:953-994`): refuse `main`, refuse a non-leaf, remove
the branch from the map, `remove_dir_all` its directory (delta,
snapshot, tombstones), invalidate the kernel cache for that branch. The
parent and siblings are untouched. **Abort does not bump the epoch**;
the mount that was on the branch learns it is gone because
`is_branch_valid` now fails (`fs.rs:1960-1977` pins this). Cost is
O(delta + snapshot) filesystem removal.

### 4.6 Sibling invalidation, epochs, and the `ESTALE` story

Two distinct mechanisms carry the word "invalidation":

- **Mount-level staleness.** Each FUSE mount remembers the epoch it
  last synced to (`fs.rs:118`). `is_stale` (`fs.rs:163-167`) is "the
  global epoch moved, or my branch no longer exists". Nearly every
  callback — lookup, getattr, read, write, readdir, create, unlink,
  rename, mkdir, symlink, readlink — returns `ESTALE` while stale
  (`fs.rs:327`, `:548`, `:684`, `:869`, ...). A mount resyncs its epoch
  only when *it* performs a control operation (`fs_ctl.rs:76-77`,
  `:149-150`, `:176-177`; `fs.rs:1586`, `:1606`, `:1626`). So after any
  commit anywhere, every *other* mount served by the daemon answers
  `ESTALE` to everything until someone writes to its control file.
  Within the README's one-mount, many-`@branch` pattern this does not
  bite: the commit came through that mount, so it resynced itself and
  the other agents' `@branch` paths keep working ("agent-b is
  unaffected", README). With genuinely separate mounts it bites hard.
  The 2026-05-22 fd-cache fix (`84965c5`) exists because the fast
  read/write paths once skipped this gate and served a file a commit
  had just replaced.
- **Branch-level first-wins.** A sibling is never told at commit time.
  It finds out when *it* commits and the counter compare fails (§4.4
  step 4). The README's "sibling_a does not see sibling_b's post-fork
  commit" test (`tests/test_commit.sh:133-150`) is exactly that: the
  sibling keeps its frozen view and keeps working.

The README promises "memory-mapped regions trigger `SIGBUS` on next
access". **There is no SIGBUS code.** The effect is emergent: the
notifier's `inval_inode` drops the kernel's cached pages, the next page
fault re-reads through FUSE, the read returns `ESTALE`, and the kernel
delivers `SIGBUS` to a mapped access it cannot satisfy. It works, but it
is a consequence of the epoch gate, not a designed signal.

### 4.7 Consistency and crash behavior, summarized

| Question | Answer in the code |
| --- | --- |
| What does a parent reader see while a child is live? | The parent's own view; nothing of the child (the child's delta is in its own directory). |
| What does a child see of parent writes after the fork? | Nothing — its snapshot is a copy (`62dd895`). |
| What do two children see of each other? | Nothing (`tests/test_integration.rs:380-404`). |
| Is fork atomic? | Yes, under the global write lock; O(tree bytes). |
| Is commit atomic? | Per file. The publish loop is not; a crash mid-loop leaves a mix. |
| Can a non-leaf commit or abort? | No (`NotALeaf`). |
| Does the parent freeze while children exist? | No (not enforced; paper says yes). |
| What survives a daemon restart? | Nothing — `branches/` is wiped on start (`daemon.rs:98-105`). |
| Conflict rule | Parent `commit_count` moved since fork → `ESTALE`, regardless of paths. |
| Quota | Delta bytes only (`--max-storage`); snapshot copies are not charged. |

### 4.8 Costs and limits, as stated and as read

Stated (README, bench, paper): create < 350 µs on the lazy design;
commit linear in modified bytes; abort near-constant; FUSE overhead
"negligible" next to LLM latency; passthrough gives near-native reads.

Read from the code at `a4b6592`: create is O(visible tree bytes) under
a global lock; commit is O(delta bytes) copy plus O(delta files)
renames under the same lock; abort is O(delta + snapshot) unlink; every
branch stores a **full copy of the tree**, so N agents on a T-byte tree
cost N × T of disk, uncharged by the quota. Symlink, hard link, and
special-file limits per §3. Names are `String`-lossy in readdir
(`branch.rs:670`), so non-UTF-8 names can collide in listings though
the commit side paths handle them (`branch.rs:217-221`).

---

## 5. Mapping onto vfs

Legend: **adopt** — take the concept now, in vfs's shape; **adapt** —
take it when the roadmap reaches the consumer; **parity** — vfs already
has it, sometimes better; **skip** — a consequence of a bet vfs did not
make.

| # | branchfs / paper item | vfs today | Verdict |
| --- | --- | --- | --- |
| 1 | A branch is an isolated view: delta over a frozen parent, with tombstones | none; spec 023 designs a *mount* overlay, not a content overlay | **adopt** as a session-scoped content overlay (§5.1) |
| 2 | Fork copies the parent's whole visible tree | immutable version rows keyed `(entry, version)` with a content hash | **skip the copy; adapt as pins** (§5.1) |
| 3 | Resolution order: tombstone → delta → inherited | — | adopt (the overlay's lookup order) |
| 4 | Tombstones for delete; rename = tombstone + new file | delete trashes, sweep destroys (ADR 027); `move` is a verb | adopt the marker; commit maps to `delete` / `move` verbs |
| 5 | Listing = union of layers minus tombstones | `ls` / `tree` / `glob` are storage SELECTs | adapt: overlay merge at the router; see §5.5 for the cost |
| 6 | Only a leaf commits, into its immediate parent | — | adopt |
| 7 | First-commit-wins on a parent counter; loser gets `ESTALE` for the whole branch | per-entry `version` guard; `conflict` (ESTALE) with `retry_class=refresh`; whole-batch redrive (ADR 025) | **parity-plus**: skip first-wins, keep the per-entry guard (§5.4) |
| 8 | Staged merge with rename publish; per-file atomic | one transaction per mount batch; no mutation on any error | parity (vfs stronger per mount; per-mount is the ceiling) |
| 9 | Abort removes the branch directory | — | adopt: drop the overlay; nothing minted, nothing to sweep (§5.3) |
| 10 | Global epoch; every op `ESTALE` after a foreign commit; emergent SIGBUS | `conflict` on write only; reads never fail for staleness | adapt as an explicit drift check; never fail reads (§5.4) |
| 11 | Frozen origin: parent read-only while children live (paper) | many concurrent writers by design (ADR 013, 025) | skip (branchfs does not enforce it either) |
| 12 | `/@branch/` virtual paths; bind-mount one per agent | MCP-session ↔ VFS-session binding planned (spec 023 §6) | adapt: the branch *is* the session; a `/.branches/` ctl tree later |
| 13 | Control file + `ioctl` lifecycle API | `/.mounts/ctl` idiom (017), clone idiom (024) | adapt later, same idiom |
| 14 | Quota on delta bytes | row caps, `truncated` | adapt later: an overlay byte budget per session |
| 15 | Branches die with the daemon | "sessions are in-memory v1" (roadmap, not-doing list) | parity |
| 16 | `branch()` syscall, `BR_MEMORY`, `BR_ISOLATE`, effect gating | out of scope | skip; note effect gating for the `run` verb (§6) |
| 17 | No merge; disjoint-file union is future work | per-entry guard gives disjoint union for free | parity-plus |
| 18 | Paper: no baselines, no agent workloads | — | a positioning fact, not a design input |

### 5.1 (a) What a branch is in vfs terms

A branch is a **session-scoped overlay** above the shared store. It
holds two maps and a name:

- **Delta**: `path → (new content | tombstone | moved-to)`. What the
  agent wrote, deleted, or moved in this branch. Same job as
  branchfs's `files/` plus `tombstones`, minus the copies: vfs holds
  the new content in memory (or, later, in a persisted overlay row),
  never a copy of the unchanged file.
- **Pins**: `path → (version, content_hash)` for every entry the branch
  has **read or written**. A pin is the exact version row the agent
  saw. This is the Mirage triad's "pin is the recovery" (Mirage memo
  §3.21) and its read-stamp (§3.22), and it is what branchfs's
  `parent_version_at_fork` is trying to be — except per entry, not per
  parent.
- **Parent**: `main` (the live store) or another branch's overlay, for
  nesting.

Reads resolve like branchfs §4.1: tombstone → delta → parent. The
difference is the bottom layer. branchfs's bottom layer is a *copy*
made at fork; vfs's is the *live store*, read through, with every read
stamping a pin. That means a vfs branch is **not** a frozen view of the
whole tree. It is a frozen view of **what the branch touched**, and a
live view of everything else. Two consequences, both deliberate:

- It is honest about what vfs can promise. ADR 013 pin 4 says there is
  no mount-wide total order and `updated_at` is coarse; vfs cannot
  answer "the tree as of instant T" without either a tree copy
  (branchfs's May design, O(tree) per fork) or an MVCC snapshot the
  store does not expose across engines. A per-entry pin needs neither.
- It is what an agent actually needs. An agent's exploration is "read
  these files, change some of them, run something, decide". The pin
  set is exactly the set of facts the decision rested on. A file the
  agent never opened cannot have influenced it; if it later opens one,
  it gets the live version and a fresh pin — which is what the lazy
  branchfs did before May, and the reason that design leaked is that
  it had *no pins*: it could not tell a fork-time read from a
  post-fork read. vfs can.

This is the same overlay shape spec 023 already designs for
**mounts** ("reads see parent ∪ overlay; edits mutate only overlay").
A branch is that pattern one plane down — an overlay of *entries*
instead of *mount bindings* — and it belongs in the same `VFSSession`
object: a session owns a mount overlay (023) and may own a content
overlay (this memo). `fork()` in 023 copies the mount overlay; a
branch fork copies the delta and pin maps (a nested branch), which is
O(delta), and an empty fork is O(1) — the number the paper claimed and
the code no longer delivers.

### 5.2 (b) What commit means

Commit is **one write batch guarded on the pins**. For every delta
entry: a `write` guarded by the pinned base version (a create is
guarded by "no row exists"), a `delete` for every tombstone guarded the
same way, a `move` for every rename. The batch lands or refuses
**whole**: `writes.py:1-19` — "a failed batch runs no mutation
statement at all" — and the guard is the `WHERE version = :base`
predicate every material update already carries (`writes.py:728`,
`:827`, `:835`). The refusal kind already exists: `vfs.conflict`
(ESTALE), `retry_class=refresh`, `data` may carry the current
`version` (`kinds.py:47`, `:76`, `:197-201`). The re-drive doctrine
already exists: a conflict-carrying batch redrives per row for exact
blame, and that is the accepted design (ADR 025 §1). Nested commit is a
map merge into the parent overlay, with branchfs's two tombstone rules
(§4.4 step 6) carried over: a child tombstone shadows a parent delta; a
child write revives a parent tombstone.

**The gap.** Today the guard compares against the version the write
transaction *itself* just read: `staging.py:328-329` takes
`base_version` from the committed row fetched at the top of the same
batch. That defends against lost updates inside the batch's own
window. It does **not** let a caller say "I read version 7; refuse if
it is not still 7". No public verb carries such a precondition:
`write` takes `entries`, `overwrite`, `parents` (`protocol.py:165-172`,
`base.py:765-774`); `edit` and `delete` accept `observations=`, and an
`Observation` does carry `version`, but the backend consumes those rows
only as an address list through `targets_of` (`backend.py:228-260`).
The Mirage memo §3.22 assumed this precondition already existed at the
storage tier; it does not. `Entry` cannot carry it either — ADR 017's
naming pin 2 says `Entry` carries no version, and that is right: the
precondition is a *request* fact, not an entry fact.

So the enabler is one parameter: a caller-supplied precondition map
(`path → expected version`, or the pinned `Observation` rows honored
for their `version`, not just their path) on `write`, `edit`, `delete`,
and `move`. When present, `StagedEntry.base_version` is the caller's
number instead of the freshly read row's, and everything downstream —
set-based VALUES guard on Postgres, executemany aggregate elsewhere,
`guard_miss` re-probe or redrive per dialect (`writes.py:759`, `:804`)
— works unchanged. That parameter is also what `serve()` (spec 054)
needs for tool-tier stale-write protection, so two roadmap items want
the same seam.

Atomicity: within one mount, a vfs commit is strictly stronger than
branchfs's (one transaction vs a rename loop). Across mounts it is
per-mount, which the roadmap fixes as the ceiling ("no cross-mount
2PC"). A branch whose delta spans mounts commits one mount at a time,
and the session should say so in the result rather than pretend.

### 5.3 (c) What abort means

Drop the overlay. Nothing was written to storage — the delta lived in
the session, and pins are read-side facts — so **no row was minted and
nothing needs sweeping**. ADR 027 is not even engaged: delete-trashes
and sweep-destroys govern rows, and a branch that never committed made
none. This is cheaper than branchfs (no directory to unlink) and
exactly as safe. The only cost is releasing memory. If overlays are
ever persisted for durability (§5.5), abort becomes a delete of overlay
rows, and *that* would fall under ADR 027's trash discipline like any
other row.

### 5.4 (d) Sibling invalidation when two agents branch the same base

Both agents fork from `main`. Each has its own delta and pins. Agent A
commits: `main`'s versions tick for A's paths only. Agent B is told
nothing — same as branchfs within one mount (§4.6). Then:

- **B commits with a disjoint write set.** Every guard matches; B's
  batch lands. This is the paper's "file-level union of non-overlapping
  changes", listed there as future work, delivered here by the
  per-entry guard with no new code.
- **B commits with an overlapping write set.** The overlapping rows
  miss their guard; the batch refuses whole with per-row `conflict`
  blame naming exactly which paths moved and (in `data`) their current
  versions. B re-reads those paths, re-applies its edits — `edit` is
  find-and-replace, so a non-overlapping textual change often
  re-applies cleanly — and commits again. Three-way merge is the
  agent's job, as it is in git; the paper's "semantic merge" rung is
  the same statement.
- **B wants to know before committing.** A `drift` check compares B's
  pins to the live versions: one chunked `SELECT entry_id, version
  WHERE entry_id IN (...)` (§5.5) and a set difference. This is
  Mirage's fingerprint verifier and branchfs's epoch, made explicit
  and made *optional*. vfs should **not** make reads fail on drift the
  way branchfs's mount-level `ESTALE` does; a read after a sibling
  commit is a fresh pin, not an error.

Compared with first-commit-wins: vfs refuses less (disjoint siblings
both win), refuses more precisely (per row, with the current version),
and never needs the parent counter. The one thing first-commit-wins
buys — "exactly one of N explorations lands" — is a *policy* an
orchestrator can impose on top (abort the others after the first
commit) and should not be baked into storage.

### 5.5 (e) Schema, and cost at 10,000 entries

**Schema: none for v1.** The overlay lives in the session. The versions
table already has what a pin points at: `(entry_id, version_number)`,
`content_hash`, and content or a diff reconstructable to it
(`models/version.py` docstring; ADR 017 pins 1–3). A persisted overlay
— for a branch that must outlive a process — would be two tables
(`branches`, `branch_entries(branch_id, path, base_version, content |
tombstone)`); the roadmap's not-doing list defers persistent sessions,
and branchfs's own "wiped on daemon start" behavior is the same stance,
so this is a later wave with no pressure behind it.

**Cost of the verbs at a 10,000-entry delta**, on the engines CLAUDE.md
names:

- **Fork**: O(1) — allocate two empty maps. Copies nothing. (branchfs
  at `a4b6592`: O(tree bytes) under a global lock.)
- **Read through the branch**: one stat / read per path as today, plus
  a map insert for the pin. Listing a directory through a branch is
  the storage listing merged with the overlay's entries under that
  directory minus tombstones — O(listing + overlay entries at that
  level), all in Python over stdlib maps, which is the "small sets and
  lists stay stdlib" rule.
- **Drift check on 10,000 pins**: `id IN (...)` chunked by
  `membership_budget` (`dialects.py:423-429`) — Oracle's 1,000-element
  floor gives 10 statements; SQL Server's ~2,100-parameter budget gives
  5; Postgres one or a few. Each returns two small columns.
- **Commit**: exactly today's write batch. One `path IN` select for
  targets and ancestors (chunked the same way), a staging pass in
  Python, then bulk inserts layered parents-before-children within the
  dialect's `insertmanyvalues_max_parameters`, guarded updates
  set-based via `VALUES` where declared (`values_join`,
  `dialects.py:95-100`) or executemany with an aggregate rowcount
  elsewhere, and guarded parent bumps (`writes.py:1-19`). A clean
  10,000-row commit costs what a clean 10,000-row `write` costs now; a
  conflict-carrying one redrives per row on the aggregate-arm engines
  (SQLite, MySQL family, Oracle), which ADR 025 accepted with the "one
  batch writer per subtree" doctrine — and a branch commit is
  precisely one batch writer.
- **Abort**: free.

Two rules from the repo's own posture to carry into the spec: the
overlay must not become a hard scale cap (no "max 10,000 entries per
branch"; if memory becomes the limit, name a byte budget per session
like branchfs's quota and classify the refusal), and any TTL-style
cleanup of abandoned branches must run at verb time, not on a timer
(ADR 013 pin 5 — storage owns no background work; spec 024's "TTL
fallback" needs the same reading).

---

## 6. What not to take

- **The eager tree snapshot.** It is branchfs's answer to "no snapshot
  coordinate", and it costs O(tree) per fork plus N copies of the tree
  on disk. Pins answer the same question per entry at O(touched).
- **First-commit-wins as the conflict rule.** Coarser than the per-entry
  guard vfs already has; refuses disjoint siblings; carries no blame.
  If an orchestrator wants exactly-one-winner, it aborts the others.
- **Frozen origin.** The paper's "parent read-only while branches
  exist" would serialize every writer on a mount behind any open
  branch — the exact contention ADR 013 removed. branchfs does not
  enforce it either.
- **Mount-level `ESTALE` on every operation after a foreign commit.**
  It makes a sibling's *reads* fail until it performs a control write.
  In vfs a read after drift is a new pin; `conflict` belongs on the
  write.
- **The global lock across copies.** A consequence of one in-process
  map guarding on-disk copies; vfs's database transaction is the
  right boundary.
- **Rename as delete + create.** vfs has `move` as a verb with its own
  guard; a branch's rename should commit as a `move`, keeping entry
  identity, versions, and edges.
- **The `branch()` syscall, `BR_MEMORY`, `BR_ISOLATE`.** Process
  groups, page tables, and signal barriers are the OS's problem. vfs
  is a storage and namespace layer for agents; the hermetic-runtime
  direction (monty, wasm) is where process isolation would live, and it
  is not this memo's question.
- **FUSE and `@branch` virtual paths as the surface.** vfs's agent
  surface is typed verbs over MCP with a session (spec 023 §6, spec
  054). A branch is bound to the session, not spelled as a path prefix
  on every call. A `/.branches/<name>/` control tree in the `ctl` idiom
  is a reasonable *later* ergonomic for the CLI front door — not the
  primary surface.
- **The README's claims at face value.** Nested `/@parent/@child/`
  paths were removed in February; "O(1) creation" was retracted in
  May; "SIGBUS" is emergent, not implemented. Cite the code, not the
  README, if branchfs is ever referenced in a vfs document.
- **Effect gating as a storage concern.** The paper's own limitation —
  side effects outside the filesystem are not rolled back — is real for
  any agent that runs commands from inside a branch. It belongs to the
  `run` verb's design, if and when a runtime lands, not to the overlay.

---

## 7. Next steps

1. **Record the decision shape as an ADR**: "a branch is a
   session-scoped content overlay — a delta map, a pin map, a parent;
   fork allocates, commit is a guarded batch, abort drops". Cite this
   memo, spec 023, and the Mirage memo §3.21–3.22. Decide there that
   the overlay is in-memory v1 and that reads never fail on drift.
2. **Open a small spec for the caller-supplied precondition** (§5.2):
   a `path → expected version` map (or honoring pinned `Observation`
   rows' `version`) on `write`, `edit`, `delete`, `move`. Router and
   staging only; the guard SQL is unchanged. It serves three consumers
   at once — branch commit, `serve()` stale-write protection (spec
   054), and any ETL that wants compare-and-set.
3. **Fold §5.1 into spec 023**: `VFSSession` owns a mount overlay *and*
   an optional content overlay; `fork()` copies both; resolution order
   tombstone → delta → parent. Note that 023's open question 4
   ("should fork flatten the overlay") is answered for content by pins:
   nothing to flatten.
4. **Add a `drift` verb or session method** (§5.4) once pins exist:
   chunked by `membership_budget`, returning the stale pins with their
   current versions. Pure read; no storage change.
5. **Reconcile spec 024's TTL fallback with ADR 013 pin 5** — eviction
   at verb time, never a timer — since a branch shares the session
   lifecycle 024 rides on.
6. **Positioning note for the README or a later memo**: vfs can say
   "fork is O(1), commit is one guarded transaction, abort is free, and
   two agents that change different files both land" — each claim
   backed by the versions table and the guard, and each one a claim
   branchfs at `a4b6592` cannot make.

---

## Sources

All branchfs paths under `~/Git/Repos/branchfs` @ `a4b6592` unless
noted.

- Model and lifecycle: `src/branch.rs` — `StorageQuota` (16-87),
  `StagedMerge` (100-211), `commit_side_path` (217-221), `Branch`
  (223-345), `validate_branch_name` (347-373), `BranchManager`
  (375-420), `switch_mount_branch` (435-453), `create_branch`
  (466-497), cache invalidation (560-646), `inherited_source_path`
  (648-654), `collect_dir_names_locked` (656-682),
  `resolve_path_locked` (684-708), `snapshot_visible_tree` /
  `snapshot_visible_dir` (710-759), `is_leaf` (776-778), `commit`
  (782-949), `abort` (953-994), `walk_files` (996-1026).
- FUSE layer: `src/fs.rs` — `TTL` (26), caches (32-111), `BranchFs`
  (113-134), `is_stale` (163-167), `switch_to_branch` (170-178),
  `read` (518-651), `write` (653-800), `readdir` (803-936), `unlink`
  (1041-1131), `rename` (1138-1310), `ioctl` (1559-1642), epoch tests
  (1943-1977).
- Control surface: `src/fs_ctl.rs` (root ctl 40-110; branch ctl
  113-162; `finalize_branch_op` 164-207), `src/fs_path.rs`
  (`classify_path` 18-41), `src/platform/linux.rs` (ioctl numbers 7-9),
  `src/error.rs` (4-37).
- Helpers: `src/fs_helpers.rs` (`ensure_cow_for_branch` 46-73,
  `collect_readdir_entries` 156-210), `src/storage.rs` (`copy_entry`
  22-34), `src/daemon.rs` (fresh-state wipe 98-105), `src/main.rs`
  (CLI 19-110).
- Tests: `tests/test_commit.sh:133-150` (sibling preserved, does not
  see the commit), `tests/test_branch_dirs.sh:142-200` (two-branch
  isolation; flat namespace; post-fork parent writes hidden),
  `tests/test_integration.rs:380-436`, `tests/test_ioctl.rs`.
- Docs: `README.md` (features, semantics, "why not overlayfs / btrfs /
  dm-snapshot"), `bench/README.md`, `Cargo.toml`, `LICENSE`.
- Commits diffed or read: `54b0305` (2026-02-01 initial), `32d3b3c`
  (02-07 immediate-parent merge), `a2468e6` (02-09 first-wins),
  `56f25df` (02-10 flat `@branch` namespace), `62dd895` (05-19 eager
  inherited snapshot; README and bench wording change), `2b6c1e2`
  (05-22 staged atomic commit), `84965c5` (05-22 fd-cache staleness
  gate).
- Paper: arXiv 2602.08199v1 (2026-02-09), fetched as HTML — abstract,
  §2.1 (current approaches), §3.2–3.3 (lifecycle and core semantics),
  §4.1–4.4 (file-level CoW, chain resolution, commit/abort, mount-based
  interface), §5.1–5.4 (`branch()` interface, nesting, fork and
  threads), §6 (evaluation, Tables 1–4), related work, limitations and
  future work, conclusion.
- vfs seams read for the mapping: `src/vfs/models/version.py`
  (docstring, `Version.create`, `Version.reconstruct`),
  `src/vfs/models/entry.py` (`Entry` docstring),
  `src/vfs/results/kinds.py` (47, 76, 122-128, 197-201),
  `src/vfs/storage/protocol.py` (165-198),
  `src/vfs/storage/backends/database/writes.py` (1-29, 590-620,
  715-770, 790-845), `staging.py` (1-62, 300-330), `topology.py`
  (883-907), `dialects.py` (74-113, 423-429, 455-459),
  `src/vfs/base.py` (`write` 765-774, `edit` 810-855);
  `context/decisions/013`, `017`, `025`, `027`;
  `context/standards/roadmap.md` (Waves 4–5, "Explicitly not doing");
  `context/specs/archive/023-per-session-namespaces/spec.md`,
  `024-graph-workspace-sessions/spec.md`;
  `context/research/2026-09-04-mirage-design-patterns.md` §3.21–3.22.
