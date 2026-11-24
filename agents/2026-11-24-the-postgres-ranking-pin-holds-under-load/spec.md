# The Postgres ranking pin holds under load

A draft, written on 2026-11-24 from a failure on the Postgres 19 leg while the third landing of `agents/2026-11-22-the-kernel-keeps-records-of-its-own/spec.md` was being gated. That landing touches no ranking code. It is not reviewed, and nothing is built.

## The outcome wanted

`tests/storage/test_conformance.py::TestPostgresRankingPin::test_ordered_top10_matches_the_pin` gives the same answer on every run, however loaded the machine is. Ranked search on Postgres orders its top 10 the same way every time for the same corpus and query.

## Builds on

- `tests/ranking/pins.py::assert_top10_pin`: it loads the golden corpus, asks each golden query, and compares the ordered top 10 with the recorded pin, first through the driver and then through the verb.
- Its `analyzed` argument states the rule this failure breaks: the pin must hold whether or not anyone has analyzed the store.

## The problem

Each fact was run, unless it says "read".

- **The failure.** In one full `-m postgres` run at `588bc53`, 656 tests passed and this test failed. The ordered top 10 of `q27` and `q39` differed from the pin, and the other 38 queries matched.
  - `q27`'s first four paths matched, and its fifth differed: `/context/research/2026-08-10-okf-open-knowledge-format.md` where the pin has `/context/research/2026-07-21-prior-art-design-review-notes.md`.
- **The load.** The run shared 4 cores with `scripts/ci.sh` and with several other agents running test suites, on a load average far above the core count.
- **Not reproduced alone or on a rerun.** The test alone passed three runs of three on the same commit. A second full leg on the same commit passed all 657.
- **A suspected cause, read and not run.** The pin is meant to hold with and without planner statistics. Postgres's autovacuum can analyze the corpus's tables at any moment while a run is under way. If two candidates tie on score and the order between them comes from the plan, an analyze that lands mid-run could change the plan and so the order.

## Decisions

1. **The order of a tie is decided by a key, never by the plan.** Every ranked statement on Postgres orders by score and then by a stable key of the row, such as its path. If one already does, the cause is elsewhere and is found before anything is changed.
2. **The pin is re-recorded only if the key changes an order it recorded.** A re-recorded pin names the queries it changed.

## Tests

- A test runs the pin with autovacuum forced to analyze between the load and the queries. Run once with an explicit `ANALYZE` at that point and once without, both must give the pinned order.
- The same test runs on SQLite, where the order of a tie must already be stable.

## Scope

- **In:** the ranked statements in `src/vfs/storage/backends/database/` that order a top 10, and `tests/ranking/pins.py`, with its pin files if they must be re-recorded.
- **Out:** every change to scoring.

## Not checked

- The cause is not shown. Whether `q27`'s and `q39`'s fifth candidates tie on score was not read from the run.
- No run measured how often the failure happens under load.

## Choices to confirm

- Which key breaks a tie: the path, or the entry id.

## One line

A ranked top 10 on Postgres orders its ties by a key, so the ranking pin gives one answer on a loaded machine.
