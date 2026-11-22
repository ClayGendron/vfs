# Case-insensitive regex ranges fold case consistently

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Case-insensitive bracket ranges and literals agree for equivalent characters across shell regex consumers.

## The problem

Scalar literals use case folding but bracket ranges compare raw scalar values. Grep, sed and shell regex conditions share this matcher.

## Proposed changes

Use case-aware range membership consistent with the supported locale and the matcher’s literal folding rules.

## Acceptance tests

Compare a simple alphabetic range on upper- and lowercase input in grep, sed and shell regex conditions. Repeat with case sensitivity enabled.

## Builds on

[machine/regex.rs L464](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/regex.rs#L464)

See also [The shell matches patterns and regular expressions in time linear in the text](../2026-11-21-the-shell-matches-in-linear-time/spec.md).
