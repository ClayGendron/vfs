# DBOS Transact (Python): durable steps, recv/send and suspend, as prior art for vfs interrupts

**Sources.** `/Users/claygendron/Git/Repos/dbos-transact-py`, `origin/main` at `28192bd` (2026-11-20, "Suspend Workflow GetResult (#970)"), MIT license (`LICENSE`, "Copyright (c) 2024 DBOS, Inc."). The suspend implementation is in the proprietary `dbos-enterprise` package and is not in the clone; only its contract (`dbos/_enterprise.py`) and the core-side schema and wake path are visible. Experiments ran the PyPI release `dbos==3.6.0` (not the clone's HEAD) on a SQLite system database, in `scratchpad/prior-art/dbos-exp/exp.py`.

Labels: READ (read in source), EXECUTED (seen in an experiment), INFERRED (a conclusion drawn from the two).

## A. Declaration and typed input

- READ. `@DBOS.workflow(name=None, max_recovery_attempts, serialization_type, validate_args, auto_upgrade)` (`dbos/_dbos.py:1587`) calls `decorate_workflow` (`dbos/_core.py:2261`). The registry key is `name` or else `func.__qualname__` (`_core.py:2292`), stamped on the function as `dbos_function_name` (`_registrations.py:21`) and stored in `DBOSRegistry.workflow_info_map: dict[str, Callable]` (`_dbos.py:295`). The key is the bare qualified name, with no module, so `a.process` and `b.process` collide.
- READ. A duplicate name raises only when both the module and the real source path differ (`_dbos.py:320-349`). Otherwise it logs a warning and **the later registration silently replaces the earlier one** (`_dbos.py:350-355`). Classes are keyed by `__qualname__` or an explicit name (`_registrations.py:174`), and a second, different class under one name raises (`_dbos.py:357-363`). Instances are keyed `class/config_name` (`_dbos.py:387-401`).
- READ. `@DBOS.step(name, retries_allowed, interval_seconds, max_attempts, backoff_rate, should_retry, preemptible, timeout_seconds)` (`_dbos.py:1607`) calls `decorate_step` (`_core.py:2734`), with the step name taken as `name or __qualname__` (`_core.py:2766`). Each step is also registered as a workflow named `"<temp>." + step_name` (`_core.py:2815-2817`), so it can be started on its own. Steps are not looked up by name on replay; the name exists only to be compared against the recorded row.
- READ. `@DBOS.transaction` no longer exists at HEAD. It was removed with the application database ("Remove Deprecated App DB", `b983385`, 2026-09-09). Transactions are now `datasource.transaction` (`_datasource.py:591`). Each one checkpoints into a `datasource_outputs(workflow_id, step_id, output, error, serialization, created_at)` table in the application's own database (`_schemas/datasource_database.py:14-30`), inside the same transaction as the user's writes, with `ON CONFLICT DO NOTHING ... RETURNING` to detect a concurrent winner (`_datasource.py:397-430`). The isolation default is `SERIALIZABLE` (`_datasource.py:99-103`).
- READ. A decorated function receives only its own arguments. There is no context parameter. Ambient state lives in a contextvar `DBOSContext` (`_context.py:182-228`) and is read through class properties: `DBOS.workflow_id`, `DBOS.step_id` (which returns `ctx.function_id`), and `DBOS.step_status` (`_dbos.py:4554-4585`). Inputs are typed only by optional pydantic validation (`validate_args`, `_core.py:2275-2283`).

## B. What is persisted

- READ. Schema model: `dbos/_schemas/system_database.py`. The DDL is hand-written SQL per engine in `dbos/_migration.py`: Postgres migrations from `:318`, and SQLite migrations from `:1727` (`sqlite_migration_one`) on to `:2176`. They are versioned in a `dbos_migrations(version)` table (`_migration.py:228`).
  - `workflow_status` (`system_database.py:29-95`). PK `workflow_uuid`. About 45 columns: status, name, class/config name, executor_id, application_version, recovery_attempts, queue fields, deadline, `owner_xid`/`creator_xid` (fencing tokens, `:70-73`), `parent_workflow_id`, `forked_from`, `serialization`, `delay_until_epoch_ms`, and, for suspend, `suspend_key` and `result_waiter_ids` (an ARRAY on Postgres and JSON on SQLite, `:85-92`). It carries many partial indexes keyed on status: `idx_workflow_status_pending` (`_migration.py:770`), `idx_workflow_status_suspended` on `delay_until_epoch_ms WHERE status='SUSPENDED'` (`:1416`; SQLite `:2174`), and others.
  - `workflow_input` and `workflow_output` (`:97-112`, migration 109 at `_migration.py:1182`). Inputs and outputs were split off the status row so that they have their own retention.
  - `operation_outputs` (`:114-132`). PK `(workflow_uuid, function_id)`. Columns: `function_name`, `output`, `error`, `child_workflow_id`, start and completion times, `serialization`, `retention_timestamp`. **Step inputs are not stored.** Its foreign key to `workflow_status` was dropped in migration 112 (`_migration.py:1218-1225`).
  - `notifications` (`:134-163`). PK `message_uuid`, which is a caller idempotency key suffixed `::destination` (`_sys_db.py:4419-4428`). Index `(destination_uuid, topic)`. Consumed messages are **kept**, with `consumed=true` and `consumed_by_function_id` set (migration 12 at `_migration.py:527`), not deleted.
  - `workflow_events` (PK `(workflow_uuid, key)`), `workflow_events_history` (PK `(workflow_uuid, key, function_id)`), `streams`, `external_objects`, `workflow_schedules`, `application_versions`, `queues` (`:165-297`).
- READ. Serialization is pluggable through the `Serializer` ABC (`_serialization.py:85-97`). The default is **pickle in base64**, named `py_pickle` (`:99-115`). An opt-in `portable_json` format exists (`:175-191`). Every row carries its format in a `serialization` column. `deserialize_value` unpickles any row tagged `py_pickle` **even when a custom serializer is configured** (`:238-251`); exceptions are handled the same way (`:460-479`).
- INFERRED. Write access to the system database is therefore code execution in every worker.
- EXECUTED. Step outputs and workflow inputs were stored as `py_pickle`. The durable sleep's wake time was stored as `portable_json`.
- READ. Engine differences:
  - SQLite connections use `isolation_level="IMMEDIATE"`, `busy_timeout=30000` and `foreign_keys=ON` (`_sys_db_sqlite.py:42-50`). WAL mode is not set anywhere.
  - Postgres uses `SELECT ... FOR NO KEY UPDATE` for the ownership check. SQLite instead uses a no-op `UPDATE ... SET owner_xid=owner_xid RETURNING`, so that pysqlite opens the write lock (`_sys_db.py:3810-3836`).
  - Postgres wakes waiters with `LISTEN`/`NOTIFY` triggers (`_migration.py:404-438`, `_sys_db_postgres.py:448-464`). SQLite polls once a second, issuing one query per registered waiter per tick (`_sys_db.py:4801-4834`).
  - Only Postgres has the SQL `enqueue_workflow` function (`_migration.py:1049+`).

## C. Resumption and matching

- READ. The step counter is `DBOSContext.function_id`. It is reset to 0 at workflow start (`_context.py:324`) and incremented once per step, recv, send, sleep or child start (`snapshot_step_ctx`, `_context.py:244-256`, and `:281`). `recv` and `get_event` reserve a second id for their timeout sleep (`reserve_sleep_id`, `_context.py:254`; `_dbos.py:2296-2303`). A child's default id is `parent_id-function_id` (`_context.py:167-179`).
- READ. Matching is **by position and name only**. `_check_operation_execution_txn` (`_sys_db.py:4087-4163`) selects the row at `(workflow_uuid, function_id)`. If none exists, the step runs. If one exists and `function_name` differs, it raises `DBOSUnexpectedStepError` (`:4145-4151`; class at `_error.py:284`). Otherwise it returns the recorded output or re-raises the recorded error (`_core.py:2571-2603`). Arguments are never compared.
- READ. The same check reads `workflow_status.status` and raises `DBOSWorkflowCancelledError` if the workflow is cancelled (`:4127-4131`), so cancellation is observed at the next step boundary.
- READ. A step is wrapped as `stepOutcome.then(record_step_result).intercept(check_existing_result)` (`_core.py:2633-2637`). The row is written only **after** the body returns or raises (`_core.py:2538-2569`). A crash mid-step therefore re-runs the step (at-least-once). A duplicate insert at the same position with a different completion time raises `DBOSStepNondeterminismError` (`_sys_db.py:3857-3916`).
- EXECUTED. The code was changed so that position 2 calls `step_b_renamed`, under the same `application_version`. Recovery raised `DBOSUnexpectedStepError: ... step 2, function step_b was recorded when step_b_renamed was expected`. The workflow ended in the **terminal status `ERROR`**, and the message sent to it stayed unconsumed.
- READ. `recv` without suspend (`_sys_db.py:4677-4702`) works in three phases:
  1. `recv_setup` (`:4476-4527`) checks for a recorded result, registers an in-memory event, polls once, and records a durable sleep at the reserved id. That sleep is an absolute wall-clock end time (`record_sleep`, `:4906-4955`).
  2. The thread then **blocks** on the event, rechecking the database every 60 s with a listener running or every polling interval without one (`:4649-4661`).
  3. `recv_consume` (`:4529-4617`) marks the oldest unconsumed message consumed and records `DBOS.recv` in **one transaction**.
- EXECUTED. A process crashed with `wf-1` blocked in recv. A fresh process started and logged "Recovering 1 workflows from application version v1". It re-enqueued the workflow to `_dbos_internal_queue` with `recovery_attempts` 1→2 and a new `owner_xid`, replayed `step_a` and `step_b` from their rows (`steps.log` shows each ran once, in the first pid), and blocked a thread in recv again. A `DBOS.send` from that process completed it. The rows show ids 1, 2 and 4 written before the crash (id 4 is the `DBOS.sleep` timeout, written *before* recv's id 3), and id 3 `DBOS.recv` written last.
- READ. Suspend mode (`suspend=True`, Enterprise only; `_dbos.py:2281-2320`, `_enterprise.py:85-116`) is the shape vfs needs:
  - A waiting recv parks the row as `SUSPENDED` with `suspend_key=topic` and `delay_until_epoch_ms=timeout`.
  - It then raises `DBOSWorkflowSuspendedError`, a **BaseException** (`_error.py:518-545`), which unwinds the whole Python stack. The executor frees its slot (`_core.py:994-997`), and tracing leaves the span status unset (`_context.py:425-427`).
  - Every send, from any process and whether or not that process uses suspend mode, runs `_wake_receivers` in the send's own transaction (`_sys_db.py:4310-4337`). It is a primary-key probe that sets `delay_until_epoch_ms=0` on a matching `SUSPENDED` row; the status test sits in `SET`, not `WHERE`, to keep the planner off the partial index.
  - A background pass re-enqueues due rows. The **workflow re-runs from the top** and replays every recorded step until the recv, which now finds the message.
  - Spurious wakes are accepted: "the replayed recv finds no message and parks again" (`:4318-4320`). `get_result(suspend=True)` does the same through `result_waiter_ids`, woken by the completing `UPDATE` (`28192bd`; `_sys_db.py:1862-1905`).

## D. Failure and change

- READ. Recovery at launch, when no Conductor is configured, selects `PENDING` rows with `executor_id = this executor` (default `"local"`, or `DBOS__VMID`) **and `application_version = this version`** (`_dbos.py:1006-1020`, `_sys_db.py:3713-3749`). Each row goes through `reenqueue_for_recovery` (`_sys_db.py:6101-6136`): `PENDING→ENQUEUED`, `owner_xid=NULL`, only `WHERE executor_id IN (dead executors)`. This makes recovery idempotent ("Idempotent Recovery", `bf4b818`, 2026-07-21; `_recovery.py:14-28`). The queue dequeue then admits exactly one runner. It uses `FOR UPDATE SKIP LOCKED` or `NOWAIT` on Postgres, and a re-check `UPDATE ... WHERE status='ENQUEUED'` that sets a fresh `owner_xid` (`_sys_db.py:5733-5800`).
- READ. Fencing: every checkpoint write first checks that `owner_xid` still matches the execution's token, holding the row lock until commit (`_sys_db.py:3810-3836`). A stale execution gets `DBOSWorkflowConflictIDError` and "adopts the recorded outcome" (`_core.py:990-993`).
- READ. `application_version` defaults to an MD5 of the sorted `inspect.getsource` of every workflow, plus the DBOS version and the app name (`_dbos.py:418-443`). Any edit to a workflow therefore orphans its pending runs from automatic recovery. Dequeue takes only rows of its own version, and version-less rows only on the latest version (`_sys_db.py:5691-5702`; `6154d14`).
- READ. In-place code change goes through `DBOS.patch(name)` (`_dbos.py:4863`; `_sys_db.py:6873-6897`), which writes a marker row at the current position. An old execution that already has a checkpoint at or after that position takes the old path. The "at or after" rule was a fix for gaps in the counter ("patch: handle gaps in checkpoints order", `232dd75`, 2026-11-02).
- READ. `fork_workflow(workflow_id, start_step)` (`_dbos.py:3367-3406`; `_sys_db.py:2630-2800`) makes a new workflow under a new id. It copies `operation_outputs`, events and streams with `function_id < start_step` in one `INSERT ... SELECT` per table, whatever the batch size, then enqueues the new workflow. Children are inherited unless `replacement_children` is given.
- READ. Cancellation (`_sys_db.py:1982-2034`) sets `CANCELLED`, clears `owner_xid` and `suspend_key`, wakes result waiters, and can cascade to children one level at a time. The running body notices at its next step check. `resume_workflows` re-enqueues.
- READ. Idempotency: a caller-chosen id is set with `SetWorkflowID`. The insert is `ON CONFLICT DO UPDATE SET creator_xid=creator_xid RETURNING ...` (`_sys_db.py:1597-1611`). A different name, class or config raises `DBOSConflictingWorkflowError`; an existing row means "do not execute, attach" (`:1640-1670`); the policy `"reject"` raises `DBOSWorkflowIDInUseError` (`_context.py:56`).

## E. Cost

- EXECUTED. A workflow with two steps and one recv issued, before blocking, 2 INSERTs on the calling thread (status and input) and 15 statements on the executor thread: 9 SELECT, 3 UPDATE and 3 INSERT.
- EXECUTED. Each step cost **two transactions and four statements**. The check transaction reads `workflow_status.status` and the `operation_outputs` row. The record transaction runs the owner-check `UPDATE` (the SQLite write lock), then inserts the output row.
- EXECUTED. Recv setup added a check, one notification poll and a recorded sleep. Completion added the consume-and-record transaction and the outcome update.
- READ. Every step therefore takes a row lock on the workflow's `workflow_status` row. On SQLite it takes the database write lock. There is no batching of step checkpoints.
- READ. Large values can be kept outside the database through `ExternalStore` (`_external_storage.py:14-40`), with the checkpoint holding a small ref of key, size and sha256. Fan-out paths (bulk send, fork, dequeue) chunk their inserts, dequeue at 4,096 ids (`_sys_db.py:5739`). Postgres sessions get `idle_in_transaction_session_timeout` 60 s by default (`_dbos_config.py:29`).

## F. History and lessons

- "SQLite Support" landed in `8629cb2` (2025-08-27). It was followed by `0beb275` (2026-01-21): dequeue on SQLite was missing its isolation, so workflows were dequeued twice. Then came `f86363b` (2026-11-09, fixing issues #939 and #940), whose root cause is that pysqlite opens a transaction only before the first DML statement. A read before a write therefore ran in autocommit. Queue budgets overspent and datasource steps hit write skew. The fix is an explicit `BEGIN IMMEDIATE` before the first read (`_sys_db.py:5591-5596`).
- recv race fixes: `023ea56` (2024-08-29) registers the waiter before checking the database, so that a notification cannot be lost. `2ad42b6` (2026-03-18) handles missed notifications with a polling fallback. `186987a` (2026-06-12) fixes an async cancellation that leaked the waiter.
- Versioning arc: "Application Versioning" `ec240d8` (2025-02-25), "Improved Versioning Support" `9882c10` (2026-03-02), "Patching" `95d0df9` (2025-12-08), "Detect Patching Non-Determinism" `9aad8fa` (2026-06-12) and the gap fix `232dd75`. Three years in, code change under pending workflows is still being patched.
- Thread-free waiting arrived late and closed-source: "Suspend" `6b8e790` (2026-10-29), "Async Suspend" `bca092d` (2026-10-30), "Fix Suspend Indexes" `0e59afe` (2026-11-09), and suspended `get_result` `28192bd` (2026-11-20).
- Serialization: "Custom Serialization" `cb51bbe` (2025-10-08), "Expose Portable Serializer" `faeeb5a` (2026-04-21), and two 2026-11 fixes (`b5d2f3f`, `a3da1f2`) restoring dates and Decimals lost by portable JSON.

## Highlighted code

1. `dbos/_sys_db.py:4087-4163`. Replay matching by `(workflow_uuid, function_id)` plus a name check, and where cancellation is observed.
2. `dbos/_sys_db.py:3810-3916`. Ownership fencing and the step insert with its nondeterminism detection, differing by engine.
3. `dbos/_core.py:2538-2637`. Step = check, then run, then record. Shows the at-least-once window.
4. `dbos/_context.py:244-256`. The position counter, and the reserved timeout id that creates gaps.
5. `dbos/_sys_db.py:4476-4617`. recv in three phases. Consume-and-record in one transaction.
6. `dbos/_sys_db.py:4310-4337`. The send-side wake of a parked receiver: one primary-key probe in the send's transaction.
7. `dbos/_enterprise.py:85-116`. The suspend contract: park, raise, re-enqueue, replay.
8. `dbos/_error.py:518-545` with `dbos/_core.py:994-997`. A BaseException unwinds an arbitrary body and the slot is freed.
9. `dbos/_schemas/system_database.py:29-163`. `workflow_status`, `operation_outputs` and `notifications` in full.
10. `dbos/_sys_db.py:4906-4955`. A durable sleep stored as an absolute wake time, before the wait.
11. `dbos/_sys_db.py:6101-6136` with `dbos/_recovery.py:14-28`. Idempotent recovery by re-enqueue, guarded by executor id.
12. `dbos/_sys_db.py:1542-1676`. A caller-chosen id as the idempotency key, with conflict on a different function.
13. `dbos/_dbos.py:418-443`. The version as a source hash, and why edits strand pending work.
14. `dbos/_sys_db.py:6873-6897`. `patch()` marker semantics, including "at or after".
15. `dbos/_serialization.py:99-115, 238-251`. Pickle by default, and format-tagged rows that bypass the configured serializer.
16. `dbos/_sys_db_sqlite.py:42-50` with `dbos/_sys_db.py:5591-5596`. The SQLite IMMEDIATE and autocommit-read pitfall.
17. `dbos/_sys_db.py:2630-2800`. Fork as a set-based copy of the history prefix.

## What this suggests for vfs (INFERRED)

**Take.**
- **Unwind and replay instead of snapshot.** DBOS's answer to "a Python body cannot be paused mid-frame" is to record the result of every effectful call and raise a BaseException at the stop point. Resume re-runs the body from the top, and each recorded call returns its stored result. vfs's tool body fits this exactly. Its effectful calls are already vfs verbs passing one gate, so the gate is the natural recorder.
- **The paused state as plain rows.** DBOS keeps a status row (`SUSPENDED`, wait key, wake time) and one result row per position, and no frame. vfs's shell, being a request/reply machine, can do better: its state *is* serializable, so it can be stored directly with no replay.
- **The answer is written with the wake.** Recording the person's answer and flipping the paused record to "due" happen in one transaction, as `_wake_receivers` does. Any process may then resume. The resumer claims with a fencing token (`owner_xid`) so that exactly one runner proceeds. Recovery is idempotent because the claim is a conditional `UPDATE`.
- **Consumed answers are kept**, as notifications are, with `consumed_by`. They serve as the audit trail. Caller-supplied idempotency keys become primary keys.

**Avoid.**
- **Pickle.** Use typed JSON only, validated on read. A row's own format tag must never select an unsafe decoder.
- **Matching by position and name alone.** vfs's `Call` is typed and serializable, so each recorded result can be keyed on `(position, verb, canonical digest of the Call)`. A divergent replay then fails at the first differing call, with a precise refusal, not a terminal `ERROR` of the whole unit.
- **A write on every call.** DBOS pays two transactions per step and a lock on the parent row, because durable execution checkpoints everything. At 150,000 verb calls a day, vfs should write nothing on the unpaused path. It should record results only inside a tool body that might stop, and write the paused record only when a stop happens.
- **Waiting by holding a thread.** Open-source `recv` blocks a thread and polls, and on SQLite issues one query per waiter per second. vfs's "never hold a call open" matches the Enterprise suspend design, not recv.
- **A version as a whole-source hash.** A pending pause should carry the identity and version of the tool and policy it stopped in. Resume under a different version should be an explicit, classified refusal or migration, not a silently stranded row.
- **pysqlite's implicit transactions.** A read-then-write resume must take its lock deliberately, and on SQLite that means `BEGIN IMMEDIATE`. It must still never make plain reads wait.

**The sharpest lesson.** Replay-based resumption is what makes an arbitrary tool body pausable without a memory snapshot. Its correctness, though, rests entirely on the body being deterministic up to the stop. DBOS checks that only by step name, and after three years of version, patch and gap fixes it still has no better guard. vfs should make the recorded result's key the full typed `Call`, so that a mismatch is caught at the first divergent call.
