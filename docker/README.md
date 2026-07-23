# Real-engine test databases

`compose.test.yml` starts the database servers the storage conformance
suite runs against. The tests themselves are wired in
`tests/test_storage_conformance.py`: each engine leg activates when its
`VFS_TEST_<ENGINE>_URL` environment variable is set and skips otherwise,
so a plain `uv run pytest` never needs Docker. CI
(`.github/workflows/test-dialects.yml`) uses this same compose file.

## Quick start (macOS, Apple Silicon)

Postgres — native arm64, up in seconds:

```sh
docker compose -f docker/compose.test.yml up -d --wait
uv sync --extra postgres --group dev
VFS_TEST_POSTGRES_URL="postgresql+asyncpg://vfs:vfs@localhost:54320/vfs" \
  uv run pytest -m postgres
```

Host ports are offset from the engine defaults (54320, 33061, 14330,
15210) so the containers never collide with a Homebrew or Postgres.app
install already holding 5432 and friends.

Naming a service activates its profile, so the heavier engines start on
demand:

```sh
docker compose -f docker/compose.test.yml up -d --wait mysql oracle mssql
```

Tear everything down (data is tmpfs/ephemeral — nothing persists).
Plain `down` skips services behind profiles, so name the profiles:

```sh
docker compose -f docker/compose.test.yml --profile mysql --profile mssql --profile oracle down
```

## Per-engine notes

| Engine | arm64 | Driver extra | URL |
|---|---|---|---|
| Postgres 17 | native | `postgres` | `postgresql+asyncpg://vfs:vfs@localhost:54320/vfs` |
| MySQL 8.4 | native | `mysql` | `mysql+aiomysql://vfs:vfs@localhost:33061/vfs?charset=utf8mb4` |
| SQL Server 2022 | Rosetta | `mssql` | `mssql+aioodbc://sa:vfsStr0ngPassw0rd@localhost:14330/master?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes` |
| Oracle Free 23ai | native | `oracle` | `oracle+oracledb_async://vfs:vfs@localhost:15210/?service_name=FREEPDB1` |

**SQL Server** is the one engine with extra macOS setup:

1. Its image is amd64-only. Enable Rosetta emulation — Docker Desktop:
   Settings > General > *Use Rosetta for x86_64/amd64 emulation on Apple
   Silicon* (needs the Virtualization framework backend). OrbStack has
   it on by default.
2. `aioodbc` needs Microsoft's ODBC driver on the host:

   ```sh
   brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
   brew install msodbcsql18
   ```

3. Tests target the `master` database — fine for a disposable container,
   and it avoids an init script.

**Oracle** publishes native arm64 images for 23ai Free (`gvenzl/oracle-free`),
so it runs *better* on Apple Silicon than SQL Server does. First start
takes 30–60 s while the pluggable database opens; `--wait` covers it.
The `oracledb` driver runs in thin mode — no Oracle client libraries to
install.

**MySQL** carries a tuned profile (3,072-byte key budget, catch-retry
arbitration, REPEATABLE READ pinned, deadlock/lock-wait errnos
retryable); MariaDB rides the same policy under its own dialect name.
Keep `?charset=utf8mb4` in the URL — the dialect does not default it,
and unicode text bodies depend on it. This leg is the regression pin
for the byte-denominated path limits and the `VARBINARY` key columns
(ADR 024). With MySQL and Oracle both tuned, no real engine resolves
to the GENERIC floor anymore — the floor is pinned synthetically in
the dialect tests, and its budget numbers remain borrowed from
Oracle's real caps (ORA-01795's 1,000-element `IN`-list).

## Why these four

- **Postgres** — the pinned REPEATABLE READ profile: native upsert
  arbitration, and serialization-failure (40001) retry classification
  for real.
- **SQL Server** — READ COMMITTED natively, the ~2,100 bind-parameter
  budget, `OUTPUT inserted.*` as the RETURNING arm.
- **MySQL** — the byte-typed key columns and byte-denominated path
  limits under InnoDB's 3,072-byte index cap (ADR 024).
- **Oracle** — also READ COMMITTED by default, and the engine whose
  1,000-element `IN`-list cap (ORA-01795) defines the GENERIC budget
  floor; a wrong chunking budget turns into a hard error here.
