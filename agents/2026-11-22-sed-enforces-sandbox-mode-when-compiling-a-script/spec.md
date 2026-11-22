# sed enforces sandbox mode when compiling a script

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

Sandbox mode rejects script-directed file access before asking the VFS to perform it.

## The problem

The bundled help promises that sandbox mode disables script file access. Option parsing discards the flag. The compiler can still accept script reads and writes, which the adapter performs with the caller’s rights. Applications accepting someone else’s sed script under that flag give the script more access than intended.

## Proposed changes

Carry the sandbox setting into compilation of inline and file-loaded scripts. Validate all restricted instructions before discovering auxiliary files or applying writes.

## Acceptance tests

Use a recording host with ordinary input and output paths. A restricted script returns a diagnostic and issues zero auxiliary file requests. A pure substitution still succeeds.

## Builds on

[programs/sed.rs L74](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/sed.rs#L74) · [programs/sed.rs L313](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/sed.rs#L313) · [programs/sed.rs L605](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/sed.rs#L605) · [programs/mod.rs L304](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/mod.rs#L304)
