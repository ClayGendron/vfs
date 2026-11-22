# File traversal reports incomplete directory results

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Find and recursive grep expose operational failures while walking a visible tree.

## The problem

Both programs can skip a directory after a failed listing. Find can substitute a zero size when a child stat fails, making an unreadable child look empty.

## Proposed changes

Carry listing and stat errors through traversal while preserving authorized partial output and each utility’s documented quiet behavior. Never infer emptiness from failed metadata.

## Acceptance tests

Return one readable child and one failed listing or stat. Verify surviving rows, error status and the treatment of the empty predicate and quiet options.

## Builds on

[programs/files.rs L431](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/files.rs#L431) · [programs/files.rs L468](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/files.rs#L468) · [programs/grep.rs L349](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/grep.rs#L349)
