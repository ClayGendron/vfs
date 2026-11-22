# Prior art: LangGraph interrupts and checkpoints

**Sources.** `/Users/claygendron/Git/Repos/langgraph`, `origin/main` at `c6335a4255dc` (commit date 2026-11-20), MIT (`LICENSE`, "Copyright (c) 2024 LangChain, Inc."). Package versions in the tree: `langgraph` 1.2.24, `langgraph-checkpoint-sqlite` 3.1.3. The experiments ran against the same versions from PyPI (`langgraph` 1.2.24, `langgraph-checkpoint` 4.3.2, `langgraph-checkpoint-sqlite` 3.1.3), with scripts in `scratchpad/prior-art/langgraph-exp/` (`exp.py`, `crash.py`, `race.py`).

Paths below are relative to the clone. `types.py` means `libs/langgraph/langgraph/types.py`, `_loop.py`, `_algo.py`, `_runner.py`, `_retry.py` and `main.py` are under `libs/langgraph/langgraph/pregel/`, and `base/__init__.py` is `libs/checkpoint/langgraph/checkpoint/base/__init__.py`.

---

## A. Declaration and typed input

- **READ.** A node is any callable passed to `StateGraph.add_node`. A tool is a LangChain `BaseTool`, run by `ToolNode`. In the default `"v1"` shape, `ToolNode` runs every tool call of one message inside a single task, through `executor.map` (`libs/prebuilt/langgraph/prebuilt/tool_node.py:843-846`). With `create_react_agent(version="v2")`, each tool call becomes its own `Send` task (`libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py:844-850`). The functional API declares `@entrypoint` and `@task` (`libs/langgraph/langgraph/func/__init__.py:110,262`).
- **READ.** There are two kinds of interrupt point. The *static* kind is `interrupt_before=` / `interrupt_after=` given to `compile`, checked by `should_interrupt` (`_algo.py:158-189`) in `tick`/`after_tick` (`_loop.py:695-699`, `786-793`). The *dynamic* kind is a call to `interrupt()` inside a node. `NodeInterrupt` still exists but is deprecated in favour of `interrupt()` (`libs/langgraph/langgraph/errors.py:112-121`).
- **READ.** The signature is `interrupt(value, *, response_schema=None) -> Any`, with an overload that returns `ResponseT` when a type is given (`types.py:906-915`). The first call raises `GraphInterrupt((Interrupt(...),))` (`types.py:1048-1059`). On a resume, the call returns the answer. When the schema is a Pydantic model, `TypedDict` or dataclass, the answer is validated with a `TypeAdapter` before it is returned. When validation fails, nothing is saved, so the question can be answered again (`types.py:895-902`, `1011-1012`).
- **READ.** The typed objects are these.
  - `Interrupt(value, id, response_schema)` (`types.py:594-668`). Its `id` is `xxh3_128(task_checkpoint_ns)` for a task's first question, and `xxh3_128(ns|n)` for the question asked after `n` answers (`types.py:583-590`).
  - `Command(graph, update, resume, goto)` (`types.py:841-867`). `resume` is either one value or a map from interrupt id to answer.
  - `PregelTask(id, name, path, error, interrupts, state, result)` (`types.py:675-683`). This is the read-side view inside a `StateSnapshot`.
  - `PregelExecutableTask` (`types.py:705-720`). This is the live task. It carries a `writes: deque`.
  - `PregelScratchpad(step, stop, call_counter, interrupt_counter, get_null_resume, resume: list)` (`libs/langgraph/langgraph/_internal/_scratchpad.py:9-19`). It travels in `RunnableConfig["configurable"]["__pregel_scratchpad"]` (`_internal/_constants.py:71`), and `interrupt()` finds it through the ambient `get_config()` (`types.py:1023`).
- **READ.** The node does not receive the pause as a typed argument. `interrupt()` reaches the per-task scratchpad through a context variable. The answer is stored per task as a plain list, `scratchpad.resume`.

