# A managed SQLite is studied before it is served

A draft, written on 2026-11-21 from the code review of the named storages, which showed that `SQLiteStorage(url=...)` could not reach a managed SQLite. It is not reviewed, and nothing is built. Its first step is research, and nothing is built before the research answers whether a managed SQLite is worth serving at all.

## The outcome wanted

A decision, made on measured facts, between two answers. Either a managed SQLite service is served as a profile of its own, with the same verb results as SQLite and Postgres, or vfs states that a managed SQLite is not served and names what to use instead. Until the decision, the docs promise neither.

## Builds on

`agents/2026-11-20-vfs-serves-sqlite-and-postgres-only/spec.md`, whose decision 10 gave `SQLiteStorage` a `url=` for a managed SQLite and then dropped it the same day, and the code review of its landings 2 and 3, `context/reviews/2026-11-21-vfs-serves-sqlite-and-postgres-only-landings-2-and-3-code-review.md`, finding L5.

## Terms

- **A managed SQLite** is a hosted database that speaks SQLite's dialect but is reached over the network through its own driver: libSQL and Turso, and Cloudflare D1, are the ones in view.
- **A replicated SQLite** is a local SQLite file that another tool copies elsewhere, as Litestream and LiteFS do. vfs opens it with `SQLiteStorage(path=...)` like any file.

## The problem

Each fact is marked read, run, or from memory. A fact from memory is the research's to confirm or refute.

### What vfs's SQLite profile assumes

- **The aiosqlite driver.** `drivers.merge_engine_arguments` puts `ClosingConnection`, a subclass of `sqlite3.Connection`, into every `sqlite` URL's `connect_args`, and `drivers.load_sqlite_vec` loads nothing unless the connection carries aiosqlite's own `_connection`. Another driver would fail first touch, because the vector probe finds no distance function. Read.
- **sqlite-vec loaded into each connection.** Ranked search needs a cosine distance in the engine, and on SQLite that is sqlite-vec, a core dependency. Read.
- **Interactive transactions.** A write is several statements inside one `BEGIN IMMEDIATE … COMMIT`, which the host's transaction control sends. Read.
- **A local driver thread to interrupt.** A cancelled call ends the statement in flight on aiosqlite's worker thread, and `close()` interrupts a running statistics pass the same way. Read.
- **SQLite's own limits.** Membership chunks are 32,668 keys, under SQLite's 32,766 variables, and the planner statistics come from `sqlite_stat1`. Read.
- **Round trips that cost microseconds.** One write sends many statements; on a local file each is a function call. Read.

### What a managed SQLite is said to change

- **No extension of the caller's own.** A hosted service does not load sqlite-vec. libSQL has vector functions of its own, and D1 pairs with a separate vector service. From memory.
- **D1 has no interactive transaction over its API**, only batches that run atomically. That would break every write. From memory.
- **D1 caps bound parameters per statement far below SQLite.** That would change every chunk size. From memory.
- **Each statement is a network round trip**, on the path where an agent waits. From memory.

### What is already served

- **Managed Postgres.** Every major cloud and several specialists host Postgres, and Postgres is the engine for a shared deployment. Read, in `AGENTS.md`.
- **A replicated SQLite.** It is a local file, so every assumption above holds. Not run.

## Decisions

1. **`SQLiteStorage` takes `path=` alone until this spec decides otherwise.** A SQLite URL with options in its query is served on the same tuned profile by `DatabaseStorage(url=...)`.
2. **The research comes first, and it may end the spec.** It runs libSQL and D1 against each assumption above, through their Python drivers, and measures what a write and a `grep` cost in round trips. If a service needs a profile of its own that is as large as a dropped engine's, the answer is that it is not served, and the docs say so with the two engines to use instead.
3. **A managed SQLite that is served is a profile of its own**, named by its own dialect, never a variant of the SQLite profile. The SQLite profile's arms stay proven on aiosqlite alone.
4. **A replicated SQLite is documented, not built.** A sentence in the docs names Litestream and LiteFS as the way to keep a local SQLite file safe elsewhere, once one is run end to end.

## Tests

None until the research decides. If a service is served, its engine leg runs the storage contract as the Postgres leg does, and each assumption above that the service changes gets a counted test.

## Scope

In: a research memo in this directory, then this spec's decisions and the docs sentence of decision 4. Out: building any profile before the research decides.

## Not checked

- Every fact marked "from memory".
- Whether a replicated SQLite keeps vfs's write lock semantics while its copy runs.
