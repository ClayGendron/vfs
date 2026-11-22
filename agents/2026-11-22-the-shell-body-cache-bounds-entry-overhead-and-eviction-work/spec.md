# The shell body cache bounds entry overhead and eviction work

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Each cache insertion costs work proportional to entries evicted, and empty bodies count toward the cache’s retained storage.

## The problem

Adding a body builds a list by scanning cached paths even when usage is far below the eviction threshold. The per-line byte tally counts payloads but omits keys and metadata, so empty files can accumulate entries without advancing it.

## Proposed changes

Maintain eviction order incrementally, count keys and entry overhead, and preserve the active-reader policy.

## Acceptance tests

Count entries visited as the number of small files doubles. Exercise entries with zero payload and verify eviction releases their overhead.

## Builds on

[src/vfs/shell/host.py L392](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L392)

See also [A line has a verb budget, a host sets the shell's budgets, and a cli call may only tighten them](../2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md).
