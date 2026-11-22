# Persistent shell descriptors report final write errors

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

A command or final flush that discovers a refused buffered write reports that failure to its caller.

## The problem

The final flush and descriptor restoration can discard a saved write error for a persistent named descriptor. Command status can indicate success even though data never landed.

## Proposed changes

Retain the first writer error across descriptor duplication. At close or line completion expose it through command status and the existing host evidence rules.

## Acceptance tests

Allow the opening write and refuse the later data flush. Verify status, diagnostic, retained host warning and actual stored bytes, including a duplicated descriptor.

## Builds on

[machine/files.rs L193](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/files.rs#L193) · [machine/exec.rs L1910](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1910) · [machine/exec.rs L2322](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L2322)
