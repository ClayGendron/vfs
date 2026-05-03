# 014 — Auto-Chunk and Auto-Index on Write

- **Status:** draft
- **Date:** 2026-05-01
- **Owner:** Clay Gendron
- **Kind:** feature + backend
- **Depends on:** 013 (chunking surface, code-gram primitives), existing
  vector / FTS / version pipelines

## Intent

Make `DatabaseFileSystem` writes self-maintaining for the three derived
artifacts that downstream search depends on: **chunks**, **trigrams**,
and **vector embeddings**. Today the model exposes the primitives
(`VFSEntry.chunk()`, `iter_code_grams`, `Vector` field) but every
caller has to wire them together by hand and remember the order. The
result is silent drift between file content and its derived state,
especially in batch data pipelines that overwrite many files at once.

This story introduces two write-time switches on `DatabaseFileSystem`:

```python
DatabaseFileSystem(
    ...,
    auto_chunk: bool = True,
    auto_index: bool = True,
)
```

When set, a single `write()` call atomically:

1. Detects content change vs. the latest stored version.
2. Cuts a new version row (existing behavior).
3. Chunks the file if `auto_chunk` is on and `index_content is True`.
4. Refreshes trigrams and embeddings for whichever rows
   (file *or* its chunks) carry `index_content is True` after step 3.

Callers can still drive each step manually by constructing a filesystem with
`auto_chunk=False` / `auto_index=False`, but the default is "do the right
thing." The pipeline-friendly contract is: **after `write()` returns success,
the database is queryable end-to-end without a follow-up maintenance call.**

## Why

Three observed pain points:

- **Pipelines forget steps.** Data ingestion code calls `write()`,
  forgets to chunk, and the trigram index ships with file rows but no
  chunk rows. `grep` scans full files instead of chunks.
- **Order is load-bearing and undocumented.** The correct order is
  version → chunk → index. Doing it backwards (index, then chunk)
  double-indexes the file and its chunks, so `grep` returns the same
  match twice. Doing it in parallel races on `index_content`.
- **`index_content` is dormant.** Story 013 added the flag as the
  signal that gates content-side indexes, but no write path consults
  it. Without an enforcement point the field is documentation, not a
  contract.

A consistent write-time pipeline is also the precondition for the
Phase-2 grep work in 013: trigrams over an empty chunk table are not
useful, and a trigram maintenance loop that runs outside the write
transaction will lose chunks on partial failures.

## Scope

### In

1. **Two new constructor flags on `DatabaseFileSystem`.**

   ```python
   def __init__(
       self,
       ...,
       auto_chunk: bool = True,
       auto_index: bool = True,
   ) -> None:
   ```

   Stored as instance state. `bool(...)` coerced. Subclasses inherit
   the flags without override.

