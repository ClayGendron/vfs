# Forced removal distinguishes absence from a failed lookup

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Forced removal suppresses expected absence while exposing actionable host failures.

## The problem

The program-facing stat helper drops host errors and forced removal treats the empty result as absence.

## Proposed changes

Retain typed stat failures through utility dispatch. Respect the router’s masking rules and suppress only the documented not-found outcome.

## Acceptance tests

Use a recording host that returns absence and then a backend error in separate cases. Assert status, diagnostic and zero deletes for both outcomes.

## Builds on

[programs/mod.rs L137](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/mod.rs#L137) · [programs/files.rs L680](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/files.rs#L680)
