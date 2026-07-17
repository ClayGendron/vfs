# LangGraph — Influences for VFS and FSP

> Reference repo: `/Users/claygendron/Git/Repos/langgraph`

## Overview

LangGraph is a stateful, checkpointed graph execution framework built for agent runtimes. It models graph state as **shared mutable channels**, sequences state updates through **reducers** (binary operator aggregates), persists execution via **pluggable checkpoint savers** (sqlite, postgres, in-memory), and enables runtime interruption + human-in-the-loop via **thread-scoped config**. The architecture mirrors Linux kernel VFS patterns: abstract backend implementations (`BaseCheckpointSaver`, `BaseStore`, `BaseChannel`) with sync/async dual paths, binary-operator reducers for concurrent write resolution, and a "channels as POSIX file descriptors" mental model. FSP clients (LangGraph runtimes) will be the exact use case LangGraph checkpointing and store semantics were designed for — agent threads with persistent state, multi-writer conflict resolution, and streaming output.

## Navigation Guide

**Entry points:** `/libs/langgraph/langgraph/graph/state.py` (StateGraph builder), `/libs/langgraph/langgraph/pregel/main.py` (Pregel execution engine), `/libs/checkpoint/langgraph/checkpoint/base/__init__.py` (BaseCheckpointSaver protocol).

**Backend implementations (skip unless implementing a VFS store saver):**
- SQLite: `/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/`
- PostgreSQL: `/libs/checkpoint-postgres/langgraph/checkpoint/postgres/`

**Channels and concurrency:** `/libs/langgraph/langgraph/channels/base.py` (BaseChannel), `/libs/langgraph/langgraph/channels/binop.py` (BinaryOperatorAggregate reducer), `/libs/langgraph/langgraph/channels/last_value.py` (simpler append-only).

**Serialization:** `/libs/checkpoint/langgraph/checkpoint/serde/base.py` (SerializerProtocol — pluggable json/pickle/msgpack), `/libs/checkpoint/langgraph/checkpoint/serde/encrypted.py` (encryption wrapper).

**Store (long-lived namespace-keyed storage):** `/libs/checkpoint/langgraph/store/base/__init__.py` (BaseStore — SearchOp, GetOp, ListNamespacesOp on tuple-keyed items).

**Thread model & interrupts:** `/libs/langgraph/langgraph/types.py` (StateSnapshot, Interrupt, StreamMode), `/libs/langgraph/langgraph/pregel/_algo.py` (task execution + interrupt emission), `/libs/langgraph/langgraph/pregel/remote.py` (thread_id config routing).

**What to skip:** Examples, tests, SDK wrappers, TypeScript bindings, `langgraph-cli` deployment tooling. The conceptual core is 100% in the files above.

## File Index

| Path | Purpose |
|------|---------|
| `/libs/langgraph/langgraph/graph/state.py:115–150` | StateGraph class signature & channel type binding |
| `/libs/langgraph/langgraph/pregel/main.py:1–100` | Pregel executor, checkpoint load/save cycle |
| `/libs/checkpoint/langgraph/checkpoint/base/__init__.py:130–250` | BaseCheckpointSaver interface, `put()`, `get_tuple()`, `list()` semantics |
| `/libs/checkpoint/langgraph/checkpoint/base/__init__.py:35–100` | Checkpoint TypedDict: `id`, `ts`, `channel_values`, `channel_versions`, `versions_seen` |
| `/libs/langgraph/langgraph/channels/base.py:40–120` | BaseChannel protocol: `checkpoint()`, `update()`, `get()` |
| `/libs/langgraph/langgraph/channels/binop.py:48–130` | BinaryOperatorAggregate: binary reducer for concurrent writes |
| `/libs/checkpoint/langgraph/store/base/__init__.py:40–200` | BaseStore, Item, SearchOp, namespace tuple semantics |
| `/libs/checkpoint/langgraph/checkpoint/serde/base.py:1–50` | SerializerProtocol: `dumps_typed(obj) → (type, bytes)`, `loads_typed()` |
| `/libs/langgraph/langgraph/types.py:110–180` | StreamMode, Interrupt, StateSnapshot, CheckpointPayload |
| `/libs/langgraph/langgraph/pregel/_checkpoint.py:1–70` | `empty_checkpoint()`, `create_checkpoint()`, `channels_from_checkpoint()` |
| `/libs/langgraph/langgraph/pregel/_algo.py:1–50` | Task scheduling & write ordering |
| `/libs/langgraph/langgraph/pregel/_write.py` | ChannelWrite, ChannelWriteEntry (batched state updates) |
| `/libs/langgraph/langgraph/pregel/_read.py` | ChannelRead, ChannelReadEntry (read fan-in) |
| `/libs/checkpoint-postgres/langgraph/checkpoint/postgres/base.py` | PostgreSQL BaseCheckpointSaver impl: `put()`, `list()` SQL schema |
| `/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/aio.py` | SQLite async impl, tx semantics |
| `/libs/langgraph/langgraph/channels/last_value.py` | LastValue channel (append-only, no reducer) |
| `/libs/langgraph/langgraph/channels/named_barrier_value.py` | NamedBarrierValue: multi-writer synchronization |
| `/libs/langgraph/langgraph/pregel/_messages.py` | StreamMessagesHandler: LLM message token streaming |
| `/libs/langgraph/langgraph/pregel/_loop.py` | SyncPregelLoop, AsyncPregelLoop: main execution loop |

