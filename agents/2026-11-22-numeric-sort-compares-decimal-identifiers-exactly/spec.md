# Numeric sort compares decimal identifiers exactly

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Numeric unique sort retains adjacent distinct integer keys throughout the supported input range.

## The problem

Conversion to floating point makes adjacent large integers compare equal. Numeric unique sort subsequently discards a record.

## Proposed changes

Compare signed decimal keys exactly for numeric sort. Keep original records available for emission and reserve floating-point semantics for its separate comparison mode.

## Acceptance tests

Compare adjacent large IDs, negatives, fractional keys and equivalent decimal spellings with GNU sort. Check ordering and which records survive unique selection.

## Builds on

[programs/text.rs L958](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/text.rs#L958) · [programs/text.rs L984](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/text.rs#L984) · [programs/text.rs L1252](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/text.rs#L1252)
