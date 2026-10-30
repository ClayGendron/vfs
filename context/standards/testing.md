# Testing

## Stance

Tests are not optional. Lint, format, type check and tests must all pass before any commit lands on `main`; a failing test is never deferred. The order of work is the test first, seen failing, then the code that turns it green; the rule and what "test" means at each layer are in [how-we-code.md](how-we-code.md), "Test first, then code".

The coverage gate is `fail_under = 100` (`[tool.coverage.report]` in `pyproject.toml`), and `scripts/ci.sh` runs the suite with `--cov-fail-under=100`. New code lands with the tests that cover it, in the same commit.

## Layout

```
tests/
  conftest.py              # shared fixtures and the engine-leg selection hook
  lint/                    # the shape checks over context/ and the tree
  support/                 # the conformance contract, oracles, doubles, helpers
  storage/database/        # one test file per database backend module
  test_<module>.py         # one file per top-level source module
  fixtures/                # static sample data (not collected)
```

Test files mirror source structure: `src/vfs/storage/backends/database/reads.py` is pinned by `tests/storage/database/test_reads.py`. A new source file is a new test file.

`tests2/` is archived. Never edit it; `ruff` and `pytest` skip it by configuration.

## Conventions

- `pytest-asyncio` runs in `asyncio_mode = "auto"`: no `@pytest.mark.asyncio` decorator, just `async def test_...`.
- Markers: `slow` for a deliberately heavy test (a BEIR corpus, a 10k batch, a second backend for a contract already proven on one), `integration`, `needs(*ops)` for a conformance test's required capabilities, and one marker per real engine (`postgres`, `mariadb`, `mssql`, `oracle`). Nothing deselects `slow` by default; `-m "not slow"` is the opt-out while iterating.
- In-memory SQLite is the default for unit tests (`InMemoryStorage`, a `DatabaseStorage` over a private in-memory file). Disk fixtures only when the behaviour under test is disk-specific.
- Never mock the database layer. If a test needs a session, give it a real one against in-memory SQLite. Mocked database layers have masked real bugs more than once.
- Never assert on elapsed time. A performance pin counts work (statements through `before_cursor_execute`, calls to a spied function, rows visited); see [CLAUDE.md](../../CLAUDE.md), "Performance tests".

## Writing a test

```python
async def test_write_then_read(storage):
    written = await storage.write(entries=[Entry(path=Path("/foo.txt"), content="hello")])
    assert written.success

    read = await storage.read(path=Path("/foo.txt"))
    assert read.one().content == "hello"
```

- Assert on `Result` fields directly. Do not wrap assertions in helper functions that hide what failed.
- One behaviour per test. If a test name needs "and", split it.
- Fixtures over setup methods. A test class is unusual here; the conformance contract is the exception.

## Pins land with their mutant

A test that exists to pin a law is proven by the mutation it kills, not by the coverage it adds. Every review campaign has found laws that held by authorship, exercised by dozens of tests and asserted by none, because the suite's rows were subset asserts, single-target shapes or unbudgeted paths. So:

- When a law is named (a docstring, a spec), ask which one-line mutation would break it silently, apply that mutation under the safe-restore rule (copy the file to the session scratchpad first; restore from the copy; verify with `ruff`), and confirm the pin fails.
- Record the mutation the test guards in its docstring: the shape, never a spec or finding number.
- Batch-shaped behaviour gets a batch-width row (a two-target delete, a two-pair move) with the referee that can see the width; mask promises get exact-equality rows (`==`, not `<=`); budgeted paths get budgeted parity rows.

Pinned mutations also land as rows in [mutant-ledger.md](mutant-ledger.md) (intent and anchor, scoped selection, advisory killers), and review campaigns replay them; the `test_review` skill owns the procedure. A replay works in place under the safe-restore rule above, never in a git worktree, which [CLAUDE.md](../../CLAUDE.md) forbids. A replayed row reports killed, survived (a pin regressed) or stale (re-prove or retire); recorded killers are diagnosis, never the assertion.

## Engine legs are reentrant

vfs's table names are fixed (`vfs_*`), so the real-engine fixtures give each test a schema of its own (`vfs_t_<hex>`, via `tests/support/server_schemas.py`) and drop it at teardown; two runs against one live engine never tear each other down (review agents sharing a Docker stack were the first to collide). A new engine-leg fixture or raw-SQL audit must take the test's schema, never the server's default one.

## Engine legs are selected by a URL

A real-engine leg runs when its `VFS_TEST_<ENGINE>_URL` variable is set and is deselected at collection otherwise (`pytest_collection_modifyitems` in `tests/conftest.py`), so a plain `uv run pytest` never needs Docker and never pays a skipped leg's fixtures. The servers come from `docker/compose.test.yml`, the same file CI's dialect workflow uses; `docker/README.md` has the per-engine URLs, and the `db_test` skill runs the whole cycle.

```bash
docker compose -f docker/compose.test.yml up -d --wait
VFS_TEST_POSTGRES_URL="postgresql+asyncpg://vfs:vfs@localhost:54320/vfs" uv run pytest -m postgres
```

## Running

```bash
uv run pytest                                   # the whole suite, parallel (-n auto --dist worksteal)
uv run pytest tests/storage/database/test_reads.py
uv run pytest -k "write_ordering"
uv run pytest -m "not slow"                     # the fast inner loop while iterating
uv run pytest --cov --cov-fail-under=100        # the coverage gate on its own
scripts/ci.sh                                   # the full gate before any commit touching src/ or tests/
```

No piping, no `2>&1`. See [tooling.md](tooling.md).

## The docs' examples are tests

Every ` ```python ` fence under `docs/tutorials`, `docs/how-to`, `docs/reference` and `docs/explanation`, and in `README.md`, runs against the live package through Sybil (the root `conftest.py`): one namespace per page, fences in document order, a fresh SQLite-backed `storage` and `fs` per page, top-level `await` allowed. A fence that is not runnable (a signature, a sketch) is preceded by `<!-- skip: next -->`. State a doc's claims as `assert` lines inside the fence so drift fails the gate rather than reading as stale prose.

```bash
uv run pytest docs README.md -p no:cov -n 0     # the doc examples; not in the default testpaths
```

`scripts/ci.sh` and the CI Tests job run this on the coverage leg, outside the coverage measurement. Adding a page to one of the four directories adds its fences to the gate with no registration.

## Code review and tests

Every change gets a code review by a reviewer who did not write it, with real tests on a real database, before it lands. Self-review and call-it-done is not the standard.
