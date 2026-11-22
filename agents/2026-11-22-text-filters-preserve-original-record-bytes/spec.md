# Text filters preserve original record bytes

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

Distinct byte records survive sorting, deduplication and translation unless the requested operation changes them.

## The problem

Several filters decode input with replacement before comparing or emitting it. Byte-distinct records can become indistinguishable inside a pipeline.

## Proposed changes

Retain raw record bytes. Use separate derived comparison keys where required by the option and locale. Preserve the documented decoding of the final display.

## Acceptance tests

Read redirected output as bytes. Check distinct invalid byte sequences, normal UTF-8 and an unchanged byte passing through tr against the reference tools.

## Builds on

[programs/text.rs L1160](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/text.rs#L1160) · [programs/text.rs L1346](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/text.rs#L1346) · [tr record conversion](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/text.rs#L1613)
