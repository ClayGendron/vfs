# Storage

A storage backend is what a mount attaches. VFS supports two engines. `SQLiteStorage` keeps its data in SQLite, the engine for a demo or a local application. `PostgresStorage` keeps it in Postgres, the engine for a shared deployment. `InMemoryStorage` is an `SQLiteStorage` over a private in-memory database.

`DatabaseStorage` is the one class all three are built on, and the type a signature names. It serves any SQLAlchemy URL. A dialect other than SQLite and Postgres is served the generic floor, is withheld `search`, and logs one warning on the `vfs.storage.backends.database.engine` logger. The floor is fit for testing only.

```python
from vfs import SQLiteStorage, PostgresStorage
from vfs import InMemoryStorage, DatabaseStorage
```

::: vfs.SQLiteStorage

::: vfs.PostgresStorage

::: vfs.InMemoryStorage

::: vfs.DatabaseStorage

## Writing a Storage Backend

`StorageBackend` is what every storage backend has. A file system calls a backend with paths it has already checked, so a backend's methods take a `ResolvedPair` for a move or a copy and a `ScopeChannel` for the scope of a search.

```python
from vfs import ResolvedPair, ScopeChannel, StorageBackend
```

::: vfs.StorageBackend

::: vfs.ResolvedPair

::: vfs.ScopeChannel
