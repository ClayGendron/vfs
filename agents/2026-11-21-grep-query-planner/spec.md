# Database grep plans from what it can count before it fetches a body

A draft, written on 2026-11-21 from `research.md` and revised after each of three adversarial review rounds (`reviews/round-1.md` to `round-3.md`). Nothing is built.

## The outcome wanted

A database `grep` costs in proportion to what it must read to answer. A grep over a small scope reads that scope and nothing near it. A corpus-wide grep fetches the bodies the index cannot rule out and no others, and on a remote engine it moves over the wire only the bodies that might match. The plan is chosen from facts read before any body is fetched, and every plan returns the same rows.

## Builds on

Two fixes, each with its own spec, land before this one:

- `agents/2026-11-21-grep-reads-a-pattern-as-its-matcher-does/spec.md`: the gram plan and the index fold read the pattern as the matcher does. Decision 0 below points to it.
- `agents/2026-11-21-a-scoped-grep-finds-its-root-by-path/spec.md`: a literal admission arm resolves by path equality. Decision 1 below points to it.

The in-hand plan reuses `grep` over rows in hand, which `agents/2026-11-21-search-and-grep-agree-over-rows-in-hand/spec.md` also changes. The benchmark that started this work is `agents/2026-11-21-linux-grep-benchmark/`.

## The problem

1. **A scoped grep pays for its root's parent subtree** (R1). The root's own literal reaches the storage as an admission arm bounded only by its parent's segments. A grep over a 30-file directory builds a 40,262-id allow-list and costs 230 ms. The same scope spelled as a glob builds 38 ids and costs 13 ms.
2. **The defer choice prices the allow-list after building it** (`_ladder_defers` in `grep.py`), and it cannot see that the allow-list itself was the cost.
3. **No plan reads a small scope directly.** In hand beats the ladder up to a few hundred files (R3), and it spends 5 statements where the ladder spends 16 to 24 (round 1). Only a caller who passes `observations` gets it.
4. **The ladder nominates a loose superset, and every candidate's body is fetched** (R5). On a remote engine each wasted candidate is a body moved over the wire. So is the unindexed tail, on every call (R6).
5. **The gram plan parses the pattern with a different parser than the matcher** (round 2, H1). The language gate and `build_code_gram_query` read the pattern with Python's `sre`. The matcher is the regex crate. The gate admits syntax the two read differently: `\<`, `\>`, `\b{start}`, POSIX classes such as `[[:alpha:]]`, and nested classes. Today's database grep loses rows silently. Under `/fs`, `[[:alpha:]]_count` returns 0 files where `rg` returns 751, and `\<kmalloc` returns 6 where `rg` returns 421. No warning reaches the caller. This predates the planner. Once plans differ in whether they read postings at all, it also makes a pattern's rows depend on which plan its scope routes to.

## Decisions

0. **One parser and one fold: the gram plan, the index fold and the literal extraction read the pattern as the matcher does.** Specified in `agents/2026-11-21-grep-reads-a-pattern-as-its-matcher-does/spec.md`, which lands first. This spec relies on it in two places. Every plan depends on the ladder's candidates being a superset of the matcher's matches, which today holds only for patterns both parsers read alike and both fold tables fold alike. And decision 7's extraction walks the same HIR that spec's gram plan walks.

1. **A fully literal admission arm resolves by path equality.** Specified in `agents/2026-11-21-a-scoped-grep-finds-its-root-by-path/spec.md`, which lands first. It removes R1's parent-subtree cost. With it in place, the ladder's local floor for a small scope falls to the 6 to 7.5 ms decision 6 uses.

2. **A root scope is bounded by its path range.** When the scope's arms are exactly `**`, its rows are `path > :root || '/' AND path < :root || '0'`, together with `path = :root`. That is the range spelling `ranges.py` already uses for scopes, and the one the in-flight spec "Postgres reads a subtree by its range" makes the rule (research R2). It is exact under `COLLATE "C"` on Postgres and `BINARY` on SQLite, because `/` sorts just before `0`. Roots are first reduced to their maximal elements, so a root beneath another root is dropped. Segment allow-lists remain for scopes with other arms, the only scopes the range cannot express.

3. **The plan begins with a bounded probe on the path index alone.** A root scope's probe reads the first `T + 1` entries of the union of the roots' ranges, plus each root's own row, judging nothing but the range. The limit is one, over every root, never one per root: round 3 measured 85,084 rows read over 24 roots where 25,001 decide. One statement per chunk of roots selects `id, path`. On SQLite it is covered by `ix_vfs_entries_path`. On Postgres the index is `(path)` alone, so each row returned costs one heap visit, which is still at most `T + 1`. If more than T come back, the answer is "more than T". Otherwise the at most T rows are fetched by id, and kind, the tombstone side, the meta exclusion, the view and the gates are judged on them alone. *Why:* round 1 measured the probe visiting every row of the range when a residual term rejected them (the trash side, a narrow view: 39,794 visits to return 0 or 10). On the index alone, the visits are bounded by T whatever the view, the tombstones or the mix of kinds. Hidden, dead and directory rows count toward T, so a scope can be routed to a ladder plan sooner than its visible files alone would route it. That costs time and never rows. A scope with other arms takes the segment table's grouped count, which already exists, as its upper bound, and the in-hand plan is chosen only when that bound is at most T.

