# Results

Every call returns a `Result`. A failure is carried on it as a `ResultError`.

```python
from vfs import Result, ResultError
```

::: vfs.Result

::: vfs.ResultError

## What a Line Returns

`cli` returns a `LineResult`: a `Result` that also carries what the line printed and the status it exited with. [The Shell](../shell.md) says how a line runs.

```python
from vfs import LineResult
```

::: vfs.LineResult

## What an Error Says

A `ResultError` names what went wrong with an `ErrorKind`, how much to trust the rest of the result with a `Severity`, and whether trying again can help with a `RetryClass`.

```python
from vfs import ErrorKind, RetryClass, Severity
```

::: vfs.ErrorKind

::: vfs.Severity

::: vfs.RetryClass
