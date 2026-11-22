# Temporal Python SDK: prior art for vfs interrupts

**Sources.** `/Users/claygendron/Git/Repos/temporal-sdk-python`, `origin/main` `5c925a41` (2026-11-20), MIT license (`LICENSE`, "Copyright (c) 2022 Temporal Technologies Inc."). The Rust core submodule `temporalio/bridge/sdk-core` is **not checked out** (`git submodule status` prints `-c675c32…`; the directory is empty). No `.proto` sources for history or activations are present; the generated stubs are (`temporalio/api/**/message_pb2.pyi`, `temporalio/bridge/proto/**/*_pb2.pyi`), and their docstrings carry the proto comments. Command-to-event matching and non-determinism detection live in Core, so they are described from those stubs and the Python callers. The AI integrations (`openai_agents`, `langgraph`, `strands`, `google_adk_agents`, `deepagents`) were moved out of the SDK on 2026-10-01 and 2026-10-08 (`6e66be6`, `d42e654`). They were studied at `d42e654^`. One read-only JSON parse of two test fixture histories was run. No server was started.

Labels: READ means read in the source. EXECUTED means run. INFERRED means reasoned from what was read.

---

## A. Declaration and typed input

**Decorators attach frozen definition objects to the function or class.** (READ)
- `@workflow.defn` calls `_Definition._apply_to_class` (`workflow/_definition.py:88-101`). That walks `inspect.getmembers(cls)` and collects the run, signal, query and update definitions into the frozen dataclass `_Definition` (`_definition.py:204-217`, `267-330`). Duplicates and misplaced methods are gathered into an `issues` list and raised together.
- `@workflow.run` refuses non-async functions and local classes. It sets only a marker attribute (`_definition.py:124-147`).
- `@workflow.signal`, `@workflow.query` and `@workflow.update` build `_SignalDefinition`, `_QueryDefinition` and `_UpdateDefinition` (`workflow/_handlers.py:451-575`). The update decorator also attaches a `.validator` sub-decorator (`_handlers.py:375-383`, `397-403`).
- `@activity.defn` refuses keyword-only parameters and records `_Definition(name, fn, is_async, …)` (`activity.py:58-91`, `560-640`).

**Types are captured, not enforced.** (READ) Every `__post_init__` calls `temporalio.common._type_hints_from_func` (`common.py:1380-1443`). It returns `arg_types` and `ret_type`. If any parameter is not positional or lacks an annotation, it returns `None` for all of them. The types are then used only as *decode hints* for the payload converter: `_process_handler_args` and `_convert_payloads` (`worker/_workflow_instance.py:2484`, `2779`), and the activity result decode (`_workflow_instance.py:974-981`). The source says so plainly: `# TODO(cretz): Check count/type of args at runtime?` (`_handlers.py:477`, `571`). A signal whose input fails to decode is logged and **dropped** (`_workflow_instance.py:2815-2829`).

**Validator shape was not checked until 2026-10-24.** (READ) `_UpdateDefinition.set_validator` now raises on an `async def` validator (`_handlers.py:563-570`). Commit `419ee16` (2026-10-24) explains why: the validator "only created a coroutine that was dropped, so the validation never ran and every update was accepted."

**Interceptors are the closest prior art to a typed `Call`.** (READ) Each hook takes one mutable `@dataclass` input:
- `ExecuteActivityInput(fn, args, executor, headers)` (`worker/_interceptor.py:100-107`).
- `ExecuteWorkflowInput(type, run_fn, args, headers)` (`:188-196`).
- `HandleSignalInput(signal, args, headers)` (`:199-205`).
- `HandleQueryInput(id, query, args, headers)` (`:208-215`).
- `HandleUpdateInput(id, update, args, headers)` (`:218-227`). The same object is passed to both the validator hook and the handler hook.
- `StartActivityInput` (`:260-287`). It carries the activity name, the decoded `args`, every timeout, the retry policy, the cancellation type, the headers, the priority, and the `arg_types` and `ret_type` hints.

