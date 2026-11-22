# Parameter pattern replacement honors nocasematch

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Shell parameter replacements follow the active case-matching option.

## The problem

The replacement path constructs default match options while other pattern consumers consult shell state.

## Proposed changes

Use the shell’s matching options when compiling and applying the replacement pattern.

## Acceptance tests

Compare replacements across mixed-case text with the option enabled and disabled. Include a literal replacement and a wildcard pattern.

## Builds on

[machine/expand.rs L1436](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/expand.rs#L1436)
