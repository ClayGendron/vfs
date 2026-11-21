# Real-engine test database

`compose.test.yml` starts the Postgres server the storage conformance
suite runs against. vfs supports two engines, SQLite and Postgres, and
SQLite needs no server. The Postgres leg activates when
`VFS_TEST_POSTGRES_URL` is set and skips otherwise, so a plain
`uv run pytest` never needs Docker. CI
(`.github/workflows/test-dialects.yml`) uses this same compose file.

vfs is tested on Postgres 17 and 18 with pgvector 0.8. The image is
`pgvector/pgvector:pg17` unless `VFS_PG_IMAGE` names another.

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

Postgres 18 runs from the same file. From 18 the image keeps its data
under `/var/lib/postgresql/18/docker`, so the tmpfs moves to the parent
directory with `VFS_PG_DATA`:

```sh
VFS_PG_IMAGE=pgvector/pgvector:pg18 VFS_PG_DATA=/var/lib/postgresql \
  docker compose -f docker/compose.test.yml up -d --wait
```

The host port is 54320, offset from 5432 so the container never
collides with a Homebrew or Postgres.app install already holding the
default port.

Tear down (data is tmpfs/ephemeral — nothing persists):

```sh
docker compose -f docker/compose.test.yml down -v
```