The `args` field is always `Sequence[Any]`. The *call kind* is the hook method's name, not a field. There is no single discriminated `Call` union.

**Chaining.** (READ) Each interceptor's `__init__` takes `next` and delegates to it (`_interceptor.py:116-135`, `420-455`). The worker builds the chain by folding the configured list in reverse over a root implementation: workflow inbound at `_workflow_instance.py:459-464`, activity at `worker/_activity.py:744-745`. Outbound interceptors are wired by `init(outbound)`: each inbound interceptor may wrap the outbound one before passing it down (`_interceptor.py:429-435`). The root `_WorkflowInboundImpl.handle_update_validator` calls the user validator with `*input.args` (`_workflow_instance.py:3366-3373`).

## B. What is persisted at a pause

**Nothing about the waiting coroutine is persisted.** (READ) `workflow.wait_condition(fn)` appends `(fn, future)` to the in-memory list `self._conditions` (`_workflow_instance.py:2049-2050`, `347`). After each activation the list is re-checked (`:2908-2923`). A condition with no timeout writes nothing to history. A condition with a timeout writes a timer. The docstring warns that changing `timeout=None` to a value is therefore a nondeterministic change (`workflow/_context.py:1038-1041`).

**What history records is events, not state.** (READ) The event types are listed at `api/enums/v1/event_type_pb2.pyi:29-217`. Two fixture histories were parsed read-only: `tests/worker/test_replayer_complete_history.json` and the nondeterministic one (EXECUTED). Each holds 11 events for a workflow with one activity: `WorkflowExecutionStarted`, then `WorkflowTaskScheduled/Started/Completed`, then `ActivityTaskScheduled/Started/Completed`, then a second `WorkflowTaskScheduled/Started/Completed`, then `WorkflowExecutionCompleted`.

A human's answer arrives as one of two things:
- `WorkflowExecutionSignaled` (event 26).
- An update. An update is `UPDATE_ADMITTED` (47), then `UPDATE_ACCEPTED` (41), then `UPDATE_COMPLETED` (43). The accepted event embeds the whole original `Request` (`api/history/v1/message_pb2.pyi:3720-3734`). `UPDATE_REJECTED` (42) is documented as **"never written to history"** (`event_type_pb2.pyi:177-178`).

**The worker sends commands, keyed by a per-kind sequence number.** (READ) Workflow code emits commands into an activation completion (`_add_command`, `_workflow_instance.py:2382-2384`). `ScheduleActivity.seq` is drawn from `_next_seq(type)`, a per-kind counter (`:2774-2777`, `:355`). The activity id defaults to `str(seq)` (`:3595`). Patches are `SetPatchMarker{patch_id, deprecated}` commands (`bridge/proto/workflow_commands/workflow_commands_pb2.pyi:1156-1171`), recorded as `MARKER_RECORDED`.

**The cache holds the live object; the history is the truth.** (READ)
- `max_cached_workflows=1000` by default. When it is nonzero, sticky task queues are used (`worker/_worker.py:118`, `208-209`).
- A task waits on the sticky queue for `sticky_queue_schedule_to_start_timeout` (10 s), then moves to the shared queue (`_worker.py:128`, `249-252`).
- A cached run lives in `_running_workflows[run_id]` (`worker/_workflow.py:200`). On a cache miss without an init job, the worker raises "could have unexpectedly been removed from cache" (`_workflow.py:376-381`). Otherwise Core replays the full history into a fresh instance (`:440-446`).
- Eviction is an activation holding only `remove_from_cache` (`workflow_activation_pb2.pyi:80-84`). Its reasons include `CACHE_FULL`, `NONDETERMINISM`, `LANG_FAIL` and `WORKFLOW_EXECUTION_ENDING` (`:1548-1594`).
- On eviction the instance sets `_deleting` and `_is_replaying` and cancels every task (`_workflow_instance.py:938-946`). It then refuses to finish if any task remains (`:603-614`).

