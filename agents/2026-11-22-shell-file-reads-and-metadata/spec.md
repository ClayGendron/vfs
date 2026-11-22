# File reads and metadata remain bounded and caller-authorized

Draft implementation contract from the November 22, 2026 review of `cbda2721`.

## The outcome wanted

A fresh open sees current authority and version. A read in progress either yields bytes from its opened version or encounters an explicit error. Predicate results and partial listings reflect the caller’s view.

## Builds on

Own src/vfs/shell/host.py read/list/stat requests, the Rust Request/Reply model and corresponding codec changes, AsyncVirtualFileSystem routing and the storage-side read/projection paths. Coordinate wire shapes with “Wire and instance lifecycle”, and stream errors with “Redirections and pipelines”. This work adds governed read/stat projections, reuses the existing paged ls verb and adds a guarded-write request for sed. Include protocol adapters, MemoryHost, database storage, testing hosts and public documentation in the same landing.

Implementation prerequisites in this change (specified, pending implementation): [Shell wire messages are exact and instance transitions are explicit](../2026-11-22-shell-wire-and-instance-lifecycle/spec.md), [A shell line has one admission budget and one terminal outcome](../2026-11-22-shell-runtime-termination/spec.md).

## The problem

- The Python host fetches an entire file for one range and can retain it regardless of size. Listing constructs all child entries before encoding the reply.
- The per-line cache key is a path. A new offset-zero read can hit a completed read’s body without asking the router again. A concurrent edit or revocation is invisible on that reopen. Exposure is limited to data already obtained by the same authority in that line. Conversely, eviction can cause a later chunk to come from a newer version.
- Adding a body builds a list by scanning cached paths even when usage is far below the eviction threshold. The per-line byte tally counts payloads but omits keys and metadata, so empty files can accumulate entries without advancing it.

## Decisions

### 1. Give a logical open a line-scoped reader ID using its first RequestKey.

Add ReadOpen(path,length), ReadNext(reader,offset,length) and ReadClose(reader) controls. Replies carry the current data bytes, eof and an opaque stable identity on open. The initial chunk and identity derive from the same authorized read. Seekless continuation requires the next sequential byte offset; unknown, closed or mismatched reader returns Invalid. A duplicate fd shares the reader and cursor. Close releases the descriptor on last use and line teardown releases all remaining handles. Each independent open goes through the router, including offset zero at the same path. No cross-line cache.

### 2. Extend the public read verb with optional keyword-only offset, length and expected identity, on the single-path form.

Offset and length are nonnegative bounded integers; both are required for a range and existing whole-read semantics stay unchanged. A shell chunk is at most 64 KiB. Return data as bytes, including for stored text, with offset measured in canonical UTF-8 bytes. Use a new optional range metadata object carrying opaque identity, bytes returned and eof; for zero length, eof means offset at or beyond the end. The identity binds mounted storage instance, stable entry ID and version, so path reuse cannot join different objects. Compare expected identity and select the slice under the same rights-checked statement/transaction. Report a visible version mismatch as conflict; hide inaccessible paths under normal VFS masking. Recheck read access on every continuation. Old handles confer no continuing read right. A conflict/refusal is final for that reader.

### 3. On SQLite slice the canonical UTF-8 byte representation as a BLOB, and on PostgreSQL use bytea or UTF-8 conversion before byte slicing.

Project only the slice, identity and length/EOF metadata across the DB boundary; preserve grants, routing and mount column masks. A backend incapable of a bounded atomic range returns unsupported before fetching a whole body. Keep the old whole-read API available to ordinary callers and legacy wire clients. Replace the path body cache with per-reader metadata and at most one active chunk, keyed by ID with O(1) insert/close. Charge keys, retained bytes and entries to the host buffer allowance; evict optional cached data only. Count refused admission for a new reader rather than evicting a live identity. MemoryHost slices the stored bytes with the same scope and errors.

### 4. Page shell listings with the public cursor.

