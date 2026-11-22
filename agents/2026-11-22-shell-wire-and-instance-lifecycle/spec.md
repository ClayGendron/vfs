# Shell wire messages are exact and instance transitions are explicit

Draft implementation contract from the November 22, 2026 review of `cbda2721`.

## The outcome wanted

The bundled Python runtime and third-party Wasm hosts agree on Unicode, integers, mutation schemas and the identity of the active line after any protocol error.

## Builds on

Own crates/vfs-shell-wasm/src/{wire,lib}.rs and the checked buffer transfer in crates/vfs-core/src/shell_binding.rs. Both the existing JSON format and a future binary carrier must meet these semantics. The separate binary-transport spec is active and is not a prerequisite. Build decoder changes before the extended read/list/stat, guarded-write and timer schemas used by the other specs.

This work can start against the reviewed implementation.

## The problem

- The JSON reader converts escaped UTF-16 code units independently. External encoders that escape supplementary characters can change source, names or paths.
- JSON numbers are converted through a floating-point representation before integer fields are recovered, which rounds large exact values.
- A failed second start leaves the previous instance active. The Python product uses a fresh instance for each line.

## Decisions

### 1. For JSON strings combine an escaped high/low UTF-16 surrogate pair into a single scalar.

Reject lone, reversed or truncated halves as malformed before constructing a request, as well as invalid UTF-8 from the guest buffer. Raw UTF-8 and equivalent valid escaped strings produce identical paths, variables and source. Retain exact integer tokens until the destination field is known, then parse with signedness/range checks for its declared width; reject decimal or exponent spellings in integer-only fields, negatives for unsigned fields and overflow. Keep ordinary fractional fields on their documented path.

### 2. A mutation decoder is fallible for its tag, required fields, field types and enum variants.

A missing or malformed body is invalid; explicitly encoded zero-length data is valid. Reject malformed base64 and duplicate recognized fields. Unknown write modes never fall back to truncate. Reject the whole step document before dispatching any request if any entry is invalid. Bundled host discards the faulty instance, returns internal/1 and dispatches nothing from that document. Extensions may add optional unknown fields; ignore them unless a required feature/version is missing. These rules keep valid existing documents usable.

### 3. Add an optional top-level features list to the start request and repeat negotiated names in the successful start reply.

Absent means legacy behavior. Enable bounded-io-v1 only on explicit mutual acknowledgment. It covers reader open/next/close, paged list, optional stat projections and guarded writes; builtin timeouts require timer-v1. Bundled host and module negotiate both; a missing acknowledgment in the bundled pair returns a classified unsupported startup failure and zero effects. External legacy pairs retain the previous request repertoire and existing defaults. Do not send enhanced operations to a host that has not opted in. If an unnegotiated feature is essential for a newly requested operation, return an explicit unsupported command error before any mutation.

### 4. start on an active instance is rejected immediately with a protocol error and leaves its running line and identity intact.

It does not validate or install a replacement. Terminal step consumes the active machine; malformed first start leaves an idle instance idle. A terminal or idle instance can start a new valid line. A step on idle or after termination returns the existing no-active-line error. cancel is idempotent; active cancellation becomes terminal on the next step, and idle cancellation has no effect. Document that an active-start rejection leaves the old line available only through an explicit subsequent step. The bundled Python API still instantiates a fresh guest per line.

### 5. Validate guest output address and length with checked arithmetic against the same current linear-memory view and remaining native wire allowance before allocating or copying on the host.

Accept a zero-length range at the exact memory end; reject addition overflow or a nonempty range beyond the end. A malformed pointer is an internal protocol failure, while a valid range above the configured host allowance is a budget failure. Decode only after validating the entire range. Hold the instance/step guard during validation and copy so that another call cannot relocate the buffer. Never use an unchecked pointer or trust a host-side allocation size supplied only by the guest.

## Acceptance criteria

1. Round-trip raw and escaped supplementary scalars in start source, paths and replies, exact integers around 2^53, maximum u64 and signed bounds. Check malformed encodings, oversized numbers and wrong field types. Submit an empty write, a malformed write, and a mixed valid/invalid batch. Inspect the dispatched operations, returned error and state after each.
2. Exercise Idle → Running → Terminal → new start, rejected restart, failed initial start, duplicate cancel and step after termination with a native wire client and the compiled module. Use a test adapter for invalid ranges and allocation counters. Exercise mutual, one-sided and absent negotiation. Compare logical request results across the native and Wasm hosts and update wire roundtrip and module law tests.

## Regression cases

| Behavior | Check through the normal entry point | Reviewed source |
|---|---|---|
| The shell wire decoder preserves supplementary Unicode | Round-trip a supplementary character as raw and escaped JSON in source and paths using a standard encoder. Check rejection of unpaired surrogate values. | [crates/vfs-shell-wasm/src/wire.rs L864](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell-wasm/src/wire.rs#L864) |
| The shell wire protocol preserves exact integer fields | Round-trip adjacent large u64 values and field boundaries with standard JSON. Check out-of-range and fractional inputs for integer fields. | [crates/vfs-shell-wasm/src/wire.rs L822](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell-wasm/src/wire.rs#L822) |
| A failed Wasm restart has a single defined lifecycle outcome | Exercise first start, repeated start, failed replacement, subsequent step and cancellation. Assert the externally visible state and which line can produce output after each transition. | [crates/vfs-shell-wasm/src/lib.rs L57](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell-wasm/src/lib.rs#L57) |
| The native binding validates guest output ranges before allocating | At the decoder boundary inject a valid small range, an out-of-bounds range and an invalid length. Check error classification and that host allocation follows validation. | [crates/vfs-core/src/shell_binding.rs L510](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-core/src/shell_binding.rs#L510) |
| Malformed shell mutation records are refused during decoding | Give the decoder malformed records and a valid empty write. Assert that only the valid record reaches the recording host. | [crates/vfs-shell-wasm/src/wire.rs L569](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell-wasm/src/wire.rs#L569) |

## Verification

Use the pinned recorder and its environment in [the shell corpus](../../tests/shell/README.md) for observable Bash/GNU behavior. Run the affected crate laws and the release corpus with `cargo test --release -p vfs-shell -p vfs-shell-wasm`. Exercise public-host behavior with `uv run pytest tests/shell` and the PostgreSQL-marked engine cases when a storage contract changes. Record intentional VFS deviations alongside the corpus fixtures. A case moves out of the known-failure list only when its recorded assertions pass.