## B. What is persisted at a pause

- **READ.** A `Checkpoint` is a TypedDict with these fields: `v`, `id` (a monotonic uuid6), `ts`, `channel_values`, `channel_versions`, `versions_seen` (node → channel → version), and `updated_channels` (`base/__init__.py:93-124`). `CheckpointMetadata` holds `source` ∈ {input, loop, update, fork}, `step`, `parents` (namespace → checkpoint id), `run_id`, and a delta-channel counter (`base/__init__.py:39-88`). `CheckpointTuple` adds `parent_config` and `pending_writes: list[(task_id, channel, value)]` (`base/__init__.py:140-147`).
- **READ.** A pause does not write a checkpoint. It writes rows into a *writes* table that hangs off the current checkpoint. `_runner.commit` writes `(__interrupt__, [Interrupt])`, plus any `__resume__` list the task holds, keyed by the task id (`_runner.py:594-600`). Four special channels go to fixed negative `idx` slots: `WRITES_IDX_MAP = {__error__: -1, __scheduled__: -2, __interrupt__: -3, __resume__: -4}` (`base/__init__.py:824`). A resume value that arrives from outside is stored under `NULL_TASK_ID` = `00000000-0000-0000-0000-000000000000` (`_internal/_constants.py:102`; `_io.py:74-75`).
- **READ. The SQLite schema** is created in `setup()` (`libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py:144-170`).
  - `checkpoints(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint BLOB, metadata BLOB)`, with PK `(thread_id, checkpoint_ns, checkpoint_id)`.
  - `writes(thread_id, checkpoint_ns, checkpoint_id, task_id, task_path, idx, channel, type, value BLOB)`, with PK `(…, task_id, idx)`.
  - The database is put in WAL mode. The one migration is a guarded `ALTER TABLE … ADD COLUMN task_path`, which catches the "duplicate column" error (`:173-183`).
  - `put` is `INSERT OR REPLACE` of the whole serialized checkpoint (`:439`). `put_writes` uses `INSERT OR REPLACE` when every write is a special channel, and `INSERT OR IGNORE` otherwise (`:475-479`). `idx` is the write's position in the list, or its special slot (`:490`).
- **READ. The Postgres schema** is an append-only list `MIGRATIONS`, where the list index is the version, recorded in `checkpoint_migrations(v)` (`libs/checkpoint-postgres/langgraph/checkpoint/postgres/base.py:43-94`).
  - It has three tables: `checkpoints` (with `checkpoint JSONB`), `checkpoint_blobs(thread_id, ns, channel, version, type, blob)` with PK `(thread_id, ns, channel, version)`, and `checkpoint_writes`, shaped like SQLite's `writes`.
  - `put` keeps primitive channel values inside the JSONB. Every other value goes to `checkpoint_blobs`, and only for channels whose version changed (`libs/checkpoint-postgres/langgraph/checkpoint/postgres/__init__.py:314-338`).
  - Blobs are `ON CONFLICT DO NOTHING`. Checkpoints are upserts. Writes are upserts for special channels and `DO NOTHING` otherwise (`base.py:134-162`).
  - Reads join the blobs back through `jsonb_each_text(checkpoint -> 'channel_versions')` (`base.py:96-121`).
- **READ. The key** is `(thread_id, checkpoint_ns, checkpoint_id)` for a checkpoint, and adds `(task_id, idx)` for a write.
  - A task id is deterministic: a hash of `(checkpoint_id, namespace, step, node name, PULL/PUSH, triggers or Send index)` (`_algo.py:614-625`, `990-1005`; `_xxhash_str` at `_algo.py:1422-1427`).
  - A functional `@task` call id adds the parent path and the call's ordinal (`_algo.py:834-845`).
  - The task's namespace is `node:task_id` (`_algo.py:625`). The interrupt id hashes that namespace, so the interrupt id depends on the checkpoint id.
