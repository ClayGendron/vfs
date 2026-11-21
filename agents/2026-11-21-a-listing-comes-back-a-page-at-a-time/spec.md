# A listing comes back a page at a time

A draft, written on 2026-11-21 from story K4 of `context/standards/roadmap.md` and from `context/specifications/active/176-the-listing-cursor/spec.md`, read against `dev` at `ffaede80`. It is not reviewed, and nothing is built.

## The outcome wanted

`ls`, `tree` and `glob` take `after=` and `limit=`, and return the path of the last row as `Result.next_after`. A directory of 10,000 children read at `limit=1000` is ten calls that visit each child exactly once. A page costs a fixed number of statements and reads about `limit` rows, however many rows in the directory are deleted.

## Builds on

- `context/specifications/active/176-the-listing-cursor/spec.md`, called spec 176 below. It holds the design: keyset pages, the fill rule, the frontier merge and the key in each mount's coordinates. That design stands except where this spec says otherwise.
- Decision 5 of `context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md`: the key is a declared field of `Result` named `next_after`, typed as a path, and it is the plain path of a row on the page, never a sealed token.
- `agents/2026-11-18-a-mount-is-listed-as-a-directory-is/spec.md`, which landed as pull request 13 and changed what a listing shows at a mount point.

## The problem

`ls` of a directory with 10,000 children returns 10,000 rows. No verb takes `after=` or `limit=`, and `Result` has no `next_after`. The one `next_after` under `src/vfs` is a field of the index pass's own cursor in `storage/backends/database/indexing.py`, which is unrelated.

Three pieces of work wait on the key.

- **The shell.** On the branch `the-shell-speaks-bash`, `ls | head -3` over 2,000 files issued one `ls` that returned every row (measured on 2026-11-21). The shell's own criterion, a 10,000-file `ls | wc -l` in ten chunks, cannot pass until a listing pages.
- **The action log.** Its read side, `calls`, pages on the same key.
- **The MCP tools,** which must not put 10,000 rows into a model's context.

## What changed since spec 176 was written

Spec 176 was written on 2026-10-24. Nine things in it no longer match the tree.

1. **vfs serves SQLite and Postgres only.** Every table, budget and counter in spec 176 for MariaDB, SQL Server and Oracle falls away. So does its reason for refusing a partial index, which was that Oracle and MariaDB have none. Choice 2 reopens that.
2. **The schema format is 27.** Spec 176 says 23, then 24 and 25. The new numbers follow 27.
3. **Its line numbers and its record numbers are stale.** The decision records were retired on 2026-10-30. The functions it names still exist: `ls_rows`, `tree_rows`, `glob_rows`, `_pattern_candidates`, `_children_by_parent` and `_trash_roots` in `storage/backends/database/reads.py`, and `descendant_filter` and `liveness_filters` in `storage/backends/database/descent.py`.
4. **Two of its three open markers are decided.** The key's shape and the field it rides are settled by the ruling above. The default page is not, and it is choice 1.
5. **The mount-point rule landed after it.** Section 3.3 of spec 176 says a mount point shows as its stored directory row in the parent mount. Each claim in that section is read again against the landed rule before the router's paging is written. The draft `agents/2026-11-21-a-listing-at-a-mount-point-is-read-again/spec.md` names defects in `tree` and in `glob`'s named roots at a mount point, and paging is built on the corrected behaviour, not beside it.
6. **A second draft wants the same range.** `agents/2026-11-21-postgres-reads-a-subtree-by-its-range/spec.md` reads a subtree by an explicit path range. Section 2.4 of spec 176 pages `tree` on the same range. One helper serves both.
7. **`base.py` and `reads.py` are at their size limits.** They hold 3,103 and 1,243 lines, and `tests/lint/allowlist.py` allows exactly that. The paging code goes where spec 176 puts it, in `vfs/results/paging.py` and `vfs/paths.py`, and the page statements go in a storage module of their own.
8. **The trash view has a column spec 176 does not know.** `vfs_entries` has `trash_root_id` and an index on it. The page of the trash head is derived again from the code as it stands.
9. **`TraitKey` has seven keys,** and none is `listing_cursor`.

