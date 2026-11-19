# Search applies its file filters to rows in hand

This spec is built, on the branch `search-applies-its-file-filters-to-rows-in-hand`, and the work is not yet committed. It was reviewed on 2026-11-18 by a fresh reader, who found one thing that stopped it, the line count of `base.py`, and eight smaller ones, each answered in the text below. It replaces the placeholder of 2026-11-17. The figures in it were executed on 2026-11-18 at commit `0d05c606`, on the in-memory storage, which is the database storage on SQLite. The build differs from the text in three ways. First, `base.py` was 3079 lines when the build began, and the three moves left it at 3073, so its baseline entry is 3073. Second, three existing tests patched `plan_scope` and the planning budget `WALL_TIME_BUDGET` on `vfs.base`, and the planner now reads both from `vfs.fanout`. So those tests patch them there: `test_planning_leaves_the_loop` and `test_planning_past_the_wall_truncates` in `tests/base/test_glob_namespace.py`, and `test_a_planning_stop_keeps_every_undecided_skip` in `tests/base/test_grep_namespace.py`. The two tests that set the budget to `-1.0` set it on both modules, so they still mean what they meant before the move. Third, the seven tests of the filter sets over the two real mounts are written as one test with a table of nine filter sets, and the expected values are the ones listed under "Tests".

## The outcome wanted

`search`, `grep` and `glob` give one meaning to a file filter over rows in hand. A call that passes `observations` and a filter gets back only rows the filter admits, from all three verbs.

## Terms

- **Rows in hand.** The rows a caller passes as `observations`. They are the rows of an earlier result.
- **File filters.** The four arguments `ext`, `ext_not`, `globs` and `globs_not`. They choose files by path and never by content.
- **Kernel.** `AsyncVirtualFileSystem` in `src/vfs/base.py`. It checks a call, finds the mounts and calls their storages.
- **Gates.** One call's four file filters, compiled once by `compile_gates`.
- **Judge.** To test rows against the gates. `judge_in_hand` in `src/vfs/chain.py` does it for rows in hand.
- **Hop.** One piece of work sent to the process pool, so the event loop is not held.
- **Meta rule.** A storage hides a row under `/.vfs` unless a pattern names `/.vfs` literally.
- **Depth.** The number of rows each mount is asked for when more than one mount answers a `search`. It is `min(3 * limit, 256)`.

## The problem

With `observations`, `search` ignores all four file filters. `grep` given the same rows applies them.

One kernel over one in-memory storage. `/x.txt` holds "alpha beta" and `/y.md` holds "alpha gamma". `rows` is the result of `glob("/*")`.

| Call | `search` returns | `grep` returns |
|---|---|---|
| `("alpha", ext=("md",))`, no `observations` | `/y.md` | not run |
| `("alpha", observations=rows, ext=("md",))` | `/x.txt`, `/y.md` | `/y.md` |
| `("alpha", observations=rows, ext_not=("md",))` | `/x.txt`, `/y.md` | `/x.txt` |
| `("alpha", observations=rows, globs=("*.md",))` | `/x.txt`, `/y.md` | `/y.md` |
| `("alpha", observations=rows, globs_not=("*.md",))` | `/x.txt`, `/y.md` | `/x.txt` |
| `("alpha", observations=rows, ext=("rs",))` | `/x.txt`, `/y.md` | nothing |
| `("alpha", observations=rows, globs=("*.{md,rst}",))` | `/x.txt`, `/y.md` | `/y.md` |
| `("alpha", observations=rows, globs=("{a",))` | `/x.txt`, `/y.md`, success | refused, `invalid` |
| `("alpha", observations=rows, globs_not=("{a",))` | `/x.txt`, `/y.md`, success | refused, `invalid` |

No error and no warning is returned by `search` in any row. The last two rows show that a glob that cannot be parsed is accepted in silence.

The filter also changes which rows fill `limit`. One storage holds `/top.txt` and `/next.txt`, which rank first and second for "alpha", and `/third.md` and `/fourth.md`, which rank third and fourth. `search("alpha", observations=rows, ext=("md",), limit=2)` returns `/top.txt` and `/next.txt`. The two `.md` rows are not returned at all.

### Where it happens

All in `src/vfs/base.py`.

- `search` builds a `PathFilters` from the four arguments and passes it to `_route_fanout` as `filters`.
- `_route_fanout` has a branch for `observations`. It calls `_dispatch_grouped_observations` and returns. It never reads `filters`.
- `_dispatch_grouped_observations` groups the rows by mount and calls each storage. A storage receives four keywords: `query`, `limit`, `observations` and `columns`. No filter reaches it.
- `glob` and `grep` do not reach that branch with rows. They filter the rows first, in `glob_rows_in_hand` and `grep_rows_in_hand`, which both call `judge_in_hand`.