- **READ. Serialization.** `JsonPlusSerializer` produces a `(type_tag, bytes)` pair. The tag is one of `null`, `bytes`, `bytearray` or `msgpack` (ormsgpack, with extension types that rebuild Pydantic models, dataclasses and similar by import path). `pickle` is used only if `pickle_fallback=True` (`libs/checkpoint/langgraph/checkpoint/serde/jsonplus.py:280-312`). An older `json` tag is still read through a reviver gated by `allowed_json_modules`.
  - **Safety history.** msgpack replaced JSON on 2024-09-16 (`3b05279e3`). The codec switched to ormsgpack on 2025-03-24 (`696a92224`), and `pickle_fallback` was added on 2025-04-30 (`b3ea406e8`).
  - A fix merged from a fork on 2026-02-26 (`50df7d423`) added an allowlist (`SAFE_MSGPACK_TYPES`) and `allowed_msgpack_modules`. Its default is still permissive with a warning. `LANGGRAPH_STRICT_MSGPACK=true` locks it down (`jsonplus.py:104-141`). The variable was documented on 2026-04-15 (`7fa49bd55`).
  - The repo's own threat model says that pickle has "no restrictions" and that a restricted unpickler "was never merged". Its trust assumption is that anyone who can write to the checkpoint DB can get code executed (`.github/THREAT_MODEL.md:262-263`).

## C. Resumption

- **READ. How a resume finds the paused task.** `_first` loads the latest checkpoint (or the one named by `checkpoint_id`) together with its `pending_writes` (`_loop.py:943-1160`).
  - A single resume value becomes the write `(NULL_TASK_ID, __resume__, v)`.
  - A map of ids is *not* written. It is put into config as `__pregel_resume_map` (`_loop.py:1076`, `1092`).
  - Tasks are then prepared again from the same checkpoint, so they get the same deterministic task ids. `_scratchpad` gathers each task's earlier `__resume__` list from the pending writes by task id. When `_interrupt_id(ns, len(list))` is in the resume map, that answer is appended (`_algo.py:1293-1333`).
- **READ. How an answer is matched to an `interrupt()` call.** It goes by call order within the task. `interrupt()` takes `idx = interrupt_counter()`. When `idx < len(resume)`, it returns `resume[idx]` (`types.py:1031-1038`). Otherwise it takes the "null" resume value once (consume-once, `_algo.py:1338-1349`) and appends it (`types.py:1040-1046`). Otherwise it raises.
  - Each answer is written back immediately as the task's whole `__resume__` list (`types.py:1037`, `1045`).
  - Ids only choose *which task* an answer goes to. Within a task, the answer is the next slot.
  - A retry resets the counter, so a retried node reuses its answers (`_retry.py:576-590`, `703`).
- **READ. Multiple interrupts.** One plain value with more than one interrupt pending raises `RuntimeError`, or `UnknownInterruptError(reason="ambiguous")` in strict mode (`_loop.py:1077-1086`). The pending set is computed from the writes by `read_task_statuses` (`libs/langgraph/langgraph/pregel/_task_status.py:99-129`; `_loop.py:935-941`).
- **READ. What reruns.** The interrupted node reruns from its first line ("re-executing all logic", `types.py:928`). The reason is that Python frames cannot be saved. Replay is made deterministic by the stored answer list.
- **READ. What does not rerun.** A finished sibling in the same super-step keeps its output in the writes table. `_reapply_writes_to_succeeded_nodes` copies that output back into `task.writes` (`_loop.py:853-866`). The runner only starts tasks whose `writes` is empty (`main.py:3085`). `@task` calls inside an `@entrypoint` are memoized the same way, by their call-ordinal task id (`_loop.py:621-658`).
- **EXECUTED** (`exp.py`). The graph fans out to three nodes in one super-step: `a` returns, `b` asks two questions in sequence, and `c` asks one.
  - **First run.** It wrote 2 checkpoints and 7 write rows: 4 from `__start__`, 1 output from `a`, and one `__interrupt__` row at idx −3 for each of `b` and `c`.
  - **Resume of b's first question by id.** No new checkpoint was written. One `__resume__` row was added at −4 for `b`. The `__interrupt__` row for `b` was replaced with its second question, which has a new id. `a` did not rerun. **`c` reran even though it was not answered**, and paused again with the same id.
  - **Count of node starts** over 4 invocations: `a`=1, `b`=3, `c`=4. Every paused task reruns up to its `interrupt()` on every resume of the thread.
  - **The super-step closed only when every task was done.** That produced checkpoint 3 (step 1).

