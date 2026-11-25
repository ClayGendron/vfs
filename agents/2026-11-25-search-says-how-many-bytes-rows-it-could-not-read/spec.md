# A search over a mount holding pending or unrendered bytes entries reports their count on its result, as the index pass does

A draft, written on 2026-11-25 against `dev` at `27f3d24d`. It is not reviewed, and nothing is built. No roadmap story names it; the map of this conversion leaves it unplaced, fitting gate `b` under domain E, whose goal ends "this domain is about defaults, truth-telling and pins" ([the roadmap](../../context/standards/roadmap.md), line 567). It is converted from [the binary bodies spec](../../context/specifications/archive/152-binary-bodies-and-text-renderings/spec.md), the open item at line 90 and item 3 of its progress note at line 188, through [the study of that source](../2026-11-25-the-backlog-converted/studies/051-162/152-binary-bodies-and-text-renderings.md), open choice 9, and [the reassessment](../2026-11-25-the-backlog-converted/reassessment/bodies-and-mounts.md) at unit 152-2. It rewrites the earlier draft of this file, written against `5b20fd4f`. It rests on slices A and B of the source, which are built, and on nothing that is not built.

## The outcome wanted

An agent, a developer or a pipeline that searches straight after writing PDFs, Office files or images gets, beside the ranked rows, one warning for each mount whose search scope holds bytes entries still waiting for a rendering. The warning says how many there are as a field, says whether that number is exact or a floor, is marked retryable, and names `refresh`. Once an index pass has rendered the rows, the warning is gone. A caller with partial rights is told only about rows it may read. A search whose scope holds no pending binary answers exactly as it does today, with the same statements.

## Builds on

- Slices A and B of [the binary bodies spec](../../context/specifications/archive/152-binary-bodies-and-text-renderings/spec.md), built on `dev`. They hold the bytes body, the `render_status` column, the render stage, its `unrendered` count and the retryable warning the pass adds when that count is above zero.
- Unit 152-1, built on `dev` as decision 5 of [the write preconditions spec](../2026-11-20-write-takes-preconditions-and-an-append/spec.md): a write of the bytes a row already holds is `unchanged` and keeps its rendering. It makes pending rows rarer. This spec does not need it.
- [The scan-tier rights spec](../../context/specifications/archive/2026-11-12-the-scan-tier-reveals-nothing-about-rows-a-caller-cannot-read.md), built: its decision 1 makes the scan tier's cut count only rows the caller may read, and its decision 5 keeps the scan tier's records' reason words and data keys.
- [The SQLite and Postgres spec](../2026-11-20-vfs-serves-sqlite-and-postgres-only/spec.md), built: the engines served are SQLite and Postgres, and an unknown dialect on the generic floor.
- On the open branch `origin/the-kernel-keeps-a-store-of-its-own`, the draft `agents/2026-11-24-the-vector-leg-leaves-the-database-storage/spec.md`, not reviewed and not built. Its decision 1 reads "The leg becomes a module of its own": the vector leg's notes leave `backend.py` for a new `vector_leg.py`. This spec edits neither file and shares no file with that draft, so either may land first. If that draft lands first, the precedent cited in decision 6 below moves from `backend.py` to `vector_leg.py` and nothing else changes.
- The vid branches (`origin/every-row-carries-a-vid` and the four in its line) grow `search.py` from 979 to 988 lines (EXECUTED, `git show <branch>:<path> | wc -l` on two of them). Decision 10's line budget fits under the ceiling in either order.

## Terms

- **Pending**: a bytes entry whose `render_status` is `pending`. It has been written, and no render stage has reached it yet.
- **Unrendered**: the index pass's word for the count of live pending rows. This spec uses the word for the same rows and for nothing else.
- **Admitted rows**: the scan tier's nominees that passed the call's gates. Every admitted row is inside the search's scope and readable by the caller.
- **Floor**: a count known to be no greater than the true count, because the scan that produced it stopped early.

## What the code does today

Every fact is at `27f3d24d`.