### What a storage does with rows

Read in `src/vfs/storage/backends/database/search.py` and executed on the storage directly, which holds `/x.txt`, `/y.md` and `/w.md`.

| Call on the storage | Returns |
|---|---|
| `search(query="alpha", observations=[/x.txt])` | `/x.txt` |
| `search(query="alpha", observations=[])` | `/w.md`, `/x.txt`, `/y.md` |
| `search(query="alpha", observations=[/x.txt], globs=("*.md",))` | `/w.md`, `/x.txt`, `/y.md` |
| `search(query="alpha", observations=[/x.txt], ext=("md",))` | nothing |
| `search(query="alpha", observations=[/x.txt], globs_not=("*.txt",))` | nothing |

Two facts follow.

- A storage adds each row's path to `globs` as one more pattern. So `globs` beside `observations` is a union in the storage, and not a filter.
- An empty list is not a batch to the storage. It searches the whole mount.

## Decisions

### 1. The kernel applies the filters, before any storage is asked

`search` judges the rows in hand against the four file filters in the kernel. Only the rows that pass are sent on. A storage receives the same four keywords it receives today.

The path judged is the path the row carries, which is a path in the caller's namespace. So `globs=("/data/**",)` keeps the rows of a mount at `/data`, and `globs=("deep/*",)` keeps nothing at `/data/deep`, because a pattern with a `/` is matched from the root. `grep` gives the same two answers for the same rows.

Reason: this keeps one meaning for a filter across the three verbs, and it needs no change to the storage protocol. The other choice does neither. A storage reads `globs` beside `observations` as a union. It sees paths inside its own mount, so each pattern would have to be rewritten for each mount. It applies the meta rule, which no verb applies to rows in hand.

### 2. The rows are filtered first and ranked second

The filter runs before the rows are grouped by mount. Everything after it sees only the rows that passed.

The code was read to confirm where each cut is made.

- `_dispatch_grouped_observations` groups the rows by mount. With more than one group, each storage is asked for the depth. With one group, it is asked for `limit`.
- Each storage ranks the rows it was sent and returns that many at most.
- `merge_ranked` in `src/vfs/rerank.py` cuts to `limit`. One answering mount is cut by `_sole_answer`. Several are merged and then cut.

The filter sits before all three. So a dropped row never takes a place in a storage's answer, in the depth or in the final cut. `limit` rows come back whenever that many of the passing rows match the query.

Executed with the four files above and `ext=("md",)`, `limit=2`. Filtering first returns `/third.md` and `/fourth.md`. Ranking first and filtering second would return nothing, because both places go to `.txt` rows.

Reason: a filter says which files the search is over. A caller that asks for 2 rows among the `.md` files expects the 2 best `.md` files.

### 3. `search` judges its rows with `judge_in_hand`, through one new function in `chain.py`

The gates, the deadline, the judging and the truncation record live in `src/vfs/chain.py`, where they live for `glob` and `grep`. One function is added there, in the section "The filters".

```python
async def admit_rows_in_hand(
    rows: list[Observation],
    *,
    globs: tuple[str, ...],
    globs_not: tuple[str, ...],
    ext: tuple[str, ...],
    ext_not: tuple[str, ...],
) -> tuple[list[Observation], list[ResultError]]:
```

It compiles the four filters with `compile_gates(globs, globs_not, ext=ext, ext_not=ext_not)`, takes the deadline of decision 6, and calls `judge_in_hand(gates, rows, deadline)`. That is the function `glob_rows_in_hand`, `grep_rows_in_hand` and the root probe already call. It returns the rows that passed, and either no record or the one record of decision 6. It takes patterns that are already expanded.

In `base.py`, `search` gains only the calls below, in its branch for `observations`. The steps run in this order.

1. `_gate_params`, unchanged.
2. `expand_channel("globs", globs)` and `expand_channel("globs_not", globs_not)`. A `PatternError` is refused as decision 8 says.
3. If the kernel is closed, `_closed_error("search")`.
4. `_observation_rows("search", observations)`. A batch that is not rows is refused with `invalid`, as today.
5. `admit_rows_in_hand`, with the expanded patterns.
6. `_route_fanout("search", observations=kept, ranked=..., query=query, limit=limit, columns=columns, authority=authority)`, where `kept` is the list `admit_rows_in_hand` returned. `filters` is not passed.
7. The records `admit_rows_in_hand` returned are added to the result with `_with_skips`.