## D. Failure and change

- **READ. Durability modes.** `Durability = Literal["sync","async","exit"]` (`types.py:99`), defaulting to `"async"` (`main.py:2714-2715`).
  - Writes are submitted as each task finishes, except in `exit` mode (`_loop.py:535`).
  - In `async`, the checkpoint is saved in the background while the next step runs, with saves chained so they stay in order (`_loop.py:1761-1776`). In `sync`, the loop waits for that save before the next step (`main.py:3103-3104`). In `exit`, a checkpoint is written only at exit, including exit by interrupt (`_loop.py:1336-1339`, `1555-1565`).
- **EXECUTED** (`crash.py`). Node `a` finishes, then the process dies through `os._exit` inside node `b`.
  - With `sync` and with `async`, `a`'s write survived (2 checkpoints, 4 writes). `invoke(None)` reran only `b`, so the node starts were a=1 and b=2.
  - With `exit`, nothing at all was persisted. The resume failed with `EmptyInputError` and the run was lost.
- **READ. Code changing between pause and resume.** No code version is stored anywhere.
  - A node that no longer exists is silently dropped (`_algo.py:601-602`, and `:980-982` for Sends).
  - Writes to a channel that no longer exists are logged and ignored (`_algo.py:313`).
  - Answers are matched by position. A node edited to ask a new question first would get the old first answer (INFERRED from `types.py:1033-1038`).
  - The format has a version: `checkpoint["v"]` picks the task-id hash (`_algo.py:551`). The id fallback for "older versions gave all of a task's interrupts the first id" keeps saved ids working (`_algo.py:1330-1332`).
- **EXECUTED.** That fallback has a cost in non-strict mode. A stale answer that re-sent b's *first* id after b had moved on to its second question was taken as the answer to the second question. The final state was `b:B1,B1-again`. Strict mode (`__pregel_strict_resume`) refused the same call with `UnknownInterruptError(reason="not_pending")` before writing anything (`_loop.py:1047-1074`; `errors.py:150-162`).
- **READ. GC and expiry.** The OSS savers have no TTL. `delete_thread` exists on both savers. `prune(strategy="keep_latest"|"delete")` exists on Postgres only, added 2026-10-14 (`36bf3887f`; `postgres/__init__.py:409-455`). The threat model lists retention as "Unbounded by default", with TTL only as a hosted-server setting (`THREAT_MODEL.md:131`, `168`).
- **READ. Concurrent resumes.** There is no thread lock, lease or compare-and-set. `SqliteSaver` serializes statements with an in-process `threading.Lock` (`sqlite/__init__.py:100`). Ordering between runs is left to the hosted platform's `multitask_strategy` (`reject|interrupt|rollback|enqueue`, `libs/sdk-py/langgraph_sdk/schema.py:85`).
- **EXECUTED** (`race.py`). Two processes resumed one paused node at once, with answers `YES` and `NO`.
  - **Both ran the side effect**: two "email sent" lines.
  - Both wrote a step-1 checkpoint with the same parent, so the thread forked silently. `get_state` showed `YES`, the sibling with the larger id.
- **READ. Who may resume.** The library does not check. Anyone holding the `thread_id` (and the DB) can resume.

## E. Cost

