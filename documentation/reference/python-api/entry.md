# Entry

An `Entry` is the full record of one file or directory. An `Observation` is what a call returns about an entry, and a `Match` is one region of an entry that a search found. An `Edge` is a typed link from one entry to another.

```python
from vfs import Edge, Entry, Match, Observation
```

::: vfs.Entry

::: vfs.Observation

::: vfs.Match

::: vfs.Edge

## Field Types

These are the types of some of an entry's fields.

```python
from vfs import ContentHash, ObjectKind, RenderStatus, Source
```

::: vfs.ObjectKind

::: vfs.Source

::: vfs.ContentHash

::: vfs.RenderStatus