`_route_fanout` and `_dispatch_grouped_observations` are not changed.

`src/vfs/base.py` is held at an exact line count by `MODULE_LINE_BASELINE` in `tests/lint/allowlist.py`, and it may not grow. The lines `search` gains are paid for in the same landing. The static method `_planned` moves out of `base.py` into `src/vfs/fanout.py`, as a function named `planned_scope` with the same arguments and the same body. It is the wrapper that runs `plan_scope` in place or on the process pool, and `fanout.py` already holds `plan_scope` and `walks`. Its two callers, `_glob_dispatches` and `_grep_dispatches`, call the function.

Measured on a copy of `base.py` after `ruff format`: `search` gains 31 lines in the shape above, and moving `_planned` frees 23. Two more helpers at the foot of `base.py` move to pay the rest, each with the same arguments and the same body.

| What moves | To | New name | Lines freed |
|---|---|---|---|
| `_planned` | `src/vfs/fanout.py` | `planned_scope` | 23 |
| `_is_tombstoned_site` | `src/vfs/mounts.py`, under the checks a mount change passes | `is_tombstoned_site` | 9 |
| `_scoped` | `src/vfs/fanout.py` | `scope_argument` | 6 |

That frees 38 lines for the 31 gained. After the changes `wc -l src/vfs/base.py` is at or below its baseline, and the baseline entry is set to the new exact count. The line counts were taken at commit `0d05c606`. If the file has changed by the time this is built, the rule stands and the counts are taken again: `base.py` ends no longer than it began.

Rows keep their order and their duplicates through the filter, as `judge_in_hand` promises.

Reason: one function already holds the rule for rows in hand, and one module already holds every filter over them. A second copy in `base.py` could drift from it, and `base.py` has no lines to spare.

### 4. The call answers as if only the passing rows had been given

`search(query, observations=rows, <filters>)` returns what `search(query, observations=<the rows that pass>)` returns. The paths, the order, the scores and the `legs` extra are the same. Executed, and true.

The consequences, each executed against the design.

| Case | What the call does |
|---|---|
| The passing rows lie in one mount of two | That mount alone is asked, for `limit` rows. Its order, its scores and its own `legs` are the answer. |
| The passing rows lie in two mounts | Each is asked for the depth, with its own passing rows. The answers are merged as today. |
| No row passes | No storage is called. The result is successful and empty, with no error and no `legs` extra. |
| No row passes and the query has no searchable term | The same empty success. The query is checked by a storage, and none is called. `search("", observations=[])` answers this way today. |
| A dropped row lies in a mount that cannot `search` | The call is not refused. See decision 7. |
| A filter drops the rows on one side of the trash view | The call is not refused for mixing the two sides. Today a storage refuses such a batch with `invalid`. |

A mount whose rows are all dropped must not be called. It has no group, so it is not. An empty list sent to a storage would search the whole mount.

`grep` differs in one of these rows. It compiles its pattern in the kernel, so it refuses a bad pattern even when no row passes. `search` cannot do that. Whether a query has a searchable term is the storage's judgement, so a call that asks no storage checks no query.

Reason: `grep` and `glob` treat a dropped row as a row that was never sent. One rule a caller can state in a sentence is worth more than a list of checks that still run on rows the caller filtered out.

### 5. No meta rule applies to a row in hand

The kernel's filter judges the path and nothing else. A row under `/.vfs` passes a filter exactly as any other row does. Whether that row is then ranked is decided by its storage, as today.

Executed. A deleted file is held as the row `/.vfs/trash/gone.md`. With no filter `search` returns it today. Under the design `globs=("*.md",)` still returns it, and `globs_not=("*.md",)` drops it.

Reason: `judge_in_hand` applies no meta rule, because what a caller holds is never hidden from that caller. `search` follows it so the three verbs agree. The kernel's filter only removes rows. It can never show a row that a storage would hide.

### 6. The filter has its own time budget, and says so once when it reaches it

The deadline is `Deadline.after(WALL_TIME_BUDGET)` when the gates hold a pattern, and `Deadline.never()` when they hold none. It is read in `admit_rows_in_hand`, after the gates are compiled, as `grep_rows_in_hand` reads its own. `WALL_TIME_BUDGET` is the name `chain.py` imports, which is 10 seconds.

With `ext` or `ext_not` alone the gates hold no pattern. No hop is made and no clock is read.

