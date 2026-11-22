# Parameter escape expansion decodes Unicode consistently

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

The parameter escape transform supports the Unicode and control escapes recognized by Bash.

## The problem

The runtime escape decoder leaves forms literal that are already decoded in the ANSI-C source path.

## Proposed changes

Share compatible escape decoding while preserving context-specific treatment of invalid or incomplete forms.

## Acceptance tests

Compare short and long Unicode escapes and a control-letter escape in both contexts. Include a literal backslash case.

## Builds on

[machine/quote.rs L244](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/quote.rs#L244) · [ANSI-C source escapes](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/syntax/parser.rs#L1884)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