Extend the request with optional after and page_size; default 128 entries and use at most the current allowance. Pass through next_after and use that opaque cursor until absent, including short pages. Validate forward progress and abort on repeated cursor. Treat the traversal as the sequence of authorized pages under concurrent changes, consistent with public ls. Charge each live page/entry and require a command accumulating a directory to reserve its aggregate logical memory before keeping entries. Propagate classified warnings of successful partial read/stat/ls/search results through the existing deduplicating evidence collector. Ignore ordinary negative existence probes; preserve operational failures and their original masking.

### 5. Extend the authorized stat projection with optional can_read, can_write and modified_at.

A visible regular file’s read bit uses the same admission as body read, and write bit uses the existing-file overwrite admission, including write masks, mount read-only policy and ownership rules. For directories, read means permission to list and write means permission to create a child under that directory. Do not name an invented child for this probe. A bare mount/unknown capability yields false. Compute capabilities in the router/backend from existing operation checks in the caller’s snapshot; a later real mutation always checks again. If a field is unavailable return unknown and test it as false. Use UTC instants at microsecond precision for age comparisons. Equal existing times compare false; newer-than succeeds when only the left exists, older-than succeeds when only the right exists, both missing or unknown timestamps compare false where both exist. Test both conditional syntaxes.

### 6. Add GuardedWrite(path,expected_identity,bytes) for publishing a completed edit.

Route to a conditional write that checks both stable identity and version in the mutation transaction; extend the current if_version path where it lacks identity. A conflict leaves the target intact. Engines that cannot check the precondition atomically return unsupported. Use an opaque token: possession alone never authorizes access. Host reply shapes and stat fields are negotiated before use under the wire spec.

## Acceptance criteria

1. Across MemoryHost, SQLite and PostgreSQL open a file, read two chunks, replace its body between opens, revoke access between chunks and recreate its path. Assert router calls on every open, no mixed-version output and no stale bytes after revocation. Include binary and multibyte text split mid-character. Instrument SQL/result rows or a test adapter to verify that a tiny range never transfers the full body into Python.
2. Page a wide directory with tiny quotas, a partial warning and a short nonfinal page. Compare cursor order and warning evidence and count live host bytes including paths and entries. Test file/directory, list-only, read-only, writable, masked and synthetic mount paths for stat probes. Try a guarded write after delete/recreate with the same numeric version and verify the replacement survives.

## Regression cases

| Behavior | Check through the normal entry point | Reviewed source |
|---|---|---|
| The shell bounds storage replies while reading and listing | Use an instrumented storage with a multi-range file and a multi-page directory. Check sizes requested, maximum live bytes, ordering and continuity of the returned data. | [src/vfs/shell/host.py L375](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L375) |
| A fresh shell file open rechecks access and pins its contents | Use two logical opens across a version or permission change. Verify the second open follows current routing, and evict a reader midway to check for mixed-version output. | [src/vfs/shell/host.py L375](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L375) |
| The shell body cache bounds entry overhead and eviction work | Count entries visited as the number of small files doubles. Exercise entries with zero payload and verify eviction releases their overhead. | [src/vfs/shell/host.py L392](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L392) |
| The shell preserves warnings from partial VFS results | Return rows with a warning from a listing and search. Check output, deduplication and the warning record. Compare with an ordinary absent-file predicate. | [src/vfs/shell/host.py L408](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L408) |
| Shell access predicates reflect caller permissions | Run predicates with read-only, writable and masked paths on the same mount. Compare answers with the applicable VFS permission decisions without writing as a probe. | [machine/test.rs L78](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/test.rs#L78) |
| Shell file age comparisons use modification time | Check older, newer and equal timestamps and both missing-operand orders on each host. | [machine/test.rs L203](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/test.rs#L203) |

## Verification

Use the pinned recorder and its environment in [the shell corpus](../../tests/shell/README.md) for observable Bash/GNU behavior. Run the affected crate laws and the release corpus with `cargo test --release -p vfs-shell -p vfs-shell-wasm`. Exercise public-host behavior with `uv run pytest tests/shell` and the PostgreSQL-marked engine cases when a storage contract changes. Record intentional VFS deviations alongside the corpus fixtures. A case moves out of the known-failure list only when its recorded assertions pass.
