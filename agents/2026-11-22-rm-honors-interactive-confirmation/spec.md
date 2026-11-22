# rm honors interactive confirmation

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

A negative response or EOF preserves each target for which confirmation was required.

## The problem

Both interactive removal options are accepted without setting any state. The delete path never reads the answer. EOF or a negative answer therefore gives no protection. GNU requires per-file confirmation for the always-interactive option and one confirmation under the applicable recursive or operand-count conditions for the once-interactive option.

## Proposed changes

Honor per-file and once-only confirmation on the shell descriptors, including option order and GNU’s recursive and operand-count conditions.

## Acceptance tests

Compare yes, no and EOF on an in-memory fixture. Count prompts and delete requests for both interactive switches, including a recursive request.

## Builds on

[programs/files.rs L655](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/files.rs#L655) · [programs/files.rs L701](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/files.rs#L701)
