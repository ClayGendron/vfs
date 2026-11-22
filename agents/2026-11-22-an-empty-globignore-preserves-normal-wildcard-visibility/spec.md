# An empty GLOBIGNORE preserves normal wildcard visibility

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Assigning an empty ignore list in a fresh shell leaves ordinary wildcard selection consistent with Bash.

## The problem

Wildcard handling treats the presence of an empty GLOBIGNORE as sufficient to include hidden paths.

## Proposed changes

Distinguish explicit dotglob state from the option transitions associated with a nonempty ignore list.

## Acceptance tests

Compare matched names in a fixture with visible and hidden entries for unset, empty, nonempty and cleared values and an explicit dotglob choice.

## Builds on

[machine/expand.rs L1854](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/expand.rs#L1854)
