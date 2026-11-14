# Sessions

A session holds one caller and one file system, so each call is made as that caller. `AsyncSession` has calls you `await`, and `Session` has the same calls as plain ones.

```python
from vfs import AsyncSession, Session
```

::: vfs.AsyncSession

::: vfs.Session