## Core Concepts (What They Did Well)

### 1. Checkpoint Abstraction + Versioning

**What:** `BaseCheckpointSaver.put(config, checkpoint, metadata, new_versions)` stores a `Checkpoint` (immutable snapshot) with channel versions. The `Checkpoint` object has:
- `id`: Unique, monotonically increasing (for sorting)
- `ts`: ISO 8601 timestamp
- `channel_values`: Dict of channel state
- `channel_versions`: Dict of version strings (one per channel)
- `versions_seen`: Per-node map of versions each node has observed

**Why it matters:** Channels track monotonic version strings, and reducers only fire on newly-updated channels. This enables **incremental computation** without re-executing nodes whose inputs haven't changed. For VFS, this is the pattern for **versioning files** — each write increments a version, and `versions_seen` lets you know which version a "reader" has consumed.

**FSP implication:** Checkpoints are append-only — every write creates a new id. FSP must expose `get_state(thread_id)` and `get_history(thread_id, limit)` to let clients replay execution. The version tracking lets FSP implement **read consistency without locks** — a query can ask "what did the world look like at version X?" and get a deterministic answer.

### 2. Pluggable Serializers (SerializerProtocol)

**What:** `SerializerProtocol` is a minimal interface:
```python
def dumps_typed(self, obj: Any) -> tuple[str, bytes]: ...
def loads_typed(self, data: tuple[str, bytes]) -> Any: ...
```

Implementations: JsonPlusSerializer, EncryptedSerializer (wraps another), custom.

**Why it matters:** Checkpoints are opaque to the framework — agents can store any Python object in channels, and the serializer decides how to encode it. This is the right inversion of control.

**VFS implication:** VFS needs a similar surface. Objects stored in the `grover_objects` table should allow custom serializers (pickle, msgpack, protobuf). Don't hardcode JSON.

### 3. Reducers via BinaryOperatorAggregate

**What:** When multiple nodes write to the same channel, instead of conflicting, the channel applies a **binary operator**:
```python
total = BinaryOperatorAggregate(int, operator.add)
total.update([1, 2, 3])  # total.value = 6
```

Each update is folded left-associatively: `value = op(value, update)`.

**Why it matters:** Solves the multi-writer problem without locks or consensus. For lists, use `operator.add` (concatenation). For dicts, use custom merge functions. For scalars, use `max`/`min`.

**VFS implication:** VFS allows concurrent mounts, each writing to their own entries. If two mounts want to contribute to the same `results` list, use a BinaryOperatorAggregate. The ordering of writes is *arbitrary*, but the semantics are deterministic.

**FSP implication:** When multiple agents write to the same namespace concurrently, FSP needs reducer semantics. Example: two agents append to a log. Reducer = `operator.add`. FSP must advertise which reducers it supports in capability negotiation.

### 4. Channel Versions for Deterministic Ordering

**What:** Every write increments the channel's version string. Nodes execute only when their input channels have newer versions than the node has seen before.

```python
versions_seen = {"node_a": {"messages": "5", "query": "3"}}
# If messages version is now "6", node_a re-executes.
# If query is still "3", it doesn't matter — node_a doesn't care.
```

**Why it matters:** Avoids re-executing nodes unnecessarily and gives a "happened-before" DAG without explicit message passing.

**VFS implication:** Every file write creates a new version. Clients can check versions to know if a file changed since they last read it, or query "was version X < version Y?" — forming a partial order without timestamps.

### 5. Thread-Scoped Config + Interrupts

**What:** Each invocation passes a `config` dict with `thread_id` and optional `checkpoint_id`. The checkpointer uses these as the primary key:

