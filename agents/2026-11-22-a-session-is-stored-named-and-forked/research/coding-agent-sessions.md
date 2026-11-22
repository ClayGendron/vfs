# Coding-agent sessions: opencode and Codex

## Sources

- opencode, `/Users/claygendron/Git/Repos/opencode`, branch `dev`, commit `e1cffae53b`, 2026-11-22, MIT. The prompt's `packages/opencode/src/` no longer exists: it was removed on 2026-07-20 (`44b6938b2ad`). The live code is the v2 rewrite in `packages/core/src/`, `packages/schema/src/` and `packages/server/src/`. Read: `specs/v2/session.md`, the session, projector, revert, snapshot, permission, file-mutation and tool sources, and the git history of the deleted `packages/opencode/src/file/time.ts`. Issues are on `anomalyco/opencode` (the repo moved from `sst/opencode`).
- OpenAI Codex, `/Users/claygendron/Git/Repos/codex`, commit `104d2564`, 2026-11-22, Apache-2.0. The clone is shallow (history from 2026-10-15), so older changes were read through `gh` on `openai/codex`. Read: `codex-rs/app-server-protocol`, `core/src/thread_manager.rs`, `thread-store/src/local/`, `rollout/src/`, `app-server/README.md`.
- Everything below is verified in code unless it says "issue" or "docs".

## What a session is here

In opencode a session is a durable, event-sourced SQLite row (`session_v2`) with messages, parts and inbox in child tables. It belongs to one project and directory, runs on a process-local executor, and carries a staged revert and a permission ruleset. Its per-file read record (`FileTime`) existed from 2025 to April 2026 and was deleted. In Codex the durable unit is a "thread": an append-only JSONL rollout plus a SQLite row; a separate `SessionId` spans a root thread and its subagents. In both, files are the shared working tree, owned by no session.

## 1. Identity

**opencode.** The id is `ses_` plus 26 characters: 12 hex characters of an inverted millisecond timestamp and counter (so newer ids sort first), then 14 random base62 characters (`packages/schema/src/session-id.ts:5-11`, `packages/schema/src/identifier.ts:16-32`). The caller may supply it: `Session.create` takes an optional `id` (`packages/core/src/session.ts:88-95`), and the HTTP handler passes `ctx.payload.id` through (`packages/server/src/handlers/session.ts:102-118`). The only format rule is the `ses` prefix. If the id already exists, create returns the existing record unchanged, even if the caller asked for another location or parent (`packages/core/src/session.ts:293-295`). A concurrent create that loses the projection race also returns the winner (`:320-334`). The spec states it plainly: "Reusing a Session ID adopts the existing Session" (`specs/v2/session.md:9`). There is no owner on a session. The server has one password for one user (`packages/server/src/auth.ts:11-37`), so nothing stops a second caller from adopting an id. The one lineage check is in the subagent tool: continuing a child session is refused unless the child's `parentID` is the calling session (`packages/core/src/tool/plugin/subagent.ts:151-153`).

**Codex.** The server mints every thread id as a UUIDv7 (`codex-rs/protocol/src/thread_id.rs:27-30`). `thread/start` takes no id from the client (`codex-rs/app-server-protocol/src/protocol/v2/thread.rs:64-176`). The owner is recorded as immutable creator tags (`creator_user_id`, `creator_account_id`), stamped from the signed-in account (`codex-rs/core/src/session/session.rs:1140-1141`). A resume by another account is refused, but only behind a feature flag and only for the TUI and exec clients (`codex-rs/app-server/src/request_processors/thread_resume_account.rs:12-45`).

## 2. State

