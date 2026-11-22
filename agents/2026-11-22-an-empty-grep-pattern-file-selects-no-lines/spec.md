# An empty grep pattern file selects no lines

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Zero patterns and one empty pattern have distinct match sets and exit statuses.

## The problem

Reading an empty pattern file creates one empty regex, so it can select every input line.

## Proposed changes

Represent an empty set separately from a regex that matches the empty string. Apply inversion to the set result.

## Acceptance tests

Compare zero-line and single-blank-line pattern files against the same input, both normally and inverted. Assert output and status.

## Builds on

[programs/grep.rs L143](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/grep.rs#L143) · [programs/grep.rs L184](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/grep.rs#L184)