- A write of bytes stores the row with `encoded` false, `indexable` false and `render_status` `pending` (READ, `src/vfs/storage/backends/database/writes.py:1328-1331`, and `encoded_at_creation` at `src/vfs/models/entry.py:46-54`). The row has no content row until a pass renders it, so neither leg of `search` and not the overlay has text for it.
- The pass counts the live pending bytes rows (`count_unrendered`, READ, `src/vfs/storage/backends/database/render.py:395-400`), reports the count as `unrendered` in its `rendering` extra, and adds a record of kind `vfs.unavailable`, severity `warning`, retryable, when the count is above zero (READ, `src/vfs/storage/backends/database/maintenance.py:346-354` for `rebuild`, `:599-603` for `refresh`). `read` of a pending binary adds the same kind, severity and retry flag per row (READ, `src/vfs/storage/backends/database/reads.py:958-959`).
- `refresh` renders exactly the pending rows: without `regenerate` the render selection reads `render_status = 'pending'` alone (READ, `render.py:166-176`; called with `regenerate=False` at `maintenance.py:571`).
- A search says nothing of pending rows. EXECUTED (scratch probe on an indexed in-memory store, a PDF and a PNG written as bytes, `storage.search(query="lantern")`): the result is successful, lists the one text file, and carries an empty error list and the extras `lexical_stats` and `legs`. `grep -n unrendered` finds nothing in `search.py` or `grep.py` (EXECUTED).
- The search already reads every pending binary in its scope. The scan tier's nominee fetch selects content-kind rows that are `NOT encoded` (READ, `src/vfs/storage/backends/database/scope.py:323-327`), under the caller's view (`:369`), and the search keeps the rows its gates admit (READ, `src/vfs/storage/backends/database/search.py:435`). EXECUTED (same probe, a spy on `search._overlay`): both pending binaries are among the admitted rows, each with `render_status` `pending`.
- Under a projection the admitted rows carry no `render_status`. The fetch selects the caller's mask plus `FETCH_RIDE` (READ, `scope.py:70`, `:327`); `render_status` is in the default mask (READ, `reads.py:102`) and not in the ride. EXECUTED (same probe with `columns=frozenset({"path"})`): the admitted rows hold no `render_status` key.
- A search of the trash view admits tombstoned rows. EXECUTED (a pending PDF deleted, then `search(globs=("/.vfs/trash/**",))` with the spy): the tombstoned row is admitted with `render_status` still `pending`. No pass renders a tombstoned row: both render reads require `deleted_at IS NULL` (READ, `render.py:179`, `:399`).
- The facade keeps records and drops a storage's extras. EXECUTED (a scratch wrapper of `search_rows` that adds one record; `AsyncVirtualFileSystem` with two `InMemoryStorage` mounts, and with one): every mount's record reaches the caller, each with its mount as `source`, and the facade's extras are `legs` alone. READ: `_rank_fanout` restores `legs` only (`src/vfs/base.py:3003-3018`).
- The search's statement count does not depend on pending rows. EXECUTED (statements recorded on the second of two identical searches, the planner-statistics step left out): 13 statements over a store holding one pending PDF, 200 pending PDFs, or one dirty text file in their place.
- `search.py` holds 979 lines against a ceiling of 1,000 (EXECUTED, `wc -l`; READ, `tests/lint/test_code_shape.py:76`). `backend.py` is held at exactly 1,509 and `base.py` at 3,090 by the line allowlist (READ, `tests/lint/allowlist.py:27-28`), so neither may grow. `render.py` holds 427 lines.

## The problem

A caller that searches right after an upload gets a clean, successful answer that silently leaves out every binary written since the last pass. It cannot tell an answer over every file in its scope from one with holes. The pass and `read` already say it; `search` is the one verb that reads text across many entries and stays silent. The constitution fails a pattern that "forces an agent to guess, retry blindly, or parse prose to learn state" ([the constitution](../../context/standards/constitution.md), line 92). At the reference deployment the hole is common, not rare: a partial index pass runs every 15 minutes, so a binary written in working hours waits up to 15 minutes, and overnight the 10,000-file batches keep thousands of rows pending between passes.