4. **The refusal gate runs first, unchanged.** A pattern with no indexable literal is refused (`unindexable_pattern`) without `allow_scan`, whatever the scope's size, exactly as today. The refusal never depends on the probe. With `allow_scan` or `invert_match`, a probe of at most T rows is served in hand, and a larger scope runs today's scan tier.

5. **Four plans, every one lawful.** Let `n` be the scope's size, from the probe while it is under T. Above T, the ladder's intersection runs first, with no allow-list, and gives `U`, the uncapped candidate count. It costs about 3 ms (R4). Only then does a second bounded probe run: decision 3's statement with limit `min(U, SCAN_TIER_BUDGET) + 1`. It tells whether `n ≤ U` and whether `n ≤ SCAN_TIER_BUDGET`, and it visits at most `min(U, SCAN_TIER_BUDGET) + 1` rows. *Why that order:* round 2 measured the probe reading 22,197 rows before a `U` of 16 was known. With `U` first, the probe never reads more rows than the plan it chooses would resolve. *The order is itself priced.* Reading `U` fetches the chosen grams' posting blobs, which grow with the corpus: 10 KB to 246 KB on the sandbox's 94,000 files, about 26 MB at ten million by extrapolation (round 3, M2). The posting metadata's `byte_size` is exact and is read in one statement before any blob is fetched, as `_ladder_defers` already reads it. So the planner reads the metadata first. When the chosen blobs cost more than a probe of `SCAN_TIER_BUDGET + 1` rows, the probe runs first and `U` is read only if the probe does not settle the plan. Neither step is then larger than the cheaper of the two. Blob fetching keeps today's `POSTING_BYTE_BUDGET`, with the rarest gram of each group exempt.
   - *In hand* (`n ≤ T`, and decision 6 prices it lower): the probe's admitted rows are the candidate set. Their bodies are fetched in `CONTENT_BYTE_BUDGET` batches and verified. No posting list is read. Unencoded rows are among the probe's rows, so the scan side is covered and nothing is unioned.
   - *Ladder, allow-listed by range* (`n ≤ U` and `n ≤ SCAN_TIER_BUDGET`): the second probe's ids are the allow-list, and the kernel meets them before the cap. Ids resolved: at most `n`.
   - *Ladder, range-scoped* (`U < n` and `U ≤ SCAN_TIER_BUDGET`): the candidate entry fetch carries the range as pushdown, and out-of-scope candidates are dropped in SQL before any body. Ids resolved: `U`, at most the budget.
   - *Ladder, allow-listed in full* (`n > SCAN_TIER_BUDGET` and `U > SCAN_TIER_BUDGET`): the allow-list is built whole and met before the cap, as today. This is the one statement the design adds that is bounded by neither a budget nor what it returns. It grows with `n`: round 1 measured 78,793 ids in one statement over seven roots, and at the reference deployment a top-level directory's share is millions. It is today's profile, which `pathterms.py` acknowledges, at a lower cost per id (0.34 µs by range against a segment join). Its direction is the same one: move the meet into SQL (a join to a temporary table or an array bind by engine), so that no id set crosses into Python.

   With no truncation, every plan returns the rows the pattern matches in the scope the caller may see. Each plan's candidate set is a superset of those rows, and all of them verify with one matcher over the same bodies. Round 1 checked in hand and the range-scoped ladder against today's code on every pair where `U ≤ 25,000`, and found the rows identical. It also confirmed that the range-scoped ladder truncates wrongly when `U` exceeds the budget, which is why that case takes the full allow-list.