**opencode.** The session row holds project, workspace, directory, `parent_id`, `fork_session_id`, `fork_boundary`, title, agent, model, cost and tokens, `revert` (JSON), `permission` (a ruleset), a share URL, and the execution-claim column `time_suspended` (`packages/core/src/session/sql.ts:28-84`). Messages, parts, inbox, instruction entries and blob references are child tables with `ON DELETE CASCADE` (`:86-213`). Every change is a durable bus event that a projector applies (`packages/core/src/session/projector.ts:1010`, `:1129-1164`). Storage moved from JSON files to SQLite on 2026-02-13 (`6d95f0d14c`, "sqlite again"). Nothing expires a session. Growth is not bounded: issue #55282 (2026-10-14, open) found 78% of a 687 MB database in one `session.revert` cell.

**Codex.** A rollout file `rollout-<timestamp>-<uuid>.jsonl` under `$CODEX_HOME/sessions` (`codex-rs/rollout/src/lib.rs:88-89`), plus SQLite metadata that points at the current rollout path (`codex-rs/thread-store/src/local/revert_thread.rs:15-18`). Paginated threads store history as a chain of immutable rollout segments with a parent pointer and an ordinal (`codex-rs/thread-store/src/local/rollout_lineage.rs:24-30`). "Approve for session" decisions live only in memory (`codex-rs/core/src/tools/sandboxing.rs:49-70`, `codex-rs/core/src/state/service.rs:72`).

## 3. Lifecycle and concurrency

**opencode.** Create, get, list, rename, archive, remove, fork, move, revert, and a resumable event log `log({after, follow})` that replays durable events after a sequence, then follows live (`packages/core/src/session.ts:126-262`). Execution is process-local, keyed by session id; repeated wakes coalesce (`specs/v2/session.md:55-66`). A turn writes a "claim" before it starts. A crash or a graceful shutdown leaves the claim in place. The next boot resumes each claimed session with the note "The server restarted while you were working", at most 10 times per turn (`packages/core/src/session/execution/restart.ts:31-79`). Recovery is at-least-once and does not promise exactly-once tool effects (`:65-78`). Prompt ids may come from the client, and a retried prompt with the same id is idempotent (`specs/v2/session.md:9`). Delete interrupts the run, cancels its jobs, removes the session, then removes its `parentID` children recursively (`packages/core/src/session.ts:404-418`). A fork is not a child, so deleting the source leaves its forks in place.

The file lock is per path, process-local and session-blind. Its own comment says so: "Mutation locking is process-local and serializes cooperating OpenCode changes; external writes can still race" (`packages/core/src/file-mutation.ts:91-118`).

**Codex.** start, resume, fork, archive, unarchive, delete, revert, list (`codex-rs/app-server-protocol/src/protocol/common.rs:580-820`). The server queues requests per thread id (`serialization: thread_id(...)`, `:586-596`, `:814-818`). Across processes, an exclusive file lock per thread under `thread-writer-locks/` gives one writer; a second writer gets `WouldBlock` and then a `Conflict` error (`codex-rs/rollout/src/writer_lock.rs:1-60`, `codex-rs/thread-store/src/local/mod.rs:402-417`).

## 4. Fork

**opencode.** `fork({sessionID, before?})` copies through the newest message, or up to but not including `before` (`packages/core/src/session.ts:98-101`, `:343-375`). It mints a new id. It records lineage as `fork_session_id` plus a boundary of `before` or `through`, kept apart from `parent_id`, which marks subagent children (`packages/core/src/session/projector.ts:163-168`). Messages and parts are copied in batches under new ids. Unfinished assistant, shell and compaction rows stay on the source: "forks copy only settled history" (`:207-215`). Permissions, metadata, agent and model are copied. Cost and tokens start at zero. `revert` is not copied (`:163-191`). Pending permission requests are not copied: they are in-memory `Deferred`s keyed by the source session (`packages/core/src/permission.ts:157`). The fork does nothing to files. Both sessions keep editing the same working tree.