## Decisions

1. **The design of spec 176 stands.** The key is a row's plain path. A page seeks strictly after the key and never counts an offset. A key is always a row that was shown, so it never names a hidden row. One frontier rule merges the pages of several mounts. A batch `ls` takes no cursor, and `glob` refuses `max_count` beside `limit`.
2. **The work is three slices, as in spec 176.** Slice A is the field, the two arguments, the merge rule, the key in each mount's coordinates, and a derived page in the router that serves every backend with no change to SQL. Slice B is the native keyset pages in the database backend, the index change, the trait, and the conformance family on both engines. Slice C is a bounded `tree` under `max_depth`.
3. **Slices A and B reach `dev` together.** The derived page of slice A is correct, but each page costs what the whole listing costs, so ten pages of a 10,000-child directory fetch 100,000 rows. A read must cost in proportion to what it returns. Slice A is a step inside the branch, not a landing.
4. **Rows visited are counted on both engines.** On SQLite the plan must name the index with the liveness term as an index constraint, as section 5 of spec 176 says. On Postgres the count comes from `EXPLAIN (ANALYZE, FORMAT JSON)`.
5. **The fronts are out.** The shell, the MCP tools and the guests each adopt the key in their own work. For the shell that is one change in its host: the listing request passes a `limit` and loops on the key.

## Tests

Written first, and seen failing. Counts and states, never clocks.

- The four criteria of story K4: ten pages of 1,000 over 10,000 children visit each child once and fetch at most `limit + 1` rows a page, with tombstones excluded by the predicate; `tree` and `glob` page on the same key, and a fan-out over three mounts merges its pages into one key; `Result | Result` clears the key, `with_mount` rebases it, and the renderer prints `more: after=…` only when it is set; an anonymous caller pages the same key under a `list` posture and is `unauthenticated` at the first page under `none`.
- Criteria 1 to 16 of spec 176, with "every engine leg" read as SQLite and Postgres, and the two criteria that name Oracle and SQL Server budgets read against Postgres's.
- The seeded test of the frontier rule against an oracle that lists everything and slices, and the property test of the key in a mount's coordinates.

## Scope

In: the two arguments on the router, on `Session`, on the synchronous face and in `PARAMS`; `Result.next_after`, its wire shape, what each operation on a `Result` does to it, and its rendered line; `vfs/results/paging.py`; the page statements, the fill rule, the index change and the trait; the conformance family; the reference pages the docs gate builds from the docstrings.

Out: the fronts, by decision 5; a cursor on `grep`, `search` or `traverse`; one snapshot across pages; retiring `glob`'s `max_count`.

## Not checked

- Whether Postgres seeks a composite index on `deleted_at IS NULL` when its leading column is bound. Spec 176 infers it and did not run it.
- The statement counts of section 4 of spec 176 (3 for the system actor, 5 for a named caller) on today's code.
- The 38 statements of a 10,000-row `write`. Spec 176 counted it on 2026-10-24, and `write` has since gained its preconditions.
- Each routing claim of section 3.3 of spec 176 against the landed mount-point rule.

## Choices to confirm

1. **Does the kernel have a default page?** Recommended: no. `limit=None` lists everything, so no caller that never reads `next_after` can lose rows, and each front passes its own page size. The other answer is a kernel default of 1,000 on all three verbs, which bounds the Python surface too and changes what an existing `ls` returns.
2. **Which index keeps a page's read work bounded?** Spec 176 chose two composite indexes, `(parent_id, deleted_at, name)` and `(deleted_at, path)`, because two engines had no partial index. Both engines served today have one. Recommended: measure both shapes on both engines as the first task of slice B, and take the partial index `WHERE deleted_at IS NULL` if each planner picks it, because it holds live rows only.
3. **Is slice C part of this work?** Recommended: no, a spec of its own after slice B. It adds a `depth` column written wherever a path is written, including every row a move rewrites, and it touches the statements the subtree-range draft touches.

## One line

`ls`, `tree` and `glob` take `after=` and `limit=` and return the last row's path as `Result.next_after`, built on spec 176's design, trued to two engines and to the tree as it stands.