6. **In hand is chosen when its price is no more than the ladder's floor.** With the probe's `n ≤ T` rows, `B` bytes of them encoded and `B_u` unencoded: in hand when `s_h·c_rt + n·c_row + (B + B_u)·c_byte ≤ s_l·c_rt + F_l + B_u·c_byte`. Here `s_h` and `s_l` are the two plans' statement counts (5 and about 19 measured), `c_rt` is the storage's round trip, and `c_row` and `c_byte` are fetch-and-verify per row and per body byte. `F_l` is the ladder's local work for a one-candidate answer plus its chosen blobs' `byte_size` at the per-posting-byte rate, read from the metadata before the choice. The unindexed tail in the scope is priced on both sides, because the ladder's scan side fetches it too (round 2: 143 MB of the 171 MB in hand would fetch, under one scope). The decision uses the probe's exact `B` and `B_u`, which it reads with the ids. `T` only bounds the probe's limit. It is the `n` at which in hand's price, at the storage's running mean body size, reaches the ladder's floor, capped at `SCAN_TIER_BUDGET`. The figures are measured, never declared. With decisions 1 and 2 in place, the ladder's local floor is 6 to 7.5 ms, and in hand wins below about 100 to 140 files on SQLite (round 2, measured at load 2.0). The pre-fix figure of 150 to 250 is wrong. A remote round trip raises the ladder's floor by about 14 round trips and in hand's per-file cost by the transfer of a body, so the remote figure must be measured on the Docker leg, not projected. *Why not the posting metadata:* the rarest gram's `doc_count` misestimates the candidate count by 2× to 10× (R4). The exact `U` costs about 3 ms and is read only when a ladder plan runs.

7. **On an engine where transfer dominates, bodies are tested for a required literal before they leave the database.** The literal set comes from its own extraction, not from the gram plan. It walks the matcher's own parsed pattern (the regex-syntax HIR in `crates/vfs-core`), where case-insensitivity, from the call's mode or from an inline `(?i)`, is already lowered to classes. A literal joins a run only as a case-exact literal node. Anything else ends the run. A concatenation requires its best run or mandatory sub-result, an alternation the union of its branches' requirements (or nothing, if any branch requires nothing), and a repeat with a minimum of at least one passes its body's requirement through. Branches and class members are never deduplicated by fold. The test is `instr(content, :lit) > 0` on SQLite or `strpos(content, :lit) > 0` on Postgres, ORed over the set, on the candidate fetch and on the scan side's fetch. It never runs under `invert_match`, which returns exactly the bodies a literal test would remove, and never for bytes bodies. *Why:* the extraction's set is a necessary condition of a match by construction. `experiments/e5_required_literals.py` prototypes the algorithm over Python's parser and found 0 violations in 557,140 random pattern-and-body checks, round 1's five failing patterns included. That prototype is evidence for the algorithm only. Run against the Rust matcher, it had 28,650 violations in 460,530 bodies, all of them from the parser mismatch of problem 5 (round 2). So decision 7 is built over the HIR (decision 0), and its property test runs against the Rust matcher, never against Python's `re`. The HIR does not factor common prefixes out of branches the way Python's parser does: `f_ref|f_count` yields `{f_ref, f_count}` over the HIR and `{ref, count}` in the prototype. R5's literal column is the HIR build's figure. The literal test lands within 25 files of the true matches over 66,000 (R5). *Turned on* when `c_byte` exceeds the server's per-byte scan cost. That cost is measured, and locally the test is expected to stay off.

