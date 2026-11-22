# Here-document delimiters preserve their quoted spelling

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

The parser retains the quote-removed delimiter exactly so that literal data remains within the intended here-document.

## The problem

The parser reconstructs the delimiter from parsed word nodes, dropping nonliteral child nodes in a double-quoted delimiter. Literal data in generated shell source can end up being parsed as commands. Any resulting effects run with the submitting caller’s authority. The existing known-failure list already records the underlying delimiter-handling discrepancy.

## Proposed changes

Read delimiter words under the shell’s quote-removal rules. Preserve expansion-like text that forms part of the literal delimiter. Relate the correction to the existing known-failure entry.

## Acceptance tests

Compare delimiter text, body boundaries and following AST nodes against the pinned corpus. Include an ordinary near-match before the terminator and verify that body text produces no command nodes.

## Builds on

[syntax/parser.rs L1317](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/syntax/parser.rs#L1317) · [syntax/parser.rs L2372](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/syntax/parser.rs#L2372) · [tests/shell/known_failures.txt L73](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/tests/shell/known_failures.txt#L73)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
