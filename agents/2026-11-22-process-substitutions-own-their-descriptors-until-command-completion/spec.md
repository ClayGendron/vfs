# Process substitutions own their descriptors until command completion

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Each active input substitution has a distinct descriptor, released with its capture storage after the consuming command ends.

## The problem

The descriptor search reuses an occupied slot and input descriptors can remain in shell state after the command exits.

## Proposed changes

Allocate genuinely free descriptors and close them on scope exit, including error paths. Charge captured bytes throughout their lifetime.

## Acceptance tests

Use several distinct short input substitutions and an occupied descriptor. Verify stream identity and that repeated commands return descriptor and byte counts to baseline.

## Builds on

[machine/exec.rs L1787](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1787) · [machine/exec.rs L1823](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1823) · [machine/exec.rs L1865](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1865)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