8. **Costs are measured per storage, at run time, on statements that do no work.** `c_rt` is the latency of a bare `SELECT 1`, sampled at most once every few seconds per storage, because a weighted mean of real statements measures their work and not the round trip (round 1: one call's statements spanned 77×). `c_byte` is the observed body bytes per second of content batches fetched without decision 7's literal test. A filtered batch returns fewer bytes than the server read: round 3 measured 0.18 MB returned for 11.66 MB read. Counting it would inflate `c_byte` and hold the test on by its own effect. Filtered batches feed a separate figure, the server's scan rate, priced on the stored `size_bytes` of the rows the server read. `c_row` is seeded from R3. No dialect profile field is added, because a round trip is a fact about a deployment, not a dialect. The plan of an identical call can change when these move. That costs time and never rows, since every plan is lawful.

9. **What the index gains.**
   - *Nothing, for the plan's inputs.* The scope's size comes from the path index (decision 3) and the candidate count from the ladder's own intersection (R4). Directory aggregates are not needed to plan a root-scoped grep. Their use stays the listing verbs, as the reference deployment row has them.
   - *A precision step, measured before it is built.* A folded 4-gram index cut candidates by 44% over nine of R5's patterns. The raw simulation gave 45%, and the cut is pattern-dependent: under the folded rule `TODO` gains 0.7%, not 11% (round 1, L2). Its posting rows, bytes and rebuild time are paid on every index visit, about 11,000,000 a day at the reference deployment, and the experiment that measures them on the folded stream comes before any spec adopts it. Intersecting every trigram instead of the rarest four removes 6%. It needs no index change, and its cost is posting bytes, under `POSTING_BYTE_BUDGET`.
   - *The unindexed tail indexed, or priced.* Every ladder plan prices the tail's bytes. Indexing the files over today's caps, in chunked postings, is the change that removes the floor (R6). Until then, decision 7 keeps the tail's non-matching bodies on the server.

## What is checked

- Every plan of decision 5 returns the identical row set, line numbers and match text included, for each pair in the sandbox matrix. The scopes are 1 to 37,340 files, multi-root, overlapping roots, roots that are files, and scopes with other arms. The patterns run from rare to very common, and include anchored patterns, alternations, case-insensitive calls, inline `(?i)`, `invert_match`, and no indexable literal (refused without `allow_scan`, scanned with it). The view, the trash side and `/.vfs` are each covered on a writable copy built for the check.
- No truncation drops an in-scope row: a scoped call whose `U` exceeds the budget returns every in-scope match while the in-scope count is under the budget.
- Every statement the design adds is counted. Decision 3's probes are bounded by T and `SCAN_TIER_BUDGET`, decision 7 by `CONTENT_BYTE_BUDGET`, and the range-scoped plan by the budget. The full allow-list is the declared exception of decision 5, measured and acknowledged.
- The extraction of decision 7 passes the property test against the matcher itself.
- Decision 0's differential test runs the gram plan's candidates against the matcher over a generated pattern corpus, POSIX classes, `\<`, `\>`, `\b{…}` and nested classes included. No match may fall outside the candidates. Until the HIR build lands, every construct the test finds is refused by the gate.
- On a quiet machine, the planner's choice is within 20% of the best plan's measured cost over the matrix, on SQLite and on Postgres in Docker with added latency.

## Out of scope

The gram extraction itself, the matcher, the search verb, and the write path.

## Changes after round 1

- H1 (the literal test lost case variants) is answered by decision 7's own extraction over the matcher's HIR, with its property test.
- H2 (the literal test under `invert_match`) is answered by excluding it there, in so many words.
- M1 (the probe visited the scope) is answered by decision 3 probing on the index alone and judging afterwards.
- M2 (the range-scoped rule ignored the scope's size) is answered by decision 5's second probe and branch order, so the ids resolved are at most `min(n, U)` except in the declared exception.
- M3 (no plan for an unindexable pattern) is answered by decision 4.
- M4 (an unbounded statement claimed bounded) is answered by declaring the exception, with its direction.
- M5 (the probe missed the root's row) and L3 (overlapping roots) are answered by decisions 2 and 3.
- L1 (a mean of latencies is not a round trip) is answered by decision 8.
- L2 (the 4-gram simulation was not folded) is answered by decision 9.
- L4 (no scope reaches the seam without arms) is answered by decisions 1 and 2 naming what the seam sees.

## Changes after round 2

Round 2 closed all eleven round-1 findings, each by a run. Over 96 pairs of scope and pattern, the revised branch order returned today's rows in 93. In the other three, today's code truncates, and the planned rows are a superset of today's.

- H1 (the gate and the gram plan parse with Python while the matcher is Rust) is answered by problem 5 and decision 0.
- M1 (the in-hand threshold was stated from pre-fix figures) is answered by decision 6's measured figures and its removal of the projected remote number.
- M2 (the second probe read up to 25,001 rows before `U` was known) is answered by decision 5's order, `U` first.
- L1 (the ladder's floor ignored the unindexed tail) is answered by decision 6 pricing `B_u` on both sides.
- L2 (the probe is covered only on SQLite) is answered by decision 3 stating the Postgres cost.
- L3 (the prototype factors common prefixes) is answered by decision 7.
- The question of T and the mean file size is answered by decision 6: T bounds only the probe's limit, and the choice uses the probe's exact bytes.

## Changes after round 3

Round 3 was a fresh reviewer. It built a writable store of 2,116 files with real grants, memberships, postures, tombstones and `/.vfs` rows, and ran 1,664 greps under four plans. The rows were identical in every cell, and no plan fetched a body outside the caller's readable set. A rival write, delete and rebuild landing mid-call left every plan returning the call's starting snapshot.

- M1 (the index fold and the matcher use different Unicode case tables) is answered by decision 0's fold table, its exhaustive test and its stored Unicode version.
- M2 (reading `U` first costs in proportion to the corpus) is answered by decision 5 reading the posting metadata first and pricing the order, and by decision 6 pricing the blobs into the ladder's floor.
- L1 (the probe's limit was per root) is answered by decision 3's one limit over the union.
- L2 (the literal test skews the figure that turns it on) is answered by decision 8 keeping filtered batches out of `c_byte`.

## Open before build

- The Postgres leg has not run in any round. Decision 6's remote threshold, decision 7's server scan rate and decision 3's heap-visit cost are measured there, with added latency, before those decisions are final.
- Decision 9's 4-gram experiment on the folded stream, with its rebuild cost, is separate work, and no spec adopts it until it has run.
- The timings in every round were taken with another session loading the machine, and the decisions rest on counts. The planner's 20% check of "What is checked" needs a quiet machine.
