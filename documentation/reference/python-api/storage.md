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

A backend that declares the `vid` trait puts a vid on every row it returns with a version. It promises four things. Every such row carries a vid. Two of its rows carry the same vid when, and only when, they are the same entry at the same version. No vid of another storage equals one of its own. And a change that passes it `if_vids` lands only on rows that still have those vids, or, under `ABSENT`, only where nothing is. A mount whose storage does not declare the trait refuses a change that requires a vid, before the storage is called. `VidMint` makes vids that keep these promises, from an identity that is the backend's own. A backend that does not declare the trait returns a version alone.

```python
from vfs import ResolvedPair, ScopeChannel, StorageBackend
from vfs import VidMint
```

::: vfs.StorageBackend

::: vfs.ResolvedPair

::: vfs.ScopeChannel

::: vfs.VidMint
