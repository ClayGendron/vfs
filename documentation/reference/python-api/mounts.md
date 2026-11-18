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

## Where a Path Lives

`locate()` returns a `Location`, which names the mount that holds a path. `locate_edge()` returns an `EdgeLocation`, which does the same for the two ends of an edge.

```python
from vfs import EdgeLocation, Location
```

::: vfs.Location

::: vfs.EdgeLocation
