# Forking the files, not only the conversation

## Sources

- **Turso AgentFS**, `/Users/claygendron/Git/Repos/agentfs`, commit `0a014eb`, 2026-06-03, CHANGELOG up to 0.6.4 (2026-03-25). The package manifests and the README badge say MIT. There is **no licence file at the repository root**. `licenses/` holds only the vendored `fuser` and `nfsserve` licences. Read: `SPEC.md` (v0.4), `MANUAL.md`, `README.md`, `CHANGELOG.md`, the Rust SDK (`sdk/rust/src`), and the CLI (`cli/src/cmd`, `cli/src/sandbox`). Issues and pull requests read with `gh`, read-only.
- **Claude Agent SDK and Claude Code** (docs, fetched 2026-11-22): [file checkpointing](https://code.claude.com/docs/en/agent-sdk/file-checkpointing), [sessions](https://code.claude.com/docs/en/agent-sdk/sessions), [checkpointing in Claude Code](https://code.claude.com/docs/en/checkpointing), [worktrees](https://code.claude.com/docs/en/worktrees).
- **Neon**: [About branching](https://neon.com/docs/introduction/branching), and Neon's own [storage FAQ](https://neon.com/faqs/managed-postgres-services-full-database-copy-storage-costs).
- **lakeFS**: [internals and merges](https://docs.lakefs.io/concepts/internals/), and a [community forum thread](https://forum.lakefs.io/t/553414/hi-everyone-use-case-we-need-to-merge-the-main-branch-to-ano) on the dirty-branch error.
- **Tensorlake**: [merging workspaces](https://docs.tensorlake.ai/filesystems/merging).
- **2026 preprints**: [Crab, arXiv 2604.28138](https://arxiv.org/html/2604.28138v1) (HKUST, 30 April 2026); [DeltaBox, arXiv 2605.22781v2](https://arxiv.org/html/2605.22781v2) (SJTU and Huawei, 8 June 2026); [Shepherd, arXiv 2605.10913](https://arxiv.org/html/2605.10913) (Stanford and Northeastern, June 2026); [Zheng et al., arXiv 2608.22928](https://arxiv.org/abs/2608.22928) (24 August 2026, abstract only).
- **vfs**: `src/vfs/models/rows.py` on the checked-out branch, read only for the facts in the last section.

Everything marked "in code" was read at the cited line. Everything from the web is marked as coming from docs or a paper. No AgentFS code was built or run.

## What a session is here

AgentFS has two units, and the word "session" belongs to only one of them. The **agent file system** is one SQLite file, `.agentfs/<id>.db`, which holds the files, a key-value table and a tool-call table. The **run session** belongs to the `agentfs run` sandbox only. It is a directory, `~/.agentfs/run/<session-id>/`, holding a `delta.db` (an agent file system used as the writable layer of an overlay), a mountpoint and a few helper files. A session is therefore "a named writable delta layered over the directory you launched from". Joining a session means attaching another process to the same live mount. Nothing in the SDKs knows what a session is, and the tool-call table has no session column.

## 1. Identity

- **Agent id.** The caller supplies it, or `agentfs init` generates `agent-<unix seconds>` (`cli/src/cmd/init.rs:82-88`). It must be alphanumeric, `-` or `_` (`sdk/rust/src/lib.rs:124-129`), and it maps straight to a file name (`lib.rs:130-151`). The id *is* the path. Its scope is the current working directory, because `.agentfs` is relative (`lib.rs:31-33`).
- **Existing id.** `init` refuses with "already exists, use --force". `--force` deletes every file in `.agentfs/` whose name *starts with* the id (`init.rs:108-125`). Read literally, `init --force my-agent` would also delete `my-agent-2.db`. This was read in code, not run. The SDK's `open` is open-or-create: an id that exists is opened, a new one is created (`lib.rs:291-368`).
- **Session id.** It comes from `--session`, or a fresh UUID v4 (`cli/src/cmd/run_darwin.rs:230`, `cli/src/sandbox/linux.rs:440`). It is joined into a path **without** the agent-id validation (`run_darwin.rs:230-231`, `linux.rs:440-441`). A supplied id that exists means "resume" if nothing has it mounted, and "join" if a healthy mount is found (`run_darwin.rs:46-59`, `linux.rs:158-175`).
- **Ownership.** There is none beyond Unix file permissions. Any process run by the same user that knows or guesses a session id can join it. The README presents this as a feature (`agentfs run --session X bash` to watch a running agent).

## 2. State

- **Schema in code.** `fs_inode`, `fs_dentry` (unique on parent and name), `fs_data` (4 KiB chunks), `fs_symlink`, `fs_config`, `kv_store` and `tool_calls` (`SPEC.md:21-297`, `SPEC.md:622-634`). An overlay adds `fs_whiteout`, `fs_overlay_config` (one row, `base_path`) and `fs_origin` (`sdk/rust/src/filesystem/overlayfs.rs:95-127`).
- **Spec and code have drifted.** The spec's `fs_whiteout` has a `parent_path` column with an index (`SPEC.md:500-506`). The code's table has only `path` and `created_at` (`overlayfs.rs:97-101`). The spec says `tool_calls` is insert-only, written once at completion (`SPEC.md:93-99`). The code inserts a `pending` row at `start` and updates it later, with `completed_at` nullable (`sdk/rust/src/toolcalls.rs:95-105`, `toolcalls.rs:129-236`).
- **In-memory state the database does not hold.** The overlay keeps inode maps, a path map and a whiteout cache in process memory (`overlayfs.rs:44-61`). It loads the whiteouts once, at `init` (`overlayfs.rs:129-155`).
- **Bounds and expiry.** There are none. Session directories are never deleted by the tool. Only the mountpoint directory is removed on exit (`run_darwin.rs:128-135`).

## 3. Lifecycle and concurrency

- **Commands.** Create: `run` with a new id. Resume: `run --session <id>` after exit. Join: the same command while the mount is live. List: `agentfs ps`, which reads one JSON file per process under `~/.agentfs/procs/<session>/` (`cli/src/cmd/ps.rs:25-60`). There is no delete command and no session close beyond process exit.
- **Concurrency means one owner process.** The owner mounts the overlay. Joiners only spawn commands inside the owner's mount (`linux.rs:313-395`). Inside the owner, the whole file system sits behind one mutex (`run_darwin.rs:90`, `linux.rs:243`), and the connection pool has `MAX_CONNECTIONS = 1` (`sdk/rust/src/connection_pool.rs:14`). Writes are serialized by design.
- **A second process opening the database is not supported.** Issue [#329](https://github.com/tursodatabase/agentfs/issues/329) (2026-03-30) reports that the KV store cannot be opened while the database is mounted: the file is locked exclusively. A comment says an experimental multi-process WAL mode in Turso fixes the lock. Even then, the overlay's in-memory whiteout and inode caches would not see another process's writes. That is inferred from `overlayfs.rs:129-155`, not tested.
- **Durability.** `PRAGMA synchronous = OFF` is set by default, with a 5-second busy timeout (`sdk/rust/src/filesystem/agentfs.rs:437-441`). Issue [#332](https://github.com/tursodatabase/agentfs/issues/332) (2026-04-11) reports a corrupt database header after a multi-agent loop.

## 4. Fork

**AgentFS has no fork, no snapshot and no clone in code.** A grep of the CLI and the SDKs for snapshot, fork, branch and clone finds only `libc::fork` for processes. The claims live in prose:

- "Snapshot an agent's state at any point with `cp agent.db snapshot.db`" (`README.md:41`). **A fork is copying the SQLite file.** That copies everything: files, the KV table and the tool-call log.
- "SQLite's write-ahead log enables snapshotting and time-travel forking" (`README.md:191`). No code implements this.
- Snapshot pull requests [#119](https://github.com/tursodatabase/agentfs/pull/119) (2025-12-22, still open) and [#268](https://github.com/tursodatabase/agentfs/pull/268) (2026-01-20, closed unmerged 2026-04-13) were not landed. The maintainer said a checkpoint followed by a file copy "is not safe against concurrent writes", and said a copy through SQL would be slow on large databases. The work waits on a `Connection::snapshot()` API in Turso.
- The open issues are [#57](https://github.com/tursodatabase/agentfs/issues/57) Snapshotting, [#61](https://github.com/tursodatabase/agentfs/issues/61) a `snapshot` command, [#232](https://github.com/tursodatabase/agentfs/issues/232) automatic snapshot on a nested `run` ("a really nice way of branching off coding agents"), and [#313](https://github.com/tursodatabase/agentfs/issues/313) rollback.

**The overlay is the real copy-on-write.** Lookup checks the delta, then the whiteouts, then the base (`SPEC.md:557-562`). A whiteout on a directory hides everything below it, because the check walks the ancestors (`overlayfs.rs:193-204`). Copy-up copies the **whole file**: it reads the entire base file into memory and writes it into the delta (`overlayfs.rs:501-600`, the read at `:580`). It records `fs_origin` so inode numbers stay stable. A rename is a copy-up, a rename inside the delta, then a whiteout at the old path (`overlayfs.rs:1224-1293`). Lineage is thin: the delta records only `base_path`, written with `INSERT OR REPLACE` on every open (`overlayfs.rs:113`). On macOS the base is the current directory of each `run` (`run_darwin.rs:79-88`). The code does not check that a resumed session runs from the directory it started in. That was read in code, not run.

**Diff, and no merge.** `agentfs diff` walks every dentry in the delta and labels each path. A path that also exists in the base is "Modified". A path only in the delta is "Added". A whiteout is "Deleted" (`cli/src/cmd/fs.rs:199-270`, `lib.rs:460-609`). The diff never compares contents, so a `chmod` or a parent directory created during copy-up also shows as modified. It compares against the base as it is *now*, not as it was when the copy was made. A move shows as a delete plus an add. **There is no command that applies or merges the delta back into the base.** Issue [#321](https://github.com/tursodatabase/agentfs/issues/321) (2026-02-28) reports that the `diff` command printed at the end of `run` fails, because `run` keeps sessions in `~/.agentfs/run/` and `diff` looks in `./.agentfs/`.

**Work in flight.** There is nothing to handle, because there is no fork operation.

## 5. Rewind, undo, edit-and-regenerate

None of these exists in AgentFS code. The README's answer is to restore a copied file. Issue #313 asks for a whole-file-system `git checkout -f`. In overlay mode, deleting `delta.db` discards everything back to the base. That is the only rewind, and it is all or nothing.

## 6. Session versus run

A session id names one delta. Each `run --session X` is one process invocation over it, and `ps` tracks those per process id. The agent's tool calls are not tied to either. The spec lists "Session/conversation grouping (add `session_id` field)" only as a possible extension (`SPEC.md:115`). Nothing in the CLI or the MCP server writes `tool_calls`; only tests do (`cli/src/cmd/timeline.rs:178-316`). The host application has to record its own calls.

## 7. Regrets

- Snapshotting was promised in the README and asked for since 2025-12-02 (#57). Two implementations were declined over consistency under concurrent writes (#119, #268).
- The `run` and `diff` paths disagree, so the printed hint fails (#321).
- Overlay deletions were not persisted across mounts. This was fixed in 0.4.x (CHANGELOG line 88, issue [#270](https://github.com/tursodatabase/agentfs/issues/270)). Several more whiteout and copy-up fixes followed (CHANGELOG lines 42-43, 77, 82-86, 137).
- The exclusive lock blocks the host's own KV access during a mount (#329).
- [#327](https://github.com/tursodatabase/agentfs/issues/327) (2026-03-19) asks for an `.agentignore`. Copy-up of build output and caches fills the delta.

## Survey: how others fork file state

**Claude Agent SDK and Claude Code.** The docs say it in one line: "Forking branches the conversation history, not the filesystem. If a forked agent edits files, those changes are real and visible to any session working in the same directory." File checkpointing is a separate system. It backs up a file before the Write, Edit or NotebookEdit tool changes it. Each user prompt that starts a turn is a checkpoint, named by that message's UUID. `rewindFiles(uuid)` restores the files and leaves the conversation as it is. The stated limits: changes made through Bash are not undone unless a tool had already edited that file; subagent edits are not tracked; checkpoints are tied to the session that made them; directory creates, moves and deletes are not undone; remote files are not tracked. Claude Code keeps snapshots for the last 100 checkpoints and deletes them after about 30 days. Its rewind menu offers code only, conversation only, or both, so rewind and fork are deliberately independent. With worktrees, "`--fork-session`: the forked session starts in the directory you launched Claude from, and Claude Code leaves the original session's worktree untouched". A fork does not inherit the parent's file view.

**Neon** ([docs](https://neon.com/docs/introduction/branching)). "A branch is a copy-on-write clone of your data", taken from the current state or from an earlier time inside a history window: 6 hours on Free, 1 day on paid plans, up to 30 days. A child branch is billed for the smaller of its changes and its logical size. Longer history costs more storage. The docs describe reset-to-parent and restore. They describe no data merge back into the parent. A Neon branch is a fork you throw away or promote, not one you merge.

**lakeFS** ([internals](https://docs.lakefs.io/concepts/internals/)). A branch is "a pointer to a commit along with a set of uncommitted changes". Creating one is zero-copy. Reads check the branch's staging area first, then the head commit. A merge is three-way against the nearest common ancestor, and whole objects are compared. A path changed differently on both sides is a conflict. So is a change on one side against a delete on the other. `source-wins` or `dest-wins` resolve conflicts, but only for all of them at once: "it is currently not possible to treat conflicts individually". A [forum thread](https://forum.lakefs.io/t/553414/hi-everyone-use-case-we-need-to-merge-the-main-branch-to-ano) reports that a merge into a branch with uncommitted changes fails as a "dirty branch". Merges work only on committed data.

**Tensorlake** ([merging](https://docs.tensorlake.ai/filesystems/merging)). An agent workspace is promoted onto a branch only if the branch has not moved. Otherwise it is merged per path, with conflict kinds `content`, `delete_modify`, `add_add`, `kind_mismatch`, `mode` and `too_large`. "Merge cost scales with the number of changed paths, not total repository size."

**2026 research.**

- [Crab](https://arxiv.org/html/2604.28138v1) measured that "up to 87% of turns" change neither the file system nor the processes. Turns that needed a file-system checkpoint were 5% for Claude Code on Terminal-Bench, 25% for iFlow, and about 25% on SWE-bench. Restoring the chat plus the files recovered only 28 to 42% of injected crashes on Terminal-Bench, because live processes were lost. It recovered 100% on SWE-bench.
- [DeltaBox](https://arxiv.org/html/2605.22781v2) found 62% of 1,689 search events were pure reads. It checkpoints by freezing the overlay's upper layer, so restore is "an O(1) layer switch". It argues that rolling back files alone leaves the agent's memory stale.
- [Shepherd](https://arxiv.org/html/2605.10913) forks by stacking a copy-on-write layer. It measured about 10 KB of storage a branch and roughly 140 ms a fork, independent of image size. It reports no conflict rates for merges.
- [Zheng et al.](https://arxiv.org/abs/2608.22928) argue that a fork, restore or merge cannot undo authorizations already given or requests already sent. An unsafe edit can repeat an action or conflict with a call still in flight.

**Git worktrees** are how Claude Code, Cursor and Codex give parallel agents their own files today. Claude Code's `--worktree` makes `.claude/worktrees/<name>` on its own branch and blocks edits and git commands aimed at the main checkout. The docs admit that "none of them tracks which files a shell command writes". Ignored files such as `.env` need a `.worktreeinclude`. The worktree shares `.git`, plugins and permission approvals with the main checkout. Cleanup needs locks, a sweep, and prompts about unsaved work. The merge back is the ordinary git merge or pull request, with ordinary conflicts.

## What "fork a session" could mean for vfs files

The vfs facts, from `src/vfs/models/rows.py`:

- `vfs_entries` has a globally unique `path` and a unique `(parent_id, name)` (`rows.py:374`, `:428`).
- A deleted row stays at its path with `deleted_at` set (`rows.py:424-426`).
- `vfs_versions` keeps every version per entry, with the actor, provenance and grant revision (`rows.py:480-508`).
- Chunks, postings and vectors key on the entry.

**(a) Share the files; copy only the session's memory.** The fork copies its stamps, shell state and lineage, and the files stay one namespace.

- *Paid by:* the Claude Agent SDK, which says so in its docs. Undo is offered separately, as checkpoint rewind.
- *Cost:* the cheapest by far, with no storage and no merge. The confusion is real but documented: edits in either branch are visible to both.
- *For vfs:* stamps copied into a fork go stale as soon as the sibling writes. The stamp design then refuses the next write, which is correct, but it surprises a user who expected isolation.
- *Undo:* vfs's version rows already give a rewind that is not limited to edit tools, because every verb writes a version. That includes `cli` (bash) writes, which Claude's checkpointing cannot undo.

**(b) A per-session overlay of uncommitted changes, which can be diffed and merged.**

- *Paid by:* AgentFS (overlay, no merge), lakeFS (staging area plus merge), and Tensorlake (workspace plus promote).
- *Cost in vfs:* the unique `path` and `(parent_id, name)` forbid a second live row at the same path. The overlay would need its own tables or a session key in those constraints, plus a whiteout form for deletes and renames.
- *Cost on every read:* every read verb (`ls`, `glob`, `grep`, `search`) must merge overlay over base. Search must also rank overlay files that the index pass never saw. That is the multiplier the reference deployment warns about, about 150,000 verb calls a day.
- *Cost of merging:* a merge needs a base version per path. vfs has that already, as entry id plus version, which is exactly what a stamp holds. The conflict rules then have to be chosen: lakeFS's whole-object rule, Tensorlake's six kinds, or refusal.
- *Lessons from the others:* AgentFS's diff compares paths, not contents, against the base as it is now, and it has no merge at all. Issue #321 shows how easily the two halves drift. lakeFS's all-or-nothing strategies and the dirty-branch refusal are the known pain points.

**(c) A full branch of the namespace.**

- *Paid by:* Neon (copy-on-write at storage pages, time-limited history, no data merge), and AgentFS's `cp agent.db` (a full copy, declined twice as unsafe under concurrent writes).
- *Cost in vfs:* a branch key on entries, versions, chunks, postings and vectors. At the reference deployment that is 10 million files and about 100 million derived rows. A branch either copies them or adds the key to every unique constraint and index, and every query must then filter on it.
- *Cost of the rebuild:* the daily rebuild, the most expensive path, would run per branch or per branch delta.
- *Grants:* rights and grants would need a rule for each branch.
- *Merge:* is either absent, as in Neon, or it is (b) with a larger surface.

**Across all three.**

- Most turns change no files: 70 to 87% in Crab, and about three reads per write in the reference table. So the storage cost of (b) and (c) is small, and the cost that matters is the complexity added to every read.
- Files are not the only effects. Crab's chat-plus-files restore failed on lost processes. Zheng et al. show that requests already sent cannot be forked. In vfs, that means a pending interrupt and its job, which are stored state, must be either copied or left with the parent.

## Code worth reading first-hand

1. `sdk/rust/src/lib.rs:124-151`: the id is the file path, plus the validation rule.
2. `cli/src/cmd/init.rs:108-125`: refusal on an existing id, and the prefix-match `--force`.
3. `cli/src/cmd/run_darwin.rs:221-262`: a session is a directory, with a UUID or a supplied id.
4. `cli/src/cmd/run_darwin.rs:46-59`: join versus resume, decided by a mount probe.
5. `sdk/rust/src/filesystem/overlayfs.rs:95-127`: overlay tables, and `base_path` overwritten on every open.
6. `sdk/rust/src/filesystem/overlayfs.rs:193-232`: whiteouts and the ancestor walk.
7. `sdk/rust/src/filesystem/overlayfs.rs:501-600`: whole-file copy-up and origin mapping.
8. `sdk/rust/src/filesystem/overlayfs.rs:1224-1293`: rename as copy-up plus whiteout.
9. `cli/src/cmd/fs.rs:199-270`: a diff by paths only, and no merge.
10. `sdk/rust/src/toolcalls.rs:95-105`: the tool-call row, with no session column.
11. `sdk/rust/src/connection_pool.rs:14`, with `run_darwin.rs:90`: one connection and one mutex per mount.
12. `SPEC.md:487-614`: the overlay spec, which drifts from the code.

## Lessons for vfs

1. **Say, in one sentence, what a fork does to files.** The Claude SDK's "branches the conversation history, not the filesystem" prevents the confusion that (a) otherwise causes. AgentFS's README promises a "time-travel forking" that no code delivers, and the result is #57, #232 and #313. *Bears on:* the session design and its fork verb.
2. **Keep rewinding the files separate from forking the session.** Claude Code offers code-only, conversation-only and both. vfs's version rows make a file rewind possible without a fork, and it covers `cli` writes too. *Bears on:* the stamp design (a rewind is a write and must refresh stamps) and the session design.
3. **A fork's copied stamps are a snapshot of another session's view.** Under (a), they are correct to refuse after the sibling writes. The fork should say that its stamps came from the parent, or start empty under strict. *Bears on:* the stamp design (PR 42).
4. **If vfs offers an overlay, the base version per path is the merge base.** lakeFS and Tensorlake need a common ancestor. vfs already stores entry id plus version in each stamp. AgentFS keeps no base version, so its diff compares against the base as it is now and cannot detect a conflict. *Bears on:* the stamp design.
5. **Cost the overlay on the read path, not on storage.** Most turns write nothing (Crab: 70 to 87%; DeltaBox: 62% of events are reads). Every `ls`, `glob`, `grep` and `search` pays the merge of overlay over base. *Bears on:* the session design and the reference-deployment filter.
6. **Do not let a supplied id double as a path or a capability.** AgentFS joins `--session` into a path unvalidated, and anyone who knows the id joins the live mount. *Bears on:* the session id and ownership design.
7. **Decide what happens to an id that already exists, and make that one explicit outcome.** AgentFS's `init` refuses unless `--force` is given, its `open` opens or creates, and its `run --session` resumes or joins. Three verbs give three answers, and `--force` deletes by prefix. *Bears on:* the session design.
8. **A fork must decide what happens to stored jobs.** An interrupted job is a request already sent to a person. Zheng et al. show that a fork, restore or merge cannot undo one. Copying the job duplicates the question; leaving it with the parent is the safe default to argue from. *Bears on:* the interrupt design.
9. **Snapshots under concurrent writers are hard on SQLite.** AgentFS declined two file-copy snapshots for that reason. Postgres has no file to copy at all. Copying the whole database is not a fork vfs can offer on either engine. *Bears on:* the session design.
