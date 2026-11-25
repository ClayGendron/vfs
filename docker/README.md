# Real-engine test databases

`compose.test.yml` starts the Postgres servers the storage conformance
suite runs against, one service per supported version. vfs supports two
engines, SQLite and Postgres, and SQLite needs no server. The Postgres
leg activates when `VFS_TEST_POSTGRES_URL` is set and skips otherwise,
so a plain `uv run pytest` never needs Docker.

vfs is tested on every Postgres major version the PostgreSQL project
supports, each with pgvector 0.8: today 15, 16, 17, 18 and 19. The
project supports a major version for five years, so each November the
version that reaches its end of life leaves this file and the workflow,
and the new major joins.

**A laptop runs one version, the newest: Postgres 19.** It is the
`postgres` service, on host port 54320, and starts by default. **CI runs
every version**, one matrix row each in
`.github/workflows/test-dialects.yml`, from this same file:

| Service | Version | Host port | Who runs it |
|---|---|---|---|
| `postgres` | 19 | 54320 | a laptop, and CI |
| `postgres18` | 18 | 54318 | CI |
| `postgres17` | 17 | 54317 | CI |
| `postgres16` | 16 | 54316 | CI |
| `postgres15` | 15 | 54315 | CI |

The older versions sit behind the `every-version` profile; naming one
service starts it alone, so a failure CI reports on one version can be
reproduced here. Each keeps its data on a tmpfs: 15, 16 and 17 at
`/var/lib/postgresql/data`, and 18 and 19 at `/var/lib/postgresql`,
since from 18 the image keeps its data under
`/var/lib/postgresql/<version>/docker`. Host ports are offset from 5432
so a container never collides with a Homebrew or Postgres.app install
already holding the default port.

The leg is reentrant: vfs's table names are fixed, so each test creates
a schema of its own (`vfs_t_<hex>`) and drops it at teardown, and
concurrent runs against one server never collide. The init script under
`initdb/postgres` installs pgvector when a container first starts: vfs
proves the extension at first touch and never creates it, because
`CREATE EXTENSION` needs rights an application role does not have on a
managed server. A crashed run's leftover `vfs_t_*` schemas are harmless
residue — data is ephemeral, and `compose down` clears everything.

## Quick start

```sh
docker compose -f docker/compose.test.yml up -d --wait
uv sync --extra postgres --extra documents --group dev
VFS_TEST_POSTGRES_URL="postgresql+asyncpg://vfs:vfs@localhost:54320/vfs" \
  uv run pytest -m postgres
```

To reproduce a failure CI found on an older version, start that service
and point the URL at its port:

```sh
docker compose -f docker/compose.test.yml up -d --wait postgres16
VFS_TEST_POSTGRES_URL="postgresql+asyncpg://vfs:vfs@localhost:54316/vfs" \
  uv run pytest -m postgres
```

Tear down (data is tmpfs/ephemeral — nothing persists):

```sh
docker compose -f docker/compose.test.yml --profile every-version down -v
```
