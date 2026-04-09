# Local SQL Server 2025 for Grover MSSQL backend tests

Custom SQL Server 2025 Developer edition container with Full-Text Search, built for running `tests/test_mssql_backend.py --mssql` locally on Apple Silicon Mac.

Not for production. Not (yet) wired into CI.

## Why a custom image?

- `MSSQLFileSystem` in `src/grover/backends/mssql.py` requires **SQL Server 2025 RTM** for `REGEXP_LIKE` (grep), `CONTAINSTABLE` / Full-Text Search (lexical search), and `LIKE ESCAPE` (glob). SQL Server 2022 lacks `REGEXP_LIKE` — the backend will not work on 2022.
- The stock `mcr.microsoft.com/mssql/server` image does **not** include the `mssql-server-fts` package and cannot be cleanly extended to install it. Ubuntu base + the Microsoft apt repo is the canonical FTS recipe.
- SQL Server is x86_64-only, so on Apple Silicon this runs under Rosetta.

## One-time host prerequisites

1. **Docker Desktop 4.25+** with Rosetta enabled
   - Settings → General → "Use Rosetta for x86_64/amd64 emulation on Apple Silicon" → Apply & Restart.
   - Without it, the container will either refuse to start or run under slow QEMU.
   - Verify: `docker run --rm --platform=linux/amd64 ubuntu:22.04 uname -m` should print `x86_64`.

2. **Microsoft ODBC Driver 18** on the Mac (required for `pyodbc` / `aioodbc` to connect from the host):
   ```bash
   brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
   brew update
   HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql18 mssql-tools18
   ```
   Verify: `odbcinst -q -d` should list `[ODBC Driver 18 for SQL Server]`.

3. **Grover's mssql optional extras** in the project venv:
   ```bash
   uv pip install -e '.[mssql]'
   ```

## Normal workflow

From the repo root:

```bash
./scripts/mssql_up.sh                 # ~90s first time (image build), ~10s after
./scripts/mssql_test.sh               # full tests/test_mssql_backend.py
./scripts/mssql_test.sh -k Grep -x    # targeted subset
./scripts/mssql_down.sh               # stop, keep data
./scripts/mssql_down.sh --clean       # stop and nuke the volume
```

The container persists its data in a named Docker volume `grover-mssql-data` across `up`/`down` cycles. Use `--clean` on teardown to drop it.

## Verification (end-to-end)

```bash
# 1. Bring instance up
./scripts/mssql_up.sh
# Expect: "=> grover-mssql-2025 is healthy." within ~90s on first build.

# 2. Confirm it's really 2025 with FTS
docker exec grover-mssql-2025 /opt/mssql-tools18/bin/sqlcmd \
    -S localhost -U sa -P 'Strong!Passw0rd' -C -N \
    -Q "SELECT @@VERSION; SELECT SERVERPROPERTY('IsFullTextInstalled');"
# Expect: "Microsoft SQL Server 2025" in version, "1" for IsFullTextInstalled.

# 3. REGEXP_LIKE smoke test — would fail on SQL Server 2022, so green here
#    proves we really have 2025.
./scripts/mssql_test.sh tests/test_mssql_backend.py::TestGrepPushdown -x -q

# 4. Full MSSQL backend suite
./scripts/mssql_test.sh

# 5. Tear down
./scripts/mssql_down.sh
```

## Troubleshooting

- **Container stuck `starting` / timeout in `mssql_up.sh`**
  Dump logs: `docker compose -f docker/mssql/docker-compose.yml logs --tail=200 mssql`. Common causes: Rosetta not enabled, password doesn't meet complexity policy, out of disk space.

- **`pyodbc.InterfaceError: ... Can't open lib 'ODBC Driver 18 for SQL Server'`**
  ODBC Driver 18 is not installed on the host. Run the `brew install msodbcsql18 mssql-tools18` step above.

- **`apt-get update` 404s during `docker build` on `mssql-server-2025.list`**
  The 2025 package list URL has shifted. Edit `Dockerfile` to use `mssql-server-preview.list` instead of `mssql-server-2025.list` (only applies while 2025 is still in a preview window).

- **`TestLexicalSearchPushdown` fails but `TestGrepPushdown` passes**
  Full-Text Search daemon isn't working under Rosetta. Confirm with
  `docker exec grover-mssql-2025 /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P 'Strong!Passw0rd' -C -N -Q "SELECT SERVERPROPERTY('IsFullTextInstalled')"`.
  Workaround: run the container on a native amd64 host (cloud VM, GH Actions `ubuntu-latest`) and point `GROVER_MSSQL_URL` at it — no code changes.

- **Image is ~2.5–3 GB and first build takes 60–120s**
  Expected. SQL Server is large, and Rosetta adds startup overhead. Subsequent `mssql_up.sh` runs reuse the cached image and persisted volume.

## Files

- `Dockerfile` — Ubuntu 22.04 + `mssql-server` + `mssql-server-fts` + `mssql-tools18`
- `docker-entrypoint.sh` — launches `sqlservr`, waits for readiness, runs `init-db.sql`
- `init-db.sql` — idempotent `CREATE DATABASE grover_test`
- `docker-compose.yml` — service, healthcheck, named volume, `linux/amd64` pin
- `.dockerignore` — keeps build context tiny

The credentials (`sa` / `Strong!Passw0rd`) are hardcoded to match `_MSSQL_DEFAULT_URL` in `tests/conftest.py`. Override via the `GROVER_MSSQL_URL` env var if you need to point at a different instance.
