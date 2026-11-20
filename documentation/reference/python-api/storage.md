# Storage

A storage backend is what a mount attaches. `DatabaseStorage` keeps its data in a SQL database, and `InMemoryStorage` keeps it in a private in-memory database.

```python
from vfs import DatabaseStorage, InMemoryStorage
```

::: vfs.DatabaseStorage

::: vfs.InMemoryStorage

## Writing a Storage Backend

`StorageBackend` is what every storage backend has. A file system calls a backend with paths it has already checked, so a backend's methods take a `ResolvedPair` for a move or a copy and a `ScopeChannel` for the scope of a search.

```python
from vfs import ResolvedPair, ScopeChannel, StorageBackend
```

::: vfs.StorageBackend

::: vfs.ResolvedPair

::: vfs.ScopeChannel