## C. Resumption

**Replay re-runs the code and answers each await from history.** (READ) Core turns history into activations: `ResolveActivity{seq, result}`, `FireTimer`, `SignalWorkflow`, `DoUpdate`, `NotifyHasPatch`, `UpdateRandomSeed` and others (`workflow_activation_pb2.pyi:229-1594`). The Python side pops the pending handle by `seq` and resolves its future (`_workflow_instance.py:949-996`). An unknown seq raises `"Failed finding activity handle for sequence"` (`:953-954`). `is_replaying` comes from the activation (`:510`).

**Non-determinism is detected in Core, not in Python.** (READ, Core absent) Core compares the commands that the re-run code emits with the recorded events. On a mismatch it evicts with `NONDETERMINISM`. The `Replayer` turns that eviction reason into `NondeterminismError` (`worker/_replayer.py:220-243`, `workflow/_exceptions.py:17-23`). By default this fails the *workflow task*, which retries forever until the code is fixed. Listing `NondeterminismError` in `workflow_failure_exception_types` makes it fail the workflow instead (`_workflow.py:844-866`).

**Job order is itself part of determinism.** (READ) Core orders jobs as: init, patches, seeds, signals and updates, others, local activities, queries (`workflow_activation_pb2.pyi:44-75`). The SDK applies them in four groups and runs the loop after each group (`_workflow_instance.py:521-575`). A newer "single batch" mode applies every job first, then runs the loop. It is gated by an internal flag that is recorded in history (`_workflow_logic_flag_enabled`, `:2386-2393`).

**How a human answer is delivered.** (READ)
- A signal is fire-and-forget. If no handler is registered yet, it is buffered (`:1221-1229`).
- An update is request and response. `_apply_do_update` (`:721-863`) works in four steps:
  1. It decodes the args.
  2. It runs the validator inside `_as_read_only`. Any command, sleep or activity there raises `ReadOnlyContextError` (`:777-789`, `:2395-2417`).
  3. It sends `update_response.accepted` (`:792-794`).
  4. It runs the handler and sends `completed`, or sends `rejected` with the failure (`:820-832`).
- The validator is **not re-run on replay**: `DoUpdate.run_validator` "will be set false during replay" (`workflow_activation_pb2.pyi:1366-1369`). The accepted event stands in for the decision.

Commit `22a2f5b` (2026-10-22) shows the cost of "rejections leave nothing". An activation that only rejects updates must not let wait conditions advance, because "Rejected updates leave nothing in history, so a condition they let through … could not unblock on replay" (`_workflow_instance.py:2908-2919`).

**The human-in-the-loop shape that recurs in the agent integrations.** (READ at `d42e654^`)
- *Google ADK* (`eb642b1`, 2026-09-19, `tests/contrib/google_adk_agents/test_adk_hitl.py:63-115`). The workflow keeps `_pending: dict[interrupt_id, HitlRequest]` and `_responses: dict[interrupt_id, Any]`. It exposes `@workflow.query pending_requests` and `@workflow.update respond(interrupt_id, response)`. The loop is: `await wait_condition(lambda: any(i in self._responses for i in self._pending))`, then re-invoke the agent with the responses keyed by id.
- *Strands* (`9000725`, 2026-06-01). A `BeforeToolCallEvent` hook (a policy) calls `event.interrupt("approval", reason=…)`. The agent returns `stop_reason == "interrupt"`. The workflow waits for a signal, then re-invokes with `{"interruptResponse": {"interruptId": i.id, "response": …}}` (`tests/contrib/strands/test_interrupt.py:22-63`).
- *Strands, interrupt raised inside an activity tool.* The activity raises `InterruptException` on its first attempt. After approval the activity is **run again from the top** and succeeds (`test_interrupt_exception.py:24-37`).
- *LangGraph* (`0522490`, 2026-04-28). A `GraphInterrupt` raised in an activity is turned into a *return value*, `ActivityOutput.langgraph_interrupts`. The workflow re-raises it (`contrib/langgraph/_activity.py:45-52`, `95-96`, `169-170`). The README tells users to use `InMemorySaver`, because "Temporal handles durability".
- *Async completion* is the other route out of an activity body. `activity.raise_complete_async()` (`activity.py:462-470`) ends the body. A client later finishes the activity by task token through `AsyncActivityHandle` (`client/_activity.py:840`, `client/_client.py:2583`).

