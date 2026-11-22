# Read timeout options preserve stream position

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A zero-time read checks readiness without consuming data and a positive timeout bounds the wait.

## The problem

The read builtin accepts the option’s value but can consume input even for a readiness check. A positive duration is discarded.

## Proposed changes

Implement non-consuming readiness and a deadline-aware wait for supported sources. Report unsupported timing explicitly on a source that cannot supply it.

## Acceptance tests

Verify the following read still returns the first record after a zero-time probe. With a controlled clock, check pending and ready sources under a positive duration.

## Builds on

[machine/builtins.rs L726](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L726)