A filter that reaches the deadline keeps the rows it judged and admitted. A row it did not judge is dropped, because it might match an exclusion. The rows kept are searched as usual. The result carries one more record, of kind `truncated` and severity `warning`, after every record the storages and the merge returned. The result is still a success.

The record is `wall_truncation(_CHAINED_SEARCH_REFINE_GUIDANCE)`. `_CHAINED_SEARCH_REFINE_GUIDANCE` is a new private constant in `chain.py`, placed under `_CHAINED_GLOB_REFINE_GUIDANCE`, with a one-line comment of its own. Its value is `"send fewer rows, or fewer globs"`. So the message is `Truncated: at the wall-time budget; send fewer rows, or fewer globs`. The two constants already in `chain.py` do not fit. Both tell the caller to narrow a pattern, and `search` has none.

Each storage then runs its own search under its own budget, as today. The two budgets are separate, and a storage may add a `truncated` record of its own.

Reason: each stage that matches rows in the kernel runs under one budget and reports once. A stage with no budget could hold a call for as long as its patterns take to build.

### 7. A row that passes is treated exactly as it is today

`search` has no `kind` argument, and the filter does not read a row's kind.

| A row that passes the filters | Today | Under the design |
|---|---|---|
| A directory | Sent to its storage, which does not rank it. No error, unless the row is a mount point or `/`. Such a row reaches its storage as the path `/`, the storage turns that path into a glob, and the call fails with `invalid`. | The same. |
| A path that is not there | Sent to its storage, which returns nothing for it. No error. | The same. |
| A row that carries no kind | Ranked if its storage holds a file there. | The same. |
| A row in a mount that cannot `search` | The whole call is refused with `unsupported` at the mount's path. No storage is called. | The same. |

A row that the filters drop is not sent and not checked. So a batch that holds a row in a mount that cannot `search` is refused only when that row passes the filters. Executed. With such a row at `/mute/m.txt`, `ext=("txt",)` is refused and `ext=("md",)` succeeds.

`grep` follows the same rule. Given a row in a mount that cannot `read`, `grep(observations=..., ext=("txt",))` is refused with `unsupported`, and `ext=("md",)` succeeds, because the dropped row is never read. Both verbs check only the storage verb the kernel needs, and only for the rows that pass.

`search` still asks the storages and returns their rows. It does not return the rows as held, which `glob` and `grep` do.

Reason: the filters choose rows. They are not a reason to change what happens to a row that was chosen.

### 8. A glob that cannot be parsed is refused with `invalid`, before any row is judged

With `observations`, `search` expands both glob channels with `expand_channel`, as `grep` does. A pattern that cannot be parsed is refused through `self._error(ErrorKind.invalid, op="search", detail=str(exc))`. No row is judged and no storage is called.

The message is the one `grep` gives for the same argument. For `globs=("{a",)` it is `Invalid: grep glob '{a': unclosed '{' — every brace group needs its '}'`. For `globs_not=("{a",)` it is `Invalid: glob exclusion '{a': unclosed '{' — every brace group needs its '}'`. Without `observations`, `search` already gives these words, from the storage.

The check comes before the check for a closed kernel, as in `grep`. So a closed kernel answers `invalid` for a bad glob and `backend_unavailable` for a good one.

Until `search` without `observations` expands its globs in the kernel, its two routes differ on a closed kernel. With `observations`, a bad glob answers `invalid`. Without, it answers `backend_unavailable`.

The expansion is also what lets a brace pattern work. `compile_gates` takes patterns that are already expanded.

Reason: a filter that cannot be parsed cannot be applied, and a call that drops it in silence returns rows the caller excluded.

### 9. A dropped row leaves no record, and the result keeps its shape

Nothing on the result says which rows were dropped or how many. `glob` and `grep` record nothing for a row their filters drop, and `search` follows them.

No key is added to the result, to a row or to `legs`. A row is what its storage returned, with `score` and `matches`. `legs` is the answering mount's own when one mount answers. It holds `merge` and `mounts` when several do. It is absent when no storage was called. `candidates` under `merge` counts fewer rows, because fewer were sent.

The scores of the rows that pass can differ from their scores in an unfiltered call. Each score is scaled over the rows that were ranked together. Decision 4 says what they equal.

Reason: a filter is the caller's own choice, and a record of it would repeat the arguments back.

### 10. Nothing is added to the storage protocol or to the public surface

No storage method, no keyword and no name exported from `vfs` is added. The new names are the function of decision 3 and the private constant of decision 6, both in `chain.py`, and `planned_scope` in `fanout.py`, which is `_planned` moved. `vfs.session` and `vfs.sync` pass the arguments through and are not changed.