## D. Failure and change

**Determinism is enforced by a sandbox and by workflow-safe replacements.** (READ)
- The sandbox re-imports the workflow's module into a fresh namespace for every run, with "passthrough" modules shared (`README.md:1119-1139`).
- Proxies refuse known nondeterministic members. Examples: `datetime.now/today/utcnow`, every public `random` callable except `Random`, and `uuid.uuid1/4/7` (`worker/workflow_sandbox/_restrictions.py:619-624`, `722-724`, `796`).
- The README states that the sandbox "is not secure" and "is only a helper" (`README.md:1339-1345`).
- The replacements are `workflow.now()`, which is the activation timestamp (`_context.py:797-807`), `workflow.random()`, which is seeded by Core and reseeded by `UpdateRandomSeed` (`_context.py:846-855`, `_workflow_instance.py:362`, `1267-1278`), and `workflow.uuid4()`.
- A deadlock detector fails a task that holds the thread for more than 2 s (`_workflow.py:212`).
- `asyncio.wait` and `as_completed` have deterministic `workflow.*` replacements, because the stdlib versions use `set()` (`README.md:870-890`).

**Versioning.** (READ)
- `workflow.patched(id)` returns True when the code is not replaying, or when replay has seen the marker. The result is memoized per id. When True, it emits a `SetPatchMarker` command (`_workflow_instance.py:1534-1570`).
- `deprecate_patch(id)` emits the marker with `deprecated=True`, so old histories that lack the marker still replay (`_context.py:585-601`).
- A `patch_activation_callback` (`663ea64`, 2026-07-16) lets the host decide whether a *new* patch takes effect (`_worker.py:323-328`).
- Worker Versioning (`d7238cd`, 2023-07-10) gave way to Worker Deployment Versioning (`fd49c4e`, 2025-04-16). Each workflow declares `VersioningBehavior.PINNED` or `AUTO_UPGRADE` (`common.py:1228-1242`, `_definition.py:63`).
- Internal *workflow logic flags* version the SDK's own semantics. A flag is written to the completion the first time it is used. On replay a flag is honoured only if the history carries it (`_workflow_instance.py:2386-2393`).

**The `Replayer`** (`5b202c0`, 2022-08-19) runs histories through a worker with no server. The NDE eviction becomes `replay_failure` (`_replayer.py:220-243`, `443-458`; `README.md:1936-1966`). The documented use is a CI check: replay every past history against new code (`README.md:1955-1964`).

**Validators reject before anything is recorded.** (READ) Rejection writes no event (`event_type_pb2.pyi:177-178`). Validators run read-only (`_workflow_instance.py:777-789`). Arguments are re-decoded after validation, in case the validator mutated them (`:780-789`).

## E. Cost

(READ, with INFERRED arithmetic)
- One activity costs three activity events. Each wake-up of the workflow costs three workflow-task events. A minimal one-activity run is therefore 11 events (EXECUTED fixture parse).
- A signal adds one event plus a workflow task. An accepted update adds 2 or 3 events plus a workflow task.
- Each activation carries `history_length`, `history_size_bytes` and `continue_as_new_suggested` (`_workflow_instance.py:503-505`; `24fea4c`, 2023-08-02). The suggestion reasons are `HISTORY_SIZE_TOO_LARGE`, `TOO_MANY_HISTORY_EVENTS` and `TOO_MANY_UPDATES` (`api/enums/v1/workflow_pb2.pyi:578-592`).
- The numeric limits are server configuration and appear nowhere in this repository.
- Continue-as-new (`workflow/_workflow_ops.py:846`) closes the run and starts a fresh run with a new empty history and carried-forward arguments. It bounds replay cost.
- Payloads too large for history go to external storage, such as S3 (`README.md:464-470`).
- Replay cost grows with history length on every cache miss. That is why sticky caching exists (INFERRED).

