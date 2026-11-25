# Two loop tests of a line's facts race its deadline

A draft, written on 2026-11-22 from a run of `scripts/ci.sh` on the branch `the-shell-serves-the-indexed-verbs` at `e18ae69`. Built on 2026-11-22 on the branch `the-shell-review-specs-are-checked` by decision 1: the loops run 300 refusals, three times `LINE_FACTS`, after both tests ended at the deadline again under a loaded `scripts/ci.sh` at 20.8 and 21.7 seconds alone.

## The outcome wanted

`tests/shell/test_host.py::test_a_refusal_repeated_in_a_loop_is_kept_once` and `::test_the_facts_a_line_keeps_are_bounded_and_the_rest_counted` pass on a loaded machine as they do on an idle one, as `agents/2026-11-21-no-test-depends-on-the-clock-or-on-luck/spec.md` asks of every test.

## The problem

- Each runs `for i in {1..2000}; do cat /nope...; done`: 2,000 refused `read` calls under the line's 30-second deadline, `DEADLINE_SECONDS` in `src/vfs/shell/host.py`.
- Alone, on an idle machine, they took 21.2 and 18.4 seconds (`--durations`, 2026-11-22).
- Run by `scripts/ci.sh` while a second `pytest tests/shell -n 4` ran beside it, both ended at the deadline with status 124 and a `timeout` fact, and failed. Neither touches code the branch changed.

## Decisions to make

1. Lower the loops to what each assertion needs: a few hundred refusals still pass `LINE_FACTS`, which is 100, and still show a repeated refusal kept once.
2. Or give these lines a deadline far past their work through `run_line`'s `deadline`, so the test is of the facts and not of the clock.

## Tests

The two tests, passing under `pytest -n auto` beside a second full shell run.

## One line

Two tests of a line's facts stop racing the 30-second deadline.