## Cost

The filter issues no SQL statement and takes no lock. It makes no storage call.

- With a pattern in `globs` or `globs_not`, it makes one hop to the process pool for the whole batch.
- With `ext` or `ext_not` alone, it makes no hop. It reads each row's extension once, in the kernel.
- It holds one `(path, name)` pair and one verdict for each row. Memory grows with the batch and with nothing else.
- `_dispatch_grouped_observations` checks the type of each kept row once more, as it does for every batch. That is one pass over a list.

Counted on two canned mounts with 10,000 rows in hand under one mount, half `.md` and half `.txt`.

| Call | Hops | Rows judged in the hop | Rows sent to the storage |
|---|---|---|---|
| `globs=("*.md",), globs_not=("**/d7/**",)` | 1 | 10,000 | 4,900 |
| `ext=("md",)` | 0 | none | 5,000 |
| no filter | 0 | none | 10,000 |

The filter can only lower what a storage does. Counted on one real storage that holds the same 10,000 files, with all 10,000 rows in hand.

| Call | Statements today | Statements under the design | Most binds in one statement, today and under the design |
|---|---|---|---|
| no filter | 69 | 69 | 10,102 and 10,102 |
| `ext=("md",)` | 59 | 34 | 10,102 and 5,052 |
| `ext=("rs",)`, which no row passes | 59 | 0 | 10,102 and 0 |

The call with no filter ran first in each run. The statement with the most binds is the read of posture rows in `labels.py`. It is cut by `chunked` to the membership budget, which is 32,668 on SQLite. So it is one statement here and several on an engine with a smaller budget. No statement grows past the budget of its engine.

At the reference deployment the multiplier is the verb call. `search` is under a tenth of about 150,000 calls a day, and a `search` over rows in hand is a part of that. Each such call gains at most one hop. No read waits on a writer because of it.

## Tests

Written and seen failing before the code, in `tests/base/test_search_merge.py`, under a new banner named "Rows in hand and the file filters". Counts are of calls a storage double recorded, or of calls to a wrapped function. None is of time.

The fixtures.

- **Two real mounts.** A kernel over one `InMemoryStorage` that holds `/x.txt` ("alpha beta") and `/y.md` ("alpha gamma"). A second `InMemoryStorage` is mounted at `/data` and holds `/data/a.txt` ("alpha one"), `/data/b.md` ("alpha two alpha") and `/data/deep/c.md` ("alpha three"). `rows` is `glob("**/*", kind="file").observations`, which is five rows.
- **Four ranked files.** A kernel over one `InMemoryStorage` that holds `/top.txt` ("alpha alpha alpha alpha"), `/next.txt` ("alpha alpha alpha"), `/third.md` ("alpha" and then "filler" five times) and `/fourth.md` ("alpha" and then "filler" eight times). `rows` is `glob("/*").observations`.
- **Two canned mounts.** The `_two_mounts()` the file already has. `/low` answers `/l1` and `/l2` with `legs={"m": 1}`. `/high` answers `/h1` and `/h2`. `held` is four rows that carry a path only: `/low/l1.md`, `/low/l2.txt`, `/high/h1.txt` and `/high/h2.md`. A canned storage returns its two rows whatever it is sent, so these tests assert on what each storage received.
- **`_sent(storage)`.** A new helper beside `_limits`. It returns, for each recorded `search` call, the paths of the `observations` the storage received, as strings.

The tests, one line each. Every expected value below was printed by the design in a scratch run.

