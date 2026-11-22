# Unsetting a shell local respects localvar_unset

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

An unset binding in a caller scope remains hidden according to the active localvar_unset setting.

## The problem

The accepted shell option is not consulted when unsetting a local can expose an outer binding.

## Proposed changes

Carry the option into scope resolution and preserve the shadow state required until the owning scope exits.

## Acceptance tests

With nested functions and a global of the same name, compare lookup in both functions and after their return with the option on and off.

## Builds on

[machine/vars.rs L171](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/vars.rs#L171)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