- **READ.** In `sync` and `async` modes, each super-step costs one `put_writes` per finished task (one row per written channel, `executemany`) and one checkpoint row. On SQLite, that checkpoint row holds the *full* serialized `channel_values` (`sqlite/__init__.py:430-449`). On Postgres it holds one JSONB row plus one blob per channel that changed (`postgres/__init__.py:314-338`).
- **EXECUTED.** A pause costs one or two write rows per interrupted task. A resume adds no checkpoint row while any task in the super-step is still paused. In the tiny test graph, the SQLite checkpoint blobs grew 250 → 634 → 1125 bytes across three checkpoints, because each stores the entire state again.
- **INFERRED.** History grows by one checkpoint per super-step per namespace, forever, unless the thread is pruned or deleted. On SQLite, the size of a thread's history is roughly steps × state size.

## F. History and lessons

| Date | Commit | Change |
|---|---|---|
| 2024-01-15 | `f6894fb5d` | First `interrupt` (static), plus `interrupt_after` on 2024-02-10 (`f1523f3e8`) |
| 2024-08-21 | `f8b053a28` | Raising `Interrupt` (`NodeInterrupt`) from inside a node |
| 2024-11-11 | `810ae0ef5` | `interrupt()` added, "like `input()`", answered by `Command(resume=…)` |
| 2025-03-17 | `e24e14125`, `dd16ae4ba` | Concurrency fix in consume-once null resume; subgraphs consume the global resume |
| 2025-04-24/28 | `644a6c3b6`, `78581b80c` | Resume map of interrupt id → value replaces task_id → value |
| 2025-04-08 → 2025-07-20 | `4fb2aeacc`, `0afc4ebda`, `cb7b92400` | `checkpoint_during` added, its default flipped to False, then replaced by `durability`, with the default back at `async` |
| 2025-07-09 | `d1710e2ea` | `Interrupt` reduced to `value` and `id` (`ns`, `when`, `resumable` removed) |
| 2025-09-10 | `a43acc33b` | One plain value refused when several are pending: "the order in which interrupts enter the queue is not deterministic" |
| 2026-10-02 | `e6cf9ea66` | One task-status reader shared by execution, `get_state` and resume checks; answered interrupts had been reported as still pending |
| 2026-10-08/16 | `5965d72ff`, `b0cabd93d` | `ToolNode` swallowed invalid answers. Cancelling siblings on an invalid answer re-sent an approved tool's email twice |
| 2026-10-16 | `e14f4277d` | `Command(update=)` applied twice, because write idx is the list position and the null task's list was re-saved in a different order |
| 2026-11-04 | `dbc60dd11`, `6ea1751a9` | Strict resume mode. Each `interrupt()` in a task gets its own id, because a shared id let a retried answer fill the next question |

**READ.** The arc runs in one direction. The project started with positional, implicit matching: one global answer, consumed by whoever reads it first. It has moved, a step at a time, toward explicit ids per question and refusal of stale or ambiguous answers. Almost every step was a bug fix in which an answer reached the wrong question, or a side effect ran twice.

---

## Highlighted code

1. `types.py:1020-1059`: the whole `interrupt()` algorithm, which is counter, stored list, consume-once global value, then raise.
2. `types.py:583-590`: the interrupt id as a hash of the task namespace and the answer count, with its comment on why call order is not used.
3. `_algo.py:1293-1363`: `_scratchpad`, which shows how saved answers and the resume map reach one task.
4. `_algo.py:614-625`: the deterministic task id, which is the thing that lets a resume find the paused task.
5. `_loop.py:943-1160`: `_first`, covering resume detection, time travel, strict checks and the routing of a `Command` into writes.
6. `_loop.py:483-577`: `put_writes`, with the null-task ordering fix and its comment about slots keyed by list position.
7. `_loop.py:853-866`: `_reapply_writes_to_succeeded_nodes`, which keeps finished siblings from rerunning.
8. `_runner.py:583-623`: `commit`, which writes an interrupt, error or output row per task.
9. `_loop.py:1287-1432` and `1761-1776`: `_put_checkpoint` and the chained background save that the durability modes hang on.
10. `libs/langgraph/langgraph/pregel/_task_status.py:99-129`: one reader of "what is this task's state", added after three readers disagreed.
11. `base/__init__.py:824`: `WRITES_IDX_MAP`, the fixed slots that make interrupt and resume rows upserts.
12. `libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py:144-183` and `458-496`: the schema, the guarded migration, and the REPLACE/IGNORE split.
13. `libs/checkpoint-postgres/langgraph/checkpoint/postgres/base.py:46-162`: the list-index migrations and the blob dedup by channel version.
14. `libs/checkpoint/langgraph/checkpoint/serde/jsonplus.py:104-141, 280-312`: the type-tagged codec, the pickle fallback and the permissive default.
15. `.github/THREAT_MODEL.md:259-263`: the project's own statement that DB write access means code execution.
16. `libs/langgraph/langgraph/errors.py:150-190`: `UnknownInterruptError` with `reason`, `interrupt_ids` and `pending_ids`, raised before any write.
17. `libs/prebuilt/langgraph/prebuilt/tool_node.py:998-1010`: how a pause raised inside a tool body is passed through `ToolNode`.

