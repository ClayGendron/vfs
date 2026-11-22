# Pattern exhaustion reaches every shell matcher caller

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

An exhausted match returns an explicit failure before negation, partial-capture selection or grep result classification.

## The problem

Shell glob depth exhaustion returns false, which a negated pattern can invert. Regex matching can select a partial best result before reporting exhaustion, and grep’s binary branch ignores the exhaustion flag.

## Proposed changes

Carry exhaustion through wildcard and regex evaluators, including negated groups, partial best matches and binary grep. Keep ordinary successful and unsuccessful matches distinct.

## Acceptance tests

Using a small injected matcher allowance, compare exhausted, completed-match and completed-miss outcomes across conditional, filename and grep callers. Verify that inversion preserves the error.

## Builds on

[machine/pattern.rs L330](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/pattern.rs#L330) · [machine/pattern.rs L501](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/pattern.rs#L501) · [machine/regex.rs L94](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/regex.rs#L94) · [programs/grep.rs L274](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/grep.rs#L274)

See also [The shell matches patterns and regular expressions in time linear in the text](../2026-11-21-the-shell-matches-in-linear-time/spec.md).
