# Read preserves literal Unicode during field splitting

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Input containing a private-use character and an escaped field separator round-trips through read.

## The problem

Escaped field separators are temporarily represented by Unicode characters that can also be present in legitimate input.

## Proposed changes

Track quoted or escaped positions independently from character values and traverse them in order.

## Acceptance tests

Compare the assigned fields with Bash for a literal private-use character next to an escaped separator. Check both ordinary and raw input modes.

## Builds on

[field splitting](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L880)