2. **Auto-chunk behavior (when `auto_chunk` is on).**

   For every entry in the write batch where `kind == "file"` and
   `index_content is True`:

   - Call `entry.chunk()` (which already mutates `index_content = False`
     on success and returns `[]` if the content fits in one chunk).
   - Append the returned chunk rows to the same write batch so they
     are inserted in the same transaction as the file row.
   - The chunk rows inherit `owner_id` from the file (already handled
     by `VFSEntry.chunk()`).

   **Conflict rule (batch-fatal):** if the incoming write batch
   *already* includes any `kind == "chunk"` whose `parent_path`
   (computed from the chunk path's `__meta__/chunks` segment) is
   also a file in the same batch with `index_content is True`,
   the call returns `VFSResult(success=False, candidates=[],
   errors=[...])` before any DB mutation. The error message names
   the offending file and the remediation:

   ```text
   Cannot auto-chunk file '/foo.py' because the same write batch
   already provides chunks for it. Either set index_content=False on
   the file, configure this filesystem with auto_chunk=False, or omit the
   pre-built chunk rows. Resubmit the batch after resolving — no
   entries from this batch were written.
   ```

   The check runs as a single batch-level pass before any per-entry
   chunking work, so the call returns before any database mutation.
   Rationale: this conflict is almost always a pipeline bug — the
   caller intended either auto-chunk *or* pre-built chunks, not
   both. Letting unrelated entries through hides the bug and risks
   a partially-committed batch where some files have indexes that
   don't reflect the caller's intent. Failing the whole batch
   surfaces the bug immediately and keeps the data store
   consistent.

   **Re-chunk cascade:** when a file row is updated and the new
   content differs from the stored content (detected in step 3 below),
   the backend deletes pre-existing chunk rows for that file before
   inserting the freshly-cut chunks. Cascade is part of the same
   transaction.

3. **Change detection (precondition for auto_index).**

   `_write_impl` already computes `content_hash` per incoming entry
   via `_content_metadata`. Compare:

   - For new files: always treated as changed.
   - For existing files: compare `incoming.content_hash` against
     `existing.content_hash`. If equal, the write is a no-op —
     no chunking, no indexing, no version row, *and no
     `updated_at` refresh on the existing row*. The row is left
     completely untouched.
   - For chunks: compare against existing chunk's `content_hash`.

   This changes the existing `_write_impl` behavior, which currently
   refreshes `updated_at` on unchanged writes. Story 014 makes that
   refresh conditional on a real change. Rationale: `updated_at`
   should reflect the last time the row's content actually changed,
   so downstream consumers (caches, replication watchers, change
   feeds) can treat it as a reliable change signal. A re-run of an
   ingestion pipeline over identical content should be observably
   free.

   Change detection runs *before* the chunk cascade so an unchanged
   file does not destroy and re-insert chunk rows.

4. **Auto-index behavior (when `auto_index` is on).**

   **Auto-index runs before any database write.** It computes
   trigram changes, calls the embedding provider, and stages every
   value on the in-memory entries / session. The single persist phase
   (item 5 below) then writes file rows, chunk rows, trigram staging
   deltas, and embedding values in the same flush. There is no second
   `UPDATE` to back-fill `embedding` after the row exists, and no
   follow-up maintenance call is required for grep correctness.

   Rationale:
   - One round-trip to the database instead of three.
   - A provider failure aborts the pipeline cleanly — no DB state
     has been mutated yet, so there is nothing to roll back.
   - The `embedding` column is never NULL between "row exists" and
     "row is searchable"; the row is born with its vector.

   For every entry that participates in content-side indexing and
   whose content or `index_content` state changed:

   - **Trigrams.** Extract old and new gram sets via the 013 pipeline
     (folded by default), then stage only the changed facts:
     - new entry: stage every new gram as `action="add"`
     - existing edit: stage `old_grams - new_grams` as
       `action="delete"` and `new_grams - old_grams` as
       `action="add"`
     - entry that becomes non-indexable: stage every old gram as
       `action="delete"`

     SQLAlchemy queues the staging rows in the unit of work; the
     actual `INSERT` happens at the persist flush in item 5. The
     contract is "after `write()` succeeds, grep is correct by
     reading compressed posting blocks plus staged adds minus staged
     deletes." The backend implements `_apply_index_maintenance(...)`
     and the base class calls it. The row-store MVP from 013 may apply
     the same deltas directly to `vfs_entry_chunk_grams`; the
     posting-list adapter stores them in its staging table.

     If a row changes multiple times before compaction, staging rows
     are interpreted by **latest action wins** per `(gram_kind,
     gram_key, entry_id)`. This prevents an older pending `delete`
     from hiding a newer pending `add` for the same gram.
   - **Embeddings.** Collect every entry that needs an embedding
     (`index_content is True`, content changed, no caller-provided
     `embedding`) into a single list and hand the whole list to the
     configured embedding provider in **one call**. The provider
     decides how to batch — true bulk request, sub-batches by token
     budget, or one-at-a-time fallback. The base class never iterates
     entries against the provider itself. The provider returns a
     vector per entry in input order; the base class assigns each
     vector to `entry.embedding` in memory. The value rides along
     when the entry is `INSERT`ed (or `UPDATE`d) at the persist
     flush. Persistence is mandatory — vectors must be on-disk
     before `write()` returns success. If the entry was *explicitly*
     given an embedding by the caller (tracked through
     `_explicit_fields`), it is excluded from the bulk call and its
     value wins — auto-index does not overwrite caller-provided
     embeddings (but those caller-provided values are still
     persisted by the same flush, because they were already on the
     entry when persist runs).
   - **FTS / lexical tokens.** Already maintained by existing write
     path metadata (`lexical_tokens` field, `search_tsv` generated
     column). Confirmed in scope only because the same flag should
     gate any future FTS-side maintenance for symmetry.

   Cleanup work for files cleared to `index_content = False` by
   auto-chunk is staged for the persist phase, not issued separately:
   delete-delta staging rows plus the embedding clear ride along in
   the same flush as the new chunks' INSERTs. The file becomes
   structurally visible (path, size, hash) but invisible to
   content-side search; its chunks carry the index instead.

5. **Single persist phase.**

   This is the only stage that mutates the database. It runs once
   per `write()` and ends in one `await session.flush()`:

   1. Stage delete trigram deltas for old indexable rows before stale
      chunks or permanent-delete content disappear.
   2. `DELETE` stale chunks for re-chunked files.
   3. Clear stale embeddings for files whose `index_content` flipped
      to `False` in auto-chunk.
   4. Cut version rows for existing files whose content changed
      (existing pipeline).
   5. `INSERT` all new file rows, chunk rows, and trigram staging
      rows in a batched insert. Embedding vectors ride along on the
      entry's `embedding` column.
   6. `UPDATE` existing files whose content changed, including the
      new content, hash, version pointer, and pre-computed
      `embedding`.
   7. Commit any new parent-dir rows.

   After the flush, posting-list adapters check the staging-table
   row count. If pending rows exceed `5_000_000`, the backend requests
   a compressed posting-list flush. That flush may run outside the
   user write transaction because grep remains correct while staging
   rows are pending. Grep and flush code both fold pending rows using
   latest-action-wins semantics before applying adds/deletes.

   The session's transaction is owned by the caller / router; this
   stage does not commit. If the enclosing transaction rolls back,
   every mutation in this stage rolls back together.

6. **Failure semantics.**

   `write()` does not raise for user-correctable problems. Instead
   it returns `VFSResult(success=False, candidates=[], errors=[...])`.
   The `errors` list carries human-readable messages with the
   offending path(s); `candidates` is empty because — by the
   "candidates = in the database" contract — nothing was written.

   - **Stage 5 file-and-chunks conflict** — `errors` carries one
     entry naming the offending file. No DB mutation.
   - **Stage 5 auto-chunk runtime error (e.g. `split_content`
     raises)** — `errors` carries the exception message and the
     offending path. No DB mutation.
   - **Stage 6a (trigram extraction) error** — `errors` carries the
     exception. Nothing to roll back.
   - **Stage 6d (embedding provider) error** — `errors` carries
     the provider exception. The provider owns its own
     retry/backoff inside the single bulk call.
   - **Stage 7 (persist flush) error** — the transaction rolls
     back: no file rows, no chunk rows, no trigram staging rows, no embedding
     updates persist. `errors` carries the underlying SQL error.
     Computed vectors are discarded.

   Programmer errors (genuinely broken state, like a corrupt model
   or a session in an unusable state) are still raised as
   exceptions — `write()` catches and converts the *expected*
   failure modes, not all of Python.

   There is no window where a file row exists with `index_content
   = False` but its chunks have not been inserted. There is no
   window where a row exists but its embedding does not — both
   are written in the same statement. There is no window where
   chunks exist with `index_content = True` but their trigram staging
   deltas have not been inserted.

   **Multi-mount note.** All of the above failure cases are
   per-mount. When the input batch spans multiple mounts (item
   12), each mount's failures are independent. A failure on mount
   B does not roll back mount A's commit — the merged result
   carries A's candidates *and* B's errors, with `success=False`
   and `to_str()` emitting both a `write errors:` block (B) and
   a `write success:` block (A). Callers that need cross-mount
   atomicity must serialize their writes per mount and handle
   reconciliation themselves.

7. **Entry-focused `write()` signature.**

   The public `write()` API is reshaped so entries are the primary
   input — the first positional argument — with `path` / `content`
   becoming keyword-only convenience args:

   ```python
   async def write(
       self,
       entries: Sequence[VFSEntry] | None = None,
       *,
       path: str | None = None,
       content: str | None = None,
       overwrite: bool = True,
       user_id: str | None = None,
   ) -> VFSResult: ...
   ```

   Two call shapes:

   ```python
   # Primary path — positional list of entries, no kwarg needed
   await fs.write([entry_a, entry_b])

   # Convenience — single path + content, kwargs only
   await fs.write(path="/foo.txt", content="hello")
   ```

   Rationale: the existing API requires `entries=[...]` as a kwarg
   even though it is the most common form. Promoting it to first
   positional matches how callers actually use the function. The
   `path` / `content` form is the convenience shortcut for the
   single-file case and is rarely used in pipelines, so demoting it
   to keyword-only costs little and removes the ambiguity of "what
   does `fs.write([...])` mean — a list or a path?".

   `_write_impl()` accepts the same arguments. Bulk-load pipelines that want to
   defer maintenance should construct the filesystem with
   `auto_chunk=False, auto_index=False` and run the maintenance pass once at the
   end if they prefer batched index builds.

   Backwards compatibility: callers that already use the
   `entries=[...]` kwarg form continue to work — the parameter is
   still named `entries`, just no longer kwarg-only. Callers that
   use `write(path, content)` positionally need to migrate to the
   keyword form `write(path="...", content="...")`. Migration notes
   ship in the changelog.

8. **Result shape — candidates are facts, errors are explanations.**

   `write()` returns a `VFSResult` (no exceptions raised for
   user-correctable problems). Two new pieces of contract:

   ```python
   class Candidate:
       path: str
       kind: str          # "file" | "chunk" | "version" | "edge" | "directory"
       status: Literal["created", "updated", "unchanged"] | None
       # ...other fields unchanged

   class VFSResult:
       function: str
       success: bool      # equivalent to: not errors
       candidates: list[Candidate]
       errors: list[str]

       def __str__(self) -> str:
           return self.to_str()

       def to_str(self) -> str: ...
   ```

   **Candidates mean "this row is now in the database."** The
   `status` field has exactly three values:
   - `created` — new row inserted by this call
   - `updated` — existing row whose content changed
   - `unchanged` — existing row, hash matched, no DB write happened
     (file row only — pre-existing chunks and versions are not
     pulled into the result for unchanged files)

   On a successful `write()`, the candidates list contains every
   row the persist phase touched: file rows, newly-created chunk
   rows (status=`created`), newly-cut version rows
   (status=`created`), plus any unchanged file rows. There is no
   `rejected` status — if a row didn't get written, it isn't in
   `candidates`.

   **Errors mean "this didn't happen."** When any error fires
   (batch-fatal conflict, persist flush failure, embedding provider
   failure), the affected entries do not appear in `candidates` at
   all. The error message in `errors` carries the path(s) and the
   reason.

   `success` is `not errors`. At the **per-mount** level the result
   is binary: either the write went through and you have
   candidates, or it didn't and you have errors. At the
   **multi-mount router** level (item 12) `candidates` and `errors`
   can both be non-empty in the same result — that's the signal
   that some mounts committed and some didn't. See item 12 for the
   merge semantics.

   **Why `to_str()` lives on the result.** The primary consumer of
   `write()` is an agent loop that returns the call summary back
   to the model. `__str__` delegates to `to_str()` so common
   patterns are one-liners:

   ```python
   print(await fs.write([entry]))         # tool-call output
   return str(await fs.write([entry]))     # return to model
   await fs.write([entry])                 # fire-and-forget
   result = await fs.write([entry])        # explicit branching
   if not result.success: ...
   ```

   **Output format.** The formatter never uses the word
   "candidates" in its output. Two blocks, both optional:

   - `write errors:` — one line per error, each line `<path>:
     <reason>`. Rendered first when present.
   - `write success: <counts>` — counts aggregated by displayable
     write kinds only: files, chunks, and edges. Version rows are
     never included in the success summary. For a single-file batch,
     a path line appears below the summary with the status verb. For
     multi-file batches, no path lines are emitted; the agent /
     caller can walk `result.candidates` for details if it wants them.

   Sample outputs covering the four shapes:

   *Empty batch (no entries to write):*
   ```text
   write: nothing to do
   ```

   *Single-entry success:*
   ```text
   write success: 1 file, 4 chunks written

     created /repo/main.py
   ```

   *Multi-entry success:*
   ```text
   write success: 3 files, 6 chunks written
   ```

   *Errors only:*
   ```text
   write errors:
     /repo/auth.py: file + chunks both in batch with index_content=True
   ```

   *Mixed (multi-mount partial commit) — errors first, then
   success:*
   ```text
   write errors:
     /docs/notes.md: pgvector dimension mismatch (mssql_docs)

   write success: 2 files, 6 chunks written
   ```

   The kind counts in the success line enumerate only files, chunks,
   and edges. A status breakdown (`1 created, 1 updated, 1 unchanged`)
   is appended in parentheses after the file count when the batch
   contains a mix; pure single-status batches omit it. Version rows
   may exist in `result.candidates` for programmatic inspection, but
   they are hidden from the human write summary.

9. **Backend hook surface.**

   The base class supplies:

   ```python
   async def _stage_chunk_cascade(
       self,
       file_entries: list[VFSEntry],   # files with content changes
       *,
       session: AsyncSession,
   ) -> None:
       """Stage a DELETE of existing chunk rows for these files for
       the persist flush. Default impl issues DELETE by path prefix
       '/path/__meta__/chunks/'. Called from the persist phase, not
       from auto-chunk."""

   async def _apply_index_maintenance(
       self,
       entries: list[VFSEntry],
       *,
       old_entries: dict[str, VFSEntry] | None = None,
       delete_only: bool = False,
       session: AsyncSession,
   ) -> None:
       """Compute trigram add/delete deltas + embeddings and stage
       them for the persist flush.

       *old_entries* supplies the current persisted content for
       existing rows so the backend can compute:

           old_grams - new_grams -> delete deltas
           new_grams - old_grams -> add deltas

       When delete_only=True, recalculate the current trigrams for
       the supplied entries and stage delete deltas only. This is used
       by delete and by files whose flag was cleared to index_content
       = False.

       Embedding work is delegated to the configured provider in a
       single bulk call (see item 10). Trigram work iterates the
       entries locally because it is pure-CPU. No INSERT, UPDATE,
       or DELETE is *issued* here — everything is queued on the
       session and emitted at the persist flush in item 5."""
   ```

   Default implementations are no-ops on the base class so the
   in-memory backend works without trigram tables. `PostgresFileSystem`
   overrides both. MSSQL does the same in story 013 phase 4.

10. **Embedding provider contract — bulk by default.**

    The base class never calls the embedding provider once per
    entry. Inside `_apply_index_maintenance` it builds **one list**
    of entries that need embeddings (`index_content is True`,
    content changed in change detection, no caller-provided
    embedding) and invokes the provider exactly once per `write()`.
    The call happens **before** any database write so a provider
    failure aborts the pipeline cleanly.

   ```python
   class EmbeddingProvider(Protocol):
       async def embed_entries(
           self,
           entries: Sequence[VFSEntry],
       ) -> Sequence[Vector]:
           """Return one vector per input entry, in input order.
           Implementations are free to:
             - send the whole list to the upstream API in one request,
             - sub-batch by token budget / rate limit,
             - serialize to one-at-a-time as a fallback.
           The base class makes no assumption about how the work is
           sharded — only that input order is preserved on output."""
   ```

   Rationale: providers know their own throughput limits, token
   budgets, and rate-limit headroom; the VFS does not. Handing the
   full set to the provider lets it issue a single OpenAI/Voyage/
   Bedrock batch request when the API supports it, and degrade
   transparently when it doesn't. This also removes per-entry
   round-trip overhead from inside the SQLAlchemy transaction —
   one HTTP call instead of N.

   The provider is responsible for:
   - returning vectors in the same order as the input entries
   - failing the whole call if any entry cannot be embedded (the
     base class re-raises and no DB write happens)
   - applying its own retry / backoff inside a single
     `embed_entries` call, not across calls

   The base class is responsible for:
   - excluding entries that already have a caller-provided embedding
   - assigning each returned vector to `entry.embedding` in memory
   - skipping the call entirely when the bulk list is empty

11. **Public API additions are confined to:**
    - the two constructor flags (item 1),
    - the `EmbeddingProvider.embed_entries` Protocol (item 10),
    - the new `Candidate.status` field and the `VFSResult.__str__`
      / `to_str()` formatter for the write function (item 8).

    Everything else stays put: chunking config still lives on
    `VFSEntry.split_content`, the embedding provider is still
    configured at `DatabaseFileSystem` construction, trigram
    extraction config still lives on the 013 module, and the
    existing read/grep/search `VFSResult` shape is untouched.

12. **Multi-mount semantics — per-mount atomicity, no cross-mount
    atomicity.**

    `VFSClient.write()` (the router) groups the input batch by
    which mount owns each path, then calls each mount's
    `_write_impl` independently. Each mount has its own session,
    its own transaction, and runs the full pipeline (validate →
    fetch → change-detect → auto-chunk → auto-index → persist
    flush) on its slice of the batch.

    The contract:
    - **Per-mount atomicity** is preserved by the underlying
      session. A mount either commits its slice cleanly or rolls
      it back; there's no half-written mount.
    - **Cross-mount atomicity is NOT provided.** vfs does not
      attempt two-phase commit across heterogeneous backends — a
      Postgres mount and an MSSQL mount cannot share a
      transaction. If mount A succeeds and mount B fails, A's
      writes are committed and B's writes never happened.

    The router merges per-mount results into one `VFSResult`:
    - `candidates = [...c for c in result.candidates for result in
      per_mount_results]` — flattened union, order roughly
      mount-iteration order.
    - `errors = [...e for e in result.errors for result in
      per_mount_results]` — flattened union; messages may be
      prefixed with the mount name for clarity.
    - `success = not errors` — `False` if any mount errored.

    A mixed outcome (some mounts committed, others failed) yields
    `success=False` AND non-empty `candidates`. The "candidates =
    in the database" contract still holds — those rows ARE in
    their respective mount's database. `to_str()` surfaces this
    by emitting both the `write errors:` block (first) and the
    `write success:` block (second) — the presence of both blocks
    is the partial-commit signal.

    Sample output for a mixed write across `/workspace` (Postgres,
    succeeded) and `/docs` (MSSQL, failed):

    ```text
    write errors:
      /docs/notes.md: pgvector dimension mismatch (mssql_docs)

    write success: 2 files, 6 chunks written
    ```

    The agent / caller reads the errors first (these need
    handling) then the success block (these are committed). The
    caller is responsible for deciding what to do — retry the
    failed mount, surface to a human, etc. vfs does not attempt
    to roll back the successful mounts because (a) it can't
    without a distributed transaction, and (b) doing so would
    require speculative writes that violate the
    content-before-commit invariant.

    Rationale: 2PC across heterogeneous DBs is genuinely hard and
    of dubious value for this product — the typical multi-mount
    setup is "workspace on SQLite, docs on Postgres" where the
    mounts represent independent stores by design. Surfacing
    partial commit honestly is more useful than hiding it.

### Out

- Async background indexing. All maintenance runs inline with the
  write transaction. A future story can add a deferred-maintenance
  queue for write-heavy pipelines.
- Embedding *re-computation* for unchanged content. Change detection
  is the gate.
- Re-chunking when only `split_content` changes. If a subclass swaps
  in a tree-sitter chunker, the dev re-runs `chunk()` themselves.
  Auto-chunk does not detect chunker code changes.
- A "rebuild all indexes" maintenance command. That is its own story.
- Schema provisioning for the trigram store. Story 013 phase 2.

## Data Flow

The pipeline is **compute-first, persist-once**. Auto-chunk and
auto-index both run before any database mutation. The persist phase
is a single batch of `DELETE` + `INSERT` + `UPDATE` ending in one
`session.flush()`.

```text
write(entries) called
  │
  ▼
[Step 1-3: existing _write_impl validation, parent dirs, fetch existing]
  │   READ-ONLY against the database.
  │
  ▼
[Step 4: change detection (per entry)]
  │   For each file in batch:
  │     - new file? → changed = True
  │     - existing file? → changed = (incoming.content_hash != existing.content_hash)
  │   For each chunk in batch:
  │     - same comparison against existing chunk row
  │   Unchanged entries are dropped from the pipeline here — no
  │   downstream work, no UPDATE on the row, no updated_at refresh.
  │
  ▼
[Step 5: auto_chunk (in-memory, only if flag is on)]
  │   For each changed file in batch where index_content is True:
  │     - check: does the same batch already contain chunks for this file?
  │       → if yes: error this file, drop it from the pipeline
  │     - call entry.chunk() → list[VFSEntry]
  │       → file's index_content flips to False (model handles it)
  │       → returned chunks carry index_content = True by validator default
  │     - append the chunks to the in-memory write batch
  │   No DB mutation yet. Cascade DELETE for re-chunked files is
  │   staged for step 7, not issued here.
  │
  ▼
[Step 6: auto_index (in-memory + provider call, only if flag is on)]
  │   For every entry with index_content = True and changed content:
  │     a. Extract old/new trigrams (pure CPU).
  │     b. Stage trigram delta rows:
  │          - add rows for grams newly present
  │          - delete rows for grams no longer present
  │        (queued in the unit of work, not yet INSERTed).
  │     c. Collect entries needing embeddings (excluding any with
  │        caller-provided embedding).
  │     d. ONE await provider.embed_entries(list) call.
  │     e. Assign returned vectors to entry.embedding in memory.
  │   Any failure here aborts before any DB mutation has happened.
  │
  ▼
[Step 7: single persist phase]
  │   In one batch, ending in one session.flush():
  │     - Stage delete trigram deltas before stale chunks/content
  │       disappear.
  │     - DELETE stale chunks for re-chunked files.
  │     - Clear stale embeddings for files whose index_content
  │       flipped to False.
  │     - Cut version rows (existing pipeline).
  │     - INSERT file rows + chunk rows + trigram staging rows.
  │       Vectors ride along on the entry's embedding column — no
  │       separate UPDATE to back-fill them.
  │     - UPDATE existing files whose content changed.
  │     - Commit any new parent-dir rows.
  │
  ▼
session.commit() (caller's / router's responsibility, unchanged)
```

## Worked Examples

### Example A — Bulk pipeline ingest, defaults on

```python
fs = PostgresFileSystem(engine=engine)  # auto_chunk=True, auto_index=True

await fs.write([
    VFSEntry(path="/repo/main.py", content="<8 KB Python source>"),
    VFSEntry(path="/repo/README.md", content="<short>"),
])
```

In-memory, before any DB write:

- `main.py` is large → `chunk()` returns ~4 chunk rows; file's
  `index_content` flips to `False`; chunks get `index_content =
  True`.
- `README.md` is short → `chunk()` returns `[]`; file's
  `index_content` stays `True`.
- Trigram add rows staged for the 4 chunks of `main.py` and the
  file row of `README.md`.
- One bulk `embed_entries` call returns 5 vectors in input order;
  each one assigned to its entry's `embedding`.

Then one persist flush:

- `INSERT` `main.py` (with `index_content = False`) + 4 chunks +
  `README.md` + their trigram staging rows. Vectors ride along on
  each row's `embedding` column.

Single transaction. Single embedding-provider call. One database
flush.

`result.to_str()` yields:

```text
write success: 2 files, 4 chunks written
```

The `candidates` list contains: the `main.py` file row
(status=`created`), 4 chunk rows (each status=`created`), and the
`README.md` file row (status=`created`). Multi-file batches show
counts only — the agent / caller can walk
`result.candidates` for path-level detail. No version rows
because both files are new.

### Example B — Re-write the same file with new content

```python
await fs.write([
    VFSEntry(path="/repo/main.py", content="<modified 8 KB source>"),
])
```

- Change detected (hash differs).
- In-memory: `main.py.chunk()` produces fresh chunks. Delete
  trigram delta rows are staged for the old chunks, and add trigram
  delta rows are staged for the new chunks. One `embed_entries` call
  returns vectors for them; vectors assigned to the in-memory chunks.
- Persist flush issues, in one round-trip:
    - stage delete trigram delta rows for old chunks before removing them.
    - `DELETE` old chunks under `/repo/main.py/__meta__/chunks/*`.
    - Version row for the previous content.
    - `INSERT` new chunks + their trigram staging rows + their embedding
      vectors as one batch.
    - `UPDATE` `main.py` with new content, hash, and
      `index_content = False`.

`result.to_str()` yields:

```text
write success: 1 file, 4 chunks written

  updated /repo/main.py
```

The deleted-then-recreated chunks appear as fresh `created`
candidates; the previous chunks aren't surfaced (they were
deleted, not "in the database"). A version row may be present in
`result.candidates`, but it is not counted in the human success
summary. Single-file batches include the path line below the
summary.

