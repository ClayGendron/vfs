# Shell runtime initialization is safe across a supported fork

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A supported fork during concurrent shell initialization cannot leave the child waiting for a vanished lock owner.

## The problem

The child locks an inherited mutex before testing the new PID. If another thread owned it at fork, it may remain locked. The existing test warms the runtime and forks when idle. This finding is conditional and source-traced.

## Proposed changes

Define when a multithreaded fork is supported. Provide fresh process-local synchronization on the child path or explicitly require and enforce a quiescent initialization protocol. Coordinate with the worker pool’s existing fork handling.

## Acceptance tests

Use controlled initialization barriers to check the chosen lifecycle protocol, with bounded test cleanup. Retain the existing warm, quiescent fork test and check that the child starts its own epoch handling.

## Builds on

[crates/vfs-core/src/shell_binding.rs L280](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-core/src/shell_binding.rs#L280) · [crates/vfs-core/src/shell_binding.rs L307](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-core/src/shell_binding.rs#L307) · [tests/shell/test_host.py L543](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/tests/shell/test_host.py#L543)
