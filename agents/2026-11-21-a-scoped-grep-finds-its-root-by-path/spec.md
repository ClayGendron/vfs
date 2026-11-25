# A scoped grep finds its root by path

A draft, written on 2026-11-21 from `agents/2026-11-21-grep-query-planner/research.md` section R1 and round 1 of its review. It is not reviewed on its own, and nothing is built.

## The outcome wanted

A `grep`, `glob` or `search` scoped to a directory or a file pays for what that scope holds, and never for what the scope's parent directory holds.

## Builds on

`agents/2026-11-21-grep-query-planner/`: its `research.md` R1, and the round-1 review scripts under `reviews/scripts/round-1/`. The grep planner designed there rests on this spec landing first.

## The problem

Shown by scripts that ran on the Linux sandbox, commit `5dfdcc79`, SQLite.

- **A root's own row is admitted by an arm bounded only by its parent's segments.** At the storage seam, `paths=("/drivers/atm",)` arrives as the entry-wide literal glob `/drivers/atm`, beside a scope whose arms are `**`. The literal compiles to the allow-list arm `/drivers/atm`, with segments `{drivers}` and a name fact `atm`. The segment table bounds an arm by its segments alone, so this arm admits every entry under any directory named `drivers`. The name fact narrows the rows only later, in the candidate fetch.
- **A 30-file directory builds a 40,262-id allow-list.** `grep("return 0;", paths=("/drivers/atm",))` built the allow-list in 42.7 ms. It then resolved all 40,262 ids in two 18,180-bind statements, at 108 ms, and took 230 ms in all. The same search spelled `globs=("/drivers/atm/**",)` built 38 ids in 3.4 ms and took 13 ms.
- **A file root pays the same way.** `/include/linux/dcache.h` built 3,958 ids, and `/fs/open.c` with `/fs/read_write.c` built 2,462 (`reviews/scripts/round-1/r01_trace_shape.py`, `research.md` R1).
- **The cost follows the parent, not the scope.** It is why `drivers/atm` (30 files), `drivers/clocksource` (100) and `drivers/md` (296) all measured the same grep cost in `agents/2026-11-21-linux-grep-benchmark/`.

## Decisions

1. **A fully literal admission arm resolves by path equality.** An arm with no wildcard, class or brace resolves to one `path = :arm` lookup on the unique path index, never to its parent's segments. The seam cannot tell a root's literal from a caller's own literal glob, and does not need to: path equality is exact for both. Other arms keep their segment terms.

## Tests

- A parity test runs `grep`, `glob` and `search` over roots that are directories, files, several roots and overlapping roots, with rare, common, anchored, alternated and case-insensitive patterns. It compares rows, line numbers and match text against today's code.
- A counted test pins the allow-list's size for a small directory under a large parent. It is the scope's entries plus the root, never the parent's subtree. The statement count is pinned too.

## Scope

In: the allow-list arm of a fully literal admission pattern, in `pathterms.py`. Out: bounding root scopes by path range, and the rest of the grep planner (both in `agents/2026-11-21-grep-query-planner/spec.md`).

## Not checked

- Postgres. The lookup is an equality on a unique index, so its plan is expected to be an index lookup on both engines, but no Postgres leg was run.
- What the fix shows on `glob` and `search` scopes. The allow-list seam is shared, so the gain is expected there too, but only `grep` was measured.

## What was checked

Round 1 of the planner's review prototyped this decision as a path-equality lookup for fully literal arms (`reviews/scripts/round-1/r04_plans.py`, mode `d1`). It covered 72 pairs: 8 scopes (1 to 1,033 files, a file root, two file roots, three roots, overlapping roots) by 9 patterns. Every pair returned the same rows as today, line spans and match text included. The allow-list fell from 40,262 ids to 39 for `/drivers/atm`, and from 3,958 to 1 for `dcache.h`.

## One line

A literal path in an admission is found by its path, so a scoped call never pays for its parent directory.
