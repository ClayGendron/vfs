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

Test files mirror source structure: `src/grover/backends/database.py` → `tests/test_database_fs.py`. New source file → new test file.

`tests_old/` is archived. Never edit it; ruff and pytest skip it.

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

- Assert on `GroverResult` fields directly. Don't wrap assertions in helper functions that hide what failed.
- One behaviour per test. If a test name needs `and`, split it.
- Fixtures over setup methods. Test classes are unusual here.

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