- On the two real mounts, `search("alpha", observations=rows, ext=("md",))` succeeds and its sorted paths are `/data/b.md`, `/data/deep/c.md`, `/y.md`.
- The same call with `ext=(".MD",)` returns the same three paths.
- With `ext_not=("md",)` the sorted paths are `/data/a.txt`, `/x.txt`.
- With `globs=("*.md",)`, and again with `globs=("*.{md,rst}",)`, the sorted paths are the three `.md` paths.
- With `globs=("/data/**",)` the sorted paths are `/data/a.txt`, `/data/b.md`, `/data/deep/c.md`. With `globs=("deep/*",)` the result is successful and empty.
- With `globs_not=("/data/**",)` the sorted paths are `/x.txt`, `/y.md`.
- With `globs=("/data/**",), ext_not=("txt",)` the sorted paths are `/data/b.md`, `/data/deep/c.md`.
- For the nine filter sets of the seven tests above, and for `ext=("rs",)`, ten in all, `set(search("alpha", observations=rows, limit=50, **filters).paths)` equals `set(grep("alpha", observations=rows, **filters).paths)`. This is one parametrized test.
- On the four ranked files, `search("alpha", observations=rows, limit=2)` returns `/top.txt`, `/next.txt` in that order, and `search("alpha", observations=rows, ext=("md",), limit=2)` returns `/third.md`, `/fourth.md` in that order.
- On the four ranked files, `search("alpha", observations=rows, ext=("md",), limit=2)` and `search("alpha", observations=[the two .md rows], limit=2)` return the same paths in the same order, the same scores, and the same `legs` extra.
- On the two canned mounts, `search("lease", observations=held, globs=("/low/**",), limit=3)` gives `_sent(low) == [["/l1.md", "/l2.txt"]]`, `_limits(low) == [3]`, `high.calls == []`, `result.paths == ("/low/l1", "/low/l2")`, scores `[0.2, 0.1]` and `_legs(result) == {"m": 1}`.
- On the two canned mounts, `search("lease", observations=held, ext=("md",), limit=3)` gives `_sent(low) == [["/l1.md"]]`, `_sent(high) == [["/h2.md"]]`, `_limits(low) == [9]`, `_limits(high) == [9]`, and `"merge" in _legs(result)`.
- In that call, the keywords each storage received are exactly `query`, `limit`, `observations` and `columns`.
- On the two canned mounts, `search("lease", observations=held, ext=("rs",))` gives `result.success is True`, `result.observations == []`, `result.errors == []`, `result.ops == ("search",)`, no `legs` in `result.model_extra`, and `low.calls == [] and high.calls == []`.
- With `held` as `/low/l1.md`, `/low/l2.txt`, `/low/l1.md`, `/low/a.md`, `search("lease", observations=held, ext=("md",))` gives `_sent(low) == [["/l1.md", "/l1.md", "/a.md"]]`.
- With `observations` as a generator that yields the four `held` rows, `search("lease", observations=..., ext=("md",), limit=3)` gives `_sent(low) == [["/l1.md"]]` and `_sent(high) == [["/h2.md"]]`.
- For `globs=("{a",)` and for `globs_not=("{a",)`, `search("lease", observations=held, ...)` fails with one error of kind `invalid`, whose message equals the message of the one error of `grep("lease", observations=held, ...)` with the same argument. `result.ops == ("search",)`, and no storage recorded a call. This is one parametrized test.
- After `close()`, `search("lease", observations=held, ext=("md",))` fails with `backend_unavailable`, and `search("lease", observations=held, globs=("{a",))` fails with `invalid`.
- `search("lease", observations="abc", ext=("md",))` fails with one `invalid` error whose message is `Invalid: observations must be an iterable of Observation, got str`. With `observations=[Observation(path=Path("/low/l1.md")), "x"]` the message is `Invalid: observations must be Observation instances, got str`. No storage recorded a call.
- With `chain_module.WALL_TIME_BUDGET` set to `-1.0` by `monkeypatch`, `search("lease", observations=held, globs=("*.md",))` gives `result.success is True`, no rows, no storage call, and exactly one error. Its kind is `truncated`, its severity is `warning`, and its message is `Truncated: at the wall-time budget; send fewer rows, or fewer globs`.
- With the same patch, `search("lease", observations=held, ext=("md",))` carries no error, and `_sent(low) == [["/l1.md"]]` and `_sent(high) == [["/h2.md"]]`.
- With `chain_module.judge_rows` replaced by a fake that judges the first row with the real function, answers `None` for every other row and reports `False`, and `held` as `/low/l1.md`, `/low/l3.md`, `/high/h2.md`, `search("lease", observations=held, globs=("*.md",), limit=3)` gives `_sent(low) == [["/l1.md"]]`, `_limits(low) == [3]`, `high.calls == []`, `result.success is True`, `result.paths == ("/low/l1", "/low/l2")`, and exactly one error, the `truncated` warning above.
- With `chain_module.judge_rows` wrapped by a counter, `search("lease", observations=held)` and `search("lease", observations=held, ext=("md",))` each make no call to it. The first sends every row and the second sends `/l1.md` and `/h2.md`.
- Marked `slow`. With the same counter and 10,000 rows `Observation(path=Path(f"/low/d{i % 100}/f{i}.{'md' if i % 2 else 'txt'}"))`, `search("lease", observations=big, globs=("*.md",), globs_not=("**/d7/**",), limit=3)` makes one call to `judge_rows`, with 10,000 rows, and `/low` receives 4,900 rows in one `search` call. `high.calls == []`.
- With a third mount at `/mute`, a `RecorderStorage(caps=frozenset({"read", "stat", "ls", "glob", "grep"}))`, and `held` plus the row `/mute/m.txt`, `search("lease", observations=..., ext=("txt",))` fails with one `unsupported` error whose path is `/mute`, and no storage recorded a `search` call.
- With the same three mounts and rows, `search("lease", observations=..., ext=("md",))` succeeds, `mute.calls == []`, `_sent(low) == [["/l1.md"]]` and `_sent(high) == [["/h2.md"]]`.
- On one `InMemoryStorage` that holds a directory `/dir` and the file `/dir/z.md` ("alpha delta"), with rows `Observation(path=Path("/dir"), kind="directory")`, `Observation(path=Path("/dir/ghost.md"))` and `Observation(path=Path("/dir/z.md"))`, `search("alpha", observations=..., globs_not=("*.txt",))` succeeds with no error and `result.paths == ("/dir/z.md",)`.
- On a kernel over one `InMemoryStorage` with a second mounted at `/data`, with the rows `Observation(path=Path(directory), kind="directory")` and `Observation(path=Path("/data/a.md"))`, for `directory` of `/data` and of `/`, `search("alpha", observations=..., ext_not=("txt",))` fails with one error of kind `invalid`. This pins the defect under "Found and left as it is", so the docstring cannot drift from it.
- On one `InMemoryStorage`, `/gone.md` ("alpha trashed") is written and deleted, and `held` is the one row `Observation(path=Path("/.vfs/trash/gone.md"))`. `search("alpha", observations=held)` returns one row. `search("alpha", observations=held, globs=("*.md",))` returns the same paths. `search("alpha", observations=held, globs_not=("*.md",))` succeeds with no row.
- On one `InMemoryStorage` that holds `/x.txt` and `/y.md`, with `/gone.md` written and deleted, and `held` as `/.vfs/trash/gone.md`, `/x.txt`, `/y.md`: `search("alpha", observations=held)` fails with one `invalid` error, `Invalid: a scope under '/.vfs/trash' cannot mix with live paths`. `search("alpha", observations=held, globs_not=("/.vfs/**",))` succeeds with sorted paths `/x.txt`, `/y.md`.
- On the two real mounts, `search("", observations=rows, ext=("rs",))` succeeds with no row and no error, and `search("", observations=rows)` fails with `invalid`.
- `admit_rows_in_hand` called directly with three rows and `ext=("md",)` returns the `.md` rows in the order given and no record.
- The existing tests of `glob` and `grep` over several mounts still pass after `_planned` becomes `planned_scope`. No test is added for the move, because it changes no behaviour.

