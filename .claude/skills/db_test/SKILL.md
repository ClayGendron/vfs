---
name: db_test
description: Run the storage conformance suite against real database engines (Postgres, MySQL, MSSQL, Oracle) in local Docker containers, end to end — start Docker Desktop, build the containers up, run the engine legs, tear everything down, quit Docker Desktop. Use when the user asks to "test against real databases", "run the postgres/mysql/mssql/oracle leg", "db test", or before landing a change that touches the database backend, the schema (models/rows.py), or a dialect profile.
---

# Local real-engine database testing

The full cycle is: **start Docker Desktop → build up → test → tear
down → quit Docker Desktop**. Leave the machine as you found it — no
containers running, no Docker Desktop in the dock, no venv missing
drivers the sqlite suite needs.

The single source of truth for images, credentials, ports, and health
checks is `docker/compose.test.yml` (CI uses the same file; details and
per-engine notes in `docker/README.md`). Engine legs live in
`tests/test_storage_conformance.py`, gated on `VFS_TEST_<ENGINE>_URL`
env vars — unset means the leg skips, so nothing here is needed for a
plain `uv run pytest`.

## 1. Start Docker Desktop

```sh
open -a Docker
for i in $(seq 1 45); do docker info >/dev/null 2>&1 && break; sleep 2; done
docker info --format '{{.ServerVersion}}' || echo "Docker never came up"
```

If `docker info` still fails after the loop, stop and report — do not
retry the suite against a dead daemon.

## 2. Build up

Postgres has no compose profile and starts by default; the heavier
engines start when named (naming a service activates its profile):

```sh
docker compose -f docker/compose.test.yml up -d --wait                 # postgres only
docker compose -f docker/compose.test.yml up -d --wait mysql          # + mysql
docker compose -f docker/compose.test.yml up -d --wait mssql oracle   # heavyweights
```

`--wait` blocks on query-level healthchecks, not container liveness.
Oracle's first start takes 30–60 s; MSSQL runs amd64-under-Rosetta and
needs the host ODBC driver (`brew install msodbcsql18`, one-time).

Install the drivers for **every** engine you will test in one sync —
`uv sync` makes the venv match exactly, so syncing one extra evicts the
others' drivers:

```sh
uv sync --extra postgres --extra mysql --group dev   # add --extra mssql / oracle as needed
```

## 3. Test

One env var + one marker per engine (URLs use offset host ports so
local installs never shadow the containers — a host Postgres on 5432
silently swallowing connections is a known failure mode):

```sh
VFS_TEST_POSTGRES_URL="postgresql+asyncpg://vfs:vfs@localhost:54320/vfs" \
  uv run pytest -m postgres --tb=short

VFS_TEST_MYSQL_URL="mysql+aiomysql://vfs:vfs@localhost:33061/vfs?charset=utf8mb4" \
  uv run pytest -m mysql --tb=short

VFS_TEST_MSSQL_URL="mssql+aioodbc://sa:vfsStr0ngPassw0rd@localhost:14330/master?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes" \
  uv run pytest -m mssql --tb=short

VFS_TEST_ORACLE_URL="oracle+oracledb_async://vfs:vfs@localhost:15210/?service_name=FREEPDB1" \
  uv run pytest -m oracle --tb=short
```

A healthy leg matches the sqlite leg's pass count, with the same
capability skips (grep and the topology verbs are classified stubs).
Keep `?charset=utf8mb4` on the MySQL URL — text bodies depend on it.
Report failures as findings against the code, not the harness: a leg
that fails on a real engine while sqlite passes is exactly the signal
this setup exists to produce (that is how the InnoDB index-cap defect
was caught).

## 4. Tear down

Plain `down` skips services behind profiles — name the profiles:

```sh
docker compose -f docker/compose.test.yml --profile mysql --profile mssql --profile oracle down
```

Data is tmpfs/ephemeral; nothing persists. Verify with
`docker ps --format '{{.Names}}'` (expect no `vfs-test-*` rows).

## 5. Quit Docker Desktop

```sh
osascript -e 'quit app "Docker"'        # stops the app and its Linux VM (the heavy part)
pkill -f "com.docker.backend" || true   # its "run in background" helpers (~400 MB) linger otherwise
```

Only after teardown succeeded — quitting the app kills the daemon out
from under any still-running container. The quit can take >30 s while
the VM winds down; `docker info` failing is the "VM is gone" signal.
`com.docker.vmnetd` remaining is normal — that is a system-wide
privileged launchd helper, not part of the session; leave it alone.
