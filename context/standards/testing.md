# Testing

## Stance

Tests are not optional. Lint, format, type check, and tests must all pass before any commit lands on `main`. Failing tests are never deferred — fix the code or fix the test, but don't merge red.

The `fail_under = 99` coverage gate is real. New code lands with the tests that cover it.

## Layout

```
tests/
  conftest.py              # shared fixtures (in-memory SQLite engines, async sessions, ...)
  test_<module>.py         # one file per source module
  fixtures/                # static repo fixtures, sample data
```

Test files mirror source structure: `src/vfs/storage/backends/database/reads.py` → `tests/storage/database/test_reads.py`. New source file → new test file.

`tests2/` is archived. Never edit it; ruff and pytest skip it.

## Conventions

- `pytest-asyncio` with `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` decorator needed; just `async def test_…`.
- Markers: `@pytest.mark.slow`, `@pytest.mark.integration`. Use them so contributors can scope runs.
- In-memory SQLite is the default for unit tests. Disk fixtures only when the behaviour under test is disk-specific.
- MSSQL backend tests run under `--mssql` against the Docker container in `docker/mssql/`. They are excluded from coverage because CI doesn't spin up SQL Server.
- Don't mock the database layer. If a test needs a session, give it a real one against in-memory SQLite. Mocked DB layers have masked real bugs more than once.

## Writing a test

```python
async def test_write_then_read(db_fs):
    result = await db_fs.write("/foo.txt", "hello")
    assert result.success

    read = await db_fs.read("/foo.txt")
    assert read.candidates[0].content == "hello"
```

- Assert on `Result` fields directly. Don't wrap assertions in helper functions that hide what failed.
- One behaviour per test. If a test name needs `and`, split it.
- Fixtures over setup methods. Test classes are unusual here.

## Pins land with their mutant

A test that exists to pin a law is proven by the mutation it kills,
not by the coverage it adds. Every review campaign has found laws
that held by authorship — exercised by dozens of tests, asserted by
none — because the suite's rows were subset asserts, single-target
shapes, or unbudgeted paths. So:

- When a law is named (a docstring, a spec, an ADR), ask which
  one-line mutation would break it silently, apply that mutation
  under the safe-restore rule (copy to the scratchpad first; restore
  from the copy; verify with `ruff`), and confirm the pin fails.
- Record the mutation the test guards in its docstring — the shape,
  never a spec or finding number.
- Batch-shaped behavior gets a batch-width row (a two-target delete,
  a two-pair move) with the referee that can see the width; mask
  promises get exact-equality rows (`==`, not `<=`); budgeted paths
  get budgeted parity rows.

Pinned mutations also land as rows in `mutant-ledger.md` (intent +
anchor, scoped selection, advisory killers), and review campaigns
replay them — the `test_review` skill owns the procedure, always in
an isolated worktree, never the live tree (ADR 050). A replayed row
reports killed, survived (a pin regressed), or stale (re-prove or
retire); recorded killers are diagnosis, never the assertion.

## Engine legs are reentrant

The real-engine fixtures mint a per-run table namespace
(`vfs_<hex>`) and drop exactly what they minted at teardown, so two
runs against one live engine never tear each other down (review
agents sharing a Docker stack were the first to collide). A new
engine-leg fixture or raw-SQL audit must take the minted name, never
a fixed `vfs`.

## Running

```bash
uv run pytest                       # full suite
uv run pytest tests/test_database_fs.py
uv run pytest -k "write_ordering"
uv run pytest --cov
uv run pytest --mssql               # adds MSSQL integration tests
```

No piping, no `2>&1`. See `standards/tooling.md`.

## Code review and tests

Every phase of work gets a sub-agent code review with real integration tests. Self-review and call-it-done is not the standard.
