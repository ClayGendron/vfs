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

These are the types of some of an entry's fields. A `Vid` is on every row a call returns with a version: it names that file or directory at that version, and it changes when the version does. It is compared and never taken apart. A `write`, `edit`, `delete`, `move` or `restore` that passes a row's vid back as `if_vid` lands only while the row still has that vid. `ABSENT`, given where a vid is given, requires that nothing is at the path.

```python
from vfs import ContentHash, ObjectKind, RenderStatus, Source
from vfs import ABSENT, Vid
```

::: vfs.ObjectKind

::: vfs.Source

::: vfs.ContentHash

::: vfs.Vid

::: vfs.ABSENT

::: vfs.RenderStatus
