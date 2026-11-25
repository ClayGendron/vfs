# LangGraph: the thread, the checkpoint and the fork

## Sources

- Repo: `langchain-ai/langgraph`, local clone `/Users/claygendron/Git/Repos/langgraph`, commit `c6335a4255dc` (2026-11-20). License MIT.
- Packages read: `libs/langgraph` (Pregel), `libs/checkpoint` (saver base), `libs/checkpoint-postgres`, `libs/checkpoint-sqlite`, `libs/checkpoint-conformance`, `libs/sdk-py` (client for the hosted Agent Server).
- The server (`langgraph-api`, the "Agent Server") is closed source. What it does is known only from the SDK's types and docstrings and from the published API reference. Those claims are marked "docs" or "SDK" below.
- Docs read on 2026-11-22: docs.langchain.com `oss/python/langgraph/persistence`, `.../checkpointers`, `.../use-time-travel`, `.../interrupts`; `langsmith/double-texting`, `langsmith/use-threads`, `langsmith/resource-auth`, and the Agent Server API pages `threads/create-thread` and `threads/copy-thread`.
- Issues and PRs came from `gh`, read only.

## What a session is here

A LangGraph "thread" is a string key, `thread_id`, under which a checkpointer stores a tree of checkpoints. The library has no thread object, no create call, no owner and no lock. A thread exists once a checkpoint has been saved under its key. Each checkpoint is a full snapshot of the graph's channels after one superstep. It holds a pointer to its parent and a list of "pending writes" from the tasks of the next step. The thread's current state is simply the checkpoint with the largest time-ordered id. A fork is one more child checkpoint under an older parent. The hosted server adds a real thread record: metadata, status, TTL, `if_exists`, copy, an owner filter, and a per-thread run queue. The thread is the conversation's state, and in LangGraph that includes the messages.

## 1. Identity

**The caller makes the id in the library.** The saver's docstring says to pass `{"configurable": {"thread_id": ...}}` and calls it "the primary key used to store and retrieve checkpoints" (`libs/checkpoint/langgraph/checkpoint/base/__init__.py:205-222`). With a checkpointer and no `configurable`, the run is refused: "Checkpointer requires one or more of the following 'configurable' keys" (`libs/langgraph/langgraph/pregel/main.py:2700-2705`). Any value is accepted and coerced with `str()` (`main.py:1491-1493`, `libs/langgraph/langgraph/pregel/_loop.py:421-425`). The persistence docs only advise "Keep `thread_id` values under 255 characters. Use a UUID or hash" (docs).

**First use and reuse are not told apart.** On entry the loop loads the latest checkpoint for the key. When there is none it substitutes an empty checkpoint: "Normal case: fetch the most recent checkpoint ... Returns None on first invocation" (`_loop.py:1887-1899`). A new id and a reused id take the same path. The checkpointers page warns that "Reusing a thread ID alone does not mean that execution resumes" (docs): whether a call resumes depends on its input (`None` or a `Command`), not on the id (`_loop.py:961-974`).

**The library has no owner.** No table has an owner column (`libs/checkpoint-postgres/langgraph/checkpoint/postgres/base.py:50-79`; `libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py:147-168`). Anyone holding a saver and a `thread_id` string can read, write, fork or delete that thread.

**The server adds a create step and a conflict rule.** `threads.create(thread_id=None, if_exists=None, metadata, ttl, supersteps, graph_id)` (`libs/sdk-py/langgraph_sdk/_async/threads.py:102-176`). With no id, "ID will be a randomly generated UUID." `if_exists` is `raise` or `do_nothing`, and the default is `raise`. `do_nothing` returns the existing thread (`threads.py:120-121`; `libs/sdk-py/langgraph_sdk/schema.py:94-99`). The API reference gives `thread_id` as `format: uuid` and lists a `409 Conflict` (docs). The auth types also type it as `UUID` (`libs/sdk-py/langgraph_sdk/auth/types.py:443-462`). So the server takes caller-chosen ids only in UUID form, while the library takes any string. Runs get a second knob: `if_not_exists="reject"|"create"`, default `reject` (`schema.py:127-132`; `libs/sdk-py/langgraph_sdk/_async/runs.py:265-266`). The newer "v3" thread stream mints a UUIDv4 on the client, and the server creates the row lazily on the first `run.start` (`threads.py:766-800`).

