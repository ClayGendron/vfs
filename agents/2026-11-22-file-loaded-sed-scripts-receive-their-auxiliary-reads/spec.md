# File-loaded sed scripts receive their auxiliary reads

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

An auxiliary read from a file-loaded script sees the same VFS data as the equivalent inline script.

## The problem

The adapter discovers needed files before loading scripts. The engine can treat a missing preloaded entry as empty and report success.

## Proposed changes

Compile authorized script sources before discovering auxiliary reads, or request reads at execution time. Apply sandbox policy before auxiliary dispatch.

## Acceptance tests

Compare inline, file-loaded and mixed scripts against the same small auxiliary file. Check output, status and the authority on each read.

## Builds on

[programs/sed.rs L128](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/sed.rs#L128) · [programs/mod.rs L304](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/mod.rs#L304) · [programs/sed.rs L1754](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/sed.rs#L1754)