```python
config = {"configurable": {"thread_id": "user_123"}}
graph.invoke(input, config=config)
```

If a node calls `interrupt(value="...", resumable=True)`, execution pauses. `graph.invoke(..., config)` resumes from the checkpoint and continues.

**Why it matters:** Agents can park mid-execution waiting for human input, database results, or async operations. No background jobs or callbacks — just checkpoint → interrupt → checkpoint again.

**FSP implication:** FSP clients (runtimes) will embed thread_id in every request. FSP must ensure checkpoints are scoped by thread_id and support interrupt/resume semantics.

### 6. Streaming Modes

**What:** `stream_mode` in ["values", "updates", "checkpoints", "tasks", "debug", "messages", "custom"] controls what gets emitted:
- `"values"`: Full state after each step
- `"updates"`: Only node outputs (compact)
- `"checkpoints"`: Only checkpoint events
- `"debug"`: Checkpoints + task start/finish + errors
- `"messages"`: LLM message chunks + metadata

**Why it matters:** Different clients need different telemetry. An LLM UI wants token-by-token `"messages"`. A backend service wants compact `"updates"`. A debugger wants `"debug"`.

**FSP implication:** FSP should support similar modes. A streaming read might emit:
- Per-byte chunks (`"stream"`)
- Complete lines (`"lines"`)
- Checkpoints (`"checkpoints"`)
- Full result once (`"values"`)

### 7. Store as Namespace-Keyed Long-Term Memory

**What:** `BaseStore` holds items with hierarchical namespace (`tuple[str, ...]`) + key. Operations:
- `GetOp(namespace, key)`: Retrieve one item
- `SearchOp(namespace_prefix, filter, query)`: Semantic search with optional filtering
- `ListNamespacesOp(match_conditions)`: Explore namespace structure

Items have `value` (dict), `created_at`, `updated_at`. Optional TTL.

**Why it matters:** Separate from checkpoints. Checkpoints are stateful execution traces. Stores are facts — embeddings, user profiles, external API responses. Both live in the database but serve different access patterns.

**VFS implication:** VFS `.versions/` and `.connections/` namespaces are analogous to stores. A connection record is `value={"type": "link", "target": "/path/to/target"}`. A version record is `value={"number": 1, "timestamp": "...", "author": "..."}`. Make these queryable (not just CRUD-able).

### 8. Append-Only Checkpoint Log

**What:** Every call to `checkpointer.put(config, checkpoint, ...)` returns an updated `config` with a new `checkpoint_id`. The checkpoint is immutable — you never overwrite. History is preserved for time-travel debugging.

**Why it matters:** Enables instant replay. Given a `thread_id` and `checkpoint_id`, the graph can restore to that exact state and continue from there. No garbage collection needed if you keep the log.

**VFS implication:** Every write to a file should create a checkpoint. The chain `version_1 → version_2 → version_3` is the append-only log. Time-travel is query-by-version.

## Anti-Patterns & Regrets

### 1. Checkpoint Schema Coupling to Serializer

**Issue:** Checkpoint structure (`Checkpoint: TypedDict`) hardcodes `channel_values` as a dict. If you want to add a new field (e.g., `deleted_channels`), you must version the schema and write migration logic.

**Regret:** LangGraph v0 mixed checkpoint versioning (v1, v2, v3, v4 formats exist) with serializer versioning (json, pickle, msgpack). This led to combinatorial test cases and subtle bugs (e.g., a v3 pickle checkpoint read with a v4 json deserializer).

**For VFS/FSP:** Don't let backend-specific schema leak into the object model. Define a versioned envelope (like `Checkpoint.v = 4`) separate from the serializer choice. Example: `{v: 4, serializer: "msgpack", data: <bytes>}`.

### 2. Missed Opportunity: Store Should Support Full-Text + Vector Search Natively

**What they did:** `SearchOp(query="...")` is optional; most implementations only support filtering.

**Regret:** Semantic search was grafted on late. The `BaseStore` interface doesn't mandate embeddings, so implementations vary widely. Some ignore `query` entirely.

**For VFS:** If you add a semantic_search method (which you have), make it a **first-class store operation**, not a heuristic post-filter. Example: `glob("*.py")` returns file paths; `semantic_search("authentication logic")` returns ranked results. Don't conflate them.

### 3. Thread Model Doesn't Isolate Per-User State by Default

**What they did:** `thread_id` is a string, typically a user ID. But there's no enforcement that user A can't call `config={"thread_id": "user_b"}` and read user B's state.