`test_observations_across_mounts_merge_the_same_way` is kept as it is and still passes. It pins the call with no filter.

The new branches are each reached by a test above: the refused pattern, the closed kernel, the batch that is not rows, a deadline with a pattern and without one, and judging that did not finish.

## Scope

In: the branch of `search` for `observations` in `src/vfs/base.py`, the function `admit_rows_in_hand` and its constant in `src/vfs/chain.py`, the three moves of decision 3, the baseline entry of `base.py`, the docstring of `search`, one sentence in each of the module docstrings of `src/vfs/chain.py` and `src/vfs/fanout.py`, the tests above, and four tasks added to `agents/tasks.md`, one for each item under "Found and left as it is".

Depends on: `src/vfs/base.py` is also changed by two other drafts, `agents/2026-11-18-add-mount-takes-a-posture` and `agents/2026-11-18-a-call-that-reaches-several-mounts-bounds-each-mount`. All three share its fixed line baseline. Whichever lands second sets the baseline again from the file as it then stands.

Out: `search` without `observations`. `glob` and `grep`. `_route_fanout`, `_dispatch_grouped_observations` and `_rank_fanout`. How a storage ranks, and how the kernel merges. The storage protocol. `vfs.session` and `vfs.sync`.

## What the docs must say

The docstring of `search` in `src/vfs/base.py` changes. The sentence "The four file filters are not yet applied to those rows." is removed. The sentence about `observations` before it moves into a paragraph of its own. The first paragraph, the paragraph on mounts and the first three sentences of the last paragraph stay as they are. The text below is wrapped as the file wraps it.

The second paragraph ends at "checked as :meth:`glob` checks them."

A new paragraph follows the paragraph on mounts.