---

## What this suggests for vfs (INFERRED)

**Take:**
- **Store the pause as rows beside the unit of work.** In LangGraph a pause is one interrupt row plus answer rows, keyed by `(thread, checkpoint, task, slot)`, each an idempotent upsert. In vfs: a stopped-work record plus its answers, keyed by a deterministic work id.
- **Make the work id deterministic** (stopped record, step, call ordinal), so a re-prepared unit finds its answers without frame state.
- **Replay a tool body from the top, and memoize its completed sub-steps.** For arbitrary Python this is the only workable model: the vfs calls the body already made return their stored results instead of running again. `@task` inside `@entrypoint` is the precedent.
- **Give every question its own id, and refuse answers by default.** Ship strict behaviour from the start: refuse an unknown or already-answered id, refuse an empty answer set, and refuse one answer while several questions are pending. Name the reason and the pending ids, and write nothing on refusal.
- **Use one reader for "what is pending".** Execution, status reads and resume checks should all derive state from the same function.
- **Type the answer.** Carry a schema on the question, validate the answer before anything is saved, and let a bad answer be retried.

**Avoid:**
- **Ambient context.** The scratchpad reaches `interrupt()` through a context variable under private config keys. A typed `Call` should carry the pause explicitly.
- **Rerunning unanswered siblings on every resume.** In the experiment, `c` ran four times while waiting. In vfs, a paused unit should not be re-entered until its own answer exists.
- **Matching an answer by its position in a list.** The 2026-10-16 double-update bug came from keying stored writes by list index. Key every stored answer by the question id.
- **A fallback that lets an old id answer a new question.** The compatibility fallback in `_algo.py:1330-1332` is how a stale answer filled the wrong question in the experiment.
- **A durability mode that loses the pause.** `exit` mode loses everything on a crash. vfs's stopped record is committed in the transaction that stops the work, with no weaker mode.
- **Leaving concurrency to the host.** Two resumes of one pause both ran the side effect, and the thread forked. vfs needs a claim on the stopped record: a conditional update from "stopped" to "resuming" with a token, on both SQLite and Postgres, so that exactly one resume proceeds.
- **Leaving authority to the host.** Record who may answer, and check the answering identity at the gate.
- **A codec that revives arbitrary types.** Keep the stopped record JSON-native. A pickle-capable codec makes the database a code-execution channel.
- **Unbounded history with no expiry.** Give stopped records an expiry or a reaping verb from the start.

**The sharpest lesson.** In LangGraph, nearly every interrupt bug of the last two years had one shape: an answer reached a question it was not for, or a side effect ran twice. The causes were order-based matching, shared ids, a compatibility fallback, and two resumes with no claim. So in vfs, each question has its own id, each answer is bound to that id, and resuming takes an exclusive claim on the stopped record. Answers are refused by default when they do not match. In one line: bind every answer to one question id, and let exactly one resume claim the pause.
