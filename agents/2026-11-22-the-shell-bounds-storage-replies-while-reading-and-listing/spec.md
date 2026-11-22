# The shell bounds storage replies while reading and listing

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

A small file-range request and one directory page require bounded host-side reply storage.

## The problem

The Python host fetches an entire file for one range and can retain it regardless of size. Listing constructs all child entries before encoding the reply.

## Proposed changes

Add version-aware ranged reads and use the router’s directory pagination with a consistent per-line allowance. Account for host buffers while preparing each reply.

## Acceptance tests

Use an instrumented storage with a multi-range file and a multi-page directory. Check sizes requested, maximum live bytes, ordering and continuity of the returned data.

## Builds on

[src/vfs/shell/host.py L375](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L375) · [src/vfs/shell/host.py L392](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L392) · [src/vfs/shell/host.py L417](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L417)

See also [A line has a verb budget, a host sets the shell's budgets, and a cli call may only tighten them](../2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md).
