# A zero-character read leaves file input untouched

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Reading zero characters preserves the position of every descriptor type.

## The problem

The file-backed input branch can fetch a byte before checking the zero count, unlike the buffer and pipe branches.

## Proposed changes

Handle zero before dispatching to descriptor-specific read logic.

## Acceptance tests

Run two consecutive reads on file, pipe and here-string inputs. Check the first result and that the second read starts at the original byte.

## Builds on

[machine/builtins.rs L582](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L582)
