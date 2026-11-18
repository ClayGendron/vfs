# Mounts

`Mount` is one storage backend attached at one path. `mounts()` returns one for each mount, and `remove_mount()` returns the one it removed.

```python
from vfs import Mount
```

::: vfs.Mount

`MountPayload` is the JSON form of a `Mount`, what `Mount.to_payload()` returns.

```python
from vfs import MountPayload
```

::: vfs.MountPayload
