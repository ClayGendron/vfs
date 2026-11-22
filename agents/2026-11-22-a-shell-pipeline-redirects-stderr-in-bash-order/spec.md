# A shell pipeline redirects stderr in Bash order

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Implicit duplication of the producer’s stderr sees the producer’s stdout after explicit redirections have been applied.

## The problem

Explicit producer redirections currently override the implicit stderr duplication. Output or diagnostics can reach a different file than Bash would select.

## Proposed changes

Apply the pipe-stderr duplication at the end of producer redirection setup for simple and compound commands.

## Acceptance tests

Compare the downstream stream, both captured outputs and the redirected file with Bash for a producer that writes to both descriptors.

## Builds on

[machine/exec.rs L472](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L472) · [machine/exec.rs L1008](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1008)
