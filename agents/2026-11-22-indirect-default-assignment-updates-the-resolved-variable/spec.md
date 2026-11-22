# Indirect default assignment updates the resolved variable

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Assigning a default through an indirect parameter changes the target while preserving the referring variable.

## The problem

The lookup resolves the referenced name but the subsequent assignment uses the original parameter.

## Proposed changes

Carry the resolved assignment target between lookup and mutation, following usual readonly and variable checks.

## Acceptance tests

Use a referring variable naming an unset target and then a set target. Compare both variables and expansion output with Bash.

## Builds on

[machine/expand.rs L1013](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/expand.rs#L1013)
