# Shell wire messages decode exactly or not at all

Draft implementation contract from the November 22, 2026 review of `cbda2721`. Verified against `dev` at `5a823ea` and amended on 2026-11-22 (`agents/2026-11-22-shell-review/reviews/verification.md`): the shell is no platform for third-party hosts, and the module and its host ship together in one wheel, so the draft's feature negotiation, legacy pairs, restart rules for a reused instance and the `bounded-io-v1`, `timer-v1` and `writer-v1` operations are withdrawn. What remains is the decoder's exactness, which the binary carrier of `agents/2026-11-21-the-shell-crosses-its-boundary-in-binary/` must keep too.

## The outcome wanted

Every value that crosses between the Python host and the module arrives as it was sent, or the step is refused before any request in it runs.

## Builds on

`crates/vfs-shell-wasm/src/wire.rs` and its callers in `crates/vfs-shell-wasm/src/lib.rs` and `crates/vfs-core/src/shell_binding.rs`. When the binary carrier lands it replaces the JSON, and these rules move to it unchanged.

This work can start against the reviewed implementation.

## The problem

- **Integers pass through `f64`.** The guest reads a JSON number as a float before it recovers an integer field. `9007199254740993` decodes as `9007199254740992`, `1.5` as 1, `-5` as 0 and `1e3` as 1000. This is reachable: `run_line(limits=...)` admits values to 2^64 and they cross `encode_start` into the guest (run on 2026-11-22).
- **A malformed mutation record decodes leniently.** A write with no data is an empty truncate, an unknown mode is a truncate, bad base64 characters are skipped, a duplicate key keeps its first value, and `recursive: "yes"` is false. Only an unknown operation fails the step (run).
- **Escaped UTF-16 halves decode one at a time.** `"😀"` becomes two U+FFFD, and a lone or reversed half is accepted (run). The bundled encoder writes non-control characters raw and Python writes no JSON, so the product does not reach this today; a reader that accepts every valid JSON spelling costs a few lines.

What was found already right: a step on an idle instance answers "no line has started", a terminal step clears the machine, a failed first start leaves the instance idle, cancel is idempotent, and a step document that fails to decode drops the instance and ends the line `internal` with nothing dispatched. The binding holds the instance's mutex for the whole call, and its `memory.read` is bounds-checked by wasmtime.

## Decisions

1. **Integer fields are parsed from their lexeme.** The decoder keeps a number's text until it knows the field, then parses it with the field's width and sign. A fraction, an exponent, a negative value in an unsigned field and an overflow are malformed. Fractional fields keep their path.
2. **A mutation record decodes or the step fails.** The tag, every required field, its type and its enum value are checked. A missing body is malformed; an explicit empty one is valid. Malformed base64, a duplicate recognized key and an unknown write mode are malformed; a write mode never falls back to truncate. One malformed record fails the whole step document before any request in it is dispatched, as an unknown operation does today: the instance is dropped and the line ends `internal`, status 1.
3. **An escaped surrogate pair is one scalar.** A high half followed by a low half combines; a lone, reversed or truncated half is malformed, as is invalid UTF-8 from the guest's buffer.
4. **The output range is checked before the host allocates.** The binding checks the guest's pointer and length with checked arithmetic against the current memory size and the line's remaining wire allowance before it allocates the copy. A range past memory is `internal`; a valid range past the allowance is `budget_exhausted`.

## Tests

- In `crates/vfs-shell-wasm/tests/wire_roundtrip.rs`, the regression `integer_and_mutation_fields_decode_exactly_or_fail_the_step`:
  - integers at 2^53 ± 1, `u64::MAX` and the signed bounds round-trip;
  - `1.5`, `-5`, `1e3` and an overflow in an integer field are refused;
  - an empty write, a write with no data, an unknown mode, bad base64 and a duplicate key are checked one by one, and a mixed valid and invalid batch dispatches nothing;
  - a raw and an escaped supplementary character decode alike, and a lone half is refused.
- In `crates/vfs-core`, a test adapter gives the binding an out-of-range and an over-budget output range and checks the classification, with no allocation before the check.

## Verification

`cargo test --release -p vfs-shell -p vfs-shell-wasm`, then `uv run pytest tests/shell`. Update `documentation/reference/shell.md` where it describes the wire.

## One line

The wire decoder reads integers, mutations and escaped characters exactly, or refuses the step before anything runs.
