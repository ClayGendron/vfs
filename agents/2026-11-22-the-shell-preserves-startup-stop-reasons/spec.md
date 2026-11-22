# The shell preserves startup stop reasons

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A runtime deadline or execution-budget stop during startup has the same category and exit status as the equivalent stop during stepping.

## The problem

Constructor failures all become exit 2. An initial module-memory refusal or startup deadline can even be classified as internal. The existing pure parse-budget case intentionally expects exit 2.

## Proposed changes

Carry a typed cause across instantiation and Python startup. Preserve the existing exit status for syntax, refused constructs and pure parse-budget failures.

## Acceptance tests

Compare identical runtime stop reasons at creation and stepping. Assert timeout 124 and execution-budget 137 and retain the separate parse-budget status 2 fixture.

## Builds on

[crates/vfs-core/src/shell_binding.rs L128](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-core/src/shell_binding.rs#L128) · [crates/vfs-core/src/shell_binding.rs L459](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-core/src/shell_binding.rs#L459) · [src/vfs/shell/host.py L267](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L267)