## F. History and lessons

(READ; commit dates from `git log`)
- `962a5e8` 2022-06-03: patch support with random and UUID helpers. `3901df8` 2022-11-08: memoize `patched`.
- `0126e6e` 2022-10-28: the workflow sandbox, followed by 100+ later sandbox fixes. Recent examples are `d488ff5` 2026-11-02 (restrict `time.clock_gettime`) and `5c925a4` 2026-11-20 (datetime decoding behind a replay flag).
- `2c15ed3` 2023-10-25: Workflow Update. It added a synchronous answer with a validator, where signals have no reply. Later: `11a97d1` 2024-05-20 (wait-for-stage), `540faeb` 2024-12-19 (update-with-start), `fe46e1a` 2025-01-21 (no longer experimental), `effc857` 2025-01-18 (runtime validator signature check), `419ee16` 2026-10-24 (reject async validators), `22a2f5b` 2026-10-22 (rejected updates must not advance conditions), `b0a52fb` 2026-08-25 (continue-as-new from an update handler fails the task).
- `1845f25` 2026-11-03 turned single-batch activation on by default. `bc45117` 2026-11-13 turned it off again, 10 days later, "to preserve legacy signal, condition-wait, and cancellation behavior for unflagged workflows" (`CHANGELOG.md` 1.36.1). The change in evaluation order changed what resumed runs did.
- `f1579fc` 2026-08-19 and `3968f3d` 2026-08-17 ("keep … credentials out of workflow history"): a manifest serialized into durable, replayed, UI-visible history recorded a credential "repeatedly for the life of the session". The fix added `SecretRef`, a lookup key resolved at the point of use.
- `6e66be6` 2026-10-01 and `d42e654` 2026-10-08: the AI integrations were moved into separately versioned packages.

---

## Highlighted code

1. `temporalio/worker/_interceptor.py:186-287`: the typed hook inputs. This is the shape a typed `Call` would take, with the kind carried by the method name.
2. `temporalio/worker/_interceptor.py:413-455`: `next`-chaining, and the separate sync `handle_update_validator` hook beside the async handler.
3. `temporalio/worker/_workflow_instance.py:455-466`: how the chain is folded over the root implementation.
4. `temporalio/worker/_workflow_instance.py:721-863`: the update lifecycle: decode, validate read-only, accept, run, complete or reject.
5. `temporalio/workflow/_handlers.py:537-575`: `_UpdateDefinition`, including the async-validator refusal and its reason.
6. `temporalio/common.py:1380-1443`: type capture as decode hints, all or nothing.
7. `temporalio/bridge/proto/workflow_activation/workflow_activation_pb2.pyi:40-85`: job ordering and why ordering is determinism.
8. `…/workflow_activation_pb2.pyi:1320-1369`: `DoUpdate`; the validator is not re-run on replay.
9. `temporalio/api/enums/v1/event_type_pb2.pyi:170-179`: the update events; a rejection is never written.
10. `temporalio/worker/_workflow_instance.py:949-996` with `2774-2777`: resolution by per-kind sequence number.
11. `temporalio/worker/_workflow_instance.py:2876-2924`: the condition loop and the rejected-update replay hazard.
12. `temporalio/worker/_workflow_instance.py:1534-1570`: `patched` and memoization; the marker as a recorded version decision.
13. `temporalio/worker/_workflow_instance.py:2386-2393`: logic flags; an SDK semantic change recorded per history.
14. `temporalio/worker/_replayer.py:220-243`: eviction reason mapped to `NondeterminismError`.
15. `temporalio/worker/_workflow.py:591-690`: safe eviction and the cost of tearing down live coroutines.
16. `temporalio/worker/workflow_sandbox/_restrictions.py:555-800`: the default list of nondeterministic calls.
17. `git show d42e654^:tests/contrib/google_adk_agents/test_adk_hitl.py` lines 63-127: pending requests and responses keyed by interrupt id, a query to list them, an update to answer.
18. `git show d42e654^:tests/contrib/strands/test_interrupt_exception.py` lines 17-37: an interrupt from inside a tool body resolved by re-running the body.