## Decisions

### 1. A search says on its own result how many bytes entries in its scope still await a rendering

The count rides the result the search already returns, never a second call. Reason: the constitution's Article 2, as quoted under The problem. Precedent: the index pass's `unrendered` count and its retryable warning (`maintenance.py:346-354`, `:599-603`), and the study's lean on open choice 9, which holds on `dev`.

### 2. Only pending rows are counted

The count is of admitted rows whose `render_status` is `pending`, the meaning `unrendered` has in the pass. A row a renderer settled without text (`empty`, `unsupported`, `unavailable`, `encrypted`, `corrupt`, `failed`) is not counted: a retry does not change it, and it states its own status on `ls`, `stat` and `read`. A key for those can be added to the record later without changing this one; Choices to confirm, item 2, holds the open side.

### 3. The count is of the search's own scope as the caller may read it, never of the whole mount

The rows counted are the admitted rows: inside the call's `globs`, `ext` and scope channels, past its exclusions, and inside the caller's view. A mount-wide count would tell a caller how many binaries sit in subtrees it cannot read, and it would move when a hidden row is written. This departs from the pass's population and from the words "over a mount" in the unit's title. Reason: every verb call is judged against row-level grants (AGENTS.md, the reference deployment's Rights row). Precedent: decision 1 of the scan-tier rights spec, which already makes the nominee fetch exact under the view.

### 4. The count is read off the admitted rows in memory; no statement is added

A pending bytes row is `NOT encoded`, so the nominee fetch already returns it. The count is one pass over the admitted list. A separate counting statement is rejected: it adds a round trip to every search, and it would spell the scope and the rights clauses a second time, a second place for a leak. `count_unrendered` stays the pass's and is not called by a search. Reason: a read costs in proportion to what it returns (AGENTS.md, the per-verb-call multiplier).

### 5. `render_status` rides the search's nominee fetch whatever the caller projected, and the caller's mask does not change

`search_rows` passes `fetched | {"render_status"}` as the `fetched` argument of `entries_for_scan`. Under the default mask the statement is unchanged; under a narrower projection it gains one select-list column. The observations are still built from the caller's own `fetched`, through `projected` and `mask` (`search.py:467-468`, `_observe` at `:930`), so no row gains a field the caller did not ask for. `FETCH_RIDE` is not widened, so grep's statements and the plan store's recorded grep statements (`tests/support/plan_store.py:589-601`) are untouched. Reason: the count must not depend on the columns asked for, and a select-list column spends no bind parameter.

### 6. The count rides one record per mount, and the facade is not changed

The pass carries its counts in a `rendering` extra, but the facade drops every storage extra except `legs`, so an extra would reach a caller of `storage.search` and never a caller of `vfs.search`. A record reaches both, stamped with its mount as `source`, and two mounts' records stay two facts because their sources differ. A search across mounts carries one record per mount with pending rows in scope; no sum is computed. This departs from the pass in the carrier, and the departure is named here. Precedent: the facade fold as executed under What the code does today, and the search's other notes, which are records with a `reason` data key (`backend.py:628`, `:642`, `:656`; in `vector_leg.py` once the vector-leg draft lands).

### 7. The record is `vfs.unavailable`, severity `warning`, retryable, with no path

It is built with `classified(ErrorKind.unavailable, severity=Severity.warning, retryable=True, detail=..., data=...)` and no `path`, so its locus is the mount. `success` is unaffected. The warning severity is defined as "loss or caveat on record — rows present are trustworthy" (`src/vfs/results/kinds.py:116`), which is this case, and it is what the pass and `read` say of the same rows. Choices to confirm, item 1, holds the open side.

### 8. The record's facts are three data keys, and its detail names `refresh`

`data` is exactly `{"reason": "pending_rendering", "unrendered": <count>, "exact": <bool>}`. `reason` is the discriminator the search's other notes carry; `unrendered` is the pass's key with the pass's meaning; `exact` is decision 9's. No `leg` key is carried, because a pending row is missing from every leg, not from one. The detail is `"<count> binaries in scope are still pending a rendering and were not searched; run refresh"`, prefixed with `"at least "` when `exact` is false. `refresh` is named because it is the pass that renders exactly the pending rows (`render.py:166-176`). The words `read` uses ("run rebuild", `reads.py:958`) are left as they are. Reason: a record's facts are structured fields, never prose (`src/vfs/results/envelope.py:250`, "a kind, a locus and fields — never prose").

### 9. The count is exact only when the scan was whole; otherwise it is a floor; a search that never ran the scan tier adds no record

`exact` is `completed and not nominees.overflow and not deadline.expired()`, taken right after the gate judgement (`search.py:432`) and before `_overlay` reassigns `completed` (`:436`). The three terms are the three ways the scan tier stops short: the fetch cut at `SCAN_TIER_BUDGET`, a judgement left unfinished, and a fetch that stopped between statements at the wall (`scope.py:361`), which a judgement with no pattern does not notice because it is complete whatever the clock reads (`src/vfs/offload.py:203-206`). No record is added when the count is zero, even on a cut scan, and none when the scan tier did not run (the store held no row awaiting the index, or the wall had passed before it): the wall and truncation records already on the result say what was cut. Under a partial view the cut counts only readable rows, so `exact` false says nothing about rows the caller cannot read.

### 10. The record is built in `render.py` and attached in `search.py`; `backend.py` and `base.py` are not edited

`render.py` gains one public function, `unrendered_records(rows: Sequence[Mapping[str, Any]], *, exact: bool) -> list[ResultError]`, in a banner group of its own, "What a search says of the rows still pending", between the landing group and the internal helpers. It counts the rows whose `render_status` equals `"pending"` and returns an empty list for zero, else one record by decisions 7 and 8. `render.py` owns the word `unrendered` and the predicate `render_status == "pending"`, so the pass and the search cannot drift on what is counted. `search_rows` calls it and puts its records after the truncation records (`search.py:475-479`), beside the search's own records, as the reassessment asks. `search.py` grows by at most 8 lines: to at most 987 on `dev` and 996 on the vid branches. `backend.py` and `base.py`, held at their exact counts, are not touched. Reason: the line allowlist (`tests/lint/allowlist.py:27-28`) and AGENTS.md's Code smells on duplicated code.

### 11. A search of the trash view adds no record

When the call's scope is the trash view (`gated.trashed`), no count is taken. The admitted rows there are tombstoned, no pass renders a tombstoned row, so "run refresh" would be false and the retry flag would promise what cannot happen. The pass's `unrendered` counts live rows only, and the search keeps that population. Reason: the record's retry flag must be true of every row it counts.

### 12. Each new test names the mutation it guards in its docstring, and the mutant ledger gains no row

The testing standard asks each pin to record its mutation in its docstring (`context/standards/testing.md:48-53`). The ledger holds bugs that once survived the whole suite (`context/standards/mutant-ledger.md:3`); a new behaviour's pins are not that. Each mutation under Tests is applied under AGENTS.md's safe-restore rule and its test seen failing. Precedent: decision 13 of [the router admission spec](../2026-11-25-a-router-is-refused-as-a-mount-and-a-dot-dot-path-meets-the-siblings-gate/spec.md) in this conversion.

## Cost

- **Statements: none added.** The multiplier is per verb call: about 150,000 calls a day with `search` under a tenth, so under 15,000 searches a day and under 2 a second at the 20-a-second peak. Each adds zero statements, which a counted test pins (Tests, item 5).
- **Bind parameters: none added.** The ride is a select-list column. The chunk sizes the nominee fetch is cut by (`membership_budget`, `arm_budget`, `chunked`) are computed from its predicates and the view's packed groups alone (`scope.py:328-350`), so every statement keeps its width under SQLite's and Postgres's budgets as `DialectProfile` declares them.
- **Bytes on the wire: one column, only under a projection.** `render_status` is `String(16)` (`src/vfs/models/rows.py:411`). Each scan-tier statement returns at most `SCAN_TIER_BUDGET + 1` rows (`scope.py:78`, `:363`), so the column adds at most about 400 KB to a statement that already carries `path`, `name`, `size_bytes` and the rights fields for the same rows. Under the default mask the column is already fetched.
- **One loop in memory.** One comparison per admitted row, bounded by the shared declared budget `SCAN_TIER_BUDGET`, on rows already held, beside the loop that builds the admitted list. No budget of this spec's own is declared.
- **Per file write, per index visit, per batch, per corpus: nothing.** No write path, pass or builder changes.
- **Per lock: nothing.** The change issues no statement, takes no lock and waits on none. The search stays SELECTs in one read session, and a read still never waits on a writer.
- **Plans.** The nominee fetch already selects columns outside every index, so one more column cannot turn an index-only plan into a table read (INFERRED, `scope.py:327`, `rows.py:429-449`).

## Left as it is

- Bytes rows a renderer settled without text stay in the scan tier for good, scanned and never scored (EXECUTED: after `refresh`, an `unsupported` PNG is still admitted). That is the standing decision 17 of the scan-tier rights spec records for bodies never encoded, and this spec does not change it.
- The facade, the storage protocol, `entries_for_scan`, `FETCH_RIDE` and `count_unrendered`.

## Tests

Written first and seen failing, counts and states, never clocks. Each docstring names its mutation (decision 12). Bytes are written with `Entry(path=..., data=...)` and a body no renderer claims, so no test depends on which renderers are installed or on unit 152-3; where a settled status is asserted, the test asserts the row left `pending`.

1. `tests/support/partial_callers.py` gains `pending_store(readable: int, hidden: int) -> InMemoryStorage`, beside `partial_store`: posture `none`, `bob` granted `read` on `/pub`, one indexed text file, then `readable` pending binaries under `/pub` and `hidden` under `/hr`, each with distinct bytes. The module docstring gains one sentence.
2. `tests/storage/database/test_render.py::TestUnrenderedRecords::test_only_pending_rows_are_counted`: given one row for each render status and one whose status is null, the function returns one record with `unrendered` 1; without the pending row it returns an empty list. Mutation: `is not None` in place of `== "pending"`.
3. `tests/storage/database/test_render.py::TestUnrenderedRecords::test_a_floor_is_marked_on_the_record`: with `exact=False` the record's `data` holds `exact` false and its detail begins "at least"; kind, severity and retry flag are decision 7's. Mutation: `exact` dropped from `data`.
4. `tests/storage/database/test_search.py::TestUnrendered::test_pending_binaries_in_scope_add_one_record_with_their_count`: over an indexed store with two pending binaries, the search is successful, lists the rows it listed before they were written, and carries exactly one record whose kind, severity and retry flag are `vfs.unavailable`, `warning` and true and whose `data` equals `{"reason": "pending_rendering", "unrendered": 2, "exact": True}`. Mutation: the records left out of the error list.
5. `tests/storage/database/test_search.py::TestUnrendered::test_the_count_adds_no_statement`: the same query issues an equal number of statements, with exactly one nominee fetch, over a store holding one pending binary, 200 pending binaries, and one dirty text file in their place, statistics statements left out by `tests/support/statements.py::is_statistics_statement`. Mutation: a `count_unrendered` call added to the search.
6. `tests/storage/database/test_search.py::TestUnrendered::test_the_count_follows_the_scope_and_its_exclusions`: one pending binary under `/docs` and two under `/src`; `globs=("docs/**",)` reports 1, `globs_not=("docs/**",)` reports 2, and a scope holding none carries no record of that reason. Mutation: the nominee rows counted in place of the admitted rows.
7. `tests/storage/database/test_search.py::TestUnrendered::test_a_projected_search_counts_and_keeps_its_mask`: with `columns=frozenset({"path"})` over two pending binaries the record says 2, and no observation's `populated` holds `render_status`. Mutation: the ride left out.
8. `tests/storage/database/test_search.py::TestUnrendered::test_settled_binaries_and_text_stores_carry_no_record`: a text-only store, and a store whose two binaries `refresh` has settled (each asserted to have left `pending`), carry no record of that reason. Mutation: the predicate widened to every bytes row.
9. `tests/storage/database/test_search.py::TestUnrendered::test_a_cut_scan_reports_a_floor`: with `search_module.SCAN_TIER_BUDGET` patched to 2 and three pending binaries, the record holds `unrendered` 2 and `exact` false, beside the `overlay budget` truncation record. Mutation: `exact` fixed at true.
10. `tests/storage/database/test_search.py::TestUnrendered::test_an_unfinished_gate_judgement_reports_a_floor`: with `search_module.judge_rows` patched to report itself unfinished, a scoped search carries the record with `exact` false. Mutation: the judgement term dropped.
11. `tests/storage/database/test_search.py::TestUnrendered::test_a_scan_that_ends_past_the_wall_reports_a_floor`: `deadline_module.monotonic` is a patched counter moved past the wall inside a wrapper of `search_module.entries_for_scan`; an unscoped search carries the record with `exact` false. Mutation: the wall term dropped.
12. `tests/storage/database/test_search.py::TestUnrendered::test_a_search_that_skips_the_scan_tier_reports_no_count`: with the patched clock past the wall before the scan tier, over a store with a pending binary, the result carries the wall record and no record of that reason. Mutation: the record built before the scan-tier guard.
13. Leak test, `tests/storage/database/test_search.py::TestUnrendered::test_hidden_pending_binaries_never_reach_a_count`: with `search_module.SCAN_TIER_BUDGET` patched to 3, `pending_store(2, 0)` and `pending_store(2, 5)` answer `bob`'s search with equal paths, scores and records, and `bob`'s record holds `unrendered` 2 and `exact` true in both; the system actor's search of the second store holds `unrendered` 3 and `exact` false, because the five `/hr` rows sort first. Mutation: the helper fed the nominees of a whole-mount fetch.
14. `tests/storage/database/test_trash.py::TestTrashView::test_a_trash_view_search_reports_no_pending_count`: after a pending binary is deleted, `search(globs=("/.vfs/trash/**",))` carries no record of that reason. Mutation: the trash guard removed.
15. `tests/base/test_search_merge.py::test_each_mounts_pending_binaries_are_reported_under_its_own_source`: a facade search across two `InMemoryStorage` mounts, `/a` with one pending binary and `/b` with two, carries two records of that reason whose `source` and `unrendered` are (`/a`, 1) and (`/b`, 2), and its extras hold `legs` alone.
16. The storage contract, on every leg: `tests/support/storage_contract.py::StorageContract::test_search_counts_the_pending_binaries_in_its_scope_until_a_pass_settles_them`. Where unit 179-1 has landed first, each conformance row named here is a method of the mixin that unit's decision 18 names for it, `QuerySearchRows` and `RightsViewRows`, under the same name and node id, no leg's class line is edited, and `tests/fixtures/conformance/rows.txt` is not edited (its decision 16). After two binaries are written the record says 2 with `exact` true, the same holds under `columns=frozenset({"path"})`, and after `rebuild` there is no record of that reason. Nodes: `tests/storage/test_conformance.py::TestMemoryConformance::<name>`, `::TestSqliteConformance::<name>` and `::TestPostgresConformance::<name>`, the Postgres leg run with the `db_test` skill.
17. Leak test, on every leg: `tests/support/grants_contract.py::GrantsContract::test_hidden_pending_binaries_never_reach_a_search_count`, under `@needs("grant", "search", "write")`. In the grants world, after pending binaries are written under `/pub` and `/hr` as the system actor, `bob`'s record counts the `/pub` ones only, and writing three more under `/hr` leaves every field of `bob`'s answer equal. Nodes: the same name under `TestMemoryConformance`, `TestSqliteConformance` and `TestPostgresConformance`.
18. The line ceiling: the existing `tests/lint/test_code_shape.py::test_a_listed_module_never_grows_and_an_unlisted_one_stays_under_the_ceiling` passes with `search.py` at most 987 lines and `backend.py` and `base.py` at their listed counts.

## Scope

In: `src/vfs/storage/backends/database/render.py` (the function, its banner group, the imports from `vfs.results`, one sentence in the module docstring); `src/vfs/storage/backends/database/search.py` (one import, the ride, the count after the judgement, the records in the error list, one sentence each in the module docstring's freshness paragraph and in `search_rows`'s docstring); `tests/support/partial_callers.py`, `tests/storage/database/test_render.py`, `tests/storage/database/test_search.py`, `tests/storage/database/test_trash.py`, `tests/base/test_search_merge.py`, `tests/support/storage_contract.py`, `tests/support/grants_contract.py`. Gates: `scripts/ci.sh`, `scripts/docs.sh check` (docstrings under `src/vfs/` change), and the Postgres leg.

Out:

- A count of the rows settled without text: decision 2, and Choices to confirm, item 2.
- The same count on `grep`, which skips the same rows through the same scan tier: no unit of [the map](../2026-11-25-the-backlog-converted/units.md) carries it and the source names the ranked verb only; `unrendered_records` takes any admitted rows, so a later spec adds it with one call.
- A `rendering` extra on a search result, and a sum across mounts in the facade: decision 6.
- Any edit to `src/vfs/base.py`, `backend.py`, the storage protocol, `FETCH_RIDE`, `entries_for_scan` or `count_unrendered`.
- The words `read` uses for a pending binary: decision 8.
- Making pending rows rarer: [the render-at-write unit](../2026-11-25-a-small-binary-write-renders-its-own-bytes-before-it-returns/spec.md).
- The docs site's account of the record, the render-status page and the glossary: [the documentation unit](../2026-11-25-binary-bodies-are-documented-on-the-docs-site/spec.md).
- How a bytes row prints in a rendered result: [the placeholder unit](../2026-11-25-a-bytes-row-renders-a-placeholder-and-leaves-the-payload-only-when-asked/spec.md).

## What the docs must say

- `search.py`'s module docstring, in its freshness paragraph: pending binaries among the admitted rows are counted on one retryable record and never scored.
- `search_rows`'s docstring: the record, its three data keys, and that it counts only admitted rows.
- `unrendered_records`'s docstring: the three data keys, the meaning of `exact`, and that its caller hands it only rows the caller of the verb may read.
- `render.py`'s module docstring: one sentence naming the search's use of the count's predicate.
- The caller-facing pages are the documentation unit's.

## Not checked

- No Postgres leg was run. That a pending bytes row is admitted on Postgres as on SQLite is inferred from the shared predicate and the conformance rows that already serve the dirty set there.
- The line counts after the edit are estimated from the decisions, not measured on an edited file.
- Whether a pending row can ever be `encoded`: no write path read sets it so, but every path that resets `render_status` was not traced.
- The facade probe wrapped `search_rows` in a scratch script; the real record was not built and run through the facade.
- The vid branches' `search.py` was counted by lines only; their edits beside the nominee fetch were read on one branch, `origin/every-row-carries-a-vid`, and found disjoint from this spec's.

## Choices to confirm

1. **The record's severity: warning or info.** The study marks it as needing a ruling. Options: (a) `warning`, as the pass and `read` say of the same rows; (b) `info`, as the search's "no embedding provider" note is (`backend.py:624-629`). Side taken: (a), because it is what vfs already says of these rows at three sites, and the cost of a frequent warning is one record per mount per call, never one per row. Either is one argument at one call site to reverse before the beta.
2. **Which rows without text are counted.** Options: (a) pending rows only, under `unrendered`; (b) pending rows plus the settled states that carry no text, each under the pass's own key (`empty`, `unsupported`, `failed`); (c) one merged count of every bytes row without text. Side taken: (a), because (b) is reachable from it by adding keys, an addition the beta allows (the roadmap's decision D2, line 17), while (c) would give `unrendered` a second meaning.

## One line

A search counts the pending bytes entries among the rows its scan tier already read and admitted, and says the number on one retryable warning per mount, exact or marked as a floor, with no statement more and no row counted that the caller cannot read.