**Regret:** Authorization is the caller's responsibility. This works in a trusted backend but is dangerous if FSP is exposed over HTTP.

**For FSP:** Explicitly scope checkpoints and stores by user. Don't pass raw thread_id from the client — use the authenticated user ID. Example: `effective_thread_id = f"{authenticated_user_id}:{client_requested_thread_id}"`.

### 4. Streaming Modes Are Loosely Typed

**What they did:** `StreamPart` is a TypedDict union, but at runtime it's just dicts. If a client expects `MessagesStreamPart` but gets `ValuesStreamPart`, they find out at runtime.

**Regret:** No static guarantees. A client registering for `stream_mode="messages"` might accidentally handle `stream_mode="updates"`.

**For FSP:** Define strict schemas for each streaming mode and validate client subscriptions. If a client subscribes to `mode="checkpoint"`, don't send it `mode="values"` by accident.

### 5. Interrupt Semantics Conflate Pause with Rejection

**What they did:** `interrupt(value)` pauses the graph, and the value is passed to the next `invoke()`. It's up to the caller to decide if the value is an input ("user provided this") or a rejection ("this node request but user said no").

**Regret:** No first-class "resume with rejection" path. If a node says "I need human approval", and the human says "no", you either resume with `None` (ambiguous) or manually edit the checkpoint to skip that node (risky).

**For FSP:** Design an explicit `InterruptResolution` type: `{"accepted": true, "value": ...}` or `{"accepted": false, "reason": "..."}`. Let the graph branches on the resolution, not on the value.

## Implications for VFS (Implementation)

### 1. Checkpoint Versioning & History

Grover's VFS should adopt LangGraph's append-only checkpoint pattern:
- Every write (file, directory, connection) creates a new checkpoint with auto-incrementing version.
- Store checkpoints in the database with `id` (monotonic string), `ts` (timestamp), `channel_values` (the state at that version).
- Expose `get_version(path, version_number)` to retrieve historical file contents.
- Implement `list_versions(path)` to show the full history.

**Mechanism:** In `DatabaseFileSystem._write_impl`, after persisting the new content, call `checkpointer.put()` to record the state. Store the `checkpoint_id` in the file metadata so you can rewind.

### 2. Reducers for Concurrent Mount Writes

When multiple mounts write to the same VFS namespace (e.g., two databases appending to a shared results list), use channel reducers:

```python
from operator import add
results = BinaryOperatorAggregate(list, add)
# Mount A appends [item_1]
# Mount B appends [item_2]
# Result: [item_1, item_2] (order arbitrary but deterministic)
```

Document which operations support concurrent writes and which don't:
- Lists: `operator.add` (concatenation)
- Dicts: Custom merge (last-write-wins, or deep merge)
- Scalars: `max`/`min`/custom

### 3. Store for `.versions/`, `.connections/`, Metadata

Implement VFS stores for each metadata type:

```python
# File versions
store.put(
    namespace=("files", mount_id, "versions"),
    key=f"{file_path}#{version_number}",
    value={"author": "user_id", "timestamp": "...", "size": 1024}
)

# Connections (graph edges)
store.put(
    namespace=("files", mount_id, "connections"),
    key=f"{source_path}→{target_path}",
    value={"type": "link", "direction": "source->target"}
)
```

Expose `SearchOp` queries so clients can find versions or connections matching a pattern.

### 4. Serializer Pluggability

Make VFS's serializer pluggable (not just JSON). Allow users to provide custom `SerializerProtocol` implementations when constructing a `DatabaseFileSystem`:

```python
fs = DatabaseFileSystem(
    engine=engine,
    serde=MessagePackSerializer(),  # Or EncryptedJsonSerializer
)
```

This lets customers use encryption at rest, compression, or domain-specific formats without modifying Grover.

### 5. User Scoping via Config

Thread VFS requests through a config that includes `user_id`:

```python
await fs.read(path, user_id=user_id)
```

VFS uses `user_id` to filter results (permissions) and scope checkpoints. This mirrors LangGraph's `thread_id`.

### 6. Multi-Version Consistency

Implement `versions_seen` semantics: if a client reads a file at version V, and later writes to a directory, the directory write includes `versions_seen={file_path: V}`. This prevents the classic bug: "I read file A, then file B was updated, but I still think the world matches what I read."

For VFS queries like `glob`, include returned versions in the result so the client can declare what they've seen.

## Implications for FSP (Protocol)

### 1. Streaming + Checkpoints on the Wire

