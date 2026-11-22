# The pipeline stage allowance covers the final stage

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Every pipeline stage, including a standalone command, counts toward the configured stage limit.

## The problem

The parser checks when it sees another pipe. The final stage can be appended without that check, so a zero limit admits one command.

## Proposed changes

Check the allowance when adding every stage and retain the existing default.

## Acceptance tests

Cover zero, one and two permitted stages. A rejected line performs no host effects.

## Builds on

[syntax/parser.rs L563](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/syntax/parser.rs#L563)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
