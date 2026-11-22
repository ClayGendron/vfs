# Shell search limits return classified usage errors

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A decimal outside the supported conversion range returns a shell usage diagnostic through the normal result path.

## The problem

The host tests ASCII digits and then converts the entire string directly to a Python integer. Conversion can raise before search returns a status.

## Proposed changes

Validate the argument with predictable bounded conversion and preserve the existing treatment of a nonnumeric query word.

## Acceptance tests

Check ordinary, out-of-range and nonnumeric arguments at the public shell entry point. Assert exit status, diagnostic and whether search was dispatched.

## Builds on

[src/vfs/shell/host.py L449](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L449)
