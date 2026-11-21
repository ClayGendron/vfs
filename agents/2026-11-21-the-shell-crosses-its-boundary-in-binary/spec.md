# The shell's module crosses its boundary in binary

A draft, written on 2026-11-21 from finding M4 of `agents/2026-11-21-the-shell-speaks-bash/reviews/step-3-7-code-review.md`. It is not reviewed, and nothing is built.

## The outcome wanted

A byte that crosses between the machine's module and its host costs a few instructions, not hundreds, so the default fuel bounds the work a line does and not the bytes it moves.

## Builds on

The wire of `crates/vfs-shell-wasm/src/wire.rs`: JSON text, every byte string in base64, parsed inside the module.

## The problem

Measured before the decoder fix of 2026-11-21: `cat` of 1 MB spent about 0.7 billion instructions and `grep -c` about 1.5 billion, so a line read about 28 MB under the default fuel of 20 billion. `progress.md` restates the figures after the decoder's reverse table.

## Decisions

1. Byte strings cross as raw bytes in the module's memory, beside a small header that names each one's offset and length; the JSON keeps the structure only.
2. Both hosts (the binding and the test runtime) read the same layout through one codec in the crate.

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