**Codex.** `thread/fork` takes `lastTurnId` (inclusive) or `beforeTurnId`. "The referenced turn cannot be in progress" (`codex-rs/app-server-protocol/src/protocol/v2/thread.rs:595-605`). A fork of a thread that is mid-turn gets the same `<turn_aborted>` marker a real interrupt writes (`codex-rs/core/src/thread_manager.rs:235-254`). History is either copied into the fork's own rollout, or referenced from the parent's segments (`codex-rs/core/src/session/mod.rs:494-504`). With `attachToSource`, "the source cannot be deleted while attached threads exist" (`thread.rs:660-665`, `codex-rs/thread-store/src/local/delete_thread.rs:39-48`). Attachments are copied under new ids (docs, `codex-rs/app-server/README.md:541`). The fork may set its own `cwd`. Files are not forked.

**Child sessions versus forks.** In opencode they are different mechanisms. A subagent child is created with `parentID` and inherits location, metadata and permissions, but starts with an empty history (`packages/core/src/tool/plugin/subagent.ts:171-183`, `packages/core/src/session.ts:310-314`). A fork copies history and has no parent. In Codex a subagent thread has its own thread id and shares the root's `SessionId` (`codex-rs/core/src/agent/host/types.rs:37-43`).

## 5. Rewind, undo, edit-and-regenerate

**opencode.** At the start of every model step, a snapshot captures the whole project tree as a git tree. The tree goes into a separate object store at `<data>/snapshot/<projectID>/<hash of worktree>`. Untracked files over 2 MiB are skipped (`packages/core/src/snapshot.ts:91-147`, `packages/core/src/session/runner/step.ts:79-81`). At the end of the step, the changed files are listed and stored on the assistant message (`step.ts:296-316`). The store is per project, not per session. Revert has three phases:

- `stage(messageID, files?)` restores, for each later assistant message, the files that message changed, from its start tree. It saves the pre-revert tree, so `clear` can undo the revert, and records `revert` on the session (`packages/core/src/session/revert.ts:22-56`, `:83-112`).
- `clear` restores the saved tree (`:58-74`).
- `commit` deletes messages and inbox rows at or after the boundary (`packages/core/src/session/projector.ts:1135-1164`). It runs on its own when the next prompt arrives (`packages/core/src/session/session.ts:171-172`). That is edit-and-regenerate.

All three are refused with `BusyError` while the session is running (`session.ts:294-318`). The changed-file list comes from a whole-tree diff, so edits by another session or a person during the step can be counted as this step's changes. Issue #54026 (2026-10-08, open) reports a revert that "silently discard[ed] uncommitted changes made by other sessions". The write and edit tools still carry `TODO: Add snapshots / undo` (`packages/core/src/tool/plugin/write.ts:32`).

