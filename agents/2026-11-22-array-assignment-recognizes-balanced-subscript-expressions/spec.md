# Array assignment recognizes balanced subscript expressions

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Whitespace inside a valid arithmetic subscript does not change an assignment into a command.

## The problem

The parser’s assignment lookahead rejects whitespace before the subscript has closed.

## Proposed changes

Scan the balanced and quoted subscript before classifying the word and its assignment operator.

## Acceptance tests

Compare a spaced arithmetic index and its compact equivalent with Bash. Verify array contents, exit status and absence of program dispatch.

## Builds on

[syntax/parser.rs L1347](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/syntax/parser.rs#L1347)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
