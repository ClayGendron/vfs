# Grep long options consume separate values

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A required long-option value is handled consistently whether joined with an equals sign or passed as the next word.

## The problem

A separate pattern or maximum count can be left among the file operands. The command then searches with a different option value.

## Proposed changes

Consume required arguments during option parsing and reject missing or malformed numeric values as usage errors.

## Acceptance tests

Compare the two spellings for regexp and maximum count, including a real file operand. Check selected lines, status and the paths read.

## Builds on

[programs/grep.rs L85](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/grep.rs#L85)
