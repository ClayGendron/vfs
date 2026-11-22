# Delimited reads drain full shell pipes

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A finite record that spans multiple pipe buffers can reach read or mapfile intact.

## The problem

A full pipe blocks its writer while the delimited reader can wait for the delimiter without draining an available prefix.

## Proposed changes

Consume available prefixes into a charged record buffer and yield to the producer. Preserve delimiter handling at exact capacity and on final EOF.

## Acceptance tests

Send finite records just below, at and above pipe capacity. Check the resulting records and exit status with a sufficient budget and then with a small logical budget.

## Builds on

[machine/io.rs L352](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/io.rs#L352) · [machine/io.rs L406](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/io.rs#L406) · [machine/mod.rs L464](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/mod.rs#L464)