---

## What this suggests for vfs (INFERRED)

**Take.**
- *A typed, mutable input dataclass per hook.* Temporal's inputs carry decoded args, headers and options, and are chained by `next`. A vfs `Call` can go further than Temporal does. It can be one discriminated type with the kind as a field, so that one policy function sees every kind. Temporal's split into per-method hooks forces each interceptor to override many methods.
- *A separate, read-only, synchronous decision step that records nothing when it refuses.* The update validator is exactly a policy's allow/deny. Running it read-only, refusing commands inside it, and re-decoding the args afterwards are all cheap protections.
- *Answers keyed by a stable id.* The ADK and Strands integrations converge on the same three pieces: a pending map keyed by interrupt id, a "list pending" read, and an "answer by id" write. Resuming re-invokes the unit with the answers attached. This is the shape of a vfs interrupt row: a stop record with an id, and an answer row keyed to it.
- *Per-kind sequence numbers* to match a re-driven step to its recorded answer, plus a loud mismatch error rather than a silent divergence. The vfs shell is a deterministic request/reply machine. It can be resumed the way Temporal resumes a workflow: store the line and the ordered list of answered replies, re-drive the machine, answer each request from the log by sequence, and raise a vfs non-determinism error when the request at sequence *n* differs from the recorded one.
- *Record the decision, not the inputs to re-decide it.* Validators are not re-run on replay. vfs must choose deliberately whether a resumed call re-runs policy, since rights can change overnight. Temporal shows the cost of the other choice: re-evaluating a recorded decision under new code breaks replay.
- *A version marker in the persisted record* (`patched`, logic flags), and a replay test harness that runs stored pause records from earlier versions against new code.
- *Keep secrets out of the stored record* by storing references, not values (`SecretRef`).

**Avoid.**
- Replay of arbitrary user Python. It needs a sandbox, deterministic time, random and UUID replacements, a deadlock detector, and four years of sandbox fixes, and it is still "not secure". vfs tool bodies should not be replayed. Temporal does not replay activity bodies either. An interrupt raised from inside a tool body should end the body. It is resolved by re-running the body from the top with the answer available by interrupt id, as in the Strands activity test, or by completing it externally, like `raise_complete_async`. Either way, the tool contract must say that the body re-runs, so work before the question must be idempotent.
- Accepting a policy shape that silently does nothing. An `async def` validator accepted every update for years. A vfs `@policy` registration should check its callable's shape (sync or async, signature) when it is registered.
- Changing evaluation order without recording it. Single-batch activation was turned on and back off within 10 days. Any change to how vfs evaluates a paused unit on resume must be keyed to a version in the stored record.
- Letting a refusal influence anything that is resumed later. A refusal that writes nothing must not change any state that a resume will depend on (`22a2f5b`).

**The one sharpest lesson.** Temporal never stores a paused state. It stores an ordered log of *outcomes*, keyed by sequence number, and rebuilds the state by re-driving deterministic code against that log. Two things make this safe: a mismatch check that refuses to continue, and a version marker for every change in semantics. vfs's shell already meets the determinism precondition, so it can take this design whole. Tool bodies do not meet it, so they should get Temporal's activity contract instead: at-least-once, re-run from the top, answer looked up by id. That contract should never be stretched into a frame snapshot.

**In one line:** Temporal pauses by storing the answers, not the state, and gets the state back by replaying deterministic code against them; vfs's shell can do the same, and its tool bodies should be re-run from the top instead.
