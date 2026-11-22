# Lastpipe releases a finished consumer’s descriptor

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A final pipeline stage that stops reading promptly releases the descriptor owned by the parent shell.

## The problem

When lastpipe is active the parent retains the read end until both stages finish. The upstream producer can keep waiting after the consumer exits.

## Proposed changes

Restore the parent’s descriptor when the final stage completes and propagate the normal producer close/broken-pipe result.

## Acceptance tests

Use a finite producer and a short-reading final stage. Check completion, pipeline statuses and restoration of the parent’s previous input.

## Builds on

[machine/exec.rs L497](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L497) · [machine/mod.rs L464](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/mod.rs#L464)