**Ownership on the server is metadata plus a filter, written by the application.** The documented pattern is an `@auth.on.threads.create` handler that stamps `metadata["owner"] = ctx.user.identity`, and read handlers that return the filter `{"owner": ...}` (`auth/types.py:995-1003`, `:80-107`). The resource-auth docs show another user's read failing with `404 Not Found` (docs). Ownership is therefore a convention the application must write. The id itself carries no owner. The code that would show what `if_exists="do_nothing"` returns when the id belongs to someone else is not public. That case was not verified.

## 2. State

The checkpoint holds `v`, `id`, `ts`, `channel_values`, `channel_versions` and `versions_seen` (`base/__init__.py:93-124`). `versions_seen` maps each node to the channel versions it last saw. That is how the engine decides what runs next. The metadata records `source` (`input`, `loop`, `update`, `fork`), `step`, `parents` (one per namespace) and `run_id` (`base/__init__.py:39-63`). `CheckpointTuple` adds `parent_config` and `pending_writes` (`:140-147`).

On Postgres there are three tables, all keyed first by `thread_id` and `checkpoint_ns` (`postgres/base.py:50-79`):

- `checkpoints`: the primary key is `(thread_id, checkpoint_ns, checkpoint_id)`, with a nullable `parent_checkpoint_id`.
- `checkpoint_blobs`: channel values keyed by `(channel, version)`. The insert is `ON CONFLICT DO NOTHING`, so a value that has not changed is stored once (`:134-138`).
- `checkpoint_writes`: keyed `(checkpoint_id, task_id, idx)`. These are the pending writes.

Pending writes are what each task of the next superstep has written so far, attached to the checkpoint the step started from. If a step fails part way, the tasks that finished are not run again (checkpointers docs). Special channels get fixed negative indexes and are upserted: `ERROR -1`, `SCHEDULED -2`, `INTERRUPT -3`, `RESUME -4` (`base/__init__.py:824`; `postgres/base.py:149-162`). An interrupt waiting for an answer is one of these rows.

SQLite has the same shape in two tables. The whole checkpoint is one blob with no value dedup, and the insert is `INSERT OR REPLACE` (`sqlite/__init__.py:147-168`, `:438-450`). Issue #7843 (2026-05-17) reported that missing dedup.

**Bounds.** None by design. Every superstep adds a row, and every changed channel adds a whole new blob. A message list is serialized again in full each time it changes. The checkpointers docs admit this "can produce significant storage growth over time" and offer `DeltaChannel` (beta, added 2026-04-29 in `5c18bde0f`), which stores deltas and rebuilds a value by walking the parent chain (`base/__init__.py:64-87`).

**Expiry.** The library has none. The server has `ttl` in minutes with strategy `delete` or `keep_latest` (`threads.py:125-127`, `:169-173`; create-thread API docs).

## 3. Lifecycle and concurrency