**Codex.** `thread/revert(beforeTurnId)` "only changes persisted conversation history. It does not revert local file changes" (`codex-rs/app-server-protocol/src/protocol/v2/thread.rs:1356-1364`). It writes a new immutable rollout and moves the SQLite pointer with a compare-and-swap. The thread id stays the same and old rollouts are kept (`codex-rs/thread-store/src/local/revert_thread.rs:15-48`). `thread/rollback` was removed in favour of it (docs, `codex-rs/app-server/README.md:609-618`). File undo used "ghost commits": a `ghost_snapshot` item in the rollout history, one per turn. They were removed on 2026-04-28 (PR #19481). The `undo` feature is now `Stage::Removed` (`codex-rs/features/src/lib.rs:1243-1247`), and old rollout lines are stripped on read (`codex-rs/rollout/src/recorder.rs:1311-1371`). Users still ask for it back (#9203, #44852).

## 6. Session versus run

opencode ids nest as session (`ses_`), then message (a user, assistant, shell or compaction row with a per-session `seq`), then part, then tool call. A tool-call id is unique only within its step, so durable tool events also carry `assistantMessageID` (`specs/v2/session.md:76`). A run (an execution) is not an id. It is a busy period with a claim. A pending permission belongs to a session through `request.sessionID` and lives only in memory. A reject cancels every other pending request of that session (`packages/core/src/permission.ts:345-366`). Process shutdown rejects them all (`:161-173`). "Always" is saved per project, not per session (`:369-375`). A session also stores its own ruleset, which forks and children inherit.

Codex ids nest as session, then thread, then turn, then item. Pending approvals are server-to-client requests indexed by thread id (`codex-rs/app-server/src/outgoing_message.rs:831-860`). They are replayed to a client that reconnects (docs, README.md:17) and aborted when the thread shuts down (`outgoing_message.rs:301`). They do not survive a restart.

## 7. Regrets

**The read-before-edit record (`FileTime`), opencode.** Exactly what it held, from the last version (`git show 76a141090ea^:packages/opencode/src/file/time.ts`):

- **What was recorded.** A stamp `{read: Date, mtime, size}`, taken by `stat` when the read tool returned, or after the agent's own write.
- **Keyed by what.** Session id, then normalised path. No content hash.
- **Where it lived.** In memory, in the per-instance state. A restart lost it.
- **The check.** Edit and write refused a path with no stamp ("You must read file … before overwriting it"). They refused when the mtime or size had changed ("has been modified since it was last read").
- **The lock.** One semaphore per path, shared by all sessions, held around check, write and re-stamp.
- **Fork and revert.** A fork got a new id and so an empty map. Revert did not refresh it.

Timeline:

| Date | Change | Ref |
|---|---|---|
| 2025-06-02 | scoped to the session | `54b99cd88a5` |
| 2025-11 to 12 | two fixes proposed and never merged: refresh stamps on undo (#4923), persist stamps to disk (#5045) | #4923, #5045 |
| 2025-12-20 | tracking issue: false refusals after undo, because restored files get a new mtime, and after restart, because state is in memory; proposed content hashes tied to history | #5840 |
| 2026-01-20 | removed from the patch tool | `9706aaf552c` |
| 2026-01-21 | `OPENCODE_DISABLE_FILETIME_CHECK` added | `c9ea9668055` |
| 2026-02-24 | 50 ms NTFS tolerance | `36197f5ff8d` |
| 2026-04-01 | Windows path-mismatch fix | `880c0a7477f`, #20354 |
| 2026-04-16 | module deleted, PR with no description | `76a141090ea`, #22999 |

Field reports: the agent's own `bash` writes left stamps stale (#14183). A plugin formatter caused false refusals (#11249). Formatters drove "up to 295 consecutive failures in 5-minute windows", because the error did not show the model the new content (#19040). Today the edit tool's only guard is that `oldString` must match exactly once (`packages/core/src/tool/plugin/edit.ts:277-365`).

**Other opencode regrets.** Revert left the session pointing at a deleted boundary, and every later send failed (#63282, open). Undo "frequently corrupts session state" (#51360). The snapshot store grew to 15 GB in 11.5 hours (#55010).

**Codex.** Ghost snapshots ran `git add -A` over a home directory and filled more than 200 GB (#19588). They were then removed (PR #19481). Codex has no read-before-write check; the only guard is that apply-patch context lines must match (`codex-rs/apply-patch/src/file_update.rs:81`, `:156`).

## Code worth reading first-hand

opencode paths are under `packages/core/src/`; Codex paths under `codex-rs/`.

- `session.ts:292-342`: optional caller id, open-or-create, projection race.
- `session/projector.ts:121-312`: what a fork copies and leaves.
- `session/revert.ts:22-112`: three-phase revert over per-step trees.
- `snapshot.ts:91-147`: the per-project shadow git store.
- `permission.ts:157-173`, `:334-395`: in-memory asks, cascading reject, "always" per project.
- `session/execution/restart.ts:31-79`: write-ahead claim, bounded resume.
- `git show 76a141090ea^:packages/opencode/src/file/time.ts`: the whole stamp design.
- `file-mutation.ts:88-118`: process-local per-file lock and its stated limit.
- `core/src/thread_manager.rs:235-254`: fork boundaries, interrupted marker.
- `thread-store/src/local/revert_thread.rs:15-48`: revert as new immutable segment plus pointer swap.
- `rollout/src/writer_lock.rs:1-60`: one writer per thread across processes.
- `app-server/src/request_processors/thread_resume_account.rs:12-45`: creator tags as owner check.

## Lessons for vfs

1. **A stamp held in memory fails exactly where chat applications live.** opencode's stamps were lost on restart, so every edit after a restart was refused as unread (#5840). vfs's strict default would do the same on every stateless turn. Store the stamps with the session row, or fall back to "read in this job". Bears on the stamp design.
2. **Compare the version, not the time.** mtime gave false refusals after undo, on NTFS, and after formatters (#5840, `36197f5ff8d`, #19040). vfs's entry id plus version is already the right key. Keep it, and never derive it from a clock. Stamp design.
3. **Every write path must refresh the session's stamp.** Shell and plugin writes did not, and same-session edits then failed (#14183, #11249). In vfs, `cli`, `move` and a resumed job's write must all refresh the stamp of the session that made the write. Both designs.
4. **A refusal should carry the current version, or the model retries forever.** 295 identical failures came from a refusal that hid the new content (#19040). A vfs refusal should name the current version and invite a re-read. Stamp design.
5. **Decide what fork and revert do to stamps on purpose.** In opencode a fork started with no stamps and revert left them stale. Copying stamps into a fork is safe, since they are versions and the files are shared. After a revert, keep only the stamps the retained history justifies. Stamp design.
6. **Keep fork lineage apart from child lineage, and do not cascade a delete into forks.** opencode has separate `fork_session_id` and `parent_id` fields. Delete cascades to children only. Codex refuses to delete a source that attached forks depend on. Session design.
7. **"Reuse an id, adopt the session" needs an owner check.** opencode adopts any existing id with no owner check. Codex never accepts a client id and still checks creator tags. If vfs accepts a caller id, open-existing must compare the stored authority and refuse a mismatch. Session design.
8. **A fork copies only settled work.** Both skip unfinished turns: opencode filters running rows, and Codex appends `<turn_aborted>`. A vfs fork should not copy a waiting interrupt. The interrupt stays with the source job. Interrupt design.
9. **File undo across shared state hurts more than it helps.** opencode's whole-tree snapshots overwrote other sessions' edits (#54026) and grew without bound (#55010, #55282). Codex removed file undo altogether. vfs files are shared rows. Keep revert to session history unless versions give a per-entry rewind, scoped to entries this session wrote. Both designs.
10. **Durable claims and idempotent ids make restarts safe.** opencode's write-ahead claim, bounded resume count and client-supplied prompt ids fit vfs jobs. A job id the caller chooses, retried, should return the same job. Interrupt design.

## Comparison

| | opencode | Codex |
|---|---|---|
| Id | `ses_` sortable, caller may supply; reuse adopts the session | UUIDv7, server only |
| Owner | none (single-user server) | creator tags, checked behind a flag |
| Store | event-sourced SQLite rows | immutable JSONL segments plus a SQLite pointer |
| Fork | full copy of settled messages; separate `fork_session_id` | copy or referenced segments; `<turn_aborted>` marker |
| Files on fork | shared | shared |
| Rewind | history plus files from per-step shadow-git trees | history only; file undo removed in April 2026 |
| Read-before-edit | existed as `FileTime` (session, path, mtime, size, in memory); deleted in April 2026 | never existed |
| Pending approvals | in memory, rejected on shutdown | in memory, replayed on reconnect |
| Concurrency | process-local executor and per-file lock | per-thread request queue and a cross-process writer lock |

**In one line:** both projects share files across sessions and forks, and opencode built the closest prior art to vfs's stamps and then deleted it, because the stamps lived in memory and compared mtimes, which broke on restart, undo and outside writes.
