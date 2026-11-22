# Here-document parsing shares the line token allowance

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

The total token count for the parent parser and a nested here-document remains within the configured limit.

## The problem

A subparser counts tokens from zero. Its count is added back without a final limit check when parsing ends there.

## Proposed changes

Use a shared remaining allowance or a checked merge before admitting the parsed tree.

## Acceptance tests

Use a small token allowance and an ordinary final document whose two parser counts straddle it. Verify admission at the boundary and zero effects on refusal.

## Builds on

[syntax/parser.rs L393](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/syntax/parser.rs#L393) · [syntax/parser.rs L414](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/syntax/parser.rs#L414)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
