# The Python shell exposes an effective slice setting

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Every accepted scheduling option has observable and documented behavior in the shipped Wasm runtime.

## The problem

The Wasm fuel probe replaces the operation-count scheduling threshold. Changing only slice does not adjust yield cadence.

## Proposed changes

Reconcile operation-count and fuel-based yield thresholds. Either honor both where accepted or reject the inactive option explicitly and document the effective control.

## Acceptance tests

Run a finite command under distinguishable thresholds with a counted yield probe. Verify that each accepted setting affects cadence as documented and preserves the command result.

## Builds on

[src/vfs/shell/host.py L57](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L57) · [crates/vfs-shell-wasm/src/lib.rs L63](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell-wasm/src/lib.rs#L63) · [machine/io.rs L218](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/io.rs#L218)

See also [A line has a verb budget, a host sets the shell's budgets, and a cli call may only tighten them](../2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md).
