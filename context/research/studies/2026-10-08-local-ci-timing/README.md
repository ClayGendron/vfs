# Local CI timing, 2026-10-08

Raw runs behind the memo `../../2026-10-08-where-the-local-ci-time-goes.md`.

- `ci_timed.patch` — the diff applied to `scripts/ci.sh` to stamp an elapsed time on every step (the `step` function) and print a `TIMING` summary. Apply to a scratch copy; the script itself was not changed.
- `runs/matrix-steps.log` — the four-leg matrix, step by step, with seconds.
- `runs/durations-py3.13-nocov.log` — one suite run on Python 3.13 without coverage, `pytest --durations=0 --durations-min=0`, every test's setup, call and teardown time.
- `aggregate.py` — sums the durations log by phase, directory, file, test function and single test; prints the concentration figures.
- `runs/aggregate-py3.13-nocov.txt` — its output.

Reproduce:

```sh
cp scripts/ci.sh /tmp/ci_timed.sh && patch /tmp/ci_timed.sh ci_timed.patch
VFS_REPO=$PWD bash /tmp/ci_timed.sh         # the matrix, ~24 min warm
UV_PROJECT_ENVIRONMENT=.venv-ci/3.13 uv run --no-sync --python 3.13 \
  pytest -q -p no:cov --durations=0 --durations-min=0 > durations.log
python3 -I aggregate.py durations.log
```