FSP must support multiple streaming modes over its MCP wire:

- **`stream_mode=values`**: Emit full state dicts after each step
- **`stream_mode=updates`**: Emit only changed keys
- **`stream_mode=checkpoints`**: Emit checkpoint IDs + metadata, not content
- **`stream_mode=debug`**: Emit task start/finish + errors

Example FSP message:

```json
{
  "type": "checkpoint",
  "thread_id": "thread_123",
  "checkpoint_id": "ck_v1_001",
  "timestamp": "2026-04-19T10:00:00Z",
  "values": {"file_handle": "/data/file.txt", "offset": 512}
}
```

### 2. Namespace-Keyed Stores on the Wire

FSP needs a store API that mirrors LangGraph's hierarchical namespaces:

```json
{
  "method": "store.search",
  "namespace_prefix": ["documents", "user_123"],
  "query": "authentication patterns",
  "filter": {"status": "active"},
  "limit": 10
}
```

This allows agents to query facts about the filesystem without reading every file. Example: "Find all API schemas that mention OAuth" → `store.search(namespace_prefix=["apis"], query="OAuth")`.

### 3. Version Tracking for Read Consistency

Every FSP read response includes a `version` field:

```json
{
  "method": "read",
  "path": "/file.txt",
  "success": true,
  "data": "...",
  "version": "ck_v1_005"  // This file's version at read time
}
```

Clients can include `seen_versions={"file.txt": "ck_v1_005"}` in future writes to detect conflicts.

### 4. Reducer Advertisement in Capabilities

FSP should advertise which reducers it supports for concurrent writes:

```json
{
  "method": "capabilities",
  "reducers": {
    "list": ["add", "replace"],
    "dict": ["merge", "replace"],
    "scalar": ["replace"]
  }
}
```

Clients can then safely call "multi-agent writes to the same list" if both agents know `"add"` is the reducer.

### 5. Interrupt + Resume on the Wire

FSP must expose interrupt/resume as first-class operations:

```json
{
  "method": "invoke",
  "command": "interrupt",
  "thread_id": "thread_123",
  "checkpoint_id": "ck_v1_010",
  "reason": "waiting_for_user_input",
  "resumable": true
}
```

And resume:

```json
{
  "method": "invoke",
  "command": "resume",
  "thread_id": "thread_123",
  "checkpoint_id": "ck_v1_010",
  "input": {"user_choice": "approved"}
}
```

### 6. Error Types Match Semantic Classes

FSP errors should map to semantic classes (like Grover's NotFoundError, WriteConflictError, etc.):

```json
{
  "success": false,
  "error": {
    "code": "write_conflict",
    "message": "Version mismatch: expected ck_v1_005, got ck_v1_006",
    "expected_version": "ck_v1_005",
    "current_version": "ck_v1_006"
  }
}
```

This lets clients detect retryable vs. fatal errors without string parsing.

### 7. Checkpointing Durability Options

Expose LangGraph's durability modes as FSP config:

- **`durability=sync`**: Wait for checkpoint to persist before returning
- **`durability=async`**: Return immediately, checkpoint in background
- **`durability=exit`**: Checkpoint only when the agent exits

```json
{
  "method": "invoke",
  "config": {
    "thread_id": "thread_123",
    "durability": "async"
  },
  "input": {...}
}
```

Clients can trade off latency vs. safety per request.

## Open Questions

1. **Checkpoint garbage collection:** LangGraph keeps all checkpoints forever. For long-running agents (weeks of conversation), this becomes expensive. Should FSP implement a `prune(strategy=keep_latest|delete_before_timestamp)` operation? Should it be automatic?

2. **Store indexing for large namespaces:** If a store has millions of items under `("documents", "*")`, how does `ListNamespacesOp` scale? Should FSP require indexes on namespace prefix?

3. **Serializer negotiation:** If FSP supports multiple serializers (json, msgpack, protobuf), how does the client and server agree? Per-request header, or one-time negotiation?

4. **Reducer composition:** Can reducers be chained? E.g., "first concatenate lists, then deduplicate by ID"? Or is each channel limited to one reducer?

5. **Transactional consistency:** LangGraph's channels are updated atomically within a checkpoint, but cross-checkpoint atomicity is not guaranteed. Should FSP expose transaction semantics (all-or-nothing writes) for operations that touch multiple files?

6. **Conflict resolution policies:** When two agents write to the same file path concurrently (both aiming for the root mount), does FSP use the reducer, last-write-wins, or require explicit conflict resolution?
