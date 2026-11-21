---
name: db_test
description: Run the storage conformance suite against a real Postgres server in a local Docker container, end to end — start Docker Desktop, build the container up, run the engine leg on Postgres 19 (CI runs every supported version), tear everything down, quit Docker Desktop. Use when the user asks to "test against a real database", "run the postgres leg", "db test", or before landing a change that touches the database backend, the schema (models/rows.py), or a dialect profile.
---

# Local real-engine database testing

vfs supports two engines, SQLite and Postgres. The SQLite legs run in
every `uv run pytest`; Postgres is the one engine leg that needs a
server. The full cycle is: **start Docker Desktop → build up → test →
tear down → quit Docker Desktop**. Leave the machine as you found it —
no containers running, no Docker Desktop in the dock, no venv missing
drivers the sqlite suite needs.

The single source of truth for the image, credentials, port, and
health check is `docker/compose.test.yml` (CI uses the same file;
details in `docker/README.md`). The engine leg is gated on
`VFS_TEST_POSTGRES_URL` — unset means the leg skips, so nothing here is
needed for a plain `uv run pytest`.

## 1. Start Docker Desktop

**Check whether Docker Desktop is already running before launching
it** — the user may have it open (or be mid-quit, which can take
>30 s while the VM winds down; `open -a Docker` during a wind-down
races the shutdown). Ask/confirm state first, then start:

```sh
pgrep -x "Docker Desktop" >/dev/null && echo "already running" || echo "not running"
open -a Docker
for i in $(seq 1 45); do docker info >/dev/null 2>&1 && break; sleep 2; done
docker info --format '{{.ServerVersion}}' || echo "Docker never came up"
```

If it was already running, skip `open -a Docker` and go straight to
the `docker info` wait. If `docker info` still fails after the loop,
stop and report — do not retry the suite against a dead daemon.

## 2. Build up

**Every run starts from a fresh container** (Clay, 2026-10-03): take
down whatever is left, volumes included, so the `docker/initdb/` init
scripts always apply and no container carries hand-applied state:

```sh
docker compose -f docker/compose.test.yml --profile every-version down -v
```

Then start Postgres. A laptop runs one version, the newest: the
`postgres` service, Postgres 19 on 54320, which starts by default. CI
runs every version the PostgreSQL project supports, 15 to 19 today, one
matrix row each; the older ones are services of their own behind the
`every-version` profile (`docker/README.md` has the table), started
here only to reproduce a failure CI found on one of them:

```sh
docker compose -f docker/compose.test.yml up -d --wait                  # Postgres 19
docker compose -f docker/compose.test.yml up -d --wait postgres16       # one older version, on its own port
```

`--wait` blocks on a query-level health check, not container liveness.

Install the Postgres driver and `documents` in one sync — `uv sync`
makes the venv match exactly. `documents` is needed because the
conformance contract renders real PDFs and Office files, and the test
modules import those libraries at the top (the CI dialect job installs
the same set):

```sh
uv sync --extra postgres --extra documents --group dev
```

## 3. Test

One env var and one marker. The URL uses an offset host port so a
local install never shadows the container — a host Postgres on 5432
silently swallowing connections is a known failure mode:

```sh
VFS_TEST_POSTGRES_URL="postgresql+asyncpg://vfs:vfs@localhost:54320/vfs" \
  uv run pytest -m postgres --tb=short
```

A healthy leg matches the sqlite leg's pass count, with the same
capability skips. The leg is reentrant: vfs's table names are fixed,
so each test gets a schema of its own (`vfs_t_<hex>`,
`tests/support/server_schemas.py`), and concurrent runs against one
server — two terminals, parallel review agents on a shared stack —
never tear each other down. The app user can create and drop schemas
because the compose init scripts (`docker/initdb/`) grant it at first
start. A crashed run's leftover `vfs_t_*` schemas are residue on an
ephemeral-data stack; `compose down` clears them.

Report failures as findings against the code, not the harness: a leg
that fails on Postgres while sqlite passes is exactly the signal this
setup exists to produce.

The sqlite CI leg (`scripts/ci.sh`) is CPU-bound in one process while
the Postgres leg mostly waits on its server, so run them at the same
time:

```sh
( VFS_TEST_POSTGRES_URL="postgresql+asyncpg://vfs:vfs@localhost:54320/vfs" \
    uv run pytest -m postgres -q > leg_postgres.log 2>&1 ) &
( scripts/ci.sh > leg_ci.log 2>&1 ) &
wait; tail -n 1 leg_*.log
```

The other versions are CI's: the pull request runs the leg on each.

While iterating on a fix, run only the slice that touches it
(`-k "<names>"`) — seconds, not minutes — and run the whole leg once,
at the gate. **Benchmarks are the exception:** a timing run wants a
quiet machine, so it runs alone, after the legs, and uses a smaller
sample on Postgres (1,000 linux files; 4,000 on sqlite — the
bulk-insert benchmark's defaults) because its job is the ratio between
shapes, not the seconds.

## 4. Tear down

```sh
docker compose -f docker/compose.test.yml --profile every-version down -v
```

Name the profile, or `down` leaves any older version you started running. Always pass
`-v`: volumes go with the containers, so the next run
starts clean. Data is on tmpfs; nothing persists. Verify with
`docker ps -a --format '{{.Names}} {{.Status}}'` — expect **zero**
rows, not just zero running.

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
