# Copy and move honor interactive and update options

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

Copy and move account for confirmation and update options before dispatching a transfer.

## The problem

The shared option parser accepts interactive and update switches without recording either choice. The reference host permits replacements that production storage refuses.

## Proposed changes

Recognize these switches explicitly. Where the backend cannot honor a requested form, return a diagnostic before dispatch. Preserve the production occupied-target policy.

## Acceptance tests

Cover a declined transfer, EOF and an older source under the update option. Inspect the original destination and the transfer request log.

## Builds on

[programs/files.rs L505](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/files.rs#L505) · [occupied destination policy](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/storage/backends/database/topology.py#L188)
