# Operations

The types that name an operation and carry the arguments of one.

```python
from vfs import CaseMode, EditOperation, GrepOutputMode, Op
from vfs import TwoPathOperation
```

## Operation Names

An `Op` is the name of one operation, such as `read` or `write`. `deny_ops` and `capabilities()` use these names.

::: vfs.Op

## Arguments

`edit` takes an `EditOperation` for each change, and `move` and `copy` take a `TwoPathOperation` for each pair of paths. `grep` takes a `CaseMode` and a `GrepOutputMode`.

::: vfs.EditOperation

::: vfs.TwoPathOperation

::: vfs.CaseMode

::: vfs.GrepOutputMode
