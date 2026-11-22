# Printed shell functions preserve their parsed behavior

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A definition produced by declare -f can be parsed again with the original function’s semantics.

## The problem

The deparser can duplicate arithmetic delimiters and omit here-document bodies, pipeline metadata or grouping that determines precedence.

## Proposed changes

Retain the source spans and precedence information needed for rendering. Emit document bodies and pipe metadata with the applicable command.

## Acceptance tests

Round-trip definitions containing arithmetic, a here-document, a grouped conditional and piped stderr. Compare output, status and file effects before and after rendering.

## Builds on

[machine/deparse.rs L66](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/deparse.rs#L66) · [machine/deparse.rs L260](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/deparse.rs#L260) · [syntax/parser.rs L964](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/syntax/parser.rs#L964)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
