# sed preserves bytes during an in-place edit

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

A successful identity edit leaves the file byte-for-byte identical.

## The problem

Sed performs lossy text conversion while splitting input records. In-place output persists the converted bytes even if the script makes no substitution.

## Proposed changes

Preserve original bytes in sed’s records and output. If an operation requires an unsupported encoding, fail before scheduling the source replacement.

## Acceptance tests

Compare checksums of a mixed text and non-UTF-8 fixture before and after an identity edit. Check stream output at the byte boundary before display decoding.

## Builds on

[programs/sed.rs L2171](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/sed.rs#L2171) · [programs/sed.rs L1338](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/sed.rs#L1338) · [src/vfs/shell/host.py L383](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L383)
