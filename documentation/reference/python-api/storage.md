# Storage

A storage backend is what a mount attaches. `DatabaseStorage` keeps its data in a SQL database, and `InMemoryStorage` keeps it in a private in-memory database.

```python
from vfs import DatabaseStorage, InMemoryStorage
```

::: vfs.DatabaseStorage

::: vfs.InMemoryStorage