```
If ``observations`` is given, the search is limited to those rows. The four file filters are applied first, to
the path that each row carries, as :meth:`grep` applies them to rows. Only the rows that pass are sent on, each
to the mount that holds it, and a mount that holds none of them is not asked. The call then answers as it would
if only those rows had been given. A row that a filter drops is never ranked, never checked and never reported.
A row that passes is ranked only if its storage can rank it. An ordinary directory or a path that is not there
is left out without an error. The row of a mount point or of the root makes the call fail with ``invalid``.
A row that passes in a mount that cannot search refuses the call with ``unsupported``.
```

Three sentences are added to the end of the last paragraph.

```
A pattern in ``globs`` or ``globs_not`` that cannot be parsed is refused with ``invalid``. The
filtering of ``observations`` runs within a time budget. If it reaches the budget, the rows it has
not judged are left out, with one ``truncated`` warning.
```

One sentence is added to the end of the module docstring's last paragraph in `src/vfs/chain.py`.

```
``search`` calls it too, for the rows it is handed, before any storage ranks them.
```

The module docstring of `src/vfs/fanout.py` says "So the router runs it on a worker under a deadline". After the move `fanout.py` makes that hop itself. The sentence becomes one that says `planned_scope` runs the walk in place, or on a worker under a deadline, as `walks` says.

No page under `documentation/` describes `search` over rows in hand, so none changes. The reference page is built from the docstring. A docstring under `src/vfs/` changes, so `scripts/docs.sh check` is run beside `scripts/ci.sh`.

The task "`search` applies its file filters to rows in hand" in `agents/tasks.md` is removed when the work is done.

## Found and left as it is

Each was executed today, and none is touched by this spec. Each is a task in `agents/tasks.md`.

- **`search` without `observations` does not expand a brace pattern in the kernel.** `grep` does. With `/y.md` in the root storage, `grep("alpha", paths=("/y.md",), globs=("*.{md,rst}",))` returns `/y.md`, and `search` with the same arguments returns nothing. A glob that cannot be parsed is refused once by each mount, and the message can show a pattern the kernel rewrote, such as `'/**/{a'`, where `grep` refuses once with the pattern as written. The cause is the same missing call to `expand_channel`. The fix is to make that call before the two routes divide, as `grep` does. It changes the route without `observations`, so it is a piece of work of its own.
- **`grep` over a held row in the trash view matches nothing.** `read(observations=[/.vfs/trash/gone.md])` returns the row at `/gone.md`. `grep_rows_in_hand` looks the content up by the held path, finds none, and returns no row and no error. `search` returns the row. So the test that compares `search` with `grep` uses live rows only.
- **A row in hand at a mount point or at `/` makes `search` fail with `invalid`.** The row reaches its storage as the path `/`. The storage adds one escaped glob for each row, and `/` is not a glob it accepts. Executed on a kernel over one `InMemoryStorage` with a second mounted at `/data`. With the row `Observation(path=Path("/data"), kind="directory")`, `search("alpha", observations=...)` fails with one error, `Invalid: grep glob '/': empty component — every '/' must separate non-empty segments`. It fails the same way with `ext_not=("txt",)` and with `globs=("/data",)`, which the row passes, and with the row of `/` under `globs_not=("*.txt",)`. `grep` given the row of `/` succeeds. `glob("/*")` on that kernel returns the row `/data`, so a `search` over those rows fails with no filter, and with `ext_not=("txt",)` or `globs_not=("*.txt",)`. With `ext=("md",)` the filter drops the row and the call succeeds. The failure was there before this spec, and the filter hides it only when it drops the row. The fix is for the storage to leave out a row at its own root.
- **10,000 rows in hand take 8 to 9 seconds in one storage.** Measured once, by the clock, on one laptop, on SQLite in memory. The storage's own budget is 10 seconds. With 1,000 rows it took 0.7 seconds and with 2,000 it took 1.4. A storage adds one pattern for each row. The filter of this spec lowers the count and does not change the growth.

## Not checked

- The server engines. Every probe ran on the in-memory storage.
- The test suite and the gate. Neither was run. The design ran as a subclass in a scratch script, and not as an edit to `base.py`.
- The vector leg. It ran with the hash embedder that `InMemoryStorage` uses by default, and it returned no hits in every probe, so every answer came from words alone.
- A storage that wraps a remote kernel.
- `vfs.session` and `vfs.sync`. They were read and they pass the arguments through. They were not executed.
- Whether a path a row carries can ever fail the path check in `_dispatch_grouped_observations`. A `Path` is made canonical when it is built, and no failing row was looked for.
- A reranker other than the built-in `BM25Rerank`.

## One line

With `observations`, `search` judges the rows against its four file filters in the kernel, with the function `grep` and `glob` use, and then ranks only the rows that pass, as if no other row had been given.
