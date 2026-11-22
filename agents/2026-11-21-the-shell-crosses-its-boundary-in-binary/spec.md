# The shell's module crosses its boundary in binary

A draft, written on 2026-11-21 from finding M4 of `agents/2026-11-21-the-shell-speaks-bash/reviews/step-3-7-code-review.md`. It is not reviewed, and nothing is built.

Ruled on 2026-11-22: this lands before `0.1.0b1`, when the public surface is frozen, not in the `0.1.0` gate after it.

## The outcome wanted

A byte that crosses between the machine's module and its host costs a few instructions, not hundreds, so the default fuel bounds the work a line does and not the bytes it moves. And the module is compiled when the wheel is built, not at a process's first line.

## Builds on

The wire of `crates/vfs-shell-wasm/src/wire.rs`: JSON text, every byte string in base64, parsed inside the module.

## The problem

Measured before the decoder fix of 2026-11-21: `cat` of 1 MB spent about 0.7 billion instructions and `grep -c` about 1.5 billion, so a line read about 28 MB under the default fuel of 20 billion. `progress.md` restates the figures after the decoder's reverse table.

- The first line in each process compiles the module: about 260 ms and 180 MB of peak memory, measured by the second structural review.
- The Rust toolchain is not pinned, so the module, and the instructions a line spends, differ between wheel builds; a line that starts with very little fuel ran out while the instance was made on one build and not on another.

## Decisions

1. Byte strings cross as raw bytes in the module's memory, beside a small header that names each one's offset and length; the JSON keeps the structure only.
2. Both hosts (the binding and the test runtime) read the same layout through one codec in the crate.
3. The build script precompiles the module for the wheel's target, and the binding deserializes it at first use; the deserialize call is the binding's one unsafe call, and it stays out of the shell's crates.
4. The toolchain the wheel builds with is pinned, so a wheel's fuel counts are a function of its version.

## Tests

A law counts the instructions a 1 MB `cat` spends and holds it under a declared bound; the wire roundtrip test holds every request and reply in the new layout.

## Scope

The wire, the module's exports and the binding.

## Not checked

How much of the remaining cost is JSON parsing rather than the bytes.

## Choices to confirm

None.

## One line

Moving a byte across the module's boundary costs almost nothing.