The library operations are `get_tuple`, `list`, `put`, `put_writes` and `delete_thread`. Optional ones are `delete_for_runs`, `copy_thread` and `prune` (`base/__init__.py:344-437`; `libs/checkpoint-conformance/langgraph/checkpoint/conformance/capabilities.py:15-48`). Neither OSS SQL saver implements `copy_thread` or `delete_for_runs`. Postgres gained `prune` on 2026-10-14 (PR #9290). `list` is the only way to enumerate, and it needs a thread id or a filter. The server adds `search`, `count`, `copy`, `prune`, `update`, a thread `status` (`idle | busy | interrupted | error`) and `delete` (`threads.py:267-486`; `schema.py:34-41`).

**What survives a restart.** Whatever has been saved. Durability decides how much:

- `sync`: the loop waits for the checkpoint future before the next step (`main.py:3103-3105`).
- `async` (the default, `main.py:2714-2715`): the put runs in the background while the next step executes.
- `exit`: no writes and no checkpoints until the graph exits (`_loop.py:535`, `:1337-1339`).

The docs say a crash under `exit` loses intermediate state. A crash before the first durable checkpoint "leaves the thread indistinguishable from a thread that was never invoked" (checkpointers docs). Issue #8764 (closed 2026-10-19) asked for an admission record. The maintainers replied that "tracking admission belongs in the caller."

**Two invocations on one thread, in the library: nothing stops them.** `put` is an upsert with no check of the expected parent (`postgres/base.py:140-147`). The "latest" checkpoint is `ORDER BY checkpoint_id DESC LIMIT 1` (`postgres/__init__.py:238-240`). The saver's `threading.Lock` only serializes one saver object's connection use (`postgres/__init__.py:487`), not two processes. Issue #8796 (2026-09-02) reproduced two processes on one `thread_id` with `durability="sync"` on real Postgres. Both ran the same task. The deterministic `task_id` plus `ON CONFLICT DO NOTHING` silently dropped one write. The second worker then wrote a child of the same parent, so the chain forked and the stale branch became the tip. "Both processes exit 0; nothing raises and nothing logs." It was closed with "feature requests go on the langchain forum." Related: #9676 (open): under `exit` durability with parallel approvals, "an approved call is asked again and runs twice, or a pending approval disappears".

**On the server: a per-thread run queue with four policies.** `multitask_strategy` is `reject`, `interrupt`, `rollback` or `enqueue` (`schema.py:85-92`), and it is recorded on every `Run` (`schema.py:368-386`). The double-texting docs say `enqueue` is the default. `interrupt` "preserves the progress made up to the interruption point" and warns that a half-run tool call may need cleaning up. `rollback` "reverts all progress—including the initial run input." Double texting "is not available in the open source LangGraph framework" (docs). `rollback` presumably uses `delete_for_runs` over `metadata.run_id` (`base/__init__.py:355-372`), but the server is closed and this was not confirmed. Issue #7417 (open, 88 comments) reports that on the hosted server, tool calls longer than about 180 s are silently dispatched a second time from the checkpoint while the first is still running.

## 4. Fork

There are three mechanisms, and they copy different things.

**a. `update_state` on an old checkpoint (the documented fork).** `update_state(config, values, as_node)` is one call to `bulk_update_state` (`main.py:2636-2647`). It loads the addressed checkpoint, applies the values through the writers of `as_node`, and `put`s a new checkpoint whose parent is the addressed one (`main.py:1675-1707`, `:2116-2123`). The docs: "It creates a new checkpoint that branches from the specified point. The original execution history remains intact." It "does not roll back a thread" (time-travel docs).

**b. `as_node="__copy__"`: a sibling copy.** It requires an existing checkpoint and saves a copy with `source: "fork"` under the original's *parent*. That makes it a sibling, not a child. It passes no new versions and copies no pending writes (`main.py:1885-1915`). Optional follow-up updates reuse the task ids the original would have had (`:1917-1967`).

**c. Invoking with a `checkpoint_id` (replay).** The run loads that checkpoint (`_loop.py:1864-1871`). The loop then checks whether the thread has moved past it, by comparing against the latest id (`libs/langgraph/langgraph/pregel/_checkpoint.py:174-188`). A docstring there admits that a leaf of an abandoned branch "counts as well; telling it apart would mean listing the thread." When time-travelling, it drops cached `RESUME` writes "so that interrupt() calls re-fire" (`_loop.py:976-1006`). It clears old `INTERRUPT` writes and saves a fork checkpoint "so the replayed execution creates a new branch" (`_loop.py:1135-1158`).

**Lineage** is only `parent_checkpoint_id` plus `metadata.source` and `metadata.parents`. There is no branch name and no head pointer. `get_state_history` returns `list()` over the whole thread in id order (`main.py:1529-1567`), so every branch comes back interleaved. A client has to rebuild the tree from parent pointers.

**Copying a whole thread.** In the library, `copy_thread(source, target)` is an optional, unimplemented interface. Its contract is "copy the **complete** parent chain" (`base/__init__.py:374-396`). Conformance requires that pending writes are copied too (`conformance/spec/test_copy_thread.py:131-152`). On the server, `threads.copy(thread_id)` takes no target id (`threads.py:411-443`). The docs: "an independent thread whose history is identical to the original thread at the time of the operation" (use-threads docs). `threads.create(supersteps=...)` replays state updates into a new thread "for copying a thread between deployments" (`threads.py:122-123`).

**Work in flight.** Under (a) and (b) the pending writes stay on the old checkpoint, including an `INTERRUPT` row. Under (c), interrupts are explicitly cleared and re-fired. The docs: "interrupts are always re-triggered during time travel" (time-travel docs). A whole-thread copy is required to carry pending writes, so a waiting interrupt arrives in the copy still waiting. The conformance test implies that two threads can then each answer the same question. No doc says so.

**Side effects are not forked.** The docs say it plainly: "Nodes after the checkpoint re-execute, including any LLM calls, API requests, or interrupts." "Replay re-executes nodes—it doesn't just read from cache" (time-travel and checkpointers docs). A node is re-run "from the beginning", so "side effects called before" an interrupt must be idempotent (interrupts docs). Issue #9240 (open, 2026-10-08) asks the docs to state that durability modes "do not imply exactly-once external side effects". Whatever a node did outside the checkpoint, such as a file it wrote or an API it called, is shared by every branch and done again on replay.

## 5. Rewind, undo, edit-and-regenerate

- **Rewind** is reading or invoking at an older `checkpoint_id`. Nothing is deleted.
- **Undo** does not exist as an operation. Undo means forking from the checkpoint before the change, which becomes the new latest.
- **Edit-and-regenerate** is (a) followed by `invoke(None, ...)` from the new checkpoint. Plain regenerate is (c).
- **Fork** is the same thing as all three: each makes a sibling branch inside the *same* `thread_id`. Only a whole-thread copy makes a new thread id.

This area keeps regressing. #7592 (open, 2026-04-22): since 1.1.7, a second regenerate from the same parent "silently overwrites branch 2" instead of making a third. #9491 (open): time travel to an interrupt reapplies the old branch's `Command(update=...)`. #8443 and #8551 (closed): `DeltaChannel` forks replayed the abandoned branch's writes. #7361 (closed): a resume addressed at a `checkpoint_id` turned into a replay. Each one comes back to the same gap: a parent pointer alone does not say which branch a write belongs to.

## 6. Session versus run

The ids nest like this:

- `thread_id` (caller or server, the conversation).
- `checkpoint_ns`: the subgraph namespace, `""` at the root.
- `checkpoint_id`: one per superstep, a uuid6 that is unique and increases over time (`base/__init__.py:98-102`). These form a tree through `parent_checkpoint_id`.
- `run_id`: one invocation. In the library it is only a metadata field on each checkpoint the run writes (`base/__init__.py:62`). On the server it is a `Run` record with status and strategy (`schema.py:368-386`).
- `task_id`: deterministic per task, and the key of pending writes.
- Interrupt `id`: one per waiting `interrupt()` (`schema.py:295-303`).

A run spans many checkpoints, and a thread holds many runs. A pending approval is an `INTERRUPT` write on the head checkpoint, and the thread's status shows `interrupted`. In the library, "is this call a resume" is inferred from the input, or from a matching `run_id` "(e.g. stream reconnect)" (`_loop.py:958-973`).

## 7. Regrets

- **Unbounded growth, fixed late.** For about two years the OSS Postgres saver had only `delete_thread`. #8531 ("accumulate an unbounded number of rows", 2026-08-05) led to `prune` in PR #9290 on 2026-10-14 (`postgres/__init__.py:409-475`). `keep_latest` refuses `DeltaChannel` threads, and it warns that "forking or replaying from a checkpoint being deleted is not" safe. `ShallowPostgresSaver`, which kept only the latest checkpoint, is deprecated in favour of `durability="exit"` (`postgres/shallow.py:169-195`). #9078 (in-memory server) found a TTL sweeper that was a stub.
- **No writer ownership.** #8796 is above. The maintainers did not take it as a bug.
- **History is a tree with no head pointer.** It caused the regenerate and fork regressions in §5.
- **A thread can get stuck.** #9712 (open): after one bad update, "`get_state()` and every later invoke on the thread raise the same error". #9078: runs left `running` by a dead process "permanently wedge their thread".
- **A new direction under review.** PR #9725 (open, 2026-11-17) proposes append-only "transcripts" with per-entry sequence numbers. In it, "A seq that already exists is a conflict", and a writer resuming from an older head "knows to fork". This is optimistic concurrency, the guard the checkpoint table never had.

## Code worth reading first-hand

1. `libs/checkpoint-postgres/langgraph/checkpoint/postgres/base.py:50-79`: the three tables. Lineage is one nullable column.
2. `libs/checkpoint-postgres/langgraph/checkpoint/postgres/base.py:140-162`: upsert with no parent check. This is the root of #8796.
3. `libs/checkpoint-postgres/langgraph/checkpoint/postgres/__init__.py:232-240`: "latest" means the largest id.
4. `libs/checkpoint/langgraph/checkpoint/base/__init__.py:344-437`: the delete, copy and prune contracts, with their warnings about lineage.
5. `libs/langgraph/langgraph/pregel/main.py:1885-1915`: `__copy__`, a sibling fork that drops pending writes.
6. `libs/langgraph/langgraph/pregel/main.py:2116-2128`: `update_state` branches by writing under the addressed parent.
7. `libs/langgraph/langgraph/pregel/_loop.py:976-1021`: deciding between time travel, resume and fork.
8. `libs/langgraph/langgraph/pregel/_loop.py:1135-1158`: a fork clears the old interrupt writes.
9. `libs/langgraph/langgraph/pregel/_checkpoint.py:174-188`: "superseded", and the admitted blind spot.
10. `libs/sdk-py/langgraph_sdk/_async/threads.py:102-176`: `create` with a caller id, `if_exists` and TTL.
11. `libs/sdk-py/langgraph_sdk/auth/types.py:995-1003`: the owner stamped as metadata by the application's handler.
12. `libs/sdk-py/langgraph_sdk/schema.py:85-132`: multitask, conflict, durability and if-not-exists vocabularies.

## Lessons for vfs

1. **Make create and open two separate verbs, with a conflict rule.** The library cannot tell a new thread from a reused one (`_loop.py:1887-1899`). The server had to add `if_exists=raise|do_nothing` (default `raise`, `409`) and `if_not_exists=reject|create` (default `reject`). vfs should refuse an unknown id on open, and should refuse an existing id on create unless asked otherwise. *Bears on the session design and on `resume(job_id)`.*

2. **Bind the owner at creation, not in the id, and answer "not found" to everyone else.** LangGraph leaves ownership to an application handler that stamps `metadata.owner`, and it returns 404 to other users. vfs already judges every call against an `Authority`. It should record the creating principal on the session row and treat a session id opened under another principal as absent. That shuts the guess-or-reuse fixation case without depending on how random the id is. *Session design; also `resume`, which is another way to touch a session's state.*

3. **Scope and bound caller-supplied ids.** The library takes any string and coerces it with `str()`. The docs only advise staying under 255 characters. The server insists on UUIDs, and its newest client mints UUIDv4s itself. vfs should declare a length and character budget for caller ids. It should also say whether uniqueness is per owner or global, because the 409-across-owners case is the one LangGraph does not document. *Session design.*

4. **Persist what the session saw, as LangGraph persists `versions_seen`.** LangGraph's nearest analogue to vfs stamps is `versions_seen`, stored inside every checkpoint (`base/__init__.py:116-121`). It survives restarts, and it forks with the checkpoint. That answers the stateless-handler tension: vfs stamps must live in the database beside the session, not only in Python memory. Otherwise strict mode refuses every edit on the next HTTP turn. *Stamp design (PR 42).*

5. **Guard the session row with a version, and refuse rather than fork silently.** #8796 shows that last-writer-wins plus "latest id is head" turns two concurrent turns into a silent branch. vfs should update session state with a compare-and-set on a session version, and report a stale turn as a conflict. PR #9725 shows LangGraph moving toward this, with a sequence conflict and "knows to fork". *Stamp design and session concurrency.*

6. **Choose a per-session policy for a second call while a job is pending.** The four policies (`reject`, `enqueue`, `interrupt`, `rollback`) exist only on the server, and the default is `enqueue`. `rollback` relies on deleting checkpoints by `run_id`. vfs cannot undo committed file writes that way, so its honest options are reject, queue, or run in parallel guarded by etags. Since a job has at most one live interrupt, a second call during it needs a declared answer. *Interrupt design.*

7. **A fork copies the session's memory and shares the files, and the docs should say so.** LangGraph forks state and says plainly that external effects run again ("including any LLM calls, API requests"). Files are vfs's external state. If a fork copies the stamps, the etag guard already does the right thing: a fork that writes a file its parent has since changed is refused as "changed". *Stamp design and fork.*

8. **Do not carry a waiting interrupt into a fork.** LangGraph's in-thread forks drop or re-fire interrupts (`main.py:1885-1915`, `_loop.py:1151-1158`). Yet its whole-thread copy must carry pending writes (`test_copy_thread.py:131-152`), and that can leave one question answerable from two threads. A vfs job should stay bound to the session that started it, and a fork should record only that the parent had a job waiting. *Interrupt design.*

9. **Store lineage as a parent id plus a fork point, and keep a head, not just "the newest row".** LangGraph's missing head pointer and branch identity cause most of its fork regressions (#7592, #9491, #8443, `_checkpoint.py:179-181`). vfs should record a session's parent session and the point it forked at. Listing a conversation's branches should then not mean scanning a whole history. *Session fork design.*

10. **Ship expiry and cascading delete on day one, and commit stamps with the write.** LangGraph went about two years without prune. Its TTL sweeper was once a stub, and its shallow saver was a workaround. vfs sessions need `delete`, a TTL and a bounded footprint. Deleting a session must also take its stamps and its job journal with it. And unlike LangGraph's `async` and `exit` modes, a stamp refresh should commit in the same transaction as the write it guards, so a crash cannot leave a stamp newer or older than the file. *Both designs.*
