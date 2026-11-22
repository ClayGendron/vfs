# The native shell corpus runs on the default debug test stack

Draft, 2026-11-22. Verification finding from the shell review of `cbda2721`.

## The outcome wanted

Developers can run the native debug corpus without an unexplained process abort or a machine-specific stack override.

## The problem

The unmodified debug corpus aborted on the default Rust 1.100.0 test-thread stack in the reviewed checkout. Both release and a debug rerun with a 16 MiB test-thread stack passed. The failing call path was not established.

## Proposed changes

Identify whether the stack is consumed by the harness or a supported native interpreter path. Fix the owning code or establish a documented, locally enforced test-harness stack requirement supported by measurements.

## Acceptance tests

Run the unmodified corpus in debug on a clean environment with the default external stack settings, then in the release CI profile. Verify the recorded corpus result and retain a focused regression for the measured cause.

## Builds on

[corpus.rs](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/tests/corpus.rs#L12) · [CI shell release suite](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/.github/workflows/test.yml#L37)