### Example C — Same content re-written

```python
await fs.write([
    VFSEntry(path="/repo/main.py", content="<unchanged content>"),
])
```

- Hash equal → no-op. No version row, no chunk cascade, no
  index work, **no `UPDATE` on the file row, no `updated_at`
  refresh**.
- Cost is one fetch and zero writes.
- `updated_at` continues to reflect the last *real* content
  change.

`result.to_str()` yields:

```text
write success: 1 file written

  unchanged /repo/main.py
```

The candidate has `status="unchanged"`; pre-existing chunks and
versions are not surfaced (they didn't change either), so the
summary doesn't mention them.

### Example D — Caller pre-builds chunks

```python
file = VFSEntry(path="/repo/main.py", content="<8 KB>")
chunks = file.chunk()              # mutates file.index_content = False
await fs.write([file, *chunks])
```

- Auto-chunk sees `file.index_content is False` → skips chunking.
- Auto-index processes the chunks (each has `index_content = True`).
- Same end state as Example A. Caller drove chunking; backend drove
  indexing.

### Example E — Caller pre-builds chunks but leaves the file flag set

```python
file = VFSEntry(path="/repo/main.py", content="<8 KB>", index_content=True)
chunks = [VFSEntry(path="/repo/main.py/__meta__/chunks/...", ...), ...]
await fs.write([file, *chunks])
```

- Auto-chunk's pre-check detects: `file.index_content is True` AND
  batch already contains chunks owned by this file → call returns
  `VFSResult(success=False, candidates=[], errors=[...])`. Neither
  the file nor the chunks persist.
- `result.to_str()` yields:
  ```text
  write errors:
    /repo/main.py: file + chunks both in batch with index_content=True
  ```
- Remediation: set `index_content=False` on the file, omit the
  pre-built chunks, or use a filesystem configured with
  `auto_chunk=False`, then resubmit the batch.

### Example F — Bulk import with deferred indexing

```python
fs = PostgresFileSystem(engine=engine, auto_chunk=False, auto_index=False)
await fs.write(large_batch)
# ... later, after all files loaded ...
await fs.rebuild_indexes()  # not in this story
```

- Pipeline ingests raw rows fast.
- Rebuild step is a follow-up story (see Out).

### Example G — Multi-mount partial commit

```python
client = VFSClient()
client.add_mount("workspace", PostgresFileSystem(engine=pg_engine))
client.add_mount("docs", MSSQLFileSystem(engine=mssql_engine))

await client.write([
    VFSEntry(path="/workspace/a.py", content=src_a),
    VFSEntry(path="/workspace/b.py", content=src_b),
    VFSEntry(path="/docs/notes.md", content=md_with_bad_embedding_dim),
])
```

- Router groups by mount: `[a.py, b.py]` → workspace,
  `[notes.md]` → docs.
- Workspace mount runs the full pipeline, persists cleanly.
- Docs mount's embedding-vector dimension doesn't match the
  `vfs_entries.embedding` column type → persist flush fails →
  docs mount returns `success=False, candidates=[], errors=[...]`.
- **Workspace's transaction is already committed.** vfs does not
  attempt to roll it back.
- The merged `VFSResult` has `success=False`, candidates from
  workspace, errors from docs.

`result.to_str()` yields:

```text
write errors:
  /docs/notes.md: pgvector dimension mismatch (mssql_docs)

write success: 2 files, 6 chunks written
```

Errors come first so a scanning agent sees the actionable items
before the success summary. The presence of both blocks in the
same result is the partial-commit signal. The caller is
responsible for deciding what to do — retry the failed mount
after fixing the embedding dim, surface to a human, or accept
the partial state.

## Acceptance Criteria

1. `DatabaseFileSystem.__init__` accepts `auto_chunk: bool = True`
   and `auto_index: bool = True` and stores them on the instance.

2. `write()` and `_write_impl()` accept `entries` as the first
   positional argument. `auto_chunk` and `auto_index` are constructor
   flags only and are not accepted by `write()`. Tests verify all three call shapes:
   `await fs.write([entry])`, `await fs.write(entries=[entry])`,
   and `await fs.write(path="/x", content="y")`.

3. With `auto_chunk=True` and a file having `index_content is True`
   and content larger than the chunker's threshold, `write()`
   produces both the file row (with `index_content = False`) and the
   chunk rows in a single transaction.

4. Files whose content fits in one chunk keep `index_content = True`
   and produce no chunk rows.

5. Re-writing a file with new content cascades: existing chunk
   rows under `/path/__meta__/chunks/` are `DELETE`d in the same
   persist flush as the new chunks' `INSERT` and the file's
   `UPDATE`. Atomic with the file update.

6. Re-writing a file with unchanged content (same `content_hash`)
   is a no-op: zero chunk-cascade work, zero index work,
   *and zero `UPDATE` on the row itself*. The `updated_at` column
   is not refreshed. A test asserts that `existing.updated_at`
   before and after such a write is byte-identical.

7. A write batch that contains both a file with `index_content is
   True` and pre-built chunks for the same file returns
   `VFSResult(success=False, candidates=[], errors=[...])` with
   the offending file path named in the error. No entry from the
   batch persists. A test asserts that after such a rejection the
   database is byte-identical to its pre-call state.

8. **Result shape — candidates are facts, errors are
   explanations.** `Candidate` has a new `status: Literal["created",
   "updated", "unchanged"] | None` field. `VFSResult.success` is
   `not errors`. On success, `candidates` contains every row the
   persist phase touched (file rows, newly-created chunk rows,
   newly-cut version rows, plus any unchanged file rows); on
   failure, `candidates` is empty and the error message in
   `errors` carries the path(s) and reason. There is no
   `rejected` status — entries that didn't write don't appear in
   `candidates`.

9. **`VFSResult.__str__` delegates to `to_str()`.** The write-mode
   formatter never uses the word "candidates" in its output and
   emits up to two blocks:
   - `write errors:` (when `errors` is non-empty), one line per
     error formatted `<path>: <reason>`. Rendered first.
   - `write success: <kind counts>` (when displayable write
     candidates are non-empty), aggregated from files, chunks, and
     edges only. Version candidates are not displayed in the success
     summary. For a single-file batch a status-verb path line appears
     below the summary; multi-file batches show counts only.
   - Empty result renders `write: nothing to do`.

   Tests assert: `str(result) == result.to_str()`; the four
   shapes (empty, success-only single, success-only multi,
   errors-only) match expected templates; in mixed results the
   errors block precedes the success block.

10. The embedding provider is invoked **at most once** per
    `write()` call, with the full list of entries needing
    embeddings handed in as one bulk request. The base class
    never iterates entries against the provider. A test asserts
    the call count is `<= 1` even when 50 entries need embeddings
    in the same write.

11. With `auto_index=True`, trigrams and embeddings are refreshed
    only for entries whose content changed. Caller-provided
    embeddings (tracked via `_explicit_fields`) are not
    overwritten and are excluded from the bulk embedding call.

12. When `auto_chunk` flips a file from `index_content = True` to
    `False`, `auto_index` stages delete deltas for the file's old
    trigrams and clears its embedding in the same transaction
    (`_apply_index_maintenance(..., delete_only=True)`).

13. **Auto-index runs before any database write.** When `auto_index
    = True`, the trigram extraction, delta-row staging, and bulk
    `embed_entries` call all complete before the persist phase
    issues any `INSERT`, `UPDATE`, or `DELETE`. A test asserts that
    a provider failure (raised from `embed_entries`) leaves the
    database byte-identical to its pre-write state — no partial
    file rows, chunk rows, or trigram staging rows.

14. **Index state is persisted in the same flush as its row.**
    After a successful `write()` with `auto_index = True`:
    - the row-store MVP has applied the expected add/delete gram
      deltas, or the posting-list adapter's staging table contains
      the expected `action="add"` and `action="delete"` rows.
    - `vfs_entries.embedding` is non-NULL on the same `INSERT` (or
      `UPDATE`) that wrote the row's content — there is never a
      window where the row exists with a NULL embedding.
    - stale trigram facts for re-chunked or flipped entries are
      represented as delete deltas before the old content disappears.
    A test reads these tables in the same transaction and asserts
    the expected row counts and vector presence.

15. **Deletes stage delete deltas before content disappears.** When
    `_delete_impl` deletes an `index_content=True` row, or a file
    whose children include indexable chunks, the backend recalculates
    current trigrams before soft/permanent deletion and stages one
    `action="delete"` row per current gram. A test asserts that grep
    no longer returns the deleted file/chunk before compressed
    posting-list compaction runs.

16. **Posting-list flush threshold.** When inserting staging rows
    causes pending staging rows to exceed `5_000_000`, the backend
    requests a compressed posting-list flush. The write itself remains
    correct even if compression runs after the user transaction
    because grep reads compressed postings plus staged adds minus
    staged deletes. If multiple pending rows exist for the same
    `(gram_kind, gram_key, entry_id)`, grep and flush use the latest
    staged action as the current truth.

17. Persist-flush failure rolls back the whole write transaction
    and returns `VFSResult(success=False, candidates=[],
    errors=[...])`. No file row, chunk row, or trigram staging row
    from this write persists. Computed vectors are discarded.

18. The default `_stage_chunk_cascade` and `_apply_index_maintenance`
    on the base class are no-ops; the in-memory backend continues
    to work without any trigram or embedding store.

19. PostgresFileSystem implements both hooks against the row-store
    trigram contract from story 013 phase 2 and the existing vector
    column. Integration test confirms grep-via-trigrams works
    end-to-end after a single `write()` (no separate maintenance
    call).

20. The `EmbeddingProvider.embed_entries` Protocol is documented and
    a reference test double is provided that proves input-order
    preservation under sub-batching.

21. Documentation on `DatabaseFileSystem` and `VFSEntry.index_content`
    states the new auto-maintenance contract: "after `write()`
    succeeds with `auto_chunk=True, auto_index=True`, the database
    is queryable without follow-up maintenance."

22. Existing tests pass unchanged with the new defaults turned on.
    No public behavior regression for callers that don't touch the
    new flags.

23. **Multi-mount partial commit is surfaced honestly.** When
    `VFSClient.write()` spans multiple mounts and at least one
    mount fails while at least one mount succeeds, the merged
    `VFSResult` has `success=False`, non-empty `candidates` from
    the successful mounts, and non-empty `errors` from the failed
    mount(s). `to_str()` emits the `write errors:` block first,
    then the `write success:` block — the presence of both blocks
    in the same output is the partial-commit signal. A test
    fixture using two mounts (one configured to fail on persist)
    asserts:
    - successful-mount candidates are present and reflect the
      committed DB state,
    - failed-mount entries are absent from `candidates`,
    - failed-mount errors are present in `errors`,
    - `to_str()` output contains both blocks in the
      errors-then-success order.

24. **Per-mount atomicity is preserved.** A single mount either
    commits its full slice of the batch or rolls it back; no
    half-committed mount is observable. A test induces a persist
    flush failure on a mount and asserts the database state on
    that mount is byte-identical to its pre-call state.

## Risks

- **Write latency.** Inline indexing makes `write()` proportional
  to chunk count and embedding-provider latency. Mitigation: construct
  bulk-load filesystems with `auto_index=False` and run deferred
  maintenance afterward.

- **Embedding provider as a transaction participant.** A slow or
  flaky provider blocks the transaction. Mitigation: the bulk
  contract collapses N round-trips into 1, providers must be
  configured with timeouts, bulk pipelines should use a filesystem
  configured with `auto_index=False`, and a future story can introduce
  deferred indexing.

- **No cross-mount atomicity.** A multi-mount batch where one
  mount succeeds and another fails leaves the successful mount
  committed and the failed mount untouched — `success=False` AND
  non-empty `candidates`. There is no automatic rollback because
  vfs does not implement two-phase commit across heterogeneous
  backends. Mitigation: `to_str()` emits both a `write errors:`
  block and a `write success:` block in that order, so partial
  commits are visually unmistakable; callers that need
  cross-mount atomicity must split their writes per mount and
  handle reconciliation themselves.

- **Bulk-call ordering bugs.** A provider that returns vectors
  out of input order would silently mis-assign embeddings to
  entries. Mitigation: the Protocol contract is explicit about
  input-order preservation; AC 20 requires a test double that
  proves it under sub-batching; integration tests assert the
  embedding-to-entry mapping matches expectation.

- **Re-chunk cascade footprint.** A file with thousands of chunks
  generates a large `DELETE` on every content change. Mitigation:
  the path-prefix delete uses the existing `path` index;
  benchmark in 013 phase 6.

- **Delete-delta volume.** Deleting or replacing a large indexed
  file may stage thousands of `action="delete"` trigram rows because
  the backend recalculates the current trigrams before content
  disappears. Mitigation: dedupe grams per row, bulk insert staging
  rows, trigger compressed posting-list flushes after `5_000_000`
  pending rows, and keep grep correct by subtracting staged deletes
  until compaction applies them.

- **Conflict-rule false positives.** A pipeline that legitimately
  wants to ship file + pre-built chunks together will hit the
  conflict error until they set `index_content=False` on the file,
  omit the pre-built chunks, or use a filesystem configured with
  `auto_chunk=False`. Mitigation: error message names the
  remediations; documented in the spec.

- **Order coupling with version rows.** Versioning runs *before*
  chunking in the existing `_write_impl`. A future change to
  versioning that mutates `content` in place would silently break
  chunk freshness. Mitigation: change detection uses the
  *post-versioning* content hash, and the cascade runs after
  versioning.

- **Caller-provided embeddings interacting with chunked files.** If
  a caller sets `embedding` on a file row that auto-chunk then flips
  to `index_content = False`, the embedding is preserved on the file row
  but the chunk rows compute their own. Documented as expected
  behavior, not a bug.

## Open Questions

1. Should `auto_chunk=True` apply to `kind == "chunk"` writes whose
   content exceeds the chunker threshold (sub-chunking)? Default:
   no. Chunks are leaf rows; sub-chunking is out of scope.

2. Should change detection compare full content rather than hash to
   handle hash collisions? Default: no. SHA-256 collisions are not
   in the threat model.

3. Should the conflict rule (file + its chunks in the same batch)
   degrade to a warning when the filesystem is configured with
   `auto_chunk=False`? Default: no. If `auto_chunk=False`, the
   conflict does not apply at all because no auto-chunking happens.

4. Should `_apply_index_maintenance` get a `kind`-aware dispatch
   (e.g. trigrams for code chunks, embeddings for prose) instead of
   running both for every indexable entry? Default: not in this
   story. The 013 trigram path and the vector path both no-op
   gracefully on empty inputs.

5. Should `mkdir` / `mkedge` / `copy` / `move` expose auto-maintenance
   controls? Default: no. Those paths don't write content; they delegate to
   `_write_impl` only for structural rows that are not eligible for chunking or
   indexing.

## References

- Story 013 — chunking surface, code-gram tokenizer, plan.md phase 2
- `src/vfs/models.py:521` — `VFSEntry.chunk()` implementation
- `src/vfs/models.py:663` — `index_content` derivation in the
  validator
- `src/vfs/backends/database.py:1264` — `_write_impl` (the integration
  point for the new pipeline steps)
- `src/vfs/backends/database.py:1050` — `_update_existing` (where
  versioning currently happens; auto_chunk runs after this)
