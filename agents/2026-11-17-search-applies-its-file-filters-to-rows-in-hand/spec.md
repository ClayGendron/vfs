# Search applies its file filters to rows in hand

This is a placeholder. It records a defect and the intended fix so the work can be picked up later. It is not yet reviewed and not yet fit to build.

## The problem

`search` takes four file filters: `ext`, `ext_not`, `globs` and `globs_not`. They choose which files may appear in the answer.

`search` also takes `observations`, the rows of an earlier result. The search is then limited to those rows.

When both are passed, the four filters are ignored. Every row in `observations` is searched, whatever its extension or path.

`grep` and `glob` take the same arguments and apply the filters to the rows in hand. So the same call shape gives a filtered answer from `grep` and an unfiltered answer from `search`.

## Evidence

Executed on 2026-11-17 against a kernel with one in-memory mount holding `/x.txt` ("alpha beta") and `/y.md` ("alpha gamma"). `rows` is the result of `glob("/*")`.

| Call | Rows returned |
|---|---|
| `search("alpha", ext=("md",))` | `/y.md` |
| `search("alpha", observations=rows, ext=("md",))` | `/x.txt`, `/y.md` |
| `grep("alpha", observations=rows, ext=("md",))` | `/y.md` |

The second row is the defect. No error and no warning is returned.

## Where it happens

All in `src/vfs/base.py`.

- `search` builds a `_PathFilters` from the four arguments and passes it to `_route_fanout` as `filters`.
- `_route_fanout` has a branch for `observations`. That branch calls `_dispatch_grouped_observations` and returns. It never reads `filters`.
- `glob` and `grep` do not reach that branch with filters. They filter the rows first, through `glob_rows_in_hand` and `grep_rows_in_hand` in `src/vfs/chain.py`.

The docstring of `search` says the filters are not yet applied to `observations`. That sentence is removed when this is fixed.

## Decided

- With `observations`, `search` keeps a row only when the four filters admit its path, exactly as `grep` does for rows in hand.
- The filtering happens in the kernel, before any mount is asked, so a mount is never sent a row the filters exclude.
- A call whose filters exclude every row returns an empty successful result, as `grep` does.
- No new argument and no new name is added.

## Not yet decided

- Whether the rows are judged by the same function `grep` uses, or by a shared helper that both call. The first reading of `chain.py` should settle it.
- Whether a row excluded by a filter is recorded on the result. `grep` and `glob` are the model, and what they record has not been checked.

## Tests, written before the fix

At the kernel layer, in `tests/base/test_search_merge.py` or beside it.

- `search` with `observations` and `ext` returns only the rows with that extension.
- The same for `ext_not`, `globs` and `globs_not`, one test each.
- With two mounts, a mount whose rows are all excluded is not asked. A recording storage shows no `search` call.
- A filter that excludes every row gives an empty successful result.
- `search` and `grep` given the same `observations` and the same filters return the same set of paths.

## Scope

In: the `observations` branch of `search`, its tests, and the one sentence in the docstring.

Out: any change to how `search` ranks or merges, and any change to `glob` or `grep`.

## One line

`search` drops its four file filters when it is given `observations`, and it should apply them as `grep` does.
